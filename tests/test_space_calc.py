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
