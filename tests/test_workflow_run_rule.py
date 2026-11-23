"""검증기 규칙 WF-16 시험 — `on: workflow_run` 워크플로의 허용 목록과 모양(감사 BA-S1-4 의 탐침 D, 2026-11-23. 2차: 판정 job·발송 job 둘로 나눔 — 안전 검증 S 의 AN1-S-4).

`workflow_run` 은 가지·PR 의 글(`github.event.workflow_run.head_branch`·`head_commit.message`·`display_title`)이 시크릿을 쥔 기본 가지의 파일 안으로 들어오는 길이다. 이 시험은
 1. 허용 목록(`scripts/validate_repo.py` 의 `WORKFLOW_RUN_ALLOWED`)이 병합 알림 워크플로 둘뿐이고 진짜 파일 둘과 저장소의 다른 워크플로 전부가 규칙을 통과하는지,
 2. 허용 목록 밖의 `workflow_run`(탐침 D 꼴 포함)이 오류인지,
 3. 허용된 파일도 한 군데씩 망가뜨리면(쓰기 권한·가지 코드 체크아웃·run·script 의 `${{ }}`·시크릿 위치·외부 액션·job 구조(decide·send)·needs·if·outputs …) 모두 오류가 되는지(탐침 A·B 꼴을 `workflow_run` 으로 바꾼 것 포함)
 를 가짜 워크플로로 확인한다. 변이는 YAML 을 읽은 값에서 한 군데씩 고쳐 다시 쓴 사본이고, job 마다(decide·send) 따로 적용한다. 검증기가 못 보는 것은 마지막 절에 '못 잡는다'고 단언해 둔다.
"""
import copy
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

READY = ".github/workflows/merge-ready-notice.yml"
CONFIRM = ".github/workflows/merge-confirm-notice.yml"
BOTH = (READY, CONFIRM)
READY_NAME = "[공통] 병합 부탁 PR 자동 만들기"
JOBS = ("decide", "send")
DECIDE_CMDS = {READY: "python -m pipeline.auto_notice merge-ready", CONFIRM: "python -m pipeline.auto_notice merge-confirm"}
SEND_CMD = "python -m pipeline.auto_notice send"


def real(rel):
    return (ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def real_data(rel):
    return yaml.safe_load(real(rel))


def dump(data):
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1_000_000)


def check(files):
    """{파일 이름 또는 경로: 글} 를 임시 저장소에 쓰고 WF-16 검사 결과(Finding 목록)를 돌려준다."""
    with tempfile.TemporaryDirectory() as tmp:
        root, rels = Path(tmp), []
        for name, text in files.items():
            rel = name if name.startswith(".github/") else f".github/workflows/{name}"
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            rels.append(rel)
        return vr.check_workflow_run_workflows(root, rels)


def codes(findings):
    return {finding.check for finding in findings}


def messages(findings):
    return "\n".join(finding.message for finding in findings)


def on_of(data):
    return data[True] if True in data else data["on"]


def step_of(data, job, index):
    return data["jobs"][job]["steps"][index]


def move_secrets(data):
    """발송 단계의 텔레그램 시크릿 둘을 판정 단계 env 로 옮긴다(발송 job 에서는 뺀다) — '시크릿은 마지막 단계 env 에' 라는 자리만 보면 놓칠 수 있는 변형."""
    send_env = step_of(data, "send", 2)["env"]
    moved = {key: send_env.pop(key) for key in list(send_env) if key.startswith("TELEGRAM_")}
    step_of(data, "decide", 2)["env"].update(moved)


def catalog(rel):
    """(이름, 사본을 고치는 함수, 오류 문구에 있어야 할 글) 목록 — 진짜 파일을 한 군데씩 망가뜨린다."""
    out = []

    def add(label, fn, needle):
        out.append((label, fn, needle))

    secret = "${{ secrets.TELEGRAM_BOT_TOKEN }}"
    # ---- 최상위: 권한·env·트리거·필터 ----
    for key in ("contents", "pull-requests", "actions"):
        add(f"{key} 쓰기", lambda d, key=key: d["permissions"].__setitem__(key, "write"), "쓰기 권한")
    for key in ("issues", "id-token", "checks", "packages", "statuses", "deployments", "discussions", "security-events"):
        add(f"{key} 쓰기 추가", lambda d, key=key: d["permissions"].__setitem__(key, "write"), "쓰기 권한")
    add("permissions 를 write-all 글자로", lambda d: d.__setitem__("permissions", "write-all"), "permissions")
    add("permissions 를 read-all 글자로", lambda d: d.__setitem__("permissions", "read-all"), "permissions")
    add("permissions 삭제", lambda d: d.pop("permissions"), "permissions")
    add("permissions 를 빈 표로", lambda d: d.__setitem__("permissions", {}), "permissions")
    add("워크플로 수준 env", lambda d: d.__setitem__("env", {"X": "y"}), "env")
    add("워크플로 수준 defaults", lambda d: d.__setitem__("defaults", {"run": {"shell": "bash"}}), "defaults")
    for trigger, value in (("workflow_dispatch", None), ("push", None), ("issue_comment", {"types": ["created"]}), ("schedule", [{"cron": "0 * * * *"}]), ("pull_request", None),
                           ("pull_request_target", None), ("issues", {"types": ["opened"]}), ("repository_dispatch", None), ("release", None)):
        add(f"{trigger} 트리거 추가", lambda d, trigger=trigger, value=value: on_of(d).__setitem__(trigger, value), "트리거")
    add("types 에 requested 추가", lambda d: on_of(d)["workflow_run"].__setitem__("types", ["completed", "requested"]), "types")
    add("types 삭제", lambda d: on_of(d)["workflow_run"].pop("types"), "types")
    add("가지 필터 삭제", lambda d: on_of(d)["workflow_run"].pop("branches"), "branches")
    add("branches-ignore 로 바꿈", lambda d: on_of(d)["workflow_run"].__setitem__("branches-ignore", on_of(d)["workflow_run"].pop("branches")), "branches")
    add("가지 필터를 모든 가지로", lambda d: on_of(d)["workflow_run"].__setitem__("branches", ["**"]), "가지 필터")
    add("가지 필터를 비운 목록으로", lambda d: on_of(d)["workflow_run"].__setitem__("branches", []), "branches")
    add("따라 도는 워크플로를 다른 것으로", lambda d: on_of(d)["workflow_run"].__setitem__("workflows", ["다른 워크플로"]), "workflows")
    add("따라 도는 워크플로를 하나 더", lambda d: on_of(d)["workflow_run"]["workflows"].append("다른 워크플로"), "workflows")
    # ---- job 구조 ----
    add("job 하나 더", lambda d: d["jobs"].__setitem__("third", {"name": "셋째", "runs-on": "ubuntu-latest", "timeout-minutes": 5, "steps": [{"run": "echo hi"}]}), "정확히 `decide`")
    add("판정 job 삭제", lambda d: d["jobs"].pop("decide"), "정확히 `decide`")
    add("발송 job 삭제", lambda d: d["jobs"].pop("send"), "정확히 `decide`")
    add("발송 job 이름을 notify 로", lambda d: d["jobs"].__setitem__("notify", d["jobs"].pop("send")), "정확히 `decide`")
    add("두 job 을 하나로 합침(옛 구조)", lambda d: (d["jobs"]["decide"]["steps"].append(d["jobs"].pop("send")["steps"][2]), d["jobs"]["decide"].pop("outputs")), "정확히 `decide`")
    # ---- 판정 job 의 출력 ----
    add("decide: outputs 삭제", lambda d: d["jobs"]["decide"].pop("outputs"), "outputs")
    add("decide: outputs 의 message 삭제", lambda d: d["jobs"]["decide"]["outputs"].pop("message"), "outputs")
    add("decide: outputs 의 send 삭제", lambda d: d["jobs"]["decide"]["outputs"].pop("send"), "outputs")
    add("decide: outputs 에 셋째 출력", lambda d: d["jobs"]["decide"]["outputs"].__setitem__("extra", "${{ steps.decide.outputs.extra }}"), "outputs")
    add("decide: outputs 가 다른 단계를 가리킴", lambda d: d["jobs"]["decide"]["outputs"].__setitem__("message", "${{ steps.other.outputs.message }}"), "outputs")
    add("decide: outputs 에 이벤트 값", lambda d: d["jobs"]["decide"]["outputs"].__setitem__("message", "${{ github.event.workflow_run.head_commit.message }}"), "outputs")
    add("decide: outputs 에 시크릿", lambda d: d["jobs"]["decide"]["outputs"].__setitem__("leak", secret), "시크릿")
    add("decide: outputs 가 표가 아님", lambda d: d["jobs"]["decide"].__setitem__("outputs", "x"), "outputs")
    add("decide: 판정 단계 id 를 바꿈", lambda d: step_of(d, "decide", 2).__setitem__("id", "other"), "id")
    add("decide: 판정 단계 id 삭제", lambda d: step_of(d, "decide", 2).pop("id"), "id")
    # ---- 발송 job 의 needs·if·env ----
    add("send: needs 삭제", lambda d: d["jobs"]["send"].pop("needs"), "needs")
    add("send: needs 를 다른 job 으로", lambda d: d["jobs"]["send"].__setitem__("needs", "other"), "needs")
    add("send: needs 에 job 을 더함", lambda d: d["jobs"]["send"].__setitem__("needs", ["decide", "other"]), "needs")
    add("send: needs 를 빈 목록으로", lambda d: d["jobs"]["send"].__setitem__("needs", []), "needs")
    add("send: if 삭제", lambda d: d["jobs"]["send"].pop("if"), "if")
    add("send: if 를 항상 참으로", lambda d: d["jobs"]["send"].__setitem__("if", "always()"), "if")
    add("send: if 를 true 로", lambda d: d["jobs"]["send"].__setitem__("if", "true"), "if")
    add("send: if 에 조건 추가", lambda d: d["jobs"]["send"].__setitem__("if", "needs.decide.outputs.send == 'yes' || true"), "if")
    add("send: if 가 이벤트 값을 봄", lambda d: d["jobs"]["send"].__setitem__("if", "github.event.workflow_run.head_branch != 'x'"), "if")
    add("send: if 가 다른 출력을 봄", lambda d: d["jobs"]["send"].__setitem__("if", "needs.decide.outputs.message != ''"), "if")
    add("send: if 에 시크릿", lambda d: d["jobs"]["send"].__setitem__("if", "secrets.TELEGRAM_BOT_TOKEN != ''"), "시크릿")
    add("send: outputs 를 가짐", lambda d: d["jobs"]["send"].__setitem__("outputs", {"x": "y"}), "outputs")
    add("send: 발송 env 에 PYTHONPATH", lambda d: step_of(d, "send", 2)["env"].__setitem__("PYTHONPATH", "/tmp/x"), "이름은 정확히")
    add("send: 발송 env 에 LD_PRELOAD", lambda d: step_of(d, "send", 2)["env"].__setitem__("LD_PRELOAD", "/tmp/x.so"), "이름은 정확히")
    add("send: 발송 env 에서 문장 삭제", lambda d: step_of(d, "send", 2)["env"].pop("NOTICE_MESSAGE_B64"), "이름은 정확히")
    add("send: 발송 env 에서 chat id 삭제", lambda d: step_of(d, "send", 2)["env"].pop("TELEGRAM_CHAT_ID"), "이름은 정확히")
    add("send: 문장이 이벤트 값", lambda d: step_of(d, "send", 2)["env"].__setitem__("NOTICE_MESSAGE_B64", "${{ github.event.workflow_run.head_commit.message }}"), "NOTICE_MESSAGE_B64")
    add("send: 문장이 다른 출력", lambda d: step_of(d, "send", 2)["env"].__setitem__("NOTICE_MESSAGE_B64", "${{ needs.decide.outputs.send }}"), "NOTICE_MESSAGE_B64")
    add("send: 문장이 글자 그대로", lambda d: step_of(d, "send", 2)["env"].__setitem__("NOTICE_MESSAGE_B64", "QUJD"), "NOTICE_MESSAGE_B64")
    # ---- job 마다(decide·send) ----
    for job in JOBS:
        def put(key, value, job=job):
            return lambda d: d["jobs"][job].__setitem__(key, value)

        for key, value in (("permissions", {"contents": "write"}), ("env", {"X": "y"}), ("defaults", {"run": {"shell": "bash"}}), ("strategy", {"matrix": {"k": ["a"]}}), ("container", "evil/image"),
                           ("services", {"x": {"image": "y"}}), ("environment", "prod"), ("continue-on-error", True), ("secrets", "inherit"), ("uses", "./.github/workflows/x.yml")):
            add(f"{job}: job 에 {key}", put(key, value), f"`{key}` 가 있습니다")
        add(f"{job}: job 에 허용되지 않은 키(concurrency)", put("concurrency", "x"), "허용되지 않은 키")
        add(f"{job}: runs-on 을 self-hosted 로", put("runs-on", "self-hosted"), "ubuntu-latest")
        add(f"{job}: runs-on 을 목록으로", put("runs-on", ["self-hosted", "linux"]), "ubuntu-latest")
        add(f"{job}: runs-on 삭제", lambda d, job=job: d["jobs"][job].pop("runs-on"), "ubuntu-latest")
        add(f"{job}: 단계 하나 더", lambda d, job=job: d["jobs"][job]["steps"].append({"run": "echo hi"}), "정확히 셋")
        add(f"{job}: 단계 하나 더(이름만 있는 빈 단계)", lambda d, job=job: d["jobs"][job]["steps"].insert(1, {"name": "빈 단계"}), "실행할 것이 없는")
        add(f"{job}: 단계 순서를 거꾸로", lambda d, job=job: d["jobs"][job]["steps"].reverse(), "정확히 셋")
        add(f"{job}: setup-python 삭제", lambda d, job=job: d["jobs"][job]["steps"].pop(1), "정확히 셋")
        add(f"{job}: 체크아웃 삭제", lambda d, job=job: d["jobs"][job]["steps"].pop(0), "정확히 셋")
        add(f"{job}: run 단계 삭제", lambda d, job=job: d["jobs"][job]["steps"].pop(2), "정확히 셋")
        # 체크아웃
        for label, fn, needle in (("ref 삭제", lambda w: w.pop("ref"), "ref"),
                                  ("ref 를 실행의 커밋으로", lambda w: w.__setitem__("ref", "${{ github.event.workflow_run.head_sha }}"), "ref"),
                                  ("ref 를 실행의 가지로", lambda w: w.__setitem__("ref", "${{ github.event.workflow_run.head_branch }}"), "ref"),
                                  ("ref 를 PR 병합 참조로", lambda w: w.__setitem__("ref", "refs/pull/1/merge"), "ref"),
                                  ("ref 를 github.head_ref 로", lambda w: w.__setitem__("ref", "${{ github.head_ref }}"), "ref"),
                                  ("ref 를 다른 가지로", lambda w: w.__setitem__("ref", "develop"), "ref"),
                                  ("다른 저장소", lambda w: w.__setitem__("repository", "evil/other"), "허용되지 않은 항목"),
                                  ("token", lambda w: w.__setitem__("token", "x"), "허용되지 않은 항목"),
                                  ("submodules", lambda w: w.__setitem__("submodules", True), "허용되지 않은 항목"),
                                  ("ssh-key", lambda w: w.__setitem__("ssh-key", "x"), "허용되지 않은 항목"),
                                  ("persist-credentials 삭제", lambda w: w.pop("persist-credentials"), "persist-credentials"),
                                  ("persist-credentials true", lambda w: w.__setitem__("persist-credentials", True), "persist-credentials"),
                                  ("시크릿을 with 에", lambda w: w.__setitem__("token", secret), "시크릿")):
            add(f"{job}: 체크아웃 {label}", lambda d, job=job, fn=fn: fn(step_of(d, job, 0)["with"]), needle)
        add(f"{job}: setup-python 에 다른 입력", lambda d, job=job: step_of(d, job, 1)["with"].__setitem__("cache", "pip"), "setup-python")
        # 외부 액션(setup-python 자리에)
        for label, replacement, needle in (("github-script 단계(탐침 B 꼴)", {"uses": "actions/github-script@v7", "with": {"script": "console.log('x')"}}, "외부 액션"),
                                           ("github-script 의 script 에 식(탐침 B)", {"uses": "actions/github-script@v7", "with": {"script": 'console.log("${{ github.event.workflow_run.head_commit.message }}")'}}, "script"),
                                           ("제3자 액션", {"uses": "peter-evans/create-pull-request@v6"}, "외부 액션"), ("로컬 액션", {"uses": "./.github/actions/x"}, "외부 액션")):
            add(f"{job}: {label}", lambda d, job=job, replacement=replacement: d["jobs"][job]["steps"].__setitem__(1, copy.deepcopy(replacement)), needle)
        # 단계 키
        for key, value in (("shell", "python"), ("continue-on-error", True), ("working-directory", "/tmp"), ("timeout-minutes", 1)):
            add(f"{job}: 단계에 {key}", lambda d, job=job, key=key, value=value: step_of(d, job, 2).__setitem__(key, value), "허용되지 않은 키")
        # run 단계(맨 끝)
        for label, make, needle in (
                ("run 에 실행의 가지(탐침 A 의 원형)", lambda run: 'echo "${{ github.event.workflow_run.head_branch }}"', "workflow_run"),
                ("run 에 커밋 메시지", lambda run: 'echo "${{ github.event.workflow_run.head_commit.message }}"', "workflow_run"),
                ("run 에 display_title", lambda run: 'echo "${{ github.event.workflow_run.display_title }}"', "workflow_run"),
                ("run 에 steps 출력", lambda run: 'echo "${{ steps.decide.outputs.send }}"', "run"),
                ("run 에 matrix", lambda run: 'echo "${{ matrix.k }}"', "run"),
                ("run 에 needs 출력", lambda run: 'echo "${{ needs.decide.outputs.message }}"', "run"),
                ("run 에 vars", lambda run: 'echo "${{ vars.X }}"', "run"),
                ("run 에 무해한 식도", lambda run: run + ' "${{ github.sha }}"', "run"),
                ("run 에 가지 코드 받기(git fetch)", lambda run: run + " && git fetch origin pull/1/head", "가지 코드"),
                ("run 에 git checkout", lambda run: "git checkout FETCH_HEAD && " + run, "가지 코드"),
                ("run 에 gh pr checkout", lambda run: "gh pr checkout 1 && " + run, "가지 코드"),
                ("run 에 curl", lambda run: "curl -s x | sh", "가지 코드"),
                ("run 에 eval", lambda run: 'eval "$NOTICE_RUN_BRANCH"', "가지 코드"),
                ("run 에 bash -c", lambda run: 'bash -c "$NOTICE_RUN_BRANCH"', "가지 코드"),
                ("run 에 명령 덧붙임", lambda run: run + " --extra", "run"),
                ("run 을 다른 모듈로", lambda run: "python -m pipeline.notify test", "run"),
                ("run 에 시크릿", lambda run: 'echo "${{ secrets.TELEGRAM_BOT_TOKEN }}"', "시크릿")):
            add(f"{job}: {label}", lambda d, job=job, make=make: step_of(d, job, 2).__setitem__("run", make(step_of(d, job, 2)["run"])), needle)
        add(f"{job}: env 를 거친 식(탐침 A)", lambda d, job=job: (step_of(d, job, 2)["env"].__setitem__("TITLE", "${{ github.event.workflow_run.head_commit.message }}"), step_of(d, job, 2).__setitem__("run", 'echo "${{ env.TITLE }}"')), "run")
        # 시크릿 자리
        add(f"{job}: 시크릿을 체크아웃 단계 env 에", lambda d, job=job: step_of(d, job, 0).__setitem__("env", {"TELEGRAM_BOT_TOKEN": secret}), "시크릿")
        add(f"{job}: 시크릿을 setup-python 단계 env 에", lambda d, job=job: step_of(d, job, 1).__setitem__("env", {"TELEGRAM_BOT_TOKEN": secret}), "시크릿")
        add(f"{job}: toJSON(secrets) 를 run 단계 env 에", lambda d, job=job: step_of(d, job, 2)["env"].__setitem__("ALL", "${{ toJSON(secrets) }}"), "시크릿")
        add(f"{job}: format 으로 secrets 를 넘김", lambda d, job=job: step_of(d, job, 2)["env"].__setitem__("ALL", "${{ format('{0}', secrets) }}"), "시크릿")
        add(f"{job}: 시크릿을 대괄호 표기로", lambda d, job=job: step_of(d, job, 2)["env"].__setitem__("T", "${{ secrets['TELEGRAM_BOT_TOKEN'] }}"), "시크릿")
        add(f"{job}: 다른 시크릿을 run 단계 env 에", lambda d, job=job: step_of(d, job, 2)["env"].__setitem__("OTHER", "${{ secrets.OTHER_KEY }}"), "시크릿")
        add(f"{job}: GITHUB_TOKEN 시크릿 표기를 run 단계 env 에", lambda d, job=job: step_of(d, job, 2)["env"].__setitem__("GITHUB_TOKEN", "${{ secrets.GITHUB_TOKEN }}"), "시크릿")
        add(f"{job}: 시크릿 이름이 소문자", lambda d, job=job: step_of(d, job, 2)["env"].__setitem__("TELEGRAM_BOT_TOKEN", "${{ secrets.telegram_bot_token }}"), "시크릿")
        add(f"{job}: 시크릿을 job env 에", lambda d, job=job: d["jobs"][job].__setitem__("env", {"TELEGRAM_CHAT_ID": "${{ secrets.TELEGRAM_CHAT_ID }}"}), "시크릿")
    # 판정 job 에 시크릿(발송 job 에서만 허용되는 자리인 '마지막 단계 env' 라도 판정 job 이면 오류)
    add("decide: 텔레그램 시크릿을 판정 단계 env 에", lambda d: step_of(d, "decide", 2)["env"].__setitem__("TELEGRAM_BOT_TOKEN", secret), "시크릿")
    add("decide: 텔레그램 시크릿 둘을 판정 단계 env 로 옮김", move_secrets, "시크릿")
    add("send: 다른 시크릿을 발송 단계에", lambda d: step_of(d, "send", 2)["env"].__setitem__("OTHER", "${{ secrets.OTHER_KEY }}"), "시크릿")
    add("send: 발송 단계가 맨 끝이 아님", lambda d: d["jobs"]["send"]["steps"].append({"name": "뒤 단계", "run": SEND_CMD}), "시크릿")
    add("send: 시크릿을 워크플로 env 에", lambda d: d.__setitem__("env", {"TELEGRAM_BOT_TOKEN": secret}), "시크릿")
    # 두 job 의 run 명령을 서로 바꿈
    add("decide: 판정 job 이 발송 명령을 돌림", lambda d: step_of(d, "decide", 2).__setitem__("run", SEND_CMD), "정확히")
    add("send: 발송 job 이 판정 명령을 돌림", lambda d, rel=rel: step_of(d, "send", 2).__setitem__("run", DECIDE_CMDS[rel]), "정확히")
    add("send: 발송 job 의 run 을 다른 모듈로", lambda d: step_of(d, "send", 2).__setitem__("run", "python -m pipeline.notify test"), "정확히")
    return out


class AllowListTest(unittest.TestCase):
    def test_the_allow_list_is_exactly_the_two_merge_notice_workflows(self):
        self.assertEqual(sorted(vr.WORKFLOW_RUN_ALLOWED), sorted(BOTH))
        self.assertEqual((vr.MERGE_READY_WORKFLOW, vr.MERGE_CONFIRM_WORKFLOW), (READY, CONFIRM))
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[READY]["workflows"], [READY_NAME])
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[CONFIRM]["workflows"], ["[공통] 저장소 규칙·테스트 자동 검사"])
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[CONFIRM]["branches"], ["main"])
        for rel, spec in vr.WORKFLOW_RUN_ALLOWED.items():
            self.assertEqual(spec["send"], SEND_CMD, rel)                                         # 발송 job 의 명령은 두 파일이 같다
            self.assertTrue(spec["decide"].startswith("python -m pipeline.auto_notice merge-"), rel)
            self.assertEqual(set(spec), {"workflows", "branches", "decide", "send"}, rel)
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[READY]["decide"], DECIDE_CMDS[READY])
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[CONFIRM]["decide"], DECIDE_CMDS[CONFIRM])
        self.assertEqual((vr.DECIDE_JOB, vr.SEND_JOB), ("decide", "send"))

    def test_only_the_two_real_files_use_workflow_run_and_they_pass(self):
        files = vr.list_files(ROOT)
        users = []
        for rel in files:
            if re.fullmatch(r"\.github/workflows/[^/]+\.ya?ml", rel):
                data = yaml.safe_load(real(rel))
                if "workflow_run" in vr._triggers(data):
                    users.append(rel)
        self.assertEqual(sorted(users), sorted(BOTH))
        self.assertEqual([finding.line() for finding in vr.check_workflow_run_workflows(ROOT, files)], [])

    def test_the_real_files_pass_with_no_other_workflow_rule_complaining_either(self):
        files = list(BOTH)
        for check_name in ("check_workflows", "check_telegram_secrets", "check_workflow_names", "check_workflow_prefixes", "check_workflow_run_workflows"):
            self.assertEqual([finding.line() for finding in getattr(vr, check_name)(ROOT, files)], [], check_name)

    def test_the_real_files_have_two_jobs_with_the_secrets_only_in_the_send_job(self):
        for rel in BOTH:
            data = real_data(rel)
            self.assertEqual(list(data["jobs"]), ["decide", "send"], rel)
            self.assertNotIn("secrets", str(data["jobs"]["decide"]), rel)                          # 판정 job 에는 시크릿이 하나도 없다
            self.assertEqual(str(data["jobs"]["send"]).count("secrets."), 2, rel)
            self.assertEqual(data["jobs"]["send"]["needs"], "decide")
            self.assertEqual(data["jobs"]["send"]["if"], "needs.decide.outputs.send == 'yes'")

    def test_the_rule_is_wired_into_check_workflows_so_every_entry_point_that_calls_it_sees_it(self):
        """감사의 탐침 스크립트처럼 `check_workflows` 만 부르는 곳에서도 workflow_run 이 잡히려고 규칙을 그 함수의 파일 반복 안(WF-3 바로 뒤)에서 부른다.
        `run_checks` 에는 따로 등록하지 않는다 — 같은 오류가 두 번 나오지 않게(`check_workflow_run_workflows` 는 시험·도구가 따로 부르는 같은 규칙의 입구다)."""
        source = (ROOT / "scripts" / "validate_repo.py").read_text(encoding="utf-8").replace("\r\n", "\n")
        body = source[source.index("def check_workflows(root, files):"):source.index("TELEGRAM_SECRETS = (")]
        self.assertEqual(body.count("_workflow_run_findings(rel, data)"), 1)
        self.assertIn('        if "workflow_run" in triggers:\n            out.extend(_workflow_run_findings(rel, data))', body)
        self.assertLess(body.index('"pull_request_target" in triggers'), body.index('"workflow_run" in triggers'))
        self.assertEqual(source.count("findings += check_workflow_run_workflows(root, files)"), 0)
        self.assertEqual(source.count("findings += check_workflows(root, files)"), 1)
        self.assertEqual(source.count("_workflow_run_findings("), 3)                       # 정의 하나 + check_workflows 의 호출 + check_workflow_run_workflows 의 호출

    def test_check_workflows_and_the_standalone_entry_report_the_same_findings_once_each(self):
        for rel in BOTH:
            broken = real(rel).replace("  contents: read\n", "  contents: write\n", 1)
            self.assertNotEqual(broken, real(rel))
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / rel
                path.parent.mkdir(parents=True)
                path.write_text(broken, encoding="utf-8", newline="\n")
                via_all = [f.message for f in vr.check_workflows(Path(tmp), [rel]) if f.check == "WF-16"]
                alone = [f.message for f in vr.check_workflow_run_workflows(Path(tmp), [rel])]
            self.assertEqual(via_all, alone, rel)
            self.assertTrue(via_all, rel)
            self.assertEqual(len(via_all), len(set(via_all)), rel)                          # 같은 오류가 두 번 나오지 않는다

    def test_an_unknown_workflow_with_workflow_run_is_an_error_even_if_everything_else_is_fine(self):
        for rel in BOTH:
            with self.subTest(rel):
                found = check({"another-notice.yml": real(rel)})
                self.assertEqual(codes(found), {"WF-16"})
                self.assertIn("허용 목록에 없는 workflow_run", messages(found))
                self.assertTrue(all(finding.level == "ERROR" for finding in found))
                self.assertEqual(len(found), 2)                                              # 모양은 멀쩡하니 허용 목록 오류 하나 + 허용 목록 밖 파일의 판정 job 출력(`outputs`)뿐 — 출력은 허용된 파일의 판정 job 만 낼 수 있다
                self.assertIn("job 'decide' 에 `outputs` 가 있습니다", messages(found))

    def test_the_names_must_match_exactly_a_renamed_copy_or_a_directory_trick_is_not_allowed(self):
        text = real(READY)
        for name in ("merge-ready-notice.yaml", "Merge-Ready-Notice.yml", "merge-ready-notice.yml.bak.yml", "merge-ready-notice2.yml", "merge-confirm-notice.yaml", "MERGE-READY-NOTICE.YML"):
            with self.subTest(name):
                found = check({name: text})
                self.assertIn("허용 목록에 없는 workflow_run", messages(found))
        # 한 단계 안쪽 폴더의 파일은 GitHub 가 워크플로로 읽지 않는다(검증기도 `.github/workflows/<이름>.yml` 만 워크플로로 센다)
        self.assertEqual(check({"sub/merge-ready-notice.yml": text}), [])

    def test_probe_d_of_the_audit_is_caught(self):
        """감사 BA-S1-4 탐침 D: `on: workflow_run` + contents: write 인 가짜 워크플로가 예전에는 0건이었다."""
        probe = '''name: "[공통] x"
on: {workflow_run: {workflows: [ci], types: [completed]}}
permissions: {contents: write}
jobs:
  j:
    name: 가
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo hi
'''
        found = check({"x.yml": probe})
        self.assertEqual(codes(found), {"WF-16"})
        text = messages(found)
        for needle in ("허용 목록에 없는 workflow_run", "쓰기 권한이 있습니다", "branches"):
            self.assertIn(needle, text)
        # 탐침 스크립트가 부르는 진입점(`check_workflows`)에서도 같은 결과가 나온다
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".github" / "workflows" / "x.yml"
            path.parent.mkdir(parents=True)
            path.write_text(probe, encoding="utf-8", newline="\n")
            via_entry = [f for f in vr.check_workflows(Path(tmp), [".github/workflows/x.yml"]) if f.level == "ERROR"]
        self.assertEqual({f.check for f in via_entry}, {"WF-16"})
        self.assertEqual(sorted(f.message for f in via_entry), sorted(f.message for f in found))

    def test_other_triggers_are_not_this_rule(self):
        for trigger in ("push", "issues", "workflow_dispatch", "schedule"):
            with self.subTest(trigger):
                body = {"push": "on:\n  push:\n    branches: [main]\n", "issues": "on:\n  issues:\n    types: [opened]\n", "workflow_dispatch": "on:\n  workflow_dispatch:\n",
                        "schedule": "on:\n  schedule:\n    - cron: '0 0 * * *'\n"}[trigger]
                text = 'name: "[공통] x"\n' + body + "permissions:\n  contents: write\njobs:\n  j:\n    name: 가\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - run: echo hi\n"
                self.assertEqual(check({"x.yml": text}), [])

    def test_on_written_as_a_string_or_a_list_is_still_seen(self):
        for on_text in ("on: workflow_run\n", "on: [workflow_run]\n", "on:\n  - workflow_run\n"):
            with self.subTest(on_text):
                text = 'name: "[공통] x"\n' + on_text + "permissions:\n  contents: read\njobs:\n  j:\n    name: 가\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - run: echo hi\n"
                found = check({"x.yml": text})
                self.assertIn("허용 목록에 없는 workflow_run", messages(found))

    def test_a_missing_allowed_file_is_not_a_problem_and_unparseable_files_are_left_to_wf0(self):
        self.assertEqual(check({}), [])
        self.assertEqual(check({"x.yml": "name: [broken"}), [])
        self.assertEqual(check({"x.yml": "- just\n- a list\n"}), [])
        self.assertEqual(vr.check_workflow_run_workflows(Path(tempfile.gettempdir()), []), [])


class MutationTest(unittest.TestCase):
    """진짜 워크플로 둘을 한 군데씩 망가뜨린 사본이 모두 WF-16 오류가 된다. 살아남는 변이가 있으면 그 줄은 규칙이 못 지킨다."""

    def test_the_catalog_is_big_and_every_label_is_unique_per_file(self):
        for rel in BOTH:
            labels = [label for label, _fn, _needle in catalog(rel)]
            self.assertEqual(len(labels), len(set(labels)), rel)
            self.assertGreaterEqual(len(labels), 200, rel)

    def test_the_real_files_pass_even_after_a_dump_and_reload_the_baseline_of_every_mutation(self):
        for rel in BOTH:
            self.assertEqual(check({rel: dump(real_data(rel))}), [], rel)

    def test_every_mutation_of_both_real_workflows_is_caught_by_wf16(self):
        count = 0
        for rel in BOTH:
            original = real_data(rel)
            for label, fn, needle in catalog(rel):
                mutated = copy.deepcopy(original)
                fn(mutated)
                self.assertNotEqual(mutated, original, f"변이가 글을 바꾸지 못했다: {label}")
                count += 1
                with self.subTest(f"{Path(rel).name}: {label}"):
                    found = [finding for finding in check({rel: dump(mutated)}) if finding.check == "WF-16"]
                    self.assertTrue(found, f"살아남은 변이: {label}")
                    self.assertTrue(all(finding.level == "ERROR" for finding in found))
                    self.assertIn(needle, messages(found), f"{label}: 기대한 문구 '{needle}' 가 없다")
        self.assertGreaterEqual(count, 2 * 200)

    def test_harmless_edits_still_pass(self):
        """규칙이 지나치게 넓어 정상 편집까지 막지 않는지: 이름·주석·ref 를 main 글자로·fetch-depth 추가·시간 제한 변경·판정 단계 env 값 추가·단계 조건은 통과한다."""
        harmless = {
            "발송 단계 이름": lambda d: step_of(d, "send", 2).__setitem__("name", "다른 이름"),
            "판정 단계 이름": lambda d: step_of(d, "decide", 2).__setitem__("name", "다른 이름"),
            "job 이름": lambda d: d["jobs"]["send"].__setitem__("name", "다른 job 이름"),
            "판정 job 이름": lambda d: d["jobs"]["decide"].__setitem__("name", "다른 job 이름"),
            "판정 job 의 ref 를 main 글자로": lambda d: step_of(d, "decide", 0)["with"].__setitem__("ref", "main"),
            "발송 job 의 ref 를 main 글자로": lambda d: step_of(d, "send", 0)["with"].__setitem__("ref", "main"),
            "fetch-depth 추가": lambda d: step_of(d, "send", 0)["with"].__setitem__("fetch-depth", 1),
            "시간 제한 변경": lambda d: d["jobs"]["send"].__setitem__("timeout-minutes", 7),
            "판정 job 시간 제한 변경": lambda d: d["jobs"]["decide"].__setitem__("timeout-minutes", 7),
            "python 버전 변경": lambda d: step_of(d, "send", 1)["with"].__setitem__("python-version", "3.10"),
            "concurrency 이름 변경": lambda d: d["concurrency"].__setitem__("group", d["concurrency"]["group"].replace("merge-", "merged-")),
            "판정 단계 env 에 값 추가": lambda d: step_of(d, "decide", 2)["env"].__setitem__("NOTICE_EXTRA", "${{ github.run_id }}"),
            "판정 단계에 조건": lambda d: step_of(d, "decide", 2).__setitem__("if", "github.event.workflow_run.head_branch != 'x'"),
            "발송 job 의 needs 를 목록 하나로": lambda d: d["jobs"]["send"].__setitem__("needs", ["decide"]),
        }
        for rel in BOTH:
            for label, fn in harmless.items():
                data = real_data(rel)
                fn(data)
                with self.subTest(f"{Path(rel).name}: {label}"):
                    self.assertNotEqual(data, real_data(rel))
                    self.assertEqual([finding.line() for finding in check({rel: dump(data)})], [])
            with self.subTest(f"{Path(rel).name}: 주석 추가"):
                self.assertEqual([finding.line() for finding in check({rel: "# 새 주석\n" + real(rel)})], [])

    def test_the_text_of_the_real_files_is_checked_not_only_the_reloaded_data(self):
        """YAML 글자 모양(들여쓰기·앵커·접은 문자열)이 검사를 피하지 못한다 — 진짜 글을 그대로 읽은 결과가 다시 쓴 사본과 같다."""
        for rel in BOTH:
            self.assertEqual(yaml.safe_load(real(rel)), yaml.safe_load(dump(real_data(rel))))


class ProbeShapesTest(unittest.TestCase):
    """감사 BA-S1-4 의 탐침 A·B 를 `workflow_run` 워크플로로 바꾼 가짜들 — 예전 검증기는 모두 0건이었다(`env` 를 거친 식·`script:` 입력). 다른 트리거에서의 같은 모양은 WF-4 확장(다른 묶음)의 몫이다."""

    HEAD = 'name: "[공통] x"\non:\n  workflow_run:\n    workflows: ["[공통] 병합 부탁 PR 자동 만들기"]\n    types: [completed]\n    branches: [main]\npermissions:\n  contents: read\n'
    JOB = "jobs:\n  j:\n    name: 가\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n"

    def test_a_env_indirection_in_a_workflow_run_workflow(self):
        text = self.HEAD + self.JOB.replace("    steps:\n", "    env:\n      TITLE: ${{ github.event.workflow_run.head_commit.message }}\n    steps:\n") + '      - run: echo "${{ env.TITLE }}"\n'
        found = check({"x.yml": text})
        self.assertIn("run 에 `${{", messages(found))
        self.assertIn("env", messages(found))

    def test_b_github_script_with_an_expression(self):
        text = self.HEAD + self.JOB + '      - uses: actions/github-script@v7\n        with:\n          script: |\n            console.log("${{ github.event.workflow_run.display_title }}")\n'
        found = check({"x.yml": text})
        self.assertIn("외부 액션", messages(found))
        self.assertIn("with.script", messages(found))

    def test_c_steps_output_and_f_matrix_in_run(self):
        for expression in ("steps.a.outputs.t", "matrix.k", "needs.p.outputs.m", "vars.X", "github.event.workflow_run.head_sha"):
            with self.subTest(expression):
                text = self.HEAD + self.JOB + '      - run: echo "${{ ' + expression + ' }}"\n'
                self.assertIn("run 에 `${{", messages(check({"x.yml": text})))

    def test_job_level_keys_that_widen_the_reach_of_the_secrets_are_refused_in_any_workflow_run_file(self):
        """허용 목록 밖 파일에도 같은 모양 규칙이 돈다(허용 목록 오류와 별개로) — job 의 container·services·environment·outputs·continue-on-error·uses·strategy 는 시크릿이 닿는 곳을 넓힌다."""
        for key, value in (("container", "evil/image"), ("services", "{x: {image: y}}"), ("environment", "prod"), ("outputs", "{x: y}"), ("continue-on-error", "true"),
                           ("strategy", "{matrix: {k: [a]}}"), ("permissions", "{contents: write}"), ("env", "{X: y}"), ("defaults", "{run: {shell: bash}}")):
            with self.subTest(key):
                text = self.HEAD + self.JOB.replace("    steps:\n", f"    {key}: {value}\n    steps:\n") + "      - run: echo hi\n"
                found = check({"x.yml": text})
                self.assertIn(f"`{key}` 가 있습니다", messages(found))

    def test_a_clean_unknown_workflow_run_file_is_still_only_the_allow_list_error(self):
        text = self.HEAD + self.JOB + "      - uses: actions/checkout@v6\n        with:\n          ref: main\n          persist-credentials: false\n      - run: python -m pipeline.x\n"
        found = check({"x.yml": text})
        self.assertEqual(len(found), 1)
        self.assertIn("허용 목록에 없는 workflow_run", found[0].message)

    def test_the_message_for_a_run_expression_says_why_without_echoing_the_expression(self):
        text = self.HEAD + self.JOB + '      - run: echo "${{ github.event.workflow_run.head_commit.message }}"\n'
        found = check({"x.yml": text})
        joined = messages(found)
        self.assertNotIn("head_commit", joined)                 # 오류 문구가 저장소 글(식)을 되풀이하지 않는다 — 워크플로 명령 줄이 될 수 없다
        self.assertIn("주입", joined)

    def test_an_unknown_file_with_two_jobs_gets_the_same_generic_rules_per_job(self):
        """허용 목록 밖 파일이 job 을 둘 이상 가져도 일반 규칙(시크릿 위치·권한·run 식)은 job 마다 돈다 — 시크릿은 어느 job 이든 마지막 단계 env 의 텔레그램 이름이 아니면 오류."""
        two = (self.HEAD + "jobs:\n  a:\n    name: 가\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - run: echo hi\n"
               "  b:\n    name: 나\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    needs: a\n    steps:\n      - run: echo hi\n        env:\n          X: ${{ secrets.OTHER }}\n")
        found = check({"x.yml": two})
        self.assertIn("시크릿(secrets.*)이 허용되지 않은 자리", messages(found))
        ok = two.replace("          X: ${{ secrets.OTHER }}\n", "          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}\n")
        self.assertNotIn("시크릿(secrets.*)", messages(check({"x.yml": ok})))                # 마지막 단계의 텔레그램 이름은 허용 목록 밖 파일에서는 자리만 본다(허용 목록 오류는 따로 난다)


class LimitsOfTheRuleTest(unittest.TestCase):
    """이 규칙이 못 잡는 것 — 문서(G-A13)에 한계로 적은 것과 같다. 못 잡는 채로 두는 것이 맞는지(다른 규칙·사람 검토가 잡는지) 눈에 보이게 단언한다."""

    def test_a_workflow_run_inside_a_reusable_workflow_call_is_not_seen(self):
        text = ('name: "[공통] x"\non:\n  workflow_call:\npermissions:\n  contents: read\njobs:\n  j:\n    name: 가\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n'
                '    steps:\n      - run: echo hi\n')
        self.assertEqual(check({"x.yml": text}), [])

    def test_a_step_condition_that_only_compares_a_workflow_run_value_is_not_blocked(self):
        """단계의 `if:` 는 식을 평가할 뿐 글을 명령에 끼우지 않는다 — 막지 않는다(막으면 정상 조건까지 막는다). 위험한 것은 run·script 로 들어가는 치환이다. (발송 job 의 `if` 는 정해진 값 하나로 고정돼 있다.)"""
        data = real_data(READY)
        step_of(data, "decide", 2)["if"] = "github.event.workflow_run.head_branch != 'x'"
        self.assertEqual(check({READY: dump(data)}), [])

    def test_the_rule_reads_the_target_names_only_from_its_own_table(self):
        """따라 도는 워크플로 이름이 그 파일의 실제 `name` 과 같은지는 이 규칙이 아니라 tests/test_merge_notice_workflows.py 가 대조한다(이 규칙은 자기 표와만 견준다)."""
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[READY]["workflows"], [yaml.safe_load(real(".github/workflows/auto-pr.yml"))["name"]])
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[CONFIRM]["workflows"], [yaml.safe_load(real(".github/workflows/guardrails.yml"))["name"]])

    def test_the_decide_step_env_names_are_not_pinned_by_the_rule(self):
        """판정 단계 env 의 이름 집합은 이 규칙이 고정하지 않는다(알려진 한계 — 판정 job 에는 시크릿이 없고 tests/test_merge_notice_workflows.py 가 정확한 집합을 고정한다)."""
        data = real_data(CONFIRM)
        step_of(data, "decide", 2)["env"]["PYTHONPATH"] = "/tmp/x"
        self.assertEqual(check({CONFIRM: dump(data)}), [])


if __name__ == "__main__":
    unittest.main()
