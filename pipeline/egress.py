"""외부 호출 관문(egress) — 외부로 나가는 요청의 주소를 판정하는 한 곳(docs/SOURCE_POLICY.md 7절).

판정: 주소는 ① 고정 운영 호스트의 **허용 목적·허용 경로**(OPS_RULES — 호스트마다 어떤 목적(purpose)으로 어떤 경로까지 열려 있는지)이거나 ② 허용 목록(Registry)의 ACTIVE Provider 가 그 호스트·경로를 접근 경로로 두고
목적이 허용 목적(`fact`)일 때만 통과한다. 일반 웹 읽기(feed·page·resolve)와 모르는 목적은 운영 호스트에서도 허용 목록에서도 거부한다. 운영자 결정(2026-11-09): 허용 목록 밖 호스트로는 자동 접근하지 않는다.

이 모듈이 하는 것
- `check_url(url, purpose, registry, own_repo=None)` — 첫 주소를 판정한다(허용이면 None, 아니면 `EgressDenied`). 요청을 보내지 않는다.
- `build_checked_opener(purpose, registry, ...)` — 리다이렉트를 따라갈 때마다 새 주소를 `check_url` 로 다시 판정하는 opener(첫 요청도 같은 판정을 거친다). 관문은 첫 주소만 판정하므로
  어댑터는 이 opener 를 쓰거나 `check_final_url` 로 최종 주소를 다시 판정해야 한다(docs 9절 의무). 요청을 보내는 것은 이 opener 를 쓰는 쪽이다.
- `check_final_url(response_url, purpose, registry, own_repo=None)` — 응답의 최종 주소(`geturl()`)를 다시 판정한다.
- `check_ai_input(provider_id, scope, registry)` — 그 Provider 의 자료를 AI 처리기(Gemini 등)에 넘겨도 되는지 판정한다(허용이면 None, 아니면 `AiInputDenied`). `ai_use` 가 NEVER 인 Provider 는 AI 처리기 정책의
  `input_scope` 와 상관없이 **항상 거부**한다(운영자 결정 007 — 규칙 기반 경로에서만 쓰는 자료). 지금 이 함수를 부르는 운영 코드는 없다(AI 로 가는 자료 경로가 없다 — FACT 2단계가 AI 단계 앞에서 부른다).
- `CallBudget`·`budgeted`·`run_call_cap`·`budget_for` — 제공처 호출 한도를 지키는 자리: 한 실행 안의 호출 상한(레지스트리 rate_limit 에서 계산)·실패 3회 뒤 건너뜀·같은 주소 한 번 더(재시도 상한)·같은 주소 성공 응답 재사용·
  403·429 면 그 실행에서 그 Provider 중지·404 면 그 주소만 중지·호출 전 선행 조건(하루·주간 상한이 이미 막았으면 호출 0). Actions 는 실행마다 새 환경이라 **새 영구 상태를 만들지 않는다** — 하루·월 합계와 24시간 중지,
  호출 간격·gzip 요청·일별 제품 시각은 이 래퍼가 강제하지 못한다(어댑터·연결 코드의 의무이고 한계는 docs/SOURCE_POLICY.md 7절).
- `EGRESS_EXCEPTIONS` — 지금 저장소가 외부로 나갈 수 있는 모양의 코드 지점 중 이 관문을 거치지 않는 곳의 등록 목록(파일·함수·이유·**어떤 관문이 어느 모드에서 막는지**).

**호출 목록 시험은 보증이 아니다.** `tests/test_egress.py` 는 알려진 모양의 호출을 AST 로 모아 이 등록 목록과 비교할 뿐이다(`tests/egress_scan.py` 머리말의 모양 목록). 새 모양·동적 코드·소스 밖의 일은 잡지 못하고
(사각지대 표: docs 7절) 사람 검토가 마지막 방어선이다. 목록에 올라 있다는 것은 '이유를 적고 사람이 보았다'는 뜻이지 '막혀 있다'는 뜻이 아니다 — 막는 장치가 있으면 `gate` 칸에 적는다.

표준 라이브러리만 쓴다. 판정 함수는 입출력이 없다(요청을 보내지 않는다).
"""
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple

from pipeline import source_registry as sr

# ----------------------------------------------------------------------------
# 고정 운영 호스트 규칙: 호스트마다 허용 목적과 허용 경로(경로 전체에 맞는 정규식 — 질의는 판정에 쓰지 않는다). 경로의 `{repo}` 는 부르는 쪽이 넘긴 자기 저장소 이름(own_repo)으로 바뀐다.
# 근거는 docs 의 외부 접근 경로 전수 목록(2026-11-09 코드 읽기)과 아래 'basis' 의 파일. 호스트 문자열이 코드에 직접 있는 것은 시험이 그 파일에 정말 있는지 확인한다. 'sdk' 는 SDK 가 정하는 호스트(코드에 문자열 없음).
# ----------------------------------------------------------------------------
OpsRule = namedtuple("OpsRule", "host purposes paths basis")
OPS_RULES = (
    # GitHub REST — 자기 저장소의 이슈·라벨·PR·커밋 검사·Actions 와 한도 조회. 코드가 부르는 경로 머리: /repos/{저장소}/issues·labels·pulls·commits(…/check-runs)·actions·check-runs 와 /rate_limit
    # (C-17 issue_package.py·C-18 drafts.py·C-20 watchdog.py·C-21 ops_inbox.py·C-22 operator_loop.py·C-23 github_status.py 의 모든 호출을 grep 으로 확인). 저장소는 own_repo 로 넘긴 것만 — 남의 저장소(예: /repos/다른소유자/다른저장소/readme)는 거부.
    OpsRule("api.github.com", ("ops_repo",), (r"/repos/{repo}/(?:issues|labels|pulls|commits|actions|check-runs)(?:/[^/]+)*", r"/rate_limit"), "pipeline/drafts.py"),
    # Telegram Bot API — 알림 sendMessage 와 수신 getUpdates 만(C-27–C-34 notify.py·telegram_inbox.py). 경로에 봇 토큰이 들어가므로 모양만 본다.
    OpsRule("api.telegram.org", ("ops_notify",), (r"/bot[0-9]+:[A-Za-z0-9_-]+/(?:sendMessage|getUpdates)",), "pipeline/notify.py"),
    # Google OAuth 토큰 갱신(C-11 publishers/blogger.py TOKEN_URI) — /token 하나.
    OpsRule("oauth2.googleapis.com", ("ops_auth",), (r"/token",), "pipeline/publishers/blogger.py"),
    # Gemini API(C-04·C-05·C-10 google-genai SDK) — 공개 문서의 /v1beta/models/{모델}:generateContent 꼴(코드에 호스트 문자열 없음).
    OpsRule("generativelanguage.googleapis.com", ("ops_llm",), (r"/v1(?:beta)?/models(?:/[^/]+)?",), "sdk"),
    # Blogger API v3(C-12–C-14 googleapiclient, pip 고정 google-api-python-client>=2,<3 — 번들 디스커버리 문서를 쓰므로 호출은 blogger.googleapis.com 의 /v3/blogs/{블로그}/posts…) — 코드에 호스트 문자열 없음.
    # www.googleapis.com 은 뺐다(D-173): 코드에 있는 www.googleapis.com 은 OAuth 범위 이름(SCOPES 글자)이고 요청 목적지가 아니며, 디스커버리를 내려받지 않는다.
    OpsRule("blogger.googleapis.com", ("ops_publish",), (r"/v3/blogs/[^/]+(?:/posts(?:/[^/]+)?)?",), "sdk"),
)
OPS_HOSTS = frozenset(rule.host for rule in OPS_RULES)
OPS_PURPOSES = frozenset(purpose for rule in OPS_RULES for purpose in rule.purposes)
OPS_HOST_BASIS = {rule.host: rule.basis for rule in OPS_RULES}
_OPS_BY_HOST = {rule.host: rule for rule in OPS_RULES}
_REPO_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}")
MAX_REDIRECTS = 3
_SENSITIVE_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie", "x-api-key", "x-goog-api-key", "private-token"})   # 다른 호스트로 따라갈 때 떼는 머리글

# ----------------------------------------------------------------------------
# 예외 목록: 이 관문을 거치지 않는 외부 접속 '알려진 모양'의 코드 지점. (파일, 함수 — 클래스는 `Class.method`, 중첩 함수는 `outer.inner`, 모듈 바로 아래는 `<module>`, 이유, 막는 장치, 종류, 지점 수)
# 한 줄이라도 낡으면(함수 이름이 바뀌거나 지점이 사라지면) 시험이 알린다. `function` 이 "*" 이면 그 파일의 어느 함수든 `kinds` 에 든 종류(모양 종류 머리말)만 면제한다.
# `kinds` 는 면제하는 모양 종류의 **앞 조각**(`net:`·`proc:`·`dyn:`·`sdk:`·`lib:`·`parse:` — 비우면 그 함수의 모든 종류)이고, `count` 는 그 항목이 덮는 지점 수다(None 이면 세지 않는다 — 와일드카드).
# 이미 등록된 함수에 **다른 종류의 모양이 더해지면** 등록 밖 지점이 되고, `count` 가 있으면 **같은 종류가 늘어도** 시험이 빨개진다(SRCV2 D2 — 등록 단위가 함수라 생기는 틈).
# `count` 가 None 인 항목(와일드카드, 그리고 다른 묶음이 계속 고치는 Fact·그림자 실행 파일의 항목)은 종류만 좁히고 개수는 세지 않는다 — 그 함수 안에서 늘어나는 것이 정당할 수 있어 합친 뒤 CI 가 빨개지지 않게 했다. 워크플로 yml 은 (파일, 종류) 단위라 줄이 늘어도 못 잡는다.
# ----------------------------------------------------------------------------
EgressException = namedtuple("EgressException", "file function reason gate kinds count", defaults=("", (), None))

_G_ALLOWLIST = "allowlist 에서는 막힘(source_policy.egress_gate → check_url 이 일반 웹 읽기 목적을 거부, 소스 건너뜀이 먼저 막음) · legacy 에서는 열려 있음(옛 동작 그대로)"
_G_PHOTO = "막는 장치 없음 — allowlist 에서도 열려 있다. 외부 사진 경로이고 사진을 자동으로 쓸지는 운영자 결정 대기(공개 글 49편 사용 중)라 이 일이 끄지 않는다"
_G_OPS = "막는 장치 없음(두 모드 모두 열림) — 운영 호스트(OPS_RULES)로만 가는 호출이라 check_url 에 연결하지 않았다. 호스트·경로는 OPS_RULES 가 문서로 정한 범위"
_G_SDK = "막는 장치 없음(두 모드 모두 열림) — SDK 가 호스트를 정해 직접 연결해 관문을 지날 수 없다. allowlist 는 SDK 입력(프롬프트)에서 외부 본문을 뺀다(prompt_inputs)"
_G_TOOL = "막는 장치 없음 — 사람이 실행하는 도구(워크플로·예약이 부르지 않는다)라 두 모드 모두 해당 없음"
_G_GIT = "막는 장치 없음 — git 이 자기 저장소 원격(origin)과 주고받는다. 일부는 로컬 읽기뿐. 하위 명령은 부르는 쪽이 정하고 이 시험은 보지 않는다"
_G_SELF = "막는 장치 없음 — 이 관문 모듈이 검사된 opener 를 만드는 곳이다. 만들어진 opener 는 첫 요청과 모든 리다이렉트를 check_url 로 다시 판정한다"
_G_LOCAL = "해당 없음 — 네트워크에 닿지 않는 동적 모양(이름으로 칸을 읽거나 저장소 안의 파일을 불러옴)을 사람이 확인해 등록했다"
_PHOTO_REASON = "외부 사진(Unsplash) 경로"

EGRESS_EXCEPTIONS = (
    # -- generator.py: 피드·기사 페이지·구글 뉴스 해석기는 allowlist 에서만 관문이 막는다 --------------------------------------------------------------------------------------------
    EgressException("generator.py", "fetch_news_items", "C-01 NEWS_SOURCES 피드 읽기 — 외부 RSS 요약을 가져오는 일반 웹 읽기(유형만으로 Tier 3)", _G_ALLOWLIST, ("net:",), 1),
    EgressException("generator.py", "_fetch_source_excerpt", "C-02 기사 페이지 게시자 요약 발췌 — 외부 기사 페이지를 읽는 일반 웹 읽기", _G_ALLOWLIST, ("net:",), 1),
    EgressException("generator.py", "_resolve_article_url", "C-03 구글 뉴스 중계 주소 해석(리다이렉트를 따라감) — 일반 웹 읽기", _G_ALLOWLIST, ("net:",), 1),
    EgressException("generator.py", "get_client", "Gemini SDK 클라이언트(C-04) — 호스트는 SDK 가 정하는 운영 호스트(generativelanguage.googleapis.com)", _G_SDK, ("sdk:",), 1),
    EgressException("generator.py", "url_ok", "이미지 주소 HEAD 확인(C-08): 새 글 단계는 후보 Unsplash 사진, 사진 교체 단계(FIX_IMAGES)는 기존 글 머리말의 `image:` 주소 호스트 전부(Unsplash 외 NASA 이미지 호스트 포함)에 HEAD 요청을 한다 — 운영자 결정(사진 자동 사용) 때 정리", _G_PHOTO, ("net:",), 1),
    EgressException("generator.py", "search_unsplash", "Unsplash 사진 검색(C-06) — " + _PHOTO_REASON, _G_PHOTO, ("net:",), 1),
    EgressException("generator.py", "trigger_download", "Unsplash 사용 알림(C-09) — " + _PHOTO_REASON + ". 알림만 따로 끄면 Unsplash API 지침 위반", _G_PHOTO, ("net:",), 1),
    EgressException("generator.py", "fetch_pool_photo", "Unsplash 고정 목록 사진 조회(C-07) — " + _PHOTO_REASON, _G_PHOTO, ("net:",), 1),
    # -- pipeline/ -------------------------------------------------------------------------------------------------------------------------------------------------------------
    EgressException("pipeline/drafts.py", "GitHubClient.__init__", "자기 저장소 GitHub API(C-18, 승인 흐름 publish_flow: pr 일 때만 — 지금 꺼짐)", _G_OPS, ("net:",), 1),
    EgressException("pipeline/draft_flow.py", "Git.run", "자기 저장소 git(C-19 승인 흐름의 ls-remote·push·pull) — 명령을 목록으로 만들고 하위 명령은 부르는 쪽이 정한다(승인 흐름 지금 꺼짐)", _G_GIT, ("proc:",), 1),
    EgressException("pipeline/edits/scope_check.py", "_git", "로컬 저장소 diff 읽기 도우미(이슈 수정 범위 검사) — 하위 명령은 부르는 쪽이 정한다(diff·show 등 읽기)", _G_GIT, ("proc:",), 1),
    EgressException("pipeline/llm.py", "make_gemini_llm.client", "Gemini SDK 클라이언트(C-10, Blogger·이슈 수정) — 입력은 우리 데이터뿐이고 호스트는 SDK 가 정하는 운영 호스트", _G_SDK, ("sdk:",), 1),
    EgressException("pipeline/llm.py", "_field", "SDK 응답 객체에서 칸 이름으로 값을 읽는다(이름은 부르는 쪽의 상수) — 네트워크 이름에 닿지 않는다", _G_LOCAL, ("dyn:",), 1),
    EgressException("pipeline/main_image.py", "search", "Blogger 대표 사진 검색(C-15) — " + _PHOTO_REASON, _G_PHOTO, ("net:",), 1),
    EgressException("pipeline/main_image.py", "ping_download", "Blogger 대표 사진 사용 알림(C-16) — " + _PHOTO_REASON, _G_PHOTO, ("net:",), 1),
    EgressException("pipeline/notify.py", "Notifier._post", "텔레그램 알림 전송(C-27–C-33, api.telegram.org)", _G_OPS, ("net:",), 1),
    EgressException("pipeline/notify.py", "*", "git 명령을 부르는 `runner=subprocess.run` 참조(커밋 목록·파일 읽기 — 로컬 git 읽기이고 명령은 이 함수들 안의 목록 상수)", _G_GIT, ("proc:ref",)),
    EgressException("pipeline/notify.py", "_pages_module", "저장소 안의 scripts/verify_pages_deploy.py 를 경로로 불러온다(주소 계산 재사용) — 그 파일은 스캔 범위 안이라 거기서 따로 잡힌다", _G_LOCAL, ("dyn:",), 2),
    EgressException("pipeline/operator_loop.py", "GitHub.__init__", "자기 저장소 GitHub API(C-22 운영자 응답 접수)", _G_OPS, ("net:",), 1),
    EgressException("pipeline/operator_loop.py", "*", "git 명령을 부르는 `runner=subprocess.run` 참조(요청 파일 이름 읽기 — 로컬 git 읽기)", _G_GIT, ("proc:ref",)),
    EgressException("pipeline/publishers/blogger.py", "BloggerPublisher._new_credentials", "Blogger OAuth 자격(C-11) — 토큰 갱신은 oauth2.googleapis.com", _G_SDK, ("sdk:",), 1),
    EgressException("pipeline/publishers/blogger.py", "BloggerPublisher._new_request", "Blogger OAuth 토큰 갱신 전송(C-11, oauth2.googleapis.com)", _G_SDK, ("sdk:",), 1),
    EgressException("pipeline/publishers/blogger.py", "BloggerPublisher._build_service", "Blogger API v3 클라이언트(C-12–C-14, blogger.googleapis.com)", _G_SDK, ("sdk:",), 1),
    EgressException("pipeline/publishers/issue_package.py", "IssuePackagePublisher.__init__", "자기 저장소 GitHub API(C-17 초안 패키지 이슈, 네이버·티스토리 — 지금 꺼짐)", _G_OPS, ("net:",), 1),
    EgressException("pipeline/telegram_inbox.py", "Telegram._once", "텔레그램 수신 getUpdates(C-34, 운영자 본인 글)", _G_OPS, ("net:",), 1),
    EgressException("pipeline/facts.py", "fact_content", "Fact 객체의 칸을 dataclass 의 `fields()` 이름으로 읽어 사전으로 만든다(이름은 정의에서 오는 상수) — 네트워크 이름에 닿지 않는다", _G_LOCAL, ("dyn:",), None),
    EgressException("pipeline/facts.py", "record_to_dict", "SourceRecord 의 칸을 `_RECORD_KEYS` 상수 이름으로 읽어 사전으로 만든다(직렬화) — 네트워크 이름에 닿지 않는다", _G_LOCAL, ("dyn:",), None),
    EgressException("pipeline/facts.py", "fact_to_dict", "Fact 의 칸을 `_FACT_KEYS` 상수 이름으로 읽어 사전으로 만든다(직렬화) — 네트워크 이름에 닿지 않는다", _G_LOCAL, ("dyn:",), None),
    EgressException("pipeline/facts.py", "derived_to_dict", "DerivedFact 의 칸을 `_DERIVED_KEYS` 상수 이름으로 읽어 사전으로 만든다(직렬화) — 네트워크 이름에 닿지 않는다", _G_LOCAL, ("dyn:",), None),
    EgressException("pipeline/facts.py", "field_of", "사전이든 객체든 같은 방식으로 칸을 읽는다(칸 이름은 부르는 쪽의 상수 — `PROVIDER_FIELDS` 등. SRC 의 Provider 는 읽기 전용 객체) — 네트워크 이름에 닿지 않는다", _G_LOCAL, ("dyn:",), None),
    EgressException("pipeline/shadow_run.py", "<module>", "그림자 실행의 파일 쓰기 깃발 상수: `getattr(os, 'O_EXCL', 0)`·`getattr(os, 'O_TEMPORARY', 0)` — 운영체제에 따라 없을 수 있는 상수를 읽을 뿐(네트워크 이름이 아니다)", _G_LOCAL, ("dyn:",), None),
    EgressException("pipeline/shadow_run.py", "read_only", "그림자 실행(읽기 전용 구간)의 방어 코드: 생성기의 쓰기 함수를 이름 목록(`getattr`)으로 읽어 부르면 거부하는 함수로 바꿔 끼우고, `subprocess.Popen`·`os.system`·`os.popen` 을 git·gh 를 막는 보호 함수로 바꿔 끼웠다가 구간이 끝나면 되돌린다 — 외부 호출을 만들지 않고 막는 쪽이다",
                    "막는 장치가 곧 이 함수다 — 읽기 전용 구간 안에서 git·gh 호출과 SHADOW_OUT 밖 쓰기를 거부한다(그림자 실행). 이 함수 자신은 네트워크 호출을 만들지 않는다", ("dyn:", "proc:"), None),
    EgressException("pipeline/source_registry.py", "Policy.__getitem__", "Policy 객체에서 CELLS 에서 검증된 칸 이름으로 값을 읽는다 — 네트워크 이름에 닿지 않는다", _G_LOCAL, ("dyn:",), 1),
    EgressException("pipeline/source_registry.py", "Policy.items", "Policy 객체의 칸을 CELLS 순서대로 읽는다 — 네트워크 이름에 닿지 않는다", _G_LOCAL, ("dyn:",), 1),
    EgressException("pipeline/egress.py", "build_checked_opener", "검사된 opener 를 만든다(첫 요청과 리다이렉트를 check_url 로 다시 판정하는 처리기만 붙이고 파일·FTP·프록시 처리기는 붙이지 않는다)", _G_SELF, ("net:",), 2),
    # -- scripts/ ------------------------------------------------------------------------------------------------------------------------------------------------------------
    EgressException("scripts/get_blogger_token.py", "main", "Blogger OAuth 토큰 1회 발급(C-42, 운영자 PC 수동 실행) — 워크플로·예약이 부르지 않는다", _G_TOOL, ("sdk:",), 1),
    EgressException("scripts/github_status.py", "Client.__init__", "자기 저장소 GitHub 공개 REST 읽기(C-23, 수동 명령줄·읽기 전용)", _G_OPS, ("net:",), 1),
    EgressException("scripts/ops_inbox.py", "GitHubClient.__init__", "자기 저장소 GitHub API(C-21 확인 필요 모음)", _G_OPS, ("net:",), 1),
    EgressException("scripts/ops_inbox.py", "fetch_feed_post_ids", "우리 Blogger 두 블로그의 공개 피드에서 글 번호만 읽음(C-35, 레지스트리 주소 모양일 때만·응답 4MB 상한) — 외부 본문을 읽지 않는 자체 블로그 점검", "막는 장치 없음 — 자체 블로그 호스트는 OPS_RULES 에 없다(허용 목록·운영 규칙 밖). 레지스트리 주소 모양 검사가 호스트를 좁힌다", ("net:",), 1),
    EgressException("scripts/verify_pages_deploy.py", "fetch", "자기 Pages 사이트의 새 글 주소 상태와 posts.json(C-36, 같은 출처 https 만) — 배포 확인", "막는 장치 없음 — 같은 출처 https 검사가 코드 안에 있다(OPS_RULES 밖의 자체 사이트)", ("net:",), 1),
    EgressException("scripts/watchdog.py", "GitHubClient.__init__", "자기 저장소 GitHub API(C-20 워치독)", _G_OPS, ("net:",), 1),
    EgressException("scripts/final_checks.py", "default_runner", "저장소 자체 점검 명령(테스트·검증 스크립트) 실행기 — 명령은 부르는 쪽이 목록으로 넘긴다", "막는 장치 없음 — 로컬 점검 명령 실행기이며 네트워크 도구를 부르는 곳은 없다(시험이 알려 줄 정도로 알려진 모양이 아님)", ("proc:",), 1),
    EgressException("scripts/validate_repo.py", "check_python", "저장소 파이썬 파일의 문법 검사 — `compile(소스, 파일, 'exec')` 로 코드 객체만 만들고 실행하지 않는다(읽기 전용 검사, 네트워크 이름에 닿지 않는다)", _G_LOCAL, ("dyn:",), 1),
    EgressException("scripts/validate_repo.py", "_git", "로컬 변경 범위 읽기(광고 표면 검사의 git diff 등) — 하위 명령은 부르는 쪽이 정한다", _G_GIT, ("proc:",), 1),
    # -- 인수인계/도구/(사람이 실행하는 운영 도구 — 워크플로·예약이 부르지 않는다) --------------------------------------------------------------------------------------------------------
    EgressException("인수인계/도구/setup_workspace.py", "run", "작업 폴더 준비 도우미 — 블로그·데스크톱 저장소(공개 clone) 내려받기를 포함한 git 명령 실행(운영 도구)", _G_TOOL, ("proc:",), 1),
    EgressException("인수인계/도구/work/commit_as_author.py", "git", "운영 도구: 작성자 이름으로 커밋하는 git 도우미(원격과 주고받지 않는다)", _G_TOOL, ("proc:",), 1),
    EgressException("인수인계/도구/work/make_request.py", "default_gate", "운영 도구: 병합 가지 머리 확인의 git ls-remote(자기 저장소 공개 원격)", _G_TOOL, ("proc:",), 1),
    EgressException("인수인계/도구/work/mk_merge_branch.py", "git", "운영 도구: 병합 가지 만들기용 git 도우미", _G_TOOL, ("proc:",), 1),
    EgressException("인수인계/도구/work/next_notice_no.py", "_git", "운영 도구: 알림 번호 계산용 git 읽기 도우미", _G_TOOL, ("proc:",), 1),
    EgressException("인수인계/도구/work/notice_tools.py", "_run_git", "운영 도구: 알림 도구의 git 실행 도우미(머리 제목 읽기)", _G_TOOL, ("proc:",), 1),
    EgressException("인수인계/도구/work/pipsafe.py", "main", "운영 도구: PyPI 공개 JSON 으로 패키지 나이 확인(pypi.org, 사람이 실행)", _G_TOOL, ("net:",), 1),
    EgressException("인수인계/도구/work/pipsafe.py", "run", "운영 도구: pip 설치를 부르는 실행 도우미(공식 인덱스, 사람이 실행)", _G_TOOL, ("proc:",), 1),
    EgressException("인수인계/도구/work/scratch/ci_web.py", "fetch", "운영 도구: GitHub Actions 공개 웹 페이지 읽기(사람이 실행)", _G_TOOL, ("net:",), 1),
    EgressException("인수인계/도구/work/scratch/run_annotations.py", "api", "운영 도구: GitHub 공개 REST 로 검사 주석 읽기(자기 저장소, 사람이 실행)", _G_TOOL, ("net:",), 1),
    EgressException("인수인계/도구/work/scratch/run_steps_times.py", "api", "운영 도구: GitHub 공개 REST 로 단계 시간 읽기(자기 저장소, 사람이 실행)", _G_TOOL, ("net:",), 1),
    EgressException("인수인계/도구/work/scratch/runs_by_sha.py", "<module>", "운영 도구: GitHub 공개 REST 로 실행 목록 읽기(자기 저장소, 사람이 실행)", _G_TOOL, ("net:",), 1),
    EgressException("인수인계/도구/work/scratch/wait_ci.py", "fetch", "운영 도구: 검사 끝날 때까지 GitHub 공개 웹·REST 읽기(자기 저장소, 사람이 실행)", _G_TOOL, ("net:",), 1),
    EgressException("인수인계/도구/work/scratch/wait_ci_multi.py", "<module>", "운영 도구: 여러 가지의 검사 상태를 GitHub 공개 REST 로 읽기(자기 저장소, 사람이 실행)", _G_TOOL, ("net:",), 1),
    EgressException("인수인계/도구/work/scratch/watch_desktop.py", "fetch", "운영 도구: 데스크톱 저장소 공개 웹 페이지 읽기(사람이 실행)", _G_TOOL, ("net:",), 1),
    EgressException("인수인계/도구/work/scratch/watch_desktop.py", "ls_remote", "운영 도구: 데스크톱 저장소 git ls-remote(공개 원격, 사람이 실행)", _G_TOOL, ("proc:",), 1),
    EgressException("인수인계/도구/work/scratch/watch_light.py", "fetch", "운영 도구: 블로그 저장소 공개 웹 페이지 읽기(사람이 실행)", _G_TOOL, ("net:",), 1),
    EgressException("인수인계/도구/work/scratch/watch_light.py", "ls_remote", "운영 도구: 블로그 저장소 git ls-remote(공개 원격, 사람이 실행)", _G_TOOL, ("proc:",), 1),
)

# 호출 목록 시험이 '관문을 거침'으로 인정하는 호출 이름(같은 함수에서 같은 주소 식으로 앞서·지배하며 문장으로 불렀을 때만 — tests/egress_scan.py 머리말). `source_policy.egress_gate` 는
# legacy 에서 아무 일도 하지 않으므로 넣지 않는다(그 호출이 있는 곳은 위 예외 목록에 '어느 모드에서 막는지'와 함께 올라 있다).
GATE_CALLS = ("egress.check_url",)


class EgressDenied(Exception):
    """허용 목록 밖이거나 ACTIVE 가 아닌 곳으로 나가려 했다. 문구에는 호스트·목적·사유만 있다 — 쿼리·토큰·경로는 어디에도 없다."""

    def __init__(self, host, purpose, reason):
        self.host = host
        self.purpose = purpose if isinstance(purpose, str) and len(purpose) <= 32 and purpose.isidentifier() else "(형식 오류)"
        self.reason = reason
        super().__init__(f"외부 호출 거부: 호스트 {host} (목적 {self.purpose}) — {reason}")


def _valid_repo(own_repo):
    return isinstance(own_repo, str) and bool(_REPO_RE.fullmatch(own_repo)) and own_repo.split("/", 1)[1] not in (".", "..")


def _ops_denial(host, path, purpose, own_repo):
    """운영 호스트 규칙에 맞으면 None, 아니면 거부 사유(문구에 경로·목적 글자를 싣지 않는다)."""
    rule = _OPS_BY_HOST[host]
    if not (isinstance(purpose, str) and purpose in rule.purposes):
        return f"운영 호스트 {host} 는 운영 목적({'·'.join(rule.purposes)})에서만 열려 있음 — 일반 웹 읽기·fact·모르는 목적은 거부"
    needs_repo = False
    for pattern in rule.paths:
        if "{repo}" in pattern:
            needs_repo = True
            if not _valid_repo(own_repo):
                continue
            pattern = pattern.replace("{repo}", re.escape(own_repo))
        if re.fullmatch(pattern, path):
            return None
    if needs_repo and not _valid_repo(own_repo):
        return f"운영 호스트 {host} 의 저장소 경로는 자기 저장소 이름(own_repo, owner/repo 꼴)이 주어져야 하고 이 경로는 그 밖임"
    return f"이 경로는 운영 호스트 {host} 의 허용 경로가 아님(자기 저장소의 알려진 경로만 열려 있음)"


def check_url(url, purpose, registry, own_repo=None):
    """허용이면 조용히 돌아가고(None), 아니면 EgressDenied. 허용: 운영 호스트의 허용 목적·허용 경로(https·443, `own_repo` 가 있어야 열리는 GitHub 저장소 경로 포함)이거나 registry 의 ACTIVE Provider 가
    그 호스트·경로를 접근 경로로 두고 목적이 허용 목적(`fact`)인 경우. registry 가 None 이면 운영 호스트 규칙만 본다. 일반 웹 읽기(feed·page·resolve)와 모르는 목적은 어디서도 거부된다.
    **첫 주소만 판정한다** — 리다이렉트는 `build_checked_opener`·`check_final_url` 의 일이다."""
    host, path, reason = sr.split_https_url(url)
    if reason is not None:
        raise EgressDenied(host or sr.UNKNOWN_HOST, purpose, f"주소 거부: {reason}")
    if host in OPS_HOSTS:
        why = _ops_denial(host, path, purpose, own_repo)
        if why is None:
            return None
        raise EgressDenied(host, purpose, why)                     # 운영 호스트는 허용 목록으로 넘어가지 않는다 — 운영 규칙에 맞지 않으면 거부가 끝이다
    if registry is None:
        allowed, why = False, "허용 목록(Registry)이 주어지지 않아 운영 호스트(OPS_RULES) 말고는 거부"
    else:
        allowed, why = registry.is_url_allowed(url, purpose)
    if allowed:
        return None
    raise EgressDenied(host, purpose, why)


def check_final_url(response_url, purpose, registry, own_repo=None):
    """응답의 최종 주소(`response.geturl()`)를 다시 판정한다 — 허용이면 None, 아니면 EgressDenied. 리다이렉트를 따라간 요청이 허용 밖으로 나갔는지 요청 뒤에 확인하는 도우미이며,
    이미 요청이 나간 뒤라는 점에서 `build_checked_opener` 보다 약하다(어댑터는 opener 를 쓰는 것이 먼저다)."""
    check_url(response_url, purpose, registry, own_repo)


class _CheckedHandler(urllib.request.BaseHandler):
    """요청을 보내기 전에 — 첫 요청과 리다이렉트로 새로 만든 요청 모두 — check_url 로 판정한다."""
    handler_order = 100                                           # 기본 처리기(500)보다 먼저 돈다

    def __init__(self, purpose, registry, own_repo):
        self._purpose, self._registry, self._own_repo = purpose, registry, own_repo

    def https_request(self, request):
        check_url(request.full_url, self._purpose, self._registry, self._own_repo)
        return request

    http_request = https_request                                  # http 주소는 check_url 이 'https 만 허용'으로 거부한다


class _CheckedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가기 전에 새 주소를 check_url 로 판정하고(허용 밖이면 EgressDenied) 최대 max_redirects 번까지만 따라간다. 다른 호스트로 따라갈 때는 인증 머리글을 뗀다."""

    def __init__(self, purpose, registry, own_repo, max_redirects):
        self._purpose, self._registry, self._own_repo = purpose, registry, own_repo
        self._max_redirects = max_redirects
        self.max_repeats = 1                                       # 같은 주소로 되돌아가는 반복은 허용하지 않는다(기본 처리기 규칙)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        hops = sum((getattr(req, "redirect_dict", None) or {}).values())        # 이 요청에 이르기까지 따라온 리다이렉트 수
        if hops >= self._max_redirects:
            raise urllib.error.HTTPError(req.full_url, code, f"{msg} — 리다이렉트는 {self._max_redirects}번까지만 따라간다", headers, fp)
        check_url(newurl, self._purpose, self._registry, self._own_repo)
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(new.full_url).hostname != urllib.parse.urlsplit(req.full_url).hostname:
            for name in [n for n in new.headers if n.lower() in _SENSITIVE_HEADERS]:
                del new.headers[name]
        return new


# ----------------------------------------------------------------------------
# AI 입력 거부: ai_use NEVER Provider 의 자료는 AI 처리기에 넘기지 않는다
# ----------------------------------------------------------------------------
class AiInputDenied(Exception):
    """그 Provider 의 자료를 AI 처리기에 넘기려 했지만 거부됐다. 문구에는 Provider 식별자·범위 이름·사유만 있다 — 자료의 내용은 어디에도 없다."""

    def __init__(self, provider_id, scope, reason):
        self.provider_id = provider_id if isinstance(provider_id, str) and sr._ID_RE.fullmatch(provider_id) else "(형식 오류)"
        self.scope = scope if isinstance(scope, str) and len(scope) <= 64 and scope.replace("_", "").isalnum() else "(형식 오류)"
        self.reason = reason
        super().__init__(f"AI 입력 거부: Provider {self.provider_id} (범위 {self.scope}) — {reason}")


def check_ai_input(provider_id, scope, registry):
    """그 Provider 의 자료를 AI 처리기(Gemini 등)에 넘겨도 되는가 — 허용이면 None, 아니면 AiInputDenied(항상 닫힌 쪽).
    ① ai_use 가 NEVER 면 scope 가 무엇이든(AI 처리기 정책의 input_scope 포함) **항상 거부**한다 — 이 자료는 규칙 기반 경로에서만 쓰기로 했다(strict 판정이 ai_input 칸을 건너뛰는 대가).
    ② 그 밖은 ACTIVE 이고 ai_input 칸이 알려졌고 DENIED 가 아니며 scope 가 AI 처리기 정책의 input_scope(Signal 과 검증된 최소 Fact)일 때만 허용한다.
    registry 가 None·모르는 Provider·모르는 범위는 모두 거부. 입출력이 없다(정책 파일을 읽지 않는다)."""
    if registry is None:
        raise AiInputDenied(provider_id, scope, "허용 목록(Registry)이 주어지지 않아 AI 입력 가능 여부를 알 수 없음")
    provider = registry.get(provider_id) if isinstance(provider_id, str) else None
    if provider is None:
        raise AiInputDenied(provider_id, scope, "허용 목록에 없는 Provider")
    if getattr(provider, "ai_use", sr.DEFAULT_AI_USE) == "NEVER":
        raise AiInputDenied(provider_id, scope, "이 Provider 의 자료는 AI 에 넘기지 않는다(ai_use NEVER — 규칙 기반 경로 전용). AI 처리기 정책의 input_scope 와 상관없이 항상 거부")
    if not registry.is_active(provider_id):
        raise AiInputDenied(provider_id, scope, "ACTIVE 가 아닌 Provider 의 자료는 AI 에 넘기지 않음")
    if scope != sr.AI_FIXED["input_scope"]:
        raise AiInputDenied(provider_id, scope, f"AI 처리기 정책의 input_scope({sr.AI_FIXED['input_scope']})와 다른 범위")
    cell = provider.policy.ai_input
    if cell.state not in ("ALLOWED", "CONDITIONAL") or not cell.known:
        raise AiInputDenied(provider_id, scope, "ai_input 칸이 AI 입력을 허락한다고 확인되지 않음")


# ----------------------------------------------------------------------------
# 호출 예산: 제공처 호출 한도를 지키는 자리(새 영구 상태 없음 — 한 실행 안의 상한과 호출 전 선행 조건)
# ----------------------------------------------------------------------------
RUNS_PER_DAY_BOUND = 30        # 정기 실행 매시 17·47분 + 후보가 없을 때 슬롯 창에서 반복 → 하루 30번 안팎(docs/ARCHITECTURE.md 4-8). 영구 상태 없이 하루 한도를 한 실행 몫으로 나눌 때 쓴다
MAX_RUN_CALLS = 20             # 한 실행이 한 Provider 에 보낼 수 있는 호출의 절대 상한(한도가 아무리 커도)
MAX_FAILURES = 3               # 실패가 이만큼 쌓이면 그 실행에서 그 Provider 는 건너뛴다
CACHE_MAX_ENTRIES = 32         # 같은 실행 안에서 재사용하려고 들고 있는 성공 응답의 최대 수


class CallBudgetDenied(Exception):
    """호출 예산이 이 호출을 막았다(요청을 보내지 않았다). code: PRECONDITION(하루·주간 상한 등 선행 조건이 이미 막음)·STOPPED_BY_STATUS(403·429)·STOPPED_URL(404)·SKIPPED_AFTER_FAILURES(실패 3회)·RETRY_CAP(같은 주소 재시도 상한)·RUN_CAP(한 실행 상한).
    문구에는 Provider 식별자와 사유만 있다 — 주소·토큰은 어디에도 없다."""

    def __init__(self, provider_id, code, reason):
        self.provider_id = provider_id if isinstance(provider_id, str) and sr._ID_RE.fullmatch(provider_id) else "(형식 오류)"
        self.code = code
        self.reason = reason
        super().__init__(f"호출 예산 거부 {code}: Provider {self.provider_id} — {reason}")


def run_call_cap(rate_limit, runs_per_day=RUNS_PER_DAY_BOUND, hard_cap=MAX_RUN_CALLS):
    """레지스트리 rate_limit 에서 **한 실행**의 호출 상한을 계산한다.
    - 글자('N/minute'·'N per hour'·'N/day', 여럿이면 가장 빡빡한 쪽): 영구 상태가 없으므로 하루 한도는 실행 횟수(runs_per_day)로 나눈 몫이고, 초·분·시 단위 한도는 한 실행(한 시간보다 짧다)이 그 횟수를 넘지 않게 한다.
    - 구조화 RateLimit: official 이 NONE(공식 수치 한도 없음)이면 우리 자체 상한(own)에서 — 글 하나가 재시도까지 쓰는 호출 수(제품 수 × 제품당 호출 × (1 + 재시도))와 하루 상한 가운데 작은 쪽. 하루·월 합계는
      영구 상태가 있어야 지킬 수 있어 여기서 나누지 않는다(선행 조건과 어댑터의 몫). official 이 문구면 그 문구의 몫도 함께 적용한다.
    한도를 모르거나(None·읽을 수 없음) 몫이 0 이면 0 — 호출하지 않는다(닫힌 쪽). 구조화 API 어댑터는 리다이렉트를 따라가지 않는 opener(`build_checked_opener(..., max_redirects=0)`)와 함께 써야 호출 한 번이 요청 한 번이다."""
    caps = [hard_cap]
    own = None
    if isinstance(rate_limit, dict):
        rate_limit = sr._build_rate_limit(rate_limit) if not sr._rate_limit_object_problems(rate_limit) else None
    if isinstance(rate_limit, sr.RateLimit):
        own = rate_limit.own
        numeric = sr.parse_rate_limit(rate_limit.official) if rate_limit.official != sr.RATE_OFFICIAL_NONE else None
        if own is None and not numeric:
            return 0
        if own is not None:
            caps += [own.max_products_per_post * own.max_calls_per_product_per_post * (1 + own.max_retries), own.max_calls_per_day]
        clauses = numeric or ()
    else:
        clauses = sr.parse_rate_limit(rate_limit)
        if not clauses:
            return 0
    for count, unit in clauses:
        seconds = sr.RATE_UNITS[unit]
        caps.append(count * (86400 // seconds) // runs_per_day)
        if seconds <= 3600:
            caps.append(count)
    return max(0, min(caps))


def budget_for(provider_id, rate_limit, precondition=None):
    """레지스트리 접근 경로의 rate_limit 에서 만든 CallBudget(한 실행 몫). 구조화 한도가 있으면 재시도 횟수·실패 상한을 그 값에서, 없으면 기본(재시도 1번·실패 3번)을 쓴다. 한도를 모르면 상한 0 이라 호출이 모두 거부된다."""
    own = rate_limit.own if isinstance(rate_limit, sr.RateLimit) else None
    return CallBudget(provider_id, run_call_cap(rate_limit), max_retries=own.max_retries if own else 1, precondition=precondition)


class CallBudget:
    """한 실행(프로세스) 안의 호출 예산 — 새 영구 상태를 만들지 않는다. 호출 전에 `before(url)` 로 확인하고(허용이면 호출 수 +1, 아니면 CallBudgetDenied), 실패하면 `failed()`, 성공 응답은 `remember(url, body)`.
    - `max_calls`: 이 실행이 보낼 수 있는 호출 수(`run_call_cap(rate_limit)` 값, 0 이면 한 번도 부르지 않는다)
    - `max_failures`: 실패 누적이 이 수에 닿으면 그 실행에서 건너뜀(기본 3회)
    - `max_retries`: 같은 주소를 실패한 뒤 다시 부를 수 있는 횟수(기본 1번 — 같은 주소는 한 실행에서 최대 1 + max_retries 번)
    - 403·429 를 받으면 그 실행에서 그 Provider 를 중지하고(IP 차단 가능성), 404 를 받으면 그 주소만 중지한다(24시간 중지는 영구 상태가 없어 이 실행 안에서만)
    - `precondition`: 호출 전에 부르는 함수 — 비어 있지 않은 사유 글자를 돌려주면(또는 예외가 나면) 호출 0. 하루·주간 발행 상한이 이미 막았을 때 제공처를 부르지 않게 하는 자리다.
    같은 주소의 성공 응답은 이 실행 안에서 다시 부르지 않고 `cached(url)` 로 재사용한다(최대 CACHE_MAX_ENTRIES 개)."""

    def __init__(self, provider_id, max_calls, max_failures=MAX_FAILURES, precondition=None, max_retries=1):
        if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 0:
            raise ValueError("max_calls 는 0 이상 정수여야 합니다")
        if isinstance(max_failures, bool) or not isinstance(max_failures, int) or max_failures < 1:
            raise ValueError("max_failures 는 1 이상 정수여야 합니다")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries 는 0 이상 정수여야 합니다")
        if precondition is not None and not callable(precondition):
            raise ValueError("precondition 은 함수여야 합니다")
        self.provider_id = provider_id
        self.max_calls = max_calls
        self.max_failures = max_failures
        self.max_retries = max_retries
        self.precondition = precondition
        self.calls = 0
        self.failures = 0
        self.blocked = False                                    # 403·429 를 받았다 — 이 실행에서 그 Provider 를 더 부르지 않는다
        self._attempts = {}                                     # 주소 → 보낸 횟수(재시도 상한)
        self._dead = set()                                      # 404 를 받은 주소 — 이 실행에서 다시 부르지 않는다
        self._cache = {}

    @property
    def skipped(self):
        return self.failures >= self.max_failures

    def before(self, url):
        """호출 전 확인. 허용이면 호출 수를 하나 올리고 None, 아니면 CallBudgetDenied(요청을 보내지 않는다). 순서: 선행 조건 → 실패 건너뜀 → 한 실행 상한."""
        if self.precondition is not None:
            try:
                reason = self.precondition()
            except Exception:                                   # noqa: BLE001 — 선행 조건을 확인할 수 없으면 닫힌 쪽
                reason = "선행 조건을 확인하지 못함"
            if reason:
                raise CallBudgetDenied(self.provider_id, "PRECONDITION", str(reason)[:120])
        if self.blocked:
            raise CallBudgetDenied(self.provider_id, "STOPPED_BY_STATUS", "403·429 를 받아 이 실행에서 이 Provider 를 더 부르지 않음(차단 가능성 — 문의는 사람이 결정)")
        if url in self._dead:
            raise CallBudgetDenied(self.provider_id, "STOPPED_URL", "404 를 받은 주소라 이 실행에서 다시 부르지 않음(폐지·이전 가능성)")
        if self.skipped:
            raise CallBudgetDenied(self.provider_id, "SKIPPED_AFTER_FAILURES", f"이 실행에서 실패가 {self.failures}번 쌓여 건너뜀(상한 {self.max_failures}번)")
        if self._attempts.get(url, 0) >= 1 + self.max_retries:
            raise CallBudgetDenied(self.provider_id, "RETRY_CAP", f"같은 주소를 이미 {self._attempts[url]}번 불렀음(재시도는 {self.max_retries}번까지)")
        if self.calls >= self.max_calls:
            raise CallBudgetDenied(self.provider_id, "RUN_CAP", f"이 실행의 호출 상한 {self.max_calls}번을 다 씀")
        self.calls += 1
        self._attempts[url] = self._attempts.get(url, 0) + 1

    def unsent(self, url=None):
        """before 가 허용했지만 요청이 나가지 않았을 때(관문이 거부) 호출 수를 되돌린다."""
        self.calls = max(0, self.calls - 1)
        if url in self._attempts:
            self._attempts[url] = max(0, self._attempts[url] - 1)

    def failed(self, status=None, url=None):
        """호출이 실패했다. status 가 403·429 면 이 실행에서 그 Provider 를 중지하고 404 면 그 주소(url)를 중지한다."""
        self.failures += 1
        if status in (403, 429):
            self.blocked = True
        elif status == 404 and url is not None:
            self._dead.add(url)

    def cached(self, url):
        """이 실행에서 이미 성공한 같은 주소의 응답(없으면 None)."""
        return self._cache.get(url)

    def remember(self, url, body):
        if url in self._cache or len(self._cache) < CACHE_MAX_ENTRIES:
            self._cache[url] = body


def budgeted(opener, budget):
    """주입되는 `opener(url, *, timeout, max_bytes) -> bytes` 를 호출 예산으로 감싼다. 같은 주소의 성공 응답은 다시 부르지 않고 돌려주며(호출 수에 세지 않는다), 호출 전에 예산이 막으면 CallBudgetDenied,
    호출이 실패하면(관문의 EgressDenied 는 요청이 나가지 않았으니 제외) 실패로 센다. 예외는 그대로 다시 올린다."""
    def call(url, *, timeout, max_bytes):
        hit = budget.cached(url)
        if hit is not None:
            return hit
        budget.before(url)
        try:
            body = opener(url, timeout=timeout, max_bytes=max_bytes)
        except EgressDenied:
            budget.unsent(url)
            raise
        except Exception as exc:
            budget.failed(getattr(exc, "code", None), url)       # urllib.error.HTTPError 의 상태 번호(그 밖의 오류는 None)
            raise
        budget.remember(url, body)
        return body
    return call


def build_checked_opener(purpose, registry, own_repo=None, max_redirects=MAX_REDIRECTS, https_handler=None):
    """리다이렉트를 막는 opener(urllib.request.OpenerDirector). 첫 요청과 따라가는 모든 리다이렉트의 새 주소를 `check_url` 로 판정하고 허용이 아니면 EgressDenied 를 올린다(최대 `max_redirects`=3번).
    https 만 다루는 처리기만 붙인다 — 파일·FTP·데이터 주소·환경 변수 프록시 처리기는 없다. `https_handler` 는 시험이 가짜 전송을 끼우려는 자리(기본은 표준 HTTPSHandler)."""
    opener = urllib.request.OpenerDirector()
    for handler in (_CheckedHandler(purpose, registry, own_repo), _CheckedRedirectHandler(purpose, registry, own_repo, max_redirects),
                    https_handler if https_handler is not None else urllib.request.HTTPSHandler(), urllib.request.HTTPDefaultErrorHandler(),
                    urllib.request.HTTPErrorProcessor(), urllib.request.UnknownHandler()):
        opener.add_handler(handler)
    return opener
