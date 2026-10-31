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


def _alert_result(environ, out, blog, status, title, url):
    """게시·초안함 업로드 성공을 텔레그램으로 알린다(보조 알림, pipeline/notify.py). 시크릿 TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID 가 없으면 아무것도 하지 않고
    출력도 만들지 않는다(기존 동작과 바이트 단위로 같다). 알림이 실패하거나 예외가 나도 게시 결과·이력·요약·종료 코드는 바뀌지 않는다 —
    로그에 한 줄과 고정 문장 ::warning:: 만 더한다(토큰·채팅 ID 는 어디에도 쓰지 않는다)."""
    try:
        notifier = notify.Notifier(environ)
        if not notifier.enabled:
            return
        result = notifier.notify_blogger_result(status, title, url=url, blog_label=blog["channel"]["label"], extra_prefixes=(blog["url"],))
        notify.log_result(result, out)
    except Exception as exc:  # noqa: BLE001 - 알림은 보조다: 어떤 예외도 글 게시 결과를 바꾸지 못한다(클래스 이름만 남긴다. 예외 문구에 요청 주소가 있을 수 있다)
        out(f"[참고] 텔레그램 알림 중 예기치 않은 오류({type(exc).__name__}) — 게시 결과에는 영향이 없습니다")


def _checked_result(result, as_draft=False):
    """게시 결과의 글 ID·주소를 검사한다. 비어 있으면 PublishError(bad_response) — 어댑터가 이미 검사하지만, 다른 어댑터나
    가짜 어댑터가 빈 값을 돌려줘도 '게시 성공'으로 기록하지 않는다. 초안함 업로드(as_draft)는 글 ID 만 있으면 올라간 것이고
    주소는 빈칸일 수 있다(어댑터와 같은 기준 — 초안 응답에 url 이 오는지는 실제 호출로 확인해야 한다). 즉시 게시는 주소가 필수다."""
    post_id = str(getattr(result, "post_id", "") or "").strip()
    url = str(getattr(result, "url", "") or "").strip()
    if not post_id or (not url and not as_draft):
        raise PublishError("게시 결과에 글 ID" + ("" if as_draft else " 또는 주소(url)") + "가 없습니다"
                           "(Blogger 화면에서 글이 만들어졌는지 확인하세요)", code="bad_response", post_id=post_id)
    return post_id, url
