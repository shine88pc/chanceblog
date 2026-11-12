"""후보 순서와 기간 중복 방지 키 시험(S2a): 키 모양·ISO 주 경계·대기 규칙·이미 낸 글 제외·순서가 주 안에서 변하지 않음·글감마다 실제 글이 나옴(어댑터→틀 끝까지, 오프라인)·순수 함수(오늘은 인자).
네트워크·시계 없이 돈다."""
import datetime
import random
import re
import unittest

import _bootstrap  # noqa: F401
import space_helpers as H
import test_space_recipes as TR

from pipeline import fact_assembler as A
from pipeline import fact_candidates as K
from pipeline import facts as F
from pipeline import recipes as R
from pipeline import recipes_noregion as RN
from pipeline.adapters import noaa_swpc as N

SPEC = {spec.spec_id: spec for spec in K.SPECS}


class KeyTest(unittest.TestCase):
    def test_the_key_is_the_subject_and_the_period_of_the_day_the_post_is_made(self):
        self.assertEqual(K.candidate_key(SPEC["kp_weekly"], "2026-11-10"), "space_weather.kp_weekly:2026-W46")
        self.assertEqual(K.candidate_key(SPEC["sunspot_monthly_monthly"], "2026-11-10"), "space_weather.sunspot_monthly_monthly:2026-11")
        for spec in K.SPECS:
            key = K.candidate_key(spec, "2026-11-10")
            self.assertRegex(key, r"\Aspace_weather\.[a-z_]+:\d{4}-(?:W\d{2}|\d{2})\Z")
            self.assertEqual(key.split(":")[0], K.KEY_PREFIX + spec.spec_id)

    def test_every_day_of_a_week_gets_the_same_key_and_the_next_week_a_new_one(self):
        monday = datetime.date(2026, 11, 9)
        keys = {K.candidate_key(SPEC["kp_weekly"], monday + datetime.timedelta(days=offset)) for offset in range(7)}
        self.assertEqual(keys, {"space_weather.kp_weekly:2026-W46"})
        self.assertEqual(K.candidate_key(SPEC["kp_weekly"], monday + datetime.timedelta(days=7)), "space_weather.kp_weekly:2026-W47")
        month = {K.candidate_key(SPEC["sunspot_daily_monthly"], datetime.date(2026, 11, day)) for day in range(1, 31)}
        self.assertEqual(month, {"space_weather.sunspot_daily_monthly:2026-11"})

    def test_iso_week_boundaries_use_the_iso_year(self):
        spec = SPEC["kp_weekly"]
        for day, expected in (("2026-01-01", "2026-W01"), ("2025-12-29", "2026-W01"), ("2025-12-28", "2025-W52"), ("2026-12-31", "2026-W53"), ("2027-01-01", "2026-W53"),
                              ("2027-01-03", "2026-W53"), ("2027-01-04", "2027-W01"), ("2024-12-30", "2025-W01"), ("2026-02-28", "2026-W09")):
            with self.subTest(day=day):
                self.assertEqual(K.candidate_key(spec, day), f"space_weather.kp_weekly:{expected}")
                self.assertEqual(K.period_id(spec, day), expected)

    def test_the_input_may_be_a_date_a_datetime_or_text_and_bad_text_is_an_error(self):
        spec = SPEC["kp_weekly"]
        base = K.candidate_key(spec, "2026-11-10")
        self.assertEqual(K.candidate_key(spec, datetime.date(2026, 11, 10)), base)
        self.assertEqual(K.candidate_key(spec, datetime.datetime(2026, 11, 10, 23, 59)), base)
        for bad in ("2026-13-01", "어제", "", None, 20261110, "2026-11"):
            with self.assertRaises(F.FactFormatError):
                K.candidate_key(spec, bad)

    def test_week_start_is_the_monday(self):
        self.assertEqual(K.week_start("2026-11-10"), datetime.date(2026, 11, 9))
        self.assertEqual(K.week_start("2026-11-09"), datetime.date(2026, 11, 9))
        self.assertEqual(K.week_start("2026-11-15"), datetime.date(2026, 11, 9))


class PlanTest(unittest.TestCase):
    def ids(self, today, done=()):
        return [candidate.spec.spec_id for candidate in K.plan_candidates(today, done)]

    def test_a_subject_waits_for_its_day_in_the_period(self):
        weekly, monthly = {"kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly"}, {"sunspot_daily_monthly", "sunspot_monthly_monthly"}
        by_day = {day: set(self.ids(f"2026-11-{day:02d}")) & weekly for day in range(9, 16)}                          # 11월 9일(월)–15일(일)
        self.assertEqual(by_day[9], {"kp_weekly"})
        self.assertEqual(by_day[10], {"kp_weekly"})                                                                    # S2AFIX D4: 같은 Kp 를 읽는 kp_storm_weekly 는 이 주(짝수 주)의 대표가 아니다
        self.assertEqual(by_day[11], {"kp_weekly", "flares_weekly"})
        self.assertEqual(by_day[12], weekly - {"kp_storm_weekly"})
        self.assertEqual(by_day[15], weekly - {"kp_storm_weekly"})
        by_next = {day: set(self.ids(f"2026-11-{day:02d}")) & weekly for day in range(16, 23)}                        # 다음 주(홀수 주): 대표가 바뀐다
        self.assertEqual(by_next[16], set())                                                                           # 월요일에는 kp_storm_weekly 가 아직 대기 전이고 kp_weekly 는 대표가 아니다
        self.assertEqual(by_next[17], {"kp_storm_weekly"})
        self.assertEqual(by_next[19], weekly - {"kp_weekly"})
        self.assertEqual(set(self.ids("2026-11-02")) & monthly, set())
        self.assertEqual(set(self.ids("2026-11-03")) & monthly, {"sunspot_daily_monthly"})
        self.assertEqual(set(self.ids("2026-11-07")) & monthly, {"sunspot_daily_monthly"})
        self.assertEqual(set(self.ids("2026-11-08")) & monthly, monthly)
        self.assertEqual(set(self.ids("2026-11-30")) & monthly, monthly)

    def test_what_was_already_made_in_the_period_is_left_out(self):
        today = "2026-11-12"
        everything = self.ids(today)
        self.assertEqual(len(everything), 5)                                                                           # 여섯 글감 가운데 같은 Kp 를 읽는 둘은 이 주에 하나만 나온다
        for spec in K.SPECS:
            key = K.candidate_key(spec, today)
            left = self.ids(today, done=[key])
            with self.subTest(done=spec.spec_id):
                if spec.spec_id == "kp_storm_weekly":                                                                  # 대표가 아닌 글감을 이미 냈어도(손으로 낸 글) 같은 제품의 묶음은 이 주에 막힌다
                    self.assertEqual(left, [item for item in everything if item != "kp_weekly"])
                else:
                    self.assertEqual(left, [item for item in everything if item != spec.spec_id])
        self.assertEqual(self.ids(today, done={K.candidate_key(spec, today) for spec in K.SPECS}), [])
        self.assertEqual(self.ids(today, done=["space_weather.kp_weekly:2026-W45"]), everything)                       # 지난주 키는 이번 주를 막지 않는다
        self.assertEqual(self.ids(today, done=iter([K.candidate_key(SPEC["kp_weekly"], today)])), [item for item in everything if item != "kp_weekly"])

    def test_the_order_rotates_with_the_iso_week_and_does_not_change_within_a_week(self):
        week = [f"2026-11-{day:02d}" for day in range(12, 16)]                                                         # 목–일: 같은 주, 여섯 글감이 모두 대기
        orders = [self.ids(day) for day in week]
        self.assertEqual(len({tuple(order) for order in orders}), 1)
        base = orders[0]
        for spec in K.SPECS:                                                                                           # 이미 낸 글감을 빼도 남은 글감의 상대 순서는 같다(같은 제품의 묶음은 함께 빠진다)
            done = [K.candidate_key(spec, week[0])]
            gone = {member.spec_id for member in K.GROUP_OF[spec.spec_id]}
            self.assertEqual(self.ids(week[0], done), [item for item in base if item not in gone])
        firsts = {self.ids(day)[0] for day in ("2026-11-12", "2026-11-19", "2026-11-26", "2026-12-03", "2026-12-10", "2026-12-17")}
        self.assertEqual(len(firsts), 6)                                                                               # 여섯 주 동안 맨 앞 글감이 모두 한 번씩 돌아온다
        self.assertEqual(sorted(base), sorted(set(K.SPEC_IDS) - {"kp_storm_weekly"}))                                  # 이 주(짝수 주)는 kp_storm_weekly 가 빠진 다섯 글감

    def test_the_result_is_a_pure_function_of_its_inputs(self):
        for day in ("2026-01-01", "2026-06-15", "2026-11-12", "2027-01-01"):
            first = K.plan_candidates(day, ())
            self.assertEqual(first, K.plan_candidates(day, ()))
            self.assertEqual(first, K.plan_candidates(datetime.date.fromisoformat(day), []))
        self.assertIsInstance(K.SPECS, tuple)
        before = tuple(K.SPECS)
        K.plan_candidates("2026-11-12", ("a",))
        self.assertEqual(tuple(K.SPECS), before)
        self.assertIsNone(K.next_candidate("2026-11-12", {K.candidate_key(spec, "2026-11-12") for spec in K.SPECS}))
        self.assertEqual(K.next_candidate("2026-11-12").spec.spec_id, self.ids("2026-11-12")[0])

    def test_candidates_carry_what_the_generator_needs(self):
        for candidate in K.plan_candidates("2026-11-12"):
            with self.subTest(spec=candidate.spec.spec_id):
                self.assertEqual(candidate.candidate_key, K.candidate_key(candidate.spec, "2026-11-12"))
                self.assertEqual(dict(candidate.params), {"key": candidate.spec.key})
                self.assertEqual(candidate.products, candidate.spec.products)
                self.assertEqual(candidate.recipe_id, candidate.spec.recipe_id)
                self.assertIs(K.get_recipe(candidate.recipe_id), K.RECIPES_BY_ID[candidate.recipe_id])

    def test_no_day_of_the_year_has_a_key_collision_between_subjects(self):
        day = datetime.date(2026, 1, 1)
        while day.year == 2026:
            keys = [K.candidate_key(spec, day) for spec in K.SPECS]
            self.assertEqual(len(set(keys)), len(keys))
            day += datetime.timedelta(days=13)


class ConflictTest(unittest.TestCase):
    """S2AFIX D4: 같은 제품을 읽는 글감은 한 기간에 하나만 — 같은 주의 같은 Kp 자료로 두 글(R04 일별 최대값·R05 기준 이상 날 수)이 나오지 않는다. 같은 7일 자료로 만든 두 글은 표의 (날짜, 값) 이
    모두 같고 문장의 숫자가 72% 겹친다(검증 보고서)."""

    def ids(self, today, done=()):
        return [candidate.spec.spec_id for candidate in K.plan_candidates(today, done)]

    def test_the_groups_come_from_the_products_each_subject_reads(self):
        names = [tuple(spec.spec_id for spec in group) for group in K.GROUPS]
        self.assertEqual(names, [("kp_weekly", "kp_storm_weekly"), ("flares_weekly",), ("scales_weekly",), ("sunspot_daily_monthly",), ("sunspot_monthly_monthly",)])
        self.assertEqual(sorted(spec.spec_id for group in K.GROUPS for spec in group), sorted(K.SPEC_IDS))                     # 모든 글감이 한 묶음에만 있다
        for group in K.GROUPS:
            for spec in group:
                self.assertIs(K.GROUP_OF[spec.spec_id], group)
        for index, group in enumerate(K.GROUPS):                                                                                 # 다른 묶음의 글감은 같은 기간 종류에서 제품을 겹쳐 읽지 않는다
            for other in K.GROUPS[index + 1:]:
                for first in group:
                    for second in other:
                        if first.period == second.period:
                            self.assertFalse(set(first.products) & set(second.products), (first.spec_id, second.spec_id))

    def test_the_rule_is_computed_from_products_and_period_kind_not_from_names(self):
        def spec(name, period, products, order):
            return K.CandidateSpec(name, "R04_NOREGION_SERIES", RN.KEY_KP, tuple(products), period, 1, order)
        week, month = K.PERIOD_WEEK, K.PERIOD_MONTH
        specs = (spec("a", week, ("p",), 0), spec("b", week, ("p", "q"), 1), spec("c", week, ("q",), 2), spec("d", month, ("p",), 3), spec("e", week, ("z",), 4), spec("f", week, ("z",), 5))
        groups = K.conflict_groups(specs)
        self.assertEqual([tuple(item.spec_id for item in group) for group in groups], [("a", "b", "c"), ("d",), ("e", "f")])    # a–b(p)·b–c(q) 가 이어져 한 묶음, 달 글감은 따로
        self.assertEqual(K.conflict_groups(tuple(reversed(specs))), groups)                                                      # 입력 순서와 상관없다
        self.assertEqual(K.conflict_groups(()), ())

    def test_a_late_subject_that_joins_two_separate_groups_keeps_the_subject_order_inside_the_merged_group(self):
        """S2AFIX2 N4: 묶음 안 순서는 대표를 돌릴 때의 색인이다. 떨어져 있던 두 묶음(a·b)을 늦은 글감 c(p, q)가 한꺼번에 이으면 합치는 차례가 b, a, c 가 되므로 정렬을 지우면 묶음 안 순서가 어긋난다(변이 K22)."""
        def spec(name, products, order, period=K.PERIOD_WEEK):
            return K.CandidateSpec(name, "R04_NOREGION_SERIES", RN.KEY_KP, tuple(products), period, 1, order)
        specs = (spec("a", ("p",), 0), spec("b", ("q",), 1), spec("c", ("p", "q"), 2))
        self.assertEqual([[item.spec_id for item in group] for group in K.conflict_groups(specs)], [["a", "b", "c"]])
        for ordered in (tuple(reversed(specs)), (specs[2], specs[0], specs[1]), (specs[1], specs[2], specs[0])):                        # 입력 순서와 상관없다
            self.assertEqual([[item.spec_id for item in group] for group in K.conflict_groups(ordered)], [["a", "b", "c"]])
        many = (spec("a", ("p",), 0), spec("b", ("q",), 1), spec("c", ("r",), 2), spec("d", ("p", "r"), 3), spec("e", ("q", "r"), 4), spec("f", ("z",), 5), spec("g", ("z",), 6, K.PERIOD_MONTH))
        self.assertEqual([[item.spec_id for item in group] for group in K.conflict_groups(many)], [["a", "b", "c", "d", "e"], ["f"], ["g"]])
        self.assertEqual([item.spec_id for item in K.conflict_groups(many)[0]], sorted(item.spec_id for item in K.conflict_groups(many)[0]))   # 묶음 안 순서 = 글감 순서

    def test_the_groups_match_a_union_find_reference_on_random_subject_sets(self):
        """S2AFIX2 N4: 무작위 글감 집합 400개(고정 시드)에서 `conflict_groups` 의 묶음·묶음 안 순서·묶음 순서가 합집합 찾기로 만든 기준과 같다."""
        def reference(specs):
            parent = {item.spec_id: item.spec_id for item in specs}

            def find(name):
                while parent[name] != name:
                    parent[name] = parent[parent[name]]
                    name = parent[name]
                return name
            for index, first in enumerate(specs):
                for second in specs[index + 1:]:
                    if first.period == second.period and set(first.products) & set(second.products):
                        parent[find(first.spec_id)] = find(second.spec_id)
            parts = {}
            for item in sorted(specs, key=lambda each: each.order):
                parts.setdefault(find(item.spec_id), []).append(item)
            return tuple(sorted((tuple(part) for part in parts.values()), key=lambda part: part[0].order))
        rng = random.Random(20261110)
        for case in range(400):
            count = rng.randint(1, 8)
            orders = rng.sample(range(20), count)
            specs = tuple(K.CandidateSpec(f"s{index}", "R04_NOREGION_SERIES", RN.KEY_KP, tuple(rng.sample("pqrst", rng.randint(1, 3))), rng.choice((K.PERIOD_WEEK, K.PERIOD_MONTH)), 1, orders[index])
                          for index in range(count))
            with self.subTest(case=case):
                self.assertEqual(K.conflict_groups(specs), reference(specs))

    def test_no_day_of_the_year_has_two_subjects_of_the_same_product(self):
        day = datetime.date(2026, 1, 1)
        seen_groups = set()
        while day.year == 2026:
            ids = set(self.ids(day))
            for group in K.GROUPS:
                names = {spec.spec_id for spec in group}
                self.assertLessEqual(len(ids & names), 1, (day.isoformat(), ids & names))
                if ids & names:
                    seen_groups.add(tuple(sorted(names)))
            day += datetime.timedelta(days=1)
        self.assertEqual(len(seen_groups), len(K.GROUPS))                                                                        # 어느 묶음도 한 해 내내 비지 않는다

    def test_the_representative_alternates_from_week_to_week_and_both_subjects_come_around(self):
        spec = SPEC["kp_weekly"]
        monday = datetime.date(2026, 1, 5)                                                                                       # ISO 2026-W02 의 월요일
        reps = [K.representative(spec, monday + datetime.timedelta(days=7 * offset)).spec_id for offset in range(51)]            # W02–W52
        for before, after in zip(reps, reps[1:]):
            self.assertNotEqual(before, after)
        self.assertEqual(set(reps), {"kp_weekly", "kp_storm_weekly"})
        self.assertGreaterEqual(reps.count("kp_storm_weekly"), 24)
        week = [monday + datetime.timedelta(days=offset) for offset in range(7)]
        self.assertEqual(len({K.representative(spec, day).spec_id for day in week}), 1)                                          # 한 주 안에서는 같다
        self.assertEqual(K.representative(SPEC["kp_storm_weekly"], monday), K.representative(spec, monday))                      # 묶음 안 어느 글감으로 물어도 같다
        for single in ("flares_weekly", "scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"):
            for day in (monday, datetime.date(2026, 11, 10), datetime.date(2026, 12, 31)):
                self.assertIs(K.representative(SPEC[single], day), SPEC[single])                                                 # 묶음에 하나뿐이면 늘 자신이다

    def test_a_subject_of_the_same_product_made_in_the_period_blocks_the_group_whichever_it_was(self):
        today = "2026-11-12"                                                                                                     # ISO 46주 — 대표는 kp_weekly
        self.assertIn("kp_weekly", self.ids(today))
        self.assertNotIn("kp_storm_weekly", self.ids(today))
        for done_spec in ("kp_weekly", "kp_storm_weekly"):
            ids = self.ids(today, done=[K.candidate_key(SPEC[done_spec], today)])
            with self.subTest(done=done_spec):
                self.assertNotIn("kp_weekly", ids)
                self.assertNotIn("kp_storm_weekly", ids)
                self.assertIn("flares_weekly", ids)                                                                              # 다른 제품의 글감은 그대로다
        later = self.ids("2026-11-19", done=[K.candidate_key(SPEC["kp_weekly"], today), K.candidate_key(SPEC["kp_storm_weekly"], today)])
        self.assertIn("kp_storm_weekly", later)                                                                                  # 다음 주(47주)에는 다시 열리고 이번에는 R05 가 대표다
        self.assertNotIn("kp_weekly", later)

    def test_neighbouring_periods_are_not_stopped_by_the_key_alone_which_is_the_limit_to_be_closed_in_s2b(self):
        """한계를 못박는다: 키는 날짜가 아니라 기간 이름이라, 일요일(46주)에 낸 Kp 글과 이틀 뒤 화요일(47주)에 낼 Kp 글은 자료 창이 거의 겹쳐도 키로는 막히지 않는다. 이력에 글을 낸 날짜를
        남겨 같은 제품의 다음 글을 자료 창 길이만큼 띄우는 것은 S2b 가 한다(docs/FACT_PATH.md §14-5)."""
        sunday_key = K.candidate_key(SPEC["kp_weekly"], "2026-11-15")
        self.assertEqual(sunday_key, "space_weather.kp_weekly:2026-W46")
        self.assertIn("kp_storm_weekly", self.ids("2026-11-17", done=[sunday_key]))
        self.assertEqual(self.ids("2026-11-16", done=[sunday_key]).count("kp_storm_weekly"), 0)                                  # 월요일에는 kp_storm_weekly 가 아직 대기 전이다(대기 시작일 화요일)


class SpecsAreRealTest(unittest.TestCase):
    PAYLOADS = {
        "kp_estimated": lambda: H.kp_rows("2026-11-02", 8, storm_days=(2,), partial_last=3),
        "ssn_daily": lambda: H.ssn_daily_rows("2026-11-09", 70),
        "ssn_monthly": lambda: H.ssn_monthly_rows("2026-10", 70),
        "xray_flares": lambda: H.flare_rows(TR.EVENTS),
        "scales": lambda: H.scales_object(g_now="1", g_forecast=("1", "2", "0"), probs=TR.PROBS),
    }

    def test_every_subject_names_a_known_recipe_key_and_at_most_three_products(self):
        supported = {"R04_NOREGION_SERIES": set(RN.SERIES_BY_KEY), "R05_THRESHOLD_COUNT": {RN.KEY_KP, RN.KEY_FLARE_FLUX}, "R06_SCALE_OUTLOOK": {RN.KEY_SCALE_GEOMAGNETIC}}
        for spec in K.SPECS:
            with self.subTest(spec=spec.spec_id):
                self.assertIsNotNone(K.get_recipe(spec.recipe_id))
                self.assertIn(spec.key, supported[spec.recipe_id])
                self.assertTrue(1 <= len(spec.products) <= K.MAX_PRODUCTS_PER_POST)
                self.assertTrue(set(spec.products) <= set(N.PRODUCTS))
                self.assertIn(spec.period, (K.PERIOD_WEEK, K.PERIOD_MONTH))
                self.assertTrue(1 <= spec.due <= (7 if spec.period == K.PERIOD_WEEK else 28))
        self.assertEqual(len({spec.order for spec in K.SPECS}), len(K.SPECS))
        self.assertEqual(sorted(spec.order for spec in K.SPECS), list(range(len(K.SPECS))))
        self.assertEqual(len(set(K.SPEC_IDS)), len(K.SPEC_IDS))

    def test_every_subject_makes_a_post_end_to_end_with_the_fake_responses(self):
        for spec in K.SPECS:
            facts, records = [], []
            for product_id in spec.products:
                record, product_facts = H.parse_value(product_id, self.PAYLOADS[product_id]())
                facts += product_facts
                records.append(record)
            source = A.SourceInfo(H.NoaaProvider(), N.product_source_name(spec.products[0]), N.product_url(spec.products[0]))
            post = A.assemble(K.get_recipe(spec.recipe_id), facts, H.TODAY, records=records, source=source, params=spec.params())
            with self.subTest(spec=spec.spec_id):
                self.assertIsInstance(post, A.AssembledPost, post)
                self.assertEqual(post.recipe_id, spec.recipe_id)
                self.assertIn(spec.key, post.dedupe_key)

    def test_the_lookup_covers_the_old_and_the_new_recipes_only(self):
        self.assertEqual(sorted(K.RECIPES_BY_ID), sorted(list(R.RECIPES) + list(RN.NOREGION_RECIPES)))
        for bad in ("R99", "", None, 5, "r04_noregion_series"):
            self.assertIsNone(K.get_recipe(bad))
        self.assertIs(K.get_recipe("R01_time_series"), R.R01_TIME_SERIES)
        self.assertIs(K.get_recipe("R06_SCALE_OUTLOOK"), RN.R06_SCALE_OUTLOOK)


if __name__ == "__main__":
    unittest.main()
