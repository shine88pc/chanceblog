"""구조화 Fact 분기가 이력에 더한 새 칸(`candidate_key`·`dedupe_key`·`recipe_id`·`as_of`·`content_source`·`provenance`)과 Fact 글이 **이력·글을 읽는 기존 코드**를 깨지 않는지의 시험 + `main()` 의 키 없는 facts 실행 +
명령줄 `content-source`. 실제 `generate_blog_posts` 가 만든 이력·글을 읽는 쪽 함수에 그대로 넣는다(네트워크·시계 없음).

읽는 쪽 전수(코드를 grep 으로 훑은 목록): 제목을 모으는 `existing_titles`·`state.entry_titles`·`state.other_blog_titles`(표식 항목은 AI 입력에서 뺀다) · 런타임 방벽 `ai_guard`(표식 항목의 제목 조각) · 승인 흐름(`drafts.slot_entry`·
`refine_slot_state`·`unmerged_draft_branches`·`draft_flow.history_entry_for`·`check_entry`) · 잠금(`publish_lock.posts_today`·`weekly_posts`) · 건강 점검(`health.post_days_from_history`) · 확인 필요 모음(`inbox.entry_moment`) ·
허용 목록 모드의 외부 제목 판정(`source_policy.external_history_titles`) · 편집 분야 추첨(`editorial_lane_order` 는 `lane` 칸이 없는 항목을 건너뛴다) · 후보 선택(`fact_candidates.made_from_history` — 옛 항목은 그대로 읽힌다)."""
import contextlib
import io
import json
import os
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import fact_branch_helpers as FB
import generator as g

from pipeline import ai_guard, draft_flow, drafts, health, inbox, provenance, publish_lock, registry, source_policy, state
from pipeline import fact_candidates as K


class ReadersBase(FB.FactEnv):
    def made_entry(self, **kwargs):
        value, report, out, error = self.run_branch(**kwargs)
        self.assertIsNone(error, error)
        self.assertIsNotNone(value, report)
        return self.history()[-1], (self.work / value[0]).read_text(encoding="utf-8")


class HistoryReadersTest(ReadersBase):
    def test_the_titles_readers_skip_the_marked_entry_for_the_model_and_show_it_to_people(self):
        entry, _text = self.made_entry()
        history = self.history()
        old = {"date": "2026-10-01", "topic": "옛 글감", "kr_title": "옛 한국어 제목", "en_title": "Old English Title"}
        mixed = [old] + history
        self.assertEqual(g.existing_titles(mixed, [], for_ai=True), ["옛 글감", "옛 한국어 제목", "Old English Title"])                    # 모델에 가는 목록에서 Fact 제목이 빠진다
        shown = g.existing_titles(mixed, [], for_ai=False)
        self.assertIn(entry["kr_title"], shown)                                                                                   # 사람이 읽는 곳에는 보인다
        self.assertEqual(sorted(state.entry_titles(mixed)), sorted(["옛 글감", "옛 한국어 제목", "Old English Title"]))
        self.assertIn(entry["kr_title"], state.entry_titles(mixed, for_ai=False))
        self.assertTrue(provenance.entry_blocks_ai(entry))

    def test_other_blog_titles_skip_the_marked_entry_too(self):
        entry, _text = self.made_entry()
        folder = self.tmp / "root"
        (folder / "hist").mkdir(parents=True)
        (folder / "hist" / "chance.json").write_text(json.dumps(self.history(), ensure_ascii=False), encoding="utf-8")
        blogs = [{"key": "chance", "state": {"history": "hist/chance.json"}}, {"key": "other", "state": {"history": "hist/chance.json"}}]
        self.assertEqual(state.other_blog_titles(folder, blogs, "x"), [])                                                          # 표식 항목 두 개(두 블로그)가 모두 빠진다
        self.assertEqual(len(state.other_blog_titles(folder, blogs, "x", for_ai=False)), 2 * 2)                                    # topic·kr_title 두 칸 × 두 블로그

    def test_the_model_entrance_guard_refuses_a_prompt_that_carries_the_fact_title(self):
        entry, text = self.made_entry()
        title = entry["kr_title"]
        self.assertGreater(len(title), 24)
        with self.assertRaises(ai_guard.AiInputForbidden):
            ai_guard.assert_clean("다음 제목과 겹치지 않게 써라: " + title)
        with self.assertRaises(ai_guard.AiInputForbidden):
            ai_guard.assert_clean("최근 글: " + json.dumps([title], ensure_ascii=False))
        ai_guard.assert_clean("전혀 다른 지시문입니다. 오늘의 주제는 도서관 이용 통계입니다.")                                              # 표식 글의 글자가 없으면 통과한다(대조군)

    def test_the_approval_flow_readers_understand_the_fact_entry(self):
        entry, text = self.made_entry()
        history = self.history()
        self.assertEqual(drafts.slot_entry(history, "2026-11-10", 9), entry)
        self.assertEqual(draft_flow.history_entry_for(history, entry["branch"]), entry)
        self.assertEqual(drafts.unmerged_draft_branches([entry["branch"]], history, exists=lambda path: False), [entry["branch"]])
        self.assertEqual(drafts.unmerged_draft_branches([entry["branch"]], history, exists=lambda path: True), [])
        self.assertEqual(drafts.parse_branch(entry["branch"]).slot, 9)
        self.assertTrue(drafts.posts_exist(entry, exists=lambda path: True))
        self.assertTrue(all(drafts.valid_post_path(path) for path in entry["paths"]))

    def test_the_lock_counts_and_the_health_and_inbox_readers_read_the_date_and_slot(self):
        entry, _text = self.made_entry()
        history = self.history()
        self.assertEqual(publish_lock.posts_today(history, "2026-11-10"), 1)
        counted = publish_lock.weekly_posts(history, [], self.now.date())
        self.assertEqual((counted.count, counted.unreadable, counted.future, counted.branch_future), (1, 0, 0, 0))
        self.assertEqual(len(health.post_days_from_history(history)), 1)
        moment, precision = inbox.entry_moment(entry)
        self.assertEqual((moment.date().isoformat(), moment.hour, precision), ("2026-11-10", 9, "slot"))

    def test_the_external_title_filter_of_the_allowlist_mode_does_not_call_the_own_title_external(self):
        entry, _text = self.made_entry()
        self.assertEqual(source_policy.external_history_titles(self.history()), set())                                             # topic 이 자체 제목(kr_title)과 같다

    def test_the_lane_draw_ignores_entries_without_a_lane_and_the_selection_reads_old_entries_as_before(self):
        entry, _text = self.made_entry()
        history = self.history()
        old = [{"date": "2026-10-01", "topic": "옛 글", "lane": "economy"}] + history
        self.assertEqual(g.editorial_lane_order(9, old, self.now), g.editorial_lane_order(9, old[:1] + [dict(entry, lane="not-a-lane")], self.now))      # lane 칸이 없거나 모르는 값이면 같은 취급
        made = K.made_from_history(old)
        self.assertEqual(set(made.last), {"kp_weekly"})                                                                            # 옛 항목은 건너뛰고 Fact 항목만 읽는다
        self.assertEqual(made.keys, frozenset({entry["candidate_key"]}))

    def test_a_feed_run_after_a_fact_post_still_works_with_the_marked_post_left_out_of_the_model_input(self):
        """같은 저장소에서 피드 경로(content_source 없음)로 되돌아가도 Fact 글은 AI 입력에서 빠지고 이력은 그대로 읽힌다(대조군: 표식이 없는 같은 모양의 글은 들어간다)."""
        _entry, text = self.made_entry()
        listing = g.load_posts(for_ai=True)
        self.assertEqual(listing, [])
        everything = g.load_posts(for_ai=False)
        self.assertEqual([post["provenance"] for post in everything], [provenance.MARK_FACTS])
        unmarked = text.replace('provenance: "facts"\n', "")
        (self.work / "_posts" / "대조군.md").write_text(unmarked, encoding="utf-8")
        self.assertEqual(len(g.load_posts(for_ai=True)), 1)

    def test_the_entry_is_valid_json_with_only_text_numbers_lists_and_null(self):
        entry, _text = self.made_entry()
        for value in entry.values():
            self.assertIsInstance(value, (str, int, list, type(None)))
        self.assertEqual(json.loads(json.dumps(entry, ensure_ascii=False)), entry)


class MainRunTest(FB.FactEnv):
    """`main()` — 키 없는 facts 실행(AI 키를 주지 않는 실행)이 끝까지 돈다. 피드 경로는 키가 없으면 이전처럼 멈춘다."""

    def setUp(self):
        super().setUp()
        self.summary = self.tmp / "summary.md"
        patch = mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(self.summary), "PIPELINE_PAUSE": "", "SHADOW_RUN": ""})
        patch.start()
        self.addCleanup(patch.stop)
        branch = mock.patch.object(draft_flow, "remote_branch_exists", return_value=False)
        branch.start()
        self.addCleanup(branch.stop)
        # 모듈 전역의 Gemini 호출 수·호출 기록은 앞선 시험(한 프로세스에서 이어 도는 CI 의 discover)이 올려 둘 수 있다 — 이 시험이 읽는 값이라 비워 두고 되돌린다(시험 순서에 기대지 않는다)
        calls = mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0})
        calls.start()
        self.addCleanup(calls.stop)
        log = mock.patch.object(g, "CALL_LOG", g.CallLog(label="chance", purpose="post", out=print, secrets=()))
        log.start()
        self.addCleanup(log.stop)

    def run_main(self):
        out, error = io.StringIO(), None
        with contextlib.redirect_stdout(out):
            try:
                g.main()
            except SystemExit as exc:
                error = exc
        return out.getvalue(), error

    def test_a_scheduled_facts_run_without_the_model_key_makes_a_draft_and_the_summary_says_zero_model_calls(self):
        self.assertTrue(g.STUB_GEMINI)                                                                                              # 키가 없다(스텁 모드)
        out, error = self.run_main()
        self.assertIsNone(error)
        self.assertEqual(len(self.posts()), 1)
        summary = self.summary.read_text(encoding="utf-8")
        self.assertIn("**DRAFT_CREATED**", summary)
        self.assertIn("Gemini 호출: 0회(실패 0회)", summary)
        self.assertNotIn("Gemini 응답 모델", summary)                                                                                # 호출 기록도 비어 있다
        self.assertIn(g.FACT_LANE_LABEL, summary)
        self.assertIn("구조화 Fact 경로", out)
        self.assertEqual(self.history()[0]["content_source"], "facts")

    def test_the_second_run_of_the_same_slot_makes_nothing_more(self):
        self.run_main()
        out, error = self.run_main()
        self.assertIsNone(error)
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(len(self.history()), 1)
        self.assertIn("지금 만들 글이 없습니다", out)

    def test_a_scheduled_facts_run_that_is_not_ready_ends_green_and_leaves_everything_alone(self):
        self.use(FB.facts_registry(), FB.real_sources(noaa_enabled=False))        # Provider 꺼짐 — 진짜 허용 목록 사본에서 NOAA 만 끈다(켜는 변경 뒤의 실제 파일은 켜져 있다)
        out, error = self.run_main()
        self.assertIsNone(error)
        self.assertEqual(self.files(), [])
        self.assertIn("::notice::", out)
        self.assertIn("code=FACT_NOT_READY", out)
        self.assertIn("**FACT_NOT_READY**", self.summary.read_text(encoding="utf-8"))

    def test_the_feed_path_without_a_key_stops_as_before(self):
        self.use(FB.facts_registry(content_source=None), FB.sources_registry())
        with self.assertRaises(RuntimeError) as caught:
            self.run_main()
        self.assertIn("GEMINI_API_KEY", str(caught.exception))

    def test_a_photo_replacement_run_without_a_key_stops_exactly_like_the_feed_value_even_when_the_registry_says_facts(self):
        """D1(독립 검증 S2b): 키 없는 완화는 Fact 글 만들기에만 해당한다. 사진 교체(FIX_IMAGES)는 Fact 분기로 가지 않고 모델로 검색어를 만들어 기존 글을 고치는 쓰기 경로라 키가 없으면 feed 값에서와 같이 멈춰야 한다
        (예전에는 facts 값에서 키 검사를 지나 `fix_images` 로 들어갔다). 종료(예외)·문구·표준 출력·실행 요약이 두 레지스트리 값에서 같다."""
        self.patch_value(g, "FIX_IMAGES", True)
        self.patch_value(g, "fix_images", mock.Mock(side_effect=AssertionError("키 없는 사진 교체가 fix_images 로 들어갔다")))
        results = {}
        for label, blogs in (("facts", FB.facts_registry()), ("feed", FB.facts_registry(content_source=None))):
            self.use(blogs, FB.sources_registry())
            self.summary.write_text("", encoding="utf-8")
            out, error = io.StringIO(), None
            with contextlib.redirect_stdout(out):
                try:
                    g.run_cli()
                except Exception as exc:       # noqa: BLE001 — 종료 방식(예외 종류·문구)을 견주려고 받는다
                    error = exc
            results[label] = (type(error).__name__, str(error), out.getvalue(), self.summary.read_text(encoding="utf-8"))
        self.assertEqual(results["facts"], results["feed"])
        kind, message, printed, summary = results["facts"]
        self.assertEqual(kind, "RuntimeError")
        self.assertIn("GEMINI_API_KEY 환경 변수가 없습니다", message)
        self.assertIn("작업 실패: RuntimeError", printed)
        self.assertIn("**실패** — RuntimeError", summary)
        self.assertEqual(self.files(), [])
        self.assertFalse(g.facts_without_key())                                                                                   # 사진 교체 실행에서는 키 없는 완화가 꺼진다
        self.patch_value(g, "FIX_IMAGES", False)
        self.use(FB.facts_registry(), FB.sources_registry())
        self.assertTrue(g.facts_without_key())                                                                                    # 대조군: 같은 레지스트리로 Fact 글 만들기면 완화된다

    def test_a_photo_replacement_practice_run_is_untouched_by_the_key_check_in_both_values(self):
        """연습 실행(DRY_RUN)은 키 검사를 하지 않는다(이전과 같다) — D1 의 수정이 연습 실행의 동작을 바꾸지 않는다."""
        self.patch_value(g, "FIX_IMAGES", True)
        self.patch_value(g, "DRY_RUN", True)
        spy = mock.Mock(return_value="사진 교체 연습")
        self.patch_value(g, "fix_images", spy)
        for blogs in (FB.facts_registry(), FB.facts_registry(content_source=None)):
            self.use(blogs, FB.sources_registry())
            out, error = self.run_main()
            self.assertIsNone(error)
            self.assertIn("[DRY_RUN] 시작", out)
        self.assertEqual(spy.call_count, 2)

    def test_the_key_check_is_skipped_only_when_the_registry_clearly_says_facts(self):
        self.assertTrue(g.facts_without_key())
        self.use(FB.facts_registry(content_source="feed"), FB.sources_registry())
        self.assertFalse(g.facts_without_key())
        self.use(FB.facts_registry(content_source="fact"), FB.sources_registry())                                                 # 이상한 값 — 키 검사를 건너뛰지 않는다
        self.assertFalse(g.facts_without_key())
        with mock.patch.object(registry, "load_registry", side_effect=registry.RegistryError("없음")):
            self.assertFalse(g.facts_without_key())
        with mock.patch.object(registry, "load_registry", side_effect=OSError("깨짐")):
            self.assertFalse(g.facts_without_key())

    def test_with_a_key_the_registry_is_not_read_an_extra_time(self):
        self.patch_value(g, "STUB_GEMINI", False)
        with mock.patch.object(g, "facts_without_key", side_effect=AssertionError("키가 있는데 레지스트리를 더 읽었다")):
            out, error = self.run_main()
        self.assertIsNone(error)
        self.assertEqual(len(self.posts()), 1)                                                                                    # 키가 있어도 facts 는 모델을 부르지 않는다
        for spy in self.spies.values():
            spy.assert_not_called()


class FeedUnchangedTest(FB.FactEnv):
    def test_a_feed_registry_never_runs_the_fact_branch(self):
        self.use(FB.facts_registry(content_source=None), FB.sources_registry())
        self.patch_value(g, "fetch_news_items", lambda editorial_lane=None, stats=None, deadline=None, clock=None: [])
        for name in ("generate_fact_post", "fact_context", "fact_prepare"):
            self.patch_value(g, name, mock.Mock(side_effect=AssertionError(f"feed 인데 {name} 을(를) 불렀다")))
        value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], "ALL_LANES_EMPTY")                                                                    # 피드 경로의 결과 코드 그대로
        self.assertEqual(self.noaa.factory_calls, 0)
        self.assertEqual(self.files(), [])


class CommandLineTest(unittest.TestCase):
    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = source_policy.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_it_prints_the_value_of_the_real_registry_which_is_facts(self):
        self.assertEqual(self.run_cli(["content-source"]), (0, "facts\n", ""))                                                   # 켜는 변경(T3, 패치 02) 뒤(전에는 feed)

    def test_it_prints_facts_for_a_facts_registry_and_nothing_when_it_cannot_read(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(registry, "REGISTRY_PATH", FB.write_json(Path(tmp) / "b.json", FB.facts_registry())):
                self.assertEqual(self.run_cli(["content-source"]), (0, "facts\n", ""))
            with mock.patch.object(registry, "REGISTRY_PATH", FB.write_json(Path(tmp) / "c.json", FB.facts_registry(content_source="x"))):
                code, out, err = self.run_cli(["content-source"])
                self.assertEqual((code, out), (1, ""))                                                                            # 출력이 비어야 워크플로 식이 닫힌 쪽이다
                self.assertIn("::error::", err)
            with mock.patch.object(registry, "REGISTRY_PATH", Path(tmp) / "없는 파일.json"):
                code, out, err = self.run_cli(["content-source"])
                self.assertEqual((code, out), (1, ""))

    def test_other_arguments_are_refused(self):
        for args in ([], ["flow"], ["content-source", "x"], ["--help"]):
            code, out, err = self.run_cli(args)
            self.assertEqual((code, out), (2, ""))
            self.assertIn("사용법", err)


if __name__ == "__main__":
    unittest.main()
