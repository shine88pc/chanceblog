"""병합 알림 자동화의 문서 시험 — 규칙 표(G-A13·G-A14·WF-16)·실행 안내서 표·구조 절(§4-6-4)·운영자 안내(사용법 8.)·결함 레지스터가 코드·워크플로와 같은 말을 하는지 본다(표류 방지).

네트워크 없이 파일만 읽는다. 코드의 상수(문장 규칙·상한·켬 상태 값)와 문서의 숫자·문장이 어긋나면 이 시험이 빨개진다.
"""
import re
import sys
import unittest

import yaml

import _bootstrap
from pipeline import auto_notice as an

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

TILDE = chr(0x7E)                                                       # 새 글에 ASCII 물결표가 없는지 보는 시험이라 글자 대신 코드 포인트로 쓴다
READY, CONFIRM = ".github/workflows/merge-ready-notice.yml", ".github/workflows/merge-confirm-notice.yml"
READY_NAME, CONFIRM_NAME = "[공통] 병합 부탁 알림 자동 보내기", "[공통] 병합완료 확인 알림 자동 보내기"


def doc(rel):
    return (ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def row(text, prefix):
    return next(line for line in text.splitlines() if line.startswith(prefix))


def section(text, heading, next_heading_prefix="\n## "):
    start = text.index(heading)
    end = text.find(next_heading_prefix, start + len(heading))
    return text[start:end] if end >= 0 else text[start:]


class SecurityRulesTest(unittest.TestCase):
    def setUp(self):
        self.text = doc("docs/SECURITY_GUARDRAILS.md")

    def test_the_rows_exist_in_order_with_three_cells(self):
        positions = [self.text.index(f"\n| {name} |") for name in ("G-A12", "G-A13", "G-A14")]
        self.assertEqual(positions, sorted(positions))
        for name in ("G-A13", "G-A14", "WF-16"):
            self.assertEqual(row(self.text, f"| {name} |").count("|"), 4, name)               # 칸 수가 어긋나면 표가 깨진다(칸 안의 세로선은 쓰지 않는다)
        self.assertLess(self.text.index("\n| WF-15 |"), self.text.index("\n| WF-16 |"))

    def test_g_a13_states_the_workflow_run_policy(self):
        text = row(self.text, "| G-A13 |")
        for needle in ("workflow_run", "허용 목록", "merge-ready-notice.yml", "merge-confirm-notice.yml", "WORKFLOW_RUN_ALLOWED", "기본 가지에 있는 파일 그대로", "시크릿을 쥔 채", "head_branch", "head_commit.message",
                       "display_title", "가지(PR 머리)의 코드는 내려받지도 실행하지도 않는다", "persist-credentials: false", "`actions/checkout`·`actions/setup-python`", "달러 기호와 이중 중괄호", "env.X", "steps.*.outputs",
                       "맨 끝 발송 단계의 env 에만", "T3", "WF-16", "WF-13", "tests/test_workflow_run_rule.py", "쓰기 0", "pull_request_target", "issue_comment", "schedule", "workflow_dispatch", "BA-S1-4", "탐침 D"):
            self.assertIn(needle, text, needle)

    def test_g_a14_states_the_notice_rules_the_states_the_trust_boundary_and_the_limits(self):
        text = row(self.text, "| G-A14 |")
        for needle in ("`merge-ready-notice.yml`", "`merge-confirm-notice.yml`", "pipeline/auto_notice.py", "병합·승인·쓰기를 하지 않고", "`off` 인 채로 병합된다", "확인 031 의 보기 2", "총괄 결정",
                       "pipeline/auto_notice.json", '{"mode": "off"}', "`off`(기본", "`dry`(모든 계산을 하고 보낼 문장을 실행 요약에만", "`on`(발송)", "값이 이상하면 off", "별도 병합 부탁(T3)",
                       "[M###] 병합 부탁 — ", "80자", "5줄×120자", "`검사: 초록`", "800자 안", "20초 간격으로 세 번", "[M###] 병합완료 확인 - 정상", "`- 이상`", "100자 안", "부모 수", "트리 일치", "트리 비교를 빼고",
                       "변경 파일 수·이름 집합", "main 커밋의 가드레일 결론", "취소·건너뜀이면 판정을 미룬다", "env 로만 받고 파이썬이 모양을 거른다", "제목에 걸리면 보내지 않고 본문 줄에 걸리면 그 줄만 뺀다",
                       "고정 문장·번호·정수만", "dry 의 보낼 문장은 거른 뒤의 값", "GET", "operator_loop.GitHub", "notify.Notifier", "새 외부 접속·새 의존성·새 시크릿은 없다", "문장을 한 번 더 검사한 뒤 보낸다",
                       "알림이 안 가는 쪽이 이상한 알림이 가는 쪽보다 낫다", "첫 관측 절차", "GitHub 에서 처음 도는 것은 병합 뒤", "가짜 응답으로만 시험했다", "중복", "Re-run", "봇의 글 커밋이 main 검사를 취소",
                       "2MB", "300개", "노란 배너", "데스크톱 앱 저장소용은 만들지 않았다", "텔레그램 시크릿이 없다", "WF-16", "tests/test_merge_notice_workflows.py", "tests/test_auto_notice.py", "tests/test_merge_notice_docs.py"):
            self.assertIn(needle, text, needle)

    def test_the_limits_in_the_rules_are_the_constants_of_the_code(self):
        text = row(self.text, "| G-A14 |") + doc("docs/ARCHITECTURE.md")
        self.assertEqual((an.MESSAGE_LIMIT, an.READY_TITLE_LIMIT, an.POINT_LINES, an.POINT_LIMIT, an.REASON_LIMIT), (800, 80, 5, 120, 100))
        self.assertEqual((an.CHECK_WAIT, an.CHECK_RETRIES, an.FILES_CAP), (20, 3, 300))
        self.assertIn(f"{an.MESSAGE_LIMIT}자 안", text)
        self.assertIn(f"{an.POINT_LINES}줄×{an.POINT_LIMIT}자", text)
        self.assertIn(f"{an.CHECK_WAIT}초 간격으로 세 번", text)

    def test_wf16_row_lists_the_checks_and_the_limits(self):
        text = row(self.text, "| WF-16 |")
        for needle in ("on: workflow_run", "허용 목록", "WORKFLOW_RUN_ALLOWED", "merge-ready-notice.yml", "merge-confirm-notice.yml", "types: [completed]", "branches", "`read`", "job 수준 permissions", "env·defaults",
                       "`actions/checkout`·`actions/setup-python`", "persist-credentials: false", "`repository`·`token`", "`run` 과 `with.script`", "env 를 거친 것·steps 출력", "git checkout", "eval", "bash -c", "curl",
                       "단계 위치별", "python -m pipeline.auto_notice merge-ready", "python -m pipeline.auto_notice send", "`secrets.` 가 나오는 모든 글", "한계", "`if:` 식은 막지 않는다", "G-A13", "BA-S1-4", "탐침 D"):
            self.assertIn(needle, text, needle)

    def test_the_approval_list_names_the_new_things_that_need_approval(self):
        section_3 = section(self.text, "## 3. AI 에이전트가 사용자 승인 없이 하면 안 되는 행동", "\n## ")
        bullet = next(line for line in section_3.splitlines() if "workflow_run" in line and "merge-ready-notice.yml" in line)
        for needle in ("새 워크플로에 쓰거나", "merge-ready-notice.yml", "merge-confirm-notice.yml", "쓰기", "체크아웃 `ref`", "시크릿 위치", "pipeline/auto_notice.json", "`dry`·`on`", "WF-16", "G-A13·G-A14"):
            self.assertIn(needle, bullet, needle)

    def test_no_double_braces_or_tildes_were_added_to_the_rules(self):
        self.assertNotIn("{{", self.text)                                                      # front matter 없는 문서의 이중 중괄호는 검증기 경고(LIQUID-1)다
        for name in ("G-A13", "G-A14", "WF-16"):
            line = row(self.text, f"| {name} |")
            self.assertNotIn(TILDE, line, name)
            self.assertNotRegex(line, r"https?://", name)


class RunbookTest(unittest.TestCase):
    def setUp(self):
        self.text = doc("docs/AGENT_RUNBOOK.md")

    def test_both_workflows_are_in_the_table_with_their_real_names_and_triggers(self):
        for rel, name, needles in ((READY, READY_NAME, ("workflow_run", "[공통] 병합 부탁 PR 자동 만들기", "ai/claude/M###-*", "꺼진 채 병합됨", "pipeline/auto_notice.json", "off", "쓰기 권한 0", "J3 9")),
                                   (CONFIRM, CONFIRM_NAME, ("workflow_run", "[공통] 저장소 규칙·테스트 자동 검사", "main", "꺼진 채 병합됨", "off", "쓰기 권한 0", "J3 9"))):
            line = row(self.text, f"| `{rel.rsplit('/', 1)[1]}` |")
            real = yaml.safe_load(doc(rel))["name"]
            self.assertEqual(real, name)
            self.assertIn(f"`{real}`", line)
            for needle in needles:
                self.assertIn(needle, line, needle)
            self.assertEqual(line.count("|"), 5)

    def test_j3_item_9_tells_the_ai_to_keep_sending_request_files_until_on_and_how_to_switch(self):
        item = next(line for line in self.text.splitlines() if line.startswith("9. **병합 알림 자동"))
        for needle in ("꺼진 채 병합됨", "확인 031 의 보기 2", "pipeline/auto_notice.json", "off", "위 5·7 대로 요청 파일로 보내는 것을 그대로 한다", "켜는 순서", "별도 병합 부탁", "T3", "`dry`", "첫 관측",
                       "python scripts/github_status.py runs", "jobs <실행 번호>", "`on`", "요청 파일을 보내지 않는다", "결정·확인·진행 현황은 그대로", "노란 배너로 직접 만들었거나", "자동 PR 실행이 실패했거나",
                       "병합 직후 봇 커밋이 main 검사를 취소한", "시크릿은 맨 끝 발송 단계 env 에만", "G-A13·G-A14", "운영자_요청함_사용법.md"):
            self.assertIn(needle, item, needle)


class ArchitectureTest(unittest.TestCase):
    def setUp(self):
        self.text = doc("docs/ARCHITECTURE.md")
        self.section = section(self.text, "## 4-6-4.")

    def test_the_section_sits_between_4_6_3_and_4_7(self):
        self.assertLess(self.text.index("## 4-6-3."), self.text.index("## 4-6-4."))
        self.assertLess(self.text.index("## 4-6-4."), self.text.index("## 4-7."))
        self.assertTrue(self.section.startswith("## 4-6-4. 병합 알림 자동화"))

    def test_the_section_covers_states_both_notices_trust_boundary_and_limits(self):
        for needle in ("확인 031 의 보기 2", "꺼진 채", "앱 저장소용은 만들지 않았다", "workflow_run", "판정 단계(시크릿 없음)", "발송 단계(텔레그램 시크릿 둘", "send=yes", "`off`(기본·병합 때의 값)", "`dry`", "`on`",
                       "pipeline/auto_notice.json", "값이 셋 밖(대소문자·공백 포함)이면 `off`", "병합된 PR 자신의 확인부터 새 값이 적용된다", "**병합 부탁**(`merge-ready-notice.yml`)", "`skipped`·`neutral` 도 초록이 아님",
                       "**병합완료 확인**(`merge-confirm-notice.yml`)", "부모 수(squash 는 1", "트리 일치", "트리 비교를 빼고", "**신뢰 경계**", "G-A13·G-A14", "WF-16", "기본 가지 `ref`",
                       "GET 만", "operator_loop.GitHub", "notify.Notifier", "**한계**", "첫 관측 전 미확인", "중복은 막지 못한다", "2MB", "300개", "tests/test_auto_notice.py", "tests/test_merge_notice_workflows.py",
                       "tests/test_workflow_run_rule.py", "tests/test_merge_notice_docs.py"):
            self.assertIn(needle, self.section, needle)

    def test_the_fixed_tail_in_the_section_is_the_one_the_code_sends(self):
        self.assertIn(an.ready_tail("M###"), self.section)
        self.assertIn(an.CHECK_LINE, self.section)
        self.assertIn(an.READY_LABEL, self.section)

    def test_the_workflow_table_has_both_rows(self):
        for name, rel in ((READY_NAME, "merge-ready-notice.yml"), (CONFIRM_NAME, "merge-confirm-notice.yml")):
            line = next(line for line in self.text.splitlines() if line.startswith("| (신규) |") and f"`{name}`" in line)
            self.assertIn(f"`{rel}`", line)
            self.assertIn("꺼진 채 병합", line)
            self.assertEqual(line.count("|"), 6)

    def test_the_old_section_4_6_3_is_unchanged_in_its_boundaries(self):
        old = self.text[self.text.index("## 4-6-3."):self.text.index("## 4-6-4.")]
        self.assertIn("병합 부탁 PR 자동 만들기", old)
        self.assertNotIn("merge-ready-notice.yml", old)


class ActionsGuideAndBriefingTest(unittest.TestCase):
    def test_the_names_table_the_chapters_and_the_briefing_rows_exist(self):
        guide, briefing = doc("docs/ACTIONS_GUIDE.md"), doc("docs/REQUEST_BRIEFING.md")
        for name, rel, chapter in ((READY_NAME, "merge-ready-notice.yml", "### 6-20."), (CONFIRM_NAME, "merge-confirm-notice.yml", "### 6-21.")):
            self.assertIn(f"| (없었음) | (없었음) | `{name}` | `{rel}` |", guide)
            text = section(guide, chapter, "\n### ")
            self.assertIn(f"`{name}`", text.splitlines()[0])
            for needle in ("꺼진 채 들어갑니다", "`off`", "`dry`", "`on`", "pipeline/auto_notice.json", "같은 알림이 두 번 올 수 있습니다", "G-A13·G-A14", "§4-6-4"):
                self.assertIn(needle, text, f"{chapter} {needle}")
            line = next(line for line in briefing.splitlines() if line.startswith("| (신규) |") and f"`{name}`" in line)
            self.assertIn(f"`{rel}`", line)
            self.assertEqual(line.count("|"), 6)
        self.assertLess(guide.index("### 6-19."), guide.index("### 6-20."))
        self.assertLess(guide.index("### 6-21."), guide.index("## 7. 알려진 한계와 예정"))

    def test_the_new_chapters_have_no_double_braces_tildes_or_links(self):
        guide = doc("docs/ACTIONS_GUIDE.md")
        text = section(guide, "### 6-20.", "\n## ")
        self.assertNotIn("{{", text)
        self.assertNotIn(TILDE, text)
        self.assertNotRegex(text, r"https?://")


class OperatorGuideTest(unittest.TestCase):
    def setUp(self):
        self.text = doc("인수인계/운영자_요청함_사용법.md")
        self.section = section(self.text, "## 8. 병합 알림 자동화", "\n## ")

    def test_it_is_one_paragraph_at_the_end_and_says_nothing_changes_for_now(self):
        self.assertTrue(self.text.rstrip().endswith(self.section.rstrip()))
        paragraphs = [part for part in self.section.split("\n\n") if part.strip()]
        self.assertEqual(len(paragraphs), 2)                                                    # 제목 줄 하나 + 본문 한 문단
        self.assertTrue(paragraphs[0].startswith("## 8."))
        body = paragraphs[1]
        for needle in (READY_NAME, CONFIRM_NAME, "pipeline/auto_notice.json", "`off`", "운영자가 달라지는 것은 없습니다", "`dry`", "`on`", "운영자 병합이 필요합니다", "제목 맨 앞이 `[M###]` 인 PR 하나만 병합",
                       "알림이 없는 열린 PR 은 아직 병합하지 마세요", "같은 알림이 두 번 올 수 있고", "병합·승인·코멘트를 하지 않고", "G-A14"):
            self.assertIn(needle, body, needle)
        self.assertNotRegex(body, r"https?://")

    def test_the_guide_before_section_8_is_untouched(self):
        self.assertIn("## 7. 알아 둘 것", self.text)
        self.assertLess(self.text.index("## 7. 알아 둘 것"), self.text.index("## 8. 병합 알림 자동화"))


class EngineeringGuideAndRegisterTest(unittest.TestCase):
    def test_the_engineering_rule_row(self):
        line = row(doc("docs/ENGINEERING_GUIDE.md"), "| W13 |")
        for needle in ("workflow_run", "허용 목록", "T3", "권한 읽기뿐", "기본 가지 `ref`", "`actions/checkout`·`actions/setup-python`", "맨 끝 발송 단계 env 에만", "G-A13·G-A14", "**WF-16**"):
            self.assertIn(needle, line, needle)
        self.assertEqual(line.count("|"), 4)

    def test_the_defect_rows_use_only_the_numbers_this_bundle_may_use(self):
        text = doc("docs/DEFECT_REGISTER.md")
        numbers = sorted({int(number) for number in re.findall(r"^\| \*\*D-([0-9]{3})\*\* \|", text, re.M) if int(number) >= 398})
        self.assertEqual(numbers[0], 398)
        self.assertTrue(all(398 <= number <= 405 for number in numbers), numbers)               # 이 묶음의 번호 구간은 D-398–D-405 (D-406 부터는 다른 묶음)
        self.assertEqual(numbers, list(range(398, 398 + len(numbers))))                         # 빠진 번호가 없다
        for number in numbers:
            line = row(text, f"| **D-{number}** |")
            self.assertEqual(line.count("|"), 7, number)
            self.assertIn("**해결**" if number != 399 else "**완화**", line)
        self.assertIn("D-398–D-400 은 2026-11-23 에 추가했다", text)
        self.assertNotIn(TILDE, row(text, "| **D-398** |"))

    def test_the_new_text_names_the_audit_probes_it_answers(self):
        text = doc("docs/DEFECT_REGISTER.md")
        self.assertIn("탐침 D", row(text, "| **D-398** |"))
        self.assertIn("탐침 A·B·C", row(text, "| **D-399** |"))
        self.assertIn("WF-16", row(text, "| **D-400** |"))


class ModuleAndWorkflowTextTest(unittest.TestCase):
    def test_the_module_docstring_states_the_rules_the_tests_hold(self):
        text = an.__doc__
        for needle in ("켬 상태", "off", "dry", "on", "값이 셋 밖이거나 다른 키가 있으면 off", "merge-ready", "merge-confirm", "send", "NOTICE_RUN_ID", "NOTICE_DEFAULT_BRANCH",
                       "가지(PR 머리)의 코드는 내려받지도 실행하지도 않는다", "GET", "operator_loop.GitHub", "평문", "알림이 안 가는 쪽이 이상한 알림이 가는 쪽보다 낫다", "G-A13·G-A14"):
            self.assertIn(needle, text, needle)
        self.assertNotIn(TILDE, text)
        self.assertNotRegex(text, r"https?://")

    def test_the_workflows_point_at_the_same_documents(self):
        for rel in (READY, CONFIRM):
            header = doc(rel).split("\non:\n")[0]
            for needle in ("G-A13·G-A14", "docs/ARCHITECTURE.md §4-6-4", "인수인계/운영자_요청함_사용법.md '8.'", "pipeline/auto_notice.py", "tests/test_merge_notice_workflows.py"):
                self.assertIn(needle, header, f"{rel}: {needle}")

    def test_the_validator_module_docstring_for_the_rule_exists(self):
        self.assertIn("WF-16", vr.check_workflow_run_workflows.__doc__)
        self.assertIn("허용 목록", vr.check_workflow_run_workflows.__doc__)
        self.assertIn("G-A13", vr.check_workflow_run_workflows.__doc__)
        self.assertIn("WF-16", vr._workflow_run_problems.__doc__)


if __name__ == "__main__":
    unittest.main()
