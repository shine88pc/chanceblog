"""독립 검증(2026-11-09)이 찾은 구멍을 막은 Gate 동작의 회귀 시험. 문제 번호는 검증 보고서(gatev/verification.md)와 수정 지시서(GATEFIX_BRIEF.md)의 번호다.

 3 출처 표지 하나가 그 뒤 글 전체를 검사 밖으로 빼던 것 · 4 입력 상한·정규식 속도 · 5 인용·직함 사각 · 6 숫자 종류 · 15 QG7 주소 정규화 · 17 QG3-LINK 정의
 1·2 건강 C 와 상담 문구 면제 · 13 시험의 공백(경계값을 못박는다). 순수 모듈이라 네트워크·파일 없이 돈다. 기관·사람 이름은 모두 지어낸 것이다.
"""
import datetime
import itertools
import time
import unittest
from decimal import Decimal
from unittest import mock

import _bootstrap  # noqa: F401
import quality_gate_helpers as h
from pipeline import quality_gate as qg

LINK = h.LINK
AS_OF = h.AS_OF
EVIDENCE_SOURCE = h.fixture_source()


def codes(holds):
    return [hold.code for hold in holds]


def gate_codes(ko_body, **kw):
    """국문 본문(머리말 앞의 글)을 후보로 넣어 Gate 전체를 돌린 보류 코드 목록(국문만)."""
    config = h.make_config(("ko",))
    return h.run_gate(data=h.make_data(ko=ko_body), config=config, **kw).codes()


def plain(n):
    """분량 채우기용 평범한 국문(숫자·건강·행사 낱말이 없다). 공백 제외 약 n 자."""
    unit = "이 문단은 설명을 이어 가기 위한 평범한 문장으로 구성되어 있으며 독자가 맥락을 이해하도록 돕습니다. "
    out = ""
    while len(out.replace(" ", "")) < n:
        out += unit
    return out.strip()


# ----------------------------------------------------------------------------------------------------------------------------------
# 문제 3: 출처 표지 한 줄이 그 뒤 글 전체를 검사 밖으로 빼지 못한다
# ----------------------------------------------------------------------------------------------------------------------------------
class StoryAndTailTest(unittest.TestCase):
    BAD_TAIL = "이 영양제를 먹으면 당뇨가 반드시 완치됩니다. 매출은 9,999억 원이었고 사망자는 77,777명이었다."

    def test_a_marker_like_line_in_the_middle_does_not_cut_the_text_after_it(self):
        body = f"{plain(1100)}\n\n| 구분 | 값 |\n|---|---|\n| 가 | 나 |\n\n출처: 통계청\n\n{plain(900)}\n\n{self.BAD_TAIL}\n\n[원문]({LINK})"
        parts = qg.split_story(body)
        self.assertEqual((parts.story, parts.block, parts.tail), (body, "", ""))                    # 글 전체가 본문이다
        self.assertEqual(qg.story_of(body), body)

    def test_the_text_after_a_mid_body_marker_is_scanned_by_every_rule(self):
        for marker in ("출처: 통계청", "## 참고 자료", "Sources: Agency", "**출처**"):
            with self.subTest(marker=marker):
                body = f"{plain(1100)}\n\n{marker}\n\n{plain(900)}\n\n{self.BAD_TAIL}\n\n[원문]({LINK})"
                found = gate_codes(body)
                for code in ("QG1-NUMBER", "QG4-HEALTH"):
                    self.assertIn(code, found, (marker, found))

    def test_a_short_tail_after_the_source_list_is_not_counted_as_body_but_is_scanned(self):
        tail = f"*{self.BAD_TAIL}*"
        body = h.ko_body(source_list=f"### 출처\n- [예시 기관 보도자료]({LINK})\n\n{tail}")
        parts = qg.split_story(body)
        self.assertTrue(parts.block.startswith("### 출처"))
        self.assertIn("9,999억", parts.tail)
        self.assertNotIn("9,999억", parts.story)
        found = gate_codes(body)
        self.assertIn("QG1-NUMBER", found)
        self.assertIn("QG4-HEALTH", found)

    def test_a_long_narrative_after_a_marker_makes_the_marker_a_caption_not_the_end_list(self):
        for length, is_end in ((qg.TAIL_MAX_CHARS - 100, True), (qg.TAIL_MAX_CHARS + 200, False)):
            with self.subTest(length=length):
                body = f"{plain(1100)}\n\n### 출처\n- [A]({LINK})\n\n{plain(length)}"
                self.assertEqual(bool(qg.split_story(body).block), is_end)

    def test_the_real_source_list_at_the_end_wins_over_an_earlier_caption(self):
        body = f"{plain(1100)}\n\n출처: 통계청\n\n{plain(900)}\n\n### 출처\n- [A]({LINK})\n- [B](https://www.example.gov/docs/two)"
        parts = qg.split_story(body)
        self.assertIn("출처: 통계청", parts.story)
        self.assertTrue(parts.block.startswith("### 출처"))
        self.assertEqual(parts.tail, "")

    def test_links_and_organization_names_in_the_source_list_are_not_claims(self):
        listing = ("### 출처\n- [통계청 2024 가구 소득 조사 결과 9,999건 요약표](https://www.example.gov/a)\n- 통계청 보도자료\n"
                   "- [Household income survey tables 12–45 (2019 edition)](https://www.example.gov/b)")
        body = h.ko_body(source_list=listing)
        self.assertEqual(h.run_gate(data=h.make_data(ko=body), config=h.make_config(("ko",))).codes(), [])      # 링크 글자의 숫자는 주장이 아니다
        scan = qg.scan_text_of(qg.split_story(body))
        self.assertNotIn("9,999", scan)
        self.assertIn("통계청 보도자료", scan)                                                                         # 링크 밖 글은 읽는다

    def test_a_claim_hidden_next_to_a_link_in_the_source_list_is_still_read(self):
        listing = f"### 출처\n- [원문]({LINK}) 이 영양제는 당뇨를 완치합니다\n- [표](https://www.example.gov/b) 매출 9,999억 원"
        found = gate_codes(h.ko_body(source_list=listing))
        self.assertIn("QG4-HEALTH", found)
        self.assertIn("QG1-CONVERSION", found)                                           # 9,999억 원 — 근거에 없는 통화(원)의 금액

    def test_a_long_bullet_in_the_list_is_narrative_not_a_source_entry(self):
        claim = "가" * 70
        body = f"{plain(1100)}\n\n### 출처\n- [A]({LINK})\n- {claim} 매출은 9,999억 원이었다\n"
        parts = qg.split_story(body)
        self.assertNotIn("9,999억", parts.block)
        self.assertIn("9,999억", parts.tail)

    def test_new_marker_shapes_are_cut_and_the_old_ones_still_are(self):
        item = f"- [A]({LINK})\n- [B](https://www.example.gov/docs/two)"
        shapes = ("## 참고", "참고:", "## 관련 링크", "## 더 읽어보기", "원문:", "> 출처:", "- 출처:", "※ 출처", "## Links", "## 출처 (Sources)", "**Sources and Reference**", "[출처]",
                  "## 출처", "### 참고 자료", "**출처:**", "Sources:", "## Read more", "___\n출처")
        for shape in shapes:
            with self.subTest(shape=shape):
                body = f"{plain(800)}\n\n{shape}\n{item}"
                parts = qg.split_story(body)
                self.assertTrue(parts.block, shape)
                self.assertEqual(qg.readable_length(parts.story) < 1000, True)

    def test_an_unknown_label_over_a_trailing_link_list_is_still_a_source_list(self):
        for label in ("## 이 글에 쓴 자료들", "**함께 보면 좋은 곳**", "더 알아보기"):
            with self.subTest(label=label):
                body = f"{plain(800)}\n\n{label}\n- [A]({LINK})\n- [B](https://www.example.gov/docs/two)"
                parts = qg.split_story(body)
                self.assertTrue(parts.block.startswith(label.strip()), parts.block[:30])
                self.assertEqual(parts.story.strip(), plain(800))

    def test_a_single_trailing_link_without_a_label_is_not_cut(self):
        body = f"{plain(800)}\n\n자세한 내용은 [여기]({LINK}) 를 보세요."
        self.assertEqual(qg.split_story(body), (body, "", ""))

    def test_text_that_only_looks_like_a_marker_is_body(self):
        for line in ("출처는 연준이라고 합니다.", "## 출처와 한계", "**참고** 로 삼을 만한 글입니다", "이 글의 출처: 여러 기관의 발표를 모아 정리했으며 아래 표에서 각각의 한계를 설명합니다 " + "가" * 300):
            with self.subTest(line=line[:20]):
                body = f"{plain(500)}\n\n{line}\n\n{plain(300)}"
                self.assertEqual(qg.split_story(body).block, "")

    def test_many_marker_lines_do_not_make_the_split_slow(self):
        for body in ("출처:\n" * 12000, "## 출처\n- [a](http://x/1)\n" * 4000, "**출처**\n" * 5000):
            with self.subTest(body=body[:12]):
                started = time.perf_counter()
                qg.split_story(body)
                self.assertLess(time.perf_counter() - started, 2.0)

    def test_the_backward_search_looks_at_a_bounded_number_of_marker_lines(self):
        body = f"{plain(300)}\n\n" + "출처:\n" * (qg.MAX_MARKER_CANDIDATES + 10) + plain(qg.TAIL_MAX_CHARS + 200)
        with mock.patch.object(qg, "_end_zone_ok", wraps=qg._end_zone_ok) as spy:
            parts = qg.split_story(body)
        self.assertEqual(parts.block, "")
        self.assertEqual(spy.call_count, qg.MAX_MARKER_CANDIDATES)          # 상한을 넘는 표지 후보는 살피지 않는다(시간 방어 — 표지 모양 줄을 잔뜩 넣어 줄마다 뒤 글 전체를 훑게 하는 입력)


# ----------------------------------------------------------------------------------------------------------------------------------
# 문제 4: 입력 상한과 정규식 속도(독립 검증이 멈춘 모양들)
# ----------------------------------------------------------------------------------------------------------------------------------
class LimitsAndSpeedTest(unittest.TestCase):
    LIMIT = 2.0

    def timed(self, fn, *args):
        started = time.perf_counter()
        fn(*args)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, self.LIMIT, f"{elapsed:.1f}초 걸렸다")

    def test_the_limit_is_thirty_thousand_chars_for_the_body_and_twenty_thousand_for_the_evidence(self):
        self.assertEqual((qg.MAX_BODY_CHARS, qg.MAX_EVIDENCE_CHARS), (30000, 20000))

    def test_a_heading_with_a_long_space_or_tab_run_is_linear(self):
        for n in (4000, 30000):
            for filler in (" ", "\t"):
                with self.subTest(n=n, filler=repr(filler)):
                    self.timed(qg.story_of, "# a" + filler * n + "b")
                    self.timed(qg.story_of, "### 출처" + filler * n + "x")
                    self.timed(qg.split_story, "- " + filler * n + "x")

    def test_a_front_matter_title_with_a_long_space_run_is_linear(self):
        self.timed(qg.front_title, "title: a" + " " * 30000 + "b")
        self.timed(qg.split_front, "---\ntitle: a" + " " * 30000 + "b\n---\n본문")

    def test_digit_runs_and_unfolded_whitespace_do_not_stop_the_health_rule(self):
        profiles = h.health_profiles()
        shapes = ("1" * 30000, "١" * 30000, "１" * 30000, "a" + chr(12) * 30000 + "b", "a" + chr(0x2028) * 30000 + "b", "a" + chr(0x85) * 30000 + "b", "a" + chr(13) * 30000 + "b",
                  "5 mg " * 6000, "1." * 15000, "\n" * 30000)
        for shape in shapes:
            with self.subTest(shape=shape[:6]):
                self.timed(qg.rule_health, "ko", "제목", shape, profiles)                      # 정제하지 않은 글이 직접 들어와도 멈추지 않는다
                self.timed(qg.rule_health, "ko", shape[:1000], qg.prose_of(shape), profiles)

    def test_the_health_rule_gives_the_old_rule_a_squashed_text(self):
        """속도 시험은 느려진 것을 시간으로만 알려 준다 — 기존 위험 규칙(gates.body_risk_hit·first_match)에 넘기는 글이 접힌 글인지 직접 확인한다(입력 정리를 지우면 곧바로 빨강이 되고, 느린 호출은 하지 않는다)."""
        seen = []

        def spy(text_or_patterns, *rest):
            seen.append(text_or_patterns if isinstance(text_or_patterns, str) else rest[0])
            return None, None

        shape = "a" + "1" * 5000 + chr(12) * 3000 + "b \t " * 100
        with mock.patch.object(qg.gates, "body_risk_hit", side_effect=spy), mock.patch.object(qg.gates, "first_match", side_effect=spy):
            qg.rule_health("ko", "제목", shape, h.health_profiles())
        self.assertGreaterEqual(len(seen), 2)
        for text in seen:
            self.assertNotRegex(text, r"\d{16}")
            self.assertNotRegex(text, r"[^\S\n]{2}")

    def test_the_squash_helper(self):
        self.assertEqual(qg._squash("a" + chr(12) * 50 + "b" + "\t \t" + "c\n\n\nd"), "a b c\n\n\nd")
        self.assertEqual(qg._squash("1" * 20), "1" * 15)
        self.assertEqual(qg._squash("12345"), "12345")

    def test_an_oversized_body_is_refused_before_any_regex_runs(self):
        content = "---\nlayout: post\ntitle: \"제목\"\n---\n\n" + "1" * (qg.MAX_BODY_CHARS + 1)
        data = h.make_data(ko=content)
        data["kr_content"] = content
        with mock.patch.object(qg, "split_story", side_effect=AssertionError("정규식을 돌렸다")), mock.patch.object(qg, "prose_of", side_effect=AssertionError("정규식을 돌렸다")):
            started = time.perf_counter()
            report = qg.check_candidate(data, h.fixture_source(), config=h.make_config(("ko",)), as_of=AS_OF)
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertEqual(report.codes(), ["QG0-INPUT"])
        self.assertIn("너무 김", report.holds[0].message)

    def test_a_body_at_the_limit_is_still_checked(self):
        content = "---\nlayout: post\ntitle: \"제목\"\n---\n\n" + "가 " * ((qg.MAX_BODY_CHARS - 40) // 2)
        self.assertLessEqual(len(content), qg.MAX_BODY_CHARS)
        data = h.make_data(ko="")
        data["kr_content"] = content
        report = qg.check_candidate(data, h.fixture_source(), config=h.make_config(("ko",)), as_of=AS_OF)
        self.assertNotIn("QG0-INPUT", report.codes())

    def test_the_evidence_is_cut_for_processing_but_the_summary_length_is_real(self):
        source = h.fixture_source(summary="가" * 500000)
        evidence = qg.evidence_text(source)
        self.assertEqual(len(evidence.text), qg.MAX_EVIDENCE_CHARS)
        self.assertEqual(evidence.summary_chars, 500000)
        self.timed(qg.rule_numbers, "ko", "매출은 1,234억 원이다", evidence.text, AS_OF)
        self.timed(qg.rule_quotes, "ko", "그는 “충분히 길어서 인용으로 읽히는 지어낸 문장입니다 정말로 길게 씁니다”라고 말했다", evidence.text)

    def test_long_runs_of_number_words_and_names_are_fast(self):
        for shape in ("one " * 7500, "and " * 7500, "twenty-" * 4000, "Aa Bb, the " * 2700, "Director " * 3300, "위원장 가나 다라 " * 3300, "김철수 위원장 " * 4000):
            with self.subTest(shape=shape[:10]):
                self.timed(qg.extract_figures, shape)
                self.timed(qg._titled_people, shape)
                self.timed(qg._quotes, shape)

    def test_runs_of_open_quotes_are_fast(self):
        for opener in ("「", "“", "‘", "«", "《", "『", "„", "\"", "'"):
            with self.subTest(opener=opener):
                self.timed(qg._quotes, opener * 30000)
                self.timed(qg._quotes, (opener + "가 ") * 10000)


# ----------------------------------------------------------------------------------------------------------------------------------
# 문제 17: QG3-LINK — 정규화한 원문 주소가 같을 때만 근거 링크다
# ----------------------------------------------------------------------------------------------------------------------------------
class VerifiedLinkTest(unittest.TestCase):
    CLAIM = "연준은 2026년 금리를 3.5%로 유지했다."

    def has(self, story, link=LINK):
        return qg.has_verified_link(story, link)

    def test_the_same_address_in_any_spelling_counts(self):
        for url in (LINK, LINK + "/", LINK + "#section", LINK + "?utm_source=x&fbclid=y", LINK.replace("https", "http"), LINK.replace("www.example-agency.europa.eu", "WWW.Example-Agency.EUROPA.eu"),
                    LINK.replace("www.", "")):
            with self.subTest(url=url):
                self.assertTrue(self.has(f"{self.CLAIM} ([원문]({url}))"))
                self.assertTrue(self.has(f"{self.CLAIM} {url} 에 있다"))

    def test_another_article_on_the_same_site_or_a_longer_address_does_not_count(self):
        for url in (LINK + "-OTHER-ARTICLE-999", LINK + "999", "https://www.example-agency.europa.eu/news/another-article", "https://www.example-agency.europa.eu/", "https://www.example-agency.europa.eu",
                    LINK + "?id=2", LINK + "/appendix", "https://www.example-agency.europa.eu/news"):
            with self.subTest(url=url):
                self.assertFalse(self.has(f"{self.CLAIM} ([다른 글]({url}))"))

    def test_the_link_inside_code_or_an_image_is_not_a_link(self):
        self.assertFalse(self.has(f"{self.CLAIM}\n\n```\n{LINK}\n```"))
        self.assertFalse(self.has(f"{self.CLAIM} `{LINK}`"))
        self.assertFalse(self.has(f"{self.CLAIM}\n\n![그림]({LINK})"))

    def test_a_missing_or_unreadable_verified_link_never_matches(self):
        for link in ("", None, "not a url", "ftp://x/y"):
            with self.subTest(link=link):
                self.assertFalse(self.has(f"{self.CLAIM} [x]({LINK})", link))
        self.assertFalse(self.has("", LINK))
        self.assertFalse(self.has(None, LINK))

    def test_trailing_punctuation_after_a_bare_address_is_ignored(self):
        for tail in (".", ",", ")", "]", ";", "\"", "”"):
            with self.subTest(tail=tail):
                self.assertTrue(self.has(f"자세한 것은 {LINK}{tail}"))

    def test_the_rule_holds_a_claim_whose_only_link_is_another_article_of_the_same_site(self):
        story = f"{plain(1100)}\n\n{self.CLAIM} ([다른 글](https://www.example-agency.europa.eu/news/another-article))"
        found = codes(qg.rule_link_and_length("ko", story, qg.prose_of(story), LINK, 1000))
        self.assertEqual(found, ["QG3-LINK"])
        story = f"{plain(1100)}\n\n{self.CLAIM} ([원문]({LINK}))"
        self.assertEqual(qg.rule_link_and_length("ko", story, qg.prose_of(story), LINK, 1000), [])


# ----------------------------------------------------------------------------------------------------------------------------------
# 문제 15: QG7 주소 정규화
# ----------------------------------------------------------------------------------------------------------------------------------
class UrlNormalizationTest(unittest.TestCase):
    def test_known_tracking_parameters_are_dropped_and_other_names_are_kept(self):
        base = "https://example.org/a"
        for tracking in ("utm_source=x", "UTM_Medium=y", "fbclid=1", "gclid=2", "dclid=3", "msclkid=4", "yclid=5", "igshid=6", "mc_cid=7", "mc_eid=8", "ixid=9", "ref=home", "ref_src=tw", "_hsenc=1"):
            with self.subTest(tracking=tracking):
                self.assertEqual(qg.normalize_url(f"{base}?{tracking}"), "example.org/a")
        # `ref` 로 시작하는 다른 이름(reference·refresh)은 추적 매개변수가 아니다 — 값이 다르면 다른 글이다
        self.assertNotEqual(qg.normalize_url(f"{base}?reference=abc"), qg.normalize_url(f"{base}?reference=xyz"))
        self.assertEqual(qg.normalize_url(f"{base}?reference=abc"), "example.org/a?reference=abc")
        self.assertEqual(qg.normalize_url(f"{base}?id=1&utm_campaign=c"), "example.org/a?id=1")

    def test_percent_encoding_index_pages_and_amp_hosts_are_the_same_article(self):
        self.assertEqual(qg.normalize_url("https://example.org/news/a%2Db"), qg.normalize_url("https://example.org/news/a-b"))
        self.assertEqual(qg.normalize_url("https://example.org/news/a/index.html"), qg.normalize_url("https://example.org/news/a"))
        self.assertEqual(qg.normalize_url("https://example.org/news/a/index.php?x=1"), "example.org/news/a?x=1")
        self.assertEqual(qg.normalize_url("https://amp.example.org/news/a"), qg.normalize_url("https://www.example.org/news/a"))
        self.assertNotEqual(qg.normalize_url("https://example.org/News/A"), qg.normalize_url("https://example.org/news/a"))      # 경로 대소문자는 다른 글이다

    def test_the_reuse_rule_sees_the_same_article_through_these_spellings(self):
        history = [{"source_url": "https://amp.example.org/news/a%2Db/index.html?utm_source=x#top"}]
        self.assertEqual(codes(qg.rule_reuse("https://www.example.org/news/a-b", history)), ["QG7-REUSE"])
        self.assertEqual(qg.rule_reuse("https://example.org/news/a-b?reference=zzz", [{"source_url": "https://example.org/news/a-b?reference=abc"}]), [])


# ----------------------------------------------------------------------------------------------------------------------------------
# 문제 6: 숫자는 같은 종류의 근거 숫자와만 맞춘다
# ----------------------------------------------------------------------------------------------------------------------------------
class NumberKindTest(unittest.TestCase):
    def held(self, evidence, body):
        return codes(qg.rule_numbers("ko", qg.prose_of(body), evidence, AS_OF))

    def test_a_percent_is_not_supported_by_a_count_with_the_same_value(self):
        for evidence in ("A survey of 45 respondents found growth of 3%.", "The agency counted 60 abstentions and 40 percent agreed."):
            number = "45" if "45 respondents" in evidence else "60"
            with self.subTest(evidence=evidence):
                self.assertEqual(self.held(evidence, f"응답자의 {number}%가 동의했다."), ["QG1-NUMBER"])
        self.assertEqual(self.held("A survey of 45 respondents found growth of 3%.", "응답자 45명이 답했다."), [])
        self.assertEqual(self.held("40 percent agreed; 60 abstained.", "40%가 찬성했다."), [])
        self.assertEqual(self.held("40 percent agreed.", "40명이 찬성했다."), ["QG1-NUMBER"])             # 반대 방향도 마찬가지다: 근거의 퍼센트는 본문의 건수를 받쳐 주지 않는다
        self.assertEqual(self.held("About 45.5 percent agreed.", "45.5개 도시가 찬성했다."), ["QG1-NUMBER"])

    def test_a_year_is_not_supported_by_a_count_or_an_amount_with_the_same_value(self):
        for evidence, body in (("Over 2,000 people responded in March 2025.", "2000년부터 이어진 흐름이다."), ("Costs reached $2,025 per unit.", "2025년에 비용이 올랐다."),
                               ("Cases: 1,950 recorded.", "1950년 기록이다."), ("The agency counted 2000 people.", "2000년에 시작됐다."), ("Surveyed 2025 households.", "2025년에 조사했다.")):
            with self.subTest(evidence=evidence):
                self.assertEqual(self.held(evidence, body), ["QG1-NUMBER"])
        for evidence, body in (("Data cover 2025 only.", "2025년 자료다."), ("Published in 2025.", "2025년 자료다."), ("The vote took place on Nov. 4, 2026.", "2026년 투표다."),
                               ("Q3 2026 results", "2026년 3분기 결과다."), ("It happened in the 1990s.", "1990년대에 일어났다.")):
            with self.subTest(evidence=evidence):
                self.assertEqual(self.held(evidence, body), [])

    def test_a_bare_year_in_the_body_needs_a_year_in_the_evidence(self):
        """'2000년' 처럼 년이 붙은 연도는 날짜 길로 읽히고, 년이 없는 연도 모양 정수(the 2000 program)는 연도 종류의 숫자다 — 둘 다 근거의 연도에만 받쳐진다."""
        self.assertEqual(self.held("The agency counted 2000 people.", "the 2000 program"), ["QG1-NUMBER"])          # 근거의 건수 2000 은 연도가 아니다
        self.assertEqual(self.held("Costs reached 2000 dollars.", "the 2000 program"), ["QG1-NUMBER"])             # 금액도 연도가 아니다
        self.assertEqual(self.held("Published in 2000.", "the 2000 program"), [])
        self.assertEqual(self.held("The vote took place on Nov. 4, 2000.", "the 2000 program"), [])                # 날짜의 연도는 연도다

    def test_a_count_that_looks_like_a_year_is_a_count(self):
        """2025건·2000 people 처럼 연도 모양의 정수에 세는 말이 붙으면 건수다: 근거의 연도 2025년이 이 건수를 받쳐 주지 않는다."""
        self.assertEqual(self.held("Data cover 2025 only.", "2025건이 접수됐다."), ["QG1-NUMBER"])
        self.assertEqual(self.held("Data cover 2025 only.", "2,025건이 접수됐다."), ["QG1-NUMBER"])
        self.assertEqual(self.held("The office received 2025 cases.", "2025건이 접수됐다."), [])
        self.assertEqual(self.held("The office received 2025 cases.", "2025명이 참가했다."), [])

    def test_a_small_integer_with_a_counter_is_still_not_a_claim(self):
        """현재 규칙 유지: 단위·퍼센트·통화·날짜 표지가 없는 31 이하 정수는 주장으로 세지 않는다(몇 가지·목록 번호) — 근거와 종류가 달라도 보류하지 않는다."""
        self.assertEqual(self.held("Growth slowed to 3% in the quarter.", "3명이 참가했다."), [])
        self.assertEqual(self.held("Growth slowed to 3% in the quarter.", "12개 도시 중 7곳에서 늘었다."), [])
        self.assertEqual(self.held("Growth slowed to 3% in the quarter.", "참가자는 45명이다."), ["QG1-NUMBER"])          # 32 이상이면 센다

    def test_percent_forms_in_the_evidence_are_percent(self):
        for evidence in ("a 3.4 percent rise", "up 3.4 per cent", "a 3.4-percent rise", "3.4% higher", "3.4 percentage points"):
            with self.subTest(evidence=evidence):
                self.assertEqual(self.held(evidence, "3.4%가 늘었다."), [])
        self.assertEqual(self.held("a 3.4 percent rise", "3.5%가 늘었다."), ["QG1-NUMBER"])

    def test_money_still_needs_the_same_currency_and_a_plain_number_only_backs_it_when_the_evidence_has_no_money(self):
        self.assertEqual(self.held("The package is worth $4.2 billion.", "규모는 42억 달러다."), [])
        self.assertEqual(self.held("The package is worth $4.2 billion.", "규모는 약 5조 8천억 원이다."), ["QG1-CONVERSION"])
        self.assertEqual(self.held("Sales were 500 million won.", "매출은 5억 원이다."), [])
        self.assertEqual(self.held("Sales were $500 million and 600 people came.", "매출은 5억 원이다."), ["QG1-CONVERSION"])

    def test_numeric_dates_are_read_in_both_orders(self):
        self.assertEqual(self.held("The vote took place on 11/04/2026.", "2026년 11월 4일에 표결이 있었다."), [])
        self.assertEqual(self.held("The vote took place on 11/04/2026.", "2026년 4월 11일에 표결이 있었다."), [])          # 일/월/연 으로도 읽을 수 있다
        self.assertEqual(self.held("The vote took place on 11/04/2026.", "2026년 11월 5일에 표결이 있었다."), ["QG1-NUMBER"])
        self.assertEqual(self.held("Meeting on 13/04/2026.", "2026년 4월 13일 회의"), [])
        self.assertEqual(self.held("Meeting on 13/04/2026.", "2026년 4월 14일 회의"), ["QG1-NUMBER"])
        self.assertEqual(self.held("The ministry met on November 5, 2026.", "회의는 11/05/2026 에 열렸다."), [])
        self.assertEqual(self.held("The ministry met on November 5, 2026.", "회의는 11/06/2026 에 열렸다."), ["QG1-NUMBER"])
        # 본문의 모호한 날짜는 앞선 읽기(월/일)가 근거에 없어도 다른 읽기(일/월)가 근거에 있으면 받는다
        self.assertEqual(self.held("The ministry met on November 5, 2026.", "회의는 05/11/2026 에 열렸다."), [])
        self.assertEqual(self.held("The ministry met on November 5, 2026.", "회의는 05/12/2026 에 열렸다."), ["QG1-NUMBER"])

    def test_a_decimal_comma_before_a_percent_is_a_decimal(self):
        self.assertEqual(self.held("Rate was 3.5% last month.", "상승률은 3,5%였다."), [])
        self.assertEqual(self.held("Rate was 3.4% last month.", "상승률은 3,5%였다."), ["QG1-NUMBER"])
        self.assertEqual(self.held("About 1,250,000 households.", "가구는 1,250,000 이다."), [])           # 천 단위 쉼표는 그대로

    def test_english_number_words_in_the_body_are_claims_when_big(self):
        self.assertEqual(self.held("About 300,000 people were affected.", "three million people were affected."), ["QG1-NUMBER"])
        self.assertEqual(self.held("About 3,000,000 people were affected.", "three million people were affected."), [])
        self.assertEqual(self.held("Forty percent agreed.", "forty percent agreed."), [])
        self.assertEqual(self.held("Forty percent agreed.", "fifty percent agreed."), ["QG1-NUMBER"])
        self.assertEqual(self.held("The fund paid five hundred dollars.", "five hundred dollars were paid."), [])


# ----------------------------------------------------------------------------------------------------------------------------------
# 문제 5: 인용·직함 사각
# ----------------------------------------------------------------------------------------------------------------------------------
class QuoteAndPersonTest(unittest.TestCase):
    EV_NONE = "The agency released a report on Tuesday about the program."
    EV_EN = ("The agency said on Tuesday that the program will expand next year. Director Jane Marlow told reporters, "
             "\"We are committed to expanding access to every region over the next two years.\" The plan covers 12 states.")
    LONG_FAKE = "we will cut prices by half next year for every single customer in the country"

    def held(self, body, evidence=None, lang="ko"):
        return codes(qg.rule_quotes(lang, qg.prose_of(body), self.EV_NONE if evidence is None else evidence))

    def test_every_quotation_mark_style_is_read(self):
        styles = (('"', '"'), ("“", "”"), ("‘", "’"), ("'", "'"), ("「", "」"), ("『", "』"), ("«", "»"), ("《", "》"), ("„", "“"))
        for open_, close in styles:
            with self.subTest(style=open_ + close):
                self.assertEqual(self.held(f"그는 {open_}{self.LONG_FAKE}{close}라고 말했다."), ["QG2-QUOTE"])
        for open_, close in styles:
            with self.subTest(style=open_ + close, grounded=True):
                self.assertEqual(self.held(f"그는 {open_}{self.LONG_FAKE}{close}라고 말했다.", self.EV_NONE + f" He said \"{self.LONG_FAKE}\" in an interview."), [])

    def test_apostrophes_inside_words_are_not_quotation_marks(self):
        self.assertEqual(self.held("The agency's plan isn't what Korea’s officials don't expect, and it's fine."), [])
        self.assertEqual(self.held(f"‘{self.LONG_FAKE.replace('we will', 'we’ll')}’라고 말했다."), ["QG2-QUOTE"])

    def test_a_short_quote_with_the_speaker_cue_right_next_to_it_is_a_quote(self):
        for body in ("위원장은 “지금이 기회”라고 강조했다.", "장관은 “반드시 이긴다”고 말했다.", "장관은 “우리는 반드시 이길 것이다”고 말했다.", 'He said "we will win this", the minister added.',
                     "The minister said: “not yet”", "“곧 발표한다”고 밝혔다."):
            with self.subTest(body=body):
                self.assertEqual(self.held(body), ["QG2-QUOTE"])

    def test_a_quoted_term_is_not_a_quote_even_with_a_cue_elsewhere_in_the_sentence(self):
        for body in ("그녀는 “데이터”가 핵심이라고 말했다.", 'The "digital divide" remains wide.', "He said the “digital divide” is wide.", "‘스마트 시티’라고 부르는 사업이 늘었다.",
                     "“디지털 격차”라고 표현하는 말이 있다.", "그는 “중위 소득”이 중요하다고 설명했다."):
            with self.subTest(body=body):
                self.assertEqual(self.held(body), [])

    def test_the_long_quote_boundaries_are_eight_words_or_forty_characters_without_a_cue(self):
        """M04: 8낱말·40자가 경계다. 7낱말 39자는 말한 사람 표현이 없으면 인용이 아니고, 8낱말이나 40자는 인용이다."""
        seven_words = "aa bb cc dd ee ff gg"                                        # 7낱말 20자
        eight_words = seven_words + " hh"                                          # 8낱말 23자
        chars_39 = "a" * 39
        chars_40 = "a" * 40
        self.assertEqual((qg.QUOTE_LONG_WORDS, qg.QUOTE_LONG_CHARS), (8, 40))
        self.assertEqual(self.held(f'The plan has "{seven_words}" in it.', lang="en"), [])
        self.assertEqual(self.held(f'The plan has "{eight_words}" in it.', lang="en"), ["QG2-QUOTE"])
        self.assertEqual(self.held(f'The plan has "{chars_39}" in it.', lang="en"), [])
        self.assertEqual(self.held(f'The plan has "{chars_40}" in it.', lang="en"), ["QG2-QUOTE"])

    def test_a_very_long_quote_and_a_quote_wrapped_over_a_line_are_read(self):
        self.assertEqual(self.held('위원장은 말했다. "' + ("가" * 700) + '"'), ["QG2-QUOTE"])
        self.assertEqual(self.held("위원장은 말했다. “" + "나는 이렇게 말한다 " * 5 + "\n이어지는 줄”"), ["QG2-QUOTE"])
        self.assertEqual(self.held("위원장은 “첫 문단 따옴표\n\n둘째 문단” 이라고 했다"), [])         # 빈 줄(문단 경계)을 넘는 따옴표는 한 인용으로 읽지 않는다

    def test_quotes_in_the_source_pass_in_any_style(self):
        self.assertEqual(self.held('Director Jane Marlow said "We are committed to expanding access to every region over the next two years."', self.EV_EN, "en"), [])
        self.assertEqual(self.held("Director Jane Marlow said ‘we are committed to expanding access to every region over the next TWO years’", self.EV_EN, "en"), [])
        self.assertEqual(self.held('Director Jane Marlow said "We are committed to expanding access to every region over the next three years."', self.EV_EN, "en"), ["QG2-QUOTE"])

    def test_the_source_side_counts_every_quoted_span_for_a_translated_quote(self):
        evidence = 'The agency said the program "will reach every county within three years" and called it "ambitious".'
        self.assertEqual(len(qg._quotes(qg._fold(evidence), everything=True)), 2)
        self.assertEqual(len(qg._quotes(qg._fold(evidence))), 0)                                  # 본문 쪽 판정(길거나 말한 사람 표현이 바로 붙은 것)으로는 둘 다 인용이 아니다

    def test_titled_people_in_korean_word_order(self):
        for body in ("김철수 위원장은 계획이 확대될 것이라고 밝혔다.", "위원장 김철수는 계획이 확대될 것이라고 밝혔다.", "제인 말로 조사국장은 계획이 확대될 것이라고 말했다.", "연준 의장 제롬 파월은 금리를 동결했다고 밝혔다.",
                     "제롬 파월 연준 의장은 금리를 동결했다고 밝혔다.", "이재명 대통령은 회의를 주재했다.", "크리스토퍼 무파리지 애플 CEO 는 신제품을 발표했다."):
            with self.subTest(body=body):
                self.assertEqual(self.held(body), ["QG2-PERSON"])
        self.assertEqual(self.held("김철수 위원장은 계획이 확대될 것이라고 밝혔다.", "Chair Kim Chul-soo said the plan will grow."), [])          # 한글 이름은 근거에 이름이 든 직함 사람이 하나 있으면 개수로 받아 준다

    def test_titled_people_with_lowercase_titles_and_possessives(self):
        for body in ("Apple chief executive Tim Cook said the plan would grow.", "professor Jane Doe of the university said the plan would grow.",
                     "Jane Marlow, the agency's director, said the program would grow.", "Tim Cook, chief executive of Apple, said the plan would grow."):
            with self.subTest(body=body):
                self.assertEqual(self.held(body, lang="en"), ["QG2-PERSON"])
        self.assertEqual(self.held("Jane Marlow, the agency's director, said the program would grow.", self.EV_EN, "en"), [])

    def test_words_that_only_look_like_names_next_to_a_title_are_not_people(self):
        for body in ("정부 위원장 선임 절차가 시작됐다.", "이사회 의장은 회의를 열었다.", "국회 의장은 법안을 상정했다.", "한국은행 총재는 금리를 동결했다고 밝혔다.", "경제 장관 회의가 열렸다.",
                     "대표적인 사례를 소개한다.", "정책 국장이 맡는다.", "The Director of the agency said the program will expand.", "The agency said the program will expand."):
            with self.subTest(body=body):
                self.assertEqual(self.held(body), [])


# ----------------------------------------------------------------------------------------------------------------------------------
# 문제 13: 경계값 — 행사 신호·번역 복제 임계값·연도 근거
# ----------------------------------------------------------------------------------------------------------------------------------
class ThresholdBoundaryTest(unittest.TestCase):
    def test_event_density_boundary_is_inclusive_and_three_distinct_signals_are_needed(self):
        """M02·M07: 1,000자당 4.0(국문)은 보류, 3.99 는 통과. 서로 다른 신호는 3가지부터다."""
        self.assertEqual((qg.EVENT_DENSITY_HOLD["ko"], qg.EVENT_DENSITY_HOLD["en"], qg.EVENT_DISTINCT_HOLD), (4.0, 1.8, 3))
        base = "가" * 992
        three = " 행사 일정 등록 행사"                                  # 신호 4개·서로 다른 3개(읽기 글자 8)
        text = base + three
        total, distinct, density = qg.event_signals("", text)
        self.assertEqual((total, distinct), (4, 3))
        readable = len("".join(text.split()))
        self.assertEqual(readable, 1000)
        self.assertEqual(density, 4.0)
        self.assertEqual(codes(qg.rule_event("ko", "", text)), ["QG5-EVENT"])                                      # 밀도가 딱 4.0 이면 보류(>= 경계)
        self.assertEqual(codes(qg.rule_event("ko", "", text + "가")), [])                                           # 1,001자면 3.996 이라 통과
        two_distinct = base + " 행사 일정 행사 일정"
        self.assertEqual(qg.event_signals("", two_distinct)[:2], (4, 2))
        self.assertEqual(codes(qg.rule_event("ko", "", two_distinct)), [])                                        # 서로 다른 신호가 2가지면 밀도가 같아도 통과
        four_distinct = base + " 행사 일정 등록 신청"
        self.assertEqual(codes(qg.rule_event("ko", "", four_distinct)), ["QG5-EVENT"])

    def test_english_event_boundary(self):
        # 신호 3개(event·agenda·register = 읽기 글자 19): 읽기 글자 1,666 이면 3000/1666 = 1.8007(보류), 1,667 이면 1.7996(통과)
        text = "a" * 1647 + " event agenda register"
        self.assertEqual(len("".join(text.split())), 1666)
        total, distinct, density = qg.event_signals("", text)
        self.assertEqual((total, distinct), (3, 3))
        self.assertGreaterEqual(density, 1.8)
        self.assertEqual(codes(qg.rule_event("en", "", text)), ["QG5-EVENT"])
        longer = "a" * 1648 + " event agenda register"
        self.assertLess(qg.event_signals("", longer)[2], 1.8)
        self.assertEqual(codes(qg.rule_event("en", "", longer)), [])

    def test_clone_number_overlap_boundary_is_inclusive(self):
        """M03: 구조 두 칸이 같고 하나가 어긋난 쌍은 숫자 겹침 0.40 이상이면 복제, 그 아래면 아니다."""
        self.assertEqual(qg.CLONE_NUMBER_OVERLAP, 0.40)
        ko_structure = "문단.\n\n### 소제목\n\n문단.\n\n- 항목\n\n"
        en_structure = "One.\n\n### Heading\n\nTwo.\n\n- item\n\nExtra paragraph.\n\n"
        # 숫자 집합: 국문 {100, 200, 300}, 영문 {100, 200, 400, 500} → 교집합 2 / 합집합 5 = 0.4
        ko = ko_structure + "수치는 100과 200과 300이다."
        en = en_structure + "Figures are 100 and 200 and 400 and 500."
        overlap = qg.number_overlap(qg.prose_of(ko), qg.prose_of(en))
        self.assertAlmostEqual(overlap, 0.4)
        self.assertEqual(codes(qg.rule_clone(ko, en, qg.prose_of(ko), qg.prose_of(en))[0]), ["QG8-CLONE"])
        en_low = en_structure + "Figures are 100 and 400 and 500 and 600."          # 교집합 1 / 합집합 6 = 0.17
        self.assertLess(qg.number_overlap(qg.prose_of(ko), qg.prose_of(en_low)), 0.4)
        self.assertEqual(codes(qg.rule_clone(ko, en_low, qg.prose_of(ko), qg.prose_of(en_low))[0]), [])

    def test_the_year_of_a_body_date_needs_a_year_in_the_source(self):
        """M09: 근거에 같은 연도가 없으면 연도만 있는 날짜도 보류다 — 근거의 연도는 날짜의 연도이거나 연도로 읽힌 수여야 한다."""
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("2019년에 시작됐다."), "Data cover 2025 only.", AS_OF)), ["QG1-NUMBER"])
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("2025년에 시작됐다."), "Data cover 2025 only.", AS_OF)), [])
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("2019년에 시작됐다."), "Published on March 3, 2019.", AS_OF)), [])
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("2019년에 시작됐다."), "Over 2,019 people came.", AS_OF)), ["QG1-NUMBER"])
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("오늘은 2026년이다."), "No year here.", AS_OF)), [])                      # 실행 날짜의 연도는 근거로 받는다


# ----------------------------------------------------------------------------------------------------------------------------------
# 문제 1·2: 건강 C — 증상·질환 + 즉각·단정 + 효과, 상담 문구가 붙어도 효능 단정은 단정이다
# ----------------------------------------------------------------------------------------------------------------------------------
NEUTRAL_TITLE = "미국 연방기관이 발표한 보고서의 핵심 내용"


def body_with(sentence):
    return f"{plain(500)}\n\n{sentence}\n\n{plain(450)}"


class HealthClaimTest(unittest.TestCase):
    PROFILES = None

    @classmethod
    def setUpClass(cls):
        cls.PROFILES = h.health_profiles()

    def in_body(self, sentence, lang="ko"):
        return codes(qg.rule_health(lang, NEUTRAL_TITLE, qg.prose_of(body_with(sentence)), self.PROFILES))

    def as_title(self, sentence):
        return codes(qg.rule_health("ko", sentence, qg.prose_of(body_with("평범한 문장입니다.")), self.PROFILES))

    def assert_held(self, sentence, lang="ko"):
        self.assertTrue(self.in_body(sentence, lang), f"본문 위치 미탐: {sentence}")
        if lang == "ko":
            self.assertTrue(self.as_title(sentence), f"제목 위치 미탐: {sentence}")

    def assert_passes(self, sentence):
        self.assertEqual(self.in_body(sentence), [], f"본문 위치 오탐: {sentence}")
        self.assertEqual(self.as_title(sentence), [], f"제목 위치 오탐: {sentence}")

    # 운영자가 직접 준 예시 16개(건강 판정 확인용 표본, 2026-11-06)와 앞 판 16개 중 C
    OPERATOR_C = ("이 영양제는 피로를 즉시 없애줍니다", "영양제로 불면이 바로 치료됩니다", "수면제 바로 끊어도 될까", "피로를 즉시 줄이는 방법", "자세를 바로 교정하는 책상 설정",
                  "통증을 완전히 없애는 의자 선택법", "당뇨 100% 보장", "당뇨를 무조건 개선하는 식품", "암 완치 보장",
                  "불면을 확실히 치료하는 방법", "영양제로 피로가 완전히 회복됩니다", "암 예방 100% 보장", "암 수술 100% 안전", "수술 후유증 100% 해결", "스트레스를 확실히 줄이는 시간 관리법")
    OPERATOR_A = ("피로할 때 작업환경을 점검하는 방법", "자세가 불편할 때 책상 높이를 확인하는 기준", "잠들기 전 화면 사용을 줄이는 생활 습관", "잠이 잘 오지 않을 때 수면 환경을 점검하는 방법",
                  "자세교정기 구매 기준")
    VARIANTS = ("두통이 바로 사라집니다", "요통을 완전히 없애는 스트레칭", "무릎 통증이 100% 사라집니다", "눈 피로가 즉시 풀리는 방법", "이 베개는 불면을 확실히 해소합니다", "우울감이 즉시 사라지는 습관",
                "탈모를 무조건 막아 주는 샴푸", "소화불량이 바로 낫는 차", "혈압을 바로 낮춰 줍니다", "체중 감량 보장 식단", "알레르기를 완전히 치료하는 공기청정기", "감기가 하루 만에 낫는 비법",
                "근육통이 즉시 사라진다", "이 제품은 어깨 결림을 확실하게 없앱니다", "피부 트러블을 완벽히 해결해 주는 크림")
    ENGLISH = ("This supplement cures insomnia instantly.", "Guaranteed diabetes cure with this diet.", "This chair completely eliminates back pain.",
               "Fatigue vanishes immediately with this routine.", "This pill definitely lowers blood pressure overnight.")

    def test_the_operators_c_examples_are_held_in_the_body_and_in_the_title(self):
        for sentence in self.OPERATOR_C:
            with self.subTest(sentence=sentence):
                self.assert_held(sentence)

    def test_the_operators_a_examples_are_not_held(self):
        for sentence in self.OPERATOR_A:
            with self.subTest(sentence=sentence):
                self.assert_passes(sentence)

    def test_symptom_and_disease_variants_with_an_immediate_or_absolute_effect_are_held(self):
        for sentence in self.VARIANTS:
            with self.subTest(sentence=sentence):
                self.assert_held(sentence)
        for sentence in self.ENGLISH:
            with self.subTest(sentence=sentence):
                self.assertTrue(self.in_body(sentence, "en"), sentence)

    def test_every_effect_verb_family_in_every_form_with_every_adverb_is_held(self):
        """운영자 기준 ①·②: 효과 동사는 기본형뿐 아니라 활용형까지, 줄이다·없애다·완화하다·개선하다·교정하다·치료하다·회복하다·예방하다·감량하다 계열 모두(9계열 × 6꼴 × 대상 × 부사)."""
        families = {
            "줄이": ("줄인다", "줄이는", "줄일 수 있다", "줄일 수 있습니다", "줄여 준다", "줄여줍니다"),
            "없애": ("없앤다", "없애는", "없앨 수 있다", "없앨 수 있습니다", "없애 준다", "없애줍니다"),
            "완화": ("완화한다", "완화하는", "완화할 수 있다", "완화할 수 있습니다", "완화해 준다", "완화해줍니다"),
            "개선": ("개선한다", "개선하는", "개선할 수 있다", "개선할 수 있습니다", "개선해 준다", "개선해줍니다"),
            "교정": ("교정한다", "교정하는", "교정할 수 있다", "교정할 수 있습니다", "교정해 준다", "교정해줍니다"),
            "치료": ("치료한다", "치료하는", "치료할 수 있다", "치료할 수 있습니다", "치료해 준다", "치료해줍니다"),
            "회복": ("회복한다", "회복하는", "회복할 수 있다", "회복할 수 있습니다", "회복해 준다", "회복해줍니다"),
            "예방": ("예방한다", "예방하는", "예방할 수 있다", "예방할 수 있습니다", "예방해 준다", "예방해줍니다"),
            "감량": ("감량한다", "감량하는", "감량할 수 있다", "감량할 수 있습니다", "감량해 준다", "감량해줍니다"),
        }
        targets = ("피로를", "통증을", "자세를", "두통을", "스트레스를")
        adverbs = ("즉시", "바로", "완전히", "확실히", "무조건")
        count, sample = 0, []
        for forms in families.values():
            for form in forms:
                for target in targets:
                    for adverb in adverbs:
                        sentence = f"{target} {adverb} {form}"
                        count += 1
                        self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)          # 효과 단정 판정 자체가 모두 잡는다
                        if count % 27 == 0:
                            sample.append(sentence)
        self.assertEqual(count, 9 * 6 * 5 * 5)
        for sentence in sample:                                                                  # 표본은 규칙 전체(제목·본문)로도 확인한다
            with self.subTest(sentence=sentence):
                self.assert_held(sentence)

    def test_the_adverb_before_the_target_also_counts(self):
        for sentence in ("즉시 피로를 줄이는 방법", "완전히 통증을 없애는 의자", "무조건 스트레스를 풀어 주는 음악", "하루 만에 두통이 낫는 비법", "3일 안에 피로가 사라지는 습관"):
            with self.subTest(sentence=sentence):
                self.assert_held(sentence)

    def test_an_adverb_that_orders_an_action_is_not_a_claim(self):
        """운영자 원칙: '바로 확인한다'처럼 행동 순서를 꾸미는 부사는 C 가 아니다."""
        for sentence in ("피로할 때 바로 작업환경을 점검하는 방법", "자세가 불편하면 책상 높이를 바로 확인하는 기준", "통증이 있을 때 즉시 쉬는 시간을 기록해 두는 방법", "스트레스를 줄이는 방법은 다음과 같다",
                         "피로 회복을 돕는 환경을 점검하는 기준", "바로 점검해 두면 좋은 점은 다음과 같다", "통증이 심할 때 바로 병원에 가세요", "피로를 줄이는 방법을 바로 확인하세요",
                         "자세를 점검한 뒤 책상을 바로 정리하세요", "통증이 계속되면, 곧바로 기록을 남기세요"):
            with self.subTest(sentence=sentence):
                self.assert_passes(sentence)

    def test_a_clause_boundary_separates_the_symptom_from_a_later_effect(self):
        self.assertEqual(self.in_body("통증이 심할 때 바로 병원에 가세요, 그러면 줄어듭니다"), [])          # 쉼표 앞 절엔 효과 동사가 없고 뒤 절엔 증상·부사가 없다
        self.assertTrue(self.in_body("통증을 즉시 줄이는 방법, 지금 확인하세요"))

    def test_the_distance_between_the_adverb_and_the_effect_verb_is_bounded(self):
        """한국어는 부사와 효과 동사 사이를 글자 수가 아니라 구조로 가른다(명사구·부사만 끼면 결과 수식, 행동 서술어·다른 대상이 끼면 행동 순서). 멀리 떨어진 말을 잇지 않으려는 느슨한 안전선만 40자로 둔다.
        영어는 부사가 동사 앞뒤 어느 쪽이든 30자 이하일 때만 효과 동사를 꾸민다고 본다. (예전 8자 상한은 '통증을 즉시 이 베개 하나만으로 줄일 수 있습니다' 같은 긴 수식을 놓쳤다 — 검증 D1-2.)"""
        self.assertEqual(qg._CLAIM_GAP_KO_CAP, 40)
        self.assertEqual(qg._CLAIM_GAP_EN, 30)
        for filler, expected in ((0, True), (6, True), (7, True), (12, True), (38, True), (39, False), (60, False)):          # 사이 글자 수 = 채움 + 앞뒤 공백 2
            with self.subTest(korean_filler=filler):
                self.assertEqual(qg._effect_claim("피로를 즉시 " + "가" * filler + " 줄이는", "ko") is not None, expected)
        for gap_phrase, expected in ((" 이 베개 하나만으로 ", True), (" 하루 한 번 이 방법만으로 ", True), (" 병원에 가서 ", False), (" 약을 먹으면 증상이 ", False), (" 작업을 ", False)):
            with self.subTest(korean_gap=gap_phrase):
                self.assertEqual(qg._effect_claim("피로를 즉시" + gap_phrase + "줄이는 방법", "ko") is not None, expected)
        for words, expected in ((14, True), (15, False), (25, False)):
            with self.subTest(english_words=words):
                self.assertEqual(qg._effect_claim("Fatigue absolutely " + "a " * words + "eliminates", "en") is not None, expected)       # 부사가 먼저
                self.assertEqual(qg._effect_claim("Fatigue eliminates " + "a " * words + "absolutely", "en") is not None, expected)     # 동사가 먼저

    def test_the_effect_claim_function_reports_the_three_words(self):
        self.assertEqual(qg._effect_claim("피로를 즉시 줄이는 방법", "ko"), ("피로", "즉시", "줄이"))
        self.assertEqual(qg._effect_claim("This chair completely eliminates back pain.", "en"), ("pain", "completely", "eliminates"))
        self.assertIsNone(qg._effect_claim("피로를 줄이는 방법", "ko"))                            # 부사가 없다
        self.assertIsNone(qg._effect_claim("즉시 확인하는 방법", "ko"))                           # 증상이 없다
        self.assertIsNone(qg._effect_claim("줄이는 방법을 즉시 확인한다 피로", "ko"))              # 한국어는 부사가 효과 동사보다 앞에 와야 한다
        self.assertIsNone(qg._effect_claim("", "ko"))
        self.assertIsNone(qg._effect_claim(None, "en"))

    def test_posture_as_a_word_is_a_body_word_only_with_a_particle(self):
        self.assertIsNone(qg._effect_claim("정부는 문제를 즉시 해결하겠다는 자세다", "ko"))
        self.assertIsNone(qg._effect_claim("자세히 보면 문제를 즉시 해결한다", "ko"))
        self.assertIsNotNone(qg._effect_claim("자세를 바로 교정한다", "ko"))

    def test_general_sentences_stay_unheld(self):
        generals = ("연준은 기준금리를 동결했다고 밝혔다.", "이번 보고서는 2026년 3분기 무역 통계를 정리한 것이다.", "NASA는 새 탐사선의 발사 일정을 공개했다.", "이 책상은 높이를 조절할 수 있어 작업 환경을 바꾸기 쉽다.",
                    "암호화 알고리즘은 암호를 보호하는 데 쓰인다.", "정부는 재생에너지 보급 계획을 반드시 이행하겠다고 밝혔다.", "전문가들은 이 정책이 효과를 낼 것이라고 분명히 말했다.", "이 위성은 반드시 정해진 궤도를 유지해야 한다.",
                    "배터리 수명이 절대 줄지 않는다는 주장은 입증되지 않았다.", "코로나19 이후 재택근무가 확산되었다.", "이 연구는 확실히 새로운 결과를 보여 준다.", "회의는 다음 주 화요일에 열릴 예정이다.",
                    "반도체 수출은 전년 대비 늘었고 정부는 지원을 약속했다.", "이 서비스는 무료이며 가입은 간단하다.", "스트레스를 풀려면 걷기가 도움이 될 수 있다.",
                    "수면 시간이 짧으면 집중력이 떨어질 수 있다는 연구가 있다.", "운동은 건강에 좋다고 알려져 있다.", "야근을 줄이면 직원 만족도가 높아졌다는 조사 결과가 나왔다.",
                    "금융 스트레스 테스트를 완전히 통과한 은행이 늘었다.", "정부가 지원금을 즉시 지급하기로 했다.", "공장은 불량을 완전히 없애는 공정을 도입했다.", "도로 정체를 확실히 줄이는 방법이 발표됐다.")
        for sentence in generals:
            with self.subTest(sentence=sentence):
                self.assertEqual(self.in_body(sentence), [], sentence)

    def test_a_consultation_phrase_does_not_excuse_an_efficacy_claim(self):
        held = ("전문의와 상담하면 당뇨를 완치할 수 있습니다.", "의사와 상담하지 않아도 영양제만으로 당뇨가 낫습니다.", "의사의 도움 없이 이 영양제로 불면이 바로 치료됩니다.", "병원 방문 없이도 이 영양제로 암이 낫습니다.",
                "병원에 가지 않아도 이 영양제로 암이 낫습니다.", "이 영양제는 당뇨를 완치합니다.", "의사와 상담하세요. 이 영양제는 당뇨를 완치합니다.", "이 영양제는 불면을 치료합니다(전문가 상담 필요).",
                "약사에게 문의하면 이 약이 혈압을 100% 낮춘다고 합니다.", "전문가와 상담하세요. 이 보충제는 만병통치입니다.", "의사와 상의하면 피로를 즉시 없앨 수 있습니다.")
        for sentence in held:
            with self.subTest(sentence=sentence):
                self.assertTrue(self.in_body(sentence), sentence)
        for sentence in ("Talk to your doctor, because this pill is a miracle cure.", "Ask your pharmacist; this supplement has no side effects."):
            with self.subTest(sentence=sentence):
                self.assertTrue(self.in_body(sentence, "en"), sentence)

    def test_an_ordinary_consultation_notice_is_still_excused(self):
        for sentence in ("증상이 계속되면 의사와 상담하세요.", "이 글은 진단이나 치료를 대신하지 않으며 전문가와 상담하시기 바랍니다.", "Talk to your doctor if the symptoms continue."):
            with self.subTest(sentence=sentence):
                self.assertEqual(self.in_body(sentence, "en" if sentence.isascii() else "ko"), [], sentence)

    def test_the_profile_efficacy_list_is_applied_to_the_title_and_the_whole_body_without_exemption(self):
        for title in ("기적의 식단 이야기", "만병통치 습관", "이 방법은 특효가 있다"):
            with self.subTest(title=title):
                found = qg.rule_health("ko", title, qg.prose_of(body_with("평범한 문장입니다.")), self.PROFILES)
                self.assertTrue(found, title)
        self.assertTrue(qg.rule_health("en", "A miracle morning routine", qg.prose_of(body_with("Plain sentence here.")), self.PROFILES))
        for profile in self.PROFILES:
            patterns = profile["banned_patterns"]
            self.assertTrue(patterns)                                                          # 프로필에 효능 단정 목록이 있다

    def test_the_assertion_words_include_cure_and_a_spaced_percent_but_not_immediacy(self):
        for sentence in ("이 약이 혈압을 100% 낮춘다고 합니다.", "당뇨는 완치된다고 합니다"):
            with self.subTest(sentence=sentence):
                self.assertIn("QG4-ASSERT", self.in_body(sentence))
        # 즉시·바로 는 행동 순서를 꾸밀 수 있어 단정 낱말이 아니다(증상 + 즉각 + 효과 동사일 때만 QG4-CLAIM)
        self.assertEqual(self.in_body("통증이 있을 때 즉시 쉬는 시간을 기록해 두는 방법"), [])
        self.assertEqual(self.in_body("If the pain persists, call a doctor immediately."), [])

    def test_a_claim_is_reported_with_its_own_code_and_a_readable_reason(self):
        found = qg.rule_health("ko", NEUTRAL_TITLE, qg.prose_of(body_with("통증을 완전히 없애는 의자 선택법")), self.PROFILES)
        claim = [hold for hold in found if hold.code == "QG4-CLAIM"]
        self.assertEqual(len(claim), 1)
        self.assertIn("통증", claim[0].message)
        self.assertIn("완전히", claim[0].message)
        self.assertIn("본문", claim[0].message)
        title_found = qg.rule_health("ko", "통증을 완전히 없애는 의자 선택법", qg.prose_of(body_with("평범한 문장입니다.")), self.PROFILES)
        self.assertIn("제목", [hold for hold in title_found if hold.code == "QG4-CLAIM"][0].message)

    def test_the_profiles_are_not_changed_by_the_checks(self):
        import copy
        before = copy.deepcopy(self.PROFILES)
        for sentence in self.OPERATOR_C + self.VARIANTS:
            self.in_body(sentence)
            self.as_title(sentence)
        self.assertEqual(self.PROFILES, before)

    def test_the_whole_flow_holds_a_claim_in_the_title_and_the_body_with_the_claim_code(self):
        data = h.make_data(ko=h.ko_body(extra="통증을 완전히 없애는 의자 선택법을 소개합니다."), ko_title="통증을 완전히 없애는 의자 선택법")
        found = h.run_gate(data=data, config=h.make_config(("ko",))).codes()
        self.assertIn("QG4-CLAIM", found)


# ----------------------------------------------------------------------------------------------------------------------------------
# D10: 2차 독립 검증의 생존 변이(U03·U05·U06·U13·U14·U15·U27)가 가리킨 시험 공백 — 상수·경계를 입력으로 못박는다(번호는 gatev2/verification.md §5-1)
# ----------------------------------------------------------------------------------------------------------------------------------
class SecondVerificationGapsTest(unittest.TestCase):
    def test_u03_the_window_between_a_consult_word_and_its_negation_is_fourteen_chars(self):
        near, far = "의사" + "가" * 14 + "않아도", "의사" + "가" * 15 + "않아도"
        self.assertIsNotNone(qg._NEGATED_CONSULT.search(near))
        self.assertIsNone(qg._NEGATED_CONSULT.search(far))
        profiles = h.health_profiles()
        for sentence in ("병원에 가서 진료를 받지 않아도 이 영양제만 드시면 됩니다.", "의사에게 가서 물어보지 않고도 이 영양제를 드시면 됩니다.", "전문가에게 자세히 상담받는 과정을 거치지 않아도 이 영양제를 드세요."):
            with self.subTest(sentence=sentence):
                found = qg.rule_health("ko", NEUTRAL_TITLE, qg.prose_of(body_with(sentence)), profiles)
                self.assertEqual(codes(found), ["QG4-HEALTH"])
                self.assertIn("상담을 부정하는", found[0].message)                           # 상담 안내 문장이 아니라 상담을 건너뛰라는 권유

    def test_u05_the_marker_candidate_cap_is_twenty_and_never_changes_the_result(self):
        """상한은 시간 방어일 뿐 결과를 바꾸지 않는다: 뒤쪽 표지가 탈락하면(꼬리가 길면) 앞쪽 표지의 꼬리는 그 꼬리를 포함하므로 늘 더 길다. 그래서 값은 상수와 호출 횟수로 못박는다."""
        self.assertEqual(qg.MAX_MARKER_CANDIDATES, 20)
        body = f"{plain(300)}\n\n" + "출처:\n" * 31 + plain(qg.TAIL_MAX_CHARS + 200)
        with mock.patch.object(qg, "_end_zone_ok", wraps=qg._end_zone_ok) as spy:
            qg.split_story(body)
        self.assertEqual(spy.call_count, 20)
        kinds = ("출처:", "- 출처:", "  출처:", "- [A](https://www.example.gov/a)", "가" * (qg.TAIL_MAX_CHARS + 100), "")
        checked = 0
        for size in range(1, 6):
            for combo in itertools.product(kinds, repeat=size):
                text = "본문 문장입니다.\n" + "\n".join(combo)
                with mock.patch.object(qg, "MAX_MARKER_CANDIDATES", 1):
                    capped = qg.split_story(text)
                with mock.patch.object(qg, "MAX_MARKER_CANDIDATES", 10 ** 6):
                    unlimited = qg.split_story(text)
                self.assertEqual(capped, unlimited, combo)
                checked += 1
        self.assertEqual(checked, sum(len(kinds) ** n for n in range(1, 6)))

    def test_u06_a_tail_of_exactly_six_hundred_readable_chars_is_still_a_tail(self):
        self.assertEqual(qg.TAIL_MAX_CHARS, 600)
        for length, is_end in ((599, True), (600, True), (601, False)):
            with self.subTest(length=length):
                self.assertEqual(qg.readable_length("가" * length), length)
                body = f"{plain(1100)}\n\n### 출처\n- [A]({LINK})\n\n" + "가" * length
                self.assertEqual(bool(qg.split_story(body).block), is_end)

    def test_u13_a_thousands_comma_before_a_percent_is_not_a_decimal_comma(self):
        self.assertEqual([(n.kind, n.value) for n in qg.extract_figures("3,500%").nums], [("pct", Decimal(3500))])
        self.assertEqual([(n.kind, n.value) for n in qg.extract_figures("3,500 %").nums], [("pct", Decimal(3500))])
        self.assertEqual([(n.kind, n.value) for n in qg.extract_figures("3,5%").nums], [("pct", Decimal("3.5"))])
        self.assertEqual([(n.kind, n.value) for n in qg.extract_figures("3,50 %").nums], [("pct", Decimal("3.5"))])
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("수익률은 3,500%였다."), "The return was 3500%.", AS_OF)), [])          # 표기만 다른 같은 값
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("수익률은 3,5%였다."), "The return was 3.5%.", AS_OF)), [])
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("수익률은 3,500%였다."), "The return was 3.5%.", AS_OF)), ["QG1-NUMBER"])      # 3500% 와 3.5% 는 다른 값

    def test_u14_a_committee_before_a_title_is_not_a_person_named_committee(self):
        for text in ("위원회 위원장은 발표했다.", "위원회 대변인은 말했다.", "이 위원회 위원장은 말했다.", "위원회 의장은 말했다.", "위원회 사무총장은 말했다."):
            with self.subTest(text=text):
                self.assertEqual(qg._titled_people(text), ([], []))

    def test_u15_a_two_character_quote_with_a_speaker_cue_is_a_quote_and_a_one_character_one_is_not(self):
        self.assertEqual(qg.QUOTE_CUE_MIN_CHARS, 2)
        self.assertEqual([inner for inner, _pos in qg._quotes('장관은 "중단"이라고 밝혔다.')], ["중단"])
        self.assertEqual(qg._quotes('그는 "가"라고 말했다.'), [])
        self.assertEqual(codes(qg.rule_quotes("ko", qg.prose_of('장관은 "중단"이라고 밝혔다.'), "The agency published a report.")), ["QG2-QUOTE"])          # 근거에 없는 두 글자 인용

    def test_u27_the_year_range_is_1900_to_2100(self):
        for text, kind in (("1899", "num"), ("1900", "year"), ("2100", "year"), ("2101", "num"), ("2150", "num")):
            with self.subTest(text=text):
                self.assertEqual([n.kind for n in qg.extract_figures("올해 " + text + " 입니다").nums], [kind])
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("총 2150 기록이다"), "records: 2,150", AS_OF)), [])           # 연도로 읽지 않고 건수로 읽으므로 근거의 2,150 이 받쳐 준다
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("총 2150 기록이다"), "records: 2,151", AS_OF)), ["QG1-NUMBER"])

    def test_d6a_a_money_figure_is_backed_by_the_same_number_when_the_source_has_no_currency_at_all(self):
        """한계(의도된 동작, docs/QUALITY_GATE.md §9): 근거에 통화 표시가 하나도 없으면 같은 값의 수가 금액을 받쳐 준다 — 원문이 단위를 적지 않은 표의 표기 차이와 환산을 가를 수 없기 때문이다.
        근거에 다른 통화가 하나라도 있으면 환산 의심으로 보류한다."""
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("매출은 5,000달러였다."), "Total sales: 5,000 units.", AS_OF)), [])
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("매출은 5,000달러였다."), "Total sales: $5,000.", AS_OF)), [])
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("매출은 5,000달러였다."), "Total sales: 5,000 euros.", AS_OF)), ["QG1-CONVERSION"])
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("매출은 5,000달러였다."), "Total sales: 5,000 euros; 5,000 units shipped.", AS_OF)), ["QG1-CONVERSION"])          # 다른 통화가 있으면 같은 값의 건수가 있어도 환산 의심
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("매출은 5,000달러였다."), "Total sales: 6,000 units.", AS_OF)), ["QG1-CONVERSION"])
        self.assertEqual(codes(qg.rule_numbers("ko", qg.prose_of("매출은 5,000달러였다."), "No figures here.", AS_OF)), ["QG1-CONVERSION"])


if __name__ == "__main__":
    unittest.main()
