"""검증기 규칙 WF-16 시험 — `on: workflow_run` 워크플로의 허용 목록과 모양(감사 BA-S1-4 의 탐침 D, 2026-11-23).

`workflow_run` 은 가지·PR 의 글(`github.event.workflow_run.head_branch`·`head_commit.message`·`display_title`)이 시크릿을 쥔 기본 가지의 파일 안으로 들어오는 길이다. 이 시험은
 1. 허용 목록(`scripts/validate_repo.py` 의 `WORKFLOW_RUN_ALLOWED`)이 병합 알림 워크플로 둘뿐이고 진짜 파일 둘과 저장소의 다른 워크플로 전부가 규칙을 통과하는지,
 2. 허용 목록 밖의 `workflow_run`(탐침 D 꼴 포함)이 오류인지,
 3. 허용된 파일도 한 군데씩 망가뜨리면(쓰기 권한·가지 코드 체크아웃·run·script 의 `${{ }}`·시크릿 위치·외부 액션 …) 모두 오류가 되는지(탐침 A·B 꼴을 `workflow_run` 으로 바꾼 것 포함)
 를 가짜 워크플로로 확인한다. 검증기가 못 보는 것은 마지막 절에 '못 잡는다'고 단언해 둔다.
"""
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


def real(rel):
    return (ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


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


def swap(text, old, new, count=1):
    assert old in text, f"바꿀 글을 찾지 못했다: {old[:50]!r}"
    return text.replace(old, new, count)


SEND_STEP = "      - name: 텔레그램으로 보내기(켬 상태가 on 일 때만)\n"
DECIDE_RUN_READY = "        run: python -m pipeline.auto_notice merge-ready\n"
DECIDE_RUN_CONFIRM = "        run: python -m pipeline.auto_notice merge-confirm\n"
CHECKOUT_REF = "          ref: ${{ github.event.repository.default_branch }}\n"
PERSIST = "          persist-credentials: false\n"


def decide_run(rel):
    return DECIDE_RUN_READY if rel == READY else DECIDE_RUN_CONFIRM


def codes(findings):
    return {finding.check for finding in findings}


def messages(findings):
    return "\n".join(finding.message for finding in findings)


class AllowListTest(unittest.TestCase):
    def test_the_allow_list_is_exactly_the_two_merge_notice_workflows(self):
        self.assertEqual(sorted(vr.WORKFLOW_RUN_ALLOWED), sorted(BOTH))
        self.assertEqual((vr.MERGE_READY_WORKFLOW, vr.MERGE_CONFIRM_WORKFLOW), (READY, CONFIRM))
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[READY]["workflows"], [READY_NAME])
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[CONFIRM]["workflows"], ["[공통] 저장소 규칙·테스트 자동 검사"])
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[CONFIRM]["branches"], ["main"])
        for rel, spec in vr.WORKFLOW_RUN_ALLOWED.items():
            self.assertEqual(spec["send"], "python -m pipeline.auto_notice send", rel)           # 맨 끝(발송 단계)은 두 파일이 같은 명령
            self.assertTrue(spec["decide"].startswith("python -m pipeline.auto_notice merge-"), rel)
            self.assertEqual(set(spec), {"workflows", "branches", "decide", "send"}, rel)
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[READY]["decide"], "python -m pipeline.auto_notice merge-ready")
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[CONFIRM]["decide"], "python -m pipeline.auto_notice merge-confirm")

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
            broken = swap(real(rel), "  contents: read\n", "  contents: write\n")
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
                self.assertEqual(len(found), 1)                                              # 모양은 멀쩡하니 허용 목록 오류 하나뿐

    def test_the_names_must_match_exactly_a_renamed_copy_or_a_directory_trick_is_not_allowed(self):
        text = real(READY)
        for name in ("merge-ready-notice.yaml", "Merge-Ready-Notice.yml", "merge-ready-notice.yml.bak.yml", "merge-ready-notice2.yml", "merge-confirm-notice.yaml"):
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

    def mutations(self, rel):
        text = real(rel)
        decide = decide_run(rel)
        run_line = decide.strip()[len("run: "):]
        yield "contents 쓰기", swap(text, "  contents: read\n", "  contents: write\n"), "쓰기 권한"
        yield "pull-requests 쓰기", swap(text, "  pull-requests: read\n", "  pull-requests: write\n"), "쓰기 권한"
        yield "actions 쓰기", swap(text, "  actions: read\n", "  actions: write\n"), "쓰기 권한"
        yield "issues 쓰기 추가", swap(text, "  actions: read\n", "  actions: read\n  issues: write\n"), "쓰기 권한"
        yield "id-token 쓰기 추가", swap(text, "  actions: read\n", "  actions: read\n  id-token: write\n"), "쓰기 권한"
        yield "checks 쓰기 추가", swap(text, "  actions: read\n", "  actions: read\n  checks: write\n"), "쓰기 권한"
        yield "permissions 를 write-all 글자로", swap(text, "permissions:\n  contents: read\n  pull-requests: read\n  actions: read\n", "permissions: write-all\n"), "permissions"
        yield "permissions 를 read-all 글자로", swap(text, "permissions:\n  contents: read\n  pull-requests: read\n  actions: read\n", "permissions: read-all\n"), "permissions"
        yield "permissions 삭제", swap(text, "permissions:\n  contents: read\n  pull-requests: read\n  actions: read\n", ""), "permissions"
        yield "job 수준 permissions", swap(text, "    timeout-minutes: 10\n", "    timeout-minutes: 10\n    permissions:\n      contents: write\n"), "permissions"
        yield "워크플로 수준 env", swap(text, "concurrency:\n", "env:\n  X: y\nconcurrency:\n"), "env"
        yield "워크플로 수준 defaults", swap(text, "concurrency:\n", "defaults:\n  run:\n    shell: bash\nconcurrency:\n"), "defaults"
        yield "job 수준 env", swap(text, "    timeout-minutes: 10\n", "    timeout-minutes: 10\n    env:\n      X: y\n"), "env"
        yield "workflow_dispatch 트리거 추가", swap(text, "on:\n  workflow_run:\n", "on:\n  workflow_dispatch:\n  workflow_run:\n"), "트리거"
        yield "push 트리거 추가", swap(text, "on:\n  workflow_run:\n", "on:\n  push:\n  workflow_run:\n"), "트리거"
        yield "issue_comment 트리거 추가", swap(text, "on:\n  workflow_run:\n", "on:\n  issue_comment:\n  workflow_run:\n"), "트리거"
        yield "schedule 트리거 추가", swap(text, "on:\n  workflow_run:\n", "on:\n  schedule:\n    - cron: '0 * * * *'\n  workflow_run:\n"), "트리거"
        yield "pull_request 트리거 추가", swap(text, "on:\n  workflow_run:\n", "on:\n  pull_request:\n  workflow_run:\n"), "트리거"
        yield "types 에 requested 추가", swap(text, "    types: [completed]\n", "    types: [completed, requested]\n"), "types"
        yield "types 삭제", swap(text, "    types: [completed]\n", ""), "types"
        yield "가지 필터 삭제", re.sub(r"    branches:\n(?:      - .*\n)+", "", text, count=1), "branches"
        yield "branches-ignore 로 바꿈", re.sub(r"    branches:\n", "    branches-ignore:\n", text, count=1), "branches"
        yield "가지 필터를 모든 가지로", re.sub(r"    branches:\n(?:      - .*\n)+", "    branches:\n      - '**'\n", text, count=1), "가지 필터"
        yield "따라 도는 워크플로를 다른 것으로", re.sub(r'    workflows: \[".*"\]\n', '    workflows: ["다른 워크플로"]\n', text, count=1), "workflows"
        yield "체크아웃 ref 삭제", swap(text, CHECKOUT_REF, ""), "ref"
        yield "체크아웃 ref 를 실행의 커밋으로", swap(text, CHECKOUT_REF, "          ref: ${{ github.event.workflow_run.head_sha }}\n"), "ref"
        yield "체크아웃 ref 를 실행의 가지로", swap(text, CHECKOUT_REF, "          ref: ${{ github.event.workflow_run.head_branch }}\n"), "ref"
        yield "체크아웃 ref 를 PR 병합 참조로", swap(text, CHECKOUT_REF, "          ref: refs/pull/1/merge\n"), "ref"
        yield "체크아웃 ref 를 github.head_ref 로", swap(text, CHECKOUT_REF, "          ref: ${{ github.head_ref }}\n"), "ref"
        yield "체크아웃 ref 를 다른 가지로", swap(text, CHECKOUT_REF, "          ref: develop\n"), "ref"
        yield "체크아웃에 다른 저장소", swap(text, PERSIST, PERSIST + "          repository: evil/other\n"), "허용되지 않은 항목"
        yield "체크아웃에 token", swap(text, PERSIST, PERSIST + "          token: x\n"), "허용되지 않은 항목"
        yield "체크아웃에 submodules", swap(text, PERSIST, PERSIST + "          submodules: true\n"), "허용되지 않은 항목"
        yield "persist-credentials 삭제", swap(text, PERSIST, ""), "persist-credentials"
        yield "persist-credentials true", swap(text, PERSIST, "          persist-credentials: true\n"), "persist-credentials"
        yield "github-script 단계(탐침 B 꼴)", swap(text, "      - uses: actions/setup-python@v6\n", "      - uses: actions/github-script@v7\n        with:\n          script: |\n            console.log('x')\n      - uses: actions/setup-python@v6\n"), "외부 액션"
        yield "github-script 의 script 에 식(탐침 B)", swap(text, "      - uses: actions/setup-python@v6\n", "      - uses: actions/github-script@v7\n        with:\n          script: |\n            console.log(\"${{ github.event.workflow_run.head_commit.message }}\")\n      - uses: actions/setup-python@v6\n"), "script"
        yield "제3자 액션", swap(text, "      - uses: actions/setup-python@v6\n", "      - uses: peter-evans/create-pull-request@v6\n      - uses: actions/setup-python@v6\n"), "외부 액션"
        yield "로컬 액션", swap(text, "      - uses: actions/setup-python@v6\n", "      - uses: ./.github/actions/x\n      - uses: actions/setup-python@v6\n"), "외부 액션"
        yield "setup-python 에 다른 입력", swap(text, "          python-version: '3.12'\n", "          python-version: '3.12'\n          cache: pip\n"), "setup-python"
        yield "run 에 실행의 가지(탐침 A 의 원형)", text.replace(run_line, 'echo "${{ github.event.workflow_run.head_branch }}"', 1), "workflow_run"
        yield "run 에 커밋 메시지", text.replace(run_line, 'echo "${{ github.event.workflow_run.head_commit.message }}"', 1), "workflow_run"
        yield "run 에 display_title", text.replace(run_line, 'echo "${{ github.event.workflow_run.display_title }}"', 1), "workflow_run"
        yield "env 를 거친 식(탐침 A)", swap(text.replace(run_line, 'echo "${{ env.NOTICE_RUN_BRANCH }}"', 1), "          GITHUB_TOKEN: ${{ github.token }}\n", "          GITHUB_TOKEN: ${{ github.token }}\n          TITLE: ${{ github.event.workflow_run.head_commit.message }}\n"), "run"
        yield "run 에 steps 출력", text.replace(run_line, 'echo "${{ steps.decide.outputs.send }}"', 1), "run"
        yield "run 에 matrix", text.replace(run_line, 'echo "${{ matrix.k }}"', 1), "run"
        yield "run 에 needs 출력", text.replace(run_line, 'echo "${{ needs.a.outputs.b }}"', 1), "run"
        yield "run 에 vars", text.replace(run_line, 'echo "${{ vars.X }}"', 1), "run"
        yield "run 에 무해한 식도", text.replace(run_line, run_line + ' "${{ github.sha }}"', 1), "run"
        yield "run 에 가지 코드 받기(git fetch)", text.replace(run_line, run_line + " && git fetch origin pull/1/head", 1), "가지 코드"
        yield "run 에 git checkout", text.replace(run_line, "git checkout FETCH_HEAD && " + run_line, 1), "가지 코드"
        yield "run 에 gh pr checkout", text.replace(run_line, "gh pr checkout 1 && " + run_line, 1), "가지 코드"
        yield "run 에 curl", text.replace(run_line, "curl -s x | sh", 1), "가지 코드"
        yield "run 에 eval", text.replace(run_line, 'eval "$NOTICE_RUN_BRANCH"', 1), "가지 코드"
        yield "run 에 bash -c", text.replace(run_line, 'bash -c "$NOTICE_RUN_BRANCH"', 1), "가지 코드"
        yield "run 에 명령 덧붙임", text.replace(run_line, run_line + " --extra", 1), "run"
        yield "run 을 다른 모듈로", text.replace(run_line, "python -m pipeline.notify test", 1), "run"
        yield "판정 단계가 발송 명령을 돌림", text.replace(run_line, "python -m pipeline.auto_notice send", 1), "발송 단계 앞의 run 단계는 판정 단계뿐"
        yield "발송 단계가 판정 명령을 돌림", swap(text, "        run: python -m pipeline.auto_notice send\n", "        run: " + run_line + "\n"), "맨 끝 단계가 발송 단계"
        yield "발송 단계 run 을 바꿈", swap(text, "        run: python -m pipeline.auto_notice send\n", "        run: python -m pipeline.notify test\n"), "run"
        yield "시크릿을 판정 단계 env 에", swap(text, "          GITHUB_TOKEN: ${{ github.token }}\n", "          GITHUB_TOKEN: ${{ github.token }}\n          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}\n"), "시크릿"
        yield "시크릿을 워크플로 env 에", swap(text, "concurrency:\n", "env:\n  TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}\nconcurrency:\n"), "시크릿"
        yield "시크릿을 job env 에", swap(text, "    timeout-minutes: 10\n", "    timeout-minutes: 10\n    env:\n      TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}\n"), "시크릿"
        yield "시크릿을 체크아웃 with 에", swap(text, PERSIST, PERSIST + "          token: ${{ secrets.TELEGRAM_BOT_TOKEN }}\n"), "시크릿"
        yield "시크릿을 run 에", text.replace(run_line, 'echo "${{ secrets.TELEGRAM_BOT_TOKEN }}"', 1), "시크릿"
        yield "시크릿을 if 에", swap(text, "        if: steps.decide.outputs.send == 'yes'\n", "        if: secrets.TELEGRAM_BOT_TOKEN != ''\n"), "시크릿"
        yield "다른 시크릿을 발송 단계에", swap(text, "          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}\n", "          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}\n          OTHER: ${{ secrets.OTHER_KEY }}\n"), "시크릿"
        yield "GITHUB_TOKEN 시크릿 표기를 발송 단계에", swap(text, "          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}\n", "          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}\n          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}\n"), "시크릿"
        yield "시크릿을 첫 단계에", swap(text, "      - uses: actions/checkout@v6\n", "      - uses: actions/checkout@v6\n        env:\n          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}\n"), "시크릿"
        yield "발송 단계가 맨 끝이 아님", text.rstrip("\n") + "\n\n      - name: 뒤 단계\n        run: python -m pipeline.auto_notice send\n", "시크릿"
        yield "시크릿 이름이 소문자", swap(text, "TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}", "TELEGRAM_BOT_TOKEN: ${{ secrets.telegram_bot_token }}"), "시크릿"
        yield "재사용 워크플로 호출 job", swap(text, "    runs-on: ubuntu-latest\n", "    uses: ./.github/workflows/x.yml\n    secrets: inherit\n    runs-on: ubuntu-latest\n"), "uses"
        yield "strategy 추가", swap(text, "    timeout-minutes: 10\n", "    timeout-minutes: 10\n    strategy:\n      matrix:\n        k: [a]\n"), "strategy"
        yield "실행할 것이 없는 단계", swap(text, "      - uses: actions/setup-python@v6\n", "      - name: 빈 단계\n      - uses: actions/setup-python@v6\n"), "실행할 것이 없는"
        yield "job 에 container", swap(text, "    timeout-minutes: 10\n", "    timeout-minutes: 10\n    container: evil/image\n"), "container"
        yield "job 에 services", swap(text, "    timeout-minutes: 10\n", "    timeout-minutes: 10\n    services:\n      x:\n        image: y\n"), "services"
        yield "job 에 environment", swap(text, "    timeout-minutes: 10\n", "    timeout-minutes: 10\n    environment: prod\n"), "environment"
        yield "job 에 outputs", swap(text, "    timeout-minutes: 10\n", "    timeout-minutes: 10\n    outputs:\n      x: y\n"), "outputs"
        yield "job 에 continue-on-error", swap(text, "    timeout-minutes: 10\n", "    timeout-minutes: 10\n    continue-on-error: true\n"), "continue-on-error"
        yield "runs-on 을 self-hosted 로", swap(text, "    runs-on: ubuntu-latest\n", "    runs-on: self-hosted\n"), "ubuntu-latest"
        yield "runs-on 을 목록으로", swap(text, "    runs-on: ubuntu-latest\n", "    runs-on: [self-hosted, linux]\n"), "ubuntu-latest"
        yield "job 하나 더", text.rstrip("\n") + "\n  second:\n    name: 둘째\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - run: echo hi\n", "정확히 하나"
        yield "단계에 shell", swap(text, "        id: decide\n", "        id: decide\n        shell: python\n"), "허용되지 않은 키"
        yield "단계에 continue-on-error", swap(text, "        id: decide\n", "        id: decide\n        continue-on-error: true\n"), "허용되지 않은 키"
        yield "단계에 working-directory", swap(text, "        id: decide\n", "        id: decide\n        working-directory: /tmp\n"), "허용되지 않은 키"
        yield "단계에 timeout-minutes", swap(text, "        id: decide\n", "        id: decide\n        timeout-minutes: 1\n"), "허용되지 않은 키"
        yield "toJSON(secrets) 를 판정 단계 env 에", swap(text, "          GITHUB_TOKEN: ${{ github.token }}\n", "          GITHUB_TOKEN: ${{ github.token }}\n          ALL: ${{ toJSON(secrets) }}\n"), "시크릿"
        yield "toJSON(secrets) 를 발송 단계 env 에도", swap(text, "          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}\n", "          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}\n          ALL: ${{ toJSON(secrets) }}\n"), "시크릿"
        yield "format 으로 secrets 를 넘김", swap(text, "          GITHUB_TOKEN: ${{ github.token }}\n", "          GITHUB_TOKEN: ${{ github.token }}\n          ALL: ${{ format('{0}', secrets) }}\n"), "시크릿"
        yield "시크릿을 대괄호 표기로", swap(text, "          GITHUB_TOKEN: ${{ github.token }}\n", "          GITHUB_TOKEN: ${{ github.token }}\n          T: ${{ secrets['TELEGRAM_BOT_TOKEN'] }}\n"), "시크릿"

    def test_every_mutation_of_both_real_workflows_is_caught_by_wf16(self):
        count = 0
        for rel in BOTH:
            original = real(rel)
            self.assertEqual(check({rel: original}), [], rel)
            for label, mutated, needle in self.mutations(rel):
                count += 1
                with self.subTest(f"{Path(rel).name}: {label}"):
                    self.assertNotEqual(mutated, original, f"변이가 글을 바꾸지 못했다: {label}")
                    found = [finding for finding in check({rel: mutated}) if finding.check == "WF-16"]
                    self.assertTrue(found, f"살아남은 변이: {label}")
                    self.assertTrue(all(finding.level == "ERROR" for finding in found))
                    self.assertIn(needle, messages(found), f"{label}: 기대한 문구 '{needle}' 가 없다")
        self.assertGreaterEqual(count, 2 * 70)

    def test_harmless_edits_still_pass(self):
        """규칙이 지나치게 넓어 정상 편집까지 막지 않는지: 단계 이름·주석·env 순서·ref 를 main 글자로·fetch-depth 추가·시간 제한 변경은 통과한다."""
        for rel in BOTH:
            text = real(rel)
            harmless = {
                "단계 이름": swap(text, "name: 텔레그램으로 보내기(켬 상태가 on 일 때만)", "name: 다른 이름"),
                "주석 추가": "# 새 주석\n" + text,
                "ref 를 main 글자로": swap(text, CHECKOUT_REF, "          ref: main\n"),
                "fetch-depth 추가": swap(text, PERSIST, PERSIST + "          fetch-depth: 1\n"),
                "시간 제한 변경": swap(text, "timeout-minutes: 10", "timeout-minutes: 7"),
                "python 버전 변경": swap(text, "python-version: '3.12'", "python-version: '3.10'"),
                "concurrency 이름 변경": swap(text, "group: merge-", "group: merged-"),
                "단계 env 에 값 추가": swap(text, "          NOTICE_RUN_ID:", "          NOTICE_EXTRA: ${{ github.run_id }}\n          NOTICE_RUN_ID:"),
            }
            for label, mutated in harmless.items():
                with self.subTest(f"{Path(rel).name}: {label}"):
                    self.assertNotEqual(mutated, text)
                    self.assertEqual([finding.line() for finding in check({rel: mutated})], [])


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
                text = self.HEAD + self.JOB + f"    {key}: {value}\n    steps:\n      - run: echo hi\n"
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


class LimitsOfTheRuleTest(unittest.TestCase):
    """이 규칙이 못 잡는 것 — 문서(G-A13)에 한계로 적은 것과 같다. 못 잡는 채로 두는 것이 맞는지(다른 규칙·사람 검토가 잡는지) 눈에 보이게 단언한다."""

    def test_a_workflow_run_inside_a_reusable_workflow_call_is_not_seen(self):
        text = ('name: "[공통] x"\non:\n  workflow_call:\npermissions:\n  contents: read\njobs:\n  j:\n    name: 가\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n'
                '    steps:\n      - run: echo hi\n')
        self.assertEqual(check({"x.yml": text}), [])

    def test_an_if_condition_that_only_compares_a_workflow_run_value_is_not_blocked(self):
        """`if:` 는 식을 평가할 뿐 글을 명령에 끼우지 않는다 — 막지 않는다(막으면 정상 조건까지 막는다). 위험한 것은 run·script 로 들어가는 치환이다."""
        text = swap(real(READY), "        if: steps.decide.outputs.send == 'yes'\n", "        if: steps.decide.outputs.send == 'yes' && github.event.workflow_run.head_branch != 'x'\n")
        self.assertEqual(check({READY: text}), [])

    def test_the_rule_reads_the_target_names_only_from_its_own_table(self):
        """따라 도는 워크플로 이름이 그 파일의 실제 `name` 과 같은지는 이 규칙이 아니라 tests/test_merge_notice_workflows.py 가 대조한다(이 규칙은 자기 표와만 견준다)."""
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[READY]["workflows"], [yaml.safe_load(real(".github/workflows/auto-pr.yml"))["name"]])
        self.assertEqual(vr.WORKFLOW_RUN_ALLOWED[CONFIRM]["workflows"], [yaml.safe_load(real(".github/workflows/guardrails.yml"))["name"]])


if __name__ == "__main__":
    unittest.main()
