"""pages.yml 게시 잡의 가지 가드 시험(결함 D-375 — 확인 015 의 AP6 F113, 병합은 운영자만).

사이트 게시(`deploy` 잡)는 저장소의 기본 가지에서 돈 실행만 한다. 푸시 트리거는 처음부터 main 으로 제한돼 있었지만 수동 실행(`workflow_dispatch`)과
Chance 두 워크플로의 배포 요청(`gh workflow run pages.yml --ref "${GITHUB_REF_NAME}"`)은 가지를 가리지 않아서, 다른 가지에서 누르면 그 가지의 내용이
공개 사이트에 올라갈 수 있었다. 이 시험은 GitHub Actions 를 돌릴 수 없는 곳에서 파일을 읽어 아래를 확인한다.

1) 가드의 모양: 게시 잡 한 곳에만, 기본 가지 변수와 견주는 식 그대로(가지 이름을 글자로 박지 않는다), 빌드·반영 확인 잡과 단계에는 조건이 없다.
2) 그 식이 여러 입력에서 내는 값: 기본 가지·다른 가지·빈 값·값이 없음·기본 가지 이름이 main 이 아닌 저장소·태그.
3) 게시가 건너뛰어지면 반영 확인도 같이 건너뛰고 빌드는 그대로 돈다(빌드 검사는 어느 가지에서나 유용하다).
4) Chance 두 워크플로의 배포 요청 줄이 그대로다(이 갈래는 그 줄을 바꾸지 않았다).
5) 안내 문서(절차서의 pages.yml 행·결함 표·관측 체크리스트)가 이 동작을 적었다.

식 해석기는 tests/test_workflow_names.py 의 것을 그대로 쓴다. 한계(그 파일 해석기의 머리 주석): 문자열끼리의 비교는 대소문자를 구분하지 않고(GitHub 도 같다),
종류가 다른 값끼리의 형 변환은 구현돼 있지 않다. 그래서 아래 표에는 '문자열 대 문자열'과 '문자열 대 없음'만 넣었다. 일부러 넣지 않은 조합: '빈 문자열 대 없음'(GitHub 는 둘을
숫자 0 으로 바꿔 참, 해석기는 거짓)과 '둘 다 없음'(둘 다 참이지만 닫힌 쪽이 아니다). 실제 이벤트에는 ref_name 과 기본 가지가 항상 있어 두 조합은 일어나지 않는다.
"""
import re
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from test_workflow_names import load, render

ROOT = Path(_bootstrap.ROOT)
RUNBOOK = ROOT / "docs" / "AGENT_RUNBOOK.md"
REGISTER = ROOT / "docs" / "DEFECT_REGISTER.md"

GUARD = "github.ref_name == github.event.repository.default_branch"


def passes(expression, ref_name, default_branch):
    """잡의 if 식을 GitHub 규칙대로 평가한다. ref_name·default_branch 에 None 을 주면 그 값이 컨텍스트에 아예 없는 경우(null)다."""
    text = expression if "${{" in expression else "${{ " + expression + " }}"
    github = {"event": {}}
    if ref_name is not None:
        github["ref_name"] = ref_name
    if default_branch is not None:
        github["event"]["repository"] = {"default_branch": default_branch}
    return render(text, {"github": github}) == "true"


def jobs_that_run(workflow, ref_name, default_branch):
    """이 워크플로가 쓰는 만큼만 GitHub 의 잡 규칙을 흉내 낸다: 잡은 needs 의 잡이 모두 돌았고 자기 if 가 참일 때 돈다(if 가 없으면 '앞 잡 성공'이 기본 조건이라 건너뛴 잡에 이어진 잡도 건너뛴다)."""
    ran = {}
    for name, job in workflow["jobs"].items():
        needs = job.get("needs", [])
        needs = [needs] if isinstance(needs, str) else list(needs)
        runs = all(ran.get(need, False) for need in needs)       # 앞 잡은 정의 순서상 앞에 있다(순서는 test_chance_draft_workflow 가 못박는다)
        if runs and "if" in job:
            runs = passes(job["if"], ref_name, default_branch)
        ran[name] = runs
    return ran


# (설명, ref_name, 기본 가지, 빌드, 게시, 반영 확인) — 빌드는 어느 가지에서나 돈다(건너뛰는 것은 게시와 반영 확인뿐이라 다른 가지의 빌드가 깨지는지 보는 데도 쓸모가 있다)
SCENARIOS = (
    ("기본 가지(main)의 push 나 수동 실행", "main", "main", True, True, True),
    ("다른 가지에서 수동 실행(이 변경이 막으려는 경우)", "ai/claude/NO-MERGE-example", "main", True, False, False),
    ("Chance 가 요청한 실행인데 요청한 가지가 main 이 아님", "ai/claude/M999-example", "main", True, False, False),
    ("ref_name 이 빈 값", "", "main", True, False, False),
    ("기본 가지 정보가 없음(닫힌 쪽으로 건너뜀)", "main", None, True, False, False),
    ("ref_name 이 없음(닫힌 쪽으로 건너뜀)", None, "main", True, False, False),
    ("기본 가지 이름이 main 이 아닌 저장소에서 그 가지(이름을 글자로 박지 않았다는 증거)", "trunk", "trunk", True, True, True),
    ("그 저장소에서 main 으로 돈 실행", "main", "trunk", True, False, False),
    ("태그에서 수동 실행(ref_name 이 태그 이름)", "v1.0", "main", True, False, False),
    ("main 으로 시작하기만 하는 가지(main-fix)", "main-fix", "main", True, False, False),
    ("main 으로 시작하기만 하는 가지(main/fix)", "main/fix", "main", True, False, False),
    ("흔한 다른 가지 이름 dev 는 특별 취급하지 않는다", "dev", "main", True, False, False),
    ("흔한 옛 기본 가지 이름 master 도 특별 취급하지 않는다", "master", "main", True, False, False),
)


class GuardShapeTest(unittest.TestCase):
    """가드가 어느 잡에, 어떤 식으로 있는지(워크플로 파일을 직접 읽는다)."""

    def setUp(self):
        self.workflow = load("pages.yml")
        self.jobs = self.workflow["jobs"]

    def test_the_deploy_job_compares_the_ref_name_with_the_default_branch_variable(self):
        guard = self.jobs["deploy"].get("if")
        self.assertIsInstance(guard, str, "게시 잡에 if 조건이 없다 — 다른 가지에서 눌러도 게시된다")
        normalized = " ".join(guard.replace("${{", " ").replace("}}", " ").split())
        self.assertEqual(normalized, GUARD, "기본 가지 이름은 변수에서 읽는다(main 을 글자로 박지 않는다: 이름이 바뀌어도 따라가고 시험이 같은 식을 평가한다)")

    def test_the_condition_is_on_the_deploy_job_only_and_no_step_has_one(self):
        self.assertEqual([name for name, job in self.jobs.items() if "if" in job], ["deploy"])
        for name, job in self.jobs.items():
            for step in job["steps"]:
                self.assertNotIn("if", step, (name, step.get("name")))

    def test_a_skipped_deploy_skips_the_verification_and_nothing_overrides_that(self):
        self.assertEqual(self.jobs["deploy"]["needs"], "build")
        self.assertEqual(self.jobs["verify"]["needs"], "deploy")
        self.assertNotIn("if", self.jobs["verify"], "반영 확인에 조건(always() 등)이 있으면 게시가 건너뛰어져도 확인이 돌아 빨강이 된다")

    def test_the_trigger_still_lets_other_branches_run_the_build(self):
        """가지를 막는 것은 게시 잡의 조건이다. 수동 실행(입력 없음)은 그대로 열려 있어서 다른 가지에서도 빌드 검사는 돈다."""
        self.assertEqual(sorted(self.workflow["on"]), ["push", "workflow_dispatch"])
        self.assertIsNone(self.workflow["on"]["workflow_dispatch"])
        self.assertEqual(self.workflow["on"]["push"]["branches"], ["main"])


class GuardEvaluationTest(unittest.TestCase):
    """파일 속 가드 식을 입력별로 평가한다(식을 고치면 이 표가 먼저 빨개진다)."""

    def setUp(self):
        self.workflow = load("pages.yml")

    def test_the_guard_expression_in_the_file_gives_the_expected_value_for_every_scenario(self):
        guard = self.workflow["jobs"]["deploy"]["if"]
        for label, ref_name, default_branch, _build, deploy, _verify in SCENARIOS:
            with self.subTest(label):
                self.assertIs(passes(guard, ref_name, default_branch), deploy)

    def test_the_whole_chain_for_every_scenario(self):
        for label, ref_name, default_branch, build, deploy, verify in SCENARIOS:
            with self.subTest(label):
                self.assertEqual(jobs_that_run(self.workflow, ref_name, default_branch), {"build": build, "deploy": deploy, "verify": verify})

class HarnessSelfTest(unittest.TestCase):
    """위 평가기가 '항상 참'이나 '항상 거짓'으로 시험을 헛되게 통과시키지 않는지."""

    def test_passes_tells_equal_from_unequal_and_notices_a_flipped_operator(self):
        self.assertIs(passes("github.ref_name == github.event.repository.default_branch", "a", "a"), True)
        self.assertIs(passes("github.ref_name == github.event.repository.default_branch", "a", "b"), False)
        self.assertIs(passes("github.ref_name != github.event.repository.default_branch", "a", "a"), False)
        self.assertIs(passes("github.ref_name != github.event.repository.default_branch", "a", "b"), True)
        self.assertIs(passes("${{ github.ref_name == 'main' }}", "main", None), True)
        self.assertIs(passes("github.ref_name == 'main'", "dev", None), False)

    def test_jobs_that_run_follows_conditions_and_skips_what_needs_a_skipped_job(self):
        def workflow(condition):
            second = {"needs": "first"} if condition is None else {"needs": "first", "if": condition}
            return {"jobs": {"first": {}, "second": second, "third": {"needs": "second"}}}

        self.assertEqual(jobs_that_run(workflow(None), "x", "x"), {"first": True, "second": True, "third": True})
        self.assertEqual(jobs_that_run(workflow("github.ref_name == 'x'"), "x", None), {"first": True, "second": True, "third": True})
        self.assertEqual(jobs_that_run(workflow("github.ref_name == 'y'"), "x", None), {"first": True, "second": False, "third": False})
        skipped_dependency = {"jobs": {"a": {}, "c": {"if": "false"}, "b": {"needs": ["a", "c"]}}}      # 목록으로 적은 needs 도 하나라도 건너뛰었으면 건너뛴다
        self.assertEqual(jobs_that_run(skipped_dependency, "x", None), {"a": True, "c": False, "b": False})


class ChanceDispatchUnchangedTest(unittest.TestCase):
    """Chance 두 워크플로의 배포 요청은 요청한 실행 자신의 가지로 pages.yml 을 부른다. 이 갈래는 그 줄을 바꾸지 않았다(가드가 그 가지를 보고 판단한다)."""

    REQUEST = 'gh workflow run pages.yml --ref "${GITHUB_REF_NAME}"'

    def test_both_chance_workflows_still_request_the_deploy_for_their_own_ref(self):
        for name in ("chanceblog.yml", "chance-fix-images.yml"):
            with self.subTest(name):
                requests = [step for step in load(name)["jobs"]["build"]["steps"] if "gh workflow run" in step.get("run", "")]
                self.assertEqual(len(requests), 1)
                self.assertIn(self.REQUEST, requests[0]["run"])
                self.assertEqual(requests[0]["if"], "steps.commit.outputs.pushed == 'true'")


class DocumentationTest(unittest.TestCase):
    """안내 문서가 가드를 적었다: 절차서의 pages.yml 행, 결함 표의 D-375·D-376, 관측 체크리스트의 병합 뒤 확인 줄."""

    RUNBOOK_TEXT = RUNBOOK.read_text(encoding="utf-8")
    REGISTER_TEXT = REGISTER.read_text(encoding="utf-8")

    def register_rows(self):
        return {m.group(1): m.group(0) for m in re.finditer(r"(?m)^\| \*\*(D-\d+)\*\* \|.*$", self.REGISTER_TEXT)}

    def test_the_runbook_row_keeps_main_push_and_says_other_branches_skip_the_publish(self):
        row = next(line for line in self.RUNBOOK_TEXT.splitlines() if line.startswith("| `pages.yml` |"))
        self.assertIn("main push", row)                                  # tests/test_agent_docs.py 도 같은 낱말을 요구한다
        for needle in ("기본 가지가 아닌 가지", "게시", "건너뜀", "D-375"):
            self.assertIn(needle, row, needle)
        self.assertEqual(row.count("|"), 5, "표의 네 칸 — 칸 안에 세로선이 없다")

    def test_the_register_rows_d375_and_d376_exist_once_with_six_cells_that_each_say_their_part(self):
        """낱말은 칸별로 본다 — 행 전체에서 찾으면 다른 칸에 같은 낱말이 있어 한 칸에서 지워도 통과한다(변이 D4 가 살아남아 보강)."""
        ids = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", self.REGISTER_TEXT)
        self.assertEqual(len(ids), len(set(ids)))
        rows = self.register_rows()
        # 칸: 0 ID · 1 심각도 · 2 결함 · 3 근거 · 4 상태 · 5 해결 계획
        needles = {"D-375": {2: ("pages.yml", "workflow_dispatch", "가지"), 3: ("확인 015", "F113", "tests/test_pages_branch_guard.py"),
                             4: ("해결",), 5: ("default_branch", "건너뜀", "관측 체크리스트")},
                   "D-376": {2: ("concurrency", "github-pages", "cancel-in-progress", "취소"), 3: ("pages.yml", "ACTIONS_GUIDE"),
                             4: ("열림",), 5: ("별도 승인",)}}
        for row_id, by_cell in needles.items():
            self.assertEqual(ids.count(row_id), 1, row_id)
            self.assertEqual(rows[row_id].count("|"), 7, row_id)         # 표의 여섯 칸 — 칸 안에 세로선이 없다
            cells = [cell.strip() for cell in rows[row_id].strip().strip("|").split("|")]
            self.assertEqual(len(cells), 6, row_id)
            for index, words in by_cell.items():
                for word in words:
                    self.assertIn(word, cells[index], f"{row_id} 의 {index}번 칸: {word}")

    def test_the_observation_checklist_has_the_after_merge_check(self):
        rows = [line for line in self.REGISTER_TEXT.splitlines() if line.startswith("| pages.yml 가지 가드(D-375)")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].count("|"), 4, "관측 체크리스트의 세 칸")
        for needle in ("[공통] 사이트 자동 배포", "세 잡", "초록", "건너뜀"):
            self.assertIn(needle, rows[0], needle)

    def test_the_new_doc_lines_keep_the_doc_rules(self):
        """문서 규칙: 물결표(범위는 en 대시)와 링크가 없다."""
        lines = [line for line in self.RUNBOOK_TEXT.splitlines() if line.startswith("| `pages.yml` |")]
        lines += [row for row_id, row in self.register_rows().items() if row_id in ("D-375", "D-376")]
        lines += [line for line in self.REGISTER_TEXT.splitlines() if line.startswith("| pages.yml 가지 가드(D-375)")]
        self.assertEqual(len(lines), 4)
        for line in lines:
            self.assertNotRegex(line, "[~～〜]")
            self.assertNotRegex(line, r"(?i)https?://|www\.")


if __name__ == "__main__":
    unittest.main()
