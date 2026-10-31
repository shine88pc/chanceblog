def _alert_status_for_result(publisher, status, title):
    """draft 업로드 직후에도 같은 제목이 이미 공개 상태면 '발행 대기' 알림을 보내지 않는다.

    운영자에게는 "게시 대기"와 "이미 게시됨"이 혼동되기 쉬워, 게시 완료 상태가 확인되면
    동일 title 의 LIVE 글을 'posted' 로 정규화해 '게시됨' 문구를 보내도록 한다.
    """
    if status != "draft_uploaded" or publisher is None:
        return status
    try:
        recent = publisher._find_recent(title, within_minutes=60)
    except Exception:  # noqa: BLE001 - 알림은 보조다: 상태 확인 실패는 경고 없이 원래 상태를 유지한다.
        return status
    if recent is not None and not recent.draft:
        return "posted"
    return status
