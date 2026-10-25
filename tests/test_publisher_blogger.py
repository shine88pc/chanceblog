import ssl
import unittest
from datetime import datetime, timezone

import _bootstrap  # noqa: F401
from pipeline.publishers.base import PublishError, redact
from pipeline.publishers.blogger import BloggerPublisher

NOW = datetime(2026, 10, 21, 2, 0, tzinfo=timezone.utc)


class HttpErr(Exception):
    def __init__(self, status, message="boom"):
        super().__init__(message)
        self.resp = type("Resp", (), {"status": status})()


class Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FakeService:
    """blogs()/posts() 가 자기 자신을 돌려주는 최소 가짜 Blogger 서비스."""

    def __init__(self, insert_results=(), list_items=(), blog=None, get_error=None, get_sequence=()):
        self.insert_results = list(insert_results)
        self.list_items = list(list_items)
        self.blog = blog or {"name": "테스트 블로그", "url": "https://b.example/"}
        self.get_error = get_error
        self.get_sequence = list(get_sequence)   # 호출마다 하나씩 꺼내 예외면 일으키고 아니면 돌려준다(재시도 시나리오)
        self.get_calls = 0
        self.insert_calls = 0
        self.last_body = None
        self.last_draft = None

    def blogs(self):
        return self

    def posts(self):
        return self

    def get(self, blogId):
        def fn():
            self.get_calls += 1
            if self.get_sequence:
                item = self.get_sequence.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item
            if self.get_error:
                raise self.get_error
            return self.blog
        return Req(fn)

    def insert(self, blogId, body, isDraft):
        self.last_body, self.last_draft = body, isDraft

        def fn():
            self.insert_calls += 1
            result = self.insert_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return Req(fn)

    def list(self, **kwargs):
        return Req(lambda: {"items": self.list_items})


def make(service, sleeps=None):
    return BloggerPublisher("123", "cid", "cs", "rt", service_factory=lambda: service,
                            sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
                            retries=2, now=lambda: NOW)


class PublishTest(unittest.TestCase):
    def test_success_sends_labels_and_draft_flag(self):
        svc = FakeService(insert_results=[{"id": 7, "url": "https://b.example/p7"}])
        res = make(svc).publish("제목", "<p>x</p>", ["수면", "생활"], draft=True)
        self.assertEqual((res.post_id, res.url, res.draft), ("7", "https://b.example/p7", True))
        self.assertEqual(svc.last_body["labels"], ["수면", "생활"])
        self.assertTrue(svc.last_draft)

    def test_transient_error_is_retried(self):
        sleeps = []
        svc = FakeService(insert_results=[HttpErr(503), {"id": 1, "url": "https://b.example/p1"}])
        res = make(svc, sleeps).publish("제목", "<p>x</p>")
        self.assertEqual(res.post_id, "1")
        self.assertEqual(svc.insert_calls, 2)
        self.assertEqual(sleeps, [3])

    def test_retry_does_not_double_post_when_first_attempt_actually_succeeded(self):
        existing = {"id": "9", "url": "https://b.example/p9", "title": "제목", "published": "2026-10-21T01:55:00Z"}
        svc = FakeService(insert_results=[HttpErr(504), {"id": 2, "url": "dup"}], list_items=[existing])
        res = make(svc).publish("제목", "<p>x</p>")
        self.assertEqual(res.post_id, "9")
        self.assertEqual(svc.insert_calls, 1)  # 두 번째 insert 를 하지 않았다

    def test_old_post_with_same_title_is_not_treated_as_duplicate(self):
        old = {"id": "9", "url": "u", "title": "제목", "published": "2026-10-21T00:30:00Z"}
        svc = FakeService(insert_results=[HttpErr(503), {"id": 2, "url": "https://b.example/new"}], list_items=[old])
        self.assertEqual(make(svc).publish("제목", "<p>x</p>").post_id, "2")

    def test_auth_error_is_not_retried(self):
        svc = FakeService(insert_results=[HttpErr(403)])
        with self.assertRaises(PublishError) as ctx:
            make(svc).publish("제목", "<p>x</p>")
        self.assertEqual(ctx.exception.code, "auth_failed")
        self.assertEqual(svc.insert_calls, 1)

    def test_client_error_is_not_retried(self):
        svc = FakeService(insert_results=[HttpErr(400)])
        with self.assertRaises(PublishError) as ctx:
            make(svc).publish("제목", "<p>x</p>")
        self.assertEqual(ctx.exception.code, "api_error")
        self.assertEqual(svc.insert_calls, 1)

    def test_gives_up_after_retries(self):
        svc = FakeService(insert_results=[HttpErr(503), HttpErr(503), HttpErr(503)])
        with self.assertRaises(PublishError):
            make(svc).publish("제목", "<p>x</p>")
        self.assertEqual(svc.insert_calls, 3)

    def test_secrets_are_masked_in_errors(self):
        secret = "ya29." + "a" * 40
        svc = FakeService(insert_results=[HttpErr(400, f"bad token {secret}")])
        with self.assertRaises(PublishError) as ctx:
            make(svc).publish("제목", "<p>x</p>")
        self.assertNotIn(secret, str(ctx.exception))


class HealthcheckTest(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(make(FakeService()).healthcheck()["name"], "테스트 블로그")

    def test_not_found_is_auth_failed(self):
        with self.assertRaises(PublishError) as ctx:
            make(FakeService(get_error=HttpErr(404))).healthcheck()
        self.assertEqual(ctx.exception.code, "auth_failed")

    def test_server_error_is_api_error(self):
        with self.assertRaises(PublishError) as ctx:
            make(FakeService(get_error=HttpErr(500))).healthcheck()
        self.assertEqual(ctx.exception.code, "api_error")


# ---------------------------------------------------------------------------
# 초안함 업로드(isDraft)·구글 인증 경로·응답 검증. 구글 라이브러리와 네트워크는 쓰지 않는다:
# 자격 증명·요청·서비스 생성 단계를 가짜로 갈아 끼워 _service() 의 실제 경로를 탄다.
# ---------------------------------------------------------------------------
# 실제 비밀처럼 보이는 리터럴을 소스에 쓰지 않으려고 런타임에 조합한다(값은 가짜다)
BLOG_ID = "7654321098" + "765432101"
CLIENT_ID = "123456789012-" + "fakeclientid"
CLIENT_SECRET = "fake-client-" + "secret-value-0001"
REFRESH_TOKEN = "fake-refresh-" + "token-value-0002"
SECRET_VALUES = (BLOG_ID, CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
POST_URL = "https://b.example/2026/10/p7.html"


class RefreshError(Exception):
    """google.auth.exceptions.RefreshError 와 같은 이름의 가짜(어댑터는 클래스 이름·문구로 분류한다)."""


class TransportError(Exception):
    """google.auth.exceptions.TransportError 와 같은 이름의 가짜."""


def real_path(creds_errors=(), service=None, sleeps=None, retries=2):
    """service_factory 없이 구글 인증·서비스 생성 단계만 가짜로 갈아 끼운 어댑터. seen 에 호출 기록이 쌓인다."""
    seen = {"requests": [], "builds": []}

    class Creds:
        def __init__(self, client_id, client_secret, refresh_token):
            seen["creds_args"] = (client_id, client_secret, refresh_token)
            self.pending = list(creds_errors)

        def refresh(self, request):
            seen["requests"].append(request)
            if self.pending:
                error = self.pending.pop(0)
                if error is not None:
                    raise error

    def new_request():
        seen["request_obj"] = object()
        return seen["request_obj"]

    def build(api, version, credentials=None, cache_discovery=None):
        seen["builds"].append((api, version, credentials, cache_discovery))
        return service or FakeService()

    pub = BloggerPublisher(BLOG_ID, CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, credentials_factory=Creds,
                           request_factory=new_request, service_builder=build,
                           sleep=(sleeps.append if sleeps is not None else (lambda s: None)), retries=retries, now=lambda: NOW)
    return pub, seen


def assert_no_secrets(test, text):
    for value in SECRET_VALUES:
        test.assertNotIn(value, text)


class GoogleAuthPathTest(unittest.TestCase):
    def test_success_refreshes_once_and_builds_the_blogger_service_once(self):
        pub, seen = real_path()
        self.assertEqual(pub.healthcheck(), {"name": "테스트 블로그", "url": "https://b.example/"})
        self.assertEqual(seen["creds_args"], (CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN))
        self.assertEqual(seen["requests"], [seen["request_obj"]])           # 토큰 갱신 1회, 같은 요청 객체로
        self.assertEqual([(api, version, cache) for api, version, _creds, cache in seen["builds"]], [("blogger", "v3", False)])
        pub.healthcheck()
        pub.healthcheck()
        self.assertEqual((len(seen["requests"]), len(seen["builds"])), (1, 1))   # 서비스를 기억해 다시 갱신하지 않는다

    def test_revoked_or_expired_token_is_auth_expired_and_not_retried(self):
        for message in ("invalid_grant: Token has been expired or revoked.", "Token has been expired or revoked.",
                        "the grant was revoked by the user"):
            with self.subTest(message):
                sleeps = []
                pub, seen = real_path([RefreshError((message, {"error": "invalid_grant"}))], sleeps=sleeps)
                with self.assertRaises(PublishError) as ctx:
                    pub.healthcheck()
                self.assertEqual(ctx.exception.code, "auth_expired")
                self.assertIn("프로덕션", str(ctx.exception))                  # 7일 만료 안내(EXPIRED_HINT)
                self.assertEqual((len(seen["requests"]), sleeps, seen["builds"]), (1, [], []))

    def test_other_refresh_rejections_are_auth_failed(self):
        for message in ("invalid_client: Unauthorized", "unauthorized_client: Client is unauthorized to retrieve access tokens"):
            with self.subTest(message):
                pub, seen = real_path([RefreshError(message)])
                with self.assertRaises(PublishError) as ctx:
                    pub.healthcheck()
                self.assertEqual(ctx.exception.code, "auth_failed")
                self.assertEqual(len(seen["requests"]), 1)                     # 설정 오류는 재시도하지 않는다

    def test_connection_errors_are_retried_then_reported_as_network(self):
        retryable = RefreshError("token endpoint returned 503")
        retryable.retryable = True            # google-auth 가 토큰 서버의 일시 오류에 붙이는 표시
        kinds = {"TransportError": lambda: TransportError("Failed to establish a new connection"),
                 "ConnectionError": lambda: ConnectionError("reset"), "TimeoutError": lambda: TimeoutError("timed out"),
                 "OSError": lambda: OSError("network unreachable"), "retryable 표시": lambda: retryable,
                 "인증서 만료 문구가 섞인 SSL 오류": lambda: ssl.SSLError("certificate verify failed: certificate has expired")}
        for label, make_error in kinds.items():
            with self.subTest(label):
                sleeps = []
                pub, seen = real_path([make_error(), make_error(), make_error()], sleeps=sleeps)
                with self.assertRaises(PublishError) as ctx:
                    pub.healthcheck()
                self.assertEqual(ctx.exception.code, "network")                # 'expired' 문구가 있어도 인증 만료로 읽지 않는다
                self.assertEqual((len(seen["requests"]), sleeps), (3, [3, 6]))

    def test_a_transient_network_error_recovers_on_retry(self):
        sleeps = []
        pub, seen = real_path([TransportError("temporary"), None], sleeps=sleeps)
        self.assertEqual(pub.healthcheck()["url"], "https://b.example/")
        self.assertEqual((len(seen["requests"]), sleeps), (2, [3]))

    def test_retries_zero_means_a_single_attempt(self):
        sleeps = []
        pub, seen = real_path([TransportError("x")], sleeps=sleeps, retries=0)
        with self.assertRaises(PublishError) as ctx:
            pub.healthcheck()
        self.assertEqual((ctx.exception.code, len(seen["requests"]), sleeps), ("network", 1, []))

    def test_a_failed_refresh_is_not_remembered(self):
        pub, seen = real_path([RefreshError("invalid_grant")])
        with self.assertRaises(PublishError):
            pub.healthcheck()
        # 같은 어댑터로 다시 부르면 새 자격 증명으로 처음부터 시도한다(실패한 서비스를 캐시하지 않는다)
        with self.assertRaises(PublishError):
            pub.healthcheck()
        self.assertEqual(seen["builds"], [])

    def test_error_messages_never_contain_the_secret_values(self):
        leaky = " ".join(f"{name}={value}" for name, value in zip(("blog", "client", "secret", "refresh"), SECRET_VALUES))
        cases = {"만료": RefreshError(f"invalid_grant {leaky}"), "거부": RefreshError(f"invalid_client {leaky}"),
                 "네트워크": TransportError(f"connect failed {leaky}")}
        for label, error in cases.items():
            with self.subTest(label):
                pub, _seen = real_path([error, error, error])
                with self.assertRaises(PublishError) as ctx:
                    pub.healthcheck()
                assert_no_secrets(self, str(ctx.exception))
        # blogs.get·posts.insert 오류 문구에는 요청 주소(블로그 ID 포함)가 섞여 나온다
        url_error = HttpErr(500, f"<HttpError 500 when requesting https://blogger.googleapis.com/v3/blogs/{BLOG_ID}?alt=json "
                                 f"returned \"boom\">")
        for label, call in (("healthcheck", lambda p: p.healthcheck()), ("publish", lambda p: p.publish("제목", "<p>x</p>"))):
            with self.subTest(label):
                pub, _seen = real_path(service=FakeService(get_error=url_error, insert_results=[url_error] * 3))
                with self.assertRaises(PublishError) as ctx:
                    call(pub)
                assert_no_secrets(self, str(ctx.exception))
                self.assertIn("***", str(ctx.exception))


class HealthcheckReliabilityTest(unittest.TestCase):
    def test_access_errors_are_auth_failed_and_not_retried(self):
        for status in (401, 403, 404):
            with self.subTest(status):
                svc = FakeService(get_error=HttpErr(status))
                with self.assertRaises(PublishError) as ctx:
                    make(svc).healthcheck()
                self.assertEqual((ctx.exception.code, svc.get_calls), ("auth_failed", 1))

    def test_transient_http_errors_are_retried_with_backoff(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status):
                sleeps = []
                svc = FakeService(get_sequence=[HttpErr(status), {"name": "n", "url": "https://b.example/"}])
                self.assertEqual(make(svc, sleeps).healthcheck()["name"], "n")
                self.assertEqual((svc.get_calls, sleeps), (2, [3]))

    def test_gives_up_after_retries_as_api_error(self):
        sleeps = []
        svc = FakeService(get_sequence=[HttpErr(503)] * 3)
        with self.assertRaises(PublishError) as ctx:
            make(svc, sleeps).healthcheck()
        self.assertEqual((ctx.exception.code, svc.get_calls, sleeps), ("api_error", 3, [3, 6]))

    def test_other_client_errors_are_api_error_without_retry(self):
        svc = FakeService(get_error=HttpErr(400))
        with self.assertRaises(PublishError) as ctx:
            make(svc).healthcheck()
        self.assertEqual((ctx.exception.code, svc.get_calls), ("api_error", 1))

    def test_connection_errors_without_a_status_are_network(self):
        sleeps = []
        svc = FakeService(get_sequence=[TransportError("dns"), {"name": "n", "url": "https://b.example/"}])
        self.assertEqual(make(svc, sleeps).healthcheck()["name"], "n")
        self.assertEqual((svc.get_calls, sleeps), (2, [3]))
        svc = FakeService(get_sequence=[ConnectionError("a"), TimeoutError("b"), OSError("c")])
        with self.assertRaises(PublishError) as ctx:
            make(svc).healthcheck()
        self.assertEqual((ctx.exception.code, svc.get_calls), ("network", 3))

    def test_a_non_http_unknown_error_is_api_error_without_retry(self):
        svc = FakeService(get_error=ValueError("weird"))
        with self.assertRaises(PublishError) as ctx:
            make(svc).healthcheck()
        self.assertEqual((ctx.exception.code, svc.get_calls), ("api_error", 1))

    def test_a_non_object_response_is_bad_response(self):
        with self.assertRaises(PublishError) as ctx:
            make(FakeService(get_sequence=["<html>not json</html>"])).healthcheck()
        self.assertEqual(ctx.exception.code, "bad_response")


class DraftUploadTest(unittest.TestCase):
    def test_draft_flag_reaches_posts_insert_and_the_result_says_draft(self):
        for draft in (True, False):
            with self.subTest(draft=draft):
                svc = FakeService(insert_results=[{"id": 7, "url": POST_URL, "status": "DRAFT" if draft else "LIVE"}])
                res = make(svc).publish("제목", "<p>x</p>", ["수면"], draft=draft)
                self.assertEqual((svc.last_draft, res.draft, res.post_id, res.url), (draft, draft, "7", POST_URL))
        svc = FakeService(insert_results=[{"id": 8, "url": POST_URL}])
        self.assertFalse(make(svc).publish("제목", "<p>x</p>").draft)        # 기본은 즉시 게시
        self.assertFalse(svc.last_draft)

    def test_incomplete_responses_are_failures_and_are_not_retried(self):
        bad = {"빈 객체": {}, "id 없음": {"url": POST_URL}, "id 비어 있음": {"id": "", "url": POST_URL},
               "url 없음": {"id": "7"}, "url 비어 있음": {"id": "7", "url": ""}, "url 이 공백": {"id": "7", "url": "  "},
               "http 가 아닌 주소": {"id": "7", "url": "javascript:alert(1)"}, "상대 주소": {"id": "7", "url": "/p7"},
               "객체가 아님": "oops", "None": None}
        for label, response in bad.items():
            with self.subTest(label):
                svc = FakeService(insert_results=[response, {"id": 9, "url": POST_URL}])
                with self.assertRaises(PublishError) as ctx:
                    make(svc).publish("제목", "<p>x</p>", draft=True)
                self.assertEqual(ctx.exception.code, "bad_response")
                self.assertEqual(svc.insert_calls, 1)       # 글이 이미 만들어졌을 수 있어 다시 올리지 않는다(중복 방지)

    def test_a_failure_after_the_post_exists_carries_its_id(self):
        svc = FakeService(insert_results=[{"id": 77, "url": ""}])
        with self.assertRaises(PublishError) as ctx:
            make(svc).publish("제목", "<p>x</p>", draft=True)
        self.assertEqual(ctx.exception.post_id, "77")           # Blogger 화면에서 찾아 지울 수 있게

    def test_a_draft_that_came_back_live_or_a_post_that_came_back_draft_is_a_failure(self):
        svc = FakeService(insert_results=[{"id": 7, "url": POST_URL, "status": "LIVE"}])
        with self.assertRaises(PublishError) as ctx:
            make(svc).publish("제목", "<p>x</p>", draft=True)
        self.assertEqual((ctx.exception.code, ctx.exception.post_id), ("bad_response", "7"))
        self.assertIn("LIVE", str(ctx.exception))
        svc = FakeService(insert_results=[{"id": 7, "url": POST_URL, "status": "draft"}])      # 소문자도 같은 상태다
        with self.assertRaises(PublishError) as ctx:
            make(svc).publish("제목", "<p>x</p>", draft=False)
        self.assertEqual(ctx.exception.code, "bad_response")
        # status 가 없거나 다른 값(예약 등)이면 검사하지 않는다: 관리자 요청에만 채워지는 필드다
        for status in (None, "", "SCHEDULED"):
            with self.subTest(status):
                body = {"id": 7, "url": POST_URL, **({} if status is None else {"status": status})}
                self.assertEqual(make(FakeService(insert_results=[body])).publish("제목", "<p>x</p>", draft=True).post_id, "7")

    def test_a_draft_listed_without_a_published_time_is_found_as_a_duplicate_via_updated(self):
        existing = {"id": "9", "url": POST_URL, "title": "제목", "status": "DRAFT", "updated": "2026-10-21T01:55:00Z"}
        svc = FakeService(insert_results=[HttpErr(504), {"id": 2, "url": POST_URL}], list_items=[existing])
        res = make(svc).publish("제목", "<p>x</p>", draft=True)
        self.assertEqual((res.post_id, res.draft, svc.insert_calls), ("9", True, 1))
        stale = {**existing, "updated": "2026-10-21T00:30:00Z"}
        svc = FakeService(insert_results=[HttpErr(504), {"id": 2, "url": POST_URL}], list_items=[stale])
        self.assertEqual(make(svc).publish("제목", "<p>x</p>", draft=True).post_id, "2")

    def test_connection_errors_on_insert_are_retried_and_end_as_network(self):
        sleeps = []
        svc = FakeService(insert_results=[TransportError("a"), TransportError("b"), TransportError("c")])
        with self.assertRaises(PublishError) as ctx:
            make(svc, sleeps).publish("제목", "<p>x</p>", draft=True)
        self.assertEqual((ctx.exception.code, svc.insert_calls, sleeps), ("network", 3, [3, 6]))
        svc = FakeService(insert_results=[ConnectionError("a"), {"id": 3, "url": POST_URL}])
        self.assertEqual(make(svc).publish("제목", "<p>x</p>", draft=True).post_id, "3")

    def test_permission_errors_on_insert_are_auth_failed_for_drafts_too(self):
        for status in (401, 403):
            svc = FakeService(insert_results=[HttpErr(status)])
            with self.assertRaises(PublishError) as ctx:
                make(svc).publish("제목", "<p>x</p>", draft=True)
            self.assertEqual((ctx.exception.code, svc.insert_calls), ("auth_failed", 1))


class RedactTest(unittest.TestCase):
    def test_exact_values_and_patterns_are_masked(self):
        text = f"token {REFRESH_TOKEN} blog {BLOG_ID} key AIza{'x' * 30}"
        out = redact(text, SECRET_VALUES)
        assert_no_secrets(self, out)
        self.assertNotIn("AIza", out)
        self.assertEqual(out.count("***"), 3)

    def test_short_or_empty_values_are_not_replaced(self):
        self.assertEqual(redact("a cid cs rt 123 abc", ("cid", "cs", "rt", "123", "", None)), "a cid cs rt 123 abc")
        self.assertEqual(redact("plain text"), "plain text")
        self.assertEqual(redact(ValueError(f"bad {BLOG_ID}"), (BLOG_ID,)), "bad ***")


if __name__ == "__main__":
    unittest.main()
