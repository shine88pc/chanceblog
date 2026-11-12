"""확인 필요 모음의 '운영자 결정' 데이터와 오래된 항목을 가려내는 규칙 — 순수 함수(I/O 없음).

이 모듈은 파일을 읽거나 쓰지 않고 네트워크·시계·난수를 쓰지 않는다(시각은 인자). 정책 파일을 읽는 것은 scripts/ops_inbox.py 가, 이 모듈은 읽은 글을 엄격하게
검증하고(parse_policy) 항목 분류에 쓰는 규칙(계절 표·검토 신호)을 한곳에 둔다. 설명서: docs/OPS_INBOX.md §10

정책 파일(pipeline/ops_inbox_policy.json)은 **운영자 결정을 데이터로** 적어 둔 것이다 — 모음의 분류와 표시만 바꾸고 공개 글·초안·설정·일시정지 변수를 자동으로 바꾸지 않는다.
이 파일을 AI 가 자동으로 고치지 않는다(고치는 것은 사람이 검토하는 병합뿐). 칸:
  planned_pause   의도된 일시정지(변수 PIPELINE_PAUSE 가 켜져 있어도 '지금 해야 할 일'이 아니라 참고로 보이게 하는 선언 — 이유·재개 조건·결정 근거가 모두 있어야 한다.
                  resume_gate_passed 는 재개 Gate 가 모두 통과했을 때만 사람이 검토하는 병합으로 켠다 — 켜면 '재개 승인' 항목이 생긴다)
  item_decisions  항목 키 → 결정(keep 유지 · discard_close 폐기 후 닫기 권장 · ignore 무시) + 결정일 + 한 줄 근거. 키는 항목 id 의 앞부분이다(draft:88 은 draft:88:wait·stale 모두).
파일이 없거나 올바르지 않으면 호출하는 쪽이 이 규칙을 쓰지 않고 예전 동작으로 돌아간다(예외로 죽지 않는다).
"""
import calendar
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from pipeline.llm import mask

# ----------------------------------------------------------------------------
# 정책 파일
# ----------------------------------------------------------------------------
POLICY_FILE = "pipeline/ops_inbox_policy.json"      # 저장소 기준 경로(scripts/ops_inbox.py 가 읽는다)
SCHEMA_VERSION = 1
MAX_POLICY_BYTES = 65536                            # 이보다 큰 파일은 읽지 않는다
DECISION_KEEP, DECISION_DISCARD, DECISION_IGNORE = "keep", "discard_close", "ignore"
DECISION_KINDS = (DECISION_KEEP, DECISION_DISCARD, DECISION_IGNORE)
DECISION_KEY_PREFIXES = ("approve", "draft", "blogger", "pr")      # 결정을 걸 수 있는 항목의 종류(승인 대기·초안·Blogger 초안·PR). 실패·워치독 같은 항목은 결정으로 숨길 수 없다
MAX_DECISIONS = 100
MAX_RESUME_CONDITIONS = 12
REASON_MAX, REF_MAX, CONDITION_MAX = 240, 200, 160
DECISION_REASON_MAX = 200
DOC_MAX = 400

_TOP_KEYS = frozenset({"schema_version", "_doc", "planned_pause", "item_decisions"})
_PAUSE_KEYS = frozenset({"active", "since", "reason", "decision_ref", "resume_conditions", "resume_gate_passed"})
_DECISION_KEYS = frozenset({"decision", "date", "reason"})
_KEY_SHAPES = (      # 결정 키는 실제로 쓰는 모양 네 가지뿐이다(2026-11-11 독립 검증 D8 — 앞으로 올 항목까지 가리는 넓은 키를 못 쓰게 한다)
    re.compile(r"^approve:[0-9a-f]{7}$"),                                  # 그 커밋 한 묶음의 승인 대기
    re.compile(r"^draft:[0-9]{1,7}$"),                                     # 이슈·PR 번호 하나(draft:88:wait·stale·season 모두 이 키에 맞는다)
    re.compile(r"^blogger:[a-z][a-z0-9_]{1,30}:drafts:[0-9]{12}$"),        # 그 시각이 가장 새 대기 초안인 Blogger 초안 항목 하나(새 초안이 오면 시각이 바뀌어 풀린다)
    re.compile(r"^pr:[0-9]{1,7}$"),                                        # PR 번호 하나
)
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_FORBIDDEN = (chr(126), "@", "http://", "https://", "www.")      # 물결표(마크다운 취소선으로 읽혀 소스에는 코드 값으로 쓴다)·멘션·주소는 정책 글에 넣지 않는다
_SENSITIVE_SHAPES = (      # 광고(게시자·앱) 번호·계정 번호·전화번호처럼 보이는 글은 정책 글에 넣지 않는다(D8). 날짜(2026-11-09)·문서 절 번호(4-9)는 걸리지 않는다
    re.compile(r"(?i)(?:ca-)?(?:app-)?pub-[0-9]{6,}"),                            # AdSense·AdMob 번호 모양
    re.compile(r"(?<![0-9])[0-9]{9,}(?![0-9])"),                                  # 아홉 자리 이상 숫자(계정·채팅·전화·광고 번호)
    re.compile(r"(?<![0-9])\+?[0-9]{2,4}[ .-][0-9]{3,4}[ .-][0-9]{4}(?![0-9])"),   # 010-1234-5678·02 123 4567 같은 전화번호 모양
)


class PolicyError(ValueError):
    """정책 파일이 올바르지 않다. 메시지는 짧은 한국어 사유이고 파일 경로나 글 내용을 싣지 않는다(모양이 틀린 칸 이름·항목 키의 앞 40자만 예외 — 부르는 쪽이 ext() 로 무력화해 안내에 싣는다)."""


@dataclass(frozen=True)
class PlannedPause:
    active: bool
    since: str = ""
    reason: str = ""
    decision_ref: str = ""
    resume_conditions: tuple = ()
    resume_gate_passed: bool = False

    @property
    def declared(self):
        """'의도된 정지'로 보여 줄 수 있는가: 켜져 있고 이유·재개 조건·결정 근거가 모두 있다(하나라도 없으면 예전 동작)."""
        return bool(self.active and self.reason and self.decision_ref and self.resume_conditions)


@dataclass(frozen=True)
class Decision:
    key: str
    kind: str
    date: str
    reason: str


@dataclass(frozen=True)
class Policy:
    planned_pause: Optional[PlannedPause] = None
    decisions: tuple = ()           # (Decision, …) 키 순

    def decision_for(self, item_id):
        return decision_for(self, item_id)


def decision_for(policy, item_id):
    """항목 id 에 걸린 결정(없으면 None). 키는 id 의 앞부분이다 — `draft:88` 은 `draft:88:wait`·`draft:88:stale` 에, `approve:7f2dfdf` 는 그 id 에만 맞는다.
    가장 긴(구체적인) 키가 이긴다. 정책이 없으면 항상 None."""
    if policy is None or not isinstance(item_id, str):
        return None
    by_key = {decision.key: decision for decision in policy.decisions}
    parts = item_id.split(":")
    for size in range(len(parts), 0, -1):
        found = by_key.get(":".join(parts[:size]))
        if found is not None:
            return found
    return None


def _text(value, name, low, high):
    if not isinstance(value, str):
        raise PolicyError(f"{name}: 글이어야 합니다")
    text = value.strip()
    if not (low <= len(text) <= high):
        raise PolicyError(f"{name}: 길이는 {low}자 이상 {high}자 이하여야 합니다")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise PolicyError(f"{name}: 줄바꿈·제어 문자를 쓸 수 없습니다")
    lowered = text.lower()
    if any(token in lowered for token in _FORBIDDEN):
        raise PolicyError(f"{name}: 물결표·@·주소(http)를 쓸 수 없습니다")
    if mask(text) != text:
        raise PolicyError(f"{name}: 비밀 값처럼 보이는 글이 들어 있습니다")
    if any(shape.search(text) for shape in _SENSITIVE_SHAPES):
        raise PolicyError(f"{name}: 계정·전화·광고 번호처럼 보이는 숫자가 들어 있습니다")
    return text


def _day(value, name, today=None):
    """YYYY-MM-DD 모양의 실제 날짜. today(date)를 주면 오늘보다 뒤의 날짜는 거절한다(운영자가 이미 한 결정·이미 시작한 정지의 날짜라서 — D8)."""
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise PolicyError(f"{name}: YYYY-MM-DD 모양의 날짜여야 합니다")
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise PolicyError(f"{name}: 실제로 있는 날짜여야 합니다") from None
    if today is not None and day > today:
        raise PolicyError(f"{name}: 오늘({today.isoformat()})보다 뒤의 날짜입니다")
    return value


def _flag(value, name):
    if not isinstance(value, bool):
        raise PolicyError(f"{name}: true 또는 false 여야 합니다")
    return value


def _unknown(data, allowed, name):
    extra = sorted(str(key) for key in data if key not in allowed)
    if extra:
        raise PolicyError(f"{name}: 알 수 없는 칸이 있습니다({', '.join(extra)[:60]})")


def _parse_pause(raw, today=None):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PolicyError("planned_pause: 객체 또는 null 이어야 합니다")
    _unknown(raw, _PAUSE_KEYS, "planned_pause")
    active = _flag(raw.get("active"), "planned_pause.active")
    gate = _flag(raw.get("resume_gate_passed", False), "planned_pause.resume_gate_passed")
    if not active:
        # 꺼 둔 선언은 다른 칸이 비어 있어도 된다(있으면 모양은 맞아야 한다)
        return PlannedPause(
            active=False, since=_day(raw["since"], "planned_pause.since", today) if "since" in raw else "",
            reason=_text(raw["reason"], "planned_pause.reason", 1, REASON_MAX) if "reason" in raw else "",
            decision_ref=_text(raw["decision_ref"], "planned_pause.decision_ref", 1, REF_MAX) if "decision_ref" in raw else "",
            resume_conditions=_conditions(raw["resume_conditions"], allow_empty=True) if "resume_conditions" in raw else (), resume_gate_passed=gate)
    for name in ("since", "reason", "decision_ref", "resume_conditions"):
        if name not in raw:
            raise PolicyError(f"planned_pause.{name}: 켜 둔 선언에는 꼭 있어야 합니다")
    return PlannedPause(
        active=True, since=_day(raw["since"], "planned_pause.since", today), reason=_text(raw["reason"], "planned_pause.reason", 1, REASON_MAX),
        decision_ref=_text(raw["decision_ref"], "planned_pause.decision_ref", 1, REF_MAX),
        resume_conditions=_conditions(raw["resume_conditions"]), resume_gate_passed=gate)


def _conditions(raw, allow_empty=False):
    if not isinstance(raw, list):
        raise PolicyError("planned_pause.resume_conditions: 글 목록이어야 합니다")
    if not raw and not allow_empty:
        raise PolicyError("planned_pause.resume_conditions: 재개 조건이 하나 이상 있어야 합니다")
    if len(raw) > MAX_RESUME_CONDITIONS:
        raise PolicyError(f"planned_pause.resume_conditions: {MAX_RESUME_CONDITIONS}개 이하여야 합니다")
    return tuple(_text(item, f"planned_pause.resume_conditions[{index}]", 1, CONDITION_MAX) for index, item in enumerate(raw))


def _valid_key(key):
    return isinstance(key, str) and any(shape.fullmatch(key) for shape in _KEY_SHAPES)


def _parse_decisions(raw, today=None):
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise PolicyError("item_decisions: 객체여야 합니다")
    if len(raw) > MAX_DECISIONS:
        raise PolicyError(f"item_decisions: {MAX_DECISIONS}개 이하여야 합니다")
    out = []
    for key in sorted(raw):
        if not _valid_key(key):
            raise PolicyError(f"item_decisions: 항목 키 모양이 올바르지 않습니다({str(key)[:40]}) — approve:<커밋 7자>·draft:<번호>·blogger:<블로그 키>:drafts:<시각 12자리>·pr:<번호> 중 하나여야 합니다")
        body = raw[key]
        if not isinstance(body, dict):
            raise PolicyError(f"item_decisions.{key}: 객체여야 합니다")
        _unknown(body, _DECISION_KEYS, f"item_decisions.{key}")
        for name in _DECISION_KEYS:
            if name not in body:
                raise PolicyError(f"item_decisions.{key}.{name}: 꼭 있어야 합니다")
        kind = body["decision"]
        if kind not in DECISION_KINDS:
            raise PolicyError(f"item_decisions.{key}.decision: {', '.join(DECISION_KINDS)} 중 하나여야 합니다")
        out.append(Decision(key, kind, _day(body["date"], f"item_decisions.{key}.date", today),
                            _text(body["reason"], f"item_decisions.{key}.reason", 1, DECISION_REASON_MAX)))
    return tuple(out)


def parse_policy(data, today=None):
    """읽어 온 JSON 값 → Policy. 올바르지 않으면 PolicyError(모르는 칸·길이·날짜 모양·종류·키 모양·비밀·번호 모양·물결표 따위 — 하나라도 있으면 파일 전체를 쓰지 않는다).
    today(date, 한국 날짜)를 주면 오늘보다 뒤의 날짜(시작일·결정일)도 거절한다 — 시계는 이 모듈이 읽지 않고 부르는 쪽이 넘긴다."""
    if not isinstance(data, dict):
        raise PolicyError("최상위가 객체가 아닙니다")
    _unknown(data, _TOP_KEYS, "최상위")
    version = data.get("schema_version")
    if type(version) is not int or version != SCHEMA_VERSION:             # 1.0·true 도 거절한다(정수 1 만)
        raise PolicyError(f"schema_version: {SCHEMA_VERSION} 이어야 합니다")
    if "_doc" in data:
        _text(data["_doc"], "_doc", 1, DOC_MAX)
    return Policy(planned_pause=_parse_pause(data.get("planned_pause"), today), decisions=_parse_decisions(data.get("item_decisions"), today))


def _no_duplicate_keys(pairs):
    """json.loads 의 object_pairs_hook — 같은 칸이 두 번 나오면 파일 전체를 거절한다('마지막 값이 조용히 이긴다'를 검토자가 놓치지 않게, D8)."""
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise PolicyError(f"같은 칸이 두 번 있습니다({str(key)[:40]})")
        seen[key] = value
    return seen


def parse_policy_text(text, today=None):
    """정책 파일 글 → Policy. 너무 크거나 JSON 이 아니거나 모양이 틀리면 PolicyError — 같은 칸이 두 번 나오거나, 깊게 중첩돼 파서가 재귀 한도에 닿거나(RecursionError),
    메모리가 모자라도(MemoryError) 예외로 죽지 않고 PolicyError 다(D3·D8). today 는 parse_policy 와 같다."""
    if not isinstance(text, str):
        raise PolicyError("글이 아닙니다")
    if len(text.encode("utf-8")) > MAX_POLICY_BYTES:
        raise PolicyError(f"파일이 {MAX_POLICY_BYTES}바이트보다 큽니다")
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except PolicyError:
        raise
    except RecursionError:
        raise PolicyError("JSON 이 너무 깊게 중첩돼 있습니다") from None
    except MemoryError:
        raise PolicyError("JSON 을 읽는 데 메모리가 모자랍니다") from None
    except ValueError as exc:
        raise PolicyError(f"JSON 형식 오류({getattr(exc, 'lineno', '?')}번째 줄)") from None
    return parse_policy(data, today)


# ----------------------------------------------------------------------------
# 계절·행사 철 표 — '철 지난 초안'(폐기 또는 재생성 검토)을 가려내는 결정적 규칙(형태소 분석·AI 호출 없음)
# ----------------------------------------------------------------------------
# 한 묶음 = (이름, 낱말 정규식, 철 시작 (월, 일), 철 끝 (월, 일)). 구간에는 '미리 준비하는 기간'이 들어 있다(봄맞이는 2월부터). 끝이 시작보다 앞서면 해를 넘기는 구간이다(겨울: 11월–2월).
# 낱말은 pipeline/topics.py 의 계절 낱말(이슈 #92: 가을에 봄맞이 대청소가 나오지 않게)과 같은 것을 쓰고, 날짜가 정해진 행사(추석·김장·설·연말 …)는 계절 전체가 아니라 좁은 구간으로 따로 둔다.
# 한국어는 낱말 첫머리에서만 맞춘다('돌봄'의 '봄'은 계절이 아니다). 모든 낱말을 담을 수는 없다 — 표에 없는 계절 이야기는 철 지난 초안으로 가려내지 못한다(미탐, docs/OPS_INBOX.md §10 한계).
# 사철 쓰는 말(연말정산·새 학기·보일러·난방)과 제목에 든 고유 이름(겨울왕국·한여름 밤의 꿈)은 오탐이라 표에서 빼거나 부정 뒤보기로 걸렀다 — 이 예외도 일부일 뿐이고 남은 오탐은 한계다.
SEASON_GRACE_DAYS = 14          # 철이 끝난 뒤에도 이만큼은 '아직 철'로 본다(초안을 며칠 늦게 읽어도 철 지난 것으로 몰지 않게)
SEASON_TERMS = (
    ("봄", re.compile(r"(?<![가-힣])(?:(?:초|늦|올|지난|이른)?봄|꽃구경|벚꽃|꽃샘|개나리|황사|입춘|식목일)"), (2, 1), (5, 31)),
    ("어린이날·어버이날", re.compile(r"(?<![가-힣])(?:어린이날|어버이날)"), (4, 10), (5, 15)),
    ("여름", re.compile(r"(?<![가-힣])(?:(?:초|늦|올|지난|이른|한)?여름(?! ?밤의 ?꿈)|장마|폭염|무더위|찜통더위|더위|열대야|피서|휴가철|물놀이|모기(?!지|업)|삼복|복날|초복|말복|단오|해수욕)"),
     (5, 15), (8, 31)),
    ("가을", re.compile(r"(?<![가-힣])(?:(?:초|늦|올|지난|이른)?가을|단풍|낙엽|추수)"), (8, 15), (11, 30)),
    ("추석", re.compile(r"(?<![가-힣])(?:추석|한가위)"), (8, 1), (10, 20)),
    ("수능", re.compile(r"(?<![가-힣])수능"), (10, 1), (1, 31)),
    ("김장", re.compile(r"(?<![가-힣])김장"), (11, 1), (12, 20)),
    ("겨울", re.compile(r"(?<![가-힣])(?:(?:초|늦|올|지난|이른|한)?겨울(?!왕국)|한파|폭설|동지(?!애|역)|월동)"), (11, 1), (2, 29)),
    ("설·정월", re.compile(r"(?<![가-힣])(?:설날|설 ?연휴|설 ?명절|구정(?!물)|정월|대보름)"), (12, 15), (3, 5)),
    ("연말·성탄", re.compile(r"(?<![가-힣])(?:연말(?! ?정산)|크리스마스|성탄)"), (11, 15), (1, 10)),
)


def in_season(today, start, end, grace_days=SEASON_GRACE_DAYS):
    """오늘(date)이 철 구간(시작·끝 (월, 일), 끝날 포함) 또는 끝난 뒤 유예 일수 안인가. 끝이 시작보다 앞서면 해를 넘기는 구간이다. 2월 29일은 그 해에 없으면 그 달의 마지막 날로 본다."""
    for year in (today.year - 1, today.year):
        begin = date(year, start[0], start[1])
        finish_year = year if tuple(end) >= tuple(start) else year + 1
        finish = date(finish_year, end[0], min(end[1], calendar.monthrange(finish_year, end[0])[1]))
        if begin <= today <= finish + timedelta(days=grace_days):
            return True
    return False


def season_review(title, today):
    """초안 제목의 계절·행사 낱말이 모두 철이 지난(또는 아직 먼) 것이면 그 묶음 이름들(표 순서), 아니면 None.
    낱말이 하나도 없으면(사철 주제) None 이고, 걸린 묶음 중 하나라도 지금 철(유예 포함) 안이면 None 이다 — 철 지난 것으로 잘못 모는 쪽을 피한다. today 는 한국 날짜(date)."""
    text = str(title or "")
    matched = [term for term in SEASON_TERMS if term[1].search(text)]
    if not matched or any(in_season(today, term[2], term[3]) for term in matched):
        return None
    return tuple(term[0] for term in matched)


def season_window_text(name):
    """철 구간을 사람이 읽는 글로(예: `2월 1일–5월 31일`). 표에 없는 이름이면 빈 글."""
    for label, _pattern, start, end in SEASON_TERMS:
        if label == name:
            return f"{start[0]}월 {start[1]}일–{end[0]}월 {end[1]}일"
    return ""


# ----------------------------------------------------------------------------
# Blogger 초안의 '검토 조건' 신호
# ----------------------------------------------------------------------------
# 6시간 넘게 공개되지 않았다는 사실만으로는 '게시 검토'를 알리지 않는다. Blogger 초안함 업로드 이력 항목(draft_uploaded)에 아래 두 신호가 **명시적으로 긍정**으로 적혀 있어야 한다.
# 둘 다 지금은 아무 쪽도 이력에 기록하지 않는다(쓰는 쪽은 아직 없다) — 그래서 당분간 모든 Blogger 초안은 '검토 조건 미확인'(참고)이다(docs/OPS_INBOX.md §10 한계).
REVIEW_QUALITY_KEY, REVIEW_QUALITY_OK = "review_quality", "pass"       # 품질 Gate 를 통과했다
REVIEW_SAFETY_KEY, REVIEW_SAFETY_OK = "review_safety", "clear"       # 건강·안전 차단 사유가 없다
REVIEW_LABELS = (("품질 Gate 통과", REVIEW_QUALITY_KEY, REVIEW_QUALITY_OK), ("건강·안전 차단 없음", REVIEW_SAFETY_KEY, REVIEW_SAFETY_OK))


def unconfirmed_review_conditions(entry):
    """이력 항목에서 명시적으로 확인되지 않은 검토 조건의 이름 목록(둘 다 확인되면 빈 목록). 값이 없거나 다르거나 항목이 사전이 아니면 확인되지 않은 것이다."""
    data = entry if isinstance(entry, dict) else {}
    return [label for label, key, wanted in REVIEW_LABELS if data.get(key) != wanted]
