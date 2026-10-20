"""플랫폼 어댑터. 새 플랫폼은 여기에 모듈을 추가하고 registry.PLATFORMS 에 등록한다.

어댑터 계약(docs/ARCHITECTURE.md):
- healthcheck() -> dict            : 자격 증명/대상 블로그 접근 가능 여부 확인(실패 시 PublishError)
- publish(title, html, labels, draft=False) -> PublishResult
- 같은 제목 글이 방금 올라갔는지 확인해 재시도 중 중복 게시를 막는다(멱등성)
"""
from pipeline.publishers.base import PublishError, PublishResult  # noqa: F401
