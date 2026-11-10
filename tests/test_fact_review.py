"""구조화 Fact 경로 1단계 — 독립 검증 지적(V-01–V-14) 회귀 시험: 보이는 값끼리 모순 없는 글(속성형)·주제 허용 목록 우회·근거 텍스트에 내부 번호 없음·기간 개수·구간척도 변화율·동률·
큰 값(퍼징)·SRC 안내 문장·우리말 수 표현·표와 설명의 일치·지역 없는 계열·죽은 방어선. 새 동작마다 이 시험이 있고, 고친 줄을 되돌리면 빨갛게 된다(변이 증명).
병합 뒤 후속 수정(재검증 D3–D12, 파일 끝쪽): 전역 decimal 문맥을 바꿔 바깥에 씌워도 같은 결과(ExactContextTest)·평균이 반 칸에 걸리는 묶음(HalfStepTest)·동률 줄(TieLineTest)·정수 개수
(CountUnitTest)·우리말 수 표현 구조(NumberWordShapeTest)·자유 글 칸(FreeTextFieldsTest)·재검증이 살려 둔 변이(SecondRoundSurvivorsTest).
무작위는 시험 안에서 고정 시드로만 쓴다(결정적). 네트워크·시계 없이 돌고, 환경(전역 decimal 문맥·재귀 한계·경로·파일)에 기대지 않는다 — 문맥은 시험 안에서 `decimal.localcontext` 로 씌운다."""
import dataclasses
import decimal
import random
import re
import types
import unittest
from decimal import Decimal

import _bootstrap  # noqa: F401
import fact_helpers as H

from pipeline import calc as C
from pipeline import fact_assembler as A
from pipeline import fact_topics as T
from pipeline import facts as F
from pipeline import recipes as R
from pipeline.adapters import mock_stats as M

RECORD_ID = H.mock_bundle()[1].record_id
SYLLABLES = "가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허"


def months(start, count):
    year, month = (int(part) for part in start.split("-"))
    return [f"{year + (month - 1 + i) // 12:04d}-{(month - 1 + i) % 12 + 1:02d}" for i in range(count)]


def ending(count, last="2026-03"):
    """마지막 달이 last 인 count 개 달."""
    year, month = (int(part) for part in last.split("-"))
    index = year * 12 + month - 1 - (count - 1)
    return months(f"{index // 12:04d}-{index % 12 + 1:02d}", count)


def series(values, *, periods=None, **kw):
    """한 계열의 Fact(가짜 수집 기록을 가리킨다). periods 가 없으면 마지막이 2026년 3월인 연속한 달."""
    periods = periods or ending(len(values))
    return [H.make_fact(value, period=period, record_id=RECORD_ID, **kw) for value, period in zip(values, periods)]


def cross(values, *, period="2026-03", names=None, **kw):
    """같은 기준일의 지역 묶음(지역 이름은 `가상 지역 가`…)."""
    out = []
    for index, value in enumerate(values):
        name = (names or {}).get(index) or "가상 지역 " + SYLLABLES[index % len(SYLLABLES)]
        out.append(H.make_fact(value, period=period, region=f"R{index + 1:02d}", region_label=name, record_id=RECORD_ID, **kw))
    return out


def run(recipe, facts, params=None, **kw):
    return H.run(recipe, facts=facts, params=params if params is not None else {}, **kw)


def story(post):
    return A.story_of(post.body_markdown)


def table_rows(post):
    return [[cell.strip() for cell in line.strip("|").split("|")] for line in post.body_markdown.split("\n") if line.startswith("| 20")]


def rank_rows(post):
    """지역 비교 표의 줄 [순위, 지역, 값, 평균과의 차이]."""
    return [[cell.strip() for cell in line.strip("|").split("|")] for line in post.body_markdown.split("\n") if re.match(r"\| [0-9]+위 \|", line)]


def number(text):
    return float(text.replace("−", "-").replace("+", "").replace(",", "").rstrip("%p명곳℃위개월분기년번"))


class DisplayConsistencyTest(unittest.TestCase):
    """V-01·V-12: 보이는 값이 서로 어긋나는 헤드라인이 없다 — 표시 소수 자리는 단위 표와 자료의 정밀도 중 큰 쪽이다."""

    def test_the_verifiers_straddling_example_is_now_consistent(self):
        post = run("R01_time_series", series(["3.30", "3.31", "3.32", "3.33", "3.34", "3.35", "3.36", "3.44", "3.46"]))
        self.assertEqual(post.title, "가상 지역 가 실업률, 2025년 7월부터 2026년 3월까지 — 숫자로 읽기")            # 제목에는 값이 없다(D-200) — 값은 설명·본문에
        self.assertNotIn("3.46", post.title)
        self.assertEqual(post.description, "가상 지역 가의 실업률 값은 2026년 2월(3.44%)보다 0.02%p 높은 3.46%입니다(2026년 3월 기준).")
        self.assertIn("- 바로 앞 기간 대비: +0.02%p, 변화율 +0.58% (견준 기간 2026년 2월, 그때 값 3.44%)", post.body_markdown)
        self.assertIn("| 2026년 3월 | 3.46% | +0.02%p | +0.58% |", post.body_markdown)
        self.assertNotIn("달라지지 않은", post.description + post.body_markdown)
        self.assertEqual(dict(post.decimals), {"%": 2, "%p": 2})

    def test_equal_values_are_the_same_and_only_then(self):
        same = run("R01_time_series", series(["3.20", "3.30", "3.40", "3.45", "3.30", "3.50", "3.45", "3.50", "3.50"]))
        self.assertNotIn("3.50", same.title)                                        # 제목에는 값이 없다(D-200)
        self.assertIn("2026년 2월(3.50%)에서 달라지지 않은 3.50%입니다", same.description)
        self.assertIn("| 2026년 3월 | 3.50% | 0.00%p | 0.00% |", same.body_markdown)
        near = run("R01_time_series", series(["3.20", "3.30", "3.40", "3.45", "3.30", "3.50", "3.45", "3.50", "3.51"]))
        self.assertIn("2026년 2월(3.50%)보다 0.01%p 높은 3.51%입니다", near.description)
        self.assertNotIn("달라지지 않은", near.description)

    def test_the_unit_table_is_the_minimum_and_the_data_may_be_more_precise(self):
        ints = run("R01_time_series", series(["10", "12", "11", "13", "12", "14", "13", "15", "16"], unit="명", label="취업자 수", key="labour.employed_persons"))
        self.assertEqual(dict(ints.decimals), {"명": 0})
        self.assertIn("16명", ints.description)
        fine = run("R01_time_series", series(["108.4", "108.6", "108.1", "108.3", "108.2", "108.9", "109.0", "108.8", "108.6"], unit="점", label="물가지수", key="price.index"))
        self.assertEqual(dict(fine.decimals), {"점": 1})                 # 표 0자리, 자료 1자리 → 1자리(108.4점과 108.6점이 108점·109점으로 뭉개지지 않는다)
        self.assertIn("108.6점", fine.description)
        percent_with_ints = run("R01_time_series", series(["3", "4", "3", "5", "4", "6", "5", "4", "6"]))
        self.assertEqual(dict(percent_with_ints.decimals), {"%": 1, "%p": 1})       # 정수 자료도 단위 표의 1자리(`3.0%`) — 자료의 정밀도를 깎지는 않는다

    def test_display_context_is_the_larger_of_the_table_and_the_data(self):
        make = lambda value, unit="%": H.make_fact(value, unit=unit)          # noqa: E731
        self.assertEqual(F.display_context([make("3.5"), make("3.46"), make("3.4")]), {"%": 2, "%p": 2})
        self.assertEqual(F.display_context([make("3"), make("4")]), {"%": 1, "%p": 1})
        self.assertEqual(F.display_context([make("3.5000")]), {"%": 1, "%p": 1})                 # 뒤의 0 은 정밀도가 아니다
        self.assertEqual(F.display_context([make("1200", "명"), make("1200.25", "명")]), {"명": 2})
        self.assertEqual(F.display_context([make("2.5", "달러")]), {"달러": 2})
        self.assertEqual(F.display_context([make(None)]), {})                                      # 모름은 정밀도를 말하지 않는다
        self.assertEqual(F.display_context([make("1.1234")]), {"%": 4, "%p": 4})
        with self.assertRaises(F.PrecisionLimit):
            F.display_context([make("1.12345")])
        self.assertEqual(F.value_decimals(Decimal("3.50")), 1)
        self.assertEqual(F.value_decimals(Decimal("1E+2")), 0)
        self.assertEqual(F.value_decimals(Decimal("0")), 0)
        self.assertEqual(F.decimals_for("%", {"%": 3}), 3)
        self.assertEqual(F.decimals_for("명", {"%": 3}), 0)
        self.assertEqual(F.format_with_unit(Decimal("3.5"), "%", context={"%": 3}), "3.500%")
        self.assertEqual(F.display_sign(Decimal("0.04"), "%p", {"%p": 2}), 1)
        self.assertEqual(F.display_sign(Decimal("0.04"), "%p"), 0)

    def test_data_more_precise_than_the_display_limit_is_refused_not_rounded(self):
        result = run("R01_time_series", series(["3.456789", "3.401234", "3.42", "3.46", "3.44", "3.5", "3.46", "3.50", "3.54"]))
        self.assertIsInstance(result, R.Insufficient)
        self.assertEqual(result.code, "PRECISION_LIMIT")
        ok = run("R01_time_series", series(["3.4567", "3.4012", "3.42", "3.46", "3.44", "3.5", "3.46", "3.50", "3.54"]))
        self.assertIsInstance(ok, A.AssembledPost)
        self.assertIn("3.5400%", ok.description)
        self.assertNotIn("3.5400%", ok.title)

    def test_region_values_that_used_to_look_equal_are_shown_exactly(self):
        post = run("R02_region_compare", cross(["3.46", "3.54", "3.50", "3.49", "3.51"]), {"key": H.UNEMP})
        self.assertIsInstance(post, A.AssembledPost)
        rows = rank_rows(post)
        self.assertEqual([row[0] for row in rows], ["1위", "2위", "3위", "4위", "5위"])
        self.assertEqual([row[2] for row in rows], ["3.54%", "3.51%", "3.50%", "3.49%", "3.46%"])
        self.assertEqual(len({row[2] for row in rows}), 5)

    def test_verdict_needs_the_displayed_numbers_to_agree(self):
        cur, ref = H.make_fact("3.46"), H.make_fact("3.44", period="2026-02")
        chg = C.f01_change(cur, ref)
        exact = F.display_context([cur, ref])
        self.assertEqual(R.verdict(cur, ref, chg, exact), "UP")
        self.assertEqual(R.verdict(ref, cur, C.f01_change(ref, cur, require="any"), exact), "DOWN")
        coarse = {"%": 1, "%p": 1}                       # 보이는 값은 3.5 와 3.4 인데 차이는 0.0 으로 보이는 설정 — 모순이라 판정하지 않는다
        self.assertIsNone(R.verdict(cur, ref, chg, coarse))
        same_a, same_b = H.make_fact("3.5"), H.make_fact("3.5", period="2026-02")
        self.assertEqual(R.verdict(same_a, same_b, C.f01_change(same_a, same_b), {"%": 1, "%p": 1}), "SAME")
        near_a, near_b = H.make_fact("3.54"), H.make_fact("3.46", period="2026-02")           # 보이는 값은 둘 다 3.5 인데 차이는 +0.1 로 보인다
        self.assertEqual(F.format_with_unit(near_a.value, "%", context={"%": 1}), F.format_with_unit(near_b.value, "%", context={"%": 1}))
        self.assertIsNone(R.verdict(near_a, near_b, C.f01_change(near_a, near_b), {"%": 1, "%p": 1}))
        flat_a, flat_b = H.make_fact("3.5"), H.make_fact("3.5", period="2026-02")
        wrong = types.SimpleNamespace(value=Decimal("0.4"), unit="%p")                         # 같은 값인데 차이가 있다고 하는 계산 결과
        self.assertIsNone(R.verdict(flat_a, flat_b, wrong, {"%": 1, "%p": 1}))
        flipped = types.SimpleNamespace(value=Decimal("-0.4"), unit="%p")                      # 방향이 거꾸로인 차이
        self.assertIsNone(R.verdict(H.make_fact("3.9"), H.make_fact("3.5", period="2026-02"), flipped, {"%": 1, "%p": 1}))

    def test_an_inconsistent_verdict_makes_no_post(self):
        original = R.verdict
        try:
            R.verdict = lambda *args, **kwargs: None
            result = run("R01_time_series", H.series_of("R01"), H.R01_PARAMS)
        finally:
            R.verdict = original
        self.assertIsInstance(result, R.Insufficient)
        self.assertEqual(result.code, "DISPLAY_INCONSISTENT")

    def boundary_series(self, rng):
        places = rng.choice((0, 1, 2, 3))
        base = rng.randint(100, 900)
        values = []
        for _ in range(rng.choice((6, 9, 12, 15))):
            base += rng.choice((-3, -2, -1, 0, 0, 1, 2, 3))                    # 아주 작은 걸음 — 반올림 경계에 자주 걸린다
            values.append(str(Decimal(base) / (Decimal(10) ** places)))
        return values

    def check_consistency(self, values, post):
        """시험이 따로 하는 대조: 제목·설명의 말과 '한눈에'·표의 차이가 글에 보이는 두 값과 어긋나지 않는다."""
        cur, prev = Decimal(values[-1]), Decimal(values[-2])
        places = max(1, max(F.value_decimals(Decimal(v)) for v in values))
        shown = lambda v: format(v.quantize(Decimal(1).scaleb(-places)), "f")        # noqa: E731
        words = {"SAME": ("앞 기간과 같아", "달라지지 않은"), "UP": ("높아", "높은"), "DOWN": ("낮아", "낮은")}
        expected = "SAME" if cur == prev else "UP" if cur > prev else "DOWN"
        self.assertIn(words[expected][1], post.description)
        for other, pair in words.items():
            if other != expected:
                self.assertNotIn(pair[1], post.description)
        for pair in words.values():                                             # 제목은 값도 방향도 말하지 않는다(D-200)
            self.assertNotIn(pair[0], post.title)
        line = next(line for line in post.body_markdown.split("\n") if line.startswith("- 바로 앞 기간 대비:"))
        diff_text = re.search(r"대비: ([+−]?[0-9,.]+)", line).group(1)
        self.assertAlmostEqual(number(diff_text), float(cur - prev), places=places + 1)
        self.assertEqual(diff_text.lstrip("+−"), shown(abs(cur - prev)))
        self.assertEqual(diff_text.startswith("+"), cur > prev)
        self.assertEqual(diff_text.startswith("−"), cur < prev)
        self.assertIn(f"그때 값 {shown(prev)}%", line)
        rows = table_rows(post)
        for top, below in zip(rows, rows[1:]):                                  # 표의 증감 = 위 줄의 보이는 값 − 아래 줄의 보이는 값(둘 다 연속한 달)
            if not top[2].startswith("해당"):
                self.assertAlmostEqual(number(top[1]) - number(below[1]), number(top[2]), places=places + 1)

    def test_no_boundary_series_makes_a_contradictory_post(self):
        rng = random.Random(20261109)
        made = 0
        for _ in range(500):
            values = self.boundary_series(rng)
            post = run("R01_time_series", series(values))
            if isinstance(post, R.Insufficient):
                self.assertIn(post.code, ("TOO_SHORT", "TOO_FEW_POINTS"), post)
                continue
            made += 1
            self.assertEqual(A.post_problems(post), [])
            self.check_consistency(values, post)
        self.assertGreater(made, 350)


class TopicAllowListTest(unittest.TestCase):
    """V-02: 주제 차단이 허용 목록이다 — 키·라벨·단위·지역 낱말이 범주의 허용 목록에 모두 있어야 글이 되고, 차단 낱말은 띄어 써도 걸린다."""

    def post(self, label="실업률", unit="%", key=H.UNEMP, region_label="가상 지역 가", rid="R01_time_series", **kw):
        facts = series(["3.1", "3.2", "3.3", "3.2", "3.4", "3.5", "3.6", "3.5", "3.7"], label=label, unit=unit, key=key, region_label=region_label, **kw)
        return run(rid, facts, {"key": key})

    def code(self, result):
        self.assertIsInstance(result, R.Insufficient, "글이 나왔다")
        return result.code

    def test_the_verifiers_bypass_examples_are_all_refused(self):
        for label, key, unit in (("당뇨병 환자 수", "population.patients", "명"), ("주식 지수", "economy.index", "점"), ("지금 사야 할 지수", "economy.index", "점"),
                                 ("폭발적 증가 지수", "economy.index", "점"), ("무 조건 지수", "economy.index", "점"), ("효 능 지수", "economy.index", "점"),
                                 ("암 환자 수", "population.total", "명"), ("치료 건수", "population.total", "건"), ("급등 지역", "economy.index", "점"),
                                 ("반드시 오르는 지수", "economy.index", "점")):
            with self.subTest(label=label):
                self.assertIn(self.code(self.post(label=label, key=key, unit=unit)), ("TOPIC_NOT_ALLOWED", "UNKNOWN_TOPIC"))
        self.assertEqual(self.code(self.post(label="폭발적 증가 지수", key="economy.index", unit="점")), "UNKNOWN_TOPIC")        # 차단 낱말이 아니어도 허용 목록에 없으면 글이 안 된다
        self.assertEqual(self.code(self.post(label="당뇨병 환자 수", key="population.total", unit="명")), "TOPIC_NOT_ALLOWED")
        self.assertEqual(self.code(self.post(label="무 조건 지수", key="economy.index", unit="점")), "TOPIC_NOT_ALLOWED")

    def test_spaced_fullwidth_and_hidden_variants_are_found_too(self):
        for label in ("무 조 건", "무·조·건", "무-조-건", "무　조건", "무​조건", "효 능", "환 자", "주 식", "사 야", "당 뇨", "ＧＭ 보 장"):
            with self.subTest(label=label):
                self.assertTrue(T.blocked_in(label), label)
        self.assertEqual(T.compact("무 조·건-!"), "무조건")
        self.assertEqual(T.compact("ＡＢＣ １２"), "abc12")
        self.assertTrue(T.blocked_in("Ｓｔｏｃｋ Ｉｎｄｅｘ", english=True))
        self.assertTrue(T.blocked_in("Cancer patients", english=True))
        self.assertEqual(T.blocked_in("암호 길이"), [])                      # 한 글자 낱말 '암' 은 낱말 전체일 때만 — 암호·암석은 과탐하지 않는다
        self.assertEqual(T.blocked_in("암모니아 농도"), [])
        self.assertTrue(T.blocked_in("암 지수"))

    def test_every_field_is_checked_not_only_the_label(self):
        self.assertEqual(self.code(self.post(unit="환자")), "TOPIC_NOT_ALLOWED")
        for kw, expected in ((dict(region_label="당뇨병 환자 모임"), "TOPIC_NOT_ALLOWED"), (dict(region_label="투자 권유 지역"), "TOPIC_NOT_ALLOWED"),
                             (dict(region_label="마법 지역"), "UNKNOWN_TOPIC"), (dict(label="실업률 보장"), "TOPIC_NOT_ALLOWED"), (dict(unit="㎜"), "UNKNOWN_TOPIC")):
            with self.subTest(kw=kw):
                self.assertEqual(self.code(self.post(**kw)), expected)
        self.assertEqual(self.code(self.post(key="labour.diabetes_rate")), "UNKNOWN_TOPIC")
        self.assertEqual(self.code(self.post(key="labour")), "UNKNOWN_TOPIC")
        english = [dataclasses.replace(fact, label_en="Cancer patients") for fact in series(["3.1"] * 9)]
        self.assertIsNotNone(T.fact_problem(english[0], R.ALLOWED_DOMAINS))
        for text in ("주식 투자 추천 통계", "당뇨 환자 통계", "무 조건 통계"):
            with self.subTest(source=text):
                result = H.run("R01_time_series", params=H.R01_PARAMS, source=A.SourceInfo(M.MockProvider(), text, M.SOURCE_URL))
                self.assertEqual(self.code(result), "SOURCE_INFO_INVALID")

    def test_one_unknown_region_refuses_the_whole_comparison(self):
        """그 지역만 빼고 비교하면 '가장 높은 곳' 이 거짓이 될 수 있다 — 낱말이 허용 목록 밖인 지역이 하나라도 있으면 묶음 전체를 쓰지 않는다."""
        facts = cross(["3.5", "3.3", "2.9", "3.8", "9.9"], names={4: "마법 지역"})
        self.assertEqual(self.code(run("R02_region_compare", facts, {"key": H.UNEMP})), "UNKNOWN_TOPIC")
        facts = cross(["3.5", "3.3", "2.9", "3.8", "9.9"], names={0: "급등 지역"})
        self.assertEqual(self.code(run("R02_region_compare", facts, {"key": H.UNEMP})), "TOPIC_NOT_ALLOWED")
        mixed = cross(["3.5", "3.3", "2.9", "3.8"]) + [H.make_fact("1", key="sports.scores", period="2026-03", region="R09", region_label="가상 지역 사", record_id=RECORD_ID)]
        self.assertIsInstance(run("R02_region_compare", mixed, {}), A.AssembledPost)            # 다른 계열(다른 묶음)의 낱말 문제는 이 묶음을 막지 않는다

    def test_a_series_with_one_bad_label_is_refused_whole(self):
        facts = series(["3.1", "3.2", "3.3", "3.2", "3.4", "3.5", "3.6", "3.5", "3.7"])
        facts[3] = dataclasses.replace(facts[3], label_ko="주식 지수")
        facts[3] = F.Fact.create(**{name: getattr(facts[3], name) for name in ("provider_id", "source_record_id", "kind", "key", "value", "unit", "as_of", "region",
                                                                                "region_level", "region_label_ko", "region_label_en", "label_ko", "label_en")})
        self.assertEqual(self.code(run("R01_time_series", facts, {})), "TOPIC_NOT_ALLOWED")
        differing = series(["3.1", "3.2", "3.3", "3.2", "3.4", "3.5", "3.6", "3.5", "3.7"])
        other = differing[2]
        differing[2] = F.Fact.create(other.provider_id, other.source_record_id, other.kind, other.key, other.value, other.unit, other.as_of, other.region, other.region_level,
                                     other.region_label_ko, other.region_label_en, "고용률", other.label_en)
        self.assertEqual(self.code(run("R01_time_series", differing, {})), "INCONSISTENT_LABELS")

    def test_a_recipe_only_uses_the_domains_it_allows(self):
        """어휘 표에 있는 범주라도 Recipe 의 `allowed_domains` 에 없으면 글이 안 된다."""
        facts = series(["3.1", "3.2", "3.3", "3.2", "3.4", "3.5", "3.6", "3.5", "3.7"], key="economy.growth_rate", label="경제 성장률")
        self.assertIsInstance(run("R01_time_series", facts, {}), A.AssembledPost)
        narrow = dataclasses.replace(R.R01_TIME_SERIES, allowed_domains=("labour",))
        result = run(narrow, facts, {})
        self.assertEqual(self.code(result), "UNKNOWN_TOPIC")
        self.assertEqual(T.fact_problem(facts[0], ("labour",))[0], "UNKNOWN_TOPIC")
        self.assertIsNone(T.fact_problem(facts[0], ("labour", "economy")))
        self.assertEqual(T.fact_problem(facts[0], ())[0], "UNKNOWN_TOPIC")

    def test_labels_of_one_comparison_must_agree(self):
        facts = cross(["3.5", "3.3", "2.9", "3.8", "4.2"])
        other = facts[2]
        facts[2] = F.Fact.create(other.provider_id, other.source_record_id, other.kind, other.key, other.value, other.unit, other.as_of, other.region, other.region_level,
                                 other.region_label_ko, other.region_label_en, "고용률", other.label_en)
        self.assertEqual(self.code(run("R02_region_compare", facts, {"key": H.UNEMP})), "INCONSISTENT_LABELS")

    def test_every_approved_domain_makes_a_post(self):
        examples = (("labour.unemployment_rate", "실업률", "%"), ("economy.growth_rate", "경제 성장률", "%"), ("price.consumer_index", "소비자물가 지수", "점"),
                    ("population.total", "총인구", "명"), ("education.students", "학생 수", "명"), ("environment.temperature", "평균기온", "℃"),
                    ("energy.demand", "전력수요", "MW"), ("space_weather.kp_index", "지자기지수", "Kp"))
        self.assertEqual({key.split(".")[0] for key, _label, _unit in examples}, set(T.DOMAINS))
        for key, label, unit in examples:
            with self.subTest(key=key):
                post = self.post(label=label, unit=unit, key=key)
                self.assertIsInstance(post, A.AssembledPost, post)
                self.assertEqual(post.category, T.DOMAINS[key.split(".")[0]].category)
                self.assertEqual(A.post_problems(post, allowed_latin=set(re.findall(r"[A-Za-z]{2,}", unit + label))), [])

    def test_the_vocabulary_is_clean(self):
        self.assertEqual(set(R.TOPIC_CATEGORY), set(T.DOMAINS))
        for domain_id, domain in T.DOMAINS.items():
            with self.subTest(domain=domain_id):
                self.assertEqual(domain.domain_id, domain_id)
                self.assertNotIn(domain_id, F.BLOCKED_TOPICS)
                for unit in domain.units:
                    self.assertIn(unit, F.UNIT_TABLE, f"{unit} 은 단위 표에 명시돼 있어야 한다")
                    self.assertRegex(unit, F._UNIT_RE.pattern)
                for word in domain.label_words | T.REGION_WORDS:
                    self.assertEqual(T.blocked_in(word), [], word)
                for word in domain.key_words:
                    self.assertEqual(T.blocked_in(word, english=True), [], word)
                    self.assertRegex(word, r"\A[a-z]+\Z")

    def test_no_two_approved_words_join_into_a_blocked_word(self):
        """공백을 지운 글에서 부분 문자열로 찾으므로 허용한 낱말 둘이 붙어 우연히 차단 낱말이 되면 안 된다."""
        for domain_id, domain in T.DOMAINS.items():
            words = sorted(domain.label_words)
            for first in words:
                for second in words:
                    self.assertEqual(T.blocked_in(f"{first} {second}"), [], (domain_id, first, second))
        regions = sorted(T.REGION_WORDS)
        for first in regions:
            for second in regions:
                self.assertEqual(T.blocked_in(f"{first} {second}"), [], (first, second))

    def test_the_blocked_word_lists_cover_the_agreed_examples(self):
        flat = {word for words in T.BLOCKED_WORDS.values() for word in words}
        for word in ("환자", "질환", "치료", "완치", "처방", "복용", "효능", "부작용", "당뇨", "고혈압", "치매", "주식", "코인", "펀드", "투자추천", "수익률", "매수", "매도", "사야", "소송",
                     "판결", "처벌", "보장", "반드시", "무조건", "역대급", "폭등", "급등", "추천", "권유", "때문", "전망", "예측"):
            self.assertIn(word, flat)
        self.assertEqual(T.text_problem("주식 투자 안내"), "건강·의료·금융 투자·법률 주제나 과장·단정 낱말이 있음")
        self.assertIsNone(T.text_problem("공식 통계 안내"))

    def test_the_region_vocabulary_accepts_real_region_names_and_the_mock_pattern(self):
        facts = series(["3.1", "3.2", "3.3", "3.2", "3.4", "3.5", "3.6", "3.5", "3.7"], region_label="서울특별시")
        self.assertIsInstance(run("R01_time_series", facts, {}), A.AssembledPost)
        self.assertIsNone(T.fact_problem(H.make_fact("1", region_label="경기도"), R.ALLOWED_DOMAINS))
        self.assertIsNone(T.fact_problem(H.make_fact("1", region_label="서울 경기"), R.ALLOWED_DOMAINS))                 # 허용한 낱말로만 이뤄진 이름
        self.assertIsNone(T.fact_problem(H.make_fact("1", region_label="가상 지역 허"), R.ALLOWED_DOMAINS))
        self.assertEqual(T.fact_problem(H.make_fact("1", region_label="가상 지역 허허"), R.ALLOWED_DOMAINS)[0], "UNKNOWN_TOPIC")
        self.assertEqual(T.fact_problem(H.make_fact("1", region_label="서울 마법"), R.ALLOWED_DOMAINS)[0], "UNKNOWN_TOPIC")
        self.assertIsNone(T.fact_problem(dataclasses.replace(H.make_fact("1"), region_label_ko=None), R.ALLOWED_DOMAINS))      # 지역 이름이 없는 계열은 이 검사로 막지 않는다(글이 안 되는 이유는 따로)
        self.assertEqual(T.fact_problem(dataclasses.replace(H.make_fact("1"), label_ko=None), R.ALLOWED_DOMAINS)[0], "UNKNOWN_TOPIC")



def value_numbers(post):
    """글에 나와도 되는 숫자(시험이 따로 만든 목록): 쓴 Fact·계산 결과의 값(글에 보인 모양)과 기준일·수집일의 숫자. 내부 번호는 없다."""
    context = dict(post.decimals)
    out = set()
    for item in (*post.facts_used, *post.derived):
        out |= set(A.number_tokens(F.format_with_unit(item.value, item.unit, signed=True, context=context)))
        out |= set(A.number_tokens(F.format_period_ko(item.as_of)))
    for record in post.source_records:
        out |= set(A.number_tokens(F.format_period_ko(record.retrieved_at[:10])))
    return out


class EvidenceTextTest(unittest.TestCase):
    """V-03: 근거 텍스트에는 값·단위·기준일·지역 이름만 있다 — id 의 숫자가 '근거 숫자'로 세어져 본문에 끼워 넣은 숫자를 못 잡는 일이 없다."""

    @classmethod
    def setUpClass(cls):
        cls.posts = {rid: H.run(rid, params=params) for rid, params in H.GOLDEN.items()}

    def test_the_evidence_numbers_are_exactly_the_values_and_dates(self):
        for rid, post in self.posts.items():
            with self.subTest(recipe=rid):
                self.assertEqual(set(A.number_tokens(post.evidence_text)), value_numbers(post))

    def test_no_internal_number_is_in_the_evidence(self):
        for rid, post in self.posts.items():
            with self.subTest(recipe=rid):
                text = post.evidence_text
                self.assertIsNone(re.search(r"[0-9a-f]{16}", text))
                self.assertIsNone(re.search(r"F[0-9]{2}", text))
                self.assertNotIn(M.PROVIDER_ID, text)
                self.assertNotIn(M.SOURCE_NAME, text)
                for item in (*post.facts_used, *post.derived):
                    self.assertNotIn(item.fact_id, text)
                for record in post.source_records:
                    self.assertNotIn(record.record_id, text)
                self.assertTrue(text.startswith("근거 자료(규칙 기반 조립, Fact 표)\n"))
                self.assertEqual(text.count("\n- "), len(post.facts_used) + len(post.derived))

    def test_every_number_that_is_not_a_value_is_caught_when_slipped_into_the_story(self):
        """id 의 숫자(0–9 와 두 자리 묶음)까지 포함해 값이 아닌 숫자는 하나도 본문에 끼워 넣을 수 없다 — 근거 텍스트에 id 를 다시 싣는 변이는 여기서 빨개진다."""
        for rid, post in self.posts.items():
            allowed = value_numbers(post)
            ids = [item.fact_id for item in (*post.facts_used, *post.derived)] + [record.record_id for record in post.source_records]
            id_numbers = {run for ident in ids for run in re.findall(r"[0-9]+", ident)}
            ghosts = sorted({str(n) for n in range(1, 200)} | id_numbers)
            ghosts = [ghost for ghost in ghosts if ghost not in allowed]
            self.assertGreater(len(ghosts), 100)
            self.assertTrue(id_numbers - allowed, "id 에 값이 아닌 숫자 묶음이 있어야 이 시험이 뜻이 있다")
            for ghost in ghosts:
                slipped = dataclasses.replace(post, body_markdown=post.body_markdown.replace("## 한눈에\n", f"## 한눈에\n\n- 몰래 넣은 값: {ghost}곳\n", 1))
                with self.subTest(recipe=rid, ghost=ghost):
                    self.assertIn("UNTRACED", [problem.split(" ", 1)[0] for problem in A.post_problems(slipped)])

    def test_the_check_also_refuses_a_post_whose_evidence_carries_internal_numbers(self):
        post = self.posts["R01_time_series"]
        for dirty in (post.evidence_text + f"- 내부 번호 {post.facts_used[0].fact_id}\n", post.evidence_text.replace("자료값", "자료값 F01_change")):
            with self.subTest(dirty=dirty[-30:]):
                self.assertIn("EVIDENCE", [problem.split(" ", 1)[0] for problem in A.post_problems(dataclasses.replace(post, evidence_text=dirty))])

    def test_the_formula_labels_have_no_digits_and_cover_every_formula(self):
        self.assertEqual(set(C.FORMULA_LABELS), set(C.FORMULAS))
        for formula_id, label in C.FORMULA_LABELS.items():
            self.assertIsNone(re.search(r"[0-9]", label), formula_id)
            self.assertTrue(label.strip() == label and label)


SHORT_VOCABULARY = dataclasses.replace(T.VOCABULARY, regions=T.VOCABULARY.regions | frozenset("가나다라마바"))      # 시험용: 한 글자 지역 이름도 허용(실제 허용 목록에는 없다)


def short(recipe):
    return dataclasses.replace(recipe, vocabulary=SHORT_VOCABULARY)


class PeriodWordsTest(unittest.TestCase):
    """V-04: 관측 개수를 기간으로 말하지 않는다 — 기간이 빠짐없이 이어질 때만 '개월·분기·년', 아니면 '관측 N개'."""

    def test_a_missing_month_makes_it_an_observation_count(self):
        periods = [p for p in months("2025-01", 15) if p != "2026-02"]                       # 앞 기간이 없으면 첫 문단이 '읽은 자료' 후보로 넘어간다
        facts = series(["3.4", "3.3", "3.3", "3.2", "3.1", "3.0", "3.0", "2.9", "2.9", "3.0", "3.1", "3.2", "3.3", "3.5"], periods=periods)
        r01 = run("R01_time_series", facts)
        self.assertIn("(이 글이 읽은 관측 14개 자료의 마지막 값)", r01.description)
        self.assertNotIn("14개월", r01.description + r01.body_markdown)
        r03 = run("R03_record_position", facts)
        self.assertIn("2025년 1월부터 2026년 3월까지 관측 14개입니다", r03.body_markdown)
        self.assertNotIn("개월입니다", r03.body_markdown)
        self.assertNotIn("15개월", r01.body_markdown + r03.body_markdown)

    def test_sparse_series_are_not_called_nine_months(self):
        periods = ["2010-01", "2012-05", "2014-09", "2016-02", "2018-07", "2020-03", "2022-11", "2025-12", "2026-03"]
        post = run("R03_record_position", series(["3.0", "3.4", "3.1", "2.8", "3.2", "3.5", "3.3", "3.1", "3.2"], periods=periods))
        self.assertIn("2010년 1월부터 2026년 3월까지 관측 9개입니다", post.body_markdown)
        self.assertNotIn("9개월", post.body_markdown)

    def test_unknown_values_inside_the_range_also_break_the_run(self):
        facts = series(["3.4", "3.3", "3.3", "3.2", None, "3.0", "2.9", "2.9", "3.0", "3.1", "3.2", "3.3", "3.2", "3.5", "3.6"])
        post = run("R03_record_position", facts)
        self.assertIn("관측 14개입니다", post.body_markdown)
        self.assertNotIn("개월입니다", post.body_markdown)

    def test_whole_runs_keep_the_period_words(self):
        facts = series(["3.4", "3.3", "3.3", "3.2", "3.0", "3.0", "2.9", "2.9", "3.0", "3.1", "3.2", "3.3", "3.2", "3.5"])
        self.assertIn("2025년 2월부터 2026년 3월까지 14개월입니다", run("R03_record_position", facts).body_markdown)
        quarters = series(["3.1", "3.0", "3.2", "3.3", "3.4", "3.1", "3.5", "3.6"], periods=["2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"])
        post = run("R03_record_position", quarters, today="2026-08-01")
        self.assertIn("2024년 3분기부터 2026년 2분기까지 8분기입니다", post.body_markdown)
        skipped = series(["3.1", "3.0", "3.3", "3.4", "3.1", "3.5", "3.6"], periods=["2024-Q3", "2024-Q4", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"])
        post = run(dataclasses.replace(R.R03_RECORD_POSITION, min_points=7), skipped, today="2026-08-01")
        self.assertIn("관측 7개입니다", post.body_markdown)
        self.assertNotIn("분기입니다", post.body_markdown)

    def test_the_short_first_paragraph_also_counts_observations_not_years(self):
        values = ["2.0", "2.1", "2.4", "2.2", "2.5", "2.6", "2.4", "2.8"]
        whole = series(values, periods=[str(y) for y in range(2018, 2026)], label="율", region_label="가")
        self.assertIn("이 글이 읽은 8년 자료의 마지막 값", run(short(R.R01_TIME_SERIES), whole, today="2026-06-01").description)
        holes = series(values[:-1] + ["2.9"], periods=["2017", "2018", "2019", "2021", "2022", "2023", "2024", "2025"], label="율", region_label="가")
        post = run(short(R.R01_TIME_SERIES), holes, today="2026-06-01")
        self.assertIn("이 글이 읽은 관측 8개 자료의 마지막 값", post.description)
        self.assertNotIn("8년", post.description)

    def test_every_period_count_in_a_record_post_is_true(self):
        rng = random.Random(7)
        regular = irregular = 0
        for _ in range(120):
            months_ = months("2025-01", 15)
            keep = sorted(rng.sample(range(15), rng.randint(8, 15)))
            if 14 not in keep:
                keep.append(14)
            periods = [months_[i] for i in keep]
            values = [str(Decimal(300 + rng.randint(-9, 9)) / 100) for _ in keep]
            post = run("R03_record_position", series(values, periods=periods))
            if isinstance(post, R.Insufficient):
                continue
            found = re.search(r"까지 (관측 )?([0-9]+)(개월|개)입니다", post.body_markdown)
            first, last = F.parse_as_of(periods[0]).ordinal, F.parse_as_of(periods[-1]).ordinal
            if last - first + 1 == len(periods):
                regular += 1
                self.assertEqual((found.group(1), found.group(3), int(found.group(2))), (None, "개월", len(periods)))
            else:
                irregular += 1
                self.assertEqual((found.group(1), found.group(3), int(found.group(2))), ("관측 ", "개", len(periods)))
        self.assertGreater(regular, 3)
        self.assertGreater(irregular, 60)


class RatioScaleTest(unittest.TestCase):
    """V-05: 0 이 임의인 구간척도(섭씨)와 순위에는 변화율(%)을 만들지 않는다 — 절대 차이만."""
    TEMPS = ["-5.5", "-3.2", "-0.5", "0.0", "1.2", "4.8", "8.0", "-1.0", "-2.5", "0.5", "3.3", "6.1"]

    def temps(self, **kw):
        return series(self.TEMPS, key="environment.temperature", unit="℃", label="평균기온", **kw)

    def test_a_temperature_series_has_no_percent_change_anywhere(self):
        post = run("R01_time_series", self.temps(), {"key": "environment.temperature"})
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertNotIn("변화율", post.title + post.description + post.body_markdown.replace("'바로 앞 기간 대비' 열은", "").replace("변화율은 계산하지 않았습니다", "").replace("증감·변화율·평균·순위", ""))
        self.assertEqual(len(table_rows(post)[0]), 3)
        self.assertNotIn("F02_pct_change", post.formulas)
        self.assertNotIn("F03_yoy", post.formulas)
        self.assertNotIn("%", re.sub(r"[0-9.]+%p", "", post.body_markdown.split("## 이 숫자를 읽을 때 주의")[0]).replace("(단위 %", ""))
        self.assertIn("이 단위는 기준점이 임의인 척도라 변화율은 계산하지 않았습니다.", post.body_markdown)
        self.assertEqual([item for item in post.skipped if item[1] in ("F02_pct_change", "F03_yoy")], [])           # 계산을 시도하지도 않았다
        self.assertIn("| 2026년 3월 | 6.1℃ | +2.8℃ |", post.body_markdown)

    def test_the_other_recipes_skip_the_ratio_too(self):
        record = run("R03_record_position", self.temps(), {"key": "environment.temperature"})
        self.assertIsInstance(record, A.AssembledPost, record)
        self.assertNotIn("변화율", record.body_markdown.replace("증감·변화율·평균·순위", ""))
        self.assertNotIn("F02_pct_change", record.formulas)
        self.assertEqual([item for item in record.skipped if item[1] in ("F02_pct_change", "F03_yoy")], [])           # 기록 글도 변화율은 계산을 시도하지도 않았다
        regional = run("R02_region_compare", cross(["-3.5", "-1.3", "2.9", "0.0", "-4.2", "1.1"], key="environment.temperature", unit="℃", label="평균기온"), {"key": "environment.temperature"})
        self.assertIsInstance(regional, A.AssembledPost, regional)
        self.assertNotIn("%", regional.body_markdown.split("## 이 숫자를 읽을 때 주의")[0])

    def test_percent_and_count_units_keep_their_ratio(self):
        for unit, key, label in (("%", H.UNEMP, "실업률"), ("명", "labour.employed_persons", "취업자 수"), ("원", "price.average_price", "평균가격")):
            post = run("R01_time_series", series(["30", "31", "32", "31", "33", "34", "35", "34", "36", "37", "36", "38"], unit=unit, key=key, label=label), {"key": key})
            with self.subTest(unit=unit):
                self.assertIsInstance(post, A.AssembledPost, post)
                self.assertIn("F02_pct_change", post.formulas)
                self.assertEqual(len(table_rows(post)[0]), 4)

    def test_calc_refuses_ratios_for_non_ratio_units(self):
        for unit in ("℃", "위", "%p", "Kp", "nT"):
            cur, ref = H.make_fact("3", unit=unit), H.make_fact("2", unit=unit, period="2026-02")
            with self.subTest(unit=unit):
                self.assertFalse(F.ratio_ok(unit))
                for result in (C.f02_pct_change(cur, ref), C.f03_yoy(cur, H.make_fact("2", unit=unit, period="2025-03")),
                               C.f05_share(H.make_fact("1", unit=unit), H.make_fact("2", unit=unit))):
                    self.assertIsInstance(result, C.Skipped)
                    self.assertEqual(result.reason, "NOT_A_RATIO_SCALE")
                self.assertIsInstance(C.f01_change(cur, ref), F.DerivedFact)                # 절대 차이는 만든다
        for unit in ("%", "명", "원", "점", "kWh", "미지정단위"):
            cur, ref = H.make_fact("3", unit=unit), H.make_fact("2", unit=unit, period="2026-02")
            with self.subTest(unit=unit):
                self.assertTrue(F.ratio_ok(unit))
                self.assertIsInstance(C.f02_pct_change(cur, ref), F.DerivedFact)
        self.assertTrue(F.ratio_ok(None) and F.ratio_ok(""))

    def test_the_unit_table_marks_exactly_these_units_as_non_ratio(self):
        self.assertEqual({unit for unit, spec in F.UNIT_TABLE.items() if not spec.ratio_ok}, {"위", "℃", "%p", "Kp", "nT", "단계"})        # 단계: 등급 단계는 순서척도(S2a)
        self.assertEqual(F.UNIT_DECIMALS["명"], 0)
        self.assertEqual(F.UNIT_DECIMALS["달러"], 2)


class TieTest(unittest.TestCase):
    """V-06: 동률인 최고·최저를 한 곳(한 기간)으로 단정하지 않는다 — '같은 값 N곳(번)'."""

    def test_region_ties_at_the_top_and_bottom(self):
        post = run("R02_region_compare", cross(["3.4", "3.6", "2.8", "3.8", "3.8", "3.8"]), {"key": H.UNEMP})                # 중앙값 3.7 — 반 칸이 아니다(N3: 3.5·3.5 였을 때는 중앙값 3.65 가 걸려 자리가 늘었다)
        self.assertNotIn("3.8", post.title)                                                    # 제목에는 값이 없다(D-200)
        self.assertIn("가장 높은 값은 3.8%(같은 값 3곳), 가장 낮은 곳은 가상 지역 다(2.8%)입니다", post.description)
        self.assertIn("- 가장 높은 값: 3.8%(같은 값 3곳)", post.body_markdown)
        self.assertIn("평균과 가장 높은 값의 차이는", post.body_markdown)
        for tied in ("가상 지역 라", "가상 지역 마", "가상 지역 바"):
            self.assertNotIn(tied, post.title + post.description)                      # 알파벳 순서 첫째를 '가장 높은 곳'으로 내세우지 않는다
        both = run("R02_region_compare", cross(["2.9", "2.9", "3.5", "3.8", "3.8", "3.3"]), {"key": H.UNEMP})                 # 중앙값 3.4(3.4 였을 때는 3.45 가 걸렸다)
        self.assertIn("가장 높은 값은 3.8%(같은 값 2곳), 가장 낮은 값은 2.9%(같은 값 2곳)입니다", both.description)
        self.assertIn("- 가장 낮은 값: 2.9%(같은 값 2곳)", both.body_markdown)
        self.assertIn("평균과 가장 높은 값의 차이는", both.body_markdown)
        self.assertIn("가장 낮은 값의 차이는", both.body_markdown)
        unique = run("R02_region_compare", cross(["3.5", "3.3", "2.9", "3.8", "4.2", "2.7"]), {"key": H.UNEMP})
        self.assertNotIn("(같은 값 ", unique.title + unique.description + unique.body_markdown)

    def test_a_comparison_where_every_region_is_equal_makes_no_post(self):
        result = run("R02_region_compare", cross(["3.5"] * 5), {"key": H.UNEMP})
        self.assertIsInstance(result, R.Insufficient)
        self.assertEqual(result.code, "NO_VARIATION")

    def test_the_latest_value_is_not_called_the_only_record_when_an_earlier_period_shares_it(self):
        flat_tail = run("R01_time_series", series(["3.0", "3.1", "3.5", "3.2", "3.1", "3.3", "3.2", "3.4", "3.5"]))
        self.assertIn("최신 값은 표에서 가장 높은 값과 같고, 그 값은 표에 2번 나옵니다.", flat_tail.body_markdown)
        self.assertNotIn("가장 높은 값이 바로 최신 값입니다", flat_tail.body_markdown)
        earlier = run("R01_time_series", series(["3.5", "3.1", "3.5", "3.2", "3.1", "3.3", "3.2", "3.4", "3.3"]))
        self.assertIn("표에서 가장 높은 값은 3.5%입니다. 이 값은 표에 2번 나오며 가장 나중은 2025년 9월입니다.", earlier.body_markdown)
        lowest = run("R01_time_series", series(["3.6", "3.1", "3.5", "3.2", "3.1", "3.3", "3.2", "3.4", "3.3"]))
        self.assertIn("가장 낮은 값은 3.1%입니다. 이 값은 표에 2번 나오며 가장 나중은 2025년 11월입니다.", lowest.body_markdown)
        sole = run("R01_time_series", series(["3.0", "3.1", "3.2", "3.2", "3.1", "3.3", "3.2", "3.4", "3.5"]))
        self.assertIn("표에서 가장 높은 값이 바로 최신 값입니다.", sole.body_markdown)

    def test_a_flat_table_does_not_name_a_highest_or_lowest_value(self):
        post = run("R01_time_series", series(["3.0"] * 9))
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertIn("표에 적은 값이 모두 같아 가장 높은 값과 가장 낮은 값을 가르지 않았습니다.", post.body_markdown)
        for text in ("표시한 기간 안의 범위", "가장 높은 값이 바로", "최저 3.0%", "최고 3.0%"):
            self.assertNotIn(text, post.title + post.description + post.body_markdown)

    def test_a_record_that_the_data_shares_with_an_earlier_period_is_called_equal(self):
        post = run("R03_record_position", series(["3.0", "3.1", "3.5", "3.2", "3.1", "3.3", "3.2", "3.4", "3.5"]))
        self.assertNotIn("3.5", post.title)
        self.assertIn("이 글이 읽은 자료(2025년 7월부터 2026년 3월까지) 안에서 가장 높은 값과 같은 3.5%입니다.", post.description)
        self.assertIn("최신 값이 이 기간에서 가장 높은 값과 같아 범위의 맨 위에 있고, 그 값은 자료에 2번 나옵니다.", post.body_markdown)
        low = run("R03_record_position", series(["3.5", "3.4", "3.4", "3.3", "3.2", "3.2", "3.1", "3.0", "3.0"]))
        self.assertIn("안에서 가장 낮은 값과 같은 3.0%입니다", low.description)
        self.assertIn("최신 값이 이 기간에서 가장 낮은 값과 같아 범위의 맨 아래에 있고, 그 값은 자료에 2번 나옵니다.", low.body_markdown)
        sole = run("R03_record_position", series(["3.5", "3.4", "3.4", "3.3", "3.2", "3.2", "3.1", "3.0", "2.8"]))
        self.assertIn("최신 값이 이 기간에서 가장 낮은 값이라 범위의 맨 아래에 있습니다.", sole.body_markdown)
        self.assertNotIn("나옵니다", sole.body_markdown)


class NeverRaisesTest(unittest.TestCase):
    """V-07: 어떤 입력에서도 예외 없이 글 또는 Insufficient 다 — 값이 범위를 넘으면 Insufficient, 예상 밖 오류도 글을 내보내지 않는 쪽으로 닫는다."""

    def test_changes_beyond_the_range_make_no_value_instead_of_an_exception(self):
        top = str(10 ** 15 - 1)
        a, b = H.make_fact(top, unit="명"), H.make_fact("-" + top, unit="명", period="2026-02")
        c1, c2 = H.make_fact("-" + top, unit="명", region="R02"), H.make_fact("-" + top, unit="명", region="R03")
        low_mean = C.f08_mean([c1, c2])
        for result in (C.f01_change(a, b), C.f13_gap(a, c1), C.f06_diff_from_mean(a, low_mean)):
            self.assertIsInstance(result, C.Skipped)
            self.assertEqual(result.reason, "VALUE_OUT_OF_RANGE")
        small_base = [H.make_fact("0.0001", unit="명", period="2026-02"), H.make_fact("100000000000000", unit="명")]
        result = C.f02_pct_change(small_base[1], small_base[0])
        self.assertIsInstance(result, C.Skipped)
        self.assertEqual(result.reason, "VALUE_OUT_OF_RANGE")
        near = [H.make_fact("500000000000000", unit="명"), H.make_fact("-499999999999999", unit="명", period="2026-02")]
        self.assertIsInstance(C.f01_change(near[0], near[1]), F.DerivedFact)               # 합이 1e15 아래면 만든다(경계 바로 아래)
        edge = [H.make_fact("500000000000000", unit="명"), H.make_fact("-500000000000000", unit="명", period="2026-02")]
        self.assertEqual(C.f01_change(edge[0], edge[1]).reason, "VALUE_OUT_OF_RANGE")                # 정확히 1e15 는 범위 밖

    def test_a_post_with_huge_changes_still_comes_out_or_is_refused_without_an_exception(self):
        for values in (["900000000000000", "-900000000000000"] * 4, ["0.0001", "100000000000000"] * 4, ["999999999999999", "0"] * 4):
            facts = series(values, unit="명", key="population.total", label="총인구", periods=ending(len(values)))
            result = run("R01_time_series", facts, {"key": "population.total"})
            self.assertTrue(isinstance(result, (A.AssembledPost, R.Insufficient)))
            if isinstance(result, A.AssembledPost):
                self.assertEqual(A.post_problems(result), [])
            else:
                self.assertNotIn(result.code, ("INTERNAL_ERROR", "PLAN_ERROR"))

    def test_the_value_limit_is_exact(self):
        self.assertEqual(F.to_decimal("999999999999999"), Decimal("999999999999999"))
        with self.assertRaises(F.FactFormatError):
            F.to_decimal("1000000000000000")
        self.assertEqual(F.validate_fact(H.make_fact("999999999999999")), [])
        self.assertIn("`value` 이(가) 너무 큼", F.validate_fact(dataclasses.replace(H.make_fact("1"), value=Decimal("1000000000000000"))))

    def test_unexpected_errors_close_toward_no_post(self):
        def boom(error):
            def plan(ctx):
                raise error
            return dataclasses.replace(R.R01_TIME_SERIES, plan=plan)
        cases = ((F.FactFormatError(["x"]), "VALUE_OUT_OF_RANGE"), (F.PrecisionLimit("x"), "PRECISION_LIMIT"), (F.UnitMismatch("x"), "PLAN_ERROR"),
                 (RuntimeError("x"), "INTERNAL_ERROR"), (KeyError("x"), "INTERNAL_ERROR"), (ZeroDivisionError(), "INTERNAL_ERROR"))
        for error, code in cases:
            with self.subTest(error=type(error).__name__):
                result = H.run(boom(error), params=H.R01_PARAMS)
                self.assertIsInstance(result, R.Insufficient)
                self.assertEqual(result.code, code)
                self.assertNotIn("x", result.detail.replace("PLAN", ""))                  # 오류 글은 싣지 않고 종류만
        with self.assertRaises(KeyboardInterrupt):                                          # 예외 전부가 아니라 프로그램 오류(Exception)만 닫는다
            H.run(boom(KeyboardInterrupt()), params=H.R01_PARAMS)

    def random_case(self, rng):
        examples = (("labour.unemployment_rate", "실업률", "%"), ("population.total", "총인구", "명"), ("environment.temperature", "평균기온", "℃"),
                    ("price.consumer_index", "소비자물가 지수", "점"), ("energy.demand", "전력수요", "MW"))
        key, label, unit = rng.choice(examples)
        count = rng.choice((0, 3, 6, 9, 12, 15, 20))
        magnitude = rng.choice((1, 10, 1000, 10 ** 6, 10 ** 12, 10 ** 14, 10 ** 15 - 1))
        places = rng.choice((0, 1, 2, 3, 4, 5))
        values = []
        for _ in range(count):
            roll = rng.random()
            if roll < 0.08:
                values.append(None)
            else:
                number = Decimal(rng.randint(-magnitude, magnitude)) / (Decimal(10) ** places)
                values.append(None if abs(number) >= Decimal(10) ** 15 else str(number))
        kind = rng.choice(("month", "month", "gap", "quarter", "year", "cross"))
        if kind == "cross":
            return key, label, unit, cross(values, key=key, unit=unit, label=label)
        if kind == "month":
            periods = ending(len(values))
        elif kind == "gap":
            periods = [p for p in ending(len(values) + 3) if rng.random() > 0.2][:len(values)]
            values = values[:len(periods)]
        elif kind == "quarter":
            periods = [f"{2024 + (i + 1) // 4:04d}-Q{(i + 1) % 4 + 1}" for i in range(len(values))]
            periods = periods[-len(values):] if values else []
        else:
            periods = [str(2026 - len(values) + 1 + i) for i in range(len(values))]
        return key, label, unit, series(values, periods=periods, key=key, label=label, unit=unit)

    def test_random_inputs_never_raise_and_never_end_in_an_internal_error(self):
        rng = random.Random(4242)
        posts = refused = 0
        for _ in range(700):
            key, label, unit, facts = self.random_case(rng)
            for rid in ("R01_time_series", "R02_region_compare", "R03_record_position"):
                try:
                    result = H.run(rid, facts=facts, params={"key": key}, today=rng.choice(("2026-04-20", "2026-12-31", "2027-06-01")))
                except Exception as exc:       # noqa: BLE001
                    self.fail(f"예외가 올라왔다: {type(exc).__name__}: {exc}")
                if isinstance(result, A.AssembledPost):
                    posts += 1
                    self.assertEqual(A.post_problems(result, allowed_latin=set(re.findall(r"[A-Za-z]{2,}", unit + label))), [])
                else:
                    refused += 1
                    self.assertIsInstance(result, R.Insufficient)
                    self.assertNotIn(result.code, ("INTERNAL_ERROR", "PLAN_ERROR"), (rid, result))
        self.assertGreater(posts, 100)
        self.assertGreater(refused, 100)



class SrcProviderShapeTest(unittest.TestCase):
    """V-08: SRC 의 Provider 모양과 맞물린다 — `exceptions`(감사 메모)는 읽지 않고, 독자용 문장은 `reader_notes` 뿐이며, 켜지지 않은(`enabled` 가 True 가 아닌) Provider 는 쓰지 않는다."""

    def src_like(self, **over):
        base = {name: getattr(M.MockProvider(), name) for name in F.PROVIDER_FIELDS}
        base.update(over)
        return types.SimpleNamespace(**base)

    def test_audit_memos_do_not_leak_and_do_not_block(self):
        memos = ("확인 못 함 — 이용 조건 원문을 2026-10-26 에 읽었고 오늘 다시 확인하지 못함", "공공누리 제1유형 표시 의무 확인 못 함", "약관 3곳 중 1곳만 읽음")
        provider = self.src_like(exceptions=memos)
        post = H.run("R01_time_series", params=H.R01_PARAMS, provider=provider)
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertNotIn("확인 못 함", post.body_markdown)
        self.assertNotIn("제공처 안내", post.body_markdown)                      # reader_notes 가 없으니 안내 줄도 없다
        self.assertEqual(A.post_problems(post), [])
        self.assertEqual(A.SourceInfo(provider, "이름", M.SOURCE_URL).reader_notes, ())

    def test_reader_notes_are_added_when_present(self):
        post = H.run("R01_time_series", params=H.R01_PARAMS, provider=self.src_like(reader_notes=("제3자 자료는 이 이용 허락에 포함되지 않습니다", "이미지와 로고는 제외됩니다.")))
        self.assertIn("- 제공처 안내: 제3자 자료는 이 이용 허락에 포함되지 않습니다.\n- 제공처 안내: 이미지와 로고는 제외됩니다.\n", post.body_markdown)
        self.assertEqual(A.post_problems(post), [])
        self.assertIsNone(re.search(r"[0-9]", post.body_markdown.split("제공처 안내")[1].split("\n")[0].replace("제3자", "")))

    def test_providers_that_are_not_enabled_are_not_used(self):
        for flag in (False, None, 0, "yes", "True"):
            with self.subTest(enabled=flag):
                result = H.run("R01_time_series", params=H.R01_PARAMS, provider=self.src_like(enabled=flag))
                self.assertIsInstance(result, R.Insufficient)
                self.assertEqual(result.code, "PROVIDER_NOT_ACTIVE")
                self.assertIn("켜져 있지 않음", F.provider_active_problem(self.src_like(enabled=flag)))
                with self.assertRaises(M.AdapterError):
                    M.MockStatsAdapter(self.src_like(enabled=flag))
        for provider in (self.src_like(enabled=True), self.src_like(), dataclasses.replace(M.MockProvider())):
            self.assertIsNone(F.provider_active_problem(provider))
            self.assertIsInstance(H.run("R01_time_series", params=H.R01_PARAMS, provider=provider), A.AssembledPost)
        self.assertIsNone(F.provider_active_problem({**{name: getattr(M.MockProvider(), name) for name in F.PROVIDER_FIELDS}, "enabled": True}))

    def test_a_label_that_says_automatable_is_not_enough_when_the_provider_is_off(self):
        result = H.run("R01_time_series", params=H.R01_PARAMS, provider=self.src_like(effective_status="자동화 가능", enabled=False))
        self.assertEqual(result.code, "PROVIDER_NOT_ACTIVE")


class NumberWordsTest(unittest.TestCase):
    """V-10: 틀에 우리말 수 표현(절반·곱절·두세 곳·열두 곳·첫 번째·삼 분기·백 퍼센트·영 이하 …)을 쓰지 않는다 — 숫자는 모두 참조 표시다."""
    FLAGGED = ("절반", "반 토막", "반토막", "곱절", "갑절", "두세 곳", "한두 개", "서너 곳", "열두 곳", "열한 개", "스물세 개", "스무 곳", "서른 명", "첫 번째", "첫째", "둘째", "셋째", "수십 곳",
               "수백 명", "수천 건", "몇 곳", "몇몇", "삼 분기", "삼십 퍼센트", "백 퍼센트", "이십삼 개월", "영 이하", "영 이상", "이분의 일", "첫 표", "둘째 표", "하나에도", "하나의 값",
               "두 배", "세 곳", "한 해", "네 번", "다섯 곳", "여섯 가지", "일곱 개", "여덟 명", "아홉 번", "열 곳", "대여섯 곳", "예닐곱 명", "셋 모두", "넷 중", "오십 퍼센트")
    CLEAN = ("한눈에", "이 글이 아는 것은 위 숫자뿐입니다", "이 기간에서 가장 높은 값", "하루", "오르내림", "이 값은 그대로", "세계 곳곳", "열차", "지역 규모 차이", "가장 최근 기간의 값",
             "표에 적은 값이 모두 같아", "그 값은 표에 나옵니다", "범위의 맨 위에 있습니다", "한쪽으로 치우쳐", "위쪽 표는 아래쪽 표", "플러스가 아니고", "기준점이 임의인 척도", "이 단위는",
             "같은 값 ", "최신 기간이 맨 위", "자료 없음", "해당 없음", "제3자 자료", "공공누리 제1유형")

    def test_every_such_expression_is_found(self):
        for text in self.FLAGGED:
            with self.subTest(text=text):
                self.assertTrue(F.untraced_numbers(f"앞 {text} 뒤"), text)
                self.assertTrue(F.untraced_numbers(text), text)

    def test_ordinary_wording_is_not_flagged(self):
        for text in self.CLEAN:
            with self.subTest(text=text):
                self.assertEqual(F.untraced_numbers(text), [], text)

    def test_the_templates_the_recipes_make_have_none(self):
        tested = 0
        for rid in H.GOLDEN:
            post = H.run(rid, params=H.GOLDEN[rid])
            self.assertEqual(F.untraced_numbers(post.template_markdown), [])
            tested += 1
        self.assertEqual(tested, 3)
        for text in (R.INTRO_TEMPLATE, R.NOTICE_TEMPLATE, *R.CAUTION_COMMON, R.intro_template("하루 최대값·개수·평균"), *R.caution_common("하루 최대값·개수·평균")):
            self.assertEqual(F.untraced_numbers(text), [], text)

    def test_other_script_numerals_are_still_found(self):
        for text in ("값 3", "값 ３", "값 ①", "값 ½", "값 一二", "값 ٣", "값 ३"):
            with self.subTest(text=text):
                self.assertTrue(F.untraced_numbers(text))


class TableAndExplanationTest(unittest.TestCase):
    """V-11: 표와 설명이 어긋나지 않는다 — 표의 첫·끝 기간, 최신 값이 모름인 때의 안내, 지역이 12곳을 넘을 때의 안내, 빠진 기간 안내."""

    def test_the_caption_range_is_the_range_of_the_table(self):
        values = ["3.4", "3.3", "3.3", "3.2", "3.1", "3.0", "3.0", "2.9", "2.9", "3.0", "3.1", "3.2", "3.3", "3.2", None]
        post = run("R01_time_series", series(values))
        self.assertIn("가상 지역 가의 실업률 값을 2025년 3월부터 2026년 3월까지 보여 줍니다", post.body_markdown)
        rows = table_rows(post)
        self.assertEqual((rows[0][0], rows[-1][0]), ("2026년 3월", "2025년 3월"))
        self.assertEqual(rows[0][1:], ["자료 없음", "해당 없음", "해당 없음"])
        self.assertIn("가장 최근 기간(2026년 3월)의 값은 자료에 없어, 값이 있는 마지막 기간 2026년 2월 기준으로 최신 값을 정했습니다.", post.body_markdown)
        self.assertIn("2025년 3월부터 2026년 3월까지", post.title)                  # 제목의 기간은 표의 처음·끝 줄(D-200)
        self.assertIn("2026년 2월 기준", post.description)
        whole = run("R01_time_series", series(values[:-1] + ["3.5"]))
        self.assertNotIn("값이 있는 마지막 기간", whole.body_markdown)
        self.assertIn("2025년 4월부터 2026년 3월까지 보여 줍니다", whole.body_markdown)

    def test_two_trailing_unknown_periods_are_explained_with_the_last_row(self):
        values = ["3.4", "3.3", "3.3", "3.2", "3.1", "3.0", "3.0", "2.9", "2.9", "3.0", "3.1", "3.2", "3.3", None, None]
        post = run("R01_time_series", series(values))
        self.assertIn("2026년 3월까지 보여 줍니다", post.body_markdown)
        self.assertIn("가장 최근 기간(2026년 3월)의 값은 자료에 없어, 값이 있는 마지막 기간 2026년 1월 기준으로", post.body_markdown)
        self.assertEqual([row[0] for row in table_rows(post)][:3], ["2026년 3월", "2026년 2월", "2026년 1월"])

    def test_a_period_missing_from_the_source_is_explained_as_skipped(self):
        periods = [p for p in months("2025-01", 15) if p != "2025-06"]
        post = run("R01_time_series", series(["3.4", "3.3", "3.3", "3.2", "3.1", "3.0", "2.9", "3.0", "3.1", "3.2", "3.3", "3.2", "3.5", "3.6"], periods=periods))
        rows = [row[0] for row in table_rows(post)]
        self.assertIn("2025년 5월", rows)
        self.assertNotIn("2025년 6월", rows)                                     # 사실 자체가 없는 기간은 표에서 건너뛴다
        self.assertIn("제공처 자료에 기간 자체가 없으면 표에서 건너뜁니다", post.body_markdown)           # 그 사실을 글이 말한다
        self.assertIn("값이 비어 있는 기간은 '자료 없음'으로 적고", post.body_markdown)

    def test_more_than_twelve_regions_are_explained(self):
        values = [str(Decimal(30 + (i * 37) % 23) / 10) for i in range(15)]
        post = run("R02_region_compare", cross(values), {"key": H.UNEMP})
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertEqual(len(rank_rows(post)), 12)
        self.assertIn("표에는 값이 높은 12곳만 적었고(전체 15곳), 아래 목록도 표에 적은 곳만 적었습니다.", post.body_markdown)
        shown = {row[1] for row in rank_rows(post)}
        listed = {name.strip() for line in post.body_markdown.split("\n") if line.startswith(("- 평균보다 높은 곳:", "- 평균보다 낮은 곳:")) for name in line.split(":", 1)[1].split(",")}
        self.assertTrue(listed and listed <= shown, listed - shown)
        for line in post.body_markdown.split("\n"):
            if line.startswith("- 평균보다 높은 곳 "):
                counts = re.search(r"평균보다 높은 곳 ([0-9]+)곳, 낮은 곳 ([0-9]+)곳", line)           # 개수는 표가 아니라 전체(15곳) 기준이다
                self.assertTrue(13 <= int(counts.group(1)) + int(counts.group(2)) <= 15)
        few = run("R02_region_compare", cross(["3.5", "3.3", "2.9", "3.8", "4.2", "2.7"]), {"key": H.UNEMP})
        self.assertNotIn("표에는 값이 높은", few.body_markdown)

    def test_exactly_twelve_regions_need_no_note(self):
        post = run("R02_region_compare", cross([str(Decimal(30 + i) / 10) for i in range(12)]), {"key": H.UNEMP})
        self.assertEqual(len(rank_rows(post)), 12)
        self.assertNotIn("표에는 값이 높은", post.body_markdown)


class NoRegionTest(unittest.TestCase):
    """V-13: 지역이 없는 계열은 R01·R03 이 `RENDER_ERROR` 로 끝나지 않고 이유를 말한다(`NO_REGION_SERIES`) — 지역 없는 틀은 2단계."""

    def regionless(self):
        return [H.make_fact(v, period=p, region=None, level=None, region_label=None, record_id=RECORD_ID)
                for v, p in zip(["3.1", "3.2", "3.3", "3.2", "3.4", "3.5", "3.6", "3.5", "3.7"], ending(9))]

    def test_a_series_without_regions_says_so(self):
        for rid in ("R01_time_series", "R03_record_position", "R02_region_compare"):
            with self.subTest(recipe=rid):
                result = run(rid, self.regionless())
                self.assertIsInstance(result, R.Insufficient)
                self.assertEqual(result.code, "NO_REGION_SERIES")
                self.assertTrue(result.detail)

    def test_a_series_with_regions_is_still_picked_when_both_are_present(self):
        mixed = self.regionless() + series(["3.1", "3.2", "3.3", "3.2", "3.4", "3.5", "3.6", "3.5", "3.7"])
        post = run("R01_time_series", mixed)
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertIn("가상 지역 가", post.title)

    def test_a_blocked_topic_is_reported_before_the_missing_region(self):
        facts = self.regionless()
        bad = [H.make_fact(v, key="health.cases", period=p, region=None, level=None, region_label=None, record_id=RECORD_ID) for v, p in zip(["1"] * 9, ending(9))]
        self.assertEqual(run("R01_time_series", facts + bad).code, "TOPIC_NOT_ALLOWED")                       # 정책으로 막힌 계열의 사유가 먼저다
        self.assertEqual(run("R01_time_series", facts + bad, {"key": H.UNEMP}).code, "NO_REGION_SERIES")        # 키를 지정하면 그 계열의 사유(지역 없음)가 나온다
        self.assertEqual(run("R01_time_series", bad, {"key": "health.cases"}).code, "TOPIC_NOT_ALLOWED")


class SurvivorsTest(unittest.TestCase):
    """V-14: 독립 검증이 찾은 생존 변이 — 시험 구멍을 하나씩 막는다(동치·죽은 코드는 코드에서 지웠다)."""

    def test_internal_rounding_is_half_even(self):
        self.assertEqual(C._quant(Decimal("0.0000000000025")), Decimal("0.000000000002"))              # N09: 12번째 자리의 동률은 짝수 쪽(표시 반올림은 0 에서 먼 쪽)
        self.assertEqual(C._quant(Decimal("0.0000000000035")), Decimal("0.000000000004"))
        self.assertEqual(F.round_display(Decimal("0.25"), 1), Decimal("0.3"))
        self.assertEqual(F.NUMBER_POLICY["internal_rounding"], "ROUND_HALF_EVEN")

    def test_every_agreed_forbidden_phrase_is_still_in_the_list(self):
        """N12·N14: 규칙을 지워도 시험이 통과하던 구멍 — 합의한 금지 표현 전체를 시험이 따로 적어 둔다(목록에서 하나를 지우면 빨갛다)."""
        agreed = {
            "건강": ("치료", "완치", "처방", "복용", "예방 효과", "효능", "부작용", "환자", "질환", "질병", "증상", "진단"),
            "단정": ("보장", "반드시", "확실히", "확실하게", "무조건", "틀림없이", "분명히", "단언", "명백히", "의심의 여지"),
            "즉시 효과": ("즉시 효과", "바로 효과", "즉각적인 효과", "당장 효과"),
            "과장": ("역대급", "폭등", "폭락", "급등", "급락", "사상 최고", "사상 최저", "충격", "대박", "놀라운", "경악", "쇼크", "초유", "전무후무"),
            "원인 단정": ("때문입니다", "때문에", "때문이다", "탓입니다", "덕분에", "덕분입니다", "원인은", "영향으로", "로 인해", "으로 인해", "으로 인한"),
            "투자·권유": ("투자 추천", "매수", "매도", "수익률", "유망", "사야 합니다", "팔아야", "추천합니다", "권합니다", "권유", "주식", "코인", "펀드", "증권"),
            "법률": ("위법입니다", "불법입니다", "처벌", "법적 책임", "소송", "판결", "재판"),
            "예측": ("예상됩니다", "전망됩니다", "전망입니다", "예측됩니다", "오를 것", "내릴 것", "곧 오", "계속 오"),
            "번역투": ("에 의해", "를 통해", "을 통해", "에 대한", "것으로 나타났"),
        }
        self.assertEqual({category: tuple(phrases) for category, phrases in R.FORBIDDEN_PHRASES.items()}, agreed)
        for category, phrases in agreed.items():
            for phrase in phrases:
                with self.subTest(phrase=phrase):
                    self.assertIn((category, phrase), A.forbidden_found(f"앞 {phrase} 뒤"))
                    caught = {found for _category, found in A.forbidden_found(f"앞 {' '.join(phrase.replace(' ', ''))} 뒤")}
                    if len(phrase.replace(" ", "")) >= 2:
                        self.assertIn(phrase, caught)                                   # 글자 사이를 띄워 써도 같다

    def test_the_description_must_be_one_sentence(self):
        """N15: 설명 '한 문장' 규칙 — 길이가 맞아도 문장이 둘이거나 물음·느낌표거나 마침표가 없으면 거절한다(첫 문단도 같이 바꿔 '첫 문단과 같음' 검사에 가려지지 않게)."""
        post = H.run("R01_time_series", params=H.R01_PARAMS)
        body = post.body_markdown
        message = "DESCRIPTION 설명이 한 문장(60자 이상 155자 이하)이 아님"
        base = "가" * 70
        cases = ((base + ".", True), (base + ". " + base + ".", False), (base + "?", False), (base + "!", False), (base, False), (base + ". ", False), ("가" * 40 + ". " + "나" * 40 + ".", False),
                 ("값은 3.5%입니다 " + base + ".", True), ("가" * 70 + "\n" + "나" * 20 + ".", False))
        for description, ok in cases:
            changed = dataclasses.replace(post, description=description, body_markdown=body.replace(post.description, description, 1))
            with self.subTest(description=description[:20] + "…", ok=ok):
                self.assertEqual(message in A.post_problems(changed), not ok)

    def test_the_provider_of_a_record_must_match_the_provider_of_the_facts(self):
        """N42: Fact 가 가리키는 출처 기록의 Provider 가 다르면 INVALID_FACTS — 그 검사를 지워도 시험이 통과하던 구멍."""
        provider, record, facts = H.mock_bundle()
        other = F.SourceRecord.create("other_stats", record.access_kind, record.request_url, record.retrieved_at, record.response_hash, record.license_snapshot, record.retention_days)
        pointing = [F.Fact.create(f.provider_id, other.record_id, f.kind, f.key, f.value, f.unit, f.as_of, f.region, f.region_level, f.region_label_ko,
                                  f.region_label_en, f.label_ko, f.label_en) for f in facts]
        result = H.run("R01_time_series", facts=pointing, records=[other], params=H.R01_PARAMS)
        self.assertIsInstance(result, R.Insufficient)
        self.assertEqual(result.code, "INVALID_FACTS")
        self.assertIn("Provider", result.detail)

    def test_the_region_recipe_has_no_unreachable_guard_left(self):
        """N41: 같은 묶음이면 평균·중앙값을 늘 만들 수 있다 — 도달할 수 없던 `NOT_COMPARABLE` 방어선은 지웠고, 계산 칸이 비면 틀 단계에서 글이 거절된다."""
        import inspect
        self.assertNotIn("NOT_COMPARABLE", inspect.getsource(R.plan_region_compare))
        original = C.f08_mean
        try:
            C.f08_mean = lambda group: C.Skipped("F08_mean", "TOO_FEW_INPUTS")
            result = run("R02_region_compare", cross(["3.5", "3.3", "2.9", "3.8", "4.2", "2.7"]), {"key": H.UNEMP})
        finally:
            C.f08_mean = original
        self.assertIsInstance(result, R.Insufficient)
        self.assertIn(result.code, ("RENDER_ERROR", "TEMPLATE_UNTRACED", "PLAN_ERROR"))



class CalcHardeningTest(unittest.TestCase):
    """L-04: 계산 층이 지역이 다른 값끼리의 시간 비교와 같은 입력을 두 번 넣은 묶음을 스스로 거절한다(Recipe 가 막아 주는 동안만 안전하던 구멍)."""

    def assertSkipped(self, result, formula_id, reason):
        self.assertIsInstance(result, C.Skipped)
        self.assertEqual((result.formula_id, result.reason), (formula_id, reason))

    def test_changes_need_the_same_region(self):
        cur = H.make_fact("3.5")
        other = H.make_fact("3.1", period="2026-02", region="R02", region_label="가상 지역 나")
        self.assertSkipped(C.f01_change(cur, other), "F01_change", "REGION_MISMATCH")
        self.assertSkipped(C.f02_pct_change(cur, other), "F02_pct_change", "REGION_MISMATCH")
        self.assertSkipped(C.f03_yoy(cur, H.make_fact("3.1", period="2025-03", region="R02", region_label="가상 지역 나")), "F03_yoy", "REGION_MISMATCH")
        self.assertSkipped(C.f01_change(cur, H.make_fact(None, period="2026-02", region="R02")), "F01_change", "MISSING_VALUE")          # 앞선 사유(모름)가 가려지지 않는다
        self.assertSkipped(C.f01_change(cur, H.make_fact("3.1", period="2026-02", unit="명", region="R02")), "F01_change", "UNIT_MISMATCH")
        same = H.make_fact("3.1", period="2026-02")
        for result in (C.f01_change(cur, same), C.f02_pct_change(cur, same), C.f03_yoy(cur, H.make_fact("3.1", period="2025-03"))):
            self.assertIsInstance(result, F.DerivedFact)
        self.assertIsInstance(C.f01_change(cur, C.f09_max([H.make_fact("3.9", period="2025-12"), H.make_fact("3.2", period="2026-01")]), require="any"), F.DerivedFact)   # 같은 지역의 최고와는 비교한다
        self.assertTrue(C.REASON_TEXT["REGION_MISMATCH"] and C.REASON_TEXT["DUPLICATE_INPUT"])

    def test_the_same_input_twice_is_not_a_group(self):
        a, b, c = H.make_fact("3.5"), H.make_fact("3.1", region="R02"), H.make_fact("2.9", region="R03")
        for name, result in (("F08", C.f08_mean([a, a, b])), ("F14", C.f14_median([a, a, b])), ("F04", C.f04_rank(a, [a, a, b])), ("F09", C.f09_max([a, a])),
                             ("F10", C.f10_min([b, b])), ("F11", C.f11_range_position(a, [a, a, b, c]))):
            with self.subTest(name=name):
                self.assertIsInstance(result, C.Skipped)
                self.assertEqual(result.reason, "DUPLICATE_INPUT")
        for result in (C.f08_mean([a, b, c]), C.f14_median([a, b, c]), C.f04_rank(a, [a, b, c]), C.f09_max([a, b, c]), C.f11_range_position(a, [a, b, c])):
            self.assertIsInstance(result, F.DerivedFact)


class HygieneTest(unittest.TestCase):
    """L-01·L-03·L-05: id 가 decimal 전역 문맥에 의존하지 않는다 · 실패 사유가 해시 시드와 무관하다 · 숫자는 아라비아 숫자만."""

    def test_ids_do_not_depend_on_the_decimal_context(self):
        import decimal
        before = [H.make_fact(value).fact_id for value in ("123456.789", "0.000123", "3.50", "-45.5", "999999999999999")]
        canon = [F.canonical_number(Decimal(value)) for value in ("123456.789", "0.000123", "3.50", "1E+2", "-0")]
        with decimal.localcontext() as ctx:
            ctx.prec, ctx.rounding = 4, decimal.ROUND_DOWN
            after = [H.make_fact(value).fact_id for value in ("123456.789", "0.000123", "3.50", "-45.5", "999999999999999")]
            self.assertEqual([F.canonical_number(Decimal(value)) for value in ("123456.789", "0.000123", "3.50", "1E+2", "-0")], canon)
            self.assertEqual(F.value_decimals(Decimal("123456.789")), 3)
        self.assertEqual(before, after)
        self.assertEqual(canon, ["123456.789", "0.000123", "3.5", "100", "0"])
        for value in ("123456.789", "0.000123"):
            fact = H.make_fact(value)
            self.assertEqual(F.validate_fact(fact), [])

    def test_values_with_too_many_digits_are_refused(self):
        self.assertEqual(F.to_decimal("123456789012345.1234567890123456789012345"), Decimal("123456789012345.1234567890123456789012345"))            # 40 자리
        with self.assertRaises(F.FactFormatError):
            F.to_decimal("123456789012345.12345678901234567890123456")                                                                          # 41 자리
        self.assertEqual(F.NUMBER_POLICY["max_digits"], 40)
        self.assertLess(F.NUMBER_POLICY["max_digits"], F.NUMBER_POLICY["precision"])

    def test_only_ascii_digits_are_numbers_and_dates(self):
        for text in ("３.５", "٣", "३", "１２", "3.５"):
            with self.subTest(text=text):
                with self.assertRaises(F.FactFormatError):
                    F.to_decimal(text)
        for text in ("２０２５", "２０２５-03", "2025-０3", "２０２５-Q1", "2025-03-０1", "2025-03-01T0９:00:00Z"):
            with self.subTest(text=text):
                self.assertIsNone(F.parse_as_of(text))
        self.assertIsNotNone(F.parse_as_of("2025-03-01T09:00:00Z"))
        self.assertEqual(F.to_decimal("3.5"), Decimal("3.5"))

    def test_the_reason_does_not_depend_on_the_hash_seed(self):
        """문제가 둘 겹쳐도(출처 기록 없음·기한 지남) 실패 사유 코드는 해시 시드와 무관하게 같다."""
        import os
        import subprocess
        import sys
        code = ("import sys\nsys.path.insert(0, sys.argv[1])\nsys.path.insert(0, sys.argv[1] + '/tests')\nimport fact_helpers as H\nfrom pipeline import facts as F\n"
                "provider, record, facts = H.mock_bundle()\n"
                "other = F.SourceRecord.create('mock_stats', 'api', record.request_url, '2024-01-02T00:00:00Z', 'c' * 64, record.license_snapshot, 30)\n"
                "mixed = [F.Fact.create(f.provider_id, other.record_id if i % 2 else f.source_record_id, f.kind, f.key, f.value, f.unit, f.as_of, f.region, f.region_level,\n"
                "                       f.region_label_ko, f.region_label_en, f.label_ko, f.label_en) for i, f in enumerate(facts)]\n"
                "missing = [F.Fact.create(f.provider_id, 's' + '1' * 16, f.kind, f.key, f.value, f.unit, f.as_of, f.region, f.region_level, f.region_label_ko, f.region_label_en,\n"
                "                         f.label_ko, f.label_en) if i % 3 == 0 else f for i, f in enumerate(mixed)]\n"
                "result = H.run('R01_time_series', facts=missing, records=[record, other], params=H.R01_PARAMS)\n"
                "print(result.code if hasattr(result, 'code') else 'POST')\n")
        outputs = set()
        for seed in ("0", "1", "42", "31337"):
            done = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", code, str(_bootstrap.ROOT)], capture_output=True, text=True, timeout=240,
                                  env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONUTF8="1"))
            self.assertEqual(done.returncode, 0, done.stderr[-400:])
            outputs.add(done.stdout.strip())
        self.assertEqual(len(outputs), 1, outputs)
        self.assertIn(outputs.pop(), ("MISSING_RECORD", "RETENTION_EXPIRED"))

    def test_a_record_dated_after_today_is_not_used(self):
        provider, record, facts = H.mock_bundle()
        result = H.run("R01_time_series", params=H.R01_PARAMS, today="2026-04-17")
        self.assertIsInstance(result, R.Insufficient)
        self.assertEqual(result.code, "FUTURE_RECORD")
        self.assertIsInstance(H.run("R01_time_series", params=H.R01_PARAMS, today="2026-04-18"), A.AssembledPost)


class QualityMeasurementTest(unittest.TestCase):
    """글 품질 평가(검증자 의견)를 숫자로 잰다: 분량·주의 절을 뺀 분량·틀 고정 글자 비율 — 문서 §13 의 표가 이 값과 같음을 문서 시험이 확인한다."""

    def test_the_golden_posts_are_measured(self):
        for rid, params in H.GOLDEN.items():
            post = H.run(rid, params=params)
            metrics = H.quality_metrics(post)
            with self.subTest(recipe=rid):
                self.assertGreaterEqual(metrics["story"], R.MIN_STORY_CHARS)
                self.assertEqual(metrics["story"] - metrics["caution"], metrics["pure"])
                self.assertTrue(0 < metrics["caution"] < metrics["story"])
                self.assertTrue(0 < metrics["fixed"] < metrics["story"])
                self.assertEqual(metrics["fixed_percent"], round(100 * metrics["fixed"] / metrics["story"]))
                self.assertLess(metrics["pure"], R.MIN_STORY_CHARS)             # 정직한 측정: 주의 절을 빼면 세 편 모두 하한(1,000자)에 못 미친다 — 분량의 상당 부분이 고정 문장이다


# ----------------------------------------------------------------------------
# 병합 뒤 후속 수정(재검증 D3–D12) 회귀 시험. 환경(전역 decimal 문맥·재귀 한계·경로·파일)에 기대지 않는다 — 문맥은 시험 안에서 `decimal.localcontext` 로 명시해 바깥에 씌운다
# ----------------------------------------------------------------------------
HOSTILE_CONTEXTS = (
    ("정밀도 5", decimal.Context(prec=5)),
    ("정밀도 10", decimal.Context(prec=10)),
    ("정밀도 28", decimal.Context(prec=28)),
    ("정밀도 50", decimal.Context(prec=50)),
    ("버림", decimal.Context(prec=7, rounding=decimal.ROUND_DOWN)),
    ("올림·좁은 지수 범위", decimal.Context(prec=12, rounding=decimal.ROUND_CEILING, Emin=-30, Emax=30)),
    ("깎일 때마다 오류", decimal.Context(prec=6, rounding=decimal.ROUND_HALF_DOWN,
                                    traps=[decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow, decimal.Inexact, decimal.Rounded])),
)


def shown_number(text):
    """글에 보인 숫자 글자('+0.05%p'·'−0.5명'·'1,234.5') → Decimal."""
    return Decimal(text.replace("−", "-").replace("+", "").replace(",", "").rstrip("%p명곳℃위개월분기년번"))


class ExactContextTest(unittest.TestCase):
    """D5(D-150): 계산·표시·해시는 호출한 쪽의 decimal 전역 정밀도·반올림·지수 한계·함정에 기대지 않는다 — 전역 정밀도 5 에서 `1,234,567.1` 이 `1,234,600.0` 이 되던 일.
    서브프로세스 없이, 시험 안에서 문맥을 명시해 바깥에 씌운다(리눅스·윈도우 같다)."""

    def under_each(self, compute):
        """compute() 를 정해 둔 문맥에서 한 번(기준), 어지럽힌 바깥 문맥마다 한 번씩 돌려 모두 같은지 본다. 기준 결과를 돌려준다."""
        with decimal.localcontext(decimal.Context(prec=60)):
            expected = compute()
        for name, ctx in HOSTILE_CONTEXTS:
            with self.subTest(context=name):
                with decimal.localcontext(ctx):
                    self.assertEqual(compute(), expected)
        return expected

    def test_the_verifiers_minimal_example_keeps_every_digit(self):
        big = Decimal("1234567.1")
        shown = self.under_each(lambda: (F.format_decimal(big, 1), F.format_decimal(big.copy_negate(), 1, signed=True), F.format_decimal(big, 1, absolute=True), F.format_with_unit(big, "%"),
                                         F.round_display(big, 0), F.display_sign(Decimal("0.05"), "%p"), F.canonical_number(Decimal("123456789.123456789")),
                                         F.value_decimals(Decimal("1234567.123456")), F.to_decimal("123456789012.5"), F.display_context([H.make_fact("1234567.12", unit="명")])))
        self.assertEqual(shown[:4], ("1,234,567.1", "−1,234,567.1", "1,234,567.1", "1,234,567.1%"))
        self.assertEqual((shown[4], shown[5], shown[6], shown[7], shown[8]), (Decimal("1234567"), 1, "123456789.123456789", 6, Decimal("123456789012.5")))
        self.assertEqual(shown[9], {"명": 2})

    def test_every_formula_gives_the_same_result_under_any_outer_context(self):
        make = lambda value, **kw: H.make_fact(value, unit="명", key="labour.employed_persons", label="취업자 수", **kw)          # noqa: E731
        cur, ref, prior = make("1234567.1234", period="2026-03"), make("1234501.9876", period="2026-02"), make("1200000.5555", period="2025-03")
        group = [make(v, region=f"R0{i}", region_label=f"가상 지역 {SYLLABLES[i]}")
                 for i, v in enumerate(("1234567.1234", "2345678.2345", "3456789.3456", "4567890.4567", "5678901.5678", "6789012.6789"), start=1)]
        window = [make(v, period=p) for v, p in zip(("1111111.1111", "2222222.2222", "3333333.3333"), ("2026-01", "2026-02", "2026-03"))]

        def compute():
            mean = C.f08_mean(group)
            results = [C.f01_change(cur, ref), C.f02_pct_change(cur, ref), C.f03_yoy(cur, prior), C.f04_rank(group[2], group), C.f05_share(group[0], group[5]), mean,
                       C.f06_diff_from_mean(group[1], mean), C.f07_rolling_mean(window), C.f09_max(group), C.f10_min(group), C.f11_range_position(group[2], group),
                       C.f12_count(group, "곳"), C.f13_gap(group[5], group[0]), C.f14_median(group), C.select_extreme(group, highest=True), C.select_extreme(group, highest=False)]
            return [(type(item).__name__, item.fact_id, str(item.value)) for item in results]

        baseline = self.under_each(compute)
        self.assertEqual(len(baseline), 16)
        self.assertEqual({entry[0] for entry in baseline}, {"DerivedFact", "Fact"})                    # 어느 계산식도 Skipped 가 아니다

    def test_posts_are_identical_under_any_outer_context(self):
        values = ["1234567.1", "1234601.3", "1234590.7", "1234655.2", "1234640.9", "1234702.4", "1234688.8", "1234733.5", "1234790.6"]
        kw = {"unit": "명", "key": "labour.employed_persons", "label": "취업자 수"}
        timeline = series(values, **kw)
        regions = cross(["2345678.1", "1234567.3", "3456789.5", "4567890.7", "5678901.9", "6789012.3"], **kw)

        def compute():
            return (run("R01_time_series", timeline, {"key": kw["key"]}), run("R02_region_compare", regions, {"key": kw["key"]}), run("R03_record_position", timeline, {"key": kw["key"]}))

        posts = self.under_each(compute)
        for post in posts:
            self.assertIsInstance(post, A.AssembledPost, post)
            self.assertEqual(A.post_problems(post), [])
        self.assertIn("1,234,790.6명", posts[0].body_markdown)                 # 끝 자리가 깎이지 않는다(전역 정밀도 5 에서는 `1,234,800.0`)
        self.assertIn("6,789,012.3명", posts[1].body_markdown)
        self.assertIn("1,234,567.1명", posts[2].body_markdown)

    def test_the_decorator_pins_precision_rounding_range_and_traps(self):
        @F.exact
        def probe():
            ctx = decimal.getcontext()
            return (ctx.prec, ctx.rounding, ctx.Emax, ctx.Emin, bool(ctx.traps[decimal.Inexact]), bool(ctx.traps[decimal.InvalidOperation]), bool(ctx.traps[decimal.DivisionByZero]))

        pinned = self.under_each(probe)
        self.assertEqual(pinned[:2], (F.NUMBER_POLICY["precision"], decimal.ROUND_HALF_EVEN))
        self.assertTrue(pinned[2] >= 999999 and pinned[3] <= -999999)
        self.assertEqual(pinned[4:], (False, True, True))
        for function in (F.format_decimal, F.to_decimal, C.f01_change, C.f09_max, R.plan_time_series, A.assemble):
            self.assertEqual(function.__name__, function.__wrapped__.__name__)         # functools.wraps — 이름·독스트링이 그대로
            self.assertTrue(function.__doc__ is None or function.__doc__ == function.__wrapped__.__doc__)

    def test_sort_keys_do_not_round_either(self):
        """내림차순 정렬 키의 단항 `-` 가 전역 정밀도로 반올림하면 값이 거의 같은 두 지역의 순서가 바뀐다."""
        regions = cross(["1234567.1234", "1234567.1235", "1234567.1236", "1234567.1237"], unit="명", key="labour.employed_persons", label="취업자 수")

        def order():
            post = run("R02_region_compare", regions, {"key": "labour.employed_persons"})
            return [row[1] for row in rank_rows(post)]

        self.assertEqual(self.under_each(order), ["가상 지역 라", "가상 지역 다", "가상 지역 나", "가상 지역 가"])


class HalfStepTest(unittest.TestCase):
    """D6(D-152): 지역이 짝수 곳이라 평균이 표시 자리의 반 칸에 정확히 걸치면(값 3.4·3.4·3.5·3.5 의 평균 3.45) 그 단위의 표시 자리를 한 칸 늘려 반올림 없이 보인다 —
    평균은 3.5%, 3.5% 인 지역은 평균보다 +0.1%p 높다는 글이 나오지 않는다."""

    def test_is_half_tie(self):
        for value, places, expected in (("3.45", 1, True), ("3.5", 1, False), ("-3.45", 1, True), ("3.425", 2, True), ("3.425", 1, False), ("3.45", 2, False), ("0.5", 0, True),
                                        ("4.5", 0, True), ("4", 0, False), ("0.05", 1, True), ("0.15", 1, True), ("2.675", 2, True), ("3.4500", 1, True), ("3.451", 1, False)):
            with self.subTest(value=value, places=places):
                self.assertEqual(F.is_half_tie(Decimal(value), places), expected)

    def test_settle_context_adds_a_digit_only_where_a_value_sits_on_a_half_step(self):
        item = lambda value, unit="%": types.SimpleNamespace(value=Decimal(value), unit=unit)          # noqa: E731
        base = {"%": 1, "%p": 1, "명": 0}
        before = dict(base)
        self.assertEqual(F.settle_context(base, [item("3.45")]), {"%": 2, "%p": 2, "명": 0})
        self.assertEqual(base, before)                                                      # 받은 사전은 바꾸지 않고 새 사전을 돌려준다
        self.assertEqual(F.settle_context(base, [item("3.46")]), base)
        self.assertEqual(F.settle_context(base, []), base)
        self.assertEqual(F.settle_context(base, [item("0.05", "%p")]), {"%": 2, "%p": 2, "명": 0})          # %p 가 걸리면 % 도 같이
        self.assertEqual(F.settle_context(base, [item("4.5", "명")]), {"%": 1, "%p": 1, "명": 1})
        self.assertEqual(F.settle_context(base, [item("-4.5", "명")]), {"%": 1, "%p": 1, "명": 1})
        self.assertEqual(F.settle_context({"%": 2, "%p": 2}, [item("3.425")]), {"%": 3, "%p": 3})
        self.assertEqual(F.settle_context({"%": 1, "%p": 1}, [item("3.425")]), {"%": 1, "%p": 1})           # 한 자리에서는 반 칸이 아니다
        self.assertEqual(F.settle_context(base, [item("3.45"), item("3.425")]), {"%": 3, "%p": 3, "명": 0})   # 한 칸 늘린 자리에서 또 걸리면 더 늘린다
        self.assertEqual(F.settle_context(base, [item("3.425"), item("3.45")]), {"%": 3, "%p": 3, "명": 0})   # 순서가 바뀌어도 같다(앞 값은 다음 바퀴에서 걸린다)
        self.assertEqual(F.settle_context({"%": 1, "%p": 3}, [item("3.45")]), {"%": 2, "%p": 3})            # 이미 더 많은 자리로 보이는 짝(%p)은 줄이지 않는다
        self.assertEqual(F.settle_context({"%": 2, "%p": 3}, [item("3.45", "%p")]), {"%": 2, "%p": 3})       # 이미 정확히 보이면 그대로
        self.assertEqual(F.settle_context({"%": 1, "%p": 2}, [item("3.45", "%")]), {"%": 2, "%p": 2})        # %p 가 % 보다 작아지지 않는다
        limit = F.NUMBER_POLICY["internal_places"] - 1
        deep = item("0." + "0" * (limit) + "5")
        self.assertEqual(F.settle_context({"%": limit}, [deep])["%"], limit)                                   # 내부 정밀도를 넘는 자리는 늘리지 않고 끝난다(무한 반복 없음)

    def test_settling_always_ends(self):
        """바퀴 수에 상한이 있어, 자리표가 늘림을 따르지 않는 이상한 경우(변이 '표시 자리 context 무시')에도 끝난다 — 상한이 없던 때는 시험 모듈이 무한 반복에 빠졌다.
        끝나지 않으면 시험이 멈추지 않고 실패하도록 호출 횟수에 한도를 둔다."""
        calls = []

        def stuck(unit, context=None):
            calls.append(unit)
            if len(calls) > 5000:
                raise AssertionError("settle_context 가 끝나지 않는다")
            return F.unit_spec(unit).decimals                          # 늘린 자리를 읽지 않는다

        original = F.decimals_for
        F.decimals_for = stuck
        try:
            settled = F.settle_context({"%": 1, "%p": 1}, [types.SimpleNamespace(value=Decimal("3.45"), unit="%")])
        finally:
            F.decimals_for = original
        self.assertIsInstance(settled, dict)
        self.assertLessEqual(len(calls), 200)

    def test_a_mean_on_a_half_step_is_shown_exactly(self):
        post = run("R02_region_compare", cross(["3.4", "3.4", "3.5", "3.5"]), {"key": H.UNEMP})
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertEqual(dict(post.decimals), {"%": 2, "%p": 2})
        for fragment in ("- 평균: 3.45%(4곳 단순 평균), 중앙값: 3.45%", "| 1위 | 가상 지역 다 | 3.50% | +0.05%p |", "| 1위 | 가상 지역 라 | 3.50% | +0.05%p |",
                         "| 3위 | 가상 지역 가 | 3.40% | −0.05%p |", "- 평균보다 높은 곳: 가상 지역 다, 가상 지역 라", "- 평균보다 낮은 곳: 가상 지역 가, 가상 지역 나",
                         "평균과 가장 높은 값의 차이는 0.05%p, 가장 낮은 값의 차이는 0.05%p입니다"):
            self.assertIn(fragment, post.body_markdown)
        self.assertNotIn("평균과 같은 곳", post.body_markdown)
        self.assertEqual(A.post_problems(post), [])

    def test_a_half_step_one_digit_further_is_followed(self):
        post = run("R02_region_compare", cross(["3.41", "3.41", "3.42", "3.46"]), {"key": H.UNEMP})           # 자료 2자리, 평균 3.425 는 2자리의 반 칸
        self.assertEqual(dict(post.decimals), {"%": 3, "%p": 3})
        self.assertIn("- 평균: 3.425%(4곳 단순 평균), 중앙값: 3.415%", post.body_markdown)
        self.assertIn("| 1위 | 가상 지역 라 | 3.460% | +0.035%p |", post.body_markdown)
        self.assertIn("| 2위 | 가상 지역 다 | 3.420% | −0.005%p |", post.body_markdown)
        self.assertIn("| 3위 | 가상 지역 가 | 3.410% | −0.015%p |", post.body_markdown)
        self.assertEqual(A.post_problems(post), [])

    def test_a_mean_that_is_not_on_a_half_step_keeps_the_table_digits(self):
        for values in (["3.4", "3.4", "3.4", "3.5"], ["3.4", "3.5", "3.5", "3.6", "3.8"], ["3.3", "3.4", "3.5", "3.5", "3.6", "3.6"]):
            post = run("R02_region_compare", cross(values), {"key": H.UNEMP})
            with self.subTest(values=values):
                self.assertEqual(dict(post.decimals), {"%": 1, "%p": 1})

    def test_whole_number_data_gets_one_decimal_only_when_the_mean_is_a_half(self):
        kw = {"unit": "명", "key": "labour.employed_persons", "label": "취업자 수"}
        half = run("R02_region_compare", cross(["7", "6", "5", "4", "3", "2"], **kw), {"key": kw["key"]})
        self.assertEqual(dict(half.decimals), {"명": 1})
        self.assertIn("- 평균: 4.5명(6곳 단순 평균), 중앙값: 4.5명", half.body_markdown)
        self.assertIn("| 1위 | 가상 지역 가 | 7.0명 | +2.5명 |", half.body_markdown)
        self.assertIn("6곳의 취업자 수", half.description)                          # 세는 말 `곳` 은 자료 단위 `명` 과 달라 정수 그대로(제목에는 값이 없다 — D-200)
        self.assertNotIn("6곳", half.title)
        whole = run("R02_region_compare", cross(["7", "6", "5", "3", "2", "1"], **kw), {"key": kw["key"]})        # 평균 4·중앙값 4 — 어느 쪽도 반 칸이 아니다(N3: 값 7·6·5·4·3·1 은 중앙값이 4.5 라 한 자리로 보인다 — test_space_f2fix)
        self.assertEqual(dict(whole.decimals), {"명": 0})

    def test_the_shown_value_minus_the_shown_mean_is_the_shown_difference_in_every_row(self):
        """속성: 값 − 평균 = 차이 가 보이는 숫자끼리도 성립하고, 평균보다 높다·낮다·같다는 보이는 차이의 부호와 같다(짝수 곳·1자리 자료·평균이 반 칸에 걸치는 묶음이 많은 표본)."""
        rng = random.Random(20261109)
        grid, tied, checked = ["3.3", "3.4", "3.5", "3.6"], 0, 0
        for _case in range(240):
            values = [rng.choice(grid) for _ in range(rng.choice((4, 6, 8, 10)))]
            if len(set(values)) == 1:
                continue
            post = run("R02_region_compare", cross(values), {"key": H.UNEMP})
            self.assertIsInstance(post, A.AssembledPost, (values, post))
            tied += dict(post.decimals)["%"] == 2
            mean = shown_number(re.search(r"- 평균: ([^(]+)\(", post.body_markdown).group(1))
            lists = {}
            for title in ("평균보다 높은 곳", "평균보다 낮은 곳", "평균과 같은 곳"):
                found = re.search(rf"(?m)^- {title}: (.+)$", post.body_markdown)
                lists[title] = set(found.group(1).split(", ")) if found else set()
            for _rank, region, value, diff in rank_rows(post):
                checked += 1
                with decimal.localcontext(decimal.Context(prec=60)):
                    self.assertEqual(shown_number(value) - mean, shown_number(diff), (values, region, value, diff, mean))
                sign = (shown_number(diff) > 0) - (shown_number(diff) < 0)
                self.assertIn(region, lists["평균보다 높은 곳" if sign > 0 else "평균보다 낮은 곳" if sign < 0 else "평균과 같은 곳"], (values, region))
        self.assertGreaterEqual(tied, 25)                       # 평균이 반 칸에 걸리는 묶음을 충분히 겪었다(속성이 비어 있지 않다)
        self.assertGreater(checked, 500)


class TieLineTest(unittest.TestCase):
    """D7(D-151): 같은 값이 여러 번이면 한 기간 하나로 단정하지 않는다 — R01 '표시한 기간 안의 범위' 줄, R03 '한눈에'의 최고·최저 줄과 위쪽 표(최신 값이 최고·최저가 아니어도)."""
    BOTH = ["3.0", "3.5", "3.1", "3.5", "3.2", "3.0", "3.3", "3.4", "3.2"]          # 최고 3.5 가 2025년 8월·10월, 최저 3.0 이 2025년 7월·12월(최신 3.2 는 어느 쪽도 아니다)

    def test_the_time_series_range_line(self):
        both = run("R01_time_series", series(self.BOTH))
        self.assertIn("- 표시한 기간 안의 범위: 최저 3.0%(같은 값 2번, 가장 나중 2025년 12월)에서 최고 3.5%(같은 값 2번, 가장 나중 2025년 10월)까지", both.body_markdown)
        high_only = run("R01_time_series", series(["3.0", "3.5", "3.1", "3.5", "3.2", "3.3", "3.3", "3.4", "3.2"]))
        self.assertIn("- 표시한 기간 안의 범위: 최저 3.0%(2025년 7월)에서 최고 3.5%(같은 값 2번, 가장 나중 2025년 10월)까지", high_only.body_markdown)
        low_only = run("R01_time_series", series(["3.0", "3.6", "3.1", "3.5", "3.2", "3.0", "3.3", "3.4", "3.2"]))
        self.assertIn("- 표시한 기간 안의 범위: 최저 3.0%(같은 값 2번, 가장 나중 2025년 12월)에서 최고 3.6%(2025년 8월)까지", low_only.body_markdown)
        unique = run("R01_time_series", series(["3.0", "3.6", "3.1", "3.5", "3.2", "3.7", "3.3", "3.4", "3.2"]))
        self.assertIn("- 표시한 기간 안의 범위: 최저 3.0%(2025년 7월)에서 최고 3.7%(2025년 12월)까지", unique.body_markdown)
        self.assertNotRegex(unique.body_markdown, r"같은 값 [0-9]+번")

    def test_the_record_recipe_glance_and_table_when_the_latest_value_is_in_the_middle(self):
        post = run("R03_record_position", series(self.BOTH))
        self.assertIsInstance(post, A.AssembledPost, post)
        for fragment in ("- 자료 기간의 최고: 3.5%(같은 값 2번, 가장 나중 2025년 10월)", "- 자료 기간의 최저: 3.0%(같은 값 2번, 가장 나중 2025년 12월)",
                         "| 최고 | 2025년 10월(가장 나중, 같은 값 2번) | 3.5% |", "| 최저 | 2025년 12월(가장 나중, 같은 값 2번) | 3.0% |", "| 최신 | 2026년 3월 | 3.2% |"):
            self.assertIn(fragment, post.body_markdown)
        self.assertNotIn("그 값은 자료에", post.body_markdown)                        # 최신 값이 최고·최저가 아니면 제목·해석은 그대로(같은 값 문장은 최신 값이 그 값일 때만)
        unique = run("R03_record_position", series(["3.0", "3.6", "3.1", "3.5", "3.2", "3.7", "3.3", "3.4", "3.2"]))
        self.assertIn("- 자료 기간의 최고: 3.7%(2025년 12월)", unique.body_markdown)
        self.assertIn("| 최고 | 2025년 12월 | 3.7% |", unique.body_markdown)
        self.assertNotRegex(unique.body_markdown, r"같은 값 [0-9]+번")

    def test_the_record_recipe_when_the_latest_value_is_the_tied_extreme(self):
        post = run("R03_record_position", series(["3.0", "3.1", "3.5", "3.2", "3.1", "3.3", "3.2", "3.4", "3.5"]))
        self.assertIn("- 자료 기간의 최고: 3.5%(같은 값 2번, 가장 나중 2026년 3월)", post.body_markdown)
        self.assertIn("| 최고 | 2026년 3월(가장 나중, 같은 값 2번) | 3.5% |", post.body_markdown)
        self.assertIn("그 값은 자료에 2번 나옵니다", post.body_markdown)
        self.assertIn("- 자료 기간의 최저: 3.0%(2025년 7월)", post.body_markdown)

    def test_a_property_every_repeated_extreme_is_said_to_repeat(self):
        rng = random.Random(7)
        repeated = 0
        for _case in range(80):
            values = [rng.choice(["3.0", "3.1", "3.2", "3.3"]) for _ in range(rng.randint(8, 14))]
            if len(set(values[-12:])) == 1 or len(set(values)) == 1:
                continue
            r01 = run("R01_time_series", series(values))
            r03 = run("R03_record_position", series(values))
            self.assertIsInstance(r01, A.AssembledPost, values)
            self.assertIsInstance(r03, A.AssembledPost, values)
            shown = values[-12:]
            line = re.search(r"- 표시한 기간 안의 범위: 최저 ([0-9.]+%)\(([^)]*)\)에서 최고 ([0-9.]+%)\(([^)]*)\)까지", r01.body_markdown)
            lines = [re.search(rf"- 자료 기간의 {name}: ([0-9.]+%)\(([^)]*)\)", r03.body_markdown) for name in ("최저", "최고")]
            checks = ((shown, (line.group(1), line.group(3)), (line.group(2), line.group(4))),             # R01: 최저·최고 값, 그 괄호 안 설명
                      (values, (lines[0].group(1), lines[1].group(1)), (lines[0].group(2), lines[1].group(2))))      # R03
            for pool, texts, notes in checks:
                for text, note, extreme in zip(texts, notes, (min(pool), max(pool))):
                    count = pool.count(extreme)
                    repeated += count > 1
                    self.assertEqual(text, f"{extreme}%")
                    self.assertEqual(f"같은 값 {count}번" in note, count > 1, (values, note))
        self.assertGreaterEqual(repeated, 60)


class CountUnitTest(unittest.TestCase):
    """D9(D-153): 순위·개수 계산 결과는 자료의 단위 자리와 상관없이 정수로 보인다 — 교육 범주의 `곳`·`개` 로 소수 자료를 넣어도 '6.0곳 비교'가 되지 않는다."""

    def test_region_counts_are_whole_numbers(self):
        kw = {"key": "education.schools", "unit": "곳", "label": "학교 수"}
        post = run("R02_region_compare", cross(["3.5", "2.5", "4.5", "1.5", "5.5", "2.5"], **kw), {"key": kw["key"]})
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertEqual(dict(post.decimals), {"곳": 1})
        text = post.title + "\n" + post.description + "\n" + post.body_markdown + "\n" + post.evidence_text
        self.assertNotIn("6곳", post.title)                                                    # 제목에는 값(곳 수)이 없다(D-200)
        self.assertIn("6곳의 학교 수", post.description)
        self.assertIn("- 평균보다 높은 곳 3곳, 낮은 곳 3곳", post.body_markdown)
        for wrong in ("6.0곳", "높은 곳 3.0곳", "낮은 곳 3.0곳", "+6.0곳", "1.0위", "2.0위", "+4.0위"):
            self.assertNotIn(wrong, text)
        self.assertIn("| 1위 | 가상 지역 마 | 5.5곳 |", post.body_markdown)           # 자료의 값은 자료 자리 그대로
        self.assertIn("6곳", post.evidence_text)
        self.assertEqual(A.post_problems(post), [])

    def test_observation_counts_are_whole_numbers(self):
        periods = months("2025-01", 12)
        del periods[3]                                                          # 기간이 빠진 자료 — 세는 말이 `개`(관측 N개)이고 자료 단위도 `개`
        values = ["12.5", "12.0", "13.5", "13.0", "12.5", "14.0", "13.5", "13.0", "12.0", "12.5", "13.0"]
        post = run("R03_record_position", series(values, periods=periods, key="education.schools", unit="개", label="학교 수"), {"key": "education.schools", "region": "R01"})
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertEqual(dict(post.decimals), {"개": 1})
        self.assertIn("관측 11개입니다", post.body_markdown)
        self.assertNotIn("11.0개", post.body_markdown + post.evidence_text)
        self.assertIn("14.0개", post.body_markdown)                               # 자료의 값은 자료 자리(1)로
        self.assertEqual(A.post_problems(post), [])
        self.assertIn("11", A.traceable_numbers(post))
        self.assertNotIn("11.0", A.traceable_numbers(post))

    def test_the_display_helpers(self):
        group = [H.make_fact(v, unit="곳", region=f"R0{i}", region_label=f"가상 지역 {SYLLABLES[i]}", key="education.schools", label="학교 수") for i, v in enumerate(("3.5", "2.5", "4.5", "1.5"), start=1)]
        count, rank, mean = C.f12_count(group, "곳"), C.f04_rank(group[0], group), C.f08_mean(group)
        context = {"곳": 3, "위": 2}
        self.assertEqual((F.decimals_of(count, context), F.decimals_of(rank, context), F.decimals_of(mean, context), F.decimals_of(group[0], context)), (0, 0, 3, 3))
        self.assertEqual((F.format_object(count, context=context), F.format_object(rank, signed=True, context=context), F.format_object(mean, context=context)), ("4곳", "+2위", "3.000곳"))
        self.assertEqual(F.format_object(group[0], context=context), F.format_with_unit(group[0].value, "곳", context=context))
        self.assertEqual(F.format_object(group[0], absolute=True, context={}), "4곳")                   # 자리표가 없으면 단위 표의 자리(곳 은 정수 — 0 에서 먼 쪽으로 반올림)
        self.assertEqual(F.INTEGER_FORMULAS, frozenset({"F04_rank", "F12_count", "F16_count_between"}))        # F16(기준 이상 개수, S2a)도 정수로 보인다
        for obj, kind, expected in ((count, "V", "4"), (count, "F", "4곳"), (count, "S", "+4곳"), (count, "A", "4곳"), (mean, "V", "3.000"), (mean, "F", "3.000곳")):
            with self.subTest(kind=kind):
                self.assertEqual(F.render_marker(kind, "x", obj, context), expected)
        self.assertIn("4곳", F.describe(count, context))
        self.assertNotIn("4.000곳", F.describe(count, context))


class NumberWordShapeTest(unittest.TestCase):
    """D8(D-154): 우리말 수 표현 검사는 흔한 낱말(조건·이번·사건·세대·열대·일명·만원·프로그램·조사원 …)을 수로 잡지 않고, 두어 곳·서넛·이삼 일·오륙 개·영하 같은 표현은 잡는다.
    한 글자 수는 띄어 쓴 꼴만(붙여 쓴 꼴은 겹치지 않는 세는 말만), 두 글자 이상 수는 붙여 쓴 꼴도, 세는 말 뒤 한글은 조사일 때만 센다."""
    CATCH = ("두어 곳", "두어 번", "서넛", "네댓 곳", "대여섯 개", "예닐곱", "한둘", "여럿", "열에 아홉", "십중팔구", "삼삼오오", "이삼 일", "오륙 개", "칠팔 명", "반 이상", "반 이하", "영하",
             "제로 값", "이틀 연속", "사흘 동안", "열흘", "닷새", "열다섯 곳", "서른다섯 명", "마흔여덟 개", "스물다섯 곳",
             "세곳", "두곳", "열곳", "한개", "두개", "세개", "네개", "열개", "한번", "세번", "한명", "두명", "열살", "두배", "네배", "열배", "십배", "백배", "천배", "만배", "십프로", "백퍼센트", "삼개월",
             "사분기", "삼십곳", "이십명", "오천원", "이삼일", "삼십분", "이십점", "사오 명", "한 사람", "세 시간", "두시간", "한 달간", "열 개월간", "한 곳으로", "한 번으로", "한 건으로",
             "세 곳이", "두 배로", "네 곳에서는", "한 달간의", "세 번째로", "두 곳뿐", "세 곳이었다", "네 곳이상", "하나라도", "하나까지만", "하나씩", "하나하나", "하나같이",
             "세 대", "열 대", "한 해", "한 주", "한 호", "삼 건", "사 건", "만 원", "억 원", "조 원", "일 위", "삼 위", "영 점", "백 점", "삼 퍼센트포인트", "사분의 삼", "삼 분의 이", "이분의 일",
             "영 초과", "삼 초과", "이십 초과", "삼 이상", "삼 미만", "삼 이하", "수만 건", "수만 가지", "수만 시간", "수만여 곳", "수십 곳", "수백", "수천억 원", "수십만 명", "수십여 곳",
             "한 군데", "두 마리", "세 가구", "네 학급", "두 학교", "세 기관", "두 나라", "세 지역", "두 기간", "한 주일", "세 단계", "두 차례", "십 달러", "삼 포인트", "오 프로", "십 년", "삼 점", "오 분",
             "십 초", "이십 일", "삼 개월", "오 번째", "삼 세", "칠 살", "오 곳", "사 명",
             "two regions", "half of the values", "TWELVE places", "Double", "zero", "Hundred", "TEN-year", "three of them")
    PASS = ("이번 달", "이번에는", "사건", "조건", "이용 조건", "이용 조건에 따라 출처를 표시합니다", "조건부", "이건", "일명", "이명", "오명", "구명", "일개", "오개", "구원", "삼세", "사세", "이세", "오세",
            "일세", "세대", "만원", "억원", "조원", "일부 지역", "이 위", "이위", "일일 건수", "일 개선", "사 건물", "이 개념", "이 곳에서", "이 점에서", "이 번호", "A사 번호",
            "강남구 개발", "제일 위쪽", "만원 버스", "한명회", "세명대학교", "한달음에", "두개골", "세배 드리다", "두건을 썼다", "한해서 승인", "열대야", "열세를 보였다", "한 프로그램", "한 프로젝트",
            "한 개인", "한 개념", "한 건강", "한 대표", "두 개발자", "두 번호", "한 위치", "조사원", "조사일", "조사 단계", "구조 위", "영구 단계", "사이 개선", "이사 회의", "오이 구이", "오일 위기",
            "만일 일이 생기면", "일이 많다", "사이가 좋다", "만조 시간", "백조가 난다", "한국은행", "신한은행", "하나은행", "하나님", "인터넷", "넷플릭스", "제로섬 게임", "알아 두세요", "그대로 두어",
            "글자 수만", "수만으로", "someone", "phone", "often", "tenant", "bone", "zeroing", "stone", "nonetheless", "평균보다 높은 ⟦F:abc⟧곳", "⟦V:n⟧⟦U:n⟧ 비교", "이 퍼센트", "이 번째",
            "이상 기후", "조사 대상", "구분 기준", "이번 분기", "한 프로", "한편 이 점에서", "오이", "한국의 하루")

    def test_every_listed_expression_is_found(self):
        for text in self.CATCH:
            with self.subTest(text=text):
                self.assertTrue(F.untraced_numbers(text), text)
                self.assertTrue(F.untraced_numbers(f"앞 {text} 뒤"), text)

    def test_ordinary_words_are_not_taken_for_numbers(self):
        for text in self.PASS:
            with self.subTest(text=text):
                self.assertEqual(F.untraced_numbers(text), [], text)

    def test_the_old_false_positives_no_longer_block_a_reader_note(self):
        """검증자가 든 예: `이용 조건에 따라…`·`이번 달 …` 같은 안내 문장이 '숫자·수 표현'으로 막혀 글이 안 되던 일."""
        for note in ("이용 조건에 따라 출처를 표시합니다", "이번 달 자료는 잠정치입니다", "사건·사고 자료는 포함하지 않았습니다", "세대 구분은 제공처 기준을 따릅니다", "조사원이 방문해 모은 자료입니다"):
            with self.subTest(note=note):
                self.assertIsNone(A._note_problem(note), note)
                post = H.run("R01_time_series", params=H.R01_PARAMS, provider=dataclasses.replace(M.MockProvider(), reader_notes=(note,)))
                self.assertIsInstance(post, A.AssembledPost, post)
                self.assertIn(f"- 제공처 안내: {note}.", post.body_markdown)
        for note in ("두 곳을 뺍니다", "수십 곳이 빠졌습니다", "이삼 일 늦게 받았습니다", "서넛 기관의 자료입니다", "절반은 제외합니다"):
            with self.subTest(note=note):
                self.assertIsNotNone(A._note_problem(note), note)

    def test_single_syllable_numbers_need_a_space_unless_the_counter_is_safe(self):
        """한 글자 수 + 세는 말: 붙여 쓴 꼴이 흔한 낱말과 겹치는 세는 말(대·호·해·주·건·위·원 …)은 띄어 쓴 꼴만 수로 본다."""
        for number in ("한", "두", "세", "네", "열"):
            for counter in ("대", "호", "해", "주", "위"):
                with self.subTest(number=number, counter=counter):
                    self.assertEqual(F.untraced_numbers(f"{number}{counter}"), [])
                    self.assertTrue(F.untraced_numbers(f"{number} {counter}"))
        for number in "일삼사오육칠팔구십백천만억조":
            for counter in ("건", "개", "명", "곳", "번", "원", "위", "세", "살", "년", "일", "점", "분", "초"):
                with self.subTest(number=number, counter=counter):
                    self.assertEqual(F.untraced_numbers(f"{number}{counter}"), [])
                    self.assertTrue(F.untraced_numbers(f"{number} {counter}"))
        for number in ("두", "네", "열"):
            self.assertTrue(F.untraced_numbers(f"{number}배"))
        for text in ("세배", "한배"):
            self.assertEqual(F.untraced_numbers(text), [])                 # 세배(설날 절)·한배(같은 배)는 흔한 낱말
        for text in ("세 배", "한 배"):
            self.assertTrue(F.untraced_numbers(text))
        self.assertEqual(F.untraced_numbers("이 곳"), [])                   # 지시어 `이` 는 한 글자 수로 보지 않는다
        self.assertEqual(F.untraced_numbers("이 점"), [])

    def test_numbers_of_two_or_more_syllables_are_found_even_when_attached(self):
        for number in ("이십", "삼십", "오십", "백오십", "천오백", "이만", "삼만", "십만", "백만", "천만", "일억", "이삼", "사오", "오륙", "칠팔", "열두", "열다섯", "스물", "스물세", "서른다섯", "마흔", "쉰",
                       "아흔아홉", "다섯", "여섯", "일곱", "여덟", "아홉", "두어", "두세"):
            for counter in ("곳", "개", "명", "번", "건"):
                for text in (f"{number}{counter}", f"{number} {counter}"):
                    with self.subTest(text=text):
                        self.assertTrue(F.untraced_numbers(text), text)

    def test_words_made_only_of_number_characters_are_not_numbers(self):
        for word in ("사이", "이사", "구이", "오이", "일일", "일이", "만일", "만조", "백조", "조사", "구조", "영구"):
            for counter in ("곳", "개", "명", "건", "원", "일", "년", "점"):
                for text in (f"{word}{counter}", f"{word} {counter}"):
                    with self.subTest(text=text):
                        self.assertEqual(F.untraced_numbers(text), [], text)

    def test_a_hangul_numeral_after_a_digit_is_counted_once(self):
        """`3만 명`·`5억 원` 은 아라비아 숫자 한 덩어리만 센다(한글 수 낱말로 두 번 세지 않는다)."""
        for text, expected in (("3만 명", ["3"]), ("5억 원", ["5"]), ("10퍼센트", ["10"]), ("2천만 달러", ["2"]), ("제3자 자료", []), ("약 12만 명", ["12"])):
            with self.subTest(text=text):
                self.assertEqual(F.untraced_numbers(text), expected)

    def test_a_long_hostile_text_is_scanned_without_trouble(self):
        """정규식이 폭발(재귀·역추적)하지 않는다 — 시간을 재지 않고, 어지러운 긴 글이 끝나기만 하면 된다."""
        for text in ("이" * 5000, "한 곳이" * 2000, "에서" * 3000 + "가", "이나이나" * 2000, "열" * 3000 + " 개", "삼 " * 3000, "a" * 5000, "일" * 4000 + "개", "수" + "십" * 4000, "한 " * 3000 + "프로그램"):
            self.assertIsInstance(F.untraced_numbers(text), list)

    def test_the_old_survivor_the_chinese_counter_words_are_counters(self):
        """D-23: 한자어 세는 말 `초과`(이상·이하·미만과 같이)를 지워도 시험이 통과하던 구멍."""
        for counter in ("초과", "이상", "이하", "미만"):
            for number in ("영", "삼", "이십", "반"):
                with self.subTest(number=number, counter=counter):
                    self.assertTrue(F.untraced_numbers(f"{number} {counter}"))


class FreeTextFieldsTest(unittest.TestCase):
    """D3·D4(D-155): 허용 목록이 없는 자유 글 칸(공식 데이터 이름·독자용 안내 문장 `reader_notes`)은 합성어 꼬리를 나눠 쓴 차단 낱말(`국민환 자 통계`)과 제어·서식·방향 문자·링크·HTML·마크다운
    기호를 받지 않는다. 낱말 경계와 상관없이 찾는 엄격한 검사는 이 두 칸에만 쓰고(오탐이 있어도 사람이 고친다), Fact 의 라벨 같은 허용 목록 칸은 '낱말 첫머리' 규칙 그대로다."""
    BAD_NAMES = ("국립당 뇨병통계", "국민환 자 통계", "주 식 시장 통계", "고 혈압 통계", "http 통계", "www 통계", "이름\x07", "이름‮", "이름​", "이름<b>", "이름@기관", "이름[1]", "이름`x`")
    GOOD_NAMES = ("시험용 가상 통계", "통계청 국가통계포털", "한국 소비자 물가 지수", "R&D 통계", "교육 통계 서비스", "KOSIS 국가통계포털")
    BAD_NOTES = ("이 자료는 국민환 자 수를 뜻하지 않습니다", "주 식 정보가 아닙니다", "효 능은 알 수 없습니다", "고 혈압 자료가 아닙니다",
                 "방향‮문자", "영 너비​공백", "벨\x07소리", "줄 바꿈", "탭\t문자", "소프트­하이픈", "문단 나눔", "[여기](링크)를 보세요", "<b>굵게</b> 표시", "`코드` 표시",
                 "주소는 http 로 시작", "주소 :// 조각", "메일@주소", "www 로 시작", "표|기호", "역슬래시\\기호", "ｈｔｔｐ 전각", "＜b＞ 전각", "＠ 전각")
    GOOD_NOTES = ("제3자 자료는 제외됩니다", "이미지와 로고는 제외됩니다.", "이용 조건에 따라 출처를 표시합니다", "이 자료는 공식 통계를 가공하지 않았습니다", "일부 지역은 자료가 없습니다",
                  "R&D 지출은 포함하지 않았습니다", "잠정치이며 개정될 수 있습니다(제공처 기준)")

    def code(self, result):
        return result.code if isinstance(result, R.Insufficient) else "POST"

    def with_note(self, note):
        return H.run("R01_time_series", params=H.R01_PARAMS, provider=dataclasses.replace(M.MockProvider(), reader_notes=(note,)))

    def with_name(self, name):
        return H.run("R01_time_series", params=H.R01_PARAMS, source=A.SourceInfo(M.MockProvider(), name, M.SOURCE_URL))

    def test_the_official_name_refuses_split_spellings_and_markup(self):
        for name in self.BAD_NAMES:
            with self.subTest(name=name):
                self.assertEqual(self.code(self.with_name(name)), "SOURCE_INFO_INVALID")

    def test_ordinary_official_names_are_used(self):
        for name in self.GOOD_NAMES:
            with self.subTest(name=name):
                post = self.with_name(name)
                self.assertIsInstance(post, A.AssembledPost, post)
                self.assertIn(f"- [{name}](", post.body_markdown)

    def test_a_reader_note_refuses_split_spellings_control_characters_and_markup(self):
        for note in self.BAD_NOTES:
            with self.subTest(note=note):
                self.assertEqual(self.code(self.with_note(note)), "READER_NOTE_UNSAFE")
                self.assertIsNotNone(A._note_problem(note))

    def test_ordinary_reader_notes_are_used(self):
        for note in self.GOOD_NOTES:
            with self.subTest(note=note):
                post = self.with_note(note)
                self.assertIsInstance(post, A.AssembledPost, post)
                self.assertIn(f"- 제공처 안내: {note if note[-1] in '.!?' else note + '.'}", post.body_markdown)
                self.assertEqual(A.post_problems(post), [])

    def test_html_entities_cannot_smuggle_characters_either(self):
        """`&` 자체는 막지 않지만 엔티티(`&lt;`·`&#x202e;`·`&shy;`)는 영문자·숫자가 있어야 만들어지고 그것을 글자 체계·숫자 검사가 막는다 — 어느 쪽이든 글이 나가지 않는다."""
        for note in ("엔티티 &lt;b&gt; 표시", "방향 &#x202e; 문자", "연자 &shy; 하이픈", "공백 &nbsp; 문자", "영너비 &zwj; 문자"):
            with self.subTest(note=note):
                self.assertNotEqual(self.code(self.with_note(note)), "POST")

    def test_unsafe_free_text_unit(self):
        for text in ("a\x00b", "a‮b", "a​b", "a­b", "a b", "a﻿b", "<", ">", "[", "]", "`", "|", "\\", "@", "HTTP", "Http://", "www", "ＨＴＴＰ", "＜", "＠"):
            with self.subTest(text=text):
                self.assertTrue(A.unsafe_free_text(text), repr(text))
        for text in ("", "평범한 문장입니다.", "R&D 통계", "제3자(제공처 기준) 자료", "쉼표, 마침표. 가운뎃점·하이픈-물음표? 느낌표! 따옴표 '작은' \"큰\"", "한글 ㅋㅋ ㅏ 호환 자모"):
            with self.subTest(text=text):
                self.assertFalse(A.unsafe_free_text(text), repr(text))

    def test_the_strict_search_finds_what_the_word_start_rule_cannot(self):
        self.assertEqual(T.blocked_in("국민환 자 통계"), [])                                                  # 낱말 첫머리 규칙은 합성어 꼬리 분리를 못 잡는다
        self.assertIn(("건강·의료", "환자"), T.blocked_loose("국민환 자 통계"))
        self.assertIn(("건강·의료", "당뇨"), T.blocked_loose("국립당 뇨병통계"))
        self.assertIsNone(T.text_problem("국민환 자 통계"))
        self.assertIsNotNone(T.text_problem("국민환 자 통계", loose=True))
        self.assertEqual(T.blocked_in("최고 소비"), [])                                                       # 그 대신 엄격한 검사는 경계를 가로질러 우연히 생긴 글자도 잡는다(문서에 적은 대가)
        self.assertIn(("법률", "고소"), T.blocked_loose("최고 소비"))
        self.assertEqual(T.blocked_loose("소비자물가지수 통계"), [])
        self.assertEqual([found for found in T.blocked_loose("암 약 병") if found[1] in ("암", "약", "병")], [("건강·의료", "암"), ("건강·의료", "약"), ("건강·의료", "병")])
        self.assertEqual(T.blocked_loose("암호 약속 병아리"), [])

    def test_fact_labels_keep_the_word_start_rule(self):
        """엄격한 검사를 허용 목록 칸(Fact 의 라벨)까지 넓히면 `최고 소비` 의 `고소` 같은 정상 라벨이 막힌다 — 라벨은 낱말 첫머리 규칙 그대로."""
        fact = H.make_fact("3.5", key="economy.retail_sales", label="최고 소비", unit="%")
        self.assertIsNone(T.fact_problem(fact, ("economy",)))
        split = H.make_fact("3.5", key="labour.unemployment_rate", label="국민환 자")
        self.assertEqual(T.fact_problem(split, ("labour",))[0], "UNKNOWN_TOPIC")                           # 허용 목록 밖 낱말이라 어차피 막힌다


class SecondRoundSurvivorsTest(unittest.TestCase):
    """D10: 재검증의 변이 24개 중 살아남은 5개를 시험이 잡는다 — 한 낱말 안의 차단 낱말(D-01)·`direction` 이 표시 자리를 무시(D-22)·슬래시로 낱말 가르기(D-05)·한 글자 차단 낱말 `병`(D-07)·`초과`(D-23, 위 NumberWordShapeTest)."""

    def test_a_blocked_word_inside_one_word_is_found(self):
        """D-01: 낱말 하나 안의 차단 낱말(`한국당뇨병통계`·`실업률환자`)을 세지 않으면 이름이 통과한다."""
        for text in ("한국당뇨병통계", "실업률환자", "국민환자통계", "주식시장"):
            with self.subTest(text=text):
                self.assertTrue(T.blocked_in(text), text)
        bad = H.make_fact("3.5", label="실업률환자")
        self.assertEqual(T.fact_problem(bad, ("labour",))[0], "TOPIC_NOT_ALLOWED")
        self.assertEqual(R.topic_problem(R.R01_TIME_SERIES, [bad]).code, "TOPIC_NOT_ALLOWED")

    def test_separators_split_words_so_that_accidental_words_across_them_are_not_counted(self):
        """D-05: `/`·`·`·`-`·괄호로 낱말을 가르지 않으면 `최고/소비` 의 `고소`·`판매/수` 의 `매수` 가 차단 낱말로 잡힌다."""
        for text in ("최고/소비", "판매/수", "최고·소비", "판매·수", "최고-소비", "판매-수", "최고(소비)", "판매(수)", "최고 소비", "판매 수"):
            with self.subTest(text=text):
                self.assertEqual(T.blocked_in(text), [], text)
        for text in ("무/조건", "무·조건", "무-조건", "무(조건)", "무 조건", "효/능", "효 능"):
            with self.subTest(text=text):
                self.assertTrue(T.blocked_in(text), text)
        self.assertEqual(T.words("가/나·다-라(마) 바"), ["가", "나", "다", "라", "마", "바"])

    def test_one_syllable_blocked_words_only_count_as_a_whole_word(self):
        """D-07: `암`·`약`·`병` 은 낱말 전체가 그 글자일 때만 차단 낱말이다(암호·약속·병아리는 아니다)."""
        for text in ("병", "암", "약", "병 이야기", "암 통계"):
            with self.subTest(text=text):
                self.assertTrue(T.blocked_in(text), text)
        for text in ("병아리", "암호", "약속", "병아리 약속 암호", "신병교육"):
            with self.subTest(text=text):
                self.assertEqual(T.blocked_in(text), [], text)
        self.assertEqual(T.fact_problem(H.make_fact("3.5", label="병"), ("labour",))[0], "TOPIC_NOT_ALLOWED")

    def test_direction_follows_the_display_digits(self):
        """D-22: `direction` 이 표시 자리(context)를 무시하면 자료 정밀도가 단위 표 최소보다 큰 글에서 모든 지역이 '평균과 같은 곳'이 되고 표에는 `+0.02%p` 가 적힌다."""
        diff = types.SimpleNamespace(value=Decimal("0.02"), unit="%p")
        self.assertEqual((R.direction(diff, {"%p": 3}), R.direction(diff, {"%p": 1}), R.direction(diff)), (1, 0, 0))
        post = run("R02_region_compare", cross(["3.450", "3.460", "3.470", "3.480", "3.490"]), {"key": H.UNEMP})
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertEqual(dict(post.decimals), {"%": 2, "%p": 2})                              # 자료의 정밀도(2자리)가 단위 표의 최소(1자리)보다 크다
        self.assertIn("- 평균보다 높은 곳: 가상 지역 마, 가상 지역 라", post.body_markdown)
        self.assertIn("- 평균보다 낮은 곳: 가상 지역 나, 가상 지역 가", post.body_markdown)
        self.assertIn("- 평균과 같은 곳: 가상 지역 다", post.body_markdown)
        self.assertIn("| 1위 | 가상 지역 마 | 3.49% | +0.02%p |", post.body_markdown)
        self.assertIn("- 평균보다 높은 곳 2곳, 낮은 곳 2곳", post.body_markdown)

    def test_the_verdict_follows_the_display_digits_too(self):
        cur, ref = H.make_fact("3.464"), H.make_fact("3.461", period="2026-02")
        diff = C.f01_change(cur, ref)
        self.assertEqual(R.verdict(cur, ref, diff, {"%": 3, "%p": 3}), "UP")
        self.assertEqual(R.verdict(cur, ref, diff, {"%": 1, "%p": 1}), "SAME")


if __name__ == "__main__":
    unittest.main()
