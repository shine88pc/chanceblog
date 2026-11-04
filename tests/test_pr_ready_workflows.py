"""PR 화면에 '이미 끝난 초록'만 보이게(운영자 요청 2026-11-04) — 워크플로의 PR 이벤트 모양을 이벤트별로 직접 계산해 고정한다.

운영자가 PR 을 만들면 화면에 '도는 중'(몇 분)이나 '건너뜀' 줄이 새로 생겨 '일부 검사가 안 돈다'로 읽혔다(실제로는 빠진 검사가 없었다). 검사는 브랜치를 push 할 때 이미 끝나 있어야 하고(`guardrails.yml` —
시험 병합은 tests/test_guardrails_precheck.py), PR 을 만드는 순간에는 새로 도는 job 이 없어야 한다. 이 시험은 모든 워크플로의 `on`·job `if` 를 GitHub 규칙대로 계산해(tests/workflow_expr_helpers.py)
같은 저장소의 `ai/claude/**` 브랜치 PR 에서 다음을 고정한다.
 1. PR 이벤트에 반응하는 워크플로는 `pr-scope-check.yml`·`ops-inbox.yml` 둘뿐이고 가드레일 검사는 PR 로 돌지 않는다.
 2. PR 을 열거나 다시 열거나 갱신해도(opened·reopened·synchronize·ready_for_review) 도는(running) job 이 하나도 없다. 시작하는 워크플로는 `pr-scope-check.yml` 하나이고 그 job 은 곧바로 건너뜀이다.
 3. 확인 필요 모음은 PR 을 열 때 시작하지 않는다(닫힘·라벨 변경뿐). 이슈 수정 요청을 처리하는 PR(Copilot·사람·issue-edit)에는 범위 검사가 그대로 돌고, 수동 실행도 그대로다.
 4. 이벤트 값(브랜치 이름·저장소 이름)은 `if` 안에서만 읽고 셸 명령에는 넣지 않는다.
네트워크·GitHub 를 쓰지 않는다.
"""
import re
import sys
import unittest

import yaml

import _bootstrap
from workflow_expr_helpers import Expr

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

WORKFLOWS = _bootstrap.ROOT / ".github" / "workflows"
REPO = "octo/blog"
AI_BRANCH = "ai/claude/wf-pr-ready-1"
DEFAULT_PULL_REQUEST_TYPES = ["opened", "synchronize", "reopened"]          # `types` 를 적지 않은 pull_request 의 기본 이벤트 종류(GitHub 규칙)
SCOPE = "pr-scope-check.yml"
INBOX = "ops-inbox.yml"


def load(name):
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def all_workflows():
    return {path.name: yaml.safe_load(path.read_text(encoding="utf-8")) for path in sorted(WORKFLOWS.glob("*.yml"))}


def starts_on_pull_request(data, action):
    """이 워크플로가 `pull_request` 의 이 종류(action)로 시작하는가. 브랜치·경로 필터는 계산하지 않는다 — 필터가 생기면 이 시험을 먼저 고친다."""
    config = vr._triggers(data).get("pull_request", False)
    if config is False:
        return False
    config = config or {}
    for key in ("branches", "branches-ignore", "paths", "paths-ignore"):
        assert key not in config, f"이 시험이 계산하지 못하는 필터({key}) — 쓰게 되면 시험을 먼저 고친다"
    return action in (config.get("types") or DEFAULT_PULL_REQUEST_TYPES)


def context(event_name="pull_request", head_ref=AI_BRANCH, head_repo=REPO, labels=(), event_label=None):
    event = {}
    if event_name == "pull_request":
        event["pull_request"] = {"head": {"repo": {"full_name": head_repo}}, "labels": [{"name": name} for name in labels]}
    if event_label is not None:
        event["label"] = {"name": event_label}
    return {"github": {"event_name": event_name, "head_ref": head_ref if event_name == "pull_request" else "", "repository": REPO, "event": event}}


def running_jobs(data, ctx):
    """job `if` 를 계산해 이 이벤트에서 실제로 도는 job 이름 목록(`if` 가 없으면 항상 돈다)."""
    running = []
    for job_id, job in (data.get("jobs") or {}).items():
        condition = job.get("if")
        if condition is None:
            running.append(job_id)
            continue
        source = str(condition).strip()
        if source.startswith("${{"):
            source = source[3:-2]
        if Expr(source, ctx).parse() is True:
            running.append(job_id)
    return running


class PullRequestScreenTest(unittest.TestCase):
    """같은 저장소의 AI 브랜치(`ai/claude/**`) PR — 운영자가 휴대폰에서 만들어 병합하는 PR — 의 화면."""

    def setUp(self):
        self.workflows = all_workflows()

    def started_by(self, action):
        return sorted(name for name, data in self.workflows.items() if starts_on_pull_request(data, action))

    def test_only_the_scope_check_and_the_inbox_react_to_pull_requests_and_the_guardrails_check_does_not(self):
        reacting = sorted(name for name, data in self.workflows.items() if "pull_request" in vr._triggers(data))
        self.assertEqual(reacting, [INBOX, SCOPE])
        self.assertNotIn("pull_request", vr._triggers(self.workflows["guardrails.yml"]))       # 가드레일 검사는 push 때 이미 끝난다
        for name, data in self.workflows.items():
            self.assertNotIn("pull_request_target", vr._triggers(data), name)
            self.assertNotIn("workflow_run", vr._triggers(data), name)                         # 다른 워크플로의 끝에 기대어 PR 화면에 줄을 더하지 않는다

    def test_opening_updating_or_reopening_an_ai_branch_pull_request_starts_no_running_job(self):
        for action in ("opened", "reopened", "synchronize", "ready_for_review"):
            for name, data in self.workflows.items():
                if starts_on_pull_request(data, action):
                    self.assertEqual(running_jobs(data, context()), [], (action, name))        # 새로 '도는 중'이 되는 줄이 없다
        for action in ("opened", "reopened", "synchronize", "ready_for_review"):
            self.assertEqual(self.started_by(action), [SCOPE], action)                         # 화면에 더해지는 것은 범위 검사의 건너뜀 한 줄뿐

    def test_the_inbox_does_not_start_when_a_pull_request_is_opened_or_updated(self):
        for action in ("opened", "reopened", "synchronize", "edited", "ready_for_review", "converted_to_draft", "review_requested", "assigned"):
            self.assertNotIn(INBOX, self.started_by(action), action)
        for action in ("closed", "labeled", "unlabeled"):
            self.assertIn(INBOX, self.started_by(action), action)                              # 초안 PR 을 닫거나 라벨을 바꾸는 것은 그대로 읽는다
        self.assertEqual(self.started_by("closed"), [INBOX])                                   # 병합(닫힘) 때의 건너뜀 한 줄은 병합 뒤라 화면에서 무관하다

    def test_the_inbox_job_is_still_skipped_for_a_pull_request_that_is_not_a_draft(self):
        data = self.workflows[INBOX]
        for action_label in (None, "bug"):
            self.assertEqual(running_jobs(data, context(event_label=action_label)), [], action_label)      # 닫힘·다른 라벨 변경: 건너뜀
        self.assertEqual(running_jobs(data, context(labels=("초안",), event_label="초안")), ["inbox"])      # 초안 PR 의 닫힘·라벨 변경은 그대로 돈다
        self.assertEqual(running_jobs(data, context(labels=("초안",), head_repo="stranger/blog")), [])        # 포크의 PR 은 돌지 않는다

    def test_the_scope_check_is_skipped_only_for_ai_branches_and_forks_and_runs_for_the_requests_it_serves(self):
        data = self.workflows[SCOPE]
        for branch in ("copilot/fix-12", "issue-edit/12-about-r5", "feature/x", "ai/claude", "ai/claudex/y", "xai/claude/y", "ai/codex/x", "ai/draft/2026-11-04-s1", "claude/ai/x"):
            self.assertEqual(running_jobs(data, context(head_ref=branch)), ["scope"], branch)  # 이슈 수정 요청을 처리하는 PR(Copilot·사람·issue-edit)은 그대로 검사한다
        for branch in (AI_BRANCH, "ai/claude/a", "ai/claude/a/b", "ai/claude/", "AI/Claude/x"):
            self.assertEqual(running_jobs(data, context(head_ref=branch)), [], branch)         # AI 브랜치 PR 은 건너뛴다(GitHub 의 startsWith 는 대소문자를 가리지 않는다)
        for branch in ("copilot/fix-12", AI_BRANCH):
            self.assertEqual(running_jobs(data, context(head_ref=branch, head_repo="stranger/blog")), [], branch)     # 포크의 PR 은 늘 건너뛴다(옛 그대로)
            self.assertEqual(running_jobs(data, context(head_ref=branch, head_repo="")), [], branch)
        self.assertEqual(running_jobs(data, context(event_name="workflow_dispatch")), ["scope"])        # 수동 실행은 그대로 돈다
        for other in ("push", "schedule", "issues", "release"):
            self.assertEqual(running_jobs(data, context(event_name=other)), [], other)

    def test_the_scope_check_keeps_everything_else_about_how_it_runs(self):
        text, data = load(SCOPE)
        triggers = vr._triggers(data)
        self.assertEqual(set(triggers), {"pull_request", "workflow_dispatch"})
        self.assertEqual(triggers["pull_request"], {"types": ["opened", "synchronize", "reopened", "ready_for_review"]})
        self.assertEqual(list(triggers["workflow_dispatch"]["inputs"]), ["pr_number"])
        self.assertEqual(data["permissions"], {"contents": "read"})
        self.assertEqual(data["concurrency"], {"group": "pr-scope-${{ github.event.pull_request.number || inputs.pr_number }}", "cancel-in-progress": True})
        job = data["jobs"]["scope"]
        self.assertEqual(job["permissions"], {"contents": "read", "pull-requests": "write", "issues": "read"})
        self.assertEqual((job["runs-on"], job["timeout-minutes"]), ("ubuntu-latest", 10))
        self.assertEqual(job["env"], {"GH_TOKEN": "${{ secrets.GITHUB_TOKEN }}", "PR_NUMBER": "${{ github.event.pull_request.number || inputs.pr_number }}"})
        self.assertEqual(job["steps"][0]["uses"], "actions/checkout@v6")
        self.assertEqual(job["steps"][0]["with"], {"ref": "${{ github.event.repository.default_branch }}", "fetch-depth": 0})      # 검증 도구는 기본 브랜치 코드로(PR 쪽 코드를 실행하지 않는다)
        condition = " ".join(str(job["if"]).split())
        self.assertEqual(condition, "github.event_name == 'workflow_dispatch' || (github.event.pull_request.head.repo.full_name == github.repository && !startsWith(github.head_ref, 'ai/claude/'))")
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", condition)      # 같은 저장소의 브랜치에서 온 PR 만(포크 코드·시크릿 노출 방지)는 그대로

    def test_event_values_are_read_only_inside_the_if_condition(self):
        text, data = load(SCOPE)
        self.assertEqual(len(re.findall(r"github\.head_ref", text)), 1)                        # 브랜치 이름은 job `if` 한 곳에서만 읽는다
        for step in data["jobs"]["scope"]["steps"]:
            for field in ("run", "with", "env"):
                self.assertNotIn("head_ref", str(step.get(field, "")), step.get("name"))
            if "run" in step:
                self.assertIsNone(re.search(r"\$\{\{\s*(?:github\.head_ref|github\.event\.pull_request\.head)", step["run"]), step.get("name"))
        findings = vr.check_workflows(_bootstrap.ROOT, [".github/workflows/pr-scope-check.yml", ".github/workflows/ops-inbox.yml", ".github/workflows/guardrails.yml"])
        self.assertEqual([f.line() for f in findings], [])                                     # 저장소 검증기의 워크플로 규칙(WF-1~9)에 걸리지 않는다


class ExpressionHelperStartsWithTest(unittest.TestCase):
    """PR 화면 시험이 기대는 해석기가 `startsWith`·`endsWith` 를 GitHub 규칙대로 계산하는지."""

    def ev(self, source, ctx=None):
        return Expr(source, ctx or {}).parse()

    def test_starts_with_and_ends_with_ignore_case_and_cast_null_to_an_empty_string(self):
        ctx = {"a": {"b": "AI/Claude/x"}}
        self.assertTrue(self.ev("startsWith(a.b, 'ai/claude/')", ctx))
        self.assertFalse(self.ev("startsWith(a.b, 'ai/claudex')", ctx))
        self.assertFalse(self.ev("startsWith(a.b, 'claude')", ctx))                             # 맨 앞에서만
        self.assertTrue(self.ev("endsWith(a.b, '/X')", ctx))
        self.assertFalse(self.ev("endsWith(a.b, 'ai')", ctx))
        self.assertFalse(self.ev("startsWith(a.missing, 'x')", ctx))                            # 없는 값(null)은 빈 문자열로 본다
        self.assertTrue(self.ev("startsWith(a.missing, '')", ctx))

    def test_negation_and_precedence_work_with_the_functions(self):
        ctx = {"a": {"b": "ai/claude/x", "c": "o/r"}}
        self.assertFalse(self.ev("a.c == 'o/r' && !startsWith(a.b, 'ai/claude/')", ctx))
        self.assertTrue(self.ev("false || (a.c == 'o/r' && !startsWith(a.b, 'x'))", ctx))
        self.assertTrue(self.ev("!startsWith(a.b, 'x') && !endsWith(a.b, 'y')", ctx))

    def test_unknown_functions_still_raise_instead_of_returning_a_wrong_value(self):
        with self.assertRaises(AssertionError):
            self.ev("toLower(a.b)", {"a": {"b": "X"}})
        with self.assertRaises(AssertionError):
            self.ev("format('{0}', a.b)", {"a": {"b": "X"}})


ROOT = _bootstrap.ROOT
READ_BY_PEOPLE = ("docs/ACTIONS_GUIDE.md", "docs/AGENT_RUNBOOK.md", "docs/ARCHITECTURE.md", "docs/SECURITY_GUARDRAILS.md", "docs/ENGINEERING_GUIDE.md", "docs/OPS_INBOX.md",
                  "docs/REQUEST_BRIEFING.md", "docs/COPILOT_GUIDE.md", "docs/ISSUE_EDITS.md", "HANDLER.md", "AGENTS.md", "인수인계/PR_병합_방법.md",
                  "인수인계/운영자_요청함_사용법.md", "인수인계/요청함/README.md", ".github/editorial/TELEGRAM_SETUP.md")


def doc(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class DocumentedBehaviorTest(unittest.TestCase):
    """운영자·AI 가 읽는 문서가 새 동작을 같게 말한다 — 'PR 을 만들면 검사가 한 번 더 돈다'·'초록이 될 때까지 기다린다' 같은 옛 설명이 남지 않았는지(작업·검증 기록 문서는 제외)."""

    OLD = (
        "PR 검사(약 2분)가 한 번 더",
        "PR 을 만들면 PR 검사",
        "병합 결과 트리를 보는 검사라 그대로 둡니다",
        "병합 결과 트리를 보는 검사라 그대로 두었습니다",
        "main push·PR·수동",
        "main push, 모든 PR",
        "(main push·모든 PR)",
        "자동(main·PR·`ai/claude/**` 브랜치 push)",
        "자동(main push·`ai/claude/**` 브랜치 push·PR)",
        "main 과 갈라진 지점 <해시>",
        "main 과 갈라진 지점(merge-base)입니다",
        "PR 검사 실패는 병합 전이라 보내지 않",
        "AI 브랜치·PR·수동 실행에서는 안 돕니다",
        "광고 표면 무승인 변경(push·PR만)",
        "검사가 **모두 초록 체크**가 될 때까지 기다린다",
    )

    def test_no_document_still_says_that_creating_a_pull_request_starts_the_check_again(self):
        for rel in READ_BY_PEOPLE:
            text = doc(rel)
            for old in self.OLD:
                self.assertNotIn(old, text, (rel, old))

    def test_the_guides_say_the_new_behaviour_in_the_words_the_workflow_uses(self):
        actions, runbook = doc("docs/ACTIONS_GUIDE.md"), doc("docs/AGENT_RUNBOOK.md")
        notice = "시험 병합 직전의 main 끝"
        self.assertIn(f"::notice title=광고 표면 검사 기준::{notice}", (ROOT / ".github" / "workflows" / "guardrails.yml").read_text(encoding="utf-8"))
        for text in (actions, runbook):
            self.assertIn(notice, text)                                              # AI 가 공개 REST 로 읽는 주석 문구가 문서와 같다
        for needle in ("PR(`pull_request`)로는 돌지 않습니다", "어느 브랜치든 push 할 때", "`origin/main` 을 **시험 병합**", "main 과 충돌하면 이 검사가 실패합니다",
                       "병합 직후 main push 로 같은 검사가 한 번 더 돌고 실패하면 휴대폰(텔레그램)으로 알립니다", "`시험 병합 직전의 main 끝 <해시>`", "Skipped(건너뜀)"):
            self.assertIn(needle, actions, needle)
        for needle in ("검사가 새로 돌지 않습니다", "`주석[notice] 시험 병합 직전의 main 끝 <해시>`", "최신 main 에서 새 브랜치를 다시 만들어", "병합 직후 main 검사가 한 번 더 돌아 실패하면 휴대폰으로 알립니다"):
            self.assertIn(needle, runbook, needle)

    def test_the_operator_guides_tell_the_operator_to_merge_right_away(self):
        merge = doc("인수인계/PR_병합_방법.md")
        for needle in ("이미 끝난 초록 체크", "기다리지 않고 바로 병합하면 됩니다", "Skipped", "병합 직후 main 의 검사도 한 번 더 돌고, 실패하면 휴대폰(텔레그램)으로 알립니다"):
            self.assertIn(needle, merge, needle)
        self.assertIn("이미 끝난 초록 체크인지 확인(PR 을 만들 때 새로 도는 검사는 없습니다)", doc("인수인계/운영자_요청함_사용법.md"))
        self.assertIn("PR 을 만들 때 새로 도는 검사가 없습니다", doc("인수인계/요청함/README.md"))

    def test_the_rule_tables_and_the_defect_register_carry_the_change(self):
        security, engineering = doc("docs/SECURITY_GUARDRAILS.md"), doc("docs/ENGINEERING_GUIDE.md")
        row = next(line for line in security.splitlines() if line.startswith("| G-A11 |"))
        for needle in ("PR(`pull_request`)로 돌지 않고 어느 브랜치든 push 로 돈다", "러너 안에서만", "`git push`", "시험 병합 직전의 `origin/main` 끝", "건너뛴 초록이 아니라 단계 실패",
                       "tests/test_guardrails_precheck.py", "tests/test_pr_ready_workflows.py"):
            self.assertIn(needle, row, needle)
        self.assertLess(security.index("| G-A10 |"), security.index("| G-A11 |"))             # 번호 순서
        self.assertIn("`closed`·`labeled`·`unlabeled`", next(line for line in security.splitlines() if line.startswith("| G-O8 |")))
        self.assertIn("`closed`·`labeled`·`unlabeled`", doc("docs/OPS_INBOX.md"))
        w12 = next(line for line in engineering.splitlines() if line.startswith("| W12 |"))
        self.assertIn("tests/test_pr_ready_workflows.py", w12)
        defects = doc("docs/DEFECT_REGISTER.md")
        d87 = next(line for line in defects.splitlines() if line.startswith("| **D-87** |"))
        for needle in ("`guardrails.yml`", "`pr-scope-check.yml`", "`ops-inbox.yml`", "첫 실제 실행 관측 완료", "건너뜀 줄 둘"):
            self.assertIn(needle, d87, needle)
        self.assertLess(defects.index("| **D-86** |"), defects.index("| **D-87** |"))
        self.assertTrue(any(line.startswith("| 가드레일 시험 병합(D-87) 병합 뒤") for line in defects.splitlines()))          # 관측 체크리스트에도 첫 실제 실행에서 볼 것이 적혀 있다

    def test_the_architecture_and_briefing_tables_state_the_real_triggers(self):
        architecture, briefing = doc("docs/ARCHITECTURE.md"), doc("docs/REQUEST_BRIEFING.md")
        guardrails_row = next(line for line in architecture.splitlines() if "| `guardrails.yml` |" in line)
        for needle in ("어느 브랜치든 push 때", "PR 로는 돌지 않아", "시험 병합", "충돌하면 실패한다", "시험 병합 직전의 main 끝"):
            self.assertIn(needle, guardrails_row, needle)
        scope_row = next(line for line in architecture.splitlines() if "| `pr-scope-check.yml` |" in line)
        self.assertIn("AI 브랜치 `ai/claude/` 의 PR 은 job 이 건너뜀", scope_row)
        self.assertIn("AI 브랜치 `ai/claude/` 의 PR 은 건너뜀", next(line for line in briefing.splitlines() if "| `pr-scope-check.yml` |" in line))
        self.assertIn("PR 로는 돌지 않아", next(line for line in briefing.splitlines() if "| `guardrails.yml` |" in line))


if __name__ == "__main__":
    unittest.main()
