"""제한 재개 잠금의 주간 상한(규칙 L8, pipeline/publish_lock.py) 시험 — 운영자 조건 '재개 시 편수 제한(주 1–2편)'(확인 요청 007 답, 2026-11-09)을 코드로 못박는다.

잠금이 켜져 있으면 Chance 는 굴러가는 7일(오늘을 포함해 오늘과 그 6일 전까지, KST 날짜)에 `chance.limits.max_posts_per_week`(1 또는 2)편까지만 만든다. 센 값은
① 이력(history.json)의 글 항목 + ② 이력에 아직 없는 열린 초안 브랜치(두 목록을 잇는 열쇠는 초안 브랜치 이름)다. 날짜를 믿을 수 없으면 멈추고, 초안 목록을 모르면 멈춘다(fail closed).
여기서는 ① 상수·규칙 L8(잠금 켬·꺼짐) ② 레지스트리 검증(registry.py) ③ 세기(weekly_posts) ④ 가드(창 경계·상한 정확히 2·우선순위·수동·읽기 전용 실행) ⑤ 이상한 날짜
⑥ 열린 초안과의 관계 ⑦ 생성기 main 수준의 하루하루와 두 달 치 흉내(어느 7일에도 상한을 넘지 않고 놀지도 않는다) ⑧ 명령줄·워크플로 입구(check·registry·plan·chance_flow)와 Blogger 러너
⑨ K1·K2 불변을 확인한다. 꺼진 상태의 출력이 바이트까지 같은지는 시나리오 도구(audit6/lockfix3)로 따로 견주었다.
네트워크·실제 시크릿·실제 git 없이 돈다(실제 git 이야기는 test_publish_lock_git).
"""
import contextlib
import io
import json
import random
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _bootstrap
import test_publish_lock as lt
from lock_helpers import CHANCE, KCYOON, MACAT, blog_of, drop_limit, lock_ready, mutated, put_in, real_registry, rules_in, set_limit, today_registry, with_lock_off, write_registry
from pipeline import draft_flow, drafts, plan, publish_lock, registry
from test_generator_drafts import PlainDirBase, run_tick
from test_generator_slots import at, candidate

KST = timezone(timedelta(hours=9))
NOW = lt.NOW                                   # 2026-11-09 10:00 KST
TODAY_DAY = date(2026, 11, 9)
ROOT = _bootstrap.ROOT


def day(offset, base=TODAY_DAY):
    """base(기본 오늘 2026-11-09)에서 offset 일 뒤의 날짜 글(YYYY-MM-DD)."""
    return (base + timedelta(days=offset)).isoformat()


def draft(offset, slot=9, base=TODAY_DAY, paths=None):
    """승인 흐름 이력 항목: 날짜는 base+offset, 브랜치 이름은 그 날짜와 슬롯으로 만든다(drafts.branch_name 과 같은 모양)."""
    date_text = day(offset, base)
    return lt.entry(date=date_text, slot=slot, branch="ai/draft/%s-s%d" % (date_text, slot), merged_paths=paths)


def branch(offset, slot=9, base=TODAY_DAY):
    return "ai/draft/%s-s%d" % (day(offset, base), slot)


BRANCH_A, BRANCH_B = lt.BRANCH_A, lt.BRANCH_B            # 2026-11-07-s9 · 2026-11-08-s18 — 둘 다 오늘(11-09)의 7일 창 안


def plain(offset, slot=9, base=TODAY_DAY):
    """승인 흐름이 아닌 이력 항목(옛·직접 게시: flow·branch 없음)."""
    return lt.entry(date=day(offset, base), slot=slot)


class WeeklyConstantsTest(unittest.TestCase):
    def test_the_constants_match_the_operator_decision(self):
        """운영자 조건: 재개 시 주 1–2편. 천장 2, 세는 창은 오늘을 포함한 7일."""
        self.assertEqual(publish_lock.MAX_POSTS_PER_WEEK, 2)
        self.assertEqual(publish_lock.WEEK_WINDOW_DAYS, 7)
        self.assertEqual(publish_lock.CODE_WEEKLY_CAP, "LOCK_WEEKLY_CAP")
        self.assertEqual(registry.WEEKLY_LIMIT_MAX, 14)
        self.assertLessEqual(publish_lock.MAX_POSTS_PER_WEEK, registry.WEEKLY_LIMIT_MAX)
        self.assertGreaterEqual(publish_lock.MAX_POSTS_PER_WEEK, publish_lock.MAX_POSTS_PER_DAY)       # 하루 상한이 주간 상한보다 크면 모순이다
        self.assertLessEqual(publish_lock.MAX_POSTS_PER_WEEK, publish_lock.MAX_POSTS_PER_DAY * publish_lock.WEEK_WINDOW_DAYS)

    def test_the_rules_list_ends_with_l8_and_names_the_week_and_the_one_blog_it_covers(self):
        self.assertEqual([rule for rule, _text in publish_lock.RULES][:9], ["L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"])     # 앞의 아홉 — 뒤에 규칙이 더해져도 깨지지 않는다
        text = dict(publish_lock.RULES)["L8"]
        for needle in ("chance.limits.max_posts_per_week", "1 이상 2 이하", "굴러가는 7일", "Chance 밖의 블로그에는 주간 상한을 강제하지 않는다"):
            self.assertIn(needle, text, needle)

    def test_the_skip_code_is_new_and_distinct_from_the_other_codes(self):
        codes = [publish_lock.CODE_BLOCKED, publish_lock.CODE_DAILY_CAP, publish_lock.CODE_WEEKLY_CAP, publish_lock.CODE_OPEN_DRAFTS, publish_lock.CODE_DRAFTS_UNKNOWN]
        self.assertEqual(len(set(codes)), len(codes))

    def test_the_ready_registry_carries_the_fifth_value_the_t3_change_will_set(self):
        self.assertEqual(blog_of(lock_ready(), CHANCE)["limits"]["max_posts_per_week"], 2)
        self.assertEqual(publish_lock.weekly_posts_limit(lock_ready()), 2)
        self.assertIsNone(publish_lock.weekly_posts_limit(today_registry()))             # 켜지기 전의 레지스트리에는 값이 없다 — 이전과 같다(진짜 레지스트리 값에 묶인 표지판은 test_publish_lock 의 한 시험뿐이다)



class WeeklyLimitReadTest(unittest.TestCase):
    def test_only_a_positive_integer_of_the_chance_entry_is_read(self):
        reg = lock_ready()
        self.assertEqual(publish_lock.weekly_posts_limit(reg), 2)
        for bad in ("2", True, False, 0, -1, None, 2.0, 1.5, [], {}):
            set_limit(reg, CHANCE, max_posts_per_week=bad)
            self.assertIsNone(publish_lock.weekly_posts_limit(reg), bad)
        self.assertIsNone(publish_lock.weekly_posts_limit({"blogs": []}))
        self.assertIsNone(publish_lock.weekly_posts_limit({}))

    def test_the_value_is_inherited_from_defaults_and_the_chance_entry_overrides_it(self):
        reg = lock_ready()
        drop_limit(reg, CHANCE, "max_posts_per_week")
        reg["defaults"]["limits"] = {"max_posts_per_day": 1, "max_posts_per_week": 1}
        self.assertEqual(publish_lock.weekly_posts_limit(reg), 1)                        # defaults 에서 물려받는다(레지스트리가 합치는 방식과 같다)
        set_limit(reg, CHANCE, max_posts_per_week=2)
        self.assertEqual(publish_lock.weekly_posts_limit(reg), 2)                        # 항목이 직접 적은 값이 이긴다

    def test_other_blogs_values_are_never_read(self):
        reg = lock_ready()
        drop_limit(reg, CHANCE, "max_posts_per_week")
        set_limit(reg, MACAT, max_posts_per_week=1)
        set_limit(reg, KCYOON, max_posts_per_week=2)
        self.assertIsNone(publish_lock.weekly_posts_limit(reg))


class WeeklyLimitRuleTest(unittest.TestCase):
    """규칙 L8: 잠금이 켜져 있으면 chance.limits.max_posts_per_week 가 있어야 하고(없으면 오류 — fail closed) 1 이상 2 이하 정수다. 꺼져 있으면 값이 있을 때만 모양(1 이상 정수)을 본다."""

    ON_BAD = [("0", 0), ("음수", -1), ("3(천장 초과)", 3), ("14(레지스트리 범위 안, 천장 초과)", 14), ("15", 15), ("참", True), ("거짓", False), ("문자열 '2'", "2"), ("소수 1.5", 1.5),
              ("소수 2.0", 2.0), ("null", None), ("빈 목록", []), ("빈 사전", {})]
    SHAPE_BAD = [("0", 0), ("음수", -1), ("참", True), ("거짓", False), ("문자열 '2'", "2"), ("소수 1.5", 1.5), ("소수 2.0", 2.0), ("null", None), ("빈 목록", []), ("빈 사전", {})]
    SHAPE_OK_WHEN_OFF = [("3", 3), ("14", 14), ("2", 2), ("1", 1)]

    def test_values_one_and_two_pass_with_the_lock_on(self):
        for good in (1, 2):
            reg = lock_ready()
            set_limit(reg, CHANCE, max_posts_per_week=good)
            self.assertEqual(publish_lock.lock_errors(reg), [], good)
            self.assertEqual(registry.validate_registry(reg), [], good)

    def test_a_missing_value_is_an_error_with_the_lock_on(self):
        reg = mutated(lambda r: drop_limit(r, CHANCE, "max_posts_per_week"))
        errors = publish_lock.lock_errors(reg)
        self.assertEqual(rules_in(errors), {"L8"})
        self.assertEqual(len(errors), 1)
        for piece in ("제한 재개 잠금 L8", "chance.limits.max_posts_per_week", "없습니다", "1 이상 2 이하 정수", "굴러가는 7일"):
            self.assertIn(piece, errors[0], piece)
        self.assertTrue(any("L8" in message for message in registry.validate_registry(reg)))        # 전체 검증(REG-1)도 같은 문장을 낸다

    def test_every_bad_value_is_an_error_naming_the_value_with_the_lock_on(self):
        for label, bad in self.ON_BAD:
            with self.subTest(case=label):
                reg = mutated(lambda r, bad=bad: set_limit(r, CHANCE, max_posts_per_week=bad))
                errors = publish_lock.lock_errors(reg)
                self.assertEqual(rules_in(errors), {"L8"}, errors)
                self.assertEqual(len(errors), 1)
                self.assertIn("1 이상 2 이하 정수", errors[0])
                self.assertIn("(지금 %s)" % publish_lock._shown(bad), errors[0])
                self.assertTrue(any("L8" in message for message in registry.validate_registry(reg)))

    def test_a_value_only_in_defaults_satisfies_the_rule_because_the_registry_merges_defaults(self):
        reg = lock_ready()
        drop_limit(reg, CHANCE, "max_posts_per_week")
        reg["defaults"]["limits"] = {**reg["defaults"].get("limits", {}), "max_posts_per_week": 2}
        self.assertEqual(publish_lock.lock_errors(reg), [])
        self.assertEqual(registry.validate_registry(reg), [])
        self.assertEqual(publish_lock.weekly_posts_limit(reg), 2)
        reg["defaults"]["limits"]["max_posts_per_week"] = 3                                # 물려받은 값도 같은 규칙으로 판정한다
        self.assertEqual(rules_in(publish_lock.lock_errors(reg)), {"L8"})

    def test_the_lock_off_ignores_a_missing_value_and_values_above_the_ceiling(self):
        """꺼짐 = 이전과 같다: 값이 없거나(지금의 레지스트리) 천장(2)을 넘어도(L8 은 켜졌을 때만 천장을 본다) 규칙 오류가 없다."""
        self.assertEqual(publish_lock.registry_errors(today_registry()), [])
        self.assertEqual(registry.validate_registry(today_registry()), [])
        for label, good in self.SHAPE_OK_WHEN_OFF:
            with self.subTest(case=label):
                reg = today_registry()
                set_limit(reg, CHANCE, max_posts_per_week=good)
                self.assertEqual(publish_lock.registry_errors(reg), [])
                self.assertEqual(publish_lock.lock_errors(reg), [])
                self.assertEqual(registry.validate_registry(reg), [])

    def test_the_lock_off_still_rejects_a_value_of_the_wrong_shape_like_the_open_drafts_limit_does(self):
        """L5(max_open_drafts)와 같은 방식: 잠금이 꺼져 있어도 값이 적혀 있으면 모양(1 이상 정수 — 불리언 아님)을 본다. 잘못 적은 값이 조용히 '주간 상한 없음'이 되지 않게."""
        for label, bad in self.SHAPE_BAD:
            with self.subTest(case=label):
                reg = today_registry()
                set_limit(reg, CHANCE, max_posts_per_week=bad)
                errors = publish_lock.registry_errors(reg)
                self.assertEqual(rules_in(errors), {"L8"}, errors)
                self.assertEqual(len(errors), 1)
                self.assertIn("1 이상 정수", errors[0])
                self.assertNotIn("1 이상 2 이하", errors[0])                                     # 천장은 켜졌을 때만 말한다
                self.assertEqual(publish_lock.lock_errors(reg), [])                         # 잠금 규칙(켜졌을 때만)이 아니라 값 모양 검사다

    def test_an_explicit_false_behaves_like_no_key_for_the_weekly_value_too(self):
        reg = lock_ready()
        reg["resume_lock"] = False
        set_limit(reg, CHANCE, max_posts_per_week=3)
        self.assertEqual(publish_lock.registry_errors(reg), [])
        self.assertEqual(registry.validate_registry(reg), [])

    def test_an_invalid_lock_value_is_read_as_locked_so_the_rule_applies(self):
        reg = lock_ready()
        reg["resume_lock"] = "true"
        drop_limit(reg, CHANCE, "max_posts_per_week")
        self.assertEqual(rules_in(publish_lock.lock_errors(reg)), {"L0", "L8"})

    def test_without_a_chance_blog_there_is_no_weekly_rule(self):
        reg = mutated(lambda r: r["blogs"].remove(blog_of(r, CHANCE)))
        self.assertEqual(publish_lock.lock_errors(reg), [])
        self.assertIsNone(publish_lock.weekly_posts_limit(reg))

    def test_other_blogs_are_not_held_to_a_weekly_cap(self):
        """Chance 밖의 블로그(Blogger·네이버 초안 패키지)는 운영자가 직접 게시하는 초안 흐름이라 하루 상한(L7)만 있다 — 주간 상한을 강제하지 않는다."""
        reg = lock_ready()
        for key in (MACAT, KCYOON):
            self.assertNotIn("max_posts_per_week", blog_of(reg, key).get("limits", {}))
        self.assertEqual(publish_lock.lock_errors(reg), [])
        set_limit(reg, MACAT, max_posts_per_week=7)                                          # 레지스트리 범위(1–14) 안의 값은 그냥 둔다
        self.assertEqual(publish_lock.lock_errors(reg), [])
        self.assertEqual(registry.validate_registry(reg), [])

    def test_messages_are_one_line_and_show_odd_values_safely(self):
        evil = "x\n::error::가짜 주석\n##[group]"
        reg = mutated(lambda r: set_limit(r, CHANCE, max_posts_per_week=evil))
        joined = "".join(publish_lock.lock_errors(reg))
        self.assertNotIn("\n", joined)
        self.assertNotIn("::error::", joined)
        self.assertNotIn("##[", joined)

    def test_malformed_registries_never_raise(self):
        weird = [{"resume_lock": True, "blogs": [{"key": "chance", "limits": None}]}, {"resume_lock": True, "blogs": [{"key": "chance", "limits": "x"}]},
                 {"resume_lock": True, "defaults": {"limits": 3}, "blogs": [{"key": "chance"}]}, {"resume_lock": True, "blogs": [{"key": "chance", "limits": {"max_posts_per_week": object}}]}]
        for reg in weird:
            with self.subTest(reg=repr(reg)[:80]):
                self.assertIsInstance(publish_lock.lock_errors(reg), list)
                self.assertIsInstance(publish_lock.registry_errors(reg), list)
                publish_lock.weekly_posts_limit(reg)


class RegistryWeeklyLimitTest(unittest.TestCase):
    """pipeline/registry.py: limits.max_posts_per_week 는 모든 블로그 항목과 defaults.limits 에서 알려진 키다 — 값이 있으면 1–14 정수(불리언 아님), 없으면 이전과 같다."""

    BAD = [0, -1, 15, 100, True, False, "2", 2.0, 1.5, None, [], {}]

    def errors_for(self, mutate):
        reg = today_registry()
        mutate(reg)
        return [message for message in registry.validate_registry(reg) if "max_posts_per_week" in message]

    def test_the_real_registry_and_every_registry_without_the_key_are_unchanged(self):
        self.assertEqual(registry.validate_registry(real_registry()), [])
        self.assertEqual(registry.validate_registry(today_registry()), [])
        self.assertEqual(registry.validate_registry(lock_ready()), [])

    def test_every_value_from_one_to_fourteen_is_accepted_for_every_blog_with_the_lock_off(self):
        for value in range(1, 15):
            for key in (CHANCE, MACAT, KCYOON, "naver_life_tips"):
                reg = today_registry()
                set_limit(reg, key, max_posts_per_week=value)
                self.assertEqual(registry.validate_registry(reg), [], (value, key))

    def test_every_bad_value_is_rejected_for_every_blog_naming_the_blog_and_the_range(self):
        for value in self.BAD:
            for key in (CHANCE, MACAT, KCYOON, "naver_life_tips"):
                with self.subTest(value=repr(value), blog=key):
                    errors = self.errors_for(lambda r, key=key, value=value: set_limit(r, key, max_posts_per_week=value))
                    registry_errors = [message for message in errors if message.startswith("블로그 '%s': limits.max_posts_per_week" % key)]
                    self.assertEqual(len(registry_errors), 1, errors)
                    self.assertIn("1–14 정수", registry_errors[0])
                    self.assertIn("(지금 %s)" % publish_lock._shown(value), registry_errors[0])

    def test_a_boolean_is_rejected_even_though_python_counts_true_as_one(self):
        self.assertEqual(len(self.errors_for(lambda r: set_limit(r, CHANCE, max_posts_per_week=True))), 2)        # 검증기의 일반 검사 + L8 의 모양 검사
        self.assertEqual(len(self.errors_for(lambda r: set_limit(r, MACAT, max_posts_per_week=True))), 1)        # Chance 밖: 일반 검사 하나뿐(L8 은 Chance 만)
        self.assertEqual(self.errors_for(lambda r: set_limit(r, MACAT, max_posts_per_week=1)), [])

    def test_defaults_limits_is_validated_on_its_own_once(self):
        for value in self.BAD:
            with self.subTest(value=repr(value)):
                errors = self.errors_for(lambda r, value=value: r["defaults"].update(limits={**r["defaults"].get("limits", {}), "max_posts_per_week": value}))
                own = [message for message in errors if message.startswith("defaults: limits.max_posts_per_week")]
                self.assertEqual(len(own), 1, errors)                                   # 물려받은 블로그마다 되풀이하지 않는다
                self.assertFalse(any(message.startswith("블로그 '") and "limits.max_posts_per_week는" in message for message in errors), errors)

    def test_a_bad_default_is_caught_even_when_every_blog_overrides_it(self):
        reg = today_registry()
        reg["defaults"]["limits"] = {**reg["defaults"]["limits"], "max_posts_per_week": 99}
        for raw in reg["blogs"]:
            raw["limits"] = {**raw.get("limits", {}), "max_posts_per_week": 1}
        messages = [message for message in registry.validate_registry(reg) if "max_posts_per_week" in message]
        self.assertEqual(len(messages), 1, messages)
        self.assertTrue(messages[0].startswith("defaults: "))

    def test_a_bad_default_is_caught_even_when_the_blog_list_is_broken(self):
        reg = today_registry()
        reg["defaults"]["limits"] = {**reg["defaults"]["limits"], "max_posts_per_week": 0}
        reg["blogs"] = []
        messages = registry.validate_registry(reg)
        self.assertTrue(any(message.startswith("defaults: limits.max_posts_per_week") for message in messages), messages)
        self.assertTrue(any("blogs는 비어 있지 않은 배열" in message for message in messages), messages)

    def test_a_good_default_is_inherited_without_any_error(self):
        reg = today_registry()
        reg["defaults"]["limits"] = {**reg["defaults"]["limits"], "max_posts_per_week": 3}
        self.assertEqual(registry.validate_registry(reg), [])

    def test_the_check_never_raises_on_odd_shapes(self):
        for limits in (None, "x", 3, [], {}, {"max_posts_per_day": 1}):
            self.assertIsNone(registry._weekly_limit_error(limits, "블로그 'x'"))
        self.assertIsNotNone(registry._weekly_limit_error({"max_posts_per_week": object()}, "블로그 'x'"))

    def test_the_message_is_one_line_even_for_a_hostile_value(self):
        message = registry._weekly_limit_error({"max_posts_per_week": "x\n::error::가짜\n" * 30}, "블로그 'x'")
        self.assertNotIn("\n", message)
        self.assertLess(len(message), 200)

    def test_with_the_lock_on_a_value_in_the_registry_range_but_above_the_ceiling_is_only_a_lock_error(self):
        reg = mutated(lambda r: set_limit(r, CHANCE, max_posts_per_week=3))
        messages = [message for message in registry.validate_registry(reg) if "max_posts_per_week" in message]
        self.assertEqual(len(messages), 1)
        self.assertIn("L8", messages[0])


class WeeklyDayParseTest(unittest.TestCase):
    def test_only_a_real_ascii_calendar_date_is_read(self):
        for good, expected in (("2026-11-09", date(2026, 11, 9)), ("2026-02-28", date(2026, 2, 28)), ("2028-02-29", date(2028, 2, 29)), ("0001-01-01", date(1, 1, 1)), ("9999-12-31", date(9999, 12, 31))):
            self.assertEqual(publish_lock.parse_day(good), expected, good)

    def test_everything_else_is_unreadable(self):
        odd = [None, 20261109, 2026.1109, True, False, [], {}, "", " ", "2026-11-9", "2026-1-09", "26-11-09", "2026/11/09", "2026.11.09", "20261109", "2026-11-09T09:00:00+09:00",
               "2026-11-09T00:00:00Z", "2026-11-09 09:00", "2026-11-09+09:00", " 2026-11-09", "2026-11-09 ", "2026-11-09\n", "\n2026-11-09", "2026-11-09\x00", "２０２６-１１-０９",
               "2026-02-30", "2027-02-29", "2026-13-01", "2026-00-10", "2026-11-00", "0000-01-01", "yesterday", "오늘", "2026-11-09-s9", "ai/draft/2026-11-09-s9"]
        for value in odd:
            self.assertIsNone(publish_lock.parse_day(value), repr(value))

    def test_arabic_indic_and_other_unicode_digits_are_not_dates(self):
        self.assertIsNone(publish_lock.parse_day("٢٠٢٦-١١-٠٩"))
        self.assertIsNone(publish_lock.parse_day("２０２６-11-09"))

    def test_the_window_starts_six_days_before_today_and_crosses_months_years_and_leap_days(self):
        self.assertEqual(publish_lock.week_start(date(2026, 11, 9)), date(2026, 11, 3))
        self.assertEqual(publish_lock.week_start(date(2026, 11, 3)), date(2026, 10, 28))
        self.assertEqual(publish_lock.week_start(date(2027, 1, 2)), date(2026, 12, 27))
        self.assertEqual(publish_lock.week_start(date(2026, 3, 2)), date(2026, 2, 24))
        self.assertEqual(publish_lock.week_start(date(2028, 3, 2)), date(2028, 2, 25))                  # 윤년
        self.assertEqual((date(2026, 11, 9) - publish_lock.week_start(date(2026, 11, 9))).days, publish_lock.WEEK_WINDOW_DAYS - 1)


class WeeklyCountTest(unittest.TestCase):
    """weekly_posts(history, remote_names, today): 창 경계·중복 제거·날짜를 믿을 수 없는 항목."""

    def count(self, history, names=(), today=TODAY_DAY):
        return publish_lock.weekly_posts(history, list(names), today)

    def test_nothing_in_nothing_out(self):
        self.assertEqual(self.count([]), (0, 0, 0, 0))

    def test_today_and_six_days_ago_are_inside_and_seven_days_ago_is_outside(self):
        for offset, expected in ((0, 1), (-1, 1), (-5, 1), (-6, 1), (-7, 0), (-8, 0), (-30, 0), (-400, 0)):
            self.assertEqual(self.count([plain(offset)]).count, expected, offset)

    def test_a_date_after_today_is_not_counted_but_reported(self):
        for offset in (1, 2, 30, 3000):
            found = self.count([plain(offset)])
            self.assertEqual(found, (0, 0, 1, 0), offset)

    def test_the_window_follows_today(self):
        history = [plain(offset) for offset in (-10, -7, -6, -3, 0)]
        self.assertEqual(self.count(history).count, 3)
        self.assertEqual(self.count(history, today=TODAY_DAY + timedelta(days=1)).count, 2)       # 내일이면 6일 전이던 항목이 7일 전이 되어 빠진다
        self.assertEqual(self.count(history, today=TODAY_DAY - timedelta(days=3)).count, 3)       # 사흘 전이면 창은 9일 전부터 3일 전까지: 7일 전·6일 전·3일 전 항목이 들어온다
        self.assertEqual(self.count(history, today=TODAY_DAY - timedelta(days=3)).future, 1)      # 오늘 항목은 그날 기준으로 미래다

    def test_every_dict_entry_counts_once_whatever_its_shape(self):
        history = [plain(-1), plain(-2, slot=None), {"date": day(-3)}, draft(-4), draft(-5, slot=18)]
        self.assertEqual(self.count(history).count, 5)

    def test_merged_closed_and_pending_drafts_all_count_because_they_are_all_in_the_history(self):
        merged = draft(-4, paths=["_posts/m/KR.md", "_posts/m/EN.md"])
        closed_or_pending = draft(-2)
        self.assertEqual(self.count([merged, closed_or_pending]).count, 2)                    # 글이 main 에 있는지 보지 않는다 — 만든 글은 이력에 남는다

    def test_non_dict_entries_are_skipped_like_the_slot_and_daily_counters_do(self):
        """실제 이력의 맨 앞 5개는 옛 형식의 제목 문자열이다 — 날짜가 없어 글 항목이 아니다(이것을 '읽을 수 없음'으로 멈추면 켜는 순간 영영 못 돈다)."""
        history = ["국가직 전환 5년 차의 그늘", "치솟는 연산량과 AI 렌더링의 역설", None, 3, 4.5, True, [], [plain(-1)], plain(-1)]
        self.assertEqual(self.count(history), (1, 0, 0, 0))

    def test_the_real_history_file_is_fully_readable(self):
        """저장소의 실제 history.json 을 센다: 사전 항목은 모두 YYYY-MM-DD 날짜를 갖고 미래 날짜가 없다 — 새 항목이 이 약속을 깨면 켠 뒤 가드가 멈추므로 여기서 먼저 빨강이 된다."""
        history = json.loads((ROOT / "history.json").read_text(encoding="utf-8"))
        found = self.count(history, today=date(2099, 1, 1))
        self.assertEqual(found, (0, 0, 0, 0))

    def test_each_odd_date_is_unreadable_and_is_never_counted(self):
        odd = [{}, {"topic": "날짜 없음"}, {"date": None}, {"date": 20261109}, {"date": ""}, {"date": "어제"}, {"date": "2026-11-9"}, {"date": "2026/11/09"}, {"date": day(-1) + "T09:00:00+09:00"},
               {"date": day(-1) + " 09:00"}, {"date": " " + day(-1)}, {"date": day(-1) + "\n"}, {"date": "２０２６-１１-０９"}, {"date": "2026-02-30"}, {"date": True}, {"date": [day(-1)]},
               {"date": {"d": day(-1)}}]
        for item in odd:
            with self.subTest(item=repr(item)):
                self.assertEqual(self.count([item]), (0, 1, 0, 0))
        self.assertEqual(self.count(odd + [plain(-1)]).count, 1)                                # 읽을 수 있는 항목은 따로 센다 — 멈출지는 호출한 쪽이 정한다

    def test_the_branch_name_links_the_history_and_the_remote_so_nothing_is_counted_twice(self):
        history = [draft(-3), draft(-5)]
        names = [branch(-3), branch(-5)]
        self.assertEqual(self.count(history, names).count, 2)                                  # 넷이 아니라 둘
        self.assertEqual(self.count(history, names + names).count, 2)                          # 목록에 같은 이름이 거듭 있어도 한 번
        self.assertEqual(self.count(history, []).count, 2)                                     # 원격에 없어도(병합 뒤 정리됨) 이력으로 센다
        self.assertEqual(self.count([], names).count, 2)                                       # 이력에 없으면 브랜치로 센다

    def test_a_remote_only_branch_counts_by_the_date_in_its_name(self):
        for offset, expected in ((0, 1), (-6, 1), (-7, 0), (-20, 0)):
            self.assertEqual(self.count([], [branch(offset)]).count, expected, offset)
        self.assertEqual(self.count([], [branch(-2), branch(-2, slot=18), "ai/draft/%s-m091722" % day(-2)]).count, 3)      # 정기(슬롯)·수동(시각) 이름 모두

    def test_a_remote_only_branch_dated_after_today_is_reported_not_counted(self):
        self.assertEqual(self.count([], [branch(1)]), (0, 0, 0, 1))
        self.assertEqual(self.count([], [branch(1), branch(-1)]), (1, 0, 0, 1))

    def test_names_this_flow_never_makes_are_ignored(self):
        names = ["ai/draft/odd", "ai/draft/2026-13-40-s9", "ai/draft/2026-11-09-s99", "ai/draft/2026-11-09-s9-extra", "ai/draft/2026-11-09", "ai/other/2026-11-09-s9", "main", "", "ai/draft/"]
        self.assertEqual(self.count([], names), (0, 0, 0, 0))

    def test_an_entry_that_is_not_a_pr_flow_entry_does_not_link_its_branch(self):
        """이력 항목이 flow=pr 이고 branch 가 글자일 때만 원격 브랜치와 잇는다(drafts.unmerged_draft_branches 와 같은 규칙). 잇지 못하면 두 번 센다 — 상한을 넘기는 쪽으로는 틀리지 않는 쪽이다."""
        direct = {"date": day(-3), "slot": 9, "branch": branch(-3), "paths": ["_posts/a/KR.md", "_posts/b/EN.md"]}          # flow 가 없다
        self.assertEqual(self.count([direct], [branch(-3)]).count, 2)
        self.assertEqual(self.count([{**direct, "flow": "direct"}], [branch(-3)]).count, 2)
        self.assertEqual(self.count([{**direct, "flow": "pr", "branch": 3}], [branch(-3)]).count, 2)
        self.assertEqual(self.count([{**direct, "flow": "pr"}], [branch(-3)]).count, 1)

    def test_a_history_entry_decides_the_date_even_if_the_branch_name_says_another(self):
        history = [{**draft(-3), "branch": branch(-12)}]                                       # 이력 날짜는 안, 이름 날짜는 밖
        self.assertEqual(self.count(history, [branch(-12)]).count, 1)
        history = [{**draft(-12), "branch": branch(-3)}]
        self.assertEqual(self.count(history, [branch(-3)]).count, 0)                           # 이력과 이어진 브랜치는 이름 날짜로 다시 세지 않는다

    def test_the_history_and_the_remote_lists_are_not_changed(self):
        history, names = [draft(-3), "x", {"date": "?"}], [branch(-3), branch(-4)]
        before = (repr(history), list(names))
        self.count(history, names)
        self.assertEqual((repr(history), names), before)

    def test_any_iterable_of_names_works_once(self):
        self.assertEqual(publish_lock.weekly_posts([], (name for name in [branch(-1), branch(-2)]), TODAY_DAY).count, 2)
        self.assertEqual(publish_lock.weekly_posts([], {branch(-1): "a" * 40, branch(-2): "b" * 40}, TODAY_DAY).count, 2)       # git ls-remote 결과(이름 → 해시 사전)

    def test_a_random_mix_agrees_with_an_independent_count(self):
        """다른 방식(오늘과의 차이 일수)으로 센 값과 같다: 차이가 0–6일이면 센다, 음수(미래)는 따로 알리고, 7 이상은 세지 않는다. 이력 항목 하나·이력과 이어진 브랜치·이력에 없는 브랜치(같은 이름이 거듭 와도 한 번)."""
        rng = random.Random(20261110)
        for _ in range(300):
            history, names, used = [], [], set()
            expected = future = branch_future = 0
            for _item in range(rng.randint(0, 12)):
                offset = rng.randint(-15, 4)
                inside = 1 if -6 <= offset <= 0 else 0
                kind = rng.choice(("plain", "draft", "remote"))
                if kind == "plain":
                    history.append(plain(offset))
                    expected += inside
                    future += 1 if offset > 0 else 0
                elif kind == "draft":
                    item = draft(offset, slot=rng.randint(0, 23))
                    if item["branch"] in used:
                        continue
                    used.add(item["branch"])
                    history.append(item)
                    names.append(item["branch"])                              # 이력과 이어진 브랜치 — 이름으로 다시 세지 않는다
                    expected += inside
                    future += 1 if offset > 0 else 0
                else:
                    name = "ai/draft/%s-m%06d" % (day(offset), rng.randint(0, 235959))
                    if name in used:
                        continue
                    used.add(name)
                    names.extend([name] * rng.randint(1, 2))                  # 이력에 없는 브랜치 — 이름이 거듭 와도 한 건
                    expected += inside
                    branch_future += 1 if offset > 0 else 0
            rng.shuffle(names)
            self.assertEqual(self.count(history, names), (expected, 0, future, branch_future), (history, names))


class WeeklyGuardBase(lt.GuardBase):
    def guard(self, reg, **kwargs):
        kwargs.setdefault("exists", lambda path: False)      # 이력 항목의 글 파일이 main 에 있는지(병합됨) — 따로 정하지 않으면 없는 것으로 둔다(작업 폴더에 따라 달라지지 않게)
        return super().guard(reg, **kwargs)

    def cap_lines(self, result):
        return [line for line in result.out if line.startswith("[SKIP] code=LOCK_WEEKLY_CAP")]


class GuardWeeklyCapTest(WeeklyGuardBase):
    def test_the_second_post_of_the_week_is_allowed_and_the_third_is_skipped(self):
        one = self.guard(lock_ready(), history=[draft(-3)], remote=[branch(-3)])
        self.assertEqual((one.code, one.out), (None, []))
        two = self.guard(lock_ready(), history=[draft(-3), draft(-5)], remote=[branch(-3), branch(-5)])
        self.assertEqual(two.code, 0)
        self.assertEqual(two.out[0], "[SKIP] code=LOCK_WEEKLY_CAP since=2026-11-03 until=2026-11-09 week=2 cap=2")
        self.assertEqual(two.remote_calls, [1])                                                   # 열린 초안 상한과 같은 원격 목록을 한 번만 읽는다
        self.assertFalse(any(line.startswith("::") for line in two.out))                           # 정상 건너뜀이다 — 정기 실행에는 주석이 없다
        self.assertIn("**LOCK_WEEKLY_CAP**", two.summary[0])

    def test_the_log_and_summary_say_in_plain_korean_which_dates_how_many_and_the_cap(self):
        result = self.guard(lock_ready(), history=[plain(-1), plain(-2)], remote=[])
        text = next(line for line in result.out if line.startswith("[잠금] "))
        for piece in ("최근 7일(2026-11-03부터 2026-11-09까지)", "이미 2건", "주간 상한(2건)", "정상 건너뜀", "승인 대기·닫은 초안도 건수에 들어갑니다"):
            self.assertIn(piece, text, piece)
        self.assertIn("2026-11-03부터 2026-11-09까지", result.summary[0])
        self.assertNotIn("~", text + result.summary[0])
        self.assertNotIn("http", text + result.summary[0])
        self.assertNotIn("\n", text)

    def test_the_skip_line_is_one_key_value_line_like_the_daily_one(self):
        result = self.guard(lock_ready(), history=[plain(-1), plain(-2)], remote=[])
        line = self.cap_lines(result)[0]
        self.assertRegex(line, r"^\[SKIP\] code=LOCK_WEEKLY_CAP since=\d{4}-\d{2}-\d{2} until=\d{4}-\d{2}-\d{2} week=\d+ cap=\d+$")
        self.assertTrue(all("=" in token for token in line.split(" ")[2:]))

    def test_the_registry_value_is_the_cap_one_a_week_stops_after_one(self):
        reg = lock_ready()
        set_limit(reg, CHANCE, max_posts_per_week=1)
        stopped = self.guard(reg, history=[plain(-4)], remote=[])
        self.assertEqual(stopped.out[0], "[SKIP] code=LOCK_WEEKLY_CAP since=2026-11-03 until=2026-11-09 week=1 cap=1")
        self.assertEqual(self.guard(reg, history=[], remote=[]).code, None)
        self.assertEqual(self.guard(reg, history=[plain(-7)], remote=[]).code, None)               # 7일 전은 창 밖

    def test_the_cap_may_come_from_defaults(self):
        reg = lock_ready()
        drop_limit(reg, CHANCE, "max_posts_per_week")
        reg["defaults"]["limits"] = {**reg["defaults"]["limits"], "max_posts_per_week": 1}
        self.assertEqual(self.guard(reg, history=[plain(-4)], remote=[]).out[0], "[SKIP] code=LOCK_WEEKLY_CAP since=2026-11-03 until=2026-11-09 week=1 cap=1")

    def test_window_boundaries_today_six_days_ago_seven_days_ago(self):
        self.assertEqual(self.guard(lock_ready(), history=[plain(-6), plain(-6, slot=18)], remote=[]).code, 0)          # 6일 전 둘: 창 안
        self.assertEqual(self.guard(lock_ready(), history=[plain(-7), plain(-7, slot=18)], remote=[]).code, None)       # 7일 전 둘: 창 밖
        self.assertEqual(self.guard(lock_ready(), history=[plain(-6), plain(-7)], remote=[]).code, None)                # 하나만 창 안
        self.assertEqual(self.guard(lock_ready(), history=[plain(-6), plain(-1)], remote=[]).code, 0)
        self.assertEqual(self.guard(lock_ready(), history=[plain(-8), plain(-100), plain(-3)], remote=[]).code, None)

    def test_boundaries_across_a_month_a_year_and_midnight(self):
        year_end = datetime(2027, 1, 2, 9, 0, tzinfo=KST)
        self.assertEqual(self.guard(lock_ready(), history=[plain(-6, base=date(2027, 1, 2)), plain(-5, base=date(2027, 1, 2))], now=year_end, remote=[]).out[0],
                         "[SKIP] code=LOCK_WEEKLY_CAP since=2026-12-27 until=2027-01-02 week=2 cap=2")
        self.assertEqual(self.guard(lock_ready(), history=[plain(-7, base=date(2027, 1, 2)), plain(-6, base=date(2027, 1, 2))], now=year_end, remote=[]).code, None)
        after_midnight = datetime(2026, 11, 10, 0, 30, tzinfo=KST)                                   # UTC 로는 아직 11월 9일 15:30 이다
        self.assertEqual(self.guard(lock_ready(), history=[plain(-6, base=date(2026, 11, 10)), plain(-5, base=date(2026, 11, 10))], now=after_midnight, remote=[]).out[0],
                         "[SKIP] code=LOCK_WEEKLY_CAP since=2026-11-04 until=2026-11-10 week=2 cap=2")
        self.assertEqual(self.guard(lock_ready(), history=[plain(-7, base=date(2026, 11, 10)), plain(-6, base=date(2026, 11, 10))], now=after_midnight, remote=[]).code, None)
        leap = datetime(2028, 3, 2, 9, 0, tzinfo=KST)
        self.assertEqual(self.guard(lock_ready(), history=[plain(-6, base=date(2028, 3, 2)), plain(-1, base=date(2028, 3, 2))], now=leap, remote=[]).out[0],
                         "[SKIP] code=LOCK_WEEKLY_CAP since=2028-02-25 until=2028-03-02 week=2 cap=2")

    def test_the_daily_cap_wins_when_both_are_reached(self):
        result = self.guard(lock_ready(), history=[plain(0), plain(-2)], remote="unused")
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_DAILY_CAP date=2026-11-09 today=1 cap=1")
        self.assertEqual(self.cap_lines(result), [])
        self.assertEqual(result.remote_calls, [])                                                  # 하루 상한이 먼저 멈춰 원격은 읽지 않는다 — 기존 동작 그대로

    def test_a_manual_run_is_counted_and_skipped_too_with_a_notice(self):
        history = [plain(-1, slot=None), plain(-3, slot=None)]
        scheduled = self.guard(lock_ready(), history=history, remote=[], environ={"EVENT_NAME": "schedule"})
        manual = self.guard(lock_ready(), history=history, remote=[], environ={"EVENT_NAME": "workflow_dispatch"})
        unnamed = self.guard(lock_ready(), history=history, remote=[], environ={})
        self.assertEqual((scheduled.code, manual.code, unnamed.code), (0, 0, 0))
        self.assertFalse(any(line.startswith("::") for line in scheduled.out))
        notice = "::notice::제한 재개 잠금: 최근 7일 안에 이미 주간 상한만큼 글이 만들어져 이번 수동 실행은 글을 만들지 않았습니다(정상 건너뜀)."
        self.assertIn(notice, manual.out)
        self.assertIn(notice, unnamed.out)                                                          # 이름을 모르는 실행은 수동으로 읽는다(하루 상한과 같다)
        self.assertEqual(manual.out[0], scheduled.out[0])

    def test_a_manual_run_in_the_week_with_room_makes_a_post(self):
        result = self.guard(lock_ready(), history=[plain(-3)], remote=[], environ={"EVENT_NAME": "workflow_dispatch"})
        self.assertEqual((result.code, result.out), (None, []))

    def test_manual_runs_are_distinct_posts_even_on_the_same_day(self):
        """수동 실행은 슬롯이 없고(slot null) 브랜치 이름에 시각(HHMMSS)이 붙어 같은 날 여러 번 해도 서로 다른 글이다 — 건마다 센다."""
        history = [lt.entry(date=day(-2), slot=None, branch="ai/draft/%s-m101500" % day(-2)), lt.entry(date=day(-2), slot=None, branch="ai/draft/%s-m163000" % day(-2))]
        result = self.guard(lock_ready(), history=history, remote=["ai/draft/%s-m101500" % day(-2), "ai/draft/%s-m163000" % day(-2)])
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_WEEKLY_CAP since=2026-11-03 until=2026-11-09 week=2 cap=2")

    def test_a_practice_run_a_shadow_run_and_the_image_fix_practice_never_count_and_are_never_stopped(self):
        full = [plain(-1), plain(-2)]
        self.assertEqual(self.guard(lock_ready(), history=full, dry_run=True, remote="unused").code, None)
        self.assertEqual(self.guard(lock_ready(), history=full, environ={"EVENT_NAME": "workflow_dispatch", "SHADOW_RUN": "1"}, remote="unused").code, None)
        self.assertEqual(self.guard(lock_ready(), history=full, fix_images=True, dry_run=True, remote="unused").code, None)
        for value in ("0", "false", "no", "off", "disabled", ""):
            self.assertEqual(self.guard(lock_ready(), history=full, environ={"SHADOW_RUN": value}, remote=[]).code, 0, value)       # 그림자가 아니면 센다

    def test_with_the_lock_off_nothing_is_counted_even_if_the_registry_carries_the_value(self):
        """꺼짐 = 이전과 같다: 값이 적혀 있어도 잠금이 꺼져 있으면 주간 상한을 세지 않는다(모양만 본다)."""
        reg = with_lock_off(lock_ready())
        result = self.guard(reg, history=[plain(-1), plain(-2), plain(-3), plain(-4)], remote=[], exists=lambda path: False)
        self.assertEqual((result.code, result.out), (None, []))
        no_open = with_lock_off(lock_ready())
        drop_limit(no_open, CHANCE, "max_open_drafts")
        result = self.guard(no_open, history=[plain(-1), plain(-2), plain(-3)], remote="unused")
        self.assertEqual((result.code, result.out, result.summary, result.status), (None, [], [], []))     # 이력도 원격도 읽지 않는다

    def test_a_registry_without_the_weekly_value_is_counted_by_nobody(self):
        """값이 없으면 주간 상한이 없다(켜지기 전의 레지스트리). 켠 레지스트리는 L8 이 먼저 막으므로 값이 없는 채로 가드에 닿지 않는다."""
        reg = with_lock_off(lock_ready())
        drop_limit(reg, CHANCE, "max_posts_per_week")
        result = self.guard(reg, history=[plain(-1), plain(-2), plain(-3)], remote=[])
        self.assertEqual((result.code, result.out), (None, []))
        locked_without = mutated(lambda r: drop_limit(r, CHANCE, "max_posts_per_week"))
        stopped = self.guard(locked_without, history=[], remote=[])
        self.assertEqual(stopped.code, 1)
        self.assertIn("rules=L8", stopped.out[0])

    def test_a_locked_registry_that_breaks_l8_stops_before_anything_is_counted(self):
        for bad in (0, 3, True, "2", None):
            result = self.guard(mutated(lambda r, bad=bad: set_limit(r, CHANCE, max_posts_per_week=bad)), history=[], remote="unused")
            self.assertEqual(result.code, 1, bad)
            self.assertEqual(result.out[0], "[SKIP] code=LOCK_BLOCKED rules=L8", bad)
            self.assertEqual(result.remote_calls, [])

    def test_a_locked_registry_without_a_chance_blog_counts_nothing(self):
        reg = mutated(lambda r: r["blogs"].remove(blog_of(r, CHANCE)))
        self.assertEqual(self.guard(reg, history=[plain(-1), plain(-2), plain(-3)], remote="unused").code, None)

    def test_an_unreadable_remote_skips_the_run_even_when_the_history_alone_would_not_reach_the_cap(self):
        result = self.guard(lock_ready(), history=[plain(-3)], remote=None)
        self.assertEqual(result.code, 0)
        self.assertEqual(result.out[0], "[SKIP] code=OPEN_DRAFTS_UNKNOWN")
        self.assertEqual(self.cap_lines(result), [])
        self.assertIn("::warning::열린 초안 수를 확인하지 못해 이번 실행은 글을 만들지 않았습니다. 다음 실행에서 다시 시도합니다.", result.out)

    def test_the_summary_for_the_cap_is_a_single_line_in_the_bullet_list(self):
        result = self.guard(lock_ready(), history=[plain(-1), plain(-2)], remote=[])
        self.assertEqual(len(result.summary), 1)
        self.assertTrue(result.summary[0].startswith("### Chance_Blog 실행 요약\n- 결과: **LOCK_WEEKLY_CAP** — "))

    def test_the_status_line_still_comes_first_and_the_guard_writes_nothing_itself(self):
        out = []
        (self.folder / "history.json").write_text(json.dumps([plain(-1), plain(-2)]), encoding="utf-8")
        before = (self.folder / "history.json").read_bytes()
        with self.assertRaises(SystemExit) as caught:
            publish_lock.guard_start({"EVENT_NAME": "schedule"}, self.folder / "history.json", lambda: NOW, False, False, [].append, out=out.append, load=lambda: lock_ready(), remote_drafts=lambda: [])
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(out[0], lt.STATUS_PREFIX + "켜짐")
        self.assertEqual((self.folder / "history.json").read_bytes(), before)

    def test_the_existence_check_for_merged_posts_does_not_change_the_weekly_count(self):
        history = [draft(-3), draft(-5)]
        for exists in (lambda path: True, lambda path: False):
            result = self.guard(lock_ready(), history=history, remote=[branch(-3), branch(-5)], exists=exists)
            self.assertEqual(result.out[0], "[SKIP] code=LOCK_WEEKLY_CAP since=2026-11-03 until=2026-11-09 week=2 cap=2")

    def test_the_real_history_shape_lets_a_fresh_run_through(self):
        """실제 history.json 모양(맨 앞에 옛 형식 문자열 5개, 그다음 사전 항목들)을 켠 레지스트리·'오래 지난 오늘'로 돌려도 멈추지 않는다 — 켜는 순간 영영 못 도는 일이 없다."""
        raw = (ROOT / "history.json").read_text(encoding="utf-8")
        later = datetime(2099, 1, 1, 9, 0, tzinfo=KST)
        result = self.guard(lock_ready(), raw_history=raw, now=later, remote=[])
        self.assertEqual((result.code, result.out), (None, []))

    def test_a_clock_that_is_not_a_calendar_date_stops_the_run(self):
        """지금 날짜가 달력 날짜로 읽히지 않거나(글자·빈 글) 6일 전을 셀 수 없는 서기 1년 첫 주면 일주일 창을 정할 수 없어 멈춘다(정상 실행에서는 일어나지 않는다)."""
        (self.folder / "history.json").write_text("[]", encoding="utf-8")
        for text in ("not-a-date", "", "0000-01-01", "0001-01-01", "0001-01-06"):
            broken = SimpleNamespace(strftime=lambda fmt, text=text: text)
            out, summary = [], []
            with self.assertRaises(SystemExit) as caught:
                publish_lock.guard_start({"EVENT_NAME": "schedule"}, self.folder / "history.json", lambda: broken, False, False, summary.append, out=out.append, load=lambda: lock_ready(),
                                         remote_drafts=lambda: [])
            self.assertEqual(caught.exception.code, 1, text)
            self.assertIn("[SKIP] code=LOCK_BLOCKED reason=CLOCK_UNREADABLE", out)
            self.assertIn("::error::" + publish_lock.WEEKLY_DATE_ERROR, out)
            self.assertIn("**LOCK_BLOCKED**", summary[0])
        fine = SimpleNamespace(strftime=lambda fmt: "0001-01-07")                                     # 6일 전이 1년 1월 1일 — 셀 수 있는 가장 이른 날
        self.assertIsNone(publish_lock.guard_start({"EVENT_NAME": "schedule"}, self.folder / "history.json", lambda: fine, False, False, [].append, out=[].append,
                                                   load=lambda: lock_ready(), remote_drafts=lambda: []))


class WeeklyOpenDraftsTest(WeeklyGuardBase):
    """열린 초안 상한(L5)과 주간 상한(L8)이 같은 원격 목록을 쓰되 서로 다른 것을 센다: 열린 초안은 병합 안 된 브랜치, 주간은 이력의 글(병합된 것 포함)과 이력에 없는 브랜치."""

    def test_two_unmerged_drafts_inside_the_week_stop_a_third_even_though_the_open_limit_has_room(self):
        result = self.guard(lock_ready(), history=[], remote=[BRANCH_A, BRANCH_B], exists=lambda path: False)
        self.assertEqual(result.code, 0)
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_WEEKLY_CAP since=2026-11-03 until=2026-11-09 week=2 cap=2")

    def test_one_unmerged_draft_leaves_room(self):
        result = self.guard(lock_ready(), history=[], remote=[BRANCH_A], exists=lambda path: False)
        self.assertEqual((result.code, result.out), (None, []))

    def test_unmerged_drafts_only_in_the_remote_are_counted_once_each(self):
        history = [draft(-2)]
        result = self.guard(lock_ready(), history=history, remote=[branch(-2), branch(-4)], exists=lambda path: False)
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_WEEKLY_CAP since=2026-11-03 until=2026-11-09 week=2 cap=2")      # 이력 하나 + 이력에 없는 브랜치 하나
        result = self.guard(lock_ready(), history=history, remote=[branch(-2)], exists=lambda path: False)
        self.assertEqual((result.code, result.out), (None, []))                                    # 같은 글을 이력과 원격이 모두 가리킨다 — 한 건

    def test_old_unmerged_drafts_do_not_count_toward_the_week_but_do_toward_the_open_limit(self):
        old = [branch(-20), branch(-21), branch(-30)]
        stopped = self.guard(lock_ready(), history=[], remote=old, exists=lambda path: False)
        self.assertEqual(stopped.out[0], "[SKIP] code=OPEN_DRAFTS_CAP open=3 limit=3")
        two_old = self.guard(lock_ready(), history=[], remote=old[:2], exists=lambda path: False)
        self.assertEqual((two_old.code, two_old.out), (None, []))

    def test_the_open_drafts_cap_is_reported_first_when_both_are_reached(self):
        """같은 순간에 둘 다 걸리면 열린 초안 상한이 먼저다 — 주간 상한이 생기기 전에 이미 있던 결과는 바뀌지 않는다."""
        result = self.guard(lock_ready(), history=[], remote=[BRANCH_A, BRANCH_B, "ai/draft/2026-11-06-s9"], exists=lambda path: False)
        self.assertEqual(result.out[0], "[SKIP] code=OPEN_DRAFTS_CAP open=3 limit=3")
        self.assertEqual(self.cap_lines(result), [])

    def test_a_lower_open_limit_is_still_checked_before_the_weekly_cap(self):
        reg = lock_ready()
        set_limit(reg, CHANCE, max_open_drafts=1)
        result = self.guard(reg, history=[plain(-1)], remote=[branch(-2)], exists=lambda path: False)
        self.assertEqual(result.out[0], "[SKIP] code=OPEN_DRAFTS_CAP open=1 limit=1")

    def test_merged_drafts_still_count_toward_the_week_because_they_are_real_posts(self):
        history = [draft(-4, paths=["_posts/m/KR.md", "_posts/m/EN.md"]), draft(-2, paths=["_posts/n/KR.md", "_posts/n/EN.md"])]
        result = self.guard(lock_ready(), history=history, remote=[branch(-4), branch(-2)], exists=lambda path: True)
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_WEEKLY_CAP since=2026-11-03 until=2026-11-09 week=2 cap=2")
        merged_only = self.guard(lock_ready(), history=history[:1], remote=[branch(-4)], exists=lambda path: True)
        self.assertEqual((merged_only.code, merged_only.out), (None, []))

    def test_a_closed_draft_still_counts_until_it_leaves_the_window(self):
        """닫은 초안도 이력에 남아 창 안에서는 센다(GitHub API 를 부를 토큰이 없어 닫힘과 대기를 가를 수 없다 — 하루 상한과 같은 보수적 근사). 원격 브랜치가 이미 지워져도 이력으로 센다."""
        history = [draft(-3), draft(-5)]
        self.assertEqual(self.guard(lock_ready(), history=history, remote=[], exists=lambda path: False).code, 0)
        later = NOW + timedelta(days=2)                                                            # 5일 전이던 글이 7일 전이 되어 창을 떠난다
        self.assertEqual(self.guard(lock_ready(), history=history, remote=[], exists=lambda path: False, now=later).code, None)

    def test_a_branch_whose_history_entry_was_never_written_is_counted_from_its_name(self):
        """이력 push 와 롤백이 모두 실패한 드문 경우: 원격에는 초안 브랜치가 있는데 이력에는 없다 — 이름의 날짜로 센다."""
        result = self.guard(lock_ready(), history=[draft(-4)], remote=[branch(-4), "ai/draft/%s-m101500" % day(-1)], exists=lambda path: False)
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_WEEKLY_CAP since=2026-11-03 until=2026-11-09 week=2 cap=2")

    def test_foreign_branch_names_are_not_counted(self):
        result = self.guard(lock_ready(), history=[], remote=["ai/draft/odd", "ai/draft/2026-11-09-s99", "ai/draft/2026-13-40-s9"], exists=lambda path: False)
        self.assertEqual((result.code, result.out), (None, []))


class WeeklyOddDateTest(WeeklyGuardBase):
    """날짜를 믿을 수 없으면 읽을 수 있는 것만 세고 지나가지 않고 멈춘다(종료 1, 코드 LOCK_BLOCKED + reason). 사전이 아닌 항목(옛 형식 문자열·null)은 글 항목이 아니라 세지도 멈추지도 않는다."""

    UNREADABLE = [("날짜 없음", {"topic": "날짜 없음", "slot": 9}), ("null", {"date": None}), ("숫자", {"date": 20261109}), ("빈 글", {"date": ""}), ("글자", {"date": "어제"}),
                  ("한 자리 달", {"date": "2026-11-9"}), ("빗금", {"date": "2026/11/09"}), ("시각 포함", {"date": "2026-11-08 09:00"}), ("시각대 표기", {"date": "2026-11-08T09:00:00+09:00"}),
                  ("UTC 표기", {"date": "2026-11-08T00:00:00Z"}), ("앞 공백", {"date": " 2026-11-08"}), ("뒤 줄바꿈", {"date": "2026-11-08\n"}), ("달력에 없는 날", {"date": "2026-02-30"}),
                  ("전각 숫자", {"date": "２０２６-１１-０８"}), ("참", {"date": True}), ("목록", {"date": ["2026-11-08"]})]

    def test_each_unreadable_date_stops_the_run_with_a_clear_reason(self):
        for label, item in self.UNREADABLE:
            with self.subTest(case=label):
                result = self.guard(lock_ready(), history=[item], remote=[])
                self.assertEqual(result.code, 1)
                self.assertEqual(result.out[0], "[SKIP] code=LOCK_BLOCKED reason=HISTORY_DATE_UNREADABLE")
                self.assertIn("::error::" + publish_lock.WEEKLY_DATE_ERROR, result.out)
                self.assertIn("**LOCK_BLOCKED**", result.summary[0])
                self.assertIn("1개", "\n".join(result.out))
                self.assertEqual(self.cap_lines(result), [])

    def test_an_unreadable_entry_stops_even_when_the_readable_ones_say_there_is_room(self):
        history = [plain(-1), {"date": "나중에"}]
        result = self.guard(lock_ready(), history=history, remote=[])
        self.assertEqual(result.code, 1)                                                           # '읽을 수 있는 것만 세면 1 < 2 라 통과'가 아니다
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_BLOCKED reason=HISTORY_DATE_UNREADABLE")

    def test_an_unreadable_entry_stops_even_when_it_is_old_because_nobody_can_tell(self):
        result = self.guard(lock_ready(), history=[plain(-300), {"date": "2025-1-1"}], remote=[])
        self.assertEqual(result.code, 1)

    def test_a_future_date_stops_the_run(self):
        for offset in (1, 2, 40, 3000):
            result = self.guard(lock_ready(), history=[plain(offset)], remote=[])
            self.assertEqual(result.code, 1, offset)
            self.assertEqual(result.out[0], "[SKIP] code=LOCK_BLOCKED reason=HISTORY_DATE_FUTURE", offset)
            self.assertIn("2026-11-09", "\n".join(result.out))                                    # 오늘 날짜를 알려 준다

    def test_a_remote_only_branch_dated_after_today_stops_the_run(self):
        result = self.guard(lock_ready(), history=[], remote=[branch(3)], exists=lambda path: False)
        self.assertEqual(result.code, 1)
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_BLOCKED reason=DRAFT_BRANCH_DATE_FUTURE")
        linked = self.guard(lock_ready(), history=[draft(-1)], remote=[branch(-1)], exists=lambda path: False)
        self.assertEqual(linked.code, None)

    def test_several_problems_are_all_listed_and_the_first_reason_is_the_headline(self):
        result = self.guard(lock_ready(), history=[{"topic": "x"}, plain(2)], remote=[branch(5)])
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_BLOCKED reason=HISTORY_DATE_UNREADABLE")
        errors = [line for line in result.out if line.startswith("[잠금 오류] ")]
        self.assertEqual(len(errors), 3)
        self.assertEqual(len(result.summary[0].splitlines()), 4)                                  # 제목 + 결과 + 나머지 둘

    def test_non_dict_entries_never_stop_the_run(self):
        history = ["국가직 전환 5년 차의 그늘", None, 3, 4.5, True, [], [plain(-1)], plain(-1)]
        result = self.guard(lock_ready(), history=history, remote=[])
        self.assertEqual((result.code, result.out), (None, []))

    def test_a_stop_is_red_and_a_cap_skip_is_green(self):
        stopped = self.guard(lock_ready(), history=[{"date": "bad"}], remote=[])
        skipped = self.guard(lock_ready(), history=[plain(-1), plain(-2)], remote=[])
        self.assertEqual((stopped.code, skipped.code), (1, 0))

    def test_the_error_annotation_is_a_fixed_sentence(self):
        for item in ({"date": "x\n::error::가짜\n##[group]"}, plain(4)):
            result = self.guard(lock_ready(), history=[item], remote=[])
            annotations = [line for line in result.out if line.startswith("::error::")]
            self.assertEqual(annotations, ["::error::" + publish_lock.WEEKLY_DATE_ERROR])
            self.assertNotIn("가짜", result.text)
            self.assertNotIn("##[", result.text)

    def test_the_output_stays_small_for_thousands_of_bad_entries(self):
        history = [{"date": "bad-%d" % number} for number in range(5000)] + [plain(3)] * 5000
        result = self.guard(lock_ready(), history=history, remote=[])
        self.assertEqual(result.code, 1)
        self.assertLess(len(result.text), 1500)                                                    # 항목마다 한 줄을 내지 않는다 — 개수만
        self.assertIn("5000개", result.text)

    def test_nothing_is_reported_when_the_lock_is_off(self):
        reg = with_lock_off(lock_ready())
        result = self.guard(reg, history=[{"date": "bad"}, plain(4)], remote=[], exists=lambda path: False)
        self.assertEqual((result.code, result.out), (None, []))                                    # 꺼짐 = 이전과 같다

    def test_a_random_mix_never_raises_and_ends_in_a_known_way(self):
        rng = random.Random(7)
        pool = [None, 0, 1, -1, 2.5, True, "", "x", "2026-11-09", "2026-11-03", "2026-11-02", "2026-11-10", "2026-02-30", "2026-11-9", day(-2), day(5), [], {}, ["2026-11-09"], {"d": 1}]
        names_pool = [None, "", "x", "ai/draft/odd", branch(-1), branch(-9), branch(4), "ai/draft/%s-m101010" % day(-3)]
        for _ in range(200):
            history = []
            for _item in range(rng.randint(0, 8)):
                kind = rng.choice(("dict", "raw", "plain"))
                if kind == "dict":
                    history.append({"date": rng.choice(pool), "slot": rng.choice((None, 9, 18)), "flow": rng.choice((None, "pr")), "branch": rng.choice(names_pool)})
                elif kind == "raw":
                    history.append(rng.choice(pool))
                else:
                    history.append(plain(rng.randint(-10, 3)))
            names = [name for name in (rng.choice(names_pool) for _n in range(rng.randint(0, 4))) if isinstance(name, str)]
            result = self.guard(lock_ready(), history=history, remote=names, exists=lambda path: False)
            self.assertIn(result.code, (None, 0, 1), (history, names))


class GeneratorWeeklyCapTest(PlainDirBase):
    """generator.main 을 가드까지 거쳐 하루하루 따라간다(실제 이력 파일·가짜 소스·가짜 Gemini): 이틀 연속 글을 만들고 사흘째는 건너뛰며, 첫 글이 창을 떠나는 날(7일 뒤) 다시 만든다."""

    TITLES = ("해양 관측 위성 자료 공개", "캐나다 소비자물가지수 발표", "신형 반도체 공장 착공 소식", "극지 연구선 관측 결과 발표", "도시 철도 신규 노선 개통 일정")

    def setUp(self):
        super().setUp()
        self.reg_path = write_registry(self.root, lock_ready())
        self.made = 0

    def tick(self, now, event="schedule", reg=None, dry=False, remote=None, flow="pr", **extra):
        path = write_registry(self.root, reg, "tick-blogs.json") if reg is not None else self.reg_path
        with mock.patch.object(registry, "REGISTRY_PATH", path), mock.patch.object(draft_flow, "ls_remote_drafts", return_value=remote or {}):
            return run_tick(self.clone, now, flow=flow, event=event, dry=dry, git_env={"EVENT_NAME": event}, guarded=True, **extra)

    def make(self, now, **kwargs):
        """글을 만드는 틱 하나: 글감을 틱마다 다르게 주고(같은 글감은 중복으로 탈락한다), 끝나면 글 파일을 작업 트리에서 치운다(draft_flow.deliver 가 초안 브랜치로 옮긴 뒤의 main)."""
        title = self.TITLES[self.made]
        self.made += 1
        result = self.tick(now, feed=[candidate(title, "https://www.reuters.com/story-%d" % self.made)], **kwargs)
        for rel in self.posts():
            (self.clone / rel).unlink()
        return result

    def test_two_drafts_a_week_and_the_third_waits_until_the_first_one_leaves_the_window(self):
        first = self.make(at(9, 20, day=28))
        self.assertIsNone(first.value)
        self.assertEqual([item["branch"] for item in first.history], ["ai/draft/2026-10-28-s9"])
        remote = {"ai/draft/2026-10-28-s9": "a" * 40}
        second = self.make(at(9, 20, day=29), remote=remote)
        self.assertIsNone(second.value)                                                           # 한 주 안의 둘째 글은 만든다
        self.assertEqual([item["branch"] for item in second.history], ["ai/draft/2026-10-28-s9", "ai/draft/2026-10-29-s9"])
        remote["ai/draft/2026-10-29-s9"] = "b" * 40
        for now, since, until in ((at(9, 20, day=30), "2026-10-24", "2026-10-30"), (at(18, 20, day=30), "2026-10-24", "2026-10-30"),
                                  (datetime(2026, 11, 3, 9, 20, tzinfo=KST), "2026-10-28", "2026-11-03")):          # 마지막은 첫 글로부터 6일째 — 아직 창 안이다
            skipped = self.tick(now, remote=remote)
            self.assertIsInstance(skipped.value, SystemExit, now)
            self.assertEqual(skipped.value.code, 0)
            self.assertIn("[SKIP] code=LOCK_WEEKLY_CAP since=%s until=%s week=2 cap=2" % (since, until), skipped.out)        # 이력과 원격이 같은 두 글을 가리킨다 — 넷이 아니라 둘
            self.assertEqual((skipped.prompts, len(skipped.history), self.posts()), ([], 2, []))     # 모델을 부르지 않았고 새 글·이력이 없다
            self.assertIn("**LOCK_WEEKLY_CAP**", skipped.summary)
            self.assertNotIn("::error::", skipped.out)                                              # 정상 건너뜀이다 — 빨강이 아니다
        third = self.make(datetime(2026, 11, 4, 9, 20, tzinfo=KST), remote=remote)
        self.assertIsNone(third.value)                                                            # 첫 글로부터 7일째: 10-28 글이 창(10-29부터)을 떠나 한 편이 남는다
        self.assertEqual([item["date"] for item in third.history], ["2026-10-28", "2026-10-29", "2026-11-04"])

    def test_a_manual_real_run_obeys_the_weekly_cap_too(self):
        self.make(at(11, 5, day=28), event="workflow_dispatch")
        self.make(at(11, 5, day=29), event="workflow_dispatch", remote={"ai/draft/2026-10-28-m110500": "a" * 40})
        blocked = self.tick(at(15, 0, day=30), event="workflow_dispatch", remote={"ai/draft/2026-10-28-m110500": "a" * 40, "ai/draft/2026-10-29-m110500": "b" * 40})
        self.assertEqual(blocked.value.code, 0)
        self.assertIn("::notice::제한 재개 잠금: 최근 7일 안에 이미 주간 상한만큼 글이 만들어져 이번 수동 실행은 글을 만들지 않았습니다(정상 건너뜀).", blocked.out)
        self.assertEqual((blocked.prompts, len(blocked.history)), ([], 2))

    def test_with_the_lock_off_the_weekly_cap_is_not_counted_and_the_third_day_makes_a_draft(self):
        off = with_lock_off(lock_ready())
        for number in range(3):
            result = self.make(at(9, 20, day=28 + number), reg=off)
            self.assertIsNone(result.value, number)
        self.assertEqual(len(result.history), 3)                                                    # 꺼져 있으면 이전과 같다

    def test_a_practice_run_is_not_counted_and_not_blocked(self):
        self.make(at(9, 20, day=28))
        self.make(at(9, 20, day=29))
        practice = self.tick(at(15, 0, day=30), event="workflow_dispatch", dry=True, feed=[candidate("연습 기사 제목입니다", "https://www.reuters.com/practice")])
        self.assertIsNone(practice.value)
        self.assertEqual(len(practice.history), 2)                                                  # 연습은 저장하지 않는다

    def test_a_history_entry_with_a_broken_date_stops_the_real_run_and_makes_nothing(self):
        self.make(at(9, 20, day=28))
        history = json.loads((self.clone / "history.json").read_text(encoding="utf-8"))
        history.append({"date": "어제", "topic": "손으로 고친 항목"})
        self.set_history(history)
        stopped = self.tick(at(9, 20, day=29))
        self.assertEqual(stopped.value.code, 1)
        self.assertIn("[SKIP] code=LOCK_BLOCKED reason=HISTORY_DATE_UNREADABLE", stopped.out)
        self.assertEqual((stopped.prompts, self.posts()), ([], []))


class WeeklySimulationTest(lt.GuardBase):
    """두 달 치 하루하루를 실제 가드(guard_start)로 흉내 낸다: 가드가 통과한 실행만 글(이력 항목)을 만든다고 놓고 어느 날 글이 나오는지 센다.
    굴러가는 7일의 상한이 정확히 지켜지고(어느 7일에도 상한을 넘지 않는다) 놀지도 않는다(상한 밑이면 그날 첫 실행이 만든다)는 두 가지를 확인한다."""

    START = date(2026, 12, 1)

    def run_days(self, cap, days, runs_of):
        """days 일 동안 하루의 실행 시각(runs_of(day_index) 가 돌려주는 (시, 분, 이벤트 이름) 목록)마다 가드를 불러 글이 나온 날 번호의 목록과 이력을 돌려준다."""
        reg = lock_ready()
        set_limit(reg, CHANCE, max_posts_per_week=cap)
        path = self.folder / "history.json"
        history, post_days = [], []
        for index in range(days):
            today = self.START + timedelta(days=index)
            for hour, minute, event in runs_of(index):
                path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
                now = datetime(today.year, today.month, today.day, hour, minute, tzinfo=KST)
                try:
                    publish_lock.guard_start({"EVENT_NAME": event}, path, lambda: now, False, False, [].append, out=[].append, load=lambda: reg,
                                             remote_drafts=lambda: [], exists=lambda candidate: False)
                except SystemExit as stop:
                    self.assertEqual(stop.code, 0, (index, hour, event))          # 건너뜀(초록)뿐이다 — 이 흐름에서 멈춤(종료 1)은 없다
                    continue
                history.append(lt.entry(date=today.isoformat(), slot=hour if event == "schedule" else None, branch="ai/draft/%s-%s" % (
                    today.isoformat(), ("s%d" % hour) if event == "schedule" else ("m%02d%02d00" % (hour, minute)))))
                post_days.append(index)
        return post_days, history

    def posts_in_every_window(self, post_days, days):
        return max(sum(1 for item in post_days if start <= item < start + publish_lock.WEEK_WINDOW_DAYS) for start in range(days))

    def test_two_a_week_makes_posts_on_days_0_1_7_8_14_15_and_so_on(self):
        post_days, _history = self.run_days(2, 63, lambda index: [(9, 20, "schedule"), (18, 20, "schedule")])
        self.assertEqual(post_days, [day_number for week in range(9) for day_number in (week * 7, week * 7 + 1)])
        self.assertEqual(self.posts_in_every_window(post_days, 63), 2)

    def test_one_a_week_makes_a_post_every_seventh_day(self):
        post_days, _history = self.run_days(1, 63, lambda index: [(9, 20, "schedule"), (18, 20, "schedule")])
        self.assertEqual(post_days, list(range(0, 63, 7)))
        self.assertEqual(self.posts_in_every_window(post_days, 63), 1)

    def test_extra_manual_and_hourly_runs_change_neither_the_days_nor_the_cap(self):
        """같은 날 여러 번 도는 정기·수동 실행(아침 수동·낮 수동·한 시간마다 도는 정기)은 하루 상한과 주간 상한에 막혀 글이 나오는 날을 바꾸지 못한다."""
        busy = lambda index: [(8, 5, "workflow_dispatch"), (9, 20, "schedule"), (10, 20, "schedule"), (13, 40, "workflow_dispatch"), (18, 20, "schedule"), (23, 50, "schedule")]
        for cap, expected in ((2, [number for week in range(9) for number in (week * 7, week * 7 + 1)]), (1, list(range(0, 63, 7)))):
            post_days, history = self.run_days(cap, 63, busy)
            self.assertEqual(post_days, expected, cap)
            self.assertEqual(self.posts_in_every_window(post_days, 63), cap)
            self.assertTrue(all(item["slot"] is None for item in history[:1]))          # 첫 글은 그날 아침 수동 실행이 만들었다(슬롯 없음) — 이름에 시각이 붙는다
            self.assertTrue(all(item["branch"].startswith("ai/draft/") for item in history))

    def test_a_gap_in_the_runs_lets_the_next_window_start_clean(self):
        """한 주 내내 아무 실행이 없었어도(점검·정지) 창은 날짜로만 굴러가므로 오래된 글은 저절로 빠진다."""
        post_days, _history = self.run_days(2, 40, lambda index: [(9, 20, "schedule")] if index in (0, 1, 30, 31, 32, 33) else [])
        self.assertEqual(post_days, [0, 1, 30, 31])                                    # 30·31 에 둘, 32·33 은 상한

    def test_every_seven_day_window_holds_at_most_the_cap_whatever_the_run_pattern(self):
        rng = random.Random(1109)
        for cap in (1, 2):
            pattern = {index: [(rng.choice((8, 9, 13, 18, 22)), rng.choice((0, 20, 45)), rng.choice(("schedule", "workflow_dispatch"))) for _run in range(rng.randint(0, 3))] for index in range(70)}
            for runs in pattern.values():
                runs.sort()
            post_days, _history = self.run_days(cap, 70, lambda index: pattern[index])
            self.assertLessEqual(self.posts_in_every_window(post_days, 70), cap, (cap, post_days))
            # 놀지 않는다: 그날 실행이 있었고 창 안의 글이 상한 밑이었다면 그날 글이 나왔다
            for index in range(70):
                if pattern[index]:
                    before = sum(1 for item in post_days if index - 6 <= item < index)
                    self.assertEqual(index in post_days, before < cap, (cap, index, post_days))


class WeeklyCommandLineTest(unittest.TestCase):
    """L8 은 켜진 잠금의 규칙이라 레지스트리를 읽는 모든 입구가 같은 말을 한다: `publish_lock check`·`registry`·`plan`·`drafts.chance_flow`(워크플로 '발행 흐름 확인' 단계)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def run_cli(self, module_main, argv, reg):
        target = write_registry(self.folder, reg)
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(registry, "REGISTRY_PATH", target), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = module_main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def run_plan(self, reg):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(plan, "load_registry", return_value=reg), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            return plan.main(["--platform", "blogger"]), stdout.getvalue(), stderr.getvalue()

    def broken(self):
        yield "값이 없음", mutated(lambda r: drop_limit(r, CHANCE, "max_posts_per_week"))
        for bad in (0, 3, 14, True, "2", 1.5, None):
            yield "값 %r" % (bad,), mutated(lambda r, bad=bad: set_limit(r, CHANCE, max_posts_per_week=bad))

    def test_check_says_on_for_a_ready_registry_and_names_l8_for_a_broken_one(self):
        code, out, _ = self.run_cli(publish_lock.main, ["check"], lock_ready())
        self.assertEqual((code, out.strip()), (0, "제한 재개 잠금: 켜짐"))
        for label, reg in self.broken():
            with self.subTest(label):
                code, out, _ = self.run_cli(publish_lock.main, ["check"], reg)
                self.assertEqual(code, 1)
                self.assertIn("[잠금 오류] 제한 재개 잠금 L8", out)

    def test_check_with_the_lock_off_ignores_the_weekly_value(self):
        for _label, reg in self.broken():
            code, out, _ = self.run_cli(publish_lock.main, ["check"], with_lock_off(reg))
            self.assertEqual((code, out.strip()), (0, "제한 재개 잠금: 꺼짐(규칙을 적용하지 않습니다)"))

    def test_the_registry_command_and_plan_reject_a_broken_weekly_value(self):
        code, out, _ = self.run_cli(registry.main, [], lock_ready())
        self.assertEqual(code, 0)
        self.assertIn("레지스트리 검증 통과", out)
        for label, reg in self.broken():
            with self.subTest(label):
                code, out, _ = self.run_cli(registry.main, [], reg)
                self.assertEqual(code, 1)
                self.assertIn("max_posts_per_week", out)
                code, out, err = self.run_plan(reg)
                self.assertEqual((code, out), (1, ""))                                           # 글 생성 잡이 시작되지 않는다

    def test_the_registry_command_rejects_an_out_of_range_value_even_with_the_lock_off(self):
        for bad in (0, 15, True, "2"):
            reg = today_registry()
            set_limit(reg, CHANCE, max_posts_per_week=bad)
            code, out, _ = self.run_cli(registry.main, [], reg)
            self.assertEqual(code, 1, bad)
            self.assertIn("max_posts_per_week", out)

    def test_the_publish_flow_step_stops_for_a_broken_weekly_value_and_answers_for_a_ready_one(self):
        self.assertEqual(drafts.chance_flow(write_registry(self.folder, lock_ready())), "pr")
        for label, reg in self.broken():
            with self.subTest(label), self.assertRaises(drafts.DraftFlowError) as caught:
                drafts.chance_flow(write_registry(self.folder, reg))
            self.assertIn("L8", str(caught.exception))
        self.assertEqual(drafts.chance_flow(write_registry(self.folder, today_registry())), "direct")      # 꺼짐 = 이전과 같다


class WeeklyBloggerRunnerTest(lt.RunBase):
    """L8 은 레지스트리 전체의 규칙이라(켜진 잠금에서 규칙 하나라도 어기면 아무것도 만들지 않는다) Blogger 러너도 멈춘다."""

    def write_locked(self, mutate=None):
        path = self.root / "pipeline" / "blogs.json"
        reg = lock_ready(json.loads(path.read_text(encoding="utf-8")))
        blog_of(reg, MACAT)["mode"] = "draft"
        if mutate:
            mutate(reg)
        path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")

    def test_a_locked_registry_without_the_weekly_value_stops_the_blogger_runner_before_any_call(self):
        self.write_locked(lambda reg: drop_limit(reg, CHANCE, "max_posts_per_week"))
        publisher = lt.FakePublisher()
        code, text = self.go(env=lt.FULL_ENV, publisher=publisher)
        self.assertEqual(code, 2)
        self.assertEqual((publisher.published, publisher.health_calls), ([], 0))
        self.assertEqual((self.history(), self.drafts()), ([], []))
        self.assertIn("제한 재개 잠금 L8", text)

    def test_with_the_weekly_value_the_blogger_draft_upload_works_as_before(self):
        self.write_locked()
        publisher = lt.FakePublisher()
        code, text = self.go(env=lt.FULL_ENV, publisher=publisher)
        self.assertEqual(code, 0, text)
        self.assertEqual([item["draft"] for item in publisher.published], [True])                 # 초안함 업로드만 — 주간 상한은 Chance 만 센다


class WeeklyKeyInvariantTest(unittest.TestCase):
    """K1·K2 는 이 일로 바뀌지 않는다: max_posts_per_week 는 최상위 키가 아니라 limits 안의 값이다."""

    def test_the_known_top_level_keys_are_unchanged(self):
        self.assertEqual(publish_lock.KNOWN_TOP_LEVEL_KEYS[:6], ("_doc", "schema_version", "shared_secrets", "defaults", "blogs", "resume_lock"))     # 이 묶음이 키를 더하지 않았다(뒤에 다른 묶음이 더해도 깨지지 않는다)
        self.assertNotIn("max_posts_per_week", publish_lock.KNOWN_TOP_LEVEL_KEYS)
        self.assertEqual([rule for rule, _text in publish_lock.KEY_RULES][:2], ["K1", "K2"])

    def test_the_weekly_value_in_limits_trips_neither_k1_nor_k2_with_the_lock_on_or_off(self):
        for reg in (lock_ready(), with_lock_off(lock_ready()), today_registry()):
            put_in(reg, ("chance", "limits"), key="max_posts_per_week", value=2)
            put_in(reg, ("defaults", "limits"), key="max_posts_per_week", value=2)
            self.assertEqual(publish_lock.lock_key_problems(reg), [])
            self.assertEqual(registry.validate_registry(reg), [])

    def test_the_name_is_nowhere_near_resume_lock_so_it_is_never_taken_for_a_typo(self):
        for name in ("max_posts_per_week", "max_posts_per_day", "max_open_drafts"):
            self.assertFalse(publish_lock._looks_like_lock_key(name), name)

    def test_putting_the_weekly_value_at_the_top_level_is_an_unknown_key_for_the_validator_only(self):
        reg = lock_ready()
        reg["max_posts_per_week"] = 2
        errors = registry.validate_registry(reg)
        self.assertTrue(any("알 수 없는 최상위 키" in message and "max_posts_per_week" in message for message in errors), errors)
        self.assertEqual(publish_lock.lock_key_problems(reg), [])                              # 실행 시 멈추는 '잠금 키 문제'가 아니다(오타로 보이지 않는다)

    def test_the_guard_ignores_a_top_level_weekly_value_because_only_the_chance_limits_are_read(self):
        reg = lock_ready()
        drop_limit(reg, CHANCE, "max_posts_per_week")
        reg["max_posts_per_week"] = 2
        self.assertEqual(rules_in(publish_lock.lock_errors(reg)), {"L8"})                      # 잘못된 자리의 값은 없는 것과 같다 — L8 이 막는다
        self.assertIsNone(publish_lock.weekly_posts_limit(reg))


if __name__ == "__main__":
    unittest.main()
