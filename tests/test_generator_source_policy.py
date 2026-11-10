"""소스 정책 스위치(레지스트리 chance.source_policy)와 생성기 연결 시험.

1. legacy(기본·꺼짐): 옛 생성기(기준 커밋 78c6b89)와 출력이 바이트까지 같다 — 같은 가짜 입력으로 돌린 여덟 시나리오의 sha256 을 옛 코드가 만든 값(GOLDEN)에 견준다.
2. allowlist: ACTIVE 가 아닌 소스를 읽지 않는다 — urlopen 을 막은 채 main() 을 돌려 호출 0, 기사 페이지 발췌·구글 뉴스 해석기·모델 호출 0, 결과 코드 SOURCE_POLICY_NO_ACTIVE_PROVIDER 는 초록(종료 0),
   Pew 는 소스 이름으로 직접 못박는다. 외부 제목·요약·태그는 프롬프트·이력·로그·실행 요약·탈락 기록에 들어가지 않는다(구조 시험 포함).
3. 레지스트리 값 검증(registry.validate_registry)과 값 읽기(source_policy.chance_source_policy).

네트워크·진짜 키·진짜 시계를 쓰지 않는다. 실제 pipeline/blogs.json 의 값은 바꾸지 않는다(켜는 것은 T3)."""
import ast
import contextlib
import copy
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import generator as g
import source_policy_scenarios as sc
from pipeline import egress, registry, source_policy, source_registry as sr
from source_registry_helpers import GOOD_HOST, TODAY, good_provider, registry_data

ROOT = _bootstrap.ROOT

# 기준 커밋 78c6b89(소스 정책 도입 전 main)의 generator.py·pipeline 이 같은 시나리오(tests/source_policy_scenarios.py)에서 만든 값. 시나리오를 바꾸면 그 모듈의 안내대로 다시 만든다.
# 운영체제와 무관하다: main_* 네 값은 표준 출력의 경로 구분자(역슬래시 → 슬래시)와 작업 폴더 파일의 줄 끝(CRLF → LF)을 통일해 해시한 값이다(윈도에서 만든 옛 값은 리눅스 CI 에서 달랐다 — 옛 코드를 같은 방식으로 다시 돌려 얻은 값이며, 리눅스가 현재 코드로 낸 값과 같다).
GOLDEN = {
    "excerpt_and_resolver": "7d154f73f629c90ce07cf5f5abe628a21db94323cbdffbf242e6d88ad159819a",
    "fetch_all_lanes": "e10096c414774e3b0887bca6d0b235a45feb5c9f51b735fadee9ae95fb2402c2",
    "finish_outcomes": "e6d11c050a9a5e6bbecd7b44d379bdada7a73b9881af11157afadaea9b9934c0",
    "main_manual_dry_run": "48dff403a143564d0f86e91060c6ded924611495dde3d9ab137bc9410a73a228",
    "main_manual_write": "ca52e5ef4839a0e6d3e982520ecf4a0a3e6afd76288dbc7410bee15d2173c1f9",
    "main_schedule_dry_run": "fd8aacf8c8107aeca835b52d3ecadc10add5ac296dc5df634a4a1af0827e18d2",
    "main_schedule_write": "049fe6f3dddf344dde78a2b41d56063dd7cfd19f3e53d4a4bd6b79ede926c072",
    "prompts": "42c952fe34c8f66411c2bd6f214c70b7263c54a8dcd4f2aa9404e21d8355562c",
}
EXT = "EXT-"      # 외부 글의 표지: 이 글자가 든 문자열은 모두 '외부에서 온 제목·요약·태그'다(출력 어디에도 나오면 안 된다)


class BlockedNet:
    """urlopen 자리에 넣는 막힌 네트워크: 호출을 적고 예외를 던진다."""

    def __init__(self):
        self.calls = []

    def __call__(self, request, timeout=None):
        self.calls.append(getattr(request, "full_url", str(request)))
        raise AssertionError("이 시험에서는 네트워크를 쓰면 안 된다")


def active_registry():
    """ACTIVE 콘텐츠 Provider 가 하나 있는 허용 목록(지어낸 기관) — allowlist 의 '일 없음' 분기를 지나 일반 흐름이 이어지게 한다."""
    return sr.build_registry(registry_data(good_provider()), TODAY)


class Base(unittest.TestCase):
    """생성기를 임시 작업 폴더에서 막힌 네트워크·가짜 모델로 돌리는 바탕. mode 는 source_policy 값(시험이 레지스트리 대신 이 값을 쓴다)."""
    mode = "allowlist"
    dry_run = False

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        (self.work / "_posts").mkdir()
        old = os.getcwd()
        os.chdir(self.work)
        self.addCleanup(os.chdir, old)
        self.summary = self.work / "summary.md"
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.stack = stack
        stack.enter_context(mock.patch.multiple(g, DRY_RUN=self.dry_run, STUB_GEMINI=self.dry_run, STUB_UNSPLASH=True, FIX_IMAGES=False, EVENT_NAME="schedule"))
        stack.enter_context(mock.patch.object(g, "now_kst", return_value=sc.NOW))
        stack.enter_context(mock.patch.object(g, "draft_flow_on", return_value=False))
        stack.enter_context(mock.patch("time.sleep", lambda s: None))
        stack.enter_context(mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(self.summary), "PIPELINE_PAUSE": ""}))
        stack.enter_context(mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0}))
        stack.enter_context(mock.patch.dict(g.UNSPLASH_RATE, {"remaining": None, "limit": None}))
        stack.enter_context(mock.patch.dict(g._credits))
        stack.enter_context(mock.patch.object(g, "CALL_LOG", g.CallLog(label="chance", purpose="post", out=print, secrets=())))
        stack.enter_context(mock.patch.object(source_policy, "chance_source_policy", return_value=self.mode))
        self.net = BlockedNet()
        stack.enter_context(mock.patch("urllib.request.urlopen", self.net))
        stack.enter_context(mock.patch("socket.create_connection", side_effect=AssertionError("소켓 연결을 시도했다")))
        self.gemini_prompts, self.excerpt_calls, self.resolver_calls = [], [], []
        stack.enter_context(mock.patch.object(g, "call_gemini_with_fallback", self.fake_gemini))
        stack.enter_context(mock.patch.object(g, "_fetch_source_excerpt", lambda url: self.excerpt_calls.append(url) or ""))
        stack.enter_context(mock.patch.object(g, "_resolve_article_url", lambda url: self.resolver_calls.append(url) or ""))
        stack.enter_context(mock.patch.object(g, "pick_images", sc.fake_pick_images(g)))
        self.write_history([])

    def fake_gemini(self, prompt):
        self.gemini_prompts.append(prompt)
        raise AssertionError("이 시험에서는 모델을 부르면 안 된다")

    def write_history(self, entries):
        Path("history.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")

    def history(self):
        return json.loads(Path("history.json").read_text(encoding="utf-8"))

    def run_main(self, event="schedule"):
        out = io.StringIO()
        code = "returned"
        with mock.patch.object(g, "EVENT_NAME", event), contextlib.redirect_stdout(out):
            try:
                g.main()
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue()

    def summary_text(self):
        return self.summary.read_text(encoding="utf-8") if self.summary.exists() else ""

    def posts(self):
        return sorted(p for p in (self.work / "_posts").rglob("*.md"))


# ----------------------------------------------------------------------------
# 1. legacy: 옛 생성기와 바이트 동일
# ----------------------------------------------------------------------------
class LegacyByteTest(unittest.TestCase):
    def test_the_real_registry_does_not_set_source_policy_so_the_default_is_legacy(self):
        reg = registry.load_registry()
        self.assertEqual([blog.get("source_policy") for blog in reg["blogs"]], [None] * len(reg["blogs"]))      # 켜는 것은 T3 — 이 변경은 값을 바꾸지 않았다
        self.assertEqual(source_policy.chance_source_policy(), "legacy")
        self.assertEqual(registry.validate_registry(reg), [])

    def test_legacy_scenarios_match_the_old_generator_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            got = sc.run_all(g, tmp)
        self.assertEqual(sorted(got), sorted(GOLDEN))
        for name in sorted(GOLDEN):
            with self.subTest(scenario=name):
                self.assertEqual(got[name], GOLDEN[name], f"{name}: 옛 생성기(78c6b89)와 출력이 달라졌다 — 꺼진 기능은 이전과 같아야 한다")

    def test_legacy_touches_neither_the_source_registry_nor_the_clock(self):
        """기본값에서는 허용 목록 파일을 읽지 않고 시계도 부르지 않는다(이전과 같다)."""
        with mock.patch.object(sr, "load_registry", side_effect=AssertionError("legacy 가 허용 목록을 읽었다")), \
                mock.patch.object(g, "now_kst", side_effect=AssertionError("legacy 가 시계를 불렀다")), \
                mock.patch("urllib.request.urlopen", sc.FakeNet(g)), mock.patch("time.sleep", lambda s: None), contextlib.redirect_stdout(io.StringIO()):
            items = g.fetch_news_items("science")
            self.assertTrue(items)
            self.assertTrue(g._fetch_source_excerpt("https://www.nasa.gov/news/a"))
            self.assertTrue(g.build_post_prompt(items[0], ["a"], "", False, "science"))

    def test_the_new_outcome_does_not_change_how_the_old_outcomes_finish(self):
        for outcome in ("ALL_LANES_EMPTY", "SOURCES_UNREACHABLE"):
            with self.subTest(outcome=outcome), contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as caught:
                g.finish_run(None, {"outcome": outcome, "lanes": []}, "schedule", sc.NOW, 9)
            self.assertEqual(caught.exception.code, 1)
            self.assertIn("::error::", out.getvalue())
        for outcome in ("ALL_REJECTED", "ALL_DUPLICATES", "NO_CANDIDATES", "NO_MATCH"):
            with self.subTest(outcome=outcome), contextlib.redirect_stdout(io.StringIO()) as out:
                g.finish_run(None, {"outcome": outcome, "lanes": []}, "schedule", sc.NOW, 9)
            self.assertIn("::warning::", out.getvalue())
            self.assertNotIn("::notice::", out.getvalue())


# ----------------------------------------------------------------------------
# 2. allowlist
# ----------------------------------------------------------------------------
class AllowlistNoCallTest(Base):
    """allowlist 이고 ACTIVE 콘텐츠 Provider 가 0 — 네트워크·모델·페이지 발췌·해석기 호출 0, 초록으로 끝."""

    def assert_idle_and_green(self, code, out):
        self.assertEqual(code, "returned", out)                                 # SystemExit 없이 끝(초록)
        self.assertEqual(self.net.calls, [])
        self.assertEqual((self.gemini_prompts, self.excerpt_calls, self.resolver_calls), ([], [], []))
        self.assertIn("[SKIP] code=SOURCE_POLICY_NO_ACTIVE_PROVIDER", out)
        self.assertIn("::notice::", out)
        self.assertNotIn("::error::", out)
        self.assertNotIn("::warning::", out)
        self.assertIn("SOURCE_POLICY_NO_ACTIVE_PROVIDER", self.summary_text())
        self.assertNotIn("ALL_LANES_EMPTY", self.summary_text())
        self.assertIn("Gemini 호출: 0회", self.summary_text())
        self.assertEqual(self.history(), [])                                    # 이력도
        self.assertEqual(self.posts(), [])                                      # 글도 쓰지 않았다

    def test_a_scheduled_run_makes_zero_network_calls_and_ends_green(self):
        self.assert_idle_and_green(*self.run_main("schedule"))

    def test_a_manual_run_makes_zero_network_calls_and_ends_green(self):
        self.assert_idle_and_green(*self.run_main("workflow_dispatch"))

    def test_a_practice_run_is_the_same(self):
        with mock.patch.multiple(g, DRY_RUN=True, STUB_GEMINI=True):
            code, out = self.run_main("schedule")
        self.assertEqual(code, "returned", out)
        self.assertEqual(self.net.calls, [])
        self.assertIn("SOURCE_POLICY_NO_ACTIVE_PROVIDER", out)

    def test_run_cli_ends_without_an_exception(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            g.run_cli()                                                         # 예외 없이 끝나야 Actions 가 초록이다
        self.assertIn("SOURCE_POLICY_NO_ACTIVE_PROVIDER", out.getvalue())

    def run_real_cli(self, policy):
        """진짜 `python generator.py` 프로세스(임시 사본 + 레지스트리의 source_policy 값)를 소켓을 막은 채 수동 실행 연습 모드로 돌려 (종료 코드, 출력, 요약)을 돌려준다."""
        import shutil
        import subprocess
        import sys
        root = self.work / f"cli_root_{policy}"
        shutil.copytree(ROOT / "pipeline", root / "pipeline", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(ROOT / "generator.py", root / "generator.py")
        (root / ".github" / "editorial").mkdir(parents=True)
        shutil.copy(ROOT / ".github" / "editorial" / "CHANCE_BLOG_TEMPLATE.md", root / ".github" / "editorial" / "CHANCE_BLOG_TEMPLATE.md")
        (root / "_posts").mkdir()
        (root / "history.json").write_text("[]", encoding="utf-8")
        reg = json.loads((root / "pipeline" / "blogs.json").read_text(encoding="utf-8"))
        if policy is not None:
            next(blog for blog in reg["blogs"] if blog["key"] == "chance")["source_policy"] = policy
        (root / "pipeline" / "blogs.json").write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        guard = ("import runpy, socket\n"
                 "def blocked(*a, **k):\n    raise AssertionError('network attempt')\n"
                 "socket.socket.connect = blocked\nsocket.create_connection = blocked\nsocket.getaddrinfo = blocked\n"
                 "runpy.run_path('generator.py', run_name='__main__')\n")
        env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "UNSPLASH_ACCESS_KEY", "PIPELINE_PAUSE", "POST_HOURS_KST")}
        summary = root / "summary.md"
        env.update(EVENT_NAME="workflow_dispatch", DRY_RUN="1", GITHUB_STEP_SUMMARY=str(summary), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        done = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", guard], cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
        return done.returncode, done.stdout + done.stderr, summary.read_text(encoding="utf-8") if summary.exists() else ""

    def test_the_real_cli_process_exits_zero_in_allowlist_and_one_in_legacy_under_the_same_blocked_network(self):
        code, out, summary = self.run_real_cli("allowlist")
        self.assertEqual(code, 0, out)
        self.assertIn("[SKIP] code=SOURCE_POLICY_NO_ACTIVE_PROVIDER", out)
        self.assertIn("SOURCE_POLICY_NO_ACTIVE_PROVIDER", summary)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("network attempt", out)                                 # 네트워크를 시도하지 않았다
        code, out, summary = self.run_real_cli(None)                             # 같은 조건의 legacy: 피드를 읽으려다 모두 실패 → 빨강(종료 1)
        self.assertEqual(code, 1, out)
        self.assertIn("SOURCES_UNREACHABLE", summary)
        self.assertNotIn("SOURCE_POLICY", out + summary)

    def test_a_topic_override_run_is_idle_too(self):
        report = {}
        self.assertIsNone(g.generate_blog_posts(topic_override="아무 주제", report=report))
        self.assertEqual(report["outcome"], "SOURCE_POLICY_NO_ACTIVE_PROVIDER")
        self.assertEqual(self.net.calls, [])

    def test_the_idle_state_is_not_the_red_all_lanes_empty(self):
        """같은 빈 피드: legacy 는 ALL_LANES_EMPTY(빨강, 종료 1) 이고 allowlist 는 새 결과 코드(초록, 종료 0) — 두 상태가 구분된다."""
        empty = type("Net", (), {"calls": [], "__call__": lambda self, request, timeout=None: sc.FakeHTTP(b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>", "u")})()
        with mock.patch.object(source_policy, "chance_source_policy", return_value="legacy"), mock.patch("urllib.request.urlopen", empty):
            code, out = self.run_main("schedule")
        self.assertEqual(code, 1, out)
        self.assertIn("ALL_LANES_EMPTY", self.summary_text())
        self.summary.unlink()
        with mock.patch("urllib.request.urlopen", empty):
            code, out = self.run_main("schedule")
        self.assertEqual(code, "returned", out)
        self.assertIn("SOURCE_POLICY_NO_ACTIVE_PROVIDER", self.summary_text())
        self.assertNotEqual(g.OUTCOME_TEXT["SOURCE_POLICY_NO_ACTIVE_PROVIDER"], g.OUTCOME_TEXT["ALL_LANES_EMPTY"])

    def test_the_pause_switch_still_wins_and_the_registry_is_not_read(self):
        with mock.patch.dict(os.environ, {"PIPELINE_PAUSE": "true"}), mock.patch.object(sr, "load_registry", side_effect=AssertionError("정지 중에 허용 목록을 읽었다")):
            code, out = self.run_main("schedule")
        self.assertEqual(code, "returned")
        self.assertIn("PAUSED", out)
        self.assertNotIn("SOURCE_POLICY", out)

    def test_image_fixing_is_not_part_of_the_content_switch(self):
        """FIX_IMAGES(기존 글 사진 교체)는 콘텐츠 읽기 경로가 아니다 — 소스 정책이 막지 않는다(사진을 쓸지는 운영자 결정 대기)."""
        calls = []
        with mock.patch.object(g, "FIX_IMAGES", True), mock.patch.object(g, "fix_images", lambda keyword=None: calls.append(1) or "사진 점검 결과"):
            code, out = self.run_main("workflow_dispatch")
        self.assertEqual((code, calls), ("returned", [1]))
        self.assertNotIn("SOURCE_POLICY", self.summary_text())

    def test_the_value_is_really_read_from_the_registry_file(self):
        """시험이 값을 바꿔 끼우지 않고 레지스트리 파일(임시 사본)의 source_policy 를 읽어도 같다."""
        self.stack.close()                                                      # 바탕의 patch 를 풀고 진짜 읽기 경로를 쓴다
        self.stack = contextlib.ExitStack()
        reg = registry.load_registry()
        next(blog for blog in reg["blogs"] if blog["key"] == "chance")["source_policy"] = "allowlist"
        path = self.work / "blogs.json"
        path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        with mock.patch.object(registry, "REGISTRY_PATH", path):
            self.assertEqual(source_policy.chance_source_policy(), "allowlist")
            with mock.patch.multiple(g, DRY_RUN=False, STUB_GEMINI=False, STUB_UNSPLASH=True, FIX_IMAGES=False, EVENT_NAME="schedule"), mock.patch.object(g, "now_kst", return_value=sc.NOW), \
                    mock.patch.object(g, "draft_flow_on", return_value=False), mock.patch("urllib.request.urlopen", self.net), contextlib.redirect_stdout(io.StringIO()) as out:
                g.main()
        self.assertEqual(self.net.calls, [])
        self.assertIn("SOURCE_POLICY_NO_ACTIVE_PROVIDER", out.getvalue())


class AllowlistFetchTest(Base):
    def lanes(self):
        return list(g.EDITORIAL_LANES)

    def test_no_source_is_read_in_any_lane_and_the_log_names_each_source_only(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for lane in self.lanes():
                stats = {}
                self.assertEqual(g.fetch_news_items(lane, stats=stats), [])
                self.assertEqual(stats.get("sources", []), [])                   # 읽은 소스 통계도 없다
        self.assertEqual(self.net.calls, [])
        self.assertEqual((self.excerpt_calls, self.resolver_calls), ([], []))
        text = out.getvalue()
        for src in g.NEWS_SOURCES:
            self.assertIn(f"소스 {src['name']}:", text, src["name"])
            if src["name"] != "UN News":                                         # UN News 는 약관 보류 줄이 먼저 나온다(그 줄은 이 변경 전과 같다)
                self.assertIn(f"소스 {src['name']}: 허용 목록(Registry)의 ACTIVE 가 아니라 읽지 않음", text)
        self.assertEqual(text.count("허용 목록(Registry)의 ACTIVE 가 아니라 읽지 않음"), 19)

    def test_pew_is_not_read_by_name(self):
        """Pew 소스(웹페이지·RSS)는 allowlist 에서 읽히지 않는다 — 같은 가짜 피드로 legacy 는 읽고 allowlist 는 읽지 않아 시험이 읽힘을 볼 수 있다는 것도 보인다."""
        pew = [src for src in g.NEWS_SOURCES if src["name"] == "Pew Research Center"]
        self.assertEqual(len(pew), 1)
        feed = pew[0]["url"]
        fake = sc.FakeNet(g)
        with mock.patch("urllib.request.urlopen", fake), mock.patch.object(source_policy, "chance_source_policy", return_value="legacy"), contextlib.redirect_stdout(io.StringIO()):
            g.fetch_news_items(pew[0]["lane"])
        self.assertIn(feed, [url for _, url, _, _ in fake.calls])                # legacy: Pew 피드를 읽는다
        with contextlib.redirect_stdout(io.StringIO()) as out:
            g.fetch_news_items(pew[0]["lane"])
        self.assertEqual(self.net.calls, [])                                    # allowlist: 같은 소스를 읽지 않는다
        self.assertIn("소스 Pew Research Center: 허용 목록(Registry)의 ACTIVE 가 아니라 읽지 않음", out.getvalue())
        registry_ = sr.load_registry(today=TODAY)
        for pid in ("pew_rss", "pew_html"):
            self.assertEqual((registry_.get(pid).effective_status, registry_.get(pid).enabled, registry_.is_active(pid)), ("자동화 제외", False, False))
        for purpose in ("fact", "feed"):
            self.assertFalse(registry_.is_url_allowed(feed, purpose)[0])

    def test_the_feed_gate_refuses_if_the_source_skip_were_ever_bypassed(self):
        """C-01 의 이중 장치(P17·D-178): 소스 건너뜀(is_url_allowed(…, "feed"))이 어쩌다 허용으로 답해도(가정) 바로 뒤의 관문 호출이 EgressDenied 로 거부한다 — 삼키지 않고 네트워크는 0."""
        real = sr.load_registry(today=TODAY)

        class SkipBypassed:
            """첫 질의(건너뜀 판정)만 허용으로 답하고 그 뒤(관문 안)는 진짜 허용 목록으로 답하는 가짜 허용 목록."""

            def __init__(self):
                self.asked = {}

            def is_url_allowed(self, url, purpose):
                self.asked[url] = self.asked.get(url, 0) + 1
                return (True, "가정: 건너뜀 판정을 우회") if self.asked[url] == 1 else real.is_url_allowed(url, purpose)

            def __getattr__(self, name):
                return getattr(real, name)

        proxy = SkipBypassed()
        with mock.patch.object(source_policy, "news_registry", return_value=proxy), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(egress.EgressDenied) as caught:
                g.fetch_news_items("science")
        self.assertEqual(self.net.calls, [])
        self.assertIn("일반 웹 읽기(feed)", str(caught.exception))
        self.assertEqual(sorted(set(proxy.asked.values())), [2])                    # 같은 주소를 건너뜀 판정과 관문이 한 번씩 물었다

    def test_the_gate_refuses_page_excerpts_and_the_resolver_if_they_are_ever_reached(self):
        """allowlist 에서는 두 함수가 호출되지 않지만, 만에 하나 불리면 관문이 거부한다(EgressDenied — 삼키지 않는다)."""
        self.stack.close()
        self.stack = contextlib.ExitStack()
        with mock.patch.object(source_policy, "chance_source_policy", return_value="allowlist"), mock.patch("urllib.request.urlopen", self.net), \
                mock.patch.object(g, "now_kst", return_value=sc.NOW):
            for call, url in ((g._fetch_source_excerpt, "https://www.nasa.gov/news/a"), (g._resolve_article_url, "https://www.nasa.gov/news/a")):
                with self.assertRaises(egress.EgressDenied) as caught:
                    call(url)
                self.assertNotIn("news/a", str(caught.exception))                 # 문구에 경로가 없다
                self.assertIn("www.nasa.gov", str(caught.exception))
        self.assertEqual(self.net.calls, [])

    def test_with_an_active_provider_the_news_sources_stay_closed_and_the_flow_ends_red(self):
        """허용 목록에 ACTIVE 콘텐츠 Provider 가 있으면 '일 없음' 분기는 지나가지만 피드는 여전히 읽지 않는다 — 후보 공급 경로(FACT 2단계 연결)가 없는 배치는 ALL_LANES_EMPTY(빨강)로 드러난다.
        알려진 한계(docs/SOURCE_POLICY.md '한계'): 후보를 공급하는 새 경로가 이 자리를 대신한다."""
        with mock.patch.object(sr, "load_registry", return_value=active_registry()), contextlib.redirect_stdout(io.StringIO()):
            report = {}
            self.assertIsNone(g.generate_blog_posts(slot=9, allow_auto_topic=False, report=report))
        self.assertEqual(report["outcome"], "ALL_LANES_EMPTY")
        self.assertEqual(self.net.calls, [])
        self.assertTrue(source_policy.active_content_providers(active_registry()))
        with mock.patch.object(sr, "load_registry", return_value=active_registry()):
            code, out = self.run_main("schedule")
        self.assertEqual(code, 1, out)

    def test_an_unreadable_source_registry_stops_the_run_instead_of_falling_back(self):
        for failure in (sr.SourceRegistryError("읽을 수 없음"), registry.RegistryError("레지스트리 오류")):
            patch = mock.patch.object(sr, "load_registry", side_effect=failure) if isinstance(failure, sr.SourceRegistryError) else \
                mock.patch.object(source_policy, "chance_source_policy", side_effect=failure)
            with self.subTest(failure=type(failure).__name__), patch, contextlib.redirect_stdout(io.StringIO()), self.assertRaises(type(failure)):
                g.fetch_news_items("science")
            self.assertEqual(self.net.calls, [])


class AllowlistPromptTest(Base):
    """프롬프트 조립부에는 외부 제목·요약·태그가 가지 않는다(자체 제목만)."""
    ITEM = {"title": EXT + "TITLE-XYZ", "summary": EXT + "SUMMARY-XYZ " * 5, "source": EXT + "SOURCE-NAME", "link": "https://ext.example/path-x", "publisher_domain": "ext.example",
            "published": sc.NOW, "prompt_rule": EXT + "RULE", "categories": [EXT + "TAG"], "notice": None, "citation": None}

    def prompt(self, item, titles=("최근 제목 하나",)):
        return g.build_post_prompt(item, list(titles), "", True, "science")

    def test_an_external_item_reaches_the_prompt_in_legacy_but_not_in_allowlist(self):
        with mock.patch.object(source_policy, "chance_source_policy", return_value="legacy"):
            legacy = self.prompt(self.ITEM)
        for needle in ("TITLE-XYZ", "SUMMARY-XYZ", "SOURCE-NAME", "path-x", "RULE"):
            self.assertIn(needle, legacy, needle)                                # legacy: 옛 동작 그대로(시험이 외부 글을 볼 수 있다)
        allow = self.prompt(self.ITEM)
        self.assertNotIn(EXT, allow)
        for needle in ("path-x", "ext.example", "2026-11-09", "[기사 요약", "[원문 URL]", "[출처]", "[원문 게시 시각]"):
            self.assertNotIn(needle, allow, needle)
        self.assertIn("검증된 출처가 제공되지 않았습니다. 반드시 skip을 반환하세요.", allow)     # 자체 제목이 없으면 '출처 없음 — skip' 입력이 된다
        self.assertIn("최근 제목 하나", allow)

    def test_only_the_own_title_reaches_the_prompt(self):
        item = dict(self.ITEM, own_title="  자체 제목 하나  ")
        allow = self.prompt(item)
        self.assertNotIn(EXT, allow)
        self.assertIn("[주제]\n자체 제목 하나\n", allow)
        for field in ("source", "link", "published", "summary", "prompt_rule"):
            self.assertNotIn(field, re.findall(r"\[[^\]\n]+\]", allow[:allow.index("[최근 다룬")]) and "", field)       # 주제 칸에는 제목 줄 말고 아무 것도 붙지 않는다
        topic_block = allow.split("[주제]\n", 1)[1].split("\n\n", 1)[0]
        self.assertEqual(topic_block, "자체 제목 하나")

    def test_an_item_without_a_non_empty_own_title_is_treated_as_no_item(self):
        for own in (None, "", "   ", 5, ["x"]):
            item = dict(self.ITEM, own_title=own)
            self.assertIn("검증된 출처가 제공되지 않았습니다", self.prompt(item), own)
        self.assertIn("검증된 출처가 제공되지 않았습니다", self.prompt(None))

    def test_structure_the_sanitizer_runs_before_the_prompt_reads_any_item_field(self):
        """AST: build_post_prompt 안에서 source_policy.prompt_inputs 호출이 item 의 어떤 칸을 읽기보다 앞선다(입력에 외부 칸이 남지 않는다)."""
        tree = ast.parse((ROOT / "generator.py").read_text(encoding="utf-8"))
        function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "build_post_prompt")
        sanitizer = [n.lineno for n in ast.walk(function) if isinstance(n, ast.Call) and ast.unparse(n.func) == "source_policy.prompt_inputs"]
        self.assertEqual(len(sanitizer), 1)
        reads = [n.lineno for n in ast.walk(function)
                 if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == "item")
                 or (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "item")]
        self.assertTrue(reads)
        self.assertLess(sanitizer[0], min(reads))
        assigned = [n for n in ast.walk(function) if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Tuple) and [e.id for e in t.elts if isinstance(e, ast.Name)] == ["item", "recent_titles"] for t in n.targets)]
        self.assertEqual(len(assigned), 1)                                      # 걸러진 item 이 같은 이름으로 이어 쓰인다
        self.assertEqual([a.arg for a in function.args.args][:2], ["item", "recent_titles"])

    def test_structure_generate_blog_posts_filters_candidates_titles_and_the_idle_state_first(self):
        tree = ast.parse((ROOT / "generator.py").read_text(encoding="utf-8"))
        function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "generate_blog_posts")

        def lines(name, kind=ast.Call):
            return [n.lineno for n in ast.walk(function) if isinstance(n, kind) and ast.unparse(n.func) == name]
        idle, fetch, lanes = lines("source_policy.idle_check"), lines("fetch_news_items"), lines("iter_candidate_lanes")
        self.assertEqual(len(idle), 1)
        self.assertTrue(fetch and lanes)
        self.assertLess(idle[0], min(fetch + lanes))                             # 후보를 읽기 전에 '일 없음'부터 본다
        batches_filter = lines("source_policy.own_title_batches")
        self.assertEqual(len(batches_filter), 1)
        use = [n.lineno for n in ast.walk(function) if isinstance(n, ast.Name) and n.id == "batches" and isinstance(n.ctx, ast.Load)]
        first_use = min(line for line in use if line != batches_filter[0])
        self.assertLess(batches_filter[0], first_use)                            # 후보 흐름은 거른 뒤에만 쓰인다
        titles = lines("source_policy.prompt_titles")
        self.assertEqual(len(titles), 1)
        prompts = lines("build_post_prompt")
        self.assertTrue(prompts)
        self.assertLess(titles[0], min(prompts))


class AllowlistHistoryAndLogsTest(Base):
    """ACTIVE 콘텐츠 Provider 가 있어 흐름이 이어질 때(가상): 외부 제목은 이력·프롬프트·로그·실행 요약·탈락 기록 어디에도 남지 않는다."""
    LINK = "https://ext.example/news/b"

    def cand(self, **fields):
        base = {"title": EXT + "TITLE-ALPHA", "summary": EXT + "SUMMARY-ALPHA " * 8, "source": EXT + "SOURCE-A", "link": "https://ext.example/news/a", "publisher_domain": "ext.example",
                "published": sc.NOW, "notice": None, "citation": None, "prompt_rule": None, "categories": [EXT + "TAG-A"]}
        base.update(fields)
        return base

    def setUp(self):
        super().setUp()
        self.stack.enter_context(mock.patch.object(sr, "load_registry", return_value=active_registry()))
        self.candidates = [self.cand(),
                           self.cand(title=EXT + "TITLE-BETA", summary=EXT + "SUMMARY-BETA " * 8, source="Fixture Agency", link=self.LINK, own_title="자체 제목 B", categories=[EXT + "TAG-B"])]
        self.stack.enter_context(mock.patch.object(g, "iter_candidate_lanes", lambda *a, **k: iter([("technology", [dict(c) for c in self.candidates])])))
        self.reply = None
        self.stack.enter_context(mock.patch.object(g, "call_gemini_with_fallback", self.model))

    def model(self, prompt):
        self.gemini_prompts.append(prompt)
        topic = re.search(r"\[주제\]\n(.*)", prompt).group(1)
        payload = self.reply if self.reply is not None else g.stub_post_data(topic, self.LINK)
        return type("R", (), {"text": json.dumps(payload)})()

    def generate(self):
        out = io.StringIO()
        report = {}
        with contextlib.redirect_stdout(out):
            result = g.generate_blog_posts(slot=9, allow_auto_topic=False, report=report)
        return result, report, out.getvalue()

    def test_the_candidate_without_an_own_title_never_enters_and_the_own_title_is_what_is_stored(self):
        result, report, out = self.generate()
        self.assertIsNotNone(result)
        self.assertEqual(len(self.gemini_prompts), 1)                           # A(자체 제목 없음)는 모델에 가지도 않았다
        self.assertIn("자체 제목 B", self.gemini_prompts[0])
        self.assertNotIn(EXT, self.gemini_prompts[0])
        entry = self.history()[-1]
        self.assertEqual(entry["topic"], "자체 제목 B")                          # 이력의 topic 은 자체 제목뿐
        self.assertNotIn(EXT, json.dumps(self.history(), ensure_ascii=False))
        self.assertNotIn(EXT, out)                                              # 로그
        self.assertIn("자체 제목이 없는 후보 1건은 쓰지 않음", out)               # 빠진 후보는 수만 알린다(제목은 알리지 않는다)
        self.assertNotIn(EXT, json.dumps(report, ensure_ascii=False, default=str).replace("TAG-B", "").replace("EXT-TAG-B", ""))     # 보고용 dict(탈락 기록 포함)
        self.assertEqual(report["rejects"], [])
        text = "\n".join(p.read_text(encoding="utf-8") for p in self.posts())
        self.assertNotIn(EXT + "TITLE", text)                                    # 글의 출처 줄에도 외부 제목이 없다
        self.assertNotIn(EXT + "SUMMARY", text)
        self.assertIn("자체 제목 B", text)

    def test_the_rejection_record_and_public_notice_carry_only_the_own_title(self):
        self.reply = {"skip": True, "reason": "중복 주제로 판단"}
        result, report, out = self.generate()
        self.assertIsNone(result)
        self.assertEqual(report["outcome"], "ALL_REJECTED")
        self.assertEqual([r["title"] for r in report["rejects"]], ["자체 제목 B"])
        notice = g.reject_summary_line(report)
        self.assertIn("자체 제목 B", notice)
        self.assertNotIn(EXT, notice + "\n".join(g.reject_detail_lines(report)) + out)
        with contextlib.redirect_stdout(io.StringIO()):
            g.finish_run(result, report, "schedule", sc.NOW, 9)
        self.assertNotIn(EXT, self.summary_text())
        self.assertIn("자체 제목 B", self.summary_text())

    def test_every_candidate_without_an_own_title_leaves_nothing_for_the_model(self):
        self.candidates = [self.cand(), self.cand(title=EXT + "TITLE-GAMMA")]
        result, report, out = self.generate()
        self.assertIsNone(result)
        self.assertEqual(self.gemini_prompts, [])
        self.assertIn("자체 제목이 없는 후보 2건은 쓰지 않음", out)
        self.assertNotIn(EXT, out + json.dumps(report, ensure_ascii=False, default=str))
        self.assertEqual(self.history(), [])

    def test_external_titles_in_the_history_do_not_come_back_through_the_recent_titles(self):
        self.write_history([
            {"date": "2026-11-01", "topic": EXT + "HISTORY-TOPIC", "kr_title": "자체 글 제목 하나", "en_title": "Own English Title", "source_url": "https://ext.example/h", "slot": 9},
            EXT + "STRING-ENTRY",
            {"date": "2026-11-02", "topic": "자체 주제 둘", "kr_title": "자체 주제 둘", "en_title": "Own Topic Two", "slot": 18},     # 자체 제목과 같은 topic 은 외부 글 제목이 아니다
        ])
        self.generate()
        prompt = self.gemini_prompts[0]
        recent = json.loads(re.search(r"\[최근 다룬 주제/제목 - 같은 소재와 관점 금지\]\n(.*)\n", prompt).group(1))
        self.assertEqual(recent, ["자체 글 제목 하나", "Own English Title", "자체 주제 둘", "자체 주제 둘", "Own Topic Two"])
        self.assertNotIn(EXT, prompt)
        with mock.patch.object(source_policy, "chance_source_policy", return_value="legacy"):         # legacy 는 그대로 — 외부 제목도 '최근 제목'에 들어간다
            self.gemini_prompts.clear()
            self.candidates = [self.cand(own_title=None)]
            self.generate()
        self.assertIn(EXT + "HISTORY-TOPIC", self.gemini_prompts[0])
        self.assertIn(EXT + "STRING-ENTRY", self.gemini_prompts[0])


class OutcomeCodeTest(Base):
    def test_finish_run_ends_green_with_a_notice_for_the_new_code_and_names_the_place(self):
        for slot, where in ((9, "9시 슬롯"), (None, "수동 실행")):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                g.finish_run(None, {"outcome": "SOURCE_POLICY_NO_ACTIVE_PROVIDER", "lanes": []}, "schedule", sc.NOW, slot)         # SystemExit 이 없어야 한다
            text = out.getvalue()
            self.assertIn("[SKIP] code=SOURCE_POLICY_NO_ACTIVE_PROVIDER lanes_tried=0", text)
            self.assertIn(f"::notice::{where}:", text)
            self.assertNotIn("::error::", text)
            self.assertNotIn("::warning::", text)
            self.assertNotIn("다음 실행에서 다시 시도합니다", text)                 # 일 없음은 재시도 대상이 아니다
        summary = self.summary_text()
        self.assertIn("**SOURCE_POLICY_NO_ACTIVE_PROVIDER** — ", summary)
        self.assertIn(g.OUTCOME_TEXT["SOURCE_POLICY_NO_ACTIVE_PROVIDER"], summary)

    def test_the_text_says_what_it_is(self):
        text = g.OUTCOME_TEXT["SOURCE_POLICY_NO_ACTIVE_PROVIDER"]
        for needle in ("allowlist", "ACTIVE", "정상", "외부 호출 0"):
            self.assertIn(needle, text)
        self.assertEqual(source_policy.NO_ACTIVE_OUTCOME, "SOURCE_POLICY_NO_ACTIVE_PROVIDER")


# ----------------------------------------------------------------------------
# 3. 레지스트리 값
# ----------------------------------------------------------------------------
class RegistryValueTest(unittest.TestCase):
    def reg(self, **fields):
        reg = registry.load_registry()
        chance = next(blog for blog in reg["blogs"] if blog["key"] == "chance")
        chance.update(copy.deepcopy(fields))
        return reg

    def test_the_two_values_are_valid_and_absent_means_legacy(self):
        self.assertEqual(registry.validate_registry(self.reg(source_policy="legacy")), [])
        self.assertEqual(registry.validate_registry(self.reg(source_policy="allowlist")), [])
        self.assertEqual(source_policy.SOURCE_POLICIES, ("legacy", "allowlist"))
        self.assertEqual(source_policy.DEFAULT_SOURCE_POLICY, "legacy")

    def test_strange_values_are_rejected(self):
        for bad in ("ALLOWLIST", "Allowlist", "on", "off", "", " allowlist", "allowlist ", "allow list", True, False, None, 1, ["allowlist"], {"a": 1}, "legacy\n"):
            with self.subTest(bad=bad):
                errors = registry.validate_registry(self.reg(source_policy=bad))
                self.assertTrue(any("source_policy" in e for e in errors), (bad, errors))

    def test_it_is_only_for_the_jekyll_git_blog(self):
        reg = registry.load_registry()
        other = next(blog for blog in reg["blogs"] if blog["platform"] == "blogger")
        other["source_policy"] = "allowlist"
        errors = registry.validate_registry(reg)
        self.assertTrue(any("source_policy" in e and "jekyll-git" in e for e in errors), errors)
        reg = registry.load_registry()
        reg["defaults"]["source_policy"] = "allowlist"                          # 기본값으로 물려주면 Blogger 항목이 이 규칙에 걸린다
        self.assertTrue(any("source_policy" in e for e in registry.validate_registry(reg)))

    def test_chance_source_policy_reads_values_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            def write(reg, name="r.json"):
                path = Path(tmp) / name
                path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
                return path
            self.assertEqual(source_policy.chance_source_policy(write(registry.load_registry())), "legacy")
            self.assertEqual(source_policy.chance_source_policy(write(self.reg(source_policy="allowlist"))), "allowlist")
            self.assertEqual(source_policy.chance_source_policy(write(self.reg(source_policy="legacy"))), "legacy")
            for bad in ("ALLOWLIST", "", None, 3, ["allowlist"]):
                with self.subTest(bad=bad), self.assertRaises(registry.RegistryError):
                    source_policy.chance_source_policy(write(self.reg(source_policy=bad), "bad.json"))
            reg = registry.load_registry()
            next(blog for blog in reg["blogs"] if blog["key"] == "chance")["key"] = "other"
            with self.assertRaises(registry.RegistryError):
                source_policy.chance_source_policy(write(reg, "nochance.json"))
            with self.assertRaises(registry.RegistryError):
                source_policy.chance_source_policy(Path(tmp) / "missing.json")
            broken = Path(tmp) / "broken.json"
            broken.write_text("{nope", encoding="utf-8")
            with self.assertRaises(registry.RegistryError):
                source_policy.chance_source_policy(broken)

    def test_other_registry_rules_are_unchanged_by_the_new_check(self):
        reg = registry.load_registry()
        self.assertEqual(registry.validate_registry(reg), [])
        reg["defaults"]["ads"] = "on"
        self.assertTrue(registry.validate_registry(reg))


if __name__ == "__main__":
    unittest.main()
