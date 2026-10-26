"""Blogger 인증 점검(사전 점검): 쓰기 없이 '토큰 갱신 → blogs.get → 블로그 주소 일치'만 확인한다.

글을 올리기 전에(Gemini 를 부르기 전에) 한 번 부른다. 하나라도 실패하면 게시·업로드를 하지 않고 실패 분류를 돌려준다.

  1. refresh token 으로 access token 을 갱신한다(만료·폐기·클라이언트 값 오류·네트워크 오류를 가른다).
  2. blogs.get 으로 BLOGGER_BLOG_ID 의 블로그를 조회한다(권한·존재 여부).
  3. 돌려준 블로그 주소가 레지스트리(pipeline/blogs.json)의 url 과 같은지 본다. 같은 구글 계정의 다른 블로그 ID 를
     넣어도 1·2번은 통과하므로, 이 비교가 엉뚱한 블로그에 쓰는 사고를 막는 마지막 문이다.

이 모듈은 순수 로직이다(입출력 없음). 로그·요약·종료 코드 처리는 pipeline/run.py 가 한다.

종료 코드 기준(docs/ENGINEERING_GUIDE.md R6: 설정 오류 2 / 인프라 실패 1):
  2 설정 — 사람이 설정(블로그 ID·계정 권한·클라이언트 ID/시크릿)을 고쳐야 한다. 다시 실행해도 같은 결과다.
  1 인프라 — 시간이 지나 생기는 외부 상태(토큰 만료·폐기)나 일시 오류(네트워크·API 오류). 다시 실행하면 풀리거나,
             토큰만 새로 발급하면 된다(설정 값을 고치는 것이 아니다).
"""
import re
from urllib.parse import urlsplit

from pipeline.publishers.base import PublishError

# PublishError.code → (사전 점검 실패 때 종료 코드, 이름, 운영자에게 보이는 고정 안내 문장).
# 안내 문장은 ::error:: 주석에도 그대로 쓰므로 외부·AI 유래 문자열을 넣지 않는다(고정 문장만).
FAILURES = {
    "auth_expired": (1, "인증 만료",
                     "Blogger 인증(refresh token)이 만료되었거나 폐기되었습니다. OAuth 동의 화면이 '프로덕션' 상태인지 확인하고 "
                     "토큰을 새로 발급해 BLOGGER_REFRESH_TOKEN 시크릿을 갱신하세요(.github/editorial/BLOGGER_API_SETUP.md)."),
    "auth_failed": (2, "권한·접근 불가",
                    "Blogger 인증 또는 블로그 접근 권한 확인에 실패했습니다. BLOGGER_BLOG_ID·BLOGGER_CLIENT_ID·"
                    "BLOGGER_CLIENT_SECRET 시크릿, Blogger API 사용 설정, 로그인한 계정의 블로그 권한을 확인하세요."),
    "blog_mismatch": (2, "블로그 주소 불일치",
                      "인증은 통과했지만 BLOGGER_BLOG_ID 가 가리키는 블로그의 주소가 레지스트리(pipeline/blogs.json)의 url 과 다릅니다. "
                      "엉뚱한 블로그에 쓰지 않도록 멈췄습니다. 블로그 ID 시크릿을 확인하세요."),
    "network": (1, "네트워크 오류",
                "Blogger 서버에 연결하지 못했습니다(연결 실패·시간 초과). 잠시 뒤 다시 실행하세요."),
    "bad_response": (1, "응답 이상",
                     "Blogger 가 필요한 값이 빠진 응답을 돌려줬습니다. 이 단계의 로그를 확인하고 잠시 뒤 다시 실행하세요."),
    "api_error": (1, "API 오류",
                  "Blogger API 가 오류를 돌려줬습니다. 이 단계의 로그를 확인하고 잠시 뒤 다시 실행하세요."),
    "unexpected": (1, "예기치 않은 오류",
                   "인증 점검 중 예기치 않은 오류가 났습니다. 이 단계의 로그를 확인하세요."),
}
KNOWN_CODES = frozenset(FAILURES)
# Blogger 호스트: <이름>.blogspot.com 또는 국가별 도메인(blogspot.kr · blogspot.co.uk · blogspot.com.au). 끝이 이 모양이어야 해서
# 'x.blogspot.com.evil.example' 같은 다른 도메인은 Blogger 주소로 읽지 않는다.
_BLOGSPOT_RX = re.compile(r"^([a-z0-9-]+)\.blogspot\.(?:com|[a-z]{2}|com?\.[a-z]{2})$")


def safe_code(code):
    """로그·이력에 쓸 분류 코드. 어댑터가 낸 값이 목록에 없으면(새 어댑터의 임의 문자열 등) api_error 로 접는다."""
    return code if code in KNOWN_CODES else "api_error"


def exit_code_for(code):
    return FAILURES[safe_code(code)][0]


def label_for(code):
    return FAILURES[safe_code(code)][1]


def sentence_for(code):
    return FAILURES[safe_code(code)][2]


def normalize_blog_url(url):
    """블로그 주소를 비교용으로 정규화한다: 스킴(http/https)·대소문자·'www.'·끝 슬래시를 무시한다.

    Blogger 블로그는 방문자 위치에 따라 blogspot.kr 같은 국가별 도메인으로 보이기도 해서 *.blogspot.<국가 도메인> 은
    *.blogspot.com 으로 본다(같은 블로그. 추정 — blogs.get 이 어느 쪽을 돌려주는지는 실제 호출로 확인해야 한다)."""
    text = str(url or "").strip().lower()
    if not text:
        return ""
    if "://" not in text:
        text = "//" + text  # 스킴 없이 적힌 주소도 호스트로 읽히게 한다
    try:
        parts = urlsplit(text)
        host = parts.hostname or ""
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return ""  # 호스트를 읽지 못한 주소는 '주소 없음'이다(경로만 남은 값끼리 같아 보이면 안 된다)
    match = _BLOGSPOT_RX.match(host)
    if match:
        host = match.group(1) + ".blogspot.com"
    return host + parts.path.rstrip("/")


def urls_match(returned_url, expected_url):
    """두 주소가 같은 블로그를 가리키는가(어느 쪽이든 비어 있으면 같다고 보지 않는다)."""
    returned, expected = normalize_blog_url(returned_url), normalize_blog_url(expected_url)
    return bool(returned) and returned == expected


def auth_check(publisher, expected_url):
    """쓰기 없는 사전 점검. 통과하면 blogs.get 의 {'name', 'url'} 을 돌려주고(출력하지 말 것: 같은 계정의 다른 블로그일 수 있다),
    실패하면 PublishError(code)를 일으킨다. code 는 FAILURES 의 키다(분류·종료 코드는 위 표).

    publisher 는 healthcheck() -> {'name': ..., 'url': ...} 를 가진 어댑터다(토큰 갱신과 blogs.get 은 그 안에서 한다)."""
    info = publisher.healthcheck()
    returned = info.get("url") if isinstance(info, dict) else None
    if not isinstance(returned, str) or not returned.strip():
        raise PublishError("블로그 조회 응답에 주소(url)가 없어 레지스트리와 비교하지 못했습니다", code="bad_response")
    if not urls_match(returned, expected_url):
        # 응답의 주소는 문구에 넣지 않는다: 잘못 넣은 ID 가 같은 계정의 다른(비공개일 수 있는) 블로그를 가리키면
        # 그 주소가 공개 저장소의 Actions 로그·이력에 남는다.
        raise PublishError("BLOGGER_BLOG_ID 가 가리키는 블로그의 주소가 레지스트리의 url 과 다릅니다"
                           "(응답 주소는 다른 블로그일 수 있어 출력하지 않습니다)", code="blog_mismatch")
    return info
