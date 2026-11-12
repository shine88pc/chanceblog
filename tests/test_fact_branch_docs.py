"""S2b 문서·워크플로 시험: `docs/FACT_PATH.md` §15 와 결정 D-230–D-246·결함 레지스터 D-250–D-256·다른 문서의 S2b 줄이 코드의 실제 이름·표·값과 어긋나지 않고,
워크플로의 AI 키 식(AF7)이 **지금 상태(`content_source` 를 모른다)와 패치 뒤 상태 어느 쪽이든** 문서와 맞으며 패치 식이 어떤 조합에서도 `facts` 실행에 키를 넘기지 않음을 증명한다.
네트워크 없이 파일만 읽는다(워크플로 식은 이 파일의 작은 평가기로 모든 조합을 계산한다 — GitHub 식의 부분집합: `||`·`&&`·`!`·`==`·`!=`·괄호·글자·`true`/`false`/`null`·점 이름)."""
import contextlib
import inspect
import io
import itertools
import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from unittest import mock

import _bootstrap
import ai_flow_scan as SCAN
import generator as g
import lock_helpers
import registry_states
import test_fact_select as SEL
import test_fact_structure as STRUCT
import test_quality_gate_fact as QGF

from pipeline import drafts, egress, fact_candidates as K, fact_supply, publish_lock, shadow_run, source_policy
from pipeline.adapters import base as adapter_base

ROOT = _bootstrap.ROOT
DOC = (ROOT / "docs" / "FACT_PATH.md").read_text(encoding="utf-8")
REGISTER = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
ARCH = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
ACTIONS = (ROOT / "docs" / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")
PUBLISH = (ROOT / "docs" / "PUBLISH_PATHS.md").read_text(encoding="utf-8")
SOURCE_POLICY_DOC = (ROOT / "docs" / "SOURCE_POLICY.md").read_text(encoding="utf-8")
SECTION = DOC[DOC.index("## 15. S2b"):]
DECISIONS = [f"D-{number}" for number in range(230, 247)]
DEFECTS = [f"D-{number}" for number in range(250, 257)]
FOLLOW_DECISIONS = [f"D-{number}" for number in (*range(290, 300), 308, 309)]      # S2BFIX(독립 검증 S2b 의 후속)가 더한 결정(300–307 은 결함 행의 번호)
FOLLOW_DEFECTS = [f"D-{number}" for number in range(300, 308)]              # 같은 묶음이 더한 결함 행
FORBIDDEN = "(?i)" + "|".join(("ca-" + "pub", "ads" + "ense", r"pub-\d{8,}", "chance" + "blog", "shine" + "88", "kc" + "yoon", "pew" + "research"))
BLOG_WORKFLOW = "chance" + "blog.yml"             # 글 작성 워크플로 파일 이름(문서·시험 파일에는 글자 그대로 쓰지 않는다 — 실제 식별자 검사)
SHADOW_WORKFLOW = "chance-shadow.yml"


def table_rows(text):
    rows = []
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                rows.append(cells)
    return rows


def sub_section(text, start, end=None):
    first = text.index(start)
    return text[first:text.index(end, first + 1)] if end else text[first:]


def row_of(text, number):
    return next(line for line in text.splitlines() if line.startswith(f"| {number} |"))


def register_row(number):
    return next(line for line in REGISTER.splitlines() if line.startswith(f"| **{number}** |"))


class DocRulesTest(unittest.TestCase):
    def test_the_new_section_and_the_new_rows_follow_the_document_rules(self):
        rows = [row_of(DOC, number) for number in DECISIONS] + [register_row(number) for number in DEFECTS]
        for text in (SECTION, *rows):
            self.assertNotRegex(text, "[~～〜]")
            self.assertNotRegex(text, r"(?i)https?://|www\.|\bftp://")
            for liquid in ("{{", "{%", "%}", "}}"):
                self.assertNotIn(liquid, text)
            self.assertNotRegex(text, r"[A-Za-z]:[\\/]|/Users/|/home/|\\\\")
            self.assertNotRegex(text, FORBIDDEN)
            self.assertNotRegex(text, r"생성기에 연결(?:했|됐|되었)")
        added = SOURCE_POLICY_DOC[SOURCE_POLICY_DOC.index("## 15. "):]
        self.assertNotRegex(added, "[~～〜]")
        self.assertNotRegex(added, r"(?i)https?://")
        self.assertNotIn("{{", added)
        self.assertNotIn("{%", added)

    def test_the_headings_exist_once_in_order_and_the_old_status_lines_are_dated(self):
        headings = ["## 15. S2b"] + [f"### 15-{number}. " for number in range(1, 11)]
        positions = []
        for heading in headings:
            self.assertEqual(len(re.findall(rf"(?m)^{re.escape(heading)}", DOC)), 1, heading)
            positions.append(DOC.index(heading))
        self.assertEqual(positions, sorted(positions))
        top = DOC[:DOC.index("## 1. 한눈에")]
        self.assertIn("1단계 시점", top)                                  # 1단계의 '연결하지 않았다' 는 그 시점의 기록이다
        self.assertIn("S2b(2단계의 연결 부분 — §15)", top)
        self.assertIn("**켜지는 값은 하나도 없다**", top)

    def test_the_eleventh_section_points_to_the_new_section_and_keeps_its_twelve_items(self):
        part = sub_section(DOC, "### 2단계 연결 계획", "## 12. 설계 결정")
        self.assertIn("S2b(2026-11-11)가 아래 1·2·5·6·8·9·10·12항을 이었고", part)
        self.assertEqual(len(re.findall(r"(?m)^\d+\. \*\*", part)), 12)
        table = table_rows(sub_section(SECTION, "### 15-1.", "### 15-2."))
        self.assertEqual(len(table) - 1, 12)                            # 머리글 하나 + 12항
        self.assertEqual([cells[0].split()[0] for cells in table[1:]], [str(number) for number in range(1, 13)])


class DecisionAndDefectRowsTest(unittest.TestCase):
    def test_the_decisions_d230_to_d246_are_there_once_each_in_order_after_d209(self):
        found = re.findall(r"(?m)^\| (D-\d+) \|", DOC)
        for number in DECISIONS:
            self.assertEqual(found.count(number), 1, number)
        positions = [found.index(number) for number in DECISIONS]
        self.assertEqual(positions, list(range(positions[0], positions[0] + len(DECISIONS))))    # 빠짐없이 이어진다
        self.assertGreater(positions[0], found.index("D-209"))
        for number in DECISIONS:
            self.assertEqual(row_of(DOC, number).count("|"), 4, number)       # 표의 세 칸(번호·결정·이유)

    def test_each_decision_names_the_code_it_decides(self):
        needles = {
            "D-230": ("content_source_of", "registry_errors", 'languages: ["ko"]', "publish_flow: pr", "총괄 기본값보다 좁은 쪽"),
            "D-231": ("select_candidates", "made_from_history", "plan_candidates", "흑점수 두 제품 28일"),
            "D-232": ("fact_start_problems", "fact_start", "FACT_NOT_READY", "_config.yml"),
            "D-233": ("fact_opener", "egress.check_url", "egress.budgeted", "make_fact_transport", "EGRESS_DENIED", "BUDGET_DENIED", "NoConnectionTest"),
            "D-234": ("fact_check_post", "require_pass", "GATE_SOURCE_KEYS", "provider_hosts", "S2BG"),
            "D-235": ("fact_check_post", "fact_history_entry", "with_marker", "entry_with_marker", "MARKER_WRITERS", "지시서와 다른 점"),
            "D-236": ("assets/fact-card.svg", "chart_svg"),
            "D-237": ("run_call_cap", "한 번만"),
            "D-238": ("skipped", "waiting", "FACT_WAITING"),
            "D-239": ("run_facts", "fact_prepare", "run.json"),
            "D-240": ("DEFAULT_ENTRIES", "FACT_MODULE_NAMES", "B16", "generate_fact_post", "run_facts"),
            "D-241": ("content-source", "== 'feed'", "test_fact_branch_docs.py", "T3"),
            "D-242": ("facts_without_key", "get_client"),
            "D-243": ("entry_fields", "DRAFT_CREATED", "publish_lock"),
            "D-244": ("FACT_NOT_READY", "FACT_WAITING", "FACT_NO_CANDIDATE", "FACT_ALL_SKIPPED"),
            "D-245": ("주제 입력", "FACT_NOT_READY"),
            "D-246": ("date.max", "made_from_history"),
        }
        self.assertEqual(set(needles), set(DECISIONS))
        for number, words in needles.items():
            for word in words:
                self.assertIn(word, row_of(DOC, number), (number, word))

    def test_the_defect_rows_are_in_order_after_d219_with_six_cells_and_the_expected_state(self):
        found = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", REGISTER)
        self.assertEqual(len(found), len(set(found)))
        positions = [found.index(number) for number in DEFECTS]
        self.assertEqual(positions, list(range(positions[0], positions[0] + len(DEFECTS))))
        self.assertGreater(positions[0], found.index("D-219"))
        states = {"D-250": "해결", "D-251": "해결", "D-253": "완화", "D-254": "해결", "D-255": "완화", "D-256": "해결"}      # D-254·D-256 은 S2BFIX 가 해결로 고쳤다(의도적 변경 — 이전 기대는 둘 다 열림)
        for number in DEFECTS:
            row = register_row(number)
            self.assertEqual(row.count("|"), 7, number)                       # 표의 여섯 칸
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            self.assertIn(cells[1], ("높음", "중간", "낮음"), number)
            if number in states:                                              # D-252(AF7)의 상태는 워크플로의 실제 상태를 따라간다 — WorkflowStateTest
                self.assertTrue(cells[4].replace("*", "").startswith(states[number]), (number, cells[4]))
        for number, word in (("D-250", "select_candidates"), ("D-251", "fact_opener"), ("D-252", "AF7"), ("D-253", "S2BG"), ("D-254", "build_pr_body"), ("D-255", "B16"), ("D-256", "write_history")):
            self.assertIn(word, register_row(number), number)

    def test_the_names_the_section_and_the_decisions_use_exist_in_the_code_and_are_written_down(self):
        documented = ((source_policy, ("content_source_of", "content_source_errors", "chance_content_source", "fact_start_problems", "fact_start")),
                      (K, ("select_candidates", "made_from_history", "WINDOW_DAYS", "plan_candidates", "representative")),
                      (fact_supply, ("supply", "gate_source", "GATE_SOURCE_KEYS", "SupplyResult", "provider_hosts")),
                      (g, ("generate_fact_post", "fact_opener", "make_fact_transport", "fact_context", "fact_prepare", "fact_check_post", "fact_history_entry", "fact_file_text",
                           "fact_card_url", "facts_without_key")),
                      (shadow_run, ("run_facts",)),
                      (egress, ("check_url", "budgeted", "budget_for", "run_call_cap")))
        for module, names in documented:
            for name in names:
                self.assertTrue(hasattr(module, name), (module.__name__, name))
                self.assertIn(name, DOC, name)
        for module, names in ((source_policy, ("main", "FACT_NOT_READY_OUTCOME", "FACT_WAITING_OUTCOME", "FACT_NO_CANDIDATE_OUTCOME", "FACT_ALL_SKIPPED_OUTCOME", "FACT_QUIET_OUTCOMES")),
                              (K, ("NOT_BEFORE_UTC_MINUTES",)), (fact_supply, ("api_access", "PROVIDER_ID")), (g, ("fact_notes", "OUTCOME_TEXT", "FACT_CARD_FILE")),
                              (shadow_run, ("facts_branch_on",)), (egress, ("CallBudget",))):
            for name in names:
                self.assertTrue(hasattr(module, name), (module.__name__, name))


class FollowUpRowsTest(unittest.TestCase):
    """S2BFIX(독립 검증 S2b 의 후속): 새 결정 D-290–D-299·결함 D-300–D-307·해결로 고친 기존 행 D-254·D-256·§15 의 새 문장이 코드·다른 문서와 어긋나지 않는다.
    다른 가지의 번호를 못박지 않는다 — 이 묶음의 행이 있고 서로 이어지는지만 본다."""
    POINTERS = {"D-300": "D-291", "D-301": "D-290", "D-302": "D-298", "D-303": "D-299", "D-304": "D-296", "D-305": "D-292", "D-306": "D-297", "D-307": "D-293"}
    STATES = {"D-300": "해결", "D-301": "해결", "D-302": "완화", "D-303": "해결", "D-304": "해결", "D-305": "해결", "D-306": "해결", "D-307": "해결"}

    def test_the_new_decisions_come_after_d246_once_each_in_order_with_three_cells_and_the_document_rules(self):
        found = re.findall(r"(?m)^\| (D-\d+) \|", DOC)
        for number in FOLLOW_DECISIONS:
            self.assertEqual(found.count(number), 1, number)
        positions = [found.index(number) for number in FOLLOW_DECISIONS]
        self.assertEqual(positions, list(range(positions[0], positions[0] + len(FOLLOW_DECISIONS))))       # 빠짐없이 이어진다
        self.assertGreater(positions[0], found.index("D-246"))
        for number in FOLLOW_DECISIONS:
            row = row_of(DOC, number)
            self.assertEqual(row.count("|"), 4, number)                                                      # 표의 세 칸(번호·결정·이유)
            self.assertNotRegex(row, "[~～〜]")
            self.assertNotRegex(row, r"(?i)https?://|www\.|\bftp://")
            self.assertNotRegex(row, r"[A-Za-z]:[\\/]|/Users/|/home/|\\\\")
            self.assertNotRegex(row, FORBIDDEN)
            for liquid in ("{{", "{%", "%}", "}}"):
                self.assertNotIn(liquid, row)

    def test_each_new_decision_names_the_code_it_decides_and_the_code_has_those_names_and_values(self):
        needles = {
            "D-290": ("_fact_fetch", "FACT_READ_DEADLINE_SECONDS", "FACT_READ_CHUNK_BYTES", "read1", "fact_clock", "OPENER_FAILED", "TimeoutError", "60초", "64KiB"),
            "D-291": ("facts_without_key", "FIX_IMAGES", "fix_images", "feed"),
            "D-292": ("read_history_strict", "FACT_NOT_READY", "generate_fact_post", "read_history"),
            "D-293": ("draft_flow", "FACT_NOT_READY", "DRAFT_CREATED", "PUBLISHED"),
            "D-294": ("build_pr_body", "is_fact_draft", "provenance: facts", "AI 미사용"),
            "D-295": ("write_history", "200", "date.max", "시뮬레이션"),
            "D-296": ("fact_supply", "run_facts", "AST", "fact_clock", "tests/ai_flow_scan.py"),
            "D-297": ("dedupe_key", "QG7-REUSE", "run_facts", "HELD"),
            "D-298": ("SOURCE_POLICY.md", "§15-10", "D-237", "run_call_cap"),
            "D-299": ("noaa_swpc_json", "T3", "임시 사본", "최소 품질 Gate", "제한 재개 잠금"),
            "D-308": ("pre_flip", "registry_states", "EXPECTED_STATE", "pre_flip_blogs.json", "REGISTRY_PATH", "DEFAULT_PATH", "test_registry_state", "알려진 상태"),
            "D-309": ("670건", "25모듈", "재현 방법", "sitecustomize", "NoOutbound", "D-308", "S2b 검증 D4"),      # N4(D-323): 저장소 밖 도구 이름 대신 방법의 원리와 저장소 안의 도구
        }
        self.assertEqual(set(needles), set(FOLLOW_DECISIONS))
        for number, words in needles.items():
            for word in words:
                self.assertIn(word, row_of(DOC, number), (number, word))
        for name in ("fact_clock", "_fact_read", "_fact_fetch", "FACT_READ_DEADLINE_SECONDS", "FACT_READ_CHUNK_BYTES", "facts_without_key", "generate_fact_post"):
            self.assertTrue(hasattr(g, name), name)
        self.assertEqual((g.FACT_READ_DEADLINE_SECONDS, g.FACT_READ_CHUNK_BYTES), (60, 64 * 1024))             # 문서의 60초·64KiB
        self.assertIn(f"`FACT_READ_DEADLINE_SECONDS`({g.FACT_READ_DEADLINE_SECONDS}초)", row_of(DOC, "D-290"))      # 상수 값이 문서의 같은 자리에 같은 모양으로 적혀 있다
        self.assertIn(f"`FACT_READ_CHUNK_BYTES`({g.FACT_READ_CHUNK_BYTES // 1024}KiB)", row_of(DOC, "D-290"))
        self.assertTrue(hasattr(drafts, "is_fact_draft"))
        self.assertTrue(hasattr(publish_lock, "read_history_strict"))
        self.assertTrue(hasattr(g, "read_history_strict"))
        self.assertTrue(hasattr(lock_helpers, "pre_flip") and hasattr(lock_helpers, "PreFlipRegistry"))                    # D-308: 데코레이터와 도구가 있다
        self.assertEqual(registry_states.STATE_NAMES, ("pre_flip", "p2", "p3"))                                            # 알려진 상태 셋(문서 D-308 의 이름)
        self.assertIn(registry_states.EXPECTED_STATE, registry_states.STATE_NAMES)

    def test_the_new_defect_rows_come_after_d268_with_six_cells_the_expected_state_and_a_pointer_to_their_decision(self):
        found = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", REGISTER)
        self.assertEqual(len(found), len(set(found)))
        positions = [found.index(number) for number in FOLLOW_DEFECTS]
        self.assertEqual(positions, list(range(positions[0], positions[0] + len(FOLLOW_DEFECTS))))
        self.assertGreater(positions[0], found.index("D-268"))
        for number in FOLLOW_DEFECTS:
            row = register_row(number)
            self.assertEqual(row.count("|"), 7, number)                                                      # 표의 여섯 칸
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            self.assertEqual(cells[1], "낮음", number)                                                         # 독립 검증이 매긴 심각도(낮음 넷·정보 다섯 가운데 정보도 낮음 행으로 올렸다)
            self.assertTrue(cells[4].replace("*", "").startswith(self.STATES[number]), (number, cells[4]))
            self.assertIn("S2BFIX", cells[4], number)
            self.assertIn(self.POINTERS[number], row, number)                                                # 결정 번호로 이어진다
            self.assertNotRegex(row, "[~～〜]")
            self.assertNotRegex(row, r"(?i)https?://|www\.|\bftp://")
            self.assertNotRegex(row, FORBIDDEN)
            for liquid in ("{{", "{%", "%}", "}}"):
                self.assertNotIn(liquid, row)
        self.assertEqual(len(set(self.POINTERS.values())), len(self.POINTERS))                              # 결함 행마다 다른 결정을 가리킨다
        self.assertTrue(set(self.POINTERS.values()) <= set(FOLLOW_DECISIONS))

    def test_the_two_old_rows_are_marked_resolved_and_point_to_the_new_rows(self):
        for number, pointers in (("D-254", ("D-294", "D-307")), ("D-256", ("D-295",))):
            row = register_row(number)
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            self.assertTrue(cells[4].replace("*", "").startswith("해결"), (number, cells[4]))
            self.assertIn("S2BFIX", cells[4])
            for pointer in pointers:
                self.assertIn(pointer, row, (number, pointer))


    def test_section_15_10_states_the_call_total_limit_and_the_decision_item_and_the_other_new_sentences_are_there(self):
        part = sub_section(SECTION, "### 15-10.")
        for word in ("호출 합계·간격은 지키지 못한다", "D-298", "같은 파일 60초·다른 파일 5초", "24–30번", "3–5회", "후보를 모두 건너뛰는 날", "켜기 전 결정 항목", "날짜별 호출 횟수", "SOURCE_POLICY.md", "D-237"):
            self.assertIn(word, part, word)
        self.assertIn("계산으로 만든 초안(AI 미사용)", part)                                                  # D-254 는 고쳤다
        self.assertNotIn("켜기 전에 고친다", part)
        self.assertIn("D-295", part)
        self.assertIn("HISTORY_DATE_UNREADABLE", part)
        connection = sub_section(SECTION, "### 15-4.", "### 15-5.")
        self.assertIn("| 응답을 60초 안에 다 받지 못함", connection)
        self.assertIn("D-290", connection)
        approval = sub_section(SECTION, "### 15-5.", "### 15-6.")
        for word in ("read_history_strict", "D-292", "D-293", "D-294", "계산으로 만든 초안(AI 미사용)", "FACT_NOT_READY"):
            self.assertIn(word, approval, word)
        self.assertIn("D-292", sub_section(SECTION, "### 15-2.", "### 15-3."))
        self.assertIn("D-293", sub_section(SECTION, "### 15-2.", "### 15-3."))

    def test_the_t3_patch_table_has_the_companion_column_and_names_the_three_patch_drafts(self):
        """D-299: 켜기 전 T3 패치 표(§15-8)에 '동반 수정(시험·문서)' 칸이 있고 다섯 행 모두 다섯 칸이며 패치 초안 세 이름(저장소 밖 파일의 이름)이 적혀 있다. 켜는 변경을 적용한 뒤에도 표 모양은 그대로다 — 행의 상태 칸만 바뀐다."""
        part = sub_section(SECTION, "### 15-8.", "### 15-9.")
        rows = table_rows(part)
        self.assertEqual(rows[0], ["순서", "변경", "등급", "상태", "동반 수정(시험·문서)"])
        self.assertEqual([cells[0] for cells in rows[1:]], ["1", "2", "3", "4", "5"])
        for cells in rows[1:]:
            self.assertEqual(len(cells), 5, cells[0])
        for name in ("01_af7_workflow_key", "02_flip_values", "03_gate_lock"):
            self.assertIn(name, part, name)
        for forbidden in ("C:", "audit6", "flip_patches", "/Users/"):
            self.assertNotIn(forbidden, part, forbidden)                                                    # 저장소 밖 파일은 이름만 적고 경로를 적지 않는다

    def test_the_t3_section_splits_what_the_branch_already_holds_from_what_the_patches_carry(self):
        """D-308·D-309: §15-8 이 '병합 가지가 먼저 담은 것' 과 '패치가 담는 것' 을 나눠 적고 검증 D4 의 짐작보다 컸다는 사실(25모듈 약 670건)과 알려진 상태 가드를 말한다."""
        part = sub_section(SECTION, "### 15-8.", "### 15-9.")
        for word in ("병합 가지가 먼저 담은 것과 패치가 담는 것(D-308·D-309)", "시험 25모듈 약 670건", "tests/registry_states.py", "tests/test_registry_state.py", "lock_helpers.pre_flip", "EXPECTED_STATE", "켜기 전·후 어느 상태에서도 초록"):
            self.assertIn(word, part, word)
        self.assertIn("tests/test_registry_state.py", sub_section(SECTION, "### 15-9.", "### 15-10."))
        self.assertEqual(register_row("D-303").count("670건"), 1)

    def test_the_other_documents_say_the_history_read_is_a_reason_for_the_quiet_stop(self):
        row = next(line for line in ACTIONS.splitlines() if line.startswith("| `FACT_NOT_READY` |"))
        self.assertIn("이력 파일 읽기", row)
        exit_row = next(line for line in ARCH.splitlines() if line.startswith("| 정상 건너뜀(Fact 경로) |"))
        self.assertIn("이력 파일 읽기", exit_row)
        self.assertEqual(exit_row.count("|"), 6)


class S2bfix2DocsTest(unittest.TestCase):
    """S2BFIX2(S2BFIX 독립 검증의 새 문제 N1–N7 중 처리분): 새 결정 D-320–D-325·결함 D-326–D-331·§15-8 권고 순서·D-309 재현 서술·§15-10 한계 문장이 코드·다른 문서와 어긋나지 않는다.
    다른 가지의 번호·전체 최댓값을 못박지 않는다 — 이 묶음의 행이 있고 서로 이어지는지만 본다."""
    NEW_DECISIONS = [f"D-{number}" for number in range(320, 326)]
    NEW_DEFECTS = [f"D-{number}" for number in range(326, 332)]
    POINTERS = {"D-326": "D-320", "D-327": "D-321", "D-328": "D-322", "D-329": "D-323", "D-330": "D-324", "D-331": "D-325"}
    STATES = {"D-326": "해결", "D-327": "해결", "D-328": "해결", "D-329": "해결", "D-330": "열림", "D-331": "열림"}
    SEVERITY = {"D-326": "낮음", "D-327": "낮음", "D-328": "정보", "D-329": "정보", "D-330": "정보", "D-331": "정보"}
    FACT_LINE = "- 제목 유사도: 해당 없음(계산 글은 제목을 견주지 않고, 같은 기간·같은 자료로 이미 낸 글이 있으면 후보에서 빼는 중복 키로 막음)"
    FEED_LINE = "- 제목 유사도: 기존 글·대기 중인 초안과 비슷하지 않음(후보 0.6·생성 제목 0.7 기준, 생성기가 검사함)"
    GATE_FAMILIES = ["QG0", "QG1", "QG2", "QG3", "QG4", "QG5", "QG6", "QG7", "QG8"]

    @staticmethod
    def order_steps(paragraph):
        """권고 순서 문단을 ①…⑥ 여섯 조각으로 자른다(각 표시가 처음 나오는 자리 — 뒤쪽 문장에서 되풀이되는 표시는 보지 않는다)."""
        positions, cursor = [], 0
        for mark in "①②③④⑤⑥":
            index = paragraph.index(mark + " ", cursor)
            positions.append(index)
            cursor = index + 1
        return [paragraph[start:end] for start, end in zip(positions, positions[1:] + [None])]

    def test_the_new_decision_rows_follow_d309_once_each_in_order_with_three_cells_and_the_document_rules(self):
        found = re.findall(r"(?m)^\| (D-\d+) \|", DOC)
        for number in self.NEW_DECISIONS:
            self.assertEqual(found.count(number), 1, number)
        positions = [found.index(number) for number in self.NEW_DECISIONS]
        self.assertEqual(positions, list(range(positions[0], positions[0] + len(self.NEW_DECISIONS))))       # 빠짐없이 이어진다
        self.assertGreater(positions[0], found.index("D-309"))
        for number in self.NEW_DECISIONS:
            row = row_of(DOC, number)
            self.assertEqual(row.count("|"), 4, number)                                                      # 표의 세 칸(번호·결정·이유)
            self.assertNotRegex(row, "[~～〜]")
            self.assertNotRegex(row, r"(?i)https?://|www\.|\bftp://")
            self.assertNotRegex(row, r"[A-Za-z]:[\\/]|/Users/|/home/|\\\\")
            self.assertNotRegex(row, FORBIDDEN)
            for liquid in ("{{", "{%", "%}", "}}"):
                self.assertNotIn(liquid, row)

    def test_each_new_decision_names_the_code_and_the_words_it_decides(self):
        needles = {
            "D-320": ("build_pr_body", "is_fact_draft", "제목 유사도", "해당 없음", "dedupe_key", "select_candidates", "바이트까지", "S2BFIX N1"),
            "D-321": ("02_flip_values", "SOURCE_POLICY.md", "5항", "README.md", "AI_COLLAB.md", "ARCHITECTURE.md", "KR/EN", "재실행 스크립트", "N2·N8"),
            "D-322": ("권고 순서", "여섯 단계", "03_gate_lock", "8편", "4편", "PUBLISH_PATHS.md", "S2BFIX N3"),
            "D-323": ("D-309", "도구 이름을 빼고", "sitecustomize", "NoOutbound", "run_real_cli", "S2BFIX N4"),
            "D-324": ("RecursionError", "read_history_strict", "OSError", "ValueError", "20만 겹", "재귀 한계를 넘는", "S2BFIX N5"),
            "D-325": ("QG1–QG8", "QG0–QG8", "40번 되풀이한 문단", "보는 것이 없다", "S2c", "quality_gate.py", "고정 문장", "S2BFIX N7"),
        }
        self.assertEqual(set(needles), set(self.NEW_DECISIONS))
        for number, words in needles.items():
            for word in words:
                self.assertIn(word, row_of(DOC, number), (number, word))
        self.assertIn(self.FACT_LINE[len("- 제목 유사도: "):], row_of(DOC, "D-320"))                         # 결정 행이 코드가 쓰는 문구를 그대로 인용한다

    def test_the_new_defect_rows_follow_d307_with_six_cells_the_expected_severity_state_and_a_pointer_to_their_decision(self):
        found = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", REGISTER)
        self.assertEqual(len(found), len(set(found)))
        positions = [found.index(number) for number in self.NEW_DEFECTS]
        self.assertEqual(positions, list(range(positions[0], positions[0] + len(self.NEW_DEFECTS))))
        self.assertGreater(positions[0], found.index("D-307"))
        for number in self.NEW_DEFECTS:
            row = register_row(number)
            self.assertEqual(row.count("|"), 7, number)                                                      # 표의 여섯 칸
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            self.assertEqual(cells[1], self.SEVERITY[number], number)                                         # 독립 검증이 매긴 심각도 그대로
            self.assertTrue(cells[4].replace("*", "").startswith(self.STATES[number]), (number, cells[4]))
            self.assertIn("S2BFIX2", cells[4], number)
            self.assertIn(self.POINTERS[number], row, number)                                                # 결정 번호로 이어진다
            self.assertNotRegex(row, "[~～〜]")
            self.assertNotRegex(row, r"(?i)https?://|www\.|\bftp://")
            self.assertNotRegex(row, FORBIDDEN)
            for liquid in ("{{", "{%", "%}", "}}"):
                self.assertNotIn(liquid, row)
        self.assertEqual(len(set(self.POINTERS.values())), len(self.POINTERS))                              # 결함 행마다 다른 결정을 가리킨다
        self.assertTrue(set(self.POINTERS.values()) <= set(self.NEW_DECISIONS))
        self.assertIn("> D-326–D-331 은 2026-11-12 에 추가했다(", REGISTER)                                    # 머리말의 번호 대역 안내

    def test_the_calculated_draft_line_in_the_decision_is_what_the_code_writes_and_the_other_two_places_name_the_decision(self):
        """N1(D-320): 최소 입력(글 머리말·이력 항목에 표식이 둘 다 있다)으로 부른 `build_pr_body` 의 제목 유사도 줄이 결정 행이 인용한 문구와 같고, 표식이 하나뿐이면 옛 줄이다 — 문서와 코드가 같은 말을 한다."""
        text = '---\nlayout: post\ntitle: "시험 제목"\nprovenance: "facts"\n---\n본문 문단입니다.\n'
        entry = {"provenance": "facts", "kr_title": "시험 제목"}
        self.assertTrue(drafts.is_fact_draft(entry, text))
        lines = drafts.build_pr_body(entry, text, None, owner="owner").splitlines()
        self.assertEqual([line for line in lines if line.startswith("- 제목 유사도")], [self.FACT_LINE])
        feed = drafts.build_pr_body({"kr_title": "시험 제목"}, text, None, owner="owner").splitlines()          # 이력 항목에 표식이 없다 → 옛 줄
        self.assertEqual([line for line in feed if line.startswith("- 제목 유사도")], [self.FEED_LINE])
        self.assertIn("D-320", sub_section(SECTION, "### 15-5.", "### 15-6."))
        self.assertIn("D-320", sub_section(SECTION, "### 15-10."))

    def test_the_recommended_order_has_six_steps_and_the_gate_and_lock_patch_comes_before_the_pause_is_released(self):
        """N3(D-322): 권고 순서 ①–⑥ 의 ④ 가 패치 03(Gate 켜기와 잠금 켜기)이고 ⑥ 정지를 푸는 단계보다 앞이며 ③ 값 패치 뒤다. 실측 한 문장과 `PUBLISH_PATHS.md` §6 의 같은 순서 문장이 있다."""
        part = sub_section(SECTION, "### 15-8.", "### 15-9.")
        paragraph = next(line for line in part.splitlines() if line.startswith("권고 순서(총괄 결정 대기):"))
        steps = self.order_steps(paragraph)
        self.assertEqual(len(steps), 6)
        for step, words in zip(steps, (("정지 변수를 켠다",), ("AF7", "1번"), ("2·3번 값",), ("4번", "03_gate_lock", "Gate 켜기", "잠금"), ("그림자 실행", "3회", "§11 11항"), ("정지를 푼다", "첫 승인 초안"))):
            for word in words:
                self.assertIn(word, step, (step[:20], word))
        gate_step = next(index for index, step in enumerate(steps) if "03_gate_lock" in step)
        release_step = next(index for index, step in enumerate(steps) if "정지를 푼다" in step)
        values_step = next(index for index, step in enumerate(steps) if "2·3번 값" in step)
        self.assertEqual((values_step, gate_step, release_step), (2, 3, 5))                                  # 값 → Gate·잠금 → (그림자 실행) → 정지 해제
        for word in ("**④ 는 ⑥ 보다 앞이어야 한다**", "`PUBLISH_PATHS.md` §6", "잠금 꺼짐은 초안 8편(하루 두 편인 날 3일)", "잠금 켬은 4편(주 2편씩, 하루 두 편인 날 0)", "D-322"):
            self.assertIn(word, paragraph, word)
        self.assertIn("잠금·최소 품질 Gate·그림자 검증이 끝난 뒤 운영자가 해제", PUBLISH)                    # 순서의 근거 문장이 그 문서에 그대로 있다
        self.assertIn("아래 권고 순서의 첫 단계", next(line for line in part.splitlines() if line.startswith("| 5 |")))      # 표 5번 행(정지 변수)은 ① 을 가리킨다
        self.assertIn("권고 순서 ⑤", sub_section(SECTION, "### 15-10."))                                    # 그림자 실행을 가리키는 쪽의 번호가 따라 옮겨졌다
        self.assertIn("그림자 실행", steps[4])
        self.assertNotIn("권고 순서 ④", DOC)

    def test_the_second_patch_row_lists_the_documents_the_flip_values_make_false(self):
        """N2(D-321): 표 2번 행의 동반 수정 칸이 값 때문에 거짓이 되는 문서 서술 넷을 이름으로 적는다(패치 파일은 저장소 밖 — 이 문서의 목록이 켜는 PR 작성자의 체크리스트다)."""
        part = sub_section(SECTION, "### 15-8.", "### 15-9.")
        row = next(cells for cells in table_rows(part)[1:] if cells[0] == "2")
        self.assertEqual(len(row), 5)
        for word in ("docs/SOURCE_POLICY.md", "§1 5항", "켜지는 않았다", "README.md", "Bilingual (KR/EN)", "AI_COLLAB.md", "§3.2", "KR/EN 생성", "docs/ARCHITECTURE.md", "§2", "KR/EN 쌍", "국문 단독", "시험이 못박지 않아", "거짓인 채 남는다", "D-321"):
            self.assertIn(word, row[4], word)
        for name in ("docs/SOURCE_POLICY.md", "README.md", "AI_COLLAB.md", "docs/ARCHITECTURE.md"):
            self.assertTrue((ROOT / name).is_file(), name)

    def test_the_d309_row_points_to_tools_that_exist_in_the_repository_and_the_old_out_of_repository_tool_is_not_named(self):
        """N4(D-323): D-309 행의 재현 서술 — 방법의 원리와 저장소 안의 같은 원리의 도구 둘. 가리킨 도구가 실제로 저장소에 있고 옛 저장소 밖 도구의 이름은 문서 어디에도 없다."""
        row = row_of(DOC, "D-309")
        for word in ("670건", "25모듈", "재현 방법", "sitecustomize", "PYTHONPATH", "NoOutbound", "run_real_cli", "tests/telegram_inbox_helpers.py", "tests/test_generator_source_policy.py", "D-308", "S2b 검증 D4"):
            self.assertIn(word, row, word)
        self.assertNotIn("netblock", DOC)
        helpers = (ROOT / "tests" / "telegram_inbox_helpers.py").read_text(encoding="utf-8")
        self.assertRegex(helpers, r"(?m)^class NoOutbound\b")
        for name in ("socket.socket", "connect", "getaddrinfo", "self.attempts"):
            self.assertIn(name, helpers.split("class NoOutbound", 1)[1], name)                                  # 연결·이름 해석 시도를 막고 기록한다
        cli_test = (ROOT / "tests" / "test_generator_source_policy.py").read_text(encoding="utf-8")
        self.assertIn("def run_real_cli", cli_test)
        for name in ("socket.socket.connect = blocked", "socket.create_connection = blocked", "socket.getaddrinfo = blocked"):
            self.assertIn(name, cli_test, name)

    def test_a_history_file_nested_beyond_the_recursion_limit_ends_all_three_readers_with_the_same_exception(self):
        """N5(D-324): 깊이가 재귀 한계를 넘는 이력은 Fact 경로의 엄격한 읽기만이 아니라 잠금 가드의 읽기와 피드 경로의 읽기도 같은 `RecursionError` 로 끝난다 — 가짜 예외로 본다(실제 20만 겹 파일은 환경마다 한계가 달라 쓰지 않는다).
        평범한 깨짐(`JSONDecodeError`)은 세 읽기가 모두 조용히 처리하는 대조군이다."""
        part = sub_section(SECTION, "### 15-10.")
        for word in ("20만 겹", "RecursionError", "read_history_strict", "D-324", "조용히 멈추지 않고", "종료 1", "이력·파일 변경 0", "NOAA 요청 0", "해 없음", "같은 규칙·같은 예외", "코드는 바꾸지 않았다"):
            self.assertIn(word, part, word)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text("[]", encoding="utf-8")
            with mock.patch.object(g, "HISTORY_FILE", path):
                with mock.patch("json.loads", side_effect=json.JSONDecodeError("깨짐", "x", 0)):                 # 대조군: 평범한 깨짐
                    self.assertIsNone(g.read_history_strict())
                    self.assertIsNone(publish_lock.read_history_strict(path))
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(g.read_history(), [])
                with mock.patch("json.loads", side_effect=RecursionError("너무 깊다")):
                    with self.assertRaises(RecursionError):
                        g.read_history_strict()
                    with self.assertRaises(RecursionError):
                        publish_lock.read_history_strict(path)
                    with self.assertRaises(RecursionError):
                        g.read_history()
            self.assertEqual(path.read_text(encoding="utf-8"), "[]")                                         # 파일은 그대로다
        self.assertIn("except (OSError, ValueError)", inspect.getsource(g.read_history_strict))               # 문서가 말하는 '잡는 예외' 가 코드의 그 줄이다

    def test_the_gate_lets_a_paragraph_of_one_sentence_repeated_forty_times_through_and_its_rule_families_are_only_qg0_to_qg8(self):
        """N7(D-325): Gate 에 문장 반복을 보는 규칙이 없다 — 반복 문단을 본문에 붙여도 보류 0 이고, 본문을 반복으로만 채워 걸리는 것은 제목의 숫자·낱말 규칙(QG6)뿐이다. 규칙 갈래가 QG0–QG8 이라는 것도 못박는다
        (새 규칙 갈래가 생기면 이 시험과 §15-10 한계 문장을 함께 고친다)."""
        part = sub_section(SECTION, "### 15-10.")
        for word in ("고정 문장 반복", "보류 규칙이 없다", "QG1–QG8", "40번 되풀이한 문단", "반복 때문이 아니라", "QG6-TITLE-NUMBER", "이 묶음 밖", "S2c 입력이다", "pipeline/quality_gate.py", "D-325"):
            self.assertIn(word, part, word)
        source = (ROOT / "pipeline" / "quality_gate.py").read_text(encoding="utf-8")
        self.assertEqual(sorted(set(re.findall(r'Hold\("(QG\d)-', source))), self.GATE_FAMILIES)
        self.assertIn("QG6-TITLE-NUMBER", source)
        post = QGF.golden_posts()["r04_kp"]
        head, divider, body = QGF.TR.generator_file(post)[0].partition("\n---\n")
        self.assertEqual(divider, "\n---\n")
        repeated = "이 값은 위성이 재는 지구 자기장의 흔들림 정도를 뜻합니다. 값이 클수록 흔들림이 큽니다. 이 값만으로 사람이나 설비에 어떤 영향이 있다고 말할 수는 없습니다. " * 40
        self.assertEqual(QGF.run(post).codes(), [])                                                          # 대조군: 원래 글은 보류 0
        self.assertEqual(QGF.run(post, content=head + divider + body + "\n\n" + repeated).codes(), [])        # 반복 문단을 붙여도 보류 0
        only_repeated = QGF.run(post, content=head + divider + repeated).codes()
        self.assertTrue(only_repeated and set(only_repeated) <= {"QG6-TITLE-NUMBER", "QG6-TITLE-WORD"}, only_repeated)


class CodeTablesTest(unittest.TestCase):
    def test_the_gate_dictionary_keys_in_the_section_are_the_code_keys(self):
        part = sub_section(SECTION, "### 15-6.", "### 15-7.")
        cells = [row[0] for row in table_rows(part)[1:]]
        in_doc = set(re.findall(r"`(\w+)`", " ".join(cells)))
        self.assertEqual(in_doc, set(fact_supply.GATE_SOURCE_KEYS))
        self.assertEqual(len(fact_supply.GATE_SOURCE_KEYS), 9)

    def test_the_skip_reasons_and_the_budget_codes_in_the_tables_exist_in_the_code(self):
        supply_source = (ROOT / "pipeline" / "fact_supply.py").read_text(encoding="utf-8")
        generator_source = (ROOT / "generator.py").read_text(encoding="utf-8")
        egress_source = (ROOT / "pipeline" / "egress.py").read_text(encoding="utf-8")
        reasons = sub_section(SECTION, "### 15-3.", "### 15-4.")
        for reason in ("ADAPTER:", "INSUFFICIENT:", "DUPLICATE:DEDUPE_KEY", "REJECTED:", "BAD_INPUT:TODAY", "BAD_INPUT:RETRIEVED_AT"):
            self.assertIn(reason, reasons, reason)
            self.assertIn(reason, supply_source, reason)
        for word in ("FRONT_MATTER", "MARKER_ERROR", "GATE:"):
            self.assertIn(word, reasons, word)
            self.assertIn(f'"{word}', generator_source, word)
        connection = sub_section(SECTION, "### 15-4.", "### 15-5.")
        for code in ("RUN_CAP", "RETRY_CAP", "STOPPED_BY_STATUS", "STOPPED_URL", "SKIPPED_AFTER_FAILURES"):
            self.assertIn(code, connection, code)
            self.assertIn(f'"{code}"', egress_source, code)
        for code in ("EGRESS_DENIED", "BUDGET_DENIED", "BAD_SHAPE", "BAD_ACCESS", "TOO_LARGE"):
            self.assertIn(code, reasons + connection, code)
            self.assertIn(code, adapter_base.MESSAGES, code)

    def test_the_static_rules_scan_exactly_the_new_fact_modules(self):
        """`AI_FLOW.md` §12-1 의 5번: 새 Fact 모듈은 `FACT_MODULE_NAMES` 에도 올라야 임포트 격리·위험 모듈 규칙이 걸린다 — 새 모듈 목록(구조 시험)과 같은 집합이고 모두 실제 파일이다."""
        self.assertEqual(set(SCAN.FACT_MODULE_NAMES), set(STRUCT.NEW_MODULES))
        for name in SCAN.FACT_MODULE_NAMES:
            base = ROOT / "pipeline" / name.replace(".", "/")
            self.assertTrue(base.with_suffix(".py").is_file() or (base / "__init__.py").is_file(), name)
        self.assertIn("fact_supply", SCAN.FACT_MODULE_NAMES)

    def test_the_window_table_and_the_subject_order_match_the_code(self):
        part = sub_section(SECTION, "**선택 정책 `select_candidates`**", "### 15-4.")
        seen = {}
        for cells in table_rows(part)[1:]:
            days = int(re.match(r"(\d+)일", cells[1]).group(1))
            for product in re.findall(r"`(\w+)`", cells[0]):
                seen[product] = days
        self.assertEqual(seen, K.WINDOW_DAYS)
        self.assertEqual(K.NOT_BEFORE_UTC_MINUTES, {"ssn_daily": 30})
        self.assertIn("0시 30분", part)
        self.assertIn("·".join(f"`{spec.spec_id}`" for spec in K.SPECS), part)         # 글감 여섯의 순서가 코드와 같다
        self.assertEqual(len(K.SPECS), 6)

    def test_the_start_conditions_are_the_six_the_code_checks(self):
        part = sub_section(SECTION, "**시작 안전장치**", "### 15-3.")
        rows = table_rows(part)[1:]
        self.assertEqual([cells[0].split()[0] for cells in rows], ["1", "2", "3", "4", "5", "6"])
        self.assertIn("자체 카드 이미지 파일", rows[4][0])                                            # 문서의 조건 이름은 코드가 남기는 이유 문장과 같은 말이다
        self.assertIn("자체 카드 이미지 파일", (ROOT / "generator.py").read_text(encoding="utf-8"))
        problems = source_policy.fact_start_problems("feed", "legacy", ["x"], None, fact_supply.PROVIDER_ID)
        self.assertGreaterEqual(len(problems), 4)                                     # 순수 판정이 보는 네 가지(스위치·허용 목록 모드·레지스트리·허용 목록 읽기)가 모두 걸린다
        self.assertIn(fact_supply.PROVIDER_ID, part)
        self.assertIn("assets/fact-card.svg", part)
        self.assertTrue(g.FACT_CARD_FILE.is_file())

    def test_the_outcome_codes_are_in_every_document_that_names_them_with_the_same_colors(self):
        quiet = (source_policy.FACT_NOT_READY_OUTCOME, source_policy.FACT_WAITING_OUTCOME, source_policy.FACT_NO_CANDIDATE_OUTCOME)
        self.assertEqual(tuple(source_policy.FACT_QUIET_OUTCOMES), quiet)
        for code in quiet + (source_policy.FACT_ALL_SKIPPED_OUTCOME,):
            self.assertIn(code, g.OUTCOME_TEXT)
            row = next(line for line in ACTIONS.splitlines() if line.startswith(f"| `{code}` |"))
            self.assertIn("초록 + 파란 안내" if code in quiet else "초록 + 노란 경고", row, code)
            self.assertIn(code, ARCH)
        exit_rows = [line for line in ARCH.splitlines() if line.startswith("| 정상 건너뜀(Fact 경로) |") or line.startswith("| 경고(Fact 경로) |")]
        self.assertEqual(len(exit_rows), 2)
        self.assertTrue(all(row.count("|") == 6 for row in exit_rows))                 # 표의 다섯 칸

    def test_the_other_documents_name_the_switch_and_the_new_stage(self):
        self.assertEqual(len(re.findall(r"(?m)^\| `content_source` \|", ARCH)), 1)
        field = next(line for line in ARCH.splitlines() if line.startswith("| `content_source` |"))
        for word in ("feed", "facts", "source_policy: allowlist", 'languages: ["ko"]', "publish_flow: pr", "T3", "FACT_PATH.md"):
            self.assertIn(word, field)
        self.assertEqual(len(re.findall(r"(?m)^\| \*\*Fact 분기\*\* \|", ARCH)), 1)
        section = sub_section(ARCH, "## 4-10.", "## 4-11.")
        self.assertIn("**S2b(2026-11-11)**", section)
        self.assertIn("**연결은 한 줄이다**", section)
        self.assertNotIn("연결 금지가 시험으로 지켜진다", ARCH)
        self.assertEqual(len(re.findall(r"(?m)^## 15\. ", SOURCE_POLICY_DOC)), 1)
        for word in ("content_source_of", "FACT_NOT_READY", "egress.check_url", "T3", "FACT_PATH.md"):
            self.assertIn(word, SOURCE_POLICY_DOC[SOURCE_POLICY_DOC.index("## 15. "):])

    def test_the_own_card_is_a_small_plain_svg_without_scripts_or_outside_references(self):
        raw = g.FACT_CARD_FILE.read_text(encoding="utf-8")
        root = ElementTree.fromstring(raw)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertTrue([node for node in root.iter() if node.tag.endswith("title") and (node.text or "").strip()])
        self.assertTrue([node for node in root.iter() if node.tag.endswith("desc") and (node.text or "").strip()])
        for node in root.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            self.assertNotIn(tag, ("script", "image", "foreignObject", "a", "use", "style", "text"), tag)       # 스크립트·바깥 그림·글꼴이 있는 글자·스타일 시트 없음
            for key, value in node.attrib.items():
                self.assertNotIn("href", key)
                self.assertNotRegex(value, r"(?i)https?:|url\(\s*[\"']?(?!#)")
        self.assertLess(len(raw.encode("utf-8")), 4096)
        self.assertNotRegex(raw, "(?i)noaa|nasa|logo")


class SimulationTableTest(unittest.TestCase):
    """§15-9 의 52주 표는 시험이 그대로 다시 계산해 문서와 견준다 — 문서의 숫자가 코드와 어긋나면 빨개진다."""

    def computed(self, model, cap, picker=None):
        posts = SEL.simulate(*SEL.NoStarvationTest.YEAR, weekly_cap=cap, model=model, picker=picker)
        counts = [sum(1 for _day, name in posts if name == spec_id) for spec_id in SEL.ALL]
        gaps = []
        for spec_id in SEL.ALL:
            days = [day for day, name in posts if name == spec_id]
            gaps.append(max(((later - earlier).days for earlier, later in zip(days, days[1:])), default=0))
        return len(posts), "·".join(str(count) for count in counts), max(gaps)

    def test_the_table_in_the_section_is_what_the_simulation_gives(self):
        part = sub_section(SECTION, "- **굶는 글감 없음", "- **시험 모듈**")
        rows = {cells[0]: cells[1:] for cells in table_rows(part)[1:]}
        names = {"rolling": "굴러가는 7일", "calendar": "달력 주"}
        for model in ("rolling", "calendar"):
            for cap in (1, 2):
                total, counts, gap = self.computed(model, cap)
                self.assertEqual(rows[f"{cap} · {names[model]}"], [str(total), counts, f"{gap}일"], (model, cap))
        for cap in (1, 2, 3):
            total, counts, _gap = self.computed("calendar", cap, picker=SEL.old_policy)
            self.assertEqual(rows[f"대조군: S2a 정책 · 달력 주 상한 {cap}"], [str(total), counts, "—"], cap)
        self.assertEqual(len(rows), 7)

    def test_the_section_states_the_two_bounds_the_simulation_test_holds(self):
        part = sub_section(SECTION, "- **굶는 글감 없음", "- **시험 모듈**")
        self.assertIn("상한 1 에서 8주·상한 2 에서 6주를 넘지 않고", part)
        for model in ("rolling", "calendar"):
            self.assertLessEqual(self.computed(model, 1)[2], 8 * 7)
            self.assertLessEqual(self.computed(model, 2)[2], 6 * 7)
        for year in (2009, 2015, 2020, 2026, 2032, 2037):
            self.assertIn(str(year), part)


# ----------------------------------------------------------------------------
# 워크플로의 AI 키 식(AF7) — GitHub 식의 부분집합을 계산하는 작은 평가기
# ----------------------------------------------------------------------------
TOKEN = re.compile(r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<op>&&|\|\||==|!=|!|\(|\))|(?P<word>[A-Za-z_][A-Za-z0-9_.\-]*))")


def tokenize(text):
    text, position, tokens = text.strip(), 0, []
    while position < len(text):
        match = TOKEN.match(text, position)
        if not match or match.end() == position:
            raise ValueError(f"읽을 수 없는 식: {text[position:position + 20]!r}")
        position = match.end()
        kind = match.lastgroup
        tokens.append((kind, match.group(kind)))
    return tokens


def truthy(value):
    """GitHub 식의 거짓: false·0·빈 글자·null 만(그 밖의 글자는 모두 참)."""
    return not (value is None or value is False or value == "" or (isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0))


def number(value):
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value) if str(value).strip() else 0.0
    except ValueError:
        return float("nan")


def loose_equal(left, right):
    """같은 종류의 글자끼리는 대소문자를 가리지 않고, 종류가 다르면 수로 바꿔 견준다(null 은 0, 글자가 수가 아니면 NaN — NaN 은 무엇과도 같지 않다)."""
    if isinstance(left, str) and isinstance(right, str):
        return left.lower() == right.lower()
    if left is None and right is None:
        return True
    return number(left) == number(right)


class Evaluator:
    """우선순위: `!` > `==`·`!=` > `&&` > `||`. `&&`·`||` 는 GitHub 처럼 불리언이 아니라 피연산자 값을 돌려준다."""

    def __init__(self, text, context):
        self.tokens, self.index, self.context = tokenize(text), 0, context

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        self.index += 1
        return token

    def run(self):
        value = self.or_expression()
        if self.index != len(self.tokens):
            raise ValueError("식이 끝나지 않았다")
        return value

    def or_expression(self):
        value = self.and_expression()
        while self.peek() == ("op", "||"):
            self.take()
            right = self.and_expression()
            value = value if truthy(value) else right
        return value

    def and_expression(self):
        value = self.equality()
        while self.peek() == ("op", "&&"):
            self.take()
            right = self.equality()
            value = right if truthy(value) else value
        return value

    def equality(self):
        left = self.unary()
        while self.peek() in (("op", "=="), ("op", "!=")):
            operator = self.take()[1]
            equal = loose_equal(left, self.unary())
            left = equal if operator == "==" else not equal
        return left

    def unary(self):
        if self.peek() == ("op", "!"):
            self.take()
            return not truthy(self.unary())
        return self.primary()

    def primary(self):
        kind, value = self.take()
        if kind == "op" and value == "(":
            inner = self.or_expression()
            if self.take() != ("op", ")"):
                raise ValueError("괄호가 닫히지 않았다")
            return inner
        if kind == "str":
            return value[1:-1].replace("''", "'")
        if kind == "word":
            if value == "true":
                return True
            if value == "false":
                return False
            if value == "null":
                return None
            return self.context.get(value)
        raise ValueError(f"식을 읽을 수 없다: {value!r}")


def evaluate(expression, **context):
    return Evaluator(expression, context).run()


SECRET = "비밀값"
OUTPUT = "steps.source.outputs.content_source"
OLD_BLOG_KEY = "(github.event_name != 'workflow_dispatch' || !inputs.dry_run || inputs.real_ai) && secrets.GEMINI_API_KEY || ''"
NEW_BLOG_KEY = "(github.event_name != 'workflow_dispatch' || !inputs.dry_run || inputs.real_ai) && steps.source.outputs.content_source == 'feed' && secrets.GEMINI_API_KEY || ''"
OLD_SHADOW_KEY = "secrets.GEMINI_API_KEY"
NEW_SHADOW_KEY = "steps.source.outputs.content_source == 'feed' && secrets.GEMINI_API_KEY || ''"
INSIDE_THE_PARENTHESES = "(github.event_name != 'workflow_dispatch' || !inputs.dry_run || inputs.real_ai && steps.source.outputs.content_source == 'feed') && secrets.GEMINI_API_KEY || ''"
OPEN_SIDE = "(github.event_name != 'workflow_dispatch' || !inputs.dry_run || inputs.real_ai) && steps.source.outputs.content_source != 'facts' && secrets.GEMINI_API_KEY || ''"
EVENTS = ("schedule", "workflow_dispatch", "push")
FLAGS = (True, False, None)
OUTPUTS = ("feed", "facts", "", None, "weird", "feed2", " feed")
SECRETS = (SECRET, "")


def combinations():
    for event, dry_run, real_ai, output, secret in itertools.product(EVENTS, FLAGS, FLAGS, OUTPUTS, SECRETS):
        yield {"github.event_name": event, "inputs.dry_run": dry_run, "inputs.real_ai": real_ai, OUTPUT: output, "secrets.GEMINI_API_KEY": secret}


def leaks(expression):
    """읽기 단계의 출력이 `feed` 가 아닌데 비밀이 나오는 조합 목록."""
    return [context for context in combinations() if context[OUTPUT] != "feed" and evaluate(expression, **context) != ""]


def key_expressions(name):
    text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    return text, [match.group(1).strip() for match in re.finditer(r"GEMINI_API_KEY:\s*\$\{\{\s*(.+?)\s*\}\}", text)]


class EvaluatorTest(unittest.TestCase):
    """평가기가 GitHub 의 규칙대로 계산하는지(속이 비지 않게): 연산자는 값을 돌려주고 `&&` 가 `||` 보다 먼저 묶인다."""

    def test_the_operators_return_operands_like_github_does(self):
        self.assertEqual(evaluate("'a' && 'b' || 'c'"), "b")
        self.assertEqual(evaluate("'' && 'b' || 'c'"), "c")
        self.assertEqual(evaluate("null || 'x'"), "x")
        self.assertEqual(evaluate("true && 'x'"), "x")
        self.assertIs(evaluate("!null"), True)
        self.assertIs(evaluate("'Feed' == 'feed'"), True)                         # 글자 비교는 대소문자를 가리지 않는다
        self.assertIs(evaluate("x == 'feed'"), False)                              # 없는 값은 null — 수 0 과 NaN 이라 같지 않다
        self.assertIs(evaluate("x == ''", x=""), True)

    def test_and_binds_tighter_than_or_and_parentheses_group(self):
        self.assertIs(evaluate("false && true || true"), True)
        self.assertIs(evaluate("false && (true || true)"), False)
        self.assertEqual(evaluate("(a || b) && 'x' || 'y'", a=None, b=None), "y")
        self.assertEqual(evaluate("(a || b) && 'x' || 'y'", a=None, b=True), "x")

    def test_bad_expressions_are_errors_not_guesses(self):
        for text in ("(a || b", "a ||", "&& a", "a b", "'abc"):
            with self.assertRaises(ValueError, msg=text):
                evaluate(text)


class PatchExpressionTest(unittest.TestCase):
    def test_the_old_expressions_pass_the_key_whatever_the_read_step_says_which_is_why_facts_runs_get_it_today(self):
        context = {"github.event_name": "schedule", "inputs.dry_run": None, "inputs.real_ai": None, OUTPUT: "facts", "secrets.GEMINI_API_KEY": SECRET}
        self.assertEqual(evaluate(OLD_BLOG_KEY, **context), SECRET)
        context.update({"github.event_name": "workflow_dispatch", "inputs.dry_run": True, "inputs.real_ai": False})
        self.assertEqual(evaluate(OLD_BLOG_KEY, **context), "")                    # 연습 실행의 기본은 키를 넘기지 않는다(옛 동작 그대로)
        self.assertEqual(evaluate(OLD_SHADOW_KEY, **context), SECRET)

    def test_the_patch_expressions_never_pass_the_key_unless_the_read_step_says_feed(self):
        self.assertEqual(leaks(NEW_BLOG_KEY), [])
        self.assertEqual(leaks(NEW_SHADOW_KEY), [])
        total = len(list(combinations()))
        self.assertEqual(total, len(EVENTS) * len(FLAGS) ** 2 * len(OUTPUTS) * len(SECRETS))      # 이벤트·dry_run·real_ai·출력·비밀의 모든 조합
        self.assertGreater(total, 300)

    def test_the_patch_expressions_give_the_old_value_when_the_read_step_says_feed(self):
        checked = 0
        for context in combinations():
            if context[OUTPUT] != "feed":
                continue
            checked += 1
            self.assertEqual(evaluate(NEW_BLOG_KEY, **context), evaluate(OLD_BLOG_KEY, **context), context)
            self.assertEqual(evaluate(NEW_SHADOW_KEY, **context), evaluate(OLD_SHADOW_KEY, **context), context)
        self.assertGreater(checked, 50)

    def test_the_two_tempting_wrong_forms_do_leak_which_is_why_the_closed_side_form_is_the_only_one_written_down(self):
        inside, open_side = leaks(INSIDE_THE_PARENTHESES), leaks(OPEN_SIDE)
        self.assertTrue(any(context["github.event_name"] == "schedule" and context[OUTPUT] == "facts" for context in inside))      # 괄호 안에 붙이면 정기 실행의 facts 에도 샌다
        self.assertTrue(any(context[OUTPUT] in ("", None) for context in open_side))                                               # 열린 쪽 식은 읽기 단계가 실패해 출력이 비면 샌다
        self.assertFalse(any(context[OUTPUT] == "facts" for context in open_side))                                                 # 열린 쪽 식은 facts 자체는 막는다 — 그래서 빈 출력이 새는 줄 모르기 쉽다


class WorkflowStateTest(unittest.TestCase):
    """지금 두 워크플로의 키 식을 읽어 두 상태(패치 전·후) 중 어느 쪽이든 문서와 맞게 한다 — 패치(T3)를 적용한 PR 은 문서의 '열림' 표시도 같이 고친다."""

    FILES = (BLOG_WORKFLOW, SHADOW_WORKFLOW)

    def states(self):
        out = {}
        for name in self.FILES:
            text, expressions = key_expressions(name)
            self.assertEqual(len(expressions), 1, f"{name}: GEMINI_API_KEY 를 넘기는 줄은 정확히 하나여야 한다")
            self.assertEqual(text.count("secrets.GEMINI_API_KEY"), 1, name)
            out[name] = (text, expressions[0], OUTPUT in text)
        return out

    def test_both_workflows_are_in_the_same_state_and_that_state_is_one_of_the_two_known(self):
        states = self.states()
        self.assertEqual({patched for _text, _expression, patched in states.values()}, {states[BLOG_WORKFLOW][2]}, "두 워크플로가 같은 상태여야 한다(한쪽만 패치하지 않는다)")
        blog, shadow = states[BLOG_WORKFLOW], states[SHADOW_WORKFLOW]
        if not blog[2]:
            self.assertEqual(blog[1], OLD_BLOG_KEY)
            self.assertEqual(shadow[1], OLD_SHADOW_KEY)
            self.assertNotIn("content_source", blog[0])                          # 지금 워크플로는 content_source 를 모른다
            self.assertNotIn("content_source", shadow[0])
        else:
            for _text, expression, _patched in states.values():
                self.assertEqual(leaks(expression), [], expression)               # 패치 뒤 상태: 어떤 식이든 feed 가 아니면 키가 비어야 한다
            for name in self.FILES:
                text = states[name][0]
                step = text.index("id: source")
                key_line = text.index("GEMINI_API_KEY:")
                self.assertLess(step, key_line, name)                             # 읽기 단계가 키를 넘기는 단계보다 앞에 있다
                self.assertIn("python -m pipeline.source_policy content-source", text[step:key_line], name)
                self.assertIn("GITHUB_OUTPUT", text[step:key_line], name)

    def test_the_documents_say_the_state_that_is_true(self):
        patched = self.states()[BLOG_WORKFLOW][2]
        status = [cell.strip() for cell in register_row("D-252").strip().strip("|").split("|")][4]
        section = sub_section(SECTION, "**AF7 패치 초안**", "### 15-9.")
        if patched:
            self.assertNotIn("열림", status, "AF7 패치를 적용했으면 D-252 의 상태를 고친다(해결)")
            self.assertNotIn("지금 두 워크플로는 `content_source` 를 모르고", section, "AF7 패치를 적용했으면 15-8 의 현재 상태 문장을 고친다")
        else:
            self.assertIn("열림", status)
            self.assertIn("T3", status)
            self.assertIn("지금 두 워크플로는 `content_source` 를 모르고", section)

    def test_the_expressions_the_section_describes_are_the_ones_proven_here(self):
        section = sub_section(SECTION, "**AF7 패치 초안**", "### 15-9.")
        for word in ("`python -m pipeline.source_policy content-source`", "== 'feed'", "괄호 밖", "`&&` 가 `||` 보다 먼저 묶여", "모든 조합"):
            self.assertIn(word, section, word)
        decision = row_of(DOC, "D-241")
        for word in ("괄호 **밖**", "`읽기 단계 출력 == 'feed'`", "`&&`", "T3"):
            self.assertIn(word, decision, word)
        self.assertIn("01_af7_workflow_key", sub_section(SECTION, "### 15-8.", "### 15-9."))      # 표의 첫 패치 이름 — 켜는 변경을 적용한 뒤에는 '패치 초안' 이 '적용함·병합함' 으로 바뀌므로 이름으로 묻는다(같은 강도)

    def test_the_real_workflows_expressions_evaluate_without_error_in_either_state(self):
        for name in self.FILES:
            _text, expressions = key_expressions(name)
            for context in itertools.islice(combinations(), 0, 400):
                self.assertIn(evaluate(expressions[0], **context), ("", SECRET), (name, context))


if __name__ == "__main__":
    unittest.main()
