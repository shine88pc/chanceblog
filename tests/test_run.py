import json
import random
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from pipeline import gates, registry
from pipeline import run as run_mod
from pipeline.llm import LLMError
from pipeline.publishers.base import PublishError, PublishResult
from pipeline.stubs import stub_llm

REAL = _bootstrap.ROOT
NOW = datetime(2026, 10, 21, 2, 0, tzinfo=timezone.utc)  # KST 2026-10-21 11:00
FULL_ENV = {"GEMINI_API_KEY": "k", "BLOGGER_BLOG_ID": "123", "BLOGGER_CLIENT_ID": "cid",
            "BLOGGER_CLIENT_SECRET": "cs", "BLOGGER_REFRESH_TOKEN": "rt"}
# 실제 워크플로(.github/workflows/blogger.yml)가 넘기는 이름. 레지스트리의 역할 이름(llm_api_key·blog_id·client_id·
# client_secret·refresh_token)에 PIPELINE_SECRET_ 을 붙인 것이고, 값은 FULL_ENV 와 같다. BLOGGER_*·GEMINI_* 는 없다.
WORKFLOW_ENV = {"PIPELINE_SECRET_LLM_API_KEY": FULL_ENV["GEMINI_API_KEY"],
                "PIPELINE_SECRET_BLOG_ID": FULL_ENV["BLOGGER_BLOG_ID"],
                "PIPELINE_SECRET_CLIENT_ID": FULL_ENV["BLOGGER_CLIENT_ID"],
                "PIPELINE_SECRET_CLIENT_SECRET": FULL_ENV["BLOGGER_CLIENT_SECRET"],
                "PIPELINE_SECRET_REFRESH_TOKEN": FULL_ENV["BLOGGER_REFRESH_TOKEN"]}
# 게시하지 않고 초안만 만드는 실행(수동 실행에서 publish 를 끈 것과 같다). 게시용 시크릿이 필요 없다.
NO_PUBLISH = {"BLOGGER_PUBLISH": "0"}
PUBLISH_SECRET_NAMES = ("BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN")


def make_root(tmp, mode="auto", lang="ko"):
    """임시 저장소. lang="ko"(기본)는 실제 레지스트리의 blogger_macat(영문 프로필)을 한국어 프로필·프롬프트로 바꿔 놓는다 —
    이 파일의 실행 흐름 시험은 한국어 스텁·한국어 프로필로 돌린다. lang="en"은 실제 레지스트리 그대로(영문 프로필)다."""
    root = Path(tmp)
    (root / "pipeline" / "profiles").mkdir(parents=True)
    reg = json.loads((REAL / "pipeline" / "blogs.json").read_text(encoding="utf-8"))
    for blog in reg["blogs"]:
        if blog["key"] == "blogger_macat":
            blog["mode"] = mode
            if lang == "ko":
                blog.update(languages=["ko"], profile="blogger_practical_ko", prompt=".github/editorial/BLOGGER_PROMPT.md")
    (root / "pipeline" / "blogs.json").write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    for name in ("blogger_practical_ko.json", "blogger_practical_en.json"):
        shutil.copy(REAL / "pipeline" / "profiles" / name, root / "pipeline" / "profiles")
    (root / ".github" / "editorial").mkdir(parents=True)
    for name in ("BLOGGER_PROMPT.md", "BLOGGER_PROMPT_EN.md"):
        shutil.copy(REAL / ".github" / "editorial" / name, root / ".github" / "editorial")
    # 워크플로 파일은 name 한 줄만 있는 스텁이다: 레지스트리 검증이 블로그의 channel.label 과 워크플로 name 의 `[라벨] ` 접두사가 같은지 읽는다
    stubs = {".github/workflows/chanceblog.yml": 'name: "[Chance] 글 자동 작성·게시"\n',
             ".github/workflows/blogger.yml": 'name: "[Blogger] 글 자동 작성(초안함 업로드)"\n'}
    for rel in (".github/workflows/chanceblog.yml", ".github/workflows/blogger.yml", "generator.py",
                "blogger_generator.py", ".github/editorial/CHANCE_BLOG_TEMPLATE.md"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stubs.get(rel, ""), encoding="utf-8")
    return root


# 레지스트리의 blogger_macat 주소. 인증 점검이 blogs.get 이 돌려준 주소와 이 값을 비교한다.
BLOG_URL = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), "blogger_macat")["url"]


class FakePublisher:
    """check: healthcheck() 가 일으킬 예외(인증 점검 실패 시나리오), blog_url: blogs.get 이 돌려주는 주소, result: publish() 의 결과."""

    def __init__(self, fail=None, check=None, blog_url=BLOG_URL, result=None, notes=()):
        self.fail, self.check, self.blog_url, self.result = fail, check, blog_url, result
        self.published, self.health_calls = [], 0
        self.notes = list(notes)      # 어댑터가 남기는 한 줄 경고(예: 중복 글 확인 실패)

    def healthcheck(self):
        self.health_calls += 1
        if self.check:
            raise self.check
        return {"name": "테스트 블로그", "url": self.blog_url}

    def publish(self, title, html, labels, draft=False):
        if self.fail:
            raise self.fail
        self.published.append({"title": title, "html": html, "labels": labels, "draft": draft})
        return self.result or PublishResult(post_id="p1", url="https://macat.example/p1")


_FAKE = object()


class RunBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_root(self._tmp.name)

    def go(self, env=None, llm=stub_llm, publisher=_FAKE, extra=(), now=NOW, seed=1, root=None):
        """publisher: 생략하면 인증 점검을 통과하는 가짜 게시자(업로드·게시 실행은 글 생성 전에 Blogger 를 점검하므로 항상 필요하다).
        None 이면 러너가 기본 게시자를 만든다(그때는 BloggerPublisher 를 mock.patch 로 바꿔 쓴다)."""
        out = []
        if publisher is _FAKE:
            publisher = FakePublisher()
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

    def test_workflow_secret_names_alone_are_enough_to_publish(self):
        """실제 워크플로는 BLOGGER_*·GEMINI_API_KEY 가 아니라 PIPELINE_SECRET_<역할> 이름으로만 시크릿을 넘긴다. 그 이름만으로
        사전 점검·LLM 키·게시자 생성이 모두 통과해 게시까지 가야 한다(다른 run 테스트는 전부 BLOGGER_* 이름을 직접 넣는다)."""
        workflow = (REAL / ".github" / "workflows" / "blogger.yml").read_text(encoding="utf-8")
        passed = set(re.findall(r"^\s+(PIPELINE_SECRET_[A-Z_]+):", workflow, re.M))
        roles = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), "blogger_macat")["secrets"]
        self.assertEqual(passed, {"PIPELINE_SECRET_" + role.upper() for role in roles})  # 워크플로가 넘기는 이름 = 러너가 읽는 이름
        self.assertEqual(passed, set(WORKFLOW_ENV))
        seen, created = {}, []

        class SpyPublisher(FakePublisher):
            def __init__(self, blog_id, client_id, client_secret, refresh_token):
                super().__init__()
                seen["publisher"] = (blog_id, client_id, client_secret, refresh_token)
                created.append(self)

        def spy_llm_factory(api_key, models, max_retries=2):
            seen["llm_key"] = api_key
            return stub_llm
        with mock.patch("pipeline.publishers.blogger.BloggerPublisher", SpyPublisher), \
                mock.patch.object(run_mod, "make_gemini_llm", spy_llm_factory):
            code, out = self.go(env=WORKFLOW_ENV, llm=None, publisher=None)   # None: 러너가 키로 Gemini 호출 객체·기본 게시자를 직접 만든다
        self.assertEqual(code, 0, out)
        self.assertEqual(seen["llm_key"], FULL_ENV["GEMINI_API_KEY"])
        self.assertEqual(seen["publisher"], tuple(FULL_ENV[name] for name in PUBLISH_SECRET_NAMES))
        self.assertEqual(len(created[0].published), 1)
        self.assertEqual(self.history()[-1]["status"], "posted")

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
        self.assertIn("저장소 파일에만 초안을 저장", out)

    def test_draft_mode_uploads_to_the_blogger_drafts_never_publishes_live(self):
        """mode draft + 게시용 시크릿 4종 → Blogger 초안함에 올린다(isDraft). 즉시 게시(draft=False)는 하지 않는다."""
        root = make_root(tempfile.mkdtemp(), mode="draft")
        self.addCleanup(shutil.rmtree, str(root), True)
        pub = FakePublisher()
        code, _ = self.go(env=FULL_ENV, publisher=pub, root=root)
        self.assertEqual(code, 0)
        self.assertEqual([item["draft"] for item in pub.published], [True])
        self.assertEqual(json.loads((root / "blogger_history.json").read_text(encoding="utf-8"))[-1]["status"], "draft_uploaded")

    def test_explicit_publish_flag_overrides_draft_mode(self):
        root = make_root(tempfile.mkdtemp(), mode="draft")
        self.addCleanup(shutil.rmtree, str(root), True)
        pub = FakePublisher()
        self.go(env={**FULL_ENV, "BLOGGER_PUBLISH": "1"}, publisher=pub, root=root)
        self.assertEqual([item["draft"] for item in pub.published], [False])

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

    def test_pause_leaves_a_skip_line_a_notice_and_a_summary(self):
        code, out = self.go(env=self.env(**FULL_ENV, PIPELINE_PAUSE="true"), publisher=FakePublisher())
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=PAUSED", out)
        self.assertIn("PAUSED", self.summary())
        # 변수를 켜 놓고 잊어도 Actions 화면에 보이도록 ::notice:: 한 줄(어떤 변수를 어디서 지우는지 포함)
        notices = [line for line in out.splitlines() if line.startswith("::")]
        self.assertEqual(len(notices), 1, notices)
        self.assertTrue(notices[0].startswith("::notice::[blogger_macat]"), notices[0])
        self.assertIn("PIPELINE_PAUSE", notices[0])
        self.assertIn("Variables", notices[0])

    def test_mode_off_leaves_a_skip_line_a_notice_and_a_summary(self):
        root = make_root(tempfile.mkdtemp(), mode="off")
        self.addCleanup(shutil.rmtree, str(root), True)
        code, out = self.go(env=self.env(**FULL_ENV), publisher=FakePublisher(), root=root)
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=MODE_OFF", out)
        self.assertIn("MODE_OFF", self.summary())
        notices = [line for line in out.splitlines() if line.startswith("::")]
        self.assertEqual(len(notices), 1, notices)
        self.assertTrue(notices[0].startswith("::notice::[blogger_macat]"), notices[0])
        self.assertIn("mode=off", notices[0])
        self.assertIn("pipeline/blogs.json", notices[0])

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
        """시드를 다 쓴 뒤 주제 확장 호출이 실패하면 '주제 없음'(초록)이 아니라 인프라 실패(종료 1)다."""
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

    def test_missing_publish_secrets_are_reported_even_when_the_daily_cap_is_reached(self):
        """사전 점검은 일일 상한보다 앞이다. 상한에 걸린 날은 초록으로 끝나 시크릿 누락이 가려지기 때문이다."""
        (self.root / "blogger_history.json").write_text(
            json.dumps([{"topic": "오늘 이미 만든 주제", "date": "2026-10-21", "status": "draft"}], ensure_ascii=False),
            encoding="utf-8")
        code, out = self.go(env=self.env(**FULL_ENV), publisher=FakePublisher())
        self.assertIn("[SKIP] code=DAILY_CAP", out)                  # 전제: 시크릿이 있었다면 상한 도달로 건너뛴다
        code, out = self.go(env=self.env(GEMINI_API_KEY="k"))
        self.assertEqual(code, 2)
        self.assertIn("[SKIP] code=SECRETS_MISSING", out)
        self.assertNotIn("DAILY_CAP", out)

    def test_missing_publish_secrets_stop_the_run_before_topic_expansion_calls_the_llm(self):
        """시드를 다 써서 주제 확장 LLM 호출이 필요한 상황에서도 시크릿이 없으면 LLM 호출 0회로 종료 2."""
        self.use_all_seeds()
        calls = []

        def spy(prompt):
            calls.append(prompt)
            return stub_llm(prompt)
        code, out = self.go(env=self.env(GEMINI_API_KEY="k"), llm=spy)
        self.assertEqual((code, calls), (2, []))
        self.assertIn("[SKIP] code=SECRETS_MISSING", out)

    def test_explicit_topic_does_not_bypass_the_publish_secret_check(self):
        """--topic·BLOGGER_TOPIC(수동 지정)은 일일 상한만 건너뛴다. 게시 시크릿 점검은 그대로 한다."""
        topic = "수동으로 지정한 오늘의 생활 습관 주제"
        for label, extra, env in (("--topic", ["--topic", topic], {}), ("BLOGGER_TOPIC", [], {"BLOGGER_TOPIC": topic})):
            with self.subTest(label):
                pub = FakePublisher()
                code, out = self.go(env=self.env(GEMINI_API_KEY="k", **env), publisher=pub, extra=extra)
                self.assertEqual(code, 2)
                self.assertIn("[SKIP] code=SECRETS_MISSING", out)
                self.assertEqual((pub.published, self.history()), ([], []))

    def test_missing_publish_secrets_are_reported_before_the_history_file_is_read(self):
        """설정 오류(시크릿 누락)는 상태 파일(이력)을 읽기 전에 알린다. 이력이 깨져 있어도 같은 오류가 먼저 보인다."""
        (self.root / "blogger_history.json").write_text("{not json", encoding="utf-8")
        code, out = self.go(env=self.env(GEMINI_API_KEY="k"))
        self.assertEqual(code, 2)
        self.assertIn("[SKIP] code=SECRETS_MISSING", out)
        self.assertEqual((self.root / "blogger_history.json").read_text(encoding="utf-8"), "{not json")  # 덮어쓰지 않음

    def test_missing_llm_key_leaves_a_summary_with_the_secret_name(self):
        out = []
        code = run_mod.run(["--blog", "blogger_macat", "--root", str(self.root)], environ=self.env(**NO_PUBLISH), now=NOW,
                           llm=None, rng=random.Random(1), out=out.append)
        self.assertEqual(code, 2)
        self.assertIn("SECRETS_MISSING", self.summary())
        self.assertIn("GEMINI_API_KEY", self.summary())

    def test_publish_failure_message_is_masked_in_the_log_the_history_and_the_summary(self):
        leaked = ["ya29." + "x" * 30, "1//" + "y" * 30]  # 런타임에 조합한다(실제 비밀처럼 보이는 리터럴 금지)
        pub = FakePublisher(fail=PublishError(f"token refresh failed: {leaked[0]} / {leaked[1]}", code="auth_failed"))
        code, out = self.go(env=self.env(**FULL_ENV), publisher=pub)
        self.assertEqual(code, 1)
        self.assertIn("auth_failed", self.history()[-1]["reasons"][0])   # 원인 분류는 남는다
        shown = out + json.dumps(self.history(), ensure_ascii=False) + self.summary()
        for secret in leaked:
            self.assertNotIn(secret, shown)

    def test_gate_warning_annotation_is_a_fixed_sentence_without_the_rejection_reasons(self):
        """탈락 사유(LLM 글에서 나온 문자열이 섞일 수 있다)는 로그 본문·요약·이력에만 두고 ::warning:: 주석에는 넣지 않는다."""
        def short(prompt):
            return "제목: 충분히 긴 제목입니다 정말로\n라벨: 가\n내용:\n<p>너무 짧음</p>", "m"
        code, out = self.go(env=self.env(**FULL_ENV), llm=short, publisher=FakePublisher())
        reasons = self.history()[-1]["reasons"]
        self.assertTrue(reasons)
        self.assertIn("LEN_SHORT", out)                                   # 사유는 로그 본문에는 있다
        annotations = [line for line in out.splitlines() if line.startswith("::")]
        self.assertEqual(len(annotations), 1, annotations)
        for reason in reasons:
            self.assertNotIn(reason, annotations[0])
            self.assertNotIn(reason.split("]", 1)[0].lstrip("["), annotations[0])  # 사유 코드(LEN_SHORT 등)도 없다

    def test_dry_run_summary(self):
        code, out = self.go(env=self.env(**FULL_ENV), publisher=FakePublisher(), extra=["--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("DRY_RUN", self.summary())

    def test_warning_annotations_never_embed_llm_text(self):
        """게이트 탈락 사유(LLM 글·이력 파일에서 나온 문자열)가 ::workflow-command:: 줄이나 요약의 새 줄이 되면 안 된다."""
        def evil(prompt):
            return "제목: ::error::위조된 명령 제목입니다 충분히 길게\n라벨: 가\n내용:\n<p>짧음</p>", "m"
        code, out = self.go(env=self.env(**FULL_ENV), llm=evil, publisher=FakePublisher())
        for line in out.splitlines():
            if line.startswith("::"):
                self.assertNotIn("위조된 명령", line)

        # 비교 대상 이력(다른 블로그는 피드·LLM 유래)의 제목에 줄 바꿈 문자로 명령·제목·링크를 숨긴 경우
        title = "충분히 긴 제목입니다 정말로 위조 테스트"

        def same_title_again(prompt):
            return f"제목: {title}\n라벨: 가\n내용:\n<p>짧음</p>", "m"
        hidden = (("개행", "\n::error::위조된 명령"), ("단독 CR", "\r::error::위조된 명령"),
                  ("U+2028", "\u2028::error::위조된 명령"), ("U+0085", "\u0085::error::위조된 명령"),
                  ("링크·표·HTML", "\n[x](https://e.io)|<b>"))
        for label, suffix in hidden:
            with self.subTest(label):
                (self.root / "history.json").write_text(
                    json.dumps([{"title": title + suffix}], ensure_ascii=False), encoding="utf-8")        # 다른 블로그 이력
                (self.root / "blogger_history.json").write_text(
                    json.dumps([{"title": title + suffix, "date": "2026-10-19", "status": "posted"}], ensure_ascii=False),
                    encoding="utf-8")                                                                      # 이 블로그 이력
                self.summary_path.unlink(missing_ok=True)
                code, out = self.go(env=self.env(**FULL_ENV), llm=same_title_again, publisher=FakePublisher())
                self.assertEqual(code, 0)
                reasons = " ".join(self.history()[-1]["reasons"])
                self.assertIn("DUP_OTHER", reasons)   # 전제: 이력 제목이 실제로 탈락 사유에 들어갔다
                self.assertIn("DUP_SAME", reasons)
                for char in ("\r", "\u2028", "\u0085"):
                    self.assertNotIn(char, out)
                annotations = [line for line in out.splitlines() if line.lstrip().startswith(("::", "##["))]
                self.assertEqual(len(annotations), 1, annotations)       # 고정 문장의 ::warning:: 한 줄뿐
                self.assertTrue(annotations[0].startswith("::warning::[blogger_macat] 게이트를"))
                self.assertNotIn("위조된 명령", annotations[0])
                self.assertIn(title, out)                                 # 어떤 제목과 겹쳤는지는 로그에 남는다
                summary_lines = self.summary().splitlines()
                self.assertEqual(len(summary_lines), 2, summary_lines)    # '### 키' 와 '- 결과' 두 줄뿐(끼워 넣은 줄 없음)
                for char in "|<>`":
                    self.assertNotIn(char, summary_lines[1])
                self.assertNotIn("](", summary_lines[1])

    def test_summary_and_log_never_get_line_breaks_or_markdown_from_the_llm_title(self):
        """LLM 제목의 단독 CR·링크·표·HTML 문법이 실행 요약(마크다운)과 로그에 그대로 들어가면 안 된다."""
        def evil(prompt):
            text, model = stub_llm(prompt)
            first_line = text.split("\n", 1)[0]
            return text.replace(first_line, "제목: [클릭](https://evil.example)|<b>굵게</b>\r::error::위조된 제목 줄", 1), model
        pub = FakePublisher()
        code, out = self.go(env=self.env(**FULL_ENV), llm=evil, publisher=pub)
        self.assertEqual(code, 0)
        self.assertIn("위조된 제목 줄", pub.published[0]["title"])        # 전제: 위조 문구가 제목에 실제로 들어갔다
        lines = self.summary().splitlines()
        self.assertEqual(len(lines), 3, lines)                           # '### 키', '- 결과', '- URL' 세 줄뿐
        self.assertEqual([line for line in lines if line.startswith("#")], ["### blogger_macat"])
        for char in "|<>`":
            self.assertNotIn(char, lines[1])
        self.assertNotIn("](", self.summary())
        self.assertIn("클릭", lines[1])                                   # 제목 내용은 읽을 수 있게 남는다
        self.assertIn("https://macat.example/p1", lines[2])               # 게시된 글 주소는 그대로

        self.summary_path.unlink()
        (self.root / "blogger_history.json").unlink()   # 방금 게시한 기록이 있으면 하루 상한에 걸린다
        code, out = self.go(env=self.env(**FULL_ENV), llm=evil, publisher=FakePublisher(), extra=["--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("[DRY_RUN]", out)
        self.assertNotIn("\r", out)
        self.assertEqual([line for line in out.splitlines() if line.lstrip().startswith(("::", "##["))], [])
        self.assertIn("위조된 제목 줄", out)                               # 로그에는 접힌 제목이 보인다
        lines = self.summary().splitlines()
        self.assertEqual(len(lines), 2, lines)
        self.assertNotIn("](", self.summary())

    def test_api_error_text_is_folded_into_one_line_before_it_reaches_the_log(self):
        """LLM·Blogger API 오류 문구(외부 유래)에 단독 CR·개행으로 숨긴 '::error::' 가 로그의 새 줄이 되면 안 된다."""
        def down(prompt):
            raise LLMError("quota exceeded\r::error::위조된 LLM 줄\n## 가짜")
        pub = FakePublisher(fail=PublishError("HTTP 500\r::error::위조된 게시 줄\n## 가짜", code="api_error"))
        for label, kwargs, forged in (("LLM", {"llm": down}, "위조된 LLM 줄"), ("게시", {"publisher": pub}, "위조된 게시 줄")):
            with self.subTest(label):
                (self.root / "blogger_history.json").unlink(missing_ok=True)
                code, out = self.go(env=self.env(**FULL_ENV), **kwargs)
                self.assertEqual(code, 1)
                self.assertIn(forged, out)                                # 원인은 접힌 한 줄로 보인다
                self.assertNotIn("\r", out)
                annotations = [line for line in out.splitlines() if line.lstrip().startswith(("::", "##["))]
                self.assertEqual(len(annotations), 1, annotations)        # 고정 문장의 ::error:: 한 줄뿐
                self.assertNotIn("위조된", annotations[0])

    def test_log_and_summary_fold_whatever_the_gate_reports(self):
        """사유를 만드는 쪽(gates)이 접어 주더라도, 로그·요약을 쓰는 run 도 받은 사유를 다시 한 줄로 접어 쓴다."""
        forged = "[NEW_GATE] 사유\r::error::위조된 명령\n## 가짜 제목\n[x](https://e.io)"
        rejected = gates.GateResult(ok=False, reasons=[forged])
        with mock.patch.object(run_mod.gates, "check_post", return_value=rejected):
            code, out = self.go(env=self.env(**FULL_ENV), publisher=FakePublisher())
        self.assertEqual(code, 0)
        self.assertEqual(self.history()[-1]["status"], "rejected")
        self.assertNotIn("\r", out)
        annotations = [line for line in out.splitlines() if line.lstrip().startswith(("::", "##["))]
        self.assertEqual(len(annotations), 1, annotations)               # 고정 문장의 ::warning:: 한 줄뿐
        self.assertNotIn("위조된 명령", annotations[0])
        lines = self.summary().splitlines()
        self.assertEqual(len(lines), 2, lines)
        self.assertNotIn("](", self.summary())
        self.assertIn("위조된 명령", lines[1])                              # 사유 내용은 읽을 수 있게 남는다


class ManualTopicGuardTest(RunBase):
    """수동 topic(--topic·BLOGGER_TOPIC)도 시드·LLM 확장 주제와 같은 금지 주제 목록을 통과해야 한다(D-64 ⑥ c, 주제 가드레일 (a)).
    걸리면 Gemini·Blogger 를 부르기 전에 종료 2(빨강)로 멈춘다. 통과하는 주제는 예전 그대로다."""

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.summary_path = Path(tmp.name) / "summary.md"

    def env(self, **extra):
        return {"GITHUB_STEP_SUMMARY": str(self.summary_path), **extra}

    def summary(self):
        return self.summary_path.read_text(encoding="utf-8") if self.summary_path.exists() else ""

    @staticmethod
    def spy():
        prompts = []

        def llm(prompt):
            prompts.append(prompt)
            return stub_llm(prompt)
        llm.prompts = prompts
        return llm

    def test_a_blocked_topic_stops_with_exit_2_before_any_llm_call_blogger_call_history_or_draft(self):
        for label, extra, env in (("--topic", ["--topic", "혈압 낮추는 아침 습관"], {}),
                                  ("BLOGGER_TOPIC", [], {"BLOGGER_TOPIC": "혈압 낮추는 아침 습관"})):
            with self.subTest(label):
                llm, pub = self.spy(), FakePublisher()
                code, out = self.go(env=self.env(**FULL_ENV, **env), llm=llm, publisher=pub, extra=extra)
                self.assertEqual(code, 2, out)
                self.assertIn("[SKIP] code=TOPIC_BLOCKED blog=blogger_macat word=혈압", out)
                self.assertEqual((llm.prompts, pub.health_calls, pub.published, self.history(), self.drafts()), ([], 0, [], [], []))

    def test_the_reason_is_in_the_log_and_the_summary_but_the_error_annotation_is_a_fixed_sentence(self):
        code, out = self.go(env=self.env(**NO_PUBLISH), extra=["--topic", "다이어트 식단 짜는 법"])
        self.assertEqual(code, 2)
        self.assertIn("'다이어트'", out)                      # 로그 줄에는 걸린 낱말
        self.assertIn("TOPIC_BLOCKED", self.summary())
        self.assertIn("'다이어트'", self.summary())           # 요약에도 — 운영자가 어떤 낱말을 고칠지 본다
        errors = [line for line in out.splitlines() if line.startswith("::error::")]
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith("::error::[blogger_macat]"), errors[0])
        self.assertNotIn("다이어트", errors[0])                # 주석에는 입력에서 온 문자열을 넣지 않는다(고정 문장)

    def test_the_guard_is_the_same_in_a_dry_run_and_does_not_need_secrets(self):
        llm = self.spy()
        code, out = self.go(env=self.env(), llm=llm, extra=["--dry-run", "--topic", "체중 감량 식단"])
        self.assertEqual((code, llm.prompts), (2, []))
        self.assertIn("[SKIP] code=TOPIC_BLOCKED", out)

    def test_a_blocked_topic_is_reported_even_when_the_daily_cap_is_reached(self):
        """수동 topic 은 하루 상한을 건너뛰지만 금지 주제는 건너뛰지 못한다. 상한 안내(초록)에 가려지면 안 된다."""
        (self.root / "blogger_history.json").write_text(
            json.dumps([{"topic": "오늘 이미 만든 주제", "date": "2026-10-21", "status": "draft"}], ensure_ascii=False), encoding="utf-8")
        code, out = self.go(env=self.env(**NO_PUBLISH), extra=["--topic", "혈당 관리 식사 순서"])
        self.assertEqual(code, 2)
        self.assertIn("[SKIP] code=TOPIC_BLOCKED", out)
        self.assertNotIn("DAILY_CAP", out)

    def test_the_quotes_around_the_input_do_not_hide_the_word(self):
        code, out = self.go(env=self.env(**NO_PUBLISH), extra=["--topic", '  "치매 예방 생활 습관"  '])
        self.assertEqual(code, 2, out)

    def test_a_safe_topic_runs_exactly_as_before(self):
        topic = "수동으로 지정한 오늘의 생활 습관 주제"
        for label, extra, env in (("--topic", ["--topic", topic], {}), ("BLOGGER_TOPIC", [], {"BLOGGER_TOPIC": topic})):
            with self.subTest(label):
                root = make_root(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, str(root), True)
                llm = self.spy()
                code, out = self.go(env=self.env(**NO_PUBLISH, **env), llm=llm, extra=extra, root=root)
                self.assertEqual(code, 0, out)
                self.assertNotIn("TOPIC_BLOCKED", out)
                self.assertIn(topic, llm.prompts[0])
                history = json.loads((root / "blogger_history.json").read_text(encoding="utf-8"))
                self.assertEqual((history[-1]["status"], history[-1]["topic_source"], history[-1]["topic"]), ("draft", "override", topic))

    def test_no_topic_input_means_no_check_and_the_seed_flow_is_unchanged(self):
        llm = self.spy()
        code, out = self.go(env=self.env(**NO_PUBLISH), llm=llm)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(self.history()[-1]["topic_source"], "seed")

    def test_a_blocked_topic_is_reported_before_the_history_file_is_read(self):
        """입력 오류는 상태 파일을 읽기 전에 알린다(깨진 이력에 가려 종료 1 로 끝나지 않게). 이력은 덮어쓰지 않는다."""
        (self.root / "blogger_history.json").write_text("{not json", encoding="utf-8")
        code, out = self.go(env=self.env(**NO_PUBLISH), extra=["--topic", "혈압 낮추는 아침 습관"])
        self.assertEqual(code, 2, out)
        self.assertIn("[SKIP] code=TOPIC_BLOCKED", out)
        self.assertEqual((self.root / "blogger_history.json").read_text(encoding="utf-8"), "{not json")

    def test_the_matched_word_is_one_token_in_the_skip_line_and_a_long_word_is_cut_in_the_log_and_the_summary(self):
        code, out = self.go(env=self.env(**NO_PUBLISH), extra=["--topic", "간 건강 챙기기 습관"])
        self.assertEqual(code, 2, out)
        self.assertIn("word=간_건강", out)                      # 낱말 안의 공백은 key=value 한 덩어리로 유지한다
        root = make_root(tempfile.mkdtemp(), lang="en")
        self.addCleanup(shutil.rmtree, str(root), True)
        code, out = self.go(env=self.env(**NO_PUBLISH), extra=["--topic", "Acupunctur" + "x" * 100], root=root)  # \bacupunctur\w* 는 끝없이 이어진다
        self.assertEqual(code, 2, out)
        line = next(line for line in out.splitlines() if line.startswith("[SKIP] code=TOPIC_BLOCKED"))
        word = line.split("word=", 1)[1]
        self.assertLessEqual(len(word), 40)
        self.assertTrue(word.endswith("…"), word)
        self.assertIn("…", self.summary())
        self.assertNotIn("x" * 60, self.summary())

    def test_a_banned_word_far_into_a_long_topic_is_still_caught(self):
        """주제 전체를 본다(앞부분만 보지 않는다). 120자 상한 안에서 금지 낱말이 뒤쪽에 있어도 막는다(D-64 ⑦ N-5)."""
        topic = "A long and calm evening routine for desk workers who love tea music and slow walks, plus a gentle plan for insomnia"
        self.assertTrue(90 < topic.index("insomnia") and len(topic) <= 120, (topic.index("insomnia"), len(topic)))
        root = make_root(tempfile.mkdtemp(), lang="en")
        self.addCleanup(shutil.rmtree, str(root), True)
        code, out = self.go(env=self.env(**NO_PUBLISH), extra=["--topic", topic], root=root)
        self.assertEqual(code, 2, out)
        self.assertIn("word=insomnia", out)

    def test_the_guard_uses_the_topic_list_and_not_the_body_list(self):
        """주제 목록에만 있는 낱말(remedy·heal·treat·pharmacy)은 본문 목록이 일상어라 뺀 것이다. 수동 topic 은 주제 목록을 쓰므로 이 낱말도 막는다(D-64 ⑦ N-5)."""
        profile = registry.load_profile("blogger_practical_en")
        root = make_root(tempfile.mkdtemp(), lang="en")
        self.addCleanup(shutil.rmtree, str(root), True)
        for topic in ("Home remedy ideas for a calm evening", "Time to heal your sleep schedule", "Treat yourself to a slow morning",
                      "Pharmacy pickup reminders for your phone"):
            with self.subTest(topic):
                self.assertEqual(gates.body_risk_hit(topic, profile), (None, None))   # 본문 목록으로는 걸리지 않는 주제
                self.assertFalse(gates.topic_allowed(topic, profile))
                code, out = self.go(env=self.env(**NO_PUBLISH), extra=["--topic", topic], root=root)
                self.assertEqual(code, 2, out)
                self.assertIn("[SKIP] code=TOPIC_BLOCKED", out)

    def test_a_blocked_topic_stops_before_the_upload_skipped_notice(self):
        """초안함 업로드(draft)인데 게시용 시크릿이 하나도 없으면 'UPLOAD_SKIPPED … 저장소 파일에만 저장합니다' 안내가 나온다. 주제가 막혀 아무것도
        저장하지 않고 멈추는 실행에서는 그 안내가 나오면 안 된다(D-64 ⑦ N-7)."""
        env = self.env(GEMINI_API_KEY="k", BLOGGER_PUBLISH="draft")
        code, out = self.go(env=env, extra=["--topic", "혈압 낮추는 아침 습관"])
        self.assertEqual(code, 2, out)
        self.assertIn("[SKIP] code=TOPIC_BLOCKED", out)
        self.assertNotIn("UPLOAD_SKIPPED", out)
        self.assertNotIn("저장소 파일에만 저장합니다", out)
        self.assertNotIn("UPLOAD_SKIPPED", self.summary())
        self.assertEqual((self.history(), self.drafts()), ([], []))

    def test_without_a_blocked_topic_the_upload_skipped_notice_is_unchanged(self):
        """주제가 없거나 통과하면 안내는 예전 그대로다(정기 실행의 출력을 바꾸지 않는다)."""
        env = self.env(GEMINI_API_KEY="k", BLOGGER_PUBLISH="draft")
        for label, extra in (("정기 실행(주제 없음)", []), ("통과하는 수동 주제", ["--topic", "수동으로 지정한 오늘의 생활 습관 주제"])):
            with self.subTest(label):
                root = make_root(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, str(root), True)
                code, out = self.go(env=env, extra=extra, root=root)
                self.assertEqual(code, 0, out)
                self.assertIn("[SKIP] code=UPLOAD_SKIPPED blog=blogger_macat reason=NO_SECRETS", out)
                self.assertIn("::notice::[blogger_macat] Blogger 초안함에는 올리지 않고 저장소 파일에만 저장합니다", out)
                self.assertNotIn("TOPIC_BLOCKED", out)

    def test_the_errors_that_came_first_still_come_first_with_a_blocked_topic(self):
        """일시정지·mode off·잘못된 BLOGGER_PUBLISH·시크릿 누락 오류는 수동 주제 검사보다 먼저 처리된다(순서는 그대로)."""
        topic = ["--topic", "혈압 낮추는 아침 습관"]
        code, out = self.go(env=self.env(PIPELINE_PAUSE="true", **NO_PUBLISH), extra=topic)
        self.assertEqual(code, 0, out)
        self.assertIn("code=PAUSED", out)
        self.assertNotIn("TOPIC_BLOCKED", out)
        off_root = make_root(tempfile.mkdtemp(), mode="off")
        self.addCleanup(shutil.rmtree, str(off_root), True)
        code, out = self.go(env=self.env(**NO_PUBLISH), extra=topic, root=off_root)
        self.assertEqual(code, 0, out)
        self.assertIn("code=MODE_OFF", out)
        self.assertNotIn("TOPIC_BLOCKED", out)
        code, out = self.go(env=self.env(BLOGGER_PUBLISH="yolo"), extra=topic)
        self.assertEqual(code, 2, out)
        self.assertIn("code=INVALID_PUBLISH", out)
        self.assertNotIn("TOPIC_BLOCKED", out)
        code, out = self.go(env=self.env(GEMINI_API_KEY="k", BLOGGER_PUBLISH="publish"), extra=topic)       # 즉시 게시인데 게시용 시크릿이 없다
        self.assertEqual(code, 2, out)
        self.assertIn("code=SECRETS_MISSING", out)
        self.assertNotIn("TOPIC_BLOCKED", out)
        code, out = self.go(env=self.env(GEMINI_API_KEY="k", BLOGGER_PUBLISH="draft", BLOGGER_BLOG_ID="123"), extra=topic)   # 일부만 등록
        self.assertEqual(code, 2, out)
        self.assertIn("code=SECRETS_MISSING", out)
        self.assertNotIn("TOPIC_BLOCKED", out)

    def test_in_a_dry_run_the_partial_secrets_warning_still_comes_before_the_topic_error(self):
        env = self.env(GEMINI_API_KEY="k", BLOGGER_PUBLISH="draft", BLOGGER_BLOG_ID="123")
        code, out = self.go(env=env, extra=["--dry-run", "--topic", "혈압 낮추는 아침 습관"])
        self.assertEqual(code, 2, out)
        self.assertIn("DRY_RUN이라 계속합니다", out)
        self.assertLess(out.index("DRY_RUN이라 계속합니다"), out.index("TOPIC_BLOCKED"))

    def test_the_architecture_doc_lists_the_skip_code_as_a_config_error_with_exit_code_2(self):
        """코드표가 문서에 있다(ARCHITECTURE §4-1): 코드 이름이 '설정 오류·종료 2' 행에 있고 처리 순서에도 나온다. 문서가 코드와 어긋나면 실패한다."""
        text = (REAL / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        section = text[text.index("## 4-1."):text.index("## 4-2.")]
        rows = [line for line in section.splitlines() if line.lstrip().startswith("|") and "`TOPIC_BLOCKED`" in line]
        self.assertTrue(rows, "TOPIC_BLOCKED 행이 §4-1 표에 없습니다")
        self.assertTrue(any(line.startswith("| 설정 오류 |") and re.search(r"\|\s*\*\*2\*\*\s*\|", line) for line in rows), rows)
        self.assertIn("수동 `topic` 금지 주제 검사", section)

    def test_the_topic_check_uses_the_topic_guard_list_of_the_blogs_own_profile(self):
        """영문 프로필 블로그에서는 영어 목록이 쓰인다(한국어 낱말은 걸리지 않고 영어 낱말은 걸린다)."""
        root = make_root(tempfile.mkdtemp(), lang="en")
        self.addCleanup(shutil.rmtree, str(root), True)
        code, out = self.go(env=self.env(**NO_PUBLISH), extra=["--topic", "Blood-pressure friendly evening habits"], root=root)
        self.assertEqual(code, 2, out)
        self.assertIn("word=Blood-pressure", out)
        code, out = self.go(env=self.env(**NO_PUBLISH), extra=["--topic", "A calm ten-minute walk after dinner"], root=root)
        self.assertEqual(code, 0, out)


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
