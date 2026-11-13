"""새 계산식 시험(S2a): F15 하루 최댓값(구간이 모두 있는 날만)·F16 기준 범위 개수(0 도 값). 경계(구간 부족·값 없음·여러 날·같은 시각·단위 불일치·기준값 이상)·UTC 날짜 경계·결정성·입력 순서 무관·정수 표시.
네트워크·시계·난수 없이 돈다."""
import random
import unittest
from decimal import Decimal

import _bootstrap  # noqa: F401

from pipeline import calc as C
from pipeline import facts as F

RECORD = "s" + "1" * 16


def kp(value, stamp, *, unit="Kp", key="space_weather.kp_estimated", provider="noaa_swpc_json", meta=None):
    return F.Fact.create(provider, RECORD, F.KIND_OBSERVATION, key, value, unit=unit, as_of=stamp, label_ko="NOAA 추정 Kp", meta=meta)


def day_of(day, values, *, offset="Z", start_hour=0):
    """한 날의 3시간 구간 Fact(구간 수 = 값 수). 시각은 `day`T시간 + offset."""
    return [kp(value, f"{day}T{start_hour + 3 * index:02d}:00:00{offset}") for index, value in enumerate(values)]


def threshold(value="5", unit="Kp", key="space_weather.kp_storm_threshold"):
    return F.Fact.create("noaa_swpc_json", RECORD, F.KIND_NUMBER, key, value, unit=unit, as_of="2026-11-10", label_ko="지자기 폭풍 기준", meta={"status": "reference", "producer": "NOAA"})


class DayMaxTest(unittest.TestCase):
    def test_the_highest_of_a_complete_day_becomes_the_value_of_that_day(self):
        group = day_of("2026-11-03", ["0.67", "1.67", "2", "1.67", "0.67", "1.33", "1.67", "1.33"])
        result = C.f15_day_max(group, expected_count=8)
        self.assertIsInstance(result, F.DerivedFact)
        self.assertEqual((result.formula_id, result.value, result.unit, result.as_of, result.key, result.region, result.provider_id),
                         ("F15_day_max", Decimal(2), "Kp", "2026-11-03", "space_weather.kp_estimated", None, "noaa_swpc_json"))
        self.assertEqual(F.validate_derived(result), [])
        self.assertEqual(result.input_fact_ids[0], group[2].fact_id)                          # 첫 입력은 최댓값을 가진 Fact
        self.assertEqual(set(result.input_fact_ids), {f.fact_id for f in group})
        self.assertEqual(len(result.input_fact_ids), 8)

    def test_a_tie_names_the_latest_interval_first(self):
        group = day_of("2026-11-03", ["1", "2", "0.67", "2", "1", "1", "1", "1"])
        result = C.f15_day_max(group, expected_count=8)
        self.assertEqual(result.input_fact_ids[0], group[3].fact_id)

    def test_incomplete_or_missing_or_duplicated_days_make_no_value(self):
        full = day_of("2026-11-03", ["1"] * 8)
        self.assertEqual(C.f15_day_max(full[:7], expected_count=8).reason, "INCOMPLETE_PERIOD")
        self.assertEqual(C.f15_day_max(full + day_of("2026-11-03", ["2"], start_hour=1), expected_count=8).reason, "INCOMPLETE_PERIOD")
        holes = list(full)
        holes[3] = kp(None, "2026-11-03T09:00:00Z")
        self.assertEqual(C.f15_day_max(holes, expected_count=8).reason, "MISSING_VALUE")
        self.assertEqual(C.f15_day_max([], expected_count=8).reason, "TOO_FEW_INPUTS")
        twice = full[:7] + [kp("3", "2026-11-03T18:00:00Z")]                                   # 같은 시각의 값이 둘(여덟 개를 채워도 거절)
        self.assertEqual(C.f15_day_max(twice, expected_count=8).reason, "DUPLICATE_PERIOD")
        spread = day_of("2026-11-03", ["1"] * 4, start_hour=12) + day_of("2026-11-04", ["1"] * 4)
        self.assertEqual(C.f15_day_max(spread, expected_count=8).reason, "NOT_ONE_DAY")
        for bad in (0, -1, 8.0, "8", None, True):
            self.assertEqual(C.f15_day_max(full, expected_count=bad).reason, "INCOMPLETE_PERIOD")

    def test_everything_but_the_hour_must_match(self):
        full = day_of("2026-11-03", ["1"] * 8)
        for odd, reason in ((kp("1", "2026-11-03T21:00:00Z", unit="℃"), "UNIT_MISMATCH"), (kp("1", "2026-11-03T21:00:00Z", key="space_weather.kp_outlook"), "DEFINITION_MISMATCH"),
                            (kp("1", "2026-11-03T21:00:00Z", provider="other_stats"), "PROVIDER_MISMATCH"), (kp("1", "2026-11-03"), "PERIOD_KIND_MISMATCH")):
            with self.subTest(reason=reason):
                result = C.f15_day_max(full[:7] + [odd], expected_count=8)
                self.assertIsInstance(result, C.Skipped)
                self.assertEqual(result.reason, reason)

    def test_the_day_is_the_utc_day_whatever_offset_the_time_is_written_in(self):
        korean = [kp("2", "2026-11-03T08:00:00+09:00"), kp("3", "2026-11-03T05:00:00+09:00")]          # UTC 로는 11월 2일 23시·20시
        result = C.f15_day_max(korean, expected_count=2)
        self.assertEqual((result.as_of, result.value), ("2026-11-02", Decimal(3)))
        straddle = [kp("1", "2026-11-03T08:00:00+09:00"), kp("1", "2026-11-03T10:00:00+09:00")]        # 한국 날짜는 같지만 UTC 날짜는 둘
        self.assertEqual(C.f15_day_max(straddle, expected_count=2).reason, "NOT_ONE_DAY")
        same = [kp("1", "2026-11-03T08:00:00+00:00"), kp("2", "2026-11-03T09:00:00Z")]
        self.assertEqual(C.f15_day_max(same, expected_count=2).as_of, "2026-11-03")

    def test_the_result_does_not_depend_on_the_input_order(self):
        group = day_of("2026-11-03", ["0.33", "2.67", "1", "2", "0.67", "1.33", "1.67", "2.33"])
        base = C.f15_day_max(group, expected_count=8)
        rng = random.Random(7)
        for _ in range(30):
            shuffled = list(group)
            rng.shuffle(shuffled)
            self.assertEqual(C.f15_day_max(shuffled, expected_count=8), base)

    def test_a_day_max_series_can_feed_the_series_formulas(self):
        days = []
        for index, day in enumerate(("2026-11-03", "2026-11-04", "2026-11-05")):
            days.append(C.f15_day_max(day_of(day, [str(index + 1)] + ["0"] * 7), expected_count=8))
        change = C.f01_change(days[2], days[1])
        self.assertEqual((change.value, change.unit), (Decimal(1), "Kp"))
        mean = C.f07_rolling_mean(days)
        self.assertEqual(mean.value, Decimal(2))
        self.assertEqual(C.f09_max(days).value, Decimal(3))
        self.assertEqual(C.f12_count(days, "일").value, Decimal(3))
        self.assertIsInstance(C.f02_pct_change(days[2], days[1]), C.Skipped)                    # Kp 는 비율 척도가 아니다


class CountBetweenTest(unittest.TestCase):
    def values(self, texts, start=0):
        return [kp(text, f"2026-11-03T{start + 3 * index:02d}:00:00Z") for index, text in enumerate(texts)]

    def test_counts_values_at_or_above_the_bound(self):
        group = self.values(["4.67", "5", "5.33", "2", "9", "0.33", "4.99", "7"])
        result = C.f16_count_between(group, threshold(), None, "구간")
        self.assertIsInstance(result, F.DerivedFact)
        self.assertEqual((result.formula_id, result.value, result.unit, result.key, result.as_of), ("F16_count_between", Decimal(4), "구간", "space_weather.kp_estimated", group[-1].as_of))
        self.assertEqual(F.validate_derived(result), [])
        self.assertEqual(result.input_fact_ids[0], threshold().fact_id)                         # 기준값 id 가 먼저 — 어떤 기준으로 셌는지 남는다
        self.assertEqual(len(result.input_fact_ids), 1 + 8)

    def test_the_bound_is_inclusive_below_and_exclusive_above(self):
        group = self.values(["1", "2", "3", "4", "5", "6"])
        low, high = threshold("2"), threshold("5", key="space_weather.kp_storm_threshold_high")
        self.assertEqual(C.f16_count_between(group, low, high, "건").value, Decimal(3))          # 2·3·4
        self.assertEqual(C.f16_count_between(group, low, None, "건").value, Decimal(5))
        self.assertEqual(C.f16_count_between(group, threshold("6"), None, "건").value, Decimal(1))
        self.assertEqual(C.f16_count_between(group, threshold("7"), None, "건").value, Decimal(0))

    def test_zero_is_a_value_and_it_is_shown_as_a_whole_number(self):
        group = self.values(["1", "1.33"])
        result = C.f16_count_between(group, threshold(), None, "일")
        self.assertEqual(result.value, Decimal(0))
        self.assertEqual(F.format_object(result), "0일")
        self.assertIn("F16_count_between", F.INTEGER_FORMULAS)
        fractional = F.Fact.create("noaa_swpc_json", RECORD, F.KIND_OBSERVATION, "space_weather.kp_estimated", "5.5", unit="Kp", as_of="2026-11-03T00:00:00Z", label_ko="NOAA 추정 Kp")
        self.assertEqual(F.format_object(C.f16_count_between([fractional], threshold(), None, "구간"), context={"Kp": 3}), "1구간")

    def test_empty_missing_or_inconsistent_inputs_make_no_count(self):
        group = self.values(["1", "2", "6"])
        self.assertEqual(C.f16_count_between([], threshold(), None, "건").reason, "TOO_FEW_INPUTS")
        with_hole = group + [kp(None, "2026-11-03T09:00:00Z")]
        self.assertEqual(C.f16_count_between(with_hole, threshold(), None, "건").reason, "MISSING_VALUE")
        self.assertEqual(C.f16_count_between(group, threshold(unit="℃"), None, "건").reason, "UNIT_MISMATCH")
        self.assertEqual(C.f16_count_between(group, kp(None, "2026-11-10"), None, "건").reason, "BAD_RANGE")
        self.assertEqual(C.f16_count_between(group, threshold("5"), threshold("5", key="space_weather.other_threshold"), "건").reason, "BAD_RANGE")        # 위쪽 끝이 아래쪽 끝 이하
        self.assertEqual(C.f16_count_between(group, threshold("5"), threshold("3", key="space_weather.other_threshold"), "건").reason, "BAD_RANGE")
        self.assertEqual(C.f16_count_between(group, group[0], None, "건").reason, "DUPLICATE_INPUT")                                              # 기준값이 묶음 안에 있다
        self.assertEqual(C.f16_count_between(group, threshold(), threshold(), "건").reason, "BAD_RANGE")
        text = F.Fact.create("noaa_swpc_json", RECORD, F.KIND_CLASS_CODE, "space_weather.xray_flare_class", "M1.0", as_of="2026-11-03T00:00:00Z")
        self.assertEqual(C.f16_count_between(group, text, None, "건").reason, "BAD_RANGE")
        odd = group + [kp("1", "2026-11-03T12:00:00Z", key="space_weather.kp_outlook")]
        self.assertEqual(C.f16_count_between(odd, threshold(), None, "건").reason, "DEFINITION_MISMATCH")

    def test_the_count_does_not_depend_on_input_order_and_works_on_derived_days(self):
        days = [C.f15_day_max(day_of(f"2026-11-0{day}", [str(day)] + ["0"] * 7), expected_count=8) for day in range(3, 9)]
        rng = random.Random(11)
        base = C.f16_count_between(days, threshold("5"), None, "일")
        self.assertEqual(base.value, Decimal(4))
        self.assertEqual(base.as_of, "2026-11-08")
        for _ in range(20):
            shuffled = list(days)
            rng.shuffle(shuffled)
            self.assertEqual(C.f16_count_between(shuffled, threshold("5"), None, "일"), base)
        self.assertEqual(C.f16_count_between(days, threshold("3"), threshold("6"), "일").value, Decimal(3))                    # 3·4·5

    def test_same_input_gives_the_same_result_with_a_foreign_global_decimal_context(self):
        import decimal
        group = self.values(["4.67", "5.33", "2"])
        base = C.f16_count_between(group, threshold(), None, "구간")
        with decimal.localcontext() as ctx:
            ctx.prec = 3
            ctx.rounding = decimal.ROUND_DOWN
            self.assertEqual(C.f16_count_between(group, threshold(), None, "구간"), base)
            self.assertEqual(C.f15_day_max(day_of("2026-11-03", ["1.33"] * 8), expected_count=8).value, Decimal("1.33"))


class RegistryTest(unittest.TestCase):
    def test_the_new_formulas_are_registered_named_and_documented_by_their_own_label(self):
        self.assertEqual(C.FORMULAS["F15_day_max"], C.f15_day_max)
        self.assertEqual(C.FORMULAS["F16_count_between"], C.f16_count_between)
        for formula_id in ("F15_day_max", "F16_count_between"):
            self.assertIn(formula_id, C.FORMULA_LABELS)
            self.assertNotRegex(C.FORMULA_LABELS[formula_id], r"\d")
        for code in ("INCOMPLETE_PERIOD", "DUPLICATE_PERIOD", "NOT_ONE_DAY", "BAD_RANGE"):
            self.assertIn(code, C.REASON_TEXT)
            self.assertNotRegex(C.REASON_TEXT[code], r"\d")


MONTH_KEY = "space_weather.sunspot_monthly_swpc"


def month(value, as_of, *, unit="개", key=MONTH_KEY, provider="noaa_swpc_json", region=None):
    """월별 흑점수 모양의 Fact 하나(S2c-1 시험용). as_of 는 `YYYY-MM`."""
    return F.Fact.create(provider, RECORD, F.KIND_OBSERVATION, key, value, unit=unit, as_of=as_of, region=region, label_ko="SWPC 월평균 흑점수", meta={"status": "observed", "producer": "NOAA"})


def series_of_months(values, *, start=(2000, 1)):
    """값 목록 → 이어지는 달의 Fact 목록(앞선 달부터)."""
    first = start[0] * 12 + start[1] - 1
    return [month(value, f"{(first + index) // 12:04d}-{(first + index) % 12 + 1:02d}") for index, value in enumerate(values)]


class SeasonRankTest(unittest.TestCase):
    """S2c-1 F17 — 같은 달·서로 다른 해의 월 값 묶음 안 순위."""

    def octobers(self, values, first_year=2019):
        return [month(value, f"{first_year + index}-10") for index, value in enumerate(values)]

    def test_rank_one_is_the_highest_and_ties_share_a_rank_and_skip_the_next(self):
        group = self.octobers(["10", "30", "20", "30", "5"])
        self.assertEqual([C.f17_season_rank(fact, group).value for fact in group], [Decimal(4), Decimal(1), Decimal(3), Decimal(1), Decimal(5)])
        flat = self.octobers(["7", "7", "7"])
        self.assertEqual({C.f17_season_rank(fact, flat).value for fact in flat}, {Decimal(1)})                 # 모두 같으면 모두 1위

    def test_the_result_records_whom_it_is_about_and_what_it_was_built_from(self):
        group = self.octobers(["61.71", "107.06", "159.45", "94.94"])
        result = C.f17_season_rank(group[0], group)
        self.assertIsInstance(result, F.DerivedFact)
        self.assertEqual((result.formula_id, result.value, result.unit, result.as_of, result.key, result.region, result.provider_id), ("F17_season_rank", Decimal(4), "위", "2019-10", MONTH_KEY, None, "noaa_swpc_json"))
        self.assertEqual(F.validate_derived(result), [])
        self.assertEqual(result.input_fact_ids[0], group[0].fact_id)                          # 첫 입력은 순위를 매긴 대상
        self.assertEqual(set(result.input_fact_ids), {fact.fact_id for fact in group})
        self.assertEqual(len(result.input_fact_ids), len(group))
        self.assertEqual(F.format_object(result), "4위")

    def test_fewer_than_three_members_make_no_rank_and_three_is_enough(self):
        group = self.octobers(["1", "2", "3"])
        self.assertIsInstance(C.f17_season_rank(group[0], group), F.DerivedFact)
        for size in (0, 1, 2):
            with self.subTest(size=size):
                self.assertEqual(C.f17_season_rank(group[0], group[:size]).reason, "TOO_FEW_INPUTS")
        self.assertEqual(C.MIN_SEASON_MEMBERS, 3)

    def test_the_members_must_be_the_same_calendar_month_of_different_years_and_the_target_must_be_among_them(self):
        group = self.octobers(["1", "2", "3", "4"])
        self.assertEqual(C.f17_season_rank(group[0], group + [month("9", "2024-11")]).reason, "NOT_SAME_SEASON")
        self.assertEqual(C.f17_season_rank(group[0], group + [month("7", "2020-10")]).reason, "DUPLICATE_MONTH")             # 같은 해(같은 달)가 둘
        self.assertEqual(C.f17_season_rank(month("5", "2030-10"), group).reason, "NOT_IN_GROUP")
        days = [month(str(index), f"2026-10-0{index}") for index in range(1, 5)]
        self.assertEqual(C.f17_season_rank(days[0], days).reason, "NOT_MONTHLY")
        shuffled_years = [month("1", "2019-10"), month("2", "2019-10"), month("3", "2020-10")]
        self.assertEqual(C.f17_season_rank(shuffled_years[0], shuffled_years).reason, "DUPLICATE_MONTH")
        self.assertEqual(C.f17_season_rank(group[0], group + [group[1]]).reason, "DUPLICATE_INPUT")                           # 같은 입력이 두 번

    def test_everything_but_the_year_must_match(self):
        group = self.octobers(["1", "2", "3", "4"])
        for odd, reason in ((month("5", "2024-10", unit="건"), "UNIT_MISMATCH"), (month("5", "2024-10", key="space_weather.other"), "DEFINITION_MISMATCH"),
                            (month("5", "2024-10", provider="other_stats"), "PROVIDER_MISMATCH"), (month(None, "2024-10"), "MISSING_VALUE"), (month("5", "2024-10", region="R9"), "REGION_MISMATCH")):
            with self.subTest(reason=reason):
                result = C.f17_season_rank(group[0], group + [odd])
                self.assertIsInstance(result, C.Skipped)
                self.assertEqual(result.reason, reason)
                self.assertEqual(result.formula_id, "F17_season_rank")

    def test_the_rank_does_not_depend_on_the_input_order_or_the_global_decimal_context(self):
        import decimal
        group = self.octobers(["61.71", "107.06", "159.45", "94.94", "85.29", "88.68"])
        base = C.f17_season_rank(group[0], group)
        rng = random.Random(17)
        for _ in range(30):
            shuffled = list(group)
            rng.shuffle(shuffled)
            self.assertEqual(C.f17_season_rank(group[0], shuffled), base)
        with decimal.localcontext() as ctx:
            ctx.prec = 3
            ctx.rounding = decimal.ROUND_DOWN
            self.assertEqual(C.f17_season_rank(group[0], group), base)

    def test_it_agrees_with_a_plain_count_on_random_groups(self):
        rng = random.Random(170)
        for case in range(150):
            size = rng.randint(3, 12)
            values = [str(rng.randint(0, 5)) for _ in range(size)]          # 값이 자주 겹치게 작은 범위
            group = self.octobers(values, first_year=1997)
            target = rng.randrange(size)
            want = 1 + sum(1 for value in values if int(value) > int(values[target]))
            self.assertEqual(C.f17_season_rank(group[target], group).value, Decimal(want), (case, values, target))


class LastLowerTest(unittest.TestCase):
    """S2c-1 F18 — 앞선 달 가운데 이번 값보다 낮은 가장 나중 달."""

    def test_the_latest_earlier_month_that_was_lower_is_found_and_the_result_is_that_months_value(self):
        series = series_of_months(["90", "56.97", "70", "80", "85", "88", "75", "61.71"], start=(2021, 12))             # 2021-12 … 2022-07
        cur, earlier = series[-1], series[:-1]
        result = C.f18_last_lower(cur, earlier)
        self.assertIsInstance(result, F.DerivedFact)
        self.assertEqual((result.formula_id, result.value, result.unit, result.as_of, result.key, result.region, result.provider_id), ("F18_last_lower", Decimal("56.97"), "개", "2022-01", MONTH_KEY, None, "noaa_swpc_json"))
        self.assertEqual(F.validate_derived(result), [])
        self.assertEqual(F.format_object(result, context={"개": 2}), "56.97개")                                       # 값은 자료의 소수 자리(글의 표시 자리)로 보인다

    def test_the_inputs_are_the_found_month_the_current_month_and_the_months_after_the_found_one_only(self):
        series = series_of_months(["90", "56.97", "70", "80", "85", "88", "75", "61.71"], start=(2021, 12))
        cur, earlier = series[-1], series[:-1]
        result = C.f18_last_lower(cur, earlier)
        found, between, before = series[1], series[2:7], series[:1]
        self.assertEqual(result.input_fact_ids[0], found.fact_id)                                                  # 첫 입력은 찾은 달
        self.assertEqual(result.input_fact_ids[1], cur.fact_id)
        self.assertEqual(set(result.input_fact_ids), {found.fact_id, cur.fact_id} | {fact.fact_id for fact in between})
        self.assertTrue(all(fact.fact_id not in result.input_fact_ids for fact in before))                         # 찾은 달보다 앞선 달은 결과를 정하지 않으므로 싣지 않는다
        self.assertEqual(list(result.input_fact_ids[2:]), sorted(fact.fact_id for fact in between))               # 나머지는 id 순

    def test_a_month_with_the_same_value_is_not_lower(self):
        series = series_of_months(["10", "60", "60", "70", "60"])
        result = C.f18_last_lower(series[-1], series[:-1])
        self.assertEqual((result.as_of, result.value), ("2000-01", Decimal(10)))                                   # 값이 같은 달은 낮은 달이 아니라 건너뛰고 더 앞의 낮은 달을 찾는다
        self.assertEqual(C.f18_last_lower(series_of_months(["60", "60"])[-1], series_of_months(["60", "60"])[:-1]).reason, "NO_MATCH")

    def test_no_lower_month_makes_no_value_and_the_reason_is_no_match(self):
        series = series_of_months(["50", "60", "70", "40"])
        result = C.f18_last_lower(series[-1], series[:-1])
        self.assertIsInstance(result, C.Skipped)
        self.assertEqual((result.formula_id, result.reason), ("F18_last_lower", "NO_MATCH"))
        self.assertTrue(C.REASON_TEXT["NO_MATCH"])

    def test_the_current_month_must_be_later_than_every_member_and_the_members_distinct(self):
        series = series_of_months(["10", "20", "30", "25"])
        cur, earlier = series[-1], series[:-1]
        self.assertEqual(C.f18_last_lower(cur, []).reason, "TOO_FEW_INPUTS")
        self.assertEqual(C.f18_last_lower(cur, earlier + [cur]).reason, "DUPLICATE_INPUT")
        self.assertEqual(C.f18_last_lower(series[1], series).reason, "DUPLICATE_INPUT")
        self.assertEqual(C.f18_last_lower(series[1], [series[0], series[2]]).reason, "NOT_EARLIER")                  # 나중 달이 묶음에 있다
        same_month = month("5", "2000-04")                                                                         # cur 와 같은 달(2000-04)의 다른 Fact
        self.assertEqual(C.f18_last_lower(cur, earlier + [same_month]).reason, "NOT_EARLIER")
        twice = month("12", "2000-02")
        self.assertEqual(C.f18_last_lower(cur, earlier + [twice]).reason, "DUPLICATE_MONTH")
        days = [month(str(index), f"2026-10-0{index}") for index in range(1, 4)]
        self.assertEqual(C.f18_last_lower(days[2], days[:2]).reason, "NOT_MONTHLY")

    def test_everything_but_the_month_must_match(self):
        series = series_of_months(["10", "20", "30", "25"])
        cur, earlier = series[-1], series[:-1]
        odd_date = "1999-12"
        for odd, reason in ((month("5", odd_date, unit="건"), "UNIT_MISMATCH"), (month("5", odd_date, key="space_weather.other"), "DEFINITION_MISMATCH"), (month("5", odd_date, provider="other_stats"), "PROVIDER_MISMATCH"),
                            (month(None, odd_date), "MISSING_VALUE"), (month("5", odd_date, region="R9"), "REGION_MISMATCH")):
            with self.subTest(reason=reason):
                result = C.f18_last_lower(cur, earlier + [odd])
                self.assertIsInstance(result, C.Skipped)
                self.assertEqual(result.reason, reason)
        self.assertEqual(C.f18_last_lower(month("5", "2000-04", region="R9"), earlier).reason, "REGION_MISMATCH")

    def test_it_agrees_with_a_plain_backward_scan_on_random_series(self):
        rng = random.Random(18)
        for case in range(200):
            count = rng.randint(2, 40)
            values = [str(rng.randint(0, 6)) for _ in range(count)]                      # 값이 자주 겹치게 작은 범위
            series = series_of_months(values)
            cur, earlier = series[-1], series[:-1]
            want = next((fact for fact in reversed(earlier) if fact.value < cur.value), None)
            result = C.f18_last_lower(cur, earlier)
            with self.subTest(case=case):
                if want is None:
                    self.assertEqual(result.reason, "NO_MATCH")
                    continue
                self.assertEqual((result.as_of, result.value, result.input_fact_ids[0]), (want.as_of, want.value, want.fact_id))
                after = series[series.index(want) + 1:-1]
                self.assertEqual(set(result.input_fact_ids), {want.fact_id, cur.fact_id} | {fact.fact_id for fact in after})
                self.assertTrue(all(fact.value >= cur.value for fact in after))               # 그 달 뒤로는 모두 이번 값 이상이다 — 입력이 이 사실을 받친다

    def test_the_result_does_not_depend_on_the_input_order_or_the_global_decimal_context(self):
        import decimal
        series = series_of_months(["90", "56.97", "70", "80", "85", "88", "75", "61.71"], start=(2021, 12))
        cur, earlier = series[-1], series[:-1]
        base = C.f18_last_lower(cur, earlier)
        rng = random.Random(19)
        for _ in range(30):
            shuffled = list(earlier)
            rng.shuffle(shuffled)
            self.assertEqual(C.f18_last_lower(cur, shuffled), base)
        with decimal.localcontext() as ctx:
            ctx.prec = 3
            ctx.rounding = decimal.ROUND_DOWN
            self.assertEqual(C.f18_last_lower(cur, earlier), base)


class MonthsBetweenTest(unittest.TestCase):
    """S2c-1 F19 — 두 월 값의 기준일 사이 개월 수."""

    def test_the_number_of_months_between_two_month_values(self):
        later, earlier = month("61.71", "2026-10"), month("56.97", "2022-01")
        result = C.f19_months_between(later, earlier)
        self.assertIsInstance(result, F.DerivedFact)
        self.assertEqual((result.formula_id, result.value, result.unit, result.as_of, result.key, result.provider_id), ("F19_months_between", Decimal(57), "개월", "2026-10", MONTH_KEY, "noaa_swpc_json"))
        self.assertEqual(F.validate_derived(result), [])
        self.assertEqual(result.input_fact_ids, (later.fact_id, earlier.fact_id))
        self.assertEqual(F.format_object(result), "57개월")
        for later_text, earlier_text, expected in (("2026-01", "2025-12", 1), ("2026-12", "2025-01", 23), ("2026-03", "2026-02", 1), ("2026-10", "2026-01", 9), ("2026-01", "1997-01", 348)):
            with self.subTest(later=later_text, earlier=earlier_text):
                self.assertEqual(C.f19_months_between(month("1", later_text), month("2", earlier_text)).value, Decimal(expected))

    def test_the_earlier_side_may_be_a_calculation_result_whose_date_is_that_month(self):
        series = series_of_months(["90", "56.97", "70", "80", "85", "88", "75", "61.71"], start=(2021, 12))
        found = C.f18_last_lower(series[-1], series[:-1])
        result = C.f19_months_between(series[-1], found)
        self.assertEqual((result.value, result.unit, result.as_of), (Decimal(6), "개월", "2022-07"))
        self.assertEqual(result.input_fact_ids, (series[-1].fact_id, found.fact_id))                           # 계산 결과 → 계산 결과 사슬이 입력 id 로 남는다

    def test_the_earlier_month_must_be_earlier_and_both_must_be_monthly_comparable_values(self):
        later, earlier = month("1", "2026-10"), month("2", "2026-09")
        self.assertEqual(C.f19_months_between(earlier, later).reason, "NOT_EARLIER")
        self.assertEqual(C.f19_months_between(later, month("3", "2026-10")).reason, "NOT_EARLIER")                # 같은 달은 0개월이 아니라 만들지 않는다
        self.assertEqual(C.f19_months_between(month("1", "2026-10-03"), month("2", "2026-10-01")).reason, "NOT_MONTHLY")
        for odd, reason in ((month("5", "2022-01", unit="건"), "UNIT_MISMATCH"), (month("5", "2022-01", key="space_weather.other"), "DEFINITION_MISMATCH"),
                            (month("5", "2022-01", provider="other_stats"), "PROVIDER_MISMATCH"), (month(None, "2022-01"), "MISSING_VALUE"), (month("5", "2022-01", region="R9"), "REGION_MISMATCH")):
            with self.subTest(reason=reason):
                self.assertEqual(C.f19_months_between(later, odd).reason, reason)
        self.assertEqual(C.f19_months_between(month("1", "2026"), month("2", "2020")).reason, "NOT_MONTHLY")        # 연 단위도 개월 수를 만들지 않는다
        self.assertEqual(C.f19_months_between(month("1", "2026-10"), month("2", "2020")).reason, "PERIOD_KIND_MISMATCH")

    def test_the_months_are_a_whole_number_even_when_the_context_gives_the_unit_decimals(self):
        result = C.f19_months_between(month("1", "2026-10"), month("2", "2022-01"))
        self.assertIn("F19_months_between", F.INTEGER_FORMULAS)
        self.assertEqual(F.format_object(result, context={"개월": 3}), "57개월")
        group = [month("5", "2026-10"), month("6", "2025-10"), month("7", "2024-10")]
        rank = C.f17_season_rank(group[1], group)                                                                   # 값 6 보다 높은 값은 7 하나 — 2위
        self.assertEqual((rank.value, F.format_object(rank, context={"위": 2})), (Decimal(2), "2위"))
        self.assertIn("F17_season_rank", F.INTEGER_FORMULAS)
        self.assertNotIn("F18_last_lower", F.INTEGER_FORMULAS)                                                     # 마지막으로 낮은 달의 값은 자료의 소수 자리로 보인다


class SeasonRegistryTest(unittest.TestCase):
    def test_the_three_new_formulas_are_registered_under_their_own_number_with_a_digit_free_label(self):
        for number, formula_id, function in ((17, "F17_season_rank", C.f17_season_rank), (18, "F18_last_lower", C.f18_last_lower), (19, "F19_months_between", C.f19_months_between)):
            with self.subTest(formula=formula_id):
                self.assertEqual(C.FORMULAS[formula_id], function)
                self.assertEqual(function.__name__, formula_id.lower())
                self.assertIn(formula_id, C.FORMULA_LABELS)
                self.assertTrue(C.FORMULA_LABELS[formula_id])
                self.assertNotRegex(C.FORMULA_LABELS[formula_id], r"\d")
        self.assertEqual(sorted(int(formula_id[1:3]) for formula_id in C.FORMULAS), list(range(1, 20)))             # 번호가 빈틈없이 1–19

    def test_the_new_reason_codes_have_a_digit_free_text(self):
        for code in ("NOT_MONTHLY", "NOT_SAME_SEASON", "DUPLICATE_MONTH", "NO_MATCH"):
            with self.subTest(code=code):
                self.assertIn(code, C.REASON_TEXT)
                self.assertNotRegex(C.REASON_TEXT[code], r"\d")
                self.assertGreaterEqual(len(C.REASON_TEXT[code]), 8)

    def test_the_new_formulas_never_return_anything_but_a_derived_fact_or_a_skip(self):
        samples = [month("1", "2026-10"), month("2", "2025-10"), month("3", "2024-10"), month(None, "2023-10"), month("9", "2022-09"), month("4", "2026-10-02")]
        rng = random.Random(1719)
        for _ in range(300):
            group = [rng.choice(samples) for _ in range(rng.randint(0, 5))]
            target = rng.choice(samples)
            for result in (C.f17_season_rank(target, group), C.f18_last_lower(target, group), C.f19_months_between(target, rng.choice(samples))):
                self.assertIsInstance(result, (F.DerivedFact, C.Skipped))


class FactMetaTailTest(unittest.TestCase):
    """꼬리표(`meta`)가 없거나 비었으면 Fact 의 id·JSON 이 꼬리표가 생기기 전과 같다 — 기존 Fact 의 id 가 바뀌지 않는다(변이 F03 이 살아남던 구멍)."""

    def test_an_empty_meta_is_the_same_fact_as_no_meta(self):
        plain = kp("3.33", "2026-11-09T00:00:00Z")
        self.assertIsNone(plain.meta)
        for empty in ({}, (), []):
            other = kp("3.33", "2026-11-09T00:00:00Z", meta=empty)
            with self.subTest(empty=repr(empty)):
                self.assertIsNone(other.meta)
                self.assertEqual(other.fact_id, plain.fact_id)
                self.assertEqual(F.fact_to_dict(other), F.fact_to_dict(plain))
                self.assertNotIn("meta", F.fact_to_dict(other))

    def test_a_meta_changes_the_id_and_is_kept_in_sorted_order(self):
        plain = kp("3.33", "2026-11-09T00:00:00Z")
        tagged = kp("3.33", "2026-11-09T00:00:00Z", meta={"status": "observed", "producer": "NOAA"})
        reversed_ = kp("3.33", "2026-11-09T00:00:00Z", meta=[("status", "observed"), ("producer", "NOAA")])
        self.assertNotEqual(tagged.fact_id, plain.fact_id)
        self.assertEqual(tagged.fact_id, reversed_.fact_id)
        self.assertEqual(tagged.meta, (("producer", "NOAA"), ("status", "observed")))
        self.assertEqual(tagged.meta_value("producer"), "NOAA")
        self.assertIsNone(tagged.meta_value("quality"))


if __name__ == "__main__":
    unittest.main()
