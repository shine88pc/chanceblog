"""신규 글 최소 품질 Gate — Chance 후보 글을 규칙만으로 평가해 '보류'(fail closed)할지 가린다.

순수 모듈이다(ENGINEERING_GUIDE R2): 파일·네트워크·시계·환경변수를 읽지 않고, 같은 입력이면 항상 같은 결과를 낸다. 레지스트리·이력·건강 프로필 같은
입력은 호출하는 쪽(generator.py)이 읽어서 넘긴다. 규칙 정의·한계·설정값·그림자 실행 인터페이스는 docs/QUALITY_GATE.md 에 있다.

성격: 보류 규칙에 걸린 후보 글은 버려지고 다음 후보로 넘어간다(전부 탈락하면 그 실행은 글 없이 경고로 끝난다 — 지금의 본문 검증 탈락과 같은 길).
설정 chance.quality_gate 가 없거나 off 면 generator.py 는 이 모듈을 부르지 않는다(기본값, 이전과 같다). 켜는 것은 별도 T3 변경이다.

규칙 8가지(코드 QG1…QG8):
  QG1 숫자 충실  본문의 숫자·퍼센트·금액·날짜가 모델에 준 근거 텍스트에 없으면 보류(단위·표기를 고르게 맞춰 견주고, 환산된 값이 근거에 없으면 보류)
  QG2 인용·직함  따옴표로 인용한 말과 직함이 붙은 사람 이름이 근거 텍스트에 없으면 보류
  QG3 출처 링크  출처 목록을 어떤 모양이든 잘라 낸 '진짜 본문'이 분량 하한에 못 미치거나, 숫자·고유명사 주장이 있는데 본문에 근거 링크가 없으면 보류
  QG4 건강 위험  질환·치료·약·보충제·체중 감량·임신·영유아·증상·진단 신호와 단정 표현이 함께 있거나, 증상에 즉각·단정 효과를 붙인 말(QG4-CLAIM)이거나, 건강 프로필 규칙에 걸리면 보류(의심스러우면 보류)
  QG5 행사·회사  행사 안내 신호가 많거나 출처가 공공·연구기관 도메인이 아니면 보류
  QG6 제목·본문  제목의 숫자와 약속어(추이·전망·순위 같은 말)가 본문에 없으면 보류
  QG7 원문 재사용 이력에 같은 출처 주소가 이미 있으면 보류
  QG8 번역 복제  국문·영문을 둘 다 만드는 설정에서 구조·숫자가 번역 복제로 보이는 쌍은 보류

근거 텍스트 경계: Gate 가 '모델에 준 근거'를 읽는 곳은 evidence_text() 함수 하나뿐이다(출처 신원은 source_ref() 하나). 나중에 근거를 다른 모양(구조화 자료와
출처 기록)으로 바꿔 끼울 때 이 두 함수만 바꾸면 된다 — 규칙 쪽은 그 함수가 돌려주는 글만 본다.
"""
import datetime
import json
import re
import unicodedata
from collections import namedtuple
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, unquote, urlsplit

from pipeline import gates

# ----------------------------------------------------------------------------
# 상수·설정
# ----------------------------------------------------------------------------
LANGS = ("ko", "en")
PREFIX = {"ko": "kr", "en": "en"}           # 후보 데이터(generator.validate_post_data 의 반환)의 키 접두사: kr_title·kr_content / en_title·en_content
LANG_LABEL = {"ko": "국문", "en": "영문"}
LANGUAGE_SETS = (("ko", "en"), ("ko",))      # chance.languages 로 허용하는 값(레지스트리 검증기가 같은 목록을 쓴다)
DEFAULT_LANGUAGES = ("ko", "en")


def normalize_languages(value):
    """chance.languages 값의 단일 정의처(레지스트리 검증기·`chance_settings`·Gate 설정이 모두 이 함수를 쓴다): 'ko' 를 포함하고 ko·en 만 겹침 없이 든 목록·튜플이면 정규 튜플
    ('ko','en') 또는 ('ko',) 를 돌려준다. 순서는 가리지 않는다(['en','ko'] 도 같은 뜻 — 제한 재개 잠금 L6 이 허용하는 집합과 같다). 그 밖의 값은 None."""
    if not isinstance(value, (list, tuple)) or not value or not all(isinstance(item, str) for item in value) or len(set(value)) != len(value):
        return None
    chosen = set(value)
    if chosen == {"ko", "en"}:
        return ("ko", "en")
    if chosen == {"ko"}:
        return ("ko",)
    return None

# 본문 분량 하한(공백·마크다운 기호를 뺀 글자). generator.MIN_BODY_CHARS 와 같은 값이다(시험이 대조한다).
MIN_BODY_CHARS = {"ko": 1000, "en": 1500}
# 입력 상한: 글이 이보다 길면 정규식을 돌리기 전에 보류한다(QG0-INPUT). 지금 글은 2–6천 자라 3만 자면 넉넉하다. 근거 글은 앞 2만 자만 읽는다.
MAX_BODY_CHARS = 30_000
MAX_EVIDENCE_CHARS = 20_000
MAX_MARKER_LINE = 300                        # 이보다 긴 줄은 출처 표지가 아니다(표지 판정은 한 줄씩 정규식을 돌린다)
TAIL_MAX_CHARS = 600                         # 출처 목록 뒤에 이 글자 수(읽기 글자)보다 긴 글이 이어지면 그 표지는 글 끝의 출처 목록이 아니다(글 전체를 본문으로 본다)
MAX_MARKER_CANDIDATES = 20                   # 뒤에서부터 이만큼의 표지 후보만 살핀다(표지 모양 줄을 잔뜩 넣어 시간을 끄는 입력 방어)

# 건강 프로필(읽기 전용 재사용): 국문·영문 Blogger 프로필의 본문 위험 규칙을 두 글 모두에 건다(국문 글에 섞인 영어 병명도 놓치지 않게).
HEALTH_PROFILE_NAMES = ("blogger_practical_ko", "blogger_practical_en")

# QG5: 행사 안내 신호 밀도(본문 1,000자당 신호 수)와 서로 다른 신호 수의 하한. 공개 글에서 보정한 값은 docs/QUALITY_GATE.md.
EVENT_DENSITY_HOLD = {"ko": 4.0, "en": 1.8}          # 영문은 같은 내용이 글자 수가 2배 넘게 길어 밀도 기준이 낮다
EVENT_DISTINCT_HOLD = 3
# QG8: 번역 복제 임계값(감사 결과로 보정: 구조 세 칸이 모두 같으면 복제, 두 칸이 같고 숫자 겹침이 높으면 복제).
CLONE_NUMBER_OVERLAP = 0.40
# QG2: 따옴표 인용으로 보는 길이(말한 사람을 알리는 표현이 곁에 있으면 짧은 것도, 없으면 긴 것만).
QUOTE_CUE_MIN_CHARS = 2                       # 말한 사람을 알리는 표현이 따옴표에 바로 붙어 있으면 2자 이상의 짧은 인용도 센다
QUOTE_LONG_WORDS, QUOTE_LONG_CHARS = 8, 40     # 이만큼 길면 알리는 표현이 없어도 인용으로 센다

# 공공·연구·국제기구 출처 도메인(QG5). 회사 도메인은 여기 없다 — 목록 밖이면 보류한다. generator.NEWS_SOURCES 의 모든 소스가 이 목록에 들어야 한다(시험이 대조한다).
PUBLIC_SOURCE_DOMAINS = (
    "nasa.gov", "noaa.gov", "nih.gov", "nist.gov", "nsf.gov", "cdc.gov", "federalreserve.gov", "ftc.gov", "bls.gov", "spaceweather.gov",
    "europa.eu", "gov.uk", "nhs.uk", "gc.ca", "statcan.gc.ca", "go.kr", "korea.kr", "kostat.go.kr", "kdi.re.kr", "bok.or.kr",
    "un.org", "unesco.org", "unicef.org", "who.int", "oecd.org", "imf.org", "worldbank.org", "ipcc.ch",
    "apa.org", "arxiv.org", "acm.org", "science.org", "pnas.org",
)
# 이 Gate 가 통과시키지 않는 도메인(새 외부 출처 방침: 자동화 제외). 허용 목록에 없으니 QG5-COMPANY 로 보류된다 — 시험이 이 목록의 도메인이 허용 목록에 없음을 못박는다.
EXCLUDED_SOURCE_DOMAINS = ("pewresearch.org",)


class GateConfigError(ValueError):
    """Gate 설정(언어·건강 프로필)이 올바르지 않을 때. 조용히 약한 검사로 떨어지지 않고 멈춘다."""


@dataclass(frozen=True)
class GateConfig:
    """Gate 한 번의 설정. health_profiles: 건강 프로필 사전(pipeline/profiles/*.json 을 읽은 것) 목록 — 비어 있으면 설정 오류다(fail closed)."""
    health_profiles: tuple = ()
    languages: tuple = DEFAULT_LANGUAGES
    public_domains: tuple = PUBLIC_SOURCE_DOMAINS
    min_body_chars: tuple = (("ko", MIN_BODY_CHARS["ko"]), ("en", MIN_BODY_CHARS["en"]))

    def __post_init__(self):
        if tuple(self.languages) not in LANGUAGE_SETS:
            raise GateConfigError(f"languages 는 {[list(s) for s in LANGUAGE_SETS]} 중 하나여야 합니다: {self.languages!r}")
        if not self.health_profiles or not all(isinstance(p, dict) for p in self.health_profiles):
            raise GateConfigError("건강 프로필(health_profiles)이 필요합니다 — 읽지 못했으면 Gate 를 켠 채 약한 검사로 떨어지지 않고 멈춥니다.")

    def minimum(self, lang):
        return dict(self.min_body_chars)[lang]


Hold = namedtuple("Hold", "code rule lang message")
Hold.__doc__ = "보류 사유 하나. code: 'QG1-NUMBER' 같은 코드 · rule: 규칙 번호 1–8(0 은 입력 이상) · lang: ko·en·pair·post · message: 한 줄 한국어 설명."


@dataclass
class GateReport:
    holds: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    @property
    def passed(self):
        return not self.holds

    def codes(self):
        return list(dict.fromkeys(h.code for h in self.holds))

    def lines(self):
        return [f"{h.code} {h.message}" for h in self.holds]

    def summary(self, limit=400):
        """로그·탈락 사유에 한 줄로 쓰는 문장. 코드를 앞에 두어 앞쪽만 잘려도 어떤 규칙인지 보인다."""
        if not self.holds:
            return "품질 Gate 통과"
        text = f"품질 Gate 보류 [{', '.join(self.codes())}]: " + " / ".join(h.message for h in self.holds)
        return _safe(text, limit)


class QualityHold(ValueError):
    """후보 글을 보류해야 할 때(generator 의 후보 검증 칸에서 ValueError 로 잡혀 '탈락 후 다음 후보'가 된다)."""

    def __init__(self, report):
        super().__init__(report.summary())
        self.report = report


def require_pass(report):
    """보류 사유가 있으면 QualityHold 를 던진다(없으면 아무것도 하지 않는다)."""
    if report.holds:
        raise QualityHold(report)
    return report


# ----------------------------------------------------------------------------
# 글자·글 모양 도우미
# ----------------------------------------------------------------------------
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _safe(text, limit=200):
    """로그·결과 파일에 싣는 한 줄(R9): 제어 문자 제거, 줄바꿈 접기, '::'·'##[' 무력화, 길이 제한. 모델·피드가 만든 글이라 소독한다."""
    folded = " ".join(_CTRL.sub(" ", str(text)).split()).replace("##[", "# [").replace("::", ": :")
    return folded[:limit]


def _text(value):
    """None 이나 글이 아닌 값도 빈 글/글로 바꿔 규칙이 입력 모양 때문에 죽지 않게 한다(총함수)."""
    return "" if value is None else str(value)


def _fold(text):
    """견주기 전에 글을 고른다: NFKC(전각 숫자·%·합자), 눈에 안 보이는 서식 문자 제거, 모든 공백을 보통 공백으로."""
    text = unicodedata.normalize("NFKC", "" if text is None else str(text))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


_FRONT = re.compile(r"\A\ufeff?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


def split_front(content):
    """(머리말 문자열 또는 '', 본문)."""
    text = "" if content is None else str(content)
    match = _FRONT.match(text)
    if not match:
        return "", text
    return match.group(1), text[match.end():]


def front_title(front):
    """머리말의 `title:` 값(한 줄 JSON 문자열이면 풀고, 아니면 따옴표만 벗긴다). 없으면 빈 문자열."""
    value = None
    for line in (front or "").split("\n"):                # 줄 단위 문자열 처리 — `title:` 줄 하나를 정규식 `(.*?)[ \t]*$` 로 받으면 공백이 긴 줄에서 제곱 시간
        if line.startswith("title:"):
            value = line[len("title:"):].strip()
            break
    if value is None:
        return ""
    if value.startswith('"'):
        try:
            loaded = json.loads(value)
            if isinstance(loaded, str):
                return loaded
        except ValueError:
            pass
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


# 출처 목록을 알리는 줄의 이름. '출처'·'참고 자료'·'Sources' 처럼 목록의 이름임이 분명한 것만 둔다('관련 자료'처럼 본문 소제목으로도 쓰는 말은 뺀다).
_SOURCE_LABELS = frozenset({
    "출처", "출처 목록", "출처 및 참고 자료", "출처 및 참고자료", "출처와 참고 자료", "출처와 참고자료", "참고 자료", "참고자료", "참고 출처", "참고 링크",
    "참고 문헌", "참고문헌", "원문 출처", "원문 링크", "원문 기사", "자료 출처", "더 읽을거리",
    "참고", "관련 링크", "더 읽어보기", "원문", "원문 보기", "링크", "링크 모음", "출처 및 링크",
    "source", "sources", "reference", "references", "citation", "citations", "further reading", "original source", "original sources",
    "sources and references", "references and sources", "sources and reference", "source and reference", "source and references",
    "links", "link", "read more", "related links", "useful links",
})
_HEADING_OPEN = re.compile(r"^\s{0,3}(#{1,6})[ \t]+(\S.*)$")
_BOLD_LINE = re.compile(r"^\s{0,3}(?:\*\*|__)([^*_\n]{1,60}?)(?:\*\*|__)[ \t]*(.*)$")
_PLAIN_LINE = re.compile(r"^\s{0,3}([^\n:：]{1,40}?)[ \t]*[:：][ \t]*(.*)$")
_RULE_LINE = re.compile(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$")
_LEAD_DECOR = re.compile(r"^(?:>[ \t]*|[-*+•·※▶▷■□◆◇○●▪][ \t]+)+")          # 줄 앞의 인용(>)·글머리·기호(※ ▶ …) — 굵은 글씨 표시(**)는 글머리가 아니다
_LIST_ITEM_LINE = re.compile(r"^[ \t]*(?:[-*+•·]|\d{1,3}[.)])[ \t]+")
_MD_LINK = re.compile(r"!?\[[^\]\n]{0,300}\]\([^)\n]{0,600}\)")
_BARE_URL = re.compile(r"https?://\S+")
_SENTENCE_END = re.compile(r"[.!?。！？]|다\s*$|요\s*$")

Story = namedtuple("Story", "story block tail")
Story.__doc__ = "본문 쪼개기 결과. story: 출처 목록 앞의 진짜 본문(분량·링크·구조를 재는 글) · block: 출처 목록 줄들 · tail: 출처 목록 뒤에 이어진 글(고지문 등 — 규칙은 이것도 읽는다)."


def _label_key(text):
    key = re.sub(r"\([^()\n]{0,40}\)|（[^（）\n]{0,40}）", " ", text or "")             # '출처 (Sources)' 의 괄호 덧말은 뗀다
    key = re.sub(r"[*_`\[\]()（）]", "", key).strip().strip(":：").strip()
    return " ".join(key.split()).casefold()


def _marker_text(line):
    """출처 표지로 볼 수 있는 줄의 글(앞의 인용·글머리 표시를 뗀 것). 비었거나 너무 긴 줄은 표지가 아니다 → ''."""
    stripped = (line or "").strip()
    if not stripped or len(stripped) > MAX_MARKER_LINE:
        return ""
    return _LEAD_DECOR.sub("", stripped, count=1)


def _heading_text(text):
    """마크다운 제목 줄이면 제목 글(닫는 # 은 뗀 것), 아니면 None. 정규식은 여는 부분만 보고 나머지는 문자열 메서드로 뗀다(꼬리를 정규식으로 받으면 공백이 긴 줄에서 3차 역추적)."""
    found = _HEADING_OPEN.match(text)
    if not found:
        return None
    return found.group(2).rstrip().rstrip("#").rstrip()


def _is_source_marker(line):
    """출처 목록을 시작하는 줄인가: 어떤 단계의 제목(#~######)이든, 굵은 글씨 한 줄(**출처**)이든, '출처:' 로 시작하는 줄이든(앞에 > · - · ※ 가 붙어도) 이름이 목록 이름이면 맞다."""
    text = _marker_text(line)
    if not text:
        return False
    heading = _heading_text(text)
    if heading is not None:
        return _label_key(heading) in _SOURCE_LABELS
    found = _BOLD_LINE.match(text)
    if found and _label_key(found.group(1)) in _SOURCE_LABELS:
        rest = found.group(2).strip()
        return not rest or rest[0] in ":：-–—"
    found = _PLAIN_LINE.match(text)
    if found and _label_key(found.group(1)) in _SOURCE_LABELS:
        return True
    return _label_key(text) in _SOURCE_LABELS and len(text) <= 40


def _link_text_free(line):
    """줄에서 마크다운 링크(글자 포함)와 맨 주소를 뗀 나머지."""
    return _BARE_URL.sub(" ", _MD_LINK.sub(" ", line))


def _is_link_entry(line):
    """출처 항목처럼 보이는 줄인가: 링크나 주소가 든 글머리 항목, 또는 링크 위주의 줄(링크 밖 글이 80자 이하)."""
    if not line.strip() or len(line) > 2000:
        return False
    has_link = bool(_MD_LINK.search(line) or _BARE_URL.search(line))
    if _LIST_ITEM_LINE.match(line):
        return has_link
    return has_link and len(_link_text_free(line).strip()) <= 80


def _is_source_entry(line):
    """출처 목록 안에 있는 줄인가: 빈 줄, 들여 쓴 이어짐, 링크 항목, 짧은(60자 이하) 글머리 항목(기관 이름 같은 것). 긴 글머리 글·문단은 목록이 아니라 본문이다."""
    if not line.strip():
        return True
    if line.startswith(("  ", "\t")):
        return True
    if _is_link_entry(line):
        return True
    if _LIST_ITEM_LINE.match(line):
        return len(_LIST_ITEM_LINE.sub("", line, count=1).strip()) <= 60
    return False


def _block_end(lines, start):
    index = start + 1
    while index < len(lines) and _is_source_entry(lines[index]):
        index += 1
    return index


def _end_zone_ok(lines, index):
    """index 줄의 표지 뒤가 '출처 목록 + 짧은 꼬리'인가(꼬리가 TAIL_MAX_CHARS 읽기 글자 이하). 서술 글이 길게 이어지면 이 표지는 글 중간의 캡션이다."""
    end = _block_end(lines, index)
    return readable_length("\n".join(lines[end:])) <= TAIL_MAX_CHARS


def _trailing_link_block_start(lines):
    """라벨이 사전에 없어도 글 맨 끝에 링크 항목이 둘 이상 이어지면 그 목록의 시작 줄 번호(바로 위의 짧은 라벨 줄 포함), 아니면 None."""
    end = len(lines)
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    start, links = end, 0
    while start > 0:
        line = lines[start - 1]
        if not line.strip():
            start -= 1
            continue
        if _is_link_entry(line):
            links += 1
            start -= 1
            continue
        break
    if links < 2:
        return None
    first = start
    while first < end and not lines[first].strip():
        first += 1
    if start > 0:
        above = lines[start - 1].strip()
        if above and len(above) <= 40 and not _SENTENCE_END.search(above):
            return start - 1
    return first


def split_story(body):
    """본문을 (진짜 본문 story, 출처 목록 block, 목록 뒤의 꼬리 tail)으로 쪼갠다.

    지금의 생성기 검사는 `##` 두 개짜리 제목만 잘라 `###`·`**출처**` 모양의 출처 목록이 본문 분량으로 세어졌다 — 여기서는 어떤 모양이든 자른다. 단, '출처 표지처럼 보이는 줄'이 하나 있다고
    그 뒤 글 전체를 검사에서 빼면 안 된다(표 아래 `출처: 통계청` 캡션 뒤의 본문이 모든 규칙을 피해 간다): 글 끝쪽의 진짜 출처 목록(표지 + 링크 항목 + 짧은 꼬리)일 때만 자르고,
    표지 뒤에 서술 글이 길게 이어지면 글 전체를 본문으로 본다. 꼬리(tail)는 규칙이 읽는다. 라벨이 사전에 없어도 맨 끝의 링크 목록은 출처 목록으로 본다."""
    lines = str(body or "").split("\n")
    cut, tried = None, 0
    for index in range(len(lines) - 1, -1, -1):
        if not _is_source_marker(lines[index]):
            continue
        tried += 1
        if _end_zone_ok(lines, index):
            cut = index
            break
        if tried >= MAX_MARKER_CANDIDATES:
            break
    if cut is None:
        cut = _trailing_link_block_start(lines)
    if cut is None:
        return Story("\n".join(lines), "", "")
    story_end = cut
    while story_end > 0 and (not lines[story_end - 1].strip() or _RULE_LINE.match(lines[story_end - 1])):
        story_end -= 1
    end = _block_end(lines, cut)
    return Story("\n".join(lines[:story_end]), "\n".join(lines[cut:end]), "\n".join(lines[end:]))


def story_of(body):
    """본문에서 출처 목록 앞부분('진짜 본문') — split_story 의 story."""
    return split_story(body).story


def _marker_rest(line):
    """표지 줄에서 라벨 뒤에 이어진 글(`출처: …`·`**출처** - …` 의 …). 제목 줄이거나 없으면 ''."""
    text = _marker_text(line)
    if not text or _heading_text(text) is not None:
        return ""
    found = _BOLD_LINE.match(text) or _PLAIN_LINE.match(text)
    return found.group(2) if found else ""


def scan_text_of(parts):
    """규칙이 읽을 글: 진짜 본문 + 출처 목록의 링크 밖 글(링크 글자·주소·글머리는 뗀다 — 링크 제목의 숫자·기관 이름은 주장이 아니다) + 꼬리.
    출처 목록 안에 주장을 숨겨도(링크 옆 문장·긴 글머리) 링크 밖 글은 읽는다."""
    block = ""
    if parts.block:
        first, *rest = parts.block.split("\n")
        pieces = [_marker_rest(first)] + [_LIST_ITEM_LINE.sub("", line, count=1) for line in rest]
        block = "\n".join(_link_text_free(piece) for piece in pieces)
    return "\n\n".join(piece for piece in (parts.story, block, parts.tail) if piece.strip())


_ALT_TEXT = re.compile(r"!\[([^\]\n]{1,300})\]\([^)\n]{0,600}\)")
_HTML_ATTR_TEXT = re.compile(r"""\b(?:title|alt|aria-label)\s*=\s*(?:"([^"\n]{1,300})"|'([^'\n]{1,300})')""", re.I)
_LINK_TEXT = re.compile(r"(?<!!)\[([^\]\n]{1,300})\]\([^)\n]{0,600}\)")


def hidden_health_text(text):
    """화면에는 보이지만 prose_of 가 지우거나 출처 목록에서 빼는 글(이미지 대체글·HTML 속성 title·alt·aria-label 의 값·링크 글자)을 모아 돌려준다. 건강 규칙(QG4)만 이것도 읽는다 —
    효능 단정을 그림 설명이나 링크 글자 속에 숨기지 못하게. 코드 블록은 읽지 않는다(코드의 영어 낱말이 증상·효과 낱말과 겹쳐 기술 글을 오탐하므로 — docs/QUALITY_GATE.md 한계)."""
    text = _text(text)
    pieces = [m.group(1) for m in _ALT_TEXT.finditer(text)] + [m.group(1) or m.group(2) for m in _HTML_ATTR_TEXT.finditer(text)] + [m.group(1) for m in _LINK_TEXT.finditer(text)]
    return "\n".join(piece.strip() for piece in pieces if piece.strip())


def readable_length(story):
    """분량을 재는 글자 수(generator._validate_editorial_body 와 같은 방식: 이미지·링크 주소·HTML·마크다운 기호·공백을 뺀 글자)."""
    readable = re.sub(r"!\[[^\]\n]{0,300}\]\([^)\n]{0,600}\)", " ", _text(story))
    readable = re.sub(r"\[([^\]\n]{1,300})\]\([^)\n]{0,600}\)", r"\1", readable)
    readable = re.sub(r"<[^>]{1,500}>|[`*_>#|~]", " ", readable)
    return len(re.sub(r"\s+", "", readable))


def prose_of(story):
    """주장을 찾을 글: 코드·이미지·링크 주소·HTML·표시 기호를 걷고 링크는 글자만 남긴다(NFKC 로 고른 글)."""
    text = re.sub(r"(?s)```.*?(?:```|\Z)", " ", _text(story))
    text = re.sub(r"`[^`\n]{0,300}`", " ", text)
    text = re.sub(r"!\[[^\]\n]{0,300}\]\([^)\n]{0,600}\)", " ", text)
    text = re.sub(r"\[([^\]\n]{0,300})\]\([^)\n]{0,600}\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"<[^>\n]{1,200}>", " ", text)
    text = re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]*", "", text)
    text = re.sub(r"(?m)^[ \t]*(?:[-*+]|\d{1,3}[.)])[ \t]+", "", text)
    text = re.sub(r"[*_~|]+", " ", text)
    folded = re.sub(r"[^\S\n]+", " ", _fold(text))               # 줄바꿈이 아닌 모든 공백(탭·폼 피드·CR·U+2028 …)을 한 칸으로 — 접히지 않는 공백 연속이 뒤의 정규식을 제곱 시간으로 만들지 못하게
    return re.sub(r"\n{3,}", "\n\n", folded)


_LONG_DIGITS = re.compile(r"\d{16,}")
_SPACE_RUN = re.compile(r"[^\S\n]+")


def _squash(text):
    """기존 위험 규칙(pipeline/gates)에 넘기기 전에 입력을 줄인다: ① 줄바꿈이 아닌 공백 연속(탭·폼 피드·CR·U+2028 …)을 한 칸으로 ② 숫자 연속을 15자리로. 그 규칙의 숫자+단위 패턴과
    `\\s*[;:—―]\\s*` 절 나누기가 숫자·공백 연속에서 제곱 시간이 되기 때문이다(진짜 숫자는 15자리를 넘지 않고 공백 연속은 의미가 없다). 정제하지 않은 글이 들어와도 멈추지 않게 이 함수가 한 번 더 막는다."""
    return _LONG_DIGITS.sub(lambda match: match.group()[:15], _SPACE_RUN.sub(" ", text))


# ----------------------------------------------------------------------------
# 근거 텍스트와 출처 신원 — Gate 가 모델에 준 근거를 읽는 유일한 곳(나중에 다른 모양의 근거로 바꿔 끼우는 자리)
# ----------------------------------------------------------------------------
Evidence = namedtuple("Evidence", "text summary_chars")
SourceRef = namedtuple("SourceRef", "link domain name")


def evidence_text(source):
    """모델에 넘긴 근거(generator.build_post_prompt 가 프롬프트에 싣는 것: 제목·출처 이름·게시 시각·기사 요약)를 한 글로 이어 돌려준다.
    게시 시각은 UTC 날짜와 한국 날짜를 둘 다 적는다(글이 한국 날짜로 쓸 수 있다). 근거가 없으면(source 가 비었으면) 빈 글이다.
    summary_chars 는 그중 기사 요약의 글자 수(그림자 결과의 source_text_chars)."""
    if not isinstance(source, dict):
        return Evidence("", 0)
    title = "" if source.get("title") is None else str(source.get("title"))
    summary = "" if source.get("summary") is None else str(source.get("summary"))
    parts = [title, "" if source.get("source") is None else str(source.get("source"))]
    published = source.get("published")
    if hasattr(published, "isoformat") and hasattr(published, "utcoffset"):
        parts.append(published.isoformat())
        try:
            offset = published.utcoffset()
            kst = (published - offset + datetime.timedelta(hours=9)) if offset is not None else published + datetime.timedelta(hours=9)
            parts.append(kst.date().isoformat())
        except (OverflowError, ValueError, TypeError):
            pass
    parts.append(summary)
    return Evidence("\n".join(p for p in parts if p)[:MAX_EVIDENCE_CHARS], len(summary))


def source_ref(source):
    """출처 신원: (검증된 원문 주소, 게시자 도메인, 출처 이름). 근거 글이 아니라 '어디서 왔나'만 읽는다."""
    if not isinstance(source, dict):
        return SourceRef("", "", "")
    pick = lambda key: "" if source.get(key) is None else str(source.get(key)).strip()   # noqa: E731
    return SourceRef(pick("link"), pick("publisher_domain").lower(), pick("source"))


# ----------------------------------------------------------------------------
# 숫자·날짜 뽑기와 견주기
# ----------------------------------------------------------------------------
Num = namedtuple("Num", "kind value cur raw base")        # kind: pct(퍼센트)·money(통화)·year(연도)·num(건수·측정값·그 밖의 수) / cur: 통화 묶음(USD·KRW·EUR·GBP·JPY·CNY) 또는 ''
DateRef = namedtuple("DateRef", "y m d raw alt", defaults=(None,))    # 없는 칸은 None. 연도만 있는 것(y 만)도 DateRef 다. alt: 월·일 순서가 모호한 숫자 날짜(11/05/2026)의 다른 해석

_DECIMAL = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_DEC_AT = re.compile(_DECIMAL)
_SCAN_STRICT = re.compile(rf"(?<![A-Za-z\d.,])(?:{_DECIMAL})(?!\d)")
_SCAN_LOOSE = re.compile(rf"(?<![\d.,])(?:{_DECIMAL})(?!\d)")
_KO_UNITS = {"조": Decimal(10) ** 12, "억": Decimal(10) ** 8, "만": Decimal(10) ** 4, "천": Decimal(1000), "백": Decimal(100)}
_KO_UNIT_AT = re.compile(r"\s{0,2}([조억만천백])")
_SPACES_AT = re.compile(r" *")
# 숫자 바로 뒤에서 단위가 아닌 낱말의 첫 글자일 때(만큼·만약·억울·조건·천연·백신 …)는 단위로 읽지 않는다
_KO_NOT_UNIT = re.compile(r"(?:만(?:큼|약|들|나|든|족|화|일)|억(?:울|지|제|양|압)|조(?:건|사|치|정|직|금|합|만간)|천(?:연|천|재|문|사)|백(?:신|화|성|인|색|업))")
_SCALE_EN = re.compile(r"\s{0,2}(thousand|million|billion|trillion|bn|mn)s?\b", re.I)
_SCALE_VALUE = {"thousand": Decimal(10) ** 3, "million": Decimal(10) ** 6, "billion": Decimal(10) ** 9, "trillion": Decimal(10) ** 12,
                "bn": Decimal(10) ** 9, "mn": Decimal(10) ** 6}
_PERCENT = re.compile(r"[\s-]{0,2}(?:%|percentage\s+points?|percent|per\s*cent|퍼센트)(?![A-Za-z])", re.I)
_CUR_PREFIX = re.compile(r"(US\$|CA\$|C\$|A\$|[$€£¥₩])\s?$")
_CUR_SUFFIX = re.compile(r"\s{0,2}(원(?!칙|래|활|리|문|본|점|천|인)|달러|유로|엔(?!진)|위안|파운드|KRW|USD|EUR|GBP|JPY|CNY|CAD|AUD|dollars?|euros?|pounds?|yen|yuan|won)(?![A-Za-z])", re.I)
_CUR_CODE = {"$": "USD", "us$": "USD", "ca$": "USD", "c$": "USD", "a$": "USD", "달러": "USD", "usd": "USD", "cad": "USD", "aud": "USD", "dollar": "USD", "dollars": "USD",
             "€": "EUR", "유로": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR",
             "£": "GBP", "파운드": "GBP", "gbp": "GBP", "pound": "GBP", "pounds": "GBP",
             "¥": "JPY", "엔": "JPY", "jpy": "JPY", "yen": "JPY",
             "위안": "CNY", "cny": "CNY", "yuan": "CNY",
             "₩": "KRW", "원": "KRW", "krw": "KRW", "won": "KRW"}
_UNIT = re.compile(r"\s?(?:mm|cm|km|kg|mg|mcg|[μµ]g|ml|ha|mph|kph|km/h|°c|°f|gwh|mwh|kwh|twh|gw|mw|kw|tw|gb|mb|tb|pb|ghz|mhz|khz|hz|nm|ppm|ppb|db|kcal|bpd|km2|m2|"
                   r"miles?|feet|foot|inch(?:es)?|yards?|tons?|tonnes?|kilograms?|grams?|liters?|litres?|meters?|metres?|kilometers?|kilometres?|hectares?|acres?|barrels?|"
                   r"watts?|kilowatts?|megawatts?|gigawatts?|킬로그램|킬로미터|킬로와트|메가와트|기가와트|센티미터|밀리미터|리터|톤|헥타르|배럴|와트|킬로|미터)(?![A-Za-z])", re.I)
_UNIT_TIGHT = re.compile(r"(?:m|g|t|l)(?![A-Za-z])")
# 연도처럼 생긴 정수(2025) 바로 뒤에 세는 말이 붙으면 연도가 아니라 건수다(2025건·2000 people). 연도로 읽으면 근거의 연도 2025년이 이 건수를 받쳐 준다.
_COUNT_SUFFIX = re.compile(r"\s?(?:명|건|개|곳|회|번|세|살|위|배|호|편|권|장|마리|채|부|점|차례|가구|"
                           r"(?:people|persons?|cases?|households?|workers|jobs|children|students|users|votes|deaths|members|employees|respondents|participants|patients|"
                           r"units|items|companies|firms|businesses|schools|projects|incidents|events|vehicles|homes|houses|sites|countries|cities|times)\b)", re.I)


def _decimal(text):
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _ko_compound(text, pos):
    """pos 에서 시작하는 '숫자+한국어 단위' 묶음(3조 4천억·28.8억·1만 5천·2천만·4만 8,200 …)을 읽는다 → (값, 끝 위치) 또는 None."""
    total, small, used, end, i, last = Decimal(0), Decimal(0), False, pos, pos, ""
    while True:
        number = _DEC_AT.match(text, i)
        num = _decimal(number.group()) if number else None
        j = number.end() if number else i
        unit = _KO_UNIT_AT.match(text, j)
        if not unit or _KO_NOT_UNIT.match(text, unit.start(1)):
            break
        if not used and num is None:
            return None
        value = _KO_UNITS[unit.group(1)]
        if unit.group(1) in "천백":
            small += (num if num is not None else Decimal(1)) * value
        else:
            block = small + (num if num is not None else Decimal(0))
            total += (block if block else Decimal(1)) * value
            small = Decimal(0)
        used, end, last = True, unit.end(), unit.group(1)
        look = _SPACES_AT.match(text, end).end()
        nxt = _DEC_AT.match(text, look)
        probe = _KO_UNIT_AT.match(text, nxt.end() if nxt else look)
        if not probe or _KO_NOT_UNIT.match(text, probe.start(1)):
            break
        i = look
    if not used:
        return None
    total += small
    if last in ("조", "억", "만") and not small:       # '4만 8,200'처럼 큰 단위 뒤에 단위 없이 붙는 나머지(콤마가 있거나 세 자리 이상, 그 단위보다 작은 정수)
        tail_at = _SPACES_AT.match(text, end).end()
        tail = _DEC_AT.match(text, tail_at) if tail_at - end <= 2 else None
        if tail and "." not in tail.group() and ("," in tail.group() or len(tail.group()) >= 3):
            remainder = _decimal(tail.group())
            if remainder is not None and remainder < _KO_UNITS[last] and not _KO_UNIT_AT.match(text, tail.end()):
                total, end = total + remainder, tail.end()
    return total, end


def _classify(text, match, strict):
    """숫자 한 토큰의 종류·값·끝 위치. strict(본문)에서는 단위 없는 작은 정수와 영문자가 붙은 식별자(5G·H5N1)를 뺀다. 못 읽으면 (None, 끝 위치)."""
    start, end = match.span()
    raw = match.group()
    base = _decimal(raw)
    if base is None:
        return None, end
    value, scaled = base, False
    compound = _ko_compound(text, start)
    if compound:
        value, end = compound
        raw, scaled = text[start:end].strip(), True
    after = text[end:end + 40]
    before = text[max(0, start - 4):start]
    cur = ""
    prefix = _CUR_PREFIX.search(before)
    if prefix:
        cur = _CUR_CODE[prefix.group(1).lower()]
    if not compound:
        scale = _SCALE_EN.match(after)
        if scale:
            value, scaled, end = base * _SCALE_VALUE[scale.group(1).lower()], True, end + scale.end()
            raw = text[start:end].strip()
            after = text[end:end + 40]
    pct = _PERCENT.match(after)
    if pct and not cur:
        return Num("pct", value, "", text[start:end + pct.end()].strip(), base), end + pct.end()
    suffix = _CUR_SUFFIX.match(after)
    if suffix and not cur:
        cur = _CUR_CODE[suffix.group(1).lower()]
        end += suffix.end()
    if cur:
        lead = len(prefix.group(0)) if prefix else 0
        return Num("money", value, cur, text[max(0, start - lead):end].strip(), base), end
    measured = _UNIT.match(after) or _UNIT_TIGHT.match(after)
    year = not scaled and "," not in raw and "." not in raw and 1900 <= value <= 2100 and not measured and not _COUNT_SUFFIX.match(after)
    if strict:
        if not measured and not scaled and after[:1].isascii() and after[:1].isalpha() and not _COUNT_SUFFIX.match(after):
            return None, end                                      # 5G·4K·21st 같은 식별자·서수는 숫자 주장이 아니다
        if not (scaled or measured or year or value >= 32 or "." in raw or "," in raw):
            return None, end                                      # 단위 없는 31 이하 정수(목록 번호·몇 가지·날짜의 일)는 주장으로 세지 않는다
    if year:
        return Num("year", value, "", raw, base), end             # 근거 쪽에서도 연도를 연도로 읽는다(근거의 2,000명·$2,025 가 연도 2000·2025 를 받쳐 주지 않게)
    return Num("num", value, "", raw, base), end


def _scan_numbers(text, strict):
    found, floor = [], 0
    for match in (_SCAN_STRICT if strict else _SCAN_LOOSE).finditer(text):
        if match.start() < floor:
            continue
        num, floor = _classify(text, match, strict)
        if num is not None:
            found.append(num)
    return found


_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
_MONTH_NUM = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_YEAR = r"(?:19|20)\d{2}"
_DATE_PATTERNS = (       # (정규식, 연·월·일을 담은 묶음 번호 — 없으면 0). 앞의 것이 먼저 읽어 글자를 지운다.
    (re.compile(rf"(?<![\d.])({_YEAR})[-/.](\d{{1,2}})[-/.](\d{{1,2}})(?!\d)"), (1, 2, 3)),
    (re.compile(rf"(?<![\d/.-])(\d{{1,2}})[-/.](\d{{1,2}})[-/.]({_YEAR})(?![\d/-]|\.\d)"), ("mdy", 1, 2)),     # 11/05/2026 — 월·일 순서가 나라마다 달라 두 해석을 모두 받는다
    (re.compile(rf"({_YEAR})\s*년\s*(\d{{1,2}})\s*월\s*(\d{{1,2}})\s*일"), (1, 2, 3)),
    (re.compile(rf"({_YEAR})\s*년\s*(\d{{1,2}})\s*월"), (1, 2, 0)),
    (re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일"), (0, 1, 2)),
    (re.compile(rf"\b({_MONTH})\b\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*({_YEAR}))?(?!\d)"), ("m", 2, 3)),
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH})\b\.?(?:,?\s*({_YEAR}))?(?!\d)"), (3, 2, 1)),
    (re.compile(rf"\b({_MONTH})\b\.?,?\s+({_YEAR})(?!\d)"), ("m2", 2, 0)),
    (re.compile(r"(?<!\d)(\d{1,2})\s*월"), (0, 1, 0)),
    (re.compile(rf"({_YEAR})\s*년"), (1, 0, 0)),
)
_BARE_MONTH = re.compile(rf"\b({_MONTH})\b")


def _month_number(word):
    return _MONTH_NUM.get(word.lower()[:3])


def _make_date(y, m, d, raw):
    if m is not None and not 1 <= m <= 12:
        return None
    if d is not None and not 1 <= d <= 31:
        return None
    if y is not None and not 1900 <= y <= 2100:
        return None
    return DateRef(y, m, d, raw.strip())


def _scan_dates(text, strict):
    """날짜를 읽어 (날짜 목록, 날짜 글자를 지운 글). 지운 글에서 숫자를 읽어야 날짜의 월·일이 숫자 주장으로 따로 세어지지 않는다."""
    found, chars = [], list(text)
    for pattern, groups in _DATE_PATTERNS:
        current = "".join(chars)
        for match in pattern.finditer(current):
            y = m = d = None
            if groups[0] == "mdy":               # 11/05/2026 — 월/일/연 과 일/월/연 두 해석
                first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                readings = [r for r in ((first, second), (second, first)) if 1 <= r[0] <= 12 and 1 <= r[1] <= 31]
                made = [_make_date(year, month, day, match.group()) for month, day in dict.fromkeys(readings)]
                made = [date for date in made if date is not None]
                if not made:
                    continue
                if strict and len(made) > 1:     # 본문: 한 날짜로 세되 다른 해석 하나라도 근거에 있으면 받는다
                    found.append(made[0]._replace(alt=made[1]))
                else:                            # 근거: 가능한 해석을 모두 근거 날짜로 받는다
                    found.extend(made)
                for k in range(match.start(), match.end()):
                    chars[k] = " "
                continue
            if groups[0] == "m":                 # Month day[, year]
                m, d = _month_number(match.group(1)), int(match.group(2))
                y = int(match.group(3)) if match.group(3) else None
            elif groups[0] == "m2":              # Month year
                m, y = _month_number(match.group(1)), int(match.group(2))
            elif groups == (3, 2, 1):            # day Month[, year]
                d, m = int(match.group(1)), _month_number(match.group(2))
                y = int(match.group(3)) if match.group(3) else None
            else:
                y = int(match.group(groups[0])) if groups[0] else None
                m = int(match.group(groups[1])) if groups[1] else None
                d = int(match.group(groups[2])) if groups[2] else None
            date = _make_date(y, m, d, match.group())
            if date is None:
                continue
            found.append(date)
            for k in range(match.start(), match.end()):
                chars[k] = " "
    masked = "".join(chars)
    if not strict:                               # 근거 쪽은 월 이름만 있는 것('until November')도 근거로 받아 준다
        for match in _BARE_MONTH.finditer(masked):
            found.append(DateRef(None, _month_number(match.group(1)), None, match.group()))
    return found, masked


_WORD_VALUE = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
               "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
               "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_WORD_SCALE = {"hundred": 100, "thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9, "trillion": 10 ** 12}
_WORD_RUN = re.compile(r"\b(?:(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
                       r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|trillion|and)(?:[\s-]+|\b))+", re.I)


def _word_numbers(text):
    """영어 숫자 낱말 묶음(two million·twenty-five)을 읽는다 → [(값, 종류, 통화, 큰 단위가 있나, 글자)]. 종류는 뒤에 퍼센트 말이 붙으면 pct, 통화 말이 붙으면 money, 아니면 num.
    근거 텍스트에서는 모두 받아 주고('스무 퍼센트'를 숫자로 쓴 글을 억울하게 보류하지 않게), 본문에서는 값이 32 이상이거나 큰 단위(hundred·thousand·million …)가 있는 것만 주장으로 센다."""
    found = []
    source = text or ""
    for run in _WORD_RUN.finditer(source):
        total, current, seen, scaled = 0, 0, False, False
        for word in re.split(r"[\s-]+", run.group().lower().strip()):
            if word in _WORD_VALUE:
                current, seen = current + _WORD_VALUE[word], True
            elif word == "hundred" and seen:
                current, scaled = (current or 1) * 100, True
            elif word in _WORD_SCALE and seen:
                total, current, scaled = total + (current or 1) * _WORD_SCALE[word], 0, True
        if not seen:
            continue
        after = source[run.end():run.end() + 30]
        suffix = _CUR_SUFFIX.match(after)
        if _PERCENT.match(after):
            kind, cur = "pct", ""
        elif suffix:
            kind, cur = "money", _CUR_CODE[suffix.group(1).lower()]
        else:
            kind, cur = "num", ""
        found.append((Decimal(total + current), kind, cur, scaled, run.group().strip()))
    return found


@dataclass
class Figures:
    nums: list
    dates: list


_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d{1,2}[\s-]{0,2}(?:%|퍼센트|percent|per\s*cent)(?![A-Za-z]))", re.I)      # 유럽식 소수점 쉼표(3,5%) 를 3.5% 로


def extract_figures(text, strict=True):
    """글에서 숫자·날짜 주장을 뽑는다(본문은 strict, 근거는 strict=False 로 작은 수·식별자까지 모두 받아 준다). strict 에서는 영어 숫자 낱말(three million)도 주장으로 센다."""
    folded = _DECIMAL_COMMA.sub(".", _fold(text))
    if len(folded) > MAX_BODY_CHARS:
        folded = folded[:MAX_BODY_CHARS]
    dates, masked = _scan_dates(folded, strict)
    nums = _scan_numbers(masked, strict)
    if strict:
        for value, kind, cur, scaled, raw in _word_numbers(masked):
            if value >= 32 or scaled:
                nums.append(Num(kind, value, cur, raw, value))
    return Figures(nums, dates)


class _Evidence:
    """근거 글에서 뽑아 둔 값을 종류별로 모은다: pct(퍼센트)·money(통화별 금액)·count(건수·측정값·그 밖의 수)·years(연도: 날짜의 연도와 연도로 읽힌 수)·dates·currencies.
    본문의 숫자는 같은 종류의 근거 숫자와만 맞춘다 — 근거의 45명(건수)이 본문 45%(퍼센트)를, 근거의 2,000명이 본문 2000년을 받쳐 주지 않는다."""

    def __init__(self, text, as_of=None):
        text = _text(text)[:MAX_EVIDENCE_CHARS]
        figures = extract_figures(text, strict=False)
        self.pct, self.count, self.year_nums = set(), set(), set()
        self.money = []
        for num in figures.nums:
            both = {num.value, num.base}
            if num.kind == "pct":
                self.pct |= both
            elif num.kind == "money":
                self.money.append((num.value, num.cur))
            elif num.kind == "year":
                self.year_nums |= both
            else:
                self.count |= both
        for value, kind, cur, _scaled, _raw in _word_numbers(_fold(text)):
            if kind == "pct":
                self.pct.add(value)
            elif kind == "money":
                self.money.append((value, cur))
            else:
                self.count.add(value)
        self.dates = list(figures.dates)
        if as_of is not None:
            self.dates.append(DateRef(as_of.year, as_of.month, as_of.day, "as_of"))
        self.years = {Decimal(d.y) for d in self.dates if d.y is not None} | self.year_nums
        self.currencies = {cur for _value, cur in self.money}


def _date_supported(date, evidence):
    for known in evidence.dates:
        if ((date.y is None or known.y == date.y) and (date.m is None or known.m == date.m) and (date.d is None or known.d == date.d)):
            return True
    return date.alt is not None and _date_supported(date.alt, evidence)


def _number_supported(num, evidence):
    if num.kind == "year":
        return num.value in evidence.years
    if num.kind == "pct":
        return num.value in evidence.pct
    if num.kind == "money":
        if any(value == num.value and cur in (num.cur, "") for value, cur in evidence.money):
            return True
        return num.value in evidence.count and not evidence.money      # 근거에 통화 표시가 하나도 없고 같은 값이 있으면 환산이 아니라 표기 차이로 본다
    return num.value in evidence.count


def unsupported_figures(text, evidence_text_value, as_of=None):
    """본문(text)의 숫자·날짜 가운데 근거 글에 없는 것. 돌려주는 값: (숫자 주장 목록, 날짜 주장 목록, 근거 통화 집합)."""
    evidence = _Evidence(evidence_text_value, as_of)
    figures = extract_figures(text, strict=True)
    bad_nums = [n for n in figures.nums if not _number_supported(n, evidence)]
    bad_dates = [d for d in figures.dates if (d.m is None and d.d is None and d.y is not None and Decimal(d.y) not in evidence.years)
                 or ((d.m is not None or d.d is not None) and not _date_supported(d, evidence))]
    return bad_nums, bad_dates, evidence.currencies


# ----------------------------------------------------------------------------
# 따옴표 인용과 직함이 붙은 사람
# ----------------------------------------------------------------------------
_QUOTE_RES = (
    # 안쪽 글자 모임에서 여는 따옴표도 뺀다 — 여는 따옴표가 줄줄이 이어진 글(「「「「…)에서 각 시작점이 2,000자씩 훑다 실패하는 제곱 시간을 막는다(따옴표 안의 같은 종류 따옴표는 올바른 글이 아니다).
    re.compile(r"\"((?:[^\"\n]|\n(?!\s*\n)){1,2000})\""), re.compile(r"“((?:[^”“\n]|\n(?!\s*\n)){1,2000})”"), re.compile(r"„((?:[^“”„\n]|\n(?!\s*\n)){1,2000})[“”]"),
    re.compile(r"「((?:[^」「\n]|\n(?!\s*\n)){1,2000})」"), re.compile(r"『((?:[^』『\n]|\n(?!\s*\n)){1,2000})』"), re.compile(r"«[ \t]?((?:[^»«\n]|\n(?!\s*\n)){1,2000})»"),
    re.compile(r"《((?:[^》《\n]|\n(?!\s*\n)){1,2000})》"),
    re.compile(r"‘((?:[^’‘\n]|’(?=[A-Za-z])|\n(?!\s*\n)){1,2000}?)’(?![A-Za-z])"),                 # 굽은 작은따옴표 ‘…’ (낱말 속 아포스트로피 ’ 는 안쪽으로 본다)
    re.compile(r"(?<![A-Za-z0-9_’'])'((?:[^'\n]|\n(?!\s*\n)){1,2000})'(?![A-Za-z0-9_’'])"),         # 곧은 작은따옴표 '…' (don't 같은 낱말 속 아포스트로피는 여는 따옴표가 아니다. 뒤에 한글 조사가 붙는 것은 따옴표로 본다)
)
# 인용에 말한 사람을 알리는 표현이 '바로 붙어' 있을 때만 짧은 따옴표도 인용으로 센다. 같은 문장에 말했다가 있어도 따옴표 뒤에 조사(가·는)가 붙은 용어 강조("데이터"가 핵심이라고 말했다)는 인용이 아니다.
_CUE_BEFORE = re.compile(
    r"(?:said|says|say|told\s+\S{1,30}|tells\s+\S{1,30}|stated|states|added|adds|noted|notes|explained|explains|argued|argues|wrote|writes|announced|asserted|claimed|warned|"
    r"stressed|emphasi[sz]ed|described|replied|declared|insisted|continued|according\s+to\s+[^,:\"“”]{1,40})\s*(?:that\s+)?[:,]?\s*$|"
    r"(?:말했다|밝혔다|강조했다|설명했다|주장했다|덧붙였다|전했다|말했습니다|밝혔습니다|이렇게\s*말했다)\s*[:,.]?\s*$", re.I)
_CUE_AFTER_EN = re.compile(
    r"[\s,.;:]*(?:[\w'’.-]{1,25}\s+){0,4}?(?:said|says|added|adds|noted|notes|explained|explains|told|argued|argues|claimed|warned|stressed|wrote|writes|announced|declared|insisted|"
    r"continued|replied|stated|asserted|emphasi[sz]ed)\b", re.I)
_CUE_AFTER_KO = re.compile(
    r"\s{0,2}(?:(?:라고|이라고|라며|이라며|라는\s*말|이라는\s*말)(?!\s*(?:부르|불리|불러|칭|일컫|명명|표현|하는))|(?:고|며)\s*(?:말|밝|강조|설명|주장|덧붙|전했|전하|언급|지적|경고|발표|답)|"
    r"(?:고|라고)\s*했)")


def _qnorm(text):
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    return "".join(ch for ch in text if ch.isalnum())


def _speech_adjacent(text, start, end):
    """따옴표(start–end) 바로 앞이나 뒤에 말한 사람을 알리는 표현(said·말했다·라고 강조했다 …)이 붙어 있나."""
    return bool(_CUE_BEFORE.search(text[max(0, start - 45):start]) or _CUE_AFTER_EN.match(text, end, end + 70) or _CUE_AFTER_KO.match(text, end, end + 40))


def _quotes(text, everything=False):
    """따옴표로 감싼 말 가운데 '인용'으로 볼 것: [(안쪽 글, 글 속 위치)]. 따옴표 종류는 큰따옴표·굽은 따옴표·작은따옴표·「」『』«»《》„“. 긴 것(8낱말 또는 40자 이상)은 늘 세고,
    짧은 것은 말한 사람을 알리는 표현이 따옴표에 바로 붙어 있을 때만 센다(2자 이상) — 용어 강조("중위 소득"이라는 말)는 세지 않는다.
    everything=True 는 근거 글을 읽을 때 쓴다: 따옴표로 감싼 2자 이상의 말은 모두 센다(국문 글의 번역 인용이 기댈 수 있는 근거 인용의 개수를 넉넉히 잡는다)."""
    found = []
    for rx in _QUOTE_RES:
        for match in rx.finditer(text):
            inner = match.group(1).strip()
            words, chars = len(inner.split()), len(re.sub(r"\s+", "", inner))
            if chars < 1:
                continue
            if everything:
                if chars >= QUOTE_CUE_MIN_CHARS:
                    found.append((inner, match.start()))
                continue
            long_quote = words >= QUOTE_LONG_WORDS or chars >= QUOTE_LONG_CHARS
            cued = chars >= QUOTE_CUE_MIN_CHARS and _speech_adjacent(text, match.start(), match.end())
            if long_quote or cued:
                found.append((inner, match.start()))
    return found


_EN_TITLE = (r"(?:Commissioner|Executive\s+Vice[-\s]President|Vice[-\s]President|President|Prime\s+Minister|Minister|Secretary|Chair(?:man|woman|person)?|"
             r"Director(?:[-\s]General)?|Governor|Administrator|Dr|Prof(?:essor)?|CEO|Chief\s+[A-Z][a-z]+(?:\s+Officer)?|Senator|Ambassador|Spokes(?:man|woman|person)|"
             r"Attorney\s+General|Mayor|Chancellor|Deputy\s+[A-Z][a-z]+)")
_EN_TITLE_LOWER = (r"(?i:commissioner|executive\s+vice[-\s]president|vice[-\s]president|president|prime\s+minister|minister|secretary|chair(?:man|woman|person)?|"
                   r"director(?:[-\s]general)?|governor|administrator|professor|ceo|chief\s+\w+(?:\s+officer)?|senator|ambassador|spokes(?:man|woman|person)|"
                   r"attorney\s+general|mayor|chancellor)")
_NAME_TOKEN = r"[A-Z][A-Za-z'’\-]+\.?"
_EN_PERSON_AFTER = re.compile(rf"\b{_EN_TITLE}\.?\s+((?:{_NAME_TOKEN}\s+){{0,3}}{_NAME_TOKEN})")
_EN_PERSON_AFTER_LOWER = re.compile(rf"\b{_EN_TITLE_LOWER}\.?\s+((?:{_NAME_TOKEN}\s+){{1,3}}{_NAME_TOKEN})")                  # chief executive Tim Cook·professor Jane Doe
_EN_PERSON_BEFORE = re.compile(rf"\b((?:{_NAME_TOKEN}\s+){{1,3}}{_NAME_TOKEN}),\s+(?:the\s+|a\s+|an\s+)?(?:[\w'’-]{{1,25}}\s+){{0,4}}?{_EN_TITLE_LOWER}\b")     # Jane Marlow, the agency's director
_EN_PERSON_BEFORE_ONE = re.compile(rf"\b({_NAME_TOKEN}),\s+(?:the\s+|a\s+|an\s+)?(?:[\w'’-]{{1,25}}\s+){{0,4}}?{_EN_TITLE_LOWER}\b")                        # Musk, the company's CEO — 문장 첫머리 낱말(However, the director …)은 아래 목록으로 뺀다
_EN_PERSON_NAME_CEO = re.compile(rf"\b((?:{_NAME_TOKEN}\s+){{1,2}}{_NAME_TOKEN})\s+(?:CEO|CTO|CFO|COO|CIO)\b")                                                # Elon Musk CEO announced …
_EN_NOT_NAME = frozenset({"in", "on", "at", "by", "for", "during", "after", "before", "since", "until", "from", "with", "as", "if", "when", "while", "although", "though", "because", "however", "meanwhile", "moreover", "furthermore", "instead", "overall", "today", "yesterday", "tomorrow", "earlier", "later", "still", "also", "then", "thus",
                          "therefore", "additionally", "specifically", "notably", "importantly", "currently", "recently", "finally", "similarly", "nevertheless", "otherwise", "indeed",
                          "first", "second", "third", "next", "last", "now", "here", "there", "yes", "no", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                          "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "spring", "summer", "autumn", "fall", "winter"})
_KO_TITLES = ("부위원장|위원장|집행위원|위원|사무총장|사무차장|장관|차관|청장|처장|원장|총재|총리|대통령|의장|국장|과장|실장|단장|본부장|대변인|사장|회장|부회장|총장|"
              "교수|박사|수석연구원|책임연구원|연구위원|연구원|소장|이사장|대표이사|대사|의원")
_KO_TITLES_NAME_FIRST = _KO_TITLES + "|대표|이사|상무|전무|부사장|CEO|CTO|CFO|COO"        # 이름이 앞에 오는 한국어 어순(김철수 위원장)에서만 쓰는 직함 — 대표·이사 는 '대표적'·'이사회'처럼 흔한 낱말이라 직함이 앞에 오는 어순에는 쓰지 않는다
_KO_PARTICLE = "은는이가의을를도과와께서씨에게로"
_KO_SURNAME = ("남궁|황보|제갈|선우|독고|사공|서문|동방|[김이박최정강조윤장임한오서신권황안송류유전홍고문양손배백허남심노하곽성차주우구민나진지엄채원천방공현변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예경봉사부음]")
_KO_LATIN_NAME_TITLE = re.compile(rf"\b((?:{_NAME_TOKEN}\s+){{0,3}}{_NAME_TOKEN})\s*(?:{_KO_TITLES})")
_KO_TITLE_LATIN_NAME = re.compile(rf"(?:{_KO_TITLES})\s+((?:{_NAME_TOKEN}\s+){{0,3}}{_NAME_TOKEN})")
_KO_TITLE_HANGUL_NAME = re.compile(rf"(?:{_KO_TITLES})\s+([가-힣]{{2,6}})\s([가-힣]{{2,6}})(?=[{_KO_PARTICLE}]?(?:[\s,.)]|$))")
_KO_END = rf"(?=[{_KO_PARTICLE}]?(?:[\s,.)·]|$))"
_KO_NAME_TITLE_SIMPLE = re.compile(rf"(?<![가-힣])((?:{_KO_SURNAME})[가-힣]{{1,2}})[ \t]+(?:[가-힣]{{1,8}}[ \t]+)?[가-힣]{{0,6}}?(?:{_KO_TITLES_NAME_FIRST}){_KO_END}")             # 김철수 위원장은·김철수 한국은행 총재는·김철수 조사국장은
_KO_NAME_TITLE_FOREIGN = re.compile(rf"(?<![가-힣])([가-힣]{{2,5}})[ \t]+([가-힣]{{2,6}})[ \t]+(?:[가-힣]{{1,8}}[ \t]+)?[가-힣]{{0,6}}?(?:{_KO_TITLES_NAME_FIRST}){_KO_END}")   # 제롬 파월 연준 의장은·제인 말로 조사국장은
_KO_TITLE_SIMPLE_NAME = re.compile(rf"(?:{_KO_TITLES})[ \t]+((?:{_KO_SURNAME})[가-힣]{{2}}){_KO_END}")                                                               # 위원장 김철수는
_KO_ONE_WORD_TITLES = "대통령|부통령|총리|수상|주석|총통|국왕|의장|총재|장관|총장|위원장|CEO|CTO|CFO|COO"             # 한 낱말 이름과 함께 쓰는 직함만(회장·사장·대표·교수는 회사·대학 이름 뒤에 흔해 이름으로 읽으면 오탐이 많다)
_KO_ORG_SUFFIX = re.compile(r"(?:은행|공사|공단|협회|연합|연맹|학회|재단|센터|그룹|연구원|연구소|대학교|대학|학교|병원|위원회|이사회|협의회|의회|정당|회의|본부|사무국|사무처|정부|당국|[부청처원국회단사위])$")
_KO_NAME_TITLE_ONE = re.compile(rf"(?<![가-힣])([가-힣]{{2,4}})[ \t]+(?:{_KO_ONE_WORD_TITLES}){_KO_END}")            # 트럼프 대통령은·파월 의장은·시진핑 주석은(한 낱말 외국 인명)
_KO_NOT_NAME = frozenset({
    "러시아", "인도", "이란", "이스라엘", "캐나다", "호주", "브라질", "멕시코", "대만", "북한", "남한", "우크라이나", "터키", "스페인", "이탈리아", "네덜란드", "스웨덴", "노르웨이", "핀란드", "덴마크",
    "폴란드", "사우디", "이집트", "남아공", "아르헨티나", "칠레", "페루", "콜롬비아", "베트남", "태국", "인도네시아", "필리핀", "말레이시아", "싱가포르", "파키스탄", "방글라데시", "여당", "야당",
    "당시", "해당", "우리", "저희", "역대", "회사", "기업", "업체", "학교", "대학", "병원", "본부", "지부", "지사", "명예", "상임", "각국", "당국", "정당", "의회", "정권", "올해", "지난해", "내년",
    "임명", "지명", "선임", "취임", "사임", "퇴임", "승진", "교체", "방문", "연설", "회견", "성명", "참석", "주재", "서명", "결정", "제안", "언급", "강조", "주장", "발표",
    "인사", "발언", "설명", "지적", "경고", "전망", "계획", "정책", "업무", "역할", "책임", "직무", "대행", "후보", "관련", "소속", "산하", "자리", "직책", "직위",
    "정부", "정보", "전문", "전체", "전국", "이번", "이전", "이후", "이날", "이달", "최근", "최대", "최소", "최고", "조사", "조직", "주요", "주무", "한국", "한편", "고위", "강력",
    "문화", "국내", "국제", "신임", "신규", "신설", "현직", "전직", "원내", "서울", "연합", "유엔", "우주", "안전", "임시", "현재", "공동", "공식", "공공", "민간", "국가", "국회",
    "지역", "지방", "중앙", "전임", "차기", "상임", "고용", "노동", "경제", "사회", "정치", "과학", "기술", "의료", "교육", "산업", "금융", "환경", "에너지", "디지털", "데이터",
    "통계", "연구", "개발", "운영", "관리", "행정", "이사회", "위원회", "연구소", "연구원", "대학교", "주식회사", "유한회사", "한국은", "미국", "중국", "일본", "유럽", "독일", "프랑스", "영국",
})
_VERB_END = tuple("다고며서니네요죠")


def _has_particle(token):
    return len(token) > 2 and token[-1] in _KO_PARTICLE


def _hangul_names(text):
    """직함과 붙은 한글 이름: ① 직함이 앞(국장 크리스토퍼 무파리지) ② 이름이 앞(김철수 위원장은, 제롬 파월 연준 의장은). 사건 명사(임명·발표 …)·흔한 낱말과 조사·어미가 붙은 낱말은 이름이 아니라 문장으로 보고 뺀다."""
    names = []
    for match in _KO_TITLE_HANGUL_NAME.finditer(text):
        first, second = match.group(1), match.group(2)
        second_clean = second[:-1] if _has_particle(second) else second
        if _has_particle(first) or first in _KO_NOT_NAME or second_clean in _KO_NOT_NAME or second_clean.endswith(_VERB_END):
            continue
        names.append(f"{first} {second_clean}")
    for rx in (_KO_NAME_TITLE_SIMPLE, _KO_TITLE_SIMPLE_NAME):
        for match in rx.finditer(text):
            name = match.group(1)
            if name not in _KO_NOT_NAME and name[:-1] not in _KO_NOT_NAME and not name.endswith(_VERB_END) and not (name[-1] in _KO_PARTICLE and len(name) == 3):
                names.append(name)
    taken = []                                               # 위 규칙이 이미 읽은 자리(같은 직함을 두 번 세지 않는다)
    for match in _KO_NAME_TITLE_FOREIGN.finditer(text):
        taken.append(match.span())
        first, second = match.group(1), match.group(2)
        if first in _KO_NOT_NAME or second in _KO_NOT_NAME or _has_particle(first) or second.endswith(_VERB_END):
            continue
        names.append(f"{first} {second}")
    for rx in (_KO_NAME_TITLE_SIMPLE, _KO_TITLE_SIMPLE_NAME):
        taken += [match.span() for match in rx.finditer(text)]
    for match in _KO_NAME_TITLE_ONE.finditer(text):          # 한 낱말 외국 인명 + 직함: 근거(한글이면 이름 그대로, 영어면 직함 붙은 사람 수)와 견준다
        name = match.group(1)
        if any(start <= match.start() < end for start, end in taken) or name in _KO_NOT_NAME or _has_particle(name) or _KO_ORG_SUFFIX.search(name):
            continue
        names.append(name)
    return list(dict.fromkeys(names))


def _titled_people(text):
    """직함이 붙은 사람: (라틴 글자 이름 목록, 한글 이름 목록). 글자 모양으로 읽는 근사라 오탐이 있을 수 있고 오탐은 보류 쪽이다."""
    latin = [m.group(1) for rx in (_EN_PERSON_AFTER, _EN_PERSON_AFTER_LOWER, _EN_PERSON_NAME_CEO, _KO_LATIN_NAME_TITLE, _KO_TITLE_LATIN_NAME) for m in rx.finditer(text)]
    for rx in (_EN_PERSON_BEFORE, _EN_PERSON_BEFORE_ONE):          # 직함이 뒤에 오는 어순: 문장 첫머리 낱말·전치사·달 이름으로 시작하는 후보('In March,'·'However,')는 이름이 아니다
        latin += [m.group(1) for m in rx.finditer(text) if m.group(1).split()[0].rstrip(".").casefold() not in _EN_NOT_NAME]
    return latin, _hangul_names(text)


def _names_in(evidence_norm_words, name):
    tokens = [t for t in re.findall(r"[A-Za-zÀ-ɏ'’\-]{2,}", name)]
    return bool(tokens) and all(t.casefold().strip("'’-") in evidence_norm_words for t in tokens)


# ----------------------------------------------------------------------------
# 규칙 구현(규칙마다 보류 사유 목록을 돌려준다)
# ----------------------------------------------------------------------------
def _shorten(tokens, count=3, width=24):
    shown = [_safe(t, width) for t in dict.fromkeys(tokens)][:count]
    rest = len(set(tokens)) - len(shown)
    return ", ".join(shown) + (f" 외 {rest}건" if rest > 0 else "")


def rule_numbers(lang, prose, evidence, as_of=None):
    """QG1 숫자 충실. 근거에 없는 숫자·날짜는 QG1-NUMBER, 근거에 쓰이지 않은 통화로 된 금액(환산 의심)은 QG1-CONVERSION."""
    bad_nums, bad_dates, currencies = unsupported_figures(prose, evidence, as_of)
    label = LANG_LABEL[lang]
    holds = []
    converted = [n for n in bad_nums if n.kind == "money" and n.cur not in currencies]
    plain = [n for n in bad_nums if n not in converted]
    if converted:
        holds.append(Hold("QG1-CONVERSION", 1, lang, f"{label}: 근거에 쓰이지 않은 통화의 금액(환산 의심) —{_shorten([n.raw for n in converted])}"))
    if plain or bad_dates:
        tokens = [n.raw for n in plain] + [d.raw for d in bad_dates]
        holds.append(Hold("QG1-NUMBER", 1, lang, f"{label}: 근거 텍스트에 없는 숫자·날짜 — {_shorten(tokens)}"))
    return holds


def rule_quotes(lang, prose, evidence_value):
    """QG2 인용·직함. 같은 글자 체계 안에서는 근거에 그대로 있어야 하고, 다른 글자 체계(국문 글·영어 근거)는 글자를 맞춰 볼 수 없어 근거에 있는 개수를 넘지 못한다."""
    label = LANG_LABEL[lang]
    holds = []
    prose, evidence_value = _text(prose), _text(evidence_value)
    ev_norm = _qnorm(evidence_value)
    ev_quotes = _quotes(_fold(evidence_value), everything=True)
    literal_missing = []
    for inner, _pos in _quotes(prose):
        if _qnorm(inner) and _qnorm(inner) in ev_norm:
            continue
        literal_missing.append(inner)
    cross = [q for q in literal_missing if re.search(r"[가-힣]", q) and not re.search(r"[가-힣]", evidence_value)]
    same = [q for q in literal_missing if q not in cross]
    if same or len(cross) > len(ev_quotes):
        shown = same + cross[len(ev_quotes):] if same else cross[len(ev_quotes):]
        holds.append(Hold("QG2-QUOTE", 2, lang, f"{label}: 근거 텍스트에 없는 따옴표 인용 — {_shorten(shown, 2, 30)}"))
    latin, hangul = _titled_people(prose)
    ev_words = {w.casefold().strip("'’-") for w in re.findall(r"[A-Za-zÀ-ɏ'’\-]{2,}", evidence_value)}
    unknown = [name for name in latin if not _names_in(ev_words, name)]
    ev_latin, ev_hangul = _titled_people(_fold(evidence_value))
    ev_people = len(ev_latin) + len(ev_hangul)
    ev_has_hangul = bool(re.search(r"[가-힣]", evidence_value))
    if hangul:
        if ev_has_hangul:
            unknown += [name for name in hangul if _qnorm(name) not in ev_norm]
        elif len(hangul) > ev_people:
            unknown += hangul[ev_people:]
    if unknown:
        holds.append(Hold("QG2-PERSON", 2, lang, f"{label}: 근거 텍스트에 없는 직함 붙은 이름 — {_shorten(unknown, 3, 30)}"))
    return holds


def _claims_present(prose):
    figures = extract_figures(prose, strict=True)
    if figures.nums or figures.dates:
        return True
    return bool(re.search(r"(?<![.!?]\s)(?<!^)\b[A-Z][A-Za-z]{2,}\b|\b[A-Z]{2,}\b", prose))


_CODE_FENCE = re.compile(r"(?s)```.*?(?:```|\Z)")
_URL_TRAIL = ".,;:!?)]}>\"'”’"


def story_links(story):
    """본문(출처 목록 앞)에 있는 링크 주소 목록: [글자](주소)의 주소와 맨 주소. 코드 블록·인라인 코드·이미지 안의 주소는 링크가 아니다."""
    text = _CODE_FENCE.sub(" ", _text(story))
    text = re.sub(r"`[^`\n]{0,300}`", " ", text)
    text = re.sub(r"!\[[^\]\n]{0,300}\]\([^)\n]{0,600}\)", " ", text)
    found = [m.group(1) for m in re.finditer(r"\]\(\s*<?([^)\s>]{1,600})", text)]
    found += re.findall(r"https?://[^\s<>)\]\"']{1,600}", text)
    return found


def has_verified_link(story, link):
    """본문에 검증된 원문 주소가 링크로 있나. 주소는 정규화해(대소문자·www·http/https·끝 슬래시·조각·추적 매개변수·질의 순서를 같게) **같을 때만** 맞다 —
    원문 주소로 시작하는 다른 주소(`…/release-1-OTHER-ARTICLE`)나 같은 도메인의 다른 글은 아니다."""
    wanted = normalize_url(link)
    if not wanted:
        return False
    return any(normalize_url(url.rstrip(_URL_TRAIL)) == wanted for url in story_links(story))


def rule_link_and_length(lang, story, prose, link, minimum):
    """QG3 출처 링크·진짜 본문 분량."""
    label = LANG_LABEL[lang]
    holds = []
    story, prose, link = _text(story), _text(prose), _text(link)
    length = readable_length(story)
    if length < minimum:
        holds.append(Hold("QG3-LENGTH", 3, lang, f"{label}: 출처 목록을 뺀 본문이 최소 분량({minimum:,}자)에 못 미침 — {length:,}자"))
    if _claims_present(prose) and not has_verified_link(story, link):
        holds.append(Hold("QG3-LINK", 3, lang, f"{label}: 숫자·고유명사 주장이 있는데 출처 목록 밖 본문에 근거 링크(검증된 원문 주소)가 없음"))
    return holds


_HEALTH_TOPIC = re.compile(
    r"질환|질병|치료|약물|의약|약품|복약|처방|보충제|영양제|건강기능식품|체중\s*감량|다이어트|임신|임산부|영유아|신생아|증상|진단|당뇨|고혈압|우울증|감염|백신|접종|의료|환자|"
    r"(?<![가-힣])암(?![가-힣])|"
    r"\b(?:disease|diseases|illness|illnesses|treatment|treatments|therapy|medication|medications|medicine|drugs?|supplements?|vitamins?|weight[- ]loss|diet|dieting|"
    r"pregnan\w*|infants?|newborns?|symptoms?|diagnos\w*|cancer|diabetes|hypertension|depression|infections?|vaccin\w*|patients?|clinical|dosage)\b", re.I)
# 단정·보장 낱말. `100%` 는 뒤에 글자가 붙지 않아도 단정이다(`\b` 안에 두면 '100% 낮춘다' 처럼 띄어 쓸 때 놓친다). 즉시·바로·immediately 는 여기에 넣지 않는다 —
# '통증이 있을 때 즉시 쉬는 시간을 기록한다'처럼 행동 순서를 꾸미는 부사이기 때문이다(운영자 원칙). 증상에 즉각 효과를 단정하는 말은 QG4-CLAIM 이 효과 동사와 함께 본다.
_HEALTH_ASSERT = re.compile(
    r"반드시|입증|증명|확실(?:히|하게)|틀림없|무조건|명백히|분명히|확증|보장|절대|완벽(?:히|하게)|완치|100\s*%|"
    r"\b(?:definitely|certainly|undoubtedly|proven|proves?|proved|guarantee[sd]?|always|conclusively|without\s+(?:a\s+)?doubt|surely|cure[sd]?)\b", re.I)

# 증상·몸 상태 낱말(프로필의 질환·약 목록에 없는 것): 즉각 효과를 단정하면 C. '자세히' 같은 낱말은 뺀다.
# 낱말 목록(흔한 증상·질환 이름)에 접미 규칙(…염·…증·…증후군·…장애·…병)을 더해 넓히되 '보험증'·'탄산염'·'시스템 장애' 같은 일반어는 막는다. 목록은 닫혀 있다 — 운영자 승인 표본과 검증자의 증상·질환 낱말
# 91개를 큰 시험 목록으로 못박았지만 낱말 규칙으로 '누락 0'을 보증할 수는 없다(docs/QUALITY_GATE.md §9).
_WORD_END = r"(?=(?:[이가을를은는의도에와과로만]|으로|에서|에게|이나)?(?![가-힣]))"
_SYMPTOM_KO = re.compile(
    r"피로|피곤|통증|두통|요통|복통|치통|생리통|월경통|근육통|관절통|신경통|편두통|흉통|인후통|견통|골반통|어깨\s*결림|결림|뻐근|뻣뻣|저림|붓기|부종|염증|우울감|불안감|무기력|불면|수면\s*장애|"
    r"스트레스(?!\s*테스트)|탈모|비듬|가려움|피부\s*트러블|트러블|여드름|아토피|알레르기|감기|기침|콧물|코막힘|몸살|발열|소화\s*불량|속쓰림|변비|설사|더부룩|어지럼|현기증|"
    r"자세(?=[를을이가은는도])|거북목|일자목|굽은\s*어깨|척추|체형|눈\s*피로|안구\s*건조|시력|체중|뱃살|비만|체지방|혈압|혈당|콜레스테롤|수면|허리|어깨|무릎|관절|근육|피부|소화|"
    # 흔한 증상·질환 이름(검증자의 91개를 포함)
    r"비염|(?<!하드)(?<!하드 )(?<!SSD)(?<!SSD )(?<!컴퓨터)(?<!컴퓨터 )(?<!서버)(?<!서버 )(?<!플래시)(?<!플래시 )(?<!USB)(?<!USB )디스크(?!\s*(?:공간|용량|드라이브|오류|조각|포맷|복구|정리|파티션|속도|사용량))|무좀|치질|치핵|통풍|이명(?!박)|귀울림|난청|대상포진|오십견|위염|장염|방광염|중이염|결막염|편도염|부비동염|축농증|건선|습진|두드러기|지루성|족저근막염|손목터널|좌골신경|척추측만|탈장|"
    r"요로결석|신장결석|담석|치주염|구내염|충치|치석|사랑니|턱관절|다래끼|안구건조증|노안|백내장|녹내장|근시|비문증|충혈|저혈압|저혈당|고혈압|빈혈|빈맥|부정맥|두근거림|숨참|호흡곤란|코골이|수면무호흡|"
    r"야뇨|빈뇨|배뇨|요실금|전립선|갱년기|생리불순|불임|발기부전|흉터|건조증|번아웃|공황\s*발작|불안장애|ADHD|자폐|치매|건망증|이석증|멀미|구토|메스꺼움|구취|입\s*냄새|발냄새|체취|다한증|냉증|수족냉증|"
    r"하지정맥류|관절염|류마티스|골다공증|협심증|뇌졸중|지방간|고지혈증|위궤양|과민성대장|역류성|숙취|오한|재채기|가래(?!떡)|독감|목감기|열감|체기|"
    r"다크서클|홍조|새치|흰머리|원형탈모|두피|셀룰라이트|튼살|내장지방|복부비만|군살|평발|무지외반|티눈|굳은살|액취|구강\s*건조|입\s*마름|(?<!\d)\d+\s*(?:[kK][gG]|㎏|킬로그램|킬로)\s*(?:감량|빼|빠|뺀)|"
    # 접미 규칙: …염(비염·관절염·역류성식도염 — 소금·화학·불꽃의 '염'과 감염·전염은 뺀다), …증(불면증·협착증 — 어근 두 글자 이상, 증명서류는 뺀다), …증후군, …장애, …병
    r"[가-힣]{1,6}(?<!저)(?<!고)(?<!무)(?<!천일)(?<!정제)(?<!죽)(?<!암)(?<!화)(?<!탄산)(?<!질산)(?<!황산)(?<!인산)(?<!규산)(?<!감)(?<!전)(?<!오)(?<!요)(?<!방)(?<!식)염" + _WORD_END + r"|"
    r"[가-힣]{2,6}(?<!영수)(?<!허가)(?<!면허)(?<!자격)(?<!등록)(?<!수료)(?<!합격)(?<!회원)(?<!출입)(?<!통행)(?<!학생)(?<!주민)(?<!보험)(?<!신분)(?<!저작권)(?<!참가)(?<!탑승)(?<!임시)(?<!취업)(?<!재직)(?<!졸업)(?<!재학)(?<!납세)(?<!인)(?<!보)(?<!교환)(?<!예약)(?<!계약)(?<!수강)(?<!관람)(?<!이용)(?<!승차)(?<!입장)(?<!사원)(?<!학위)(?<!인정)(?<!검정)증"
    + _WORD_END + r"|"
    r"[가-힣]{2,8}증후군|"
    r"(?:수면|불안|우울|섭식|발달|기억|소화|배뇨|성기능|학습|언어|청각|시각|운동|자폐|공황|강박|양극성|인지|호흡|순환|지적|정신|신경|감각|보행|집중|배변|식이|조현|분리불안|적응|충동조절|성격|해리)\s*장애" + _WORD_END + r"|"
    r"(?:당뇨|심장|정신|불치|난치|성|피부|만성|신장|지|고질|생활습관|희귀|유전|직업|열대)병" + _WORD_END)
_SYMPTOM_EN = re.compile(
    r"\b(?:pain|pains|aches?|headaches?|migraines?|fatigue|tiredness|soreness|stiffness|stress|anxiety|insomnia|colds?|cough|flu|acne|eczema|allerg(?:y|ies)|bloating|"
    r"constipation|nausea|dizziness|hair\s+loss|dandruff|swelling|inflammation|posture|belly\s+fat|body\s+fat|weight|blood\s+pressure|cholesterol|"
    r"snor(?:e|es|ed|ing)|eye\s*strain|sore\s+throat|runny\s+nose|congestion|heartburn|indigestion|acid\s+reflux|hangovers?|wrinkles?|dark\s+circles|cramps?|vertigo|tinnitus|sciatica|"
    r"arthritis|gout|hemorrhoids?|asthma|sinus\w*|depression|stiff\s+neck)\b", re.I)
# 즉각·단정 부사(한국어는 부사가 동사 앞에 온다). 효과 동사와 함께 있어야 의미가 있다.
_IMMEDIATE_KO = re.compile(
    r"즉시|즉각|즉석에서|곧바로|바로|당장|단번에|단숨에|한\s*번에|한\s*방에|순식간(?:에)?|금세|금방|눈\s*깜짝할\s*사이에|눈\s*녹듯|그\s*자리에서|하룻밤(?:\s*(?:만에|에|안에|사이에))?|딱\s*한\s*번|한\s*번만|싹(?=\s)|(?<![가-힣])(?:확|쏙|쫙|쭉|뚝)(?=\s)|"
    r"(?:하루|이틀|사흘|나흘|일주일|이주일|한\s*달|며칠|\d+\s*(?:분|시간|일|주|개월))\s*(?:이면|이내|만에|안에|내에|동안)|"
    r"완전(?:히|하게)?|완벽(?:히|하게)?|확실(?:히|하게)?|무조건|반드시|100\s*(?:%|퍼센트)|백\s*퍼센트|영원히|영구(?:적(?:으로)?|히)|평생|깨끗(?:이|하게)|깔끔(?:히|하게)|말끔(?:히|하게)|뿌리\s*뽑|근본적으로|전혀|절대|보장")
# 효과 동사의 어간(활용형: 줄인다·줄이는·줄일 수 있다·줄여 준다·줄여줍니다·풀립니다·가라앉습니다). '나아가'(나아가다)·'낫'(낫다)을 가린다. '치료를 받' 처럼 목적어로 쓴 말(행동)은 효과 동사가 아니다.
# '멈추'는 증상이 주어인 활용(멈춥니다·멈췄다·멈춰)만 센다 — '작업을 즉시 멈추세요'는 행동이다.
_EFFECT_KO = re.compile(
    r"(?:줄이|줄여|줄인|줄일|줄임|줄입|줄어|줄었|없애|없앤|없앨|없앱|없앴|없어지|없어진|없어져|없어집|없어졌|사라지|사라진|사라질|사라집|사라져|사라졌|해소|풀리|풀려|풀린|풀릴|풀립|풀렸|풀어|해결|교정|바로잡|치료|완치|"
    r"낫(?:는|습|게|다|고|기|도록|아|지)|나았|나아(?!가)|나은|나을|완화|개선|회복|예방|감량|제거|막아|막는|막은|막을|막습|잡아|잡는|잡은|잡습|날려|날리|날립|날아|덜어|낮추|낮춰|낮춘|낮출|낮춥|끝내|끝냅|"
    r"가라앉|멈춥|멈춘다|멈췄|멈춰(?!\s*주세요)|멈추게|멎|뚫리|뚫려|뚫린|뚫립|뚫어|뚫습|편안해지|편안해져|편안해집|편해지|편해져|펴지|펴져|펴집|펴\s*주|펴준|정복|차단|녹이|녹여|녹입|녹아|태우|태워|태웁|"
    r"좋아지|좋아져|좋아집|호전|치유|잊게|잊도록|털어|떨쳐|떨치|몰아내|물리치(?!료)|물리쳐|극복|탈출|퇴치|끝장|개운|가뿐|가벼워지|가벼워집|가벼워져|정상화|떨어지|떨어집|떨어졌|떨어뜨리|떨어트리|씻어\s*내|되찾|되살|되돌리|되돌려|되돌립|젊어지|젊어져|젊어집|재생(?=[시하해합되된됩될됨됐돼])|빠지는|빠집|"
    r"가시(?=는\s*(?:비밀|비결|비법|효과|마법|차|음료|습관)|어(?:요|집)|었|네요|죠))(?![을를]\s*(?:받|위해|통해))")
_IMMEDIATE_EN = re.compile(
    r"\b(?:instantly|immediately|instant|immediate|right\s+away|at\s+once|overnight|in\s+(?:minutes|seconds|no\s+time|(?:a|an|one|two|three|four|five|six|seven|ten|\d+)\s+(?:seconds?|minutes?|hours?|days?|nights?|weeks?))|"
    r"within\s+(?:a|an|one|\d+)\s+(?:hour|day|week)s?|completely|totally|fully|permanently|permanent|forever|"
    r"once\s+and\s+for\s+all|guaranteed|definitely|absolutely|always|for\s+good|never\s+again)\b|100\s*%", re.I)
_EFFECT_EN = re.compile(
    r"\b(?:eliminat\w*|cur(?:e|es|ed|ing)|relie(?:ve|ves|ved|ving|f)|remov\w*|vanish\w*|disappear\w*|eras(?:e|es|ed|ing)|stop(?:s|ped|ping)?|fix(?:es|ed|ing)?|solv(?:e|es|ed|ing)|"
    r"end(?:s|ed|ing)?|banish\w*|melt(?:s|ed|ing)?\s+away|reduc(?:e|es|ed|ing)|eas(?:e|es|ed|ing)|heal(?:s|ed|ing)?|clear(?:s|ed|ing)?|gone|kill(?:s|ed|ing)?|"
    r"wip(?:e|es|ed|ing)|get(?:s|ting)?\s+rid\s+of|resolv\w*|prevent(?:s|ed|ing)?|goodbye|farewell|knock(?:s|ed|ing)?\s+out|beat(?:s|ing)?|conquer\w*|eradicat\w*|"
    r"los(?:e|es|ing|t)|shed(?:s|ding)?|burn(?:s|ed|ing)?|drop(?:s|ped|ping)?|treat(?:s|ed|ing)?|soothe\w*|zap\w*|crush\w*|neutraliz\w*)\b", re.I)
# 글을 효과 단정을 찾을 조각으로 가른다: 문장 경계(마침표·줄바꿈)는 늘 경계이고, 절 경계(쉼표·느낌표·쌍점·물음표)는 짧은 글에서는 경계로 쓰지 않고 긴 글에서는 이웃한 두 절을 함께 본다(물음표는 짧은 질문 뒤에 답이 이어질 때만).
_HARD_SPLIT = re.compile(r"[.。\n]+")
_SOFT_SPLIT = re.compile(r"([,，、;；!！?？]+)")
CLAIM_SHORT_CHARS = 120            # 제목처럼 이보다 짧은 글은 쉼표·느낌표·물음표뿐 아니라 마침표도 경계로 쓰지 않고 통째로 본다('허리 통증, 즉시 줄이는 방법'·'피로가 심한가요? 즉시 해소')
CLAIM_QUESTION_CHARS = 40          # 물음표 앞 절이 이 글자 수 이하일 때만 뒤 절과 이어 본다('요즘 피곤하신가요? 이 비타민 하나면 즉시 회복됩니다')
CLAIM_WINDOW, CLAIM_STEP = 400, 200          # 400자를 넘는 조각은 자르지 않고 겹치는 창(400자 창·200자 간격)으로 훑는다 — 앞 400자만 보면 긴 문장 뒤의 단정이 빠진다
# 증상이 있는 같은 조각에 '제로·걱정 끝·이제 안녕'처럼 증상이 없어진다고 단정하는 문구가 있으면 효과 동사가 없어도 C 다('두통 제로 비법'·'통증 걱정 끝, 이 의자 하나로').
_RIDDANCE_KO = re.compile(r"제로(?![가-힣])|걱정\s*(?:끝|없(?:는|이|어))|고민\s*끝|이제\s*(?:끝|안녕)(?![가-힣])|안녕\s*(?=통증|두통|피로|스트레스)|굿바이|작별")
# 시간 부사(즉시·바로·당장 …) + 효과 동사가 명령형('바로 자세를 교정하세요')이면 그 부사는 행동을 재촉하는 것이지 결과를 단정하는 것이 아니다. 단정 부사(완전히·확실히 …)는 명령형이어도 단정이다('이 샴푸로 완전히 해결하세요').
_TEMPORAL_KO = frozenset({"즉시", "즉각", "곧바로", "바로", "당장"})
_IMPERATIVE_AFTER = re.compile(r"\s*[가-힣]{0,2}(?:세요|십시오|시오|합시다|하자|하라)(?![가-힣])|\s*[가-힣]{0,2}\s*(?:보세요|주세요|드세요)")
_CLAIM_GAP_KO_CAP = 40             # 한국어: 부사와 효과 동사 사이 글자 수의 느슨한 상한(구조 규칙이 주된 판정이고 이것은 멀리 떨어진 말을 잇지 않으려는 안전선이다)
_CLAIM_GAP_EN = 30
# 부사와 효과 동사 사이에 다른 서술어(행동)가 끼면 부사는 그 행동 순서를 꾸미는 것이다('즉시 병원에 가서 치료를 받으세요'). 명사구·부사만 끼면 효과 결과를 꾸미는 것이다('즉시 이 베개 하나만으로 줄일 수 있습니다').
_ACTION_IN_GAP = re.compile(
    r"세요|십시오|합시다|[가-힣]{1,4}하고(?=\s|$)|하며|하면서|하여|해서|한\s*뒤|한\s*후|한\s*다음|하다가|하자마자|가서|가고|가면|갑니다|찾아가|방문|예약|"
    r"받고|받아|받으|받는|받습니다|드세요|드시|먹고|먹어|먹으|먹는|마시고|마시면|마셔|바르고|바르면|발라|복용|섭취|취해|취하고|쉬고|쉬어|쉬면|눕|앉아|앉으|일어나|씻고|씻어|닦|찜질|끊고|끊어|끊으|중단")
_OBJECT_IN_GAP = re.compile(r"([가-힣A-Za-z0-9]{1,12}[을를])(?=\s|$)")
# 상담을 부정하는 표현(상담·병원 안 가도·없이): 있으면 상담 안내 절이 아니라 위험한 권유다 — 프로필의 상담 절 면제를 받을 수 없다.
_NEGATED_CONSULT = re.compile(
    r"(?:의사|약사|전문가|전문의|의료진|주치의|병원|한의원|상담|문의|진료|진찰|방문|도움|조언)[^.!?\n]{0,14}?(?:하지\s*않|않아도|않고도|없이|없어도|말고|필요\s*(?:가\s*)?없|안\s*(?:해도|받아도|가도|가고))|"
    r"(?:병원|의사|약사)(?:에|을|를)?\s*(?:가지|찾지|방문하지)\s*않|"
    r"\b(?:without|no\s+need\s+(?:to|for)|instead\s+of|skip(?:ping)?|never\s+(?:see|visit|consult))\b[^.!?\n]{0,30}?\b(?:doctors?|physicians?|pharmacists?|hospital|medical\s+(?:advice|help|care)|prescription)\b", re.I)


def _claim_units(text):
    """효과 단정을 찾을 글 조각을 차례로 돌려준다. 제목처럼 짧은 글(CLAIM_SHORT_CHARS 이하, 줄바꿈 없음)은 통째로 한 조각이다 — 쉼표·느낌표·물음표 뒤의 즉각 효과도 앞의 증상과 이어서 본다.
    그보다 긴 글은 문장 경계(마침표·줄바꿈)로 가르고, 문장이 짧으면(CLAIM_SHORT_CHARS 이하) 문장 하나가 한 조각, 길면 절(쉼표·느낌표·물음표·쌍점 사이) 하나씩과 이웃한 두 절을 이은 것이 조각이다."""
    text = _text(text).strip()
    if not text:
        return
    if len(text) <= CLAIM_SHORT_CHARS and "\n" not in text:
        yield text
        return
    for segment in _HARD_SPLIT.split(text):
        segment = segment.strip()
        if not segment:
            continue
        if len(segment) <= CLAIM_SHORT_CHARS:
            yield segment
            continue
        parts = _SOFT_SPLIT.split(segment)             # [절, 구분자, 절, 구분자, …]
        clauses = [parts[i].strip() for i in range(0, len(parts), 2)]
        marks = [parts[i] for i in range(1, len(parts), 2)]
        for index, clause in enumerate(clauses):
            if clause:
                yield clause
            if index < len(marks) and clause and clauses[index + 1] and len(clause) + len(clauses[index + 1]) < CLAIM_WINDOW:
                if "?" in marks[index] or "？" in marks[index]:
                    if len(clause) > CLAIM_QUESTION_CHARS:           # 짧은 질문('피곤하세요?') 뒤의 답만 잇는다 — 긴 문장 끝의 물음표는 경계다
                        continue
                yield clause + " " + clauses[index + 1]


def _claim_windows(unit):
    """조각이 CLAIM_WINDOW 자를 넘으면 자르지 않고 겹치는 창(CLAIM_WINDOW 자 창·CLAIM_STEP 자 간격)으로 나눈다(시간은 글 길이에 비례)."""
    if len(unit) <= CLAIM_WINDOW:
        yield unit
        return
    for start in range(0, len(unit), CLAIM_STEP):
        yield unit[start:start + CLAIM_WINDOW]
        if start + CLAIM_WINDOW >= len(unit):
            break


def _ko_gap_modifies_result(gap):
    """한국어: 즉각·단정 부사와 효과 동사 사이(gap)가 결과를 꾸미는 말인가. 사이에 다른 서술어(행동: 가서·받·드세요·하고 …)나 증상이 아닌 다른 대상(…을·를)이 끼면 그 행동의 순서를 꾸미는 부사이므로 C 가 아니다.
    명사구·부사만 끼면(이 베개 하나만으로·하루 한 번 이 방법만으로·그리고 영구적으로·눈에 띄게) 효과 결과를 꾸미는 것이다. 너무 멀리(CLAIM_GAP 상한) 떨어진 말은 잇지 않는다."""
    if len(gap) > _CLAIM_GAP_KO_CAP or _ACTION_IN_GAP.search(gap):
        return False
    return all(_SYMPTOM_KO.search(noun) or _SYMPTOM_EN.search(noun) for noun in _OBJECT_IN_GAP.findall(gap))          # noun 은 조사(을·를)까지 붙은 낱말


def _claim_in(unit, lang):
    """조각 하나에서 증상 + 즉각·단정 부사 + 효과 동사를 찾는다 → (증상, 부사, 동사) 또는 None."""
    symptom = _SYMPTOM_KO.search(unit) or _SYMPTOM_EN.search(unit)
    if not symptom:
        return None
    if lang == "ko":
        for adverb in _IMMEDIATE_KO.finditer(unit):
            effect = _EFFECT_KO.search(unit, adverb.end())          # 부사 뒤의 첫 효과 동사만 본다 — 더 뒤의 동사는 사이가 더 길어 같은 이유로 막힌다
            if effect and _ko_gap_modifies_result(unit[adverb.end():effect.start()]):
                if adverb.group(0) in _TEMPORAL_KO and _IMPERATIVE_AFTER.match(unit, effect.end()):
                    continue                                        # '바로 자세를 교정하세요' — 행동을 재촉하는 말
                return symptom.group(0), adverb.group(0), effect.group(0)
        riddance = _RIDDANCE_KO.search(unit)
        if riddance:
            return symptom.group(0), riddance.group(0), riddance.group(0)
        return None
    for adverb in _IMMEDIATE_EN.finditer(unit):
        for effect in _EFFECT_EN.finditer(unit):
            if abs(effect.start() - adverb.end()) <= _CLAIM_GAP_EN or abs(adverb.start() - effect.end()) <= _CLAIM_GAP_EN:
                return symptom.group(0), adverb.group(0), effect.group(0)
    return None


def _effect_claim(text, lang):
    """증상·몸 상태 + 즉각·단정 표현 + 효과 동사가 한 조각에 있으면 (증상, 부사, 동사) 낱말, 아니면 None. 운영자 판정 C(피로를 즉시 줄이는 방법·통증을 완전히 없애는 의자 선택법).
    한국어는 부사와 효과 동사 사이에 다른 서술어(행동)·다른 대상이 끼면 C 가 아니다 — '바로 확인한다'·'즉시 병원에 가서 치료를 받으세요'처럼 행동 순서를 꾸미는 부사는 효과 동사를 꾸미지 않는다. 영어는
    부사가 동사 앞뒤 어느 쪽이든 30자 안. 조각 나누기와 창은 _claim_units·_claim_windows."""
    for unit in _claim_units(text):
        for window in _claim_windows(unit):
            found = _claim_in(window, lang)
            if found is not None:
                return found
    return None


def _claim_lang_hit(text):
    """국문·영문 두 글에 모두 거는 효과 단정 검사(국문 글에 섞인 영어 문장도 놓치지 않게): 한국어 규칙과 영어 규칙을 둘 다 돌린다."""
    return _effect_claim(text, "ko") or _effect_claim(text, "en")


# 질환·증상을 '이 영양제·이 방법으로 낫는다·치료한다'고 단정하는 말(상담 문구가 붙어도 효능 주장이다: '의사와 상담하세요(이 약은 암을 치료합니다)'·'의사에게 물어보면 이 영양제로 당뇨가 낫는다고 합니다').
# 지시어('이·그·저·해당') + 제품·방법 낱말 + 같은 문장의 낫는다·치료한다 같은 단정 활용. 부정·반박('못합니다'·'근거는 없다')과 정보 문장('치료하는 데 쓰입니다')은 건너뛴다.
_PRODUCT_NOUN = (r"(?:영양제|보충제|건강기능식품|약물|약|식품|식단|음식|차|음료|제품|기기|기구|앱|방법|비법|비결|요법|치료법|운동|스트레칭|습관|베개|의자|샴푸|크림|마스크|패치|침대|매트리스)"
                 r"(?=(?:[이가은는을를로과와의도만]|으로|에게|에서)?(?![가-힣]))")
_PRODUCT_CURE = re.compile(
    r"(?:이|그|저|해당)\s*" + _PRODUCT_NOUN + r"[^.!?\n]{0,40}?"
    r"(?:낫(?:는다|습니다|게\s*합니다|게\s*해)|나아(?:집니다|진다|져요)|치료(?:합니다|한다|됩니다|된다|해\s*줍니다|해줍니다)|완치(?:합니다|한다|됩니다|된다|시킵니다)|고쳐\s*줍니다|고칩니다|고친다|"
    r"사라집니다|사라진다|없앱니다|없앤다|해결(?:합니다|한다|됩니다|된다)|개선(?:합니다|한다|됩니다|된다))")
_CURE_GUARD = re.compile(r"않|없다|없습니다|아니|못\s|못합|입증되지|증명되지|확인되지|근거|과학적|주장|광고|허위|과장|주의|믿지|사실이")


def _profile_topic(profiles, text):
    """프로필의 금지 주제 낱말(질환·약·보충제 …)이나 증상 낱말이 text 에 있으면 그 낱말, 없으면 None."""
    for profile in profiles:
        raw, word = gates.first_match(profile.get("banned_topic_patterns"), text)
        if raw is not None:
            return word
    found = _HEALTH_TOPIC.search(text) or _SYMPTOM_KO.search(text) or _SYMPTOM_EN.search(text)
    return found.group(0) if found else None


def rule_health(lang, title, prose, profiles):
    """QG4 건강 위험(fail closed).
    ① 건강 프로필의 본문 위험 규칙(pipeline/gates.body_risk_hit, 읽기 전용 재사용) — 상담·면책 절은 프로필 규칙대로 건너뛴다.
    ② 프로필의 효능 단정 목록(banned_patterns: 완치·만병통치·기적의·특효·부작용 없음·100% 효과 …)을 제목·본문 전체에 면제 없이 건다(상담 문구가 붙어도 단정은 단정이다).
    ③ 상담을 부정하는 문장('의사 상담 없이'·'병원에 가지 않아도')은 상담 안내가 아니므로 프로필 면제 없이 위험 낱말을 본다.
    ④ 건강 신호(프로필 주제 낱말·증상)와 단정 낱말이 같은 문단에 함께 있으면(면책 절 안이어도) 보류.
    ⑤ 증상·몸 상태 + 즉각·단정 부사 + 효과 동사(QG4-CLAIM, 제목 포함) — 운영자 판정 C.  ⑥ 제목의 금지 주제 낱말(QG4-TITLE)."""
    label = LANG_LABEL[lang]
    holds = []
    title, prose = _text(title)[:1000], _squash(_text(prose))
    both = title + "\n" + prose
    for profile in profiles:
        raw, word = gates.body_risk_hit(prose, profile)
        if raw is not None:
            holds.append(Hold("QG4-HEALTH", 4, lang, f"{label}: 건강 위험 표현(프로필 규칙) — '{_safe(word, 30)}'"))
            break
    if not holds:
        for profile in profiles:
            raw, word = gates.first_match(profile.get("banned_patterns"), both)
            if raw is not None:
                holds.append(Hold("QG4-HEALTH", 4, lang, f"{label}: 효능 단정 표현(프로필 banned_patterns, 상담 문구가 있어도 면제 없음) — '{_safe(word, 30)}'"))
                break
    if not holds:
        for sentence in re.split(r"[.!?。！？\n]+", prose):
            if sentence.strip() and _NEGATED_CONSULT.search(sentence):
                topic = None
                for profile in profiles:
                    raw, word = gates.first_match(profile.get("body_banned_patterns"), sentence)
                    if raw is not None:
                        topic = word
                        break
                topic = topic or (_effect_claim(sentence, "ko") or _effect_claim(sentence, "en") or (None,))[0]
                if topic:
                    holds.append(Hold("QG4-HEALTH", 4, lang, f"{label}: 상담을 부정하는 문장에 건강 낱말 — '{_safe(topic, 30)}'(상담 안내 문장이 아니다)"))
                    break
    for paragraph in re.split(r"\n\s*\n|\n", prose):
        topic = _profile_topic(profiles, paragraph)
        assertion = _HEALTH_ASSERT.search(paragraph)
        if topic and assertion:
            holds.append(Hold("QG4-ASSERT", 4, lang, f"{label}: 건강 신호('{_safe(topic, 20)}')와 단정 표현('{_safe(assertion.group(0), 20)}')이 함께 있음"))
            break
    claim = _claim_lang_hit(prose)
    where = "본문"
    if claim is None:
        claim, where = _claim_lang_hit(title), "제목"
    if claim is not None:
        holds.append(Hold("QG4-CLAIM", 4, lang, f"{label}: {where}에 증상('{_safe(claim[0], 15)}')을 즉각·단정('{_safe(claim[1], 15)}')으로 해결한다는 효과 표현('{_safe(claim[2], 15)}')"))
    else:
        for sentence in re.split(r"[.!?。！？\n]+", both):
            found = _PRODUCT_CURE.search(sentence)
            if found and not _CURE_GUARD.search(sentence) and _profile_topic(profiles, sentence):
                holds.append(Hold("QG4-CLAIM", 4, lang, f"{label}: 질환·증상을 이 제품·방법으로 낫게 한다는 효능 단정 — '{_safe(found.group(0), 40)}'(상담 문구가 있어도 면제 없음)"))
                break
    for profile in profiles:
        raw, word = gates.first_match(profile.get("banned_topic_patterns"), title)
        if raw is not None:
            holds.append(Hold("QG4-TITLE", 4, lang, f"{label}: 제목에 건강·금지 주제 낱말 — '{_safe(word, 30)}'"))
            break
    return holds


_EVENT_TERMS = re.compile(
    r"행사|개최|참가|참석|일정|등록|신청|접수|컨퍼런스|콘퍼런스|세미나|웨비나|박람회|포럼|설명회|개막|폐막|초청|발표회|전시회|시상식|공모전|워크숍|워크샵|심포지엄|서밋|"
    r"\b(?:events?|conferences?|webinars?|workshops?|summits?|symposium|forums?|expos?|exhibitions?|agenda|register|registration|rsvp|save\s+the\s+date|will\s+host|"
    r"will\s+be\s+held|takes?\s+place|join\s+us|sign\s+up|deadline|ceremony|keynote|panel|roundtable|attendees?|speakers?)\b", re.I)
_EVENT_TITLE = re.compile(r"행사|개최|참가|컨퍼런스|웨비나|세미나|설명회|\b(?:summit|conference|webinar|workshop|registration|save\s+the\s+date)\b", re.I)


def event_signals(title, prose):
    """(신호 수, 서로 다른 신호 수, 본문 1,000자당 밀도). 제목의 행사 낱말은 신호 3개로 센다."""
    prose = _text(prose)
    hits = [m.group(0).casefold() for m in _EVENT_TERMS.finditer(prose)]
    bonus = 3 if _EVENT_TITLE.search(_text(title)) else 0
    length = max(len(re.sub(r"\s+", "", prose)), 1)
    return len(hits) + bonus, len(set(hits)) + (1 if bonus else 0), (len(hits) + bonus) * 1000.0 / length


def rule_event(lang, title, prose):
    """QG5 행사 안내: 신호 밀도가 높고 서로 다른 신호가 여럿이면 보류."""
    total, distinct, density = event_signals(title, prose)
    if density >= EVENT_DENSITY_HOLD[lang] and distinct >= EVENT_DISTINCT_HOLD:
        return [Hold("QG5-EVENT", 5, lang, f"{LANG_LABEL[lang]}: 행사 안내 신호가 많음(신호 {total}개·서로 다른 낱말 {distinct}개·1,000자당 {density:.1f}개)")]
    return []


def _domain_in(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def rule_company(domain, public_domains):
    """QG5 회사 발표: 출처 도메인이 공공·연구·국제기구 목록 밖이면 보류(도메인을 모르면 보류). 자동화 제외 도메인(EXCLUDED_SOURCE_DOMAINS)은 허용 목록에 있어도 보류한다."""
    host = (domain or "").lower().rstrip(".")
    if host and _domain_in(host, EXCLUDED_SOURCE_DOMAINS):
        return [Hold("QG5-COMPANY", 5, "post", f"자동화에서 제외한 출처 도메인 — {_safe(host, 60)}")]
    if host and _domain_in(host, public_domains):
        return []
    return [Hold("QG5-COMPANY", 5, "post", f"출처 도메인이 공공·연구기관 목록 밖이거나 알 수 없음 — {_safe(host or '(없음)', 60)}")]


# 제목이 약속하는 내용(약속어) → 본문에 있어야 하는 낱말. 제목에 약속어가 있는데 본문에 그 낱말이 하나도 없으면 약속을 못 지킨 제목이다(예: 제목은 '추이'인데 본문에 추이가 없다).
_PROMISES = (
    ("추이", ("추이", "동향", "트렌드", "시계열", "trend")),
    ("동향", ("동향", "추이", "트렌드", "trend")),
    ("전망", ("전망", "예상", "예측", "forecast", "outlook", "projection", "predict")),
    ("순위", ("순위", "1위", "2위", "3위", "상위", "하위", "rank")),
    ("비교", ("비교", "대비", "견주", "compar")),
    ("원인", ("원인", "때문", "이유", "cause", "because", "reason")),
    ("이유", ("이유", "때문", "원인", "reason", "because", "cause")),
    ("급증", ("급증", "크게 늘", "급격", "surge", "sharp")),
    ("급감", ("급감", "크게 줄", "급격", "plunge", "sharp")),
    ("최초", ("최초", "처음", "first")),
    ("역대", ("역대", "사상", "기록", "record", "highest", "lowest")),
    ("trend", ("trend", "추이", "동향")),
    ("forecast", ("forecast", "outlook", "projection", "전망", "예상")),
    ("outlook", ("outlook", "forecast", "projection", "전망", "예상")),
    ("ranking", ("rank", "순위")),
    ("record", ("record", "highest", "lowest", "역대", "사상", "기록")),
    ("surge", ("surge", "sharp", "급증")),
    ("first", ("first", "최초", "처음")),
)
_TITLE_ACRONYM = re.compile(r"\b[A-Z]{3,}[A-Za-z0-9]*\b")


def rule_title(lang, title, prose):
    """QG6 제목·본문 일치: 제목의 숫자와 약속어, 영문 약어(NASA·FTC)가 본문에 있어야 한다."""
    label = LANG_LABEL[lang]
    holds = []
    body = _fold(prose)
    body_fold = body.casefold()
    title_figures = extract_figures(title or "", strict=True)
    body_figures = extract_figures(prose, strict=True)
    body_values = {n.value for n in body_figures.nums} | {n.base for n in body_figures.nums}
    body_years = {Decimal(d.y) for d in body_figures.dates if d.y is not None}
    missing = []
    for num in title_figures.nums:
        if num.kind == "year":
            if num.value not in body_values and num.value not in body_years:
                missing.append(num.raw)
        elif num.value not in body_values:
            missing.append(num.raw)
    for date in title_figures.dates:
        if not any(((date.y is None or known.y == date.y) and (date.m is None or known.m == date.m) and (date.d is None or known.d == date.d))
                   for known in body_figures.dates) and not (date.m is None and date.d is None and date.y is not None and Decimal(date.y) in body_values):
            missing.append(date.raw)
    if missing:
        holds.append(Hold("QG6-TITLE-NUMBER", 6, lang, f"{label}: 제목의 숫자·날짜가 본문에 없음 — {_shorten(missing)}"))
    words = []
    title_fold = _fold(title or "").casefold()
    for promise, accepted in _PROMISES:
        if promise in title_fold and not any(a in body_fold for a in accepted):
            words.append(promise)
    for acronym in dict.fromkeys(_TITLE_ACRONYM.findall(_fold(title or ""))):
        if acronym.casefold() not in body_fold:
            words.append(acronym)
    if words:
        holds.append(Hold("QG6-TITLE-WORD", 6, lang, f"{label}: 제목의 핵심어가 본문에 없음 — {_shorten(words)}"))
    return holds


# 추적용 질의 매개변수(이름이 정확히 같거나 접두사). `ref` 로 시작하는 이름을 통째로 지우면 `?reference=abc` 와 `?reference=xyz` 가 같은 글이 되므로 알려진 이름 목록만 쓴다.
_TRACKING_EXACT = frozenset({"fbclid", "gclid", "dclid", "msclkid", "yclid", "igshid", "mc_cid", "mc_eid", "ixid", "ref", "ref_src", "ref_url", "_hsenc", "_hsmi",
                             "mkt_tok", "s_cid", "wt.mc_id", "oly_enc_id", "oly_anon_id", "vero_id", "__s", "spm"})
_TRACKING_PREFIXES = ("utm_",)
_INDEX_PAGE = re.compile(r"/index\.(?:html?|php)$", re.I)


def normalize_url(url):
    """원문 주소를 견주기 좋게 고른다: 소문자 주소·www·amp. 제거·조각 제거·추적 매개변수(알려진 이름만) 제거·%XX 풀기·끝 슬래시와 index.html 제거·질의 정렬. 계정 정보와 기본(80·443)이 아닌 포트는 남긴다.
    못 읽으면 빈 문자열."""
    text = str(url or "").strip()
    try:
        parts = urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return ""
    host = (parts.hostname or "").lower().rstrip(".")
    for prefix in ("www.", "amp."):
        host = host[len(prefix):] if host.startswith(prefix) else host
    try:
        port = parts.port
    except ValueError:                                              # 숫자가 아니거나 범위를 벗어난 포트는 읽을 수 없는 주소다
        return ""
    userinfo = parts.netloc.rpartition("@")[0] if "@" in parts.netloc else ""
    host = (f"{userinfo}@" if userinfo else "") + host + (f":{port}" if port not in (None, 80, 443) else "")      # 계정·기본이 아닌 포트가 다르면 다른 주소다
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_EXACT and not k.lower().startswith(_TRACKING_PREFIXES))
    path = _INDEX_PAGE.sub("", unquote(parts.path)).rstrip("/") or ""
    return f"{host}{path}" + ("?" + "&".join(f"{k}={v}" for k, v in query) if query else "")


def rule_reuse(link, history):
    """QG7 같은 원문 재사용: 이력에 같은 출처 주소(source_url)가 이미 있으면 보류."""
    wanted = normalize_url(link)
    if not wanted:
        return []
    for entry in history or ():
        if isinstance(entry, dict) and normalize_url(entry.get("source_url")) == wanted:
            return [Hold("QG7-REUSE", 7, "post", "이력에 같은 출처 주소로 만든 글이 이미 있음")]
    return []


_LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+]|\d{1,3}[.)])[ \t]+")
_HEADING_ITEM = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+")


def structure_counts(story):
    """(소제목 수, 문단 수, 불릿 수). 문단은 빈 줄로 나뉜 덩어리 가운데 소제목·목록·표·이미지가 아닌 것."""
    headings = bullets = paragraphs = 0
    for block in re.split(r"\n\s*\n", story or ""):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        plain = False
        for line in lines:
            if _HEADING_ITEM.match(line):
                headings += 1
            elif _LIST_ITEM.match(line):
                bullets += 1
            elif line.lstrip().startswith(("|", "![", ">", "---", "***", "___")):
                continue
            else:
                plain = True
        if plain:
            paragraphs += 1
    return headings, paragraphs, bullets


def number_overlap(prose_a, prose_b):
    """두 글이 가진 숫자(값)·날짜의 자카드 겹침. 둘 다 숫자가 없으면 None."""
    def keys(text):
        figures = extract_figures(text, strict=True)
        return ({("n", n.value) for n in figures.nums} | {("d", d.y, d.m, d.d) for d in figures.dates})
    first, second = keys(prose_a), keys(prose_b)
    union = first | second
    return (len(first & second) / len(union)) if union else None


def rule_clone(story_ko, story_en, prose_ko, prose_en):
    """QG8 번역 복제. 구조 세 칸(소제목·문단·불릿 수) 가운데 어느 한쪽에라도 있는 칸만 '정보가 있는 칸'으로 센다(둘 다 0 인 칸은 우연히 같을 뿐이라 센 것으로 치지 않는다).
    정보가 있는 칸이 둘 이상이고 모두 같으면 복제, 하나만 어긋나고 숫자 겹침이 높거나 비교할 숫자가 없으면 복제다(감사 22쌍으로 보정 — docs/QUALITY_GATE.md)."""
    a, b = structure_counts(story_ko), structure_counts(story_en)
    dims = [i for i in range(3) if a[i] or b[i]]
    matched = [i for i in dims if a[i] == b[i]]
    overlap = number_overlap(prose_ko, prose_en)
    is_clone = len(dims) >= 2 and (len(matched) == len(dims) or (len(matched) == len(dims) - 1 and (overlap is None or overlap >= CLONE_NUMBER_OVERLAP)))
    detail = {"structure_same": len(matched), "structure_dims": len(dims), "number_overlap": None if overlap is None else round(overlap, 2), "ko": list(a), "en": list(b)}
    if not is_clone:
        return [], detail
    shown = "숫자 겹침 없음" if overlap is None else f"숫자 겹침 {overlap:.2f}"
    return [Hold("QG8-CLONE", 8, "pair", f"국문·영문이 번역 복제로 보임 — 구조 {len(matched)}/{len(dims)}칸 일치(소제목·문단·불릿 수 국문 {a}·영문 {b}), {shown}")], detail


# ----------------------------------------------------------------------------
# 공개 진입점
# ----------------------------------------------------------------------------
def _content_of(data, lang):
    prefix = PREFIX[lang]
    content, title = data.get(f"{prefix}_content"), data.get(f"{prefix}_title")
    return (content if isinstance(content, str) else ""), (title if isinstance(title, str) else "")


def check_candidate(data, source, history=(), config=None, as_of=None):
    """후보 글 한 건(검증을 통과한 data: kr_*·en_* 키)을 규칙 8가지로 평가해 GateReport 를 돌려준다. 보류 사유가 하나라도 있으면 보류다.
    source: 후보 기사 항목(title·source·link·publisher_domain·summary·published). history: 이력 항목 목록. as_of: 오늘 날짜(글이 오늘 날짜를 적을 수 있다)."""
    if config is None:
        raise GateConfigError("Gate 설정(config)이 필요합니다.")
    report = GateReport()
    evidence = evidence_text(source)
    ref = source_ref(source)
    report.facts["source_text_chars"] = evidence.summary_chars
    report.facts["evidence_chars"] = len(evidence.text)
    if not evidence.text.strip():
        report.holds.append(Hold("QG0-NO-SOURCE", 0, "post", "모델에 준 근거 텍스트를 알 수 없어 숫자·인용을 확인할 수 없음"))
    if not isinstance(data, dict):
        report.holds.append(Hold("QG0-INPUT", 0, "post", "후보 글 데이터가 올바르지 않음"))
        return report
    stories, proses, titles = {}, {}, {}
    for lang in config.languages:
        content, data_title = _content_of(data, lang)
        if len(content) > MAX_BODY_CHARS:         # 정규식을 돌리기 전에 먼저 거른다 — 상한이 시간 방어를 겸한다
            stories[lang], proses[lang], titles[lang] = "", "", []
            report.holds.append(Hold("QG0-INPUT", 0, lang, f"{LANG_LABEL[lang]}: 글이 너무 김({len(content):,}자, 상한 {MAX_BODY_CHARS:,}자)"))
            continue
        front, body = split_front(content)
        titles[lang] = [t for t in dict.fromkeys([front_title(front)[:300], data_title[:300]]) if t]
        parts = split_story(body)
        stories[lang] = parts.story
        proses[lang] = prose_of(scan_text_of(parts))
        if not body.strip():
            report.holds.append(Hold("QG0-INPUT", 0, lang, f"{LANG_LABEL[lang]}: 글이 비었음"))
            continue
        report.facts[f"body_chars_{lang}"] = readable_length(stories[lang])
        report.holds += rule_link_and_length(lang, stories[lang], proses[lang], ref.link, config.minimum(lang))
        if evidence.text.strip():
            report.holds += rule_numbers(lang, proses[lang], evidence.text, as_of)
            report.holds += rule_quotes(lang, proses[lang], evidence.text)
        hidden = hidden_health_text(body)                              # 이미지 대체글·HTML 속성·링크 글자 속 단정도 건강 규칙이 읽는다
        report.holds += rule_health(lang, " ".join(titles[lang]), proses[lang] + ("\n" + hidden if hidden else ""), config.health_profiles)
        report.holds += rule_event(lang, " ".join(titles[lang]), proses[lang])
        for title in titles[lang]:
            report.holds += rule_title(lang, title, proses[lang])
    report.holds += rule_company(ref.domain, config.public_domains)
    report.holds += rule_reuse(ref.link, history)
    if stories.get("ko") is not None and stories.get("en") is not None:       # 국문 전용이면 영문 글을 모으지 않으므로(위 반복) 이 규칙은 쌍일 때만 돈다
        clone, detail = rule_clone(stories["ko"], stories["en"], proses["ko"], proses["en"])
        report.holds += clone
        report.facts["clone"] = detail
    # 같은 사유가 두 제목(머리말 제목·JSON 제목)에서 겹쳐 나오면 한 번만 적는다
    unique, seen = [], set()
    for hold in report.holds:
        key = (hold.code, hold.lang, hold.message)
        if key not in seen:
            seen.add(key)
            unique.append(hold)
    report.holds = unique
    return report
