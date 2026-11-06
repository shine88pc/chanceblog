"""알림 번호 도구(인수인계/도구/work/next_notice_no.py·notice_tools.py·make_request.py)와 문서 사본 3개의 시험(TG-STD, 운영자 승인 2026-11-06 계획 R-165).

핵심: ① 번호 읽기·판정·다음 번호는 git 없이 표로 못박고 pipeline/notify.py 의 판정과 짧은 글 전수로 맞춰 본다 ② git 읽기는 가짜 git 으로 오류 경로까지, 진짜 git 은 임시 저장소 하나로만 시험한다
(원격 가지는 `refs/remotes/origin/…` 로 흉내 — 이 컴퓨터는 git 한 번이 0.3초라 저장소는 한 번만 만든다) ③ make_request.py 는 main() 으로 불러 가짜 검사 관문으로 시험한다
④ 본보기 문서의 앞머리는 진짜 읽기 규칙(operator_loop.parse_request strict)이 읽는다. 네트워크·실제 GitHub·실제 텔레그램은 없다.
"""
import ast
import contextlib
import importlib.util
import io
import itertools
import random
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap
import notice_helpers as nth
import notify_helpers as nh
from pipeline import llm, notify, secret_patterns
from pipeline import operator_loop as ol
from pipeline.console import INVISIBLE_CODEPOINTS

ROOT = _bootstrap.ROOT
TOOLS = ROOT / "인수인계" / "도구"
WORK = TOOLS / "work"
sys.path.insert(0, str(WORK))
import make_request  # noqa: E402
import next_notice_no as nn  # noqa: E402
import notice_tools as nt  # noqa: E402

BOM = chr(0xFEFF)
ZWSP = chr(0x200B)
FOLDER = "인수인계/요청함"
PR_TITLE = "[R-170] 알림 번호 도구 \"P012\" & 'M007' <b> — 끝 [대상: 공통]"
REMOTE_TITLE = "[R-171] 원격에만 있는 가지 [대상: 공통]"


def fm(*lines, body="본문\n"):
    """요청 파일 글: 앞머리(`---` 사이의 줄들)와 본문."""
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def long_front(no_line, closing_line):
    """닫는 `---` 가 closing_line(1 부터 센 줄 번호)번째 줄에 오는 글 — 2번째 줄이 no_line 이고 나머지는 채움 줄이다."""
    fillers = [f"k{index}: v" for index in range(closing_line - 3)]
    return "\n".join(["---", no_line, *fillers, "---"]) + "\n본문\n"


def scan_result(progress=0, merge=0, ask=0, source="R-100_x.md @ origin/main"):
    return {kind: (value, source if value else "") for kind, value in (("progress", progress), ("merge", merge), ("ask", ask))}


# ==== 순수 계산 =================================================================================
class FrontMatterTest(unittest.TestCase):
    CASES = (
        ("평범한 번호", "---\nid: R-170\nno: P012\n---\n본문\n", ["P012"]),
        ("큰따옴표", '---\nno: "003"\n---\n', ["003"]),
        ("작은따옴표", "---\nno: '003'\n---\n", ["003"]),
        ("짝이 안 맞는 따옴표는 벗기지 않는다", '---\nno: "003\n---\n', ['"003']),
        ("콜론 앞 공백", "---\nno : P012\n---\n", ["P012"]),
        ("콜론 뒤 공백 없음", "---\nno:P012\n---\n", ["P012"]),
        ("탭과 뒤 공백", "---\nno:\tP012  \n---\n", ["P012"]),
        ("맨 앞 BOM", BOM + "---\nno: P012\n---\n", ["P012"]),
        ("CRLF", "---\r\nno: P012\r\n---\r\n본문\r\n", ["P012"]),
        ("여닫는 줄 뒤의 공백", "---  \nno: P012\n---   \n", ["P012"]),
        ("본문의 no 는 세지 않는다", "---\nid: x\n---\nno: P050\n", []),
        ("본문의 두 번째 앞머리 모양도 세지 않는다", "---\nno: P012\n---\n본문\n---\nno: P099\n---\n", ["P012"]),
        ("앞머리가 없다", "no: P012\n", []),
        ("첫 줄이 비었다", "\n---\nno: P012\n---\n", []),
        ("닫지 않은 앞머리", "---\nno: P012\n", []),
        ("들여쓴 줄", "---\n no: P012\n---\n", []),
        ("다른 키", "---\nNo: P012\nnotice_no: P012\nno_x: P012\nxno: P012\n---\n", []),
        ("빈 값", "---\nno:\n---\n", [""]),
        ("주석과 빈 줄은 건너뛴다", "---\n# no: P012\n\nno: P013\n---\n", ["P013"]),
        ("같은 키가 둘이면 둘 다 본다", "---\nno: P012\nno: M003\n---\n", ["P012", "M003"]),
        ("줄 끝 주석은 값의 일부다", "---\nno: P012 # c\n---\n", ["P012 # c"]),
        ("빈 글", "", []),
    )

    def test_front_values_table(self):
        for label, text, expected in self.CASES:
            self.assertEqual(nn.front_values(text), expected, label)

    def test_only_valid_numbers_are_counted(self):
        text = "---\nno: P012\nno: p013\nno: M0\nno: 004\n---\n"
        self.assertEqual(nn.front_numbers(text), [("progress", 12), ("ask", 4)])

    def test_the_closing_line_may_be_the_41st_line_like_the_real_parser(self):
        for closing_line, counted in ((41, True), (42, False)):
            text = long_front("no: P011", closing_line)
            self.assertEqual(text.count("\n") - 1, closing_line, closing_line)           # 본문 한 줄을 뺀 줄 수 = 닫는 줄 번호
            self.assertEqual(nn.front_numbers(text), [("progress", 11)] if counted else [], closing_line)
            try:
                ol.parse_request("R-170_x.md", text)               # id 가 없어 다른 문제가 나올 수 있다 — 닫는 줄을 찾았는지만 본다
                code = ""
            except ol.RequestError as exc:
                code = exc.code
            self.assertEqual(code == "unclosed", not counted, (closing_line, code))

    def test_real_request_files_give_the_number_the_parser_reads(self):
        for number, no in ((170, "P012"), (171, "M007"), (172, "003"), (173, "P1000"), (174, "1234")):
            text = nth.notice_text(number=number, no=no)
            request = ol.parse_request(nth.name_of(number), text, strict=True)
            self.assertEqual(request.no, no)
            self.assertEqual(nn.front_numbers(text), [nn.parse_no(no)], no)
        quoted = nth.notice_text(number=172, no="003").replace("no: 003", 'no: "003"')
        self.assertEqual(ol.parse_request(nth.name_of(172), quoted, strict=True).no, "003")
        self.assertEqual(nn.front_numbers(quoted), [("ask", 3)])


class NumberJudgmentTest(unittest.TestCase):
    VALID = (("P001", "progress", 1), ("P012", "progress", 12), ("P999", "progress", 999), ("P1000", "progress", 1000), ("P9999", "progress", 9999),
             ("M001", "merge", 1), ("M007", "merge", 7), ("M1234", "merge", 1234), ("001", "ask", 1), ("003", "ask", 3), ("999", "ask", 999),
             ("1000", "ask", 1000), ("9999", "ask", 9999), ("P0999", "progress", 999), ("0012", "ask", 12))
    INVALID = ("", "P", "M", "P1", "P12", "M12", "12", "1", "0", "00", "P000", "M000", "000", "0000", "P0000", "P00000", "10000", "P10000", "p001", "m001", "PM001",
               "P-001", "P 001", " 001", "001 ", "001\n", "\n001", "P001\n", "001.", "#001", "R-001", "r001", "P00a", "00a", "A001", "001-", "P001x", "０１２", "P０１２",
               "①②③", "P①②③", "٠٠١", "0" + ZWSP + "01", ZWSP + "001", BOM + "001", "0 01", "001001", None, 1, 12.0, b"001", ("001",))

    def test_valid_numbers(self):
        for text, kind, number in self.VALID:
            self.assertEqual(nn.parse_no(text), (kind, number), text)

    def test_everything_else_is_not_a_number(self):
        for text in self.INVALID:
            self.assertIsNone(nn.parse_no(text), repr(text))

    def test_every_short_text_agrees_with_the_pipeline(self):
        """길이 4 이하 글 전수(글자 10종)와 길이 5 의 일부를 pipeline/notify.py 의 판정(notice_type·notice_number)과 하나씩 맞춰 본다.
        파이프라인이 번호로 받는 글은 도구도 같은 (유형, 순번)으로 읽고, 파이프라인이 받지 않는 글 중 도구가 읽는 것은 **일부러 더 넓게 읽는 한 가지**(앞 0 이 붙은 네 자리 `P0012`·`0003` — 수정 1차)뿐이다."""
        lenient = re.compile(r"[PM]?0[0-9]{3}")
        extra = []

        def check(text):
            want = (notify.notice_type(text), notify.notice_number(text))
            got = nn.parse_no(text) or ("", 0)
            if want != ("", 0):
                self.assertEqual(got, want, repr(text))
            elif got != ("", 0):
                self.assertIsNotNone(lenient.fullmatch(text), repr(text))
                extra.append(text)
        alphabet = ["P", "M", "p", "0", "1", "９", "①", " ", "\n", "-"]
        for length in range(5):
            for chars in itertools.product(alphabet, repeat=length):
                check("".join(chars))
        for chars in itertools.product(["P", "0", "1", "\n", " "], repeat=5):
            check("".join(chars))
        self.assertIn("0011", extra)                                         # 관용 읽기가 실제로 있다(전수 표본에 앞 0 네 자리가 들어 있다)
        self.assertEqual(sorted(extra), sorted({f"0{a}{b}{c}" for a, b, c in itertools.product("01", repeat=3)} - {"0000"} | {f"P0{a}{b}{c}" for a, b, c in itertools.product("01", repeat=3)} - {"P0000"}))

    def test_the_tool_reads_zero_padded_old_texts_so_it_never_picks_a_number_that_is_in_use_but_the_pipeline_refuses_them(self):
        """읽기는 넓다(더 많이 세는 쪽이 안전): 가지에 남은 `P0012` 도 12 로 세므로 다음 번호가 그 번호를 피한다. 그러나 파이프라인은 이 글을 번호로 받지 않는다(검증기 REQ-1 이 거절)."""
        for text, kind, number in (("P0012", "progress", 12), ("M0007", "merge", 7), ("0003", "ask", 3), ("P0999", "progress", 999)):
            self.assertEqual(nn.parse_no(text), (kind, number), text)
            self.assertEqual(notify.notice_type(text), "", text)
        result = scan_result(12, 7, 3)
        self.assertEqual(nn.next_numbers(result), {"progress": "P013", "merge": "M008", "ask": "004"})

    def test_the_numbers_the_tool_makes_are_always_the_standard_spelling_the_pipeline_accepts(self):
        """만들 때는 늘 표준 표기 — 1..9999 × 3유형 전부 `format_no` 의 글이 파이프라인의 번호이고 같은 (유형, 순번)으로 읽힌다."""
        for kind in nn.KINDS:
            for number in range(1, 10000):
                text = nn.format_no(kind, number)
                self.assertEqual(text, notify.notice_no_text(kind, number), (kind, number))
                self.assertEqual((notify.notice_type(text), notify.notice_number(text)), (kind, number), text)
                self.assertEqual(nn.parse_no(text), (kind, number), text)

    def test_format_no_matches_the_pipeline_and_refuses_what_it_refuses(self):
        for kind in nn.KINDS:
            for number in (1, 2, 9, 10, 12, 99, 100, 998, 999, 1000, 1001, 9998, 9999):
                self.assertEqual(nn.format_no(kind, number), notify.notice_no_text(kind, number), (kind, number))
        self.assertEqual([nn.format_no("progress", n) for n in (1, 999, 1000)], ["P001", "P999", "P1000"])
        self.assertEqual([nn.format_no("ask", n) for n in (1, 999, 1000)], ["001", "999", "1000"])
        for kind, number in (("progress", 0), ("progress", 10000), ("merge", -1), ("ask", 0), ("ask", True), ("ask", 1.5), ("ask", "1"), ("note", 1), ("", 1), (None, 1)):
            with self.assertRaises(ValueError, msg=(kind, number)):
                nn.format_no(kind, number)


class NextNumbersTest(unittest.TestCase):
    def test_empty_state_starts_each_type_at_one(self):
        self.assertEqual(nn.next_numbers(scan_result()), {"progress": "P001", "merge": "M001", "ask": "001"})

    def test_maximum_plus_one_and_the_three_types_are_independent(self):
        self.assertEqual(nn.next_numbers(scan_result(11, 4, 7)), {"progress": "P012", "merge": "M005", "ask": "008"})
        self.assertEqual(nn.next_numbers(scan_result(5, 0, 0)), {"progress": "P006", "merge": "M001", "ask": "001"})
        self.assertEqual(nn.next_numbers(scan_result(0, 2, 0)), {"progress": "P001", "merge": "M003", "ask": "001"})
        self.assertEqual(nn.next_numbers(scan_result(0, 0, 9)), {"progress": "P001", "merge": "M001", "ask": "010"})

    def test_three_digits_become_four_after_999_and_there_is_no_000(self):
        self.assertEqual(nn.next_numbers(scan_result(998, 998, 998)), {"progress": "P999", "merge": "M999", "ask": "999"})
        self.assertEqual(nn.next_numbers(scan_result(999, 999, 999)), {"progress": "P1000", "merge": "M1000", "ask": "1000"})
        self.assertEqual(nn.next_numbers(scan_result(9998, 9998, 9998)), {"progress": "P9999", "merge": "M9999", "ask": "9999"})
        for kind in nn.KINDS:
            self.assertNotIn("000", nn.next_numbers(scan_result())[kind])

    def test_9999_stops_with_an_error_only_for_the_exhausted_type(self):
        result = scan_result(9999, 3, 3)
        with self.assertRaises(nn.NumberExhausted) as caught:
            nn.next_numbers(result)
        self.assertIn("P 번호가 상한 9999", str(caught.exception))
        with self.assertRaises(nn.NumberExhausted):
            nn.next_number(result, "progress")
        self.assertEqual(nn.next_number(result, "merge"), "M004")
        self.assertEqual(nn.next_number(result, "ask"), "004")
        with self.assertRaises(nn.NumberExhausted):
            nn.next_number(scan_result(0, 0, 9999), "ask")
        self.assertTrue(issubclass(nn.NumberExhausted, ValueError))

    def test_fold_keeps_the_largest_and_the_first_source_on_a_tie(self):
        best = {kind: (0, "") for kind in nn.KINDS}
        nn.fold(best, "R-1_a.md", "origin/main", [("progress", 3), ("merge", 2)])
        nn.fold(best, "R-2_b.md", "origin/ai/x", [("progress", 3), ("merge", 5), ("ask", 1)])
        nn.fold(best, "R-3_c.md", "origin/ai/y", [("progress", 2), ("progress", 4)])
        nn.fold(best, "R-4_d.md", "origin/ai/z", [])
        self.assertEqual(best, {"progress": (4, "R-3_c.md @ origin/ai/y"), "merge": (5, "R-2_b.md @ origin/ai/x"), "ask": (1, "R-2_b.md @ origin/ai/x")})
        nn.fold(best, "R-5_e.md", "origin/ai/w", [("progress", 4)])
        self.assertEqual(best["progress"], (4, "R-3_c.md @ origin/ai/y"))

    def test_describe_lines(self):
        result = {"progress": (11, "R-168_progress-p011.md @ origin/main"), "merge": (0, ""), "ask": (7, "R-170_ask.md @ origin/ai/codex/y")}
        self.assertEqual(nn.describe(result, "progress", "P012"), "P 다음 번호: P012 (지금 최댓값 P011 — R-168_progress-p011.md @ origin/main)")
        self.assertEqual(nn.describe(result, "merge", "M001"), "M 다음 번호: M001 (아직 없음)")
        self.assertEqual(nn.describe(result, "ask", "008"), "확인 다음 번호: 008 (지금 최댓값 007 — R-170_ask.md @ origin/ai/codex/y)")
        self.assertEqual(nn.describe(scan_result(), "ask", "001"), "확인 다음 번호: 001 (아직 없음)")


class ConstantsMatchThePipelineTest(unittest.TestCase):
    """도구는 pipeline 을 불러 쓰지 않는 사본이라(작업 폴더 W 에는 pipeline 이 없다) 값이 어긋나지 않는지 여기서 비교한다."""

    def test_number_shapes_and_the_front_matter_rules(self):
        self.assertEqual(nt.STRICT_NO_RE.pattern, notify.NOTICE_NO_RE.pattern)           # 만들 때의 표준 표기(앞 0 없음)는 파이프라인과 같다
        self.assertEqual(nn.NO_RE.pattern, "[PM][0-9]{3,4}|[0-9]{3,4}")                  # 읽기는 일부러 더 넓다(앞 0 이 붙은 옛 글도 센다) — 아래 NumberJudgmentTest 가 그 차이가 이 한 가지뿐임을 확인한다
        self.assertEqual(nn.NO_MAX, notify.NOTICE_NO_MAX)
        self.assertEqual({kind: nn.PREFIX[kind] for kind in nn.KINDS}, {notify.NOTICE_PROGRESS: "P", notify.NOTICE_MERGE: "M", notify.NOTICE_ASK: ""})
        self.assertEqual(set(nn.KINDS), set(notify.NOTICE_LABELS))
        self.assertEqual((nn.KEY_LINE_RE.pattern, nn.FRONT_LINES, nn.REQUEST_DIR), (ol._KEY_LINE_RE.pattern, ol.MAX_FRONT_LINES, ol.REQUEST_DIR))
        for raw in ('"x"', "'x'", '"x', "x'", '"', "''", "", "x", "\"x'", "'x\""):
            self.assertEqual(nn.unquote(raw), ol._unquote(raw), raw)

    def test_request_file_names(self):
        names = ("R-001_a.md", "R-170_progress-p012.md", "R-170_a-b-c.md", "R-17_a.md", "R-1700_a.md", "r-170_a.md", "R-170_A.md", "R-170_a_b.md", "R-170_a--b.md", "R-170_-a.md",
                 "R-170_a-.md", "R-170_한글.md", "R-170_a.txt", "R-170_a.md.bak", "README.md", "R-170.md", " R-170_a.md", "R-170_a.md\n", "R-170_" + "a" * 60 + ".md")
        for name in names:
            self.assertEqual(nn.NAME_RE.fullmatch(name) is not None, ol.REQUEST_NAME_RE.fullmatch(name) is not None, name)

    def test_kinds_limits_and_the_pr_title_rules(self):
        self.assertEqual(nt.NOTICE_TYPE_OF_KIND, notify.NOTICE_KIND_TYPES)
        self.assertEqual({key: nt.LIMITS[key] for key in ol.NOTICE_LIMITS}, ol.NOTICE_LIMITS)
        self.assertEqual((nt.LIMITS["title"], nt.LIMITS["summary"], nt.LIMITS["pr_title"]), (ol.TITLE_MAX, ol.SUMMARY_MAX, notify.PR_TITLE_LIMIT))
        self.assertEqual(set(nt.LIMITS), {"title", "summary", "pr_title", *ol.NOTICE_LIMITS})
        self.assertEqual((nt.OPTION_LIMIT, nt.OPTION_SEPARATOR), (notify.OPTION_LIMIT, notify.OPTION_SEPARATOR))
        self.assertEqual(nt.INVISIBLE_CODEPOINTS, INVISIBLE_CODEPOINTS)
        self.assertEqual(nt.BAD_CATEGORIES, notify._PR_TITLE_BAD_CATEGORIES)
        self.assertEqual(nt.PR_TITLE_EXTRA_INVISIBLE_CODEPOINTS, notify.PR_TITLE_EXTRA_INVISIBLE_CODEPOINTS)
        self.assertEqual(nt.INVISIBLE, frozenset(map(chr, (*INVISIBLE_CODEPOINTS, *notify.PR_TITLE_EXTRA_INVISIBLE_CODEPOINTS))))

    def test_the_secret_shapes_of_the_tool_are_the_pipelines_copy(self):
        """수정 1차(V1 M-1): 도구는 pipeline 을 불러 쓰지 못하는 사본이라 비밀 모양 판정(llm.mask 의 `_SECRET_RX` + secret_patterns.SECRET_PATTERNS)이 원본과 같은지 여기서 못박는다 —
        원본에 패턴이 더해지면 이 시험이 빨개져 도구 사본도 같이 고치게 된다."""
        self.assertEqual((nt.SECRET_RX.pattern, nt.SECRET_RX.flags), (llm._SECRET_RX.pattern, llm._SECRET_RX.flags))
        self.assertEqual([(rx.pattern, rx.flags) for rx in nt.SECRET_PATTERNS], [(rx.pattern, rx.flags) for _label, rx in secret_patterns.SECRET_PATTERNS])
        for text in ("key=abc", "no secrets here", "AIza" + "x" * 35, "xAIza" + "y" * 20, "monkey=banana", "token=a&b", "ghp_" + "c" * 36, "a ya29." + "d" * 30, "plain 한글 text"):
            self.assertEqual(nt.mask(text), llm.mask(text), text)
            self.assertEqual(nt.looks_secret(text), llm.mask(text) != text, text)

    def test_the_pr_title_check_agrees_with_the_validator(self):
        """검증기(notify.pr_title_problem)가 통과시키는 제목은 통과, 막는 제목은 막는다(앞뒤 공백은 이 도구가 더 엄격하다)."""
        samples = (("정상 제목 [R-170] 도구 [대상: 공통]", ""), ("x" * 200, ""), ("x" * 201, "too_long"), ("", "empty"), ("   ", "empty"), ("a" + ZWSP + "b", "control"),
                   ("a\tb", "control"), ("a\nb", "control"), ("a\rb", "control"), ("a" + chr(0xAD) + "b", "control"), ("a" + BOM + "b", "control"), ("a" + chr(0x202E) + "b", "control"),
                   ("a" + chr(0x2028) + "b", "control"), ("a" + chr(0x2029) + "b", "control"), ("a\x00b", "control"), ("a" + chr(0xD800) + "b", "control"),
                   ("a" + chr(0x2060) + "b", "control"), ("a" + chr(0xA0) + "b", ""), ("a" + chr(0x3000) + "b", ""), ("한글 😀 제목", ""),
                   # 수정 1차(V1 M-1): 비밀 모양 — 런타임·검증기가 거절하는 제목을 도구도 거절한다(`monkey=banana` 처럼 낱말 일부여도 걸리고 `tokenizer=fast` 는 통과)
                   ("hotkey=Ctrl 설정", "secret"), ("key=abc123 설정", "secret"), ("token=abc", "secret"), ("secret=1", "secret"), ("MONKEY=banana", "secret"),
                   ("AIza" + "x" * 35 + " 끝", "secret"), ("ghp_" + "y" * 36, "secret"), ("ya29." + "z" * 30, "secret"), ("123456789:" + "A" * 35, "secret"), ("sk-" + "b" * 32, "secret"),
                   ("tokenizer=fast 사용", ""), ("api 설계 key 값", ""), ("AIza 짧은 것", ""),
                   # 수정 1차(V1 L-2): 글자처럼 보이지만 비어 보이는 문자
                   *((f"가{chr(code)}나", "control") for code in notify.PR_TITLE_EXTRA_INVISIBLE_CODEPOINTS))
        for title, expected in samples:
            self.assertEqual(notify.pr_title_problem(title, limit=200), expected, repr(title))
            self.assertEqual(bool(nt.pr_title_problem(title)), bool(expected), repr(title))
        for title in (" x", "x ", "x" + chr(0xA0)):
            self.assertEqual(notify.pr_title_problem(title, limit=200), "", repr(title))                       # 검증기는 통과시키지만 요청 파일은 앞뒤 공백을 자르므로 글자 그대로 쓸 수 없다
            self.assertIn("공백", nt.pr_title_problem(title))
        self.assertIn("U+200B", nt.pr_title_problem("a" + ZWSP + "b"))
        self.assertIn("2번째", nt.pr_title_problem("a" + ZWSP + "b"))
        self.assertIn("201자", nt.pr_title_problem("x" * 201))
        self.assertEqual(nt.pr_title_problem(None), "비어 있다")


class PrTitleAndNumberAgreementTest(unittest.TestCase):
    """수정 1차(V1 M-1·L-2, V2 M1·L2): 도구·런타임(notify)·검증기(operator_loop.notice_problem 의 REQ-1)가 같은 글을 같은 결론으로 거절하는지 무작위·전수로 비교한다."""
    FRAGMENTS = ("정상", " ", "[R-170]", "key=", "token=", "secret=", "monkey=banana", "tokenizer=fast", "AIza" + "x" * 35, "AIza" + "y" * 10, "ghp_" + "a" * 36, "ghp_" + "a" * 10,
                 "123456789:" + "A" * 35, "sk-" + "b" * 32, "api_key: '" + "k" * 24 + "'", "&", "<b>", "@user", "https://example.com", ZWSP, BOM, chr(0x202E), chr(0xA0), "\t", "\n",
                 *map(chr, notify.PR_TITLE_EXTRA_INVISIBLE_CODEPOINTS), "😀", "한글", "a", "x" * 60)
    CODES = {"": "", "missing_pr_title": "empty", "long_pr_title": "too_long", "pr_title_control": "control", "pr_title_secret": "secret"}
    PHRASES = {"empty": "비어", "too_long": "넘는다", "control": "보이지 않거나", "secret": "비밀(키·토큰)"}

    @staticmethod
    def validator(title):
        """REQ-1 이 병합 요청의 PR 제목 하나에 내리는 결론(코드) — 다른 칸은 모두 올바르게 둔다."""
        values = {"no": "M001", "repo": "shine88pc/chanceblog-desktop", "target": "병합 대상", "pr_title": title, "verify": "검증 결과"}
        return ol.notice_problem(values, "merge", 170, True)

    def check(self, title):
        runtime = notify.pr_title_problem(title, limit=200)
        self.assertEqual(self.CODES[self.validator(title)], runtime, repr(title))                  # 검증기와 런타임은 같은 함수를 쓴다
        tool = nt.pr_title_problem(title)
        self.assertEqual(bool(tool), bool(runtime) or title != title.strip(), repr(title))         # 도구는 같은 결론 + 앞뒤 공백(요청 파일이 자르므로)만 더 엄격하다
        if runtime:
            self.assertIn(self.PHRASES[runtime], tool, repr(title))                                  # 이유의 종류도 같다

    def test_random_titles_get_the_same_verdict_from_the_tool_the_runtime_and_the_validator(self):
        rng = random.Random(20261106)
        seen = set()
        for _ in range(6000):
            title = "".join(rng.choice(self.FRAGMENTS) for _ in range(rng.randint(1, 6)))
            self.check(title)
            seen.add(notify.pr_title_problem(title, limit=200))
        self.assertTrue({"", "control", "secret"} <= seen, seen)                                              # 표본이 통과·제어·비밀을 모두 만났다(무작위 표본이 한쪽에 쏠리지 않았다는 확인)

    def test_each_fixed_secret_shape_and_blank_looking_character_is_refused_by_all_three(self):
        titles = ["hotkey=Ctrl", "key=abc123", "token=abc", "secret=1", "AIza" + "x" * 35, "ghp_" + "y" * 36, "123456789:" + "A" * 35, "sk-" + "b" * 32, "[R-170] monkey=banana 설정",
                  *(f"가{chr(code)}나" for code in notify.PR_TITLE_EXTRA_INVISIBLE_CODEPOINTS), "x" * 201, "", "   "]
        for title in titles:
            self.check(title)
            self.assertTrue(nt.pr_title_problem(title), repr(title))
        for title in ("정상 제목 [R-170] [대상: 공통]", "tokenizer=fast 사용", "x" * 200, "한글 😀 제목", "가" + chr(0xA0) + "나"):
            self.check(title)
            self.assertEqual(nt.pr_title_problem(title), "", repr(title))

    def test_the_strict_number_shape_the_tool_checks_is_the_pipelines_for_every_short_text(self):
        alphabet = ["P", "M", "p", "0", "1", "9", "９", "①", " ", "\n", "-"]
        for length in range(6):
            for chars in itertools.product(alphabet, repeat=length):
                text = "".join(chars)
                self.assertEqual(nt.STRICT_NO_RE.fullmatch(text) is not None, notify.notice_type(text) != "", repr(text))

    def test_the_hand_written_number_check_table(self):
        wanted = {"P012": "info", "M007": "merge", "003": "decision", "1000": "confirm", "P9999": "info"}
        for no, kind in wanted.items():
            self.assertEqual(nt.no_problem(no, kind), "", (no, kind))
        for no, kind, phrase in (("P0012", "info", "앞에 0 을 더 붙인"), ("0003", "decision", "앞에 0 을 더 붙인"), ("M0007", "merge", "앞에 0 을 더 붙인"), ("P12", "info", "모양이 아니다"),
                                 ("P000", "info", "모양이 아니다"), ("000", "run", "모양이 아니다"), ("p012", "info", "모양이 아니다"), ("P012 ", "info", "모양이 아니다"), ("", "info", "모양이 아니다"),
                                 ("P０１２", "info", "모양이 아니다"), ("M007", "info", "kind: info 와 맞지 않는다"), ("003", "merge", "kind: merge 와 맞지 않는다"),
                                 ("P012", "decision", "kind: decision 와 맞지 않는다"), ("P012", "note", "번호 유형을 알 수 없다"), ("P012", "", "번호 유형을 알 수 없다")):
            problem = nt.no_problem(no, kind)
            self.assertIn(phrase, problem, (no, kind, problem))
            self.assertEqual(len(problem.splitlines()), 1)
        self.assertIn("이미 쓰고 있다", nt.no_problem("P012", "info", taken=[("progress", 12)]))
        for taken in ([("merge", 12)], [("ask", 12)], [("progress", 11), ("progress", 13)], []):
            self.assertEqual(nt.no_problem("P012", "info", taken=taken), "", taken)             # 다른 유형의 같은 숫자·다른 숫자는 겹침이 아니다
        self.assertEqual(nt.no_problem("012", "decision", taken=[("progress", 12)]), "")
        for number in range(1, 10000):                                                           # 표준 표기는 1..9999 전부·세 유형 모두 통과
            for kind, number_type in (("info", "progress"), ("merge", "merge"), ("decision", "ask")):
                self.assertEqual(nt.no_problem(nn.format_no(number_type, number), kind), "", (kind, number))

    def test_the_folder_numbers_are_read_from_every_request_file_but_the_one_being_made(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "R-100_a.md").write_text(nth.notice_text(number=100, no="P012"), encoding="utf-8")
            (folder / "R-101_b.md").write_text(nth.notice_text(number=101, no="M007"), encoding="utf-8")
            (folder / "R-102_c.md").write_text(nth.notice_text(number=102, no="003"), encoding="utf-8")
            (folder / "R-103_d.md").write_text(nth.notice_text(number=103, no="P0099"), encoding="utf-8")          # 읽기는 넓다
            (folder / "R-104_old.md").write_text("---\nid: R-104\nkind: info\ntitle: t\nsummary: s\n---\n본문\n", encoding="utf-8")
            (folder / "README.md").write_text("---\nno: P777\n---\n", encoding="utf-8")                              # 요청 파일 이름이 아니다
            (folder / "R-105_bad.md").write_bytes(b"\xff\xfe\x00 not utf-8")
            (folder / "sub").mkdir()
            self.assertEqual(sorted(nt.folder_numbers(folder)), [("ask", 3), ("merge", 7), ("progress", 12), ("progress", 99)])
            self.assertEqual(sorted(nt.folder_numbers(folder, skip="R-100_a.md")), [("ask", 3), ("merge", 7), ("progress", 99)])

    def test_the_notice_front_check_covers_the_number_and_the_merge_title(self):
        good = {"kind": "merge", "no": "M007", "pr_title": "[R-170] 제목 [대상: 공통]"}
        self.assertEqual(nt.notice_front_problem(good), "")
        self.assertIn("앞머리 no:", nt.notice_front_problem({**good, "no": "M0007"}))
        self.assertIn("앞머리 pr_title", nt.notice_front_problem({**good, "pr_title": "key=abc"}))
        self.assertIn("비밀", nt.notice_front_problem({**good, "pr_title": "key=abc"}))
        self.assertNotIn("key=abc", nt.notice_front_problem({**good, "pr_title": "key=abc"}))                    # 비밀 모양 글을 되풀이하지 않는다
        self.assertEqual(nt.notice_front_problem({"kind": "info", "pr_title": "key=abc"}), "")                    # 병합 요청이 아니면 PR 제목을 보지 않는다
        self.assertEqual(nt.notice_front_problem({"kind": "info"}), "")                                          # 옛 모양(no 없음)은 건드리지 않는다


# ==== git 읽기(가짜 git) =========================================================================
def raw_tree(entries, raw_len=20):
    """(모드, 이름, 해시 16진수) 목록 → git 트리 오브젝트 본문(이진)."""
    out = b""
    for mode, name, hex_digest in entries:
        out += mode.encode() + b" " + name.encode("utf-8") + b"\0" + bytes.fromhex(hex_digest[:raw_len * 2])
    return out


def found(kind, body):
    """`git cat-file --batch` 이 찾은 오브젝트 하나에 주는 응답."""
    return f"{'0' * 40} {kind} {len(body)}\n".encode() + body + b"\n"


class FakeGit:
    """nn._git 자리에 끼우는 가짜 — for-each-ref 줄과 `cat-file --batch` 응답의 모양을 흉내 낸다. trees·blobs: {해시: (종류, 내용 바이트) 또는 None(없음)}."""

    def __init__(self, refs, trees, blobs):
        self.refs, self.trees, self.blobs, self.calls = refs, trees, blobs, []

    def __call__(self, repo, *args, data=None):
        self.calls.append((args, data))
        if args[0] == "for-each-ref":
            return "".join(f"{sha} {kind} {name}\n" for sha, kind, name in self.refs).encode()
        if args[:2] == ("cat-file", "--batch"):
            out = b""
            for query in data.decode("utf-8").splitlines():
                entry = self.trees.get(query.split(":", 1)[0]) if ":" in query else self.blobs.get(query)
                out += f"{query} missing\n".encode() if entry is None else found(*entry)
            return out
        raise AssertionError(args)

    def batch_queries(self):
        return [data.decode("utf-8").splitlines() for args, data in self.calls if args[0] == "cat-file"]


MAIN_SHA, X_SHA, OLD_SHA, BLOB_SHA = "a" * 40, "b" * 40, "d" * 40, "c" * 40
D1, D2, D3, D4, D5, D6, D7, D8 = (char * 40 for char in "123456" + "78")


def basic_fake():
    refs = [(MAIN_SHA, "commit", "refs/remotes/origin/main"), (X_SHA, "commit", "refs/remotes/origin/ai/claude/x"), (MAIN_SHA, "commit", "refs/remotes/origin/ai/claude/same-as-main"),
            (BLOB_SHA, "blob", "refs/remotes/origin/ai/claude/blobref"), (OLD_SHA, "commit", "refs/remotes/origin/ai/claude/old")]
    trees = {MAIN_SHA: ("tree", raw_tree([("100644", "R-168_progress-p010.md", D1), ("100644", "R-169_merge-m004.md", D2), ("100644", "README.md", D3), ("40000", "old", D4),
                                          ("120000", "R-170_link.md", D5), ("100644", "R-171_x.md.bak", D6), ("100755", "R-172_exec.md", D7)])),
             X_SHA: ("tree", raw_tree([("100644", "R-168_progress-p010.md", D1), ("100644", "R-176_progress-p013.md", D8)])),
             OLD_SHA: None}
    blobs = {D1: ("blob", fm("no: P010").encode()), D2: ("blob", fm("no: M004").encode()), D7: ("blob", fm('no: "002"').encode()), D8: ("blob", fm("no: P013").encode())}
    return FakeGit(refs, trees, blobs)


class GitReadingWithFakeGitTest(unittest.TestCase):
    def read(self, fake, local=False):
        warnings = []
        with mock.patch.object(nn, "_git", fake):
            return nn.scan("repo", local=local, warn=warnings.append), warnings

    def test_three_git_calls_each_commit_and_file_is_read_once_and_only_request_files_are_asked_for(self):
        fake = basic_fake()
        result, warnings = self.read(fake)
        self.assertEqual(result, {"progress": (13, "R-176_progress-p013.md @ origin/ai/claude/x"), "merge": (4, "R-169_merge-m004.md @ origin/main"),
                                  "ask": (2, "R-172_exec.md @ origin/main")})
        self.assertEqual([args[0] for args, _ in fake.calls], ["for-each-ref", "cat-file", "cat-file"])
        trees_asked, blobs_asked = fake.batch_queries()
        self.assertEqual(trees_asked, [f"{MAIN_SHA}:{FOLDER}", f"{OLD_SHA}:{FOLDER}", f"{X_SHA}:{FOLDER}"])      # 같은 커밋(별명 가지)은 한 번 — main 먼저
        self.assertEqual(blobs_asked, sorted([D1, D2, D7, D8]))                                                  # 같은 파일(D1)은 한 번, README·하위 폴더·링크·.bak 는 묻지도 않는다
        self.assertEqual(len(warnings), 1)
        self.assertIn("origin/ai/claude/blobref", warnings[0])
        self.assertIn("커밋이 아니다", warnings[0])
        self.assertEqual(fake.calls[0][0][:2], ("for-each-ref", "--format=%(objectname) %(objecttype) %(refname)"))
        self.assertEqual(fake.calls[0][0][2:], ("refs/remotes/origin/main", "refs/remotes/origin/ai"))             # `ai/*` 가 아니라 접두사

    def test_local_branches_are_read_only_when_asked(self):
        fake = basic_fake()
        self.read(fake, local=True)
        self.assertEqual(fake.calls[0][0][2:], ("refs/remotes/origin/main", "refs/remotes/origin/ai", "refs/heads"))

    def test_a_commit_without_the_request_folder_is_not_a_problem_but_the_other_oddities_warn(self):
        refs = [(MAIN_SHA, "commit", "refs/remotes/origin/main"), (OLD_SHA, "commit", "refs/remotes/origin/ai/claude/old"), (X_SHA, "commit", "refs/remotes/origin/ai/claude/x"),
                ("e" * 40, "commit", "refs/remotes/origin/ai/claude/notdir"), ("f" * 40, "commit", "refs/remotes/origin/ai/claude/cut")]
        good = raw_tree([("100644", "R-168_progress-p010.md", D1), ("100644", "R-169_merge-m004.md", D2)])
        trees = {MAIN_SHA: ("tree", good), OLD_SHA: None, X_SHA: ("tree", raw_tree([("100644", "R-170_ask-ok.md", D3)])), "e" * 40: ("blob", b"x"), "f" * 40: ("tree", good[:-5])}
        blobs = {D1: ("blob", fm("no: P010").encode()), D2: None, D3: ("blob", fm('no: "005"').encode())}
        result, warnings = self.read(FakeGit(refs, trees, blobs))
        self.assertEqual(result, {"progress": (10, "R-168_progress-p010.md @ origin/main"), "merge": (0, ""), "ask": (5, "R-170_ask-ok.md @ origin/ai/claude/x")})
        self.assertEqual(len(warnings), 3, warnings)
        joined = "\n".join(warnings)
        self.assertIn("폴더가 아니다: origin/ai/claude/notdir", joined)
        self.assertIn("트리가 잘렸다): origin/ai/claude/cut", joined)
        self.assertIn("읽을 수 없는 파일: R-169_merge-m004.md @ origin/main", joined)
        self.assertNotIn("old", joined)                                                  # 요청함 폴더가 없는 가지는 조용히 건너뛴다

    def test_missing_origin_main_warns_to_fetch(self):
        refs = [(X_SHA, "commit", "refs/remotes/origin/ai/claude/x")]
        result, warnings = self.read(FakeGit(refs, {X_SHA: ("tree", raw_tree([("100644", "R-176_progress-p013.md", D8)]))}, {D8: ("blob", fm("no: P013").encode())}))
        self.assertEqual(result["progress"][0], 13)
        self.assertEqual(len(warnings), 1)
        self.assertIn("origin/main", warnings[0])
        self.assertIn("git fetch origin", warnings[0])

    def test_a_cut_batch_output_is_an_error_not_a_silent_miss(self):
        class Cut(FakeGit):
            def __call__(self, repo, *args, data=None):
                out = super().__call__(repo, *args, data=data)
                return out[:30] if args[0] == "cat-file" else out
        fake = Cut([(MAIN_SHA, "commit", "refs/remotes/origin/main")], {MAIN_SHA: ("tree", raw_tree([("100644", "R-168_a.md", D1)]))}, {})
        with mock.patch.object(nn, "_git", fake), self.assertRaises(nn.ScanError):
            nn.scan("repo", warn=lambda message: None)

    def test_sha256_sized_object_names_and_a_huge_file(self):
        digest32 = "9" * 64
        self.assertEqual(nn.tree_files(raw_tree([("100644", "R-168_a.md", digest32)], raw_len=32), 32), [("R-168_a.md", digest32)])
        with self.assertRaises(ValueError):
            nn.tree_files(raw_tree([("100644", "R-168_a.md", digest32)], raw_len=32)[:-1], 32)
        big = ("---\nno: P012\n---\n" + "x" * 500000).encode()
        sha = "9" * 64
        refs = [(sha, "commit", "refs/remotes/origin/main")]
        result, _ = self.read(FakeGit(refs, {sha: ("tree", raw_tree([("100644", "R-168_big.md", digest32)], raw_len=32))}, {digest32: ("blob", big)}))
        self.assertEqual(result["progress"], (12, "R-168_big.md @ origin/main"))

    def test_tree_files_keeps_only_regular_files_and_decodes_names(self):
        body = raw_tree([("100644", "R-168_a.md", D1), ("40000", "dir", D2), ("120000", "R-169_link.md", D3), ("160000", "R-170_sub.md", D4), ("100755", "R-171_한글.md", D5)])
        self.assertEqual(nn.tree_files(body, 20), [("R-168_a.md", D1), ("R-171_한글.md", D5)])


class GitCallTest(unittest.TestCase):
    def done(self, code=0, out=b"", err=b""):
        return subprocess.CompletedProcess(["git"], code, out, err)

    def test_the_command_line_the_environment_and_stdin(self):
        with mock.patch.object(nn.subprocess, "run", return_value=self.done(out=b"x")) as run:
            self.assertEqual(nn._git("some/repo", "for-each-ref", "a"), b"x")
            self.assertEqual(nn._git("some/repo", "cat-file", "--batch", data=b"q\n"), b"x")
        first, second = run.call_args_list
        self.assertEqual(first.args[0], ["git", "-c", "core.quotePath=false", "-C", "some/repo", "for-each-ref", "a"])
        self.assertEqual(first.kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("input", first.kwargs)
        self.assertEqual(second.kwargs["input"], b"q\n")
        self.assertNotIn("stdin", second.kwargs)
        for call in (first, second):
            self.assertTrue(call.kwargs["capture_output"])
            self.assertEqual(call.kwargs["timeout"], nn.GIT_TIMEOUT)
            self.assertEqual(call.kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
            self.assertEqual(call.kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")

    def test_failures_become_scan_errors(self):
        refused = self.done(128, err=b"fatal: not a git repository")
        with mock.patch.object(nn.subprocess, "run", return_value=refused), self.assertRaises(nn.ScanError) as caught:
            nn._git("x", "for-each-ref")
        self.assertIn("git for-each-ref 실패(종료 128)", str(caught.exception))
        self.assertIn("not a git repository", str(caught.exception))
        with mock.patch.object(nn.subprocess, "run", side_effect=FileNotFoundError()), self.assertRaisesRegex(nn.ScanError, "git 을 찾을 수 없다"):
            nn._git("x", "for-each-ref")
        with mock.patch.object(nn.subprocess, "run", side_effect=subprocess.TimeoutExpired(["git"], 1)), self.assertRaisesRegex(nn.ScanError, "끝나지 않았다"):
            nn._git("x", "for-each-ref")


class WorkFolderReadingTest(unittest.TestCase):
    def test_only_files_directly_under_the_request_folder_are_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "인수인계" / "요청함"
            (folder / "sub").mkdir(parents=True)
            for rel, text in (("R-183_merge-m030.md", fm("no: M030")), ("R-184_progress-p004.md", fm("no: P004")), ("README.md", fm("no: M099")), ("sub/R-185_x.md", fm("no: M098")),
                              ("R-186_body.md", fm("id: R-186", body="no: M097\n")), ("R-187_x.txt", fm("no: M096")), ("R-188_bad.md", fm("no: M12"))):
                (folder / rel).write_text(text, encoding="utf-8", newline="\n")
            warnings = []
            result = nn.scan(None, dirs=[tmp], warn=warnings.append)
            self.assertEqual(result, {"progress": (4, f"R-184_progress-p004.md @ 폴더 {tmp}"), "merge": (30, f"R-183_merge-m030.md @ 폴더 {tmp}"), "ask": (0, "")})
            self.assertEqual(warnings, [])
            self.assertEqual(nn.scan(None, dirs=[tmp, tmp], warn=warnings.append), result)                # 같은 폴더를 두 번 줘도 같다
            self.assertEqual(nn.scan(None, dirs=[Path(tmp)], warn=warnings.append), result)               # make_request.py 는 Path 로 준다
            self.assertEqual(warnings, [])

    def test_a_folder_without_the_request_folder_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            warnings = []
            self.assertEqual(nn.scan(None, dirs=[tmp], warn=warnings.append), scan_result())
            self.assertEqual(len(warnings), 1)
            self.assertIn("작업 폴더에", warnings[0])
            self.assertIn(tmp, warnings[0])


class CommandLineTest(unittest.TestCase):
    RESULT = (("progress", (11, "R-168_progress-p011.md @ origin/main")), ("merge", (4, "R-169_merge-m004.md @ origin/ai/claude/x")), ("ask", (7, "R-170_ask.md @ origin/ai/codex/y")))

    def run_cli(self, *argv, result=None, error=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(nn, "scan", return_value=result or dict(self.RESULT), side_effect=error) as scan, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = nn.main(list(argv))
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue(), scan

    def test_default_output_is_three_lines(self):
        code, out, err, scan = self.run_cli()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), ["P 다음 번호: P012 (지금 최댓값 P011 — R-168_progress-p011.md @ origin/main)",
                                            "M 다음 번호: M005 (지금 최댓값 M004 — R-169_merge-m004.md @ origin/ai/claude/x)",
                                            "확인 다음 번호: 008 (지금 최댓값 007 — R-170_ask.md @ origin/ai/codex/y)"])
        scan.assert_called_once_with(".", [], False)

    def test_an_empty_state_says_there_is_nothing_yet(self):
        code, out, _err, _scan = self.run_cli(result=scan_result())
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["P 다음 번호: P001 (아직 없음)", "M 다음 번호: M001 (아직 없음)", "확인 다음 번호: 001 (아직 없음)"])

    def test_type_prints_just_the_number(self):
        for argument, expected in (("P", "P012"), ("p", "P012"), ("M", "M005"), ("m", "M005"), ("ask", "008"), ("ASK", "008"), (" P ", "P012")):
            code, out, err, _scan = self.run_cli("--type", argument)
            self.assertEqual((code, out, err), (0, expected + "\n", ""), argument)
        self.assertEqual(self.run_cli("--type=M")[1], "M005\n")

    def test_flags_reach_the_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _out, _err, scan = self.run_cli("--repo", tmp, "--dir", "a", "--dir", "b", "--local")
            self.assertEqual(code, 0)
            scan.assert_called_once_with(tmp, ["a", "b"], True)

    def test_usage_errors_exit_with_2_and_do_not_scan(self):
        for argv in (("--type", "X"), ("--type", ""), ("--type", "progress2"), ("--bogus",), ("--repo",), ("--repo", "nonexistent-folder-for-this-test")):
            code, out, err, scan = self.run_cli(*argv)
            self.assertEqual(code, 2, argv)
            self.assertEqual(out, "", argv)
            self.assertTrue(err, argv)
            scan.assert_not_called()

    def test_an_exhausted_type_is_an_error_but_the_others_still_print(self):
        result = dict(dict(self.RESULT), progress=(9999, "R-1_x.md @ origin/main"))
        code, out, err, _scan = self.run_cli(result=result)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["M 다음 번호: M005 (지금 최댓값 M004 — R-169_merge-m004.md @ origin/ai/claude/x)",
                                            "확인 다음 번호: 008 (지금 최댓값 007 — R-170_ask.md @ origin/ai/codex/y)"])
        self.assertIn("P 번호가 상한 9999", err)
        code, out, err, _scan = self.run_cli("--type", "P", result=result)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("상한", err)
        self.assertEqual(self.run_cli("--type", "M", result=result)[:2], (0, "M005\n"))

    def test_a_read_failure_is_exit_1_with_the_reason_on_stderr(self):
        code, out, err, _scan = self.run_cli(error=nn.ScanError("git 을 찾을 수 없다"))
        self.assertEqual((code, out, err), (1, "", "오류: git 을 찾을 수 없다\n"))

    def test_run_as_a_script_the_exit_codes_are_the_documented_ones(self):
        done = subprocess.run([sys.executable, "-X", "utf8", str(WORK / "next_notice_no.py"), "--type", "X"], check=False, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 2)
        self.assertIn("--type", done.stderr)
        self.assertEqual(done.stdout, "")


# ==== notice_tools(순수 함수) ====================================================================
class NoticeToolsTest(unittest.TestCase):
    def test_read_front(self):
        text = fm("id: R-170", 'title: "따옴표 제목"', "no: '003'", "pr_title: \"그대로\" 제목", "kind: merge", "kind: info", "# 주석", "모양 아닌 줄", "now:", body="id: X\n")
        self.assertEqual(nt.read_front(text), {"id": "R-170", "title": "따옴표 제목", "no": "003", "pr_title": '"그대로" 제목', "kind": "merge", "now": ""})
        self.assertEqual(nt.read_front("pr_title: x\n"), {})
        self.assertEqual(nt.read_front(fm('pr_title: "x"'))["pr_title"], '"x"')                      # PR 제목은 따옴표까지 제목의 글자다
        self.assertEqual(nt.read_front(fm("kind: info"))["kind"], "info")

    def test_length_problems_at_the_limit_and_one_over(self):
        for key, limit in nt.LIMITS.items():
            self.assertEqual(nt.length_problems({key: "가" * limit}), [], key)
            self.assertEqual(nt.length_problems({key: "가" * (limit + 1)}), [(key, limit + 1, limit)], key)
        self.assertEqual(nt.length_problems({}), [])
        self.assertEqual(nt.length_problems({"unknown": "가" * 1000, "no": "가" * 1000}), [])
        over = nt.length_problems({"now": "가" * 201, "title": "가" * 81, "waiting": "가" * 200})
        self.assertEqual(over, [("title", 81, 80), ("now", 201, 200)])                                 # LIMITS 의 순서
        self.assertEqual(nt.length_problems({"options": "가 / 나 / " + "다" * 61}), [("options 보기 3번", 61, 60)])
        self.assertEqual(nt.length_problems({"options": "가 / " + "나" * 60}), [])
        self.assertEqual(nt.length_problems({"options": ""}), [])

    def test_no_front_value(self):
        self.assertEqual([nt.no_front_value(no) for no in ("P012", "M007", "003", "1000")], ["P012", "M007", '"003"', '"1000"'])

    def test_fill_front_values(self):
        text = "---\nid: R-170\nno: @NO@\npr_title: @PR_TITLE@\nsummary: 「@PR_TITLE@」 번호 @NO@\n---\n본문 @NO@ 와 @PR_TITLE@\nno: @NO@\n"
        title = 'a\\1 "q" \'s\' & <b> : [대상: 공통]'
        filled = nt.fill_front_values(text, no="P012", pr_title=title)
        self.assertEqual(filled, f'---\nid: R-170\nno: P012\npr_title: {title}\nsummary: 「{title}」 번호 P012\n---\n본문 P012 와 {title}\nno: P012\n')
        self.assertEqual(nt.fill_front_values(text, no="003").splitlines()[2], 'no: "003"')
        self.assertIn("본문 003 와 @PR_TITLE@", nt.fill_front_values(text, no="003"))               # 본문에서는 따옴표 없이
        self.assertEqual(nt.fill_front_values(text), text)
        self.assertEqual(nt.fill_front_values("본문 @NO@\n", no="P012"), "본문 P012\n")
        quoted = nt.fill_front_values('---\nno: "@NO@"\n---\n', no="P012")
        self.assertEqual(quoted, '---\nno: "P012"\n---\n')
        self.assertEqual(nt.read_front(quoted)["no"], "P012")
        crlf = nt.fill_front_values("---\r\nno: @NO@\r\n---\r\n", no="P012")
        self.assertIn("P012", crlf)

    def test_fill_placeholders_is_one_pass_and_literal(self):
        self.assertEqual(nt.fill_placeholders("@TESTS@ / @VERIFY@ / @OTHER@", {"TESTS": "@VERIFY@", "VERIFY": "x"}), "@VERIFY@ / x / @OTHER@")
        self.assertEqual(nt.fill_placeholders("[@TESTS@]", {"TESTS": "\\1 \\g<0> \\n"}), "[\\1 \\g<0> \\n]")
        self.assertEqual(nt.fill_placeholders("@TESTS@ @TESTS@", {"TESTS": ""}), " ")
        self.assertEqual(nt.fill_placeholders("@TESTS@", {}), "@TESTS@")
        self.assertEqual(nt.fill_placeholders("x@TESTS@y", {"TESTS": "-"}), "x-y")

    def test_leftover_placeholders(self):
        text = "@PR_TITLE@ @NO@ @VERIFY@ @LINK@ @PREVIOUS@ @TESTS@ @DATE@"
        self.assertEqual(nt.leftover_placeholders(text), ["@TESTS@", "@VERIFY@", "@LINK@", "@PREVIOUS@", "@NO@", "@PR_TITLE@"])
        self.assertEqual(nt.leftover_placeholders(text, ignore=("@VERIFY@", "@NO@")), ["@TESTS@", "@LINK@", "@PREVIOUS@", "@PR_TITLE@"])
        self.assertEqual(nt.leftover_placeholders("깨끗한 글 @DATE@"), [])

    def test_the_automatic_verify_text_never_claims_an_independent_verification(self):
        self.assertEqual(nt.auto_verify_text(4), "검사 4칸 초록")
        self.assertNotIn("독립", nt.auto_verify_text(4))
        self.assertLessEqual(len(nt.auto_verify_text(10 ** 6)), nt.LIMITS["verify"])

    def test_repo_folder(self):
        self.assertEqual([nt.repo_folder(name) for name in ("shine88pc/chanceblog-desktop", "x/y-desktop", "shine88pc/chanceblog", "shine88pc/desktop", "chanceblog-desktop/x")],
                         ["cd_repo", "cd_repo", "wt_r30", "wt_r30", "wt_r30"])


class HeadSubjectWithFakeRunTest(unittest.TestCase):
    SHA = "ab" * 20

    def runner(self, *replies):
        calls = []

        def run(args):
            calls.append(args)
            reply = replies[min(len(calls), len(replies)) - 1]
            if isinstance(reply, BaseException):
                raise reply
            return reply
        run.calls = calls
        return run

    def ok(self, subject, sha=None, end="\n"):
        return subprocess.CompletedProcess([], 0, f"{sha or self.SHA}\0{subject}{end}".encode(), b"")

    def failed(self):
        return subprocess.CompletedProcess([], 128, b"", b"fatal: bad revision")

    def test_the_local_branch_comes_first_and_the_command_is_exact(self):
        run = self.runner(self.ok("[R-170] 제목 [대상: 공통]"))
        self.assertEqual(nt.head_subject("W/wt_r30", "ai/claude/r170-x", run=run), ("[R-170] 제목 [대상: 공통]", self.SHA, "ai/claude/r170-x"))
        self.assertEqual(run.calls, [["git", "-C", "W/wt_r30", "log", "-1", "--format=%H%x00%B", "ai/claude/r170-x", "--"]])

    def test_only_the_first_line_of_the_commit_message_is_the_title(self):
        """수정 1차(V2 L2): `%s` 는 첫 문단이 두 줄이면 한 칸 띄어 이어 붙여 GitHub PR 제목(첫 줄)과 달라진다 — 메시지 전체(`%B`)의 첫 줄만 제목으로 쓴다."""
        for message, want in (("첫 줄\n둘째 줄\n\n본문", "첫 줄"), ("첫 줄\r\n둘째 줄\r\n\r\n본문", "첫 줄"), ("첫 줄\n\n본문\n", "첫 줄"), ("한 줄뿐\n", "한 줄뿐"),
                              ("[R-170] 제목 [대상: 공통]\n둘째 줄(첫 문단이 이어짐)\n", "[R-170] 제목 [대상: 공통]"), ("\n빈 첫 줄 뒤의 글", "")):
            self.assertEqual(nt.head_subject("r", "b", run=self.runner(self.ok(message)))[0], want, repr(message))
        self.assertEqual(nt.pr_title_problem(""), "비어 있다")                       # 첫 줄이 비면 요청 파일을 만들지 않는다

    def test_without_a_local_branch_it_reads_origin(self):
        run = self.runner(self.failed(), self.ok("원격 제목"))
        self.assertEqual(nt.head_subject("W/cd_repo", "ai/claude/r170-x", run=run), ("원격 제목", self.SHA, "origin/ai/claude/r170-x"))
        self.assertEqual([call[6] for call in run.calls], ["ai/claude/r170-x", "origin/ai/claude/r170-x"])

    def test_no_branch_anywhere_is_an_error_naming_both(self):
        run = self.runner(self.failed())
        with self.assertRaises(nt.TitleError) as caught:
            nt.head_subject("W/wt_r30", "ai/claude/nope", run=run)
        self.assertIn("ai/claude/nope", str(caught.exception))
        self.assertIn("origin/ai/claude/nope", str(caught.exception))
        self.assertEqual(len(run.calls), 2)

    def test_only_surrounding_line_breaks_are_removed(self):
        for end in ("", "\n", "\r\n", "\n\n"):
            self.assertEqual(nt.head_subject("r", "b", run=self.runner(self.ok("  두 칸 앞과 뒤 공백 ", end=end)))[0], "  두 칸 앞과 뒤 공백 ", repr(end))
        self.assertEqual(nt.head_subject("r", "b", run=self.runner(self.ok("a: b \"c\" 'd' & <e> \\ @ #", end="\r\n")))[0], "a: b \"c\" 'd' & <e> \\ @ #")
        self.assertEqual(nt.head_subject("r", "b", run=self.runner(self.ok("가" + ZWSP + "나")))[0], "가" + ZWSP + "나")            # 보이지 않는 글자도 그대로(걸러내는 것은 pr_title_problem)
        self.assertEqual(nt.head_subject("r", "b", run=self.runner(self.ok("x", sha="cd" * 32)))[1], "cd" * 32)

    def test_odd_branch_names_never_reach_git(self):
        for branch in ("", "-x", "--output=x", "a..b", "a b", "a;b", "a\nb", "a$b", "한글", "/a", "a`b"):
            run = self.runner(self.ok("x"))
            with self.assertRaises(nt.TitleError, msg=repr(branch)):
                nt.head_subject("r", branch, run=run)
            self.assertEqual(run.calls, [], repr(branch))
        for branch in ("ai/claude/r170-x", "main", "a.b_c-d/e"):
            self.assertEqual(nt.head_subject("r", branch, run=self.runner(self.ok("x")))[0], "x")

    def test_garbled_output_is_an_error(self):
        for reply in (subprocess.CompletedProcess([], 0, b"no separator\n", b""), subprocess.CompletedProcess([], 0, b"abc\0title\n", b""),
                      subprocess.CompletedProcess([], 0, b"", b""), subprocess.CompletedProcess([], 0, (self.SHA + "\0").encode() + b"\xff\xfe\n", b"")):
            with self.assertRaises(nt.TitleError):
                nt.head_subject("r", "b", run=self.runner(reply))
        with self.assertRaisesRegex(nt.TitleError, "git 을 부르지 못했다"):
            nt.head_subject("r", "b", run=self.runner(FileNotFoundError()))
        with self.assertRaisesRegex(nt.TitleError, "git 을 부르지 못했다"):
            nt.head_subject("r", "b", run=self.runner(subprocess.TimeoutExpired(["git"], 1)))


# ==== make_request.main ========================================================================
class Gate:
    """검사 관문 자리에 끼우는 가짜 — 부르면 (머리 커밋 해시, 실행 목록)을 돌려주고 호출을 기록한다. head 가 None 이면 부르는 순간 시험이 실패한다."""

    def __init__(self, head="a" * 40, runs=3):
        self.head, self.runs, self.calls = head, runs, []

    def __call__(self, target, workspace):
        if self.head is None:
            raise AssertionError("검사 관문을 부르면 안 되는 흐름이다")
        self.calls.append((target, workspace))
        return self.head, [{"id": index} for index in range(self.runs)]


INFO_DRAFT = """---
id: R-195
kind: info
title: [R-195] 진행 현황 P — 11-06 12:07 기준
summary: 현황 알림입니다
urgency: 보통
created: 2026-11-06
no: @NO@
at: 2026-11-06 12:07
now: 도구 시험 중
changed: 없음
next: 병합 요청
eta: 11-06 15:00경(추정)
waiting: 없음
check: 이상 없음
---
본문 @TESTS@ @VERIFY@ @PREVIOUS@
"""
MERGE_DRAFT = """---
id: R-196
kind: merge
title: [R-196] 병합 부탁 — 알림 번호 도구
summary: 병합할 PR 제목 → 「@PR_TITLE@」 이 제목 하나만 병합합니다.
urgency: 보통
created: 2026-11-06
no: M007
repo: shine88pc/chanceblog
target: 알림 번호 도구
pr_title: @PR_TITLE@
verify: @VERIFY@
---
## 병합할 제목 (이것 하나만)
> @PR_TITLE@

시험: @TESTS@
"""
OLD_DRAFT = ("---\nid: R-197\nkind: merge\ntitle: [R-197] 병합 부탁 — 옛 모양\nsummary: 병합 부탁입니다\nurgency: 보통\ncreated: 2026-11-06\n---\n"
             "시험: @TESTS@\n검증: @VERIFY@\n이전: @PREVIOUS@\n")
TARGET = "shine88pc/chanceblog:ai/claude/r170-x"


def run_main(argv, workspace, gate=None):
    """make_request.main 을 불러 (종료 값: 정상이면 None·멈췄으면 그 글, 출력)을 돌려준다."""
    out, code = io.StringIO(), None
    with contextlib.redirect_stdout(out):
        try:
            make_request.main(argv, workspace=workspace, gate=gate)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue()


class MakeRequestTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name) / "W"
        self.folder = self.work / "wt_r30" / "인수인계" / "요청함"
        self.folder.mkdir(parents=True)

    def draft(self, text, name="draft.md"):
        (self.work / name).write_text(text, encoding="utf-8", newline="\n")
        return name

    def run_it(self, number, slug, draft, tests="", verify="", previous="", target="", gate=None):
        return run_main([number, slug, draft, tests, verify, previous, target], self.work, gate)

    def written(self, name):
        return (self.folder / name).read_text(encoding="utf-8")

    def assertStops(self, code, *phrases):
        self.assertIsInstance(code, str)
        for phrase in phrases:
            self.assertIn(phrase, code)
        self.assertEqual(list(self.folder.iterdir()), [], "멈췄으니 파일은 없어야 한다")

    # -- 옛 동작은 그대로
    def test_the_old_style_merge_request_is_filled_exactly_as_before(self):
        gate = Gate(runs=3)
        code, out = self.run_it("R-197", "old-merge", self.draft(OLD_DRAFT), "시험 통과", "검증 통과", "이전 문장", TARGET, gate)
        self.assertIsNone(code)
        self.assertEqual(self.written("R-197_old-merge.md"), OLD_DRAFT.replace("@TESTS@", "시험 통과").replace("@VERIFY@", "검증 통과").replace("@PREVIOUS@", "이전 문장"))
        self.assertEqual(gate.calls, [(TARGET, self.work)])
        self.assertEqual(out.splitlines()[-1], f"파일 R-197_old-merge.md | 줄 수 {OLD_DRAFT.count(chr(10))} | title {len('[R-197] 병합 부탁 — 옛 모양')} | summary {len('병합 부탁입니다')}")

    def test_an_info_request_never_calls_the_gate_and_an_empty_verify_stays_empty(self):
        gate = Gate(head=None)
        code, _out = self.run_it("R-198", "note", self.draft(OLD_DRAFT.replace("kind: merge", "kind: info").replace("R-197", "R-198")), "", "", "", "", gate)
        self.assertIsNone(code)
        self.assertEqual(self.written("R-198_note.md").splitlines()[-3:], ["시험: ", "검증: ", "이전: "])
        gate2 = Gate(head=None)
        self.assertIsNone(self.run_it("R-199", "note2", self.draft(OLD_DRAFT.replace("kind: merge", "kind: info").replace("R-197", "R-199"), "d2.md"), target=TARGET, gate=gate2)[0])

    def test_a_merge_request_with_an_empty_verify_gets_the_check_count_and_says_so(self):
        code, out = self.run_it("R-197", "old-merge", self.draft(OLD_DRAFT), "시험 통과", "", "", TARGET, Gate(runs=4))
        self.assertIsNone(code)
        self.assertIn("검증: 검사 4칸 초록\n", self.written("R-197_old-merge.md"))
        self.assertIn("검증 문구가 비어 있어 `검사 4칸 초록` 으로 채웠다", out)
        self.assertIn("독립 검증", out)

    def test_a_given_verify_text_is_used_and_nothing_is_added_to_it(self):
        code, out = self.run_it("R-196", "merge-tool", self.draft(MERGE_DRAFT.replace("pr_title: @PR_TITLE@", "pr_title: 직접 쓴 제목").replace("@PR_TITLE@", "직접 쓴 제목")), "통과",
                                "독립 검증 통과 · 검사 4칸 초록", "", TARGET, Gate(runs=9))
        self.assertIsNone(code)
        self.assertIn("verify: 독립 검증 통과 · 검사 4칸 초록\n", self.written("R-196_merge-tool.md"))
        self.assertNotIn("으로 채웠다", out)

    def test_a_utf8_bom_in_the_draft_is_dropped_from_the_written_file(self):
        (self.work / "bom.md").write_bytes((BOM + OLD_DRAFT.replace("kind: merge", "kind: info")).encode("utf-8"))
        self.assertIsNone(self.run_it("R-197", "bom", "bom.md")[0])
        self.assertTrue(self.written("R-197_bom.md").startswith("---\n"))

    # -- 알림 번호
    def test_the_progress_number_is_the_next_one_and_is_printed(self):
        found = scan_result(11, 4, 7, "R-168_progress-p011.md @ origin/main")
        with mock.patch.object(nn, "scan", return_value=found) as scan:
            code, out = self.run_it("R-195", "progress-p012", self.draft(INFO_DRAFT), "t", "", "p")
        self.assertIsNone(code)
        scan.assert_called_once_with(self.work / "wt_r30", dirs=[self.work / "wt_r30"], local=True)
        text = self.written("R-195_progress-p012.md")
        request = ol.parse_request("R-195_progress-p012.md", text, strict=True)
        self.assertEqual((request.no, request.kind), ("P012", "info"))
        self.assertIn("\nno: P012\n", text)
        self.assertIn("본문 t  p\n", text)
        self.assertIn("알림 번호: P 다음 번호: P012 (지금 최댓값 P011 — R-168_progress-p011.md @ origin/main)", out)

    def test_a_confirmation_number_is_digits_only_in_quotes(self):
        draft = INFO_DRAFT.replace("kind: info", "kind: decision").replace(
            "at: 2026-11-06 12:07\nnow: 도구 시험 중\nchanged: 없음\nnext: 병합 요청\neta: 11-06 15:00경(추정)\nwaiting: 없음\ncheck: 이상 없음\n",
            "options: 지금 / 나중에\ndefault: 1\napprove: 2\n")
        self.assertNotIn("at: 2026", draft)                                       # 진행 현황 칸을 확인 요청 칸으로 바꿨다
        for kind in ("decision", "confirm", "run"):
            with mock.patch.object(nn, "scan", return_value=scan_result(0, 0, 2, "R-1_x.md @ origin/main")):
                code, out = self.run_it("R-195", f"ask-{kind}", self.draft(draft.replace("kind: decision", f"kind: {kind}"), f"{kind}.md"))
            self.assertIsNone(code, kind)
            text = self.written(f"R-195_ask-{kind}.md")
            self.assertIn('\nno: "003"\n', text, kind)
            self.assertEqual(ol.parse_request(f"R-195_ask-{kind}.md", text, strict=True).no, "003", kind)
            self.assertIn("확인 다음 번호: 003", out)

    def test_a_merge_number_is_m_and_the_kind_decides_the_type(self):
        expected = {"info": "P012", "merge": "M005", "decision": "008", "confirm": "008", "run": "008"}
        for kind, no in expected.items():
            draft = "---\nid: R-195\nkind: " + kind + "\ntitle: t\nsummary: s\nno: @NO@\n---\n"
            with mock.patch.object(nn, "scan", return_value=scan_result(11, 4, 7)):
                code, _out = self.run_it("R-195", f"k-{kind}", self.draft(draft, f"{kind}.md"), target=TARGET, gate=Gate())
            self.assertIsNone(code, kind)
            value = nt.read_front(self.written(f"R-195_k-{kind}.md"))["no"]
            self.assertEqual(value, no, kind)

    def test_number_problems_stop_before_anything_is_written(self):
        draft = self.draft(INFO_DRAFT)
        with mock.patch.object(nn, "scan", side_effect=nn.ScanError("git 을 찾을 수 없다")):
            self.assertStops(self.run_it("R-195", "x", draft)[0], "알림 번호를 정하지 못했다", "git 을 찾을 수 없다")
        with mock.patch.object(nn, "scan", return_value=scan_result(9999, 0, 0)):
            self.assertStops(self.run_it("R-195", "x", draft)[0], "알림 번호를 정하지 못했다", "상한 9999")
        self.assertStops(self.run_it("R-195", "x", self.draft(INFO_DRAFT.replace("kind: info", "kind: note"), "k.md"))[0], "no: @NO@", "'note'")
        self.assertStops(self.run_it("R-195", "x", self.draft(INFO_DRAFT.replace("kind: info\n", ""), "nokind.md"))[0], "no: @NO@")

    def test_a_target_that_already_exists_is_refused_before_a_number_is_chosen(self):
        (self.folder / "R-195_x.md").write_text("이미 있음\n", encoding="utf-8")
        with mock.patch.object(nn, "scan", side_effect=AssertionError("이미 있는 파일이면 번호를 구하지 않는다")):
            code, _out = self.run_it("R-195", "x", self.draft(INFO_DRAFT))
        self.assertIn("이미 있다", code)
        self.assertEqual(self.written("R-195_x.md"), "이미 있음\n")

    # -- PR 제목
    def merge_with_title(self, subject, sha="a" * 40, gate_head="a" * 40, gate=None, draft=MERGE_DRAFT):
        """브랜치 머리 커밋 제목(subject)을 읽은 것으로 가장하고 병합 부탁을 만든다. 돌려주는 값: (종료 값, 출력, 검사 관문, 제목 읽기 가짜)."""
        gate = gate or Gate(head=gate_head)
        with mock.patch.object(nt, "head_subject", return_value=(subject, sha, "ai/claude/r170-x")) as read:
            code, out = self.run_it("R-196", "merge-tool", self.draft(draft), "시험 통과", target=TARGET, gate=gate)
        return code, out, gate, read

    def test_the_pr_title_goes_into_the_file_verbatim_and_without_quotes(self):
        for subject in (PR_TITLE, "[R-196] 따옴표 \"두\" '작은' 역슬래시 \\ 와 \\1 — 한글 😀 [대상: 공통]", "[R-196] 끝에 점. 콜론: 있음 # 샵 @ 골뱅이", "x" * 200):
            self.setUp()
            code, out, _gate, read = self.merge_with_title(subject)
            self.assertIsNone(code, subject)
            text = self.written("R-196_merge-tool.md")
            self.assertIn(f"\npr_title: {subject}\n", text)
            self.assertIn(f"> {subject}\n", text)
            request = ol.parse_request("R-196_merge-tool.md", text, strict=True)
            self.assertEqual(dict(request.fields)["pr_title"], subject)
            read.assert_called_once_with(self.work / "wt_r30", "ai/claude/r170-x")
            self.assertIn(f"PR 제목(글자 그대로): {subject}", out)
            self.assertEqual(dict(request.fields)["verify"], "검사 3칸 초록")

    def test_a_secret_shaped_pr_title_stops_before_the_gate_and_is_never_echoed(self):
        """수정 1차(V1 M-1): 알림 실행이 '보내지 않음'이 될 제목(`key=`·`token=`·`secret=`·`AIza…`)을 도구가 만들기 전에 막고, 비밀 모양 글을 화면에 되풀이하지 않는다."""
        for subject in ("hotkey=Ctrl 설정", "[R-196] key=abc123 설정", "token=abc", "secret=1", "AIza" + "x" * 35, "ghp_" + "y" * 36, "123456789:" + "A" * 35, "[R-196] monkey=banana"):
            self.setUp()
            code, out, gate, _read = self.merge_with_title(subject, gate=Gate(head=None))
            self.assertStops(code, "그대로 쓸 수 없어 요청 파일을 만들지 않는다", "비밀(키·토큰)로 보이는 글", "화면에 적지 않는다")
            self.assertNotIn(subject, code + out, repr(subject))
            self.assertEqual(gate.calls, [], repr(subject))
        self.setUp()
        code, _out, _gate, _read = self.merge_with_title("[R-196] tokenizer=fast 사용")            # 낱말 경계가 있는 보통 글은 통과(런타임과 같다)
        self.assertIsNone(code, code)

    def test_a_pr_title_with_blank_looking_characters_stops_too(self):
        for code_point in nt.PR_TITLE_EXTRA_INVISIBLE_CODEPOINTS:
            self.setUp()
            code, _out, gate, _read = self.merge_with_title("[R-196] 가" + chr(code_point) + "나", gate=Gate(head=None))
            self.assertStops(code, "그대로 쓸 수 없어 요청 파일을 만들지 않는다", f"U+{code_point:04X}")
            self.assertEqual(gate.calls, [])

    def test_a_hand_written_pr_title_is_checked_like_the_automatic_one(self):
        for title, phrase in (("key=abc123 설정", "비밀(키·토큰)"), ("가" + chr(0x3164) + "나", "비어 보이는 글자"), ("가" + ZWSP + "나", "U+200B")):
            self.setUp()
            draft = MERGE_DRAFT.replace("pr_title: @PR_TITLE@", f"pr_title: {title}").replace("@PR_TITLE@", "직접 쓴 제목")
            code, _out = self.run_it("R-196", "merge-tool", self.draft(draft), "통과", "독립 검증 통과", "", TARGET, Gate(runs=9))
            self.assertStops(code, "앞머리 pr_title 을 그대로 쓸 수 없다", phrase)
            self.assertNotIn("key=abc123", code)                                                  # 비밀 모양 글을 되풀이하지 않는다

    def test_a_hand_written_notice_number_is_checked_before_the_file_is_written(self):
        """수정 1차(V2 L2): 손으로 쓴 `no`(표준 표기·kind 와 유형 일치·요청함에 이미 있는 번호가 아님)를 푸시 뒤 REQ-1 이 잡기 전에 도구가 잡는다."""
        for no, phrase in (("P0012", "앞에 0 을 더 붙인"), ("P12", "모양이 아니다"), ("P000", "모양이 아니다"), ("M007", "kind: info 와 맞지 않는다"), ("003", "kind: info 와 맞지 않는다"),
                           ("p012", "모양이 아니다")):
            self.setUp()
            code, _out = self.run_it("R-195", "x", self.draft(INFO_DRAFT.replace("no: @NO@", f"no: {no}")))
            self.assertStops(code, "앞머리 no:", phrase)
        self.setUp()
        (self.folder / "R-100_old.md").write_text(nth.notice_text(number=100, no="P012"), encoding="utf-8")
        code, _out = self.run_it("R-195", "dup", self.draft(INFO_DRAFT.replace("no: @NO@", "no: P012"), "dup.md"))
        self.assertIn("앞머리 no:", code)
        self.assertIn("이미 쓰고 있다", code)
        self.assertFalse((self.folder / "R-195_dup.md").exists())
        for no in ("P013", "M012", "P1000"):                                                   # 다른 숫자·다른 유형의 같은 숫자는 통과(kind 에 맞는 것만)
            number = "R-196" if no.startswith("M") else "R-195"                                # 초안의 id 와 같은 번호로 만든다
            draft = (MERGE_DRAFT.replace("no: M007", f"no: {no}").replace("pr_title: @PR_TITLE@", "pr_title: 직접 쓴 제목").replace("@PR_TITLE@", "직접 쓴 제목") if no.startswith("M")
                     else INFO_DRAFT.replace("no: @NO@", f"no: {no}"))
            name = f"{number}_ok-{no.lower()}.md"
            code, _out = self.run_it(number, f"ok-{no.lower()}", self.draft(draft, f"{no}.md"), "t", "독립 검증 통과", "", TARGET, Gate(runs=3))
            self.assertIsNone(code, (no, code))
            self.assertEqual(ol.parse_request(name, self.written(name), strict=True).no, no)

    def test_the_number_the_tool_chose_itself_is_not_checked_against_the_folder_again(self):
        """`@NO@` 는 요청함 파일까지 읽어 최댓값 + 1 로 정한 번호라 겹침 검사를 다시 하지 않는다(가짜 scan 이 폴더와 어긋나도 막지 않는다)."""
        (self.folder / "R-100_old.md").write_text(nth.notice_text(number=100, no="P012"), encoding="utf-8")
        with mock.patch.object(nn, "scan", return_value=scan_result(11, 0, 0)):                 # 가짜 scan 은 P011 까지라고 하고 폴더에는 P012 가 있다
            code, _out = self.run_it("R-195", "auto", self.draft(INFO_DRAFT))
        self.assertIsNone(code, code)
        self.assertEqual(nt.read_front(self.written("R-195_auto.md"))["no"], "P012")

    def test_the_desktop_repository_is_read_from_cd_repo(self):
        gate = Gate()
        with mock.patch.object(nt, "head_subject", return_value=("[R-196] 데스크톱 [대상: 데스크톱]", "a" * 40, "x")) as read:
            code, _out = self.run_it("R-196", "merge-tool", self.draft(MERGE_DRAFT), "t", target="shine88pc/chanceblog-desktop:ai/claude/r196-desk", gate=gate)
        self.assertIsNone(code)
        read.assert_called_once_with(self.work / "cd_repo", "ai/claude/r196-desk")
        self.assertEqual(gate.calls[0][0], "shine88pc/chanceblog-desktop:ai/claude/r196-desk")

    def test_an_unsafe_pr_title_stops_before_the_gate_and_before_any_file(self):
        for subject, phrase in (("[R-196] 보이지 않는" + ZWSP + "글자", "U+200B"), ("탭\t제목", "U+0009"), ("x" * 201, "201자"), ("", "비어"), ("   ", "비어"),
                                (" 앞 공백", "공백"), ("뒤 공백 ", "공백"), ("줄\r바꿈", "U+000D"), ("a" + chr(0x202E) + "b", "U+202E")):
            code, _out, gate, _read = self.merge_with_title(subject, gate=Gate(head=None))
            self.assertStops(code, "그대로 쓸 수 없어 요청 파일을 만들지 않는다", phrase)
            self.assertEqual(gate.calls, [], repr(subject))

    def test_a_title_that_cannot_be_read_stops_with_the_reason(self):
        with mock.patch.object(nt, "head_subject", side_effect=nt.TitleError("머리 커밋을 읽지 못했다")):
            code, _out = self.run_it("R-196", "merge-tool", self.draft(MERGE_DRAFT), "t", target=TARGET, gate=Gate(head=None))
        self.assertStops(code, "병합 PR 제목을 읽지 못했다", "머리 커밋을 읽지 못했다")

    def test_a_title_read_from_another_commit_than_the_gate_saw_is_refused(self):
        code, _out, gate, _read = self.merge_with_title(PR_TITLE, sha="1" * 40, gate_head="2" * 40)
        self.assertStops(code, "11111111", "22222222", "다르다")
        self.assertEqual(len(gate.calls), 1)

    def test_pr_title_placeholder_needs_a_merge_and_a_branch(self):
        self.assertStops(self.run_it("R-196", "x", self.draft(MERGE_DRAFT), "t", gate=Gate(head=None))[0], "마지막 인자로 소유자/저장소:브랜치")
        self.assertStops(self.run_it("R-196", "x", self.draft(MERGE_DRAFT.replace("kind: merge", "kind: info"), "i.md"), "t", target=TARGET, gate=Gate(head=None))[0], "kind: merge", "'info'")
        self.assertStops(self.run_it("R-197", "x", self.draft(OLD_DRAFT, "o.md"), "t", "v", "p", "", Gate(head=None))[0], "마지막 인자로 소유자/저장소:브랜치")

    def test_a_failed_gate_leaves_no_file(self):
        def failing(target, workspace):
            raise SystemExit("검사가 아직 끝나지 않았거나 초록이 아니다: 1(in_progress/-)")
        code, _out = self.run_it("R-197", "old-merge", self.draft(OLD_DRAFT), "t", "v", "p", TARGET, failing)
        self.assertStops(code, "검사가 아직 끝나지 않았거나")

    # -- 검사
    def test_leftovers_links_ids_names_and_lengths_stop_the_file(self):
        base = OLD_DRAFT.replace("kind: merge", "kind: info")
        self.assertStops(self.run_it("R-197", "x", self.draft(base + "@LINK@\n"))[0], "채우지 않은 자리표시자: @LINK@")
        self.assertStops(self.run_it("R-197", "x", self.draft(base + "번호 @NO@\n", "n.md"))[0], "@NO@")
        self.assertStops(self.run_it("R-197", "x", self.draft(base + "http://example.invalid/a\n", "l.md"))[0], "링크 주소(http…)")
        self.assertStops(self.run_it("R-197", "x", self.draft(base + "https://example.invalid/a\n", "l2.md"))[0], "링크 주소(http…)")
        self.assertStops(self.run_it("R-197", "x", self.draft(base.replace("id: R-197", "id: R-111"), "i.md"))[0], "id(R-111)", "번호(R-197)")
        self.assertStops(self.run_it("R-197", "x", self.draft(base.replace("title: [R-197] 병합 부탁 — 옛 모양", "title: " + "가" * 81), "t.md"))[0], "앞머리 길이 초과", "title 81/80")
        self.assertStops(self.run_it("r-197", "x", self.draft(base, "r.md"))[0], "모양이 아니다")
        self.assertStops(self.run_it("R-197", "Bad_Slug", self.draft(base, "s.md"))[0], "모양이 아니다")
        self.assertStops(self.run_it("R-197", "../x", self.draft(base, "p.md"))[0], "모양이 아니다")

    def test_every_new_field_has_its_limit(self):
        def limited(**fields):
            data = {"id": "R-197", "kind": "info", "title": "t", "summary": "s", "no": "P012", **fields}
            return "---\n" + "".join(f"{key}: {value}\n" for key, value in data.items()) + "---\n본문\n"
        for key, limit in (("title", 80), ("summary", 300), ("now", 200), ("changed", 200), ("next", 200), ("waiting", 200), ("eta", 100), ("check", 60), ("target", 100),
                           ("verify", 120), ("state", 40), ("pr_title", 200)):
            self.setUp()
            self.assertIsNone(self.run_it("R-197", "ok", self.draft(limited(**{key: "가" * limit})))[0], key)
            self.setUp()
            code, _out = self.run_it("R-197", "over", self.draft(limited(**{key: "가" * (limit + 1)})))
            self.assertStops(code, "앞머리 길이 초과", f"{key} {limit + 1}/{limit}")
        self.setUp()
        code, _out = self.run_it("R-197", "opt", self.draft(limited(options="가 / " + "나" * 61)))
        self.assertStops(code, "options 보기 2번 61/60")

    def test_the_length_after_the_pr_title_is_filled_is_what_counts(self):
        long_summary = MERGE_DRAFT.replace("summary: 병합할 PR 제목 → 「@PR_TITLE@」 이 제목 하나만 병합합니다.", "summary: " + "가" * 120 + "「@PR_TITLE@」")
        self.assertNotEqual(long_summary, MERGE_DRAFT)
        code, _out, _gate, _read = self.merge_with_title("나" * 100, draft=long_summary)                # 채우기 전 132자, 채운 뒤 222자
        self.assertIsNone(code, code)
        self.setUp()
        code, _out, gate, _read = self.merge_with_title("나" * 200, draft=long_summary, gate=Gate(head="a" * 40))  # 채운 뒤 322자
        self.assertStops(code, "앞머리 길이 초과", "summary 322/300")
        self.assertEqual(gate.calls, [])                                                                  # 길이 검사는 검사 관문(인터넷)보다 먼저다

    def test_missing_pieces_are_explained_not_crashed(self):
        self.assertIn("사용:", make_request.__doc__)
        with self.assertRaises(SystemExit) as caught:
            make_request.main(["R-197", "x", "d.md"], workspace=self.work)
        self.assertIn("사용:", caught.exception.code)
        (self.work / "nofolder" / "wt_r30").mkdir(parents=True)
        (self.work / "nofolder" / "d.md").write_text(OLD_DRAFT, encoding="utf-8")
        code, _out = run_main(["R-197", "x", "d.md", "", "", ""], self.work / "nofolder")
        self.assertIn("요청함 폴더가 없다", code)
        with self.assertRaises(FileNotFoundError):
            run_main(["R-197", "x", "nodraft.md", "", "", ""], self.work)


# ==== 진짜 git(임시 저장소 하나) =================================================================
def fast_import(repo, commits):
    """commits: [(ref, 표식 번호, 부모 표식 번호 또는 None, 제목, {경로: 내용})] 를 `git fast-import` 한 번으로 만든다(원격 가지는 refs/remotes/origin/… 로 흉내).
    돌려주는 값: {표식 번호: 커밋 해시} — fast-import 가 직접 적어 주는 값이라 다른 git 호출 없이 정답 해시를 안다."""
    marks = Path(repo) / ".git" / "marks-under-test.txt"
    stream = bytearray()
    for ref, mark, parent, message, files in commits:
        text = (message + "\n").encode()
        stream += f"commit {ref}\nmark :{mark}\ncommitter tester <tester@example.com> 1700000000 +0900\ndata {len(text)}\n".encode() + text
        if parent is not None:
            stream += f"from :{parent}\n".encode()
        for path, content in files.items():
            data = content.encode()
            stream += f"M 100644 inline {path}\ndata {len(data)}\n".encode() + data + b"\n"
        stream += b"\n"
    done = subprocess.run(["git", "-C", str(repo), "fast-import", "--quiet", f"--export-marks={marks}"], check=False, input=bytes(stream), capture_output=True)
    if done.returncode:
        raise AssertionError(done.stderr.decode("utf-8", "replace"))
    return {int(line.split()[0][1:]): line.split()[1] for line in marks.read_text(encoding="utf-8").splitlines()}


MAIN_FILES = {
    f"{FOLDER}/README.md": fm("no: P077"),
    f"{FOLDER}/R-001_old.md": fm("id: R-001", "kind: info", "title: t", "summary: s"),
    f"{FOLDER}/R-168_progress-p010.md": fm("id: R-168", "kind: info", "no: P010"),
    f"{FOLDER}/R-169_merge-m004.md": fm("id: R-169", "kind: merge", "no: M004"),
    f"{FOLDER}/R-170_ask-quoted.md": fm("id: R-170", "kind: decision", 'no: "007"'),
    f"{FOLDER}/R-171_body-only.md": fm("id: R-171", body="no: P090\n"),
    f"{FOLDER}/R-172_unclosed-front.md": long_front("no: P095", 42),
    f"{FOLDER}/R-173_close-at-41.md": long_front("no: P011", 41),
    f"{FOLDER}/R-174_bad-no.md": fm("no: P12345"),
    f"{FOLDER}/R-175_not-markdown.txt": fm("no: P080"),
    f"{FOLDER}/old/R-180_sub.md": fm("no: P060"),
    "docs/R-190_outside.md": fm("no: P070"),
}
COMMITS = [
    ("refs/remotes/origin/main", 1, None, "main", MAIN_FILES),
    ("refs/remotes/origin/ai/claude/x", 2, 1, "x", {f"{FOLDER}/R-176_progress-p013.md": fm("no: P013"), f"{FOLDER}/R-177_merge-m009.md": fm("no: M009")}),
    ("refs/remotes/origin/ai/codex/y", 3, 1, "y", {f"{FOLDER}/R-178_ask-011.md": fm('no: "011"')}),
    ("refs/remotes/other/ai/claude/z", 4, 1, "z", {f"{FOLDER}/R-181_other.md": fm("no: P500")}),
    ("refs/remotes/origin/feature/q", 5, 1, "q", {f"{FOLDER}/R-182_feature.md": fm("no: P600")}),
    ("refs/heads/local-only", 6, 1, "local", {f"{FOLDER}/R-179_ask-local.md": fm('no: "012"')}),
    ("refs/heads/ai/claude/r170-x", 7, 1, PR_TITLE, {}),
    ("refs/remotes/origin/ai/claude/r171-remote-only", 8, 1, REMOTE_TITLE, {}),
]


class RealGitTest(unittest.TestCase):
    """진짜 git 으로 한 번만: 임시 작업 폴더 W 의 wt_r30 에 원격 가지(refs/remotes/origin/…)와 로컬 가지를 흉내 낸 저장소를 만들고 읽는다. 준비에 git 호출이 많아 한 번만 만든다."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.work = Path(cls._tmp.name) / "W"
        cls.repo = cls.work / "wt_r30"
        cls.folder = cls.repo / "인수인계" / "요청함"
        cls.folder.mkdir(parents=True)
        nh.git(cls.repo, "init", "-q", "-b", "main")
        cls.title_sha = fast_import(cls.repo, COMMITS)[7]                        # 표식 7 = 로컬 가지 ai/claude/r170-x 의 머리 커밋
        for name, text in (("R-183_merge-m030.md", fm("no: M030")), ("README.md", fm("no: M099"))):      # 아직 커밋·push 전인 작업 파일(요청 파일 하나와 README)
            (cls.folder / name).write_text(text, encoding="utf-8", newline="\n")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_one_real_scan_through_the_command_line_reads_every_source_in_three_git_calls(self):
        """make_request.py 가 쓰는 것과 같은 읽기(저장소 wt_r30 + 로컬 가지 + 그 폴더의 아직 push 전인 작업 파일)를 명령 줄로 한 번만 진짜 git 으로 돌린다. 유형마다 이긴 출처가 달라
        (진행 현황은 원격 가지 x, 병합 요청은 작업 폴더, 확인 요청은 로컬 가지) 한 번의 출력으로 세 출처가 모두 읽혔음이 드러나고, 이긴 값에 가려진 출처는 read_git 이 돌려준 목록으로 본다."""
        captured, out, err = [], io.StringIO(), io.StringIO()
        real_read_git = nn.read_git

        def spy(*args, **kwargs):
            captured.append(real_read_git(*args, **kwargs))
            return captured[-1]
        with mock.patch.object(nn, "read_git", side_effect=spy), mock.patch.object(nn.subprocess, "run", wraps=subprocess.run) as run, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = nn.main(["--repo", str(self.repo), "--dir", str(self.repo), "--local"])
        self.assertEqual((code, err.getvalue()), (0, ""))
        self.assertEqual(run.call_count, 3)                                                  # 가지 수와 상관없이 git 세 번(for-each-ref 한 번 + cat-file 두 번)
        self.assertEqual(out.getvalue().splitlines(), ["P 다음 번호: P014 (지금 최댓값 P013 — R-176_progress-p013.md @ origin/ai/claude/x)",
                                                       f"M 다음 번호: M031 (지금 최댓값 M030 — R-183_merge-m030.md @ 폴더 {self.repo})",
                                                       "확인 다음 번호: 013 (지금 최댓값 012 — R-179_ask-local.md @ heads/local-only)"])
        seen = {}
        for name, where, numbers in captured[0]:
            seen.setdefault(name, {"where": set(), "numbers": numbers})["where"].add(where)
        # 센 것만: main 의 번호 파일 4개(41번째 줄에서 닫는 앞머리 포함)·가지 x·y·로컬 가지의 파일. 세지 않은 것: README P077·본문 P090·닫히지 않은 앞머리 P095·모양 아닌 값 P12345·
        # .txt P080·하위 폴더 P060·요청함 밖 P070·다른 원격 P500·origin/feature P600
        self.assertEqual({name: item["numbers"] for name, item in seen.items()}, {
            "R-168_progress-p010.md": [("progress", 10)], "R-169_merge-m004.md": [("merge", 4)], "R-170_ask-quoted.md": [("ask", 7)], "R-173_close-at-41.md": [("progress", 11)],
            "R-176_progress-p013.md": [("progress", 13)], "R-177_merge-m009.md": [("merge", 9)], "R-178_ask-011.md": [("ask", 11)], "R-179_ask-local.md": [("ask", 12)]})
        self.assertEqual(seen["R-176_progress-p013.md"]["where"], {"origin/ai/claude/x"})
        self.assertEqual(seen["R-177_merge-m009.md"]["where"], {"origin/ai/claude/x"})
        self.assertEqual(seen["R-178_ask-011.md"]["where"], {"origin/ai/codex/y"})                      # `ai/codex/y` 두 단계 이름도 찾는다
        self.assertEqual(seen["R-179_ask-local.md"]["where"], {"heads/local-only"})
        self.assertIn("origin/main", seen["R-168_progress-p010.md"]["where"])
        self.assertNotIn("origin/feature/q", {where for item in seen.values() for where in item["where"]})
        self.assertEqual(nn.next_numbers(nn.scan(None, dirs=[self.repo], warn=lambda message: None)), {"progress": "P001", "merge": "M031", "ask": "001"})     # 작업 폴더만 읽으면 그 파일뿐

    def test_head_subject_falls_back_to_the_remote_tracking_branch(self):
        subject, sha, ref = nt.head_subject(self.repo, "ai/claude/r171-remote-only")
        self.assertEqual((subject, ref), (REMOTE_TITLE, "origin/ai/claude/r171-remote-only"))
        self.assertRegex(sha, r"^[0-9a-f]{40}$")

    def test_make_request_fills_the_pr_title_from_the_real_branch_head_and_the_check_count(self):
        (self.work / "merge.md").write_text(MERGE_DRAFT, encoding="utf-8", newline="\n")
        gate = Gate(head=self.title_sha, runs=3)
        code, out = run_main(["R-196", "merge-tool", "merge.md", "단위 시험 전부 통과", "", "", "shine88pc/chanceblog:ai/claude/r170-x"], self.work, gate)
        self.assertIsNone(code, code)
        text = (self.folder / "R-196_merge-tool.md").read_text(encoding="utf-8")
        request = ol.parse_request("R-196_merge-tool.md", text, strict=True)
        fields = dict(request.fields)
        self.assertEqual((fields["pr_title"], fields["verify"], request.no), (PR_TITLE, "검사 3칸 초록", "M007"))
        self.assertIn(f"\npr_title: {PR_TITLE}\n", text)
        self.assertIn(f"「{PR_TITLE}」", request.summary)
        self.assertIn("검증 문구가 비어 있어 `검사 3칸 초록` 으로 채웠다", out)
        self.assertEqual(gate.calls, [("shine88pc/chanceblog:ai/claude/r170-x", self.work)])
        message = notify.format_notice(request.no, dict(request.fields))                         # 폰 글에도 같은 제목이 그대로 간다(이스케이프만 다름)
        self.assertIn("PR 제목: <code>" + PR_TITLE.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</code>", message)


# ==== 배포·문법·문서 ==============================================================================
class ShippingAndSyntaxTest(unittest.TestCase):
    TOOL_FILES = ("next_notice_no.py", "notice_tools.py", "make_request.py", "make_info_request.py")

    def test_the_scripts_read_without_syntax_errors_in_the_python_3_10_grammar(self):
        for name in self.TOOL_FILES + ("../setup_workspace.py",):
            source = (WORK / name).read_text(encoding="utf-8")
            ast.parse(source, filename=name, feature_version=(3, 10))
            self.assertTrue(source.endswith("\n"), name)
        source = Path(__file__).read_text(encoding="utf-8")
        ast.parse(source, filename="test_notice_tools.py", feature_version=(3, 10))

    def test_setup_workspace_ships_the_new_tools_and_the_wrapper_runs_from_the_copy(self):
        spec = importlib.util.spec_from_file_location("setup_workspace_under_test", TOOLS / "setup_workspace.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "W"
            with contextlib.redirect_stdout(io.StringIO()):
                module.copy_tools(target)
            for name in self.TOOL_FILES:
                self.assertTrue((target / name).is_file(), name)
            (target / "wt_r30" / "인수인계" / "요청함").mkdir(parents=True)
            (target / "draft.md").write_text(OLD_DRAFT.replace("kind: merge", "kind: info").replace("R-197", "R-198"), encoding="utf-8", newline="\n")
            done = subprocess.run([sys.executable, "-X", "utf8", str(target / "make_info_request.py"), "R-198", "wrapper-note", "draft.md"], check=False, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("파일 R-198_wrapper-note.md", done.stdout)
            self.assertTrue((target / "wt_r30" / "인수인계" / "요청함" / "R-198_wrapper-note.md").is_file())


class DocumentsTest(unittest.TestCase):
    DOCS = ("README.md", "정기_현황_알림_프롬프트.txt", "정기_현황_알림_본보기.md")

    def read(self, name):
        return (TOOLS / name).read_text(encoding="utf-8")

    def test_no_template_marks_secret_shapes_or_links_were_added(self):
        for name in self.DOCS:
            text = self.read(name)
            self.assertNotIn("{{", text, name)
            self.assertNotIn("{%", text, name)
            self.assertIsNone(re.search(r"[0-9]{6,}:[A-Za-z0-9_-]{30,}", text), name)               # 토큰 모양(숫자:영숫자 30자 이상)
            self.assertNotIn("](http", text, name)
        for name in self.DOCS[1:]:
            self.assertIsNone(re.search(r"https?://", self.read(name)), name)

    def test_the_example_front_matter_in_the_model_document_is_read_by_the_real_parser(self):
        text = self.read("정기_현황_알림_본보기.md")
        boxes = re.findall(r"```[a-z]*\n(.*?)\n```", text, re.DOTALL)
        sample = next(box for box in boxes if box.startswith("---\n"))
        request = ol.parse_request("R-170_progress-p012.md", sample + "\n", strict=True)
        self.assertEqual((request.id, request.kind, request.no), ("R-170", "info", "P012"))
        self.assertEqual({key for key, _value in request.fields}, set(ol.PROGRESS_KEYS))
        for key in ol.PROGRESS_KEYS:
            self.assertIn(f"`{key}`", text, key)
        lines = notify.format_notice(request.no, dict(request.fields)).splitlines()
        self.assertEqual(lines[0], f"{notify.PROGRESS_MARK} <b>P012 · 진행 현황</b> · 11-06 12:07 기준 · 점검 이상 없음")
        self.assertEqual([line.split(":")[0] for line in lines[1:]], ["현재 진행", "직전 보고 이후", "다음 계획", "예상 완료", "확인·승인 대기"])
        body = sample.split("\n---\n", 1)[1]
        self.assertIn("## 점검 결과", body)                                                # 본문에 점검표와 진행표가 있다
        self.assertIn("## 진행 중인 일", body)
        self.assertEqual(len(boxes), 1, "본보기 코드 상자는 요청 파일 하나뿐이다")

    def test_the_cron_prompt_has_the_new_rules_and_not_the_old_ones(self):
        text = self.read("정기_현황_알림_프롬프트.txt")
        self.assertEqual((text.count("=== 프롬프트 시작 ==="), text.count("=== 프롬프트 끝 ===")), (1, 1))
        block = text[text.index("=== 프롬프트 시작 ==="):text.index("=== 프롬프트 끝 ===")]
        for phrase in ("230분", "3시간 50분", "12시간", "변화 없음", "next_notice_no.py", "진행 현황 P", "M004 발송", "즉시", "no: @NO@", "시간대 제한은 없다", "앱 푸시"):
            self.assertIn(phrase, block, phrase)
        for stale in ("50분 이상", "50분 미만"):
            self.assertNotIn(stale, text, stale)
        self.assertIn("7 * * * *", text)
        for key in ("at", "now", "changed", "next", "eta", "waiting", "check"):
            self.assertIn(f"`{key}`", block, key)

    def test_the_tools_readme_describes_the_new_tool_and_rules(self):
        text = self.read("README.md")
        for phrase in ("next_notice_no.py", "notice_tools.py", "@NO@", "@PR_TITLE@", "230분", "M004 발송", "정기_현황_알림_본보기.md"):
            self.assertIn(phrase, text, phrase)
        self.assertNotIn("50분 이상", text)
        self.assertEqual(text.count("| `next_notice_no.py` |"), 1)


if __name__ == "__main__":
    unittest.main()
