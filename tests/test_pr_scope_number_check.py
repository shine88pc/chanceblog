"""`pr-scope-check.yml` 의 수동 입력 `pr_number` 형식 검사 — 확인 032 ②(운영자 승인, 이슈 #254), 결함 D-438.

배경: 범위 검사 워크플로는 수동 실행(`workflow_dispatch`)의 문자열 입력 `pr_number` 를 아무 검사 없이 환경변수 `PR_NUMBER` 로 받아 `gh api repos/…/pulls/${PR_NUMBER}`·`gh pr comment "$PR_NUMBER"` 에 썼다.
같은 종류의 입력을 받는 `issue-edit.yml` 은 첫 단계에서 `^[1-9][0-9]{0,8}$` 를 검사하는데 이쪽만 빠져 있었다(독립 감사 BA-S1-11, 제안 T3-3). 입력은 쓰기 권한이 있는 사람만 줄 수 있고 셸 명령에 보간하지는 않지만
(env 로 받아 `"$PR_NUMBER"` 로만 읽는다) 앞자리 0·너무 긴 숫자·명령 조각이 API 주소와 `gh` 인자에 들어가게 두지 않는다.

이 시험이 지키는 것
 1. 첫 단계가 형식 검사다(체크아웃·설치·`gh` 보다 앞, `uses` 없음, 식 보간 없음, `issue-edit.yml` 과 같은 정규식 — 러너의 상수와도 같다).
 2. 진짜 bash 로 그 단계를 돌려 값 표대로 통과·실패하고, 명령 조각은 실행되지 않으며 실패 문구에 값이 되풀이되지 않는다.
 3. 실패하면 뒤 단계가 하나도 돌지 않는다(`always()` 가 붙은 코멘트 단계도 `steps.info.outputs.issue` 가 비어 건너뛴다).
 4. 검증기: 진짜 파일은 워크플로 규칙(WF-1–9, 특히 WF-4 의 `inputs` 계열)에 걸리지 않고, 검사를 `${{ inputs.pr_number }}` 직접 보간으로 쓰면 걸린다.
 5. 문서와 결함 행.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _bootstrap
from pipeline.edits import runner
from workflow_expr_helpers import Expr

try:
    import yaml
except ImportError:  # pragma: no cover - CI 에는 항상 있다
    yaml = None

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

NEEDS_YAML = unittest.skipUnless(yaml is not None, "PyYAML(requirements-dev.txt)이 필요합니다(CI 에서는 항상 실행됩니다)")
SCOPE = "pr-scope-check.yml"
SCOPE_REL = ".github/workflows/pr-scope-check.yml"
STEP_NAME = "PR 번호 형식 검사"
PATTERN = f"^{runner.ISSUE_NUMBER_PATTERN}$"


def load(name):
    """`.github/workflows/<name>` 을 읽는다(YAML 1.1 은 키 `on` 을 True 로 읽어 `on` 으로 되돌린다)."""
    data = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


def steps_of(name=SCOPE, job="scope"):
    return load(name)["jobs"][job]["steps"]


def find_bash():
    """단계의 셸을 돌릴 bash. Windows 에서는 WSL 런처가 아니라 Git for Windows 의 것을 찾는다."""
    if os.name != "nt":
        return shutil.which("bash")
    candidates = []
    git = shutil.which("git")
    if git:
        top = Path(git).resolve().parent.parent
        candidates += [top / "bin" / "bash.exe", top / "usr" / "bin" / "bash.exe"]
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(name):
            candidates.append(Path(os.environ[name]) / "Git" / "bin" / "bash.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


BASH = find_bash()
needs_bash = unittest.skipUnless(BASH, "bash 가 없어 단계의 셸 스크립트를 돌려 보지 못했다(Actions 의 ubuntu 에는 있다)")

VALID = ("1", "7", "42", "100", "123456789", "999999999", "100000000")
INVALID = ("", "0", "00", "01", "007", "0123", "1234567890", "99999999999", "12a", "a12", "-1", "+1", "1.5", "1e3", "0x1f", " 1", "1 ", "1 2", "1\n2", "12\n", "\n12", "12\r",
           chr(0xFF11) + chr(0xFF12), chr(0x0663), "#12", "PR-12", "12abc", "$(touch pwned)", "1; touch pwned", "`touch pwned`", "1 && touch pwned", "1|touch pwned", "../../x",
           "$PR_NUMBER", "${PR_NUMBER}", "'1'", '"1"', "1" * 10)


@NEEDS_YAML
class FirstStepStructureTest(unittest.TestCase):
    def setUp(self):
        self.data = load(SCOPE)
        self.job = self.data["jobs"]["scope"]
        self.steps = self.job["steps"]

    def test_the_first_step_is_the_number_check_and_runs_before_any_other_step(self):
        first = self.steps[0]
        self.assertEqual(first.get("name"), STEP_NAME)
        for key in ("uses", "if", "with", "env", "continue-on-error", "shell", "working-directory", "id"):
            self.assertNotIn(key, first, key)                            # 체크아웃·설치보다 먼저 도는 순수 셸 단계다
        script = first["run"]
        self.assertIn("set -euo pipefail", script)
        self.assertIn('"$PR_NUMBER"', script)
        self.assertIn(PATTERN, script)                                   # 러너(ISSUE_NUMBER_PATTERN)·issue-edit.yml 첫 단계와 같은 규칙
        self.assertIn("exit 1", script)
        self.assertNotIn("${{", script)                                  # 번호를 셸에 보간하지 않고 env 로 읽는다
        self.assertIn("PR_NUMBER", self.job["env"])
        self.assertIn("inputs.pr_number", self.job["env"]["PR_NUMBER"])  # 수동 입력이 이 env 로만 들어온다

    def test_everything_else_keeps_its_order_after_the_check(self):
        names = [step.get("uses") or step.get("name") for step in self.steps]
        self.assertEqual(names[0], STEP_NAME)
        self.assertEqual(names[1], "actions/checkout@v6")
        self.assertEqual(names[2], "actions/setup-python@v6")
        self.assertEqual(names[3:], ["의존성 설치", "PR 과 연결된 이슈 찾기", "요청 범위 검증", "PR 에 결과 코멘트"])
        self.assertEqual(self.steps[1]["with"], {"ref": "${{ github.event.repository.default_branch }}", "fetch-depth": 0})        # 검증 도구는 기본 브랜치의 코드로(그대로)

    def test_the_regular_expression_is_the_same_text_as_the_issue_edit_workflows_first_step(self):
        other = steps_of("issue-edit.yml", "edit")[0]["run"]
        found_other = re.search(r"=~ (\^[^ ]+\$) \]\]", other)
        found_here = re.search(r"=~ (\^[^ ]+\$) \]\]", self.steps[0]["run"])
        self.assertIsNotNone(found_other)
        self.assertIsNotNone(found_here)
        self.assertEqual(found_here.group(1), found_other.group(1))
        self.assertEqual(found_here.group(1), PATTERN)
        self.assertEqual(runner.ISSUE_NUMBER_PATTERN, r"[1-9][0-9]{0,8}")

    def test_the_message_is_fixed_and_does_not_repeat_the_value(self):
        script = self.steps[0]["run"]
        self.assertIn("PR 번호는 1", script)
        self.assertIn("앞자리 0 불가", script)
        echoes = [line for line in script.splitlines() if "echo" in line]
        self.assertEqual(len(echoes), 1)
        self.assertNotIn("$", echoes[0])                                 # 값(또는 어떤 변수)도 로그에 되풀이하지 않는다 — `::error::` 같은 워크플로 명령 주입 방지
        self.assertIn(">&2", echoes[0])

    def test_no_run_step_interpolates_the_manual_input_or_the_pull_request_text(self):
        for step in self.steps:
            run = str(step.get("run", ""))
            self.assertNotRegex(run, r"\$\{\{\s*(?:github\.event\.inputs|inputs)\.", step.get("name"))
            self.assertNotRegex(run, r"\$\{\{\s*github\.(?:event\.pull_request|head_ref)", step.get("name"))

    def test_the_manual_input_is_still_a_required_string_and_the_triggers_did_not_change(self):
        triggers = vr._triggers(self.data)
        self.assertEqual(set(triggers), {"pull_request", "workflow_dispatch"})
        self.assertEqual(triggers["pull_request"], {"types": ["opened", "synchronize", "reopened", "ready_for_review"]})
        inputs = triggers["workflow_dispatch"]["inputs"]
        self.assertEqual(list(inputs), ["pr_number"])
        self.assertEqual((inputs["pr_number"]["type"], inputs["pr_number"]["required"]), ("string", True))
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        self.assertEqual(self.job["permissions"], {"contents": "read", "pull-requests": "write", "issues": "read"})

    def test_a_failing_first_step_leaves_no_later_step_running(self):
        """GitHub 규칙: `if` 에 상태 함수가 없으면 `success()` 가 앞에 붙어 건너뛰고, `always()` 가 붙은 단계는 식을 계산한다 — 이 워크플로의 `always()` 단계는 `steps.info.outputs.issue` 가
        비어 있으면(첫 단계가 실패해 `info` 단계가 돌지 않았으니 비어 있다) 거짓이다."""
        ctx = {"steps": {"info": {"outputs": {"issue": ""}}}}
        for step in self.steps[1:]:
            condition = step.get("if")
            self.assertNotIn("continue-on-error", step, step.get("name"))
            if condition is None:
                continue                                                   # 암묵적 success() — 앞 단계가 실패했으니 건너뛴다
            source = str(condition).strip()
            if source.startswith("${{"):
                source = source[3:-2]
            self.assertNotRegex(source, r"\b(?:failure|cancelled)\(\)", step.get("name"))      # 실패 뒤에 도는 단계는 이 시험이 계산하지 못한다 — 쓰게 되면 먼저 고친다
            if re.search(r"\balways\(\)", source):
                source = re.sub(r"\balways\(\)", "true", source)
                self.assertFalse(Expr(source, ctx).parse(), step.get("name"))


class FirstStepBashTest(unittest.TestCase):
    """단계의 `run:` 을 진짜 bash 로 돌린다(GitHub·저장소에는 아무것도 쓰지 않는다)."""

    def run_step(self, value, tmp):
        script = Path(tmp) / "check.sh"
        script.write_text(steps_of()[0]["run"], encoding="utf-8", newline="\n")
        env = {**os.environ, "PR_NUMBER": value, "MSYS_NO_PATHCONV": "1", "MSYS2_ARG_CONV_EXCL": "*"}
        env.pop("GITHUB_OUTPUT", None)
        return subprocess.run([BASH, "-e", script.as_posix()], cwd=str(tmp), env=env, capture_output=True, timeout=120)

    @NEEDS_YAML
    @needs_bash
    def test_valid_numbers_pass_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            for value in VALID:
                with self.subTest(value=value):
                    done = self.run_step(value, tmp)
                    self.assertEqual((done.returncode, done.stdout, done.stderr), (0, b"", b""))

    @NEEDS_YAML
    @needs_bash
    def test_every_bad_value_fails_with_the_fixed_message_and_runs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            for value in INVALID:
                with self.subTest(value=value):
                    done = self.run_step(value, tmp)
                    self.assertEqual(done.returncode, 1, (value, done.stdout, done.stderr))
                    self.assertEqual(done.stdout, b"")
                    message = done.stderr.decode("utf-8", "replace")
                    self.assertIn("PR 번호는 1", message)
                    self.assertEqual(len(message.strip().splitlines()), 1)
                    for piece in ("touch", "pwned", "PR_NUMBER", "::"):
                        self.assertNotIn(piece, message)                    # 값을 되풀이하지 않는다
            self.assertEqual(sorted(path.name for path in Path(tmp).iterdir()), ["check.sh"])      # `touch pwned` 같은 명령 조각이 실행되지 않았다

    def test_the_same_table_holds_for_the_regular_expression_itself(self):
        """bash 가 없어도 규칙 자체를 파이썬으로 같은 표에 대 본다(러너의 `valid_issue_number` 와 같은 정규식 — 같은 값 표에서 같은 답이어야 한다)."""
        for value in VALID:
            self.assertIsNotNone(re.fullmatch(runner.ISSUE_NUMBER_PATTERN, value), value)
            self.assertEqual(runner.valid_issue_number(value), int(value), value)
        for value in INVALID:
            self.assertIsNone(re.fullmatch(runner.ISSUE_NUMBER_PATTERN, value), repr(value))
            self.assertIsNone(runner.valid_issue_number(value), repr(value))


@NEEDS_YAML
class ValidatorTest(unittest.TestCase):
    def test_the_real_workflow_passes_the_workflow_rules_with_no_input_warning(self):
        self.assertEqual([f.line() for f in vr.check_workflows(ROOT, [SCOPE_REL])], [])          # WF-4 의 `inputs` 계열을 포함한 모든 규칙
        self.assertEqual(vr.check_workflow_write_permissions(ROOT, [SCOPE_REL]), [])
        self.assertEqual(vr.check_telegram_secrets(ROOT, [SCOPE_REL]), [])

    def findings_for(self, mutate):
        text = (ROOT / SCOPE_REL).read_text(encoding="utf-8")
        text = mutate(text)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / SCOPE_REL
            path.parent.mkdir(parents=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            return [(f.check, f.level, f.message) for f in vr.check_workflows(Path(tmp), [SCOPE_REL])]

    def swap_in_check(self, new):
        def mutate(text):
            self.assertEqual(text.count('"$PR_NUMBER" =~'), 1)
            return text.replace('"$PR_NUMBER" =~', new + " =~")
        return mutate

    def test_writing_the_check_with_a_direct_input_interpolation_is_flagged_as_an_inputs_warning(self):
        found = self.findings_for(self.swap_in_check('"${{ inputs.pr_number }}"'))
        self.assertEqual([item[:2] for item in found], [("WF-4", "WARN")])
        self.assertIn("inputs", found[0][2])

    def test_writing_the_check_with_pull_request_text_is_an_error(self):
        found = self.findings_for(self.swap_in_check('"${{ github.event.pull_request.title }}"'))
        self.assertEqual([item[:2] for item in found], [("WF-4", "ERROR")])


# ----------------------------------------------------------------------------
# 문서와 결함 행
# ----------------------------------------------------------------------------
def doc(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def row(text, start):
    found = [line for line in text.splitlines() if line.startswith(start)]
    assert len(found) == 1, (start, len(found))
    return found[0]


class DocsTest(unittest.TestCase):
    def test_the_edit_request_guide_lists_the_check_in_its_table_and_its_manual_run_notes(self):
        text = doc("docs/ISSUE_EDITS.md")
        line = row(text, "| 수동 실행의 PR 번호")
        for needle in ("`pr_number`", "`^[1-9][0-9]{0,8}$`", "첫 단계", "이후 단계는 돌지 않", "`pr-scope-check.yml`", "issue-edit"):
            self.assertIn(needle, line, needle)
        bullet = row(text, "- 범위 검사(`pr-scope-check.yml`)의 수동 실행")
        for needle in ("`pr_number`", "숫자(1–999999999, 앞자리 0 불가)", "첫 단계(체크아웃 전)", "D-438"):
            self.assertIn(needle, bullet, needle)

    def test_the_actions_guide_says_the_manual_input_is_checked_first(self):
        text = doc("docs/ACTIONS_GUIDE.md")
        section = text[text.index("### 6-7."):text.index("### 6-8.")]
        for needle in ("수동: `pr_number`(필수", "앞자리 0 불가", "첫 단계에서 바로 실패"):
            self.assertIn(needle, section, needle)

    def test_the_input_rule_names_the_number_check_next_to_the_inputs_warning(self):
        line = row(doc("docs/SECURITY_GUARDRAILS.md"), "| G-A2 |")
        for needle in ("`issue_number`·`pr_number`", "첫 단계에서 형식(`^[1-9][0-9]{0,8}$`)", "D-438", "tests/test_pr_scope_number_check.py"):
            self.assertIn(needle, line, needle)

    def test_the_defect_row_is_after_d_428_and_names_the_files_and_the_tests(self):
        register = doc("docs/DEFECT_REGISTER.md")
        self.assertGreater(register.index("| **D-438** |"), register.index("| **D-428** |"))
        line = row(register, "| **D-438** |")
        for needle in ("pr-scope-check.yml", "`pr_number`", "`^[1-9][0-9]{0,8}$`", "issue-edit.yml", "tests/test_pr_scope_number_check.py", "해결"):
            self.assertIn(needle, line, needle)


if __name__ == "__main__":
    unittest.main()
