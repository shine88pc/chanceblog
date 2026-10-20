"""Blogger API v3 어댑터 (refresh token 방식).

- 인증 실패(invalid_grant 등)는 PublishError(code=auth_expired/auth_failed)로 구분한다.
- 일시 오류(429/5xx)는 백오프 재시도. 재시도 전에 같은 제목 글이 이미 올라갔는지 확인해
  '서버는 처리했는데 응답만 실패한' 경우의 중복 게시를 막는다.
- google 라이브러리는 실제 호출 때만 import 한다(테스트는 service_factory 로 가짜를 주입).
"""
import time
from datetime import datetime, timedelta, timezone

from pipeline.llm import mask
from pipeline.publishers.base import PublishError, PublishResult

SCOPES = ["https://www.googleapis.com/auth/blogger"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
_TRANSIENT = {429, 500, 502, 503, 504}
EXPIRED_HINT = ("refresh token이 만료/폐기됐습니다. OAuth 동의 화면이 '테스트' 상태이면 7일 뒤 만료됩니다 → "
                "'프로덕션(게시)'으로 전환 후 토큰 재발급 (docs/SECURITY_GUARDRAILS.md D-11)")


def _status_of(exc):
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


class BloggerPublisher:
    def __init__(self, blog_id, client_id, client_secret, refresh_token,
                 service_factory=None, sleep=time.sleep, retries=2, now=None):
        self.blog_id = blog_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._factory = service_factory
        self._sleep = sleep
        self._retries = retries
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._svc = None

    # -- 인증/서비스 ---------------------------------------------------------
    def _service(self):
        if self._svc is not None:
            return self._svc
        if self._factory:
            self._svc = self._factory()
            return self._svc
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds = Credentials(token=None, refresh_token=self._refresh_token, token_uri=TOKEN_URI,
                            client_id=self._client_id, client_secret=self._client_secret, scopes=SCOPES)
        try:
            creds.refresh(Request())
        except Exception as exc:  # noqa: BLE001
            text = mask(exc)
            if "invalid_grant" in text or "expired" in text.lower() or "revoked" in text.lower():
                raise PublishError(f"{EXPIRED_HINT} | {text[:160]}", code="auth_expired") from exc
            raise PublishError(f"토큰 갱신 실패: {text[:200]}", code="auth_failed") from exc
        self._svc = build("blogger", "v3", credentials=creds, cache_discovery=False)
        return self._svc

    # -- 공개 API -----------------------------------------------------------
    def healthcheck(self):
        """대상 블로그에 접근할 수 있는지 확인한다."""
        svc = self._service()
        try:
            blog = svc.blogs().get(blogId=self.blog_id).execute()
        except Exception as exc:  # noqa: BLE001
            status = _status_of(exc)
            code = "auth_failed" if status in (401, 403, 404) else "api_error"
            raise PublishError(f"블로그 접근 확인 실패(status={status}): {mask(exc)[:200]}", code=code) from exc
        return {"name": blog.get("name", ""), "url": blog.get("url", "")}

    def publish(self, title, html, labels=(), draft=False):
        svc = self._service()
        body = {"kind": "blogger#post", "title": title, "content": html}
        if labels:
            body["labels"] = list(labels)
        for attempt in range(self._retries + 1):
            try:
                res = svc.posts().insert(blogId=self.blog_id, body=body, isDraft=draft).execute()
                return PublishResult(post_id=str(res.get("id", "")), url=res.get("url", ""), draft=draft)
            except Exception as exc:  # noqa: BLE001
                status = _status_of(exc)
                if status in (401, 403):
                    raise PublishError(f"권한 오류(status={status}): {mask(exc)[:200]}", code="auth_failed") from exc
                transient = status in _TRANSIENT or isinstance(exc, (TimeoutError, ConnectionError))
                duplicate = self._find_recent(title) if (transient or status is None) else None
                if duplicate:
                    return duplicate  # 응답은 실패했지만 글은 이미 올라가 있다
                if transient and attempt < self._retries:
                    self._sleep(3 * (2 ** attempt))
                    continue
                raise PublishError(f"Blogger 게시 실패(status={status}): {mask(exc)[:200]}", code="api_error") from exc
        raise PublishError("Blogger 게시 실패: 재시도 초과", code="api_error")

    # -- 멱등성 -------------------------------------------------------------
    def _find_recent(self, title, within_minutes=15):
        try:
            res = self._service().posts().list(
                blogId=self.blog_id, maxResults=5, orderBy="published", fetchBodies=False,
                status=["live", "draft"]).execute()
        except Exception:  # noqa: BLE001 - 확인 실패는 '없음'으로 본다
            return None
        cutoff = self._now() - timedelta(minutes=within_minutes)
        for item in res.get("items", []) or []:
            if item.get("title") != title:
                continue
            published = item.get("published", "")
            try:
                when = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when >= cutoff:
                return PublishResult(post_id=str(item.get("id", "")), url=item.get("url", ""),
                                     draft=item.get("status") == "DRAFT")
        return None
