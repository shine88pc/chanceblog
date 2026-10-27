"""chanceblog.yml 의 승인 흐름(publish_flow) 구조 시험: 발행 흐름 확인 단계, 단계 조건의 진리표, 권한, 직접 게시(direct) 경로가 예전과 같은 뜻인지.
GitHub Actions 를 실행할 수 없는 환경에서도 YAML 식을 직접 평가하고(test_workflow_names.py 의 해석기), 단계의 셸 스크립트를 가짜 python 으로 돌려 본다.
"""
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from itertools import product
from pathlib import Path

import _bootstrap  # noqa: F401
from test_workflow_names import context, load, render

OLD_COMMIT_IF = "${{ !(github.event_name == 'workflow_dispatch' && inputs.dry_run) }}"
EVENTS = (("schedule", None), ("workflow_dispatch", {"dry_run": True, "real_ai": False}), ("workflow_dispatch", {"dry_run": True, "real_ai": True}),
          ("workflow_dispatch", {"dry_run": False, "real_ai": False}), ("workflow_dispatch", {"dry_run": False, "real_ai": True}),
          ("workflow_dispatch", {"dry_run": False}), ("workflow_dispatch", {}))


def steps_of(name="chanceblog.yml"):
    return load(name)["jobs"]["build"]["steps"]


def by_id(step_id):
    return next(s for s in steps_of() if s.get("id") == step_id)


def deliver_step():
    return next(s for s in steps_of() if "pipeline.draft_flow deliver" in s.get("run", ""))


def pages_step():
    return next(s for s in steps_of() if "gh workflow run pages.yml" in s.get("run", ""))


def generator_step():
    return next(s for s in steps_of() if s.get("run") == "python generator.py")


def evaluate(condition, event, inputs, flow, pushed=""):
    """단계의 if 조건을 GitHub 규칙대로 평가한다. flow: 발행 흐름 확인 단계의 출력, pushed: 커밋 단계의 pushed 출력."""
    text = condition if "${{" in condition else "${{ " + condition + " }}"
    ctx = context(event, inputs)
    ctx["steps"] = {"flow": {"outputs": {"flow": flow}}, "commit": {"outputs": {"pushed": pushed}}}
    return render(text, ctx) == "true"


class FlowStepTest(unittest.TestCase):
    def test_the_flow_step_comes_after_setup_python_and_before_everything_that_writes(self):
        names = [s.get("name") or s.get("uses") for s in steps_of()]
        ids = [s.get("id") for s in steps_of()]
        self.assertEqual(ids[names.index("발행 흐름 확인 (레지스트리 publish_flow)")], "flow")
        flow_index = ids.index("flow")
        self.assertEqual(steps_of()[flow_index - 1]["uses"], "actions/setup-python@v5")
        generator_index = steps_of().index(generator_step())
        self.assertLess(flow_index, generator_index)
        self.assertLess(generator_index, ids.index("commit"))
        self.assertLess(ids.index("commit"), steps_of().index(pages_step()))
        self.assertLess(steps_of().index(pages_step()), steps_of().index(deliver_step()))
        # 알림 단계(텔레그램 새 글, 통합)가 항상 맨 끝이다. 승인 PR 올리기 단계는 그 바로 앞이다.
        self.assertEqual(steps_of()[-2], deliver_step())
        self.assertEqual(steps_of()[-1].get("name"), "텔레그램 알림(새 글)")

    def test_the_flow_step_uses_the_registry_cli_and_stops_on_error(self):
        run = by_id("flow")["run"]
        self.assertIn("set -euo pipefail", run)
        self.assertIn("flow=$(python -m pipeline.draft_flow flow)", run)         # 변수에 먼저 받아 set -e 가 실패를 잡게 한다(echo 안의 명령 치환은 실패를 가린다)
        self.assertIn('echo "flow=${flow}" >> "$GITHUB_OUTPUT"', run)
        self.assertNotIn("|| true", run)
        self.assertNotIn("continue-on-error", by_id("flow"))
        self.assertNotIn("if", by_id("flow"))                                      # 연습 실행에서도 항상 돈다(쓰기가 없다)

    def run_flow_script(self, fake_flow, fake_exit=0):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash 가 없다")
        script = by_id("flow")["run"]
        with tempfile.TemporaryDirectory() as tmp:
            shim = Path(tmp) / "python"
            shim.write_text('#!/bin/sh\n[ "$1 $2 $3" = "-m pipeline.draft_flow flow" ] || { echo "예상 밖 호출: $*" >&2; exit 9; }\n'
                            'echo "$FAKE_FLOW"\nexit "${FAKE_EXIT:-0}"\n', encoding="utf-8", newline="\n")
            shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            out, summary = Path(tmp) / "output.txt", Path(tmp) / "summary.md"
            out.write_text("", encoding="utf-8")
            summary.write_text("", encoding="utf-8")
            env = {**os.environ, "PATH": tmp + os.pathsep + os.environ.get("PATH", ""), "GITHUB_OUTPUT": out.as_posix(),
                   "GITHUB_STEP_SUMMARY": summary.as_posix(), "FAKE_FLOW": fake_flow, "FAKE_EXIT": str(fake_exit)}
            proc = subprocess.run([bash, "-e", "-c", script], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            return proc, out.read_text(encoding="utf-8"), summary.read_text(encoding="utf-8")

    def test_direct_writes_the_output_and_nothing_to_the_summary(self):
        proc, output, summary = self.run_flow_script("direct")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(output, "flow=direct\n")
        self.assertEqual(summary, "")                                              # direct 의 실행 요약은 예전과 같다
        self.assertEqual(proc.stdout, "")

    def test_pr_writes_the_output_and_a_small_summary_block(self):
        proc, output, summary = self.run_flow_script("pr")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(output, "flow=pr\n")
        self.assertEqual(summary, "### 발행 흐름\n- 승인 흐름(pr): 글은 초안 브랜치와 PR 로 올라가고, 병합하면 공개됩니다(닫으면 폐기)\n")

    def test_a_failing_cli_fails_the_step_and_writes_no_output(self):
        proc, output, summary = self.run_flow_script("", fake_exit=1)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual((output, summary), ("", ""))


class ConditionTruthTableTest(unittest.TestCase):
    def test_in_direct_flow_the_commit_condition_is_exactly_the_old_one(self):
        old = OLD_COMMIT_IF
        new = by_id("commit")["if"]
        self.assertNotEqual(new, old)
        for (event, inputs), flow in product(EVENTS, ("direct", "")):               # 빈 값은 출력이 없을 때(건너뛴 단계)다
            with self.subTest(event=event, inputs=inputs, flow=flow):
                self.assertEqual(evaluate(new, event, inputs, flow), evaluate(old, event, inputs, flow))

    def test_the_old_condition_means_everything_except_a_practice_run(self):
        for (event, inputs) in EVENTS:
            practice = event == "workflow_dispatch" and bool((inputs or {}).get("dry_run"))
            self.assertEqual(evaluate(OLD_COMMIT_IF, event, inputs, "direct"), not practice, (event, inputs))

    def test_in_pr_flow_nothing_is_committed_to_main_by_the_old_step(self):
        for (event, inputs) in EVENTS:
            self.assertFalse(evaluate(by_id("commit")["if"], event, inputs, "pr"), (event, inputs))

    def test_the_deploy_request_follows_the_commit_step_only(self):
        condition = pages_step()["if"]
        self.assertEqual(condition, "steps.commit.outputs.pushed == 'true'")
        self.assertTrue(evaluate(condition, "schedule", None, "direct", pushed="true"))
        self.assertFalse(evaluate(condition, "schedule", None, "direct", pushed=""))
        self.assertFalse(evaluate(condition, "schedule", None, "pr", pushed=""))     # 승인 흐름에서는 커밋 단계가 건너뛰어져 배포 요청도 없다

    def test_the_deliver_step_runs_only_in_pr_flow_and_never_in_a_practice_run(self):
        condition = deliver_step()["if"]
        for (event, inputs), flow in product(EVENTS, ("direct", "pr", "")):
            practice = event == "workflow_dispatch" and bool((inputs or {}).get("dry_run"))
            expected = flow == "pr" and not practice
            self.assertEqual(evaluate(condition, event, inputs, flow), expected, (event, inputs, flow))

    def test_exactly_one_of_commit_and_deliver_runs_for_a_real_run(self):
        for (event, inputs), flow in product(EVENTS, ("direct", "pr")):
            practice = event == "workflow_dispatch" and bool((inputs or {}).get("dry_run"))
            commit, deliver = evaluate(by_id("commit")["if"], event, inputs, flow), evaluate(deliver_step()["if"], event, inputs, flow)
            self.assertEqual((commit, deliver), (False, False) if practice else ((True, False) if flow == "direct" else (False, True)), (event, inputs, flow))


class DeliverStepTest(unittest.TestCase):
    def test_it_runs_the_cli_and_nothing_else(self):
        step = deliver_step()
        self.assertEqual(step["run"], "python -m pipeline.draft_flow deliver")
        self.assertRegex(step["name"], r"[가-힣]")
        for forbidden in ("gh workflow run", "git push", "git commit", "|| true"):
            self.assertNotIn(forbidden, step["run"])

    def test_it_gets_only_the_github_token_the_practice_switch_and_the_pause_switch(self):
        env = deliver_step()["env"]
        self.assertEqual(set(env), {"GITHUB_TOKEN", "DRY_RUN", "PIPELINE_PAUSE"})
        self.assertEqual(env["GITHUB_TOKEN"], "${{ secrets.GITHUB_TOKEN }}")
        self.assertEqual(env["PIPELINE_PAUSE"], "${{ vars.PIPELINE_PAUSE }}")
        for (event, inputs) in EVENTS:
            practice = event == "workflow_dispatch" and bool((inputs or {}).get("dry_run"))
            self.assertEqual(render(env["DRY_RUN"], context(event, inputs)), "1" if practice else "0", (event, inputs))

    def test_the_generator_step_does_not_get_the_github_token(self):
        """AI 출력과 외부 피드를 읽는 생성기 프로세스에는 저장소 쓰기 토큰을 넘기지 않는다(올리기 단계만 받는다)."""
        env = generator_step()["env"]
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertFalse(any("GITHUB_TOKEN" in str(v) for v in env.values()))
        self.assertNotIn("GEMINI_API_KEY", deliver_step()["env"])

    def test_the_other_steps_get_no_new_secrets(self):
        deliver = deliver_step()
        for step in steps_of():
            if step != deliver:
                self.assertNotIn("GITHUB_TOKEN", step.get("env", {}))
        self.assertEqual(pages_step()["env"], {"GH_TOKEN": "${{ secrets.GITHUB_TOKEN }}"})          # 배포 요청 단계의 GH_TOKEN 은 예전부터다

    def test_it_passes_no_outside_text_into_the_script(self):
        text = deliver_step()["run"] + str(deliver_step().get("env"))
        for dangerous in ("github.event.issue", "github.event.pull_request", "github.head_ref", "github.event.comment", "inputs.topic"):
            self.assertNotIn(dangerous, text)


class WorkflowGlobalsTest(unittest.TestCase):
    def test_permissions_add_only_pull_requests_write(self):
        self.assertEqual(load("chanceblog.yml")["permissions"], {"contents": "write", "actions": "write", "pull-requests": "write"})

    def test_the_concurrency_group_and_the_job_limits_are_the_old_ones(self):
        wf = load("chanceblog.yml")
        self.assertEqual(wf["concurrency"], {"group": "chanceblog", "cancel-in-progress": False})
        self.assertEqual(wf["jobs"]["build"]["timeout-minutes"], 20)
        self.assertEqual(wf["jobs"]["build"]["runs-on"], "ubuntu-latest")
        self.assertEqual(wf["on"]["schedule"], [{"cron": "17 * * * *"}, {"cron": "47 * * * *"}])
        self.assertEqual(list(wf["on"]["workflow_dispatch"]["inputs"]), ["dry_run", "real_ai"])                # 새 입력 없음: 승인 흐름은 레지스트리가 정한다
        self.assertEqual(wf["jobs"]["build"]["name"], "글 작성·게시")

    def test_python_stays_3_10_for_the_engine(self):
        setup = next(s for s in steps_of() if str(s.get("uses", "")).startswith("actions/setup-python"))
        self.assertEqual(setup["with"]["python-version"], "3.10")

    def test_the_generator_step_is_unchanged(self):
        step = generator_step()
        self.assertEqual(set(step["env"]), {"GEMINI_API_KEY", "UNSPLASH_ACCESS_KEY", "EVENT_NAME", "DRY_RUN", "PIPELINE_PAUSE"})
        self.assertEqual(step["name"], "AI 블로그 제너레이터 실행")
        self.assertNotIn("id", step)
        self.assertNotIn("if", step)

    def test_the_commit_script_is_unchanged(self):
        script = by_id("commit")["run"]
        for line in ('git config user.name "github-actions[bot]"', "git add -A", 'git commit -m "🤖 자동 포스팅/이미지 수정"',
                     'git pull --rebase origin "${GITHUB_REF_NAME}"', "git push", 'echo "pushed=true" >> "$GITHUB_OUTPUT"'):
            self.assertIn(line, script)

    def test_the_image_fix_workflow_is_untouched_by_the_draft_flow(self):
        wf = load("chance-fix-images.yml")
        self.assertEqual(wf["permissions"], {"contents": "write", "actions": "write"})
        text = (Path(_bootstrap.ROOT) / ".github" / "workflows" / "chance-fix-images.yml").read_text(encoding="utf-8")
        for needle in ("draft_flow", "publish_flow", "steps.flow"):
            self.assertNotIn(needle, text)

    def test_the_watchdog_may_read_pull_requests_and_nothing_more(self):
        permissions = load("watchdog.yml")["permissions"]
        self.assertEqual(permissions, {"contents": "read", "actions": "read", "pull-requests": "read", "issues": "write"})

    def test_pages_deploy_is_untouched(self):
        wf = load("pages.yml")
        self.assertEqual(wf["on"]["push"]["branches"], ["main"])
        self.assertEqual(wf["permissions"], {"contents": "read"})
        self.assertEqual(list(wf["jobs"]), ["build", "deploy", "verify"])
        text = (Path(_bootstrap.ROOT) / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertNotIn("draft", text)

    def test_the_steps_that_call_the_registry_never_use_untrusted_expressions(self):
        for step in steps_of():
            run = step.get("run", "")
            self.assertIsNone(re.search(r"\$\{\{\s*(?:github\.event\.(?:issue|comment|pull_request|head_commit)|github\.head_ref)", run))


if __name__ == "__main__":
    unittest.main()
