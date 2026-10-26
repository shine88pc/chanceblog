"""게시 어댑터 공통 타입."""
from dataclasses import dataclass

from pipeline.llm import mask

MIN_REDACT_LEN = 6  # 이보다 짧은 값은 일반 단어와 겹쳐 오탐이 많아 치환하지 않는다(실제 시크릿은 훨씬 길다)


def redact(text, secrets=()):
    """로그·이력에 쓸 문구에서 비밀을 가린다: 비밀 모양 패턴(llm.mask)에 더해, 이 실행이 가진 실제 값(블로그 ID·
    클라이언트 ID·클라이언트 시크릿·refresh token)을 글자 그대로 찾아 가린다. API 오류 문구는 요청 주소를 담는데
    그 안에 블로그 ID 가 들어 있어 패턴만으로는 못 가린다(D-31)."""
    out = mask(text)
    for value in secrets or ():
        value = str(value or "")
        if len(value) >= MIN_REDACT_LEN:
            out = out.replace(value, "***")
    return out


class PublishError(RuntimeError):
    """게시 실패. code 로 원인을 분류한다.

    auth_expired : refresh token 만료/폐기 (OAuth 동의 화면이 '테스트' 상태면 7일 후 만료)
    auth_failed  : 인증/권한 오류(클라이언트 값 불일치, 블로그 접근 불가: 401·403·404)
    blog_mismatch: 인증은 통과했지만 블로그 주소가 레지스트리와 다름(엉뚱한 블로그에 쓰지 않으려고 멈춘다)
    network      : 연결 실패·시간 초과 같은 네트워크 오류(재시도 후에도 실패)
    bad_response : API 응답에 필요한 값(id·url)이 없거나 요청과 다른 상태(초안 요청인데 공개 등)
    api_error    : 그 밖의 API 오류(HTTP 오류 상태, 재시도 후에도 실패)
    unexpected   : (러너가 붙이는 분류) 어댑터가 분류하지 못한 예외
    post_id      : 응답에서 글 ID 를 읽었는데 다른 값이 틀렸다면 그 ID(Blogger 화면에서 찾아 지울 수 있게)
    """

    def __init__(self, message, code="api_error", post_id=""):
        super().__init__(message)
        self.code = code
        self.post_id = post_id


@dataclass
class PublishResult:
    post_id: str
    url: str
    draft: bool = False
