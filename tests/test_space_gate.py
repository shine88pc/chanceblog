"""S2AFIX D2: 현재 main 의 품질 관문(Gate, `pipeline/quality_gate.py`)이 모든 틀(R01–R06)의 골든 글과 무작위 글을 QG1(숫자 일치)·QG4(건강 단정)·QG6(제목·본문 일치)에서 보류하지 않는 시험.
흑점수 두 틀의 제목어 `추이` 가 본문에 없어 무작위 글 720편 가운데 흑점수 240편이 모두 QG6-TITLE-WORD 로 보류되던 일(S2a 검증 D2)을 막는다. 관문을 켜지는 않는다 — `check_candidate` 함수만
부르고 네트워크·시계가 없다. 대조군(일부러 결함을 넣은 글)이 실제로 걸리는지도 본다 — 관문을 부르는 줄이 빠지거나 규칙이 느슨해지면 이 시험이 알려 준다. 난수는 고정 시드로만."""
import datetime
import random
import unittest

import _bootstrap  # noqa: F401
import fact_helpers as FH
import space_helpers as H
import test_space_recipes as TR

from pipeline import fact_assembler as A
from pipeline import quality_gate as qg
from pipeline import recipes as R
from pipeline import recipes_noregion as RN
from pipeline import registry
from pipeline.adapters import noaa_swpc as N

CONFIG = qg.GateConfig(health_profiles=tuple(registry.load_profile(name) for name in qg.HEALTH_PROFILE_NAMES), languages=("ko",))
CHECKED = ("QG1", "QG4", "QG6")                                                     # 이 시험이 지키는 규칙: 숫자 일치·건강 단정·제목과 본문 일치
KP_THIRDS = tuple(round(step / 3, 2) for step in range(28))
NOAA_DAY, OLD_DAY = datetime.date(2026, 11, 10), datetime.date(2026, 4, 20)
KINDS = ("kp", "kp_storm", "ssn_daily", "ssn_monthly", "flares", "scales")
PER_KIND = 10


def report_of(post, *, title=None, content=None, evidence=None, domain=None, day=NOAA_DAY):
    """글을 생성기가 쓰는 파일 모양(머리말+본문)으로 만들어 관문에 넣는다. 근거 텍스트는 조립기가 만든 것이고 출처 이름·주소도 글의 것이다."""
    text, _source = TR.generator_file(post)
    src = {"title": post.source_name, "source": post.source_name, "link": post.source_url, "publisher_domain": domain or post.source_domain,
           "summary": post.evidence_text if evidence is None else evidence, "published": datetime.datetime(day.year, day.month, day.day, 1, 10, tzinfo=datetime.timezone.utc)}
    data = {"kr_title": post.title if title is None else title, "kr_content": text if content is None else content}
    return qg.check_candidate(data, src, history=(), config=CONFIG, as_of=day)


def held(report):
    return sorted(code for code in report.codes() if code.startswith(CHECKED))


def noaa_post(recipe_id, product_id, payload, key):
    """실제 NOAA 이름·주소와 보고서 B안 출처 문구로 글을 만든다(출처 도메인 검사 QG5 도 지나게)."""
    record, facts = H.parse_value(product_id, payload)
    provider = H.provider(attribution_template=H.B_TEMPLATE)
    return A.assemble(RN.NOREGION_RECIPES[recipe_id], list(facts), H.TODAY, records=[record], source=H.source_info(product_id, provider), params={"key": key} if key else None)


def day_text(back, last="2026-11-09"):
    return (datetime.date.fromisoformat(last) - datetime.timedelta(days=back)).isoformat()


def kp_payload(rng):
    days = rng.choice((5, 6, 7, 7, 8, 9, 12))
    mode = rng.choice(("wide", "wide", "flat", "ties", "storm"))
    if mode == "flat":
        maxima = [rng.choice(KP_THIRDS[:12])] * days
    elif mode == "ties":
        maxima = [rng.choice((2.0, 3.0)) for _ in range(days)]
    elif mode == "storm":
        maxima = [rng.choice(KP_THIRDS[:16] + (5.0, 5.33, 6.0, 6.67, 7.33)) for _ in range(days)]
    else:
        maxima = [rng.choice(KP_THIRDS[:20]) for _ in range(days)]
    return TR.kp_rows_with_daily_maxima(maxima, first_day=day_text(days - 1), base=rng.choice((0.0, 1.0, 1.33)))


def flare_payload(rng):
    stamps = sorted({f"2026-11-0{rng.randint(3, 9)}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00Z" for _ in range(rng.randint(6, 30))})
    letters = rng.choice(("BCCCMX", "BBCC", "CCCCM", "CBB", "CMMX"))
    return H.flare_rows([(stamp, f"{rng.choice(letters)}{rng.randint(1, 9)}.{rng.randint(0, 9)}") for stamp in stamps])


def scales_payload(rng):
    probs = {str(day): (str(rng.randint(0, 99)), str(rng.randint(0, 60)), str(rng.randint(0, 99))) for day in (1, 2, 3)}
    return H.scales_object(g_now=rng.choice("0123"), g_forecast=tuple(rng.choice("0012") for _ in range(3)), probs=probs)


def random_cases(seed, per_kind):
    """(종류, Recipe id, 제품, 가상 응답, 글감 키): 종류마다 per_kind 개. 고정 시드라 같은 입력이다."""
    rng = random.Random(seed)
    for _ in range(per_kind):
        kp = kp_payload(rng)
        yield "kp", "R04_NOREGION_SERIES", "kp_estimated", kp, RN.KEY_KP
        yield "kp_storm", "R05_THRESHOLD_COUNT", "kp_estimated", kp, RN.KEY_KP
        yield "ssn_daily", "R04_NOREGION_SERIES", "ssn_daily", H.ssn_daily_rows("2026-11-09", rng.choice((40, 70, 100)), gaps=tuple(rng.sample(range(10, 30), rng.randint(0, 3))),
                                                                                  seed=rng.randrange(1000)), RN.KEY_SSN_DAILY
        yield "ssn_monthly", "R04_NOREGION_SERIES", "ssn_monthly", H.ssn_monthly_rows("2026-10", rng.choice((24, 40, 70)), seed=rng.randrange(1000)), RN.KEY_SSN_MONTHLY
        yield "flares", "R05_THRESHOLD_COUNT", "xray_flares", flare_payload(rng), RN.KEY_FLARE_FLUX
        yield "scales", "R06_SCALE_OUTLOOK", "scales", scales_payload(rng), None


def months_ending(count, last="2026-03"):
    year, month = (int(part) for part in last.split("-"))
    first = year * 12 + month - count
    return [f"{(first + index) // 12:04d}-{(first + index) % 12 + 1:02d}" for index in range(count)]


def old_posts(seed, count):
    """기존 틀 R01·R02·R03 글 — 골든 셋과 무작위 계열(가짜 통계). 값과 개수만 바꾼다."""
    record_id = FH.mock_bundle()[1].record_id
    rng = random.Random(seed)
    posts = [("golden", recipe_id, FH.run(recipe_id, params=params)) for recipe_id, params in FH.GOLDEN.items()]
    for _ in range(count):
        values = [f"{rng.uniform(2.5, 6.5):.1f}" for _ in range(rng.randint(8, 24))]
        series = [FH.make_fact(value, period=period, record_id=record_id) for value, period in zip(values, months_ending(len(values)))]
        for recipe_id in ("R01_time_series", "R03_record_position"):
            posts.append(("random", recipe_id, FH.run(recipe_id, facts=series, params=FH.R01_PARAMS)))
        regions = [FH.make_fact(f"{rng.uniform(2.5, 6.5):.1f}", period="2026-03", region=f"R{index + 1:02d}", region_label=f"가상 지역 {'가나다라마바사아자'[index]}", record_id=record_id)
                   for index in range(rng.randint(4, 9))]
        posts.append(("random", "R02_region_compare", FH.run("R02_region_compare", facts=regions, params=FH.R02_PARAMS)))
    return posts


class GateAcceptsTheNewPostsTest(unittest.TestCase):
    def test_the_six_golden_posts_pass_the_whole_gate(self):
        for name, (recipe_id, product_id, rows, params) in TR.golden_cases().items():
            post = noaa_post(recipe_id, product_id, rows, params.get("key"))
            self.assertIsInstance(post, A.AssembledPost, (name, post))
            report = report_of(post)
            with self.subTest(post=name):
                self.assertEqual(report.codes(), [], [(hold.code, hold.message[:80]) for hold in report.holds])
                self.assertTrue(report.passed)

    def test_random_posts_of_every_new_recipe_pass_qg1_qg4_qg6(self):
        made = {kind: 0 for kind in KINDS}
        for kind, recipe_id, product_id, payload, key in random_cases(20261110, PER_KIND):
            post = noaa_post(recipe_id, product_id, payload, key)
            if not isinstance(post, A.AssembledPost):
                continue                                                                      # 입력이 모자라 글이 안 나온 경우는 관문이 볼 글이 없다
            made[kind] += 1
            self.assertEqual(held(report_of(post)), [], (kind, post.title))
            self.assertEqual(TR.notice_words(post), (None, R.calc_words(post.formulas)), (kind, post.title))               # S2AFIX2 N5: 공통 안내(주의 줄)가 이 글이 쓴 계산식만 말한다 — S2c-1 S1-b: 첫 문단 뒤 안내는 같은 목록을 되풀이하지 않는다
        for kind in KINDS:
            self.assertGreaterEqual(made[kind], PER_KIND - 2, (kind, made))                   # 시험이 속이 비지 않게: 종류마다 거의 모든 입력이 글이 된다
        self.assertGreaterEqual(sum(made.values()), 6 * (PER_KIND - 2))

    def test_the_old_recipes_pass_qg1_qg4_qg6_too(self):
        made = 0
        for how, recipe_id, post in old_posts(7, 6):
            if not isinstance(post, A.AssembledPost):
                continue
            made += 1
            self.assertEqual(held(report_of(post, domain=N.HOST, day=OLD_DAY)), [], (how, recipe_id, post.title))
        self.assertGreaterEqual(made, 3 + 6)                                                  # 골든 셋과 무작위 글이 함께 돈다

    def test_every_title_word_that_the_gate_promises_for_is_in_the_body_of_the_sunspot_posts(self):
        for name in ("r04_ssn_daily", "r04_ssn_monthly"):
            recipe_id, product_id, rows, params = TR.golden_cases()[name]
            post = noaa_post(recipe_id, product_id, rows, params["key"])
            self.assertIn("추이", post.title)
            self.assertNotIn("QG6-TITLE-WORD", report_of(post).codes(), name)


class GateStillBitesTest(unittest.TestCase):
    """대조군: 같은 글에 일부러 결함을 넣으면 관문이 막는다 — 위 시험이 관문을 정말 부르고 있다는 증거."""

    @classmethod
    def setUpClass(cls):
        recipe_id, product_id, rows, params = TR.golden_cases()["r04_ssn_daily"]
        cls.post = noaa_post(recipe_id, product_id, rows, params["key"])
        cls.content, _source = TR.generator_file(cls.post)

    def test_the_original_defect_a_title_word_that_the_body_lacks_is_held(self):
        broken = self.content.replace("의 추이를 ", "의 값을 ")
        self.assertNotEqual(broken, self.content)
        self.assertIn("QG6-TITLE-WORD", report_of(self.post, content=broken).codes())
        self.assertEqual(held(report_of(self.post)), [])

    def test_a_number_that_is_not_in_the_evidence_is_held(self):
        broken = self.content.replace("## 한눈에", "이 글은 987.65개를 더 말합니다.\n\n## 한눈에", 1)
        self.assertIn("QG1-NUMBER", report_of(self.post, content=broken).codes())

    def test_a_health_claim_is_held(self):
        broken = self.content.replace("## 한눈에", "이 지수가 오르면 두통이 생기고 약을 먹으면 반드시 낫습니다.\n\n## 한눈에", 1)
        codes = report_of(self.post, content=broken).codes()
        self.assertTrue(any(code.startswith("QG4") for code in codes), codes)

    def test_a_title_number_that_the_body_lacks_is_held(self):
        self.assertIn("QG6-TITLE-NUMBER", report_of(self.post, title="SWPC 일별 흑점수 최고 987.65 추이").codes())

    def test_an_empty_evidence_text_is_held(self):
        self.assertTrue(any(code.startswith("QG1") for code in report_of(self.post, evidence="").codes()))


if __name__ == "__main__":
    unittest.main()
