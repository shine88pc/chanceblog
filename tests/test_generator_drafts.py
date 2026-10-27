"""Chance 엔진(generator.py)의 승인 흐름 쪽 시험: 발행 흐름 읽기, 슬롯 판정 코드(DRAFT_PENDING·DRAFT_CHECK_FAILED), 이력 항목의 flow·branch·paths,
결과 코드 DRAFT_CREATED, 수동 실행, 연습 실행, 대기 초안 제목 중복. direct(기본)의 바이트 단위 불변은 이 시험이 아니라 저장소 밖의 비교 도구가
같은 입력으로 main 과 이 브랜치를 돌려 증명하고, 여기서는 direct 의 이력 항목·요약이 승인 흐름 필드 없이 그대로임을 고정한다. 네트워크 없이 돈다.
"""
import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _bootstrap
import generator as g
from draft_helpers import REAL_PUBLISH_FLOW, HermeticGit
from pipeline import draft_flow, drafts
from test_generator_slots import at, candidate, long_post, run_captured

ROOT = _bootstrap.ROOT
LINK = "https://www.reuters.com/a"
BRANCH_9 = "ai/draft/2026-10-28-s9"


@contextlib.contextmanager
def chdir(path):
    """작업 폴더를 잠시 옮긴다(contextlib.chdir 는 파이썬 3.11부터라 CI 의 3.10 에서는 쓸 수 없다)."""
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def run_tick(clone, now, flow="pr", event="schedule", dry=False, feed=None, gemini="ok", remote_exists=False, git_env=None, summary_name="summary.md"):
    """한 번의 실행(generator.main)을 clone 폴더에서 돌린다. 소스·Gemini·이미지 확인은 가짜이고 네트워크는 쓰지 않는다.
    remote_exists: 초안 브랜치 확인(draft_flow.remote_branch_exists)의 가짜 결과(True·False·None). 실제 git 을 쓰려면 'real'.
    돌려주는 값: SimpleNamespace(value, out, summary, prompts, history)."""
    clone = Path(clone)
    summary = clone.parent / summary_name
    summary.unlink(missing_ok=True)
    prompts = []
    items = [candidate("후보 기사", LINK)] if feed is None else feed

    def fake_fetch(editorial_lane=None, stats=None, deadline=None, clock=None):
        return list(items)

    def fake_gemini(prompt):
        prompts.append(prompt)
        if gemini == "fail":
            raise RuntimeError("가짜 Gemini 장애")
        item = items[0]
        return SimpleNamespace(text=json.dumps(long_post(item["title"], item["link"]), ensure_ascii=False))

    env = {k: v for k, v in os.environ.items() if k not in ("PIPELINE_PAUSE", "GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT")}
    env.update(git_env or {})
    env["GITHUB_STEP_SUMMARY"] = str(summary)
    patches = [mock.patch.dict(os.environ, env, clear=True), mock.patch.object(g, "EVENT_NAME", event), mock.patch.object(g, "DRY_RUN", dry),
               mock.patch.object(g, "STUB_GEMINI", False), mock.patch.object(g, "STUB_UNSPLASH", True), mock.patch.object(g, "FIX_IMAGES", False),
               mock.patch.object(g, "SLOT_HOURS", [9, 18]), mock.patch.object(g, "now_kst", return_value=now),
               mock.patch.object(g, "fetch_news_items", fake_fetch), mock.patch.object(g, "call_gemini_with_fallback", fake_gemini),
               mock.patch.object(g, "url_ok", lambda url, timeout=10: True), mock.patch.object(g, "trigger_download", lambda url: None),
               mock.patch.object(g, "get_client", side_effect=AssertionError("가짜 Gemini 만 쓴다")),
               mock.patch.object(drafts, "chance_flow", return_value=flow)]
    if remote_exists != "real":
        patches.append(mock.patch.object(draft_flow, "remote_branch_exists", return_value=remote_exists))
    with contextlib.ExitStack() as stack, chdir(clone):
        for patcher in patches:
            stack.enter_context(patcher)
        value, out = run_captured(g.main)
        history = json.loads(Path("history.json").read_text(encoding="utf-8")) if Path("history.json").exists() else []
    return SimpleNamespace(value=value, out=out, summary=summary.read_text(encoding="utf-8") if summary.exists() else "", prompts=prompts,
                           history=history)


class PlainDirBase(unittest.TestCase):
    """git 이 필요 없는 시험의 작업 폴더(빈 이력과 _posts 폴더 하나)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.clone = self.root / "repo"
        (self.clone / "_posts").mkdir(parents=True)
        (self.clone / "history.json").write_bytes(b"[]\n")

    def set_history(self, entries):
        (self.clone / "history.json").write_bytes(json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8"))

    def posts(self):
        return sorted(p.relative_to(self.clone).as_posix() for p in (self.clone / "_posts").rglob("*.md"))


class PrFlowGenerationTest(PlainDirBase):
    def test_a_due_slot_makes_a_draft_entry_with_flow_branch_and_paths(self):
        tick = run_tick(self.clone, at(9, 20, day=28))
        self.assertIsNone(tick.value)
        self.assertEqual(len(tick.history), 1)
        entry = tick.history[0]
        self.assertEqual((entry["flow"], entry["branch"], entry["slot"], entry["date"]), ("pr", BRANCH_9, 9, "2026-10-28"))
        self.assertEqual(sorted(entry["paths"]), self.posts())
        self.assertEqual(len(entry["paths"]), 2)
        self.assertEqual([p.split("/")[-1] for p in entry["paths"]], ["2026-10-28-KR-092000.md", "2026-10-28-EN-092000.md"])      # 한국어, 영어 순서(올리기 단계가 이 순서로 읽는다)
        self.assertTrue(all(drafts.valid_post_path(p) for p in entry["paths"]))
        self.assertEqual(entry["topic"], "후보 기사")           # 슬롯·제목 중복 검사가 보는 필드는 direct 와 같다

    def test_the_summary_says_draft_created_not_published(self):
        tick = run_tick(self.clone, at(9, 20, day=28))
        self.assertIn("결과: **DRAFT_CREATED**", tick.summary)
        self.assertNotIn("**PUBLISHED**", tick.summary)
        self.assertIn(g.OUTCOME_TEXT["DRAFT_CREATED"], tick.summary)
        self.assertIn(f"- 승인 흐름: 초안 브랜치 `{BRANCH_9}` 로 올립니다 — PR 을 병합하면 공개, 닫으면 폐기", tick.summary)
        self.assertIn(f"- 승인 흐름: 초안 브랜치 {BRANCH_9} 로 올립니다(PR 을 병합하면 공개, 닫으면 폐기)", tick.out)
        self.assertIn("- 제목: 테스트 후보 기사", tick.summary)

    def test_a_pending_slot_is_skipped_with_its_own_code_and_no_gemini_call(self):
        run_tick(self.clone, at(9, 20, day=28))
        for rel in self.posts():                                  # deliver 가 글을 초안 브랜치로 옮긴 뒤의 main 작업 트리: 글이 없다
            (self.clone / rel).unlink()
        tick = run_tick(self.clone, at(9, 50, day=28))
        self.assertIsNone(tick.value)
        self.assertIn("[SKIP] code=DRAFT_PENDING", tick.out)
        self.assertIn("9시 슬롯 초안이 승인(PR 병합)을 기다리는 중이거나 닫혀 폐기됨", tick.out)
        self.assertIn("결과: **DRAFT_PENDING**", tick.summary)
        self.assertIn("(정상 건너뜀)", tick.summary)
        self.assertEqual(tick.prompts, [])
        self.assertEqual(len(tick.history), 1)
        self.assertEqual(self.posts(), [])

    def test_a_merged_slot_reads_as_already_published(self):
        run_tick(self.clone, at(9, 20, day=28))                    # 글이 main 에 있는 상태 = 병합된 뒤
        tick = run_tick(self.clone, at(9, 50, day=28))
        self.assertIn("[SKIP] code=ALREADY_PUBLISHED", tick.out)
        self.assertNotIn("DRAFT_PENDING", tick.out)
        self.assertIn("9시 슬롯 글이 이미 있음", tick.out)
        self.assertEqual(tick.prompts, [])

    def test_the_other_slot_is_independent_of_a_pending_one(self):
        run_tick(self.clone, at(9, 20, day=28))
        for rel in self.posts():
            (self.clone / rel).unlink()
        tick = run_tick(self.clone, at(18, 20, day=28), feed=[candidate("해양 관측 위성 자료 공개", "https://www.reuters.com/b")])
        self.assertIn("결과: **DRAFT_CREATED**", tick.summary)
        self.assertEqual([(e["slot"], e["branch"]) for e in tick.history], [(9, BRANCH_9), (18, "ai/draft/2026-10-28-s18")])

    def test_the_next_day_is_independent_of_yesterdays_pending_draft(self):
        run_tick(self.clone, at(9, 20, day=28))
        for rel in self.posts():
            (self.clone / rel).unlink()
        tick = run_tick(self.clone, at(9, 20, day=29), feed=[candidate("캐나다 소비자물가지수 발표", "https://www.reuters.com/c")])
        self.assertEqual(tick.history[-1]["branch"], "ai/draft/2026-10-29-s9")

    def test_a_due_slot_whose_branch_already_exists_is_pending(self):
        """이력 쓰기가 실패한 드문 경우: 이력에는 없지만 그 슬롯의 초안 브랜치가 원격에 있으면 다시 만들지 않는다."""
        tick = run_tick(self.clone, at(9, 20, day=28), remote_exists=True)
        self.assertIn("[SKIP] code=DRAFT_PENDING", tick.out)
        self.assertEqual((tick.prompts, tick.history, self.posts()), ([], [], []))

    def test_an_unreadable_remote_skips_this_run_with_a_warning(self):
        tick = run_tick(self.clone, at(9, 20, day=28), remote_exists=None)
        self.assertIn("[SKIP] code=DRAFT_CHECK_FAILED", tick.out)
        self.assertIn("::warning::초안 브랜치를 확인하지 못해 이번 실행은 글을 만들지 않았습니다. 다음 실행에서 다시 시도합니다.", tick.out)
        self.assertIn("결과: **DRAFT_CHECK_FAILED** — 초안 브랜치를 확인하지 못함(다음 실행에서 다시 확인)", tick.summary)
        self.assertEqual((tick.prompts, tick.history, self.posts()), ([], [], []))

    def test_before_the_first_slot_nothing_checks_the_remote(self):
        def boom(*args, **kwargs):
            raise AssertionError("창 밖에서는 원격을 보지 않는다")
        with mock.patch.object(draft_flow, "remote_branch_exists", boom):
            tick = run_tick(self.clone, at(8, 40, day=28), remote_exists="real")
        self.assertIn("[SKIP] code=OUT_OF_WINDOW", tick.out)

    def test_a_practice_run_never_asks_the_remote(self):
        def boom(*args, **kwargs):
            raise AssertionError("연습 실행은 네트워크를 쓰지 않는다")
        with mock.patch.object(draft_flow, "remote_branch_exists", boom):
            tick = run_tick(self.clone, at(9, 20, day=28), dry=True, remote_exists="real")
        self.assertIn("연습으로 글을 만들어 봤습니다(저장하지 않았습니다)", tick.summary)
        self.assertIn(f"- 승인 흐름: 연습 실행이라 초안 브랜치 `{BRANCH_9}` 를 올리지 않습니다", tick.summary)      # 연습이 '올립니다'라고 말하지 않는다
        self.assertIn(f"- 승인 흐름: 연습 실행이라 초안 브랜치 {BRANCH_9} 를 올리지 않습니다", tick.out)
        self.assertNotIn("로 올립니다", tick.summary + tick.out)
        self.assertEqual(self.posts(), [])
        self.assertEqual(tick.history, [])

    def test_a_manual_run_in_the_draft_flow_gets_a_time_stamped_branch_and_no_slot(self):
        tick = run_tick(self.clone, at(11, 5, day=28), event="workflow_dispatch")
        entry = tick.history[0]
        self.assertEqual((entry["flow"], entry["slot"], entry["branch"]), ("pr", None, "ai/draft/2026-10-28-m110500"))
        self.assertIn("결과: **DRAFT_CREATED**", tick.summary)

    def test_a_gate_rejection_creates_no_entry_and_no_branch(self):
        thin = candidate("얇은 기사", "https://www.reuters.com/t")
        with mock.patch.object(g, "validate_post_data", side_effect=ValueError("본문 얇음")):
            tick = run_tick(self.clone, at(9, 20, day=28), feed=[thin])
        self.assertEqual((tick.history, self.posts()), ([], []))
        self.assertIn("ALL_REJECTED", tick.out)

    def test_every_draft_skip_reason_formats(self):
        for state, reason in g.DRAFT_SKIP_REASONS.items():
            self.assertTrue(reason.format(slot=9))
        self.assertEqual(set(g.DRAFT_SKIP_REASONS), {drafts.STATE_PENDING, drafts.STATE_CHECK_FAILED})


class PendingTitleTest(PlainDirBase):
    """⑦ 대기 중이거나 닫힌 초안의 제목·주제는 이력에 남아 있어, 같은 날 다음 슬롯의 후보와 겹치면 후보에서 빠진다."""

    def pending_entry(self, **extra):
        entry = {"date": "2026-10-28", "slot": 9, "topic": "유럽연합 인공지능 규제안 발표", "kr_title": "유럽연합이 인공지능 규제안을 발표했다",
                 "en_title": "EU unveils AI regulation proposal", "lane": "technology",
                 **drafts.entry_fields("2026-10-28", 9, None, ["_posts/a/KR.md", "_posts/b/EN.md"])}
        entry.update(extra)
        return entry

    def test_a_similar_candidate_is_dropped_while_the_draft_is_pending(self):
        self.set_history([self.pending_entry()])
        similar = candidate("유럽연합 인공지능 규제안 발표", "https://www.reuters.com/eu")
        tick = run_tick(self.clone, at(18, 20, day=28), feed=[similar])
        self.assertEqual(tick.prompts, [])                                  # Gemini 를 부르지 않았다
        self.assertIn("ALL_LANES_EMPTY", tick.out)                          # 후보가 모두 기존 글(대기 초안 포함)과 비슷해 탈락했다
        self.assertEqual(len(tick.history), 1)

    def test_a_different_candidate_is_still_written(self):
        self.set_history([self.pending_entry()])
        other = candidate("캐나다 통계청 소비자물가지수 발표", "https://www.reuters.com/ca")
        tick = run_tick(self.clone, at(18, 20, day=28), feed=[other])
        self.assertIn("결과: **DRAFT_CREATED**", tick.summary)
        self.assertEqual(len(tick.prompts), 1)

    def test_a_rejected_draft_is_remembered_the_same_way_so_the_topic_is_not_proposed_again(self):
        """PR 을 닫아도 이력 항목은 그대로다 — 폐기한 주제가 다음 슬롯에 또 올라오지 않는다."""
        self.set_history([self.pending_entry()])
        similar = candidate("유럽연합 인공지능 규제안 발표", "https://www.reuters.com/eu")
        tick = run_tick(self.clone, at(9, 20, day=29), feed=[similar])      # 다음 날 같은 슬롯
        self.assertEqual(tick.prompts, [])

    def test_existing_titles_include_the_pending_entries_topic_and_both_titles(self):
        titles = g.existing_titles([self.pending_entry()], [])
        for expected in ("유럽연합 인공지능 규제안 발표", "유럽연합이 인공지능 규제안을 발표했다", "EU unveils AI regulation proposal"):
            self.assertIn(expected, titles)


class DirectFlowUnchangedTest(PlainDirBase):
    """direct(기본)에서는 이력 항목·요약에 승인 흐름의 흔적이 없다."""

    def test_the_entry_has_no_draft_fields_and_the_outcome_is_published(self):
        tick = run_tick(self.clone, at(9, 20, day=28), flow="direct")
        entry = tick.history[0]
        for key in ("flow", "branch", "paths"):
            self.assertNotIn(key, entry)
        self.assertEqual(sorted(entry), sorted(["date", "topic", "kr_title", "en_title", "kr_image", "en_image", "slot", "lane", "source", "source_url"]))
        self.assertIn("결과: **PUBLISHED** — 글을 만들었습니다", tick.summary)
        self.assertNotIn("승인 흐름", tick.summary + tick.out)
        self.assertEqual(len(self.posts()), 2)                    # 글은 작업 트리에 그대로 남는다(워크플로의 커밋 단계가 올린다)

    def test_the_slot_codes_are_the_old_ones(self):
        run_tick(self.clone, at(9, 20, day=28), flow="direct")
        tick = run_tick(self.clone, at(9, 50, day=28), flow="direct", remote_exists="real")      # direct 는 원격을 보지 않는다(실제 git 이었다면 이 폴더는 저장소가 아니다)
        self.assertIn("[SKIP] code=ALREADY_PUBLISHED", tick.out)
        self.assertNotIn("DRAFT", tick.out + tick.summary)

    def test_a_pending_looking_entry_is_not_reinterpreted_in_direct_flow(self):
        """flow=pr 항목이 이력에 남아 있어도(되돌린 뒤) direct 는 예전 판정(ALREADY_PUBLISHED)만 쓴다 — 슬롯을 다시 열지 않는다."""
        entry = {"date": "2026-10-28", "slot": 9, "topic": "t", **drafts.entry_fields("2026-10-28", 9, None, ["_posts/a/KR.md", "_posts/b/EN.md"])}
        (self.clone / "history.json").write_bytes(json.dumps([entry]).encode("utf-8"))
        tick = run_tick(self.clone, at(9, 50, day=28), flow="direct")
        self.assertIn("[SKIP] code=ALREADY_PUBLISHED", tick.out)


class FlowLookupTest(PlainDirBase):
    def test_a_broken_registry_stops_the_engine_instead_of_publishing_directly(self):
        with mock.patch.object(drafts, "chance_flow", side_effect=drafts.DraftFlowError("레지스트리 오류")):
            with chdir(self.clone), mock.patch.object(g, "EVENT_NAME", "schedule"), mock.patch.object(g, "DRY_RUN", False), \
                    mock.patch.object(g, "STUB_GEMINI", False), mock.patch.object(g, "SLOT_HOURS", [9, 18]), \
                    mock.patch.object(g, "now_kst", return_value=at(9, 20, day=28)), \
                    mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "PIPELINE_PAUSE"}, clear=True):
                with self.assertRaises(drafts.DraftFlowError):
                    run_captured(g.run_cli)
        self.assertEqual(self.posts(), [])

    def test_the_manual_path_reads_the_flow_too(self):
        with mock.patch.object(drafts, "chance_flow", side_effect=drafts.DraftFlowError("레지스트리 오류")):
            with chdir(self.clone), mock.patch.object(g, "EVENT_NAME", "workflow_dispatch"), mock.patch.object(g, "DRY_RUN", False), \
                    mock.patch.object(g, "STUB_GEMINI", False), mock.patch.object(g, "now_kst", return_value=at(11, 0, day=28)), \
                    mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "PIPELINE_PAUSE"}, clear=True):
                with self.assertRaises(drafts.DraftFlowError):
                    run_captured(g.main)

    def test_the_pause_switch_and_the_image_fix_do_not_need_the_registry(self):
        with mock.patch.object(drafts, "chance_flow", side_effect=AssertionError("읽으면 안 된다")):
            with chdir(self.clone), mock.patch.dict(os.environ, {"PIPELINE_PAUSE": "true"}):
                value, out = run_captured(g.main)
        self.assertIn("[SKIP] code=PAUSED", out)

    def test_the_engine_enters_the_draft_flow_exactly_when_the_real_registry_says_pr(self):
        """진짜 레지스트리가 direct(지금)이면 엔진은 승인 흐름에 들어가지 않는다. 값은 draft_helpers.REAL_PUBLISH_FLOW 와 묶여 있다."""
        self.assertEqual(g.draft_flow_on(), REAL_PUBLISH_FLOW == "pr")

    def test_draft_flow_on_follows_the_registry_value(self):
        for value, expected in (("direct", False), ("pr", True)):
            with mock.patch.object(drafts, "chance_flow", return_value=value):
                self.assertEqual(g.draft_flow_on(), expected)


class RefineForDraftsTest(unittest.TestCase):
    def test_a_due_slot_asks_the_remote_for_that_slots_branch_only(self):
        asked = []
        with mock.patch.object(draft_flow, "remote_branch_exists", lambda name, *a, **k: asked.append(name) or False), mock.patch.object(g, "DRY_RUN", False):
            self.assertEqual(g.refine_for_drafts("DUE", 18, [], at(18, 30, day=28)), "DUE")
        self.assertEqual(asked, ["ai/draft/2026-10-28-s18"])

    def test_other_states_are_decided_from_the_history_alone(self):
        def boom(*args, **kwargs):
            raise AssertionError("원격을 보지 않는다")
        history = [{"date": "2026-10-28", "slot": 9, **drafts.entry_fields("2026-10-28", 9, None, ["_posts/a/KR.md", "_posts/b/EN.md"])}]
        with mock.patch.object(draft_flow, "remote_branch_exists", boom), mock.patch.object(g, "DRY_RUN", False):
            self.assertEqual(g.refine_for_drafts("ALREADY_PUBLISHED", 9, history, at(9, 30, day=28)), "DRAFT_PENDING")
            self.assertEqual(g.refine_for_drafts("OUT_OF_WINDOW", None, [], at(8, 30, day=28)), "OUT_OF_WINDOW")


class HermeticEnvTest(unittest.TestCase):
    def test_the_helper_environment_does_not_set_an_author(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = HermeticGit(tmp).env
        self.assertNotIn("GIT_AUTHOR_NAME", env)
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")


if __name__ == "__main__":
    unittest.main()
