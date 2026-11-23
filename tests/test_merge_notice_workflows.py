"""병합 알림 자동화 워크플로 둘(`merge-ready-notice.yml`·`merge-confirm-notice.yml`)의 모양 시험 — 운영자 확인 031 의 보기 2(2026-11-23).

`workflow_run` 은 시크릿을 쥔 채 기본 가지의 파일로 도는 위험한 트리거라, 이 시험이 두 파일을 한 줄씩 고정한다(`tests/test_auto_pr_workflow.py` 와 같은 방식):
 1. 모양(YAML 을 읽어서) — 트리거는 `workflow_run` 하나(따라 도는 워크플로·가지 필터가 정해진 값), 권한은 읽기 셋뿐, 체크아웃은 기본 가지 `ref`·`persist-credentials: false`, 외부 액션은 둘뿐,
    `${{ }}` 는 정해진 자리의 정해진 식뿐이고 `run:` 에는 하나도 없다, 시크릿은 맨 끝 발송 단계의 env 에만 있고 그 단계는 `steps.decide.outputs.send == 'yes'` 일 때만 돈다.
    같은 검사를 일부러 틀리게 만든 사본에 돌려 시험이 정말 잡는지도 본다(살아남는 변이가 없어야 한다).
 2. 두 파일이 같은 뼈대인지, 따라 도는 워크플로 이름·가지 필터가 실제 워크플로와 같은지, 동시 실행 그룹이 다른 워크플로와 겹치지 않는지.
 3. 켬 상태 파일이 `off` 로 병합되는지, 문서가 같은 말을 하는지(문서는 tests/test_merge_notice_docs.py).
"""
import re
import sys
import unittest
from pathlib import Path

import yaml

import _bootstrap
from pipeline import auto_notice as an
from test_auto_pr_workflow import glob_to_regex

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

WORKFLOWS = ROOT / ".github" / "workflows"
PERMISSIONS = {"contents": "read", "pull-requests": "read", "actions": "read"}
TELEGRAM_ENV = {"TELEGRAM_BOT_TOKEN": "${{ secrets.TELEGRAM_BOT_TOKEN }}", "TELEGRAM_CHAT_ID": "${{ secrets.TELEGRAM_CHAT_ID }}"}
DECIDE_ENV = {
    "GITHUB_TOKEN": "${{ github.token }}",
    "NOTICE_RUN_ID": "${{ github.event.workflow_run.id }}",
    "NOTICE_RUN_BRANCH": "${{ github.event.workflow_run.head_branch }}",
    "NOTICE_RUN_SHA": "${{ github.event.workflow_run.head_sha }}",
    "NOTICE_RUN_EVENT": "${{ github.event.workflow_run.event }}",
    "NOTICE_RUN_CONCLUSION": "${{ github.event.workflow_run.conclusion }}",
    "NOTICE_RUN_REPO": "${{ github.event.workflow_run.head_repository.full_name }}",
    "NOTICE_DEFAULT_BRANCH": "${{ github.event.repository.default_branch }}",
}
CHECKOUT = {"uses": "actions/checkout@v6", "with": {"ref": "${{ github.event.repository.default_branch }}", "persist-credentials": False}}
SETUP = {"uses": "actions/setup-python@v6", "with": {"python-version": "3.12"}}
SEND_NAME = "텔레그램으로 보내기(켬 상태가 on 일 때만)"
SEND_IF = "steps.decide.outputs.send == 'yes'"
SEND_RUN = "python -m pipeline.auto_notice send"
READY_FILTERS = ["ai/claude/M[0-9][0-9][0-9]-*", "ai/claude/M[0-9][0-9][0-9][0-9]-*"]

SPECS = {
    "merge-ready-notice.yml": {
        "name": "[공통] 병합 부탁 알림 자동 보내기", "target": "[공통] 병합 부탁 PR 자동 만들기", "branches": READY_FILTERS,
        "group": "merge-ready-notice-${{ github.event.workflow_run.head_sha }}", "job_name": "병합 부탁 알림 판정과 발송",
        "decide_name": "병합 부탁 문장 만들기(켬 상태가 꺼짐이면 곧바로 끝)", "decide_run": "python -m pipeline.auto_notice merge-ready"},
    "merge-confirm-notice.yml": {
        "name": "[공통] 병합완료 확인 알림 자동 보내기", "target": "[공통] 저장소 규칙·테스트 자동 검사", "branches": ["main"],
        "group": "merge-confirm-notice-${{ github.event.workflow_run.head_sha }}", "job_name": "병합완료 확인 판정과 발송",
        "decide_name": "병합완료 확인 문장 만들기(켬 상태가 꺼짐이면 곧바로 끝)", "decide_run": "python -m pipeline.auto_notice merge-confirm"},
}
# 코드 줄(주석 뺀 글)에 있으면 안 되는 것: (이유, 정규식)
FORBIDDEN = [
    ("다른 트리거", re.compile(r"\b(?:pull_request_target|pull_request|issue_comment|schedule|workflow_dispatch|workflow_call|repository_dispatch)\b|^\s*push:|^\s*issues:|^\s*create:|^\s*release:", re.M)),
    ("병합·승인·라벨·코멘트 호출", re.compile(r"--admin|auto_merge|enable_auto|/reviews|event=APPROVE|--approve|\bgh\s|\bgit\s|gh api|pulls/", re.I)),
    ("셸이 글을 해석하는 길", re.compile(r"\beval\b|\bbash\s+-c\b|\bsh\s+-c\b|\bsource\b|`|\bcurl\b|\bwget\b")),
    ("환경·출력 파일 쓰기(출력은 파이썬이 고정 한 줄만 쓴다)", re.compile(r"GITHUB_ENV|GITHUB_OUTPUT|GITHUB_PATH|set-output|add-mask|GITHUB_STEP_SUMMARY")),
    ("실패 은폐·셸 약화", re.compile(r"continue-on-error|\bset\s+\+[a-zA-Z]|\|\|\s*true\b|\btrap\b|\bshell:|working-directory")),
    ("가지 코드 체크아웃", re.compile(r"ref:\s*\$\{\{\s*github\.(?:head_ref|ref|event\.pull_request|event\.workflow_run)|ref:\s*refs/", re.M)),
    ("외부 액션 추가", re.compile(r"uses:\s*(?!actions/checkout@v6\s*$|actions/setup-python@v6\s*$)\S+", re.M)),
]


def load_text(name):
    return (WORKFLOWS / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def code_text(text):
    """주석만 있는 줄을 뺀 글(헤더 설명에는 규칙 이름·금지 낱말이 나온다)."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def expressions(text):
    return sorted(re.findall(r"\$\{\{.*?\}\}", code_text(text)))


def static_problems(text, spec):
    """워크플로 글의 모양이 규칙과 다른 곳의 목록(없으면 빈 목록). 아래 시험이 진짜 파일에는 빈 목록을, 일부러 망가뜨린 사본에는 비어 있지 않은 목록을 기대한다."""
    problems = []
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return ["워크플로 최상위가 표가 아님"]
    triggers = vr._triggers(data)
    wanted = {"workflow_run": {"workflows": [spec["target"]], "types": ["completed"], "branches": spec["branches"]}}
    if triggers != wanted:
        problems.append(f"트리거가 정해진 모양이 아님: {triggers}")
    if data.get("permissions") != PERMISSIONS:
        problems.append(f"권한이 정해진 셋(읽기)이 아님: {data.get('permissions')}")
    if data.get("concurrency") != {"group": spec["group"], "cancel-in-progress": False}:
        problems.append(f"동시 실행 설정이 다름: {data.get('concurrency')}")
    extra = sorted(set(map(str, data)) - {"name", "on", "True", "permissions", "concurrency", "jobs"})
    if extra:
        problems.append(f"최상위에 더 있는 키: {extra}")
    if data.get("name") != spec["name"] or "run-name" in data:
        problems.append("워크플로 이름이 다르거나 run-name 이 있음")
    jobs = data.get("jobs") or {}
    if list(jobs) != ["notify"]:
        return problems + [f"job 이 notify 하나가 아님: {list(jobs)}"]
    job = jobs["notify"]
    if set(job) != {"name", "runs-on", "timeout-minutes", "steps"} or job.get("name") != spec["job_name"]:
        problems.append(f"job 의 키·이름이 정해진 것과 다름: {sorted(job)}")
    if job.get("runs-on") != "ubuntu-latest" or job.get("timeout-minutes") != 10:
        problems.append("runs-on·timeout-minutes 가 다름")
    steps = job.get("steps") or []
    if len(steps) != 4:
        return problems + [f"단계가 넷이 아님: {len(steps)}"]
    if steps[0] != CHECKOUT:
        problems.append(f"체크아웃 단계가 정해진 것과 다름: {steps[0]}")
    if steps[1] != SETUP:
        problems.append(f"setup-python 단계가 정해진 것과 다름: {steps[1]}")
    decide = {"name": spec["decide_name"], "id": "decide", "env": DECIDE_ENV, "run": spec["decide_run"]}
    if steps[2] != decide:
        problems.append(f"판정 단계가 정해진 것과 다름: {steps[2]}")
    send = {"name": SEND_NAME, "if": SEND_IF, "env": TELEGRAM_ENV, "run": SEND_RUN}
    if steps[3] != send:
        problems.append(f"발송 단계가 정해진 것과 다름: {steps[3]}")
    for index, step in enumerate(steps):
        run = step.get("run")
        if isinstance(run, str) and "${{" in run:
            problems.append(f"{index + 1}번째 단계의 run 안에 ${{{{ }}}} 가 있음")
    code = code_text(text)
    for reason, rx in FORBIDDEN:
        found = rx.search(code)
        if found:
            problems.append(f"{reason}: {found.group(0)!r}")
    wanted_expressions = sorted(["${{ github.event.workflow_run.head_sha }}", "${{ github.event.repository.default_branch }}", "${{ github.token }}", "${{ github.event.workflow_run.id }}",
                                 "${{ github.event.workflow_run.head_branch }}", "${{ github.event.workflow_run.head_sha }}", "${{ github.event.workflow_run.event }}",
                                 "${{ github.event.workflow_run.conclusion }}", "${{ github.event.workflow_run.head_repository.full_name }}", "${{ github.event.repository.default_branch }}",
                                 "${{ secrets.TELEGRAM_BOT_TOKEN }}", "${{ secrets.TELEGRAM_CHAT_ID }}"])
    if expressions(text) != wanted_expressions:
        problems.append(f"`${{{{ }}}}` 식의 목록이 정해진 것과 다름: {expressions(text)}")
    if len(re.findall(r"secrets\s*[.\[]", code)) != 2:
        problems.append("시크릿 참조가 정확히 둘(발송 단계 env)이 아님")
    problems += vr._workflow_run_problems(data, vr.WORKFLOW_RUN_ALLOWED[f".github/workflows/{spec['file']}"]) if "file" in spec else []
    return problems


def with_file(name):
    return dict(SPECS[name], file=name)


class WorkflowShapeTest(unittest.TestCase):
    def test_the_real_files_have_no_static_problem(self):
        for name in SPECS:
            with self.subTest(name):
                self.assertEqual(static_problems(load_text(name), with_file(name)), [])

    def test_each_file_has_exactly_the_four_steps_in_order(self):
        for name, spec in SPECS.items():
            with self.subTest(name):
                steps = yaml.safe_load(load_text(name))["jobs"]["notify"]["steps"]
                self.assertEqual([step.get("uses") or step.get("id") or step.get("name") for step in steps], ["actions/checkout@v6", "actions/setup-python@v6", "decide", SEND_NAME])
                self.assertEqual(steps[-1]["env"], TELEGRAM_ENV)
                self.assertEqual([index for index, step in enumerate(steps) if "env" in step and set(step["env"]) & set(TELEGRAM_ENV)], [3])      # 시크릿은 맨 끝 발송 단계에만
                self.assertNotIn("env", steps[0])
                self.assertNotIn("env", steps[1])
                self.assertEqual(sorted(steps[2]["env"]), sorted(DECIDE_ENV))
                self.assertNotIn("secrets", str(steps[2]))                                         # 판정 단계에는 시크릿이 없다
                self.assertEqual(steps[3]["if"], SEND_IF)

    def test_names_follow_the_repository_rules(self):
        for name, spec in SPECS.items():
            with self.subTest(name):
                data = yaml.safe_load(load_text(name))
                self.assertEqual(data["name"], spec["name"])
                self.assertTrue(data["name"].startswith("[공통] "))
                self.assertRegex(data["jobs"]["notify"]["name"], r"[가-힣]")
                for step in data["jobs"]["notify"]["steps"][2:]:
                    self.assertRegex(step["name"], r"[가-힣]")
                self.assertNotIn("run-name", data)                                                  # 실행 목록에 가지·커밋 글이 제목으로 보이지 않게
                self.assertFalse(re.match(r"\[", data["jobs"]["notify"]["name"]))
                files = [f".github/workflows/{name}"]
                findings = vr.check_workflows(ROOT, files) + vr.check_workflow_names(ROOT, files) + vr.check_workflow_prefixes(ROOT, files) + vr.check_telegram_secrets(ROOT, files)
                self.assertEqual([finding.line() for finding in findings], [])                      # 경고도 없다(WF-1 에서 WF-13)

    def test_the_trigger_is_exactly_one_workflow_run_with_the_target_and_filters(self):
        for name, spec in SPECS.items():
            with self.subTest(name):
                data = yaml.safe_load(load_text(name))
                self.assertEqual(vr._triggers(data), {"workflow_run": {"workflows": [spec["target"]], "types": ["completed"], "branches": spec["branches"]}})
                head = load_text(name).split("\npermissions:")[0]
                on_block = [line for line in head.split("\non:\n")[1].splitlines() if line.strip() and not line.strip().startswith("#")]
                self.assertEqual(on_block[:4], ["  workflow_run:", f'    workflows: ["{spec["target"]}"]', "    types: [completed]", "    branches:"])

    def test_the_target_names_are_the_real_names_of_the_workflows_they_follow(self):
        self.assertEqual(SPECS["merge-ready-notice.yml"]["target"], yaml.safe_load(load_text("auto-pr.yml"))["name"])
        self.assertEqual(SPECS["merge-confirm-notice.yml"]["target"], yaml.safe_load(load_text("guardrails.yml"))["name"])

    def test_the_ready_branch_filters_are_the_push_filters_of_the_auto_pr_workflow(self):
        """병합 부탁 알림은 자동 PR 워크플로가 도는 가지에서만 깨어난다 — 필터 두 줄이 auto-pr.yml 의 push 필터와 글자까지 같다."""
        auto = yaml.safe_load(load_text("auto-pr.yml"))
        self.assertEqual(vr._triggers(auto)["push"]["branches"], READY_FILTERS)

    def test_the_confirm_workflow_follows_the_check_that_runs_on_main_pushes(self):
        guardrails = yaml.safe_load(load_text("guardrails.yml"))
        self.assertIn("push", vr._triggers(guardrails))                                             # main 병합 직후의 검사는 push 로 돈다(G-A11)

    def test_permissions_are_the_three_reads_and_no_job_asks_for_more(self):
        for name in SPECS:
            with self.subTest(name):
                data = yaml.safe_load(load_text(name))
                self.assertEqual(data["permissions"], PERMISSIONS)
                self.assertNotIn("permissions", data["jobs"]["notify"])
                for value in data["permissions"].values():
                    self.assertEqual(value, "read")
                text = code_text(load_text(name))
                self.assertNotRegex(text, r"write|admin")

    def test_every_dollar_brace_expression_is_in_a_with_env_or_concurrency_value_never_in_a_run(self):
        for name in SPECS:
            with self.subTest(name):
                data = yaml.safe_load(load_text(name))
                for step in data["jobs"]["notify"]["steps"]:
                    self.assertNotIn("${{", step.get("run", ""))
                    self.assertNotIn("${{", str(step.get("if", "")))
                self.assertEqual(len(expressions(load_text(name))), 12)

    def test_the_decide_env_carries_the_trigger_values_only_as_env_and_the_names_match_what_the_module_reads(self):
        source = (ROOT / "pipeline" / "auto_notice.py").read_text(encoding="utf-8")
        for env_name in DECIDE_ENV:
            if env_name.startswith("NOTICE_"):
                self.assertEqual(len(re.findall(rf'"{env_name}"', source)), 1, env_name)           # 모듈이 그 이름을 읽는다(정확히 한 군데)
        self.assertIn('"GITHUB_TOKEN"', source)
        read_names = set(re.findall(r'get\("(NOTICE_[A-Z_]+)"\)', source))
        self.assertEqual(read_names, {name for name in DECIDE_ENV if name.startswith("NOTICE_")})

    def test_the_python_commands_exist_in_the_module_and_are_the_only_things_run(self):
        parser = an.build_parser()
        for name, spec in SPECS.items():
            command = spec["decide_run"].rsplit(" ", 1)[1]
            self.assertEqual(parser.parse_args([command]).command, command)
        self.assertEqual(parser.parse_args(["send"]).command, "send")

    def test_the_external_actions_are_exactly_the_ones_the_other_workflows_already_use(self):
        """새 액션을 들이지 않는다 — 두 파일의 `uses:` 는 정확히 `actions/checkout@v6`·`actions/setup-python@v6` 이고 둘 다 이 저장소의 다른 워크플로가 이미 같은 글자로 쓴다."""
        used_elsewhere = set()
        for path in sorted(WORKFLOWS.glob("*.yml")):
            if path.name in SPECS:
                continue
            for job in (yaml.safe_load(path.read_text(encoding="utf-8")).get("jobs") or {}).values():
                for step in job.get("steps") or []:
                    if isinstance(step, dict) and "uses" in step:
                        used_elsewhere.add(step["uses"])
        for name in SPECS:
            mine = {step["uses"] for step in yaml.safe_load(load_text(name))["jobs"]["notify"]["steps"] if "uses" in step}
            self.assertEqual(mine, {"actions/checkout@v6", "actions/setup-python@v6"}, name)
            self.assertLessEqual(mine, used_elsewhere, name)

    def test_the_two_files_are_the_same_skeleton(self):
        """두 파일의 차이는 이름·따라 도는 워크플로·가지 필터·동시 실행 그룹·job 이름·판정 단계의 이름과 명령뿐이다(뼈대가 갈라지면 한쪽만 약해진다)."""
        ready, confirm = (yaml.safe_load(load_text(name)) for name in SPECS)
        for data, spec in ((ready, SPECS["merge-ready-notice.yml"]), (confirm, SPECS["merge-confirm-notice.yml"])):
            data["name"], data["concurrency"], data["jobs"]["notify"]["name"] = "N", "C", "J"
            on = vr._triggers(data)["workflow_run"]
            on["workflows"], on["branches"] = ["W"], ["B"]
            decide = data["jobs"]["notify"]["steps"][2]
            decide["name"], decide["run"] = "D", "R"
        self.assertEqual(ready, confirm)

    def test_the_concurrency_groups_are_one_per_commit_and_do_not_collide_with_other_workflows(self):
        groups = {}
        for path in sorted(WORKFLOWS.glob("*.yml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            value = data.get("concurrency")
            group = value["group"] if isinstance(value, dict) else value
            if group:
                groups.setdefault(group, []).append(path.name)
        for name, spec in SPECS.items():
            self.assertEqual(groups[spec["group"]], [name], name)
            self.assertTrue(spec["group"].endswith("-${{ github.event.workflow_run.head_sha }}"))
        self.assertNotEqual(SPECS["merge-ready-notice.yml"]["group"], SPECS["merge-confirm-notice.yml"]["group"])
        for name in SPECS:
            self.assertIs(yaml.safe_load(load_text(name))["concurrency"]["cancel-in-progress"], False)      # 진행 중인 알림을 취소하지 않는다

    def test_the_header_comment_states_the_rules_and_the_limits(self):
        needles = ["병합하지 않는다", "G-A13", "G-A14", "workflow_run", "pull_request_target", "issue_comment", "schedule", "workflow_dispatch", "가지(PR 머리)의 코드는 내려받지도 실행하지도 않는다",
                   "persist-credentials: false", "WF-16", "env 로만", "쓰기 0", "off", "dry", "on", "pipeline/auto_notice.json", "T3", "첫 관측", "한계", "Re-run", "AI 의 요청 파일 알림이 병행한다",
                   "actions/checkout", "actions/setup-python", "새 의존성이 없다", "데스크톱 앱 저장소에는 텔레그램 시크릿이 없어", "기본 가지"]
        for name in SPECS:
            header = load_text(name).split("\non:\n")[0]
            for needle in needles:
                self.assertIn(needle, header, f"{name}: {needle}")
            self.assertNotIn(chr(0x7E), header)
            self.assertNotRegex(header, r"https?://")

    def test_the_confirm_header_documents_its_extra_limits(self):
        header = load_text("merge-confirm-notice.yml").split("\non:\n")[0]
        for needle in ("취소되거나 건너뛰어졌으면", "판정을 미루고", "300개", "2MB", "트리 일치", "트리 비교를 빼고", "변경 파일 수·이름 집합", "부모 수", "정확히 하나일 때뿐", "봇이 글을 올릴 때마다"):
            self.assertIn(needle, header, needle)
        ready = load_text("merge-ready-notice.yml").split("\non:\n")[0]
        for needle in ("자동 만들기 실행이 성공으로 끝났고", "머리 커밋이 이 실행의 커밋과 같고", "모두 끝나 성공(가드레일 포함)", "20초 간격으로 세 번", "노란 배너로 직접 만들었거나", "force-push"):
            self.assertIn(needle, ready, needle)


class BranchFilterTest(unittest.TestCase):
    CASES = [("ai/claude/M004-health-fit-2", True, True), ("ai/claude/M0045-x", True, True), ("ai/claude/M123-a.b_c-d", True, True), ("ai/claude/M004-" + "a" * 80, True, True),
             ("ai/claude/M004-" + "a" * 81, True, False), ("ai/claude/M004-", True, False), ("ai/claude/M004-한글", True, False), ("ai/claude/M004-x;touch", True, False),
             ("ai/claude/M004-x y", True, False), ("xai/claude/M004-x", False, False), ("ai/claude/M004-x/y", False, False), ("ai/claude/M04-short", False, False),
             ("ai/claude/M00045-x", False, False), ("ai/claude/NO-MERGE-operator-requests", False, False), ("ai/claude/R-001-x", False, False), ("ai/codex/M004-x", False, False),
             ("main", False, False)]

    def test_the_filter_and_the_module_pattern_pick_the_same_branches_and_the_pattern_is_never_wider(self):
        filters = [re.compile(glob_to_regex(pattern)) for pattern in READY_FILTERS]
        for name, by_filter, by_pattern in self.CASES:
            with self.subTest(name[:40]):
                self.assertEqual(any(rx.fullmatch(name) for rx in filters), by_filter)
                self.assertEqual(an.BRANCH_RE.fullmatch(name) is not None, by_pattern)
                if by_pattern:
                    self.assertTrue(by_filter)

    def test_the_confirm_filter_is_main_only(self):
        self.assertEqual(SPECS["merge-confirm-notice.yml"]["branches"], ["main"])
        filters = [re.compile(glob_to_regex(pattern)) for pattern in ["main"]]
        for name, expected in (("main", True), ("main2", False), ("xmain", False), ("refs/heads/main", False), ("ai/claude/M004-x", False)):
            self.assertEqual(any(rx.fullmatch(name) for rx in filters), expected, name)


class MutationTest(unittest.TestCase):
    """같은 모양 검사를 일부러 틀리게 만든 사본에 돌려 모두 잡는지 본다(살아남는 변이가 있으면 그 검사가 허술한 것)."""

    def mutations(self, name):
        text = load_text(name)
        spec = SPECS[name]
        decide_run = spec["decide_run"]
        yield "pull_request_target 트리거 추가", text.replace("on:\n  workflow_run:", "on:\n  pull_request_target:\n  workflow_run:", 1)
        yield "schedule 트리거 추가", text.replace("on:\n  workflow_run:", "on:\n  schedule:\n    - cron: '0 * * * *'\n  workflow_run:", 1)
        yield "workflow_dispatch 트리거 추가", text.replace("on:\n  workflow_run:", "on:\n  workflow_dispatch:\n  workflow_run:", 1)
        yield "issue_comment 트리거 추가", text.replace("on:\n  workflow_run:", "on:\n  issue_comment:\n  workflow_run:", 1)
        yield "push 트리거 추가", text.replace("on:\n  workflow_run:", "on:\n  push:\n  workflow_run:", 1)
        yield "따라 도는 워크플로를 바꿈", re.sub(r'    workflows: \[".*"\]\n', '    workflows: ["[공통] 다른 워크플로"]\n', text, count=1)
        yield "가지 필터를 넓힘", re.sub(r"    branches:\n(?:      - .*\n)+", "    branches:\n      - '**'\n", text, count=1)
        yield "가지 필터 삭제", re.sub(r"    branches:\n(?:      - .*\n)+", "", text, count=1)
        yield "types 에 requested 추가", text.replace("types: [completed]", "types: [completed, requested]", 1)
        yield "contents 쓰기 권한", text.replace("  contents: read\n", "  contents: write\n", 1)
        yield "pull-requests 쓰기 권한", text.replace("  pull-requests: read\n", "  pull-requests: write\n", 1)
        yield "actions 쓰기 권한", text.replace("  actions: read\n", "  actions: write\n", 1)
        yield "issues 쓰기 권한 추가", text.replace("  actions: read\n", "  actions: read\n  issues: write\n", 1)
        yield "job 이 더 넓은 권한을 달라고 함", text.replace("    timeout-minutes: 10\n", "    timeout-minutes: 10\n    permissions:\n      contents: write\n", 1)
        yield "동시 실행 취소 켬", text.replace("cancel-in-progress: false", "cancel-in-progress: true", 1)
        yield "동시 실행 그룹을 가지로", text.replace("head_sha }}\n  cancel", "head_branch }}\n  cancel", 1)
        yield "시간 제한 삭제", text.replace("    timeout-minutes: 10\n", "", 1)
        yield "체크아웃 ref 삭제", text.replace("          ref: ${{ github.event.repository.default_branch }}\n", "", 1)
        yield "체크아웃 ref 를 실행의 커밋으로", text.replace("ref: ${{ github.event.repository.default_branch }}", "ref: ${{ github.event.workflow_run.head_sha }}", 1)
        yield "체크아웃 ref 를 실행의 가지로", text.replace("ref: ${{ github.event.repository.default_branch }}", "ref: ${{ github.event.workflow_run.head_branch }}", 1)
        yield "체크아웃 persist-credentials 켬", text.replace("          persist-credentials: false\n", "          persist-credentials: true\n", 1)
        yield "체크아웃에 다른 저장소", text.replace("          persist-credentials: false\n", "          persist-credentials: false\n          repository: evil/x\n", 1)
        yield "외부 액션 추가", text.replace("    steps:\n", "    steps:\n      - uses: actions/github-script@v7\n", 1)
        yield "체크아웃 버전 바꿈", text.replace("actions/checkout@v6", "actions/checkout@v4", 1)
        yield "시크릿을 판정 단계에", text.replace("          GITHUB_TOKEN: ${{ github.token }}\n", "          GITHUB_TOKEN: ${{ github.token }}\n          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}\n", 1)
        yield "시크릿 사용(GITHUB_TOKEN 을 시크릿으로)", text.replace("GITHUB_TOKEN: ${{ github.token }}", "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}", 1)
        yield "발송 단계의 if 삭제", text.replace("        if: steps.decide.outputs.send == 'yes'\n", "", 1)
        yield "발송 단계의 if 를 항상 참으로", text.replace("if: steps.decide.outputs.send == 'yes'", "if: always()", 1)
        yield "발송 단계에 continue-on-error", text.replace("        if: steps.decide.outputs.send == 'yes'\n", "        if: steps.decide.outputs.send == 'yes'\n        continue-on-error: true\n", 1)
        yield "run 안에 이벤트 값 보간", text.replace(decide_run, 'echo "${{ github.event.workflow_run.head_branch }}"', 1)
        yield "run 안에 커밋 메시지 보간", text.replace(decide_run, 'echo "${{ github.event.workflow_run.head_commit.message }}"', 1)
        yield "run 안에 env 를 거친 식", text.replace(decide_run, 'echo "${{ env.NOTICE_RUN_BRANCH }}"', 1)
        yield "env 에 커밋 메시지 추가", text.replace("          NOTICE_RUN_ID:", "          NOTICE_MSG: ${{ github.event.workflow_run.head_commit.message }}\n          NOTICE_RUN_ID:", 1)
        yield "env 에서 저장소 값 삭제", text.replace("          NOTICE_RUN_REPO: ${{ github.event.workflow_run.head_repository.full_name }}\n", "", 1)
        yield "env 에서 이벤트 값 삭제", text.replace("          NOTICE_RUN_EVENT: ${{ github.event.workflow_run.event }}\n", "", 1)
        yield "실행 명령을 다른 모듈로", text.replace(decide_run, "python -m pipeline.notify test", 1)
        yield "실행 명령에 명령 덧붙임", text.replace(decide_run, decide_run + " && echo done", 1)
        yield "발송 명령 바꿈", text.replace("run: python -m pipeline.auto_notice send", "run: python -m pipeline.notify test", 1)
        yield "가지 코드 받기 단계", text.replace("      - name: " + SEND_NAME, "      - name: 가지 받기\n        run: git fetch origin pull/1/head\n\n      - name: " + SEND_NAME, 1)
        yield "gh 로 병합 호출", text.rstrip("\n") + "\n\n      - name: 병합\n        run: gh pr merge 1 --squash\n"
        yield "단계 하나 더", text.rstrip("\n") + "\n\n      - name: 뒤 단계\n        run: echo done\n"
        yield "단계 id 삭제", text.replace("        id: decide\n", "", 1)
        yield "run-name 추가", text.replace("\non:\n", '\nrun-name: "[공통] ${{ github.event.workflow_run.head_commit.message }}"\non:\n', 1)
        yield "job 이름 삭제", text.replace("    name: " + spec["job_name"] + "\n", "", 1)
        yield "runs-on 을 self-hosted 로", text.replace("runs-on: ubuntu-latest", "runs-on: self-hosted", 1)
        yield "env 를 job 수준에도", text.replace("    timeout-minutes: 10\n", "    timeout-minutes: 10\n    env:\n      X: y\n", 1)

    def test_every_mutation_is_caught(self):
        count = 0
        for name in SPECS:
            original = load_text(name)
            spec = with_file(name)
            self.assertEqual(static_problems(original, spec), [])
            for label, mutated in self.mutations(name):
                count += 1
                with self.subTest(f"{name}: {label}"):
                    self.assertNotEqual(mutated, original, f"변이가 글을 바꾸지 못했다: {label}")
                    self.assertTrue(static_problems(mutated, spec), f"살아남은 변이: {label}")
        self.assertGreaterEqual(count, 2 * 45)

    def test_the_validator_rule_catches_the_security_relevant_mutations_without_this_test_file(self):
        """같은 변이 중 시크릿·권한·체크아웃·run 식에 닿는 것은 검증기 WF-16 만으로도 잡힌다(시험이 없어도 CI 의 검증기가 마지막 안전망이다)."""
        security = ("contents 쓰기 권한", "pull-requests 쓰기 권한", "actions 쓰기 권한", "issues 쓰기 권한 추가", "job 이 더 넓은 권한을 달라고 함", "체크아웃 ref 삭제", "체크아웃 ref 를 실행의 커밋으로",
                    "체크아웃 ref 를 실행의 가지로", "체크아웃 persist-credentials 켬", "체크아웃에 다른 저장소", "외부 액션 추가", "시크릿을 판정 단계에", "시크릿 사용(GITHUB_TOKEN 을 시크릿으로)",
                    "run 안에 이벤트 값 보간", "run 안에 커밋 메시지 보간", "run 안에 env 를 거친 식", "가지 코드 받기 단계", "단계 하나 더", "pull_request_target 트리거 추가", "schedule 트리거 추가",
                    "workflow_dispatch 트리거 추가", "issue_comment 트리거 추가", "push 트리거 추가", "가지 필터를 넓힘", "가지 필터 삭제", "따라 도는 워크플로를 바꿈", "실행 명령을 다른 모듈로",
                    "실행 명령에 명령 덧붙임", "발송 명령 바꿈", "env 를 job 수준에도")
        import tempfile
        for name in SPECS:
            for label, mutated in self.mutations(name):
                if label not in security:
                    continue
                with self.subTest(f"{name}: {label}"):
                    with tempfile.TemporaryDirectory() as tmp:
                        rel = f".github/workflows/{name}"
                        path = Path(tmp) / rel
                        path.parent.mkdir(parents=True)
                        path.write_text(mutated, encoding="utf-8", newline="\n")
                        findings = vr.check_workflow_run_workflows(Path(tmp), [rel]) + vr.check_workflows(Path(tmp), [rel]) + vr.check_telegram_secrets(Path(tmp), [rel])
                        self.assertTrue([f for f in findings if f.level == "ERROR"], f"검증기가 놓친 변이: {label}")


class StateFileTest(unittest.TestCase):
    def test_the_repository_state_is_off_so_both_workflows_end_at_once_after_merging(self):
        import json
        self.assertEqual(json.loads((ROOT / "pipeline" / "auto_notice.json").read_text(encoding="utf-8")), {"mode": "off"})
        self.assertEqual(an.read_mode(), "off")

    def test_no_workflow_or_script_other_than_the_module_reads_the_state_file(self):
        readers = []
        for base in ("pipeline", "scripts", ".github"):
            for path in sorted((ROOT / base).rglob("*")):
                if path.is_file() and path.suffix in (".py", ".yml", ".yaml", ".sh"):
                    text = path.read_text(encoding="utf-8", errors="replace")
                    if path.suffix != ".py":
                        text = code_text(text)                                                       # 워크플로의 설명 주석은 읽는 것이 아니다
                    if "auto_notice.json" in text:
                        readers.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(readers, ["pipeline/auto_notice.py"])


if __name__ == "__main__":
    unittest.main()
