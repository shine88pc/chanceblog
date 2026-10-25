"""Chance 엔진(generator.py)의 슬롯 판정·분야 폴백·탈락 사유 기록·종료 정책 테스트. 네트워크 없이 돈다.

배경(Task 4 진단): 스케줄 실행이 초록인데 글이 없던 것은 (1) 추첨된 분야에 후보가 0건이면 다른 분야를
시도하지 않고 정상 종료했고 (2) 왜 0건인지 기록이 없었기 때문이다. 이 테스트는 그 둘을 고정한다.
"""
import io
import os
import random
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import generator as g

KST = g.KST


def at(hour, minute=0, day=25):
    return datetime(2026, 10, day, hour, minute, tzinfo=KST)


def run_captured(fn, *args, **kwargs):
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            value = fn(*args, **kwargs)
        except SystemExit as exc:
            return exc, buf.getvalue()
    return value, buf.getvalue()


class FakeResponse:
    def __init__(self, data=b"", url=""):
        self._data, self._url = data, url

    def read(self, *args):
        return self._data

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def rss(items):
    """items: (title, link, published_dt, summary, publisher_url) 목록 → RSS 바이트."""
    body = ""
    for title, link, published, summary, publisher_url in items:
        source = f'<source url="{publisher_url}">pub</source>' if publisher_url else ""
        body += (f"<item><title>{title}</title><link>{link}</link>"
                 f"<pubDate>{format_datetime(published)}</pubDate>"
                 f"<description>{summary}</description>{source}</item>")
    return f"<?xml version='1.0'?><rss><channel>{body}</channel></rss>".encode("utf-8")


def candidate(title="후보 기사", link="https://www.reuters.com/a"):
    return {"title": title, "source": "Reuters", "link": link,
            "publisher_domain": "www.reuters.com", "summary": "요약 " * 40,
            "published": datetime.now(timezone.utc)}


def long_post(topic, link):
    """검증(최소 분량 + 원문 링크 인용)을 통과하는 가짜 Gemini 결과."""
    kr_body = ("이 글은 테스트용 본문입니다. " * 80) + f"\n\n근거는 [원문]({link})에 있습니다.\n"
    en_body = ("This is a test body for the generator. " * 80) + f"\n\nSee [source]({link}).\n"
    fm = "---\nlayout: post\ntitle: \"{t}\"\ncategory: \"{c}\"\ntags: []\n---\n\n{b}"
    return {
        "kr_category": "기술·미래", "kr_title": f"테스트 {topic}", "kr_tags": ["테스트"],
        "kr_content": fm.format(t=f"테스트 {topic}", c="기술·미래", b=kr_body),
        "en_category": "Technology & Future", "en_title": f"Test {topic}", "en_tags": ["test"],
        "en_content": fm.format(t=f"Test {topic}", c="Technology & Future", b=en_body),
        "image_queries": ["technology", "computer hardware"],
    }


class SkipLineTest(unittest.TestCase):
    def test_single_line_with_code_and_fields(self):
        line = g.skip_line("NO_CANDIDATES", lane="economy", fetched=71,
                           reasons={"UNTRUSTED": 60, "AGE": 11})
        self.assertEqual(line, "[SKIP] code=NO_CANDIDATES lane=economy fetched=71 reasons=AGE:11,UNTRUSTED:60")
        self.assertNotIn("\n", line)

    def test_empty_reasons_are_dashed(self):
        self.assertIn("reasons=-", g.skip_line("X", reasons={}))


class StepSummaryTest(unittest.TestCase):
    def test_appends_to_target_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "summary.md"
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(target)}):
                g.write_step_summary("첫 줄")
                g.write_step_summary("둘째 줄")
            text = target.read_text(encoding="utf-8")
        self.assertIn("첫 줄", text)
        self.assertIn("둘째 줄", text)

    def test_no_env_is_a_noop(self):
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
        with mock.patch.dict(os.environ, env, clear=True):
            _, out = run_captured(g.write_step_summary, "내용")
        self.assertEqual(out, "")

    def test_write_failure_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:  # 디렉터리를 파일처럼 열면 OSError
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": tmp}):
                _, out = run_captured(g.write_step_summary, "내용")
        self.assertIn("실행 요약 쓰기 실패", out)


class SlotStateTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(g, "SLOT_HOURS", [9, 18])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_before_first_slot_is_out_of_window(self):
        self.assertEqual(g.slot_state([], at(8, 54)), (None, "OUT_OF_WINDOW"))
        self.assertIsNone(g.current_due_slot([], at(8, 54)))

    def test_after_first_slot_without_post_is_due(self):
        self.assertEqual(g.slot_state([], at(10, 12)), (9, "DUE"))
        self.assertEqual(g.current_due_slot([], at(10, 12)), 9)

    def test_existing_post_for_the_slot_is_already_published(self):
        history = [{"date": "2026-10-25", "slot": 9, "topic": "t"}]
        self.assertEqual(g.slot_state(history, at(10, 12)), (9, "ALREADY_PUBLISHED"))
        self.assertIsNone(g.current_due_slot(history, at(10, 12)))

    def test_second_slot_is_due_when_only_first_is_done(self):
        history = [{"date": "2026-10-25", "slot": 9}]
        self.assertEqual(g.slot_state(history, at(19, 6)), (18, "DUE"))

    def test_manual_post_without_slot_does_not_count(self):
        history = [{"date": "2026-10-25", "slot": None}, "옛 문자열 항목"]
        self.assertEqual(g.slot_state(history, at(10, 12)), (9, "DUE"))

    def test_yesterday_post_does_not_count(self):
        history = [{"date": "2026-10-24", "slot": 9}]
        self.assertEqual(g.slot_state(history, at(10, 12)), (9, "DUE"))

    def test_no_slot_hours_configured_is_out_of_window(self):
        with mock.patch.object(g, "SLOT_HOURS", []):
            self.assertEqual(g.slot_state([], at(12)), (None, "OUT_OF_WINDOW"))


def legacy_first_lane(slot, history, now):
    """폴백 도입 전 choose_editorial_lane 의 계산식(회귀 비교용 사본)."""
    lanes = list(g.EDITORIAL_LANES)
    recent = [item.get("lane") for item in history[-12:]
              if isinstance(item, dict) and item.get("lane") in g.EDITORIAL_LANES]
    weights = {}
    for lane in lanes:
        weights[lane] = 1.0 / (1.0 + recent.count(lane) * 0.65)
        if recent and recent[-1] == lane:
            weights[lane] *= 0.25
        elif len(recent) > 1 and recent[-2] == lane:
            weights[lane] *= 0.6
    latest = history[-1] if history else None
    latest_key = (latest.get("date", ""), latest.get("topic", "")) if isinstance(latest, dict) else str(latest or "")
    seed = f"{now:%Y-%m-%d}|{slot}|{len(history)}|{latest_key}"
    return random.Random(seed).choices(lanes, weights=[weights[lane] for lane in lanes], k=1)[0]


class LaneOrderTest(unittest.TestCase):
    HISTORY = [
        {"date": "2026-10-20", "topic": "a", "lane": "daily_life"},
        {"date": "2026-10-21", "topic": "b", "lane": "technology"},
        {"date": "2026-10-21", "topic": "c", "lane": "economy"},
    ]

    def order(self, slot, history=None, now=None):
        with mock.patch.object(g, "now_kst", return_value=now or at(10)):
            return g.editorial_lane_order(slot, self.HISTORY if history is None else history)

    def test_order_contains_every_lane_once(self):
        order = self.order(9)
        self.assertEqual(sorted(order), sorted(g.EDITORIAL_LANES))
        self.assertEqual(len(order), len(set(order)))

    def test_first_lane_is_unchanged_from_the_old_draw(self):
        for slot in (None, 9, 18):
            for history in ([], self.HISTORY):
                for day in (23, 24, 25):
                    now = at(10, day=day)
                    with self.subTest(slot=slot, n=len(history), day=day):
                        self.assertEqual(self.order(slot, history, now)[0],
                                         legacy_first_lane(slot, history, now))

    def test_choose_editorial_lane_is_the_first_of_the_order(self):
        with mock.patch.object(g, "now_kst", return_value=at(10)):
            self.assertEqual(g.choose_editorial_lane(9, self.HISTORY),
                             g.editorial_lane_order(9, self.HISTORY)[0])

    def test_order_is_deterministic_for_the_same_inputs(self):
        self.assertEqual(self.order(9), self.order(9))

    def test_order_changes_with_the_slot_or_history(self):
        orders = {tuple(self.order(slot)) for slot in (3, 9, 18, 21)}
        self.assertGreater(len(orders), 1)


def fake_pick_factory(lane_results):
    """lane_results: {lane: [후보...]} — 요청된 분야 순서를 기록하는 pick_topic_candidates 대역."""
    calls = []

    def fake(titles, allow_auto_topic=True, editorial_lane=None, stats=None):
        calls.append(editorial_lane)
        found = lane_results.get(editorial_lane, [])
        if stats is not None:
            stats["sources"] = [{"name": f"{editorial_lane}-소스", "fetched": 5 if not found else 8,
                                 "kept": len(found), "drops": {} if found else {"UNTRUSTED": 5}}]
            stats["candidates"] = len(found)
        return found

    return fake, calls


class CollectCandidatesTest(unittest.TestCase):
    ORDER = ["economy", "culture", "technology", "society", "science", "daily_life"]

    def collect(self, lane_results, **kwargs):
        fake, calls = fake_pick_factory(lane_results)
        report = {"lanes": []}
        with mock.patch.object(g, "pick_topic_candidates", fake):
            (found, lane), out = run_captured(
                g.collect_candidates, [], False, self.ORDER, report, **kwargs)
        return found, lane, calls, report, out

    def test_first_lane_with_candidates_is_used_without_fallback_noise(self):
        item = candidate()
        found, lane, calls, report, out = self.collect({"economy": [item]})
        self.assertEqual((found, lane, calls), ([item], "economy", ["economy"]))
        self.assertNotIn("::notice::", out)
        self.assertNotIn("[SKIP]", out)

    def test_empty_lane_falls_back_to_the_next_lane_in_order(self):
        item = candidate()
        found, lane, calls, report, out = self.collect({"technology": [item]})
        self.assertEqual(found, [item])
        self.assertEqual(lane, "technology")
        self.assertEqual(calls, ["economy", "culture", "technology"])  # 후보가 나온 뒤에는 멈춘다
        self.assertEqual([r["lane"] for r in report["lanes"]], calls)
        self.assertIn("[SKIP] code=NO_CANDIDATES lane=economy", out)
        self.assertIn("[SKIP] code=NO_CANDIDATES lane=culture", out)
        self.assertIn("::notice::", out)
        self.assertIn("기술·미래", out)

    def test_every_lane_empty_returns_nothing_and_tries_them_all(self):
        found, lane, calls, report, out = self.collect({})
        self.assertEqual(found, [])
        self.assertEqual(lane, "economy")  # 처음 추첨된 분야
        self.assertEqual(calls, self.ORDER)
        self.assertEqual(out.count("[SKIP] code=NO_CANDIDATES"), len(self.ORDER))
        self.assertNotIn("budget_exceeded", report)

    def test_skip_line_carries_the_drop_reasons(self):
        _, _, _, report, out = self.collect({})
        self.assertIn("reasons=UNTRUSTED:5", out)
        self.assertEqual(report["lanes"][0]["drops"], {"UNTRUSTED": 5})
        self.assertEqual(report["lanes"][0]["fetched"], 5)

    def test_fallback_can_be_disabled(self):
        found, lane, calls, report, out = self.collect({"technology": [candidate()]}, fallback=False)
        self.assertEqual((found, calls), ([], ["economy"]))

    def test_time_budget_stops_the_search_and_says_so(self):
        ticks = iter([0, 10_000, 10_000])  # 시작 시각, 두 번째 분야 직전(이미 상한 초과)
        found, lane, calls, report, out = self.collect({}, clock=lambda: next(ticks))
        self.assertEqual(calls, ["economy"])
        self.assertTrue(report["budget_exceeded"])
        self.assertIn("::warning::분야 대체 시도를", out)


class FetchNewsStatsTest(unittest.TestCase):
    """소스 줄과 stats 에 탈락 사유가 정확히 남는지."""
    FEED = "https://feed.test/economy"
    NOW = datetime.now(timezone.utc)

    def run_fetch(self, items, resolve=None, excerpt="", sources=None):
        sources = sources or [{"name": "테스트 소스", "google": True, "lane": "economy", "url": self.FEED}]
        stats = {}

        def fake_urlopen(req, timeout=0):
            url = getattr(req, "full_url", req)
            if url != self.FEED:
                raise AssertionError(f"예상하지 못한 네트워크 호출: {url}")
            return FakeResponse(rss(items))

        resolver = resolve or (lambda url: "")
        with mock.patch.object(g, "NEWS_SOURCES", sources), \
                mock.patch.object(g.urllib.request, "urlopen", fake_urlopen), \
                mock.patch.object(g, "_resolve_article_url", side_effect=resolver), \
                mock.patch.object(g, "_fetch_source_excerpt", return_value=excerpt):
            merged, out = run_captured(g.fetch_news_items, "economy", stats=stats)
        return merged, stats, out

    def fresh(self, hours=1):
        return self.NOW - timedelta(hours=hours)

    def test_each_gate_is_counted_under_its_code(self):
        long_summary = "요약 문장입니다. " * 20
        items = [
            ("오래된 기사", "https://news.example/1", self.fresh(100), long_summary, ""),
            ("작은 매체 기사", "https://news.example/2", self.fresh(), long_summary, "https://small.example"),
            ("해석 실패 기사", "https://news.example/3", self.fresh(), long_summary, "https://www.reuters.com"),
            ("게시자 불일치 기사", "https://news.example/4", self.fresh(), long_summary, "https://www.reuters.com"),
            ("요약 부족 기사", "https://news.example/5", self.fresh(), "짧음", "https://www.reuters.com"),
            ("통과 기사", "https://news.example/6", self.fresh(), long_summary, "https://www.reuters.com"),
            ("", "https://news.example/7", self.fresh(), long_summary, ""),
        ]
        resolved = {
            "https://news.example/3": "",
            "https://news.example/4": "https://other.example/a",
            "https://news.example/5": "https://www.reuters.com/e",
            "https://news.example/6": "https://www.reuters.com/ok",
        }
        merged, stats, out = self.run_fetch(items, resolve=lambda url: resolved.get(url, ""))
        self.assertEqual([m["title"] for m in merged], ["통과 기사"])
        src = stats["sources"][0]
        self.assertEqual((src["fetched"], src["kept"]), (7, 1))
        self.assertEqual(src["drops"], {"AGE": 1, "UNTRUSTED": 1, "UNRESOLVED": 1,
                                        "HOST_MISMATCH": 1, "SHORT_SUMMARY": 1, "NO_TITLE": 1})
        self.assertIn("소스 테스트 소스: 7건 중 1건 사용 (탈락: ", out)
        self.assertIn("AGE 1", out)

    def test_resolution_cap_is_reported_as_unchecked(self):
        summary = "요약 문장입니다. " * 20
        items = [(f"기사 {i}", f"https://news.example/{i}", self.fresh(), summary, "https://www.reuters.com")
                 for i in range(8)]
        merged, stats, out = self.run_fetch(items)  # 해석은 전부 실패
        self.assertEqual(merged, [])
        self.assertEqual(stats["sources"][0]["drops"], {"UNRESOLVED": 5, "UNCHECKED": 3})

    def test_tech_filter_drops_are_counted(self):
        summary = "요약 문장입니다. " * 20
        sources = [{"name": "기술만", "lane": "economy", "tech_filter": True, "url": self.FEED}]
        items = [("오늘 날씨", "https://www.reuters.com/w", self.fresh(), summary, "")]
        merged, stats, out = self.run_fetch(items, sources=sources)
        self.assertEqual(stats["sources"][0]["drops"], {"NOT_TECH": 1})

    def test_failed_source_is_recorded_not_hidden(self):
        sources = [{"name": "죽은 소스", "lane": "economy", "url": "https://dead.test/feed"}]
        merged, stats, out = self.run_fetch([], sources=sources)
        self.assertEqual(merged, [])
        self.assertIn("수집 실패", out)
        self.assertEqual(stats["sources"][0]["error"], "AssertionError")

    def test_stats_are_optional_and_the_result_is_the_same(self):
        summary = "요약 문장입니다. " * 20
        items = [("통과 기사", "https://news.example/6", self.fresh(), summary, "https://www.reuters.com")]
        resolver = lambda url: "https://www.reuters.com/ok"  # noqa: E731
        with_stats, _, _ = self.run_fetch(items, resolve=resolver)
        sources = [{"name": "테스트 소스", "google": True, "lane": "economy", "url": self.FEED}]
        with mock.patch.object(g, "NEWS_SOURCES", sources), \
                mock.patch.object(g.urllib.request, "urlopen",
                                  lambda req, timeout=0: FakeResponse(rss(items))), \
                mock.patch.object(g, "_resolve_article_url", side_effect=resolver):
            without_stats, _ = run_captured(g.fetch_news_items, "economy")
        self.assertEqual([m["title"] for m in with_stats], [m["title"] for m in without_stats])


class PickTopicStatsTest(unittest.TestCase):
    def test_duplicates_are_counted_and_candidates_capped(self):
        items = [candidate("이미 쓴 제목입니다 반도체"), candidate("새로운 주제 하나"),
                 candidate("새로운 주제 둘 다른 이야기"), candidate("새로운 주제 셋 또 다른 것"),
                 candidate("새로운 주제 넷 마지막")]
        stats = {}
        with mock.patch.object(g, "fetch_news_items", return_value=items):
            picked = g.pick_topic_candidates(["이미 쓴 제목입니다 반도체"], True, "economy", stats=stats)
        self.assertEqual(len(picked), g.MAX_ATTEMPTS)
        self.assertEqual(stats["duplicates"], 1)
        self.assertEqual(stats["candidates"], g.MAX_ATTEMPTS)

    def test_default_call_keeps_the_old_signature(self):
        with mock.patch.object(g, "fetch_news_items", return_value=[candidate("하나")]):
            self.assertEqual(len(g.pick_topic_candidates([], True, "economy")), 1)


class GenerateWithFallbackTest(unittest.TestCase):
    """DRY_RUN + 가짜 Gemini/Unsplash 로 generate_blog_posts 전체 흐름(파일은 쓰지 않음)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name, value in (("DRY_RUN", True), ("STUB_GEMINI", True), ("STUB_UNSPLASH", True),
                            ("POSTS_DIR", self.root / "_posts"),
                            ("HISTORY_FILE", self.root / "history.json")):
            patcher = mock.patch.object(g, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(g, "now_kst", return_value=at(10, 12))
        patcher.start()
        self.addCleanup(patcher.stop)
        # 처음 추첨이 technology 가 아닌 슬롯을 고른다(폴백이 실제로 쓰이도록).
        self.slot = next(s for s in range(1, 30)
                         if g.editorial_lane_order(s, [])[0] != "technology")
        self.order = g.editorial_lane_order(self.slot, [])

    def fake_fetch(self, results):
        def fake(editorial_lane=None, stats=None):
            found = results.get(editorial_lane, [])
            if stats is not None:
                stats.setdefault("sources", []).append(
                    {"name": f"{editorial_lane}", "fetched": 4, "kept": len(found),
                     "drops": {} if found else {"UNTRUSTED": 4}})
            return found
        return fake

    LINK = "https://www.reuters.com/a"

    def generate(self, results, **kwargs):
        report = {}
        with mock.patch.object(g, "fetch_news_items", self.fake_fetch(results)), \
                mock.patch.object(g, "stub_post_data", lambda topic: long_post(topic, self.LINK)):
            value, out = run_captured(g.generate_blog_posts, slot=self.slot, report=report, **kwargs)
        return value, report, out

    def test_empty_first_lane_still_publishes_from_the_next_lane_with_candidates(self):
        value, report, out = self.generate(
            {"technology": [candidate("기술 기사", self.LINK)]}, allow_auto_topic=False)
        self.assertIsNotNone(value)
        self.assertEqual(report["outcome"], "PUBLISHED")
        self.assertEqual(report["lane"], "technology")
        self.assertEqual(len(report["lanes"]), self.order.index("technology") + 1)
        self.assertIn("::notice::", out)
        # 연습 실행이라는 사실을 완료 문구에 밝힌다(파일이 생겼다고 오해하지 않게)
        self.assertIn("블로그 글 생성 완료 (DRY_RUN: 파일·기록은 저장되지 않았습니다):", out)

    def test_all_lanes_empty_returns_none_with_all_lanes_empty_outcome(self):
        value, report, out = self.generate({}, allow_auto_topic=False)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], "ALL_LANES_EMPTY")
        self.assertEqual(len(report["lanes"]), len(g.EDITORIAL_LANES))
        self.assertEqual(out.count("[SKIP] code=NO_CANDIDATES"), len(g.EDITORIAL_LANES))

    def test_candidates_all_rejected_is_all_rejected_in_schedule_mode(self):
        link = "https://www.reuters.com/a"
        results = {self.order[0]: [candidate("기사", link)]}
        report = {}
        with mock.patch.object(g, "fetch_news_items", self.fake_fetch(results)), \
                mock.patch.object(g, "stub_post_data", lambda topic: {"skip": True, "reason": "중복"}):
            value, out = run_captured(g.generate_blog_posts, slot=self.slot,
                                      allow_auto_topic=False, report=report)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], "ALL_REJECTED")

    def test_candidates_all_rejected_raises_in_manual_mode(self):
        link = "https://www.reuters.com/a"
        results = {self.order[0]: [candidate("기사", link)]}
        report = {}
        with mock.patch.object(g, "fetch_news_items", self.fake_fetch(results)), \
                mock.patch.object(g, "stub_post_data", lambda topic: {"skip": True, "reason": "중복"}):
            with self.assertRaises(RuntimeError):
                run_captured(g.generate_blog_posts, slot=None, allow_auto_topic=True, report=report)
        self.assertEqual(report["outcome"], "ALL_REJECTED")

    def test_report_is_optional(self):
        link = "https://www.reuters.com/a"
        results = {"technology": [candidate("기술 기사", link)]}
        with mock.patch.object(g, "fetch_news_items", self.fake_fetch(results)), \
                mock.patch.object(g, "stub_post_data", lambda topic: long_post(topic, link)):
            value, _ = run_captured(g.generate_blog_posts, slot=self.slot, allow_auto_topic=False)
        self.assertIsNotNone(value)


class MainPolicyTest(unittest.TestCase):
    """main()/finish_run 의 종료 정책: 정상 스킵 0, 경고 0(+주석), 모든 분야 비음 1."""

    def setUp(self):
        for name, value in (("DRY_RUN", False), ("STUB_GEMINI", False), ("FIX_IMAGES", False)):
            patcher = mock.patch.object(g, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(g, "SLOT_HOURS", [9, 18])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.summary = Path(self.tmp.name) / "summary.md"
        env = {k: v for k, v in os.environ.items() if k != "PIPELINE_PAUSE"}
        env["GITHUB_STEP_SUMMARY"] = str(self.summary)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def summary_text(self):
        return self.summary.read_text(encoding="utf-8") if self.summary.exists() else ""

    def run_main(self, event, now, history=(), generate=None):
        def boom(*args, **kwargs):
            raise AssertionError("이 경로에서는 글 생성을 시도하면 안 됩니다")
        with mock.patch.object(g, "EVENT_NAME", event), \
                mock.patch.object(g, "now_kst", return_value=now), \
                mock.patch.object(g, "read_history", return_value=list(history)), \
                mock.patch.object(g, "generate_blog_posts", generate or boom):
            return run_captured(g.main)

    def test_pause_does_nothing_and_says_so(self):
        with mock.patch.dict(os.environ, {"PIPELINE_PAUSE": "true"}):
            _, out = self.run_main("schedule", at(10, 12))
        self.assertIn("[SKIP] code=PAUSED", out)
        self.assertIn("[일시정지]", out)
        self.assertIn("일시정지", self.summary_text())

    def test_pause_off_values_do_not_pause(self):
        with mock.patch.dict(os.environ, {"PIPELINE_PAUSE": ""}):
            _, out = self.run_main("schedule", at(8, 54))
        self.assertNotIn("[일시정지]", out)

    def test_before_first_slot_is_a_normal_skip_with_its_own_code(self):
        value, out = self.run_main("schedule", at(8, 54))
        self.assertIsNone(value)
        self.assertIn("[SKIP] code=OUT_OF_WINDOW", out)
        self.assertIn("첫 게시 시각 전", out)
        self.assertIn("OUT_OF_WINDOW", self.summary_text())

    def test_already_published_slot_is_a_normal_skip_with_its_own_code(self):
        history = [{"date": "2026-10-25", "slot": 9}]
        value, out = self.run_main("schedule", at(10, 12), history)
        self.assertIsNone(value)
        self.assertIn("[SKIP] code=ALREADY_PUBLISHED", out)
        self.assertIn("9시 슬롯 글이 이미 있음", out)

    def fake_generate(self, outcome, result=None, lanes=2):
        def fake(slot=None, allow_auto_topic=True, report=None, **kwargs):
            report["outcome"] = outcome
            report["lanes"] = [{"lane": "economy", "label": "경제·일", "sources": 2, "failed_sources": 0,
                                "fetched": 70, "passed": 0, "candidates": 0,
                                "drops": {"UNTRUSTED": 60, "AGE": 10}}] * lanes
            report["lane_label"] = "경제·일"
            if result:
                report.update(title="제목", source="Reuters", paths=["_posts/a.md", "_posts/b.md"])
            return result
        return fake

    def test_all_lanes_empty_in_a_due_slot_is_red(self):
        value, out = self.run_main("schedule", at(10, 12),
                                   generate=self.fake_generate("ALL_LANES_EMPTY"))
        self.assertIsInstance(value, SystemExit)
        self.assertEqual(value.code, 1)
        self.assertIn("::error::9시 슬롯", out)
        self.assertIn("[SKIP] code=ALL_LANES_EMPTY", out)
        text = self.summary_text()
        self.assertIn("ALL_LANES_EMPTY", text)
        self.assertIn("UNTRUSTED 60, AGE 10", text)  # 사유별 개수가 요약에 남는다

    def test_all_rejected_is_a_warning_not_a_failure(self):
        value, out = self.run_main("schedule", at(10, 12),
                                   generate=self.fake_generate("ALL_REJECTED"))
        self.assertIsNone(value)
        self.assertIn("::warning::9시 슬롯", out)
        self.assertIn("[SKIP] code=ALL_REJECTED", out)

    def test_budget_cut_search_is_a_warning(self):
        value, out = self.run_main("schedule", at(10, 12),
                                   generate=self.fake_generate("NO_CANDIDATES"))
        self.assertIsNone(value)
        self.assertIn("::warning::", out)

    def test_published_run_is_green_and_summarised(self):
        value, out = self.run_main("schedule", at(10, 12),
                                   generate=self.fake_generate("PUBLISHED", result=("a", "b"), lanes=1))
        self.assertIsNone(value)
        self.assertNotIn("::error::", out)
        text = self.summary_text()
        self.assertIn("글을 만들었습니다", text)
        self.assertIn("제목", text)
        self.assertIn("`_posts/a.md`", text)

    def test_manual_run_with_no_article_is_red_too(self):
        value, out = self.run_main("workflow_dispatch", at(10, 12),
                                   generate=self.fake_generate("ALL_LANES_EMPTY"))
        self.assertIsInstance(value, SystemExit)
        self.assertEqual(value.code, 1)
        self.assertIn("::error::수동 실행", out)

    def test_missing_api_key_still_fails_loudly(self):
        with mock.patch.object(g, "STUB_GEMINI", True):
            with self.assertRaises(RuntimeError):
                run_captured(g.main)


class SourceListTest(unittest.TestCase):
    def test_dead_bloter_feed_is_gone(self):
        self.assertNotIn("블로터", [s["name"] for s in g.NEWS_SOURCES])
        self.assertFalse(any("bloter.net/feed" in s["url"] for s in g.NEWS_SOURCES))

    def test_every_lane_has_at_least_one_source(self):
        lanes = {s.get("lane") for s in g.NEWS_SOURCES}
        self.assertEqual(lanes, set(g.EDITORIAL_LANES))

    def test_every_drop_code_has_a_label(self):
        for code in ("NO_TITLE", "NOT_TECH", "AGE", "UNTRUSTED", "UNCHECKED", "UNRESOLVED",
                     "HOST_MISMATCH", "SHORT_SUMMARY", "DUPLICATE"):
            self.assertIn(code, g.DROP_LABELS)


if __name__ == "__main__":
    unittest.main()
