"""최소 품질 Gate(pipeline/quality_gate.py)의 규칙별 시험: 통과 예문·탈락 예문·경계값·빈 입력. 순수 모듈이라 네트워크·파일 없이 돈다.

감사에서 실제로 나온 오류의 모양(원문에 없는 원화 환산, 원문에 없는 직함 인용, 제목의 '추이'가 본문에 없음, 출처 목록이 본문 분량으로 세어짐)을 예문으로 쓴다.
기관·사람·제품 이름은 모두 지어낸 것이다.
"""
import ast
import datetime
import time
import unittest
from decimal import Decimal
from unittest import mock
from urllib.parse import urlsplit

import _bootstrap
import generator
import quality_gate_helpers as h
from pipeline import quality_gate as qg

ROOT = _bootstrap.ROOT
MODULE = ROOT / "pipeline" / "quality_gate.py"


def codes(holds):
    return [hold.code for hold in holds]


def figures(text, strict=True):
    found = qg.extract_figures(text, strict)
    return [(n.kind, n.value, n.cur) for n in found.nums], [(d.y, d.m, d.d) for d in found.dates]


class TextHelperTest(unittest.TestCase):
    def test_front_matter_split_and_title(self):
        front, body = qg.split_front('---\nlayout: post\ntitle: "제목: 하나"\n---\n\n본문입니다.\n')
        self.assertEqual(qg.front_title(front), "제목: 하나")
        self.assertEqual(body.strip(), "본문입니다.")
        self.assertEqual(qg.split_front("머리말 없음"), ("", "머리말 없음"))
        self.assertEqual(qg.split_front(None), ("", ""))
        self.assertEqual(qg.front_title(""), "")
        self.assertEqual(qg.front_title("title: 따옴표 없는 제목"), "따옴표 없는 제목")

    def test_every_source_list_shape_is_cut_from_the_real_body(self):
        body = "첫 문단입니다. 내용이 있습니다.\n\n둘째 문단입니다."
        tails = ("## 출처\n- [a](https://x.example/a)", "### 출처\n- [a](https://x.example/a)", "#### Source\n- [a](https://x.example/a)",
                 "**출처**\n- [a](https://x.example/a)", "**Sources:**\n- [a](https://x.example/a)", "__출처__\n- a", "출처:\n- [a](https://x.example/a)",
                 "출처: [a](https://x.example/a)", "---\n\n### 출처 및 참고 자료\n- a", "## 참고 자료\n- a", "### References\n- a", "## Sources\n- a",
                 "**참고자료**\n- a", "### 참고 문헌\n- a", "# 원문 출처\n- a", "### Further reading\n- a", "### 출처 목록\n- a",
                 "**출처** - [a](https://x.example/a)", "**출처** – [a](https://x.example/a)", "**Sources** — [a](https://x.example/a)", "__출처__ - a")      # 굵은 글씨 라벨 + 줄표로 이어지는 모양
        for tail in tails:
            with self.subTest(tail=tail.splitlines()[0]):
                self.assertEqual(qg.story_of(f"{body}\n\n{tail}").strip(), body)

    def test_the_rule_line_and_blank_lines_before_the_source_list_are_removed_too(self):
        self.assertEqual(qg.story_of("본문\n\n\n---\n\n### 출처\n- a"), "본문")
        self.assertEqual(qg.story_of("본문\n\n***\n### 출처\n- a"), "본문")

    def test_headings_that_only_start_with_a_label_are_not_source_lists(self):
        for line in ("### 출처와 한계", "### 관련 자료", "### 참고할 점", "출처는 연준이라고 합니다.", "**중요**", "## Sources of growth",
                     "**출처**에 따르면 증가했다", "**출처** 는 연준이다", "**Sources** say it rose"):      # 굵은 글씨 라벨 뒤가 문장으로 이어지면 목록이 아니라 본문이다
            with self.subTest(line=line):
                self.assertEqual(qg.story_of(f"앞 문단\n\n{line}\n\n뒤 문단").strip(), f"앞 문단\n\n{line}\n\n뒤 문단")

    def test_text_without_any_marker_is_returned_whole_and_empty_input_is_empty(self):
        self.assertEqual(qg.story_of("문단 하나"), "문단 하나")
        self.assertEqual(qg.story_of(""), "")
        self.assertEqual(qg.story_of(None), "")

    def test_readable_length_gives_the_same_verdict_as_the_generators_body_check(self):
        link = "https://x.example/l"
        front = "---\nlayout: post\ntitle: \"t\"\ncategory: \"c\"\ntags: []\n---\n\n"
        texts = ("[링크 글자](https://x.example/a) 본문 *강조* 입니다. ![그림](https://x.example/i.png) <b>태그</b> 와 `코드` 와 | 표 | " * 30, "가" * 999, "가" * 1000,
                 "나 " * 600, "나 " * 499)
        for text in texts:
            body = text + f"\n\n[원문]({link})"
            enough = qg.readable_length(body) >= generator.MIN_BODY_CHARS["kr"]
            with self.subTest(length=qg.readable_length(body)):
                if enough:
                    generator._validate_editorial_body(front + body, "kr", link)
                else:
                    with self.assertRaises(ValueError):
                        generator._validate_editorial_body(front + body, "kr", link)

    def test_min_body_chars_equal_the_generators(self):
        self.assertEqual(qg.MIN_BODY_CHARS["ko"], generator.MIN_BODY_CHARS["kr"])
        self.assertEqual(qg.MIN_BODY_CHARS["en"], generator.MIN_BODY_CHARS["en"])

    def test_prose_drops_code_images_link_targets_and_markup_but_keeps_link_text(self):
        prose = qg.prose_of("## 제목\n\n- 항목 [링크](https://x.example/a?n=123) 와 `코드 99` ![그림 77](https://x.example/i.png)\n\n```\n블록 55\n```\n")
        self.assertIn("링크", prose)
        for gone in ("123", "99", "77", "55", "http", "```", "##"):
            self.assertNotIn(gone, prose)


class NumberExtractionTest(unittest.TestCase):
    def test_korean_big_number_units(self):
        cases = (("약 4조 2천억 원이", Decimal(4200000000000), "KRW"), ("합의금 4,975만 달러를", Decimal(49750000), "USD"), ("2천만 원", Decimal(20000000), "KRW"),
                 ("3억 5천만 원", Decimal(350000000), "KRW"), ("28.8억 유로", Decimal(2880000000), "EUR"), ("1조 2,500억 원", Decimal(1250000000000), "KRW"),
                 ("4만 8,200달러", Decimal(48200), "USD"), ("4만 8천 달러", Decimal(48000), "USD"), ("3.5조 원", Decimal(3500000000000), "KRW"))
        for text, value, cur in cases:
            with self.subTest(text=text):
                nums, _ = figures(text)
                self.assertEqual(nums, [("money", value, cur)])

    def test_korean_units_that_are_really_other_words_are_not_units(self):
        for text, expected in (("100만큼 늘었다", [Decimal(100)]), ("5원칙을 세웠다", []), ("3억울한", []), ("5조건을 달았다", []), ("1천연가스 사업", [])):
            with self.subTest(text=text):
                nums, _ = figures(text)
                self.assertEqual([n[1] for n in nums], expected, nums)

    def test_english_scales_currency_and_percent_forms(self):
        self.assertEqual(figures("pay $49.75 million to settle")[0], [("money", Decimal("49750000.00"), "USD")])
        self.assertEqual(figures("2.9 billion euros and €600 million")[0], [("money", Decimal("2900000000.0"), "EUR"), ("money", Decimal("600000000"), "EUR")])
        self.assertEqual(figures("12.5% and 12 percent and 5 percentage points")[0], [("pct", Decimal("12.5"), ""), ("pct", Decimal(12), ""), ("pct", Decimal(5), "")])
        self.assertEqual(figures("fullwidth １２．５％")[0], [("pct", Decimal("12.5"), "")])

    def test_dates_are_read_and_their_digits_are_not_counted_twice(self):
        nums, dates = figures("2026년 11월 4일 발표, 11월 5일, 2025년 대비, 11월, Nov. 5, March 2025, 4 November 2026, 2026-11-04")
        self.assertEqual(nums, [])
        self.assertEqual(set(dates), {(2026, 11, 4), (None, 11, 5), (None, 11, None), (2025, None, None), (2025, 3, None)})
        self.assertEqual(len(dates), 8)

    def test_small_integers_and_identifiers_are_not_claims_but_units_make_them_claims(self):
        for text in ("3개 주와 10가지와 31명", "5G 네트워크와 H5N1 과 CO2 와 4K", "1) 첫째 2) 둘째", "21st century", "24/7 서비스"):
            with self.subTest(text=text):
                self.assertEqual(figures(text)[0], [])
        for text in ("5 km", "20 mg", "15℃", "32명", "1,200건", "0.5배", "1999년의 일", "3.5조"):
            with self.subTest(text=text):
                self.assertTrue(figures(text)[0] or figures(text)[1], text)

    def test_loose_mode_keeps_small_numbers_and_identifiers_for_the_source_side(self):
        values = {n.value for n in qg.extract_figures("5G and H5N1 and 3 projects", strict=False).nums}
        self.assertTrue({Decimal(5), Decimal(3)} <= values)

    def test_english_number_words_are_read_with_their_kind(self):
        read = [(value, kind, scaled) for value, kind, _cur, scaled, _raw in qg._word_numbers("twenty-five percent of two million people and three hundred")]
        self.assertEqual(sorted(read), [(Decimal(25), "pct", False), (Decimal(300), "num", True), (Decimal(2000000), "num", True)])
        money = qg._word_numbers("paid five hundred dollars")
        self.assertEqual([(value, kind, cur) for value, kind, cur, _s, _r in money], [(Decimal(500), "money", "USD")])

    def test_english_number_words_are_claims_in_the_body_only_when_big(self):
        """본문: 큰 단위(hundred·thousand·million …)가 있거나 32 이상인 영어 숫자 낱말만 주장으로 센다. 작은 낱말(one·two·twenty)은 세지 않는다."""
        nums = lambda text: [(n.kind, n.value) for n in qg.extract_figures(text, strict=True).nums]      # noqa: E731
        self.assertEqual(nums("three million people and forty percent and two projects"), [("num", Decimal(3000000)), ("pct", Decimal(40))])
        self.assertEqual(nums("one or two of twenty-five items"), [])
        self.assertEqual(qg.extract_figures("three million people", strict=False).nums, [])      # 근거 쪽은 _Evidence 가 따로 읽는다

    def test_empty_and_none_input(self):
        self.assertEqual(figures(""), ([], []))
        self.assertEqual(figures(None), ([], []))

    def test_dates_with_impossible_parts_are_not_dates(self):
        self.assertEqual(figures("2026년 13월 45일 그리고 20월")[1], [(2026, None, None)])      # 연도만 남는다 — 13월·45일·20월은 날짜가 아니다
        self.assertEqual(figures("13월 45일과 99월")[1], [])


class NumberRuleTest(unittest.TestCase):
    EVIDENCE = qg.evidence_text(h.fixture_source()).text

    def hold_codes(self, prose, evidence=None, as_of=h.AS_OF):
        return codes(qg.rule_numbers("ko", prose, self.EVIDENCE if evidence is None else evidence, as_of))

    def test_figures_that_are_in_the_source_pass_in_any_notation(self):
        prose = ("2026년 11월 4일 조사에서 가구 1,250,000가구, 2025년 중위 소득 3.4%, 4만 8,200달러, 12.5퍼센트. "
                 "１,２５０,０００ 도 같은 수이고 3.4 퍼센트 와 3.4% 도 같다.")
        self.assertEqual(self.hold_codes(prose), [])

    def test_number_words_in_the_source_count_as_digits(self):
        self.assertEqual(self.hold_codes("가구의 25%가 해당합니다.", "One quarter... twenty-five percent of households said so."), [])

    def test_a_korean_won_conversion_that_is_not_in_the_source_is_held(self):
        evidence = "The call received requests for 2.88 billion euros against 600 million euros available."
        self.assertEqual(self.hold_codes("요청액은 약 4조 2천억 원에 이릅니다.", evidence), ["QG1-CONVERSION"])
        self.assertEqual(self.hold_codes("요청액은 28.8억 유로입니다.", evidence), [])

    def test_a_currency_swap_with_the_same_digits_is_a_conversion(self):
        self.assertEqual(self.hold_codes("합의금은 3,000만 원입니다.", "The firm will pay 30 million euros."), ["QG1-CONVERSION"])
        self.assertEqual(self.hold_codes("합의금은 3,000만 유로입니다.", "The firm will pay 30 million euros."), [])

    def test_derived_and_rounded_values_are_held(self):
        evidence = "Employment was 71 percent in 2025 and 69 percent in 2024."
        self.assertEqual(self.hold_codes("고용률은 2%포인트 올랐습니다.", evidence), ["QG1-NUMBER"])
        self.assertEqual(self.hold_codes("고용률은 약 70%입니다.", evidence), ["QG1-NUMBER"])
        self.assertEqual(self.hold_codes("고용률은 71%였습니다.", evidence), [])

    def test_a_number_that_is_not_in_the_source_is_held_and_named(self):
        holds = qg.rule_numbers("ko", "표본은 1,300,000가구였습니다.", self.EVIDENCE)
        self.assertEqual(codes(holds), ["QG1-NUMBER"])
        self.assertIn("1,300,000", holds[0].message)

    def test_dates_are_checked_against_the_source_dates(self):
        self.assertEqual(self.hold_codes("11월 4일에 나왔습니다."), [])
        self.assertEqual(self.hold_codes("11월 5일에 나왔습니다."), ["QG1-NUMBER"])
        self.assertEqual(self.hold_codes("2024년 값과 비교합니다."), ["QG1-NUMBER"])
        self.assertEqual(self.hold_codes("2026년 11월 6일이었습니다."), ["QG1-NUMBER"])
        self.assertEqual(self.hold_codes("The 2026-11-04 release."), [])

    def test_the_run_date_is_a_known_date_and_a_publication_time_in_korea_is_too(self):
        self.assertEqual(self.hold_codes("2026년 11월 9일 기준입니다."), [])
        self.assertEqual(self.hold_codes("2026년 11월 9일 기준입니다.", as_of=None), ["QG1-NUMBER"])
        late = {"title": "t", "source": "s", "summary": "x" * 120, "published": datetime.datetime(2026, 11, 3, 20, 0, tzinfo=datetime.timezone.utc)}
        self.assertEqual(self.hold_codes("11월 4일 오전 발표입니다.", qg.evidence_text(late).text), [])      # UTC 11-03 20시 = 한국 11-04 05시

    def test_boundary_of_the_small_integer_exemption(self):
        self.assertEqual(self.hold_codes("31개 기관이 참여했습니다.", "No numbers here."), [])
        self.assertEqual(self.hold_codes("32개 기관이 참여했습니다.", "No numbers here."), ["QG1-NUMBER"])
        self.assertEqual(self.hold_codes("32개 기관이 참여했습니다.", "Thirty-two agencies took part, and 32 is the count."), [])

    def test_numbers_inside_links_and_code_are_not_claims(self):
        prose = qg.prose_of("[보도자료](https://x.example/release/2026/11/04/987654321) 와 `코드 4,444` 를 봅니다.")
        self.assertEqual(self.hold_codes(prose), [])

    def test_empty_prose_or_evidence(self):
        self.assertEqual(self.hold_codes("", ""), [])
        self.assertEqual(self.hold_codes("숫자 1,300,000 이 있다.", ""), ["QG1-NUMBER"])
        self.assertEqual(codes(qg.rule_numbers("ko", None, None)), [])


class QuoteRuleTest(unittest.TestCase):
    EVIDENCE = ('The agency said the program "will reach every county within three years" and that "costs remain low". '
                'Director Jane Marlow, the head of the survey unit, added that the sample was weighted.')

    def hold_codes(self, prose, evidence=None, lang="en"):
        return codes(qg.rule_quotes(lang, prose, self.EVIDENCE if evidence is None else evidence))

    def test_a_quote_that_is_in_the_source_passes_even_with_different_punctuation_and_case(self):
        self.assertEqual(self.hold_codes('The agency said the program “Will reach every county within three years.”'), [])

    def test_an_invented_quote_is_held(self):
        self.assertEqual(self.hold_codes('Officials said "the plan is a complete success for every household in the country".'), ["QG2-QUOTE"])

    def test_short_quoted_terms_without_a_speech_cue_are_not_quotes(self):
        self.assertEqual(self.hold_codes('The "median" is the middle value and the "poverty line" is a threshold.'), [])

    def test_a_short_quote_with_a_speech_cue_is_still_a_quote(self):
        self.assertEqual(self.hold_codes('The minister said "we will act soon on this".'), ["QG2-QUOTE"])

    def test_a_titled_person_that_is_in_the_source_passes(self):
        self.assertEqual(self.hold_codes("Director Jane Marlow explained the weighting."), [])
        self.assertEqual(self.hold_codes("Jane Marlow, the director of the unit, explained the weighting."), [])

    def test_a_titled_person_that_is_not_in_the_source_is_held(self):
        self.assertEqual(self.hold_codes("Commissioner Anton Reyes explained the weighting."), ["QG2-PERSON"])
        self.assertEqual(self.hold_codes("Director Jane Smith explained the weighting."), ["QG2-PERSON"])      # 이름은 같고 성이 다르다

    def test_a_korean_translated_quote_cannot_be_matched_so_it_is_bounded_by_the_source_quote_count(self):
        evidence = 'The agency said the program "will reach every county within three years".'
        first = '기관은 "3년 안에 모든 군에 닿을 것"이라고 밝혔습니다.'
        second = ' 또한 "모든 비용이 앞으로도 계속 낮게 유지될 것"이라고 말했습니다.'
        self.assertEqual(self.hold_codes(first, evidence, "ko"), [])                          # 원문에 인용이 하나 있다 → 번역 인용 하나는 허용
        self.assertEqual(self.hold_codes(first + second, evidence, "ko"), ["QG2-QUOTE"])      # 원문보다 인용이 많다
        self.assertEqual(self.hold_codes(first, "The agency published a summary without any quotation.", "ko"), ["QG2-QUOTE"])

    def test_a_korean_titled_name_is_bounded_by_the_titled_people_in_the_source(self):
        evidence = "Director Jane Marlow said the sample was weighted."
        self.assertEqual(self.hold_codes("조사국장 제인 말로는 표본을 가중했다고 설명했습니다.", evidence, "ko"), [])
        self.assertEqual(self.hold_codes("조사국장 제인 말로는 표본을 가중했다고 설명했습니다.", "The agency published a summary without any person named.", "ko"), ["QG2-PERSON"])
        self.assertEqual(self.hold_codes("조사국장 제인 말로와 부위원장 안톤 레예스가 설명했습니다.", evidence, "ko"), ["QG2-PERSON"])

    def test_korean_words_after_a_title_are_not_names(self):
        for text in ("국장 임명 발표가 있었습니다.", "장관 직무 대행이 맡습니다.", "교수 연구팀이 밝혔습니다.", "의원 세 명이 참석했습니다."):
            with self.subTest(text=text):
                self.assertEqual(self.hold_codes(text, "No people.", "ko"), [])

    def test_empty_input(self):
        self.assertEqual(self.hold_codes("", ""), [])
        self.assertEqual(codes(qg.rule_quotes("ko", None, None)), [])


class LinkAndLengthRuleTest(unittest.TestCase):
    def holds(self, story, lang="ko", link=h.LINK):
        return qg.rule_link_and_length(lang, story, qg.prose_of(story), link, qg.MIN_BODY_CHARS[lang])

    def test_a_long_enough_body_with_the_inline_link_passes(self):
        self.assertEqual(self.holds(qg.story_of(h.ko_body())), [])

    def test_a_source_list_that_the_old_cut_misses_no_longer_counts_as_body(self):
        thin = "통계청이 소득 조사를 공개했습니다. " * 20 + f"[원문]({h.LINK})"             # 진짜 본문은 1000자에 못 미친다
        listing = "\n".join(f"- [참고 {i}](https://x.example/{i}) 출처 설명 문장입니다 열두 글자 이상" for i in range(70))
        body = thin + "\n\n### 출처\n" + listing
        try:
            generator._validate_editorial_body(h.front("t", "ko") + body, "kr", h.LINK)
        except ValueError:
            self.fail("이 예문은 옛 검사를 통과해야 허점을 보여 준다")
        self.assertIn("QG3-LENGTH", codes(self.holds(qg.story_of(body))))

    def test_the_old_cut_misses_bold_and_deeper_headings_but_this_one_does_not(self):
        thin = "내용 문장입니다 " * 40 + f"[원문]({h.LINK})"
        for tail in ("**출처**\n", "#### 출처\n", "### 출처\n"):
            body = thin + "\n\n" + tail + "- [참고](https://x.example/a) " + "가나다라마바사 " * 150
            with self.subTest(tail=tail.strip()):
                self.assertIn("QG3-LENGTH", codes(self.holds(qg.story_of(body))))

    def test_a_link_only_in_the_source_list_is_a_missing_evidence_link(self):
        body = ("통계청이 2026년 소득 조사를 공개했습니다 " * 60) + f"\n\n### 출처\n- [원문]({h.LINK})"
        self.assertIn("QG3-LINK", codes(self.holds(qg.story_of(body))))

    def test_text_without_claims_does_not_need_a_link(self):
        story = "이것은 숫자도 이름도 없는 아주 평범한 문장입니다 " * 60
        self.assertEqual([c for c in codes(self.holds(story)) if c == "QG3-LINK"], [])

    def test_english_minimum_is_larger(self):
        self.assertIn("QG3-LENGTH", codes(self.holds(qg.story_of(h.en_body(minimum=1300)), "en")))
        self.assertEqual(self.holds(qg.story_of(h.en_body()), "en"), [])

    def test_empty_body(self):
        self.assertEqual(codes(self.holds("")), ["QG3-LENGTH"])


class HealthRuleTest(unittest.TestCase):
    PROFILES = h.health_profiles()

    def hold_codes(self, prose, title="가구 소득 조사", lang="ko"):
        return codes(qg.rule_health(lang, title, prose, self.PROFILES))

    def test_a_plain_economics_text_passes(self):
        self.assertEqual(self.hold_codes("가구 소득이 늘었고 물가도 올랐습니다. Household income rose and prices rose too."), [])

    def test_profile_keywords_hold_in_both_languages_even_inside_a_korean_text(self):
        self.assertEqual(self.hold_codes("이 약물은 우울증 환자에게 쓰입니다."), ["QG4-HEALTH"])
        self.assertEqual(self.hold_codes("The treatment for the disease is expensive.", lang="en"), ["QG4-HEALTH"])
        self.assertEqual(self.hold_codes("국문 문장 속에 ADHD 라는 말이 섞였습니다."), ["QG4-HEALTH"])

    def test_health_signal_with_an_assertion_in_the_same_paragraph_holds(self):
        self.assertIn("QG4-ASSERT", self.hold_codes("이 영양제는 반드시 도움이 됩니다."))
        self.assertIn("QG4-ASSERT", self.hold_codes("The vaccine is proven to protect.", lang="en"))

    def test_an_assertion_and_a_signal_in_different_paragraphs_do_not_trigger_the_combination(self):
        text = "반드시 확인해야 할 점은 조사 방식입니다.\n\n보건 당국은 감염 통계를 갱신했습니다."
        self.assertNotIn("QG4-ASSERT", self.hold_codes(text))

    def test_a_disclaimer_clause_is_skipped_by_the_profile_rule_but_an_assertion_in_it_still_holds(self):
        self.assertEqual(self.hold_codes("진단이나 치료를 대신하지 않습니다."), [])
        self.assertIn("QG4-ASSERT", self.hold_codes("진단이나 치료를 대신하지 않으며 반드시 전문가와 상담하세요."))

    def test_a_banned_topic_word_in_the_title_holds(self):
        self.assertEqual(self.hold_codes("평범한 본문입니다.", title="다이어트 식단의 비밀"), ["QG4-TITLE"])
        self.assertEqual(self.hold_codes("A plain text.", title="Weight loss tips", lang="en"), ["QG4-TITLE"])

    def test_the_profiles_are_used_read_only(self):
        before = repr(self.PROFILES)
        self.hold_codes("이 약물은 우울증 환자에게 쓰입니다.")
        self.assertEqual(repr(self.PROFILES), before)

    def test_empty_input(self):
        self.assertEqual(self.hold_codes("", ""), [])


class EventAndCompanyRuleTest(unittest.TestCase):
    EVENT_KO = ("올해 행사는 바르셀로나에서 개최됩니다. 참가 기관은 전시 부스를 운영하고 참석자는 현장 등록을 해야 합니다. 행사 일정은 홈페이지에 공지됩니다. "
                "컨퍼런스 참가 신청은 다음 달 마감입니다. " * 2)
    EVENT_EN = ("The expo will take place in Barcelona next week. Delegates can register for the conference and the workshop. "
                "The event agenda lists every speaker. Join us at the summit. ")

    def test_a_dense_event_announcement_is_held_in_both_languages(self):
        self.assertEqual(codes(qg.rule_event("ko", "행사 안내", self.EVENT_KO)), ["QG5-EVENT"])
        self.assertEqual(codes(qg.rule_event("en", "Event notice", self.EVENT_EN)), ["QG5-EVENT"])

    def test_a_policy_text_with_a_few_event_words_passes(self):
        prose = "정부는 등록 차량 통계를 발표했고 일정에 따라 시행합니다. " * 3 + "가구 소득 조사 결과를 읽는 법을 설명합니다. " * 30
        self.assertEqual(qg.rule_event("ko", "차량 등록 통계", prose), [])

    def test_a_single_repeated_word_is_not_enough_distinct_signals(self):
        self.assertEqual(qg.rule_event("ko", "학교", "학교 등록자 수가 늘었습니다. 등록자 수 등록 변화 등록 통계 " * 3), [])

    def test_the_title_adds_signals(self):
        total, distinct, density = qg.event_signals("스마트시티 엑스포 참가 안내 행사", "짧은 본문")
        self.assertGreaterEqual(total, 3)
        self.assertGreaterEqual(distinct, 1)
        self.assertGreater(density, 0)

    def test_empty_input(self):
        self.assertEqual(qg.rule_event("ko", "", ""), [])
        self.assertEqual(qg.event_signals(None, "")[0], 0)

    def test_public_domains_pass_including_subdomains_and_company_or_unknown_domains_hold(self):
        for domain in ("www.nasa.gov", "science.nasa.gov", "commission.europa.eu", "www.statcan.gc.ca", "www.ftc.gov", "www.federalreserve.gov", "www.gov.uk"):
            with self.subTest(domain=domain):
                self.assertEqual(qg.rule_company(domain, qg.PUBLIC_SOURCE_DOMAINS), [])
        for domain in ("www.example-company.com", "blog.example.ai", "", None, "nasa.gov.evil.example", "notnasa.gov"):
            with self.subTest(domain=domain):
                self.assertEqual(codes(qg.rule_company(domain, qg.PUBLIC_SOURCE_DOMAINS)), ["QG5-COMPANY"])

    def test_every_news_source_the_generator_reads_is_a_public_domain_except_the_excluded_ones(self):
        for source in generator.NEWS_SOURCES:
            host = urlsplit(source["url"]).hostname
            with self.subTest(source=source["name"]):
                if any(host == d or host.endswith("." + d) for d in qg.EXCLUDED_SOURCE_DOMAINS):
                    self.assertEqual(codes(qg.rule_company(host, qg.PUBLIC_SOURCE_DOMAINS)), ["QG5-COMPANY"], "새 외부 출처 방침: 이 Gate 는 자동화 제외 소스를 통과시키지 않는다")
                else:
                    self.assertEqual(qg.rule_company(host, qg.PUBLIC_SOURCE_DOMAINS), [], f"{host} 가 공공 도메인 목록에 없다 — 회사 소스를 더하는 것이면 운영자 결정이 먼저다")
        # 생성기의 신뢰 목록에는 있지만 이 Gate 가 통과시키지 않는 도메인: 읽는 소스가 아닌 언론 매체, 상업 출판사, 자동화 제외 도메인
        held_in_gate = ("reuters.com", "apnews.com", "ft.com", "bloomberg.com", "variety.com", "nytimes.com", "cell.com", "pewresearch.org")
        for lane, domains in generator.TRUSTED_SOURCE_DOMAINS.items():
            for domain in domains:
                with self.subTest(lane=lane, domain=domain):
                    verdict = codes(qg.rule_company(domain, qg.PUBLIC_SOURCE_DOMAINS))
                    self.assertEqual(verdict, ["QG5-COMPANY"] if domain in held_in_gate else [])

    def test_this_gate_does_not_let_an_excluded_domain_through_even_if_it_is_added_to_the_allowlist(self):
        self.assertEqual(qg.EXCLUDED_SOURCE_DOMAINS, ("pewresearch.org",))
        for domain in qg.EXCLUDED_SOURCE_DOMAINS:
            self.assertNotIn(domain, qg.PUBLIC_SOURCE_DOMAINS)
            for host in (domain, f"www.{domain}", f"news.{domain}"):
                with self.subTest(host=host):
                    holds = qg.rule_company(host, qg.PUBLIC_SOURCE_DOMAINS + (domain,))
                    self.assertEqual(codes(holds), ["QG5-COMPANY"])
                    self.assertIn("제외", holds[0].message)

    def test_a_generic_korean_nonprofit_suffix_and_commercial_publishers_are_not_public(self):
        for host in ("samsung.or.kr", "foundation.or.kr", "www.cell.com", "press.cell.com"):
            with self.subTest(host=host):
                self.assertEqual(codes(qg.rule_company(host, qg.PUBLIC_SOURCE_DOMAINS)), ["QG5-COMPANY"])
        self.assertEqual(qg.rule_company("www.bok.or.kr", qg.PUBLIC_SOURCE_DOMAINS), [])


class TitleRuleTest(unittest.TestCase):
    def hold_codes(self, title, prose, lang="ko"):
        return codes(qg.rule_title(lang, title, prose))

    def test_a_title_promising_a_trend_that_the_body_never_mentions_is_held(self):
        self.assertEqual(self.hold_codes("교정 시설 이후 삶: 조기 사망 추이", "사망 통계의 한 시점 값만 설명합니다."), ["QG6-TITLE-WORD"])
        self.assertEqual(self.hold_codes("Life after release: the trend in early deaths", "The release gives one value for one period.", "en"), ["QG6-TITLE-WORD"])

    def test_the_promise_is_kept_when_the_body_uses_the_word_or_its_listed_equivalent(self):
        self.assertEqual(self.hold_codes("조기 사망 추이", "연도별 추이를 표로 봅니다."), [])
        self.assertEqual(self.hold_codes("조기 사망 추이", "해마다 동향이 달랐습니다."), [])

    def test_title_numbers_must_be_in_the_body(self):
        self.assertEqual(self.hold_codes("소득 3.4% 증가", "소득이 3.4% 늘었습니다."), [])
        self.assertEqual(self.hold_codes("소득 3.4% 증가", "소득이 3.5% 늘었습니다."), ["QG6-TITLE-NUMBER"])
        self.assertEqual(self.hold_codes("2025년 소득", "2024년 소득을 다룹니다."), ["QG6-TITLE-NUMBER"])
        self.assertEqual(self.hold_codes("11월 4일 발표", "11월 5일 발표였습니다."), ["QG6-TITLE-NUMBER"])

    def test_title_numbers_in_other_notations_match(self):
        self.assertEqual(self.hold_codes("4,975만 달러 합의", "합의금은 $49.75 million 입니다."), [])
        self.assertEqual(self.hold_codes("Settlement of $49.75 million", "합의금은 4,975만 달러입니다.", "en"), [])

    def test_small_numbers_in_a_title_are_not_checked(self):
        self.assertEqual(self.hold_codes("5가지 변화와 3개 주", "본문에는 숫자가 없습니다."), [])

    def test_an_english_acronym_in_the_title_must_be_in_the_body(self):
        self.assertEqual(self.hold_codes("FTC 합의 소식", "연방거래위원회가 합의를 발표했습니다."), ["QG6-TITLE-WORD"])
        self.assertEqual(self.hold_codes("FTC 합의 소식", "연방거래위원회(FTC)가 합의를 발표했습니다."), [])
        self.assertEqual(self.hold_codes("AI 와 일", "인공지능 이야기입니다."), [])         # 두 글자 약어는 보지 않는다

    def test_empty_title_or_body(self):
        self.assertEqual(self.hold_codes("", ""), [])
        self.assertEqual(self.hold_codes(None, None), [])


class ReuseRuleTest(unittest.TestCase):
    def test_the_same_source_address_in_history_is_held_in_any_spelling(self):
        entry = {"source_url": "https://www.Example.org/news/a/?utm_source=x&b=2&a=1#top"}
        for link in ("https://example.org/news/a?a=1&b=2", "http://www.example.org/news/a/?b=2&a=1&utm_medium=y", "https://EXAMPLE.org/news/a?a=1&b=2&ixid=zz"):
            with self.subTest(link=link):
                self.assertEqual(codes(qg.rule_reuse(link, [entry])), ["QG7-REUSE"])

    def test_a_different_article_or_query_passes(self):
        history = [{"source_url": "https://example.org/news/a"}, {"source_url": "https://example.org/news/b?id=1"}]
        self.assertEqual(qg.rule_reuse("https://example.org/news/c", history), [])
        self.assertEqual(qg.rule_reuse("https://example.org/news/b?id=2", history), [])

    def test_old_history_shapes_do_not_crash(self):
        history = ["문자열 항목", {"topic": "주제"}, {"source_url": None}, {"source_url": 5}, None, 7, {"source_url": ""}]
        self.assertEqual(qg.rule_reuse("https://example.org/news/a", history), [])
        self.assertEqual(qg.rule_reuse("https://example.org/news/a", None), [])
        self.assertEqual(qg.rule_reuse("https://example.org/news/a", ()), [])

    def test_an_address_that_cannot_be_read_is_never_a_match(self):
        self.assertEqual(qg.rule_reuse("", [{"source_url": ""}]), [])
        self.assertEqual(qg.rule_reuse("not a url", [{"source_url": "not a url"}]), [])
        self.assertEqual(qg.rule_reuse(None, [{"source_url": None}]), [])

    def test_normalize_url(self):
        self.assertEqual(qg.normalize_url("HTTPS://WWW.Example.ORG:443/A/b/?z=1&a=2&utm_campaign=c#frag"), "example.org/A/b?a=2&z=1")
        self.assertEqual(qg.normalize_url("ftp://example.org/a"), "")
        self.assertEqual(qg.normalize_url("https://"), "")


class CloneRuleTest(unittest.TestCase):
    def pair(self, ko, en):
        return codes(qg.rule_clone(ko, en, qg.prose_of(ko), qg.prose_of(en))[0])

    def test_identical_structure_is_a_clone(self):
        ko = "문단 하나.\n\n### 소제목\n\n문단 둘.\n\n- 항목 가\n- 항목 나\n\n문단 셋."
        en = "Paragraph one.\n\n### Heading\n\nParagraph two.\n\n- item a\n- item b\n\nParagraph three."
        self.assertEqual(self.pair(ko, en), ["QG8-CLONE"])

    def test_different_structure_is_independent(self):
        ko = "문단 하나.\n\n### 소제목\n\n문단 둘.\n\n문단 셋."
        en = "Paragraph one.\n\nParagraph two.\n\n### Heading\n\nParagraph three.\n\n- a\n- b\n- c\n\nParagraph four.\n\nParagraph five."
        self.assertEqual(self.pair(ko, en), [])

    def test_two_matching_counts_need_a_high_number_overlap_or_no_numbers_to_compare(self):
        self.assertEqual(self.pair("한 문단.\n\n### 가\n\n둘째.\n\n- 항목", "One.\n\n### A\n\nTwo.\n\n- item\n\nExtra."), ["QG8-CLONE"])               # 두 칸 일치, 비교할 숫자 없음
        self.assertEqual(self.pair("한 문단 5%.\n\n### 가\n\n둘째 7%.\n\n- 항목", "One 90%.\n\n### A\n\nTwo 80%.\n\n- item\n\nExtra."), [])            # 두 칸 일치, 숫자 겹침 낮음
        self.assertEqual(self.pair("한 문단 5%.\n\n### 가\n\n둘째 7%.\n\n- 항목", "One 5%.\n\n### A\n\nTwo 7%.\n\n- item\n\nExtra."), ["QG8-CLONE"])    # 두 칸 일치, 숫자 겹침 높음

    def test_counts_that_are_zero_on_both_sides_carry_no_information(self):
        # 소제목도 불릿도 없는 두 글은 문단 수 하나만 정보가 있다 — 문단 수가 같아도 복제로 단정하지 않고, 달라도 '두 칸이 같다'고 우기지 않는다
        self.assertEqual(self.pair("문단 하나.\n\n문단 둘.\n\n문단 셋.", "One.\n\nTwo."), [])
        self.assertEqual(self.pair("문단 하나.\n\n문단 둘.", "One.\n\nTwo."), [])
        self.assertEqual(self.pair("하나 5%.\n\n둘 7%.\n\n셋.", "One 5%.\n\nTwo 7%."), [])

    def test_one_matching_informative_count_out_of_three_is_not_enough(self):
        self.assertEqual(self.pair("문단.\n\n### 가\n\n문단.\n\n- a", "One.\n\n### A\n\n### B\n\nTwo.\n\nThree.\n\n- a\n- b"), [])

    def test_the_detail_reports_the_counts_for_the_shadow_result(self):
        detail = qg.rule_clone("가.\n\n### 소제목\n\n나.", "A.\n\n### Heading\n\nB.", "가 나", "A B")[1]
        self.assertEqual(detail, {"structure_same": 2, "structure_dims": 2, "number_overlap": None, "ko": [1, 2, 0], "en": [1, 2, 0]})

    def test_structure_counts(self):
        self.assertEqual(qg.structure_counts("문단.\n\n## 가\n\n문단.\n\n- a\n- b\n\n1. c\n\n| 표 |\n\n![그림](x)\n\n> 인용"), (1, 2, 3))
        self.assertEqual(qg.structure_counts(""), (0, 0, 0))
        self.assertEqual(qg.structure_counts(None), (0, 0, 0))

    def test_number_overlap(self):
        self.assertEqual(qg.number_overlap("3.4% 와 1,250,000", "3.4% and 1,250,000"), 1.0)
        self.assertEqual(qg.number_overlap("3.4%", "5.5%"), 0.0)
        self.assertIsNone(qg.number_overlap("숫자 없음", "no numbers"))


class CheckCandidateTest(unittest.TestCase):
    def test_the_fixture_passes_every_rule(self):
        report = h.run_gate()
        self.assertTrue(report.passed, report.lines())
        self.assertEqual(report.summary(), "품질 Gate 통과")
        self.assertEqual(report.facts["source_text_chars"], len(h.SUMMARY))
        self.assertGreaterEqual(report.facts["body_chars_ko"], 1000)

    def test_each_rule_fires_on_its_own_variant(self):
        variants = {
            "QG1-NUMBER": h.make_data(ko=h.ko_body().replace("1,250,000가구", "1,300,000가구")),
            "QG1-CONVERSION": h.make_data(ko=h.ko_body(extra="필요한 금액은 약 4조 2천억 원입니다.")),
            "QG2-QUOTE": h.make_data(en=h.en_body(extra='Officials said "the plan is a complete success for every household in the country".')),
            "QG2-PERSON": h.make_data(en=h.en_body(extra="Commissioner Anton Reyes explained the weighting.")),
            "QG3-LENGTH": h.make_data(ko=h.ko_body(minimum=800)),
            "QG3-LINK": h.make_data(ko=h.ko_body(link="https://x.example/other")),
            "QG4-HEALTH": h.make_data(ko=h.ko_body(extra="이 약물은 우울증 환자에게 쓰입니다.")),
            "QG5-EVENT": h.make_data(ko=h.ko_body(extra=EventAndCompanyRuleTest.EVENT_KO)),
            "QG6-TITLE-WORD": h.make_data(ko_title="가구 소득 조사: 2025년 중위 소득 3.4% 증가 추이"),
            "QG6-TITLE-NUMBER": h.make_data(ko_title="가구 소득 조사: 2025년 중위 소득 3.5% 증가"),
            "QG8-CLONE": h.make_data(en=h.ko_body().replace("통계청이", "The office").replace("### 무엇을 읽어야 하나", "### Heading")),
        }
        for code, data in variants.items():
            with self.subTest(code=code):
                self.assertIn(code, h.run_gate(data=data).codes())
        self.assertIn("QG5-COMPANY", h.run_gate(source=h.fixture_source(publisher_domain="www.example-company.com")).codes())
        self.assertIn("QG7-REUSE", h.run_gate(history=[{"source_url": h.LINK + "?utm_source=x"}]).codes())

    def test_every_rule_family_is_exercised_by_the_variants_above(self):
        self.assertEqual({int(code[2]) for code in ("QG1-NUMBER", "QG2-QUOTE", "QG3-LINK", "QG4-HEALTH", "QG5-EVENT", "QG6-TITLE-WORD", "QG7-REUSE", "QG8-CLONE")}, set(range(1, 9)))

    def test_all_holds_are_collected_not_just_the_first(self):
        data = h.make_data(ko=h.ko_body(link="https://x.example/other").replace("1,250,000가구", "1,300,000가구"))
        self.assertGreaterEqual(len(h.run_gate(data=data).codes()), 2)

    def test_the_hold_summary_is_one_line_with_codes_first_and_is_bounded(self):
        data = h.make_data(ko=h.ko_body(link="https://x.example/other").replace("1,250,000가구", "1,300,000가구"))
        summary = h.run_gate(data=data).summary()
        self.assertTrue(summary.startswith("품질 Gate 보류 ["))
        self.assertNotIn("\n", summary)
        self.assertLessEqual(len(summary), 400)

    def test_require_pass_raises_a_value_error_subclass_carrying_the_report(self):
        report = h.run_gate(data=h.make_data(ko=h.ko_body(link="https://x.example/other")))
        with self.assertRaises(qg.QualityHold) as caught:
            qg.require_pass(report)
        self.assertIsInstance(caught.exception, ValueError)
        self.assertIs(caught.exception.report, report)
        self.assertTrue(qg.require_pass(h.run_gate()).passed)

    def test_korean_only_ignores_the_english_text_and_the_pair_rule(self):
        data = h.make_data(en="")
        data["en_content"] = ""
        self.assertTrue(h.run_gate(data=data, config=h.make_config(("ko",))).passed)
        broken_en = h.make_data(en=h.en_body(link="https://x.example/other"))
        self.assertIn("QG3-LINK", h.run_gate(data=broken_en).codes())
        self.assertTrue(h.run_gate(data=broken_en, config=h.make_config(("ko",))).passed)
        clone = h.make_data(en=h.ko_body())
        self.assertNotIn("QG8-CLONE", h.run_gate(data=clone, config=h.make_config(("ko",))).codes())

    def test_a_missing_or_empty_source_fails_closed(self):
        for source in ({}, "문자열", {"title": "", "summary": ""}):
            with self.subTest(source=source):
                self.assertIn("QG0-NO-SOURCE", h.run_gate(source=source).codes())
        self.assertIn("QG0-NO-SOURCE", qg.check_candidate(h.fixture_data(), None, config=h.make_config()).codes())

    def test_malformed_candidate_data_fails_closed_without_raising(self):
        for data in (None, "문자열", [], {}, {"kr_content": 5, "en_content": None}):
            with self.subTest(data=data):
                report = qg.check_candidate(data, h.fixture_source(), config=h.make_config())
                self.assertFalse(report.passed)
                self.assertIn("QG0-INPUT", report.codes())

    def test_an_oversized_body_is_held(self):
        data = h.make_data(ko=h.ko_body(extra="가 " * 60000))
        self.assertIn("QG0-INPUT", h.run_gate(data=data).codes())

    def test_configuration_errors_stop_instead_of_weakening_the_gate(self):
        with self.assertRaises(qg.GateConfigError):
            qg.GateConfig(health_profiles=(), languages=("ko", "en"))
        with self.assertRaises(qg.GateConfigError):
            qg.GateConfig(health_profiles=("문자열",), languages=("ko", "en"))
        for languages in (("en",), ("ko", "en", "ja"), (), ("en", "ko"), ("ko", "ko")):
            with self.subTest(languages=languages):
                with self.assertRaises(qg.GateConfigError):
                    qg.GateConfig(health_profiles=h.health_profiles(), languages=languages)
        with self.assertRaises(qg.GateConfigError):
            qg.check_candidate(h.fixture_data(), h.fixture_source(), config=None)

    def test_the_function_is_deterministic_and_does_not_change_its_inputs(self):
        data, source, history = h.fixture_data(), h.fixture_source(), [{"source_url": "https://other.example/a"}]
        before = (repr(data), repr(source), repr(history))
        config = h.make_config()
        first = qg.check_candidate(data, source, history=history, config=config, as_of=h.AS_OF)
        second = qg.check_candidate(data, source, history=history, config=config, as_of=h.AS_OF)
        self.assertEqual((first.holds, first.facts), (second.holds, second.facts))
        self.assertEqual((repr(data), repr(source), repr(history)), before)

    def test_the_gate_never_touches_files_network_or_processes(self):
        config, bad = h.make_config(), h.make_data(ko=h.ko_body(link="https://x.example/other"))
        with mock.patch("builtins.open", side_effect=AssertionError("파일을 열었다")), mock.patch("socket.socket", side_effect=AssertionError("네트워크를 열었다")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("프로세스를 열었다")), mock.patch("os.system", side_effect=AssertionError("셸을 열었다")):
            self.assertTrue(qg.check_candidate(h.fixture_data(), h.fixture_source(), config=config, as_of=h.AS_OF).passed)
            self.assertFalse(qg.check_candidate(bad, h.fixture_source(), config=config, as_of=h.AS_OF).passed)

    def test_hold_text_taken_from_the_model_is_one_line_and_cannot_forge_workflow_commands(self):
        evil = 'Officials said "::error::fake ## [group] the plan is a success\x07 for every household" today.'
        data = h.make_data(en=h.en_body(extra=evil))
        lines = h.run_gate(data=data).lines()
        self.assertTrue([line for line in lines if line.startswith("QG2-QUOTE")])
        for line in lines:
            self.assertNotIn("\n", line)
            self.assertNotIn("::error::", line)
            self.assertNotIn("\x07", line)
            self.assertNotIn("##[", line)


class EvidenceBoundaryTest(unittest.TestCase):
    """근거 텍스트는 evidence_text() 한 함수로만, 출처 신원은 source_ref() 한 함수로만 읽힌다 — 나중에 근거를 다른 모양으로 바꿔 끼우는 자리."""

    def test_evidence_text_has_what_the_prompt_gives_the_model(self):
        evidence = qg.evidence_text(h.fixture_source())
        for needle in (h.TITLE, "Example Agency", "2026-11-04T03:00:00+00:00", "2026-11-04", "1,250,000 households"):
            self.assertIn(needle, evidence.text)
        self.assertEqual(evidence.summary_chars, len(h.SUMMARY))

    def test_a_publication_time_is_given_in_utc_and_korean_dates(self):
        late = h.fixture_source(published=datetime.datetime(2026, 11, 3, 20, 0, tzinfo=datetime.timezone.utc))
        text = qg.evidence_text(late).text
        self.assertIn("2026-11-03T20:00:00+00:00", text)
        self.assertIn("2026-11-04", text)

    def test_missing_pieces_are_tolerated(self):
        self.assertEqual(qg.evidence_text(None), ("", 0))
        self.assertEqual(qg.evidence_text({}).text, "")
        self.assertEqual(qg.evidence_text({"summary": None, "title": None, "published": "문자열"}).summary_chars, 0)

    def test_only_the_two_boundary_functions_read_the_source_item_keys(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        readers = {"summary": set(), "published": set(), "link": set(), "publisher_domain": set(), "title": set()}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Constant) and isinstance(inner.value, str) and inner.value in readers:
                        readers[inner.value].add(node.name)
        self.assertEqual(readers["summary"], {"evidence_text"})
        self.assertEqual(readers["published"], {"evidence_text"})
        self.assertEqual(readers["title"], {"evidence_text"})
        self.assertEqual(readers["link"], {"source_ref"})
        self.assertEqual(readers["publisher_domain"], {"source_ref"})

    def test_source_ref(self):
        ref = qg.source_ref(h.fixture_source())
        self.assertEqual((ref.link, ref.domain, ref.name), (h.LINK, h.DOMAIN, "Example Agency"))
        self.assertEqual(qg.source_ref(None), ("", "", ""))


class RobustnessTest(unittest.TestCase):
    """R5: 정규식이 입력 길이에 지수로 느려지지 않는다(최악 모양 입력을 시간으로 잰다)."""
    LIMIT = 4.0

    def timed(self, fn, *args):
        started = time.perf_counter()
        fn(*args)
        self.assertLess(time.perf_counter() - started, self.LIMIT, "너무 오래 걸렸다")

    def test_worst_case_shapes_finish_quickly(self):
        shapes = ("1," * 40000, "3억 " * 15000, "가" * 90000, "[" * 40000, '"' * 40000, "출처" * 20000, "9" * 90000, "$" * 40000, "Dr " * 20000, "국장 가나 " * 15000,
                  "- " * 40000, "#" * 90000, "\n" * 90000, "2026년 " * 15000, "November " * 15000, "한" * 5000 + "!" * 5000)
        for shape in shapes:
            with self.subTest(shape=shape[:12]):
                for fn in (qg.extract_figures, qg.story_of, qg.prose_of, qg._quotes, qg._titled_people):
                    self.timed(fn, shape)

    def test_a_whole_check_on_a_large_but_allowed_body_is_fast(self):
        data = h.make_data(ko=h.ko_body(extra="소득 조사 결과 설명 문장입니다. " * 2500))
        config = h.make_config()
        self.timed(lambda: qg.check_candidate(data, h.fixture_source(), config=config, as_of=h.AS_OF))


class PurityTest(unittest.TestCase):
    def test_the_module_is_pure_and_not_connected_to_the_shadow_tool(self):
        text = MODULE.read_text(encoding="utf-8")
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        for banned in ("import os", "import sys", "import socket", "import subprocess", "import time", "import random", "import pathlib", "urllib.request", "import requests",
                       "open(", "quality_shadow", "msvcrt", "ctypes", "environ"):
            self.assertNotIn(banned, code, banned)

    def test_no_tilde_in_the_module_docstring(self):
        docstring = MODULE.read_text(encoding="utf-8").split('"""')[1]
        self.assertNotIn("~", docstring)


if __name__ == "__main__":
    unittest.main()
