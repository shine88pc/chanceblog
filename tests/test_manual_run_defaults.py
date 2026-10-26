"""수동 실행의 낭비와 정지 스위치 테스트(D-51·D-53·D-54). 네트워크 없이 돈다.

배경(무료 한도 진단 2026-10-25): Gemini 무료 한도는 프로젝트 단위라 Chance·Blogger·이슈 수정·수동 실행이 한 통을 나눠 쓴다. 그런데
(1) Chance 연습 실행과 이미지 교체 연습이 실제 Gemini 를 불렀고, (2) Blogger 수동 실행은 기본이 '연습 아님'이라 입력을 건드리지 않으면
초안 커밋과 하루 상한 소진까지 갔으며, (3) 이슈 수정은 PIPELINE_PAUSE 를 읽지 않았고, (4) 이미지 교체는 한 번에 처리하는 글 수에 상한이 없었고,
(5) Chance 수동 실제 실행이 게시 시각·하루 상한을 우회하는데 표시가 없었다. 이 테스트는 워크플로 YAML 의 기본값과 식을 직접 평가해
'기본값으로 눌렀을 때 Gemini 를 부르지 않는다'를 끝에서 끝까지(YAML 식 → 환경변수 → generator 의 스텁 판정 → 호출 0회) 증명한다.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap
import generator as g
from edits_helpers import ABOUT, image_body, issue, make_edit_root, page_body
from pipeline import registry
from pipeline import run as run_mod
from pipeline.edits import runner
from pipeline.stubs import stub_llm
from test_generator_slots import at, candidate, long_post, run_captured
from test_run import RunBase
from test_workflow_names import context, load, render

ROOT = _bootstrap.ROOT
CHANCE_WORKFLOWS = ("chanceblog.yml", "chance-fix-images.yml")


def generator_step(workflow):
    return next(s for s in load(workflow)["jobs"]["build"]["steps"] if s.get("run") == "python generator.py")


def value_of(template, event, inputs=None, secrets=None, event_inputs=None):
    """워크플로의 `${{ … }}` 식을 GitHub 규칙대로 평가한다. inputs 는 입력 컨텍스트, event_inputs 는 github.event.inputs(문자열)."""
    ctx = context(event, inputs)
    ctx["secrets"] = secrets if secrets is not None else {"GEMINI_API_KEY": "fake-gemini-secret"}
    if event_inputs is not None:
        ctx["github"]["event"] = {"inputs": event_inputs}
    return render(template, ctx)


def gemini_key(workflow, event, inputs=None, secret="fake-gemini-secret"):
    secrets = {"GEMINI_API_KEY": secret} if secret is not None else {}
    return value_of(generator_step(workflow)["env"]["GEMINI_API_KEY"], event, inputs, secrets)


# ----------------------------------------------------------------------------
# 1) Chance 두 워크플로: 연습 실행은 가짜 AI 응답이 기본, real_ai 로만 실제 호출
# ----------------------------------------------------------------------------
class ChanceWorkflowDefaultsTest(unittest.TestCase):
    def test_manual_practice_run_gets_no_gemini_key_by_default(self):
        for wf in CHANCE_WORKFLOWS:
            with self.subTest(workflow=wf):
                self.assertEqual(gemini_key(wf, "workflow_dispatch", {"dry_run": True, "real_ai": False}), "")
                self.assertEqual(gemini_key(wf, "workflow_dispatch", {"dry_run": True}), "")           # real_ai 값이 아예 없어도
                self.assertEqual(gemini_key(wf, "workflow_dispatch", {"dry_run": True, "real_ai": None}), "")

    def test_real_ai_checkbox_hands_the_key_to_the_practice_run(self):
        for wf in CHANCE_WORKFLOWS:
            with self.subTest(workflow=wf):
                self.assertEqual(gemini_key(wf, "workflow_dispatch", {"dry_run": True, "real_ai": True}), "fake-gemini-secret")

    def test_a_real_run_always_gets_the_key_whatever_real_ai_says(self):
        for wf in CHANCE_WORKFLOWS:
            for real_ai in (False, True, None):
                with self.subTest(workflow=wf, real_ai=real_ai):
                    self.assertEqual(gemini_key(wf, "workflow_dispatch", {"dry_run": False, "real_ai": real_ai}), "fake-gemini-secret")

    def test_the_scheduled_run_always_gets_the_key(self):
        self.assertEqual(gemini_key("chanceblog.yml", "schedule"), "fake-gemini-secret")
        self.assertEqual(gemini_key("chanceblog.yml", "schedule", {"dry_run": True}), "fake-gemini-secret")   # 정기 실행에는 입력이 없다

    def test_without_the_secret_nothing_is_passed(self):
        for event, inputs in (("schedule", None), ("workflow_dispatch", {"dry_run": False}), ("workflow_dispatch", {"dry_run": True, "real_ai": True})):
            self.assertEqual(gemini_key("chanceblog.yml", event, inputs, secret=None), "")

    def test_both_chance_workflows_use_the_same_key_expression_and_still_wire_the_secret(self):
        exprs = {wf: generator_step(wf)["env"]["GEMINI_API_KEY"] for wf in CHANCE_WORKFLOWS}
        self.assertEqual(len(set(exprs.values())), 1, exprs)
        for wf in CHANCE_WORKFLOWS:
            self.assertIn("secrets.GEMINI_API_KEY", exprs[wf])                 # 검증기 REG-3(시크릿 연결) 이 보는 글자
            self.assertEqual(generator_step(wf)["env"]["UNSPLASH_ACCESS_KEY"], "${{ secrets.UNSPLASH_ACCESS_KEY }}")

    def test_the_dry_run_switch_itself_is_unchanged(self):
        for wf in CHANCE_WORKFLOWS:
            template = generator_step(wf)["env"]["DRY_RUN"]
            self.assertEqual(value_of(template, "workflow_dispatch", {"dry_run": True}), "1")
            self.assertEqual(value_of(template, "workflow_dispatch", {"dry_run": False}), "0")
        self.assertEqual(value_of(generator_step("chanceblog.yml")["env"]["DRY_RUN"], "schedule"), "0")

    def test_the_inputs_dry_run_stays_on_and_real_ai_is_off_by_default(self):
        for wf in CHANCE_WORKFLOWS:
            inputs = load(wf)["on"]["workflow_dispatch"]["inputs"]
            self.assertEqual(list(inputs), ["dry_run", "real_ai"], wf)
            self.assertEqual((inputs["dry_run"]["type"], inputs["dry_run"]["default"]), ("boolean", True), wf)
            self.assertEqual((inputs["real_ai"]["type"], inputs["real_ai"]["default"]), ("boolean", False), wf)

    def test_input_descriptions_tell_what_the_defaults_mean(self):
        for wf in CHANCE_WORKFLOWS:
            inputs = load(wf)["on"]["workflow_dispatch"]["inputs"]
            self.assertIn("가짜 AI", inputs["dry_run"]["description"], wf)
            description = inputs["real_ai"]["description"]
            for fragment in ("실제 Gemini", "무료 한도", "기본은 꺼짐", "가짜 AI"):
                self.assertIn(fragment, description, wf)

    def test_input_descriptions_say_that_practice_runs_still_search_unsplash(self):
        """독립 검증 V-01: 연습 실행도 Unsplash 이미지 검색은 실제로 한다(UNSPLASH_ACCESS_KEY 는 항상 넘어간다). 그 사실과 한도를 나눠 쓴다는 것을
        입력 설명이 알려야 한다 — 'Gemini 한도를 쓰지 않는다'만 읽으면 연습이 아무 한도도 안 쓰는 것으로 오해한다."""
        for wf in CHANCE_WORKFLOWS:
            description = load(wf)["on"]["workflow_dispatch"]["inputs"]["real_ai"]["description"]
            self.assertIn("연습도 Unsplash 이미지 검색은 실제로 합니다", description, wf)
            self.assertIn("시간당 한도를 정기 글과 나눠 씁니다", description, wf)

    def test_the_practice_run_still_hands_over_the_unsplash_key_so_the_description_is_true(self):
        for wf in CHANCE_WORKFLOWS:
            for inputs in ({"dry_run": True, "real_ai": False}, {"dry_run": True, "real_ai": True}, {"dry_run": False}):
                env = generator_step(wf)["env"]
                self.assertEqual(value_of(env["UNSPLASH_ACCESS_KEY"], "workflow_dispatch", inputs,
                                          secrets={"UNSPLASH_ACCESS_KEY": "fake-unsplash"}), "fake-unsplash", (wf, inputs))

    def test_run_names_show_whether_the_practice_run_used_the_real_ai(self):
        self.assertEqual(render(load("chanceblog.yml")["run-name"], context("workflow_dispatch", {"dry_run": True, "real_ai": True})),
                         "Chance 글 작성·게시 · 수동(연습: 실제 AI 호출·저장 안 함)")
        self.assertEqual(render(load("chanceblog.yml")["run-name"], context("workflow_dispatch", {"dry_run": True, "real_ai": False})),
                         "Chance 글 작성·게시 · 수동(연습: 저장 안 함)")
        self.assertEqual(render(load("chance-fix-images.yml")["run-name"], context("workflow_dispatch", {"dry_run": True, "real_ai": True})),
                         "Chance 기존 글 이미지 교체 · 연습(실제 AI 호출·저장 안 함)")

    def test_the_cap_written_in_the_fix_images_description_is_the_cap_in_the_code(self):
        description = load("chance-fix-images.yml")["on"]["workflow_dispatch"]["inputs"]["dry_run"]["description"]
        self.assertIn(f"최대 {g.FIX_IMAGES_MAX_PER_RUN}건", description)


class DefaultPracticeRunCallsNoGeminiTest(unittest.TestCase):
    """기본값으로 수동 연습 실행을 눌렀을 때 Gemini 호출이 0회임을 YAML 식 → 환경변수 → generator 판정 → 호출 수까지 이어서 본다."""

    def module_flags(self, key, dry):
        env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "DRY_RUN", "FIX_IMAGES", "PIPELINE_PAUSE")}
        env.update({"GEMINI_API_KEY": key, "DRY_RUN": dry})
        proc = subprocess.run([sys.executable, "-c", "import generator as g; print(g.STUB_GEMINI, g.DRY_RUN)"], cwd=str(ROOT), env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.split()

    def flags_for(self, workflow, event, inputs=None):
        step = generator_step(workflow)
        key = value_of(step["env"]["GEMINI_API_KEY"], event, inputs)
        dry = value_of(step["env"]["DRY_RUN"], event, inputs)
        return self.module_flags(key, dry)

    def test_the_module_decides_stub_from_the_key_alone(self):
        self.assertEqual(self.module_flags("", "1"), ["True", "True"])
        self.assertEqual(self.module_flags("fake-key", "1"), ["False", "True"])

    def test_default_manual_practice_run_is_a_stub_run(self):
        for wf in CHANCE_WORKFLOWS:
            self.assertEqual(self.flags_for(wf, "workflow_dispatch", {"dry_run": True, "real_ai": False}), ["True", "True"], wf)

    def test_real_ai_practice_run_the_real_publish_and_the_schedule_are_not_stubs(self):
        self.assertEqual(self.flags_for("chanceblog.yml", "workflow_dispatch", {"dry_run": True, "real_ai": True}), ["False", "True"])
        self.assertEqual(self.flags_for("chanceblog.yml", "workflow_dispatch", {"dry_run": False, "real_ai": False}), ["False", "False"])
        self.assertEqual(self.flags_for("chanceblog.yml", "schedule"), ["False", "False"])


class GenerationBase(unittest.TestCase):
    LINK = "https://www.reuters.com/a"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name, value in (("DRY_RUN", True), ("STUB_UNSPLASH", True), ("POSTS_DIR", root / "_posts"), ("HISTORY_FILE", root / "history.json")):
            patcher = mock.patch.object(g, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(g, "now_kst", return_value=at(10, 12))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.model_calls = []
        self.client = self.make_client()

    def make_client(self):
        outer = self

        class Response:
            def __init__(self, text):
                self.text = text

        class Models:
            def generate_content(self, model, contents):
                outer.model_calls.append(model)
                return Response(json.dumps(long_post("연습 기사", GenerationBase.LINK), ensure_ascii=False))

        class Client:
            models = Models()
        return Client()

    def generate(self, stub):
        def fetch(editorial_lane=None, stats=None, deadline=None, clock=None):
            return [candidate("연습 기사", self.LINK)]
        report = {}
        with mock.patch.object(g, "STUB_GEMINI", stub), mock.patch.object(g, "get_client", return_value=self.client), \
                mock.patch.object(g, "fetch_news_items", fetch):
            value, out = run_captured(g.generate_blog_posts, slot=9, report=report)
        return value, report, out


class StubPracticeFlowTest(GenerationBase):
    def test_a_stub_practice_run_completes_without_touching_the_client(self):
        value, report, out = self.generate(stub=True)
        self.assertIsNotNone(value, out)
        self.assertEqual(report["outcome"], "PUBLISHED")
        self.assertEqual(self.model_calls, [])                                   # 클라이언트를 한 번도 부르지 않았다
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 0, "failed": 0})
        self.assertNotIn("Gemini 모델 호출 시도", out)

    def test_the_real_path_does_call_the_client_so_the_comparison_is_meaningful(self):
        value, report, out = self.generate(stub=False)
        self.assertIsNotNone(value, out)
        self.assertEqual(len(self.model_calls), 1)
        self.assertEqual(g.GEMINI_CALLS["attempts"], 1)

    def test_the_summary_says_whether_the_practice_run_used_fake_or_real_answers(self):
        with mock.patch.object(g, "STUB_GEMINI", True):
            stub_text = g.render_run_summary("workflow_dispatch", at(10, 12), None, {"outcome": "ALL_LANES_EMPTY", "lanes": []})
        self.assertIn("- AI 응답: 가짜(스텁) — Gemini를 호출하지 않았습니다", stub_text)
        self.assertIn("real_ai", stub_text)
        with mock.patch.object(g, "STUB_GEMINI", False):
            real_text = g.render_run_summary("workflow_dispatch", at(10, 12), None, {"outcome": "ALL_LANES_EMPTY", "lanes": []})
        self.assertIn("- AI 응답: 실제 Gemini 호출 — 연습 실행이지만 무료 한도를 씁니다", real_text)
        self.assertNotIn("가짜(스텁)", real_text)

    def test_a_practice_run_summary_does_not_read_like_a_publication(self):
        """독립 검증 V-12: 연습 실행은 아무것도 저장하지 않는데 `결과: PUBLISHED — 글을 만들었습니다`로 보이면 발행된 것처럼 읽힌다."""
        report = {"outcome": "PUBLISHED", "title": "연습 글", "paths": ["_posts/a.md"], "lanes": []}
        with mock.patch.object(g, "DRY_RUN", True):
            practice = g.render_run_summary("workflow_dispatch", at(10, 12), None, dict(report))
        self.assertIn("- 결과: **PUBLISHED** — 연습으로 글을 만들어 봤습니다(저장하지 않았습니다)", practice)
        self.assertNotIn("글을 만들었습니다", practice)
        with mock.patch.object(g, "DRY_RUN", False):
            real = g.render_run_summary("workflow_dispatch", at(10, 12), None, dict(report))
        self.assertIn("- 결과: **PUBLISHED** — 글을 만들었습니다", real)
        self.assertNotIn("연습으로", real)
        with mock.patch.object(g, "DRY_RUN", True):                   # 다른 결과의 문구는 연습이어도 그대로다
            empty = g.render_run_summary("workflow_dispatch", at(10, 12), None, {"outcome": "ALL_REJECTED", "lanes": []})
        self.assertIn(g.OUTCOME_TEXT["ALL_REJECTED"], empty)

    def test_a_real_publish_summary_has_no_ai_mode_line(self):
        with mock.patch.object(g, "DRY_RUN", False):
            text = g.render_run_summary("workflow_dispatch", at(10, 12), None, {"outcome": "ALL_LANES_EMPTY", "lanes": []})
        self.assertNotIn("AI 응답", text)

    def test_the_stub_path_is_still_the_keyless_dry_run_main_takes(self):
        """키가 없고 연습이면 main() 은 오류 없이 시작한다(키가 없는 실제 실행만 오류) — 기본값 변경이 기대는 기존 동작."""
        env = {k: v for k, v in os.environ.items() if k not in ("PIPELINE_PAUSE", "GITHUB_STEP_SUMMARY")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(g, "STUB_GEMINI", True), \
                mock.patch.object(g, "FIX_IMAGES", False), mock.patch.object(g, "EVENT_NAME", "workflow_dispatch"), \
                mock.patch.object(g, "generate_blog_posts", return_value=None) as gen:
            value, out = run_captured(g.main)
        self.assertIn("[DRY_RUN] 시작 (Gemini=스텁", out)
        gen.assert_called_once()


# ----------------------------------------------------------------------------
# 2) 기존 글 이미지 교체: 한 번에 처리하는 글 수 상한
# ----------------------------------------------------------------------------
class FixImagesCapTest(unittest.TestCase):
    def setUp(self):
        self.repairs, self.writes = [], []
        for name, value in (("DRY_RUN", False), ("STUB_GEMINI", True)):
            patcher = mock.patch.object(g, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def posts(self, n):
        return [{"path": Path(f"_posts/p{i:02d}.md"), "text": "---\ntitle: x\n---\n본문\n", "title": f"글 {i}", "image": "",
                 "tags": "", "category": ""} for i in range(n)]

    def run_fix(self, n, repair_result=lambda post: f"https://images.unsplash.com/photo-{post['title'].split()[-1]}", dry=False, stub=True):
        def repair(post, used):
            self.repairs.append(post["path"].name)
            return repair_result(post)
        with mock.patch.object(g, "load_posts", return_value=self.posts(n)), mock.patch.object(g, "repair", repair), \
                mock.patch.object(g, "write_text_atomic", lambda path, content: self.writes.append(Path(path).name)), \
                mock.patch.object(g, "trigger_download", lambda url: None), \
                mock.patch.object(g, "DRY_RUN", dry), mock.patch.object(g, "STUB_GEMINI", stub):
            return run_captured(g.fix_images)

    def test_the_cap_is_twenty(self):
        self.assertEqual(g.FIX_IMAGES_MAX_PER_RUN, 20)

    def test_over_the_cap_only_the_first_twenty_are_processed_and_the_rest_are_deferred_in_the_summary(self):
        summary, out = self.run_fix(25)
        self.assertEqual(self.repairs, [f"p{i:02d}.md" for i in range(20)])              # 오래된 글(앞)부터 20건
        self.assertEqual(len(self.writes), 20)
        self.assertEqual(summary, "이미지 점검: 완료: 문제 25건 중 20건 처리 / 교체 20건 / 건너뜀 0건 / "
                                  "나머지 5건은 다음 실행으로 넘김(한 번에 최대 20건)")
        self.assertIn("한 번에 최대 20건만 처리합니다. 나머지 5건은 다음 실행에서 처리합니다.", out)

    def test_exactly_at_the_cap_nothing_is_deferred(self):
        summary, out = self.run_fix(20)
        self.assertEqual(len(self.repairs), 20)
        self.assertEqual(summary, "이미지 점검: 완료: 문제 20건 / 교체 20건 / 건너뜀 0건")
        self.assertNotIn("다음 실행", out)

    def test_one_over_the_cap_defers_exactly_one(self):
        summary, out = self.run_fix(21)
        self.assertEqual(len(self.repairs), 20)
        self.assertIn("나머지 1건은 다음 실행으로 넘김", summary)
        self.assertIn("문제 21건 중 20건 처리", summary)
        self.assertIn("한 번에 최대 20건만 처리합니다. 나머지 1건은 다음 실행에서 처리합니다.", out)     # 독립 검증 XN10: 이월 1건일 때의 로그 줄

    def test_far_over_the_cap_still_processes_twenty_and_defers_the_rest(self):
        """독립 검증 XN11: 상한을 크게 넘어도(100건) 처리는 20건이고 나머지는 세어서 알린다."""
        summary, out = self.run_fix(100)
        self.assertEqual(self.repairs, [f"p{i:02d}.md" for i in range(20)])
        self.assertEqual(summary, "이미지 점검: 완료: 문제 100건 중 20건 처리 / 교체 20건 / 건너뜀 0건 / "
                                  "나머지 80건은 다음 실행으로 넘김(한 번에 최대 20건)")
        self.assertIn("한 번에 최대 20건만 처리합니다. 나머지 80건은 다음 실행에서 처리합니다.", out)

    def test_below_the_cap_the_old_summary_text_is_unchanged(self):
        summary, _ = self.run_fix(2)
        self.assertEqual(summary, "이미지 점검: 완료: 문제 2건 / 교체 2건 / 건너뜀 0건")
        none, _ = self.run_fix(0)
        self.assertEqual(none, "이미지 점검: 완료: 문제 0건 / 교체 0건 / 건너뜀 0건")

    def test_skipped_candidates_count_inside_the_batch_only(self):
        summary, _ = self.run_fix(25, repair_result=lambda post: None)
        self.assertEqual(self.writes, [])
        self.assertIn("교체 0건 / 건너뜀 20건 / 나머지 5건", summary)

    def test_dry_run_summary_reads_planned_replacements_out_of_the_batch(self):
        summary, out = self.run_fix(25, dry=True)
        self.assertEqual(summary, "이미지 점검: 완료: 교체 예정 25건 중 20건 처리 대상 / 교체 20건 / 건너뜀 0건 / "
                                  "나머지 5건은 다음 실행으로 넘김(한 번에 최대 20건) (DRY_RUN: 실제 변경 없음, 가짜 AI 검색어 사용)")
        small, _ = self.run_fix(3, dry=True)
        self.assertEqual(small, "이미지 점검: 완료: 교체 예정 3건 중 3건 처리 대상 / 교체 3건 / 건너뜀 0건 (DRY_RUN: 실제 변경 없음, 가짜 AI 검색어 사용)")

    def test_dry_run_with_the_real_ai_says_so(self):
        summary, _ = self.run_fix(2, dry=True, stub=False)
        self.assertTrue(summary.endswith("(DRY_RUN: 실제 변경 없음, 실제 Gemini 호출)"), summary)

    def test_the_cap_bounds_the_gemini_calls_of_a_run(self):
        """상한이 없으면 문제 글 25건에 Gemini 가 25번 불렸다. 이제 20번이다."""
        calls = []

        class Response:
            text = json.dumps({"image_queries": ["a b", "c d"]})

        class Models:
            def generate_content(self, model, contents):
                calls.append(model)
                return Response()

        class Client:
            models = Models()
        posts = self.posts(25)
        with mock.patch.object(g, "load_posts", return_value=posts), mock.patch.object(g, "get_client", return_value=Client()), \
                mock.patch.object(g, "STUB_GEMINI", False), mock.patch.object(g, "STUB_UNSPLASH", True), mock.patch.object(g, "DRY_RUN", True):
            summary, _ = run_captured(g.fix_images)
        self.assertEqual(len(calls), 20)
        self.assertIn("교체 예정 25건 중 20건 처리 대상", summary)

    def test_a_stub_run_makes_no_gemini_call_at_all(self):
        calls = []

        class Client:
            class models:
                @staticmethod
                def generate_content(model, contents):
                    calls.append(model)
        with mock.patch.object(g, "load_posts", return_value=self.posts(5)), mock.patch.object(g, "get_client", return_value=Client()), \
                mock.patch.object(g, "STUB_GEMINI", True), mock.patch.object(g, "STUB_UNSPLASH", True), mock.patch.object(g, "DRY_RUN", True):
            summary, _ = run_captured(g.fix_images)
        self.assertEqual(calls, [])
        self.assertIn("교체 예정 5건 중 5건 처리 대상", summary)


# ----------------------------------------------------------------------------
# 3) Chance 수동 실제 실행: 게시 시각·하루 상한을 따지지 않지만 막지 않고 경고만
# ----------------------------------------------------------------------------
class ManualOverCapTest(unittest.TestCase):
    TODAY = "2026-10-25"

    def setUp(self):
        for name, value in (("DRY_RUN", False), ("STUB_GEMINI", False), ("FIX_IMAGES", False), ("EVENT_NAME", "workflow_dispatch")):
            patcher = mock.patch.object(g, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(g, "now_kst", return_value=at(10, 12))
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.summary = Path(tmp.name) / "summary.md"
        env = {k: v for k, v in os.environ.items() if k != "PIPELINE_PAUSE"}
        env["GITHUB_STEP_SUMMARY"] = str(self.summary)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.generated = []

    def fake_generate(self, slot=None, allow_auto_topic=True, report=None, **kwargs):
        self.generated.append((slot, allow_auto_topic))
        report["outcome"] = "PUBLISHED"
        report.update(title="제목", source="Reuters", lane_label="기술·미래", paths=["_posts/a.md", "_posts/b.md"], lanes=[])
        return ("a", "b")

    def run_main(self, history, event="workflow_dispatch"):
        with mock.patch.object(g, "EVENT_NAME", event), mock.patch.object(g, "read_history", return_value=list(history)), \
                mock.patch.object(g, "generate_blog_posts", self.fake_generate):
            return run_captured(g.main)

    def summary_text(self):
        return self.summary.read_text(encoding="utf-8") if self.summary.exists() else ""

    def today(self, n):
        return [{"date": self.TODAY, "topic": f"주제 {i}", "slot": None} for i in range(n)]

    def test_the_cap_is_read_from_the_registry(self):
        reg = registry.load_registry()
        self.assertEqual(g.daily_cap(), registry.get_blog(reg, "chance")["limits"]["max_posts_per_day"])
        self.assertEqual(g.daily_cap(), 2)

    def test_at_the_cap_it_warns_but_still_makes_the_post(self):
        value, out = self.run_main(self.today(2))
        self.assertNotIsInstance(value, SystemExit)
        self.assertEqual(self.generated, [(None, True)])                          # 막지 않는다: 수동 경로 그대로 글을 만든다
        warnings = [line for line in out.splitlines() if line.startswith("::warning::")]
        self.assertEqual(warnings, ["::warning::수동 실행: 오늘(2026-10-25) 이미 2건이 게시되어 하루 상한(2건) 이상입니다. "
                                    "수동 실행은 게시 시각·하루 상한을 따지지 않고 글을 만듭니다(막지 않습니다)."])
        text = self.summary_text()
        self.assertIn("- 경고: 수동 실행은 게시 시각·하루 상한을 따지지 않습니다 — 오늘(2026-10-25) 이미 2건이 게시되어 상한(2건) 이상입니다", text)
        self.assertIn("글을 만들었습니다", text)

    def test_over_the_cap_the_real_count_is_shown(self):
        value, out = self.run_main(self.today(3))
        self.assertIn("이미 3건이 게시되어 하루 상한(2건)", out)
        self.assertEqual(len(self.generated), 1)

    def test_today_is_the_korean_date_even_right_after_midnight(self):
        """독립 검증 GN17·XN01: 한국 시각 00:00~08:59 는 UTC 로는 전날이다. 오늘 글을 세는 날짜가 UTC 날짜면 이 시간대에 경고가 틀린다."""
        with mock.patch.object(g, "now_kst", return_value=at(0, 30)):
            value, out = self.run_main(self.today(2))
            self.assertIn("오늘(2026-10-25) 이미 2건이 게시되어 하루 상한(2건)", out)
            value, out = self.run_main([{"date": "2026-10-24", "topic": f"어제 {i}", "slot": None} for i in range(3)])     # 어제 글은 오늘이 아니다
            self.assertNotIn("::warning::", out)
        with mock.patch.object(g, "now_kst", return_value=at(23, 59)):
            value, out = self.run_main(self.today(2))
            self.assertIn("오늘(2026-10-25) 이미 2건이", out)

    def test_below_the_cap_there_is_no_warning_and_no_summary_line(self):
        value, out = self.run_main(self.today(1))
        self.assertNotIn("::warning::", out)
        self.assertNotIn("상한", self.summary_text())
        value, out = self.run_main([])
        self.assertNotIn("::warning::", out)

    def test_only_todays_dict_entries_are_counted(self):
        history = ["문자열 항목", {"date": "2026-10-24", "topic": "어제"}, {"date": "2026-10-24", "topic": "어제2"}, {"topic": "날짜 없음"}] + self.today(1)
        value, out = self.run_main(history)
        self.assertNotIn("::warning::", out)
        self.assertEqual(len(self.generated), 1)

    def test_a_practice_run_never_warns_because_it_publishes_nothing(self):
        with mock.patch.object(g, "DRY_RUN", True):
            value, out = self.run_main(self.today(5))
        self.assertNotIn("::warning::", out)
        self.assertNotIn("상한", self.summary_text())

    def test_the_scheduled_run_uses_the_slot_judgement_not_this_warning(self):
        value, out = self.run_main(self.today(5), event="schedule")
        self.assertNotIn("하루 상한", out)
        self.assertNotIn("manual_over_cap", self.summary_text())

    def test_an_unreadable_registry_skips_the_warning_and_says_so(self):
        for broken in (registry.RegistryError("없음"), ):
            with mock.patch.object(registry, "load_registry", side_effect=broken):
                value, out = self.run_main(self.today(5))
            self.assertNotIn("::warning::", out)
            self.assertIn("하루 게시 상한을 읽지 못해 수동 실행의 상한 초과 경고를 건너뜁니다.", out)
            self.assertEqual(len(self.generated), 1)                              # 글 만들기는 그대로

    def test_a_registry_without_the_chance_blog_or_a_bad_cap_is_treated_as_unknown(self):
        for reg in ({"blogs": []}, {"defaults": {"limits": {"max_posts_per_day": "많이"}}, "blogs": [{"key": "chance"}]},
                    {"blogs": [{"key": "chance", "limits": {}}]}):
            with mock.patch.object(registry, "load_registry", return_value=reg):
                self.assertIsNone(g.daily_cap(), reg)

    def test_the_default_cap_applies_when_the_chance_entry_has_no_limits(self):
        reg = {"defaults": {"limits": {"max_posts_per_day": 7}}, "blogs": [{"key": "chance"}]}
        with mock.patch.object(registry, "load_registry", return_value=reg):
            self.assertEqual(g.daily_cap(), 7)


# ----------------------------------------------------------------------------
# 4) Blogger 수동 실행: dry_run 기본이 켜짐
# ----------------------------------------------------------------------------
class BloggerManualDefaultsTest(RunBase):
    def workflow_inputs(self):
        return load("blogger.yml")["on"]["workflow_dispatch"]["inputs"]

    def dry_env_for(self, event, dry_input=None):
        template = load("blogger.yml")["jobs"]["generate"]["env"]["DRY_RUN"]
        inputs = {} if dry_input is None else {"dry_run": dry_input}
        return value_of(template, event, event_inputs=inputs)

    def test_dry_run_is_on_by_default(self):
        inputs = self.workflow_inputs()
        self.assertEqual((inputs["dry_run"]["type"], inputs["dry_run"]["default"]), ("boolean", True))

    def test_the_descriptions_say_what_is_saved_and_what_uses_the_daily_cap(self):
        inputs = self.workflow_inputs()
        description = inputs["dry_run"]["description"]
        for fragment in ("기본 켜짐", "가짜 AI 응답", "호출하지 않", "체크를 풀면", "초안", "커밋", "하루 상한"):
            self.assertIn(fragment, description)
        # 독립 검증 BL07: 낱말이 아니라 뜻을 고정한다 — 연습은 하루 상한을 쓰지 않고, 체크를 풀면 쓴다(앞뒤가 뒤바뀌면 운영자가 상한을 소진한다)
        self.assertIn("파일 저장·게시·하루 상한 소진 없이 로그만 남깁니다", description)
        self.assertIn("체크를 풀면 실제 Gemini로 글을 만들어 초안을 저장소에 커밋하고 그날 하루 상한을 씁니다", description)

    def test_the_default_value_reaches_the_runner_as_a_dry_run_and_scheduled_runs_never_are(self):
        default = self.workflow_inputs()["dry_run"]["default"]
        self.assertEqual(self.dry_env_for("workflow_dispatch", str(default).lower()), "true")   # GitHub 은 boolean 입력을 'true'/'false' 로 넘긴다
        self.assertEqual(self.dry_env_for("workflow_dispatch", "false"), "false")
        self.assertEqual(self.dry_env_for("schedule"), "false")

    def test_a_default_manual_run_saves_nothing_and_calls_no_gemini(self):
        """입력을 건드리지 않고 Run workflow 를 누른 것과 같다: 파일·이력이 생기지 않고 가짜 AI 응답을 쓴다."""
        dry = self.dry_env_for("workflow_dispatch", str(self.workflow_inputs()["dry_run"]["default"]).lower())
        code, out = self.go(env={"DRY_RUN": dry, "GEMINI_API_KEY": "fake-llm-key", "BLOGGER_PUBLISH": "off"}, llm=None)
        self.assertEqual(code, 0, out)
        self.assertIn("[DRY_RUN]", out)
        self.assertEqual(self.history(), [])
        self.assertEqual(self.drafts(), [])

    def test_unchecking_the_dry_run_saves_a_draft_and_uses_the_daily_cap(self):
        dry = self.dry_env_for("workflow_dispatch", "false")
        code, out = self.go(env={"DRY_RUN": dry, "GEMINI_API_KEY": "fake-llm-key", "BLOGGER_PUBLISH": "off"})
        self.assertEqual(code, 0, out)
        self.assertEqual(self.history()[-1]["status"], "draft")
        self.assertEqual(len(self.drafts()), 1)
        code, out = self.go(env={"DRY_RUN": dry, "GEMINI_API_KEY": "fake-llm-key", "BLOGGER_PUBLISH": "off"})
        self.assertIn("[SKIP] code=DAILY_CAP", out)                                  # 그날 하루 상한을 썼다


# ----------------------------------------------------------------------------
# 5) 이슈 수정: PIPELINE_PAUSE
# ----------------------------------------------------------------------------
ENV = {"GITHUB_RUN_NUMBER": "5"}
OLD_SENTENCE = "문의는 old@example.com 으로 보내 주세요."
NEW_SENTENCE = "문의는 new@example.com 으로 보내 주세요."
LAYOUT = "layout | 섹션/레이아웃 변경 (해당 페이지 안에서만)"
IMAGE_URL = "https://shine88pc.github.io/chanceblog/posts/2026/10/18/kr-111111/"


class IssueEditPauseTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_edit_root(self._tmp.name)
        io_dir = tempfile.TemporaryDirectory()      # 처리기의 입출력 파일은 저장소 사본 밖에 둔다(저장소가 바뀌지 않았는지 비교하려고)
        self.addCleanup(io_dir.cleanup)
        self.io = Path(io_dir.name)
        self.llm_calls, self.picker_calls = [], []

    def llm(self, prompt):
        self.llm_calls.append(prompt)
        return json.dumps({"patches": [{"old": "두 번째 문단입니다.", "new": "고친 문단입니다."}]}), "m"

    def picker(self, queries, used):
        self.picker_calls.append(list(queries))
        return "https://images.unsplash.com/photo-777?auto=format&fit=crop&w=1000&q=80"

    def go(self, iss, pause="true", **kw):
        env = dict(ENV)
        if pause is not None:
            env["PIPELINE_PAUSE"] = pause
        kw.setdefault("llm", self.llm)
        kw.setdefault("image_picker", self.picker)
        return runner.process_issue(iss, self.root, env=env, **kw)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}

    def literal_issue(self):
        return issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE))

    def test_a_valid_literal_request_is_paused_without_touching_anything(self):
        before = self.snapshot()
        res = self.go(self.literal_issue())
        self.assertEqual((res.status, res.exit_code, res.files, res.branch), ("paused", 0, [], ""))
        self.assertEqual(self.snapshot(), before)
        self.assertIn("일시정지 중", res.comment)
        self.assertIn("PIPELINE_PAUSE", res.comment)
        self.assertEqual((res.edit_type, res.target), ("text_change", "about.md"))

    def test_an_ai_request_never_reaches_the_llm_while_paused(self):
        res = self.go(issue(page_body(edit=LAYOUT, after="둘째 문단 아래에 강조 문장을 넣어 주세요")))
        self.assertEqual(res.status, "paused")
        self.assertEqual(self.llm_calls, [])

    def test_an_image_request_never_reaches_the_llm_or_the_image_search_while_paused(self):
        res = self.go(issue(image_body(IMAGE_URL, "소방관 구조 활동"), labels=("blog-control", "edit:image"), title="[이미지 변경] x"))
        self.assertEqual(res.status, "paused")
        self.assertEqual((self.llm_calls, self.picker_calls), ([], []))

    def test_without_the_switch_the_same_requests_are_processed(self):
        res = self.go(self.literal_issue(), pause=None)
        self.assertEqual(res.status, "ok")
        res = self.go(issue(page_body(edit=LAYOUT, after="둘째 문단 아래에 강조 문장을 넣어 주세요")), pause=None)
        self.assertEqual(res.status, "ok")
        self.assertEqual(len(self.llm_calls), 1)

    def test_every_truthy_value_the_other_pipelines_accept_pauses_and_the_falsy_ones_do_not(self):
        for value in sorted(run_mod._TRUE) + [" TRUE ", "On", "YES", "1 "]:
            with self.subTest(value=value):
                self.assertEqual(self.go(self.literal_issue(), pause=value).status, "paused")
        for value in ("", "0", "false", "no", "off", "  ", "pause", "2"):
            with self.subTest(value=value):
                self.assertEqual(self.go(self.literal_issue(), pause=value).status, "ok")
                (self.root / "about.md").write_bytes(ABOUT.encode("utf-8"))                # 다음 값을 위해 되돌린다

    def test_the_value_set_is_the_same_as_the_blogger_runner_and_chance(self):
        self.assertEqual(runner.PAUSE_VALUES, run_mod._TRUE)
        for value in sorted(run_mod._TRUE):
            self.assertTrue(runner.pause_on({"PIPELINE_PAUSE": value}))
        self.assertFalse(runner.pause_on({}))
        self.assertFalse(runner.pause_on({"PIPELINE_PAUSE": None}))

    def test_a_malformed_request_is_still_rejected_with_its_reason_not_paused(self):
        """AI·이미지 검색을 부르지 않는 거부·무시는 정지 중에도 그대로다(요청자가 이유를 알 수 있다)."""
        res = self.go(issue(page_body(after="")))
        self.assertEqual(res.status, "rejected")
        self.assertEqual(self.go(issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE), assoc="NONE")).status, "ignored")

    def test_the_pause_comment_names_the_workflow_by_its_current_korean_name(self):
        res = self.go(self.literal_issue())
        self.assertIn(load("issue-edit.yml")["name"], res.comment)

    def test_the_pause_comment_says_what_was_not_done_and_how_to_run_it_again(self):
        """독립 검증 V-04·RN15: 수동 실행은 `연습 실행`이 기본 켜짐이라, 정지를 풀고 그냥 다시 실행하면 연습만 돌아 PR 이 안 생긴다.
        코멘트가 그 체크를 풀라고 말해야 하고(그 입력이 실제로 그 이름인지도 확인), 안 한 일을 정확히 말해야 한다."""
        res = self.go(self.literal_issue())
        self.assertIn("저장소 변수 `PIPELINE_PAUSE` 가 켜져 있어 이 요청을 처리하지 않았습니다", res.comment)
        self.assertIn("(AI·이미지 검색도 부르지 않았고 저장소는 변경되지 않았습니다)", res.comment)
        self.assertIn("변수를 지운 뒤 Actions 의 `이슈 수정 요청 처리(수정안 PR 만들기)` 에서 이 이슈 번호로, "
                      "`연습 실행` 체크를 풀고 다시 실행해 주세요.", res.comment)
        description = load("issue-edit.yml")["on"]["workflow_dispatch"]["inputs"]["dry_run"]["description"]
        self.assertTrue(description.startswith("연습 실행"), description)          # 코멘트가 가리키는 입력의 이름

    def test_an_already_processed_issue_is_a_duplicate_even_while_paused(self):
        """독립 검증 RN12: 이미 처리한 이슈를 정지 중에 다시 실행하면 '일시정지 중'이 아니라 '이미 처리한 이슈'다(중복 확인이 정지 확인보다 먼저)."""
        res = self.go(self.literal_issue(), remote_refs=["0123456789abcdef0123456789abcdef01234567\trefs/heads/issue-edit/12-about-r5"])
        self.assertEqual(res.status, "duplicate")
        self.assertIn("이미 처리한 이슈입니다", res.comment)
        labeled = self.go(issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE),
                                labels=("blog-control", "edit:page", "issue-edit-done")), remote_refs=[])
        self.assertEqual(labeled.status, "duplicate")
        self.assertEqual(self.go(self.literal_issue(), remote_refs=[]).status, "paused")      # 처리한 적이 없으면 정지가 먼저 알린다

    def test_write_outputs_has_the_status_the_workflow_reads(self):
        res = self.go(self.literal_issue())
        out = self.io / "out"
        runner.write_outputs(res, out)
        self.assertEqual((out / "status.txt").read_text(encoding="utf-8").strip(), "paused")
        self.assertEqual((out / "files.txt").read_text(encoding="utf-8"), "")
        self.assertIn("일시정지 중", (out / "comment.md").read_text(encoding="utf-8"))

    def run_cli(self, pause, extra=()):
        f = self.io / "issue.json"
        f.write_text(json.dumps(self.literal_issue()), encoding="utf-8")
        out = self.io / "cli"
        env = {k: v for k, v in os.environ.items() if k not in ("PIPELINE_PAUSE", "GEMINI_API_KEY", "UNSPLASH_ACCESS_KEY")}
        if pause is not None:
            env["PIPELINE_PAUSE"] = pause
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(buf):
            code = runner.main(["--issue-file", str(f), "--out", str(out), "--root", str(self.root), *extra])
        return code, buf.getvalue(), out

    def test_the_cli_exits_zero_leaves_a_tagged_note_and_changes_nothing(self):
        """하드닝의 로그 정책: 러너가 내는 모든 줄은 이슈 머리로 시작하고 `::` 줄이 없다 — 그래서 알림은 `::notice::` 가 아니라 머리를 단 참고 줄이다."""
        before = self.snapshot()
        code, text, out = self.run_cli("on")
        self.assertEqual(code, 0)
        self.assertEqual((out / "status.txt").read_text(encoding="utf-8").strip(), "paused")
        lines = text.splitlines()
        tag = "[issue-edit] issue=#12 author=@shine88pc(OWNER)"
        for line in lines:
            self.assertTrue(line.startswith(tag), line)
            self.assertFalse(line.lstrip().startswith("::"), line)
        notes = [line for line in lines if line.startswith(tag + "   * 저장소 변수 PIPELINE_PAUSE")]
        self.assertEqual(len(notes), 1, lines)
        self.assertIn("Variables 에서 PIPELINE_PAUSE 를 지우세요", notes[0])
        self.assertIn("status=paused", lines[0])
        self.assertEqual(self.snapshot(), before)

    def test_the_cli_is_not_paused_without_the_variable(self):
        code, text, out = self.run_cli(None, extra=["--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual((out / "status.txt").read_text(encoding="utf-8").strip(), "ok")
        self.assertNotIn("PIPELINE_PAUSE", text)

    def test_the_workflow_hands_the_variable_to_the_runner_and_posts_the_paused_comment(self):
        wf = load("issue-edit.yml")
        steps = wf["jobs"]["edit"]["steps"]
        edit = next(s for s in steps if s.get("id") == "edit")
        self.assertEqual(edit["env"]["PIPELINE_PAUSE"], "${{ vars.PIPELINE_PAUSE }}")
        comment = next(s for s in steps if s.get("name") == "이슈에 결과 코멘트")
        self.assertIn("rejected|error|duplicate|paused) cp \"$out/comment.md\" \"$final\"", comment["run"])    # 하드닝의 duplicate 와 같은 분기
        self.assertEqual(wf["permissions"], {"contents": "read"})                  # 최상위 권한은 그대로


# ----------------------------------------------------------------------------
# 6) 다른 워크플로·정기 경로는 바뀌지 않았다
# ----------------------------------------------------------------------------
class UntouchedPathsTest(unittest.TestCase):
    def test_the_schedule_and_the_commit_and_deploy_steps_are_untouched(self):
        chance = load("chanceblog.yml")
        # 2026-10-26 운영자 승인(D-59): 매시 17분에 47분 틱을 더했다. 게시는 슬롯 규칙(하루 2편)이 지킨다.
        self.assertEqual(chance["on"]["schedule"], [{"cron": "17 * * * *"}, {"cron": "47 * * * *"}])
        steps = chance["jobs"]["build"]["steps"]
        commit = next(s for s in steps if s.get("id") == "commit")
        self.assertEqual(commit["if"], "${{ !(github.event_name == 'workflow_dispatch' && inputs.dry_run) }}")
        deploy = steps[-1]
        self.assertEqual(deploy["if"], "steps.commit.outputs.pushed == 'true'")

    def test_blogger_keeps_its_cron_and_matrix_flow(self):
        wf = load("blogger.yml")
        self.assertEqual(wf["on"]["schedule"], [{"cron": "0 2 * * *"}])
        # 독립 검증 V-06: 목록 전체가 아니라 필수 입력을 포함하는지만 본다 — 인증 점검 입력(auth_check) 같은 새 입력이 더해져도 이 시험이 깨지지 않게
        for name in ("blog", "topic", "dry_run", "publish"):
            self.assertIn(name, wf["on"]["workflow_dispatch"]["inputs"])

    def test_pause_variable_is_still_passed_to_the_other_workflows(self):
        for wf in ("chanceblog.yml", "chance-fix-images.yml"):
            self.assertEqual(generator_step(wf)["env"]["PIPELINE_PAUSE"], "${{ vars.PIPELINE_PAUSE }}")
        self.assertEqual(load("blogger.yml")["jobs"]["generate"]["env"]["PIPELINE_PAUSE"], "${{ vars.PIPELINE_PAUSE }}")

    def test_the_stub_llm_still_answers_without_a_network(self):
        text, model = stub_llm("주제: 테스트 주제입니다")
        self.assertEqual(model, "stub")


# ----------------------------------------------------------------------------
# 7) 독립 검증 V-07: 식과 `run:` 스크립트를 직접 고정한다(정기 실행은 입력과 무관하게 게시·커밋 경로 그대로)
# ----------------------------------------------------------------------------
class BloggerPublishSwitchTest(unittest.TestCase):
    """BL09·BL10: 정기 실행은 BLOGGER_PUBLISH 를 비워 레지스트리 mode 를 따르고, 수동 실행은 `publish` 3택(off·draft·publish)을 그대로 넘긴다.
    즉시 게시는 운영자가 `publish` 를 직접 고를 때뿐이고 기본값은 `draft`(Blogger 초안함)다."""

    CHOICES = ("off", "draft", "publish")

    def publish_input(self):
        return load("blogger.yml")["on"]["workflow_dispatch"]["inputs"]["publish"]

    def publish_value(self, event, publish=None):
        step = next(s for s in load("blogger.yml")["jobs"]["generate"]["steps"] if "BLOGGER_PUBLISH" in s.get("env", {}))
        event_inputs = None if publish is None else {"publish": publish}
        return value_of(step["env"]["BLOGGER_PUBLISH"], event, event_inputs=event_inputs)

    def test_a_scheduled_run_leaves_it_empty_so_the_registry_mode_decides(self):
        self.assertEqual(self.publish_value("schedule"), "")
        for value in (*self.CHOICES, "true", "false"):                       # 정기 실행에는 입력이 없지만 있어도 무시한다(모드는 레지스트리가 정한다)
            self.assertEqual(self.publish_value("schedule", value), "", value)

    def test_a_manual_run_passes_the_chosen_value_and_only_an_explicit_publish_publishes(self):
        for choice in self.CHOICES:
            self.assertEqual(self.publish_value("workflow_dispatch", choice), choice)
        # 러너가 그 값을 읽는 방식: 즉시 게시('on')는 publish 를 고를 때뿐이다
        self.assertEqual({choice: run_mod.publish_policy(None, {"BLOGGER_PUBLISH": choice}) for choice in self.CHOICES},
                         {"off": "off", "draft": "draft", "publish": "on"})

    def test_the_publish_input_is_a_three_way_choice_whose_default_never_publishes(self):
        """GitHub 는 생략된 입력(API 로 부른 경우 포함)에 기본값을 채운다. 그 기본값이 즉시 게시면 입력을 안 건드린 실행이 게시한다."""
        publish = self.publish_input()
        self.assertEqual((publish["type"], publish["options"], publish["default"]), ("choice", list(self.CHOICES), "draft"))


SHIM = """#!/usr/bin/env bash
echo "$(basename "$0") $*" >> "$STEP_CALLS"
if [ "$(basename "$0")" = "git" ] && [ "$1" = "diff" ]; then exit 1; fi
if [ "$(basename "$0")" = "gh" ] && [ "$1" = "pr" ] && [ "$2" = "create" ]; then echo "https://example.invalid/pr/1"; fi
exit 0
"""


def find_bash():
    """워크플로의 `run:` 스크립트를 실제로 돌릴 bash. Windows 에서는 WSL 런처(System32 의 bash.exe)가 아니라 Git 의 bash 를 찾는다. 없으면 None."""
    candidates = [shutil.which("bash")]
    if os.name == "nt":
        candidates += [r"C:\Program Files\Git\usr\bin\bash.exe", r"C:\Program Files\Git\bin\bash.exe"]
    for path in candidates:
        if path and os.path.exists(path) and "system32" not in path.lower():
            return path
    return None


BASH = find_bash()


@unittest.skipUnless(BASH, "bash 가 필요합니다(CI 의 Linux 에서는 항상 실행됩니다)")
class WorkflowStepScriptTest(unittest.TestCase):
    """워크플로의 `run:` 스크립트를 가짜 git·gh·python 으로 실제 실행해 상태별로 어떤 명령이 불리는지 본다(GitHub·저장소에는 아무것도 쓰지 않는다)."""

    def step(self, workflow, job, name):
        return next(s for s in load(workflow)["jobs"][job]["steps"] if s.get("name") == name)

    def run_script(self, script, env, files=None, dirs=()):
        """(종료 코드, 부른 명령 목록, 표준 출력, 임시 폴더, 작업 폴더 안 파일들)을 돌려준다."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            work, bin_dir, out_dir = tmp / "work", tmp / "bin", tmp / "issue-edit"
            for folder in (work, bin_dir, out_dir):
                folder.mkdir()
            for name in dirs:
                (work / name).mkdir()
            for name, text in (files or {}).items():
                target = (out_dir if name.startswith("out/") else work) / name.removeprefix("out/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8", newline="\n")
            for name in ("git", "gh", "python"):
                shim = bin_dir / name
                shim.write_text(SHIM, encoding="utf-8", newline="\n")
                shim.chmod(0o755)          # 실행 권한이 없으면 Linux 의 bash 는 PATH 에서 이 파일을 건너뛰고 진짜 git 을 부른다
            calls = tmp / "calls.log"
            calls.write_text("", encoding="utf-8")
            full_env = {k: v for k, v in os.environ.items() if k not in ("DRY_RUN", "GITHUB_REF_NAME", "ISSUE_NUMBER")}
            full_env.update({"STEP_CALLS": calls.as_posix(), "RUNNER_TEMP": tmp.as_posix(), **env})
            # 가짜 명령 폴더를 bash 안에서 PATH 맨 앞에 둔다(Windows 의 Git bash 는 시작할 때 자기 git 을 PATH 앞에 끼워 넣으므로 환경 변수로는 부족하다)
            prelude = 'export PATH="$(cd ../bin && pwd):$PATH"\n'
            proc = subprocess.run([BASH, "-c", prelude + script], cwd=str(work), env=full_env, capture_output=True, text=True,
                                  encoding="utf-8", timeout=120)
            made = {p.name: p.read_text(encoding="utf-8") for p in out_dir.iterdir() if p.is_file()}
            return proc.returncode, calls.read_text(encoding="utf-8").strip().splitlines(), proc.stdout, made

    # --- Blogger: 변경 사항 커밋(BL06) ---
    def commit_step(self, dry_run):
        script = self.step("blogger.yml", "generate", "변경 사항 커밋")["run"]
        env = {"BLOG_KEY": "blogger_macat", "HISTORY_FILE": "blogger_history.json", "CONTENT_DIR": "_blogger_drafts", "GITHUB_REF_NAME": "main"}
        if dry_run is not None:
            env["DRY_RUN"] = dry_run
        return self.run_script(script, env, files={"blogger_history.json": "[]", "_blogger_drafts/a.md": "x"})

    def test_a_dry_run_commits_and_pushes_nothing(self):
        code, calls, out, _ = self.commit_step("true")
        self.assertEqual((code, calls), (0, []))
        self.assertIn("DRY_RUN — 커밋 생략", out)

    def test_a_real_run_commits_and_pushes_to_the_branch_it_ran_on(self):
        for dry_run in ("false", None, "", "TRUE", "1"):          # 정확히 'true' 만 연습이다(워크플로의 DRY_RUN 식은 'true'·'false' 만 만든다)
            code, calls, out, _ = self.commit_step(dry_run)
            self.assertEqual(code, 0, (dry_run, out))
            self.assertEqual(calls[:2], ["git config user.name github-actions[bot]",
                                         "git config user.email 41898282+github-actions[bot]@users.noreply.github.com"], dry_run)
            self.assertIn("git add -- blogger_history.json", calls, dry_run)
            self.assertIn("git add -- _blogger_drafts", calls, dry_run)
            self.assertTrue(any(call.startswith("git commit -m ") and "[blogger_macat]" in call for call in calls), (dry_run, calls))
            self.assertIn("git push origin HEAD:main", calls, dry_run)
            self.assertNotIn("DRY_RUN", out, dry_run)

    # --- 이슈 수정: 브랜치·커밋·PR 생성(IE04), 이슈에 결과 코멘트 ---
    def issue_env(self):
        return {"ISSUE_NUMBER": "12", "DRY_RUN": "false", "DEFAULT_BRANCH": "main", "GITHUB_REPOSITORY": "owner/repo", "GH_TOKEN": "FAKE"}

    def issue_files(self, status, **extra):
        files = {"out/status.txt": status + "\n", "out/comment.md": f"[{status}] 코멘트 본문\n", "out/branch.txt": "issue-edit/12-about-r5\n",
                 "out/files.txt": "about.md\n", "out/commit_msg.txt": "msg\n", "out/pr_title.txt": "title\n", "out/pr_body.md": "body\n",
                 "out/summary.md": "- 요약\n"}
        files.update({"out/" + name: text for name, text in extra.items()})
        return files

    def test_only_a_status_ok_result_reaches_the_branch_commit_and_pr_step(self):
        script = self.step("issue-edit.yml", "edit", "브랜치·커밋·PR 생성")["run"]
        for status in ("paused", "rejected", "duplicate", "error", "ignored", "weird"):
            code, calls, out, _ = self.run_script(script, self.issue_env(), files=self.issue_files(status))
            self.assertEqual((code, calls), (0, []), status)
            self.assertIn("수정안 없음 — PR 을 만들지 않습니다", out, status)

    def test_a_status_ok_result_makes_the_branch_the_commit_the_push_and_the_pr(self):
        script = self.step("issue-edit.yml", "edit", "브랜치·커밋·PR 생성")["run"]
        code, calls, out, made = self.run_script(script, self.issue_env(), files=self.issue_files("ok"))
        self.assertEqual(code, 0, out)
        expected = ["git config user.name ", "git config user.email ", "git switch -c issue-edit/12-about-r5", "git add -- about.md",
                    "python -m pipeline.edits.runner --verify-staged ", "git commit -F ", "git push origin issue-edit/12-about-r5",
                    "gh pr create --base main --head issue-edit/12-about-r5 ", "gh workflow run guardrails.yml --ref issue-edit/12-about-r5"]
        self.assertEqual(len(calls), len(expected), calls)
        for call, prefix in zip(calls, expected):
            self.assertTrue(call.startswith(prefix), (call, prefix))
        self.assertEqual(made["pr_url.txt"].strip(), "https://example.invalid/pr/1")

    def comment_step(self, status, **extra):
        script = self.step("issue-edit.yml", "edit", "이슈에 결과 코멘트")["run"]
        files = self.issue_files(status, **extra) if status is not None else {}
        if status is None:                                      # 처리기가 죽어 status.txt 자체가 없는 경우
            files = {"out/comment.md": "x\n"}
        return self.run_script(script, self.issue_env(), files=files)

    def test_the_four_comment_statuses_post_the_comment_file_as_it_is(self):
        for status in ("paused", "rejected", "duplicate", "error"):
            code, calls, out, made = self.comment_step(status)
            self.assertEqual(code, 0, (status, out))
            self.assertEqual(len(calls), 1, (status, calls))
            self.assertTrue(calls[0].startswith("gh issue comment 12 --body-file "), calls[0])
            self.assertEqual(made["final_comment.md"], f"[{status}] 코멘트 본문\n", status)
            self.assertFalse(any("issue edit" in call for call in calls), status)           # 표식 라벨은 붙이지 않는다

    def test_an_ignored_issue_gets_no_comment_and_a_missing_result_gets_the_failure_notice(self):
        code, calls, out, _ = self.comment_step("ignored")
        self.assertEqual((code, calls), (0, []))
        self.assertIn("처리 대상이 아니어서 코멘트하지 않습니다.", out)
        for status in ("weird", None):
            code, calls, out, made = self.comment_step(status)
            self.assertEqual(code, 0, (status, out))
            self.assertEqual(len(calls), 1, (status, calls))
            self.assertIn("처리 결과를 만들지 못했습니다", made["final_comment.md"], status)

    def test_a_status_ok_result_comments_and_labels_the_issue_only_when_a_pr_or_compare_link_exists(self):
        code, calls, out, made = self.comment_step("ok", **{"pr_url.txt": "https://example.invalid/pr/1\n"})
        self.assertEqual(code, 0, out)
        self.assertIn("수정안을 PR 로 만들었습니다", made["final_comment.md"])
        self.assertIn("- PR: https://example.invalid/pr/1", made["final_comment.md"])
        self.assertEqual([call.split(" --")[0] for call in calls], ["gh issue comment 12", "gh issue edit 12"])
        self.assertTrue(calls[1].endswith("--add-label issue-edit-done"), calls[1])
        code, calls, out, made = self.comment_step("ok", **{"compare_url.txt": "https://github.com/owner/repo/compare/main...x?expand=1\n"})
        self.assertIn("수정 브랜치를 만들었습니다", made["final_comment.md"])
        self.assertEqual(len(calls), 2)
        code, calls, out, made = self.comment_step("ok")                 # 브랜치·PR 단계가 실패한 경우
        self.assertIn("브랜치·PR 단계에서 실패했습니다", made["final_comment.md"])
        self.assertEqual(len(calls), 1)                                  # 코멘트만 — 표식 라벨은 붙이지 않는다(다시 처리할 수 있게)


# ----------------------------------------------------------------------------
# 8) 독립 검증 V-03: 이제 Blogger 수동 실행은 `연습 실행`이 기본 켜짐이라 체크를 풀지 않으면 `publish`(off·draft·publish 3택)가 무엇이든 아무것도 저장되지 않는다 — 안내 문구가 그 사실을 따라간다
# ----------------------------------------------------------------------------
class ManualRunGuidanceTest(unittest.TestCase):
    def lines(self, doc, needle):
        return [line for line in (ROOT / doc).read_text(encoding="utf-8").splitlines() if needle in line]

    def test_every_blogger_first_run_guidance_tells_to_uncheck_the_practice_run(self):
        # `publish` 가 off/draft/publish 3택이 된 뒤의 첫 실행 안내: HANDLER 는 재개 절차(`publish=draft`)와 §10 5번 4(`publish`를 `draft`(기본값)로 두면)
        for doc, needle in (("HANDLER.md", "`publish=draft`"), ("HANDLER.md", "`publish`를 `draft`(기본값)"),
                            ("docs/ENGINEERING_GUIDE.md", "**L3 초안**"), ("docs/ARCHITECTURE.md", "`blog=<key>`")):
            found = self.lines(doc, needle)
            self.assertTrue(found, (doc, needle))
            for line in found:
                self.assertRegex(line, r"`연습 실행` 체크(를)? ?(풀|푼|해제)", (doc, needle))

    def test_the_architecture_first_run_row_names_the_publish_choices(self):
        """`publish` 는 off/draft/publish 3택이다. 첫 실행 행은 초안함 업로드(`publish=draft`)를 안내하고, 시크릿을 등록하기 전에는 저장소 초안만
        남기는 `publish=off` 를 안내한다. 즉시 게시(`publish=publish`)는 처음에 고르라고 하지 않는다."""
        row = self.lines("docs/ARCHITECTURE.md", "`blog=<key>`")[0]
        self.assertIn("`publish=draft`", row)
        self.assertIn("`publish=off`", row)
        self.assertNotIn("publish=publish", row)

    def test_the_docs_say_that_practice_runs_still_search_unsplash(self):
        paragraph = next(line for line in self.lines("docs/ARCHITECTURE.md", "수동 실행의 기본값과 정지 스위치"))
        register = next(line for line in self.lines("docs/DEFECT_REGISTER.md", "**D-51**"))
        for text in (paragraph, register):
            self.assertIn("Unsplash 이미지 검색은 실제로", text)
            self.assertIn("시간당 한도", text)

    def test_the_docs_state_the_known_limits_of_the_manual_run_defaults(self):
        paragraph = next(line for line in self.lines("docs/ARCHITECTURE.md", "수동 실행의 기본값과 정지 스위치"))
        register = next(line for line in self.lines("docs/DEFECT_REGISTER.md", "**D-54**"))
        for text in (paragraph, register):
            self.assertIn("하루 3편", text)                       # V-05: 슬롯은 수동 글을 세지 않아 09시 슬롯 글이 있는 날 낮의 수동 게시 뒤 18시에 또 만들어진다
        for fragment in ("`gh label create --force` 4건", "굶김", "교체 0건 / 건너뜀 N건"):                # V-13
            self.assertIn(fragment, paragraph)

    def test_the_defect_register_checklist_matches_the_current_behaviour(self):
        """V-02: 정지 시험의 기대 결과에 `::notice::`는 없다(로그 정책 #19) — 머리를 단 참고 줄이다. V-11: 이미지 교체도 Gemini 를 쓴다."""
        text = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if not line.startswith("| **D-")      # 결함 행이 아니라 관측 체크리스트의 행
                   and "PIPELINE_PAUSE=true" in line and "수정안 PR 만들기" in line and "일시정지 중" in line)
        self.assertNotIn("::notice::", row)
        self.assertIn("status=paused", row)
        self.assertIn("issue=#", row)
        d49 = next(line for line in text.splitlines() if line.startswith("| **D-49**"))
        self.assertNotIn("이미지 교체는 Gemini를 쓰지 않는데", d49)
        self.assertIn("make_image_queries", d49)


if __name__ == "__main__":
    unittest.main()
