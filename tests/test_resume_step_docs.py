"""해제하는 날의 순서 한 줄(AP16 — 확인 015 의 F047)의 문서 시험 — `docs/OPS_INBOX.md` §10-3 의 새 문단이 '변수는 운영자만 지운다 · AI 는 변경을 미리 준비만 한다 · 병합은 운영자가 한다'는
규칙과, 코드가 실제로 만드는 항목 id·알림 수준·운영자 전용 병합 목록·워치독이 읽는 곳·STALE 기준 시간과 어긋나지 않는지 본다.
문장이 읽기 좋은지는 시험이 알 수 없어 사람이 본다. 여기서는 ① 문단의 자리(§10-3 안, 점검표 위치 문단 바로 아래, 표 줄이 아님) ② 필수 낱말과 규칙을 어기는 모양이 없는지
③ 문단이 말하는 사실(항목 id·알림 수준·'한 줄'이면 된다·정책 선언은 모음만 읽는다·STALE 기준)을 코드로 대조 ④ 결함 대장 행 — 을 본다.
독립 검증(2026-11-22)의 권고를 받아 더한 것: 규칙 위반 문장 검사를 'AI 가' 모양에서 '허용 문구 밖의 모든 AI 언급 금지'로 넓힘(QP-1) · 끝 절과 권유 문장을 못박고 코드와 묶음(QP-2·QP-3) ·
문단이 가리키는 규칙 문서의 표를 읽음(QP-4) · 워치독이 모음을 가져오거나 부르지 않음(QP-5) · 이 절차가 STALE 알림·빨간 실행을 막지 않는다는 한계를 결함 대장 행에 정직하게 적음(SP-2).
네트워크·실제 시계 없이 파일과 순수 함수만 쓴다. 실제 정책 파일의 선언이 켜져 있는지 꺼져 있는지에는 기대지 않는다(해제한 뒤에도 이 시험은 그대로 통과해야 한다)."""
import json
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone

import _bootstrap
from pipeline import health
from pipeline import inbox
from pipeline import inbox_policy as ip
from pipeline import registry

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402

ROOT = _bootstrap.ROOT
DOC = (ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
GUIDE = (ROOT / "docs" / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
REGISTER = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
POLICY = json.loads((ROOT / ip.POLICY_FILE).read_text(encoding="utf-8"))
RULE_DOC = (ROOT / "docs" / "AI_MERGE_POLICY.md").read_text(encoding="utf-8")        # 문단이 가리키는 규칙 문서(문서 쪽 표만 읽는다 — 그 모듈은 부르지 않는다)

LEAD = "**해제하는 날의 순서 한 줄**"
PLACE = "**해제 점검표의 위치**"
URL = "https://github.com/o/r"

# 문단에서 'AI' 가 나와도 되는 말 — 모두 '운영자만 지운다·AI 는 준비만·AI 는 병합 안 한다' 를 말하는 문구다. 이 밖의 모든 'AI' 언급은 규칙 위반으로 본다.
ALLOWED_AI_PHRASES = ("`docs/AI_MERGE_POLICY.md`", "AI 는 변수를 만지지 않습니다", "AI 가 미리 준비", "AI 는 병합하지 않습니다", "AI 병합이 켜져도")
OTHER_AGENT_WORDS = ("에이전트", "인공지능", "Claude", "Copilot", "Gemini", "코파일럿")
AUTO_WORDS = ("자동으로 지", "자동으로 해제", "자동 해제", "자동으로 끕", "자동으로 바꿉", "스스로 지", "대신 지웁", "대신 해제")
CLOSING = "새 글이 나오면 자동으로 닫힙니다"                                            # 가이드 3-9 의 끝 절과 같은 말


def stray_ai_mentions(text):
    """허용 문구를 뺀 나머지에 남은 'AI' 언급의 앞뒤 글(없으면 빈 목록) — 'AI 가'·'AI 에게'·'AI는'·'AI가' 어느 모양이든 걸린다."""
    rest = text
    for phrase in ALLOWED_AI_PHRASES:
        rest = rest.replace(phrase, "")
    return [rest[max(0, found.start() - 10):found.end() + 14] for found in re.finditer("AI", rest)]


# §10-3 안의 문단들(빈 줄로 나눈다) — 새 문단은 이 중 하나다.
_START, _END = DOC.find("### 10-3. "), DOC.find("### 10-4. ")
SECTION_3 = DOC[_START:_END] if 0 <= _START < _END else ""
PARAGRAPHS = SECTION_3.split("\n\n")
PARAGRAPH = next((text for text in PARAGRAPHS if text.startswith(LEAD)), "")

# 시험용 정지 선언(실제 정책 파일의 값과 무관) — 켠 것과, 같은 선언에서 `active` 한 칸만 끈 것.
PLANNED = {"active": True, "since": "2026-01-02", "reason": "시험용 이유", "decision_ref": "시험용 근거", "resume_conditions": ["시험용 조건 하나"], "resume_gate_passed": False}
DECLARED = ip.parse_policy({"schema_version": 1, "planned_pause": PLANNED})
TURNED_OFF = ip.parse_policy({"schema_version": 1, "planned_pause": dict(PLANNED, active=False)})

# 모음이 워치독 쪽 파일에서 쓰이는 모양(가져오기·pause_items 부르기) — 글자 planned_pause·inbox_policy 만 찾던 검사의 빈틈을 막는다.
INBOX_IMPORT = re.compile(r"(?m)^[ \t]*(?:from[ \t]+pipeline[ \t]+import[ \t]+[^#\n]*\binbox(?:_policy)?\b|(?:from|import)[ \t]+pipeline\.inbox(?:_policy)?\b)")


class FakeClient:
    """watchdog.sync_issues 가 부르는 GitHub 클라이언트의 가짜 — 부른 것만 기록한다."""

    def __init__(self):
        self.created, self.comments, self.closed, self.updated = [], [], [], []

    def create_issue(self, title, body, assignees=None):
        self.created.append(title)

    def comment(self, number, body):
        self.comments.append(number)

    def close(self, number):
        self.closed.append(number)

    def update_body(self, number, body):
        self.updated.append(number)


def one(items):
    assert len(items) == 1, [item.id for item in items]
    return items[0]


def backticked(text):
    return re.findall(r"`([^`]+)`", text)


def alert_legend():
    """OPS_INBOX 앞쪽 해설표의 {수준: 알림 칸}."""
    legend = {}
    for line in DOC.split("## 10. ")[0].splitlines():
        found = re.match(r"^\| \*\*[^|]+\*\* \(`(action|check|info)`\) \|[^|]*\| ([^|]+) \|\s*$", line)
        if found:
            legend[found.group(1)] = found.group(2).strip()
    return legend


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

    def test_every_ai_mention_is_one_of_the_allowed_phrases(self):
        """QP-1 — 규칙 위반 문장이 'AI 가' 가 아닌 말투('AI 에게 맡겨도 됩니다'·'AI는 변수를 지웁니다')나 다른 이름('에이전트가 대신 지웁니다')으로 들어와도 잡는다."""
        self.assertTrue(PARAGRAPH)
        self.assertEqual(stray_ai_mentions(PARAGRAPH), [], "허용 문구 밖의 AI 언급이 있다")
        for word in OTHER_AGENT_WORDS + AUTO_WORDS:
            self.assertNotIn(word, PARAGRAPH, word)

    def test_the_ai_mention_checker_catches_other_phrasings_and_passes_the_allowed_ones(self):
        """검사기 자체 — 규칙 위반 표본(검증자의 E1·E2 와 같은 모양 포함)은 잡고, 지금 문단의 허용 문구는 통과시킨다."""
        for sample in ("급하면 AI 에게 맡겨도 됩니다", "급하면 AI는 변수를 지웁니다", "AI가 병합합니다", "AI 도 병합합니다", "AI 에게 요청해 지웁니다", "AI 와 운영자가 함께 지웁니다"):
            self.assertTrue(stray_ai_mentions("앞 문장입니다. " + sample + ". 뒤 문장입니다."), sample)
        for sample in ("변수 `PIPELINE_PAUSE` 는 운영자만 지웁니다(AI 는 변수를 만지지 않습니다).", "변경을 AI 가 미리 준비해 두고 운영자가 병합합니다",
                       "(AI 는 병합하지 않습니다 — 이 파일은 AI 병합이 켜져도 운영자가 직접 병합하는 목록에 있습니다, `docs/AI_MERGE_POLICY.md` 7-2절 4·5번)"):
            self.assertEqual(stray_ai_mentions(sample), [], sample)

    def test_the_sources_of_the_rule_say_the_same(self):
        self.assertIn("`PIPELINE_PAUSE`(발행 정지 변수)는 운영자만 만지고 해제도 운영자만 한다", AGENTS)
        self.assertIn("이 파일은 사람이 검토하는 병합으로만 고친다(AI 가 자동으로 고치지 않는다)", POLICY["_doc"])

    def test_the_paragraph_says_the_policy_file_stays_with_the_operator_even_when_ai_merging_is_on(self):
        # 이 파일이 운영자 전용 병합 목록(승인해도 AI 가 병합하지 않는 12항목 중 발행 정지·발행 재개)에 있다는 코드 쪽 사실은 기존 시험이 못박는다.
        # 병합 정책 모듈을 가져오거나 그 모듈의 소문자 이름을 글자로 쓰는 것은 기존 NotWiredTest 가 막으므로 이 시험은 그 모듈을 부르지 않는다 —
        # 여기서는 문단이 그 사실을 말하는지만 본다(문서 쪽 표는 바로 아래 시험이 읽는다).
        self.assertIn(f"`{ip.POLICY_FILE}`", PARAGRAPH)
        self.assertIn("이 파일은 AI 병합이 켜져도 운영자가 직접 병합하는 목록에 있습니다", PARAGRAPH)

    def test_the_rule_document_the_paragraph_cites_lists_the_policy_file_in_rows_4_and_5(self):
        """QP-4 — 문단이 가리키는 '`docs/AI_MERGE_POLICY.md` 7-2절 4·5번' 을 문서 쪽에서 확인한다(코드 쪽 사실은 기존 시험이 지킨다)."""
        start = RULE_DOC.index("### 7-2. ")
        table = RULE_DOC[start:RULE_DOC.index("\n### ", start + 5)]
        self.assertIn("운영자가 직접 병합", table.splitlines()[0])
        rows = {found.group(1): found.group(0) for found in re.finditer(r"^\| (\d+) \|.*$", table, re.M)}
        self.assertEqual(sorted(rows, key=int), [str(number) for number in range(1, 13)])
        for number in ("4", "5"):
            self.assertIn(f"`{ip.POLICY_FILE}`", rows[number], f"7-2절 {number}번 줄에 정책 파일 경로가 없다")
        self.assertIn("PIPELINE_PAUSE", rows["4"])
        self.assertIn("발행 모드와 발행 재개", rows["5"])
        self.assertIn("`docs/AI_MERGE_POLICY.md` 7-2절 4·5번", PARAGRAPH)

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

    def test_the_advice_on_the_order_follows_from_the_alert_levels(self):
        """QP-3 — '알림을 줄이려면 변수를 먼저 지우고 …' 는 코드의 알림 수준에서 도출한 권유다 — 수준이 바뀌면 권유도 같이 고쳐야 하고, 거꾸로 쓰면 빨개진다."""
        unset = one(inbox.pause_items(False, URL, DECLARED))        # 변수를 먼저 지운 중간 상태
        plain = one(inbox.pause_items(True, URL, TURNED_OFF))       # 병합을 먼저 한 중간 상태
        legend = alert_legend()
        variable_first_is_quiet = legend[unset.level] == "알림 없음"
        policy_first_is_quiet = legend[plain.level] == "알림 없음"
        self.assertNotEqual(variable_first_is_quiet, policy_first_is_quiet, "한쪽만 조용해야 순서를 권할 수 있다")
        quiet = "변수를 먼저 지우고 이어서 병합하는 쪽이 낫습니다" if variable_first_is_quiet else "병합을 먼저 하고 이어서 변수를 지우는 쪽이 낫습니다"
        loud = "병합을 먼저 하고 이어서 변수를 지우는" if variable_first_is_quiet else "변수를 먼저 지우고 이어서 병합하는"
        self.assertIn("알림을 줄이려면 " + quiet, PARAGRAPH)
        self.assertNotIn(loud, PARAGRAPH)

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

    def test_the_watchdog_files_neither_import_the_inbox_nor_call_its_pause_items(self):
        """QP-5 — 글자 planned_pause·inbox_policy 가 없어도 워치독 쪽이 모음 모듈을 가져와 pause_items 를 부르면 '워치독은 읽지 않는다' 가 거짓이 된다."""
        for name in ("scripts/watchdog.py", "pipeline/health.py"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("pause_items", text, name)
            self.assertIsNone(INBOX_IMPORT.search(text), name)
        for sample in ("from pipeline import inbox as _hidden\n", "from pipeline import health, inbox_policy\n", "import pipeline.inbox as x\n", "    from pipeline.inbox import pause_items\n"):
            self.assertIsNotNone(INBOX_IMPORT.search(sample), sample)                        # 검사기 자체: 숨겨 가져오는 모양을 잡는다
        for sample in ("from pipeline import health\n", "# 이 모듈은 순수 함수라 inbox 를 가져오지 않고\n", "from pipeline.health import Finding\n"):
            self.assertIsNone(INBOX_IMPORT.search(sample), sample)

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
        watchdog_text = (ROOT / "scripts" / "watchdog.py").read_text(encoding="utf-8")
        self.assertRegex(watchdog_text, r"if new_critical and not dry:\n(?:.*\n){0,4}?\s+return 1\n")      # 새로 생긴 심각 건은 실행을 빨갛게 한다

    def test_the_closing_clause_is_the_guides_and_nothing_in_the_paragraph_says_the_opposite(self):
        """QP-2 — 문단의 끝 절이 가이드 3-9 의 뒷절과 같은 말이다. 반대로('새 글이 나와도 자동으로 닫히지 않습니다') 바꾸면 빨개진다."""
        start = GUIDE.index("### 3-9. ")
        section = GUIDE[start:GUIDE.index("### 3-10. ")]
        self.assertIn(CLOSING, section)
        self.assertIn(CLOSING + "(`docs/ACTIONS_GUIDE.md` 3-9)", PARAGRAPH)
        for opposite in ("닫히지 않", "닫지 않", "계속 열려", "그대로 열려"):
            self.assertNotIn(opposite, PARAGRAPH, opposite)

    def test_the_stale_issue_really_closes_by_itself_when_a_new_post_arrives(self):
        """QP-2 를 동작으로 — 마지막 글이 허용 시간을 넘으면 STALE 이슈가 열려 있고(닫히지 않음), 새 글이 나와 점검에 STALE 이 없으면 워치독이 열린 이슈를 닫는다."""
        chance = registry.get_blog(registry.load_registry(), "chance")
        limit = chance["health"]["max_gap_hours"] + health.WEEKLY_EXTRA_HOURS
        now = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
        stale = health.evaluate(chance, [], now, last_content_commit=now - timedelta(hours=limit, minutes=1), weekly_cap=1)
        self.assertEqual([found.code for found in stale], ["STALE"])
        open_issue = {"number": 7, "title": stale[0].title, "body": ""}
        still_open = FakeClient()
        _created, closed, _renotified, _new_critical = watchdog.sync_issues(stale, [open_issue], still_open, out=lambda text: None, owner="o", now=now)
        self.assertEqual((closed, still_open.closed), ([], []))
        fresh = health.evaluate(chance, [], now, last_content_commit=now - timedelta(hours=1), weekly_cap=1)
        self.assertEqual(fresh, [])
        resolved = FakeClient()
        _created, closed, _renotified, _new_critical = watchdog.sync_issues(fresh, [open_issue], resolved, out=lambda text: None, owner="o", now=now)
        self.assertEqual((closed, resolved.closed), ([open_issue["title"]], [7]))

    def test_without_the_weekly_mode_the_stale_limit_is_the_registry_gap(self):
        """문단의 '마지막 글 36시간' 쪽(제한 재개 잠금이 꺼진 기준)도 동작으로 묶는다 — 주 단위 가산이 꺼진 쪽에도 새면 빨개진다."""
        chance = registry.get_blog(registry.load_registry(), "chance")
        gap = chance["health"]["max_gap_hours"]
        now = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
        inside = health.evaluate(chance, [], now, last_content_commit=now - timedelta(hours=gap), weekly_cap=None)
        beyond = health.evaluate(chance, [], now, last_content_commit=now - timedelta(hours=gap, minutes=1), weekly_cap=None)
        self.assertEqual(inside, [])
        self.assertEqual([(found.code, found.severity) for found in beyond], [("STALE", "critical")])
        self.assertIn(f"마지막 글 {gap}시간", PARAGRAPH)

    def test_the_paragraph_does_not_claim_the_procedure_prevents_the_first_stale_alert(self):
        """SP-2 — 정책 선언을 끄는 절차는 모음의 항목만 줄인다. 해제 직후 첫 워치독의 STALE 알림·빨간 실행을 막는다고 쓰면 거짓이다(문단은 둘을 따로 움직인다고 쓴다)."""
        self.assertIn("워치독은 이 선언과 따로 움직입니다", PARAGRAPH)
        for claim in ("막습니다", "막아 줍니다", "막을 수", "예방", "없앱니다"):
            self.assertNotIn(claim, PARAGRAPH, claim)


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

    def test_the_register_row_says_honestly_what_the_procedure_does_not_do(self):
        """SP-2 — D-390 행(해결 계획 칸)에 '이 절차는 해제 직후 첫 워치독의 STALE 알림·빨간 실행을 막지 않는다(별도 설계)' 가 적혀 있다."""
        row = next(line for line in REGISTER.splitlines() if line.startswith("| **D-390** |"))
        plan = row.split("|")[6]
        for phrase in ("**한계**", "막지 않는다", "STALE", "빨간 실행", "별도 설계", "승인 원문"):
            self.assertIn(phrase, plan, phrase)


if __name__ == "__main__":
    unittest.main()
