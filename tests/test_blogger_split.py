"""Blogger 워크플로 분리(작업 D) 시험: blogger.yml 은 재사용 워크플로(`on: workflow_call`)이고, 채널별 래퍼 blogger-en.yml(영문)·blogger-ko.yml(한글)이 자기 예약·수동 입력·
동시 실행 줄·시크릿 이름으로 `with:`·`secrets:` 를 명시해 부른다. 네트워크·GitHub Actions 없이 YAML 을 직접 읽고 표현식을 평가해 확인한다(문법·입력 형은 CI 의 actionlint 도 본다).

구성
  1) 공용 워크플로: 직접 실행하는 트리거가 없다, 입력·시크릿 정의, 부르는 쪽 이벤트를 읽지 않는다, 단계·권한·시간 제한이 그대로다.
  2) 래퍼: 이름·run-name 접두사(N7: 괄호 설명 없음), 예약·입력·권한·동시 실행 줄, 레지스트리와의 연결, 두 래퍼가 채널 값 말고는 같다.
  3) 표현식 동등성: 모든 이벤트·입력 조합에서 (래퍼 with → 공용 워크플로 환경변수)가 분리 전 blogger.yml 이 만든 값과 같다.
  4) 시크릿 분리: 영문·한글이 서로의 시크릿을 쓰지 않고, 한글 래퍼가 영문 시크릿을 넘겨도 러너가 쓰기 전에 멈춘다.
  5) 감시 연속성: 워치독·확인 필요 모음이 래퍼 파일 아래 기록된 실행을 본다.
"""
import io
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

import _bootstrap  # noqa: F401
import blogger_workflow_helpers as wf
import ops_inbox_helpers as h
from blogger_ko_helpers import EN_NAMES, EN_VALUES, GEMINI, KO_NAMES, KoreanRunBase, ko_publisher
from pipeline import inbox, plan, registry
from pipeline.stubs import stub_llm
from watchdog_helpers import FakeGitHub, run_record

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import ops_inbox as oi  # noqa: E402
import watchdog  # noqa: E402

REAL = _bootstrap.ROOT
WORKFLOWS = REAL / ".github" / "workflows"
WRAPPERS = wf.WRAPPERS
SEVEN_SECRETS = ("PIPELINE_SECRET_LLM_API_KEY", "PIPELINE_SECRET_BLOG_ID", "PIPELINE_SECRET_CLIENT_ID", "PIPELINE_SECRET_CLIENT_SECRET",
                 "PIPELINE_SECRET_REFRESH_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


def code_text(name):
    """워크플로 파일에서 주석 줄을 뺀 글(머리 주석이 시험 대상 낱말을 설명하느라 적고 있어도 오탐하지 않게)."""
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


class ReusableWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.data = wf.load(wf.REUSABLE)

    def test_it_is_an_internal_workflow_that_nobody_can_start_directly(self):
        self.assertEqual(self.data["name"], "[내부] Blogger 글 작성 공용(직접 실행하지 마세요)")
        self.assertEqual(list(self.data["on"]), ["workflow_call"])                  # schedule·workflow_dispatch 가 없다 → Run workflow 버튼도 정기 실행도 없다
        self.assertNotIn("run-name", self.data)                                     # 재사용 워크플로의 실행 제목은 부른 쪽 것이다
        self.assertEqual(registry.name_label(self.data["name"]), "내부")

    def test_the_inputs_are_the_five_the_wrappers_hand_over(self):
        inputs = self.data["on"]["workflow_call"]["inputs"]
        self.assertEqual(list(inputs), list(wf.CALL_INPUTS))
        self.assertEqual({k: (v["type"], v["required"], v.get("default")) for k, v in inputs.items()},
                         {"blog": ("string", True, None), "topic": ("string", False, ""), "dry_run": ("boolean", False, True),
                          "publish": ("string", False, ""), "auth_check": ("boolean", False, False)})
        for name, spec in inputs.items():
            self.assertRegex(spec["description"], "[가-힣]", name)

    def test_the_secrets_are_declared_by_role_name_and_all_optional(self):
        declared = self.data["on"]["workflow_call"]["secrets"]
        self.assertEqual(tuple(declared), SEVEN_SECRETS)
        for name, spec in declared.items():
            self.assertIs(spec["required"], False, name)                            # 시크릿이 아직 없는 블로그(정지 중인 한글)의 호출이 시작 단계에서 실패하지 않는다
            self.assertRegex(spec["description"], "[가-힣]", name)
            self.assertNotRegex(spec["description"], "TELEGRAM_|PIPELINE_SECRET_|BLOGGER_", name)    # 정의 설명에 시크릿 이름을 되풀이하지 않는다(WF-13)

    def test_it_never_reads_the_event_of_the_caller_and_never_inherits_or_indexes_secrets(self):
        code = code_text("blogger.yml")
        for forbidden in ("github.event_name", "github.event.inputs", "secrets: inherit", "secrets[", "toJSON(secrets", "github.event."):
            self.assertNotIn(forbidden, code, forbidden)
        self.assertIn("vars.PIPELINE_PAUSE", code)                                  # 킬 스위치 변수는 그대로 읽는다

    def test_the_jobs_steps_permissions_and_limits_are_the_ones_the_single_workflow_had(self):
        jobs = self.data["jobs"]
        self.assertEqual(list(jobs), ["plan", "generate"])
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        plan_job, generate = jobs["plan"], jobs["generate"]
        self.assertEqual((plan_job["name"], plan_job["runs-on"], plan_job["timeout-minutes"], "permissions" in plan_job), ("대상 블로그 계획", "ubuntu-latest", 5, False))
        self.assertEqual((generate["name"], generate["needs"], generate["if"], generate["timeout-minutes"], generate["permissions"]),
                         ("글 생성 (${{ matrix.key }})", "plan", "needs.plan.outputs.count != '0'", 15, {"contents": "write"}))
        self.assertEqual(generate["strategy"], {"fail-fast": False, "max-parallel": 1, "matrix": "${{ fromJSON(needs.plan.outputs.matrix) }}"})
        self.assertEqual(generate["concurrency"], {"group": "blogger-${{ matrix.key }}", "cancel-in-progress": False})   # 블로그별 줄은 그대로(영문 그룹 이름 불변)
        self.assertEqual(generate["env"], {"PIPELINE_PAUSE": "${{ vars.PIPELINE_PAUSE }}", "DRY_RUN": "${{ inputs.dry_run && 'true' || 'false' }}"})
        self.assertEqual([step.get("name") or step["uses"] for step in plan_job["steps"]], ["actions/checkout@v4", "actions/setup-python@v5", "실행 대상 계산 (레지스트리 검증 포함)"])
        self.assertEqual([step.get("name") or step["uses"] for step in generate["steps"]],
                         ["actions/checkout@v4", "actions/setup-python@v5", "의존성 설치", "생성 → 검증 → 게시/초안", "변경 사항 커밋"])
        for job in jobs.values():
            self.assertEqual(job["steps"][1]["with"], {"python-version": "3.12"})

    def test_both_jobs_run_on_ubuntu_latest_because_their_scripts_are_bash(self):
        """독립 검증 N7(변이 X03): plan 잡의 runs-on 은 위 시험이 고정했지만 generate 잡의 것은 아무 시험·검증기·actionlint 도 보지 않았다. 두 잡의 `run:` 은 bash
        스크립트(`set -euo pipefail`·배열·`$GITHUB_OUTPUT`)라 윈도 러너로 바뀌면 첫 정기 실행에서 깨진다."""
        jobs = self.data["jobs"]
        self.assertEqual({name: job["runs-on"] for name, job in jobs.items()}, {"plan": "ubuntu-latest", "generate": "ubuntu-latest"})
        for name, job in jobs.items():
            self.assertNotIn("shell", job.get("defaults", {}).get("run", {}), name)               # 기본 셸을 바꾸지도 않는다(바꾸면 bash 가정이 깨진다)
            for step in job["steps"]:
                self.assertNotIn("shell", step, (name, step.get("name")))

    def test_the_plan_script_and_the_commit_script_keep_their_behavior_lines(self):
        plan_step, generate, run_step = wf.callee_steps()
        script = plan_step["run"]
        for line in ("set -euo pipefail", "args=(--platform blogger)", 'if [ -n "${ONLY_BLOG:-}" ]; then args+=(--only "$ONLY_BLOG"); fi',
                     'if [ -n "${AUTH_CHECK_ONLY:-}" ]; then args+=(--include-off); fi', 'matrix=$(python -m pipeline.plan "${args[@]}")',
                     'count=$(python -m pipeline.plan "${args[@]}" --count)', 'echo "matrix=${matrix}" >> "$GITHUB_OUTPUT"', 'echo "count=${count}" >> "$GITHUB_OUTPUT"',
                     'if [ "$count" = "0" ]; then', "::notice::실행할 Blogger 블로그가 없습니다", "### Blogger 글 자동 작성", "**대상 0개**"):
            self.assertIn(line, script)
        self.assertEqual(run_step["run"], 'python -m pipeline.run --blog "$BLOG_KEY"')
        commit = generate["steps"][4]
        self.assertEqual((commit["if"], commit["env"]), ("${{ !cancelled() }}", {"BLOG_KEY": "${{ matrix.key }}", "HISTORY_FILE": "${{ matrix.history }}", "CONTENT_DIR": "${{ matrix.content_dir }}"}))
        for line in ('if [ "${DRY_RUN:-false}" = "true" ]; then echo "DRY_RUN — 커밋 생략"; exit 0; fi', 'git add -- "$p"', 'git commit -m "🤖 [${BLOG_KEY}] 생성/게시 기록"',
                     'git pull --rebase origin "${GITHUB_REF_NAME}" && git push origin "HEAD:${GITHUB_REF_NAME}"', "for i in 1 2 3; do"):
            self.assertIn(line, commit["run"])

    def test_the_runner_step_receives_exactly_the_environment_the_runner_reads(self):
        _plan, _generate, run_step = wf.callee_steps()
        self.assertEqual(set(run_step["env"]), {"BLOG_KEY", "BLOGGER_TOPIC", "BLOGGER_PUBLISH", "BLOGGER_AUTH_CHECK", *SEVEN_SECRETS})
        for name in SEVEN_SECRETS:
            self.assertEqual(run_step["env"][name], "${{ secrets.%s }}" % name, name)
        self.assertEqual(run_step["env"]["BLOG_KEY"], "${{ matrix.key }}")

    def test_the_file_is_the_only_place_that_runs_the_blogger_runner(self):
        """러너(pipeline.run)는 공용 워크플로 한 곳에서만 돈다 — 래퍼에 `run:` 이 없다."""
        for wrapper in WRAPPERS.values():
            self.assertNotIn("pipeline.run", code_text(wrapper), wrapper)
            for job in wf.load(wrapper)["jobs"].values():
                self.assertNotIn("steps", job, wrapper)
                self.assertNotIn("runs-on", job, wrapper)


class WrapperTest(unittest.TestCase):
    def test_names_and_run_names_use_the_channel_label_and_do_not_describe_a_mode(self):
        """검증 지적 N7: 옛 이름의 괄호 설명 `(초안함 업로드)` 는 mode auto(즉시 게시)에서 어긋난다 — 새 이름에는 mode 설명이 없다."""
        for wrapper, label in wf.WRAPPER_LABELS.items():
            data = wf.load(wrapper)
            self.assertEqual(data["name"], f"[{label}] 글 자동 작성", wrapper)
            self.assertTrue(data["run-name"].startswith(f"[{label}] 글 작성 · "), wrapper)
            self.assertEqual(registry.name_label(data["name"]), registry.name_label(data["run-name"]), wrapper)
            self.assertNotIn("(", data["name"], wrapper)
            self.assertNotIn("초안함 업로드)", data["name"], wrapper)

    def test_each_wrapper_belongs_to_exactly_one_registry_blog_and_the_channel_label_matches(self):
        reg = registry.load_registry(REAL / "pipeline" / "blogs.json")
        for key, wrapper in WRAPPERS.items():
            blog = registry.get_blog(reg, key)
            self.assertEqual(blog["workflow"], f".github/workflows/{wrapper}", key)
            self.assertEqual(registry.name_label(wf.load(wrapper)["name"]), blog["channel"]["label"], key)
            self.assertEqual(wf.WRAPPER_LABELS[wrapper], blog["channel"]["label"], key)
            self.assertEqual(wf.call_job(wrapper)[1]["with"]["blog"], key, wrapper)
            self.assertEqual(wf.load(wrapper)["on"]["schedule"], [{"cron": blog["schedule"]["cron"]}], wrapper)
        self.assertEqual({blog["workflow"] for blog in (registry.get_blog(reg, key) for key in WRAPPERS)}, {f".github/workflows/{w}" for w in WRAPPERS.values()})

    def test_every_blogger_blog_in_the_registry_has_its_wrapper_listed_in_the_test_helpers_so_the_other_tests_cover_it(self):
        """독립 검증 N10: 새 Blogger 블로그를 레지스트리에 더하고 래퍼를 만들어도 이 도우미의 `WRAPPERS` 에 한 줄을 안 더하면 이벤트·입력 조합 대조·시크릿 분리 시험이 새 래퍼를 보지 못한다.
        레지스트리의 Blogger 블로그와 도우미 목록이 어긋나면 여기서 알려 준다(REG-6 은 래퍼의 구조만 보고 `with` 식의 의미는 시험이 본다)."""
        reg = registry.load_registry(REAL / "pipeline" / "blogs.json")
        blogger_blogs = {blog["key"]: blog["workflow"].rsplit("/", 1)[-1] for blog in reg["blogs"] if blog["platform"] == "blogger"}
        self.assertEqual(WRAPPERS, blogger_blogs)
        self.assertEqual(sorted(wf.WRAPPER_LABELS), sorted(WRAPPERS.values()))

    def test_the_schedules_do_not_overlap_each_other_or_the_other_channels(self):
        crons = {name: wf.load(name)["on"]["schedule"][0]["cron"] for name in ("blogger-en.yml", "blogger-ko.yml", "tistory.yml", "naver.yml")}
        self.assertEqual(crons["blogger-en.yml"], "0 2 * * *")                      # 영문 정기 실행 시각은 그대로다
        self.assertEqual(crons["blogger-ko.yml"], "30 3 * * *")
        self.assertEqual(len(set(crons.values())), 4, crons)

    def test_the_triggers_and_inputs_are_the_old_workflows_inputs_without_the_blog_picker(self):
        english, korean = wf.load("blogger-en.yml"), wf.load("blogger-ko.yml")
        for data in (english, korean):
            self.assertEqual(set(data["on"]), {"schedule", "workflow_dispatch"})
            inputs = data["on"]["workflow_dispatch"]["inputs"]
            self.assertEqual(list(inputs), ["topic", "dry_run", "publish", "auth_check"])
            self.assertNotIn("blog", inputs)                                        # 어느 블로그인지는 래퍼가 정한다 — 수동 실행에서 바꿀 수 없다
            self.assertEqual((inputs["dry_run"]["type"], inputs["dry_run"]["default"]), ("boolean", True))
            self.assertEqual((inputs["publish"]["type"], inputs["publish"]["default"], inputs["publish"]["options"]), ("choice", "draft", ["off", "draft", "publish"]))
            self.assertEqual((inputs["auth_check"]["type"], inputs["auth_check"]["default"]), ("boolean", False))
            self.assertEqual((inputs["topic"]["type"], inputs["topic"]["required"]), ("string", False))
        self.assertEqual(english["on"]["workflow_dispatch"], korean["on"]["workflow_dispatch"])    # 입력의 이름·형·기본값·설명이 두 채널에서 글자까지 같다

    def test_permissions_concurrency_and_the_call_are_least_privilege_and_explicit(self):
        for key, wrapper in WRAPPERS.items():
            data = wf.load(wrapper)
            job_id, job = wf.call_job(wrapper)
            self.assertEqual(list(data["jobs"]), [job_id], wrapper)
            self.assertEqual(data["permissions"], {"contents": "read"}, wrapper)
            self.assertEqual(job["permissions"], {"contents": "write"}, wrapper)    # 불린 워크플로는 부르는 쪽 권한을 넘지 못한다 → 이력 커밋에 필요한 쓰기 권한만
            self.assertEqual(job["uses"], "./.github/workflows/blogger.yml", wrapper)
            self.assertRegex(job["name"], "[가-힣]", wrapper)
            self.assertNotIn("if", job, wrapper)
            self.assertNotIn("needs", job, wrapper)
            self.assertNotEqual(job["secrets"], "inherit", wrapper)
            self.assertEqual(data["concurrency"]["cancel-in-progress"], False, wrapper)
            self.assertNotEqual(data["concurrency"]["group"], f"blogger-{key}", wrapper)   # 공용 워크플로 안의 블로그별 줄과 이름이 같으면 서로를 기다려 멈춘다
        self.assertEqual({wf.load(w)["concurrency"]["group"] for w in WRAPPERS.values()}, {"blogger-en", "blogger-ko"})

    def test_the_two_wrappers_differ_only_in_what_belongs_to_the_channel(self):
        def normalized(wrapper, key, label, cron, group, secrets):
            text = (WORKFLOWS / wrapper).read_text(encoding="utf-8")
            text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
            for old, new in ((label, "LABEL"), (cron, "CRON"), (group, "GROUP"), (key, "KEY"), (wrapper_job_name(wrapper), "JOBNAME")):
                text = text.replace(old, new)
            for name in secrets:
                text = text.replace(name, "SECRET")
            return text

        def wrapper_job_name(wrapper):
            return wf.call_job(wrapper)[1]["name"]
        english = normalized("blogger-en.yml", "blogger_macat", "Blogger 영문", "0 2 * * *", "blogger-en", EN_NAMES)
        korean = normalized("blogger-ko.yml", "blogger_kcyoon", "Blogger 한글", "30 3 * * *", "blogger-ko", KO_NAMES)
        self.assertEqual(english, korean)

    def test_the_comments_say_where_the_logic_lives_and_how_to_turn_the_korean_blog_on(self):
        for wrapper in WRAPPERS.values():
            text = (WORKFLOWS / wrapper).read_text(encoding="utf-8")
            self.assertIn("blogger.yml", text)
            self.assertIn("with:", text)
        self.assertIn("mode: off", (WORKFLOWS / "blogger-ko.yml").read_text(encoding="utf-8"))
        self.assertIn("BLOGGER_KO_*", (WORKFLOWS / "blogger-ko.yml").read_text(encoding="utf-8"))

    def test_files_are_utf8_without_bom_and_end_with_a_newline(self):
        for name in ("blogger.yml", "blogger-en.yml", "blogger-ko.yml"):
            raw = (WORKFLOWS / name).read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), name)
            self.assertTrue(raw.endswith(b"\n"), name)
            raw.decode("utf-8")


class ExpressionEquivalenceTest(unittest.TestCase):
    """분리 전 blogger.yml 이 환경변수로 만든 값과 새 구조(래퍼 with → 공용 워크플로 env)가 낸 값이 모든 이벤트·입력 조합에서 같다 — 영문 정기·수동 동작 불변의 핵심 증명."""
    SHARED = ("AUTH_CHECK_ONLY", "DRY_RUN", "BLOGGER_TOPIC", "BLOGGER_PUBLISH", "BLOGGER_AUTH_CHECK")

    def test_every_event_and_input_combination_gives_the_old_values_for_both_wrappers(self):
        checked = 0
        for wrapper in WRAPPERS.values():
            for event, combos in (("schedule", [{}, {"dry_run": "true", "publish": "publish", "auth_check": "true", "topic": "x"}]),
                                  ("workflow_dispatch", list(wf.dispatch_combinations()))):
                for combo in combos:
                    old, new = wf.old_env(event, combo), wf.end_to_end_env(wrapper, event, combo)
                    for name in self.SHARED:
                        self.assertEqual(new[name], old[name], (wrapper, event, combo, name))
                    checked += 1
        self.assertEqual(checked, 2 * (2 + 108))                                   # 수동 108조합(연습 3 × publish 4 × 인증 점검 3 × 주제 3) + 정기 2, 래퍼 둘
        self.assertEqual(len(list(wf.dispatch_combinations())), 108)

    def test_the_old_expressions_are_what_the_main_workflow_had(self):
        """대조 기준(OLD_ENV)이 분리 전 식 그대로인지: 티스토리·네이버 워크플로가 같은 식을 아직 쓰므로 거기서 되읽는다."""
        tistory = wf.load("tistory.yml")["jobs"]["generate"]
        self.assertEqual(tistory["env"]["DRY_RUN"], wf.OLD_ENV["DRY_RUN"])
        self.assertEqual(wf.load("tistory.yml")["jobs"]["generate"]["steps"][3]["env"]["BLOGGER_TOPIC"], wf.OLD_ENV["BLOGGER_TOPIC"])

    def test_scheduled_runs_are_never_practice_runs_and_never_use_manual_inputs(self):
        for wrapper in WRAPPERS.values():
            env = wf.end_to_end_env(wrapper, "schedule", {"dry_run": "true", "auth_check": "true", "publish": "publish", "topic": "x"})
            self.assertEqual((env["DRY_RUN"], env["BLOGGER_PUBLISH"], env["BLOGGER_AUTH_CHECK"], env["AUTH_CHECK_ONLY"], env["BLOGGER_TOPIC"]), ("false", "", "", "", ""))

    def test_the_only_new_difference_is_that_the_wrapper_fixes_the_blog(self):
        """예전에는 `blog` 입력이 비면 Blogger 블로그 전체였고, 이제 래퍼가 자기 블로그 key 를 항상 넘긴다."""
        for key, wrapper in WRAPPERS.items():
            for event, combo in (("schedule", {}), ("workflow_dispatch", {"dry_run": "false"}), ("workflow_dispatch", {})):
                self.assertEqual(wf.end_to_end_env(wrapper, event, combo)["ONLY_BLOG"], key)
            self.assertEqual(wf.old_env("schedule")["AUTH_CHECK_ONLY"], "")

    def test_a_string_input_is_never_handed_over_as_null_for_any_event_or_input_combination(self):
        """독립 검증 N9: 정기 실행(과 API 로 입력을 생략한 수동 실행)에는 github.event.inputs.topic 이 없어 식이 null 이 된다. 문자열 입력에 null 을 넘길 때의 동작은 GitHub 문서에
        없으므로(엄격하게 거부하는 구현이면 첫 정기 실행이 실패한다) 래퍼가 `|| ''` 로 빈 문자열을 직접 넘긴다 — 모든 조합에서 문자열이고, 불린 입력은 불린이다."""
        checked = 0
        for wrapper in WRAPPERS.values():
            for event, combos in (("schedule", [{}, {"dry_run": "true", "publish": "publish", "auth_check": "true", "topic": "x"}]),
                                  ("workflow_dispatch", list(wf.dispatch_combinations()))):
                for combo in combos:
                    given = wf.wrapper_with(wrapper, event, combo)
                    for name in ("blog", "topic", "publish"):
                        self.assertIsInstance(given[name], str, (wrapper, event, combo, name))
                    for name in wf.BOOLEAN_INPUTS:
                        self.assertIsInstance(given[name], bool, (wrapper, event, combo, name))
                    checked += 1
        self.assertEqual(checked, 2 * (2 + 108))

    def test_the_topic_expression_falls_back_to_an_empty_string_in_both_wrappers(self):
        for wrapper in WRAPPERS.values():
            self.assertEqual(wf.call_job(wrapper)[1]["with"]["topic"], "${{ github.event.inputs.topic || '' }}", wrapper)
            self.assertEqual(wf.wrapper_with(wrapper, "schedule")["topic"], "", wrapper)                           # 정기 실행: 입력이 없다 → 빈 문자열
            self.assertEqual(wf.wrapper_with(wrapper, "workflow_dispatch", {"dry_run": "true"})["topic"], "", wrapper)    # 수동인데 주제를 안 준 경우
            self.assertEqual(wf.wrapper_with(wrapper, "workflow_dispatch", {"topic": "직접 정한 주제"})["topic"], "직접 정한 주제", wrapper)

    def test_typed_inputs_have_the_types_the_called_workflow_declares(self):
        for wrapper in WRAPPERS.values():
            for event, combo in (("schedule", {}), ("workflow_dispatch", {"dry_run": "true", "auth_check": "true", "publish": "off", "topic": "t"}), ("workflow_dispatch", {})):
                given = wf.wrapper_with(wrapper, event, combo)
                self.assertEqual(set(given), set(wf.CALL_INPUTS), wrapper)
                for name in wf.BOOLEAN_INPUTS:
                    self.assertIsInstance(given[name], bool, (wrapper, event, name))
                for name in ("blog", "topic", "publish"):
                    self.assertIsInstance(given[name], str, (wrapper, event, name))

    def test_the_plan_matrix_of_one_blog_is_what_the_single_blogger_workflow_gave_for_that_blog(self):
        """영문: `--platform blogger --only blogger_macat` 의 매트릭스 항목 = 한글 항목이 없던 레지스트리에서 `--platform blogger` 가 주던 그 항목."""
        reg = registry.load_registry(REAL / "pipeline" / "blogs.json")
        before = dict(reg, blogs=[blog for blog in reg["blogs"] if blog["key"] != "blogger_kcyoon"])    # 한글 블로그가 없던 레지스트리(블로그 객체는 reg 와 같은 것이다)
        for mode in ("draft", "auto", "off"):
            for blog in reg["blogs"]:
                if blog["key"] == "blogger_macat":
                    blog["mode"] = mode
            old = plan.build_matrix(before, "blogger", include_off=(mode == "off"))
            new = plan.build_matrix(reg, "blogger", only="blogger_macat", include_off=(mode == "off"))
            self.assertEqual(new, old, mode)
            self.assertEqual([item["key"] for item in new["include"]], ["blogger_macat"], mode)
            if mode != "off":     # 한글 블로그가 꺼져 있는 동안은 `--platform blogger` 만으로도 분리 전과 같은 매트릭스다(인증 점검의 `--include-off` 만 한글까지 본다)
                self.assertEqual(plan.build_matrix(reg, "blogger"), old, mode)


class SecretIsolationTest(unittest.TestCase):
    """영문과 한글은 계정·Cloud 프로젝트·OAuth 클라이언트가 달라야 한다(작업요청서 §3-4): 한 블로그의 시크릿이 다른 블로그의 실행에 닿는 길이 없다."""
    SECRETS = {**{name: f"ENV-{name}" for name in EN_NAMES}, **{name: f"KOR-{name}" for name in KO_NAMES}, "GEMINI_API_KEY": "GEM", "TELEGRAM_BOT_TOKEN": "TOK", "TELEGRAM_CHAT_ID": "CHAT"}

    def passed_by(self, wrapper, available=None):
        """래퍼의 `secrets:` 매핑을 주어진 저장소 시크릿으로 평가한 값(없는 시크릿은 빈 문자열 — GitHub 가 그렇게 넘긴다)."""
        pool = self.SECRETS if available is None else available
        out = {}
        for name, template in wf.call_job(wrapper)[1]["secrets"].items():
            ref = re.fullmatch(r"\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", template).group(1)
            out[name] = pool.get(ref, "")
        return out

    def test_each_wrapper_hands_over_only_its_own_blogs_secrets_plus_the_shared_ones(self):
        english, korean = self.passed_by("blogger-en.yml"), self.passed_by("blogger-ko.yml")
        self.assertEqual(english, {"PIPELINE_SECRET_LLM_API_KEY": "GEM", "PIPELINE_SECRET_BLOG_ID": "ENV-BLOGGER_BLOG_ID", "PIPELINE_SECRET_CLIENT_ID": "ENV-BLOGGER_CLIENT_ID",
                                   "PIPELINE_SECRET_CLIENT_SECRET": "ENV-BLOGGER_CLIENT_SECRET", "PIPELINE_SECRET_REFRESH_TOKEN": "ENV-BLOGGER_REFRESH_TOKEN",
                                   "TELEGRAM_BOT_TOKEN": "TOK", "TELEGRAM_CHAT_ID": "CHAT"})
        self.assertEqual(korean, {"PIPELINE_SECRET_LLM_API_KEY": "GEM", "PIPELINE_SECRET_BLOG_ID": "KOR-BLOGGER_KO_BLOG_ID", "PIPELINE_SECRET_CLIENT_ID": "KOR-BLOGGER_KO_CLIENT_ID",
                                  "PIPELINE_SECRET_CLIENT_SECRET": "KOR-BLOGGER_KO_CLIENT_SECRET", "PIPELINE_SECRET_REFRESH_TOKEN": "KOR-BLOGGER_KO_REFRESH_TOKEN",
                                  "TELEGRAM_BOT_TOKEN": "TOK", "TELEGRAM_CHAT_ID": "CHAT"})
        self.assertEqual(set(english), set(SEVEN_SECRETS))
        self.assertFalse(any(value.startswith("KOR-") for value in english.values()))
        self.assertFalse(any(value.startswith("ENV-") for value in korean.values()))

    def test_with_only_the_other_blogs_secrets_registered_a_wrapper_hands_over_nothing_of_it(self):
        only_english = {name: value for name, value in self.SECRETS.items() if name not in KO_NAMES}
        korean = self.passed_by("blogger-ko.yml", only_english)
        self.assertEqual([korean[name] for name in SEVEN_SECRETS[1:5]], ["", "", "", ""])          # 한글 시크릿이 없으면 빈 값이지 영문 값이 아니다
        only_korean = {name: value for name, value in self.SECRETS.items() if name not in EN_NAMES}
        english = self.passed_by("blogger-en.yml", only_korean)
        self.assertEqual([english[name] for name in SEVEN_SECRETS[1:5]], ["", "", "", ""])

    def test_the_registry_names_the_runner_resolves_are_the_ones_the_wrapper_maps(self):
        reg = registry.load_registry(REAL / "pipeline" / "blogs.json")
        for key, wrapper in WRAPPERS.items():
            blog = registry.get_blog(reg, key)
            env = dict(self.passed_by(wrapper))
            resolved = registry.resolve_secrets(blog, env)
            expected = {role: self.SECRETS[name] for role, name in blog["secrets"].items()}
            self.assertEqual(resolved, expected, key)
            self.assertEqual(registry.missing_secret_roles(blog, env), [], key)

    def test_the_runner_has_no_fallback_from_the_korean_blog_to_the_english_names(self):
        blog = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), "blogger_kcyoon")
        english_only_env = {"GEMINI_API_KEY": GEMINI, **EN_VALUES}
        self.assertEqual(registry.resolve_secrets(blog, english_only_env), {"llm_api_key": GEMINI, "blog_id": "", "client_id": "", "client_secret": "", "refresh_token": ""})
        self.assertEqual(registry.missing_secret_roles(blog, english_only_env), ["blog_id", "client_id", "client_secret", "refresh_token"])
        self.assertEqual(set(blog["secrets"].values()) & set(EN_NAMES), set())
        self.assertEqual(set(registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), "blogger_macat")["secrets"].values()) & set(KO_NAMES), set())

    def test_the_auth_check_is_the_second_line_of_defense_if_the_english_secrets_were_ever_handed_to_the_korean_run(self):
        """한글 래퍼가 실수로 영문 시크릿을 넘겨도(REG-6 이 PR 에서 먼저 막는다) 러너는 글을 만들기 전에 인증 점검에서 '블로그 주소 불일치'로 멈추고 아무것도 쓰지 않는다."""
        class Case(KoreanRunBase):
            def runTest(self):
                pass
        case = Case()
        case.setUp()
        try:
            english_workflow_env = {"PIPELINE_SECRET_LLM_API_KEY": GEMINI, "PIPELINE_SECRET_BLOG_ID": EN_VALUES["BLOGGER_BLOG_ID"],
                                    "PIPELINE_SECRET_CLIENT_ID": EN_VALUES["BLOGGER_CLIENT_ID"], "PIPELINE_SECRET_CLIENT_SECRET": EN_VALUES["BLOGGER_CLIENT_SECRET"],
                                    "PIPELINE_SECRET_REFRESH_TOKEN": EN_VALUES["BLOGGER_REFRESH_TOKEN"]}
            llm_calls = []

            def counting_llm(*args, **kwargs):
                llm_calls.append(args)
                return stub_llm(*args, **kwargs)
            publisher = ko_publisher(blog_url="https://macat0722.blogspot.com/")          # 영문 계정의 블로그 주소가 돌아온다
            code, out = case.go(env=english_workflow_env, publisher=publisher, llm=counting_llm)
            self.assertEqual(code, 2, out)
            self.assertIn("reason=blog_mismatch exit=2", out)
            self.assertEqual((publisher.published, case.drafts(), len(llm_calls)), ([], [], 0))     # 글을 만들지도, 올리지도, 저장하지도 않았다
            self.assertEqual([(entry["blog"], entry["status"], entry["topic"]) for entry in case.history()], [("blogger_kcyoon", "publish_failed", "")])   # 실패 한 줄만 남는다
            self.assertNotIn("macat0722", out)                                            # 다른 블로그 주소는 로그에 쓰지 않는다
            for value in EN_VALUES.values():
                self.assertNotIn(value, out)
        finally:
            case.doCleanups()

    def test_the_wrappers_never_name_the_other_blogs_secret_in_any_line_of_code(self):
        english, korean = code_text("blogger-en.yml"), code_text("blogger-ko.yml")
        for name in KO_NAMES:
            self.assertNotIn(name, english, name)
        for name in EN_NAMES:
            self.assertNotRegex(korean, rf"secrets\.{name}\b", name)

    def test_the_doc_and_the_registry_name_the_same_korean_secrets(self):
        setup = (REAL / ".github" / "editorial" / "BLOGGER_API_SETUP.md").read_text(encoding="utf-8")
        for name in KO_NAMES:
            self.assertIn(f"`{name}`", setup, name)


class MonitoringContinuityTest(unittest.TestCase):
    """워치독·확인 필요 모음은 레지스트리 workflow 필드(래퍼 파일)로 '마지막 실행'을 찾는다 — 재사용 워크플로를 부른 실행은 부른 쪽(래퍼) 아래에 기록된다.
    감시가 옛 blogger.yml 을 본다면 실행이 한 건도 안 보여 조용히 꺼진다(실패해도 모른다)."""

    def registry_with_blogger_blogs_on(self):
        reg = registry.load_registry(REAL / "pipeline" / "blogs.json")
        reg["blogs"] = [blog for blog in reg["blogs"] if blog["platform"] == "blogger"]
        for blog in reg["blogs"]:
            blog["mode"] = "auto"
        return reg

    def collect(self, runs):
        client = FakeGitHub(runs=runs)
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            findings, stats = watchdog.collect(self.registry_with_blogger_blogs_on(), tmp, datetime(2026, 10, 22, tzinfo=timezone.utc), client)
        return findings, client

    @staticmethod
    def failures(count=3):
        now = datetime(2026, 10, 21, tzinfo=timezone.utc)
        return [run_record("failure", now - timedelta(days=day)) for day in range(count)]

    def test_the_watchdog_asks_for_the_runs_of_each_wrapper_and_never_for_the_reusable_file(self):
        findings, client = self.collect({})
        asked = sorted(name for name, _branch in client.runs_asked)
        self.assertIn("blogger-en.yml", asked)
        self.assertIn("blogger-ko.yml", asked)
        self.assertNotIn("blogger.yml", asked)

    def test_three_failed_runs_under_the_english_wrapper_alert_only_for_the_english_blog(self):
        findings, _client = self.collect({"blogger-en.yml": self.failures()})
        fails = sorted((f.blog, f.code) for f in findings if f.code == "RUN_FAIL_STREAK")
        self.assertEqual(fails, [("blogger_macat", "RUN_FAIL_STREAK")])

    def test_three_failed_runs_under_the_korean_wrapper_alert_only_for_the_korean_blog(self):
        findings, _client = self.collect({"blogger-ko.yml": self.failures()})
        fails = sorted((f.blog, f.code) for f in findings if f.code == "RUN_FAIL_STREAK")
        self.assertEqual(fails, [("blogger_kcyoon", "RUN_FAIL_STREAK")])

    def test_failures_recorded_under_the_reusable_file_would_be_invisible_which_is_why_the_registry_points_at_the_wrappers(self):
        findings, _client = self.collect({"blogger.yml": self.failures()})
        self.assertEqual([f for f in findings if f.code == "RUN_FAIL_STREAK"], [])

    def test_a_stopped_blog_is_not_watched_at_all(self):
        reg = self.registry_with_blogger_blogs_on()
        for blog in reg["blogs"]:
            blog["mode"] = "off"
        client = FakeGitHub(runs={"blogger-en.yml": self.failures(), "blogger-ko.yml": self.failures()})
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            findings, _stats = watchdog.collect(reg, tmp, datetime(2026, 10, 22, tzinfo=timezone.utc), client)
        self.assertEqual(findings, [])
        self.assertNotIn("blogger-en.yml", [name for name, _branch in client.runs_asked])

    def test_the_operations_inbox_lists_the_wrappers_and_names_a_failed_wrapper_run_by_its_current_name(self):
        files = oi.list_workflow_files(REAL)
        for name in ("blogger.yml", "blogger-en.yml", "blogger-ko.yml"):
            self.assertIn(name, files)
        names = oi.read_workflow_names(REAL, files)
        self.assertEqual((names["blogger-en.yml"], names["blogger-ko.yml"], names["blogger.yml"]),
                         ("[Blogger 영문] 글 자동 작성", "[Blogger 한글] 글 자동 작성", "[내부] Blogger 글 작성 공용(직접 실행하지 마세요)"))
        now = h.NOW
        runs = {"blogger-en.yml": [h.make_run(11, h.ago(hours=1), "failure", path=".github/workflows/blogger-en.yml", name="[Blogger 영문] 글 작성 · 정기")],
                "blogger-ko.yml": [h.make_run(12, h.ago(hours=1), "success", path=".github/workflows/blogger-ko.yml", name="[Blogger 한글] 글 작성 · 정기")],
                "blogger.yml": []}
        items = inbox.run_items(runs, {}, now, h.REPO_URL, names=names)
        self.assertEqual([item.id for item in items], ["run:blogger_en.yml:failed"])
        self.assertEqual(items[0].title, "워크플로 실패 — " + "[Blogger 영문] 글 자동 작성".replace("[", chr(0xFF3B)).replace("]", chr(0xFF3D)))   # 모음은 대괄호를 전각으로 바꿔 보인다
        self.assertIn("blogger-en.yml", items[0].detail)

    def test_the_inbox_asks_the_runs_of_every_workflow_file_including_the_new_ones_within_its_call_budget(self):
        files = oi.list_workflow_files(REAL)
        calls = len([f for f in files if f != inbox.OWN_WORKFLOW])
        self.assertLessEqual(calls + 12, oi.MAX_CALLS_WITH_TOKEN, (calls, oi.MAX_CALLS_WITH_TOKEN))   # 워크플로 파일마다 한 번 + 이슈·PR·검사 읽기: 한도(150) 안이다
        self.assertEqual(len(files), 17)                                                                  # 열두 개였다가 공용 하나·래퍼 둘이 더해져 열다섯, 운영자 요청함의 ai-request·operator-reply 로 열일곱


class SplitDocsAreCurrentTest(unittest.TestCase):
    """독립 검증 N8: 영문/한글 분리 뒤에도 옛 문장이 남은 곳 — 요약 머리 예시(`### [Blogger] …`)·워크플로 접두사 예시(`[Blogger]`)·`pipeline/plan.py` 첫 줄('워크플로 수정 없이 잡이 늘어난다')."""

    def test_the_summary_head_example_in_the_architecture_doc_uses_the_two_current_channel_labels(self):
        text = (REAL / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        self.assertNotIn("### [Blogger] ", text)
        self.assertIn("### [Blogger 영문] Blogger (macat0722)", text)
        self.assertIn("### [Blogger 한글] Blogger (kcyoon)", text)

    def test_the_workflow_editing_rules_name_the_two_blogger_prefixes_not_the_old_single_one(self):
        text = (REAL / ".github" / "instructions" / "workflows.instructions.md").read_text(encoding="utf-8")
        self.assertNotIn("`[Blogger]`", text)
        self.assertIn("`[Blogger 영문]`·`[Blogger 한글]`", text)
        for label in ("Blogger 영문", "Blogger 한글"):
            self.assertIn(label, registry.CHANNEL_LABELS)                                       # 예시가 실제 허용 라벨이다

    def test_the_add_a_blogger_blog_playbook_tells_the_new_wrapper_to_be_listed_in_the_test_helpers(self):
        text = (REAL / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| 3-1 | AI (T3 승인 후) | **채널 래퍼 워크플로**"))
        for fragment in ("tests/blogger_workflow_helpers.py", "`WRAPPERS`·`WRAPPER_LABELS`", "REG-6 은 래퍼의 구조"):
            self.assertIn(fragment, row)

    def test_the_plan_module_no_longer_promises_that_adding_any_blog_needs_no_workflow_change(self):
        first = plan.__doc__.splitlines()[0]
        self.assertNotIn("블로그를 추가하면 워크플로 수정 없이 잡이 늘어난다", first)
        self.assertIn("Blogger 는 블로그마다 채널 래퍼 워크플로 하나를 더해야 한다", first)
        # 말이 맞는지: 티스토리·네이버 워크플로는 plan 의 매트릭스만 읽고, Blogger 는 래퍼가 `with.blog` 로 key 를 박는다
        for name in ("tistory.yml", "naver.yml"):
            self.assertIn("--platform " + name.split(".")[0], code_text(name))
        for wrapper in WRAPPERS.values():
            self.assertIn("blog:", code_text(wrapper))


class PlanCliTest(unittest.TestCase):
    """`python -m pipeline.plan` 출력(래퍼가 부르는 plan 단계가 읽는 것): 한글 블로그는 정지라 기본 대상 0개, `--include-off` 에서만 포함."""

    def run_plan(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = plan.main(list(args))
        return code, out.getvalue().strip()

    def test_the_real_registry_gives_zero_default_targets_and_the_korean_blog_only_with_include_off(self):
        self.assertEqual(self.run_plan("--platform", "blogger", "--count"), (0, "0"))
        self.assertEqual(self.run_plan("--platform", "blogger"), (0, '{"include":[]}'))
        code, text = self.run_plan("--platform", "blogger", "--include-off")
        self.assertEqual(code, 0)
        self.assertEqual([item["key"] for item in __import__("json").loads(text)["include"]], ["blogger_macat", "blogger_kcyoon"])
        for key in WRAPPERS:
            self.assertEqual(self.run_plan("--platform", "blogger", "--only", key, "--count"), (0, "0"), key)
            self.assertEqual(self.run_plan("--platform", "blogger", "--only", key, "--include-off", "--count"), (0, "1"), key)

    def test_each_wrapper_can_name_only_a_blogger_blog(self):
        code, _text = self.run_plan("--platform", "blogger", "--only", "chance")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
