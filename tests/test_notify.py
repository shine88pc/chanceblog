"""텔레그램 알림 모듈(pipeline/notify.py) 시험 — 전송·재시도·분류·소독·주소 허용 목록·길이·이벤트별 문구·토큰이 새지 않는 것.

네트워크는 쓰지 않는다(요청은 전부 가짜 FakeNet 이 받는다). 가짜 토큰·채팅 ID 는 런타임에 조합한다(notify_helpers.py).
이 모듈의 최우선 품질 기준은 **토큰·채팅 ID 가 로그·예외·출력·결과 어디에도 나오지 않는 것**이다: LeakTest 가 requests 식 예외 문자열(요청 주소가 든 것)을
포함한 여러 실패 모양에서 결과·설명·예외 사슬을 검사한다.
"""
import http.client
import http.server
import json
import socket
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from unittest import mock

import _bootstrap  # noqa: F401
import notify_helpers as nh
from notify_helpers import CHAT, ENV, TOKEN, FakeNet, FakeResponse, http_error, leaks, make_notifier, ok_reply
from pipeline import notify

BLOG_URL = "https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-093056/"
EN_URL = "https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-093056/"
FW_COLON = chr(0xFF1A)          # defang_urls 가 주소의 ':' 를 바꾸는 전각 콜론(소스에는 코드 포인트로 적는다)


def posts(kr_url=BLOG_URL, en_url=EN_URL, kr_title="한글 제목", en_title="English Title"):
    return [{"lang": "ko", "title": kr_title, "category": "경제·일", "source_name": "유럽연합 CINEA", "url": kr_url},
            {"lang": "en", "title": en_title, "category": "Economy & Work", "source_name": "European Commission", "url": en_url}]


class ConfigTest(unittest.TestCase):
    def test_missing_or_blank_values_disable_it_without_any_request(self):
        for env in ({}, {"TELEGRAM_BOT_TOKEN": TOKEN}, {"TELEGRAM_CHAT_ID": CHAT}, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": CHAT},
                    {"TELEGRAM_BOT_TOKEN": " \n ", "TELEGRAM_CHAT_ID": CHAT}, {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "\t"},
                    {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}):
            with self.subTest(env=sorted(env)):
                notifier, net, _ = make_notifier(environ=env)
                self.assertFalse(notifier.enabled)
                self.assertEqual(notifier.send_message("안녕"), notify.Result(True, False, None, "disabled", ""))
                self.assertEqual(net.calls, 0)

    def test_every_event_is_a_silent_no_op_when_disabled(self):
        notifier, net, _ = make_notifier(environ={})
        results = [notifier.notify_chance_published(posts()), notifier.notify_draft_waiting("티스토리", "제목", "어디서"),
                   notifier.notify_blogger_result("draft_uploaded", "제목"), notifier.notify_ops_alert(["a"], "https://github.com/shine88pc/chanceblog/issues/22"),
                   notifier.notify_test()]
        for result in results:
            self.assertEqual((result.ok, result.sent, result.reason), (True, False, "disabled"), result)
        self.assertEqual(net.calls, 0)

    def test_the_default_environment_is_the_process_environment(self):
        with mock.patch.dict("os.environ", ENV, clear=False):
            self.assertTrue(notify.Notifier().enabled)
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(notify.Notifier().enabled)

    def test_surrounding_whitespace_in_the_secrets_is_ignored(self):
        notifier, net, _ = make_notifier(environ={"TELEGRAM_BOT_TOKEN": f" {TOKEN}\n", "TELEGRAM_CHAT_ID": f"\t{CHAT} "})
        self.assertTrue(notifier.send_message("안녕").sent)
        self.assertEqual(net.requests[0].full_url, nh.SEND_URL)
        self.assertEqual(net.bodies()[0]["chat_id"], int(CHAT))

    def test_repr_and_str_never_show_the_values(self):
        notifier, _, _ = make_notifier()
        self.assertEqual(leaks(repr(notifier), str(notifier), f"{notifier}", f"{notifier!r}"), [])
        self.assertEqual(repr(notifier), "<Notifier enabled=True>")

    def test_a_malformed_token_is_reported_without_any_request(self):
        shapes = (f'"{TOKEN}"', "bot" + TOKEN, TOKEN.replace(":", ""), TOKEN.split(":")[1], "abc:" + TOKEN.split(":")[1], TOKEN + " x", TOKEN.replace(":", "/"),
                  TOKEN.split(":")[0] + ":short")
        for shape in shapes:
            with self.subTest(shape=len(shape)):
                notifier, net, _ = make_notifier(environ={"TELEGRAM_BOT_TOKEN": shape, "TELEGRAM_CHAT_ID": CHAT})
                result = notifier.send_message("안녕")
                self.assertEqual((result.ok, result.sent, result.reason, result.status), (False, False, "invalid_token", None))
                self.assertEqual(net.calls, 0)
                self.assertEqual(leaks(repr(result), notify.describe(result)), [])
                self.assertNotIn(shape.split(":")[-1], repr(result))

    def test_a_malformed_chat_id_is_reported_without_any_request(self):
        for shape in ("abc", f'"{CHAT}"', "12.5", "-", "@ab", "@" + "x" * 40, "1 2", "1" * 30):
            with self.subTest(shape=shape):
                notifier, net, _ = make_notifier(environ={"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": shape})
                result = notifier.send_message("안녕")
                self.assertEqual((result.ok, result.sent, result.reason), (False, False, "invalid_chat_id"))
                self.assertEqual(net.calls, 0)

    def test_chat_id_types(self):
        for chat, expected in ((CHAT, int(CHAT)), ("-100" + CHAT, -int("100" + CHAT)), ("@chance_channel", "@chance_channel")):
            with self.subTest(chat=type(expected).__name__):
                notifier, net, _ = make_notifier(environ={"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": chat})
                self.assertTrue(notifier.send_message("안녕").sent)
                self.assertEqual(net.bodies()[0]["chat_id"], expected)

    def test_empty_text_is_not_sent(self):
        notifier, net, _ = make_notifier()
        for text in ("", "   \n", None):
            result = notifier.send_message(text)
            self.assertEqual((result.ok, result.reason), (False, "empty_text"))
        self.assertEqual(net.calls, 0)

    def test_only_plain_or_html_parse_modes_exist(self):
        notifier, net, _ = make_notifier()
        result = notifier.send_message("x", parse_mode="MarkdownV2")
        self.assertEqual((result.ok, result.sent, result.reason), (False, False, "internal_error"))
        self.assertEqual(net.calls, 0)


class RequestShapeTest(unittest.TestCase):
    def test_posts_json_to_the_bot_url_with_a_15_second_timeout(self):
        notifier, net, _ = make_notifier()
        result = notifier.send_message("안녕")
        self.assertEqual(result, notify.Result(True, True, 200, "sent", ""))
        request = net.requests[0]
        self.assertEqual(request.full_url, nh.SEND_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(net.timeouts, [15])
        self.assertEqual(request.get_header("Content-type"), "application/json; charset=utf-8")
        self.assertEqual(net.bodies()[0], {"chat_id": int(CHAT), "text": "안녕", "link_preview_options": {"is_disabled": True}})

    def test_the_token_is_only_in_the_url_never_in_the_body_or_headers(self):
        notifier, net, _ = make_notifier()
        notifier.send_message("안녕", parse_mode="HTML", buttons=[("열기", BLOG_URL)])
        request = net.requests[0]
        self.assertEqual(leaks(str(request.data, "utf-8"), dict(request.header_items()), request.get_method(), chat=False), [])
        self.assertEqual(sorted(key.lower() for key, _ in request.header_items()), ["content-type", "user-agent"])
        self.assertEqual(request.full_url.count(TOKEN), 1)

    def test_optional_fields_appear_only_when_asked(self):
        notifier, net, _ = make_notifier()
        notifier.send_message("a")
        notifier.send_message("b", silent=True)
        notifier.send_message("<b>c</b>", parse_mode="HTML")
        plain, silent, formatted = net.bodies()
        for key in ("disable_notification", "parse_mode", "reply_markup"):
            self.assertNotIn(key, plain)
        self.assertIs(silent["disable_notification"], True)
        self.assertEqual(formatted["parse_mode"], "HTML")
        self.assertNotIn("disable_notification", formatted)

    def test_link_previews_are_always_disabled(self):
        notifier, net, _ = make_notifier()
        notifier.send_message("https://github.com/shine88pc/chanceblog")
        self.assertEqual(net.bodies()[0]["link_preview_options"], {"is_disabled": True})

    def test_buttons_become_one_row_of_url_buttons_and_only_allowed_addresses_survive(self):
        notifier, net, _ = make_notifier()
        notifier.send_message("본문", buttons=[("한글 글", BLOG_URL), ("나쁜 주소", "https://evil.example/x"), ("English", EN_URL)])
        markup = net.bodies()[0]["reply_markup"]
        self.assertEqual(markup, {"inline_keyboard": [[{"text": "한글 글", "url": BLOG_URL}, {"text": "English", "url": EN_URL}]]})

    def test_no_keyboard_is_sent_when_no_button_survives(self):
        notifier, net, _ = make_notifier()
        notifier.send_message("본문", buttons=[("a", "http://shine88pc.github.io/x"), ("", BLOG_URL), ("b", None)])
        self.assertNotIn("reply_markup", net.bodies()[0])

    def test_at_most_four_buttons(self):
        notifier, net, _ = make_notifier()
        notifier.send_message("본문", buttons=[(f"b{i}", BLOG_URL + f"?n={i}") for i in range(7)])
        self.assertEqual(len(net.bodies()[0]["reply_markup"]["inline_keyboard"][0]), 4)

    def test_button_labels_are_cleaned_and_shortened(self):
        notifier, net, _ = make_notifier()
        notifier.send_message("본문", buttons=[("한\n글\x00 글" + "가" * 80, BLOG_URL)])
        label = net.bodies()[0]["reply_markup"]["inline_keyboard"][0][0]["text"]
        self.assertLessEqual(len(label), 30)
        self.assertNotIn("\n", label)
        self.assertNotIn("\x00", label)

    def test_malformed_button_entries_are_ignored(self):
        notifier, net, _ = make_notifier()
        notifier.send_message("본문", buttons=["문자열", ("하나",), ("a", BLOG_URL, "셋"), None, ("ok", BLOG_URL)])
        self.assertEqual(net.bodies()[0]["reply_markup"]["inline_keyboard"], [[{"text": "ok", "url": BLOG_URL}]])

    def test_korean_text_is_sent_as_utf8_not_escaped(self):
        notifier, net, _ = make_notifier()
        notifier.send_message("한글 €")
        self.assertIn("한글 €".encode("utf-8"), net.requests[0].data)

    def test_lone_surrogates_do_not_break_the_request(self):
        notifier, net, _ = make_notifier()
        result = notifier.send_message("앞\ud800뒤")
        self.assertTrue(result.sent)
        self.assertEqual(net.bodies()[0]["text"], "앞뒤")

    def test_the_response_body_is_never_exposed_in_the_result(self):
        notifier, _, _ = make_notifier(net=FakeNet(FakeResponse(200, {"ok": True, "result": {"text": "비밀이 아닌 내용 XYZ", "chat": {"first_name": "이름", "id": int(CHAT)}}})))
        result = notifier.send_message("안녕")
        self.assertEqual(result, notify.Result(True, True, 200, "sent", ""))
        self.assertEqual(leaks(repr(result)), [])


class ClassificationTest(unittest.TestCase):
    def run_one(self, outcome, **kw):
        notifier, net, clock = make_notifier(net=FakeNet(outcome))
        return notifier.send_message("안녕", **kw), net, clock

    def test_error_statuses_map_to_reasons(self):
        table = (
            (401, "Unauthorized", "unauthorized"),
            (400, "Bad Request: chat not found", "chat_not_found"),
            (403, "Forbidden: bot can't initiate conversation with a user", "forbidden"),
            (403, "Forbidden: bot was blocked by the user", "forbidden"),
            (404, "Not Found", "not_found"),
            (400, "Bad Request: message is too long", "bad_request"),
            (409, "Conflict", "bad_request"),
            (400, "Bad Request: something else", "bad_request"),
        )
        for status, description, reason in table:
            with self.subTest(status=status, description=description):
                result, net, _ = self.run_one(http_error(status, description))
                self.assertEqual((result.ok, result.sent, result.status, result.reason), (False, False, status, reason))
                self.assertEqual(result.detail, description)
                self.assertEqual(net.calls, 1, "4xx 는 다시 시도하지 않는다")

    def test_a_successful_status_without_ok_true_is_a_bad_response(self):
        for body in ({"ok": False}, {"result": {}}, [], "text", b"", b"<html>", {"ok": "true"}, {"ok": 1}):
            with self.subTest(body=repr(body)[:20]):
                result, _, _ = self.run_one(FakeResponse(200, body))
                self.assertEqual((result.ok, result.reason, result.status), (False, "bad_response", 200))

    def test_a_non_200_success_status_is_a_bad_response(self):
        result, _, _ = self.run_one(FakeResponse(202, {"ok": True}))
        self.assertEqual((result.sent, result.reason), (False, "bad_response"))

    def test_error_body_that_is_not_json_still_classifies_by_status(self):
        result, _, _ = self.run_one(http_error(401, raw=b"<html>nope</html>"))
        self.assertEqual((result.reason, result.status, result.detail), ("unauthorized", 401, ""))
        result, _, _ = self.run_one(http_error(403, raw=b"[1, 2]"))
        self.assertEqual((result.reason, result.detail), ("forbidden", ""))

    def test_description_must_be_text(self):
        result, _, _ = self.run_one(http_error(400, raw=b'{"description": {"a": 1}}'))
        self.assertEqual((result.reason, result.detail), ("bad_request", ""))

    def test_detail_is_one_short_clean_line(self):
        result, _, _ = self.run_one(http_error(400, "Bad Request:\n::error::fake\x00 " + "x" * 400))
        self.assertNotIn("\n", result.detail)
        self.assertNotIn("::", result.detail)
        self.assertLessEqual(len(result.detail), 120)

    def test_server_errors_are_server_error_after_one_retry(self):
        result, net, clock = self.run_one(http_error(502, "Bad Gateway"))
        self.assertEqual((result.reason, result.status, net.calls, clock.sleeps), ("server_error", 502, 2, [2]))

    def test_connection_level_failures_are_network_after_one_retry(self):
        for exc in (urllib.error.URLError("x"), ConnectionResetError("x"), OSError("x"), http.client.RemoteDisconnected("x"), http.client.IncompleteRead(b"x"),
                    ValueError("x"), RuntimeError("x")):
            with self.subTest(exc=type(exc).__name__):
                result, net, clock = self.run_one(exc)
                self.assertEqual((result.ok, result.sent, result.status, result.reason, net.calls, clock.sleeps), (False, False, None, "network", 2, [2]))

    def test_timeouts_are_timeout_after_one_retry(self):
        for exc in (socket.timeout("x"), TimeoutError("x"), urllib.error.URLError(socket.timeout("x")), urllib.error.URLError(TimeoutError("x"))):
            with self.subTest(exc=repr(exc)[:30]):
                result, net, clock = self.run_one(exc)
                self.assertEqual((result.reason, net.calls, clock.sleeps), ("timeout", 2, [2]))

    def test_keyboard_interrupt_is_not_swallowed(self):
        notifier, _, _ = make_notifier(net=FakeNet(KeyboardInterrupt()))
        with self.assertRaises(KeyboardInterrupt):
            notifier.send_message("안녕")

    def test_error_responses_are_closed(self):
        error = http_error(401, "Unauthorized")
        closed = []
        error.close = lambda: closed.append(True)
        self.run_one(error)
        self.assertEqual(closed, [True])

    def test_success_responses_are_closed(self):
        reply = ok_reply()
        self.run_one(reply)
        self.assertTrue(reply.closed)

    def test_a_response_without_a_status_uses_getcode(self):
        class Legacy:
            headers = {}

            def getcode(self):
                return 200

            def read(self, n=-1):
                return b'{"ok": true}'

            def close(self):
                pass
        result, _, _ = self.run_one(Legacy())
        self.assertTrue(result.sent)

    def test_a_response_that_fails_while_reading_is_a_network_failure(self):
        class Broken:
            status = 200

            def read(self, n=-1):
                raise OSError("boom")

            def close(self):
                pass
        result, _, _ = self.run_one(Broken())
        self.assertEqual((result.sent, result.reason), (False, "bad_response"))


class RetryTest(unittest.TestCase):
    def test_429_waits_retry_after_once_then_succeeds(self):
        notifier, net, clock = make_notifier(net=FakeNet(http_error(429, "Too Many Requests: retry after 3", retry_after=3), ok_reply()))
        result = notifier.send_message("안녕")
        self.assertEqual((result.sent, net.calls, clock.sleeps), (True, 2, [3]))

    def test_the_wait_is_capped_at_ten_seconds(self):
        notifier, net, clock = make_notifier(net=FakeNet(http_error(429, retry_after=300), ok_reply()))
        self.assertTrue(notifier.send_message("안녕").sent)
        self.assertEqual(clock.sleeps, [10])

    def test_a_second_429_gives_up(self):
        notifier, net, clock = make_notifier(net=FakeNet(http_error(429, "Too Many Requests", retry_after=2)))
        result = notifier.send_message("안녕")
        self.assertEqual((result.sent, result.reason, result.status, net.calls, clock.sleeps), (False, "rate_limited", 429, 2, [2]))

    def test_a_missing_or_odd_retry_after_waits_one_second_or_the_header(self):
        for outcome, expected in ((http_error(429), 1), (http_error(429, header_retry=4), 4), (http_error(429, retry_after="abc"), 1),
                                  (http_error(429, retry_after=0), 1), (http_error(429, retry_after=-5), 1), (http_error(429, retry_after=2.9), 2),
                                  (http_error(429, retry_after=None, header_retry="x"), 1), (http_error(429, retry_after=True), 1)):
            with self.subTest(expected=expected):
                notifier, _, clock = make_notifier(net=FakeNet(outcome, ok_reply()))
                self.assertTrue(notifier.send_message("안녕").sent)
                self.assertEqual(clock.sleeps, [expected])

    def test_network_error_is_retried_once_after_two_seconds(self):
        notifier, net, clock = make_notifier(net=FakeNet(urllib.error.URLError("x"), ok_reply()))
        self.assertTrue(notifier.send_message("안녕").sent)
        self.assertEqual((net.calls, clock.sleeps), (2, [2]))

    def test_a_timeout_then_success(self):
        notifier, net, clock = make_notifier(net=FakeNet(socket.timeout(), ok_reply()))
        self.assertTrue(notifier.send_message("안녕").sent)
        self.assertEqual(net.calls, 2)

    def test_server_error_then_success(self):
        notifier, net, _ = make_notifier(net=FakeNet(http_error(503, "Service Unavailable"), ok_reply()))
        self.assertTrue(notifier.send_message("안녕").sent)
        self.assertEqual(net.calls, 2)

    def test_the_network_retry_is_used_only_once_per_message(self):
        notifier, net, clock = make_notifier(net=FakeNet(urllib.error.URLError("x"), http_error(502, "Bad Gateway"), ok_reply()))
        result = notifier.send_message("안녕")
        self.assertEqual((result.sent, result.reason, net.calls), (False, "server_error", 2))

    def test_429_then_network_error_then_success_uses_both_retries(self):
        notifier, net, clock = make_notifier(net=FakeNet(http_error(429, retry_after=1), urllib.error.URLError("x"), ok_reply()))
        self.assertTrue(notifier.send_message("안녕").sent)
        self.assertEqual((net.calls, clock.sleeps), (3, [1, 2]))

    def test_client_errors_are_never_retried(self):
        for code, description in ((400, "Bad Request: x"), (401, "Unauthorized"), (403, "Forbidden"), (404, "Not Found")):
            with self.subTest(code=code):
                notifier, net, clock = make_notifier(net=FakeNet(http_error(code, description), ok_reply()))
                self.assertFalse(notifier.send_message("안녕").sent)
                self.assertEqual((net.calls, clock.sleeps), (1, []))

    def test_html_that_telegram_cannot_parse_is_resent_as_plain_text_once(self):
        notifier, net, _ = make_notifier(net=FakeNet(http_error(400, "Bad Request: can't parse entities: Unsupported start tag \"br\""), ok_reply()))
        result = notifier.send_message("<b>굵게</b> &amp; <a href=\"https://github.com/shine88pc/chanceblog\">링크</a>", parse_mode="HTML")
        self.assertTrue(result.sent)
        first, second = net.bodies()
        self.assertEqual(first["parse_mode"], "HTML")
        self.assertNotIn("parse_mode", second)
        self.assertEqual(second["text"], "굵게 & 링크")

    def test_the_plain_resend_happens_once_even_if_it_is_also_rejected(self):
        notifier, net, _ = make_notifier(net=FakeNet(http_error(400, "Bad Request: can't parse entities: x")))
        result = notifier.send_message("<b>x</b>", parse_mode="HTML")
        self.assertEqual((result.sent, result.reason, net.calls), (False, "bad_request", 2))

    def test_a_parse_error_on_a_plain_message_is_not_retried(self):
        notifier, net, _ = make_notifier(net=FakeNet(http_error(400, "Bad Request: can't parse entities: x"), ok_reply()))
        result = notifier.send_message("평문")
        self.assertEqual((result.sent, result.reason, net.calls), (False, "parse_error", 1))

    def test_rejected_buttons_are_dropped_and_the_message_is_resent_once(self):
        notifier, net, _ = make_notifier(net=FakeNet(http_error(400, "Bad Request: BUTTON_URL_INVALID"), ok_reply()))
        result = notifier.send_message("본문", buttons=[("열기", BLOG_URL)])
        self.assertTrue(result.sent)
        first, second = net.bodies()
        self.assertIn("reply_markup", first)
        self.assertNotIn("reply_markup", second)
        self.assertEqual(second["text"], first["text"])

    def test_a_button_error_without_buttons_is_not_retried(self):
        notifier, net, _ = make_notifier(net=FakeNet(http_error(400, "Bad Request: BUTTON_URL_INVALID"), ok_reply()))
        self.assertEqual(notifier.send_message("본문").reason, "button_error")
        self.assertEqual(net.calls, 1)

    def test_the_worst_case_is_five_requests(self):
        net = FakeNet(http_error(429, retry_after=1), urllib.error.URLError("x"), http_error(400, "Bad Request: can't parse entities: x"),
                      http_error(400, "Bad Request: BUTTON_URL_INVALID"), http_error(400, "Bad Request: nope"), ok_reply())
        notifier, _, _ = make_notifier(net=net)
        result = notifier.send_message("<b>x</b>", parse_mode="HTML", buttons=[("열기", BLOG_URL)])
        self.assertEqual((result.sent, result.reason, net.calls), (False, "bad_request", 5))


class LeakTest(unittest.TestCase):
    """토큰이 요청 주소의 경로에 들어가는 서비스라, 예외 문구·응답 설명·사슬에 주소가 실리면 공개 로그로 샌다. 어떤 실패 모양에서도 결과에 값이 없어야 한다."""

    @staticmethod
    def requests_style():
        """requests 라이브러리가 연결 실패 때 내는 예외 문자열의 모양(요청 주소의 경로에 토큰이 든다)."""
        class ConnectionError(Exception):          # noqa: A001 - requests.exceptions.ConnectionError 흉내
            pass
        return ConnectionError("HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries exceeded with url: "
                               f"/bot{TOKEN}/sendMessage (Caused by NewConnectionError('<urllib3.connection.HTTPSConnection object at 0x7f>: "
                               "Failed to establish a new connection: [Errno -2] Name or service not known'))")

    @staticmethod
    def chained():
        try:
            try:
                raise OSError(f"[Errno 111] Connection refused: {nh.SEND_URL}")
            except OSError as inner:
                raise RuntimeError(f"request to {nh.SEND_URL} failed") from inner
        except RuntimeError as exc:
            return exc

    def scenarios(self):
        encoded = TOKEN.replace(":", "%3A")
        return {
            "requests 식 연결 실패": self.requests_style(),
            "원인 사슬에 주소": self.chained(),
            "InvalidURL": http.client.InvalidURL(f"URL can't contain control characters. '/bot{TOKEN}/sendMessage' (found at least ' ')"),
            "URLError 에 주소": urllib.error.URLError(f"<urlopen error {nh.SEND_URL}>"),
            "ValueError 에 주소": ValueError(f"unknown url type: {nh.SEND_URL}"),
            "gaierror 에 토큰": socket.gaierror(-2, f"Name or service not known ({TOKEN})"),
            "OSError 인코딩 형태": OSError(f"bad: https://api.telegram.org/bot{encoded}/sendMessage"),
            "401 설명에 토큰": http_error(401, f"Unauthorized: bot{TOKEN}"),
            "400 설명에 채팅 ID": http_error(400, f"Bad Request: chat not found ({CHAT})"),
            "403 설명에 인코딩 토큰": http_error(403, f"Forbidden: {encoded} {nh.SEND_URL}"),
            "429 설명에 토큰": http_error(429, f"Too Many Requests {TOKEN}", retry_after=1),
            "500 설명에 비밀 절반": http_error(500, f"oops {TOKEN.split(':')[1]}"),
            "200 이지만 본문이 토큰": FakeResponse(200, f"<html>{TOKEN}</html>"),
            "200 JSON 에 토큰": FakeResponse(200, {"ok": False, "description": f"{TOKEN} {CHAT}"}),
            "HTTPError 본문이 읽기 불가": http_error(401, raw=TOKEN.encode("utf-8")),
        }

    def test_no_failure_shape_leaks_the_token_or_chat_id_into_the_result(self):
        for name, outcome in self.scenarios().items():
            with self.subTest(name=name):
                notifier, net, _ = make_notifier(net=FakeNet(outcome))
                result = notifier.send_message("안녕")
                self.assertEqual(leaks(repr(result), str(result), notify.describe(result), result.detail, result.reason), [])
                self.assertNotIn(TOKEN, repr(result._asdict()))

    def test_scrubbed_descriptions_keep_the_rest_of_the_sentence(self):
        notifier, _, _ = make_notifier(net=FakeNet(http_error(401, f"Unauthorized: bot{TOKEN} rejected")))
        result = notifier.send_message("안녕")
        self.assertEqual(result.detail, "Unauthorized: bot*** rejected")

    def test_the_exception_text_is_never_used_only_the_class_name(self):
        class Secretive(Exception):
            def __str__(self):
                return f"{nh.SEND_URL} 에 실패"
        notifier, _, _ = make_notifier(net=FakeNet(Secretive()))
        result = notifier.send_message("안녕")
        self.assertEqual((result.reason, result.detail), ("network", ""))

    def test_an_unexpected_internal_error_reports_only_the_class_name(self):
        notifier, _, _ = make_notifier()
        with mock.patch.object(notify.Notifier, "_deliver", side_effect=RuntimeError(f"boom {nh.SEND_URL}")):
            result = notifier.send_message("안녕")
        self.assertEqual((result.ok, result.sent, result.reason, result.detail), (False, False, "internal_error", "RuntimeError"))
        self.assertEqual(leaks(repr(result)), [])

    def test_event_functions_never_raise_and_report_internal_errors_by_class_name(self):
        notifier, _, _ = make_notifier()
        with mock.patch.object(notify.Notifier, "send_message", side_effect=RuntimeError(nh.SEND_URL)):
            results = [notifier.notify_chance_published(posts()), notifier.notify_draft_waiting("c", "t", "w"),
                       notifier.notify_blogger_result("posted", "t"), notifier.notify_ops_alert(["a"], ""), notifier.notify_test()]
        for result in results:
            self.assertEqual((result.ok, result.reason, result.detail), (False, "internal_error", "RuntimeError"))
            self.assertEqual(leaks(repr(result)), [])

    def test_titles_that_contain_the_token_are_masked_in_the_message_itself(self):
        notifier, net, _ = make_notifier()
        notifier.notify_chance_published(posts(kr_title=f"제목 {TOKEN} 끝", en_title=f"{TOKEN}"))
        self.assertEqual(leaks(str(net.requests[0].data, "utf-8"), chat=False), [])

    def test_scrub_removes_every_form_of_the_values(self):
        notifier, _, _ = make_notifier()
        text = " | ".join([TOKEN, TOKEN.replace(":", "%3A"), TOKEN.replace(":", "%3a"), TOKEN.replace(":", "%3A").lower(), CHAT, nh.SECRET_HALF, nh.BOT_ID,
                           f"/bot{TOKEN}/sendMessage"])
        cleaned = notifier.scrub(text)
        self.assertEqual(leaks(cleaned), [])
        self.assertEqual(cleaned.count("***"), 8)

    def test_scrub_without_values_still_masks_secret_shapes(self):
        notifier, _, _ = make_notifier(environ={})
        self.assertEqual(notifier.scrub("x " + nh.BOT_ID + ":" + nh.SECRET_HALF + " y"), "x *** y")
        self.assertEqual(notifier.scrub(None), "")

    def test_the_token_shape_is_a_registered_secret_pattern(self):
        from pipeline.llm import mask
        from pipeline.secret_patterns import find_secrets
        self.assertIn("Telegram 봇 토큰", [label for label, _ in find_secrets(TOKEN)])
        self.assertEqual(mask(f"url=/bot{TOKEN}/sendMessage"), "url=/bot***/sendMessage")


class SanitizeTest(unittest.TestCase):
    def test_clean_text_folds_to_one_short_line(self):
        self.assertEqual(notify.clean_text("a\n\nb\r\n c\t\td"), "a b c d")
        self.assertEqual(notify.clean_text("a\x00b\x07c\x1bd"), "a b c d")
        self.assertEqual(notify.clean_text("a" + chr(0x2028) + "b" + chr(0x2029) + "c" + chr(0x85) + "d"), "a b c d")
        self.assertEqual(notify.clean_text(None), "")
        self.assertEqual(notify.clean_text(123), "123")

    def test_clean_text_truncates_with_an_ellipsis(self):
        text = notify.clean_text("가" * 500, 120)
        self.assertEqual(len(text), 120)
        self.assertTrue(text.endswith("…"))
        self.assertEqual(notify.clean_text("가" * 120, 120), "가" * 120)

    def test_clean_text_defuses_workflow_commands(self):
        for raw in ("::error::가짜", "  ::warning::x", "a\n::set-output name=x::y", "##[group]x"):
            with self.subTest(raw=raw):
                cleaned = notify.clean_text(raw)
                self.assertNotIn("::", cleaned)
                self.assertNotIn("##[", cleaned)

    def test_clean_text_removes_invisible_and_direction_controls(self):
        self.assertEqual(notify.clean_text("a" + chr(0x200B) + "b" + chr(0x200F) + "c" + chr(0x202E) + "d" + chr(0x2066) + "e" + chr(0xFEFF) + "f" + chr(0xAD) + "g"), "abcdefg")

    def test_clean_text_removes_lone_surrogates_but_keeps_emoji(self):
        self.assertEqual(notify.clean_text("a\ud83dz"), "az")
        self.assertEqual(notify.clean_text("a\U0001F600z"), "a\U0001F600z")

    def test_clean_text_masks_secret_shapes(self):
        key = "AIza" + "B" * 35
        self.assertNotIn(key, notify.clean_text(f"제목 {key}"))
        self.assertNotIn(TOKEN, notify.clean_text(f"제목 {TOKEN}"))

    def test_escape_html_only_changes_the_three_characters(self):
        self.assertEqual(notify.escape_html("<script>a&b</script> \"q\" 'q'"), "&lt;script&gt;a&amp;b&lt;/script&gt; \"q\" 'q'")

    def test_defang_urls_breaks_the_scheme_separator(self):
        for scheme in ("http", "https", "HTTPS", "ftp", "tg"):
            out = notify.defang_urls(f"가 {scheme}://evil.example/x 나")
            self.assertNotIn("://", out)
            self.assertIn("evil.example", out)
        self.assertEqual(notify.defang_urls("그냥 글: 비율 3:1"), "그냥 글: 비율 3:1")

    def test_titles_in_html_messages_cannot_inject_tags(self):
        notifier, net, _ = make_notifier()
        notifier.notify_chance_published(posts(kr_title='<script>alert(1)</script><a href="https://evil.example">x</a> & "y"', en_title="<b>bold</b>"))
        text = net.bodies()[0]["text"]
        self.assertNotIn("<script", text)
        self.assertNotIn("evil.example\">", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", text)
        self.assertIn("&amp;", text)
        import re
        tags = set(re.findall(r"</?([a-z]+)", text))
        self.assertLessEqual(tags, {"b", "a"})

    def test_markdown_link_syntax_in_a_title_is_just_text(self):
        notifier, net, _ = make_notifier()
        notifier.notify_chance_published(posts(kr_title="[클릭](https://evil.example/x) 제목"))
        text = net.bodies()[0]["text"]
        self.assertIn("[클릭](", text)
        self.assertNotIn('href="https://evil.example', text)
        self.assertEqual(net.bodies()[0]["parse_mode"], "HTML")

    def test_mentions_and_hashtags_are_passed_through_harmlessly_in_plain_alerts(self):
        notifier, net, _ = make_notifier()
        notifier.notify_ops_alert(["@someone 에게 #12 를 보냈다"], "")
        self.assertNotIn("parse_mode", net.bodies()[0])
        self.assertIn("@someone 에게 #12 를 보냈다", net.bodies()[0]["text"])

    def test_workflow_commands_in_titles_cannot_start_a_line(self):
        notifier, net, _ = make_notifier()
        notifier.notify_draft_waiting("티스토리", "::error::가짜 실패\n::warning::x", "어디서")
        for line in net.bodies()[0]["text"].splitlines():
            self.assertFalse(line.lstrip().startswith("::"), line)


class UrlTest(unittest.TestCase):
    ALLOWED = ("https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-093056/", "https://shine88pc.github.io/", "https://shine88pc.github.io",
               "https://github.com/shine88pc/chanceblog/issues/22", "https://github.com/shine88pc/chanceblog/actions/runs/123?x=1#y",
               "https://github.com/shine88pc/chanceblog", "https://www.blogger.com/", "https://www.blogger.com/blog/posts/12345",
               "https://shine88pc.github.io/chanceblog/posts/2026/10/20/korean-food-date-labels/",
               "https://shine88pc.github.io/chanceblog/posts/2026/10/27/%ED%95%9C%EA%B8%80/", "https://SHINE88PC.github.io/x")
    DENIED = (
        "http://shine88pc.github.io/chanceblog/", "https://shine88pc.github.io.evil.example/x", "https://evil.example/https://shine88pc.github.io/",
        "https://shine88pc.github.io@evil.example/", "https://evil.example@shine88pc.github.io/x", "https://github.com@evil.example/shine88pc/chanceblog/",
        "https://github.com/shine88pc/chanceblogger/x", "https://github.com/shine88pc/other/x", "https://github.com/other/chanceblog/x",
        "https://github.com/shine88pc/chanceblog/../../evil/repo", "https://github.com/shine88pc/chanceblog/%2e%2e/%2e%2e/evil",
        "https://github.com/shine88pc/chanceblog/./x/../..", "https://shine88pc.github.io:8443/x", "https://shine88pc.github.io:443/x",
        "https://shine88pc.github.io/x y", 'https://shine88pc.github.io/"onmouseover="x', "https://shine88pc.github.io/<b>",
        "https://shine88pc.github.io/x\nHost: evil", "https://shine88pc.github.io/\\evil", "javascript:alert(1)", "tg://resolve?domain=x",
        "//github.com/shine88pc/chanceblog/", "https://gist.github.com/shine88pc/x", "https://blogger.com/", "https://www.blogger.com.evil.example/",
        "https://macat0722.blogspot.com/2026/10/x.html", "ftp://shine88pc.github.io/x", "", None, 123, "https://", "https://[::1]/", "x" * 700,
        "https://shine88pc.github.io/" + "a" * 700,
    )

    def test_allowed_addresses_pass_unchanged(self):
        for url in self.ALLOWED:
            with self.subTest(url=url):
                self.assertEqual(notify.allowed_url(url), url)

    def test_everything_else_is_refused(self):
        for url in self.DENIED:
            with self.subTest(url=str(url)[:50]):
                self.assertEqual(notify.allowed_url(url), "")

    def test_extra_prefixes_come_from_code_and_allow_that_host_only(self):
        blog = "https://macat0722.blogspot.com/"
        self.assertEqual(notify.allowed_url("https://macat0722.blogspot.com/2026/10/x.html", (blog,)), "https://macat0722.blogspot.com/2026/10/x.html")
        self.assertEqual(notify.allowed_url("https://other.blogspot.com/x", (blog,)), "")
        self.assertEqual(notify.allowed_url("http://macat0722.blogspot.com/x", (blog,)), "")
        self.assertEqual(notify.allowed_url("https://macat0722.blogspot.com.evil.example/x", (blog,)), "")
        self.assertEqual(notify.allowed_url("https://macat0722.blogspot.com/x", ("not a url", None, "http://macat0722.blogspot.com/")), "")
        self.assertEqual(notify.allowed_url("https://macat0722.blogspot.com/x"), "")

    def test_a_disallowed_address_is_shown_defanged_not_linked(self):
        notifier, net, _ = make_notifier()
        notifier.notify_chance_published(posts(kr_url="https://evil.example/phish", en_url=EN_URL))
        body = net.bodies()[0]
        self.assertNotIn("https://evil.example", body["text"])
        self.assertIn("evil.example/phish", body["text"])
        self.assertEqual([button["text"] for button in body["reply_markup"]["inline_keyboard"][0]], ["English"])

    def test_href_values_are_attribute_safe(self):
        notifier, net, _ = make_notifier()
        notifier.notify_chance_published(posts(), {"run_url": "https://github.com/shine88pc/chanceblog/actions/runs/9?a=1&b='2'"})
        text = net.bodies()[0]["text"]
        self.assertIn('<a href="https://github.com/shine88pc/chanceblog/actions/runs/9?a=1&amp;b=&#x27;2&#x27;">열기</a>', text)


class LengthTest(unittest.TestCase):
    def test_utf16_len_counts_astral_characters_twice(self):
        self.assertEqual(notify.utf16_len("한글abc"), 5)
        self.assertEqual(notify.utf16_len("\U0001F600"), 2)
        self.assertEqual(notify.utf16_len("a\ud800"), 2)         # 짝 없는 서로게이트도 세기만 한다(예외 없음)

    def test_fit_text_keeps_short_text_and_cuts_long_text_with_an_ellipsis(self):
        self.assertEqual(notify.fit_text("가" * 3800), "가" * 3800)
        cut = notify.fit_text("가" * 3801)
        self.assertEqual((len(cut), cut[-1], notify.utf16_len(cut)), (3800, "…", 3800))
        self.assertEqual(cut[:-1], "가" * 3799)

    def test_fit_text_counts_utf16_units_so_emoji_text_is_cut_earlier(self):
        cut = notify.fit_text("\U0001F600" * 2500)
        self.assertLessEqual(notify.utf16_len(cut), 3800)
        self.assertTrue(cut.endswith("…"))
        self.assertNotIn("\ud83d", cut.replace("\U0001F600", ""))          # 서로게이트 쌍이 갈라지지 않는다
        self.assertEqual(notify.utf16_len(notify.fit_text("\U0001F600" * 1900)), 3800)

    def test_fit_text_with_a_custom_limit(self):
        self.assertEqual(notify.fit_text("abcdef", 4), "abc…")
        self.assertEqual(notify.fit_text("abcd", 4), "abcd")

    def test_long_plain_messages_are_cut_before_sending(self):
        notifier, net, _ = make_notifier()
        notifier.send_message("가" * 5000)
        text = net.bodies()[0]["text"]
        self.assertEqual((len(text), text[-1]), (3800, "…"))

    def test_long_html_messages_fall_back_to_plain_text_without_broken_tags(self):
        notifier, net, _ = make_notifier()
        notifier.send_message("<b>" + "가" * 4000 + "</b>", parse_mode="HTML")
        body = net.bodies()[0]
        self.assertNotIn("parse_mode", body)
        self.assertNotIn("<", body["text"])
        self.assertEqual(notify.utf16_len(body["text"]), 3800)

    def test_html_to_plain(self):
        self.assertEqual(notify.html_to_plain('<b>a</b> &lt;x&gt; &amp; <a href="https://shine88pc.github.io/">b</a>'), "a <x> & b")


class BudgetTest(unittest.TestCase):
    def test_at_most_five_messages_per_process(self):
        notifier, net, _ = make_notifier()
        results = [notifier.send_message(f"{i}") for i in range(7)]
        self.assertEqual([r.sent for r in results], [True] * 5 + [False] * 2)
        self.assertEqual([r.reason for r in results[5:]], ["limit", "limit"])
        self.assertEqual(net.calls, 5)
        self.assertEqual(leaks(*[repr(r) for r in results]), [])

    def test_failed_attempts_count_toward_the_cap(self):
        notifier, net, _ = make_notifier(net=FakeNet(http_error(401, "Unauthorized")))
        for _ in range(7):
            notifier.send_message("x")
        self.assertEqual(net.calls, 5)

    def test_disabled_and_invalid_calls_do_not_use_the_budget(self):
        budget = notify.Budget()
        for env in ({}, {"TELEGRAM_BOT_TOKEN": "bad", "TELEGRAM_CHAT_ID": CHAT}):
            notifier, _, _ = make_notifier(environ=env, budget=budget)
            for _ in range(10):
                notifier.send_message("x")
        self.assertEqual(budget.used, 0)

    def test_messages_are_spaced_by_at_least_1_1_seconds(self):
        notifier, net, clock = make_notifier()
        notifier.send_message("a")
        self.assertEqual(clock.sleeps, [])
        notifier.send_message("b")
        self.assertEqual([round(s, 3) for s in clock.sleeps], [1.1])
        clock.advance(0.4)
        notifier.send_message("c")
        self.assertAlmostEqual(clock.sleeps[-1], 0.7, places=3)
        clock.advance(5)
        notifier.send_message("d")
        self.assertEqual(len(clock.sleeps), 2)                    # 이미 충분히 지났으면 기다리지 않는다

    def test_the_budget_is_shared_between_notifiers_by_default(self):
        notify.reset_budget()
        try:
            first = notify.Notifier(ENV, opener=FakeNet(), sleep=lambda s: None, clock=nh.Clock().clock)
            second = notify.Notifier(ENV, opener=FakeNet(), sleep=lambda s: None, clock=nh.Clock().clock)
            for _ in range(3):
                first.send_message("a")
            for _ in range(3):
                second.send_message("b")
            self.assertEqual(notify.reset_budget() or 0, 0)
        finally:
            notify.reset_budget()

    def test_the_default_budget_limits_across_notifiers(self):
        notify.reset_budget()
        try:
            net = FakeNet()
            made = [notify.Notifier(ENV, opener=net, sleep=lambda s: None, clock=nh.Clock().clock) for _ in range(3)]
            results = [made[i % 3].send_message("a") for i in range(7)]
            self.assertEqual([r.sent for r in results], [True] * 5 + [False] * 2)
        finally:
            notify.reset_budget()

    def test_a_failed_send_still_stamps_the_time_for_spacing(self):
        notifier, net, clock = make_notifier(net=FakeNet(http_error(401, "Unauthorized"), ok_reply()))
        notifier.send_message("a")
        notifier.send_message("b")
        self.assertEqual([round(s, 3) for s in clock.sleeps], [1.1])


class EventMessageTest(unittest.TestCase):
    def sent(self, call):
        notifier, net, _ = make_notifier()
        result = call(notifier)
        self.assertTrue(result.sent, result)
        self.assertEqual(net.calls, 1)
        return net.bodies()[0]

    def test_chance_published_message(self):
        body = self.sent(lambda n: n.notify_chance_published(posts(), {"run_url": "https://github.com/shine88pc/chanceblog/actions/runs/42"}))
        self.assertEqual(body["parse_mode"], "HTML")
        self.assertNotIn("disable_notification", body)
        lines = body["text"].split("\n")
        self.assertEqual(lines[0], f"{notify.OK_MARK} <b>새 글이 발행됐습니다</b>")
        self.assertEqual(lines[1], f"{notify.FLAGS['ko']} 한글 제목")
        self.assertEqual(lines[2], f"{notify.FLAGS['en']} English Title")
        self.assertIn("분야: 경제·일 · Economy &amp; Work", lines)
        self.assertIn("출처: 유럽연합 CINEA", lines)
        wait_line = f"{notify.WAIT_MARK} {notify.DEPLOY_WAIT_NOTE}"
        self.assertIn(wait_line, lines)
        self.assertEqual(lines[lines.index(wait_line) + 1:][:2], [BLOG_URL, EN_URL])
        self.assertEqual(lines[-1], '실행 기록: <a href="https://github.com/shine88pc/chanceblog/actions/runs/42">열기</a>')
        self.assertEqual(body["reply_markup"], {"inline_keyboard": [[{"text": "한글 글", "url": BLOG_URL}, {"text": "English", "url": EN_URL}]]})

    def test_chance_published_tells_the_reader_to_wait_three_minutes_because_of_the_cached_404(self):
        """독립 검증 N-2(D-41): 알림은 배포를 요청한 직후에 와서, 일찍 열면 공개 CDN 이 그 404 를 최대 약 18분 보관할 수 있다 — 문구가 그 사실과 '3분 뒤'를 말한다."""
        body = self.sent(lambda n: n.notify_chance_published(posts()))
        lines = body["text"].split("\n")
        wait = next(line for line in lines if line.startswith(notify.WAIT_MARK))
        for needle in ("배포가 끝나기까지 약 3분", "일찍 열면 404 가 최대 약 18분 보관될 수 있으니", "3분 뒤에 열어 보세요"):
            self.assertIn(needle, wait)
        self.assertLess(lines.index(wait), lines.index(BLOG_URL))          # 주소보다 먼저 읽힌다
        self.assertNotIn("1~3분", body["text"])

    def test_chance_published_escapes_the_source_name_and_the_category(self):
        """독립 검증 E08: 출처 이름·분야에 든 <·&·> 는 글자로 보내야 한다(이스케이프가 빠지면 텔레그램이 서식으로 읽어 400 이 난다)."""
        two = posts()
        two[0]["source_name"] = "A <b>x</b> & B"
        two[0]["category"] = "C <i>y</i> & D"
        text = self.sent(lambda n: n.notify_chance_published(two))["text"]
        self.assertIn("출처: A &lt;b&gt;x&lt;/b&gt; &amp; B", text.split("\n"))
        self.assertIn("분야: C &lt;i&gt;y&lt;/i&gt; &amp; D · Economy &amp; Work", text.split("\n"))
        self.assertNotIn("<b>x</b>", text)
        self.assertNotIn("<i>y</i>", text)

    def test_chance_published_address_lines_are_html_escaped_but_the_buttons_keep_the_raw_address(self):
        """독립 검증 U16: 허용된 주소에도 쿼리 구분자 & 가 있을 수 있다 — 글자로 보이는 주소 줄은 이스케이프하고 버튼 주소는 그대로 둔다."""
        kr, en = BLOG_URL + "?a=1&b=2", EN_URL + "?c=3&d=4"
        body = self.sent(lambda n: n.notify_chance_published(posts(kr_url=kr, en_url=en)))
        lines = body["text"].split("\n")
        self.assertIn(BLOG_URL + "?a=1&amp;b=2", lines)
        self.assertIn(EN_URL + "?c=3&amp;d=4", lines)
        self.assertNotIn("?a=1&b=2", body["text"])
        self.assertEqual([button["url"] for button in body["reply_markup"]["inline_keyboard"][0]], [kr, en])

    def test_chance_published_never_turns_text_in_a_title_or_source_into_a_link(self):
        """독립 검증 N-7: 제목·분야·출처 속 https://…·tg://… 는 텔레그램이 링크로 바꾸지 못하게 글자로만 둔다(링크는 허용 목록의 주소를 코드가 건 것뿐)."""
        hostile = posts(kr_title="클릭 https://evil.example/login 하세요", en_title="open tg://resolve?domain=evil now")
        hostile[0]["source_name"] = "Src http://evil.example/x"
        hostile[1]["category"] = "Cat ftp://evil.example"
        text = self.sent(lambda n: n.notify_chance_published(hostile))["text"]
        for raw in ("https://evil.example", "tg://resolve", "http://evil.example", "ftp://evil.example"):
            self.assertNotIn(raw, text)
        for shown in ("https" + FW_COLON + "//evil.example/login", "tg" + FW_COLON + "//resolve?domain=evil", "http" + FW_COLON + "//evil.example/x",
                      "ftp" + FW_COLON + "//evil.example"):
            self.assertIn(shown, text)
        self.assertEqual(text.count("https://"), 2)                     # 남은 것은 코드가 건 예상 공개 주소 둘뿐

    def test_chance_published_puts_the_korean_post_first_whatever_the_input_order(self):
        body = self.sent(lambda n: n.notify_chance_published(list(reversed(posts()))))
        self.assertLess(body["text"].index("한글 제목"), body["text"].index("English Title"))
        self.assertEqual([b["text"] for b in body["reply_markup"]["inline_keyboard"][0]], ["한글 글", "English"])

    def test_chance_published_with_one_language_only(self):
        body = self.sent(lambda n: n.notify_chance_published(posts()[1:]))
        self.assertNotIn(notify.FLAGS["ko"], body["text"])
        self.assertEqual([b["text"] for b in body["reply_markup"]["inline_keyboard"][0]], ["English"])

    def test_chance_published_without_addresses_has_no_buttons_and_no_address_lines(self):
        body = self.sent(lambda n: n.notify_chance_published(posts(kr_url="", en_url=None)))
        self.assertNotIn("reply_markup", body)
        self.assertNotIn("https://", body["text"])

    def test_chance_published_run_url_must_be_allowed(self):
        body = self.sent(lambda n: n.notify_chance_published(posts(), {"run_url": "https://evil.example/runs/1"}))
        self.assertNotIn("실행 기록", body["text"])
        self.assertNotIn("evil.example", body["text"])

    def test_chance_published_shows_each_category_once(self):
        two_same = posts()
        two_same[1]["category"] = two_same[0]["category"]
        body = self.sent(lambda n: n.notify_chance_published(two_same))
        self.assertEqual(body["text"].count("경제·일"), 1)

    def test_chance_published_ignores_garbage_entries_and_reports_nothing_to_send(self):
        notifier, net, _ = make_notifier()
        for value in ([], None, ["x", 3, None]):
            result = notifier.notify_chance_published(value)
            self.assertEqual((result.ok, result.sent, result.reason), (True, False, "not_applicable"))
        self.assertEqual(net.calls, 0)

    def test_chance_published_titles_are_limited_to_120_characters(self):
        body = self.sent(lambda n: n.notify_chance_published(posts(kr_title="가" * 400)))
        title_line = body["text"].split("\n")[1]
        self.assertLessEqual(len(title_line), 130)
        self.assertTrue(title_line.endswith("…"))

    def test_draft_waiting_message(self):
        body = self.sent(lambda n: n.notify_draft_waiting("티스토리", "초안 제목", "GitHub 이슈 #5 를 열어 본문을 복사해 붙여넣고 발행하세요",
                                                          url="https://github.com/shine88pc/chanceblog/issues/5"))
        self.assertEqual(body["text"], f"{notify.MEMO_MARK} <b>발행 대기</b> — 티스토리: 초안 제목\n→ GitHub 이슈 #5 를 열어 본문을 복사해 붙여넣고 발행하세요")
        self.assertEqual(body["parse_mode"], "HTML")
        self.assertEqual(body["reply_markup"], {"inline_keyboard": [[{"text": "열기", "url": "https://github.com/shine88pc/chanceblog/issues/5"}]]})

    def test_draft_waiting_without_or_with_a_bad_address_has_no_button(self):
        for url in (None, "", "https://evil.example/x"):
            with self.subTest(url=url):
                body = self.sent(lambda n, u=url: n.notify_draft_waiting("네이버", "제목", "어디서", url=u))
                self.assertNotIn("reply_markup", body)

    def test_draft_waiting_escapes_all_dynamic_parts(self):
        body = self.sent(lambda n: n.notify_draft_waiting("<채널>", "<b>제목</b> & 그", "<i>어디서</i>"))
        self.assertEqual(body["text"], f"{notify.MEMO_MARK} <b>발행 대기</b> — &lt;채널&gt;: &lt;b&gt;제목&lt;/b&gt; &amp; 그\n→ &lt;i&gt;어디서&lt;/i&gt;")

    def test_draft_waiting_limits_the_length_of_every_part(self):
        body = self.sent(lambda n: n.notify_draft_waiting("c" * 300, "t" * 300, "w" * 900))
        self.assertLess(len(body["text"]), 120 + 60 + 200 + 80)

    def test_blogger_draft_uploaded(self):
        body = self.sent(lambda n: n.notify_blogger_result("draft_uploaded", "영문 글 제목", url="https://macat0722.blogspot.com/p/x.html"))
        self.assertEqual(body["text"], f"{notify.MEMO_MARK} <b>발행 대기</b> — Blogger: 영문 글 제목\n→ 초안함에 올라왔습니다 — Blogger 대시보드 → 초안에서 확인하고 게시하세요")
        self.assertEqual(body["reply_markup"]["inline_keyboard"][0][0]["url"], "https://www.blogger.com/")

    def test_blogger_posted(self):
        for code in ("posted", "published"):
            with self.subTest(code=code):
                body = self.sent(lambda n, c=code: n.notify_blogger_result(c, "영문 글 제목", url="https://macat0722.blogspot.com/2026/10/x.html",
                                                                        extra_prefixes=("https://macat0722.blogspot.com/",)))
                self.assertEqual(body["text"], f"{notify.OK_MARK} <b>게시됨</b> — Blogger: 영문 글 제목")
                self.assertEqual(body["reply_markup"]["inline_keyboard"][0], [{"text": "글 보기", "url": "https://macat0722.blogspot.com/2026/10/x.html"}])

    def test_blogger_posted_without_a_trusted_address_has_no_button(self):
        body = self.sent(lambda n: n.notify_blogger_result("posted", "제목", url="https://macat0722.blogspot.com/2026/10/x.html"))
        self.assertNotIn("reply_markup", body)

    def test_blogger_uses_the_blog_label(self):
        body = self.sent(lambda n: n.notify_blogger_result("draft_uploaded", "t", blog_label="Blogger 한글"))
        self.assertIn("Blogger 한글: t", body["text"])
        body = self.sent(lambda n: n.notify_blogger_result("draft_uploaded", "t", blog_label=""))
        self.assertIn("Blogger: t", body["text"])
        body = self.sent(lambda n: n.notify_blogger_result("posted", "t", blog_label="Blogger 한글"))        # 게시됨 쪽도 같은 라벨을 쓴다(독립 검증 H12)
        self.assertEqual(body["text"], f"{notify.OK_MARK} <b>게시됨</b> — Blogger 한글: t")

    def test_blogger_posted_escapes_the_title_and_the_label(self):
        """독립 검증 E12: AI 가 만든 제목이 가장 바깥의 입력이다 — 게시됨 알림도 제목·라벨의 <·&·> 를 글자로 보낸다."""
        body = self.sent(lambda n: n.notify_blogger_result("posted", "<i>x</i> & y", blog_label="<b>L</b> & M"))
        self.assertEqual(body["text"], f"{notify.OK_MARK} <b>게시됨</b> — &lt;b&gt;L&lt;/b&gt; &amp; M: &lt;i&gt;x&lt;/i&gt; &amp; y")

    def test_draft_waiting_never_turns_text_into_a_link(self):
        """독립 검증 N-7: 채널 이름·제목·안내 문구 속 주소는 글자로만 둔다(버튼은 허용 목록의 주소만)."""
        body = self.sent(lambda n: n.notify_draft_waiting("채널 https://c.example", "제목 https://evil.example/a", "여기 tg://resolve?domain=x 에서"))
        self.assertNotIn("://", body["text"])
        for shown in ("https" + FW_COLON + "//c.example", "https" + FW_COLON + "//evil.example/a", "tg" + FW_COLON + "//resolve?domain=x"):
            self.assertIn(shown, body["text"])

    def test_blogger_results_never_turn_the_title_or_the_label_into_a_link(self):
        for code in ("posted", "draft_uploaded"):
            with self.subTest(code=code):
                body = self.sent(lambda n, c=code: n.notify_blogger_result(c, "제목 https://evil.example/a tg://x", blog_label="Blogger https://l.example"))
                self.assertNotIn("://", body["text"])
                self.assertIn("https" + FW_COLON + "//evil.example/a", body["text"])
                self.assertIn("Blogger https" + FW_COLON + "//l.example", body["text"])

    def test_blogger_results_that_need_no_alert_send_nothing(self):
        notifier, net, _ = make_notifier()
        for code in ("publish_failed", "draft", "draft_saved", "rejected", "llm_failed", "skipped_no_topic", "generated_unpublished", "", None, "DRAFT_UPLOADED"):
            with self.subTest(code=code):
                result = notifier.notify_blogger_result(code, "제목")
                self.assertEqual((result.ok, result.sent, result.reason), (True, False, "not_applicable"))
        self.assertEqual(net.calls, 0)

    def test_ops_alert_is_plain_text_with_a_header_bullets_and_one_button(self):
        body = self.sent(lambda n: n.notify_ops_alert(["PR #1 병합하면 됩니다", "워크플로 실패 — x"], "https://github.com/shine88pc/chanceblog/issues/22", count=2))
        self.assertNotIn("parse_mode", body)
        self.assertEqual(body["text"], f"{notify.PIN_MARK} 확인 필요 모음 — 새로 해야 할 일 2건\n• PR #1 병합하면 됩니다\n• 워크플로 실패 — x")
        self.assertEqual(body["reply_markup"], {"inline_keyboard": [[{"text": "확인 필요 모음 열기", "url": "https://github.com/shine88pc/chanceblog/issues/22"}]]})

    def test_ops_alert_count_defaults_to_the_number_of_lines(self):
        body = self.sent(lambda n: n.notify_ops_alert(["a", "b", "c"], ""))
        self.assertIn("새로 해야 할 일 3건", body["text"])
        for bad in (0, -1, True, "5", None):
            body = self.sent(lambda n, c=bad: n.notify_ops_alert(["a", "b"], "", count=c))
            self.assertIn("새로 해야 할 일 2건", body["text"])

    def test_ops_alert_without_a_good_address_has_no_button(self):
        for url in ("", None, "https://evil.example/issues/1"):
            body = self.sent(lambda n, u=url: n.notify_ops_alert(["a"], u))
            self.assertNotIn("reply_markup", body)

    def test_ops_alert_lines_are_sanitized_defanged_and_limited(self):
        body = self.sent(lambda n: n.notify_ops_alert(["::error::나쁨 https://evil.example/x\n둘째 줄", "가" * 400, "   ", None, "AIza" + "B" * 35], ""))
        text = body["text"]
        self.assertNotIn("::", text)
        self.assertNotIn("://", text)
        self.assertNotIn("AIza" + "B" * 35, text)
        lines = text.split("\n")
        self.assertLessEqual(max(len(line) for line in lines), 170)
        self.assertEqual(len(lines), 1 + 3)                          # 헤더 + 비어 있지 않은 3줄

    def test_ops_alert_keeps_at_most_ten_lines(self):
        body = self.sent(lambda n: n.notify_ops_alert([f"항목 {i}" for i in range(30)], "", count=30))
        self.assertEqual(len(body["text"].split("\n")), 1 + 10)
        self.assertIn("새로 해야 할 일 30건", body["text"])

    def test_ops_alert_with_nothing_to_say_sends_nothing(self):
        notifier, net, _ = make_notifier()
        for lines in ([], None, ["", "  ", None]):
            self.assertEqual(notifier.notify_ops_alert(lines, "").reason, "not_applicable")
        self.assertEqual(net.calls, 0)

    def test_test_message(self):
        notifier, net, _ = make_notifier()
        notifier.notify_test(now=datetime(2026, 10, 27, 3, 5, tzinfo=timezone.utc))
        body = net.bodies()[0]
        self.assertNotIn("parse_mode", body)
        self.assertEqual(body["text"], f"{notify.OK_MARK} 알림 연결 확인\n챈스블로그의 새 글·발행 대기·확인 필요 알림이 이 채팅으로 옵니다.\n시험 시각: 2026-10-27 12:05 KST")

    def test_module_level_functions_use_the_given_notifier(self):
        notifier, net, _ = make_notifier()
        self.assertTrue(notify.send_message("a", notifier=notifier).sent)
        self.assertTrue(notify.notify_chance_published(posts(), notifier=notifier).sent)
        self.assertTrue(notify.notify_draft_waiting("c", "t", "w", url=BLOG_URL, notifier=notifier).sent)
        self.assertTrue(notify.notify_blogger_result("posted", "t", notifier=notifier).sent)
        self.assertTrue(notify.notify_ops_alert(["a"], "", notifier=notifier).sent)
        self.assertEqual(net.calls, 5)
        self.assertEqual(notify.notify_test(notifier=make_notifier()[0]).sent, True)

    def test_module_level_functions_build_a_notifier_from_the_environment(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(notify.send_message("a").reason, "disabled")
            self.assertEqual(notify.notify_ops_alert(["a"], "").reason, "disabled")


class DescribeTest(unittest.TestCase):
    def test_every_reason_has_a_korean_explanation(self):
        expected = {"sent", "disabled", "not_applicable", "invalid_token", "invalid_chat_id", "empty_text", "unauthorized", "forbidden", "not_found",
                    "chat_not_found", "bad_request", "parse_error", "button_error", "rate_limited", "server_error", "network", "timeout",
                    "bad_response", "limit", "internal_error"}
        self.assertEqual(set(notify.REASON_TEXT), expected)
        for reason in expected:
            self.assertRegex(notify.REASON_TEXT[reason], "[가-힣]", reason)

    def test_describe_includes_status_and_detail(self):
        text = notify.describe(notify.Result(False, False, 401, "unauthorized", "Unauthorized"))
        self.assertIn("401", text)
        self.assertIn("[HTTP 401, Unauthorized]", text)
        self.assertEqual(notify.describe(notify.Result(False, False, None, "network", "")), notify.REASON_TEXT["network"])
        self.assertEqual(notify.describe(notify.Result(False, False, None, "mystery", "")), "mystery")

    def test_the_operator_hints_name_the_actions(self):
        self.assertIn("/start", notify.REASON_TEXT["forbidden"])
        self.assertIn("/start", notify.REASON_TEXT["chat_not_found"])
        self.assertIn("BotFather", notify.REASON_TEXT["unauthorized"])
        self.assertIn("bot", notify.REASON_TEXT["invalid_token"])

    def test_log_result_is_silent_when_nothing_happened(self):
        lines = []
        for reason in ("disabled", "not_applicable"):
            notify.log_result(notify.Result(True, False, None, reason, ""), lines.append)
        self.assertEqual(lines, [])

    def test_log_result_for_a_sent_message_is_one_line(self):
        lines = []
        notify.log_result(notify.Result(True, True, 200, "sent", ""), lines.append)
        self.assertEqual(lines, ["[참고] 텔레그램 알림: 보냈습니다"])

    def test_log_result_for_a_failure_adds_a_fixed_warning(self):
        lines = []
        notify.log_result(notify.Result(False, False, 403, "forbidden", "Forbidden: bot was blocked"), lines.append)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("[참고] 텔레그램 알림을 보내지 못했습니다 — "))
        self.assertIn("403", lines[0])
        self.assertEqual(lines[1], notify.WARNING_LINE)
        self.assertTrue(notify.WARNING_LINE.startswith("::warning::"))
        self.assertNotIn("\n", notify.WARNING_LINE)


class RobustnessTest(unittest.TestCase):
    """알림은 어떤 입력에도 예외를 호출한 쪽으로 보내지 않고, 그 결과에도 값이 없다(`str()` 이 예외를 던지는 값·잘못된 모양·아주 긴 글)."""

    class Hostile:
        def __str__(self):
            raise RuntimeError(nh.SEND_URL)

        __repr__ = __str__

    def test_no_public_function_raises_for_hostile_inputs(self):
        bad = self.Hostile()
        notifier, net, _ = make_notifier()
        calls = [
            lambda: notifier.send_message(bad), lambda: notifier.send_message("x", buttons=bad), lambda: notifier.send_message("x", buttons=[(bad, bad)]),
            lambda: notifier.send_message("x", extra_prefixes=bad), lambda: notifier.send_message("x", buttons=[("a", bad)]),
            lambda: notifier.notify_chance_published([{"lang": "ko", "title": bad, "category": bad, "source_name": bad, "url": bad}], {"run_url": bad}),
            lambda: notifier.notify_chance_published(bad), lambda: notifier.notify_chance_published([{"title": "t"}], bad),
            lambda: notifier.notify_draft_waiting(bad, bad, bad, url=bad), lambda: notifier.notify_draft_waiting("c", "t", "w", url=bad),
            lambda: notifier.notify_blogger_result(bad, bad, url=bad, blog_label=bad), lambda: notifier.notify_blogger_result("posted", bad, url=bad, extra_prefixes=bad),
            lambda: notifier.notify_blogger_result("draft_uploaded", bad), lambda: notifier.notify_ops_alert(bad, bad, count=bad),
            lambda: notifier.notify_ops_alert([bad], bad), lambda: notifier.notify_ops_alert(["a"], bad), lambda: notifier.notify_test(now=bad),
            lambda: notify.allowed_url(bad), lambda: notify.clean_text(bad),
        ]
        for index, call in enumerate(calls):
            with self.subTest(call=index):
                try:
                    result = call()
                except Exception as exc:  # noqa: BLE001
                    if index >= len(calls) - 2:       # 모듈 수준 소독 함수는 호출한 쪽이 감싼다(알림 함수는 Result 로 돌려준다)
                        continue
                    self.fail(f"예외가 밖으로 나왔습니다: {type(exc).__name__}")
                self.assertIsInstance(result, notify.Result)
                self.assertEqual(leaks(repr(result), notify.describe(result)), [])

    def test_hostile_inputs_are_reported_by_class_name_only(self):
        notifier, _, _ = make_notifier()
        result = notifier.send_message(self.Hostile())
        self.assertEqual((result.ok, result.sent, result.reason, result.detail), (False, False, "internal_error", "RuntimeError"))

    def test_huge_inputs_are_cut_quickly(self):
        import time
        started = time.monotonic()
        notifier, net, _ = make_notifier()
        huge = "가" * 2_000_000
        self.assertTrue(notifier.send_message(huge).sent)
        self.assertEqual(notify.utf16_len(net.bodies()[0]["text"]), 3800)
        result = notifier.notify_chance_published([{"lang": "ko", "title": huge, "category": huge, "source_name": huge, "url": "https://shine88pc.github.io/" + "a" * 100}])
        self.assertTrue(result.sent)
        self.assertLess(len(net.bodies()[1]["text"]), 1500)
        self.assertTrue(notifier.notify_ops_alert([huge] * 50, "").sent)
        self.assertLess(len(net.bodies()[2]["text"]), 3000)
        self.assertLess(time.monotonic() - started, 5)                # 수백만 자 입력에도 정규식을 통째로 돌리지 않는다(예전에는 수십 초)

    def test_a_response_body_larger_than_the_cap_is_only_partly_read(self):
        class Endless:
            status = 200
            headers = {}
            read_sizes = []

            def read(self, n=-1):
                Endless.read_sizes.append(n)
                return b"{" + b" " * (n if n and n > 0 else 10 ** 7)

            def close(self):
                pass
        notifier, _, _ = make_notifier(net=FakeNet(Endless()))
        result = notifier.send_message("안녕")
        self.assertEqual((result.sent, result.reason), (False, "bad_response"))
        self.assertEqual(Endless.read_sizes, [65536])                     # 상수를 그대로 비교하면 값이 바뀌어도 통과한다(독립 검증 C07) — 64KB 라는 값 자체를 고정한다
        self.assertEqual(notify.MAX_RESPONSE_BYTES, 65536)


class SourceSafetyTest(unittest.TestCase):
    """소스 수준 불변식: 워크플로 명령(줄 머리 '::')은 고정 문장뿐이고, 토큰을 다루는 코드가 예외 문구를 출력하지 않는다."""

    @classmethod
    def setUpClass(cls):
        import ast
        cls.source = (_bootstrap.ROOT / "pipeline" / "notify.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_workflow_command_strings_are_fixed_sentences(self):
        import ast
        commands = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.JoinedStr):
                first = node.values[0] if node.values else None
                if isinstance(first, ast.Constant) and str(first.value).lstrip().startswith("::"):
                    self.fail(f"{node.lineno}번째 줄: 값을 끼운 f-string 이 워크플로 명령으로 시작합니다")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.lstrip().startswith("::"):
                commands.append(node.value)
        self.assertEqual(sorted(commands), sorted([notify.WARNING_LINE, notify.ERROR_LINE]))

    @staticmethod
    def harmless(parent, child):
        """예외 변수를 글로 만들지 않는 쓰임: type(exc)·getattr(exc, …)·isinstance(exc, …)·exc.code/.reason/.headers/.close·self._read_json(exc)."""
        import ast
        if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id in ("type", "getattr", "isinstance"):
            return True
        if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute) and parent.func.attr == "_read_json":
            return True
        return isinstance(parent, ast.Attribute) and parent.value is child and parent.attr in ("code", "reason", "headers", "close")

    def test_no_exception_is_ever_converted_to_text_except_by_class_name(self):
        """`str(exc)`·f"{exc}"·repr(exc) 로 예외를 글로 만드는 곳이 없다(예외 문구에는 요청 주소가 들어 있을 수 있다). 예외는 이 모듈이 직접 만든 GitError(고정 문구) 말고는
        클래스 이름·HTTP 상태·분류 속성으로만 쓴다."""
        import ast
        offenders = set()
        for handler in ast.walk(self.tree):
            if not (isinstance(handler, ast.ExceptHandler) and handler.name):
                continue
            kind = getattr(handler.type, "id", None) or getattr(handler.type, "attr", None) or "(여러 종류)"      # except 뒤의 예외 이름(Name·Attribute)
            for parent in ast.walk(handler):
                for child in ast.iter_child_nodes(parent):
                    if isinstance(child, ast.Name) and child.id == handler.name and isinstance(child.ctx, ast.Load) and not self.harmless(parent, child):
                        offenders.add(kind)
        self.assertEqual(sorted(offenders), ["GitError"])

    def test_the_token_is_interpolated_into_exactly_one_string_the_request_address(self):
        import ast
        uses = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.JoinedStr):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Attribute) and inner.attr == "_token":
                        uses.append([part.value if isinstance(part, ast.Constant) else (part.value.id if isinstance(part.value, ast.Name) else part.value.attr)
                                     for part in node.values])
        self.assertEqual(uses, [["API_BASE", "/bot", "_token", "/sendMessage"]])

    def test_there_are_no_debug_switches_or_traceback_printing(self):
        for banned in ("set_debuglevel", "traceback", "logging", "print_exc", "format_exc", "warnings"):
            self.assertNotIn(banned, self.source, banned)

    def test_only_the_standard_library_and_two_repository_modules_are_imported(self):
        import ast
        imported = set()
        for node in self.tree.body:
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(imported - {"pipeline"}, set(__import__("sys").stdlib_module_names))
        modules = {node.module for node in self.tree.body if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("pipeline")}
        self.assertEqual(modules, {"pipeline.console", "pipeline.llm"})


class LoopbackTest(unittest.TestCase):
    """가짜 urlopen 으로는 볼 수 없는 것을 실제 urllib 으로 확인한다: 127.0.0.1 의 임시 서버에만 보내고(텔레그램으로는 한 번도 나가지 않는다 — API_BASE 를 이 서버로 바꾼다),
    프록시 설정을 타지 않게 ProxyHandler({}) 를 단 opener 를 주입한다. 실제 HTTPError 의 본문 읽기·소켓 제한 시간·연결 거부가 분류로 이어지는지 본다."""

    def setUp(self):
        outer = self
        self.script, self.log = [], []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                outer.log.append({"path": self.path, "headers": dict(self.headers), "body": self.rfile.read(length)})
                status, body, delay = outer.script.pop(0) if len(outer.script) > 1 else outer.script[0]
                if delay:
                    threading.Event().wait(delay)
                raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except OSError:
                    pass                                           # 클라이언트가 제한 시간으로 먼저 끊은 경우

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        patcher = mock.patch.object(notify, "API_BASE", f"http://127.0.0.1:{self.server.server_address[1]}")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def notifier(self):
        clock = nh.Clock()
        return notify.Notifier(ENV, opener=self.direct.open, sleep=clock.sleep, clock=clock.clock, budget=notify.Budget()), clock

    def test_a_real_request_reaches_the_bot_path_with_a_json_body_and_no_credentials_in_headers(self):
        self.script = [(200, {"ok": True, "result": {"message_id": 1}}, 0)]
        notifier, _ = self.notifier()
        result = notifier.send_message("안녕 <b>x</b>", parse_mode="HTML", buttons=[("열기", BLOG_URL)], silent=True)
        self.assertEqual(result, notify.Result(True, True, 200, "sent", ""))
        seen = self.log[0]
        self.assertEqual(seen["path"], f"/bot{TOKEN}/sendMessage")
        self.assertEqual(seen["headers"]["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(seen["headers"]["User-Agent"], "chanceblog-notify")
        self.assertNotIn("Authorization", seen["headers"])
        body = json.loads(str(seen["body"], "utf-8"))
        self.assertEqual((body["chat_id"], body["text"], body["parse_mode"], body["disable_notification"]), (int(CHAT), "안녕 <b>x</b>", "HTML", True))
        self.assertEqual(body["reply_markup"]["inline_keyboard"][0][0]["url"], BLOG_URL)
        self.assertEqual(leaks(seen["headers"], chat=False), [])

    def test_real_error_bodies_are_read_and_classified(self):
        for status, description, reason in ((401, "Unauthorized", "unauthorized"), (400, "Bad Request: chat not found", "chat_not_found"),
                                            (403, "Forbidden: bot can't initiate conversation with a user", "forbidden"), (404, "Not Found", "not_found")):
            with self.subTest(status=status):
                self.script, self.log = [(status, {"ok": False, "error_code": status, "description": description}, 0)], []
                notifier, _ = self.notifier()
                result = notifier.send_message("안녕")
                self.assertEqual((result.sent, result.status, result.reason, result.detail), (False, status, reason, description))
                self.assertEqual(len(self.log), 1)

    def test_a_real_429_waits_the_announced_time_and_retries_once(self):
        self.script = [(429, {"ok": False, "error_code": 429, "description": "Too Many Requests: retry after 2", "parameters": {"retry_after": 2}}, 0),
                       (200, {"ok": True, "result": {}}, 0)]
        notifier, clock = self.notifier()
        result = notifier.send_message("안녕")
        self.assertEqual((result.sent, len(self.log), clock.sleeps), (True, 2, [2]))

    def test_a_real_5xx_with_an_html_body_is_a_server_error_after_one_retry(self):
        self.script = [(502, b"<html><body>Bad Gateway</body></html>", 0)]
        notifier, clock = self.notifier()
        result = notifier.send_message("안녕")
        self.assertEqual((result.reason, result.status, result.detail, len(self.log), clock.sleeps), ("server_error", 502, "", 2, [2]))

    def test_a_real_socket_timeout_is_a_timeout(self):
        self.script = [(200, {"ok": True}, 1.5)]
        notifier, clock = self.notifier()
        with mock.patch.object(notify, "TIMEOUT_SECONDS", 0.3):
            result = notifier.send_message("안녕")
        self.assertEqual((result.sent, result.reason, result.status, clock.sleeps), (False, "timeout", None, [2]))
        self.assertEqual(leaks(repr(result)), [])

    def test_a_refused_connection_is_a_network_failure_without_the_address(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        with mock.patch.object(notify, "API_BASE", f"http://127.0.0.1:{port}"):
            notifier, clock = self.notifier()
            result = notifier.send_message("안녕")
        self.assertEqual((result.sent, result.reason, result.status, result.detail, clock.sleeps), (False, "network", None, "", [2]))
        self.assertEqual(leaks(repr(result), notify.describe(result)), [])

    def test_the_stock_urlopen_is_what_runs_when_nothing_is_injected(self):
        """주입한 opener 가 없으면 urllib.request.urlopen 을 부른다(시험은 그것을 가짜로 바꿔 끼운다 — 작업 지시의 방식)."""
        net = FakeNet()
        notifier = notify.Notifier(ENV, sleep=lambda s: None, clock=nh.Clock().clock, budget=notify.Budget())
        with mock.patch("urllib.request.urlopen", net):
            self.assertTrue(notifier.send_message("안녕").sent)
        self.assertEqual(net.calls, 1)
        self.assertEqual(net.timeouts, [15])


if __name__ == "__main__":
    unittest.main()
