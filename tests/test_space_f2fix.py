"""S2a 에서 고친 F2(구조화 Fact 후속 수정) 독립 검증의 낮은 지적 N2·N3·N4 시험.
 - N2: 우리말 수 표현 검사가 세는 말 바로 뒤의 서술격 '이다' 꼴(`두 가지다`·`세 곳인데`·`한 해다`·`세 가지면`·`열두 곳인데`·`두 가지예요`)도 잡는다 — 받침 없는 세는 말 뒤에서만 줄어든 꼴을 세고,
   '세는 말 + 어미' 가 흔한 낱말이 되는 짝(한 개인·한 주요·한 해고 …)은 수로 보지 않는다.
 - N3: 지역 비교(R02)에서 중앙값(짝수 곳은 가운데 두 값의 평균)과 평균·중앙값의 차이도 표시 자리의 반 칸에 걸리면 자리를 한 칸 늘린다 — `평균 3.4%, 중앙값 3.4% 인데 차이 0.1%p` 가 나오지 않는다.
 - N4: 새 시험이 못 잡던 변이 둘(수 낱말 왼쪽 경계 삭제·세는 말 `초과` 삭제)을 잡는다.
네트워크 없이 가짜 자료로만 돈다."""
import random
import re
import unittest
from decimal import Decimal

import _bootstrap  # noqa: F401
import fact_helpers as H

from pipeline import calc as C
from pipeline import fact_assembler as A
from pipeline import facts as F

SYLLABLES = "가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허"
RECORD_ID = H.mock_bundle()[1].record_id


def cross(values, *, period="2026-03", **kw):
    """같은 기준일의 지역 묶음(지역 이름은 `가상 지역 가`…)."""
    return [H.make_fact(value, period=period, region=f"R{index + 1:02d}", region_label="가상 지역 " + SYLLABLES[index % len(SYLLABLES)], record_id=RECORD_ID, **kw)
            for index, value in enumerate(values)]


def run_r02(values, **kw):
    return H.run("R02_region_compare", facts=cross(values, **kw), params={"key": kw.get("key", H.UNEMP)})


def shown(text):
    """글에 보인 숫자 글자('+0.05%p'·'−0.5명'·'1,234.5') → Decimal."""
    return Decimal(text.replace("−", "-").replace("+", "").replace(",", "").rstrip("%p명곳℃위개월분기년번"))


def mean_median_gap(post):
    """글에 보인 평균·중앙값·평균과 중앙값의 차이(문자열)."""
    line = re.search(r"- 평균: ([^(]+)\([^)]*\), 중앙값: (\S+)", post.body_markdown)
    gap = re.search(r"평균과 중앙값의 차이는 ([^ ]+)입니다", post.body_markdown)
    return line.group(1), line.group(2), gap.group(1)


def exact_median(values):
    ordered = sorted(Decimal(v) for v in values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


class MedianHalfStepTest(unittest.TestCase):
    """N3(D-152 의 확장): 평균만 보던 표시 자리 늘림을 중앙값·평균과 중앙값의 차이에도 건다."""

    def test_the_verifiers_example_shows_the_median_exactly(self):
        """값 3.3·3.3·3.4·3.6: 평균 3.4·중앙값 3.35 — 예전에는 `평균 3.4%`·`중앙값 3.4%` 인데 차이는 `0.1%p` 였다."""
        post = run_r02(["3.3", "3.3", "3.4", "3.6"])
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertEqual(dict(post.decimals), {"%": 2, "%p": 2})
        self.assertEqual(mean_median_gap(post), ("3.40%", "3.35%", "0.05%p"))
        self.assertIn("- 평균: 3.40%(4곳 단순 평균), 중앙값: 3.35%", post.body_markdown)
        self.assertIn("지역 값의 중앙값은 3.35%입니다. 평균과 중앙값의 차이는 0.05%p입니다.", post.body_markdown)
        self.assertNotIn("0.1%p", post.body_markdown)
        self.assertEqual(A.post_problems(post), [])

    def test_a_median_on_a_half_step_beside_a_mean_one_digit_further_is_followed(self):
        """값 3.3·3.4·3.5·3.5: 평균 3.425·중앙값 3.45 — 예전에는 `평균 3.4%`·`중앙값 3.5%`·차이 `0.0%p`. 중앙값이 걸려 두 자리가 되고 평균이 거기서 또 걸려 세 자리가 된다."""
        post = run_r02(["3.3", "3.4", "3.5", "3.5"])
        self.assertEqual(dict(post.decimals), {"%": 3, "%p": 3})
        self.assertEqual(mean_median_gap(post), ("3.425%", "3.450%", "0.025%p"))
        self.assertEqual(A.post_problems(post), [])

    def test_whole_number_data_with_a_median_on_a_half_gets_one_decimal(self):
        """짝수 곳의 정수 자료(명): 가운데 두 값의 평균이 4.5 이면 중앙값은 `5명` 이 아니라 `4.5명` 으로 보인다. 평균이 반 칸이 아니어도 마찬가지다."""
        kw = {"unit": "명", "key": "labour.employed_persons", "label": "취업자 수"}
        post = run_r02(["7", "6", "5", "4", "3", "1"], **kw)                 # 평균 4.33…·중앙값 4.5
        self.assertEqual(dict(post.decimals), {"명": 1})
        self.assertEqual(mean_median_gap(post)[1], "4.5명")
        self.assertIn("| 1위 | 가상 지역 가 | 7.0명 | +2.7명 |", post.body_markdown)
        neither = run_r02(["7", "6", "5", "3", "2", "1"], **kw)              # 평균 4·중앙값 4 — 어느 쪽도 반 칸이 아니다
        self.assertEqual(dict(neither.decimals), {"명": 0})
        self.assertEqual(mean_median_gap(neither), ("4명", "4명", "0명"))

    def test_a_median_that_is_not_on_a_half_step_keeps_the_table_digits(self):
        for values in (["3.3", "3.3", "3.3", "3.4"], ["3.4", "3.5", "3.5", "3.6", "3.8"], ["3.3", "3.4", "3.5", "3.5", "3.6", "3.7"]):
            with self.subTest(values=values):
                post = run_r02(values)
                self.assertEqual(dict(post.decimals), {"%": 1, "%p": 1})
                self.assertEqual(shown(mean_median_gap(post)[1]), exact_median(values))

    def test_the_median_is_shown_exactly_and_the_three_numbers_agree_in_every_post(self):
        """속성(자료 정밀도 1·2자리, 4·6·8·10곳): ① 보이는 중앙값은 정확한 중앙값과 같다 ② 보이는 평균과 보이는 중앙값이 같으면 보이는 차이는 0, 다르면 0 이 아니다 — 이 둘이 N3 가 막으려던
        '같은 값으로 보이는데 차이가 있다·다른 값으로 보이는데 차이가 0' 이다(중앙값이 정확히 보이면 평균이 반 칸에 걸리지 않는 한 두 말이 같이 선다)."""
        rng = random.Random(20261110)
        tied, checked = 0, 0
        for places, grid in ((1, ["3.3", "3.4", "3.5", "3.6"]), (2, ["3.31", "3.32", "3.33", "3.34", "3.35"])):
            for _case in range(120):
                values = [rng.choice(grid) for _ in range(rng.choice((4, 6, 8, 10)))]
                if len(set(values)) == 1:
                    continue
                post = run_r02(values)
                self.assertIsInstance(post, A.AssembledPost, (values, post))
                mean_text, median_text, gap_text = mean_median_gap(post)
                median = exact_median(values)
                tied += (median * 10 ** places) % 1 == Decimal("0.5")
                checked += 1
                self.assertEqual(shown(median_text), median, (values, median_text))
                self.assertEqual(mean_text == median_text, shown(gap_text) == 0, (values, mean_text, median_text, gap_text))
        self.assertGreaterEqual(tied, 40)                         # 중앙값이 반 칸에 걸리는 묶음을 충분히 겪었다(속성이 비어 있지 않다)
        self.assertGreater(checked, 200)

    def test_the_gap_between_mean_and_median_never_needs_a_digit_of_its_own(self):
        """평균과 중앙값의 차이를 따로 넣어도 결과가 달라지지 않는다 — 자료 정밀도의 값에서는 차이가 반 칸에 걸리려면 평균이나 중앙값이 먼저 걸려야 하기 때문이다(그래도 같은 줄에서 견주므로
        표시 자리 계산에는 넣어 둔다). 이 시험은 그 사실을 표본으로 확인한다."""
        rng = random.Random(20261111)
        grid = ["3.3", "3.4", "3.5", "3.6", "3.7"]
        for _case in range(300):
            values = [rng.choice(grid) for _ in range(rng.choice((4, 5, 6, 7, 8, 9, 10)))]
            if len(set(values)) == 1:
                continue
            group = cross(values)
            mean, median = C.f08_mean(group), C.f14_median(group)
            gap = C.f13_gap(mean, median)
            base = F.display_context(group)
            self.assertEqual(F.settle_context(base, [mean, median, gap]), F.settle_context(base, [mean, median]), values)


def has_no_final_consonant(syllable):
    """한글 음절이 받침 없이 끝나는가(가·개·해 …)."""
    return 0xAC00 <= ord(syllable) <= 0xD7A3 and (ord(syllable) - 0xAC00) % 28 == 0


NATIVE_OPEN = ("가지", "개", "해", "배", "마리", "군데", "나라", "자리", "대", "호", "주", "위", "차례", "단계", "가구", "학교")
NATIVE_CLOSED = ("곳", "명", "건", "번", "달", "살", "개월", "지역", "기간", "시간", "사람", "학급", "기관", "구간", "줄", "열", "날")          # `주일` 은 뺀다 — 주(받침 없음)+일(서술격 어미)로도 읽혀 어느 쪽이든 센다
SINO_OPEN = ("분기", "퍼센트", "포인트", "프로", "달러", "초", "이하", "초과", "번째", "배", "개", "세", "위")
SINO_CLOSED = ("곳", "명", "건", "번", "원", "년", "일", "점", "분", "이상", "미만")
SHORT_ENDINGS = ("다", "면", "며", "죠", "든", "예요", "요", "고", "지", "야")
SHORT_COLLISIONS = {("개", "요"), ("해", "요"), ("주", "요"), ("대", "요"), ("세", "요"), ("해", "고"), ("배", "고"), ("해", "지"), ("대", "지"), ("주", "지"), ("배", "지"), ("해", "야"), ("대", "야"), ("주", "야")}


class NumberWordEndingTest(unittest.TestCase):
    """N2(D-154 의 보강): 세는 말 바로 뒤에 서술격 '이다' 의 줄임꼴·연결 어미가 붙은 문장도 수 표현으로 센다. 기준선은 자연문장 25개를 모두 잡았는데 F2 의 오른쪽 경계 목록(조사·어미 시작 글자)에는
    `다·면·고·며·인·지·야·요·죠·든·예` 가 없어 13개를 놓쳤다. 줄어든 꼴은 받침 없는 세는 말 뒤에서만 세고, 흔한 낱말과 겹치는 짝은 뺀다."""
    NATURAL = ("두 가지다", "이 글은 두 가지다", "두 개다", "세 곳인데", "세 곳인지", "세 곳인가요", "한 해다", "근거는 세 가지면 충분하다", "열두 곳인데", "세 지역인데", "두 가지예요",
               "세 가지며 하나는 같다", "두 가지죠", "세 가지든 네 가지든", "두 가지야", "한 가지다", "다섯 가지다", "세 가지인 이유", "네 곳인 이유", "두 배다", "세 배면 충분하다", "열 배다",
               "두 배인 것", "삼 분기다", "십 퍼센트다", "이십 달러다", "삼 초면 된다", "세 가지고 두 곳이다", "세 단계다", "두 차례다", "세 군데다", "세 마리면", "두 나라다", "두 호다",
               "세 위다", "세 곳일 때", "두 가지일 수 있다", "세 가지요", "두 배요", "세 군데요", "세 가지지만", "두 개지만", "열두 가지다", "스무 곳이다", "한 번이다", "세 번째다", "두 차례예요",
               "세 개였다", "세 개월이다", "한 주면 된다", "다섯 곳인데도", "세 가지다고",
               "네 구간인데", "두 줄이다", "두 열은", "세 날이다", "세 구간이다", "열 줄이다", "두 열이다", "네 날인데도", "다섯 구간이면", "한 줄인지", "열두 열이었다", "열한 날이다", "스물한 날이다", "열한 줄이다")        # S2AFIX D12: 구간·줄·열·날
    COMMON = ("한 개인이 신고했다", "한 개인의 소득", "한 주요 지표", "한 주요 원인은", "한 해고 노동자", "한 해지 신청", "한 대지 위에", "한 대야 가득", "한 살인 사건", "한 달인이 되었다",
              "한 배고픈 사람", "한 개요 문서", "한 주인이 키운다", "한 배지를 달았다", "한 지역지에 실렸다", "한 위인의 일생", "한 번지 주소", "한 분야에서", "일 분야 전문가",
              "그 일 원인은", "세 대인은", "한 개인", "한 개념", "한 대표", "두 개발자", "한 위치", "한 프로그램",
              "구간별 값을 적는다", "구간이 모자란 날은 뺀다", "날씨가 좋다", "날짜를 적는다", "오늘날의 값", "줄이다", "줄어든 값", "열린 자료", "열대 지역", "열기가 식다", "이 구간을 읽는다", "그 날이 지났다",
              "생일날 값", "마지막 날의 값", "한 날씨", "줄임말", "날개 달린 값", "열쇠 낱말", "날마다 갱신된다", "줄곧 같다",
              "수동 실제 게시를 한 날은 아니다", "작업을 한 날", "글을 한 날의 값", "한 날은 쉰다", "한 날이 있다")        # 새 세는 말(구간·줄·열·날)이 들어간 흔한 말(S2AFIX D12) — 하다 의 관형형 `한` 뒤의 `날` 은 수가 아니다

    def test_the_natural_sentences_are_found(self):
        for text in self.NATURAL:
            for sample in (text, f"앞 {text} 뒤", f"{text}.", f"{text},"):
                with self.subTest(text=sample):
                    self.assertTrue(F.untraced_numbers(sample), sample)

    def test_common_words_that_begin_like_a_counter_and_an_ending_are_not_numbers(self):
        for text in self.COMMON:
            with self.subTest(text=text):
                self.assertEqual(F.untraced_numbers(text), [], text)

    def test_the_short_copula_follows_a_counter_without_a_final_consonant_only(self):
        """받침 없는 세는 말(가지·개·해·배 …) 뒤에서는 `이다` 가 줄어 `다·면·며·죠·든·예요·요·고·지·야` 가 바로 붙고, 받침 있는 세는 말(곳·명·번·달 …) 뒤에서는 `이다`·`인데`·`일 때` 가 맞아
        줄어든 꼴은 수 표현이 아니라 낱말의 일부(한 번지·한 살다·한 달다)다. 겹치는 짝(개요·해고·주요·해지·대지·해야 …)은 센 말에서 뺐다."""
        for number in ("두", "세", "네", "다섯", "열두", "스무", "한"):
            for counter in NATIVE_OPEN:
                for ending in SHORT_ENDINGS:
                    text = f"{number} {counter}{ending}"
                    with self.subTest(text=text):
                        if (counter[-1], ending) in SHORT_COLLISIONS:
                            self.assertEqual(F.untraced_numbers(text), [], text)
                        else:
                            self.assertTrue(F.untraced_numbers(text), text)
            for counter in NATIVE_CLOSED:
                for ending in SHORT_ENDINGS:
                    text = f"{number} {counter}{ending}"
                    with self.subTest(text=text):
                        self.assertEqual(F.untraced_numbers(text), [], text)
        for number in ("삼", "십", "이십", "백", "영"):
            for counter in SINO_OPEN:
                for ending in SHORT_ENDINGS:
                    text = f"{number} {counter}{ending}"
                    with self.subTest(text=text):
                        if (counter[-1], ending) in SHORT_COLLISIONS:
                            self.assertEqual(F.untraced_numbers(text), [], text)
                        else:
                            self.assertTrue(F.untraced_numbers(text), text)
            for counter in SINO_CLOSED:
                for ending in SHORT_ENDINGS:
                    text = f"{number} {counter}{ending}"
                    with self.subTest(text=text):
                        self.assertEqual(F.untraced_numbers(text), [], text)

    def test_the_copula_that_starts_with_i_is_found_after_every_counter(self):
        """받침 있는 세는 말은 `이다`·`입니다`·`였다`·`일 때`·`인데` 로 이미 `이`·`입`·`였`·`일`·`인` 으로 시작한다."""
        for number, counters in (("세", NATIVE_OPEN + NATIVE_CLOSED), ("삼십", SINO_OPEN + SINO_CLOSED)):
            for counter in counters:
                for tail in ("이다", "입니다", "였다", "일 때", "이었다", "이므로"):
                    text = f"{number} {counter}{tail}"
                    with self.subTest(text=text):
                        self.assertTrue(F.untraced_numbers(text), text)

    def test_the_adnominal_in_is_counted_except_where_the_counter_and_in_make_a_common_word(self):
        """`인`(인데·인지·인가·인걸·인즉·인 경우): 개인·주인·살인·달인·위인·대인·원인 처럼 '세는 말 + 인' 이 흔한 낱말인 끝 글자 뒤에서는 인데·인지·인가·인걸·인즉 일 때만 센다."""
        for number, counter in (("세", "곳"), ("두", "명"), ("한", "번"), ("세", "해"), ("두", "배"), ("세", "가지"), ("네", "마리"), ("세", "지역"), ("열", "시간"), ("두", "사람"), ("삼", "분기"),
                                ("네", "구간"), ("두", "줄"), ("세", "열"), ("네", "날"),
                                ("십", "퍼센트"), ("삼", "이하"), ("삼십", "점"), ("삼", "일")):
            for tail in ("인데", "인지", "인가요", "인걸", "인 경우", "인 이유", "인", "인데도"):
                with self.subTest(number=number, counter=counter, tail=tail):
                    self.assertTrue(F.untraced_numbers(f"{number} {counter}{tail}"))
        for number, counter in (("두", "개"), ("세", "주"), ("열", "살"), ("세", "달"), ("두", "위"), ("세", "대"), ("만", "원"), ("삼", "위")):
            for tail in ("인데", "인지", "인가요", "인걸", "인즉"):
                with self.subTest(number=number, counter=counter, tail=tail):
                    self.assertTrue(F.untraced_numbers(f"{number} {counter}{tail}"))
            for tail in ("인", "인 경우", "인이", "인의", "인은", "인을"):
                with self.subTest(number=number, counter=counter, tail=tail):
                    self.assertEqual(F.untraced_numbers(f"{number} {counter}{tail}"), [], f"{number} {counter}{tail}")

    def test_the_list_of_open_counter_endings_matches_the_counter_lists(self):
        """`_NUM_OPEN` 은 받침 없이 끝나는 세는 말(고유어·한자어 목록)의 끝 글자와 같은 집합이다 — 세는 말 목록이 바뀌면 이 시험이 알려 준다."""
        counters = [c for c in (F._NATIVE_COUNTERS + "|" + F._SINO_COUNTERS).split("|") if c != "%"]
        expected = {c[-1] for c in counters if has_no_final_consonant(c[-1])}
        self.assertEqual(set(F._NUM_OPEN), expected)
        self.assertEqual(len(F._NUM_OPEN), len(set(F._NUM_OPEN)))
        ends = {c[-1] for c in counters}
        self.assertTrue(set(F._NUM_IN_WORDS) <= ends, set(F._NUM_IN_WORDS) - ends)
        for syllable in "다면며죠든고지야요":
            self.assertNotIn(syllable, F._NUM_PARTICLES)                     # 줄어든 꼴의 글자는 받침 없는 세는 말 뒤에서만 센다(조사 목록에 있으면 받침 있는 말 뒤에서도 센다)

    def test_a_long_tail_after_an_ending_does_not_make_it_slow_or_wrong(self):
        for text in ("두 가지다" * 2000, "세 곳인데" * 2000, "한 해" + "다" * 3000, "열두 곳인" + "데" * 3000, "두 가지" + "예요" * 2000):
            self.assertIsInstance(F.untraced_numbers(text), list)


class NumberWordLeftEdgeTest(unittest.TestCase):
    """N4(a): 수 낱말 가지의 왼쪽 경계(앞 글자가 한글이면 수가 아니다)를 지워도 시험이 통과하던 구멍 — `반영하는`·`수영하는` 의 `영하`(영하 = 0 도 아래)가 새로 걸렸을 것이다."""

    def test_a_number_word_inside_a_longer_word_is_not_a_number(self):
        for text in ("반영하는", "수영하는", "투영하면", "표영하다", "미반영하는"):
            with self.subTest(text=text):
                self.assertEqual(F.untraced_numbers(text), [], text)

    def test_the_same_word_standing_alone_is_found(self):
        for text in ("영하", "영하 기온", "기온이 영하", "앞 영하 뒤"):
            with self.subTest(text=text):
                self.assertTrue(F.untraced_numbers(text), text)


class SinoCounterLongTailTest(unittest.TestCase):
    """N4(b): 한자어 세는 말 `초과` 는 `초`+조사 `과` 로는 잡히지 않는 꼴(과 뒤에 네 음절 이상)이 있다 — 지워도 통과하던 구멍(구현자가 동치로 분류했으나 동치가 아니었다)."""

    def test_the_counter_excess_catches_what_second_plus_particle_cannot(self):
        for text in ("삼 초과이므로써", "이십 초과이면서도", "영 초과이므로써", "백 초과이라서도"):
            with self.subTest(text=text):
                self.assertTrue(F.untraced_numbers(text), text)
                self.assertTrue(F.untraced_numbers(f"앞 {text} 뒤"), text)


if __name__ == "__main__":
    unittest.main()
