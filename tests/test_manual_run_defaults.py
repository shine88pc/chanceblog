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
from test_run import FakePublisher, RunBase
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
        summary, _ = self.run_fix(21)
        self.assertEqual(len(self.repairs), 20)
        self.assertIn("나머지 1건은 다음 실행으로 넘김", summary)
        self.assertIn("문제 21건 중 20건 처리", summary)

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

    def test_dry_run_is_on_by_default_and_publish_is_off(self):
        inputs = self.workflow_inputs()
        self.assertEqual((inputs["dry_run"]["type"], inputs["dry_run"]["default"]), ("boolean", True))
        self.assertEqual((inputs["publish"]["type"], inputs["publish"]["default"]), ("boolean", False))

    def test_the_descriptions_say_what_is_saved_and_what_uses_the_daily_cap(self):
        inputs = self.workflow_inputs()
        description = inputs["dry_run"]["description"]
        for fragment in ("기본 켜짐", "가짜 AI 응답", "호출하지 않", "체크를 풀면", "초안", "커밋", "하루 상한"):
            self.assertIn(fragment, description)
        self.assertIn("연습 실행을 풀었을 때만", inputs["publish"]["description"])

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

    def test_the_publish_switch_expression_is_unchanged(self):
        step = next(s for s in load("blogger.yml")["jobs"]["generate"]["steps"] if s.get("run", "").startswith("python -m pipeline.run"))
        self.assertEqual(value_of(step["env"]["BLOGGER_PUBLISH"], "workflow_dispatch", event_inputs={"publish": "true"}), "on")
        self.assertEqual(value_of(step["env"]["BLOGGER_PUBLISH"], "workflow_dispatch", event_inputs={"publish": "false"}), "off")
        self.assertEqual(value_of(step["env"]["BLOGGER_PUBLISH"], "schedule"), "")

    def test_publish_does_nothing_while_the_practice_run_is_on(self):
        """입력 설명대로 publish 는 연습 실행을 풀었을 때만 뜻이 있다: 연습이 켜져 있으면 publish 를 체크해도 게시하지 않는다."""
        pub = FakePublisher()
        env = {"DRY_RUN": "true", "BLOGGER_PUBLISH": "on", "GEMINI_API_KEY": "k", "BLOGGER_BLOG_ID": "1", "BLOGGER_CLIENT_ID": "c",
               "BLOGGER_CLIENT_SECRET": "s", "BLOGGER_REFRESH_TOKEN": "r"}
        code, out = self.go(env=env, publisher=pub)
        self.assertEqual(code, 0, out)
        self.assertEqual(pub.published, [])
        self.assertEqual(self.history(), [])


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
        self.assertEqual(chance["on"]["schedule"], [{"cron": "17 * * * *"}])
        steps = chance["jobs"]["build"]["steps"]
        commit = next(s for s in steps if s.get("id") == "commit")
        self.assertEqual(commit["if"], "${{ !(github.event_name == 'workflow_dispatch' && inputs.dry_run) }}")
        deploy = steps[-1]
        self.assertEqual(deploy["if"], "steps.commit.outputs.pushed == 'true'")

    def test_blogger_keeps_its_cron_and_matrix_flow(self):
        wf = load("blogger.yml")
        self.assertEqual(wf["on"]["schedule"], [{"cron": "0 2 * * *"}])
        self.assertEqual(list(wf["on"]["workflow_dispatch"]["inputs"]), ["blog", "topic", "dry_run", "publish"])

    def test_pause_variable_is_still_passed_to_the_other_workflows(self):
        for wf in ("chanceblog.yml", "chance-fix-images.yml"):
            self.assertEqual(generator_step(wf)["env"]["PIPELINE_PAUSE"], "${{ vars.PIPELINE_PAUSE }}")
        self.assertEqual(load("blogger.yml")["jobs"]["generate"]["env"]["PIPELINE_PAUSE"], "${{ vars.PIPELINE_PAUSE }}")

    def test_the_stub_llm_still_answers_without_a_network(self):
        text, model = stub_llm("주제: 테스트 주제입니다")
        self.assertEqual(model, "stub")


if __name__ == "__main__":
    unittest.main()
