"""Chance 엔진(generator.py)의 글 머리말(front matter) 방어 시험(결함 D-80, 사용자 이슈 #59). 네트워크 없이 돈다.

배경: 2026-10-27 18시 슬롯 글 한 쌍은 모델이 `------` 로 시작하는 이중 머리말을, 2026-10-28 9시 슬롯 한글 글은 바깥 따옴표 안에 안쪽 따옴표를 이스케이프하지
않은 제목(`title: ""…": …"`)을 내보냈고, 옛 `validate_post_data` 는 모델이 쓴 머리말 줄을 그대로 믿어 파일에 썼다. 그 결과 공개 사이트의 글 제목이 파일 이름
(`Kr 221527`·`2026-10-28-KR-111851.md`)으로, 분야가 General 로 나왔다. 아래 시험은 (1) 그 응답을 그대로 흉내 내 결함을 재현하고, (2) 머리말을 가르는 규칙마다,
(3) 완성된 글의 최종 검사(`front_matter_problems`)의 규칙마다 그것만 잡는 시험을 두고, (4) 좋은 입력의 출력이 옛 함수와 바이트 단위로 같음을 고정한다.
저장소의 실제 글 전체를 지키는 시험은 `test_posts_front_matter.py`.
"""
import copy
import json
import random
import re
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

import _bootstrap
import generator as g
from test_generator_slots import at, candidate, run_captured

ROOT = _bootstrap.ROOT
LINK = "https://www.nasa.gov/general/how-a-johnson-mentor-shapes-the-next-generation-of-nasa-talent/"
KR_BODY = ("이 글은 테스트용 본문입니다. " * 80) + f"\n\n근거는 [원문]({LINK})에 있습니다.\n"
EN_BODY = ("This is a test body for the generator. " * 80) + f"\n\nSee [source]({LINK}).\n"
KR_IMAGE, EN_IMAGE = "https://img.test/kr.jpg", "https://img.test/en.jpg"
SOURCE = {"title": "원문 제목", "source": "NASA", "link": LINK, "publisher_domain": "www.nasa.gov"}


def make_data(kr_content, en_content, kr_title="한글 제목", en_title="English Title", kr_category="과학·환경",
              en_category="Science & Environment", kr_tags=("태그1", "태그2"), en_tags=("tag1", "tag2")):
    """모델의 JSON 응답과 같은 모양의 dict."""
    return {"kr_category": kr_category, "kr_title": kr_title, "kr_tags": list(kr_tags), "kr_content": kr_content,
            "en_category": en_category, "en_title": en_title, "en_tags": list(en_tags), "en_content": en_content,
            "image_queries": ["a", "b", "c"]}


def validate(data, **kwargs):
    return g.validate_post_data(data, KR_IMAGE, EN_IMAGE, verified_source_url=LINK, **kwargs)


def split_post(text):
    """완성된 글 한 편을 (머리말 줄 목록, 본문 줄 목록)으로 가른다. 첫 줄이 정확히 `---` 이고 닫는 `---` 줄이 있어야 한다."""
    lines = text.split("\n")
    if lines[0] != "---":
        raise AssertionError(f"첫 줄이 정확히 '---' 가 아님: {lines[0]!r}")
    if "---" not in lines[1:]:
        raise AssertionError("닫는 '---' 줄이 없음")
    end = lines.index("---", 1)
    return lines[1:end], lines[end + 1:]


def first_body_line(body_lines):
    return next((line for line in body_lines if line.strip()), "")


# ---- 실제로 깨졌던 모델 응답(공개 글 세 편의 머리말에서 엔진이 더한 줄을 뺀 것) ----------------------------------------------
QUOTED_TITLE = '"너에게 무엇이 중요한지 결정하는 것": 우주 공학 현장에서 멘토링이 갖는 의미'
QUOTED_TITLE_RESPONSE = (
    '---\nlayout: post\ntitle: ""너에게 무엇이 중요한지 결정하는 것": 우주 공학 현장에서 멘토링이 갖는 의미"\ncategory: "과학·환경"\n'
    "tags:\n  - 멘토링\n  - 존슨우주센터\n  - 과학기술인재\n  - 공학교육\nlang: ko\n---\n\n" + KR_BODY)
DOUBLE_FENCE_KR_TITLE = "기후변화 대응의 축 이동: 선제적·시스템적 위험 관리가 공동체와 경제에 의미하는 것"
DOUBLE_FENCE_KR_RESPONSE = (
    f'------\nlayout: post\ntitle: "{DOUBLE_FENCE_KR_TITLE}"\ncategory: "사회·정책"\n'
    'tags: ["유럽연합", "기후변화", "위험관리", "공공정책"]\nlang: ko\n---\n\n---\n\n' + KR_BODY)
DOUBLE_FENCE_EN_TITLE = "Shifting the Climate Defense: What Proactive Risk Management Means for European Communities"
DOUBLE_FENCE_EN_RESPONSE = (
    f'------\nlayout: post\ntitle: "{DOUBLE_FENCE_EN_TITLE}"\ncategory: "Society & Policy"\n'
    'tags: ["European Union", "Climate Change", "Risk Management", "Public Policy"]\nlang: en\n---\n\n---\n\n' + EN_BODY)
GOOD_EN_TITLE = "\"You Decide What’s Important\": How Mentorship Shapes Aerospace Engineering Talent"
GOOD_EN_RESPONSE = (
    '---\nlayout: post\ntitle: "\\"You Decide What’s Important\\": How Mentorship Shapes Aerospace Engineering Talent"\n'
    'category: "Science & Environment"\ntags:\n  - Mentorship\n  - Johnson Space Center\nlang: en\n---\n\n' + EN_BODY)


class BrokenHeaderReproTest(unittest.TestCase):
    """공개된 세 편의 깨진 머리말을 만든 모델 응답을 그대로 넣으면, 파일에 쓰는 글의 머리말이 정상이어야 한다(수정 전에는 이 시험들이 실패했다)."""

    def finish(self, data):
        """validate_post_data → add_discovery_metadata 까지(파일에 쓰기 직전의 글)."""
        out = validate(data)
        return {key: g.add_discovery_metadata(out[f"{key}_content"], dict(SOURCE)) for key in ("kr", "en")}

    def check_post(self, text, title, category, lang, body_start):
        header, body = split_post(text)
        loaded = yaml.safe_load("\n".join(header))
        self.assertIsInstance(loaded, dict)
        self.assertEqual(loaded["title"], title)
        self.assertEqual(loaded["category"], category)
        self.assertEqual(loaded["lang"], lang)
        self.assertEqual(loaded["layout"], "post")
        self.assertIsInstance(loaded["tags"], list)
        self.assertTrue(loaded["image"].startswith("https://img.test/"))
        self.assertEqual((loaded["source_name"], loaded["source_url"], loaded["source_domain"]), ("NASA", LINK, "www.nasa.gov"))
        self.assertTrue(loaded["description"])
        self.assertNotEqual(first_body_line(body), "---", "본문이 울타리 줄로 시작하면 안 된다")
        self.assertTrue(first_body_line(body).startswith(body_start), first_body_line(body)[:40])
        return loaded

    def test_a_title_with_unescaped_inner_quotes_is_written_as_a_valid_one_line_string(self):
        data = make_data(QUOTED_TITLE_RESPONSE, GOOD_EN_RESPONSE, kr_title=QUOTED_TITLE, en_title=GOOD_EN_TITLE)
        final = self.finish(data)
        loaded = self.check_post(final["kr"], QUOTED_TITLE, "과학·환경", "ko", "이 글은 테스트용 본문입니다.")
        self.assertEqual(loaded["tags"], ["태그1", "태그2"])   # 믿지 않는 머리말은 구조화된 값으로 다시 쓴다
        # 짝인 영문 글은 좋은 머리말이라 모델이 쓴 줄(블록 목록 태그)이 그대로 남는다
        self.check_post(final["en"], GOOD_EN_TITLE, "Science & Environment", "en", "This is a test body")
        self.assertIn("tags:\n  - Mentorship\n  - Johnson Space Center\nlang: en", final["en"])

    def test_a_response_that_starts_with_six_dashes_and_repeats_the_fence_gets_one_clean_header(self):
        data = make_data(DOUBLE_FENCE_KR_RESPONSE, DOUBLE_FENCE_EN_RESPONSE, kr_title=DOUBLE_FENCE_KR_TITLE,
                         en_title=DOUBLE_FENCE_EN_TITLE, kr_category="사회·정책", en_category="Society & Policy")
        final = self.finish(data)
        self.check_post(final["kr"], DOUBLE_FENCE_KR_TITLE, "사회·정책", "ko", "이 글은 테스트용 본문입니다.")
        self.check_post(final["en"], DOUBLE_FENCE_EN_TITLE, "Society & Policy", "en", "This is a test body")
        for text in final.values():
            self.assertEqual(len(re.findall(r"(?m)^---$", text.split("\n\n![Thumbnail]")[0])), 2, "울타리 줄은 머리말의 두 줄뿐이어야 한다")

    def test_the_body_text_is_never_changed_by_the_repair(self):
        data = make_data(DOUBLE_FENCE_KR_RESPONSE, GOOD_EN_RESPONSE, kr_title=DOUBLE_FENCE_KR_TITLE, kr_category="사회·정책")
        final = self.finish(data)
        _, body = split_post(final["kr"])
        self.assertTrue("\n".join(body).lstrip().startswith(KR_BODY.rstrip()))


# ======================================================================================================================
# 최종 검사 front_matter_problems — 규칙마다 그것만 잡는 시험
# ======================================================================================================================
GOOD = ('---\nlayout: post\ntitle: "제목: \\"안\\""\ncategory: "분야"\ntags: ["a", "b"]\nlang: ko\nimage: "https://img.test/a.jpg"\n---\n\n본문 첫 줄입니다.\n')


def with_replaced(old, new, text=GOOD):
    assert old in text, old
    return text.replace(old, new, 1)


class FrontMatterProblemsTest(unittest.TestCase):
    def only(self, text, needle, source=None):
        """text 가 정확히 하나의 문제를 가지고 그 문장에 needle 이 들어 있는지."""
        problems = g.front_matter_problems(text, source)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn(needle, problems[0])

    def test_a_good_post_has_no_problems(self):
        self.assertEqual(g.front_matter_problems(GOOD), [])

    def test_the_shapes_the_model_and_older_posts_really_use_are_accepted(self):
        for label, text in (
                ("블록 목록 태그", with_replaced('tags: ["a", "b"]', "tags:\n  - a\n  - b")),
                ("들여쓰기 없는 블록 목록", with_replaced('tags: ["a", "b"]', "tags:\n- a\n- b")),
                ("따옴표 없는 목록", with_replaced('tags: ["a", "b"]', "tags: [a, b]")),
                ("작은따옴표 목록", with_replaced('tags: ["a", "b"]', "tags: ['a', 'b']")),
                ("빈 목록", with_replaced('tags: ["a", "b"]', "tags: []")),
                ("태그 없음", with_replaced('tags: ["a", "b"]\n', "")),
                ("따옴표 없는 분야", with_replaced('category: "분야"', "category: 분야")),
                ("작은따옴표 분야", with_replaced('category: "분야"', "category: '분야'")),
                ("따옴표 없는 이미지", with_replaced('image: "https://img.test/a.jpg"', "image: https://img.test/a.jpg")),
                ("날짜·공개 여부·permalink", with_replaced("lang: ko\n", "lang: ko\ndate: 2026-10-20 08:20:00 +0900\npublished: true\npermalink: /posts/a/\n")),
                ("따옴표 친 lang", with_replaced("lang: ko", 'lang: "ko"')),
                ("머리말 안의 빈 줄", with_replaced("lang: ko\n", "lang: ko\n\n"))):
            with self.subTest(label):
                self.assertEqual(g.front_matter_problems(text), [])

    def test_the_first_line_must_be_exactly_three_dashes(self):
        for label, text in (("대시 여섯 개", with_replaced("---\nlayout", "------\nlayout")), ("뒤 공백", with_replaced("---\nlayout", "--- \nlayout")),
                            ("앞의 빈 줄", "\n" + GOOD), ("CRLF", GOOD.replace("\n", "\r\n")), ("머리말 없음", "본문뿐입니다.\n")):
            with self.subTest(label):
                self.only(text, "첫 줄이 정확히")

    def test_a_byte_order_mark_is_refused(self):
        self.only("\ufeff" + GOOD, "BOM")

    def test_the_closing_fence_must_exist_and_be_exactly_three_dashes(self):
        self.only(GOOD.replace("\n---\n\n본문", "\n\n본문"), "닫는 `---` 줄이 없음")
        for label, closing in (("대시 네 개", "----"), ("뒤 공백", "---  ")):
            with self.subTest(label):
                self.only(GOOD.replace("\n---\n\n본문", f"\n{closing}\n\n본문"), "닫는 줄이 정확히")

    def test_carriage_returns_inside_the_header_are_refused(self):
        self.only(with_replaced("lang: ko\n", "lang: ko\r\n"), "CR")

    def test_characters_yaml_cannot_read_are_refused(self):
        self.only(with_replaced("분야", "분\x7f야"), "제어 문자")
        problems = g.front_matter_problems(with_replaced("분야", "분\x00야"))         # JSON 은 문자열 안의 날 제어 문자를 받지 않으므로 값 모양 문제도 함께 나온다
        self.assertIn(UNREADABLE, problems)
        self.assertEqual(g.front_matter_problems(with_replaced("분야", "분야이모지😀")), [])         # 이모지(astral 글자)는 읽힌다
        self.assertEqual(g.front_matter_problems(with_replaced("분야", "분\\t야")), [])           # JSON 이스케이프 \\t 는 읽힌다(엔진의 json.dumps 가 쓰는 모양)
        self.assertTrue(g.front_matter_problems(with_replaced("분야", "분\t야")))                 # 날 탭은 JSON 이 받지 않는다 — 보수적으로 믿지 않는다

    def test_each_header_line_must_be_one_key_and_one_value(self):
        for label, text in (("키 없는 줄", with_replaced("lang: ko\n", "lang: ko\n그냥 글\n")),
                            ("콜론 뒤 공백 없음", with_replaced("lang: ko", "lang:ko")),
                            ("앞에 키 없는 목록 항목", with_replaced("lang: ko\n", "lang: ko\n  - x\n")),
                            ("값이 있는 키 뒤의 이어진 줄", with_replaced('tags: ["a", "b"]', 'tags: ["a", "b"]\n  - c')),
                            ("들여쓴 키", with_replaced("lang: ko", "  lang: ko")),
                            ("주석 줄", with_replaced("lang: ko\n", "lang: ko\n# 주석\n"))):
            with self.subTest(label):
                self.assertTrue(any("한 줄 모양이 아닌 줄" in p for p in g.front_matter_problems(text)), label)

    def test_a_key_may_appear_only_once(self):
        self.only(with_replaced("lang: ko\n", "lang: ko\nlang: en\n"), "`lang` 키가 두 번")
        self.only(with_replaced("lang: ko\n", "lang: ko\ntitle: \"둘\"\n"), "`title` 키가 두 번")

    def test_the_title_must_be_a_one_line_json_string(self):
        for label, line in (("따옴표 없음", "title: 제목"), ("안쪽 따옴표 이스케이프 없음(공개된 결함)", 'title: ""제목": 안"'),
                            ("작은따옴표", "title: '제목'"), ("뒤 주석", 'title: "제목" # c'), ("닫는 따옴표 없음", 'title: "제목'),
                            ("목록", "title: [a, b]"), ("잘못된 이스케이프", 'title: "a\\qb"')):
            with self.subTest(label):
                self.only(with_replaced('title: "제목: \\"안\\""', line), "`title` 값이 한 줄 JSON 문자열")

    def test_the_title_must_not_be_blank(self):
        for line in ('title: ""', 'title: "   "'):
            with self.subTest(line):
                self.only(with_replaced('title: "제목: \\"안\\""', line), "`title` 값이 비어 있음")

    def test_every_required_key_is_checked_on_its_own(self):
        for key, line in (("layout", "layout: post\n"), ("title", 'title: "제목: \\"안\\""\n'), ("category", 'category: "분야"\n'),
                          ("lang", "lang: ko\n"), ("image", 'image: "https://img.test/a.jpg"\n')):
            with self.subTest(key):
                self.only(with_replaced(line, ""), f"필수 키 `{key}` 줄이 없음")
        self.assertEqual(g.front_matter_problems(with_replaced('tags: ["a", "b"]\n', "")), [])      # tags 는 필수가 아니다

    def test_a_key_with_no_value_needs_list_items(self):
        self.only(with_replaced('tags: ["a", "b"]', "tags:"), "`tags` 값이 비어 있음")
        self.only(with_replaced('image: "https://img.test/a.jpg"', "image:"), "`image` 값이 비어 있음")

    def test_quoted_values_must_close_on_the_same_line(self):
        self.only(with_replaced("lang: ko\n", 'lang: ko\ncustom: "닫히지 않음\n'), "`custom` 값이 큰따옴표 문자열")
        self.only(with_replaced("lang: ko\n", "lang: ko\ncustom: '닫히지 않음\n"), "`custom` 값이 작은따옴표 문자열")
        self.assertEqual(g.front_matter_problems(with_replaced("lang: ko\n", "lang: ko\ncustom: 'it''s'\n")), [])

    def test_plain_values_must_be_safe_yaml(self):
        for label, value in (("콜론+공백", "a: b"), ("공백+샵", "a #b"), ("끝 콜론", "a:"), ("탭", "a\tb"), ("목록 표지", "- a"), ("앵커", "&x"),
                             ("블록 스칼라", "|"), ("선행 따옴표 아님 지시자", "%x"), ("선행 @", "@x")):
            with self.subTest(label):
                self.only(with_replaced("lang: ko\n", f"lang: ko\ncustom: {value}\n"), "`custom` 값이")
        for value in ("a:b", "https://a.test/x?y=1&z=2", "2026-10-20 08:20:00 +0900", "/posts/x/", "한글 평문", "a#b"):
            with self.subTest(value):
                self.assertEqual(g.front_matter_problems(with_replaced("lang: ko\n", f"lang: ko\ncustom: {value}\n")), [])

    def test_one_line_lists_must_be_flat_and_closed(self):
        for label, value in (("닫는 괄호 없음", "[a, b"), ("안쪽 목록", "[[a], b]"), ("안쪽 매핑", "[{a: 1}]"), ("평문 항목의 콜론", "[a: b]"), ("JSON 아닌 매핑", "{a: 1}"),
                             ("닫은 뒤 군더더기", "[a, b] 군더더기"), ("닫은 뒤 또 하나", '["a"] ["b"]')):
            with self.subTest(label):
                self.assertTrue(g.front_matter_problems(with_replaced('tags: ["a", "b"]', f"tags: {value}")), label)
        for value in ('["a", 1, true, null]', "[a, b, ]", "['a', \"b\"]", "[ a , b ]", '["안: 쪽"]'):
            with self.subTest(value):
                self.assertEqual(g.front_matter_problems(with_replaced('tags: ["a", "b"]', f"tags: {value}")), [])

    def test_tags_must_be_a_list_not_a_string(self):
        for label, value in (("큰따옴표 글자", '"가, 나"'), ("작은따옴표 글자", "'가, 나'"), ("따옴표 없는 글자", "가, 나"), ("숫자", "3")):
            with self.subTest(label):
                self.only(with_replaced('tags: ["a", "b"]', f"tags: {value}"), "`tags` 값이 한 줄 목록([…])이 아님")

    def test_block_list_items_must_be_safe(self):
        for item in ("a: b", "- a", "a #b", "[a"):
            with self.subTest(item):
                self.only(with_replaced('tags: ["a", "b"]', f"tags:\n  - {item}"), "블록 목록 항목")
        self.assertEqual(g.front_matter_problems(with_replaced('tags: ["a", "b"]', 'tags:\n  - "a: b"\n  - \'c\'')), [])

    def test_lang_must_be_ko_or_en(self):
        self.only(with_replaced("lang: ko", "lang: fr"), "`lang` 값이 ko·en 이 아님")
        self.assertEqual(g.front_matter_problems(with_replaced("lang: ko", "lang: en")), [])

    def test_a_blank_category_or_image_is_refused(self):
        self.only(with_replaced('category: "분야"', 'category: ""'), "`category` 값이 비어 있음")
        self.only(with_replaced('image: "https://img.test/a.jpg"', 'image: ""'), "`image` 값이 비어 있음")

    def test_a_very_long_line_is_refused_without_a_slow_scan(self):
        self.only(with_replaced("lang: ko\n", "lang: ko\ncustom: " + "가" * 2500 + "\n"), "`custom` 값이 너무 김")

    def test_the_body_must_not_start_with_a_fence_line(self):
        for fence in ("---", "------", "---  "):
            with self.subTest(fence):
                self.only(with_replaced("\n---\n\n본문", f"\n---\n\n{fence}\n\n본문"), "본문이 `---` 울타리 줄로 시작함")
        self.assertEqual(g.front_matter_problems(with_replaced("본문 첫 줄입니다.\n", "본문 첫 줄입니다.\n\n---\n\n둘째\n")), [])      # 본문 가운데의 구분선은 괜찮다

    def test_a_byte_order_mark_before_a_fence_at_the_start_of_the_body_is_refused(self):
        self.only(with_replaced("본문 첫 줄입니다.", "\ufeff---\n본문"), "본문이 `---` 울타리 줄로 시작함")

    def test_the_body_must_not_start_with_a_header_line(self):
        for line in ("layout: post", "title: 가짜", "category: x", "tags: []", "lang: ko", "image: x", "description: x", "published: true", "date: 2026-10-20",
                     "permalink: /a/", "slug: a", "source_name: x", "source_url: https://a.test/", "source_domain: a.test"):
            with self.subTest(line):
                self.only(with_replaced("본문 첫 줄입니다.", line), "본문이 머리말 줄")
        for line in ("Summary: 요약", "title 이라는 말로 시작", "# title: x", "Title: 대문자 키는 글", "layout 이라는 말: 글"):
            with self.subTest(line):
                self.assertEqual(g.front_matter_problems(with_replaced("본문 첫 줄입니다.", line)), [])

    def test_a_header_line_among_the_first_three_body_lines_is_caught_but_not_a_later_one(self):
        """닫는 울타리가 없거나 머리말 사이에 글이 섞여 머리말이 본문에 남은 응답은 첫 줄이 머리말 키가 아닐 수도 있다(예: published 가 먼저)."""
        for position, expected in ((1, True), (2, True), (3, True), (4, False)):
            lines = ["첫 문단입니다.", "둘째 문단입니다.", "셋째 문단입니다.", "넷째 문단입니다."]
            lines.insert(position - 1, "source_url: https://a.test/x")
            text = with_replaced("본문 첫 줄입니다.", "\n\n".join(lines))
            with self.subTest(position=position):
                self.assertEqual(any("본문이 머리말 줄" in p for p in g.front_matter_problems(text)), expected)

    def test_the_problems_never_contain_the_values_of_the_header(self):
        text = with_replaced("lang: ko\n", 'lang: ko\ncustom: "비밀값 토큰\n').replace('"제목: \\"안\\""', "제목 비밀")
        joined = " ".join(g.front_matter_problems(text))
        self.assertNotIn("비밀", joined)
        self.assertNotIn("토큰", joined)


class FrontMatterProblemsSourceTest(unittest.TestCase):
    """source(add_discovery_metadata 에 넘기는 소스 항목)를 주면 엔진이 더하는 설명·출처 줄이 있는지도 본다."""

    LONG_BODY = "이 문단은 설명으로 뽑힐 만큼 충분히 긴 한국어 문장입니다. 예순 글자를 넘기려고 이렇게 길게 씁니다. 그래서 설명 줄이 만들어집니다.\n"

    def finished(self, body=None, source=None):
        text = with_replaced("본문 첫 줄입니다.\n", body or self.LONG_BODY)
        return g.add_discovery_metadata(text, dict(source or SOURCE))

    def test_a_post_finished_by_the_engine_passes(self):
        self.assertEqual(g.front_matter_problems(self.finished(), SOURCE), [])

    def test_each_source_line_is_checked_on_its_own(self):
        text = self.finished()
        for key in ("source_name", "source_url", "source_domain"):
            with self.subTest(key):
                lines = [line for line in text.split("\n") if not line.startswith(f"{key}:")]
                problems = g.front_matter_problems("\n".join(lines), SOURCE)
                self.assertEqual(len(problems), 1, problems)
                self.assertIn(f"`{key}` 줄이 없거나 원문 정보와 다름", problems[0])

    def test_a_source_line_that_differs_from_the_source_is_refused(self):
        text = self.finished().replace('source_name: "NASA"', 'source_name: "다른 곳"')
        self.assertEqual(g.front_matter_problems(text, SOURCE), ["`source_name` 줄이 없거나 원문 정보와 다름"])

    def test_the_description_is_required_when_the_body_has_one_to_take(self):
        text = self.finished()
        without = "\n".join(line for line in text.split("\n") if not line.startswith("description:"))
        self.assertEqual(g.front_matter_problems(without, SOURCE), ["설명(`description`) 줄이 없음"])
        self.assertEqual(g.front_matter_problems(without), [])        # source 를 주지 않으면 설명·출처는 보지 않는다(옛 글)

    def test_no_description_is_required_when_no_paragraph_is_long_enough(self):
        text = self.finished(body="짧은 글.\n")
        self.assertNotIn("description:", text)
        self.assertEqual(g.front_matter_problems(text, SOURCE), [])

    def test_single_quoted_source_values_are_decoded_before_the_comparison(self):
        name = "O" + chr(39) + "Brien Lab"
        source = dict(SOURCE, source=name)
        text = self.finished(source=source).replace(f"source_name: {json.dumps(name)}", "source_name: " + chr(39) + "O" + chr(39) * 2 + "Brien Lab" + chr(39))
        self.assertIn("source_name: " + chr(39) + "O" + chr(39) * 2 + "Brien Lab" + chr(39), text)
        self.assertEqual(g.front_matter_problems(text, source), [])

    def test_a_source_the_engine_would_not_record_needs_no_source_lines(self):
        for source in ({"title": "t", "source": "X", "link": LINK}, {"title": "t", "source": "", "link": LINK, "publisher_domain": "x"},
                       {"title": "t", "source": "X", "link": "ftp://x/y", "publisher_domain": "x"}, None, {}):
            with self.subTest(source=source):
                self.assertEqual(g.front_matter_problems(self.finished(source=SOURCE), source), [])
        self.assertIsNone(g._source_front_fields({"source": "X", "link": LINK}))
        self.assertEqual(g._source_front_fields(SOURCE), ("NASA", LINK, "www.nasa.gov"))

    def test_a_silent_no_op_of_front_matter_set_is_exposed(self):
        """`_front_matter_set` 이 머리말을 못 찾으면 글을 그대로 돌려줘 줄이 조용히 빠진다(옛 동작) — 최종 검사가 그것을 문제로 드러낸다."""
        with mock.patch.object(g, "_front_matter_set", lambda content, key, value: content):
            text = self.finished()
        problems = g.front_matter_problems(text, SOURCE)
        self.assertEqual(len(problems), 4, problems)
        self.assertEqual(sum("원문 정보와 다름" in p for p in problems), 3)
        self.assertEqual(sum("`description`" in p for p in problems), 1)


# ======================================================================================================================
# 모델 응답 가르기 _split_model_content
# ======================================================================================================================
HEADER = 'layout: post\ntitle: "t"\ncategory: "c"\ntags: []'
BODY = "본문 첫 줄\n\n둘째 문단\n"


class SplitModelContentTest(unittest.TestCase):
    def split(self, text):
        return g._split_model_content(text)

    def test_a_standard_response_is_clean(self):
        self.assertEqual(self.split(f"---\n{HEADER}\n---\n\n{BODY}"), ("clean", HEADER.split("\n"), BODY))

    def test_blank_lines_and_spaces_before_the_opening_fence_are_ignored(self):
        self.assertEqual(self.split(f"\n\n  ---\n{HEADER}\n---\n\n{BODY}")[0], "clean")

    def test_a_byte_order_mark_before_the_opening_fence_is_ignored(self):
        self.assertEqual(self.split(f"\ufeff---\n{HEADER}\n---\n\n{BODY}"), ("clean", HEADER.split("\n"), BODY))

    def test_trailing_spaces_after_either_fence_are_tolerated(self):
        for text in (f"--- \n{HEADER}\n---\n\n{BODY}", f"---\t\n{HEADER}\n---\n\n{BODY}", f"---\n{HEADER}\n---  \n\n{BODY}"):
            with self.subTest(text[:12]):
                self.assertEqual(self.split(text), ("clean", HEADER.split("\n"), BODY))

    def test_windows_line_endings_are_normalised_in_the_header_but_kept_in_the_body(self):
        kind, header, body = self.split(f"---\r\n{HEADER}\r\n---\r\n\r\n{BODY}".replace("\n", "\r\n").replace("\r\r", "\r"))
        self.assertEqual((kind, header), ("clean", HEADER.split("\n")))
        self.assertTrue(body.startswith("본문 첫 줄\r\n"), repr(body[:20]))

    def test_an_opening_fence_longer_than_three_dashes_is_messy(self):
        self.assertEqual(self.split(f"------\n{HEADER}\n---\n\n{BODY}"), ("messy", HEADER.split("\n"), BODY))

    def test_a_closing_fence_longer_than_three_dashes_is_messy_and_leaves_no_dash_in_the_body(self):
        self.assertEqual(self.split(f"---\n{HEADER}\n----\n\n{BODY}"), ("messy", HEADER.split("\n"), BODY))

    def test_a_doubled_opening_fence_is_messy_and_the_second_block_is_the_header(self):
        self.assertEqual(self.split(f"---\n---\n{HEADER}\n---\n\n{BODY}"), ("messy", HEADER.split("\n"), BODY))

    def test_an_empty_header_is_clean_but_has_no_lines(self):
        for text in (f"---\n---\n\n{BODY}", f"---\n\n---\n\n{BODY}"):
            self.assertEqual(self.split(text), ("clean", [], BODY))

    def test_a_stray_rule_line_after_the_closing_fence_is_dropped_and_the_header_stays_clean(self):
        for between in ("\n\n---\n\n", "\n---\n", "\n\n------\n\n", "\n\n---\n\n---\n\n"):
            with self.subTest(between=between):
                self.assertEqual(self.split(f"---\n{HEADER}\n---{between}{BODY}"), ("clean", HEADER.split("\n"), BODY))

    def test_a_second_header_block_after_the_first_is_dropped_and_the_response_is_messy(self):
        text = f"---\n{HEADER}\n---\n\n---\n{HEADER}\n---\n\n{BODY}"
        self.assertEqual(self.split(text), ("messy", HEADER.split("\n"), BODY))

    def test_a_rule_followed_by_prose_is_not_mistaken_for_a_second_header(self):
        body = "첫 문단입니다.\n\n---\n\n끝 문단\n"
        kind, _, got = self.split(f"---\n{HEADER}\n---\n\n---\n\n{body}")
        self.assertEqual((kind, got), ("clean", body))        # 본문 가운데의 구분선은 그대로

    def test_a_response_with_no_opening_fence_is_returned_untouched(self):
        for text in (BODY, "\n\n" + BODY, "  들여쓴 글\n", "---제목 같은 첫 줄\n본문\n", "- 목록으로 시작\n"):
            with self.subTest(text[:10]):
                self.assertEqual(self.split(text), ("none", [], text))

    def test_a_leading_rule_without_a_header_is_dropped_and_the_prose_is_kept(self):
        self.assertEqual(self.split(f"---\n\n{BODY}"), ("none", [], BODY))
        prose = "본문 문단입니다.\n\n---\n\n끝 문단\n"
        self.assertEqual(self.split(f"---\n\n{prose}"), ("none", [], prose))        # 다음 구분선까지가 글이라 머리말로 읽지 않는다

    def test_a_block_of_key_like_lines_without_any_header_key_is_prose_not_a_header(self):
        prose = "Note: 이것은 첫 문단의 일부입니다\nSummary: 두 번째 줄\n"
        kind, header, body = self.split(f"---\n{prose}---\n\n{BODY}")
        self.assertEqual((kind, header), ("none", []))
        self.assertTrue(body.startswith("Note: 이것은"), body[:20])

    def test_an_unclosed_header_is_not_a_header_so_its_lines_stay_visible_for_the_final_check(self):
        kind, header, body = self.split(f"---\n{HEADER}\n\n{BODY}")
        self.assertEqual((kind, header), ("none", []))
        self.assertTrue(body.startswith("layout: post\n"), body[:20])
        self.assertTrue(g.front_matter_problems("---\nlayout: post\ntitle: \"t\"\ncategory: \"c\"\nlang: ko\nimage: \"x\"\n---\n\n" + body))

    def test_a_non_header_line_inside_the_header_makes_the_block_prose_not_a_header(self):
        kind, _, body = self.split(f"---\n{HEADER}\n머리말이 아닌 줄\n---\n\n{BODY}")
        self.assertEqual(kind, "none")
        self.assertIn("머리말이 아닌 줄", body)         # 지우지 않는다 — 최종 검사가 후보를 거절한다

    def test_the_first_body_line_keeps_its_indentation(self):
        self.assertEqual(self.split(f"---\n{HEADER}\n---\n\n    들여쓴 첫 줄\n다음 줄\n")[2], "    들여쓴 첫 줄\n다음 줄\n")

    def test_header_lines_are_returned_without_trailing_carriage_returns(self):
        _, header, _ = self.split("---\r\ntitle: \"t\"\r\nlayout: post\r\n---\r\nbody\r\n")
        self.assertEqual(header, ['title: "t"', "layout: post"])

    def test_a_response_of_only_a_fence_line_has_an_empty_body(self):
        self.assertEqual(self.split("---\n"), ("none", [], ""))


# ======================================================================================================================
# 모델 머리말을 보존해도 되는가
# ======================================================================================================================
class ModelHeaderTrustTest(unittest.TestCase):
    def problems(self, *lines):
        return g._model_header_problems(list(lines))

    def test_a_normal_model_header_is_trusted(self):
        self.assertEqual(self.problems(*HEADER.split("\n")), [])
        self.assertEqual(self.problems('title: "t"', "tags:", "  - a", "  - b", "lang: ko"), [])

    def test_a_missing_title_is_not_trusted(self):
        self.assertEqual(self.problems("layout: post", 'category: "c"'), ["제목(`title`) 줄이 없음"])
        self.assertEqual(self.problems(), ["제목(`title`) 줄이 없음"])

    def test_lang_and_image_must_be_single_line_values(self):
        for key in ("lang", "image"):
            with self.subTest(key):
                self.assertEqual(self.problems('title: "t"', f"{key}:", "  - x"), [f"`{key}` 는 한 줄 값이어야 함"])
                self.assertEqual(self.problems('title: "t"', f"{key}:"), [f"`{key}` 값이 비어 있음"])

    def test_header_grammar_problems_make_the_header_untrusted(self):
        self.assertTrue(self.problems('title: ""x": y"'))
        self.assertTrue(self.problems('title: "t"', 'title: "u"'))
        self.assertTrue(self.problems('title: "t"', "free text"))
        self.assertTrue(self.problems('title: "t"', "custom: [a"))

    def test_characters_yaml_cannot_read_make_the_header_untrusted(self):
        self.assertEqual(self.problems('title: "t\x7f"'), [UNREADABLE])

    def test_a_plain_category_and_extra_keys_are_trusted_because_the_engine_rewrites_or_keeps_them_as_before(self):
        self.assertEqual(self.problems('title: "t"', "category: 분야", "published: true", "date: 2026-10-20 08:20:00 +0900"), [])


# ======================================================================================================================
# validate_post_data — 머리말이 붙는 길
# ======================================================================================================================
def kr_only(kr_content, **fields):
    return make_data(kr_content, GOOD_EN_RESPONSE, en_title=GOOD_EN_TITLE, **fields)


class ValidatePostDataHeaderTest(unittest.TestCase):
    def kr(self, response, notes=None, **fields):
        out = validate(kr_only(response, **fields), **({} if notes is None else {"notes": notes}))
        return out["kr_content"]

    def test_a_good_model_header_is_kept_line_for_line_with_lang_and_image_moved_to_the_end(self):
        response = ('---\nlayout: post\ntitle: "제목"\nlang: ko\ncategory: "분야"\ntags:\n  - 가\n  - 나\nimage: "https://old.test/x.jpg"\ndate: 2026-10-20 08:20:00 +0900\n---\n\n'
                    + KR_BODY)
        text = self.kr(response, kr_category="분야")
        self.assertTrue(text.startswith('---\nlayout: post\ntitle: "제목"\ncategory: "분야"\ntags:\n  - 가\n  - 나\ndate: 2026-10-20 08:20:00 +0900\n'
                                        f'lang: ko\nimage: "{KR_IMAGE}"\n---\n\n이 글은'), text[:240])

    def test_the_category_line_always_comes_from_the_structured_value(self):
        text = self.kr('---\nlayout: post\ntitle: "제목"\ncategory: 모델이 쓴 분야\ntags: []\n---\n\n' + KR_BODY, kr_category="구조화된 분야")
        self.assertIn('category: "구조화된 분야"\n', text)
        self.assertNotIn("모델이 쓴 분야", text)

    def test_a_missing_layout_is_added_first(self):
        text = self.kr('---\ntitle: "제목"\ncategory: "c"\ntags: []\n---\n\n' + KR_BODY)
        self.assertTrue(text.startswith('---\nlayout: post\ntitle: "제목"\n'), text[:60])

    def test_an_untrusted_header_is_rewritten_from_the_structured_values_and_every_model_line_is_dropped(self):
        response = '---\nlayout: wide\ntitle: ""깨짐": 제목"\ncategory: "모델 분야"\ntags: [깨짐\nsecret_key: 모델이 쓴 값\n---\n\n' + KR_BODY
        text = self.kr(response, kr_title='"깨짐": 제목', kr_category="과학·환경", kr_tags=["가", "나"])
        header, body = split_post(text)
        self.assertEqual(header, ["layout: post", 'title: "\\"깨짐\\": 제목"', 'category: "과학·환경"', 'tags: ["가", "나"]', "lang: ko", f'image: "{KR_IMAGE}"'])
        self.assertTrue(first_body_line(body).startswith("이 글은 테스트용"))
        for dropped in ("wide", "모델 분야", "secret_key", "모델이 쓴 값"):
            self.assertNotIn(dropped, text)

    def test_the_rewritten_header_is_valid_even_for_a_title_with_newlines_backslashes_and_quotes(self):
        title = '줄바꿈\n그리고 "따옴표" 와 \\ 역슬래시 와 \t탭'
        text = self.kr('---\ntitle: 깨진 제목: 하나\n---\n\n' + KR_BODY, kr_title=title)
        header, _ = split_post(text)
        self.assertEqual(yaml.safe_load("\n".join(header))["title"], title)
        self.assertEqual(g.front_matter_problems(text), [])

    def test_a_response_without_any_header_gets_the_structured_one_and_keeps_its_text_untouched(self):
        for response in (KR_BODY, "\n\n" + KR_BODY, "  " + KR_BODY):
            with self.subTest(repr(response[:6])):
                text = self.kr(response, kr_title="제목")
                header, body = split_post(text)
                self.assertEqual(header[:3], ["layout: post", 'title: "제목"', 'category: "과학·환경"'])
                self.assertTrue("\n".join(body).lstrip().startswith("이 글은 테스트용"))

    def test_a_leading_rule_without_a_header_is_dropped(self):
        text = self.kr("---\n\n" + KR_BODY)
        self.assertEqual(g.front_matter_problems(text), [])
        self.assertTrue(first_body_line(split_post(text)[1]).startswith("이 글은 테스트용"))

    def test_a_byte_order_mark_does_not_make_a_second_header(self):
        text = self.kr('\ufeff---\nlayout: post\ntitle: "제목"\ncategory: "c"\ntags: []\n---\n\n' + KR_BODY)
        self.assertEqual(g.front_matter_problems(text), [])
        self.assertEqual(text.count("layout:"), 1)
        self.assertNotIn("\ufeff", text)

    def test_windows_line_endings_in_the_header_do_not_leave_carriage_returns(self):
        text = self.kr('---\r\nlayout: post\r\ntitle: "제목"\r\ncategory: "c"\r\ntags: []\r\n---\r\n\r\n' + KR_BODY)
        header, _ = split_post(text)
        self.assertEqual(g.front_matter_problems(text), [])
        self.assertFalse(any("\r" in line for line in header))
        self.assertEqual(header[1], 'title: "제목"')

    def test_a_stray_rule_after_a_good_header_is_dropped_and_the_model_header_is_kept(self):
        text = self.kr('---\nlayout: post\ntitle: "모델 제목"\ncategory: "c"\ntags:\n  - 가\n---\n\n---\n\n' + KR_BODY)
        header, body = split_post(text)
        self.assertEqual(header[:2], ["layout: post", 'title: "모델 제목"'])
        self.assertIn("  - 가", header)
        self.assertNotEqual(first_body_line(body), "---")

    def test_notes_say_which_header_was_rewritten_and_why_without_any_model_text(self):
        notes = []
        validate(make_data(QUOTED_TITLE_RESPONSE, DOUBLE_FENCE_EN_RESPONSE, kr_title=QUOTED_TITLE, en_title=DOUBLE_FENCE_EN_TITLE), notes=notes)
        self.assertEqual(len(notes), 2)
        self.assertTrue(notes[0].startswith("KR 머리말을 모델이 쓴 줄 대신 구조화된 값으로 다시 썼습니다("), notes[0])
        self.assertIn("`title` 값이 한 줄 JSON 문자열", notes[0])
        self.assertTrue(notes[1].startswith("EN 머리말을 모델이 쓴 줄 대신 구조화된 값으로 다시 썼습니다("), notes[1])
        self.assertIn("머리말 울타리가 어긋남", notes[1])
        for note in notes:
            self.assertNotIn("너에게", note)
            self.assertNotIn("Shifting", note)

    def test_no_note_for_a_good_header_or_for_a_response_without_a_header(self):
        for kr, en in ((GOOD_EN_RESPONSE.replace("lang: en", "lang: ko").replace("Science & Environment", "과학"), GOOD_EN_RESPONSE), (KR_BODY, EN_BODY)):
            notes = []
            validate(make_data(kr, en, en_title=GOOD_EN_TITLE), notes=notes)
            self.assertEqual(notes, [])

    def test_validate_post_data_still_works_without_the_notes_argument(self):
        self.assertEqual(g.front_matter_problems(self.kr(QUOTED_TITLE_RESPONSE, kr_title=QUOTED_TITLE)), [])

    def test_the_body_checks_still_run_on_the_repaired_response(self):
        with self.assertRaisesRegex(ValueError, "최소 편집 분량"):
            validate(kr_only("------\nlayout: post\ntitle: \"t\"\n---\n\n---\n\n짧은 글입니다.\n" + f"[원문]({LINK})\n"))

    def test_the_unsplash_thumbnail_and_the_category_lines_are_unchanged(self):
        text = self.kr('---\nlayout: post\ntitle: "제목"\ncategory: "c"\ntags: []\n---\n\n' + KR_BODY + "\n![x](https://images.unsplash.com/photo-1?w=1)\n")
        self.assertIn(f"![Thumbnail]({KR_IMAGE})", text)
        self.assertNotIn("photo-1?w=1", text)


# ======================================================================================================================
# 후보를 거르는 길과 마지막 방어선
# ======================================================================================================================
class GateAndGuardTest(unittest.TestCase):
    """generate_blog_posts 전체 흐름(가짜 피드·가짜 Gemini·임시 폴더)에서 깨진 머리말이 어디서 어떻게 걸러지는지."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name, value in (("DRY_RUN", False), ("STUB_GEMINI", False), ("STUB_UNSPLASH", True), ("FIX_IMAGES", False),
                            ("POSTS_DIR", self.root / "_posts"), ("HISTORY_FILE", self.root / "history.json")):
            patcher = mock.patch.object(g, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in (("now_kst", at(10, 12)),):
            patcher = mock.patch.object(g, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in (("url_ok", lambda url, timeout=10: True), ("trigger_download", lambda url: None)):
            patcher = mock.patch.object(g, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.slot = next(s for s in range(1, 30) if g.editorial_lane_order(s, [])[0] != "technology")

    def responses(self, *pairs):
        """pairs: (한글 응답, 영어 응답, 한글 제목, 영어 제목) 후보별 — 후보 i 의 제목은 '기술 기사 i' 로 구분한다."""
        titles = [f"기술 기사 {chr(0x41 + i)} 전혀 다른 소재 {i * 7}" for i in range(len(pairs))]
        table = {}
        for title, (kr, en, kr_title, en_title) in zip(titles, pairs):
            table[title] = json.dumps(make_data(kr, en, kr_title=kr_title, en_title=en_title), ensure_ascii=False)
        return titles, table

    def run_generation(self, pairs):
        titles, table = self.responses(*pairs)
        items = [candidate(title, LINK) for title in titles]
        written, report = [], {}
        calls = []

        def fake_gemini(prompt):
            calls.append(prompt)
            return SimpleNamespace(text=table[prompt])

        def fake_fetch(editorial_lane=None, stats=None, deadline=None, clock=None):
            if stats is not None:
                stats.setdefault("sources", []).append({"name": "x", "fetched": 4, "kept": len(items), "drops": {}})
            return list(items) if editorial_lane == "technology" else []

        with mock.patch.object(g, "build_post_prompt", lambda item, recent, category_hint="", allow_skip=False, editorial_lane=None: item["title"]), \
                mock.patch.object(g, "call_gemini_with_fallback", fake_gemini), mock.patch.object(g, "fetch_news_items", fake_fetch), \
                mock.patch.object(g, "get_client", side_effect=AssertionError("가짜 Gemini 만 쓴다")):
            real_write = g.write_text_atomic
            with mock.patch.object(g, "write_text_atomic", lambda path, content: (written.append((str(path), content)), real_write(path, content))[1]):
                try:
                    value, out = run_captured(g.generate_blog_posts, slot=self.slot, allow_auto_topic=False, report=report)
                except RuntimeError as exc:
                    value, out = exc, ""
        return value, report, out, written, calls

    def published_posts(self, written):
        return {Path(path).name: content for path, content in written if path.endswith(".md")}

    def test_the_two_real_failures_are_published_with_a_repaired_header_by_the_whole_flow(self):
        value, report, out, written, calls = self.run_generation(
            [(QUOTED_TITLE_RESPONSE, GOOD_EN_RESPONSE, QUOTED_TITLE, GOOD_EN_TITLE)])
        self.assertIsNotNone(value)
        self.assertEqual(report["outcome"], "PUBLISHED")
        posts = self.published_posts(written)
        self.assertEqual(len(posts), 2)
        for name, content in posts.items():
            self.assertEqual(g.front_matter_problems(content, candidate("x", LINK)), [], name)
        kr = next(c for n, c in posts.items() if "-KR-" in n)
        self.assertEqual(yaml.safe_load(kr.split("\n---\n", 1)[0][4:])["title"], QUOTED_TITLE)
        self.assertIn("[참고] KR 머리말을 모델이 쓴 줄 대신 구조화된 값으로 다시 썼습니다(", out)
        self.assertNotIn("너에게", out)         # 모델이 쓴 글은 로그에 싣지 않는다
        self.assertNotIn("EN 머리말을", out)

    def test_the_double_fence_pair_is_published_with_one_header_and_the_source_lines(self):
        value, report, out, written, _ = self.run_generation(
            [(DOUBLE_FENCE_KR_RESPONSE, DOUBLE_FENCE_EN_RESPONSE, DOUBLE_FENCE_KR_TITLE, DOUBLE_FENCE_EN_TITLE)])
        self.assertEqual(report["outcome"], "PUBLISHED")
        for name, content in self.published_posts(written).items():
            header, body = split_post(content)
            loaded = yaml.safe_load("\n".join(header))
            self.assertEqual(loaded["source_url"], LINK, name)
            self.assertTrue(loaded["description"], name)
            self.assertNotEqual(first_body_line(body), "---", name)

    def test_candidates_whose_final_header_would_be_broken_are_all_rejected_and_nothing_is_written(self):
        """`_front_matter_set` 이 조용히 아무것도 못 더하는 경우(옛 동작)를 흉내 내면 설명·출처 줄이 빠진다 — 첫 후보는 거절되고 다음 후보도 같은 이유로 거절된다."""
        with mock.patch.object(g, "_front_matter_set", lambda content, key, value: content):
            value, report, out, written, calls = self.run_generation(
                [(GOOD_EN_RESPONSE.replace("lang: en", "lang: ko"), GOOD_EN_RESPONSE, "한글 제목", GOOD_EN_TITLE)] * 2)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], "ALL_REJECTED")
        self.assertEqual(written, [])
        self.assertEqual(len(report["gate_rejects"]), 2)
        self.assertIn("머리말이 검사를 통과하지 못했습니다", report["gate_rejects"][0])
        self.assertIn("본문 검증 탈락", out)

    def test_one_bad_candidate_does_not_stop_the_run(self):
        """첫 후보의 한글 응답은 머리말을 닫지 않아 머리말 줄이 본문 앞에 남고(최종 검사가 거절), 둘째 후보가 발행된다."""
        broken = ("---\nlayout: post\ntitle: \"t\"\n\n본문 첫 줄이 머리말 뒤에 닫는 울타리 없이 이어집니다.\n" + KR_BODY)
        value, report, out, written, calls = self.run_generation([
            (broken, GOOD_EN_RESPONSE, "한글 제목", GOOD_EN_TITLE),
            (QUOTED_TITLE_RESPONSE, GOOD_EN_RESPONSE, QUOTED_TITLE, GOOD_EN_TITLE)])
        self.assertIsNotNone(value)
        self.assertEqual(report["outcome"], "PUBLISHED")
        self.assertEqual(len(report["gate_rejects"]), 1)
        self.assertIn("머리말 줄", report["gate_rejects"][0])
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(self.published_posts(written)), 2)

    def test_a_code_fenced_header_candidate_is_rejected_and_the_next_one_is_published(self):
        """```yaml 로 감싼 머리말 후보는 머리말 없는 응답으로 보아 코드 블록이 본문 앞에 남고, 그 안의 `layout:`·`title:` 줄이 본문 앞 세 줄에 있어 최종 검사가 거절한다 — 조용히 발행되지 않는다."""
        fenced = '```yaml\n---\nlayout: post\ntitle: "t"\ncategory: "c"\n---\n```\n\n' + KR_BODY
        value, report, out, written, calls = self.run_generation([
            (fenced, GOOD_EN_RESPONSE, "한글 제목", GOOD_EN_TITLE),
            (QUOTED_TITLE_RESPONSE, GOOD_EN_RESPONSE, QUOTED_TITLE, GOOD_EN_TITLE)])
        self.assertIsNotNone(value)
        self.assertEqual(report["outcome"], "PUBLISHED")
        self.assertEqual(len(report["gate_rejects"]), 1)
        self.assertIn("본문이 머리말 줄", report["gate_rejects"][0])
        self.assertEqual(len(calls), 2)
        for name, content in self.published_posts(written).items():
            self.assertNotIn("```", content, name)

    def test_the_last_line_of_defence_writes_nothing_when_the_finished_post_is_broken(self):
        """자리표시 이미지로 한 후보 검사는 통과했지만 실제 이미지 주소가 머리말을 깨는 경우(따옴표가 든 주소): 파일도 이력도 쓰지 않고 멈춘다. 한글·영어 글 각각."""
        bad_url, good_url = 'https://images.unsplash.com/photo-1?x="y', "https://images.unsplash.com/photo-2?w=1"
        for label, images, language in (("한글 글의 주소", [bad_url, good_url], "KR"), ("영어 글의 주소", [good_url, bad_url], "EN")):
            with self.subTest(label):
                with mock.patch.object(g, "pick_images", lambda queries, used, count=1, allow_pool=False, images=images: list(images)):
                    value, report, out, written, calls = self.run_generation(
                        [(GOOD_EN_RESPONSE.replace("lang: en", "lang: ko").replace("Science & Environment", "과학·환경"), GOOD_EN_RESPONSE, "한글 제목", GOOD_EN_TITLE)])
                self.assertIsInstance(value, RuntimeError)
                self.assertTrue(str(value).startswith(f"{language} 글 머리말이 검사를 통과하지 못해 글을 저장하지 않습니다"), str(value))
                self.assertEqual(written, [])
                self.assertFalse((self.root / "history.json").exists())

    def test_the_english_post_is_checked_too(self):
        data = validate(make_data(GOOD_EN_RESPONSE.replace("lang: en", "lang: ko"), GOOD_EN_RESPONSE, en_title=GOOD_EN_TITLE))
        data["en_content"] = data["en_content"].replace("---\nlayout: post", "------\nlayout: post", 1)
        with self.assertRaises(ValueError) as caught:
            g.check_final_front_matter(data, SOURCE)
        self.assertTrue(str(caught.exception).startswith("EN 글 머리말이 검사를 통과하지 못했습니다: 첫 줄이 정확히"), str(caught.exception))

    def test_check_final_front_matter_names_the_language_and_the_first_problems_only(self):
        data = validate(make_data(GOOD_EN_RESPONSE.replace("lang: en", "lang: ko"), GOOD_EN_RESPONSE, en_title=GOOD_EN_TITLE))
        with mock.patch.object(g, "_front_matter_set", lambda content, key, value: content):
            with self.assertRaises(ValueError) as caught:
                g.check_final_front_matter(data, SOURCE)
        message = str(caught.exception)
        self.assertTrue(message.startswith("KR 글 머리말이 검사를 통과하지 못했습니다: "), message)
        self.assertEqual(message.count(" / "), 2)         # 문제는 앞의 세 개만
        self.assertNotIn("\n", message)


# ======================================================================================================================
# 한 줄 목록(`tags: [a, b]`) 검사 — 정규식 폭주(N1)와 `?`·잘못된 이스케이프(N2)
# ======================================================================================================================
ESC = chr(92)      # 역슬래시 — 소스에 이스케이프를 쓰지 않으려고 코드 포인트로 만든다(편집 도구가 이스케이프를 실제 글자로 바꿔 쓰는 일이 있다)


class FlowListShapeTest(unittest.TestCase):
    """JSON 으로 읽히지 않는 한 줄 목록(따옴표 없는 항목·작은따옴표 항목이 섞인 것)은 정규식(`_FM_FLOW_LIST`)이 가른다 — 무엇을 받고 무엇을 거절하는지."""

    def test_lists_with_ordinary_spacing_are_accepted_and_pyyaml_reads_them_as_lists(self):
        for value in ("[a, b]", "[a ,b]", "[a , b]", "[a,b]", "[ a ]", "[ a , b ]", "[a b, c d]", "[a  b]", "[a, b, ]", "[a,]", "[a ,]", "[a , ]", "[]", "[ ]",
                      "['a', b]", "['it''s', b]", "['a'  ,  'b' ]", '["a", b]', "[가나 다, 라]", "[a-b, c.d, e_f, 1, 2.5]", "[a!b, c&d, e*f, g|h, i>j, k%l, m@n, o`p]",
                      '["a' + ESC + 'nb", c]', '["a' + ESC + 'u00e9", b]', '["a' + ESC + '"b", c]', '["a' + ESC + ESC + 'b", c]'):
            with self.subTest(value):
                self.assertTrue(g._fm_flow_list_ok(value))
                self.assertIsInstance(yaml.safe_load("tags: " + value)["tags"], list)

    def test_malformed_lists_are_refused(self):
        for value in ("[a, b", "a, b]", "[a b] c", "[a,, b]", "[,a]", "[a, #]", "[a #b]", "[a: b]", "[a:b]", "[[a]]", "[{a}]", "[a, {b}]", '["a" "b"]', "['a' 'b']",
                      '["a"b]', "[a, b]]", "[[a, b]"):
            with self.subTest(value):
                self.assertFalse(g._fm_flow_list_ok(value))

    def test_a_question_mark_in_a_plain_item_is_refused_because_yaml_cannot_read_it(self):
        """한 줄 목록 안에서 `?` 는 평문 항목을 끝내는 '키' 표지다 — `[a?b]` 는 PyYAML 이 ParserError 로 읽지 못한다(검증자 N2). 따옴표 안의 `?` 는 괜찮다."""
        for value in ("[a?b]", "[a, b?]", "[what? yes]", "[a ? b]", "[a, b ?]"):
            with self.subTest(value):
                with self.assertRaises(yaml.YAMLError):
                    yaml.safe_load("tags: " + value)            # 정말 읽지 못하는 모양이다
                self.assertFalse(g._fm_flow_list_ok(value))
        for value in ("[?]", "[a, ?b]", "[? a]"):               # 읽히기는 해도(한 쌍짜리 사전) 태그 목록이 아니다
            with self.subTest(value):
                self.assertFalse(g._fm_flow_list_ok(value))
        for value in ('["a?b"]', '["what? yes", "b?"]', "['a?b']", "['what?', \"why?\"]", "[x, 'a?b']", "['a', \"b?\" , c]"):
            with self.subTest(value):
                self.assertTrue(g._fm_flow_list_ok(value))
                self.assertIsInstance(yaml.safe_load("tags: " + value)["tags"], list)

    def test_a_double_quoted_item_may_only_use_escapes_yaml_knows(self):
        """JSON 으로 읽히지 않는 목록(작은따옴표·평문 항목이 섞인 것)의 큰따옴표 항목에 `\\q` 같은 이스케이프가 있으면 PyYAML·libyaml 이 읽지 못한다(소리 없이 받아들이던 구멍 —
        N2 를 찾으려고 만든 무작위 대조가 드러냈다)."""
        for value in ('[x, "a' + ESC + 'qb"]', '[x, "' + ESC + ']"]', "['x', \"a" + ESC + "+b\"]", '[x, "a' + ESC + 'u12g4"]', '[x, "a' + ESC + 'u12"]'):
            with self.subTest(value):
                with self.assertRaises(yaml.YAMLError):
                    yaml.safe_load("tags: " + value)
                self.assertFalse(g._fm_flow_list_ok(value))

    def test_the_header_level_checks_use_the_same_rule(self):
        for value in ("[a, b?]", "[a?b]", '[x, "a' + ESC + 'qb"]'):
            with self.subTest(value):
                self.only_problem(with_replaced('tags: ["a", "b"]', f"tags: {value}"))
                self.assertEqual(g._model_header_problems(['title: "t"', f"tags: {value}"]), ["`tags` 값이 한 줄 목록([…])이 아님"])

    def only_problem(self, text):
        problems = g.front_matter_problems(text)
        self.assertEqual(problems, ["`tags` 값이 한 줄 목록([…])이 아님"])

    def test_question_marks_stay_accepted_where_yaml_allows_them(self):
        for line in ("tags:\n  - what? yes\n  - a?b", 'tags: ["what?", "b"]'):
            with self.subTest(line):
                text = with_replaced('tags: ["a", "b"]', line)
                self.assertEqual(g.front_matter_problems(text), [])
                self.assertIsInstance(yaml.safe_load(text.split("\n---\n", 1)[0][4:])["tags"], list)
        self.assertEqual(g.front_matter_problems(with_replaced("lang: ko\n", "lang: ko\ncustom: https://a.test/x?y=1\n")), [])

    def test_every_list_the_check_accepts_is_a_flat_list_for_pyyaml(self):
        """무작위로 만든 한 줄 목록 1만 개: 검사가 받아들인 것은 PyYAML 이 모두 안쪽 목록·사전 없는 목록으로 읽는다. 받아들이고도 읽지 못하는 것이 하나라도 있으면 실패한다
        (`?` 와 `\\q` 가 이렇게 드러났다). 알파벳에 탭·제어 문자·`=` 는 없다 — 제어 문자는 머리말 전체 검사(_YAML_UNPRINTABLE)가 따로 막고, 탭과 `=` 는 PyYAML 만 못 읽는다
        (Jekyll 이 쓰는 libyaml 은 읽는다)."""
        rng = random.Random(20261029)
        alphabet = list("ab가 ,,,?:#-[]\"'!&*|>%@`{}1") + [ESC, "''", " , ", ESC + '"', ESC + "n", ESC + "q"]
        accepted = 0
        for _ in range(10000):
            value = "[" + "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 11))) + "]"
            if not g._fm_flow_list_ok(value):
                continue
            accepted += 1
            try:
                loaded = yaml.safe_load("tags: " + value)["tags"]
            except yaml.YAMLError as exc:
                self.fail(f"받아들였지만 PyYAML 이 읽지 못함: {value!r} ({type(exc).__name__})")
            self.assertIsInstance(loaded, list, value)
            self.assertFalse(any(isinstance(item, (list, dict)) for item in loaded), value)
        self.assertGreater(accepted, 800)      # 받아들이는 쪽도 충분히 돌았다(속 빈 시험이 아니다)


class FlowListSpeedTest(unittest.TestCase):
    """한 줄 목록 검사는 입력 길이에 비례해 끝난다. 검증자 N1: 평문 항목의 꼬리가 공백까지 먹고 뒤의 `[ \\t]*` 가 또 먹어서 되돌아가기(backtracking)가 항목 수의 지수로 늘었다 —
    `tags: [a ,a ,… #]` 처럼 끝이 틀린 줄에서 항목 22개 1.3초, 하나 늘 때마다 두 배(25개 10.5초, 26개 20.8초 — 30개는 5분 남짓, 35개는 몇 시간)라 슬롯 실행이 멈춘다.
    시간 제한 0.2초는 넉넉한 값이다(고친 코드는 1000분의 몇 초).
    아래 입력은 옛 정규식에서도 몇 초면 끝나는 크기로 골랐다(시험이 영영 멈추지 않고 실패한다)."""
    LIMIT = 0.2
    SHAPES = (
        ("쉼표 앞 공백 한 칸 + 끝 #", "[" + ",".join(["a "] * 22) + "#]"),
        ("쉼표 앞 탭 + 끝 #", "[" + ",".join(["a" + chr(9)] * 22) + "#]"),
        ("쉼표 앞 공백 5칸 + 끝 #", "[" + ",".join(["a" + " " * 5] * 8) + "#]"),
        ("쉼표 앞 공백 한 칸 + 끝 :", "[" + ",".join(["a "] * 22) + ":]"),
        ("닫는 괄호 없음", "[" + ",".join(["a "] * 22)),
        ("앞뒤 공백 + 끝 #", "[" + ",".join([" a "] * 22) + "#]"),
        ("쉼표 앞 공백 둘 + 끝 #", "[" + " , ".join(["a "] * 14) + "#]"),
        ("여러 낱말 + 끝 #", "[" + ",".join(["a b "] * 20) + "#]"),
    )

    def timed(self, call):
        """call 의 걸린 시간과 결과를 돌려준다. 시간 제한을 넘으면 최대 세 번까지 다시 재서 가장 빠른 값을 쓴다 — 한 번의 일시적인 멈춤으로 시험이 흔들리지 않게 한다(정규식이 정말 느리면 세 번 다
        느리고, 제한의 열 배를 넘게 느리면 일시적인 멈춤일 수 없어 다시 재지 않는다)."""
        best, result = None, None
        for _ in range(3):
            started = time.perf_counter()
            result = call()
            spent = time.perf_counter() - started
            best = spent if best is None else min(best, spent)
            if best < self.LIMIT or spent > 10 * self.LIMIT:
                break
        return best, result

    def test_the_worst_shapes_finish_within_the_time_limit(self):
        for label, value in self.SHAPES:
            with self.subTest(label):
                spent, problem = self.timed(lambda: g._fm_value_problem("tags", value))
                self.assertIsNotNone(problem)             # 모두 잘못된 목록이다
                self.assertLess(spent, self.LIMIT, f"{label}: {spent:.2f}초")

    def test_every_check_that_reads_the_line_is_fast_too(self):
        bad = "[" + ",".join(["a "] * 22) + "#]"
        response = f'---\nlayout: post\ntitle: "제목"\ncategory: "c"\ntags: {bad}\n---\n\n' + KR_BODY
        for label, call in (("최종 검사", lambda: g.front_matter_problems(with_replaced('tags: ["a", "b"]', f"tags: {bad}"))),
                            ("모델 머리말 신뢰 검사", lambda: g._model_header_problems(['title: "t"', f"tags: {bad}"])),
                            ("블록 목록 항목 검사", lambda: g._fm_value_problem("item", bad)),
                            ("validate_post_data 전체", lambda: validate(kr_only(response, kr_title="제목", kr_tags=("가", "나")))["kr_content"])):
            with self.subTest(label):
                spent, result = self.timed(call)
                self.assertTrue(result, label)
                self.assertLess(spent, self.LIMIT, f"{label}: {spent:.2f}초")

    def test_a_response_with_such_a_tags_line_gets_a_clean_rewritten_header(self):
        bad = "[" + ",".join(["a "] * 22) + "#]"
        notes = []
        text = validate(kr_only(f'---\nlayout: post\ntitle: "제목"\ncategory: "c"\ntags: {bad}\n---\n\n' + KR_BODY, kr_title="제목", kr_tags=("가", "나")), notes=notes)["kr_content"]
        self.assertIn('tags: ["가", "나"]\n', text)
        self.assertEqual(g.front_matter_problems(text), [])
        self.assertEqual(len(notes), 1)
        self.assertIn("`tags` 값이 한 줄 목록", notes[0])

    def test_long_valid_lists_are_accepted_quickly(self):
        for label, value in (("1자 항목 600개", "[" + ",".join(["a"] * 600) + "]"), ("낱말 둘짜리 150개", "[" + ", ".join(["alpha beta"] * 150) + "]"),
                             ("쉼표 앞 공백 600개", "[" + " ,".join(["a"] * 600) + " ]"), ("작은따옴표 항목 250개", "[" + ", ".join(["'a b'"] * 250) + "]")):
            with self.subTest(label):
                self.assertLessEqual(len(value), 2000)
                spent, problem = self.timed(lambda: g._fm_value_problem("tags", value))
                self.assertIsNone(problem)
                self.assertLess(spent, self.LIMIT, f"{label}: {spent:.2f}초")

    def test_random_adversarial_lines_never_take_long(self):
        """무작위로 고른 위험한 모양(쉼표 앞 공백 한 칸·탭·둘·다섯 칸·앞뒤 공백·낱말 둘)을 항목 수를 바꿔 가며 틀린 끝으로 닫는다 — 모두 0.2초 안에 끝나야 한다."""
        rng = random.Random(7)
        shapes = (("a ", 20, 23, ","), ("a" + chr(9), 20, 23, ","), ("a ", 11, 13, " ,"), ("a" + " " * 5, 7, 8, ","), (" a ", 20, 22, ","), ("a b ", 18, 20, ","))
        tails = ["#]", ":]", "", "?]", " #"]
        worst = 0.0
        for _ in range(40):
            item, low, high, separator = rng.choice(shapes)
            value = "[" + separator.join([item] * rng.randint(low, high)) + rng.choice(tails)
            spent, _ = self.timed(lambda: g._fm_value_problem("tags", value))
            worst = max(worst, spent)
        self.assertLess(worst, self.LIMIT, f"가장 느린 줄 {worst:.2f}초")

    def test_the_other_header_patterns_are_linear_on_long_lines(self):
        """같은 겹침(양쪽이 같은 글자를 먹는 반복)이 다른 머리말 정규식에도 있는지 보는 시험. 두 단계로 돈다: ① 짧은 줄(18~46글자) — 되돌아가기가 지수로 느는 정규식은 이것만으로 몇 초가 걸린다
        ② 길고 공백·대시가 많은 줄(1,990글자) — 제곱으로 느는 정규식이 드러난다. ① 에서 느린 것이 나오면 ② 는 돌리지 않는다(지수로 느린 정규식에 긴 줄을 주면 끝나지 않는다)."""
        short = (("키 모양 + 틀린 끝", "a" * 18 + "!"), ("대시 뭉치", "-" * 46 + " x"), ("닫히지 않은 작은따옴표 값", "custom: '" + "a" * 26))
        long = (("키 뒤 공백 뭉치", "custom:" + " " * 1990 + "x"), ("들여쓴 목록 항목 뒤 공백", " " * 1900 + "-" + " " * 90 + "x"), ("대시 뭉치", "-" * 1990 + " x"),
                ("키 모양 긴 이름", "a" * 1990 + ":"), ("작은따옴표 뭉치", "custom: '" + "''" * 990 + "x"), ("따옴표 안 역슬래시", 'custom: "' + (ESC + '"') * 990 + "x"),
                ("공백과 샵", "custom: " + " #" * 990 + "x"), ("콜론 뭉치", "custom: " + ":" * 1980))
        for phase, shapes in (("짧은 줄", short), ("긴 줄", long)):
            slow = []
            for label, line in shapes:
                text = with_replaced("lang: ko\n", f"lang: ko\n{line}\n")
                spent_check, _ = self.timed(lambda: g.front_matter_problems(text))
                spent_split, _ = self.timed(lambda: g._split_model_content(text + "\n" + KR_BODY))
                if max(spent_check, spent_split) >= self.LIMIT:
                    slow.append(f"{label}: {spent_check:.2f}·{spent_split:.2f}초")
            self.assertEqual(slow, [], f"{phase}에서 느린 정규식")


# ======================================================================================================================
# YAML 이 줄바꿈으로 읽는 글자 U+0085·U+2028·U+2029 (N3)
# ======================================================================================================================
NEL, LS, PS = chr(0x85), chr(0x2028), chr(0x2029)      # 소스에 날 글자를 넣지 않으려고 코드 포인트로 만든다
LINE_BREAKS = (("U+0085", NEL), ("U+2028", LS), ("U+2029", PS))
UNREADABLE = "머리말에 YAML 이 읽지 못하는 제어 문자나 줄바꿈으로 읽는 U+0085·U+2028·U+2029 가 있음"


class YamlLineBreakCharacterTest(unittest.TestCase):
    """U+0085(NEL)·U+2028(줄 구분)·U+2029(문단 구분)는 YAML 이 줄바꿈으로 읽는 글자다(검증자 N3). `json.dumps(ensure_ascii=False)` 는 이 글자를 날 글자로 두는데, 머리말 한 줄 안에 날 글자로 있으면
    큰따옴표 제목 안의 NEL 은 공백으로 접혀 제목이 조용히 바뀌고, 따옴표 없는 값 안에서는 읽지 못하며, 키 줄 사이에서는 줄이 갈라져 다른 키가 끼어든다. 그래서 모델이 쓴 머리말에 날 글자가 있으면
    믿지 않고 다시 쓰며, 우리가 쓰는 JSON 한 줄에서는 `\\uXXXX` 로 이스케이프해 글자(제목·분야·태그)를 그대로 보존한다."""

    def kr(self, response, notes=None, **fields):
        return validate(kr_only(response, **fields), **({} if notes is None else {"notes": notes}))["kr_content"]

    def test_the_premise_json_dumps_leaves_them_raw_and_pyyaml_misreads_them(self):
        for name, char in LINE_BREAKS:
            with self.subTest(name):
                self.assertIn(char, json.dumps("a" + char + "b", ensure_ascii=False))
                with self.assertRaises(yaml.YAMLError):
                    yaml.safe_load("custom: a" + char + "b")
                self.assertEqual(yaml.safe_load("layout: post" + char + "title: x"), {"layout": "post", "title": "x"})      # 줄바꿈이 되어 키가 끼어든다
                self.assertTrue(g._YAML_UNPRINTABLE.search(char), "그래서 날 글자는 읽지 못하는 글자로 취급한다")
        self.assertEqual(yaml.safe_load('title: "a' + NEL + 'b"')["title"], "a b")      # 날 NEL 은 공백으로 접힌다 — 제목이 바뀐다

    def test_a_raw_line_break_character_in_the_header_is_a_problem_wherever_it_is(self):
        for name, char in LINE_BREAKS:
            for label, text in (("큰따옴표 제목", with_replaced("제목", "제" + char + "목")), ("분야", with_replaced("분야", "분" + char + "야")),
                                ("태그 목록", with_replaced('["a", "b"]', '["a' + char + '", "b"]')),
                                ("따옴표 없는 값", with_replaced("lang: ko\n", "lang: ko\ncustom: a" + char + "b\n")),
                                ("키 줄 사이", with_replaced("lang: ko", "lang: ko" + char + "published: false"))):
                with self.subTest(f"{name} {label}"):
                    self.assertIn(UNREADABLE, g.front_matter_problems(text))

    def test_the_other_unreadable_characters_are_still_a_problem_and_the_body_is_not_checked(self):
        for char in (chr(0x7f), chr(0x84), chr(0x86), chr(0x9f), chr(0x0b), chr(0x00), chr(0xd800), chr(0xfffe)):
            with self.subTest(hex(ord(char))):
                self.assertIn(UNREADABLE, g.front_matter_problems(with_replaced("분야", "분" + char + "야")))
        for char in (chr(0xa0), chr(0x2027), chr(0x202a), chr(0x3000), chr(0xfeff), chr(0x1F600)):      # 읽히는 글자(바로 옆 코드 포인트)는 그대로 받는다
            with self.subTest(hex(ord(char))):
                self.assertNotIn(UNREADABLE, g.front_matter_problems(with_replaced("분야", "분" + char + "야")))
        for name, char in LINE_BREAKS:
            self.assertEqual(g.front_matter_problems(with_replaced("본문 첫 줄입니다.", "본문" + char + "첫 줄입니다.")), [], name)

    def test_a_model_header_with_a_raw_line_break_character_is_not_trusted(self):
        for name, char in LINE_BREAKS:
            with self.subTest(name):
                self.assertEqual(g._model_header_problems(['title: "앞' + char + '뒤"']), [UNREADABLE])
                self.assertEqual(g._model_header_problems(['title: "t"', "tags: [a" + char + "b]"]), [UNREADABLE])
                self.assertEqual(g._model_header_problems(['title: "t"', "category: 분" + char + "야"]), [UNREADABLE])

    def test_json_line_is_json_dumps_except_for_the_three_characters(self):
        for value in ("한글", 'quote"d', ESC + "slash", "tab" + chr(9) + "here", "emoji" + chr(0x1F600), "del" + chr(0x7f), "", ["a", "b"], ["가", '나"다'], "a" * 50):
            with self.subTest(repr(value)[:20]):
                self.assertEqual(g._json_line(value), json.dumps(value, ensure_ascii=False))
        for name, char in LINE_BREAKS:
            with self.subTest(name):
                for value in ("a" + char + "b", ["x", "a" + char + "b"]):
                    line = g._json_line(value)
                    self.assertNotIn(char, line)
                    self.assertEqual(json.loads(line), value)
                    self.assertEqual(yaml.safe_load("k: " + line)["k"], value)
                self.assertIn(ESC + "u%04x" % ord(char), g._json_line("a" + char + "b"))

    def test_a_title_category_and_tags_with_the_characters_are_written_escaped_and_read_back_exactly(self):
        for name, char in LINE_BREAKS:
            with self.subTest(name):
                title, category, tags = "앞" + char + "뒤", "분" + char + "야", ["가" + char + "다", "나"]
                text = self.kr(KR_BODY, kr_title=title, kr_category=category, kr_tags=tags)
                header, _ = split_post(text)
                self.assertNotIn(char, "\n".join(header))
                loaded = yaml.safe_load("\n".join(header))
                self.assertEqual((loaded["title"], loaded["category"], loaded["tags"]), (title, category, tags))
                self.assertEqual(g.front_matter_problems(text), [])

    def test_the_fresh_header_escapes_each_structured_value_on_its_own(self):
        """`validate_post_data` 가 분야 줄을 다시 쓰므로 위 시험으로는 `_fresh_front_matter` 의 분야 줄이 가려진다 — 함수를 직접 부른다."""
        for name, char in LINE_BREAKS:
            with self.subTest(name):
                data = {"kr_title": "앞" + char + "뒤", "kr_category": "분" + char + "야", "kr_tags": ["가" + char + "다"]}
                header = g._fresh_front_matter(data, "kr", "ko", KR_IMAGE)
                self.assertNotIn(char, header)
                loaded = yaml.safe_load(header.split("\n---\n", 1)[0][4:])
                self.assertEqual((loaded["title"], loaded["category"], loaded["tags"]), (data["kr_title"], data["kr_category"], data["kr_tags"]))

    def test_a_model_header_with_a_raw_character_is_rewritten_and_the_title_survives_exactly(self):
        for name, char in LINE_BREAKS:
            with self.subTest(name):
                notes, title = [], "앞" + char + "뒤"
                text = self.kr('---\nlayout: post\ntitle: "' + title + '"\ncategory: "c"\ntags: []\n---\n\n' + KR_BODY, notes, kr_title=title)
                header, _ = split_post(text)
                self.assertNotIn(char, "\n".join(header))
                self.assertEqual(yaml.safe_load("\n".join(header))["title"], title)
                self.assertEqual(g.front_matter_problems(text), [])
                self.assertEqual(len(notes), 1)
                self.assertIn("제어 문자", notes[0])

    def test_the_lines_the_engine_adds_later_escape_them_too(self):
        for name, char in LINE_BREAKS:
            with self.subTest(name):
                text = g._front_matter_set(GOOD, "category", "분" + char + "야")
                self.assertEqual(g.front_matter_problems(text), [])
                self.assertEqual(yaml.safe_load(text.split("\n---\n", 1)[0][4:])["category"], "분" + char + "야")
                source = dict(SOURCE, source="NASA" + char + "Lab")
                finished = g.add_discovery_metadata(with_replaced("본문 첫 줄입니다.\n", FrontMatterProblemsSourceTest.LONG_BODY), source)
                self.assertEqual(g.front_matter_problems(finished, source), [])
                self.assertEqual(yaml.safe_load(finished.split("\n---\n", 1)[0][4:])["source_name"], "NASA" + char + "Lab")


# ======================================================================================================================
# 레이아웃은 post (N4)
# ======================================================================================================================
class LayoutRuleTest(unittest.TestCase):
    """글의 레이아웃은 `post` 여야 한다(검증자 N4). 모델이 `layout: default` 같은 줄을 써도 옛 코드는 그대로 보존해 사이트가 글 모양으로 그리지 않았다. 이제 `layout` 줄이 있는데 값이 정확히
    post 가 아니면 머리말을 믿지 않고 다시 쓴다. 값이 post 로 읽히는 세 표기(`post`·`"post"`·`'post'`)는 지금처럼 그대로 보존한다(좋은 입력의 출력은 바이트 동일). `layout` 줄이 없는 것은
    지금처럼 엔진이 맨 앞에 `layout: post` 를 넣는다. `published`·`date`·`permalink`·`slug`·`redirect_from` 같은 다른 Jekyll 키는 건드리지 않는다(허용 키 목록은 두지 않는다 — 열린 문제 ②)."""

    OTHER = ("default", "page", "Post", "POST", "posts", "post2", "post.html", '""', "''", '"default"', "'default'", "[post]", "null", "~")

    def test_the_final_check_wants_layout_post(self):
        for value in self.OTHER:
            with self.subTest(value):
                self.assertEqual(g.front_matter_problems(with_replaced("layout: post", f"layout: {value}")), ["`layout` 값이 post 가 아님"])
        for value in ("post", '"post"', "'post'"):
            with self.subTest(value):
                self.assertEqual(g.front_matter_problems(with_replaced("layout: post", f"layout: {value}")), [])

    def test_a_layout_given_as_a_block_list_is_refused(self):
        self.assertIn("`layout` 값이 post 가 아님", g.front_matter_problems(with_replaced("layout: post", "layout:\n  - post")))

    def test_a_missing_layout_is_still_only_a_missing_key(self):
        self.assertEqual(g.front_matter_problems(with_replaced("layout: post\n", "")), ["필수 키 `layout` 줄이 없음"])

    def test_a_model_header_with_another_layout_is_not_trusted(self):
        for value in self.OTHER:
            with self.subTest(value):
                self.assertEqual(g._model_header_problems([f"layout: {value}", 'title: "t"']), ["`layout` 값이 post 가 아님"])
        for value in ("post", '"post"', "'post'"):
            with self.subTest(value):
                self.assertEqual(g._model_header_problems([f"layout: {value}", 'title: "t"']), [])
        self.assertEqual(g._model_header_problems(['title: "t"']), [])      # 줄이 없으면 엔진이 맨 앞에 `layout: post` 를 넣는다

    def test_a_model_layout_other_than_post_gets_the_header_rewritten_with_layout_post(self):
        for value in ("default", '"page"'):
            with self.subTest(value):
                notes = []
                response = f'---\nlayout: {value}\ntitle: "제목"\ncategory: "c"\ntags: ["가"]\ndate: 2026-10-20 08:20:00 +0900\n---\n\n' + KR_BODY
                text = validate(kr_only(response, kr_title="제목", kr_tags=("가", "나")), notes=notes)["kr_content"]
                header, _ = split_post(text)
                self.assertEqual(header, ["layout: post", 'title: "제목"', 'category: "과학·환경"', 'tags: ["가", "나"]', "lang: ko", f'image: "{KR_IMAGE}"'])
                self.assertEqual(g.front_matter_problems(text), [])
                self.assertEqual(len(notes), 1)
                self.assertIn("`layout` 값이 post 가 아님", notes[0])

    def test_layout_post_in_its_three_spellings_is_kept_byte_for_byte(self):
        for layout in ("layout: post", 'layout: "post"', "layout: 'post'"):
            with self.subTest(layout):
                response = f'---\n{layout}\ntitle: "제목"\ncategory: "c"\ntags: []\n---\n\n' + KR_BODY
                data = kr_only(response, kr_title="제목")
                got = validate(copy.deepcopy(data))["kr_content"]
                self.assertEqual(got, legacy_validate_post_data(copy.deepcopy(data), KR_IMAGE, EN_IMAGE, LINK)["kr_content"])
                self.assertTrue(got.startswith(f"---\n{layout}\n"))

    def test_other_jekyll_keys_in_a_good_header_are_not_touched(self):
        extra = "published: false\ndate: 2026-10-20 08:20:00 +0900\npermalink: /posts/x/\nslug: x\nredirect_from:\n  - /old/\n"
        response = f'---\nlayout: post\ntitle: "제목"\ncategory: "c"\ntags: []\n{extra}---\n\n' + KR_BODY
        data = kr_only(response, kr_title="제목")
        got = validate(copy.deepcopy(data))["kr_content"]
        self.assertEqual(got, legacy_validate_post_data(copy.deepcopy(data), KR_IMAGE, EN_IMAGE, LINK)["kr_content"])
        self.assertIn(extra, got)


# ======================================================================================================================
# 코드 블록으로 감싼 머리말(열린 문제 ③)
# ======================================================================================================================
class CodeFencedHeaderTest(unittest.TestCase):
    """머리말을 코드 블록(```yaml 등)으로 감싼 응답은 머리말 없는 응답으로 본다 — 코드 블록이 본문 맨 앞에 남는다. 그렇다고 '검사하지 않는' 것은 아니다: 코드 블록 안의 `layout:`·`title:` 같은 줄이
    본문의 앞 세 줄(빈 줄 제외)에 들어 있으면 최종 검사가 그 후보를 거절한다. 그보다 뒤에 있으면 검사하지 않는다(현재 한계)."""

    def response(self, opening, *inner):
        return opening + "\n" + "\n".join(inner) + "\n```\n\n" + KR_BODY

    def test_a_fenced_header_is_not_taken_for_a_header(self):
        for opening in ("```yaml", "```yml", "```markdown", "```"):
            with self.subTest(opening):
                kind, header, body = g._split_model_content(self.response(opening, "---", "layout: post", 'title: "t"', "---"))
                self.assertEqual((kind, header), ("none", []))
                self.assertTrue(body.startswith(opening))

    def test_the_final_check_rejects_the_candidate_when_a_header_key_is_among_the_first_three_body_lines(self):
        for opening in ("```yaml", "```markdown", "```"):
            for inner in (("---", "layout: post", 'title: "t"', "---"), ("layout: post", 'title: "t"'), ("title: t",), ("# 머리말", "title: t")):
                with self.subTest(opening=opening, inner=inner):
                    data = validate(kr_only(self.response(opening, *inner)))
                    with self.assertRaises(ValueError) as caught:
                        g.check_final_front_matter(data, SOURCE)
                    self.assertTrue(str(caught.exception).startswith("KR 글 머리말이 검사를 통과하지 못했습니다"), str(caught.exception))
                    self.assertIn("본문이 머리말 줄", str(caught.exception))

    def test_a_header_key_beyond_the_first_three_body_lines_is_not_checked(self):
        """현재 한계를 고정한다: 코드 블록 안의 머리말 줄이 본문 앞 세 줄 밖에 있으면 최종 검사가 보지 못한다."""
        data = validate(kr_only(self.response("```yaml", "# 가", "# 나", "# 다", "layout: post")))
        g.check_final_front_matter(data, SOURCE)        # 거절하지 않는다


# ======================================================================================================================
# 옛 함수와의 바이트 비교(좋은 입력의 출력은 그대로)
# ======================================================================================================================
def legacy_validate_post_data(data, kr_image, en_image, verified_source_url=None):
    """기준 main(30f5b7c)의 validate_post_data 사본 — 좋은 입력의 출력이 바이트 단위로 같음을 보이는 비교용이다. 고치지 않는다."""
    for key in ("kr_category", "kr_title", "kr_content",
                "en_category", "en_title", "en_content"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"생성 결과의 {key} 값이 비었거나 문자열이 아닙니다.")
    for key in ("kr_tags", "en_tags"):
        if not isinstance(data.get(key), list):
            data[key] = []
        data[key] = [str(t).strip() for t in data[key] if str(t).strip()]

    for prefix, image_url in (("kr", kr_image), ("en", en_image)):
        html_lang = "ko" if prefix == "kr" else "en"
        content = data[f"{prefix}_content"]
        if not content.lstrip().startswith("---"):
            content = (
                "---\nlayout: post\n"
                f"title: {json.dumps(data[f'{prefix}_title'], ensure_ascii=False)}\n"
                f"category: {json.dumps(data[f'{prefix}_category'], ensure_ascii=False)}\n"
                f"tags: {json.dumps(data[f'{prefix}_tags'], ensure_ascii=False)}\n"
                f"lang: {html_lang}\nimage: {json.dumps(image_url)}\n---\n\n" + content
            )
        else:
            content = content.lstrip()
            end = content.find("\n---", 3)
            if end != -1:
                front = content[3:end]
                body = content[end + 4:].lstrip("\n")
                front = re.sub(r"(?m)^image:\s*.*$", "", front)
                front = re.sub(r"(?m)^lang:\s*.*$", "", front)
                front = re.sub(r"\n{2,}", "\n", front).rstrip()
                if not re.search(r"(?m)^layout\s*:", front):
                    rest = front.strip()
                    front = "\nlayout: post" + ("\n" + rest if rest else "")
                front += f'\nlang: {html_lang}\nimage: "{image_url}"'
                content = f"---{front}\n---\n\n{body}"

        content = g._front_matter_set(content, "category", data[f"{prefix}_category"])
        g._validate_editorial_body(content, prefix, verified_source_url)

        if not re.search(r"(?m)^!\[[^\]]*\]\(", content):
            content = content.rstrip() + f"\n\n![Thumbnail]({image_url})\n"
        else:
            content = re.sub(
                r"(?m)^!\[[^\]]*\]\(https://images\.unsplash\.com/[^)]+\)",
                f"![Thumbnail]({image_url})", content, count=1)
        data[f"{prefix}_content"] = content.rstrip() + "\n"
    return data


def legacy_add_discovery_metadata(content, source=None):
    """기준 main(30f5b7c)의 add_discovery_metadata 사본(출처 세 줄 조건을 인라인으로 쓰던 때). 비교용이다. 고치지 않는다."""
    description = g._description_from_markdown(content)
    if description:
        content = g._front_matter_set(content, "description", description)
    if source:
        source_url = str(source.get("link") or "").strip()
        parsed = urllib.parse.urlparse(source_url)
        if (parsed.scheme in {"http", "https"} and parsed.netloc
                and source.get("source") and source.get("publisher_domain")):
            content = g._front_matter_set(content, "source_name", source.get("source") or "원문")
            content = g._front_matter_set(content, "source_url", source_url)
            content = g._front_matter_set(content, "source_domain", source["publisher_domain"])
            body_match = re.match(r"\A---\s*\n.*?\n---\s*\n(.*)\Z", content, re.S)
            body = body_match.group(1) if body_match else content
            if source_url not in body:
                heading = "\n\n## 출처\n" if g._content_lang(content, body) == "ko" else "\n\n## Sources\n"
                content = content.rstrip() + f"{heading}- [{source['source']}: {source.get('title', '원문 기사')}]({source_url})\n"
        content = g._append_source_notice(content, source)
    return content


WORDS_KO = "인공지능 반도체 기후 변화 정책 경제 사회 문화 환경 교육 일상 기술 연구 데이터 시장 산업 에너지 안전 건강".split()
WORDS_EN = "climate energy policy economy society culture science research market industry data safety health education".split()
SOURCES = (SOURCE, {"title": "T", "source": "EC", "link": "https://commission.europa.eu/x_en", "publisher_domain": "commission.europa.eu",
                    "notice": {"ko": "고지문입니다.", "en": "Notice."}}, {"title": "도메인 없음", "source": "X", "link": LINK},
           {"title": "ftp", "source": "X", "link": "ftp://x/y", "publisher_domain": "x"}, None)


def random_title(rng, ko):
    words = rng.sample(WORDS_KO if ko else WORDS_EN, rng.randint(2, 6))
    text = " ".join(words)
    extra = rng.random()
    if extra < 0.12:
        text += ': "' + words[0] + '" ' + words[1]
    elif extra < 0.20:
        text += " \\ 역슬래시"
    elif extra < 0.26:
        text += " 'single'"
    elif extra < 0.30:
        text += " — 대시 # 샵"
    return text


def random_body(rng, ko):
    unit = "이 글은 임의로 만든 시험용 본문입니다. " if ko else "This is a randomly generated test body for the comparison. "
    paragraphs = [unit * 4 for _ in range(20 if ko else 18)]
    paragraphs.insert(rng.randint(1, 3), f"근거는 [원문]({LINK})에 있습니다." if ko else f"See [source]({LINK}).")
    first = rng.choice([None, None, None, "## 소제목", "Note: 주의", "    들여쓴 첫 줄", "- 목록으로 시작", "> 인용으로 시작", "* * *"])
    if first:
        paragraphs.insert(0, first)
    text = "\n\n".join(paragraphs)
    if rng.random() < 0.15:
        text += "\n\n## 출처\n- [NASA](" + LINK + ")"
    return text + rng.choice(["", "\n", "\n\n", "  \n"])


def random_header_lines(rng, title, category, tags, ko):
    json_text = lambda value: json.dumps(value, ensure_ascii=False)      # noqa: E731
    parts = [rng.choice(["layout: post", "layout: post", "layout: post", "layout: default", 'layout: "post"', None, None])]
    roll = rng.random()
    parts.append("title: " + json_text(title) if roll < 0.55 else 'title: "' + title + '"' if roll < 0.65 else "title: '" + title.replace("'", "''") + "'" if roll < 0.72
                 else "title: " + title if roll < 0.78 else "title: " + json_text(title) + " # 주석" if roll < 0.82 else 'title: ""' if roll < 0.85
                 else None if roll < 0.88 else "title: " + json_text(title))
    roll = rng.random()
    parts.append("category: " + json_text(category) if roll < 0.6 else "category: " + category if roll < 0.7 else "category: '" + category + "'" if roll < 0.75
                 else None if roll < 0.85 else "category: " + json_text(category))
    roll = rng.random()
    parts.append("tags: " + json_text(tags) if roll < 0.3 else "tags: [" + ", ".join(tags) + "]" if roll < 0.42 else "tags: [" + ", ".join("'" + t + "'" for t in tags) + "]" if roll < 0.5
                 else "tags:\n" + "\n".join("  - " + t for t in tags) if roll < 0.62 else "tags:\n" + "\n".join("- " + t for t in tags) if roll < 0.68
                 else "tags:" if roll < 0.72 else "tags: []" if roll < 0.76 else "tags: [" + ", ".join(tags) + "   " if roll < 0.8 else None if roll < 0.9 else "tags: " + json_text(tags))
    parts.append(rng.choice(["lang: ko" if ko else "lang: en", "lang: en" if ko else "lang: ko", None, 'lang: "ko"' if ko else 'lang: "en"', "lang:"]))
    parts.append(rng.choice(['image: "https://images.unsplash.com/photo-9?w=1"', "image: https://images.unsplash.com/photo-8?w=1", None, "image:", "image: 'x'"]))
    for key, values in (("description", [json_text("설명 한 줄"), "plain 설명", '"unterminated']), ("date", ["2026-10-20 08:20:00 +0900"]), ("published", ["true", "false"]),
                        ("permalink", ["/posts/x/"]), ("source_name", [json_text("NASA"), "NASA"]), ("source_url", [json_text(LINK), LINK]),
                        ("custom_key", ["값", "a: b", "[x"]), ("layout", ["post"]), ("title", [json_text("중복 제목")])):
        if rng.random() < 0.12:
            parts.append(f"{key}: {rng.choice(values)}")
    parts = [part for part in parts if part is not None]
    rng.shuffle(parts)
    if rng.random() < 0.5:
        order = {"layout": 0, "title": 1, "category": 2, "tags": 3, "lang": 4, "image": 5}
        parts.sort(key=lambda s: order.get(s.split(":", 1)[0], 9))
    if rng.random() < 0.06:
        parts.insert(rng.randint(0, len(parts)), "")
    return "\n".join(parts).split("\n")


def random_content(rng, ko):
    title, category = random_title(rng, ko), rng.choice(["과학·환경", "기술·미래", "Society & Policy", "Technology & Future", "x: y"])
    tags = rng.sample(WORDS_KO if ko else WORDS_EN, rng.randint(0, 4))
    body, header = random_body(rng, ko), random_header_lines(rng, title, category, tags, ko)
    shape = rng.random()
    opener, closer, between = "---", "---", "\n\n"
    if 0.62 <= shape < 0.66:
        opener = "--- "
    elif shape < 0.68:
        opener = "---\t"
    elif shape < 0.72:
        closer = "---  "
    elif shape < 0.74:
        opener = "------"
    elif shape < 0.76:
        opener = "----"
    elif shape < 0.78:
        closer = "----"
    elif shape < 0.80:
        between = "\n\n---\n\n"
    elif shape < 0.82:
        between = "\n---\n"
    elif shape < 0.84:
        closer = None
    elif shape < 0.86:
        header = []
    elif shape < 0.88:
        between = "\n"
    if 0.90 <= shape < 0.93:
        content = body
    elif 0.93 <= shape < 0.95:
        content = "---\n---\n" + "\n".join(header) + "\n---" + between + body
    elif 0.95 <= shape < 0.97:
        content = "---\n" + "\n".join(header) + "\n---\n\n---\n" + "\n".join(header[:3]) + "\n---" + between + body
    elif 0.97 <= shape < 0.99:
        content = "---\n\n" + body
    else:
        content = opener + "\n" + "\n".join(header) + ("\n" + closer if closer is not None else "") + between + body
    pre = rng.random()
    if pre < 0.04:
        content = "\n\n  " + content
    elif pre < 0.06:
        content = "\ufeff" + content
    elif pre < 0.08:
        content = content.replace("\n", "\r\n")
    return content, title, category, tags


def random_data(rng):
    kc, kt, kcat, ktags = random_content(rng, True)
    ec, et, ecat, etags = random_content(rng, False)
    return {"kr_category": kcat, "kr_title": kt, "kr_tags": ktags, "kr_content": kc,
            "en_category": ecat, "en_title": et, "en_tags": etags, "en_content": ec, "image_queries": ["a"]}


def run_module(validate_fn, metadata_fn, data, source, link=LINK):
    """(검증만 한 글, 최종 글) 또는 (None, None, 거절 문구)."""
    try:
        out = validate_fn(copy.deepcopy(data), KR_IMAGE, EN_IMAGE, verified_source_url=link)
    except ValueError as exc:
        return None, None, str(exc)
    final = {k: metadata_fn(out[f"{k}_content"], dict(source) if source else None) for k in ("kr", "en")}
    return {k: out[f"{k}_content"] for k in ("kr", "en")}, final, None


class LegacyIdentityTest(unittest.TestCase):
    """좋은 입력의 출력은 옛 함수와 바이트 단위로 같다. '좋은 입력' = (a) 모델 머리말이 엄격 검사를 통과하고 옛 출력이 정상인 입력 (b) 맨 앞이 울타리가 아니라 머리말이
    없는 입력. 그 밖의 입력(머리말이 믿을 수 없는 모양)은 옛 출력이 우연히 정상이었어도 새 출력이 달라질 수 있으니 새 출력이 정상인지만 본다.
    비교 대상(legacy_*)은 이 변경 전의 기준 사본이다. 머리말을 만드는 방식을 일부러 바꾸는 뒤의 변경이면 이 비교를 그때의 기준으로 다시 맞춘다."""

    def test_random_model_responses_follow_the_identity_rules(self):
        rng = random.Random(20261028)
        counts = {"identical_strict": 0, "identical_headerless": 0, "repaired": 0, "expected_reject": 0, "old_accidentally_good": 0}
        for index in range(1500):
            data, source = random_data(rng), rng.choice(SOURCES)
            old_val, old_fin, old_err = run_module(legacy_validate_post_data, legacy_add_discovery_metadata, data, source)
            new_val, new_fin, new_err = run_module(g.validate_post_data, g.add_discovery_metadata, data, source)
            for key in ("kr", "en"):      # add_discovery_metadata 는 같은 입력에서 옛·새가 같다
                probe = data[f"{key}_content"]
                self.assertEqual(g.add_discovery_metadata(probe, dict(source) if source else None),
                                 legacy_add_discovery_metadata(probe, dict(source) if source else None), (index, key))
            if old_err is not None:
                continue            # 본문 검증 탈락은 머리말과 무관하다 — 새 함수는 새 출력이 따로 있을 수 있다
            self.assertIsNone(new_err, (index, new_err))        # 옛 함수가 받던 입력을 새 함수가 머리말 때문에 거절하지 않는다
            for key in ("kr", "en"):
                content = data[f"{key}_content"]
                kind, header, _ = g._split_model_content(content)
                strict = kind == "clean" and not g._model_header_problems(header)
                old_ok = not g.front_matter_problems(old_val[key])
                new_problems = g.front_matter_problems(new_val[key])
                fence_start = re.match(r"-{3,}", content.lstrip("\ufeff").lstrip()) is not None
                if fence_start and new_problems and all("본문이 머리말 줄" in p for p in new_problems):
                    counts["expected_reject"] += 1       # 닫히지 않았거나 머리말 아닌 줄이 섞인 머리말: 최종 검사가 후보를 거절한다(본문을 지우지 않는다)
                    continue
                if strict and old_ok:
                    self.assertEqual((new_val[key], new_fin[key]), (old_val[key], old_fin[key]), (index, key, content[:160]))
                    counts["identical_strict"] += 1
                elif not fence_start and not content.lstrip("\ufeff").lstrip().startswith("---"):
                    self.assertEqual((new_val[key], new_fin[key]), (old_val[key], old_fin[key]), (index, key, content[:160]))
                    counts["identical_headerless"] += 1
                else:
                    self.assertEqual(new_problems, [], (index, key, content[:200]))      # 어느 쪽이든 새 출력의 머리말은 정상이다
                    counts["old_accidentally_good" if old_ok else "repaired"] += 1
        # 시험이 속 빈 강정이 되지 않게: 각 갈래가 실제로 여러 번 돌았다
        self.assertGreater(counts["identical_strict"], 400, counts)
        self.assertGreater(counts["identical_headerless"], 40, counts)
        self.assertGreater(counts["repaired"], 800, counts)
        self.assertGreater(counts["old_accidentally_good"], 100, counts)
        self.assertGreater(counts["expected_reject"], 20, counts)

    def test_every_real_post_fed_back_as_a_model_response_is_identical_when_the_old_output_was_good(self):
        compared = 0
        for path in sorted((ROOT / "_posts").rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            front = yaml.safe_load(text.split("\n---\n", 1)[0][4:]) if text.startswith("---\n") else None
            if not isinstance(front, dict) or not front.get("title"):
                continue
            ko = front.get("lang") == "ko"
            link = front.get("source_url") or (re.search(r"https?://[^\s)\]>\"']+", text.split("\n---\n", 1)[-1]) or [LINK])[0]
            stub = '---\nlayout: post\ntitle: "t"\n---\n\n'
            data = {"kr_category": str(front.get("category") or "분야"), "kr_title": str(front["title"]), "kr_tags": ["a"],
                    "kr_content": text if ko else stub + "가" * 1300 + "\n\n" + link,
                    "en_category": str(front.get("category") or "분야"), "en_title": str(front["title"]), "en_tags": ["a"],
                    "en_content": text if not ko else stub + "a" * 1700 + "\n\n" + link, "image_queries": ["a"]}
            item = {"title": "t", "source": "S", "link": link, "publisher_domain": "d.example"}
            old_val, old_fin, old_err = run_module(legacy_validate_post_data, legacy_add_discovery_metadata, data, item, link)
            new_val, new_fin, new_err = run_module(g.validate_post_data, g.add_discovery_metadata, data, item, link)
            self.assertEqual(old_err is None, new_err is None, (path.name, old_err, new_err))
            if old_err is not None:
                continue            # 옛 손글 중에는 본문 검증(분량·원문 링크)을 못 넘는 글이 있다
            key = "kr" if ko else "en"
            self.assertEqual(g.front_matter_problems(old_val[key]), [], path.name)        # 저장소의 글은 모두 정상이므로 옛 출력도 정상이다
            self.assertEqual((new_val, new_fin), (old_val, old_fin), path.name)
            compared += 1
        self.assertGreater(compared, 15)        # 읽을 수 있는 글이 실제로 비교됐다


class FinalCheckOnOldOutputsTest(unittest.TestCase):
    """깨진 응답에 대한 옛 출력은 최종 검사가 잡고 새 출력은 정상이다 — 이 시험이 최종 검사의 힘을 증명한다(수정 전 코드로 같은 입력을 돌린 결과)."""

    def test_the_old_function_wrote_the_broken_headers_and_the_final_check_flags_them(self):
        old = legacy_validate_post_data(make_data(QUOTED_TITLE_RESPONSE, DOUBLE_FENCE_EN_RESPONSE, kr_title=QUOTED_TITLE, en_title=DOUBLE_FENCE_EN_TITLE),
                                        KR_IMAGE, EN_IMAGE, LINK)
        kr_problems, en_problems = g.front_matter_problems(old["kr_content"]), g.front_matter_problems(old["en_content"])
        self.assertTrue(any("`title` 값이 한 줄 JSON 문자열" in p for p in kr_problems), kr_problems)
        self.assertEqual(en_problems[:1], ["첫 줄이 정확히 `---` 가 아님"])
        new = validate(make_data(QUOTED_TITLE_RESPONSE, DOUBLE_FENCE_EN_RESPONSE, kr_title=QUOTED_TITLE, en_title=DOUBLE_FENCE_EN_TITLE))
        self.assertEqual((g.front_matter_problems(new["kr_content"]), g.front_matter_problems(new["en_content"])), ([], []))

    def test_the_old_function_also_produced_a_header_without_a_title_for_an_empty_one(self):
        old = legacy_validate_post_data(make_data("---\n---\n\n" + KR_BODY, EN_BODY), KR_IMAGE, EN_IMAGE, LINK)
        self.assertIn("필수 키 `title` 줄이 없음", g.front_matter_problems(old["kr_content"]))


if __name__ == "__main__":
    unittest.main()
