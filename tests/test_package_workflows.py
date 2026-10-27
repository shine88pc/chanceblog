"""초안 패키지 래퍼 워크플로(tistory.yml·naver.yml) 구조 시험.

GitHub Actions 를 실행할 수 없는 환경에서도 이름·run-name·트리거·권한·시크릿·동시성·연습 실행 기본값·계획 단계가 의도대로인지 YAML 로 확인한다.
(문법·표현식은 CI 의 actionlint 가 따로 본다.)
"""
import json
import re
import tempfile
import unittest

import yaml

import _bootstrap  # noqa: F401
from package_helpers import make_package_root, package_entry, registry_of
from pipeline import plan, registry
from test_workflow_names import context, load, render, workflow_paths

REAL = _bootstrap.ROOT
WORKFLOWS = REAL / ".github" / "workflows"
SPEC = {
    "tistory": {"name": "[티스토리] 초안 패키지 만들기", "cron": "20 5 * * *", "label": "티스토리"},
    "naver": {"name": "[네이버] 초안 패키지 만들기", "cron": "20 6 * * *", "label": "네이버"},
}
BOTH = tuple(SPEC)


def text_of(platform):
    return (WORKFLOWS / f"{platform}.yml").read_text(encoding="utf-8")


def code_lines(text):
    """주석 줄을 뺀 글(스크립트의 # 주석 설명이 시험 대상 문자열을 담고 있어도 오탐하지 않게)."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def steps_of(workflow, job):
    return workflow["jobs"][job]["steps"]


class NamesAndTriggersTest(unittest.TestCase):
    def test_names_follow_the_channel_prefix_rule(self):
        for platform in BOTH:
            workflow, spec = load(f"{platform}.yml"), SPEC[platform]
            self.assertEqual(workflow["name"], spec["name"], platform)
            self.assertEqual(registry.name_label(workflow["name"]), spec["label"], platform)
            self.assertEqual(registry.name_label(workflow["run-name"]), spec["label"], platform)
            self.assertEqual(registry.PACKAGE_PLATFORMS[platform], spec["label"], platform)

    def test_run_names_show_scheduled_manual_and_practice_runs(self):
        for platform in BOTH:
            workflow, label = load(f"{platform}.yml"), SPEC[platform]["label"]

            def title(event, inputs=None):
                return render(workflow["run-name"], context(event, inputs))
            self.assertEqual(title("schedule"), f"[{label}] 초안 패키지 · 정기", platform)
            self.assertEqual(title("workflow_dispatch", {"dry_run": True}), f"[{label}] 초안 패키지 · 수동(연습: 이슈 안 만듦)", platform)
            self.assertEqual(title("workflow_dispatch", {"dry_run": False}), f"[{label}] 초안 패키지 · 수동(초안 이슈 만들기)", platform)
            self.assertEqual(title("schedule", {"dry_run": True}), f"[{label}] 초안 패키지 · 정기", platform)        # 정기 실행은 연습이 아니다

    def test_only_a_daily_schedule_and_the_manual_trigger(self):
        for platform in BOTH:
            workflow, spec = load(f"{platform}.yml"), SPEC[platform]
            self.assertEqual(set(workflow["on"]), {"schedule", "workflow_dispatch"}, platform)
            self.assertEqual(workflow["on"]["schedule"], [{"cron": spec["cron"]}], platform)
            minute, hour, day, month, weekday = spec["cron"].split()
            self.assertTrue(minute.isdigit() and hour.isdigit() and (day, month, weekday) == ("*", "*", "*"), "하루에 한 번")

    def test_the_cron_does_not_collide_with_any_other_workflow(self):
        crons = {}
        for path in workflow_paths():
            for item in load(path.name)["on"].get("schedule") or []:
                crons.setdefault(item["cron"], []).append(path.name)
        for platform, spec in SPEC.items():
            self.assertEqual(crons[spec["cron"]], [f"{platform}.yml"], spec["cron"])          # 같은 시각에 도는 다른 워크플로가 없다
            self.assertNotEqual(tuple(spec["cron"].split()[:2]), ("0", "2"))                  # Blogger(KST 11시)와도 겹치지 않는다
        self.assertNotEqual(SPEC["tistory"]["cron"], SPEC["naver"]["cron"])

    def test_the_cron_matches_the_registry_fixture_the_operator_will_copy(self):
        for platform, spec in SPEC.items():
            self.assertEqual(package_entry(platform)["schedule"]["cron"], spec["cron"])

    def test_inputs_have_the_blogger_style_names_and_practice_is_on_by_default(self):
        for platform in BOTH:
            workflow, spec = load(f"{platform}.yml"), SPEC[platform]
            inputs = workflow["on"]["workflow_dispatch"]["inputs"]
            self.assertEqual(list(inputs), ["blog", "topic", "dry_run"], platform)           # publish·auth_check 는 이 채널에 없다
            self.assertEqual((inputs["dry_run"]["type"], inputs["dry_run"]["default"]), ("boolean", True), platform)
            for name in ("blog", "topic"):
                self.assertEqual(inputs[name]["type"], "string")
                self.assertFalse(inputs[name].get("required"))
            description = inputs["dry_run"]["description"]
            for needle in ("연습 실행(기본 켜짐)", "Gemini와 GitHub를 호출하지 않으며", "체크를 풀면", "초안 이슈 1개", "하루 상한"):
                self.assertIn(needle, description, platform)
            self.assertIn(spec["label"], inputs["blog"]["description"])


class SecurityTest(unittest.TestCase):
    def test_permissions_are_minimal_and_issues_write_is_only_on_the_generate_job(self):
        for platform in BOTH:
            workflow = load(f"{platform}.yml")
            self.assertEqual(workflow["permissions"], {"contents": "read"}, platform)
            self.assertNotIn("permissions", workflow["jobs"]["plan"], platform)
            self.assertEqual(workflow["jobs"]["generate"]["permissions"], {"contents": "write", "issues": "write"}, platform)   # PR·actions 권한 없음

    def test_the_only_secrets_are_the_gemini_key_and_the_default_token(self):
        for platform in BOTH:
            workflow = load(f"{platform}.yml")
            refs = set(re.findall(r"secrets(?:\.[A-Za-z_]+|\[[^\]]+\])", code_lines(text_of(platform))))
            self.assertEqual(refs, {"secrets.GITHUB_TOKEN", "secrets[matrix.secret_llm_api_key]"}, platform)
            env = next(step for step in steps_of(workflow, "generate") if step.get("run", "").startswith("python -m pipeline.run"))["env"]
            self.assertEqual(env["PIPELINE_SECRET_LLM_API_KEY"], "${{ secrets[matrix.secret_llm_api_key] }}", platform)
            self.assertEqual(env["GITHUB_TOKEN"], "${{ secrets.GITHUB_TOKEN }}", platform)

    def test_no_account_information_appears_anywhere_in_the_environment(self):
        for platform in BOTH:
            workflow, names = load(f"{platform}.yml"), set()
            for job in workflow["jobs"].values():
                names |= set(job.get("env") or {})
                for step in job.get("steps", []):
                    names |= set(step.get("env") or {})
            for name in names:
                for word in registry.ACCOUNT_SECRET_WORDS + ("BLOG_ID", "CLIENT", "REFRESH", "OAUTH"):
                    self.assertNotIn(word, name.upper(), name)
            self.assertEqual(names, {"ONLY_BLOG", "PIPELINE_PAUSE", "DRY_RUN", "BLOG_KEY", "BLOGGER_TOPIC", "GITHUB_TOKEN", "PIPELINE_SECRET_LLM_API_KEY",
                                     "HISTORY_FILE", "CONTENT_DIR"}, platform)

    def test_untrusted_inputs_reach_the_scripts_only_through_env(self):
        for platform in BOTH:
            for job in load(f"{platform}.yml")["jobs"].values():
                for step in job.get("steps", []):
                    self.assertNotIn("${{", step.get("run", ""), (platform, step.get("name")))

    def test_actions_are_the_first_party_ones_pinned_by_major_version(self):
        for platform in BOTH:
            workflow = load(f"{platform}.yml")
            uses = {step["uses"] for job in workflow["jobs"].values() for step in job.get("steps", []) if "uses" in step}
            self.assertEqual(uses, {"actions/checkout@v4", "actions/setup-python@v5"}, platform)

    def test_the_kill_switch_and_practice_flag_are_wired_like_the_blogger_workflow(self):
        blogger = load("blogger.yml")["jobs"]["generate"]["env"]
        for platform in BOTH:
            env = load(f"{platform}.yml")["jobs"]["generate"]["env"]
            self.assertEqual(env["PIPELINE_PAUSE"], "${{ vars.PIPELINE_PAUSE }}", platform)
            self.assertEqual(env["DRY_RUN"], "${{ github.event.inputs.dry_run == 'true' && 'true' || 'false' }}", platform)
            self.assertEqual((env["PIPELINE_PAUSE"], env["DRY_RUN"]), (blogger["PIPELINE_PAUSE"], blogger["DRY_RUN"]), platform)


class PlanAndRunTest(unittest.TestCase):
    def test_the_plan_step_selects_only_this_platform_and_reports_zero_targets_as_green(self):
        for platform in BOTH:
            workflow = load(f"{platform}.yml")
            run = next(s for s in steps_of(workflow, "plan") if s.get("id") == "plan")["run"]
            script = code_lines(run)
            self.assertIn(f"args=(--platform {platform})", script, platform)
            self.assertIn('args+=(--only "$ONLY_BLOG")', script, platform)
            self.assertNotIn("--include-off", script, platform)                              # 정지한 블로그는 대상이 아니다
            self.assertIn("set -euo pipefail", script, platform)
            self.assertIn('matrix=$(python -m pipeline.plan "${args[@]}")', script, platform)   # 먼저 변수에 받아 set -e 가 실패를 잡게 한다
            self.assertNotIn('echo "matrix=$(', script, platform)
            zero = script.split('if [ "$count" = "0" ]; then')[1]
            self.assertIn("::notice::", zero, platform)
            self.assertIn("대상 0개", zero, platform)
            self.assertIn("GITHUB_STEP_SUMMARY", zero, platform)
            self.assertNotIn("exit", zero, platform)                                          # 0개는 오류가 아니다
            self.assertEqual(workflow["jobs"]["generate"]["if"], "needs.plan.outputs.count != '0'", platform)
            self.assertNotIn("pip install", json.dumps(workflow["jobs"]["plan"]), platform)    # plan 은 표준 라이브러리만 쓴다

    def test_the_generate_job_runs_one_blog_at_a_time_with_a_per_blog_concurrency_group(self):
        for platform in BOTH:
            workflow = load(f"{platform}.yml")
            job = workflow["jobs"]["generate"]
            self.assertEqual(job["needs"], "plan", platform)
            self.assertEqual(job["strategy"], {"fail-fast": False, "max-parallel": 1, "matrix": "${{ fromJSON(needs.plan.outputs.matrix) }}"}, platform)
            self.assertEqual(job["concurrency"], {"group": platform + "-${{ matrix.key }}", "cancel-in-progress": False}, platform)
            self.assertEqual((workflow["jobs"]["plan"]["timeout-minutes"], job["timeout-minutes"]), (5, 15), platform)

    def test_every_matrix_field_the_workflow_reads_exists_in_the_plan_output(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        entry = plan.build_matrix(registry_of(make_package_root(tmp.name)), "tistory")["include"][0]
        for platform in BOTH:
            used = set(re.findall(r"matrix\.([a-z_]+)", text_of(platform)))
            self.assertLessEqual(used, set(entry), (platform, used - set(entry)))
            self.assertEqual(used, {"key", "history", "content_dir", "secret_llm_api_key"}, platform)

    def test_the_run_step_and_the_commit_step_do_what_the_blogger_workflow_does(self):
        for platform in BOTH:
            steps = steps_of(load(f"{platform}.yml"), "generate")
            run_step = next(s for s in steps if s.get("run", "").startswith("python -m pipeline.run"))
            self.assertEqual(run_step["run"], 'python -m pipeline.run --blog "$BLOG_KEY"', platform)
            self.assertEqual(run_step["env"]["BLOG_KEY"], "${{ matrix.key }}", platform)
            self.assertEqual(run_step["env"]["BLOGGER_TOPIC"], "${{ github.event.inputs.topic }}", platform)
            self.assertNotIn("BLOGGER_PUBLISH", run_step["env"], platform)                    # 게시 방식 선택은 이 채널에 없다
            self.assertNotIn("BLOGGER_AUTH_CHECK", run_step["env"], platform)
            commit = next(s for s in steps if s.get("name") == "변경 사항 커밋")
            self.assertEqual(commit["if"], "${{ !cancelled() }}", platform)                    # 생성 단계가 실패해도 기록·사본은 남긴다
            script = commit["run"]
            self.assertIn('if [ "${DRY_RUN:-false}" = "true" ]; then echo "DRY_RUN — 커밋 생략"; exit 0; fi', script, platform)
            self.assertIn('for p in "$HISTORY_FILE" "$CONTENT_DIR"; do', script, platform)
            self.assertIn('git add -- "$p"', script, platform)
            self.assertNotIn("git add .", script, platform)
            self.assertNotIn("git add -A", script, platform)
            self.assertIn('git commit -m "🤖 [${BLOG_KEY}] 초안 패키지 기록"', script, platform)
            self.assertIn("for i in 1 2 3; do", script, platform)
            self.assertIn("git pull --rebase origin", script, platform)
            self.assertNotIn("--force", script, platform)
            self.assertNotIn("|| true", script, platform)
            self.assertEqual(commit["env"], {"BLOG_KEY": "${{ matrix.key }}", "HISTORY_FILE": "${{ matrix.history }}", "CONTENT_DIR": "${{ matrix.content_dir }}"})
            install = next(s for s in steps if s.get("name") == "의존성 설치")
            self.assertIn("pip install -r requirements-pipeline.txt", install["run"], platform)
            self.assertEqual(install["run"].count("pip install"), 2, platform)                # pip 업그레이드와 요구 파일 하나뿐

    def test_the_job_and_step_names_are_korean_and_have_no_prefix(self):
        for platform in BOTH:
            for job in load(f"{platform}.yml")["jobs"].values():
                self.assertRegex(job["name"], "[가-힣]")
                self.assertIsNone(registry.name_label(job["name"]))
                for step in job["steps"]:
                    if "name" in step:
                        self.assertRegex(step["name"], "[가-힣]", step["name"])

    def test_the_two_workflows_differ_only_in_the_channel(self):
        def normalize(platform):
            text = json.dumps(load(f"{platform}.yml"), ensure_ascii=False, sort_keys=True)
            text = text.replace(SPEC[platform]["cron"], "CRON").replace(SPEC[platform]["label"], "LABEL").replace(platform, "PLATFORM")
            return re.sub(r"네이버 블로그|티스토리 블로그", "LABEL 블로그", text)
        self.assertEqual(normalize("tistory"), normalize("naver"))

    def test_the_workflow_files_are_utf8_without_bom_and_end_with_a_newline(self):
        for platform in BOTH:
            raw = (WORKFLOWS / f"{platform}.yml").read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertTrue(raw.endswith(b"\n"))
            yaml.safe_load(raw.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
