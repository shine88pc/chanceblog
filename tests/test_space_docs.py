"""S2a 문서 시험: `docs/FACT_PATH.md` 14절이 코드의 실제 이름·표와 어긋나지 않고(제품·키·Recipe·사유 코드·후보 이름), 결정 D-200–D-209 와 결함 레지스터 D-210–D-219 가 이 묶음의 번호로 한 번씩만 있고,
문서 규칙(물결표·http 링크·Liquid·로컬 경로 없음)을 지킨다. 다른 묶음의 번호·전체 최댓값·개수를 못박지 않는다. 네트워크 없이 파일만 읽는다."""
import re
import unittest

import _bootstrap

from pipeline import calc as C
from pipeline import fact_assembler as A
from pipeline import fact_candidates as K
from pipeline import facts as F
from pipeline import recipes as R
from pipeline import recipes_noregion as RN
from pipeline.adapters import noaa_swpc as N

ROOT = _bootstrap.ROOT
DOC = (ROOT / "docs" / "FACT_PATH.md").read_text(encoding="utf-8")
ARCH = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
REGISTER = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
SECTION = DOC[DOC.index("## 14. S2a"):]
DECISIONS = [f"D-{number}" for number in range(200, 210)]
ROWS = [f"D-{number}" for number in range(210, 220)]


def table_rows(text):
    rows = []
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                rows.append(cells)
    return rows


class SectionTest(unittest.TestCase):
    def test_the_section_follows_the_document_rules(self):
        self.assertGreater(len(SECTION), 6000)
        for text in (SECTION, *[next(line for line in REGISTER.splitlines() if line.startswith(f"| **{number}** |")) for number in ROWS]):
            self.assertNotRegex(text, "[~～〜]")
            self.assertNotRegex(text, r"(?i)https?://|www\.|\bftp://")
            for liquid in ("{{", "{%", "%}", "}}"):
                self.assertNotIn(liquid, text)
            self.assertNotRegex(text, r"[A-Za-z]:[\\/]|/Users/|/home/|\\\\")
            self.assertNotRegex(text, "(?i)" + "|".join(("ca-" + "pub", "ads" + "ense", r"pub-\d{8,}", "chance" + "blog", "shine" + "88", "kc" + "yoon", "pew" + "research")))
        self.assertIn("연결하지 않았다", SECTION)
        self.assertNotRegex(SECTION, r"생성기에 연결(?:했|됐|되었)")
        self.assertIn("S2b", SECTION)

    def test_the_sub_sections_and_what_they_promise_are_there(self):
        for heading in ("### 14-1. 어댑터", "### 14-2. Fact 키", "### 14-3. 지역 없는 틀", "### 14-4. 출처 문구 자동 첨부(R14)", "### 14-5. 중복 방지와 후보 순서", "### 14-6. 어댑터 체크리스트", "### 14-7. S2b 에 넘기는 것",
                        "### 14-8. 한계와 남은 일"):
            self.assertIn(heading, SECTION)
        for needle in ("확인 요청 008", "확인 요청 007", "제목에 값 없음", "AI 미사용", "`blogs.json`", "방어 묶음(AG)", "허용 목록(SRC2)", "STATUS_MISMATCH", "ATTRIBUTION_REQUIRED",
                       "ATTRIBUTION_SCOPE_MISMATCH", "own_data_only", "producer", "AF4", "reader_notes", "`과학·환경`", "새 분류는 만들지 않았다"):
            self.assertIn(needle, SECTION)
        checklist = SECTION[SECTION.index("### 14-6."):SECTION.index("### 14-7.")]
        self.assertEqual(len([cells for cells in table_rows(checklist) if cells[0].isdigit() or re.match(r"\d+ ", cells[0])]), 10)

    def test_every_product_key_recipe_candidate_and_code_is_named(self):
        for product_id, product in N.PRODUCTS.items():
            self.assertIn(f"`{product_id}`", SECTION)
            self.assertIn(product.path, SECTION)
        for key in N.LABELS:
            short = key.rsplit("_", 1)[0] if key.startswith("xray_class_floor_") else key
            self.assertIn(short, SECTION, key)
        for recipe_id, recipe in RN.NOREGION_RECIPES.items():
            self.assertIn(f"`{recipe_id}` {recipe.name_ko}", SECTION)
            for formula_id in recipe.formulas:
                self.assertIn(formula_id.split("_", 1)[0], SECTION)
        for spec_id in K.SPEC_IDS:
            self.assertIn(f"`{spec_id}`", SECTION)
        for function in ("attribution_line", "plan_candidates", "get_recipe", "product_source_name", "product_url", "candidate_key", "NoaaSwpcAdapter", "title_template_problem"):
            self.assertIn(function, DOC)
        for code in set(re.findall(r'Insufficient\("([A-Z_]+)"', (ROOT / "pipeline" / "recipes_noregion.py").read_text(encoding="utf-8"))) | {"STATUS_MISMATCH", "HAS_REGION", "NO_THRESHOLD", "UNKNOWN_SUBJECT"}:
            self.assertIn(f"`{code}`", DOC, code)
        for code in ("ATTRIBUTION_REQUIRED", "ATTRIBUTION_SCOPE_MISMATCH", "TITLE_HAS_VALUE"):
            self.assertIn(f"`{code}`", DOC)

    def test_the_formula_rows_and_the_integer_formulas_are_documented(self):
        for formula_id in ("F15_day_max", "F16_count_between"):
            self.assertIn(formula_id, DOC)
            self.assertIn(f"`{C.FORMULAS[formula_id].__name__}", DOC)
        self.assertIn("INTEGER_FORMULAS`: F04·F12·F16", DOC)
        self.assertEqual(F.INTEGER_FORMULAS, frozenset({"F04_rank", "F12_count", "F16_count_between"}))
        self.assertIn("등급 단계(단계)는 `ratio_ok` 가 거짓", DOC)

    def test_the_recipe_table_of_the_section_matches_the_code(self):
        table = [cells for cells in table_rows(SECTION[SECTION.index("### 14-3."):SECTION.index("### 14-4.")]) if cells[0].startswith("`R0")]
        self.assertEqual({cells[0] for cells in table}, {f"`{rid}` {recipe.name_ko}" for rid, recipe in RN.NOREGION_RECIPES.items()})
        for cells in table:
            rid = cells[0].split("`")[1]
            self.assertTrue(all(fid.split("_", 1)[0] in cells[2] for fid in RN.NOREGION_RECIPES[rid].formulas), rid)
            self.assertNotRegex(cells[3], r"⟦F:|높아|낮아")                                  # 제목 틀에 값이 없다

    def test_the_title_policy_is_stated_where_the_old_recipes_are_described(self):
        policy = DOC[DOC.index("**제목 정책(S2a, D-200)**"):DOC.index("**비교 불가면 그 문장을 만들지 않는다**")]
        for needle in ("측정값(숫자)을 넣지 않고", "이름(`⟦L⟧`)·지역(`⟦R⟧`)·기준일(`⟦D⟧`·`⟦T⟧`)만", "설명(`description`)과 본문에는 값이 있어도 된다", "제목·태그·분류뿐", "TITLE_HAS_VALUE",
                       "`first_row`·`last_row`", "R18"):
            self.assertIn(needle, policy)
        self.assertEqual(sorted(R.TITLE_DATE_SLOTS), sorted([("D", "main"), ("D", "cur"), ("D", "first_row"), ("D", "last_row"), ("D", "first"), ("T", "record")]))

    def test_the_known_limits_are_stated(self):
        limits = SECTION[SECTION.index("### 14-8."):]
        for needle in ("제3자 필드", "45일 예보", "이 글이 읽은 일수", "5.00", "interval_scale_", "평활값", "가상 응답은 모양만", "새 분류가 필요하지 않았다"):
            self.assertIn(needle, limits)


class NumberingTest(unittest.TestCase):
    def test_the_decisions_of_this_bundle_exist_once_each_in_order(self):
        found = re.findall(r"(?m)^\| (D-\d+) \|", DOC)
        for number in DECISIONS:
            self.assertEqual(found.count(number), 1, number)
        mine = [item for item in found if item in DECISIONS]
        self.assertEqual(mine, DECISIONS)
        rows = {cells[0]: cells for cells in table_rows(DOC) if cells and cells[0] in DECISIONS}
        for number in DECISIONS:
            self.assertEqual(len(rows[number]), 3, number)                                   # 번호·결정·이유
            self.assertTrue(rows[number][1] and rows[number][2])

    def test_the_register_rows_of_this_bundle_exist_once_each_and_have_six_cells(self):
        found = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", REGISTER)
        self.assertEqual(len(found), len(set(found)))
        for number in ROWS:
            self.assertEqual(found.count(number), 1, number)
            row = next(line for line in REGISTER.splitlines() if line.startswith(f"| **{number}** |"))
            self.assertEqual(row.count("|"), 7, number)
            for needle in ("FACT_PATH.md", "S2a", "T2"):
                self.assertIn(needle, row)
        order = [item for item in found if item in ROWS]
        self.assertEqual(order, ROWS)
        self.assertGreater(found.index("D-210"), found.index("D-180"))                       # 번호순으로 D-180 보다 뒤(끝쪽) — 다른 묶음의 행이 사이에 끼어도 통과한다

    def test_the_numbers_do_not_overlap_with_the_other_bundles_ranges_i_know_of(self):
        ours = {int(item.split("-")[1]) for item in DECISIONS + ROWS}
        others = set(range(150, 200)) | set(range(160, 180)) | {186, 187, 188, 189, 190, 191, 192, 193}
        self.assertFalse(ours & others)
        self.assertEqual(min(ours), 200)

    def test_the_architecture_section_mentions_the_bundle_without_a_second_module_row(self):
        section = ARCH[ARCH.index("## 4-10."):ARCH.index("## 5. 상태·멱등성·동시성")]
        self.assertIn("S2a", section)
        for module in ("pipeline/adapters/noaa_swpc.py", "pipeline/recipes_noregion.py", "pipeline/fact_candidates.py"):
            self.assertIn(module, section)
        self.assertEqual(len([cells for cells in table_rows(section) if cells[0].startswith("`pipeline/")]), 1)
        self.assertNotRegex(section, "[~～〜]")
        self.assertNotRegex(section, r"(?i)https?://|www\.")

    def test_the_doc_never_claims_the_path_is_connected(self):
        self.assertNotRegex(DOC, r"생성기에 연결(?:했|됐|되었)")
        self.assertIn("연결은 2단계", DOC)
        self.assertIn("켜는 설정은 아직 없다", DOC)
        self.assertNotIn("content_source", (ROOT / "pipeline" / "blogs.json").read_text(encoding="utf-8"))


class FollowUpN2N4DocsTest(unittest.TestCase):
    """F2 독립 검증의 낮은 지적 N2–N4 를 S2a 가 고쳤다는 기록이 결정 표·한계 절·결함 레지스터에 있고, 사실이 아니라고 밝혀진 옛 문구가 남아 있지 않다."""

    def rows(self, *numbers):
        return {cells[0]: cells for cells in table_rows(DOC) if cells and cells[0] in numbers}

    def test_the_decision_rows_say_what_was_added(self):
        rows = self.rows("D-152", "D-154", "D-156")
        self.assertEqual(set(rows), {"D-152", "D-154", "D-156"})
        for number in rows:
            self.assertEqual(len(rows[number]), 3, number)
        text = {number: rows[number][1] + " " + rows[number][2] for number in rows}
        for needle in ("평균·중앙값", "평균과 중앙값의 차이", "N3(S2a)", "settle_context", "3.3·3.3·3.4·3.6"):
            self.assertIn(needle, text["D-152"])
        for needle in ("서술격 '이다' 꼴", "N2, S2a", "받침 없는 세는 말 뒤에서만", "개인·주인·해고·해지·대지·대야·배지·개요·주요", "N2(독립 검증)", "13개를 놓쳤다"):
            self.assertIn(needle, text["D-154"])
        for needle in ("5개 가운데 4개", "삼 초과이므로써", "반영하는", "tests/test_space_f2fix.py", "동치가 아니다"):
            self.assertIn(needle, text["D-156"])
        self.assertNotIn("재검증이 살려 둔 변이 5개(", DOC)                      # 5개를 모두 잡았다는 옛 문구는 사실이 아니라 고쳤다

    def test_the_limits_section_describes_the_endings_the_half_steps_and_the_info_items(self):
        limits = DOC[DOC.index("## 13. 한계와 남은 일"):DOC.index("## 14. ")]
        for needle in ("서술격 어미 꼴(N2, S2a)", "받침 없는 세는 말", "열 가지고 있는 병", "두 주요 지표", "N3, S2a", "중앙값(짝수 곳이면 가운데 두 값의 평균)", "지역 없는 시계열(R04)의 창 평균", "N5–N9"):
            self.assertIn(needle, limits)
        self.assertNotIn("같은 줄에 견주는 말이 없다", DOC)                      # N3: 사실이 아닌 이유 문구(해석 문단이 평균과 중앙값의 차이를 적는다)를 지웠다

    def test_the_register_row_names_the_three_findings_and_stays_in_order(self):
        row = next(line for line in REGISTER.splitlines() if line.startswith("| **D-214** |"))
        for needle in ("N2–N4", "서술격", "중앙값", "초과", "동치", "FACT_PATH.md", "tests/test_space_f2fix.py", "N5–N9"):
            self.assertIn(needle, row)
        found = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", REGISTER)
        self.assertGreater(found.index("D-214"), found.index("D-213"))


class FollowUpS2afixDocsTest(unittest.TestCase):
    """S2a 첫 독립 검증의 지적(D2–D14)을 S2AFIX 가 고쳤다는 기록이 문서에 있고(결정 행·14절·한계·결함 레지스터 D-215–D-219), 운영자 결정 항목과 이웃 기간 한계가 적혀 있다."""

    def test_the_decision_rows_say_the_new_rules(self):
        rows = {cells[0]: cells for cells in table_rows(DOC) if cells and cells[0] in ("D-154", "D-206", "D-208")}
        self.assertEqual(set(rows), {"D-154", "D-206", "D-208"})
        text = {number: " ".join(cells[1:]) for number, cells in rows.items()}
        for needle in ("명시적으로 `ALLOWED`", "모르면 막는다", "`own_data_only` 가 명시적으로 참일 때만"):
            self.assertIn(needle, text["D-206"])
        for needle in ("한 기간에 하나만", "대표 글감", "72%"):
            self.assertIn(needle, text["D-208"])
        for needle in ("`구간`·`줄`·`열`·`날`", "S2AFIX D12", "`한 날`"):
            self.assertIn(needle, text["D-154"])
        self.assertNotIn("출처 표시 칸이 `CONDITIONAL` 인데 템플릿이 비면", DOC)                   # 옛 뜻(조건부일 때만 막음)은 모르면 막는 쪽으로 바뀌었다

    def test_section_14_describes_the_background_sentences_the_kp_column_the_ties_and_the_groups(self):
        for needle in ("배경 문장·Kp 증감 칸·R05 동률", "`KP_ABOUT`", "`SCALE_ABOUT`", "`KP_LIMIT`", "고정 글자 비율은 줄지 않았다", "Kp 표에는 증감 칸·줄이 없다", "−2.66", "flat_table",
                       "tests/test_space_gate.py", "`conflict_groups`", "대표 글감 하나", "이웃 기간의 겹침은 막지 못한다", "NFKC", "명시적으로 `ALLOWED`", "own_data_only"):
            self.assertIn(needle, SECTION)

    def test_the_limits_name_the_operator_decisions_and_the_collection_time(self):
        limits = SECTION[SECTION.index("### 14-8."):]
        for needle in ("켜기 전 운영자 결정 — 제목·태그·라벨의 기관명(NOAA) 사용 범위", "S2AFIX D10", "수집 시각의 한계", "00:30 UTC", "S2AFIX D11", "받아들일지는 운영자가 정한다", "S2AFIX D5", "0.01"):
            self.assertIn(needle, limits)

    def test_the_register_rows_d215_to_d219_name_each_finding_and_stay_in_order(self):
        names = ("D-215", "D-216", "D-217", "D-218", "D-219")
        rows = {number: next(line for line in REGISTER.splitlines() if line.startswith(f"| **{number}** |")) for number in names}
        expected = (("D-215", ("추이", "QG6-TITLE-WORD", "240", "720", "tests/test_space_gate.py")), ("D-216", ("InvalidOperation", "ArithmeticError", "42 → 0", "3.12·3.10")),
                    ("D-217", ("같은 Kp", "conflict_groups", "이웃 기간", "S2b")), ("D-218", ("배경 문장", "고정 문장 비율은 줄지 않았다", "−2.66", "flat_table")),
                    ("D-219", ("ALLOWED", "`own_data_only`", "구간", "9.33", "기관명", "수집 시각")))
        for number, needles in expected:
            for needle in needles:
                self.assertIn(needle, rows[number], (number, needle))
        found = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", REGISTER)
        positions = [found.index(number) for number in ("D-214",) + names]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("D-219", next(line for line in REGISTER.splitlines() if line.startswith("| **D-211** |")))        # D-211 의 맞물림 문장이 이후 지적을 가리킨다
        self.assertNotIn("R01–R03 의 본문·표 출력은 바이트까지 같고 제목만 바뀐다", REGISTER)                                  # D13: 사실이 아닌 옛 문구는 남지 않았다


class FollowUpS2afix2DocsTest(unittest.TestCase):
    """S2a 두 번째 독립 검증의 지적(N1–N7)을 S2AFIX2 가 고쳤다는 기록이 문서에 있다 — 측정과 어긋나는 문구가 남지 않았고, S2b 에 넘길 것 넷·품질 개선 후보·평평한 Kp 한계·낱말 목록의 한계가 적혀 있다."""

    def test_14_7_names_the_four_things_for_s2b(self):
        part = SECTION[SECTION.index("### 14-7."):SECTION.index("### 14-8.")]
        for needle in ("S2b 가 연결하기 전에 정해야 하는 것 넷", "QG7-REUSE", "6/6 보류", "`flares_weekly`·`scales_weekly`", "굶는 글감", "폴백 없음", "53주 해(2009·2015·2020·2026·2032·2037)", "1,619주 중 6번",
                       "홀수 주 월요일"):
            self.assertIn(needle, part)
        self.assertEqual(len(re.findall(r"(?m)^\d\. \*\*", part)), 4)

    def test_14_8_says_what_the_second_verification_found(self):
        limits = SECTION[SECTION.index("### 14-8."):]
        for needle in ("평평한 Kp 에 빠진 날이 있으면 글이 나지 않는다", "NO_ANALYSIS", "입력 500건 중 15건", "공공영역 표지의 낱말 목록은 완전하지 않다", "`저작권 걱정 없이 쓸 수 있습니다`", "병합 점검(S2AFIX2 N1)",
                       "facts.field_of", "품질 개선 후보(운영자 결정·후속 묶음)", "한 번 쓰는 '지표 설명' 페이지", "충분히 채운다고 말할 수 없다", "S2AFIX2 N7", "확인 요청 008"):
            self.assertIn(needle, limits)
        self.assertNotIn("위험은 줄었지만", DOC)                                                 # N5 ①: 측정과 어긋나는 문구는 남지 않았다
        self.assertIn("개선 여부는 이 측정으로 알 수 없다", limits)
        self.assertIn("(65–85%)", limits)

    def test_14_3_describes_the_calculation_words_of_the_common_notice(self):
        part = SECTION[SECTION.index("### 14-3."):SECTION.index("### 14-4.")]
        for needle in ("공통 안내 두 곳", "Recipe.calc_from_formulas", "CALC_WORDS", "S2AFIX2 N5", "하루 최대값·평균·평균과의 차이·최고값·최저값·개수", "옛 고정 문장으로 돌아간다", "기존 틀 R01–R03 은 고정 문장 그대로"):
            self.assertIn(needle, part)

    def test_the_register_corrects_the_numbers_and_the_status_that_gave_too_much_credit(self):
        rows = {number: next(line for line in REGISTER.splitlines() if line.startswith(f"| **{number}** |")) for number in ("D-216", "D-217", "D-218", "D-219")}
        self.assertIn("남은 이상 42건", rows["D-216"])
        self.assertNotIn("44건", rows["D-216"])
        status = [cell.strip() for cell in rows["D-218"].strip().strip("|").split("|")][4]
        self.assertTrue(status.startswith("**부분 해결**"), status)                              # 글이 얇다는 위험은 해결이 아니다
        self.assertNotIn("**해결**", status)
        for number in ("D-217", "D-218", "D-219"):
            self.assertIn("S2AFIX2", rows[number], number)
        for needle in ("정렬", "§14-7"):
            self.assertIn(needle, rows["D-217"])
        for needle in ("NO_ANALYSIS", "입력 500건 중 15건", "충분히 채운다고 말할 수 없다", "FACT_PATH.md"):
            self.assertIn(needle, rows["D-218"])
        for needle in ("field_of", "저작권 보호 대상이 아니다", "연방정부의 저작물"):
            self.assertIn(needle, rows["D-219"])


class AssemblerNamesTest(unittest.TestCase):
    def test_the_new_public_names_of_the_assembler_exist(self):
        for name in ("attribution_line", "attribution_required", "attribution_scope_problem", "claims_public_domain", "date_numbers", "ALWAYS_ALLOWED_LATIN", "PUBLIC_DOMAIN_CLAIM_WORDS"):
            self.assertTrue(hasattr(A, name), name)
        self.assertEqual(A.ALWAYS_ALLOWED_LATIN, frozenset({"UTC"}))
        self.assertTrue(hasattr(R, "title_template_problem") and hasattr(R, "TITLE_POLICY_R01"))


if __name__ == "__main__":
    unittest.main()
