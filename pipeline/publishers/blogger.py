"""Blogger API v3 어댑터 (refresh token 방식).

- 인증 실패(invalid_grant 등)는 PublishError(code=auth_expired/auth_failed)로 구분한다.
- 일시 오류(429/5xx)는 백오프 재시도. 재시도 전에 같은 제목 글이 이미 올라갔는지 확인해
  '서버는 처리했는데 응답만 실패한' 경우의 중복 게시를 막는다.
- google 라이브러리는 실제 호출 때만 import 한다. 테스트는 service_factory 로 서비스 전체를 가짜로 갈아 끼우거나,
  credentials_factory·request_factory·service_builder 로 구글 인증·서비스 생성 단계만 가짜로 갈아 끼운다
  (그러면 토큰 갱신 실패 분류·재시도·blogs.get·posts.insert(isDraft) 경로를 실제 구글 호출 없이 시험할 수 있다).
- 오류 문구에는 요청 주소(블로그 ID 포함)가 섞여 나오므로, 이 어댑터가 가진 실제 값 4개와 클라이언트 ID 앞 12자리(구글 클라우드
  프로젝트 번호: 'Blogger API has not been used in project <번호>' 같은 403 문구에 실려 나온다)를 글자 그대로 가려서 낸다.
- 중복 확인(posts.list)이 실패해도 게시는 계속하되(확인 실패 = '없음'), 조용히 넘기지 않고 notes 에 마스킹한 한 줄을 남긴다.
  러너가 로그에 [참고] 줄로 찍는다.
- googleapiclient 의 열거값(status·orderBy)은 대소문자를 구분한다: LIVE/DRAFT, PUBLISHED/UPDATED. 소문자로 부르면 요청을 만들기도
  전에 TypeError 가 나서 중복 확인이 늘 꺼진 채 재시도 중복 게시가 난다(V-01).
- 오류 문구가 운영자에게 시크릿 이름을 말할 때(블로그 ID 형식 안내)는 secret_names(레지스트리 블로그 항목의 secrets: 역할 → 이름)에 있는 이름을 쓴다.
  한글 Blogger 는 BLOGGER_KO_* 라서 영문 이름을 박아 두면 영문 값을 고치러 가게 된다(독립 검증 N3). 생략하면 영문 Blogger 의 이름이다.
"""
import json
import re
import time
from datetime import datetime, timedelta, timezone

from pipeline.auth_check import secret_names_for
from pipeline.publishers.base import PublishError, PublishResult, redact

SCOPES = ["https://www.googleapis.com/auth/blogger"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
_TRANSIENT = {429, 500, 502, 503, 504}
# 연결 실패·시간 초과처럼 HTTP 응답 없이 나는 오류의 클래스 이름(google·requests·httplib2 를 import 하지 않고 이름으로 알아본다)
_NETWORK_NAMES = {"TransportError", "ServerNotFoundError", "HttpLib2Error", "ConnectionError", "Timeout",
                  "ConnectTimeout", "ReadTimeout"}
_URL_RX = re.compile(r"^https?://\S+$")
# 403 이라도 권한이 아니라 호출 한도(쿼터·속도 제한) 때문일 때 오류 본문 errors[].reason 에 오는 값. 권한 오류로 오인하면
# 운영자가 멀쩡한 시크릿·API 설정을 고치러 가므로 api_error 로 가른다.
_QUOTA_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded", "dailyLimitExceeded",
                            "dailyLimitExceededUnreg", "sharedRateLimitExceeded"})
EXPIRED_HINT = ("refresh token이 만료/폐기됐습니다. OAuth 동의 화면이 '테스트' 상태이면 7일 뒤 만료됩니다 → "
                "'프로덕션(게시)'으로 전환 후 토큰 재발급 (docs/SECURITY_GUARDRAILS.md D-11)")


def _status_of(exc):
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _http_reasons(exc):
    """구글 API 오류 본문에서 errors[].reason 값들을 읽는다(googleapiclient HttpError 의 content(JSON 바이트)와 error_details).
    읽지 못하면 빈 집합이다(그러면 상태 코드만으로 분류한다)."""
    found = set()
    content = getattr(exc, "content", None)
    if isinstance(content, (bytes, bytearray)):
        try:
            content = bytes(content).decode("utf-8")
        except UnicodeDecodeError:
            content = None
    if isinstance(content, str):
        try:
            body = json.loads(content)
        except ValueError:
            body = None
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict) and isinstance(error.get("errors"), list):
            found.update(item["reason"] for item in error["errors"] if isinstance(item, dict) and isinstance(item.get("reason"), str))
    details = getattr(exc, "error_details", None)
    if isinstance(details, str):
        found.add(details)
    elif isinstance(details, (list, tuple)):
        found.update(item["reason"] for item in details if isinstance(item, dict) and isinstance(item.get("reason"), str))
        found.update(item for item in details if isinstance(item, str))
    return found


def _is_quota_error(exc):
    """403 이면서 사유가 호출 한도(쿼터·속도 제한)인가."""
    return _status_of(exc) == 403 and bool(_http_reasons(exc) & _QUOTA_REASONS)


def _is_network_error(exc):
    """연결 실패·시간 초과처럼 HTTP 응답 없이 난 오류(잠시 뒤 다시 하면 될 수 있는 일시 오류)인가."""
    if isinstance(exc, OSError):  # socket·ssl·requests 의 연결 오류와 내장 TimeoutError·ConnectionError 를 포함한다
        return True
    if getattr(exc, "retryable", False) is True:  # google-auth 가 토큰 서버의 일시 오류에 붙이는 표시
        return True
    return bool({cls.__name__ for cls in type(exc).__mro__} & _NETWORK_NAMES)


class BloggerPublisher:
    def __init__(self, blog_id, client_id, client_secret, refresh_token,
                 service_factory=None, sleep=time.sleep, retries=2, now=None,
                 credentials_factory=None, request_factory=None, service_builder=None, secret_names=None):
        self.blog_id = blog_id
        self._secret_names = secret_names_for(secret_names)  # 오류 문구에 쓰는 시크릿 '이름'(값이 아님). 기본은 영문 Blogger 의 이름
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._factory = service_factory
        self._credentials_factory = credentials_factory  # (client_id, client_secret, refresh_token) -> 자격 증명 객체
        self._request_factory = request_factory          # () -> 토큰 갱신 때 쓰는 HTTP 요청 객체
        self._service_builder = service_builder          # (api, version, credentials=..., cache_discovery=...) -> 서비스
        self._sleep = sleep
        self._retries = retries
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._svc = None
        self.notes = []   # 실패하지 않았지만 운영자가 알아야 할 일(예: 중복 확인 실패)을 마스킹한 한 줄로 쌓는다. 러너가 로그에 찍는다

    def _scrub(self, exc):
        """오류 문구에서 비밀(패턴 + 이 어댑터가 가진 실제 값 + 클라이언트 ID 앞 12자리 프로젝트 번호)을 가린다."""
        project_number = str(self._client_id or "").split("-")[0]
        return redact(exc, (self.blog_id, self._client_id, self._client_secret, self._refresh_token, project_number))

    # -- 인증/서비스 ---------------------------------------------------------
    def _service(self):
        if self._svc is not None:
            return self._svc
        if self._factory:
            self._svc = self._factory()
            return self._svc
        creds = self._new_credentials()
        self._refresh_credentials(creds, self._new_request())
        self._svc = self._build_service(creds)
        return self._svc

    def _new_credentials(self):
        if self._credentials_factory:
            return self._credentials_factory(self._client_id, self._client_secret, self._refresh_token)
        from google.oauth2.credentials import Credentials
        return Credentials(token=None, refresh_token=self._refresh_token, token_uri=TOKEN_URI,
                           client_id=self._client_id, client_secret=self._client_secret, scopes=SCOPES)

    def _new_request(self):
        if self._request_factory:
            return self._request_factory()
        from google.auth.transport.requests import Request
        return Request()

    def _build_service(self, creds):
        if self._service_builder:
            return self._service_builder("blogger", "v3", credentials=creds, cache_discovery=False)
        from googleapiclient.discovery import build
        return build("blogger", "v3", credentials=creds, cache_discovery=False)

    def _refresh_credentials(self, creds, request):
        """access token 갱신. 연결 오류는 잠시 뒤 다시 시도하고, 그래도 안 되면 network. 거부는 auth_expired/auth_failed 로 가른다."""
        for attempt in range(self._retries + 1):
            try:
                creds.refresh(request)
                return
            except Exception as exc:  # noqa: BLE001
                text = self._scrub(exc)
                if _is_network_error(exc):  # 만료 문구('certificate has expired' 등)가 섞여도 연결 오류가 먼저다
                    if attempt < self._retries:
                        self._sleep(3 * (2 ** attempt))
                        continue
                    raise PublishError(f"토큰 갱신 중 네트워크 오류: {text[:200]}", code="network") from exc
                if "invalid_grant" in text or "expired" in text.lower() or "revoked" in text.lower():
                    raise PublishError(f"{EXPIRED_HINT} | {text[:160]}", code="auth_expired") from exc
                raise PublishError(f"토큰 갱신 실패: {text[:200]}", code="auth_failed") from exc

    # -- 공개 API -----------------------------------------------------------
    def healthcheck(self):
        """대상 블로그에 접근할 수 있는지 확인한다(쓰기 없음: 토큰 갱신 + blogs.get)."""
        svc = self._service()
        for attempt in range(self._retries + 1):
            try:
                blog = svc.blogs().get(blogId=self.blog_id).execute()
                break
            except Exception as exc:  # noqa: BLE001
                status = _status_of(exc)
                if status == 400:  # blogs.get 의 400 은 보통 블로그 ID 형식 오류다. 다시 해도 같으니 재시도하지 않는다
                    raise PublishError("블로그 접근 확인 실패(status=400): 블로그 ID 형식이 올바르지 않은 것 같습니다 — "
                                       f"{self._secret_names['blog_id']} 시크릿에 블로그 번호(숫자)만 넣었는지 확인하세요 | {self._scrub(exc)[:160]}",
                                       code="auth_failed") from exc
                if _is_quota_error(exc):  # 권한 문제가 아니라 호출 한도다: 시크릿·설정을 고칠 일이 아니라 시간이 지나야 풀린다
                    raise PublishError("블로그 접근 확인 실패(status=403): 호출 한도(쿼터·속도 제한)에 걸린 것 같습니다 — "
                                       f"잠시 뒤 다시 실행하세요 | {self._scrub(exc)[:160]}", code="api_error") from exc
                if status in (401, 403, 404):
                    raise PublishError(f"블로그 접근 확인 실패(status={status}): {self._scrub(exc)[:200]}",
                                       code="auth_failed") from exc
                network = status is None and _is_network_error(exc)
                if (network or status in _TRANSIENT) and attempt < self._retries:
                    self._sleep(3 * (2 ** attempt))
                    continue
                raise PublishError(f"블로그 접근 확인 실패(status={status}): {self._scrub(exc)[:200]}",
                                   code="network" if network else "api_error") from exc
        if not isinstance(blog, dict):
            raise PublishError("블로그 조회 응답이 객체가 아닙니다", code="bad_response")
        return {"name": blog.get("name", ""), "url": blog.get("url", "")}

    def publish(self, title, html, labels=(), draft=False):
        """draft=True 면 Blogger 초안함(isDraft)에 올리고, False 면 즉시 게시한다. 응답에 글 ID·주소가 없으면 실패다."""
        svc = self._service()
        body = {"kind": "blogger#post", "title": title, "content": html}
        if labels:
            body["labels"] = list(labels)
        for attempt in range(self._retries + 1):
            try:
                res = svc.posts().insert(blogId=self.blog_id, body=body, isDraft=draft).execute()
            except Exception as exc:  # noqa: BLE001
                status = _status_of(exc)
                if _is_quota_error(exc):  # 403 이어도 요청은 처리되지 않았다: 재시도·중복 확인 없이 호출 한도 오류로 알린다
                    raise PublishError("Blogger 호출 한도(쿼터·속도 제한)에 걸린 것 같습니다(status=403) — 잠시 뒤 다시 실행하세요 | "
                                       f"{self._scrub(exc)[:160]}", code="api_error") from exc
                if status in (401, 403):
                    raise PublishError(f"권한 오류(status={status}): {self._scrub(exc)[:200]}", code="auth_failed") from exc
                network = status is None and _is_network_error(exc)
                transient = status in _TRANSIENT or network
                duplicate = self._find_recent(title) if (transient or status is None) else None
                if duplicate:
                    return duplicate  # 응답은 실패했지만 글은 이미 올라가 있다
                if transient and attempt < self._retries:
                    self._sleep(3 * (2 ** attempt))
                    continue
                raise PublishError(f"Blogger 게시 실패(status={status}): {self._scrub(exc)[:200]}",
                                   code="network" if network else "api_error") from exc
            return self._checked_result(res, draft)  # 검증 실패는 재시도하지 않는다(글이 이미 만들어졌을 수 있어 중복이 생긴다)
        raise PublishError("Blogger 게시 실패: 재시도 초과", code="api_error")

    @staticmethod
    def _checked_result(res, draft):
        """posts.insert 응답을 검사한다: 글 ID 가 비어 있거나, 요청(초안/게시)과 다른 상태면 실패로 본다.
        즉시 게시는 글 주소(url)도 있어야 한다. 초안은 글 ID 만 있으면 올라간 것이다: 초안 응답에 url 이 오는지는 공식 문서에
        없어서(실제 호출로 확인 필요), 없거나 http(s)가 아니면 빈칸으로 두고 성공으로 본다(운영자는 Blogger 초안함에서 찾는다)."""
        if not isinstance(res, dict):
            raise PublishError("게시 응답이 객체가 아닙니다", code="bad_response")
        post_id = str(res.get("id") or "").strip()
        url = str(res.get("url") or "").strip()
        status = str(res.get("status") or "").upper()  # 관리자 수준 요청에만 채워진다. 없으면 검사하지 않는다
        if not post_id:
            raise PublishError("게시 응답에 글 ID가 없습니다(글이 만들어졌는지 Blogger 화면에서 확인하세요)", code="bad_response")
        if not _URL_RX.match(url):
            if not draft:
                raise PublishError("게시 응답에 글 주소(url)가 없거나 http(s) 주소가 아닙니다(Blogger 화면에서 확인하세요)",
                                   code="bad_response", post_id=post_id)
            url = ""
        if draft and status == "LIVE":
            raise PublishError("초안으로 올렸는데 응답이 공개(LIVE) 상태입니다 — Blogger 화면에서 바로 확인하세요",
                               code="bad_response", post_id=post_id)
        if not draft and status == "DRAFT":
            raise PublishError("게시를 요청했는데 응답이 초안(DRAFT) 상태입니다 — Blogger 화면에서 확인하세요",
                               code="bad_response", post_id=post_id)
        return PublishResult(post_id=post_id, url=url, draft=draft)

    # -- 멱등성 -------------------------------------------------------------
    def _find_recent(self, title, within_minutes=15):
        try:
            # 열거값은 대소문자를 구분한다(LIVE/DRAFT, PUBLISHED/UPDATED). 초안에는 published 가 없을 수 있어 수정 시각(UPDATED) 순으로 본다
            res = self._service().posts().list(
                blogId=self.blog_id, maxResults=5, orderBy="UPDATED", fetchBodies=False,
                status=["LIVE", "DRAFT"]).execute()
        except Exception as exc:  # noqa: BLE001 - 확인 실패는 '없음'으로 보되, 조용히 넘기지 않고 마스킹한 한 줄을 남긴다
            note = (f"중복 게시 확인(posts.list)에 실패해 '없음'으로 보고 진행합니다: "
                    f"{type(exc).__name__}: {' '.join(self._scrub(exc).split())[:120]}")
            if note not in self.notes:
                self.notes.append(note)
            return None
        cutoff = self._now() - timedelta(minutes=within_minutes)
        for item in res.get("items", []) or []:
            if item.get("title") != title:
                continue
            published = item.get("published") or item.get("updated") or ""  # 초안에는 published 가 없을 수 있다(미확인)
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
