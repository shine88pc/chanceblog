import json
import random
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from pipeline import run as run_mod
from pipeline.llm import LLMError
from pipeline.publishers.base import PublishError, PublishResult
from pipeline.stubs import stub_llm

REAL = _bootstrap.ROOT
NOW = datetime(2026, 10, 21, 2, 0, tzinfo=timezone.utc)  # KST 2026-10-21 11:00
FULL_ENV = {"GEMINI_API_KEY": "k", "BLOGGER_BLOG_ID": "123", "BLOGGER_CLIENT_ID": "cid",
            "BLOGGER_CLIENT_SECRET": "cs", "BLOGGER_REFRESH_TOKEN": "rt"}
# 게시하지 않고 초안만 만드는 실행(수동 실행에서 publish 를 끈 것과 같다). 게시용 시크릿이 필요 없다.
NO_PUBLISH = {"BLOGGER_PUBLISH": "0"}
PUBLISH_SECRET_NAMES = ("BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN")


def make_root(tmp, mode="auto"):
    root = Path(tmp)
    (root / "pipeline" / "profiles").mkdir(parents=True)
    reg = json.loads((REAL / "pipeline" / "blogs.json").read_text(encoding="utf-8"))
    for blog in reg["blogs"]:
        if blog["key"] == "blogger_macat":
            blog["mode"] = mode
    (root / "pipeline" / "blogs.json").write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    shutil.copy(REAL / "pipeline" / "profiles" / "blogger_practical_ko.json", root / "pipeline" / "profiles")
    (root / ".github" / "editorial").mkdir(parents=True)
    shutil.copy(REAL / ".github" / "editorial" / "BLOGGER_PROMPT.md", root / ".github" / "editorial")
    for rel in (".github/workflows/chanceblog.yml", ".github/workflows/blogger.yml", "generator.py",
                "blogger_generator.py", ".github/editorial/CHANCE_BLOG_TEMPLATE.md"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return root


class FakePublisher:
    def __init__(self, fail=None):
        self.fail, self.published, self.health_calls = fail, [], 0

    def healthcheck(self):
        self.health_calls += 1
        return {}

    def publish(self, title, html, labels, draft=False):
        if self.fail:
            raise self.fail
        self.published.append({"title": title, "html": html, "labels": labels, "draft": draft})
        return PublishResult(post_id="p1", url="https://macat.example/p1")


class RunBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_root(self._tmp.name)

    def go(self, env=None, llm=stub_llm, publisher=None, extra=(), now=NOW, seed=1, root=None):
        out = []
        factory = (lambda blog, environ: publisher) if publisher is not None else None
        code = run_mod.run(["--blog", "blogger_macat", "--root", str(root or self.root), *extra],
                           environ={} if env is None else env, now=now, llm=llm, publisher_factory=factory,
                           rng=random.Random(seed), out=out.append)
        return code, "\n".join(out)

    def history(self):
        path = self.root / "blogger_history.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def drafts(self):
        folder = self.root / "_blogger_drafts"
        return sorted(folder.glob("*.md")) if folder.exists() else []


class FlowTest(RunBase):
    def test_publishes_when_secrets_exist(self):
        pub = FakePublisher()
        code, _ = self.go(env=FULL_ENV, publisher=pub)
        self.assertEqual(code, 0)
        self.assertEqual(pub.health_calls, 1)
        self.assertEqual(len(pub.published), 1)
        sent = pub.published[0]
        self.assertIn("AI의 도움", sent["html"])          # 면책·AI 사용 문구가 항상 붙는다
        self.assertNotIn("<script", sent["html"].lower())
        entry = self.history()[-1]
        self.assertEqual((entry["status"], entry["url"], entry["post_id"]), ("posted", "https://macat.example/p1", "p1"))
        self.assertEqual((entry["blog"], entry["date"], entry["v"]), ("blogger_macat", "2026-10-21", 1))
        self.assertEqual(len(self.drafts()), 1)
        self.assertIn("status: posted", self.drafts()[0].read_text(encoding="utf-8"))

    def test_publish_target_without_publish_secrets_fails_before_any_llm_call(self):
        """D-25: 게시 대상인데 게시용 시크릿이 없으면 글을 만들기 전에 종료 2(빨강). 예전에는 초안만 저장하고 초록이었다."""
        calls = []

        def spy(prompt):
            calls.append(prompt)
            return stub_llm(prompt)
        code, out = self.go(env={"GEMINI_API_KEY": "k"}, llm=spy)
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])                      # Gemini 호출(= 무료 한도)을 쓰지 않는다
        self.assertEqual(self.history(), [])             # 미게시 초안으로 하루 상한을 소진하지 않는다
        self.assertEqual(self.drafts(), [])
        self.assertIn("[SKIP] code=SECRETS_MISSING", out)
        self.assertIn("::error::[blogger_macat]", out)
        for name in PUBLISH_SECRET_NAMES:                # 시크릿 '이름'을 안내한다
            self.assertIn(name, out)
        self.assertNotIn("GEMINI_API_KEY", out)          # LLM 키는 있으므로 목록에 없다

    def test_missing_secret_names_never_include_values(self):
        env = {"GEMINI_API_KEY": "gemini-secret-value", "BLOGGER_BLOG_ID": "blog-secret-value"}
        code, out = self.go(env=env)
        self.assertEqual(code, 2)
        self.assertNotIn("gemini-secret-value", out)
        self.assertNotIn("blog-secret-value", out)
        self.assertNotIn("BLOGGER_BLOG_ID,", out.replace(" ", ""))  # 등록된 것은 누락 목록에 없다

    def test_dry_run_only_warns_about_missing_publish_secrets(self):
        """등록 점검용: DRY_RUN 은 시크릿이 없어도 끝까지 가고 경고만 한다."""
        code, out = self.go(env={}, extra=["--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("::warning::[blogger_macat] (DRY_RUN이라 계속합니다)", out)
        self.assertEqual(self.history(), [])

    def test_publish_off_needs_no_publish_secrets(self):
        code, out = self.go(env=NO_PUBLISH)
        self.assertEqual(code, 0)
        self.assertEqual(self.history()[-1]["status"], "draft")
        self.assertEqual(len(self.drafts()), 1)
        self.assertIn("draft/off", out)

    def test_draft_mode_never_publishes(self):
        root = make_root(tempfile.mkdtemp(), mode="draft")
        self.addCleanup(shutil.rmtree, str(root), True)
        pub = FakePublisher()
        code, _ = self.go(env=FULL_ENV, publisher=pub, root=root)
        self.assertEqual(code, 0)
        self.assertEqual(pub.published, [])
        self.assertEqual(json.loads((root / "blogger_history.json").read_text(encoding="utf-8"))[-1]["status"], "draft")

    def test_explicit_publish_flag_overrides_draft_mode(self):
        root = make_root(tempfile.mkdtemp(), mode="draft")
        self.addCleanup(shutil.rmtree, str(root), True)
        pub = FakePublisher()
        self.go(env={**FULL_ENV, "BLOGGER_PUBLISH": "1"}, publisher=pub, root=root)
        self.assertEqual(len(pub.published), 1)

    def test_publish_off_overrides_auto_mode(self):
        pub = FakePublisher()
        self.go(env={**FULL_ENV, "BLOGGER_PUBLISH": "0"}, publisher=pub)
        self.assertEqual(pub.published, [])
        self.assertEqual(self.history()[-1]["status"], "draft")

    def test_publish_failure_exits_1_but_keeps_draft_and_history(self):
        pub = FakePublisher(fail=PublishError("token expired", code="auth_expired"))
        code, out = self.go(env=FULL_ENV, publisher=pub)
        self.assertEqual(code, 1)
        entry = self.history()[-1]
        self.assertEqual(entry["status"], "publish_failed")
        self.assertIn("auth_expired", json.dumps(entry["reasons"]))
        self.assertEqual(len(self.drafts()), 1)

    def test_daily_cap_blocks_second_run_but_manual_topic_bypasses(self):
        self.go(env=NO_PUBLISH)
        code, out = self.go(env=NO_PUBLISH)
        self.assertEqual(code, 0)
        self.assertIn("상한", out)
        self.assertIn("[SKIP] code=DAILY_CAP", out)
        self.assertIn("::notice::", out)
        self.assertIn("draft", out)                      # 어떤 기록이 상한을 채웠는지 보인다
        self.assertEqual(len(self.history()), 1)
        self.go(env=NO_PUBLISH, extra=["--topic", "수동으로 지정한 오늘의 생활 습관 주제"])
        self.assertEqual(len(self.history()), 2)
        self.assertEqual(self.history()[-1]["topic_source"], "override")

    def test_next_day_runs_again(self):
        self.go(env=NO_PUBLISH)
        later = datetime(2026, 10, 22, 2, 0, tzinfo=timezone.utc)
        self.go(env=NO_PUBLISH, now=later)
        self.assertEqual([e["date"] for e in self.history()], ["2026-10-21", "2026-10-22"])
        self.assertNotEqual(self.history()[0]["topic"], self.history()[1]["topic"])  # 쿨다운으로 같은 주제 반복 안 함


class GateIntegrationTest(RunBase):
    def test_rejected_after_max_attempts(self):
        calls = []

        def short(prompt):
            calls.append(prompt)
            return "제목: 충분히 긴 제목입니다 정말로\n라벨: 가\n내용:\n<p>너무 짧음</p>", "m"
        code, out = self.go(env=FULL_ENV, llm=short, publisher=FakePublisher())
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 3)
        entry = self.history()[-1]
        self.assertEqual((entry["status"], entry["attempts"]), ("rejected", 3))
        self.assertEqual(self.drafts(), [])  # 탈락 글은 저장·게시하지 않는다

    def test_feedback_is_given_and_second_attempt_can_pass(self):
        prompts = []

        def flaky(prompt):
            prompts.append(prompt)
            if len(prompts) == 1:
                text, model = stub_llm(prompt)
                return text.replace("<p>처음부터", "<p>이 방법으로 완치됩니다. 처음부터"), model
            return stub_llm(prompt)
        pub = FakePublisher()
        code, _ = self.go(env=FULL_ENV, llm=flaky, publisher=pub)
        self.assertEqual(code, 0)
        self.assertEqual(len(prompts), 2)
        self.assertIn("[이전 시도에서 고쳐야 할 점]", prompts[1])
        self.assertIn("BANNED", prompts[1])
        self.assertEqual(self.history()[-1]["attempts"], 2)
        self.assertEqual(len(pub.published), 1)

    def test_script_in_llm_output_never_reaches_the_publisher(self):
        def evil(prompt):
            text, model = stub_llm(prompt)
            return text.replace("<h3>1.", "<script>steal()</script><img src=x onerror=alert(1)><h3>1."), model
        pub = FakePublisher()
        self.go(env=FULL_ENV, llm=evil, publisher=pub)
        html = pub.published[0]["html"].lower()
        self.assertNotIn("<script", html)
        self.assertNotIn("onerror", html)
        self.assertNotIn("steal()", html)

    def test_llm_failure_exits_1_and_is_recorded(self):
        def down(prompt):
            raise LLMError("all models failed")
        code, _ = self.go(env=FULL_ENV, llm=down)
        self.assertEqual(code, 1)
        self.assertEqual(self.history()[-1]["status"], "llm_failed")

    def test_no_topic_is_recorded_and_exits_0(self):
        seeds = json.loads((REAL / "pipeline" / "profiles" / "blogger_practical_ko.json").read_text(encoding="utf-8"))["seed_topics"]
        (self.root / "blogger_history.json").write_text(
            json.dumps([{"topic": t, "date": "2026-10-20", "status": "posted"} for t in seeds], ensure_ascii=False),
            encoding="utf-8")
        code, _ = self.go(env=FULL_ENV, llm=lambda prompt: ("[]", "m"))
        self.assertEqual(code, 0)
        self.assertEqual(self.history()[-1]["status"], "skipped_no_topic")

    def test_cross_blog_titles_are_avoided(self):
        seeds = json.loads((REAL / "pipeline" / "profiles" / "blogger_practical_ko.json").read_text(encoding="utf-8"))["seed_topics"]
        # Chance 이력에 시드 하나만 빼고 전부 이미 있다 → 남은 하나만 선택돼야 한다
        (self.root / "history.json").write_text(json.dumps(seeds[:-1], ensure_ascii=False), encoding="utf-8")
        self.go(env=NO_PUBLISH)
        self.assertEqual(self.history()[-1]["topic"], seeds[-1])


class GuardTest(RunBase):
    def test_kill_switch(self):
        code, out = self.go(env={**FULL_ENV, "PIPELINE_PAUSE": "true"}, publisher=FakePublisher())
        self.assertEqual(code, 0)
        self.assertIn("일시정지", out)
        self.assertEqual(self.history(), [])
        self.assertEqual(self.drafts(), [])

    def test_mode_off_is_a_noop(self):
        root = make_root(tempfile.mkdtemp(), mode="off")
        self.addCleanup(shutil.rmtree, str(root), True)
        code, out = self.go(env=FULL_ENV, publisher=FakePublisher(), root=root)
        self.assertEqual(code, 0)
        self.assertFalse((root / "blogger_history.json").exists())

    def test_dry_run_writes_nothing_and_publishes_nothing(self):
        pub = FakePublisher()
        before = {p for p in self.root.rglob("*")}
        code, out = self.go(env=FULL_ENV, publisher=pub, extra=["--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(pub.published, [])
        self.assertEqual({p for p in self.root.rglob("*")}, before)
        self.assertIn("DRY_RUN", out)

    def test_missing_llm_key_is_a_config_error(self):
        out = []
        code = run_mod.run(["--blog", "blogger_macat", "--root", str(self.root)], environ=dict(NO_PUBLISH), now=NOW,
                           llm=None, rng=random.Random(1), out=out.append)
        self.assertEqual(code, 2)
        text = "\n".join(out)
        self.assertIn("GEMINI_API_KEY", text)
        self.assertIn("::error::", text)
        self.assertIn("[SKIP] code=SECRETS_MISSING", text)

    def test_corrupt_history_fails_closed(self):
        (self.root / "blogger_history.json").write_text("{not json", encoding="utf-8")
        code, out = self.go(env=FULL_ENV, publisher=FakePublisher())
        self.assertEqual(code, 1)
        self.assertEqual((self.root / "blogger_history.json").read_text(encoding="utf-8"), "{not json")  # 덮어쓰지 않음

    def test_unknown_blog_and_unsupported_platform(self):
        out = []
        code = run_mod.run(["--blog", "nope", "--root", str(self.root)], environ={}, now=NOW, llm=stub_llm, out=out.append)
        self.assertEqual(code, 2)
        out.clear()
        code = run_mod.run(["--blog", "chance", "--root", str(self.root)], environ={}, now=NOW, llm=stub_llm, out=out.append)
        self.assertEqual(code, 2)
        self.assertIn("blogger", "\n".join(out))

    def test_invalid_registry_is_a_config_error(self):
        reg_path = self.root / "pipeline" / "blogs.json"
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["blogs"][1]["mode"] = "yolo"
        reg_path.write_text(json.dumps(reg), encoding="utf-8")
        code, out = self.go(env=FULL_ENV, publisher=FakePublisher())
        self.assertEqual(code, 2)
        self.assertIn("레지스트리 검증 실패", out)

    def test_history_is_trimmed(self):
        many = [{"topic": f"옛 주제 {i}", "date": "2020-01-01", "status": "posted"} for i in range(250)]
        (self.root / "blogger_history.json").write_text(json.dumps(many, ensure_ascii=False), encoding="utf-8")
        self.go(env=NO_PUBLISH)
        self.assertEqual(len(self.history()), run_mod.HISTORY_KEEP)


class VisibilityTest(RunBase):
    """초록인데 아무 일도 안 일어나는 경로마다 [SKIP] 한 줄·알림 주석·실행 요약이 남는지(D-25~D-27)."""

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.summary_path = Path(tmp.name) / "summary.md"

    def env(self, **extra):
        return {"GITHUB_STEP_SUMMARY": str(self.summary_path), **extra}

    def summary(self):
        return self.summary_path.read_text(encoding="utf-8") if self.summary_path.exists() else ""

    def use_all_seeds(self):
        seeds = json.loads((REAL / "pipeline" / "profiles" / "blogger_practical_ko.json").read_text(
            encoding="utf-8"))["seed_topics"]
        (self.root / "blogger_history.json").write_text(
            json.dumps([{"topic": t, "date": "2026-10-20", "status": "posted"} for t in seeds], ensure_ascii=False),
            encoding="utf-8")

    def test_pause_leaves_a_skip_line_and_a_summary(self):
        code, out = self.go(env=self.env(**FULL_ENV, PIPELINE_PAUSE="true"), publisher=FakePublisher())
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=PAUSED", out)
        self.assertIn("PAUSED", self.summary())

    def test_mode_off_leaves_a_skip_line_and_a_summary(self):
        root = make_root(tempfile.mkdtemp(), mode="off")
        self.addCleanup(shutil.rmtree, str(root), True)
        code, out = self.go(env=self.env(**FULL_ENV), publisher=FakePublisher(), root=root)
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=MODE_OFF", out)
        self.assertIn("MODE_OFF", self.summary())

    def test_daily_cap_summary_says_unpublished_drafts_count(self):
        self.go(env=self.env(**NO_PUBLISH))
        self.summary_path.unlink()
        code, out = self.go(env=self.env(**NO_PUBLISH))
        self.assertEqual(code, 0)
        self.assertIn("DAILY_CAP", self.summary())
        self.assertIn("게시되지 않은 초안도 상한에 포함", self.summary())

    def test_exhausted_topics_is_a_warning_not_a_failure(self):
        self.use_all_seeds()
        code, out = self.go(env=self.env(**FULL_ENV), llm=lambda prompt: ("[]", "m"))
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=NO_TOPIC", out)
        self.assertIn("::warning::[blogger_macat]", out)
        self.assertEqual(self.history()[-1]["status"], "skipped_no_topic")
        self.assertIn("NO_TOPIC", self.summary())

    def test_topic_expansion_llm_failure_is_an_infra_failure(self):
        """시드를 다 쓴 뒤 주제 확장 호출이 실패하면 '주제 없음'(초록)이 아니라 인프라 실패(종료 1)다(E12)."""
        self.use_all_seeds()

        def down(prompt):
            raise LLMError("all models failed")
        code, out = self.go(env=self.env(**FULL_ENV), llm=down)
        self.assertEqual(code, 1)
        self.assertIn("[SKIP] code=EXPAND_FAILED", out)
        self.assertIn("::error::[blogger_macat]", out)
        entry = self.history()[-1]
        self.assertEqual(entry["status"], "llm_failed")
        self.assertIn("expand_failed", json.dumps(entry["reasons"]))
        self.assertIn("EXPAND_FAILED", self.summary())

    def test_llm_failure_is_an_error_annotation_and_the_message_is_masked(self):
        leaked = "AIza" + "x" * 30  # 런타임에 조합한다(실제 비밀처럼 보이는 리터럴 금지)

        def down(prompt):
            raise LLMError(f"request failed for {leaked}")
        code, out = self.go(env=self.env(**FULL_ENV), llm=down)
        self.assertEqual(code, 1)
        self.assertIn("[SKIP] code=LLM_FAILED", out)
        self.assertIn("::error::[blogger_macat]", out)
        self.assertNotIn(leaked, out)
        self.assertNotIn(leaked, json.dumps(self.history(), ensure_ascii=False))
        self.assertIn("LLM_FAILED", self.summary())

    def test_gate_rejection_is_a_warning_with_a_summary(self):
        def short(prompt):
            return "제목: 충분히 긴 제목입니다 정말로\n라벨: 가\n내용:\n<p>너무 짧음</p>", "m"
        code, out = self.go(env=self.env(**FULL_ENV), llm=short, publisher=FakePublisher())
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=GATE_REJECTED", out)
        self.assertIn("::warning::[blogger_macat]", out)
        self.assertIn("GATE_REJECTED", self.summary())

    def test_publish_failure_is_an_error_annotation(self):
        pub = FakePublisher(fail=PublishError("token expired", code="auth_expired"))
        code, out = self.go(env=self.env(**FULL_ENV), publisher=pub)
        self.assertEqual(code, 1)
        self.assertIn("[SKIP] code=PUBLISH_FAILED", out)
        self.assertIn("reason=auth_expired", out)
        self.assertIn("::error::[blogger_macat] 게시에 실패했습니다(auth_expired)", out)

    def test_missing_publish_secrets_leave_a_summary_with_names_only(self):
        code, out = self.go(env=self.env(GEMINI_API_KEY="k"))
        self.assertEqual(code, 2)
        text = self.summary()
        self.assertIn("SECRETS_MISSING", text)
        for name in PUBLISH_SECRET_NAMES:
            self.assertIn(name, text)

    def test_dry_run_summary(self):
        code, out = self.go(env=self.env(**FULL_ENV), publisher=FakePublisher(), extra=["--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("DRY_RUN", self.summary())

    def test_warning_annotations_never_embed_llm_text(self):
        """게이트 탈락 사유(LLM 글에서 나온 문자열)가 ::workflow-command:: 줄에 들어가면 안 된다."""
        def evil(prompt):
            return "제목: ::error::위조된 명령 제목입니다 충분히 길게\n라벨: 가\n내용:\n<p>짧음</p>", "m"
        code, out = self.go(env=self.env(**FULL_ENV), llm=evil, publisher=FakePublisher())
        for line in out.splitlines():
            if line.startswith("::"):
                self.assertNotIn("위조된 명령", line)


class PolicyTest(unittest.TestCase):
    def test_publish_policy_values(self):
        for cli, env, expected in ((None, {}, "auto"), (None, {"BLOGGER_PUBLISH": "1"}, "on"),
                                   (None, {"BLOGGER_PUBLISH": "0"}, "off"), ("off", {"BLOGGER_PUBLISH": "1"}, "off"),
                                   ("on", {}, "on"), ("auto", {"BLOGGER_PUBLISH": "0"}, "auto")):
            self.assertEqual(run_mod.publish_policy(cli, env), expected)

    def test_prompt_template_requires_topic_placeholder(self):
        blog = {"prompt": ".github/editorial/BLOGGER_PROMPT.md"}
        self.assertIn("{topic}", run_mod.load_prompt_template(REAL, blog))


if __name__ == "__main__":
    unittest.main()
