"""해제하는 날의 순서 한 줄(AP16 — 확인 015 의 F047)의 문서 시험 — `docs/OPS_INBOX.md` §10-3 의 새 문단이 '변수는 운영자만 지운다 · AI 는 변경을 미리 준비만 한다 · 병합은 운영자가 한다'는
규칙과, 코드가 실제로 만드는 항목 id·알림 수준·운영자 전용 병합 목록·워치독이 읽는 곳·STALE 기준 시간과 어긋나지 않는지 본다.
문장이 읽기 좋은지는 시험이 알 수 없어 사람이 본다. 여기서는 ① 문단의 자리(§10-3 안, 점검표 위치 문단 바로 아래, 표 줄이 아님) ② 필수 낱말과 규칙을 어기는 모양이 없는지
③ 문단이 말하는 사실(항목 id·알림 수준·'한 줄'이면 된다·정책 선언은 모음만 읽는다·STALE 기준)을 코드로 대조 ④ 결함 대장 행 — 을 본다.
네트워크·실제 시계 없이 파일과 순수 함수만 쓴다. 실제 정책 파일의 선언이 켜져 있는지 꺼져 있는지에는 기대지 않는다(해제한 뒤에도 이 시험은 그대로 통과해야 한다)."""
import json
import re
import unittest
from datetime import datetime, timedelta, timezone

import _bootstrap
from pipeline import health
from pipeline import inbox
from pipeline import inbox_policy as ip
from pipeline import registry

ROOT = _bootstrap.ROOT
DOC = (ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
GUIDE = (ROOT / "docs" / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
REGISTER = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
POLICY = json.loads((ROOT / ip.POLICY_FILE).read_text(encoding="utf-8"))

LEAD = "**해제하는 날의 순서 한 줄**"
PLACE = "**해제 점검표의 위치**"
URL = "https://github.com/o/r"

# §10-3 안의 문단들(빈 줄로 나눈다) — 새 문단은 이 중 하나다.
_START, _END = DOC.find("### 10-3. "), DOC.find("### 10-4. ")
SECTION_3 = DOC[_START:_END] if 0 <= _START < _END else ""
PARAGRAPHS = SECTION_3.split("\n\n")
PARAGRAPH = next((text for text in PARAGRAPHS if text.startswith(LEAD)), "")

# 시험용 정지 선언(실제 정책 파일의 값과 무관) — 켠 것과, 같은 선언에서 `active` 한 칸만 끈 것.
PLANNED = {"active": True, "since": "2026-01-02", "reason": "시험용 이유", "decision_ref": "시험용 근거", "resume_conditions": ["시험용 조건 하나"], "resume_gate_passed": False}
DECLARED = ip.parse_policy({"schema_version": 1, "planned_pause": PLANNED})
TURNED_OFF = ip.parse_policy({"schema_version": 1, "planned_pause": dict(PLANNED, active=False)})


def one(items):
    assert len(items) == 1, [item.id for item in items]
    return items[0]


def backticked(text):
    return re.findall(r"`([^`]+)`", text)


class PlacementTest(unittest.TestCase):
    def test_the_paragraph_exists_once_and_inside_section_10_3(self):
        self.assertGreaterEqual(_START, 0)
        self.assertGreater(_END, _START)
        self.assertEqual(DOC.count(LEAD), 1)
        self.assertTrue(PARAGRAPH, "§10-3 안에 '해제하는 날의 순서 한 줄' 문단이 없습니다")
        self.assertGreaterEqual(DOC.index(LEAD), _START)
        self.assertLess(DOC.index(LEAD), _END)

    def test_it_is_the_paragraph_right_below_the_checklist_place_paragraph(self):
        places = [index for index, text in enumerate(PARAGRAPHS) if text.startswith(PLACE)]
        self.assertEqual(len(places), 1)
        self.assertTrue(PARAGRAPHS[places[0]].rstrip().endswith("해제는 이 셋을 확인한 운영자가 직접 정합니다."), "기존 문단의 끝 문장은 그대로여야 합니다")
        self.assertLess(places[0] + 1, len(PARAGRAPHS))
        self.assertTrue(PARAGRAPHS[places[0] + 1].startswith(LEAD), "새 문단은 해제 점검표의 위치 문단 바로 아래에 있어야 합니다")

    def test_it_is_one_paragraph_and_not_a_table_row(self):
        self.assertTrue(PARAGRAPH)
        self.assertEqual(PARAGRAPH.strip().count("\n"), 0, "한 문단(빈 줄도 줄바꿈도 없음)이어야 합니다")
        self.assertFalse(PARAGRAPH.lstrip().startswith("|"))
        self.assertLessEqual(len(PARAGRAPH), 1200)

    def test_the_resume_checks_table_still_has_its_six_rows_and_the_fifth_row_is_untouched(self):
        start = DOC.index("### 10-11. ")
        text = DOC[start:]
        rows = [line for line in text.splitlines() if re.match(r"^\| \d+ \|", line)]
        self.assertEqual(len(rows), 6)
        self.assertEqual(sum(1 for line in text.splitlines() if "해제하는 날의 순서 한 줄" in line), 0, "표 줄로 옮기지 않습니다")
        self.assertIn("재개하면 정책 파일의 `planned_pause.active` 를 끄는 변경(AI 가 준비하고 운영자가 병합)이 따라와야", rows[4])


class RuleTest(unittest.TestCase):
    def test_only_the_operator_removes_the_variable(self):
        for phrase in ("운영자만 지웁니다", "AI 는 변수를 만지지 않습니다", "`PIPELINE_PAUSE`"):
            self.assertIn(phrase, PARAGRAPH, phrase)

    def test_the_ai_only_prepares_and_the_operator_merges(self):
        for phrase in ("AI 가 미리 준비", "운영자가 병합합니다", "AI 는 병합하지 않습니다", "`planned_pause.active`"):
            self.assertIn(phrase, PARAGRAPH, phrase)
        # 'AI 가' 는 '미리 준비' 에만 쓴다 — AI 가 같은 시각에 바꾼다·병합한다·지운다는 문장은 규칙 위반이다.
        self.assertEqual(re.findall(r"AI 가(?! 미리 준비)", PARAGRAPH), [])
        for word in ("AI 도", "AI 와 운영자", "AI 또는", "AI 나 운영자", "같은 시각에 바꿉니다", "자동으로 바꿉니다", "자동으로 끕니다"):
            self.assertNotIn(word, PARAGRAPH, word)
        # 병합은 운영자가 한다 — '병합합니다' 앞의 말은 늘 '운영자가' 다.
        merges = re.findall(r"(\S+) 병합합니다", PARAGRAPH)
        self.assertTrue(merges)
        self.assertEqual(set(merges), {"운영자가"})

    def test_the_sources_of_the_rule_say_the_same(self):
        self.assertIn("`PIPELINE_PAUSE`(발행 정지 변수)는 운영자만 만지고 해제도 운영자만 한다", AGENTS)
        self.assertIn("이 파일은 사람이 검토하는 병합으로만 고친다(AI 가 자동으로 고치지 않는다)", POLICY["_doc"])

    def test_the_paragraph_says_the_policy_file_stays_with_the_operator_even_when_ai_merging_is_on(self):
        # 이 파일이 운영자 전용 병합 목록(승인해도 AI 가 병합하지 않는 12항목 중 발행 정지·발행 재개)에 있다는 사실은 기존 시험이 코드와 문서로 못박는다.
        # 병합 정책 모듈과 그 문서의 이름은 기존 시험이 부를 수 있는 파일을 셋으로 제한하므로 이 시험은 부르지 않는다 — 여기서는 문단이 그 사실을 말하는지만 본다.
        self.assertIn(f"`{ip.POLICY_FILE}`", PARAGRAPH)
        self.assertIn("이 파일은 AI 병합이 켜져도 운영자가 직접 병합하는 목록에 있습니다", PARAGRAPH)

    def test_the_policy_file_has_the_flag_the_paragraph_names_on_a_line_of_its_own(self):
        self.assertIsInstance(POLICY["planned_pause"]["active"], bool)
        self.assertIn("active", ip._PAUSE_KEYS)
        self.assertTrue(hasattr(DECLARED.planned_pause, "active"))
        # '한 줄 변경' — 켜짐·꺼짐 어느 쪽이든 그 칸은 정책 파일에서 줄 하나를 차지한다(다른 칸과 한 줄에 섞여 있지 않다).
        lines = (ROOT / ip.POLICY_FILE).read_text(encoding="utf-8").splitlines()
        flag_lines = [line for line in lines if re.match(r'^\s*"active":\s*(true|false),?\s*$', line)]
        self.assertEqual(len(flag_lines), 1)
        self.assertEqual(sum(1 for line in lines if '"active"' in line), 1)


class CodeFactsTest(unittest.TestCase):
    def test_the_ids_and_titles_are_the_ones_the_inbox_makes_when_only_one_side_is_done(self):
        unset = one(inbox.pause_items(False, URL, DECLARED))        # 변수만 지웠다 — 정책 선언은 아직 켜져 있다
        plain = one(inbox.pause_items(True, URL, TURNED_OFF))       # 선언만 껐다 — 변수는 아직 켜져 있다
        in_paragraph = {token for token in backticked(PARAGRAPH) if token == "pause" or token.startswith("pause:")}
        self.assertEqual(in_paragraph, {unset.id, plain.id})
        self.assertNotEqual(unset.id, plain.id)
        self.assertIn("실수로 해제했나요?", unset.title)
        self.assertIn("'실수로 해제했나요?'", PARAGRAPH)
        self.assertIn(plain.title, PARAGRAPH)

    def test_the_alert_words_match_the_levels_the_guide_explains(self):
        unset = one(inbox.pause_items(False, URL, DECLARED))
        plain = one(inbox.pause_items(True, URL, TURNED_OFF))
        legend = {}
        for line in DOC.split("## 10. ")[0].splitlines():
            found = re.match(r"^\| \*\*[^|]+\*\* \(`(action|check|info)`\) \|[^|]*\| ([^|]+) \|\s*$", line)
            if found:
                legend[found.group(1)] = found.group(2).strip()
        self.assertEqual(set(legend), {"action", "check", "info"})
        self.assertEqual((unset.level, plain.level), (inbox.LEVEL_CHECK, inbox.LEVEL_ACTION))
        self.assertEqual(legend[unset.level], "알림 없음")
        self.assertTrue(legend[plain.level].startswith("새로 생기면"))
        self.assertIn(f"(`{unset.id}`, 확인 항목이라 {legend[unset.level]})", PARAGRAPH)
        self.assertIn(f"(`{plain.id}`, 해야 할 일이라 알림이 갈 수 있음)", PARAGRAPH)

    def test_doing_both_leaves_no_pause_item_and_the_one_line_is_enough(self):
        # TURNED_OFF 는 켠 선언에서 `active` 한 칸만 바꾼 것이다 — 그 한 칸으로 변수가 꺼진 상태의 확인 항목이 사라진다.
        self.assertEqual(len(inbox.pause_items(False, URL, DECLARED)), 1)
        self.assertEqual(inbox.pause_items(False, URL, TURNED_OFF), [])
        self.assertEqual(inbox.pause_items(False, URL, None), [])
        self.assertIn("둘 다 마치면 두 항목이 모두 사라집니다", PARAGRAPH)

    def test_only_the_inbox_reads_the_declaration_not_the_watchdog(self):
        readers = set()
        for pattern in ("*.py", "pipeline/**/*.py", "scripts/**/*.py"):
            for path in ROOT.glob(pattern):
                if "planned_pause" in path.read_text(encoding="utf-8", errors="replace"):
                    readers.add(path.relative_to(ROOT).as_posix())
        self.assertEqual(readers, {"pipeline/inbox.py", "pipeline/inbox_policy.py"})
        for name in ("scripts/watchdog.py", "pipeline/health.py", ".github/workflows/watchdog.yml"):
            path = ROOT / name
            self.assertTrue(path.is_file(), name)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("planned_pause", text, name)
            self.assertNotIn("inbox_policy", text, name)
        self.assertIn("확인 필요 모음(`pipeline/inbox.py`·`pipeline/inbox_policy.py`)만 읽고 워치독은 읽지 않습니다", PARAGRAPH)

    def test_the_stale_sentence_is_the_one_in_the_actions_guide_and_the_numbers_are_the_codes(self):
        start = GUIDE.index("### 3-9. ")
        section = GUIDE[start:GUIDE.index("### 3-10. ")]
        self.assertIn("재개한 직후에는 마지막 글이 오래돼 `STALE`이 열릴 수 있고, 새 글이 나오면 자동으로 닫힙니다", section)
        self.assertIn("`docs/ACTIONS_GUIDE.md` 3-9", PARAGRAPH)
        chance = registry.get_blog(registry.load_registry(), "chance")
        gap = chance["health"]["max_gap_hours"]
        limit = gap + health.WEEKLY_EXTRA_HOURS
        self.assertEqual(limit % 24, 12)                                     # 8일 반
        for phrase in (f"마지막 글 {gap}시간", f"{limit}시간", f"{limit // 24}일 반", "`STALE`(심각)", "빨갛게 끝날 수 있"):
            self.assertIn(phrase, PARAGRAPH, phrase)
        now = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
        inside = health.evaluate(chance, [], now, last_content_commit=now - timedelta(hours=limit), weekly_cap=1)
        beyond = health.evaluate(chance, [], now, last_content_commit=now - timedelta(hours=limit, minutes=1), weekly_cap=1)
        self.assertEqual(inside, [])
        self.assertEqual([(found.code, found.severity) for found in beyond], [("STALE", "critical")])
        watchdog = (ROOT / "scripts" / "watchdog.py").read_text(encoding="utf-8")
        self.assertRegex(watchdog, r"if new_critical and not dry:\n(?:.*\n){0,4}?\s+return 1\n")      # 새로 생긴 심각 건은 실행을 빨갛게 한다


class DocumentRulesAndRegisterTest(unittest.TestCase):
    def test_the_paragraph_follows_the_document_rules(self):
        self.assertTrue(PARAGRAPH)
        self.assertNotIn(chr(126), PARAGRAPH)
        self.assertIsNone(re.search(r"https?://", PARAGRAPH))
        self.assertNotIn("{{", PARAGRAPH)
        self.assertNotIn("{%", PARAGRAPH)
        self.assertNotRegex(PARAGRAPH, r"[A-Za-z]:[/\\]")
        self.assertEqual(PARAGRAPH.count("`") % 2, 0)

    def test_the_register_row_is_in_the_main_table_and_is_resolved(self):
        rows = {found.group(1): found.group(0) for found in re.finditer(r"^\| \*\*(D-\d+)\*\* \|.*$", REGISTER, re.M)}
        self.assertEqual(len(re.findall(r"^\| \*\*D-390\*\* \|", REGISTER, re.M)), 1)
        row = rows["D-390"]
        self.assertLess(REGISTER.index(row), REGISTER.index("## 운영 중 확인할 것"))
        parts = row.split("|")
        self.assertEqual(len(parts), 8)                                      # 여섯 칸
        self.assertTrue(parts[5].strip().startswith("**해결**"))
        for phrase in ("`docs/OPS_INBOX.md` §10-3", "해제하는 날의 순서 한 줄", "`pause:unset`", "`pause`", "F047", "확인 015"):
            self.assertIn(phrase, row, phrase)


if __name__ == "__main__":
    unittest.main()
