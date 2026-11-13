"""S2c-1 S1-c — 얇음 측정 `pipeline/fact_thin.py` 시험: 문장·항목 나누기와 분류(손으로 만든 틀)·일곱 값의 정의(고정 글자 비율·순수 고정 문장·값 문장·C 등급 계산 문장·직접 계산 표명·받은 날짜 표기·근거 텍스트 글자)·
여섯 골든 글에서의 값(독립 계산과 같음)·기준(d503c1b) 대비 늘지 않음·월별 수락 기준·순수 모듈(AI·시계·파일 없음)·`fact_supply.thin_of` 의 실패 처리. 네트워크·시계 없이 돈다."""
import ast
import re
import unittest
from types import SimpleNamespace
from unittest import mock

import _bootstrap
import fact_helpers as FH
import space_helpers as H
import test_space_recipes as TR

from pipeline import calc as C
from pipeline import fact_assembler as A
from pipeline import fact_supply as S
from pipeline import fact_thin as T
from pipeline import facts as F
from pipeline import recipes as R

ROOT = _bootstrap.ROOT
# 기준(S2c-1 전, origin/main d503c1b)의 골든 글 고정 비율 — '늘지 않음' 을 못박는다(전체 시험이 코드를 돌려 같은 정의로 잰 값)
BASELINE_FIXED_PCT = {"r04_kp": 77, "r04_ssn_daily": 66, "r04_ssn_monthly": 66, "r05_kp_storm": 79, "r05_flares": 85, "r06_scales": 83}
SOURCE = "\n\n## 출처\n\n- [이름](https://example.invalid/x) — 열람 2026년 11월 10일\n- 이용 조건: 자료 ({date} 열람)\n"

TEMPLATE = ("첫 문단의 문장입니다. 날짜 ⟦D:a⟧ 칸만 있는 문장입니다. 값은 ⟦F:b⟧입니다.\n\n"
            "이 글의 값은 안내입니다. ⟦T:record⟧ 에 받았습니다.\n\n"
            "## 한눈에\n\n"
            "- 최신 값: ⟦F:b⟧(⟦D:a⟧ 기준)\n- 고정 항목입니다.\n- 이름 ⟦L:main⟧ 칸만 있는 항목\n\n"
            "## 숫자로 보기\n\n"
            "표 소개 문장입니다. 이 글이 직접 계산했습니다.\n\n"
            "| 기준 | 값 |\n| --- | ---: |\n| ⟦D:a⟧ | ⟦F:b⟧ |\n\n"
            "## 비교·해석\n\n"
            "**이 글의 해석**: 값 ⟦A:c⟧ 높습니다. 고정 문장입니다.\n\n"
            "## 이 숫자를 읽을 때 주의\n\n"
            "- 계산한 값: 평균 같은 값은 이 글이 직접 계산했습니다. 반올림 경고입니다.\n- 이 글이 아는 것: 위 숫자뿐입니다.")
UNITS = [
    ("머리", "sentence", "첫 문단의 문장입니다."), ("머리", "sentence", "날짜 ⟦D:a⟧ 칸만 있는 문장입니다."), ("머리", "sentence", "값은 ⟦F:b⟧입니다."),
    ("머리", "sentence", "이 글의 값은 안내입니다."), ("머리", "sentence", "⟦T:record⟧ 에 받았습니다."),
    ("한눈에", "heading", "## 한눈에"), ("한눈에", "bullet", "- 최신 값: ⟦F:b⟧(⟦D:a⟧ 기준)"), ("한눈에", "bullet", "- 고정 항목입니다."), ("한눈에", "bullet", "- 이름 ⟦L:main⟧ 칸만 있는 항목"),
    ("숫자로 보기", "heading", "## 숫자로 보기"), ("숫자로 보기", "sentence", "표 소개 문장입니다."), ("숫자로 보기", "sentence", "이 글이 직접 계산했습니다."),
    ("숫자로 보기", "table_head", "| 기준 | 값 |"), ("숫자로 보기", "table_row", "| ⟦D:a⟧ | ⟦F:b⟧ |"),
    ("비교·해석", "heading", "## 비교·해석"), ("비교·해석", "sentence", "**이 글의 해석**: 값 ⟦A:c⟧ 높습니다."), ("비교·해석", "sentence", "고정 문장입니다."),
    ("이 숫자를 읽을 때 주의", "heading", "## 이 숫자를 읽을 때 주의"),
    ("이 숫자를 읽을 때 주의", "bullet", "- 계산한 값: 평균 같은 값은 이 글이 직접 계산했습니다. 반올림 경고입니다."), ("이 숫자를 읽을 때 주의", "bullet", "- 이 글이 아는 것: 위 숫자뿐입니다."),
]
FORMULA_OF = {"b": "F17_season_rank", "c": "F01_change"}


def fake_post(template=TEMPLATE, *, rendered=None, derived=FORMULA_OF, date="2026-11-10T01:10:00Z", evidence="근거 글자", sources=None):
    body = (rendered if rendered is not None else F.REF_RE.sub("값", template)) + (SOURCE.format(date="2026년 11월 10일") if sources is None else sources)
    return SimpleNamespace(template_markdown=template, body_markdown=body, derived=tuple(SimpleNamespace(fact_id=key, formula_id=value) for key, value in derived.items()),
                           source_records=(SimpleNamespace(retrieved_at=date),), evidence_text=evidence)


class SplitAndClassifyTest(unittest.TestCase):
    def test_a_hand_made_template_is_split_into_exactly_the_expected_units(self):
        self.assertEqual(T.split_units(TEMPLATE), UNITS)

    def test_only_sentences_and_bullets_are_counted_not_headings_or_table_lines(self):
        kinds = {kind for _section, kind, _text in T.split_units(TEMPLATE)}
        self.assertEqual(kinds, {"sentence", "bullet", "heading", "table_head", "table_row"})
        self.assertEqual(T.COUNTED_KINDS, ("sentence", "bullet"))
        counted = [text for _section, kind, text in UNITS if kind in T.COUNTED_KINDS]
        self.assertEqual(len(counted), 14)

    def test_each_unit_is_pure_stamp_or_value_by_the_references_it_holds_and_names_its_formulas(self):
        expected = {"첫 문단의 문장입니다.": ("pure", set()), "날짜 ⟦D:a⟧ 칸만 있는 문장입니다.": ("stamp", set()), "값은 ⟦F:b⟧입니다.": ("value", {"F17_season_rank"}),
                    "⟦T:record⟧ 에 받았습니다.": ("stamp", set()), "- 최신 값: ⟦F:b⟧(⟦D:a⟧ 기준)": ("value", {"F17_season_rank"}), "- 이름 ⟦L:main⟧ 칸만 있는 항목": ("stamp", set()),
                    "**이 글의 해석**: 값 ⟦A:c⟧ 높습니다.": ("value", {"F01_change"}), "- 고정 항목입니다.": ("pure", set()), "고정 문장입니다.": ("pure", set())}
        for text, want in expected.items():
            with self.subTest(text=text):
                self.assertEqual(T.classify(text, FORMULA_OF), want)
        self.assertEqual(T.classify("값 ⟦S:b⟧ ⟦V:c⟧", FORMULA_OF), ("value", {"F17_season_rank", "F01_change"}))
        self.assertEqual(T.classify("값 ⟦F:zzz⟧", FORMULA_OF), ("value", set()))                  # 계산 결과가 아닌 Fact 를 가리키는 값 참조는 값 문장이지만 계산식은 없다
        self.assertEqual(T.VALUE_KINDS, frozenset("FSAV"))

    def test_the_units_counts_of_the_hand_made_post_are_the_hand_counts(self):
        thin = T.measure(fake_post())
        self.assertEqual(thin["pure_units"], 8)                    # 손으로 센 값: 첫 문단·안내·고정 항목·표 소개·직접 계산 문장·해석 끝 문장·주의 줄 둘
        self.assertEqual(thin["value_units"], 3)                   # 값은 ⟦F⟧ 문장·최신 값 항목·해석 첫 문장(날짜·이름 칸만 있는 셋은 값 문장이 아니다)
        self.assertEqual(thin["c_units"], 2)                       # F17(C 등급) 이 든 두 문장·항목 — F01(산술)은 C 가 아니다
        self.assertEqual(thin["calc_claims"], 2)                   # 표 소개 뒤 문장과 주의 줄 '계산한 값' 항목
        self.assertEqual(thin["date_marks"], 3)                    # 틀의 수집일 참조 하나 + 출처 줄과 이용 조건 줄의 열람일 둘
        self.assertEqual(thin["evidence_chars"], len("근거 글자"))


class DefinitionsTest(unittest.TestCase):
    def test_the_fixed_percent_is_the_literal_characters_over_the_story_characters(self):
        post = fake_post("## 한눈에\n\n- 가나다라마 ⟦F:b⟧\n\n## 이 숫자를 읽을 때 주의\n\n- 바사아자차 고정", rendered="## 한눈에\n\n- 가나다라마 12.5개\n\n## 이 숫자를 읽을 때 주의\n\n- 바사아자차 고정")
        story = A.story_of(post.body_markdown)
        literal = F.REF_RE.sub("", post.template_markdown)
        self.assertEqual(T.measure(post)["fixed_pct"], round(100 * A.readable_chars(literal) / A.readable_chars(story)))
        self.assertEqual(T.measure(post)["fixed_pct"], round(100 * 26 / 31))      # 손으로 센 값: 틀 글자 한눈에 3 + 줄표 1 + 가나다라마 5 + 이 숫자를 읽을 때 주의 9 + 줄표 1 + 바사아자차 5 + 고정 2 = 26, 본문은 값 `12.5개` 5자가 더해져 31
        empty = fake_post("", rendered="", sources="")
        self.assertEqual(T.measure(empty)["fixed_pct"], 0)          # 본문이 비면 0 으로 닫는다(0 으로 나누지 않는다)

    def test_the_source_link_token_is_not_a_fixed_character(self):
        with_link = fake_post("가나다 " + R.SOURCE_LINK_TOKEN + " 라마바", rendered="가나다 링크 라마바")
        plain = fake_post("가나다  라마바", rendered="가나다 링크 라마바")
        self.assertEqual(T.measure(with_link)["fixed_pct"], T.measure(plain)["fixed_pct"])

    def test_c_formulas_are_the_design_set_and_all_exist(self):
        self.assertEqual(T.C_FORMULAS, frozenset({"F03_yoy", "F04_rank", "F11_range_position", "F14_median", "F16_count_between", "F17_season_rank", "F18_last_lower"}))
        self.assertLessEqual(T.C_FORMULAS, set(C.FORMULAS))
        for plain_formula in ("F01_change", "F02_pct_change", "F06_diff_from_mean", "F07_rolling_mean", "F09_max", "F10_min", "F12_count", "F15_day_max", "F19_months_between"):
            self.assertNotIn(plain_formula, T.C_FORMULAS)            # 재배열·산술은 C 등급이 아니다

    def test_a_unit_counts_as_c_only_when_a_value_reference_points_to_a_c_calculation(self):
        for formula_id in sorted(T.C_FORMULAS):
            post = fake_post("고정입니다. 값 ⟦F:k⟧ 입니다.", derived={"k": formula_id})
            with self.subTest(formula=formula_id):
                self.assertEqual(T.measure(post)["c_units"], 1)
        for formula_id in ("F01_change", "F07_rolling_mean", "F12_count"):
            self.assertEqual(T.measure(fake_post("고정입니다. 값 ⟦F:k⟧ 입니다.", derived={"k": formula_id}))["c_units"], 0, formula_id)
        self.assertEqual(T.measure(fake_post("고정입니다. 날짜 ⟦D:k⟧ 입니다.", derived={"k": "F17_season_rank"}))["c_units"], 0)      # 날짜 참조는 값이 아니다
        two = fake_post("값 ⟦F:k⟧ 하나 ⟦F:j⟧ 둘 입니다.", derived={"k": "F17_season_rank", "j": "F18_last_lower"})
        self.assertEqual(T.measure(two)["c_units"], 1)                                          # 한 문장에 C 계산이 둘이어도 문장은 하나다

    def test_calc_claims_count_units_not_occurrences_and_only_the_claiming_phrases(self):
        for text, expected in (("이 글이 직접 계산했습니다.", 1), ("이 글이 직접 계산했고 이 글이 직접 골랐습니다.", 1), ("직접 센 것입니다.", 1), ("이 글이 센 건수입니다.", 1), ("하루 최댓값을 직접 골랐습니다.", 1),
                               ("이 글은 평균과 범위만 계산했습니다.", 0), ("직접 견주지 않았습니다.", 0), ("값은 제공처 자료 그대로입니다.", 0)):
            with self.subTest(text=text):
                self.assertEqual(T.measure(fake_post(text))["calc_claims"], expected)
        self.assertEqual(T.measure(fake_post("이 글이 직접 계산했습니다. 이 글이 직접 계산했습니다."))["calc_claims"], 2)         # 두 문장은 둘
        self.assertEqual(T.measure(fake_post("- 가 이 글이 직접 계산했습니다.\n- 나 이 글이 직접 계산했습니다."))["calc_claims"], 2)

    def test_date_marks_are_the_collection_date_references_plus_the_dates_in_the_sources_section_and_nothing_in_the_tables(self):
        none = fake_post("고정 문장입니다.", sources="")
        self.assertEqual(T.measure(none)["date_marks"], 0)
        refs = fake_post("가 ⟦T:record⟧ 나 ⟦T:record⟧ 다 ⟦D:a⟧ 라", sources="")
        self.assertEqual(T.measure(refs)["date_marks"], 2)                                      # 기준일(D)은 받은 날짜가 아니다
        table_date = fake_post("| 기준 | 값 |\n| --- | ---: |\n| ⟦D:a⟧ | ⟦F:b⟧ |", rendered="| 기준 | 값 |\n| --- | ---: |\n| 2026년 11월 10일 | 3 |", sources="")
        self.assertEqual(T.measure(table_date)["date_marks"], 0)                                # 표에 같은 날짜 글자가 있어도 세지 않는다
        sources = "\n\n## 출처\n\n- [이름](https://example.invalid/x) — 열람 2026년 11월 10일\n- 이용 조건: 자료(2026년 11월 10일 열람)\n- 또 하나(2026년 11월 10일)"
        self.assertEqual(T.measure(fake_post("고정 문장입니다.", sources=sources))["date_marks"], 3)
        other = fake_post("고정 문장입니다.", sources="\n\n## 출처\n\n- 열람 2026년 11월 9일", date="2026-11-10T01:10:00Z")
        self.assertEqual(T.measure(other)["date_marks"], 0)                                     # 수집일과 다른 날짜는 세지 않는다

    def test_the_evidence_chars_are_the_length_of_the_evidence_text(self):
        for text in ("", "가", "가나다라마" * 100):
            self.assertEqual(T.measure(fake_post(evidence=text))["evidence_chars"], len(text))


class OnTheGoldenPostsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.posts = {name: TR.build(name) for name in TR.golden_cases()}
        cls.dated = {name: TR.build(name, provider_=H.provider(attribution_template=H.B_TEMPLATE)) for name in TR.golden_cases()}

    def test_the_block_has_the_seven_integer_fields_in_the_documented_order(self):
        self.assertEqual(T.FIELDS, ("fixed_pct", "pure_units", "value_units", "c_units", "calc_claims", "date_marks", "evidence_chars"))
        for name, post in self.posts.items():
            thin = T.measure(post)
            with self.subTest(post=name):
                self.assertEqual(tuple(thin), T.FIELDS)
                for value in thin.values():
                    self.assertIs(type(value), int)
                    self.assertGreaterEqual(value, 0)
                self.assertLessEqual(thin["fixed_pct"], 100)

    def test_the_values_equal_independent_counts(self):
        for name, post in self.posts.items():
            thin = T.measure(post)
            with self.subTest(post=name):
                self.assertEqual(thin["fixed_pct"], FH.quality_metrics(post)["fixed_percent"])                     # 시험 도구의 독립 구현과 같은 정의
                self.assertEqual(thin["evidence_chars"], len(post.evidence_text))
                self.assertEqual(thin["calc_claims"], TR.calc_claim_units(post))
                counted = [text for _section, kind, text in T.split_units(post.template_markdown) if kind in T.COUNTED_KINDS]
                self.assertEqual(len(counted), thin["pure_units"] + thin["value_units"] + sum(1 for text in counted if F.references(text) and not any(kind in "FSAV" for kind, _ref in F.references(text))))
                self.assertLessEqual(thin["c_units"], thin["value_units"])

    def test_the_post_text_says_each_calculation_claim_in_two_places_and_the_date_marks_match_the_phrases(self):
        for name in self.posts:
            with self.subTest(post=name):
                self.assertEqual(T.measure(self.posts[name])["calc_claims"], 2)
                self.assertEqual(T.measure(self.posts[name])["date_marks"], len(re.findall(r"(?:열람|받아 옮긴)", self.posts[name].body_markdown)))      # 시험용 출처 문구에는 열람일이 없다 — 안내와 출처 줄
                self.assertEqual(T.measure(self.dated[name])["date_marks"], 3)                                  # 실제 출처 문구는 열람일이 든다
                self.assertEqual(T.measure(self.dated[name])["date_marks"], len(re.findall(r"(?:열람|받아 옮긴|받은 값)", self.dated[name].body_markdown)))

    def test_the_fixed_percent_never_grew_against_the_state_before_s2c1_and_the_monthly_post_meets_the_design_targets(self):
        for name, post in self.posts.items():
            with self.subTest(post=name):
                self.assertLessEqual(T.measure(post)["fixed_pct"], BASELINE_FIXED_PCT[name])
        monthly = T.measure(self.posts["r04_ssn_monthly"])
        self.assertLessEqual(monthly["fixed_pct"], 64)                                                          # 수락 기준: 월별 고정 비율 66 → 64 이하
        self.assertGreaterEqual(monthly["c_units"], 4)                                                          # C 등급 계산 문장 1 → 4 이상
        self.assertLessEqual(monthly["calc_claims"], 2)
        self.assertLessEqual(monthly["evidence_chars"], 15_000)

    def test_the_old_recipes_are_measured_too_and_say_the_old_things(self):
        for recipe_id, params in FH.GOLDEN.items():
            old = FH.run(recipe_id, params=params)
            thin = T.measure(old)
            with self.subTest(recipe=recipe_id):
                self.assertEqual(thin["fixed_pct"], FH.quality_metrics(old)["fixed_percent"])
                self.assertGreaterEqual(thin["date_marks"], 3)                                                   # 옛 틀은 받은 날짜를 첫 문단 뒤 안내·'잠정치와 개정' 줄·출처 줄에서 말한다(바뀌지 않았다)
                self.assertGreaterEqual(thin["calc_claims"], 3)                                                  # 옛 틀은 첫 문단 뒤 안내·표 소개·주의 줄 모두 '직접 계산' 을 말한다(바뀌지 않았다)

    def test_the_measure_is_a_pure_function_of_the_post(self):
        for name, post in self.posts.items():
            self.assertEqual(T.measure(post), T.measure(post), name)
        rebuilt = TR.build("r04_ssn_monthly")
        self.assertEqual(T.measure(rebuilt), T.measure(self.posts["r04_ssn_monthly"]))


class RealisticMonthlyInputTest(unittest.TestCase):
    def test_a_358_month_input_has_the_designed_measures(self):
        values = [round(40 + (index * 53) % 151 + (index % 12) * 1.5, 2) for index in range(358)]
        post = TR.monthly_post(values, provider=H.provider(attribution_template=H.B_TEMPLATE))
        self.assertIsInstance(post, A.AssembledPost, post)
        thin = T.measure(post)
        self.assertGreaterEqual(thin["c_units"], 4)
        self.assertEqual((thin["calc_claims"], thin["date_marks"]), (2, 3))
        self.assertLessEqual(thin["fixed_pct"], BASELINE_FIXED_PCT["r04_ssn_monthly"])                          # 값 글자가 짧은(소수 한 자리) 입력은 비율이 조금 높다 — 기준(66)보다는 늘지 않는다. 64 이하는 소수 둘째 자리 골든에서 못박는다
        self.assertLessEqual(thin["evidence_chars"], 15_000)
        self.assertEqual(thin["evidence_chars"], len(post.evidence_text))


class SupplyWrapTest(unittest.TestCase):
    def test_thin_of_returns_the_measure_and_never_raises(self):
        post = TR.build("r04_ssn_monthly")
        self.assertEqual(S.thin_of(post), T.measure(post))
        with mock.patch.object(T, "measure", side_effect=KeyError("SECRET-PATH-TEXT")):
            wrapped = S.thin_of(post)
        self.assertEqual(wrapped, {"error": "KeyError"})                                                        # 예외 문장(값·경로가 있을 수 있는)은 남기지 않고 이름만 남긴다
        self.assertNotIn("SECRET", repr(wrapped))
        self.assertEqual(S.thin_of(SimpleNamespace()), {"error": "AttributeError"})                             # 글이 아닌 입력도 예외 없이 닫힌다


class PureModuleTest(unittest.TestCase):
    SOURCE_PATH = ROOT / "pipeline" / "fact_thin.py"

    def test_the_module_imports_only_re_and_three_fact_modules_and_has_no_clock_file_or_ai(self):
        text = self.SOURCE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(text, feature_version=(3, 10))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported |= {f"{node.module}.{alias.name}" for alias in node.names}
        self.assertEqual(imported, {"re", "pipeline.fact_assembler", "pipeline.facts", "pipeline.recipes"})
        code = re.sub(r'"""[\s\S]*?"""', "", text)
        for needle in ("llm", "gemini", "generator", "subprocess", "open(", "datetime", "random", "os.", "sys.", "getattr", "eval(", "exec("):
            self.assertNotIn(needle, code, needle)
        self.assertNotRegex(code, r"[~～〜]")

    def test_the_module_is_named_in_the_structure_and_flow_lists(self):
        structure = (ROOT / "tests" / "test_fact_structure.py").read_text(encoding="utf-8")
        scan = (ROOT / "tests" / "ai_flow_scan.py").read_text(encoding="utf-8")
        self.assertIn('"pipeline/fact_thin.py"', structure)
        self.assertIn('"fact_thin"', structure)
        self.assertIn('"fact_thin")', scan)
        self.assertIn("tests/test_fact_thin.py", structure)


if __name__ == "__main__":
    unittest.main()
