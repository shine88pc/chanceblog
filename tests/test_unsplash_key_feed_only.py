"""쓰지 않는 Unsplash 키 거르기(BP3, 감사 BP-S1-10 의 T3-2, 결함 D-430) 시험. 네트워크 없이 돈다. PyYAML 이 없어도 돈다(워크플로 글자를 직접 읽는다).

글 작성 워크플로(chanceblog.yml)와 그림자 실행 워크플로(chance-shadow.yml)의 생성기 단계는 콘텐츠 출처가 facts 이면 사진을 고르지 않는다(자체 카드 이미지) — 그런데 Unsplash 키를 늘 환경에 실었다.
Gemini 키 줄과 같은 식으로 글감 방식('콘텐츠 출처 확인' 단계의 출력)이 feed 일 때만 키를 싣고 아니면 빈 글을 싣는다(`&&` 를 `||` 보다 앞에 둔다). 키를 실제로 쓰는 다른 워크플로
(chance-fix-images.yml·issue-edit.yml·Blogger 래퍼 둘)는 그대로다. 아래 평가기는 GitHub 식의 `&&`·`||`·`==`·`!=`·`!`·괄호만 읽는 작은 것이고, 모르는 글자는 오류로 멈춘다.
"""
import re
import unittest
from pathlib import Path

import _bootstrap
from pipeline import registry

ROOT = _bootstrap.ROOT
WORKFLOWS = ROOT / ".github" / "workflows"
DOCS = ROOT / "docs"
FEED_ONLY = ("chanceblog.yml", "chance-shadow.yml")
ALWAYS_ON = ("chance-fix-images.yml", "issue-edit.yml")
WRAPPERS = ("blogger-en.yml", "blogger-ko.yml")
KEY = "UNSPLASH_ACCESS_KEY"
NEW_EXPRESSION = "steps.source.outputs.content_source == 'feed' && secrets.UNSPLASH_ACCESS_KEY || ''"
OUTPUT = "steps.source.outputs.content_source"
OUTPUTS = ("feed", "facts", "", None, "weird", "fact", "feed2", " feed", "FEED")          # 읽기 단계의 출력(없음 포함)
SECRET = "CANARY_" + "unsplash_key"                              # 가짜 비밀(시험 규칙: CANARY_ 로 시작하는 조립 문자열)
SECRETS = (SECRET, "", None)


def read(name):
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def key_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip().startswith(KEY + ":")]


def key_expression(text):
    found = re.findall(KEY + r":\s*\$\{\{\s*(.+?)\s*\}\}", text)
    assert len(found) == 1, found
    return found[0]


# ----------------------------------------------------------------------------
# GitHub 식 평가기(필요한 만큼만): 연산자는 값을 돌려주고 && 가 || 보다 먼저 묶이며, 문자열 비교는 대소문자를 가리지 않는다.
# ----------------------------------------------------------------------------
TOKEN = re.compile(r"\s*(?:('(?:[^']|'')*')|(&&|\|\||==|!=|!|\(|\))|([A-Za-z_][A-Za-z0-9_.\-]*))")


def tokenize(text):
    tokens, index = [], 0
    while text[index:].strip():
        match = TOKEN.match(text, index)
        if not match:
            raise ValueError("식을 읽을 수 없다: %r" % text[index:index + 20])
        string, operator, word = match.groups()
        tokens.append(("str", string) if string is not None else ("op", operator) if operator is not None else ("word", word))
        index = match.end()
    return tokens


def truthy(value):
    return value is not None and value is not False and value != ""


def loose_equal(left, right):
    if isinstance(left, str) and isinstance(right, str):
        return left.casefold() == right.casefold()
    return left is None and right is None


class Evaluator:
    def __init__(self, expression, context):
        self.tokens, self.index, self.context = tokenize(expression), 0, context

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        if token[0] is None:
            raise ValueError("식이 갑자기 끝났다")
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
            return {"true": True, "false": False, "null": None}[value] if value in ("true", "false", "null") else self.context.get(value)
        raise ValueError("식을 읽을 수 없다: %r" % (value,))


def evaluate(expression, **context):
    return Evaluator(expression, context).run()


def hand_over(expression, output, secret):
    """식이 키로 내보내는 값(없으면 빈 글자로 본다 — 환경 변수에는 빈 글자가 간다)."""
    value = evaluate(expression, **{OUTPUT: output, "secrets." + KEY: secret})
    return "" if value is None else value


def leaks(expression):
    """읽기 단계의 출력이 feed 가 아닌데 비밀이 나오는 조합 목록."""
    return [(output, secret) for output in OUTPUTS for secret in SECRETS
            if not (output is not None and output.casefold() == "feed") and hand_over(expression, output, secret) != ""]


class EvaluatorTest(unittest.TestCase):
    """평가기가 속이 비지 않았다: 옛 식(늘 넘김)과 흔한 틀린 식은 새는 조합이 있고, 새 식은 없다."""

    def test_the_operators_return_operands_like_github_does(self):
        self.assertEqual(evaluate("'a' && 'b' || 'c'"), "b")
        self.assertEqual(evaluate("'' && 'b' || 'c'"), "c")
        self.assertEqual(evaluate("x && 'b' || ''"), "")
        self.assertIs(evaluate("'Feed' == 'feed'"), True)
        self.assertIs(evaluate("x == 'feed'"), False)

    def test_bad_expressions_are_errors_not_guesses(self):
        for text in ("(a || b", "a ||", "&& a", "a b", "'abc", "a ? b"):
            with self.assertRaises(ValueError, msg=text):
                evaluate(text)

    def test_the_old_expression_and_common_mistakes_leak_and_the_new_one_does_not(self):
        self.assertEqual(len(leaks("secrets.UNSPLASH_ACCESS_KEY")), 7)                 # 옛 식은 늘 넘긴다: feed 가 아닌 출력 일곱 가지(키가 있을 때)가 모두 샌다
        self.assertTrue(leaks("steps.source.outputs.content_source == 'feed' || secrets.UNSPLASH_ACCESS_KEY"))                 # || 로 이으면 샌다
        self.assertTrue(leaks("steps.source.outputs.content_source != 'facts' && secrets.UNSPLASH_ACCESS_KEY || ''"))          # 열린 쪽(facts 만 막음) — 빈 값·모르는 값에서 샌다
        self.assertTrue(leaks("secrets.UNSPLASH_ACCESS_KEY || ''"))
        self.assertEqual(leaks(NEW_EXPRESSION), [])


class TheTwoWorkflowsTest(unittest.TestCase):
    def test_the_key_line_is_the_feed_only_expression_once(self):
        for name in FEED_ONLY:
            with self.subTest(workflow=name):
                text = read(name)
                self.assertEqual(key_lines(text), [KEY + ": ${{ " + NEW_EXPRESSION + " }}"])
                self.assertEqual(text.count("secrets." + KEY), 1)
                self.assertEqual(key_expression(text), NEW_EXPRESSION)

    def test_the_key_line_sits_right_under_the_gemini_key_line_that_has_the_same_clause(self):
        gemini = {"chanceblog.yml": "GEMINI_API_KEY: ${{ (github.event_name != 'workflow_dispatch' || !inputs.dry_run || inputs.real_ai) && steps.source.outputs.content_source == 'feed' && secrets.GEMINI_API_KEY || '' }}",
                  "chance-shadow.yml": "GEMINI_API_KEY: ${{ steps.source.outputs.content_source == 'feed' && secrets.GEMINI_API_KEY || '' }}"}
        for name in FEED_ONLY:
            with self.subTest(workflow=name):
                lines = [line.strip() for line in read(name).splitlines()]
                at = lines.index(gemini[name])
                self.assertTrue(lines[at + 1].startswith(KEY + ":"), lines[at + 1])
                self.assertIn("steps.source.outputs.content_source == 'feed' && ", lines[at])
                self.assertIn("steps.source.outputs.content_source == 'feed' && ", lines[at + 1])

    def test_the_source_step_runs_before_the_generator_step_and_exists_once(self):
        for name in FEED_ONLY:
            with self.subTest(workflow=name):
                text = read(name)
                self.assertEqual(len(re.findall(r"(?m)^\s+id: source\s*$", text)), 1)
                self.assertLess(re.search(r"(?m)^\s+id: source\s*$", text).start(), text.index(KEY + ":"))      # 단계 출력은 앞 단계의 것만 읽힌다

    def test_the_key_is_handed_over_only_when_the_source_is_feed(self):
        for name in FEED_ONLY:
            expression = key_expression(read(name))
            self.assertEqual(leaks(expression), [], name)
            for output in OUTPUTS:
                for secret in SECRETS:
                    with self.subTest(workflow=name, output=output, secret=secret):
                        feed = output is not None and output.casefold() == "feed"
                        self.assertEqual(hand_over(expression, output, secret), (secret or "") if feed else "")

    def test_facts_and_every_unknown_output_get_an_empty_key(self):
        for name in FEED_ONLY:
            expression = key_expression(read(name))
            for output in ("facts", "", None, "weird", "fact", "feed2", " feed"):
                self.assertEqual(hand_over(expression, output, SECRET), "", (name, output))
            self.assertEqual(hand_over(expression, "feed", SECRET), SECRET, name)

    def test_no_event_or_input_clause_was_added_so_practice_runs_still_search_unsplash_when_the_source_is_feed(self):
        """연습 실행의 입력 설명('연습도 Unsplash 이미지 검색은 실제로 합니다' — test_manual_run_defaults)이 feed 에서는 그대로 참이다: 키 식은 이벤트·입력을 보지 않는다."""
        for name in FEED_ONLY:
            expression = key_expression(read(name))
            self.assertNotIn("inputs.", expression)
            self.assertNotIn("github.", expression)
            self.assertNotIn("vars.", expression)


class TheOtherWorkflowsTest(unittest.TestCase):
    def test_the_image_fix_and_the_issue_edit_workflows_keep_the_old_expression(self):
        for name in ALWAYS_ON:
            with self.subTest(workflow=name):
                text = read(name)
                self.assertEqual(key_lines(text), [KEY + ": ${{ secrets." + KEY + " }}"])
                self.assertEqual(text.count("secrets." + KEY), 1)

    def test_the_blogger_wrappers_are_untouched(self):
        for name in WRAPPERS:
            with self.subTest(workflow=name):
                text = read(name)
                self.assertEqual(text.count("PIPELINE_SECRET_UNSPLASH_KEY: ${{ secrets." + KEY + " }}"), 1)
                self.assertEqual(text.count("secrets." + KEY), 1)

    def test_exactly_these_workflows_use_the_key(self):
        users = sorted(path.name for path in WORKFLOWS.glob("*.yml") if "secrets." + KEY in path.read_text(encoding="utf-8"))
        self.assertEqual(users, sorted(FEED_ONLY + ALWAYS_ON + WRAPPERS))

    def test_the_registry_secret_name_is_still_wired_in_the_post_workflow(self):
        """검증기 REG-3 이 보는 것: 레지스트리 블로그의 시크릿 이름이 워크플로 글자에 secrets.이름 으로 나온다(식이 바뀌어도 글자는 그대로 있다)."""
        blog = registry.get_blog(registry.load_registry(), "chance")
        self.assertEqual(blog["secrets"]["unsplash_key"], KEY)
        text = read(Path(blog["workflow"]).name)
        for env_name in blog["secrets"].values():
            self.assertIn("secrets." + env_name, text, env_name)


class DocumentTest(unittest.TestCase):
    OPS = (DOCS / "OPS_INBOX.md").read_text(encoding="utf-8")
    GUIDE = (DOCS / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")
    DEFECTS = (DOCS / "DEFECT_REGISTER.md").read_text(encoding="utf-8")

    def test_the_release_checklist_says_the_key_is_now_withheld_when_the_source_is_not_feed(self):
        line = next(item for item in self.OPS.splitlines() if item.startswith("- 참고(BP-S1-10"))
        for needle in ("Unsplash 키", "`feed` 일 때만", "`chanceblog.yml`", "`chance-shadow.yml`", "결함 D-430", "`chance-fix-images.yml`"):
            self.assertIn(needle, line, needle)
        self.assertNotIn("제안만 두었습니다", line)

    def test_the_operator_guide_says_facts_runs_do_not_carry_the_key(self):
        line = next(item for item in self.GUIDE.splitlines() if item.startswith("`UNSPLASH_ACCESS_KEY`가 만료·오류면"))
        for needle in ("콘텐츠 출처가 facts 이면 글 작성·그림자 실행 워크플로가 이 키를 환경에 싣지 않습니다", "결함 D-430"):
            self.assertIn(needle, line, needle)

    def test_the_defect_row_d430_exists_once_with_six_cells_and_is_solved(self):
        rows = [line for line in self.DEFECTS.splitlines() if line.startswith("| **D-430** |")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].count("|"), 7)
        self.assertIn("**해결**", rows[0])
        for needle in ("BP-S1-10", "chanceblog.yml", "chance-shadow.yml", "chance-fix-images.yml", "tests/test_unsplash_key_feed_only.py", "확인 032"):
            self.assertIn(needle, rows[0], needle)

    def test_the_new_text_has_no_tilde_and_no_link(self):
        for text in (self.OPS, self.GUIDE, self.DEFECTS):
            for line in text.splitlines():
                if "D-430" in line or "BP-S1-10" in line:
                    self.assertNotIn(chr(126), line)
                    self.assertIsNone(re.search(r"https?://", line))


if __name__ == "__main__":
    unittest.main()
