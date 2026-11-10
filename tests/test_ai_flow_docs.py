"""docs/AI_FLOW.md 가 코드의 실제 이름·표·상수와 어긋나지 않게 잡는 시험(표류 방지) — 선례: test_fact_docs·test_source_policy_docs. 네트워크 없이 파일만 읽는다.

문서의 표가 등록 상수(tests/ai_flow_scan.py)·방벽 상수(pipeline/ai_guard.py)·시험의 번호와 **양쪽으로** 같아야 한다: 코드에 항목이 늘었는데 표가 그대로이거나, 표에 있는데 코드에 없으면 빨강이다.
설명 문장이 옳은지는 시험이 알 수 없으므로 사람이 본다. 문서 규칙(물결표·링크·Liquid·로컬 경로 없음)과 다른 문서에 한 고침(ARCHITECTURE·DEFECT_REGISTER·SECURITY_GUARDRAILS·ACTIONS_GUIDE·FACT_PATH)도 본다.
"""
import re
import unittest

import _bootstrap
import ai_flow_scan as S
import test_ai_flow as flow
import test_provenance as provenance_test
from pipeline import ai_guard

ROOT = _bootstrap.ROOT
DOC = (ROOT / "docs" / "AI_FLOW.md").read_text(encoding="utf-8")
ARCH = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
REGISTER = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
GUARDS = (ROOT / "docs" / "SECURITY_GUARDRAILS.md").read_text(encoding="utf-8")
ACTIONS = (ROOT / "docs" / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")
FACT_PATH = ROOT / "docs" / "FACT_PATH.md"
CFG = S.DEFAULT_CONFIG
MY_DEFECTS = ("D-190", "D-191", "D-192", "D-193", "D-194", "D-195", "D-196", "D-197", "D-198", "D-199")          # 이 묶음이 DEFECT_REGISTER 에 더한 행(번호 대역 D-190–D-199)


def chunks(text):
    """제목(## 또는 ###) 단위로 나눈 {제목 줄: 본문}."""
    parts = re.split(r"(?m)^(?=#{2,3} )", text)
    return {part.split("\n", 1)[0]: part for part in parts if part.startswith("#")}


CHUNKS = chunks(DOC)


def chunk(prefix):
    found = [body for heading, body in CHUNKS.items() if heading.startswith(prefix)]
    if len(found) != 1:
        raise AssertionError(f"docs/AI_FLOW.md 에 '{prefix}…' 절이 정확히 하나여야 합니다(찾은 수 {len(found)})")
    return found[0]


def table_rows(text):
    """마크다운 표의 모든 줄(머리글 포함, 구분선 제외)을 셀 목록으로."""
    rows = []
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                rows.append(cells)
    return rows


def body_rows(text):
    return table_rows(text)[1:]


def plain(cell):
    return cell.strip("`")


def site(cell):
    """`파일:함수` 칸 → (파일, 함수)."""
    path, _colon, function = plain(cell).partition(":")
    return path, function


class DocRulesTest(unittest.TestCase):
    def test_the_document_follows_the_doc_rules(self):
        self.assertGreater(len(DOC), 8000)
        self.assertNotRegex(DOC, "[~～〜]")                                     # 범위는 en 대시
        self.assertNotRegex(DOC, r"(?i)https?://|www\.|\bftp://")              # 문서에 링크 금지
        for liquid in ("{{", "{%", "%}", "}}"):
            self.assertNotIn(liquid, DOC)
        self.assertNotRegex(DOC, r"[A-Za-z]:[\\/]|/Users/|/home/|\\\\")          # 로컬 경로 금지
        self.assertNotRegex(DOC, r"(?i)ca-pub|adsense|pub-\d{8,}")
        for relative in re.findall(r"\]\((\./[^)]+)\)", DOC):
            self.assertTrue((ROOT / "docs" / relative).exists(), relative)

    def test_the_lines_added_to_the_other_documents_follow_the_same_rules(self):
        new_arch = ARCH[ARCH.index("## 4-11."):ARCH.index("## 5. 상태·멱등성·동시성")]
        rows = [next(line for line in REGISTER.splitlines() if line.startswith(f"| **{number}** |")) for number in MY_DEFECTS]
        rows.append(next(line for line in GUARDS.splitlines() if line.startswith("| G-L10 |")))
        rows.append(next(line for line in ACTIONS.splitlines() if line.startswith("8. 로그에 `AiInputForbidden`")))
        for text in (new_arch, *rows):
            self.assertNotRegex(text, "[~～〜]")
            self.assertNotRegex(text, r"(?i)https?://|www\.")
            for liquid in ("{{", "{%"):
                self.assertNotIn(liquid, text)

    def test_the_document_states_what_it_does_not_do(self):
        for needle in ("켜는 변경은 없다", "정상 입력에서", "AF7", "2단계", "T3", "허용 목록 묶음이 고칠 것", "못 막는", "알 수 없으면 막는다"):
            self.assertIn(needle, DOC)
        self.assertNotRegex(DOC, r"생성기에 연결(?:했|됐|되었)")


class TablesMatchCodeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.found = S.inventory(flow.REAL)

    def test_the_sink_table(self):
        kinds = {"SDK 원시 호출": set(), "호출 객체 소비자": set(), "호출 객체 만들기": set()}
        for cells in body_rows(chunk("## 3. ")):
            self.assertIn(cells[0], kinds)
            kinds[cells[0]].add(site(cells[1]))
        self.assertEqual(kinds["SDK 원시 호출"], set(CFG.ai_primitives))
        self.assertEqual(kinds["호출 객체 소비자"], set(CFG.llm_consumers))
        self.assertEqual(kinds["호출 객체 만들기"], set(CFG.llm_factory_callers))
        self.assertEqual(kinds["SDK 원시 호출"], self.found["primitives"])
        self.assertEqual(kinds["호출 객체 소비자"], self.found["consumers"])
        self.assertEqual(kinds["호출 객체 만들기"], self.found["factories"])

    def test_the_call_site_table(self):
        documented = {}
        for cells in body_rows(chunk("## 4. ")):
            documented.setdefault(plain(cells[0]), set()).add(site(cells[1]))
        self.assertEqual(documented, {name: set(sites) for name, sites in CFG.ai_call_sites.items()})
        self.assertEqual(documented, self.found["call_sites"])

    def test_the_reader_tables(self):
        readers = {site(cells[0]): plain(cells[1]) for cells in body_rows(chunk("### 5-1."))}
        self.assertEqual(readers, {key: kind for key, (kind, _why) in CFG.posts_readers.items()})
        self.assertEqual(set(readers), self.found["readers"])
        calls = set()
        for cells in body_rows(chunk("### 5-2.")):
            path, function = site(cells[0])
            calls.add((path, function, plain(cells[1]), cells[2]))
        self.assertEqual(calls, self.found["filtered_calls"])
        self.assertNotIn("끔", {cells[2] for cells in body_rows(chunk("### 5-2."))})        # 사람·알림·사이트가 for_ai=False 로 읽는 곳은 지금 없다

    def test_the_unfiltered_and_human_caller_tables(self):
        """D-197: for_ai 를 켜지 않은 채 읽는 함수(5-2 의 끔·식 줄)와 사람용 읽기를 부르는 함수(5-4 표)가 등록 상수·코드와 양쪽으로 같다."""
        unfiltered = {site(cells[0]) for cells in body_rows(chunk("### 5-2.")) if cells[2] in ("끔", "식")}
        self.assertEqual(unfiltered, set(CFG.unfiltered_sites))
        self.assertEqual(unfiltered, self.found["unfiltered_calls"])
        humans = {site(cells[0]) for cells in body_rows(chunk("### 5-4."))}
        self.assertEqual(humans, set(CFG.human_callers))
        self.assertEqual(humans, self.found["human_callers"])

    def test_the_consumer_table_names_real_tests(self):
        names = set(re.findall(r"`(\w+Test)`", chunk("### 5-3.")))
        self.assertGreaterEqual(len(names), 6)
        source = (ROOT / "tests" / "test_ai_flow_consumers.py").read_text(encoding="utf-8")
        for name in names:
            self.assertRegex(source, rf"(?m)^class {name}\(", name)

    def test_the_guard_constants_table(self):
        rows = {plain(cells[0]): int(cells[1]) for cells in body_rows(chunk("## 7. ")) if cells[0].startswith("`") and cells[1].isdigit()}
        self.assertEqual(rows, {"TITLE_MIN_CHARS": ai_guard.TITLE_MIN_CHARS, "TITLE_PREFIX_CHARS": ai_guard.TITLE_PREFIX_CHARS,
                                "DESCRIPTION_PREFIX_CHARS": ai_guard.DESCRIPTION_PREFIX_CHARS, "DESCRIPTION_MIN_CHARS": ai_guard.DESCRIPTION_MIN_CHARS})
        section = chunk("## 7. ")
        for kind in ai_guard.KINDS:
            self.assertIn(f"`{kind}`", section)
        self.assertIn("10만 개", section)
        self.assertEqual(ai_guard.MAX_POST_FILES, 100_000)
        self.assertIn("5천만 바이트", section)
        self.assertEqual(ai_guard.MAX_HISTORY_BYTES, 50_000_000)

    def test_the_limits_table_matches_the_limits_test(self):
        ids = [cells[0] for cells in table_rows(chunk("## 7. ")) if re.fullmatch(r"L\d+", cells[0])]
        self.assertEqual(ids, [f"L{n}" for n in range(1, 14)])
        limits = (ROOT / "tests" / "test_ai_guard.py").read_text(encoding="utf-8")
        for name in ("test_the_tail_of_a_long_title_alone_is_not_blocked", "test_a_value_alone_is_not_blocked", "test_a_paraphrase_is_not_blocked", "test_a_translation_is_not_blocked",
                     "test_a_short_title_is_not_a_fragment", "test_tags_category_and_body_sentences_of_a_marked_post_are_not_fragments", "test_a_corrupt_or_oversized_history_file_is_not_read",
                     "test_a_post_file_that_cannot_be_read_gives_no_fragments_that_call_but_is_read_again_on_the_next", "test_a_marker_added_in_place_with_the_same_size_inode_and_an_old_time_is_not_seen",
                     "test_prompts_held_as_bytearray_or_memoryview_are_not_read", "test_lookalike_letters_from_other_scripts_are_not_the_same_text", "test_a_block_or_multiline_title_is_not_read_as_the_title",
                     "test_a_history_that_cannot_be_read_passes_with_one_fixed_warning_line"):
            self.assertIn(name, limits)

    def test_the_rule_table(self):
        documented = {cells[0]: cells[1] for cells in body_rows(chunk("## 8. ")) if re.fullmatch(r"AF\d", cells[0])}
        self.assertEqual(documented, S.RULE_NAMES)
        self.assertNotIn("AF7", documented)
        self.assertIn("AF7", chunk("## 8. "))

    def test_the_blind_spot_table_matches_the_blind_spot_test(self):
        ids = [cells[0] for cells in body_rows(chunk("### 사각지대"))]
        self.assertEqual(ids, [ident for ident, *_rest in flow.BLIND_SPOTS])
        self.assertIn(f"합성 변이 {len(flow.CASES)}개", chunk("## 8. "))

    def test_the_requirement_table(self):
        ids = [cells[0] for cells in body_rows(chunk("## 9. "))]
        self.assertEqual(ids[:-1], ["R3", "R4", "R5", "R6", "R7", "R8", "R13", "R16", "R17"])
        self.assertIn("R1·R2·R12·R14·R15·R18", ids[-1])

    def test_the_marker_writer_section_matches_the_test(self):
        self.assertEqual(provenance_test.MARKER_WRITERS, set())
        self.assertIn("지금 없다", chunk("### 표식 쓰는 곳"))
        self.assertIn("MARKER_WRITERS", chunk("### 표식 쓰는 곳"))

    def test_the_mark_state_table_matches_the_code(self):
        from pipeline import provenance
        rows = {plain(cells[0]) for cells in body_rows(chunk("## 6. "))}
        self.assertEqual(rows, {provenance.MARK_NONE, provenance.MARK_NO_FRONT_MATTER, provenance.MARK_FACTS, provenance.MARK_OTHER, provenance.MARK_UNKNOWN})
        self.assertIn(provenance.CANONICAL_LINE, chunk("## 6. "))


class HandOverTest(unittest.TestCase):
    def test_the_sections_for_the_other_bundles_exist_and_are_complete(self):
        allow = chunk("## 11. ")
        self.assertIn("SOURCE_POLICY.md", allow)
        for number, key in enumerate(("**9절 2항", "**9절 3항", "**9절 7항", "**12절 ③", "**10절·", "**레지스트리 스키마(R10)**"), 1):
            self.assertRegex(allow, rf"(?m)^{number}\. {re.escape(key)}")
        for phrase in ("피드 글(Gemini 로 쓰는 글)", "Fact 분기는 프롬프트를 만들지도 AI 를 부르지도 않는다", "Fact 후보는 `own_title_batches`·`build_post_prompt` 를 지나지 않는다", "ai_blocked"):
            self.assertIn(phrase, allow)
        stage2 = chunk("## 12. ")
        for number, key in enumerate(("**Fact 분기 진입 함수 등록**", "**`NoConnectionTest` 개정**", "**AF7**", "**표식 쓰는 곳 한 군데**", "**후보 공급**", "**제목 정책(R18)·이미지·영문**", "**AI 서술(완성형 단계)**"), 1):
            self.assertRegex(stage2, rf"(?m)^{number}\. {re.escape(key)}")
        self.assertIn("DEFAULT_ENTRIES", stage2)
        self.assertIn("허용 연결 한 군데", stage2)
        self.assertFalse(S.DEFAULT_ENTRIES)       # 진입 함수 목록은 지금 비어 있다 — 2단계가 채운다

    def test_the_stage_two_instructions_keep_their_key_decisions(self):
        """D-199: 문서 표 시험은 설명 문단·12절 지시를 못 본다(지시를 정반대로 바꿔도 초록이었다) — 2단계 지시의 핵심 낱말을 못박는다: AF7 은 닫힌 쪽 극성(`== 'feed'`)·괄호 밖 연결·식 전체 평가 시험·키를 뺄 수 없는 넷, 별도 함수 조건, 같이 고칠 단언과 NoConnectionTest 코드."""
        stage2 = chunk("## 12. ")
        af7 = next(line for line in stage2.splitlines() if line.startswith("3. **AF7**"))
        for phrase in ("== 'feed'", "닫힌 쪽(허용 목록)", "열린 쪽", "괄호 **밖**", "모든 조합으로 평가하는 시험", "조건이 거짓일 때 빈 글자를 얻기 위해서", "chance-fix-images.yml:61", "issue-edit.yml:100",
                       "blogger-en.yml:62", "blogger-ko.yml:64", "구조 방벽(R5·R6·R7)", "비운다"):
            self.assertIn(phrase, af7)
        self.assertIn("`!= 'facts'` 는 읽기 단계가 실패해 출력이 비면 참이 되어 키가 새므로(열린 쪽) 쓰지 않는다", af7)          # 열린 쪽 식은 쓰지 않는다고 적는다(권하지 않는다)
        self.assertIn("별도 함수", stage2)
        first = chunk("### 12-1. ")
        for phrase in ("assertFalse(S.DEFAULT_ENTRIES)", "test_the_marker_writer_section_matches_the_test", "MARKER_WRITERS", "synthetic_fact_entry", "test_the_registry_has_no_switch_for_the_new_path_yet",
                       "FACT_MODULE_NAMES"):
            self.assertIn(phrase, first)
        second = chunk("### 12-2. ")
        for phrase in ("ALLOWED", "허용 연결", "scan_targets", "self.PATTERN.findall"):
            self.assertIn(phrase, second)
        self.assertEqual(second.count("```"), 2)


class OtherDocumentsTest(unittest.TestCase):
    def test_architecture_has_the_new_section_and_the_row(self):
        self.assertEqual(len(re.findall(r"(?m)^## 4-11\. ", ARCH)), 1)
        titles = re.findall(r"(?m)^## (\d+-\d+)\. ", ARCH)
        self.assertEqual(len(titles), len(set(titles)))
        self.assertTrue(ARCH.index("## 4-10.") < ARCH.index("## 4-11.") < ARCH.index("## 5. 상태·멱등성·동시성"))
        section = ARCH[ARCH.index("## 4-11."):ARCH.index("## 5. 상태·멱등성·동시성")]
        self.assertIn("(./AI_FLOW.md)", section)
        self.assertIn("켜는 변경은 없다", section)
        self.assertEqual([cells[0] for cells in body_rows(section)], ["출처 표식", "표식 소비자", "런타임 방벽", "정적 규칙"])
        self.assertEqual(len([line for line in ARCH.splitlines() if line.startswith("| AI 입력 방어 |")]), 1)

    def test_the_defect_register_has_the_new_rows_from_d190(self):
        ids = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", REGISTER)
        self.assertEqual(len(ids), len(set(ids)))
        mine = list(MY_DEFECTS)          # D-186–D-189 는 Gate 후속(GATEFIX3)이 쓴다 — 이 묶음은 D-190 부터(D-190–D-193 은 첫 구현, 그 뒤는 독립 검증 지적 반영)
        self.assertTrue(set(mine) <= set(ids), ids[-8:])
        for identifier in mine:
            row = next(line for line in REGISTER.splitlines() if line.startswith(f"| **{identifier}** |"))
            self.assertEqual(row.count("|"), 7, identifier)       # 표의 여섯 칸
            self.assertIn("**해결**", row)
            self.assertIn("2026-11-10", row)
        self.assertIn("(./AI_FLOW.md)", next(line for line in REGISTER.splitlines() if line.startswith("| **D-190** |")))

    def test_the_security_guardrails_name_the_rule_and_the_t3_change(self):
        row = next(line for line in GUARDS.splitlines() if line.startswith("| G-L10 |"))
        for needle in ("`provenance: \"facts\"`", "T3", "AF0–AF6·AF8", "(./AI_FLOW.md)", "statcan"):
            self.assertIn(needle, row)
        bullet = next(line for line in GUARDS.splitlines() if line.startswith("- AI 흐름 방어 장치를 약하게 하는 변경"))
        for needle in ("AI_PRIMITIVES", "POSTS_READERS", "pipeline/ai_guard.py", "for_ai", "provenance"):
            self.assertIn(needle, bullet)
        self.assertTrue(GUARDS.index("## 3. AI 에이전트가 사용자 승인 없이") < GUARDS.index(bullet) < GUARDS.index("## 4. 사고 대응 플레이북"))
        self.assertIn("test_ai_flow_docs.py", GUARDS)

    def test_the_actions_guide_tells_the_operator_what_the_message_means(self):
        line = next(line for line in ACTIONS.splitlines() if line.startswith("8. 로그에 `AiInputForbidden`"))
        for needle in ("운영자가 할 일은 없고", "(./AI_FLOW.md)", "값은 새지 않았습니다"):
            self.assertIn(needle, line)
        self.assertIn("| [`AI_FLOW.md`](./AI_FLOW.md) |", ACTIONS)

    def test_fact_path_says_it_in_one_voice_when_the_file_exists(self):
        if not FACT_PATH.exists():
            self.skipTest("이 트리에는 구조화 Fact 경로 문서가 없다(병합 뒤 적용된다)")
        text = FACT_PATH.read_text(encoding="utf-8")
        sentence = "이 세 곳(캐나다 통계청 `statcan`·영국 정부 콘텐츠 API `uk_govuk`·미국 NOAA 우주날씨 `noaa_swpc`) 자료에는 AI 서술·번역·요약·다듬기·이미지 설명 단계를 만들지 않는다"
        self.assertIn(sentence, text)
        self.assertNotIn("그림자 실행은 후보를 일반 실행과 같은 함수로 만들고 쓰지 않으므로, Fact 후보도 같은 함수에서 나오면 호환된다", text)
        self.assertIn("**코드와 달랐다**", text)
        self.assertIn("**이 분기는 AI 를 부르지 않는다**", text)
        self.assertEqual(len(re.findall(r"(?m)^- \*\*D-158\*\*", text)), 1)
        self.assertEqual(len(re.findall(r"(?m)^- \*\*D-159\*\*", text)), 1)
        self.assertNotIn("AI 서술(선택)과 출력 검증은 완성형 단계다", text)
        self.assertNotRegex(text, "[~～〜]")
        self.assertNotRegex(text, r"(?i)https?://|www\.")


if __name__ == "__main__":
    unittest.main()
