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

    def test_without_publish_secrets_only_a_draft_is_saved(self):
        code, out = self.go(env={})
        self.assertEqual(code, 0)
        self.assertEqual(self.history()[-1]["status"], "generated_unpublished")
        self.assertIn("SECRETS", json.dumps(self.history()[-1], ensure_ascii=False))
        self.assertEqual(len(self.drafts()), 1)
        self.assertIn("시크릿이 없어", out)

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
        self.go(env={})
        code, out = self.go(env={})
        self.assertEqual(code, 0)
        self.assertIn("상한", out)
        self.assertEqual(len(self.history()), 1)
        self.go(env={}, extra=["--topic", "수동으로 지정한 오늘의 생활 습관 주제"])
        self.assertEqual(len(self.history()), 2)
        self.assertEqual(self.history()[-1]["topic_source"], "override")

    def test_next_day_runs_again(self):
        self.go(env={})
        later = datetime(2026, 10, 22, 2, 0, tzinfo=timezone.utc)
        self.go(env={}, now=later)
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
        self.go(env={})
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
        code = run_mod.run(["--blog", "blogger_macat", "--root", str(self.root)], environ={}, now=NOW,
                           llm=None, rng=random.Random(1), out=out.append)
        self.assertEqual(code, 2)
        self.assertIn("GEMINI_API_KEY", "\n".join(out))

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
        self.go(env={})
        self.assertEqual(len(self.history()), run_mod.HISTORY_KEEP)


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
