"""S2BG: 최소 품질 Gate(`pipeline/quality_gate.py`)가 구조화 Fact 글(조립기 결과)을 평가하는 방법의 시험 — docs/QUALITY_GATE.md 11절.

Fact 후보의 `source` 는 `fact_post`(정확히 True)·`evidence_text`·`source_url`·`source_domain`·`source_name`(모두 글)을 가진 사전이다. 이 사전일 때만 근거·출처가 Fact 사전에서 읽히고, QG5 에 Provider 허용 호스트
(`provider_hosts` — 정확히 같은 호스트만)가 더해지며, QG7 은 같은 출처 주소 대신 같은 `dedupe_key` 를 본다. 피드 글(Gemini 로 쓰는 글)의 평가는 한 글자도 달라지지 않는다.

시험은 다섯 갈래다: 올바른/위조된 사전의 인식 · QG5 호스트 일치와 가짜 호스트 · QG7 키 비교 · S2a 의 골든 글·무작위 글이 Fact 사전으로 보류 0 이고 결함을 넣은 대조군은 해당 규칙으로 보류됨 ·
피드 글 불변(옛 함수 모양을 시험 안에 고정해 견줌)과 근거 경계의 구조. 네트워크·시계가 없고 난수는 고정 시드로만 쓴다(S2a 의 생성 방식을 그대로 가져다 쓴다).
윈도에서 만든 해시·경로·줄 끝이 값에 들어가는 비교는 두지 않는다.
"""
import ast
import copy
import datetime
import functools
import re
import string
import time
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import quality_gate_helpers as h
import test_space_gate as SG
import test_space_recipes as TR

from pipeline import quality_gate as qg

# Fact 모듈(조립기·NOAA 어댑터)은 직접 import 하지 않고 S2a 시험이 이미 가져온 이름을 빌려 쓴다 — `test_fact_structure.NoConnectionTest` 가 Fact 시험 목록 밖의 시험이
# 그 모듈을 import 하는 것을 막기 때문이다(그 목록을 고치지 않고도 이 시험이 돌게 하려는 선택).
A, N = SG.A, SG.N

ROOT = _bootstrap.ROOT
MODULE = ROOT / "pipeline" / "quality_gate.py"
CONFIG = SG.CONFIG                      # 국문 전용(languages ko) — Fact 글은 국문 단독이다
DAY = SG.NOAA_DAY
REGISTRY_HOST = "stats.example-agency.org"          # 공공·연구기관 목록 밖의 호스트 — 레지스트리가 허용한 Provider 호스트라는 가정(시험용 가짜 이름)
PER_KIND = 12
DROP = object()
FACT_KEYS = ("fact_post", "evidence_text", "source_url", "source_domain", "source_name", "provider_hosts", "dedupe_key", "recipe_id")


def codes(holds):
    return [hold.code for hold in holds]


def with_changes(base, changes):
    out = dict(base)
    for key, value in changes.items():
        if value is DROP:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def plain_source(**changes):
    """손으로 만든(조립기를 거치지 않은) 올바른 Fact 사전. DROP 을 주면 그 키를 뺀다."""
    base = {"fact_post": True, "evidence_text": "NOAA 추정 Kp 2.67 기준일 2026-11-08", "source_url": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
            "source_domain": "services.swpc.noaa.gov", "source_name": "NOAA SWPC 행성 K 지수 추정값", "provider_hosts": ["services.swpc.noaa.gov"],
            "dedupe_key": "R04_NOREGION_SERIES|space_weather.kp_estimated|-|2026-11-08", "recipe_id": "R04_NOREGION_SERIES", "as_of": "2026-11-08"}
    return with_changes(base, changes)


def fact_dict(post, hosts=(N.HOST,), **changes):
    """조립기 결과(AssembledPost)로 만든 Fact source 사전 — 생성기가 레지스트리·조립기의 값으로 채우는 모양."""
    base = {"fact_post": True, "evidence_text": post.evidence_text, "source_url": post.source_url, "source_domain": post.source_domain, "source_name": post.source_name,
            "provider_hosts": list(hosts), "dedupe_key": post.dedupe_key, "recipe_id": post.recipe_id, "as_of": post.as_of}
    return with_changes(base, changes)


@functools.lru_cache(maxsize=None)
def golden_posts():
    posts = {}
    for name, (recipe_id, product_id, rows, params) in TR.golden_cases().items():
        post = SG.noaa_post(recipe_id, product_id, rows, params.get("key"))
        assert isinstance(post, A.AssembledPost), (name, post)
        posts[name] = post
    return posts


@functools.lru_cache(maxsize=None)
def golden_file(name):
    return TR.generator_file(golden_posts()[name])[0]


def run(post, *, content=None, title=None, source=None, history=(), config=CONFIG, day=DAY, hosts=(N.HOST,), **changes):
    """글을 생성기가 쓰는 파일 모양(머리말 + 본문)으로 만들어 Fact 사전과 함께 Gate 에 넣는다."""
    text = TR.generator_file(post)[0] if content is None else content
    data = {"kr_title": post.title if title is None else title, "kr_content": text}
    return qg.check_candidate(data, fact_dict(post, hosts=hosts, **changes) if source is None else source, history=history, config=config, as_of=day)


# ----------------------------------------------------------------------------
# 1. 올바른 Fact 사전과 위조된 반쪽 사전
# ----------------------------------------------------------------------------
class FactSourceRecognitionTest(unittest.TestCase):
    def test_a_correct_fact_source_gives_its_own_evidence_and_identity(self):
        source = plain_source(source_domain="Services.SWPC.NOAA.gov")
        self.assertEqual(qg.evidence_text(source), qg.Evidence(source["evidence_text"], 0))
        self.assertEqual(qg.source_ref(source), qg.SourceRef(source["source_url"], "services.swpc.noaa.gov", source["source_name"]))
        self.assertEqual(qg.fact_ref(source), qg.FactRef(("services.swpc.noaa.gov",), source["dedupe_key"]))

    def test_the_evidence_is_not_an_article_summary_and_is_cut_at_the_limit(self):
        long_text = "값 12.5 " * 6000
        evidence = qg.evidence_text(plain_source(evidence_text=long_text))
        self.assertEqual(len(evidence.text), qg.MAX_EVIDENCE_CHARS)
        self.assertEqual(evidence.text, long_text[:qg.MAX_EVIDENCE_CHARS])
        self.assertEqual(evidence.summary_chars, 0)
        exact = "가" * qg.MAX_EVIDENCE_CHARS
        self.assertEqual(qg.evidence_text(plain_source(evidence_text=exact)).text, exact)

    def test_the_feed_keys_of_a_correct_fact_source_are_not_read(self):
        source = plain_source(title="피드 제목 777", summary="피드 요약 888", link="https://feed.example/article", publisher_domain="www.nasa.gov", published=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc))
        self.assertEqual(qg.evidence_text(source).text, source["evidence_text"])
        self.assertNotIn("777", qg.evidence_text(source).text)
        self.assertEqual(qg.source_ref(source).link, source["source_url"])
        self.assertEqual(qg.source_ref(source).domain, "services.swpc.noaa.gov")

    def test_an_empty_evidence_is_still_a_correct_source_and_is_held_as_no_source(self):
        source = plain_source(evidence_text="   ")
        self.assertIsNotNone(qg.fact_ref(source))
        report = qg.check_candidate({"kr_title": "t", "kr_content": "본문"}, source, config=CONFIG, as_of=DAY)
        self.assertIn("QG0-NO-SOURCE", report.codes())

    def test_only_a_marker_that_is_exactly_true_makes_a_fact_source(self):
        for marker in (1, 1.0, "true", "True", "yes", "1", None, False, 0, "", [True], {"fact_post": True}, b"true", (True,)):
            with self.subTest(marker=marker):
                source = plain_source(fact_post=marker)
                self.assertIsNone(qg.fact_ref(source))
                self.assertEqual(qg.evidence_text(source), qg.Evidence("", 0))                     # 피드 항목으로 읽히고 피드 키가 없으니 근거가 없다
                self.assertEqual(qg.source_ref(source), qg.SourceRef("", "", ""))
        self.assertIsNone(qg.fact_ref(plain_source(fact_post=DROP)))

    def test_a_missing_or_non_text_required_key_makes_it_a_forged_half_source(self):
        for key in ("evidence_text", "source_url", "source_domain", "source_name"):
            for value in (DROP, None, 5, 1.5, b"bytes", ["a"], {"a": 1}, ("a",), True):
                with self.subTest(key=key, value=value):
                    source = plain_source(**{key: value})
                    self.assertIsNone(qg.fact_ref(source))
                    self.assertEqual(qg.evidence_text(source), qg.Evidence("", 0))
                    self.assertEqual(qg.source_ref(source), qg.SourceRef("", "", ""))

    def test_a_source_that_is_not_a_dict_is_never_a_fact_source(self):
        for source in (None, "문자열", 5, [], ["fact_post"], (("fact_post", True),), set(), b"x"):
            with self.subTest(source=source):
                self.assertIsNone(qg.fact_ref(source))
                self.assertEqual(qg.evidence_text(source), qg.Evidence("", 0))
                self.assertEqual(qg.source_ref(source), qg.SourceRef("", "", ""))

    def test_a_forged_half_source_cannot_pass_the_gate_even_with_a_perfect_post(self):
        post = golden_posts()["r04_ssn_daily"]
        self.assertEqual(run(post).codes(), [])                                                  # 올바른 사전이면 같은 글이 통과한다(대조)
        forged = (fact_dict(post, fact_post=1), fact_dict(post, fact_post="true"), fact_dict(post, fact_post=DROP), fact_dict(post, evidence_text=None),
                  fact_dict(post, evidence_text=5), fact_dict(post, source_url=DROP), fact_dict(post, source_domain=DROP), fact_dict(post, source_name=DROP),
                  {"fact_post": True, "evidence_text": post.evidence_text}, {"fact_post": True}, {"evidence_text": post.evidence_text, "source_url": post.source_url})
        for index, source in enumerate(forged):
            with self.subTest(index=index):
                report = run(post, source=source)
                self.assertFalse(report.passed)
                self.assertIn("QG0-NO-SOURCE", report.codes())

    def test_a_half_source_with_feed_keys_is_read_exactly_like_a_feed_item(self):
        feed = h.fixture_source()
        for marker in (1, "true", None, DROP):
            with self.subTest(marker=marker):
                mixed = with_changes(dict(feed, evidence_text="이 글은 쓰이지 않는다 4,321", source_url="https://other.example/x", source_domain="www.nasa.gov",
                                          source_name="가짜 출처", provider_hosts=["www.example-company.com"], dedupe_key="k"), {"fact_post": marker})
                self.assertEqual(qg.evidence_text(mixed), qg.evidence_text(feed))
                self.assertEqual(qg.source_ref(mixed), qg.source_ref(feed))
                self.assertIsNone(qg.fact_ref(mixed))
                self.assertEqual(h.run_gate(source=mixed).holds, h.run_gate(source=feed).holds)

    def test_each_key_is_read_only_once_in_one_reading(self):
        class Recording(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.keys_read = []

            def get(self, key, default=None):
                self.keys_read.append(key)
                return super().get(key, default)
        source = Recording(plain_source())
        qg.fact_ref(source)
        self.assertEqual(len(source.keys_read), len(set(source.keys_read)))
        self.assertEqual(set(source.keys_read), {"fact_post", "evidence_text", "source_url", "source_domain", "source_name", "provider_hosts", "dedupe_key"})


# ----------------------------------------------------------------------------
# 2. QG5 — 허용 호스트(provider_hosts)
# ----------------------------------------------------------------------------
class FactCompanyRuleTest(unittest.TestCase):
    PUBLIC = qg.PUBLIC_SOURCE_DOMAINS

    def verdict(self, domain, hosts):
        return codes(qg.rule_company_fact(domain, self.PUBLIC, hosts))

    def test_the_registry_host_used_by_these_tests_is_not_a_public_domain(self):
        self.assertFalse(qg._domain_in(REGISTRY_HOST, self.PUBLIC))
        self.assertEqual(codes(qg.rule_company(REGISTRY_HOST, self.PUBLIC)), ["QG5-COMPANY"])        # 피드 글이면 보류다(옛 규칙 그대로)

    def test_a_registry_host_outside_the_public_list_passes_only_with_that_exact_host(self):
        self.assertEqual(self.verdict(REGISTRY_HOST, [REGISTRY_HOST]), [])
        self.assertEqual(self.verdict(REGISTRY_HOST, ["other.example-agency.org", REGISTRY_HOST]), [])
        for hosts in (None, [], (), "", REGISTRY_HOST, {REGISTRY_HOST}, {REGISTRY_HOST: 1}, 5, [None], [""]):
            with self.subTest(hosts=hosts):
                self.assertEqual(self.verdict(REGISTRY_HOST, hosts), ["QG5-COMPANY"])

    def test_a_public_domain_passes_without_any_provider_host_just_like_before(self):
        for domain in ("services.swpc.noaa.gov", "www.nasa.gov", "commission.europa.eu", "www.bok.or.kr"):
            with self.subTest(domain=domain):
                self.assertEqual(self.verdict(domain, []), [])
                self.assertEqual(self.verdict(domain, None), [])
                self.assertEqual(codes(qg.rule_company(domain, self.PUBLIC)), [])

    def test_spelling_variants_of_the_same_host_are_the_same_host(self):
        for domain in (REGISTRY_HOST.upper(), "Stats.Example-Agency.ORG", REGISTRY_HOST + "."):
            with self.subTest(domain=domain):
                self.assertEqual(self.verdict(domain, [REGISTRY_HOST]), [])
        for host in (REGISTRY_HOST.upper(), REGISTRY_HOST + ".", "Stats.Example-Agency.ORG."):
            with self.subTest(host=host):
                self.assertEqual(self.verdict(REGISTRY_HOST, [host]), [])

    def test_lookalike_hosts_are_held_because_only_the_exact_host_counts(self):
        lookalikes = (
            REGISTRY_HOST + ".evil.example",                    # 레지스트리 호스트로 시작하는 남의 도메인
            "evil-" + REGISTRY_HOST,                            # 같은 끝을 가진 다른 호스트(접미사 일치 금지)
            "x" + REGISTRY_HOST,
            "sub." + REGISTRY_HOST,                             # 하위 도메인
            "example-agency.org",                               # 상위 도메인
            REGISTRY_HOST + ":443",                             # 포트
            REGISTRY_HOST + "/path", "https://" + REGISTRY_HOST, "user@" + REGISTRY_HOST,
            REGISTRY_HOST + " ", " " + REGISTRY_HOST, REGISTRY_HOST + "\n", REGISTRY_HOST + "\u200b",     # 공백·보이지 않는 글자
            REGISTRY_HOST + "..",                               # 끝 점이 둘
            "stats.example\u2010agency.org", "stats\uff0eexample-agency\uff0eorg",                      # 하이픈·점의 비슷한 유니코드 글자
            "stats.ex\u0430mple-agency.org", "\u0455tats.example-agency.org",                           # 키릴 글자 동형 문자
            "stats.example-agency.org\u3002", "STATS.EXAMPLE-AGENCY.ORG\uff0e",
        )
        for domain in lookalikes:
            with self.subTest(domain=domain):
                self.assertEqual(self.verdict(domain, [REGISTRY_HOST]), ["QG5-COMPANY"])

    def test_the_noaa_lookalikes_are_held_when_the_provider_host_is_the_only_way_in(self):
        """공공 목록에 noaa.gov 가 있어 진짜 NOAA 호스트는 목록으로 통과한다. 비슷한 가짜 호스트가 Provider 호스트 규칙으로 넓게 통과하지 않음을 가려 보려면 공공 목록에서 noaa.gov 를 뺀 설정으로 본다."""
        public = tuple(domain for domain in self.PUBLIC if domain != "noaa.gov")
        for domain, expected in (("services.swpc.noaa.gov", []), ("SERVICES.SWPC.NOAA.GOV.", []), ("services.swpc.noaa.gov.evil.example", ["QG5-COMPANY"]),
                                 ("evil-services.swpc.noaa.gov", ["QG5-COMPANY"]), ("swpc.noaa.gov", ["QG5-COMPANY"]), ("a.services.swpc.noaa.gov", ["QG5-COMPANY"]),
                                 ("services.swpc.noaa.gov:443", ["QG5-COMPANY"]), ("s\u0435rvices.swpc.noaa.gov", ["QG5-COMPANY"])):
            with self.subTest(domain=domain):
                self.assertEqual(codes(qg.rule_company_fact(domain, public, ["services.swpc.noaa.gov"])), expected)

    def test_the_kelvin_sign_does_not_become_an_ascii_k_through_lowercasing(self):
        host = "kstats.example-agency.org"
        self.assertEqual(self.verdict(host, [host]), [])
        self.assertEqual("\u212a".lower(), "k")                                                  # 유니코드 소문자화는 켈빈 기호를 ASCII k 로 만든다 — 그래서 쓰지 않는다
        self.assertEqual(self.verdict("\u212astats.example-agency.org", [host]), ["QG5-COMPANY"])
        self.assertEqual(self.verdict(host, ["\u212astats.example-agency.org"]), ["QG5-COMPANY"])
        self.assertEqual(qg.source_ref(plain_source(source_domain="\u212astats.example-agency.org")).domain, "\u212astats.example-agency.org")
        self.assertEqual(qg._clean_host("\u212astats.example-agency.org"), None)

    def test_ascii_lowercasing_changes_only_ascii_capitals(self):
        self.assertEqual(qg._ascii_lower(string.ascii_uppercase + string.ascii_lowercase + string.digits + ".-"), string.ascii_lowercase * 2 + string.digits + ".-")
        for text in ("\u212a", "\u0130", "\u00c4\u00d6", "\u017f", "\uff21", "\u0410", "가나다", ""):
            with self.subTest(text=text):
                self.assertEqual(qg._ascii_lower(text), text)                                  # 비 ASCII 글자는 건드리지 않는다
        self.assertEqual(self.verdict("ZONES.EXAMPLE-AGENCY.ORG", ["zones.example-agency.org"]), [])
        self.assertEqual(self.verdict("zones.example-agency.org", ["ZONES.Example-Agency.ORG"]), [])

    def test_the_host_length_limit_is_exact_and_a_trailing_dot_does_not_count(self):
        host253 = ".".join(("a" * 63, "a" * 63, "a" * 63, "a" * 61))
        host254 = ".".join(("a" * 63, "a" * 63, "a" * 63, "a" * 62))
        self.assertEqual((len(host253), len(host254)), (253, 254))
        self.assertEqual(qg._clean_host(host253), host253)
        self.assertIsNone(qg._clean_host(host254))
        self.assertEqual(qg._clean_host(host253 + "."), host253)
        self.assertIsNone(qg._clean_host(host254 + "."))
        self.assertIsNone(qg._clean_host(host253 + ".."))

    def test_the_host_checks_are_fast_and_never_raise_on_worst_case_shapes(self):
        shapes = ("a." * 126 + "-", "a" * 253, "-" * 253, "a." * 100 + "a" * 53 + "!", "a" * 63 + "." + "a" * 63 + "." + "a" * 63 + "." + "a" * 62, "." * 253, "a-" * 126 + "a",
                  "1." * 126 + "1", "a." * 126 + "a.", "a" * 254, "a" * 100000, "a." * 50000, "\u00e4" * 1000, " " * 100000, "\n" * 1000)
        started = time.perf_counter()
        for shape in shapes:
            qg._clean_host(shape)
            qg._provider_hosts([shape, shape])
            qg.rule_company_fact(shape, self.PUBLIC, [shape])
        self.assertLess(time.perf_counter() - started, 2.0)

    def test_a_label_is_at_most_63_characters_wherever_it_stands(self):
        for prefix, suffix in (("", ".org"), ("a.", ""), ("b.", ".org")):
            with self.subTest(prefix=prefix, suffix=suffix):
                self.assertEqual(qg._clean_host(prefix + "a" * 63 + suffix), prefix + "a" * 63 + suffix)
                self.assertIsNone(qg._clean_host(prefix + "a" * 64 + suffix))

    def test_a_malformed_provider_host_is_ignored_and_never_widens_the_list(self):
        malformed = ("*", "*.example-agency.org", "", " ", "\t", "https://" + REGISTRY_HOST, "//" + REGISTRY_HOST, REGISTRY_HOST + "/path", REGISTRY_HOST + ":443", "user@" + REGISTRY_HOST,
                     REGISTRY_HOST + " ", " " + REGISTRY_HOST, "stats example-agency.org", REGISTRY_HOST + "\n", "localhost", "com", "127.0.0.1", "10.0.0.1", "a..b", ".a.b", "a.b..", "-a.example.org",
                     "a-.example.org", "a_b.example.org", "ex\u00e4mple.org", "\uff53tats.example-agency.org", 5, None, b"stats.example-agency.org", ["a.b"], {"a": 1}, True, 1.5)
        self.assertEqual(qg._provider_hosts(list(malformed)), ())
        self.assertEqual(self.verdict(REGISTRY_HOST, list(malformed)), ["QG5-COMPANY"])
        for item in malformed:
            if isinstance(item, str) and item.strip():
                with self.subTest(item=item):                                                    # 이상한 항목과 글자 그대로 같은 도메인도 통과하지 못한다
                    self.assertEqual(self.verdict(item, list(malformed)), ["QG5-COMPANY"])
        mixed = list(malformed[:3]) + [REGISTRY_HOST] + list(malformed[3:])                      # 이상한 항목 사이에 낀 올바른 항목은 그대로 읽힌다(앞의 32개 안)
        self.assertEqual(self.verdict(REGISTRY_HOST, mixed), [])
        self.assertEqual(qg._provider_hosts(list(malformed[:3]) + [REGISTRY_HOST.upper() + "."] + list(malformed[3:])), (REGISTRY_HOST,))

    def test_a_list_of_hosts_is_read_only_up_to_the_limit_and_kept_without_duplicates(self):
        self.assertEqual(qg.MAX_PROVIDER_HOSTS, 32)                                                  # 한도 값 자체를 못박는다(아래 경계는 이 값 그대로다)
        filler = [f"junk{index}.example-agency.org" for index in range(31)]
        self.assertEqual(self.verdict(REGISTRY_HOST, filler + [REGISTRY_HOST]), [])                  # 마지막 자리(32번째)는 읽는다
        self.assertEqual(self.verdict(REGISTRY_HOST, filler + ["bad host"] + [REGISTRY_HOST]), ["QG5-COMPANY"])      # 33번째는 읽지 않는다
        self.assertEqual(qg._provider_hosts([REGISTRY_HOST, REGISTRY_HOST.upper(), REGISTRY_HOST + "."]), (REGISTRY_HOST,))
        self.assertEqual(qg._provider_hosts((REGISTRY_HOST,)), (REGISTRY_HOST,))                     # 튜플도 목록이다
        long_label = "a" * 63
        self.assertEqual(qg._clean_host(long_label + ".org"), long_label + ".org")
        self.assertIsNone(qg._clean_host("a" * 64 + ".org"))
        too_long = ".".join(["a" * 60] * 5)
        self.assertGreater(len(too_long), qg.MAX_HOST_CHARS)
        self.assertIsNone(qg._clean_host(too_long))
        self.assertEqual(qg._clean_host(".".join(["a" * 60] * 4) + ".org"), ".".join(["a" * 60] * 4) + ".org")

    def test_a_post_domain_that_is_not_a_host_name_is_held_even_under_a_public_suffix(self):
        """공공 목록은 접미 일치라 `x/.nasa.gov`·앞 공백·줄바꿈이 낀 이름도 옛 규칙은 통과시킨다 — Fact 글은 글의 도메인 자신도 호스트 이름 모양이어야 한다."""
        sneaky = ("evil.example/x.nasa.gov", " www.nasa.gov", "www.nasa.gov ", "a b.nasa.gov", "*.nasa.gov", ".nasa.gov", "a..nasa.gov", "-a.nasa.gov", "a_b.nasa.gov",
                  "evil.example" + chr(10) + ".nasa.gov", "user@www.nasa.gov", "www.nasa.gov:443", "www.nasa.gov/", "https://www.nasa.gov", "www.nasa.gov" + chr(0x200b),
                  chr(0xe4) + ".nasa.gov", "www.nasa.gov..", "a.nasa.gov." + chr(0xff0e), "x" * 64 + ".nasa.gov")
        for domain in sneaky:
            with self.subTest(domain=domain):
                self.assertEqual(self.verdict(domain, [REGISTRY_HOST]), ["QG5-COMPANY"])
                self.assertEqual(self.verdict(domain, [domain]), ["QG5-COMPANY"])
        for domain in ("www.nasa.gov", "WWW.NASA.GOV", "www.nasa.gov.", "science.nasa.gov", "nasa.gov", "a-b.nasa.gov", "a1.b2.nasa.gov"):
            with self.subTest(domain=domain):
                self.assertEqual(self.verdict(domain, []), [])
        self.assertEqual(codes(qg.rule_company("evil.example/x.nasa.gov", self.PUBLIC)), [])                       # 피드 글의 옛 규칙은 그대로 통과시킨다(바이트 불변 — 한계)
        self.assertEqual(codes(qg.rule_company(" www.nasa.gov", self.PUBLIC)), [])

    def test_an_excluded_domain_wins_even_if_the_provider_lists_it(self):
        for domain in qg.EXCLUDED_SOURCE_DOMAINS:
            for host in (domain, "www." + domain, "news." + domain, domain.upper(), domain + ".", domain + "..", "WWW." + domain.upper() + "."):
                with self.subTest(host=host):
                    holds = qg.rule_company_fact(host, self.PUBLIC + (domain,), [domain, "www." + domain, "news." + domain])
                    self.assertEqual(codes(holds), ["QG5-COMPANY"])
                    self.assertIn("제외", holds[0].message)

    def test_the_hold_text_is_one_line_and_safe_for_hostile_domains(self):
        hostile = "evil.example\n::error::fake ## [group] \x07" + "x" * 300
        for domain in (hostile, None, 5, ""):
            with self.subTest(domain=domain):
                holds = qg.rule_company_fact(domain, self.PUBLIC, [REGISTRY_HOST])
                self.assertEqual(codes(holds), ["QG5-COMPANY"])
                for hold in holds:
                    self.assertEqual((hold.rule, hold.lang), (5, "post"))
                    for bad in ("\n", "::", "##[", "\x07"):
                        self.assertNotIn(bad, hold.message)
                    self.assertLess(len(hold.message), 200)

    def test_the_whole_gate_uses_the_registry_hosts_of_the_post_only_for_fact_posts(self):
        post = TR.build("r04_ssn_daily")                                                          # 시험용 출처(example.invalid) — 공공 목록 밖
        self.assertEqual(post.source_domain, "example.invalid")
        self.assertIn("QG5-COMPANY", run(post, hosts=()).codes())
        self.assertEqual(run(post, hosts=("example.invalid",)).codes(), [])
        self.assertIn("QG5-COMPANY", run(post, hosts=("example.invalid.evil.example", "evil-example.invalid", "sub.example.invalid")).codes())
        feed = h.fixture_source(publisher_domain="www.example-company.com", provider_hosts=["www.example-company.com"], dedupe_key="k")        # 피드 글: provider_hosts 는 읽히지 않는다
        self.assertIn("QG5-COMPANY", h.run_gate(source=feed).codes())
        self.assertNotIn("QG5-COMPANY", h.run_gate().codes())

    def test_old_recipe_posts_pass_with_their_registry_host_and_are_held_without_it(self):
        made = 0
        for how, recipe_id, post in SG.old_posts(7, 2):
            if not isinstance(post, A.AssembledPost):
                continue
            made += 1
            self.assertEqual(post.source_domain, "stats.mock.invalid")
            with self.subTest(how=how, recipe=recipe_id):
                self.assertEqual(run(post, hosts=(post.source_domain,), day=SG.OLD_DAY).codes(), [])
                self.assertEqual(run(post, hosts=(), day=SG.OLD_DAY).codes(), ["QG5-COMPANY"])
        self.assertGreaterEqual(made, 3 + 2)


class RealRegistryHostsTest(unittest.TestCase):
    """실제 허용 목록(`pipeline/source_registry.json`)의 Provider 호스트가 이 Gate 에서 쓸 수 있는 모양이다 — 호스트를 올렸는데 모양 때문에 조용히 무시되는 일이 없게 한다."""

    @classmethod
    def setUpClass(cls):
        from pipeline import source_registry
        registry = source_registry.load_registry()
        cls.hosts = sorted({host for provider in registry.providers() for access in provider.access for host in access.hosts})

    def test_every_registry_host_is_a_usable_provider_host_as_it_is(self):
        self.assertGreater(len(self.hosts), 10)
        for host in self.hosts:
            with self.subTest(host=host):
                self.assertEqual(qg._clean_host(host), host)
        self.assertEqual(qg._provider_hosts(self.hosts[:qg.MAX_PROVIDER_HOSTS]), tuple(self.hosts[:qg.MAX_PROVIDER_HOSTS]))

    def test_a_host_outside_the_public_list_passes_only_when_it_is_listed_and_an_excluded_one_never_does(self):
        outside = [host for host in self.hosts if not qg._domain_in(host, qg.PUBLIC_SOURCE_DOMAINS)]
        self.assertTrue(outside)
        for host in outside:
            with self.subTest(host=host):
                excluded = qg._domain_in(host, qg.EXCLUDED_SOURCE_DOMAINS)
                self.assertEqual(codes(qg.rule_company_fact(host, qg.PUBLIC_SOURCE_DOMAINS, [host])), ["QG5-COMPANY"] if excluded else [])
                self.assertEqual(codes(qg.rule_company_fact(host, qg.PUBLIC_SOURCE_DOMAINS, [])), ["QG5-COMPANY"])
                self.assertEqual(codes(qg.rule_company_fact("evil-" + host, qg.PUBLIC_SOURCE_DOMAINS, [host])), ["QG5-COMPANY"])
                self.assertEqual(codes(qg.rule_company_fact("sub." + host, qg.PUBLIC_SOURCE_DOMAINS, [host])), ["QG5-COMPANY"])
                self.assertEqual(codes(qg.rule_company_fact(host + ".evil.example", qg.PUBLIC_SOURCE_DOMAINS, [host])), ["QG5-COMPANY"])


# ----------------------------------------------------------------------------
# 3. QG7 — 같은 dedupe_key
# ----------------------------------------------------------------------------
class FactReuseRuleTest(unittest.TestCase):
    KEY = "R04_NOREGION_SERIES|space_weather.kp_estimated|-|2026-11-08"

    def test_the_same_key_in_history_is_held_and_a_different_key_passes(self):
        self.assertEqual(codes(qg.rule_reuse_fact(self.KEY, [{"dedupe_key": self.KEY}])), ["QG7-REUSE"])
        self.assertEqual(codes(qg.rule_reuse_fact(self.KEY, [{"topic": "다른 글"}, {"dedupe_key": "다른 키"}, {"dedupe_key": self.KEY, "source_url": "x"}])), ["QG7-REUSE"])
        self.assertEqual(qg.rule_reuse_fact(self.KEY, [{"dedupe_key": self.KEY.replace("2026-11-08", "2026-11-01")}]), [])
        self.assertEqual(qg.rule_reuse_fact(self.KEY, [{"dedupe_key": self.KEY.replace("R04", "R05")}]), [])

    def test_the_comparison_is_exact(self):
        for other in (self.KEY.lower(), self.KEY.upper(), self.KEY + " ", " " + self.KEY, self.KEY + "|", self.KEY[:-1], self.KEY.replace("|", " | ")):
            with self.subTest(other=other):
                self.assertEqual(qg.rule_reuse_fact(self.KEY, [{"dedupe_key": other}]), [])
        self.assertEqual(codes(qg.rule_reuse_fact(" " + self.KEY, [{"dedupe_key": " " + self.KEY}])), ["QG7-REUSE"])        # 공백도 글자 그대로 견준다

    def test_old_entries_without_a_key_and_odd_entries_are_skipped(self):
        history = ["문자열 항목", self.KEY, {"topic": "주제"}, {"dedupe_key": None}, {"dedupe_key": 5}, {"dedupe_key": [self.KEY]}, {"dedupe_key": {"k": self.KEY}}, {"dedupe_key": b"x"},
                   {"dedupe_key": ""}, None, 7, (self.KEY,), {"source_url": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"}]
        self.assertEqual(qg.rule_reuse_fact(self.KEY, history), [])
        for empty in (None, (), []):
            self.assertEqual(qg.rule_reuse_fact(self.KEY, empty), [])
        self.assertEqual(codes(qg.rule_reuse_fact(self.KEY, iter([{"dedupe_key": self.KEY}]))), ["QG7-REUSE"])

    def test_a_missing_or_unusable_key_is_an_input_error_not_a_reuse_hold(self):
        for key in (None, "", " ", "\t\n", 5, b"key", ["k"], {"k": 1}, True):
            with self.subTest(key=key):
                for history in ((), [{"dedupe_key": key}], [{"dedupe_key": "x"}]):
                    holds = qg.rule_reuse_fact(key, history)
                    self.assertEqual(codes(holds), ["QG0-DEDUPE-KEY"])
                    self.assertEqual((holds[0].rule, holds[0].lang), (0, "post"))
        self.assertIsNone(qg.fact_ref(plain_source(dedupe_key=DROP)).dedupe_key)
        self.assertIsNone(qg.fact_ref(plain_source(dedupe_key="   ")).dedupe_key)
        self.assertEqual(qg.fact_ref(plain_source(dedupe_key=" k ")).dedupe_key, " k ")             # 공백이 든 키는 그대로 둔다

    def test_the_whole_gate_holds_a_fact_post_without_a_usable_key_as_a_qg0_error(self):
        post = golden_posts()["r04_kp"]
        for changes in ({"dedupe_key": DROP}, {"dedupe_key": ""}, {"dedupe_key": None}, {"dedupe_key": 5}, {"dedupe_key": "  "}):
            with self.subTest(changes=changes):
                report = run(post, history=[{"dedupe_key": post.dedupe_key}], **changes)
                self.assertEqual(report.codes(), ["QG0-DEDUPE-KEY"])
        self.assertEqual(run(post).codes(), [])

    def test_a_past_post_with_the_same_product_address_does_not_block_a_fact_post(self):
        post = golden_posts()["r04_kp"]
        last_week = {"topic": "지난주 글", "source_url": post.source_url, "dedupe_key": post.dedupe_key.replace("2026-11-08", "2026-11-01")}
        self.assertEqual(run(post, history=[last_week]).codes(), [])
        same_week = dict(last_week, dedupe_key=post.dedupe_key)
        self.assertEqual(run(post, history=[same_week]).codes(), ["QG7-REUSE"])
        sibling = golden_posts()["r05_kp_storm"]                                                  # 같은 제품 주소를 쓰는 다른 글(Recipe 가 다르다)
        self.assertEqual(sibling.source_url, post.source_url)
        self.assertNotEqual(sibling.dedupe_key, post.dedupe_key)
        self.assertEqual(run(sibling, history=[dict(last_week, dedupe_key=post.dedupe_key)]).codes(), [])

    def test_the_same_address_still_blocks_a_feed_item_exactly_as_before(self):
        post = golden_posts()["r04_kp"]
        history = [{"source_url": post.source_url, "dedupe_key": "무관한 키"}]
        feed = {"title": post.source_name, "source": post.source_name, "link": post.source_url, "publisher_domain": post.source_domain, "summary": post.evidence_text,
                "published": datetime.datetime(2026, 11, 10, 1, 10, tzinfo=datetime.timezone.utc)}
        text = TR.generator_file(post)[0]
        data = {"kr_title": post.title, "kr_content": text}
        report = qg.check_candidate(data, feed, history=history, config=CONFIG, as_of=DAY)
        self.assertEqual(report.codes(), ["QG7-REUSE"])                                           # S2a 두 번째 검증 N6 의 재현: 피드 모양이면 같은 제품 주소는 막힌다(옛 동작 그대로)
        for name, golden in golden_posts().items():
            with self.subTest(post=name):
                feed_like = dict(feed, link=golden.source_url, title=golden.source_name, summary=golden.evidence_text)
                data = {"kr_title": golden.title, "kr_content": golden_file(name)}
                self.assertIn("QG7-REUSE", qg.check_candidate(data, feed_like, history=[{"source_url": golden.source_url}], config=CONFIG, as_of=DAY).codes())
                self.assertEqual(run(golden, history=[{"source_url": golden.source_url}]).codes(), [])


# ----------------------------------------------------------------------------
# 4. 골든 글·무작위 글·결함을 넣은 대조군
# ----------------------------------------------------------------------------
class FactPostsPassTheWholeGateTest(unittest.TestCase):
    def test_the_six_golden_posts_have_no_hold_at_all(self):
        self.assertEqual(set(golden_posts()), {"r04_kp", "r04_ssn_daily", "r04_ssn_monthly", "r05_kp_storm", "r05_flares", "r06_scales"})
        for name, post in golden_posts().items():
            with self.subTest(post=name):
                report = run(post)
                self.assertEqual(report.codes(), [], [(hold.code, hold.message[:80]) for hold in report.holds])
                self.assertTrue(report.passed)
                self.assertEqual(report.facts["source_text_chars"], 0)
                self.assertEqual(report.facts["evidence_chars"], len(post.evidence_text))

    def test_random_posts_of_every_kind_have_no_hold_at_all(self):
        made = {kind: 0 for kind in SG.KINDS}
        for kind, recipe_id, product_id, payload, key in SG.random_cases(20261110, PER_KIND):
            post = SG.noaa_post(recipe_id, product_id, payload, key)
            if not isinstance(post, A.AssembledPost):
                continue
            made[kind] += 1
            report = run(post)
            self.assertEqual(report.codes(), [], (kind, post.title, [(hold.code, hold.message[:80]) for hold in report.holds]))
        for kind in SG.KINDS:
            self.assertGreaterEqual(made[kind], 10, (kind, made))                                 # 종류마다 열 편 이상이 실제로 관문을 지난다(시험이 속이 비지 않게)

    def test_the_old_recipes_pass_the_whole_gate_with_their_registry_host(self):
        made = 0
        for how, recipe_id, post in SG.old_posts(7, 3):
            if not isinstance(post, A.AssembledPost):
                continue
            made += 1
            self.assertEqual(run(post, hosts=(post.source_domain,), day=SG.OLD_DAY).codes(), [], (how, recipe_id))
        self.assertGreaterEqual(made, 3 + 3)

    def test_a_korean_and_english_pair_setting_holds_a_fact_post_because_there_is_no_english_text(self):
        report = run(golden_posts()["r04_kp"], config=h.make_config())
        self.assertEqual(report.codes(), ["QG0-INPUT"])
        self.assertIn("영문", report.holds[0].message)                                              # Fact 글은 국문 전용이다 — 국문 전용 설정(languages ko)에서만 평가한다


class FactControlGroupTest(unittest.TestCase):
    """대조군: 같은 글에 일부러 결함을 넣으면 규칙마다 보류한다 — 위 시험이 관문을 정말 거치고 있다는 증거."""

    @classmethod
    def setUpClass(cls):
        cls.post = golden_posts()["r04_ssn_daily"]
        cls.content = golden_file("r04_ssn_daily")

    def test_the_unmodified_post_passes(self):
        self.assertEqual(run(self.post).codes(), [])

    def test_a_number_that_the_evidence_lacks_is_held_by_qg1(self):
        broken = self.content.replace("## 한눈에", "이 글은 987.65개를 더 말합니다.\n\n## 한눈에", 1)
        self.assertNotEqual(broken, self.content)
        self.assertIn("QG1-NUMBER", run(self.post, content=broken).codes())

    def test_the_evidence_of_another_post_does_not_support_this_body(self):
        other = golden_posts()["r05_flares"]
        report = run(self.post, evidence_text=other.evidence_text)
        self.assertIn("QG1-NUMBER", report.codes())

    def test_a_health_claim_is_held_by_qg4(self):
        broken = self.content.replace("## 한눈에", "이 지수가 오르면 두통이 생기고 약을 먹으면 반드시 낫습니다.\n\n## 한눈에", 1)
        self.assertTrue(any(code.startswith("QG4") for code in run(self.post, content=broken).codes()))

    def test_a_deleted_title_word_is_held_by_qg6(self):
        broken = self.content.replace("의 추이를 ", "의 값을 ")
        self.assertNotEqual(broken, self.content)
        self.assertIn("QG6-TITLE-WORD", run(self.post, content=broken).codes())
        self.assertIn("QG6-TITLE-NUMBER", run(self.post, title="SWPC 일별 흑점수 최고 987.65 추이").codes())

    def test_a_forged_domain_is_held_by_qg5(self):
        for domain in ("evil.example", "services.swpc.noaa.gov.evil.example", "www.example-company.com", "", "www.pewresearch.org"):
            with self.subTest(domain=domain):
                report = run(self.post, source_domain=domain, hosts=(N.HOST, "www.pewresearch.org"))
                self.assertEqual(report.codes(), ["QG5-COMPANY"])

    def test_a_removed_source_link_is_held_by_qg3(self):
        broken = self.content.replace(self.post.source_url, "https://evil.example/elsewhere")
        self.assertNotEqual(broken, self.content)
        self.assertIn("QG3-LINK", run(self.post, content=broken).codes())

    def test_a_quote_that_the_evidence_lacks_is_held_by_qg2(self):
        broken = self.content.replace("## 한눈에", "한 연구자는 \"이 숫자는 앞으로도 계속 오를 것이라고 확신한다\"고 말했다.\n\n## 한눈에", 1)
        self.assertIn("QG2-QUOTE", run(self.post, content=broken).codes())

    def test_the_same_dedupe_key_in_history_is_held_by_qg7_only(self):
        report = run(self.post, history=[{"dedupe_key": self.post.dedupe_key, "topic": self.post.title}])
        self.assertEqual(report.codes(), ["QG7-REUSE"])

    def test_an_empty_evidence_is_held_as_no_source(self):
        report = run(self.post, evidence_text="")
        self.assertIn("QG0-NO-SOURCE", report.codes())


# ----------------------------------------------------------------------------
# 5. 피드 글 불변과 근거 경계
# ----------------------------------------------------------------------------
def legacy_evidence_text(source):
    """이 묶음 앞의 evidence_text(피드 항목 읽기) — 시험 안에 고정한 사본."""
    if not isinstance(source, dict):
        return ("", 0)
    title = "" if source.get("title") is None else str(source.get("title"))
    summary = "" if source.get("summary") is None else str(source.get("summary"))
    parts = [title, "" if source.get("source") is None else str(source.get("source"))]
    published = source.get("published")
    if hasattr(published, "isoformat") and hasattr(published, "utcoffset"):
        parts.append(published.isoformat())
        try:
            offset = published.utcoffset()
            kst = (published - offset + datetime.timedelta(hours=9)) if offset is not None else published + datetime.timedelta(hours=9)
            parts.append(kst.date().isoformat())
        except (OverflowError, ValueError, TypeError):
            pass
    parts.append(summary)
    return ("\n".join(p for p in parts if p)[:qg.MAX_EVIDENCE_CHARS], len(summary))


def legacy_source_ref(source):
    if not isinstance(source, dict):
        return ("", "", "")
    pick = lambda key: "" if source.get(key) is None else str(source.get(key)).strip()   # noqa: E731
    return (pick("link"), pick("publisher_domain").lower(), pick("source"))


def legacy_rule_company(domain, public_domains):
    host = (domain or "").lower().rstrip(".")
    in_domains = lambda domains: any(host == d or host.endswith("." + d) for d in domains)   # noqa: E731
    if host and in_domains(qg.EXCLUDED_SOURCE_DOMAINS):
        return [("QG5-COMPANY", 5, "post", f"자동화에서 제외한 출처 도메인 — {qg._safe(host, 60)}")]
    if host and in_domains(public_domains):
        return []
    return [("QG5-COMPANY", 5, "post", f"출처 도메인이 공공·연구기관 목록 밖이거나 알 수 없음 — {qg._safe(host or '(없음)', 60)}")]


def mixed_radix_samples(fields, count, stride=7919):
    """필드별 값 목록의 곱 공간에서 count 개를 결정적으로 고른다(난수 없음)."""
    total = 1
    for values in fields.values():
        total *= len(values)
    for index in range(count):
        number = (index * stride) % total
        item = {}
        for name, values in fields.items():
            number, pick = divmod(number, len(values))
            item[name] = values[pick]
        yield item


AWARE = datetime.datetime(2026, 11, 4, 3, 0, tzinfo=datetime.timezone.utc)
FEED_FIELDS = {
    "title": (h.TITLE, "", None, 5),
    "source": ("Example Agency", None, "", " 공백 "),
    "link": (h.LINK, "", None, "ftp://x.example/a", " " + h.LINK + " "),
    "publisher_domain": (h.DOMAIN, "WWW.NASA.GOV", "evil.example", "", None, "www.pewresearch.org", "nasa.gov.", "Services.SWPC.NOAA.gov", " www.nasa.gov "),
    "summary": (h.SUMMARY, "", None, "x" * 5000, "값 3.4% 와 1,250,000"),
    "published": (AWARE, datetime.datetime(2026, 11, 4, 3, 0), "문자열", None, datetime.date(2026, 11, 4), datetime.datetime(2026, 11, 3, 20, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=-5)))),
    "extras": ({}, {"fact_post": 1}, {"fact_post": "true"}, {"fact_post": None}, {"fact_post": True}, {"provider_hosts": ["www.example-company.com"], "dedupe_key": "k"},
               {"fact_post": False, "evidence_text": "쓰이지 않음", "source_url": "https://x.example/", "source_domain": "x.example", "source_name": "n"}),
}


class FeedPathUnchangedTest(unittest.TestCase):
    def test_the_boundary_functions_read_feed_items_exactly_as_before(self):
        seen = 0
        for item in mixed_radix_samples(FEED_FIELDS, 900):
            source = {key: value for key, value in item.items() if key != "extras"}
            source.update(item["extras"])
            if source.get("fact_post") is True and all(isinstance(source.get(key), str) for key in ("evidence_text", "source_url", "source_domain", "source_name")):
                continue                                                                           # 올바른 Fact 사전은 이 시험 대상이 아니다(위 시험)
            seen += 1
            self.assertEqual(tuple(qg.evidence_text(source)), legacy_evidence_text(source))
            self.assertEqual(tuple(qg.source_ref(source)), legacy_source_ref(source))
            self.assertIsNone(qg.fact_ref(source))
        self.assertGreater(seen, 800)
        for source in (None, [], "문자열", 5, {}, {"title": None}):
            self.assertEqual(tuple(qg.evidence_text(source)), legacy_evidence_text(source))
            self.assertEqual(tuple(qg.source_ref(source)), legacy_source_ref(source))

    def test_the_company_rule_for_feed_items_is_the_same_as_before(self):
        domains = (h.DOMAIN, "WWW.NASA.GOV", "evil.example", "", None, "www.pewresearch.org", "PewResearch.ORG.", "nasa.gov.", "nasa.gov..", "services.swpc.noaa.gov", "services.swpc.noaa.gov:443",
                   "notnasa.gov", "nasa.gov.evil.example", "\u212aorea.kr", "www.bok.or.kr", " www.nasa.gov ", "a/.nasa.gov")
        for domain in domains:
            with self.subTest(domain=domain):
                self.assertEqual([tuple(hold) for hold in qg.rule_company(domain, qg.PUBLIC_SOURCE_DOMAINS)], legacy_rule_company(domain, qg.PUBLIC_SOURCE_DOMAINS))
        self.assertEqual(codes(qg.rule_company("\u212aorea.kr", qg.PUBLIC_SOURCE_DOMAINS)), [])      # 피드 글의 옛 동작(유니코드 소문자화)은 그대로다 — Fact 글만 ASCII 소문자화
        self.assertEqual(codes(qg.rule_company_fact("\u212aorea.kr", qg.PUBLIC_SOURCE_DOMAINS, [])), ["QG5-COMPANY"])

    def test_extra_fact_keys_on_a_feed_item_change_nothing_in_the_whole_gate(self):
        base = h.fixture_source()
        data = h.make_data()
        config = h.make_config(("ko",))
        histories = ((), [{"source_url": h.LINK, "dedupe_key": "k"}], [{"source_url": "https://other.example/a", "dedupe_key": "k"}, "문자열", {"dedupe_key": "k"}])
        extras = ({"fact_post": 1, "dedupe_key": "k"}, {"fact_post": "true", "provider_hosts": ["www.example-company.com"]}, {"fact_post": None, "evidence_text": "x 99999"}, {"provider_hosts": [h.DOMAIN], "dedupe_key": ""})
        for domain in (h.DOMAIN, "www.example-company.com", "WWW.PEWRESEARCH.ORG"):
            for history in histories:
                reference = qg.check_candidate(data, dict(base, publisher_domain=domain), history=history, config=config, as_of=h.AS_OF)
                for extra in extras:
                    with self.subTest(domain=domain, extra=sorted(extra)):
                        report = qg.check_candidate(data, dict(base, publisher_domain=domain, **extra), history=history, config=config, as_of=h.AS_OF)
                        self.assertEqual((report.holds, report.facts), (reference.holds, reference.facts))

    def test_a_feed_item_with_provider_hosts_is_still_held_by_qg5_and_reuse_still_uses_the_address(self):
        source = h.fixture_source(publisher_domain="www.example-company.com", provider_hosts=["www.example-company.com"], dedupe_key="k")
        self.assertIn("QG5-COMPANY", h.run_gate(source=source).codes())
        report = h.run_gate(history=[{"source_url": h.LINK + "?utm_source=x", "dedupe_key": "다른 키"}], source=h.fixture_source(dedupe_key="k"))
        self.assertIn("QG7-REUSE", report.codes())
        self.assertNotIn("QG0-DEDUPE-KEY", report.codes())

    def test_the_value_shapes_of_the_boundary_results_did_not_change(self):
        self.assertEqual(qg.Evidence._fields, ("text", "summary_chars"))
        self.assertEqual(qg.SourceRef._fields, ("link", "domain", "name"))
        self.assertEqual(qg.source_ref(None), ("", "", ""))
        self.assertEqual(qg.evidence_text(None), ("", 0))
        self.assertEqual(h.run_gate().codes(), [])
        self.assertEqual(sorted(h.run_gate().facts), ["body_chars_en", "body_chars_ko", "clone", "evidence_chars", "source_text_chars"])

    def test_the_generator_does_not_put_the_fact_marker_into_feed_items(self):
        tree = ast.parse((ROOT / "generator.py").read_text(encoding="utf-8"))
        feed_keys = {"title", "source", "link", "publisher_domain", "summary", "published"}
        feed_dicts = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = [key.value if isinstance(key, ast.Constant) else None for key in node.keys]
            if "publisher_domain" in keys:
                feed_dicts += 1
                self.assertNotIn("fact_post", keys)
                self.assertNotIn(None, keys, "** 로 펼친 키가 있으면 표지가 섞여 들어올 수 있다")
            if "fact_post" in keys:
                self.assertFalse(feed_keys & set(keys), "Fact 사전에 피드 항목의 키가 섞이면 안 된다")
        self.assertGreaterEqual(feed_dicts, 1)


class FactBoundaryStructureTest(unittest.TestCase):
    """Fact 사전의 칸을 읽는 곳은 정해진 함수뿐이다 — 규칙 함수는 source 를 받지 않는다."""

    @staticmethod
    def readers(keys):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        found = {key: set() for key in keys}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Constant) and isinstance(inner.value, str) and inner.value in found:
                        found[inner.value].add(node.name)
        return found

    def test_the_fact_keys_are_read_in_one_place(self):
        found = self.readers(FACT_KEYS)
        for key in ("fact_post", "evidence_text", "source_domain", "source_name", "provider_hosts"):
            self.assertEqual(found[key], {"_fact_source"}, key)
        self.assertEqual(found["source_url"], {"_fact_source", "rule_reuse"}, "source_url: Fact 사전은 _fact_source, 이력 항목은 rule_reuse")
        self.assertEqual(found["dedupe_key"], {"_fact_source", "rule_reuse_fact"}, "dedupe_key: Fact 사전은 _fact_source, 이력 항목은 rule_reuse_fact")
        self.assertEqual(found["recipe_id"], set())                                                # 참고용 칸 — 규칙이 읽지 않는다

    def test_no_rule_function_takes_the_source_item(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("rule_")]
        self.assertTrue({"rule_company", "rule_company_fact", "rule_reuse", "rule_reuse_fact"} <= set(names))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("rule_"):
                arguments = [arg.arg for arg in node.args.args]
                self.assertNotIn("source", arguments, node.name)
                self.assertNotIn("item", arguments, node.name)

    def test_the_gate_chooses_the_fact_rules_in_one_place_and_keeps_the_feed_calls(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "check_candidate")
        called = [inner.func.id for inner in ast.walk(function) if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)]
        for name in ("fact_ref", "rule_company", "rule_company_fact", "rule_reuse", "rule_reuse_fact"):
            self.assertEqual(called.count(name), 1, name)
        branch = next(node for node in ast.walk(function) if isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name) and node.test.left.id == "fact")
        self.assertEqual(sorted(inner.func.id for stmt in branch.body for inner in ast.walk(stmt) if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)), ["rule_company", "rule_reuse"])
        self.assertEqual(sorted(inner.func.id for stmt in branch.orelse for inner in ast.walk(stmt) if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)), ["rule_company_fact", "rule_reuse_fact"])

    def test_the_new_code_has_no_input_output_clock_or_randomness(self):
        text = MODULE.read_text(encoding="utf-8")
        start = text.index("def _ascii_lower")
        end = text.index("def evidence_text")
        code = "\n".join(line for line in text[start:end].splitlines() if not line.lstrip().startswith("#"))
        for banned in ("open(", "import ", "environ", "time.", "random", "datetime", "socket", "subprocess"):
            self.assertNotIn(banned, code, banned)


class FactGateIsPureTest(unittest.TestCase):
    def test_the_result_is_deterministic_and_the_inputs_are_not_changed(self):
        post = golden_posts()["r05_flares"]
        source, history = fact_dict(post), [{"dedupe_key": "다른 키", "source_url": post.source_url}]
        data = {"kr_title": post.title, "kr_content": golden_file("r05_flares")}
        before = (repr(source), repr(history), repr(data))
        first = qg.check_candidate(data, source, history=history, config=CONFIG, as_of=DAY)
        second = qg.check_candidate(copy.deepcopy(data), copy.deepcopy(source), history=copy.deepcopy(history), config=CONFIG, as_of=DAY)
        self.assertEqual((first.holds, first.facts), (second.holds, second.facts))
        self.assertEqual((repr(source), repr(history), repr(data)), before)

    def test_a_fact_check_never_touches_files_network_or_processes(self):
        post = golden_posts()["r06_scales"]
        data = {"kr_title": post.title, "kr_content": golden_file("r06_scales")}                 # 파일 모양 글은 미리 만들어 둔다(만드는 길은 생성기 함수라 파일을 읽을 수 있다)
        source = fact_dict(post)
        with mock.patch("builtins.open", side_effect=AssertionError("파일을 열었다")), mock.patch("socket.socket", side_effect=AssertionError("네트워크를 열었다")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("프로세스를 열었다")), mock.patch("os.system", side_effect=AssertionError("셸을 열었다")):
            self.assertEqual(qg.check_candidate(data, source, history=(), config=CONFIG, as_of=DAY).codes(), [])
            self.assertIn("QG7-REUSE", qg.check_candidate(data, source, history=[{"dedupe_key": post.dedupe_key}], config=CONFIG, as_of=DAY).codes())


class FactDocsTest(unittest.TestCase):
    """문서가 구현과 같은 말을 한다: QUALITY_GATE.md 11절·FACT_PATH.md 11절 표시·결함 레지스터 행. 문서 규칙(물결표·http 링크·Liquid 없음)도 본다."""

    @classmethod
    def setUpClass(cls):
        cls.gate_doc = (ROOT / "docs" / "QUALITY_GATE.md").read_text(encoding="utf-8")
        cls.fact_doc = (ROOT / "docs" / "FACT_PATH.md").read_text(encoding="utf-8")
        cls.register = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
        cls.section = cls.gate_doc[cls.gate_doc.index("## 11. "):]

    def test_the_gate_document_has_the_fact_section_with_the_interface_and_the_rules(self):
        self.assertEqual(len(re.findall(r"(?m)^## 11\. ", self.gate_doc)), 1)
        for needle in ("fact_post", "evidence_text", "source_url", "source_domain", "source_name", "provider_hosts", "dedupe_key", "QG0-NO-SOURCE", "QG0-DEDUPE-KEY", "QG5-COMPANY",
                       "QG7-REUSE", "정확히 같은 호스트", "접미사", "켈빈", "EXCLUDED_SOURCE_DOMAINS", "tests/test_quality_gate_fact.py", "켜지 않", "fact_ref", "_fact_source"):
            self.assertIn(needle, self.section, needle)

    def test_the_new_section_follows_the_document_rules(self):
        self.assertNotIn("~", self.section)
        self.assertNotRegex(self.section, r"https?://")
        self.assertNotRegex(self.section, r"\{\{|\{%")
        self.assertNotIn("~", qg.__doc__)

    def test_the_decision_rows_exist_once_each_and_have_six_cells(self):
        for number in range(260, 269):                                                            # 이 묶음이 쓰는 번호(D-269 는 예비)
            rows = [line for line in self.register.splitlines() if line.startswith(f"| **D-{number}** |")]
            self.assertEqual(len(rows), 1, f"D-{number}")
            self.assertEqual(rows[0].count("|"), 7, f"D-{number}")
            self.assertIn("QUALITY_GATE.md", rows[0], f"D-{number}")
        self.assertLessEqual(len([line for line in self.register.splitlines() if line.startswith("| **D-269** |")]), 1)

    def test_the_decisions_are_listed_in_the_gate_document_too(self):
        for number in range(260, 269):
            self.assertEqual(len(re.findall(rf"(?m)^\| D-{number} \|", self.section)), 1, f"D-{number}")

    def test_the_fact_path_document_marks_the_three_items_as_implemented(self):
        section = self.fact_doc[self.fact_doc.index("### 2단계 연결 계획"):self.fact_doc.index("## 12. 설계 결정")]
        for prefix in ("3. **Gate 의 두 함수만", "4. **Gate `QG5-COMPANY`", "7. **중복 방지**"):
            line = next(line for line in section.splitlines() if line.startswith(prefix))
            self.assertIn("구현됨(S2BG)", line, prefix)
            self.assertIn("QUALITY_GATE.md", line, prefix)


if __name__ == "__main__":
    unittest.main()
