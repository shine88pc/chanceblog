"""R-119 A(2026-11-05) 시험 — Chance 글감 소스 1차 6곳(미 FTC 보도자료·연준 FEDS Notes·영국 CMA·집행위 R&I·집행위 EMPL·미 NSF 뉴스) 추가.
네트워크 없이 돈다(가짜 피드). 새 소스가 하는 일과 기존 소스·기존 동작이 그대로임을 함께 못박는다.

배경: 2026-11-05 Chance 9시 슬롯이 세 번(09:32·15:50·16:25) 후보 3건이 전부 탈락했다 — 요약이 얇은 글감으로 쓴 한글 본문이 463~799자라 최소 1000자에 못 미쳤다. 뿌리는 글감 공급 가뭄이었고
(docs/analysis/chance-stall-2026-11-04/), 운영자 결정 요청 R-119 의 기본값(A=1)이 이 6곳을 승인했다. 하지 않는 것: 건강·소비자 안전 소스, 국가데이터처, 미 노동부, 공식 기관 밖, 보충 소스.

이 시험이 지키는 것: ① 6곳 각각의 이름·분야·주소·약관 필드·인용 줄·고지문·입력 상한·제외 규칙·주제어·지침 ② 신뢰 도메인은 정확히 세 개(ftc.gov·www.gov.uk 의 경제 분야·nsf.gov)만 늘었고 쓰지 않는 소스의 도메인은 없다
③ 가짜 피드로 실제 엔진(fetch_news_items·pick_topic_candidates·iter_candidate_lanes)이 새 소스에서 후보를 만든다 — 72시간 창·짧은 요약·다른 호스트·제외 규칙·기사 페이지를 읽지 않음
④ 기존 14개 소스의 정의는 2026-11-05 이전(92c70a8)과 한 글자도 다르지 않고(해시), 새 소스가 비어 있으면 기존 출력이 그대로이며, 기존 상수(72시간·후보 3건·요약 1,800자·얇은 근거 150자)가 그대로다.
표본 피드의 제목은 모양만 따라 만든 가짜 제목이다(원문을 저장소에 복사하지 않는다).
"""
import hashlib
import json
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from xml.sax.saxutils import escape

import _bootstrap  # noqa: F401
import generator as g
from lock_helpers import pre_flip
from test_generator_slots import FakeResponse, rss, run_captured

ROOT = _bootstrap.ROOT

OLD_NAMES = ["NASA", "UN News", "Pew Research Center", "Federal Reserve", "European Commission", "European Commission · Energy",
             "European Commission · Environment", "European Commission · JRC", "EU Digital Strategy", "Statistics Canada · economy",
             "Statistics Canada · society", "Statistics Canada · daily life", "GOV.UK · Environment & Energy", "GOV.UK · Science & Technology"]
FTC, FEDS, CMA, RTD, EMPL, NSF = ("FTC · press (consumer protection)", "Federal Reserve · FEDS Notes", "UK CMA · Competition & Markets",
                                  "European Commission · R&I", "European Commission · Employment & Social Affairs", "U.S. NSF · news")
NEW_NAMES = [FTC, FEDS, CMA, RTD, EMPL, NSF]

# 2026-11-05 이전(origin/main 92c70a8)의 기존 소스 14개를 json.dumps(sort_keys=True, ensure_ascii=False) 로 직렬화한 글자열의 SHA-256.
# 기존 소스의 어느 키 하나(주소·약관·제외 규칙·고지문·지침)가 바뀌거나 공유 상수가 바뀌어 기존 소스가 달라지면 이 값이 달라진다.
OLD_SOURCES_SHA256 = "efb15888882ebf75a0c034c08897df88345b30b67267100432cccc6471935930"

BASELINE_TRUSTED = {
    "science": ["science.org", "pnas.org", "cell.com", "who.int", "nih.gov", "noaa.gov", "nasa.gov", "ipcc.ch", "jpl.nasa.gov", "ec.europa.eu", "www.gov.uk",
                "reuters.com", "apnews.com"],
    "economy": ["oecd.org", "imf.org", "worldbank.org", "federalreserve.gov", "bls.gov", "bok.or.kr", "kostat.go.kr", "kdi.re.kr", "ec.europa.eu",
                "statcan.gc.ca", "reuters.com", "apnews.com", "ft.com", "bloomberg.com"],
    "society": ["oecd.org", "un.org", "unesco.org", "unicef.org", "korea.kr", "kostat.go.kr", "kdi.re.kr", "commission.europa.eu", "ec.europa.eu",
                "statcan.gc.ca", "reuters.com", "apnews.com"],
    "technology": ["nist.gov", "acm.org", "arxiv.org", "science.org", "ec.europa.eu", "www.gov.uk", "reuters.com", "apnews.com"],
    "culture": ["unesco.org", "pewresearch.org", "reuters.com", "apnews.com", "variety.com", "nytimes.com"],
    "daily_life": ["who.int", "nih.gov", "nhs.uk", "cdc.gov", "apa.org", "kostat.go.kr", "korea.kr", "mfds.go.kr", "foodsafetykorea.go.kr", "kca.go.kr",
                   "consumer.go.kr", "statcan.gc.ca", "reuters.com", "apnews.com"],
}
ADDED_DOMAINS = {"economy": ["ftc.gov", "www.gov.uk"], "technology": ["nsf.gov"]}
# R-119 가 이번에 하지 않기로 한 소스(B 건강·소비자 안전, C 국가데이터처, D 미 노동부, E 공식 기관 밖, 보충 소스)의 도메인 — 소스에도 신뢰 목록에도 없다.
NOT_APPROVED_HOSTS = ("dol.gov", "mods.go.kr", "fda.gov", "ecdc.europa.eu", "cedefop.europa.eu", "consumer.ftc.gov", "arxiv.org", "single-market-economy.ec.europa.eu",
                      "taxation-customs.ec.europa.eu", "finance.ec.europa.eu", "agriculture.ec.europa.eu", "transport.ec.europa.eu", "nist.gov")

HEALTH = "건강·의료 정보는 정책과 통계 사실만 전하고 진단·치료·복용·예방 효과를 조언하지 마세요."
OGL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
CC_BY = "https://creativecommons.org/licenses/by/4.0/"

SPEC = {
    FTC: dict(lane="economy", url="https://www.ftc.gov/feeds/press-release-consumer-protection.xml", display="Federal Trade Commission", host="www.ftc.gov",
              terms={"status": "allowed", "checked": "2026-11-04", "url": "https://www.ftc.gov/policy-notices/website-policy"},
              citation="“Sample release.” Source: United States Federal Trade Commission, www.ftc.gov, October 23, 2026 <https://www.ftc.gov/news-events/news/press-releases/x>",
              notice_ko=("미국 연방거래위원회(FTC)", "AI 도구가", "FTC는 이 글을 검토하거나 보증하지 않았으며", "FTC의 공식 입장이나 공식 문서가 아닙니다"),
              notice_en=("U.S. Federal Trade Commission", "written with an AI tool", "The FTC has not reviewed or endorsed it", "not an official FTC publication or position"),
              keys={"exclude_title"}, cap=1500),
    FEDS: dict(lane="economy", url="https://www.federalreserve.gov/feeds/feds_notes.xml", display="Federal Reserve Board (FEDS Notes)", host="www.federalreserve.gov",
               terms={"status": "allowed", "checked": "2026-11-04", "url": "https://www.federalreserve.gov/disclaimer.htm"},
               citation="“Sample release.” FEDS Notes, Board of Governors of the Federal Reserve System, October 23, 2026 <https://www.federalreserve.gov/econres/notes/feds-notes/x>",
               notice_ko=("연방준비제도 이사회 연구진", "AI 도구가", "저자의 것이며 연준이나 이사회의 공식 입장이 아니고", "이사회는 이 글을 검토하거나 승인하지 않았습니다"),
               notice_en=("staff of the Federal Reserve Board", "written with an AI tool", "do not represent the Board or the Federal Reserve", "the Board has not reviewed or approved this article"),
               keys=set(), cap=None),
    CMA: dict(lane="economy", url=g._GOVUK_FEED + "organisations%5B%5D=competition-and-markets-authority", display="GOV.UK (Competition and Markets Authority)",
              host="www.gov.uk", terms={"status": "allowed", "checked": "2026-10-26", "url": "https://www.gov.uk/help/terms-conditions"},
              citation="“Sample release.” GOV.UK, October 23, 2026 <https://www.gov.uk/government/news/x>. Contains public sector information licensed under the Open Government Licence v3.0. (" + OGL + ")",
              notice_ko=("영국 정부(GOV.UK)", "AI 도구가", "Open Government Licence v3.0", "보증하지 않았으며", "공식 입장이나 공식 문서가 아닙니다"),
              notice_en=("GOV.UK", "written with an AI tool", "Contains public sector information licensed under the Open Government Licence v3.0.", "have not reviewed or endorsed this article"),
              keys={"exclude_title", "exclude_link"}, cap=None),
    RTD: dict(lane="technology", url="https://research-and-innovation.ec.europa.eu/node/2/rss_en", display="European Commission (DG Research and Innovation)",
              host="research-and-innovation.ec.europa.eu", terms={"status": "allowed", "checked": "2026-10-26", "url": "https://commission.europa.eu/legal-notice_en"},
              citation="“Sample release.” European Commission, DG Research and Innovation, October 23, 2026 <https://research-and-innovation.ec.europa.eu/news/x>. © European Union, licensed under CC BY 4.0 (" + CC_BY + ").",
              notice_ko=("유럽연합 집행위원회", "AI 도구가", "CC BY 4.0", "바뀐 부분이 있습니다", "집행위원회는 이 글을 검토하거나 보증하지 않았습니다"),
              notice_en=("European Commission", "written with an AI tool", "changes were made", "CC BY 4.0", "has not reviewed or endorsed this article"),
              keys={"exclude_title", "exclude_link", "exclude_tags", "topic_regex"}, cap=None),
    EMPL: dict(lane="society", url="https://employment-social-affairs.ec.europa.eu/node/2/rss_en", display="European Commission (DG Employment, Social Affairs and Inclusion)",
               host="employment-social-affairs.ec.europa.eu", terms={"status": "allowed", "checked": "2026-10-26", "url": "https://commission.europa.eu/legal-notice_en"},
               citation="“Sample release.” European Commission, DG Employment, Social Affairs and Inclusion, October 23, 2026 <https://employment-social-affairs.ec.europa.eu/news/x>. © European Union, licensed under CC BY 4.0 (" + CC_BY + ").",
               notice_ko=("유럽연합 집행위원회", "AI 도구가", "CC BY 4.0", "바뀐 부분이 있습니다", "집행위원회는 이 글을 검토하거나 보증하지 않았습니다"),
               notice_en=("European Commission", "written with an AI tool", "changes were made", "CC BY 4.0", "has not reviewed or endorsed this article"),
               keys={"exclude_title", "exclude_link", "exclude_tags"}, cap=None),
    NSF: dict(lane="technology", url="https://www.nsf.gov/rss/rss_www_news.xml", display="U.S. National Science Foundation", host="www.nsf.gov",
              terms={"status": "allowed", "checked": "2026-11-04", "url": "https://www.nsf.gov/policies/digital"},
              citation="“Sample release.” Source: U.S. National Science Foundation, October 23, 2026 <https://www.nsf.gov/news/x>",
              notice_ko=("미국 국립과학재단(NSF)", "AI 도구가", "NSF는 이 글을 검토하거나 보증하지 않았으며", "NSF의 공식 입장이 아닙니다", "사진·그래픽은 사용하지 않았습니다"),
              notice_en=("U.S. National Science Foundation", "written with an AI tool", "NSF has not reviewed or endorsed it", "not an official NSF position", "No NSF images or graphics are used"),
              keys={"exclude_title"}, cap=None),
}

# 규칙 문장(소스 고유) — 지침(prompt_rule)에 그대로 들어 있어야 하는 말
PROMPT_SENTENCES = {
    FTC: ("FTC가 제기한 소송·조치와 업체의 해명·합의를 구분하세요.", "'FTC는 …라고 주장했다'(영어 글은 'the FTC alleges')", "특정 업체나 사람을 단정적으로 비난하지 마세요.",
          "독자에게 법률·금융 조언을 하지 말고", "보도자료 문장을 그대로 옮기지 말고", "따옴표로 옮겨 쓰지 마세요", "'By BCP Staff'는 글쓴이 표기이니 글에 쓰지 마세요.", HEALTH),
    FEDS: ("연준이나 이사회의 입장·결정·전망으로 쓰지 마세요", "저자의 분석임을 밝히세요", "저자들의 이름", "직함·소속을 덧붙이지 마세요", "금융 전문 용어는 처음 나올 때 쉬운 말로 풀어 쓰세요.",
           "독자에게 투자·재테크 조언을 하지 마세요."),
    CMA: (g._GOVUK_PROMPT_RULE, "영국 경쟁시장청(CMA)의 조사 착수·잠정 판단·의견 수렴은 확정된 결정이 아님을 구분하고", "'the CMA has provisionally found'", "특정 기업의 위법을 단정하지 마세요.", HEALTH),
    RTD: (g._EC_PROMPT_RULE,),
    EMPL: (g._EC_PROMPT_RULE,),
    NSF: ("NSF가 지원한 연구라고 해서 NSF가 결과를 보증하거나 이 글을 검토한 것처럼 쓰지 마세요.", "연구자의 주장과 확인된 결과를 구분하고", "발언이나 수치를 지어내지 마세요.", HEALTH),
}


def source(name):
    return next(s for s in g.NEWS_SOURCES if s["name"] == name)


def hours_ago(hours):
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def digest(sources):
    return hashlib.sha256(json.dumps(sources, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atom(entries):
    """GOV.UK 뉴스 Atom 모양: entries = (제목, 주소, updated(datetime), 요약) 목록."""
    body = "".join(f"<entry><id>tag:www.gov.uk,2005:{escape(link)}</id><updated>{updated.isoformat()}</updated>"
                   f"<link rel='alternate' type='text/html' href='{escape(link)}'/><title>{escape(title)}</title>"
                   f"<summary type='html'>{escape(summary)}</summary></entry>" for title, link, updated, summary in entries)
    return f"<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>{body}</feed>".encode()


EMPTY = rss([])


class Router:
    """urllib.request.urlopen 자리에 넣는 가짜: 주소별 피드를 내주고(없으면 빈 피드) 요청한 주소를 모두 적는다."""

    def __init__(self, feeds=None):
        self.feeds, self.requested = dict(feeds or {}), []

    def __call__(self, req, timeout=0):
        url = getattr(req, "full_url", req)
        self.requested.append(url)
        return FakeResponse(self.feeds.get(url, EMPTY))


def no_page_reads(url):
    raise AssertionError(f"기사 페이지를 읽었다: {url}")


def fetch(lane, router, sources=None, stats=None):
    """실제 fetch_news_items 를 가짜 피드로 돈다(기사 페이지·주소 해석은 부르면 실패)."""
    patches = [mock.patch.object(g.urllib.request, "urlopen", router), mock.patch.object(g, "_fetch_source_excerpt", side_effect=no_page_reads),
               mock.patch.object(g, "_resolve_article_url", side_effect=no_page_reads)]
    if sources is not None:
        patches.append(mock.patch.object(g, "NEWS_SOURCES", sources))
    for patcher in patches:
        patcher.start()
    try:
        return run_captured(g.fetch_news_items, lane, stats=stats)
    finally:
        for patcher in reversed(patches):
            patcher.stop()


def good_item(name, hours=5, summary_len=None):
    """소스 `name` 의 실제 피드 모양(분류 태그·주소 경로)을 따른 가짜 글감 한 건 → (제목, 주소, 게시 시각, 요약, '', 태그)."""
    spec = SPEC[name]
    host = spec["host"]
    base = {FTC: ("FTC Sues Online Seller Over Hidden Fees", f"https://{host}/news-events/news/press-releases/2026/11/ftc-sues-online-seller", [], 700),
            FEDS: ("FEDS Note: A Short Analysis of Bond Market Liquidity", f"https://{host}/econres/notes/feds-notes/a-short-analysis-of-bond-market-liquidity-20261102.html",
                   ["FEDS Notes"], 420),
            CMA: ("CMA opens investigation into a software company's terms", f"https://{host}/government/news/cma-opens-investigation-into-software-terms", [], 130),
            RTD: ("New EU initiative on artificial intelligence in research", f"https://{host}/news/all-research-and-innovation-news/new-eu-ai-initiative_en",
                  ["Directorate-General for Research and Innovation", "News article", "artificial intelligence"], 210),
            EMPL: ("New EU rules help workers move between countries", f"https://{host}/news/new-eu-rules-workers-move_en",
                   ["Directorate-General for Employment, Social Affairs and Inclusion", "News article", "labour mobility"], 210),
            NSF: ("Researchers build a faster quantum sensor", f"https://{host}/news/researchers-build-faster-quantum-sensor", [], 220)}[name]
    title, link, tags, length = base
    summary = ("A plain factual summary sentence for this sample release. " * 80)[:summary_len or length]
    return title, link, hours_ago(hours), summary, "", tags


def feed_for(name, items):
    """소스의 실제 피드 형식(CMA 만 Atom, 나머지는 RSS)으로 가짜 피드 바이트를 만든다. items 는 good_item 모양의 튜플 목록."""
    if name == CMA:
        return atom([(title, link, published, summary) for title, link, published, summary, _pub, *_rest in items])
    return rss(items)


class NewSourceDefinitionTest(unittest.TestCase):
    def test_the_list_is_the_old_fourteen_unchanged_in_order_and_then_exactly_the_six_new_ones(self):
        self.assertEqual([s["name"] for s in g.NEWS_SOURCES], OLD_NAMES + NEW_NAMES)
        self.assertEqual(len(g.NEWS_SOURCES), 20)

    def test_each_new_source_is_pinned_name_lane_url_display_name_and_terms(self):
        for name, spec in SPEC.items():
            with self.subTest(source=name):
                src = source(name)
                self.assertEqual((src["lane"], src["url"], src["display_name"]), (spec["lane"], spec["url"], spec["display"]))
                self.assertEqual(src["terms"], spec["terms"])
                self.assertEqual(g._host(src["url"]), spec["host"])
                self.assertNotIn("blocker", src["terms"])          # 6곳 모두 allowed(보류 없음)

    def test_each_new_source_reads_only_the_feed_and_never_an_article_page(self):
        for name in NEW_NAMES:
            with self.subTest(source=name):
                src = source(name)
                self.assertIs(src.get("no_page_fetch"), True)
                for key in ("google", "tech_filter", "page_delay"):
                    self.assertNotIn(key, src)

    def test_each_new_source_has_exactly_the_optional_keys_it_should(self):
        optional = ("exclude_title", "exclude_link", "exclude_tags", "topic_regex")
        for name, spec in SPEC.items():
            with self.subTest(source=name):
                src = source(name)
                self.assertEqual({k for k in optional if k in src}, spec["keys"])
                for key in optional:
                    if key in src:
                        re.compile(src[key], re.I)
                        self.assertTrue(src[key].strip())

    def test_the_credit_line_and_notices_carry_what_each_publisher_asks_for(self):
        for name, spec in SPEC.items():
            with self.subTest(source=name):
                src = source(name)
                sample = {"title": "Sample release", "link": re.search(r"<(https://[^>]+)>", spec["citation"]).group(1), "published": datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)}
                self.assertEqual(g._citation_line(src["citation"], sample), spec["citation"])
                self.assertEqual(sorted(src["notice"]), ["en", "ko"])
                for needle in spec["notice_ko"]:
                    self.assertIn(needle, src["notice"]["ko"])
                for needle in spec["notice_en"]:
                    self.assertIn(needle, src["notice"]["en"])
                # 기관이 이 글을 검토·보증하지 않았다는 문장이 두 언어에 모두 있다
                self.assertRegex(src["notice"]["ko"], r"검토하거나 (?:보증|승인)하지 않았")
                self.assertRegex(src["notice"]["en"], r"has not reviewed or (?:endorsed|approved)|have not reviewed or endorsed")

    def test_the_prompt_rules_say_what_each_source_needs_and_nothing_the_common_rules_already_say(self):
        for name, sentences in PROMPT_SENTENCES.items():
            with self.subTest(source=name):
                rule = source(name)["prompt_rule"]
                for sentence in sentences:
                    self.assertIn(sentence, rule)
                for marker in ("요약에 없는", "환산", "반올림"):
                    self.assertNotIn(marker, rule)

    def test_government_rules_forbid_endorsement_claims_and_the_enforcement_sources_separate_allegations_from_decisions(self):
        for name in (FTC, FEDS, NSF, RTD, EMPL, CMA):
            with self.subTest(source=name):
                self.assertRegex(source(name)["prompt_rule"], r"검토·보증|검토한 것처럼|보증하거나|입장·결정·전망으로 쓰지|검토하거나 보증")
        self.assertIn("주장", source(FTC)["prompt_rule"])
        self.assertIn("확정된 결정이 아님", source(CMA)["prompt_rule"])
        self.assertIn("공식 입장이 아니", source(FEDS)["notice"]["ko"])

    def test_only_the_ftc_pins_an_input_limit_and_every_limit_is_at_or_below_the_default(self):
        for name, spec in SPEC.items():
            with self.subTest(source=name):
                src = source(name)
                self.assertEqual(src.get("summary_max_chars"), spec["cap"])
                self.assertLessEqual(src.get("summary_max_chars") or g.SUMMARY_MAX_CHARS, g.SUMMARY_MAX_CHARS)
        self.assertLess(source(FTC)["summary_max_chars"], g.SUMMARY_MAX_CHARS)

    def test_names_that_the_older_tests_count_by_prefix_are_not_disturbed(self):
        # test_generator_slots 는 'GOV.UK' 로 시작하는 소스를 2개로 세고(분야별 피드 순서를 가정), 통계청은 3개로 센다
        self.assertEqual(len([s for s in g.NEWS_SOURCES if s["name"].startswith("GOV.UK")]), 2)
        self.assertEqual(len([s for s in g.NEWS_SOURCES if s["name"].startswith("Statistics Canada")]), 3)

    def test_the_six_sources_are_spread_over_the_three_thin_lanes_only(self):
        lanes = {}
        for name in NEW_NAMES:
            lanes.setdefault(source(name)["lane"], []).append(name)
        self.assertEqual(lanes, {"economy": [FTC, FEDS, CMA], "technology": [RTD, NSF], "society": [EMPL]})

    def test_nothing_outside_the_approved_six_was_added(self):
        for src in g.NEWS_SOURCES:
            host = g._host(src["url"])
            for banned in NOT_APPROVED_HOSTS:
                self.assertFalse(g._host_in(host, (banned,)), f"{src['name']} 이 승인 밖 호스트 {banned} 를 읽는다")
        self.assertEqual([s["name"] for s in g.NEWS_SOURCES if s["name"] not in OLD_NAMES], NEW_NAMES)


class TrustedDomainTest(unittest.TestCase):
    def test_exactly_three_domains_were_added_and_the_old_ones_keep_their_order(self):
        for lane, old in BASELINE_TRUSTED.items():
            with self.subTest(lane=lane):
                now = list(g.TRUSTED_SOURCE_DOMAINS[lane])
                self.assertEqual([d for d in now if d not in ADDED_DOMAINS.get(lane, [])], old)       # 기존 항목은 같은 순서로 그대로
                self.assertEqual(sorted(d for d in now if d not in old), sorted(ADDED_DOMAINS.get(lane, [])))
        self.assertEqual(set(g.TRUSTED_SOURCE_DOMAINS), set(BASELINE_TRUSTED))

    def test_domains_of_the_sources_that_were_not_approved_are_in_no_trust_list(self):
        for lane, domains in g.TRUSTED_SOURCE_DOMAINS.items():
            for banned in ("dol.gov", "mods.go.kr", "fda.gov", "ecdc.europa.eu", "cedefop.europa.eu"):
                self.assertNotIn(banned, domains, (lane, banned))

    def test_each_new_domain_is_trusted_only_in_its_own_lane(self):
        trusted = {(host, lane) for host in ("www.ftc.gov", "ftc.gov", "www.nsf.gov", "new.nsf.gov") for lane in g.EDITORIAL_LANES if g._trusted_domain(host, lane)}
        self.assertEqual(trusted, {("www.ftc.gov", "economy"), ("ftc.gov", "economy"), ("www.nsf.gov", "technology"), ("new.nsf.gov", "technology")})
        for lane in g.EDITORIAL_LANES:
            self.assertEqual(g._trusted_domain("www.gov.uk", lane), lane in {"science", "technology", "economy"}, lane)

    def test_each_new_sources_feed_and_article_hosts_are_trusted_in_its_lane(self):
        for name, spec in SPEC.items():
            with self.subTest(source=name):
                self.assertTrue(g._trusted_domain(g._host(spec["url"]), spec["lane"]))
                self.assertTrue(g._trusted_domain(spec["host"], spec["lane"]))

    def test_look_alike_hosts_are_never_trusted(self):
        for host in ("evilftc.gov", "ftc.gov.evil.example", "notnsf.gov", "nsf.gov.evil.example", "www.gov.uk.evil.example", "evilgov.uk", "gov.uk", "ons.gov.uk",
                     "assets.publishing.service.gov.uk", "eeas.europa.eu", "www.eeas.europa.eu"):
            for lane in g.EDITORIAL_LANES:
                with self.subTest(host=host, lane=lane):
                    self.assertFalse(g._trusted_domain(host, lane))

    def test_the_blocked_publisher_list_is_unchanged(self):
        self.assertEqual(g.TERMS_BLOCKED_DOMAINS, ("bbc.com", "bbc.co.uk", "bbci.co.uk", "theguardian.com", "guardian.co.uk", "nature.com", "technologyreview.com",
                                                   "aitimes.com", "arstechnica.com", "ieee.org", "etnews.com"))
        for lane, domains in g.TRUSTED_SOURCE_DOMAINS.items():
            for domain in domains:
                self.assertFalse(g._host_in(domain, g.TERMS_BLOCKED_DOMAINS), (lane, domain))


class ExclusionRuleTest(unittest.TestCase):
    """제외·주제 규칙을 가짜 제목(실제 피드의 제목 모양을 따름)으로 고정한다. 규칙을 하나씩 지우면 실패하게 낱말마다 단독 제목을 둔다."""

    def excluded(self, name, title, link="https://example.test/x", categories=()):
        return g._rule_excludes(source(name), title, {"link": link, "categories": list(categories)})

    def on_topic(self, name, title, categories=()):
        return bool(re.search(source(name)["topic_regex"], " ".join([title, *categories]), re.I))

    def test_ftc_drops_comment_requests_deadline_extensions_withdrawals_commissioner_statements_and_fee_notices(self):
        for title in ("FTC Seeks Public Comment on Proposed Rule Changes", "FTC Seeks Comment on a Draft Guide", "FTC Extends Public Comment Period on a Proposed Policy",
                      "FTC Extends the Comment Period for a Rule Review", "FTC Withdraws Outdated Guidance", "FTC Withdraw Notice Published",
                      "Commissioner Smith Remarks at a Conference", "FTC Chairman Doe Names New Bureau Director", "Statement from the FTC on a Court Decision",
                      "Statement by the Agency on a Ruling", "Statement of the FTC on Recent Events", "Statement on a Merger Review",
                      "FTC Approves Final Order Settling Charges", "FTC Announces 2027 Telemarketer Fees for the Registry"):
            with self.subTest(title=title):
                self.assertTrue(self.excluded(FTC, title), title)

    def test_ftc_keeps_enforcement_refunds_reports_and_orders(self):
        for title in ("FTC Sues Online Seller Over Hidden Fees", "FTC Sends Refunds to Consumers Harmed by a Subscription Scheme", "FTC Issues Annual Report to Congress on Older Adults",
                      "FTC Finalizes Orders With Payment Processors", "FTC Launches Personalized Pricing Inquiry", "Court Shuts Down Illegal Debt Relief Operation",
                      "FTC Publishes Price Transparency FAQs for Auto Dealers", "FTC Takes Action Against Payment Processor"):
            with self.subTest(title=title):
                self.assertFalse(self.excluded(FTC, title), title)

    def test_the_two_commission_directorates_drop_statements_visits_calls_events_and_cedefop_items_but_keep_news(self):
        for name in (RTD, EMPL):
            for title in ("Statement by Executive Vice-President Doe on a proposal", "Joint statement on research cooperation", "Speech by the Commissioner at the forum",
                          "Opening remarks by the Commissioner on funding", "Commissioner Smith visits Warsaw", "Executive Vice-President Doe meets ministers in Paris",
                          "Apply now for the new fellowship", "Call for experts to join the advisory board", "Call for tenders for a study", "Call for proposals on skills",
                          "Call for feedback on the draft guidelines", "Call for evidence on future rules", "Webinar on the new rules", "Podcast episode on skills policy"):
                with self.subTest(source=name, title=title):
                    self.assertTrue(self.excluded(name, title), title)
            for tag in ("Cedefop", "Statement", "Statements", "Events", "Event", "cedefop"):
                with self.subTest(source=name, tag=tag):
                    self.assertTrue(self.excluded(name, "A plain headline", categories=("Directorate-General", "News article", tag)), tag)
            for title in ("New EU rules help workers move between countries", "Commission publishes the annual report on research funding", "Importers must apply for authorisation by 2027"):
                with self.subTest(source=name, title=title):
                    self.assertFalse(self.excluded(name, title, categories=("Directorate-General", "News article")), title)
            for link in ("https://ec.europa.eu/commission/presscorner/detail/en/ip_26_1", "https://ec.europa.eu/eurostat/web/x", "https://x.test/horizon-magazine/story"):
                with self.subTest(source=name, link=link):
                    self.assertTrue(self.excluded(name, "A plain headline", link=link), link)

    def test_tags_are_matched_whole_so_ordinary_tags_that_merely_contain_the_words_survive(self):
        for name in (RTD, EMPL):
            for tag in ("Cedefop skills panorama", "Eventually", "Statement of work", "Prevention"):
                with self.subTest(source=name, tag=tag):
                    self.assertFalse(self.excluded(name, "A plain headline", categories=(tag,)), tag)

    def test_the_research_directorate_topic_filter_really_filters(self):
        dg = "Directorate-General for Research and Innovation"      # 이 피드의 모든 항목에 붙는 분류 태그 — 조사 초안의 주제어 'innovation' 은 이것 때문에 아무것도 거르지 못했다
        self.assertFalse(self.on_topic(RTD, "Meeting of the joint committee", (dg, "News article", "international cooperation")))
        self.assertFalse(self.on_topic(RTD, "Prize winners announced", (dg, "News alerts", "research programme")))
        self.assertNotIn("innovation", source(RTD)["topic_regex"].lower())
        for title, tags in (("New EU initiative on artificial intelligence in research", ()), ("Joint website on Earth observation", ("earth observation",)),
                            ("Fusion research prize", ("nuclear fusion",)), ("Cloud services for researchers", ("cloud computing",)), ("Open science policy update", ("open science",))):
            with self.subTest(title=title):
                self.assertTrue(self.on_topic(RTD, title, (dg, "News article", *tags)), title)
        # 주제어 하나하나가 제 몫을 한다: 낱말마다 그 낱말만 든 제목을 두고, 낱말 하나를 빼거나 더하면 실패하게 한다(낱말이 겹치는 제목은 하나를 지워도 통과해 버린다)
        parts = source(RTD)["topic_regex"].split("|")
        samples = {"artificial intelligence": "artificial intelligence", r"\bAI\b": "AI", "quantum": "quantum", "fusion": "fusion", "supercomput": "supercomputers",
                   "semiconductor": "semiconductor", r"\bchips?\b": "chips", "robot": "robots", "space": "space", "satellite": "satellite", "earth observation": "Earth observation",
                   "digital": "digital", r"\bdata\b": "data", "cyber": "cyber", "cloud": "cloud", "biotech": "biotech", "bioeconomy": "bioeconomy", "battery": "battery",
                   "hydrogen": "hydrogen", "photonic": "photonics", "open science": "open science", "research infrastructure": "research infrastructure"}
        self.assertEqual(parts, list(samples))
        for part, word in samples.items():
            with self.subTest(part=part):
                text = f"A story about {word} for readers"
                self.assertEqual([p for p in parts if re.search(p, text, re.I)], [part], text)

    def test_the_social_affairs_directorate_has_no_topic_filter_and_the_other_new_sources_have_none_either(self):
        for name in (FTC, FEDS, CMA, EMPL, NSF):
            self.assertNotIn("topic_regex", source(name), name)

    def test_nsf_drops_podcast_blurbs_and_statements_but_keeps_science_news_and_program_announcements(self):
        for title in ("Podcast: The laser that could change physics", "podcast: lowercase also counts", "Joint statement on research security", "NSF-UKRI metascience statement"):
            with self.subTest(title=title):
                self.assertTrue(self.excluded(NSF, title), title)
        for title in ("Researchers build a faster quantum sensor", "NSF launches a pilot to speed up technology transfer", "New dwarf planet candidate found by a telescope",
                      "NSF announces new topics for a research initiative", "Podcasting tools help teachers"):
            with self.subTest(title=title):
                self.assertFalse(self.excluded(NSF, title), title)

    def test_cma_keeps_news_stories_only_and_drops_publications_speeches_and_personnel_notices(self):
        news = "https://www.gov.uk/government/news/"
        for path in ("publications/cma-response-to-consultation", "speeches/a-speech-by-the-chief-executive", "case-studies/a-case", "statistics/x", "news"):
            with self.subTest(path=path):
                self.assertTrue(self.excluded(CMA, "A plain headline", link=("https://www.gov.uk/government/" + path)), path)
        self.assertFalse(self.excluded(CMA, "CMA fines firms over misleading sales tactics", link=news + "cma-fines-firms"))
        self.assertTrue(self.excluded(CMA, "Two new appointments to the board", link=news + "x"))
        self.assertTrue(self.excluded(CMA, "Call for evidence on a market study", link=news + "x"))
        self.assertTrue(self.excluded(CMA, "CMA joint statement with other regulators", link=news + "x"))
        self.assertEqual(source(CMA)["exclude_title"], g._GOVUK_EXCLUDE_TITLE)
        self.assertEqual(source(CMA)["exclude_link"], g._GOVUK_EXCLUDE_LINK)

    def test_feds_notes_are_all_kept(self):
        self.assertNotIn("exclude_title", source(FEDS))
        self.assertFalse(self.excluded(FEDS, "FEDS Note: A Short Analysis of Bond Market Liquidity", link="https://www.federalreserve.gov/econres/notes/feds-notes/x.html", categories=("FEDS Notes",)))


@pre_flip
class DateFormatTest(unittest.TestCase):
    def test_the_date_shapes_the_six_feeds_really_use_are_read_with_their_offsets(self):
        # 2026-11-05 실제 피드에서 본 모양(날짜 글자만 — 본문 아님). 읽지 못하면 72시간 검사를 건너뛰어 묵은 글감이 통과하므로 모양마다 못박는다.
        cases = {"Mon, 02 Nov 2026 07:00:00 -0500": (2026, 11, 2, 12, 0),       # FTC
                 "Fri, 30 Oct 2026 17:20:00 GMT": (2026, 10, 30, 17, 20),        # FEDS Notes
                 "2026-11-04T11:30:20+00:00": (2026, 11, 4, 11, 30),             # CMA(Atom updated)
                 "Wed, 04 Nov 2026 00:00:00 +0100": (2026, 11, 3, 23, 0),        # 집행위 R&I·EMPL
                 "Mon, 02 Nov 2026 16:07:52 -0500": (2026, 11, 2, 21, 7)}        # NSF
        for text, expected in cases.items():
            with self.subTest(text=text):
                parsed = g._parse_date(text)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed.astimezone(timezone.utc).timetuple()[:5], expected)

    def test_a_feed_item_with_one_of_those_dates_gets_a_real_age_check(self):
        for name in NEW_NAMES:
            with self.subTest(source=name):
                router = Router({SPEC[name]["url"]: feed_for(name, [good_item(name, hours=100)])})
                merged, out = fetch(SPEC[name]["lane"], router, stats={})
                self.assertEqual([m for m in merged if m["source"] == SPEC[name]["display"]], [])
                self.assertIn("AGE 1", out)


@pre_flip
class EngineWithFakeFeedsTest(unittest.TestCase):
    """실제 엔진(fetch_news_items)이 새 소스 6곳의 가짜 피드에서 후보를 만든다 — 기사 페이지·주소 해석은 부르면 실패."""

    def test_each_source_makes_a_candidate_with_its_own_notice_citation_rule_and_display_name(self):
        for name, spec in SPEC.items():
            with self.subTest(source=name):
                router = Router({spec["url"]: feed_for(name, [good_item(name)])})
                stats = {}
                merged, out = fetch(spec["lane"], router, stats=stats)
                mine = [m for m in merged if m["source"] == spec["display"]]
                self.assertEqual(len(mine), 1, out)
                item, src = mine[0], source(name)
                title, link, *_ = good_item(name)
                self.assertEqual((item["title"], item["link"], item["publisher_domain"]), (title, link, spec["host"]))
                self.assertEqual((item["notice"], item["citation"], item["prompt_rule"]), (src["notice"], src["citation"], src["prompt_rule"]))
                self.assertIsNotNone(item["published"])
                self.assertEqual(router.requested.count(spec["url"]), 1)       # 피드 한 번뿐이다
                self.assertEqual([s["drops"] for s in stats["sources"] if s["name"] == name], [{}])

    def test_one_lane_read_requests_each_of_its_sources_feed_exactly_once(self):
        for lane, expected_new in (("economy", {FTC, FEDS, CMA}), ("technology", {RTD, NSF}), ("society", {EMPL})):
            with self.subTest(lane=lane):
                router = Router()
                fetch(lane, router)
                self.assertEqual(len(router.requested), len(set(router.requested)))
                lane_urls = [s["url"] for s in g.NEWS_SOURCES if s["lane"] == lane and s["terms"]["status"] != "pending"]
                self.assertEqual(router.requested, lane_urls)
                self.assertTrue({source(n)["url"] for n in expected_new} <= set(router.requested))
                for other in NEW_NAMES:
                    if source(other)["lane"] != lane:
                        self.assertNotIn(source(other)["url"], router.requested)

    def test_the_72_hour_window_is_the_same_as_for_the_old_sources(self):
        for name, spec in SPEC.items():
            with self.subTest(source=name):
                inside = good_item(name, hours=71)
                old_title, old_link, *old_rest = good_item(name, hours=73)
                outside = (old_title + " (old)", old_link + "-old", *old_rest)
                router = Router({spec["url"]: feed_for(name, [inside, outside])})
                stats = {}
                merged, _out = fetch(spec["lane"], router, stats=stats)
                self.assertEqual([m["link"] for m in merged if m["source"] == spec["display"]], [inside[1]])
                self.assertEqual([s["drops"] for s in stats["sources"] if s["name"] == name], [{"AGE": 1}])

    def test_a_summary_under_100_characters_is_dropped_without_reading_the_article_page(self):
        for name, spec in SPEC.items():
            with self.subTest(source=name):
                router = Router({spec["url"]: feed_for(name, [good_item(name, summary_len=99)])})
                stats = {}
                merged, _out = fetch(spec["lane"], router, stats=stats)          # fetch 가 기사 페이지 읽기를 AssertionError 로 막아 둔다
                self.assertEqual([m for m in merged if m["source"] == spec["display"]], [])
                self.assertEqual([s["drops"] for s in stats["sources"] if s["name"] == name], [{"SHORT_SUMMARY": 1}])

    def test_an_item_whose_link_leaves_the_trusted_hosts_is_dropped(self):
        for name, spec in SPEC.items():
            with self.subTest(source=name):
                title, _link, published, summary, pub, tags = good_item(name)
                router = Router({spec["url"]: feed_for(name, [(title, "https://example.test/elsewhere", published, summary, pub, tags)])})
                stats = {}
                merged, _out = fetch(spec["lane"], router, stats=stats)
                self.assertEqual([m for m in merged if m["source"] == spec["display"]], [])
                # CMA 는 보도 기사 주소(www.gov.uk/government/news/)가 아니면 주소 규칙(EXCLUDED)이 먼저 거른다 — 신뢰 목록보다 엄격하다
                self.assertEqual([s["drops"] for s in stats["sources"] if s["name"] == name], [{"EXCLUDED": 1} if name == CMA else {"UNTRUSTED": 1}])

    def test_the_ftc_summary_is_cut_to_its_pinned_limit_and_the_others_to_the_default(self):
        for name, spec in SPEC.items():
            with self.subTest(source=name):
                router = Router({spec["url"]: feed_for(name, [good_item(name, summary_len=3200)])})
                merged, _out = fetch(spec["lane"], router)
                mine = [m for m in merged if m["source"] == spec["display"]]
                self.assertEqual(len(mine[0]["summary"]), spec["cap"] or g.SUMMARY_MAX_CHARS)
        # 피드 쪽에서도 같은 값이 쓰인다: 소스의 상한이 없으면 기본값(1,800), 있으면 그 값(FTC 1,500)
        item = g.parse_feed(feed_for(FTC, [good_item(FTC, summary_len=3200)]), summary_limit=source(FTC).get("summary_max_chars"))[0]
        self.assertEqual(len(item["summary"]), 1500)
        self.assertEqual(len(g.parse_feed(feed_for(FEDS, [good_item(FEDS, summary_len=3200)]))[0]["summary"]), 1800)

    def test_excluded_items_are_counted_as_excluded_and_never_become_candidates(self):
        bad = {FTC: ("FTC Seeks Public Comment on Proposed Rule Changes", "https://www.ftc.gov/news-events/news/press-releases/2026/11/x", []),
               CMA: ("CMA response to a consultation", "https://www.gov.uk/government/publications/cma-response", []),
               RTD: ("A plain headline", "https://ec.europa.eu/commission/presscorner/detail/en/ip_26_9", ["Directorate-General for Research and Innovation", "artificial intelligence"]),
               EMPL: ("A plain headline", "https://employment-social-affairs.ec.europa.eu/news/x_en", ["Cedefop", "News article"]),
               NSF: ("Podcast: A talk about new materials", "https://www.nsf.gov/news/podcast-a-talk", [])}
        for name, (title, link, tags) in bad.items():
            with self.subTest(source=name):
                spec = SPEC[name]
                _t, _l, published, summary, pub, _tags = good_item(name)
                router = Router({spec["url"]: feed_for(name, [(title, link, published, summary, pub, tags)])})
                stats = {}
                merged, _out = fetch(spec["lane"], router, stats=stats)
                self.assertEqual([m for m in merged if m["source"] == spec["display"]], [])
                self.assertEqual([s["drops"] for s in stats["sources"] if s["name"] == name], [{"EXCLUDED": 1}])

    def test_an_off_topic_research_directorate_item_is_counted_as_off_topic(self):
        spec = SPEC[RTD]
        title, link, published, summary, pub, _tags = good_item(RTD)
        router = Router({spec["url"]: rss([("Meeting of the joint committee", link, published, summary, pub,
                                            ["Directorate-General for Research and Innovation", "News article", "international cooperation"])])})
        stats = {}
        merged, _out = fetch("technology", router, stats=stats)
        self.assertEqual([m for m in merged if m["source"] == spec["display"]], [])
        self.assertEqual([s["drops"] for s in stats["sources"] if s["name"] == RTD], [{"OFF_TOPIC": 1}])

    def test_the_cma_atom_feed_keeps_news_stories_and_drops_publications_and_speeches(self):
        spec = SPEC[CMA]
        long = "Decision focuses on whether the remedies remain appropriate and continue to deliver benefits for consumers and businesses across the market."
        entries = [("CMA publishes a decision in a market review", "https://www.gov.uk/government/news/cma-publishes-a-decision", hours_ago(20), long),
                   ("Online retailers: showing the total price", "https://www.gov.uk/government/publications/online-retailers-total-price", hours_ago(30), long),
                   ("Delivering predictable regulation", "https://www.gov.uk/government/speeches/delivering-predictable-regulation", hours_ago(31), long)]
        stats = {}
        merged, _out = fetch("economy", Router({spec["url"]: atom(entries)}), stats=stats)
        self.assertEqual([m["title"] for m in merged if m["source"] == spec["display"]], ["CMA publishes a decision in a market review"])
        self.assertEqual([s["drops"] for s in stats["sources"] if s["name"] == CMA], [{"EXCLUDED": 2}])

    def test_all_requests_use_the_same_user_agent_the_engine_always_used(self):
        seen = []

        def spy(req, timeout=0):
            seen.append((req.full_url, dict(req.header_items()), timeout))
            return FakeResponse(EMPTY)

        with mock.patch.object(g.urllib.request, "urlopen", spy):
            for lane in ("economy", "technology", "society"):
                run_captured(g.fetch_news_items, lane)
        new_requests = [item for item in seen if item[0] in {source(n)["url"] for n in NEW_NAMES}]
        self.assertEqual(len(new_requests), 6)
        for _url, headers, timeout in new_requests:
            self.assertEqual(headers, {"User-agent": g.UA})
            self.assertEqual(timeout, 15)


@pre_flip
class LaneFlowWithNewSourcesTest(unittest.TestCase):
    """분야 이어가기(iter_candidate_lanes)와 후보 고르기(pick_topic_candidates)가 새 소스의 후보를 올린다 — 가짜 피드, 모델은 부르지 않는다."""

    ORDER = ["technology", "economy", "society", "science", "culture", "daily_life"]

    def feeds(self):
        feeds = {}
        for name in NEW_NAMES:
            feeds[SPEC[name]["url"]] = feed_for(name, [good_item(name, hours=5)])
        return feeds

    def run_lanes(self, feeds, order=None):
        report = {"lanes": []}
        router = Router(feeds)
        with mock.patch.object(g.urllib.request, "urlopen", router), mock.patch.object(g, "_fetch_source_excerpt", side_effect=no_page_reads), \
                mock.patch.object(g, "_resolve_article_url", side_effect=no_page_reads):
            value, out = run_captured(lambda: list(g.iter_candidate_lanes([], False, order or self.ORDER, report)))
        return value, report, out, router

    def test_the_new_sources_are_the_candidates_of_the_lanes_that_were_dry(self):
        found, report, out, router = self.run_lanes(self.feeds())
        by_lane = {lane: [c["source"] for c in cands] for lane, cands in found}
        self.assertEqual(by_lane["technology"], [SPEC[RTD]["display"], SPEC[NSF]["display"]])
        self.assertEqual(by_lane["economy"], [SPEC[FTC]["display"], SPEC[FEDS]["display"], SPEC[CMA]["display"]])
        self.assertEqual(by_lane["society"], [SPEC[EMPL]["display"]])
        self.assertEqual([lane for lane, _ in found], ["technology", "economy", "society"])      # 나머지 분야(옛 소스만 있고 피드가 빈)는 후보가 없다
        self.assertEqual(sum(len(c) for c in by_lane.values()), 6)
        lane_sources = {entry["lane"]: entry["sources"] for entry in report["lanes"]}
        self.assertEqual(lane_sources["economy"], 6)
        self.assertEqual(lane_sources["technology"], 4)
        self.assertEqual(lane_sources["society"], 3)           # UN News 는 보류라 세지 않는다
        self.assertIn("::notice::'기술·미래' 분야의 후보가 모두 탈락해 '경제·일' 분야를 이어서 시도합니다.", out)

    def test_a_dry_first_lane_falls_through_to_a_new_source_lane(self):
        # 뽑힌 첫 분야(과학·환경)에 후보가 없으면 옛 동작대로 다음 분야를 보고, 경제·일에서 FTC·FEDS 가 후보로 나온다
        found, report, out, router = self.run_lanes(self.feeds(), order=["science", "economy", "technology"])
        self.assertEqual([lane for lane, _ in found], ["economy", "technology"])
        self.assertIn("::notice::'과학·환경' 분야에 후보가 없어 '경제·일' 분야로 대체했습니다.", out)

    def test_thick_new_candidates_are_tried_before_a_thin_old_one(self):
        energy = source("European Commission · Energy")
        thin = ("Commission publishes an energy note", "https://energy.ec.europa.eu/news/a-note_en", hours_ago(2), ("energy note " * 10)[:120], "", [])
        feeds = {energy["url"]: rss([thin]), SPEC[FTC]["url"]: feed_for(FTC, [good_item(FTC)]), SPEC[FEDS]["url"]: feed_for(FEDS, [good_item(FEDS)])}
        router = Router(feeds)
        with mock.patch.object(g.urllib.request, "urlopen", router), mock.patch.object(g, "_fetch_source_excerpt", side_effect=no_page_reads), \
                mock.patch.object(g, "_resolve_article_url", side_effect=no_page_reads):
            picked, _out = run_captured(g.pick_topic_candidates, [], False, "economy", stats={})
        self.assertEqual([c["source"] for c in picked], [SPEC[FTC]["display"], SPEC[FEDS]["display"], "European Commission (DG Energy)"])

    def test_a_new_candidate_that_resembles_an_existing_title_is_dropped_as_a_duplicate(self):
        stats = {}
        router = Router(self.feeds())
        with mock.patch.object(g.urllib.request, "urlopen", router), mock.patch.object(g, "_fetch_source_excerpt", side_effect=no_page_reads), \
                mock.patch.object(g, "_resolve_article_url", side_effect=no_page_reads):
            picked, _out = run_captured(g.pick_topic_candidates, ["FTC Sues Online Seller Over Hidden Fees", "FEDS Note: A Short Analysis of Bond Market Liquidity"],
                                        False, "economy", stats=stats)
        self.assertEqual([c["source"] for c in picked], [SPEC[CMA]["display"]])
        self.assertEqual(stats["duplicates"], 2)

    def test_at_most_three_candidates_per_lane_as_before(self):
        extra = []
        for i, hours in enumerate((3, 4, 5)):
            title, link, published, summary, pub, tags = good_item(FTC, hours=hours)
            extra.append((f"{title} variant {i} about a different matter {i * 7}", f"{link}-{i}", published, summary, pub, tags))
        feeds = self.feeds()
        feeds[SPEC[FTC]["url"]] = feed_for(FTC, extra)
        router = Router(feeds)
        with mock.patch.object(g.urllib.request, "urlopen", router), mock.patch.object(g, "_fetch_source_excerpt", side_effect=no_page_reads), \
                mock.patch.object(g, "_resolve_article_url", side_effect=no_page_reads):
            picked, _out = run_captured(g.pick_topic_candidates, [], False, "economy", stats={})
        self.assertEqual(len(picked), g.MAX_ATTEMPTS)
        self.assertEqual(g.MAX_ATTEMPTS, 3)


class PostAssemblyTest(unittest.TestCase):
    """엔진이 글을 마무리할 때(add_discovery_metadata) 새 소스의 출처 이름·인용 줄·고지문이 글 끝에 붙고 머리말 엄격 검사(front_matter_problems)를 통과한다 — 표시 이름에 쉼표·괄호가 있어도."""

    def post(self, lang, link):
        body = ("이 글은 시험용 본문입니다. " * 30 if lang == "ko" else "This is a test body for the generator. " * 30) + f"\n\n[원문]({link})\n"
        return f'---\nlayout: post\ntitle: "시험 제목"\ncategory: "경제·일"\ntags: ["시험"]\nlang: {lang}\nimage: "https://example.test/i.jpg"\n---\n\n{body}'

    def test_each_source_adds_its_credit_line_and_then_its_notice_in_both_languages(self):
        for name, spec in SPEC.items():
            src = source(name)
            link = f"https://{spec['host']}/news/sample-story"
            item = {"title": "Sample story: a headline, with punctuation?", "source": spec["display"], "link": link, "publisher_domain": spec["host"], "summary": "x" * 200,
                    "published": datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc), "notice": src["notice"], "citation": src["citation"], "prompt_rule": src["prompt_rule"]}
            for lang in ("ko", "en"):
                with self.subTest(source=name, lang=lang):
                    out = g.add_discovery_metadata(self.post(lang, link), item)
                    self.assertEqual(g.front_matter_problems(out, item), [])
                    lines = out.rstrip().splitlines()
                    self.assertEqual(lines[-1], f"*{src['notice'][lang]}*")
                    self.assertEqual(lines[-2], "")
                    self.assertEqual(lines[-3], g._citation_line(src["citation"], item))
                    self.assertIn(f'source_name: "{spec["display"]}"', out)


@pre_flip
class ExistingBehaviourUnchangedTest(unittest.TestCase):
    def test_the_old_fourteen_source_definitions_are_byte_identical_to_the_state_before_this_change(self):
        old = [s for s in g.NEWS_SOURCES if s["name"] in OLD_NAMES]
        self.assertEqual([s["name"] for s in old], OLD_NAMES)
        self.assertEqual(digest(old), OLD_SOURCES_SHA256)

    def test_the_shared_constants_the_old_sources_use_keep_their_text(self):
        # 새 소스가 공유 상수를 고쳐 쓰지 않았다(고치면 위 해시도 달라지지만, 어느 상수인지 바로 보이게 따로 못박는다)
        self.assertEqual(g._EC_TERMS, {"status": "allowed", "checked": "2026-10-26", "url": "https://commission.europa.eu/legal-notice_en"})
        self.assertEqual(g._EC_EXCLUDE_LINK, r"/eurostat/|/horizon-magazine/|/commission/presscorner/")
        self.assertEqual(g._GOVUK_TERMS, {"status": "allowed", "checked": "2026-10-26", "url": "https://www.gov.uk/help/terms-conditions"})
        self.assertEqual(g._GOVUK_EXCLUDE_LINK, r"^(?!https://www\.gov\.uk/government/news/)")
        self.assertTrue(g._GOVUK_PROMPT_RULE.endswith(HEALTH))
        self.assertTrue(g._EC_PROMPT_RULE.endswith(HEALTH))

    def test_the_engine_constants_for_age_attempts_summary_thinness_and_body_length_are_unchanged(self):
        self.assertEqual(g.NEWS_MAX_AGE_HOURS, 72)
        self.assertEqual(g.MAX_ATTEMPTS, 3)
        self.assertEqual(g.SUMMARY_MAX_CHARS, 1800)
        self.assertEqual(g.THIN_EVIDENCE_CHARS, 150)
        self.assertEqual(g.MIN_BODY_CHARS, {"kr": 1000, "en": 1500})
        self.assertEqual(g.LANE_ORDER_BUCKET_MINUTES, 10)
        self.assertEqual(sorted(g.DROP_LABELS), ["AGE", "DUPLICATE", "EXCLUDED", "HOST_MISMATCH", "NOT_TECH", "NO_TITLE", "OFF_TOPIC", "SHORT_SUMMARY", "UNCHECKED",
                                                 "UNRESOLVED", "UNTRUSTED"])

    def test_the_duplicate_check_still_drops_candidates_at_a_title_similarity_of_0_6_or_more(self):
        existing = "FTC Sues Online Seller Over Hidden Fees"
        duplicates = ("FTC Sues Online Platform Over Deceptive Pricing", "FTC Sues Payment Processor Over Hidden Charges")       # 유사도 0.6 이상 0.7 미만 — 기존 글과 비슷하다
        fresh = ("FTC Sues Gym Chain Over Cancellation Rules", "FTC Sues Ticket Broker Over Resale Tactics")                      # 0.6 미만 — 새 글감이다
        for title in duplicates:
            self.assertTrue(0.6 <= g.similarity(existing, title) < 0.7, title)
        for title in fresh:
            self.assertLess(g.similarity(existing, title), 0.6, title)
        spec = SPEC[FTC]
        _title, link, _published, summary, pub, tags = good_item(FTC)
        order = (duplicates[0], fresh[0], duplicates[1], fresh[1])
        items = [(title, f"{link}-{i}", hours_ago(1 + i), summary, pub, tags) for i, title in enumerate(order)]
        stats = {}
        with mock.patch.object(g.urllib.request, "urlopen", Router({spec["url"]: feed_for(FTC, items)})), mock.patch.object(g, "_fetch_source_excerpt", side_effect=no_page_reads), \
                mock.patch.object(g, "_resolve_article_url", side_effect=no_page_reads):
            picked, _out = run_captured(g.pick_topic_candidates, [existing], False, "economy", stats=stats)
        self.assertEqual([c["title"] for c in picked], list(fresh))
        self.assertEqual(stats["duplicates"], 2)

    def old_feeds(self):
        """기존 소스 14곳의 가짜 피드: 소스마다 신선한 글감 두 건(자기 분야·호스트에서 신뢰되는 주소)."""
        feeds = {}
        for src in g.NEWS_SOURCES:
            if src["name"] not in OLD_NAMES or src["terms"]["status"] == "pending":
                continue
            host = "www.statcan.gc.ca" if src["name"].startswith("Statistics Canada") else g._host(src["url"])
            link = f"https://{host}/news/" if not host.endswith("gov.uk") else f"https://{host}/government/news/"
            summary = "A plain factual summary sentence for this old source sample. " * 8
            title_words = {"economy": "consumer prices and retail trade", "society": "population and education", "daily_life": "health reports and births",
                           "science": "climate and energy", "technology": "artificial intelligence", "culture": "social media and news"}[src["lane"]]
            feeds[src["url"]] = rss([(f"{src['name']} {title_words} release {n}", f"{link}{n}-{hashlib.md5(src['name'].encode()).hexdigest()[:6]}", hours_ago(3 + n), summary, "") for n in range(2)])
        return feeds

    def snapshot(self, sources, lane, feeds):
        router = Router(feeds)
        merged, out = fetch(lane, router, sources=sources)
        return json.dumps([{**m, "published": m["published"].isoformat()} for m in merged], sort_keys=True, ensure_ascii=False), out

    def test_with_the_new_sources_returning_nothing_every_lane_gives_exactly_the_old_result_and_log(self):
        old_only = [s for s in g.NEWS_SOURCES if s["name"] in OLD_NAMES]
        feeds = self.old_feeds()
        for lane in g.EDITORIAL_LANES:
            with self.subTest(lane=lane):
                merged_old, out_old = self.snapshot(old_only, lane, feeds)
                merged_all, out_all = self.snapshot(list(g.NEWS_SOURCES), lane, feeds)       # 새 소스의 피드는 Router 가 빈 피드로 돌려준다
                self.assertEqual(merged_all, merged_old)
                kept = [line for line in out_all.splitlines() if not any(line.startswith(f"  소스 {n}:") for n in NEW_NAMES)]
                self.assertEqual("\n".join(kept), "\n".join(out_old.splitlines()))
        # 시험 자료가 비어 있지 않다: 적어도 한 분야는 실제 후보가 나온다
        self.assertTrue(any(json.loads(self.snapshot(old_only, lane, feeds)[0]) for lane in g.EDITORIAL_LANES))

    def test_the_old_sources_come_before_the_new_ones_in_every_lane_so_their_candidate_order_cannot_change(self):
        for lane in g.EDITORIAL_LANES:
            names = [s["name"] for s in g.NEWS_SOURCES if s["lane"] == lane]
            old_part = [n for n in names if n in OLD_NAMES]
            self.assertEqual(names[:len(old_part)], old_part, lane)

    def test_new_candidates_only_follow_the_old_ones_at_each_rank(self):
        old_only = [s for s in g.NEWS_SOURCES if s["name"] in OLD_NAMES]
        feeds = {**self.old_feeds(), **{SPEC[n]["url"]: feed_for(n, [good_item(n)]) for n in NEW_NAMES}}
        for lane in ("economy", "technology", "society"):
            with self.subTest(lane=lane):
                old_titles = [m["title"] for m in json.loads(self.snapshot(old_only, lane, feeds)[0])]
                all_titles = [m["title"] for m in json.loads(self.snapshot(list(g.NEWS_SOURCES), lane, feeds)[0])]
                self.assertEqual([t for t in all_titles if t in old_titles], old_titles)         # 옛 후보의 순서는 그대로
                self.assertEqual(len(all_titles), len(old_titles) + sum(1 for n in NEW_NAMES if SPEC[n]["lane"] == lane))


class DocsTest(unittest.TestCase):
    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_the_defect_register_has_the_d88_row_after_d87_with_six_cells(self):
        text = self.read("docs/DEFECT_REGISTER.md")
        rows = [line for line in text.splitlines() if line.startswith("| **D-88** |")]
        self.assertEqual(len(rows), 1)
        self.assertLess(text.index("| **D-87** |"), text.index("| **D-88** |"))
        cells = [cell.strip() for cell in rows[0].strip().strip("|").split(" | ")]
        self.assertEqual(len(cells), 6, cells)                         # ID | 심각도 | 결함 | 근거 | 상태 | 해결 계획
        for word in ("R-119", "FTC", "FEDS", "R&I", "EMPL", "NSF", "CMA", "tests/test_generator_sources_r119a.py"):
            with self.subTest(word=word):
                self.assertIn(word, rows[0])
        self.assertIn("완화", cells[4])
        self.assertEqual(len(re.findall(r"\*\*D-88\*\*", text)), 1)

    def test_the_architecture_source_table_lists_each_new_source_in_its_lane(self):
        text = self.read("docs/ARCHITECTURE.md")
        rows = {line.split("|")[1].strip() + "|" + line.split("|")[2].strip(): line for line in text.splitlines() if line.startswith("| ") and line.count("|") >= 4}
        for lane_label, name in (("경제·일", FTC), ("경제·일", FEDS), ("경제·일", CMA), ("기술·미래", RTD), ("기술·미래", NSF), ("사회·정책", EMPL)):
            with self.subTest(source=name):
                self.assertTrue(any(key.startswith(lane_label) and name in key for key in rows), (lane_label, name))
        self.assertIn("`summary_max_chars`", text)

    def test_the_actions_guide_names_the_new_sources_in_the_lane_sentence(self):
        text = self.read("docs/ACTIONS_GUIDE.md")
        line = next(line for line in text.splitlines() if line.startswith("- 분야 하나가 비면 `[SKIP] code=LANE_EMPTY"))
        for word in ("FTC", "FEDS Notes", "CMA", "집행위 연구·혁신(R&I)", "집행위 고용·사회(EMPL)", "NSF"):
            with self.subTest(word=word):
                self.assertIn(word, line)


if __name__ == "__main__":
    unittest.main()
