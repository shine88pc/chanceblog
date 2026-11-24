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
                       "발송 job 의 맨 끝 단계 env 에만", "T3", "WF-16", "WF-13", "tests/test_workflow_run_rule.py", "쓰기 0", "pull_request_target", "issue_comment", "schedule", "workflow_dispatch", "BA-S1-4", "탐침 D",
                       "정확히 둘", "`decide`", "`send`", "`needs: decide`", "`if: needs.decide.outputs.send == 'yes'`", "시작도 하지 않으므로 시크릿이 어떤 러너에도 내려가지 않는다", "AN1-S-4",
                       "tests/test_validator_loader.py", "428개(두 파일 × 214가지"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("맨 끝 발송 단계의 env 에만", text)                                   # 옛 구조(단계 하나짜리 job)의 문장이 남지 않았다

    def test_g_a14_states_the_notice_rules_the_states_the_trust_boundary_and_the_limits(self):
        text = row(self.text, "| G-A14 |")
        for needle in ("`merge-ready-notice.yml`", "`merge-confirm-notice.yml`", "pipeline/auto_notice.py", "병합·승인·쓰기를 하지 않고", "`off` 인 채로 병합된다", "확인 031 의 보기 2", "총괄 결정",
                       "pipeline/auto_notice.json", '{"mode": "off"}', "`off`(기본", "`dry`(모든 계산을 하고 보낼 문장을 실행 요약에만", "`on`(발송)", "값이 이상하면 off", "별도 병합 부탁(T3)",
                       "[M###] 병합 부탁 — ", "80자", "5줄×120자", "`검사: 초록`", "800자 안", "20초 간격으로 세 번", "[M###] 병합완료 확인 - 정상", "`- 이상`", "100자 안", "부모 수", "트리 일치", "트리 비교를 빼고",
                       "변경 파일 수·이름 집합", "main 커밋의 가드레일 결론", "취소·건너뜀이면 판정을 미룬다", "env 로만 받고 파이썬이 모양을 거른다", "제목에 걸리면 보내지 않고 본문 줄에 걸리면 그 줄만 뺀다",
                       "고정 문장·번호·정수만", "dry 의 보낼 문장은 거른 뒤의 값", "GET", "operator_loop.GitHub", "notify.Notifier", "새 외부 접속·새 의존성·새 시크릿은 없다", "문장을 한 번 더 검사한 뒤 보낸다",
                       "알림이 안 가는 쪽이 이상한 알림이 가는 쪽보다 낫다", "첫 관측 절차", "GitHub 에서 처음 도는 것은 병합 뒤", "가짜 응답으로만 시험했다", "중복", "Re-run", "봇의 글 커밋이 main 검사를 취소",
                       "2MB", "300개", "노란 배너", "데스크톱 앱 저장소용은 만들지 않았다", "텔레그램 시크릿이 없다", "WF-16", "tests/test_merge_notice_workflows.py", "tests/test_auto_notice.py", "tests/test_merge_notice_docs.py",
                       # 2차(안전 검증 S 의 권고 반영)
                       "판정 job", "발송 job", "base64 한 줄", "`::` 명령 머리가 끼어들 수 없다", "코드가 만드는 문장 모양과 같은지", "내용 비교 생략", "blob 해시(`files[].sha`)", "심볼릭 링크·폴더 — 도 off",
                       "구조(`낱말 점 영문 2–24자`", "점처럼 읽히는 글자 다섯", "'거른 뒤 자른다'", "앞쪽 600자를 먼저 거름", "과잉 거절", "IDN 최상위 도메인", "`pull_requests[0]` 으로 단순화하지 말 것",
                       "`GET /pulls?head=소유자:가지`", "문장 그대로는 아니다", "시작도 하지 않는다"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("맨 끝 발송 단계 env 에만", text)

    def test_the_limits_in_the_rules_are_the_constants_of_the_code(self):
        text = row(self.text, "| G-A14 |") + doc("docs/ARCHITECTURE.md")
        self.assertEqual((an.MESSAGE_LIMIT, an.READY_TITLE_LIMIT, an.POINT_LINES, an.POINT_LIMIT, an.REASON_LIMIT), (800, 80, 5, 120, 100))
        self.assertEqual((an.CHECK_WAIT, an.CHECK_RETRIES, an.FILES_CAP), (20, 3, 300))
        self.assertEqual((an.POINT_CHECK_CHARS, an.MESSAGE_BYTES_LIMIT, an.MESSAGE_B64_LIMIT), (600, 3200, 4268))
        self.assertIn(f"{an.POINT_CHECK_CHARS}자를 먼저 거름", text)                                # 요점 줄을 자르기 전에 거르는 앞쪽 글자 수
        self.assertIn(f"{an.MESSAGE_LIMIT}자 안", text)
        self.assertIn(f"{an.POINT_LINES}줄×{an.POINT_LIMIT}자", text)
        self.assertIn(f"{an.CHECK_WAIT}초 간격으로 세 번", text)

    def test_wf16_row_lists_the_checks_and_the_limits(self):
        text = row(self.text, "| WF-16 |")
        for needle in ("on: workflow_run", "허용 목록", "WORKFLOW_RUN_ALLOWED", "merge-ready-notice.yml", "merge-confirm-notice.yml", "types: [completed]", "branches", "`read`", "job 수준 permissions", "env·defaults",
                       "`actions/checkout`·`actions/setup-python`", "persist-credentials: false", "`repository`·`token`", "`run` 과 `with.script`", "env 를 거친 것·steps 출력", "git checkout", "eval", "bash -c", "curl",
                       "job 별로 글자 그대로", "python -m pipeline.auto_notice merge-ready", "python -m pipeline.auto_notice send", "`secrets.` 가 나오는 모든 글", "한계", "`if:` 식은 막지 않는다", "G-A13", "BA-S1-4", "탐침 D",
                       "정확히 `decide`·`send` 둘", "`needs: decide`", "`if: needs.decide.outputs.send == 'yes'`", "`NOTICE_MESSAGE_B64`", "`steps.decide.outputs.*`", "판정 job 에는 하나도 없음",
                       "중복 키를 WF-0 오류로", "AN1-S-6·7", "판정 단계 env 의 이름 집합은 고정하지 않는다"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("단계 위치별", text)

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
                       "병합 직후 봇 커밋이 main 검사를 취소한", "시크릿은 발송 job 의 맨 끝 단계 env 에만", "발송 job 은 시작도 하지 않는다", "G-A13·G-A14", "운영자_요청함_사용법.md"):
            self.assertIn(needle, item, needle)
        self.assertNotIn("맨 끝 발송 단계 env", item)


class ArchitectureTest(unittest.TestCase):
    def setUp(self):
        self.text = doc("docs/ARCHITECTURE.md")
        self.section = section(self.text, "## 4-6-4.")

    def test_the_section_sits_between_4_6_3_and_4_7(self):
        self.assertLess(self.text.index("## 4-6-3."), self.text.index("## 4-6-4."))
        self.assertLess(self.text.index("## 4-6-4."), self.text.index("## 4-7."))
        self.assertTrue(self.section.startswith("## 4-6-4. 병합 알림 자동화"))

    def test_the_section_covers_states_both_notices_trust_boundary_and_limits(self):
        for needle in ("확인 031 의 보기 2", "꺼진 채", "앱 저장소용은 만들지 않았다", "workflow_run", "판정 job decide(시크릿 없음)", "발송 job send(needs: decide", "send=yes", "`off`(기본·병합 때의 값)", "`dry`", "`on`",
                       "pipeline/auto_notice.json", "값이 셋 밖(대소문자·공백 포함)이면 `off`", "병합된 PR 자신의 확인부터 새 값이 적용된다", "**병합 부탁**(`merge-ready-notice.yml`)", "`skipped`·`neutral` 도 초록이 아님",
                       "**병합완료 확인**(`merge-confirm-notice.yml`)", "부모 수(squash 는 1", "트리 일치", "트리 비교를 빼고", "**신뢰 경계**", "G-A13·G-A14", "WF-16", "기본 가지 `ref`",
                       "GET 만", "operator_loop.GitHub", "notify.Notifier", "**한계**", "첫 관측 전 미확인", "중복은 막지 못한다", "2MB", "300개", "tests/test_auto_notice.py", "tests/test_merge_notice_workflows.py",
                       "tests/test_workflow_run_rule.py", "tests/test_merge_notice_docs.py", "tests/test_validator_loader.py",
                       "message=<base64 한 줄>", "발송 job 은 판정 job 이 `send=yes` 를 낸 때만 시작한다", "내용 비교 생략", "고정 글(참고 둘·사유 여섯)", "점이 든 코드 이름은 주소 모양이라 그 줄이 빠진다",
                       "`workflow_run.pull_requests` 에 기대지 않고 API 로 찾는다"):
            self.assertIn(needle, self.section, needle)
        self.assertNotIn("문장 파일", self.section)                                            # 문장은 더 이상 파일로 넘어가지 않는다(두 job 은 러너가 다르다)

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

    def test_the_chapters_tell_the_two_job_structure_and_the_content_note(self):
        guide = doc("docs/ACTIONS_GUIDE.md")
        ready, confirm = section(guide, "### 6-20.", "\n### "), section(guide, "### 6-21.", "\n### ")
        for needle in ("두 번째 job 은 시작도 하지 않습니다", "일은 두 job 으로 나뉩니다", "텔레그램 시크릿은 여기에만", "점이 든 코드 이름"):
            self.assertIn(needle, ready, needle)
        for needle in ("'내용 비교 생략' 이라고 적습니다", "시크릿은 발송 job 에만 있습니다", "발송 job 은 시작도 하지 않습니다"):
            self.assertIn(needle, confirm, needle)
        self.assertNotIn("맨 끝 발송 단계", ready + confirm)

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
                       "알림이 없는 열린 PR 은 아직 병합하지 마세요", "같은 알림이 두 번 올 수 있고", "병합·승인·코멘트를 하지 않고", "G-A14", "텔레그램 시크릿은 발송 job 에만 있고", "그 job 이 시작도 하지 않습니다"):
            self.assertIn(needle, body, needle)
        self.assertNotRegex(body, r"https?://")

    def test_the_guide_before_section_8_is_untouched(self):
        self.assertIn("## 7. 알아 둘 것", self.text)
        self.assertLess(self.text.index("## 7. 알아 둘 것"), self.text.index("## 8. 병합 알림 자동화"))


class EngineeringGuideAndRegisterTest(unittest.TestCase):
    def test_the_engineering_rule_row(self):
        line = row(doc("docs/ENGINEERING_GUIDE.md"), "| W13 |")
        for needle in ("workflow_run", "허용 목록", "T3", "권한 읽기뿐", "기본 가지 `ref`", "`actions/checkout`·`actions/setup-python`", "시크릿은 발송 job 의 맨 끝 단계 env 에만", "판정(시크릿 없음)·발송 둘", "G-A13·G-A14", "**WF-16**"):
            self.assertIn(needle, line, needle)
        self.assertEqual(line.count("|"), 4)

    def test_the_defect_rows_use_only_the_numbers_this_bundle_may_use(self):
        text = doc("docs/DEFECT_REGISTER.md")
        # 이 묶음의 번호 구간은 D-398–D-405 — D-406 부터는 다른 묶음(BA1 등)이 쓴다. 통합 뒤에도 이 묶음의 여덟 행이 빠짐없이 있고 형식이 맞는지만 본다(구간 밖 번호는 이 시험이 보지 않는다).
        numbers = sorted({int(number) for number in re.findall(r"^\| \*\*D-([0-9]{3})\*\* \|", text, re.M) if 398 <= int(number) <= 405})
        self.assertEqual(numbers, list(range(398, 406)))                                        # 여덟 행 모두 있고 빠진 번호가 없다
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

    def test_the_second_round_rows_d401_to_d405_name_the_findings_of_the_safety_check_they_answer(self):
        """2차(안전 검증 S 의 권고·참고 반영): 다섯 행이 각각 어느 지적(AN1-S-n)에 답하는지, 어느 시험이 막는지, 무엇으로 고쳤는지를 적는다."""
        text = doc("docs/DEFECT_REGISTER.md")
        wanted = {401: ("AN1-S-1·2", "tests/test_auto_notice.py", "거른 뒤 자름", "구조(`낱말 점 영문 2–24자`"), 402: ("AN1-S-3", "tests/test_auto_notice.py", "lstat", "심볼릭 링크"),
                  403: ("AN1-S-4·5", "tests/test_merge_notice_workflows.py", "job 둘", "`needs: decide`"), 404: ("AN1-S-6·7", "tests/test_validator_loader.py", "중복 키", "`_triggers`"),
                  405: ("AN1-S-10", "tests/test_auto_notice.py", "blob 해시", "내용 비교 생략")}
        for number, needles in wanted.items():
            line = row(text, f"| **D-{number}** |")
            for needle in needles:
                self.assertIn(needle, line, f"D-{number}: {needle}")
            self.assertNotRegex(line, r"https?://")
            self.assertNotIn(TILDE, line)
        self.assertIn("D-401–D-405 는 같은 묶음의 2차 라운드", text)
        self.assertIn("시작점과 기존 워크플로 20개에서 새 오류 0 을 먼저 확인했다", row(text, "| **D-404** |"))
        self.assertIn("발송 job 은 건너뜀 표시", text)                                            # 첫 관측 체크리스트: off·dry 에서 발송 job 은 건너뜀으로 보인다

    def test_the_numbers_in_the_docs_are_the_real_sizes_of_the_mutation_catalog(self):
        """문서가 말하는 변이 개수(두 파일 × 214가지 = 428개)가 시험의 실제 목록과 같다 — 목록을 늘리고 줄이면 문서도 함께 고친다."""
        from test_workflow_run_rule import catalog
        sizes = {len(catalog(READY)), len(catalog(CONFIRM))}
        self.assertEqual(sizes, {214})
        for rel in ("docs/SECURITY_GUARDRAILS.md", "docs/DEFECT_REGISTER.md"):
            self.assertIn("428개", doc(rel), rel)


class PublishPathsTableTest(unittest.TestCase):
    """공개 경로 문서의 워크플로 전수표(docs/PUBLISH_PATHS.md §3)에 두 워크플로가 읽기 전용 한 줄로 올라 있다 — 쓰기 길 검토표(tests/test_publish_paths.py ALLOWED)와 같은 말."""

    PREFIX = "| `merge-ready-notice.yml`, `merge-confirm-notice.yml` |"

    def test_the_two_workflows_have_one_read_only_row_in_the_workflow_table(self):
        text = doc("docs/PUBLISH_PATHS.md")
        line = row(text, self.PREFIX)
        self.assertEqual(text.count(self.PREFIX), 1)
        self.assertEqual(line.count("|"), 8)                                                    # 일곱 칸(파일·경로 번호·무엇을·트리거·쓰기·승인·공개) — 칸 안의 세로선은 쓰지 않는다
        for needle in ("읽기 전용", "pipeline/auto_notice.json", "`off`", "`workflow_run`", "**없음**", "`gh pr merge` 없음", "내려받지도 실행하지도 않는다", "| 아니오 |"):
            self.assertIn(needle, line, needle)
        self.assertNotIn(TILDE, line)
        self.assertNotIn("{{", line)
        self.assertLess(text.index("| `guardrails.yml`, `ai-request.yml`, `telegram-test.yml` |"), text.index(self.PREFIX))
        self.assertLess(text.index(self.PREFIX), text.index("| `chance-shadow.yml` |"))

    def test_the_review_table_of_the_write_paths_knows_both_files_with_the_one_python_entry_and_no_write_signal(self):
        import test_publish_paths as table                                                      # 쓰기 길 검토표 — 두 워크플로는 파이썬 진입점 하나뿐이고 쓰기 신호가 하나도 없다
        for name in ("merge-ready-notice.yml", "merge-confirm-notice.yml"):
            self.assertEqual(table.ALLOWED[name], table.entry(py={"pipeline.auto_notice"}), name)
            self.assertEqual(table.COUNTS[name], {}, name)
            self.assertEqual(table.signature(table.read(name)), table.ALLOWED[name], name)


class ModuleAndWorkflowTextTest(unittest.TestCase):
    def test_the_module_docstring_states_the_rules_the_tests_hold(self):
        text = an.__doc__
        for needle in ("켬 상태", "off", "dry", "on", "값이 셋 밖이거나 다른 키가 있으면 off", "merge-ready", "merge-confirm", "send", "NOTICE_RUN_ID", "NOTICE_DEFAULT_BRANCH",
                       "가지(PR 머리)의 코드는 내려받지도 실행하지도 않는다", "GET", "operator_loop.GitHub", "평문", "알림이 안 가는 쪽이 이상한 알림이 가는 쪽보다 낫다", "G-A13·G-A14",
                       "NOTICE_MESSAGE_B64", "base64", "판정 job", "발송 job", "`pull_requests[0]`", "send=yes", "message=<base64"):
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


class DefinitionLineDocsTest(unittest.TestCase):
    """독립 감사 BA-S2 R2·N6(결함 D-467): 병합 부탁 문장의 새 두 줄(검사 정의가 바뀐 PR 의 경고·머리 커밋 7자리)과 변경 파일 읽기가 구조 절·런북·운영자 사용법에 적혀 있고, 적힌 글이 코드의 상수와 같다."""

    def test_the_architecture_section_describes_the_new_lines_with_the_exact_constants(self):
        section_text = section(doc("docs/ARCHITECTURE.md"), "## 4-6-4.")
        for needle in ("**병합 부탁 문장의 검사 정의 표시와 머리 커밋**", "결함 D-467", "`GET /pulls/{번호}/files`", "병합완료 확인과 같은 읽기", "`.github/` 는 바뀌지 않았다", "옛 이름까지 센다",
                       "`CHECK_DEFINITION_FILES`", "`CHECK_DEFINITION_DIRS`", "`too_large`", "머리 커밋 줄을 운영자가 견주는 것으로"):
            self.assertIn(needle, section_text, needle)
        self.assertIn(f"`{an.DEFINITION_LINE}`", section_text)
        self.assertIn(an.HEAD_LINE.format("a1b2c3d"), section_text)
        for path in an.CHECK_DEFINITION_FILES + an.CHECK_DEFINITION_DIRS:
            self.assertIn(f"`{path}`", section_text, path)

    def test_the_runbook_and_the_operator_guide_say_the_same_marking_for_request_files_and_for_the_operator(self):
        runbook = doc("docs/AGENT_RUNBOOK.md")
        start = runbook.index("   - **검사 정의가 바뀐 병합 가지**")
        item = runbook[start:runbook.index("\n", start)]
        for needle in ("결함 D-467", "`verify` 칸에도", "머리 커밋 7자리", "120자 이하", f"`{an.DEFINITION_LINE}`"):
            self.assertIn(needle, item, needle)
        for path in an.CHECK_DEFINITION_FILES + an.CHECK_DEFINITION_DIRS:
            self.assertIn(f"`{path}`", item, path)
        self.assertLessEqual(len("독립 검증 통과 · 검사 4칸 초록 · 머리 a1b2c3d · " + an.DEFINITION_LINE), 120)         # 예로 든 verify 한 줄이 칸 상한 안이다
        guide = doc("인수인계/운영자_요청함_사용법.md")
        paragraph = guide[guide.index("**검사 정의가 바뀐 병합 부탁에는 경고 한 줄이 붙습니다**"):]
        paragraph = paragraph[:paragraph.index("\n")]
        for needle in (f"`{an.DEFINITION_LINE}`", "머리 커밋 a1b2c3d", "PR 화면의 해시와 같은지", "AI 가 요청 파일로 보내는 병합 부탁에도 같은 표기"):
            self.assertIn(needle, paragraph, needle)

    def test_the_new_text_has_no_tilde_no_double_braces_and_no_address(self):
        """이 변경이 새로 쓴 글만 본다(문서 전체에는 옛 글의 물결표가 있을 수 있다)."""
        architecture, runbook, guide = doc("docs/ARCHITECTURE.md"), doc("docs/AGENT_RUNBOOK.md"), doc("인수인계/운영자_요청함_사용법.md")
        starts = (architecture.index("**병합 부탁 문장의 검사 정의 표시와 머리 커밋**"), runbook.index("   - **검사 정의가 바뀐 병합 가지**"), guide.index("**검사 정의가 바뀐 병합 부탁에는 경고 한 줄이 붙습니다**"))
        for label, text, start in (("ARCHITECTURE", architecture, starts[0]), ("RUNBOOK", runbook, starts[1]), ("사용법", guide, starts[2])):
            new = text[start:text.index("\n", start)]
            self.assertNotIn(TILDE, new, label)
            self.assertNotIn("{" + "{", new, label)
            self.assertNotRegex(new, r"https?://")


if __name__ == "__main__":
    unittest.main()
