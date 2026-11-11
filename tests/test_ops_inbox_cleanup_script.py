"""확인 필요 모음 — 오래된 항목·의도된 정지 정리(2026-11-11)의 입출력 시험: 승인 대기 실행의 가지 PR 상태 조회·정책 파일 읽기·전체 실행·쓰기 범위.

네트워크는 쓰지 않는다(FakeGitHub). 분류 규칙 자체는 test_ops_inbox_cleanup.py, 정책 파일 검증은 test_ops_inbox_policy.py.
"""
import ast
import json
import re
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import _bootstrap
import ops_inbox_helpers as h
import ops_inbox as oi
import ops_inbox_repro as repro
from pipeline import inbox
from pipeline import inbox_policy as ip

NOW, URL, ago = h.NOW, h.REPO_URL, h.ago
TOKEN = "gh" + "s_" + "Q" * 36
ENV = {"GITHUB_REPOSITORY": h.REPO, "GITHUB_TOKEN": TOKEN, "GITHUB_REPOSITORY_OWNER": "octo"}
REAL_POLICY = (_bootstrap.ROOT / ip.POLICY_FILE).read_text(encoding="utf-8")


def api_error(status, message="HTTP error"):
    return oi.ApiError(message, status=status)


def listing(*prs):
    return list(prs)


# ----------------------------------------------------------------------------
# 응답 하나를 가지 상태로
# ----------------------------------------------------------------------------
class BranchPrStateTest(unittest.TestCase):
    BRANCH = "ai/claude/M029-a"

    def state(self, *prs, repo=h.REPO):
        return oi.branch_pr_state(list(prs), self.BRANCH, repo)

    def test_an_open_pull_request_makes_the_branch_alive_even_next_to_merged_ones(self):
        self.assertEqual(self.state(h.make_history_pull(1, self.BRANCH, "open")), "open")
        self.assertEqual(self.state(h.make_history_pull(1, self.BRANCH, "closed", True), h.make_history_pull(2, self.BRANCH, "open"), h.make_history_pull(3, self.BRANCH, "closed", False)), "open")

    def test_closed_with_a_merge_time_is_merged_and_without_it_is_closed(self):
        self.assertEqual(self.state(h.make_history_pull(1, self.BRANCH, "closed", True)), "merged")
        self.assertEqual(self.state(h.make_history_pull(1, self.BRANCH, "closed", False)), "closed")
        self.assertEqual(self.state(h.make_history_pull(1, self.BRANCH, "closed", False), h.make_history_pull(2, self.BRANCH, "closed", True)), "merged")

    def test_no_pull_request_means_unknown(self):
        for value in ([], None, {}, "x", 5, {"message": "Not Found"}):
            self.assertIsNone(oi.branch_pr_state(value, self.BRANCH, h.REPO), repr(value))

    def test_pull_requests_of_another_branch_or_of_a_fork_do_not_count(self):
        self.assertIsNone(self.state(h.make_history_pull(1, "ai/claude/other", "closed", True)))
        self.assertIsNone(self.state(h.make_history_pull(1, self.BRANCH, "closed", True, repo="stranger/blog")))
        self.assertIsNone(self.state(h.make_history_pull(1, self.BRANCH + "x", "closed", True)))
        self.assertEqual(self.state(h.make_history_pull(1, self.BRANCH, "closed", True, repo="OCTO/Blog")), "merged")                    # 저장소 이름은 대소문자를 가리지 않는다
        self.assertEqual(self.state(h.make_history_pull(1, self.BRANCH, "closed", True, repo="stranger/blog"), h.make_history_pull(2, self.BRANCH, "open")), "open")

    def test_an_unknown_state_value_or_a_broken_entry_is_skipped_not_believed(self):
        for state in ("weird", "", None, "draft", 5):
            self.assertIsNone(self.state(dict(h.make_history_pull(1, self.BRANCH, "closed", True), state=state)), repr(state))
        broken = [None, "x", 5, {}, {"head": None}, {"head": {"ref": self.BRANCH, "repo": None}, "state": "closed", "merged_at": "x"},
                  {"head": {"ref": self.BRANCH}, "state": "closed"}, {"head": {"ref": self.BRANCH, "repo": {"full_name": None}}, "state": "open"}]
        self.assertIsNone(oi.branch_pr_state(broken, self.BRANCH, h.REPO))
        self.assertEqual(oi.branch_pr_state(broken + [h.make_history_pull(9, self.BRANCH, "closed", True)], self.BRANCH, h.REPO), "merged")

    def test_the_state_word_is_read_in_any_letter_case(self):
        self.assertEqual(self.state(dict(h.make_history_pull(1, self.BRANCH, "closed", True), state="CLOSED")), "merged")
        self.assertEqual(self.state(dict(h.make_history_pull(1, self.BRANCH, "open"), state="Open")), "open")


# ----------------------------------------------------------------------------
# 가지마다 한 번 읽기
# ----------------------------------------------------------------------------
class FetchApprovalPrsTest(unittest.TestCase):
    def setUp(self):
        self.fake, self.failures = h.FakeGitHub(), []

    def fetch(self, runs, **kw):
        return oi.fetch_approval_prs(self.fake, runs, h.REPO, self.failures, **kw)

    def gets(self):
        return [(path, params) for method, path, params in self.fake.log if method == "GET"]

    def test_each_branch_is_asked_once_with_the_documented_parameters(self):
        self.fake.history_pulls = [h.make_history_pull(1, "ai/claude/M029-a", "closed", True), h.make_history_pull(2, "ai/claude/M034-b", "closed", False)]
        self.fake.pulls = [h.make_pull_raw(3, ref="ai/claude/M038-c")]
        runs = [h.make_approval_run(101, branch="ai/claude/M029-a"), h.make_approval_run(102, branch="ai/claude/M029-a", sha="b" * 40), h.make_approval_run(103, branch="ai/claude/M034-b"),
                h.make_approval_run(104, branch="ai/claude/M038-c"), h.make_approval_run(105, branch="ai/claude/M099-none")]
        self.assertEqual(self.fetch(runs), {"ai/claude/M029-a": "merged", "ai/claude/M034-b": "closed", "ai/claude/M038-c": "open"})
        self.assertEqual(self.gets(), [("/pulls", {"state": "all", "head": f"octo:{b}", "per_page": 10})
                                       for b in ("ai/claude/M029-a", "ai/claude/M034-b", "ai/claude/M038-c", "ai/claude/M099-none")])
        self.assertEqual(self.failures, [])

    def test_a_branch_without_any_pull_request_is_simply_not_in_the_answer(self):
        self.assertEqual(self.fetch([h.make_approval_run(101, branch="ai/claude/M099-none")]), {})
        self.assertEqual(self.failures, [])

    def test_no_waiting_runs_cost_no_calls(self):
        self.assertEqual(self.fetch([]), {})
        self.assertEqual(self.fake.log, [])
        self.assertEqual(self.fetch([h.make_approval_run(1, path=".github/workflows/ops-inbox.yml"), dict(h.make_approval_run(2), conclusion="success")]), {})
        self.assertEqual(self.fake.log, [])

    def test_a_failed_lookup_is_recorded_once_and_the_branch_stays_unknown(self):
        self.fake.history_pulls = [h.make_history_pull(1, "ai/claude/M034-b", "closed", True)]
        self.fake.fail = [(r"GET /pulls\?.*M029", api_error(500, "HTTP 500: boom"))]
        runs = [h.make_approval_run(101, branch="ai/claude/M029-a"), h.make_approval_run(102, branch="ai/claude/M034-b")]
        self.assertEqual(self.fetch(runs), {"ai/claude/M034-b": "merged"})
        self.assertEqual(len(self.failures), 1)
        self.assertEqual(self.failures[0][0], "approval_prs")
        self.assertIn("HTTP 500: boom", self.failures[0][1])
        self.assertNotIn("외 ", self.failures[0][1])

    def test_several_failures_are_summarised_in_one_record(self):
        self.fake.fail = [(r"GET /pulls\?", api_error(502, "HTTP 502: Bad Gateway"))]
        runs = [h.make_approval_run(100 + n, branch=f"ai/claude/B{n}") for n in range(3)]
        self.assertEqual(self.fetch(runs), {})
        self.assertEqual(len(self.failures), 1)
        self.assertTrue(self.failures[0][1].endswith("(외 2건)"))

    def test_budget_exhaustion_stops_the_lookups_and_is_reported(self):
        small = h.FakeGitHub(max_calls=2)
        failures = []
        runs = [h.make_approval_run(100 + n, branch=f"ai/claude/B{n}") for n in range(5)]
        self.assertEqual(oi.fetch_approval_prs(small, runs, h.REPO, failures), {})
        self.assertEqual(small.calls, 2)
        self.assertEqual(len(failures), 1)
        self.assertIn("상한", failures[0][1])

    def test_a_response_that_is_not_a_list_is_a_failure_not_a_state(self):
        class Odd(h.FakeGitHub):
            def get(self, path, **params):
                self._enter("GET", path, params)
                return {"message": "oops"}
        odd, failures = Odd(), []
        self.assertEqual(oi.fetch_approval_prs(odd, [h.make_approval_run(1, branch="ai/claude/B")], h.REPO, failures), {})
        self.assertEqual(failures, [("approval_prs", "ai/claude/B: 응답이 목록이 아닙니다")])

    def test_at_most_ten_branches_are_asked_and_the_rest_stay_unknown(self):
        runs = [h.make_approval_run(100 + n, branch=f"ai/claude/B{n:02d}") for n in range(14)]
        self.fake.history_pulls = [h.make_history_pull(n, f"ai/claude/B{n:02d}", "closed", True) for n in range(14)]
        states = self.fetch(runs)
        self.assertEqual(len(self.gets()), oi.MAX_APPROVAL_LOOKUPS)
        self.assertEqual(sorted(states), [f"ai/claude/B{n:02d}" for n in range(oi.MAX_APPROVAL_LOOKUPS)])
        self.assertEqual(oi.MAX_APPROVAL_LOOKUPS, 10)

    def test_branch_names_that_look_odd_are_never_asked(self):
        names = [None, "", "a b", "a:b", "a?b", "a#b", "/start", "-start", "x" * 201, 5, ["x"], "ai/claude/ok"]
        runs = [dict(h.make_approval_run(100 + n), head_branch=name) for n, name in enumerate(names)]
        self.fetch(runs)
        self.assertEqual([params["head"] for _path, params in self.gets()], ["octo:ai/claude/ok"])

    def test_the_owner_part_is_the_repository_owner(self):
        oi.fetch_approval_prs(self.fake, [h.make_approval_run(1, branch="ai/claude/B")], "someone/blog", self.failures)
        self.assertEqual(self.gets()[0][1]["head"], "someone:ai/claude/B")

    def test_the_answer_is_checked_against_the_branch_so_a_chatty_server_cannot_hide_a_run(self):
        self.fake.history_pulls = [h.make_history_pull(1, "ai/claude/other", "closed", True)]          # 가짜가 head 로 거르지 않아도(다른 가지의 PR 만 와도)
        class Chatty(h.FakeGitHub):
            def get(self, path, **params):
                self._enter("GET", path, params)
                return [h.make_history_pull(1, "ai/claude/other", "closed", True)]
        chatty, failures = Chatty(), []
        self.assertEqual(oi.fetch_approval_prs(chatty, [h.make_approval_run(1, branch="ai/claude/B")], h.REPO, failures), {})


class BranchHeadsTest(unittest.TestCase):
    """D2(D-281): 같은 응답에서 병합됐거나 닫힌 PR 들의 head 커밋을 모은다 — 승인 대기 실행의 커밋이 그중 하나일 때만 모음이 그 실행을 뺀다."""
    BRANCH = "ai/claude/M029-a"

    def heads(self, *prs, repo=h.REPO):
        return oi.branch_pr_heads(list(prs), self.BRANCH, repo)

    def test_only_closed_pull_requests_of_that_branch_and_repository_count(self):
        merged = h.make_history_pull(1, self.BRANCH, "closed", True, sha="a" * 40)
        closed = h.make_history_pull(2, self.BRANCH, "closed", False, sha="b" * 40)
        opened = h.make_history_pull(3, self.BRANCH, "open", sha="c" * 40)
        other = h.make_history_pull(4, "ai/claude/other", "closed", True, sha="d" * 40)
        fork = h.make_history_pull(5, self.BRANCH, "closed", True, repo="stranger/blog", sha="e" * 40)
        self.assertEqual(self.heads(merged, closed, opened, other, fork), frozenset({"a" * 40, "b" * 40}))
        self.assertEqual(self.heads(opened), frozenset())

    def test_the_commit_is_lower_cased_and_must_be_a_real_full_commit(self):
        self.assertEqual(self.heads(h.make_history_pull(1, self.BRANCH, "closed", True, sha="A" * 40)), frozenset({"a" * 40}))
        for sha in (None, "", "a" * 39, "g" * 40, 5, "a" * 41):
            odd = dict(h.make_history_pull(1, self.BRANCH, "closed", True), head={"ref": self.BRANCH, "sha": sha, "repo": {"full_name": h.REPO}})
            self.assertEqual(self.heads(odd), frozenset(), repr(sha))

    def test_odd_answers_give_an_empty_set(self):
        for junk in (None, "x", 5, {}, [None, "x", 5, {}, []]):
            self.assertEqual(oi.branch_pr_heads(junk, self.BRANCH, h.REPO), frozenset(), repr(junk))
        self.assertEqual(oi.branch_pr_heads([dict(h.make_history_pull(1, self.BRANCH), head="x")], self.BRANCH, h.REPO), frozenset())

    def test_the_state_and_the_heads_read_the_same_pull_requests(self):
        listing = [h.make_history_pull(1, self.BRANCH, "closed", True, sha="a" * 40), h.make_history_pull(2, self.BRANCH, "closed", False, sha="b" * 40)]
        self.assertEqual(oi.branch_pr_state(listing, self.BRANCH, h.REPO), "merged")
        self.assertEqual(oi.branch_pr_heads(listing, self.BRANCH, h.REPO), frozenset({"a" * 40, "b" * 40}))
        self.assertEqual([pr["number"] for pr, _head in oi._branch_pulls(listing, self.BRANCH, h.REPO)], [1, 2])


class FetchApprovalHeadsTest(unittest.TestCase):
    def setUp(self):
        self.fake, self.failures = h.FakeGitHub(), []

    def gets(self):
        return [(path, params) for method, path, params in self.fake.log if method == "GET"]

    def test_the_heads_come_from_the_same_calls_and_only_for_branches_with_a_state(self):
        self.fake.history_pulls = [h.make_history_pull(1, "ai/claude/M029-a", "closed", True, sha="a" * 40), h.make_history_pull(2, "ai/claude/M034-b", "closed", False, sha="b" * 40)]
        self.fake.pulls = [h.make_pull_raw(3, ref="ai/claude/M038-c")]
        runs = [h.make_approval_run(101, branch="ai/claude/M029-a"), h.make_approval_run(103, branch="ai/claude/M034-b"), h.make_approval_run(104, branch="ai/claude/M038-c"),
                h.make_approval_run(105, branch="ai/claude/M099-none")]
        heads = {}
        states = oi.fetch_approval_prs(self.fake, runs, h.REPO, self.failures, heads=heads)
        self.assertEqual(states, {"ai/claude/M029-a": "merged", "ai/claude/M034-b": "closed", "ai/claude/M038-c": "open"})
        self.assertEqual(heads, {"ai/claude/M029-a": frozenset({"a" * 40}), "ai/claude/M034-b": frozenset({"b" * 40}), "ai/claude/M038-c": frozenset()})
        self.assertEqual(len([1 for path, _params in self.gets() if path == "/pulls"]), 4)             # 호출은 늘지 않는다
        self.assertEqual(self.failures, [])

    def test_without_the_heads_argument_the_answer_is_what_it_was(self):
        self.fake.history_pulls = [h.make_history_pull(1, "ai/claude/M029-a", "closed", True)]
        self.assertEqual(oi.fetch_approval_prs(self.fake, [h.make_approval_run(101, branch="ai/claude/M029-a")], h.REPO, self.failures), {"ai/claude/M029-a": "merged"})

    def test_a_failed_lookup_leaves_the_branch_out_of_both(self):
        self.fake.history_pulls = [h.make_history_pull(1, "ai/claude/M034-b", "closed", True, sha="b" * 40)]
        self.fake.fail = [(r"GET /pulls\?.*M029", api_error(500, "HTTP 500: boom"))]
        heads = {}
        states = oi.fetch_approval_prs(self.fake, [h.make_approval_run(101, branch="ai/claude/M029-a"), h.make_approval_run(102, branch="ai/claude/M034-b")], h.REPO, self.failures, heads=heads)
        self.assertEqual((states, heads), ({"ai/claude/M034-b": "merged"}, {"ai/claude/M034-b": frozenset({"b" * 40})}))

    def test_after_the_budget_refuses_the_loop_stops_and_asks_nothing_more(self):
        class Refusing(h.FakeGitHub):
            def get(self, path, **params):
                self._enter("GET", path, params)
                raise oi.ApiBudgetError("GitHub API 호출 상한(2회)에 도달했습니다")
        refusing, failures = Refusing(), []
        runs = [h.make_approval_run(100 + n, branch=f"ai/claude/B{n}") for n in range(5)]
        self.assertEqual(oi.fetch_approval_prs(refusing, runs, h.REPO, failures), {})
        self.assertEqual(len([1 for method, _path, _params in refusing.log if method == "GET"]), 1)           # 첫 거절에서 멈춘다(continue 였다면 다섯 번 묻는다)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][0], "approval_prs")
        self.assertNotIn("외 ", failures[0][1])


# ----------------------------------------------------------------------------
# 정책 파일 읽기
# ----------------------------------------------------------------------------
class ReadPolicyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "pipeline").mkdir()

    def write(self, text, raw=None):
        (self.root / ip.POLICY_FILE).write_bytes(raw if raw is not None else text.encode("utf-8"))

    def test_a_missing_file_is_silent_and_means_the_old_rules(self):
        self.assertEqual(oi.read_policy(self.root), (None, "", ""))
        self.assertEqual(oi.read_policy(self.root / "nowhere"), (None, "", ""))

    def test_the_real_policy_file_is_read(self):
        self.write(REAL_POLICY)
        policy, banner, log = oi.read_policy(self.root)
        self.assertTrue(policy.planned_pause.declared)
        self.assertEqual((banner, log), ("", ""))
        self.assertEqual(oi.read_policy(_bootstrap.ROOT)[0].planned_pause.since, policy.planned_pause.since)

    def test_a_file_that_cannot_be_used_gives_the_old_rules_a_banner_line_and_a_log_line_and_never_raises(self):
        cases = {"깨진 JSON": "{깨짐", "모르는 칸": '{"schema_version": 1, "oops": 1}', "비밀": json.dumps({"schema_version": 1, "_doc": "ghp_" + "a" * 36}),
                 "버전": '{"schema_version": 2}', "배열": "[]", "빈 파일": ""}
        for name, text in cases.items():
            self.write(text)
            policy, banner, log = oi.read_policy(self.root)
            self.assertIsNone(policy, name)
            self.assertTrue(banner.startswith("참고: 정책 파일(pipeline/ops_inbox_policy.json)을 읽지 못했어요 — 이번 점검은 운영자 결정 없이 예전 규칙으로 표시합니다("), name)
            self.assertTrue(log.startswith("[참고] 정책 파일을 읽지 못해 운영자 결정 없이 예전 규칙으로 표시합니다: "), name)
            self.assertNotIn("ghp_", banner + log)

    def test_a_file_that_is_not_text_or_is_too_big_or_is_a_folder_is_handled(self):
        self.write("", raw=b"\xff\xfe\x00{")
        self.assertIsNone(oi.read_policy(self.root)[0])
        self.assertIn("읽지 못했어요", oi.read_policy(self.root)[1])
        self.write("", raw=b" " * (ip.MAX_POLICY_BYTES + 1) + b'{"schema_version": 1}')
        self.assertIn("읽지 못했어요", oi.read_policy(self.root)[1])
        target = self.root / ip.POLICY_FILE
        target.unlink()
        target.mkdir()
        self.assertEqual(oi.read_policy(self.root), (None, "", ""))                          # 폴더는 '파일이 없다'와 같다

    def test_a_key_text_from_the_file_that_the_reason_repeats_is_neutralised_in_the_banner_and_the_log(self):
        self.write(json.dumps({"schema_version": 1, "item_decisions": {"draft:<b>x</b> [a](b)": {"decision": "keep", "date": "2026-11-11", "reason": "사유"}}}))
        _policy, banner, log = oi.read_policy(self.root)
        self.assertIn("항목 키 모양이 올바르지 않습니다", banner)
        for text in (banner, log):
            self.assertNotIn("<b>", text)
            self.assertNotIn("[a]", text)

    def test_deep_nesting_a_repeated_field_and_a_future_date_give_the_old_rules(self):
        pause = json.loads(REAL_POLICY)["planned_pause"]
        cases = {"깊은 중첩": ("[" * 30000 + "]" * 30000, None, "너무 깊게 중첩"), "중복 칸": ('{"schema_version": 1, "schema_version": 1}', None, "같은 칸이 두 번"),
                 "미래 시작일": (json.dumps({"schema_version": 1, "planned_pause": dict(pause, since="2026-11-12")}), date(2026, 11, 11), "오늘(2026-11-11)보다 뒤의 날짜")}
        for name, (text, today, word) in cases.items():
            self.write(text)
            policy, banner, log = oi.read_policy(self.root, today)
            self.assertIsNone(policy, name)
            self.assertIn(word, banner, name)
            self.assertIn(word, log, name)

    def test_the_policy_is_read_with_the_day_it_is_given(self):
        self.write(REAL_POLICY)
        self.assertIsNotNone(oi.read_policy(self.root, date(2026, 11, 11))[0])
        self.assertIsNotNone(oi.read_policy(self.root)[0])                                    # 날짜를 안 주면 미래 날짜를 거르지 않는다
        policy, banner, _log = oi.read_policy(self.root, date(2026, 11, 8))
        self.assertIsNone(policy)
        self.assertIn("planned_pause.since", banner)

    def test_a_parser_that_runs_out_of_stack_or_memory_still_gives_the_old_rules(self):
        self.write(REAL_POLICY)
        for error in (RecursionError, MemoryError):
            with mock.patch.object(ip, "parse_policy_text", side_effect=error()):
                policy, banner, log = oi.read_policy(self.root)
            self.assertIsNone(policy, error.__name__)
            self.assertIn(f"파일을 읽지 못했습니다({error.__name__})", banner)
            self.assertIn(f"파일을 읽지 못했습니다({error.__name__})", log)

    def test_the_banner_reason_is_short_neutralised_and_never_the_file_content(self):
        self.write(json.dumps({"schema_version": 1, "item_decisions": {"draft:1": {"decision": "keep", "date": "2026-11-11", "reason": "<b>@누구</b>"}}}))
        _policy, banner, log = oi.read_policy(self.root)
        self.assertNotIn("<b>", banner + log)
        self.assertLessEqual(len(banner), 330)


# ----------------------------------------------------------------------------
# 전체 실행
# ----------------------------------------------------------------------------
ALLOWED_WRITES = (("POST", re.compile(r"^/labels$")), ("POST", re.compile(r"^/issues$")), ("POST", re.compile(r"^/issues/\d+/comments$")), ("PATCH", re.compile(r"^/issues/\d+$")))


class RunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.summary = self.tmp / "summary.md"
        self.out = []

    def world(self, policy_text=REAL_POLICY, merged=True):
        """2026-11-11 11:16 의 모음 상태: 승인 대기 넷(가지의 PR 은 모두 병합됨)·네이버 초안 둘·Blogger 초안 둘·정지."""
        files = {"blogger_history.json": repro.histories()["blogger_macat"], "blogger_ko_history.json": repro.histories()["blogger_kcyoon"], "history.json": repro.histories()["chance"],
                 "naver_history.json": []}
        registry = json.dumps({"schema_version": 1, "defaults": {"mode": "draft"}, "blogs": [
            {"key": b["key"], "name": b["name"], "platform": b["platform"], "mode": b["mode"], "channel": b["channel"], "url": b.get("url", ""),
             "state": b["state"], "secrets": {"llm_api_key": "GEMINI_API_KEY"}} for b in repro.blogs()]}, ensure_ascii=False)
        root = h.make_root(self.tmp / "repo", histories=files, blogs_json=registry, workflows={"pr-scope-check.yml": 'name: "[공통] PR 변경 범위 검사"\n', "chanceblog.yml": "name: x\n"})
        if policy_text is not None:
            (root / "pipeline" / "ops_inbox_policy.json").write_text(policy_text, encoding="utf-8")
        fake = h.FakeGitHub()
        fake.issues = [h.make_draft_raw(number, title, "네이버", created=repro.iso(*when)) for number, title, when in repro.NAVER_DRAFTS]
        fake.approvals = repro.approval_runs(h.REPO)
        if merged:
            fake.history_pulls = [h.make_history_pull(160 + n, run[1], "closed", True, sha=run[2] + "0" * 33) for n, run in enumerate(repro.APPROVALS)]
        fake.runs = {"chanceblog.yml": [h.make_run(1, ago(hours=3))], "pr-scope-check.yml": []}
        return fake, root

    def run_script(self, fake, root, paused=True, feed=None, env=None):
        environ = dict(ENV, GITHUB_STEP_SUMMARY=str(self.summary), **({"PIPELINE_PAUSE": "true"} if paused else {}), **(env or {}))
        fetch = feed if feed is not None else (lambda url: frozenset({"1"}))
        return oi.run(environ, fake, repro.NOW, root, self.out.append, sleep=lambda seconds: None, feed_fetcher=fetch)

    def issue(self, fake):
        return [i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE][0]

    def counts_line(self):
        return next(line for line in self.out if line.startswith("[점검]"))

    def test_the_real_case_leaves_nothing_to_do_and_names_every_decision(self):
        fake, root = self.world()
        self.assertEqual(self.run_script(fake, root), 0)
        body = self.issue(fake)["body"]
        self.assertIn("**지금 해야 할 일 0건** · 확인하면 좋은 것 2건 · 참고 ", body)
        self.assertNotIn("## 지금 해야 할 일", body)
        for gone in ("승인 대기(Approve and run)", "자동 발행이 멈춰 있습니다", "게시 대기", "PR #176"):
            self.assertNotIn(gone, body, gone)
        for shown in ("폐기 후 닫기 권장(운영자 결정) — 봄맞이 대청소", "폐기 후 닫기 권장(운영자 결정) — 가을 여행 전", "참고: 계획된 일시정지", "Blogger (macat0722): 초안 1건 유지 — 운영자 결정(2026-11-11)",
                      "Blogger (kcyoon): 초안 1건 유지 — 운영자 결정(2026-11-11)", "네이버 (계절·생활 팁): 정지 중(mode=off)", "2 (정지 전 초안)", "Blogger 영문 | 1 (정지 전 초안)"):
            self.assertIn(shown, body, shown)
        self.assertEqual(fake.comments, {})                                                   # 새로 해야 할 일이 없으니 코멘트도 없다
        self.assertIn("지금 해야 할 일 0건 · 확인하면 좋은 것 2건", self.counts_line())
        self.assertTrue(any("병합됐거나 닫힌 가지의 오래된 승인 대기 실행 4건은 모음에서 뺐습니다(PR 상태를 알아낸 가지 4개)" in line for line in self.out))
        for word in ("게시하세요", "발행하세요", "병합하면 공개"):
            self.assertNotIn(word, body)

    def test_the_four_branch_lookups_are_the_only_new_reads_and_nothing_else_is_written(self):
        fake, root = self.world()
        self.run_script(fake, root)
        pulls_by_head = [params for method, path, params in fake.log if method == "GET" and path == "/pulls" and "head" in params]
        self.assertEqual(len(pulls_by_head), 4)
        for kind, path, _payload in fake.writes():
            self.assertTrue(any(kind == k and pattern.fullmatch(path) for k, pattern in ALLOWED_WRITES), (kind, path))
        self.assertLessEqual({method for method, _path, _p in fake.log}, {"GET", "POST", "PATCH"})
        self.assertEqual([i["number"] for i in fake.issues if i["state"] != "open"], [])         # 이슈를 닫지 않았다
        for number in (88, 103):
            draft = fake.find(number)
            self.assertEqual([label["name"] for label in draft["labels"]], ["초안", "채널:네이버"])     # 초안에 라벨을 붙이지 않았다
            self.assertEqual(draft["state"], "open")
            self.assertEqual(draft["title"], dict((n, t) for n, t, _w in repro.NAVER_DRAFTS)[number])
        self.assertNotIn(88, fake.comments)

    def test_when_the_lookups_fail_the_waiting_runs_show_as_before_and_the_failure_is_visible(self):
        fake, root = self.world(policy_text=None)
        fake.fail = [(r"GET /pulls\?.*head=", api_error(502, "HTTP 502: Bad Gateway"))]
        self.assertEqual(self.run_script(fake, root, paused=False), 0)
        body = self.issue(fake)["body"]
        self.assertIn("조회 실패 — 승인 대기 실행의 PR 상태(가지 이름으로 조회)", body)
        self.assertIn("HTTP 502", body)
        self.assertEqual(body.count("승인 대기(Approve and run)"), 4)                         # 확인하지 못한 승인 대기를 숨기지 않는다
        self.assertEqual(len(fake.comments[self.issue(fake)["number"]]), 1)                     # 새 해야 할 일이니 알린다(안전한 쪽)

    def test_the_operators_ignore_decisions_still_hide_their_four_commits_when_the_lookups_fail(self):
        fake, root = self.world()
        fake.fail = [(r"GET /pulls\?.*head=", api_error(502, "HTTP 502: Bad Gateway"))]
        self.assertEqual(self.run_script(fake, root), 0)
        body = self.issue(fake)["body"]
        self.assertIn("조회 실패 — 승인 대기 실행의 PR 상태(가지 이름으로 조회)", body)
        self.assertNotIn("승인 대기(Approve and run)", body)                                  # 운영자가 이미 무시하기로 한 커밋 넷은 조회와 상관없이 숨는다
        self.assertEqual(fake.comments, {})

    def test_unverified_waiting_runs_are_never_hidden_without_a_decision(self):
        fake, root = self.world(policy_text=None)
        fake.history_pulls = []
        self.assertEqual(self.run_script(fake, root, paused=False), 0)
        body = self.issue(fake)["body"]
        self.assertEqual(body.count("승인 대기(Approve and run)"), 4)
        self.assertIn("**지금 해야 할 일 4건**", body.split("\n")[2])
        self.assertTrue(fake.comments[self.issue(fake)["number"]][0].startswith("@octo 새로 해야 할 일이 4건"))
        self.assertFalse(any("뺐습니다" in line for line in self.out))

    def test_a_branch_that_still_has_an_open_pull_request_keeps_its_waiting_run(self):
        fake, root = self.world(policy_text=None)
        fake.history_pulls = [h.make_history_pull(160 + n, run[1], "closed", True, sha=run[2] + "0" * 33) for n, run in enumerate(repro.APPROVALS[:3])]
        fake.pulls = [h.make_pull_raw(170, ref=repro.APPROVALS[3][1])]
        fake.details = {170: {"mergeable": True, "mergeable_state": "clean", "state": "open"}}
        self.run_script(fake, root, paused=False)
        body = self.issue(fake)["body"]
        self.assertEqual(body.count("승인 대기(Approve and run)"), 1)
        self.assertIn("M048", body)

    def test_a_merged_pull_request_that_the_open_list_still_names_is_dropped_by_its_detail(self):
        fake, root = self.world(policy_text=None)
        fake.approvals, fake.history_pulls = [], []
        fake.pulls = [h.make_pull_raw(repro.MERGED_PULL, ref=repro.MERGED_BRANCH)]
        fake.details = {repro.MERGED_PULL: {"mergeable": None, "mergeable_state": "unknown", "state": "closed", "merged": True}}
        self.run_script(fake, root, paused=False)
        self.assertNotIn("PR #176", self.issue(fake)["body"])

    def test_without_a_policy_file_the_paused_inbox_keeps_the_old_pause_item_and_prints_nothing_new(self):
        fake, root = self.world(policy_text=None)
        self.assertEqual(self.run_script(fake, root), 0)
        body = self.issue(fake)["body"]
        self.assertIn("자동 발행이 멈춰 있습니다 — 해제 방법", body)
        self.assertNotIn("정책 파일", body)
        self.assertFalse(any("정책 파일" in line for line in self.out))
        self.assertNotIn("참고: 계획된 일시정지", body)
        self.assertNotIn("\n> ", body)

    def test_a_broken_policy_file_falls_back_to_the_old_rules_and_says_so_at_the_top(self):
        fake, root = self.world(policy_text='{"schema_version": 1, "planned_pause": {"active": true}}')
        self.assertEqual(self.run_script(fake, root), 0)
        body = self.issue(fake)["body"]
        lines = body.splitlines()
        self.assertEqual(lines[0], "# 확인 필요 모음")
        self.assertTrue(lines[2].startswith("> 참고: 정책 파일(pipeline/ops_inbox_policy.json)을 읽지 못했어요"))
        self.assertIn("자동 발행이 멈춰 있습니다 — 해제 방법", body)                            # 예전 규칙: 정지 안내가 지금 해야 할 일
        self.assertIn("planned_pause.since", lines[2])
        self.assertTrue(any(line.startswith("[참고] 정책 파일을 읽지 못해") for line in self.out))
        self.assertTrue(self.summary_text().startswith("# 확인 필요 모음\n\n> 참고: 정책 파일"))
        self.assertEqual(self.out[0][:4], "[점검]")                                           # 로그 첫 줄은 그대로

    def summary_text(self):
        return self.summary.read_text(encoding="utf-8") if self.summary.exists() else ""

    def test_the_same_inputs_the_second_time_write_nothing(self):
        fake, root = self.world()
        self.run_script(fake, root)
        writes = len(fake.writes())
        self.assertEqual(self.run_script(fake, root), 0)
        self.assertEqual(len(fake.writes()), writes)
        self.assertIn("변경 없음", self.summary_text())

    def test_an_old_marker_from_before_the_cleanup_is_updated_without_a_comment(self):
        fake, root = self.world()
        old = ("approve:7f2dfdf,approve:8076dcf,approve:87fc678,approve:b27b3fb,blogger:blogger_kcyoon:drafts:202611081938,"
               "blogger:blogger_macat:drafts:202611081745,pause,pr:176:ready")
        fake.issues.append(h.make_issue(22, inbox.ISSUE_TITLE, f"# 옛 본문\n\n<!-- ops-inbox:hash=dcfd8c0d1aa25678;items={old} -->\n", labels=(inbox.LABEL,)))
        self.assertEqual(self.run_script(fake, root), 0)
        self.assertEqual(fake.comments, {})
        issue = fake.find(22)
        self.assertEqual(issue["state"], "open")
        self.assertIn("**지금 해야 할 일 0건**", issue["body"])
        marker = inbox.parse_marker(issue["body"])
        self.assertEqual(marker.items, ())

    def test_a_closed_inbox_issue_stays_closed_because_nothing_new_needs_doing(self):
        fake, root = self.world()
        old = "approve:7f2dfdf,pause,pr:176:ready"
        fake.issues.append(h.make_issue(22, inbox.ISSUE_TITLE, f"# 옛 본문\n\n<!-- ops-inbox:hash=aaaaaaaaaaaaaaaa;items={old} -->\n", state="closed", labels=(inbox.LABEL,)))
        self.run_script(fake, root)
        self.assertEqual(fake.find(22)["state"], "closed")
        self.assertEqual(fake.comments, {})

    def test_when_the_gate_flag_is_set_the_resume_approval_is_announced_exactly_once(self):
        gate = json.loads(REAL_POLICY)
        gate["planned_pause"]["resume_gate_passed"] = True
        fake, root = self.world(policy_text=json.dumps(gate, ensure_ascii=False))
        self.assertEqual(self.run_script(fake, root), 0)
        number = self.issue(fake)["number"]
        self.assertEqual(len(fake.comments[number]), 1)
        self.assertIn("재개 승인 필요", fake.comments[number][0])
        self.assertEqual(self.run_script(fake, root), 0)
        self.assertEqual(len(fake.comments[number]), 1)

    def test_a_run_whose_commit_is_not_the_finished_pull_requests_commit_still_shows(self):
        fake, root = self.world(policy_text=None)
        runs = repro.approval_runs(h.REPO)
        runs[3] = dict(runs[3], head_sha="9" * 40)                                           # M048 가지에 병합 뒤 새 커밋이 올라와 승인을 기다린다
        fake.approvals = runs
        self.run_script(fake, root, paused=False)
        body = self.issue(fake)["body"]
        self.assertEqual(body.count("승인 대기(Approve and run)"), 1)
        self.assertIn("M048", body)
        self.assertTrue(any("승인 대기 실행 3건은 모음에서 뺐습니다(PR 상태를 알아낸 가지 4개)" in line for line in self.out))

    def test_a_run_from_a_fork_with_a_merged_branchs_name_still_shows_and_is_not_counted(self):
        fake, root = self.world(policy_text=None)
        runs = repro.approval_runs(h.REPO)
        runs[0] = dict(runs[0], head_repository={"full_name": "stranger/blog"})
        fake.approvals = runs
        self.run_script(fake, root, paused=False)
        body = self.issue(fake)["body"]
        self.assertEqual(body.count("승인 대기(Approve and run)"), 1)
        self.assertIn("M029", body)
        self.assertTrue(any("승인 대기 실행 3건은 모음에서 뺐습니다" in line for line in self.out))

    def test_with_the_real_policy_and_the_variable_off_the_inbox_asks_if_it_was_a_mistake_without_an_alert(self):
        fake, root = self.world()
        self.assertEqual(self.run_script(fake, root, paused=False), 0)
        body = self.issue(fake)["body"]
        self.assertIn("정책 파일은 일시정지를 선언했는데 변수 PIPELINE_PAUSE 가 꺼져 있습니다 — 실수로 해제했나요?", body)
        self.assertNotIn("참고: 계획된 일시정지", body)
        self.assertEqual(fake.comments, {})                                                   # 확인 항목이라 코멘트 알림이 없다

    def test_a_pause_older_than_three_weeks_is_flagged_by_the_run_too(self):
        fake, root = self.world()
        environ = dict(ENV, GITHUB_STEP_SUMMARY=str(self.summary), PIPELINE_PAUSE="true")
        late = repro.NOW + timedelta(days=30)
        self.assertEqual(oi.run(environ, fake, late, root, self.out.append, sleep=lambda seconds: None, feed_fetcher=lambda url: frozenset({"1"})), 0)
        body = self.issue(fake)["body"]
        self.assertIn("계획된 일시정지가 길어졌어요 — 재개 조건을 점검하세요", body)
        self.assertIn("참고: 계획된 일시정지", body)
        self.assertEqual(fake.comments, {})

    def test_a_deeply_nested_policy_file_never_stops_the_run(self):
        fake, root = self.world(policy_text="[" * 30000 + "]" * 30000)
        self.assertEqual(self.run_script(fake, root), 0)
        lines = self.issue(fake)["body"].splitlines()
        self.assertTrue(lines[2].startswith("> 참고: 정책 파일(pipeline/ops_inbox_policy.json)을 읽지 못했어요"))
        self.assertIn("너무 깊게 중첩", lines[2])
        self.assertTrue(any(line.startswith("[참고] 정책 파일을 읽지 못해") for line in self.out))

    def test_a_policy_with_a_future_start_date_or_a_repeated_field_is_not_used(self):
        real = json.loads(REAL_POLICY)
        future = json.dumps(dict(real, planned_pause=dict(real["planned_pause"], since="2026-11-12")), ensure_ascii=False)
        repeated = REAL_POLICY.replace('"resume_gate_passed": false', '"resume_gate_passed": false, "resume_gate_passed": false')
        self.assertNotEqual(repeated, REAL_POLICY)
        for name, text in (("미래", future), ("중복", repeated)):
            fake, root = self.world(policy_text=text)
            self.assertEqual(self.run_script(fake, root), 0, name)
            body = self.issue(fake)["body"]
            self.assertTrue(body.splitlines()[2].startswith("> 참고: 정책 파일"), name)
            self.assertIn("자동 발행이 멈춰 있습니다 — 해제 방법", body, name)               # 정책을 쓰지 않으니 예전 규칙으로 돌아간다

    def test_the_pause_variable_being_off_shows_no_pause_item_at_all(self):
        fake, root = self.world()
        self.run_script(fake, root, paused=False)
        body = self.issue(fake)["body"]
        self.assertNotIn("계획된 일시정지", body)
        self.assertNotIn("자동 발행이 멈춰", body)

    def test_a_run_without_waiting_runs_makes_exactly_the_same_reads_as_before(self):
        fake, root = self.world(policy_text=None)
        fake.approvals = []
        self.run_script(fake, root)
        self.assertFalse(any(path == "/pulls" and "head" in params for method, path, params in fake.log))


class WriteScopeStaticTest(unittest.TestCase):
    """쓰기 호출 목록 단언(2026-11-11): 이 스크립트가 쓰는 길은 예전 그대로 네 가지뿐이다 — 새 코드가 다른 이슈·PR·파일·브랜치·변수를 바꾸는 호출을 더하지 못한다."""

    def write_paths(self, rel):
        tree = ast.parse((_bootstrap.ROOT / rel).read_text(encoding="utf-8"))
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("post", "patch", "put", "delete") and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    path = arg.value
                elif isinstance(arg, ast.JoinedStr):
                    path = "".join(part.value if isinstance(part, ast.Constant) else "{}" for part in arg.values)
                else:
                    path = "?"
                found.add(f"{node.func.attr.upper()} {path}")
        return found

    def test_the_script_writes_only_labels_issues_and_issue_comments(self):
        self.assertEqual(self.write_paths("scripts/ops_inbox.py"), {"POST /labels", "POST /issues", "POST /issues/{}/comments", "PATCH /issues/{}"})

    def test_the_rule_modules_never_call_a_client_at_all(self):
        for rel in ("pipeline/inbox.py", "pipeline/inbox_policy.py"):
            self.assertEqual(self.write_paths(rel), set(), rel)

    def test_the_rule_modules_do_not_touch_files_the_network_or_processes(self):
        for rel, allowed in (("pipeline/inbox_policy.py", {"calendar", "json", "re", "dataclasses", "datetime", "typing", "pipeline"}),
                             ("pipeline/inbox.py", {"hashlib", "re", "urllib", "dataclasses", "datetime", "typing", "pipeline"})):
            tree = ast.parse((_bootstrap.ROOT / rel).read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported |= {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    imported.add((node.module or "").split(".")[0])
            self.assertLessEqual(imported, allowed, (rel, sorted(imported - allowed)))
            calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
            self.assertFalse(calls & {"open", "print", "exec", "eval", "input", "__import__"}, (rel, calls & {"open", "print", "exec", "eval", "input", "__import__"}))
            attrs = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
            self.assertFalse(attrs & {"write", "write_text", "write_bytes", "mkdir", "unlink", "rmdir", "rename", "urlopen", "run", "Popen", "system"}, (rel, attrs))

    def test_the_policy_module_reads_no_clock_and_urllib_in_the_rules_is_only_the_link_encoder(self):
        tree = ast.parse((_bootstrap.ROOT / "pipeline" / "inbox_policy.py").read_text(encoding="utf-8"))
        clock = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)} & {"now", "utcnow", "today", "time", "monotonic", "random", "randint", "choice"}
        self.assertEqual(clock, set())                                                       # 시각은 늘 인자다
        source = (_bootstrap.ROOT / "pipeline" / "inbox.py").read_text(encoding="utf-8")
        self.assertEqual(sorted(set(re.findall(r"urllib\.[a-z]+\.[a-z_]+", source))), ["urllib.parse.quote_plus"])


if __name__ == "__main__":
    unittest.main()
