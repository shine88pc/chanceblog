"""워크플로 검증기의 사각 닫기(독립 감사 BA-S1-4, 결함 D-409) — WF-4 를 env·단계 출력·job 출력·matrix 와 github-script 의 script 까지, WF-3 을 issue_comment·pull_request_review·
pull_request_review_comment 까지(허용 목록), 쓰기 권한 허용 표(WF-1 의 한 갈래).

식 치환(`${{ … }}`)은 셸·스크립트가 읽기 전에 글자로 들어간다. 옛 WF-4 는 run 안의 `github.*` 낱말만 봐서 `env: T: ${{ github.event.issue.title }}` 를 거쳐 `${{ env.T }}` 로 되돌아오는 길·github-script 의 script·
단계·job 출력·matrix 가 지나갔다. 새 규칙은 값이 신뢰할 수 없는 곳에서 왔다고 알 수 있으면 오류, 알 수 없으면 경고다(저장소의 워크플로 20개는 이 낱말을 run 에 쓰지 않아 새 지적 0). 이 시험은 네트워크·GitHub 없이 임시 폴더에
워크플로 글을 써서 돌린다. 가짜 값만 쓴다. `workflow_run` 은 이 묶음이 다루지 않는다(다른 갈래).
"""
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap
from real_repo_helpers import run_checks_once

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover - CI 에는 항상 있다
    yaml = None

REAL = _bootstrap.ROOT
NEEDS_YAML = unittest.skipUnless(yaml is not None, "PyYAML(requirements-dev.txt)이 필요합니다(CI 에서는 항상 실행됩니다)")
TITLE = "${{ github.event.issue.title }}"
CHANCE = "chance" + "blog.yml"                     # 실제 워크플로 파일 이름(이어 붙여 적는다)


def job(steps, name="j", env="", strategy="", outputs="", needs=""):
    """job 한 개의 YAML 글. steps 는 `- …` 들(줄 맞춤은 알아서), env·strategy·outputs 는 job 수준 키 블록."""
    head = f"{name}:\n  name: 가\n  runs-on: ubuntu-latest\n  timeout-minutes: 5\n"
    for block in (needs, env, strategy, outputs):
        if block:
            head += textwrap.indent(textwrap.dedent(block).strip("\n"), "  ") + "\n"
    return head + "  steps:\n" + textwrap.indent(textwrap.dedent(steps).strip("\n"), "    ") + "\n"


def workflow(*jobs, on="{workflow_dispatch: {}}", top="", perms="  contents: read"):
    text = f'name: "[공통] w"\non: {on}\npermissions:\n{perms}\n{top}jobs:\n'
    return text + "".join(textwrap.indent(one, "  ") for one in jobs)


class WorkflowCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, text, name="w.yml"):
        path = self.root / ".github" / "workflows" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return f".github/workflows/{name}"

    def check(self, text, name="w.yml"):
        rel = self.write(text, name)
        return vr.check_workflows(self.root, [rel])

    def of(self, text, check, name="w.yml"):
        return [(finding.level, finding.message) for finding in self.check(text, name) if finding.check == check]

    def levels(self, text, check="WF-4"):
        return [level for level, _ in self.of(text, check)]


@NEEDS_YAML
class EnvIndirectionTest(WorkflowCase):
    """`env: T: ${{ github.event.issue.title }}` 뒤 run 의 `${{ env.T }}` — 식 치환이라 셸이 읽기 전에 제목이 글자로 들어간다."""

    def run_step(self, run, **kw):
        return workflow(job(f"- run: {run}\n", **kw))

    def test_a_job_env_that_holds_an_untrusted_expression_is_an_error_when_interpolated_into_run(self):
        text = self.run_step('echo "${{ env.TITLE }}"', env=f"env:\n  TITLE: {TITLE}")
        found = self.of(text, "WF-4")
        self.assertEqual([level for level, _ in found], ["ERROR"])
        self.assertIn("env.title", found[0][1])
        self.assertIn("신뢰할 수 없는 입력이 거쳐 오는", found[0][1])
        self.assertEqual(len(found[0][1].splitlines()), 1)

    def test_the_other_two_scopes_and_any_untrusted_name_are_found_too(self):
        for scope, text in (
            ("workflow", workflow(job('- run: echo "${{ env.T }}"\n'), top=f"env:\n  T: {TITLE}\n")),
            ("step", workflow(job(f'- run: echo "${{{{ env.T }}}}"\n  env:\n    T: {TITLE}\n'))),
            ("branch name", workflow(job('- run: echo "${{ env.T }}"\n', env="env:\n  T: ${{ github.head_ref }}"))),
            ("ref name", workflow(job('- run: echo "${{ env.T }}"\n', env="env:\n  T: ${{ github.ref_name }}"))),
            ("label", workflow(job('- run: echo "${{ env.T }}"\n', env="env:\n  T: ${{ github.event.label.name }}"))),
            ("inside a function", workflow(job('- run: echo "${{ format(\'{0}\', env.T) }}"\n', env=f"env:\n  T: {TITLE}"))),
            ("inside a condition", workflow(job('- run: echo "${{ env.T || \'x\' }}"\n', env=f"env:\n  T: {TITLE}"))),
        ):
            with self.subTest(scope=scope):
                self.assertEqual(self.levels(text), ["ERROR"])

    def test_the_name_is_matched_without_regard_to_case_and_the_inner_scope_wins(self):
        self.assertEqual(self.levels(workflow(job('- run: echo "${{ env.title }}"\n', env=f"env:\n  TITLE: {TITLE}"))), ["ERROR"])
        self.assertEqual(self.levels(workflow(job('- run: echo "${{ env.TITLE }}"\n', env=f"env:\n  title: {TITLE}"))), ["ERROR"])
        # 단계의 env 가 job 의 env 를 덮어쓴다 — 안쪽이 고정 값이면 통과, 안쪽이 신뢰할 수 없는 식이면 오류
        inner_safe = workflow(job(f'- run: echo "${{{{ env.T }}}}"\n  env:\n    T: fixed\n', env=f"env:\n  T: {TITLE}"))
        self.assertEqual(self.levels(inner_safe), [])
        inner_bad = workflow(job(f'- run: echo "${{{{ env.T }}}}"\n  env:\n    T: {TITLE}\n', env="env:\n  T: fixed"))
        self.assertEqual(self.levels(inner_bad), ["ERROR"])

    def test_a_chain_of_envs_ending_in_an_untrusted_expression_is_an_error(self):
        env = f"env:\n  A: ${{{{ env.B }}}}\n  B: ${{{{ env.C }}}}\n  C: {TITLE}"
        self.assertEqual(self.levels(self.run_step('echo "${{ env.A }}"', env=env)), ["ERROR"])
        loop = "env:\n  A: ${{ env.B }}\n  B: ${{ env.A }}"                        # 서로를 가리키는 고리는 끝없이 따라가지 않는다
        self.assertEqual(self.levels(self.run_step('echo "${{ env.A }}"', env=loop)), [])

    def test_a_fixed_env_value_and_safe_expressions_are_not_flagged(self):
        for env in ("env:\n  T: fixed text", "env:\n  T: 3", "env:\n  T: true", "env:\n  T: ${{ github.sha }}", "env:\n  T: ${{ github.run_id }}-${{ runner.os }}",
                    "env:\n  T: ${{ secrets.SOME_SECRET }}", "env:\n  T: ${{ vars.SOME }}"):
            with self.subTest(env=env):
                self.assertEqual(self.of(self.run_step('echo "${{ env.T }}"', env=env), "WF-4"), [])

    def test_an_env_with_no_definition_is_only_a_warning(self):
        found = self.of(self.run_step('echo "${{ env.NOWHERE }}"'), "WF-4")
        self.assertEqual([level for level, _ in found], ["WARN"])
        self.assertIn("env.nowhere", found[0][1])
        self.assertIn("출처를 알 수 없습니다", found[0][1])

    def test_passing_the_value_through_env_and_reading_it_in_the_shell_is_clean(self):
        text = workflow(job(f'- run: echo "$TITLE"\n  env:\n    TITLE: {TITLE}\n'))
        self.assertEqual([f for f in self.check(text) if f.check == "WF-4"], [])

    def test_the_old_direct_check_is_unchanged(self):
        self.assertEqual(self.levels(self.run_step('echo "${{ github.event.issue.title }}"')), ["ERROR"])
        self.assertEqual(self.levels(self.run_step('echo "${{ inputs.name }}"')), ["WARN"])
        self.assertEqual(self.levels(self.run_step('echo "${{ github.sha }}"')), [])

    def test_only_run_and_script_are_sinks_not_env_if_name_or_with(self):
        text = workflow(job(f'- name: x ${{{{ env.T }}}}\n  if: ${{{{ env.T != \'\' }}}}\n  run: echo hi\n  env:\n    U: ${{{{ env.T }}}}\n', env=f"env:\n  T: {TITLE}"))
        self.assertEqual([f for f in self.check(text) if f.check == "WF-4"], [])


@NEEDS_YAML
class GithubScriptTest(WorkflowCase):
    SCRIPT = "- uses: actions/github-script@v7\n  with:\n    script: |\n      {line}\n"

    def script_step(self, line, **kw):
        return workflow(job(self.SCRIPT.format(line=line), **kw))

    def test_an_untrusted_expression_inside_the_script_input_is_an_error(self):
        found = self.of(self.script_step('console.log("${{ github.event.issue.title }}")'), "WF-4")
        self.assertEqual([level for level, _ in found], ["ERROR"])
        self.assertIn("github-script 의 script", found[0][1])
        self.assertIn("process.env", found[0][1])

    def test_every_untrusted_context_is_an_error_in_the_script_too(self):
        for name in ("github.head_ref", "github.ref_name", "github.event.comment.body", "github.event.pull_request.title", "toJSON(github.event)", "github['event']['issue']['body']"):
            with self.subTest(name=name):
                self.assertEqual(self.levels(self.script_step('console.log("${{ %s }}")' % name)), ["ERROR"])

    def test_env_and_outputs_and_matrix_follow_the_same_rules_as_run(self):
        self.assertEqual(self.levels(self.script_step('console.log("${{ env.T }}")', env=f"env:\n  T: {TITLE}")), ["ERROR"])
        self.assertEqual(self.levels(self.script_step('console.log("${{ env.T }}")', env="env:\n  T: fixed")), [])
        self.assertEqual(self.levels(self.script_step('console.log("${{ env.NOWHERE }}")')), ["WARN"])
        self.assertEqual(self.levels(self.script_step('console.log("${{ steps.a.outputs.t }}")')), ["WARN"])
        self.assertEqual(self.levels(self.script_step('console.log("${{ inputs.name }}")')), ["WARN"])

    def test_safe_values_in_the_script_are_not_flagged(self):
        for line in ('console.log("${{ github.run_id }}")', 'console.log(process.env.TITLE)', 'const t = context.payload.issue.title', 'console.log("${{ github.sha }} ${{ runner.os }}")'):
            with self.subTest(line=line):
                self.assertEqual(self.of(self.script_step(line), "WF-4"), [])

    def test_the_action_name_is_matched_loosely_but_other_actions_script_inputs_are_not_read(self):
        sha = "0" * 40
        for uses in ("actions/github-script@v7", "Actions/GitHub-Script@v6", f"actions/github-script@{sha}"):
            with self.subTest(uses=uses):
                text = workflow(job(f"- uses: {uses}\n  with:\n    script: |\n      console.log('${{{{ github.head_ref }}}}')\n"))
                self.assertEqual(self.levels(text), ["ERROR"])
        other = workflow(job("- uses: actions/checkout@v6\n  with:\n    script: |\n      console.log('${{ github.head_ref }}')\n"))
        self.assertEqual(self.of(other, "WF-4"), [])                                     # github-script 가 아니면 script 는 입력이 아니다
        no_script = workflow(job("- uses: actions/github-script@v7\n  with:\n    github-token: ${{ github.token }}\n"))
        self.assertEqual(self.of(no_script, "WF-4"), [])


@NEEDS_YAML
class StepAndJobOutputTest(WorkflowCase):
    def test_an_output_of_a_step_that_took_untrusted_input_is_an_error_when_interpolated(self):
        """감사 BA-S1-4 의 길: env 로 안전하게 받은 제목을 단계 출력으로 내보낸 뒤 다음 단계가 식 치환으로 run 에 넣는다."""
        steps = f"""\
- id: a
  run: echo "t=$TITLE" >> "$GITHUB_OUTPUT"
  env:
    TITLE: {TITLE}
- run: echo "${{{{ steps.a.outputs.t }}}}"
"""
        found = self.of(workflow(job(steps)), "WF-4")
        self.assertEqual([level for level, _ in found], ["ERROR"])
        self.assertIn("steps.a.outputs", found[0][1])

    def test_the_input_may_reach_the_step_through_a_job_env_read_as_a_shell_variable(self):
        steps = """\
- id: a
  run: echo "t=${TITLE}" >> "$GITHUB_OUTPUT"
- run: echo "${{ steps.a.outputs.t }}"
"""
        text = workflow(job(steps, env=f"env:\n  TITLE: {TITLE}"))
        self.assertEqual(self.levels(text), ["ERROR"])
        text = workflow(job(steps.replace('"t=${TITLE}"', '"t=${OTHER}"'), env=f"env:\n  TITLE: {TITLE}\n  OTHER: fixed"))
        self.assertEqual(self.levels(text), ["WARN"])                                    # 신뢰할 수 없는 env 를 읽지 않으면 오류가 아니다

    def test_a_uses_step_given_untrusted_input_has_tainted_outputs(self):
        steps = f"""\
- id: a
  uses: actions/github-script@v7
  with:
    script: |
      return 1
    result-encoding: {TITLE}
- run: echo "${{{{ steps.a.outputs.result }}}}"
"""
        self.assertEqual(self.levels(workflow(job(steps))), ["ERROR"])

    def test_an_output_of_a_step_with_no_untrusted_input_is_only_a_warning(self):
        steps = """\
- id: a
  run: echo "t=$(date)" >> "$GITHUB_OUTPUT"
- run: echo "${{ steps.a.outputs.t }}"
"""
        found = self.of(workflow(job(steps)), "WF-4")
        self.assertEqual([level for level, _ in found], ["WARN"])
        self.assertIn("출처를 알 수 없습니다", found[0][1])

    def test_an_unknown_step_id_is_a_warning(self):
        self.assertEqual(self.levels(workflow(job('- run: echo "${{ steps.nowhere.outputs.x }}"\n'))), ["WARN"])

    def test_a_dynamic_index_is_a_warning(self):
        """색인이 문자열 리터럴이 아니면 어느 단계·job·env 를 읽는지 알 수 없다 — 경고. (키가 고정된 matrix 를 써서 matrix 자체의 경고와 섞이지 않게 한다.)"""
        strategy = "strategy:\n  matrix:\n    id: [a]\n    job: [b]\n    k: [c]"
        for expression in ("steps[matrix.id].outputs.value", "needs[matrix.job].outputs.x", "env[matrix.k]"):
            with self.subTest(expression=expression):
                found = self.of(workflow(job('- run: echo "${{ %s }}"\n' % expression, strategy=strategy)), "WF-4")
                self.assertEqual([level for level, _ in found], ["WARN"])
                self.assertIn("색인으로 읽는 컨텍스트", found[0][1])

    def test_an_output_of_a_job_that_carries_untrusted_input_is_an_error_in_the_next_job(self):
        first = job(f"- id: a\n  run: echo \"t=$TITLE\" >> \"$GITHUB_OUTPUT\"\n  env:\n    TITLE: {TITLE}\n", name="p", outputs="outputs:\n  t: ${{ steps.a.outputs.t }}")
        second = job('- run: echo "${{ needs.p.outputs.t }}"\n', name="q", needs="needs: p")
        found = self.of(workflow(first, second), "WF-4")
        self.assertEqual([level for level, _ in found], ["ERROR"])
        self.assertIn("needs.p.outputs.t", found[0][1])
        direct = job('- run: echo hi\n', name="p", outputs=f"outputs:\n  t: {TITLE}")                    # 출력 값이 곧 신뢰할 수 없는 식
        self.assertEqual(self.levels(workflow(direct, second)), ["ERROR"])
        whole = job('- run: echo "${{ toJSON(needs.p.outputs) }}"\n', name="q", needs="needs: p")      # 출력 이름을 모르는 통째 읽기도 그 job 의 어느 출력이든
        self.assertEqual(self.levels(workflow(first, whole)), ["ERROR"])

    def test_an_output_of_a_job_with_no_untrusted_input_or_an_unknown_job_is_a_warning(self):
        first = job("- id: a\n  run: echo \"t=1\" >> \"$GITHUB_OUTPUT\"\n", name="p", outputs="outputs:\n  t: ${{ steps.a.outputs.t }}")
        second = job('- run: echo "${{ needs.p.outputs.t }}"\n', name="q", needs="needs: p")
        self.assertEqual(self.levels(workflow(first, second)), ["WARN"])
        self.assertEqual(self.levels(workflow(second)), ["WARN"])                                    # 같은 파일에 job p 가 없다


@NEEDS_YAML
class MatrixTest(WorkflowCase):
    RUN = '- run: echo "${{ matrix.k }}"\n'

    def test_a_matrix_written_in_the_same_file_is_fixed_and_passes(self):
        for strategy in ("strategy:\n  matrix:\n    k: [a, b]", "strategy:\n  matrix:\n    k:\n      - 3.10\n      - 3.12", "strategy:\n  matrix:\n    include:\n      - k: a\n      - k: b",
                         "strategy:\n  fail-fast: false\n  matrix:\n    k: [a]\n    other: [x, y]"):
            with self.subTest(strategy=strategy):
                self.assertEqual(self.of(workflow(job(self.RUN, strategy=strategy)), "WF-4"), [])

    def test_a_computed_matrix_or_a_value_with_an_expression_is_a_warning(self):          # 식이 있되 출처가 신뢰할 수 없는 입력은 아닌 값(`github.sha`) — 직접 적은 신뢰할 수 없는 식은 이제 오류(MatrixDirectValueTest)
        for strategy in ("strategy:\n  matrix: ${{ fromJSON(needs.plan.outputs.matrix) }}", "strategy:\n  matrix:\n    k: ${{ fromJSON(needs.plan.outputs.k) }}",
                         "strategy:\n  matrix:\n    k: [a, '${{ github.sha }}']", "strategy:\n  matrix:\n    include:\n      - k: ${{ needs.plan.outputs.k }}"):
            with self.subTest(strategy=strategy):
                found = self.of(workflow(job(self.RUN, strategy=strategy)), "WF-4")
                self.assertEqual([level for level, _ in found], ["WARN"])
                self.assertIn("matrix.k", found[0][1])

    def test_a_key_that_the_matrix_does_not_define_or_a_job_without_a_matrix_is_a_warning(self):
        self.assertEqual(self.levels(workflow(job(self.RUN, strategy="strategy:\n  matrix:\n    other: [a]"))), ["WARN"])
        self.assertEqual(self.levels(workflow(job(self.RUN))), ["WARN"])

    def test_an_excluded_expression_makes_it_a_warning_and_the_names_include_and_exclude_are_not_keys(self):
        strategy = "strategy:\n  matrix:\n    k: [a]\n    exclude:\n      - k: ${{ needs.p.outputs.x }}"
        self.assertEqual(self.levels(workflow(job(self.RUN, strategy=strategy))), ["WARN"])
        self.assertEqual(self.levels(workflow(job('- run: echo "${{ matrix.include }}"\n', strategy="strategy:\n  matrix:\n    include:\n      - k: a"))), ["WARN"])


@NEEDS_YAML
class ReferencesAreReportedOnceTest(WorkflowCase):
    def test_each_distinct_reference_gets_one_finding_and_repeats_do_not_multiply(self):
        run = 'echo "${{ env.T }} ${{ env.T }} ${{ steps.a.outputs.x }} ${{ steps.a.outputs.y }}"'
        found = self.of(workflow(job(f"- run: {run}\n", env=f"env:\n  T: {TITLE}")), "WF-4")
        self.assertEqual(sorted(level for level, _ in found), ["ERROR", "WARN"])           # env.t(오류)와 단계 출력(경고) 한 번씩

    def test_findings_are_one_line_and_carry_the_path(self):
        rel = self.write(workflow(job('- run: echo "${{ env.NOWHERE }}"\n')))
        for finding in vr.check_workflows(self.root, [rel]):
            if finding.check == "WF-4":
                self.assertEqual(len(finding.line().splitlines()), 1)
                self.assertEqual(finding.path, rel)


@NEEDS_YAML
class UntrustedTriggerTest(WorkflowCase):
    TRIGGERS = ("issue_comment", "pull_request_review", "pull_request_review_comment")

    def body(self, on):
        return workflow(job("- run: echo hi\n"), on=on)

    def test_each_trigger_is_an_error_in_every_spelling_of_on(self):
        for trigger in self.TRIGGERS:
            for label, on in ((f"string", trigger), ("list", f"[{trigger}, workflow_dispatch]"), ("mapping", "{%s: {types: [created]}}" % trigger), ("upper", "{%s: {}}" % trigger.upper())):
                with self.subTest(trigger=trigger, on=label):
                    found = self.of(self.body(on), "WF-3")
                    self.assertEqual([level for level, _ in found], ["ERROR"])
                    self.assertIn(trigger, found[0][1])
                    self.assertIn("WF3_UNTRUSTED_TRIGGERS", found[0][1])

    def test_a_workflow_with_two_of_them_gets_two_errors(self):
        self.assertEqual(self.levels(self.body("{issue_comment: {}, pull_request_review: {}}"), "WF-3"), ["ERROR", "ERROR"])

    def test_pull_request_target_is_still_forbidden_and_ordinary_triggers_pass(self):
        self.assertEqual(self.levels(self.body("{pull_request_target: {}}"), "WF-3"), ["ERROR"])
        for on in ("push", "[push, workflow_dispatch]", "{schedule: [{cron: '0 0 * * *'}]}", "{issues: {types: [opened]}}", "{pull_request: {}}", "workflow_call"):
            with self.subTest(on=on):
                self.assertEqual(self.of(self.body(on), "WF-3"), [])

    def test_the_allow_list_is_empty_today_and_opens_only_the_named_file_for_the_named_trigger(self):
        for trigger in self.TRIGGERS:
            self.assertEqual(vr.WF3_UNTRUSTED_TRIGGERS[trigger], (), trigger)
        text = self.body("{issue_comment: {}}")
        with mock.patch.dict(vr.WF3_UNTRUSTED_TRIGGERS, {"issue_comment": ("w.yml",)}):
            self.assertEqual(self.of(text, "WF-3"), [])                                            # 허용한 파일(w.yml)
            self.assertEqual(len(self.of(text, "WF-3", name="other.yml")), 1)                      # 다른 파일은 여전히 오류
            self.assertEqual(len(self.of(self.body("{pull_request_review: {}}"), "WF-3")), 1)      # 다른 트리거도 여전히 오류


@NEEDS_YAML
class WritePermissionTableTest(WorkflowCase):
    def real_map(self):
        found = {}
        for path in sorted((REAL / ".github" / "workflows").glob("*.yml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            for scope, names in vr.write_permissions(data).items():
                found[(path.name, scope)] = names
        return found

    def test_the_table_equals_what_the_real_workflows_grant_in_both_directions(self):
        """표를 만든 지금 파일과 정확히 같다 — 권한이 늘면 검증기가, 줄거나 파일이 바뀌면 이 시험이 알려 표를 함께 고치게 한다."""
        self.assertEqual(self.real_map(), {key: tuple(sorted(value)) for key, value in vr.WORKFLOW_WRITE_PERMISSIONS.items()})
        for (name, _scope), names in vr.WORKFLOW_WRITE_PERMISSIONS.items():
            self.assertEqual(names, tuple(sorted(names)), name)
            self.assertTrue((REAL / ".github" / "workflows" / name).is_file(), name)

    def test_the_real_repository_passes_the_check(self):
        files = [f for f in vr.list_files(REAL) if f.startswith(".github/workflows/")]
        self.assertGreaterEqual(len(files), 15)
        self.assertEqual([f.line() for f in vr.check_workflow_write_permissions(REAL, files)], [])

    def check_new(self, name, text):
        rel = self.write(text, name)
        return [(f.check, f.level, f.message) for f in vr.check_workflow_write_permissions(self.root, [rel])]

    def test_a_new_workflow_with_a_write_permission_is_an_error(self):
        found = self.check_new("brand-new.yml", workflow(job("- run: echo hi\n"), perms="  contents: write"))
        self.assertEqual([(check, level) for check, level, _ in found], [("WF-1", "ERROR")])
        self.assertIn("contents", found[0][2])
        self.assertIn("WORKFLOW_WRITE_PERMISSIONS", found[0][2])
        self.assertIn("최상위", found[0][2])

    def test_a_new_job_a_wider_scope_or_an_added_permission_is_an_error(self):
        for label, name, text in (
            ("new job with write", CHANCE, workflow(job("- run: echo hi\n"), job("- run: echo hi\n", name="extra").replace("  steps:", "  permissions:\n    issues: write\n  steps:"),
                                                              perms="  actions: write\n  contents: write\n  pull-requests: write")),
            ("job write moved to the top", "blogger-en.yml", workflow(job("- run: echo hi\n", name="blogger"), perms="  contents: write")),
            ("one more permission", CHANCE, workflow(job("- run: echo hi\n"), perms="  actions: write\n  contents: write\n  issues: write\n  pull-requests: write")),
            ("job renamed", "pr-scope-check.yml", workflow(job("- run: echo hi\n", name="renamed").replace("  steps:", "  permissions:\n    pull-requests: write\n  steps:"))),
        ):
            with self.subTest(label=label):
                found = self.check_new(name, text)
                self.assertTrue(found and all(item[:2] == ("WF-1", "ERROR") for item in found), found)

    def test_the_same_or_fewer_permissions_than_the_table_are_fine(self):
        same = workflow(job("- run: echo hi\n"), perms="  actions: write\n  contents: write\n  pull-requests: write")
        fewer = workflow(job("- run: echo hi\n"), perms="  contents: write")
        read_only = workflow(job("- run: echo hi\n"), perms="  actions: read\n  contents: read\n  pull-requests: read")
        for label, text in (("same", same), ("fewer", fewer), ("read only", read_only), ("none", workflow(job("- run: echo hi\n"), perms="  {}"))):
            with self.subTest(label=label):
                self.assertEqual(self.check_new(CHANCE, text), [])

    def test_a_workflow_with_no_write_permission_is_not_in_the_table_and_needs_no_row(self):
        self.assertEqual(self.check_new("brand-new.yml", workflow(job("- run: echo hi\n"))), [])
        self.assertEqual(self.check_new("brand-new.yml", workflow(job("- run: echo hi\n"), perms="  contents: read\n  issues: read")), [])

    def test_write_all_at_the_job_level_is_an_error_and_at_the_top_is_left_to_the_older_check(self):
        job_level = workflow(job("- run: echo hi\n").replace("  steps:", "  permissions: write-all\n  steps:"))
        found = self.check_new("brand-new.yml", job_level)
        self.assertEqual([(check, level) for check, level, _ in found], [("WF-1", "ERROR")])
        self.assertIn("write-all", found[0][2])
        top = workflow(job("- run: echo hi\n"), perms="  write-all")
        self.assertEqual(self.check_new("brand-new.yml", top), [])                                  # 최상위 write-all 은 check_workflows 가 낸다(같은 오류를 두 번 내지 않는다)
        self.assertEqual([f.check for f in vr.check_workflows(self.root, [".github/workflows/brand-new.yml"]) if f.check == "WF-1"], ["WF-1"])

    def test_the_shapes_of_permissions_are_read_the_same_way_as_github_does(self):
        self.assertEqual(vr.write_permissions({"permissions": {"contents": "write", "issues": "read"}}), {"*": ("contents",)})
        self.assertEqual(vr.write_permissions({"permissions": "write-all"}), {"*": ("write-all",)})
        self.assertEqual(vr.write_permissions({"permissions": "read-all"}), {})
        self.assertEqual(vr.write_permissions({"permissions": {}}), {})
        self.assertEqual(vr.write_permissions({"jobs": {"a": {"permissions": {"pages": "write", "id-token": "write", "contents": "read"}}, "b": {}, "c": 3}}), {"a": ("id-token", "pages")})
        self.assertEqual(vr.write_permissions({"permissions": {"contents": "Write"}}), {"*": ("contents",)})
        self.assertEqual(vr.write_permissions(None), {})
        self.assertEqual(vr.write_permissions({"permissions": {"contents": None}}), {})
        self.assertEqual(vr.write_permissions({"jobs": ["a", "b"]}), {})        # 깨진 jobs(목록·글)에도 죽지 않는다
        self.assertEqual(vr.write_permissions({"permissions": {"contents": "write"}, "jobs": "x"}), {"*": ("contents",)})

    def test_the_check_is_part_of_run_checks_and_stays_quiet_when_pyyaml_is_missing(self):
        rel = self.write(workflow(job("- run: echo hi\n"), perms="  contents: write"), "brand-new.yml")
        self.assertIn(("WF-1", "ERROR"), [(f.check, f.level) for f in vr.run_checks(self.root)])
        with mock.patch.object(vr, "yaml", None):
            self.assertEqual(vr.check_workflow_write_permissions(self.root, [rel]), [])

    def test_a_workflow_that_does_not_parse_is_left_to_wf_0(self):
        rel = self.write("name: [unclosed\n", "broken.yml")
        self.assertEqual(vr.check_workflow_write_permissions(self.root, [rel]), [])


@NEEDS_YAML
class RealRepositoryTest(unittest.TestCase):
    def test_none_of_the_real_workflows_is_flagged_by_the_new_rules(self):
        files = [f for f in vr.list_files(REAL) if f.startswith(".github/workflows/")]
        self.assertGreaterEqual(len(files), 15)
        found = [f.line() for f in vr.check_workflows(REAL, files) if f.check in ("WF-3", "WF-4")]
        self.assertEqual(found, [])

    def test_the_whole_validator_has_no_error_and_no_workflow_finding_for_the_real_repository(self):
        """검증기 전체(run_checks)가 저장소에 오류 0 이고 워크플로 권한·트리거·주입 지적(WF-1·WF-3·WF-4)이 없다 — 이 변경이 시작점의 출력(오류 0·경고는 문서·Liquid)에 지적을 더하지 않는다."""
        findings = run_checks_once(REAL)                           # 진짜 저장소의 결과는 한 프로세스 안에서 한 번만 계산해 나눠 쓴다(tests/real_repo_helpers.py)
        self.assertEqual([f.line() for f in findings if f.level == "ERROR"], [])
        self.assertEqual([f.line() for f in findings if f.check in ("WF-1", "WF-3", "WF-4")], [])


TAINTED_STEP = '- id: a\n  env:\n    X: ' + TITLE + '\n  run: echo "t=$X" >> "$GITHUB_OUTPUT"\n'          # 신뢰할 수 없는 입력을 받아 출력 파일에 쓰는 단계


@NEEDS_YAML
class WholeContextReadTest(WorkflowCase):
    """검증자 S 의 V4(a) — 맵 통째 읽기(`toJSON(env)`·`join(env.*, ',')`·`toJSON(steps)`·`toJSON(needs)`·`toJSON(matrix)`): github 컨텍스트는 `_WHOLE_CONTEXT`·`.*` 로 막는데
    env·steps·needs·matrix 는 같은 처리가 없어 오염된 항목이 든 맵을 통째로 읽어도 지적이 0 이었다. 오염된 항목이 하나라도 있으면 오류, 없어도 통째 읽기는 항목을 하나씩 알 수 없어 경고."""

    def levels_of(self, text):
        return self.levels(text)

    def test_a_whole_env_read_with_a_tainted_entry_is_an_error_in_every_spelling(self):
        for expression in ("toJSON(env)", "join(env.*, ',')", "format('{0}', env)", "toJSON( env )", "fromJSON(toJSON(env)).A", "ENV.*"):
            with self.subTest(expression=expression):
                text = workflow(job("- run: echo ${{ " + expression + " }}\n", env=f"env:\n  A: {TITLE}\n  B: fixed"))
                self.assertEqual(self.levels_of(text), ["ERROR"])

    def test_a_whole_env_read_without_a_tainted_entry_is_a_warning_not_silence(self):
        for env in ("", "env:\n  A: fixed", "env:\n  A: ${{ github.sha }}"):
            with self.subTest(env=env):
                self.assertEqual(self.levels_of(workflow(job("- run: echo ${{ toJSON(env) }}\n", env=env))), ["WARN"])

    def test_a_whole_steps_read_after_a_tainted_step_is_an_error_and_a_single_step_object_too(self):
        for expression in ("toJSON(steps)", "toJSON(steps.a)", "join(steps.*.outputs, ',')", "toJSON(steps.a.outputs)"):
            with self.subTest(expression=expression):
                text = workflow(job(TAINTED_STEP + "- run: echo ${{ " + expression + " }}\n"))
                self.assertEqual(self.levels_of(text), ["ERROR"])

    def test_a_whole_steps_read_without_a_tainted_step_is_a_warning(self):
        text = workflow(job('- id: a\n  run: echo "t=1" >> "$GITHUB_OUTPUT"\n- run: echo ${{ toJSON(steps) }}\n'))
        self.assertEqual(self.levels_of(text), ["WARN"])
        self.assertEqual(self.levels_of(workflow(job("- run: echo ${{ steps.a.outcome }}\n"))), [])                          # 속성이 고정된 값(outcome)은 통째 읽기가 아니다

    def two_jobs(self, consumer_run, output=TITLE):
        return workflow(job("- run: echo hi\n", name="a", outputs="outputs:\n  t: " + output),
                        job("- run: " + consumer_run + "\n", name="b", needs="needs: a"))

    def test_a_whole_needs_read_with_a_tainted_job_output_is_an_error(self):
        for expression in ("toJSON(needs)", "toJSON(needs.a)", "join(needs.*.outputs, ',')", "toJSON(needs.a.outputs)"):
            with self.subTest(expression=expression):
                self.assertEqual(self.levels_of(self.two_jobs("echo ${{ " + expression + " }}")), ["ERROR"])

    def test_a_whole_needs_read_without_a_tainted_output_is_a_warning(self):
        self.assertEqual(self.levels_of(self.two_jobs("echo ${{ toJSON(needs) }}", output="fixed")), ["WARN"])
        self.assertEqual(self.levels_of(self.two_jobs("echo ${{ needs.a.result }}", output="fixed")), [])                      # 고정된 값(result)

    def test_a_whole_matrix_read_with_a_tainted_value_is_an_error_and_otherwise_a_warning(self):
        tainted = job("- run: echo ${{ toJSON(matrix) }}\n", strategy="strategy:\n  matrix:\n    x: ['" + TITLE + "']")
        fixed = job("- run: echo ${{ toJSON(matrix) }}\n", strategy="strategy:\n  matrix:\n    x: [a, b]")
        self.assertEqual(self.levels_of(workflow(tainted)), ["ERROR"])
        self.assertEqual(self.levels_of(workflow(fixed)), ["WARN"])

    def test_single_entries_and_literal_indexes_keep_their_old_verdicts(self):
        env = f"env:\n  A: {TITLE}\n  B: fixed"
        self.assertEqual(self.levels_of(workflow(job("- run: echo ${{ env.B }}\n", env=env))), [])
        self.assertEqual(self.levels_of(workflow(job("- run: echo ${{ env['B'] }}\n", env=env))), [])
        self.assertEqual(self.levels_of(workflow(job("- run: echo ${{ env.A }}\n", env=env))), ["ERROR"])
        self.assertEqual(self.levels_of(workflow(job("- run: echo ${{ environment.x }}\n", env=env))), [])                       # env 로 시작하는 다른 이름은 컨텍스트가 아니다

    def test_the_same_reads_in_github_script_are_found_too(self):
        text = workflow(job("- uses: actions/github-script@v7\n  with:\n    script: core.info(`${{ toJSON(env) }}`)\n", env=f"env:\n  A: {TITLE}"))
        self.assertEqual(self.levels_of(text), ["ERROR"])


@NEEDS_YAML
class SetOutputAndMatrixNameTest(WorkflowCase):
    """검증자 Q 의 F2·N1(Q31·Q32): 새 코드에 시험이 못박지 않은 갈래 둘."""

    def test_the_old_set_output_command_makes_a_step_output_like_github_output(self):
        """옛 출력 명령 `::set-output name=t::$X` 도 `$GITHUB_OUTPUT` 과 같이 단계 출력을 만든다 — job·워크플로 env 의 신뢰할 수 없는 값을 셸 변수로 읽어 내보내는 단계는 입력을 받은 단계다."""
        run = '- id: a\n  run: echo "::set-output name=t::$X"\n- run: echo ${{ steps.a.outputs.t }}\n'
        self.assertEqual(self.levels(workflow(job(run, env="env:\n  X: " + TITLE))), ["ERROR"])                      # job env
        self.assertEqual(self.levels(workflow(job(run), top="env:\n  X: " + TITLE + "\n")), ["ERROR"])               # 워크플로 env
        self.assertEqual(self.levels(workflow(job(run, env="env:\n  X: fixed"))), ["WARN"])                        # 고정 값을 내보내면 출처를 알 수 없는 출력일 뿐 — 경고
        quiet = '- id: a\n  run: echo "hi"\n- run: echo ${{ steps.a.outputs.t }}\n'
        self.assertEqual(self.levels(workflow(job(quiet, env="env:\n  X: " + TITLE))), ["WARN"])                    # 출력 명령이 없으면 입력을 받은 단계가 아니다

    def test_a_matrix_key_named_env_is_not_the_env_context(self):
        """`matrix.env.name` 의 `env.name` 은 env 컨텍스트가 아니라 matrix 키 `env` 의 값이다 — 점 뒤의 env 는 컨텍스트가 아니라 지적이 없다."""
        strategy = "strategy:\n  matrix:\n    env:\n      - {name: a}\n      - {name: b}"
        self.assertEqual(self.levels(workflow(job("- run: echo ${{ matrix.env.name }}\n", strategy=strategy))), [])


@NEEDS_YAML
class MatrixDirectValueTest(WorkflowCase):
    """검증자 S 의 V4(b) — matrix 값에 신뢰할 수 없는 식을 직접 적은 경우는 출처를 아니 경고가 아니라 오류다."""

    def test_an_untrusted_expression_written_into_the_matrix_is_an_error(self):
        for strategy in ("strategy:\n  matrix:\n    x: ['" + TITLE + "']",
                         "strategy:\n  matrix:\n    include:\n      - x: '" + TITLE + "'",
                         "strategy:\n  matrix:\n    x: [a]\n    include:\n      - x: '${{ github.head_ref }}'",
                         "strategy:\n  matrix:\n    x:\n      - '${{ github.event.comment.body }}'"):
            with self.subTest(strategy=strategy):
                self.assertEqual(self.levels(workflow(job("- run: echo ${{ matrix.x }}\n", strategy=strategy))), ["ERROR"])

    def test_fixed_and_computed_values_keep_their_old_verdicts(self):
        self.assertEqual(self.levels(workflow(job("- run: echo ${{ matrix.x }}\n", strategy="strategy:\n  matrix:\n    x: [a, b]"))), [])
        self.assertEqual(self.levels(workflow(job("- run: echo ${{ matrix.x }}\n", strategy="strategy:\n  matrix: ${{ fromJSON(needs.a.outputs.m) }}"))), ["WARN"])
        self.assertEqual(self.levels(workflow(job("- run: echo ${{ matrix.x }}\n", strategy="strategy:\n  matrix:\n    x: ['${{ github.sha }}']"))), ["WARN"])      # 식이 있지만 신뢰할 수 없는 입력은 아니다

    def test_another_key_with_an_untrusted_value_does_not_taint_this_key(self):
        strategy = "strategy:\n  matrix:\n    x: [a]\n    y: ['" + TITLE + "']"
        self.assertEqual(self.levels(workflow(job("- run: echo ${{ matrix.x }}\n", strategy=strategy))), [])
        self.assertEqual(self.levels(workflow(job("- run: echo ${{ matrix.y }}\n", strategy=strategy))), ["ERROR"])


@NEEDS_YAML
class InputsThroughEnvTest(WorkflowCase):
    """검증자 S 의 V4(c) — `env: T: ${{ inputs.x }}` 를 거친 `${{ env.T }}` 도 경고 이상이다(직접 `${{ inputs.x }}` 가 경고인 것과 일관)."""

    def test_an_env_that_holds_inputs_is_a_warning_when_interpolated(self):
        for value in ("${{ inputs.x }}", "${{ github.event.inputs.x }}", "${{ format('{0}', inputs.x) }}", "pre-${{ inputs['x'] }}", "${{ toJSON(inputs) }}"):
            with self.subTest(value=value):
                text = workflow(job('- run: echo "${{ env.T }}"\n', env=f"env:\n  T: {value}"))
                self.assertEqual(self.levels(text), ["WARN"])

    def test_a_chain_ending_in_inputs_is_a_warning_and_a_tainted_end_still_wins(self):
        self.assertEqual(self.levels(workflow(job('- run: echo "${{ env.A }}"\n', env="env:\n  A: ${{ env.B }}\n  B: ${{ inputs.x }}"))), ["WARN"])
        self.assertEqual(self.levels(workflow(job('- run: echo "${{ env.A }}"\n', env=f"env:\n  A: ${{{{ env.B }}}}\n  B: ${{{{ inputs.x }}}}-{TITLE}"))), ["ERROR"])

    def test_passing_inputs_through_env_and_reading_them_in_the_shell_stays_clean(self):
        text = workflow(job('- run: echo "$T"\n', env="env:\n  T: ${{ inputs.x }}"))
        self.assertEqual([f for f in self.check(text) if f.check == "WF-4"], [])


@NEEDS_YAML
class BrokenShapesTest(WorkflowCase):
    """검증자 S 의 V3 — 깨진 워크플로에서 검증기가 죽지 않는다: `jobs` 가 객체가 아니면 WF-0 오류로 알리고(시작점부터 AttributeError 둘), matrix 의 include·exclude 가 목록이 아니어도
    순회하지 않는다(이번 묶음이 만든 TypeError 하나)."""

    def test_jobs_that_is_a_list_a_string_or_a_number_is_a_wf0_error_not_a_crash(self):
        for jobs in ("\n  - a\n  - b\n", " hello\n", " 5\n", " true\n"):
            with self.subTest(jobs=jobs):
                text = f'name: t\non: workflow_dispatch\npermissions:\n  contents: read\njobs:{jobs}'
                found = self.check(text)
                self.assertEqual([(f.check, f.level) for f in found], [("WF-0", "ERROR")])
                self.assertIn("jobs", found[0].message)

    def test_empty_jobs_is_not_an_error(self):
        for jobs in (" null\n", " {}\n", " []\n"):
            with self.subTest(jobs=jobs):
                text = f'name: t\non: workflow_dispatch\npermissions:\n  contents: read\njobs:{jobs}'
                self.assertEqual([f for f in self.check(text) if f.check == "WF-0"], [])

    def test_matrix_include_and_exclude_that_are_not_lists_do_not_crash(self):
        for strategy in ("strategy:\n  matrix:\n    include: 5", "strategy:\n  matrix:\n    include: hello", "strategy:\n  matrix:\n    include: ${{ fromJSON(x) }}",
                         "strategy:\n  matrix:\n    x: [a]\n    exclude: 5", "strategy:\n  matrix:\n    x: [a]\n    include: {y: 1}", "strategy:\n  matrix: hello", "strategy: hello",
                         "strategy:\n  matrix:\n    include:\n      - 5\n      - hello"):
            with self.subTest(strategy=strategy):
                found = self.check(workflow(job("- run: echo ${{ matrix.x }}\n", strategy=strategy)))
                self.assertEqual([f for f in found if f.level == "ERROR"], [])

    def test_a_computed_include_is_not_a_fixed_value(self):
        text = workflow(job("- run: echo ${{ matrix.x }}\n", strategy="strategy:\n  matrix:\n    include: ${{ fromJSON(needs.a.outputs.m) }}"))
        self.assertEqual(self.levels(text), ["WARN"])

    def test_the_whole_validator_survives_a_broken_workflow(self):
        for jobs in ("\n  - a\n", " hello\n"):
            with self.subTest(jobs=jobs):
                self.write(f'name: t\non: workflow_dispatch\npermissions:\n  contents: read\njobs:{jobs}', "broken.yml")
                findings = vr.run_checks(self.root)
                self.assertIn(("WF-0", "ERROR"), [(f.check, f.level) for f in findings])


@NEEDS_YAML
class DiscussionTriggerTest(WorkflowCase):
    """검증자 S 의 V10 — 낯선 사람이 쓴 글이 실행을 일으키는 `discussion`·`discussion_comment` 도 허용 목록(지금은 빔)이다."""

    def test_the_discussion_triggers_are_errors_in_every_notation(self):
        for on in ("discussion", "discussion_comment", "[discussion]", "[push, discussion_comment]", "\n  discussion:\n    types: [created]", "\n  discussion_comment:\n    types: [created]", "Discussion_Comment"):
            with self.subTest(on=on):
                found = [(f.level, f.message) for f in self.check(workflow(job("- run: echo hi\n"), on=on)) if f.check == "WF-3"]
                self.assertEqual([level for level, _ in found], ["ERROR"])
                self.assertIn("허용 목록", found[0][1])

    def test_the_allow_list_names_all_five_and_stays_empty(self):
        self.assertEqual(sorted(vr.WF3_UNTRUSTED_TRIGGERS), ["discussion", "discussion_comment", "issue_comment", "pull_request_review", "pull_request_review_comment"])
        self.assertTrue(all(value == () for value in vr.WF3_UNTRUSTED_TRIGGERS.values()))


if __name__ == "__main__":
    unittest.main()
