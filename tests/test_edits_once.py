"""한 이슈는 한 번만 처리한다 — 계획 보고 항목 5, docs/DEFECT_REGISTER.md D-37.

- 이슈 번호 형식 검사(워크플로 첫 단계와 러너가 같은 규칙)
- 이미 처리한 이슈 판단(순수 함수): 원격 브랜치 `refs/heads/issue-edit/<번호>-*`(앞부분 고정) 또는 표식 라벨
- 이미 처리했다면 코멘트만, 새 브랜치·PR 없음(dry_run 은 예외)
- 워크플로 YAML 회귀 테스트: 트리거는 issues opened 뿐, 이슈별 concurrency, 번호 검사가 첫 단계
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap  # noqa: F401
from edits_helpers import ABOUT, REAL, issue, page_body
from pipeline.edits import runner, spec as spec_mod
from test_edits_logging import run_main, strip_code_spans
from test_edits_runner import NEW_SENTENCE, OLD_SENTENCE, RunnerBase

SHA = "a" * 40


def ref(branch, sha=SHA):
    return f"{sha}\trefs/heads/{branch}"


REFS = [ref("issue-edit/1-about-r3"), ref("issue-edit/12-about-r5"), ref("issue-edit/120-about-r9")]


class IssueNumberTest(unittest.TestCase):
    def test_valid_numbers(self):
        for value, want in ((1, 1), (12, 12), ("12", 12), ("120", 120), (999999999, 999999999), ("999999999", 999999999)):
            self.assertEqual(runner.valid_issue_number(value), want, value)

    def test_invalid_numbers(self):
        for value in (None, "", "0", 0, -1, "-1", "012", "1234567890", 1234567890, "12a", "1 2", " 12", "12\n", "12\nabc", "../1",
                      "1;rm", True, False, 1.5, "1.0", "\N{ARABIC-INDIC DIGIT THREE}", [12], {"n": 12}):
            self.assertIsNone(runner.valid_issue_number(value), repr(value))

    def test_pattern_matches_what_the_workflow_checks(self):
        self.assertEqual(runner.ISSUE_NUMBER_PATTERN, r"[1-9][0-9]{0,8}")


class AlreadyProcessedTest(unittest.TestCase):
    def test_number_boundaries_1_12_120(self):
        for number, branch in ((1, "issue-edit/1-about-r3"), (12, "issue-edit/12-about-r5"), (120, "issue-edit/120-about-r9")):
            done = runner.already_processed(number, REFS)
            self.assertTrue(done, number)
            self.assertEqual(done.branches, (branch,), number)      # 1 은 12·120 과, 12 는 120 과 섞이지 않는다
            self.assertFalse(done.labeled)
        for number in (2, 11, 13, 100, 121, 1200, 999999999):
            self.assertFalse(runner.already_processed(number, REFS), number)

    def test_the_prefix_is_anchored_so_other_paths_do_not_match(self):
        traps = ["feature/issue-edit/12-x", "ai/claude/issue-edit/12-x", "xissue-edit/12-x", "issue-edit/12", "issue-edit/12x-y",
                 "issue-edit/012-x", "issue-edit/1/2-x", "issues/issue-edit/12-x"]
        lines = [ref(b) for b in traps]
        lines += [f"{SHA}\trefs/tags/issue-edit/12-tag", f"{SHA}\trefs/remotes/origin/issue-edit/12-x", f"{SHA}\trefs/pull/12/head"]
        self.assertFalse(runner.already_processed(12, lines))
        self.assertTrue(runner.already_processed(12, lines + [ref("issue-edit/12-x")]))

    def test_accepts_ls_remote_lines_plain_refs_a_single_string_and_iterables(self):
        want = ("issue-edit/12-a", "issue-edit/12-b")
        sources = [[ref("issue-edit/12-a"), ref("issue-edit/12-b")], ["refs/heads/issue-edit/12-a", "refs/heads/issue-edit/12-b"],
                   ref("issue-edit/12-a") + "\n" + ref("issue-edit/12-b") + "\n", (ref("issue-edit/12-b"), ref("issue-edit/12-a")),
                   (x for x in [ref("issue-edit/12-a"), ref("issue-edit/12-b"), ref("issue-edit/12-a")])]
        for src in sources:
            self.assertEqual(runner.already_processed(12, src).branches, want)
        for empty in ((), [], "", None, [""], ["   "]):
            self.assertFalse(runner.already_processed(12, empty))

    def test_the_label_marker_is_a_second_independent_evidence(self):
        done = runner.already_processed(12, [], [{"name": "blog-control"}, {"name": "issue-edit-done"}])
        self.assertTrue(done)
        self.assertEqual((done.branches, done.labeled), ((), True))
        self.assertTrue(runner.already_processed(12, [], ["issue-edit-done"]))
        self.assertFalse(runner.already_processed(12, [], [{"name": "blog-control"}, {"name": "edit:page"}, "edit:image"]))
        both = runner.already_processed(12, REFS, [{"name": "issue-edit-done"}])
        self.assertEqual((both.branches, both.labeled), (("issue-edit/12-about-r5",), True))

    def test_invalid_numbers_never_match_and_never_crash(self):
        everything = REFS + [ref("issue-edit/-x"), ref("issue-edit/0-x"), ref("issue-edit/012-x")]
        for number in (None, "", "abc", "12; rm", 0, -1, True, 1.5, "012", "1" * 10, "\N{ARABIC-INDIC DIGIT THREE}"):
            self.assertFalse(runner.already_processed(number, everything, [{"name": "issue-edit-done"}]), repr(number))

    def test_custom_prefix(self):
        refs = [ref("edits/12-a"), ref("issue-edit/12-b")]
        self.assertEqual(runner.already_processed(12, refs, prefix="edits/").branches, ("edits/12-a",))


class ProcessIssueOnceTest(RunnerBase):
    def literal(self, issue_kw=None, **kw):
        return self.go(issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE), **(issue_kw or {})), **kw)

    def test_existing_branch_means_comment_only(self):
        res = self.literal(remote_refs=[ref("issue-edit/12-about-r5")])
        self.assertEqual((res.status, res.exit_code), ("duplicate", 0))
        self.assertEqual((res.files, res.branch, res.pr_title, res.pr_body, res.commit_message), ([], "", "", "", ""))
        self.assertEqual(self.read("about.md"), ABOUT)               # 아무것도 고치지 않았다
        for phrase in ("이미 처리한 이슈입니다", "`issue-edit/12-about-r5`", "새 이슈로"):
            self.assertIn(phrase, res.comment)

    def test_label_marker_alone_is_enough_even_if_the_branch_was_deleted(self):
        res = self.literal(remote_refs=[], issue_kw={"labels": ("blog-control", "edit:page", "issue-edit-done")})
        self.assertEqual(res.status, "duplicate")
        self.assertIn("issue-edit-done", res.comment)
        self.assertEqual(self.read("about.md"), ABOUT)

    def test_other_issues_branches_do_not_block(self):
        res = self.literal(remote_refs=[ref("issue-edit/1-about-r3"), ref("issue-edit/120-about-r9"), ref("feature/issue-edit/12-x")])
        self.assertEqual(res.status, "ok")
        self.assertIn(NEW_SENTENCE, self.read("about.md"))

    def test_without_refs_nothing_blocks_by_branch(self):
        self.assertEqual(self.literal().status, "ok")

    def test_dry_run_is_exempt_and_leaves_a_note(self):
        res = self.literal(remote_refs=[ref("issue-edit/12-about-r5")], dry_run=True)
        self.assertEqual(res.status, "ok")
        self.assertTrue(any("dry-run" in n and "issue-edit/12-about-r5" in n for n in res.notes), res.notes)
        self.assertEqual(self.read("about.md"), ABOUT)               # dry-run 이라 파일은 그대로
        labeled = self.literal(remote_refs=[], dry_run=True, issue_kw={"labels": ("blog-control", "edit:page", "issue-edit-done")})
        self.assertEqual(labeled.status, "ok")
        self.assertTrue(any("표식 라벨" in n for n in labeled.notes))

    def test_ignored_issues_stay_ignored_and_get_no_comment(self):
        res = self.literal(remote_refs=[ref("issue-edit/12-about-r5")], issue_kw={"assoc": "NONE"})
        self.assertEqual((res.status, res.comment), ("ignored", ""))

    def test_the_check_comes_before_parsing_so_a_garbled_body_still_gets_the_duplicate_notice(self):
        res = self.go(issue("그냥 아무 말", labels=(), title="무제"), remote_refs=[ref("issue-edit/12-about-r5")])
        self.assertEqual(res.status, "duplicate")

    def test_invalid_issue_numbers_stop_with_a_config_error(self):
        for number in (0, -5, 10 ** 9, True, "012", None, "12; rm -rf"):
            iss = issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE))
            iss["number"] = number
            res = self.go(iss)
            self.assertEqual((res.status, res.exit_code), ("error", runner.EXIT_CONFIG), repr(number))
        self.assertEqual(self.read("about.md"), ABOUT)

    def test_the_branch_the_runner_makes_is_recognised_by_the_check(self):
        """브랜치 이름 규칙(runner)과 재처리 확인(already_processed)이 어긋나지 않는다."""
        made = self.literal()
        self.assertEqual(made.status, "ok")
        self.assertTrue(made.branch.startswith("issue-edit/12-"))
        done = runner.already_processed(12, [ref(made.branch)])
        self.assertEqual(done.branches, (made.branch,))
        self.assertFalse(runner.already_processed(13, [ref(made.branch)]))

    def test_spec_branch_prefix_is_used_for_the_check(self):
        spec_file = self.root / ".github" / "editorial" / "edit-spec.yml"
        raw = spec_file.read_bytes().decode("utf-8")
        spec_file.write_bytes(raw.replace('branch_prefix: "issue-edit/"', 'branch_prefix: "edits/"').encode("utf-8"))
        self.assertEqual(self.literal(remote_refs=[ref("edits/12-about-r5")]).status, "duplicate")
        self.assertEqual(self.literal(remote_refs=[ref("issue-edit/12-about-r5")]).status, "ok")

    def test_comment_links_only_with_sane_environment_values_and_never_renders_branch_text(self):
        env = {"GITHUB_REPOSITORY": "shine88pc/chanceblog", "DEFAULT_BRANCH": "main"}
        res = self.literal(remote_refs=[ref("issue-edit/12-about-r5")], env=env)
        self.assertIn("https://github.com/shine88pc/chanceblog/compare/main...issue-edit/12-about-r5?expand=1", res.comment)
        for repo, base in (("evil) [x](http://e", "main"), ("shine88pc/chanceblog", "ma in"), ("", "")):
            bad = self.literal(remote_refs=[ref("issue-edit/12-about-r5")], env={"GITHUB_REPOSITORY": repo, "DEFAULT_BRANCH": base})
            self.assertNotIn("compare/", bad.comment, (repo, base))
        hostile = self.literal(remote_refs=[ref("issue-edit/12-![x](https://evil.example/p.png)@everyone")], env=env)
        self.assertEqual(hostile.status, "duplicate")
        link = re.search(r"\]\((https://github\.com/shine88pc/chanceblog/compare/[^)\s]*)\)", hostile.comment).group(1)
        self.assertRegex(link, r"^[A-Za-z0-9/._~%?=:.-]+$")        # 괄호·대괄호·느낌표·@ 는 퍼센트 인코딩돼 링크를 깨뜨리지 못한다
        outside = strip_code_spans(re.sub(r"\]\([^)\s]*\)", "]", hostile.comment))
        for fragment in ("![", "evil.example", "@everyone"):
            self.assertNotIn(fragment, outside)


class MainCliOnceTest(RunnerBase):
    def run_cli(self, extra, iss=None):
        iss = iss or issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE))
        return run_main(self.root, iss, extra)

    def refs_file(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "remote_refs.txt"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_duplicate_is_logged_commented_and_changes_nothing(self):
        code, out, files = self.run_cli(["--remote-refs", self.refs_file(ref("issue-edit/12-about-r5") + "\n")])
        self.assertEqual(code, 0)
        self.assertEqual(files["status.txt"].strip(), "duplicate")
        self.assertEqual((files["files.txt"], files["branch.txt"].strip(), files["pr_title.txt"].strip()), ("", "", ""))
        self.assertIn("이미 처리한 이슈입니다", files["comment.md"])
        self.assertTrue(out.splitlines()[0].startswith("[issue-edit] issue=#12 author=@shine88pc(OWNER) status=duplicate"), out)
        self.assertEqual(self.read("about.md"), ABOUT)

    def test_empty_refs_file_lets_the_first_run_through(self):
        code, _out, files = self.run_cli(["--remote-refs", self.refs_file("")])
        self.assertEqual((code, files["status.txt"].strip()), (0, "ok"))

    def test_unreadable_refs_file_fails_closed(self):
        code, out, files = self.run_cli(["--remote-refs", "/no/such/remote_refs.txt"])
        self.assertEqual(code, runner.EXIT_CONFIG)
        self.assertEqual(files["status.txt"].strip(), "error")
        self.assertIn("원격 브랜치 목록을 읽을 수 없습니다", out)
        self.assertEqual(self.read("about.md"), ABOUT)

    def test_dry_run_continues_and_logs_the_note(self):
        code, out, files = self.run_cli(["--dry-run", "--remote-refs", self.refs_file(ref("issue-edit/12-about-r5"))])
        self.assertEqual((code, files["status.txt"].strip()), (0, "ok"))
        self.assertIn("dry-run 이라 처리를 계속했습니다", out)
        self.assertTrue(all(ln.startswith("[issue-edit] issue=#12 author=@shine88pc(OWNER)") for ln in out.splitlines()))


class IssueEditWorkflowTest(unittest.TestCase):
    """issue-edit.yml 을 yaml.safe_load 로 읽어 재처리·경쟁 조건 방어가 사라지지 않게 지킨다(D-21 이 인용한 테스트는 워크플로를 읽지 않았다)."""

    @classmethod
    def setUpClass(cls):
        cls.wf = yaml.safe_load((REAL / ".github" / "workflows" / "issue-edit.yml").read_text(encoding="utf-8"))
        cls.job = next(iter(cls.wf["jobs"].values()))          # 첫 job(번호를 받는 job)
        cls.steps = cls.job["steps"]

    def triggers(self):
        return self.wf.get("on", self.wf.get(True))            # YAML 1.1: `on` 이 True 로 읽힌다

    def step_index(self, fragment):
        for i, step in enumerate(self.steps):
            if fragment in str(step.get("run", "")):
                return i
        self.fail(f"{fragment!r} 를 실행하는 단계가 없습니다")

    def test_triggers_only_on_issues_opened_and_manual_dispatch(self):
        triggers = self.triggers()
        self.assertEqual(set(triggers), {"issues", "workflow_dispatch"})      # edited·reopened·labeled·issue_comment 등 재실행 트리거 없음
        self.assertEqual(triggers["issues"]["types"], ["opened"])
        inputs = triggers["workflow_dispatch"]["inputs"]
        self.assertEqual(inputs["issue_number"]["type"], "string")
        self.assertTrue(inputs["issue_number"]["required"])
        self.assertIs(inputs["dry_run"]["default"], True)                      # 수동 실행의 기본값은 dry-run

    def test_each_issue_has_its_own_concurrency_group_and_is_never_cancelled(self):
        group = self.wf["concurrency"]["group"]
        self.assertIn("issue-edit-", group)
        self.assertIn("github.event.issue.number", group)
        self.assertIn("inputs.issue_number", group)
        self.assertIs(self.wf["concurrency"]["cancel-in-progress"], False)

    def test_the_first_step_validates_the_issue_number_before_anything_else(self):
        first = self.steps[0]
        self.assertNotIn("uses", first)                                         # 체크아웃·설치보다 먼저 돈다
        script = first["run"]
        self.assertIn("ISSUE_NUMBER", script)
        self.assertIn(f"^{runner.ISSUE_NUMBER_PATTERN}$", script)               # 러너와 같은 규칙
        self.assertIn("exit 1", script)
        self.assertNotIn("${{", script)                                         # 번호를 셸에 보간하지 않고 env 로 읽는다
        self.assertIn("ISSUE_NUMBER", self.job["env"])

    def test_no_run_step_interpolates_untrusted_expressions(self):
        for step in self.steps:
            run = str(step.get("run", ""))
            self.assertNotRegex(run, r"\$\{\{\s*(?:github\.event\.issue|inputs\.)")

    def test_existing_branches_are_queried_with_an_anchored_pattern_and_handed_to_the_runner(self):
        idx = self.step_index("git ls-remote")
        query = self.steps[idx]["run"]
        self.assertIn('git ls-remote --heads origin "refs/heads/issue-edit/${ISSUE_NUMBER}-*"', query)
        self.assertIn("remote_refs.txt", query)
        run_idx = self.step_index("pipeline.edits.runner --issue-file")
        self.assertLess(idx, run_idx)
        self.assertIn('--remote-refs "${RUNNER_TEMP}/remote_refs.txt"', self.steps[run_idx]["run"])
        checkout = next(i for i, step in enumerate(self.steps) if str(step.get("uses", "")).startswith("actions/checkout"))
        self.assertLess(checkout, idx)                                          # origin 은 체크아웃 뒤에 있다

    def test_branch_prefix_in_the_spec_matches_the_workflow_pattern(self):
        self.assertEqual(spec_mod.load_spec(REAL)["output"]["branch_prefix"], "issue-edit/")

    def test_duplicate_status_gets_a_comment_and_done_issues_get_the_marker_label(self):
        comment_step = self.steps[self.step_index('gh issue comment "$ISSUE_NUMBER"')]["run"]
        self.assertRegex(comment_step, r"rejected\|error\|duplicate\)\s+cp ")
        self.assertIn(f'gh issue edit "$ISSUE_NUMBER" --add-label "{runner.DONE_LABEL}"', comment_step)
        self.assertLess(comment_step.index("gh issue comment"), comment_step.index("--add-label"))   # 코멘트가 먼저
        labels_step = self.steps[self.step_index("gh label create")]["run"]
        self.assertIn(f'gh label create "{runner.DONE_LABEL}"', labels_step)

    def test_dry_run_output_goes_through_the_guarded_printer_not_cat(self):
        step = self.steps[self.step_index("--show-output")]
        self.assertNotIn("cat ", step["run"])
        self.assertIn("DRY_RUN", str(step["if"]))

    def test_ls_remote_pattern_is_anchored_in_a_real_repository(self):
        """워크플로의 실제 패턴을 임시 저장소에 적용한다: 번호 경계(1·12·120)와 다른 경로가 섞이지 않고, 고정하지 않으면 섞인다는 대조까지."""
        template = re.search(r'"(refs/heads/issue-edit/\$\{ISSUE_NUMBER\}-\*)"', self.steps[self.step_index("git ls-remote")]["run"]).group(1)
        names = ["issue-edit/1-about-r3", "issue-edit/12-about-r5", "issue-edit/12-about-r6", "issue-edit/120-about-r9",
                 "feature/issue-edit/12-trap", "ai/claude/issue-edit/12-trap", "issue-edit/12", "issue-edit/12x-trap",
                 "issue-edit/013-x", "xissue-edit/12-trap"]
        stream = (b"commit refs/heads/main\ncommitter t <t@example.com> 1700000000 +0000\ndata 1\nx\nM 100644 inline a.txt\ndata 1\na\n\n")
        for name in names:
            stream += b"reset refs/heads/%s\nfrom refs/heads/main\n\n" % name.encode()
        stream += b"reset refs/tags/issue-edit/12-tag\nfrom refs/heads/main\n\n"
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True, capture_output=True)
            subprocess.run(["git", "fast-import", "--quiet"], cwd=tmp, input=stream, check=True, capture_output=True)

            def ls_remote(pattern):
                out = subprocess.run(["git", "ls-remote", "--heads", Path(tmp).as_posix(), pattern], check=True, capture_output=True)
                return out.stdout.decode("utf-8").splitlines()

            expected = {1: ["issue-edit/1-about-r3"], 12: ["issue-edit/12-about-r5", "issue-edit/12-about-r6"],
                        120: ["issue-edit/120-about-r9"], 3: []}
            for number, want in expected.items():
                lines = ls_remote(template.replace("${ISSUE_NUMBER}", str(number)))
                self.assertEqual(sorted(line.split("\t")[1][len("refs/heads/"):] for line in lines), want, number)   # git 자체가 이미 고정
                self.assertEqual(list(runner.already_processed(number, lines).branches), want, number)               # 러너의 판단도 같다
            unanchored = ls_remote("issue-edit/12-*")                                                                  # 대조: 고정하지 않으면
            self.assertIn("refs/heads/feature/issue-edit/12-trap", [line.split("\t")[1] for line in unanchored])


if __name__ == "__main__":
    unittest.main()
