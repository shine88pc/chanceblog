"""Chance 엔진(generator.py)의 슬롯 판정·분야 폴백·탈락 사유 기록·종료 정책 테스트. 네트워크 없이 돈다.

배경(운영자 요청서 4번 '발행 복구' 진단): 스케줄 실행이 초록인데 글이 없던 것은 (1) 추첨된 분야에 후보가 0건이면 다른 분야를
시도하지 않고 정상 종료했고 (2) 왜 0건인지 기록이 없었기 때문이다. 이 테스트는 그 둘을 고정한다.
"""
import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest import mock
from xml.sax.saxutils import escape

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
    """items: (title, link, published_dt, summary, publisher_url[, 분류 태그 목록]) 목록 → RSS 바이트."""
    body = ""
    for title, link, published, summary, publisher_url, *rest in items:
        source = f'<source url="{publisher_url}">pub</source>' if publisher_url else ""
        categories = "".join(f"<category>{escape(c)}</category>" for c in (rest[0] if rest else ()))
        body += (f"<item><title>{title}</title><link>{link}</link>"
                 f"<pubDate>{format_datetime(published)}</pubDate>"
                 f"<description>{summary}</description>{source}{categories}</item>")
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


def thin_post(topic, link):
    """분량 검증(한국어 최소 1000자)에 못 미치는 가짜 Gemini 결과. 실제 실행 #61에서 973자짜리 본문이 나온 상황."""
    data = long_post(topic, link)
    front = "---\nlayout: post\ntitle: \"t\"\ncategory: \"c\"\ntags: []\n---\n\n"
    data["kr_content"] = front + "너무 짧은 본문입니다. " * 5 + f"\n\n[원문]({link})\n"
    return data


class FakeGemini:
    """후보 제목(=프롬프트)에 따라 다른 응답을 내는 대역. responses 값이 예외면 던진다."""

    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def prompt(self, item, recent_titles, category_hint="", allow_skip=False, editorial_lane=None):
        return item["title"]

    def call(self, prompt):
        self.calls.append(prompt)
        value = self.responses[prompt]
        if isinstance(value, Exception):
            raise value
        return mock.Mock(text=value)


class SkipLineTest(unittest.TestCase):
    def test_single_line_with_code_and_fields(self):
        line = g.skip_line("LANE_EMPTY", lane="economy", fetched=71,
                           reasons={"UNTRUSTED": 60, "AGE": 11})
        self.assertEqual(line, "[SKIP] code=LANE_EMPTY lane=economy fetched=71 reasons=AGE:11,UNTRUSTED:60")
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

    def test_every_order_is_a_permutation_of_all_lanes(self):
        for slot in range(1, 40):
            with self.subTest(slot=slot):
                self.assertEqual(sorted(self.order(slot)), sorted(g.EDITORIAL_LANES))

    def test_fallback_order_is_a_weighted_draw_not_a_fixed_sort(self):
        tails = [self.order(slot)[1:] for slot in range(1, 40)]
        self.assertTrue(any(tail != sorted(tail) for tail in tails))
        self.assertTrue(any(tail != sorted(tail, reverse=True) for tail in tails))
        self.assertGreater(len({tuple(tail) for tail in tails}), 5)

    def test_recently_used_lanes_are_drawn_first_less_often(self):
        history = [{"date": f"2026-10-{20 + i % 5}", "topic": f"t{i}", "lane": "economy"} for i in range(10)]
        firsts = Counter(self.order(slot, history)[0] for slot in range(1, 400))
        others = min(firsts[lane] for lane in g.EDITORIAL_LANES if lane != "economy")
        self.assertLess(firsts["economy"], others)


def fake_pick_factory(lane_results, errors=(), time_skipped=()):
    """lane_results: {lane: [후보...]} — 요청된 분야 순서와 넘겨받은 마감 인자를 기록하는 pick_topic_candidates 대역.
    errors: 소스 수집이 모두 실패한 것으로 꾸밀 분야. time_skipped: 마감 때문에 소스를 건너뛴 것으로 꾸밀 분야."""
    calls = []

    def fake(titles, allow_auto_topic=True, editorial_lane=None, stats=None, **kwargs):
        calls.append(editorial_lane)
        fake.kwargs.append(kwargs)
        found = lane_results.get(editorial_lane, [])
        if stats is not None:
            if editorial_lane in errors:
                stats["sources"] = [{"name": f"{editorial_lane}-소스", "fetched": 0, "kept": 0,
                                     "drops": {}, "error": "URLError"}]
            else:
                stats["sources"] = [{"name": f"{editorial_lane}-소스", "fetched": 5 if not found else 8,
                                     "kept": len(found), "drops": {} if found else {"UNTRUSTED": 5}}]
            if editorial_lane in time_skipped:
                stats["time_skipped"] = 2
            stats["candidates"] = len(found)
        return found

    fake.kwargs = []
    return fake, calls


class CollectCandidatesTest(unittest.TestCase):
    ORDER = ["economy", "culture", "technology", "society", "science", "daily_life"]

    def collect(self, lane_results, errors=(), time_skipped=(), **kwargs):
        fake, calls = fake_pick_factory(lane_results, errors, time_skipped)
        self.fake = fake
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
        self.assertIn("[SKIP] code=LANE_EMPTY lane=economy", out)
        self.assertIn("[SKIP] code=LANE_EMPTY lane=culture", out)
        self.assertNotIn("code=NO_CANDIDATES", out)  # 이 코드는 '실행 결과'에만 쓴다
        self.assertIn("::notice::", out)
        self.assertIn("기술·미래", out)

    def test_every_lane_empty_returns_nothing_and_tries_them_all(self):
        found, lane, calls, report, out = self.collect({})
        self.assertEqual(found, [])
        self.assertEqual(lane, "economy")  # 처음 추첨된 분야
        self.assertEqual(calls, self.ORDER)
        self.assertEqual(out.count("[SKIP] code=LANE_EMPTY"), len(self.ORDER))
        self.assertNotIn("budget_exceeded", report)
        self.assertFalse(report["sources_unreachable"])

    def test_skip_line_carries_the_drop_reasons(self):
        _, _, _, report, out = self.collect({})
        self.assertIn("sources=1 failed=0 fetched=5 passed=0 reasons=UNTRUSTED:5", out)
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

    def test_lane_empty_line_reports_how_many_sources_failed(self):
        _, _, _, report, out = self.collect({}, errors={"economy"})
        line = next(row for row in out.splitlines() if "[SKIP]" in row and "lane=economy" in row)
        self.assertIn("code=LANE_EMPTY", line)
        self.assertIn("sources=1 failed=1", line)
        self.assertEqual(report["lanes"][0]["failed_sources"], 1)

    def test_every_attempted_source_failing_is_flagged_unreachable(self):
        _, _, _, report, _ = self.collect({}, errors=set(self.ORDER))
        self.assertTrue(report["sources_unreachable"])

    def test_one_reachable_source_is_enough_to_not_be_unreachable(self):
        _, _, _, report, _ = self.collect({}, errors=set(self.ORDER[:-1]))
        self.assertFalse(report["sources_unreachable"])

    def test_unreachable_is_decided_on_what_was_attempted_even_when_the_budget_cut_the_search(self):
        ticks = iter([0, 10_000, 10_000])
        _, _, calls, report, _ = self.collect({}, errors={"economy"}, clock=lambda: next(ticks))
        self.assertEqual(calls, ["economy"])
        self.assertTrue(report["budget_exceeded"])
        self.assertTrue(report["sources_unreachable"])

    def test_deadline_and_clock_reach_the_source_loop(self):
        clock = lambda: 100  # noqa: E731
        self.collect({"economy": [candidate()]}, clock=clock)
        self.assertEqual(self.fake.kwargs[0], {"deadline": 100 + g.LANE_SEARCH_BUDGET_SECONDS, "clock": clock})

    def test_a_lane_cut_short_inside_the_deadline_marks_the_budget(self):
        _, _, calls, report, _ = self.collect({}, time_skipped={"economy"})
        self.assertTrue(report["budget_exceeded"])
        self.assertEqual(calls, self.ORDER)  # 실제 시계는 상한 전이므로 다음 분야는 계속 시도한다


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

    def test_exclude_title_regex_drops_are_counted_as_excluded(self):
        summary = "요약 문장입니다. " * 20
        sources = [{"name": "제외형", "lane": "economy", "url": self.FEED, "exclude_title": r"^APOD\b|\bquiz\b"}]
        items = [("APOD: 오늘의 사진", "https://www.reuters.com/a", self.fresh(), summary, ""),
                 ("Take our Quiz", "https://www.reuters.com/b", self.fresh(), summary, ""),
                 ("통과 기사", "https://www.reuters.com/c", self.fresh(), summary, "")]
        merged, stats, out = self.run_fetch(items, sources=sources)
        self.assertEqual([m["title"] for m in merged], ["통과 기사"])
        self.assertEqual(stats["sources"][0]["drops"], {"EXCLUDED": 2})
        self.assertIn("EXCLUDED 2", out)

    def test_a_source_on_a_blocked_host_is_never_requested(self):
        sources = [{"name": "차단 호스트 소스", "lane": "technology", "url": "https://www.aitimes.com/rss/allArticle.xml",
                    "terms": {"status": "unverified"}}]

        def forbidden(req, timeout=0):
            raise AssertionError(f"차단 호스트를 요청했다: {getattr(req, 'full_url', req)}")

        stats = {}
        with mock.patch.object(g, "NEWS_SOURCES", sources), mock.patch.object(g.urllib.request, "urlopen", forbidden):
            merged, out = run_captured(g.fetch_news_items, "technology", stats=stats)
        self.assertEqual(merged, [])
        self.assertIn("약관상 접근하지 않는 도메인", out)
        self.assertNotIn("sources", stats)

    def test_a_link_with_markup_or_whitespace_is_dropped_as_unresolved(self):
        summary = "요약 문장입니다. " * 20
        sources = [{"name": "링크 시험", "lane": "economy", "url": self.FEED}]
        hostile = escape("https://www.reuters.com/a\n\n## injected heading\n<img src=x onerror=alert(1)>")
        items = [("악성 링크 기사", hostile, self.fresh(), summary, ""),
                 ("공백 링크 기사", "https://www.reuters.com/b c", self.fresh(), summary, ""),
                 ("정상 기사", "https://www.reuters.com/ok?x=1&amp;y=2#frag", self.fresh(), summary, "")]
        merged, stats, out = self.run_fetch(items, sources=sources)
        self.assertEqual([m["title"] for m in merged], ["정상 기사"])
        self.assertEqual(merged[0]["link"], "https://www.reuters.com/ok?x=1&y=2#frag")
        self.assertEqual(stats["sources"][0]["drops"], {"UNRESOLVED": 2})

    def test_every_unsafe_character_and_scheme_in_a_link_is_dropped_as_unresolved(self):
        # 링크는 글의 출처 목록·인용 줄에 그대로 들어간다. 마크다운·HTML 을 만들 수 있는 글자와 http(s) 아닌 주소는 하나씩 걸러야 한다.
        summary = "요약 문장입니다. " * 20
        sources = [{"name": "링크 시험", "lane": "economy", "url": self.FEED}]
        bad = ["https://www.reuters.com/a" + ch + "b" for ch in '<>"\'\\()[] \t']
        bad += ["ftp://www.reuters.com/a", "javascript:alert(1)", "//www.reuters.com/a",
                "https://www.reuters.com/x)[click](javascript:alert(1))"]
        control = ("정상 기사", "https://www.reuters.com/ok", self.fresh(), summary, "")
        for link in bad:
            with self.subTest(link=link):
                items = [("나쁜 링크 기사", escape(link), self.fresh(), summary, ""), control]
                merged, stats, out = self.run_fetch(items, sources=sources)
                self.assertEqual([m["title"] for m in merged], ["정상 기사"])
                self.assertEqual(stats["sources"][0]["drops"], {"UNRESOLVED": 1})

    def test_ordinary_links_with_query_percent_unicode_and_port_are_kept(self):
        summary = "요약 문장입니다. " * 20
        sources = [{"name": "링크 시험", "lane": "economy", "url": self.FEED}]
        good = ["https://www.reuters.com/ok?x=1&y=2#frag", "https://www.reuters.com/a%20b/%E2%80%99",
                "https://www.reuters.com/기사/한글", "http://www.reuters.com:8080/a"]
        items = [(f"정상 링크 {n}", escape(link), self.fresh(), summary, "") for n, link in enumerate(good)]
        merged, stats, out = self.run_fetch(items, sources=sources)
        self.assertEqual(sorted(m["link"] for m in merged), sorted(good))
        self.assertEqual(stats["sources"][0]["drops"], {})

    def test_an_atom_href_with_a_trailing_newline_is_dropped_as_unresolved(self):
        # Atom 의 href 속성은 파서가 다듬지 않는다. 끝의 줄바꿈이 정규식 `$` 에 걸려 통과하면 안 된다.
        summary = "요약 문장입니다. " * 20
        sources = [{"name": "링크 시험", "lane": "economy", "url": self.FEED}]
        updated = self.fresh().isoformat()

        def entry(title, href):
            return (f"<entry><title>{title}</title><link href='{href}'/><updated>{updated}</updated>"
                    f"<summary>{summary}</summary></entry>")

        atom = ("<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>"
                + entry("끝 줄바꿈 기사", "https://www.reuters.com/a&#10;")
                + entry("정상 기사", "https://www.reuters.com/ok") + "</feed>").encode("utf-8")
        stats = {}
        with mock.patch.object(g, "NEWS_SOURCES", sources), \
                mock.patch.object(g.urllib.request, "urlopen", lambda req, timeout=0: FakeResponse(atom)), \
                mock.patch.object(g, "_fetch_source_excerpt", return_value=""):
            merged, out = run_captured(g.fetch_news_items, "economy", stats=stats)
        self.assertEqual([m["title"] for m in merged], ["정상 기사"])
        self.assertEqual(stats["sources"][0]["drops"], {"UNRESOLVED": 1})

    def test_items_between_36_and_72_hours_old_are_kept_and_older_ones_are_dropped_as_age(self):
        # 신선도 한도는 72시간이다(2026-10-26): 금요일 발표가 월요일 슬롯까지 닿게 한다. 한도 안팎의 경계를 고정한다.
        summary = "요약 문장입니다. " * 20
        self.assertEqual(g.NEWS_MAX_AGE_HOURS, 72)
        self.assertEqual(g.DROP_LABELS["AGE"], "72시간 초과")
        items = [("71시간 된 기사", "https://www.reuters.com/a", self.fresh(71), summary, ""),
                 ("40시간 된 기사", "https://www.reuters.com/b", self.fresh(40), summary, ""),
                 ("73시간 된 기사", "https://www.reuters.com/c", self.fresh(73), summary, "")]
        sources = [{"name": "시간 시험", "lane": "economy", "url": self.FEED}]
        merged, stats, out = self.run_fetch(items, sources=sources)
        self.assertEqual(sorted(m["title"] for m in merged), ["40시간 된 기사", "71시간 된 기사"])
        self.assertEqual(stats["sources"][0]["drops"], {"AGE": 1})

    def test_page_delay_waits_between_consecutive_article_page_fetches_only(self):
        short = "짧음"
        items = [(f"기사 {i}", f"https://www.reuters.com/a{i}", self.fresh(), short, "") for i in range(3)]
        with mock.patch.object(g.time, "sleep") as sleep:
            merged, stats, out = self.run_fetch(items, sources=[{"name": "예절 시험", "lane": "economy", "url": self.FEED, "page_delay": 2}],
                                                excerpt="긴 요약 문장입니다. " * 20)
        self.assertEqual(len(merged), 3)
        self.assertEqual([c.args for c in sleep.call_args_list], [(2,), (2,)])   # 세 번 읽는 사이사이에 두 번
        with mock.patch.object(g.time, "sleep") as sleep:
            self.run_fetch(items, sources=[{"name": "지연 없음", "lane": "economy", "url": self.FEED}], excerpt="긴 요약 문장입니다. " * 20)
        sleep.assert_not_called()

    def test_display_name_is_what_the_post_shows_and_name_is_the_fallback(self):
        summary = "요약 문장입니다. " * 20
        items = [("통과 기사", "https://www.reuters.com/a", self.fresh(), summary, "")]
        merged, stats, out = self.run_fetch(items, sources=[{"name": "소스 · 경제", "display_name": "표시 이름", "lane": "economy", "url": self.FEED}])
        self.assertEqual([m["source"] for m in merged], ["표시 이름"])
        self.assertIn("소스 소스 · 경제: 1건 중 1건 사용", out)  # 로그에는 name 이 보인다
        merged, stats, out = self.run_fetch(items, sources=[{"name": "이름만 있는 소스", "lane": "economy", "url": self.FEED}])
        self.assertEqual([m["source"] for m in merged], ["이름만 있는 소스"])

    def test_atom_text_inside_child_elements_is_read_as_xhtml_text(self):
        # Statistics Canada The Daily 는 제목·요약이 type="xhtml" 이라 글자가 div·span 안에 있다. 예전에는 빈 제목으로 읽혀 전부 NO_TITLE 이 됐다.
        atom = ("<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'><entry>"
                "<title type='xhtml'><div xmlns='http://www.w3.org/1999/xhtml'>Retail trade, <span class='refper'>August 2026</span></div></title>"
                "<link href='https://www.statcan.gc.ca/daily-quotidien/261023/dq261023a-eng.htm'></link>"
                "<updated>2026-10-23T08:30:00-04:00</updated>"
                "<summary type='xhtml'><div xmlns='http://www.w3.org/1999/xhtml'>Retail sales increased 1.2% to $74.6 billion in August.&#160;Sales were up.</div></summary>"
                "</entry></feed>").encode("utf-8")
        item = g.parse_feed(atom)[0]
        self.assertEqual(item["title"], "Retail trade, August 2026")
        self.assertEqual(item["summary"], "Retail sales increased 1.2% to $74.6 billion in August. Sales were up.")
        self.assertEqual(item["link"], "https://www.statcan.gc.ca/daily-quotidien/261023/dq261023a-eng.htm")
        # 평범한 텍스트·CDATA 제목은 그대로다
        plain = ("<rss><channel><item><title>평범한 제목</title><description><![CDATA[<p>요약 <b>문장</b></p>]]></description>"
                 "<link>https://www.reuters.com/a</link></item></channel></rss>").encode("utf-8")
        item = g.parse_feed(plain)[0]
        self.assertEqual((item["title"], item["summary"]), ("평범한 제목", "요약 문장"))

    def test_the_real_statcan_sources_split_one_feed_by_lane(self):
        def entry(title, minutes=0):
            when = (self.fresh(2 + minutes)).astimezone(timezone(timedelta(hours=-4))).isoformat()
            return (f"<entry><title type='xhtml'><div xmlns='http://www.w3.org/1999/xhtml'>{title}</div></title>"
                    f"<link href='https://www.statcan.gc.ca/daily-quotidien/261023/{abs(hash(title)) % 10**8}-eng.htm'></link><updated>{when}</updated>"
                    f"<summary type='xhtml'><div xmlns='http://www.w3.org/1999/xhtml'>{'Summary sentence for the release. ' * 5}</div></summary></entry>")
        titles = ["Retail trade, August 2026", "Consumer Price Index, September 2026", "Retail Services Price Index, August 2026",
                  "Canadian postsecondary enrolments and graduates, 2024/2025", "Health Reports, October 2026",
                  "Natural gas supply and disposition, August 2026", "Violent victimization and unwanted sexual behaviours experienced by 2SLGBTQ+ people in Canada, 2025"]
        atom = ("<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>" + "".join(entry(t, i) for i, t in enumerate(titles)) + "</feed>").encode("utf-8")
        statcan = [s for s in g.NEWS_SOURCES if s["name"].startswith("Statistics Canada")]
        self.assertEqual(len(statcan), 3)
        expected = {"economy": ["Consumer Price Index, September 2026", "Retail trade, August 2026"],
                    "society": ["Canadian postsecondary enrolments and graduates, 2024/2025"],
                    "daily_life": ["Health Reports, October 2026"]}
        for lane, want in expected.items():
            with self.subTest(lane=lane):
                with mock.patch.object(g, "NEWS_SOURCES", statcan), \
                        mock.patch.object(g.urllib.request, "urlopen", lambda req, timeout=0: FakeResponse(atom)), \
                        mock.patch.object(g, "_fetch_source_excerpt", return_value=""):
                    merged, out = run_captured(g.fetch_news_items, lane)
                self.assertEqual(sorted(m["title"] for m in merged), sorted(want))
                self.assertEqual({m["source"] for m in merged}, {"Statistics Canada"})
                self.assertTrue(all(m["notice"] and m["citation"] and m["prompt_rule"] for m in merged))

    def test_the_govuk_sources_read_the_news_atom_feed_and_never_open_article_pages(self):
        gov = [s for s in g.NEWS_SOURCES if s["name"].startswith("GOV.UK")]
        self.assertEqual(len(gov), 2)
        long = "Government sets out new plans to protect homes and businesses from flooding with funding for local schemes. " * 2

        def entry(title, path, hours, summary):
            return (f"<entry><id>tag:www.gov.uk,2005:/government/{path}</id><updated>{self.fresh(hours).isoformat()}</updated>"
                    f"<link rel='alternate' type='text/html' href='https://www.gov.uk/government/{path}'/>"
                    f"<title>{title}</title><summary type='html'>{summary}</summary></entry>")

        atom = ("<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>"
                + entry("New flood schemes announced", "news/new-flood-schemes", 5, long)
                + entry("Short summary news", "news/short-summary", 6, "Too short.")
                + entry("Heat networks speech", "speeches/heat-networks", 7, long)
                + entry("Two new appointments to the board", "news/two-new-appointments", 8, long)
                + entry("Old announcement", "news/old-announcement", 100, long)
                + "</feed>").encode("utf-8")
        requested = []

        def fake_urlopen(req, timeout=0):
            requested.append(getattr(req, "full_url", req))
            return FakeResponse(atom)

        def no_page_reads(url):
            raise AssertionError(f"GOV.UK 기사 페이지를 읽었다: {url}")

        stats = {}
        with mock.patch.object(g, "NEWS_SOURCES", gov), mock.patch.object(g.urllib.request, "urlopen", fake_urlopen), \
                mock.patch.object(g, "_fetch_source_excerpt", side_effect=no_page_reads):
            merged, out = run_captured(g.fetch_news_items, "science", stats=stats)
        self.assertEqual([m["title"] for m in merged], ["New flood schemes announced"])
        self.assertEqual(stats["sources"][0]["drops"], {"EXCLUDED": 2, "SHORT_SUMMARY": 1, "AGE": 1})
        self.assertEqual((merged[0]["source"], merged[0]["publisher_domain"]), ("GOV.UK", "www.gov.uk"))
        self.assertTrue(merged[0]["notice"] and merged[0]["citation"] and merged[0]["prompt_rule"])
        self.assertEqual(requested, [gov[0]["url"]])       # 과학·환경 분야는 에너지·환경 피드만 요청한다
        requested.clear()
        with mock.patch.object(g, "NEWS_SOURCES", gov), mock.patch.object(g.urllib.request, "urlopen", fake_urlopen), \
                mock.patch.object(g, "_fetch_source_excerpt", side_effect=no_page_reads):
            merged, out = run_captured(g.fetch_news_items, "technology", stats={})
        self.assertEqual([m["title"] for m in merged], ["New flood schemes announced"])
        self.assertEqual(requested, [gov[1]["url"]])       # 기술·미래 분야는 과학·기술 피드만 요청한다

    def test_exclude_link_and_exclude_tags_are_counted_as_excluded(self):
        summary = "요약 문장입니다. " * 20
        sources = [{"name": "링크·태그 제외", "lane": "economy", "url": self.FEED,
                    "exclude_link": r"/newsletter/", "exclude_tags": r"^methodolog"}]
        items = [("뉴스레터 모음", "https://www.reuters.com/newsletter/a", self.fresh(), summary, ""),
                 ("방법론 글", "https://www.reuters.com/b", self.fresh(), summary, "", ("Methodological Research",)),
                 ("통과 기사", "https://www.reuters.com/c", self.fresh(), summary, "", ("Economy",))]
        merged, stats, out = self.run_fetch(items, sources=sources)
        self.assertEqual([m["title"] for m in merged], ["통과 기사"])
        self.assertEqual(stats["sources"][0]["drops"], {"EXCLUDED": 2})

    def test_a_direct_feeds_source_tag_is_not_used_as_the_publisher(self):
        # UN News 처럼 직접 RSS 항목에 피드 자기소개용 <source> 가 붙어도 게시자 표시·신뢰 판정에 쓰지 않는다.
        summary = "요약 문장입니다. " * 20
        sources = [{"name": "UN형 소스", "lane": "economy", "url": self.FEED}]
        items = [("통과 기사", "https://www.reuters.com/a", self.fresh(), summary, "https://elsewhere.example/feed.xml")]
        merged, stats, out = self.run_fetch(items, sources=sources)
        self.assertEqual([(m["source"], m["publisher_domain"]) for m in merged], [("UN형 소스", "www.reuters.com")])

    def test_topic_regex_looks_at_the_title_and_the_feed_categories(self):
        summary = "요약 문장입니다. " * 20
        sources = [{"name": "혼합 피드", "lane": "economy", "url": self.FEED, "topic_regex": r"social media|\bnews\b"}]
        items = [("제목에는 없는 기사", "https://www.reuters.com/a", self.fresh(), summary, "", ("Social Media",)),
                 ("Where people get news", "https://www.reuters.com/b", self.fresh(), summary, ""),
                 ("전혀 다른 기사", "https://www.reuters.com/c", self.fresh(), summary, "", ("Politics",))]
        merged, stats, out = self.run_fetch(items, sources=sources)
        self.assertEqual(sorted(m["title"] for m in merged), ["Where people get news", "제목에는 없는 기사"])
        self.assertEqual(stats["sources"][0]["drops"], {"OFF_TOPIC": 1})

    def test_feed_categories_are_parsed_from_rss_and_atom(self):
        data = (b"<rss><channel><item><title>t</title><link>https://a.test/1</link>"
                b"<category>Social Media</category><category> </category><category>AI</category></item></channel></rss>")
        self.assertEqual(g.parse_feed(data)[0]["categories"], ["Social Media", "AI"])
        atom = (b"<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>t</title><link href='https://a.test/1'/>"
                b"<category term='Science'/></entry></feed>")
        self.assertEqual(g.parse_feed(atom)[0]["categories"], ["Science"])

    def run_short_summary_fetch(self, source_extra):
        sources = [dict({"name": "짧은 요약 소스", "lane": "economy", "url": self.FEED}, **source_extra)]
        items = [("요약이 짧은 기사", "https://www.reuters.com/a", self.fresh(), "짧음", "")]
        stats = {}
        with mock.patch.object(g, "NEWS_SOURCES", sources), \
                mock.patch.object(g.urllib.request, "urlopen", lambda req, timeout=0: FakeResponse(rss(items))), \
                mock.patch.object(g, "_fetch_source_excerpt", return_value="긴 요약 문장입니다. " * 20) as excerpt:
            merged, _ = run_captured(g.fetch_news_items, "economy", stats=stats)
        return merged, stats, excerpt

    def test_no_page_fetch_source_never_reads_the_article_page(self):
        merged, stats, excerpt = self.run_short_summary_fetch({"no_page_fetch": True})
        excerpt.assert_not_called()
        self.assertEqual(merged, [])
        self.assertEqual(stats["sources"][0]["drops"], {"SHORT_SUMMARY": 1})

    def test_other_sources_still_read_the_page_when_the_summary_is_short(self):
        merged, stats, excerpt = self.run_short_summary_fetch({})
        excerpt.assert_called_once()
        self.assertEqual([m["title"] for m in merged], ["요약이 짧은 기사"])

    def test_the_real_pew_config_never_reads_an_article_page_for_a_short_summary(self):
        items = [("Social media use among teens", "https://www.pewresearch.org/internet/2026/10/01/a/", self.fresh(), "짧음", "",
                  ("Social Media",))]
        stats = {}
        with mock.patch.object(g.urllib.request, "urlopen", lambda req, timeout=0: FakeResponse(rss(items))), \
                mock.patch.object(g, "_fetch_source_excerpt", return_value="긴 요약 문장입니다. " * 20) as excerpt:
            merged, out = run_captured(g.fetch_news_items, "culture", stats=stats)
        excerpt.assert_not_called()
        self.assertEqual(merged, [])
        self.assertEqual(stats["sources"][0]["drops"], {"SHORT_SUMMARY": 1})

    def test_notice_and_prompt_rule_travel_with_the_item(self):
        summary = "요약 문장입니다. " * 20
        notice = {"ko": "고지", "en": "notice"}
        sources = [{"name": "고지 소스", "lane": "economy", "url": self.FEED, "notice": notice, "prompt_rule": "규칙",
                    "citation": "{title} {date} {url}"}]
        items = [("통과 기사", "https://www.reuters.com/a", self.fresh(), summary, "")]
        merged, stats, out = self.run_fetch(items, sources=sources)
        self.assertEqual((merged[0]["notice"], merged[0]["prompt_rule"], merged[0]["citation"]),
                         (notice, "규칙", "{title} {date} {url}"))

    def test_a_pending_source_is_not_requested_and_the_log_says_why(self):
        sources = [{"name": "보류 소스", "lane": "economy", "url": self.FEED,
                    "terms": {"status": "pending", "blocker": "알림을 아직 하지 않았다"}}]
        requested = []

        def fake_urlopen(req, timeout=0):
            requested.append(getattr(req, "full_url", req))
            return FakeResponse(rss([]))

        stats = {}
        with mock.patch.object(g, "NEWS_SOURCES", sources), mock.patch.object(g.urllib.request, "urlopen", fake_urlopen):
            merged, out = run_captured(g.fetch_news_items, "economy", stats=stats)
        self.assertEqual((requested, merged), ([], []))
        self.assertIn("소스 보류 소스: 보류 — 알림을 아직 하지 않았다", out)
        self.assertNotIn("sources", stats)  # 시도하지 않았으니 분야 요약의 소스 수에 세지 않는다
        self.assertNotIn("모든 뉴스 소스 수집에 실패", out)

    def test_the_held_un_news_source_is_never_requested(self):
        requested = []

        def fake_urlopen(req, timeout=0):
            requested.append(getattr(req, "full_url", req))
            return FakeResponse(rss([]))

        stats = {}
        with mock.patch.object(g.urllib.request, "urlopen", fake_urlopen):
            merged, out = run_captured(g.fetch_news_items, "society", stats=stats)
        self.assertEqual(merged, [])
        self.assertIn("소스 UN News: 보류", out)
        self.assertEqual([u for u in requested if "un.org" in u], [])
        # 사회·정책 분야는 집행위원회 소식과 통계청(사회)을 읽고, 보류한 UN News 는 소스 수에 세지 않는다
        self.assertEqual([s["name"] for s in stats["sources"]], ["European Commission", "Statistics Canada · society"])

    def test_failed_source_is_recorded_not_hidden(self):
        sources = [{"name": "죽은 소스", "lane": "economy", "url": "https://dead.test/feed"}]
        merged, stats, out = self.run_fetch([], sources=sources)
        self.assertEqual(merged, [])
        self.assertIn("수집 실패", out)
        self.assertIn("::warning::모든 뉴스 소스 수집에 실패", out)
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

    def test_untrusted_publisher_found_only_after_resolution_is_counted(self):
        # <source url> 이 없으면 원문 주소를 해석한 뒤에야 게시자를 알 수 있다(두 번째 UNTRUSTED 관문).
        summary = "요약 문장입니다. " * 20
        items = [("출처 표시 없는 기사", "https://news.example/9", self.fresh(), summary, "")]
        merged, stats, out = self.run_fetch(items, resolve=lambda url: "https://untrusted.example/a")
        self.assertEqual(merged, [])
        self.assertEqual(stats["sources"][0]["drops"], {"UNTRUSTED": 1})

    SOURCES3 = [{"name": f"소스{i}", "lane": "economy", "url": f"https://feed.test/{i}"} for i in range(3)]

    def run_with_deadline(self, deadline, ticks):
        stats, requested = {}, []

        def fake_urlopen(req, timeout=0):
            requested.append(getattr(req, "full_url", req))
            return FakeResponse(rss([]))

        clock = iter(ticks)
        with mock.patch.object(g, "NEWS_SOURCES", self.SOURCES3), \
                mock.patch.object(g.urllib.request, "urlopen", fake_urlopen):
            _, out = run_captured(g.fetch_news_items, "economy", stats=stats,
                                  deadline=deadline, clock=lambda: next(clock))
        return stats, requested, out

    def test_sources_after_the_deadline_are_skipped_and_counted(self):
        stats, requested, out = self.run_with_deadline(deadline=100, ticks=[0, 200, 200])
        self.assertEqual(requested, ["https://feed.test/0"])
        self.assertEqual(stats["time_skipped"], 2)
        self.assertIn("시간 상한으로 소스 2개를 시도하지 않았습니다", out)
        self.assertNotIn("모든 뉴스 소스 수집에 실패", out)  # 시도한 첫 소스는 성공했다

    def test_nothing_attempted_because_of_the_deadline_is_not_a_collection_failure(self):
        stats, requested, out = self.run_with_deadline(deadline=100, ticks=[500, 500, 500])
        self.assertEqual(requested, [])
        self.assertEqual(stats["time_skipped"], 3)
        self.assertNotIn("sources", stats)
        self.assertNotIn("모든 뉴스 소스 수집에 실패", out)

    def test_failure_text_is_folded_so_it_cannot_start_a_workflow_command(self):
        sources = [{"name": "소스", "lane": "economy", "url": "https://dead.test/feed"}]

        def boom(req, timeout=0):
            raise OSError("연결 거부\n::error::가짜 실패 알림")

        with mock.patch.object(g, "NEWS_SOURCES", sources), \
                mock.patch.object(g.urllib.request, "urlopen", boom):
            _, out = run_captured(g.fetch_news_items, "economy")
        self.assertFalse(any(line.startswith("::error::") for line in out.splitlines()))
        self.assertIn("연결 거부 ::error::가짜 실패 알림", out)


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

    def test_deadline_and_clock_are_forwarded_to_the_fetch(self):
        seen = {}

        def fake_fetch(lane=None, stats=None, deadline=None, clock=None):
            seen.update(deadline=deadline, clock=clock)
            return []

        clock = lambda: 1  # noqa: E731
        with mock.patch.object(g, "fetch_news_items", fake_fetch):
            g.pick_topic_candidates([], True, "economy", deadline=5, clock=clock)
        self.assertEqual(seen, {"deadline": 5, "clock": clock})


class LaneReportTest(unittest.TestCase):
    def test_duplicates_join_the_lane_drops_and_counts_sum_over_sources(self):
        stats = {"sources": [{"name": "a", "fetched": 10, "kept": 3, "drops": {"UNTRUSTED": 5, "AGE": 2}},
                             {"name": "b", "fetched": 4, "kept": 1, "drops": {"UNTRUSTED": 3}},
                             {"name": "c", "fetched": 0, "kept": 0, "drops": {}, "error": "URLError"}],
                 "duplicates": 2}
        report = g._lane_report("economy", stats, [])
        self.assertEqual(report["drops"], {"UNTRUSTED": 8, "AGE": 2, "DUPLICATE": 2})
        self.assertEqual((report["sources"], report["failed_sources"], report["fetched"], report["passed"]),
                         (3, 1, 14, 4))
        self.assertEqual(report["candidates"], 0)


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

    def fake_fetch(self, results, errors=False):
        def fake(editorial_lane=None, stats=None, deadline=None, clock=None):
            found = results.get(editorial_lane, [])
            if stats is not None:
                if errors:
                    entry = {"name": f"{editorial_lane}", "fetched": 0, "kept": 0, "drops": {},
                             "error": "URLError"}
                else:
                    entry = {"name": f"{editorial_lane}", "fetched": 4, "kept": len(found),
                             "drops": {} if found else {"UNTRUSTED": 4}}
                stats.setdefault("sources", []).append(entry)
            return found
        return fake

    LINK = "https://www.reuters.com/a"

    def generate(self, results, errors=False, **kwargs):
        report = {}
        with mock.patch.object(g, "fetch_news_items", self.fake_fetch(results, errors)), \
                mock.patch.object(g, "stub_post_data", lambda topic, link=None: long_post(topic, self.LINK)):
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
        self.assertEqual(out.count("[SKIP] code=LANE_EMPTY"), len(g.EDITORIAL_LANES))

    def test_unreachable_sources_are_reported_as_an_outage_not_as_empty_lanes(self):
        value, report, out = self.generate({}, errors=True, allow_auto_topic=False)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], "SOURCES_UNREACHABLE")
        self.assertIn("failed=1", out)

    def test_verified_articles_that_are_all_already_written_are_all_duplicates(self):
        known = "이미 쓴 기사 제목 반도체"
        results = {lane: [candidate(known, self.LINK)] for lane in g.EDITORIAL_LANES}
        with mock.patch.object(g, "existing_titles", return_value=[known]):
            value, report, out = self.generate(results, allow_auto_topic=False)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], "ALL_DUPLICATES")
        self.assertEqual(report["lanes"][0]["drops"], {"DUPLICATE": 1})

    def test_a_budget_stop_is_reported_as_no_candidates(self):
        with mock.patch.object(g, "LANE_SEARCH_BUDGET_SECONDS", -1):
            value, report, out = self.generate({}, allow_auto_topic=False)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], "NO_CANDIDATES")
        self.assertEqual(len(report["lanes"]), 1)
        self.assertIn("::warning::분야 대체 시도를", out)

    def test_fallback_lane_is_what_the_prompt_and_the_history_use(self):
        results = {"technology": [candidate("기술 기사", self.LINK)]}
        seen = {}

        def fake_prompt(item, recent_titles, category_hint="", allow_skip=False, editorial_lane=None):
            seen["prompt_lane"] = editorial_lane
            return "PROMPT"

        class Response:
            text = json.dumps(long_post("기술 기사", self.LINK), ensure_ascii=False)

        with mock.patch.object(g, "STUB_GEMINI", False), \
                mock.patch.object(g, "build_post_prompt", fake_prompt), \
                mock.patch.object(g, "call_gemini_with_fallback", lambda prompt: Response()), \
                mock.patch.object(g, "fetch_news_items", self.fake_fetch(results)), \
                mock.patch.object(g, "write_history", lambda history: seen.update(history=list(history))):
            value, _ = run_captured(g.generate_blog_posts, slot=self.slot, allow_auto_topic=False, report={})
        self.assertIsNotNone(value)
        self.assertNotEqual(self.order[0], "technology")  # 이 슬롯은 정말로 폴백을 거친다
        self.assertEqual(seen["prompt_lane"], "technology")
        self.assertEqual(seen["history"][-1]["lane"], "technology")

    def test_real_stub_body_passes_validation_so_a_keyless_dry_run_completes(self):
        results = {"technology": [candidate("기술 기사", self.LINK)]}
        report = {}
        with mock.patch.object(g, "fetch_news_items", self.fake_fetch(results)):  # stub_post_data 는 실물
            value, _ = run_captured(g.generate_blog_posts, slot=self.slot, allow_auto_topic=False, report=report)
        self.assertIsNotNone(value)
        self.assertEqual(report["outcome"], "PUBLISHED")

    def test_candidates_all_rejected_is_all_rejected_in_schedule_mode(self):
        link = "https://www.reuters.com/a"
        results = {self.order[0]: [candidate("기사", link)]}
        report = {}
        with mock.patch.object(g, "fetch_news_items", self.fake_fetch(results)), \
                mock.patch.object(g, "stub_post_data", lambda topic, link=None: {"skip": True, "reason": "중복"}):
            value, out = run_captured(g.generate_blog_posts, slot=self.slot,
                                      allow_auto_topic=False, report=report)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], "ALL_REJECTED")

    def test_candidates_all_rejected_raises_in_manual_mode(self):
        link = "https://www.reuters.com/a"
        results = {self.order[0]: [candidate("기사", link)]}
        report = {}
        with mock.patch.object(g, "fetch_news_items", self.fake_fetch(results)), \
                mock.patch.object(g, "stub_post_data", lambda topic, link=None: {"skip": True, "reason": "중복"}):
            with self.assertRaises(RuntimeError):
                run_captured(g.generate_blog_posts, slot=None, allow_auto_topic=True, report=report)
        self.assertEqual(report["outcome"], "ALL_REJECTED")

    def test_requested_topic_without_a_matching_verified_article_is_no_match(self):
        results = {lane: [candidate("전혀 상관없는 후보 기사", self.LINK)] for lane in g.EDITORIAL_LANES}
        report = {}
        with mock.patch.object(g, "fetch_news_items", self.fake_fetch(results)):
            value, _ = run_captured(g.generate_blog_posts, topic_override="양자컴퓨터 상용화 일정",
                                    slot=None, report=report)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], "NO_MATCH")

    def run_with_gemini(self, responses, titles, **kwargs):
        cands = [candidate(title, self.LINK) for title in titles]
        gemini = FakeGemini(responses)
        report = {}
        kwargs.setdefault("slot", self.slot)
        kwargs.setdefault("allow_auto_topic", False)
        with mock.patch.object(g, "STUB_GEMINI", False), \
                mock.patch.object(g, "build_post_prompt", gemini.prompt), \
                mock.patch.object(g, "call_gemini_with_fallback", gemini.call), \
                mock.patch.object(g, "fetch_news_items", self.fake_fetch({"technology": cands})):
            value, out = run_captured(g.generate_blog_posts, report=report, **kwargs)
        return value, report, out, gemini

    def dump(self, post):
        return json.dumps(post, ensure_ascii=False)

    def test_a_thin_body_rejects_that_candidate_and_the_next_one_is_published(self):
        first, second = "첫째 기술 기사", "둘째 기술 기사 전혀 다른 소재"
        value, report, out, gemini = self.run_with_gemini(
            {first: self.dump(thin_post(first, self.LINK)), second: self.dump(long_post(second, self.LINK))},
            [first, second])
        self.assertIsNotNone(value)
        self.assertEqual(report["outcome"], "PUBLISHED")
        self.assertEqual(gemini.calls, [first, second])
        self.assertEqual(len(report["gate_rejects"]), 1)
        self.assertIn("최소 편집 분량", report["gate_rejects"][0])
        self.assertIn("본문 검증 탈락", out)
        self.assertIn(second, report["title"])

    def test_every_candidate_failing_the_body_gate_is_all_rejected_not_a_crash(self):
        titles = ["기술 기사 알파", "기술 기사 베타"]
        value, report, out, gemini = self.run_with_gemini(
            {title: self.dump(thin_post(title, self.LINK)) for title in titles}, titles)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], "ALL_REJECTED")
        self.assertEqual(len(report["gate_rejects"]), 2)
        self.assertEqual(gemini.calls, titles)

    def test_the_same_failure_in_a_manual_run_says_why_no_post_was_made(self):
        titles = ["기술 기사 알파"]
        with self.assertRaisesRegex(RuntimeError, "후보가 모두 탈락"):
            self.run_with_gemini({titles[0]: self.dump(thin_post(titles[0], self.LINK))}, titles,
                                 slot=None, allow_auto_topic=True)

    def test_unreadable_gemini_json_rejects_only_that_candidate(self):
        first, second = "첫째 기술 기사", "둘째 기술 기사 전혀 다른 소재"
        value, report, out, gemini = self.run_with_gemini(
            {first: "이건 JSON이 아닙니다", second: self.dump(long_post(second, self.LINK))}, [first, second])
        self.assertIsNotNone(value)
        self.assertEqual(report["outcome"], "PUBLISHED")
        self.assertEqual(len(report["gate_rejects"]), 1)
        self.assertIn("JSON", report["gate_rejects"][0])

    def test_a_gemini_outage_still_fails_the_run_and_stops_trying(self):
        first, second = "첫째 기술 기사", "둘째 기술 기사 전혀 다른 소재"
        with self.assertRaises(RuntimeError):
            self.run_with_gemini({first: RuntimeError("모든 Gemini 모델 호출 실패"),
                                  second: self.dump(long_post(second, self.LINK))}, [first, second])

    def test_published_files_never_contain_the_placeholder_images(self):
        # 본문 사전 검증은 자리표시 이미지 주소로 하고 복사본에만 쓴다. 그 주소가 게시 파일에 새면 안 된다.
        written = []
        results = {"technology": [candidate("기술 기사", self.LINK)]}
        with mock.patch.object(g, "fetch_news_items", self.fake_fetch(results)), \
                mock.patch.object(g, "write_text_atomic", lambda path, content: written.append((str(path), content))):
            value, _ = run_captured(g.generate_blog_posts, slot=self.slot, allow_auto_topic=False, report={})
        self.assertIsNotNone(value)
        posts = [content for path, content in written if path.endswith(".md")]
        self.assertEqual(len(posts), 2)
        for content in posts:
            self.assertNotIn("example.invalid", content)
            self.assertIn("images.unsplash.com", content)

    def test_unreachable_sources_beat_a_budget_stop_in_the_outcome(self):
        with mock.patch.object(g, "LANE_SEARCH_BUDGET_SECONDS", -1):
            value, report, out = self.generate({}, errors=True, allow_auto_topic=False)
        self.assertIsNone(value)
        self.assertTrue(report["budget_exceeded"])
        self.assertEqual(report["outcome"], "SOURCES_UNREACHABLE")

    def test_unreadable_gemini_text_is_folded_in_the_log_and_the_reason_list(self):
        value, report, out, gemini = self.run_with_gemini({"기술 기사": "첫 줄\n::error::가짜"}, ["기술 기사"])
        self.assertIsNone(value)
        self.assertNotIn("\n", report["gate_rejects"][0])
        self.assertFalse(any(line.startswith("::error::") for line in out.splitlines()))

    def test_gemini_skip_reason_is_folded_in_the_log(self):
        skip = json.dumps({"skip": True, "reason": "중복\n::error::가짜"}, ensure_ascii=False)
        value, report, out, gemini = self.run_with_gemini({"기술 기사": skip}, ["기술 기사"])
        self.assertIsNone(value)
        self.assertIn("중복 ::error::가짜", out)
        self.assertFalse(any(line.startswith("::error::") for line in out.splitlines()))

    def test_generated_title_too_similar_to_an_existing_post_is_discarded_and_folded(self):
        existing = "인공지능 반도체 시장 전망과 한국 기업의 대응 전략 분석 보고서"
        post = long_post("기술 기사", self.LINK)
        post["kr_title"] = existing + "\n::error::가짜"
        with mock.patch.object(g, "existing_titles", return_value=[existing]):
            value, report, out, gemini = self.run_with_gemini({"기술 기사": self.dump(post)}, ["기술 기사"])
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], "ALL_REJECTED")
        self.assertIn("생성된 제목이 기존 글과 비슷해 폐기", out)
        self.assertFalse(any(line.startswith("::error::") for line in out.splitlines()))

    def test_feed_titles_and_publisher_names_are_folded_before_printing(self):
        dirty = "기술 기사\n::error::가짜"
        item = candidate(dirty, self.LINK)
        item["source"] = "출처\n##[error]가짜"
        gemini = FakeGemini({dirty: self.dump(long_post("기술 기사", self.LINK))})
        with mock.patch.object(g, "STUB_GEMINI", False), \
                mock.patch.object(g, "build_post_prompt", gemini.prompt), \
                mock.patch.object(g, "call_gemini_with_fallback", gemini.call), \
                mock.patch.object(g, "fetch_news_items", self.fake_fetch({"technology": [item]})):
            value, out = run_captured(g.generate_blog_posts, slot=self.slot, allow_auto_topic=False, report={})
        self.assertIsNotNone(value)
        self.assertFalse(any(line.startswith("::error::") or "##[" in line for line in out.splitlines()))
        self.assertIn("주제 시도: 기술 기사 ::error::가짜", out)
        self.assertIn("- 주제: 기술 기사 ::error::가짜", out)

    def test_report_is_optional(self):
        link = "https://www.reuters.com/a"
        results = {"technology": [candidate("기술 기사", link)]}
        with mock.patch.object(g, "fetch_news_items", self.fake_fetch(results)), \
                mock.patch.object(g, "stub_post_data", lambda topic, link=None: long_post(topic, link)):
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
        # 이 시험들은 직접 게시 경로의 종료 정책을 본다. 진짜 레지스트리의 publish_flow 값(승인 흐름을 켜면 pr)에 기대지 않고, 승인 흐름이었다면
        # 만들 차례인 정기 실행이 부르는 원격 브랜치 확인(git ls-remote, 네트워크)도 시험에서 일어나지 않게 직접 게시로 고정한다.
        patcher = mock.patch.object(g, "draft_flow_on", return_value=False)
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
        self.assertIn("::notice::PIPELINE_PAUSE", out)
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

    def test_pause_accepts_every_value_the_blogger_runner_accepts(self):
        from pipeline import run as blogger_run
        for value in sorted(blogger_run._TRUE) + [" TRUE ", "On"]:
            with self.subTest(value=value), mock.patch.dict(os.environ, {"PIPELINE_PAUSE": value}):
                self.assertTrue(g._pause_on())
        for value in ("", "0", "false", "no", "off"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"PIPELINE_PAUSE": value}):
                self.assertFalse(g._pause_on())

    def test_pause_wins_over_a_missing_api_key(self):
        with mock.patch.object(g, "STUB_GEMINI", True), mock.patch.dict(os.environ, {"PIPELINE_PAUSE": "on"}):
            value, out = run_captured(g.main)
        self.assertIsNone(value)
        self.assertIn("[SKIP] code=PAUSED", out)

    def test_slot_zero_is_reported_as_a_slot_not_a_manual_run(self):
        value, out = run_captured(g.finish_run, None, {"outcome": "ALL_LANES_EMPTY", "lanes": []},
                                  "schedule", at(0, 30), 0)
        self.assertIsInstance(value, SystemExit)
        self.assertIn("::error::0시 슬롯", out)
        self.assertIn("0시 슬롯", self.summary_text())

    def test_source_outage_is_red_even_though_it_is_not_an_empty_lane(self):
        value, out = self.run_main("schedule", at(10, 12),
                                   generate=self.fake_generate("SOURCES_UNREACHABLE"))
        self.assertIsInstance(value, SystemExit)
        self.assertEqual(value.code, 1)
        self.assertIn("::error::9시 슬롯", out)
        self.assertIn("[SKIP] code=SOURCES_UNREACHABLE", out)

    def test_all_duplicates_is_a_warning_because_it_means_a_quiet_news_day(self):
        value, out = self.run_main("schedule", at(10, 12),
                                   generate=self.fake_generate("ALL_DUPLICATES"))
        self.assertIsNone(value)
        self.assertIn("::warning::9시 슬롯", out)
        self.assertNotIn("::error::", out)

    def test_summary_includes_the_gemini_calls_of_this_run(self):
        with mock.patch.dict(g.GEMINI_CALLS, {"attempts": 2, "failed": 1}):
            self.run_main("schedule", at(10, 12), generate=self.fake_generate("ALL_REJECTED"))
        self.assertIn("- Gemini 호출: 2회(실패 1회)", self.summary_text())

    def test_summary_is_safe_to_publish_when_the_title_comes_from_the_model(self):
        hostile = "제목 | 열\n# 가짜 제목\n[클릭](http://evil.example) `x` <img src=x>"
        report = {"outcome": "PUBLISHED", "title": hostile, "source": "A|B\n[x]", "lane_label": "경제·일",
                  "paths": ["_posts/a`b.md"], "lanes": []}
        text = g.render_run_summary("schedule", at(10), 9, report)
        title_line = next(line for line in text.splitlines() if line.startswith("- 제목:"))
        for ch in "|`<>[]":
            self.assertNotIn(ch, title_line.split(":", 1)[1])
        self.assertNotIn("\n# 가짜 제목", text)
        source_line = next(line for line in text.splitlines() if line.startswith("- 편집 축:"))
        self.assertNotIn("|", source_line)
        self.assertNotIn("[", source_line)

    def test_summary_lists_body_gate_rejections_safely(self):
        report = {"outcome": "ALL_REJECTED", "lanes": [],
                  "gate_rejects": ["KR 본문이 최소 편집 분량(1000자)에 미달합니다: 973자 | 표\n[링크](http://evil.example)"]}
        text = g.render_run_summary("schedule", at(10), 9, report)
        line = next(row for row in text.splitlines() if row.startswith("- 후보 탈락"))
        self.assertIn("1건", line)
        self.assertIn("973자", line)
        for ch in "|[]":
            self.assertNotIn(ch, line)

    def test_summary_explains_the_drop_codes_it_uses(self):
        report = {"outcome": "ALL_LANES_EMPTY",
                  "lanes": [{"lane": "economy", "label": "경제·일", "sources": 2, "failed_sources": 0,
                             "fetched": 70, "passed": 0, "candidates": 0,
                             "drops": {"UNTRUSTED": 60, "AGE": 10}}]}
        text = g.render_run_summary("schedule", at(10), 9, report)
        self.assertIn(f"UNTRUSTED={g.DROP_LABELS['UNTRUSTED']}", text)
        self.assertIn(f"AGE={g.DROP_LABELS['AGE']}", text)
        self.assertNotIn("NOT_TECH=", text)  # 쓰이지 않은 코드는 범례에 넣지 않는다

    # --- FIX_IMAGES 계약: 기존 글 이미지 교체는 chance-fix-images.yml(FIX_IMAGES=1)만 부른다 ---------------------------------
    # 분리 전에는 chanceblog.yml 의 입력이었다. 두 워크플로가 이 스위치로 갈라지므로 generator.py 의 현재 동작을 고정한다.

    def test_fix_images_switch_runs_only_the_image_repair_path(self):
        """FIX_IMAGES 가 켜지면 main() 은 기존 글의 이미지 교체만 한다. 새 글 생성(run_main 의 기본 generate 는 호출되면
        AssertionError)도 정기 슬롯 판정(slot_state)도 하지 않는다. 이벤트가 schedule 이어도 교체 스위치가 먼저다."""
        for event in ("workflow_dispatch", "schedule"):
            with self.subTest(event=event):
                self.summary.write_text("", encoding="utf-8")
                calls = []

                def fake_fix(keyword=None):
                    calls.append(keyword)
                    return "이미지 점검: 완료: 문제 2건 / 교체 2건 / 건너뜀 0건 (DRY_RUN: 실제 변경 없음)"

                def no_slot_judgement(*args, **kwargs):
                    raise AssertionError("이미지 교체 실행은 슬롯 판정을 하지 않습니다")

                with mock.patch.object(g, "FIX_IMAGES", True), mock.patch.object(g, "fix_images", fake_fix), \
                        mock.patch.object(g, "slot_state", no_slot_judgement):
                    value, out = self.run_main(event, at(10, 12))
                self.assertIsNone(value)
                self.assertEqual(calls, [None])  # 한 번만, 검색어 없이
                text = self.summary_text()
                self.assertIn("### Chance_Blog 실행 요약", text)
                self.assertIn("- 이미지 점검: 완료: 문제 2건 / 교체 2건", text)
                self.assertNotIn("[SKIP]", out)  # 슬롯 건너뜀 줄이 없다

    def test_without_the_switch_main_never_repairs_images(self):
        """FIX_IMAGES 가 꺼져 있으면(chanceblog.yml 에는 이제 이 스위치가 없다) 정기·수동 어느 실행도 기존 글의 이미지를 건드리지
        않고 글 작성 경로(슬롯 판정·생성)만 탄다."""
        def boom_fix(*args, **kwargs):
            raise AssertionError("FIX_IMAGES 가 꺼져 있는데 이미지 교체를 시도했습니다")

        made = []
        base = self.fake_generate("PUBLISHED", result=("a", "b"), lanes=1)

        def generate(slot=None, allow_auto_topic=True, report=None, **kwargs):
            made.append((slot, allow_auto_topic))
            return base(slot=slot, allow_auto_topic=allow_auto_topic, report=report, **kwargs)

        with mock.patch.object(g, "fix_images", boom_fix):
            value, out = self.run_main("schedule", at(8, 54))  # 첫 슬롯 전: 정상 건너뜀
            self.assertIsNone(value)
            self.assertIn("[SKIP] code=OUT_OF_WINDOW", out)
            self.assertEqual(made, [])
            value, _ = self.run_main("schedule", at(10, 12), generate=generate)  # 9시 슬롯: 글 작성
            self.assertIsNone(value)
            self.assertEqual(made, [(9, False)])
            value, _ = self.run_main("workflow_dispatch", at(10, 12), generate=generate)  # 수동: 글 작성
            self.assertIsNone(value)
            self.assertEqual(made, [(9, False), (None, True)])

    def test_fix_images_flag_comes_only_from_the_environment_and_is_off_when_unset(self):
        """chance-fix-images.yml 만 FIX_IMAGES: '1' 을 넘기고 chanceblog.yml 은 아무것도 넘기지 않는다. 환경변수가 없으면 꺼져 있어야
        정기 실행이 이미지를 건드리지 않는다. 모듈이 읽히는 순간의 값을 보려고 새 프로세스에서 import 한다."""
        base = {k: v for k, v in os.environ.items() if k != "FIX_IMAGES"}
        cases = [(None, "False"), ("", "False"), ("0", "False"), ("false", "False"), ("no", "False"),
                 ("1", "True"), ("true", "True"), ("yes", "True"), (" TRUE ", "True")]
        for value, expected in cases:
            with self.subTest(value=value):
                env = dict(base)
                if value is not None:
                    env["FIX_IMAGES"] = value
                proc = subprocess.run([sys.executable, "-c", "import generator; print(generator.FIX_IMAGES)"],
                                      cwd=str(_bootstrap.ROOT), env=env, capture_output=True, text=True, timeout=60)
                self.assertEqual(proc.stdout.strip(), expected, proc.stderr)


class GeminiCallCountTest(unittest.TestCase):
    """무료 한도를 나눠 쓰려면 먼저 몇 번 부르는지 알아야 한다: 모델 호출 시도와 실패를 센다."""

    def setUp(self):
        patcher = mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0})
        patcher.start()
        self.addCleanup(patcher.stop)

    def client(self, outcomes):
        models = mock.Mock()
        models.generate_content.side_effect = outcomes
        return mock.Mock(models=models)

    def test_failed_models_and_the_final_success_are_all_counted(self):
        ok = mock.Mock(text="응답")
        with mock.patch.object(g, "MODEL_CANDIDATES", ["a", "b", "c"]), \
                mock.patch.object(g, "get_client", return_value=self.client([RuntimeError("503"), mock.Mock(text=""), ok])):
            response, _ = run_captured(g.call_gemini_with_fallback, "프롬프트")
        self.assertIs(response, ok)
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 3, "failed": 2})

    def test_model_failure_text_is_folded_in_the_log(self):
        ok = mock.Mock(text="응답")
        client = self.client([RuntimeError("503\n::error::가짜 알림"), ok])
        with mock.patch.object(g, "MODEL_CANDIDATES", ["a", "b"]), mock.patch.object(g, "get_client", return_value=client):
            response, out = run_captured(g.call_gemini_with_fallback, "프롬프트")
        self.assertIs(response, ok)
        self.assertFalse(any(line.startswith("::error::") for line in out.splitlines()))
        self.assertIn("503 ::error::가짜 알림", out)

    def test_summary_reports_the_calls(self):
        report = {"outcome": "ALL_REJECTED", "lanes": [], "gemini_calls": {"attempts": 4, "failed": 1}}
        text = g.render_run_summary("schedule", at(10), 9, report)
        self.assertIn("- Gemini 호출: 4회(실패 1회)", text)

    def test_summary_says_zero_when_gemini_was_not_called(self):
        """예전에는 호출이 없으면 줄을 생략했다. Blogger·이슈 수정은 0회를 적고, 줄이 없으면 '호출 안 함'과 '이 기능이 없는 옛 요약'을
        구분할 수 없어(독립 검증 F-09) Chance 도 0회를 적는다. 호출 수 항목 자체가 없는 보고서에는 줄을 만들지 않는다."""
        report = {"outcome": "ALL_LANES_EMPTY", "lanes": [], "gemini_calls": {"attempts": 0, "failed": 0}}
        self.assertIn("- Gemini 호출: 0회(실패 0회)", g.render_run_summary("schedule", at(10), 9, report))
        self.assertNotIn("Gemini 호출", g.render_run_summary("schedule", at(10), 9, {"outcome": "ALL_LANES_EMPTY", "lanes": []}))


class SanitizeTest(unittest.TestCase):
    def test_one_line_folds_newlines_and_runs_of_whitespace(self):
        self.assertEqual(g._one_line("a\n\n  b\r\nc"), "a b c")

    def test_one_line_never_starts_with_a_workflow_command(self):
        # 러너는 줄 앞 공백을 지우고 '::' 를 찾으므로 공백으로 막은 것은 막은 것이 아니다
        self.assertFalse(g._one_line("::error::x").lstrip().startswith("::"))
        self.assertFalse(g._one_line("\n::error::x").lstrip().startswith("::"))
        self.assertFalse(g._one_line("   ::error::x").lstrip().startswith("::"))

    def test_one_line_neutralises_group_markers(self):
        self.assertNotIn("##[", g._one_line("##[error]x"))

    def test_one_line_limits_the_length(self):
        self.assertEqual(len(g._one_line("a" * 1000, 50)), 50)

    def test_md_cell_escapes_table_and_link_syntax(self):
        cell = g._md_cell("제목 | 열\n[링크](http://evil.example) `코드` <b>x</b>")
        for ch in "|\n`<>[]":
            self.assertNotIn(ch, cell)

    def test_image_query_failure_text_is_folded(self):
        with mock.patch.object(g, "STUB_GEMINI", False), \
                mock.patch.object(g, "call_gemini_with_fallback",
                                  side_effect=RuntimeError("실패\n::error::가짜")):
            value, out = run_captured(g.make_image_queries, "제목", [], "카테고리")
        self.assertEqual(value, ["technology", "computer hardware"])
        self.assertFalse(any(line.startswith("::error::") for line in out.splitlines()))
        self.assertIn("실패 ::error::가짜", out)

    def test_unsplash_failure_text_is_folded(self):
        def boom(req, timeout=0):
            raise OSError("연결 거부\n::error::가짜")

        with mock.patch.object(g, "STUB_UNSPLASH", False), mock.patch.object(g, "UNSPLASH_KEY", "k"), \
                mock.patch.object(g.urllib.request, "urlopen", boom):
            value, out = run_captured(g.search_unsplash, "query")
        self.assertEqual(value, [])
        self.assertFalse(any(line.startswith("::error::") for line in out.splitlines()))
        self.assertIn("연결 거부 ::error::가짜", out)


class StubPostTest(unittest.TestCase):
    LINK = "https://www.reuters.com/a"

    def test_stub_passes_the_same_validation_as_a_real_post(self):
        data = g.stub_post_data("주제", self.LINK)
        out = g.validate_post_data(data, "https://img.test/a.jpg", "https://img.test/b.jpg",
                                   verified_source_url=self.LINK)
        self.assertIn(self.LINK, out["kr_content"])
        self.assertIn(self.LINK, out["en_content"])

    def test_stub_without_a_link_keeps_the_old_call_form(self):
        data = g.stub_post_data("주제")
        self.assertNotIn("http", data["kr_content"])


class LayoutGuaranteeTest(unittest.TestCase):
    """모델이 front matter 에서 layout 줄을 빼먹은 글(2026-10-26 18시 슬롯 글이 그랬다)도 `layout: post` 로 나간다."""
    LINK = "https://www.reuters.com/a"

    def data_with_front(self, front):
        """스텁 글의 본문에 주어진 front matter 를 붙인다(분량·원문 링크 검증은 스텁 본문이 통과시킨다)."""
        data = g.stub_post_data("주제", self.LINK)
        for prefix in ("kr", "en"):
            body = data[f"{prefix}_content"].split("\n---\n", 1)[1]
            data[f"{prefix}_content"] = f"---\n{front}\n---\n{body}"
        return data

    def validate(self, data):
        return g.validate_post_data(data, "https://img.test/a.jpg", "https://img.test/b.jpg", verified_source_url=self.LINK)

    def test_a_front_matter_without_layout_gets_layout_post_first(self):
        out = self.validate(self.data_with_front('title: "t"\ncategory: "c"\ntags: []'))
        for key in ("kr_content", "en_content"):
            with self.subTest(key=key):
                self.assertTrue(out[key].startswith("---\nlayout: post\ntitle: "), out[key][:60])
                self.assertEqual(len(re.findall(r"(?m)^layout\s*:", out[key])), 1)

    def test_an_existing_layout_is_left_alone(self):
        for layout in ("layout: post", "layout: default", 'layout: "post"'):
            with self.subTest(layout=layout):
                out = self.validate(self.data_with_front(f'{layout}\ntitle: "t"\ncategory: "c"\ntags: []'))
                self.assertTrue(out["kr_content"].startswith(f"---\n{layout}\ntitle: "), out["kr_content"][:60])
                self.assertEqual(len(re.findall(r"(?m)^layout\s*:", out["kr_content"])), 1)

    def test_a_layout_word_inside_another_value_or_key_does_not_count_as_a_layout_line(self):
        for front in ('title: "layout: post 이야기"\ncategory: "c"\ntags: []',  # 값 안의 layout
                      'layouts: "x"\ntitle: "t"\ncategory: "c"\ntags: []',  # layout 으로 시작하는 다른 키
                      'my_layout: post\ntitle: "t"\ncategory: "c"\ntags: []'):  # 이름 끝이 layout 인 다른 키
            with self.subTest(front=front):
                out = self.validate(self.data_with_front(front))
                self.assertTrue(out["kr_content"].startswith("---\nlayout: post\n"), out["kr_content"][:60])
                self.assertEqual(len(re.findall(r"(?m)^layout\s*:", out["kr_content"])), 1)

    def test_a_layout_line_that_is_not_the_first_front_matter_line_still_counts(self):
        out = self.validate(self.data_with_front('title: "t"\ncategory: "c"\ntags: []\nlayout: post'))
        self.assertEqual(len(re.findall(r"(?m)^layout\s*:", out["kr_content"])), 1)
        self.assertTrue(out["kr_content"].startswith('---\ntitle: "t"\n'), out["kr_content"][:40])

    def test_only_the_front_matter_is_searched_for_a_layout_line(self):
        data = self.data_with_front('title: "t"\ncategory: "c"\ntags: []')
        for prefix in ("kr", "en"):
            data[f"{prefix}_content"] += "\nlayout: x\n"  # 본문에 layout: 으로 시작하는 줄이 있어도 front matter 의 layout 은 없는 글이다
        out = self.validate(data)
        self.assertTrue(out["kr_content"].startswith("---\nlayout: post\ntitle: "), out["kr_content"][:60])

    def test_whitespace_after_the_opening_fence_leaves_no_blank_or_tab_only_line(self):
        for opening in ("--- ", "---  ", "---\t"):
            with self.subTest(opening=repr(opening)):
                data = g.stub_post_data("주제", self.LINK)
                for prefix in ("kr", "en"):
                    body = data[f"{prefix}_content"].split("\n---\n", 1)[1]
                    data[f"{prefix}_content"] = f'{opening}\ntitle: "t"\ncategory: "c"\ntags: []\n---\n{body}'
                out = self.validate(data)
                self.assertEqual(out["kr_content"].split("\n")[:3], ["---", "layout: post", 'title: "t"'])

    def test_blank_lines_before_the_opening_fence_are_dropped(self):
        data = self.data_with_front('title: "t"\ncategory: "c"\ntags: []')
        for prefix in ("kr", "en"):
            data[f"{prefix}_content"] = "\n\n  " + data[f"{prefix}_content"]
        out = self.validate(data)
        self.assertTrue(out["kr_content"].startswith('---\nlayout: post\ntitle: "t"'), repr(out["kr_content"][:50]))

    def test_an_empty_front_matter_gets_just_the_layout_line_without_a_blank_line(self):
        data = g.stub_post_data("주제", self.LINK)
        for prefix in ("kr", "en"):
            body = data[f"{prefix}_content"].split("\n---\n", 1)[1]
            data[f"{prefix}_content"] = "---\n---\n" + body
        out = self.validate(data)
        self.assertEqual(out["kr_content"].split("\n")[:3], ["---", "layout: post", "lang: ko"])

    def test_a_front_matter_with_windows_line_endings_still_gets_a_clean_layout_line(self):
        data = g.stub_post_data("주제", self.LINK)
        for prefix in ("kr", "en"):
            body = data[f"{prefix}_content"].split("\n---\n", 1)[1]
            data[f"{prefix}_content"] = '---\r\ntitle: "t"\r\ncategory: "c"\r\ntags: []\r\n---\r\n' + body
        out = self.validate(data)
        self.assertTrue(out["kr_content"].startswith("---\nlayout: post\ntitle: "), repr(out["kr_content"][:60]))

    def test_content_without_any_front_matter_still_gets_one_with_layout(self):
        data = g.stub_post_data("주제", self.LINK)
        for prefix in ("kr", "en"):
            data[f"{prefix}_content"] = data[f"{prefix}_content"].split("\n---\n", 1)[1].lstrip("\n")
        out = self.validate(data)
        self.assertTrue(out["kr_content"].startswith("---\nlayout: post\ntitle: "), out["kr_content"][:60])
        self.assertTrue(out["en_content"].startswith("---\nlayout: post\ntitle: "), out["en_content"][:60])


class IntEnvTest(unittest.TestCase):
    def test_reads_an_integer_and_ignores_garbage(self):
        for raw, expected in (("42", 42), ("0", 0), ("abc", 7), ("", 7), ("  9 ", 9)):
            with self.subTest(raw=raw), mock.patch.dict(os.environ, {"X_TEST_INT": raw}):
                self.assertEqual(g._int_env("X_TEST_INT", 7), expected)


class SourceNoticeTest(unittest.TestCase):
    """소스 약관이 요구하는 고지문과 글 작성 지침 한 줄이 글과 프롬프트에 정확히 들어가는지."""
    LINK = "https://www.nasa.gov/a"
    NOTICE = {"ko": "고지문 한국어입니다.", "en": "English notice sentence."}

    def source(self, notice="기본"):
        return {"title": "원문 제목", "source": "NASA", "link": self.LINK, "publisher_domain": "www.nasa.gov",
                "notice": self.NOTICE if notice == "기본" else notice}

    @staticmethod
    def post(body):
        return f"---\nlayout: post\ntitle: \"t\"\n---\n\n{body}\n"

    def test_korean_post_gets_the_korean_notice_at_the_very_end(self):
        body = f"본문입니다. [원문]({self.LINK})\n\n## 출처\n- [NASA]({self.LINK})"
        content = g.add_discovery_metadata(self.post(body), self.source())
        self.assertTrue(content.endswith("\n\n*고지문 한국어입니다.*\n"), content[-80:])
        self.assertNotIn("English notice", content)

    def test_english_post_gets_the_english_notice(self):
        body = f"Body text. [source]({self.LINK})\n\n## Sources\n- [NASA]({self.LINK})"
        content = g.add_discovery_metadata(self.post(body), self.source())
        self.assertTrue(content.endswith("\n\n*English notice sentence.*\n"), content[-80:])
        self.assertNotIn("한국어", content)

    def test_the_language_comes_from_the_front_matter_before_hangul_detection(self):
        english = ("---\nlayout: post\ntitle: \"t\"\nlang: en\n---\n\n"
                   f"Hallyu (한류) keeps spreading. [source]({self.LINK})\n")
        self.assertTrue(g.add_discovery_metadata(english, self.source()).endswith("*English notice sentence.*\n"))
        korean = ("---\nlayout: post\ntitle: \"t\"\nlang: ko\n---\n\n"
                  f"plain ascii body only. [source]({self.LINK})\n")
        self.assertTrue(g.add_discovery_metadata(korean, self.source()).endswith("*고지문 한국어입니다.*\n"))

    def test_an_english_post_with_a_korean_word_still_gets_the_english_sources_heading(self):
        english = "---\nlayout: post\ntitle: \"t\"\nlang: en\n---\n\nHallyu (한류) keeps spreading with no link in the story.\n"
        content = g.add_discovery_metadata(english, self.source())
        self.assertIn("\n## Sources\n", content)
        self.assertNotIn("## 출처", content)

    def test_the_notice_is_added_only_once(self):
        once = g.add_discovery_metadata(self.post(f"본문입니다. [원문]({self.LINK})"), self.source())
        twice = g.add_discovery_metadata(once, self.source())
        self.assertEqual(once, twice)
        self.assertEqual(twice.count("고지문 한국어입니다."), 1)

    def test_a_source_without_a_notice_changes_nothing(self):
        plain = self.post(f"본문입니다. [원문]({self.LINK})")
        for notice in (None, "문자열은 무시", {"ko": ""}):
            with self.subTest(notice=notice):
                content = g.add_discovery_metadata(plain, self.source(notice))
                self.assertNotIn("고지", content)
                self.assertFalse(content.rstrip().endswith("*"))

    def test_a_citation_line_comes_before_the_notice_and_uses_the_items_title_date_and_link(self):
        item = self.source()
        item["citation"] = "“{title}.” Pew Research Center, Washington, D.C. ({date}) <{url}>"
        item["title"] = "1 in 5 Americans Regularly Get News on TikTok."  # 제목 끝의 마침표가 겹치지 않아야 한다
        item["published"] = datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc)
        story = "충분히 긴 첫 문단입니다. " * 8 + f"[원문]({self.LINK})"  # 실제 글처럼 60자 넘는 문단이 있어야 description 이 인용 줄이 아니라 본문에서 나온다
        content = g.add_discovery_metadata(self.post(story), item)
        citation = f"“1 in 5 Americans Regularly Get News on TikTok.” Pew Research Center, Washington, D.C. (October 24, 2026) <{self.LINK}>"
        self.assertIn(citation, content)
        self.assertLess(content.index(citation), content.index("*고지문 한국어입니다.*"))
        self.assertTrue(content.endswith("*고지문 한국어입니다.*\n"))
        self.assertEqual(g.add_discovery_metadata(content, item), content)  # 다시 붙이지 않는다

    def test_no_citation_line_without_a_template_a_date_or_a_title(self):
        template = "“{title}.” ({date}) <{url}>"
        base = dict(self.source(None), citation=template, published=datetime(2026, 10, 24, tzinfo=timezone.utc))
        for label, item in (("틀 없음", dict(base, citation=None)),
                            ("게시일 없음", dict(base, published=None)),
                            ("제목 없음", dict(base, title=""))):
            with self.subTest(label):
                content = g.add_discovery_metadata(self.post(f"본문입니다. [원문]({self.LINK})"), item)
                self.assertNotIn(f"<{self.LINK}>", content)
                self.assertNotIn("(October 24, 2026)", content)

    def test_a_title_ending_with_a_question_or_exclamation_mark_gets_no_extra_period(self):
        sample = {"link": "https://x.test/a", "published": datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)}
        template = "“{title}.” Source, {date} <{url}>."
        self.assertTrue(g._citation_line(template, dict(sample, title="How can Europe counter hybrid warfare?")).startswith("“How can Europe counter hybrid warfare?” Source,"))
        self.assertTrue(g._citation_line(template, dict(sample, title="Apply now!")).startswith("“Apply now!” Source,"))
        self.assertTrue(g._citation_line(template, dict(sample, title="A plain title.")).startswith("“A plain title.” Source,"))   # 마침표는 하나만
        self.assertTrue(g._citation_line(template, dict(sample, title="A plain title")).startswith("“A plain title.” Source,"))
        self.assertTrue(g._citation_line(template, dict(sample, title="What now?")).endswith("<https://x.test/a>."))             # 끝의 틀 마침표는 그대로

    def test_a_citation_without_a_notice_is_still_added(self):
        item = dict(self.source(None), citation="{title} ({date}) {url}", published=datetime(2026, 1, 5, tzinfo=timezone.utc))
        content = g.add_discovery_metadata(self.post(f"본문입니다. [원문]({self.LINK})"), item)
        self.assertTrue(content.endswith(f"원문 제목 (January 5, 2026) {self.LINK}\n"), content[-120:])

    def test_prompt_rule_is_in_the_prompt_only_for_the_source_that_has_it(self):
        with_rule = g.build_post_prompt(dict(candidate(), prompt_rule="규칙 한 줄 XYZ"), [], editorial_lane="science")
        self.assertIn("\n- 규칙 한 줄 XYZ\n", with_rule)
        self.assertNotIn("XYZ", g.build_post_prompt(candidate(), [], editorial_lane="science"))


class SourceRuleSamplesTest(unittest.TestCase):
    """2026-10-26 에 실제 피드에서 받은 제목·주소·분류 태그로 소스별 제외·주제 규칙을 고정한다(피드가 바뀌면 규칙도 다시 본다)."""

    def kept(self, name, title, categories=(), link=""):
        src = next(s for s in g.NEWS_SOURCES if s["name"] == name)
        if g._rule_excludes(src, title, {"link": link, "categories": list(categories)}):  # 엔진과 같은 함수
            return False
        topic = src.get("topic_regex")
        return not topic or bool(re.search(topic, " ".join([title, *categories]), re.I))

    def test_nasa_skips_apod_advisories_captions_and_center_pages_only(self):
        skipped = (
            ("APOD: 2026 October 25 – Dark Matter in a Simulated Universe", "https://science.nasa.gov/image-article/apod-2026-10-25/"),
            ("NASA Invites Media to 2026 von Braun Space Exploration Symposium", "https://www.nasa.gov/news-release/nasa-invites-media/"),
            ("NASA to Host News Conference Previewing US Spacewalks 100, 101", "https://www.nasa.gov/news-release/nasa-to-host-news-conference/"),
            ("NASA Astronauts to Answer Questions from Florida Students", "https://www.nasa.gov/learning-resources/nasa-astronauts-to-answer/"),
            ("NASA to Conduct NCAA Flyover, Engage Fans at University of Alabama", "https://www.nasa.gov/news-release/nasa-to-conduct-ncaa-flyover/"),
            ("NASA to Conduct Low-Altitude Flights Over Texas Farmland", "https://www.nasa.gov/general/nasa-to-conduct-low-altitude-flights/"),
            ("Spiral’s Edge", "https://www.nasa.gov/image-article/spirals-edge/"),
            ("Martian Dawn", "https://www.nasa.gov/image-article/martian-dawn/"),
            ("Software", "https://www.nasa.gov/centers-and-facilities/glenn/acoustics-software/"),
            ("Instrumentation", "https://www.nasa.gov/centers-and-facilities/glenn/acoustics-instrumentation/"),
            ("NASA Sets Coverage for Crew-12 Launch", "https://www.nasa.gov/news-release/nasa-sets-coverage-crew-12/"),
            ("Media Accreditation Open for Artemis II Launch", "https://www.nasa.gov/news-release/media-accreditation-artemis-ii/"),
            ("APOD: 2026 October 26 – Aurora", "https://apod.nasa.gov/apod/ap261026.html"),
        )
        for title, link in skipped:
            self.assertFalse(self.kept("NASA", title, link=link), title)
        kept = (
            ("NASA, Partners Accelerate Lander Development for 2028 Moon Missions", "https://www.nasa.gov/news-release/nasa-partners-accelerate-lander/"),
            ("NASA’s Swift Mission Ends, Leaves Behind Scientific Bonanza", "https://science.nasa.gov/missions/swift/ends/"),
            ("NASA’s Artemis III Mission to Test Future Moon Lander Operations", "https://www.nasa.gov/news-release/artemis-iii/"),
            ("El Niño Then and Now", "https://science.nasa.gov/earth/el-nino-then-and-now/"),
            ("RS-25 Engine Tests at NASA Stennis", "https://www.nasa.gov/centers/stennis/rs-25/"),
            ("Artemis II", "https://www.nasa.gov/news-release/artemis-ii/"),  # 짧은 제목이라는 이유만으로는 빼지 않는다
            # 센터 소식 기사는 /centers-and-facilities/ 경로에 있어도 살린다(2026-10-26 표본에서 실제 기사 4건이 빠지던 것)
            ("NASA, Virginia Launch Power Partnership for Energy Security", "https://www.nasa.gov/centers-and-facilities/langley/nasa-power-energy-partnership/"),
            ("NASA JPL Looks to Next 90 Years of Innovation, Exploration", "https://www.nasa.gov/centers-and-facilities/jpl/nasa-jpl-looks-to-next-90-years-of-innovation-exploration/"),
            ("NASA’s SR-1 Freedom Advances with Progress on Nuclear Power Module", "https://www.nasa.gov/centers-and-facilities/glenn/sr-1-freedom-advances-with-progress-on-nuclear-power-module/"),
            ("NASA Improves Shock, Vibration Analysis", "https://www.nasa.gov/centers-and-facilities/kennedy/nasa-improves-shock-vibration-analysis/"),
        )
        for title, link in kept:
            self.assertTrue(self.kept("NASA", title, link=link), title)

    def test_un_news_skips_the_roundups_only(self):
        self.assertFalse(self.kept("UN News", "World News in Brief: Iran nuclear inspections, deadly church attack in Jordan"))
        for title in ("UN marks 81 years of global cooperation",
                      "Soil mapping aims to boost agricultural production in Kenya",
                      "Mothers get nearly eight times more paid leave than fathers – and women pay the price"):
            self.assertTrue(self.kept("UN News", title), title)

    def test_federal_reserve_skips_enforcement_and_application_orders(self):
        for title in ("Federal Reserve Board announces termination of enforcement actions with Gardner Bancshares",
                      "Federal Reserve Board announces enforcement action against American Express Company",
                      "Federal Reserve Board announces approval of application by Isabella Bank Corporation",
                      "Federal Reserve Board announces approval of related applications by Columbia Bank MHC and Columbia Financial, Inc.",
                      "Federal Reserve Board does not object to the conversion of United Texas Bank to a state charter",
                      "Federal Reserve Board has made the joint findings with the OCC on the proposed merger"):
            self.assertFalse(self.kept("Federal Reserve", title), title)
        for title in ("Federal Reserve issues FOMC statement",
                      "Minutes of the Federal Open Market Committee, September 15-16, 2026",
                      "Federal Reserve Board releases results of the 2025 Survey of Consumer Finances",
                      "Agencies seek comment on proposed third-party risk management guidance"):
            self.assertTrue(self.kept("Federal Reserve", title), title)

    def test_pew_keeps_media_and_online_topics_and_drops_politics_quizzes_digests_and_method_pages(self):
        pew = "https://www.pewresearch.org"
        cases = [
            ("Growing Share of Americans Say Social Media Is an Important News Source for Them", ("Social Media",), f"{pew}/short-reads/2026/10/23/a/", True),
            ("1 in 5 Americans Regularly Get News on TikTok", ("Social Media", "TikTok"), f"{pew}/short-reads/2026/10/19/b/", True),
            ("Americans’ Use of Social Media in 2026", ("Social Media",), f"{pew}/internet/fact-sheet/social-media/", True),
            ("Online Communities Rarely Focus on Politics, and Many Say It Should Stay That Way", ("Friendships", "Online Services"), f"{pew}/short-reads/2026/10/20/c/", True),
            ("News Platform Fact Sheet", ("News Platforms & Sources",), f"{pew}/journalism/fact-sheet/news-platform/", True),
            ("Where Americans are getting their news in the digital age", (), f"{pew}/newsletter/the-briefing/the-briefing-10-22/", False),
            ("Turkish police raid offices of major TV news channel", (), f"{pew}/newsletter/the-briefing/the-briefing-10-15/", False),
            ("Can AI Stand In for Human Survey-Takers? Not Really", ("Artificial Intelligence", "Methodological Research"), f"{pew}/data-labs/2026/09/30/d/", False),
            ("🔎 What’s your civic personality? Take our quiz", (), f"{pew}/quiz/civic-personality/", False),
            ("Quiz: What Is Your Civic Personality?", ("News Habits & Media",), f"{pew}/quiz/civic-personality/", False),
            ("Acknowledgments", ("Election 2026",), f"{pew}/politics/2026/e/acknowledgments/", False),
            ("Methodology", ("Election 2026",), f"{pew}/politics/2026/e/methodology/", False),
            ("Additional charts", (), f"{pew}/politics/2026/e/charts/", False),
            ("Few Americans Say They Are Asking AI Chatbots for 2026 Election Information", ("Artificial Intelligence", "Election 2026"), f"{pew}/short-reads/2026/f/", False),
            ("Americans’ mood before the election", (), f"{pew}/politics/2026/g/", False),
            ("How U.S. Voters View Mail and Absentee Balloting", ("Election 2026",), f"{pew}/politics/2026/h/", False),
            ("Pace of Trump’s Judicial Appointments Has Slowed in His Second Term", ("Criminal Justice", "Supreme Court"), f"{pew}/politics/2026/i/", False),
            ("Women, Work and Caregiving Through the Arc of Family Life", ("Family Caregiving", "Uncategorized"), f"{pew}/social-trends/2026/j/", False),
            # 제목에 선거·정당 낱말이 없어도 분류 태그(exclude_tags)가 정치 글을 걸러야 한다(2026-10-26 실제 제목)
            ("So Far, the 119th Congress Is Among the Least Productive of the Past 40 Years", ("Congress", "Politics & Policy"), f"{pew}/politics/2026/k/", False),
            ("Iran Conflict Remains Deeply Unpopular as Many Americans Expect It To Go On for Months", ("Donald Trump", "War & International Conflict"), f"{pew}/politics/2026/l/", False),
            ("Cost Concerns Dominate as Public’s Economic Ratings Turn More Negative", ("Donald Trump", "Economic Conditions"), f"{pew}/politics/2026/m/", False),
            # 언론·방송 주제어
            ("How Americans View Local Television News", ("Television",), f"{pew}/journalism/2026/n/", True),
            ("Journalists and the Public: A New Survey", ("Journalists",), f"{pew}/journalism/2026/o/", True),
        ]
        for title, categories, link, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(self.kept("Pew Research Center", title, categories, link), expected)

    def test_each_pew_exclude_tag_alone_decides_the_outcome(self):
        # 제목이 주제어 검사(topic_regex)를 통과하고 제목 제외 규칙에 안 걸리게 해 두면 분류 태그(exclude_tags)만 결과를 가른다.
        link = "https://www.pewresearch.org/short-reads/2026/10/20/x/"
        title = "How Americans Follow the News Online"
        self.assertTrue(self.kept("Pew Research Center", title, (), link))
        self.assertTrue(self.kept("Pew Research Center", title, ("Social Media",), link))
        for tag in ("Methodological Research", "Elections", "Voters", "Voting", "Political Issues", "Donald Trump", "Politics & Policy"):
            with self.subTest(tag=tag):
                self.assertFalse(self.kept("Pew Research Center", title, (tag,), link))
        # 앵커(^…$)가 있는 세 태그는 정확히 그 태그일 때만 거른다 — 더 긴 태그(미디어 주제가 들어올 수 있는)는 살린다
        for tag in ("Political Issues and Media", "Donald Trump Jr.", "Politics & Policy Journalism",
                    "Global Political Issues", "Not Donald Trump", "Local Politics & Policy"):
            with self.subTest(longer_tag=tag):
                self.assertTrue(self.kept("Pew Research Center", title, (tag,), link))

    def test_pew_citation_line_matches_the_format_pews_terms_require(self):
        pew = next(s for s in g.NEWS_SOURCES if s["name"] == "Pew Research Center")
        sample = {"title": "1 in 5 Americans Regularly Get News on TikTok",
                  "link": "https://www.pewresearch.org/short-reads/2026/10/19/1-in-5/",
                  "published": datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)}
        self.assertEqual(
            g._citation_line(pew["citation"], sample),
            "“1 in 5 Americans Regularly Get News on TikTok.” Pew Research Center, Washington, D.C. "
            "(October 19, 2026) <https://www.pewresearch.org/short-reads/2026/10/19/1-in-5/>")

    def test_notices_of_the_other_sources_say_what_their_terms_ask(self):
        by_name = {s["name"]: s for s in g.NEWS_SOURCES}
        self.assertIn("United Nations has not reviewed or approved", by_name["UN News"]["notice"]["en"])
        self.assertIn("Federal Reserve Board", by_name["Federal Reserve"]["notice"]["en"])
        self.assertIn("검토하거나 승인하지 않았", by_name["Federal Reserve"]["notice"]["ko"])
        self.assertIn("has not reviewed or approved", by_name["Federal Reserve"]["notice"]["en"])
        self.assertIn("검토하거나 승인하지 않았", by_name["UN News"]["notice"]["ko"])
        self.assertIn("has not reviewed or approved", by_name["Pew Research Center"]["notice"]["en"])
        self.assertIn("연방준비제도 이사회", by_name["Federal Reserve"]["notice"]["ko"])
        self.assertIn("공식 입장이 아닙니다", by_name["UN News"]["notice"]["ko"])
        self.assertIn("not an official UN position", by_name["UN News"]["notice"]["en"])
        self.assertIn("분석과 해석의 책임은 이 사이트에 있습니다", by_name["Pew Research Center"]["notice"]["ko"])
        self.assertIn("responsibility for the analysis and interpretation rests with this site", by_name["Pew Research Center"]["notice"]["en"])

    def test_european_commission_news_skips_bond_auctions_calls_elections_and_democracy_items_only(self):
        # 2026-10-26 피드(30건)에서: 국채 입찰 결과·공지 8건, 모집·신청 1건, 'democracy' 분류 5건이 빠지고 나머지 16건이 남는다.
        base = "https://commission.europa.eu/news-and-media/news/"
        skipped = (
            ("Results of 21-10-2026 auction (EU-Bills)", ("Directorate-General for Budget", "News article")),
            ("Announcement of next auction (EU-Bonds) on 26-10-2026", ("News article", "EU budget")),
            ("Apply now to be a European Climate Pact Ambassador!", ("News article", "climate change")),
            ("The Parliament’s EUDS Special Committee visits the Centre", ("News article", "democracy")),
            ("Pilot phase of Stakeholder Platform begins", ("News article", "democracy")),
            ("The Commission launches a repository for transparency information on online political ads", ("News article",)),
            ("Commission publishes guidance for the 2029 European elections", ("News article",)),
            ("Webinar: how to use the new EU funding portal", ("News article",)),
        )
        for title, tags in skipped:
            self.assertFalse(self.kept("European Commission", title, tags, base + "x_en"), title)
        for title, tags in (
                ("Click wisely: promoting online safety during European Cybersecurity Month", ("Directorate-General for Communication", "News article")),
                ("An EU strategy for a rapidly changing Arctic", ("News article",)),
                ("World Mental Health Day: let’s talk and listen", ("News article",)),
                ("A long-term vision for a successful fisheries and aquaculture sector", ("News article",)),
                ("Making data centres energy efficient thanks to a new EU rating system", ("News article", "energy efficiency"))):
            self.assertTrue(self.kept("European Commission", title, tags, base + "x_en"), title)

    def test_the_eurostat_and_statement_items_in_the_dg_feeds_are_skipped_and_the_rest_kept(self):
        eurostat = "https://ec.europa.eu/eurostat/web/products-eurostat-news/w/ddn-20261020-1"
        presscorner = "https://ec.europa.eu/commission/presscorner/detail/en/ip_26_1234"
        energy_news = "https://energy.ec.europa.eu/news/commission-invests-eu34-billion-net-zero-technology-projects-2026-10-20_en"
        # Eurostat 소식은 Eurostat 자체 고지(출처 표기·면책 문구)가 따로 있어 쓰지 않는다. 프레스 코너 보도자료는 재사용 조건(법적 고지)을 확인하지 못해 쓰지 않는다(아래 전용 시험).
        for name in ("European Commission · Energy", "European Commission · Environment"):
            self.assertFalse(self.kept(name, "Eurostat: EU trade in wind turbines increased in 2025", link=eurostat), name)
            self.assertFalse(self.kept(name, "Commission invests €3.4 billion in net-zero technology projects", link=presscorner), name)
            self.assertTrue(self.kept(name, "Commission invests €3.4 billion in net-zero technology projects", link=energy_news), name)
        energy = "European Commission · Energy"
        self.assertFalse(self.kept(energy, "Statement by President von der Leyen at the joint press conference with President Costa", link=presscorner))
        self.assertFalse(self.kept(energy, "Cross-border gas network code – Commission launches call for feedback on revision of rules"))
        self.assertFalse(self.kept(energy, "Energy Transition Investment Council - Call for applications"))
        for title in ("Oil Coordination Group discusses EU fuel market developments",
                      "EU and New Caledonia sign strategic partnership on sustainable raw materials",
                      "In focus: Renewable energy – building trust and sharing benefits"):
            self.assertTrue(self.kept(energy, title), title)
        self.assertTrue(self.kept("European Commission · Environment", "Bio-based Alliance launches to drive sustainable solutions"))
        self.assertFalse(self.kept("European Commission · Environment", "Apply now: LIFE programme call for applications"))

    def test_the_commission_feeds_never_pull_in_the_eib_or_acer_items(self):
        # 에너지 피드에는 집행위원회 자료가 아닌 EIB·ACER 기사가 섞인다. 이 고지(CC BY 4.0)의 대상이 아니라 신뢰 목록에 두지 않는다.
        for host in ("www.eib.org", "www.acer.europa.eu", "ec.europa.eu.evil.example", "evilec.europa.eu"):
            for lane in g.EDITORIAL_LANES:
                self.assertFalse(g._trusted_domain(host, lane), (host, lane))
        for host, lane in (("energy.ec.europa.eu", "economy"), ("finance.ec.europa.eu", "economy"), ("ec.europa.eu", "economy"),
                           ("environment.ec.europa.eu", "science"), ("projects.research-and-innovation.ec.europa.eu", "science"),
                           ("joint-research-centre.ec.europa.eu", "science"), ("digital-strategy.ec.europa.eu", "technology"),
                           ("commission.europa.eu", "society")):
            self.assertTrue(g._trusted_domain(host, lane), (host, lane))
        self.assertFalse(g._trusted_domain("commission.europa.eu", "economy"))  # 집행위원회 소식 피드는 사회·정책 분야에만 쓴다

    def test_horizon_magazine_articles_never_enter_through_the_commission_feeds(self):
        # Horizon 은 재게시에 원 기자 이름·바닥글을 요구하는데 피드의 기자 이름을 읽지 못한다. DG Environment 피드에 Horizon 기사가 섞여 든다(2026-10-26 검증).
        horizon = "https://projects.research-and-innovation.ec.europa.eu/en/horizon-magazine/plants-and-waste-everyday-products-boosting-europes-bioeconomy"
        news = "https://research-and-innovation.ec.europa.eu/news/all-research-and-innovation-news/horizon-europe-launches-new-research-and-innovation-call-nature-2026-10-02_en"
        for name in ("European Commission", "European Commission · Energy", "European Commission · Environment",
                     "European Commission · JRC", "EU Digital Strategy"):
            with self.subTest(source=name):
                self.assertFalse(self.kept(name, "From plants and waste to everyday products: boosting Europe’s bioeconomy", link=horizon), name)
                # 'Horizon Europe' 연구 사업 소식(집행위원회 R&I 뉴스)은 Horizon 매거진이 아니라 살린다
                self.assertTrue(self.kept(name, "Horizon Europe launches new research and innovation call on nature", link=news), name)

    def test_energy_skips_statements_speeches_and_declarations_but_keeps_news_with_the_word_statement_inside(self):
        energy = "European Commission · Energy"
        for title in ("Statement by President von der Leyen at the joint press conference with President Costa",
                      "Joint statement on energy security", "G7 Leaders’ Statement on the energy transition",
                      "Speech by Commissioner Jørgensen at the Energy Forum", "Remarks by the Commissioner on gas storage",
                      "Berlin Declaration on affordable energy"):
            self.assertFalse(self.kept(energy, title), title)
        for title in ("Commission invests €3.4 billion in net-zero technology projects", "Oil Coordination Group discusses EU fuel market developments",
                      "Energy statistics: renewables share reaches a record"):
            self.assertTrue(self.kept(energy, title), title)

    def test_press_corner_items_are_not_used_until_their_reuse_terms_are_confirmed(self):
        # 보도자료(Press Corner, ec.europa.eu/commission/presscorner)는 앱 바닥글에 법적 고지·라이선스 링크가 없어 재사용 조건을 확인하지 못했다(2026-10-26 약관 검증).
        # 불명확은 유예한다(운영자 원칙). 같은 호스트의 다른 집행위원회 기사는 그대로 쓴다.
        self.assertIn("/commission/presscorner/", g._EC_EXCLUDE_LINK)
        presscorner_links = ("https://ec.europa.eu/commission/presscorner/detail/en/ip_26_1234",
                             "https://ec.europa.eu/commission/presscorner/home/en",
                             "https://ec.europa.eu/commission/presscorner/api/files/document/print/en/ip_26_1234/IP_26_1234_EN.pdf")   # 실제 주소 3형태
        other = "https://ec.europa.eu/info/news/commission-launches-new-energy-tool-2026-10-20_en"
        for name in ("European Commission", "European Commission · Energy", "European Commission · Environment",
                     "European Commission · JRC", "EU Digital Strategy"):
            with self.subTest(source=name):
                for presscorner in presscorner_links:
                    self.assertFalse(self.kept(name, "Commission launches a new tool for households", link=presscorner), (name, presscorner))
                self.assertTrue(self.kept(name, "Commission launches a new tool for households", link=other), name)

    def test_every_commission_source_skips_speeches_statements_and_declarations(self):
        link = "https://energy.ec.europa.eu/news/x_en"
        for name in ("European Commission", "European Commission · Energy", "European Commission · Environment",
                     "European Commission · JRC", "EU Digital Strategy"):
            with self.subTest(source=name):
                for title in ("Statement by President von der Leyen on energy security", "Joint statement on the energy transition",
                              "Speech by Commissioner Jørgensen at the Energy Forum", "Opening remarks by the Commissioner on gas storage",
                              "Berlin Declaration on affordable energy", "G7 Leaders’ Statement on the energy transition",
                              "Joint press conference by the Commissioner and the Minister",
                              "Joint Declaration of Intent on clean hydrogen cooperation"):
                    self.assertFalse(self.kept(name, title, link=link), (name, title))
                for title in ("Energy statistics: renewables share reaches a record", "Commission publishes its annual report on the state of the energy union"):
                    self.assertTrue(self.kept(name, title, link=link), (name, title))

    def test_every_commission_source_keeps_its_display_name_and_the_eurostat_rule(self):
        by_name = {s["name"]: s for s in g.NEWS_SOURCES}
        expected = {"European Commission": None, "European Commission · Energy": "European Commission (DG Energy)",
                    "European Commission · Environment": "European Commission (DG Environment)",
                    "European Commission · JRC": "European Commission, Joint Research Centre",
                    "EU Digital Strategy": "European Commission (Digital Strategy)"}
        for name, shown in expected.items():
            with self.subTest(source=name):
                self.assertEqual(by_name[name].get("display_name"), shown)
                self.assertEqual(by_name[name].get("exclude_link"), g._EC_EXCLUDE_LINK)
                self.assertFalse(self.kept(name, "Eurostat: EU trade in wind turbines increased in 2025",
                                           link="https://ec.europa.eu/eurostat/web/products-eurostat-news/w/ddn-20261020-1"), name)

    def test_the_trust_lists_of_the_new_domains_are_exactly_the_agreed_lanes(self):
        lanes_of = {domain: {lane for lane, domains in g.TRUSTED_SOURCE_DOMAINS.items() if domain in domains}
                    for domain in ("ec.europa.eu", "commission.europa.eu", "statcan.gc.ca", "www.gov.uk")}
        self.assertEqual(lanes_of, {"ec.europa.eu": {"science", "economy", "society", "technology"},
                                    "commission.europa.eu": {"society"},
                                    "statcan.gc.ca": {"economy", "society", "daily_life"},
                                    "www.gov.uk": {"science", "technology"}})
        # GOV.UK 는 www.gov.uk 호스트만 신뢰한다 — 다른 정부 부처 사이트(*.gov.uk)나 비슷한 이름은 아니다
        for host in ("ons.gov.uk", "assets.publishing.service.gov.uk", "gov.uk", "evilgov.uk", "www.gov.uk.evil.example", "nhs.uk"):
            for lane in ("science", "technology"):
                self.assertFalse(g._trusted_domain(host, lane), (host, lane))
        self.assertFalse(g._trusted_domain("www.gov.uk", "economy"))   # 경제 분야 피드(재무부·DWP·DBT)는 정치 발표가 대부분이라 쓰지 않는다

    def test_the_commission_and_statcan_prompt_rules_forbid_medical_advice(self):
        by_name = {s["name"]: s for s in g.NEWS_SOURCES}
        for name in ("European Commission", "European Commission · Energy", "European Commission · Environment", "European Commission · JRC",
                     "EU Digital Strategy", "Statistics Canada · economy", "Statistics Canada · society", "Statistics Canada · daily life"):
            with self.subTest(source=name):
                self.assertIn("진단·치료·복용·예방 효과를 조언하지 마세요", by_name[name]["prompt_rule"])

    def test_energy_and_news_skip_commissioner_visit_notices_and_promotions_but_keep_policy_news(self):
        for name in ("European Commission · Energy", "European Commission"):
            for title in ("Commissioner Jørgensen in Hungary to address high energy prices, energy security and housing",
                          "Commissioner Jørgensen in Slovakia to discuss energy prices and security with Visegrad Energy Ministers",
                          "Commissioner Kos visits Kyiv", "Turning 18? Apply for a DiscoverEU pass",
                          # 이름이 두 단어인 위원, 부위원장·집행부위원장(2026-10-26 코드 검증이 과소 일치로 지적)
                          "Commissioner Dan Jørgensen visits Kyiv", "Executive Vice-President Ribera visits Warsaw to discuss the clean industrial deal",
                          "Vice-President Šefčovič in Washington for trade talks"):
                self.assertFalse(self.kept(name, title), (name, title))
        energy = "European Commission · Energy"
        self.assertFalse(self.kept(energy, "Opening remarks by Commissioner Jørgensen at the press conference"))
        for title in ("Oil Coordination Group discusses EU fuel market developments", "The Commissioner’s energy price package explained"):
            self.assertTrue(self.kept(energy, title), title)

    def test_policy_news_that_merely_contains_apply_or_declaration_is_kept_and_promotions_and_joint_texts_are_dropped(self):
        # 제목 가운데의 "must apply for", 문서 이름인 "Declaration of conformity" 는 정책 기사라 살리고, 신청 홍보·공동 선언·공동 성명·연설(복수형)은 뺀다(코드 검증 과잉·과소 탐침).
        for name in ("European Commission", "European Commission · Energy", "European Commission · Environment"):
            for title in ("Importers must apply for authorisation by 2027 under the new rules", "Declaration of conformity rules for batteries simplified"):
                self.assertTrue(self.kept(name, title), (name, title))
        for name in ("European Commission", "European Commission · Energy", "European Commission · Environment",
                     "European Commission · JRC", "EU Digital Strategy"):
            for title in ("EU-Japan Joint Declaration on clean energy", "G7 Leaders’ Joint Statement on the energy transition",
                          "Speeches by the Commissioner at the forum"):
                self.assertFalse(self.kept(name, title), (name, title))
        environment = "European Commission · Environment"
        self.assertFalse(self.kept(environment, "Apply for a LIFE grant today"))              # 제목 앞의 '신청 안내' 홍보
        self.assertFalse(self.kept(environment, "Apply now: LIFE programme call for applications"))

    def test_atom_and_rss_nested_elements_are_not_taken_for_summaries_unless_they_are_xhtml(self):
        rss = ("<rss xmlns:media='http://search.yahoo.com/mrss/'><channel><item><title>제목 하나</title>"
               "<media:content url='https://x.test/i.jpg' type='image/jpeg'><media:description>이미지 설명입니다</media:description></media:content>"
               "<description>진짜 요약 문장입니다.</description><link>https://www.reuters.com/a</link></item></channel></rss>").encode("utf-8")
        item = g.parse_feed(rss)[0]
        self.assertEqual(item["summary"], "진짜 요약 문장입니다.")
        # xhtml 이 아닌 type 이 붙은 빈 요소는 자식 글자를 읽지 않는다
        atom = ("<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>T</title><summary type='html'><b>태그</b></summary>"
                "<content>본문 글자</content><link href='https://www.reuters.com/b'/></entry></feed>").encode("utf-8")
        self.assertEqual(g.parse_feed(atom)[0]["summary"], "본문 글자")

    def test_jrc_skips_defence_and_security_items_by_feed_category(self):
        jrc = "European Commission · JRC"
        self.assertTrue(self.kept(jrc, "AI adoption more than doubles in almost every EU strategic sector",
                                  ("Joint Research Centre", "Digital transformation, cybersecurity", "News announcement")))
        self.assertTrue(self.kept(jrc, "Food crises across the globe: acute food insecurity remains alarmingly high",
                                  ("Joint Research Centre", "Anticipation, risks, resilience", "Sustainable food systems")))
        self.assertFalse(self.kept(jrc, "How can Europe counter hybrid warfare?", ("Joint Research Centre", "Space, security, defence")))
        self.assertFalse(self.kept(jrc, "JRC launches Security Research and Innovation Campus",
                                   ("Joint Research Centre", "Security and law enforcement", "Space, security, defence")))
        # 앵커가 있는 분류 태그는 정확히 그 태그일 때만 거른다
        self.assertTrue(self.kept(jrc, "Privacy tools for citizens", ("Joint Research Centre", "Security and law enforcement research methods")))
        # 태그 하나만으로 결과가 갈린다(제외 정규식을 하나씩 지워도 시험이 실패하게)
        self.assertFalse(self.kept(jrc, "Border technology", ("Security and law enforcement",)))
        self.assertFalse(self.kept(jrc, "Space systems", ("Space, security, defence",)))
        self.assertTrue(self.kept(jrc, "Space systems", ("Space",)))

    def test_eu_digital_strategy_skips_only_calls_for_tenders(self):
        name = "EU Digital Strategy"
        self.assertFalse(self.kept(name, "Establishing the European AI Observatory: Call for tenders"))
        for title in ("First harmonised standard supporting the AI Act published in the Official Journal",
                      "Commission to investigate how Booking.com combats scams and fraud under the Digital Services Act",
                      "Consultation on EU KIDS ACT"):
            self.assertTrue(self.kept(name, title), title)

    def test_statcan_keeps_headline_releases_and_studies_and_drops_technical_products_and_sensitive_topics(self):
        economy, society, life = "Statistics Canada · economy", "Statistics Canada · society", "Statistics Canada · daily life"
        # 2026-10-26 The Daily 실제 제목
        for title in ("Retail trade, August 2026", "Consumer Price Index, September 2026", "Labour Force Survey, September 2026",
                      "Gross domestic product by industry, July 2026", "New Housing Price Index, September 2026",
                      "Canadian international merchandise trade, August 2026", "Employment Insurance, August 2026", "Building permits, August 2026",
                      "Impact of cybercrime on Canadian businesses, 2025"):
            self.assertTrue(self.kept(economy, title), title)
        for title in ("Industrial product and raw materials price indexes, September 2026", "Retail Services Price Index, August 2026",
                      "Lending Services Price Index, second quarter 2026", "Natural gas supply and disposition, August 2026",
                      "Monthly credit aggregates, August 2026", "Monthly Mineral Production Survey, August 2026",
                      "Building construction price indexes: announcement", "Electric power generating stations, 2025",
                      "Employment by industry in rural Canada: Interactive dashboard, September 2026", "Open Database of Healthcare Facilities, version 2.0"):
            self.assertFalse(self.kept(economy, title), title)
        for title in ("The gender gap in high school graduation narrows in 2023/2024", "Canadian postsecondary enrolments and graduates, 2024/2025",
                      "Canada's population estimates, second quarter 2026", "Housing affordability in Canada, 2024",
                      "Police-reported hate crime and cybercrime, preliminary quarterly data, second quarter 2026"):
            self.assertTrue(self.kept(society, title), title)
        for title in ("Health Reports, October 2026", "Canadian Community Health Survey, 2025", "Births, 2025", "Fertility and baby names, 2025",
                      "Study: Understanding quality of life among persons with disabilities in Canada—material and social well-being"):
            self.assertTrue(self.kept(life, title), title)
        # 자동으로 다시 쓰기에 민감한 주제는 세 분야 모두에서 뺀다. 같은 낱말이 든 평범한 제목은 살린다.
        sensitive = ("Violent victimization and unwanted sexual behaviours experienced by 2SLGBTQ+ people in Canada, 2025",
                     "Opioid and stimulant consumption patterns in select Canadian cities, January 2024 to March 2026",
                     "Suicide mortality in Canada, 2023", "Homicide in Canada, 2025", "Drug overdose deaths and hospitalizations, 2025",
                     "Police-reported violence among gender-related homicide victims in Canada, 2025",   # 2026-10-26 실제 피드 222번째 — 'police'(사회 주제어)에 걸려 제외어가 없으면 통과했다
                     "Self-harm among youth in Canada, 2024", "Family violence in Canada, 2025", "Intimate partner violence, 2025",
                     "Child abuse and maltreatment statistics, 2025",
                     # 제외어를 하나씩 지워도 시험이 실패하게 낱말마다 단독 제목을 둔다(코드 검증의 생존 변이 9개)
                     "Domestic violence in Canada, 2025", "Gender-based violence among youth, 2025", "Child maltreatment in Canada, 2024",
                     "Opioid-related harms, 2025", "Stimulant use patterns, 2025", "Sexual assault in Canada, 2024",
                     "Violent victimization in Canada, 2024")
        harmless = ("Violent crime severity index, 2025", "Family income and household wealth, 2025", "Child care costs, 2025",
                    "Domestic travel by Canadians, 2025", "Drinking and driving trends, 2025")
        for name in (economy, society, life):
            src = next(s for s in g.NEWS_SOURCES if s["name"] == name)
            for title in sensitive:
                # 주제어 불일치(OFF_TOPIC)가 아니라 제외 규칙(EXCLUDED)이 직접 걸러야 한다 — 제외어를 지워도 시험이 실패하게
                self.assertTrue(g._rule_excludes(src, title, {"link": "", "categories": []}), (name, title))
            for title in harmless:
                self.assertFalse(g._rule_excludes(src, title, {"link": "", "categories": []}), (name, title))   # 같은 낱말이 든 평범한 제목은 살린다
        # 분야가 다른 제목은 이 분야 주제어에 맞지 않아 떨어진다(OFF_TOPIC)
        self.assertFalse(self.kept(society, "Retail trade, August 2026"))
        self.assertFalse(self.kept(life, "Consumer Price Index, September 2026"))
        self.assertFalse(self.kept(economy, "Births, 2025"))

    def test_the_new_sources_carry_the_credit_and_change_notices_their_licences_ask_for(self):
        by_name = {s["name"]: s for s in g.NEWS_SOURCES}
        sample = {"title": "AI adoption more than doubles in almost every EU strategic sector",
                  "link": "https://joint-research-centre.ec.europa.eu/jrc-news-and-updates/ai-adoption_en",
                  "published": datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)}
        for name in ("European Commission", "European Commission · Energy", "European Commission · Environment",
                     "European Commission · JRC", "EU Digital Strategy"):
            with self.subTest(source=name):
                src = by_name[name]
                line = g._citation_line(src["citation"], sample)
                for needle in ("AI adoption more than doubles", "October 23, 2026", sample["link"], "© European Union", "CC BY 4.0",
                               "https://creativecommons.org/licenses/by/4.0/"):
                    self.assertIn(needle, line)
                self.assertNotIn("{", line)
                self.assertIn("CC BY 4.0", src["notice"]["ko"])
                self.assertIn("바뀐 부분", src["notice"]["ko"])
                self.assertIn("보증하지 않았", src["notice"]["ko"])
                self.assertIn("CC BY 4.0", src["notice"]["en"])
                self.assertIn("changes were made", src["notice"]["en"])
                self.assertIn("has not reviewed or endorsed", src["notice"]["en"])
                self.assertIn("확정된 법·결정을 구분", src["prompt_rule"])
                self.assertIn("왜곡하지 말고", src["prompt_rule"])
        self.assertIn("DG CNECT", by_name["EU Digital Strategy"]["citation"])            # 디지털 전략 사이트의 출처 표시 안내(작품 제목·유럽연합 귀속·원문 주소)
        self.assertIn("Anonymous (not verified)", by_name["EU Digital Strategy"]["prompt_rule"])
        for name in ("Statistics Canada · economy", "Statistics Canada · society", "Statistics Canada · daily life"):
            with self.subTest(source=name):
                src = by_name[name]
                self.assertEqual(
                    g._citation_line(src["citation"], dict(sample, title="Retail trade, August 2026", link="https://www.statcan.gc.ca/daily-quotidien/261023/dq261023a-eng.htm")),
                    "Adapted from Statistics Canada, Retail trade, August 2026, October 23, 2026. This does not constitute an endorsement by Statistics Canada of this product.")
                self.assertNotIn("statcan.gc.ca", g._citation_line(src["citation"], sample))  # 통계청 도메인 이름을 글에 표시하지 않는다(링크는 출처 목록에만)
                self.assertIn("보증하지 않았", src["notice"]["ko"])
                self.assertIn("has not reviewed or endorsed", src["notice"]["en"])
                self.assertIn("그대로 쓰세요", src["prompt_rule"])
                self.assertIn("statcan.gc.ca", src["prompt_rule"])            # 링크 글자에 주소를 보이지 않게 하는 지침(통계청 'Advertising and Publicity')
                self.assertEqual(src.get("page_delay"), 2)                    # 통계청 robots.txt 의 Crawl-delay: 2

    def test_govuk_keeps_news_stories_and_drops_speeches_publications_case_studies_appointments_and_sensitive_items(self):
        env, tech = "GOV.UK · Environment & Energy", "GOV.UK · Science & Technology"
        news = "https://www.gov.uk/government/news/"
        # 2026-10-26 DESNZ·Defra 피드의 실제 제목: 보도 기사(/government/news/)는 살린다
        for title, slug in (("Households to receive £150 Warm Home Discount confirmation letter", "households-to-receive-150-warm-home-discount-confirmation-letter"),
                            ("World-first taskforce to protect communities from climate change", "world-first-taskforce-to-protect-communities-from-climate-change"),
                            ("Octopus explosion off South West prompts talks between fishermen and scientists", "octopus-explosion-off-south-west"),
                            ("Plan to unlock organic market for stronger farms, more homegrown food", "plan-to-unlock-organic-market"),
                            ("£1.6m fine for Anglian Water's pollution of Essex river", "16m-fine-for-anglian-waters-pollution-of-essex-river"),
                            ("Government activates plan to protect consumers as severe drought declared in parts of England", "government-activates-plan-to-protect-consumers")):
            self.assertTrue(self.kept(env, title, link=news + slug), title)
        # DSIT·AISI 피드의 실제 제목(2026-06~10)
        for title, slug in (("UK backs new AI labs to make technology cheaper, more reliable and easier to use", "uk-backs-new-ai-labs"),
                            ("World’s first national framework for quantum standards to boost UK leadership", "worlds-first-national-framework-for-quantum-standards"),
                            ("Britain steps up national defences against growing AI risks", "britain-steps-up-national-defences-against-growing-ai-risks"),
                            ("Businesses across Britain sign up to Cyber Resilience Pledge as ministers urge firms to strengthen cyber defences", "businesses-sign-up-to-cyber-resilience-pledge")):
            self.assertTrue(self.kept(tech, title, link=news + slug), title)
        # 같은 피드에 섞이는 연설·정책 문서·편지·사례 소개는 주소 경로로 뺀다
        for title, path in (("The role of heat networks in the energy transition", "speeches/the-role-of-heat-networks-in-the-energy-transition"),
                            ("Strategic Spatial Energy Plan: deadline extension", "publications/strategic-spatial-energy-plan-deadline-extension"),
                            ("Ministerial direction to protect public water supplies in areas affected by severe drought", "publications/ministerial-direction-to-protect-public-water-supplies"),
                            ("Improving access to and use of digital services: open letter to business leaders", "publications/improving-access-to-and-use-of-digital-services"),
                            ("When AI Leaves the Lab: Testing Frontier Models in Government Cyber Defence", "case-studies/when-ai-leaves-the-lab"),
                            ("Liz Kendall's statement on children and social media", "speeches/liz-kendalls-statement-on-children-and-social-media")):
            for name in (env, tech):
                self.assertFalse(self.kept(name, title, link="https://www.gov.uk/government/" + path), (name, title))
        # 보도 기사라도 인사·신청 안내·성명·선거·전쟁 소재·민감 주제는 뺀다(주소가 아니라 제목 규칙이 직접 걸러야 한다)
        for title in ("Two new appointments to the Marine Management Organisation board",
                      "Seven non-executive members appointed to Information Commission Board as chair recruitment launches",
                      "Government reappoints the chair of the Environment Agency",
                      "New chief executive named for the Met Office", "Chair recruitment launches for the new regulator",
                      "Barnsley Tech Town's £800,000 AI skills fund opens for applications",
                      "Applications are now open for the Clean Heat Grant", "Applications open for the green skills programme",
                      "Apply now for the farming resilience fund", "Apply for a green homes grant today", "Call for evidence on water company performance", "Call for views on the new energy plan",
                      "Joint statement from the UK and Canada on clean energy", "Joint statement signed at the clean energy summit", "Statement on the death of a former minister", "Condolences on the passing of the former chair",
                      "New partnership set to see the UK and Ukraine develop battle winning technology", "Military drones to be tested in new range",
                      "UK sanctions Russia over energy exports", "Elections Act changes explained", "Political parties to publish funding data",
                      # 낱말마다 단독 제목(제외어를 하나씩 지워도 시험이 실패하게)
                      "New weapons export controls announced", "Hybrid warfare resilience plan published", "Missiles testing range to expand",
                      "Armed forces covenant update for veterans", "Gaza aid flights resume", "Terror attack response drill held",
                      "New measures to tackle self-harm content online", "Suicide prevention funding for the NHS", "Child sexual abuse material to be blocked by new AI tool", "Child sexual imagery detection tool launched",
                      "Sexual exploitation online: new offence announced", "Counter-terrorism strategy published",
                      # 코드 검증이 지적한 보강: 인사 소식·분쟁·학대·극단주의, 단독 낱말 제목(제외어를 하나씩 지워도 시험이 실패하게)
                      "New chair announced for the Environment Agency", "Chief executive steps down at the Met Office", "Minister appoints new advisers to the AI panel",
                      "Dr Jane Smith appointed lead scientist for the new AI lab", "Russia gas imports fall to a record low", "Middle East energy outlook published",
                      "Iran energy talks resume", "Israel and the UK sign a research agreement", "NATO summit agrees new cyber funding", "New sanctions on energy exports announced",
                      "Child abuse imagery detection to be expanded", "Domestic abuse victims to get new online support", "Violence against women and girls strategy published",
                      "Extremism commission launched", "Radicalisation online: new report published",
                      "Call for input on AI regulation", "Call for applications to the AI fellowship", "Statement from the Energy Secretary on energy bills",
                      "Statement by the Environment Secretary on flooding", "Sexual abuse online: new measures", "Sexual assault reporting to be easier", "Sexual violence strategy refreshed"):
            for name in (env, tech):
                src = next(s for s in g.NEWS_SOURCES if s["name"] == name)
                self.assertTrue(g._rule_excludes(src, title, {"link": news + "x", "categories": []}), (name, title))
        # 같은 낱말이 든 평범한 기사(제목 가운데의 "must apply for", 낱말 일부 일치)는 살린다
        for title in ("Applying for the Warm Home Discount made simpler", "Households must apply for the new scheme by March",
                      "Flood defences get a funding boost", "Rural broadband rollout reaches another 2,000 homes",
                      "AI to speed up appointments for patients", "NHS appointments made easier with a new booking tool"):
            for name in (env, tech):
                src = next(s for s in g.NEWS_SOURCES if s["name"] == name)
                self.assertFalse(g._rule_excludes(src, title, {"link": news + "x", "categories": []}), (name, title))

    def test_govuk_link_rule_passes_only_https_news_stories_on_the_exact_host(self):
        # 코드 검증의 생존 변이(http 허용·점 이스케이프 삭제·news/ 끝 슬래시 삭제)를 잡는다. 호스트 신뢰는 따로 시험하지만 링크 규칙도 스스로 엄격해야 한다.
        src = next(s for s in g.NEWS_SOURCES if s["name"] == "GOV.UK · Environment & Energy")
        cases = (("https://www.gov.uk/government/news/ok-story", False), ("https://WWW.GOV.UK/government/news/ok-story?x=1#y", False),
                 ("http://www.gov.uk/government/news/ok-story", True), ("https://wwwxgovxuk/government/news/ok-story", True),
                 ("https://www.gov.uk/government/newsflash/ok-story", True), ("https://www.gov.uk/government/news", True),
                 ("https://www.gov.uk/government/speeches/ok-story", True), ("https://www.gov.uk.evil.example/government/news/ok-story", True),
                 ("/government/news/ok-story", True), ("", True))
        for link, excluded in cases:
            with self.subTest(link=link):
                self.assertEqual(g._rule_excludes(src, "A plain title", {"link": link, "categories": []}), excluded, link)

    def test_govuk_sources_carry_the_ogl_credit_and_notice_and_forbid_medical_advice(self):
        by_name = {s["name"]: s for s in g.NEWS_SOURCES}
        sample = {"title": "Jackdaw gas field gets green light", "link": "https://www.gov.uk/government/news/jackdaw-gas-field-gets-green-light",
                  "published": datetime(2026, 10, 23, 17, 30, tzinfo=timezone.utc)}
        ogl = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
        for name in ("GOV.UK · Environment & Energy", "GOV.UK · Science & Technology"):
            with self.subTest(source=name):
                src = by_name[name]
                self.assertEqual(src["display_name"], "GOV.UK")
                self.assertEqual(src["terms"], {"status": "allowed", "checked": "2026-10-26", "url": "https://www.gov.uk/help/terms-conditions"})
                self.assertEqual(
                    g._citation_line(src["citation"], sample),
                    "“Jackdaw gas field gets green light.” GOV.UK, October 23, 2026 <https://www.gov.uk/government/news/jackdaw-gas-field-gets-green-light>. "
                    "Contains public sector information licensed under the Open Government Licence v3.0. (" + ogl + ")")
                self.assertIn("Open Government Licence v3.0", src["notice"]["ko"])
                self.assertIn("바뀐 부분", src["notice"]["ko"])
                self.assertIn("보증하지 않았", src["notice"]["ko"])
                self.assertIn("공식 입장이나 공식 문서가 아닙니다", src["notice"]["ko"])      # OGL Non-endorsement: 공식 지위를 암시하지 말 것
                self.assertIn("is not an official government publication or position", src["notice"]["en"])
                self.assertIn("Contains public sector information licensed under the Open Government Licence v3.0.", src["notice"]["en"])
                self.assertIn(ogl, src["notice"]["en"])
                self.assertIn("changes were made", src["notice"]["en"])
                self.assertIn("have not reviewed or endorsed", src["notice"]["en"])
                self.assertIn("진단·치료·복용·예방 효과를 조언하지 마세요", src["prompt_rule"])
                self.assertIn("정당·선거·장관 개인에 대한 평가", src["prompt_rule"])
                self.assertIn("공식 입장·문서인 것처럼 쓰지 마세요", src["prompt_rule"])
                self.assertIs(src.get("no_page_fetch"), True)   # 기사 페이지의 메타 설명이 피드 요약과 같아 읽어도 소용없다
                self.assertEqual(src.get("exclude_link"), g._GOVUK_EXCLUDE_LINK)

    def test_pew_topic_words_need_word_boundaries(self):
        pew = next(s for s in g.NEWS_SOURCES if s["name"] == "Pew Research Center")
        for text in ("Automobile ownership trends", "Spreading costs across households"):
            self.assertFalse(re.search(pew["topic_regex"], text, re.I), text)
        for text in ("Americans’ Use of Mobile Devices in 2026", "Reading habits of adults"):
            self.assertTrue(re.search(pew["topic_regex"], text, re.I), text)


class SourceListTest(unittest.TestCase):
    # 모든 분야에 읽는 소스가 있다(2026-10-26 해외 소스 추가: 일상·마음·사회·정책은 Statistics Canada·집행위원회 소식). UN News 는 보류(pending)라 읽지 않는다(D-63).
    # 분야가 하나라도 다시 비면 여기에 적고 이유를 남긴다(그 분야가 뽑히면 후보가 없어 다음 분야로 넘어간다).
    LANES_WITHOUT_SOURCES = set()
    # 약관을 읽지 못했거나 불명확해 운영자 결정 전까지 쓰는 기존 소스(유예). 마지막이던 전자신문을 2026-10-26에 뺐다 — 지금은 없고 새로 늘릴 수 없다.
    # 읽고 allowed 로 올리거나 목록에서 빼서 줄이기만 한다. 금지로 읽히면 소스에 두지 않고 TERMS_BLOCKED_DOMAINS 에 올린다.
    LEGACY_GRACE = set()

    def test_dead_bloter_feed_is_gone(self):
        self.assertNotIn("블로터", [s["name"] for s in g.NEWS_SOURCES])
        self.assertFalse(any("bloter.net/feed" in s["url"] for s in g.NEWS_SOURCES))

    def test_every_lane_has_a_source_it_actually_reads_except_the_known_gaps(self):
        every = {s.get("lane") for s in g.NEWS_SOURCES}
        self.assertTrue(every <= set(g.EDITORIAL_LANES), every - set(g.EDITORIAL_LANES))
        read = {s["lane"] for s in g.NEWS_SOURCES if s["terms"]["status"] != "pending"}
        self.assertEqual(set(g.EDITORIAL_LANES) - read, self.LANES_WITHOUT_SOURCES)

    def test_google_news_sources_are_gone(self):
        self.assertEqual([s["name"] for s in g.NEWS_SOURCES
                          if s.get("google") or "news.google.com" in s["url"] or s["name"].startswith("Google")], [])

    def test_source_names_are_unique_and_every_feed_lane_and_publisher_is_pinned(self):
        names = [s["name"] for s in g.NEWS_SOURCES]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual({s["name"]: (s["lane"], s["url"]) for s in g.NEWS_SOURCES}, {
            "NASA": ("science", "https://www.nasa.gov/feed/"),
            "UN News": ("society", "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
            "Pew Research Center": ("culture", "https://www.pewresearch.org/feed/"),
            "Federal Reserve": ("economy", "https://www.federalreserve.gov/feeds/press_all.xml"),
            "European Commission": ("society", "https://commission.europa.eu/node/2/rss_en"),
            "European Commission · Energy": ("economy", "https://energy.ec.europa.eu/node/2/rss_en"),
            "European Commission · Environment": ("science", "https://environment.ec.europa.eu/node/92/rss_en"),
            "European Commission · JRC": ("science", "https://joint-research-centre.ec.europa.eu/node/2/rss_en"),
            "EU Digital Strategy": ("technology", "https://digital-strategy.ec.europa.eu/en/rss.xml"),
            "Statistics Canada · economy": ("economy", "https://www150.statcan.gc.ca/n1/rss/dai-quo/0-eng.atom"),
            "Statistics Canada · society": ("society", "https://www150.statcan.gc.ca/n1/rss/dai-quo/0-eng.atom"),
            "Statistics Canada · daily life": ("daily_life", "https://www150.statcan.gc.ca/n1/rss/dai-quo/0-eng.atom"),
            "GOV.UK · Environment & Energy": ("science", "https://www.gov.uk/search/news-and-communications.atom?organisations%5B%5D=department-for-energy-security-and-net-zero"
                                                         "&organisations%5B%5D=department-for-environment-food-rural-affairs"),
            "GOV.UK · Science & Technology": ("technology", "https://www.gov.uk/search/news-and-communications.atom?organisations%5B%5D=ai-security-institute"
                                                            "&organisations%5B%5D=department-for-science-innovation-and-technology"),
        })
        # 읽는 소스 전부(승인 상태와 상관없이)의 피드 호스트가 자기 분야에서 신뢰된다
        for src in g.NEWS_SOURCES:
            self.assertTrue(g._trusted_domain(g._host(src["url"]), src["lane"]), src["name"])
        # 피드와 기사 호스트가 다른 소스(통계청 피드 www150 → 기사 www.statcan.gc.ca)도 기사 호스트가 신뢰된다
        for host, lane in (("www.nasa.gov", "science"), ("science.nasa.gov", "science"),
                           ("www.statcan.gc.ca", "economy"), ("www.statcan.gc.ca", "society"), ("www.statcan.gc.ca", "daily_life")):
            self.assertTrue(g._trusted_domain(host, lane), (host, lane))

    def test_the_tech_title_filter_still_works_though_no_source_uses_it(self):
        # tech_filter 를 쓰던 마지막 소스(전자신문)를 2026-10-26에 뺐다. 기능과 낱말 목록은 남겨 두어 시험으로 고정한다.
        self.assertEqual([s["name"] for s in g.NEWS_SOURCES if s.get("tech_filter")], [])
        self.assertFalse(g.is_tech_title("오십견인 줄, 방치했더니…'옆으로 누워 자는 습관', 어깨 통증 키운다"))
        self.assertTrue(g.is_tech_title("사람 표정 따라하는 28cm AI 로봇"))

    def test_english_tech_words_are_found_next_to_korean_text_but_not_inside_other_words(self):
        for title in ("AI가 일자리를 바꾼다", "GPU가 부족한 진짜 이유", "생성AI 시대의 일하는 법", "온디바이스AI 경쟁 본격화",
                      "LLM을 쓰는 법", "5G를 넘어 6G로", "Nvidia와 손잡은 회사"):
            with self.subTest(title=title):
                self.assertTrue(g.is_tech_title(title), title)
        for title in ("Dubai 부동산 시장 전망", "Taipei 여행 후기", "Chipotle 신메뉴 출시", "Wait 후기와 AIDS 연구 동향"):
            with self.subTest(title=title):
                self.assertFalse(g.is_tech_title(title), title)

    def test_every_english_tech_word_is_pinned_on_its_own(self):
        words = [w for w in "ai gpu cpu llm chatgpt openai nvidia 5g 6g chip robot quantum software cloud startup cyber satellite rocket".split()]
        self.assertEqual(len(words), 18)
        for word in words:
            for form in (word, word.upper()):
                with self.subTest(word=form):
                    self.assertTrue(g.is_tech_title(f"{form}를 둘러싼 논쟁"), form)
                    self.assertFalse(g.is_tech_title(f"x{form} 이야기"), form)

    def test_look_alike_hosts_are_never_trusted_and_never_blocked_by_accident(self):
        for host in ("notbbc.co.uk", "bbc.com.evil.example", "evilnasa.gov", "nasa.gov.evil.example", "xfederalreserve.gov"):
            for lane in g.EDITORIAL_LANES:
                with self.subTest(host=host, lane=lane):
                    self.assertFalse(g._trusted_domain(host, lane))
        self.assertTrue(g._host_in("sub.bbc.co.uk", g.TERMS_BLOCKED_DOMAINS))
        self.assertFalse(g._host_in("notbbc.co.uk", g.TERMS_BLOCKED_DOMAINS))

    def test_trust_is_per_lane_and_an_unknown_lane_trusts_nothing(self):
        self.assertTrue(g._trusted_domain("www.nasa.gov", "science"))
        self.assertFalse(g._trusted_domain("www.nasa.gov", "culture"))
        self.assertFalse(g._trusted_domain("news.un.org", "science"))
        for lane in (None, "", "no-such-lane"):
            for host in ("www.nasa.gov", "www.reuters.com"):
                self.assertFalse(g._trusted_domain(host, lane), (host, lane))

    def test_the_blocked_domain_list_is_exactly_the_agreed_publishers(self):
        self.assertEqual(set(g.TERMS_BLOCKED_DOMAINS),
                         {"bbc.com", "bbc.co.uk", "bbci.co.uk", "theguardian.com", "guardian.co.uk",
                          "nature.com", "technologyreview.com", "aitimes.com", "arstechnica.com", "ieee.org", "etnews.com"})

    def test_pew_never_reads_article_pages_and_the_prompt_rules_exist(self):
        by_name = {s["name"]: s for s in g.NEWS_SOURCES}
        self.assertIs(by_name["Pew Research Center"].get("no_page_fetch"), True)
        self.assertIn("NASA가 직접", by_name["NASA"]["prompt_rule"])
        self.assertIn("according to NASA", by_name["NASA"]["prompt_rule"])
        self.assertIn("Pew", by_name["Pew Research Center"]["prompt_rule"])

    def test_every_source_declares_its_terms_status(self):
        for src in g.NEWS_SOURCES:
            with self.subTest(source=src["name"]):
                terms = src.get("terms")
                self.assertIsInstance(terms, dict)
                self.assertIn(terms.get("status"), {"allowed", "pending", "unverified"})
                if terms["status"] in {"allowed", "pending"}:
                    self.assertRegex(terms.get("checked", ""), r"^\d{4}-\d{2}-\d{2}$")
                    self.assertTrue(terms.get("url", "").startswith("https://"))
                if terms["status"] == "pending":
                    self.assertTrue(str(terms.get("blocker", "")).strip(), "보류에는 이유(blocker)가 있어야 한다")
                if terms["status"] == "unverified" and src["name"] in self.LEGACY_GRACE:
                    self.assertTrue(str(terms.get("note", "")).strip(), "유예 소스는 읽은 결과(note)를 남긴다")

    def test_sources_under_grace_cannot_grow(self):
        grace = {s["name"] for s in g.NEWS_SOURCES if s["terms"]["status"] == "unverified"}
        self.assertTrue(grace <= self.LEGACY_GRACE, grace - self.LEGACY_GRACE)
        self.assertEqual(grace, set(), "2026-10-26 이후 약관 불명확(unverified) 소스는 없다")

    def test_etnews_is_blocked_and_neither_read_nor_trusted_anywhere(self):
        # 콘텐츠 이용에 사전 협의·정식 계약·사용료가 필요하고 무단 사용에는 30배 배상을 안내한다. 운영자 결정(2026-10-26 "무료 자동화 기반" 취지에 맞지 않음)으로 접근하지 않는다.
        self.assertIn("etnews.com", g.TERMS_BLOCKED_DOMAINS)
        self.assertEqual([s["name"] for s in g.NEWS_SOURCES if s["name"] == "전자신문" or "etnews" in s["url"]], [])
        for host in ("www.etnews.com", "rss.etnews.com", "etnews.com"):
            for lane in g.EDITORIAL_LANES:
                self.assertFalse(g._trusted_domain(host, lane), (host, lane))
        for lane, domains in g.TRUSTED_SOURCE_DOMAINS.items():
            self.assertNotIn("etnews.com", domains, lane)
        self.assertFalse(g._host_in("notetnews.com", g.TERMS_BLOCKED_DOMAINS))  # 비슷한 이름은 막지 않는다

    def test_aitimes_is_blocked_and_neither_read_nor_trusted_anywhere(self):
        # 기사 페이지 하단의 'AI학습 및 활용 금지' 표기(2026-10-26)와 운영자 결정("금지된 부분이면 접근하지 않는다")으로 접근하지 않는다.
        self.assertIn("aitimes.com", g.TERMS_BLOCKED_DOMAINS)
        self.assertEqual([s["name"] for s in g.NEWS_SOURCES if s["name"] == "AI타임스" or "aitimes" in s["url"]], [])
        for lane in g.EDITORIAL_LANES:
            self.assertFalse(g._trusted_domain("www.aitimes.com", lane), lane)

    def test_ars_and_ieee_are_blocked_and_neither_read_nor_trusted_anywhere(self):
        # robots.txt 가 AI 크롤러를 막는 사이트라 운영자 결정(2026-10-26 "AI 크롤러를 막는 사이트는 접근하지 않는 원칙")으로 접근하지 않는다.
        self.assertIn("arstechnica.com", g.TERMS_BLOCKED_DOMAINS)
        self.assertIn("ieee.org", g.TERMS_BLOCKED_DOMAINS)
        self.assertEqual([s["name"] for s in g.NEWS_SOURCES
                          if s["name"] in {"Ars Technica", "IEEE Spectrum"} or "arstechnica" in s["url"] or "ieee.org" in s["url"]], [])
        for host in ("arstechnica.com", "feeds.arstechnica.com", "spectrum.ieee.org", "www.ieee.org"):
            for lane in g.EDITORIAL_LANES:
                self.assertFalse(g._trusted_domain(host, lane), (host, lane))
        for lane, domains in g.TRUSTED_SOURCE_DOMAINS.items():
            self.assertFalse({"arstechnica.com", "ieee.org"} & set(domains), lane)

    def test_sources_that_never_produce_candidates_and_have_restrictive_terms_are_gone(self):
        # 신뢰 목록에 없어 글감이 한 건도 안 되는 TechCrunch·The Verge, 링크가 약관을 읽지 않은 매체로 가는 Hacker News.
        names = {s["name"] for s in g.NEWS_SOURCES}
        self.assertFalse(names & {"TechCrunch", "The Verge", "Hacker News"})

    def test_un_news_is_held_until_its_conditions_are_met(self):
        un = next(s for s in g.NEWS_SOURCES if s["name"] == "UN News")
        self.assertEqual(un["terms"]["status"], "pending")
        self.assertIn("robots.txt", un["terms"]["blocker"])

    def test_pew_texts_carry_what_pews_terms_require(self):
        pew = next(s for s in g.NEWS_SOURCES if s["name"] == "Pew Research Center")
        self.assertIn("Pew Research Center, Washington, D.C.", pew["citation"])
        self.assertIn("Pew Research Center has published the original content in English but has not reviewed or approved this translation.",
                      pew["notice"]["ko"])

    def test_nasa_notice_says_nasa_is_not_responsible_for_accuracy(self):
        nasa = next(s for s in g.NEWS_SOURCES if s["name"] == "NASA")
        self.assertIn("정확성에 책임지지 않", nasa["notice"]["ko"])
        self.assertIn("not responsible for its accuracy", nasa["notice"]["en"])
        # NASA 의 AI 이용 안내: 검토·승인했다고 암시하지 말고, NASA 의 입장처럼 쓰지 말 것
        self.assertIn("검토하거나 승인하지 않았", nasa["notice"]["ko"])
        self.assertIn("NASA의 입장이 아닙니다", nasa["notice"]["ko"])
        self.assertIn("has not reviewed or approved", nasa["notice"]["en"])
        self.assertIn("does not represent NASA's position", nasa["notice"]["en"])

    def test_terms_blocked_publishers_are_in_no_source_and_no_trust_list(self):
        for domain in ("bbc.com", "bbc.co.uk", "theguardian.com", "nature.com", "technologyreview.com", "aitimes.com",
                       "arstechnica.com", "ieee.org", "etnews.com"):
            self.assertIn(domain, g.TERMS_BLOCKED_DOMAINS)
        for lane, domains in g.TRUSTED_SOURCE_DOMAINS.items():
            for domain in domains:
                self.assertFalse(g._host_in(domain, g.TERMS_BLOCKED_DOMAINS), f"{lane}: {domain}")
        for src in g.NEWS_SOURCES:
            self.assertFalse(g._host_in(g._host(src["url"]), g.TERMS_BLOCKED_DOMAINS), src["name"])

    def test_a_blocked_domain_is_refused_even_if_someone_adds_it_to_a_trust_list(self):
        widened = {**g.TRUSTED_SOURCE_DOMAINS,
                   "technology": g.TRUSTED_SOURCE_DOMAINS["technology"]
                   + ("bbc.co.uk", "technologyreview.com", "arstechnica.com", "ieee.org", "etnews.com")}
        with mock.patch.object(g, "TRUSTED_SOURCE_DOMAINS", widened):
            self.assertFalse(g._trusted_domain("www.bbc.co.uk", "technology"))
            self.assertFalse(g._trusted_domain("www.technologyreview.com", "technology"))
            self.assertFalse(g._trusted_domain("feeds.arstechnica.com", "technology"))
            self.assertFalse(g._trusted_domain("spectrum.ieee.org", "technology"))
            self.assertFalse(g._trusted_domain("www.etnews.com", "technology"))
            self.assertTrue(g._trusted_domain("digital-strategy.ec.europa.eu", "technology"))

    def test_each_allowed_source_publisher_is_trusted_in_its_own_lane(self):
        for src in g.NEWS_SOURCES:
            if src["terms"]["status"] == "allowed":
                self.assertTrue(g._trusted_domain(g._host(src["url"]), src["lane"]), src["name"])
        for host, lane in (("science.nasa.gov", "science"), ("news.un.org", "society")):
            self.assertTrue(g._trusted_domain(host, lane), host)

    def test_every_citation_template_fills_in_and_every_source_has_a_visible_name(self):
        sample = {"title": "Sample release", "link": "https://example.test/a", "published": datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)}
        for src in g.NEWS_SOURCES:
            with self.subTest(source=src["name"]):
                if src.get("citation"):
                    line = g._citation_line(src["citation"], sample)
                    self.assertIn("October 23, 2026", line)
                    self.assertNotRegex(line, r"[{}]")
                self.assertTrue(str(src.get("display_name") or src["name"]).strip())

    def test_source_regexes_compile_and_notices_cover_both_languages(self):
        for src in g.NEWS_SOURCES:
            for key in ("exclude_title", "topic_regex", "exclude_link", "exclude_tags"):
                if src.get(key):
                    re.compile(src[key], re.I)
            if src["terms"]["status"] in {"allowed", "pending"}:
                self.assertEqual(sorted(src["notice"]), ["en", "ko"], src["name"])
                self.assertTrue(all(src["notice"].values()), src["name"])

    def test_every_drop_code_has_a_label(self):
        for code in ("NO_TITLE", "NOT_TECH", "EXCLUDED", "OFF_TOPIC", "AGE", "UNTRUSTED", "UNCHECKED",
                     "UNRESOLVED", "HOST_MISMATCH", "SHORT_SUMMARY", "DUPLICATE"):
            self.assertIn(code, g.DROP_LABELS)

    def test_every_outcome_the_engine_can_report_has_a_text(self):
        for code in ("PUBLISHED", "ALL_LANES_EMPTY", "SOURCES_UNREACHABLE", "ALL_DUPLICATES",
                     "NO_CANDIDATES", "ALL_REJECTED", "NO_MATCH"):
            self.assertIn(code, g.OUTCOME_TEXT)


if __name__ == "__main__":
    unittest.main()
