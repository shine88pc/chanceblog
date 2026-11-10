"""출처 표식(pipeline/provenance.py) 시험 — 구조화 Fact 글을 AI 입력에서 빼는 표식의 읽기·쓰기 규칙. 네트워크 없이 돈다.

못박는 것: ① 표식을 읽는 규칙(정본·서식이 다른 표식·모르는 값·열리지 않는 머리말·한 줄 묶음 머리말은 모두 막는 쪽, 머리말이 없거나 본문 속 낱말은 표식이 아님)
② 쓰는 규칙(정본 한 줄·줄 끝 보존·이미 있으면 그대로)과 '생성기만 쓴다' ③ 모델이 쓴 머리말의 표식은 지운다(generator._front_matter_from_model)
④ front_matter_problems 가 모르는 값·둘 이상·모델 글의 표식을 거른다 ⑤ AI 입력을 만드는 읽기의 기본값이 '표식 글을 거름'(for_ai=True)이다.
"""
import ast
import inspect
import random
import re
import unittest
from pathlib import Path

import _bootstrap
import generator as g
from ai_flow_helpers import FACT_POSTS, fact_text, normal_text
from pipeline import provenance as P
from pipeline import state

ROOT = _bootstrap.ROOT
MARKER_WRITERS = set()          # 표식을 쓰는 (파일, 호출 이름) — 지금은 없다. 2단계가 생성기의 한 군데를 이유와 함께 올리고 docs/AI_FLOW.md 의 표도 고친다
HEADER ='---\nlayout: post\ntitle: "제목"\n{extra}---\n\n본문\n'


def doc(extra="", newline="\n"):
    return HEADER.format(extra=extra).replace("\n", newline)


class MarkOfTextTest(unittest.TestCase):
    CASES = (
        # (이름, 글, 기대 표식)
        ("정본", doc('provenance: "facts"\n'), P.MARK_FACTS),
        ("따옴표 없는 값", doc("provenance: facts\n"), P.MARK_FACTS),
        ("작은따옴표 값", doc("provenance: 'facts'\n"), P.MARK_FACTS),
        ("값 뒤 주석", doc("provenance: facts # 생성기\n"), P.MARK_FACTS),
        ("키 대소문자", doc("Provenance: facts\n"), P.MARK_FACTS),
        ("키 전부 대문자", doc("PROVENANCE: facts\n"), P.MARK_FACTS),
        ("콜론 앞 공백", doc('provenance : "facts"\n'), P.MARK_FACTS),
        ("들여쓴 줄", doc('  provenance: "facts"\n'), P.MARK_FACTS),
        ("목록 표지", doc('- provenance: facts\n'), P.MARK_FACTS),
        ("따옴표 친 키", doc('"provenance": facts\n'), P.MARK_FACTS),
        ("작은따옴표 친 키", doc("'provenance': facts\n"), P.MARK_FACTS),
        ("따옴표 친 키 첫 글자 대문자", doc('"Provenance": facts\n'), P.MARK_FACTS),
        ("작은따옴표 친 키 전부 대문자", doc("'PROVENANCE': \"facts\"\n"), P.MARK_FACTS),
        ("탭 들여쓰기", doc('\tprovenance: "facts"\n'), P.MARK_FACTS),
        ("모르는 값", doc("provenance: human\n"), P.MARK_OTHER),
        ("값 대소문자 다름", doc("provenance: Facts\n"), P.MARK_OTHER),
        ("빈 값", doc("provenance:\n"), P.MARK_OTHER),
        ("블록 글자 값", doc("provenance: >\n  facts\n"), P.MARK_OTHER),
        ("키 둘(같은 값)", doc('provenance: "facts"\nprovenance: "facts"\n'), P.MARK_OTHER),
        ("키 둘(다른 값)", doc('provenance: "facts"\nprovenance: "human"\n'), P.MARK_OTHER),
        ("표식 없음", doc(), P.MARK_NONE),
        ("제목 값 안의 낱말", '---\nlayout: post\ntitle: "Art provenance: a study"\n---\n본문\n', P.MARK_NONE),
        ("설명 값 안의 낱말", '---\nlayout: post\ndescription: "the provenance: of data"\n---\n본문\n', P.MARK_NONE),
        ("본문 속 표식 글자", '---\nlayout: post\ntitle: "x"\n---\n\nprovenance: facts\n', P.MARK_NONE),
        ("머리말 없음", "그냥 글입니다\nprovenance: facts\n", P.MARK_NO_FRONT_MATTER),
        ("빈 글", "", P.MARK_NO_FRONT_MATTER),
        ("닫는 줄 없음", '---\nlayout: post\ntitle: "x"\nprovenance: "facts"\n', P.MARK_UNKNOWN),
        ("닫는 줄 없고 표식도 없음", '---\nlayout: post\ntitle: "x"\n', P.MARK_UNKNOWN),
        ("한 줄 묶음 머리말", '---\n{title: x, provenance: facts}\n---\n본문\n', P.MARK_UNKNOWN),
        ("묶음 머리말(표식 없음)", '---\n{title: x}\n---\n본문\n', P.MARK_UNKNOWN),
        ("대괄호 줄 안의 표식 낱말", '---\ntitle: "x"\n[provenance, facts]\n---\n본문\n', P.MARK_UNKNOWN),
        ("YAML 줄바꿈 글자 U+2028", '---\ntitle: "x\u2028provenance: facts"\n---\n본문\n', P.MARK_UNKNOWN),
        ("YAML 줄바꿈 글자 U+0085", '---\ntitle: "x\u0085provenance: facts"\n---\n본문\n', P.MARK_UNKNOWN),
        ("제어 글자(BEL)", '---\ntitle: "x\x07"\n---\n본문\n', P.MARK_UNKNOWN),
        ("글 앞 BOM", "\ufeff" + doc('provenance: "facts"\n'), P.MARK_FACTS),
        ("글 앞 빈 줄", "\n\n" + doc('provenance: "facts"\n'), P.MARK_FACTS),
        ("줄 끝 CRLF", doc('provenance: "facts"\n', newline="\r\n"), P.MARK_FACTS),
        ("줄 끝 CRLF 표식 없음", doc(newline="\r\n"), P.MARK_NONE),
        # 기대값 변경(D-196): 예전에는 facts 였다. 닫는 울타리가 정확히 `---` 가 아니면 사이트 빌더와 머리말 범위가 어긋날 수 있어(여러 줄 따옴표 값 안의 `----` 줄) 이제 알 수 없음으로 읽는다. 차단은 그대로다(facts 도 unknown 도 막는다).
        ("닫는 울타리가 더 긴 대시", '---\ntitle: "x"\nprovenance: facts\n------\n본문\n', P.MARK_UNKNOWN),
        ("주석 줄 안의 표식 낱말", doc("# provenance: facts\n"), P.MARK_NONE),
        # --- D-196: 독립 검증이 찾은, YAML 이 표식으로 읽는데 예전 읽기가 통과시킨 모양 — 모두 알 수 없음(막는다) ---
        ("머리말 한 줄 안의 날 CR", "---\ntitle: x\rprovenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("복합 키 ? 와 다음 줄 :", "---\ntitle: x\n? provenance\n: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("따옴표 키 안 \\x 이스케이프", '---\ntitle: x\n"prov\\x65nance": facts\n---\n본문\n', P.MARK_UNKNOWN),
        ("따옴표 키 안 \\U 이스케이프", '---\ntitle: x\n"prov\\U00000065nance": facts\n---\n본문\n', P.MARK_UNKNOWN),
        ("앵커 붙은 키", "---\ntitle: x\n&k provenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("태그 붙은 키", "---\ntitle: x\n!!str provenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("별칭 키", "---\nk: &k provenance\n*k : facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("병합 키(묶음)", "---\ntitle: x\n<<: {provenance: facts}\n---\n본문\n", P.MARK_UNKNOWN),
        ("병합 키(별칭)", "---\nbase: &b {provenance: facts}\n<<: *b\n---\n본문\n", P.MARK_UNKNOWN),
        ("줄 머리 BOM 이 붙은 키", "---\ntitle: x\n\U0000feffprovenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("여러 줄 따옴표 값 안의 ---- 줄(울타리 어긋남)", '---\ntitle: "abc\n----\ndef"\nprovenance: facts\n---\n본문\n', P.MARK_UNKNOWN),
        ("여는 울타리가 더 긴 대시", "----\ntitle: x\nprovenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("여는 울타리 뒤 CR 과 공백(사이트는 머리말로 읽는다 — 독립 검증 2차 N1)", "---\r \nprovenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("여는 울타리 뒤 공백·CR·공백", "--- \r \nprovenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("여는 울타리 뒤 탭·CR·공백", "---\t\r \nprovenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("여는 울타리 뒤 CR·공백 둘", "---\r  \nprovenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("여는 울타리 뒤 CR·공백·CR", "---\r \r\nprovenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("여는 울타리 뒤 CR 둘·공백", "---\r\r \nprovenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("닫는 울타리 뒤 CR 과 공백", "---\nprovenance: facts\n---\r \n본문\n", P.MARK_UNKNOWN),
        ("머리말 안의 ... 줄", "---\ntitle: x\n...\nprovenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("첫 내용 줄이 들여쓰기", "---\n  title: x\n  provenance: facts\n---\n본문\n", P.MARK_UNKNOWN),
        ("0열 줄이 키도 목록도 아님", "---\ntitle: x\nprovenance facts\n---\n본문\n", P.MARK_UNKNOWN),
        # --- 대조: 흔한 정상 머리말은 그대로 표식 없음이다(거짓 양성 없음) ---
        ("0열 목록 항목", '---\nlayout: post\ntitle: "x"\ntags:\n- a\n- b\n---\n본문\n', P.MARK_NONE),
        ("들여쓴 목록 항목", '---\nlayout: post\ntitle: "x"\ntags:\n  - a\n  - b\n---\n본문\n', P.MARK_NONE),
        ("블록 글자와 빈 줄·주석", '---\nlayout: post\n\n# 설명\ndescription: |\n  첫 줄\n  둘째 줄\ntitle: "x"\n---\n본문\n', P.MARK_NONE),
    )

    def test_every_case(self):
        for name, text, expected in self.CASES:
            with self.subTest(case=name):
                self.assertEqual(P.mark_of_text(text), expected)

    def test_blocking_marks_are_exactly_marked_other_and_unknown(self):
        self.assertEqual(P.BLOCKING_MARKS, {P.MARK_FACTS, P.MARK_OTHER, P.MARK_UNKNOWN})
        for name, text, expected in self.CASES:
            with self.subTest(case=name):
                self.assertEqual(P.blocks_ai(text), expected in P.BLOCKING_MARKS)
        self.assertFalse(P.mark_blocks_ai(P.MARK_NONE))
        self.assertFalse(P.mark_blocks_ai(P.MARK_NO_FRONT_MATTER))

    def test_a_non_string_is_unknown_and_blocked(self):
        for value in (None, 123, b"---\n---\n", ["---"]):
            with self.subTest(value=value):
                self.assertEqual(P.mark_of_text(value), P.MARK_UNKNOWN)

    def test_a_header_that_never_closes_within_the_scan_limit_is_unknown(self):
        text = "---\n" + "x: y\n" * (P.HEADER_SCAN_LIMIT // 4 + 10)
        self.assertEqual(P.mark_of_text(text), P.MARK_UNKNOWN)

    def test_a_long_closed_header_is_still_read(self):
        text = "---\n" + "x: y\n" * 1000 + 'provenance: "facts"\n---\n본문\n'
        self.assertEqual(P.mark_of_text(text), P.MARK_FACTS)

    def test_the_real_synthetic_fact_post_texts_are_marked_and_their_controls_are_not(self):
        for index in range(len(FACT_POSTS)):
            self.assertEqual(P.mark_of_text(fact_text(index)), P.MARK_FACTS)
            self.assertEqual(P.mark_of_text(fact_text(index, newline="\r\n")), P.MARK_FACTS)
            self.assertEqual(P.mark_of_text(fact_text(index, marker=False)), P.MARK_NONE)
        self.assertEqual(P.mark_of_text(normal_text(0)), P.MARK_NONE)

    def test_a_file_that_cannot_be_read_or_decoded_is_unknown(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.md"
            good.write_bytes(fact_text(0).encode("utf-8"))
            bad = Path(tmp) / "bad.md"
            bad.write_bytes(b"---\ntitle: \xff\xfe\n---\n")
            self.assertEqual(P.mark_of_file(good), P.MARK_FACTS)
            self.assertEqual(P.mark_of_file(bad), P.MARK_UNKNOWN)
            self.assertEqual(P.mark_of_file(Path(tmp) / "missing.md"), P.MARK_UNKNOWN)
            self.assertEqual(P.mark_of_file(Path(tmp)), P.MARK_UNKNOWN)       # 폴더


class RandomHeaderTest(unittest.TestCase):
    """무작위 머리말(따옴표·묶음·줄바꿈 글자·제어 글자·BOM·줄 끝을 섞은 것)에 읽기·쓰기가 터지지 않고, 읽기가 '느슨한 표식 줄 탐지' 보다 약하지 않으며, 쓴 글은 반드시 정본(facts)으로 읽힌다 — 씨앗을 고정한 성질 시험."""
    TOKENS = ("title: x", "provenance: facts", 'provenance: "facts"', "Provenance:facts", "\tprovenance: facts", "- provenance: facts", "{a: b}", "[x]", "---", "...", "# c", "key: |",
              "  provenance: facts", '"provenance": facts', "'provenance': 'facts'", "provenance :facts", "provenance: facts # c", "\u2028", "\u0085", "\x00", "\x0b", "\ufeff",
              "layout: post", "tags: [a, b]", "image: x", "", "? provenance: facts", "- - provenance: facts", "provenance:", "provenance: human", "description: provenance: facts",
              'title: "provenance: facts"')
    FENCE = re.compile(r"-{3,}[ \t]*")
    LENIENT = re.compile(r"(?im)^[ \t]*(?:[-?][ \t]+)*[\"']?provenance[\"']?[ \t]*:")
    STATES = {P.MARK_NONE, P.MARK_NO_FRONT_MATTER, P.MARK_FACTS, P.MARK_OTHER, P.MARK_UNKNOWN}

    def random_text(self, rng):
        pieces = []
        if rng.random() < 0.9:
            pieces.append(rng.choice(["---", "--- ", "----", "---\t"]))
        for _ in range(rng.randint(0, 8)):
            pieces.append(rng.choice(self.TOKENS))
        if rng.random() < 0.85:
            pieces.append(rng.choice(["---", "--- "]))
        pieces.append(rng.choice(["본문", "", "provenance: facts", "---"]))
        text = rng.choice(["\n", "\r\n", "\n"]).join(pieces)
        if rng.random() < 0.1:
            text = "\ufeff" + text
        if rng.random() < 0.1:
            text = "\n\n" + text
        return text

    def header_lines(self, text):
        lines = text.lstrip("\ufeff").split("\n")
        index = 0
        while index < len(lines) and not lines[index].strip(" \t\r\x0b\x0c"):
            index += 1
        if index >= len(lines) or not self.FENCE.fullmatch(lines[index].rstrip("\r")):
            return None
        found = []
        for line in lines[index + 1:]:
            if self.FENCE.fullmatch(line.rstrip("\r")):
                break
            found.append(line.rstrip("\r"))
        return found

    def test_random_headers(self):
        rng = random.Random(20261110)
        seen = set()
        for _ in range(4000):
            text = self.random_text(rng)
            mark = P.mark_of_text(text)
            self.assertIn(mark, self.STATES, repr(text))
            seen.add(mark)
            self.assertEqual(P.blocks_ai(text), mark in P.BLOCKING_MARKS, repr(text))
            title, description = P.header_fields(text)
            self.assertTrue(isinstance(title, str) and isinstance(description, str), repr(text))
            lines = self.header_lines(text)
            if lines is not None and any(self.LENIENT.search(line) for line in lines):
                self.assertNotEqual(mark, P.MARK_NONE, "표식 줄처럼 보이는 줄이 머리말에 있는데 표식 없음으로 읽었다: " + repr(text))
            try:
                written = P.with_marker(text)
            except ValueError:
                continue
            self.assertEqual(P.mark_of_text(written), P.MARK_FACTS, "쓴 글이 정본으로 읽히지 않는다: " + repr(text))
        self.assertEqual(seen, self.STATES, "무작위 입력이 다섯 상태를 모두 만들어야 이 시험이 뜻이 있다")


class EntryAndPostTest(unittest.TestCase):
    def test_entry_marks(self):
        self.assertEqual(P.entry_mark({"kr_title": "x"}), P.MARK_NONE)
        self.assertEqual(P.entry_mark({"provenance": "facts"}), P.MARK_FACTS)
        self.assertEqual(P.entry_mark({" Provenance ": "facts"}), P.MARK_FACTS)
        self.assertEqual(P.entry_mark({"provenance": "human"}), P.MARK_OTHER)
        self.assertEqual(P.entry_mark({"provenance": None}), P.MARK_OTHER)
        self.assertEqual(P.entry_mark({"provenance": ""}), P.MARK_OTHER)
        self.assertEqual(P.entry_mark({"provenance": "facts", "PROVENANCE": "facts"}), P.MARK_OTHER)
        for item in ("그냥 문자열 항목", None, 5, ["provenance"]):
            self.assertEqual(P.entry_mark(item), P.MARK_NONE)
            self.assertFalse(P.entry_blocks_ai(item))
        self.assertTrue(P.entry_blocks_ai({"provenance": "x"}))

    def test_post_blocks_ai_reads_the_provenance_field_or_the_text(self):
        self.assertTrue(P.post_blocks_ai({"provenance": P.MARK_FACTS, "text": normal_text(0)}))
        self.assertFalse(P.post_blocks_ai({"provenance": P.MARK_NONE, "text": fact_text(0)}))       # 칸이 우선(load_posts 가 읽은 값)
        self.assertTrue(P.post_blocks_ai({"text": fact_text(0)}))
        self.assertFalse(P.post_blocks_ai({"text": normal_text(0)}))
        self.assertFalse(P.post_blocks_ai({"title": "시험용 가짜 글(text·provenance 없음)"}))
        self.assertFalse(P.post_blocks_ai("글 사전이 아님"))

    def test_entry_titles_of_lists_every_title_field(self):
        entry = {"topic": " 주제 ", "kr_title": "국문", "en_title": None, "title": "", "kr_image": "x"}
        self.assertEqual(P.entry_titles_of(entry), ["주제", "국문"])
        self.assertEqual(P.entry_titles_of("문자열"), ["문자열"])
        self.assertEqual(P.entry_titles_of(None), [])

    def test_header_fields_reads_title_and_description_loosely(self):
        text = '---\nlayout: post\ntitle: "가상 제목: 부제"\ndescription: \'설명 글\'\nprovenance: "facts"\n---\n본문\n'
        self.assertEqual(P.header_fields(text), ("가상 제목: 부제", "설명 글"))
        self.assertEqual(P.header_fields('---\ntitle: 평문 제목\n'), ("평문 제목", ""))         # 닫히지 않은 머리말에서도 읽는다
        self.assertEqual(P.header_fields("머리말 없음"), ("", ""))


class WriterTest(unittest.TestCase):
    def test_with_marker_adds_one_canonical_line_before_the_closing_fence(self):
        plain = normal_text(0)
        marked = P.with_marker(plain)
        self.assertEqual(P.mark_of_text(marked), P.MARK_FACTS)
        self.assertEqual(marked.count(P.CANONICAL_LINE), 1)
        before, after = marked.split(P.CANONICAL_LINE + "\n")
        self.assertTrue(before.endswith("\n") and after.startswith("---\n"))
        self.assertEqual(marked.replace(P.CANONICAL_LINE + "\n", ""), plain)         # 표식 줄 말고는 글자 하나 다르지 않다
        self.assertEqual(P.CANONICAL_LINE, 'provenance: "facts"')

    def test_with_marker_keeps_crlf(self):
        plain = normal_text(0, newline="\r\n")
        marked = P.with_marker(plain)
        self.assertEqual(marked.replace(P.CANONICAL_LINE + "\r\n", ""), plain)
        self.assertNotIn("\n" + P.CANONICAL_LINE + "\n", marked)
        self.assertEqual(P.mark_of_text(marked), P.MARK_FACTS)

    def test_with_marker_is_idempotent_and_refuses_unsafe_texts(self):
        marked = fact_text(0)
        self.assertEqual(P.with_marker(marked), marked)
        for bad in ("머리말 없음", '---\ntitle: "x"\n', doc("provenance: human\n"), doc('provenance: facts\nprovenance: facts\n'), '---\n{title: x}\n---\n'):
            with self.subTest(text=bad[:30]):
                with self.assertRaises(ValueError):
                    P.with_marker(bad)

    def test_with_marker_after_leading_blank_lines_and_bom(self):
        marked = P.with_marker("\ufeff\n" + normal_text(0))
        self.assertEqual(P.mark_of_text(marked), P.MARK_FACTS)

    def test_entry_with_marker(self):
        entry = {"kr_title": "제목"}
        marked = P.entry_with_marker(entry)
        self.assertEqual(marked, {"kr_title": "제목", "provenance": "facts"})
        self.assertNotIn("provenance", entry)            # 원본은 그대로
        self.assertEqual(P.entry_with_marker(marked), marked)
        with self.assertRaises(ValueError):
            P.entry_with_marker({"provenance": "human"})
        with self.assertRaises(ValueError):
            P.entry_with_marker("사전이 아님")

    def test_only_the_generator_may_write_the_marker(self):
        """표식을 쓰는 함수(with_marker·entry_with_marker)는 provenance.py 밖에서 부르지 않는다 — 지금은 부르는 곳이 0이다(2단계의 구조화 Fact 분기가 생성기 안의 한 군데로 연결한다).
        그 한 군데를 올릴 때는 MARKER_WRITERS 와 docs/AI_FLOW.md 의 '표식 쓰는 곳' 표를 같이 고친다."""
        writers = set()
        for path in sorted(list((ROOT / "pipeline").rglob("*.py")) + [ROOT / "generator.py", ROOT / "blogger_generator.py"] + sorted((ROOT / "scripts").glob("*.py"))):
            rel = path.relative_to(ROOT).as_posix()
            if rel == "pipeline/provenance.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                    if name in ("with_marker", "entry_with_marker"):
                        writers.add((rel, name))
        self.assertEqual(writers, MARKER_WRITERS)


class GeneratorIntegrationTest(unittest.TestCase):
    """생성기의 머리말 검사·모델 출력 처리가 표식을 다루는 방식."""

    IMAGE = "https://images.unsplash.com/photo-1000000000009?auto=format&fit=crop&w=1000&q=80"

    def front(self, extra=""):
        return ("---\nlayout: post\ntitle: \"제목\"\ncategory: \"예시\"\ntags: [\"예시\"]\nlang: ko\n" + f"image: \"{self.IMAGE}\"\n" + extra + "---\n\n본문입니다.\n")

    def test_front_matter_problems_flags_a_marker_by_default(self):
        self.assertEqual(g.front_matter_problems(self.front()), [])
        problems = g.front_matter_problems(self.front('provenance: "facts"\n'))
        self.assertTrue(any("provenance" in p for p in problems), problems)

    def test_front_matter_problems_accepts_exactly_one_canonical_marker_when_allowed(self):
        self.assertEqual(g.front_matter_problems(self.front('provenance: "facts"\n'), allow_provenance=True), [])
        self.assertEqual(g.front_matter_problems(self.front("provenance: facts\n"), allow_provenance=True), [])
        for bad in ('provenance: "human"\n', 'provenance: "facts"\nProvenance: "facts"\n', 'Provenance: "facts"\n', "provenance:\n", 'provenance: "Facts"\n'):
            with self.subTest(extra=bad):
                problems = g.front_matter_problems(self.front(bad), allow_provenance=True)
                self.assertTrue(any("provenance" in p or "키가 두 번" in p for p in problems), problems)

    def test_the_marker_line_is_not_allowed_to_start_a_body(self):
        content = self.front().replace("본문입니다.", "provenance: facts\n본문입니다.")
        self.assertTrue(any("머리말 줄" in p for p in g.front_matter_problems(content)))

    def test_a_marker_the_model_wrote_is_removed_from_the_header(self):
        data = {"kr_title": "제목", "kr_category": "예시", "kr_tags": ["예시"],
                "kr_content": '---\nlayout: post\ntitle: "제목"\ncategory: "예시"\ntags: ["예시"]\nprovenance: "facts"\n---\n\n본문입니다.\n'}
        content, reason = g._front_matter_from_model(data, "kr", "ko", self.IMAGE)
        self.assertIsNotNone(reason)
        self.assertEqual(P.mark_of_text(content), P.MARK_NONE)
        self.assertNotIn("provenance", content)
        self.assertEqual(g.front_matter_problems(content), [])

    def test_a_second_header_block_holding_only_a_marker_is_stripped_too(self):
        data = {"kr_title": "제목", "kr_category": "예시", "kr_tags": ["예시"],
                "kr_content": '---\nlayout: post\ntitle: "제목"\ncategory: "예시"\n---\n---\nprovenance: "facts"\n---\n\n본문입니다.\n'}
        content, reason = g._front_matter_from_model(data, "kr", "ko", self.IMAGE)
        self.assertIsNotNone(reason)
        self.assertEqual(P.mark_of_text(content), P.MARK_NONE)
        self.assertNotIn("provenance", content)

    def test_validate_post_data_never_lets_a_model_marker_through(self):
        notes = []
        for key_style in ('provenance: "facts"', "Provenance: facts", "  provenance: facts", '"provenance": facts'):
            with self.subTest(style=key_style):
                body = "본문 문장입니다. " * 220 +"\n\n근거는 [원문](https://example.invalid/a)에 있습니다.\n"
                data = {"kr_title": "제목", "kr_category": "예시", "kr_tags": ["예시"],
                        "kr_content": f'---\nlayout: post\ntitle: "제목"\ncategory: "예시"\n{key_style}\n---\n\n{body}'}
                checked = g.validate_post_data(data, "https://example.invalid/kr.jpg", None, verified_source_url="https://example.invalid/a", notes=notes, languages=("ko",))
                self.assertEqual(P.mark_of_text(checked["kr_content"]), P.MARK_NONE, checked["kr_content"][:200])
                self.assertNotIn("provenance", checked["kr_content"].lower().split("---", 2)[1])

    def test_real_posts_have_only_known_marks_and_pass_the_strict_header_check(self):
        posts = sorted((ROOT / "_posts").rglob("*.md"))
        self.assertGreater(len(posts), 10)
        for path in posts:
            text = path.read_text(encoding="utf-8")
            with self.subTest(post=path.name):
                self.assertIn(P.mark_of_text(text), (P.MARK_NONE, P.MARK_FACTS))
                problems = [p for p in g.front_matter_problems(text, allow_provenance=True) if "provenance" in p]
                self.assertEqual(problems, [])


class SafeDefaultsTest(unittest.TestCase):
    """AI 입력을 만드는 읽기의 기본값은 '표식 글을 거름'(for_ai=True)이다 — 기본이 바뀌면 사람이 읽는 길과 AI 입력 길이 뒤섞인다."""

    def test_for_ai_defaults_to_true(self):
        for function in (g.load_posts, g.existing_titles, state.entry_titles, state.other_blog_titles):
            with self.subTest(function=function.__name__):
                parameter = inspect.signature(function).parameters["for_ai"]
                self.assertIs(parameter.default, True)

    def test_for_ai_is_keyword_only_so_a_positional_flag_cannot_turn_the_filter_off(self):
        """D-197: 정적 규칙(AF6)이 못 보는 호출 모양(`load_posts(False)`·`existing_titles(history, posts, False)`)을 코드가 막는다 — 위치 인자로는 for_ai 를 넘길 수 없다."""
        for function in (g.load_posts, g.existing_titles, state.entry_titles, state.other_blog_titles):
            with self.subTest(function=function.__name__):
                self.assertIs(inspect.signature(function).parameters["for_ai"].kind, inspect.Parameter.KEYWORD_ONLY)
        with self.assertRaises(TypeError):
            g.load_posts(False)
        with self.assertRaises(TypeError):
            g.existing_titles([], [], False)
        with self.assertRaises(TypeError):
            state.entry_titles([], False)
        with self.assertRaises(TypeError):
            state.other_blog_titles(".", [], "key", False)

    def test_a_marked_post_in_a_hand_written_posts_list_is_filtered_by_existing_titles(self):
        posts = [{"title": "보통 글 제목입니다", "text": normal_text(0)}, {"title": FACT_POSTS[0]["title"], "text": fact_text(0)},
                 {"title": "표식 칸만 있는 글", "provenance": P.MARK_FACTS}]
        self.assertEqual(g.existing_titles([], posts), ["보통 글 제목입니다"])
        self.assertEqual(len(g.existing_titles([], posts, for_ai=False)), 3)


try:
    import yaml
except ImportError:      # pragma: no cover - 이 저장소 CI 는 requirements-dev.txt 로 PyYAML 을 설치한다
    yaml = None

BS = chr(92)
RUBY_SPACE = "[ \t\r\n\f\v]"      # Ruby 의 공백(파이썬 \s 는 NBSP·U+2028 등도 포함하므로 그대로 쓰면 어긋난다)
JEKYLL_RE = re.compile(r"\A(---" + RUBY_SPACE + r"*\n.*?\n?)^((?:---|\.\.\.)" + RUBY_SPACE + r"*$\n?)", re.S | re.M)      # 사이트 빌더(Jekyll)가 머리말을 자르는 정규식


def yaml_header_of_site(text):
    body = text[1:] if text.startswith(chr(0xFEFF)) else text
    found = JEKYLL_RE.match(body)
    return found.group(1) if found else None


def yaml_header_of_ours(text):
    status, lines = P._split_header(text)
    return None if status == "none" else "---\n" + "\n".join(lines) + "\n"


def yaml_reads_a_provenance_key(text):
    """사이트 빌더가 자른 머리말과 우리가 자른 머리말을 PyYAML 의 순수 로더·libyaml 로더로 읽어, 키 `provenance`(대소문자 무시)가 하나라도 있으면 그 값 목록을 돌려준다(없으면 빈 목록)."""
    found = []
    for header in (yaml_header_of_site(text), yaml_header_of_ours(text)):
        if header is None:
            continue
        for name in ("SafeLoader", "CSafeLoader"):
            loader = getattr(yaml, name, None)
            if loader is None:
                continue
            try:
                data = yaml.load(header, Loader=loader)
            except Exception:      # noqa: BLE001 - 어떤 파서 오류든 '읽지 못함' 이다(사이트도 이 글을 만들지 못한다)
                continue
            if isinstance(data, dict):
                found += [value for key, value in data.items() if isinstance(key, str) and key.lower() == "provenance"]
    return found


@unittest.skipIf(yaml is None, "PyYAML 이 없어 YAML 의 답을 구하지 못해 건너뜀 — 이 저장소 CI 는 requirements-dev.txt 로 PyYAML 을 설치한다(없는 PC 에서는 위의 손으로 만든 표 시험이 같은 모양을 막는다)")
class YamlDifferentialTest(unittest.TestCase):
    """D-196: PyYAML 이 머리말에서 `provenance` 키(대소문자 무시)를 읽는 글은 모두 차단이다 — 손으로 모은 모양 표와 씨앗을 고정한 무작위 머리말 둘 다.
    '알 수 없으면 막는다' 가 서식 차이로 빠져나가지 않는다는 말은 이 시험이 보인 범위까지만 사실이다(YAML 전체를 증명한 것이 아니다 — provenance.py 머리말)."""

    SHAPES = (
        ("정본", '---\ntitle: x\nprovenance: "facts"\n---\n본문\n'),
        ("키 대소문자·공백·탭", "---\ntitle: x\nPROVENANCE\t:\tfacts\n---\n본문\n"),
        ("따옴표 친 키", '---\ntitle: x\n"provenance": facts\n---\n본문\n'),
        ("머리말 한 줄 안의 날 CR", "---\ntitle: x\rprovenance: facts\n---\n본문\n"),
        ("복합 키", "---\ntitle: x\n? provenance\n: facts\n---\n본문\n"),
        ("복합 키(따옴표)", '---\ntitle: x\n? "provenance"\n: facts\n---\n본문\n'),
        ("\\x 이스케이프 키", '---\ntitle: x\n"prov' + BS + 'x65nance": facts\n---\n본문\n'),
        ("\\u 이스케이프 키", '---\ntitle: x\n"prov' + BS + 'u0065nance": facts\n---\n본문\n'),
        ("\\U 이스케이프 키", '---\ntitle: x\n"prov' + BS + 'U00000065nance": facts\n---\n본문\n'),
        ("줄잇기 이스케이프 키", '---\ntitle: x\n"prov' + BS + '\n  enance": facts\n---\n본문\n'),
        ("앵커 키", "---\ntitle: x\n&k provenance: facts\n---\n본문\n"),
        ("태그 키", "---\ntitle: x\n!!str provenance: facts\n---\n본문\n"),
        ("별칭 키", "---\nk: &k provenance\n*k : facts\n---\n본문\n"),
        ("병합 키(묶음)", "---\ntitle: x\n<<: {provenance: facts}\n---\n본문\n"),
        ("병합 키(별칭)", "---\nbase: &b {provenance: facts}\n<<: *b\n---\n본문\n"),
        ("병합 키(별칭 목록)", "---\na: &a {provenance: facts}\nb: &b {x: y}\n<<: [*b, *a]\n---\n본문\n"),
        ("줄 머리 BOM 키", "---\ntitle: x\n" + chr(0xFEFF) + "provenance: facts\n---\n본문\n"),
        ("여러 줄 따옴표 값 안의 ---- 줄", '---\ntitle: "abc\n----\ndef"\nprovenance: facts\n---\n본문\n'),
        ("여러 줄 따옴표 값 안의 ------ 줄", "---\ntitle: 'abc\n------\ndef'\nprovenance: facts\n---\n본문\n"),
        ("값이 이스케이프·앵커·블록", '---\ntitle: x\nprovenance: "fac' + BS + 'x74s"\n---\n본문\n'),
        ("모르는 값", "---\ntitle: x\nprovenance: human\n---\n본문\n"),
        ("한 줄 묶음 머리말", "---\n{title: x, provenance: facts}\n---\n본문\n"),
        ("목록 속 매핑", "---\n- provenance: facts\n---\n본문\n"),
        ("여는 울타리 뒤 CR 과 공백", "---\r \nprovenance: facts\n---\n본문\n"),
        ("여는 울타리 뒤 공백·CR·공백", "--- \r \nprovenance: facts\n---\n본문\n"),
        ("여는 울타리 뒤 탭·CR·공백", "---\t\r \nprovenance: facts\n---\n본문\n"),
        ("여는 울타리 뒤 CR·공백 둘", "---\r  \nprovenance: facts\n---\n본문\n"),
        ("여는 울타리 뒤 CR·공백·CR", "---\r \r\nprovenance: facts\n---\n본문\n"),
        ("여는 울타리 뒤 CR 둘·공백", "---\r\r \nprovenance: facts\n---\n본문\n"),
    )

    def test_every_hand_made_shape_that_yaml_reads_as_a_provenance_key_is_blocked(self):
        reads = 0
        for name, text in self.SHAPES:
            with self.subTest(shape=name):
                if yaml_reads_a_provenance_key(text):
                    reads += 1
                    self.assertTrue(P.blocks_ai(text), "PyYAML 은 표식 키로 읽는데 차단하지 않는다: " + repr(text))
        self.assertGreaterEqual(reads, 18, "손으로 만든 모양 가운데 PyYAML 이 표식으로 읽는 것이 너무 적다 — 이 시험이 아무것도 보지 않는 것이 아닌지 확인한다")

    def test_a_marker_free_header_that_yaml_also_reads_as_marker_free_is_not_blocked(self):
        """과차단 점검(거짓 양성): 흔한 정상 머리말은 YAML 도 표식 없음으로 읽고 우리도 막지 않는다."""
        for name, text in (("정상 한 줄 키", '---\nlayout: post\ntitle: "x"\ncategory: "예시"\ntags: ["a", "b"]\nlang: ko\nimage: "https://example.invalid/a.png"\n---\n본문\n'),
                           ("0열 목록", '---\nlayout: post\ntags:\n- a\n- b\n---\n본문\n'), ("들여쓴 목록·블록 글자", '---\nlayout: post\ntags:\n  - a\n  - b\ndescription: |\n  첫 줄\n  둘째 줄\n---\n본문\n'),
                           ("CRLF", '---\r\nlayout: post\r\ntitle: "x"\r\n---\r\n본문\r\n')):
            with self.subTest(case=name):
                self.assertEqual(yaml_reads_a_provenance_key(text), [])
                self.assertFalse(P.blocks_ai(text))

    # 무작위 머리말의 재료(독립 검증의 차분 퍼저에서 옮겨 와 줄였다). 유니코드 글자는 chr 로 만든다.
    KEY_FORMS = ("provenance", "provenance", "provenance", "Provenance", "PROVENANCE", "pRoVeNaNcE", '"provenance"', "'provenance'", '"Provenance"', "'PROVENANCE'",
                 '"prov' + BS + 'u0065nance"', '"prov' + BS + 'x65nance"', '"' + BS + 'u0070rovenance"', '"prov' + BS + 'U00000065nance"', '"prov' + BS + '\n  enance"',
                 "&k provenance", "&k  provenance", "!!str provenance", "!t provenance", "*k ", chr(0xFEFF) + "provenance", chr(0x200B) + "provenance", chr(0xFF50) + "rovenance",
                 "pr" + chr(0x043E) + "venance", "provenanc" + chr(0x0435), "provenance ", "  provenance", "\tprovenance", "? provenance\n", '? "provenance"\n', "? &k provenance\n",
                 "- provenance", "- - provenance", "? ", "<<")
    SEPARATORS = (": ", ": ", ": ", ":  ", ":\t", " : ", " :", "\t: ", ":\n  ", ":\n", ":", ":\r\n  ", ":\r  ")
    VALUES = ("facts", "facts", "facts", '"facts"', "'facts'", "Facts", '" facts "', "!!str facts", "&a facts", "*a", '"fac' + BS + 'x74s"', '"fact' + BS + 'U00000073"', "facts # c", "facts#c", '"facts" # c',
              "[facts]", "{v: facts}", chr(126), "null", "", '""', "|\n  facts", ">-\n  facts", "other", "human", "'fa''cts'", "facts" + chr(0x2028), "facts" + chr(0x85))
    OTHER_KEYS = ("layout: post", 'category: "경제·일"', 'tags: ["a", "b"]', "lang: ko", 'image: "https://example.invalid/x.png"', "tags:\n  - a\n  - b", "date: 2026-11-20", "x: &a facts", "y: *a", "# comment", "",
                  "   ", "\t", "a: |\n  provenance: facts\n  more", "meta:\n  provenance: facts", "meta: {provenance: facts}", "- provenance: facts", 'z: "multi\n  provenance: facts"',
                  "base: &b {provenance: facts}", "base2: &b2\n  provenance: facts", "<<: *b", "<<: {provenance: facts}", "<<: [*b]", "{provenance: facts}", "[provenance, facts]", "...", "---", "----", "-----",
                  'q: "abc\n----\ndef"', "q: 'abc\n------\ndef'", "q: abc\n  ----\n  def", "q: |\n  abc\n  ----\n  def", 'title: "가상 지역 가 실업률 3.5%(2026년 3월 기준)"', "title: |\n  가상 지역 나 소비자물가")
    WEIRD = ("\t", " ", "\r", chr(0x85), chr(0x2028), chr(0x2029), chr(0xFEFF), chr(0x200B), "\x0b", "\x0c", chr(0xA0), "'", '"', BS, "#", "&", "*", "!", "?", ":", "-", ",", "[", "]", "{", "}", "|", ">", "%", "@", "`", "<", "=", "\n")
    BREAKS = ("\n",) * 12 + ("\r\n", "\r", chr(0x85), chr(0x2028), chr(0x2029))
    OPEN_FENCES = ("---",) * 20 + ("--- ", "---\t", "----", "---\x0b", "---\x0c", "---" + chr(0xA0), "--- # c", "  ---", "---\r ", "--- \r ", "---\t\r ", "---\r  ", "---\r \r", "---\r\r ", "--")
    CLOSE_FENCES = ("---",) * 20 + ("--- ", "---\t", "----", "------", "...", "... ", "---\x0b", "---\x0c", "---" + chr(0xA0))
    PREFIXES = ("",) * 30 + (chr(0xFEFF), chr(0xFEFF) * 2, "\n", "\n\n", "   \n", chr(0xFEFF) + "\n", "# c\n", "x\n", chr(0xA0) + "\n", "\t\n")
    BODIES = ("body\n", "", "provenance: facts\n", "text\n---\nprovenance: facts\n---\n", "...\nprovenance: facts\n", "\n\nbody\n---\n", "a" + chr(0x85) + "b\n", "한 줄\n")

    def marker(self, rng):
        key, value = rng.choice(self.KEY_FORMS), rng.choice(self.VALUES)
        if key.endswith("? ") or key == "? ":
            return key + "provenance\n: " + value
        if key.endswith("\n"):
            return key + ": " + value
        if key.startswith("*k"):
            return "x: &k provenance\n*k " + rng.choice(self.SEPARATORS[:6]) + value
        if key == "<<":
            return "<<: {provenance: " + value + "}"
        return key + rng.choice(self.SEPARATORS) + value

    def mutate(self, rng, text):
        for _ in range(rng.randint(1, 3)):
            if not text:
                break
            pos = rng.randrange(len(text) + 1)
            roll = rng.random()
            if roll < 0.5:
                text = text[:pos] + rng.choice(self.WEIRD) + text[pos:]
            elif roll < 0.8 and pos < len(text):
                text = text[:pos] + rng.choice(self.WEIRD) + text[pos + 1:]
            elif pos < len(text):
                text = text[:pos] + text[pos + 1:]
        return text

    def document(self, rng):
        items = [self.marker(rng)] if rng.random() < 0.85 else []
        for _ in range(rng.randint(0, 6)):
            roll = rng.random()
            if roll < 0.15:
                items.append(self.marker(rng) if rng.random() < 0.5 else rng.choice(self.KEY_FORMS) + rng.choice(self.SEPARATORS) + rng.choice(self.VALUES))
            else:
                items.append(rng.choice(self.OTHER_KEYS))
        rng.shuffle(items)
        header = ""
        for index, item in enumerate(items):
            header += self.mutate(rng, item) if rng.random() < 0.10 else item
            if index < len(items) - 1:
                header += rng.choice(self.BREAKS)
        if rng.random() < 0.05:
            header = self.mutate(rng, header)
        newline = "\n" if rng.random() < 0.85 else "\r\n"
        return rng.choice(self.PREFIXES) + rng.choice(self.OPEN_FENCES) + newline + header + newline + rng.choice(self.CLOSE_FENCES) + newline + rng.choice(self.BODIES)

    def test_random_headers_that_yaml_reads_as_a_provenance_key_are_never_passed(self):
        for seed in (20261110, 7):
            rng = random.Random(seed)
            reads = passed = 0
            for _ in range(3000):
                text = self.document(rng)
                values = yaml_reads_a_provenance_key(text)
                if values:
                    reads += 1
                    self.assertTrue(P.blocks_ai(text), f"씨앗 {seed}: PyYAML 은 표식 키(값 {values!r})로 읽는데 차단하지 않는다: {text!r}")
                elif not P.blocks_ai(text):
                    passed += 1
            self.assertGreater(reads, 300, f"씨앗 {seed}: 표식으로 읽히는 무작위 글이 너무 적어 시험이 뜻이 없다")
            self.assertGreater(passed, 100, f"씨앗 {seed}: 통과하는 글이 너무 적다 — 전부 막는 것은 방어가 아니다")


if __name__ == "__main__":
    unittest.main()
