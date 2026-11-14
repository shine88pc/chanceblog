"""조건부 승인형 AI 병합 정책의 순수 함수 모음 — 운영자 확인 016 답(2026-11-15), 정책 정본 docs/AI_MERGE_POLICY.md.

**지금은 꺼져 있다.** 이 모듈은 어디서도 import 되지 않는다. AI 병합을 켜는 변경이 별도 병합 요청으로 들어와 운영자가 직접 병합하기 전까지 AI 는 병합하지 않는다.
표준 라이브러리 중 re 와 dataclasses 만 쓰고, 네트워크·파일 쓰기·환경 변수·시간·난수를 쓰지 않는다(tests/test_merge_policy_docs.py 가 정적으로 지킨다). 3.10 문법이다.
정책의 목록(AI 병합 가능 7종·운영자 전용 12항목·재확인 8조건·불허 문구 5개·완료 알림 7항목·시험 기준 6가지)은 모듈 상수이고, 문서와 시험이 같은 낱말을 못박는다.

원칙: 모호하면 승인 인정은 좁게, 운영자 전용은 넓게. 빠진 값·알 수 없는 값·해석할 수 없는 값은 언제나 실패(무효·운영자 전용) 쪽이다 — 없다고 통과로 보지 않는다.
이 파일을 바꾸는 변경은 그 자체로 운영자 전용이다(classify_change 의 policy_self) — 정책을 AI 가 스스로 느슨하게 만들 수 없게 한다.

흐름(docs/AI_MERGE_POLICY.md §3): AI 가 PR 작성 → 검사와 독립 검증 → 쉬운 병합 설명 발송 → 운영자가 병합 번호를 명시해 승인 → AI 가 승인된 PR 병합 → main 사후 검사 → 병합 완료 알림.
이 모듈이 맡는 것: 승인 글 읽기(parse_approval·check_approval_text) · 승인의 유효성(approval_matches·approval_still_valid·ApprovalLedger) · 변경 분류(classify_change) ·
병합 직전 재확인(check_preconditions) · 병합 방식 제한(merge_method_allowed) · 쉬운 병합 설명(render_explanation·explanation_problems) ·
병합 완료 알림(render_completion_notice·completion_notice_problems) · 첫 운영 3건 시험(evaluate_trial).
"""
import re
from dataclasses import dataclass

POLICY_DOC = "docs/AI_MERGE_POLICY.md"
REPO_KINDS = ("blog", "desktop")
TIER_AI_OK, TIER_OPERATOR_ONLY = "ai_ok", "operator_only"

# ---- 운영자 결정 원문(확인 016 답)의 목록 — 줄이거나 넓히지 않는다. 시험은 이 값을 글자 그대로 따로 적어 두고 대조한다 ------------------------------------
# AI 가 병합할 수 있는 범위(7종) — 분류 이름이 아니라 '운영자 전용 12항목에 안 걸리면 ai_ok' 라는 뜻으로 구현한다(classify_change).
AI_MERGE_SCOPES = ("일반 프로그램 코드", "일반 UI", "시험", "문서", "로컬 저장·조회", "오류 수정", "접근성·성능 개선")

# 승인해도 AI 가 직접 병합하지 않고 운영자 직접 병합으로 남는 12항목: (코드, 운영자 원문 낱말)
OPERATOR_ONLY_ITEMS = (
    ("workflow", "GitHub Actions Workflow"),
    ("ads", "광고·AdSense·ads.txt"),
    ("public_content", "공개 게시물과 고정 페이지"),
    ("pipeline_pause", "PIPELINE_PAUSE"),
    ("publish_mode", "발행 모드와 발행 재개"),
    ("provider_activation", "Provider 활성화"),
    ("credentials", "API Key·Secret·Credential"),
    ("dependencies", "의존성 추가"),
    ("data_deletion_migration", "데이터 삭제·Migration"),
    ("auto_publish", "자동 게시 활성화"),
    ("external_cost", "외부 비용 발생 기능"),
    ("branch_protection", "Main Branch 보호 설정"),
)
OPERATOR_ONLY_CODES = tuple(code for code, _label in OPERATOR_ONLY_ITEMS)
OPERATOR_ONLY_LABELS = tuple(label for _code, label in OPERATOR_ONLY_ITEMS)
_ITEM_LABELS = dict(OPERATOR_ONLY_ITEMS)
# 경로·내용으로 알아낼 수 없어 사람이 선언해야 하는 6항목(declared) — 참이거나 미응답이면 운영자 전용이다.
DECLARED_REQUIRED = ("data_deletion_migration", "external_cost", "auto_publish", "provider_activation", "publish_mode", "branch_protection")

# 승인 뒤에도 병합 직전에 다시 확인하는 8조건: (코드, 운영자 원문 낱말)
PRECONDITIONS = (
    ("number_match", "승인된 병합 번호와 PR 일치"),
    ("no_new_commit", "승인 이후 Commit 추가 없음"),
    ("checks_pass", "검사 전체 통과"),
    ("independent_verified", "독립 검증 통과"),
    ("no_conflict", "충돌 없음"),
    ("scope_matches", "변경 범위가 승인 설명과 일치"),
    ("no_secret_exposure", "비밀정보 노출 없음"),
    ("rollback_confirmed", "원복 방법 확인"),
)

# 이 글만으로는 병합 승인으로 보지 않는 표현 5개
REJECTED_PHRASES = ("확인했습니다", "진행하세요", "좋아 보입니다", "기본값대로", "다음 단계 진행")

# 병합 전 쉬운 설명 6항목(운영자 예시의 낱말)
EXPLANATION_ITEMS = ("무엇을 바꾸나요?", "왜 필요한가요?", "사용할 때 무엇이 달라지나요?", "위험은 무엇인가요?", "검사 결과", "되돌리기")

# 병합 완료 알림 필수 7항목
COMPLETION_ITEMS = ("병합 번호", "PR 번호", "병합된 Commit", "실제 반영된 변화", "main 검사 결과", "이상 유무", "원복 Commit 또는 원복 방법")

# 첫 운영 3건의 시험 기준 6가지: (기록의 키, 운영자 원문 낱말) — 기록의 값은 '충족했는가'(참이면 충족)다
TRIAL_CRITERIA = (
    ("approved_only", "승인받은 PR만 병합"),
    ("no_change_after_approval", "승인 후 변경 없음"),
    ("main_checks_passed", "main 검사 전체 통과"),
    ("no_revert", "원복 발생 0건"),
    ("no_wrong_merge", "다른 PR 오병합 0건"),
    ("no_operator_only_path_change", "운영자 전용 경로 변경 0건"),
)
TRIAL_SIZE = 3
TRIAL_CONTINUE, TRIAL_PENDING, TRIAL_STOP = "continue", "pending", "stop_immediately"

# ---- 운영자 결정 원문에 없는, 보수적으로 더한 표시(운영자 판단 필요 — docs/AI_MERGE_POLICY.md §7) -----------------------------------------------------
# policy_self: 이 정책의 파일 자체를 바꾸는 변경 · packaging_release: 데스크톱 앱의 VERSION·패키징 설정 · invalid_input: 입력을 확인할 수 없음
EXTRA_FLAGS = (
    ("policy_self", "병합 정책 자체"),
    ("packaging_release", "데스크톱 앱 패키징·배포 설정"),
    ("invalid_input", "입력을 확인할 수 없음"),
)
EXTRA_CODES = tuple(code for code, _label in EXTRA_FLAGS)
_EXTRA_LABELS = dict(EXTRA_FLAGS)
POLICY_SELF_FILES = ("docs/AI_MERGE_POLICY.md", "pipeline/merge_policy.py", "tests/test_merge_policy.py", "tests/test_merge_policy_docs.py")

# 문서 §7 의 규칙 표가 반드시 적어야 하는 경로·낱말(시험이 문서와 대조한다) — 아래 classify_change 의 규칙과 함께 고친다
DOCUMENTED_RULE_WORDS = (
    ".github/", "index.html", "_layouts/", "_includes/", "_config.yml", "ads.txt", "adsbygoogle", "ca-pub-",
    "_posts/", "about.md", "contact.md", "privacy.md", "categories.md", "pages.json", "assets/",
    "pipeline/blogs.json", "pipeline/source_registry.json", "pipeline/ops_inbox_policy.json",
    "requirements*.txt", "vendor/", "package*.json", "pyproject.toml", "Pipfile*", "*.lock",
    ".env*", "secrets.", "PIPELINE_PAUSE", "VERSION",
)

# ---- 병합 방식(§8) ---------------------------------------------------------------------------------------------------------------------------------------
ALLOWED_MERGE_METHOD = "pr_merge"
FORBIDDEN_MERGE_METHODS = ("push_main", "direct_push", "force_push")

# ---- 승인 글 -----------------------------------------------------------------------------------------------------------------------------------------------
APPROVAL_EXAMPLE = "M075 승인"
APPROVAL_GUIDE_LINE = "승인 방식은 반드시 병합 번호와 함께 사용해 주세요."
AI_MERGE_OFF_NOTICE = "지금은 AI 병합 기능이 꺼져 있어 운영자께서 직접 병합해 주세요."
AI_MERGE_ON_NOTICE = "승인하시면 AI 가 이 PR 한 건만 PR 병합으로 병합합니다. main 에 직접 push 하지 않습니다."

# 병합 번호 = pipeline.notify.NOTICE_NO_RE 의 숫자 부분과 같은 값(앞에 0 을 더 붙인 네 자리와 000 은 번호가 아니다) + 접두어 M. 같은 값임은 시험이 못박는다.
MERGE_NUMBER_DIGITS = r"(?:(?!000)[0-9]{3}|[1-9][0-9]{3})"
MERGE_NUMBER_RE = re.compile("M" + MERGE_NUMBER_DIGITS)       # 쓸 때는 fullmatch
_ASCII_SPACE = " \t\r\n"
APPROVAL_TEXT_MAX = 2000
# 글 전체가 'M### 승인'(번호 뒤 공백 하나 이상, 끝의 마침표 하나는 허용)일 때만 승인이다 — 소문자 m 은 받아 대문자로 돌려준다
_APPROVAL_RE = re.compile(r"[Mm](" + MERGE_NUMBER_DIGITS + r")[ \t]+승인\.?")
_NUMBER_LIKE_RE = re.compile(r"(?<![A-Za-z0-9])[Mm][0-9]+(?![A-Za-z0-9])")
_APPROVAL_GUIDE = "병합 승인은 병합 번호와 함께 한 줄로 `" + APPROVAL_EXAMPLE + "` 처럼 보내 주세요."
APPROVAL_REASONS = ("ok", "empty", "rejected_phrase", "no_number", "several_numbers", "bad_number", "not_exact_form")


@dataclass(frozen=True)
class ApprovalCheck:
    """승인 글 읽기 결과. number 는 승인이면 `M075`(대문자), 아니면 None. reason 은 APPROVAL_REASONS 중 하나, guidance 는 승인이 아닐 때 다시 보낼 정확한 형태 안내(쉬운 말)다."""
    number: object
    reason: str
    guidance: str


def check_approval_text(text):
    """승인 글을 읽어 번호와 이유·안내를 돌려준다. 승인은 글 전체가 `M###` 한 개 + 공백 + `승인` 일 때뿐이다(앞뒤 공백·끝의 마침표 허용, M 대소문자 무시, 번호는 M + 숫자 세 자리 또는 네 자리).
    불허 문구 5개만 있는 글·번호 없는 승인·번호가 둘 이상인 글·번호 뒤에 다른 말이 붙은 글·다른 문장 속에 섞인 번호·표준이 아닌 번호(M75·M0075·M000)는 모두 승인이 아니다 —
    모호하면 거절하고 정확한 형태를 다시 안내한다(guidance)."""
    if not isinstance(text, str) or not text.strip(_ASCII_SPACE):
        return ApprovalCheck(None, "empty", "승인 글이 비어 있습니다. " + _APPROVAL_GUIDE)
    body = text.strip(_ASCII_SPACE)
    if len(body) > APPROVAL_TEXT_MAX:
        return ApprovalCheck(None, "not_exact_form", "승인 글이 너무 깁니다. " + _APPROVAL_GUIDE)
    match = _APPROVAL_RE.fullmatch(body)
    if match is not None:
        return ApprovalCheck("M" + match.group(1), "ok", "")
    numbers = _NUMBER_LIKE_RE.findall(body)
    if len(numbers) >= 2:
        return ApprovalCheck(None, "several_numbers", "번호가 둘 이상 들어 있어 어느 병합인지 알 수 없습니다. " + _APPROVAL_GUIDE)
    if len(numbers) == 1:
        if MERGE_NUMBER_RE.fullmatch(numbers[0].upper()) is None:
            return ApprovalCheck(None, "bad_number", "번호가 표준 모양이 아닙니다(M 뒤에 세 자리 또는 네 자리 숫자, 앞에 0 을 더 붙이지 않습니다). " + _APPROVAL_GUIDE)
        return ApprovalCheck(None, "not_exact_form", "승인 글이 정해진 한 줄 모양과 다릅니다(번호 뒤에 한 칸을 띄우고 승인 한 낱말만, 다른 말은 붙이지 않습니다). " + _APPROVAL_GUIDE)
    if any(phrase in body for phrase in REJECTED_PHRASES):
        return ApprovalCheck(None, "rejected_phrase", "'확인했습니다'·'진행하세요' 같은 말만으로는 병합 승인으로 보지 않습니다. " + _APPROVAL_GUIDE)
    if "승인" in body:
        return ApprovalCheck(None, "no_number", "승인에 병합 번호가 없습니다. " + _APPROVAL_GUIDE)
    return ApprovalCheck(None, "not_exact_form", "병합 승인으로 읽을 수 없는 글입니다. " + _APPROVAL_GUIDE)


def parse_approval(text):
    """승인 글 → 병합 번호(`M075`) 또는 None. 규칙은 check_approval_text 와 같다."""
    return check_approval_text(text).number


# ---- 값 읽기 도우미 -----------------------------------------------------------------------------------------------------------------------------------------
def _standard_label(value):
    """표준 병합 번호(`M075`·`M1000`, 대문자 M)면 그대로, 아니면 None."""
    return value if isinstance(value, str) and MERGE_NUMBER_RE.fullmatch(value) is not None else None


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


_SHA_RE = re.compile(r"[0-9a-fA-F]{40}")


def _sha(value):
    """40자 16진 해시면 소문자로, 아니면 None."""
    return value.lower() if isinstance(value, str) and _SHA_RE.fullmatch(value) is not None else None


def normalize_path(raw):
    """저장소 안 상대 경로를 '/' 로 통일해 돌려준다. 글자가 아니거나·비었거나·절대 경로(앞 '/'·드라이브 글자)이거나·제어 문자가 있거나·`..` 구간이 있으면 None(확인할 수 없는 입력)."""
    if not isinstance(raw, str):
        return None
    text = raw.strip().replace("\\", "/")
    if not text or text.startswith("/") or re.match(r"[A-Za-z]:", text) or any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        return None
    parts = []
    for segment in text.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            return None
        parts.append(segment)
    return "/".join(parts) if parts else None


def _path_set(paths):
    """경로 목록 → 정규화한 경로의 frozenset. 목록이 아니거나(글자 하나·None 포함) 올바르지 않은 경로가 하나라도 있으면 None."""
    if paths is None or isinstance(paths, (str, bytes)):
        return None
    try:
        items = list(paths)
    except TypeError:
        return None
    found = set()
    for item in items:
        normal = normalize_path(item)
        if normal is None:
            return None
        found.add(normal)
    return frozenset(found)


def _clip(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---- 승인의 유효성 -------------------------------------------------------------------------------------------------------------------------------------------
_TITLE_TAG_RE = re.compile(r"\[[Mm][0-9]+\]")


def pr_title_label(title):
    """PR 제목의 병합 번호 — 제목이 맨 앞의 `[M075]` 로 시작하고 `[M###]` 꼴 태그가 정확히 하나일 때만 `M075`, 아니면 None(태그가 둘이면 어느 병합인지 모호하다)."""
    if not isinstance(title, str):
        return None
    tags = _TITLE_TAG_RE.findall(title)
    if len(tags) != 1 or not title.startswith(tags[0]):
        return None
    return _standard_label(tags[0][1:-1])


def approval_matches(approved_number, pr_number_label):
    """승인된 병합 번호와 PR 의 병합 번호(제목의 `[M###]`)가 표준 모양이면서 정확히 같은가. 대소문자·공백을 고쳐 읽지 않는다(승인 글은 parse_approval 이 대문자로 돌려준다)."""
    approved = _standard_label(approved_number)
    return approved is not None and approved == _standard_label(pr_number_label)


def approval_still_valid(approved_head_sha, current_head_sha, approved_paths, current_paths):
    """승인 뒤에도 승인이 유효한가 — 머리 커밋(40자 해시)이 같고 변경 파일 목록이 같아야 한다. 승인 뒤 커밋이 더해졌거나 목록이 달라졌거나 값이 올바르지 않으면(빈 목록 포함) False."""
    approved_sha, current_sha = _sha(approved_head_sha), _sha(current_head_sha)
    if approved_sha is None or current_sha is None or approved_sha != current_sha:
        return False
    approved_set, current_set = _path_set(approved_paths), _path_set(current_paths)
    return approved_set is not None and current_set is not None and len(approved_set) > 0 and approved_set == current_set


@dataclass(frozen=True)
class Decision:
    ok: bool
    reason: str


class ApprovalLedger:
    """승인은 PR 한 건에만 유효하다 — 이미 쓴 승인(병합 번호)과 이미 승인으로 처리한 PR 을 다시 쓰려는 시도를 거절하는 메모리 안 기록(파일·시계 없음).
    켜는 변경이 이 기록을 저장소 밖에 따로 두지 않고 병합된 PR 이력에서 다시 만들어 넣는다(consumed)."""

    def __init__(self, consumed=()):
        self._numbers = set()
        self._prs = set()
        try:
            pairs = [(number, pr_number) for number, pr_number in consumed]
        except (TypeError, ValueError):
            raise ValueError("consumed") from None
        for number, pr_number in pairs:
            if _standard_label(number) is None or not _positive_int(pr_number):
                raise ValueError("consumed")
            self._numbers.add(number)
            self._prs.add(pr_number)

    @property
    def consumed_numbers(self):
        return tuple(sorted(self._numbers))

    def consume(self, number, pr_number):
        """승인을 한 번 쓴다. 번호가 표준이 아니거나·PR 번호가 양의 정수가 아니거나·이미 쓴 번호이거나·이미 승인으로 처리한 PR 이면 거절(Decision.ok 가 False)하고 기록을 바꾸지 않는다."""
        if _standard_label(number) is None:
            return Decision(False, "승인 번호가 표준 모양(M 뒤에 세 자리 또는 네 자리 숫자)이 아닙니다")
        if not _positive_int(pr_number):
            return Decision(False, "PR 번호가 양의 정수가 아닙니다")
        if number in self._numbers:
            return Decision(False, "이미 한 번 쓴 승인입니다 — 승인은 PR 한 건에만 유효하며 다른 PR 이나 이후 변경에 다시 쓸 수 없습니다")
        if pr_number in self._prs:
            return Decision(False, "이 PR 은 이미 다른 승인으로 병합 처리되었습니다 — 새 설명과 새 승인을 받아야 합니다")
        self._numbers.add(number)
        self._prs.add(pr_number)
        return Decision(True, "")


# ---- 변경 분류 ----------------------------------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Classification:
    """classify_change 의 결과. tier 는 `ai_ok` 또는 `operator_only`, categories 는 걸린 운영자 전용 12항목의 코드(정책 순서), extra_flags 는 12항목 밖의 보수적 표시, reasons 는 쉬운 말 이유,
    paths 는 분류한 정규화 경로(병합 직전 재확인이 '분류가 지금 변경 파일로 계산됐는지' 대조한다)."""
    tier: str
    categories: tuple
    extra_flags: tuple
    reasons: tuple
    paths: tuple

    @property
    def operator_only(self):
        return self.tier == TIER_OPERATOR_ONLY

    def to_dict(self):
        return {"tier": self.tier, "categories": list(self.categories), "extra_flags": list(self.extra_flags),
                "reasons": list(self.reasons), "paths": list(self.paths)}

    def __getitem__(self, key):
        """`result["tier"]` 처럼 사전 모양으로도 읽을 수 있다(키는 to_dict 와 같다)."""
        return self.to_dict()[key]


# 경로 규칙 — 이름은 모두 소문자로 접어(casefold) 비교한다. 규칙을 바꾸면 DOCUMENTED_RULE_WORDS 와 문서 §7 도 같이 고친다.
_DEPENDENCY_BASE_RE = re.compile(r"(?:requirements|constraints)[^/]*\.txt|package[^/]*\.json|pnpm-lock\.yaml|pyproject\.toml|setup\.py|setup\.cfg|pipfile[^/]*|gemfile[^/]*|[^/]*\.lock")
_CRED_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".ppk", ".kdbx")
_CRED_BASE_RE = re.compile(r"\.env.*|\.netrc|\.npmrc|\.pypirc|id_(?:rsa|dsa|ecdsa|ed25519).*|client_secret.*\.json|token[^/]*\.json|.*service[-_]?account.*")
_CRED_WORDS = ("secret", "credential", "keystore", "keyring")
_ADS_FILES = frozenset({"ads.txt", "app-ads.txt", "index.html", "_config.yml"})
_ADS_DIRS = frozenset({"_layouts", "_includes"})
_PUBLIC_DIRS = frozenset({"_posts", "_blogger_drafts", "_blogger_ko_drafts", "_naver_drafts"})
_PUBLIC_ROOT_FILES = frozenset({"about.md", "contact.md", "privacy.md", "categories.md", "pages.json", "posts.json", "feed.xml", "robots.txt",
                                "history.json", "blogger_history.json", "blogger_ko_history.json", "naver_history.json"})
_BLOG_SETTINGS = {
    "pipeline/blogs.json": ("publish_mode", "auto_publish", "ads"),
    "pipeline/source_registry.json": ("provider_activation",),
    "pipeline/ops_inbox_policy.json": ("pipeline_pause", "publish_mode"),
}
_PACKAGING_FILES = frozenset({"version", "version.txt", "manifest.in"})
_PACKAGING_SUFFIXES = (".spec", ".iss", ".nsi", ".wxs", ".wixproj", ".msix", ".msi", ".appxmanifest", ".manifest", ".rc")
_PACKAGING_DIRS = frozenset({"packaging", "installer", "installers", "package", "release", "releases", "dist", "build", "pyinstaller", "nsis", "msix", "wix"})
_POLICY_SELF_FOLDED = frozenset(name.casefold() for name in POLICY_SELF_FILES)

# 내용 규칙(추가된 줄의 글) — 대소문자를 가리지 않는다. 정규식 안의 단어 경계는 look-around 로 쓴다.
_ADS_TEXT_RE = re.compile(r"adsbygoogle|ca-pub-", re.I)
_PAUSE_TEXT_RE = re.compile(r"PIPELINE_PAUSE", re.I)
_DESTRUCTIVE_TEXT_RE = re.compile(
    r"(?<![A-Za-z0-9_])drop\s+(?:table|database|schema)(?![A-Za-z0-9_])|(?<![A-Za-z0-9_])delete\s+from(?![A-Za-z0-9_])|(?<![A-Za-z0-9_])truncate\s+table(?![A-Za-z0-9_])"
    r"|rmtree|마이그레이션|(?<![A-Za-z0-9_])migrat(?:e|es|ed|ing|ion|ions)(?![A-Za-z0-9_])", re.I)
_SECRETS_REF_RE = re.compile(r"(?<![A-Za-z0-9_])secrets\s*(?:\.|\[)")
# 비밀 값의 모양(저장소 검증기의 패턴과 같은 종류를 이 모듈 안에 따로 둔다 — 그 단일 원천 모듈은 소비처 목록 시험이 있어 import 하지 않는다)
_SECRET_VALUE_RES = (
    ("Google API 키 모양", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Google API 키(새 형식) 모양", re.compile(r"(?<![A-Za-z0-9])AQ\.[0-9A-Za-z_\-]{40,}")),
    ("Google OAuth 클라이언트 비밀 모양", re.compile(r"GOCSPX-[0-9A-Za-z_\-]{20,}")),
    ("Google refresh 토큰 모양", re.compile(r"(?<![A-Za-z0-9_])1//0[0-9A-Za-z_\-]{40,}")),
    ("Google access 토큰 모양", re.compile(r"(?<![A-Za-z0-9_])ya29\.[0-9A-Za-z_\-]{30,}")),
    ("GitHub 토큰 모양", re.compile(r"(?<![A-Za-z0-9_])gh[pousr]_[0-9A-Za-z]{36,}")),
    ("GitHub PAT 모양", re.compile(r"(?<![A-Za-z0-9_])github_pat_[0-9A-Za-z_]{40,}")),
    ("개인 키 블록", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----")),
    ("Slack 토큰 모양", re.compile(r"(?<![A-Za-z0-9_])xox[baprs]-[0-9A-Za-z\-]{10,}")),
    ("AWS 액세스 키 모양", re.compile(r"(?<![A-Za-z0-9_])AKIA[0-9A-Z]{16}(?![A-Za-z0-9_])")),
    ("Telegram 봇 토큰 모양", re.compile(r"[0-9]{6,12}:[A-Za-z0-9_\-]{30,50}(?![A-Za-z0-9_\-])")),
    ("sk- 형식 API 키 모양", re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9]{32,}(?![A-Za-z0-9_])")),
    ("긴 값을 넣는 키·토큰 할당", re.compile(r"""(?i)(?<![A-Za-z0-9_])(?:api[_-]?key|secret|token|passwd|password)(?![A-Za-z0-9_])\s*[:=]\s*['"][A-Za-z0-9_\-/+=]{24,}['"]""")),
)
# 키·토큰·비밀번호 같은 낱말(이름 포함) — 복수형 tokens·tokenizer 같은 낱말은 걸리지 않는다
_CRED_WORD_RE = re.compile(
    r"api[ _-]?key|secret|passw(?:or)?d|credential|private[ _-]?key|access[ _-]?key|token(?![A-Za-z0-9])"
    r"|비밀번호|비밀 번호|시크릿|비밀 키|API 키|자격 증명|자격증명|인증 정보|인증정보|접근 키|액세스 키|접근 토큰|봇 토큰|인증 토큰|액세스 토큰", re.I)
_REASON_CAP = 40


def _tag(code):
    """이유 앞에 붙이는 항목 이름(운영자 전용 12항목의 원문 낱말 또는 보수적 표시의 이름)."""
    return _ITEM_LABELS.get(code) or _EXTRA_LABELS.get(code, code)


def _shown(path):
    if any(rx.search(path) for _label, rx in _SECRET_VALUE_RES):
        return "(경로에 비밀 모양이 있어 가렸습니다)"
    return path if len(path) <= 80 else path[:77] + "..."


def _path_findings(repo_kind, path):
    """경로 한 개가 걸리는 규칙: [(코드, 쉬운 말 이유)] — 코드는 운영자 전용 12항목 코드 또는 EXTRA_CODES."""
    segments = [part.casefold() for part in path.split("/")]
    base = segments[-1]
    found = []
    if ".github" in segments:
        found.append(("workflow", "GitHub Actions Workflow 폴더(.github)의 파일입니다"))
    if "vendor" in segments or "node_modules" in segments or _DEPENDENCY_BASE_RE.fullmatch(base) is not None:
        found.append(("dependencies", "의존성 목록·잠금 파일이거나 vendor 폴더의 파일입니다"))
    if base.endswith(_CRED_SUFFIXES) or _CRED_BASE_RE.fullmatch(base) is not None or "security" in segments or any(word in part for part in segments for word in _CRED_WORDS):
        found.append(("credentials", "키·비밀·자격 증명과 관련된 파일 이름입니다"))
    if path.casefold() in _POLICY_SELF_FOLDED:
        found.append(("policy_self", "병합 정책의 문서·모듈·시험 자체입니다(정책은 운영자 결정으로만 바뀝니다)"))
    if repo_kind == "blog":
        if base in _ADS_FILES or any(part in _ADS_DIRS for part in segments):
            found.append(("ads", "광고 표면 파일(index.html·_layouts/·_includes/·_config.yml·ads.txt)입니다"))
        if any(part in _PUBLIC_DIRS for part in segments) or segments[0] == "assets" or (len(segments) == 1 and (base in _PUBLIC_ROOT_FILES or base.endswith((".html", ".htm")))):
            found.append(("public_content", "공개 게시물·고정 페이지·사이트 공개 파일입니다"))
        for code in _BLOG_SETTINGS.get("/".join(segments), ()):
            found.append((code, "발행 설정 파일(pipeline/blogs.json·source_registry.json·ops_inbox_policy.json)입니다"))
    elif repo_kind == "desktop":
        if base in _PACKAGING_FILES or base.endswith(_PACKAGING_SUFFIXES) or any(part in _PACKAGING_DIRS for part in segments):
            found.append(("packaging_release", "데스크톱 앱의 VERSION·패키징·배포 설정입니다"))
    return found


def _text_findings(text):
    """추가된 줄의 글이 걸리는 규칙: [(코드, 쉬운 말 이유)]. 걸린 글 자체는 이유에 싣지 않는다(비밀이 새지 않게)."""
    found = []
    if _ADS_TEXT_RE.search(text):
        found.append(("ads", "광고 코드 낱말(adsbygoogle·ca-pub-)이 있습니다"))
    if _PAUSE_TEXT_RE.search(text):
        found.append(("pipeline_pause", "발행 정지 변수 이름(PIPELINE_PAUSE)이 있습니다"))
    if _DESTRUCTIVE_TEXT_RE.search(text):
        found.append(("data_deletion_migration", "데이터를 지우는 명령이나 마이그레이션 낱말이 있습니다"))
    for label, rx in _SECRET_VALUE_RES:
        if rx.search(text):
            found.append(("credentials", "비밀 모양의 값이 있습니다(" + label + ")"))
    if _SECRETS_REF_RE.search(text):
        found.append(("credentials", "secrets. 참조가 있습니다"))
    if _CRED_WORD_RE.search(text):
        found.append(("credentials", "키·토큰·비밀번호·자격 증명 같은 낱말이 있습니다"))
    return found


def _added_text_value(value):
    """added_text 는 글자 하나(빈 글 가능) 또는 {경로: 글} 사전이다. 그 밖이면 None(읽을 수 없음)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and all(isinstance(item, str) for item in value.values()):
        return "\n".join(value.values())
    return None


def classify_change(repo_kind, changed_paths, added_text, declared=None):
    """변경을 `ai_ok`(AI 병합 가능) 또는 `operator_only`(운영자 직접 병합)로 분류한다 — 운영자 전용 12항목에 하나도 안 걸리고 입력을 모두 확인할 수 있을 때만 ai_ok 다.
    repo_kind: `'blog'` 또는 `'desktop'`. changed_paths: 바뀐 경로 목록(이름 바꾸기는 옛 경로와 새 경로를 모두, 삭제도 포함). added_text: 추가된 줄의 글(글자 하나 또는 {경로: 글}).
    declared: 사람이 선언하는 항목 {코드: 참/거짓/None}. DECLARED_REQUIRED 6항목은 거짓이어야 통과이고 참이거나 미응답(없음·None·해석할 수 없는 값)이면 운영자 전용이다.
    경로·내용 규칙에 걸린 항목은 declared 가 거짓이어도 운영자 전용이다. 입력이 올바르지 않으면(저장소 종류·경로 목록·글·알 수 없는 선언 항목) 예외 없이 operator_only(invalid_input)로 돌려준다."""
    categories, extras = set(), set()
    notes = {}                       # (코드, 이유) -> 경로 목록(경로 규칙) — 같은 이유는 한 줄로 묶는다
    plain = []                       # (코드, 이유) — 내용·선언·입력 문제

    def add_plain(code, why):
        (extras if code in _EXTRA_LABELS else categories).add(code)
        if (code, why) not in plain:
            plain.append((code, why))

    kind_ok = isinstance(repo_kind, str) and repo_kind in REPO_KINDS
    if not kind_ok:
        add_plain("invalid_input", "저장소 종류가 blog 나 desktop 이 아니라 분류할 수 없습니다")
    paths = _path_set(changed_paths)
    if paths is None:
        add_plain("invalid_input", "변경 파일 목록의 모양이 올바르지 않습니다(글자 목록이어야 하고 .. 구간이 든 경로·절대 경로는 안 됩니다)")
        paths = frozenset()
    elif not paths:
        add_plain("invalid_input", "변경 파일 목록이 비어 있습니다")
    for path in sorted(paths):
        for code, why in _path_findings(repo_kind if kind_ok else "", path):
            (extras if code in _EXTRA_LABELS else categories).add(code)
            notes.setdefault((code, why), []).append(path)
    text = _added_text_value(added_text)
    if text is None:
        add_plain("invalid_input", "추가된 줄의 글을 읽을 수 없습니다(글자여야 합니다)")
    else:
        for code, why in _text_findings(text):
            add_plain(code, "추가된 줄 — " + why)
    given = {} if declared is None else declared
    if not isinstance(given, dict):
        add_plain("invalid_input", "선언 항목의 모양이 올바르지 않습니다(사전이어야 합니다)")
    else:
        if any(key not in _ITEM_LABELS for key in given):
            add_plain("invalid_input", "선언 항목에 알 수 없는 이름이 있습니다")
        for code, label in OPERATOR_ONLY_ITEMS:
            value = given.get(code)
            if code in DECLARED_REQUIRED:
                if value is False:
                    continue
                state = "참" if value is True else ("미응답" if value is None else "해석할 수 없는 값")
                add_plain(code, "선언 — " + label + ": " + state + "(참이거나 미응답이면 운영자 전용)")
            elif value is not None and value is not False:
                add_plain(code, "선언 — " + label + ": 참")
    reasons = ["[" + _tag(code) + "] " + why for code, why in plain]
    for (code, why), listed in notes.items():
        shown = ", ".join(_shown(item) for item in listed[:3]) + (" 외 " + str(len(listed) - 3) + "개" if len(listed) > 3 else "")
        reasons.append("[" + _tag(code) + "] " + why + ": " + shown)
    ordered_categories = tuple(code for code in OPERATOR_ONLY_CODES if code in categories)
    ordered_extras = tuple(code for code in EXTRA_CODES if code in extras)
    tier = TIER_OPERATOR_ONLY if ordered_categories or ordered_extras else TIER_AI_OK
    return Classification(tier, ordered_categories, ordered_extras, tuple(reasons[:_REASON_CAP]), tuple(sorted(paths)))


def _coerce_classification(value):
    """Classification 이거나 to_dict 모양의 사전이면 Classification, 아니면 None(키가 빠졌거나 모양이 다르면 None)."""
    if isinstance(value, Classification):
        return value
    if not isinstance(value, dict):
        return None
    try:
        tier, categories, extra_flags, paths = value["tier"], tuple(value["categories"]), tuple(value["extra_flags"]), tuple(value["paths"])
        reasons = tuple(value.get("reasons", ()))
    except (KeyError, TypeError):
        return None
    if tier not in (TIER_AI_OK, TIER_OPERATOR_ONLY) or not all(isinstance(item, str) for item in categories + extra_flags + paths + reasons):
        return None
    return Classification(tier, categories, extra_flags, reasons, paths)


# ---- 병합 직전 재확인 8조건 ------------------------------------------------------------------------------------------------------------------------------------
FACT_KEYS = (
    "approved_number", "approved_pr_number", "pr_number", "pr_title_label", "consumed_numbers",
    "approved_head_sha", "current_head_sha", "current_tree", "approved_paths", "current_paths",
    "checks", "independent_verification", "has_conflict", "classification", "secret_findings", "rollback_method",
)
VERIFICATION_KEYS = ("verdict", "verifier", "implementer", "verified_tree", "open_required_findings")
ROLLBACK_MIN_CHARS = 10
_ROLLBACK_PLACEHOLDERS = frozenset({"없음", "해당 없음", "없다", "미정", "모름", "tbd", "n/a", "na", "-", "?"})


@dataclass(frozen=True)
class Failure:
    code: str
    name: str
    reason: str


@dataclass(frozen=True)
class Verdict:
    """check_preconditions 의 결과 — failures 가 비어 있어야 ok 다(8조건 모두 통과)."""
    ok: bool
    failures: tuple

    @property
    def failed_codes(self):
        return tuple(item.code for item in self.failures)

    def explain(self):
        return [item.name + ": " + item.reason for item in self.failures]


def _need(facts, *keys):
    absent = [key for key in keys if facts.get(key) is None]
    return ("필요한 값이 없습니다: " + ", ".join(absent)) if absent else None


def _label_shown(value):
    return value if _standard_label(value) is not None else "(표준 모양이 아닌 값)"


def _c_number_match(facts):
    problem = _need(facts, "approved_number", "approved_pr_number", "pr_number", "pr_title_label", "consumed_numbers")
    if problem:
        return problem
    approved, label = facts["approved_number"], facts["pr_title_label"]
    if _standard_label(approved) is None:
        return "승인된 병합 번호가 표준 모양(M 뒤에 세 자리 또는 네 자리 숫자)이 아닙니다"
    if not approval_matches(approved, label):
        return "승인된 번호(" + approved + ")와 PR 제목의 번호(" + _label_shown(label) + ")가 다릅니다"
    approved_pr, pr_number = facts["approved_pr_number"], facts["pr_number"]
    if not (_positive_int(approved_pr) and _positive_int(pr_number)):
        return "PR 번호가 양의 정수가 아닙니다"
    if approved_pr != pr_number:
        return "승인할 때 설명한 PR(#" + str(approved_pr) + ")과 지금 병합하려는 PR(#" + str(pr_number) + ")이 다릅니다"
    consumed = facts["consumed_numbers"]
    if not isinstance(consumed, (list, tuple, set, frozenset)) or any(_standard_label(item) is None for item in consumed):
        return "이미 쓴 승인 기록의 모양이 올바르지 않습니다(표준 병합 번호의 목록이어야 합니다)"
    if approved in consumed:
        return "이미 한 번 쓴 승인입니다 — 승인은 PR 한 건에만 유효합니다"
    return None


def _c_no_new_commit(facts):
    problem = _need(facts, "approved_head_sha", "current_head_sha")
    if problem:
        return problem
    approved, current = _sha(facts["approved_head_sha"]), _sha(facts["current_head_sha"])
    if approved is None or current is None:
        return "머리 커밋 값이 올바른 40자 해시가 아닙니다"
    if approved != current:
        return "승인한 뒤에 커밋이 더해지거나 바뀌었습니다(승인 때 " + approved[:7] + ", 지금 " + current[:7] + ")"
    return None


def _c_checks_pass(facts):
    problem = _need(facts, "checks")
    if problem:
        return problem
    checks = facts["checks"]
    if not isinstance(checks, (list, tuple)) or not checks:
        return "검사 결과가 하나도 없습니다(검사가 없으면 통과가 아닙니다)"
    bad = []
    for item in checks:
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not name.strip():
            bad.append("(이름 없는 검사)")
        elif item.get("conclusion") != "success":
            bad.append(_clip(name, 40))
    if bad:
        return "통과하지 않은 검사가 있습니다: " + ", ".join(bad[:5]) + (" 외 " + str(len(bad) - 5) + "개" if len(bad) > 5 else "")
    return None


def _c_independent(facts):
    problem = _need(facts, "independent_verification", "current_tree")
    if problem:
        return problem
    record = facts["independent_verification"]
    if not isinstance(record, dict):
        return "독립 검증 기록의 모양이 올바르지 않습니다"
    absent = [key for key in VERIFICATION_KEYS if record.get(key) is None]
    if absent:
        return "독립 검증 기록에 없는 값이 있습니다: " + ", ".join(absent)
    if record["verdict"] != "pass":
        return "독립 검증 결과가 통과(pass)가 아닙니다"
    verifier, implementer = record["verifier"], record["implementer"]
    if not isinstance(verifier, str) or not isinstance(implementer, str) or not verifier.strip() or not implementer.strip():
        return "검증자나 구현자 이름이 비어 있습니다"
    if verifier.strip().casefold() == implementer.strip().casefold():
        return "검증자와 구현자가 같습니다(독립 검증이 아닙니다)"
    open_findings = record["open_required_findings"]
    if not _non_negative_int(open_findings):
        return "남은 필수 지적 수가 올바른 숫자가 아닙니다"
    if open_findings != 0:
        return "필수 지적이 " + str(open_findings) + "건 남아 있습니다"
    verified, current = _sha(record["verified_tree"]), _sha(facts["current_tree"])
    if verified is None or current is None:
        return "트리 해시가 올바른 40자 값이 아닙니다"
    if verified != current:
        return "독립 검증한 내용과 지금 병합하려는 내용(트리)이 다릅니다"
    return None


def _c_no_conflict(facts):
    value = facts.get("has_conflict")
    if value is False:
        return None
    if value is True:
        return "main 과 충돌이 있습니다"
    return "충돌 여부를 알 수 없습니다(값이 없거나 참·거짓이 아닙니다)"


def _c_scope(facts):
    problem = _need(facts, "approved_paths", "current_paths", "classification")
    if problem:
        return problem
    approved, current = _path_set(facts["approved_paths"]), _path_set(facts["current_paths"])
    if not approved or not current:
        return "변경 파일 목록이 올바르지 않거나 비어 있습니다"
    if approved != current:
        return "승인할 때 설명한 파일 목록과 지금 변경 파일이 다릅니다(새로 생긴 파일 " + str(len(current - approved)) + "개, 빠진 파일 " + str(len(approved - current)) + "개)"
    classified = _coerce_classification(facts["classification"])
    if classified is None:
        return "변경 분류 결과의 모양이 올바르지 않습니다"
    if frozenset(classified.paths) != current:
        return "변경 분류가 지금 변경 파일 목록으로 계산되지 않았습니다(낡은 분류)"
    if classified.tier != TIER_AI_OK or classified.categories or classified.extra_flags:
        names = [_ITEM_LABELS.get(code) or _EXTRA_LABELS.get(code, "(알 수 없는 항목)") for code in classified.categories + classified.extra_flags]
        return "운영자 전용 항목이 걸려 AI 가 병합할 수 없습니다" + (": " + ", ".join(names) if names else "")
    return None


def _c_no_secret(facts):
    value = facts.get("secret_findings")
    if value is None:
        return "비밀 모양 검사 결과가 없습니다"
    if not _non_negative_int(value):
        return "비밀 모양 발견 수가 올바른 숫자가 아닙니다"
    if value != 0:
        return "비밀 모양이 " + str(value) + "건 발견되었습니다"
    return None


def _c_rollback(facts):
    text = facts.get("rollback_method")
    if not isinstance(text, str):
        return "되돌리는 방법 문장이 없습니다"
    body = " ".join(text.split())
    if len(body) < ROLLBACK_MIN_CHARS or body.casefold() in _ROLLBACK_PLACEHOLDERS:
        return "되돌리는 방법이 구체적이지 않습니다(최소 " + str(ROLLBACK_MIN_CHARS) + "자의 문장이어야 하고 없음·미정 같은 말은 안 됩니다)"
    return None


_CONDITION_CHECKS = {
    "number_match": _c_number_match, "no_new_commit": _c_no_new_commit, "checks_pass": _c_checks_pass, "independent_verified": _c_independent,
    "no_conflict": _c_no_conflict, "scope_matches": _c_scope, "no_secret_exposure": _c_no_secret, "rollback_confirmed": _c_rollback,
}


def check_preconditions(facts):
    """병합 직전 재확인 8조건(PRECONDITIONS)을 각각 판정해 Verdict 를 돌려준다. facts 는 FACT_KEYS 의 값을 담은 평범한 사전이다 —
    approved_number(`M075`)·approved_pr_number·pr_number(양의 정수)·pr_title_label(pr_title_label 의 결과)·consumed_numbers(이미 쓴 승인 번호 목록)·
    approved_head_sha·current_head_sha(40자 해시)·current_tree(현재 PR 머리의 트리 해시)·approved_paths·current_paths(변경 파일 목록)·
    checks([{name, conclusion}] — conclusion 이 success 인 것만 통과, 건너뜀·중립도 통과가 아니다)·independent_verification(VERIFICATION_KEYS 의 값 — 검증자가 구현자와 다르고 필수 지적 0건이며
    검증한 트리가 current_tree 와 같아야 한다)·has_conflict(False 만 통과)·classification(classify_change 의 결과 — 현재 변경 파일로 계산한 것이어야 한다)·
    secret_findings(0 만 통과)·rollback_method(구체적인 문장).
    **모든 값이 있어야 하며 빠진 값·None·모양이 다른 값은 해당 조건의 실패다**(없다고 통과로 보지 않는다). 확인 중 예상하지 못한 오류가 나도 실패로 처리한다."""
    failures = []
    for code, name in PRECONDITIONS:
        if not isinstance(facts, dict):
            reason = "확인에 쓸 자료(사전)가 없습니다"
        else:
            try:
                reason = _CONDITION_CHECKS[code](facts)
            except Exception:                      # 확인 장치의 오류가 통과로 바뀌지 않게 닫는다
                reason = "확인하는 중 예상하지 못한 오류가 나 실패로 처리합니다"
        if reason is not None:
            failures.append(Failure(code, name, reason))
    return Verdict(not failures, tuple(failures))


# ---- 병합 방식 제한 --------------------------------------------------------------------------------------------------------------------------------------------
def merge_method_allowed(method):
    """병합은 `pr_merge`(GitHub PR 병합) 하나뿐이다. main 직접 push(`push_main`·`direct_push`)·강제 push(`force_push`)와 모르는 값·글자가 아닌 값·대소문자나 공백이 다른 값은 모두 거짓이다."""
    return isinstance(method, str) and method == ALLOWED_MERGE_METHOD


# ---- 쉬운 병합 설명 --------------------------------------------------------------------------------------------------------------------------------------------
_INVISIBLE_CODEPOINTS = tuple(range(0x200B, 0x2010)) + tuple(range(0x202A, 0x202F)) + tuple(range(0x2060, 0x2065)) + tuple(range(0x2066, 0x206A)) + (0xFEFF,)
_INVISIBLE_RE = re.compile("[" + "".join(chr(code) for code in _INVISIBLE_CODEPOINTS) + "]")     # 방향을 바꾸는 글자·너비 없는 글자 — 운영자가 눈으로 읽는 글을 속이는 데 쓰인다
_HEADER_RE = re.compile(r"병합 요청[ \t]+(M[0-9]+)")
_PR_RE = re.compile(r"대상 PR[ \t]*[:：][ \t]*#([0-9]+)")
_COMMIT_RE = re.compile(r"머리 커밋[ \t]*[:：][ \t]*([0-9a-fA-F]{7,40})(?![0-9A-Za-z])")
_FILES_HEAD_RE = re.compile(r"변경 파일[ \t]*\(([0-9]+)개\)")
_CHECKLIST_HEAD = "운영자 전용 항목 점검"
_MERGE_WAY_PREFIX = "병합 방식:"
_APPROVAL_EXAMPLE_RE = re.compile(r"승인 예[ \t]*[:：][ \t]*(M[0-9]+)[ \t]+승인")
_ANY_APPROVAL_RE = re.compile(r"(M[0-9]+)[ \t]+승인")
ANSWER_MIN_CHARS = 8
ANSWER_MIN_HANGUL = 4
_HANGUL_RE = re.compile("[가-힣]")
_COMMIT_VALUE_RE = re.compile(r"[0-9a-fA-F]{7,40}")


def _one_line(value, limit=400):
    """설명 한 항목을 한 줄로 접는다(줄 바꿈이 구조를 흉내 내지 못하게) — 보이지 않는 글자·제어 문자를 지우고 길이를 제한한다. 글자가 아니거나 비면 ValueError."""
    if not isinstance(value, str):
        raise ValueError("text")
    text = _INVISIBLE_RE.sub("", " ".join(value.split()))
    text = "".join(ch for ch in text if ord(ch) >= 32 and ord(ch) != 127)
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    if not text:
        raise ValueError("empty")
    return text


def _mark(marks, code):
    """점검표 한 줄의 값 — 알려 주지 않은 항목은 `아니오`(기본), 알려 준 값이 정확히 False 가 아니면 `예`(해석할 수 없는 값도 예로 적어 눈에 띄게 한다)."""
    if code not in marks:
        return "아니오"
    return "아니오" if marks[code] is False else "예"


def render_explanation(number, pr_number, head_sha, changed_paths, what, why, user_change, risk, check_summary, rollback, ai_merge_enabled=False, checklist=None):
    """구조화된 입력으로 표준 병합 설명(운영자가 본 예시 형식)을 만든다 — 첫 줄 `병합 요청 M075`, 대상 PR·머리 커밋(짧은 해시), 6항목, 변경 파일 목록, 운영자 전용 12항목 점검표(기본은 전부 아니오),
    병합 방식 줄(ai_merge_enabled 가 False 면 '꺼져 있어 운영자께서 직접 병합' 표지), 승인 안내(`M075 승인`). 입력이 올바르지 않으면 ValueError. 만든 글은 explanation_problems 로 다시 점검한다."""
    label = _standard_label(number)
    sha = _sha(head_sha)
    paths = _path_set(changed_paths)
    if label is None or sha is None or not _positive_int(pr_number) or not paths:
        raise ValueError("input")
    if any(_INVISIBLE_RE.search(path) for path in paths):
        raise ValueError("path")
    answers = [_one_line(item) for item in (what, why, user_change, risk, check_summary, rollback)]
    marks = {} if checklist is None else checklist
    if not isinstance(marks, dict):
        raise ValueError("checklist")
    lines = ["병합 요청 " + label, "대상 PR: #" + str(pr_number) + " · 머리 커밋: " + sha[:7]]
    lines += [item + " " + answer for item, answer in zip(EXPLANATION_ITEMS, answers)]
    lines.append("변경 파일 (" + str(len(paths)) + "개)")
    lines += ["- " + path for path in sorted(paths)]
    lines.append(_CHECKLIST_HEAD + " (모두 아니오여야 AI 병합 대상입니다)")
    lines += ["- " + name + ": " + _mark(marks, code) for code, name in OPERATOR_ONLY_ITEMS]
    lines.append(_MERGE_WAY_PREFIX + " " + (AI_MERGE_ON_NOTICE if ai_merge_enabled else AI_MERGE_OFF_NOTICE))
    lines.append(APPROVAL_GUIDE_LINE)
    lines.append("승인 예: " + label + " 승인")
    return "\n".join(lines) + "\n"


def _split_lines(text):
    return [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def _label_lines(lines, label):
    """줄 맨 앞(목록 기호는 허용)이 label 로 시작하고 바로 뒤가 공백·콜론인 줄들의 뒷부분."""
    found = []
    for line in lines:
        body = line[2:].lstrip() if line.startswith(("- ", "* ")) else line
        if body == label:
            found.append("")
        elif body.startswith(label) and body[len(label)] in " \t:：":
            found.append(body[len(label):].lstrip(" \t:：").strip())
    return found


def _answer_problem(answer):
    if len(answer) < ANSWER_MIN_CHARS or len(_HANGUL_RE.findall(answer)) < ANSWER_MIN_HANGUL:
        return "내용이 비어 있거나 너무 짧거나 한글 문장이 아닙니다(쉬운 한국어로 " + str(ANSWER_MIN_CHARS) + "자 이상)"
    return None


def _section(lines, start):
    """lines[start] 다음부터 이어지는 `- ` 줄들."""
    found = []
    for line in lines[start + 1:]:
        if not line.startswith("- "):
            break
        found.append(line[2:].strip())
    return found


def explanation_problems(text, pr_title=None):
    """쉬운 병합 설명의 빠진 곳·어긋난 곳 목록(비어 있으면 통과). 점검: 첫 줄 `병합 요청 M###` · 대상 PR 번호 · 머리 커밋(짧은 해시) · 6항목(각각 정확히 한 번, 한글 문장 8자 이상) ·
    변경 파일 목록(개수 일치·비어 있지 않음) · 운영자 전용 12항목 점검표(전부 `아니오` — 하나라도 `예`거나 빠지면 문제) · 병합 방식 줄(꺼짐 표지 또는 켜짐 문장) · 승인 안내 줄과 `승인 예: M### 승인` ·
    번호 일치(첫 줄·승인 예·글 속 모든 `M### 승인` 문구, pr_title 을 주면 PR 제목의 `[M###]` 까지) · 보이지 않는 글자 없음."""
    if not isinstance(text, str):
        return ["설명이 글이 아닙니다"]
    problems = []
    if _INVISIBLE_RE.search(text):
        problems.append("보이지 않는 글자(방향을 바꾸는 글자·너비 없는 글자)가 들어 있습니다")
    lines = _split_lines(text)
    nonblank = [line for line in lines if line]
    head = _HEADER_RE.fullmatch(nonblank[0]) if nonblank else None
    number = head.group(1) if head is not None and _standard_label(head.group(1)) is not None else None
    if number is None:
        problems.append("첫 줄이 '병합 요청 M075' 모양이 아닙니다(번호는 M 뒤에 세 자리 또는 네 자리 숫자)")
    prs = _PR_RE.findall(text)
    if len(prs) != 1 or int(prs[0]) < 1:
        problems.append("대상 PR 번호가 정확히 한 번 있어야 합니다(예: 대상 PR: #198)")
    commits = _COMMIT_RE.findall(text)
    if len(commits) != 1:
        problems.append("머리 커밋(짧은 해시)이 정확히 한 번 있어야 합니다(예: 머리 커밋: abc1234)")
    for item in EXPLANATION_ITEMS:
        answers = _label_lines(lines, item)
        if not answers:
            problems.append("항목이 빠졌습니다: " + item)
        elif len(answers) > 1:
            problems.append("항목이 두 번 이상 나옵니다: " + item)
        else:
            why = _answer_problem(answers[0])
            if why:
                problems.append(item + " — " + why)
    starts = [index for index, line in enumerate(lines) if _FILES_HEAD_RE.fullmatch(line)]
    if len(starts) != 1:
        problems.append("변경 파일 목록(변경 파일 (N개))이 정확히 한 번 있어야 합니다")
    else:
        listed = _section(lines, starts[0])
        declared_count = int(_FILES_HEAD_RE.fullmatch(lines[starts[0]]).group(1))
        if not listed:
            problems.append("변경 파일 목록이 비어 있습니다")
        elif declared_count != len(listed):
            problems.append("변경 파일 개수(" + str(declared_count) + ")와 적힌 파일 수(" + str(len(listed)) + ")가 다릅니다")
        if any(normalize_path(item) != item for item in listed):
            problems.append("변경 파일 목록에 올바르지 않은 경로가 있습니다")
    heads = [index for index, line in enumerate(lines) if line.startswith(_CHECKLIST_HEAD)]
    if len(heads) != 1:
        problems.append("운영자 전용 항목 점검표가 정확히 한 번 있어야 합니다")
    else:
        rows = _section(lines, heads[0])
        table = {}
        for row in rows:
            name, _sep, value = row.partition(":")
            table[name.strip()] = value.strip()
        for name in OPERATOR_ONLY_LABELS:
            if name not in table:
                problems.append("점검표에 빠진 항목: " + name)
        for name, value in table.items():
            if value != "아니오":
                problems.append("점검표에 '예'(또는 알 수 없는 값)가 있습니다: " + name + " — AI 병합 대상이 아닙니다")
    ways = [line for line in lines if line.startswith(_MERGE_WAY_PREFIX)]
    if len(ways) != 1 or (AI_MERGE_OFF_NOTICE not in ways[0] and AI_MERGE_ON_NOTICE not in ways[0]):
        problems.append("병합 방식 줄이 정확히 한 번 있어야 하고 꺼짐 표지 또는 켜짐 문장을 담아야 합니다")
    if lines.count(APPROVAL_GUIDE_LINE) != 1:
        problems.append("승인 안내 줄이 정확히 한 번 있어야 합니다: " + APPROVAL_GUIDE_LINE)
    examples = _APPROVAL_EXAMPLE_RE.findall(text)
    if len(examples) != 1:
        problems.append("승인 예 줄(승인 예: M075 승인)이 정확히 한 번 있어야 합니다")
    elif number is not None and examples[0] != number:
        problems.append("승인 예의 번호(" + examples[0] + ")가 첫 줄의 병합 번호(" + number + ")와 다릅니다")
    if number is not None:
        stray = sorted({token for token in _ANY_APPROVAL_RE.findall(text) if token != number})
        if stray:
            problems.append("글 속에 다른 번호의 승인 문구가 있습니다: " + ", ".join(stray))
        if pr_title is not None and pr_title_label(pr_title) != number:
            problems.append("PR 제목의 병합 번호와 설명의 병합 번호가 다르거나 제목에서 번호를 읽을 수 없습니다")
    return problems


# ---- 병합 완료 알림 --------------------------------------------------------------------------------------------------------------------------------------------
def render_completion_notice(number, pr_number, merged_commit, change, main_checks, anomaly, rollback):
    """병합 완료 알림의 표준 글 — 첫 줄 `병합 완료 알림` 아래에 필수 7항목(COMPLETION_ITEMS)을 `이름: 값` 줄로 적는다. 입력이 올바르지 않으면 ValueError."""
    label = _standard_label(number)
    if label is None or not _positive_int(pr_number) or not isinstance(merged_commit, str) or _COMMIT_VALUE_RE.fullmatch(merged_commit) is None:
        raise ValueError("input")
    values = [label, "#" + str(pr_number), merged_commit[:12], _one_line(change), _one_line(main_checks), _one_line(anomaly), _one_line(rollback)]
    return "\n".join(["병합 완료 알림"] + [item + ": " + value for item, value in zip(COMPLETION_ITEMS, values)]) + "\n"


def _labeled_values(lines, label):
    """`이름: 값` 줄(목록 기호 허용, 콜론은 ASCII 또는 전각)의 값들."""
    found = []
    for line in lines:
        body = line[2:].lstrip() if line.startswith(("- ", "* ")) else line
        if body.startswith(label):
            rest = body[len(label):].lstrip(" \t")
            if rest and rest[0] in ":：":
                found.append(rest[1:].strip())
    return found


def completion_notice_problems(text):
    """병합 완료 알림이 필수 7항목(병합 번호·PR 번호·병합된 Commit·실제 반영된 변화·main 검사 결과·이상 유무·원복 Commit 또는 원복 방법)을 모두 갖췄는지 — 빠진 곳 목록(비어 있으면 통과).
    각 항목은 `이름: 값` 줄로 정확히 한 번, 값이 비어 있지 않아야 하고, 병합 번호는 표준 `M###`, PR 번호는 양의 정수(앞 # 허용), 병합된 Commit 은 7–40자 16진 해시여야 한다."""
    if not isinstance(text, str):
        return ["알림이 글이 아닙니다"]
    problems = []
    if _INVISIBLE_RE.search(text):
        problems.append("보이지 않는 글자(방향을 바꾸는 글자·너비 없는 글자)가 들어 있습니다")
    lines = _split_lines(text)
    for item in COMPLETION_ITEMS:
        values = _labeled_values(lines, item)
        if not values:
            problems.append("항목이 빠졌습니다: " + item)
            continue
        if len(values) > 1:
            problems.append("항목이 두 번 이상 나옵니다: " + item)
            continue
        value = values[0]
        if not value:
            problems.append("내용이 비어 있습니다: " + item)
        elif item == "병합 번호" and _standard_label(value) is None:
            problems.append("병합 번호가 표준 모양(M075)이 아닙니다")
        elif item == "PR 번호" and re.fullmatch(r"#?[0-9]+", value) is None:
            problems.append("PR 번호가 숫자가 아닙니다")
        elif item == "PR 번호" and int(value.lstrip("#")) < 1:
            problems.append("PR 번호가 1 보다 작습니다")
        elif item == "병합된 Commit" and _COMMIT_VALUE_RE.fullmatch(value) is None:
            problems.append("병합된 Commit 이 7–40자 16진 해시가 아닙니다")
    return problems


# ---- 첫 운영 3건 시험과 즉시 중지 ----------------------------------------------------------------------------------------------------------------------------
_ABSENT = object()


@dataclass(frozen=True)
class TrialReport:
    """evaluate_trial 의 자세한 결과 — result 는 TRIAL_CONTINUE·TRIAL_PENDING·TRIAL_STOP 중 하나, violations 는 위반(또는 확인할 수 없는 기록)의 쉬운 말 목록."""
    result: str
    violations: tuple
    counted: int


def trial_report(records):
    """AI 병합 기록(리스트의 사전)을 시험 기준 6가지로 평가한다. 각 기록은 `number`(M###)와 TRIAL_CRITERIA 의 6개 키(값은 '충족했는가' — 참이 충족)를 가진다.
    한 건이라도 기준을 어기거나(값이 False) 값이 빠졌거나 참·거짓이 아니거나(main_checks_passed 의 None 만 '아직 모름'으로 허용) 번호가 표준이 아니거나 같은 번호가 두 번 나오면
    기록이 3건 미만이어도 즉시 TRIAL_STOP 이다. 위반이 없고 서로 다른 번호의 기록이 TRIAL_SIZE 건 이상이며 모두 충족이면 TRIAL_CONTINUE, 그 밖(3건 미만·main 검사 결과 아직 모름)이면 TRIAL_PENDING 이다."""
    if not isinstance(records, (list, tuple)):
        return TrialReport(TRIAL_STOP, ("기록이 목록이 아니라 평가할 수 없습니다 — 보수적으로 중지합니다",), 0)
    violations, seen, unknown = [], set(), False
    for position, record in enumerate(records, 1):
        number = record.get("number") if isinstance(record, dict) else None
        name = number if _standard_label(number) is not None else "기록 " + str(position)
        if not isinstance(record, dict):
            violations.append(name + ": 기록이 사전이 아닙니다")
            continue
        if _standard_label(number) is None:
            violations.append(name + ": 병합 번호가 표준 모양이 아닙니다")
        elif number in seen:
            violations.append(name + ": 같은 병합 번호가 두 번 기록되었습니다(승인 재사용 의심)")
        else:
            seen.add(number)
        for key, label in TRIAL_CRITERIA:
            value = record.get(key, _ABSENT)               # 키가 아예 없으면 형식 오류(위반), 값이 None 이면 '아직 모름'(main 검사 결과만 허용)
            if value is True:
                continue
            if key == "main_checks_passed" and value is None:
                unknown = True
                continue
            violations.append(name + ": " + label + " 기준을 어겼거나 확인할 수 없습니다")
    if violations:
        return TrialReport(TRIAL_STOP, tuple(violations), len(seen))
    if len(seen) < TRIAL_SIZE or unknown:
        return TrialReport(TRIAL_PENDING, (), len(seen))
    return TrialReport(TRIAL_CONTINUE, (), len(seen))


def evaluate_trial(records):
    """trial_report 의 result 만: `'continue'`(3건 모두 충족) · `'pending'`(3건 미만이고 위반 없음, 또는 main 검사 결과를 아직 모름) · `'stop_immediately'`(한 건이라도 위반 — 3건 미만이어도 즉시)."""
    return trial_report(records).result
