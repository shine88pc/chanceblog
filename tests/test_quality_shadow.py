"""그림자 모드(품질 측정) `pipeline/quality_shadow.py` 의 정의를 못박는 시험 — 9항목의 예문·경계값·'측정 불가는 null + 이유'·결정성.

네트워크·실제 시크릿을 쓰지 않는다. 연결 금지·네트워크 0·쓰기 범위·문서/표 대조·실제 글 스모크는 test_quality_shadow_guards.py 에 있다.
문서: docs/QUALITY_SHADOW.md (정의·한계·임계값). 이 시험의 예문은 모두 합성한 것이다(실제 글을 옮기지 않는다).
"""
import datetime
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from pipeline import quality_shadow as q

AS_OF = datetime.date(2026, 11, 9)


def make_text(body, **front):
    fields = {"layout": "post", "title": "테스트 글", "lang": "ko"}
    fields.update(front)
    lines = [f'{key}: "{value}"' for key, value in fields.items() if value is not None]
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body


def make_post(body, name="2026-11-01-KR-123456.md", **front):
    return q.parse_post(make_text(body, **front), name)


def analyze(body, name="2026-11-01-KR-123456.md", source_text=None, as_of=AS_OF, **front):
    return q.analyze_post(make_post(body, name, **front), as_of, source_text)


KO_SOURCE_URL = "https://www.ftc.gov/news-events/news/press-releases/2026/11/x"
KO_BODY = f"""FTC는 2026년 11월 6일 합의금 4,975만 달러를 발표했다. [FTC 보도자료]({KO_SOURCE_URL})에 따르면 이는 역대 최대 규모이다.

### 소제목에 숫자 100이 있어도 세지 않는다

- **허위 광고:** 초기 임대료를 낮게 표시했다는 주장이다.

일반적으로 시장은 변한다. 소비자는 어떻게 비교할까?

---
### 출처
- [FTC 보도자료]({KO_SOURCE_URL})

![Thumbnail](https://images.unsplash.com/photo-1?auto=format)
*Photo by [Name](https://unsplash.com/@n?utm_source=app) on [Unsplash](https://unsplash.com/?utm_source=app)*

"합의 보도자료." Source: Agency, www.ftc.gov, November 6, 2026 <{KO_SOURCE_URL}>

*이 글은 AI 도구가 작성했습니다. 1234명이 읽었다.*
"""


# ----------------------------------------------------------------------------
# 입력 읽기·영역 나누기
# ----------------------------------------------------------------------------
class ParsingTest(unittest.TestCase):
    def test_front_matter_is_read_and_quotes_are_removed(self):
        post = make_post("본문입니다.", source_url=KO_SOURCE_URL, published="false")
        self.assertEqual(post.title, "테스트 글")
        self.assertEqual(post.source_url, KO_SOURCE_URL)
        self.assertFalse(post.published)
        self.assertEqual((post.date, post.kind, post.pair_key, post.lang), ("2026-11-01", "KR", "123456", "ko"))

    def test_a_file_without_front_matter_is_not_a_post(self):
        with self.assertRaises(q.PostReadError):
            q.parse_post("그냥 글", "x.md")

    def test_crlf_and_bom_give_the_same_result_as_lf(self):
        lf = make_text(KO_BODY)
        crlf = chr(0xFEFF) + lf.replace("\n", "\r\n")
        a = q.analyze_post(q.parse_post(lf, "2026-11-01-KR-123456.md"), AS_OF)
        b = q.analyze_post(q.parse_post(crlf, "2026-11-01-KR-123456.md"), AS_OF)
        self.assertEqual(a, b)

    def test_pair_key_is_the_last_six_digits_of_the_file_name_and_single_files_have_none(self):
        self.assertEqual(make_post("x", "2026-10-18-EN-233513.md").pair_key, "233513")
        single = make_post("x", "2026-10-18-AI.md")
        self.assertEqual((single.kind, single.pair_key), ("AI", ""))

    def test_language_falls_back_to_the_script_when_the_header_has_none(self):
        text = "---\ntitle: x\n---\n\nThis is an English paragraph about energy policy."
        self.assertEqual(q.parse_post(text, "free.md").lang, "en")
        text = "---\ntitle: x\n---\n\n이것은 한국어 문단이다. 에너지 정책을 다룬다."
        self.assertEqual(q.parse_post(text, "free.md").lang, "ko")


class ZonesTest(unittest.TestCase):
    HEADINGS = ("## 출처", "### 출처", "#### 출처", "**출처**", "## Sources", "### Sources", "## Source", "### Source", "**Source**", "**Sources**",
                "**Sources and Reference**", "**출처 및 참고자료**", "### 참고 자료", "## 참고자료", "### References", "**Sources:**")

    def test_every_known_shape_of_a_sources_heading_is_recognized(self):
        for heading in self.HEADINGS:
            with self.subTest(heading=heading):
                zones = q.split_zones(f"본문 문단.\n\n{heading}\n- [A](https://a.example.org/x)\n- 둘째 항목\n")
                self.assertTrue(zones.sources_heading, heading)
                self.assertEqual(len(zones.sources_items), 2)
                self.assertEqual(zones.main, ["본문 문단."])

    def test_an_image_credit_heading_is_not_a_sources_heading(self):
        for heading in ("## 이미지 출처", "### Image credits", "**사진 출처**"):
            self.assertFalse(q.is_sources_heading(heading), heading)
        zones = q.split_zones("본문.\n\n## 이미지 출처\n- Photo by Someone on Unsplash\n")
        self.assertEqual(zones.sources_heading, "")
        self.assertEqual(zones.sources_items, [])
        self.assertEqual(zones.main, ["본문."])

    def test_the_rule_before_the_sources_heading_is_not_body(self):
        zones = q.split_zones("본문.\n\n---\n**출처**\n- 항목\n")
        self.assertEqual(zones.main, ["본문."])

    def test_tail_lines_are_separated_from_the_body(self):
        zones = q.split_zones(KO_BODY)
        joined = "\n".join(zones.main)
        for leaked in ("출처", "Photo by", "Source:", "AI 도구", "1234", "unsplash"):
            self.assertNotIn(leaked, joined, leaked)
        self.assertEqual((zones.image_lines, len(zones.credit_lines), len(zones.citation_lines), len(zones.notice_lines)), (1, 1, 1, 1))
        self.assertEqual(len(zones.sources_items), 1)

    def test_a_new_heading_after_the_sources_section_returns_to_the_body(self):
        zones = q.split_zones("본문.\n\n## Sources\n- [A](https://a.example.org/x)\n\n## 덧붙임\n덧붙임 문단.\n")
        self.assertEqual(len(zones.sources_items), 1)
        self.assertIn("덧붙임 문단.", zones.main)

    def test_very_long_lines_are_cut_and_counted(self):
        zones = q.split_zones("가" * (q.MAX_LINE_CHARS + 500))
        self.assertEqual(zones.truncated_lines, 1)
        self.assertEqual(len(zones.main[0]), q.MAX_LINE_CHARS)

    def test_no_sources_heading_means_no_sources_section(self):
        zones = q.split_zones("본문 한 줄.\n\n또 한 줄.")
        self.assertEqual((zones.sources_heading, zones.sources_items), ("", []))


# ----------------------------------------------------------------------------
# 링크·도메인
# ----------------------------------------------------------------------------
class LinksAndDomainsTest(unittest.TestCase):
    def test_links_are_marked_and_images_are_dropped(self):
        text, urls = q.replace_links("[가](https://a.example.org/x) 와 <https://b.example.org/y> 와 https://c.example.org/z. ![img](https://u.example.org/i.png)")
        self.assertEqual(urls, ["https://a.example.org/x", "https://b.example.org/y", "https://c.example.org/z"])
        self.assertNotIn("u.example.org", text)

    def test_host_registrable_domain_and_normalization(self):
        cases = {"https://www150.statcan.gc.ca/n1/x": ("www150.statcan.gc.ca", "statcan.gc.ca"),
                 "https://science.nasa.gov/x": ("science.nasa.gov", "nasa.gov"),
                 "https://www.gov.uk/government/news/x": ("gov.uk", "gov.uk"),
                 "https://www.mfds.go.kr/brd/x": ("mfds.go.kr", "mfds.go.kr"),
                 "https://cinea.ec.europa.eu/news": ("cinea.ec.europa.eu", "europa.eu")}
        for url, (host, domain) in cases.items():
            with self.subTest(url=url):
                self.assertEqual(q.host_of(url), host)
                self.assertEqual(q.registrable_domain(host), domain)
        self.assertEqual(q.normalize_url("HTTPS://Example.org/a/?utm_source=x&k=1#frag"), "https://example.org/a?k=1")

    def test_classification_examples_from_the_operator_standard(self):
        expected = {"nasa.gov": "public_agency", "europa.eu": "public_agency", "statcan.gc.ca": "public_agency", "ftc.gov": "public_agency",
                    "federalreserve.gov": "public_agency", "nsf.gov": "public_agency", "gov.uk": "public_agency", "pewresearch.org": "research",
                    "openai.com": "company", "onepredict.ai": "company", "apnews.com": "news_media", "spectrum.ieee.org": "news_media",
                    "ieee.org": "research", "nst.re.kr": "public_agency", "kimm.re.kr": "research", "unsplash.com": "other",
                    "something.example.com": "unknown", "agency.gov": "public_agency", "dept.state.edu": "research", "agency.int": "public_agency"}
        for host, category in expected.items():
            with self.subTest(host=host):
                self.assertEqual(q.classify_host(host)[0], category)
                self.assertEqual(q.classify_host("sub." + host)[0], category)

    def test_the_most_specific_rule_wins_and_unknown_is_never_guessed_as_company(self):
        self.assertEqual(q.classify_host("spectrum.ieee.org")[2], "spectrum.ieee.org")
        self.assertEqual(q.classify_host("news.some-startup.com")[0], "unknown")
        self.assertEqual(q.classify_host("")[0], "unknown")

    def test_every_rule_classifies_its_own_suffix(self):
        for suffix, category, _ in q.DOMAIN_RULES:
            with self.subTest(suffix=suffix):
                self.assertEqual(q.classify_host(suffix)[0], category)
        self.assertEqual(len({suffix for suffix, _, _ in q.DOMAIN_RULES}), len(q.DOMAIN_RULES), "같은 도메인이 표에 두 번 있다")

    def test_press_format_tokens_strong_and_weak(self):
        self.assertEqual(q.press_format_signals(KO_SOURCE_URL), (["press", "releases"], ["news"]))
        self.assertEqual(q.press_format_signals("https://science.nasa.gov/missions/hubble/x"), ([], []))
        self.assertEqual(q.press_format_signals("https://example.com/%EB%B3%B4%EB%8F%84%EC%9E%90%EB%A3%8C/1")[0], ["보도자료"])   # 퍼센트 인코딩된 한글 경로도 읽는다
        self.assertEqual(q.press_format_signals("https://example.com/" + "보도자료" + "/1")[0], ["보도자료"])
        self.assertEqual(q.press_format_signals(""), ([], []))

    def test_license_links_are_recognized(self):
        self.assertTrue(q.is_license_url("https://creativecommons.org/licenses/by/4.0/"))
        self.assertTrue(q.is_license_url("https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"))
        self.assertFalse(q.is_license_url("https://www.nationalarchives.gov.uk/about/"))
        self.assertFalse(q.is_license_url(KO_SOURCE_URL))

    # --- 독립 검증 P2: `[`·`]` 가 든 깨진 주소가 urlsplit 의 ValueError 로 전체 실행을 죽이지 않는다 ---
    MALFORMED_URLS = ("http://[abc/x", "http://[abc", "https://[::1/x", "http://]x/", "http://[/", "http://a[b]c/x", "https://[fe80::1%25eth0/x", "http://[")

    def test_every_url_helper_survives_a_malformed_address(self):
        for url in self.MALFORMED_URLS:
            with self.subTest(url=url):
                self.assertFalse(q.is_license_url(url))
                self.assertIsInstance(q.host_of(url), str)
                self.assertIsInstance(q.normalize_url(url), str)
                self.assertIsInstance(q.press_format_signals(url), tuple)
                self.assertIn(q.classify_host(q.host_of(url))[0], q.CATEGORIES)

    def test_a_post_with_a_malformed_address_anywhere_is_still_analyzed_and_the_link_is_still_counted_as_a_link(self):
        bodies = {"markdown link": "[자료](http://[abc/x)에 따르면 2026년 계획이 있다고 한다.",
                  "autolink": "자세한 내용은 <http://[abc> 에 있고 2026년 계획을 밝혔다.",
                  "bare address": "자세한 내용은 http://[abc/x 에 있다고 2026년에 발표했다.",
                  "image link": "![그림](http://[abc/x.png) 아래 2026년 계획을 밝혔다고 한다.",
                  "reference list": "본문 2026년 계획을 밝혔다.\n\n## 출처\n- [자료](http://[abc/x)\n- [다른 자료](https://www.nasa.gov/a)\n"}
        for name, body in bodies.items():
            with self.subTest(body=name):
                result = analyze(body)
                self.assertIn("sources", result)
                self.assertEqual(result["topic_fit"]["fit"] is None or result["topic_fit"]["fit"] in ("core", "borderline", "off"), True)
        self.assertEqual(analyze(bodies["markdown link"])["sources"]["body_links"], 1)
        self.assertEqual(analyze(bodies["autolink"])["sources"]["body_links"], 1)
        self.assertEqual(analyze(bodies["reference list"])["sources"]["domains"], ["nasa.gov"])        # 깨진 주소는 도메인으로 세지 않는다

    def test_a_malformed_front_matter_source_url_does_not_stop_the_measurement(self):
        for url in self.MALFORMED_URLS:
            with self.subTest(url=url):
                result = analyze("NASA는 2026년 10월 1일 발표했다고 한다.", source_url=url)
                self.assertEqual(result["grounding"]["mode"], "inline_link_approx")
                self.assertIn(result["press_release_summary"]["flag"], (True, False, None))


# ----------------------------------------------------------------------------
# 숫자·날짜·고유명사·문장
# ----------------------------------------------------------------------------
class AnchorsTest(unittest.TestCase):
    def numbers(self, text):
        return [(token.kind, token.value) for token in q.find_numbers(text)]

    def test_korean_and_english_scales_give_the_same_value(self):
        self.assertEqual(self.numbers("4,975만 달러"), [("money", 49750000.0)])
        self.assertEqual(self.numbers("$49.75 million"), [("money", 49750000.0)])
        self.assertEqual(q.numeric_key(49750000.0), q.numeric_key(49.75 * 10 ** 6))
        self.assertEqual(self.numbers("1.2 trillion won"), [("money", 1.2e12)])
        self.assertEqual(self.numbers("약 4조 2천억 원"), [("money", 4.2e12)])        # 4조 + 2천억 을 합친다
        self.assertEqual(self.numbers("28.8억 유로"), [("money", 2.88e9)])

    def test_percent_year_and_plain_numbers(self):
        self.assertEqual(self.numbers("71%에서 69%로"), [("percent", 71.0), ("percent", 69.0)])
        self.assertEqual(self.numbers("rose 2.4 percent in 2025"), [("percent", 2.4), ("year", 2025.0)])
        self.assertEqual(self.numbers("1,790명이 사망"), [("number", 1790.0)])

    def test_absurdly_long_digit_runs_are_not_numbers_and_never_crash(self):
        self.assertEqual(self.numbers("1" * 400), [])
        self.assertEqual(self.numbers("값은 " + "9" * 40 + "원이다"), [])
        self.assertEqual(self.numbers("pi is 3.14159265358979323846264"), [])      # 소수점 아래가 너무 길면 읽지 않는다(정수 부분 3 만 읽어 틀린 값을 내지 않는다 — 독립 검증 P5)
        self.assertEqual(q.numeric_key(float("inf")), "inf")
        self.assertEqual(analyze("합계 " + "7" * 500 + " 라고 2026년에 밝혔다.")["claims"]["total"], 1)

    def test_identifiers_and_article_numbers_are_not_numbers(self):
        for text in ("G1에서 G5까지", "COP31 회의", "5G 네트워크", "제10조에 따라"):
            with self.subTest(text=text):
                self.assertEqual(self.numbers(text), [], text)

    # --- 독립 검증 P5: 영문 단위가 붙은 수·규모 약어·한글에 붙은 수 ---
    def test_a_decimal_with_an_attached_english_unit_keeps_its_whole_value(self):
        """옛 정규식은 3.5GHz 를 3, 12.5km 를 12, 1.8m 를 1, 12,246kg 를 12 로 읽었다(소수·천 단위가 정수 앞부분으로 되돌아가 틀린 값)."""
        cases = {"3.5GHz": 3.5, "12.5km": 12.5, "1.8m": 1.8, "0.75mm": 0.75, "2.5GW": 2.5, "2.4GHz": 2.4, "4.5kWh": 4.5, "12,246kg": 12246.0, "4,261km": 4261.0}
        for text, value in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.numbers(text), [("number", value)])
                self.assertEqual(self.numbers(f"칩은 {text} 로 동작한다"), [("number", value)])

    def test_attached_english_units_without_a_decimal_are_numbers_with_the_typed_value(self):
        cases = {"5km": 5.0, "30kg": 30.0, "100MW": 100.0, "7GW": 7.0, "155mm": 155.0, "300W": 300.0, "10GB": 10.0, "3nm": 3.0, "60fps": 60.0, "15KM": 15.0, "5ms": 5.0}
        for text, value in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.numbers(text), [("number", value)])
        self.assertEqual(self.numbers("약 45km 와 약 480km"), [("number", 45.0), ("number", 480.0)])

    def test_scale_abbreviations_after_a_currency_symbol_are_values_and_bn_works_everywhere(self):
        cases = {"$5M": 5e6, "€3M": 3e6, "$2.5B": 2.5e9, "$300K": 3e5, "$5m": 5e6, "£1.2B": 1.2e9, "₩5B": 5e9}
        for text, value in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.numbers(text), [("money", value)])
        self.assertEqual(self.numbers("3.2bn 와 5bn"), [("number", 3.2e9), ("number", 5e9)])
        self.assertEqual(self.numbers("$1.2 billion"), [("money", 1.2e9)])
        self.assertEqual(q.numeric_key(q.find_numbers("$2.5B")[0].value), q.numeric_key(q.find_numbers("$2.5 billion")[0].value))        # 표기가 달라도 같은 값

    def test_ambiguous_letters_after_a_number_stay_out_and_a_cut_decimal_is_never_returned(self):
        for text in ("3M Company", "4K 영상", "401K plan", "5G 네트워크", "21st century", "3x", "2020s", "5W1H", "7B parameters", "3.5xyz", "2.5abc", "버전 3.5.2",
                     "G1에서 G5까지", "COP31 회의", "1,000x", "12,246xyz", "3,500th", "10,000s", "1,000.5x"):
            with self.subTest(text=text):
                self.assertEqual(self.numbers(text), [], text)               # 정수 부분(3)이나 천 단위 앞 묶음(1·12)만 잘라 내는 일도 없다

    def test_thousands_groups_stay_one_number_while_comma_separated_lists_are_read_apart(self):
        """천 단위 쉼표 묶음은 한 수(쉼표 뒤 정확히 세 자리가 끝날 때)이고, 쉼표로 이은 연도·번호 목록은 따로 읽는다."""
        self.assertEqual(self.numbers("12,246kg"), [("number", 12246.0)])
        self.assertEqual(self.numbers("1,234,567명"), [("number", 1234567.0)])
        self.assertEqual(self.numbers("$1,200K"), [("money", 1200000.0)])
        self.assertEqual(self.numbers("1,000,000달러"), [("money", 1000000.0)])
        self.assertEqual(self.numbers("2026,2027"), [("year", 2026.0), ("year", 2027.0)])
        self.assertEqual(self.numbers("1,2,3 순서"), [("number", 1.0), ("number", 2.0), ("number", 3.0)])
        self.assertEqual(self.numbers("약 1,200명"), [("number", 1200.0)])

    def test_numbers_glued_to_hangul_are_read_when_a_unit_or_counter_follows(self):
        cases = {"약5%": ("percent", 5.0), "총3명": ("number", 3.0), "연2회": ("number", 2.0), "월10만원": ("money", 100000.0), "전년대비12%": ("percent", 12.0),
                 "올해12월": ("number", 12.0), "약3억원": ("money", 3e8), "약5km": ("number", 5.0), "최근5년": ("number", 5.0)}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.numbers(text), [expected])
        for identifier in ("코로나19", "코로나19가 확산", "아이폰15", "제10조에 따라", "제3회 대회"):                 # 이름에 붙은 수·조문 번호는 식별자라 읽지 않는다
            with self.subTest(identifier=identifier):
                self.assertEqual(self.numbers(identifier), [], identifier)
        self.assertEqual(self.numbers("약 5%"), self.numbers("약5%"))                               # 띄어 쓴 것과 같은 값

    def test_glued_numbers_make_a_sentence_a_numeric_claim(self):
        claims = analyze("올해 사업은 약5%에서 총3명으로 늘었다고 밝혔다.")["claims"]
        self.assertEqual((claims["total"], claims["numeric"]), (1, 1))
        self.assertEqual(analyze("코로나19가 확산된 뒤에도 일상은 이어졌다고 말했다.")["claims"]["numeric"], 0)

    # --- 독립 검증 P12: 월 뒤의 개수·퍼센트는 날짜가 아니고, 연도 없는 기간은 끝 날짜의 해를 먼저 정한다 ---
    def test_a_number_after_a_month_with_a_counting_word_is_not_a_date_and_stays_a_number(self):
        ref = datetime.date(2026, 10, 30)
        for text in ("3월 20개 사업", "5월 15명 참석", "6월 30% 증가", "9월 10건 접수", "1월 31% 42% 27%", "3월 20 개", "3월 20만 명", "11월 3-5명 참석"):
            with self.subTest(text=text):
                self.assertEqual(q.find_dates(text, ref), [], text)
        self.assertEqual([token.value for token in q.find_numbers("3월 20개 사업")], [3.0, 20.0])          # 개수는 숫자에서 빠지지 않는다
        self.assertEqual([(t.kind, t.value) for t in q.find_numbers("1월 31% 42% 27%")], [("number", 1.0), ("percent", 31.0), ("percent", 42.0), ("percent", 27.0)])
        for text, expected in (("3월 20일 사업", (3, 20)), ("5월 15일에 참석", (5, 15)), ("9월 10일 접수", (9, 10)), ("11월 3" + chr(126) + "5일 개최", (11, 3))):
            with self.subTest(real=text):
                found = q.find_dates(text, ref)[0].start
                self.assertEqual((found.month, found.day), expected)                    # 일(日)을 적은 진짜 날짜는 그대로 읽는다
        self.assertEqual(q.find_dates("8월 19 포획이 취소됐다", ref)[0].start.isoformat(), "2026-08-19")      # 일 표시도 단위 낱말도 없으면 예전처럼 날짜로 읽는다

    def test_a_past_period_without_a_year_takes_the_year_of_its_end_date(self):
        ref = datetime.date(2026, 10, 30)
        cases = {"분석 기간은 1월 1일–10월 24일이다": ("2026-01-01", "2026-10-24"), "1월 1일" + chr(126) + "10월 24일": ("2026-01-01", "2026-10-24"),
                 "7월 27일부터 10월 24일까지": ("2026-07-27", "2026-10-24"), "Jan 1 - Oct 24": ("2026-01-01", "2026-10-24"), "11월 3-5일": ("2026-11-03", "2026-11-05")}
        for text, (start, end) in cases.items():
            with self.subTest(text=text):
                found = q.find_dates(text, ref)
                self.assertEqual([(m.start.isoformat(), m.end.isoformat()) for m in found], [(start, end)])
        year_end = datetime.date(2026, 12, 30)                                          # 해를 넘기는 기간은 끝이 다음 해, 시작은 그 전해
        self.assertEqual([(m.start.isoformat(), m.end.isoformat()) for m in q.find_dates("12월 28일–1월 3일", year_end)], [("2026-12-28", "2027-01-03")])
        year_start = datetime.date(2026, 1, 10)
        self.assertEqual([(m.start.isoformat(), m.end.isoformat()) for m in q.find_dates("12월 28일–1월 3일", year_start)], [("2025-12-28", "2026-01-03")])
        explicit = q.find_dates("2026년 12월 28일부터 1월 3일까지", year_end)                    # 연도를 적었으면 그 해가 시작이다(예전 규칙 그대로)
        self.assertEqual([(m.start.isoformat(), m.end.isoformat()) for m in explicit], [("2026-12-28", "2027-01-03")])

    def test_the_period_and_percent_table_of_the_real_pew_post_shape_are_not_an_upcoming_event(self):
        """2026-10-30 KR-224001 모양: 표의 `1월 | 31%` 가 1월 31일로, 기간 `1월 1일–10월 24일` 이 2027년으로 읽혀 date_status 가 upcoming 이던 오류."""
        body = ("미국 정치 광고 가운데 데이터센터를 언급한 광고의 입장별 비율을 정리했습니다. 10월(24일까지)에는 57%가 반대하는 쪽이었고 찬성하는 쪽은 3%였습니다.\n\n"
                "아래는 월별 값입니다(2026년, 광고 건수 기준). 분석 대상은 1월 1일–10월 24일에 실린 광고 20,751건입니다. 1월에는 찬성 광고가 반대 광고보다 많았습니다.\n\n"
                "| 월 | 반대 | 찬성 | 나머지 |\n|---|---|---|---|\n| 1월 | 31% | 42% | 27% |\n| 9월 | 61% | 8% | 31% |\n\n"
                "7월 27일부터 10월 24일까지 90일 동안 광고에 쓰인 돈은 1,200만 달러에 조금 못 미칩니다.\n")
        result = analyze(body, "2026-10-30-KR-224001.md")["event_focus"]
        self.assertEqual(result["dates_after_as_of"], [])
        self.assertEqual(result["date_status"], "no_event_dates")
        self.assertNotEqual(result["date_status"], "upcoming")
        percent_claim = analyze(body, "2026-10-30-KR-224001.md")["claims"]["by_anchor"]
        self.assertGreaterEqual(percent_claim["percent"], 3)                               # 표의 31% 도 퍼센트 집계에 들어간다

    def test_source_text_mode_compares_attached_units_by_value_in_both_directions(self):
        body = "새 칩은 3.5GHz 로 동작한다고 밝혔다.\n"
        supported = analyze(body, source_text="The chip runs at 3.5 GHz.")["grounding"]
        self.assertEqual((supported["supported"], supported["unsupported"]), (1, 0))
        wrong = analyze(body, source_text="The chip runs at 3 GHz.")["grounding"]
        self.assertEqual((wrong["supported"], wrong["unsupported"]), (0, 1))                # 옛 코드는 3.5GHz 를 3 으로 읽어 이쪽이 지지로 통과했다
        spaced = analyze("새 칩은 3.5 GHz 로 동작한다고 밝혔다.\n", source_text="Clock speed: 3.5GHz.")["grounding"]
        self.assertEqual((spaced["supported"], spaced["unsupported"]), (1, 0))                 # 붙여 쓴 원문도 같은 값
        money = analyze("투자 규모는 $5M 이라고 밝혔다.\n", source_text="The investment is 5 million dollars.")["grounding"]
        self.assertEqual((money["supported"], money["unsupported"]), (1, 0))
        count = analyze("선정된 사업은 20개라고 밝혔다.\n", source_text="Twenty projects were chosen; 20 projects in March.")["grounding"]
        self.assertEqual((count["supported"], count["unsupported"]), (1, 0))                  # 개수 20 은 날짜 20일이 아니라 숫자 20 으로 맞는다

    def test_dates_in_both_languages_and_ranges(self):
        ref = datetime.date(2026, 11, 1)
        cases = {"2026년 11월 3일부터 5일까지": ("2026-11-03", "2026-11-05"), "11월 3" + chr(126) + "5일 개최": ("2026-11-03", "2026-11-05"),
                 "November 3 to November 5, 2026": ("2026-11-03", "2026-11-05"), "on 3 November 2026": ("2026-11-03", "2026-11-03"),
                 "2026-11-06 발표": ("2026-11-06", "2026-11-06"), "From Nov. 3-5 at the hall": ("2026-11-03", "2026-11-05")}
        for text, (start, end) in cases.items():
            with self.subTest(text=text):
                found = q.find_dates(text, ref)
                self.assertEqual([(m.start.isoformat(), m.end.isoformat()) for m in found], [(start, end)])

    def test_a_date_without_a_year_is_the_nearest_year_to_the_post_date(self):
        post_date = datetime.date(2026, 11, 2)
        self.assertEqual(q.find_dates("8월 19일 포획이 취소됐다", post_date)[0].start, datetime.date(2026, 8, 19))      # 지난 일
        self.assertEqual(q.find_dates("January 3 deadline", post_date)[0].start, datetime.date(2027, 1, 3))          # 곧 올 일
        self.assertEqual(q.find_dates("we may 5 times", post_date), [])                                              # 조동사 may

    def test_month_only_dates_have_month_precision_in_both_languages(self):
        mention = q.find_dates("2026년 11월 보고서", datetime.date(2026, 11, 1))[0]
        self.assertEqual((mention.precision, mention.start.day, mention.end.day), ("month", 1, 30))
        for text in ("in November 2026 the", "since Nov. 2026,"):
            found = q.find_dates(text, datetime.date(2026, 11, 1))
            self.assertEqual([(m.precision, m.start.isoformat(), m.end.isoformat()) for m in found], [("month", "2026-11-01", "2026-11-30")], text)
        full = q.find_dates("on November 3, 2026", datetime.date(2026, 11, 1))                     # 일이 있으면 일 단위가 이긴다
        self.assertEqual([(m.precision, m.start.isoformat()) for m in full], [("day", "2026-11-03")])
        self.assertEqual(q.find_dates("we may 2026 times", datetime.date(2026, 11, 1)), [])        # 조동사 may

    def test_entities_latin_and_korean(self):
        self.assertEqual(q.find_entities("According to the Federal Trade Commission, Progress Residential and Pretium Partners agreed."),
                         ["Federal Trade Commission", "Progress Residential", "Pretium Partners"])
        self.assertEqual(q.find_entities("Residents say the U.S. policy is changing."), ["U.S."])
        self.assertEqual(q.find_entities("NASA and ESA said AI will help."), ["NASA", "ESA"])             # 일반 약어 AI 는 뺀다
        self.assertEqual(q.find_entities("Residents say it changed."), [])                               # 문장 첫 낱말 하나만 대문자
        self.assertEqual(q.find_entities("캐나다 통계청은 온타리오와 앨버타 데이터를 발표했다."), ["캐나다", "온타리오", "앨버타"])
        self.assertIn("연방거래위원회", q.find_entities("연방거래위원회가 합의했다"))
        self.assertEqual(q.find_entities("이란 실제 도시의 도로"), [])                                    # 오탐이 잦은 '이란' 은 뺐다

    def test_sentence_splitting_keeps_abbreviations_and_decimals_together(self):
        self.assertEqual(q.split_sentences("The U.S. Federal Reserve cut rates by 0.25 percent. Markets rose. See No. 5."),
                         ["The U.S. Federal Reserve cut rates by 0.25 percent.", "Markets rose.", "See No. 5."])
        self.assertEqual(q.split_sentences("합의금은 4,975만 달러였다. 이는 최대 규모다! 정말일까? 그렇다."),
                         ["합의금은 4,975만 달러였다.", "이는 최대 규모다!", "정말일까?", "그렇다."])


# ----------------------------------------------------------------------------
# 항목 1 — 핵심 사실 주장 수
# ----------------------------------------------------------------------------
class ClaimsTest(unittest.TestCase):
    def test_counts_only_anchored_statements_outside_headings_quotes_questions_and_tails(self):
        claims = analyze(KO_BODY)["claims"]
        self.assertEqual((claims["total"], claims["numeric"], claims["entity_only"]), (2, 1, 1))
        self.assertEqual(claims["by_anchor"]["money"], 1)
        self.assertEqual(claims["by_anchor"]["date"], 1)

    def test_english_posts_are_measured_the_same_way(self):
        body = ("The Federal Trade Commission announced a $49.75 million settlement on November 6, 2026. Markets were calm. "
                "Is this the end?\n\n## Sources\n- [FTC](https://www.ftc.gov/x)\n")
        claims = analyze(body, "2026-11-08-EN-111111.md", lang="en")["claims"]
        self.assertEqual((claims["total"], claims["numeric"]), (1, 1))

    def test_digits_inside_urls_and_markup_are_not_numbers(self):
        body = "자세한 내용은 [여기](https://example.org/2026/11/dq261106b/12345)에 있다 한다."
        self.assertEqual(analyze(body)["claims"]["total"], 0)

    def test_table_rows_are_claims_and_the_header_row_is_not(self):
        body = "| 구분 | 값 |\n|---|---|\n| 2025년 실업률 | 4.1% |\n| 2026년 실업률 | 3.9% |\n"
        claims = analyze(body)["claims"]
        self.assertEqual((claims["total"], claims["numeric"]), (2, 2))
        self.assertEqual(analyze(body)["body"]["table_data_rows"], 2)

    def test_pure_quotations_and_blockquotes_are_not_counted(self):
        body = "> 인용 줄에 4,000명이 있다고 한다.\n\n\"그 합의금은 4,975만 달러였다.\"\n\n담당자는 \"합의금은 4,975만 달러\"라고 말했다.\n"
        self.assertEqual(analyze(body)["claims"]["total"], 1)

    def test_an_empty_body_has_zero_claims_and_a_null_ratio_with_a_reason(self):
        claims = analyze("")["claims"]
        self.assertEqual(claims["total"], 0)
        self.assertIsNone(claims["claim_ratio"])
        self.assertIn("claim_ratio", claims["null_reasons"])

    def test_detail_option_lists_the_claims(self):
        detail = q.analyze_post(make_post(KO_BODY), AS_OF, None, detail=True)["claims"]["detail"]
        self.assertEqual(len(detail), 2)
        self.assertIn("4,975만 달러", detail[0]["numbers"])
        self.assertNotIn("detail", analyze(KO_BODY)["claims"])


# ----------------------------------------------------------------------------
# 항목 2 — 공식 근거로 지원되는 주장 수
# ----------------------------------------------------------------------------
class GroundingTest(unittest.TestCase):
    OFFICIAL = "https://www.nasa.gov/news/x"

    def test_approximate_mode_counts_claims_with_an_official_link_in_the_same_paragraph(self):
        body = (f"NASA는 2026년 10월 1일 [발표]({self.OFFICIAL})했다. 예산은 500만 달러다.\n\n"
                "한편 EU는 2025년 계획을 밝혔다.\n\n"
                "회사 [블로그](https://onepredict.ai/news/1)는 2024년 계획을 밝혔다.\n")
        grounding = analyze(body)["grounding"]
        self.assertEqual((grounding["mode"], grounding["approximate"]), ("inline_link_approx", True))
        self.assertEqual(grounding["claims_checked"], 4)
        self.assertEqual(grounding["linked_in_sentence"], 2)
        self.assertEqual(grounding["linked_in_paragraph"], 3)
        self.assertEqual(grounding["supported"], 2)                       # 공식 도메인 링크가 같은 문단에 있는 주장만
        self.assertIsNone(grounding["unsupported"])
        self.assertIn("unsupported", grounding["null_reasons"])

    def test_image_credit_and_license_links_never_support_a_claim(self):
        body = "NASA는 2026년 10월 1일 [사진](https://unsplash.com/@x?utm_source=a)과 [라이선스](https://creativecommons.org/licenses/by/4.0/)를 썼다.\n"
        grounding = analyze(body, source_url="https://www.nasa.gov/a")["grounding"]
        self.assertEqual((grounding["linked_in_sentence"], grounding["supported"]), (0, 0))

    def test_without_any_original_the_value_is_null_not_zero(self):
        grounding = analyze("NASA는 2026년 10월 1일 발표했다.")["grounding"]
        self.assertEqual(grounding["mode"], "unavailable")
        for key in ("supported", "unsupported", "unverifiable", "supported_ratio", "linked_in_sentence", "linked_in_paragraph"):
            self.assertIsNone(grounding[key], key)
            self.assertIn(key, grounding["null_reasons"])
        self.assertNotEqual(grounding["supported"], 0)

    def test_a_front_matter_source_url_alone_is_enough_to_measure_the_approximation(self):
        grounding = analyze("NASA는 2026년 10월 1일 발표했다.", source_url="https://www.nasa.gov/a")["grounding"]
        self.assertEqual(grounding["mode"], "inline_link_approx")
        self.assertEqual(grounding["supported"], 0)                       # 측정했고 0 이다(본문에 링크가 없다)

    def test_source_text_mode_compares_values_across_languages(self):
        source = "The FTC announced on November 6, 2026 that the companies will pay $49.75 million. The order covers four states."
        body = ("FTC는 2026년 11월 6일 합의금 4,975만 달러를 발표했다.\n\n"                  # 값이 같다(만 달러 = million)
                "이 합의금은 약 4조 2천억 원 규모다.\n\n"                                  # 원문에 없는 환산
                "FTC는 소비자 보호를 맡는 기관이다.\n\n"                                    # 고유명사만 — FTC 는 원문에 있다
                "일반적으로 시장은 변한다.\n")                                              # 확인할 토큰이 없다
        grounding = analyze(body, source_text=source)["grounding"]
        self.assertEqual((grounding["mode"], grounding["approximate"]), ("source_text", False))
        self.assertEqual((grounding["supported"], grounding["unsupported"], grounding["unverifiable"]), (2, 1, 0))
        self.assertEqual(grounding["supported_ratio"], round(2 / 3, 3))
        self.assertEqual(len(grounding["unsupported_examples"]), 1)
        self.assertIn("4조 2천억", grounding["unsupported_examples"][0])
        self.assertIsNone(grounding["linked_in_paragraph"])

    def test_dates_and_small_counts_in_words_match_the_original(self):
        source = "Four states joined on November 3 to November 5, 2026."
        body = "4개 주가 2026년 11월 3일부터 5일까지 참여했다 한다.\n"
        self.assertEqual(analyze(body, source_text=source)["grounding"]["supported"], 1)
        wrong = "4개 주가 2026년 11월 4일부터 5일까지 참여했다 한다.\n"
        self.assertEqual(analyze(wrong, source_text=source)["grounding"]["unsupported"], 1)

    def test_hangul_entities_cannot_be_checked_against_an_english_original(self):
        grounding = analyze("캐나다 통계청은 새 통계를 발표했다.", source_text="Statistics Canada released new data.")["grounding"]
        self.assertEqual((grounding["supported"], grounding["unsupported"], grounding["unverifiable"]), (0, 0, 1))   # 한글 고유명사는 영문 원문과 맞출 수 없다
        none_checkable = analyze("정부는 새 제도를 도입했다고 밝혔다.", source_text="Some text.")["grounding"]
        self.assertEqual(none_checkable["unverifiable"], 0)               # 앵커가 없는 문장은 주장이 아니다

    def test_ratio_is_null_when_nothing_can_be_verified(self):
        grounding = analyze("일반적으로 시장은 변한다.", source_text="Anything.")["grounding"]
        self.assertEqual((grounding["supported"], grounding["unsupported"]), (0, 0))
        self.assertIsNone(grounding["supported_ratio"])
        self.assertIn("supported_ratio", grounding["null_reasons"])


# ----------------------------------------------------------------------------
# 항목 3 — 출처 수
# ----------------------------------------------------------------------------
class SourcesTest(unittest.TestCase):
    def test_counts_domains_links_and_list_items_without_image_credit_or_license_links(self):
        body = ("본문 [하나](https://science.nasa.gov/a) 와 [둘](https://www.nasa.gov/b) 와 [셋](https://www.pewresearch.org/c).\n\n"
                "## Sources\n- [NASA](https://science.nasa.gov/a)\n- [Pew](https://www.pewresearch.org/c)\n"
                "- Photo [작가](https://unsplash.com/@x?utm_source=a)\n\n"
                "![t](https://images.unsplash.com/p)\n*Photo by [N](https://unsplash.com/@n?utm_source=a) on [Unsplash](https://unsplash.com/?utm_source=a)*\n\n"
                "\"Title.\" Agency, Nov 6, 2026 <https://science.nasa.gov/a>. (https://creativecommons.org/licenses/by/4.0/)\n")
        sources = analyze(body, source_url="https://science.nasa.gov/a")["sources"]
        self.assertEqual(sources["domains"], ["nasa.gov", "pewresearch.org"])
        self.assertEqual((sources["distinct_domains"], sources["distinct_hosts"]), (2, 3))
        self.assertEqual((sources["body_links"], sources["body_links_unique"]), (3, 3))
        self.assertEqual(sources["sources_list_items"], 2)                       # 이미지 크레딧뿐인 항목은 세지 않는다
        self.assertTrue(sources["sources_section_present"])
        self.assertTrue(sources["citation_line"])
        self.assertTrue(sources["front_matter_source_url"])
        self.assertTrue(sources["source_url_in_text"])
        self.assertGreaterEqual(sources["image_credit_links_excluded"], 3)
        self.assertEqual(sources["license_links_excluded"], 1)

    def test_no_source_url_means_null_for_the_in_text_check(self):
        sources = analyze("본문 [하나](https://a.example.org/x) 입니다.")["sources"]
        self.assertFalse(sources["front_matter_source_url"])
        self.assertIsNone(sources["source_url_in_text"])
        self.assertIn("source_url_in_text", sources["null_reasons"])

    def test_categories_are_decided_by_host_so_one_registrable_domain_can_hold_a_magazine_and_a_society(self):
        sources = analyze("본문 [잡지](https://spectrum.ieee.org/x) 와 [학회](https://www.ieee.org/y) 와 [국가](https://www.nist.gov/z).\n")["sources"]
        self.assertEqual(sources["domains"], ["ieee.org", "nist.gov"])
        self.assertEqual(sources["categories"], ["news_media", "public_agency", "research"])
        self.assertEqual(sources["official_domains"], ["ieee.org", "nist.gov"])          # 학회 도메인(ieee.org)과 정부(nist.gov), 잡지 호스트는 공식으로 세지 않는다
        magazine_only = analyze("본문 [잡지](https://spectrum.ieee.org/x) 입니다.\n")["sources"]
        self.assertEqual((magazine_only["official_domains"], magazine_only["categories"]), ([], ["news_media"]))

    def test_links_to_the_own_site_are_not_external_sources_when_the_domain_is_given(self):
        body = ("NASA는 2026년 10월 1일 [공식](https://www.nasa.gov/a) 자료와 [다른 글](https://blog.example.github.io/posts/1/)·[또](https://example.github.io/posts/2/)를 참고했다.\n\n"
                "블로그 [소개](https://blog.example.github.io/about) 로 갔다.\n")
        plain = q.prepare(make_post(body))
        self.assertEqual(q.measure_sources(plain)["distinct_domains"], 2)             # 모르면 자기 사이트도 외부로 센다(github.io 하나)
        own = q.prepare(make_post(body), ["Example.GitHub.io"])
        sources = q.measure_sources(own)
        self.assertEqual((sources["domains"], sources["body_links"], sources["own_site_links_excluded"]), (["nasa.gov"], 1, 3))
        self.assertEqual(q.measure_grounding(own)["linked_in_paragraph"], 1)           # 자기 사이트 링크는 근거 링크도 아니다
        self.assertNotIn("example.github.io", json.dumps(q.analyze_corpus([make_post(body)], AS_OF, own_domains=["example.github.io"])))   # 보고서에는 개수만 남는다

    def test_a_post_without_any_link_has_zero_domains(self):
        sources = analyze("링크 없는 글이다.")["sources"]
        self.assertEqual((sources["distinct_domains"], sources["body_links"], sources["sources_list_items"]), (0, 0, 0))


# ----------------------------------------------------------------------------
# 항목 4 — 원문 대비 추가 가치(신호를 나눠 낸다)
# ----------------------------------------------------------------------------
class AddedValueTest(unittest.TestCase):
    def test_without_source_text_the_unsupported_addition_ratio_is_null(self):
        added = analyze(KO_BODY)["added_value"]
        self.assertIsNone(added["unsupported_addition_ratio"])
        self.assertIn("unsupported_addition_ratio", added["null_reasons"])
        for key in ("table_data_rows", "own_calculation_markers", "comparison_markers", "distinct_official_domains"):
            self.assertIn(key, added)

    def test_with_source_text_the_ratio_is_the_unsupported_share_of_checkable_claims(self):
        body = "FTC는 합의금 4,975만 달러를 발표했다.\n\n이 합의금은 약 4조 2천억 원 규모다.\n"
        added = analyze(body, source_text="The FTC said the settlement is $49.75 million.")["added_value"]
        self.assertEqual(added["unsupported_addition_ratio"], 0.5)

    def test_own_work_signals_are_separate_and_markers_of_the_sources_own_calculation_do_not_count(self):
        plain = analyze("통계청이 산출한 값은 4.1%다. 지난해와 비교하면 높다.\n")["added_value"]
        self.assertEqual((plain["own_calculation_markers"], plain["comparison_markers"], plain["own_work_signals_present"]), (0, 1, False))
        own = analyze("원문 수치로 직접 계산하면 증가율은 4.1%다.\n")["added_value"]
        self.assertEqual(own["own_calculation_markers"], 1)
        self.assertTrue(own["own_work_signals_present"])
        table = analyze("| 연도 | 값 |\n|---|---|\n| 2025 | 4.1% |\n")["added_value"]
        self.assertEqual(table["table_data_rows"], 1)
        self.assertTrue(table["own_work_signals_present"])

    def test_two_official_domains_count_as_a_cross_check_signal(self):
        body = "본문 [하나](https://www.nasa.gov/a) 와 [둘](https://www.pewresearch.org/b).\n"
        added = analyze(body)["added_value"]
        self.assertEqual(added["distinct_official_domains"], 2)
        self.assertTrue(added["own_work_signals_present"])
        self.assertNotIn("score", added)                                  # 점수 하나로 합치지 않는다


# ----------------------------------------------------------------------------
# 항목 5 — 한·영 유사도
# ----------------------------------------------------------------------------
def synth(lang, headings=1, paragraphs=3, bullets=2, numbers=""):
    """같은 모양의 합성 본문. 국문 문단은 공백 뺀 60자, 영문 문단은 112자라 길이 비율이 약 1.87(번역 범위 안)이다."""
    unit = ("가나다라마바 " * 10) if lang == "ko" else ("alpha beta gamma " * 8)
    title = "제목" if lang == "ko" else "Heading"
    lines = []
    for index in range(paragraphs):
        if 0 < index <= headings:
            lines += [f"### {title} {index}", ""]
        text = unit.strip() if index else (numbers + " " + unit.strip()).strip()
        lines += [text, ""]
    lines += [f"- {unit[:12].strip()} {index}" for index in range(bullets)]
    return "\n".join(lines) + "\n"


def pair_of(ko_body, en_body, ko_url="https://a.example.org/x", en_url="https://a.example.org/x"):
    ko = make_post(ko_body, "2026-11-01-KR-123456.md", lang="ko", source_url=ko_url)
    en = make_post(en_body, "2026-11-01-EN-123456.md", lang="en", source_url=en_url)
    return q.pair_metrics(q.prepare(ko), q.prepare(en))


class PairTest(unittest.TestCase):
    def test_a_translation_with_the_same_structure_numbers_and_length_band_is_suspected(self):
        result = pair_of(synth("ko", numbers="1,000명 2,000명"), synth("en", numbers="1,000 people and 2,000 people"))
        self.assertEqual(result["structure"]["matched"], 3)
        self.assertEqual(result["number_jaccard"], 1.0)
        self.assertTrue(q.CLONE_LENGTH_RATIO_BAND[0] <= result["length_ratio_en_per_ko"] <= q.CLONE_LENGTH_RATIO_BAND[1], result["length_ratio_en_per_ko"])
        self.assertIs(result["same_source_url"], True)
        self.assertTrue(result["translation_clone_suspected"])

    def test_the_structure_tolerance_boundary(self):
        ko = synth("ko", numbers="1,000명")
        same_plus_one = pair_of(ko, synth("en", paragraphs=4, headings=1, numbers="1,000 people"))
        self.assertEqual((same_plus_one["structure"]["matched"], same_plus_one["structure"]["within_tolerance"]), (2, 3))
        self.assertTrue(same_plus_one["translation_clone_suspected"])      # ±1 은 번역이 문단 하나를 합치거나 쪼갠 정도다
        plus_two = pair_of(ko, synth("en", paragraphs=5, headings=1, numbers="1,000 people"))
        self.assertEqual(plus_two["structure"]["within_tolerance"], 2)
        self.assertFalse(plus_two["translation_clone_suspected"])
        bullets_plus_two = pair_of(ko, synth("en", bullets=4, numbers="1,000 people"))
        self.assertFalse(bullets_plus_two["translation_clone_suspected"])
        self.assertEqual(q.CLONE_STRUCTURE_TOLERANCE, 1)

    def test_the_number_overlap_boundary_and_the_null_when_nobody_has_numbers(self):
        ko = synth("ko", numbers="1,000명 2,000명 3,000명 4,000명")
        same = pair_of(ko, synth("en", numbers="1,000 and 2,000 and 3,000 and 4,000 people"))
        self.assertEqual(same["number_jaccard"], 1.0)
        half = pair_of(ko, synth("en", numbers="1,000 and 2,000 and 5,000 and 6,000 people"))
        self.assertEqual(half["number_jaccard"], round(2 / 6, 3))
        self.assertFalse(half["translation_clone_suspected"])
        at_threshold = pair_of(synth("ko", numbers="1,000명 2,000명"), synth("en", numbers="1,000 and 3,000 people"))
        self.assertEqual(at_threshold["number_jaccard"], round(1 / 3, 3))
        exactly_half = pair_of(synth("ko", numbers="1,000명 2,000명 3,000명"), synth("en", numbers="1,000 and 2,000 people"))
        self.assertEqual(exactly_half["number_jaccard"], round(2 / 3, 3))
        self.assertTrue(exactly_half["translation_clone_suspected"])
        none = pair_of(synth("ko"), synth("en"))
        self.assertIsNone(none["number_jaccard"])
        self.assertIn("number_jaccard", none["null_reasons"])
        self.assertTrue(none["translation_clone_suspected"])              # 숫자가 없으면 구조·길이로만 본다

    def test_the_number_overlap_threshold_is_inclusive(self):
        ko = synth("ko", numbers="1,000명 2,000명")
        result = pair_of(ko, synth("en", numbers="1,000 and 2,000 and 3,000 and 4,000 people"))
        self.assertEqual(result["number_jaccard"], 0.5)                    # 2/4 — 기준(0.5)과 같으면 같은 숫자로 본다
        self.assertTrue(result["translation_clone_suspected"])

    def test_the_length_ratio_band_edges(self):
        lo, hi = q.CLONE_LENGTH_RATIO_BAND
        ko = "가" * 1000 + "\n\n" + "나" * 10
        for ratio, expected in ((lo - 0.05, False), (lo, True), (hi, True), (hi + 0.05, False)):
            with self.subTest(ratio=ratio):
                en_chars = round(ratio * (1000 + 10))
                en = "a" * (en_chars - 10) + "\n\n" + "b" * 10
                result = pair_of(ko, en)
                self.assertAlmostEqual(result["length_ratio_en_per_ko"], ratio, places=2)
                self.assertEqual(result["translation_clone_suspected"], expected)

    def test_different_source_urls_hold_the_verdict_back_as_null_with_a_reason_instead_of_asserting_not_a_pair(self):
        """독립 검증 P6: 출처 주소가 달라도 '번역 짝이 아니다'로 단정하지 않는다 — 판정을 보류(null)하고 이유 코드 source_url_differs 를 남긴다."""
        result = pair_of(synth("ko"), synth("en"), en_url="https://b.example.org/other")
        self.assertIs(result["same_source_url"], False)
        self.assertIsNone(result["translation_clone_suspected"])
        self.assertTrue(result["null_reasons"]["translation_clone_suspected"].startswith("source_url_differs"))
        self.assertTrue(result["reasons"][0].startswith("source_url_differs"))
        self.assertEqual(result["structure"]["within_tolerance"], 3)                 # 구조·숫자·길이 신호는 참고로 그대로 적는다
        self.assertIn("length_ratio_en_per_ko", result)
        report = q.analyze_corpus([make_post(synth("ko"), "2026-11-01-KR-123456.md", lang="ko", source_url="https://a.example.org/x"),
                                   make_post(synth("en"), "2026-11-01-EN-123456.md", lang="en", source_url="https://b.example.org/other")], AS_OF)
        self.assertEqual((report["summary"]["translation_clone_suspected"], report["summary"]["translation_clone_undetermined"]), (0, 1))
        self.assertIsNone(report["posts"][0]["pair"]["translation_clone_suspected"])
        text = q.render_markdown(report)
        self.assertIn("판정 보류(출처 주소가 달라서) 1쌍", text)
        self.assertEqual(text.count("보류(주소 다름)"), 3)                            # 글별 표 둘 + 짝 표 하나

    def test_a_missing_source_url_is_null_with_a_reason_and_does_not_block_the_structure_rule(self):
        ko = make_post(synth("ko"), "2026-11-01-KR-123456.md", lang="ko")
        en = make_post(synth("en"), "2026-11-01-EN-123456.md", lang="en")
        result = q.pair_metrics(q.prepare(ko), q.prepare(en))
        self.assertIsNone(result["same_source_url"])
        self.assertIn("same_source_url", result["null_reasons"])
        self.assertTrue(result["translation_clone_suspected"])

    def test_pairs_are_keyed_by_date_and_key_not_by_the_key_alone(self):
        posts = [make_post("가 문단이다.", "2026-10-26-KR-101652.md", lang="ko"), make_post("An english paragraph.", "2026-10-26-EN-101652.md", lang="en"),
                 make_post("나 문단이다.", "2026-10-29-KR-101652.md", lang="ko"), make_post("Another english paragraph.", "2026-10-29-EN-101652.md", lang="en"),
                 make_post("혼자 있는 글이다.", "2026-10-30-KR-222222.md", lang="ko")]
        pairs, unpaired = q.pair_posts(posts)
        self.assertEqual([(ko.date, en.date) for ko, en in pairs], [("2026-10-26", "2026-10-26"), ("2026-10-29", "2026-10-29")])
        self.assertEqual([post.rel for post in unpaired], ["2026-10-30-KR-222222.md"])

    def test_unpaired_posts_report_null_with_a_reason(self):
        report = q.analyze_corpus([make_post("혼자 있는 글이다.", "2026-10-30-KR-222222.md", lang="ko")], AS_OF)
        result = report["posts"][0]
        self.assertIsNone(result["pair"])
        self.assertIn("pair", result["null_reasons"])
        self.assertEqual(report["pairs"], [])


# ----------------------------------------------------------------------------
# 항목 5 보강(독립 검증 P6) — 독립 각색 음성 표본, 주소 표기 차이, 참고 신호
# ----------------------------------------------------------------------------
def frame(heading, paragraphs, bullets):
    """소제목 1·문단 3·불릿 2 인 같은 틀의 글 본문."""
    return f"### {heading}\n\n" + "\n\n".join(paragraphs) + "\n\n" + "\n".join(f"- {bullet}" for bullet in bullets) + "\n"


SAME_URL = "https://a.example.org/x"
OTHER_URL = "https://b.example.org/other"


def adaptation_fixtures():
    """독립 각색 합성 표본 8쌍(같은 틀 소제목 1·문단 3·불릿 2, 문장은 서로 다르게 직접 쓴 것). 번역이 아니라 같은 틀로 따로 쓴 글이다.
    verdict 는 이 도구가 지금 내는 판정이다 — False 는 걸러진 것, None 은 보류, True 는 알려진 오탐이다(아래 시험이 이유를 못박는다)."""
    transit_ko = ["도시 철도 이용객은 하루 340만 명으로 추산되며 출근 시간에 가장 많이 몰린다.",
                  "운영 기관은 열차 간격을 줄이는 방안을 검토했고 비용은 120억 원으로 본다.",
                  "내년에는 노선 두 곳부터 먼저 고치고 그 결과를 보아 나머지를 정할 계획이다."]
    transit_en = ["Rail ridership is estimated at 4.1 million trips a day, and crowding peaks at the morning commute.",
                  "The operator studied shorter train intervals and puts the cost at 35 billion won.",
                  "Next year two lines are rebuilt first, and the results decide the rest."]
    water_ko = ["알파기관(Alpha Agency)은 지역 물 관리 계획을 새로 다듬어 시민에게 설명했다.", "계획의 핵심은 저수지 운영 기준을 가뭄 상황에 맞춰 바꾸는 것이다.",
                "다음 단계로 지자체와 주민 대표가 참여하는 협의 자리를 마련한다."]
    water_en = ["Beta Institute explained its review of reservoir operation during dry spells to residents.", "It argues that release rules should follow the drought stage, not the calendar.",
                "A consultation round with officers and residents is planned next."]
    return {
        "different numbers": dict(ko=transit_ko, en=transit_en, verdict=False, band="in", ref_numbers_below=0.5),
        "one shared number out of five": dict(
            ko=["지역 병원 접근성 조사에서 응답자 1,200명 가운데 45%가 대기 시간이 길다고 답했다.", "보건소는 예약 제도를 손보는 데 7억 원을 쓰기로 했다.", "조사 결과는 다음 분기 회의에서 다시 다룬다."],
            en=["A regional survey of 1,200 respondents found that nearly half said waiting times were too long.",
                "Local clinics plan to spend 2.5 billion won on bookings, and 88 sites will be reviewed.",
                "The results will be discussed again at the meeting next quarter."],
            verdict=False, band="in", ref_numbers_below=0.5),
        "no numbers and a much shorter English post": dict(
            ko=["새 환경 규칙은 공공기관과 연구소가 먼저 따르도록 하고 민간에는 단계적으로 적용한다고 밝혔다.", "규칙의 세부 기준은 전문가 자문을 거쳐 올해 안에 정하며 이후 점검 결과를 공개한다.",
                "관계 부처는 현장 의견을 모아 필요하면 기준을 고치겠다고 설명했다."],
            en=["The new rules apply to agencies first.", "Details will be set this year.", "Ministries may revise them later."], verdict=False, band="below"),
        "no numbers and a much longer English post": dict(
            ko=["항만 자동화 시험은 안전 점검을 먼저 끝낸 뒤 시작한다.", "운영사는 장비 교체 계획을 알렸다.", "결과는 나중에 공개한다."],
            en=["The port automation trial will begin only after the safety inspection is finished, and the terminal operator has stressed that every crane, vehicle and control "
                "system must pass a separate review before any live operation is allowed to start on the quay.",
                "The operator announced a replacement plan for aging equipment, noting that suppliers, insurers and the local labor council will all be consulted over the coming "
                "months before any schedule is confirmed in writing.",
                "Results of the trial will be published later together with a plain language summary of what went well, what failed and what the operator intends to change in "
                "the second phase."], verdict=False, band="above"),
        "no source address on either side and different numbers": dict(ko=transit_ko, en=transit_en, ko_url=None, en_url=None, verdict=False, band="in", ref_numbers_below=0.5),
        "different source address even though every signal matches": dict(ko=water_ko, en=water_en, en_url=OTHER_URL, verdict=None, band="in", ref_names=0.0),
        "known false positive: same frame, same address, no numbers, different names": dict(ko=water_ko, en=water_en, verdict=True, band="in", ref_names=0.0),
        "known false positive: same frame, no address, no numbers, no names": dict(
            ko=["이 에세이는 일상의 작은 습관이 오래 남는 이유를 천천히 살펴본다.", "습관은 환경과 반복이 만든다는 점을 여러 장면으로 보여 준다.", "마지막으로 독자가 해 볼 만한 작은 실험을 제안한다."],
            en=["This essay slowly looks at why small daily habits tend to last for such a long time.", "It shows through several scenes that habits are shaped by surroundings and repetition.",
                "At the end it suggests a few small experiments that readers can try for themselves."], ko_url=None, en_url=None, verdict=True, band="in", ref_none=True)}


def adaptation_pair(fixture):
    ko = frame("쟁점", fixture["ko"], ["쟁점 정리", "다음 단계"])
    en = frame("Issues", fixture["en"], ["Key issues", "Next steps"])
    return pair_of(ko, en, ko_url=fixture.get("ko_url", SAME_URL), en_url=fixture.get("en_url", SAME_URL))


class IndependentAdaptationTest(unittest.TestCase):
    def test_eight_independent_adaptations_with_the_same_frame_are_mostly_rejected_and_two_known_cases_are_not(self):
        outcomes = {}
        for name, fixture in adaptation_fixtures().items():
            with self.subTest(name=name):
                result = adaptation_pair(fixture)
                self.assertEqual(result["structure"]["within_tolerance"], 3, "표본의 틀이 같아야 한다")
                low, high = q.CLONE_LENGTH_RATIO_BAND
                ratio = result["length_ratio_en_per_ko"]
                self.assertEqual({"in": low <= ratio <= high, "below": ratio < low, "above": ratio > high}[fixture["band"]], True, (name, ratio))
                self.assertEqual(result["translation_clone_suspected"], fixture["verdict"], (name, result["reasons"]))
                outcomes[name] = result["translation_clone_suspected"]
        counts = {"걸러짐": sum(1 for value in outcomes.values() if value is False), "보류": sum(1 for value in outcomes.values() if value is None),
                  "걸림(오탐)": sum(1 for value in outcomes.values() if value is True)}
        self.assertEqual(counts, {"걸러짐": 5, "보류": 1, "걸림(오탐)": 2})          # 문서의 '오탐 0'은 표본 수와 함께 이 숫자로 적는다

    def test_the_two_known_false_positives_are_the_ones_with_no_numbers_and_the_same_frame_and_the_reference_signals_show_it(self):
        fixtures = adaptation_fixtures()
        names = fixtures["known false positive: same frame, same address, no numbers, different names"]
        result = adaptation_pair(names)
        self.assertIsNone(result["number_jaccard"])                                 # 숫자가 없으면 숫자 규칙이 아무것도 못 거른다
        self.assertEqual(result["ref_names_jaccard"], 0.0)                          # 참고 신호는 영문 이름이 전혀 겹치지 않는다고 알려 준다
        self.assertEqual(result["ref_shared_names"], 0)
        bare = adaptation_pair(fixtures["known false positive: same frame, no address, no numbers, no names"])
        self.assertIsNone(bare["ref_numbers_jaccard"])
        self.assertIsNone(bare["ref_names_jaccard"])                                # 이름도 숫자도 없으면 참고 신호도 근거가 없다
        for key in ("ref_numbers_jaccard", "ref_names_jaccard"):
            self.assertIn(key, bare["null_reasons"])

    def test_rejected_adaptations_share_little_with_their_partner_while_a_real_translation_shares_everything(self):
        fixtures = adaptation_fixtures()
        for name in ("different numbers", "one shared number out of five", "no source address on either side and different numbers"):
            with self.subTest(name=name):
                self.assertLess(adaptation_pair(fixtures[name])["ref_numbers_jaccard"], fixtures[name]["ref_numbers_below"])
        translated_ko = frame("쟁점", ["FTC는 2026년 11월 6일 합의금 4,975만 달러를 발표했다.", "Progress Residential 은 합의에 동의했다고 밝혔다.", "후속 조치는 다음 분기에 다룬다."], ["쟁점 정리", "다음 단계"])
        translated_en = frame("Issues", ["The FTC announced a $49.75 million settlement on November 6, 2026, according to the agency.", "Progress Residential said it agreed to the settlement.",
                                         "Follow-up steps will be handled next quarter."], ["Key issues", "Next steps"])
        translated = pair_of(translated_ko, translated_en)
        self.assertEqual((translated["ref_numbers_jaccard"], translated["ref_names_jaccard"]), (1.0, 1.0))
        self.assertGreaterEqual((translated["ref_shared_numbers"], translated["ref_shared_names"]), (2, 2))
        self.assertTrue(translated["translation_clone_suspected"])
        self.assertTrue(any(reason.startswith("참고(판정에 쓰지 않음)") for reason in translated["reasons"]))

    def test_reference_signals_never_change_the_verdict(self):
        """참고 신호는 판정 임계값에 쓰이지 않는다(독립 검증 P6 권고: 임계값은 건드리지 않는다) — 신호를 비워도 모든 표본의 판정이 같다."""
        for name, fixture in adaptation_fixtures().items():
            with self.subTest(name=name):
                with_signals = adaptation_pair(fixture)
                with mock.patch.object(q, "_reference_anchors", return_value=(set(), set())):
                    without_signals = adaptation_pair(fixture)
                self.assertEqual(with_signals["translation_clone_suspected"], without_signals["translation_clone_suspected"])
                self.assertIsNone(without_signals["ref_numbers_jaccard"])

    def test_a_true_translation_pair_is_still_suspected_when_the_two_addresses_differ_only_in_spelling(self):
        """독립 검증 P6: www. 없음·http·`&ref=x`·끝 슬래시 한 글자 차이로 번역 쌍 판정이 풀리던 미탐."""
        ko_url = "https://www.example.org/report/2026/a?id=7"
        variants = ["https://example.org/report/2026/a?id=7", "http://www.example.org/report/2026/a?id=7", "https://www.example.org/report/2026/a?id=7&ref=x",
                    "https://www.example.org/report/2026/a/?id=7&utm_medium=mail", "https://WWW.Example.org/report/2026/a?id=7#top", "https://www.example.org/report/2026/a?ref=x&id=7"]
        for en_url in variants:
            with self.subTest(en_url=en_url):
                result = pair_of(synth("ko", numbers="1,000명 2,000명"), synth("en", numbers="1,000 people and 2,000 people"), ko_url=ko_url, en_url=en_url)
                self.assertIs(result["same_source_url"], True)
                self.assertIs(result["translation_clone_suspected"], True)
        for different in ("https://www.example.org/report/2026/b?id=7", "https://www.example.org/report/2026/a?id=8", "https://other.example.org/report/2026/a?id=7"):
            with self.subTest(different=different):
                result = pair_of(synth("ko", numbers="1,000명 2,000명"), synth("en", numbers="1,000 people and 2,000 people"), ko_url=ko_url, en_url=different)
                self.assertIs(result["same_source_url"], False)
                self.assertIsNone(result["translation_clone_suspected"])

    def test_url_normalization_ignores_www_scheme_trailing_slash_tracking_keys_and_query_order(self):
        base = q.normalize_url("https://example.org/a/b?id=7&k=1")
        same = ["http://example.org/a/b?id=7&k=1", "https://www.example.org/a/b?id=7&k=1", "https://EXAMPLE.org/a/b/?id=7&k=1", "https://example.org/a/b?k=1&id=7",
                "https://example.org/a/b?id=7&k=1&utm_source=x&ref=twitter", "https://example.org/a/b?id=7&k=1&ref=x", "https://example.org/a/b?id=7&k=1#section",
                "https://example.org/a/b?fbclid=abc&id=7&k=1&gclid=1", "  https://example.org/a/b?id=7&k=1  "]
        for url in same:
            with self.subTest(url=url):
                self.assertEqual(q.normalize_url(url), base)
        different = ["https://example.org/a/b?id=8&k=1", "https://example.org/a/c?id=7&k=1", "https://example.com/a/b?id=7&k=1", "https://example.org/a/b?id=7&k=1&page=2",
                     "https://sub.example.org/a/b?id=7&k=1", "https://example.org/A/b?id=7&k=1"]
        for url in different:
            with self.subTest(url=url):
                self.assertNotEqual(q.normalize_url(url), base)
        self.assertEqual(q.normalize_url("HTTPS://Example.org/a/?utm_source=x&k=1#frag"), "https://example.org/a?k=1")
        self.assertEqual(q.normalize_url("http://[abc/x"), "http://[abc/x")                 # 깨진 주소는 그대로 돌려준다(예외 없음)


# ----------------------------------------------------------------------------
# 항목 6 — 보도자료·회사 발표 단순 요약 여부
# ----------------------------------------------------------------------------
COMPANY_URL = "https://onepredict.ai/news/?bmode=view&idx=1"


def press(body, **front):
    return analyze(body, **front)["press_release_summary"]


class PressReleaseTest(unittest.TestCase):
    def test_single_company_source_without_own_work_is_flagged(self):
        result = press(f"회사는 [발표]({COMPANY_URL})에서 새 제품을 소개했다고 밝혔다.\n", source_url=COMPANY_URL)
        self.assertTrue(result["flag"])
        self.assertEqual(result["kind"], "company_release_summary")
        self.assertEqual(result["primary_source_category"], "company")

    def test_own_work_signals_or_a_second_official_source_clear_the_flag(self):
        table = f"회사는 [발표]({COMPANY_URL})했다.\n\n| 연도 | 값 |\n|---|---|\n| 2025 | 4.1% |\n"
        self.assertFalse(press(table, source_url=COMPANY_URL)["flag"])
        two = f"회사는 [발표]({COMPANY_URL})했다. 공공 자료 [하나](https://www.nasa.gov/a) 와 [둘](https://www.pewresearch.org/b) 도 있다.\n"
        self.assertFalse(press(two, source_url=COMPANY_URL)["flag"])

    def test_company_plus_news_media_without_any_official_source_is_still_company_only(self):
        body = f"회사는 [발표]({COMPANY_URL})했다. 언론 [보도](https://www.edaily.co.kr/news/1)도 같다.\n"
        result = press(body, source_url=COMPANY_URL)
        self.assertEqual(result["kind"], "company_release_summary")
        self.assertTrue(any("회사 도메인뿐" in reason for reason in result["reasons"]))

    def test_an_official_press_release_url_with_no_own_work_is_flagged_as_official_press_release_summary(self):
        result = press(f"FTC는 [보도자료]({KO_SOURCE_URL})에서 합의를 발표했다.\n", source_url=KO_SOURCE_URL)
        self.assertEqual(result["kind"], "official_press_release_summary")
        self.assertIn("press", result["press_format_tokens"])

    def test_a_plain_news_path_on_an_official_domain_is_not_a_press_release(self):
        url = "https://commission.europa.eu/news-and-media/news/x_en"
        result = press(f"집행위는 [소식]({url})에서 발표했다.\n", source_url=url)
        self.assertFalse(result["flag"])
        self.assertEqual(result["kind"], "none")
        self.assertEqual(result["press_format_tokens"], [])             # 공식 도메인에서는 약한 조각(news·media)을 보도자료 형식으로 세지 않는다

    def test_an_unknown_domain_with_a_press_path_is_a_press_format_summary(self):
        url = "https://something.example.com/press/2026/x"
        result = press(f"이곳은 [공지]({url})를 냈다.\n", source_url=url)
        self.assertEqual(result["kind"], "press_format_summary")

    def test_an_unknown_domain_without_any_signal_is_not_flagged(self):
        result = press("이곳은 [공지](https://something.example.com/a/b)를 냈다.\n", source_url="https://something.example.com/a/b")
        self.assertFalse(result["flag"])

    # --- 독립 검증 P10: 기사 주소의 /news/ 조각 하나만으로는 '보도자료 형식 요약'이 켜지지 않는다 ---
    def test_a_news_path_alone_is_not_a_press_release_format(self):
        for url in ("https://www.aitimes.com/news/articleView.html?idxno=1", "https://something.example.com/news/2026/x", "https://www.edaily.co.kr/news/read?newsId=1",
                    "https://medium.com/news/post-1"):
            with self.subTest(url=url):
                result = press(f"이곳은 [기사]({url})를 냈다.\n", source_url=url)
                self.assertFalse(result["flag"])
                self.assertEqual((result["kind"], result["press_format_tokens"]), ("none", []))

    def test_release_like_fragments_other_than_news_still_make_a_press_format_summary(self):
        for url in ("https://www.aitimes.com/news/press/1", "https://something.example.com/announcements/2026/x", "https://something.example.com/news/notice/1",
                    "https://something.example.com/pr/2026/x", "https://www.edaily.co.kr/press-release/1"):
            with self.subTest(url=url):
                result = press(f"이곳은 [공지]({url})를 냈다.\n", source_url=url)
                self.assertEqual(result["kind"], "press_format_summary", url)
                self.assertTrue(result["press_format_tokens"])
        mixed = press("이곳은 [공지](https://something.example.com/news/announcement/1)를 냈다.\n", source_url="https://something.example.com/news/announcement/1")
        self.assertEqual(mixed["press_format_tokens"], ["announcement", "news"])                      # 보고에는 news 도 남는다(켜진 이유가 아니다)
        self.assertEqual(q.PRESS_GENERIC_TOKENS, frozenset({"news"}))

    def test_without_any_source_address_the_flag_is_null_with_a_reason(self):
        result = press("출처 없는 글이다.")
        self.assertIsNone(result["flag"])
        self.assertIsNone(result["kind"])
        self.assertIn("flag", result["null_reasons"])
        self.assertIn("kind", result["null_reasons"])


# ----------------------------------------------------------------------------
# 항목 7 — 행사 안내 중심 여부
# ----------------------------------------------------------------------------
EVENT_KO = """유럽 위원회는 2026년 11월 3일부터 5일까지 바르셀로나에서 열리는 엑스포에 참가한다. 이번 행사에서 인간 중심 AI를 선보일 예정이다.

행사장 부스에서 방문객을 맞는다. 참석 신청은 현장에서 접수한다.

디지털 트윈은 도시를 가상 공간에 구현하는 기술이다. 정책 효과를 미리 시뮬레이션할 수 있다.

기술의 한계도 있다. 시민의 의견 수렴이 필요하다.
"""
NON_EVENT_KO = """통계청은 2026년 10월 30일 실업률이 4.1%라고 발표했다. 전년보다 0.3%포인트 낮다.

허블 망원경의 부스트 방안이 검토됐다. 부스트는 궤도를 높이는 방식이다.

정책 효과는 아직 알기 어렵다. 후속 조사가 필요하다.
"""


class EventFocusTest(unittest.TestCase):
    def event(self, body, name="2026-11-01-KR-123456.md", as_of=AS_OF, **front):
        return analyze(body, name, as_of=as_of, **front)["event_focus"]

    def test_an_event_announcement_is_flagged_with_reasons_and_date_status(self):
        result = self.event(EVENT_KO)
        self.assertTrue(result["flag"])
        self.assertGreaterEqual(result["event_sentence_ratio"], q.EVENT_SENTENCE_RATIO_MIN)
        self.assertGreaterEqual(result["distinct_event_terms"], q.EVENT_DISTINCT_TERMS_MIN)
        self.assertEqual(result["dates_after_post_date"], ["2026-11-05"])
        self.assertEqual(result["date_status"], "past_event_dates")        # 기준일 11-09 에는 이미 끝난 행사
        self.assertTrue(any("지난 행사" in reason for reason in result["reasons"]))

    def test_the_as_of_date_decides_whether_the_event_is_still_upcoming(self):
        upcoming = self.event(EVENT_KO, as_of=datetime.date(2026, 11, 2))
        self.assertEqual(upcoming["date_status"], "upcoming")
        self.assertEqual(upcoming["dates_after_as_of"], ["2026-11-05"])
        self.assertTrue(any("아직 열리지 않은" in reason for reason in upcoming["reasons"]))
        self.assertEqual(self.event(EVENT_KO, as_of=datetime.date(2026, 11, 5))["date_status"], "past_event_dates")      # 끝나는 날은 지난 것이 아니다 → 기준일 이후가 아니다

    def test_a_policy_or_statistics_post_is_not_an_event_post_and_boost_is_not_a_booth(self):
        result = self.event(NON_EVENT_KO)
        self.assertFalse(result["flag"])
        self.assertEqual(result["distinct_event_terms"], 0)                # 부스트(boost)는 행사 신호어 '부스'가 아니다
        self.assertEqual(result["date_status"], "no_event_dates")

    def test_english_event_posts_and_the_title_rule(self):
        body = ("The delegation will attend the Smart City Expo. The event will take place from November 3 to November 5, 2026. "
                "Visitors can register at the booth.\n\nDigital twins model cities. They help planners.\n\nLimits remain. Public input matters.\n")
        self.assertTrue(self.event(body, "2026-11-01-EN-123456.md", lang="en", title="Smart City Expo 2026")["flag"])
        title_only = ("The program covers rules for energy storage. The Expo is mentioned once here.\n\nSecond paragraph about the rules. Third sentence about costs.\n\n"
                      "Fourth paragraph on limits. Fifth sentence about timing.\n\nSixth paragraph. Seventh sentence. Eighth sentence.\n")
        result = self.event(title_only, "2026-11-01-EN-123456.md", lang="en", title="Smart City Expo 2026")
        self.assertEqual(result["title_event_terms"], ["expo"])
        self.assertFalse(result["flag"])                                   # 제목에 있어도 문장 비율이 EVENT_TITLE_RATIO_MIN 미만이면 아니다

    def test_the_ratio_and_distinct_term_thresholds_are_both_needed(self):
        one_term_everywhere = "행사가 있다. 행사 안내가 있다. 행사 장소가 있다.\n"
        result = self.event(one_term_everywhere)
        self.assertEqual(result["distinct_event_terms"], 1)
        self.assertFalse(result["flag"])

    def test_an_empty_body_is_null_not_false(self):
        result = self.event("")
        self.assertIsNone(result["flag"])
        self.assertIsNone(result["event_sentence_ratio"])
        self.assertIn("flag", result["null_reasons"])

    def test_every_event_term_matches_a_sample_of_itself(self):
        samples = {"행사 일정": "일정을 확인하세요", "신청 기간": "신청 기간 안내", "take place": "it will take place", "joins ... expo": "Seoul joins the Smart City Expo"}
        for label, pattern in q.EVENT_TERMS:
            with self.subTest(label=label):
                text = samples.get(label, label)
                self.assertTrue(re.search(pattern, text, re.I), f"{label}: {pattern}")

    # --- 독립 검증 P10: 공청회·설명회·간담회·hearing·briefing·town hall·open house 안내가 행사로 잡힌다 ---
    def test_hearing_briefing_town_hall_and_open_house_notices_are_event_posts_in_both_languages(self):
        korean = ("시 교통정책 공청회가 있다. 주민 설명회가 있다. 관계자 간담회가 있다. 시민 토론회가 있다. 일반 의견은 서면으로도 받는다. "
                  "정책 배경은 아래 자료와 같다. 예산 규모는 아직 정해지지 않았다. 세부 내용은 추후 알린다. 문서는 누리집에 있다. 담당 부서는 같다.\n")
        result = self.event(korean)
        self.assertEqual(result["distinct_event_terms"], 4)
        self.assertGreaterEqual(result["event_sentence_ratio"], q.EVENT_SENTENCE_RATIO_MIN)
        self.assertTrue(result["flag"])
        english = ("A public hearing is planned. A briefing will follow. A town hall is open to all residents. An open house is also planned. "
                   "The policy background is in the paper below. The budget is not set yet. Details come later. The document is online. The office stays the same. "
                   "Residents may send written comments.\n")
        result = self.event(english, "2026-11-01-EN-123456.md", lang="en")
        self.assertEqual(sorted(result["top_terms"]), sorted(["hearing", "briefing", "town hall", "open house"]))
        self.assertTrue(result["flag"])
        for text in ("public hearings", "two briefings", "Town Halls", "an Open House", "a roundtable", "a round-table talk", "seminars", "forums"):   # 복수형·대소문자도 잡는다
            self.assertTrue(q._event_terms_in(text), text)
        for text in ("a rehearing was denied", "hearsay", "briefly", "informal", "reforum", "seminary", "청문 절차"):                      # 다른 낱말의 일부는 잡지 않는다
            self.assertEqual(q._event_terms_in(text), [], text)

    def notice_body(self, total, event_sentences, terms):
        """문장 total 개 중 event_sentences 개만 행사 신호어(terms 를 돌려 쓴다)를 담는다 — 나머지는 신호어가 없는 정책 설명 문장."""
        sentences = []
        for index in range(total):
            if index < event_sentences:
                sentences.append(f"{terms[index % len(terms)]} 안내 문장 {index} 이다.")
            else:
                sentences.append(f"정책 배경 설명 문장 {index} 번째 내용이다.")
        return " ".join(sentences) + "\n"

    def test_the_sentence_ratio_threshold_is_inclusive_and_just_below_it_is_not_an_event_post(self):
        """독립 검증 P10: 행사가 아닌 글의 최고 0.176 과 임계값 0.2 의 간격이 좁다 — 경계 양쪽을 못박는다."""
        terms = ["행사", "개최", "참가"]
        for event_sentences, expected in ((17, False), (19, False), (20, True), (21, True)):
            with self.subTest(event_sentences=event_sentences):
                result = self.event(self.notice_body(100, event_sentences, terms))
                self.assertEqual(result["event_sentence_ratio"], event_sentences / 100)
                self.assertEqual(result["distinct_event_terms"], 3)
                self.assertEqual(result["flag"], expected)
        self.assertEqual(q.EVENT_SENTENCE_RATIO_MIN, 0.2)

    def test_the_distinct_term_threshold_and_the_title_rule_have_their_own_edges(self):
        two_terms = self.event(self.notice_body(100, 50, ["행사", "개최"]))
        self.assertEqual((two_terms["distinct_event_terms"], two_terms["flag"]), (2, False))              # 비율이 높아도 신호어가 둘뿐이면 아니다
        three_terms = self.event(self.notice_body(100, 20, ["행사", "개최", "참가"]))
        self.assertEqual((three_terms["distinct_event_terms"], three_terms["flag"]), (3, True))
        for event_sentences, expected in ((14, False), (15, True), (16, True)):                            # 제목에 신호어가 있으면 0.15 부터
            with self.subTest(title_rule=event_sentences):
                result = self.event(self.notice_body(100, event_sentences, ["행사"]), title="국제 행사 안내")
                self.assertEqual(result["title_event_terms"], ["행사"])
                self.assertEqual(result["flag"], expected)
        self.assertFalse(self.event(self.notice_body(100, 16, ["행사"]), title="정책 안내")["flag"])          # 제목에 신호어가 없으면 0.16 은 모자란다


# ----------------------------------------------------------------------------
# 항목 8 — 건강 위험 판정
# ----------------------------------------------------------------------------
class HealthTest(unittest.TestCase):
    def health(self, body, **kw):
        return analyze(body, **kw)["health_risk"]

    def test_a_post_without_health_words_is_none(self):
        result = self.health("통계청은 2026년 10월 30일 실업률이 4.1%라고 발표했다.")
        self.assertEqual(result["level"], "none")
        self.assertEqual(result["reasons"], [])

    def test_a_strong_medical_word_alone_is_caution(self):
        result = self.health("보건 당국은 만성 질환 관리 통계를 공개했다.")
        self.assertEqual(result["level"], "caution")
        self.assertIn("질환", result["medical_strong_terms"])

    def test_two_different_weak_or_safety_terms_are_caution_and_one_is_not(self):
        two = self.health("교정 시설 경험자의 사망 통계와 건강 지표를 정리했다.")
        self.assertEqual(two["level"], "caution")
        self.assertEqual(sorted(set(two["medical_weak_terms"]) | set(two["safety_adjacent_terms"])), ["건강", "사망"])
        one = self.health("교정 시설 경험자의 사망 통계를 정리했다.")
        self.assertEqual(one["level"], "none")
        repeated = self.health("사망 통계의 사망 원인과 사망 시기를 정리했다.")
        self.assertEqual(repeated["level"], "none")                        # 같은 낱말을 여러 번 써도 종류는 하나

    def test_english_diagnostics_is_not_a_medical_diagnosis(self):
        technical = self.health("The climate dashboard offers diagnostic tools for regional hazards.", name="2026-11-01-EN-123456.md", lang="en")
        self.assertEqual(technical["level"], "none")
        medical = self.health("The patient received a diagnosis last year.", name="2026-11-01-EN-123456.md", lang="en")
        self.assertEqual(medical["level"], "caution")
        self.assertIn("diagnosis", medical["medical_strong_terms"])

    def test_a_medical_word_with_an_assertion_in_one_sentence_is_high(self):
        result = self.health("이 보충제는 반드시 효과가 입증된 치료법이다.")
        self.assertEqual(result["level"], "high")
        self.assertTrue(result["assertive_with_medical"])
        english = self.health("This supplement definitely cures the disease.", name="2026-11-01-EN-123456.md", lang="en")
        self.assertEqual(english["level"], "high")

    def test_advice_next_to_a_medical_word_is_high_unless_a_consultation_notice_is_in_the_same_sentence(self):
        advice = self.health("환자는 이 약물을 매일 복용하세요.")
        self.assertEqual(advice["level"], "high")
        self.assertTrue(advice["advice_with_medical"])
        disclaimed = self.health("환자는 의사와 상담한 뒤 이 약물을 복용하세요.")
        self.assertNotEqual(disclaimed["level"], "high")
        self.assertEqual(disclaimed["advice_with_medical"], [])

    def test_the_profile_rule_is_evidence_and_counts_as_one_extra_signal_only_for_a_word_the_dictionary_lacks(self):
        result = self.health("건강 지표를 정리했다. 비만 통계도 함께 실었다.")             # 건강(사전 약한 의료어) + 비만(사전에 없고 프로필 규칙만 맞춤) = 서로 다른 신호 둘
        self.assertEqual(result["profile"], "blogger_practical_ko.json")
        self.assertEqual([hit["word"] for hit in result["profile_body_rule_hits"]], ["비만"])
        self.assertEqual(sorted(result["medical_weak_terms"]), ["건강"])
        self.assertTrue(result["profile_adds_signal"])
        self.assertEqual(result["level"], "caution")
        self.assertNotEqual(result["level"], "high")                       # 프로필 규칙은 증거일 뿐 판정(높음)을 만들지 않는다
        self.assertTrue(any("프로필 본문 규칙" in reason for reason in result["reasons"]))
        alone = self.health("비만 통계를 정리했다.")                         # 프로필 규칙 신호 하나뿐이면 주의가 아니다
        self.assertEqual((alone["level"], alone["profile_adds_signal"]), ("none", True))
        english = self.health("The health report also lists pills.", name="2026-11-01-EN-123456.md", lang="en")
        self.assertEqual((english["level"], english["profile_adds_signal"]), ("caution", True))
        self.assertEqual(self.health("The report lists pills.", name="2026-11-01-EN-123456.md", lang="en")["level"], "none")

    ONE_WORD_KO = ("진단", "처방", "접종", "의료", "부작용", "중독", "병원", "건강", "의사", "사망", "사고")
    ONE_WORD_EN = ("medical", "drug", "treatment", "health", "hospital", "death")

    def test_one_ordinary_sentence_with_a_single_weak_or_safety_word_is_none_in_both_languages(self):
        """독립 검증 P4: 사전 약한 의료어를 프로필 규칙이 한 번 더 세어 '진단'·'처방'·'접종'·'의료'·medical·drug·treatment 한 낱말이 주의가 되던 오탐."""
        for word in self.ONE_WORD_KO:
            with self.subTest(word=word):
                result = self.health(f"이 문장은 평범하게 {word}이라는 낱말 하나만 들어 있다.")
                self.assertEqual(set(result["medical_weak_terms"]) | set(result["safety_adjacent_terms"]), {word}, "시험 문장이 사전 낱말 하나를 정확히 담아야 한다")
                self.assertEqual(result["medical_strong_terms"], {})
                self.assertEqual((result["level"], result["reasons"]), ("none", []))
                self.assertFalse(result["profile_adds_signal"], "프로필이 맞춘 낱말이 사전에 이미 있으면 더하지 않는다")
        for word in self.ONE_WORD_EN:
            with self.subTest(word=word):
                result = self.health(f"This ordinary sentence mentions the word {word} just once.", name="2026-11-01-EN-123456.md", lang="en")
                self.assertEqual(set(result["medical_weak_terms"]) | set(result["safety_adjacent_terms"]), {word})
                self.assertEqual(result["medical_strong_terms"], {})
                self.assertEqual((result["level"], result["reasons"]), ("none", []))
                self.assertFalse(result["profile_adds_signal"])

    def test_the_profile_rule_and_the_dictionary_do_not_double_count_but_two_different_words_still_make_caution(self):
        for first, second in (("진단", "병원"), ("처방", "사망"), ("의료", "건강")):
            with self.subTest(pair=(first, second)):
                result = self.health(f"{first}과 {second}에 대한 평범한 문장이다.")
                self.assertEqual(result["level"], "caution")
                self.assertFalse(result["profile_adds_signal"])
                self.assertEqual(sorted(set(result["medical_weak_terms"]) | set(result["safety_adjacent_terms"])), sorted([first, second]))
        repeated = self.health("진단 결과가 나왔다. 진단 방식을 바꿨다. 진단 기준도 있다.")
        self.assertEqual(repeated["level"], "none")                        # 같은 낱말을 여러 번 써도 하나
        self.assertEqual(self.health("The medical team said the drug was approved.", name="2026-11-01-EN-123456.md", lang="en")["level"], "caution")   # 서로 다른 둘

    def test_a_profile_word_found_by_the_strong_list_changes_nothing_extra(self):
        result = self.health("보건 당국은 암 수술 통계를 공개했다.")
        self.assertEqual(result["level"], "caution")                       # 강한 의료어 하나만으로 이미 주의
        self.assertFalse(result["profile_adds_signal"])                    # 프로필이 맞춘 '수술' 은 사전에 있다

    def test_a_missing_profile_is_null_with_a_reason_and_the_own_dictionary_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(q, "_PROFILE_DIR", Path(tmp)), mock.patch.dict(q._PROFILE_CACHE, {}, clear=True):
                result = self.health("보건 당국은 만성 질환 관리 통계를 공개했다.")
        self.assertIsNone(result["profile_body_rule_hits"])
        self.assertIn("profile_body_rule_hits", result["null_reasons"])
        self.assertEqual(result["level"], "caution")

    def test_every_lexicon_term_matches_a_sample_of_itself(self):
        for lang, groups in q.HEALTH_LEXICON.items():
            for group, specs in groups.items():
                for label, pattern in specs:
                    with self.subTest(lang=lang, group=group, label=label):
                        self.assertTrue(re.search(pattern, label, re.I), f"{label}: {pattern}")


# ----------------------------------------------------------------------------
# 항목 9 — 주제 적합성
# ----------------------------------------------------------------------------
class TopicFitTest(unittest.TestCase):
    def topic(self, body, **front):
        return analyze(body, **front)["topic_fit"]

    def test_official_primary_source_without_flags_is_core(self):
        url = "https://science.nasa.gov/missions/hubble/x"
        result = self.topic(f"NASA는 [발표]({url})에서 2026년 계획을 밝혔다.\n", source_url=url)
        self.assertEqual(result["fit"], "core")
        self.assertEqual(result["primary_source_category"], "public_agency")

    def test_official_source_but_event_or_press_release_rewrite_is_borderline_with_the_reason(self):
        event = self.topic(EVENT_KO, source_url="https://digital-strategy.ec.europa.eu/en/events/x")
        self.assertEqual(event["fit"], "borderline")
        self.assertTrue(any("행사" in reason for reason in event["reasons"]))
        release = self.topic(f"FTC는 [보도자료]({KO_SOURCE_URL})에서 합의를 발표했다.\n", source_url=KO_SOURCE_URL)
        self.assertEqual(release["fit"], "borderline")
        self.assertTrue(any("보도자료" in reason for reason in release["reasons"]))

    def test_company_only_is_off_and_company_plus_an_official_source_is_borderline(self):
        off = self.topic(f"회사는 [발표]({COMPANY_URL})했다.\n", source_url=COMPANY_URL)
        self.assertEqual(off["fit"], "off")
        mixed = self.topic(f"회사는 [발표]({COMPANY_URL})했다. 공공 [자료](https://www.nasa.gov/a)도 있다.\n", source_url=COMPANY_URL)
        self.assertEqual(mixed["fit"], "borderline")

    def test_unknown_domain_needs_a_human_and_no_address_is_null(self):
        unknown = self.topic("이곳은 [공지](https://something.example.com/a)를 냈다.\n", source_url="https://something.example.com/a")
        self.assertEqual(unknown["fit"], "borderline")
        none = self.topic("출처 없는 글이다.")
        self.assertIsNone(none["fit"])
        self.assertIn("fit", none["null_reasons"])


# ----------------------------------------------------------------------------
# 보고서 — 결정성·null 규약·형식
# ----------------------------------------------------------------------------
def sample_corpus():
    return [make_post(KO_BODY, "2026-11-01-KR-123456.md", lang="ko", source_url=KO_SOURCE_URL),
            make_post("FTC announced a $49.75 million settlement on November 6, 2026.\n\n## Sources\n- [FTC](" + KO_SOURCE_URL + ")\n", "2026-11-01-EN-123456.md",
                      lang="en", source_url=KO_SOURCE_URL),
            make_post(EVENT_KO, "2026-11-02-KR-222222.md", lang="ko", source_url="https://digital-strategy.ec.europa.eu/en/events/x"),
            make_post("출처 없는 혼자 글이다.", "2026-11-03-AI.md", lang="ko", published="false")]


def walk_nulls(node, path=""):
    """측정 항목 묶음 안의 None 이 모두 같은 묶음 null_reasons 에 이유가 있는지 → 이유가 없는 None 의 경로 목록."""
    missing = []
    if isinstance(node, dict):
        reasons = node.get("null_reasons", {}) if isinstance(node.get("null_reasons"), dict) else {}
        for key, value in node.items():
            if value is None and key not in reasons:
                missing.append(f"{path}.{key}")
            elif isinstance(value, (dict, list)):
                missing += walk_nulls(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            missing += walk_nulls(item, f"{path}[{index}]")
    return missing


class ReportTest(unittest.TestCase):
    def test_every_null_in_a_measurement_section_has_a_reason(self):
        report = q.analyze_corpus(sample_corpus(), AS_OF)
        missing = []
        for result in report["posts"]:
            for section in ("claims", "grounding", "sources", "added_value", "press_release_summary", "event_focus", "health_risk", "topic_fit"):
                missing += walk_nulls(result[section], f"{result['path']}.{section}")
            if result["pair"] is None:
                self.assertIn("pair", result["null_reasons"])
        for pair in report["pairs"]:
            missing += walk_nulls(pair, f"pair {pair['pair_key']}")
        self.assertEqual(missing, [])

    def test_same_input_gives_the_same_bytes_and_no_machine_specific_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "posts"
            folder.mkdir()
            for post in sample_corpus():
                (folder / post.rel).write_text(make_text(post.body, **post.front), encoding="utf-8")
            first = q.render_json(q.analyze_corpus(q.collect_posts(folder)[0], AS_OF))
            second = q.render_json(q.analyze_corpus(q.collect_posts(folder)[0], AS_OF))
            self.assertEqual(first, second)
            self.assertNotIn(tmp, first)
            self.assertNotIn(str(Path(tmp).name), first)

    def test_the_json_report_has_the_declaration_the_thresholds_and_a_summary(self):
        report = json.loads(q.render_json(q.analyze_corpus(sample_corpus(), AS_OF)))
        self.assertEqual((report["tool"], report["schema_version"], report["as_of"]), ("quality_shadow", 1, "2026-11-09"))
        self.assertIn("게시와 무관", report["note"])
        for key in ("clone_structure_tolerance", "clone_number_jaccard_min", "clone_length_ratio_band", "event_sentence_ratio_min", "event_distinct_terms_min",
                    "event_title_ratio_min", "health_caution_distinct_min", "small_integer_max"):
            self.assertIn(key, report["thresholds"])
        self.assertEqual(report["summary"]["all"]["posts"], 4)
        self.assertEqual((report["summary"]["published"]["posts"], report["summary"]["private"]["posts"]), (3, 1))
        self.assertEqual(report["summary"]["pairs"], 1)
        self.assertEqual(report["summary"]["unpaired_posts"], 2)
        self.assertIn("grounding.unsupported", report["summary"]["null_counts"])

    def test_the_markdown_report_has_the_sections_and_escapes_external_text(self):
        hostile = make_post("본문이다. 2026년 계획을 밝혔다.", "2026-11-04-KR-333333.md", lang="ko", title="표를 깨는 | 제목 ::error::x <script>")
        report = q.analyze_corpus(sample_corpus() + [hostile], AS_OF)
        text = q.render_markdown(report)
        for heading in ("# 품질 측정 보고서", "## 요약", "## 글별", "## 한·영 짝", "## 측정 불가(null)가 나온 항목 수"):
            self.assertIn(heading, text)
        self.assertIn("게시와 무관", text)
        self.assertNotIn("<script>", text)
        self.assertNotIn("::error::", text)
        rows = [line for line in text.splitlines() if line.startswith("| 2026-11-04-KR-333333.md")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].count("|"), text.splitlines()[text.splitlines().index("## 글별") + 2].count("|"), "표의 칸 수가 어긋났다")

    def test_titles_in_json_are_one_line(self):
        post = make_post("본문이다.", "2026-11-04-KR-333333.md", title="여러 줄 ::notice:: 제목")
        result = q.analyze_post(post, AS_OF)
        self.assertNotIn("::notice", result["title"])


# ----------------------------------------------------------------------------
# 글별 방어(독립 검증 P2) — 글 하나의 예외가 일괄 실행을 멈추지 않는다
# ----------------------------------------------------------------------------
def batch_posts():
    return [make_post("가 문단에서 2026년 계획을 밝혔다.", "2026-11-01-KR-111111.md", lang="ko"),
            make_post("An English paragraph says the plan starts in 2026.", "2026-11-01-EN-111111.md", lang="en"),
            make_post("나 문단에서 2025년 계획을 밝혔다.", "2026-11-02-KR-222222.md", lang="ko")]


class BatchGuardTest(unittest.TestCase):
    FAILING = "2026-11-02-KR-222222.md"

    def failing_on(self, name, error=ValueError("글 내용이 섞인 예외 문구 /abs/path"), rel=None):
        """`q.<name>` 이 `rel`(기본: FAILING) 글에서만 예외를 던지게 바꾼다(다른 글은 원래 함수 그대로)."""
        real = getattr(q, name)
        target = rel or self.FAILING

        def wrapper(first, *args, **kwargs):
            if (first.post.rel if hasattr(first, "post") else first.rel) == target:
                raise error
            return real(first, *args, **kwargs)
        return mock.patch.object(q, name, wrapper)

    def test_an_exception_while_measuring_one_post_is_recorded_and_the_others_are_still_measured(self):
        for error in (ValueError("x"), RecursionError("depth"), KeyError("k"), ZeroDivisionError("z")):
            with self.subTest(error=error.__class__.__name__), self.failing_on("measure_health", error):
                report = q.analyze_corpus(batch_posts(), AS_OF)
                self.assertEqual([r["path"] for r in report["posts"]], ["2026-11-01-KR-111111.md", "2026-11-01-EN-111111.md"])           # 입력 순서 그대로
                self.assertEqual(report["read_problems"], [{"path": self.FAILING, "error": f"분석 중 예외({error.__class__.__name__})"}])
                self.assertEqual(report["summary"]["read_problems"], 1)
                self.assertEqual(report["summary"]["all"]["posts"], 2)
                self.assertEqual(len(report["pairs"]), 1)
                self.assertNotIn("abs/path", q.render_json(report))             # 예외 문구는 싣지 않는다(입력 내용·경로가 섞일 수 있다)

    def test_an_exception_while_preparing_a_post_drops_only_that_post(self):
        with self.failing_on("prepare", TypeError("t")):
            report = q.analyze_corpus(batch_posts(), AS_OF)
        self.assertEqual([item["error"] for item in report["read_problems"]], ["준비 중 예외(TypeError)"])
        self.assertEqual(len(report["posts"]), 2)
        self.assertEqual(len(report["pairs"]), 1)

    def test_when_one_side_of_a_pair_cannot_be_prepared_the_pair_is_dropped_and_the_partner_is_measured_alone(self):
        with self.failing_on("prepare", ValueError("v"), rel="2026-11-01-KR-111111.md"):
            report = q.analyze_corpus(batch_posts(), AS_OF)
        self.assertEqual([item["path"] for item in report["read_problems"]], ["2026-11-01-KR-111111.md"])
        self.assertEqual(report["pairs"], [])                                                      # 한쪽이 없으면 짝도 없다
        partner = next(r for r in report["posts"] if r["path"] == "2026-11-01-EN-111111.md")
        self.assertIsNone(partner["pair"])
        self.assertIn("pair", partner["null_reasons"])

    def test_an_exception_while_comparing_a_pair_omits_the_pair_and_still_measures_both_posts(self):
        with mock.patch.object(q, "pair_metrics", side_effect=ValueError("v")):
            report = q.analyze_corpus(batch_posts(), AS_OF)
        self.assertEqual(report["pairs"], [])
        self.assertEqual(len(report["posts"]), 3)
        self.assertEqual(len(report["read_problems"]), 1)
        self.assertTrue(report["read_problems"][0]["error"].startswith("짝 비교(짝 글 2026-11-01-EN-111111.md) 중 예외(ValueError)"))
        self.assertEqual(report["summary"]["pairs"], 0)

    def test_an_unreadable_original_text_for_one_post_is_recorded_and_the_batch_goes_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = Path(tmp)
            (sources / "2026-11-02-KR-222222.txt").write_bytes(bytes([0xFF, 0xFE, 0x00, 0x80]))
            (sources / "2026-11-01-KR-111111.txt").write_text("The plan starts in 2026.", encoding="utf-8")
            report = q.analyze_corpus(batch_posts(), AS_OF, sources_dir=sources)
        self.assertEqual(len(report["posts"]), 2)
        self.assertEqual(report["read_problems"][0]["path"], self.FAILING)
        self.assertIn("UTF-8", report["read_problems"][0]["error"])
        modes = {r["path"]: r["grounding"]["mode"] for r in report["posts"]}
        self.assertEqual(modes["2026-11-01-KR-111111.md"], "source_text")

    def test_an_interrupt_is_never_swallowed(self):
        with self.failing_on("measure_health", KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                q.analyze_corpus(batch_posts(), AS_OF)

    def test_the_problem_list_is_deterministic_and_keeps_the_read_problems_that_came_in(self):
        incoming = [{"path": "x/깨진.md", "error": "머리말이 없다"}]
        with self.failing_on("measure_health"):
            first = q.render_json(q.analyze_corpus(batch_posts(), AS_OF, problems=incoming))
        with self.failing_on("measure_health"):
            second = q.render_json(q.analyze_corpus(batch_posts(), AS_OF, problems=incoming))
        self.assertEqual(first, second)
        report = json.loads(first)
        self.assertEqual([item["path"] for item in report["read_problems"]], ["x/깨진.md", self.FAILING])
        self.assertEqual(incoming, [{"path": "x/깨진.md", "error": "머리말이 없다"}])           # 받은 목록을 바꾸지 않는다

    def test_the_command_line_writes_the_report_for_the_rest_and_exits_1_with_the_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "posts"
            folder.mkdir()
            for post in batch_posts():
                (folder / post.rel).write_text(make_text(post.body, **post.front), encoding="utf-8")
            out = root / "report.json"
            import contextlib
            import io
            captured = io.StringIO()
            with self.failing_on("measure_health"), contextlib.redirect_stdout(captured), contextlib.redirect_stderr(io.StringIO()):
                code = q.main(["--posts", str(folder), "--as-of", "2026-11-09", "--out", str(out)])
            self.assertEqual(code, 1)
            self.assertIn("글 2편", captured.getvalue())
            self.assertIn("읽기 문제 1건", captured.getvalue())
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual((len(report["posts"]), len(report["read_problems"])), (2, 1))


# ----------------------------------------------------------------------------
# 명령줄
# ----------------------------------------------------------------------------
class CliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.posts = self.root / "posts"
        (self.posts / "분야").mkdir(parents=True)
        for post in sample_corpus():
            (self.posts / "분야" / post.rel).write_text(make_text(post.body, **post.front), encoding="utf-8")

    def run_cli(self, *args):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = q.main(list(args))
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def tree(self):
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))

    def test_as_of_is_required(self):
        code, _, err = self.run_cli("--posts", str(self.posts))
        self.assertEqual(code, 2)
        self.assertIn("--as-of", err)

    def test_an_invalid_as_of_is_a_usage_error(self):
        code, _, err = self.run_cli("--posts", str(self.posts), "--as-of", "2026-13-40")
        self.assertEqual(code, 2)
        self.assertIn("YYYY-MM-DD", err)

    def test_writes_only_the_report_file_and_never_touches_the_posts(self):
        before = self.tree()
        contents = {p: p.read_bytes() for p in self.posts.rglob("*.md")}
        out = self.root / "report.json"
        code, stdout, _ = self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--out", str(out))
        self.assertEqual(code, 0)
        self.assertEqual(sorted(set(self.tree()) - set(before)), ["report.json"])
        self.assertEqual(contents, {p: p.read_bytes() for p in self.posts.rglob("*.md")})
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(len(report["posts"]), 4)
        self.assertIn("report.json", stdout)
        self.assertNotIn(str(self.root), stdout)                     # 절대 경로는 출력하지 않는다

    def test_the_format_follows_the_extension_unless_given(self):
        md = self.root / "report.md"
        self.assertEqual(self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--out", str(md))[0], 0)
        self.assertTrue(md.read_text(encoding="utf-8").startswith("# 품질 측정 보고서"))
        forced = self.root / "report.txt"
        self.assertEqual(self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--out", str(forced), "--format", "md")[0], 0)
        self.assertTrue(forced.read_text(encoding="utf-8").startswith("# 품질 측정 보고서"))
        data = self.root / "report.data"
        self.assertEqual(self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--out", str(data))[0], 0)
        self.assertEqual(json.loads(data.read_text(encoding="utf-8"))["tool"], "quality_shadow")

    def test_without_out_the_report_goes_to_stdout_and_nothing_is_written(self):
        before = self.tree()
        code, stdout, _ = self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["tool"], "quality_shadow")
        self.assertEqual(self.tree(), before)

    def test_an_out_path_inside_the_posts_folder_or_equal_to_the_input_file_is_refused(self):
        before = self.tree()
        code, _, err = self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--out", str(self.posts / "분야" / "report.json"))
        self.assertEqual(code, 2)
        self.assertIn("--out", err)
        self.assertEqual(self.tree(), before)
        single = next(self.posts.rglob("2026-11-03-AI.md"))
        content = single.read_bytes()
        code, _, err = self.run_cli("--posts", str(single), "--as-of", "2026-11-09", "--out", str(single))
        self.assertEqual(code, 2)
        self.assertEqual(single.read_bytes(), content)

    def test_a_missing_parent_folder_is_an_error_and_creates_nothing(self):
        before = self.tree()
        code, _, err = self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--out", str(self.root / "nope" / "report.json"))
        self.assertEqual(code, 2)
        self.assertEqual(self.tree(), before)

    # --- 독립 검증 P1: --out 이 --posts 말고 다른 입력도 덮어쓰지 못한다 ---
    def candidate_and_original(self):
        """글 파일 하나(폴더 cand)와 원문 텍스트(폴더 orig) — 서로 다른 폴더라서 '글 폴더 안' 규칙이 아니라 원문 규칙만 걸린다."""
        (self.root / "cand").mkdir()
        (self.root / "orig").mkdir()
        candidate = self.root / "cand" / "candidate.md"
        candidate.write_text(make_text("FTC는 합의금 4,975만 달러를 발표했다.\n", lang="ko"), encoding="utf-8")
        original = self.root / "orig" / "original.txt"
        original.write_text("The FTC said the settlement is $49.75 million.", encoding="utf-8")
        return candidate, original

    def test_out_may_not_overwrite_the_original_text_file_in_any_spelling(self):
        candidate, original = self.candidate_and_original()
        before_bytes, before_tree = original.read_bytes(), self.tree()
        for out in (original, self.root / "orig" / ".." / "orig" / "original.txt", self.root / "cand" / ".." / "orig" / "." / "original.txt"):
            with self.subTest(out=out.relative_to(self.root).as_posix()):
                code, _, err = self.run_cli("--posts", str(candidate), "--as-of", "2026-11-09", "--source-text", str(original), "--out", str(out))
                self.assertEqual(code, 2)
                self.assertIn("--source-text", err)
                self.assertEqual(original.read_bytes(), before_bytes)
        self.assertEqual(self.tree(), before_tree)

    def test_out_may_not_be_inside_the_sources_folder_and_nothing_there_changes(self):
        sources = self.root / "sources"
        (sources / "sub").mkdir(parents=True)
        original = sources / "2026-11-01-KR-123456.txt"
        original.write_text("The FTC settlement is $49.75 million on November 6, 2026.", encoding="utf-8")
        before_bytes, before_tree = original.read_bytes(), self.tree()
        for out in (original, sources / "new-report.json", sources / "sub" / "report.json", sources / ".." / "sources" / "report.md"):
            with self.subTest(out=out.relative_to(self.root).as_posix()):
                code, _, err = self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--sources-dir", str(sources), "--out", str(out))
                self.assertEqual(code, 2)
                self.assertIn("--sources-dir", err)
        self.assertEqual(original.read_bytes(), before_bytes)
        self.assertEqual(self.tree(), before_tree)

    def test_in_single_post_mode_out_may_not_be_in_the_posts_folder_the_post_lives_in_or_under_a_posts_tree(self):
        single = next(self.posts.rglob("2026-11-03-AI.md"))
        before = self.tree()
        for out in (single.parent / "report.json", single.parent / "report.md", single.parent / "deeper" / "x.json"):
            with self.subTest(out=out.relative_to(self.root).as_posix()):
                code, _, err = self.run_cli("--posts", str(single), "--as-of", "2026-11-09", "--out", str(out))
                self.assertEqual(code, 2)
                self.assertIn("--out", err)
        self.assertEqual(self.tree(), before)
        jekyll = self.root / "_posts" / "분야"                                     # `_posts` 아래에 있는 글이면 `_posts` 전체가 글 폴더다(`.md` 보고서는 글로 발행될 수 있다)
        jekyll.mkdir(parents=True)
        post = jekyll / "2026-11-03-AI.md"
        post.write_text(make_text("혼자 있는 글이다.", lang="ko"), encoding="utf-8")
        before = self.tree()
        for posts_argument in (post, jekyll, self.root / "_posts"):
            for out in (self.root / "_posts" / "report.md", self.root / "_posts" / "분야" / "report.json"):
                with self.subTest(posts=posts_argument.relative_to(self.root).as_posix(), out=out.relative_to(self.root).as_posix()):
                    self.assertEqual(self.run_cli("--posts", str(posts_argument), "--as-of", "2026-11-09", "--out", str(out))[0], 2)
        self.assertEqual(self.tree(), before)
        outside = self.root / "report.json"
        self.assertEqual(self.run_cli("--posts", str(post), "--as-of", "2026-11-09", "--out", str(outside))[0], 0)       # `_posts` 밖이면 된다

    def test_an_existing_folder_or_an_unwritable_place_is_a_usage_error_not_a_traceback(self):
        before = self.tree()
        code, _, err = self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--out", str(self.root))
        self.assertEqual((code, "폴더" in err, "Traceback" in err), (2, True, False))
        blocker = self.root / "blocker.txt"
        blocker.write_text("파일", encoding="utf-8")
        code, _, err = self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--out", str(blocker / "report.json"))
        self.assertEqual((code, "Traceback" in err), (2, False))
        self.assertEqual(sorted(set(self.tree()) - set(before)), ["blocker.txt"])
        denied = PermissionError(13, "Permission denied")
        with mock.patch.object(Path, "write_text", side_effect=denied):
            code, _, err = self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--out", str(self.root / "report.json"))
        self.assertEqual(code, 2)
        self.assertIn("쓸 수 없다", err)
        self.assertNotIn(str(self.root), err)
        with self.assertRaises(q.QualityShadowError):
            q.write_report(self.root, "x")                                           # 이미 있는 폴더를 직접 줘도 설정 오류다

    def test_a_hard_link_to_an_input_file_is_refused_even_under_another_name(self):
        post = next(self.posts.rglob("2026-11-03-AI.md"))
        link = self.root / "alias.md"
        try:
            os.link(post, link)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("이 환경에서는 하드 링크를 만들 수 없다")
        content = post.read_bytes()
        code, _, err = self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--out", str(link))
        self.assertEqual(code, 2)
        self.assertIn("같은 파일", err)
        self.assertEqual(post.read_bytes(), content)
        self.assertEqual(link.read_bytes(), content)

    def test_a_normal_out_path_next_to_the_inputs_but_outside_them_still_works(self):
        out = self.root / "report.json"
        sources = self.root / "sources"
        sources.mkdir()
        code, stdout, _ = self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--sources-dir", str(sources), "--out", str(out))
        self.assertEqual(code, 0)
        self.assertIn("report.json", stdout)
        self.assertTrue(out.is_file())

    def test_a_file_without_front_matter_is_reported_and_the_exit_code_is_1(self):
        (self.posts / "분야" / "broken.md").write_text("머리말 없는 글", encoding="utf-8")
        out = self.root / "report.json"
        code, _, _ = self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--out", str(out))
        self.assertEqual(code, 1)
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["read_problems"][0]["path"], "분야/broken.md")
        self.assertEqual(len(report["posts"]), 4)

    def test_own_domain_must_be_a_domain_name_and_the_count_is_recorded(self):
        for bad in ("https://example.github.io/", "example", "exa mple.org", "example.org/path", ""):
            with self.subTest(value=bad):
                self.assertEqual(self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--own-domain", bad)[0], 2)
        out = self.root / "report.json"
        code, _, _ = self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--own-domain", "Example.github.io", "--own-domain", "other.example.org", "--out", str(out))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["options"], {"own_domain_count": 2, "detail": False})
        self.assertNotIn("example.github.io", out.read_text(encoding="utf-8"))

    def test_a_folder_without_any_post_gives_a_warning_and_exit_code_1_but_still_a_valid_empty_report(self):
        empty = self.root / "empty"
        empty.mkdir()
        out = self.root / "empty.json"
        code, _, err = self.run_cli("--posts", str(empty), "--as-of", "2026-11-09", "--out", str(out))
        self.assertEqual(code, 1)
        self.assertIn("하나도 없다", err)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["posts"], [])

    def test_a_missing_posts_path_and_a_missing_sources_dir_are_usage_errors(self):
        self.assertEqual(self.run_cli("--posts", str(self.root / "nope"), "--as-of", "2026-11-09")[0], 2)
        self.assertEqual(self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--sources-dir", str(self.root / "nope"))[0], 2)

    def test_sources_dir_supplies_original_text_by_file_name_pair_key_or_date_and_key(self):
        sources = self.root / "sources"
        sources.mkdir()
        (sources / "2026-11-01-KR-123456.txt").write_text("The FTC settlement is $49.75 million on November 6, 2026.", encoding="utf-8")
        (sources / "222222.txt").write_text("Nothing about numbers.", encoding="utf-8")
        out = self.root / "report.json"
        self.assertEqual(self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--sources-dir", str(sources), "--out", str(out))[0], 0)
        by_name = {Path(r["path"]).name: r for r in json.loads(out.read_text(encoding="utf-8"))["posts"]}
        self.assertEqual(by_name["2026-11-01-KR-123456.md"]["grounding"]["mode"], "source_text")
        self.assertEqual(by_name["2026-11-02-KR-222222.md"]["grounding"]["mode"], "source_text")
        self.assertEqual(by_name["2026-11-01-EN-123456.md"]["grounding"]["mode"], "inline_link_approx")      # 이 글의 원문 파일은 없다

    def test_source_text_works_for_a_single_candidate_file_and_is_refused_for_a_folder(self):
        single = self.root / "candidate.md"
        single.write_text(make_text("FTC는 합의금 4,975만 달러를 발표했다.\n\n약 4조 2천억 원 규모다.\n", lang="ko"), encoding="utf-8")
        original = self.root / "original.txt"
        original.write_text("The FTC said the settlement is $49.75 million.", encoding="utf-8")
        code, stdout, _ = self.run_cli("--posts", str(single), "--as-of", "2026-11-09", "--source-text", str(original))
        self.assertEqual(code, 0)
        grounding = json.loads(stdout)["posts"][0]["grounding"]
        self.assertEqual((grounding["supported"], grounding["unsupported"]), (1, 1))
        self.assertEqual(self.run_cli("--posts", str(self.posts), "--as-of", "2026-11-09", "--source-text", str(original))[0], 2)

    def test_an_oversized_or_non_utf8_original_is_a_read_error_not_a_crash(self):
        bad = self.root / "bad.txt"
        bad.write_bytes(bytes([0xFF, 0xFE, 0x00, 0x80]))
        single = self.root / "candidate.md"
        single.write_text(make_text("본문이다.", lang="ko"), encoding="utf-8")
        code, _, err = self.run_cli("--posts", str(single), "--as-of", "2026-11-09", "--source-text", str(bad))
        self.assertEqual(code, 2)
        self.assertIn("UTF-8", err)


# ----------------------------------------------------------------------------
# 가장자리 경우 — 덜 쓰이는 분기도 정의대로 움직인다
# ----------------------------------------------------------------------------
class EdgeCasesTest(unittest.TestCase):
    def test_language_falls_back_to_the_file_name_kind_and_empty_text_has_none(self):
        self.assertEqual(q._lang_from({}, "KR", "x"), "ko")
        self.assertEqual(q._lang_from({}, "EN", "x"), "en")
        self.assertEqual(q._lang_from({}, "", ""), "")
        self.assertEqual(q._lang_from({}, "", "12345 !!!"), "")
        self.assertEqual(q._lang_from({"lang": "EN"}, "KR", "한국어"), "en")          # 머리말이 파일 이름보다 우선

    def test_unreadable_or_oversized_files_are_read_errors_not_crashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = Path(tmp) / "big.txt"
            big.write_text("가" * 100, encoding="utf-8")
            with mock.patch.object(q, "MAX_TEXT_BYTES", 10):
                with self.assertRaises(q.PostReadError):
                    q.read_text_file(big)
            with self.assertRaises(q.PostReadError):
                q.read_text_file(Path(tmp))                                           # 폴더를 파일로 읽을 수 없다

    def test_a_paragraph_after_the_sources_list_is_a_note_and_not_body_text(self):
        zones = q.split_zones("본문.\n\n## Sources\n- [A](https://a.example.org/x)\n\n출처 뒤의 설명 문단이다 2026년.\n")
        self.assertEqual(zones.main, ["본문."])
        self.assertEqual(zones.notice_lines, ["출처 뒤의 설명 문단이다 2026년."])

    def test_a_wrapped_list_item_is_one_item_and_numbers_zero_has_a_key(self):
        blocks = q.build_blocks(["- 항목 하나가 길어서", "  다음 줄로 이어진다", "- 둘째 항목"])
        self.assertEqual([(b.kind, b.raw) for b in blocks], [("list", "항목 하나가 길어서 다음 줄로 이어진다"), ("list", "둘째 항목")])
        self.assertEqual(q.numeric_key(0.0), "0")

    def test_a_year_or_a_month_is_supported_by_the_originals_dates_and_a_made_up_name_is_not(self):
        source = "The meeting was held in November 2026 under the Commission."
        self.assertEqual(analyze("2026년 회의가 있었다고 한다 2026.", source_text=source)["grounding"]["supported"], 1)        # 연도 2026 은 원문의 날짜에도 있다
        self.assertEqual(analyze("2026년 11월 회의가 있었다고 한다.", source_text=source)["grounding"]["supported"], 1)          # 월 단위 날짜
        self.assertEqual(analyze("2026년 12월 회의가 있었다고 한다.", source_text=source)["grounding"]["unsupported"], 1)
        invented = analyze("Zorblax Industries announced a plan.", "2026-11-01-EN-123456.md", lang="en", source_text=source)["grounding"]
        self.assertEqual((invented["supported"], invented["unsupported"]), (0, 1))                                             # 원문에 없는 이름

    def test_a_company_only_event_post_says_both_reasons(self):
        topic = analyze(EVENT_KO, source_url=COMPANY_URL)["topic_fit"]
        self.assertEqual(topic["fit"], "off")
        self.assertTrue(any("행사" in reason for reason in topic["reasons"]))

    def test_the_pair_length_ratio_is_null_when_the_korean_body_is_empty(self):
        result = pair_of("", synth("en"))
        self.assertIsNone(result["length_ratio_en_per_ko"])
        self.assertIn("length_ratio_en_per_ko", result["null_reasons"])
        self.assertFalse(result["translation_clone_suspected"])

    def test_markdown_shows_original_text_results_the_empty_null_list_and_read_problems(self):
        post = make_post("FTC는 합의금 4,975만 달러를 발표했다.", "2026-11-01-KR-123456.md", lang="ko", source_url="https://www.ftc.gov/a")
        report = q.analyze_corpus([post], AS_OF, single_source_text="The FTC said $49.75 million.", problems=[{"path": "x/깨진.md", "error": "머리말이 없다"}])
        text = q.render_markdown(report)
        self.assertIn("원문 대조 지지 1", text)
        self.assertIn("## 읽거나 분석하지 못한 파일", text)
        self.assertIn("깨진.md", text)
        clean = q.analyze_corpus([make_post("FTC는 합의금 4,975만 달러를 발표했다.", "2026-11-01-KR-123456.md", lang="ko", source_url="https://www.ftc.gov/a")], AS_OF,
                                 single_source_text="The FTC said $49.75 million.")
        clean["summary"]["null_counts"] = {}
        self.assertIn("- 없음", q.render_markdown(clean))

    def test_running_the_module_with_dash_m_works_and_reports_usage_errors_with_exit_code_2(self):
        import subprocess
        import sys
        env = dict(__import__("os").environ, PYTHONUTF8="1")
        helped = subprocess.run([sys.executable, "-X", "utf8", "-B", "-m", "pipeline.quality_shadow", "--help"], cwd=str(Path(q.__file__).resolve().parent.parent),
                                capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(helped.returncode, 0)
        self.assertIn("--as-of", helped.stdout)
        failed = subprocess.run([sys.executable, "-X", "utf8", "-B", "-m", "pipeline.quality_shadow", "--posts", "no-such-folder", "--as-of", "2026-11-09"],
                                cwd=str(Path(q.__file__).resolve().parent.parent), capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(failed.returncode, 2)
        self.assertIn("오류", failed.stderr)


# ----------------------------------------------------------------------------
# 정규식 최악 모양 시간(R5) — 닫히지 않는 표시·긴 반복에서 수 초가 걸리지 않는다
# ----------------------------------------------------------------------------
class PathologicalInputTest(unittest.TestCase):
    SHAPES = {"open brackets": "[" * 4000 + "x", "open autolinks": "<http://" * 500, "open bold": "**" * 2500 + "x", "long hangul": "가" * 4000,
              "digits and commas": "1," * 2500, "hash heading": "# " + " #" * 2000 + "x", "capitalized run": "Aa " * 1500, "open parens": "(" * 4000 + "https://a.b/c",
              "bold label": "**" + "가" * 4000, "table pipes": "|" * 4000, "quotes": "“" * 2000 + "x", "dates": "11월 3일 " * 800, "backticks": "`" * 4000}

    def test_each_shape_is_analyzed_quickly_and_without_error(self):
        for name, shape in self.SHAPES.items():
            with self.subTest(shape=name):
                body = shape + "\n\n" + shape[:300] + "\n"
                started = time.monotonic()
                result = analyze(body)
                self.assertLess(time.monotonic() - started, 5.0, name)
                self.assertIn("claims", result)


# ----------------------------------------------------------------------------
# 시간이 걸릴 수 있는 시나리오는 자식 프로세스에서 제한 시간을 걸어 돌린다 — 회귀로 정규식이 폭주해도 시험 전체가 멈추지 않고 그 시험만 제한 시간에 실패한다.
# ----------------------------------------------------------------------------
def whitespace_run_lines():
    """공백·탭 연속이 길게 이어진 줄 모양(독립 검증 P3: 제목 정규식이 3차 역추적이던 모양과 같은 계열)."""
    return {"heading and spaces": "# a" + " " * 4000 + "x", "heading and tabs": "# a" + "\t" * 4000 + "x", "hash only": "#" + " " * 4000 + "x",
            "closing hashes": "# a " + "# " * 1900 + "x", "bold label and spaces": "**a**" + " " * 4000 + "x", "bold label colon spaces": "**a**:" + " " * 4000 + "x",
            "sources heading and spaces": "## 출처" + " " * 4000 + "x", "heading and stars": "# " + "* " * 1900 + "x"}


def date_paragraph(lines=240, units_per_line=67):
    """날짜가 아주 많은 한 단락 — 줄은 469자(줄 상한 5,000자 안)이고 빈 줄이 없어 한 문단으로 합쳐진다. 약 112 KB, 날짜 16,080개."""
    return "\n".join(["11월 3일 " * units_per_line] * lines)


def source_text_with_many_dates(copies=16000):
    return " and ".join(f"on November {1 + index % 28}, 2026 item {index}" for index in range(copies))


def child_main(scenario):
    """자식 프로세스 진입점: 시나리오 하나를 돌려 걸린 시간(초)을 한 줄로 찍는다."""
    started = time.monotonic()
    if scenario == "whitespace-runs":
        per_shape = {}
        for name, line in whitespace_run_lines().items():
            shape_started = time.monotonic()
            analyze(line + "\n\n" + line[:300] + "\n")
            per_shape[name] = round(time.monotonic() - shape_started, 3)
        print(json.dumps(per_shape))
        return
    elif scenario == "linear-helpers":
        # 줄 상한(5,000자) 밖의 5만 자 공백 연속을 제목·굵은 글씨 도우미에 직접 준다 — 제곱 시간이면 수십 초가 걸려 제한 시간에 걸린다
        run = " " * 50000

        calls = {"heading_text": lambda: q.heading_text("# a" + run + "x"), "plain_title": lambda: q._plain_title(run + "x" + run + "y"),
                 "bold label regex": lambda: q._BOLD_ONLY_RE.match("**a**" + run + "x"), "bold label colon regex": lambda: q._BOLD_ONLY_RE.match("**a**:" + run + "x"),
                 "sources heading": lambda: q.is_sources_heading("## 출처" + run + "x"), "image credit heading": lambda: q._is_image_credit_heading("## 이미지 출처" + run + "x"),
                 "bold sources label": lambda: q.is_sources_heading("**Sources**" + run + "x"),
                 "credit start regex": lambda: q._CREDIT_START_RE.match(run + "x"), "credit start regex with stars": lambda: q._CREDIT_START_RE.match("*" + run + "x"),
                 "table separator regex": lambda: q._TABLE_SEPARATOR_RE.match(run + "x"), "table separator regex with pipe": lambda: q._TABLE_SEPARATOR_RE.match("|" + run + "x"),
                 "citation regex": lambda: q._CITATION_RE.match((run + "x").lstrip()), "host with 50000 labels": lambda: q.classify_host("." * 50000 + "x"),
                 "registrable domain of 50000 labels": lambda: q.registrable_domain("." * 50000 + "x")}
        per_call = {}
        for name, call in calls.items():
            call_started = time.monotonic()
            call()
            per_call[name] = round(time.monotonic() - call_started, 3)
        print(json.dumps(per_call))
        return
    elif scenario == "whitespace-lines":
        # 공백·탭이 길게 이어진 줄을 여러 개 이어 붙인 글(앞 표지: 없음·표 줄·크레딧 줄) — 줄마다 0.2초씩 걸리던 겹친 `\s*` 정규식이 회귀하면 수십 초가 된다
        lines = [" " * 4000 + "x", "\t" * 4000 + "x", "|" + " " * 4000 + "x", "* " + " " * 4000 + "photo by", "*" + " " * 4000 + "x"]
        analyze("\n\n".join(lines * 50))
    elif scenario == "digit-runs":
        # 줄 상한(5,000자) 길이의 숫자 연속 40줄 — 빌려 쓰는 국문 용량 규칙(`\d+ … mg`)이 제곱 시간이면 줄마다 1초 이상이다(독립 재탐색)
        body = "\n\n".join(["1" * 5000] * 40) + "\n\n이 제품은 " + "9" * 4900 + "mg 을 담았다.\n"                 # 마지막 줄은 줄 상한(5,000자) 안이라 mg 가 잘리지 않는다
        result = analyze(body)
        assert result["health_risk"]["profile_body_rule_hits"], "용량 규칙이 숫자 연속 뒤의 mg 를 못 찾았다"
    elif scenario == "date-paragraph":
        result = analyze(date_paragraph())
        assert result["claims"]["total"] >= 1
    elif scenario == "source-text-dates":
        text = source_text_with_many_dates()
        assert len(text) > 400000
        result = analyze("FTC는 2026년 11월 6일 합의금 4,975만 달러를 발표했다.\n", source_text=text)
        assert result["grounding"]["mode"] == "source_text"
    else:
        raise SystemExit(f"알 수 없는 시나리오: {scenario}")
    print(f"{time.monotonic() - started:.3f}")


def seconds_in_child(scenario, timeout=60):
    """시나리오를 자식 프로세스에서 돌려 걸린 시간(초)을 돌려준다. 제한 시간을 넘기면 None."""
    root = Path(q.__file__).resolve().parent.parent
    env = dict(os.environ, PYTHONUTF8="1", PYTHONPATH=os.pathsep.join([str(root), str(root / "tests")]))
    try:
        done = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", f"import test_quality_shadow as t; t.child_main({scenario!r})"], cwd=str(root), env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    if done.returncode != 0:
        raise AssertionError(f"{scenario}: 자식 프로세스가 실패했다: {done.stderr[-400:]}")
    return float(done.stdout.strip().splitlines()[-1])


class WhitespaceRunTest(unittest.TestCase):
    def test_a_whole_post_with_a_4000_character_whitespace_run_is_analyzed_within_a_second_per_shape(self):
        """모양마다 글 전체 분석이 1초 안(독립 검증 P3: 옛 제목 정규식은 공백 3,000칸 한 줄에 56초, 4,000칸이면 2분이 넘는다). 정규식이 회귀해도
        시험 전체가 멈추지 않도록 자식 프로세스에서 제한 시간(60초)을 걸고 모양별 시간을 받는다."""
        root = Path(q.__file__).resolve().parent.parent
        env = dict(os.environ, PYTHONUTF8="1", PYTHONPATH=os.pathsep.join([str(root), str(root / "tests")]))
        try:
            done = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", "import test_quality_shadow as t; t.child_main('whitespace-runs')"], cwd=str(root), env=env,
                                  capture_output=True, text=True, encoding="utf-8", timeout=60)
        except subprocess.TimeoutExpired:
            self.fail("공백 연속 줄 모양이 60초 안에 끝나지 않았다 — 정규식 역추적을 의심한다")
        self.assertEqual(done.returncode, 0, done.stderr[-400:])
        per_shape = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual(sorted(per_shape), sorted(whitespace_run_lines()))
        for name, seconds in per_shape.items():
            with self.subTest(shape=name):
                self.assertLess(seconds, 1.0, name)

    def test_the_title_helpers_stay_linear_on_50000_character_whitespace_runs(self):
        """줄 상한 안(4,000칸)에서는 제곱 시간도 0.4초라 위 시험에 안 걸린다 — 상한 밖의 5만 칸을 직접 주어 제곱·3차 회귀를 잡는다."""
        root = Path(q.__file__).resolve().parent.parent
        env = dict(os.environ, PYTHONUTF8="1", PYTHONPATH=os.pathsep.join([str(root), str(root / "tests")]))
        try:
            done = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", "import test_quality_shadow as t; t.child_main('linear-helpers')"], cwd=str(root), env=env,
                                  capture_output=True, text=True, encoding="utf-8", timeout=60)
        except subprocess.TimeoutExpired:
            self.fail("5만 칸 공백 연속이 60초 안에 끝나지 않았다 — 제목·굵은 글씨 도우미가 입력 길이의 제곱 이상으로 느려졌다")
        self.assertEqual(done.returncode, 0, done.stderr[-400:])
        per_call = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual(len(per_call), 14)
        for name, seconds in per_call.items():
            with self.subTest(call=name):
                self.assertLess(seconds, 1.0, name)

    def test_250_lines_of_long_whitespace_runs_are_analyzed_within_the_limit(self):
        elapsed = seconds_in_child("whitespace-lines", timeout=60)
        self.assertIsNotNone(elapsed, "공백이 길게 이어진 줄 250개가 60초 안에 끝나지 않았다 — 크레딧·표 구분선·인용 줄 정규식이 공백 길이의 제곱 시간이 된다")
        self.assertLess(elapsed, 5.0)

    OLD_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
    OLD_CREDIT_START = re.compile(r"^\s*[*_]*\s*(?:photo\s+by|image\s+by|photo\s*:|사진\s*[:：]?|이미지\s*[:：]?)", re.I)
    OLD_CITATION = re.compile(r"^\s*(?:[“\"].*(?:<https?://|Source:)|Adapted from\b|.*Contains public sector information)")

    def test_the_rewritten_line_regexes_accept_exactly_the_lines_the_old_ones_did(self):
        """제곱 시간을 없애려고 다시 쓴 세 줄 정규식이 받아들이는 줄은 옛 정규식과 같다(작은 문자열 전수 + 예문)."""
        import itertools
        for length in range(0, 7):
            for combo in itertools.product((" ", "|", ":", "-", "x", "\t"), repeat=length):
                text = "".join(combo)
                self.assertEqual(bool(self.OLD_TABLE_SEPARATOR.match(text)), bool(q._TABLE_SEPARATOR_RE.match(text)), repr(text))
        credit_words = ("photo by", "Photo  By", "image by", "photo:", "photo :", "사진", "사진:", "이미지", "이미지 ：", "x", "photographer")
        for length in range(0, 4):
            for combo in itertools.product((" ", "*", "_", "\t", "photo by", "사진", ":", "x"), repeat=length):
                for word in credit_words:
                    text = "".join(combo) + word
                    self.assertEqual(bool(self.OLD_CREDIT_START.match(text)), bool(q._CREDIT_START_RE.match(text)), repr(text))
        for text in ("“제목.” Source: Agency <https://a.example.org/x>", '"Title." Agency <http://x.org>', "Adapted from the report", "  Adapted from the report", "\tAdapted from x",
                     "Contains public sector information licensed", "  text Contains public sector information", "일반 문장", "  “인용” 만 있다", "", "   ", "adapted from x", "Adapted fromx"):
            self.assertEqual(bool(self.OLD_CITATION.match(text)), bool(q._CITATION_RE.match(text.lstrip())), repr(text))
        for separator in ("|---|---|", "---|---", ":--|--:", "| --- |", "--", " |:--:|:--|", "|---|---|   "):
            self.assertTrue(q._TABLE_SEPARATOR_RE.match(separator), separator)
        for not_separator in ("|-|", "abc", "| a |", "-", "|", "|---|x|"):
            self.assertFalse(q._TABLE_SEPARATOR_RE.match(not_separator), not_separator)
        # 인용 줄 정규식은 앞 공백을 뗀 글을 받는다는 계약: 앞 공백을 정규식(`^\s*`)에 맡기면 공백이 긴 줄에서 `.*` 와 겹쳐 제곱 시간이 된다 — 부르는 쪽이 lstrip 한다
        self.assertTrue(q._CITATION_RE.match("Adapted from the report"))
        self.assertIsNone(q._CITATION_RE.match("  Adapted from the report"))
        self.assertIsNone(q._CITATION_RE.match("\t“제목.” Source: A <https://a.example.org/x>"))
        zones = q.split_zones("본문.\n\n  *Photo by [N](https://unsplash.com/@n) on Unsplash*\n\n  \"제목.\" Source: A <https://a.example.org/x>\n")
        self.assertEqual((len(zones.credit_lines), len(zones.citation_lines), zones.main), (1, 1, ["본문."]))        # 앞 공백이 있는 크레딧·인용 줄도 그대로 가려낸다

    def test_a_host_with_thousands_of_labels_is_classified_quickly_and_normal_hosts_keep_their_rule(self):
        started = time.monotonic()
        self.assertEqual(q.classify_host("." * 5000 + "x")[0], "unknown")
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(q.classify_host("a.b.c.d.e.f.g.h.i.nasa.gov")[:1] + (q.classify_host("a.b.c.d.e.f.g.h.i.nasa.gov")[2],), ("public_agency", "nasa.gov"))
        self.assertEqual(q.classify_host("news.bbc.co.uk")[2], "bbc.co.uk")
        self.assertEqual(q.classify_host("x.spectrum.ieee.org")[2], "spectrum.ieee.org")
        self.assertEqual(len(q._suffix_candidates("a." * 100 + "nasa.gov")), q.MAX_RULE_LABELS)

    def test_the_analysis_of_those_shapes_still_returns_every_section(self):
        for name, line in whitespace_run_lines().items():
            with self.subTest(shape=name):
                self.assertIn("claims", analyze(line[:600] + "\n\n" + line[:300] + "\n"))

    def test_heading_text_keeps_the_old_meaning_of_the_heading_line(self):
        cases = {"## 제목": "제목", "## 제목 ##": "제목", "##   제목   ###   ": "제목", "# C#": "C", "#\t탭 제목": "탭 제목", "   ### 들여쓴 제목": "들여쓴 제목",
                 "# ": "", "#     ": "", "# #": "", "###### 여섯": "여섯", "# a # b": "a # b"}
        for line, expected in cases.items():
            with self.subTest(line=line):
                self.assertEqual(q.heading_text(line), expected)
        for not_heading in ("#", "#제목", "####### 일곱", "    # 네 칸 들여쓰기", "본문 # 중간", "", "- # 목록"):
            with self.subTest(not_heading=not_heading):
                self.assertIsNone(q.heading_text(not_heading))

    def test_titles_and_bold_labels_with_trailing_marks_are_still_recognized_as_sources_headings(self):
        for line in ("## 출처 ##", "**Sources:**   ", "**출처** :", "**Source**：  ", "### Sources ###   ", "##\t출처\t"):
            with self.subTest(line=line):
                self.assertTrue(q.is_sources_heading(line), line)
        for line in ("**출처 아님 문장**이다", "## 출처를 밝힌다", "**a** x"):
            with self.subTest(line=line):
                self.assertFalse(q.is_sources_heading(line), line)


# ----------------------------------------------------------------------------
# 고정 시드 퍼징(독립 검증 P2: 퍼징 재료에 `[`·`]` 가 든 깨진 주소를 넣는다) — 글별 방어가 예외를 삼켜 숨기지 않도록 read_problems 가 비어 있음을 본다.
# ----------------------------------------------------------------------------
FUZZ_FRAGMENTS = (
    "[자료](http://[abc/x)", "<http://[abc>", "http://]x/y", "https://[::1/x", "![그림](http://[abc/x.png)", "[a](https://www.nasa.gov/a)", "[b](https://www.pewresearch.org/x?ref=1&utm_source=2)",
    "https://[fe80::1%25eth0/x", "[](http://[)", "NASA는 2026년 10월 1일 발표했다.", "3월 20개 사업", "6월 30% 증가", "1월 31% 42% 27%", "1월 1일–10월 24일", "11월 3–5일", "12월 28일–1월 3일",
    "November 9, 2026", "Jan 1 - Oct 24", "2026-11-06", "2026년 11월", "$5M", "€3.5B", "$300K", "3.5GHz", "12,246kg", "100MW", "155mm", "1.8m", "약5%", "총3명", "연2회", "월10만원",
    "코로나19", "제10조", "5G", "G20", "21st", "3M", "4K", "3.5.2", "3.5xyz", "# 제목 ##", "##   ", "## 출처", "**Sources:**", "- [항목](https://x.example.org/a)", "| a | b |", "|---|---|",
    "| 1월 | 31% |", "**굵게**", "> 인용 2026년", "“따옴표 4,975만 달러.”", "한글 English 混合 日本語", "​", "﻿", "　", "…", " " * 300, "\t" * 50, "가" * 200, "A" * 80,
    "1" * 30, "9" * 17 + "." + "9" * 17, "[", "]", "(", ")", "`", "**", "*", "_", "<", ">", "|", "\\", "\n\n", "\n", " ", "FTC", "The Federal Trade Commission", "연방거래위원회", "진단", "medical", "행사 개최 참가")
FUZZ_URLS = ("", "http://[abc/x", "https://www.nasa.gov/a", "https://[::1/x", "http://]x/", "https://onepredict.ai/news/?bmode=view&idx=1", "not a url", "https://example.org/a?ref=1")


class SeededFuzzTest(unittest.TestCase):
    @staticmethod
    def random_body(rng):
        return "".join(rng.choice(FUZZ_FRAGMENTS) + rng.choice(("", " ", "\n", "\n\n")) for _ in range(rng.randint(3, 25)))

    def test_random_combinations_never_raise_and_never_hide_an_exception_in_read_problems(self):
        rng = random.Random(20261109)
        for index in range(260):
            body = self.random_body(rng)
            url = rng.choice(FUZZ_URLS)
            post = make_post(body, f"2026-11-{1 + index % 28:02d}-KR-{index:06d}.md", lang="ko", source_url=url or None)
            report = q.analyze_corpus([post], AS_OF, own_domains=["x.y"] if index % 3 == 0 else [], detail=(index % 5 == 0))
            self.assertEqual(report["read_problems"], [], (index, body[:160], url))
            self.assertEqual(len(report["posts"]), 1)
            json.loads(q.render_json(report))
            self.assertIn("## 글별", q.render_markdown(report))

    def test_random_korean_english_pairs_with_odd_addresses_never_raise(self):
        rng = random.Random(1109)
        for index in range(60):
            ko = make_post(self.random_body(rng), f"2026-11-02-KR-{index:06d}.md", lang="ko", source_url=rng.choice(FUZZ_URLS) or None)
            en = make_post(self.random_body(rng), f"2026-11-02-EN-{index:06d}.md", lang="en", source_url=rng.choice(FUZZ_URLS) or None)
            report = q.analyze_corpus([ko, en], AS_OF)
            self.assertEqual(report["read_problems"], [], index)
            self.assertEqual(len(report["pairs"]), 1)
            pair = report["pairs"][0]
            self.assertIn(pair["translation_clone_suspected"], (True, False, None))
            self.assertEqual(walk_nulls(pair), [])

    def test_the_same_random_input_gives_byte_identical_json(self):
        rng = random.Random(7)
        posts = [make_post(self.random_body(rng), f"2026-11-0{1 + index % 9}-KR-{index:06d}.md", lang="ko", source_url=rng.choice(FUZZ_URLS) or None) for index in range(40)]
        self.assertEqual(q.render_json(q.analyze_corpus(posts, AS_OF)), q.render_json(q.analyze_corpus(posts, AS_OF)))


# ----------------------------------------------------------------------------
# 날짜가 많은 큰 입력(독립 검증 P8) — 구간을 정렬해 한 번에 이어 붙이고 겹침 검사가 날짜 수에 비례해 느려지지 않는다.
# 상한은 느슨하다(옛 코드는 같은 입력에 38초·27초였고 지금은 1–2초·0.5초 안팎).
# ----------------------------------------------------------------------------
class ProfileRuleDigitRunTest(unittest.TestCase):
    """독립 재탐색: 빌려 쓰는 국문 프로필의 용량 규칙(`\\d+(?:\\.\\d+)?\\s?(?:mg|mcg|μg|iu)`)은 숫자가 길게 이어지면 연속 길이의 제곱 시간이다 —
    이 도구는 그 규칙에 넘기는 글에서 20자리를 넘는 숫자 연속만 줄인다(규칙 파일은 고치지 않는다)."""

    def test_digit_runs_longer_than_twenty_are_clipped_and_shorter_ones_are_kept(self):
        self.assertEqual(q._clip_digit_runs("a" + "1" * 25 + "b" + "2" * 20 + "c" + "3" * 21), "a" + "1" * 20 + "b" + "2" * 20 + "c" + "3" * 20)
        self.assertEqual(q._clip_digit_runs("약 5%와 1,234,567명 그리고 2026년"), "약 5%와 1,234,567명 그리고 2026년")
        self.assertEqual(q._clip_digit_runs(chr(0x663) * 30), chr(0x663) * 20)                 # 아랍 인도 숫자도 `\\d` 라서 같이 줄인다(프로필 규칙의 `\\d` 와 같은 집합)
        self.assertEqual(q._clip_digit_runs(""), "")

    def test_the_profile_rules_find_the_same_rule_with_and_without_clipping(self):
        for lang in ("ko", "en"):
            _, profile, _ = q._load_health_profile(lang)
            for digits in (25, 100, 300):
                for tail in ("mg 을 담았다", " mg of it", "개를 샀다", " units", "mcg", "IU"):
                    text = "이 제품은 " + "9" * digits + tail
                    with self.subTest(lang=lang, digits=digits, tail=tail):
                        self.assertEqual(q.gates.body_risk_hit(q._clip_digit_runs(text), profile)[0], q.gates.body_risk_hit(text, profile)[0])
                        self.assertEqual(q.gates.first_match(profile["banned_patterns"], q._clip_digit_runs(text))[0], q.gates.first_match(profile["banned_patterns"], text)[0])

    def test_the_dosage_rule_still_matches_a_number_with_a_unit_after_a_very_long_digit_run(self):
        result = analyze("이 제품은 " + "9" * 4000 + "mg 을 담았다.")["health_risk"]
        self.assertEqual(len(result["profile_body_rule_hits"]), 1)
        self.assertIn("mg", result["profile_body_rule_hits"][0]["pattern"])
        plain = analyze("이 제품은 " + "9" * 4000 + "개를 담았다.")["health_risk"]
        self.assertEqual(plain["profile_body_rule_hits"], [])

    def test_forty_lines_of_5000_digits_are_analyzed_within_the_limit(self):
        elapsed = seconds_in_child("digit-runs", timeout=60)
        self.assertIsNotNone(elapsed, "5,000자리 숫자 줄 40개가 60초 안에 끝나지 않았다 — 프로필 용량 규칙이 숫자 연속에서 제곱 시간이 된다")
        self.assertLess(elapsed, 5.0)


class LargeDateInputTest(unittest.TestCase):
    def test_a_112kb_paragraph_with_16000_dates_is_analyzed_within_the_limit(self):
        elapsed = seconds_in_child("date-paragraph", timeout=90)
        self.assertIsNotNone(elapsed, "날짜 16,080개가 든 112 KB 단락이 90초 안에 끝나지 않았다 — 날짜 수에 제곱으로 느려지는 곳을 의심한다")
        self.assertLess(elapsed, 12.0)

    def test_a_550kb_original_text_with_16000_dates_is_indexed_within_the_limit(self):
        elapsed = seconds_in_child("source-text-dates", timeout=90)
        self.assertIsNotNone(elapsed, "날짜 16,000개가 든 원문 텍스트가 90초 안에 끝나지 않았다 — 날짜 수에 제곱으로 느려지는 곳을 의심한다")
        self.assertLess(elapsed, 12.0)

    def test_blanking_spans_in_one_pass_equals_blanking_them_one_by_one(self):
        def one_by_one(text, spans):
            for start, end in sorted(spans, reverse=True):
                text = text[:start] + " " * (end - start) + text[end:]
            return text
        text = "abc 11월 3일 def 2026-11-06 ghi 11월 4일"
        for spans in ([], [(4, 10)], [(15, 25), (4, 10)], [(0, 3), (3, 4)], [(0, len(text))], [(4, 10), (15, 25), (30, len(text))]):
            with self.subTest(spans=spans):
                self.assertEqual(q._blank_spans(text, spans), one_by_one(text, spans))
                self.assertEqual(len(q._blank_spans(text, spans)), len(text))
        self.assertEqual(q._blank_spans(text, [(4, 10), (6, 12)]), q._blank_spans(text, [(4, 10)]))      # 겹친 구간은 먼저 온 것이 이긴다(날짜 구간은 원래 겹치지 않는다)

    def test_dates_found_in_a_large_text_are_the_same_as_in_its_pieces(self):
        piece = "회의는 2026년 11월 3일에 열리고 11월 5일에 끝나며 November 9, 2026 에 보고한다. "
        whole = piece * 300
        ref = datetime.date(2026, 11, 1)
        found = q.find_dates(whole, ref)
        self.assertEqual(len(found), 900)
        self.assertEqual([m.text for m in found[:3]], [m.text for m in q.find_dates(piece, ref)])
        self.assertTrue(all(found[i].span[1] <= found[i + 1].span[0] for i in range(len(found) - 1)), "날짜 구간은 겹치지 않고 위치 순이다")


if __name__ == "__main__":
    unittest.main()
