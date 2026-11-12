"""병합완료 확인(`kind: merged`, 운영자 요청 2026-11-12)의 문서가 코드와 어긋나지 않는지 — 요청함 README 의 예시는 새 읽기 규칙을 그대로 통과하고 문서에 실린 폰 글은 notify.format_merged 의 출력과 글자 그대로 같으며,
사용법·사전·구조·보안·절차서·도구 안내와 결함 레지스터가 같은 말을 한다. 알림 워크플로(`ai-request.yml`)는 이 변경의 범위 밖이고(한 줄도 바꾸지 않는다) 경로 필터가 없어 새 파일 이름도 걸러지지 않는다는 것을 읽어서 확인한다.
네트워크 없이 파일만 읽는다.
"""
import re
import unittest

import _bootstrap
from merged_helpers import merge_text, merged_name, merged_text, req_errors
from pipeline import notify
from pipeline import operator_loop as ol

ROOT = _bootstrap.ROOT


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def code_blocks(text, language):
    return re.findall(r"```" + re.escape(language) + r"\n(.*?)```", text, re.S)


def table_row(text, first_cell):
    for line in text.splitlines():
        if line.startswith(f"| {first_cell} |"):
            return line
    raise AssertionError(f"`{first_cell}` 로 시작하는 표의 줄이 없다")


class FolderReadmeTest(unittest.TestCase):
    def setUp(self):
        self.readme = read(ol.REQUEST_DIR + "/README.md")

    def test_the_key_table_has_the_result_key_and_the_kind_row_lists_the_new_kind(self):
        self.assertIn("`merged`(병합완료 확인)", table_row(self.readme, "`kind`"))
        row = table_row(self.readme, "`result`")
        self.assertIn("병합완료 확인 필수", row)
        for needle in ("`정상`", "`이상`", "일곱 개"):
            self.assertIn(needle, row, needle)
        self.assertIn("`merged`=확인하는 병합 부탁의 M 번호", table_row(self.readme, "`no`"))

    def test_the_section_explains_the_rules_the_code_enforces(self):
        section = self.readme[self.readme.index("## 병합완료 확인(`merged`) 쓰는 법"):self.readme.index("## 병합 부탁(`merge`) 쓰는 법")]
        for needle in ("확인하는 병합 부탁의 `M` 번호", "하나뿐", "일곱 개뿐", "`urgency`", "`pr`", "`work`", "`[M050] 병합완료 확인 - 정상`", "60자", "100자", "제목 한 줄뿐", "요청 열기",
                       "`P###`", "`next_notice_no.py`", "make_merged_notice.py", "`bad_kind`", "경로 필터 없이", "옛 방식(`info`)", "`[M049] 병합완료`", "강제 푸시·되돌림 금지"):
            self.assertIn(needle, section, needle)
        self.assertEqual(notify.MERGED_SUMMARY_LIMITS, {"정상": 60, "이상": 100})
        self.assertNotIn("~", section)
        self.assertNotRegex(section, r"https?://")

    def test_the_section_carries_the_round_two_corrections_of_the_independent_check(self):
        """독립 검증(MDONEV 2026-11-12)이 짚은 안내의 빈틈 — D3 다시 보내는 길·D4 따로 push·D9 앞뒤 공백·D10 사유 글·D1 고정 문구·D2 도구 기본 검증·정직 문장."""
        section = self.readme[self.readme.index("## 병합완료 확인(`merged`) 쓰는 법"):self.readme.index("## 병합 부탁(`merge`) 쓰는 법")]
        for needle in ("다른 알림(`info`)", "새로 *더해진* 파일만", "따로 push", "3통", "`… 외 N건`", "앞뒤 공백(NBSP 포함)", "도메인·전화번호·`#해시태그`·`/명령`·광고 번호 모양", "`병합완료 확인` 글자를 쓸 수 없고",
                       "`--no-verify` 는 시험 전용", "`요청 가지에 main 을 합치기 전입니다 — 먼저 합치세요`", "`--verify-with <코드 폴더>`", "직접 확인한 결과를 적는 값", "병합 결과를 검사하지 않습니다"):
            self.assertIn(needle, section, needle)
        self.assertNotIn("그 파일을 고칩니다", self.readme)                                                       # D3: '다시 보내야 하면 그 파일을 고친다' 는 틀린 안내였다
        self.assertIn(notify.format_merged_unreadable("R-266"), section)                                         # 문서의 고정 문구는 코드가 보내는 글 그대로(D1)
        self.assertIn("옛 모양이 아니라 요청 번호만 든 고정 문구 한 줄로 보냅니다", self.readme)                              # 위쪽 '런타임은 새 칸이 틀려도…' 문단도 병합완료 확인만 예외임을 적는다

    def test_the_example_is_a_valid_merged_file_and_pairs_with_the_merge_example(self):
        blocks = code_blocks(self.readme, "markdown-merged")
        self.assertEqual(len(blocks), 1)
        example = blocks[0]
        request = ol.parse_request("R-173_merged-m007.md", example, strict=True)
        self.assertEqual((request.id, request.kind, request.no, request.notice_error, dict(request.fields)), ("R-173", "merged", "M007", "", {"result": "정상", "summary": "정상"}))
        self.assertEqual(request.title, notify.merged_title("M007", "정상"))
        merge_example = next(block for block in code_blocks(self.readme, "markdown") if "\nno: M007\n" in block)         # README 의 병합 요청 예시(파일 R-171_merge-p2b.md)와 짝이 맞는다
        found = req_errors({"R-171_merge-p2b.md": merge_example, "R-173_merged-m007.md": example})
        self.assertEqual([f.line() for f in found], [])
        self.assertEqual(len(example.strip().splitlines()[-1].splitlines()), 1)                                      # 본문은 한 줄

    def test_the_phone_text_in_the_readme_is_what_the_code_sends(self):
        text = notify.format_merged("M007", {"result": "정상", "summary": "정상"})
        self.assertEqual(text, "[M007] 병합완료 확인 - 정상")
        self.assertIn(text + "\n", code_blocks(self.readme, "text"))

    def test_the_examples_the_other_tests_pin_are_untouched(self):
        examples = [block for block in code_blocks(self.readme, "markdown") if block.startswith("---\n")]
        kinds = [ol.parse_request(re.search(r"^id: (R-[0-9]{3})$", block, re.M).group(1) + "_x.md", block, strict=True).kind for block in examples]
        self.assertGreaterEqual(len(kinds), 4)
        self.assertNotIn("merged", kinds)                                                                           # 병합완료 확인 예시는 따로 표시한 상자(markdown-merged)에만 있다


class OperatorGuideTest(unittest.TestCase):
    def setUp(self):
        self.guide = read(ol.GUIDE_PATH)

    def test_the_guide_shows_the_one_line_the_operator_gets_and_says_what_to_do(self):
        text = notify.format_merged("M007", {"result": "정상", "summary": "정상"})
        self.assertIn(text + "\n", code_blocks(self.guide, "text"))
        for needle in ("**병합 확인 알림 (2026-11-12 부터)**", "한 줄", "하실 일이 없습니다", "요청 열기", "진행 현황 번호", "`[M007] 병합완료 확인 - 이상`", "답하지 않아도 됩니다"):
            self.assertIn(needle, self.guide, needle)

    def test_the_operator_texts_say_the_one_line_comes_only_after_the_request_branch_took_main(self):
        """D7(독립 검증): '2026-11-12 부터 한 줄' 은 요청 전용 가지가 이 기능이 병합된 main 을 합친 뒤부터다 — 그 전에는 예전 진행 현황 알림으로 온다고 운영자 글에도 적는다."""
        for needle in ("**뒤부터** 이 한 줄로 옵니다", "예전처럼 `P###` 번호가 붙은 진행 현황 알림으로 올 수 있습니다"):
            self.assertIn(needle, self.guide, needle)
        merge_guide = read("인수인계/PR_병합_방법.md")
        for needle in ("요청 전용 가지가 이 기능이 병합된 `main` 을 합친 뒤부터", "예전처럼 `병합완료` 진행 알림으로 올 수 있습니다"):
            self.assertIn(needle, merge_guide, needle)

    def test_the_guide_tells_the_operator_what_the_fixed_warning_line_means(self):
        """D1: 칸이 틀린 파일은 고정 문구가 간다 — 운영자 글에 그 글(앞부분)과 '이 알림으로 병합 결과를 판단하지 말 것' 이 있다."""
        head = notify.format_merged_unreadable("R-266").split("(요청")[0]
        self.assertIn(head, self.guide)
        self.assertIn("이 알림으로 병합 결과를 판단하지 말고", self.guide)

    def test_the_old_shape_kind_table_lists_the_new_kind_last(self):
        row = table_row(self.guide, "병합완료 확인")
        self.assertIn("`정상`·`이상`", row)
        self.assertEqual(notify.REQUEST_KIND_LABELS["merged"], "병합완료 확인")


class OtherDocsTest(unittest.TestCase):
    def test_the_glossary_defines_the_kind_and_says_it_takes_no_new_number(self):
        glossary = read("docs/GLOSSARY.md")
        row = table_row(glossary, "병합완료 확인")
        for needle in ("`kind: merged`", "`정상`·`이상`", "`[M007] 병합완료 확인 - 정상`", "진행 현황 번호", "`M` 번호", "같은 번호의 병합 부탁"):
            self.assertIn(needle, row, needle)
        self.assertIn("`merged` 병합완료 확인", glossary)
        self.assertIn("병합완료 확인(`merged`)은 새 번호를 쓰지 않고", table_row(glossary, "알림 번호"))

    def test_the_architecture_section_names_the_pieces(self):
        architecture = read("docs/ARCHITECTURE.md")
        section = architecture[architecture.index("## 4-6-2."):architecture.index("## 4-7.")]
        row = next(line for line in section.splitlines() if line.startswith("| 병합완료 확인("))
        for needle in ("`kind: merged`", "`MERGED_ALLOWED`", "`notify.merged_title`", "`_merged_problem`", "`format_merged`", "`request_buttons`", "`merged_pairing_problems`", "일곱 개", "정상 60자·이상 100자",
                       "짝을 확인하지 않고", "바이트까지 같다", "D-310", "D-310–D-319", "`format_merged_unreadable`", "고정 문구", "`merged_summary_label`", "(D-319)"):
            self.assertIn(needle, row, needle)

    def test_the_security_row_the_runbook_and_the_tool_guide_say_the_same(self):
        security = read("docs/SECURITY_GUARDRAILS.md")
        row = next(line for line in security.splitlines() if line.startswith("| REQ-1 |"))
        for needle in ("`kind: merged`", "`result`", "같은 번호의 `kind: merge` 요청 파일", "하나뿐", "`merged_summary_label`"):
            self.assertIn(needle, row, needle)
        runbook = read("docs/AGENT_RUNBOOK.md")
        for needle in ("**병합완료 확인 알림**", "`kind: merged`", "진행 현황 번호(`P###`)는 먹지 않습니다", "make_merged_notice.py", "옛 방식(`info`)",
                       "`--no-verify` 는 시험 전용", "**다른 요청과 따로 push**", "병합 결과를 검사하지 않으며", "다른 알림(`info`)으로 보냅니다"):
            self.assertIn(needle, runbook, needle)
        tools = read("인수인계/도구/README.md")
        for needle in ("**병합완료 확인(`kind: merged`", "make_merged_notice.py", "`make_request.py`·`notice_tools.py` 는 `kind: merged` 를 거절", "`next_notice_no.py` 는 그 파일의 `no` 를 세지 않는다",
                       "`요청 가지에 main 을 합치기 전입니다 — 먼저 합치세요`", "`--verify-with <코드 폴더>`", "`--no-verify` 는 시험 전용", "따로 push", "다른 알림(`info`)으로 보낸다", "병합 결과를 검사하지 않는다"):
            self.assertIn(needle, tools, needle)

    def test_the_defect_register_records_the_decisions_in_its_own_range(self):
        register = read("docs/DEFECT_REGISTER.md")
        self.assertIn("> D-310–D-319 는 2026-11-12 에 추가했다", register)
        rows = {int(match.group(1)): line for line in register.splitlines() for match in [re.match(r"\| \*\*D-(3[1][0-9])\*\* \|", line)] if match}
        self.assertLessEqual(set(range(310, 320)), set(rows))                                                    # 라운드 2 결정은 D-319 한 행(D-310–D-319 범위 안에서만)
        self.assertEqual(max(rows), 319)
        for number, line in rows.items():
            self.assertTrue("병합완료 확인" in line or "merged" in line, number)
            self.assertEqual(len(re.findall(r"\|", line)) - len(re.findall(r"\\\|", line)), 7, f"D-{number}: 표의 칸이 여섯이어야 한다")
        for needle in ("독립 검증", "고정 문구", "`merged_title`", "`--no-verify`", "다른 알림(`info`)", "따로 push", "notify.notify_merged", "`merged_summary_label`", "D8", "불변식"):
            self.assertIn(needle, rows[319], needle)
        self.assertNotIn("옛 모양(제목·요약)으로 폴백해 알림을 잃지 않는다", rows[316])                                  # D-316 의 낡은 문장을 고쳤다
        self.assertIn("(D-319", rows[316])


class WorkflowIsUntouchedTest(unittest.TestCase):
    """알림 워크플로는 이 변경의 범위 밖이다 — 읽어서 확인만 한다: push 트리거가 `ai/claude/**` 가지 하나뿐이고 파일 경로 필터가 없어 새 요청 파일 이름도 걸러지지 않는다."""

    def test_the_request_workflow_triggers_on_branches_only_with_no_path_filter(self):
        text = read(".github/workflows/ai-request.yml")
        trigger = text[text.index("\non:\n"):text.index("\npermissions:")]
        self.assertEqual(trigger.strip().splitlines(), ["on:", "  push:", "    branches:", "      - 'ai/claude/**'"])
        self.assertNotRegex(trigger, r"(?m)^\s*paths(?:-ignore)?\s*:")
        self.assertIn("run: python -m pipeline.operator_loop requests", text)

    def test_the_new_file_names_are_request_file_names(self):
        for no in ("M001", "M050", "M999", "M1000", "M9999"):
            name = f"R-266_merged-{no.lower()}.md"
            self.assertIsNotNone(ol.REQUEST_NAME_RE.fullmatch(name), name)
            self.assertLessEqual(len(name.split("_", 1)[1]) - 3, ol.SLUG_MAX)
            self.assertEqual(merged_name(266, no), name)
        self.assertEqual(ol.parse_request(merged_name(), merged_text(), strict=True).kind, "merged")
        self.assertEqual(ol.parse_request("R-264_merge-m050.md", merge_text(), strict=True).kind, "merge")


if __name__ == "__main__":
    unittest.main()
