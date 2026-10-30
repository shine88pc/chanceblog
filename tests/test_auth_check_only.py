"""단독 인증 점검(`--auth-check`, 워크플로 입력 '인증 점검만 실행'): 글을 만들지 않고 쓰기 없이 토큰 갱신·블로그 조회·주소 일치만 확인한다.

구성
  1) 시나리오: 통과·시크릿 없음·분류별 실패, 쓰기 0(이력·초안·저장소 파일)·Gemini 호출 0·시크릿 값 출력 0, 연습 실행·정지·입력의 영향.
  2) 열거: 모드 3 × 시크릿 16가지 × 연습 2 × 켜는 방법 2(명령줄·환경변수), 인증 점검 결과 10가지 × 모드 3.
  3) 계획(plan) 단계와 Blogger 워크플로(채널별 래퍼 + 공용 blogger.yml): 정지한 블로그도 점검 대상에 넣는 `--include-off`, 새 입력·환경변수, 예약(cron) 불변.

실제 구글·Blogger·Gemini 호출은 없다(가짜 게시자). 인증 점검 로직과 분류표 자체는 test_auth_check.py·test_draft_upload.py 가 본다.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap
import blogger_workflow_helpers as wf
from pipeline import auth_check as ac
from pipeline import plan, registry
from pipeline import run as run_mod
from pipeline.publishers.base import PublishError
from test_draft_upload import (ALL_ENV, AUTH_STAGE, EVERY_SECRET_VALUE, PROJECT_NUMBER, SECRET_NAMES, SECRET_VALUES,
                               TODAY_ENTRY, Runner, must_not_be_called, raising_factory)
from test_plan_and_watchdog import plan_step_script
from test_run import NOW, FakePublisher, make_root

try:
    import yaml
except ImportError:  # pragma: no cover - requirements-dev.txt 가 설치하는 의존성
    yaml = None

REAL = _bootstrap.ROOT
MODES = ("off", "draft", "auto")
BLOGGER_SECRETS_ONLY = {name: SECRET_VALUES[name] for name in SECRET_NAMES}   # Gemini 키 없이 블로그 시크릿 4종만


def tree(root):
    """폴더 안 모든 파일의 {상대 경로: 내용}. 실행 전후를 비교해 '쓰기 0'을 확인한다."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


class ScenarioTest(unittest.TestCase):
    def setUp(self):
        self.r = Runner(self)

    def check(self, mode="draft", env=None, publisher=None, **kwargs):
        """--auth-check 로 실행하고 (결과, 실행 전 파일, 실행 후 파일)을 돌려준다."""
        before = tree(self.r.roots[mode])
        res = self.r.run(mode, env if env is not None else ALL_ENV, publisher, extra=["--auth-check"], **kwargs)
        return res, before, tree(self.r.roots[mode])

    def test_a_passing_check_writes_nothing_and_never_calls_gemini(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                pub = FakePublisher()
                res, before, after = self.check(mode, publisher=pub)
                self.assertEqual(res.code, 0, res.out)
                self.assertEqual(before, after)                                  # 저장소 파일이 하나도 안 바뀐다(이력·초안·요약 파일 제외 — 아래)
                self.assertEqual((res.history, res.drafts), ([], {}))
                self.assertEqual((res.llm_calls.calls, pub.published, pub.health_calls), (0, [], 1))
                self.assertEqual(res.skips, [])
                self.assertEqual(len(res.annotations), 1)
                self.assertTrue(res.annotations[0].startswith("::notice::[blogger_macat] 인증 점검 통과"), res.annotations)
                self.assertIn("인증 점검 통과", res.out)
                # 실행 요약: 이름만, 값은 없다
                self.assertEqual(len(res.summary_lines), 4, res.summary)
                self.assertEqual(res.summary_lines[0], "### [Blogger 영문] Blogger (macat0722)")
                self.assertIn("**AUTH_CHECK_OK**", res.summary_lines[1])
                self.assertIn("쓰기 없음", res.summary_lines[1])
                for name in SECRET_NAMES:
                    self.assertIn(name, res.summary_lines[2])
                self.assertIn(f"mode: {mode}", res.summary_lines[3])
                for value in EVERY_SECRET_VALUE:
                    self.assertNotIn(value, res.everything())

    def test_it_works_without_a_gemini_key_and_without_any_llm(self):
        """글을 만들지 않으므로 Gemini 키가 없어도, LLM 객체가 없어도 점검한다(일반 실행이라면 키가 없어 종료 2)."""
        pub = FakePublisher()
        res, _before, _after = self.check("draft", BLOGGER_SECRETS_ONLY, pub, llm=None)
        self.assertEqual((res.code, pub.health_calls), (0, 1), res.out)
        normal = self.r.run("draft", BLOGGER_SECRETS_ONLY, FakePublisher(), llm=None)
        self.assertEqual((normal.code, normal.skips), (2, ["SECRETS_MISSING"]))      # 대조: 같은 환경의 일반 실행은 막힌다

    def test_the_environment_variable_is_the_same_as_the_command_line_option(self):
        for value, expected in (("1", True), ("true", True), ("True", True), ("TRUE", True), ("yes", True), ("YES", True), ("on", True),
                                ("On", True), (" true ", True), ("\tOn\n", True),
                                ("0", False), ("", False), ("   ", False), ("no", False), ("false", False), ("2", False), ("truee", False)):
            with self.subTest(value):
                pub = FakePublisher()
                res = self.r.run("off", {**ALL_ENV, "BLOGGER_AUTH_CHECK": value}, pub)
                self.assertEqual(res.skips == [], expected)       # 꺼져 있으면 정지(mode off)라 MODE_OFF 로 건너뛴다
                self.assertEqual(pub.health_calls, 1 if expected else 0)
                self.assertEqual((res.history, res.drafts), ([], {}))

    def test_a_stopped_blog_is_checked_but_a_normal_run_is_still_blocked(self):
        res, _before, _after = self.check("off", publisher=FakePublisher())
        self.assertEqual(res.code, 0)
        self.assertIn("mode=off(정지 중)이지만 인증 점검은 쓰기가 없어 실행합니다", res.out)
        normal = self.r.run("off", ALL_ENV, FakePublisher())
        self.assertEqual((normal.code, normal.skips), (0, ["MODE_OFF"]))

    def test_the_pause_switch_still_wins(self):
        res = self.r.run("draft", {**ALL_ENV, "PIPELINE_PAUSE": "true"}, factory=must_not_be_called, extra=["--auth-check"])
        self.assertEqual((res.code, res.skips), (0, ["PAUSED"]))

    def test_dry_run_does_not_stop_the_check_because_it_writes_nothing(self):
        for extra, env_extra in ((["--auth-check", "--dry-run"], {}), (["--auth-check"], {"DRY_RUN": "1"})):
            pub = FakePublisher()
            res = self.r.run("draft", {**ALL_ENV, **env_extra}, pub, extra=extra)
            self.assertEqual((res.code, pub.health_calls), (0, 1), res.out)
            self.assertIn("연습 실행(DRY_RUN)이 켜져 있지만 인증 점검은 쓰기가 없어 실제로 점검합니다", res.out)

    def test_publish_topic_and_cap_inputs_do_not_matter(self):
        """BLOGGER_PUBLISH(잘못된 값이어도)·--topic·하루 상한은 읽지 않는다. 같은 날 글이 이미 있어도 점검한다."""
        for env_extra, extra in (({"BLOGGER_PUBLISH": "yolo"}, []), ({"BLOGGER_PUBLISH": "off"}, []), ({"BLOGGER_PUBLISH": "publish"}, []),
                                 ({"BLOGGER_TOPIC": "수동으로 지정한 오늘의 생활 습관 주제"}, ["--topic", "다른 주제를 지정해도 무시됩니다 정말로"]),
                                 ({}, ["--publish", "off"])):
            with self.subTest(env=env_extra, extra=extra):
                pub = FakePublisher()
                res = self.r.run("draft", {**ALL_ENV, **env_extra}, pub, extra=["--auth-check", *extra], history=[TODAY_ENTRY])
                self.assertEqual((res.code, res.skips, pub.health_calls), (0, [], 1), res.out)
                self.assertEqual(res.history, [TODAY_ENTRY])                     # 이력은 읽지도 바꾸지도 않는다

    def test_a_corrupt_history_file_is_neither_read_nor_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, mode="draft")
            (root / "blogger_history.json").write_text("{not json", encoding="utf-8")
            pub, out = FakePublisher(), []
            code = run_mod.run(["--blog", "blogger_macat", "--root", str(root), "--auth-check"], environ=dict(ALL_ENV), now=NOW,
                               llm=None, publisher_factory=lambda blog, environ: pub, rng=random.Random(1), out=out.append)
            self.assertEqual((code, pub.health_calls), (0, 1), out)
            self.assertEqual((root / "blogger_history.json").read_text(encoding="utf-8"), "{not json")

    def test_no_secrets_is_a_clear_config_error_that_names_the_secrets_only(self):
        res = self.r.run("draft", {}, factory=must_not_be_called, extra=["--auth-check"])
        self.assertEqual((res.code, res.skips), (2, ["SECRETS_MISSING"]))
        self.assertIn("check=auth", res.out)
        self.assertEqual(len(res.annotations), 1)
        self.assertTrue(res.annotations[0].startswith("::error::[blogger_macat] 인증 점검을 할 수 없습니다: 게시용 시크릿이 하나도 등록되어 있지 않습니다"))
        for name in SECRET_NAMES:
            self.assertIn(name, res.annotations[0])
        self.assertEqual(len(res.summary_lines), 2, res.summary)
        self.assertIn("시크릿 없음", res.summary_lines[1])
        self.assertEqual((res.history, res.drafts, res.llm_calls.calls), ([], {}, 0))

    def test_partially_registered_secrets_are_a_config_error_naming_only_the_missing_ones(self):
        for mask in range(1, 15):
            present = [n for i, n in enumerate(SECRET_NAMES) if mask >> i & 1]
            missing = [n for n in SECRET_NAMES if n not in present]
            with self.subTest(present=present):
                res = self.r.run("draft", {name: SECRET_VALUES[name] for name in present}, factory=must_not_be_called,
                                 extra=["--auth-check"])
                self.assertEqual((res.code, res.skips), (2, ["SECRETS_MISSING"]))
                self.assertIn("missing=" + ",".join(missing), res.out)
                self.assertIn("일부만", res.annotations[0])
                self.assertIn("시크릿 일부 없음", res.summary)
                for name in present:
                    self.assertNotIn(name, res.annotations[0])
                for value in SECRET_VALUES.values():
                    self.assertNotIn(value, res.everything())

    def test_failures_use_the_same_classification_and_write_nothing(self):
        cases = {"auth_expired": 1, "auth_failed": 2, "blog_mismatch": 2, "network": 1, "bad_response": 1, "api_error": 1, "something_new": 1}
        for code, expected_exit in cases.items():
            for mode in MODES:
                with self.subTest(code=code, mode=mode):
                    marker = "RAW-MARKER-서버가-준-문구"
                    pub = (FakePublisher(blog_url="https://private-diary-of-someone.blogspot.com/") if code == "blog_mismatch"
                           else FakePublisher(check=PublishError(marker, code=code)))
                    res, before, after = self.check(mode, publisher=pub)
                    shown = ac.safe_code(code)
                    self.assertEqual(res.code, expected_exit, res.out)
                    self.assertEqual(res.skips, ["AUTH_CHECK_FAILED"])
                    self.assertIn(f"reason={shown} exit={expected_exit}", res.out)
                    self.assertEqual(res.annotations, [f"::error::[blogger_macat] {ac.sentence_for(shown)}"])   # 고정 문장만
                    self.assertEqual((before, res.history, res.drafts, pub.published, res.llm_calls.calls), (after, [], {}, [], 0))
                    self.assertEqual(len(res.summary_lines), 2, res.summary)
                    self.assertIn(ac.label_for(shown), res.summary_lines[1])
                    self.assertNotIn("private-diary", res.everything())          # 다른 블로그 주소는 출력하지 않는다
                    if code != "blog_mismatch":
                        self.assertIn(marker, res.out)                             # 원인은 로그 본문에만

    def test_exceptions_outside_the_adapter_are_reported_not_raised(self):
        res = self.r.run("draft", ALL_ENV, factory=raising_factory, extra=["--auth-check"])
        self.assertEqual((res.code, res.skips, res.history), (1, ["AUTH_CHECK_FAILED"], []))
        self.assertIn("reason=unexpected exit=1", res.out)
        self.assertIn("ImportError", res.out)
        res = self.r.run("draft", ALL_ENV, FakePublisher(check=KeyError("x")), extra=["--auth-check"])
        self.assertEqual((res.code, res.skips), (1, ["AUTH_CHECK_FAILED"]))

    def test_secret_values_and_forged_commands_never_reach_the_output(self):
        leaked = " ".join(SECRET_VALUES.values())
        forged = "HTTP 500\r::error::위조된 줄\n##[error]가짜 로그"
        for message in (f"fail {leaked}", forged, f"{forged} {leaked}"):
            with self.subTest(message[:20]):
                res = self.r.run("draft", ALL_ENV, FakePublisher(check=PublishError(message, code="api_error")), extra=["--auth-check"])
                self.assertEqual(res.code, 1)
                for value in SECRET_VALUES.values():
                    self.assertNotIn(value, res.everything())
                self.assertNotIn("\r", res.out)
                self.assertEqual(len([line for line in res.lines if line.lstrip().startswith(("::", "##["))]), 1, res.out)
                self.assertNotIn("위조된", res.annotations[0])

    def test_the_cloud_project_number_never_reaches_the_output_of_the_standalone_check_either(self):
        """403 'Blogger API has not been used in project <번호>' 문구의 프로젝트 번호(클라이언트 ID 앞 12자리)도 가린다(V-10)."""
        text = f"Blogger API has not been used in project {PROJECT_NUMBER} before or it is disabled."
        for code in ("auth_failed", "api_error"):
            with self.subTest(code):
                res = self.r.run("draft", ALL_ENV, FakePublisher(check=PublishError(text, code=code)), extra=["--auth-check"])
                self.assertNotEqual(res.code, 0)
                self.assertNotIn(PROJECT_NUMBER, res.everything())
        res = self.r.run("draft", ALL_ENV, FakePublisher(check=RuntimeError(text)), extra=["--auth-check"])
        self.assertNotIn(PROJECT_NUMBER, res.everything())
        # 일반 실행의 인증 점검과 같은 목록을 쓴다
        self.assertEqual(run_mod._secret_values(registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), "blogger_macat"),
                                                ALL_ENV)[-1], PROJECT_NUMBER)

    def test_unknown_blog_and_other_platforms_are_config_errors(self):
        root = self.r.roots["draft"]
        for key in ("nope", "chance"):
            out = []
            code = run_mod.run(["--blog", key, "--root", str(root), "--auth-check"], environ=dict(ALL_ENV), now=NOW, llm=None,
                               publisher_factory=must_not_be_called, rng=random.Random(1), out=out.append)
            self.assertEqual(code, 2, key)

    def test_architecture_and_setup_docs_describe_the_standalone_check(self):
        arch = (REAL / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        section = arch[arch.index("## 4-1."):arch.index("## 4-2.")]
        for word in ("--auth-check", "AUTH_CHECK_OK", "인증 점검만 실행", "--include-off", "BLOGGER_AUTH_CHECK", "주 1회", "워치독", "T3"):
            self.assertIn(word, section)
        setup = (REAL / ".github" / "editorial" / "BLOGGER_API_SETUP.md").read_text(encoding="utf-8")
        for word in ("인증 점검만 실행", "--auth-check", "AUTH_CHECK_OK"):
            self.assertIn(word, setup)
        register = (REAL / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
        self.assertIn("**D-57**", register)


# ----------------------------------------------------------------------------
# 2) 열거
# ----------------------------------------------------------------------------
class EnumerationTest(unittest.TestCase):
    def test_every_mode_secret_and_switch_combination(self):
        """모드 3 × 시크릿 16가지(4종 각각 있음/없음) × 연습 2 × 켜는 방법 2(명령줄·환경변수) = 192조합. Gemini 키·LLM 은 없다.
        시크릿이 4종 모두 있을 때만 점검(종료 0)하고, 아니면 Blogger 에 접속하지 않고 종료 2. 어느 조합도 쓰기·Gemini 호출이 없다."""
        r = Runner(self, in_memory_summary=True)
        mismatches, count = [], 0
        for mode in MODES:
            for mask in range(16):
                present = [n for i, n in enumerate(SECRET_NAMES) if mask >> i & 1]
                for dry in (False, True):
                    for how in ("cli", "env"):
                        env = {name: SECRET_VALUES[name] for name in present}
                        if dry:
                            env["DRY_RUN"] = "1"
                        if how == "env":
                            env["BLOGGER_AUTH_CHECK"] = "1"
                        pub = FakePublisher()
                        res = r.run(mode, env, pub, llm=None, extra=["--auth-check"] if how == "cli" else [])
                        count += 1
                        complete = len(present) == len(SECRET_NAMES)
                        want = (0 if complete else 2, [] if complete else ["SECRETS_MISSING"], 1 if complete else 0)
                        got = (res.code, res.skips, pub.health_calls)
                        label = f"mode={mode} secrets={len(present)}/4({mask}) dry={dry} via={how}"
                        if got != want:
                            mismatches.append(f"{label}: 실제 {got} / 기준 {want}")
                        if res.history or res.drafts or pub.published or res.llm_calls.calls:
                            mismatches.append(f"{label}: 쓰기 또는 Gemini 호출이 있음")
                        if "### [Blogger 영문] Blogger (macat0722)" not in res.summary or len(res.annotations) != 1:
                            mismatches.append(f"{label}: 요약·주석이 하나씩이 아님 {res.annotations}")
                        if complete and not res.annotations[0].startswith("::notice::"):
                            mismatches.append(f"{label}: 통과인데 notice 가 아님")
                        if not complete and not res.annotations[0].startswith("::error::"):
                            mismatches.append(f"{label}: 실패인데 error 가 아님")
                        if any(value in res.everything() for value in EVERY_SECRET_VALUE):
                            mismatches.append(f"{label}: 시크릿 값이 출력에 나옴")
        self.assertEqual(count, 3 * 16 * 2 * 2)
        self.assertEqual(mismatches[:10], [], f"어긋난 조합 {len(mismatches)}건")

    def test_every_check_outcome_in_every_mode(self):
        """인증 점검 결과 10가지(실패 분류 9 + 게시자 생성 실패) × 모드 3 = 30경로 + 통과 3경로: 종료 코드·분류가 표와 같고, 쓰기가 없다."""
        r = Runner(self, in_memory_summary=True)
        mismatches = []
        for mode in MODES:
            for name, (make_pub, exit_code, reason) in AUTH_STAGE.items():
                auth_pub = make_pub()
                factory = raising_factory if auth_pub is None else (lambda blog, environ, p=auth_pub: p)
                res = r.run(mode, ALL_ENV, factory=factory, llm=None, extra=["--auth-check"])
                label = f"mode={mode} 결과={name}"
                if (res.code, res.skips) != (exit_code, ["AUTH_CHECK_FAILED"]) or f"reason={reason} exit={exit_code}" not in res.out:
                    mismatches.append(f"{label}: 실제 {(res.code, res.skips)} / 기준 {(exit_code, ['AUTH_CHECK_FAILED'])} {reason}")
                if res.annotations != [f"::error::[blogger_macat] {ac.sentence_for(reason)}"]:
                    mismatches.append(f"{label}: 주석이 고정 문장이 아님 {res.annotations}")
                if res.history or res.drafts:
                    mismatches.append(f"{label}: 쓰기가 있음")
            pub = FakePublisher()
            res = r.run(mode, ALL_ENV, pub, llm=None, extra=["--auth-check"])
            if (res.code, pub.health_calls, res.skips) != (0, 1, []):
                mismatches.append(f"mode={mode} 통과 경로: {(res.code, pub.health_calls, res.skips)}")
        self.assertEqual(mismatches[:10], [], f"어긋난 경로 {len(mismatches)}건")


# ----------------------------------------------------------------------------
# 3) plan 단계와 blogger.yml
# ----------------------------------------------------------------------------
def registry_with(mode, korean_mode="off"):
    """영문(blogger_macat)의 mode 를 정하고, 한글(blogger_kcyoon)은 기본으로 정지(off)에 맞춘다 — 이 시험들은 '정지 상태'의 계획을 보므로
    실제 레지스트리의 한글 mode(2026-10-29 부터 draft)와 무관하게 만든다."""
    reg = registry.load_registry()
    for blog in reg["blogs"]:
        if blog["key"] == "blogger_macat":
            blog["mode"] = mode
        elif blog["key"] == "blogger_kcyoon":
            blog["mode"] = korean_mode
    return reg


class PlanIncludeOffTest(unittest.TestCase):
    def test_stopped_blogs_are_targets_only_when_asked(self):
        reg = registry_with("off")
        self.assertEqual(plan.build_matrix(reg, "blogger")["include"], [])
        self.assertEqual(plan.build_matrix(reg, "blogger", include_off=False)["include"], [])
        items = plan.build_matrix(reg, "blogger", include_off=True)["include"]
        self.assertEqual([(i["key"], i["mode"]) for i in items], [("blogger_macat", "off"), ("blogger_kcyoon", "off")])      # 한글 Blogger 도 정지(이 시험이 맞춘 상태 — 실제 값은 2026-10-29 부터 draft)
        self.assertEqual(items[0]["secret_refresh_token"], "BLOGGER_REFRESH_TOKEN")      # 이름만 있고 값은 없다
        self.assertEqual(items[1]["secret_refresh_token"], "BLOGGER_KO_REFRESH_TOKEN")   # 한글은 영문과 다른 시크릿 이름이다
        self.assertEqual([i["key"] for i in plan.build_matrix(reg, "blogger", only="blogger_macat", include_off=True)["include"]],
                         ["blogger_macat"])
        self.assertEqual([i["key"] for i in plan.build_matrix(reg, "blogger", only="blogger_kcyoon", include_off=True)["include"]],
                         ["blogger_kcyoon"])
        self.assertEqual(plan.build_matrix(reg, "blogger", only="chance", include_off=True)["include"], [])

    def test_the_platform_filter_and_running_blogs_are_unchanged(self):
        reg = registry_with("draft")
        self.assertEqual([i["key"] for i in plan.build_matrix(reg, "blogger", include_off=True)["include"]], ["blogger_macat", "blogger_kcyoon"])
        self.assertEqual([i["key"] for i in plan.build_matrix(reg, "blogger")["include"]], ["blogger_macat"])           # 한글은 정지라 일반 실행의 대상이 아니다
        everything = [i["key"] for i in plan.build_matrix(reg, include_off=True)["include"]]
        self.assertEqual(everything, ["chance", "blogger_macat", "blogger_kcyoon", "naver_life_tips"])      # 플랫폼을 안 주면 레지스트리 전부(초안 패키지 채널 포함) — 위 blogger 필터가 이 하나를 빼는 것은 그대로다

    def test_the_command_line_flag(self):
        import io
        from contextlib import redirect_stdout
        with mock.patch.object(plan, "load_registry", return_value=registry_with("off")):
            for extra, expected in (([], "0"), (["--include-off"], "2")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    self.assertEqual(plan.main(["--platform", "blogger", "--count", *extra]), 0)
                self.assertEqual(buf.getvalue().strip(), expected, extra)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(plan.main(["--platform", "blogger", "--include-off", "--only", "blogger_macat"]), 0)
            self.assertEqual(json.loads(buf.getvalue())["include"][0]["key"], "blogger_macat")


@unittest.skipUnless(yaml is not None and shutil.which("bash"),
                     "PyYAML(requirements-dev.txt)과 bash 가 필요합니다(CI 의 Linux 에서는 항상 실행됩니다)")
class PlanStepIncludeOffTest(unittest.TestCase):
    """blogger.yml 의 plan 단계를 GitHub 처럼 `bash -e <스크립트>` 로 실제 실행한다(레지스트리는 임시 저장소 사본)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.script = self.work / "plan_step.sh"
        self.script.write_bytes(plan_step_script().encode("utf-8"))

    def repo(self, mode):
        root = self.work / f"repo_{mode}"
        make_root(root, mode=mode)
        ignore = shutil.ignore_patterns("__pycache__", "blogs.json", "profiles")
        shutil.copytree(REAL / "pipeline", root / "pipeline", dirs_exist_ok=True, ignore=ignore)
        return root

    def run_step(self, root, only="blogger_macat", auth_check_only=""):
        """only 기본값은 영문 래퍼가 넘기는 값이다(래퍼는 항상 자기 블로그 key 를 `blog` 로 넘기므로 실제 실행에서 ONLY_BLOG 가 비는 일은 없다)."""
        output, summary = root / "github_output", root / "github_step_summary"
        output.write_bytes(b"")
        summary.write_bytes(b"")
        env = {**os.environ, "PYTHONUTF8": "1", "ONLY_BLOG": only, "AUTH_CHECK_ONLY": auth_check_only,
               "GITHUB_OUTPUT": output.as_posix(), "GITHUB_STEP_SUMMARY": summary.as_posix(),
               "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")}
        proc = subprocess.run(["bash", "-e", self.script.as_posix()], cwd=str(root), env=env, capture_output=True,
                              text=True, encoding="utf-8", timeout=120)
        return proc, output.read_text(encoding="utf-8"), summary.read_text(encoding="utf-8")

    def test_the_auth_check_run_includes_the_stopped_blog_and_the_normal_run_still_skips_it(self):
        off, auto = self.repo("off"), self.repo("auto")
        with self.subTest("정지한 블로그 + 점검만: 대상 1개, 알림 없음"):
            proc, output, summary = self.run_step(off, auth_check_only="1")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("count=1", output.splitlines())
            self.assertIn('"key":"blogger_macat"', output)
            self.assertIn('"mode":"off"', output)
            self.assertNotIn("::notice::", proc.stdout)
            self.assertEqual(summary, "")
        with self.subTest("정지한 블로그 + 일반 실행: 예전처럼 대상 0개"):
            proc, output, summary = self.run_step(off)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("count=0", output.splitlines())
            self.assertIn("::notice::실행할 Blogger 블로그가 없습니다", proc.stdout)
        with self.subTest("정지한 블로그 + 점검만 + 블로그 지정"):
            proc, output, _summary = self.run_step(off, only="blogger_macat", auth_check_only="1")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("count=1", output.splitlines())
        with self.subTest("한글 래퍼가 넘기는 key: 한글 블로그만 점검 대상"):
            proc, output, _summary = self.run_step(off, only="blogger_kcyoon", auth_check_only="1")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("count=1", output.splitlines())
            self.assertIn('"key":"blogger_kcyoon"', output)
            self.assertNotIn("blogger_macat", output)
            self.assertIn("BLOGGER_KO_BLOG_ID", output)                            # 이름만(값 없음) — 한글 블로그의 시크릿 이름이다
        with self.subTest("key 를 비우면(래퍼는 그러지 않는다) Blogger 블로그 전체: 정지한 둘이 모두 점검 대상"):
            proc, output, _summary = self.run_step(off, only="", auth_check_only="1")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("count=2", output.splitlines())
        with self.subTest("켜진 블로그 + 점검만: 대상 1개"):
            proc, output, _summary = self.run_step(auto, auth_check_only="1")
            self.assertEqual((proc.returncode, "count=1" in output.splitlines()), (0, True))
        with self.subTest("점검만이어도 다른 플랫폼 블로그 key 는 오류(빨강)"):
            proc, output, _summary = self.run_step(auto, only="chance", auth_check_only="1")
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(output, "")


@unittest.skipUnless(yaml is not None, "PyYAML(requirements-dev.txt)이 필요합니다(CI 에서는 항상 실행됩니다)")
class WorkflowAuthCheckInputTest(unittest.TestCase):
    """인증 점검만 실행 입력: 채널별 래퍼(blogger-en.yml·blogger-ko.yml)가 입력을 받아 `with:` 로 넘기고 공용 blogger.yml 이 환경변수로 러너·plan 단계에 준다."""
    WRAPPERS = tuple(wf.WRAPPERS.values())

    @classmethod
    def setUpClass(cls):
        cls.data = wf.load(wf.REUSABLE)
        cls.plan_step, cls.generate, cls.run_step = wf.callee_steps()

    def inputs(self, wrapper):
        return wf.load(wrapper)["on"]["workflow_dispatch"]["inputs"]

    def test_the_input_is_an_off_by_default_boolean_with_a_precise_korean_description(self):
        for wrapper in self.WRAPPERS:
            spec = self.inputs(wrapper)["auth_check"]
            self.assertEqual((spec["type"], spec["default"]), ("boolean", False), wrapper)
            for word in ("인증 점검", "기본 꺼짐", "Gemini", "쓰기 없음", "BLOGGER_API_SETUP.md"):     # 자세한 설명은 문서로(V-16)
                self.assertIn(word, spec["description"], wrapper)
            self.assertRegex(spec["description"], r"[가-힣]")
            self.assertLessEqual(len(spec["description"]), 120, "실행 대화상자에서 읽히도록 한 줄 요약 + 문서 링크로 둔다")

    def test_the_details_the_short_description_dropped_are_in_the_setup_guide(self):
        """입력 설명에서 뺀 동작(시크릿 없음·정지 중·연습 실행·입력 무시)은 BLOGGER_API_SETUP.md 에 있다."""
        setup = (REAL / ".github" / "editorial" / "BLOGGER_API_SETUP.md").read_text(encoding="utf-8")
        bullet = next(line for line in setup.splitlines() if line.startswith("- **`인증 점검만 실행` 체크"))
        for word in ("시크릿 없음", "`mode: off`", "`연습 실행`", "`publish`", "`topic`", "Gemini 호출 0회"):
            self.assertIn(word, bullet)

    def test_the_input_reaches_the_runner_and_the_plan_step_only_through_environment_variables(self):
        for step in self.generate["steps"] + self.data["jobs"]["plan"]["steps"]:
            self.assertNotIn("inputs.auth_check", str(step.get("run", "")))
        self.assertEqual(self.run_step["run"], 'python -m pipeline.run --blog "$BLOG_KEY"')   # 명령줄 플래그가 아니라 환경변수로 켠다
        self.assertIn("--include-off", self.plan_step["run"])
        self.assertIn('AUTH_CHECK_ONLY:-', self.plan_step["run"])

    def test_scheduled_runs_never_turn_the_check_on_and_manual_runs_follow_the_checkbox(self):
        for wrapper in self.WRAPPERS:
            for label, name in (("실행 단계", "BLOGGER_AUTH_CHECK"), ("plan 단계", "AUTH_CHECK_ONLY")):
                with self.subTest(wrapper=wrapper, step=label):
                    self.assertEqual(wf.end_to_end_env(wrapper, "workflow_dispatch", {"auth_check": "true"})[name], "1")
                    self.assertEqual(wf.end_to_end_env(wrapper, "workflow_dispatch", {"auth_check": "false"})[name], "")
                    self.assertEqual(wf.end_to_end_env(wrapper, "workflow_dispatch", {})[name], "")
                    self.assertEqual(wf.end_to_end_env(wrapper, "schedule")[name], "")        # 정기 실행은 항상 글을 만든다
                    self.assertEqual(wf.end_to_end_env(wrapper, "schedule", {"auth_check": "true"})[name], "")

    def test_no_new_schedule_and_no_wider_permissions(self):
        """새 예약 작업은 T3 다. 주 1회 점검은 후속에서 워치독에 붙인다(문서에만 남김). 래퍼의 예약은 레지스트리의 cron 그대로다."""
        reg = registry.load_registry(REAL / "pipeline" / "blogs.json")
        for key, wrapper in wf.WRAPPERS.items():
            data = wf.load(wrapper)
            self.assertEqual(data["on"]["schedule"], [{"cron": registry.get_blog(reg, key)["schedule"]["cron"]}], wrapper)
            self.assertEqual(set(data["on"]), {"schedule", "workflow_dispatch"}, wrapper)
            self.assertEqual(data["permissions"], {"contents": "read"}, wrapper)
        self.assertEqual(wf.load("blogger-en.yml")["on"]["schedule"], [{"cron": "0 2 * * *"}])          # 영문 예약은 그대로
        self.assertEqual(set(self.data["on"]), {"workflow_call"})                                         # 공용 워크플로는 직접 실행하는 트리거가 없다
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        self.assertEqual(self.generate["permissions"], {"contents": "write"})
        self.assertEqual(self.generate["if"], "needs.plan.outputs.count != '0'")

    def test_secrets_are_still_passed_only_as_pipeline_secret_variables(self):
        roles = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), "blogger_macat")["secrets"]
        expected = {"PIPELINE_SECRET_" + role.upper(): "${{ secrets.PIPELINE_SECRET_%s }}" % role.upper() for role in roles}
        env = self.run_step["env"]
        self.assertEqual({k: v for k, v in env.items() if k.startswith("PIPELINE_SECRET_")}, expected)
        self.assertEqual(set(env) - set(expected), {"BLOG_KEY", "BLOGGER_TOPIC", "BLOGGER_PUBLISH", "BLOGGER_AUTH_CHECK", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"})
        for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):          # 알림용 시크릿은 같은 이름의 환경변수로만 나간다(검증기 WF-13)
            self.assertEqual(env[name], "${{ secrets.%s }}" % name)
        self.assertEqual(set(self.plan_step["env"]), {"ONLY_BLOG", "AUTH_CHECK_ONLY"})            # plan 단계에는 시크릿이 없다


if __name__ == "__main__":
    unittest.main()
