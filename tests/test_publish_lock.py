"""제한 재개 잠금(레지스트리 resume_lock, pipeline/publish_lock.py) 시험.

잠금은 '사람 승인 없는 공개 경로 0개'를 코드로 지키는 스위치다(기본 꺼짐 — 꺼져 있으면 이전과 같은 동작). 여기서는 ① 잠금 상태 읽기·규칙 L0–L7 ② 실행 시작 가드(하루 상한·열린 초안 상한·이미지 교체
거절·깨진 이력) ③ generator.main 이 가드를 부르는 모양 ④ drafts.chance_flow 와 워크플로 단계의 연결(직접 커밋 단계가 잠금 아래에서 한 번도 돌지 않음) ⑤ Blogger 러너의 거절
(공개 게시 코드 감시) ⑥ 명령줄을 확인한다. 워크플로 파일 전체의 쓰기 경로 목록과 문서 일치는 tests/test_publish_paths.py. 네트워크·실제 시크릿 없이 돈다.
"""
import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import generator as g
from lock_helpers import (CHANCE, KCYOON, MACAT, VIOLATIONS, EXTRA, KEY_TYPOS, DEEP_PLACES, put_in, blog_of, drop_limit, lock_ready, mutated, real_registry, rules_in, set_in,
                          set_limit, today_registry, with_lock_off, write_registry)
from pipeline import draft_flow, drafts, plan, publish_lock, registry
from test_chance_draft_workflow import steps_of
from test_generator_drafts import PlainDirBase, chdir, run_tick
from test_generator_slots import at, candidate, run_captured
from test_run import FULL_ENV, RunBase, FakePublisher
from test_workflow_names import context, load, render

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 9, 10, 0, tzinfo=KST)
TODAY = "2026-11-09"
BRANCH_A, BRANCH_B, BRANCH_C = "ai/draft/2026-11-07-s9", "ai/draft/2026-11-08-s18", "ai/draft/2026-11-09-m091722"


def entry(date=TODAY, slot=9, branch=None, merged_paths=None):
    """이력 항목 하나(승인 흐름 모양). branch 가 있으면 flow=pr·branch·paths 가 붙는다."""
    item = {"date": date, "slot": slot, "topic": "t"}
    if branch:
        item.update(flow="pr", branch=branch, paths=merged_paths or ["_posts/a/KR.md", "_posts/b/EN.md"])
    return item


STATUS_PREFIX = "[잠금] 제한 재개 잠금: "      # 잠금 키가 레지스트리에 적혀 있을 때만 가드가 로그에 남기는 상태 줄(키가 없으면 줄도 없다 — 출력이 이전과 같다)


class GuardRun:
    """guard_start 를 한 번 부른 결과를 모은다: code(None 이면 조용히 돌아옴, 아니면 SystemExit 의 값)·out 줄(상태 줄은 뺀다)·status(상태 줄)·요약."""

    def __init__(self, folder, reg, history=None, now=NOW, fix_images=False, dry_run=False, environ=None, remote="unused", exists=None, raw_history=None):
        self.summary, self.remote_calls = [], []
        raw = []
        path = Path(folder) / "history.json"
        if raw_history is not None:
            path.write_text(raw_history, encoding="utf-8")
        elif history is not None:
            path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
        if remote == "unused":
            def remote_drafts():
                raise AssertionError("원격 초안 브랜치를 읽으면 안 되는 경우다")
        else:
            def remote_drafts():
                self.remote_calls.append(1)
                return remote
        try:
            publish_lock.guard_start({"EVENT_NAME": "schedule"} if environ is None else environ, path, lambda: now, fix_images, dry_run, self.summary.append,
                                     out=raw.append, load=lambda: reg, remote_drafts=remote_drafts, exists=exists)
            self.code = None
        except SystemExit as exc:
            self.code = exc.code
        self.status = [line for line in raw if line.startswith(STATUS_PREFIX)]
        self.out = [line for line in raw if not line.startswith(STATUS_PREFIX)]

    @property
    def text(self):
        return "\n".join(self.out)


class LockStateTest(unittest.TestCase):
    def test_a_missing_key_and_false_mean_off(self):
        for reg in ({}, {"resume_lock": False}, {"blogs": []}):
            self.assertEqual(publish_lock.lock_state(reg), "off", reg)
            self.assertFalse(publish_lock.lock_active(reg))

    def test_true_means_on(self):
        self.assertEqual(publish_lock.lock_state({"resume_lock": True}), "on")
        self.assertTrue(publish_lock.lock_active({"resume_lock": True}))

    def test_any_other_value_is_read_as_locked_fail_closed(self):
        for value in ("true", "false", "yes", 1, 0, None, [], {}, "켜짐"):
            reg = {"resume_lock": value}
            self.assertEqual(publish_lock.lock_state(reg), "invalid", value)
            self.assertTrue(publish_lock.lock_active(reg), value)

    def test_a_registry_that_is_not_an_object_is_unreadable_and_not_active(self):
        for reg in (None, [], "x", 3):
            self.assertEqual(publish_lock.lock_state(reg), "unreadable", reg)
            self.assertFalse(publish_lock.lock_active(reg))
            self.assertEqual(publish_lock.lock_errors(reg), [])
            self.assertEqual(publish_lock.registry_errors(reg), [])

    def test_the_real_registry_has_the_lock_off_today(self):
        """레지스트리 값을 바꾸는 것(켜기)은 별도 T3 병합이다 — 이 일은 값을 바꾸지 않는다. 켜는 변경은 이 시험을 함께 고친다(`today_registry()` 대신 `lock_ready()`).
        '꺼짐' 기준의 다른 시험은 진짜 레지스트리가 아니라 `today_registry()` 를 쓰므로, 진짜 값에 묶인 것은 이 시험 하나다."""
        reg = real_registry()
        from registry_states import state_registry
        self.assertNotIn("resume_lock", reg)
        self.assertEqual(publish_lock.lock_state(reg), "off")
        self.assertEqual(reg, state_registry("p2"))          # 켜는 변경(T3, 패치 02) 뒤: 잠금은 아직 꺼져 있고 값(스위치·허용 목록 모드·국문 단독·승인 흐름·주간 상한)이 알려진 상태 p2 와 정확히 같다(패치 03 이 잠금을 켠다)


class RegistryRuleTest(unittest.TestCase):
    def test_the_real_registry_is_valid_and_has_no_lock_error(self):
        reg = real_registry()
        self.assertEqual(publish_lock.lock_errors(reg), [])
        self.assertEqual(publish_lock.registry_errors(reg), [])
        self.assertEqual(registry.validate_registry(reg), [])

    def test_a_registry_that_obeys_every_rule_passes_the_whole_validator_with_the_lock_on(self):
        reg = lock_ready()
        self.assertTrue(reg["resume_lock"])
        self.assertEqual(publish_lock.lock_errors(reg), [])
        self.assertEqual(registry.validate_registry(reg), [])            # 채널·워크플로·시크릿·프로필까지 전체 검증을 통과한다 — 켜는 변경이 실제로 만들 수 있는 모양이다

    def test_the_lock_ready_registry_only_differs_in_the_values_the_t3_change_would_set(self):
        before, after = today_registry(), lock_ready()
        self.assertEqual(after.pop("resume_lock"), True)
        chance_before, chance_after = blog_of(before, CHANCE), blog_of(after, CHANCE)
        self.assertEqual(chance_after.pop("publish_flow"), "pr")
        self.assertEqual(chance_after.pop("limits"), {"max_posts_per_day": 1, "max_open_drafts": 3, "max_posts_per_week": 2})     # 켜는 값 다섯째: 주간 상한(L8)
        self.assertEqual(chance_before.pop("limits"), {"max_posts_per_day": 2})
        self.assertEqual(chance_before.pop("publish_flow"), "direct")
        self.assertEqual(before, after)                                  # 나머지(Blogger 둘·네이버 모드, 광고 선언 등)는 그대로 규칙을 이미 지킨다

    def test_every_rule_has_a_violation_that_only_it_and_its_known_partners_report(self):
        self.assertEqual({rule for rule, _text in publish_lock.RULES}, set(VIOLATIONS))
        for rule, cases in VIOLATIONS.items():
            self.assertTrue(cases, rule)
            for label, mutate in cases:
                with self.subTest(rule=rule, case=label):
                    reg = mutated(mutate)
                    found = rules_in(publish_lock.lock_errors(reg))
                    self.assertEqual(found, {rule, *EXTRA.get((rule, label), ())}, publish_lock.lock_errors(reg))
                    self.assertTrue(any(rule in message for message in registry.validate_registry(reg)), rule)   # 전체 검증(REG-1)도 같은 문장을 낸다

    def test_the_same_violations_are_ignored_when_the_lock_is_off(self):
        """잠금이 꺼져 있으면 규칙은 적용되지 않는다(이전과 같음): 잠금 키만 지운 사본은 규칙 오류가 없다."""
        for rule, cases in VIOLATIONS.items():
            if rule == "L0":
                continue                                                  # L0 은 잠금 키 자체의 값이다 — 꺼짐에는 해당 없음
            for label, mutate in cases:
                with self.subTest(rule=rule, case=label):
                    reg = with_lock_off(mutated(mutate))
                    self.assertEqual(publish_lock.lock_errors(reg), [])
                    if rule != "L5":                                          # L5 의 값 모양(1 이상 정수)만 잠금과 무관하게 본다 — 아래 시험
                        self.assertEqual(publish_lock.registry_errors(reg), [])

    def test_an_explicit_false_is_the_same_as_no_key(self):
        reg = mutated(lambda r: set_in(r, CHANCE, publish_flow="direct"))
        reg["resume_lock"] = False
        self.assertEqual(publish_lock.registry_errors(reg), [])
        self.assertEqual(registry.validate_registry(reg), [])

    def test_with_the_lock_off_a_registry_that_breaks_every_rule_still_passes_as_before(self):
        reg = today_registry()
        set_in(reg, MACAT, mode="auto")
        set_limit(reg, KCYOON, max_posts_per_day=5)
        # chance.languages(L6)는 일부러 뺐다: GATE 묶음이 병합되면 languages 검증이 잠금과 무관하게 항상 켜져 있어 ["en"] 을 거절한다 — 이 시험은 '잠금 규칙'이 꺼짐에서 적용되지 않음을 본다.
        # L6 의 꺼짐 동작(오류 문장이 나오지 않음)은 위 test_the_same_violations_are_ignored_when_the_lock_is_off 가 값 모양마다 확인하므로 GATE 가 있든 없든 같다.
        self.assertEqual(registry.validate_registry(reg), [])            # 이전과 같다: 규칙은 켜졌을 때만 적용된다

    def test_a_bad_value_of_the_open_drafts_limit_is_caught_even_with_the_lock_off(self):
        """값이 있는 chance.limits.max_open_drafts 는 잠금과 무관하게 1 이상 정수여야 한다(잘못 적은 값이 조용히 '규칙 없음'이 되지 않게). 키가 없으면 아무 일도 없다."""
        for bad in ("3", True, 0, -1, 1.5, None):
            reg = today_registry()
            set_limit(reg, CHANCE, max_open_drafts=bad)
            errors = registry.validate_registry(reg)
            self.assertEqual(len(errors), 1, (bad, errors))
            self.assertIn("L5", errors[0])
            self.assertIn("1 이상 정수", errors[0])
        for good in (1, 3, 7):
            reg = today_registry()
            set_limit(reg, CHANCE, max_open_drafts=good)
            self.assertEqual(registry.validate_registry(reg), [], good)

    def test_the_messages_name_the_rule_the_value_and_the_blog(self):
        reg = mutated(lambda r: set_in(r, MACAT, mode="auto"))
        message = publish_lock.lock_errors(reg)[0]
        for piece in ("제한 재개 잠금 L2", "blogger_macat", "'auto'", "off·draft·package"):
            self.assertIn(piece, message)
        reg = mutated(lambda r: set_limit(r, CHANCE, max_posts_per_day=2))
        self.assertIn("(지금 2)", publish_lock.lock_errors(reg)[0])
        reg = mutated(lambda r: blog_of(r, CHANCE).pop("publish_flow"))
        self.assertIn("적지 않으면 direct 로 읽힙니다", publish_lock.lock_errors(reg)[0])

    def test_values_are_shown_safely_on_one_line(self):
        evil = "x\n::error::가짜 주석\n"
        reg = mutated(lambda r: set_in(r, MACAT, mode=evil))
        joined = "".join(publish_lock.lock_errors(reg))
        self.assertNotIn("\n", joined)
        self.assertNotIn("::error::", joined)                             # '::' 는 풀어 놓는다(워크플로 명령 흉내 방지)

    def test_a_registry_without_a_chance_blog_has_no_chance_rules(self):
        reg = mutated(lambda r: r["blogs"].remove(blog_of(r, CHANCE)))
        self.assertEqual(publish_lock.lock_errors(reg), [])               # Chance 글은 chance_flow 가 읽지 못해 이미 멈춘다 — 이 규칙들이 따로 막을 것이 없다

    def test_malformed_registries_never_raise(self):
        weird = [{"resume_lock": True}, {"resume_lock": True, "blogs": None}, {"resume_lock": True, "blogs": [None, 3, "x", {}]},
                 {"resume_lock": True, "defaults": None, "blogs": [{"key": "chance", "limits": None, "languages": 3}]},
                 {"resume_lock": True, "defaults": {"limits": "x"}, "blogs": [{"key": "other", "mode": ["auto"]}]},
                 {"resume_lock": 3, "blogs": [{"key": "chance", "publish_flow": ["pr"]}]}]
        for reg in weird:
            with self.subTest(reg=reg):
                self.assertIsInstance(publish_lock.lock_errors(reg), list)
                self.assertIsInstance(publish_lock.registry_errors(reg), list)

    def test_defaults_are_read_the_way_the_registry_merges_them(self):
        reg = lock_ready()
        blog_of(reg, MACAT).pop("limits", None)
        reg["defaults"]["limits"] = {"max_posts_per_day": 1}
        self.assertEqual(publish_lock.lock_errors(reg), [])
        reg["defaults"]["limits"] = {"max_posts_per_day": 2}
        self.assertEqual(rules_in(publish_lock.lock_errors(reg)), {"L7"})


class PureHelperTest(unittest.TestCase):
    def test_posts_today_counts_dict_entries_with_that_date_only(self):
        history = ["문자열 항목", {"date": "2026-11-08", "topic": "어제"}, {"topic": "날짜 없음"}, None, 3, entry(), entry(slot=None)]
        self.assertEqual(publish_lock.posts_today(history, TODAY), 2)
        self.assertEqual(publish_lock.posts_today([], TODAY), 0)
        self.assertEqual(publish_lock.posts_today(history, "2026-11-08"), 1)

    def test_open_drafts_limit_reads_only_a_positive_integer_of_the_chance_entry(self):
        reg = lock_ready()
        self.assertEqual(publish_lock.open_drafts_limit(reg), 3)
        for bad in ("3", True, 0, None, 2.0):
            set_limit(reg, CHANCE, max_open_drafts=bad)
            self.assertIsNone(publish_lock.open_drafts_limit(reg), bad)
        self.assertIsNone(publish_lock.open_drafts_limit(today_registry()))
        self.assertIsNone(publish_lock.open_drafts_limit({"blogs": []}))
        reg = lock_ready()
        reg["defaults"]["limits"] = {"max_open_drafts": 2}
        blog_of(reg, CHANCE)["limits"] = {"max_posts_per_day": 1}
        self.assertEqual(publish_lock.open_drafts_limit(reg), 2)          # defaults 에서 물려받는다

    def test_flow_of_defaults_to_direct_like_the_registry(self):
        self.assertEqual(publish_lock.flow_of(today_registry()), "direct")
        self.assertEqual(publish_lock.flow_of(lock_ready()), "pr")
        self.assertIsNone(publish_lock.flow_of({"blogs": []}))
        self.assertEqual(publish_lock.flow_of(today_registry()), registry.DEFAULT_PUBLISH_FLOW)

    def test_the_read_only_history_reader_tells_missing_from_broken(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            self.assertEqual(publish_lock.read_history_strict(path), [])            # 파일이 없다 = 아직 글이 없다
            path.write_text("[1, 2]", encoding="utf-8")
            self.assertEqual(publish_lock.read_history_strict(path), [1, 2])
            for broken in ("{", "", "null", "{\"a\": 1}", "\"x\""):
                path.write_text(broken, encoding="utf-8")
                self.assertIsNone(publish_lock.read_history_strict(path), broken)
            path.write_bytes(b"\xff\xfe\x00bad")
            self.assertIsNone(publish_lock.read_history_strict(path))

    def test_the_constants_match_the_operator_decision(self):
        self.assertEqual((publish_lock.MAX_POSTS_PER_DAY, publish_lock.MAX_OPEN_DRAFTS), (1, 3))
        self.assertEqual(publish_lock.SAFE_MODES, ("off", "draft", "package"))
        self.assertNotIn("auto", publish_lock.SAFE_MODES)
        self.assertEqual(publish_lock.REQUIRED_FLOW, "pr")
        self.assertEqual(publish_lock.REQUIRED_FLOW, drafts.FLOW_PR)
        self.assertEqual(set(publish_lock.SAFE_MODES) | {"auto"}, set(registry.MODES))      # 레지스트리 모드 전체 = 안전 셋 + auto
        self.assertEqual(publish_lock.LANGUAGE_CODES, ("ko", "en"))                          # 허용 언어는 정확히 이 둘(검증 지적 4④ — ja 를 더하는 변이를 잡는다)
        self.assertEqual(publish_lock.SHADOW_ON_VALUES, ("1", "true", "yes", "on", "enabled"))
        self.assertEqual(publish_lock.SHADOW_OFF_VALUES, ("", "0", "false", "no", "off", "disabled"))
        self.assertEqual(set(publish_lock.SHADOW_ON_VALUES) & set(publish_lock.SHADOW_OFF_VALUES), set())


class UnmergedDraftBranchTest(unittest.TestCase):
    def test_unmerged_means_the_posts_are_not_on_main_yet(self):
        history = [entry(branch=BRANCH_A, merged_paths=["_posts/m/KR.md", "_posts/m/EN.md"]), entry(branch=BRANCH_B)]
        found = drafts.unmerged_draft_branches([BRANCH_A, BRANCH_B, BRANCH_C], history, exists=lambda path: path.startswith("_posts/m/"))
        self.assertEqual(found, [BRANCH_B, BRANCH_C])                      # A 는 병합됨(글이 main 에 있음), C 는 이력에 없어 열린 것으로 센다

    def test_names_this_flow_never_makes_are_ignored(self):
        found = drafts.unmerged_draft_branches(["ai/draft/odd", "ai/draft/2026-13-40-s9", "ai/draft/2026-11-09-s99", BRANCH_A], [], exists=lambda path: False)
        self.assertEqual(found, [BRANCH_A])

    def test_one_missing_path_keeps_the_branch_unmerged_and_duplicates_count_once(self):
        history = [entry(branch=BRANCH_A, merged_paths=["_posts/m/KR.md", "_posts/n/EN.md"])]
        self.assertEqual(drafts.unmerged_draft_branches([BRANCH_A, BRANCH_A], history, exists=lambda path: path == "_posts/m/KR.md"), [BRANCH_A])

    def test_direct_flow_entries_and_junk_entries_do_not_mark_a_branch_merged(self):
        direct = {"date": TODAY, "slot": 9, "branch": BRANCH_A, "paths": ["_posts/a/KR.md", "_posts/b/EN.md"]}          # flow 가 없다
        self.assertEqual(drafts.unmerged_draft_branches([BRANCH_A], ["x", None, direct, {"flow": "pr", "branch": 3}], exists=lambda path: True), [BRANCH_A])

    def test_an_empty_remote_has_nothing_unmerged(self):
        self.assertEqual(drafts.unmerged_draft_branches([], [entry(branch=BRANCH_A)]), [])

    def test_the_default_existence_check_looks_at_the_working_tree(self):
        with tempfile.TemporaryDirectory() as tmp, chdir(tmp):
            for rel in ("_posts/a/KR.md", "_posts/b/EN.md"):
                Path(rel).parent.mkdir(parents=True, exist_ok=True)
                Path(rel).write_text("x", encoding="utf-8")
            self.assertEqual(drafts.unmerged_draft_branches([BRANCH_A], [entry(branch=BRANCH_A)]), [])
            Path("_posts/b/EN.md").unlink()
            self.assertEqual(drafts.unmerged_draft_branches([BRANCH_A], [entry(branch=BRANCH_A)]), [BRANCH_A])


class GuardBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def guard(self, reg, **kwargs):
        return GuardRun(self.folder, reg, **kwargs)


class GuardOffTest(GuardBase):
    def test_with_the_lock_off_the_guard_reads_the_registry_and_nothing_else(self):
        """꺼짐 = 이전과 같다: 이력도 원격도 읽지 않고(원격 대역은 부르면 실패한다) 출력·요약이 없다 — 상태 줄도 없다(상태 줄은 잠금이 켜져 있을 때만 남는다)."""
        no_key = with_lock_off(lock_ready())
        drop_limit(no_key, CHANCE, "max_open_drafts")                     # 열린 초안 상한 값이 없으면(지금의 레지스트리) 이 규칙도 꺼져 있다
        for reg in (today_registry(), no_key, {"blogs": []}):
            result = self.guard(reg, history=[entry()], remote="unused")
            self.assertEqual((result.code, result.out, result.summary, result.status), (None, [], [], []))
        result = self.guard({"resume_lock": False}, history=[entry()], remote="unused")       # 키가 있어도 false 면 출력이 같다 — 상태 줄은 켜져 있을 때만 남는다
        self.assertEqual((result.code, result.out, result.summary, result.status), (None, [], [], []))

    def test_with_the_lock_off_a_missing_or_broken_history_does_not_matter(self):
        result = self.guard(today_registry(), raw_history="{ 망가진 파일")
        self.assertEqual((result.code, result.out), (None, []))

    def test_off_and_not_a_draft_flow_ignores_the_open_drafts_limit(self):
        reg = with_lock_off(lock_ready())
        set_in(reg, CHANCE, publish_flow="direct")
        self.assertEqual(self.guard(reg, remote="unused").code, None)    # direct 에는 초안이 없다 — 원격을 읽지 않는다

    def test_a_practice_run_and_a_shadow_run_never_count(self):
        reg = lock_ready()
        done = [entry()]
        self.assertEqual(self.guard(reg, history=done, dry_run=True, remote="unused").code, None)
        self.assertEqual(self.guard(reg, history=done, environ={"EVENT_NAME": "workflow_dispatch", "SHADOW_RUN": "1"}, remote="unused").code, None)
        for value in ("true", "yes", "on", "1", " 1 ", "enabled", "ENABLED", " Enabled "):
            self.assertEqual(self.guard(reg, history=done, environ={"SHADOW_RUN": value}, remote="unused").code, None, value)
        for value in ("0", "false", "no", "off", "disabled", "", " OFF "):
            self.assertEqual(self.guard(reg, history=done, environ={"SHADOW_RUN": value}).code, 0, value)       # 그림자가 아니면 센다


class GuardRegistryRuleTest(GuardBase):
    def test_a_rule_violation_stops_before_anything_is_made(self):
        for rule, cases in VIOLATIONS.items():
            for label, mutate in cases:
                with self.subTest(rule=rule, case=label):
                    result = self.guard(mutated(mutate), history=[], remote=[])
                    self.assertEqual(result.code, 1)
                    self.assertTrue(result.out[0].startswith("[SKIP] code=LOCK_BLOCKED rules="), result.out[0])
                    self.assertIn(rule, result.out[0])
                    errors = [line for line in result.out if line.startswith("::error::")]
                    self.assertEqual(errors, ["::error::제한 재개 잠금(resume_lock)이 켜져 있는데 설정이 규칙을 어깁니다 — 글을 만들지 않고 멈춥니다. 어긴 규칙은 위 줄과 실행 요약에 있습니다."])
                    self.assertTrue(any(line.startswith("[잠금 오류] 제한 재개 잠금 " + rule) for line in result.out))
                    self.assertIn("**LOCK_BLOCKED**", result.summary[0])

    def test_a_violation_stops_even_a_practice_run_and_a_shadow_run(self):
        reg = mutated(lambda r: set_in(r, CHANCE, publish_flow="direct"))
        self.assertEqual(self.guard(reg, dry_run=True).code, 1)
        self.assertEqual(self.guard(reg, environ={"SHADOW_RUN": "1"}).code, 1)                    # 규칙 위반은 읽기 전용 실행에도 우회가 없다(상한만 세지 않는다)

    def test_the_error_annotation_holds_only_a_fixed_sentence(self):
        reg = mutated(lambda r: set_in(r, MACAT, mode="x\n::error::가짜\n##[group]"))
        result = self.guard(reg)
        for line in result.out:
            if line.startswith("::error::"):
                self.assertEqual(line.count("::"), 2)                       # 맨 앞 `::error::` 의 두 쌍뿐
                self.assertNotIn("가짜", line)
        self.assertNotIn("##[", result.text)

    def test_a_compliant_registry_lets_a_normal_run_through(self):
        result = self.guard(lock_ready(), history=[], remote=[])
        self.assertEqual((result.code, result.out, result.summary), (None, [], []))
        self.assertEqual(result.status, [STATUS_PREFIX + "켜짐"])              # 잠금 키가 있으면 어느 실행이든 로그에 상태가 남는다


class GuardStatusTest(GuardBase):
    """검증 지적 1②: 잠금이 켜져 있으면 가드가 로그에 상태를 남긴다. 꺼져 있으면(키가 없든 false 든) 아무것도 남기지 않는다(출력이 이전과 바이트까지 같다 — 기준선과 견줘 확인). 꺼짐은 check 로 본다."""

    def test_off_no_line_whether_the_key_is_missing_or_false(self):
        explicit_false = today_registry()
        explicit_false["resume_lock"] = False
        for reg in (today_registry(), {"blogs": []}, {}, {"resume_lock": False}, explicit_false):
            result = self.guard(reg, history=[], remote="unused")
            self.assertEqual((result.status, result.out), ([], []))

    def test_the_line_is_the_first_thing_logged_and_it_precedes_a_stop(self):
        out = []
        (self.folder / "history.json").write_text(json.dumps([entry()]), encoding="utf-8")       # 오늘 이미 1건 → 하루 상한 건너뜀(SystemExit 0)
        with self.assertRaises(SystemExit):
            publish_lock.guard_start({"EVENT_NAME": "schedule"}, self.folder / "history.json", lambda: NOW, False, False, [].append, out=out.append,
                                     load=lambda: lock_ready(), remote_drafts=lambda: [])
        self.assertEqual(out[0], STATUS_PREFIX + "켜짐")
        self.assertEqual(len([line for line in out if line.startswith(STATUS_PREFIX)]), 1)

    def test_the_line_is_logged_for_a_practice_run_an_image_fix_practice_and_a_shadow_run_too(self):
        for kwargs in (dict(dry_run=True), dict(fix_images=True, dry_run=True), dict(environ={"SHADOW_RUN": "1"})):
            self.assertEqual(self.guard(lock_ready(), history=[entry()], **kwargs).status, [STATUS_PREFIX + "켜짐"], kwargs)

    def test_a_blocked_run_says_why_instead_of_the_status(self):
        result = self.guard(mutated(lambda r: set_in(r, CHANCE, publish_flow="direct")), history=[], remote=[])
        self.assertEqual((result.code, result.status), (1, []))


class ShadowValueTest(GuardBase):
    """검증 지적 3: SHADOW_RUN 켜짐·꺼짐 값 집합을 GATE 와 같게 맞추고(켜짐 1·true·yes·on·enabled / 꺼짐 비움·0·false·no·off·disabled), 그 밖의 값은 잠금이 켜져 있을 때 가드가 실행을 거절한다(종료 2)."""

    def test_the_state_reads_case_and_spaces(self):
        for value in publish_lock.SHADOW_ON_VALUES:
            for text in (value, value.upper(), "  %s " % value.title()):
                self.assertEqual(publish_lock.shadow_state({"SHADOW_RUN": text}), "on", text)
        for value in publish_lock.SHADOW_OFF_VALUES:
            for text in (value, value.upper(), "  %s " % value):
                self.assertEqual(publish_lock.shadow_state({"SHADOW_RUN": text}), "off", text)
        self.assertEqual(publish_lock.shadow_state({}), "off")
        self.assertEqual(publish_lock.shadow_state(None), "off")
        for value in ("maybe", "2", "y", "enable", "tru", "t", "-1", "on off", "ㅇㅇ"):
            self.assertEqual(publish_lock.shadow_state({"SHADOW_RUN": value}), "invalid", value)

    def test_every_on_value_skips_the_counting_and_every_off_value_counts(self):
        done = [entry()]
        for value in publish_lock.SHADOW_ON_VALUES:
            self.assertEqual(self.guard(lock_ready(), history=done, environ={"SHADOW_RUN": value}, remote="unused").code, None, value)
        for value in publish_lock.SHADOW_OFF_VALUES:
            self.assertEqual(self.guard(lock_ready(), history=done, environ={"SHADOW_RUN": value}).code, 0, value)

    def test_an_unknown_value_is_refused_with_exit_2_when_the_lock_is_on(self):
        for value in ("maybe", "2", "y", "enable", " tru "):
            result = self.guard(lock_ready(), history=[], remote=[], environ={"SHADOW_RUN": value})
            with self.subTest(value=value):
                self.assertEqual(result.code, 2)
                self.assertEqual(result.out[0], "[SKIP] code=LOCK_BLOCKED reason=SHADOW_RUN_VALUE")
                errors = [line for line in result.out if line.startswith("::error::")]
                self.assertEqual(errors, ["::error::SHADOW_RUN 값을 알 수 없어 실행하지 않습니다 — 켜짐(1·true·yes·on·enabled) 또는 꺼짐(비움·0·false·no·off·disabled)으로 적으세요."])
                self.assertTrue(any(value.strip() in line for line in result.out if line.startswith("[잠금 오류] ")), result.out)        # 주석에는 고정 문장만 — 값은 로그 줄(따옴표 안)에만
                self.assertIn("**LOCK_BLOCKED**", result.summary[0])

    def test_an_unknown_value_is_refused_even_for_a_practice_run_and_an_image_fix_practice(self):
        for kwargs in (dict(dry_run=True), dict(fix_images=True, dry_run=True)):
            self.assertEqual(self.guard(lock_ready(), environ={"SHADOW_RUN": "maybe"}, **kwargs).code, 2, kwargs)

    def test_with_the_lock_off_the_value_is_not_looked_at_so_the_output_stays_as_before(self):
        for reg in (today_registry(), {"resume_lock": False}):
            result = self.guard(reg, history=[entry()], environ={"SHADOW_RUN": "maybe"}, remote="unused")
            self.assertEqual((result.code, result.out, result.summary), (None, [], []))

    def test_with_the_lock_off_an_unknown_value_does_not_skip_the_open_drafts_limit_but_an_on_value_does(self):
        """독립 재검증 D5(변이 W05 `shadow == "on"` → `!= "off"`): 잠금은 꺼져 있어도 max_open_drafts 값이 있고 pr 흐름이면 열린 초안을 센다 — 그림자 켜짐 값만 건너뛰고 모르는 값은 센다."""
        reg = with_lock_off(lock_ready())                                                        # 잠금 키 없음 · publish_flow pr · max_open_drafts 3
        names = [BRANCH_A, BRANCH_B, BRANCH_C]
        for value in ("maybe", "2", "y", "enable"):
            result = self.guard(reg, history=[], remote=names, exists=lambda path: False, environ={"SHADOW_RUN": value})
            with self.subTest(unknown=value):
                self.assertEqual(result.code, 0)
                self.assertEqual(result.out[0], "[SKIP] code=OPEN_DRAFTS_CAP open=3 limit=3")
        for value in ("1", "on", "enabled", " ENABLED "):
            with self.subTest(on=value):
                self.assertEqual(self.guard(reg, history=[], remote="unused", environ={"SHADOW_RUN": value}).code, None)         # 세지 않으므로 원격을 읽지도 않는다

    def test_the_value_sets_match_the_generator_when_the_shadow_code_is_merged(self):
        try:
            from pipeline import shadow_run  # noqa: F401  (GATE 묶음의 읽기 전용 실행 경로)
        except ImportError:
            self.skipTest("이 가지에는 그림자 실행 코드(pipeline/shadow_run.py, GATE 묶음)가 없다 — 병합 뒤에는 생성기의 SHADOW_RUN 판정이 같은 값 집합인지 이 시험이 견준다")
        self.assertTrue(hasattr(g, "shadow_run_on"), "그림자 실행 코드가 있는데 생성기에 shadow_run_on 이 없다 — GATE 의 인터페이스가 바뀌었는지 확인하세요")
        for value in publish_lock.SHADOW_ON_VALUES:
            for text in (value, value.upper(), " %s " % value):
                with mock.patch.dict(os.environ, {"SHADOW_RUN": text}):
                    self.assertTrue(g.shadow_run_on(), text)
        for value in publish_lock.SHADOW_OFF_VALUES:
            for text in (value, value.upper(), " %s " % value):
                with mock.patch.dict(os.environ, {"SHADOW_RUN": text}):
                    self.assertFalse(g.shadow_run_on(), text)


class KeyTypoTest(unittest.TestCase):
    """검증 지적 1(2026-11-09): 키가 없으면 잠금이 꺼진 것이라, resume_lock 을 오타(resume_lok·대소문자·하이픈·뒤 공백)로 적거나 defaults·블로그 항목 안에 두면 켠 줄 알았는데 꺼진 채로 통과했다.
    지금은 검증기가 알려진 최상위 키만 허용하고(K1) 잠금 키의 위치를 보며(K2), 실행 시(가드·chance_flow·Blogger 러너·check·check-direct)에도 멈춘다. 잠금 키가 없는 지금의 레지스트리는 그대로 통과한다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def variants(self):
        for base_label, base in (("켠 레지스트리", lock_ready), ("지금의 레지스트리", today_registry)):
            for label, mutate in KEY_TYPOS:
                reg = base()
                mutate(reg)
                yield "%s · %s" % (base_label, label), reg

    def test_the_known_top_level_keys_are_pinned_and_the_real_registry_uses_only_them(self):
        self.assertEqual(publish_lock.KNOWN_TOP_LEVEL_KEYS, ("_doc", "schema_version", "shared_secrets", "defaults", "blogs", "resume_lock"))
        keys = set(real_registry())
        self.assertLessEqual(keys, set(publish_lock.KNOWN_TOP_LEVEL_KEYS))
        self.assertEqual(keys - {"resume_lock"}, set(publish_lock.KNOWN_TOP_LEVEL_KEYS) - {"resume_lock"})        # 잠금을 뺀 알려진 키는 지금 레지스트리에 모두 있다
        self.assertEqual([rule for rule, _text in publish_lock.KEY_RULES], ["K1", "K2"])

    def test_the_real_registry_and_a_registry_with_the_proper_key_pass_the_key_rules(self):
        for reg in (real_registry(), today_registry(), lock_ready()):
            self.assertEqual(publish_lock.lock_key_problems(reg), [])
            self.assertEqual([error for error in registry.validate_registry(reg) if error.startswith("레지스트리 키 K")], [])
        self.assertEqual(registry.validate_registry(real_registry()), [])                    # 잠금 키가 없는 지금의 blogs.json 은 그대로 통과한다

    def test_every_typo_and_misplacement_is_exactly_one_validator_error(self):
        count = 0
        for label, reg in self.variants():
            count += 1
            with self.subTest(label):
                key_errors = [error for error in registry.validate_registry(reg) if error.startswith("레지스트리 키 K")]
                self.assertEqual(len(key_errors), 1, key_errors)
                self.assertIn("resume_lock", key_errors[0])
                self.assertEqual(registry.validate_registry(reg), key_errors)                  # 그 밖의 오류는 없다 — 막는 것은 이 규칙뿐이다
                self.assertEqual(publish_lock.lock_state(reg), "off")                          # 잠금 값 읽기는 이 오타를 못 본다 — 그래서 키 규칙이 필요하다
        self.assertEqual(count, 2 * len(KEY_TYPOS))
        self.assertEqual(len(KEY_TYPOS), 9)                                                   # 요청 6 + 전부 대문자 1 + 두 단계 깊이 둘(독립 재검증 D1)

    def test_the_message_says_what_is_wrong_and_where(self):
        reg = lock_ready()
        reg["resume_lok"] = reg.pop("resume_lock")
        errors = publish_lock.lock_key_problems(reg)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("레지스트리 키 K1: 최상위 키 'resume_lok' 는 알려진 키가 아닙니다 — resume_lock 오타로 보입니다."), errors[0])
        self.assertIn("오타면 잠금이 꺼진 채로 통과합니다", errors[0])
        reg = lock_ready()
        reg["resume_lock "] = reg.pop("resume_lock")
        self.assertIn("'resume_lock '", publish_lock.lock_key_problems(reg)[0])                  # 뒤 공백이 보이게 따옴표째 적는다
        reg = lock_ready()
        reg["defaults"]["resume_lock"] = True
        errors = publish_lock.lock_key_problems(reg)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("레지스트리 키 K2: defaults 안에 'resume_lock' 가 있습니다"), errors[0])
        self.assertIn("최상위", errors[0])
        reg = lock_ready()
        blog_of(reg, CHANCE)["resume_lock"] = False
        self.assertIn("블로그 'chance' 안에 'resume_lock' 가 있습니다", publish_lock.lock_key_problems(reg)[0])

    def test_a_typo_next_to_the_proper_key_is_still_an_error_and_a_proper_key_alone_is_not(self):
        reg = lock_ready()
        reg["resume_lok"] = True
        self.assertEqual(len(publish_lock.lock_key_problems(reg)), 1)
        self.assertEqual(publish_lock.lock_state(reg), "on")                                   # 진짜 키는 켜짐으로 읽히지만 오타 키가 남아 있으면 멈춘다
        reg = lock_ready()
        self.assertEqual(publish_lock.lock_key_problems(reg), [])

    def test_a_key_that_does_not_look_like_the_lock_is_a_validator_error_but_does_not_stop_a_run(self):
        reg = today_registry()
        reg["extra_setting"] = 1
        errors = [error for error in registry.validate_registry(reg) if error.startswith("레지스트리 키 K")]
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("레지스트리 키 K1: 알 수 없는 최상위 키 'extra_setting' 가 있습니다"), errors[0])
        self.assertIn(", ".join(publish_lock.KNOWN_TOP_LEVEL_KEYS), errors[0])                  # 허용 목록을 보여 준다
        self.assertNotIn("오타", errors[0])
        self.assertEqual(publish_lock.lock_key_problems(reg), [])                                # 실행 시에는 새 실패 방식을 만들지 않는다(잠금과 관계없는 키)
        run = GuardRun(self.folder, reg, history=[], remote="unused")
        self.assertEqual((run.code, run.out, run.status), (None, [], []))

    CLOSE_NAMES = ("resume_lok", "Resume_Lock", "RESUME-LOCK", "resumelock", "resume_lock ", " resume_lock", "resume_lock_v2", "my-resume-lock", "resumlok", "rsumelck", "reumelok",
                   "resume_lcok", "resum_lok", "reesume_lock", "resume lock",
                   "ｒｅｓｕｍｅ_lock", "resume_ｌｏｃｋ", "ＲＥＳＵＭＥ－ＬＯＣＫ", "r\u0435sume_lock", "resume_lock\u200b")
    ORDINARY_NAMES = ("block", "clock", "unlock", "locked", "resumed", "blocklist", "deadlock", "resume_after", "lock", "resume", "publish_lock", "lock_resume", "resume_unlocked_at")

    def test_only_names_close_to_resume_lock_look_like_a_typo(self):
        """독립 재검증 D2: 예전에는 줄인 이름에 resume 이나 lock 낱말이 든 모르는 키(block·clock·unlock·locked·resumed·blocklist·resume_after …)가 모두 오타라고 안내되고 실행도 멈췄다.
        지금은 이름이 resumelock 을 품거나 편집 거리 2 이내일 때만 오타로 본다."""
        for name in self.CLOSE_NAMES:
            reg = today_registry()
            reg[name] = True
            with self.subTest(close=name):
                self.assertTrue(publish_lock._looks_like_lock_key(name))
                problems = publish_lock.lock_key_problems(reg)
                self.assertEqual(len(problems), 1)
                self.assertIn("resume_lock 오타로 보입니다", problems[0])
        for name in self.ORDINARY_NAMES:
            reg = today_registry()
            reg[name] = True
            with self.subTest(ordinary=name):
                self.assertFalse(publish_lock._looks_like_lock_key(name))
                self.assertEqual(publish_lock.lock_key_problems(reg), [])                       # 실행 시에는 멈추지 않는다
        for name in publish_lock.KNOWN_TOP_LEVEL_KEYS:
            self.assertFalse(publish_lock._looks_like_lock_key(name) and name != "resume_lock", name)

    def test_an_ordinary_unknown_key_is_called_unknown_not_a_typo_and_does_not_stop_a_run(self):
        for name in self.ORDINARY_NAMES:
            for base in (lock_ready, today_registry):
                reg = base()
                reg[name] = 1
                with self.subTest(name=name, base=base.__name__):
                    errors = [error for error in registry.validate_registry(reg) if error.startswith("레지스트리 키 K")]
                    self.assertEqual(len(errors), 1)                                              # 알려진 키만 허용하는 K1 은 그대로 오류다
                    self.assertTrue(errors[0].startswith("레지스트리 키 K1: 알 수 없는 최상위 키 %s 가 있습니다" % publish_lock._shown(name)), errors[0])
                    self.assertNotIn("오타", errors[0])
                    run = GuardRun(self.folder, reg, history=[], remote=[])
                    self.assertEqual(run.code, None)                                              # 실행은 이 키 때문에 멈추지 않는다
                    self.assertEqual(run.status, [STATUS_PREFIX + "켜짐"] if base is lock_ready else [])

    def test_the_squashed_name_folds_case_separators_and_full_width_letters(self):
        """줄인 이름: 전각·호환 글자는 보통 글자로(NFKC), 소문자로, 공백·밑줄·하이픈은 뺀다 — 검증자의 233변형에서 전각 이름은 예전 판정이 잡았으므로 좁히면서 놓치지 않는다."""
        squash = publish_lock._squash
        self.assertEqual(squash("Resume-Lock "), "resumelock")
        self.assertEqual(squash(" resume\tlock"), "resumelock")
        self.assertEqual(squash("ｒｅｓｕｍｅ＿ｌｏｃｋ"), "resumelock")                             # 전각 글자와 전각 밑줄
        self.assertEqual(squash("ＲＥＳＵＭＥ－ＬＯＣＫ"), "resumelock")                             # 전각 대문자와 전각 하이픈
        self.assertEqual(squash("ℝesume_lock"), "resumelock")                                   # 호환 글자(NFKC 가 먼저, 소문자는 그 뒤)
        self.assertEqual(squash(3), "3")
        self.assertEqual(squash(None), "none")
        self.assertEqual(squash("\ud800"), "\ud800")                                            # 짝 없는 서로게이트도 예외 없이
        self.assertEqual(publish_lock.LOCK_KEY_SQUASHED, squash(publish_lock.LOCK_KEY))

    def test_the_edit_distance_helper_has_exact_boundaries(self):
        within = publish_lock._within_edits
        self.assertTrue(within("resumelock", "resumelock", 0))
        self.assertFalse(within("resumelok", "resumelock", 0))
        self.assertTrue(within("resumelok", "resumelock", 1))                                   # 글자 하나 빠짐
        self.assertTrue(within("resumelockx", "resumelock", 1))                                 # 글자 하나 더함
        self.assertTrue(within("resumelacks", "resumelock", 2))                                 # 바꿈 둘
        self.assertTrue(within("resumelcok", "resumelock", 2))                                  # 자리 바뀜(교환)은 둘
        self.assertFalse(within("resumlok", "resumelock", 1))
        self.assertTrue(within("resumlok", "resumelock", 2))
        self.assertFalse(within("resumlk", "resumelock", 2))                                    # 셋
        self.assertFalse(within("x" * 10000, "resumelock", 2))                                  # 길이 차이만으로 거짓 — 계산하지 않는다
        self.assertTrue(within("", "ab", 2))
        self.assertFalse(within("", "abc", 2))
        self.assertEqual(publish_lock.LOCK_KEY_SQUASHED, publish_lock._squash(publish_lock.LOCK_KEY))
        self.assertEqual((publish_lock.LOCK_KEY_EDITS, publish_lock.MAX_KEY_SCAN_DEPTH, publish_lock.MAX_KEY_MESSAGES), (2, 16, 20))

    def test_the_misplaced_key_rule_sees_typos_too_not_only_the_exact_key(self):
        """독립 재검증 D5(변이 W08·W09): K2 는 '정확한 resume_lock' 만이 아니라 오타(대소문자·하이픈·글자 하나 빠짐)와 resume_lock 을 품은 이름도 본다 — 문서의 약속을 못박는다."""
        for name in ("Resume_Lock", "resume_lok", "RESUME-LOCK", "resume_lock_v2", "resume_lock "):
            for path, where in ((("defaults",), "defaults"), ((CHANCE,), "블로그 'chance'"), ((MACAT,), "블로그 'blogger_macat'")):
                reg = lock_ready()
                put_in(reg, path, name)
                with self.subTest(name=name, where=where):
                    problems = publish_lock.lock_key_problems(reg)
                    self.assertEqual(len(problems), 1)
                    self.assertTrue(problems[0].startswith("레지스트리 키 K2: %s 안에 %s 가 있습니다" % (where, publish_lock._shown(name))), problems[0])
                    self.assertEqual([error for error in registry.validate_registry(reg) if error.startswith("레지스트리 키 K")], problems)
        for name in ("limits_note", "block", "resume_after"):                                    # 이름이 다르면 직속에 있어도 오류가 아니다
            reg = lock_ready()
            put_in(reg, ("defaults",), name)
            self.assertEqual(publish_lock.lock_key_problems(reg), [], name)

    def test_odd_inputs_never_raise(self):
        for reg in (None, [], "x", 3, {}, {"defaults": None, "blogs": "x"}, {"defaults": [], "blogs": [1, None, {"key": 3}]}, {1: 2, None: 3}):
            self.assertIsInstance(publish_lock.lock_key_problems(reg), list)
            self.assertIsInstance(publish_lock.registry_errors(reg), list)

    def test_the_guard_stops_before_anything_is_made(self):
        for label, reg in self.variants():
            run = GuardRun(self.folder, reg, history=[], remote=[])
            with self.subTest(label):
                self.assertEqual(run.code, 1)
                self.assertTrue(run.out[0].startswith("[SKIP] code=LOCK_BLOCKED rules=K"), run.out[0])
                self.assertEqual([line for line in run.out if line.startswith("::error::")], ["::error::" + publish_lock.KEY_ERROR])
                self.assertTrue(any(line.startswith("[잠금 오류] 레지스트리 키 K") for line in run.out))
                self.assertIn("**LOCK_BLOCKED**", run.summary[0])

    def test_the_guard_stops_a_practice_run_an_image_fix_and_a_shadow_run_too(self):
        reg = lock_ready()
        reg["resume_lok"] = reg.pop("resume_lock")
        for kwargs in (dict(dry_run=True), dict(fix_images=True), dict(fix_images=True, dry_run=True), dict(environ={"SHADOW_RUN": "1"})):
            self.assertEqual(GuardRun(self.folder, reg, **kwargs).code, 1, kwargs)

    def test_chance_flow_stops_so_no_later_step_of_the_workflow_runs(self):
        for label, reg in self.variants():
            with self.subTest(label), self.assertRaises(drafts.DraftFlowError) as caught:
                drafts.chance_flow(write_registry(self.folder, reg))
            self.assertIn("제한 재개 잠금 키가 잘못 적혀 있어 잠금 상태를 알 수 없습니다", str(caught.exception))

    def test_the_block_helper_names_the_key_problem_not_a_rule_violation(self):
        reg = lock_ready()
        reg["resume_lok"] = reg.pop("resume_lock")
        block = publish_lock.registry_block(reg)
        self.assertEqual((block.code, block.error), (publish_lock.CODE_BLOCKED, publish_lock.KEY_ERROR))
        self.assertTrue(all(line.startswith("레지스트리 키 K1:") for line in block.lines))
        both = lock_ready()
        both["resume_lok"] = True
        set_in(both, CHANCE, publish_flow="direct")
        block = publish_lock.registry_block(both)
        self.assertEqual(block.error, publish_lock.KEY_ERROR)                                    # 키 문제가 먼저다(켜진 것인지부터 알 수 없다)
        self.assertEqual(rules_in([line for line in block.lines if line.startswith("제한 재개 잠금 ")]), {"L1", "L3"})
        self.assertIsNone(publish_lock.registry_block(lock_ready()))
        self.assertIsNone(publish_lock.registry_block(today_registry()))


class DeepKeyTest(unittest.TestCase):
    """독립 재검증 D1(2026-11-09): K2 는 defaults·블로그 항목의 직속 키만 봐서 chance.limits·defaults.limits 같은 두 단계 이상 깊은 곳의 resume_lock 은 검증기·가드가 못 막았다 —
    켠 사본에서 resume_lock 을 최상위에서 빼 chance.limits 안에 두면 하루 상한 없이 둘째 글이 만들어졌다. 지금은 최상위 밖 어디든(깊이 상한 MAX_KEY_SCAN_DEPTH) 오류다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    @staticmethod
    def where(path):
        return ".".join(path) if path[0] == "defaults" else "블로그 '%s'" % path[0] + "".join("." + step for step in path[1:])

    def places(self):
        for base_label, base in (("켠 레지스트리", lock_ready), ("지금의 레지스트리", today_registry)):
            for path in DEEP_PLACES:
                for key in ("resume_lock", "resume_lok", "Resume-Lock"):
                    reg = base()
                    reg.pop("resume_lock", None)                      # 진짜 최상위 키를 '빼서' 옮긴 모양(검증자 재현)
                    put_in(reg, path, key)
                    yield "%s · %s · %s" % (base_label, ".".join(path), key), path, key, reg

    def test_every_deep_placement_is_exactly_one_validator_error_that_names_the_place(self):
        count = 0
        for label, path, key, reg in self.places():
            count += 1
            with self.subTest(label):
                key_errors = [error for error in registry.validate_registry(reg) if error.startswith("레지스트리 키 K")]
                self.assertEqual(len(key_errors), 1, key_errors)
                self.assertTrue(key_errors[0].startswith("레지스트리 키 K2: %s 안에 %s 가 있습니다" % (self.where(path), publish_lock._shown(key))), key_errors[0])
                self.assertEqual(publish_lock.lock_key_problems(reg), key_errors)
                self.assertEqual(publish_lock.lock_state(reg), "off")                               # 잠금 값 읽기는 이 자리를 못 본다 — 그래서 위치 규칙이 필요하다
        self.assertEqual(count, 2 * len(DEEP_PLACES) * 3)

    def test_the_verifier_reproduction_a_second_post_without_a_cap_is_stopped(self):
        """켠 사본에서 resume_lock 을 최상위에서 빼 chance.limits·defaults.limits 안에 두고 오늘 이미 1건 — 예전에는 잠금이 꺼진 줄로 읽혀 가드가 조용히 통과했다."""
        for path in (("chance", "limits"), ("defaults", "limits")):
            reg = lock_ready()
            reg.pop("resume_lock")
            put_in(reg, path)
            for kwargs in (dict(), dict(environ={"EVENT_NAME": "workflow_dispatch"})):
                run = GuardRun(self.folder, reg, history=[entry()], remote=[], **kwargs)
                with self.subTest(path=path, kwargs=kwargs):
                    self.assertEqual(run.code, 1)                                                  # None(통과) 이 아니다
                    self.assertTrue(run.out[0].startswith("[SKIP] code=LOCK_BLOCKED rules=K2"), run.out[0])
                    self.assertEqual([line for line in run.out if line.startswith("::error::")], ["::error::" + publish_lock.KEY_ERROR])

    def test_every_deep_placement_stops_the_guard_and_chance_flow(self):
        for label, path, key, reg in self.places():
            run = GuardRun(self.folder, reg, history=[], remote=[])
            with self.subTest(label):
                self.assertEqual(run.code, 1)
                self.assertTrue(run.out[0].startswith("[SKIP] code=LOCK_BLOCKED rules=K2"), run.out[0])
                with self.assertRaises(drafts.DraftFlowError) as caught:
                    drafts.chance_flow(write_registry(self.folder, reg))
                self.assertIn("제한 재개 잠금 키가 잘못 적혀 있어 잠금 상태를 알 수 없습니다", str(caught.exception))

    def test_a_key_inside_a_list_of_dicts_is_found_and_the_place_is_spelled_out(self):
        reg = lock_ready()
        reg["defaults"]["extra"] = [{"x": 1}, {"resume_lock": True}]
        problems = publish_lock.lock_key_problems(reg)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("레지스트리 키 K2: defaults.extra[1] 안에 'resume_lock' 가 있습니다"), problems[0])
        reg = lock_ready()
        blog_of(reg, CHANCE)["schedule"]["slots_extra"] = [[{"resume_lok": 1}]]
        self.assertTrue(publish_lock.lock_key_problems(reg)[0].startswith("레지스트리 키 K2: 블로그 'chance'.schedule.slots_extra[0][0] 안에 'resume_lok' 가 있습니다"))

    def test_the_depth_limit_is_inclusive_and_anything_deeper_is_an_error_that_stops_the_run(self):
        limit = publish_lock.MAX_KEY_SCAN_DEPTH

        def chain(extra_levels):                                           # defaults(깊이 1) 아래로 사전을 extra_levels 개 더 쌓는다
            reg = lock_ready()
            node = reg["defaults"]
            for _ in range(extra_levels):
                node = node.setdefault("n", {})
            return reg, node
        reg, node = chain(limit - 1)                                       # 깊이가 정확히 limit 인 사전
        node["resume_lock"] = True
        problems = publish_lock.lock_key_problems(reg)
        self.assertEqual(len(problems), 1)
        self.assertIn("안에 'resume_lock' 가 있습니다", problems[0])                                  # 상한 안이라 찾는다
        reg, node = chain(limit)                                           # 한 단계 더 깊다 — 안을 못 본다
        node["resume_lock"] = True
        problems = publish_lock.lock_key_problems(reg)
        self.assertEqual(len(problems), 1)
        self.assertIn("너무 깊어(깊이 %d 초과)" % limit, problems[0])
        reg, node = chain(limit)
        self.assertEqual(GuardRun(self.folder, reg, history=[], remote=[]).code, 1)

    def test_a_very_deep_registry_is_an_error_and_never_a_recursion_crash(self):
        reg = lock_ready()
        node = reg["defaults"]
        for _ in range(5000):
            node["n"] = {}
            node = node["n"]
        problems = publish_lock.lock_key_problems(reg)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("레지스트리 키 K2: 레지스트리 구조가 너무 깊어"), problems[0])
        self.assertEqual(len(publish_lock.registry_errors(reg)), 1)
        run = GuardRun(self.folder, reg, history=[], remote=[])
        self.assertEqual(run.code, 1)

    def test_a_cycle_or_a_shared_substructure_is_visited_once(self):
        reg = lock_ready()
        reg["defaults"]["loop"] = reg["defaults"]
        reg["defaults"]["limits"]["resume_lock"] = True
        self.assertEqual(len(publish_lock.lock_key_problems(reg)), 1)                              # 순환이어도 끝나고 한 번만 센다
        shared = {"resume_lock": True}
        node = shared
        for _ in range(6):
            node = {str(index): node for index in range(10)}                                        # 같은 하위 구조를 열 곳이 가리킨다 — 길은 10의 6제곱 가지
        reg = lock_ready()
        reg["defaults"]["fan"] = node
        problems = publish_lock.lock_key_problems(reg)
        self.assertEqual(len(problems), 1)                                                         # 한 번씩만 훑으므로 한 건이다(세 번 훑으면 상한 20 을 채운 줄이 나온다)

    def test_the_scan_never_raises_on_odd_containers(self):
        reg = lock_ready()
        reg["defaults"][3] = {"resume_lok": 1}                                                    # 문자열이 아닌 키(JSON 에는 없지만 사전에는 들어갈 수 있다)
        reg["defaults"][None] = [None, 1, "x", {"k": [{}]}, [[], [None]]]
        reg["defaults"]["empty"] = {}
        problems = publish_lock.lock_key_problems(reg)
        self.assertEqual(len(problems), 1)
        self.assertIn("안에 'resume_lok' 가 있습니다", problems[0])

    def test_the_real_registry_and_the_registries_of_the_other_branches_have_no_key_problem(self):
        self.assertEqual(publish_lock.lock_key_problems(real_registry()), [])
        for reg in (today_registry(), lock_ready()):
            self.assertEqual(publish_lock.lock_key_problems(reg), [])
            self.assertEqual(publish_lock.registry_errors(reg), [])


class KeyOutputCapTest(unittest.TestCase):
    """독립 재검증 D4: 모르는 키(오타 모양 포함)가 아주 많아도 검증기·가드의 오류 출력은 앞 MAX_KEY_MESSAGES 개와 '외 N개' 한 줄이다(2만 개에서 4MB 였다)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def key_lines(self, errors):
        return [error for error in errors if error.startswith("레지스트리 키 K")]

    def test_many_unknown_top_level_keys_give_a_short_validator_output(self):
        cap = publish_lock.MAX_KEY_MESSAGES
        reg = today_registry()
        for index in range(5000):
            reg["extra_%d" % index] = index
        lines = self.key_lines(registry.validate_registry(reg))
        self.assertEqual(len(lines), cap + 1)
        self.assertIn("… 외 %d개의 최상위 키가 더 있습니다(출력은 앞 %d개만 냅니다)" % (5000 - cap, cap), lines[-1])
        self.assertLess(sum(len(line) for line in lines), 20000)
        self.assertEqual(publish_lock.lock_key_problems(reg), [])                                   # 오타 모양이 아니라 실행은 멈추지 않는다

    def test_the_boundary_is_exact_twenty_unknown_keys_have_no_summary_line_and_twenty_one_have_one(self):
        cap = publish_lock.MAX_KEY_MESSAGES
        for total, expected in ((cap, cap), (cap + 1, cap + 1), (cap + 2, cap + 1)):
            reg = today_registry()
            for index in range(total):
                reg["extra_%d" % index] = 1
            lines = self.key_lines(registry.validate_registry(reg))
            with self.subTest(total=total):
                self.assertEqual(len(lines), expected)
        reg = today_registry()
        for index in range(cap + 1):
            reg["extra_%d" % index] = 1
        self.assertIn("… 외 1개의 최상위 키가 더 있습니다", self.key_lines(registry.validate_registry(reg))[-1])

    def test_many_typo_shaped_top_level_keys_cap_the_runtime_output_too(self):
        cap = publish_lock.MAX_KEY_MESSAGES
        reg = lock_ready()
        for index in range(3000):
            reg["resume_lock_%d" % index] = True                                                     # resume_lock 을 품은 이름 — 오타 모양
        problems = publish_lock.lock_key_problems(reg)
        self.assertEqual(len(problems), cap + 1)
        self.assertIn("… 외 %d개의 최상위 키가 더 있습니다" % (3000 - cap), problems[-1])
        run = GuardRun(self.folder, reg, history=[], remote=[])
        self.assertEqual(run.code, 1)
        self.assertLess(len(run.out), cap + 10)                                                      # 로그도 작다
        self.assertLess(len(run.summary[0]), 20000)

    def test_many_misplaced_keys_cap_the_output(self):
        cap = publish_lock.MAX_KEY_MESSAGES
        reg = lock_ready()
        for index in range(3000):
            reg["defaults"]["resume_lock_%d" % index] = True
        problems = publish_lock.lock_key_problems(reg)
        self.assertEqual(len(problems), cap + 1)
        self.assertIn("… 외 %d개의 resume_lock 모양 이름이 최상위 밖에 더 있습니다(출력은 앞 %d개만 냅니다)" % (3000 - cap, cap), problems[-1])
        self.assertEqual(len(self.key_lines(registry.validate_registry(reg))), cap + 1)

    def test_a_registry_with_a_few_problems_lists_each_without_a_summary(self):
        reg = lock_ready()
        reg["defaults"]["resume_lock"] = True
        reg["resume_lok"] = True
        lines = self.key_lines(registry.validate_registry(reg))
        self.assertEqual(len(lines), 2)
        self.assertFalse(any("… 외" in line for line in lines))


class GuardFixImagesTest(GuardBase):
    def test_the_image_fix_that_commits_straight_to_main_is_refused_with_the_lock_on(self):
        result = self.guard(lock_ready(), fix_images=True, history=[])
        self.assertEqual(result.code, 1)
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_BLOCKED reason=FIX_IMAGES")
        self.assertIn("::error::제한 재개 잠금이 켜져 있어 기존 글 이미지 교체(main 직접 커밋)를 멈춥니다.", result.out)
        self.assertIn("이슈 수정 요청(수정안 PR)", result.text)

    def test_a_practice_image_fix_writes_nothing_so_it_may_run(self):
        self.assertEqual(self.guard(lock_ready(), fix_images=True, dry_run=True).code, None)

    def test_with_the_lock_off_the_image_fix_is_unchanged(self):
        self.assertEqual(self.guard(today_registry(), fix_images=True).code, None)
        self.assertEqual(self.guard(today_registry(), fix_images=True, dry_run=True).code, None)

    def test_an_unreadable_registry_stops_only_the_path_that_never_read_it(self):
        def unreadable():
            raise registry.RegistryError("읽을 수 없음")
        out, summary = [], []
        with self.assertRaises(SystemExit) as caught:
            publish_lock.guard_start({}, self.folder / "history.json", lambda: NOW, True, False, summary.append, out=out.append, load=unreadable)
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("::error::레지스트리를 읽을 수 없어 제한 재개 잠금 상태를 알 수 없습니다 — 기존 글 이미지 교체를 멈춥니다.", out)
        for fix_images, dry_run in ((False, False), (True, True), (False, True)):
            out2 = []
            publish_lock.guard_start({}, self.folder / "history.json", lambda: NOW, fix_images, dry_run, summary.append, out=out2.append, load=unreadable)
            self.assertEqual(out2, [], (fix_images, dry_run))              # 글을 만드는 길은 drafts.chance_flow 가 읽지 못하면 이미 멈춘다 — 기존 동작을 바꾸지 않는다

    def test_a_registry_that_is_not_an_object_counts_as_unreadable(self):
        out = []
        with self.assertRaises(SystemExit):
            publish_lock.guard_start({}, self.folder / "history.json", lambda: NOW, True, False, [].append, out=out.append, load=lambda: ["x"])


class GuardDailyCapTest(GuardBase):
    def test_one_post_today_stops_the_next_run_whatever_slot_it_is_for(self):
        result = self.guard(lock_ready(), history=[entry(slot=9)])
        self.assertEqual(result.code, 0)
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_DAILY_CAP date=2026-11-09 today=1 cap=1")
        self.assertTrue(any("하루 상한(1건)에 도달" in line for line in result.out))
        self.assertIn("**LOCK_DAILY_CAP**", result.summary[0])
        self.assertFalse(any(line.startswith("::error::") for line in result.out))     # 정상 건너뜀이다 — 빨강이 아니다
        self.assertEqual(result.remote_calls, [])                                        # 상한이 먼저 보고 원격은 읽지 않는다

    def test_a_scheduled_skip_has_no_annotation_a_manual_one_has_a_notice(self):
        history = [entry(slot=None)]
        scheduled = self.guard(lock_ready(), history=history, environ={"EVENT_NAME": "schedule"})
        manual = self.guard(lock_ready(), history=history, environ={"EVENT_NAME": "workflow_dispatch"})
        self.assertFalse(any(line.startswith("::") for line in scheduled.out))
        self.assertIn("::notice::제한 재개 잠금: 오늘 이미 하루 상한만큼 글이 만들어져 이번 수동 실행은 글을 만들지 않았습니다(정상 건너뜀).", manual.out)
        self.assertEqual((scheduled.code, manual.code), (0, 0))

    def test_closed_and_pending_drafts_count_like_published_ones(self):
        """승인 대기·닫힘·병합 모두 이력에 남으므로 같은 날 다시 만들지 않는다(닫은 뒤에도 하루 1편)."""
        for flow_entry in (entry(branch=BRANCH_C), entry(slot=None, branch=BRANCH_C), entry()):
            self.assertEqual(self.guard(lock_ready(), history=[flow_entry]).code, 0)

    def test_yesterdays_and_foreign_entries_do_not_count(self):
        """어제 항목과 사전이 아닌 항목(옛 형식 제목 문자열·null — 실제 이력 맨 앞에 있다)은 하루 상한에 세지 않는다. 날짜가 없는 사전 항목·오늘보다 뒤 날짜 항목은 이 시험에서 뺐다:
        주간 상한(L8)이 켜진 뒤로는 그런 항목이 '세지 않고 지나가는' 것이 아니라 일주일 안의 글 수를 셀 수 없게 만들어 가드가 멈춘다(WeeklyOddDateTest 가 그 멈춤을 확인한다)."""
        history = [entry(date="2026-11-08"), "문자열", None]
        result = self.guard(lock_ready(), history=history, remote=[])
        self.assertEqual((result.code, result.out), (None, []))

    def test_today_is_the_korean_date_even_right_after_midnight(self):
        late = datetime(2026, 11, 9, 23, 59, tzinfo=KST)
        early = datetime(2026, 11, 10, 0, 30, tzinfo=KST)               # UTC 로는 아직 11월 9일 15:30 이다
        self.assertEqual(self.guard(lock_ready(), history=[entry()], now=late).code, 0)
        self.assertEqual(self.guard(lock_ready(), history=[entry()], now=early, remote=[]).code, None)
        self.assertEqual(self.guard(lock_ready(), history=[entry(date="2026-11-10")], now=early).code, 0)

    def test_two_entries_report_the_real_count(self):
        result = self.guard(lock_ready(), history=[entry(slot=9), entry(slot=18)])
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_DAILY_CAP date=2026-11-09 today=2 cap=1")

    def test_the_cap_does_not_depend_on_the_registry_number_being_obeyed(self):
        """레지스트리의 하루 상한이 규칙을 어기면(2) 가드가 이미 멈춘다 — 상한은 코드 상수 1 이다."""
        reg = mutated(lambda r: set_limit(r, CHANCE, max_posts_per_day=2))
        self.assertEqual(self.guard(reg, history=[]).code, 1)

    def test_a_broken_history_stops_the_run_instead_of_counting_zero(self):
        for raw in ("{ 망가짐", "null", "{\"date\": \"2026-11-09\"}"):
            result = self.guard(lock_ready(), raw_history=raw, remote=[])
            self.assertEqual(result.code, 1, raw)
            self.assertEqual(result.out[0], "[SKIP] code=LOCK_BLOCKED reason=HISTORY_UNREADABLE", raw)
            self.assertIn("::error::이력 파일을 읽을 수 없어 상한을 셀 수 없습니다 — 글을 만들지 않고 멈춥니다.", result.out)

    def test_a_missing_history_file_means_no_post_yet(self):
        self.assertEqual(self.guard(lock_ready(), remote=[]).code, None)


class GuardOpenDraftsTest(GuardBase):
    def names(self, *branches):
        return list(branches)

    def test_three_unmerged_drafts_stop_a_new_one(self):
        result = self.guard(lock_ready(), history=[], remote=[BRANCH_A, BRANCH_B, "ai/draft/2026-11-06-s9"], exists=lambda path: False)
        self.assertEqual(result.code, 0)
        self.assertEqual(result.out[0], "[SKIP] code=OPEN_DRAFTS_CAP open=3 limit=3")
        self.assertIn("**OPEN_DRAFTS_CAP**", result.summary[0])
        self.assertEqual(result.remote_calls, [1])

    def test_two_leave_room_for_one_more(self):
        """열린 초안 상한(3)만 보는 시험이다 — 주간 상한(L8, 굴러가는 7일에 2편)이 따로 걸리지 않도록 지금(`later`)을 두 초안이 7일보다 오래된 날로 잡았다.
        같은 두 초안이 일주일 안에 있으면 주간 상한이 막는다(WeeklyOpenDraftsTest)."""
        result = self.guard(lock_ready(), history=[], remote=[BRANCH_A, BRANCH_B], exists=lambda path: False, now=NOW + timedelta(days=11))
        self.assertEqual((result.code, result.out), (None, []))

    def test_merged_branches_do_not_count_even_before_the_branch_is_cleaned_up(self):
        """병합된 초안은 열린 초안 수에 세지 않는다(주간 상한 이야기가 아니다 — 병합된 글도 일주일 안이면 주간 상한에는 센다: WeeklyOpenDraftsTest). 그래서 지금(`later`)을 일주일 뒤로 잡았다."""
        history = [entry(date="2026-11-07", branch=BRANCH_A), entry(date="2026-11-08", branch=BRANCH_B), entry(date="2026-11-06", branch="ai/draft/2026-11-06-s9")]
        result = self.guard(lock_ready(), history=history, remote=[BRANCH_A, BRANCH_B, "ai/draft/2026-11-06-s9", "ai/draft/odd"], exists=lambda path: True, now=NOW + timedelta(days=11))
        self.assertEqual((result.code, result.out), (None, []))

    def test_the_limit_is_the_registry_value(self):
        reg = lock_ready()
        set_limit(reg, CHANCE, max_open_drafts=1)
        self.assertEqual(self.guard(reg, history=[], remote=[BRANCH_A], exists=lambda path: False).out[0], "[SKIP] code=OPEN_DRAFTS_CAP open=1 limit=1")
        self.assertEqual(self.guard(reg, history=[], remote=[], exists=lambda path: False).code, None)

    def test_an_unreadable_remote_skips_the_run_with_the_fixed_warning(self):
        result = self.guard(lock_ready(), history=[], remote=None)
        self.assertEqual(result.code, 0)
        self.assertEqual(result.out[0], "[SKIP] code=OPEN_DRAFTS_UNKNOWN")
        self.assertIn("::warning::열린 초안 수를 확인하지 못해 이번 실행은 글을 만들지 않았습니다. 다음 실행에서 다시 시도합니다.", result.out)

    def test_with_the_lock_off_the_limit_applies_only_when_the_key_is_written_and_the_flow_is_pr(self):
        reg = with_lock_off(lock_ready())
        self.assertEqual(self.guard(reg, history=[], remote=[BRANCH_A, BRANCH_B, BRANCH_C], exists=lambda path: False).out[0], "[SKIP] code=OPEN_DRAFTS_CAP open=3 limit=3")
        no_key = with_lock_off(lock_ready())
        drop_limit(no_key, CHANCE, "max_open_drafts")
        self.assertEqual(self.guard(no_key, history=[], remote="unused").code, None)                  # 키가 없으면 이전과 같다
        direct = with_lock_off(lock_ready())
        set_in(direct, CHANCE, publish_flow="direct")
        self.assertEqual(self.guard(direct, history=[], remote="unused").code, None)

    def test_with_the_lock_off_the_daily_cap_is_not_counted_at_all(self):
        reg = with_lock_off(lock_ready())
        result = self.guard(reg, history=[entry(slot=9), entry(slot=18)], remote=[], exists=lambda path: False)
        self.assertEqual((result.code, result.out), (None, []))           # 수동·정기 실행의 하루 상한은 잠금이 켜질 때만 코드로 강제된다(지금 동작 그대로)

    def test_a_broken_history_stops_an_open_drafts_check_even_with_the_lock_off(self):
        reg = with_lock_off(lock_ready())
        self.assertEqual(self.guard(reg, raw_history="[", remote=[]).code, 1)


class GeneratorMainTest(PlainDirBase):
    """generator.main 이 정지 검사 바로 뒤에 가드를 부른다: 정기·수동·연습·이미지 교체·정지."""

    def setUp(self):
        super().setUp()
        self.reg_path = write_registry(self.root, lock_ready())

    def tick(self, now, event="schedule", reg=None, dry=False, remote=None, flow="pr", **extra):
        path = write_registry(self.root, reg, "tick-blogs.json") if reg is not None else self.reg_path
        with mock.patch.object(registry, "REGISTRY_PATH", path), mock.patch.object(draft_flow, "ls_remote_drafts", return_value=remote or {}):
            return run_tick(self.clone, now, flow=flow, event=event, dry=dry, git_env={"EVENT_NAME": event}, guarded=True, **extra)

    def test_the_first_scheduled_run_of_the_day_makes_a_draft(self):
        result = self.tick(at(9, 20, day=28))
        self.assertIsNone(result.value)
        self.assertEqual([item["branch"] for item in result.history], ["ai/draft/2026-10-28-s9"])
        self.assertEqual(len(result.prompts), 1)

    def test_a_second_slot_the_same_day_is_skipped_with_the_lock_but_made_without_it(self):
        self.tick(at(9, 20, day=28))
        for rel in self.posts():                                            # deliver 가 글을 초안 브랜치로 옮긴 뒤의 main 작업 트리
            (self.clone / rel).unlink()
        locked = self.tick(at(18, 20, day=28), feed=[candidate("해양 관측 위성 자료 공개", "https://www.reuters.com/b")])
        self.assertIsInstance(locked.value, SystemExit)
        self.assertEqual(locked.value.code, 0)
        self.assertIn("[SKIP] code=LOCK_DAILY_CAP date=2026-10-28 today=1 cap=1", locked.out)
        self.assertEqual((locked.prompts, len(locked.history), self.posts()), ([], 1, []))      # 모델을 부르지 않았고 새 글·이력이 없다
        self.assertIn("**LOCK_DAILY_CAP**", locked.summary)
        unlocked = self.tick(at(18, 20, day=28), reg=with_lock_off(lock_ready()), feed=[candidate("해양 관측 위성 자료 공개", "https://www.reuters.com/b")])
        self.assertIsNone(unlocked.value)                                   # 잠금이 꺼져 있으면 이전과 같다: 18시 슬롯 글이 하나 더 만들어진다
        self.assertEqual([item["slot"] for item in unlocked.history], [9, 18])

    def test_the_next_day_starts_again(self):
        self.tick(at(9, 20, day=28))
        for rel in self.posts():
            (self.clone / rel).unlink()
        result = self.tick(at(9, 20, day=29), feed=[candidate("캐나다 소비자물가지수 발표", "https://www.reuters.com/c")])
        self.assertIsNone(result.value)
        self.assertEqual(result.history[-1]["branch"], "ai/draft/2026-10-29-s9")

    def test_a_manual_real_run_obeys_the_cap_too_without_it_the_cap_is_only_a_warning(self):
        made = self.tick(at(11, 5, day=28), event="workflow_dispatch")
        self.assertIsNone(made.value)
        self.assertEqual(made.history[0]["branch"], "ai/draft/2026-10-28-m110500")
        for rel in self.posts():
            (self.clone / rel).unlink()
        blocked = self.tick(at(15, 0, day=28), event="workflow_dispatch", feed=[candidate("다른 기사 제목입니다", "https://www.reuters.com/d")])
        self.assertIsInstance(blocked.value, SystemExit)
        self.assertEqual(blocked.value.code, 0)
        self.assertIn("::notice::제한 재개 잠금: 오늘 이미 하루 상한만큼 글이 만들어져 이번 수동 실행은 글을 만들지 않았습니다(정상 건너뜀).", blocked.out)
        self.assertEqual((blocked.prompts, len(blocked.history)), ([], 1))
        free = self.tick(at(15, 0, day=28), event="workflow_dispatch", reg=with_lock_off(lock_ready()), feed=[candidate("다른 기사 제목입니다", "https://www.reuters.com/d")])
        self.assertIsNone(free.value)                                       # 잠금이 꺼져 있으면 수동 실행은 상한을 따지지 않는다(지금 동작)
        self.assertEqual(len(free.history), 2)

    def test_a_practice_run_is_not_counted_and_not_blocked(self):
        self.tick(at(9, 20, day=28))
        result = self.tick(at(15, 0, day=28), event="workflow_dispatch", dry=True, feed=[candidate("연습 기사 제목입니다", "https://www.reuters.com/e")])
        self.assertIsNone(result.value)
        self.assertEqual(len(result.history), 1)                            # 연습은 저장하지 않는다(이력 그대로)

    def test_with_the_lock_off_the_guard_changes_nothing_the_run_prints_makes_or_asks_for(self):
        """꺼짐 = 이전과 같다(main 수준): 같은 하루를 '가드를 거쳐서'(잠금 꺼짐 레지스트리) 돌린 결과가 가드를 건너뛴 결과와 같다 — 반환값·출력·요약·모델에 보낸 글·이력.
        기존 시험(test_generator_drafts·test_generator_slots 등)은 가드를 건너뛰고 흐름만 보므로, 가드를 거친 채의 같음은 이 시험이 지킨다."""
        fixed = candidate("후보 기사", "https://www.reuters.com/a")
        fixed["published"] = datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc)      # candidate() 는 지금 시각을 넣는다 — 두 번의 실행이 같은 입력을 받게 고정한다
        off = write_registry(self.root, today_registry(), "off-blogs.json")
        scenarios = (dict(now=at(9, 20, day=28)), dict(now=at(8, 40, day=28)), dict(now=at(11, 5, day=28), event="workflow_dispatch"),
                     dict(now=at(9, 20, day=28), dry=True), dict(now=at(9, 20, day=28), flow="direct"),
                     dict(now=at(11, 5, day=28), event="workflow_dispatch", flow="direct"))
        for index, scenario in enumerate(scenarios):
            seen = []
            for guarded in (False, True):
                clone = self.root / f"eq-{index}-{int(guarded)}" / "repo"
                (clone / "_posts").mkdir(parents=True)
                (clone / "history.json").write_bytes(b"[]\n")
                event = scenario.get("event", "schedule")
                with mock.patch.object(registry, "REGISTRY_PATH", off), \
                        mock.patch.object(draft_flow, "ls_remote_drafts", side_effect=AssertionError("꺼짐이면 원격 초안 브랜치를 읽지 않는다")):
                    tick = run_tick(clone, scenario["now"], flow=scenario.get("flow", "pr"), event=event, dry=scenario.get("dry", False),
                                    feed=[dict(fixed)], git_env={"EVENT_NAME": event}, guarded=guarded)
                seen.append((repr(tick.value), tick.out, tick.summary, tick.prompts, tick.history))
            self.assertEqual(seen[0], seen[1], scenario)
            self.assertTrue(seen[0][2], scenario)                                      # 비교한 것이 비어 있지 않다(요약이 있다)

    def test_a_rule_violation_makes_nothing_and_ends_red(self):
        reg = lock_ready()
        set_in(reg, CHANCE, publish_flow="direct")
        result = self.tick(at(9, 20, day=28), reg=reg, flow="direct")
        self.assertIsInstance(result.value, SystemExit)
        self.assertEqual(result.value.code, 1)
        self.assertIn("[SKIP] code=LOCK_BLOCKED rules=L1,L3", result.out)
        self.assertTrue(any(line.startswith("::error::제한 재개 잠금(resume_lock)이 켜져 있는데") for line in result.out.splitlines()))
        self.assertEqual((result.prompts, result.history, self.posts()), ([], [], []))

    def test_an_invalid_lock_value_is_read_as_locked(self):
        reg = lock_ready()
        reg["resume_lock"] = "true"
        result = self.tick(at(9, 20, day=28), reg=reg)
        self.assertEqual(result.value.code, 1)
        self.assertIn("rules=L0", result.out)

    def test_the_pause_switch_wins_the_guard_does_not_even_read_the_registry(self):
        with chdir(self.clone), mock.patch.dict(os.environ, {"PIPELINE_PAUSE": "true"}), \
                mock.patch.object(registry, "load_registry", side_effect=AssertionError("정지 중에는 읽으면 안 된다")):
            value, out = run_captured(g.main)
        self.assertIsNone(value)
        self.assertIn("[SKIP] code=PAUSED", out)

    def test_the_image_fix_is_refused_with_the_lock_and_unchanged_without_it(self):
        called = []

        def fake_fix(*args, **kwargs):
            called.append(1)
            return "교체 0건"

        def run_main(path):
            env = {k: v for k, v in os.environ.items() if k != "PIPELINE_PAUSE"}
            with chdir(self.clone), mock.patch.dict(os.environ, env, clear=True), mock.patch.object(registry, "REGISTRY_PATH", path), \
                    mock.patch.object(g, "FIX_IMAGES", True), mock.patch.object(g, "DRY_RUN", False), mock.patch.object(g, "STUB_GEMINI", False), \
                    mock.patch.object(g, "fix_images", fake_fix):
                return run_captured(g.main)
        value, out = run_main(self.reg_path)
        self.assertIsInstance(value, SystemExit)
        self.assertEqual(value.code, 1)
        self.assertEqual(called, [])
        self.assertIn("[SKIP] code=LOCK_BLOCKED reason=FIX_IMAGES", out)
        value, out = run_main(write_registry(self.root, today_registry(), "off.json"))
        self.assertIsNone(value)
        self.assertEqual(called, [1])

    def test_open_drafts_at_the_limit_stop_a_scheduled_run(self):
        remote = {BRANCH_A: "a" * 40, BRANCH_B: "b" * 40, "ai/draft/2026-10-27-s9": "c" * 40}
        result = self.tick(at(9, 20, day=28), remote=remote)
        self.assertEqual(result.value.code, 0)
        self.assertIn("[SKIP] code=OPEN_DRAFTS_CAP open=3 limit=3", result.out)
        self.assertEqual((result.prompts, result.history), ([], []))


class ChanceFlowLockTest(unittest.TestCase):
    """drafts.chance_flow 는 워크플로의 '발행 흐름 확인' 단계·draft_flow deliver·생성기가 모두 쓰는 한 곳 — 잠금이 켜져 있는데 규칙을 어기면 direct 로도 pr 로도 답하지 않고 멈춘다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def flow(self, reg):
        return drafts.chance_flow(write_registry(self.folder, reg))

    def test_the_registry_as_it_is_today_answers_direct_and_the_real_file_answers_what_it_says(self):
        self.assertEqual(self.flow(today_registry()), "direct")
        self.assertEqual(drafts.chance_flow(), publish_lock.flow_of(real_registry()))        # 진짜 파일을 읽는 길도 같은 한 곳(켜는 값은 LockStateTest 의 한 시험이 못박는다)

    def test_a_lock_on_registry_that_obeys_the_rules_answers_pr(self):
        self.assertEqual(self.flow(lock_ready()), "pr")

    def test_a_lock_on_registry_that_breaks_a_rule_stops(self):
        for rule, cases in VIOLATIONS.items():
            for label, mutate in cases:
                with self.subTest(rule=rule, case=label), self.assertRaises(drafts.DraftFlowError) as caught:
                    self.flow(mutated(mutate))
                self.assertTrue("제한 재개 잠금이 켜져 있는데 레지스트리가 규칙을 어깁니다" in str(caught.exception)
                                or "publish_flow 값이 올바르지 않습니다" in str(caught.exception), str(caught.exception))   # 모르는 값은 기존 검사가 먼저 멈춘다

    def test_pr_without_the_lock_is_unchanged_whatever_else_is_set(self):
        reg = with_lock_off(lock_ready())
        set_limit(reg, CHANCE, max_posts_per_day=2)
        self.assertEqual(self.flow(reg), "pr")
        direct = with_lock_off(lock_ready())
        set_in(direct, CHANCE, publish_flow="direct")
        self.assertEqual(self.flow(direct), "direct")

    def test_the_existing_stops_are_unchanged(self):
        with self.assertRaises(drafts.DraftFlowError):
            drafts.chance_flow(self.folder / "없는-파일.json")
        reg = real_registry()
        set_in(reg, CHANCE, publish_flow="maybe")
        with self.assertRaises(drafts.DraftFlowError):
            self.flow(reg)

    def test_the_flow_command_fails_and_prints_nothing_on_stdout_when_the_lock_is_violated(self):
        bad = write_registry(self.folder, mutated(lambda r: set_in(r, CHANCE, publish_flow="direct")), "bad.json")
        good = write_registry(self.folder, lock_ready(), "good.json")
        for path, code, shown in ((bad, 1, ""), (good, 0, "pr\n")):
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch.object(registry, "REGISTRY_PATH", path), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(draft_flow.main(["flow"]), code)
            self.assertEqual(stdout.getvalue(), shown)
            self.assertEqual("제한 재개 잠금" in stderr.getvalue(), code == 1)

    def test_deliver_stops_with_a_clear_error_under_a_violation(self):
        bad = write_registry(self.folder, mutated(lambda r: set_limit(r, CHANCE, max_posts_per_day=2)))
        stdout = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != "PIPELINE_PAUSE"}
        with mock.patch.object(registry, "REGISTRY_PATH", bad), mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(stdout):
            self.assertEqual(draft_flow.main(["deliver"]), 1)
        self.assertIn("제한 재개 잠금이 켜져 있는데 레지스트리가 규칙을 어깁니다", stdout.getvalue())


class BloggerLockTest(RunBase):
    """잠금이 켜져 있으면 Blogger 러너는 규칙 위반이면 아무것도 하지 않고, 즉시 게시는 어떤 길로도 하지 않는다(감시자: 가짜 게시자의 publish·인증 점검 호출 수)."""

    def lock(self, mode="draft", mutate=None, lock_on=True):
        path = self.root / "pipeline" / "blogs.json"
        reg = json.loads(path.read_text(encoding="utf-8"))
        reg = lock_ready(reg) if lock_on else reg
        blog_of(reg, MACAT)["mode"] = mode
        if mutate:
            mutate(reg)
        path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")

    def assertNothingHappened(self, publisher):
        self.assertEqual((publisher.published, publisher.health_calls), ([], 0))
        self.assertEqual((self.history(), self.drafts()), ([], []))

    def test_a_blogger_blog_in_auto_mode_is_refused_before_any_blogger_call(self):
        self.lock(mode="auto")
        pub = FakePublisher()
        code, text = self.go(env=FULL_ENV, publisher=pub)
        self.assertEqual(code, 2)
        self.assertNothingHappened(pub)
        self.assertIn("[SKIP] code=LOCK_BLOCKED", text)
        self.assertIn("제한 재개 잠금 L2", text)
        self.assertIn("::error::제한 재개 잠금(resume_lock)이 켜져 있는데 설정이 규칙을 어깁니다", text)

    def test_the_manual_immediate_publish_is_refused_in_every_spelling(self):
        for value in ("publish", "on", "1", "true", "yes", "PUBLISH", " Publish "):
            self.lock(mode="draft")
            pub = FakePublisher()
            code, text = self.go(env={**FULL_ENV, "BLOGGER_PUBLISH": value}, publisher=pub)
            with self.subTest(value=value):
                self.assertEqual(code, 2)
                self.assertNothingHappened(pub)
                self.assertIn("::error::[blogger_macat] 제한 재개 잠금이 켜져 있어 즉시 게시는 하지 않습니다", text)
                self.assertIn("[SKIP] code=LOCK_BLOCKED blog=blogger_macat", text)

    def test_the_command_line_publish_option_is_refused_too(self):
        self.lock(mode="draft")
        pub = FakePublisher()
        code, text = self.go(env=FULL_ENV, publisher=pub, extra=("--publish", "on"))
        self.assertEqual(code, 2)
        self.assertNothingHappened(pub)

    def test_a_practice_run_with_the_publish_choice_is_refused_as_well(self):
        self.lock(mode="draft")
        pub = FakePublisher()
        code, text = self.go(env={**FULL_ENV, "BLOGGER_PUBLISH": "publish", "DRY_RUN": "1"}, publisher=pub)
        self.assertEqual(code, 2)
        self.assertNothingHappened(pub)

    def test_draft_upload_still_works_and_nothing_is_made_public(self):
        self.lock(mode="draft")
        pub = FakePublisher()
        code, text = self.go(env=FULL_ENV, publisher=pub)
        self.assertEqual(code, 0, text)
        self.assertEqual([item["draft"] for item in pub.published], [True])          # 초안함 업로드만 — 공개 게시(draft=False)는 한 번도 없다
        self.assertEqual(self.history()[-1]["status"], "draft_uploaded")

    def test_the_manual_choices_off_and_draft_and_the_registry_mode_keep_working(self):
        for value, expect_published in (("draft", [True]), ("off", []), ("auto", [True]), ("", [True])):
            self.lock(mode="draft")
            (self.root / "blogger_history.json").unlink(missing_ok=True)
            pub = FakePublisher()
            code, text = self.go(env={**FULL_ENV, "BLOGGER_PUBLISH": value}, publisher=pub)
            with self.subTest(value=value):
                self.assertEqual(code, 0, text)
                self.assertEqual([item["draft"] for item in pub.published], expect_published)

    def test_mode_off_is_still_a_quiet_skip(self):
        self.lock(mode="off")
        pub = FakePublisher()
        code, text = self.go(env=FULL_ENV, publisher=pub)
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=MODE_OFF", text)
        self.assertNothingHappened(pub)

    def test_a_violation_anywhere_in_the_registry_stops_this_blog_too(self):
        self.lock(mode="draft", mutate=lambda r: set_in(r, CHANCE, publish_flow="direct"))
        pub = FakePublisher()
        code, text = self.go(env=FULL_ENV, publisher=pub)
        self.assertEqual(code, 2)
        self.assertNothingHappened(pub)
        self.assertIn("제한 재개 잠금 L1", text)

    def test_without_the_lock_auto_mode_and_the_manual_publish_work_as_before(self):
        self.lock(mode="auto", lock_on=False)
        pub = FakePublisher()
        code, text = self.go(env=FULL_ENV, publisher=pub)
        self.assertEqual(code, 0, text)
        self.assertEqual([item["draft"] for item in pub.published], [False])        # 이전과 같다: mode auto 는 즉시 게시
        self.assertNotIn("LOCK", text)
        self.lock(mode="draft", lock_on=False)
        (self.root / "blogger_history.json").unlink(missing_ok=True)
        pub = FakePublisher()
        code, text = self.go(env={**FULL_ENV, "BLOGGER_PUBLISH": "publish"}, publisher=pub)
        self.assertEqual(code, 0, text)
        self.assertEqual([item["draft"] for item in pub.published], [False])

    def test_a_mistyped_lock_key_stops_the_runner_instead_of_letting_everything_through(self):
        """검증 지적 1: 켠 뒤 키 이름이 오타면 예전에는 잠금이 꺼진 채로 수동 publish 가 그대로 게시됐다(검증자 시나리오 LB208). 지금은 어떤 글도 만들지 않는다."""
        for label, mutate in KEY_TYPOS:
            for extra in ({}, {"BLOGGER_PUBLISH": "publish"}):
                self.lock(mode="draft", mutate=mutate)
                (self.root / "blogger_history.json").unlink(missing_ok=True)
                pub = FakePublisher()
                code, text = self.go(env={**FULL_ENV, **extra}, publisher=pub)
                with self.subTest(label=label, extra=extra):
                    self.assertEqual(code, 2)
                    self.assertNothingHappened(pub)
                    self.assertIn("[SKIP] code=LOCK_BLOCKED", text)
                    self.assertIn("레지스트리 키 K", text)
                    self.assertIn("::error::" + publish_lock.KEY_ERROR, text)

    def test_the_summary_says_why(self):
        self.lock(mode="auto")
        summary = self.root / "summary.md"
        self.go(env={**FULL_ENV, "GITHUB_STEP_SUMMARY": str(summary)}, publisher=FakePublisher())
        text = summary.read_text(encoding="utf-8")
        self.assertIn("**LOCK_BLOCKED**", text)
        self.assertNotIn("::", text.replace("**LOCK_BLOCKED**", ""))
        self.lock(mode="draft")
        summary.unlink()
        self.go(env={**FULL_ENV, "BLOGGER_PUBLISH": "publish", "GITHUB_STEP_SUMMARY": str(summary)}, publisher=FakePublisher())
        self.assertIn("**LOCK_BLOCKED**", summary.read_text(encoding="utf-8"))


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def run_cli(self, module_main, argv, reg=None, path=None):
        target = path or (write_registry(self.folder, reg) if reg is not None else registry.REGISTRY_PATH)
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(registry, "REGISTRY_PATH", target), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = module_main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_check_reports_off_on_and_violations(self):
        code, out, _ = self.run_cli(publish_lock.main, ["check"], today_registry())
        self.assertEqual((code, out.strip()), (0, "제한 재개 잠금: 꺼짐(규칙을 적용하지 않습니다)"))
        code, out, _ = self.run_cli(publish_lock.main, ["check"], lock_ready())
        self.assertEqual((code, out.strip()), (0, "제한 재개 잠금: 켜짐"))
        code, out, _ = self.run_cli(publish_lock.main, ["check"], mutated(lambda r: set_in(r, MACAT, mode="auto")))
        self.assertEqual(code, 1)
        self.assertIn("[잠금 오류] 제한 재개 잠금 L2", out)
        code, out, _ = self.run_cli(publish_lock.main, ["check"], path=self.folder / "없음.json")
        self.assertEqual(code, 1)
        self.assertIn("레지스트리를 읽을 수 없습니다", out)

    def test_check_direct_lets_a_workflow_that_commits_to_main_run_only_with_the_lock_off(self):
        code, out, _ = self.run_cli(publish_lock.main, ["check-direct"], today_registry())
        self.assertEqual((code, out.strip()), (0, "[잠금] 제한 재개 잠금이 꺼져 있어 이 워크플로를 그대로 실행합니다."))
        for reg in (lock_ready(), mutated(lambda r: r.update(resume_lock="yes")), mutated(lambda r: set_in(r, CHANCE, publish_flow="direct"))):
            code, out, _ = self.run_cli(publish_lock.main, ["check-direct"], reg)
            self.assertEqual(code, 1)
            self.assertEqual(out.strip(), "::error::제한 재개 잠금이 켜져 있어 main 에 직접 커밋하는 이 워크플로는 실행하지 않습니다 — 이미지 변경은 이슈 수정 요청(수정안 PR)으로 하세요.")

    def test_check_direct_fails_closed_when_the_registry_cannot_be_read(self):
        code, out, _ = self.run_cli(publish_lock.main, ["check-direct"], path=self.folder / "없음.json")
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), "::error::레지스트리를 읽을 수 없어 제한 재개 잠금 상태를 알 수 없습니다 — main 에 직접 커밋하는 이 워크플로는 멈춥니다.")
        broken = self.folder / "broken.json"
        broken.write_text("{ 망가짐", encoding="utf-8")
        self.assertEqual(self.run_cli(publish_lock.main, ["check-direct"], path=broken)[0], 1)

    def test_check_and_check_direct_fail_closed_on_a_mistyped_lock_key(self):
        """검증자 시나리오 LC07·LC08: 켠 뒤 키 오타여도 check 가 '꺼짐'으로 통과하고 check-direct 가 이미지 교체 길을 열던 구멍."""
        for label, mutate in KEY_TYPOS:
            reg = lock_ready()
            mutate(reg)
            with self.subTest(label):
                code, out, _ = self.run_cli(publish_lock.main, ["check"], reg)
                self.assertEqual(code, 1)
                self.assertIn("[잠금 오류] 레지스트리 키 K", out)
                self.assertIn("제한 재개 잠금: 알 수 없음(키가 잘못 적혀 있습니다", out)
                code, out, _ = self.run_cli(publish_lock.main, ["check-direct"], reg)
                self.assertEqual(code, 1)
                self.assertIn("[잠금 오류] 레지스트리 키 K", out)
                self.assertIn("::error::" + publish_lock.KEY_ERROR_DIRECT, out)

    def test_the_registry_and_plan_commands_reject_a_mistyped_lock_key(self):
        def run_plan(reg):
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch.object(plan, "load_registry", return_value=reg), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                return plan.main(["--platform", "blogger"]), stdout.getvalue(), stderr.getvalue()
        for label, mutate in KEY_TYPOS:
            reg = lock_ready()
            mutate(reg)
            with self.subTest(label):
                code, out, _ = self.run_cli(registry.main, [], reg)
                self.assertEqual(code, 1)
                self.assertIn("레지스트리 키 K", out)
                code, out, err = run_plan(reg)
                self.assertEqual((code, out), (1, ""))
                self.assertIn("레지스트리 키 K", err)

    def test_the_commands_leave_the_lock_state_in_the_run_summary(self):
        cases = ((["check"], today_registry(), "- 제한 재개 잠금: 꺼짐(규칙을 적용하지 않습니다)"), (["check"], lock_ready(), "- 제한 재개 잠금: 켜짐"),
                 (["check-direct"], today_registry(), "- 제한 재개 잠금: 꺼짐 — 직접 커밋 워크플로를 그대로 실행합니다"),
                 (["check-direct"], lock_ready(), "- 제한 재개 잠금: 켜짐 — 직접 커밋 워크플로를 멈췄습니다"))
        for argv, reg, line in cases:
            summary = self.folder / "summary.md"
            summary.unlink(missing_ok=True)
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}):
                self.run_cli(publish_lock.main, argv, reg)
            with self.subTest(argv=argv, lock=reg.get("resume_lock")):
                self.assertEqual(summary.read_text(encoding="utf-8").strip(), line)
        typo = lock_ready()
        typo["resume_lok"] = typo.pop("resume_lock")
        summary = self.folder / "typo.md"
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}):
            self.run_cli(publish_lock.main, ["check-direct"], typo)
        self.assertIn("- 제한 재개 잠금: 알 수 없음(키가 잘못 적혀 있어 직접 커밋 워크플로를 멈췄습니다)", summary.read_text(encoding="utf-8"))
        unreadable = self.folder / "unreadable.md"
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(unreadable)}):
            self.run_cli(publish_lock.main, ["check-direct"], path=self.folder / "없음.json")
        self.assertIn("- 제한 재개 잠금: 알 수 없음(레지스트리를 읽을 수 없어 직접 커밋 워크플로를 멈췄습니다)", unreadable.read_text(encoding="utf-8"))

    def test_without_a_summary_variable_the_commands_write_nothing_but_their_log_lines(self):
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
        with mock.patch.dict(os.environ, env, clear=True):
            code, out, _ = self.run_cli(publish_lock.main, ["check"], today_registry())
        self.assertEqual((code, out.strip()), (0, "제한 재개 잠금: 꺼짐(규칙을 적용하지 않습니다)"))

    def test_unknown_commands_are_a_usage_error(self):
        for argv in ([], ["nope"], ["CHECK"]):
            code, out, err = self.run_cli(publish_lock.main, argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("사용법", err)
            self.assertEqual(out, "")

    def test_the_registry_command_rejects_a_violation_and_accepts_the_ready_registry(self):
        code, out, _ = self.run_cli(registry.main, [], mutated(lambda r: set_limit(r, CHANCE, max_posts_per_day=2)))
        self.assertEqual(code, 1)
        self.assertIn("제한 재개 잠금 L4", out)
        code, out, _ = self.run_cli(registry.main, [], lock_ready())
        self.assertEqual(code, 0)
        self.assertIn("레지스트리 검증 통과", out)
        code, out, _ = self.run_cli(registry.main, [])
        self.assertEqual(code, 0)

    def test_the_plan_command_used_by_the_blogger_workflows_fails_under_a_violation(self):
        """Blogger 워크플로의 대상 계산(plan 잡)이 레지스트리 검증을 먼저 하므로 규칙 위반이면 글 생성 잡이 시작되지 않는다."""
        def run_plan(reg):
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch.object(plan, "load_registry", return_value=reg), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                return plan.main(["--platform", "blogger"]), stdout.getvalue(), stderr.getvalue()
        code, out, err = run_plan(mutated(lambda r: set_in(r, MACAT, mode="auto")))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("제한 재개 잠금 L2", err)
        code, out, _ = run_plan(lock_ready())
        self.assertEqual(code, 0)
        self.assertEqual([item["key"] for item in json.loads(out)["include"]], [MACAT, KCYOON])


class WorkflowSimulation:
    """워크플로 한 job 의 단계들이 GitHub 규칙대로 도는지 계산한다(시험 전용): 앞 단계가 실패하면 뒤 단계는 건너뛴다(조건에 상태 함수가 없는 한 — 그것은 따로 확인한다).
    명령 단계의 결과는 진짜 코드를 불러 정한다: 발행 흐름 확인 = drafts.chance_flow, 생성기 = publish_lock.guard_start(가드 통과 여부), 잠금 확인 = publish_lock.main."""

    def __init__(self, name, reg, folder, event, inputs):
        self.name, self.reg, self.event, self.inputs = name, reg, event, inputs
        self.path = write_registry(folder, reg, "sim-blogs.json")
        self.folder = Path(folder)
        self.ctx = context(event, inputs)
        self.ctx["steps"] = {}
        self.ran, self.failed_at = [], None
        self.run()

    @staticmethod
    def label(step):
        return step.get("id") or step.get("name") or step.get("uses")

    def condition_holds(self, step):
        condition = step.get("if")
        if condition is None:
            return True
        text = condition if "${{" in condition else "${{ " + condition + " }}"
        return render(text, self.ctx) == "true"

    def outcome(self, step):
        """(성공 여부, 단계 출력)."""
        script = str(step.get("run", ""))
        env = step.get("env", {})
        if "pipeline.draft_flow flow" in script:
            try:
                with mock.patch.object(registry, "REGISTRY_PATH", self.path):
                    return True, {"flow": drafts.chance_flow()}
            except drafts.DraftFlowError:
                return False, {}
        if "pipeline.publish_lock check-direct" in script:
            with mock.patch.object(registry, "REGISTRY_PATH", self.path), contextlib.redirect_stdout(io.StringIO()):
                return publish_lock.main(["check-direct"]) == 0, {}
        if script == "python generator.py":
            dry = render(env.get("DRY_RUN", "0"), self.ctx) in ("1", "true")
            fix = env.get("FIX_IMAGES") in ("1", 1, True)
            history = self.folder / "sim-history.json"
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    publish_lock.guard_start({"EVENT_NAME": self.event}, history, lambda: NOW, fix, dry, lambda text: None, load=lambda: self.reg, remote_drafts=lambda: [])
            except SystemExit as exc:
                return exc.code == 0, {}
            return True, {}
        if step.get("id") == "commit":
            return True, {"pushed": "true"}
        return True, {}

    def run(self):
        for step in load(self.name)["jobs"]["build"]["steps"]:
            if self.failed_at is not None or not self.condition_holds(step):
                continue
            ok, outputs = self.outcome(step)
            self.ran.append(self.label(step))
            if step.get("id"):
                self.ctx["steps"][step["id"]] = {"outputs": outputs}
            if not ok:
                self.failed_at = self.label(step)


EVENTS = (("schedule", {}), ("workflow_dispatch", {"dry_run": False, "real_ai": False}), ("workflow_dispatch", {"dry_run": True, "real_ai": False}))


def real_run(event, inputs):
    return not (event == "workflow_dispatch" and inputs.get("dry_run"))


class DirectPushNeverRunsUnderTheLockTest(unittest.TestCase):
    """'chanceblog.yml 의 main 직접 푸시 단계가 잠금 아래에서는 절대 돌지 않는다'를 단계 조건과 진짜 코드의 결과로 보인다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def sim(self, name, reg, event, inputs):
        return WorkflowSimulation(name, reg, self.folder, event, inputs)

    def test_no_step_of_the_two_committing_workflows_can_run_after_a_failure(self):
        """앞 단계가 실패하면 뒤 단계가 돌지 않는다는 전제: 두 워크플로의 어떤 단계도 상태 함수(always·failure·cancelled)를 조건에 쓰지 않는다."""
        for name in ("chanceblog.yml", "chance-fix-images.yml"):
            for step in load(name)["jobs"]["build"]["steps"]:
                condition = str(step.get("if", ""))
                for status in ("always()", "failure()", "cancelled()"):
                    self.assertNotIn(status, condition, (name, step.get("name")))

    def test_without_the_lock_a_real_run_commits_to_main_exactly_like_before(self):
        for event, inputs in EVENTS:
            result = self.sim("chanceblog.yml", today_registry(), event, inputs)
            self.assertEqual("commit" in result.ran, real_run(event, inputs), (event, inputs, result.ran))
            self.assertNotIn("초안 올리기와 승인 PR 열기 (승인 흐름일 때만)", result.ran)
            self.assertIsNone(result.failed_at)

    def test_with_a_compliant_lock_the_commit_step_never_runs_and_the_draft_step_does(self):
        for event, inputs in EVENTS:
            result = self.sim("chanceblog.yml", lock_ready(), event, inputs)
            self.assertNotIn("commit", result.ran, (event, inputs))
            self.assertEqual("초안 올리기와 승인 PR 열기 (승인 흐름일 때만)" in result.ran, real_run(event, inputs), (event, inputs, result.ran))
            self.assertEqual("flow", result.ran[2])

    def test_with_the_lock_on_and_any_violation_the_flow_step_fails_and_nothing_after_it_runs(self):
        for rule, cases in VIOLATIONS.items():
            for label, mutate in cases:
                for event, inputs in EVENTS:
                    result = self.sim("chanceblog.yml", mutated(mutate), event, inputs)
                    with self.subTest(rule=rule, case=label, event=event, inputs=inputs):
                        self.assertEqual(result.failed_at, "flow")
                        self.assertEqual(result.ran[-1], "flow")
                        self.assertNotIn("commit", result.ran)
                        self.assertEqual([item for item in result.ran if item not in ("actions/checkout@v6", "actions/setup-python@v6", "flow")], [])

    def test_the_commit_step_needs_the_flow_output_to_be_something_other_than_pr_and_the_flow_step_cannot_be_skipped(self):
        steps = steps_of()
        flow = next(step for step in steps if step.get("id") == "flow")
        commit = next(step for step in steps if step.get("id") == "commit")
        self.assertNotIn("if", flow)
        self.assertIn("steps.flow.outputs.flow != 'pr'", commit["if"])
        self.assertLess(steps.index(flow), steps.index(commit))

    LOCK_STEP = "제한 재개 잠금 확인 (켜져 있으면 직접 커밋 금지)"

    def test_the_image_fix_workflow_stops_at_its_first_step_under_the_lock_whatever_else_is_set(self):
        regs = [lock_ready(), mutated(lambda r: set_in(r, CHANCE, publish_flow="direct")), mutated(lambda r: r.update(resume_lock="yes"))]
        for reg in regs:
            for event, inputs in [case for case in EVENTS[1:] if real_run(*case)]:
                result = self.sim("chance-fix-images.yml", reg, event, inputs)
                with self.subTest(event=event, inputs=inputs, lock=reg["resume_lock"]):
                    self.assertEqual(result.failed_at, self.LOCK_STEP)
                    self.assertNotIn("commit", result.ran)
                    self.assertEqual(result.ran[-1], self.LOCK_STEP)

    def test_a_practice_image_fix_is_not_stopped_by_the_lock_step_and_still_writes_nothing(self):
        """검증 지적 6: 연습 실행(저장 안 함)은 쓰는 길이 없고(커밋 단계는 연습이면 건너뜀) 생성기 가드도 통과시키므로 첫 단계가 막지 않는다. 규칙 위반이면 생성기 가드가 연습도 멈춘다."""
        inputs = {"dry_run": True, "real_ai": False}
        result = self.sim("chance-fix-images.yml", lock_ready(), "workflow_dispatch", inputs)
        self.assertNotIn(self.LOCK_STEP, result.ran)
        self.assertIsNone(result.failed_at)
        self.assertNotIn("commit", result.ran)
        self.assertNotIn("Pages 배포 실행 (새 커밋이 있을 때만)", result.ran)
        for reg in (mutated(lambda r: set_in(r, CHANCE, publish_flow="direct")), mutated(lambda r: r.update(resume_lock="yes"))):
            result = self.sim("chance-fix-images.yml", reg, "workflow_dispatch", inputs)
            self.assertEqual(result.failed_at, "기존 글 이미지 교체 실행")                       # 규칙 위반은 연습도 생성기 가드가 멈춘다
            self.assertNotIn("commit", result.ran)

    def test_a_mistyped_lock_key_cannot_open_the_direct_commit_paths(self):
        """검증자 시나리오(wf_sim): 켠 뒤 키 이름이 오타여도 예전에는 flow 단계가 통과하고 이미지 교체 단계가 직접 커밋했다. 지금은 flow 단계가 실패하고 두 워크플로 어디서도 커밋이 돌지 않는다."""
        for label, mutate in KEY_TYPOS:
            reg = lock_ready()
            mutate(reg)
            for event, inputs in EVENTS:
                result = self.sim("chanceblog.yml", reg, event, inputs)
                with self.subTest(label=label, workflow="chanceblog", event=event, inputs=inputs):
                    self.assertEqual(result.failed_at, "flow")
                    self.assertNotIn("commit", result.ran)
            for event, inputs in EVENTS[1:]:
                result = self.sim("chance-fix-images.yml", reg, event, inputs)
                with self.subTest(label=label, workflow="fix-images", event=event, inputs=inputs):
                    self.assertNotIn("commit", result.ran)
                    self.assertEqual(result.failed_at, self.LOCK_STEP if real_run(event, inputs) else "기존 글 이미지 교체 실행")     # 연습은 잠금 단계를 건너뛰고 생성기 가드가 멈춘다

    def test_without_the_lock_the_image_fix_workflow_commits_exactly_like_before(self):
        for event, inputs in EVENTS[1:]:
            result = self.sim("chance-fix-images.yml", today_registry(), event, inputs)
            self.assertIsNone(result.failed_at)
            self.assertEqual("commit" in result.ran, real_run(event, inputs))

    def test_the_lock_check_step_is_right_after_python_is_set_up_and_before_anything_that_writes(self):
        names = [step.get("name") or step.get("uses") for step in load("chance-fix-images.yml")["jobs"]["build"]["steps"]]
        self.assertEqual(names, ["actions/checkout@v6", "actions/setup-python@v6", "제한 재개 잠금 확인 (켜져 있으면 직접 커밋 금지)", "의존성 설치",
                                 "기존 글 이미지 교체 실행", "변경 사항 커밋", "Pages 배포 실행 (새 커밋이 있을 때만)"])
        step = load("chance-fix-images.yml")["jobs"]["build"]["steps"][2]
        self.assertEqual(step["run"], "python -m pipeline.publish_lock check-direct")
        self.assertEqual(step["if"], "${{ !inputs.dry_run }}")                          # 연습 실행(저장 안 함)만 건너뛴다 — 입력 dry_run 은 boolean(커밋 단계 조건과 같은 식)
        commit = next(item for item in load("chance-fix-images.yml")["jobs"]["build"]["steps"] if item.get("id") == "commit")
        self.assertIn("inputs.dry_run", commit["if"])                                    # 연습이면 커밋 단계도 건너뛴다 — 두 조건이 같은 입력을 본다
        self.assertNotIn("env", step)
        self.assertNotIn("continue-on-error", step)

    def test_the_generator_guard_is_the_second_lock_for_the_image_fix(self):
        """워크플로 단계를 못 거쳤더라도(코드로 직접 실행) 생성기 가드가 같은 일을 한다 — GuardFixImagesTest 와 GeneratorMainTest 가 값을 확인한다."""
        text = Path(g.__file__).read_text(encoding="utf-8")
        self.assertIn("publish_lock.guard_start(os.environ, HISTORY_FILE, now_kst, FIX_IMAGES, DRY_RUN, write_step_summary)", text)
        main_source = text[text.index("def main():"):text.index("def run_cli():")]
        self.assertLess(main_source.index("_pause_on()"), main_source.index("publish_lock.guard_start"))
        self.assertLess(main_source.index("publish_lock.guard_start"), main_source.index("if FIX_IMAGES:"))
        self.assertLess(main_source.index("publish_lock.guard_start"), main_source.index("generate_blog_posts("))


class GeneratorChangeIsSmallTest(unittest.TestCase):
    def test_generator_py_only_gained_the_import_and_the_call_in_main(self):
        """generator.py 는 main() 앞부분에 가드를 부르는 줄만 더했다(다른 에이전트가 같은 파일을 고친다 — 충돌 최소화). 줄 수를 못박는다."""
        text = Path(g.__file__).read_text(encoding="utf-8")
        self.assertEqual(text.count("publish_lock"), 2)          # import 한 줄 + 호출 한 줄(다른 곳에는 이름이 없다 — 순서 주석에도 이 이름을 쓰지 않는다)
        self.assertIn("정지 검사 → 그림자 분기(SHADOW_RUN, 읽기 전용으로 처리하고 끝난다) → 아래 잠금 가드", text)          # 합친 뒤의 순서(A)를 코드에 남겼다
        self.assertIn("그림자 분기를 이 가드 아래에 두지 않는다", text)
        self.assertEqual(text.count("from pipeline import publish_lock"), 1)
        self.assertEqual(text.count("publish_lock.guard_start("), 1)


if __name__ == "__main__":
    unittest.main()
