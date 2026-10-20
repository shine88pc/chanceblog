import unittest
from datetime import datetime, timezone

import _bootstrap  # noqa: F401
from pipeline.publishers.base import PublishError
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

    def __init__(self, insert_results=(), list_items=(), blog=None, get_error=None):
        self.insert_results = list(insert_results)
        self.list_items = list(list_items)
        self.blog = blog or {"name": "테스트 블로그", "url": "https://b.example/"}
        self.get_error = get_error
        self.insert_calls = 0
        self.last_body = None
        self.last_draft = None

    def blogs(self):
        return self

    def posts(self):
        return self

    def get(self, blogId):
        def fn():
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
        svc = FakeService(insert_results=[HttpErr(503), {"id": 1, "url": "u"}])
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
        svc = FakeService(insert_results=[HttpErr(503), {"id": 2, "url": "new"}], list_items=[old])
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


if __name__ == "__main__":
    unittest.main()
