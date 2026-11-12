"""퍼징과 독립 오라클(S2a): 가상 응답을 무작위로 만들고(고정 시드) 형식·값·결측·순서·중복·시각을 망가뜨려 어댑터에 넣고, 읽힌 Fact 는 상태·단위·기준값·값을 다시 망가뜨려 새 틀에 넣는다.
**어떤 입력에서도** 예외는 `AdapterError` 뿐이고 글이 나오면 모든 숫자가 Fact·계산에서 왔고(`untraced_numbers`·`traceable_numbers`)·금지 표현 0·조사 규칙 위반 0·제목에 값 없음·같은 입력이면 같은 글이며,
글이 나온 경우 표의 값과 개수는 **독립 오라클**(응답 JSON 에서 일반 파이썬으로 직접 센 값)과 같다. 예상 밖 사유 코드(`INTERNAL_ERROR`·`PLAN_ERROR`·`RENDER_ERROR`·`QUALITY_CHECK_FAILED` 등)는 0 이다.
시험은 `SPACE_FUZZ_CASES`(기본 240)건을 돌리고 구현자 점검 도구는 같은 함수를 수천 건으로 돌린다. 네트워크·시계 없이 돈다."""
import copy
import datetime
import json
import os
import random
import re
import unittest
from decimal import Decimal

import _bootstrap  # noqa: F401
import space_helpers as H
import test_space_recipes as TR

from pipeline import fact_assembler as A
from pipeline import facts as F
from pipeline import recipes as R
from pipeline import recipes_noregion as RN
from pipeline.adapters import base as B
from pipeline.adapters import noaa_swpc as N

CASES = int(os.environ.get("SPACE_FUZZ_CASES", "240"))
SEED = int(os.environ.get("SPACE_FUZZ_SEED", "20261110"))
ADAPTER_CODES = {"BAD_SHAPE", "BAD_JSON", "BAD_ENCODING", "DUPLICATE_ROW", "TOO_MANY_ROWS", "TOO_LARGE"}
UNEXPECTED = {"INTERNAL_ERROR", "PLAN_ERROR", "RENDER_ERROR", "TEMPLATE_UNTRACED", "QUALITY_CHECK_FAILED", "INVALID_FACTS", "MISSING_RECORD", "SOURCE_INFO_INVALID", "PROVIDER_NOT_ACTIVE", "BAD_TODAY",
              "TITLE_HAS_VALUE", "ATTRIBUTION_TEMPLATE_INVALID", "READER_NOTE_UNSAFE", "VALUE_OUT_OF_RANGE", "PRECISION_LIMIT"}
RECIPES_FOR = {"kp_estimated": ("R04_NOREGION_SERIES", "R05_THRESHOLD_COUNT"), "kp_outlook": ("R04_NOREGION_SERIES", "R05_THRESHOLD_COUNT"), "ssn_daily": ("R04_NOREGION_SERIES",),
               "ssn_monthly": ("R04_NOREGION_SERIES",), "xray_flares": ("R05_THRESHOLD_COUNT",), "scales": ("R06_SCALE_OUTLOOK",)}
KEY_FOR = {("R04_NOREGION_SERIES", "kp_estimated"): RN.KEY_KP, ("R05_THRESHOLD_COUNT", "kp_estimated"): RN.KEY_KP, ("R04_NOREGION_SERIES", "kp_outlook"): RN.KEY_KP, ("R05_THRESHOLD_COUNT", "kp_outlook"): RN.KEY_KP,
           ("R04_NOREGION_SERIES", "ssn_daily"): RN.KEY_SSN_DAILY, ("R04_NOREGION_SERIES", "ssn_monthly"): RN.KEY_SSN_MONTHLY, ("R05_THRESHOLD_COUNT", "xray_flares"): RN.KEY_FLARE_FLUX,
           ("R06_SCALE_OUTLOOK", "scales"): None}


# ----------------------------------------------------------------------------
# 입력 만들기
# ----------------------------------------------------------------------------
def random_flare_events(rng, count):
    stamps = set()
    while len(stamps) < count:
        stamp = datetime.datetime(2026, 11, 3, 2, 0) + datetime.timedelta(minutes=rng.randint(0, 6 * 24 * 60 + 18 * 60))
        stamps.add(stamp.strftime("%Y-%m-%dT%H:%M:00Z"))
    events = []
    for stamp in sorted(stamps):
        letter = rng.choices("ABCMX", weights=(1, 4, 8, 2, 1))[0]
        mantissa = rng.choice(("1.0", "1.2", "2.5", "4.8", "7.7", "9.9")) if letter != "X" else rng.choice(("1.0", "1.5", "10.0"))
        events.append((stamp, letter + mantissa))
    return events


def random_payload(rng):
    product = rng.choice(list(H.FIXTURE_FILES))
    if product == "kp_estimated":
        days = rng.randint(1, 10)
        value = H.kp_rows("2026-11-0%d" % rng.randint(1, 3), days, seed=rng.randint(1, 10 ** 6), storm_days=tuple(rng.sample(range(days), rng.randint(0, min(3, days)))),
                          partial_last=rng.choice((0, 0, 0, rng.randint(1, 7))))
    elif product == "kp_outlook":
        days = rng.randint(1, 7)
        value = H.kp_rows("2026-11-0%d" % rng.randint(1, 3), days, seed=rng.randint(1, 10 ** 6), storm_days=tuple(rng.sample(range(days), rng.randint(0, min(2, days)))), keys="outlook")
        base = datetime.datetime(2026, 11, 10, 0, 0)
        for step in range(rng.randint(0, 9)):
            stamp = (base + datetime.timedelta(hours=3 * step)).strftime("%Y-%m-%dT%H:%M:00")
            value.append({"time_tag": stamp, "kp": round(rng.randint(0, 20) / 3, 2), "observed": "estimated" if step < 3 else "predicted", "noaa_scale": rng.choice((None, None, "G1", "G2"))})
    elif product == "scales":
        value = H.scales_object(date_now="2026-11-1%d" % rng.randint(0, 1), g_now=str(rng.randint(0, 3)), g_forecast=tuple(str(rng.randint(0, 3)) for _ in range(3)),
                                probs={str(day): (str(rng.randint(0, 100)), str(rng.randint(0, 100)), str(rng.randint(0, 100))) for day in (1, 2, 3)})
    elif product == "ssn_daily":
        count = rng.randint(3, 120)
        value = H.ssn_daily_rows("2026-11-0%d" % rng.randint(1, 9), count, gaps=tuple(rng.sample(range(count), rng.randint(0, min(5, count - 1)))), seed=rng.randint(1, 10 ** 6))
    elif product == "ssn_monthly":
        value = H.ssn_monthly_rows("2026-%02d" % rng.randint(7, 10), rng.randint(4, 80), seed=rng.randint(1, 10 ** 6), third_party=rng.random() < 0.7)
    else:
        value = H.flare_rows(random_flare_events(rng, rng.randint(1, 25)))
    return product, value


def rows_of(value):
    return value if isinstance(value, list) else list(value.values())


def mutate_value(value, rng):
    """JSON 구조를 무작위로 망가뜨린다(바이트로 바꿀 수도 있다). (구조 또는 바이트, 설명)."""
    kind = rng.choices(("none", "drop", "dup", "shuffle", "null", "neg", "weird", "rename", "extra", "truncate", "wrap", "empty", "pretty", "inflate", "intify", "time"),
                       weights=(10, 3, 3, 3, 4, 3, 5, 3, 2, 1, 1, 1, 2, 1, 2, 3))[0]
    value = copy.deepcopy(value)
    rows = rows_of(value)
    if kind in ("none", "pretty"):
        return (json.dumps(value, ensure_ascii=False, indent=rng.choice((1, 2, 4))).encode("utf-8") if kind == "pretty" else value), kind
    if kind == "empty":
        return ([] if isinstance(value, list) else {}), kind
    if kind == "wrap":
        return ({"data": value} if isinstance(value, list) else [value]), kind
    if kind == "truncate":
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        return raw[:rng.randint(0, max(1, len(raw) - 1))], kind
    if kind == "inflate":
        return (value * rng.randint(2, 6) if isinstance(value, list) else value), kind
    if not rows or not isinstance(rows[0], dict):
        return value, kind
    row = rng.choice(rows)
    fields = list(row)
    if kind == "drop":
        if isinstance(value, list):
            value.remove(row)
        else:
            value.pop(rng.choice(list(value)))
    elif kind == "dup" and isinstance(value, list):
        value.append(copy.deepcopy(row))
    elif kind == "shuffle" and isinstance(value, list):
        rng.shuffle(value)
    elif kind == "null":
        row[rng.choice(fields)] = None
    elif kind == "neg":
        row[rng.choice(fields)] = rng.choice((-1, -1.0, -2))
    elif kind == "weird":
        row[rng.choice(fields)] = rng.choice(("x", True, [], {}, 1e99, "", "2026-11-03T00:00:00Z", 12.5, "NaN"))
    elif kind == "rename":
        name = rng.choice(fields)
        row[name + "_x"] = row.pop(name)
    elif kind == "extra":
        row["extra_field"] = rng.choice((1, "x", None))
    elif kind == "intify":
        for name in fields:
            if isinstance(row[name], float):
                row[name] = int(row[name])
    elif kind == "time":
        for name in fields:
            if isinstance(row[name], str) and "T" in row[name][:12]:
                row[name] = rng.choice((row[name] + "Z", row[name].replace("T", " "), row[name][:10], row[name].replace(":00:00", ":60:00")))
                break
    return value, kind


def mutate_facts(facts, rng):
    """읽힌 Fact 를 다시 망가뜨린다(상태·단위·기준값·값·기관). (Fact 목록, 설명)."""
    facts = list(facts)
    kind = rng.choices(("none", "status", "unit", "drop_threshold", "none_value", "drop", "dup_value", "producer"), weights=(18, 3, 2, 2, 3, 3, 2, 2))[0]
    if kind == "none" or not facts:
        return facts, kind
    index = rng.randrange(len(facts))
    fact = facts[index]
    if kind == "status":
        facts[index] = TR.revalue(fact, meta=dict(fact.meta or {}, status=rng.choice(("observed", "estimated", "predicted", "reference", "unknown"))))
    elif kind == "unit":
        facts[index] = TR.revalue(fact, unit=rng.choice(("개", "건", "Kp", "%", "단계", "nW/㎡"))) if fact.kind in F.NUMERIC_KINDS else fact
    elif kind == "drop_threshold":
        facts = [f for f in facts if "threshold" not in f.key and "floor" not in f.key]
    elif kind == "none_value":
        facts[index] = TR.revalue(fact, value=None) if fact.kind in F.NUMERIC_KINDS else fact
    elif kind == "drop":
        del facts[index]
    elif kind == "dup_value":
        facts.append(TR.revalue(fact, value="3" if fact.kind in F.NUMERIC_KINDS else fact.value))
    elif kind == "producer":
        facts[index] = TR.revalue(fact, meta=dict(fact.meta or {}, producer=rng.choice(("SIDC", "NRC", "NOAA"))))
    return facts, kind


# ----------------------------------------------------------------------------
# 독립 오라클 — 응답 JSON 에서 일반 파이썬으로 직접 센다(어댑터·계산식·틀을 쓰지 않는다)
# ----------------------------------------------------------------------------
def missing(value):
    return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and value == -1)


def oracle_kp_days(rows):
    by_day = {}
    for row in rows:
        by_day.setdefault(row["time_tag"][:10], []).append(row)
    out = {}
    for day, items in by_day.items():
        if len(items) == 8 and len({item["time_tag"] for item in items}) == 8 and not any(missing(item["Kp"]) for item in items):
            out[day] = [Decimal(str(item["Kp"])) for item in items]
    return out


def day_ordinal(day):
    return datetime.date.fromisoformat(day).toordinal()


def table(post, header_start):
    lines = post.body_markdown.split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith(header_start))
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def korean_day(day):
    year, month, date = day.split("-")
    return f"{int(year)}년 {int(month)}월 {int(date)}일"


def number(text):
    return Decimal(text.replace("−", "-").replace("+", "").replace(",", "").rstrip("Kp%개건구간일단계"))


def oracle_problems(product, recipe_id, value, post):
    """응답(JSON 구조)과 글의 표·한눈에를 견준다. 문제 목록(비면 같다)."""
    problems = []
    if product in ("kp_estimated", "kp_outlook") and recipe_id.startswith("R04"):
        rows = value if product == "kp_estimated" else [dict(time_tag=r["time_tag"], Kp=r["kp"]) for r in value if r["observed"] == "observed"]
        days = oracle_kp_days(rows)
        if not days:
            return ["오라클: 완전한 날이 없는데 글이 나옴"]
        latest = max(days, key=day_ordinal)
        shown = {day: max(values) for day, values in days.items() if day_ordinal(latest) - day_ordinal(day) < RN.DAY_TABLE_ROWS}
        cells = table(post, "| 기준 기간 | 값")
        got = {row[0]: number(row[1]) for row in cells if row[1] != R.MISSING_CELL}
        if got != {korean_day(day): value_ for day, value_ in shown.items()}:
            problems.append("오라클: R04 Kp 하루 최댓값 표가 다름")
    elif product in ("kp_estimated", "kp_outlook") and recipe_id.startswith("R05"):
        rows = value if product == "kp_estimated" else [dict(time_tag=r["time_tag"], Kp=r["kp"]) for r in value if r["observed"] == "observed"]
        days = oracle_kp_days(rows)
        over_days = sum(1 for values in days.values() if max(values) >= 5)
        over_intervals = sum(1 for values in days.values() for item in values if item >= 5)
        if f"가운데 기준 이상인 날: {over_days}일" not in post.body_markdown:
            problems.append("오라클: R05 폭풍 일수가 다름")
        if f"가운데 기준 이상인 구간: {over_intervals}구간" not in post.body_markdown:
            problems.append("오라클: R05 폭풍 구간 수가 다름")
        if f"이 글이 읽은 {len(days)}일 가운데" not in post.body_markdown:
            problems.append("오라클: R05 읽은 일수가 다름")
    elif product == "xray_flares":
        counts = {letter: 0 for letter in "ABCMX"}
        for row in value:
            counts[row["max_class"][0]] += 1
        cells = {row[0]: row[1] for row in table(post, "| 등급 | 건수")}
        for letter, count in counts.items():
            if cells.get(f"{letter}급") != f"{count}건":
                problems.append(f"오라클: 플레어 {letter}급 건수가 다름")
        if cells.get("전체") != f"{len(value)}건" or cells.get("M급 이상 합계") != f"{counts['M'] + counts['X']}건":
            problems.append("오라클: 플레어 합계가 다름")
    elif product == "scales":
        forecast = [row for row in table(post, "| 예보 날짜")]
        days = ("1", "2", "3")
        for row, name in zip(forecast, days):
            entry = value[name]
            want = [entry["R"]["MinorProb"], entry["R"]["MajorProb"], entry["S"]["Prob"], entry["G"]["Scale"]]
            if row[0] != korean_day(entry["DateStamp"]) or [str(int(number(cell))) for cell in row[1:]] != [str(int(item)) for item in want]:
                problems.append("오라클: 예보 표가 다름")
        observed = table(post, "| 기준일 | 전파 교란 등급")
        now = value["0"]
        if observed[0][1:] != [f"{now[scale]['Scale']}단계" for scale in ("R", "S", "G")]:
            problems.append("오라클: 관측 표가 다름")
    elif product in ("ssn_daily", "ssn_monthly"):
        if product == "ssn_daily":
            values = {row["Obsdate"][:10]: row["swpc_ssn"] for row in value if not missing(row["swpc_ssn"])}
            latest = max(values, key=day_ordinal)
            shown = {day: Decimal(str(item)) for day, item in values.items() if day_ordinal(latest) - day_ordinal(day) < RN.DAY_TABLE_ROWS}
            got = {row[0]: number(row[1]) for row in table(post, "| 기준 기간 | 값") if row[1] != R.MISSING_CELL}
            if got != {korean_day(day): item for day, item in shown.items()}:
                problems.append("오라클: 일별 흑점수 표가 다름")
        else:
            values = {row["time-tag"]: row["observed_swpc_ssn"] for row in value if not missing(row["observed_swpc_ssn"])}
            latest = max(values)
            year, month = int(latest[:4]), int(latest[5:])
            index = year * 12 + month - 1
            shown = {tag: Decimal(str(item)) for tag, item in values.items() if index - (int(tag[:4]) * 12 + int(tag[5:]) - 1) < RN.MONTH_TABLE_ROWS}
            got = {row[0]: number(row[1]) for row in table(post, "| 기준 기간 | 값") if row[1] != R.MISSING_CELL}
            if got != {f"{int(tag[:4])}년 {int(tag[5:])}월": item for tag, item in shown.items()}:
                problems.append("오라클: 월평균 흑점수 표가 다름")
    return problems


# ----------------------------------------------------------------------------
# 불변식
# ----------------------------------------------------------------------------
def allowed_latin_of(post, source_name):
    allowed = set(A.ALWAYS_ALLOWED_LATIN) | set(re.findall(r"[A-Za-z]{2,}", source_name))
    for fact in post.facts_used:
        for text in (fact.label_ko, fact.region_label_ko, fact.unit):
            allowed.update(re.findall(r"[A-Za-z]{2,}", text or ""))
    return allowed


def post_problems(post, source_name):
    problems = list(A.post_problems(post, allowed_latin=allowed_latin_of(post, source_name)))
    if F.untraced_numbers(post.template_markdown):
        problems.append("틀에 참조 없는 숫자")
    if not set(A.number_tokens(A.story_of(post.body_markdown))) <= A.traceable_numbers(post):
        problems.append("본문에 값에서 오지 않은 숫자")
    if not set(A.number_tokens(post.title)) <= A.date_numbers(post):
        problems.append("제목에 값")
    if A.forbidden_found(post.title + "\n" + post.description + "\n" + post.body_markdown) or A.blocked_found(post.title + "\n" + post.description + "\n" + post.body_markdown):
        problems.append("금지 표현")
    if re.search(R.VARYING_PARTICLE_PATTERNS[2], post.body_markdown) or A.particle_problems(post.template_markdown):
        problems.append("조사")
    if not re.fullmatch(r"R0[4-6]_[A-Z_]+\|space_weather\.[a-z_]+\|-\|\d{4}-\d{2}(?:-\d{2})?", post.dedupe_key):
        problems.append("중복 방지 키 모양")
    if post.category != "과학·환경" or post.lang != "ko":
        problems.append("분류·언어")
    return problems


def run_fuzz(cases=CASES, seed=SEED):
    """무작위 사례 cases 건을 돌려 통계(dict)를 돌려준다. 불변식이 깨지면 사례 번호와 설명을 담은 AssertionError."""
    stats = {"cases": 0, "adapter_ok": 0, "adapter_refused": {}, "posts": 0, "insufficient": {}, "oracle_checked": 0, "assembled": 0}
    for number_ in range(cases):
        rng = random.Random(f"{seed}:{number_}")
        product, value = random_payload(rng)
        mutated, how = mutate_value(value, rng)
        raw = mutated if isinstance(mutated, bytes) else json.dumps(mutated, ensure_ascii=False).encode("utf-8")
        stats["cases"] += 1
        where = f"사례 {number_} 제품 {product} 변형 {how}"
        try:
            record, facts = H.parse_bytes(product, raw)
        except B.AdapterError as error:
            assert error.code in ADAPTER_CODES, f"{where}: 예상 밖 어댑터 코드 {error.code}"
            assert not re.search(r"(?i)http|services\.swpc|SECRET", str(error)), f"{where}: 오류 문구에 주소"
            stats["adapter_refused"][error.code] = stats["adapter_refused"].get(error.code, 0) + 1
            continue
        stats["adapter_ok"] += 1
        bundle_problems = F.validate_bundle(F.FactBundle((record,), tuple(facts)))
        assert not bundle_problems, f"{where}: Fact 묶음이 검증을 통과하지 못함 {bundle_problems[:2]}"
        assert {f.meta_value("producer") for f in facts} == {"NOAA"}, f"{where}: producer"
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, (list, dict)):
            continue
        mutated_facts, fact_how = mutate_facts(facts, rng)
        for recipe_id in RECIPES_FOR[product]:
            today = rng.choice((H.TODAY, H.TODAY, "2026-11-11", "2026-11-14", "2026-12-20", "2026-11-05"))
            provider = H.provider(attribution_template=rng.choice((H.TEST_TEMPLATE, H.B_TEMPLATE)))
            params = {"key": KEY_FOR[(recipe_id, product)]} if KEY_FOR[(recipe_id, product)] else {}
            source = A.SourceInfo(provider, N.product_source_name(product), N.product_url(product))
            tag = f"{where} Fact변형 {fact_how} {recipe_id} 오늘 {today}"
            try:
                result = A.assemble(RN.NOREGION_RECIPES[recipe_id], mutated_facts, today, records=[record], source=source, params=params)
            except Exception as error:      # noqa: BLE001 — 조립기는 어떤 입력에서도 예외를 올리지 않는다
                raise AssertionError(f"{tag}: 예외 {type(error).__name__}") from None
            stats["assembled"] += 1
            if isinstance(result, R.Insufficient):
                assert result.code not in UNEXPECTED, f"{tag}: 예상 밖 사유 {result.code} {result.detail}"
                stats["insufficient"][result.code] = stats["insufficient"].get(result.code, 0) + 1
                continue
            stats["posts"] += 1
            problems = post_problems(result, source.name)
            assert not problems, f"{tag}: {problems}"
            shuffled = list(mutated_facts)
            rng.shuffle(shuffled)
            again = A.assemble(RN.NOREGION_RECIPES[recipe_id], shuffled, today, records=[record], source=source, params=params)
            assert again == result, f"{tag}: 입력 순서에 따라 글이 달라짐"
            if fact_how == "none" and how in ("none", "pretty", "shuffle"):
                found = oracle_problems(product, recipe_id, parsed, result)
                stats["oracle_checked"] += 1
                assert not found, f"{tag}: {found}"
    return stats


class FuzzTest(unittest.TestCase):
    def test_random_payloads_never_break_an_invariant(self):
        stats = run_fuzz()
        self.assertEqual(stats["cases"], CASES)
        self.assertGreater(stats["adapter_ok"], CASES // 4)                                  # 읽히는 사례가 충분히 많다
        self.assertGreater(stats["adapter_refused"].get("BAD_SHAPE", 0), 0)                   # 거절되는 사례도 있다
        self.assertGreater(stats["posts"], CASES // 12)
        self.assertGreater(stats["oracle_checked"], CASES // 30)
        self.assertEqual(sum(1 for code in stats["insufficient"] if code in UNEXPECTED), 0)

    def test_the_fuzz_is_reproducible(self):
        self.assertEqual(run_fuzz(20, 7), run_fuzz(20, 7))


class OracleSelfTest(unittest.TestCase):
    """오라클이 헛돌지 않는다 — 글의 숫자를 일부러 고치면 오라클이 잡는다."""

    def test_the_oracle_notices_a_changed_cell_in_each_table(self):
        for name in ("r04_kp", "r04_ssn_daily", "r04_ssn_monthly", "r05_flares", "r06_scales", "r05_kp_storm"):
            recipe_id, product, rows, params = TR.golden_cases()[name]
            post = TR.build(name)
            self.assertEqual(oracle_problems(product, recipe_id, json.loads(json.dumps(rows)), post), [], name)
            first_cell = re.search(r"(?m)^\| (?:20\d\d년|[A-Z]급) .*?\| ([0-9][0-9,.]*)", post.body_markdown) if name != "r05_kp_storm" else re.search(r"가운데 기준 이상인 날: (\d+)일", post.body_markdown)
            self.assertTrue(first_cell, name)
            text = post.body_markdown
            start, end = first_cell.span(1)
            digit = "9" if text[start] != "9" else "8"
            broken = TR.dataclasses.replace(post, body_markdown=text[:start] + digit + text[start + 1:])
            self.assertTrue(oracle_problems(product, recipe_id, json.loads(json.dumps(rows)), broken), name)


if __name__ == "__main__":
    unittest.main()
