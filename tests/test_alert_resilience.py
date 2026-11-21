"""운영 알림이 조용히 사라지지 않게(L7, 결함 D-360·D-361·D-362) 시험.

세 가지를 본다. ① 열린 이슈 읽기의 쪽 넘기기와 '일부만 읽음' 경고(확인 필요 모음·워치독, D-361) ② 켜진 허용 목록 제공처의 약관 점검 기한이 14일 안으로 다가오면 미리 알리는 것(D-360)
③ 텔레그램 전송의 일시 오류 재시도(D-362). 네트워크·실제 시계는 쓰지 않는다 — 날짜·시각은 모두 값으로 넣고, 요청은 가짜 GitHub·가짜 HTTP 가 받는다. 가짜 비밀은 런타임에 조합한다.
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
from notify_helpers import CHAT, ENV, TOKEN, FakeNet, http_error, leaks, make_notifier, ok_reply
from pipeline import inbox, notify, terms_deadline

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402


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

    def test_the_default_output_is_print(self):
        client = watchdog.GitHubClient("t", "o/r", opener=PagedOpener([labeled_issue(n) for n in range(1, 601)]))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            client.list_open_issues()
        self.assertIn("::warning::", buf.getvalue())


class TelegramRetryTest(unittest.TestCase):
    """텔레그램 전송의 일시 오류 재시도(D-362): 한 통에 최대 3번·간격을 늘려, 영구 오류는 다시 보내지 않고, 보낸 통은 다시 보내지 않으며, 한 실행 전체의 재시도는 묶고, 비밀은 어디에도 없다."""

    @staticmethod
    def texts(net):
        return [body["text"] for body in net.bodies()]

    def test_the_constants_agree_with_each_other_and_stay_inside_the_workflow_limit(self):
        self.assertEqual(notify.TRANSIENT_RETRIES, 3)
        self.assertEqual(len(notify.RETRY_BACKOFF), notify.TRANSIENT_RETRIES)
        self.assertEqual(notify.RETRY_BACKOFF[0], notify.NETWORK_RETRY_WAIT)
        self.assertEqual(list(notify.RETRY_BACKOFF), sorted(notify.RETRY_BACKOFF))                      # 간격은 줄지 않는다
        self.assertEqual(set(notify.TRANSIENT_REASONS), {"rate_limited", "network", "timeout", "server_error"})
        self.assertEqual(notify.Budget().retries, notify.MAX_RETRIES_PER_RUN)
        # 알림을 보내는 워크플로의 제한은 가장 짧은 것이 5분(300초) — 텔레그램이 통째로 막혀 모든 요청이 제한 시간(15초)까지 가도 그 안에 끝나야 한다
        worst = (notify.MAX_MESSAGES + notify.MAX_RETRIES_PER_RUN) * notify.TIMEOUT_SECONDS + notify.MAX_RETRIES_PER_RUN * notify.RETRY_AFTER_MAX
        self.assertLess(worst, 300)

    def test_a_flaky_send_is_retried_with_growing_waits_until_it_gets_through(self):
        net = FakeNet(urllib.error.URLError("x"), http_error(502, "Bad Gateway"), socket.timeout("x"), ok_reply())
        notifier, net, clock = make_notifier(net=net)
        result = notifier.send_message("안녕")
        self.assertEqual((result.ok, result.sent, result.reason), (True, True, "sent"))
        self.assertEqual((net.calls, clock.sleeps), (4, [2, 4, 8]))

    def test_after_the_third_retry_it_gives_up_and_the_failure_is_in_the_result(self):
        for outcome, reason, status in ((http_error(502, "Bad Gateway"), "server_error", 502), (urllib.error.URLError("x"), "network", None),
                                        (urllib.error.URLError(socket.timeout("x")), "timeout", None)):
            with self.subTest(reason=reason):
                notifier, net, clock = make_notifier(net=FakeNet(outcome))
                result = notifier.send_message("안녕")
                self.assertEqual((result.ok, result.sent, result.reason, result.status), (False, False, reason, status))
                self.assertEqual((net.calls, clock.sleeps), (4, [2, 4, 8]))

    def test_a_failure_after_the_request_went_out_is_resent_at_most_once_so_a_delivered_message_is_not_tripled(self):
        """응답을 기다리다·읽다 끊긴 실패는 텔레그램이 이미 받았을 수 있다 — 같은 통이 여러 번 가지 않게 예전처럼 한 번만 다시 보낸다."""
        for exc in (socket.timeout("x"), TimeoutError("x"), ConnectionResetError("x"), http.client.RemoteDisconnected("x"), http.client.IncompleteRead(b"x"), OSError("x")):
            with self.subTest(exc=type(exc).__name__):
                notifier, net, clock = make_notifier(net=FakeNet(exc))
                result = notifier.send_message("안녕")
                self.assertEqual((result.sent, result.status, net.calls, clock.sleeps), (False, None, 2, [2]))
                self.assertIn(result.reason, ("timeout", "network"))
        self.assertEqual(notify.UNSURE_RETRIES, 1)

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

    def test_a_failure_before_the_request_went_out_or_an_answer_that_says_not_delivered_gets_all_three_retries(self):
        sure = (urllib.error.URLError("x"), urllib.error.URLError(socket.timeout("x")), urllib.error.URLError(ConnectionRefusedError("x")), http_error(500, "Internal Server Error"),
                http_error(503, "Service Unavailable"))
        for outcome in sure:
            with self.subTest(outcome=type(outcome).__name__ + str(getattr(outcome, "code", ""))):
                notifier, net, clock = make_notifier(net=FakeNet(outcome))
                self.assertFalse(notifier.send_message("안녕").sent)
                self.assertEqual((net.calls, clock.sleeps), (4, [2, 4, 8]))

    def test_one_unsure_failure_among_sure_ones_does_not_block_the_others_but_a_second_one_stops_the_resending(self):
        net = FakeNet(urllib.error.URLError("x"), socket.timeout("x"), urllib.error.URLError("x"), ok_reply())
        notifier, net, clock = make_notifier(net=net)
        self.assertTrue(notifier.send_message("안녕").sent)
        self.assertEqual((net.calls, clock.sleeps), (4, [2, 4, 8]))
        net = FakeNet(socket.timeout("x"), socket.timeout("x"), ok_reply())
        notifier, net, clock = make_notifier(net=net)
        result = notifier.send_message("안녕")
        self.assertEqual((result.sent, result.reason, net.calls), (False, "timeout", 2))             # 두 번째 '모르는 실패' 뒤에는 보내지 않는다(성공이 기다리고 있어도)

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

    def test_the_whole_run_shares_one_retry_allowance(self):
        notifier, net, clock = make_notifier(net=FakeNet(urllib.error.URLError("x")))
        results = [notifier.send_message(f"통 {i}") for i in range(6)]
        self.assertEqual([r.reason for r in results], ["network"] * 5 + ["limit"])
        self.assertEqual(net.calls, 4 + 4 + 1 + 1 + 1)                              # 처음 두 통이 재시도 6번을 쓰면 나머지 통은 한 번만 보내 본다
        self.assertEqual(sum(s for s in clock.sleeps if s >= 2), 2 + 4 + 8 + 2 + 4 + 8)
        self.assertEqual(notifier.budget.retries_left, 0)

    def test_the_allowance_can_be_set_and_is_restored_by_reset(self):
        budget = notify.Budget(retries=1)
        notifier, net, clock = make_notifier(net=FakeNet(urllib.error.URLError("x")), budget=budget)
        notifier.send_message("안녕")
        self.assertEqual((net.calls, budget.retries_left), (2, 0))
        budget.reset()
        self.assertEqual((budget.retries_left, budget.used), (1, 0))
        none = notify.Budget(retries=0)
        notifier, net, _ = make_notifier(net=FakeNet(urllib.error.URLError("x")), budget=none)
        self.assertFalse(notifier.send_message("안녕").sent)
        self.assertEqual(net.calls, 1)                                              # 재시도 0 이면 예전의 '한 번도 다시 보내지 않음'

    def test_the_worst_case_for_one_message_is_six_requests(self):
        net = FakeNet(http_error(429, retry_after=1), urllib.error.URLError("x"), http_error(502, "Bad Gateway"),
                      http_error(400, "Bad Request: can't parse entities: x"), http_error(400, "Bad Request: BUTTON_URL_INVALID"), http_error(400, "Bad Request: nope"), ok_reply())
        notifier, net, _ = make_notifier(net=net)
        result = notifier.send_message("<b>x</b>", parse_mode="HTML", buttons=[("열기", "https://github.com/shine88pc/chanceblog")])
        self.assertEqual((result.sent, result.reason, net.calls), (False, "bad_request", 6))

    def test_the_format_and_button_fallbacks_do_not_use_up_the_retry_allowance(self):
        net = FakeNet(http_error(400, "Bad Request: can't parse entities: x"), http_error(400, "Bad Request: BUTTON_URL_INVALID"), ok_reply())
        budget = notify.Budget()
        notifier, net, _ = make_notifier(net=net, budget=budget)
        self.assertTrue(notifier.send_message("<b>x</b>", parse_mode="HTML", buttons=[("열기", "https://github.com/shine88pc/chanceblog")]).sent)
        self.assertEqual(budget.retries_left, notify.MAX_RETRIES_PER_RUN)

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
                self.assertEqual(net.calls, 2 if isinstance(shape, (ConnectionResetError, socket.timeout)) else 4)       # 응답이 끊긴 실패는 한 번만 다시 보낸다

    def test_the_first_try_succeeds_without_any_wait_or_retry(self):
        notifier, net, clock = make_notifier()
        self.assertTrue(notifier.send_message("안녕").sent)
        self.assertEqual((net.calls, clock.sleeps, notifier.budget.retries_left), (1, [], notify.MAX_RETRIES_PER_RUN))


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

    def test_an_expiring_provider_is_one_check_item_that_names_the_date_and_days(self):
        (item,) = self.items([prov()])
        self.assertEqual((item.id, item.level), ("terms:noaa_swpc_json:soon", "check"))
        self.assertIn("다가옵니다", item.title)
        self.assertIn("NOAA SWPC JSON", item.title)
        self.assertIn("2027-02-08", item.detail)
        self.assertIn("9일 남았습니다", item.detail)
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
        self.assertIn("1일 지나", item.detail)
        self.assertIn("자동 글감에서 빠져", item.detail)

    def test_an_enabled_provider_without_a_readable_expiry_is_an_action_item(self):
        (item,) = self.items([prov(expires=None)])
        self.assertEqual((item.id, item.level), ("terms:noaa_swpc_json:missing", "action"))
        self.assertIn("읽을 수 없습니다", item.title)

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

    def test_the_watchdog_issue_stays_visible_when_the_inbox_has_nothing_of_its_own(self):
        issues = [h.make_watchdog(7, blog="공통", code="SOURCE_TERMS_EXPIRED", severity="critical", message="약관 점검 기한이 지났습니다.")]
        ids = [i.id for i in inbox.build_items(snapshot(kst(2027, 2, 9), issues=issues, source_terms=None, failures=[("source_terms", "읽지 못함")]))]
        self.assertIn("watchdog:7", ids)
        self.assertIn("source:source_terms", ids)
        stale = [i.id for i in inbox.build_items(snapshot(kst(2027, 2, 1), issues=issues, source_terms=[prov(expires="2028-01-01")]))]
        self.assertIn("watchdog:7", stale)                                           # 모음이 보기에는 이상 없는데 낡은 워치독 이슈만 남았으면 숨기지 않는다

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
        self.assertIn("9일 남았습니다", text)
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


if __name__ == "__main__":
    unittest.main()
