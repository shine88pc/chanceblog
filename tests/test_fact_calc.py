"""구조화 Fact 경로 1단계 — `pipeline/calc.py` 시험: 계산식마다 통과·경계(0 나누기·누락·단위/기간 불일치)·비교 가능성 판정·결정성·입력 순서 무관.
네트워크·시계·난수 없이 돈다."""
import ast
import re
import unittest
from decimal import Decimal

import _bootstrap
import fact_helpers as H

from pipeline import calc as C
from pipeline import facts as F

ROOT = _bootstrap.ROOT
MAKE = H.make_fact


def months(values, *, start=(2025, 1), **kw):
    """연속한 달의 Fact 목록(값이 None 이면 모름)."""
    out = []
    year, month = start
    for value in values:
        out.append(MAKE(value, period=f"{year:04d}-{month:02d}", **kw))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return out


def status_fact():
    return F.Fact.create("mock_stats", "s" + "0" * 16, F.KIND_OFFICIAL_STATUS, "environment.alert", "경보")


class ComparableTest(unittest.TestCase):
    def test_same_everything_is_comparable(self):
        a, b = MAKE("3.5"), MAKE("3.1")
        verdict = C.comparable(a, b)
        self.assertTrue(verdict)
        self.assertTrue(verdict.ok)
        self.assertEqual((verdict.verdict, verdict.reasons), (C.COMPARABLE, ()))

    def test_each_difference_gets_its_own_verdict_and_reason(self):
        base = MAKE("3.5")
        cases = [
            ("UNIT_MISMATCH", C.DISCARD, MAKE("3.5", unit="명")),
            ("MISSING_VALUE", C.DISCARD, MAKE(None)),
            ("NON_NUMERIC", C.DISCARD, status_fact()),
            ("PERIOD_MISMATCH", C.CONTEXT_ONLY, MAKE("3.5", period="2026-02")),
            ("PERIOD_KIND_MISMATCH", C.CONTEXT_ONLY, MAKE("3.5", period="2026-Q1")),
            ("DEFINITION_MISMATCH", C.CONTEXT_ONLY, MAKE("3.5", key="labour.employment_rate")),
            ("REGION_LEVEL_MISMATCH", C.CONTEXT_ONLY, MAKE("3.5", level="city")),
            ("PROVIDER_MISMATCH", C.CONTEXT_ONLY, MAKE("3.5", provider="other_stats")),
        ]
        for reason, verdict, other in cases:
            with self.subTest(reason=reason):
                result = C.comparable(base, other)
                self.assertFalse(result)
                self.assertEqual(result.verdict, verdict)
                self.assertEqual(result.reasons[0], reason)
                self.assertIn(reason, C.REASON_TEXT)

    def test_a_different_region_alone_is_still_comparable(self):
        self.assertTrue(C.comparable(MAKE("3.5", region="R01"), MAKE("3.1", region="R02")))

    def test_period_may_differ_when_asked_but_the_period_kind_may_not(self):
        a, b = MAKE("3.5", period="2026-03"), MAKE("3.1", period="2025-03")
        self.assertFalse(C.comparable(a, b))
        self.assertTrue(C.comparable(a, b, same_period=False))
        self.assertEqual(C.comparable(a, MAKE("3.1", period="2025-Q1"), same_period=False).reasons, ("PERIOD_KIND_MISMATCH",))

    def test_the_flags_relax_one_rule_each(self):
        base = MAKE("3.5")
        self.assertTrue(C.comparable(base, MAKE("3.5", key="a.b"), same_key=False))
        self.assertTrue(C.comparable(base, MAKE("3.5", level="city"), same_level=False))
        self.assertTrue(C.comparable(base, MAKE("3.5", provider="other_stats"), same_provider=False))
        self.assertFalse(C.comparable(base, MAKE("3.5", unit="명"), same_key=False, same_level=False, same_provider=False, same_period=False))

    def test_discard_wins_over_context_only_and_reasons_are_listed_in_order(self):
        result = C.comparable(MAKE("3.5"), MAKE("3.5", unit="명", key="labour.other"))
        self.assertEqual(result.verdict, C.DISCARD)
        self.assertEqual(result.reasons, ("UNIT_MISMATCH", "DEFINITION_MISMATCH"))

    def test_a_missing_as_of_cannot_be_compared(self):
        derived = F.DerivedFact.create("F08_mean", ("f" + "1" * 16,), "3", "%", as_of=None, key=MAKE("3").key, region_level="province", provider_id="mock_stats")
        result = C.comparable(MAKE("3"), derived)
        self.assertEqual(result.verdict, C.DISCARD)
        self.assertEqual(result.reasons[0], "AS_OF_MISSING")

    def test_a_derived_fact_is_comparable_with_a_fact_it_inherits_from(self):
        cur = MAKE("3.5")
        mean = C.f08_mean([MAKE("3.1", region="R02"), cur])
        self.assertTrue(C.comparable(cur, mean))


class Skip(unittest.TestCase):
    def assertSkipped(self, result, reason, formula_id):
        self.assertIsInstance(result, C.Skipped)
        self.assertFalse(result)
        self.assertEqual((result.formula_id, result.reason), (formula_id, reason))
        self.assertTrue(result.detail)
        self.assertNotIn(result.detail, ("", result.reason))


class F01ChangeTest(Skip):
    def test_the_difference_and_what_it_remembers(self):
        cur, prev = MAKE("3.5", period="2026-03"), MAKE("3.2", period="2026-02")
        result = C.f01_change(cur, prev)
        self.assertEqual((result.formula_id, result.value, result.unit), ("F01_change", Decimal("0.3"), "%p"))
        self.assertEqual((result.as_of, result.region, result.key, result.region_level), ("2026-03", "R01", cur.key, "province"))
        self.assertEqual(result.input_fact_ids, (cur.fact_id, prev.fact_id))
        self.assertEqual(F.validate_derived(result), [])

    def test_negative_difference_and_a_non_percent_unit(self):
        result = C.f01_change(MAKE("1000", unit="명", period="2026-03"), MAKE("1250", unit="명", period="2026-02"))
        self.assertEqual((result.value, result.unit), (Decimal("-250"), "명"))

    def test_adjacency_is_required_by_default(self):
        cur = MAKE("3.5", period="2026-03")
        self.assertSkipped(C.f01_change(cur, MAKE("3.2", period="2026-01")), "NOT_ADJACENT", "F01_change")
        self.assertSkipped(C.f01_change(cur, MAKE("3.2", period="2026-03")), "NOT_ADJACENT", "F01_change")
        self.assertSkipped(C.f01_change(cur, MAKE("3.2", period="2026-04")), "NOT_ADJACENT", "F01_change")
        self.assertIsInstance(C.f01_change(MAKE("3.5", period="2026-01"), MAKE("3.2", period="2025-12")), F.DerivedFact)      # 해를 넘어도 바로 앞 달
        self.assertIsInstance(C.f01_change(MAKE("3.5", period="2026-Q1"), MAKE("3.2", period="2025-Q4")), F.DerivedFact)
        self.assertIsInstance(C.f01_change(MAKE("3.5", period="2026"), MAKE("3.2", period="2025")), F.DerivedFact)

    def test_earlier_and_any(self):
        cur = MAKE("3.5", period="2026-03")
        self.assertIsInstance(C.f01_change(cur, MAKE("3.2", period="2025-03"), require="earlier"), F.DerivedFact)
        self.assertSkipped(C.f01_change(cur, MAKE("3.2", period="2026-03"), require="earlier"), "NOT_EARLIER", "F01_change")
        self.assertSkipped(C.f01_change(cur, MAKE("3.2", period="2026-04"), require="earlier"), "NOT_EARLIER", "F01_change")
        self.assertIsInstance(C.f01_change(cur, MAKE("3.2", period="2026-09"), require="any"), F.DerivedFact)

    def test_unknown_values_are_never_treated_as_zero(self):
        self.assertSkipped(C.f01_change(MAKE(None, period="2026-03"), MAKE("3.2", period="2026-02")), "MISSING_VALUE", "F01_change")
        self.assertSkipped(C.f01_change(MAKE("3.5", period="2026-03"), MAKE(None, period="2026-02")), "MISSING_VALUE", "F01_change")

    def test_incomparable_inputs_are_skipped_with_the_reason(self):
        cur = MAKE("3.5", period="2026-03")
        self.assertSkipped(C.f01_change(cur, MAKE("3.2", period="2026-02", unit="명")), "UNIT_MISMATCH", "F01_change")
        self.assertSkipped(C.f01_change(cur, MAKE("3.2", period="2026-02", key="labour.other")), "DEFINITION_MISMATCH", "F01_change")
        self.assertSkipped(C.f01_change(cur, MAKE("3.2", period="2026-02", provider="other_stats")), "PROVIDER_MISMATCH", "F01_change")
        self.assertSkipped(C.f01_change(cur, MAKE("3.2", period="2026-02", level="city")), "REGION_LEVEL_MISMATCH", "F01_change")
        self.assertSkipped(C.f01_change(cur, MAKE("3.2", period="2025-Q4")), "PERIOD_KIND_MISMATCH", "F01_change")
        self.assertSkipped(C.f01_change(cur, status_fact()), "NON_NUMERIC", "F01_change")

    def test_unit_mismatch_is_also_caught_by_the_arithmetic_guard(self):
        with self.assertRaises(F.UnitMismatch):
            F.require_same_unit(MAKE("1"), MAKE("1", unit="명"))


class F02PctChangeTest(Skip):
    def test_the_ratio_and_its_precision(self):
        result = C.f02_pct_change(MAKE("3.5", period="2026-03"), MAKE("3.2", period="2026-02"))
        self.assertEqual((result.value, result.unit, result.formula_id), (Decimal("9.375000000000"), "%", "F02_pct_change"))
        third = C.f02_pct_change(MAKE("1", period="2026-03"), MAKE("3", period="2026-02"))
        self.assertEqual(third.value, Decimal("-66.666666666667"))                      # 내부는 12자리 정밀값
        self.assertEqual(F.format_with_unit(third.value, third.unit), "−66.7%")           # 반올림은 보여 줄 때만

    def test_current_zero_is_a_real_value(self):
        self.assertEqual(C.f02_pct_change(MAKE("0", period="2026-03"), MAKE("4", period="2026-02")).value, Decimal("-100"))

    def test_division_by_zero_and_negative_base_make_no_value(self):
        cur = MAKE("3.5", period="2026-03")
        self.assertSkipped(C.f02_pct_change(cur, MAKE("0", period="2026-02")), "DIVISION_BY_ZERO", "F02_pct_change")
        self.assertSkipped(C.f02_pct_change(cur, MAKE("-1", period="2026-02")), "NEGATIVE_BASE", "F02_pct_change")
        self.assertSkipped(C.f02_pct_change(cur, MAKE(None, period="2026-02")), "MISSING_VALUE", "F02_pct_change")
        self.assertSkipped(C.f02_pct_change(cur, MAKE("3", period="2026-02", unit="명")), "UNIT_MISMATCH", "F02_pct_change")
        self.assertSkipped(C.f02_pct_change(cur, MAKE("3", period="2025-12")), "NOT_ADJACENT", "F02_pct_change")

    def test_any_and_earlier_relations(self):
        cur = MAKE("5", period="2026-03")
        self.assertEqual(C.f02_pct_change(cur, MAKE("4", period="2025-03"), require="earlier").value, Decimal("25"))
        self.assertEqual(C.f02_pct_change(cur, MAKE("4", period="2026-09"), require="any").value, Decimal("25"))


class F03YoyTest(Skip):
    def test_same_period_one_year_before(self):
        for cur, prior in (("2026-03", "2025-03"), ("2026-Q2", "2025-Q2"), ("2026", "2025"), ("2026-03-05", "2025-03-05")):
            with self.subTest(period=cur):
                result = C.f03_yoy(MAKE("110", period=cur), MAKE("100", period=prior))
                self.assertEqual((result.value, result.unit, result.formula_id), (Decimal("10"), "%", "F03_yoy"))
                self.assertEqual(result.as_of, cur)

    def test_other_gaps_are_not_a_year(self):
        cur = MAKE("110", period="2026-03")
        for prior in ("2025-02", "2025-04", "2024-03", "2026-03", "2025-12"):
            with self.subTest(prior=prior):
                self.assertSkipped(C.f03_yoy(cur, MAKE("100", period=prior)), "NOT_ONE_YEAR_APART", "F03_yoy")

    def test_instants_and_leap_days_have_no_year_before(self):
        self.assertSkipped(C.f03_yoy(MAKE("1", period="2026-03-05T09:30:00Z"), MAKE("1", period="2025-03-05T09:30:00Z")), "NOT_ONE_YEAR_APART", "F03_yoy")
        self.assertSkipped(C.f03_yoy(MAKE("1", period="2024-02-29"), MAKE("1", period="2023-02-28")), "NOT_ONE_YEAR_APART", "F03_yoy")

    def test_division_and_negative_base_and_missing(self):
        cur = MAKE("110", period="2026-03")
        self.assertSkipped(C.f03_yoy(cur, MAKE("0", period="2025-03")), "DIVISION_BY_ZERO", "F03_yoy")
        self.assertSkipped(C.f03_yoy(cur, MAKE("-5", period="2025-03")), "NEGATIVE_BASE", "F03_yoy")
        self.assertSkipped(C.f03_yoy(cur, MAKE(None, period="2025-03")), "MISSING_VALUE", "F03_yoy")
        self.assertSkipped(C.f03_yoy(cur, MAKE("100", period="2025-03", unit="명")), "UNIT_MISMATCH", "F03_yoy")


class F04RankTest(Skip):
    def group(self, values, **kw):
        return [MAKE(v, region=f"R{i:02d}", **kw) for i, v in enumerate(values, start=1)]

    def test_competition_ranking_with_ties(self):
        group = self.group(["5", "4", "4", "3", "1"])
        ranks = [C.f04_rank(f, group).value for f in group]
        self.assertEqual(ranks, [Decimal(r) for r in (1, 2, 2, 4, 5)])
        result = C.f04_rank(group[3], group)
        self.assertEqual((result.unit, result.formula_id, result.region, result.input_fact_ids[0]), ("위", "F04_rank", "R04", group[3].fact_id))
        self.assertEqual(set(result.input_fact_ids), {f.fact_id for f in group})
        self.assertEqual(F.format_with_unit(result.value, result.unit), "4위")

    def test_input_order_does_not_matter(self):
        group = self.group(["5", "4", "4", "3", "1"])
        self.assertEqual(C.f04_rank(group[2], group), C.f04_rank(group[2], list(reversed(group))))

    def test_guard_rails(self):
        group = self.group(["5", "4", "3"])
        self.assertSkipped(C.f04_rank(MAKE("9", region="R09"), group), "NOT_IN_GROUP", "F04_rank")
        self.assertSkipped(C.f04_rank(group[0], group[:1]), "TOO_FEW_INPUTS", "F04_rank")
        self.assertSkipped(C.f04_rank(group[0], group + [MAKE("2", region="R09", period="2026-02")]), "PERIOD_MISMATCH", "F04_rank")
        self.assertSkipped(C.f04_rank(group[0], group + [MAKE("2", region="R09", unit="명")]), "UNIT_MISMATCH", "F04_rank")
        self.assertSkipped(C.f04_rank(group[0], group + [MAKE(None, region="R09")]), "MISSING_VALUE", "F04_rank")
        self.assertSkipped(C.f04_rank(group[0], group + [MAKE("2", region="R09", key="labour.other")]), "DEFINITION_MISMATCH", "F04_rank")


class F05ShareTest(Skip):
    def test_part_over_total(self):
        part, total = MAKE("25", unit="명", key="population.region"), MAKE("100", unit="명", key="population.total", level="country")
        result = C.f05_share(part, total)
        self.assertEqual((result.value, result.unit, result.formula_id, result.key), (Decimal("25"), "%", "F05_share", "population.region"))
        self.assertEqual(C.f05_share(MAKE("100", unit="명"), MAKE("100", unit="명", key="population.total")).value, Decimal("100"))
        self.assertEqual(C.f05_share(MAKE("0", unit="명"), MAKE("100", unit="명", key="population.total")).value, Decimal("0"))

    def test_guard_rails(self):
        part = MAKE("25", unit="명", key="population.region")
        total = lambda value="100", **kw: MAKE(value, unit=kw.pop("unit", "명"), key="population.total", **kw)      # noqa: E731
        self.assertSkipped(C.f05_share(part, total("0")), "DIVISION_BY_ZERO", "F05_share")
        self.assertSkipped(C.f05_share(part, total("20")), "PART_EXCEEDS_TOTAL", "F05_share")
        self.assertSkipped(C.f05_share(part, total("-100")), "NEGATIVE_VALUE", "F05_share")
        self.assertSkipped(C.f05_share(MAKE("-5", unit="명"), total()), "NEGATIVE_VALUE", "F05_share")
        self.assertSkipped(C.f05_share(part, total(unit="가구")), "UNIT_MISMATCH", "F05_share")
        self.assertSkipped(C.f05_share(part, total(period="2026-02")), "PERIOD_MISMATCH", "F05_share")
        self.assertSkipped(C.f05_share(part, total(provider="other_stats")), "PROVIDER_MISMATCH", "F05_share")
        self.assertSkipped(C.f05_share(MAKE(None, unit="명"), total()), "MISSING_VALUE", "F05_share")


class MeansTest(Skip):
    def group(self, values, **kw):
        return [MAKE(v, region=f"R{i:02d}", **kw) for i, v in enumerate(values, start=1)]

    def test_mean_and_diff_from_mean(self):
        group = self.group(["3.5", "3.3", "2.9"])
        mean = C.f08_mean(group)
        self.assertEqual((mean.formula_id, mean.value, mean.unit, mean.region, mean.as_of), ("F08_mean", Decimal("3.233333333333"), "%", None, "2026-03"))
        self.assertEqual(set(mean.input_fact_ids), {f.fact_id for f in group})
        diff = C.f06_diff_from_mean(group[0], mean)
        self.assertEqual((diff.formula_id, diff.value, diff.unit, diff.region), ("F06_diff_from_mean", Decimal("0.266666666667"), "%p", "R01"))
        self.assertEqual(diff.input_fact_ids, (group[0].fact_id, mean.fact_id))
        self.assertEqual(F.format_with_unit(diff.value, diff.unit, signed=True), "+0.3%p")

    def test_the_mean_needs_two_and_comparable_members(self):
        group = self.group(["3.5", "3.3"])
        self.assertSkipped(C.f08_mean(group[:1]), "TOO_FEW_INPUTS", "F08_mean")
        self.assertSkipped(C.f08_mean(group + [MAKE(None, region="R09")]), "MISSING_VALUE", "F08_mean")
        self.assertSkipped(C.f08_mean(group + [MAKE("1", region="R09", period="2026-02")]), "PERIOD_MISMATCH", "F08_mean")
        self.assertSkipped(C.f08_mean(group + [MAKE("1", region="R09", unit="명")]), "UNIT_MISMATCH", "F08_mean")

    def test_diff_from_mean_accepts_only_a_mean_of_the_same_period_and_unit(self):
        group = self.group(["3.5", "3.3", "2.9"])
        self.assertSkipped(C.f06_diff_from_mean(group[0], group[1]), "NOT_A_MEAN", "F06_diff_from_mean")
        self.assertSkipped(C.f06_diff_from_mean(group[0], C.f03_yoy(MAKE("110", period="2026-03"), MAKE("100", period="2025-03"))), "NOT_A_MEAN", "F06_diff_from_mean")
        mean = C.f08_mean(group)
        self.assertSkipped(C.f06_diff_from_mean(MAKE("3.5", period="2026-02"), mean), "PERIOD_MISMATCH", "F06_diff_from_mean")
        self.assertSkipped(C.f06_diff_from_mean(MAKE("3.5", unit="명"), mean), "UNIT_MISMATCH", "F06_diff_from_mean")
        self.assertSkipped(C.f06_diff_from_mean(MAKE(None), mean), "MISSING_VALUE", "F06_diff_from_mean")

    def test_rolling_mean_is_chronological_and_feeds_diff_from_mean(self):
        window = months(["3.3", "3.2", "3.5"], start=(2026, 1))
        mean = C.f07_rolling_mean(list(reversed(window)))
        self.assertEqual((mean.formula_id, mean.value, mean.as_of, mean.region), ("F07_rolling_mean", Decimal("3.333333333333"), "2026-03", "R01"))
        self.assertEqual(mean.input_fact_ids, tuple(f.fact_id for f in window))
        diff = C.f06_diff_from_mean(window[-1], mean)
        self.assertEqual(diff.value, Decimal("0.166666666667"))

    def test_rolling_mean_needs_consecutive_periods_of_one_region(self):
        window = months(["3.3", "3.2", "3.5"], start=(2026, 1))
        self.assertSkipped(C.f07_rolling_mean(window[:1]), "TOO_FEW_INPUTS", "F07_rolling_mean")
        self.assertSkipped(C.f07_rolling_mean([window[0], window[2]]), "BAD_WINDOW", "F07_rolling_mean")
        self.assertSkipped(C.f07_rolling_mean([window[0], MAKE("9.9", period=window[0].as_of)]), "BAD_WINDOW", "F07_rolling_mean")      # 같은 기간의 서로 다른 값 둘
        self.assertSkipped(C.f07_rolling_mean([window[0], window[0]]), "DUPLICATE_INPUT", "F07_rolling_mean")                          # 같은 입력을 두 번
        self.assertSkipped(C.f07_rolling_mean(window[:2] + [MAKE("3", period="2026-03", region="R02")]), "REGION_MISMATCH", "F07_rolling_mean")
        self.assertSkipped(C.f07_rolling_mean(window[:2] + [MAKE(None, period="2026-03")]), "MISSING_VALUE", "F07_rolling_mean")
        self.assertSkipped(C.f07_rolling_mean(window[:2] + [MAKE("3", period="2026-03", unit="명")]), "UNIT_MISMATCH", "F07_rolling_mean")

    def test_median_odd_even_and_guards(self):
        odd = C.f14_median(self.group(["5", "1", "3"]))
        even = C.f14_median(self.group(["5", "1", "3", "4"]))
        self.assertEqual((odd.value, even.value, odd.formula_id, odd.region), (Decimal("3"), Decimal("3.5"), "F14_median", None))
        self.assertSkipped(C.f14_median(self.group(["5"])), "TOO_FEW_INPUTS", "F14_median")
        self.assertSkipped(C.f14_median(self.group(["5", "3"]) + [MAKE("1", region="R09", unit="명")]), "UNIT_MISMATCH", "F14_median")


class ExtremesTest(Skip):
    def test_max_and_min_remember_the_fact_that_has_the_value(self):
        series = months(["3.0", "3.4", "2.9", "3.4", "3.1"], start=(2025, 11))
        high, low = C.f09_max(series), C.f10_min(series)
        self.assertEqual((high.formula_id, high.value, high.as_of), ("F09_max", Decimal("3.4"), "2026-02"))       # 동률은 더 나중 기준일
        self.assertEqual((low.formula_id, low.value, low.as_of), ("F10_min", Decimal("2.9"), "2026-01"))
        self.assertEqual(high.input_fact_ids[0], series[3].fact_id)
        self.assertEqual(low.input_fact_ids[0], series[2].fact_id)
        self.assertEqual(set(high.input_fact_ids), {f.fact_id for f in series})

    def test_ties_across_regions_pick_the_first_region_name_and_ignore_input_order(self):
        group = [MAKE("4", region="R03"), MAKE("4", region="R01"), MAKE("4", region="R02"), MAKE("2", region="R04")]
        for order in (group, list(reversed(group)), [group[2], group[0], group[3], group[1]]):
            self.assertEqual(C.select_extreme(order).region, "R01")
            self.assertEqual(C.select_extreme(order, highest=False).region, "R04")
            self.assertEqual(C.f09_max(order), C.f09_max(group))

    def test_select_extreme_skips_unknown_values_and_handles_empty(self):
        self.assertIsNone(C.select_extreme([]))
        self.assertIsNone(C.select_extreme([MAKE(None)]))
        self.assertEqual(C.select_extreme([MAKE(None), MAKE("1", region="R02")]).region, "R02")

    def test_guards(self):
        self.assertSkipped(C.f09_max([]), "TOO_FEW_INPUTS", "F09_max")
        self.assertSkipped(C.f10_min([MAKE("1"), MAKE(None, region="R02")]), "MISSING_VALUE", "F10_min")
        self.assertSkipped(C.f09_max([MAKE("1"), MAKE("2", unit="명")]), "UNIT_MISMATCH", "F09_max")


class RangePositionTest(Skip):
    def test_position_between_low_and_high(self):
        series = months(["2.9", "3.0", "3.2", "3.5"], start=(2025, 9))
        self.assertEqual(C.f11_range_position(series[3], series).value, Decimal("100"))
        self.assertEqual(C.f11_range_position(series[0], series).value, Decimal("0"))
        mid = C.f11_range_position(series[2], series)
        self.assertEqual((mid.value, mid.unit, mid.formula_id, mid.input_fact_ids[0]), (Decimal("50"), "%", "F11_range_position", series[2].fact_id))

    def test_guards(self):
        series = months(["3.0", "3.0", "3.0"])
        self.assertSkipped(C.f11_range_position(series[0], series), "ZERO_RANGE", "F11_range_position")
        self.assertSkipped(C.f11_range_position(series[0], series[:1]), "TOO_FEW_INPUTS", "F11_range_position")
        self.assertSkipped(C.f11_range_position(MAKE("3", period="2030-01"), months(["1", "5"])), "NOT_IN_GROUP", "F11_range_position")
        self.assertSkipped(C.f11_range_position(series[0], series + [MAKE(None, period="2026-01")]), "MISSING_VALUE", "F11_range_position")


class CountAndGapTest(Skip):
    def test_count_takes_the_unit_and_counts_unknown_values_too(self):
        group = [MAKE("1", region="R01"), MAKE(None, region="R02"), MAKE("3", region="R03")]
        result = C.f12_count(group, "곳")
        self.assertEqual((result.formula_id, result.value, result.unit, result.as_of, result.region), ("F12_count", Decimal("3"), "곳", "2026-03", None))
        self.assertEqual(F.format_with_unit(result.value, result.unit), "3곳")
        self.assertSkipped(C.f12_count([], "곳"), "TOO_FEW_INPUTS", "F12_count")
        self.assertEqual(C.f12_count(months(["1", "2", "3"]), "개월").as_of, "2025-03")

    def test_gap_is_a_minus_b_for_the_same_period(self):
        result = C.f13_gap(MAKE("4.2", region="R05"), MAKE("2.7", region="R06"))
        self.assertEqual((result.formula_id, result.value, result.unit, result.region), ("F13_gap", Decimal("1.5"), "%p", None))
        self.assertEqual(C.f13_gap(MAKE("1", region="R05"), MAKE("3", region="R06")).value, Decimal("-2"))
        self.assertSkipped(C.f13_gap(MAKE("4.2"), MAKE("2.7", period="2026-02")), "PERIOD_MISMATCH", "F13_gap")
        self.assertSkipped(C.f13_gap(MAKE("4.2"), MAKE("2.7", unit="명")), "UNIT_MISMATCH", "F13_gap")
        self.assertSkipped(C.f13_gap(MAKE("4.2"), MAKE(None, region="R02")), "MISSING_VALUE", "F13_gap")

    def test_the_gap_works_between_a_mean_and_a_median(self):
        group = [MAKE(v, region=f"R{i}") for i, v in enumerate(["1", "2", "9"], start=1)]
        result = C.f13_gap(C.f08_mean(group), C.f14_median(group))
        self.assertEqual(result.value, Decimal("2"))


class RegistryOfFormulasTest(unittest.TestCase):
    def test_every_formula_function_is_registered_under_its_own_number(self):
        source = (ROOT / "pipeline" / "calc.py").read_text(encoding="utf-8")
        functions = set(re.findall(r"(?m)^def (f\d{2}_[a-z_]+)\(", source))
        self.assertEqual({fn.__name__ for fn in C.FORMULAS.values()}, functions)
        for formula_id, fn in C.FORMULAS.items():
            with self.subTest(formula=formula_id):
                self.assertRegex(formula_id, r"\AF\d{2}_[a-z_]+\Z")
                self.assertEqual(formula_id.lower(), fn.__name__)
        numbers = sorted(int(i[1:3]) for i in C.FORMULAS)
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))

    def test_reason_codes_in_the_source_all_have_a_text_and_every_text_is_used(self):
        source = (ROOT / "pipeline" / "calc.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertTrue(tree.body)
        referenced = {a or b for a, b in re.findall(r'_skip\(formula_id, "([A-Z_]+)"\)|reasons\.append\("([A-Z_]+)"\)', source)}
        self.assertGreater(len(referenced), 15)
        self.assertFalse(referenced - set(C.REASON_TEXT), "문구가 없는 사유 코드")
        for code in C.REASON_TEXT:
            with self.subTest(code=code):
                self.assertGreaterEqual(source.count(f'"{code}"'), 2, "쓰이지 않는 사유 문구")      # 문구 표에 한 번, 코드 어딘가에 한 번 이상
                self.assertTrue(C.REASON_TEXT[code].strip())
                self.assertFalse(re.search(r"\d", C.REASON_TEXT[code]), "사유 문구에 숫자가 있다")

    def test_formulas_return_the_formula_id_they_are_registered_under(self):
        a, b = MAKE("4", period="2026-03"), MAKE("2", period="2026-02")
        group = [MAKE("4", region="R01"), MAKE("2", region="R02"), MAKE("3", region="R03")]
        window = months(["1", "2", "3"])
        day_group = [MAKE(str(1 + step % 3), period=f"2026-03-05T{3 * step:02d}:00:00Z", region=None, level=None) for step in range(8)]          # S2a: 한 날 8구간
        season = [MAKE(str(value), period=f"{2020 + index}-10") for index, value in enumerate((3, 1, 2, 5))]          # S2c-1: 같은 달(10월)·서로 다른 해
        calls = {
            "F01_change": lambda: C.f01_change(a, b), "F02_pct_change": lambda: C.f02_pct_change(a, b),
            "F03_yoy": lambda: C.f03_yoy(a, MAKE("2", period="2025-03")), "F04_rank": lambda: C.f04_rank(group[0], group),
            "F05_share": lambda: C.f05_share(group[1], group[0]), "F06_diff_from_mean": lambda: C.f06_diff_from_mean(group[0], C.f08_mean(group)),
            "F07_rolling_mean": lambda: C.f07_rolling_mean(window), "F08_mean": lambda: C.f08_mean(group), "F09_max": lambda: C.f09_max(group),
            "F10_min": lambda: C.f10_min(group), "F11_range_position": lambda: C.f11_range_position(window[1], window), "F12_count": lambda: C.f12_count(group, "곳"),
            "F13_gap": lambda: C.f13_gap(group[0], group[1]), "F14_median": lambda: C.f14_median(group),
            "F15_day_max": lambda: C.f15_day_max(day_group, expected_count=8), "F16_count_between": lambda: C.f16_count_between(group, MAKE("3", region="R09"), None, "곳"),
            "F17_season_rank": lambda: C.f17_season_rank(season[0], season), "F18_last_lower": lambda: C.f18_last_lower(window[-1], window[:-1]),           # S2c-1
            "F19_months_between": lambda: C.f19_months_between(MAKE("4", period="2026-03"), MAKE("2", period="2025-11"))}
        self.assertEqual(set(calls), set(C.FORMULAS))
        for formula_id, call in calls.items():
            with self.subTest(formula=formula_id):
                result = call()
                self.assertIsInstance(result, F.DerivedFact)
                self.assertEqual(result.formula_id, formula_id)
                self.assertEqual(F.validate_derived(result), [])
                self.assertEqual(call(), result)                                    # 같은 입력이면 같은 결과(id 까지)


class DeterminismTest(unittest.TestCase):
    def test_results_do_not_depend_on_input_order(self):
        group = [MAKE(v, region=f"R{i}") for i, v in enumerate(["3.5", "3.3", "2.9", "3.8"], start=1)]
        for fn in (C.f08_mean, C.f09_max, C.f10_min, C.f14_median):
            with self.subTest(fn=fn.__name__):
                self.assertEqual(fn(group), fn(list(reversed(group))))
        self.assertEqual(C.f12_count(group, "곳"), C.f12_count(list(reversed(group)), "곳"))
        self.assertEqual(C.f11_range_position(group[0], group), C.f11_range_position(group[0], group[::-1]))

    def test_internal_precision_is_twelve_places_and_the_policy_lives_in_one_place(self):
        self.assertEqual(F.NUMBER_POLICY["internal_places"], 12)
        self.assertEqual(C.f08_mean([MAKE("1", region="R1"), MAKE("2", region="R2"), MAKE("2", region="R3")]).value, Decimal("1.666666666667"))
        source = (ROOT / "pipeline" / "calc.py").read_text(encoding="utf-8")
        self.assertNotIn("ROUND_HALF", source.replace("NUMBER_POLICY", ""), "반올림 방식은 facts.NUMBER_POLICY 한 곳에만 있다")
        self.assertNotIn("quantize(Decimal(1).scaleb(-1)", source)


if __name__ == "__main__":
    unittest.main()
