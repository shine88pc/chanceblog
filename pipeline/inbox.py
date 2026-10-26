"""확인 필요 모음(운영 인박스) 규칙 — 순수 함수(I/O 없음: 네트워크 없이 테스트한다).

운영자가 해야 할 일·확인할 일을 한 목록으로 모은다. 입력은 Snapshot(열린 이슈·PR과 CI 상태, 워크플로 실행, 실행 주석,
환경 플래그, 블로그 레지스트리·이력, 조회 실패 기록), 출력은 Item 목록과 마크다운이다.
GitHub 읽기·쓰기와 이슈 관리는 scripts/ops_inbox.py 가 맡는다. 설명서: docs/OPS_INBOX.md

수준(level)
  action  지금 해야 할 일 — 사람이 손대야 풀린다(병합·승인·시크릿 등록·실패 원인 확인). 새로 생기면 코멘트(@멘션)로 알린다.
  check   확인하면 좋은 것 — 급하지 않거나 사실 확인이 필요한 것(경고·조회 실패·오래된 PR). 알림은 가지 않는다.
  info    참고 — 현황(블로그별 마지막 글 등)과 진행 중인 것.

보안: 외부에서 온 텍스트(PR 제목·주석 문구·이슈 제목·이력 사유)는 ext() 로 한 줄로 접고, 비밀 값 모양을 가리고, '@'·'<'·'&' 를
전각으로 바꾸고, 링크 문법 문자를 바꾸고, '::'·'##[' 를 풀어 쓴다. 렌더러는 한 번 더 같은 안전망(safe_text)을 거친다.
링크는 숫자 id 로 직접 만들며 API 가 준 URL 은 쓰지 않는다. 이 이슈는 공개 저장소의 공개 이슈이므로 수익·방문 수치와
비밀 값은 싣지 않는다(docs/SECURITY_GUARDRAILS.md G-O7).
"""
import hashlib
import re
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
    "history": "블로그 이력 파일", "registry": "블로그 레지스트리",
}
SOURCE_PREFIXES = {
    "issues": ("watchdog:",), "pulls": ("pr:",), "pull_details": ("pr:",), "runs": ("run:",),
    "approvals": ("approve:",), "history": ("blogger:",), "registry": ("blogger:",),
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
             + stats_items(snap.blogs, snap.histories, now) + failure_items(snap.failures, repo_url)
             + note_items(snap.notes))
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


def render(items, repo_url, limit=BODY_LIMIT):
    """마크다운 본문(섹션: 지금 해야 할 일 / 확인하면 좋은 것 / 참고). 같은 항목이면 항상 같은 글자(시각·경과 시간을 넣지 않는다).
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
    foot_text = ("\n---\n\n이 목록은 `확인 필요 모음` 워크플로가 갱신합니다(2시간 간격으로 예약돼 있지만 GitHub 사정으로 보통 3~6시간마다 갱신됩니다. 직접 고쳐도 다음 갱신 때 덮어씁니다). "
                 "이 이슈는 공개입니다 — 비밀 값·수익·방문 수치는 싣지 않습니다. "
                 f"규칙·끄는 법: [docs/OPS_INBOX.md]({doc_url})\n")
    note_reserve = 200
    used = len(head_text) + len(foot_text)
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
    text = head_text + "".join(parts)
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
