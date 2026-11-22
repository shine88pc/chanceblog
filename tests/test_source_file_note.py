"""출처 목록의 '원자료 파일' 안내 한 줄 시험(AP4, F106 — 확인 015 항목 2): 출처 링크가 읽을 화면이 아니라 제공처의 원자료 파일(`.json`)일 때만, 링크 바로 아래에 안내가 정확히 한 줄 더해진다.

네 갈래를 지킨다. (a) NOAA 제품 여섯 주소로 조립한 글의 `## 출처` 절은 '링크 줄, 안내 줄, 이용 조건 줄' 순서이고 안내는 한 번뿐이다. (b) 확장자가 없는 주소(시험용 주소·`.html` 따위)의 글은 한 글자도 달라지지 않는다.
(c) 안내 줄은 숫자·영문·금지어·차단어·표시 문자가 없고 한 줄 60자 안의 글머리 항목이라 품질 Gate 가 출처 목록 안에 두며 본문(story)을 바꾸지 않는다. (d) 주소를 판정하는 함수의 경계(물음표·꼬리표·대소문자·빈 값·글이 아닌 값).
조립기·글 틀·어댑터 모듈은 직접 import 하지 않고 `space_helpers` 가 이미 가져온 이름을 빌려 쓴다(`test_fact_structure.NoConnectionTest` 가 Fact 시험 목록 밖의 직접 import 를 막는다). 네트워크·시계 없이 돈다."""
import unittest

import _bootstrap  # noqa: F401
import space_helpers as H
import test_space_gate as SG
import test_space_recipes as TR

from pipeline import quality_gate as qg

A, F, R, RN, N = H.A, H.F, H.R, H.RN, H.N

NOTE = "- 위 링크는 읽을 수 있는 화면이 아니라 제공처가 내려 주는 원자료 파일입니다."          # 승인된 한 줄(확인 015 항목 2 '원자료 파일입니다') — 문구를 바꾸면 이 시험도 일부러 고친다
PLAIN_URL = TR.TEST_SOURCE_URL                                                                  # 확장자가 없는 시험용 주소(골든 글이 쓰는 주소)


def noaa_post(name, *, product_id=None, provider_=None):
    """골든 한 편의 입력을 NOAA 제품 주소(운영과 같은 모양의 주소)로 조립한다. product_id 를 주면 그 제품의 이름·주소를 쓴다(자료는 같은 골든 입력이고 출처 이름·주소만 바뀐다)."""
    recipe_id, own_product, rows, params = TR.golden_cases()[name]
    record, facts = H.parse_value(own_product, rows)
    source = H.source_info(product_id or own_product, provider_)
    post = A.assemble(RN.NOREGION_RECIPES[recipe_id], list(facts), H.TODAY, records=[record], source=source, params=params)
    assert isinstance(post, A.AssembledPost), post
    return post


def post_at(name, url, *, provider_=None):
    """골든 한 편을 이름은 시험용 그대로 두고 주소만 url 로 바꿔 조립한다."""
    post = TR.build(name, source=A.SourceInfo(provider_ or H.NoaaProvider(), TR.TEST_SOURCE_NAME, url))
    assert isinstance(post, A.AssembledPost), post
    return post


def source_lines(post):
    """`## 출처` 절의 목록 줄(구분선 앞까지, 빈 줄 제외)."""
    section = post.body_markdown.split("\n## " + R.H_SOURCE + "\n", 1)[1]
    return [line for line in section.split("\n---\n", 1)[0].split("\n") if line.strip()]


def link_line(post):
    return f"- [{post.source_name}]({post.source_url}) — 열람 "


class NoteIsAddedForDataFilesTest(unittest.TestCase):
    """(a) 주소가 원자료 파일이면 링크 줄 바로 아래에 안내가 한 번 더해진다."""

    def check_lines(self, post, label):
        lines = source_lines(post)
        self.assertEqual(len(lines), 3, (label, lines))
        self.assertTrue(lines[0].startswith(link_line(post)), (label, lines[0]))
        self.assertEqual(lines[1], NOTE, label)
        self.assertTrue(lines[2].startswith(A.ATTRIBUTION_PREFIX), (label, lines[2]))
        self.assertEqual(post.body_markdown.count(NOTE), 1, label)

    def test_all_six_noaa_product_addresses_get_the_note_once_between_the_link_and_the_terms(self):
        self.assertEqual(len(N.PRODUCT_IDS), 6)
        for product_id in N.PRODUCT_IDS:
            post = noaa_post("r04_kp", product_id=product_id)
            with self.subTest(product=product_id):
                self.assertTrue(N.product_url(product_id).endswith(".json"))
                self.assertEqual(post.source_url, N.product_url(product_id))
                self.check_lines(post, product_id)

    def test_the_six_golden_posts_with_their_own_products_get_the_note(self):
        for name in TR.golden_cases():
            with self.subTest(post=name):
                self.check_lines(noaa_post(name), name)

    def test_without_a_terms_line_the_note_is_still_right_under_the_link(self):
        no_terms = H.provider(attribution_template="", policy=H.Policy(attribution=H.Cell("ALLOWED")))
        post = noaa_post("r04_ssn_daily", provider_=no_terms)
        lines = source_lines(post)
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(lines[0].startswith(link_line(post)))
        self.assertEqual(lines[1], NOTE)
        self.assertNotIn(A.ATTRIBUTION_PREFIX, post.body_markdown)

    def test_an_address_with_a_query_after_the_file_name_gets_the_note_too(self):
        post = post_at("r04_kp", PLAIN_URL + ".json?v=2")
        self.assertEqual(source_lines(post)[1], NOTE)
        self.assertEqual(post.body_markdown.count(NOTE), 1)

    def test_the_note_is_the_only_difference_from_a_post_with_a_plain_address(self):
        for name in TR.golden_cases():
            noaa, plain = noaa_post(name), TR.build(name)
            without = noaa.body_markdown.replace(NOTE + "\n", "", 1)
            with self.subTest(post=name):
                self.assertNotEqual(without, noaa.body_markdown)
                self.assertEqual(without.replace(noaa.source_url, plain.source_url).replace(noaa.source_name, plain.source_name), plain.body_markdown)
                self.assertEqual((noaa.title, noaa.description, noaa.category, noaa.tags, noaa.formulas), (plain.title, plain.description, plain.category, plain.tags, plain.formulas))
                self.assertEqual(A.readable_chars(A.story_of(noaa.body_markdown)), A.readable_chars(A.story_of(plain.body_markdown)))


class NoteIsAbsentForOtherAddressesTest(unittest.TestCase):
    """(b) 확장자가 없는(또는 원자료가 아닌) 주소의 글은 그대로다 — 골든 파일 아홉 개가 바이트 그대로 남는 근거."""

    def test_the_plain_test_address_gives_two_lines_and_no_note(self):
        for name in TR.golden_cases():
            post = TR.build(name)
            with self.subTest(post=name):
                self.assertEqual(post.source_url, PLAIN_URL)
                lines = source_lines(post)
                self.assertEqual(len(lines), 2, lines)
                self.assertTrue(lines[0].startswith(link_line(post)))
                self.assertTrue(lines[1].startswith(A.ATTRIBUTION_PREFIX))
                self.assertNotIn("원자료", post.body_markdown)

    def test_addresses_that_do_not_end_in_a_data_file_name_get_no_note(self):
        for suffix in (".html", "/", ".jsonl", ".json5", ".json/", "?format=json", ".json.html"):
            post = post_at("r05_flares", PLAIN_URL + suffix)
            with self.subTest(suffix=suffix):
                self.assertEqual(len(source_lines(post)), 2, source_lines(post))
                self.assertNotIn(NOTE, post.body_markdown)
                self.assertNotIn("원자료", post.body_markdown)


class NoteTextTest(unittest.TestCase):
    """(c) 안내 줄이 글 모양 점검 규칙과 품질 Gate 를 모두 지난다."""

    def test_the_note_is_the_approved_sentence_as_one_short_bullet(self):
        self.assertEqual(R.SOURCE_FILE_NOTE, NOTE)
        self.assertEqual(R.SOURCE_FILE_SUFFIXES, (".json",))
        self.assertTrue(NOTE.startswith("- ") and NOTE.endswith("원자료 파일입니다."))
        self.assertNotIn("\n", NOTE)

    def test_the_note_has_no_number_latin_word_forbidden_or_blocked_word_or_markup(self):
        in_post = source_lines(noaa_post("r04_kp"))[1]                                           # 코드가 실제로 쓰는 상수와 조립된 글 속의 줄, 둘 다 같은 규칙을 받는다
        for note in (R.SOURCE_FILE_NOTE, in_post):
            with self.subTest(note=note):
                self.assertEqual(A.number_tokens(note), [])
                self.assertEqual(F.untraced_numbers(note), [])
                self.assertEqual(A.latin_words(note), [])
                self.assertEqual(A.forbidden_found(note), [])
                self.assertEqual(A.blocked_found(note), [])
                self.assertEqual([mark for mark in R.BLOCKED_TEXT_CHARS if mark in note], [])
                self.assertEqual([mark for mark in F.FORBIDDEN_TEMPLATE_CHARS if mark in note], [])
                self.assertFalse(A.unsafe_free_text(note))
                self.assertIsNone(A._note_problem(note[2:]))                                      # 독자용 안내 문장에 거는 검사를 그대로 받는다
                self.assertLessEqual(len(note[2:]), 60)                                           # 품질 Gate 가 출처 목록 안에 두는 짧은 글머리 항목의 한도

    def test_the_gate_keeps_the_note_inside_the_source_list_and_the_story_is_unchanged(self):
        short_terms, long_terms = H.provider(), H.provider(attribution_template=H.B_TEMPLATE)        # 이용 조건 줄이 60자 안이면 목록 안에, 길면 목록 뒤 꼬리에 놓인다 — 어느 쪽이든 안내는 목록 안에 있어야 한다
        for label, provider_ in (("짧은 이용 조건", short_terms), ("긴 이용 조건", long_terms)):
            for name in TR.golden_cases():
                body = noaa_post(name, provider_=provider_).body_markdown
                without = body.replace(NOTE + "\n", "", 1)
                split, split_without = qg.split_story(body), qg.split_story(without)
                with self.subTest(terms=label, post=name):
                    block_lines = split.block.split("\n")
                    self.assertEqual(block_lines.count(NOTE), 1)
                    self.assertNotIn(NOTE, split.story)
                    self.assertNotIn(NOTE, split.tail)
                    self.assertEqual(split.story, split_without.story)
                    self.assertEqual(split.tail, split_without.tail)
                    block_lines.remove(NOTE)
                    self.assertEqual(block_lines, split_without.block.split("\n"))

    def test_the_post_with_the_note_passes_the_generator_and_the_whole_gate(self):
        for name, (recipe_id, product_id, rows, params) in TR.golden_cases().items():
            post = SG.noaa_post(recipe_id, product_id, rows, params.get("key"))                      # 실제 NOAA 출처 문구(보고서 B안)로 조립 — 출처 도메인 검사까지 지나게
            self.assertIsInstance(post, A.AssembledPost, name)
            content, source = TR.generator_file(post)
            with self.subTest(post=name):
                self.assertEqual(post.body_markdown.count(NOTE), 1)
                TR.g._validate_editorial_body(content, "kr", post.source_url)                       # 생성기의 본문 규칙(예외가 없으면 통과)
                self.assertEqual(TR.g.front_matter_problems(content, source), [])
                self.assertEqual(A.post_problems(post, allowed_latin={"NOAA", "SWPC", "GOES", "Kp", "UTC", "nW"}), [])
                self.assertEqual(SG.report_of(post).codes(), [])


class IsDataFileUrlTest(unittest.TestCase):
    """(d) 주소 판정의 경계."""

    BASE = PLAIN_URL

    def test_a_json_file_name_before_the_query_or_fragment_counts_whatever_the_case(self):
        for url in (self.BASE + ".json", self.BASE + ".JSON", self.BASE + ".Json", self.BASE + ".json?", self.BASE + ".json?v=2", self.BASE + ".json#top", self.BASE + ".json?v=2#top",
                    "HTTPS://EXAMPLE.INVALID/DATA.JSON", N.product_url("scales"), N.product_url("ssn_monthly")):
            with self.subTest(url=url):
                self.assertTrue(R.is_data_file_url(url))

    def test_other_endings_and_a_json_name_in_the_query_or_fragment_do_not_count(self):
        for url in (self.BASE, self.BASE + ".html", self.BASE + ".jsonl", self.BASE + ".json5", self.BASE + ".json/", self.BASE + ".json.html", self.BASE + "/json",
                    self.BASE + "?file=a.json", self.BASE + "#a.json", self.BASE + "?v=2#a.json", ".json ", " "):
            with self.subTest(url=url):
                self.assertFalse(R.is_data_file_url(url))

    def test_an_empty_or_non_text_value_is_not_a_data_file(self):
        for value in ("", None, 0, 5, 1.5, True, b"data.json", [".json"], (".json",), {"url": ".json"}):
            with self.subTest(value=value):
                self.assertFalse(R.is_data_file_url(value))

    def test_the_six_noaa_product_addresses_all_count_as_data_files(self):
        for product_id in N.PRODUCT_IDS:
            with self.subTest(product=product_id):
                self.assertTrue(R.is_data_file_url(N.product_url(product_id)))


if __name__ == "__main__":
    unittest.main()
