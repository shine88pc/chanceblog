"""플랫폼 어댑터. 새 플랫폼은 여기에 모듈을 추가하고 registry.PLATFORMS 에 등록한다.

어댑터 계약(docs/ARCHITECTURE.md):
- healthcheck() -> dict            : 자격 증명/대상 블로그 접근 가능 여부 확인(실패 시 PublishError)
- publish(title, html, labels, draft=False) -> PublishResult
- 같은 제목 글이 방금 올라갔는지 확인해 재시도 중 중복 게시를 막는다(멱등성)

초안 패키지 어댑터(issue_package.py, 티스토리·네이버)는 게시가 아니라 GitHub 이슈 만들기라 계약이 다르다:
- count_open_drafts(채널 라벨) -> int  : 같은 채널에 열린 초안 이슈 수(적체 점검, 읽기만)
- publish_package(draft) -> PublishResult : 이슈 1개를 만든다(본문 첫 줄의 숨은 표지로 멱등, 라벨 보장). 이슈 만들기는 한 번만 보낸다 — 만들어졌는지
  모호한 실패(응답 유실·시간 초과·서버 오류)는 다시 만들지 않고 같은 표지를 한 번 찾아 있으면 그것을 쓰고 없으면 멈춘다(오류의 `maybe_created` 가 참).
  HTTP 4xx 로 거절되거나 만들기 전에 실패하면 `maybe_created` 가 거짓이다. 입력이 비었거나 어긋나면 code `invalid_draft`, 너무 길면 `too_long`
- notes : 실패는 아니지만 운영자가 알아야 할 일(예: 같은 초안의 이슈가 이미 있어 새로 만들지 않음)
- build_issue(draft) 는 입출력이 없는 순수 함수라 연습 실행이 API 를 부르지 않고 본문을 보인다
"""
from pipeline.publishers.base import PublishError, PublishResult  # noqa: F401
