"""워크플로 `if`·`run-name` 식을 GitHub 규칙대로 계산하는 작은 해석기(시험 전용, 네트워크·GitHub 없음).

`.github/workflows/*.yml` 의 `${{ … }}` 식이 이벤트마다 무엇이 되는지(어느 job 이 돌고 어느 job 이 건너뛰어지는지)를 시험이 직접 계산해 보려고 쓴다.
원래 tests/test_ops_inbox_drafts.py 안에 있던 것을 옮겼고(그 시험은 `Expr as _Expr` 로 그대로 쓴다) `startsWith()`·`endsWith()` 를 더했다
(PR 검사 범위 확인 워크플로의 AI 브랜치 건너뛰기 조건이 쓴다). 식이 이 해석기가 모르는 모양이면 조용히 틀린 값을 내지 않고 오류를 낸다 — 식이 바뀌면 이 해석기와 시험을 함께 고친다.
"""
import re


class Expr:
    """워크플로 job `if` 식(`||`·`&&`·`==`·`!=`·`!`·괄호·문자열·`contains()`·`startsWith()`·`endsWith()`·`a.b.*.c` 참조)을 GitHub 규칙대로 계산하는 작은 해석기."""
    TOKEN = re.compile(r"\s*(?:(?P<op>\|\||&&|==|!=|[(),!])|'(?P<str>(?:[^']|'')*)'|(?P<id>[A-Za-z_][A-Za-z0-9_.*\-]*))")

    def __init__(self, source, context):
        self.tokens, pos, src = [], 0, source.strip()
        while pos < len(src):
            match = self.TOKEN.match(src, pos)
            if not match:
                raise ValueError(f"읽을 수 없는 식: {src[pos:pos + 30]!r}")
            pos = match.end()
            if match.group("op"):
                self.tokens.append(("op", match.group("op")))
            elif match.group("str") is not None:
                self.tokens.append(("val", match.group("str").replace("''", "'")))
            else:
                self.tokens.append(("id", match.group("id")))
        self.i, self.context = 0, context

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        self.i += 1
        return token

    @staticmethod
    def as_text(value):
        return "" if value is None else "true" if value is True else "false" if value is False else str(value)

    @staticmethod
    def truthy(value):
        return not (value is None or value is False or value == 0 or value == "" or value == [])

    def parse(self):
        value = self.or_()
        if self.i != len(self.tokens):
            raise ValueError("식 끝에 남은 토큰이 있습니다")
        return value

    def or_(self):
        value = self.and_()
        while self.peek() == ("op", "||"):
            self.take()
            right = self.and_()
            value = value if self.truthy(value) else right
        return value

    def and_(self):
        value = self.eq()
        while self.peek() == ("op", "&&"):
            self.take()
            right = self.eq()
            value = right if self.truthy(value) else value
        return value

    def eq(self):
        value = self.unary()
        while self.peek() in (("op", "=="), ("op", "!=")):
            op = self.take()[1]
            right = self.unary()
            same = value.casefold() == right.casefold() if isinstance(value, str) and isinstance(right, str) else value == right
            value = same if op == "==" else not same
        return value

    def unary(self):
        if self.peek() == ("op", "!"):
            self.take()
            return not self.truthy(self.unary())
        return self.primary()

    def primary(self):
        kind, text = self.take()
        if (kind, text) == ("op", "("):
            value = self.or_()
            assert self.take() == ("op", ")")
            return value
        if kind == "val":
            return text
        if kind == "id" and self.peek() == ("op", "("):
            self.take()
            args = [self.or_()]
            while self.peek() == ("op", ","):
                self.take()
                args.append(self.or_())
            assert self.take() == ("op", ")")
            assert text in ("contains", "startsWith", "endsWith"), text
            haystack, needle = args
            if text in ("startsWith", "endsWith"):                  # 문자열로 바꿔(null 은 빈 문자열) 대소문자 구분 없이 견준다 — GitHub 규칙
                whole, part = self.as_text(haystack).casefold(), self.as_text(needle).casefold()
                return whole.startswith(part) if text == "startsWith" else whole.endswith(part)
            if isinstance(haystack, list):
                return any(isinstance(item, str) and isinstance(needle, str) and item.casefold() == needle.casefold() for item in haystack)
            return isinstance(haystack, str) and isinstance(needle, str) and needle.casefold() in haystack.casefold()
        if kind == "id":
            return {"true": True, "false": False, "null": None}[text] if text in ("true", "false", "null") else self.lookup(text)
        raise ValueError(f"예상하지 못한 토큰 {kind} {text}")

    def lookup(self, path):
        nodes = [self.context]
        for part in path.split("."):
            nxt = []
            for node in nodes:
                if part == "*":
                    nxt += node if isinstance(node, list) else []
                elif isinstance(node, dict):
                    nxt.append(node.get(part))
                else:
                    nxt.append(None)
            nodes = nxt
        return nodes if ".*." in path else (nodes[0] if nodes else None)
