"""결정적 계산기 — 계산식마다 번호(`F01_change` …)와 순수 함수. 표준 라이브러리만, 입출력·시계·난수 없음.

입력은 Fact(또는 다른 계산 결과 DerivedFact), 출력은 `DerivedFact`(입력 id 와 식 번호를 기록) 또는 `Skipped`(값을 만들지 않고 이유를 돌려준다).
**AI 는 계산하지 않는다.** 같은 입력이면 같은 결과다. 반올림은 이 모듈이 아니라 `facts.NUMBER_POLICY` 한 곳에 못박혀 있다 — 계산은 정밀값(Decimal, 12자리)으로 하고
글로 쓸 때만 반올림한다.

값이 없는(모름) 입력은 0 으로 채우지 않고 `Skipped("MISSING_VALUE")` 다. 단위가 다르면 계산하지 않고(`UNIT_MISMATCH`), 기준일·정의·지역 수준이 달라도
견주지 않는다(`comparable`). 0 으로 나누기·음수 기준값·기간 어긋남도 값을 만들지 않는다.

| 번호 | 함수 | 뜻 |
|---|---|---|
| F01_change | f01_change | 현재 − 기준(차이). 퍼센트끼리의 차이는 퍼센트포인트(`%p`) |
| F02_pct_change | f02_pct_change | (현재 − 기준) ÷ 기준 × 100 (기준이 0 이하면 안 만든다) |
| F03_yoy | f03_yoy | 정확히 한 해 전 같은 기간 대비 변화율 |
| F04_rank | f04_rank | 같은 기준일·같은 지표의 묶음 안 순위(1 = 가장 높음, 동률은 같은 순위) |
| F05_share | f05_share | 부분 ÷ 전체 × 100 |
| F06_diff_from_mean | f06_diff_from_mean | 값 − 평균(F08 이나 F07 의 결과) |
| F07_rolling_mean | f07_rolling_mean | 연속한 기간의 평균(이동평균) |
| F08_mean | f08_mean | 같은 기준일·같은 지표 묶음의 평균 |
| F09_max | f09_max | 묶음의 최댓값(값·기준일·지역은 그 값을 가진 Fact 의 것) |
| F10_min | f10_min | 묶음의 최솟값 |
| F11_range_position | f11_range_position | (현재 − 최저) ÷ (최고 − 최저) × 100 (자료 기간 안의 위치) |
| F12_count | f12_count | 묶음의 개수(세는 단위는 인자) |
| F13_gap | f13_gap | 같은 기준일 두 값의 차이(a − b: 최고 − 최저 같은 격차, 평균 − 중앙값) |
| F14_median | f14_median | 같은 기준일·같은 지표 묶음의 중앙값(짝수 개면 가운데 둘의 평균) |

설명: docs/FACT_PATH.md
"""
from dataclasses import dataclass
from decimal import Decimal

from pipeline import facts as F

COMPARABLE = "COMPARABLE"
CONTEXT_ONLY = "CONTEXT_ONLY"     # 참고로만 언급할 수 있다(같은 숫자 줄에 놓고 견주지 않는다)
DISCARD = "DISCARD"               # 버린다

REASON_TEXT = {
    "MISSING_VALUE": "값이 없어(모름) 계산하지 않음",
    "NON_NUMERIC": "숫자 종류가 아니라 계산하지 않음",
    "UNIT_MISMATCH": "단위가 달라 계산하지 않음",
    "DEFINITION_MISMATCH": "지표 정의(key)가 달라 견주지 않음",
    "PERIOD_MISMATCH": "기준일이 달라 견주지 않음",
    "PERIOD_KIND_MISMATCH": "기간 단위(월·분기·연)가 달라 견주지 않음",
    "REGION_LEVEL_MISMATCH": "지역 수준이 달라 견주지 않음",
    "PROVIDER_MISMATCH": "제공처가 달라 견주지 않음",
    "AS_OF_MISSING": "기준일이 없거나 읽을 수 없어 계산하지 않음",
    "DIVISION_BY_ZERO": "영으로 나눌 수 없어 계산하지 않음",
    "NEGATIVE_BASE": "기준값이 음수라 비율 변화를 계산하지 않음",
    "NEGATIVE_VALUE": "음수 값이 있어 비중을 계산하지 않음",
    "PART_EXCEEDS_TOTAL": "부분이 전체보다 커서 비중을 계산하지 않음",
    "NOT_ADJACENT": "바로 앞 기간이 아니라 계산하지 않음",
    "NOT_EARLIER": "기준이 현재보다 앞선 기간이 아니라 계산하지 않음",
    "NOT_ONE_YEAR_APART": "전년 같은 기간이 아니라 계산하지 않음",
    "TOO_FEW_INPUTS": "입력이 모자라 계산하지 않음",
    "NOT_IN_GROUP": "대상이 묶음 안에 없어 계산하지 않음",
    "ZERO_RANGE": "최고와 최저가 같아 위치를 계산하지 않음",
    "BAD_WINDOW": "연속한 기간이 아니라 이동평균을 계산하지 않음",
    "NOT_A_MEAN": "평균 계산 결과가 아니라 계산하지 않음",
    "REGION_MISMATCH": "지역이 달라 계산하지 않음",
    "DUPLICATE_INPUT": "같은 입력이 두 번 들어 있어 계산하지 않음",
    "NOT_A_RATIO_SCALE": "기준점이 임의인 척도(섭씨 같은 구간척도)나 순위라 변화율을 계산하지 않음",
    "VALUE_OUT_OF_RANGE": "계산 결과가 다룰 수 있는 범위를 넘어 계산하지 않음",
}
DISCARD_REASONS = frozenset({"MISSING_VALUE", "NON_NUMERIC", "UNIT_MISMATCH", "AS_OF_MISSING"})


@dataclass(frozen=True)
class Comparability:
    """`comparable()` 의 판정. verdict 는 COMPARABLE·CONTEXT_ONLY·DISCARD, reasons 는 사유 코드(앞이 가장 먼저 걸린 것). 참이면 비교 가능."""
    verdict: str
    reasons: tuple = ()

    @property
    def ok(self):
        return self.verdict == COMPARABLE

    def __bool__(self):
        return self.ok


@dataclass(frozen=True)
class Skipped:
    """값을 만들지 않은 계산식의 결과. 거짓으로 읽힌다(`if not result`)."""
    formula_id: str
    reason: str
    detail: str = ""

    def __bool__(self):
        return False


def _numeric(obj):
    return isinstance(obj, F.DerivedFact) or (isinstance(obj, F.Fact) and obj.kind in F.NUMERIC_KINDS)


def comparable(a, b, *, same_period=True, same_key=True, same_level=True, same_provider=True):
    """두 값을 견줄 수 있는가: 단위·정의(key)·기간(기준일)·지역 수준(·제공처)이 같아야 COMPARABLE.
    단위가 다르거나 값이 없거나 숫자가 아니면 DISCARD, 정의·기간·지역 수준·제공처만 다르면 CONTEXT_ONLY(참고로만 언급). `same_period=False` 는 시계열의 서로 다른 기간을 견주는 식이 쓴다
    (그래도 기간 단위(월·분기·연)는 같아야 한다). 사유 코드는 `REASON_TEXT` 에 뜻이 있다."""
    reasons = []
    for obj in (a, b):
        if not _numeric(obj):
            reasons.append("NON_NUMERIC")
        elif obj.value is None:
            reasons.append("MISSING_VALUE")
    if not reasons:
        if a.unit != b.unit:
            reasons.append("UNIT_MISMATCH")
        period_a, period_b = F.parse_as_of(a.as_of), F.parse_as_of(b.as_of)
        if period_a is None or period_b is None:
            reasons.append("AS_OF_MISSING")
        elif period_a.granularity != period_b.granularity:
            reasons.append("PERIOD_KIND_MISMATCH")
        elif same_period and period_a.ordinal != period_b.ordinal:
            reasons.append("PERIOD_MISMATCH")
        if same_key and getattr(a, "key", None) != getattr(b, "key", None):
            reasons.append("DEFINITION_MISMATCH")
        if same_level and getattr(a, "region_level", None) != getattr(b, "region_level", None):
            reasons.append("REGION_LEVEL_MISMATCH")
        if same_provider and getattr(a, "provider_id", None) != getattr(b, "provider_id", None):
            reasons.append("PROVIDER_MISMATCH")
    if not reasons:
        return Comparability(COMPARABLE)
    verdict = DISCARD if any(r in DISCARD_REASONS for r in reasons) else CONTEXT_ONLY
    return Comparability(verdict, tuple(reasons))


def _skip(formula_id, reason):
    return Skipped(formula_id, reason, REASON_TEXT.get(reason, reason))


def _pair(formula_id, a, b, **flags):
    verdict = comparable(a, b, **flags)
    if verdict.ok:
        return None
    return _skip(formula_id, verdict.reasons[0])


def _same_region(formula_id, a, b):
    """시간 비교(차이·변화율)는 같은 지역의 두 기간이어야 한다 — 서울 3월에서 부산 2월을 뺀 값을 만들지 않는다(L-04)."""
    if a.region != b.region:
        return _skip(formula_id, "REGION_MISMATCH")
    return None


# 계산은 모두 `facts.exact`(명시한 지역 문맥) 안에서 한다 — 호출한 쪽의 decimal 전역 정밀도·반올림·지수 한계에 기대지 않는다(재검증 D5, D-150)
@F.exact
def _quant(value):
    places = F.NUMBER_POLICY["internal_places"]
    return value.quantize(Decimal(1).scaleb(-places), rounding=F.NUMBER_POLICY["internal_rounding"])


@F.exact
def _div(numerator, denominator):
    return _quant(numerator / denominator)


@F.exact
def _mean(values):
    return _quant(sum(values, Decimal(0)) / Decimal(len(values)))


def _common_provider(items):
    ids = {getattr(item, "provider_id", None) for item in items}
    return next(iter(ids)) if len(ids) == 1 else None


_KEEP = object()    # `_derive` 의 칸을 anchor 에서 이어받는다는 표지(None 으로 비우는 것과 구별)


@F.exact
def _derive(formula_id, inputs, value, unit, anchor, *, as_of=_KEEP, region=_KEEP, key=_KEEP, region_level=_KEEP):
    quantized = _quant(value)
    if quantized.copy_abs() >= F.NUMBER_POLICY["max_abs_value"]:
        return _skip(formula_id, "VALUE_OUT_OF_RANGE")            # 값은 정상 범위여도 차이·변화율이 범위를 넘을 수 있다 — 예외로 죽지 않고 값을 만들지 않는다(D-137)
    return F.DerivedFact.create(
        formula_id, tuple(item.fact_id for item in inputs), quantized, unit,
        as_of=anchor.as_of if as_of is _KEEP else as_of,
        region=anchor.region if region is _KEEP else region,
        key=getattr(anchor, "key", None) if key is _KEEP else key,
        region_level=getattr(anchor, "region_level", None) if region_level is _KEEP else region_level,
        provider_id=_common_provider(inputs))


def _relation(formula_id, cur, ref, require):
    """현재와 기준의 기간 관계: adjacent(바로 앞 기간)·earlier(앞선 기간)·any(순서 무관)."""
    if require == "any":
        return None
    period_cur, period_ref = F.parse_as_of(cur.as_of), F.parse_as_of(ref.as_of)
    if period_cur.granularity != period_ref.granularity:
        return _skip(formula_id, "PERIOD_KIND_MISMATCH")
    if require == "adjacent":
        if period_cur.granularity == "instant" or period_ref.ordinal != period_cur.ordinal - 1:
            return _skip(formula_id, "NOT_ADJACENT")
        return None
    if period_ref.ordinal >= period_cur.ordinal:
        return _skip(formula_id, "NOT_EARLIER")
    return None


@F.exact
def f01_change(cur, ref, *, require="adjacent"):
    """현재 − 기준. require: adjacent(기본, 바로 앞 기간)·earlier(앞선 기간)·any."""
    formula_id = "F01_change"
    problem = _pair(formula_id, cur, ref, same_period=False)
    if problem is None:
        problem = _same_region(formula_id, cur, ref)
    if problem is None:
        problem = _relation(formula_id, cur, ref, require)
    if problem is not None:
        return problem
    F.require_same_unit(cur, ref)
    return _derive(formula_id, (cur, ref), cur.value - ref.value, F.diff_unit(cur.unit), cur)


@F.exact
def f02_pct_change(cur, ref, *, require="adjacent"):
    """(현재 − 기준) ÷ 기준 × 100. 기준이 0 이면 DIVISION_BY_ZERO, 음수면 NEGATIVE_BASE."""
    formula_id = "F02_pct_change"
    problem = _pair(formula_id, cur, ref, same_period=False)
    if problem is None:
        problem = _same_region(formula_id, cur, ref)
    if problem is None:
        problem = _relation(formula_id, cur, ref, require)
    if problem is not None:
        return problem
    F.require_same_unit(cur, ref)
    if not F.ratio_ok(cur.unit):
        return _skip(formula_id, "NOT_A_RATIO_SCALE")
    if ref.value == 0:
        return _skip(formula_id, "DIVISION_BY_ZERO")
    if ref.value < 0:
        return _skip(formula_id, "NEGATIVE_BASE")
    return _derive(formula_id, (cur, ref), _div((cur.value - ref.value) * 100, ref.value), "%", cur)


@F.exact
def f03_yoy(cur, prior):
    """전년 같은 기간 대비 변화율(%). prior 의 기준일이 정확히 한 해 전 같은 기간이어야 한다."""
    formula_id = "F03_yoy"
    problem = _pair(formula_id, cur, prior, same_period=False)
    if problem is None:
        problem = _same_region(formula_id, cur, prior)
    if problem is not None:
        return problem
    if F.parse_as_of(cur.as_of).granularity == "instant" or F.shift_year(cur.as_of, -1) != prior.as_of:
        return _skip(formula_id, "NOT_ONE_YEAR_APART")
    F.require_same_unit(cur, prior)
    if not F.ratio_ok(cur.unit):
        return _skip(formula_id, "NOT_A_RATIO_SCALE")
    if prior.value == 0:
        return _skip(formula_id, "DIVISION_BY_ZERO")
    if prior.value < 0:
        return _skip(formula_id, "NEGATIVE_BASE")
    return _derive(formula_id, (cur, prior), _div((cur.value - prior.value) * 100, prior.value), "%", cur)


def _group_problem(formula_id, group, *, same_period=True, min_size=1):
    """묶음 전체가 서로 견줄 수 있는지(첫 항목 기준). 문제가 있으면 Skipped, 없으면 None. 같은 입력이 두 번 들어 있어도 계산하지 않는다."""
    members = list(group)
    if len(members) < min_size:
        return _skip(formula_id, "TOO_FEW_INPUTS")
    if len({item.fact_id for item in members}) != len(members):
        return _skip(formula_id, "DUPLICATE_INPUT")
    first = sorted(members, key=lambda item: item.fact_id)[0]
    for other in members:
        verdict = comparable(first, other, same_period=same_period)
        if not verdict.ok:
            return _skip(formula_id, verdict.reasons[0])
    return None


def _ordered_ids(group):
    return sorted(item.fact_id for item in group)


@F.exact
def f04_rank(fact, group):
    """묶음 안의 순위(1 = 가장 높은 값, 동률은 같은 순위·다음 순위는 건너뜀). 대상은 묶음 안에 있어야 하고 묶음은 둘 이상이어야 한다."""
    formula_id = "F04_rank"
    members = list(group)
    problem = _group_problem(formula_id, members, min_size=2)
    if problem is not None:
        return problem
    if fact.fact_id not in {m.fact_id for m in members}:
        return _skip(formula_id, "NOT_IN_GROUP")
    rank = 1 + sum(1 for m in members if m.value > fact.value)
    inputs = (fact.fact_id,) + tuple(i for i in _ordered_ids(members) if i != fact.fact_id)
    return F.DerivedFact.create(formula_id, inputs, Decimal(rank), "위", as_of=fact.as_of, region=fact.region, key=getattr(fact, "key", None),
                                region_level=getattr(fact, "region_level", None), provider_id=_common_provider(members))


@F.exact
def f05_share(part, total):
    """부분 ÷ 전체 × 100(%). 같은 단위·같은 기준일. 전체가 0 이면 DIVISION_BY_ZERO, 음수가 있으면 NEGATIVE_VALUE, 부분이 전체보다 크면 PART_EXCEEDS_TOTAL."""
    formula_id = "F05_share"
    problem = _pair(formula_id, part, total, same_key=False, same_level=False)
    if problem is not None:
        return problem
    F.require_same_unit(part, total)
    if not F.ratio_ok(part.unit):
        return _skip(formula_id, "NOT_A_RATIO_SCALE")
    if total.value == 0:
        return _skip(formula_id, "DIVISION_BY_ZERO")
    if total.value < 0 or part.value < 0:
        return _skip(formula_id, "NEGATIVE_VALUE")
    if part.value > total.value:
        return _skip(formula_id, "PART_EXCEEDS_TOTAL")
    return _derive(formula_id, (part, total), _div(part.value * 100, total.value), "%", part)


@F.exact
def f08_mean(group):
    """같은 기준일·같은 지표 묶음의 평균(두 개 이상)."""
    formula_id = "F08_mean"
    members = list(group)
    problem = _group_problem(formula_id, members, min_size=2)
    if problem is not None:
        return problem
    anchor = sorted(members, key=lambda item: item.fact_id)[0]
    return F.DerivedFact.create(
        formula_id, tuple(_ordered_ids(members)), _mean([m.value for m in members]), anchor.unit, as_of=anchor.as_of, region=None,
        key=getattr(anchor, "key", None), region_level=getattr(anchor, "region_level", None), provider_id=_common_provider(members))


@F.exact
def f06_diff_from_mean(fact, mean):
    """값 − 평균. mean 은 F08(같은 기준일 묶음)이나 F07(이동평균)의 결과여야 하고 같은 단위·같은 기준일·같은 지표여야 한다."""
    formula_id = "F06_diff_from_mean"
    if not isinstance(mean, F.DerivedFact) or mean.formula_id not in ("F08_mean", "F07_rolling_mean"):
        return _skip(formula_id, "NOT_A_MEAN")
    problem = _pair(formula_id, fact, mean, same_level=False)
    if problem is not None:
        return problem
    F.require_same_unit(fact, mean)
    return _derive(formula_id, (fact, mean), fact.value - mean.value, F.diff_unit(fact.unit), fact)


@F.exact
def f07_rolling_mean(window):
    """연속한 기간의 평균(두 기간 이상). 같은 지표·같은 지역·같은 단위여야 하고 기간이 빠짐없이 이어져야 한다. 결과의 기준일은 가장 나중 기간."""
    formula_id = "F07_rolling_mean"
    members = list(window)
    problem = _group_problem(formula_id, members, same_period=False, min_size=2)
    if problem is not None:
        return problem
    if len({m.region for m in members}) != 1:
        return _skip(formula_id, "REGION_MISMATCH")
    ordered = sorted(members, key=lambda m: F.parse_as_of(m.as_of).ordinal)
    ordinals = [F.parse_as_of(m.as_of).ordinal for m in ordered]
    if F.parse_as_of(ordered[0].as_of).granularity == "instant" or any(b - a != 1 for a, b in zip(ordinals, ordinals[1:])):
        return _skip(formula_id, "BAD_WINDOW")
    latest = ordered[-1]
    return F.DerivedFact.create(
        formula_id, tuple(m.fact_id for m in ordered), _mean([m.value for m in ordered]), latest.unit, as_of=latest.as_of, region=latest.region,
        key=latest.key, region_level=latest.region_level, provider_id=_common_provider(ordered))


def _rank_key_high(item):
    period = F.parse_as_of(item.as_of)
    return (item.value.copy_negate(), -(period.ordinal if period else 0), item.region or "", item.fact_id)       # 단항 `-` 는 전역 정밀도로 반올림되므로 copy_negate(D5)


def _rank_key_low(item):
    period = F.parse_as_of(item.as_of)
    return (item.value, -(period.ordinal if period else 0), item.region or "", item.fact_id)


@F.exact
def select_extreme(group, *, highest=True):
    """묶음에서 가장 높은(낮은) Fact 하나. 동률이면 더 나중 기준일, 그다음 지역 이름, 그다음 id 순 — 같은 입력이면 항상 같은 Fact 다."""
    members = [m for m in group if _numeric(m) and m.value is not None]
    if not members:
        return None
    return sorted(members, key=_rank_key_high if highest else _rank_key_low)[0]


@F.exact
def _extreme(formula_id, group, highest):
    members = list(group)
    problem = _group_problem(formula_id, members, same_period=False)
    if problem is not None:
        return problem
    chosen = select_extreme(members, highest=highest)
    inputs = (chosen.fact_id,) + tuple(i for i in _ordered_ids(members) if i != chosen.fact_id)
    return F.DerivedFact.create(formula_id, inputs, chosen.value, chosen.unit, as_of=chosen.as_of, region=chosen.region, key=getattr(chosen, "key", None),
                                region_level=getattr(chosen, "region_level", None), provider_id=_common_provider(members))


@F.exact
def f09_max(group):
    """묶음의 최댓값. 결과의 기준일·지역은 그 값을 가진 Fact 의 것이다(입력 id 의 첫째가 그 Fact)."""
    return _extreme("F09_max", group, True)


@F.exact
def f10_min(group):
    """묶음의 최솟값(f09 와 같은 규칙)."""
    return _extreme("F10_min", group, False)


@F.exact
def f11_range_position(cur, group):
    """(현재 − 최저) ÷ (최고 − 최저) × 100(%). 현재가 묶음 안에 있어야 하고 최고와 최저가 달라야 한다(ZERO_RANGE). 0 은 최저, 100 은 최고."""
    formula_id = "F11_range_position"
    members = list(group)
    problem = _group_problem(formula_id, members, same_period=False, min_size=2)
    if problem is not None:
        return problem
    if cur.fact_id not in {m.fact_id for m in members}:
        return _skip(formula_id, "NOT_IN_GROUP")
    high, low = max(m.value for m in members), min(m.value for m in members)
    if high == low:
        return _skip(formula_id, "ZERO_RANGE")
    inputs = (cur.fact_id,) + tuple(i for i in _ordered_ids(members) if i != cur.fact_id)
    return F.DerivedFact.create(formula_id, inputs, _div((cur.value - low) * 100, high - low), "%", as_of=cur.as_of, region=cur.region, key=cur.key,
                                region_level=cur.region_level, provider_id=_common_provider(members))


@F.exact
def f12_count(group, unit):
    """묶음의 개수(한 개 이상). unit 은 세는 단위('곳'·'개월' 같은 우리 낱말). 모두 값이 있어야 하는 것은 아니다 — 센다."""
    formula_id = "F12_count"
    members = list(group)
    if not members:
        return _skip(formula_id, "TOO_FEW_INPUTS")
    periods = [F.parse_as_of(m.as_of) for m in members]
    latest = None
    if all(p is not None for p in periods):
        latest = max(zip(periods, members), key=lambda pair: (pair[0].ordinal, pair[1].fact_id))[1]
    keys = {getattr(m, "key", None) for m in members}
    return F.DerivedFact.create(
        formula_id, tuple(_ordered_ids(members)), Decimal(len(members)), unit, as_of=latest.as_of if latest else None, region=None,
        key=next(iter(keys)) if len(keys) == 1 else None, region_level=None, provider_id=_common_provider(members))


@F.exact
def f13_gap(a, b):
    """같은 기준일 두 값의 차이(a − b). 같은 지표·같은 단위·같은 기준일이어야 한다(최고 − 최저, 평균 − 중앙값 같은 격차)."""
    formula_id = "F13_gap"
    problem = _pair(formula_id, a, b, same_level=False)
    if problem is not None:
        return problem
    F.require_same_unit(a, b)
    return _derive(formula_id, (a, b), a.value - b.value, F.diff_unit(a.unit), a, region=None)


@F.exact
def f14_median(group):
    """같은 기준일·같은 지표 묶음의 중앙값(둘 이상). 짝수 개면 가운데 둘의 평균."""
    formula_id = "F14_median"
    members = list(group)
    problem = _group_problem(formula_id, members, min_size=2)
    if problem is not None:
        return problem
    values = sorted(m.value for m in members)
    middle = len(values) // 2
    value = values[middle] if len(values) % 2 else _mean([values[middle - 1], values[middle]])
    anchor = sorted(members, key=lambda item: item.fact_id)[0]
    return F.DerivedFact.create(
        formula_id, tuple(_ordered_ids(members)), value, anchor.unit, as_of=anchor.as_of, region=None, key=getattr(anchor, "key", None),
        region_level=getattr(anchor, "region_level", None), provider_id=_common_provider(members))


# 근거 텍스트에 쓰는 계산식 이름(숫자 없는 우리 낱말 — 계산식 번호 `F01` 의 숫자가 근거 숫자로 세어지지 않게 번호 대신 이 이름을 쓴다, D-131)
FORMULA_LABELS = {
    "F01_change": "증감", "F02_pct_change": "변화율", "F03_yoy": "전년 같은 기간 대비 변화율", "F04_rank": "순위", "F05_share": "비중",
    "F06_diff_from_mean": "평균과의 차이", "F07_rolling_mean": "이동평균", "F08_mean": "평균", "F09_max": "최댓값", "F10_min": "최솟값",
    "F11_range_position": "범위 안의 위치", "F12_count": "개수", "F13_gap": "격차", "F14_median": "중앙값",
}

FORMULAS = {
    "F01_change": f01_change,
    "F02_pct_change": f02_pct_change,
    "F03_yoy": f03_yoy,
    "F04_rank": f04_rank,
    "F05_share": f05_share,
    "F06_diff_from_mean": f06_diff_from_mean,
    "F07_rolling_mean": f07_rolling_mean,
    "F08_mean": f08_mean,
    "F09_max": f09_max,
    "F10_min": f10_min,
    "F11_range_position": f11_range_position,
    "F12_count": f12_count,
    "F13_gap": f13_gap,
    "F14_median": f14_median,
}
