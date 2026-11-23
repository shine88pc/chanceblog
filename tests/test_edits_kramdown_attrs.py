"""위험 마크업 검사의 kramdown 속성 목록 틈(결함 D-406 — 독립 감사 BA-S1-1).

kramdown(이 사이트의 마크다운 변환기)의 인라인 속성 목록 `글{:이름="값"}` 은 `{:` 바로 뒤에서 속성이 시작할 수 있다(속성 목록 읽기가 문자열 처음과 공백을 구분자로 받는다 — 소스 기억 기준).
그래서 `**x**{:onclick="alert(1)"}` 는 `<strong onclick="alert(1)">` 가 된다. 옛 이벤트 핸들러 규칙은 `on…=` 바로 앞 글자가 공백·따옴표·슬래시일 때만 잡았고(`{:` 의 콜론은 아니다)
그 입력들이 AI 패치와 문구 그대로 바꾸기 모두에서 검사를 통과했다. 정의형 `{:이름:onclick="x"}`·`{::options …}` 꼴도 같다.
고침: 앞 글자 조건을 '속성 이름의 일부가 아닌 모든 글자'(영숫자·밑줄·하이픈이 아닌 것)로 넓혔다. 이 PC 에 Ruby 가 없어 kramdown 의 실제 출력은 확인하지 못했다 — 추정에 기대 보수적으로 막는다.
그 대가로 `?online=1` 같은 질의 문자열·`f(online=1)` 같은 코드 조각을 새로 넣는 수정도 거절한다(아래 시험이 이 한계를 적어 둔다). 개수가 늘 때만 막으므로 원문에 이미 있는 것은 그대로 둘 수 있다.
가짜 값만 쓴다.
"""
import tempfile
import unittest

import _bootstrap  # noqa: F401
from edits_helpers import ABOUT, issue, make_edit_root, page_body
from pipeline.edits import checks
from test_edits_runner import OLD_SENTENCE, NEW_SENTENCE, RunnerBase, Snapshot, llm_returning

try:
    import yaml
except ImportError:  # pragma: no cover - CI 에는 항상 있다
    yaml = None

# 수정 흐름(러너·PR 범위 검사)은 PyYAML 이 있어야 돈다(PyYAML 이 필요합니다 오류) — 없는 환경에서는 끝에서 끝 시험만 건너뛴다. 규칙 시험(checks)은 어디서나 돈다.
NEEDS_YAML = unittest.skipUnless(yaml is not None, "수정 흐름은 PyYAML 이 있어야 돕니다(requirements-dev.txt — CI 에서는 항상 실행됩니다)")

NL, TAB = chr(10), chr(9)
LIMITS = {"max_changed_files": 1, "max_changed_lines": 80, "max_file_chars": 80000}
BASE = "안녕하세요. 소개 문장입니다." + NL + "둘째 문장입니다." + NL
AI_AND_PLAIN = (True, False)           # AI 패치와 문구 그대로 바꾸기(AI 가 아닌 교체)


def verify(before, after, ai):
    return checks.verify_changes({"about.md": (before, after)}, ["about.md"], LIMITS, ai_patch=ai)


def handler_reasons(reasons):
    return [reason for reason in reasons if "이벤트 핸들러" in reason]


def blocked(payload, before=BASE, ai=True):
    return bool(handler_reasons(verify(before, before + payload + NL, ai)))


# 옛 규칙이 놓치던 꼴 — kramdown 속성 목록(`{:` 바로 뒤, 정의 이름의 콜론 바로 뒤)
IAL_NO_SPACE = (
    '**x**{:onclick="alert(1)"}',
    'text{:onmouseover="alert(1)"}',
    "text{:onfocus='alert(1)'}",
    'text{:ONERROR="alert(1)"}',
    "text{:OnClick=alert(1)}",
    "text{:onclick=alert(1) .big}",
    '[a](/b){:onclick="x"}',
    '![i](/p.png){:onerror="x"}',
    '* item{:onload="x"}',
    '> quote{:ontoggle="x"}',
    '`code`{:onclick="x"}',
    'x{:onclick="a" onmouseover="b"}',
    'x{:oncut="x"}',                                     # 이름 뒤 글자가 3개인 핸들러(oncut·onend 처럼 가장 짧은 것)
    'x{:onend="x"}',
    'x{:onclick  =' + NL + '"x"}',                       # 이름과 등호 사이의 공백·줄바꿈
    '{:onclick="x"}',                                    # 빈 문장 뒤의 속성 목록
    'x{:onclick="x"}{:onmouseover="y"}',
    'x{:' + NL + 'onclick="x"}',                         # 속성 목록 안의 줄바꿈
)
# 정의형(`{:이름:속성…}` — 이름 뒤 콜론 바로 뒤가 속성 시작)과 `{::options …}`·확장
ALD_FORMS = (
    '{:ref:onclick="x"}',
    "{:ref:onfocus='x'}",
    '{:ref-1:onclick="x"}',
    '{:ref_2:ONCLICK="x"}',
    '{:ref:onclick="x" .a}',
    '{::options onclick="x" /}',
    '{::options onclick="x"/}',
    '{::onclick="x"}',
    '{::options auto_ids="false" onclick="x"}',
)
# 옛 규칙도 막던 꼴(공백·따옴표·슬래시 앞) — 약해지지 않았는지 지킨다
OLD_CAUGHT = (
    '**x**{: onclick="alert(1)"}',
    '{:.c onclick="x"}',
    "<p/onclick=alert(1)>x</p>",
    "<p" + TAB + "onclick=alert(1)>x</p>",
    '<a href="x"onclick="y()">x</a>',
    "<a href='x'onclick='y()'>x</a>",
    "<a href=# onfocus=alert(1) autofocus>x</a>",
    "<details open ontoggle=alert(1)>x</details>",
    "<svg onload=alert(1)>",
    '<img src=x onerror=alert(1)>',
    '<p onclick = "x">y</p>',
    "<p" + chr(12) + "onclick=x>y</p>",                  # 쪽 나눔 문자(브라우저가 공백으로 읽는다)
    "<p" + chr(0x200B) + "onclick=x>y</p>",              # 폭 없는 공백(검사가 공백으로 바꾼다)
    '<p &#111;nclick="x">y</p>',                         # 글자 참조로 쓴 이름
    '<p o&#110;click=x>y</p>',
    '<p &amp;#111;nclick=x>y</p>',                       # 겹쳐 쓴 참조
)
# 속성 이름의 일부가 아닌 글자 — 이 앞의 `onclick=` 는 새 속성으로 읽힐 수 있다(추정 기반 보수적 규칙)
BOUNDARY_CHARS = (":", "{", "(", "[", ",", ";", ".", "?", "&", "=", ">", "<", "|", "*", "!", "#", "`", "+", "%", "@", "$", "^", "}", ")", "]", chr(92), "/", '"', "'", " ", TAB, NL)
# 속성 이름의 일부인 글자 — 더 긴 이름(`data-onclick`·`x_onclick`·`monitor`)이므로 이벤트 핸들러가 아니다
NAME_CHARS = ("a", "Z", "k", "0", "9", "_", "-")
# 정상 수정에 흔한 글 — 새 거절이 없어야 한다
BENIGN = (
    "text{: .big #id}",
    "text{:#intro .lead}",
    'text{: data-x="1"}',
    'text{:data-x="1"}',
    'text{:data-onclick="1"}',                           # 이름이 data-onclick 이라 핸들러가 아니다
    'text{:x_onclick="1"}',
    'text{:title="온라인 안내"}',
    "text{:#a}",
    "{:ref: .big}",
    "{:ref:.big}",
    "{::comment}숨김 글{:/comment}",
    "condition=1 location=x position=2 person=3 button=4 reason=5 season=6 Emotion=7",
    "monitor=1 and Monitoring=2 and Python=3 and iron=4 and Kingdom=5",
    "once upon a time, online shopping is common and ongoing",
    "[x](/a?condition=1&version=3&section=2)",
    "[y](/b?season=1&reason=2)",
    "소개: 온라인(on-line) 안내입니다.",
    "on = 3, on: 4, one=5, ones=6, only=7",                # 이름 뒤 글자가 3개 미만이거나 등호가 아닌 것
    "| 항목 | 값 |" + NL + "|---|---|" + NL + "| 가 | 나 |",
)


class KramdownAttributeListTest(unittest.TestCase):
    def test_attribute_lists_with_a_handler_are_blocked_for_ai_patches_and_plain_replacements(self):
        for payload in IAL_NO_SPACE:
            for ai in AI_AND_PLAIN:
                with self.subTest(payload=payload, ai=ai):
                    self.assertTrue(blocked(payload, ai=ai))

    def test_definition_forms_and_option_extensions_are_blocked(self):
        for payload in ALD_FORMS:
            for ai in AI_AND_PLAIN:
                with self.subTest(payload=payload, ai=ai):
                    self.assertTrue(blocked(payload, ai=ai))

    def test_block_level_attribute_lines_are_blocked(self):
        """문단 바로 아래 줄의 속성 목록(블록 속성)과 표·목록 안의 속성 목록."""
        for payload in ('문단입니다.' + NL + '{:onclick="x"}', '문단입니다.' + NL + NL + '{:onmouseover="x"}', '| a | b |' + NL + '|---|---|' + NL + '| 1 | 2 |' + NL + '{:onclick="x"}',
                        '1. 하나{:onclick="x"}', '- 하나' + NL + '  {:onclick="x"}', '# 제목{:onclick="x"}', '{:ref:onclick="x"}' + NL + '문단{:ref}'):
            for ai in AI_AND_PLAIN:
                with self.subTest(payload=payload, ai=ai):
                    self.assertTrue(blocked(payload, ai=ai))

    def test_the_forms_the_old_rule_caught_are_still_caught(self):
        for payload in OLD_CAUGHT:
            for ai in AI_AND_PLAIN:
                with self.subTest(payload=payload, ai=ai):
                    self.assertTrue(blocked(payload, ai=ai))

    def test_the_reason_names_the_event_handler_rule(self):
        reasons = verify(BASE, BASE + '**x**{:onclick="alert(1)"}' + NL, False)
        self.assertEqual(len(reasons), 1, reasons)
        self.assertIn("위험한 마크업(이벤트 핸들러 속성(on…=))이 새로 들어갑니다", reasons[0])
        self.assertNotIn("alert", reasons[0])                      # 값은 사유에 되풀이하지 않는다

    def test_a_handler_hidden_by_entities_or_control_characters_is_blocked(self):
        for payload in ('x{:&#111;nclick="x"}', 'x{:o&#110;click="x"}', 'x{:&amp;#111;nclick="x"}', 'x{:&#x6f;nclick="x"}', 'x{:' + chr(12) + 'onclick="x"}'):
            for ai in AI_AND_PLAIN:
                with self.subTest(payload=payload, ai=ai):
                    self.assertTrue(blocked(payload, ai=ai))


class BoundaryTest(unittest.TestCase):
    """규칙의 경계: 이름의 일부가 아닌 글자 뒤의 `on…=` 는 막고, 더 긴 이름 안의 `on…=` 은 막지 않는다."""

    def test_a_handler_after_any_character_that_is_not_part_of_a_name_is_blocked(self):
        for char in BOUNDARY_CHARS:
            for ai in AI_AND_PLAIN:
                with self.subTest(char=repr(char), ai=ai):
                    self.assertTrue(blocked("x" + char + "onclick=1", ai=ai))

    def test_a_longer_attribute_name_is_not_a_handler(self):
        for char in NAME_CHARS:
            for ai in AI_AND_PLAIN:
                with self.subTest(char=repr(char), ai=ai):
                    self.assertFalse(blocked("x" + char + "onclick=1", ai=ai))

    def test_the_conservative_reading_also_rejects_query_strings_and_keyword_arguments(self):
        """알려진 한계(결함 D-406): 속성 이름 경계로만 읽으므로 질의 문자열·코드 조각의 `online=1` 도 새로 넣으면 거절한다 — 정상 수정이 걸리는 드문 꼴이라 보수적으로 둔다.
        완화하려면 이 시험과 결함 D-406 의 한계 칸을 함께 고친다."""
        for payload in ("[x](/search?online=1)", "[x](/a?x=1&ongoing=2)", "함수는 f(online=1) 처럼 쓴다."):
            with self.subTest(payload=payload):
                self.assertTrue(blocked(payload, ai=False))

    def test_names_after_a_boundary_need_three_letters_and_an_equals_sign(self):
        for payload in ("x on=1", "x one=1", "x only=1", "x once=1", "x on:click=1", "x onclick", "x onclick: 1", "x on click=1", "x on-click=1"):
            with self.subTest(payload=payload):
                self.assertFalse(blocked(payload, ai=False))


class NoNewRejectionsTest(unittest.TestCase):
    def test_ordinary_text_still_passes_for_ai_patches_and_plain_replacements(self):
        for payload in BENIGN:
            for ai in AI_AND_PLAIN:
                with self.subTest(payload=payload, ai=ai):
                    self.assertEqual(verify(BASE, BASE + payload + NL, ai), [])

    def test_a_handler_that_is_already_in_the_page_may_stay_but_not_grow(self):
        """개수 비교 — 원문에 이미 있는 것은 그대로 두는 수정이 막히지 않고, 하나 더 넣으면 막힌다(옛 규칙과 같은 방식)."""
        before = BASE + 'old{:onclick="x"}' + NL
        for ai in AI_AND_PLAIN:
            with self.subTest(ai=ai):
                self.assertEqual(handler_reasons(verify(before, before.replace("둘째", "셋째"), ai)), [])
                self.assertTrue(handler_reasons(verify(before, before + 'new{:onmouseover="y"}' + NL, ai)))
                self.assertTrue(handler_reasons(verify(before, before + 'old{:onclick="x"}' + NL, ai)))      # 같은 글이라도 개수가 늘면 막힌다

    def test_removing_a_handler_is_allowed(self):
        before = BASE + 'old{:onclick="x"}' + NL
        self.assertEqual(handler_reasons(verify(before, BASE, False)), [])


@NEEDS_YAML
class RunnerEndToEndTest(RunnerBase):
    """실제 수정 흐름(문구 그대로 바꾸기·AI 패치)이 속성 목록 핸들러를 파일에 쓰지 않는다."""
    LAYOUT = "layout | 섹션/레이아웃 변경 (해당 페이지 안에서만)"

    def test_literal_text_change_with_a_handler_is_rejected_and_nothing_is_written(self):
        for tail in (' **x**{:onclick="alert(1)"}', ' text{:onmouseover="alert(1)"}', '{:ref:onclick="x"}', '{::options onclick="x" /}'):
            with self.subTest(tail=tail):
                res = self.go(issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE + tail)))
                self.assertRejected(res, "이벤트 핸들러")
                self.assertEqual(self.read("about.md"), ABOUT)

    def test_ai_patch_with_a_handler_is_rejected_and_nothing_is_written(self):
        for tail in ('{:onclick="alert(1)"}', '{:onmouseover="alert(1)"}', '{:ref:onfocus="x"}'):
            with self.subTest(tail=tail):
                payload = {"patches": [{"old": "두 번째 문단입니다.", "new": "두 번째 문단입니다." + tail}]}
                res = self.go(issue(page_body(edit=self.LAYOUT, after="둘째 문단을 강조해 주세요")), llm=llm_returning(payload))
                self.assertRejected(res, "이벤트 핸들러")
                self.assertEqual(self.read("about.md"), ABOUT)

    def test_a_plain_ai_patch_still_applies(self):
        payload = {"patches": [{"old": "두 번째 문단입니다.", "new": "두 번째 문단입니다.{: .lead}"}]}
        res = self.go(issue(page_body(edit=self.LAYOUT, after="둘째 문단을 강조해 주세요")), llm=llm_returning(payload))
        self.assertEqual(res.status, "ok", res.reasons)
        self.assertIn("{: .lead}", self.read("about.md"))


@NEEDS_YAML
class ScopeCheckEndToEndTest(unittest.TestCase):
    """PR 범위 검사(같은 함수)도 속성 목록 핸들러가 든 변경을 '통과' 로 읽지 않는다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_edit_root(self._tmp.name)
        self.snap = Snapshot(self.root)

    def check(self, after_sentence):
        iss = issue(page_body(before=OLD_SENTENCE, after=after_sentence))
        return self.snap.check(self.root, iss, self.snap.head(edits={"about.md": ABOUT.replace(OLD_SENTENCE, after_sentence)}))

    def test_a_pull_request_that_adds_a_handler_is_not_a_pass(self):
        for tail in (' **x**{:onclick="alert(1)"}', ' text{:onmouseover="alert(1)"}'):
            with self.subTest(tail=tail):
                report = self.check(NEW_SENTENCE + tail)
                self.assertEqual(report.verdict, "FAIL", report.items)
                self.assertIn("이벤트 핸들러", report.markdown())

    def test_the_same_pull_request_without_the_handler_passes(self):
        report = self.check(NEW_SENTENCE)
        self.assertEqual(report.verdict, "PASS", report.items)


if __name__ == "__main__":
    unittest.main()
