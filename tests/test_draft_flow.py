"""Chance 승인 흐름의 실행부(pipeline/draft_flow.py) 시험. 네트워크 없이 돈다. 실제 GitHub 호출·실제 Actions 는 하지 않는다.

두 층으로 나눈다(git 프로세스 하나가 0.3~1초 걸리는 PC가 있다):
- 가짜 git(FakeGit)과 가짜 GitHub 로 판단·실패 처리·정리 규칙을 빠르게 시험한다. 부른 git 명령의 순서와 인자까지 고정한다.
- 실제 git(임시 bare origin + 로컬 clone)은 이야기 하나(ApprovalStoryTest)와 작은 시험 셋(RealPushTest)에만 쓴다. 이야기 하나가 하루를 따라간다:
  ① 첫 틱의 브랜치 push·이력 커밋(저장소 설정이 꺼져 PR 이 거부됨) ② 같은 슬롯 둘째 틱의 DRAFT_PENDING ③ 설정을 켠 뒤 다음 틱이 PR 을 다시 여는 일
  ④ 18시 초안과 슬롯 둘의 독립 ⑤ 두 순서의 병합과 이력이 PR 안에 있었다면 났을 충돌 ⑥ 병합 뒤 ALREADY_PUBLISHED ⑦ 7일 뒤 정리.
  나머지: 이력 push 의 재시도·롤백, 글 이름의 특수 문자. 대기 초안 제목 중복은 test_generator_drafts.py, 소독은 test_drafts.py.
"""
import contextlib
import io
import json
import tempfile
import types
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

import _bootstrap
from draft_helpers import REPO, FakeGit, FakeGitHub, HermeticGit, OriginTemplate, Sandbox, post_text, write_draft
from pipeline import draft_flow, drafts
from pipeline.state import KST
from test_generator_drafts import run_tick
from test_generator_slots import at, candidate

ROOT = _bootstrap.ROOT
BRANCH_9 = "ai/draft/2026-10-28-s9"
BRANCH_18 = "ai/draft/2026-10-28-s18"
KR_9 = "_posts/기술·미래/2026-10-28-KR-090000.md"
EN_9 = "_posts/Technology & Future/2026-10-28-EN-090000.md"
NOW = datetime(2026, 10, 28, 9, 20, tzinfo=KST)
HISTORY_TITLE = "🤖 이력: 초안 제목 (승인 대기)"
DRAFT_TITLE = "🤖 초안: 초안 제목 (승인 대기)"
ENV = {"GITHUB_REPOSITORY": REPO, "GITHUB_REPOSITORY_OWNER": "shine88pc", "GITHUB_TOKEN": "ghs_" + "T" * 36}


# ----------------------------------------------------------------------------
# 가짜 git 으로 보는 올리기(deliver)
# ----------------------------------------------------------------------------
class FakeBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "history.json").write_bytes(b"[]\n")
        self.git = FakeGit(self.root)
        self.gh = FakeGitHub()
        self.out, self.sleeps = [], []
        self.env = dict(ENV)

    def draft(self, **kwargs):
        return write_draft(self.root, **kwargs)

    def deliver(self):
        return draft_flow.deliver(self.git, self.gh, self.env, out=self.out.append, sleep=self.sleeps.append)

    def housekeeping(self, today, skip=()):
        return draft_flow.housekeeping(self.git, self.gh, self.env, today, skip=skip, out=self.out.append, sleep=self.sleeps.append)

    def run_it(self, env=None, flow="pr", client=True):
        with mock.patch.object(drafts, "chance_flow", return_value=flow):
            return draft_flow.run(self.env if env is None else env, git=self.git, client=self.gh if client else None, out=self.out.append,
                                  sleep=self.sleeps.append, now=NOW)

    def log_text(self):
        return "\n".join(self.out)


class DeliverCommandsTest(FakeBase):
    def test_the_git_commands_are_exactly_these_in_this_order(self):
        """부른 명령과 인자를 그대로 고정한다: 글 두 개만 명시한 경로로 추가(`-A`·`.` 아님), 초안 브랜치를 먼저 push 하고 이력을 그다음에,
        강제 push 없음, 이력 커밋은 history.json 만."""
        self.draft()
        result = self.deliver()
        self.assertEqual((result.status, result.code), ("opened", 0))
        self.assertEqual(self.git.calls, [
            ("show", "HEAD:history.json"),
            ("rev-parse", "--abbrev-ref", "HEAD"),
            ("checkout", "-q", "-b", BRANCH_9),
            ("add", "--", KR_9, EN_9),
            ("commit", "-q", "-m", DRAFT_TITLE),
            ("checkout", "-q", "main"),
            ("commit", "-q", "-m", HISTORY_TITLE, "--", "history.json"),
            ("push", "origin", f"refs/heads/{BRANCH_9}:refs/heads/{BRANCH_9}"),
            ("push", "origin", "HEAD:refs/heads/main"),
        ])

    def test_the_pr_goes_from_the_draft_branch_to_the_checked_out_base_branch(self):
        self.draft()
        self.git.branch = "release"
        result = self.deliver()
        pr = self.gh.prs[result.number]
        self.assertEqual((pr["head_ref"], pr["base"]), (BRANCH_9, "release"))
        self.assertIn(("push", "origin", "HEAD:refs/heads/release"), self.git.calls)
        self.assertIn(("checkout", "-q", "release"), self.git.calls)

    def test_title_body_labels_and_the_owner_mention(self):
        self.draft(kr_title="한국어 제목", en_title="English Title")
        result = self.deliver()
        pr = self.gh.prs[result.number]
        self.assertEqual(pr["title"], "[초안][Chance] 한국어 제목 / English Title")
        self.assertTrue(pr["body"].startswith("@shine88pc **승인 대기 초안**입니다."))
        self.assertIn("- 출처: Reuters — [원문 보기](https://www.reuters.com/a)", pr["body"])
        self.assertIn("이 글은 시험용 본문입니다.", pr["body"])                  # 본문은 기준 브랜치로 돌아가기 전에 읽은 실제 글에서 만든다
        self.assertNotIn("발췌할 문단을 찾지 못했습니다", pr["body"])
        self.assertNotIn("미달(확인 필요)", pr["body"])
        self.assertEqual(pr["labels"], ["초안", "채널:Chance"])
        self.assertEqual(sorted(self.gh.labels), ["채널:Chance", "초안"])
        self.assertEqual(self.gh.verbs(), ["create", "label", "label", "add_labels"])
        self.assertEqual((result.number, result.detail, result.title), (41, "", "한국어 제목"))

    def test_the_owner_falls_back_to_the_repository_owner(self):
        self.draft()
        del self.env["GITHUB_REPOSITORY_OWNER"]
        result = self.deliver()
        self.assertTrue(self.gh.prs[result.number]["body"].startswith("@shine88pc "))

    def test_the_log_names_the_branch_and_the_pr_link(self):
        self.draft()
        self.deliver()
        self.assertIn(f"초안 브랜치 {BRANCH_9} 를 main 에서 만듭니다", self.log_text())
        self.assertIn(f"https://github.com/{REPO}/pull/41", self.log_text())

    def test_manual_runs_get_a_time_stamped_branch(self):
        self.draft(slot=None, stamp="091722")
        result = self.deliver()
        self.assertEqual(result.branch, "ai/draft/2026-10-28-m091722")
        self.assertIn(("checkout", "-q", "-b", "ai/draft/2026-10-28-m091722"), self.git.calls)

    def test_only_the_newest_pr_entry_not_already_in_head_is_delivered(self):
        old = {"date": "2026-10-27", "slot": 18, "topic": "어제", "flow": "pr", **drafts.entry_fields("2026-10-27", 18, None, ["_posts/a/KR.md", "_posts/b/EN.md"])}
        self.git.history_head = json.dumps([old])
        (self.root / "history.json").write_bytes(json.dumps([old]).encode("utf-8"))
        self.draft()
        self.assertEqual(self.deliver().branch, BRANCH_9)

    def test_nothing_new_means_nothing_to_deliver_and_no_mutating_git_command(self):
        result = self.deliver()
        self.assertEqual((result.status, result.code, result.branch), ("no_draft", 0, None))
        self.assertEqual(self.git.calls, [("show", "HEAD:history.json")])
        self.assertEqual(self.gh.calls, [])

    def test_an_entry_already_in_head_is_not_delivered_again(self):
        self.draft()
        self.git.history_head = (self.root / "history.json").read_text(encoding="utf-8")
        self.assertEqual(self.deliver().status, "no_draft")

    def test_a_non_pr_entry_is_ignored(self):
        self.draft(extra={"flow": "direct"})
        self.assertEqual(self.deliver().status, "no_draft")
        self.draft(date="2026-10-29", extra={"flow": None})
        self.assertEqual(self.deliver().status, "no_draft")

    def test_an_unreadable_head_history_counts_every_entry_as_new(self):
        self.draft()
        self.git.history_head = "깨진 JSON"
        self.assertEqual(self.deliver().status, "opened")
        self.git.history_head = '{"not": "a list"}'
        self.git.calls.clear()
        self.gh.prs.clear()
        self.assertEqual(self.deliver().status, "opened")

    def test_malformed_entries_are_refused_before_any_git_change(self):
        for bad in ({"branch": "main"}, {"branch": "ai/draft/x"}, {"branch": None}, {"paths": ["_posts/a.md"]}, {"paths": ["x/a.md", "x/b.md"]},
                    {"paths": ["_posts/../a.md", "_posts/b.md"]}, {"paths": None}, {"paths": "x"}, {"paths": [KR_9, KR_9, EN_9]}):
            with self.subTest(bad=bad):
                self.git.calls.clear()
                (self.root / "history.json").write_bytes(b"[]\n")
                self.draft(extra=bad)
                with self.assertRaises(draft_flow.DeliveryError):
                    self.deliver()
                self.assertEqual(self.git.calls, [("show", "HEAD:history.json")])

    def test_missing_post_files_are_refused_before_any_git_change(self):
        self.draft()
        (self.root / KR_9).unlink()
        with self.assertRaises(draft_flow.DeliveryError):
            self.deliver()
        self.assertEqual(self.git.calls, [("show", "HEAD:history.json")])
        self.assertEqual(self.gh.calls, [])

    def test_a_detached_head_is_refused_before_any_branch_is_made(self):
        self.draft()
        self.git.branch = "HEAD"
        with self.assertRaises(draft_flow.DeliveryError):
            self.deliver()
        self.assertEqual(self.git.names(), ["show", "rev-parse"])

    def test_the_branch_commit_message_neutralizes_the_title(self):
        self.draft(kr_title="@evil #123 <b>x</b>")
        self.deliver()
        message = self.git.calls_of("commit")[0][3]
        self.assertNotRegex(message, r"@[A-Za-z]|#\d|<|>")
        self.assertTrue(message.startswith("🤖 초안: "))


class PushFailureTest(FakeBase):
    def test_a_rejected_history_push_is_rebased_and_retried(self):
        self.draft()
        self.git.queue_failure("push-base", 1, "! [rejected] main -> main (fetch first)")
        result = self.deliver()
        self.assertEqual(result.status, "opened")
        self.assertEqual(self.sleeps, [5])
        names = self.git.names()
        self.assertEqual(names.count("pull"), 1)
        self.assertEqual(names.index("pull") > names.index("push"), True)
        self.assertEqual(self.git.calls_of("pull"), [("pull", "--rebase", "origin", "main")])
        self.assertEqual([c for c in self.git.calls if c[0] == "push"].count(("push", "origin", "HEAD:refs/heads/main")), 2)
        self.assertIn("이력 push 가 거절돼 최신 main 위로 다시 쌓습니다(1/3)", self.log_text())

    def test_three_rejections_delete_the_branch_it_just_pushed_and_fail(self):
        """이력 push 가 끝내 안 되면 방금 올린 초안 브랜치를 지운다 — 이력 없는 초안이 남아 같은 슬롯을 또 만들게 하지 않는다."""
        self.draft()
        self.git.queue_failure("push-base", 1, "rejected", times=3)
        with self.assertRaises(draft_flow.GitError):
            self.deliver()
        self.assertEqual(self.sleeps, [5, 10])
        self.assertEqual(self.git.names().count("pull"), 2)
        self.assertEqual(self.git.calls[-1], ("push", "origin", "--delete", BRANCH_9))
        self.assertEqual(self.git.remote, {})
        self.assertEqual(self.gh.calls, [])                                   # PR 은 시도하지도 않았다
        self.assertIn("방금 올린 초안 브랜치를 지웁니다", self.log_text())

    def test_a_failed_rebase_is_aborted_then_the_branch_is_rolled_back(self):
        self.draft()
        self.git.queue_failure("push-base", 1, "rejected")
        self.git.queue_failure("pull", 1, "CONFLICT (content): Merge conflict in history.json")
        with self.assertRaises(draft_flow.GitError):
            self.deliver()
        names = self.git.names()
        self.assertLess(names.index("pull"), names.index("rebase"))
        self.assertEqual(self.git.calls_of("rebase"), [("rebase", "--abort")])
        self.assertEqual(self.git.calls[-1], ("push", "origin", "--delete", BRANCH_9))
        self.assertEqual(self.sleeps, [])

    def test_a_rollback_that_fails_is_reported_but_the_original_error_stands(self):
        self.draft()
        self.git.queue_failure("push-base", 1, "rejected", times=3)
        self.git.queue_failure("push-delete", 1, "remote: denied")
        with self.assertRaises(draft_flow.GitError) as ctx:
            self.deliver()
        self.assertIn("push", str(ctx.exception))
        self.assertIn("초안 브랜치를 지우지 못했습니다(다음 실행이 같은 슬롯을 건너뜁니다)", self.log_text())
        self.assertIn(BRANCH_9, self.git.remote)

    def test_the_branch_push_failing_means_no_history_push_no_rollback_no_pr(self):
        self.draft()
        self.git.queue_failure("push-branch", 1, "! [rejected] (non-fast-forward)")
        with self.assertRaises(draft_flow.GitError):
            self.deliver()
        pushes = self.git.calls_of("push")
        self.assertEqual(pushes, [("push", "origin", f"refs/heads/{BRANCH_9}:refs/heads/{BRANCH_9}")])
        self.assertEqual(self.gh.calls, [])

    def test_the_run_wrapper_turns_these_failures_into_exit_1_with_a_summary(self):
        self.draft()
        self.git.queue_failure("push-base", 1, "rejected", times=3)
        summary = self.root / "summary.md"
        code = self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)})
        self.assertEqual(code, 1)
        self.assertIn("작업 실패: GitError", self.log_text())
        self.assertIn("**실패**", summary.read_text(encoding="utf-8"))

    def test_other_git_failures_before_the_push_also_stop_cleanly(self):
        for key in ("checkout", "add", "commit"):
            with self.subTest(command=key):
                self.git.calls.clear()
                self.git.queue_failure(key, 128, "fatal: boom")
                (self.root / "history.json").write_bytes(b"[]\n")
                self.draft()
                with self.assertRaises(draft_flow.GitError):
                    self.deliver()
                self.assertEqual(self.git.calls_of("push"), [])
                self.assertEqual(self.gh.calls, [])


class PullRequestFailureTest(FakeBase):
    def test_a_403_keeps_the_branch_and_the_history_and_ends_red(self):
        self.draft()
        self.gh.create_errors = [drafts.GitHubError("HTTP 403: GitHub Actions is not permitted to create or approve pull requests.", 403)]
        result = self.deliver()
        self.assertEqual((result.status, result.code, result.number, result.title), ("branch_only", 1, None, "초안 제목"))
        self.assertIn("HTTP 403", result.detail)
        self.assertEqual(self.sleeps, [])                                                   # 403 은 재시도하지 않는다
        self.assertEqual(self.git.calls_of("push")[-1], ("push", "origin", "HEAD:refs/heads/main"))     # 브랜치도 이력도 올라간 뒤다
        self.assertIn(BRANCH_9, self.git.remote)
        self.assertEqual(self.gh.verbs(), ["create"])                                        # 라벨도 붙이지 않는다(PR 이 없다)

    def test_the_summary_tells_the_operator_what_to_do_and_the_run_is_red(self):
        self.draft()
        self.gh.create_errors = [drafts.GitHubError("HTTP 403: nope", 403)]
        summary = self.root / "summary.md"
        code = self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)})
        self.assertEqual(code, 1)
        text = summary.read_text(encoding="utf-8")
        self.assertIn(f"브랜치 `{BRANCH_9}` 가 push 됐고 PR 은 만들지 못했습니다(HTTP 403: nope)", text)
        self.assertIn("Allow GitHub Actions to create and approve pull requests", text)
        self.assertIn("Compare & pull request", text)
        self.assertIn("다음 실행(30분 안)이 PR 을 다시 열어 봅니다", text)
        self.assertIn("만든 글은 잃지 않았습니다", text)
        self.assertEqual([line for line in self.out if line.startswith("::")], [draft_flow.ERROR_PR_FAILED])

    def test_the_error_annotation_is_a_fixed_sentence_without_any_outside_text(self):
        self.assertNotRegex(draft_flow.ERROR_PR_FAILED, r"\{|\}|HTTP|403")
        self.assertNotRegex(draft_flow.WARN_HOUSEKEEPING, r"\{|\}|HTTP|403")
        for name in ("ERROR_PR_FAILED", "WARN_HOUSEKEEPING"):
            self.assertEqual(getattr(draft_flow, name).count("\n"), 0)

    def test_a_hostile_error_message_cannot_reach_a_workflow_command(self):
        self.draft()
        self.gh.create_errors = [drafts.GitHubError("HTTP 500: ::error::가짜\n::set-output name=x::y", 500)] * 3
        summary = self.root / "summary.md"
        self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)})
        for line in self.out:
            self.assertFalse(line.startswith("::") and line not in (draft_flow.ERROR_PR_FAILED, draft_flow.WARN_HOUSEKEEPING), line)
        self.assertNotIn("\n::", summary.read_text(encoding="utf-8"))

    def test_a_5xx_is_retried_and_the_pr_opens(self):
        self.draft()
        self.gh.create_errors = [drafts.GitHubError("HTTP 500", 500), drafts.GitHubError("HTTP 502", 502), None]
        result = self.deliver()
        self.assertEqual((result.status, result.code), ("opened", 0))
        self.assertEqual(self.sleeps, [2, 5])
        self.assertEqual(self.gh.verbs().count("create"), 3)

    def test_a_5xx_that_never_ends_leaves_the_branch_and_fails_after_three_tries(self):
        self.draft()
        self.gh.create_errors = [drafts.GitHubError("HTTP 503", 503)] * 3
        result = self.deliver()
        self.assertEqual((result.status, result.code), ("branch_only", 1))
        self.assertEqual(self.gh.verbs(), ["create"] * 3)
        self.assertEqual(self.sleeps, [2, 5])
        self.assertIn(BRANCH_9, self.git.remote)

    def test_a_network_error_is_retried_too(self):
        self.draft()
        self.gh.create_errors = [drafts.GitHubError("URLError: boom"), None]
        self.assertEqual(self.deliver().status, "opened")

    def test_other_client_errors_are_not_retried(self):
        for status in (401, 404, 422):
            with self.subTest(status=status):
                self.git.calls.clear()
                (self.root / "history.json").write_bytes(b"[]\n")
                self.draft()
                self.gh.calls.clear()
                self.gh.create_errors = [drafts.GitHubError(f"HTTP {status}: x", status)]
                result = self.deliver()
                self.assertEqual((result.status, self.gh.verbs()), ("branch_only", ["create"]))

    def test_an_existing_pr_for_the_branch_is_reused_not_duplicated(self):
        self.draft()
        self.gh.add_pr(7, BRANCH_9)
        result = self.deliver()
        self.assertEqual((result.status, result.number), ("opened", 7))
        self.assertEqual(len(self.gh.prs), 1)
        self.assertEqual(self.gh.verbs()[:2], ["create", "find"])

    def test_a_422_that_is_not_a_duplicate_is_a_failure(self):
        self.draft()
        self.gh.create_errors = [drafts.GitHubError("HTTP 422: Validation Failed", 422)]
        self.assertEqual(self.deliver().status, "branch_only")
        self.assertEqual(self.gh.verbs(), ["create"])

    def test_an_already_exists_answer_with_no_findable_pr_is_a_failure(self):
        self.draft()
        self.gh.create_errors = [drafts.GitHubError("HTTP 422: A pull request already exists", 422)]
        self.assertEqual(self.deliver().status, "branch_only")
        self.assertEqual(self.gh.verbs(), ["create", "find"])

    def test_a_label_failure_does_not_undo_the_pr(self):
        self.draft()
        self.gh.label_error = drafts.GitHubError("HTTP 403", 403)
        result = self.deliver()
        self.assertEqual((result.status, result.code), ("opened", 0))
        self.assertIn("라벨을 붙이지 못했습니다(PR 은 열렸습니다)", self.log_text())

    def test_the_detail_is_a_one_line_clean_text(self):
        self.draft()
        self.gh.create_errors = [drafts.GitHubError("HTTP 403: " + "가" * 500, 403)]
        detail = self.deliver().detail
        self.assertLessEqual(len(detail), 160)
        self.assertNotIn("\n", detail)


# ----------------------------------------------------------------------------
# 정리 규칙(가짜 git)
# ----------------------------------------------------------------------------
class HousekeepingLogicTest(FakeBase):
    def remote(self, *names):
        for name in names:
            self.git.remote[name] = "b" * 40

    def deleted(self):
        return [call[-1] for call in self.git.calls if call[:3] == ("push", "origin", "--delete")]

    def test_a_closed_or_merged_branch_is_deleted_on_the_seventh_day_not_before(self):
        self.remote(BRANCH_9, BRANCH_18)
        self.gh.add_pr(1, BRANCH_9, "closed")
        self.gh.add_pr(2, BRANCH_18, "closed", merged=True)
        self.assertEqual(self.housekeeping(date(2026, 11, 3)), ([], 0))                 # 6일째
        self.assertEqual(self.deleted(), [])
        notes, failures = self.housekeeping(date(2026, 11, 4))                          # 7일째
        self.assertEqual((notes, failures), (["오래된 브랜치 삭제 2건"], 0))
        self.assertEqual(sorted(self.deleted()), [BRANCH_18, BRANCH_9])
        self.assertEqual(self.git.remote, {})
        self.assertIn("병합됨", self.log_text())
        self.assertIn("닫힘", self.log_text())

    def test_a_branch_with_an_open_pr_is_never_deleted_however_old(self):
        self.remote(BRANCH_9)
        self.gh.add_pr(1, BRANCH_9, "open")
        self.assertEqual(self.housekeeping(date(2027, 1, 1)), ([], 0))
        self.assertEqual(self.deleted(), [])

    def test_a_pr_less_old_branch_is_deleted(self):
        self.remote("ai/draft/2026-10-20-s9")
        self.assertEqual(self.housekeeping(date(2026, 10, 28)), (["오래된 브랜치 삭제 1건"], 0))
        self.assertIn("PR 없음", self.log_text())

    def test_branches_that_are_not_ours_are_left_alone(self):
        self.remote("ai/draft/weird", "ai/draft/2026-13-45-s9", "ai/draft/2026-10-20-s99", "ai/draft/2026-10-20-s9-extra")
        self.assertEqual(self.housekeeping(date(2027, 1, 1)), ([], 0))
        self.assertEqual(self.gh.calls, [])                                               # 우리 이름이 없으면 API 도 부르지 않는다
        self.assertEqual(self.deleted(), [])

    def test_a_tick_with_no_draft_branches_makes_no_api_call(self):
        self.assertEqual(self.housekeeping(date(2027, 1, 1)), ([], 0))
        self.assertEqual(self.gh.calls, [])
        self.assertEqual(self.git.calls, [("ls-remote", "--heads", "origin", "refs/heads/ai/draft/*")])

    def test_the_branch_created_this_run_is_skipped(self):
        self.remote(BRANCH_9)
        self.assertEqual(self.housekeeping(date(2027, 1, 1), skip=(BRANCH_9,)), ([], 0))
        self.assertEqual(self.gh.calls, [])

    def test_a_listing_that_fails_deletes_nothing_and_counts_as_a_failure(self):
        self.remote("ai/draft/2026-10-01-s9")
        self.gh.list_error = drafts.GitHubError("HTTP 500", 500)
        self.assertEqual(self.housekeeping(date(2027, 1, 1)), (["정리 시작 실패(다음 실행에서 다시 시도)"], 1))
        self.assertEqual(self.deleted(), [])
        self.assertIn("정리를 시작하지 못했습니다", self.log_text())

    def test_an_unreadable_remote_counts_as_a_failure_not_an_exception(self):
        self.git.queue_failure("ls-remote", 128, "fatal: unable to access")
        self.assertEqual(self.housekeeping(date(2027, 1, 1)), (["정리 시작 실패(다음 실행에서 다시 시도)"], 1))
        self.assertEqual(self.gh.calls, [])

    def test_a_broken_history_file_counts_as_a_failure_not_an_exception(self):
        self.remote(BRANCH_9)
        (self.root / "history.json").write_text("{깨짐", encoding="utf-8")
        self.assertEqual(self.housekeeping(date(2026, 10, 28)), (["정리 시작 실패(다음 실행에서 다시 시도)"], 1))

    def test_a_full_listing_is_not_trusted_to_prove_a_branch_has_no_pr(self):
        self.remote("ai/draft/2026-10-01-s9")
        for number in range(300):
            self.gh.add_pr(1000 + number, "ai/draft/2026-10-%02d-s18" % (number % 28 + 1), "closed")
        self.housekeeping(date(2027, 1, 1))
        self.assertEqual([name for name in self.deleted() if name.endswith("2026-10-01-s9")], [])      # 목록이 가득 차 'PR 없음'을 믿을 수 없다

    def test_an_incomplete_listing_still_cleans_branches_whose_closed_pr_it_shows(self):
        """목록이 끝까지 읽히지 않았어도 닫힌 PR 이 보이는 브랜치는 지울 수 있다(열린 PR 은 같은 브랜치에 하나뿐이고 최신이 먼저 읽힌다)."""
        self.remote("ai/draft/2026-10-01-s9", BRANCH_9)
        self.gh.add_pr(1, BRANCH_9, "closed")
        for number in range(300):
            self.gh.add_pr(1000 + number, "ai/draft/2026-11-%02d-s18" % (number % 28 + 1), "closed")
        self.housekeeping(date(2027, 1, 1))
        self.assertEqual(self.deleted(), [BRANCH_9])                                                    # PR 이 안 보이는 옛 브랜치만 남는다

    def test_a_listing_without_a_completeness_flag_is_treated_as_incomplete(self):
        """알 수 없는 목록(깃발이 없는 일반 리스트)은 완전하다고 믿지 않는다 — 열린 PR 이 안 보일 뿐인데 브랜치를 지우면 PR 이 닫힌다."""
        self.remote("ai/draft/2026-10-01-s9")
        self.gh.list_draft_pull_requests = lambda state="all", max_pages=3: []
        self.housekeeping(date(2027, 1, 1))
        self.assertEqual(self.deleted(), [])

    def test_when_a_branch_has_several_prs_the_open_one_wins(self):
        self.remote(BRANCH_9)
        self.gh.add_pr(1, BRANCH_9, "open")
        self.gh.add_pr(2, BRANCH_9, "closed")
        self.housekeeping(date(2027, 1, 1))
        self.assertEqual(self.deleted(), [])

    def test_when_every_pr_of_a_branch_is_closed_it_is_deleted(self):
        self.remote(BRANCH_9)
        self.gh.add_pr(1, BRANCH_9, "closed")
        self.gh.add_pr(2, BRANCH_9, "closed", merged=True)
        self.housekeeping(date(2027, 1, 1))
        self.assertEqual(self.deleted(), [BRANCH_9])

    def test_one_failed_deletion_does_not_stop_the_others(self):
        self.remote("ai/draft/2026-10-01-s9", "ai/draft/2026-10-02-s9")
        self.gh.add_pr(1, "ai/draft/2026-10-01-s9", "closed")
        self.gh.add_pr(2, "ai/draft/2026-10-02-s9", "closed")
        self.git.queue_failure("push-delete", 1, "denied")
        notes, failures = self.housekeeping(date(2027, 1, 1))
        self.assertEqual(failures, 1)
        self.assertEqual(notes, ["오래된 브랜치 삭제 1건", "정리 실패 1건(다음 실행에서 다시 시도)"])
        self.assertEqual(len(self.deleted()), 2)

    # ---- PR 다시 열기 ----
    def orphan(self, **kwargs):
        entry = self.draft(**kwargs)
        self.remote(entry["branch"])
        self.git.branch_files = {entry["paths"][0]: post_text("한국어 제목"), entry["paths"][1]: post_text("English Title")}
        return entry

    def test_a_pr_less_young_branch_gets_its_pr_back_from_the_branch_contents(self):
        entry = self.orphan(kr_title="한국어 제목", en_title="English Title")
        notes, failures = self.housekeeping(date(2026, 10, 28))
        self.assertEqual((notes, failures), (["PR 다시 열기 1건"], 0))
        pr = self.gh.prs[41]
        self.assertEqual((pr["head_ref"], pr["base"], pr["labels"]), (BRANCH_9, "main", ["초안", "채널:Chance"]))
        self.assertEqual(pr["title"], "[초안][Chance] 한국어 제목 / English Title")
        self.assertIn("- [ ] 원문과 수치·사실을 대조했다", pr["body"])
        self.assertIn("이 글은 시험용 본문입니다.", pr["body"])
        self.assertEqual(self.git.calls_of("fetch"), [("fetch", "--depth=1", "origin", f"refs/heads/{entry['branch']}")])
        self.assertEqual(self.git.calls_of("show")[-2:], [("show", f"FETCH_HEAD:{entry['paths'][0]}"), ("show", f"FETCH_HEAD:{entry['paths'][1]}")])

    def test_a_full_clone_fetches_without_a_depth_limit(self):
        self.git.shallow = False
        entry = self.orphan()
        self.housekeeping(date(2026, 10, 28))
        self.assertEqual(self.git.calls_of("fetch"), [("fetch", "origin", f"refs/heads/{entry['branch']}")])

    def test_the_retry_window_is_three_days_and_the_deletion_starts_on_the_seventh(self):
        self.orphan()
        for today, expected in ((date(2026, 10, 31), 1), (date(2026, 11, 1), 0)):
            self.gh.prs.clear()
            self.housekeeping(today)
            self.assertEqual(len(self.gh.prs), expected, today)
        self.assertEqual(self.deleted(), [])
        self.housekeeping(date(2026, 11, 4))
        self.assertEqual(self.deleted(), [BRANCH_9])

    def test_a_pr_less_branch_without_a_history_entry_is_not_reopened(self):
        self.remote(BRANCH_9)
        self.assertEqual(self.housekeeping(date(2026, 10, 28)), ([], 0))
        self.assertEqual(self.gh.prs, {})
        self.assertIn("이력 항목이 없어 다시 열지 못합니다", self.log_text())

    def test_a_reopen_that_fails_is_counted_and_does_not_stop_the_rest(self):
        self.orphan()
        other = self.draft(slot=18, date="2026-10-28")
        self.remote(other["branch"])
        self.git.branch_files.update({other["paths"][0]: post_text("저녁"), other["paths"][1]: post_text("Evening")})
        self.gh.create_errors = [drafts.GitHubError("HTTP 403", 403)]
        notes, failures = self.housekeeping(date(2026, 10, 28))
        self.assertEqual(failures, 1)
        self.assertEqual(notes, ["PR 다시 열기 1건", "정리 실패 1건(다음 실행에서 다시 시도)"])
        self.assertEqual(len(self.gh.prs), 1)

    def test_a_branch_whose_files_cannot_be_read_counts_as_a_failure(self):
        self.orphan()
        self.git.branch_files = {}
        self.assertEqual(self.housekeeping(date(2026, 10, 28)), (["정리 실패 1건(다음 실행에서 다시 시도)"], 1))

    def test_an_entry_with_broken_paths_is_not_reopened(self):
        entry = self.draft(extra={"paths": ["x", "y"]})
        self.remote(entry["branch"])
        self.assertEqual(self.housekeeping(date(2026, 10, 28)), (["정리 실패 1건(다음 실행에서 다시 시도)"], 1))
        self.assertEqual(self.gh.prs, {})


class RunGuardsTest(FakeBase):
    def test_pause_does_nothing_even_with_a_draft_waiting(self):
        self.draft()
        self.assertEqual(self.run_it({**self.env, "PIPELINE_PAUSE": "true"}), 0)
        self.assertIn("[일시정지]", self.log_text())
        self.assertEqual((self.git.calls, self.gh.calls), ([], []))

    def test_every_pause_spelling_the_other_workflows_accept(self):
        for value in ("1", "true", "yes", "on", "TRUE", " On "):
            self.out.clear()
            self.assertEqual(self.run_it({**self.env, "PIPELINE_PAUSE": value}), 0)
            self.assertIn("[일시정지]", self.log_text(), value)
        self.out.clear()
        self.draft()
        self.run_it({**self.env, "PIPELINE_PAUSE": "false"})
        self.assertNotIn("[일시정지]", self.log_text())

    def test_direct_flow_does_nothing(self):
        self.draft()
        self.assertEqual(self.run_it(flow="direct"), 0)
        self.assertIn("발행 흐름이 direct", self.log_text())
        self.assertEqual((self.git.calls, self.gh.calls), ([], []))

    def test_a_practice_run_writes_nothing(self):
        self.draft()
        for value in ("1", "true", "yes", "on"):
            self.out.clear()
            self.assertEqual(self.run_it({**self.env, "DRY_RUN": value}), 0)
            self.assertIn("[DRY_RUN]", self.log_text())
        self.assertEqual((self.git.calls, self.gh.calls), ([], []))
        self.run_it({**self.env, "DRY_RUN": "0"})
        self.assertTrue(self.git.calls)                                                # 0 은 연습이 아니다

    def test_without_a_token_or_repository_nothing_is_pushed(self):
        self.draft()
        for env in ({}, {"GITHUB_TOKEN": "x" * 10}, {"GITHUB_REPOSITORY": REPO}, {"GITHUB_TOKEN": "x", "GITHUB_REPOSITORY": "not a repo"},
                    {"GITHUB_TOKEN": "  ", "GITHUB_REPOSITORY": REPO}):
            self.out.clear()
            self.assertEqual(self.run_it(env, client=False), 0)
            self.assertIn("[로컬]", self.log_text())
        self.assertEqual(self.git.calls, [])

    def test_a_broken_registry_stops_the_run(self):
        with mock.patch.object(drafts, "chance_flow", side_effect=drafts.DraftFlowError("깨짐")):
            with self.assertRaises(drafts.DraftFlowError):
                draft_flow.run(self.env, git=self.git, client=self.gh, out=self.out.append, now=NOW)

    def test_a_clean_run_writes_the_summary_block_with_the_pr_link(self):
        self.draft()
        summary = self.root / "summary.md"
        self.assertEqual(self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)}), 0)
        text = summary.read_text(encoding="utf-8")
        self.assertIn("### Chance 초안 승인 흐름", text)
        self.assertIn("**DRAFT_OPENED**", text)
        self.assertIn(f"https://github.com/{REPO}/pull/41 · 브랜치 `{BRANCH_9}`", text)
        self.assertIn("- 제목: 초안 제목", text)
        self.assertIn("병합하면 공개, 닫으면 폐기", text)

    def test_housekeeping_notes_reach_the_summary(self):
        self.draft(date="2026-10-20")
        self.git.remote["ai/draft/2026-10-20-s9"] = "b" * 40
        self.draft()
        summary = self.root / "summary.md"
        self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)})
        self.assertIn("- 정리: 오래된 브랜치 삭제 1건", summary.read_text(encoding="utf-8"))

    def test_a_run_with_nothing_to_deliver_says_so_and_still_housekeeps(self):
        self.git.remote["ai/draft/2026-10-01-s9"] = "b" * 40
        summary = self.root / "summary.md"
        self.assertEqual(self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)}), 0)
        text = summary.read_text(encoding="utf-8")
        self.assertIn("**NO_DRAFT**", text)
        self.assertIn("오래된 브랜치 삭제 1건", text)

    def test_a_retry_that_fails_again_is_a_warning_not_a_red_run(self):
        entry = self.draft()
        self.git.remote[entry["branch"]] = "b" * 40
        self.git.branch_files = {entry["paths"][0]: post_text("가"), entry["paths"][1]: post_text("나")}
        (self.root / "history.json").write_text(json.dumps([entry], ensure_ascii=False), encoding="utf-8")
        self.git.history_head = json.dumps([entry], ensure_ascii=False)          # 이번 실행이 만든 새 초안은 없다
        self.gh.create_errors = [drafts.GitHubError("HTTP 403", 403)]
        summary = self.root / "summary.md"
        code = self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)})
        self.assertEqual(code, 0)
        self.assertIn(draft_flow.WARN_HOUSEKEEPING, self.out)
        self.assertIn("정리 실패 1건", summary.read_text(encoding="utf-8"))

    def test_an_unexpected_error_in_the_cleanup_does_not_hide_the_delivery_result(self):
        self.draft()
        summary = self.root / "summary.md"
        with mock.patch.object(draft_flow, "housekeeping", side_effect=KeyError("깨짐")):
            code = self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)})
        self.assertEqual(code, 0)                                                       # 초안은 올라갔고 PR 도 열렸다
        self.assertIn("정리 중 예상 밖 오류: KeyError", self.log_text())
        self.assertIn(draft_flow.WARN_HOUSEKEEPING, self.out)
        text = summary.read_text(encoding="utf-8")
        self.assertIn("**DRAFT_OPENED**", text)
        self.assertIn("정리 중 예상 밖 오류", text)

    def test_the_cli_commands(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch.object(drafts, "chance_flow", return_value="pr"):
            self.assertEqual(draft_flow.main(["flow"]), 0)
        self.assertEqual(buf.getvalue().strip(), "pr")
        with contextlib.redirect_stderr(io.StringIO()) as err, mock.patch.object(drafts, "chance_flow", side_effect=drafts.DraftFlowError("깨짐")):
            self.assertEqual(draft_flow.main(["flow"]), 1)
        self.assertIn("[오류] 깨짐", err.getvalue())
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(draft_flow.main([]), 2)
            self.assertEqual(draft_flow.main(["nope"]), 2)
        self.assertIn("사용법", err.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as out, mock.patch.object(drafts, "chance_flow", side_effect=drafts.DraftFlowError("깨짐")):
            self.assertEqual(draft_flow.main(["deliver"]), 1)
        self.assertIn("[오류] 깨짐", out.getvalue())


class RemoteBranchLogicTest(FakeBase):
    def test_exists_true_false_and_unknown(self):
        self.git.remote[BRANCH_9] = "b" * 40
        self.assertTrue(draft_flow.remote_branch_exists(BRANCH_9, self.git))
        self.assertFalse(draft_flow.remote_branch_exists(BRANCH_18, self.git))
        self.assertFalse(draft_flow.remote_branch_exists("ai/draft/2026-10-28", self.git))
        out = []
        self.git.queue_failure("ls-remote", 128, "fatal: unable to access 'https://x/'")
        self.assertIsNone(draft_flow.remote_branch_exists(BRANCH_9, self.git, out=out.append))
        self.assertEqual(out[0], "::warning::초안 브랜치를 확인하지 못했습니다(이번 실행은 건너뛰고 다음 실행에서 다시 확인합니다).")
        self.assertIn("브랜치 확인 실패", out[1])

    def test_malformed_ls_remote_lines_are_ignored(self):
        """ls-remote 가 이상한 줄(해시가 아닌 앞부분·refs/heads 가 아닌 이름·빈 줄)을 섞어 줘도 올바른 줄만 브랜치로 읽는다."""
        reply = types.SimpleNamespace(returncode=0, stderr="", stdout=(f"{'b' * 40}\trefs/heads/{BRANCH_9}\nnot-a-sha\trefs/heads/{BRANCH_18}\n"
                                                                         f"{'c' * 40}\trefs/tags/v1\n\ngarbage\n{'d' * 64}\trefs/heads/ai/draft/2026-10-29-s9\n"))
        with mock.patch.object(self.git, "run", return_value=reply):
            self.assertEqual(draft_flow.ls_remote_drafts(self.git), {BRANCH_9: "b" * 40, "ai/draft/2026-10-29-s9": "d" * 64})

    def test_the_exact_ref_is_compared_not_a_suffix(self):
        """ls-remote 가 꼬리만 같은 다른 브랜치까지 돌려줘도 정확히 같은 이름일 때만 있다고 본다."""
        reply = types.SimpleNamespace(returncode=0, stdout=f"{'b' * 40}\trefs/heads/x/{BRANCH_9}\n{'c' * 40}\trefs/heads/{BRANCH_9}-2\n", stderr="")
        with mock.patch.object(self.git, "run", return_value=reply):
            self.assertFalse(draft_flow.remote_branch_exists(BRANCH_9, self.git))
        reply.stdout += f"{'d' * 40}\trefs/heads/{BRANCH_9}\n"
        with mock.patch.object(self.git, "run", return_value=reply):
            self.assertTrue(draft_flow.remote_branch_exists(BRANCH_9, self.git))


# ----------------------------------------------------------------------------
# 실제 git 이야기: 하루가 흘러가는 순서대로 한 저장소(임시 bare origin)에서
# ----------------------------------------------------------------------------
class ApprovalStoryTest(unittest.TestCase):
    """09시 초안(그날은 저장소 설정이 꺼져 PR 열기가 거부됨) → 30분 뒤 틱(같은 슬롯 DRAFT_PENDING, 설정을 켠 뒤 PR 다시 열기) → 18시 초안(PR 열림)
    → 두 PR 을 두 순서로 병합 → 병합 뒤 틱(ALREADY_PUBLISHED) → 7일 뒤 정리. 실제 git 과 실제 생성기(가짜 소스·가짜 Gemini)를 쓴다.
    git 프로세스 하나가 1초 가까이 걸리는 PC 가 있어서 이야기 하나를 클래스 하나로 만들고(setUpClass 에서 한 번), 질의는 git 한 번에 묶어서 한다."""

    @classmethod
    def setUpClass(cls):
        cls.template = OriginTemplate()
        cls.box = box = Sandbox(cls.template)
        cls.gh = gh = FakeGitHub()
        cls.out, cls.sleeps, cls.out2, cls.out3 = [], [], [], []
        env = box.git.env
        cls.git = box.git_git()
        # ① 09:20 틱과 올리기. 이 날은 'Allow GitHub Actions to create and approve pull requests' 가 꺼져 있어 PR 열기가 403 으로 거부된다
        cls.tick1 = run_tick(box.work, at(9, 20, day=28), remote_exists="real", git_env=env, summary_name="s1.md")
        gh.create_errors = [drafts.GitHubError("HTTP 403: GitHub Actions is not permitted to create or approve pull requests.", 403)]
        cls.result1 = draft_flow.deliver(cls.git, gh, dict(ENV), out=cls.out.append, sleep=cls.sleeps.append)
        cls.sleeps_after_403 = list(cls.sleeps)
        cls.prs_after_403 = dict(gh.prs)
        cls.branches1 = box.origin_branches()
        cls.draft_commits = box.commits(f"main..{BRANCH_9}")
        cls.main_commits = box.commits("-2", "main")
        cls.main_files = box.sh(box.origin, "ls-tree", "-r", "--name-only", "main").stdout.splitlines()
        cls.main_history = box.origin_history("main")
        cls.runner_status = box.sh(box.work, "status", "--porcelain", "-b").stdout.splitlines()
        cls.exists_true = draft_flow.remote_branch_exists(BRANCH_9, cls.git)
        cls.exists_false = draft_flow.remote_branch_exists(BRANCH_18, cls.git)
        cls.listed = draft_flow.ls_remote_drafts(cls.git)
        # ② 30분 뒤 틱: 새 실행기가 최신 main 을 받아 같은 슬롯을 다시 본다. 설정을 켠 뒤라서 정리 단계가 PR 을 다시 연다
        cls.clone2 = box.clone("tick2")
        cls.tick2 = run_tick(cls.clone2, at(9, 50, day=28), remote_exists="real", git_env=env, summary_name="s2.md")
        git2 = box.git_git(cls.clone2)
        cls.notes2 = draft_flow.housekeeping(git2, gh, dict(ENV), date(2026, 10, 28), out=cls.out2.append, sleep=cls.sleeps.append)
        cls.pr_reopened = dict(gh.prs.get(41) or {})
        cls.notes2_again = draft_flow.housekeeping(git2, gh, dict(ENV), date(2026, 10, 28), out=cls.out2.append, sleep=cls.sleeps.append)
        cls.pr_count2 = len(gh.prs)
        # ③ 18:20 틱: 9시 초안이 승인을 기다리는 동안 새 실행기가 최신 main 을 받는다. 이번에는 PR 이 바로 열린다
        cls.clone3 = box.clone("evening")
        cls.tick3 = run_tick(cls.clone3, at(18, 20, day=28), remote_exists="real", git_env=env, summary_name="s3.md",
                             feed=[candidate("해양 관측 위성 자료 공개", "https://www.reuters.com/b")])
        cls.result3 = draft_flow.deliver(box.git_git(cls.clone3), gh, dict(ENV), out=cls.out3.append, sleep=lambda s: None)
        cls.branches3 = box.origin_branches()
        cls.slots3 = [e["slot"] for e in box.origin_history("main")]
        cls.evening_commits = box.commits(f"main..{BRANCH_18}")
        # ④ 운영자가 병합한다: 두 순서 모두(운영자가 GitHub 에서 병합하는 것과 같은 3-way 병합)
        cls.merger = merger = box.clone("merger")
        cls.order_a = [box.sh(merger, "merge", "-q", "--no-ff", "-m", b, f"origin/{b}", check=False).returncode for b in (BRANCH_9, BRANCH_18)]
        cls.files_a = sorted(box.sh(merger, "ls-tree", "-r", "--name-only", "HEAD", "_posts").stdout.splitlines())
        box.sh(merger, "reset", "-q", "--hard", "origin/main")
        cls.order_b = [box.sh(merger, "merge", "-q", "--no-ff", "-m", b, f"origin/{b}", check=False).returncode for b in (BRANCH_18, BRANCH_9)]
        cls.files_b = sorted(box.sh(merger, "ls-tree", "-r", "--name-only", "HEAD", "_posts").stdout.splitlines())
        cls.merger_history = json.loads((Path(merger) / "history.json").read_text(encoding="utf-8"))
        cls.control = cls.history_conflict_control(box)
        # ⑤ 병합 결과가 main 에 올라간 뒤의 틱(새 실행기)
        box.sh(merger, "push", "-q", "origin", "HEAD:refs/heads/main")
        cls.clone4 = box.clone("tick4")
        cls.tick4_morning = run_tick(cls.clone4, at(10, 20, day=28), remote_exists="real", git_env=env, summary_name="s4a.md")
        cls.tick4_evening = run_tick(cls.clone4, at(18, 50, day=28), remote_exists="real", git_env=env, summary_name="s4b.md")
        # ⑥ 7일 뒤 정리: 병합·닫힌 브랜치만 지우고 열린 PR 이 있는 브랜치·모르는 이름은 그대로 둔다
        box.sh(merger, "push", "-q", "origin", "HEAD:refs/heads/ai/draft/2026-10-29-s9", "HEAD:refs/heads/ai/draft/weird", "HEAD:refs/heads/feature/x")
        gh.prs[41].update(state="closed", merged=True)
        gh.prs[42].update(state="closed", merged=False)
        gh.add_pr(43, "ai/draft/2026-10-29-s9", "open")
        git4 = box.git_git(cls.clone4)
        cls.cleanup6 = draft_flow.housekeeping(git4, gh, dict(ENV), date(2026, 11, 3), out=cls.out2.append, sleep=lambda s: None)
        cls.branches_day6 = box.origin_branches()
        cls.cleanup7 = draft_flow.housekeeping(git4, gh, dict(ENV), date(2026, 11, 4), out=cls.out2.append, sleep=lambda s: None)
        cls.branches_day7 = box.origin_branches()

    @staticmethod
    def history_conflict_control(box):
        """설계 근거를 git 으로 보인다: 두 PR 이 같은 이력 파일 끝에 항목을 덧붙이면 3-way 병합이 충돌한다(휴대폰에서는 풀 수 없다).
        git merge-file 하나로 확인한다(저장소·브랜치를 만들지 않는다). 종료 코드는 충돌 수다."""
        base = [{"date": "2026-10-27", "slot": 18, "topic": "어제 글"}]
        mine = base + [{"date": "2026-10-28", "slot": 9, "topic": "아침 글"}]
        theirs = base + [{"date": "2026-10-28", "slot": 18, "topic": "저녁 글"}]
        folder = Path(box.root) / "control"
        folder.mkdir()
        for name, entries in (("base.json", base), ("mine.json", mine), ("theirs.json", theirs)):
            (folder / name).write_bytes((json.dumps(entries, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return box.sh(folder, "merge-file", "-p", "mine.json", "base.json", "theirs.json", check=False)

    @classmethod
    def tearDownClass(cls):
        cls.box.close()
        cls.template.close()

    def test_the_first_tick_made_a_draft_entry_and_two_posts(self):
        self.assertEqual(self.tick1.history[0]["branch"], BRANCH_9)
        self.assertEqual(self.tick1.history[0]["flow"], "pr")
        self.assertIn("결과: **DRAFT_CREATED**", self.tick1.summary)

    def test_the_draft_branch_holds_only_the_two_posts_and_main_only_the_history_entry(self):
        (who, mail, subject, files), = self.draft_commits                                  # 초안 브랜치에는 커밋 하나, 바뀐 파일은 글 둘뿐
        self.assertEqual(files, ["_posts/Technology & Future/2026-10-28-EN-092000.md", "_posts/기술·미래/2026-10-28-KR-092000.md"])
        self.assertTrue(subject.startswith("🤖 초안: "))
        history_commit, seed_commit = self.main_commits                                    # main 에는 이력 커밋 하나가 시드 위에 얹혔다
        self.assertEqual(history_commit[3], ["history.json"])
        self.assertTrue(history_commit[2].startswith("🤖 이력: "))
        self.assertEqual(seed_commit[2], "seed")
        self.assertEqual(self.main_files, ["README.md", "_posts/keep.txt", "history.json"])   # 병합 전에는 글이 main 에 없다(공개되지 않는다)
        entry = self.main_history[0]
        self.assertEqual((entry["flow"], entry["branch"], entry["slot"]), ("pr", BRANCH_9, 9))
        self.assertEqual(entry, self.tick1.history[0])                                     # 생성기가 쓴 항목 그대로 올라갔다

    def test_both_commits_are_authored_by_the_bot(self):
        who = (draft_flow.BOT_NAME, draft_flow.BOT_EMAIL)
        self.assertEqual(self.draft_commits[0][:2], who)
        self.assertEqual(self.main_commits[0][:2], who)

    def test_the_runner_ends_on_the_base_branch_with_a_clean_tree(self):
        self.assertTrue(self.runner_status[0].startswith("## main"), self.runner_status)
        self.assertEqual(len(self.runner_status), 1, self.runner_status)                    # 바뀐 파일 줄이 없다

    def test_the_403_keeps_the_branch_and_the_history_and_loses_nothing(self):
        self.assertEqual((self.result1.status, self.result1.code, self.result1.number), ("branch_only", 1, None))
        self.assertEqual(self.branches1, [BRANCH_9, "main"])
        self.assertEqual(self.prs_after_403, {})
        self.assertEqual(self.sleeps_after_403, [])                                        # 403 은 재시도하지 않는다

    def test_the_second_tick_for_the_same_slot_is_draft_pending_and_creates_nothing(self):
        self.assertIn("[SKIP] code=DRAFT_PENDING", self.tick2.out)
        self.assertEqual(self.tick2.prompts, [])
        self.assertEqual(len(self.tick2.history), 1)

    def test_once_the_setting_is_on_the_next_tick_opens_the_missing_pr_from_what_is_on_the_branch(self):
        self.assertEqual(self.notes2, (["PR 다시 열기 1건"], 0))
        pr = self.pr_reopened
        self.assertEqual((pr["head_ref"], pr["base"], pr["labels"]), (BRANCH_9, "main", ["초안", "채널:Chance"]))
        self.assertTrue(pr["title"].startswith("[초안][Chance] 테스트 후보 기사 / Test 후보 기사"))
        self.assertIn("- [ ] 원문과 수치·사실을 대조했다", pr["body"])
        self.assertIn("이 글은 테스트용 본문입니다.", pr["body"])

    def test_the_tick_after_the_reopen_has_nothing_to_do(self):
        self.assertEqual(self.notes2_again, ([], 0))
        self.assertEqual(self.pr_count2, 1)

    def test_the_evening_draft_gets_its_pr_at_once_with_labels_and_a_log_line(self):
        self.assertEqual((self.result3.status, self.result3.branch, self.result3.number, self.result3.code), ("opened", BRANCH_18, 42, 0))
        pr = self.gh.prs[42]
        self.assertEqual((pr["head_ref"], pr["base"], pr["labels"]), (BRANCH_18, "main", ["초안", "채널:Chance"]))
        self.assertIn("- [ ] 병합 = 공개(사람 검토 단계)", pr["body"])
        self.assertIn("이 글은 테스트용 본문입니다.", pr["body"])                # 실제 글에서 만든 본문(기준 브랜치로 돌아가면 글이 작업 트리에서 사라진다)
        text = "\n".join(self.out3)
        self.assertIn(f"초안 브랜치 {BRANCH_18} 를 올렸습니다", text)
        self.assertIn("/pull/42", text)
        self.assertIn("결과: **DRAFT_CREATED**", self.tick3.summary)

    def test_both_drafts_are_open_at_the_same_time_with_their_own_branches_and_posts(self):
        self.assertEqual(self.branches3, [BRANCH_18, BRANCH_9, "main"])
        self.assertEqual(self.slots3, [9, 18])
        (_, _, _, evening_files), = self.evening_commits
        self.assertEqual(evening_files, ["_posts/Technology & Future/2026-10-28-EN-182000.md", "_posts/기술·미래/2026-10-28-KR-182000.md"])
        self.assertEqual(self.draft_commits[0][3], ["_posts/Technology & Future/2026-10-28-EN-092000.md", "_posts/기술·미래/2026-10-28-KR-092000.md"])

    def test_merging_morning_then_evening_has_no_conflict(self):
        self.assertEqual(self.order_a, [0, 0])
        self.assertEqual(len([f for f in self.files_a if f.endswith(".md")]), 4)

    def test_merging_evening_then_morning_has_no_conflict_either(self):
        self.assertEqual(self.order_b, [0, 0])
        self.assertEqual(self.files_b, self.files_a)
        self.assertEqual([e["slot"] for e in self.merger_history], [9, 18])

    def test_why_the_history_entry_is_not_part_of_the_pr(self):
        """두 PR 이 같은 이력 파일 끝에 항목을 덧붙이면 하나를 병합한 뒤 다른 쪽이 충돌한다. 그래서 이력은 생성 시점에 main 에 따로 커밋하고 PR 에는 글 파일만 둔다."""
        self.assertGreater(self.control.returncode, 0)                                      # merge-file 의 종료 코드는 충돌 수
        self.assertIn("<<<<<<<", self.control.stdout)

    def test_after_the_merge_the_slots_read_as_already_published(self):
        for tick in (self.tick4_morning, self.tick4_evening):
            self.assertIn("[SKIP] code=ALREADY_PUBLISHED", tick.out)
            self.assertNotIn("DRAFT_PENDING", tick.out)
            self.assertEqual(tick.prompts, [])
        self.assertTrue((self.clone4 / "_posts" / "기술·미래" / "2026-10-28-KR-092000.md").exists())

    def test_the_remote_branch_helpers_against_a_real_origin(self):
        self.assertTrue(self.exists_true)
        self.assertFalse(self.exists_false)
        self.assertEqual(list(self.listed), [BRANCH_9])
        self.assertRegex(self.listed[BRANCH_9], r"^[0-9a-f]{40,64}$")

    def test_the_cleanup_deletes_old_closed_branches_on_the_seventh_day_and_nothing_else(self):
        self.assertEqual(self.cleanup6, ([], 0))                                            # 6일째
        self.assertEqual(self.branches_day6, [BRANCH_18, BRANCH_9, "ai/draft/2026-10-29-s9", "ai/draft/weird", "feature/x", "main"])
        self.assertEqual(self.cleanup7, (["오래된 브랜치 삭제 2건"], 0))                      # 7일째: 병합된 것과 닫힌 것
        self.assertEqual(self.branches_day7, ["ai/draft/2026-10-29-s9", "ai/draft/weird", "feature/x", "main"])   # 열린 PR·모르는 이름은 그대로


class RealPushTest(unittest.TestCase):
    """이력 push 의 재시도와 롤백(실제 git 의 rebase 동작), 글 이름의 특수 문자."""

    @classmethod
    def setUpClass(cls):
        cls.template = OriginTemplate()

    @classmethod
    def tearDownClass(cls):
        cls.template.close()

    def setUp(self):
        self.box = Sandbox(self.template)
        self.addCleanup(self.box.close)
        self.gh = FakeGitHub()
        self.out, self.sleeps = [], []
        self.git = self.box.git_git()

    def deliver(self):
        return draft_flow.deliver(self.git, self.gh, dict(ENV), out=self.out.append, sleep=self.sleeps.append)

    def advance_origin(self, path, content):
        other = self.box.clone("other")
        (Path(other) / path).write_bytes(content.encode("utf-8"))
        self.box.sh(other, "add", "-A")
        self.box.sh(other, "commit", "-q", "-m", "다른 변경")
        self.box.sh(other, "push", "-q", "origin", "HEAD:refs/heads/main")

    def test_a_rejected_history_push_is_rebased_onto_the_newer_main_and_retried(self):
        write_draft(self.box.work)
        self.advance_origin("README.md", "다른 사람이 고침\n")            # main 이 앞서가 첫 push 가 거절된다
        result = self.deliver()
        self.assertEqual((result.status, self.sleeps), ("opened", [5]))
        self.assertEqual(self.box.origin_show("main", "README.md"), "다른 사람이 고침\n")      # 앞선 변경을 덮어쓰지 않았다
        self.assertEqual(len(self.box.origin_history("main")), 1)
        self.assertEqual(self.box.origin_branches(), [BRANCH_9, "main"])

    def test_a_history_conflict_deletes_the_branch_it_just_pushed(self):
        write_draft(self.box.work)
        self.advance_origin("history.json", json.dumps([{"date": "2026-10-28", "slot": 18, "topic": "다른 글"}]) + "\n")
        with self.assertRaises(draft_flow.GitError):
            self.deliver()
        self.assertEqual(self.box.origin_branches(), ["main"])               # 초안 브랜치가 지워졌다
        self.assertEqual(self.box.origin_history("main"), [{"date": "2026-10-28", "slot": 18, "topic": "다른 글"}])
        self.assertEqual(self.gh.calls, [])

    def test_a_category_with_glob_characters_adds_only_the_literal_files(self):
        """분야 이름은 AI 가 정한다. 대괄호가 든 이름이 다른 폴더의 파일을 끌어오면 안 된다(GIT_LITERAL_PATHSPECS). deliver 가 쓰는 `add --` 와 같은 명령으로 본다."""
        literal = "_posts/기[술]/2026-10-28-KR-090000.md"
        decoy = "_posts/기술/2026-10-28-KR-090000.md"
        for rel, body in ((literal, b"real kr\n"), (decoy, b"decoy\n")):
            (Path(self.box.work) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(self.box.work) / rel).write_bytes(body)
        self.git.run("add", "--", literal)
        staged = self.git.run("diff", "--cached", "--name-only", "-z").stdout.split("\0")
        self.assertEqual([name for name in staged if name], [literal])


class GitWrapperTest(unittest.TestCase):
    def test_errors_carry_a_clean_message_without_the_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            hermetic = HermeticGit(tmp)
            repo = Path(tmp) / "r"
            repo.mkdir()
            hermetic.run(repo, "init", "-q", "-b", "main")
            git = draft_flow.Git(cwd=repo, env=hermetic.env, secrets=("sekret-value-123",))
            with self.assertRaises(draft_flow.GitError) as ctx:
                git.run("checkout", "-q", "sekret-value-123")          # 오류 문구가 인자를 그대로 되풀이한다
        message = str(ctx.exception)
        self.assertIn("***", message)
        self.assertNotIn("sekret-value-123", message)
        self.assertNotIn("\n", message)

    def test_prompts_and_pathspec_magic_are_off(self):
        git = draft_flow.Git()
        self.assertEqual(git.env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(git.env["GIT_LITERAL_PATHSPECS"], "1")

    def test_a_missing_git_binary_is_reported_as_a_git_error(self):
        with mock.patch.object(draft_flow.subprocess, "run", side_effect=FileNotFoundError("git")):
            with self.assertRaises(draft_flow.GitError):
                draft_flow.Git().run("status")

    def test_a_timeout_is_reported_as_a_git_error(self):
        with mock.patch.object(draft_flow.subprocess, "run", side_effect=draft_flow.subprocess.TimeoutExpired("git", 1)):
            with self.assertRaises(draft_flow.GitError):
                draft_flow.Git().run("status")

    def test_truthy_values(self):
        for value in ("1", "true", "TRUE", " yes ", "on"):
            self.assertTrue(draft_flow.truthy(value), value)
        for value in ("0", "false", "", None, "no", "off"):
            self.assertFalse(draft_flow.truthy(value), value)


if __name__ == "__main__":
    unittest.main()
