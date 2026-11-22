"""운영 알림이 조용히 사라지지 않게(L7, 결함 D-360·D-361·D-362·D-364) 시험.

세 가지를 본다. ① 열린 이슈 읽기의 쪽 넘기기와 '일부만 읽음' 경고(확인 필요 모음·워치독, D-361) ② 켜진 허용 목록 제공처의 약관 점검 기한이 14일 안으로 다가오면 미리 알리는 것(D-360)
③ 텔레그램 전송의 일시 오류 재시도(D-362 — 확실히 안 간 실패는 3번·받았을 수 있는 실패는 1번·통마다 첫 재시도 보장·한 실행 추가 재시도 상한과 270초 시간 안전망, 독립 검증 반영 D-364).
끝에는 문서의 숫자·이름·표를 코드와 맞춰 보는 시험(AlertDocsMatchCodeTest)이 있다. 네트워크·실제 시계는 쓰지 않는다 — 날짜·시각은 모두 값으로 넣고, 요청은 가짜 GitHub·가짜 HTTP 가 받는다. 가짜 비밀은 런타임에 조합한다.
"""
import ast
import contextlib
import datetime
import http.client
import io
import json
import pathlib
import re
import socket
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

import _bootstrap
import ops_inbox_helpers as h
import ops_inbox as oi
from notify_helpers import CHAT, ENV, TOKEN, Clock, FakeNet, http_error, leaks, make_notifier, ok_reply
from pipeline import inbox, notify, telegram_inbox, terms_deadline

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402

BUTTON_URL = "https://www.blogger.com/"        # 알림 버튼으로 허용된 주소(notify.ALLOWED_URLS) — 서식·버튼 대체 전송 시험이 쓴다


def issue_pages(fake, *numbers):
    """가짜 GitHub 에 열린 이슈를 번호만큼 더한다(최신 번호가 앞에 오지는 않는다 — 가짜는 넣은 순서대로 쪽을 자른다)."""
    for number in numbers:
        fake.issues.append(h.make_issue(number, f"일반 이슈 {number}", labels=("bug",)))
    return fake


class OpenIssuePagingTest(unittest.TestCase):
    """확인 필요 모음 fetch_issues(D-361): 한 쪽 100건씩 끝까지 읽고, 상한에 닿으면 '조회 실패' 항목으로 알린다."""

    def run_fetch(self, fake):
        failures = []
        found = oi.fetch_issues(fake, failures)
        return found, failures

    def pages_asked(self, fake):
        return [params for method, path, params in fake.log if method == "GET" and path == "/issues"]

    def test_a_short_first_page_is_one_call_without_any_warning(self):
        fake = issue_pages(h.FakeGitHub(), *range(1, 4))
        found, failures = self.run_fetch(fake)
        self.assertEqual((len(found), failures, len(self.pages_asked(fake))), (3, [], 1))

    def test_issues_beyond_the_first_hundred_are_read(self):
        fake = issue_pages(h.FakeGitHub(), *range(1, 150))
        fake.issues.append(h.make_watchdog(900))                       # 101번째 뒤에 있는 워치독 알림 — 예전에는 조용히 잘렸다
        found, failures = self.run_fetch(fake)
        self.assertEqual(failures, [])
        self.assertIn(900, [issue["number"] for issue in found])
        self.assertEqual(len(found), 150)
        asked = self.pages_asked(fake)
        self.assertEqual([p.get("page", 1) for p in asked], [1, 2])
        self.assertEqual(asked[0], {"state": "open", "per_page": 100})                # 첫 쪽 요청은 예전과 같다(page 는 기본값 1 이라 적지 않는다)
        self.assertEqual(asked[1], {"state": "open", "per_page": 100, "page": 2})

    def test_exactly_one_hundred_issues_end_on_an_empty_second_page_without_a_warning(self):
        fake = issue_pages(h.FakeGitHub(), *range(1, 101))
        found, failures = self.run_fetch(fake)
        self.assertEqual((len(found), failures, len(self.pages_asked(fake))), (100, [], 2))

    def test_when_every_page_is_full_the_read_says_it_stopped_early(self):
        fake = issue_pages(h.FakeGitHub(), *range(1, 351))
        found, failures = self.run_fetch(fake)
        self.assertEqual(len(found), 300)
        self.assertEqual(len(self.pages_asked(fake)), oi.MAX_ISSUE_PAGES)
        self.assertEqual([source for source, _ in failures], ["issues_cap"])
        self.assertIn("300건", failures[0][1])
        self.assertIn("워치독", failures[0][1])

    def test_pull_requests_count_toward_the_page_size_but_are_not_returned(self):
        fake = h.FakeGitHub()
        for number in range(1, 101):                                  # 한 쪽 100건 중 60건이 PR — 쪽이 가득 찼으니 다음 쪽도 읽어야 한다
            fake.issues.append(h.make_issue(number, f"항목 {number}", pull=number <= 60))
        fake.issues.append(h.make_watchdog(500))
        found, failures = self.run_fetch(fake)
        self.assertEqual(failures, [])
        self.assertEqual(len(self.pages_asked(fake)), 2)
        self.assertEqual(sorted(i["number"] for i in found), list(range(61, 101)) + [500])

    def test_a_failure_on_a_later_page_keeps_what_was_already_read(self):
        fake = issue_pages(h.FakeGitHub(), *range(1, 160))
        fake.fail.append((r"GET /issues\?.*page=2", oi.ApiError("HTTP 502", status=502)))
        found, failures = self.run_fetch(fake)
        self.assertEqual(len(found), 100)
        self.assertEqual(failures, [("issues", "HTTP 502")])

    def test_the_call_budget_running_out_mid_read_is_a_failure_not_silence(self):
        fake = issue_pages(h.FakeGitHub(max_calls=1), *range(1, 160))
        found, failures = self.run_fetch(fake)
        self.assertEqual(len(found), 100)
        self.assertEqual([source for source, _ in failures], ["issues"])

    def test_a_first_page_failure_is_the_same_failure_as_before(self):
        fake = issue_pages(h.FakeGitHub(), 1)
        fake.fail.append((r"GET /issues\?", oi.ApiError("HTTP 500", status=500)))
        self.assertEqual(self.run_fetch(fake), ([], [("issues", "HTTP 500")]))

    def test_an_answer_that_is_not_a_list_is_a_failure_not_an_empty_list(self):
        class Odd:
            def get(self, path, **params):
                return {"message": "Not Found"}
        self.assertEqual(self.run_fetch(Odd()), ([], [("issues", "응답이 목록이 아닙니다")]))

    def test_a_later_page_that_is_not_a_list_is_a_failure_and_the_first_page_is_kept(self):
        class OddSecondPage:
            def __init__(self):
                self.calls = 0

            def get(self, path, **params):
                self.calls += 1
                if self.calls == 1:
                    return [h.make_issue(n, f"일반 이슈 {n}", labels=("bug",)) for n in range(1, 101)]
                return {"message": "Server Error"}
        client = OddSecondPage()
        found, failures = self.run_fetch(client)
        self.assertEqual((len(found), failures, client.calls), (100, [("issues", "응답이 목록이 아닙니다")], 2))      # 둘째 쪽의 이상한 답을 '끝' 으로 삼켜 정상으로 쓰지 않는다

    def test_the_cap_warning_reaches_the_inbox_as_a_check_item_and_keeps_watchdog_ids_in_the_marker(self):
        items = inbox.failure_items([("issues_cap", "열린 이슈·PR 이 300건을 넘을 수 있어 처음 300건만 읽었습니다")], h.REPO_URL)
        self.assertEqual([(i.id, i.level) for i in items], [("source:issues_cap", "check")])
        self.assertIn("일부만 읽음", items[0].title)
        kept = inbox.plan_notice([], ("watchdog:2", "pr:1:x"), [("issues_cap", "x")])[1]
        self.assertEqual(kept, ["watchdog:2"])                         # 뒤쪽에 밀려 안 보인 워치독 알림을 '해소됨'으로 오해했다가 다시 알리지 않는다

    def test_a_full_run_with_more_than_the_cap_shows_the_warning_in_the_inbox_body(self):
        import tempfile
        fake = issue_pages(h.FakeGitHub(), *range(1, 401))
        env = {"GITHUB_REPOSITORY": h.REPO, "GITHUB_REPOSITORY_OWNER": "octo"}      # 토큰 없음 = 읽기 전용 점검(이슈를 쓰지 않는다)
        lines = []
        with tempfile.TemporaryDirectory() as tmp:
            root = h.make_root(tmp)
            code = oi.run(env, fake, h.NOW, root, lines.append, sleep=lambda seconds: None)
        text = "\n".join(lines)
        self.assertEqual(code, 0)
        self.assertIn("조회 실패 — 열린 이슈 목록(일부만 읽음)", text)
        self.assertIn("처음 300건만 읽었습니다", text)

    def test_a_full_run_below_the_cap_shows_no_issue_list_warning(self):
        import tempfile
        fake = issue_pages(h.FakeGitHub(), *range(1, 121))
        fake.issues.append(h.make_watchdog(900))
        env = {"GITHUB_REPOSITORY": h.REPO, "GITHUB_REPOSITORY_OWNER": "octo"}
        lines = []
        with tempfile.TemporaryDirectory() as tmp:
            root = h.make_root(tmp)
            oi.run(env, fake, h.NOW, root, lines.append, sleep=lambda seconds: None)
        text = "\n".join(lines)
        self.assertNotIn("일부만 읽음", text)
        self.assertIn("워치독 알림", text)                              # 101번째 뒤의 워치독 알림이 이제 모음에 보인다


class FakeHttpResponse:
    def __init__(self, body):
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class PagedOpener:
    """GET 주소의 page 값에 맞는 쪽을 돌려주는 가짜 urlopen: items 를 per_page 건씩 자른다. 요청 주소를 기록한다."""

    def __init__(self, items):
        self.items, self.urls = items, []

    def __call__(self, request, timeout=None):
        self.urls.append(request.full_url)
        query = dict(part.split("=", 1) for part in request.full_url.split("?", 1)[1].split("&"))
        per_page, page = int(query["per_page"]), int(query["page"])
        return FakeHttpResponse(self.items[(page - 1) * per_page:page * per_page])


def labeled_issue(number, pull=False):
    issue = {"number": number, "title": f"[Watchdog] chance: CODE{number}", "labels": [{"name": "watchdog"}]}
    if pull:
        issue["pull_request"] = {}
    return issue


def draft_pull(number, ref="ai/draft/chance-x", repo="o/r"):
    return {"number": number, "created_at": "2026-11-20T00:00:00Z", "head": {"ref": ref, "repo": {"full_name": repo}}}


class WatchdogPagingTest(unittest.TestCase):
    """워치독 GitHubClient(D-361): 열린 [Watchdog] 이슈(예전 50건)와 열린 PR(예전 100건)도 끝까지 읽고, 상한에 닿으면 ::warning:: 을 남긴다."""

    def client(self, items):
        opener, lines = PagedOpener(items), []
        return watchdog.GitHubClient("t", "o/r", opener=opener, out=lines.append), opener, lines

    def test_issues_beyond_the_old_fifty_are_read_in_hundreds(self):
        client, opener, lines = self.client([labeled_issue(n) for n in range(1, 131)])
        found = client.list_open_issues()
        self.assertEqual([i["number"] for i in found], list(range(1, 131)))
        self.assertEqual(lines, [])
        self.assertEqual(len(opener.urls), 2)
        self.assertTrue(all("labels=watchdog&state=open&per_page=100&page=" in url for url in opener.urls))

    def test_exactly_one_hundred_is_two_calls_and_no_warning(self):
        client, opener, lines = self.client([labeled_issue(n) for n in range(1, 101)])
        self.assertEqual(len(client.list_open_issues()), 100)
        self.assertEqual((len(opener.urls), lines), (2, []))

    def test_pull_requests_in_the_issue_listing_are_dropped(self):
        client, _, _ = self.client([labeled_issue(1), labeled_issue(2, pull=True), labeled_issue(3)])
        self.assertEqual([i["number"] for i in client.list_open_issues()], [1, 3])

    def test_a_full_set_of_pages_is_never_cut_silently(self):
        client, opener, lines = self.client([labeled_issue(n) for n in range(1, 601)])
        found = client.list_open_issues()
        self.assertEqual((len(found), len(opener.urls)), (watchdog.MAX_PAGES * watchdog.PAGE_SIZE, watchdog.MAX_PAGES))
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("::warning::"))
        self.assertIn("500건", lines[0])
        self.assertIn("[Watchdog] 이슈", lines[0])
        self.assertNotIn("\n", lines[0])

    def test_open_pull_requests_beyond_the_first_hundred_are_found(self):
        items = [draft_pull(n, ref="feature/x") for n in range(1, 151)] + [draft_pull(777)]
        client, opener, lines = self.client(items)
        self.assertEqual(client.list_open_draft_pulls(), [{"number": 777, "created_at": "2026-11-20T00:00:00Z"}])     # 151번째 — 예전에는 잘렸다
        self.assertEqual((len(opener.urls), lines), (2, []))

    def test_the_pull_request_read_warns_when_the_pages_never_end(self):
        client, _, lines = self.client([draft_pull(n) for n in range(1, 601)])
        self.assertEqual(len(client.list_open_draft_pulls()), 500)
        self.assertEqual(len(lines), 1)
        self.assertIn("PR 목록", lines[0])

    def test_an_error_on_a_later_page_is_raised_not_turned_into_a_partial_list(self):
        class BreaksOnTheSecondPage(PagedOpener):
            def __call__(self, request, timeout=None):
                if "page=2" in request.full_url:
                    self.urls.append(request.full_url)
                    raise http_error(502, "Bad Gateway")
                return super().__call__(request, timeout)
        for read in (lambda c: c.list_open_issues(), lambda c: c.list_open_draft_pulls()):
            with self.subTest(read=read):
                opener, lines = BreaksOnTheSecondPage([labeled_issue(n) for n in range(1, 131)]), []
                client = watchdog.GitHubClient("t", "o/r", opener=opener, out=lines.append)
                with self.assertRaises(urllib.error.HTTPError):
                    read(client)                                      # 앞 100건만 쥔 채 '이상 없음' 이 되면 같은 이슈를 또 만든다 — 오류는 올려 실행을 빨갛게 한다
                self.assertEqual((len(opener.urls), lines), (2, []))

    def test_the_default_output_is_print(self):
        client = watchdog.GitHubClient("t", "o/r", opener=PagedOpener([labeled_issue(n) for n in range(1, 601)]))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            client.list_open_issues()
        self.assertIn("::warning::", buf.getvalue())


class TelegramRetryTest(unittest.TestCase):
    """텔레그램 전송의 일시 오류 재시도(D-362). 확실히 안 간 실패(연결 단계)와 429 는 한 통에 최대 3번(2·4·8초), 받았을 수 있는 실패(응답이 끊김·5xx)는 1번. 통마다 첫 재시도는 한 실행 상한과 별개로 보장하고,
    추가 재시도(2·3번째)만 한 실행 상한을 나눠 쓰며(상한은 통 수에 맞춰 최악 시간을 270초 안에 둔다), 영구 오류는 다시 보내지 않고, 보낸 통은 다시 보내지 않으며, 비밀은 어디에도 없다."""

    # 확실히 안 간 실패: 시험마다 새 오류 객체를 만든다(오류 응답의 본문은 한 번만 읽히므로)
    SURE = {
        "429": lambda: http_error(429, "Too Many Requests", retry_after=1),
        "연결 단계 URLError": lambda: urllib.error.URLError("x"),
        "연결 단계 시간 초과": lambda: urllib.error.URLError(socket.timeout("x")),
        "연결 거부": lambda: urllib.error.URLError(ConnectionRefusedError("x")),
    }
    # 텔레그램이 받았을 수 있는 실패: 요청을 다 보낸 뒤 응답이 끊김, 그리고 5xx 응답(게이트웨이는 처리한 뒤에도 5xx 를 준다)
    UNSURE = {
        "500": lambda: http_error(500, "Internal Server Error"),
        "502": lambda: http_error(502, "Bad Gateway"),
        "503": lambda: http_error(503, "Service Unavailable"),
        "504": lambda: http_error(504, "Gateway Time-out"),
        "응답 대기 시간 초과": lambda: socket.timeout("x"),
        "TimeoutError": lambda: TimeoutError("x"),
        "ConnectionResetError": lambda: ConnectionResetError("x"),
        "RemoteDisconnected": lambda: http.client.RemoteDisconnected("x"),
        "IncompleteRead": lambda: http.client.IncompleteRead(b"x"),
    }

    @staticmethod
    def texts(net):
        return [body["text"] for body in net.bodies()]

    @staticmethod
    def failing_run(make, messages, retries, then_ok=False):
        """make() 가 만든 오류로 계속 실패하는 가짜 망에서 messages 통을 보낸다(한 실행 추가 재시도 상한 retries). then_ok 면 통마다 한 번 실패한 뒤 성공한다."""
        budget = notify.Budget(retries=retries)
        outcomes = []
        for _ in range(messages):
            outcomes += [make(), ok_reply()] if then_ok else [make() for _ in range(6)]
        notifier, net, clock = make_notifier(net=FakeNet(*outcomes), budget=budget)
        results = [notifier.send_message(f"통 {index}") for index in range(messages)]
        return net, budget, results, clock

    @staticmethod
    def slow(clock, seconds, make):
        """요청 하나가 seconds 초 걸린 뒤 make() 의 오류로 실패하는 가짜 응답(가짜 시계를 앞으로 보낸다)."""
        def outcome():
            clock.advance(seconds)
            raise make()
        return outcome

    def worst_run(self, limit, seconds, make, retries=None, messages=None):
        """한도 limit 통의 기본 Budget 으로 messages 통을 보내는 동안, 요청마다 seconds 초가 걸리고 끝까지 실패하는 가장 나쁜 망의 걸린 시간(가짜 시계)과 요청 수."""
        clock = Clock()
        budget = notify.Budget(limit=limit, retries=retries)
        notifier, net, clock = make_notifier(net=FakeNet(self.slow(clock, seconds, make)), clock=clock, budget=budget)
        started = clock.now
        for index in range(limit if messages is None else messages):
            notifier.send_message(f"통 {index}")
        return clock.now - started, net.calls

    def test_the_constants_agree_with_each_other(self):
        self.assertEqual(notify.TRANSIENT_RETRIES, 3)
        self.assertEqual(len(notify.RETRY_BACKOFF), notify.TRANSIENT_RETRIES)
        self.assertEqual(notify.RETRY_BACKOFF[0], notify.NETWORK_RETRY_WAIT)
        self.assertEqual(list(notify.RETRY_BACKOFF), sorted(notify.RETRY_BACKOFF))                      # 간격은 줄지 않는다
        self.assertEqual(set(notify.TRANSIENT_REASONS), {"rate_limited", "network", "timeout", "server_error"})
        self.assertEqual(notify.UNSURE_REASONS, (notify.SERVER_ERROR,))                                 # 5xx 는 받았을 수 있다 — 429 는 아니다
        self.assertNotIn(notify.RATE_LIMITED, notify.UNSURE_REASONS)
        self.assertEqual(notify.UNSURE_RETRIES, 1)
        self.assertEqual(notify.Budget().retries, notify.extra_retries_for(notify.MAX_MESSAGES))

    def test_the_extra_retry_allowance_follows_the_message_count_so_the_worst_case_always_fits(self):
        self.assertEqual({n: notify.extra_retries_for(n) for n in (1, 3, 5, 8, 9, 12)}, {1: 6, 3: 6, 5: 4, 8: 0, 9: 0, 12: 0})
        values = [notify.extra_retries_for(n) for n in range(1, 13)]
        self.assertEqual(values, sorted(values, reverse=True))                                          # 통이 많을수록 추가 재시도는 줄기만 한다
        self.assertLessEqual(max(values), notify.MAX_RETRIES_PER_RUN)
        self.assertEqual((notify.Budget().retries, notify.Budget(limit=3).retries, notify.Budget(limit=8).retries), (4, 6, 0))
        self.assertEqual(notify.Budget(limit=8, retries=2).retries, 2)                                  # 값을 직접 주면 그 값이다
        self.assertEqual(notify.Budget(retries=0).retries, 0)
        self.assertEqual(notify.Budget(limit=telegram_inbox.MAX_MESSAGES).retries, 0)                   # 텔레그램 수신은 한 실행 8통 — 5분 제한 안에 두려고 추가 재시도가 없다(예전과 같다)

    def test_a_flaky_send_is_retried_with_growing_waits_until_it_gets_through(self):
        net = FakeNet(urllib.error.URLError("x"), urllib.error.URLError("x"), http_error(502, "Bad Gateway"), ok_reply())
        notifier, net, clock = make_notifier(net=net)
        result = notifier.send_message("안녕")
        self.assertEqual((result.ok, result.sent, result.reason), (True, True, "sent"))
        self.assertEqual((net.calls, clock.sleeps), (4, [2, 4, 8]))

    def test_after_the_third_retry_it_gives_up_and_the_failure_is_in_the_result(self):
        for outcome, reason in ((urllib.error.URLError("x"), "network"), (urllib.error.URLError(socket.timeout("x")), "timeout")):
            with self.subTest(reason=reason):
                notifier, net, clock = make_notifier(net=FakeNet(outcome))
                result = notifier.send_message("안녕")
                self.assertEqual((result.ok, result.sent, result.reason, result.status), (False, False, reason, None))
                self.assertEqual((net.calls, clock.sleeps), (4, [2, 4, 8]))

    def test_a_failure_before_the_request_went_out_or_a_429_gets_all_three_retries(self):
        for label, make in self.SURE.items():
            with self.subTest(kind=label):
                net, budget, results, clock = self.failing_run(make, messages=1, retries=4)
                self.assertFalse(results[0].sent)
                self.assertEqual(net.calls, 4)                                                           # 처음 1 + 재시도 3
                self.assertEqual(budget.retries_left, 4 - 2)                                             # 첫 재시도는 상한 밖 — 추가 재시도 둘만 상한을 쓴다

    def test_a_failure_the_telegram_may_have_processed_is_resent_at_most_once_so_a_delivered_message_is_not_multiplied(self):
        """응답을 기다리다·읽다 끊긴 실패와 5xx 응답은 텔레그램이 이미 받았을 수 있다 — 같은 통이 여러 번 가지 않게 예전처럼 한 번만 다시 보낸다."""
        for label, make in self.UNSURE.items():
            with self.subTest(kind=label):
                notifier, net, clock = make_notifier(net=FakeNet(*[make() for _ in range(6)]))
                result = notifier.send_message("안녕")
                self.assertEqual((result.sent, net.calls, clock.sleeps), (False, 2, [2]))
                self.assertIn(result.reason, ("timeout", "network", "server_error"))
        self.assertEqual(notify.UNSURE_RETRIES, 1)

    def test_a_5xx_answer_is_resent_once_not_three_times_and_a_429_is_not_a_5xx(self):
        for status in (500, 501, 502, 503, 504, 599):
            with self.subTest(status=status):
                notifier, net, clock = make_notifier(net=FakeNet(http_error(status, "x"), http_error(status, "x"), ok_reply()))
                result = notifier.send_message("안녕")
                self.assertEqual((result.sent, result.reason, result.status, net.calls, clock.sleeps), (False, "server_error", status, 2, [2]))     # 두 번 모두 5xx 면 거기서 멈춘다(성공이 기다려도)
        notifier, net, clock = make_notifier(net=FakeNet(http_error(502, "x"), ok_reply()))
        self.assertTrue(notifier.send_message("안녕").sent)                                              # 한 번 5xx 뒤의 성공은 보낸다(예전과 같다)
        self.assertEqual((net.calls, clock.sleeps), (2, [2]))
        notifier, net, clock = make_notifier(net=FakeNet(*[http_error(429, "x", retry_after=1) for _ in range(3)], ok_reply()))
        self.assertTrue(notifier.send_message("안녕").sent)                                              # 429 는 처리하지 않았다는 뜻이라 세 번까지 다시 보낸다
        self.assertEqual(net.calls, 4)

    def test_a_response_that_cannot_be_read_back_is_also_resent_at_most_once(self):
        class Unreadable:
            headers = {}

            def getcode(self):
                raise OSError("boom")

            def read(self, n=-1):
                return b"{}"

            def close(self):
                pass
        notifier, net, clock = make_notifier(net=FakeNet(Unreadable()))
        result = notifier.send_message("안녕")
        self.assertEqual((result.sent, result.reason, net.calls, clock.sleeps), (False, "network", 2, [2]))

    def test_one_unsure_failure_among_sure_ones_does_not_block_the_others_but_a_second_one_stops_the_resending(self):
        for unsure in (socket.timeout("x"), http_error(502, "x")):
            with self.subTest(unsure=type(unsure).__name__):
                net = FakeNet(urllib.error.URLError("x"), unsure, urllib.error.URLError("x"), ok_reply())
                notifier, net, clock = make_notifier(net=net)
                self.assertTrue(notifier.send_message("안녕").sent)
                self.assertEqual((net.calls, clock.sleeps), (4, [2, 4, 8]))
        for make in (lambda: socket.timeout("x"), lambda: http_error(503, "x")):
            net = FakeNet(make(), make(), ok_reply())
            notifier, net, clock = make_notifier(net=net)
            result = notifier.send_message("안녕")
            self.assertEqual((result.sent, net.calls), (False, 2))                                       # 두 번째 '받았을 수 있는 실패' 뒤에는 보내지 않는다(성공이 기다리고 있어도)

    def test_every_429_waits_what_telegram_asked_up_to_ten_seconds(self):
        net = FakeNet(http_error(429, retry_after=3), http_error(429, retry_after=5), http_error(429, retry_after=300), ok_reply())
        notifier, net, clock = make_notifier(net=net)
        self.assertTrue(notifier.send_message("안녕").sent)
        self.assertEqual(clock.sleeps, [3, 5, 10])

    def test_the_network_wait_starts_at_two_seconds_even_after_a_429(self):
        net = FakeNet(http_error(429, retry_after=1), urllib.error.URLError("x"), http_error(502, "Bad Gateway"), ok_reply())
        notifier, net, clock = make_notifier(net=net)
        self.assertTrue(notifier.send_message("안녕").sent)
        self.assertEqual((net.calls, clock.sleeps), (4, [1, 2, 4]))

    def test_permanent_errors_are_not_retried_and_the_failure_is_logged_without_secrets(self):
        for status, description in ((400, "Bad Request: chat not found"), (400, "Bad Request: message is too long"), (401, "Unauthorized"),
                                    (403, "Forbidden: bot was blocked by the user"), (404, "Not Found"), (409, "Conflict"), (413, "Payload Too Large")):
            with self.subTest(status=status, description=description):
                notifier, net, clock = make_notifier(net=FakeNet(http_error(status, description + " " + TOKEN), ok_reply()))
                result = notifier.send_message("안녕")
                self.assertEqual((result.ok, result.sent, result.status, net.calls, clock.sleeps), (False, False, status, 1, []))
                lines = []
                notify.log_result(result, lines.append)
                self.assertEqual(len(lines), 2)
                self.assertIn("보내지 못했습니다", lines[0])
                self.assertEqual(lines[1], notify.WARNING_LINE)
                self.assertEqual(leaks(repr(result), notify.describe(result), *lines), [])

    def test_a_message_that_was_sent_is_never_sent_again_even_when_a_later_one_is_retried(self):
        net = FakeNet(ok_reply(), urllib.error.URLError("x"), ok_reply(), ok_reply())
        notifier, net, clock = make_notifier(net=net)
        results = [notifier.send_message(text) for text in ("A", "B", "C")]
        self.assertEqual([r.sent for r in results], [True, True, True])
        self.assertEqual(self.texts(net), ["A", "B", "B", "C"])                    # A·C 는 한 번, B 는 실패한 시도 한 번 + 성공 한 번(받은 것은 한 번)

    def test_a_message_that_failed_for_good_does_not_resend_the_ones_before_or_after_it(self):
        net = FakeNet(ok_reply(), http_error(401, "Unauthorized"), ok_reply())
        notifier, net, clock = make_notifier(net=net)
        results = [notifier.send_message(text) for text in ("A", "B", "C")]
        self.assertEqual([r.sent for r in results], [True, False, True])
        self.assertEqual(self.texts(net), ["A", "B", "C"])
        self.assertEqual([s for s in clock.sleeps if s != 1.1 and round(s, 3) != 1.1], [])      # 재시도 대기는 없다(통 사이 간격 1.1초만)

    def test_the_extra_retries_of_every_sure_kind_spend_the_run_wide_allowance(self):
        """한 실행의 추가 재시도 상한(실행 시간 폭증을 막는 안전 장치)이 확실히 안 간 실패의 모든 종류에서 지켜진다 — 429·연결 단계 실패마다 한 통이 상한을 쓰고, 다 쓰면 뒤 통은 첫 재시도만 한다."""
        for label, make in self.SURE.items():
            with self.subTest(kind=label):
                net, budget, results, clock = self.failing_run(make, messages=3, retries=2)
                self.assertEqual([r.sent for r in results], [False, False, False])
                self.assertEqual(budget.retries_left, 0)
                self.assertEqual(net.calls, (1 + 1 + 2) + (1 + 1) + (1 + 1))                              # 첫 통은 추가 재시도 둘까지, 나머지 통은 처음 + 보장되는 첫 재시도

    def test_the_kinds_the_telegram_may_have_processed_never_spend_the_allowance(self):
        for label, make in self.UNSURE.items():
            with self.subTest(kind=label):
                net, budget, results, clock = self.failing_run(make, messages=3, retries=5)
                self.assertEqual(budget.retries_left, 5)                                                 # 첫 재시도는 상한 밖이고 추가 재시도는 이 종류에 없다
                self.assertEqual(net.calls, 3 * 2)

    def test_a_retry_after_the_first_spends_the_allowance_whatever_its_kind(self):
        """확실히 안 간 실패 뒤에 받았을 수 있는 실패가 오면 그 재시도는 통의 둘째 재시도라 한 실행 상한을 쓴다 — 상한이 받았을 수 있는 실패의 종류에서도 지켜진다
        (독립 검증 변이 QM-20·QM-21 의 새 코드 대응: 이 종류는 혼자서는 둘째 재시도에 닿지 못하므로 확실히 안 간 실패와 섞어서 본다)."""
        for label, make in self.UNSURE.items():
            with self.subTest(kind=label):
                budget = notify.Budget(retries=1)
                outcomes = [urllib.error.URLError("x"), make(), ok_reply(), urllib.error.URLError("x"), make(), ok_reply()]
                notifier, net, clock = make_notifier(net=FakeNet(*outcomes), budget=budget)
                self.assertTrue(notifier.send_message("통 1").sent)
                self.assertEqual((net.calls, budget.retries_left), (3, 0))                              # 첫 재시도는 상한 밖, 받았을 수 있는 실패 뒤의 둘째 재시도가 상한 하나를 썼다
                self.assertFalse(notifier.send_message("통 2").sent)                                    # 상한이 없으니 둘째 재시도는 없다 — 처음 + 보장되는 첫 재시도에서 끝난다
                self.assertEqual(net.calls, 3 + 2)

    def test_a_format_or_button_error_is_swapped_at_once_never_waited_for_and_repeated(self):
        """서식 해석 실패(400)와 버튼 거부(400)는 일시 오류가 아니다 — 기다렸다 같은 요청을 다시 보내지 않고 바로 서식·버튼을 뺀 요청으로 바꿔 보낸다."""
        net = FakeNet(http_error(400, "Bad Request: can't parse entities: x"), http_error(400, "Bad Request: BUTTON_URL_INVALID"), ok_reply())
        notifier, net, clock = make_notifier(net=net)
        self.assertTrue(notifier.send_message("<b>x</b>", parse_mode="HTML", buttons=[("열기", BUTTON_URL)]).sent)
        self.assertEqual((net.calls, clock.sleeps), (3, []))
        first, second, third = net.bodies()
        self.assertEqual((first.get("parse_mode"), "reply_markup" in first), ("HTML", True))
        self.assertEqual(("parse_mode" in second, "reply_markup" in second), (False, True))             # 서식만 뺐다
        self.assertEqual(("parse_mode" in third, "reply_markup" in third), (False, False))              # 버튼도 뺐다

    def test_every_message_keeps_its_guaranteed_first_retry_even_when_the_allowance_is_gone(self):
        """앞 통이 한 실행 재시도를 다 써도 뒤 통은 예전처럼 첫 재시도를 잃지 않는다(통마다 한 번)."""
        for label, make in {**self.SURE, **self.UNSURE}.items():
            with self.subTest(kind=label):
                net, budget, results, clock = self.failing_run(make, messages=3, retries=0, then_ok=True)
                self.assertEqual([r.sent for r in results], [True, True, True])                          # 통마다 한 번 실패한 뒤 첫 재시도로 보낸다
                self.assertEqual(net.calls, 6)
                net, budget, results, clock = self.failing_run(make, messages=3, retries=0)
                self.assertEqual([r.sent for r in results], [False, False, False])
                self.assertEqual(net.calls, 6)                                                           # 상한이 0 이어도 통마다 첫 재시도는 하고 추가 재시도는 없다

    def test_the_guaranteed_first_retry_does_not_touch_the_allowance(self):
        for label, make in {**self.SURE, **self.UNSURE}.items():
            with self.subTest(kind=label):
                net, budget, results, clock = self.failing_run(make, messages=3, retries=4, then_ok=True)
                self.assertEqual((net.calls, budget.retries_left), (6, 4))

    def test_the_whole_run_shares_one_allowance_and_later_messages_still_get_their_first_retry(self):
        notifier, net, clock = make_notifier(net=FakeNet(urllib.error.URLError("x")))
        results = [notifier.send_message(f"통 {i}") for i in range(6)]
        self.assertEqual([r.reason for r in results], ["network"] * 5 + ["limit"])
        self.assertEqual(net.calls, 4 + 4 + 2 + 2 + 2)                              # 기본 5통의 추가 재시도 상한 4번을 앞의 두 통이 쓰고, 나머지 통은 처음 + 첫 재시도
        self.assertEqual(sum(s for s in clock.sleeps if s >= 2), (2 + 4 + 8) * 2 + 2 * 3)
        self.assertEqual(notifier.budget.retries_left, 0)

    def test_the_allowance_can_be_set_and_is_restored_by_reset(self):
        budget = notify.Budget(retries=1)
        notifier, net, clock = make_notifier(net=FakeNet(urllib.error.URLError("x")), budget=budget)
        notifier.send_message("안녕")
        self.assertEqual((net.calls, budget.retries_left), (3, 0))                  # 처음 + 보장되는 첫 재시도 + 추가 재시도 한 번
        budget.reset()
        self.assertEqual((budget.retries_left, budget.used), (1, 0))
        none = notify.Budget(retries=0)
        notifier, net, _ = make_notifier(net=FakeNet(urllib.error.URLError("x")), budget=none)
        self.assertFalse(notifier.send_message("안녕").sent)
        self.assertEqual(net.calls, 2)                                              # 상한 0 이어도 통마다 첫 재시도 한 번은 예전처럼 한다

    def test_the_worst_case_for_one_message_is_six_requests(self):
        net = FakeNet(http_error(429, retry_after=1), urllib.error.URLError("x"), http_error(502, "Bad Gateway"),
                      http_error(400, "Bad Request: can't parse entities: x"), http_error(400, "Bad Request: BUTTON_URL_INVALID"), http_error(400, "Bad Request: nope"), ok_reply())
        notifier, net, _ = make_notifier(net=net)
        result = notifier.send_message("<b>x</b>", parse_mode="HTML", buttons=[("열기", BUTTON_URL)])
        self.assertEqual((result.sent, result.reason, net.calls), (False, "bad_request", 6))

    def test_the_format_and_button_fallbacks_do_not_use_up_the_retry_allowance(self):
        net = FakeNet(http_error(400, "Bad Request: can't parse entities: x"), http_error(400, "Bad Request: BUTTON_URL_INVALID"), ok_reply())
        budget = notify.Budget()
        notifier, net, _ = make_notifier(net=net, budget=budget)
        self.assertTrue(notifier.send_message("<b>x</b>", parse_mode="HTML", buttons=[("열기", BUTTON_URL)]).sent)
        self.assertEqual(budget.retries_left, budget.retries)

    def test_a_blocked_telegram_never_keeps_a_run_past_the_time_budget(self):
        """텔레그램이 통째로 막혀 모든 요청이 제한 시간까지 가도(가짜 시계로 끝까지 실패시킴) 어느 통 수의 실행도 RUN_TIME_BUDGET 안에 끝난다 — 5분 워크플로 제한 안의 안전망."""
        kinds = {
            "연결 단계 시간 초과": (15, lambda: urllib.error.URLError(socket.timeout("x"))),
            "응답 대기 시간 초과": (15, lambda: socket.timeout("x")),
            "연결 끊김": (15, lambda: ConnectionResetError("x")),
            "느린 504": (10, lambda: http_error(504, "Gateway Time-out")),
            "429(바로 답하고 10초를 기다리라고 함)": (1, lambda: http_error(429, "Too Many Requests", retry_after=10)),      # 429 는 텔레그램이 바로 답하는 한도 응답이다 — 요청 시간을 제한 시간으로 세지 않는다
        }
        for label, (seconds, make) in kinds.items():
            for limit in (1, 3, 5, 8):
                with self.subTest(kind=label, limit=limit):
                    elapsed, calls = self.worst_run(limit, seconds, make)
                    self.assertLessEqual(elapsed, notify.RUN_TIME_BUDGET)

    def test_the_time_budget_check_can_fail_so_it_would_notice_a_missing_cap(self):
        """같은 가짜 망에서 추가 재시도 상한을 없애면(retries 99) 5통 실행이 예산을 넘는다 — 위 시험이 헛돌지 않는다는 확인."""
        elapsed, calls = self.worst_run(5, 15, lambda: urllib.error.URLError(socket.timeout("x")), retries=99)
        self.assertGreater(elapsed, notify.RUN_TIME_BUDGET)
        elapsed, calls = self.worst_run(8, 15, lambda: urllib.error.URLError(socket.timeout("x")), retries=notify.MAX_RETRIES_PER_RUN)
        self.assertGreater(elapsed, notify.RUN_TIME_BUDGET)

    def test_a_single_message_stays_inside_the_two_minute_step_limit(self):
        """새 글·검사 실패 알림 단계의 제한은 2분 — 한 통만 보내는 실행의 최악도 그 안이다."""
        for seconds, make in ((15, lambda: urllib.error.URLError(socket.timeout("x"))), (15, lambda: socket.timeout("x")), (10, lambda: http_error(504, "x"))):
            elapsed, calls = self.worst_run(notify.MAX_MESSAGES, seconds, make, messages=1)
            self.assertLessEqual(elapsed, 100)
            self.assertLessEqual(calls, 4)

    def test_the_real_consumers_stay_inside_the_time_budget(self):
        consumers = {"기본 한도(확인 모음·AI 요청 알림 …)": notify.MAX_MESSAGES, "텔레그램 수신": telegram_inbox.MAX_MESSAGES}
        for label, limit in consumers.items():
            with self.subTest(consumer=label):
                elapsed, calls = self.worst_run(limit, notify.TIMEOUT_SECONDS, lambda: urllib.error.URLError(socket.timeout("x")))
                self.assertLessEqual(elapsed, notify.RUN_TIME_BUDGET)

    def test_the_telegram_receiver_gives_its_notifier_a_budget_made_for_its_own_message_count(self):
        """텔레그램 수신은 한 번에 8통까지 보낸다 — 기본 한도(5통)용 추가 재시도 상한을 그대로 쓰면 최악 시간이 예산을 넘는다. 그 프로세스가 자기 통 수로 만든 한도를 쓰는지 본다."""
        seen = []

        def spy(environ, **kwargs):
            seen.append(kwargs["budget"])
            raise RuntimeError("여기서 멈춘다")
        with mock.patch.object(notify, "Notifier", spy):
            with self.assertRaises(RuntimeError):
                telegram_inbox.run_inbox({notify.ENV_TOKEN: TOKEN, notify.ENV_CHAT: CHAT}, lambda text: None)
        (budget,) = seen
        self.assertEqual((budget.limit, budget.retries), (telegram_inbox.MAX_MESSAGES, notify.extra_retries_for(telegram_inbox.MAX_MESSAGES)))
        self.assertEqual(budget.retries, 0)

    def test_no_secret_leaks_through_any_retry_attempt(self):
        shapes = (http_error(502, f"Bad Gateway {TOKEN} {CHAT}"), http_error(429, f"Too Many Requests {TOKEN}", retry_after=1),
                  urllib.error.URLError(f"https://api.telegram.org/bot{TOKEN}/sendMessage 연결 실패"), ConnectionResetError(f"bot{TOKEN}"), socket.timeout(TOKEN))
        for shape in shapes:
            with self.subTest(shape=type(shape).__name__):
                notifier, net, clock = make_notifier(net=FakeNet(shape))
                result = notifier.send_message("안녕")
                lines = []
                notify.log_result(result, lines.append)
                self.assertEqual(leaks(repr(result), str(result), notify.describe(result), result.detail, *lines), [])
                maybe_processed = isinstance(shape, (ConnectionResetError, socket.timeout)) or (isinstance(shape, urllib.error.HTTPError) and shape.code >= 500)
                self.assertEqual(net.calls, 2 if maybe_processed else 4)       # 받았을 수 있는 실패(응답이 끊김·5xx)는 한 번만 다시 보낸다

    def test_the_first_try_succeeds_without_any_wait_or_retry(self):
        notifier, net, clock = make_notifier()
        self.assertTrue(notifier.send_message("안녕").sent)
        self.assertEqual((net.calls, clock.sleeps, notifier.budget.retries_left), (1, [], notifier.budget.retries))


class AlertCallbackRetryTest(unittest.TestCase):
    """확인 필요 모음의 휴대폰 알림 콜백(make_alert)이 일시 오류에도 알림을 잃지 않고, 초안 대기 알림과 일반 알림을 서로 다시 보내지 않는다."""

    def test_a_blip_on_the_general_message_does_not_resend_the_waiting_message(self):
        out = []
        drafts = [inbox.normalize_draft(h.make_draft_raw(15, "[초안][Chance] 새 글", channel="Chance", pull=True))]
        alert = oi.make_alert(ENV, out.append, drafts, h.REPO_URL)
        new_items = [inbox.Item("draft:15:wait", "action", "초안 대기 PR #15", url=f"{h.REPO_URL}/pull/15"), inbox.Item("pr:9:ready", "action", "PR #9 병합하면 됩니다")]
        net = FakeNet(ok_reply(), urllib.error.URLError("x"), http_error(502, "Bad Gateway"), ok_reply())
        notify.reset_budget()
        try:
            with mock.patch("urllib.request.urlopen", net), mock.patch("time.sleep", lambda seconds: None):
                alert(new_items, f"{h.REPO_URL}/issues/22")
        finally:
            notify.reset_budget()
        bodies = [json.loads(request.data.decode("utf-8")) for request in net.requests]
        self.assertEqual(len(bodies), 4)
        self.assertEqual(sum("발행 대기" in body["text"] for body in bodies), 1)          # 초안 대기 알림은 한 번만
        self.assertEqual(sum("PR #9" in body["text"] for body in bodies), 3)             # 일반 알림만 실패 2번 + 성공 1번
        self.assertTrue(any("[참고] 텔레그램 알림: 보냈습니다" in line for line in out))
        self.assertFalse(any("::warning::" in line for line in out))


def prov(provider_id="noaa_swpc_json", expires="2027-02-08", enabled=True, name="NOAA SWPC JSON"):
    """허용 목록 파일의 Provider 한 항목(시험에 필요한 칸만)."""
    return {"provider_id": provider_id, "name": name, "enabled": enabled, "snapshot": {"terms_pages": ["문서"], "expires_at": expires}}


class TermsDeadlineRuleTest(unittest.TestCase):
    """pipeline/terms_deadline.py(순수): 남은 날 수·경계·켜진 제공처만·입력 순서와 무관한 결과. 오늘은 모두 값으로 넣는다(실제 시계 없음)."""

    def test_the_date_shape_is_the_registry_shape_on_every_python(self):
        for good in ("2027-02-08", datetime.date(2027, 2, 8), datetime.datetime(2027, 2, 8, 23, 59)):
            self.assertEqual(terms_deadline.parse_day(good), datetime.date(2027, 2, 8))
        for bad in ("20270208", "2027-2-8", "2027-02-30", "2027-02-08T00:00", " 2027-02-08", "", None, 20270208, ["2027-02-08"]):
            self.assertIsNone(terms_deadline.parse_day(bad), repr(bad))

    def test_days_left_counts_the_last_valid_day_as_zero(self):
        self.assertEqual([terms_deadline.days_left("2027-02-08", day) for day in ("2027-01-25", "2027-02-07", "2027-02-08", "2027-02-09", "2027-03-01")], [14, 1, 0, -1, -21])
        self.assertEqual(terms_deadline.days_left("2027-02-08", datetime.date(2027, 2, 7)), 1)
        self.assertEqual(terms_deadline.days_left("2027-02-08", datetime.datetime(2027, 2, 8, 23, 0)), 0)
        self.assertIsNone(terms_deadline.days_left("내일", "2027-02-08"))
        self.assertIsNone(terms_deadline.days_left(None, "2027-02-08"))
        with self.assertRaises(ValueError):
            terms_deadline.days_left("2027-02-08", "어제")                 # 오늘을 읽을 수 없으면 시계로 대신하지 않고 멈춘다

    def test_the_boundaries_between_the_states(self):
        self.assertEqual(terms_deadline.WARN_DAYS, 14)
        self.assertEqual([terms_deadline.state_of(left) for left in (None, -1, 0, 1, 14, 15, 106)],
                         ["missing", "expired", "expiring", "expiring", "expiring", None, None])
        self.assertEqual([terms_deadline.state_of(left, 3) for left in (3, 4)], ["expiring", None])

    def test_only_enabled_providers_are_looked_at(self):
        providers = [prov("on_one"), prov("off_one", enabled=False), prov("text_true", enabled="true"), prov("number_one", enabled=1), prov("none_one", enabled=None)]
        self.assertEqual([n.provider_id for n in terms_deadline.notices(providers, "2027-02-01")], ["on_one"])

    def test_a_far_expiry_is_silent_and_the_window_opens_on_the_fourteenth_day(self):
        providers = [prov("p_far", "2028-01-01"), prov("p_near", "2027-02-08")]
        self.assertEqual(terms_deadline.notices(providers, "2027-01-24"), [])
        found = terms_deadline.notices(providers, "2027-01-25")
        self.assertEqual([(n.provider_id, n.days_left, n.state) for n in found], [("p_near", 14, "expiring")])

    def test_expired_and_missing_come_before_expiring_and_the_order_never_depends_on_the_input_order(self):
        providers = [prov("p_soon", "2027-02-05"), prov("p_lapsed", "2027-01-20"), prov("p_missing", None), prov("p_today", "2027-02-01"), prov("p_long", "2027-01-01")]
        expected = [("p_missing", "missing"), ("p_long", "expired"), ("p_lapsed", "expired"), ("p_today", "expiring"), ("p_soon", "expiring")]
        for ordering in (providers, list(reversed(providers)), providers[2:] + providers[:2]):
            self.assertEqual([(n.provider_id, n.state) for n in terms_deadline.notices(ordering, "2027-02-01")], expected)

    def test_a_missing_or_unreadable_expiry_of_an_enabled_provider_is_reported_without_echoing_the_file(self):
        bad_shapes = ({"snapshot": None}, {"snapshot": {}}, {"snapshot": {"expires_at": None}}, {"snapshot": {"expires_at": "내일 @누군가 <b>x</b>"}},
                      {"snapshot": {"expires_at": "20270208"}}, {"snapshot": {"expires_at": 20270208}}, {})
        for extra in bad_shapes:
            with self.subTest(extra=str(extra)[:40]):
                entry = {"provider_id": "p_bad", "enabled": True, **extra}
                found = terms_deadline.notices([entry], "2027-02-01")
                self.assertEqual([(n.provider_id, n.state, n.days_left, n.expires_at) for n in found], [("p_bad", "missing", None, "")])

    def test_malformed_entries_are_skipped_not_fatal(self):
        providers = ["글자", None, 5, ["x"], {"enabled": True}, {"provider_id": "BAD ID", "enabled": True}, {"provider_id": "a", "enabled": True},
                     {"provider_id": "x" * 70, "enabled": True}, {"provider_id": "ok_one", "enabled": True, "name": ["x"], "snapshot": {"expires_at": "2027-02-02"}}]
        found = terms_deadline.notices(providers, "2027-02-01")
        self.assertEqual([(n.provider_id, n.name) for n in found], [("ok_one", "")])
        self.assertEqual(terms_deadline.notices([], "2027-02-01"), [])
        self.assertEqual(terms_deadline.notices((prov("tuple_ok"),), "2027-02-01")[0].provider_id, "tuple_ok")
        for not_a_list in (None, {"providers": []}, "글자", 5):
            with self.assertRaises(ValueError):
                terms_deadline.notices(not_a_list, "2027-02-01")

    def test_providers_with_the_same_expiry_come_out_in_id_order_whatever_the_input_order(self):
        today = datetime.date(2027, 1, 30)
        for expires in ("2027-02-08", "2027-01-01", None):                            # 임박·지남·기한 없음 — 세 경우 모두 같은 기한끼리는 제공처 이름순이다
            first, second = prov("a_one", expires), prov("b_one", expires)
            for providers in ([first, second], [second, first]):
                with self.subTest(expires=expires, order=[p["provider_id"] for p in providers]):
                    self.assertEqual([n.provider_id for n in terms_deadline.notices(providers, today)], ["a_one", "b_one"])

    def test_the_warning_window_argument_is_honoured(self):
        today = datetime.date(2027, 1, 30)
        providers = [prov(expires="2027-02-08")]                                     # 9일 남음
        self.assertEqual([n.state for n in terms_deadline.notices(providers, today, warn_days=9)], ["expiring"])
        self.assertEqual(terms_deadline.notices(providers, today, warn_days=8), [])
        self.assertEqual(terms_deadline.state_of(9, warn_days=9), "expiring")
        self.assertIsNone(terms_deadline.state_of(9, warn_days=8))

    def test_the_provider_id_shape_matches_the_registry_rule_at_its_edges(self):
        today = datetime.date(2027, 1, 30)
        for good in ("a" + "b" * 63, "ab", "a1_b2"):
            with self.subTest(good=good):
                self.assertEqual([n.provider_id for n in terms_deadline.notices([prov(good, "2027-02-08")], today)], [good])
        for bad in ("a" + "b" * 64, "a", "Ab", "1ab", "a-b", "a b", ""):
            with self.subTest(bad=bad):
                self.assertEqual(terms_deadline.notices([prov(bad, "2027-02-08")], today), [])

    def test_the_name_is_one_short_line(self):
        found = terms_deadline.notices([prov("p_name", "2027-02-02", name="  첫 줄\n둘째 줄\t" + "길" * 200)], "2027-02-01")
        self.assertNotIn("\n", found[0].name)
        self.assertLessEqual(len(found[0].name), terms_deadline.NAME_LIMIT)

    def test_left_text_reads_in_days(self):
        def text(left):
            return terms_deadline.left_text(terms_deadline.Notice("p", "", "2027-02-08", left, "x"))
        self.assertEqual([text(left) for left in (None, 0, 3, -2)], ["기한 없음", "오늘이 마지막 날", "3일 남음", "2일 지남"])

    def test_the_rule_is_pure_it_never_reads_a_clock_a_file_or_the_network(self):
        source = (_bootstrap.ROOT / "pipeline" / "terms_deadline.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertEqual(imported, {"datetime", "re", "collections"})
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertFalse(attributes & {"now", "today", "utcnow", "time", "read_text", "open", "environ", "urlopen"}, attributes)
        self.assertNotIn("~", source)
        self.assertNotRegex(source, r"https?://")

    def test_the_committed_registry_warns_exactly_on_the_fourteenth_day_before_each_enabled_expiry(self):
        data = json.loads((_bootstrap.ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8"))
        enabled = [p for p in data["providers"] if p.get("enabled") is True]
        self.assertTrue(enabled)
        for provider in enabled:
            expiry = terms_deadline.parse_day(provider["snapshot"]["expires_at"])
            self.assertIsNotNone(expiry, provider["provider_id"])
            states = {offset: [n.state for n in terms_deadline.notices(data["providers"], expiry + datetime.timedelta(days=offset)) if n.provider_id == provider["provider_id"]]
                      for offset in (-15, -14, 0, 1)}
            self.assertEqual(states, {-15: [], -14: ["expiring"], 0: ["expiring"], 1: ["expired"]}, provider["provider_id"])


def snapshot(now, **kw):
    return inbox.Snapshot(now=now, repo=h.REPO, **kw)


def kst(year, month, day, hour=12, minute=0):
    """한국 시각(KST)을 UTC 시각으로 — 날짜 경계 시험용."""
    return datetime.datetime(year, month, day, hour, minute, tzinfo=inbox.KST).astimezone(datetime.timezone.utc)


class TermsInboxItemsTest(unittest.TestCase):
    """확인 필요 모음(pipeline/inbox.py): 약관 점검 기한이 14일 안이면 check(미리 알림), 지났거나 없으면 action. 한국 날짜 기준이고, 워치독 이슈와 한 줄만 싣는다."""

    def items(self, providers, today=datetime.date(2027, 1, 30)):
        return inbox.terms_items(providers, today, h.REPO_URL)

    def test_an_expiring_provider_is_one_check_item_that_names_the_date(self):
        (item,) = self.items([prov()])
        self.assertEqual((item.id, item.level), ("terms:noaa_swpc_json:soon", "check"))
        self.assertIn("다가옵니다", item.title)
        self.assertIn("NOAA SWPC JSON", item.title)
        self.assertIn("점검 기한 2027-02-08", item.detail)
        self.assertIn("당일까지 유효합니다", item.detail)
        self.assertNotIn("9일", item.detail)                                         # 남은 날 수는 글에 넣지 않는다(본문이 날마다 바뀌지 않게)
        self.assertEqual(item.url, f"{h.REPO_URL}/blob/main/docs/SOURCE_POLICY.md")
        self.assertIn("snapshot.expires_at", item.hint)
        self.assertIn("운영자 승인", item.hint)

    def test_the_last_valid_day_says_today_is_the_last_day(self):
        (item,) = self.items([prov()], datetime.date(2027, 2, 8))
        self.assertEqual((item.id, item.level), ("terms:noaa_swpc_json:soon", "check"))
        self.assertIn("오늘이 마지막 날입니다", item.detail)

    def test_an_expired_provider_is_an_action_item(self):
        (item,) = self.items([prov()], datetime.date(2027, 2, 9))
        self.assertEqual((item.id, item.level), ("terms:noaa_swpc_json:expired", "action"))
        self.assertIn("지났습니다", item.title)
        self.assertIn("점검 기한 2027-02-08 이 지나", item.detail)
        self.assertIn("자동 글감에서 빠져", item.detail)
        self.assertNotIn("1일", item.detail)

    def test_an_enabled_provider_without_a_readable_expiry_is_an_action_item(self):
        (item,) = self.items([prov(expires=None)])
        self.assertEqual((item.id, item.level), ("terms:noaa_swpc_json:missing", "action"))
        self.assertIn("읽을 수 없습니다", item.title)

    def test_the_text_does_not_change_from_day_to_day_within_a_state_so_the_inbox_body_is_not_rewritten_daily(self):
        """이 모듈의 원칙(시각·경과 시간을 넣지 않는다): 같은 상태의 본문은 날마다 같다. 바뀌는 때는 상태가 바뀔 때와 마지막 날뿐이다."""
        def shown(day):
            items = self.items([prov()], day)
            return [(i.id, i.level, i.title, i.detail, i.url, i.hint) for i in items], inbox.render(items, h.REPO_URL)
        start = datetime.date(2027, 1, 25)
        soon = [shown(start + datetime.timedelta(days=n)) for n in range(14)]                  # 남은 날 14 … 1
        self.assertEqual(len({text for _, text in soon}), 1)
        self.assertEqual(len({str(rows) for rows, _ in soon}), 1)
        last, after_1, after_40 = shown(datetime.date(2027, 2, 8)), shown(datetime.date(2027, 2, 9)), shown(datetime.date(2027, 3, 20))
        self.assertNotEqual(last[1], soon[0][1])                                               # 마지막 날은 따로 말한다
        self.assertEqual(after_1, after_40)                                                    # 지난 뒤 며칠이 지나도 같은 글

    def test_far_expiry_disabled_providers_and_no_data_add_nothing(self):
        self.assertEqual(self.items([prov(expires="2027-06-01")]), [])
        self.assertEqual(self.items([prov(enabled=False)]), [])
        self.assertEqual(inbox.terms_items(None, datetime.date(2027, 2, 9), h.REPO_URL), [])
        self.assertEqual(self.items([]), [])

    def test_the_provider_name_cannot_inject_markup_or_mentions(self):
        (item,) = self.items([prov(name="@누군가 <b>굵게</b> [링크](x) " + "길" * 100)])
        self.assertNotIn("@", item.title)
        self.assertNotIn("<", item.title)
        rendered = inbox.render([item], h.REPO_URL)
        self.assertNotIn("@누군가", rendered)

    def test_the_item_ids_are_valid_for_every_provider_id_shape_the_registry_allows(self):
        for provider_id in ("ab", "a" + "b" * 63, "kosis_openapi_stat_data", "datago_15084084_kma_vilage_fcst"):
            (item,) = self.items([prov(provider_id)])
            self.assertTrue(re.fullmatch(r"[a-z0-9_.:]{1,80}", item.id), item.id)

    def test_build_items_adds_nothing_without_source_terms_and_the_old_output_is_unchanged(self):
        now = kst(2027, 2, 9)
        base = [(i.id, i.level, i.title) for i in inbox.build_items(snapshot(now))]
        self.assertFalse([entry for entry in base if entry[0].startswith("terms:")])
        again = [(i.id, i.level, i.title) for i in inbox.build_items(snapshot(now, source_terms=None))]
        self.assertEqual(base, again)

    def test_build_items_uses_the_korean_date_of_now(self):
        providers = [prov(expires="2027-02-08")]
        before_midnight = inbox.build_items(snapshot(datetime.datetime(2027, 2, 8, 14, 59, tzinfo=datetime.timezone.utc), source_terms=providers))      # KST 2027-02-08 23:59
        after_midnight = inbox.build_items(snapshot(datetime.datetime(2027, 2, 8, 15, 0, tzinfo=datetime.timezone.utc), source_terms=providers))         # KST 2027-02-09 00:00
        self.assertEqual([(i.id, i.level) for i in before_midnight if i.id.startswith("terms:")], [("terms:noaa_swpc_json:soon", "check")])
        self.assertEqual([(i.id, i.level) for i in after_midnight if i.id.startswith("terms:")], [("terms:noaa_swpc_json:expired", "action")])

    def test_only_the_lapsed_state_is_announced_and_going_from_soon_to_lapsed_is_a_new_alert(self):
        soon = inbox.build_items(snapshot(kst(2027, 2, 1), source_terms=[prov()]))
        self.assertEqual(inbox.plan_notice(soon, None)[0], [])                       # 미리 알림(check)은 코멘트·텔레그램을 보내지 않는다
        lapsed = inbox.build_items(snapshot(kst(2027, 2, 9), source_terms=[prov()]))
        self.assertEqual(inbox.plan_notice(lapsed, None)[0], ["terms:noaa_swpc_json:expired"])
        self.assertEqual(inbox.plan_notice(lapsed, ["terms:noaa_swpc_json:expired"])[0], [])      # 이미 알렸으면 다시 알리지 않는다

    def test_the_same_fact_is_not_listed_twice_when_the_watchdog_issue_is_open_too(self):
        issues = [h.make_watchdog(7, blog="공통", code="SOURCE_TERMS_EXPIRED", severity="critical", message="약관 점검 기한이 지났습니다."),
                  h.make_watchdog(8, blog="공통", code="SOURCE_TERMS_EXPIRING", severity="warning", message="다가옵니다."),
                  h.make_watchdog(9, blog="chance", code="STALE", severity="critical")]
        ids = [i.id for i in inbox.build_items(snapshot(kst(2027, 2, 9), issues=issues, source_terms=[prov()]))]
        self.assertIn("terms:noaa_swpc_json:expired", ids)
        self.assertNotIn("watchdog:7", ids)
        self.assertNotIn("watchdog:8", ids)
        self.assertIn("watchdog:9", ids)                                             # 다른 워치독 알림은 그대로

    def test_the_watchdog_issue_stays_visible_only_while_the_registry_could_not_be_read(self):
        issues = [h.make_watchdog(7, blog="공통", code="SOURCE_TERMS_EXPIRED", severity="critical", message="약관 점검 기한이 지났습니다.")]
        unreadable = [i.id for i in inbox.build_items(snapshot(kst(2027, 2, 9), issues=issues, source_terms=None, failures=[("source_terms", "읽지 못함")]))]
        self.assertIn("watchdog:7", unreadable)                                      # 허용 목록을 못 읽었으면 워치독 이슈가 유일한 단서다
        self.assertIn("source:source_terms", unreadable)
        missing = [i.id for i in inbox.build_items(snapshot(kst(2027, 2, 9), issues=issues, source_terms=None))]
        self.assertIn("watchdog:7", missing)                                         # 파일이 없어(읽지 않아) 모음이 모를 때도 이슈를 숨기지 않는다
        fine = [i.id for i in inbox.build_items(snapshot(kst(2027, 2, 1), issues=issues, source_terms=[prov(expires="2028-01-01")]))]
        self.assertNotIn("watchdog:7", fine)                                         # 읽었고 이상 없으면(기한을 갱신한 직후) 아직 안 닫힌 낡은 이슈를 새 일로 싣지 않는다
        self.assertEqual([i for i in fine if i.startswith("terms:")], [])

    def test_renewing_the_date_before_the_watchdog_closes_its_issue_announces_nothing_new(self):
        issue = h.make_watchdog(7, blog="공통", code="SOURCE_TERMS_EXPIRED", severity="critical", message="약관 점검 기한이 지났습니다.")
        first = inbox.build_items(snapshot(kst(2027, 2, 9), issues=[issue], source_terms=[prov()]))
        new_first, marker_first = inbox.plan_notice(first, None)
        self.assertEqual(new_first, ["terms:noaa_swpc_json:expired"])                # 지난 날의 알림은 한 번 간다
        renewed = inbox.build_items(snapshot(kst(2027, 2, 10), issues=[issue], source_terms=[prov(expires="2028-02-08")]))     # 운영자가 갱신했지만 워치독은 하루 두 번만 돌아 이슈가 아직 열려 있다
        new_second, marker_second = inbox.plan_notice(renewed, marker_first)
        self.assertEqual((new_second, marker_second), ([], []))                      # 낡은 이슈가 '새로 해야 할 일' 로 되살아나 알림이 한 번 더 가지 않는다
        closed = inbox.build_items(snapshot(kst(2027, 2, 10), issues=[], source_terms=[prov(expires="2028-02-08")]))
        self.assertEqual(inbox.plan_notice(closed, marker_second), ([], []))

    def test_a_provider_without_a_name_is_shown_by_its_id(self):
        nameless = {"provider_id": "no_name_one", "enabled": True, "snapshot": {"expires_at": "2027-02-08"}}
        (item,) = self.items([nameless])
        self.assertTrue(item.title.endswith(" — no_name_one"), item.title)

    def test_a_paused_pipeline_still_shows_the_terms_items(self):
        for paused in (False, True):
            with self.subTest(paused=paused):
                items = inbox.build_items(snapshot(kst(2027, 2, 1), source_terms=[prov(expires="2027-02-08"), prov("gone_one", "2027-01-01")], paused=paused))
                ids = {i.id: i.level for i in items}
                self.assertEqual((ids["terms:noaa_swpc_json:soon"], ids["terms:gone_one:expired"]), ("check", "action"))      # 약관 기한은 발행 정지와 상관없이 알린다(OPS_INBOX 11-1)

    def test_a_stranger_cannot_hide_anything_by_copying_the_title(self):
        stranger = h.make_watchdog(7, blog="공통", code="SOURCE_TERMS_EXPIRED", login="낯선사람", assoc="NONE")
        ids = [i.id for i in inbox.build_items(snapshot(kst(2027, 2, 9), issues=[stranger], source_terms=[prov()]))]
        self.assertNotIn("watchdog:7", ids)                                          # 낯선 사람의 이슈는 원래 싣지 않는다
        self.assertIn("terms:noaa_swpc_json:expired", ids)

    def test_an_unreadable_registry_keeps_the_previously_announced_ids_in_the_marker(self):
        kept = inbox.plan_notice([], ("terms:noaa_swpc_json:expired", "pr:1:x"), [("source_terms", "x")])[1]
        self.assertEqual(kept, ["terms:noaa_swpc_json:expired"])
        self.assertEqual(inbox.SOURCE_LABELS["source_terms"], "허용 목록(약관 점검 기한)")
        items = inbox.failure_items([("source_terms", "pipeline/source_registry.json: JSON 형식 오류")], h.REPO_URL)
        self.assertEqual([(i.id, i.level) for i in items], [("source:source_terms", "check")])


class TermsReadAndRunTest(unittest.TestCase):
    """scripts/ops_inbox.py 의 허용 목록 읽기: 파일이 없으면 조용히 없음(예전과 같다), 읽지 못하면 '조회 실패' 항목, 있으면 모음 본문에 경고가 보인다."""

    def root(self, text=None, raw=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = h.make_root(folder.name)
        if text is not None or raw is not None:
            (root / "pipeline" / "source_registry.json").write_bytes(raw if raw is not None else text.encode("utf-8"))
        return root

    def test_a_missing_file_is_silently_nothing(self):
        failures = []
        self.assertIsNone(oi.read_source_terms(self.root(), failures))
        self.assertEqual(failures, [])

    def test_a_good_file_gives_the_providers_array(self):
        failures = []
        providers = oi.read_source_terms(self.root(json.dumps({"schema_version": 1, "providers": [prov()]})), failures)
        self.assertEqual((providers, failures), ([prov()], []))

    def test_an_unreadable_file_is_a_failure_with_a_short_reason_and_no_path(self):
        cases = {"깨진 JSON": b"{ not json", "UTF-8 아님": b"\xff\xfe\x00", "배열 최상위": b"[1, 2]", "providers 없음": b'{"schema_version": 1}', "providers 가 객체": b'{"providers": {}}'}
        for label, raw in cases.items():
            with self.subTest(label=label):
                failures = []
                self.assertIsNone(oi.read_source_terms(self.root(raw=raw), failures))
                self.assertEqual([source for source, _ in failures], ["source_terms"])
                self.assertIn("pipeline/source_registry.json", failures[0][1])
                self.assertNotIn(":\\", failures[0][1])
                self.assertNotIn("/tmp", failures[0][1])

    def test_a_deeply_nested_file_and_a_read_error_are_failures_never_a_crash(self):
        deep = ("[" * 30000 + "]" * 30000).encode("ascii")                            # 재귀 한도를 넘는 중첩 — 읽기 방어막(RecursionError)이 없으면 모음이 통째로 멈춘다
        failures = []
        self.assertIsNone(oi.read_source_terms(self.root(raw=deep), failures))
        self.assertEqual([source for source, _ in failures], ["source_terms"])
        self.assertIn("pipeline/source_registry.json", failures[0][1])
        root = self.root(json.dumps({"schema_version": 1, "providers": [prov()]}))
        failures = []
        with mock.patch.object(pathlib.Path, "read_text", side_effect=PermissionError(13, "denied")):
            self.assertIsNone(oi.read_source_terms(root, failures))                  # 읽기 권한 오류(OSError)도 같다
        self.assertEqual(failures, [("source_terms", "pipeline/source_registry.json: PermissionError")])

    def run_inbox(self, root, now):
        lines, fake = [], h.FakeGitHub()
        env = {"GITHUB_REPOSITORY": h.REPO, "GITHUB_REPOSITORY_OWNER": "octo"}
        code = oi.run(env, fake, now, root, lines.append, sleep=lambda seconds: None)
        return code, "\n".join(lines)

    def test_a_run_shows_the_early_warning_as_a_check_item_and_no_alert_count_change(self):
        root = self.root(json.dumps({"schema_version": 1, "providers": [prov(expires="2027-02-08"), prov("off_one", "2027-02-02", enabled=False)]}))
        code, text = self.run_inbox(root, kst(2027, 1, 30))
        self.assertEqual(code, 0)
        self.assertIn("약관 점검 기한이 다가옵니다 — NOAA SWPC JSON", text)
        self.assertIn("점검 기한 2027-02-08", text)
        self.assertNotIn("off_one", text)
        self.assertIn("확인하면 좋은 것 1건", text)
        self.assertIn("지금 해야 할 일 0건", text)

    def test_a_run_after_the_expiry_shows_an_action_item(self):
        root = self.root(json.dumps({"schema_version": 1, "providers": [prov(expires="2027-02-08")]}))
        _, text = self.run_inbox(root, kst(2027, 2, 9))
        self.assertIn("약관 점검 기한이 지났습니다 — NOAA SWPC JSON", text)
        self.assertIn("지금 해야 할 일 1건", text)

    def test_a_run_with_a_far_expiry_or_no_file_prints_nothing_about_terms(self):
        for root in (self.root(json.dumps({"schema_version": 1, "providers": [prov(expires="2028-01-01")]})), self.root()):
            _, text = self.run_inbox(root, kst(2027, 1, 30))
            self.assertNotIn("약관", text)

    def test_a_broken_registry_file_becomes_a_read_failure_item_in_the_run(self):
        _, text = self.run_inbox(self.root(text="{ not json"), kst(2027, 1, 30))
        self.assertIn("조회 실패 — 허용 목록(약관 점검 기한)", text)
        self.assertIn("JSON 형식 오류", text)


class WatchdogTermsTest(unittest.TestCase):
    """scripts/watchdog.py terms_findings: 14일 안이면 SOURCE_TERMS_EXPIRING(경고), 지났거나 없으면 SOURCE_TERMS_EXPIRED(심각). 한국 날짜 기준·꺼진 제공처 제외·읽지 못하면 ::warning::."""

    def root(self, providers=None, raw=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = pathlib.Path(folder.name)
        if providers is not None or raw is not None:
            (root / "pipeline").mkdir()
            (root / "pipeline" / "source_registry.json").write_bytes(raw if raw is not None else json.dumps({"schema_version": 1, "providers": providers}).encode("utf-8"))
        return root

    def findings(self, root, now):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            found = watchdog.terms_findings(root, now)
        return found, buf.getvalue()

    def test_an_expiring_provider_is_one_warning_finding(self):
        found, out = self.findings(self.root([prov(expires="2027-02-08")]), kst(2027, 2, 1))
        self.assertEqual([(f.blog, f.code, f.severity) for f in found], [("공통", "SOURCE_TERMS_EXPIRING", "warning")])
        self.assertEqual(found[0].title, "[Watchdog] 공통: SOURCE_TERMS_EXPIRING")
        self.assertIn("noaa_swpc_json(2027-02-08, 7일 남음)", found[0].message)
        self.assertIn("14일 안으로", found[0].message)
        self.assertIn("운영자 승인", found[0].message)
        self.assertEqual(out, "")

    def test_a_lapsed_provider_is_one_critical_finding(self):
        found, _ = self.findings(self.root([prov(expires="2027-02-08")]), kst(2027, 2, 11))
        self.assertEqual([(f.code, f.severity) for f in found], [("SOURCE_TERMS_EXPIRED", "critical")])
        self.assertIn("noaa_swpc_json(2027-02-08, 3일 지남)", found[0].message)
        self.assertIn("FACT_NOT_READY", found[0].message)

    def test_a_missing_expiry_is_critical_and_does_not_echo_the_file(self):
        found, _ = self.findings(self.root([prov(expires="내일 @누군가")]), kst(2027, 2, 1))
        self.assertEqual([(f.code, f.severity) for f in found], [("SOURCE_TERMS_EXPIRED", "critical")])
        self.assertIn("noaa_swpc_json(기한 없음)", found[0].message)
        self.assertNotIn("@누군가", found[0].message)

    def test_both_kinds_at_once_are_two_findings_and_long_lists_are_shortened(self):
        providers = [prov("p_lapsed", "2027-01-20"), prov("p_soon", "2027-02-05")] + [prov(f"p_more{n}", "2027-01-01") for n in range(7)]
        found, _ = self.findings(self.root(providers), kst(2027, 2, 1))
        self.assertEqual([(f.code, f.severity) for f in found], [("SOURCE_TERMS_EXPIRED", "critical"), ("SOURCE_TERMS_EXPIRING", "warning")])
        self.assertIn("외 3개", found[0].message)                                     # 지난 제공처 8개 중 5개만 이름을 싣는다
        self.assertEqual(found[1].message.count("p_soon"), 1)

    def test_far_disabled_missing_file_and_no_providers_are_all_quiet(self):
        for root in (self.root([prov(expires="2028-01-01")]), self.root([prov(enabled=False)]), self.root(), self.root([])):
            found, out = self.findings(root, kst(2027, 2, 1))
            self.assertEqual((found, out), ([], ""))

    def test_the_date_is_the_korean_date_of_now(self):
        providers = [prov(expires="2027-02-08")]
        before, _ = self.findings(self.root(providers), datetime.datetime(2027, 2, 8, 14, 59, tzinfo=datetime.timezone.utc))
        after, _ = self.findings(self.root(providers), datetime.datetime(2027, 2, 8, 15, 0, tzinfo=datetime.timezone.utc))
        self.assertEqual([f.code for f in before], ["SOURCE_TERMS_EXPIRING"])
        self.assertEqual([f.code for f in after], ["SOURCE_TERMS_EXPIRED"])

    def test_an_unreadable_file_is_a_warning_annotation_not_silence_and_not_a_crash(self):
        for raw in (b"{ not json", b"\xff\xfe", b"[1]", b'{"providers": 5}'):
            with self.subTest(raw=raw):
                found, out = self.findings(self.root(raw=raw), kst(2027, 2, 1))
                self.assertEqual(found, [])
                self.assertTrue(out.startswith("::warning::"), out)
                self.assertEqual(len(out.splitlines()), 1)
                self.assertIn("약관 점검 기한을 확인하지 못했습니다", out)

    def test_a_deeply_nested_file_and_a_read_error_are_warning_annotations_never_a_crash(self):
        deep = ("[" * 30000 + "]" * 30000).encode("ascii")
        found, out = self.findings(self.root(raw=deep), kst(2027, 2, 1))
        self.assertEqual(found, [])
        self.assertTrue(out.startswith("::warning::") and "RecursionError" in out, out)
        root = self.root([prov(expires="2027-02-08")])
        with mock.patch.object(pathlib.Path, "read_text", side_effect=PermissionError(13, "denied")):
            found, out = self.findings(root, kst(2027, 2, 1))
        self.assertEqual(found, [])
        self.assertTrue(out.startswith("::warning::") and "PermissionError" in out, out)
        self.assertEqual(len(out.splitlines()), 1)

    def test_the_run_warning_line_is_listed_next_to_the_terms_item_a_documented_limit(self):
        """OPS_INBOX 11-1 의 한계: 같은 사실의 '이슈' 는 모음에서 숨기지만, 워치독 실행이 남긴 ::warning:: 주석이 만드는 '실행 경고' 줄(run:watchdog.yml:warn)은 약관 경고가 있는 동안 따로 보인다.
        둘 다 확인 수준이라 알림은 가지 않는다. 이 줄을 거르게 고치면 이 시험과 문서 11-1 의 그 문장을 함께 고친다."""
        now = kst(2027, 2, 1)
        (finding,) = watchdog.terms_findings(self.root([prov(expires="2027-02-08")]), now)
        text = f"{finding.title}: {watchdog._oneline(finding.message)[:200]}"           # main() 이 ::warning:: 으로 찍는 줄과 같은 글
        run = h.make_run(901, created=h.iso(now - datetime.timedelta(hours=1)), conclusion="success", name="발행 중단 감시", path=".github/workflows/watchdog.yml")
        snap = snapshot(now, source_terms=[prov(expires="2027-02-08")], runs={"watchdog.yml": [run]},
                        annotations={901: [{"annotation_level": "warning", "message": text, "title": ""}]}, workflow_names={"watchdog.yml": "[공통] 발행 중단 감시·알림"})
        items = inbox.build_items(snap)
        levels = {i.id: i.level for i in items}
        self.assertEqual((levels["terms:noaa_swpc_json:soon"], levels["run:watchdog.yml:warn"]), ("check", "check"))
        self.assertEqual(inbox.plan_notice(items, None)[0], [])

    def test_collect_adds_the_findings_after_the_blog_findings(self):
        root = self.root([prov(expires="2027-02-08")])
        with mock.patch.object(watchdog, "enabled_blogs", return_value=[]):
            findings, stats = watchdog.collect({"blogs": []}, root, kst(2027, 2, 1), None)
        self.assertEqual([f.code for f in findings], ["SOURCE_TERMS_EXPIRING"])
        self.assertEqual(stats, [])

    def test_a_warning_finding_opens_an_issue_without_failing_the_run_and_a_lapse_does(self):
        class Client:
            def __init__(self):
                self.created = []

            def create_issue(self, title, body, assignees=None):
                self.created.append((title, body))
                return {"number": 1}

        client = Client()
        warn = watchdog.terms_findings(self.root([prov(expires="2027-02-08")]), kst(2027, 2, 1))
        created, closed, renotified, new_critical = watchdog.sync_issues(warn, [], client, owner="octo", now=kst(2027, 2, 1), out=lambda text: None)
        self.assertEqual((created, new_critical), (["[Watchdog] 공통: SOURCE_TERMS_EXPIRING"], []))
        self.assertIn("**블로그**: `공통` / **코드**: `SOURCE_TERMS_EXPIRING` / **심각도**: warning", client.created[0][1])
        lapsed = watchdog.terms_findings(self.root([prov(expires="2027-02-08")]), kst(2027, 2, 9))
        created, _, _, new_critical = watchdog.sync_issues(lapsed, [], Client(), owner="octo", now=kst(2027, 2, 9), out=lambda text: None)
        self.assertEqual(new_critical, ["[Watchdog] 공통: SOURCE_TERMS_EXPIRED"])

    def test_when_the_registry_is_renewed_the_open_issue_is_closed(self):
        class Client:
            def __init__(self):
                self.closed, self.comments = [], []

            def comment(self, number, body):
                self.comments.append(number)

            def close(self, number):
                self.closed.append(number)

        open_issue = {"number": 5, "title": "[Watchdog] 공통: SOURCE_TERMS_EXPIRING", "body": "x", "created_at": "2027-01-26T00:00:00Z"}
        renewed = watchdog.terms_findings(self.root([prov(expires="2027-05-08")]), kst(2027, 2, 1))
        client = Client()
        _, closed, _, _ = watchdog.sync_issues(renewed, [open_issue], client, owner="octo", now=kst(2027, 2, 1), out=lambda text: None)
        self.assertEqual((closed, client.closed), (["[Watchdog] 공통: SOURCE_TERMS_EXPIRING"], [5]))



ROOT = _bootstrap.ROOT


def read_doc(name):
    return (ROOT / "docs" / name).read_text(encoding="utf-8")


class AlertDocsMatchCodeTest(unittest.TestCase):
    """L7 의 문서(OPS_INBOX 11절·TELEGRAM_INBOX 12절·ARCHITECTURE 전송 규칙·ACTIONS_GUIDE·DEFECT_REGISTER)의 숫자·이름·표가 코드의 실제 상수와 어긋나지 않는지 본다.
    글이 옳은지는 시험이 알 수 없어 사람이 본다 — 여기서는 숫자·이름·표·옛 문장·문서 규칙(물결표·http 주소 없음)만 대조한다(독립 검증 Q: 문서를 읽는 시험이 없어 옛 문장이 남았다)."""

    OPS = read_doc("OPS_INBOX.md")
    ARCH = read_doc("ARCHITECTURE.md")
    ACTIONS = read_doc("ACTIONS_GUIDE.md")
    TELEGRAM = read_doc("TELEGRAM_INBOX.md")
    REGISTER = read_doc("DEFECT_REGISTER.md")
    S11 = OPS[OPS.index("## 11. 운영 알림이 조용히 사라지지 않게"):]
    S12 = TELEGRAM[TELEGRAM.index("## 12. 보내기 재시도"):]

    @classmethod
    def sub(cls, number):
        """OPS_INBOX 의 `### 11-n.` 소절."""
        start = cls.S11.index(f"### 11-{number}. ")
        match = re.search(r"^###? ", cls.S11[start + 5:], re.M)
        return cls.S11[start:start + 5 + match.start()] if match else cls.S11[start:]

    @classmethod
    def row(cls, code):
        """DEFECT_REGISTER 의 한 결함 행."""
        found = [line for line in cls.REGISTER.splitlines() if line.startswith(f"| **{code}** |")]
        assert len(found) == 1, (code, len(found))
        return found[0]

    def test_the_retry_numbers_in_the_docs_are_the_ones_in_the_code(self):
        backoff = " → ".join(str(seconds) for seconds in notify.RETRY_BACKOFF) + "초"
        extras = (f"5통 실행은 추가 {notify.extra_retries_for(5)}번, 3통 이하는 {notify.extra_retries_for(3)}번, "
                  f"텔레그램 수신 프로세스의 {telegram_inbox.MAX_MESSAGES}통은 {notify.extra_retries_for(telegram_inbox.MAX_MESSAGES)}번")
        text = self.sub(3)
        for needle in (f"최대 {notify.TRANSIENT_RETRIES}번", backoff, f"한 통의 요청은 최대 {1 + notify.TRANSIENT_RETRIES + 2}번", extras,
                       f"{notify.RUN_TIME_BUDGET}초(`RUN_TIME_BUDGET`)", "`UNSURE_RETRIES`", "`extra_retries_for`"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        self.assertEqual({notify.extra_retries_for(n) for n in (1, 2, 3)}, {notify.MAX_RETRIES_PER_RUN})     # '3통 이하는 6번' 이 상한 그대로인 것
        self.assertEqual(notify.UNSURE_RETRIES, 1)
        self.assertEqual(notify.UNSURE_REASONS, (notify.SERVER_ERROR,))                                      # 문서가 말하는 '5xx 는 받았을 수 있는 실패'

    def test_the_structure_document_states_the_current_transmission_rule(self):
        self.assertNotIn("한 통에 요청은 최대 5번", self.ARCH)
        start = self.ARCH.index("**전송 규칙**")
        rule = self.ARCH[start:self.ARCH.index("\n", start)]
        self.assertNotIn("5xx 는 2초 뒤 한 번", rule)                                                  # 읽기(getUpdates)쪽 문장은 그대로 한 번이다 — 보내기 규칙에만 옛 문장이 없어야 한다
        for needle in (f"한 통에 최대 {notify.TRANSIENT_RETRIES}번", f"한 통에 요청은 최대 {1 + notify.TRANSIENT_RETRIES + 2}번", f"{notify.RUN_TIME_BUDGET}초(`RUN_TIME_BUDGET`)",
                       f"5통은 추가 {notify.extra_retries_for(5)}번·8통은 {notify.extra_retries_for(8)}번", " → ".join(str(s) for s in notify.RETRY_BACKOFF) + "초"):
            with self.subTest(needle=needle):
                self.assertIn(needle, rule)

    def test_the_telegram_inbox_document_matches_its_message_count(self):
        self.assertIn(f"최대 {telegram_inbox.MAX_MESSAGES}통(`MAX_MESSAGES`)", self.S12)
        self.assertEqual(notify.extra_retries_for(telegram_inbox.MAX_MESSAGES), 0)
        self.assertIn("추가 재시도 상한이 0", self.S12)
        self.assertIn(f"최대 {notify.TRANSIENT_RETRIES}번", self.S12)

    def test_the_paging_numbers_are_the_ones_in_the_code_and_the_old_sentences_are_gone(self):
        inbox_cap = f"최대 {oi.MAX_ISSUE_PAGES}쪽({oi.MAX_ISSUE_PAGES * oi.ISSUES_PER_PAGE}건)"
        watchdog_cap = f"최대 {watchdog.MAX_PAGES}쪽({watchdog.MAX_PAGES * watchdog.PAGE_SIZE}건)"
        self.assertIn(inbox_cap, self.sub(2))
        self.assertIn(watchdog_cap, self.sub(2))
        before = self.OPS[:self.OPS.index("## 11. ")]
        self.assertIn(inbox_cap, before.split("## 5. ")[1].split("## 6. ")[0])                       # 5절 한계 5번
        self.assertNotIn("쪽 넘김 없음", before)
        self.assertNotIn("처음 100건", before)
        self.assertNotIn("처음 100건", self.ACTIONS)
        self.assertIn(inbox_cap, self.ACTIONS)

    def test_the_new_item_ids_and_codes_are_in_the_tables(self):
        rules = self.OPS.split("## 3. ")[1].split("## 4. ")[0]
        for suffix in ("soon", "expired", "missing"):
            with self.subTest(suffix=suffix):
                self.assertIn(f"terms:<제공처>:{suffix}", rules)
        items = inbox.terms_items([prov(expires="2027-02-08"), prov("gone_one", "2027-01-01"), prov("none_one", None)], datetime.date(2027, 1, 30), h.REPO_URL)
        self.assertEqual({item.id.split(":")[2] for item in items}, {"soon", "expired", "missing"})         # 문서가 적은 세 id 꼴이 코드가 만드는 것 전부다
        self.assertIn("source:issues_cap", rules)
        self.assertIn("source:source_terms", rules)
        self.assertEqual(inbox.SOURCE_PREFIXES["source_terms"], ("terms:",))
        self.assertIn("`terms:<제공처>:…`", self.OPS.split("## 4. ")[1].split("## 5. ")[0])

    def test_the_watchdog_code_table_has_both_new_codes_with_the_right_severity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "pipeline").mkdir()
            (root / "pipeline" / "source_registry.json").write_text(json.dumps({"providers": [prov(expires="2027-02-08"), prov("gone_one", "2027-01-01")]}), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                found = watchdog.terms_findings(root, kst(2027, 1, 30))
        shown = {"critical": "심각", "warning": "경고"}
        self.assertEqual(sorted(f.code for f in found), sorted(terms_deadline.FINDING_CODES))
        for finding in found:
            with self.subTest(code=finding.code):
                self.assertRegex(self.ACTIONS, rf"\| `{finding.code}` \| {shown[finding.severity]} \|")

    def test_the_stated_limits_and_open_questions_are_written_down(self):
        text = self.sub(1)
        self.assertIn("정지(`PIPELINE_PAUSE`) 중에도 뜹니다", text)
        self.assertIn("run:watchdog.yml:warn", text)                                                  # 한계: 실행 경고 줄이 따로 보일 수 있다
        self.assertIn("`.github/editorial/TELEGRAM_SETUP.md`", text)
        self.assertIn("'최대 10초'는 유지", text)                                                      # tests/test_notify_integration.py 가 그 문서의 '10초'를 찾는다
        self.assertIn(f"0–{terms_deadline.WARN_DAYS}일", text)
        self.assertIn("LEVEL_ACTION", text)

    def test_the_defect_register_has_the_five_rows_in_the_table_shape(self):
        self.assertIn("D-360–D-364 는 2026-11-22 에 추가했다", self.REGISTER)
        self.assertIn("(2026-11-22, 결함 D-360–D-364)", self.S11)
        for number in range(360, 365):
            with self.subTest(defect=number):
                row = self.row(f"D-{number}")
                self.assertEqual(len(row.split(" | ")), 6)
                self.assertTrue(row.endswith(" |"))
        self.assertIn("시험 5개", self.row("D-362"))
        self.assertIn("`extra_retries_for`", self.row("D-362"))
        self.assertIn("AlertDocsMatchCodeTest", self.row("D-364"))

    def test_the_new_text_follows_the_document_rules(self):
        pieces = {"OPS_INBOX 11절": self.S11, "TELEGRAM_INBOX 12절": self.S12}
        pieces.update({f"DEFECT_REGISTER D-{n}": self.row(f"D-{n}") for n in range(360, 365)})
        start = self.ARCH.index("일시 오류는 다시 보낸다(L7, D-362)")
        pieces["ARCHITECTURE 전송 규칙(새 문장)"] = self.ARCH[start:self.ARCH.index("\n", start)]
        for label, text in pieces.items():
            with self.subTest(piece=label):
                self.assertNotIn(chr(126), text)                                                      # 물결표 없음(범위는 가운뎃점·줄표로)
                self.assertNotIn("http://", text)
                self.assertNotIn("https://", text)
                self.assertNotIn("{%", text)                                                          # Liquid 태그 없음


if __name__ == "__main__":
    unittest.main()
