"""S2C0 묶음의 문서 시험 — `docs/S2C_PLAN.md`(S2c 설계 요약)·`docs/FACT_PATH.md` §16·결함 레지스터 D-332–D-337 이 코드의 실제 이름·값과 어긋나지 않고 문서 규칙(물결표·http 링크·Liquid·로컬 경로·광고 번호·실제 이름 없음)을 지킨다.
네트워크 없이 파일만 읽는다. 다른 가지의 결정 번호·전체 최댓값은 못박지 않는다 — 이 묶음의 행이 있고 서로 이어지는지만 본다."""
import re
import unittest

import _bootstrap
import hold_helpers as HH
import test_fact_hold as TH

from pipeline import fact_candidates as K
from pipeline import fact_supply as S
from pipeline import shadow_run

ROOT = _bootstrap.ROOT
PLAN = (ROOT / "docs" / "S2C_PLAN.md").read_bytes()
PLAN_TEXT = PLAN.decode("utf-8").replace(chr(13) + chr(10), chr(10))           # 줄 끝은 맞춰서 읽는다(윈도 자동 줄바꿈 변환으로 CRLF 가 된 작업 사본에서도 같다)
DOC = (ROOT / "docs" / "FACT_PATH.md").read_text(encoding="utf-8")
REGISTER = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
SECTION = DOC[DOC.index("## 16. S2c-0"):]
NUMBERS = ("D-332", "D-333", "D-334", "D-335", "D-336", "D-337")
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


class PlanDocumentTest(unittest.TestCase):
    def test_the_summary_is_about_ten_to_fourteen_kilobytes_and_follows_the_document_rules(self):
        size = len(PLAN_TEXT.encode("utf-8"))
        self.assertGreaterEqual(size, 10_000)
        self.assertLessEqual(size, 14_500)
        assert_doc_rules(self, PLAN_TEXT, "S2C_PLAN.md")
        for relative in re.findall(r"\]\((\./[^)]+)\)", PLAN_TEXT):
            self.assertTrue((ROOT / "docs" / relative).exists(), relative)

    def test_it_says_it_is_not_an_approval_and_what_it_does_not_change(self):
        for needle in ("**승인이 아니다.**", "답이 아직 없으면 **기본값으로 진행**", "켜는 값 변경·발행 정지 변수·광고 표면·새 공개 페이지·제공처 추가는 운영자 승인이 따로 필요하며 S2c-0 은 그 어느 것도 바꾸지 않는다",
                       "새 사실을 더하지 않았다", "**켜는 값 변경 없음**"):
            self.assertIn(needle, PLAN_TEXT, needle)

    def test_the_numbers_are_the_design_documents(self):
        """설계안(작업 폴더의 plan.md)의 숫자를 그대로 옮겼다 — 같은 값이 문서 안에서 서로 어긋나지 않게 못박는다(원문 대조는 검증자의 일)."""
        for needle in ("**65–84%**", "26–30개", "**숫자 칸이 하나도 없는 고정 문장이 11–16개**", "**글자 그대로 같은 문장이 60–68%**", "**88–99.8%**", "서로 다른 문장 틀은 29–46개뿐", "받은 날짜 4번", "3–4번", "1–2번",
                       "**19편(79%)이 가장 얇은 주간 글감 넷**", "일별 3·월별 2", "75%", "월별 66 → 약 62%", "276개월", "358개월", "하루 8·월 100", "±4점 안팎", "문장 틀 56–62%", "최근 13개월 전부", "(월별 글의 새 맥락 계산 1 → 4–5개)"):
            self.assertIn(needle, PLAN_TEXT, needle)
        diagnosis = {cells_[0]: cells_[2:] for cells_ in table_rows(PLAN_TEXT[PLAN_TEXT.index("| 글감 | 틀 |"):PLAN_TEXT.index("같은 글감의 이어진 글 사이")])[1:]}
        self.assertEqual(diagnosis, {"일별 Kp 최대값": ["1,478", "76%", "28", "15 (54%)"], "Kp 폭풍 기준 이상 날·구간": ["1,576", "78%", "29", "11 (38%)"], "X선 플레어 등급별 건수": ["1,206", "84%", "26", "16 (62%)"],
                                     "우주기상 등급 현황과 예보": ["1,500", "83%", "30", "16 (53%)"], "일별 흑점수": ["1,616", "65%", "30", "15 (50%)"], "월별 흑점수": ["1,747", "66%", "28", "15 (54%)"]})
        repeats = {cells_[0]: cells_[1:] for cells_ in table_rows(PLAN_TEXT[PLAN_TEXT.index("| 글감과 입력 | 글 수 |"):PLAN_TEXT.index("월별 값은 일별 파일의 달 평균과")])[1:]}
        self.assertEqual(repeats, {"일별 흑점수(실제, 52주)": ["52", "60.3%", "92.2%", "45"], "월별 흑점수(실제 일별 평균, 36개월)": ["36", "63.9%", "95.8%", "34"], "Kp 일별 최대값(가상, 100주)": ["100", "63.6%", "88.3%", "46"],
                                   "Kp 폭풍 기준(가상, 100주)": ["100", "64.7%", "96.9%", "35"], "플레어(가상, 100주)": ["100", "68.1%", "99.8%", "29"], "등급 현황(가상, 100주)": ["100", "61.6%", "97.7%", "34"]})

    def test_the_twelve_week_numbers_in_the_text_are_what_the_code_computes(self):
        """문서의 79% → 75% 는 코드가 실제로 내는 값이다 — 시험(`test_fact_hold`)과 같은 12주 모의를 다시 돌려 문서의 숫자와 견준다."""
        with HH.policy_off():
            old = TH.twelve_week_picks()
        new = TH.twelve_week_picks()
        thin = ("kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly")
        self.assertEqual((len(old), sum(1 for _d, n in old if n in thin), len(new), sum(1 for _d, n in new if n in thin)), (24, 19, 24, 18))
        self.assertIn("처음 12주 글 24편 중 **19편(79%)이 가장 얇은 주간 글감 넷**", PLAN_TEXT)
        self.assertIn("가장 얇은 둘(등급·Kp 폭풍)을 빼도 75%", PLAN_TEXT)

    def test_the_selection_the_step_table_and_the_five_decisions_are_all_there(self):
        for number in "①②③④⑤⑥⑦":
            self.assertIn(f"| {number} |", PLAN_TEXT)
        steps = [cells_[0].strip("*").split(" ")[0] for cells_ in table_rows(PLAN_TEXT[PLAN_TEXT.index("| 단계 | 내용 | 크기 | 승인 |"):PLAN_TEXT.index("모든 단계 공통")])[1:]]
        self.assertEqual(steps, [f"S2c-{number}" for number in range(8)])
        for needle in ("**재개 전에 무엇을 먼저?**", "**얇은 주간 글감(Kp 두 가지·플레어·등급)**", "**주간 정리 한 편으로 묶기**", "**'지표 설명' 고정 페이지**", "**글마다 다른 차트**"):
            self.assertIn(needle, PLAN_TEXT, needle)
        self.assertEqual(len(re.findall(r"(?m)^\d\. \*\*", PLAN_TEXT[PLAN_TEXT.index("## 6."):PLAN_TEXT.index("## 7.")])), 5)
        self.assertEqual(len(re.findall(r"(?m)^- ", PLAN_TEXT[PLAN_TEXT.index("## 7."):PLAN_TEXT.index("## 8.")])), 14)       # 하지 말아야 할 것 열네 가지

    def test_the_summary_does_not_name_the_things_the_repository_must_not_name(self):
        self.assertNotIn("C:/", PLAN_TEXT)
        self.assertNotIn("plan.md", PLAN_TEXT)
        self.assertNotRegex(PLAN_TEXT, r"(?i)adsense")


class FactPathSectionTest(unittest.TestCase):
    def test_the_section_follows_the_document_rules_and_is_the_last_one_ending_with_the_pointer(self):
        assert_doc_rules(self, SECTION, "FACT_PATH §16")
        self.assertEqual(len(re.findall(r"(?m)^## ", SECTION)), 1)
        self.assertTrue(DOC.rstrip().endswith("설계 요약: [`S2C_PLAN.md`](./S2C_PLAN.md)"))
        for heading in ("### 16-1. 한눈에", "### 16-2. a —", "### 16-3. b —", "### 16-4. c —", "### 16-5. d —", "### 16-6. 시험"):
            self.assertIn(heading, SECTION, heading)
        for relative in re.findall(r"\]\((\./[^)]+)\)", SECTION):
            self.assertTrue((ROOT / "docs" / relative).exists(), relative)

    def test_the_names_and_values_the_section_states_are_the_codes(self):
        for name in ("HELD_SPEC_IDS", "FIRST_SPEC_IDS", "RawRecorder", "raw_index.json", "product_id_of_url", "SupplyResult.notes", "fact_notes", "ShadowViolation", "OPENER_FAILED", "not_stored"):
            self.assertIn(name, SECTION, name)
        self.assertTrue(hasattr(K, "HELD_SPEC_IDS") and hasattr(K, "FIRST_SPEC_IDS") and hasattr(shadow_run, "RawRecorder") and hasattr(S, "product_id_of_url"))
        self.assertIn('HELD_SPEC_IDS = ("scales_weekly", "kp_storm_weekly")', SECTION)
        self.assertEqual(HH.PRODUCTION_HELD, ("scales_weekly", "kp_storm_weekly"))
        self.assertIn('FIRST_SPEC_IDS = ("sunspot_monthly_monthly",)', SECTION)
        self.assertEqual(HH.PRODUCTION_FIRST, ("sunspot_monthly_monthly",))
        self.assertEqual(shadow_run.RAW_MAX_TOTAL_BYTES, 2 * 1024 * 1024)
        self.assertIn("총 크기 상한 2 MiB", SECTION)
        self.assertIn("478,190바이트", SECTION)
        self.assertEqual(shadow_run.RAW_INDEX_FILE, "raw_index.json")
        self.assertEqual(shadow_run.RAW_PREFIX, "raw_")
        for needle in ("24편 중 19편(79%)", "24편 중 18편(75%,", "Kp 일별 9·플레어 9·일별 흑점수 3·월별 3", "12월 11일", "(9,907행", "행 9907"):
            self.assertIn(needle, SECTION, needle)

    def test_the_files_the_section_names_exist(self):
        for relative in re.findall(r"`(tests/[A-Za-z0-9_]+\.py)`", SECTION):
            self.assertTrue((ROOT / relative).is_file(), relative)
        for relative in ("tests/test_fact_hold.py", "tests/hold_helpers.py", "tests/test_fact_today_row.py", "tests/test_shadow_raw.py", "tests/test_s2c0_docs.py", "tests/test_space_adapter.py", "docs/S2C_PLAN.md"):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_the_old_sentence_about_the_whole_product_being_refused_is_replaced_and_the_pinned_words_stay(self):
        limits = DOC[DOC.index("### 14-8."):DOC.index("## 15. S2b")]
        self.assertNotIn("그 제품 전체를 `BAD_SHAPE` 로 거절한다(안전하지만 그 행만 건너뛰는 편이 더 견고하다)", limits)
        for needle in ("수집 시각의 한계", "S2AFIX D11", "S2C0-b D-333", "00:30 UTC", "여전히 제품 전체를 거절한다"):
            self.assertIn(needle, limits, needle)
        self.assertIn("§16-2", DOC[DOC.index("**선택 정책 `select_candidates`**"):DOC.index("### 15-4.")])
        self.assertIn("S2C0-c, §16-4", DOC[DOC.index("### 15-7."):DOC.index("### 15-8.")])


class RegisterRowsTest(unittest.TestCase):
    STATES = {"D-332": "**완화**", "D-333": "**해결**", "D-334": "**해결**", "D-335": "**해결**", "D-336": "**열림**", "D-337": "**열림**"}
    SEVERITY = {"D-332": "낮음", "D-333": "낮음", "D-334": "낮음", "D-335": "정보", "D-336": "정보", "D-337": "정보"}
    POINTERS = {"D-332": "§16-2", "D-333": "§16-3", "D-334": "§16-4", "D-335": "`docs/S2C_PLAN.md`", "D-336": "§16-2", "D-337": "§16-4"}

    def test_the_six_rows_exist_once_each_in_order_after_d331_with_six_cells_and_the_right_marks(self):
        found = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", REGISTER)
        positions = [found.index(number) for number in ("D-331",) + NUMBERS]
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
        expected = {"D-332": ("79%", "75%", "HELD_SPEC_IDS", "FIRST_SPEC_IDS", "빈 튜플", "골든 600장면"), "D-333": ("BAD_SHAPE", "9,907행", "내일(다음 달) 이후 행", "SupplyResult.notes", "무작위 600입력"),
                    "D-334": ("raw_index.json", "하위 폴더", "result.json", "2 MiB", "notes"), "D-335": ("docs/S2C_PLAN.md", "80KB", "새 사실 없음"),
                    "D-336": ("kp_storm_weekly", "폴백", "상수를 비우면 복구"), "D-337": ("그림자 실행", "14일", "NEVER")}
        for number, needles in expected.items():
            for needle in needles:
                self.assertIn(needle, register_row(number), (number, needle))

    def test_the_section_names_the_same_numbers(self):
        self.assertIn("결정·결함은 D-332–D-337", SECTION)
        for number in NUMBERS[:4]:
            self.assertIn(number, SECTION, number)
        self.assertIn("D-336", SECTION)
        self.assertIn("D-337", SECTION)


if __name__ == "__main__":
    unittest.main()
