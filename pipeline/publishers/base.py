"""게시 어댑터 공통 타입."""
from dataclasses import dataclass


class PublishError(RuntimeError):
    """게시 실패. code 로 원인을 분류한다.

    auth_expired : refresh token 만료/폐기 (OAuth 동의 화면이 '테스트' 상태면 7일 후 만료)
    auth_failed  : 인증/권한 오류
    api_error    : 그 밖의 API 오류(재시도 후에도 실패)
    """

    def __init__(self, message, code="api_error"):
        super().__init__(message)
        self.code = code


@dataclass
class PublishResult:
    post_id: str
    url: str
    draft: bool = False
