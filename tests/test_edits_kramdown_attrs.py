"""위험 마크업 검사의 kramdown 속성 목록 틈(결함 D-406 — 독립 감사 BA-S1-1).

kramdown(이 사이트의 마크다운 변환기)의 인라인 속성 목록 `글{:이름="값"}` 은 `{:` 바로 뒤에서 속성이 시작할 수 있다(속성 목록 읽기가 문자열 처음과 공백을 구분자로 받는다 — 소스 기억 기준).
그래서 `**x**{:onclick="alert(1)"}` 는 `<strong onclick="alert(1)">` 가 된다. 옛 이벤트 핸들러 규칙은 `on…=` 바로 앞 글자가 공백·따옴표·슬래시일 때만 잡았고(`{:` 의 콜론은 아니다)
그 입력들이 AI 패치와 문구 그대로 바꾸기 모두에서 검사를 통과했다. 정의형 `{:이름:onclick="x"}`·`{::options …}` 꼴도 같다.
고침: 앞 글자 조건을 '속성 이름의 일부가 아닌 모든 글자'(영숫자·밑줄·하이픈이 아닌 것)로 넓혔다. 이 PC 에 Ruby 가 없어 kramdown 의 실제 출력은 확인하지 못했다 — 추정에 기대 보수적으로 막는다.
그 대가로 `?online=1` 같은 질의 문자열·`f(online=1)` 같은 코드 조각을 새로 넣는 수정도 거절한다(아래 시험이 이 한계를 적어 둔다). 개수가 늘 때만 막으므로 원문에 이미 있는 것은 그대로 둘 수 있다.
3차(검증자 Q 의 F1·N3, S 의 W1): 규칙이 셋이 되었다 — 속성 목록 `{: … }` 안만 따로 세는 규칙. 질의 문자열이 가린 바꿔 쓰기(앞글의 `?online=1` 을 지우며 `x{:onclick=…}` 를 넣기)는 이제 막힌다(옛 정답은 '통과' 였고 의도해서 뒤집었다).
따옴표 없는 값 꼴(`text{:OnClick=alert(1)}`·`{::options onclick="x" /}`)을 '막힘' 으로 단언한 곳은 kramdown 이 그 꼴을 속성으로 읽는지 렌더로 확인하지 못한(Ruby 없음) 과차단 쪽 단언이다 —
근거가 되는 한 줄 확인(`**x**{:onclick="y"}` 와 `x{:onclick=y}` 의 렌더 출력)은 렌더러가 있는 곳에서 해야 한다.
가짜 값만 쓴다.
"""
import itertools
import re
import tempfile
import time
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

# 이벤트 핸들러 규칙 둘의 기준 복사본 — 시험이 직접 적은 것이라 코드가 바뀌어도 기준이 같이 움직이지 않는다(2차, 검증자 S 의 V1).
OLD_HANDLER_RULE = re.compile(r"""[\s"'/]on[a-z]{3,}\s*=""", re.I)                  # 시작점의 규칙 그대로 — 앞 글자가 공백·따옴표·슬래시
NEW_HANDLER_RULE = re.compile(r"(?<![A-Za-z0-9_-])on[a-z]{3,}\s*=", re.I)           # D-406 의 새 규칙 — 앞 글자가 속성 이름의 일부가 아니면
IAL_HANDLER_RULE = re.compile(r"\{:[^}]{0,400}?(?<![A-Za-z0-9_-])on[a-z]{3,}\s*=", re.I)             # 3차(Q F1·S W1)의 세 번째 규칙 — 속성 목록 `{: … }` 안만 따로 센다(질의 문자열이 가릴 수 없게)


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


# 새 규칙만 세는 꼴(앞 글자가 공백·따옴표·슬래시가 아닌 `on…=`): 질의 문자열·코드 조각·속성 이름 같은 글 — 앞글에 이것이 있으면 같은 수정이 그것을 지우고 진짜 핸들러를 넣어 개수를 맞출 수 있었다
NEW_RULE_ONLY = ("/status?online=1", "f(online=1)", "?ongoing=2&x=1", "a.onboard=3", "[online=1]", "x;oncall=1", "&onready=1", "/p?ONLINE=1", "id=x,online=1", "{:onfoo=1}")
# 옛 규칙이 막던 진짜 핸들러(앞 글자가 공백·따옴표·슬래시)
OLD_RULE_HANDLERS = ("<b onclick=alert(1)>y</b>", "<img src=x onerror=alert(1)>", '<a href="#"onclick=alert(1)>x</a>', "<a/onfocus=x>", "<p ONCLICK=alert(1)>t</p>",
                     "<i" + TAB + "onmouseover=a>t</i>", "<b onclick = alert(1)>y</b>")
FRAGMENTS = (" <b onclick=alert(1)>y</b>", "/status?online=1", "(online=1)", "x{:onclick=alert(1)}", ' title="t"', '<a href="#"onfocus=z>', "?ongoing=2", " ONCLICK=1", "ordinary text")


class CountMaskingTest(unittest.TestCase):
    """검증자 S 의 V1(결함 D-406) — 개수 비교와 '바꿔 쓰기'. 새 규칙은 옛 규칙이 센 것을 모두 세지만 더 많이 센다: 옛 규칙을 새 규칙 하나로 대체하면 앞글에 새 규칙만 세는 꼴(`/status?online=1`)이 있을 때
    같은 수정이 그 꼴을 지우며 진짜 핸들러(` onclick=`)를 넣어도 개수가 늘지 않아 통과했다(옛 규칙에서는 앞글이 0 개라 막혔다 — '더 막는 쪽뿐' 이 사실이 아니었다).
    두 규칙을 따로 두고 각각 개수를 비교하면 옛 규칙이 막던 것은 항상 막히고 새 규칙은 더 막기만 한다."""

    @staticmethod
    def swap(budget, handler, ai, repeat=1):
        before = BASE + "참고 링크: " + " | ".join([budget] * repeat) + " 입니다." + NL
        after = BASE + "참고 링크: " + " | ".join([handler] * repeat) + " 입니다." + NL          # 새 규칙만 세던 꼴을 지우고 진짜 핸들러를 넣는다
        return verify(before, after, ai)

    def test_replacing_a_query_string_or_code_fragment_with_a_real_handler_is_blocked(self):
        for budget in NEW_RULE_ONLY:
            for handler in OLD_RULE_HANDLERS:
                for ai in AI_AND_PLAIN:
                    with self.subTest(budget=budget, handler=handler, ai=ai):
                        self.assertTrue(handler_reasons(self.swap(budget, handler, ai)))

    def test_several_budget_items_swapped_for_several_handlers_are_blocked(self):
        for budget in NEW_RULE_ONLY:
            for ai in AI_AND_PLAIN:
                with self.subTest(budget=budget, ai=ai):
                    self.assertTrue(handler_reasons(self.swap(budget, "<b onclick=alert(1)>y</b>", ai, repeat=3)))

    def test_the_verifiers_example_m02_is_blocked_for_ai_patches_and_plain_replacements(self):
        before = BASE + "참고 링크: /status?online=1 입니다." + NL
        after = before.replace("/status?online=1", "/status?x=1 <b onclick=alert(1)>y</b>")
        for ai in AI_AND_PLAIN:
            with self.subTest(ai=ai):
                self.assertTrue(handler_reasons(verify(before, after, ai)))

    def test_adding_a_handler_next_to_the_query_string_and_removing_the_query_string_are_both_decided_by_the_old_rule(self):
        before = BASE + "참고 링크: /status?online=1 입니다." + NL
        for ai in AI_AND_PLAIN:
            with self.subTest(ai=ai):
                self.assertTrue(handler_reasons(verify(before, before + "<b onclick=alert(1)>y</b>" + NL, ai)))            # 같은 줄이 아니라 덧붙임(m01)
                self.assertEqual(handler_reasons(verify(before, BASE, ai)), [])                                           # 지우기만 하면 막지 않는다

    BUDGETS_OUTSIDE_LISTS = tuple(budget for budget in NEW_RULE_ONLY if not budget.startswith("{:"))          # 속성 목록 밖의 꼴(질의 문자열·코드 조각 …) — 속성 목록 안의 `{:onfoo=1}` 은 속성 목록 규칙의 예산이기도 하다
    IAL_HANDLERS = ("x{:onclick=alert(1)}", '**x**{:onclick="alert(1)"}', "text{:onmouseover='a'}", '{:ref:onclick="x"}', '{:ref: onclick="x"}', 'x{:ONCLICK="a"}',
                    'x{:o&#110;click="a"}', "x{:" + NL + 'onclick="a"}', "x{::options onclick=" + chr(34) + "x" + chr(34) + " /}")

    def test_replacing_a_query_string_with_an_attribute_list_handler_is_blocked(self):
        """3차(Q F1·S W1): 새 규칙은 질의 문자열(`?online=1`)과 속성 목록 핸들러(`{:onclick=…}`)를 한 숫자로 세므로 앞글의 질의 문자열을 지우며 속성 목록 핸들러를 넣으면 개수가 같아 통과했다
        (V1 과 같은 구조 — 시작점 대비 약화는 아니지만 속성 목록은 이 묶음이 새로 막는 꼴이다). 속성 목록 `{: … }` 안만 따로 세는 규칙이 더해져 이제 막힌다. 이 시험(과 아래 모델 시험)의 옛 정답은 '통과' 였고
        의도해서 '거절' 로 뒤집었다."""
        self.assertEqual(len(self.BUDGETS_OUTSIDE_LISTS), len(NEW_RULE_ONLY) - 1)
        for budget in self.BUDGETS_OUTSIDE_LISTS:
            for handler in self.IAL_HANDLERS:
                for ai in AI_AND_PLAIN:
                    with self.subTest(budget=budget, handler=handler, ai=ai):
                        self.assertTrue(handler_reasons(self.swap(budget, handler, ai)))

    def test_several_budget_items_swapped_for_several_attribute_list_handlers_are_blocked(self):
        for budget in self.BUDGETS_OUTSIDE_LISTS:
            for ai in AI_AND_PLAIN:
                with self.subTest(budget=budget, ai=ai):
                    self.assertTrue(handler_reasons(self.swap(budget, "x{:onclick=alert(1)}", ai, repeat=3)))

    def test_the_verifiers_b2_and_b3_examples_are_blocked_for_ai_patches_and_plain_replacements(self):
        b2_before = BASE + "참고 링크: /status?online=1 입니다." + NL
        b2_after = BASE + "참고 링크: /status?x=1 x{:onclick=alert(1)} 입니다." + NL
        b3_before = BASE + "a /s?online=1 b /t?ongoing=2 c (onboard=3) d" + NL
        b3_after = BASE + "a /s?x=1 x{:onclick=1} b /t?y=2 y{:onfocus=2} c (z=3) z{:onmouseover=3} d" + NL
        for ai in AI_AND_PLAIN:
            with self.subTest(ai=ai):
                self.assertTrue(handler_reasons(verify(b2_before, b2_after, ai)))
                self.assertTrue(handler_reasons(verify(b3_before, b3_after, ai)))

    def test_plain_edits_around_the_query_string_are_still_fine(self):
        before = BASE + "참고 링크: /status?online=1 입니다." + NL
        for ai in AI_AND_PLAIN:
            with self.subTest(ai=ai):
                self.assertEqual(handler_reasons(verify(before, BASE + "참고 링크 없음" + NL, ai)), [])                      # 지우기만(B9)
                self.assertEqual(handler_reasons(verify(before, before + "새 문장입니다." + NL, ai)), [])                    # 그대로 두고 문장을 더함(B10)
                self.assertEqual(handler_reasons(verify(before, before.replace("입니다", "입니다요"), ai)), [])              # 질의 문자열 바깥만 고침
                self.assertEqual(handler_reasons(verify(before, before + "{: .lead}" + NL, ai)), [])                        # 핸들러 없는 속성 목록

    def test_a_handler_far_inside_a_long_attribute_list_is_still_blocked_by_the_old_rule_even_with_a_budget(self):
        """속성 목록 안 판정은 `{:` 에서 400자까지만 본다(`{:` 만 잔뜩인 글에서 느려지지 않게). 그 뒤의 핸들러는 앞이 공백이라 옛 규칙이 센다 — 400자 너머로 숨겨도 막힌다."""
        padded = "{:" + " .c" * 200 + ' onclick="x"}'
        before = BASE + "참고 링크: /status?online=1 입니다." + NL
        for ai in AI_AND_PLAIN:
            with self.subTest(ai=ai):
                self.assertTrue(handler_reasons(verify(before, BASE + "참고 링크: " + padded + " 입니다." + NL, ai)))

    def test_many_unclosed_attribute_list_starts_are_not_slow(self):
        """`{:` 만 만 번 되풀이한 글(닫는 `}` 없음)에서 속성 목록 규칙이 제곱 시간으로 느려지지 않는다(안쪽 탐색에 400자 상한)."""
        text = "{:" * 10000
        started = time.perf_counter()
        IAL_HANDLER_RULE.findall(text)
        for rx in (rx for name, rx in checks.DANGEROUS if "이벤트 핸들러" in name):
            rx.findall(text)
        self.assertLess(time.perf_counter() - started, 5)

    def test_the_three_rules_are_kept_apart_and_the_old_one_is_exactly_the_original(self):
        """3차: 규칙이 둘에서 셋으로 — 옛 규칙(시작점 그대로)·새 규칙(넓게 셈)·속성 목록 안만 따로 세는 규칙. 각 항목이 따로 개수를 비교한다."""
        rules = [rx for name, rx in checks.DANGEROUS if "이벤트 핸들러" in name]
        self.assertEqual(len(rules), 3)
        old = [rx for rx in rules if rx.pattern == OLD_HANDLER_RULE.pattern and rx.flags == OLD_HANDLER_RULE.flags]
        new = [rx for rx in rules if rx.pattern == NEW_HANDLER_RULE.pattern and rx.flags == NEW_HANDLER_RULE.flags]
        ial = [rx for rx in rules if rx.pattern == IAL_HANDLER_RULE.pattern and rx.flags == IAL_HANDLER_RULE.flags]
        self.assertEqual((len(old), len(new), len(ial)), (1, 1, 1))

    def test_one_reason_even_when_both_rules_count_the_same_text(self):
        for payload in (" <b onclick=alert(1)>y</b>", "x{:onclick=alert(1)}", "/status?online=1", ' <a href="#"onfocus=z>'):
            for ai in AI_AND_PLAIN:
                with self.subTest(payload=payload, ai=ai):
                    self.assertEqual(len(handler_reasons(verify(BASE, BASE + payload + NL, ai))), 1)

    def test_the_verdict_equals_the_three_rules_counted_separately_for_every_pair_of_small_edits(self):
        """앞글과 뒤글을 조각 0–2개의 모든 조합으로 만들어(2116쌍 × 두 경로) '막힘 ⇔ 옛 규칙·새 규칙·속성 목록 규칙 중 하나라도 개수가 는다' 를 확인한다 — 옛 규칙이 막던 것은 하나도 빠지지 않고(단조),
        새 규칙과 속성 목록 규칙은 따로 센다. **3차에 기대값이 의도해서 뒤집혔다**: 앞글의 `/status?online=1` 을 지우며 `x{:onclick=alert(1)}` 를 넣는 쌍은 새 규칙의 개수가 같아 옛 정답이 '통과' 였고
        (Q F1·S W1 이 이것을 정답으로 못박았다고 지적), 지금은 속성 목록 규칙이 늘어 '막힘' 이다. 기준은 위의 기준 복사본이고 엔티티 풀기는 코드의 것을 쓴다."""
        subsets = [()] + [(part,) for part in FRAGMENTS] + list(itertools.combinations(FRAGMENTS, 2))
        self.assertEqual(len(subsets), 46)

        def text(parts):
            return BASE + "".join("줄 " + part + NL for part in parts)

        old_rises_seen = new_only_seen = masked_seen = 0
        for before_parts in subsets:
            before = text(before_parts)
            decoded_before = checks._decode(before)
            for after_parts in subsets:
                after = text(after_parts)
                decoded_after = checks._decode(after)
                old_rises = len(OLD_HANDLER_RULE.findall(decoded_after)) > len(OLD_HANDLER_RULE.findall(decoded_before))
                new_rises = len(NEW_HANDLER_RULE.findall(decoded_after)) > len(NEW_HANDLER_RULE.findall(decoded_before))
                ial_rises = len(IAL_HANDLER_RULE.findall(decoded_after)) > len(IAL_HANDLER_RULE.findall(decoded_before))
                old_rises_seen += old_rises
                new_only_seen += new_rises and not old_rises
                masked_seen += ial_rises and not old_rises and not new_rises          # 속성 목록만 늘고 넓은 규칙의 개수는 그대로(앞글의 질의 문자열이 가린 것) — 옛 정답은 '통과'
                for ai in AI_AND_PLAIN:
                    got = bool(handler_reasons(verify(before, after, ai)))
                    which = "old" if old_rises else "new" if new_rises else "ial" if ial_rises else "none"
                    self.assertEqual(got, old_rises or new_rises or ial_rises, (before_parts, after_parts, ai, which))
        self.assertGreater(old_rises_seen, 300)            # 시험이 비어 있지 않다: 옛 규칙이 막는 쌍도, 새 규칙만 막는 쌍도, 속성 목록 규칙만 막는 쌍(뒤집힌 것)도 충분히 있다
        self.assertGreater(new_only_seen, 50)
        self.assertGreater(masked_seen, 10)


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
