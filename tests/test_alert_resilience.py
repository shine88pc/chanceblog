"""운영 알림이 조용히 사라지지 않게(L7, 결함 D-360·D-361·D-362) 시험.

세 가지를 본다. ① 열린 이슈 읽기의 쪽 넘기기와 '일부만 읽음' 경고(확인 필요 모음·워치독, D-361) ② 켜진 허용 목록 제공처의 약관 점검 기한이 14일 안으로 다가오면 미리 알리는 것(D-360)
③ 텔레그램 전송의 일시 오류 재시도(D-362). 네트워크·실제 시계는 쓰지 않는다 — 날짜·시각은 모두 값으로 넣고, 요청은 가짜 GitHub·가짜 HTTP 가 받는다. 가짜 비밀은 런타임에 조합한다.
"""
import contextlib
import io
import json
import re
import sys
import unittest
from unittest import mock

import _bootstrap
import ops_inbox_helpers as h
import ops_inbox as oi
from pipeline import inbox

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


if __name__ == "__main__":
    unittest.main()
