"""S2C1 묶음의 문서 시험 — `docs/FACT_PATH.md` §16-7(S2c-1)·§5 계산식 표·§14 표와 결함 레지스터 D-338–D-343 이 코드의 실제 이름·값과 어긋나지 않고 문서 규칙(물결표·http 링크·Liquid·로컬 경로·광고 번호·실제 이름 없음)을 지킨다.
네트워크 없이 파일만 읽는다. 다른 가지의 결정 번호·전체 최댓값은 못박지 않는다 — 이 묶음의 행이 있고 서로 이어지는지만 본다. 표의 '후' 숫자는 이 묶음의 골든 글이 내는 값이다
(S2c-2 처럼 골든을 바꾸는 묶음은 §16-7-5 의 표를 함께 고쳐야 한다 — 골든 파일을 바꾸면 그 묶음의 골든 시험도 같이 고치는 것과 같다)."""
import re
import unittest

import _bootstrap
import fact_helpers as FH
import test_space_recipes as TR

from pipeline import calc as C
from pipeline import fact_thin as T
from pipeline import facts as F
from pipeline import recipes as R
from pipeline import recipes_noregion as RN
from pipeline.adapters import noaa_swpc as N

ROOT = _bootstrap.ROOT
DOC = (ROOT / "docs" / "FACT_PATH.md").read_text(encoding="utf-8")
REGISTER = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
SECTION = DOC[DOC.index("### 16-7."):]
NUMBERS = ("D-338", "D-339", "D-340", "D-341", "D-342", "D-343")
FORBIDDEN = "(?i)" + "|".join(("ca-" + "pub", "ads" + "ense", r"pub-\d{8,}", "chance" + "blog", "shine" + "88", "kc" + "yoon", "pew" + "research", "ma" + "cat", "blog" + "spot", "adsby" + "google"))


def register_row(number):
    return next(line for line in REGISTER.splitlines() if line.startswith(f"| **{number}** |"))


def cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def table_rows(text):
    rows = []
    for line in text.splitlines():
        if line.startswith("|"):
            found = cells(line)
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in found):
                rows.append(found)
    return rows


def assert_doc_rules(testcase, text, label):
    testcase.assertNotRegex(text, "[~～〜]", label)                                    # 범위는 en 대시
    testcase.assertNotRegex(text, r"(?i)https?://|www\.|\bftp://", label)               # 문서에 링크 금지
    for liquid in ("{{", "{%", "%}", "}}"):
        testcase.assertNotIn(liquid, text, label)
    testcase.assertNotRegex(text, r"[A-Za-z]:[\\/]|/Users/|/home/|\\\\", label)         # 로컬 경로 금지
    testcase.assertNotRegex(text, FORBIDDEN, label)                                     # 광고 번호·실제 블로그 이름 금지


def number_of(text):
    return int(re.sub(r"[^0-9]", "", text))


class SectionTest(unittest.TestCase):
    def test_the_subsection_follows_the_document_rules_and_stays_inside_section_16_which_still_ends_with_the_pointer(self):
        assert_doc_rules(self, SECTION, "FACT_PATH §16-7")
        section_16 = DOC[DOC.index("## 16. S2c-0"):]
        self.assertEqual(len(re.findall(r"(?m)^## ", section_16)), 1)                    # S2c-0 시험이 못박은 모양: §16 은 마지막 절이고 소제목 하나뿐
        self.assertTrue(DOC.rstrip().endswith("설계 요약: [`S2C_PLAN.md`](./S2C_PLAN.md)"))
        for heading in ("### 16-7. S2c-1 —", "#### 16-7-1. a —", "#### 16-7-2. b —", "#### 16-7-3. c —", "#### 16-7-4. d —", "#### 16-7-5. 전·후 측정과 한계", "#### 16-7-6. 시험"):
            self.assertIn(heading, SECTION, heading)
        self.assertLess(DOC.index("### 16-6. 시험"), DOC.index("### 16-7."))
        for relative in re.findall(r"\]\((\./[^)]+)\)", SECTION):
            self.assertTrue((ROOT / "docs" / relative).exists(), relative)

    def test_it_says_what_it_did_not_change_and_that_nothing_was_switched_on(self):
        for needle in ("켜지는 값은 하나도 바뀌지 않았다", "`.github/`(워크플로)", "레지스트리 값", "발행 정지 변수", "광고 표면", "공개 글", "AI 가능 함수·`pipeline.llm`·생성기를 가져오지 않는다", "D-338–D-343"):
            self.assertIn(needle, SECTION, needle)

    def test_the_names_and_values_the_section_states_are_the_codes(self):
        for name in ("F17_season_rank", "F18_last_lower", "F19_months_between", "INTEGER_FORMULAS", "calc.FORMULA_LABELS", "recipes.CALC_WORDS", "SEASON_TABLE_ROWS", "SEASON_CAUTION", "count_window",
                     "SeriesSubject.compare", "SSN_MONTHLY_KEEP_MONTHS", "fact_thin.py", "thin_of", "measure(post)", "result.json", "`thin`", "NO_MATCH", "NOT_MONTHLY", "NOT_SAME_SEASON", "DUPLICATE_MONTH"):
            self.assertIn(name, SECTION, name)
        for formula_id in ("F17_season_rank", "F18_last_lower", "F19_months_between"):
            self.assertIn(formula_id, C.FORMULAS)
            self.assertIn(formula_id, C.FORMULA_LABELS)
        self.assertEqual((N.SSN_MONTHLY_KEEP_MONTHS, RN.SEASON_TABLE_ROWS, C.MIN_SEASON_MEMBERS), (360, 8, 3))
        self.assertIn("**360**(30년)", SECTION)
        self.assertIn("최대 720(관측 360 + 평활 360", SECTION)
        self.assertIn("최대 8줄", SECTION)
        self.assertIn("묶음 셋 미만이면 만들지 않는다", SECTION)
        for word in ("같은 달 순위", "마지막으로 낮은 달", "경과 개월"):
            self.assertIn(word, SECTION)
        self.assertEqual({word for _formula, word in R.CALC_WORDS if _formula in ("F17_season_rank", "F18_last_lower", "F19_months_between")}, {"같은 달 순위", "마지막으로 낮은 달", "경과 개월"})
        self.assertTrue({"NOT_MONTHLY", "NOT_SAME_SEASON", "DUPLICATE_MONTH", "NO_MATCH"} <= set(C.REASON_TEXT))

    def test_the_thin_table_lists_exactly_the_seven_fields_in_order_and_the_c_formulas_are_the_code_set(self):
        part = SECTION[SECTION.index("#### 16-7-4."):SECTION.index("#### 16-7-5.")]
        names = [re.sub(r"[`*]", "", cells_[0]) for cells_ in table_rows(part)[1:]]
        self.assertEqual(tuple(names), T.FIELDS)
        listed = {f"F{number}" for number in re.findall(r"`F(\d\d)`", part[part.index("그 가운데 C 등급 계산"):part.index("그 가운데 C 등급 계산") + 140])}
        self.assertEqual(listed, {formula_id.split("_", 1)[0] for formula_id in T.C_FORMULAS})
        self.assertIn("**어느 값도 판정이 아니라 사람이 먼저 볼 순서를 정하는 신호다**", part)
        self.assertIn("`{\"error\": 예외 이름}`", part)
        self.assertIn("피드 경로의 결과에는 없다", part)

    def test_the_files_the_section_names_exist(self):
        found = set(re.findall(r"`(tests/[A-Za-z0-9_]+\.py)`", SECTION))
        self.assertTrue({"tests/test_fact_thin.py", "tests/test_s2c1_docs.py", "tests/test_space_calc.py", "tests/test_space_recipes.py", "tests/test_space_adapter.py", "tests/test_fact_shadow.py"} <= found)
        for relative in found | {"pipeline/fact_thin.py", "pipeline/fact_supply.py", "pipeline/shadow_run.py", "docs/S2C_PLAN.md"}:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_the_before_and_after_table_matches_what_the_golden_posts_say_now(self):
        part = SECTION[SECTION.index("#### 16-7-5."):SECTION.index("#### 16-7-6.")]
        rows = {re.sub(r"\*", "", cells_[0]): cells_[1:] for cells_ in table_rows(part)[1:]}
        names = {"일별 Kp 최대값(R04)": "r04_kp", "일별 흑점수(R04)": "r04_ssn_daily", "월별 흑점수(R04)": "r04_ssn_monthly", "Kp 폭풍 기준(R05)": "r05_kp_storm", "플레어 등급별 건수(R05)": "r05_flares", "등급 현황과 예보(R06)": "r06_scales"}
        for label, golden in names.items():
            post = TR.build(golden)
            thin = T.measure(post)
            after = [number_of(cell.split("→")[1]) for cell in rows[label]]
            causes = sum(1 for unit in re.split(r"(?<=[.!?])\s+|\n", TR.story(post)) if TR.CAUSE_RE.search(unit))
            dates = len(re.findall(r"(?:열람|받아 옮긴|받은 값)", post.body_markdown))
            with self.subTest(post=golden):
                self.assertEqual(after, [FH.quality_metrics(post)["story"], thin["fixed_pct"], thin["c_units"], thin["calc_claims"], dates, causes])
        self.assertEqual([row for row in rows if row.startswith("월별 흑점수 — 실제")], ["월별 흑점수 — 실제 일별 파일의 달 평균 277개월"])

    def test_the_acceptance_numbers_the_section_claims_hold_for_the_golden_monthly_post(self):
        thin = T.measure(TR.build("r04_ssn_monthly"))
        self.assertLessEqual(thin["fixed_pct"], 64)
        self.assertGreaterEqual(thin["c_units"], 4)
        self.assertEqual(thin["calc_claims"], 2)
        self.assertIn("월별 C 등급 계산 문장 4 이상", SECTION)
        self.assertIn("월별 고정 비율 64% 이하", SECTION)
        self.assertIn("기존 틀 R01–R03 골든 바이트 불변", SECTION)

    def test_the_decisions_the_section_states_are_the_ones_the_code_made(self):
        for needle in ("② `F18` 입력은 받치는 값만", "③ 설계의 '같은 달 중앙값과의 차'는 만들지 않았다", "④ '마지막으로 높았던 달'(대칭)은 만들지 않았다", "⑥ 머리 소개 변주는 S2c-2 로 미뤘다", "`F20`–`F22` 로 밀린다"):
            self.assertIn(needle, SECTION, needle)
        self.assertEqual(len(C.FORMULAS), 19)                                                  # 번호가 빈틈없이 19 까지 — 다음 묶음은 F20 부터 쓴다
        self.assertEqual(sorted(int(formula_id[1:3]) for formula_id in C.FORMULAS), list(range(1, 20)))
        self.assertIn("하지 않은 것", SECTION)
        self.assertIn("Kp 글의 '하루 값' 정의 되풀이", SECTION)
        self.assertIn("선택 항목, D-342", SECTION)


class OtherDocPartsTest(unittest.TestCase):
    def test_the_calc_table_the_adapter_table_and_the_recipe_table_say_the_new_things(self):
        table = DOC[DOC.index("## 5. 계산식"):DOC.index("**비교 가능성")]
        rows = {cells_[0]: cells_ for cells_ in table_rows(table) if cells_ and cells_[0].startswith("F")}
        for formula_id in ("F17_season_rank", "F18_last_lower", "F19_months_between"):
            self.assertIn(formula_id, rows)
            self.assertIn(f"`{C.FORMULAS[formula_id].__name__}", rows[formula_id][1])
        self.assertIn("입력 id 는 찾은 달(첫째)·`cur`·그 달보다 나중인 달들뿐이다", rows["F18_last_lower"][2])
        self.assertIn("`INTEGER_FORMULAS`: F04·F12·F16·F17·F19", DOC)
        self.assertIn("최근 360개월(30년)만 Fact", DOC)
        self.assertNotIn("최근 60개월만 Fact", DOC)                                                # 옛 문구는 남지 않았다
        recipe_table = [cells_ for cells_ in table_rows(DOC[DOC.index("### 14-3."):DOC.index("### 14-4.")]) if cells_[0].startswith("`R04")]
        self.assertEqual(len(recipe_table), 1)
        for formula_id in RN.R04_NOREGION_SERIES.formulas:
            self.assertIn(formula_id.split("_", 1)[0], recipe_table[0][2])
        self.assertIn("F17 F18 F19", recipe_table[0][2])
        self.assertTrue({"F17_season_rank", "F18_last_lower", "F19_months_between"} <= set(RN.R04_NOREGION_SERIES.formulas))

    def test_the_module_docstrings_describe_the_new_code(self):
        self.assertIn("F17_season_rank", C.__doc__)
        self.assertIn("F19_months_between", C.__doc__)
        self.assertIn("docs/FACT_PATH.md §16-7", T.__doc__)
        self.assertIn("360", (ROOT / "pipeline" / "adapters" / "noaa_swpc.py").read_text(encoding="utf-8").split("SSN_MONTHLY_KEEP_MONTHS", 1)[1][:80])
        self.assertIn("최근 360개월", N.__doc__)


class RegisterRowsTest(unittest.TestCase):
    STATES = {"D-338": "**해결**", "D-339": "**해결**", "D-340": "**완화**", "D-341": "**해결**", "D-342": "**열림**", "D-343": "**열림**"}
    SEVERITY = {"D-338": "낮음", "D-339": "정보", "D-340": "낮음", "D-341": "정보", "D-342": "정보", "D-343": "정보"}
    POINTERS = {"D-338": "§16-7-1", "D-339": "§16-7-2", "D-340": "§16-7-3", "D-341": "§16-7-4", "D-342": "§16-7-4", "D-343": "§16-7-5"}

    def test_the_six_rows_exist_once_each_in_order_after_d337_with_six_cells_and_the_right_marks(self):
        found = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", REGISTER)
        positions = [found.index(number) for number in ("D-337",) + NUMBERS]
        self.assertEqual(positions, sorted(positions))
        for number in NUMBERS:
            self.assertEqual(found.count(number), 1, number)
            row = register_row(number)
            self.assertEqual(len(cells(row)), 6, number)
            self.assertEqual(cells(row)[1], self.SEVERITY[number], number)
            self.assertTrue(cells(row)[4].startswith(self.STATES[number]), (number, cells(row)[4][:30]))
            self.assertIn(self.POINTERS[number], row, number)
            assert_doc_rules(self, row, number)

    def test_each_row_names_what_it_is_about(self):
        expected = {"D-338": ("F17_season_rank", "F18_last_lower", "F19_months_between", "360개월", "C 등급 계산 문장 1 → 4", "69 → 63%", "4,859자", "F20", "같은 달 중앙값"),
                    "D-339": ("count_window", "관측 N개", "MonthlyCountWindowTest", "바이트까지 같다"),
                    "D-340": ("받은 날짜 4 → 3", "원인 2 → 1", "RepeatCleanupTest", "R01–R03 은 바이트까지 같다", "Kp 글의 '하루 값' 정의 되풀이"),
                    "D-341": ("fact_thin.py", "thin", "fact_supply.thin_of", "보류 코드는 없다", "ThinBlockTest"),
                    "D-342": ("build_pr_body", "이력 항목", "설계 ⑦ e", "별도 묶음"),
                    "D-343": ("358개월", "1개월 전", "반 칸 규칙", "소수 셋째 자리", "그림자 실행")}
        for number, needles in expected.items():
            for needle in needles:
                self.assertIn(needle, register_row(number), (number, needle))

    def test_the_section_names_the_same_numbers(self):
        self.assertIn("결정·결함은 D-338–D-343", SECTION)
        for number in NUMBERS:
            self.assertIn(number, SECTION, number)


if __name__ == "__main__":
    unittest.main()
