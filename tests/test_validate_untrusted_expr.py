"""워크플로 `run:` 의 주입 검사(WF-4)가 보는 '신뢰할 수 없는 입력' 낱말 목록(결함 D-351).

옛 검사는 식의 **시작**에 `github.event.(issue|comment|pull_request|…)` 나 `github.head_ref` 가 있을 때만 걸렸다. 그래서 `github.ref_name`·`github.ref`·`github.base_ref`·
`github.event.label.name`·`release`·`client_payload` 같은 낱말, 대괄호 표기(`github['head_ref']`), 대소문자만 다른 표기, `github.head_ref || 'x'`·`format(…)`·`toJSON(github.event)` 처럼
식 안쪽에 숨은 이름이 지나갔다. 브랜치·태그·라벨 이름과 이슈·PR·커밋의 제목·본문은 누구나 정할 수 있고 셸 메타문자를 담을 수 있다 — run 에 직접 보간하면 명령이 된다.
워크플로 파일은 고치지 않는다(검사만). 저장소의 실제 워크플로는 run 안에 `${{ }}` 를 쓰지 않아 목록을 넓혀도 빨개지지 않는다(마지막 시험이 확인한다).
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

import _bootstrap

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

REAL = _bootstrap.ROOT

# 이 목록은 시험이 독립적으로 가진다(코드의 목록에서 낱말 하나를 빼면 여기서 빨개지게). 위쪽 둘은 옛 검사가 이미 알던 것, 나머지가 이번에 더한 것이다.
KNOWN_BEFORE = (
    "github.head_ref", "github.event.issue.title", "github.event.issue.body", "github.event.comment.body", "github.event.pull_request.title",
    "github.event.pull_request.head.ref", "github.event.pull_request.head.label", "github.event.review.body", "github.event.review_comment.body",
    "github.event.discussion.title", "github.event.head_commit.message", "github.event.commits[0].message", "github.event.pages[0].page_name",
    "github.event.workflow_run.head_branch",
)
ADDED = (
    "github.ref_name", "github.ref", "github.base_ref", "github.workflow_ref", "github.event.ref", "github.event.base_ref", "github.event.label.name",
    "github.event.release.name", "github.event.release.body", "github.event.release.tag_name", "github.event.client_payload.value", "github.event.check_run.name",
    "github.event.check_suite.head_branch", "github.event.deployment.payload.value", "github.event.deployment_status.description", "github.event.milestone.title",
    "github.event.project_card.note", "github.event.project_column.name", "github.event.project.name", "github.event.changes.title.from",
    "github.event.workflow_job.head_branch", "github.event.merge_group.head_ref", "github.event.merge_group.head_commit.message",
    "github.event.description", "github.event.context", "github.event.branches[0].name", "github.event.commit.message", "github.event.target_url",
    "github.event.forkee.description", "github.event.team.name",
)
HIDDEN = (
    "GitHub.Head_Ref", "GITHUB.EVENT.ISSUE.TITLE", "github['head_ref']", "github['event']['pull_request']['head']['ref']", "github.event['issue']['title']",
    "github . event . issue . title", "github.head_ref || 'main'", "github.head_ref || github.ref_name", "format('{0}', github.head_ref)",
    "contains(github.event.issue.title, 'x') && 'a' || 'b'", "!github.event.issue.title", "(github.ref_name)", "toJSON(github.event)", "toJSON(github)",
    "fromJSON(toJSON(github.event)).issue.title", "join(github.event.commits.*.message, ' ')", "matrix.x || github.ref_name",
    # 이름을 눈으로 못 읽는 접근(검증자 S 의 SP-2): 객체 필터 `*` 와 문자열 리터럴이 아닌 색인
    "join(github.event.*.title, ',')", "toJSON(github.event.*)", "toJSON(github.*)", "github[format('{0}', 'head_ref')]", "github.event[format('i{0}', 'ssue')].title",
    "github['event'][env.K].title", """github[join(fromJSON('["head","ref"]'), '_')]""", "github  .  event\n  .*",
    # 공백을 끼워 숨기기(검증자 S 의 SP-13): `[` 앞과 함수 이름·`(` 사이의 공백·개행·탭. 러너가 `toJSON (…)`·`github [...]` 꼴을 받는지는 추측이라 받는다고 보고 막는다
    "toJSON (github)", "toJSON\n(github.event)", "toJSON\t(github.event)", "fromJSON(toJSON (github.event)).issue.title", "toJSON  \n  (  github  )",
    "format('{0}', toJSON (github))", "github [format('{0}', 'head_ref')]", "github\n[env.K]", "github.event [env.K].title", "github\t[env.K]", "github  [  env.K  ]",
    "github ['event'] [env.K].title", "github.event\n  [format('i{0}', 'ssue')]  .  title",
)
SAFE = (
    "github.sha", "github.repository", "github.repository_owner", "github.run_id", "github.run_number", "github.event_name", "github.actor", "github.ref_protected",
    "github.ref_type", "github.event.repository.default_branch", "github.event.before", "github.event.after", "github.event.number", "github.workflow", "github.token",
    "matrix.python-version", "steps.build.outputs.value", "needs.plan.outputs.matrix", "runner.os", "env.PLAIN", "secrets.SOME_SECRET", "inputs.dry_run",
    "format('{0}-{1}', github.run_id, github.sha)", "needs.github.outputs.value", "steps.github.outputs.ref", "matrix.github.ref_name", "needs.github.event.issue.title",     # 다른 컨텍스트의 키가 github 일 뿐
    "github.event.issuer", "github.event.labelled", "github.references", "github.refs_note",     # 낱말 경계: 목록의 낱말로 시작할 뿐 다른 이름이다
    # toJSON 은 컨텍스트 통째(github·github.event)일 때만 위험하다 · 하이픈 뒤의 github 는 다른 낱말의 일부 · 리터럴 색인은 점 표기와 같다 · 다른 컨텍스트의 동적 색인은 해당 없다(저장소 워크플로가 쓴다)
    "toJSON(github.sha)", "toJSON(matrix)", "toJSON(needs)", "toJSON(github.event.repository)", "matrix.x-github.ref_name", "github.event.repository['default_branch']",
    "secrets[matrix.secret_name]", "steps[matrix.id].outputs.value", "needs[matrix.job].outputs.x",
    # 동적 색인·객체 필터 검사도 낱말 경계를 지킨다 — github 라는 이름의 단계·작업·행렬 칸을 동적으로 읽는 식은 github 컨텍스트가 아니다
    "steps.github.outputs[matrix.k]", "matrix.x-github[matrix.k]", "mygithub[matrix.k]", "needs.github.outputs.*", "toJSON(matrix.x-github)",
    # 공백을 끼워도 안전한 식은 그대로 안전하다(SP-13): 다른 컨텍스트의 동적 색인·낱말 경계·toJSON 의 대상이 github 가 아닌 것·github 의 안전한 칸을 함수에 넘김
    "secrets [matrix.n]", "matrix.github [x]", "steps.github.outputs [matrix.k]", "toJSON (matrix)", "toJSON (github.sha)", "toJSON\n(needs)", "toJSON (matrix.x-github)",
    "format ('{0}', github.sha)", "contains (github.event.repository.name, 'x')",
)


def workflow(run_lines, env=None, extra_step=""):
    env_block = "".join(f"          {key}: {value}\n" for key, value in (env or {}).items())
    env_section = f"        env:\n{env_block}" if env_block else ""
    body = "".join(f"          {line}\n" for line in run_lines.splitlines())
    return ("name: w\non: push\npermissions:\n  contents: read\njobs:\n  j:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n"
            f"{extra_step}      - name: step\n{env_section}        run: |\n{body}")


class WorkflowCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def check(self, text):
        path = self.root / ".github" / "workflows" / "w.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return vr.check_workflows(self.root, [".github/workflows/w.yml"])

    def injection(self, text):
        return [f for f in self.check(text) if f.check == "WF-4" and f.level == "ERROR"]


class UntrustedContextListTest(WorkflowCase):
    def test_every_context_the_old_check_knew_is_still_an_error(self):
        for name in KNOWN_BEFORE:
            with self.subTest(name=name):
                self.assertEqual(len(self.injection(workflow(f"echo ${{{{ {name} }}}}"))), 1)

    def test_every_context_added_by_this_change_is_an_error(self):
        for name in ADDED:
            with self.subTest(name=name):
                found = self.injection(workflow(f"echo ${{{{ {name} }}}}"))
                self.assertEqual(len(found), 1)
                self.assertIn("신뢰할 수 없는 입력", found[0].message)
                self.assertIn(name.split(".")[-1].split("[")[0], found[0].message)

    def test_the_same_names_hidden_in_other_spellings_and_positions_are_errors_too(self):
        for expression in HIDDEN:
            with self.subTest(expression=expression):
                self.assertEqual(len(self.injection(workflow(f"echo ${{{{ {expression} }}}}"))), 1)

    def test_a_name_in_a_later_expression_of_the_same_run_is_found(self):
        text = workflow("echo ${{ github.sha }} and ${{ runner.os }} then ${{ github.ref_name }}")
        self.assertEqual(len(self.injection(text)), 1)

    def test_a_closing_brace_pair_inside_a_string_literal_does_not_end_the_expression(self):
        """리터럴 안의 `}}` 를 식의 끝으로 읽으면 그 뒤의 이름이 식 밖 글자로 보여 검사를 지나갔다."""
        for expression in ("format('}}{0}', github.head_ref)", "format('{0}}}', github.ref_name)", "'}}' && github.event.issue.title",
                           "format('it''s }}{0}', github.event.label.name)", "'a}}b' || github.ref"):
            with self.subTest(expression=expression):
                self.assertEqual(len(self.injection(workflow("echo ${{ " + expression + " }}"))), 1)

    def test_dynamic_access_to_the_github_context_is_an_error_but_other_contexts_are_not(self):
        """이름을 눈으로 읽을 수 없는 접근(객체 필터 `*`·리터럴이 아닌 색인)은 오류, 다른 컨텍스트의 동적 색인은 해당 없다."""
        for expression in ("github.*", "github.event.*", "github[env.K]", "github.event[matrix.k]", "github[format('{0}', 'x')].y"):
            with self.subTest(expression=expression):
                self.assertEqual(len(self.injection(workflow("echo ${{ " + expression + " }}"))), 1)
        for expression in ("secrets[matrix.name]", "steps[matrix.id].outputs.value", "needs[matrix.job].outputs.x", "matrix.x[0]", "github.event.repository.default_branch"):
            with self.subTest(expression=expression):
                self.assertEqual(self.injection(workflow("echo ${{ " + expression + " }}")), [])

    def test_a_very_long_run_of_spaces_inside_an_expression_is_folded_in_linear_time(self):
        """공백을 접는 정규식이 제곱 시간이라 공백 10만 개에 20초 넘게 걸렸다(검증자 Q 의 QP-7·S 의 SP-7). 지금은 선형이다."""
        started = time.monotonic()
        self.assertIsNone(vr._untrusted_expression("echo ${{ " + " " * 100000 + "github.sha }}"))
        self.assertIsNotNone(vr._untrusted_expression("echo ${{ " + " " * 100000 + "github . ref_name }}"))
        self.assertLess(time.monotonic() - started, 5.0)                                       # 선형이면 0.1초 안팎, 제곱이면 이 PC 에서 20초 넘는다

    def test_an_expression_that_is_never_closed_is_read_to_the_end(self):
        self.assertEqual(len(self.injection(workflow("echo ${{ github.head_ref"))), 1)

    def test_an_expression_spread_over_several_lines_is_found_and_reported_on_one_line(self):
        found = self.injection(workflow("echo ${{\n  github.head_ref\n}}"))
        self.assertEqual(len(found), 1)
        for text in (found[0].message, found[0].line()):
            self.assertEqual(len(text.splitlines()), 1, text)
        self.assertIn("github.head_ref", found[0].message)


class NoFalsePositiveTest(WorkflowCase):
    def test_safe_expressions_in_run_are_not_flagged(self):
        for name in SAFE:
            with self.subTest(name=name):
                self.assertEqual(self.injection(workflow(f"echo ${{{{ {name} }}}}")), [])

    def test_a_name_inside_a_string_literal_is_text_not_a_context(self):
        for expression in ("format('{0}', 'github.head_ref')", "contains('github.ref_name', 'x')", "'github.event.issue.title'", "'}}'", "format('}}{0}', github.sha)"):
            with self.subTest(expression=expression):
                self.assertEqual(self.injection(workflow(f"echo ${{{{ {expression} }}}}")), [])

    def test_passing_the_same_values_through_env_is_clean(self):
        env = {"BRANCH": "${{ github.head_ref }}", "REF": "${{ github.ref_name }}", "TITLE": "${{ github.event.issue.title }}", "LABEL": "${{ github.event.label.name }}",
               "EVENT": "${{ toJSON(github.event) }}"}
        text = workflow('echo "$BRANCH $REF $TITLE $LABEL"\necho "$EVENT"', env=env)
        self.assertEqual([f for f in self.check(text) if f.check == "WF-4"], [])

    def test_only_run_is_a_sink_conditions_and_names_may_use_the_contexts(self):
        text = ("name: w\non: push\npermissions:\n  contents: read\nconcurrency:\n  group: g-${{ github.ref }}\njobs:\n  j:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n"
                "    if: ${{ github.head_ref != '' }}\n    steps:\n      - name: step\n        if: ${{ github.ref_name == 'main' }}\n        run: echo fixed\n")
        self.assertEqual([f for f in self.check(text) if f.check == "WF-4"], [])

    def test_the_inputs_warning_is_unchanged(self):
        found = self.check(workflow("echo ${{ inputs.name }}"))
        self.assertEqual([(f.check, f.level) for f in found if f.check == "WF-4"], [("WF-4", "WARN")])


class ExpressionNamesTest(unittest.TestCase):
    def test_brackets_become_dots_and_case_and_spaces_fold(self):
        self.assertEqual(vr._expression_names(" GitHub['Event']['Issue'] . Title "), " github.event.issue.title ")
        self.assertEqual(vr._expression_names("github.event.commits[0].message"), "github.event.commits.0.message")

    def test_runs_of_any_whitespace_are_folded_before_the_dots_are_joined(self):
        self.assertEqual(vr._expression_names("github \t\n .  event\n\n.   issue"), "github.event.issue")
        self.assertEqual(vr._expression_names("a    b"), "a b")

    def test_spaces_before_an_opening_paren_or_bracket_are_dropped_so_a_call_or_an_index_cannot_hide_behind_them(self):
        """함수 이름과 `(` 사이·컨텍스트 이름과 `[` 사이의 공백은 이름 읽기에서 지운다(검증자 S 의 SP-13)."""
        self.assertEqual(vr._expression_names("toJSON (github)"), "tojson(github)")
        self.assertEqual(vr._expression_names("toJSON \n\t (github.event)"), "tojson(github.event)")
        self.assertEqual(vr._expression_names("github [format('{0}', 'x')]"), "github[format('', '')]")
        self.assertEqual(vr._expression_names("github  .event  [env.K]"), "github.event[env.k]")
        self.assertEqual(vr._expression_names("a (b) [c]"), "a(b)[c]")
        self.assertEqual(vr._expression_names(" a  b "), " a b ")                                  # 괄호·대괄호 앞이 아니면 공백 하나는 그대로

    def test_string_literals_are_emptied_including_doubled_quotes(self):
        self.assertEqual(vr._expression_names("format('a.b', 'it''s github.ref')"), "format('', '')")

    def test_the_expression_blocks_end_only_at_a_closing_pair_outside_a_literal(self):
        self.assertEqual(list(vr._expression_blocks("a ${{ x }} b ${{ format('}}', y) }} c")),
                         [("${{ x }}", " x "), ("${{ format('}}', y) }}", " format('}}', y) ")])
        self.assertEqual(list(vr._expression_blocks("no expression")), [])
        self.assertEqual(list(vr._expression_blocks("${{ never closed")), [("${{ never closed", " never closed")])
        self.assertEqual(list(vr._expression_blocks("${{ a }}${{ b }}")), [("${{ a }}", " a "), ("${{ b }}", " b ")])
        self.assertEqual(vr._untrusted_expression("echo ${{ format('}}', github.ref_name) }}"), "${{ format('}}', github.ref_name) }}")

    def test_the_untrusted_expression_helper_returns_the_first_one_folded_to_one_line(self):
        self.assertIsNone(vr._untrusted_expression("echo ${{ github.sha }} ${{ runner.os }}"))
        self.assertIsNone(vr._untrusted_expression("no expression at all"))
        self.assertEqual(vr._untrusted_expression("a ${{ github.sha }} b ${{ github.head_ref }} c ${{ github.ref_name }}"), "${{ github.head_ref }}")
        self.assertEqual(vr._untrusted_expression("${{\n github.ref_name\n}}"), "${{ github.ref_name }}")


class RealRepositoryTest(unittest.TestCase):
    def test_no_workflow_of_this_repository_interpolates_untrusted_input_into_run(self):
        files = [f for f in vr.list_files(REAL) if f.startswith(".github/workflows/")]
        self.assertGreaterEqual(len(files), 10)
        found = [f.line() for f in vr.check_workflows(REAL, files) if f.check == "WF-4" and f.level == "ERROR"]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
