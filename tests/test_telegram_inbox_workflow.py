"""텔레그램 수신 워크플로(telegram-inbox.yml)의 구조와 검증기 규칙 WF-15 시험.

실제 `.github/workflows/telegram-inbox.yml` 을 읽어 모양(트리거·cron 형식·권한·단계·env·동시 실행)을 고정하고, 검증기 규칙은 실제 파일을 한 군데씩 망가뜨린 사본이
'잡히는지'로 확인한다(허용 모양은 통과하고 일부러 틀린 모양은 거절한다). GitHub 를 실행할 수 없는 환경에서도 구조로 증명한다.
"""
import copy
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
from test_workflow_names import context, load, render

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "telegram-inbox.yml"
REL = vr.TELEGRAM_INBOX_WORKFLOW
TELEGRAM_ENV = {"TELEGRAM_BOT_TOKEN": "${{ secrets.TELEGRAM_BOT_TOKEN }}", "TELEGRAM_CHAT_ID": "${{ secrets.TELEGRAM_CHAT_ID }}"}
INBOX_ENV = {"GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}", **TELEGRAM_ENV}


def real():
    return load("telegram-inbox.yml")


def steps(data):
    return data["jobs"]["fetch"]["steps"]


# ====================================================================================================================
# 1. 실제 파일의 모양
# ====================================================================================================================
class RealWorkflowTest(unittest.TestCase):
    def test_triggers_are_exactly_schedule_dispatch_and_ai_claude_push(self):
        self.assertEqual(real()["on"], {"schedule": [{"cron": "*/10 * * * *"}], "workflow_dispatch": None, "push": {"branches": ["ai/claude/**"]}})

    def test_cron_is_a_valid_five_field_expression_with_a_step_github_allows(self):
        cron = real()["on"]["schedule"][0]["cron"]
        fields = cron.split(" ")
        self.assertEqual(len(fields), 5)
        found = re.fullmatch(r"\*/([0-9]{1,2})", fields[0])
        self.assertIsNotNone(found, "분 칸은 `*/간격` 이어야 합니다")
        self.assertGreaterEqual(int(found.group(1)), 5, "GitHub 예약 실행의 최소 간격은 5분입니다")
        self.assertEqual(fields[1:], ["*", "*", "*", "*"])
        self.assertEqual(len(real()["on"]["schedule"]), 1)

    def test_no_dangerous_triggers(self):
        code = "\n".join(line for line in WORKFLOW.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#"))
        for name in ("pull_request_target", "pull_request:", "issue_comment", "workflow_run", "workflow_call", "repository_dispatch", "release:", "discussion", "pull_request_review"):
            self.assertNotIn(name, code, name)
        self.assertEqual(sorted(real()["on"]), ["push", "schedule", "workflow_dispatch"])          # `issues:` 는 권한 이름으로만 있고 트리거가 아니다

    def test_dispatch_takes_no_input(self):
        self.assertIsNone(real()["on"]["workflow_dispatch"])

    def test_push_trigger_is_the_branch_filter_only(self):
        self.assertEqual(real()["on"]["push"], {"branches": ["ai/claude/**"]})
        self.assertEqual((WORKFLOW.read_text(encoding="utf-8")).count("branches:"), 1)

    def test_permissions_are_minimal(self):
        self.assertEqual(real()["permissions"], {"contents": "read", "issues": "write"})
        self.assertNotIn("permissions", real()["jobs"]["fetch"])

    def test_one_job_with_a_short_timeout_on_ubuntu(self):
        data = real()
        self.assertEqual(list(data["jobs"]), ["fetch"])
        job = data["jobs"]["fetch"]
        self.assertEqual(job["runs-on"], "ubuntu-latest")
        self.assertLessEqual(job["timeout-minutes"], 5)
        self.assertEqual(sorted(job), ["name", "runs-on", "steps", "timeout-minutes"])
        self.assertRegex(job["name"], r"[가-힣]")

    def test_concurrency_is_one_group_that_never_cancels(self):
        data = real()
        self.assertEqual(data["concurrency"], {"group": "telegram-inbox", "cancel-in-progress": False})
        others = {load(path.name).get("concurrency", {}).get("group") if isinstance(load(path.name).get("concurrency"), dict) else None
                  for path in (ROOT / ".github" / "workflows").glob("*.yml") if path.name != "telegram-inbox.yml"}
        self.assertNotIn("telegram-inbox", others)

    def test_three_steps_checkout_python_and_one_run_line(self):
        checkout, python, run = steps(real())
        self.assertTrue(checkout["uses"].startswith("actions/checkout@"))
        self.assertEqual(checkout["with"], {"persist-credentials": False})
        self.assertTrue(python["uses"].startswith("actions/setup-python@"))
        self.assertEqual(python["with"], {"python-version": "3.12"})
        self.assertEqual(sorted(run), ["env", "name", "run"])
        self.assertEqual(run["run"], "python -m pipeline.telegram_inbox")
        self.assertRegex(run["name"], r"[가-힣]")
        for step in (checkout, python):
            self.assertNotIn("run", step)
            self.assertNotIn("env", step)

    def test_secrets_are_only_the_three_env_lines_of_the_last_step(self):
        data = real()
        self.assertEqual(steps(data)[2]["env"], INBOX_ENV)
        text = WORKFLOW.read_text(encoding="utf-8")
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        self.assertEqual(len(re.findall(r"secrets\.", code)), 3)
        for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GITHUB_TOKEN"):
            self.assertEqual(code.count(f"secrets.{name}"), 1, name)
        self.assertNotIn("secrets: inherit", code)
        self.assertNotIn("env", {key for key in data if key != "jobs" and key == "env"})
        for key in ("env", "defaults"):
            self.assertNotIn(key, data)

    def test_the_run_line_has_no_expression_and_no_external_input(self):
        run = steps(real())[2]["run"]
        self.assertNotIn("${{", run)
        self.assertNotIn("$", run)
        text = WORKFLOW.read_text(encoding="utf-8")
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        for needle in ("github.event.issue", "github.event.comment", "github.event.head_commit", "github.event.pull_request", "github.head_ref", "github.event.commits", "inputs."):
            self.assertNotIn(needle, code, needle)

    def test_no_error_hiding_and_no_external_action(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        for needle in ("|| true", "continue-on-error", "docker://"):
            self.assertNotIn(needle, code, needle)
        for step in steps(real()):
            if "uses" in step:
                self.assertTrue(step["uses"].startswith("actions/"), step["uses"])        # 외부 액션 없음(WF-5 의 고정 대상이 없다)

    def test_titles_say_when_the_run_happens_and_never_use_external_values(self):
        self.assertEqual(render(real()["run-name"], context("schedule")), "[공통] 텔레그램 수신 가져오기 · 정기")
        self.assertEqual(render(real()["run-name"], context("push")), "[공통] 텔레그램 수신 가져오기 · 요청 푸시 뒤")
        self.assertEqual(render(real()["run-name"], context("workflow_dispatch")), "[공통] 텔레그램 수신 가져오기 · 수동")
        refs = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+", re.sub(r"'(?:[^']|'')*'", "''", real()["run-name"].split("${{", 1)[1])))
        self.assertEqual(refs, {"github.event_name"})

    def test_the_header_comment_states_the_limits_and_how_to_turn_it_off(self):
        header = WORKFLOW.read_text(encoding="utf-8").split("\non:")[0]
        for needle in ("접수일 뿐 승인이 아니다", "G-S9", "G-S10", "WF-15", "지연", "24시간", "웹훅", "끄는 법", "Disable workflow", "공개", "concurrency" if False else "그룹은 하나"):
            self.assertIn(needle, header, needle)

    def test_the_name_uses_the_common_prefix(self):
        self.assertEqual(real()["name"], "[공통] 텔레그램 수신 가져오기")

    def test_the_python_module_it_runs_exists_and_the_run_line_matches_the_validator(self):
        self.assertTrue((ROOT / "pipeline" / "telegram_inbox.py").is_file())
        self.assertEqual(vr._INBOX_RUN, steps(real())[2]["run"])
        self.assertEqual(vr._INBOX_ENV, INBOX_ENV)
        self.assertEqual(vr._INBOX_CRON, real()["on"]["schedule"][0]["cron"])
        self.assertEqual(vr._INBOX_RUN_NAME, real()["run-name"])


# ====================================================================================================================
# 2. 검증기 규칙 WF-15
# ====================================================================================================================
def findings_for(data=None, extra=None, text=None):
    """data(워크플로 dict)를 임시 저장소 폴더에 쓰고 WF-15 결과를 돌려준다. extra: {상대 경로: 글} 을 더 쓴다."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        files = []
        for rel, content in ({REL: text if text is not None else yaml.safe_dump(data, allow_unicode=True, sort_keys=False)} if (data is not None or text is not None) else {}).items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            files.append(rel)
        for rel, content in (extra or {}).items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            files.append(rel)
        return vr.check_telegram_inbox_workflow(root, files)


def mutated(function):
    data = copy.deepcopy(real())
    function(data)
    return data


def set_in(path, value):
    def apply(data):
        node = data
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return apply


def delete_in(path):
    def apply(data):
        node = data
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
    return apply


RUN = ("jobs", "fetch", "steps", 2)
CHECKOUT = ("jobs", "fetch", "steps", 0)
PYTHON = ("jobs", "fetch", "steps", 1)


def at(path, *more):
    return tuple(path) + more


def step_edit(index, function):
    def apply(data):
        function(data["jobs"]["fetch"]["steps"][index])
    return apply


MUTATIONS = {
    # 트리거
    "pull_request_target 추가": lambda d: d["on"].update({"pull_request_target": {}}),
    "issue_comment 추가": lambda d: d["on"].update({"issue_comment": {"types": ["created"]}}),
    "issues 추가": lambda d: d["on"].update({"issues": {"types": ["opened"]}}),
    "workflow_run 추가": lambda d: d["on"].update({"workflow_run": {"workflows": ["x"]}}),
    "pull_request 추가": lambda d: d["on"].update({"pull_request": {}}),
    "push 삭제": delete_in(("on", "push")),
    "schedule 삭제": delete_in(("on", "schedule")),
    "workflow_dispatch 삭제": delete_in(("on", "workflow_dispatch")),
    "매분 실행": set_in(("on", "schedule"), [{"cron": "* * * * *"}]),
    "5분 간격": set_in(("on", "schedule"), [{"cron": "*/5 * * * *"}]),
    "예약 둘": set_in(("on", "schedule"), [{"cron": "*/10 * * * *"}, {"cron": "5 * * * *"}]),
    "push 에 main 추가": set_in(("on", "push", "branches"), ["ai/claude/**", "main"]),
    "push 를 ai/** 로": set_in(("on", "push", "branches"), ["ai/**"]),
    "push 에 paths": lambda d: d["on"]["push"].update({"paths": ["인수인계/요청함/**"]}),
    "push 에 tags": lambda d: d["on"]["push"].update({"tags": ["*"]}),
    "수동 실행에 입력": set_in(("on", "workflow_dispatch"), {"inputs": {"x": {"type": "string"}}}),
    # 권한
    "contents 쓰기": set_in(("permissions", "contents"), "write"),
    "pull-requests 쓰기 추가": lambda d: d["permissions"].update({"pull-requests": "write"}),
    "actions 쓰기 추가": lambda d: d["permissions"].update({"actions": "write"}),
    "id-token 추가": lambda d: d["permissions"].update({"id-token": "write"}),
    "issues 권한 삭제": delete_in(("permissions", "issues")),
    "write-all": set_in(("permissions",), "write-all"),
    "permissions 없음": delete_in(("permissions",)),
    "issues 읽기": set_in(("permissions", "issues"), "read"),
    # 워크플로·job 수준
    "워크플로 env": lambda d: d.update({"env": {"X": "1"}}),
    "워크플로 defaults": lambda d: d.update({"defaults": {"run": {"shell": "bash"}}}),
    "job permissions": lambda d: d["jobs"]["fetch"].update({"permissions": {"contents": "write"}}),
    "job if": lambda d: d["jobs"]["fetch"].update({"if": "github.actor == 'x'"}),
    "job env": lambda d: d["jobs"]["fetch"].update({"env": {"X": "1"}}),
    "job continue-on-error": lambda d: d["jobs"]["fetch"].update({"continue-on-error": True}),
    "job strategy": lambda d: d["jobs"]["fetch"].update({"strategy": {"matrix": {"x": [1]}}}),
    "job secrets": lambda d: d["jobs"]["fetch"].update({"secrets": "inherit"}),
    "timeout 6": set_in(("jobs", "fetch", "timeout-minutes"), 6),
    "timeout 30": set_in(("jobs", "fetch", "timeout-minutes"), 30),
    "timeout 없음": delete_in(("jobs", "fetch", "timeout-minutes")),
    "timeout 불리언": set_in(("jobs", "fetch", "timeout-minutes"), True),
    "self-hosted": set_in(("jobs", "fetch", "runs-on"), "self-hosted"),
    "windows 러너": set_in(("jobs", "fetch", "runs-on"), "windows-latest"),
    "job 둘": lambda d: d["jobs"].update({"other": copy.deepcopy(d["jobs"]["fetch"])}),
    # 동시 실행
    "concurrency 취소": set_in(("concurrency", "cancel-in-progress"), True),
    "concurrency 그룹 다름": set_in(("concurrency", "group"), "telegram-inbox-${{ github.sha }}"),
    "concurrency 없음": delete_in(("concurrency",)),
    "concurrency 문자열": set_in(("concurrency",), "telegram-inbox"),
    # 단계
    "단계 추가": lambda d: d["jobs"]["fetch"]["steps"].append({"run": "echo hi"}),
    "단계 삭제": lambda d: d["jobs"]["fetch"]["steps"].pop(1),
    "단계 순서 바꿈": lambda d: d["jobs"]["fetch"]["steps"].reverse(),
    "checkout ref": step_edit(0, lambda s: s["with"].update({"ref": "main"})),
    "checkout token": step_edit(0, lambda s: s["with"].update({"token": "${{ secrets.PAT }}"})),
    "checkout fetch-depth": step_edit(0, lambda s: s["with"].update({"fetch-depth": 0})),
    "checkout 자격 유지": step_edit(0, lambda s: s["with"].update({"persist-credentials": True})),
    "checkout with 없음": step_edit(0, lambda s: s.pop("with")),
    "checkout repository": step_edit(0, lambda s: s["with"].update({"repository": "x/y"})),
    "checkout 외부 액션": step_edit(0, lambda s: s.update({"uses": "evil/checkout@v1"})),
    "setup-python cache": step_edit(1, lambda s: s["with"].update({"cache": "pip"})),
    "setup-python env": step_edit(1, lambda s: s.update({"env": {"X": "1"}})),
    "setup-python 외부 액션": step_edit(1, lambda s: s.update({"uses": "evil/python@v1"})),
    "단계 if": step_edit(2, lambda s: s.update({"if": "always()"})),
    "단계 continue-on-error": step_edit(2, lambda s: s.update({"continue-on-error": True})),
    "단계 shell": step_edit(2, lambda s: s.update({"shell": "bash"})),
    "단계 working-directory": step_edit(2, lambda s: s.update({"working-directory": "tests"})),
    "단계 timeout": step_edit(2, lambda s: s.update({"timeout-minutes": 1})),
    "단계 uses": step_edit(2, lambda s: s.update({"uses": "actions/checkout@v6"})),
    "단계 with": step_edit(2, lambda s: s.update({"with": {"x": 1}})),
    # run 줄
    "run 에 인자": step_edit(2, lambda s: s.update({"run": "python -m pipeline.telegram_inbox --x"})),
    "run 다른 모듈": step_edit(2, lambda s: s.update({"run": "python -m pipeline.operator_loop ack"})),
    "run 에 표현식": step_edit(2, lambda s: s.update({"run": "python -m pipeline.telegram_inbox ${{ github.event.head_commit.message }}"})),
    "run || true": step_edit(2, lambda s: s.update({"run": "python -m pipeline.telegram_inbox || true"})),
    "run 두 줄": step_edit(2, lambda s: s.update({"run": "python -m pipeline.telegram_inbox\necho done"})),
    "run 환경변수 출력": step_edit(2, lambda s: s.update({"run": "python -m pipeline.telegram_inbox; echo $TELEGRAM_BOT_TOKEN"})),
    "run 없음": step_edit(2, lambda s: s.pop("run")),
    # env
    "env 추가": step_edit(2, lambda s: s["env"].update({"EXTRA": "1"})),
    "env 채팅 ID 삭제": step_edit(2, lambda s: s["env"].pop("TELEGRAM_CHAT_ID")),
    "env 토큰 삭제": step_edit(2, lambda s: s["env"].pop("TELEGRAM_BOT_TOKEN")),
    "env GITHUB_TOKEN 삭제": step_edit(2, lambda s: s["env"].pop("GITHUB_TOKEN")),
    "env 다른 시크릿": step_edit(2, lambda s: s["env"].update({"TELEGRAM_BOT_TOKEN": "${{ secrets.OTHER }}"})),
    "env GITHUB_TOKEN 을 PAT 로": step_edit(2, lambda s: s["env"].update({"GITHUB_TOKEN": "${{ secrets.PAT }}"})),
    "env 값을 글자 그대로": step_edit(2, lambda s: s["env"].update({"TELEGRAM_CHAT_ID": "12345"})),
    "env 이름 바꿔치기": step_edit(2, lambda s: s["env"].update({"TELEGRAM_BOT_TOKEN": "${{ secrets.TELEGRAM_CHAT_ID }}"})),
    "env 없음": step_edit(2, lambda s: s.pop("env")),
    # 이름
    "run-name 에 외부 값": set_in(("run-name",), "[공통] 수신 ${{ github.event.head_commit.message }}"),
    "run-name 에 브랜치": set_in(("run-name",), "[공통] 텔레그램 수신 가져오기 · ${{ github.ref_name }}"),
}


class ValidatorRuleTest(unittest.TestCase):
    def test_the_real_file_passes_every_workflow_rule(self):
        files = vr.list_files(ROOT)
        self.assertIn(REL, files)
        self.assertEqual([f.line() for f in vr.check_telegram_inbox_workflow(ROOT, files)], [])
        for check in (vr.check_workflows, vr.check_telegram_secrets, vr.check_operator_workflows, vr.check_workflow_names, vr.check_workflow_prefixes):
            self.assertEqual([f.line() for f in check(ROOT, files) if f.level == "ERROR"], [], check.__name__)

    def test_a_fresh_copy_of_the_real_file_is_accepted_after_a_yaml_round_trip(self):
        self.assertEqual(findings_for(real()), [])

    def test_every_wrong_shape_is_rejected(self):
        self.assertGreaterEqual(len(MUTATIONS), 60)
        for name, mutate in MUTATIONS.items():
            with self.subTest(name):
                found = findings_for(mutated(mutate))
                self.assertTrue(found, f"{name}: 검증기가 잡지 못했습니다")
                self.assertTrue(all(f.check == "WF-15" and f.level == "ERROR" and f.path == REL for f in found), name)

    def test_other_workflows_may_not_run_the_inbox_module(self):
        other = yaml.safe_dump({"name": "x", "on": {"push": {}}, "permissions": {"contents": "read"},
                                "jobs": {"j": {"runs-on": "ubuntu-latest", "timeout-minutes": 5, "steps": [{"run": "python -m pipeline.telegram_inbox"}]}}}, allow_unicode=True)
        found = findings_for(real(), extra={".github/workflows/other.yml": other})
        self.assertEqual([(f.check, f.path) for f in found], [("WF-15", ".github/workflows/other.yml")])
        found = findings_for(None, extra={".github/workflows/other.yml": other})
        self.assertEqual([f.check for f in found], ["WF-15"])
        unrelated = other.replace("pipeline.telegram_inbox", "pipeline.notify test")
        self.assertEqual(findings_for(real(), extra={".github/workflows/other.yml": unrelated}), [])

    def test_a_missing_file_means_the_feature_is_off_and_is_not_a_problem(self):
        self.assertEqual(findings_for(None), [])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(vr.check_telegram_inbox_workflow(Path(tmp), []), [])

    def test_unreadable_or_broken_yaml_is_left_to_wf_0(self):
        self.assertEqual(findings_for(text="a: [unclosed\n"), [])
        self.assertEqual(findings_for(text="- just\n- a list\n"), [])

    def test_the_wrong_shape_messages_name_the_reason_in_korean_without_echoing_long_values(self):
        data = mutated(set_in(("jobs", "fetch", "runs-on"), "x" * 500))
        for finding in findings_for(data):
            self.assertLess(len(finding.message), 600)
            self.assertRegex(finding.message, r"[가-힣]")

    def test_wf14_still_covers_only_the_two_operator_workflows(self):
        """WF-14 는 두 워크플로만 본다 — 새 워크플로가 있어도 WF-14 의 오류가 늘지 않는다."""
        files = vr.list_files(ROOT)
        self.assertEqual(vr.check_operator_workflows(ROOT, files), [])
        self.assertEqual([vr.AI_REQUEST_WORKFLOW, vr.OPERATOR_REPLY_WORKFLOW], [".github/workflows/ai-request.yml", ".github/workflows/operator-reply.yml"])

    def test_the_whole_validator_has_no_errors_on_the_repository(self):
        errors = [f.line() for f in vr.run_checks(ROOT) if f.level == "ERROR"]
        self.assertEqual(errors, [])

    def test_run_checks_calls_the_new_rule(self):
        source = (ROOT / "scripts" / "validate_repo.py").read_text(encoding="utf-8")
        self.assertIn("findings += check_telegram_inbox_workflow(root, files)", source)


if __name__ == "__main__":
    unittest.main()
