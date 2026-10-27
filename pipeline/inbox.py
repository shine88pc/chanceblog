"""확인 필요 모음(운영 인박스) 규칙 — 순수 함수(I/O 없음: 네트워크 없이 테스트한다).

운영자가 해야 할 일·확인할 일을 한 목록으로 모은다. 입력은 Snapshot(열린 이슈·PR과 CI 상태, 워크플로 실행, 실행 주석,
환경 플래그, 블로그 레지스트리·이력, 조회 실패 기록), 출력은 Item 목록과 마크다운이다.
GitHub 읽기·쓰기와 이슈 관리는 scripts/ops_inbox.py 가 맡는다. 설명서: docs/OPS_INBOX.md

수준(level)
  action  지금 해야 할 일 — 사람이 손대야 풀린다(병합·승인·시크릿 등록·실패 원인 확인). 새로 생기면 코멘트(@멘션)로 알린다.
  check   확인하면 좋은 것 — 급하지 않거나 사실 확인이 필요한 것(경고·조회 실패·오래된 PR). 알림은 가지 않는다.
  info    참고 — 현황(블로그별 마지막 글 등)과 진행 중인 것.

초안 현황(2026-10-27, 작업요청서 5 PR-B): 채널별로 발행을 기다리는 초안을 한 표로 보여 준다. 초안 모델 — 초안 1건 = 이슈 1개 또는 PR 1개,
라벨 `초안` + `채널:<채널 라벨>`(채널 라벨은 레지스트리 channel.label), 쓰지 않을 초안은 라벨 `폐기` 또는 닫기. 열린 초안 이슈가 새로 생기면
action(코멘트 알림), 3일 넘게 열려 있으면 check. Blogger 는 이력의 draft_uploaded 를 센 대략치다(공개 여부는 Blogger 쪽 사실).
표는 항목(Item)이 아니라 render() 의 board 인자로 본문 위쪽에 들어간다.

보안: 외부에서 온 텍스트(PR 제목·주석 문구·이슈 제목·이력 사유)는 ext() 로 한 줄로 접고, 비밀 값 모양을 가리고, '@'·'<'·'&' 를
전각으로 바꾸고, 링크 문법 문자를 바꾸고, '::'·'##[' 를 풀어 쓴다. 렌더러는 한 번 더 같은 안전망(safe_text)을 거친다.
링크는 숫자 id 로 직접 만들며 API 가 준 URL 은 쓰지 않는다. 이 이슈는 공개 저장소의 공개 이슈이므로 수익·방문 수치와
비밀 값은 싣지 않는다(docs/SECURITY_GUARDRAILS.md G-O7).
"""
import hashlib
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from pipeline.console import one_line
from pipeline.llm import mask
from pipeline.state import KST

# ----------------------------------------------------------------------------
# 상수(기본값). 규칙의 근거와 한계는 docs/OPS_INBOX.md
# ----------------------------------------------------------------------------
ISSUE_TITLE = "[운영] 확인 필요 모음"      # 워치독 이슈 접두 '[Watchdog]' 와 겹치지 않는다
LABEL = "ops-inbox"
LABEL_COLOR = "fbca04"
LABEL_DESCRIPTION = "운영 확인 필요 모음(자동 관리)"
OWN_WORKFLOW = "ops-inbox.yml"            # 이 모음을 만드는 워크플로(자기 자신의 실행은 점검하지 않는다)
BOT_LOGIN = "github-actions[bot]"
WATCHDOG_PREFIX = "[Watchdog]"
TRUSTED_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")

LEVEL_ACTION, LEVEL_CHECK, LEVEL_INFO = "action", "check", "info"
LEVELS = (LEVEL_ACTION, LEVEL_CHECK, LEVEL_INFO)
SECTION_TITLES = {LEVEL_ACTION: "지금 해야 할 일", LEVEL_CHECK: "확인하면 좋은 것", LEVEL_INFO: "참고"}

RUN_WINDOW_HOURS = 48          # 워크플로 실행은 최근 48시간만 본다
RUNS_PER_FILE = 10             # 워크플로 파일마다 최근 10건
ANNOTATION_RUNS_PER_FILE = 3   # 경고(주석)는 파일마다 최근 성공 실행 3건까지만 읽는다(API 호출 절약)
PR_STALE_DAYS = 3              # 이보다 오래 열린 PR 은 수준을 check 이상으로 올린다
DRAFT_WAIT_DAYS = 7            # Blogger 초안함에 올라간 글은 7일 안의 것만 '게시 대기'로 센다
APPROVAL_ITEMS_MAX = 5
WARNING_MESSAGES_MAX = 3       # 워크플로 하나의 경고 문구는 서로 다른 것 3개까지만 나열한다
BODY_LIMIT = 58000             # 보이는 본문은 이 길이까지만. 뒤에 붙는 표식(알린 id 80개 × 80자 + 구분자 ≈ 6,530자)을 더해도 GitHub 이슈 본문 한도(65,536자) 안이다
SUMMARY_LIMIT = 500000         # 실행 요약은 사실상 자르지 않는다(같은 마크다운)
COMMENT_ITEMS_MAX = 8
MARKER_IDS_MAX = 80

# 초안 모델(docs/OPS_INBOX.md §3-1): 초안 1건 = 이슈 1개 또는 PR 1개. 라벨 `초안`(대기) + `채널:<채널 라벨>`(어느 채널의 글인가), 쓰지 않을 초안은
# 라벨 `폐기` 또는 닫기(닫기 = 발행 완료 또는 폐기). 라벨이 저장소에 없으면 scripts/ops_inbox.py 가 만든다(이름·색·설명은 아래 값으로 고정).
DRAFT_LABEL = "초안"
DISCARD_LABEL = "폐기"
CHANNEL_LABEL_PREFIX = "채널:"
CHANNEL_LABEL_COLOR = "bfdadc"
DRAFT_LABEL_SPECS = (       # (라벨 이름, 색, 설명)
    (DRAFT_LABEL, "c2e0c6", "발행 대기 초안(확인 필요 모음의 초안 현황이 센다)"),
    (DISCARD_LABEL, "cfd3d7", "쓰지 않기로 한 초안(초안 현황에서 빠진다)"),
)
LABEL_NAME_MAX = 50            # GitHub 라벨 이름 길이 한도
DRAFT_STALE_DAYS = 3           # 이보다 오래 열려 있는 초안은 action 에서 check 로 내린다(PR_STALE_DAYS 와 같은 값)
DRAFT_WINDOW_DAYS = 14         # 초안 현황의 Blogger 칸은 초안함 업로드 기록 중 이 기간 안의 것만 센다(게시 여부는 Blogger 쪽 사실이라 모른다)
BOARD_ROWS_MAX = 12            # 초안 현황 표의 최대 줄 수(레지스트리 채널 + 레지스트리에 없는 채널의 초안)
BOARD_TITLE_MAX = 24           # 표 안의 글 제목 길이
DRAFT_TITLE_MAX = 80           # 항목 제목 안의 글 제목 길이

TITLE_MAX, DETAIL_MAX, HINT_MAX, MESSAGE_MAX = 110, 420, 260, 150

PUBLISH_STAGE = ("posted", "draft", "generated_unpublished", "publish_failed", "draft_uploaded")
IGNORED_CONCLUSIONS = ("cancelled", "skipped", "neutral", "stale", "action_required")     # 최근 완료 실행을 고를 때 건너뛴다(승인 대기는 성공도 실패도 아니다)
PULL_EVENTS = ("pull_request", "pull_request_target")     # 이 이벤트의 실행은 head 저장소가 이 저장소일 때만 센다(포크 PR 의 head 브랜치가 main 이어도 섞이지 않게)
FAILED_CONCLUSIONS = ("failure", "timed_out", "startup_failure")
_CONCLUSION_LABELS = {"failure": "실패", "timed_out": "시간 초과", "startup_failure": "시작 실패"}
_CI_LABELS = {"pass": "통과", "fail": "실패", "pending": "진행 중", "none": "기록 없음", "unknown": "알 수 없음"}

# 조회 실패 기록의 소스 이름 → 화면 문구 / 그 소스가 만드는 action 항목 id 접두(조회 실패 때 '해소된 것'으로 오해하지 않으려고 쓴다)
SOURCE_LABELS = {
    "issues": "열린 이슈 목록", "pulls": "열린 PR 목록", "pull_details": "PR 검사·병합 상태",
    "runs": "워크플로 실행 기록", "approvals": "승인 대기 실행", "annotations": "실행 경고(주석)",
    "history": "블로그 이력 파일", "registry": "블로그 레지스트리", "drafts": "열린 초안(이슈·PR) 목록",
}
SOURCE_PREFIXES = {
    "issues": ("watchdog:",), "pulls": ("pr:",), "pull_details": ("pr:",), "runs": ("run:",),
    "approvals": ("approve:",), "history": ("blogger:",), "registry": ("blogger:",), "drafts": ("draft:",),
}

# 플랫폼(GitHub)이 거의 모든 실행에 붙이는 안내성 주석 — 우리 스크립트가 남긴 것이 아니라서 check 로 올리지 않고 '참고' 한 줄로 합친다.
# 실제 문구(2026-10-25 모든 실행): warning "Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to
# run on Node.js 24: actions/checkout@v4, actions/setup-python@v5 …" / notice "The ubuntu-latest label will migrate to Ubuntu 26
# beginning October 19, 2026 …". 새 종류가 소음으로 보이면 여기에 정규식을 더하고 tests/test_ops_inbox.py 의 PlatformNoticeTest 에 그 문구를 넣는다.
PLATFORM_NOISE = (
    re.compile(r"(?i)\bnode\.js\s*\d+\b"),                      # Node.js 20 is deprecated … forced to run on Node.js 24 ('Node 18' 처럼 .js 가 없는 우리 쪽 문구는 소음이 아니다)
    re.compile(r"(?i)\bwill migrate\b"),                        # The ubuntu-latest label will migrate to Ubuntu 26 …
    re.compile(r"github\.blog/changelog/"),                     # GitHub 공지(changelog) 링크
    re.compile(r"actions/runner-images"),                       # 러너 이미지 공지 링크
    re.compile(r"(?i)\b(?:set-output|save-state|set-env|add-path)\b.*\bdeprecat"),
    # 지원 종료 예고(deprecated)는 플랫폼 용어(액션·러너·ubuntu·Node)가 함께 있을 때만 — 우리 코드의 deprecated 경고(예: 모델 이름)는 남긴다
    re.compile(r"(?is)(?=.*\bdeprecat)(?=.*(?:\bactions?/|\brunner|\bubuntu|\bnode\b|github actions))"),
)
PLATFORM_LEVELS = ("warning", "notice")      # 이 수준의 플랫폼 문구만 모은다(우리 쪽 notice 는 무시)

EMPTY_TEXT = "지금 확인할 것이 없습니다. 새로 해야 할 일이 생기면 이 이슈에 코멘트로 알려 드립니다."

_ID_RE = re.compile(r"^[a-z0-9_.:]{1,80}$")
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_ROLE_RE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/(?!\.+$)[A-Za-z0-9._-]{1,100}$")
_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_SEVERITY_RE = re.compile(r"심각도[\s*:：]*(critical|warning)", re.IGNORECASE)
_TRUE = ("1", "true", "yes", "on")


# ----------------------------------------------------------------------------
# 외부 텍스트 무력화
# ----------------------------------------------------------------------------
_NO_LIMIT = 10 ** 9      # one_line 에 '자르지 않음'을 알리는 큰 수
# 글자 순서를 뒤집어 속이는 제어 문자(U+200E·U+200F·U+202A~U+202E·U+2066~U+2069). 소스에 보이지 않는 문자를 넣지 않으려고 코드 포인트로 쓴다.
_BIDI_CODEPOINTS = (0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A))
_BIDI_RE = re.compile("[" + "".join(chr(c) for c in _BIDI_CODEPOINTS) + "]")
# 알림·HTML·링크 문법을 무력화하는 전각 문자(보이는 모양은 거의 같다): ＠ U+FF20, ＜ U+FF1C, ＆ U+FF06, ［ U+FF3B, ］ U+FF3D
_SAFE_MAP = str.maketrans({"@": chr(0xFF20), "<": chr(0xFF1C), "&": chr(0xFF06)})
_EXT_MAP = str.maketrans({"[": chr(0xFF3B), "]": chr(0xFF3D), "`": "'"})


def _clip(text, limit):
    if limit is None or len(text) <= limit:
        return text
    return text[:max(limit - 1, 0)].rstrip() + "…"


def fold(text, limit=300):
    """외부 유래 문자열을 로그에 넣을 한 줄로 접는다(길이는 limit 이하, 줄이면 끝에 '…'). limit=None 이면 자르지 않는다.

    pipeline.console.one_line 을 쓴다: 줄을 바꾸는 모든 문자(개행·단독 CR·U+2028·U+2029·U+0085·탭)와 그 밖의 제어 문자는 공백으로,
    연속 공백은 하나로 줄이고, 워크플로 명령 표기 '::' 와 로그 서식 표기 '##[' 는 어디에 있든 풀어 쓴다(러너는 줄 맨 앞 '::' 를
    명령으로 읽는다). 여기에 더해 글자 순서를 뒤집어 속이는 제어 문자(bidi)를 지운다."""
    return one_line(_BIDI_RE.sub("", "" if text is None else str(text)), _NO_LIMIT if limit is None else limit)


def safe_text(text, limit=300):
    """GitHub(이슈·코멘트·실행 요약)에 인용해도 알림·HTML 주석·명령이 되지 않는 한 줄 텍스트.

    '@' 는 전각 '＠' 로 바꿔 다른 사람에게 멘션 알림이 가지 않게 하고(문자 참조 '&#64;' 도 멘션이 되므로 '&' 도 전각으로),
    '<' 는 전각 '＜' 로 바꿔 HTML 태그·주석(표식 위조)을 막는다. 멘션과 표식은 이 모듈이 직접 붙인다."""
    return _clip(fold(text, None).translate(_SAFE_MAP), limit)


def ext(text, limit=120):
    """외부에서 온 값을 항목에 넣을 때 쓴다: 비밀 값 모양을 가리고, safe_text 에 더해 링크 문법([ ])과 코드 스팬(`)을 무력화한다."""
    raw = "" if text is None else mask(str(text))
    return _clip(safe_text(raw, None).translate(_EXT_MAP), limit)


_URL_RE = re.compile(r"^https://(?:github\.com|www\.blogger\.com)/[A-Za-z0-9._~:/?#@!$*+,;=%\-]*$")


def safe_url(url):
    """github.com·blogger.com 의 단순한 https 주소만 링크로 쓴다(공백·괄호·꺾쇠 따위가 있으면 링크를 만들지 않는다)."""
    text = str(url or "")
    return text if _URL_RE.fullmatch(text) else ""


def is_truthy(value):
    return str(value or "").strip().lower() in _TRUE


def is_valid_repo(repo):
    """'소유자/저장소' 형식인가(링크를 만드는 데 쓰므로 '..' 같은 값은 거른다)."""
    return bool(_REPO_RE.fullmatch(str(repo or "")))


def _as_int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _slug(text, limit=48):
    return re.sub(r"[^a-z0-9_.]+", "_", str(text).lower()).strip("_")[:limit] or "x"


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_time(value):
    """GitHub·이력의 ISO-8601 시각 → UTC aware datetime. 읽을 수 없으면 None('Z' 는 Python 3.10 도 읽도록 바꿔서 해석)."""
    if isinstance(value, datetime):
        return _aware(value)
    if not isinstance(value, str) or len(value.strip()) <= 10:      # 날짜만 있는 값은 시각이 아니다
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return _aware(datetime.fromisoformat(text))
    except ValueError:
        return None


def fmt_kst(moment):
    return moment.astimezone(KST).strftime("%Y-%m-%d %H:%M") + " KST"


# ----------------------------------------------------------------------------
# 항목·입력
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Item:
    """운영 인박스의 한 줄. id 는 같은 사실이면 항상 같아야 한다(새 알림 판정·표식에 쓴다): 소문자·숫자·_ . : 만 허용."""
    id: str
    level: str
    title: str
    detail: str = ""
    url: str = ""
    hint: str = ""
    since: Optional[datetime] = None

    def __post_init__(self):
        if self.level not in LEVELS:
            raise ValueError(f"알 수 없는 수준: {self.level!r}")
        if not _ID_RE.fullmatch(self.id):
            raise ValueError(f"항목 id 형식이 올바르지 않습니다: {self.id!r}")


@dataclass
class Snapshot:
    """한 번의 점검에서 읽은 사실 전부(규칙의 유일한 입력). 모든 필드는 비어 있어도 된다."""
    now: datetime
    repo: str                                               # "소유자/저장소"
    issues: list = field(default_factory=list)              # 열린 이슈(GitHub 이슈 객체 — 필요한 필드만 읽는다)
    pulls: list = field(default_factory=list)               # normalize_pull() 이 만든 열린 PR
    runs: dict = field(default_factory=dict)                # 워크플로 파일 이름 → 최근 실행 목록(GitHub 실행 객체)
    approvals: list = field(default_factory=list)           # 승인 대기(action_required) 실행
    annotations: dict = field(default_factory=dict)         # 실행 id(int) → 주석 목록(GitHub 주석 객체)
    paused: bool = False                                    # PIPELINE_PAUSE
    blogs: list = field(default_factory=list)               # 레지스트리 블로그(기본값 병합본)
    histories: dict = field(default_factory=dict)           # 블로그 key → 이력 목록
    failures: list = field(default_factory=list)            # [(소스 이름, 사유)] 조회 실패
    notes: list = field(default_factory=list)               # [(id, 문구)] 참고 안내(예: 일부만 확인함)
    workflow_names: dict = field(default_factory=dict)      # 워크플로 파일 이름 → 그 파일의 최상위 name(체크아웃한 파일에서 읽음). 실행(run)의 name 은 run-name 이라 쓰지 않는다
    drafts: list = field(default_factory=list)              # normalize_draft() 가 만든 열린 `초안` 이슈·PR(라벨 초안이 붙은 것). 읽지 못했으면 failures 에 ('drafts', 사유)


# ----------------------------------------------------------------------------
# 규칙 1: 워치독 이슈
# ----------------------------------------------------------------------------
def trusted_author(issue):
    """이슈 작성자가 github-actions 봇이거나 저장소 소유자·멤버·협업자인가(낯선 사람이 같은 제목으로 위장하는 것을 막는다)."""
    login = str((issue.get("user") or {}).get("login") or "")
    return login == BOT_LOGIN or str(issue.get("author_association") or "") in TRUSTED_ASSOCIATIONS


def _watchdog_message(body):
    """워치독 이슈 본문의 '문제 설명' 문단(심각도 줄 바로 다음 문단). 없으면 빈 문자열."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", str(body or "").replace("\r\n", "\n").replace("\r", "\n")) if p.strip()]
    for index, paragraph in enumerate(paragraphs):
        if "심각도" in paragraph:
            return paragraphs[index + 1] if index + 1 < len(paragraphs) else ""
    return ""


def watchdog_items(issues, repo_url):
    """열린 `[Watchdog] …` 이슈 → 심각(critical)=action, 경고(warning)=check. 심각도를 읽지 못하면 action(놓치는 쪽이 더 위험하다).
    제목만 같은 낯선 사람의 이슈는 걸러낸다(작성자가 github-actions 봇이거나 저장소 소유자·멤버·협업자일 때만)."""
    out = []
    for issue in issues:
        if not isinstance(issue, dict) or "pull_request" in issue:
            continue
        title = str(issue.get("title") or "")
        number = _as_int(issue.get("number"))
        if not title.startswith(WATCHDOG_PREFIX) or number is None or not trusted_author(issue):
            continue
        match = _SEVERITY_RE.search(str(issue.get("body") or ""))
        severity = match.group(1).lower() if match else "critical"
        warning = severity == "warning"
        message = ext(_watchdog_message(issue.get("body")), 220) or "이슈 본문을 확인하세요."
        detail = f"{'경고' if warning else '심각'} · {message}"
        out.append(Item(
            id=f"watchdog:{number}", level=LEVEL_CHECK if warning else LEVEL_ACTION,
            title=f"워치독 알림 — {ext(title[len(WATCHDOG_PREFIX):].strip(), 80)}",
            detail=detail, url=f"{repo_url}/issues/{number}", since=parse_time(issue.get("created_at")),
            hint="이슈를 열어 내용을 확인하세요. 문제가 해소되면 워치독이 이슈를 자동으로 닫고 이 목록에서도 사라집니다."))
    return out


# ----------------------------------------------------------------------------
# 규칙 2: 열린 PR
# ----------------------------------------------------------------------------
def summarize_checks(check_runs):
    """헤드 커밋의 check-runs → 'pass' | 'fail' | 'pending' | 'none'.
    실패가 하나라도 있으면 fail, 끝나지 않은 것이 있으면 pending, 끝난 것 중 성공이 있고 실패가 없으면 pass.
    취소·오래됨만 있으면 none(기록 없음). 건너뜀·중립은 통과로 본다."""
    runs = [c for c in (check_runs or []) if isinstance(c, dict)]
    if not runs:
        return "none"
    conclusions = [c.get("conclusion") for c in runs]
    if any(x in FAILED_CONCLUSIONS for x in conclusions):
        return "fail"
    if any(c.get("status") != "completed" or x in (None, "action_required") for c, x in zip(runs, conclusions)):
        return "pending"
    return "pass" if "success" in conclusions else "none"


def normalize_pull(raw, detail=None, check_runs=None, error=""):
    """GitHub 응답(목록의 PR 하나·상세·헤드 커밋의 check-runs)을 규칙이 읽는 평평한 dict 로 바꾼다."""
    raw = raw if isinstance(raw, dict) else {}
    detail = detail if isinstance(detail, dict) else {}
    head = raw.get("head") if isinstance(raw.get("head"), dict) else {}
    base = raw.get("base") if isinstance(raw.get("base"), dict) else {}
    head_repo = head.get("repo") if isinstance(head.get("repo"), dict) else None
    base_repo = base.get("repo") if isinstance(base.get("repo"), dict) else None
    fork = head_repo is None or (base_repo is not None and head_repo.get("full_name") != base_repo.get("full_name"))
    user = raw.get("user") if isinstance(raw.get("user"), dict) else {}
    mergeable = detail.get("mergeable")
    return {
        "number": _as_int(raw.get("number")), "title": raw.get("title"), "author": user.get("login"),
        "association": raw.get("author_association"), "created_at": raw.get("created_at"),
        "draft": bool(raw.get("draft")), "head_ref": head.get("ref"), "fork": fork,
        "ci": summarize_checks(check_runs) if check_runs is not None else "unknown",
        "mergeable": mergeable if isinstance(mergeable, bool) else None,
        "mergeable_state": str(detail.get("mergeable_state") or "").lower(), "error": str(error or ""),
    }


_PULL_COPY = {
    "ready": ("병합하면 됩니다", "검사(CI)가 모두 통과했고 충돌이 없습니다.",
              "PR 코멘트의 변경 범위 검사 결과를 먼저 확인하세요(경고여도 검사는 초록으로 보입니다). 이상이 없고 변경 내용도 훑어봤다면 'Merge pull request'를 누르세요."),
    "conflict": ("충돌을 풀어야 합니다", "main 브랜치와 충돌합니다.",
                 "PR을 만든 AI(또는 Copilot)에게 '충돌을 해결해 달라'고 요청하세요."),
    "ci_fail": ("검사(CI) 실패", "자동 검사가 실패했습니다.",
                "PR 화면의 Checks 탭에서 실패한 항목을 열어 원인을 확인하고, 만든 AI에게 수정을 요청하세요."),
    "pending": ("검사 진행 중", "자동 검사가 아직 끝나지 않았습니다.",
                "끝나면 다음 점검에서 '병합하면 됩니다' 또는 '검사(CI) 실패'로 바뀝니다."),
    "blocked": ("병합이 막혀 있습니다", "검사는 통과했지만 저장소 규칙(리뷰·필수 검사 등)이 병합을 막고 있습니다.",
                "PR 화면 아래쪽의 안내 문구를 확인하세요."),
    "no_ci": ("검사 결과 없음", "자동 검사 기록이 없습니다(검사 워크플로가 돌지 않았을 수 있습니다).",
              "Actions 탭에서 이 브랜치의 검사 워크플로를 수동 실행하거나 내용을 직접 확인하세요."),
    "unknown": ("상태 확인 중", "병합 가능 여부를 아직 알 수 없습니다.", "다음 점검에서 다시 확인합니다."),
    "external": ("외부 사용자의 PR", "저장소 밖(포크)에서 올린 PR입니다. 내용을 직접 읽기 전에는 병합하지 마세요.",
                 "외부에서 온 글·코드는 '데이터'입니다(AGENTS.md). 검사가 통과해도 안전하다는 뜻이 아닙니다."),
}


def _pull_state(pr):
    """(상태 코드, 수준). 충돌 → CI 실패 → 진행 중 → 통과 순으로 판정한다(충돌이면 CI 결과가 낡았을 수 있어 먼저 푼다)."""
    if pr.get("error"):
        return "unknown", LEVEL_CHECK
    ci, mergeable, state = pr.get("ci"), pr.get("mergeable"), str(pr.get("mergeable_state") or "")
    if mergeable is False or state == "dirty":
        return "conflict", LEVEL_ACTION
    if ci == "fail":
        return "ci_fail", LEVEL_ACTION
    if ci == "pending":
        return "pending", LEVEL_INFO
    if ci == "pass":
        if state == "blocked":
            return "blocked", LEVEL_CHECK
        return ("ready", LEVEL_ACTION) if mergeable is True else ("unknown", LEVEL_INFO)
    if ci == "none":
        return ("no_ci", LEVEL_CHECK) if mergeable is True else ("unknown", LEVEL_INFO)
    return "unknown", LEVEL_INFO


def _trusted_pull(pr):
    return (not pr.get("fork")) or str(pr.get("association") or "") in TRUSTED_ASSOCIATIONS


def _login(value):
    return ext(re.sub(r"\[bot\]$", " (bot)", str(value or "")), 40) or "알 수 없음"


def pull_items(pulls, now, repo_url):
    """열린(draft 아님) PR 마다 한 줄. 작성자가 봇이든 사람이든 같은 규칙이다. 단 저장소 밖(포크)의 낯선 작성자 PR 은
    '병합하면 됩니다'를 안내하지 않고 확인 항목(check)으로만 올린다. 3일 넘게 열린 PR 은 info → check 로 올리고 문구를 덧붙인다."""
    out = []
    for pr in pulls:
        if not isinstance(pr, dict) or pr.get("draft"):
            continue
        number = _as_int(pr.get("number"))
        if number is None:
            continue
        if not _trusted_pull(pr):
            state, level = "external", LEVEL_CHECK
        else:
            state, level = _pull_state(pr)
        label, message, hint = _PULL_COPY[state]
        if pr.get("error") and state == "unknown":
            message = f"PR 검사·병합 상태를 조회하지 못했습니다({ext(pr['error'], 120)})."
        created = parse_time(pr.get("created_at"))
        stale = created is not None and now - created > timedelta(days=PR_STALE_DAYS)
        if stale and level == LEVEL_INFO:
            level = LEVEL_CHECK
        context = [f"작성 {_login(pr.get('author'))}"]
        if pr.get("head_ref"):
            context.append(f"브랜치 {ext(pr.get('head_ref'), 50)}")
        context.append(f"검사 {_CI_LABELS.get(pr.get('ci'), _CI_LABELS['unknown'])}")
        detail = f"{message} ({' · '.join(context)})" + (f" · {PR_STALE_DAYS}일 넘게 열려 있음" if stale else "")
        out.append(Item(
            id=f"pr:{number}:{state}", level=level, since=created, url=f"{repo_url}/pull/{number}",
            title=f"PR #{number} {label} — {ext(pr.get('title'), 70)}", detail=detail, hint=hint))
    return out


# ----------------------------------------------------------------------------
# 규칙 3: 워크플로 실행(실패·경고·승인 대기)
# ----------------------------------------------------------------------------
def _is_noise(message):
    return any(rx.search(message) for rx in PLATFORM_NOISE)


_ACTION_REF_RE = re.compile(r"\b([A-Za-z0-9][\w.-]*/[\w.-]+)@([\w.-]*\w)")   # actions/checkout@v4 → ('actions/checkout', 'v4')
_WORKFLOW_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}\.ya?ml$")


def workflow_file(path):
    """실행의 path(예: .github/workflows/pages.yml, 끝에 @refs/… 가 붙기도 한다) → 파일 이름(pages.yml). 알 수 없으면 빈 문자열."""
    base = str(path or "").split("@", 1)[0].rsplit("/", 1)[-1]
    return base if _WORKFLOW_FILE_RE.fullmatch(base) else ""


def _repo_of(repo_url):
    return str(repo_url).rpartition("github.com/")[2]


def foreign_pull_run(run, repo):
    """저장소 밖(포크)에서 온 풀 리퀘스트가 일으킨 실행인가: event 가 pull_request·pull_request_target 이고 head 저장소가 이 저장소가 아니거나 알 수 없다.
    포크 PR 의 head 브랜치가 main 이면 'main 브랜치의 실행'에 섞여 들 수 있어(API 가 막아 주는지는 확인하지 못했다) 방어적으로 거른다.
    다른 이벤트(schedule·push·workflow_dispatch 등)는 head 저장소를 보지 않는다."""
    if not isinstance(run, dict) or run.get("event") not in PULL_EVENTS:
        return False
    head = run.get("head_repository")
    name = head.get("full_name") if isinstance(head, dict) else None
    return not (isinstance(name, str) and name.lower() == str(repo).lower())


def _platform_item(texts, repo_url):
    """플랫폼 안내성 주석(문구 목록)을 한 줄로 합친다: 몇 종인지, 어떤 액션인지, 예시 문구 하나.

    어느 워크플로·어느 실행에서 나왔는지는 싣지 않고 링크도 저장소의 Actions 화면(고정 주소)으로 둔다 — 싣는 순간 다른 워크플로가 돌 때마다
    본문이 바뀌어 이슈를 계속 다시 쓰게 된다(알림은 없어도 수정 이력·쓰기 호출이 늘고 '바로 한 번 더 실행하면 변경 없음'이 깨진다).
    같은 문구 집합이면 입력 순서와 상관없이 항상 같은 항목이다(같은 종류의 문구는 글자 순으로 앞선 것, 예시는 접은 문구 순으로 가장 앞의 것)."""
    kinds, actions = {}, set()
    for text in texts:
        key = fold(text, 400).lower()
        kinds[key] = min(kinds[key], text) if key in kinds else text
        actions.update(_ACTION_REF_RE.findall(text))
    parts = []
    if actions:
        # '@' 는 멘션으로 읽힐 수 있어 공백으로 쓰고, 커밋 해시(40자)로 고정된 액션은 앞 7자만 보인다
        parts.append("액션: " + ", ".join(f"{ext(repo, 40)} {ref[:7] if _SHA_RE.fullmatch(ref) else ext(ref, 12)}" for repo, ref in sorted(actions)))
    parts.append(f"예: “{ext(kinds[min(kinds)], 110)}”")
    return Item(
        id="run:platform_notice", level=LEVEL_INFO, url=f"{repo_url}/actions",
        title=f"GitHub Actions 플랫폼 경고 {len(kinds)}종 — {'액션 버전 갱신 필요' if actions else '플랫폼 변경 예고'}, 당장은 발행에 영향 없음",
        detail=" · ".join(parts),
        hint="우리 스크립트가 남긴 경고가 아니라 GitHub 가 모든 실행에 붙이는 안내입니다. 액션 버전을 올리는 변경을 AI에게 요청하면 됩니다(지금 할 일은 없습니다).")


def _run_time(run):
    return parse_time(run.get("created_at"))


def run_items(runs_by_file, annotations, now, repo_url, own=OWN_WORKFLOW, names=None):
    """워크플로 파일마다 main 브랜치의 최근 실행(48시간 창)을 보고 항목을 만든다. 이 모음 자신의 실행·취소·건너뜀·승인 대기는 무시한다.

    - 항목 제목의 워크플로 이름은 names(파일 이름 → 그 파일의 최상위 name)에서 가져온다. 실행(run)의 name 은 run-name 이라 실행마다 다르고
      (연습 여부·이슈 번호 등), 이름을 바꾸기 전에 만든 실행의 옛 이름도 이력에 섞여 있다. 이름을 읽지 못한 파일은 파일 이름으로 보인다.
    - 포크 PR 이 일으킨 실행(foreign_pull_run)은 판단에서 뺀다(그 head 브랜치가 main 이어도 main 의 실패·성공으로 섞이지 않게).
    - 가장 최근 완료 실행이 failure/timed_out/startup_failure → action(연속 실패 횟수와 시작 시각 포함)
    - 성공 실행의 주석(annotations)에 warning 수준 문구가 있으면 → check(서로 다른 문구 3개까지, 한 줄로 접어서). 주석을 읽은
      실행(annotations 에 id 가 있는 실행)만 본다.
    - 플랫폼이 붙이는 안내성 주석(PLATFORM_NOISE, warning·notice 수준)은 check 가 아니라 모든 워크플로를 통틀어 info 한 줄로 합친다
      (몇 종인지·어떤 액션인지·예시 문구). 어느 워크플로·실행인지는 싣지 않는다(다른 워크플로가 돌 때마다 본문이 바뀌므로). info 라서 새 action 알림 대상이
      아니다. 우리 쪽 notice 는 무시한다."""
    items, platform = [], []
    names = names if isinstance(names, dict) else {}
    repo = _repo_of(repo_url)
    for file in sorted(runs_by_file):
        if file == own:
            continue
        runs = [r for r in (runs_by_file.get(file) or [])
                if isinstance(r, dict) and _run_time(r) is not None and now - _run_time(r) <= timedelta(hours=RUN_WINDOW_HOURS)
                and not foreign_pull_run(r, repo)]
        runs.sort(key=_run_time, reverse=True)
        completed = [r for r in runs if r.get("status") == "completed" and r.get("conclusion") not in IGNORED_CONCLUSIONS]
        name = ext(names.get(file) or file, 60)
        slug = _slug(file)

        if completed and completed[0].get("conclusion") in FAILED_CONCLUSIONS:
            streak = []
            for run in completed:
                if run.get("conclusion") not in FAILED_CONCLUSIONS:
                    break
                streak.append(run)
            newest = streak[0]
            kind = _CONCLUSION_LABELS.get(newest.get("conclusion"), "실패")
            items.append(Item(
                id=f"run:{slug}:failed", level=LEVEL_ACTION, title=f"워크플로 실패 — {name}",
                detail=f"가장 최근 실행이 {kind}했습니다({file})" + (f" · 연속 {len(streak)}회" if len(streak) > 1 else ""),
                url=f"{repo_url}/actions/runs/{_as_int(newest.get('id')) or 0}", since=_run_time(streak[-1]),
                hint="실행 화면에서 빨간 단계의 로그를 확인하세요(이 링크를 AI에게 주고 원인 분석을 요청할 수 있습니다)."))

        successes = [r for r in completed if r.get("conclusion") == "success"]
        scanned = [r for r in successes if _as_int(r.get("id")) in annotations]
        hits = []
        for run in scanned:
            messages = []
            for ann in annotations.get(_as_int(run.get("id"))) or []:
                level = ann.get("annotation_level") if isinstance(ann, dict) else None
                text = str(ann.get("message") or ann.get("title") or "").strip() if level in PLATFORM_LEVELS else ""
                if not text:
                    continue
                if _is_noise(text):
                    platform.append(text)
                elif level == "warning":
                    messages.append(text)
            if messages:
                hits.append((run, messages))
        if hits:
            shown, seen = [], set()
            for _run, messages in hits:
                for message in messages:
                    key = fold(message, MESSAGE_MAX).lower()
                    if key not in seen and len(shown) < WARNING_MESSAGES_MAX:
                        seen.add(key)
                        shown.append(f"“{ext(message, MESSAGE_MAX)}”")
            items.append(Item(
                id=f"run:{slug}:warn", level=LEVEL_CHECK, title=f"실행은 성공했지만 경고가 있습니다 — {name}",
                detail=f"경고 문구: {' / '.join(shown)} (확인한 성공 실행 {len(scanned)}회 중 {len(hits)}회)",
                url=f"{repo_url}/actions/runs/{_as_int(hits[0][0].get('id')) or 0}", since=_run_time(hits[-1][0]),
                hint="초록 체크여도 글이 올라가지 않았거나 일부 단계를 건너뛴 경우가 있습니다. 경고 문구와 실행 요약을 확인하세요."))
    if platform:
        items.append(_platform_item(platform, repo_url))
    return items


def approval_items(runs, repo_url, own=OWN_WORKFLOW, names=None):
    """승인 대기(action_required) 실행 → action 'Approve and run'. 같은 커밋의 실행은 한 항목으로 묶고 최대 5개만 보여 준다.
    워크플로 이름은 실행의 path 가 가리키는 파일의 최상위 name(names)을 먼저 쓰고, 그 파일을 모르면 실행의 name 을 쓴다."""
    names = names if isinstance(names, dict) else {}
    groups = {}
    for run in runs:
        if not isinstance(run, dict) or _as_int(run.get("id")) is None:
            continue
        if run.get("status") != "action_required" and run.get("conclusion") != "action_required":
            continue
        path = str(run.get("path") or "")
        if path == own or path.endswith("/" + own):
            continue
        sha = str(run.get("head_sha") or "")
        key = sha[:7] if _SHA_RE.fullmatch(sha) else f"r{run['id']}"
        groups.setdefault(key, []).append(run)

    def oldest(key):
        times = [t for t in (_run_time(r) for r in groups[key]) if t]
        return (min(times).timestamp() if times else float("inf"), key)

    keys = sorted(groups, key=oldest)
    items = []
    for key in keys[:APPROVAL_ITEMS_MAX]:
        group = sorted(groups[key], key=lambda r: r["id"])
        titles = ", ".join(sorted({ext(names.get(workflow_file(r.get("path"))) or r.get("name") or r.get("path") or "워크플로", 40) for r in group})[:3])
        first = group[0]
        label = ext(first.get("display_title") or first.get("head_branch") or "이름 없음", 70)
        times = [t for t in (_run_time(r) for r in group) if t]
        items.append(Item(
            id=f"approve:{key}", level=LEVEL_ACTION, title=f"승인 대기(Approve and run) — {label}",
            detail=f"워크플로 {titles}가 승인을 기다립니다(브랜치 {ext(first.get('head_branch'), 40)}). 승인 전에는 검사가 시작되지 않습니다.",
            url=f"{repo_url}/actions/runs/{first['id']}", since=min(times) if times else None,
            hint="실행 화면의 'Approve and run workflows'를 누르면 시작됩니다. 모르는 사람이 올린 코드라면 읽어 보기 전에는 승인하지 마세요."))
    if len(keys) > APPROVAL_ITEMS_MAX:
        items.append(Item(
            id="approve:more", level=LEVEL_ACTION, title=f"승인 대기 실행이 {len(keys) - APPROVAL_ITEMS_MAX}건 더 있습니다",
            url=f"{repo_url}/actions", hint="Actions 탭에서 승인 대기 중인 실행을 확인하세요."))
    return items


# ----------------------------------------------------------------------------
# 규칙 4: 일시정지
# ----------------------------------------------------------------------------
def pause_items(paused, repo_url):
    if not paused:
        return []
    return [Item(
        id="pause", level=LEVEL_ACTION, title="자동 발행이 멈춰 있습니다 — 해제 방법",
        detail="저장소 변수 PIPELINE_PAUSE 가 켜져 있어 Chance·Blogger 자동 글 생성이 멈춰 있습니다.",
        url=f"{repo_url}/settings/variables/actions",
        hint="변수 PIPELINE_PAUSE 를 삭제(또는 false 로 변경)하면 다음 실행부터 다시 발행합니다. 일부러 멈춘 것이라면 그대로 두어도 됩니다.")]


# ----------------------------------------------------------------------------
# 규칙 5: 블로그 상태(게시 시크릿·정지·초안 대기) / 규칙 6: 현황
# ----------------------------------------------------------------------------
def _parse_day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def entry_moment(entry):
    """이력 항목의 (시각, 정밀도). 정밀도: 'time' 정확한 시각 / 'slot' 날짜+게시 슬롯 시(KST) / 'date' 날짜만. 읽을 수 없으면 None."""
    if not isinstance(entry, dict):
        return None
    moment = parse_time(entry.get("generated_at"))
    if moment:
        return moment, "time"
    day = _parse_day(entry.get("date"))
    if day is None:
        return None
    slot = entry.get("slot")
    if _as_int(slot) is not None and 0 <= slot <= 23:
        return datetime(day.year, day.month, day.day, slot, tzinfo=KST), "slot"
    return datetime(day.year, day.month, day.day, tzinfo=KST), "date"


def _missing_secret_names(reason, mapping):
    """'[SECRETS] 게시 시크릿 미등록: blog_id, client_id' → 레지스트리의 시크릿 '이름'(값이 아니다) 목록."""
    tail = reason.split(":", 1)[1] if ":" in reason else ""
    names = []
    for role in (t.strip() for t in tail.split(",")):
        env = mapping.get(role) if isinstance(mapping, dict) and _ROLE_RE.fullmatch(role) else None
        if isinstance(env, str) and _ENV_RE.fullmatch(env) and env not in names:
            names.append(env)
    return names


def _secrets_item(blog, key, name, history, repo_url):
    stage = [e for e in history if isinstance(e, dict) and e.get("status") in PUBLISH_STAGE]
    if not stage or stage[-1].get("status") != "generated_unpublished":
        return None
    reasons = stage[-1].get("reasons")
    reason = next((r for r in (reasons if isinstance(reasons, list) else []) if isinstance(r, str) and "[SECRETS]" in r), None)
    if reason is None:
        return None
    streak = []
    for entry in reversed(stage):
        if entry.get("status") != "generated_unpublished":
            break
        streak.append(entry)
    names = _missing_secret_names(reason, blog.get("secrets"))
    moment = entry_moment(streak[-1])
    return Item(
        id=f"blogger:{key}:secrets", level=LEVEL_ACTION, title=f"{name} 게시 설정(시크릿) 필요", since=moment[0] if moment else None,
        detail=(f"최근 {len(streak)}회 연속으로 글은 만들었지만 게시하지 못하고 저장소 초안으로만 남았습니다. "
                + (f"비어 있는 시크릿 이름: {', '.join(names)}." if names else "게시용 시크릿이 비어 있습니다.")),
        url=f"{repo_url}/settings/secrets/actions",
        hint="위 이름으로 저장소 시크릿을 등록하세요(값은 채팅·이슈에 적지 마세요). 발급 절차는 HANDLER.md §10.")


def _drafts_item(key, name, history, now):
    waiting = []
    for entry in history:
        moment = entry_moment(entry) if isinstance(entry, dict) and entry.get("status") == "draft_uploaded" else None
        if moment and now - moment[0] <= timedelta(days=DRAFT_WAIT_DAYS):
            waiting.append(moment[0])
    if not waiting:
        return None
    return Item(
        id=f"blogger:{key}:drafts:{max(waiting).astimezone(KST).strftime('%Y%m%d%H%M')}", level=LEVEL_ACTION,
        title=f"{name}: 초안 {len(waiting)}건 게시 대기", since=min(waiting), url="https://www.blogger.com/",
        detail=(f"Blogger 초안함에 올라간 글이 최근 {DRAFT_WAIT_DAYS}일 안에 {len(waiting)}건 있습니다. 이력으로는 게시했는지 알 수 없어 "
                f"{DRAFT_WAIT_DAYS}일이 지나면 이 항목은 저절로 사라집니다."),
        hint="Blogger 관리 화면의 '글'에서 초안을 확인하고 게시하세요.")


def blog_items(blogs, histories, now, repo_url):
    """mode=off 는 참고(정지 이유 포함). auto·draft 블로그는 ① 최신 게시 단계 이력이 generated_unpublished 이고 사유에 [SECRETS] 가 있으면
    시크릿 등록 action, ② Blogger 초안함 업로드(draft_uploaded) 가 최근 7일 안에 있으면 게시 대기 action.
    '최신 게시 단계 이력'은 posted·draft·generated_unpublished·publish_failed·draft_uploaded 중 가장 나중 항목이다
    (rejected·skipped 같은 게시 단계에 가지 못한 실행은 시크릿 상태를 알려 주지 않으므로 건너뛴다)."""
    items = []
    for blog in blogs:
        key = blog.get("key") if isinstance(blog, dict) else None
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
            continue
        name = ext(blog.get("name") or key, 50)
        if str(blog.get("mode") or "draft") == "off":
            note = str(blog.get("note") or blog.get("_note") or "").strip()
            items.append(Item(
                id=f"blog:{key}:off", level=LEVEL_INFO, title=f"{name}: 정지 중(mode=off)",
                detail=f"이유: {ext(note, 200)}" if note else "블로그 레지스트리(pipeline/blogs.json)에서 mode=off 로 멈춰 있습니다.",
                hint="다시 켜려면 mode 를 draft(초안만) 또는 auto(자동 게시)로 바꾸는 변경이 필요합니다. auto 전환은 운영자 승인 사항입니다."))
            continue
        history = histories.get(key)
        history = history if isinstance(history, list) else []
        for item in (_secrets_item(blog, key, name, history, repo_url), _drafts_item(key, name, history, now)):
            if item is not None:
                items.append(item)
    return items


def _post_kind(entry):
    """'post' 게시된 글 / 'draft' 초안·미게시 / None 해당 없음. Chance 처럼 status 가 없는 dict 는 글 한 건(KR+EN 한 쌍)이다."""
    if not isinstance(entry, dict):
        return None
    status = entry.get("status")
    if status is None or status == "posted":
        return "post"
    return "draft" if status in ("draft", "generated_unpublished", "draft_uploaded") else None


def blog_stats(history, now):
    """이력 → {last: (시각, 정밀도) | None, posts_24h, drafts_24h}. 날짜만 기록된 항목은 오늘(KST) 날짜면 24시간 안으로 센다."""
    today = now.astimezone(KST).date()
    posts, last = 0, None
    drafts = 0
    for entry in history:
        kind = _post_kind(entry)
        moment = entry_moment(entry) if kind else None
        if moment is None:
            continue
        when, precision = moment
        inside = (when.astimezone(KST).date() == today) if precision == "date" else (timedelta(0) <= now - when <= timedelta(hours=24))
        if kind == "post":
            posts += 1 if inside else 0
            if last is None or when > last[0]:
                last = moment
        elif inside:
            drafts += 1
    return {"last": last, "posts_24h": posts, "drafts_24h": drafts}


def _last_text(last):
    if last is None:
        return "없음"
    when, precision = last
    if precision == "time":
        return fmt_kst(when)
    day = when.astimezone(KST).strftime("%Y-%m-%d")
    return f"{day} {when.astimezone(KST).hour:02d}시 슬롯(KST)" if precision == "slot" else f"{day}(날짜만 기록됨)"


def stats_items(blogs, histories, now):
    """블로그별 현황(참고): 마지막 글 시각(KST)·최근 24시간 글 수. 이력이 없거나 형식이 달라도 죽지 않는다. mode=off 는 제외."""
    items = []
    for blog in blogs:
        key = blog.get("key") if isinstance(blog, dict) else None
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key) or str(blog.get("mode") or "draft") == "off":
            continue
        history = histories.get(key)
        stats = blog_stats(history if isinstance(history, list) else [], now)
        detail = f"최근 24시간 글 {stats['posts_24h']}건"
        if stats["drafts_24h"]:
            detail += f" · 초안·미게시 {stats['drafts_24h']}건"
        items.append(Item(id=f"stat:{key}", level=LEVEL_INFO, title=f"{ext(blog.get('name') or key, 50)}: 마지막 글 {_last_text(stats['last'])}",
                          detail=detail))
    return items


# ----------------------------------------------------------------------------
# 규칙 7: 초안(이슈·PR) — 초안 모델·항목·초안 현황 표
# ----------------------------------------------------------------------------
def channel_label_name(label):
    """채널 라벨(레지스트리 channel.label) → 초안에 붙이는 GitHub 라벨 이름(예: `채널:티스토리`)."""
    return f"{CHANNEL_LABEL_PREFIX}{label}"


def _registry_channel(blog):
    """레지스트리 블로그의 채널 라벨. 없거나 문자열이 아니면 빈 문자열(그 블로그는 초안 현황에 줄이 없다 — 레지스트리 검증이 channel 을 필수로 요구한다)."""
    channel = blog.get("channel") if isinstance(blog, dict) else None
    label = channel.get("label") if isinstance(channel, dict) else None
    return label.strip() if isinstance(label, str) else ""


def draft_label_specs(blogs):
    """초안 모델의 라벨 [{name, color, description}] — 초안·폐기, 그리고 레지스트리 채널마다 `채널:<라벨>`(레지스트리 순서, 중복·너무 긴 이름은 뺀다).
    scripts/ops_inbox.py 가 저장소에 없는 것만 만든다. 색·설명은 고정이다."""
    specs = [{"name": name, "color": color, "description": text} for name, color, text in DRAFT_LABEL_SPECS]
    seen = {spec["name"].casefold() for spec in specs}
    for blog in blogs:
        label = _registry_channel(blog)
        name = channel_label_name(label)
        if not label or len(name) > LABEL_NAME_MAX or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        specs.append({"name": name, "color": CHANNEL_LABEL_COLOR, "description": f"초안이 속한 채널: {label}"[:100]})
    return specs


def normalize_draft(raw):
    """GitHub 이슈·PR 객체 하나 → 규칙이 읽는 평평한 dict(번호·종류·제목·채널·라벨·상태·생성 시각·믿을 수 있는 작성자인가). 번호를 읽을 수 없으면 None.

    GET /issues 는 PR 도 돌려주고 PR 에는 'pull_request' 키가 있다(종류 'pull'). 채널은 `채널:` 로 시작하는 라벨에서 읽는다(여럿이면 글자 순으로 첫 번째).
    링크는 번호로 직접 만드므로 API 가 준 주소(html_url 등)는 읽지 않는다."""
    if not isinstance(raw, dict):
        return None
    number = _as_int(raw.get("number"))
    if number is None or number < 1:
        return None
    labels = []
    for label in raw.get("labels") if isinstance(raw.get("labels"), list) else []:
        name = label.get("name") if isinstance(label, dict) else label
        if isinstance(name, str) and name.strip():
            labels.append(name.strip())
    channels = sorted(name[len(CHANNEL_LABEL_PREFIX):].strip() for name in labels if name.startswith(CHANNEL_LABEL_PREFIX))
    channels = [name for name in channels if name]
    return {"number": number, "kind": "pull" if "pull_request" in raw else "issue", "title": raw.get("title"),
            "state": str(raw.get("state") or "open").lower(), "created_at": raw.get("created_at"), "labels": tuple(labels),
            "channel": channels[0] if channels else None, "trusted": trusted_author(raw)}


def pending_drafts(drafts):
    """normalize_draft 결과 중 '대기 초안'만, 번호 순서로: 열려 있고 · 라벨 `초안`이 있고 · 라벨 `폐기`가 없고 · 믿을 수 있는 작성자(github-actions 봇이거나
    소유자·멤버·협업자)가 만든 것. 낯선 사람이 같은 제목으로 위장한 이슈는 세지 않는다(워치독 이슈와 같은 원칙). 같은 번호는 한 번만(이슈와 PR 은 번호를 함께 쓴다)."""
    out, seen = [], set()
    for draft in drafts if isinstance(drafts, (list, tuple)) else []:
        if not isinstance(draft, dict):
            continue
        number = _as_int(draft.get("number"))
        labels = draft.get("labels") if isinstance(draft.get("labels"), (list, tuple)) else ()
        if (number is None or number in seen or draft.get("state", "open") != "open" or DRAFT_LABEL not in labels
                or DISCARD_LABEL in labels or draft.get("trusted") is not True):
            continue
        seen.add(number)
        out.append(draft)
    return sorted(out, key=lambda d: d["number"])


def _draft_title_text(draft, limit):
    """초안 이슈 제목(`[초안][티스토리] 글 제목`)에서 앞의 `[초안]`·`[채널]` 표지를 떼고 ext() 로 무력화한 글 제목. 비면 '제목 없음'."""
    text = " ".join(str(draft.get("title") or "").split())
    for tag in (DRAFT_LABEL, draft.get("channel")):
        if tag and text.startswith(f"[{tag}]"):
            text = text[len(tag) + 2:].lstrip()
    return ext(text, limit) or "제목 없음"


def draft_items(drafts, now, repo_url):
    """열린 초안 '이슈'마다 한 줄. DRAFT_STALE_DAYS 일 이하로 열려 있으면 action(새 초안 — 새 항목이라 코멘트(@멘션)로 알림), 그보다 오래면 check(알림 없음).

    상태가 id 에 들어 있다(draft:<번호>:wait · draft:<번호>:stale) — 같은 초안이 오래되면 새 알림 없이 check 로 옮겨 가고, 닫았다가 다시 열면 새 항목으로 다시 알린다.
    PR 초안(kind 'pull')은 여기서 항목을 만들지 않는다: 열린 PR 규칙(pull_items)이 같은 PR 을 검사·병합 상태와 함께 이미 한 줄로 다루므로 또 만들면 같은 PR 이 두 번 알림이 된다.
    PR 초안도 초안 현황 표(draft_board)에는 센다."""
    out = []
    for draft in pending_drafts(drafts):
        if draft["kind"] != "issue":
            continue
        number = draft["number"]
        created = parse_time(draft.get("created_at"))
        stale = created is not None and now - created > timedelta(days=DRAFT_STALE_DAYS)
        channel = ext(draft.get("channel") or "채널 표시 없음", 30)
        title = _draft_title_text(draft, DRAFT_TITLE_MAX)
        url = f"{repo_url}/issues/{number}"
        if stale:
            out.append(Item(
                id=f"draft:{number}:stale", level=LEVEL_CHECK, since=created, url=url,
                title=f"초안 {DRAFT_STALE_DAYS}일 넘게 대기 — {title}",
                detail=f"채널 {channel} · 이슈 #{number} · {DRAFT_STALE_DAYS}일 넘게 열려 있음",
                hint="발행했다면 이슈를 닫고, 쓰지 않기로 했다면 라벨 `폐기`를 붙이거나 닫으세요. 닫으면 이 목록에서 사라집니다."))
        else:
            out.append(Item(
                id=f"draft:{number}:wait", level=LEVEL_ACTION, since=created, url=url,
                title=f"초안 대기 — {title}", detail=f"채널 {channel} · 이슈 #{number} · 발행을 기다립니다",
                hint="이슈 본문의 제목·본문·태그를 복사해 직접 발행한 뒤 이슈를 닫으세요(닫기 = 발행 완료). 쓰지 않을 글은 라벨 `폐기`를 붙이거나 닫으세요."))
    return out


def draft_filter_url(repo_url, label=None, pulls=False):
    """휴대폰에서 바로 열 수 있는 대기 초안 목록 주소: `is:open label:초안`(+ `label:"채널:<라벨>"`)을 퍼센트 인코딩해 이슈(또는 PR) 목록의 검색어로 넣는다.
    GitHub 의 이슈 목록은 이슈만, PR 목록은 PR 만 보여 주므로 PR 초안(Chance 승인 흐름)은 pulls=True 주소로 본다."""
    query = f"is:open label:{DRAFT_LABEL}"
    if label:
        query += ' label:"' + channel_label_name(label).replace('"', "") + '"'
    return f"{repo_url}/{'pulls' if pulls else 'issues'}?q={urllib.parse.quote_plus(query)}"


def history_drafts(history, now):
    """Blogger 이력의 draft_uploaded 중 DRAFT_WINDOW_DAYS 일 안의 것 → [(시각, 정밀도)]. 시각을 읽을 수 없는 항목은 세지 않는다.
    이력만으로는 사람이 이미 게시했는지 알 수 없다 — 대략치다."""
    out = []
    for entry in history if isinstance(history, list) else []:
        moment = entry_moment(entry) if isinstance(entry, dict) and entry.get("status") == "draft_uploaded" else None
        if moment and now - moment[0] <= timedelta(days=DRAFT_WINDOW_DAYS):
            out.append(moment)
    return out


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_BAR = chr(0xFF5C)         # '｜' — 표 칸 구분자 '|' 를 대신하는 전각 문자
_LINKABLE_LABEL_RE = re.compile(r"^[0-9A-Za-z가-힣][0-9A-Za-z가-힣 _.\-]{0,39}$")
BOARD_HEADER = ("채널", "대기 초안", "가장 오래된", "최신 초안")
BOARD_NOTE_MODEL = ("초안은 라벨 `초안`과 `채널:티스토리` 같은 채널 라벨이 붙은 열린 이슈·PR 입니다. 발행했으면 이슈를 닫고, 쓰지 않을 글은 라벨 `폐기`를 붙이거나 닫으세요"
                    "(둘 다 이 표에서 빠집니다). '가장 오래된'은 하루 단위라 하루에 한 번 바뀝니다.")
BOARD_NOTE_BLOGGER = (f"Blogger 는 초안함에 올린 기록(최근 {DRAFT_WINDOW_DAYS}일)을 센 대략치입니다 — 이미 게시했는지는 Blogger 쪽 사실이라 여기서는 알 수 없습니다. "
                      "확인·게시: Blogger 대시보드 → 글 → 초안(블로그 ID 가 시크릿이라 링크는 싣지 않습니다).")


def _cell(text):
    """표 칸에 넣는 글: 칸 구분자 '|' 를 전각으로 바꾼다(ext 가 이미 줄·링크 문법·멘션을 무력화했다)."""
    return str(text).replace("|", _BAR)


def _filter_links(label, repo_url, with_pull):
    """채널 하나의 모바일 필터 링크 [(글, 주소)](이슈 목록, with_pull 이면 PR 목록도). 라벨이 단순한 글자(영문·숫자·한글·공백·_.-, 40자 이하)이고 비밀 값 모양이
    아닐 때만 만든다 — 주소에는 ext() 를 쓸 수 없어서, 레지스트리에 없는 채널 라벨(외부 글)의 멘션·HTML·비밀 값이 주소에 그대로 실리지 않게 한다. 링크가 없어도 표의 줄은 남는다."""
    if not isinstance(label, str) or not _LINKABLE_LABEL_RE.fullmatch(label) or mask(label) != label:
        return []
    shown = _cell(ext(label, 30))
    links = [(shown, draft_filter_url(repo_url, label))]
    if with_pull:
        links.append((shown + " PR", draft_filter_url(repo_url, label, pulls=True)))
    return links


def _age_text(now, moment):
    days = max(int((now - moment).total_seconds() // 86400), 0)
    return f"{days}일" if days else "1일 미만"


def _depends_on_github(blog):
    """이 채널의 대기 초안이 GitHub(라벨 초안인 이슈·PR)에 있는가. Blogger 는 이력, Chance 는 승인 흐름(publish_flow=pr)일 때만 PR, 그 밖의 새 채널(티스토리·네이버 등)은 이슈."""
    platform = str(blog.get("platform") or "")
    if platform == "blogger":
        return False
    return not (platform == "jekyll-git" and blog.get("publish_flow") != "pr")


def _candidate_from_draft(draft, repo_url):
    """(생성 시각, 번호, 최신 초안 칸 글, 대략치인가) — GitHub 초안은 번호와 제목이 든 링크."""
    number = draft["number"]
    path = "pull" if draft["kind"] == "pull" else "issues"
    title = _cell(_draft_title_text(draft, BOARD_TITLE_MAX))
    return parse_time(draft.get("created_at")), number, f"[#{number} {title}]({repo_url}/{path}/{number})", False


def _row_cells(label, blog, candidates, now, lookup_failed):
    """표의 한 줄 [채널, 대기 초안, 가장 오래된, 최신 초안]. candidates: _candidate_* 목록."""
    mode = str(blog.get("mode") or "draft") if blog else "draft"
    if candidates:
        text = str(len(candidates)) + (" (대략)" if any(c[3] for c in candidates) else "") + (" (정지 중)" if mode == "off" else "")
        moments = [c[0] for c in candidates if c[0] is not None]
        newest = max(candidates, key=lambda c: (c[0] or _EPOCH, c[1]))
        return [label, text, _age_text(now, min(moments)) if moments else "-", newest[2]]
    if mode == "off":
        text = "정지"
    elif lookup_failed:
        text = "조회 실패"
    elif blog and str(blog.get("platform") or "") == "jekyll-git" and blog.get("publish_flow") != "pr":
        text = "자동 공개"
    else:
        text = "0"
    return [label, text, "-", "-"]


def board_rows(snap, now=None):
    """초안 현황 표의 줄과 모바일 필터 링크. (줄 목록 [[채널, 대기 초안, 가장 오래된, 최신 초안], …], 링크 목록 [(글, 주소), …],
    Blogger 안내 줄이 필요한가 — 정지(mode=off)가 아닌 Blogger 채널이 있을 때 True).

    줄 순서: 레지스트리 블로그 순서의 채널(대기 0 이어도 유지, mode=off 는 '정지') → 레지스트리에 없는 채널 이름의 초안(라벨 글자 순, '(미등록)') → 채널 표시가
    없는 초안('(채널 표시 없음)'). 줄 수는 BOARD_ROWS_MAX 이하(넘치는 미등록 채널은 한 줄로 합친다)."""
    now = _aware(snap.now) if now is None else now
    repo_url = f"https://github.com/{snap.repo}"
    by_channel = {}
    for draft in pending_drafts(snap.drafts):
        by_channel.setdefault((draft.get("channel") or "").casefold(), []).append(draft)
    drafts_failed = any(source == "drafts" for source, _reason in snap.failures)
    rows, links, known, blogger = [], [], set(), False
    for blog in snap.blogs:
        label = _registry_channel(blog)
        if not label or label.casefold() in known:
            continue
        known.add(label.casefold())
        mine = by_channel.get(label.casefold(), [])
        candidates = [_candidate_from_draft(draft, repo_url) for draft in mine]
        github = _depends_on_github(blog)
        failed = github and drafts_failed
        if str(blog.get("platform") or "") == "blogger" and str(blog.get("mode") or "draft") != "off":
            blogger = True           # 대략치가 나올 수 있는(정지가 아닌) Blogger 채널이 있을 때만 표 아래에 Blogger 안내 줄을 붙인다
            history = snap.histories.get(blog.get("key")) if isinstance(snap.histories, dict) else None
            if isinstance(history, list):
                candidates += [(moment[0], 0, _last_text(moment), True) for moment in history_drafts(history, now)]
            else:
                failed = True
        rows.append(_row_cells(_cell(ext(label, 30)), blog, candidates, now, failed))
        if github or mine:
            links += _filter_links(label, repo_url, blog.get("publish_flow") == "pr" or any(draft["kind"] == "pull" for draft in mine))
    extra = []
    for key in sorted(by_channel, key=lambda k: (k == "", k)):
        if key in known:
            continue
        group = by_channel[key]
        shown = f"{_cell(ext(group[0]['channel'], 30))} (미등록)" if key else "(채널 표시 없음)"
        extra.append((shown, group, group[0]["channel"] if key else None))
    room = max(BOARD_ROWS_MAX - len(rows), 1)
    for shown, group, raw_label in extra[:room - 1 if len(extra) > room else room]:
        rows.append(_row_cells(shown, None, [_candidate_from_draft(draft, repo_url) for draft in group], now, False))
        if raw_label:
            links += _filter_links(raw_label, repo_url, any(draft["kind"] == "pull" for draft in group))
    if len(extra) > room:
        rest = [draft for _shown, group, _label in extra[room - 1:] for draft in group]
        rows.append(_row_cells(f"그 밖의 채널 {len(extra) - room + 1}개", None, [_candidate_from_draft(draft, repo_url) for draft in rest], now, False))
    return rows, links, blogger


def draft_board(snap):
    """초안 현황 구역의 마크다운(`## 초안 현황` 부터). 보여 줄 채널이 하나도 없으면(레지스트리에 channel 이 없고 대기 초안도 없음) 빈 문자열.
    render() 의 board 인자로 넣는다. 같은 입력이면 항상 같은 글자다 — 점검 시각을 쓰지 않고 '가장 오래된'만 하루 단위 경과 일수로 바뀐다."""
    if not is_valid_repo(snap.repo):
        raise ValueError(f"저장소 이름 형식이 올바르지 않습니다: {snap.repo!r}")
    rows, links, blogger = board_rows(snap)
    if not rows:
        return ""
    repo_url = f"https://github.com/{snap.repo}"
    lines = ["## 초안 현황", "", "| " + " | ".join(BOARD_HEADER) + " |", "|" + "|".join("---" for _ in BOARD_HEADER) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    lines += ["", f"- {BOARD_NOTE_MODEL}"]
    if blogger:
        lines.append(f"- {BOARD_NOTE_BLOGGER}")
    shortcut = [("대기 초안 전체(이슈)", draft_filter_url(repo_url)), ("대기 초안 전체(PR)", draft_filter_url(repo_url, pulls=True))] + links
    parts = [f"[{text}]({url})" for text, url in shortcut if safe_url(url)]
    lines.append("- 휴대폰에서 거르기: " + " · ".join(parts))
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# 조회 실패·안내 / 전체 조립
# ----------------------------------------------------------------------------
def failure_items(failures, repo_url):
    """소스 조회가 실패하면 그 사실을 check 항목으로 남긴다(조용히 빠지면 '문제 없음'으로 오해한다)."""
    out = []
    for source, reason in failures:
        out.append(Item(
            id=f"source:{_slug(source)}", level=LEVEL_CHECK, title=f"조회 실패 — {SOURCE_LABELS.get(source) or ext(source, 30)}",
            detail=f"{ext(reason, 200)} (이번 점검에서는 이 부분을 확인하지 못했습니다)",
            url=f"{repo_url}/actions/workflows/{OWN_WORKFLOW}",
            hint="다음 점검에 다시 시도합니다. 계속되면 이 워크플로의 실행 로그를 확인하세요."))
    return out


def note_items(notes):
    return [Item(id=f"note:{_slug(note_id)}", level=LEVEL_INFO, title=ext(text, 160)) for note_id, text in notes]


def sort_items(items):
    """수준(action → check → info) → 오래된 것부터(since) → id 순. 입력 순서와 무관하게 항상 같은 결과."""
    return sorted(items, key=lambda i: (LEVELS.index(i.level), i.since is None, i.since.timestamp() if i.since else 0.0, i.id))


def build_items(snap):
    """Snapshot → 정렬된 항목 목록(같은 id 는 먼저 만든 것만 남긴다)."""
    if not is_valid_repo(snap.repo):
        raise ValueError(f"저장소 이름 형식이 올바르지 않습니다: {snap.repo!r}")
    repo_url = f"https://github.com/{snap.repo}"
    now = _aware(snap.now)
    items = (watchdog_items(snap.issues, repo_url) + pull_items(snap.pulls, now, repo_url)
             + run_items(snap.runs, snap.annotations, now, repo_url, names=snap.workflow_names)
             + approval_items(snap.approvals, repo_url, names=snap.workflow_names)
             + pause_items(snap.paused, repo_url) + blog_items(snap.blogs, snap.histories, now, repo_url)
             + stats_items(snap.blogs, snap.histories, now) + draft_items(snap.drafts, now, repo_url)
             + failure_items(snap.failures, repo_url) + note_items(snap.notes))
    unique, seen = [], set()
    for item in items:
        if item.id not in seen:
            seen.add(item.id)
            unique.append(item)
    return sort_items(unique)


# ----------------------------------------------------------------------------
# 렌더링·표식·새 알림 판정
# ----------------------------------------------------------------------------
def _item_block(item):
    lines = [f"- **{safe_text(item.title, TITLE_MAX)}**"]
    meta = [part for part in (safe_text(item.detail, DETAIL_MAX), f"{fmt_kst(item.since)}부터" if item.since else "") if part]
    if meta:
        lines.append("  - " + " · ".join(meta))
    url, hint = safe_url(item.url), safe_text(item.hint, HINT_MAX)
    if url:
        lines.append(f"  - ▶ [바로 하기]({url})" + (f" — {hint}" if hint else ""))
    elif hint:
        lines.append(f"  - 안내: {hint}")
    return "\n".join(lines) + "\n"


BOARD_OMITTED = "초안 현황은 길이 제한으로 줄였습니다. 실행 요약(Actions)에서 볼 수 있습니다."


def _board_text(board, used, limit, reserve):
    """초안 현황 구역(draft_board 의 마크다운)을 본문에 넣는 글. 남은 길이에 통째로 들어갈 때만 넣고, 안 들어가면 한 줄 안내로, 그것도 안 들어가면 넣지 않는다.
    표는 항목이 아니라 머리 바로 아래에 고정이라 항목을 줄일 때도 먼저 자리를 잡는다."""
    text = str(board or "").strip()
    if not text:
        return ""
    for candidate in (text + "\n\n", BOARD_OMITTED + "\n\n"):
        if used + len(candidate) + reserve <= limit:
            return candidate
    return ""


def render(items, repo_url, limit=BODY_LIMIT, board=""):
    """마크다운 본문(섹션: 지금 해야 할 일 / 확인하면 좋은 것 / 참고). 같은 항목이면 항상 같은 글자(시각·경과 시간을 넣지 않는다).
    board 가 있으면(draft_board 의 초안 현황 구역) 머리 바로 아래, 항목 구역들 앞에 넣는다. 없으면 이 인자가 생기기 전과 글자 하나 다르지 않다.
    길이가 limit 을 넘으면 뒤쪽 항목을 잘라 내고 몇 건을 줄였는지 한 줄로 알린다."""
    items = sort_items(list(items))
    counts = {level: sum(1 for i in items if i.level == level) for level in LEVELS}
    head = ["# 확인 필요 모음", ""]
    if not items:
        head.append(EMPTY_TEXT)
    else:
        head += [f"**지금 해야 할 일 {counts[LEVEL_ACTION]}건** · 확인하면 좋은 것 {counts[LEVEL_CHECK]}건 · 참고 {counts[LEVEL_INFO]}건", "",
                 "자동으로 모은 목록입니다. 해소되면 저절로 사라지고, 새로 해야 할 일이 생기면 코멘트로 알려 드립니다."]
    head_text = "\n".join(head) + "\n\n"
    doc_url = f"{repo_url}/blob/main/docs/OPS_INBOX.md"
    foot_text = ("\n---\n\n이 목록은 `[공통] 확인 필요 모음` 워크플로가 갱신합니다(2시간 간격으로 예약돼 있지만 GitHub 사정으로 보통 3~6시간마다 갱신됩니다. 직접 고쳐도 다음 갱신 때 덮어씁니다). "
                 "이 이슈는 공개입니다 — 비밀 값·수익·방문 수치는 싣지 않습니다. "
                 f"규칙·끄는 법: [docs/OPS_INBOX.md]({doc_url})\n")
    note_reserve = 200
    used = len(head_text) + len(foot_text)
    board_text = _board_text(board, used, limit, note_reserve)
    used += len(board_text)
    parts, last_level, shown = [], None, 0
    for item in items:
        block = ""
        if item.level != last_level:
            block += ("\n" if parts else "") + f"## {SECTION_TITLES[item.level]} ({counts[item.level]}건)\n\n"
        block += _item_block(item)
        if used + len(block) + note_reserve > limit:
            break
        parts.append(block)
        used += len(block)
        last_level = item.level
        shown += 1
    text = head_text + board_text + "".join(parts)
    if shown < len(items):
        text += f"\n… 외 {len(items) - shown}건은 길이 제한으로 줄였습니다. 실행 요약(Actions)에서 전체를 볼 수 있습니다.\n"
    return text + foot_text


@dataclass(frozen=True)
class Marker:
    hash: str
    items: tuple


_MARKER_RE = re.compile(r"<!--\s*ops-inbox:hash=([0-9a-f]{8,64});items=([a-z0-9_.:,]*)\s*-->")


def body_hash(visible):
    return hashlib.sha256(visible.encode("utf-8")).hexdigest()[:16]


def _marker_ids(ids):
    return tuple(sorted(set(ids))[:MARKER_IDS_MAX])


def make_marker(digest, ids):
    return f"<!-- ops-inbox:hash={digest};items={','.join(_marker_ids(ids))} -->"


def parse_marker(body):
    """본문 끝의 숨은 표식 → Marker(hash, items). 없거나 모양이 틀리면 None. 인용된 문구와 헷갈리지 않게 마지막 것을 쓴다."""
    matches = _MARKER_RE.findall(str(body or ""))
    if not matches:
        return None
    digest, ids = matches[-1]
    return Marker(digest, tuple(i for i in ids.split(",") if i))


def build_body(visible, ids):
    """이슈 본문 = 보이는 마크다운 + 숨은 표식(해시·알린 action id). 표식은 항상 맨 끝에 한 번만 붙인다."""
    return visible.rstrip() + "\n\n" + make_marker(body_hash(visible), ids) + "\n"


def needs_update(marker, visible, ids):
    """본문을 다시 써야 하나: 표식이 없거나, 보이는 본문의 해시나 알린 id 목록이 달라졌을 때만 True."""
    return marker is None or marker.hash != body_hash(visible) or marker.items != _marker_ids(ids)


def action_ids(items):
    return sorted(i.id for i in items if i.level == LEVEL_ACTION)


def plan_notice(items, previous_ids, failures=()):
    """(새로 알릴 action id 목록, 표식에 남길 id 목록).

    previous_ids 는 이전 표식의 id(표식이 없으면 None → 지금 있는 action 이 전부 '새 것').
    소스 조회가 실패한 때에는 그 소스의 이전 id 를 표식에 그대로 남긴다 — 조회 실패를 '해소됨'으로 오해했다가 복구 때
    같은 항목을 또 새 항목으로 알리지 않도록."""
    current = set(action_ids(items))
    previous = None if previous_ids is None else set(previous_ids)
    new = sorted(current if previous is None else current - previous)
    carried = set()
    if previous:
        prefixes = tuple(p for source, _reason in failures for p in SOURCE_PREFIXES.get(source, ()))
        if prefixes:
            carried = {i for i in previous if i.startswith(prefixes) and i not in current}
    return new, sorted(current | carried)


def comment_text(owner, items, issue_url=""):
    """새 action 항목 알림 코멘트(휴대폰 푸시용 @멘션). 항목 제목은 safe_text 를 거쳐 다른 사람을 멘션하지 못한다."""
    mention = f"@{owner} " if owner and _LOGIN_RE.fullmatch(str(owner)) else ""
    lines = [f"{mention}새로 해야 할 일이 {len(items)}건 생겼습니다."]
    lines += [f"- {safe_text(item.title, TITLE_MAX)}" for item in items[:COMMENT_ITEMS_MAX]]
    if len(items) > COMMENT_ITEMS_MAX:
        lines.append(f"- … 외 {len(items) - COMMENT_ITEMS_MAX}건")
    url = safe_url(issue_url)
    lines += ["", f"▶ [모아 보기]({url})" if url else "이슈 본문의 '▶ 바로 하기' 링크로 바로 처리할 수 있습니다."]
    return "\n".join(lines)
