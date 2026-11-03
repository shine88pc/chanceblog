"""Unsplash 사진 출처·ixid 공용 모듈(pipeline/unsplash_credit.py) 단위 시험 — 순수 함수라 네트워크도 파일도 쓰지 않는다.

구성
  1) ixid: 값 모양 표(영숫자·_ - =, 1~200자, 정확히 하나)·주소 만들기(맨 앞에 남김, 틀리면 빼고 계속).
  2) 작가 이름 정리: 보이지 않는 문자·제어 문자·중괄호(Liquid)·길이 80자·보이는 글자 없음.
  3) 마크다운 이스케이프와 출처 줄: 특수문자 하나하나·악성 이름·정확한 모양·utm.
  4) 프로필 주소·응답 한 건에서 작가 읽기·고정 목록 조회용 번호·download 주소.
  5) 우리 줄 알아보기(위조 방지)·지우기·넣기·멱등·검증용 문제 목록.
"""
import ast
import re
import time
import unittest
from pathlib import Path

import _bootstrap
from pipeline import console, unsplash_credit as uc
from pipeline.publishers import issue_package

ESC = chr(92)                                   # 역슬래시 — 소스에 이스케이프를 쓰지 않으려고 코드 포인트로 만든다
BASE = "https://images.unsplash.com/photo-1507146426996-ef05306b995a"
PARAMS = "?auto=format&fit=crop&w=1000&q=80"
PROFILE = "https://unsplash.com/@janedoe"
UTM = "utm_source=chanceblog&utm_medium=referral"
LINE = f"*Photo by [Jane Doe]({PROFILE}?{UTM}) on [Unsplash](https://unsplash.com/?{UTM})*"


def unescape(text):
    """출처 줄의 이름 칸을 마크다운 규칙대로 푼다(역슬래시 + 글자 → 글자)."""
    out, i = [], 0
    while i < len(text):
        if text[i] == ESC and i + 1 < len(text):
            i += 1
        out.append(text[i])
        i += 1
    return "".join(out)


def unescaped_marks(text, marks):
    """역슬래시로 이스케이프되지 않은 marks 글자의 개수."""
    count, i = 0, 0
    while i < len(text):
        if text[i] == ESC:
            i += 2
            continue
        count += text[i] in marks
        i += 1
    return count


def name_part(line):
    """출처 줄에서 이름 칸(`*Photo by [` 와 `](https://unsplash.com/@` 사이)."""
    return line[len("*Photo by ["):line.index("](https://unsplash.com/@")]


class ConstantsTest(unittest.TestCase):
    def test_the_utm_value_is_the_one_the_draft_packages_use(self):
        self.assertEqual(uc.UTM, issue_package.UNSPLASH_UTM)
        self.assertEqual(uc.UTM, UTM)

    def test_the_marker_and_the_fixed_tail_of_our_line(self):
        self.assertEqual(uc.CREDIT_MARKER, f" on [Unsplash](https://unsplash.com/?{UTM})*")
        self.assertTrue(LINE.endswith(uc.CREDIT_MARKER))

    def test_the_module_uses_only_the_standard_library(self):
        tree = ast.parse(Path(uc.__file__).read_text(encoding="utf-8"))
        names = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        names |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        self.assertEqual(names, {"re", "unicodedata", "urllib"})

    def test_the_module_does_no_io(self):
        source = Path(uc.__file__).read_text(encoding="utf-8")
        for needle in ("open(", "urlopen", "print(", "os.environ", "subprocess", "socket"):
            self.assertNotIn(needle, source, needle)

    def test_every_invisible_code_point_the_logs_know_is_removed_from_names(self):
        for code in console.INVISIBLE_CODEPOINTS:
            self.assertEqual(uc.clean_name(f"Ja{chr(code)}ne"), "Jane", hex(code))


class IxidTest(unittest.TestCase):
    VALID = ("M3wxfDB8", "a", "A" * 200, "aZ09_-=", "=", "-", "_", "MXwxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHw=", "eyJhcHBfaWQiOjEyMDd9")
    INVALID = ("", "A" * 201, "a b", "a+b", "a/b", "a:b", "a&b", "a%b", "a;b", "a,b", "a.b", "a@b", "a!b", "a" + ESC + "b", "a'b", 'a"b', "a<b", "한글", "a\nb", "a\x00b", "a\tb", "ａｂ")

    def test_the_value_shape_table(self):
        for value in self.VALID:
            self.assertEqual(uc.ixid_from_query(f"ixid={value}"), value, value)
        for value in self.INVALID:
            from urllib.parse import quote
            self.assertEqual(uc.ixid_from_query("ixid=" + quote(value, safe="")), "", repr(value))

    def test_exactly_one_ixid_is_read_wherever_it_stands(self):
        for query in ("ixid=M3w", "a=1&ixid=M3w", "ixid=M3w&a=1", "ixlib=rb-4.0.3&ixid=M3w&w=9"):
            self.assertEqual(uc.ixid_from_query(query), "M3w", query)

    def test_missing_duplicate_or_lookalike_keys_give_nothing(self):
        for query in ("", "a=1", "ixlib=rb", "ixid", "ixid=", "ixid=a&ixid=b", "ixid=a&ixid=a", "IXID=a", "Ixid=a", "xixid=a", "ixidx=a", "ixid%3D=a", "ix_id=a", " ixid=a", "ixid =a"):
            self.assertEqual(uc.ixid_from_query(query), "", repr(query))

    def test_percent_encoding_is_decoded_before_the_shape_check(self):
        self.assertEqual(uc.ixid_from_query("ixid=MXwx%3D"), "MXwx=")
        self.assertEqual(uc.ixid_from_query("ixid=MXwx%3d"), "MXwx=")
        self.assertEqual(uc.ixid_from_query("ixid=a%20b"), "")               # 디코딩하면 공백 — 틀린 값
        self.assertEqual(uc.ixid_from_query("ixid=a%26b"), "")               # 디코딩하면 `&` — 값에 다른 매개변수를 끼워 넣는 길을 막는다
        self.assertEqual(uc.ixid_from_query("ixid=%3Cscript%3E"), "")

    def test_non_strings_and_huge_queries_give_nothing(self):
        for query in (None, 5, [], {}, b"ixid=a", "x" * 2001, "ixid=a&" + "z=1&" * 600):
            self.assertEqual(uc.ixid_from_query(query), "", repr(query)[:40])
        self.assertEqual(uc.ixid_from_query("ixid=a&" + "z=1&" * 100), "a")  # 상한(2000자) 안이면 읽는다

    def test_with_ixid_puts_the_value_first_and_keeps_the_size_parameters(self):
        self.assertEqual(uc.with_ixid(BASE, "ixid=M3wx&ixlib=rb-4.0.3", PARAMS), f"{BASE}?ixid=M3wx&auto=format&fit=crop&w=1000&q=80")
        self.assertEqual(uc.with_ixid(BASE, "ixid=M3wx", "?w=1080&q=80"), f"{BASE}?ixid=M3wx&w=1080&q=80")

    def test_without_a_good_ixid_it_is_the_old_address(self):
        for query in ("", "ixlib=rb-4.0.3", "ixid=a b", "ixid=a&ixid=b", None):
            self.assertEqual(uc.with_ixid(BASE, query, PARAMS), f"{BASE}{PARAMS}", repr(query))

    def test_params_without_a_question_mark_and_empty_params(self):
        self.assertEqual(uc.with_ixid(BASE, "ixid=M3wx", "w=9"), f"{BASE}?ixid=M3wx&w=9")
        self.assertEqual(uc.with_ixid(BASE, "ixid=M3wx", ""), f"{BASE}?ixid=M3wx")
        self.assertEqual(uc.with_ixid(BASE, "ixid=M3wx", "?"), f"{BASE}?ixid=M3wx")

    def test_the_other_query_values_never_leak_into_the_address(self):
        out = uc.with_ixid(BASE, "ixid=M3wx&utm_source=x&token=SECRET&ixlib=rb", PARAMS)
        for needle in ("utm_source", "SECRET", "ixlib", "token"):
            self.assertNotIn(needle, out)


class CleanNameTest(unittest.TestCase):
    def test_ordinary_names_pass_unchanged(self):
        for name in ("Jane Doe", "Alexandre Debiève", "김하늘", "O'Brien", "Jean-Luc Picard", "  spaced   out  ", "日本語の名前", "Zoë 🙂"):
            self.assertEqual(uc.clean_name(name), " ".join(name.split()), name)

    def test_invisible_and_format_characters_are_removed(self):
        for char in ("\u200b", "\u200c", "\u200d", "\u200e", "\u200f", "\u202e", "\u202a", "\u2060", "\u2066", "\u2069", "\ufeff", "\u00ad", "\u061c", chr(0xE0041)):
            self.assertEqual(uc.clean_name(f"Ja{char}ne{char}"), "Jane", hex(ord(char)))

    def test_blank_lookalikes_are_removed(self):
        for char in ("\u115f", "\u1160", "\u3164", "\uffa0", "\u2800", "\u180e"):
            self.assertEqual(uc.clean_name(f"Ja{char}ne"), "Jane", hex(ord(char)))
            self.assertEqual(uc.clean_name(char * 5), "", hex(ord(char)))      # 그것뿐인 이름은 이름이 아니다

    def test_control_characters_and_odd_spaces_become_one_space(self):
        for char in ("\n", "\r", "\r\n", "\t", "\x00", "\x1b", "\x85", "\u2028", "\u2029", "\xa0", "\u3000", "\u2003", "\x0b", "\x0c"):
            self.assertEqual(uc.clean_name(f"Jane{char}Doe"), "Jane Doe", repr(char))

    def test_liquid_braces_are_removed_so_no_tag_can_start(self):
        for name, want in (("{{ site.title }}", "site.title"), ("{% include x %}", "% include x %"), ("a{b}c", "abc"), ("}}{{", ""), ("{", "")):
            out = uc.clean_name(name)
            self.assertEqual(out, want, name)
            self.assertNotIn("{", out)
            self.assertNotIn("}", out)

    def test_lone_surrogates_and_private_use_characters_are_removed(self):
        self.assertEqual(uc.clean_name("Jane \ud800Doe"), "Jane Doe")
        self.assertEqual(uc.clean_name("Jane \udc00Doe\ue000"), "Jane Doe")

    def test_length_limit_is_eighty_characters(self):
        self.assertEqual(uc.NAME_MAX, 80)
        self.assertEqual(uc.clean_name("N" * 80), "N" * 80)
        for size in (81, 200, 5000):
            out = uc.clean_name("N" * size)
            self.assertEqual(len(out), 80, size)
            self.assertTrue(out.endswith("…"))
        self.assertEqual(len(uc.clean_name("가" * 500)), 80)
        self.assertEqual(uc.clean_name("N" * 200, limit=10), "N" * 9 + "…")

    def test_names_without_a_visible_character_or_not_text_give_nothing(self):
        for value in ("", "   ", "\n\t", "\u200b", "{}", "{{ }}", chr(0x301), chr(0x301) + chr(0x302), chr(0xFE0F), None, 5, [], {"a": 1}, b"Jane", True):
            self.assertEqual(uc.clean_name(value), "", repr(value))

    def test_a_name_made_only_of_punctuation_is_still_a_visible_name(self):
        self.assertEqual(uc.clean_name("..."), "...")
        self.assertEqual(uc.clean_name("★"), "★")


class EscapeTest(unittest.TestCase):
    SPECIALS = "[]()<>*_`|#" + ESC

    def test_each_markdown_special_character_gets_a_backslash(self):
        for char in self.SPECIALS:
            self.assertEqual(uc.escape_md(f"a{char}b"), f"a{ESC}{char}b", repr(char))

    def test_other_characters_are_untouched(self):
        text = "Jane Doe 김하늘 O'Brien - & ! ? ~ . , : ; = + / @ $ % ^ \" é"
        self.assertEqual(uc.escape_md(text), text)

    def test_a_backslash_is_escaped_once_and_not_twice(self):
        self.assertEqual(uc.escape_md(ESC + "*"), ESC + ESC + ESC + "*")
        self.assertEqual(uc.escape_md(ESC * 3), ESC * 6)

    def test_unescaping_gives_back_the_text(self):
        text = "a[b]c(d)e<f>g*h_i`j|k#l" + ESC + "m"
        self.assertEqual(unescape(uc.escape_md(text)), text)


class CreditMarkdownTest(unittest.TestCase):
    def test_the_exact_line(self):
        self.assertEqual(uc.credit_markdown("Jane Doe", PROFILE), LINE)

    def test_both_links_carry_the_utm_parameters(self):
        self.assertEqual(LINE.count(UTM), 2)
        self.assertIn(f"]({PROFILE}?{UTM})", LINE)
        self.assertIn(f"](https://unsplash.com/?{UTM})*", LINE)

    def test_the_line_is_one_markdown_paragraph_without_raw_html(self):
        line = uc.credit_markdown("Jane <b>&Co</b> \"x\"", PROFILE)
        self.assertNotIn("\n", line)
        self.assertEqual(line.count("<"), line.count(ESC + "<"))              # 꺾쇠는 모두 이스케이프돼 HTML 로 읽히지 않는다
        self.assertEqual(line.count(">"), line.count(ESC + ">"))
        self.assertFalse(line.startswith(" "))
        self.assertTrue(line.startswith("*Photo by ["))

    def test_hostile_names_cannot_open_close_or_add_markup(self):
        names = ("]( https://evil.example ) [x", "x](https://evil.example)", "*bold*", "_it_", "`code`", "# heading", "| a | b |", "<script>alert(1)</script>", "<img src=x onerror=y>",
                 "[a](b)", "![x](https://evil.example/p.png)", ESC, ESC + "]", "a" + ESC + "*b", "**", "__", "- item", "1. item", "> quote", "<https://evil.example>",
                 "{{ 7*7 }}", "{% raw %}", "{%", "%}", "javascript:alert(1)", "https://evil.example", "a\nb\n\n# x", "x" * 79 + "*")
        for name in names:
            line = uc.credit_markdown(name, PROFILE)
            self.assertTrue(line, repr(name))
            self.assertTrue(uc.is_credit_line(line), repr(name))
            part = name_part(line)
            for char in "[]()<>*_`|#":
                self.assertEqual(unescaped_marks(part, char), 0, (name, char))     # 이름 칸에는 이스케이프되지 않은 특수문자가 없다
            self.assertEqual(unescaped_marks(line, "[]"), 4, name)                 # 틀의 대괄호 네 개뿐
            self.assertEqual(unescaped_marks(line, "()"), 4, name)
            self.assertEqual(unescaped_marks(line, "<>"), 0, name)
            self.assertEqual(unescaped_marks(line, "*"), 2, name)
            self.assertNotIn("{", line)
            self.assertNotIn("}", line)
            self.assertEqual(line.count("](https://unsplash.com/"), 2, name)         # 링크 주소는 우리 두 개뿐 — 이름 칸의 `](` 는 이스케이프돼 새 링크가 되지 않는다

    def test_the_visible_name_is_the_cleaned_name(self):
        for name in ("Jane Doe", "O'Brien & Co", "a[b]c", "x*y_z", "가*나"):
            self.assertEqual(unescape(name_part(uc.credit_markdown(name, PROFILE))), uc.clean_name(name), name)

    def test_invisible_characters_never_reach_the_line(self):
        line = uc.credit_markdown("Ja\u200bne\u202e Doe\x00\n", PROFILE)
        self.assertEqual(name_part(line), "Jane Doe")
        for char in line:
            self.assertNotIn(char, "\u200b\u202e\x00\n\r")

    def test_the_name_is_cut_at_eighty_characters(self):
        line = uc.credit_markdown("N" * 500, PROFILE)
        self.assertEqual(len(unescape(name_part(line))), 80)

    def test_a_name_or_profile_that_fails_the_checks_gives_no_line(self):
        for name, profile in (("", PROFILE), ("   ", PROFILE), ("\u200b", PROFILE), ("{}", PROFILE), (None, PROFILE), (5, PROFILE),
                              ("Jane", ""), ("Jane", None), ("Jane", "https://evil.example/@jane"), ("Jane", "http://unsplash.com/@jane"), ("Jane", "https://unsplash.com/jane"),
                              ("Jane", "https://unsplash.com/@" + "a" * 65), ("Jane", 'https://unsplash.com/@jane"x')):
            self.assertEqual(uc.credit_markdown(name, profile), "", (name, profile))

    def test_the_query_of_the_profile_is_replaced_by_our_utm(self):
        line = uc.credit_markdown("Jane", PROFILE + "?utm_source=other&x=1")
        self.assertIn(f"]({PROFILE}?{UTM})", line)
        self.assertNotIn("other", line)


class ProfileUrlTest(unittest.TestCase):
    def test_valid_profile_addresses(self):
        for raw in ("https://unsplash.com/@janedoe", "https://unsplash.com/@jane.doe-1_x", "https://unsplash.com/@" + "a" * 64, "  https://unsplash.com/@janedoe\n"):
            self.assertEqual(uc.safe_profile_url(raw), raw.strip().split("?")[0], raw)

    def test_a_query_and_a_fragment_are_dropped(self):
        for raw in ("https://unsplash.com/@janedoe?utm_source=x&a=b", "https://unsplash.com/@janedoe#top", "https://unsplash.com/@janedoe?a=b#top"):
            self.assertEqual(uc.safe_profile_url(raw), "https://unsplash.com/@janedoe")

    def test_everything_else_is_refused(self):
        bad = ("http://unsplash.com/@jane", "https://www.unsplash.com/@jane", "https://unsplash.com.evil.example/@jane", "https://evil.example/@jane", "https://evil.example/https://unsplash.com/@jane",
               "https://UNSPLASH.COM/@jane", "https://user@unsplash.com/@jane", "https://unsplash.com@evil.example/@jane", "https://unsplash.com:443/@jane", "//unsplash.com/@jane",
               "https://unsplash.com/jane", "https://unsplash.com/@", "https://unsplash.com/@jane/", "https://unsplash.com/@jane/photos", "https://unsplash.com/@jane/../x",
               "https://unsplash.com/@" + "a" * 65, "https://unsplash.com/@ja ne", "https://unsplash.com/@ja\nne", 'https://unsplash.com/@ja"ne', "https://unsplash.com/@ja'ne",
               "https://unsplash.com/@ja<ne", "https://unsplash.com/@ja`ne", "https://unsplash.com/@ja" + ESC + "ne", "https://unsplash.com/@ja(ne)", "https://unsplash.com/@ja;ne",
               "https://unsplash.com/@jane?x=<", "https://unsplash.com/@jane?x=" + "a" * 600, "javascript:alert(1)", "data:text/html,x", "", "   ", None, 5, ["x"], {"a": 1},
               "https://[::1/@jane", "ftp://unsplash.com/@jane", "https://unsplash.com/@%6Aane")
        for raw in bad:
            self.assertEqual(uc.safe_profile_url(raw), "", repr(raw))


class AuthorOfTest(unittest.TestCase):
    def item(self, **fields):
        user = {"name": "Jane Doe", "username": "janedoe", "links": {"html": PROFILE}}
        user.update(fields)
        return {"id": "Abc123XyZ_k", "user": user}

    def test_name_and_profile_are_read(self):
        self.assertEqual(uc.author_of(self.item()), ("Jane Doe", PROFILE))

    def test_the_username_stands_in_for_a_missing_name(self):
        for name in (None, "", "   ", "\u200b", "{}", 5):
            self.assertEqual(uc.author_of(self.item(name=name)), ("janedoe", PROFILE), repr(name))
        self.assertIsNone(uc.author_of(self.item(name=None, username=None)))

    def test_values_are_cleaned_before_they_are_kept(self):
        self.assertEqual(uc.author_of(self.item(name="Ja\u200bne\n Doe"))[0], "Jane Doe")
        self.assertEqual(uc.author_of(self.item(links={"html": PROFILE + "?x=1#y"}))[1], PROFILE)
        self.assertEqual(len(uc.author_of(self.item(name="N" * 300))[0]), 80)

    def test_a_missing_or_wrong_profile_means_the_photo_has_no_usable_credit(self):
        for links in ({}, None, "x", [], {"html": None}, {"html": ""}, {"html": "https://evil.example/@jane"}, {"html": "http://unsplash.com/@jane"}, {"html": "https://unsplash.com/jane"}):
            self.assertIsNone(uc.author_of(self.item(links=links)), repr(links))

    def test_wrong_shapes_give_nothing(self):
        for item in (None, 5, "x", [], {}, {"user": None}, {"user": "x"}, {"user": []}, {"id": "a"}, {"user": {}}):
            self.assertIsNone(uc.author_of(item), repr(item))


class DownloadAndLookupTest(unittest.TestCase):
    def test_download_locations_only_on_the_api_host_and_path(self):
        good = "https://api.unsplash.com/photos/Abc123XyZ_k/download?ixid=M3wxfDB8"
        self.assertEqual(uc.safe_download_url(good), good)
        self.assertEqual(uc.safe_download_url("  " + good + "\n"), good)
        for bad in ("http://api.unsplash.com/photos/Abc123XyZ_k/download", "https://evil.example/photos/Abc123XyZ_k/download", "https://api.unsplash.com.evil.example/photos/Abc123XyZ_k/download",
                    "https://api.unsplash.com/photos/Abc123XyZ_k", "https://api.unsplash.com/photos/a/download", "https://api.unsplash.com/photos/Abc123XyZ_k/download/x",
                    "https://api.unsplash.com/search/photos", "https://user@api.unsplash.com/photos/Abc123XyZ_k/download", "https://api.unsplash.com:443/photos/Abc123XyZ_k/download",
                    'https://api.unsplash.com/photos/Abc123XyZ_k/download?x="', "", None, 5):
            self.assertEqual(uc.safe_download_url(bad), "", repr(bad))

    def test_photo_addresses(self):
        for url in (f"{BASE}{PARAMS}", f"{BASE}?ixid=M3w&auto=format", BASE):
            self.assertTrue(uc.photo_url_ok(url), url)
        for url in ("http://images.unsplash.com/photo-1", "https://evil.example/photo-1", "https://images.unsplash.com/uploads/1", "https://images.unsplash.com/photo-1/x",
                    "https://images.unsplash.com.evil.example/photo-1", "https://plus.unsplash.com/photo-1", "https://images.unsplash.com/photo-", "", None):
            self.assertFalse(uc.photo_url_ok(url), repr(url))

    def test_fixed_list_numbers_become_lookup_ids(self):
        self.assertEqual(uc.photo_lookup_id("1558494949-ef010cbdcc31"), "photo-1558494949-ef010cbdcc31")
        self.assertEqual(uc.photo_lookup_id("1550745165-9bc0b252726f"), "photo-1550745165-9bc0b252726f")
        for bad in ("", "photo-1558494949-ef010cbdcc31", "../x", "1558494949", "1558494949-", "-ef010cbdcc31", "1558494949-ef01 0cbdcc31", "1558494949-ef010cbdcc31/x", "1558494949-ef010cbdcc31?x=1",
                    "abc-ef010cbdcc31", "1" * 21 + "-ef010cbdcc31", None, 5):
            self.assertEqual(uc.photo_lookup_id(bad), "", repr(bad))

    def test_every_number_of_the_fixed_list_is_a_valid_lookup_id(self):
        import generator
        for number in generator.POOL_IDS:
            self.assertTrue(uc.photo_lookup_id(number).startswith("photo-"), number)


class CreditedTest(unittest.TestCase):
    def test_it_is_the_address_itself_with_a_credit_attached(self):
        picked = uc.Credited(f"{BASE}{PARAMS}")
        picked.credit = LINE
        self.assertEqual(picked, f"{BASE}{PARAMS}")
        self.assertIsInstance(picked, str)
        self.assertEqual(picked.credit, LINE)
        self.assertEqual(uc.Credited("x").credit, "")
        self.assertEqual(f"image: {picked}", f"image: {BASE}{PARAMS}")
        self.assertEqual(str(picked), f"{BASE}{PARAMS}")
        self.assertIs(type(str(picked)), str)


class StrictCreditLineTest(unittest.TestCase):
    """'우리 줄'은 이름 칸을 풀어 `credit_markdown` 으로 다시 만든 줄과 글자까지 같은 줄뿐이다. 틀만 닮은 줄(이스케이프되지 않은 마크다운·HTML·보이지 않는 문자·중괄호·긴 이름·두 번 접은 공백)은 흉내일 뿐이라
    우리 줄이 아니다 — 지울 때 건드리지 않고, 이슈 수정의 사후 검증이 '우리 줄 교체'로 통과시키지도 않는다."""
    TEMPLATE = "*Photo by [{name}](https://unsplash.com/@janedoe?" + UTM + ") on [Unsplash](https://unsplash.com/?" + UTM + ")*"

    def line(self, name):
        return self.TEMPLATE.replace("{name}", name)

    def test_the_same_name_is_ours_only_when_it_is_written_the_way_the_builder_writes_it(self):
        self.assertTrue(uc.is_credit_line(self.line("Jane Doe")))
        for char in "[]()<>*_`|#":
            raw = self.line("a" + char + "b")
            escaped = self.line("a" + ESC + char + "b")
            self.assertFalse(uc.is_credit_line(raw), repr(char))                      # 이스케이프하지 않은 특수문자가 든 줄은 우리 줄이 아니다
            self.assertTrue(uc.is_credit_line(escaped), repr(char))
        self.assertTrue(uc.is_credit_line(self.line("a" + ESC + ESC + "b")))              # 역슬래시 자신도 이스케이프된 모양이어야 한다
        self.assertFalse(uc.is_credit_line(self.line("a" + ESC + "b")))

    def test_markup_and_hidden_text_in_the_name_make_it_a_lookalike(self):
        for name in ('<a href="https://evil.example">click</a>', "<script>alert(1)</script>", "**bold**", "`code`", "# heading", "| a | b |", "{{ site.title }}", "{% raw %}", "a{b}c",
                     "a" + chr(0x200B) + "b", "a" + chr(0x202E) + "b", "a" + chr(0x3164) + "b", "a" + chr(7) + "b", "a" + chr(0xA0) + "b", "a  b", " Jane", "Jane ", ESC + "q", ESC + "{",
                     "https://evil.example/phish", "<img src=x onerror=y>", "N" * 81, "N" * 200):
            line = self.line(name)
            expected = uc.credit_markdown(name, PROFILE)                                # 같은 이름을 우리 빌더로 쓰면 우리 줄이 된다(이스케이프·정리를 거친 모양)
            if expected:
                self.assertTrue(uc.is_credit_line(expected), repr(name))
            if line != expected:
                self.assertFalse(uc.is_credit_line(line), repr(name))

    def test_a_name_at_the_length_limit_is_ours_and_one_more_character_is_not(self):
        self.assertTrue(uc.is_credit_line(self.line("N" * 80)))
        self.assertFalse(uc.is_credit_line(self.line("N" * 81)))
        self.assertTrue(uc.is_credit_line(self.line("N" * 79 + "…")))

    def test_lookalikes_stay_in_the_text_when_ours_are_stripped_or_replaced(self):
        hostile = self.line('<a href="https://evil.example">x</a>')
        text = f"앞\n{hostile}\n뒤\n"
        self.assertEqual(uc.strip_credit_lines(text), text)
        self.assertEqual(uc.credit_lines(text), [])
        placed = uc.place_credit(f"![T](https://x/a)\n{hostile}\n", "https://x/a", LINE)
        self.assertIn(hostile, placed)
        self.assertEqual(placed.count(LINE), 1)

    def test_whatever_the_builder_writes_is_recognised_and_survives_a_strip_and_place_round_trip(self):
        import random
        pool = list("abcXYZ019 .-_'\"&!?:;,/@~^$%=+{}[]()<>*_`|#") + [ESC, "가", "나", "é", "日", "\n", "\t", chr(0x200B), chr(0x202E), chr(0x3000), chr(0x2028)]
        rng = random.Random(20261104)
        for _ in range(400):
            name = "".join(rng.choice(pool) for _ in range(rng.randint(0, 120)))
            line = uc.credit_markdown(name, PROFILE)
            if not line:
                continue
            self.assertTrue(uc.is_credit_line(line), repr(name))
            self.assertEqual(unescape(name_part(line)), uc.clean_name(name))
            self.assertEqual(uc.strip_credit_lines(f"![T](https://x/a)\n{line}\n"), "![T](https://x/a)\n")
            self.assertEqual(uc.place_credit(f"![T](https://x/a)\n", "https://x/a", line), f"![T](https://x/a)\n{line}\n")


class IsCreditLineTest(unittest.TestCase):
    def test_our_own_line_is_recognised_even_with_outer_whitespace(self):
        for line in (LINE, "  " + LINE, LINE + "  ", LINE + "\r", "\t" + LINE + "\r\n", uc.credit_markdown("O'Brien [x] *y*", PROFILE)):
            self.assertTrue(uc.is_credit_line(line), repr(line))

    def test_near_misses_are_not_ours(self):
        tail = f" on [Unsplash](https://unsplash.com/?{UTM})*"
        bad = (
            "", "   ", None, 5, [], LINE + " x", "x " + LINE, LINE + LINE, LINE.replace("*", "", 1), LINE[:-1], LINE.replace("Photo by", "Photo From"), LINE.replace("*Photo", "*photo"),
            LINE.replace("https://unsplash.com/@janedoe", "https://evil.example/@janedoe"), LINE.replace("https://unsplash.com/@janedoe", "http://unsplash.com/@janedoe"),
            LINE.replace("https://unsplash.com/@janedoe", "https://unsplash.com.evil.example/@janedoe"), LINE.replace("https://unsplash.com/@janedoe", "https://unsplash.com/janedoe"),
            LINE.replace("@janedoe?", "@janedoe/x?"), LINE.replace(UTM, "utm_source=other&utm_medium=referral"), LINE.replace(UTM, "utm_source=chanceblog"), LINE.replace(f"/?{UTM})*", f"/)*"),
            LINE.replace("on [Unsplash]", "on [Pexels]"), LINE.replace(" on [Unsplash]", " and [Unsplash]"), LINE.replace("[Jane Doe]", "[]"), LINE.replace("[Jane Doe]", "[Jane ] Doe]"),
            LINE.replace("[Jane Doe]", "[Jane\nDoe]"), LINE.replace("[Jane Doe]", "Jane Doe"), "*Photo by [x](https://unsplash.com/@y?" + UTM + ")" + tail + "\n*Photo by [x]",
            "- " + LINE, "> " + LINE, "# " + LINE, "<p>" + LINE + "</p>", "*Photo by [" + "a" * 700 + "](https://unsplash.com/@y?" + UTM + ")" + tail,
        )
        for line in bad:
            self.assertFalse(uc.is_credit_line(line), repr(line)[:90])

    def test_a_long_escape_chain_is_checked_in_linear_time(self):
        names = (ESC * 250, (ESC + "a") * 250, "a" * 480, ESC * 249 + "]", "[" * 400, (ESC + "]") * 240)
        started = time.perf_counter()
        for name in names:
            line = "*Photo by [" + name + "](https://unsplash.com/@y?" + UTM + ")" + uc.CREDIT_MARKER
            uc.is_credit_line(line)
            uc.is_credit_line(line + "x")
        self.assertLess(time.perf_counter() - started, 2.0)

    def test_credit_lines_lists_them_in_order(self):
        other = uc.credit_markdown("Other Name", "https://unsplash.com/@other")
        text = f"a\n{LINE}\nb\n  {other}  \n"
        self.assertEqual(uc.credit_lines(text), [LINE, other])
        self.assertEqual(uc.credit_lines("nothing"), [])
        self.assertEqual(uc.credit_lines(None), [])


class StripCreditLinesTest(unittest.TestCase):
    def test_nothing_changes_when_there_is_no_credit_line(self):
        for text in ("", "a", "a\n", "a\n\nb\n", "![Thumbnail](x)\n\ntext\n", "---\ntitle: x\n---\n\n본문\n\n\n\n끝", "x\r\ny\r\n"):
            self.assertEqual(uc.strip_credit_lines(text), text)

    def test_a_line_right_after_the_image_line_goes_away(self):
        self.assertEqual(uc.strip_credit_lines(f"![Thumbnail](x)\n{LINE}\n\ncite\n"), "![Thumbnail](x)\n\ncite\n")

    def test_a_line_between_two_blank_lines_takes_one_blank_with_it(self):
        self.assertEqual(uc.strip_credit_lines(f"a\n\n{LINE}\n\nb\n"), "a\n\nb\n")
        self.assertEqual(uc.strip_credit_lines(f"a\n\n{LINE}\n{LINE}\n\nb\n"), "a\n\nb\n")

    def test_a_line_at_the_start_the_end_or_beside_text_keeps_the_blanks(self):
        self.assertEqual(uc.strip_credit_lines(f"{LINE}\n\nb\n"), "\nb\n")
        self.assertEqual(uc.strip_credit_lines(f"a\n\n{LINE}"), "a\n")
        self.assertEqual(uc.strip_credit_lines(f"a\n{LINE}\nb\n"), "a\nb\n")

    def test_lines_that_only_look_similar_stay(self):
        near = LINE.replace("unsplash.com/@janedoe", "evil.example/@janedoe")
        text = f"a\n{near}\nb\n"
        self.assertEqual(uc.strip_credit_lines(text), text)

    def test_it_never_touches_the_front_matter_or_other_text(self):
        text = f'---\nlayout: post\ntitle: "x"\nimage: "{BASE}"\n---\n\nbody\n![Thumbnail]({BASE})\n{LINE}\nnext\n'
        self.assertEqual(uc.strip_credit_lines(text), text.replace(LINE + "\n", ""))

    def test_a_trailing_carriage_return_is_tolerated(self):
        self.assertEqual(uc.strip_credit_lines(f"a\r\n{LINE}\r\nb\r\n"), "a\r\nb\r\n")

    def test_non_text_input_is_read_as_empty(self):
        self.assertEqual(uc.strip_credit_lines(None), "")


class PlaceCreditTest(unittest.TestCase):
    URL = f"{BASE}{PARAMS}"
    NEW = f"{BASE}?ixid=M3wx&auto=format&fit=crop&w=1000&q=80"
    TEXT = f'---\nlayout: post\nimage: "{URL}"\n---\n\n본문입니다.\n\n![Thumbnail]({URL})\n\n"인용" 한 줄.\n'

    def test_the_line_goes_in_right_after_the_image_line_with_no_blank_between(self):
        out = uc.place_credit(self.TEXT, self.URL, LINE)
        lines = out.split("\n")
        at = lines.index(f"![Thumbnail]({self.URL})")
        self.assertEqual(lines[at + 1], LINE)
        self.assertEqual(out.count(LINE), 1)
        self.assertEqual(out.replace(LINE + "\n", ""), self.TEXT)               # 그 밖의 글자는 한 글자도 바뀌지 않는다

    def test_doing_it_again_changes_nothing(self):
        once = uc.place_credit(self.TEXT, self.URL, LINE)
        self.assertEqual(uc.place_credit(once, self.URL, LINE), once)
        self.assertEqual(uc.place_credit(uc.place_credit(once, self.URL, LINE), self.URL, LINE), once)

    def test_the_old_line_is_replaced_and_the_photo_of_the_line_follows_the_new_image(self):
        old = uc.place_credit(self.TEXT, self.URL, LINE)
        other = uc.credit_markdown("Other Name", "https://unsplash.com/@other")
        swapped = uc.place_credit(old.replace(self.URL, self.NEW), self.NEW, other)
        self.assertNotIn(LINE, swapped)
        self.assertEqual(swapped.count(other), 1)
        lines = swapped.split("\n")
        self.assertEqual(lines[lines.index(f"![Thumbnail]({self.NEW})") + 1], other)
        self.assertEqual(uc.place_credit(swapped, self.NEW, other), swapped)

    def test_without_a_new_line_the_old_one_is_removed_and_nothing_is_added(self):
        old = uc.place_credit(self.TEXT, self.URL, LINE)
        self.assertEqual(uc.place_credit(old, self.URL, ""), self.TEXT)
        self.assertEqual(uc.place_credit(old, self.URL, None), self.TEXT)

    def test_a_line_that_is_not_ours_is_never_inserted(self):
        for bad in ("*Photo by [x](https://evil.example/@y) on [Unsplash](https://evil.example/)*", "text", "<script>x</script>", LINE + " extra", LINE + "\n" + LINE):
            self.assertEqual(uc.place_credit(self.TEXT, self.URL, bad), self.TEXT, repr(bad))

    def test_forged_lines_in_the_model_text_are_all_removed_even_when_no_line_is_added(self):
        forged = uc.credit_markdown("Evil Name", "https://unsplash.com/@evil")
        text = self.TEXT.replace("본문입니다.", f"본문입니다.\n\n{forged}\n\n끝.\n{forged}").replace('"인용"', f"{forged}\n\"인용\"")
        for credit in ("", LINE):
            out = uc.place_credit(text, self.URL, credit)
            self.assertNotIn("Evil Name", out)
            self.assertEqual(out.count("*Photo by ["), 1 if credit else 0)

    def test_no_image_line_means_no_credit_line(self):
        text = "---\nimage: \"x\"\n---\n\n본문\n"
        self.assertEqual(uc.place_credit(text, self.URL, LINE), text)
        other_image = self.TEXT.replace(f"![Thumbnail]({self.URL})", f"![Thumbnail]({self.NEW})")
        self.assertEqual(uc.place_credit(other_image, self.URL, LINE), other_image)          # 다른 사진의 이미지 줄에는 붙이지 않는다

    def test_the_image_line_may_carry_any_alt_text_and_outer_spaces(self):
        for image_line in (f"![Thumbnail]({self.URL})", f"![]({self.URL})", f"![설명 글]({self.URL})", f"  ![Thumbnail]({self.URL})  "):
            out = uc.place_credit(f"앞\n\n{image_line}\n\n뒤\n", self.URL, LINE)
            lines = out.split("\n")
            self.assertEqual(lines[lines.index(image_line) + 1], LINE, image_line)

    def test_an_image_mentioned_inside_other_text_is_not_an_image_line(self):
        for text in (f"설명 ![x]({self.URL}) 끝\n", f"- ![x]({self.URL})\n", f"> ![x]({self.URL})\n", f"![x]({self.URL}) 뒤에 글\n", f"[![x]({self.URL})](https://example.com/)\n"):
            self.assertEqual(uc.place_credit(text, self.URL, LINE), text, text)

    def test_the_image_address_is_matched_literally(self):
        weird = "https://images.unsplash.com/photo-1+2.3?ixid=a=&q=(1)"
        text = f"![T]({weird})\n"
        self.assertEqual(uc.place_credit(text, weird, LINE), f"![T]({weird})\n{LINE}\n")
        self.assertEqual(uc.place_credit("![T](https://images.unsplash.com/photo-1x2.3)\n", weird, LINE), "![T](https://images.unsplash.com/photo-1x2.3)\n")

    def test_only_the_first_matching_image_line_gets_the_credit(self):
        text = f"![a]({self.URL})\n\n![b]({self.URL})\n"
        out = uc.place_credit(text, self.URL, LINE)
        self.assertEqual(out.count(LINE), 1)
        self.assertEqual(out.split("\n")[1], LINE)

    def test_carriage_returns_are_kept_with_the_line_ending(self):
        text = f"앞\r\n![T]({self.URL})\r\n뒤\r\n"
        out = uc.place_credit(text, self.URL, LINE)
        self.assertEqual(out, f"앞\r\n![T]({self.URL})\r\n{LINE}\r\n뒤\r\n")
        self.assertEqual(uc.place_credit(out, self.URL, LINE), out)

    def test_text_that_is_not_a_string_is_read_as_empty(self):
        self.assertEqual(uc.place_credit(None, self.URL, LINE), "")


class CreditProblemsTest(unittest.TestCase):
    URL = PlaceCreditTest.URL

    def test_a_post_with_no_line_or_one_line_in_the_right_place_is_fine(self):
        self.assertEqual(uc.credit_problems(PlaceCreditTest.TEXT, self.URL), [])
        self.assertEqual(uc.credit_problems(uc.place_credit(PlaceCreditTest.TEXT, self.URL, LINE), self.URL), [])

    def test_two_lines_are_refused(self):
        text = uc.place_credit(PlaceCreditTest.TEXT, self.URL, LINE) + f"\n{LINE}\n"
        problems = uc.credit_problems(text, self.URL)
        self.assertTrue(any("둘 이상" in problem for problem in problems), problems)

    def test_a_line_that_does_not_follow_the_image_line_is_refused(self):
        for text in (f"![T]({self.URL})\n\n{LINE}\n", f"{LINE}\n![T]({self.URL})\n", f"본문\n{LINE}\n", f"![T](https://images.unsplash.com/photo-9)\n{LINE}\n", f"{LINE}\n"):
            problems = uc.credit_problems(text, self.URL)
            self.assertTrue(any("바로 다음" in problem for problem in problems), (text, problems))


if __name__ == "__main__":
    unittest.main()
