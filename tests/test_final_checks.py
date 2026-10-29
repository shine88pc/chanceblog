"""검증 사다리 도구(scripts/final_checks.py) 시험. 진짜 시험·도구를 돌리지 않고 가짜 실행기로만 돈다."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import final_checks as fc  # noqa: E402

OK_TESTS = (0, "", "----------------------------------------------------------------------\nRan 4146 tests in 428.5s\n\nOK\n")
OK_VALIDATE = (0, "요약: 오류 0건, 경고 2건 — 통과\n", "")


class FakeRunner:
    """cmd 가 규칙의 조건에 맞는 첫 규칙의 결과를 돌려준다. 맞는 규칙이 없으면 (0, '', '')."""

    def __init__(self, rules=()):
        self.rules, self.calls = list(rules), []

    def __call__(self, cmd, cwd, timeout):
        self.calls.append((list(cmd), str(cwd), timeout))
        for matches, result in self.rules:
            if matches(cmd):
                return result
        return 0, "", ""

    def commands(self, *needles):
        return [c for c, _, _ in self.calls if all(any(n in str(part) for part in c) for n in needles)]


def has(*needles):
    return lambda cmd: all(any(n in str(part) for part in cmd) for n in needles)


def git_is(*words):
    """git 명령(앞쪽의 `-c 이름=값` 옵션은 건너뛰고)이 words 로 시작하는가."""
    def matches(cmd):
        if cmd[0] != "git":
            return False
        rest = list(cmd[1:])
        while rest[:1] == ["-c"]:
            rest = rest[2:]
        return rest[:len(words)] == list(words)
    return matches


def make_root(py_files=("pipeline/x.py", "tests/test_x.py", "scripts/validate_repo.py", "scripts/final_checks.py")):
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    for name in py_files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "a.yml").write_text("name: a\n", encoding="utf-8")
    return tmp, root


def base_rules(**overrides):
    rules = {"tests": (has("unittest"), OK_TESTS), "validate": (has("validate_repo.py"), OK_VALIDATE),
             "revparse": (git_is("rev-parse"), (0, "abc\n", "")),
             "diff": (git_is("diff"), (0, "pipeline/x.py\ndocs/a.md\ntests/gone.py\n", "")),
             "untracked": (git_is("ls-files"), (0, "scripts/final_checks.py\n", "")),
             "vermin": (has("vermin"), (0, "Minimum required versions: 3.10\n", ""))}
    rules.update(overrides)
    return list(rules.values())


def fake_finder(**found):
    """find_executable 대신 쓴다: 이름별로 정한 경로를 돌려주고 없으면 None."""
    return lambda name, which=None: found.get(name)


def ladder(root, runner, base="origin/main", pattern=None, actionlint="/bin/actionlint", vermin="/bin/vermin", modules=("pyflakes",)):
    with mock.patch.object(fc, "find_executable", fake_finder(actionlint=actionlint, vermin=vermin)):
        return fc.run_ladder(root, base, pattern, runner=runner, which=lambda name: None, module_ok=lambda name: name in modules)


class LadderTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = make_root()
        self.addCleanup(self.tmp.cleanup)

    def test_everything_passing_runs_six_steps_and_names_them(self):
        runner = FakeRunner(base_rules())
        steps, files, note = ladder(self.root, runner)
        self.assertEqual([s.name for s in steps], ["전체 시험", "저장소 규칙 검증기", "actionlint", "pyflakes", "vermin(3.10 이하)", "3.12 전용 f-string"])
        self.assertEqual([s.status for s in steps[:5]], [fc.PASS] * 5)
        self.assertIn("4146개 통과 (428.5초)", steps[0].detail)
        self.assertIn("오류 0건, 경고 2건", steps[1].detail)
        # 바뀐 .py 만: 지운 파일(tests/gone.py)·.py 가 아닌 파일(docs/a.md)은 빠지고 새 파일(scripts/final_checks.py)은 들어온다
        self.assertEqual(files, ["pipeline/x.py", "scripts/final_checks.py"])
        self.assertIn("origin/main 대비", note)

    def test_unittest_and_validate_are_run_from_the_root_with_the_base(self):
        runner = FakeRunner(base_rules())
        ladder(self.root, runner)
        unit = runner.commands("unittest")[0]
        self.assertEqual(unit[1:], ["-X", "utf8", "-m", "unittest", "discover", "-s", "tests"])
        validate = runner.commands("validate_repo.py")[0]
        self.assertEqual(validate[-2:], ["--base", "origin/main"])
        self.assertTrue(all(cwd == str(self.root) for _, cwd, _ in runner.calls))

    def test_tests_pattern_is_passed_and_named_in_the_step(self):
        runner = FakeRunner(base_rules())
        steps, _, _ = ladder(self.root, runner, pattern="test_llm_timeout.py")
        self.assertEqual(runner.commands("unittest")[0][-2:], ["-p", "test_llm_timeout.py"])
        self.assertEqual(steps[0].name, "시험(test_llm_timeout.py)")

    def test_without_a_base_commit_validate_skips_ad_check_and_all_python_files_are_used(self):
        runner = FakeRunner(base_rules(revparse=(git_is("rev-parse"), (1, "", ""))))
        steps, files, note = ladder(self.root, runner)
        self.assertNotIn("--base", runner.commands("validate_repo.py")[0])
        self.assertEqual(steps[1].status, fc.SKIP)                       # 광고 표면(AD-1·AD-2)을 못 봤으니 통과가 아니다
        self.assertIn("광고 표면 검사(AD-1·AD-2)를 하지 못했습니다", steps[1].detail)
        self.assertIn("pipeline/x.py", files)
        self.assertIn("tests/test_x.py", files)
        self.assertIn("모든 .py", note)

    def test_git_diff_failure_falls_back_to_all_python_files(self):
        runner = FakeRunner(base_rules(diff=(git_is("diff"), (128, "", "fatal"))))
        _, files, note = ladder(self.root, runner)
        self.assertIn("pipeline/x.py", files)
        self.assertIn("모든 .py", note)


class StepResultsTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = make_root()
        self.addCleanup(self.tmp.cleanup)

    def test_failing_tests_report_the_tail_of_the_output(self):
        bad = (1, "", "FAIL: test_a (x.Y)\nTraceback...\nAssertionError: 1 != 2\n\n----\nRan 3 tests in 0.1s\n\nFAILED (failures=1)\n")
        step = fc.step_tests(self.root, None, FakeRunner([(has("unittest"), bad)]))
        self.assertEqual(step.status, fc.FAIL)
        self.assertIn("FAILED (failures=1)", step.detail)

    def test_zero_exit_without_an_ok_line_is_not_a_pass(self):
        step = fc.step_tests(self.root, None, FakeRunner([(has("unittest"), (0, "", "Ran 0 tests in 0.0s\n"))]))
        self.assertEqual(step.status, fc.FAIL)

    def test_skipped_unit_tests_are_counted_apart_and_zero_tests_fail(self):
        skipped = (0, "", "Ran 120 tests in 3.0s\n\nOK (skipped=7)\n")
        step = fc.step_tests(self.root, None, FakeRunner([(has("unittest"), skipped)]))
        self.assertEqual(step.status, fc.PASS)
        self.assertIn("113개 통과", step.detail)
        self.assertIn("건너뛴 시험 7개", step.detail)
        none_ran = (0, "", "Ran 0 tests in 0.000s\n\nOK\n")
        step = fc.step_tests(self.root, "test_typo.py", FakeRunner([(has("unittest"), none_ran)]))
        self.assertEqual(step.status, fc.FAIL)
        self.assertIn("하나도 돌지 않았습니다", step.detail)

    def test_validate_without_a_base_is_a_skip_when_the_rest_passed_and_still_a_failure_when_it_failed(self):
        step = fc.step_validate(self.root, None, FakeRunner(base_rules()))
        self.assertEqual(step.status, fc.SKIP)
        failing = FakeRunner(base_rules(validate=(has("validate_repo.py"), (1, "ERROR [X-1] 깨짐\n요약: 오류 1건, 경고 0건 — 실패\n", ""))))
        step = fc.step_validate(self.root, None, failing)
        self.assertEqual(step.status, fc.FAIL)
        self.assertIn("ERROR [X-1] 깨짐", step.detail)

    def test_pyflakes_that_crashed_fails_even_when_it_printed_nothing(self):
        for code in (2, 124, 127, -9):
            with self.subTest(code=code):
                step = fc.step_pyflakes(self.root, ["pipeline/x.py"], FakeRunner([(has("pyflakes"), (code, "", "No module named pyflakes"))]), lambda name: True)
                self.assertEqual(step.status, fc.FAIL)
                self.assertIn("비정상 종료", step.detail)

    def test_pyflakes_does_not_count_the_known_package_reexport_lines(self):
        known = (1, "pipeline/publishers/__init__.py:16:1: 'pipeline.publishers.base.PublishError' imported but unused\n"
                    "pipeline/publishers/__init__.py:16:1: 'pipeline.publishers.base.PublishResult' imported but unused\n", "")
        step = fc.step_pyflakes(self.root, ["pipeline/publishers/__init__.py"], FakeRunner([(has("pyflakes"), known)]), lambda name: True)
        self.assertEqual(step.status, fc.PASS)
        other = (1, "pipeline/publishers/__init__.py:16:1: 'pipeline.publishers.base.Other' imported but unused\n", "")
        self.assertEqual(fc.step_pyflakes(self.root, ["pipeline/publishers/__init__.py"], FakeRunner([(has("pyflakes"), other)]), lambda name: True).status, fc.FAIL)

    def test_git_is_asked_for_names_without_quoting_non_ascii_paths(self):
        runner = FakeRunner(base_rules())
        fc.changed_python_files(self.root, "origin/main", runner)
        diff = runner.commands("diff")[0]
        self.assertEqual(diff[:3], ["git", "-c", "core.quotepath=off"])

    def test_validate_failure_lists_the_error_lines(self):
        out = "ERROR [AD-1] index.html 승인 표시 없음\nWARN x\n\n요약: 오류 1건, 경고 1건 — 실패\n"
        step = fc.step_validate(self.root, "origin/main", FakeRunner(base_rules(validate=(has("validate_repo.py"), (1, out, "")))))
        self.assertEqual(step.status, fc.FAIL)
        self.assertIn("ERROR [AD-1] index.html", step.detail)
        self.assertIn("오류 1건", step.detail)

    def test_actionlint_missing_is_skipped_not_passed(self):
        with mock.patch.object(fc, "find_executable", fake_finder()):
            step = fc.step_actionlint(self.root, FakeRunner(), lambda name: None)
        self.assertEqual(step.status, fc.SKIP)

    def test_actionlint_findings_fail_with_the_first_lines(self):
        runner = FakeRunner([(lambda cmd: cmd[0] == "/bin/actionlint", (1, ".github/workflows/a.yml:3:1: bad [syntax-check]\n", ""))])
        with mock.patch.object(fc, "find_executable", fake_finder(actionlint="/bin/actionlint")):
            step = fc.step_actionlint(self.root, runner, lambda name: None)
        self.assertEqual(step.status, fc.FAIL)
        self.assertIn("a.yml:3:1", step.detail)
        self.assertEqual(runner.calls[0][0], ["/bin/actionlint", ".github/workflows/a.yml"])

    def test_pyflakes_ignores_the_repo_bootstrap_idiom_but_not_real_warnings(self):
        only_idiom = (1, "tests/test_x.py:3:1: '_bootstrap' imported but unused\n", "")
        step = fc.step_pyflakes(self.root, ["tests/test_x.py"], FakeRunner([(has("pyflakes"), only_idiom)]), lambda name: True)
        self.assertEqual(step.status, fc.PASS)
        real = (1, "tests/test_x.py:3:1: '_bootstrap' imported but unused\npipeline/x.py:9:5: undefined name 'foo'\n", "")
        step = fc.step_pyflakes(self.root, ["pipeline/x.py"], FakeRunner([(has("pyflakes"), real)]), lambda name: True)
        self.assertEqual(step.status, fc.FAIL)
        self.assertIn("undefined name 'foo'", step.detail)
        self.assertNotIn("_bootstrap", step.detail)

    def test_pyflakes_and_vermin_are_skipped_when_not_installed_and_trivially_pass_without_changes(self):
        self.assertEqual(fc.step_pyflakes(self.root, ["a.py"], FakeRunner(), lambda name: False).status, fc.SKIP)
        self.assertEqual(fc.step_pyflakes(self.root, [], FakeRunner(), lambda name: True).status, fc.PASS)
        with mock.patch.object(fc, "find_executable", fake_finder()):
            self.assertEqual(fc.step_vermin(self.root, ["a.py"], FakeRunner(), lambda name: None).status, fc.SKIP)
        with mock.patch.object(fc, "find_executable", fake_finder(vermin="/bin/vermin")):
            self.assertEqual(fc.step_vermin(self.root, [], FakeRunner(), lambda name: None).status, fc.PASS)

    def vermin_step(self, result):
        runner = FakeRunner([(has("vermin"), result)])
        with mock.patch.object(fc, "find_executable", fake_finder(vermin="/bin/vermin")):
            return fc.step_vermin(self.root, ["pipeline/x.py"], runner, lambda name: None), runner

    def test_vermin_fails_when_code_needs_newer_than_3_10(self):
        for text in ("Minimum required versions: 3.12\n", "Minimum required versions: 3.11\n", "Target versions not met: 3.10-\n"):
            step, _ = self.vermin_step((1, text, ""))
            self.assertEqual(step.status, fc.FAIL, text)
        step, runner = self.vermin_step((0, "Minimum required versions: 3.9\n", ""))
        self.assertEqual((step.status, step.detail), (fc.PASS, "최소 3.9"))
        self.assertEqual(runner.calls[0][0], ["/bin/vermin", "--target=3.10-", "--no-tips", "pipeline/x.py"])

    def test_vermin_that_did_not_run_is_a_failure_not_a_pass(self):
        """`python -m vermin` 은 실행되지 않고 출력이 비어 '지적 없음'으로 보이는 가짜 통과가 실제로 났다."""
        for result in ((1, "", "No module named vermin.__main__"), (0, "", ""), (127, "", "실행하지 못했습니다: FileNotFoundError")):
            step, _ = self.vermin_step(result)
            self.assertEqual(step.status, fc.FAIL, result)
            self.assertIn("읽지 못했습니다", step.detail)

    def test_fstring_step_is_skipped_below_python_3_12(self):
        step = fc.step_fstrings(self.root, ["pipeline/x.py"], version=(3, 10, 12))
        self.assertEqual(step.status, fc.SKIP)
        self.assertIn("3.12", step.detail)


@unittest.skipIf(sys.version_info < (3, 12), "3.12 이상에서만 f-string 토큰이 있다")
class FstringDetectorTest(unittest.TestCase):
    def test_same_quote_reuse_and_comments_inside_an_expression_are_found(self):
        source = ('d = {"x": 1}\n'
                  'a = f"{d["x"]}"\n'
                  "b = f'{'abc'.upper()}'\n"
                  'c = f"""{\n    d  # 주석\n}"""\n').encode("utf-8")
        reasons = [why for _, _, why in fc.find_py312_only_fstrings(source)]
        self.assertEqual(len(reasons), 3)
        self.assertEqual(reasons.count("f-string 식 안에서 같은 따옴표를 다시 씀"), 2)
        self.assertEqual(reasons.count("f-string 식 안의 주석"), 1)

    def test_nested_same_quote_fstrings_backslashes_and_newlines_inside_an_expression_are_found(self):
        """독립 검증이 짚은 미탐 셋: 같은 따옴표의 f-string 중첩, 식 안의 역슬래시, 한 줄 f-string 식 안의 줄바꿈(3.12 파서는 모두 통과시킨다)."""
        nested = 'y = 1\na = f"{f"{y}"}"\n'
        backslash = 'y = ["a"]\nb = f"{\'\\n\'.join(y)}"\n'
        newline = 'y = 1\nc = f"{\n y }"\n'
        for source, expected in ((nested, "같은 따옴표의 f-string"), (backslash, "역슬래시"), (newline, "줄바꿈")):
            with self.subTest(expected=expected):
                reasons = [why for _, _, why in fc.find_py312_only_fstrings(source.encode("utf-8"))]
                self.assertTrue(any(expected in why for why in reasons), (expected, reasons))

    def test_ordinary_fstrings_are_clean(self):
        source = ('d = {"x": 1}\n'
                  "a = f\"{d['x']}\"\n"
                  "b = f'{d[\"x\"]}'\n"
                  'c = f"""{d["x"]} 큰따옴표 세 개 안에서는 큰따옴표 하나가 괜찮다"""\n'
                  "e = f'{d!r:>10}'\n"
                  "f = f\"줄바꿈은 글 부분에서는 괜찮다\\n{d}\\t끝\"\n"
                  "g = f'{f\"{d}\"}'\n"
                  'h = f"""{\n    d\n}"""\n').encode("utf-8")
        self.assertEqual(fc.find_py312_only_fstrings(source), [])

    def test_step_fails_on_a_bad_file_and_passes_on_clean_files(self):
        tmp, root = make_root()
        self.addCleanup(tmp.cleanup)
        (root / "pipeline" / "bad.py").write_text('d = {"x": 1}\na = f"{d["x"]}"\n', encoding="utf-8")
        step = fc.step_fstrings(root, ["pipeline/bad.py"])
        self.assertEqual(step.status, fc.FAIL)
        self.assertIn("pipeline/bad.py:2:", step.detail)
        self.assertEqual(fc.step_fstrings(root, ["pipeline/x.py"]).status, fc.PASS)
        self.assertEqual(fc.step_fstrings(root, []).status, fc.PASS)

    def test_the_repo_itself_has_no_python_312_only_fstrings(self):
        files = fc.all_python_files(_bootstrap.ROOT)
        self.assertGreater(len(files), 50)
        self.assertEqual(fc.step_fstrings(_bootstrap.ROOT, files).status, fc.PASS)


class FindExecutableTest(unittest.TestCase):
    def test_which_wins_then_the_interpreter_folder_then_none(self):
        self.assertEqual(fc.find_executable("actionlint", lambda name: "/usr/bin/actionlint"), "/usr/bin/actionlint")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "vermin.exe").write_text("", encoding="utf-8")
            with mock.patch.object(fc.sys, "executable", str(Path(tmp) / "python")):
                self.assertEqual(Path(fc.find_executable("vermin", lambda name: None)).name, "vermin.exe")
                self.assertIsNone(fc.find_executable("actionlint", lambda name: None))


class MainAndRenderTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = make_root()
        self.addCleanup(self.tmp.cleanup)

    def run_main(self, argv, runner, **kwargs):
        lines = []
        found = fake_finder(actionlint="/bin/actionlint", vermin="/bin/vermin") if kwargs.get("tools", True) else fake_finder()
        with mock.patch.object(fc, "find_executable", found):
            code = fc.main(["--root", str(self.root)] + argv, runner=runner, which=lambda name: None, module_ok=kwargs.get("module_ok", lambda name: True), out=lines.append)
        return code, lines

    def test_all_pass_exits_0_and_prints_a_table(self):
        code, lines = self.run_main([], FakeRunner(base_rules()))
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("검증 사다리 (기준 origin/main 대비 바뀐 .py"))
        self.assertTrue(any(line.startswith("결과: 통과 (실패 0 · 건너뜀 ") for line in lines))

    def test_a_failed_step_exits_1(self):
        rules = base_rules(tests=(has("unittest"), (1, "", "FAILED (failures=1)\n")), vermin=(has("vermin"), (0, "Minimum required versions: 3.10\n", "")))
        code, lines = self.run_main([], FakeRunner(rules))
        self.assertEqual(code, 1)
        self.assertTrue(any(line.startswith("결과: 실패 (실패 1") for line in lines))

    def test_skipped_steps_are_not_counted_as_passes_and_the_report_says_what_to_write(self):
        code, lines = self.run_main([], FakeRunner(base_rules()), module_ok=lambda name: False, tools=False)
        text = "\n".join(lines)
        self.assertEqual(code, 3)                                            # 실패는 없지만 불완전: 종료 코드로도 '통과'가 아니다
        self.assertIn("결과: 불완전", text)
        self.assertIn("건너뛴 검증은 통과가 아닙니다", text)                    # 보고에 '실행 필요'로 적도록 알린다
        for name in ("actionlint", "pyflakes", "vermin(3.10 이하)"):
            self.assertIn(name, text.split("실행 필요:")[1])

    def test_json_output_has_the_steps(self):
        code, lines = self.run_main(["--json"], FakeRunner(base_rules()))
        data = json.loads(lines[0])
        self.assertEqual((data["base"], data["result"]), ("origin/main", "통과"))
        code, lines = self.run_main(["--json"], FakeRunner(base_rules()), tools=False)
        self.assertEqual((json.loads(lines[0])["result"], code), ("불완전", 3))
        self.assertEqual(len(data["steps"]), 6)
        self.assertEqual({"name", "status", "detail", "seconds"}, set(data["steps"][0]))

    def test_a_folder_that_is_not_the_repo_root_exits_2(self):
        with tempfile.TemporaryDirectory() as empty:
            lines = []
            code = fc.main(["--root", empty], runner=FakeRunner(), out=lines.append)
        self.assertEqual(code, 2)
        self.assertIn("사용법 오류", lines[0])


class DefaultRunnerTest(unittest.TestCase):
    def test_runs_a_real_command_and_decodes_utf8(self):
        code, out, err = fc.default_runner([sys.executable, "-X", "utf8", "-c", "print('안녕')"], Path.cwd(), 30)
        self.assertEqual((code, out.strip(), err), (0, "안녕", ""))

    def test_timeout_and_missing_program_become_exit_codes_not_exceptions(self):
        code, _, err = fc.default_runner([sys.executable, "-c", "import time; time.sleep(30)"], Path.cwd(), 1)
        self.assertEqual(code, 124)
        self.assertIn("중단", err)
        code, _, err = fc.default_runner(["this-program-does-not-exist-xyz"], Path.cwd(), 5)
        self.assertEqual(code, 127)


if __name__ == "__main__":
    unittest.main()
