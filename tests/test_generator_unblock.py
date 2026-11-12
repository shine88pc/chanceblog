"""Chance 생성기 막힘 해소 묶음(gfix: F 탈락 사유 공개 주석 + A 분야 이어가기·시드 시각 구간 + B 얇은 근거 뒤로 + C 요약 상한 + E 응답 형식·호출 시간 상한) 시험.
네트워크 없이 돈다(가짜 피드·가짜 Gemini·가짜 SDK).

배경(2026-11-04 조사 보고): 11-04 9시 슬롯이 두 번 모두 같은 후보 한 건(EU Digital Strategy 'Web Summit 2026' 행사 안내)만 모델에 보내고 탈락해 글이 없었다. 후보가 8건 있던 다른 분야로
넘어가지 않았고(A), 같은 날 같은 슬롯이면 분야 순서·후보가 같았고(A-b, D-34), 한 문장뿐인 근거가 먼저 갔고(B), 모델은 그 근거의 일부(300자)만 봤고(C),
탈락 사유가 공개 주석에 없었고(F), 호출에 형식 지정·시간 상한이 없었다(E, D-66). 이 시험은 그 고침을 고정한다. 글 품질 검사(분량·원문 링크·제목 유사도)는 그대로임도 함께 본다.
"""
import io
import json
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _bootstrap  # noqa: F401
import generator as g
from lock_helpers import pre_flip
from pipeline import llm

KST = g.KST
LINK = "https://www.reuters.com/a"
ORDER = ["technology", "science", "economy", "society", "culture", "daily_life"]
LABEL = {lane: g.EDITORIAL_LANES[lane]["label"] for lane in g.EDITORIAL_LANES}

# 진단 주석(cz_diag_annotations)에서 그대로 옮긴 'Web Summit 2026' 요약의 앞 300자(원래 403자 중 모델이 본 부분): 한 문장 + 사이트 틀 문구.
WEB_SUMMIT = ("Web Summit 2026 Anonymous (not verified) Tue, 11/03/2026 - 11:13 10 November 2026 - 12 November 2026 "
              "DG Connect will be at Web Summit in Lisbon from 10 to 12 November. "
              "Main link https://digital-strategy.ec.europa.eu/en/news/digitaleu-web-summit-2026-support… "
              "Related topics Cloud computing Start-ups")


def at(hour, minute=0, day=4, month=11):
    return datetime(2026, month, day, hour, minute, tzinfo=KST)


def run_captured(fn, *args, **kwargs):
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            value = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - 시험이 예외도 값으로 본다
            return exc, buf.getvalue()
    return value, buf.getvalue()


def thick(n=30):
    """증거가 두꺼운 요약(틀 문구 없음, 150자 이상)."""
    return "충분한 근거 문장입니다. " * n


def candidate(title, summary=None, link=LINK):
    return {"title": title, "source": "Reuters", "link": link, "publisher_domain": "www.reuters.com",
            "summary": thick() if summary is None else summary, "published": datetime.now(timezone.utc)}


def long_post(topic, link=LINK):
    """본문 검증(한국어 1000자·영어 1500자, 원문 링크 인용)을 통과하는 가짜 모델 응답."""
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


def thin_post(topic, link=LINK):
    """분량 검증(한국어 최소 1000자)에 못 미치는 가짜 모델 응답."""
    data = long_post(topic, link)
    front = "---\nlayout: post\ntitle: \"t\"\ncategory: \"c\"\ntags: []\n---\n\n"
    data["kr_content"] = front + "너무 짧은 본문입니다. " * 5 + f"\n\n[원문]({link})\n"
    return data


def skip(reason="근거가 부족합니다"):
    return {"skip": True, "reason": reason}


def warnings_of(out):
    return [line for line in out.splitlines() if line.startswith("::warning::")]


def notices_of(out):
    return [line for line in out.splitlines() if line.startswith("::notice::")]


@pre_flip
class FlowBase(unittest.TestCase):
    """DRY_RUN + 가짜 피드·가짜 모델·임시 폴더로 generate_blog_posts 전체 흐름을 돌린다(파일은 쓰지 않는다). 분야 순서는 ORDER 로 고정한다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name, value in (("DRY_RUN", True), ("STUB_GEMINI", False), ("STUB_UNSPLASH", True), ("API_KEY", None),
                            ("POSTS_DIR", root / "_posts"), ("HISTORY_FILE", root / "history.json")):
            patcher = mock.patch.object(g, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for patcher in (mock.patch.object(g, "now_kst", return_value=at(10, 12)),
                        mock.patch.object(g, "editorial_lane_order", lambda slot, history: list(ORDER)),
                        mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0})):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.histories = []

    def flow(self, lanes, responses, existing=(), **kwargs):
        """lanes: {분야: [후보…]}, responses: {후보 제목: JSON 글자 | dict | 예외}. 결과 묶음(value·report·out·fetch·calls·prompts)을 돌려준다."""
        fetch, prompts, calls = [], [], []

        def fake_fetch(editorial_lane=None, stats=None, deadline=None, clock=None):
            fetch.append(editorial_lane)
            found = list(lanes.get(editorial_lane, []))
            if stats is not None:
                stats.setdefault("sources", []).append({"name": str(editorial_lane), "fetched": 4, "kept": len(found),
                                                        "drops": {} if found else {"UNTRUSTED": 4}})
            return found

        def fake_prompt(item, recent_titles, category_hint="", allow_skip=False, editorial_lane=None):
            prompts.append((item["title"], editorial_lane))
            return item["title"]

        def fake_call(prompt):
            calls.append(prompt)
            value = responses[prompt]
            if isinstance(value, BaseException):
                raise value
            return SimpleNamespace(text=value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))

        report = {}
        kwargs.setdefault("slot", 9)
        kwargs.setdefault("allow_auto_topic", False)
        with mock.patch.object(g, "fetch_news_items", fake_fetch), mock.patch.object(g, "build_post_prompt", fake_prompt), \
                mock.patch.object(g, "call_gemini_with_fallback", fake_call), \
                mock.patch.object(g, "existing_titles", return_value=list(existing)), \
                mock.patch.object(g, "write_history", lambda history: self.histories.append(list(history))):
            value, out = run_captured(g.generate_blog_posts, report=report, **kwargs)
        return SimpleNamespace(value=value, report=report, out=out, fetch=fetch, calls=calls, prompts=prompts)


# ======================================================================================================================
# F — 탈락 사유를 공개 주석 한 줄과 실행 요약에
# ======================================================================================================================
class RejectAnnotationTest(FlowBase):
    def four_kinds(self, **kwargs):
        """한 분야 후보 4건이 각각 다른 이유로 탈락한다: 응답 형식·skip·제목 유사·본문 분량."""
        titles = ["첫째 기술 기사 알파", "둘째 기술 기사 베타 전혀 다른 소재", "셋째 기술 기사 감마 또 다른 것", "넷째 기술 기사 델타 마지막"]
        similar = long_post("셋째", LINK)
        existing = "인공지능 반도체 시장 전망과 한국 기업의 대응 전략 분석 보고서"
        similar["kr_title"] = existing
        responses = {titles[0]: "이건 JSON이 아닙니다", titles[1]: skip("가" * 200),
                     titles[2]: similar, titles[3]: thin_post("넷째")}
        with mock.patch.object(g, "MAX_ATTEMPTS", 4):
            return self.flow({"technology": [candidate(t) for t in titles]}, responses, existing=[existing], **kwargs), titles

    def test_every_kind_of_rejection_has_its_own_phrase_and_the_counts_are_listed(self):
        res, titles = self.four_kinds()
        self.assertIsNone(res.value)
        self.assertEqual(res.report["outcome"], "ALL_REJECTED")
        kinds = [r["kind"] for r in res.report["rejects"]]
        self.assertEqual(kinds, ["FORMAT", "SKIP", "SIMILAR", "BODY"])
        line = warnings_of(res.out)[-1]
        self.assertIn("후보 4건이 모두 탈락했습니다", line)
        self.assertIn("분야 1곳(기술·미래) · 후보 4건 시도", line)
        self.assertIn("건너뜀(skip) 1", line)
        self.assertIn("응답 형식 오류 1", line)
        self.assertIn("제목이 기존 글과 비슷 1", line)
        self.assertIn("본문 검증 탈락 1", line)
        for title in titles:                                                   # 후보마다 제목 앞 글자가 보인다
            self.assertIn(title[:g.REJECT_TITLE_CHARS], line)
        self.assertIn("응답 형식 오류: ValueError: JSON 객체를 찾을 수 없습니다", line)    # 모델이 쓴 글 조각은 싣지 않고 오류 종류만
        self.assertNotIn("이건 JSON이 아닙니다", line)
        self.assertIn("제목이 기존 글과 비슷: 유사도 1.00(기준 0.70)", line)
        self.assertRegex(line, r"본문 검증 탈락: KR 본문이 최소 편집 분량\(1000자\)에 미달합니다: \d+자")
        self.assertLessEqual(len(line), len("::warning::") + g.REJECT_LINE_MAX)

    def test_the_skip_reason_is_cut_to_its_first_80_characters(self):
        res, _ = self.four_kinds()
        line = warnings_of(res.out)[-1]
        self.assertIn("가" * g.REJECT_REASON_CHARS, line)
        self.assertNotIn("가" * (g.REJECT_REASON_CHARS + 1), line)
        self.assertEqual(g.REJECT_REASON_CHARS, 80)
        self.assertEqual(g.REJECT_TITLE_CHARS, 40)

    def test_the_counts_include_zero_for_kinds_that_did_not_happen(self):
        res = self.flow({"technology": [candidate("기술 기사")]}, {"기술 기사": skip("근거 부족")})
        line = warnings_of(res.out)[-1]
        self.assertIn("건너뜀(skip) 1 · 응답 형식 오류 0 · 제목이 기존 글과 비슷 0 · 본문 검증 탈락 0", line)

    def test_the_line_names_every_lane_tried_the_candidates_and_the_gemini_calls(self):
        with mock.patch.dict(g.GEMINI_CALLS, {"attempts": 3, "failed": 1}):
            res = self.flow({"technology": [candidate("기술 기사 하나")], "science": [candidate("과학 기사 하나 다른 이야기"), candidate("과학 기사 둘 또 다른 이야기")]},
                            {"기술 기사 하나": skip("a"), "과학 기사 하나 다른 이야기": skip("b"), "과학 기사 둘 또 다른 이야기": skip("c")})
        line = warnings_of(res.out)[-1]
        self.assertIn("분야 2곳(기술·미래, 과학·환경) · 후보 3건 시도 · Gemini 호출 3회(실패 1회)", line)
        self.assertIn("[기술·미래] 기술 기사 하나", line)
        self.assertIn("[과학·환경] 과학 기사 하나 다른 이야기", line)

    def test_a_scheduled_run_prints_exactly_one_reason_line_and_keeps_its_old_ending(self):
        res = self.flow({"technology": [candidate("기술 기사")]}, {"기술 기사": skip("근거 부족")}, allow_auto_topic=False)
        self.assertIsNone(res.value)
        self.assertEqual(len([w for w in warnings_of(res.out) if w.startswith("::warning::후보 ")]), 1)

    def test_a_manual_run_prints_the_reason_line_before_it_raises(self):
        res = self.flow({"technology": [candidate("기술 기사")]}, {"기술 기사": skip("근거 부족")}, allow_auto_topic=True, slot=None)
        self.assertIsInstance(res.value, RuntimeError)
        self.assertIn("후보가 모두 탈락", str(res.value))
        self.assertTrue(any(w.startswith("::warning::후보 1건이 모두 탈락했습니다") for w in warnings_of(res.out)))

    def test_a_manual_run_that_ends_with_an_error_still_leaves_the_reasons_in_the_step_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "summary.md"
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(target)}):
                res = self.flow({"technology": [candidate("기술 기사")]}, {"기술 기사": skip("근거 부족")}, allow_auto_topic=True, slot=None)
            text = target.read_text(encoding="utf-8")
        self.assertIsInstance(res.value, RuntimeError)
        self.assertIn("### Chance_Blog 후보 탈락 사유", text)
        self.assertIn("후보별 탈락 사유(분야 1곳 · 후보 1건 시도):", text)
        self.assertIn("모델이 건너뜀(skip): 근거 부족", text)

    def test_a_scheduled_run_writes_no_extra_summary_block_because_finish_run_writes_the_full_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "summary.md"
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(target)}):
                res = self.flow({"technology": [candidate("기술 기사")]}, {"기술 기사": skip("근거 부족")}, allow_auto_topic=False)
            self.assertIsNone(res.value)
            self.assertFalse(target.exists())

    def test_a_run_that_publishes_after_a_rejection_leaves_a_notice_with_the_reason(self):
        responses = {"첫째 기술 기사 알파": skip("근거가 한 문장뿐"), "둘째 기술 기사 베타 전혀 다른 소재": long_post("둘째")}
        res = self.flow({"technology": [candidate(t) for t in responses]}, responses)
        self.assertIsNotNone(res.value)
        self.assertEqual(res.report["outcome"], "PUBLISHED")
        notice = [n for n in notices_of(res.out) if "앞선 후보" in n]
        self.assertEqual(len(notice), 1)
        self.assertIn("앞선 후보 1건이 탈락한 뒤 2번째 후보로 글을 만들었습니다", notice[0])
        self.assertIn("모델이 건너뜀(skip): 근거가 한 문장뿐", notice[0])
        self.assertIn("분야 1곳(기술·미래) · 후보 2건 시도", notice[0])      # 탈락 1건이어도 시도한 후보는 2건이다
        self.assertFalse([w for w in warnings_of(res.out) if w.startswith("::warning::후보 ")])

    def test_a_first_candidate_success_leaves_no_reason_line_at_all(self):
        res = self.flow({"technology": [candidate("기술 기사")]}, {"기술 기사": long_post("기술")})
        self.assertIsNotNone(res.value)
        self.assertEqual(res.report["rejects"], [])
        self.assertNotIn("앞선 후보", res.out)
        self.assertNotIn("::warning::후보", res.out)

    def test_hostile_titles_and_reasons_cannot_start_a_workflow_command_or_a_second_line(self):
        hostile_title = "제목\n::error::가짜 제목\r##[group]x"
        hostile_reason = "사유\n::warning::가짜\n##[error]가짜 %0A::error::또"
        res = self.flow({"technology": [candidate(hostile_title)]}, {hostile_title: skip(hostile_reason)})
        commands = [line for line in res.out.splitlines() if line.lstrip().startswith(("::", "##["))]
        self.assertTrue(commands)
        for line in commands:
            self.assertTrue(line.startswith(("::warning::후보 ", "::notice::")), line)
        line = warnings_of(res.out)[-1]
        self.assertNotIn("##[", line)
        self.assertFalse(any(row.startswith("::error::") for row in res.out.splitlines()))
        self.assertNotIn("\r", line)

    def test_the_line_never_exceeds_the_limit_even_with_a_huge_report(self):
        rejects = [{"lane": "기술·미래", "title": "제" * 500, "kind": "BODY", "detail": "사" * 5000} for _ in range(200)]
        line = g.reject_summary_line({"outcome": "ALL_REJECTED", "rejects": rejects, "attempts": 200})
        self.assertLessEqual(len(line), g.REJECT_LINE_MAX)
        self.assertEqual(g.REJECT_LINE_MAX, 3500)

    def test_a_small_limit_is_honoured_and_cuts_after_the_sanitising(self):
        with mock.patch.object(g, "REJECT_LINE_MAX", 120):
            res = self.flow({"technology": [candidate("기술 기사")]}, {"기술 기사": skip("근거 부족" * 40)})
        self.assertLessEqual(len(warnings_of(res.out)[-1]), len("::warning::") + 120)

    def test_keys_tokens_and_url_query_strings_never_reach_the_line_or_the_summary(self):
        key = "my-secret-key-0123456789"
        aiza = "AIza" + "B" * 35
        reason = f"본 키 {key} 와 {aiza} 그리고 https://example.com/a?token=abc123&x=1#frag 와 token=zzz999"
        with mock.patch.object(g, "API_KEY", key):
            res = self.flow({"technology": [candidate("기술 기사 https://example.com/t?secret=hunter2")]},
                            {"기술 기사 https://example.com/t?secret=hunter2": skip(reason)})
            summary = g.render_run_summary("schedule", at(10, 12), 9, res.report)
        line = warnings_of(res.out)[-1]
        for text in (line, summary):
            for leaked in (key, aiza, "token=abc123", "x=1", "#frag", "token=zzz999", "secret=hunter2", "hunter2"):
                self.assertNotIn(leaked, text)
        self.assertIn("https://example.com/a", line)          # 질의만 떼고 주소 본체는 남는다

    def test_a_key_that_straddles_the_cut_is_masked_before_cutting(self):
        key = "straddling-secret-key-9876543210"
        with mock.patch.object(g, "API_KEY", key):
            record = g._reject_record("technology", "기술 기사", "SKIP", "가" * (g.REJECT_REASON_CHARS - 6) + key)
        self.assertNotIn("straddl", record["detail"])
        self.assertNotIn(key[:8], record["detail"])
        self.assertLessEqual(len(record["detail"]), g.REJECT_REASON_CHARS)

    def test_the_run_summary_lists_each_rejected_candidate(self):
        res, titles = self.four_kinds()
        summary = g.render_run_summary("schedule", at(10, 12), 9, res.report)
        self.assertIn("- 후보별 탈락 사유(분야 1곳 · 후보 4건 시도):", summary)
        for kind in g.REJECT_LABELS.values():
            self.assertIn(kind, summary)
        self.assertIn("- 후보 탈락 2건(본문 검증·응답 형식)", summary)      # 기존 줄은 그대로다

    def test_the_run_summary_detail_is_safe_markdown(self):
        report = {"outcome": "ALL_REJECTED", "lanes": [], "attempts": 1,
                  "rejects": [{"lane": "기술·미래", "title": "제목 | 열 [x](http://evil.example) `코드` <img src=x>", "kind": "SKIP",
                               "detail": "사유 | 표\n# 가짜 제목 [링크](http://evil.example)"}]}
        text = g.render_run_summary("schedule", at(10), 9, report)
        rows = [row for row in text.splitlines() if row.startswith("  - ")]
        self.assertEqual(len(rows), 1)
        for ch in "|`<>[]":
            self.assertNotIn(ch, rows[0])
        self.assertNotIn("\n# 가짜 제목", text)

    def test_a_report_without_reject_records_prints_nothing_new(self):
        text = g.render_run_summary("schedule", at(10), 9, {"outcome": "ALL_LANES_EMPTY", "lanes": []})
        self.assertNotIn("후보별 탈락 사유", text)
        self.assertEqual(g.reject_summary_line({}), "")
        self.assertEqual(g.reject_detail_lines({"rejects": []}), [])

    def test_finish_run_puts_the_detail_into_the_step_summary(self):
        res, _ = self.four_kinds()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "summary.md"
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(target)}):
                run_captured(g.finish_run, None, res.report, "schedule", at(10, 12), 9)
            text = target.read_text(encoding="utf-8")
        self.assertIn("후보별 탈락 사유", text)
        self.assertIn("ALL_REJECTED", text)

    def test_format_error_kind_keeps_only_the_error_name_and_the_fixed_phrase(self):
        self.assertEqual(g._format_error_kind(ValueError("JSON 객체를 찾을 수 없습니다: 모델이 쓴 긴 글 ::error::")),
                         "ValueError: JSON 객체를 찾을 수 없습니다")
        self.assertEqual(g._format_error_kind(ValueError("Gemini 응답이 비어 있습니다.")), "ValueError: Gemini 응답이 비어 있습니다.")
        try:
            json.loads('{"a": 1,}')
        except json.JSONDecodeError as exc:
            self.assertTrue(g._format_error_kind(exc).startswith("JSONDecodeError: "))

    def test_the_lanes_footer_of_the_summary_also_covers_the_rejection_case(self):
        lane = {"lane": "technology", "label": "기술·미래", "sources": 1, "failed_sources": 0, "fetched": 4, "passed": 1,
                "candidates": 1, "drops": {}}
        text = g.render_run_summary("schedule", at(10, 12), 9, {"outcome": "ALL_REJECTED", "lanes": [lane, dict(lane, label="과학·환경")]})
        self.assertIn("분야 2개를 차례로 시도했습니다(처음 추첨된 분야에 후보가 없거나 그 후보가 모두 탈락하면 다음 분야).", text)

    def test_the_new_regexes_and_masks_stay_fast_on_hostile_input(self):
        hostile = ["A" * 300_000, "Anonymous (not verified) " * 8000, "Main link " * 20000, "http://" + "a?" * 100_000,
                   "https://" + "x" * 300_000 + "?" + "y" * 300_000, " " * 300_000 + "Related topics", "\n" * 200_000]
        started = time.monotonic()
        for text in hostile:
            g.evidence_chars(text)
            g._public_text(text, 80)
        self.assertLess(time.monotonic() - started, 10)

    def test_a_url_fragment_without_a_query_is_cut_too(self):
        self.assertEqual(g._public_text("https://e.com/p#frag-secret 끝", 80), "https://e.com/p 끝")
        self.assertEqual(g._public_text("https://e.com/p?a=1#frag-secret 끝", 80), "https://e.com/p 끝")

    def test_public_text_masks_then_folds_then_cuts(self):
        self.assertEqual(g._public_text("a\n\nb", 10), "a b")
        self.assertFalse(g._public_text("::error::x", 50).startswith("::"))
        self.assertNotIn("##[", g._public_text("##[error]x", 50))
        self.assertEqual(g._public_text("https://e.com/p?a=1&b=2#c 끝", 50), "https://e.com/p 끝")
        self.assertEqual(len(g._public_text("가" * 500, 80)), 80)


# ======================================================================================================================
# A — 한 분야의 후보가 모두 탈락하면 다음 분야로 계속한다
# ======================================================================================================================
class NextLaneTest(FlowBase):
    def test_a_first_lane_whose_candidates_are_all_rejected_is_followed_by_the_next_lane(self):
        responses = {"기술 행사 안내 한 건": skip("근거가 한 문장뿐"), "과학 기사 하나 다른 이야기": long_post("과학")}
        res = self.flow({"technology": [candidate("기술 행사 안내 한 건")],
                         "science": [candidate("과학 기사 하나 다른 이야기"), candidate("과학 기사 둘 또 다른 이야기")]}, responses)
        self.assertIsNotNone(res.value)
        self.assertEqual(res.report["outcome"], "PUBLISHED")
        self.assertEqual(res.calls, ["기술 행사 안내 한 건", "과학 기사 하나 다른 이야기"])
        self.assertEqual(res.prompts, [("기술 행사 안내 한 건", "technology"), ("과학 기사 하나 다른 이야기", "science")])
        self.assertEqual(res.report["lane"], "science")
        self.assertEqual(res.report["lane_label"], "과학·환경")
        self.assertEqual(self.histories[-1][-1]["lane"], "science")              # 이력에는 글이 실제로 나온 분야가 쓰인다
        self.assertEqual([lane["lane"] for lane in res.report["lanes"]], ["technology", "science"])
        self.assertEqual(res.fetch, ["technology", "science"])                    # 그 뒤 분야는 읽지 않는다
        self.assertEqual(res.report["rejects"][0]["lane"], "기술·미래")
        self.assertIn("::notice::'기술·미래' 분야의 후보가 모두 탈락해 '과학·환경' 분야를 이어서 시도합니다.", res.out)
        self.assertNotIn("후보가 없어", res.out)                                   # 후보가 없어서가 아니므로 옛 '대체' 문구는 쓰지 않는다
        done = [n for n in notices_of(res.out) if n.startswith("::notice::앞선 후보")]
        self.assertEqual(len(done), 1)
        self.assertIn("분야 2곳(기술·미래, 과학·환경) · 후보 2건 시도", done[0])      # 글이 나온 분야도 시도한 분야에 들어간다

    def test_the_old_substitution_notice_is_unchanged_when_the_first_lane_was_simply_empty(self):
        res = self.flow({"science": [candidate("과학 기사 하나")]}, {"과학 기사 하나": long_post("과학")})
        self.assertIsNotNone(res.value)
        self.assertIn("::notice::'기술·미래' 분야에 후보가 없어 '과학·환경' 분야로 대체했습니다.", res.out)
        self.assertNotIn("이어서 시도", res.out)

    def test_the_total_number_of_attempts_is_capped_across_lanes(self):
        titles = ["과학 기사 일", "과학 기사 이 다른 소재", "과학 기사 삼 또 다른 소재", "과학 기사 사 마지막 소재"]
        responses = {"기술 기사 하나": skip("a"), **{t: skip("b") for t in titles}}
        res = self.flow({"technology": [candidate("기술 기사 하나")], "science": [candidate(t) for t in titles]}, responses)
        self.assertIsNone(res.value)
        self.assertEqual(res.report["outcome"], "ALL_REJECTED")
        self.assertEqual(len(res.calls), g.MAX_ATTEMPTS)                           # 1(기술) + 2(과학) = 3
        self.assertEqual(res.calls, ["기술 기사 하나", titles[0], titles[1]])
        self.assertEqual(res.report["attempts"], g.MAX_ATTEMPTS)
        self.assertNotIn("economy", res.fetch)                                      # 상한에 닿았으면 다음 분야를 읽지도 않는다

    def test_a_first_lane_that_uses_up_every_attempt_stops_the_search(self):
        titles = ["기술 기사 일", "기술 기사 이 다른 소재", "기술 기사 삼 또 다른 소재"]
        res = self.flow({"technology": [candidate(t) for t in titles], "science": [candidate("과학 기사 하나")]},
                        {**{t: skip("a") for t in titles}, "과학 기사 하나": long_post("과학")})
        self.assertIsNone(res.value)
        self.assertEqual(res.calls, titles)
        self.assertEqual(res.fetch, ["technology"])

    def test_the_cap_is_read_at_run_time(self):
        with mock.patch.object(g, "MAX_ATTEMPTS", 1):
            res = self.flow({"technology": [candidate("기술 기사 하나")], "science": [candidate("과학 기사 하나")]},
                            {"기술 기사 하나": skip("a"), "과학 기사 하나": long_post("과학")})
        self.assertIsNone(res.value)
        self.assertEqual(res.calls, ["기술 기사 하나"])
        self.assertEqual(res.fetch, ["technology"])

    def test_the_search_budget_also_counts_the_time_spent_calling_the_model(self):
        def slow_skip(prompt):
            time.sleep(0.15)
            return skip("느린 응답")

        with mock.patch.object(g, "LANE_SEARCH_BUDGET_SECONDS", 0.05):
            res = self.slow_flow(slow_skip)
        self.assertIsNone(res.value)
        self.assertEqual(res.report["outcome"], "ALL_REJECTED")                    # 후보는 있었으니 NO_CANDIDATES 가 아니다
        self.assertTrue(res.report["budget_exceeded"])
        self.assertIn("::warning::분야 대체 시도를 시간 상한", res.out)
        self.assertEqual(res.fetch, ["technology"])

    def slow_flow(self, slow):
        fetch, calls = [], []

        def fake_fetch(editorial_lane=None, stats=None, deadline=None, clock=None):
            fetch.append(editorial_lane)
            found = [candidate("기술 기사 하나")] if editorial_lane == "technology" else [candidate("과학 기사 하나")]
            stats.setdefault("sources", []).append({"name": editorial_lane, "fetched": 1, "kept": 1, "drops": {}})
            return found

        def fake_call(prompt):
            calls.append(prompt)
            return SimpleNamespace(text=json.dumps(slow(prompt), ensure_ascii=False))

        report = {}
        with mock.patch.object(g, "fetch_news_items", fake_fetch), \
                mock.patch.object(g, "build_post_prompt", lambda item, *a, **k: item["title"]), \
                mock.patch.object(g, "call_gemini_with_fallback", fake_call), \
                mock.patch.object(g, "existing_titles", return_value=[]):
            value, out = run_captured(g.generate_blog_posts, slot=9, allow_auto_topic=False, report=report)
        return SimpleNamespace(value=value, report=report, out=out, fetch=fetch, calls=calls)

    def test_candidates_that_all_fail_with_empty_later_lanes_are_all_rejected_not_all_lanes_empty(self):
        res = self.flow({"technology": [candidate("기술 기사 하나")]}, {"기술 기사 하나": skip("a")})
        self.assertIsNone(res.value)
        self.assertEqual(res.report["outcome"], "ALL_REJECTED")
        self.assertEqual(len(res.report["lanes"]), len(g.EDITORIAL_LANES))         # 나머지 분야도 끝까지 읽어 본 뒤에 끝난다
        self.assertEqual(res.out.count("[SKIP] code=LANE_EMPTY"), len(g.EDITORIAL_LANES) - 1)
        self.assertEqual(res.report["lane"], "technology")
        self.assertFalse(any(line.startswith("::error::") for line in res.out.splitlines()))

    def test_no_candidate_anywhere_keeps_every_old_outcome(self):
        res = self.flow({}, {})
        self.assertEqual(res.report["outcome"], "ALL_LANES_EMPTY")
        self.assertEqual(res.report["lane"], ORDER[0])                              # 후보가 없으면 처음 추첨된 분야 그대로
        self.assertEqual(res.report["attempts"], 0)
        self.assertEqual(res.report["rejects"], [])
        self.assertIn("쓸 만한 새 기사가 없습니다", res.out)
        self.assertEqual(res.calls, [])

    def test_a_manual_run_continues_to_the_next_lane_too_and_still_raises_when_all_fail(self):
        res = self.flow({"technology": [candidate("기술 기사 하나")], "science": [candidate("과학 기사 하나 다른 이야기")]},
                        {"기술 기사 하나": skip("a"), "과학 기사 하나 다른 이야기": long_post("과학")}, allow_auto_topic=True, slot=None)
        self.assertIsNotNone(res.value)
        self.assertEqual(res.report["lane"], "science")
        res = self.flow({"technology": [candidate("기술 기사 하나")], "science": [candidate("과학 기사 하나 다른 이야기")]},
                        {"기술 기사 하나": skip("a"), "과학 기사 하나 다른 이야기": skip("b")}, allow_auto_topic=True, slot=None)
        self.assertIsInstance(res.value, RuntimeError)
        self.assertEqual(res.calls, ["기술 기사 하나", "과학 기사 하나 다른 이야기"])
        self.assertEqual(res.report["outcome"], "ALL_REJECTED")

    def test_a_requested_topic_never_continues_to_other_lanes(self):
        topic = "양자컴퓨터 상용화 일정"
        res = self.flow({ORDER[0]: [candidate(topic)], "science": [candidate("과학 기사 하나")]}, {topic: skip("a")},
                        topic_override=topic, slot=None, allow_auto_topic=True)
        self.assertIsInstance(res.value, RuntimeError)
        self.assertEqual(res.fetch, [ORDER[0]])
        self.assertEqual(res.calls, [topic])

    def test_a_gemini_outage_still_fails_the_run_instead_of_moving_on(self):
        res = self.flow({"technology": [candidate("기술 기사 하나")], "science": [candidate("과학 기사 하나")]},
                        {"기술 기사 하나": RuntimeError("모든 Gemini 모델 호출 실패"), "과학 기사 하나": long_post("과학")})
        self.assertIsInstance(res.value, RuntimeError)
        self.assertEqual(res.calls, ["기술 기사 하나"])
        self.assertEqual(res.fetch, ["technology"])


class IterCandidateLanesTest(unittest.TestCase):
    """제너레이터 계약: 후보가 나온 분야마다 하나씩, 다음을 요청받기 전에는 다음 분야를 읽지 않는다. collect_candidates 는 그 첫 항목이다."""

    def setUp(self):
        self.read = []
        self.results = {}

    def fake_pick(self, titles, allow_auto_topic=True, editorial_lane=None, stats=None, **kwargs):
        self.read.append(editorial_lane)
        found = self.results.get(editorial_lane, [])
        stats["sources"] = [{"name": editorial_lane, "fetched": 3, "kept": len(found), "drops": {} if found else {"UNTRUSTED": 3}}]
        return found

    def test_it_reads_one_lane_at_a_time_and_ends_when_the_order_is_used_up(self):
        self.results = {"economy": [candidate("a")], "science": [candidate("b")]}
        report = {"lanes": []}
        with mock.patch.object(g, "pick_topic_candidates", self.fake_pick), redirect_stdout(io.StringIO()) as out:
            gen = g.iter_candidate_lanes([], False, ["economy", "culture", "science", "society"], report)
            lane, found = next(gen)
            self.assertEqual((lane, self.read), ("economy", ["economy"]))
            lane, found = next(gen)
            self.assertEqual((lane, self.read), ("science", ["economy", "culture", "science"]))
            self.assertIn("::notice::'경제·일' 분야의 후보가 모두 탈락해 '과학·환경' 분야를 이어서 시도합니다.", out.getvalue())
            with self.assertRaises(StopIteration):
                next(gen)
        self.assertEqual(self.read, ["economy", "culture", "science", "society"])
        self.assertFalse(report["sources_unreachable"])

    def test_collect_candidates_is_the_first_item_and_leaves_the_rest_unread(self):
        self.results = {"economy": [candidate("a")], "science": [candidate("b")]}
        with mock.patch.object(g, "pick_topic_candidates", self.fake_pick), redirect_stdout(io.StringIO()):
            found, lane = g.collect_candidates([], False, ["economy", "science"], {"lanes": []})
        self.assertEqual((lane, len(found), self.read), ("economy", 1, ["economy"]))

    def test_nothing_found_gives_the_first_lane_and_no_items(self):
        with mock.patch.object(g, "pick_topic_candidates", self.fake_pick), redirect_stdout(io.StringIO()):
            found, lane = g.collect_candidates([], False, ["economy", "science"], {"lanes": []})
        self.assertEqual((found, lane), ([], "economy"))


# ======================================================================================================================
# A-b — 같은 슬롯 창 안에서 시도마다 분야 순서가 달라진다
# ======================================================================================================================
@pre_flip
class LaneOrderBucketTest(unittest.TestCase):
    HISTORY = [{"date": f"2026-10-{20 + i // 2}", "topic": f"t{i}", "lane": ORDER[i % 6], "slot": 9 if i % 2 == 0 else 18}
               for i in range(25)]

    def order(self, now, slot=9, history=None):
        return g.editorial_lane_order(slot, self.HISTORY if history is None else history, now=now)

    def test_the_default_is_ten_minute_buckets(self):
        self.assertEqual(g.LANE_ORDER_BUCKET_MINUTES, 10)

    def test_different_times_in_one_slot_window_give_different_orders_and_first_lanes(self):
        times = [at(9 + minute // 60, minute % 60) for minute in range(0, 9 * 60, 10)]      # 09:00~17:50 = 9시 슬롯 창
        self.assertEqual(len(times), 54)
        orders = {tuple(self.order(t)) for t in times}
        firsts = {self.order(t)[0] for t in times}
        self.assertGreater(len(orders), 10)
        self.assertGreater(len(firsts), 3)        # 첫 분야가 달라질 수 있다

    def test_the_incident_pair_gets_different_orders(self):
        """11-04 의 10:24·12:19 실행: 같은 날·같은 슬롯·같은 이력이었는데 옛 시드는 같은 순서를 냈다."""
        self.assertNotEqual(self.order(at(10, 24)), self.order(at(12, 19)))
        with mock.patch.object(g, "LANE_ORDER_BUCKET_MINUTES", 0):
            self.assertEqual(self.order(at(10, 24)), self.order(at(12, 19)))        # 시각 항목을 끄면 옛 동작(같은 순서)

    def test_the_same_bucket_gives_the_same_order_and_the_next_bucket_has_another_seed(self):
        self.assertEqual(self.order(at(10, 20)), self.order(at(10, 29)))
        self.assertEqual(g._lane_order_bucket(at(10, 20)), g._lane_order_bucket(at(10, 29)))
        self.assertNotEqual(g._lane_order_bucket(at(10, 29)), g._lane_order_bucket(at(10, 30)))
        self.assertNotEqual(g._lane_order_bucket(at(23, 59)), g._lane_order_bucket(at(0, 0)))

    def test_the_bucket_length_is_read_at_run_time(self):
        with mock.patch.object(g, "LANE_ORDER_BUCKET_MINUTES", 30):
            self.assertEqual(g._lane_order_bucket(at(10, 0)), g._lane_order_bucket(at(10, 29)))
            self.assertNotEqual(g._lane_order_bucket(at(10, 29)), g._lane_order_bucket(at(10, 30)))

    def test_zero_turns_the_time_item_off_and_gives_the_old_seed(self):
        with mock.patch.object(g, "LANE_ORDER_BUCKET_MINUTES", 0):
            self.assertEqual(g._lane_order_bucket(at(10, 24)), "")
        with mock.patch.object(g, "LANE_ORDER_BUCKET_MINUTES", -5):
            self.assertEqual(g._lane_order_bucket(at(10, 24)), "")

    def test_now_is_injectable_and_defaults_to_the_kst_clock(self):
        with mock.patch.object(g, "now_kst", return_value=at(10, 24)):
            self.assertEqual(g.editorial_lane_order(9, self.HISTORY), self.order(at(10, 24)))
            self.assertEqual(g.choose_editorial_lane(9, self.HISTORY), self.order(at(10, 24))[0])
        self.assertEqual(g.editorial_lane_order(9, self.HISTORY, now=at(12, 19)), self.order(at(12, 19)))

    def test_every_order_is_a_permutation_of_all_lanes(self):
        for minute in range(0, 24 * 60, 10):
            with self.subTest(minute=minute):
                self.assertEqual(sorted(self.order(at(minute // 60, minute % 60))), sorted(g.EDITORIAL_LANES))

    def test_the_balance_against_repeating_the_last_lanes_does_not_depend_on_the_time(self):
        """이력의 마지막이 technology·그 앞이 culture 이면 어느 시각 구간에서든 두 분야는 첫 분야로 드물게 뽑히고(직전 ×0.25·그 전 ×0.6) 최근에 안 쓴 분야는 고르게 뽑힌다.
        3일 × 슬롯 2개 × 하루 144구간 = 864번을 뽑아 비율을 본다(이론값: technology 4.1%·culture 9.9%·economy 4.4%·나머지 셋 각 약 27%)."""
        lanes = ["economy"] * 8 + ["culture", "technology"]
        history = [{"date": "2026-11-0%d" % (1 + i // 2), "topic": f"t{i}", "lane": lane} for i, lane in enumerate(lanes)]
        firsts = {lane: 0 for lane in g.EDITORIAL_LANES}
        for day in (2, 3, 4):
            for slot in (9, 18):
                for minute in range(0, 24 * 60, 10):
                    firsts[self.order(at(minute // 60, minute % 60, day=day), slot=slot, history=history)[0]] += 1
        total = sum(firsts.values())
        self.assertEqual(total, 864)
        share = {lane: count / total for lane, count in firsts.items()}
        self.assertLess(share["technology"], 0.06)                     # 직전 분야(×0.25)
        self.assertLess(share["culture"], 0.13)                        # 그 전 분야(×0.6)
        self.assertGreater(share["culture"], share["technology"])
        self.assertLess(share["economy"], 0.08)                        # 최근 12편에 8번 나온 분야
        for lane in ("science", "society", "daily_life"):
            self.assertGreater(share[lane], 0.20)

    def test_generate_blog_posts_calls_the_order_with_the_two_old_arguments_only(self):
        """다른 시험이 editorial_lane_order 를 (slot, history) 두 인자짜리 함수로 바꿔 끼운다 — 호출 모양이 바뀌면 그 시험이 깨진다."""
        seen = []

        def fake(slot, history):
            seen.append((slot, len(history)))
            return list(ORDER)

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.multiple(g, DRY_RUN=True, STUB_GEMINI=True, STUB_UNSPLASH=True, POSTS_DIR=Path(tmp) / "p",
                                    HISTORY_FILE=Path(tmp) / "h.json"), \
                mock.patch.object(g, "editorial_lane_order", fake), \
                mock.patch.object(g, "fetch_news_items", lambda editorial_lane=None, stats=None, deadline=None, clock=None: []):
            run_captured(g.generate_blog_posts, slot=9, allow_auto_topic=False, report={})
        self.assertEqual(seen, [(9, 0)])


# ======================================================================================================================
# B — 근거가 한 문장뿐인 후보는 뒤로
# ======================================================================================================================
class ThinEvidenceTest(FlowBase):
    def pick(self, items, stats=None):
        with mock.patch.object(g, "fetch_news_items", return_value=items):
            return run_captured(g.pick_topic_candidates, [], True, "technology", stats=stats)

    def test_the_web_summit_sample_counts_as_one_sentence_although_its_raw_length_is_not(self):
        self.assertEqual(len(WEB_SUMMIT), 299)
        self.assertGreaterEqual(len(WEB_SUMMIT), g.THIN_EVIDENCE_CHARS)               # 글자 수만 보면 두꺼워 보인다
        self.assertLess(g.evidence_chars(WEB_SUMMIT), g.THIN_EVIDENCE_CHARS)           # 틀 문구를 빼면 한 문장이다
        self.assertEqual(g.evidence_chars(WEB_SUMMIT), 118)

    def test_the_frame_head_tail_and_urls_are_not_evidence(self):
        self.assertEqual(g.evidence_chars("가나다 라마바"), 7)
        self.assertEqual(g.evidence_chars("  가나다 \n\n 라마바  "), 7)                  # 공백은 접어서 센다
        self.assertEqual(g.evidence_chars(None), 0)
        self.assertEqual(g.evidence_chars(""), 0)
        self.assertEqual(g.evidence_chars("사실 문장. Anonymous (not verified) Wed, 01/02/2026 - 09:05 이어지는 문장"), len("사실 문장. 이어지는 문장"))
        self.assertEqual(g.evidence_chars("사실 문장. Main link https://e.com/a 뒤의 글은 틀"), len("사실 문장."))
        self.assertEqual(g.evidence_chars("사실 문장. Related topics Cloud 뒤의 글은 틀"), len("사실 문장."))
        self.assertEqual(g.evidence_chars("사실 https://e.com/a?x=1 문장"), len("사실 문장"))

    def test_the_frame_words_are_matched_case_sensitively_so_prose_is_not_cut(self):
        text = "The main link between prices and wages is weak, and related topics such as rents matter too."
        self.assertEqual(g.evidence_chars(text), len(text))

    def test_the_boundary_is_150_characters(self):
        self.assertEqual(g.THIN_EVIDENCE_CHARS, 150)
        self.assertEqual(g.evidence_chars("가" * 150), 150)
        items = [candidate("얇은 후보 일", "가" * 149), candidate("두꺼운 후보 이 다른 소재", "가" * 150)]
        picked, _ = self.pick(items)
        self.assertEqual([it["title"] for it in picked], ["두꺼운 후보 이 다른 소재", "얇은 후보 일"])

    def test_thick_candidates_come_first_and_each_group_keeps_its_own_order(self):
        thin_a, thick_a, thin_b, thick_b, thick_c = (candidate("후보 가", "짧은 요약"), candidate("후보 나 다른 이야기"),
                                                     candidate("후보 다 또 다른", "짧은 요약"), candidate("후보 라 이건 다른", None),
                                                     candidate("후보 마 그리고 다른"))
        with mock.patch.object(g, "MAX_ATTEMPTS", 5):
            picked, out = self.pick([thin_a, thick_a, thin_b, thick_b, thick_c])
        self.assertEqual(picked, [thick_a, thick_b, thick_c, thin_a, thin_b])
        self.assertIn("근거가 얇은 후보 2건(증거 150자 미만)은 시도 순서를 뒤로 미룸", out)

    def test_the_first_three_are_the_thick_ones_when_there_are_enough(self):
        items = [candidate("후보 가", "짧은 요약")] + [candidate(f"후보 {n} 서로 다른 소재 {n * 7}") for n in "나다라"]
        picked, _ = self.pick(items)
        self.assertEqual([it["title"] for it in picked], [it["title"] for it in items[1:]])

    def test_only_thin_candidates_are_still_tried_in_their_old_order_without_any_note(self):
        items = [candidate("후보 가", "짧은 요약"), candidate("후보 나 다른 이야기", "짧은 요약 둘")]
        picked, out = self.pick(items)
        self.assertEqual(picked, items)
        self.assertNotIn("뒤로 미룸", out)

    def test_normal_candidates_keep_their_order_and_identity(self):
        items = [candidate(f"후보 {n} 서로 다른 소재 {n * 7}") for n in "가나다라"]
        picked, out = self.pick(items)
        self.assertEqual(len(picked), g.MAX_ATTEMPTS)
        self.assertTrue(all(a is b for a, b in zip(picked, items)))
        self.assertNotIn("뒤로 미룸", out)

    def test_a_thin_candidate_that_was_thin_only_by_its_frame_text_goes_behind_a_short_plain_one(self):
        summit = candidate("Web Summit 2026", WEB_SUMMIT)
        plain = candidate("평범한 후보 이야기", "가" * 160)
        picked, _ = self.pick([summit, plain])
        self.assertEqual(picked, [plain, summit])

    def test_stats_count_the_thin_candidates_among_the_picked(self):
        items = [candidate("후보 가", "짧은 요약"), candidate("후보 나 다른 이야기"), candidate("후보 다 또 다른", "짧은 요약")]
        stats = {}
        self.pick(items, stats)
        self.assertEqual(stats["thin"], 2)
        self.assertEqual(stats["candidates"], 3)

    def test_duplicates_are_still_removed_after_the_reordering(self):
        items = [candidate("이미 쓴 제목입니다 반도체", "짧은 요약"), candidate("새로운 주제 하나")]
        stats = {}
        with mock.patch.object(g, "fetch_news_items", return_value=items):
            picked, _ = run_captured(g.pick_topic_candidates, ["이미 쓴 제목입니다 반도체"], True, "technology", stats=stats)
        self.assertEqual([it["title"] for it in picked], ["새로운 주제 하나"])
        self.assertEqual(stats["duplicates"], 1)

    def test_the_summary_that_goes_to_the_model_is_not_touched(self):
        item = candidate("Web Summit 2026", WEB_SUMMIT)
        picked, _ = self.pick([item])
        self.assertEqual(picked[0]["summary"], WEB_SUMMIT)

    def test_the_thick_candidate_is_the_first_one_sent_to_the_model(self):
        summit, nasa = candidate("Web Summit 2026 행사 안내", WEB_SUMMIT), candidate("NASA 탐사선 소식 전혀 다른 소재")
        responses = {summit["title"]: skip("근거가 한 문장뿐"), nasa["title"]: long_post("NASA")}
        res = self.flow({"technology": [summit, nasa]}, responses)
        self.assertEqual(res.calls[0], nasa["title"])
        self.assertEqual(res.report["outcome"], "PUBLISHED")
        self.assertEqual(res.report["rejects"], [])
        self.assertEqual(len(res.calls), 1)                                              # 얇은 후보에는 호출을 쓰지 않았다


# ======================================================================================================================
# C — 모델에 넘기는 요약 상한
# ======================================================================================================================
def feed(description, title="기사 제목 입니다"):
    return (f"<?xml version='1.0'?><rss><channel><item><title>{title}</title><link>https://www.federalreserve.gov/a</link>"
            f"<pubDate>{format_datetime(datetime.now(timezone.utc))}</pubDate><description>{description}</description></item>"
            "</channel></rss>").encode("utf-8")


@pre_flip
class SummaryLimitTest(unittest.TestCase):
    def test_the_default_limit_is_1800_and_far_above_the_old_300(self):
        self.assertEqual(g.SUMMARY_MAX_CHARS, 1800)

    def test_a_long_feed_text_goes_in_up_to_the_limit(self):
        limit = g.SUMMARY_MAX_CHARS
        for size, expected in ((limit - 1, limit - 1), (limit, limit), (limit + 1, limit), (limit * 3, limit)):
            with self.subTest(size=size):
                self.assertEqual(len(g.parse_feed(feed("가" * size))[0]["summary"]), expected)

    def test_the_limit_is_read_at_call_time(self):
        with mock.patch.object(g, "SUMMARY_MAX_CHARS", 500):
            self.assertEqual(len(g.parse_feed(feed("가" * 900))[0]["summary"]), 500)

    def test_an_explicit_limit_overrides_the_default_both_ways(self):
        self.assertEqual(len(g.parse_feed(feed("가" * 900), summary_limit=300)[0]["summary"]), 300)
        self.assertEqual(len(g.parse_feed(feed("가" * 5000), summary_limit=3000)[0]["summary"]), 3000)

    def test_titles_and_the_other_feed_fields_keep_their_own_limits(self):
        item = g.parse_feed(feed("요약", title="제" * 500))[0]
        self.assertEqual(len(item["title"]), 300)

    def fetch_with(self, sources):
        feeds = {src["url"]: feed("가" * 1500, title=f"기사 제목 {src['name']}") for src in sources}

        class Response:
            def __init__(self, data):
                self.data = data

            def read(self, *args):
                return self.data

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with mock.patch.object(g, "NEWS_SOURCES", sources), \
                mock.patch.object(g.urllib.request, "urlopen", lambda req, timeout=0: Response(feeds[req.full_url])):
            value, _ = run_captured(g.fetch_news_items, "economy")
        return value

    def test_a_source_can_pin_its_own_limit_and_the_others_follow_the_default(self):
        sources = [{"name": "고정 소스", "lane": "economy", "url": "https://feed.test/pinned", "summary_max_chars": 300},
                   {"name": "기본 소스", "lane": "economy", "url": "https://feed.test/default"}]
        items = self.fetch_with(sources)
        self.assertEqual(sorted(len(it["summary"]) for it in items), [300, 1500])

    # R-119 A(2026-11-05): 미 FTC 보도자료는 약관 때문이 아니라 요약이 보도자료 전문 수준(중앙 3,520자)이라 원문 문장을 베끼지 않게 1,500자로 고정한다. 다른 소스는 그대로 기본값이다.
    PINNED_SUMMARY_CAPS = {"FTC · press (consumer protection)": 1500}

    def test_every_allowed_source_follows_the_default_after_the_terms_review(self):
        """2026-11-04 약관 점검(terms 기록 기준): 읽는 소스(allowed) 모두 입력 분량 제한 조항이 없어 소스별 고정이 없다. 약관이 더 짧은 발췌만 허락하면 그 소스에 summary_max_chars 를 적고 이 시험을 고친다.
        예외는 PINNED_SUMMARY_CAPS 에 적은 소스뿐이고(값까지 못박는다) 나머지는 고정이 없어야 한다."""
        for src in g.NEWS_SOURCES:
            with self.subTest(source=src["name"]):
                self.assertIn(src["terms"]["status"], {"allowed", "pending"})
                if src["name"] in self.PINNED_SUMMARY_CAPS:
                    self.assertEqual(src["summary_max_chars"], self.PINNED_SUMMARY_CAPS[src["name"]])
                else:
                    self.assertNotIn("summary_max_chars", src)
        self.assertEqual({s["name"] for s in g.NEWS_SOURCES if "summary_max_chars" in s}, set(self.PINNED_SUMMARY_CAPS))

    def test_the_prompt_grows_by_exactly_the_extra_summary_and_keeps_the_copy_guards(self):
        def prompt(size):
            item = {"title": "기사", "source": "NASA", "link": LINK, "published": datetime.now(timezone.utc), "summary": "가" * size}
            return g.build_post_prompt(item, [], editorial_lane="technology")

        old, new = prompt(300), prompt(g.SUMMARY_MAX_CHARS)
        self.assertEqual(len(new) - len(old), g.SUMMARY_MAX_CHARS - 300)
        self.assertIn("가" * g.SUMMARY_MAX_CHARS, new)
        self.assertLess(len(new), 20000)                                   # 프롬프트는 약 12,000자 + 요약이라 모델 한도에 한참 못 미친다
        self.assertIn("[기사 요약 - 참고만 하고 문장을 그대로 옮기지 마세요]", new)
        for rule in g.GROUNDING_RULES:
            self.assertIn(f"- {rule}\n", new)


# ======================================================================================================================
# E — 응답 형식 지정과 호출 시간 상한
# ======================================================================================================================
class ApiError(Exception):
    def __init__(self, code, status, message):
        super().__init__(f"{code} {status}. {message}")
        self.code, self.status = code, status


class RecordingModels:
    """config 를 받는 가짜 SDK(`generate_content(model, contents, config=None)`). plan 의 항목을 차례로 쓴다: 예외면 던지고, 함수면 불러서 쓰고, 아니면 글자로 응답한다."""

    def __init__(self, plan):
        self.plan, self.calls = list(plan), []

    def generate_content(self, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        step = self.plan.pop(0)
        if isinstance(step, BaseException):
            raise step
        if callable(step):
            return step()
        return SimpleNamespace(text=step)


class OldModels:
    """config 를 받지 않는 낡은 SDK 모양(`generate_content(model, contents)`)."""

    def __init__(self, plan):
        self.plan, self.calls = list(plan), []

    def generate_content(self, model, contents):
        self.calls.append({"model": model, "contents": contents})
        step = self.plan.pop(0)
        if isinstance(step, BaseException):
            raise step
        return SimpleNamespace(text=step)


@pre_flip
class GeminiCallOptionsTest(unittest.TestCase):
    def setUp(self):
        self.log = llm.CallLog(label="chance", purpose="post", out=print)
        self.release = threading.Event()
        self.addCleanup(self.release.set)          # 붙잡힌 가짜 호출 스레드를 시험이 끝나면 풀어 준다
        for patcher in (mock.patch.object(g, "CALL_LOG", self.log),
                        mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0}),
                        mock.patch.object(g, "MODEL_CANDIDATES", ["m1", "m2", "m3"])):
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, models, prompt="프롬프트"):
        with mock.patch.object(g, "get_client", return_value=SimpleNamespace(models=models)):
            return run_captured(g.call_gemini_with_fallback, prompt)

    def hang(self):
        self.release.wait(5)
        return SimpleNamespace(text="너무 늦은 응답")

    def test_json_response_format_is_set_on_the_call(self):
        models = RecordingModels(['{"a": 1}'])
        response, _ = self.call(models)
        self.assertEqual(response.text, '{"a": 1}')
        self.assertEqual(models.calls, [{"model": "m1", "contents": "프롬프트", "config": {"response_mime_type": "application/json"}}])

    def test_the_pinned_config_value(self):
        self.assertEqual(g.JSON_RESPONSE_CONFIG, {"response_mime_type": "application/json"})

    def test_every_fallback_model_gets_the_format_and_the_shared_dict_stays_untouched(self):
        models = RecordingModels([RuntimeError("503 unavailable"), "{}"])
        self.call(models)
        self.assertEqual([c["config"] for c in models.calls], [{"response_mime_type": "application/json"}] * 2)
        models.calls[0]["config"]["response_mime_type"] = "text/plain"
        self.assertEqual(g.JSON_RESPONSE_CONFIG, {"response_mime_type": "application/json"})

    def test_an_sdk_without_config_support_is_called_the_old_way(self):
        models = OldModels(["{}"])
        response, _ = self.call(models)
        self.assertEqual(response.text, "{}")
        self.assertEqual(models.calls, [{"model": "m1", "contents": "프롬프트"}])

    def test_a_mock_client_that_takes_anything_gets_the_config(self):
        models = mock.Mock()
        models.generate_content.return_value = SimpleNamespace(text="{}")
        self.call(models)
        self.assertEqual(models.generate_content.call_args.kwargs["config"], {"response_mime_type": "application/json"})
        self.assertEqual(models.generate_content.call_args.kwargs["model"], "m1")

    def test_accepts_config_reads_the_signature(self):
        self.assertTrue(g._accepts_config(RecordingModels([]).generate_content))
        self.assertFalse(g._accepts_config(OldModels([]).generate_content))
        self.assertTrue(g._accepts_config(lambda **kwargs: None))
        self.assertFalse(g._accepts_config(lambda model, contents: None))
        self.assertFalse(g._accepts_config(42))

    def test_the_sdk_range_the_format_setting_was_checked_against_is_still_the_pinned_one(self):
        """E 는 google-genai 2.x 의 `generate_content(model, contents, config)` 와 `GenerateContentConfig.response_mime_type` 을 쓴다(2026-11-04 에 격리 venv 의 2.34.0 과
        가짜 서버로 요청 본문에 `generationConfig.responseMimeType` 이 실리는 것을 확인했다). 범위가 3 이상으로 넓어지면 이 시험이 깨져 SDK 호출 모양을 다시 확인하게 한다."""
        for name in ("requirements-pipeline.txt", "requirements-edits.txt"):
            lines = [line.strip() for line in (_bootstrap.ROOT / name).read_text(encoding="utf-8").splitlines()]
            self.assertIn("google-genai>=2,<3", lines, name)

    def test_the_timeout_is_the_pipeline_one_and_120_seconds(self):
        self.assertIs(g._run_with_timeout, llm._run_with_timeout)
        self.assertEqual(g.GEMINI_CALL_TIMEOUT_SECONDS, llm.CALL_TIMEOUT_SECONDS)
        self.assertEqual(g.GEMINI_CALL_TIMEOUT_SECONDS, 120)

    def test_a_call_that_hangs_is_cut_and_the_next_model_answers(self):
        models = RecordingModels([self.hang, '{"ok": true}'])
        started = time.monotonic()
        with mock.patch.object(g, "GEMINI_CALL_TIMEOUT_SECONDS", 0.2):
            response, out = self.call(models)
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(response.text, '{"ok": true}')
        self.assertEqual([c["model"] for c in models.calls], ["m1", "m2"])
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 2, "failed": 1})
        self.assertEqual([r.outcome for r in self.log.records], ["other", "ok"])
        self.assertIn("CallTimeout", self.log.records[0].detail)
        self.assertIn("Gemini 모델 호출 실패: m1 - ", out)
        self.assertIn("안에 끝나지 않았습니다", out)

    def test_when_every_model_hangs_the_run_fails_the_old_way(self):
        models = RecordingModels([self.hang, self.hang, self.hang])
        with mock.patch.object(g, "GEMINI_CALL_TIMEOUT_SECONDS", 0.1):
            exc, _ = self.call(models)
        self.assertIsInstance(exc, RuntimeError)
        self.assertTrue(str(exc).startswith("모든 Gemini 모델 호출 실패\nm1: "))
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 3, "failed": 3})
        self.assertEqual(len(models.calls), 3)

    def test_a_slow_but_in_time_call_is_not_cut(self):
        def slow():
            time.sleep(0.1)
            return SimpleNamespace(text="{}")

        models = RecordingModels([slow])
        with mock.patch.object(g, "GEMINI_CALL_TIMEOUT_SECONDS", 5):
            response, _ = self.call(models)
        self.assertEqual(response.text, "{}")
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 1, "failed": 0})

    def test_a_quick_sdk_error_is_a_plain_failure_not_a_timeout(self):
        models = RecordingModels([RuntimeError("503 unavailable"), "{}"])
        response, out = self.call(models)
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 2, "failed": 1})
        self.assertNotIn("CallTimeout", self.log.records[0].detail)
        self.assertIn("503 unavailable", out)

    def test_the_empty_answer_rule_is_unchanged(self):
        models = RecordingModels(["", "{}"])
        response, _ = self.call(models)
        self.assertEqual([r.outcome for r in self.log.records], ["empty", "ok"])
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 2, "failed": 1})

    def test_a_model_that_refuses_the_format_is_called_again_without_it(self):
        refusal = ApiError(400, "INVALID_ARGUMENT", "JSON mode is not enabled for models/m1")
        models = RecordingModels([refusal, '{"ok": true}'])
        response, out = self.call(models)
        self.assertEqual(response.text, '{"ok": true}')
        self.assertEqual([c["model"] for c in models.calls], ["m1", "m1"])
        self.assertEqual(models.calls[0]["config"], {"response_mime_type": "application/json"})
        self.assertIsNone(models.calls[1]["config"])
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 2, "failed": 1})
        self.assertEqual([r.outcome for r in self.log.records], ["other", "ok"])
        self.assertIn("JSON 형식 지정을 거절해 지정 없이 다시 호출합니다: m1", out)

    def test_a_refusal_looking_error_from_an_sdk_that_never_got_the_config_is_not_retried(self):
        refusal = ApiError(400, "INVALID_ARGUMENT", "JSON mode is not enabled for models/m1")
        models = OldModels([refusal, "{}"])
        self.call(models)
        self.assertEqual([c["model"] for c in models.calls], ["m1", "m2"])            # 지정을 보내지 않았으니 같은 호출을 되풀이하지 않는다
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 2, "failed": 1})

    def test_other_400_errors_are_not_mistaken_for_a_format_refusal(self):
        bad_key = ApiError(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.")
        models = RecordingModels([bad_key, "{}"])
        self.call(models)
        self.assertEqual([c["model"] for c in models.calls], ["m1", "m2"])           # 같은 모델을 다시 부르지 않고 다음 모델로
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 2, "failed": 1})

    def test_a_refusal_is_retried_once_per_model_only(self):
        refusal = ApiError(400, "INVALID_ARGUMENT", "response_mime_type is not supported")
        models = RecordingModels([refusal, refusal, "{}"])
        response, _ = self.call(models)
        self.assertEqual([c["model"] for c in models.calls], ["m1", "m1", "m2"])
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 3, "failed": 2})

    def test_a_server_error_that_mentions_json_is_not_a_format_refusal(self):
        models = RecordingModels([ApiError(503, "UNAVAILABLE", "JSON service overloaded"), "{}"])
        self.call(models)
        self.assertEqual([c["model"] for c in models.calls], ["m1", "m2"])

    def test_format_rejected_needs_a_400_or_invalid_argument_and_a_format_word(self):
        self.assertTrue(g._format_rejected(ApiError(400, "INVALID_ARGUMENT", "JSON mode is not enabled")))
        self.assertTrue(g._format_rejected(ApiError(400, "", "Unsupported MIME type")))
        self.assertTrue(g._format_rejected(ApiError(0, "INVALID_ARGUMENT", "application/json not allowed")))
        self.assertTrue(g._format_rejected(ApiError(400, "INVALID_ARGUMENT", 'Invalid JSON payload received. Unknown name "response_mime_type"')))      # 문구가 낯설어도 낱말이 든다(검증 S17)
        self.assertTrue(g._format_rejected(ApiError(400, "INVALID_ARGUMENT", "The response format is not supported by this model")))
        self.assertTrue(g._format_rejected(ApiError(400, "INVALID_ARGUMENT", "Unknown field in generationConfig")))
        self.assertFalse(g._format_rejected(ApiError(400, "INVALID_ARGUMENT", "The request body is empty")))              # 형식과 무관한 400 은 지정 없이 다시 부르지 않는다
        self.assertFalse(g._format_rejected(ApiError(400, "INVALID_ARGUMENT", "API key not valid")))
        self.assertFalse(g._format_rejected(ApiError(429, "RESOURCE_EXHAUSTED", "mime quota")))
        self.assertFalse(g._format_rejected(RuntimeError("something about json mode")))

    def test_the_whole_flow_sends_the_format_through_the_real_call_function(self):
        models = RecordingModels([json.dumps(long_post("기술"), ensure_ascii=False)])
        item = candidate("기술 기사 하나")
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.multiple(g, DRY_RUN=True, STUB_GEMINI=False, STUB_UNSPLASH=True, POSTS_DIR=Path(tmp) / "p",
                                    HISTORY_FILE=Path(tmp) / "h.json"), \
                mock.patch.object(g, "get_client", return_value=SimpleNamespace(models=models)), \
                mock.patch.object(g, "editorial_lane_order", lambda slot, history: ["technology"]), \
                mock.patch.object(g, "fetch_news_items", lambda editorial_lane=None, stats=None, deadline=None, clock=None: [item]), \
                mock.patch.object(g, "existing_titles", return_value=[]), \
                mock.patch.object(g, "write_history", lambda history: None):
            report = {}
            value, _ = run_captured(g.generate_blog_posts, slot=9, allow_auto_topic=False, report=report)
        self.assertIsNotNone(value)
        self.assertEqual(models.calls[0]["config"], {"response_mime_type": "application/json"})
        self.assertEqual(report["outcome"], "PUBLISHED")


if __name__ == "__main__":
    unittest.main()
