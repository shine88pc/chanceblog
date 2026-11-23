"""병합 알림 자동화 워크플로 둘(`merge-ready-notice.yml`·`merge-confirm-notice.yml`)의 모양 시험 — 운영자 확인 031 의 보기 2(2026-11-23). 2차: 판정 job·발송 job 둘로 나눔(안전 검증 S 의 AN1-S-4).

`workflow_run` 은 시크릿을 쥔 채 기본 가지의 파일로 도는 위험한 트리거라, 이 시험이 두 파일을 한 줄씩 고정한다(`tests/test_auto_pr_workflow.py` 와 같은 방식):
 1. 모양(YAML 을 읽어서) — 트리거는 `workflow_run` 하나(따라 도는 워크플로·가지 필터가 정해진 값), 권한은 읽기 셋뿐, job 은 정확히 둘: `decide`(시크릿 없음 — 체크아웃·setup-python·판정 단계, 출력 `send`·`message`)와
    `send`(`needs: decide`, `if: needs.decide.outputs.send == 'yes'`, 시크릿은 여기 마지막 단계 env 에만). 체크아웃은 두 job 모두 기본 가지 `ref`·`persist-credentials: false`, 외부 액션은 둘뿐,
    `${{ }}` 는 정해진 자리의 정해진 식뿐이고 `run:` 에는 하나도 없다. 같은 검사를 일부러 틀리게 만든 사본에 돌려 시험이 정말 잡는지도 본다(살아남는 변이가 없어야 한다 — 검증기 시험의 변이 목록을 그대로 쓴다).
 2. 두 파일이 같은 뼈대인지, 따라 도는 워크플로 이름·가지 필터가 실제 워크플로와 같은지, 동시 실행 그룹이 다른 워크플로와 겹치지 않는지, env·출력 이름이 파이썬 모듈이 읽고 쓰는 이름과 같은지.
 3. 켬 상태 파일이 `off` 로 병합되는지, 문서가 같은 말을 하는지(문서는 tests/test_merge_notice_docs.py).
"""
import copy
import re
import sys
import unittest
from pathlib import Path

import yaml

import _bootstrap
from pipeline import auto_notice as an
from test_auto_pr_workflow import glob_to_regex
from test_workflow_run_rule import catalog as rule_catalog, dump, step_of

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

WORKFLOWS = ROOT / ".github" / "workflows"
PERMISSIONS = {"contents": "read", "pull-requests": "read", "actions": "read"}
TELEGRAM_ENV = {"TELEGRAM_BOT_TOKEN": "${{ secrets.TELEGRAM_BOT_TOKEN }}", "TELEGRAM_CHAT_ID": "${{ secrets.TELEGRAM_CHAT_ID }}"}
SEND_ENV = {"NOTICE_MESSAGE_B64": "${{ needs.decide.outputs.message }}", **TELEGRAM_ENV}
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
DECIDE_OUTPUTS = {"send": "${{ steps.decide.outputs.send }}", "message": "${{ steps.decide.outputs.message }}"}
CHECKOUT = {"uses": "actions/checkout@v6", "with": {"ref": "${{ github.event.repository.default_branch }}", "persist-credentials": False}}
SETUP = {"uses": "actions/setup-python@v6", "with": {"python-version": "3.12"}}
SEND_NAME = "텔레그램으로 보내기(켬 상태가 on 일 때만)"
SEND_IF = "needs.decide.outputs.send == 'yes'"
SEND_RUN = "python -m pipeline.auto_notice send"
READY_FILTERS = ["ai/claude/M[0-9][0-9][0-9]-*", "ai/claude/M[0-9][0-9][0-9][0-9]-*"]

SPECS = {
    "merge-ready-notice.yml": {
        "name": "[공통] 병합 부탁 알림 자동 보내기", "target": "[공통] 병합 부탁 PR 자동 만들기", "branches": READY_FILTERS,
        "group": "merge-ready-notice-${{ github.event.workflow_run.head_sha }}", "decide_job_name": "병합 부탁 알림 판정(시크릿 없음)", "send_job_name": "병합 부탁 알림 발송(시크릿은 이 job 에만)",
        "decide_name": "병합 부탁 문장 만들기(켬 상태가 꺼짐이면 곧바로 끝)", "decide_run": "python -m pipeline.auto_notice merge-ready"},
    "merge-confirm-notice.yml": {
        "name": "[공통] 병합완료 확인 알림 자동 보내기", "target": "[공통] 저장소 규칙·테스트 자동 검사", "branches": ["main"],
        "group": "merge-confirm-notice-${{ github.event.workflow_run.head_sha }}", "decide_job_name": "병합완료 확인 판정(시크릿 없음)", "send_job_name": "병합완료 확인 알림 발송(시크릿은 이 job 에만)",
        "decide_name": "병합완료 확인 문장 만들기(켬 상태가 꺼짐이면 곧바로 끝)", "decide_run": "python -m pipeline.auto_notice merge-confirm"},
}
# 코드 줄(주석 뺀 글)에 있으면 안 되는 것: (이유, 정규식)
FORBIDDEN = [
    ("다른 트리거", re.compile(r"\b(?:pull_request_target|pull_request|issue_comment|schedule|workflow_dispatch|workflow_call|repository_dispatch)\b|^\s*push:|^\s*issues:|^\s*create:|^\s*release:", re.M)),
    ("병합·승인·라벨·코멘트 호출", re.compile(r"--admin|auto_merge|enable_auto|/reviews|event=APPROVE|--approve|\bgh\s|\bgit\s|gh api|pulls/", re.I)),
    ("셸이 글을 해석하는 길", re.compile(r"\beval\b|\bbash\s+-c\b|\bsh\s+-c\b|\bsource\b|`|\bcurl\b|\bwget\b")),
    ("환경·출력 파일 쓰기(출력은 파이썬이 고정 두 줄만 쓴다)", re.compile(r"GITHUB_ENV|GITHUB_OUTPUT|GITHUB_PATH|set-output|add-mask|GITHUB_STEP_SUMMARY")),
    ("실패 은폐·셸 약화", re.compile(r"continue-on-error|\bset\s+\+[a-zA-Z]|\|\|\s*true\b|\btrap\b|\bshell:|working-directory")),
    ("가지 코드 체크아웃", re.compile(r"ref:\s*\$\{\{\s*github\.(?:head_ref|ref|event\.pull_request|event\.workflow_run)|ref:\s*refs/", re.M)),
    ("외부 액션 추가", re.compile(r"uses:\s*(?!actions/checkout@v6\s*$|actions/setup-python@v6\s*$)\S+", re.M)),
]
# 이 파일 둘의 `${{ }}` 식 전부(정확히 열여섯 — 동시 실행 그룹 하나·판정 job 의 출력 둘·체크아웃 ref 둘·판정 단계 env 여덟·발송 단계 env 셋)
WANTED_EXPRESSIONS = sorted(["${{ github.event.workflow_run.head_sha }}", "${{ steps.decide.outputs.send }}", "${{ steps.decide.outputs.message }}",
                             "${{ github.event.repository.default_branch }}", "${{ github.token }}", "${{ github.event.workflow_run.id }}", "${{ github.event.workflow_run.head_branch }}",
                             "${{ github.event.workflow_run.head_sha }}", "${{ github.event.workflow_run.event }}", "${{ github.event.workflow_run.conclusion }}",
                             "${{ github.event.workflow_run.head_repository.full_name }}", "${{ github.event.repository.default_branch }}", "${{ github.event.repository.default_branch }}",
                             "${{ needs.decide.outputs.message }}", "${{ secrets.TELEGRAM_BOT_TOKEN }}", "${{ secrets.TELEGRAM_CHAT_ID }}"])


def load_text(name):
    return (WORKFLOWS / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def load_data(name):
    return yaml.safe_load(load_text(name))


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
    if list(jobs) != ["decide", "send"]:
        return problems + [f"job 이 decide·send 둘이 아님: {list(jobs)}"]
    decide, send = jobs["decide"], jobs["send"]
    if set(decide) != {"name", "runs-on", "timeout-minutes", "outputs", "steps"} or decide.get("name") != spec["decide_job_name"]:
        problems.append(f"판정 job 의 키·이름이 정해진 것과 다름: {sorted(decide)}")
    if set(send) != {"name", "needs", "if", "runs-on", "timeout-minutes", "steps"} or send.get("name") != spec["send_job_name"]:
        problems.append(f"발송 job 의 키·이름이 정해진 것과 다름: {sorted(send)}")
    for label, job in (("판정", decide), ("발송", send)):
        if job.get("runs-on") != "ubuntu-latest" or job.get("timeout-minutes") != 10:
            problems.append(f"{label} job 의 runs-on·timeout-minutes 가 다름")
    if decide.get("outputs") != DECIDE_OUTPUTS:
        problems.append(f"판정 job 의 출력이 정해진 둘이 아님: {decide.get('outputs')}")
    if send.get("needs") != "decide" or send.get("if") != SEND_IF:
        problems.append(f"발송 job 의 needs·if 가 정해진 것과 다름: {send.get('needs')!r} {send.get('if')!r}")
    expected = {"decide": [CHECKOUT, SETUP, {"name": spec["decide_name"], "id": "decide", "env": DECIDE_ENV, "run": spec["decide_run"]}],
                "send": [CHECKOUT, SETUP, {"name": SEND_NAME, "env": SEND_ENV, "run": SEND_RUN}]}
    for label, job_id in (("판정", "decide"), ("발송", "send")):
        steps = jobs[job_id].get("steps") or []
        if len(steps) != 3:
            problems.append(f"{label} job 의 단계가 셋이 아님: {len(steps)}")
            continue
        for index, (step, want) in enumerate(zip(steps, expected[job_id]), 1):
            if step != want:
                problems.append(f"{label} job 의 {index}번째 단계가 정해진 것과 다름: {step}")
            run = step.get("run")
            if isinstance(run, str) and "${{" in run:
                problems.append(f"{label} job 의 {index}번째 단계의 run 안에 ${{{{ }}}} 가 있음")
    code = code_text(text)
    for reason, rx in FORBIDDEN:
        found = rx.search(code)
        if found:
            problems.append(f"{reason}: {found.group(0)!r}")
    if expressions(text) != WANTED_EXPRESSIONS:
        problems.append(f"`${{{{ }}}}` 식의 목록이 정해진 것과 다름: {expressions(text)}")
    if len(re.findall(r"secrets\s*[.\[]", code)) != 2:
        problems.append("시크릿 참조가 정확히 둘(발송 job 의 발송 단계 env)이 아님")
    if "secrets" in str(decide):
        problems.append("판정 job 에 시크릿이 있음")
    problems += vr._workflow_run_problems(data, vr.WORKFLOW_RUN_ALLOWED[f".github/workflows/{spec['file']}"]) if "file" in spec else []
    return problems


def with_file(name):
    return dict(SPECS[name], file=name)


class WorkflowShapeTest(unittest.TestCase):
    def test_the_real_files_have_no_static_problem(self):
        for name in SPECS:
            with self.subTest(name):
                self.assertEqual(static_problems(load_text(name), with_file(name)), [])

    def test_each_file_has_exactly_the_two_jobs_with_three_steps_each_in_order(self):
        for name, spec in SPECS.items():
            with self.subTest(name):
                jobs = load_data(name)["jobs"]
                self.assertEqual(list(jobs), ["decide", "send"])
                for job_id in jobs:
                    self.assertEqual(len(jobs[job_id]["steps"]), 3)
                    self.assertEqual([step.get("uses") for step in jobs[job_id]["steps"][:2]], ["actions/checkout@v6", "actions/setup-python@v6"])
                    self.assertEqual([step.get("uses") for step in jobs[job_id]["steps"][2:]], [None])
                    self.assertNotIn("env", jobs[job_id]["steps"][0])
                    self.assertNotIn("env", jobs[job_id]["steps"][1])
                decide_step, send_step = jobs["decide"]["steps"][2], jobs["send"]["steps"][2]
                self.assertEqual((decide_step["id"], sorted(decide_step["env"])), ("decide", sorted(DECIDE_ENV)))
                self.assertEqual(send_step["env"], SEND_ENV)
                self.assertNotIn("id", send_step)
                self.assertEqual(send_step["name"], SEND_NAME)

    def test_the_secrets_are_only_in_the_send_job_last_step_and_the_decide_job_has_none(self):
        for name in SPECS:
            with self.subTest(name):
                jobs = load_data(name)["jobs"]
                self.assertNotIn("secrets", str(jobs["decide"]))                                       # 판정 job 에는 시크릿이 하나도 없다(env 이름·값 어디에도)
                self.assertNotIn("TELEGRAM", str(jobs["decide"]))
                self.assertEqual([index for index, step in enumerate(jobs["send"]["steps"]) if "secrets" in str(step)], [2])        # 발송 job 에서도 맨 끝 단계에만
                self.assertEqual(sorted(key for key in jobs["send"]["steps"][2]["env"] if "secrets." in jobs["send"]["steps"][2]["env"][key]), sorted(TELEGRAM_ENV))
                self.assertEqual(jobs["decide"]["steps"][2]["env"]["GITHUB_TOKEN"], "${{ github.token }}")                    # 판정 job 의 토큰은 읽기 권한의 job 토큰이지 시크릿이 아니다

    def test_the_send_job_starts_only_when_the_decide_job_says_yes_so_off_and_dry_never_start_it(self):
        """off·dry 에서는 판정 단계가 출력을 하나도 쓰지 않는다(파이썬 시험이 고정) → send 가 비어 있어 발송 job 은 시작도 하지 않는다."""
        for name in SPECS:
            with self.subTest(name):
                jobs = load_data(name)["jobs"]
                self.assertEqual(jobs["send"]["needs"], "decide")
                self.assertEqual(jobs["send"]["if"], SEND_IF)
                self.assertNotIn("${{", jobs["send"]["if"])                                           # job 의 if 는 식 괄호 없이 컨텍스트만 본다
                self.assertEqual(jobs["decide"]["outputs"], DECIDE_OUTPUTS)
                self.assertEqual(set(DECIDE_OUTPUTS), {an.OUTPUT_KEY, an.MESSAGE_KEY})                  # 파이썬이 쓰는 출력 이름과 같다
                self.assertEqual(an.OUTPUT_YES, "yes")
                self.assertTrue(SEND_IF.endswith(f"== '{an.OUTPUT_YES}'"))
                self.assertIn(an.MESSAGE_ENV, SEND_ENV)                                              # 발송 단계가 받는 env 이름도 파이썬 모듈의 상수와 같다

    def test_names_follow_the_repository_rules(self):
        for name, spec in SPECS.items():
            with self.subTest(name):
                data = load_data(name)
                self.assertEqual(data["name"], spec["name"])
                self.assertTrue(data["name"].startswith("[공통] "))
                for job_id in ("decide", "send"):
                    self.assertRegex(data["jobs"][job_id]["name"], r"[가-힣]")
                    self.assertFalse(re.match(r"\[", data["jobs"][job_id]["name"]))
                    for step in data["jobs"][job_id]["steps"][2:]:
                        self.assertRegex(step["name"], r"[가-힣]")
                self.assertNotIn("run-name", data)                                                  # 실행 목록에 가지·커밋 글이 제목으로 보이지 않게
                files = [f".github/workflows/{name}"]
                findings = vr.check_workflows(ROOT, files) + vr.check_workflow_names(ROOT, files) + vr.check_workflow_prefixes(ROOT, files) + vr.check_telegram_secrets(ROOT, files)
                self.assertEqual([finding.line() for finding in findings], [])                      # 경고도 없다(WF-1 에서 WF-13)

    def test_the_trigger_is_exactly_one_workflow_run_with_the_target_and_filters(self):
        for name, spec in SPECS.items():
            with self.subTest(name):
                data = load_data(name)
                self.assertEqual(vr._triggers(data), {"workflow_run": {"workflows": [spec["target"]], "types": ["completed"], "branches": spec["branches"]}})
                head = load_text(name).split("\npermissions:")[0]
                on_block = [line for line in head.split("\non:\n")[1].splitlines() if line.strip() and not line.strip().startswith("#")]
                self.assertEqual(on_block[:4], ["  workflow_run:", f'    workflows: ["{spec["target"]}"]', "    types: [completed]", "    branches:"])

    def test_the_target_names_are_the_real_names_of_the_workflows_they_follow(self):
        self.assertEqual(SPECS["merge-ready-notice.yml"]["target"], load_data("auto-pr.yml")["name"])
        self.assertEqual(SPECS["merge-confirm-notice.yml"]["target"], load_data("guardrails.yml")["name"])

    def test_the_ready_branch_filters_are_the_push_filters_of_the_auto_pr_workflow(self):
        """병합 부탁 알림은 자동 PR 워크플로가 도는 가지에서만 깨어난다 — 필터 두 줄이 auto-pr.yml 의 push 필터와 글자까지 같다."""
        auto = load_data("auto-pr.yml")
        self.assertEqual(vr._triggers(auto)["push"]["branches"], READY_FILTERS)

    def test_the_confirm_workflow_follows_the_check_that_runs_on_main_pushes(self):
        guardrails = load_data("guardrails.yml")
        self.assertIn("push", vr._triggers(guardrails))                                             # main 병합 직후의 검사는 push 로 돈다(G-A11)

    def test_permissions_are_the_three_reads_and_no_job_asks_for_more(self):
        for name in SPECS:
            with self.subTest(name):
                data = load_data(name)
                self.assertEqual(data["permissions"], PERMISSIONS)
                for job_id in ("decide", "send"):
                    self.assertNotIn("permissions", data["jobs"][job_id])
                for value in data["permissions"].values():
                    self.assertEqual(value, "read")
                text = code_text(load_text(name))
                self.assertNotRegex(text, r"write|admin")

    def test_every_dollar_brace_expression_is_in_a_with_env_outputs_or_concurrency_value_never_in_a_run(self):
        for name in SPECS:
            with self.subTest(name):
                data = load_data(name)
                for job in data["jobs"].values():
                    self.assertNotIn("${{", str(job.get("if", "")))
                    for step in job["steps"]:
                        self.assertNotIn("${{", step.get("run", ""))
                        self.assertNotIn("${{", str(step.get("if", "")))
                self.assertEqual(expressions(load_text(name)), WANTED_EXPRESSIONS)
                self.assertEqual(len(expressions(load_text(name))), 16)

    def test_the_decide_env_carries_the_trigger_values_only_as_env_and_the_names_match_what_the_module_reads(self):
        source = (ROOT / "pipeline" / "auto_notice.py").read_text(encoding="utf-8")
        for env_name in DECIDE_ENV:
            if env_name.startswith("NOTICE_"):
                self.assertEqual(len(re.findall(rf'"{env_name}"', source)), 1, env_name)           # 모듈이 그 이름을 읽는다(정확히 한 군데)
        self.assertIn('"GITHUB_TOKEN"', source)
        read_names = set(re.findall(r'get\("(NOTICE_[A-Z_]+)"\)', source))
        self.assertEqual(read_names, {name for name in DECIDE_ENV if name.startswith("NOTICE_")})
        self.assertEqual(an.MESSAGE_ENV, "NOTICE_MESSAGE_B64")                                       # 발송 단계가 읽는 이름(판정 단계 이름 목록과 따로)
        self.assertEqual(source.count('"NOTICE_MESSAGE_B64"'), 1)

    def test_the_python_commands_exist_in_the_module_and_are_the_only_things_run(self):
        parser = an.build_parser()
        for name, spec in SPECS.items():
            command = spec["decide_run"].rsplit(" ", 1)[1]
            self.assertEqual(parser.parse_args([command]).command, command)
        self.assertEqual(parser.parse_args(["send"]).command, "send")

    def test_the_external_actions_are_exactly_the_ones_the_other_workflows_already_use(self):
        """새 액션을 들이지 않는다 — 두 파일의 두 job 의 `uses:` 는 정확히 `actions/checkout@v6`·`actions/setup-python@v6` 이고 둘 다 이 저장소의 다른 워크플로가 이미 같은 글자로 쓴다."""
        used_elsewhere = set()
        for path in sorted(WORKFLOWS.glob("*.yml")):
            if path.name in SPECS:
                continue
            for job in (yaml.safe_load(path.read_text(encoding="utf-8")).get("jobs") or {}).values():
                for step in job.get("steps") or []:
                    if isinstance(step, dict) and "uses" in step:
                        used_elsewhere.add(step["uses"])
        for name in SPECS:
            for job_id, job in load_data(name)["jobs"].items():
                mine = {step["uses"] for step in job["steps"] if "uses" in step}
                self.assertEqual(mine, {"actions/checkout@v6", "actions/setup-python@v6"}, (name, job_id))
                self.assertLessEqual(mine, used_elsewhere, (name, job_id))

    def test_the_two_files_are_the_same_skeleton(self):
        """두 파일의 차이는 이름·따라 도는 워크플로·가지 필터·동시 실행 그룹·job 이름 둘·판정 단계의 이름과 명령뿐이다(뼈대가 갈라지면 한쪽만 약해진다)."""
        ready, confirm = (load_data(name) for name in SPECS)
        for data in (ready, confirm):
            data["name"], data["concurrency"] = "N", "C"
            data["jobs"]["decide"]["name"], data["jobs"]["send"]["name"] = "J1", "J2"
            on = vr._triggers(data)["workflow_run"]
            on["workflows"], on["branches"] = ["W"], ["B"]
            decide = data["jobs"]["decide"]["steps"][2]
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
            self.assertIs(load_data(name)["concurrency"]["cancel-in-progress"], False)            # 진행 중인 알림을 취소하지 않는다

    def test_the_header_comment_states_the_rules_and_the_limits(self):
        needles = ["병합하지 않는다", "G-A13", "G-A14", "workflow_run", "pull_request_target", "issue_comment", "schedule", "workflow_dispatch", "가지(PR 머리)의 코드는 내려받지도 실행하지도 않는다",
                   "persist-credentials: false", "WF-16", "env 로만", "쓰기 0", "off", "dry", "on", "pipeline/auto_notice.json", "T3", "첫 관측", "한계", "Re-run", "AI 의 요청 파일 알림이 병행한다",
                   "actions/checkout", "actions/setup-python", "새 의존성이 없다", "데스크톱 앱 저장소에는 텔레그램 시크릿이 없어", "기본 가지",
                   "job 둘", "판정 job", "발송 job", "needs: decide", "시작도 하지 않아", "러너가 다르다", "base64", "시크릿은 여기에만", "발송 job 의 마지막 단계 env 로만", "판정 job 에는 시크릿이 하나도 없다"]
        for name in SPECS:
            header = load_text(name).split("\non:\n")[0]
            for needle in needles:
                self.assertIn(needle, header, f"{name}: {needle}")
            self.assertNotIn(chr(0x7E), header)
            self.assertNotRegex(header, r"https?://")

    def test_the_confirm_header_documents_its_extra_limits(self):
        header = load_text("merge-confirm-notice.yml").split("\non:\n")[0]
        for needle in ("취소되거나 건너뛰어졌으면", "판정을 미루고", "300개", "2MB", "트리 일치", "트리 비교를 빼고", "변경 파일 수·이름 집합", "부모 수", "정확히 하나일 때뿐", "봇이 글을 올릴 때마다",
                       "blob 해시", "내용 비교 생략"):
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


def own_mutations(name):
    """검증기가 고정하지 않지만 이 시험이 고정하는 것(동시 실행·시간 제한·run-name·이름·판정 단계 env 의 이름 집합·단계 이름 …)을 한 군데씩 망가뜨린다. (이름, 사본을 고치는 함수)."""
    out = []

    def add(label, fn):
        out.append((label, fn))

    add("동시 실행 취소 켬", lambda d: d["concurrency"].__setitem__("cancel-in-progress", True))
    add("동시 실행 그룹을 가지로", lambda d: d["concurrency"].__setitem__("group", d["concurrency"]["group"].replace("head_sha", "head_branch")))
    add("동시 실행 삭제", lambda d: d.pop("concurrency"))
    add("run-name 추가", lambda d: d.__setitem__("run-name", "[공통] ${{ github.event.workflow_run.head_commit.message }}"))
    add("워크플로 이름 바꿈", lambda d: d.__setitem__("name", "[공통] 다른 이름"))
    add("최상위에 키 하나 더", lambda d: d.__setitem__("x", "y"))
    for job in ("decide", "send"):
        add(f"{job}: 시간 제한 삭제", lambda d, job=job: d["jobs"][job].pop("timeout-minutes"))
        add(f"{job}: 시간 제한을 늘림", lambda d, job=job: d["jobs"][job].__setitem__("timeout-minutes", 360))
        add(f"{job}: job 이름 삭제", lambda d, job=job: d["jobs"][job].pop("name"))
        add(f"{job}: 체크아웃 버전 바꿈", lambda d, job=job: step_of(d, job, 0).__setitem__("uses", "actions/checkout@v4"))
        add(f"{job}: setup-python 버전 바꿈", lambda d, job=job: step_of(d, job, 1).__setitem__("uses", "actions/setup-python@v4"))
        add(f"{job}: python 버전 바꿈", lambda d, job=job: step_of(d, job, 1)["with"].__setitem__("python-version", "3.8"))
        add(f"{job}: run 단계 이름 삭제", lambda d, job=job: step_of(d, job, 2).pop("name"))
        add(f"{job}: run 단계에 if 추가", lambda d, job=job: step_of(d, job, 2).__setitem__("if", "always()"))
        add(f"{job}: 병합 호출 단계 추가", lambda d, job=job: d["jobs"][job]["steps"].append({"name": "병합", "run": "gh pr merge 1 --squash"}))
    add("decide: env 에 값 추가", lambda d: step_of(d, "decide", 2)["env"].__setitem__("NOTICE_EXTRA", "${{ github.run_id }}"))
    add("decide: env 에서 저장소 값 삭제", lambda d: step_of(d, "decide", 2)["env"].pop("NOTICE_RUN_REPO"))
    add("decide: env 에서 이벤트 값 삭제", lambda d: step_of(d, "decide", 2)["env"].pop("NOTICE_RUN_EVENT"))
    add("decide: env 에 커밋 메시지 추가", lambda d: step_of(d, "decide", 2)["env"].__setitem__("NOTICE_MSG", "${{ github.event.workflow_run.head_commit.message }}"))
    add("decide: GITHUB_TOKEN 을 시크릿으로", lambda d: step_of(d, "decide", 2)["env"].__setitem__("GITHUB_TOKEN", "${{ secrets.GITHUB_TOKEN }}"))
    add("decide: env 값을 다른 이벤트 값으로", lambda d: step_of(d, "decide", 2)["env"].__setitem__("NOTICE_RUN_BRANCH", "${{ github.event.workflow_run.head_commit.message }}"))
    add("decide: 판정 단계 이름 바꿈", lambda d: step_of(d, "decide", 2).__setitem__("name", "다른 이름"))
    add("send: 발송 단계 이름 바꿈", lambda d: step_of(d, "send", 2).__setitem__("name", "다른 이름"))
    add("send: 발송 단계에 id", lambda d: step_of(d, "send", 2).__setitem__("id", "send"))
    add("send: 발송 단계 env 값을 시크릿 아닌 것으로", lambda d: step_of(d, "send", 2)["env"].__setitem__("TELEGRAM_CHAT_ID", "12345"))
    return out


class MutationTest(unittest.TestCase):
    """같은 모양 검사를 일부러 틀리게 만든 사본에 돌려 모두 잡는지 본다(살아남는 변이가 있으면 그 검사가 허술한 것). 검증기 시험의 변이 목록(job 마다·시크릿 자리·needs·if·outputs …)을 그대로 쓰고
    검증기가 고정하지 않는 것(동시 실행·시간 제한·run-name·이름·판정 단계 env)은 이 모듈의 변이로 더한다."""

    def test_every_mutation_is_caught(self):
        count = 0
        for name in SPECS:
            original = load_data(name)
            spec = with_file(name)
            self.assertEqual(static_problems(load_text(name), spec), [])
            self.assertEqual(static_problems(dump(original), spec), [])                           # 다시 쓴 사본도 통과(모든 변이의 기준)
            for label, fn, _needle in rule_catalog(f".github/workflows/{name}"):
                mutated = copy.deepcopy(original)
                fn(mutated)
                count += 1
                with self.subTest(f"{name}: {label}"):
                    self.assertNotEqual(mutated, original, f"변이가 글을 바꾸지 못했다: {label}")
                    self.assertTrue(static_problems(dump(mutated), spec), f"살아남은 변이: {label}")
            for label, fn in own_mutations(name):
                mutated = copy.deepcopy(original)
                fn(mutated)
                count += 1
                with self.subTest(f"{name}: {label}"):
                    self.assertNotEqual(mutated, original, f"변이가 글을 바꾸지 못했다: {label}")
                    self.assertTrue(static_problems(dump(mutated), spec), f"살아남은 변이: {label}")
        self.assertGreaterEqual(count, 2 * 230)

    def test_the_validator_alone_catches_every_security_relevant_mutation_the_shared_catalog_has(self):
        """공유 변이 목록은 검증기 WF-16 이 만든 것이다 — 시험이 없어도 CI 의 검증기가 마지막 안전망이라는 것을, 같은 변이를 검증기 입구(check_workflows)로 흘려 확인한다."""
        import tempfile
        for name in SPECS:
            rel = f".github/workflows/{name}"
            original = load_data(name)
            for label, fn, _needle in rule_catalog(rel):
                mutated = copy.deepcopy(original)
                fn(mutated)
                with self.subTest(f"{name}: {label}"):
                    with tempfile.TemporaryDirectory() as tmp:
                        path = Path(tmp) / rel
                        path.parent.mkdir(parents=True)
                        path.write_text(dump(mutated), encoding="utf-8", newline="\n")
                        findings = vr.check_workflows(Path(tmp), [rel]) + vr.check_telegram_secrets(Path(tmp), [rel])
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
