"""AP5(F104, 확인 015 항목 3)의 시험 — '계산이 값을 더하는 글' 판정 기준(`docs/FACT_PATH.md` §16-8)이 코드의 실제 값과 어긋나지 않는다.

① 골든 여섯 편을 조립해 얇음 측정(`fact_thin.measure`)의 `c_units` 와 `F15`(하루 최댓값) 사용을 재고 문서 표와 견준다. ② 문서 표의 글감이 글감 목록(`SPECS`)과 같고 판정과 후보 상태가 `HELD_SPEC_IDS` 와
어긋나지 않는다 — 더함은 `c_units` 1 이상, 경계와 해당(표만 옮김)은 `c_units` 0, 해당은 반드시 제외·더함과 경계는 제외가 아님. ③ `C_FORMULAS`·`MIN_DISTINCT_FORMULAS`·정지 해제 조건 넷째와 문서의 말이 같다.
④ 이 절과 결함 레지스터 두 행이 문서 규칙(물결표·링크·Liquid·로컬 경로·실제 이름)을 지키고 끝 안내 줄·절 모양을 해치지 않는다. 코드를 한 줄도 바꾸지 않은 묶음이라 문서와 코드의 일치만 본다.
Fact 모듈은 직접 import 하지 않고 다른 시험이 이미 가져온 이름을 빌려 쓴다(`test_fact_structure.NoConnectionTest`). 네트워크·시계 없이 돈다."""
import functools
import inspect
import json
import re
import unittest

import _bootstrap
import hold_helpers as HH
import test_fact_thin as TT
import test_s2c0_docs as T0
import test_space_recipes as TR

ROOT = _bootstrap.ROOT
K, FT, A = HH.K, TT.T, TR.A
DOC = (ROOT / "docs" / "FACT_PATH.md").read_text(encoding="utf-8")
REGISTER = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
HEADING = "### 16-8. "
SECTION = DOC[DOC.index(HEADING):] if HEADING in DOC else ""                                    # 소제목이 없으면 불러오다 멈추지 않고 시험마다 빨갛게 나오게 한다
POINTER = "설계 요약: [`S2C_PLAN.md`](./S2C_PLAN.md)"
LABELS = ("더함", "경계", "해당(표만 옮김)")
BOUNDARY_SPECS = {"kp_weekly", "sunspot_daily_monthly"}          # 사람이 '경계'로 적은 글감 둘(일별 Kp·일별 흑점수) — 바꾸려면 문서와 함께 일부러 고친다
TABLE_ONLY_SPECS = {"scales_weekly"}                              # '해당(표만 옮김)' — 후보에서 이미 빠져 있다


def register_row(number):
    return next(line for line in REGISTER.splitlines() if line.startswith(f"| **{number}** |"))


def doc_rows():
    """§16-8 의 글감 표 → {spec_id: [틀, c_units, F15 사용, 판정, 후보 상태]}."""
    rows = {}
    for line in SECTION.splitlines():
        match = re.match(r"\| `([a-z_]+)` ", line)
        if match:
            rows[match.group(1)] = [cell.strip() for cell in line.strip().strip("|").split("|")][1:]
    return rows


def golden_names_for(spec):
    """글감 하나에 맞는 골든 글 이름들 — Recipe 가 같고 key 가 같은 것(등급 틀 R06 은 key 를 받지 않으므로 글감의 key 로 본다)."""
    return [name for name, (recipe_id, _product, _rows, params) in TR.golden_cases().items() if recipe_id == spec.recipe_id and params.get("key", spec.key) == spec.key]


@functools.lru_cache(maxsize=None)
def measured():
    """{spec_id: (c_units, F15 사용)} — 골든 글을 조립해 얇음 측정으로 잰 값."""
    out = {}
    for spec in K.SPECS:
        post = TR.build(golden_names_for(spec)[0])
        out[spec.spec_id] = (FT.measure(post)["c_units"], "F15_day_max" in post.formulas)
    return out


class GoldenMeasurementTest(unittest.TestCase):
    def test_every_candidate_spec_has_exactly_one_golden_post_and_every_golden_post_one_spec(self):
        used = []
        for spec in K.SPECS:
            names = golden_names_for(spec)
            with self.subTest(spec=spec.spec_id):
                self.assertEqual(len(names), 1, names)
            used += names
        self.assertEqual(sorted(used), sorted(TR.golden_cases()))

    def test_the_measured_values_are_the_ones_the_document_table_states(self):
        rows = doc_rows()
        for spec_id, (c_units, uses_f15) in measured().items():
            with self.subTest(spec=spec_id):
                self.assertIn(spec_id, rows)
                self.assertEqual(int(rows[spec_id][1]), c_units)
                self.assertEqual(rows[spec_id][2], "있음" if uses_f15 else "없음")

    def test_the_measurement_is_a_count_of_c_grade_sentences_not_a_guess(self):
        for spec_id, (c_units, _uses_f15) in measured().items():
            self.assertIsInstance(c_units, int, spec_id)
            self.assertGreaterEqual(c_units, 0, spec_id)
        self.assertGreater(sum(c for c, _f in measured().values()), 0)                       # 세는 도구가 모두 0 을 내는 고장이면 표가 우연히 맞지 않게


class TableConsistencyTest(unittest.TestCase):
    def test_the_table_lists_exactly_the_candidate_specs_with_their_recipes(self):
        rows = doc_rows()
        self.assertEqual(sorted(rows), sorted(K.SPEC_IDS))
        for spec in K.SPECS:
            with self.subTest(spec=spec.spec_id):
                self.assertEqual(len(rows[spec.spec_id]), 5, rows[spec.spec_id])
                self.assertEqual(rows[spec.spec_id][0], spec.recipe_id[:3])

    def test_the_label_agrees_with_the_number_and_the_candidate_state_agrees_with_the_held_list(self):
        rows = doc_rows()
        for spec in K.SPECS:
            _recipe, c_text, f15_text, label, status = rows[spec.spec_id]
            held = spec.spec_id in HH.PRODUCTION_HELD                                            # 운영 기본값(다른 시험이 상수를 비워도 이 모듈을 가져올 때 읽은 값)
            with self.subTest(spec=spec.spec_id):
                self.assertIn(label, LABELS)
                self.assertEqual(status.startswith("제외"), held, status)
                self.assertEqual(label == "더함", int(c_text) >= 1, (label, c_text))              # 더함은 기계가 C 등급 계산을 센 글이고, 그 밖의 글은 0 이다
                if label == "해당(표만 옮김)":
                    self.assertTrue(held and f15_text == "없음", (held, f15_text))                # 표만 옮긴 글감은 후보에 없고 하루 값 모으기도 없다
                if label == "경계":
                    self.assertFalse(held)                                                      # 경계는 막지 않는다

    def test_the_table_only_spec_and_the_boundary_pair_are_the_ones_the_summary_names(self):
        labels = {spec_id: cells[3] for spec_id, cells in doc_rows().items()}
        self.assertEqual({s for s, label in labels.items() if label == "해당(표만 옮김)"}, TABLE_ONLY_SPECS)
        self.assertEqual({s for s, label in labels.items() if label == "경계"}, BOUNDARY_SPECS)
        self.assertEqual({s for s, label in labels.items() if label == "더함"}, set(K.SPEC_IDS) - TABLE_ONLY_SPECS - BOUNDARY_SPECS)
        self.assertTrue(TABLE_ONLY_SPECS <= set(HH.PRODUCTION_HELD))                             # 표만 옮긴 글감은 이미 후보에서 빠져 있다 — 코드를 바꾸지 않은 이유


class SectionStatementsTest(unittest.TestCase):
    def test_what_adds_value_and_what_does_not_are_stated_in_the_four_plus_one_words(self):
        for needle in ("큰 단위로 모으기", "표에 없는 앞 기간이나 작년 같은 때와 견주기", "정해 둔 기준과 견준 개수", "순위나 마지막으로 낮았던 때 같은 위치 계산",
                       "표에 이미 보이는 서너 값의 최댓값·최솟값·평균·차이뿐"):
            self.assertIn(needle, SECTION, needle)

    def test_the_seven_c_formulas_the_section_lists_are_the_code(self):
        start = SECTION.index("`fact_thin.C_FORMULAS`")
        listed = set(re.findall(r"`(F\d\d)`", SECTION[start:SECTION.index("큰 단위로 모으기는", start)]))
        self.assertEqual(listed, {name.split("_")[0] for name in FT.C_FORMULAS})
        self.assertEqual(len(FT.C_FORMULAS), 7)
        self.assertNotIn("F15_day_max", FT.C_FORMULAS)                                           # 하루 최댓값은 C 등급 계산이 아니라 따로 센다(문서가 그렇게 적었다)
        self.assertIn("`F15`(하루 최댓값)", SECTION)

    def test_the_held_list_and_the_formula_threshold_the_section_quotes_are_the_code(self):
        quoted = "HELD_SPEC_IDS = (" + ", ".join(f'"{spec_id}"' for spec_id in HH.PRODUCTION_HELD) + ")"
        self.assertIn(quoted, SECTION)
        self.assertEqual(A.MIN_DISTINCT_FORMULAS, 2)
        for needle in ("`MIN_DISTINCT_FORMULAS`", "`NO_ANALYSIS`", "서로 다른 계산식 둘 이상"):
            self.assertIn(needle, SECTION, needle)
        self.assertIn("NO_ANALYSIS", inspect.getsource(A))

    def test_the_decisions_are_the_recommended_defaults_and_the_code_gate_is_left_out(self):
        for needle in ("추천안", "답이 없으면 이대로 진행", "막지 않는다", "S2c-2", "코드 게이트는 이번 범위 밖", "별도 T2 묶음", "제품 코드는 한 줄도 바꾸지 않았다",
                       "일별 Kp·일별 흑점수·등급 현황 셋이 멈춰", "운영자 판단이 필요하다"):
            self.assertIn(needle, SECTION, needle)

    def test_the_fourth_resume_condition_it_serves_is_the_one_in_the_pause_setting(self):
        data = json.loads((ROOT / "pipeline" / "ops_inbox_policy.json").read_text(encoding="utf-8"))
        conditions = data["planned_pause"]["resume_conditions"]
        self.assertIn("계산이 값을 더하는 글만", conditions[3])
        self.assertIn("'계산이 값을 더하는 글만'", SECTION)
        self.assertIn("`resume_conditions` 넷째", SECTION)


class DocumentRulesTest(unittest.TestCase):
    def test_the_section_follows_the_document_rules(self):
        self.assertTrue(SECTION.startswith(HEADING))                                             # 빈 글이 규칙을 그냥 지나가지 않게
        self.assertGreater(len(SECTION), 1500)
        T0.assert_doc_rules(self, SECTION, "FACT_PATH 16-8")

    def test_it_sits_between_the_last_paragraph_and_the_pointer_inside_section_16(self):
        self.assertEqual(DOC.count(HEADING), 1)
        self.assertLess(DOC.index("### 16-7."), DOC.index(HEADING))
        self.assertLess(DOC.index("S2c-1 후속(S2C1B"), DOC.index(HEADING))
        self.assertLess(DOC.index(HEADING), DOC.index(POINTER))
        self.assertTrue(DOC.rstrip().endswith(POINTER))                                          # 끝 안내 줄은 그대로다(기존 문서 시험이 못박는다)
        self.assertEqual(len(re.findall(r"(?m)^## ", DOC[DOC.index("## 16. S2c-0"):])), 1)       # 새 절을 만들지 않았다
        self.assertEqual(SECTION.count("\n### "), 0)                                             # 이 소제목이 문서의 마지막 소제목이다
        for relative in re.findall(r"\]\((\./[^)]+)\)", SECTION):
            self.assertTrue((ROOT / "docs" / relative).exists(), relative)
        for relative in re.findall(r"`(tests/[A-Za-z0-9_]+\.py)`", SECTION):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_the_two_register_rows_exist_follow_the_rules_and_name_what_they_are_about(self):
        expected = {"D-388": ("F104", "확인 015 항목 3", "`docs/FACT_PATH.md` §16-8", "`tests/test_s2c_value_rule.py`", "문서와 시험뿐, 코드는 바꾸지 않았다", "`MIN_DISTINCT_FORMULAS`", "`NO_ANALYSIS`"),
                    "D-389": ("`c_units`", "`F15`", "최근 30일 평균과 그 앞 30일 평균 비교", "글을 거절하는 코드 게이트는 하지 않았다", "일별 Kp·일별 흑점수·등급 현황 셋이 멈춰", "`HELD_SPEC_IDS`")}
        for number, needles in expected.items():
            row = register_row(number)
            with self.subTest(row=number):
                self.assertEqual(row.count("|"), 7)
                T0.assert_doc_rules(self, row, number)
                for needle in needles:
                    self.assertIn(needle, row, needle)

    def test_the_numbers_in_the_first_register_row_are_the_measured_ones(self):
        order = ("kp_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly", "kp_storm_weekly", "flares_weekly", "scales_weekly")
        names = {"kp_weekly": "일별 Kp", "sunspot_daily_monthly": "일별 흑점수", "sunspot_monthly_monthly": "월별 흑점수", "kp_storm_weekly": "Kp 폭풍", "flares_weekly": "플레어", "scales_weekly": "등급 현황"}
        self.assertEqual(sorted(order), sorted(K.SPEC_IDS))
        stated = "·".join(f"{names[spec_id]} {measured()[spec_id][0]}" for spec_id in order)
        self.assertIn(stated, register_row("D-388"))


if __name__ == "__main__":
    unittest.main()
