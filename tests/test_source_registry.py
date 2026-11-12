"""허용 목록(Source Registry) 시험: 실제 파일의 모양과 초기 내용, 검증기의 모든 규칙(경계 시험: 규칙마다 통과·탈락 예문, 한 칸씩 UNKNOWN 으로 바꾸기),
질의 API(get·active_providers·is_url_allowed), 로더, AI 처리기 정책 11칸, 새 모듈의 위생(시각·무작위·비표준 import 없음).

네트워크·시계를 쓰지 않는다 — '오늘'은 인자로 준다. 규칙마다 문제 문장의 `[규칙번호]` 태그를 확인해, 그 규칙을 지우면 시험이 깨지게 한다(변이 증명은 audit6/src/report.md)."""
import ast
import contextlib
import copy
import dataclasses
import datetime
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from pipeline import source_registry as sr
from source_registry_helpers import GOOD_HOST, TODAY, cell, codes, good_provider, has, registry_data, with_access, with_cell

ROOT = _bootstrap.ROOT
REAL_PATH = ROOT / "pipeline" / "source_registry.json"
AI_PATH = ROOT / "pipeline" / "ai_processor_policy.json"


def real_data():
    return json.loads(REAL_PATH.read_text(encoding="utf-8"))


class RealFileTest(unittest.TestCase):
    """저장소에 들어 있는 실제 허용 목록: 감사표(2026-11-09, 69행)에서 옮긴 56 Provider 에 접근 경로별로 쪼갠 항목 6개(구조화 API 3·SWPC 서비스의 제3자 자료 3)를 더한 62 Provider 이고 전부 꺼져 있다."""

    def test_the_real_file_is_valid_with_a_date_and_only_asks_for_a_date_without_one(self):
        self.assertEqual(sr.validate_registry(real_data(), TODAY), [])
        errors = sr.validate_registry(real_data())          # 켜는 변경(T3, 패치 02) 뒤: 켜진 제공처의 만료를 확인하려면 오늘이 필요하다 — 켜진 곳 하나만 그것을 묻는다(전에는 enabled 가 없어 문제 없었다)
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith("noaa_swpc_json: [A4]"), errors)

    def test_only_the_noaa_entry_is_enabled_and_it_is_the_only_active_provider(self):
        data = real_data()
        self.assertEqual([p["provider_id"] for p in data["providers"] if p["enabled"] is not False], ["noaa_swpc_json"])    # 켜는 변경(T3, 패치 02) 뒤: 켜진 곳은 이 하나뿐(전에는 하나도 없었다)
        registry = sr.load_registry(today=TODAY)
        self.assertEqual([p.provider_id for p in registry.active_providers()], ["noaa_swpc_json"])
        self.assertEqual(registry.inactive_reasons(), {})
        self.assertEqual(registry.report_lines(), [])

    def test_initial_content_matches_the_audit_distribution(self):
        data = real_data()
        providers = data["providers"]
        self.assertEqual(len(providers), 62)
        self.assertEqual(len({p["provider_id"] for p in providers}), 62)
        tiers, status, classes = {}, {}, {}
        for p in providers:
            tiers[p["strict_tier"]] = tiers.get(p["strict_tier"], 0) + 1
            status[p["effective_status"]] = status.get(p["effective_status"], 0) + 1
            classes[p["class"]] = classes.get(p["class"], 0) + 1
        # 감사표 56곳은 tier {1: 1, 3: 41, 4: 14}·상태 {자동화 제외 29, 완전 제외 14, 참고 전용 13}·종류 {data 54, image 2} 였고, 쪼갠 새 항목 6개가 더해졌다:
        # noaa_swpc_json(Tier 1·자동화 가능 — NOAA 조사로 칸·경로·한도·출처 문구가 확인됨)·statcan_wds·uk_govuk_api(조사 전 Tier 3·자동화 제외)·swpc_f107_nrc·swpc_kyoto_dst(제3자·Tier 3·자동화 제외)·swpc_sidc_penticton_fields(Tier 3·참고 전용)
        self.assertEqual(tiers, {1: 2, 3: 46, 4: 14})
        self.assertEqual(status, {"자동화 가능": 1, "자동화 제외": 33, "완전 제외": 14, "참고 전용": 14})
        self.assertEqual(classes, {"data": 60, "image": 2})               # 이미지는 Unsplash·NASA 이미지 두 곳
        self.assertEqual({p["provider_id"] for p in providers if p["class"] == "image"}, {"unsplash", "nasa_images"})
        self.assertNotIn("google_gemini_api", {p["provider_id"] for p in providers})       # AI 처리기는 출처가 아니라 따로(ai_processor_policy.json)
        self.assertEqual(data["schema_version"], 1)

    def test_every_provider_but_the_researched_noaa_entry_is_excluded_from_automation(self):
        """실제 파일에서 enabled 를 켜 보아도(가정) 검증이 거부하지 않는 Provider 는 NOAA 조사로 값이 확인된 noaa_swpc_json 하나뿐이다 — 나머지는 유형·Tier·UNKNOWN 칸·한도·출처 문구 때문에 거부된다.
        그것도 켜는 것은 enabled 한 칸(T3 — 운영자 승인)이고 이 변경은 켜지 않았다(위 시험이 enabled 전부 false 를 못박는다)."""
        passing = []
        for p in real_data()["providers"]:
            probe = copy.deepcopy(p)
            probe["enabled"] = True
            if not sr.provider_problems(probe, TODAY):
                passing.append(p["provider_id"])
        self.assertEqual(passing, ["noaa_swpc_json"])

    def test_switching_every_real_provider_on_at_once_activates_only_the_noaa_entry_and_only_its_six_files(self):
        """P05: 62곳을 한꺼번에 enabled 로 켜도(가정) ACTIVE 는 noaa_swpc_json 하나뿐이고 허용되는 주소는 그 여섯 파일(목적 fact)뿐이다 — 켜는 것이 T3 인 이유가 시험으로 남는다."""
        data = real_data()
        for provider in data["providers"]:
            provider["enabled"] = True
        registry = sr.build_registry(data, TODAY)
        self.assertEqual([p.provider_id for p in registry.active_providers()], ["noaa_swpc_json"])
        self.assertEqual(len(registry.inactive_reasons()), 61)
        noaa_paths = set(registry.get("noaa_swpc_json").access[0].paths)
        hosts = {h for p in registry.providers() for a in p.access for h in a.hosts}
        self.assertGreater(len(hosts), 20)
        for host in sorted(hosts):
            for purpose in ("fact", "feed", "page", "resolve", "web", "article"):
                self.assertFalse(registry.is_url_allowed(f"https://{host}/", purpose)[0], (host, purpose))        # 호스트 전체(/)는 어느 목적으로도 열리지 않는다
        for path in sorted(noaa_paths):
            self.assertTrue(registry.is_url_allowed(f"https://services.swpc.noaa.gov{path}", "fact")[0], path)
            for purpose in ("feed", "page", "resolve", "web", "article", "ops_repo"):
                self.assertFalse(registry.is_url_allowed(f"https://services.swpc.noaa.gov{path}", purpose)[0], (path, purpose))
        for path in ("/json/", "/json/45-day-forecast.json", "/products/10cm-flux-30-day.json", "/json/f107_cm_flux.json", "/products/kyoto-dst.json", "/json/goes/primary/xrays-7-day.json",
                     "/json/planetary_k_index_1m.json", "/products/noaa-scales.json/../x", "/products/noaa-scales.json2", "/text/daily-geomagnetic-indices.txt"):
            self.assertFalse(registry.is_url_allowed(f"https://services.swpc.noaa.gov{path}", "fact")[0], path)    # 제3자 파일·큰 파일·예보·옛 주소 모양은 NOAA 항목의 경로가 아니다

    def test_the_pew_web_page_and_rss_are_both_excluded_and_disabled(self):
        registry = sr.load_registry(today=TODAY)
        rss, html = registry.get("pew_rss"), registry.get("pew_html")
        self.assertIsNotNone(rss)
        self.assertIsNotNone(html)
        for provider, kind in ((rss, "rss"), (html, "html")):
            self.assertEqual(provider.effective_status, "자동화 제외", provider.provider_id)
            self.assertFalse(provider.enabled, provider.provider_id)
            self.assertFalse(registry.is_active(provider.provider_id))
            self.assertEqual([a.kind for a in provider.access], [kind])
            self.assertEqual(provider.access[0].hosts, ("www.pewresearch.org",))
        allowed, reason = registry.is_url_allowed("https://www.pewresearch.org/feed/", "fact")
        self.assertFalse(allowed)
        self.assertIn("pew_rss", reason)
        self.assertNotIn(rss, registry.active_providers())

    def test_every_news_source_of_the_generator_is_known_to_the_registry_but_none_is_allowed(self):
        import generator
        registry = sr.load_registry(today=TODAY)
        known = {h for p in registry.providers() for a in p.access for h in a.hosts} | {h for p in registry.providers() for h in p.reference_hosts}
        self.assertEqual(len(generator.NEWS_SOURCES), 20)
        for src in generator.NEWS_SOURCES:
            host = generator._host(src["url"])
            self.assertIn(host, known, f"{src['name']}: 호스트 {host} 가 허용 목록에 등록돼 있지 않다")
            for purpose in ("feed", "fact", "page"):
                allowed, reason = registry.is_url_allowed(src["url"], purpose)
                self.assertFalse(allowed, f"{src['name']} {purpose}: {reason}")

    def test_the_file_carries_no_link_no_account_and_no_real_blog_name(self):
        text = REAL_PATH.read_text(encoding="utf-8") + AI_PATH.read_text(encoding="utf-8")
        self.assertNotIn("://", text)                                       # 근거는 문서 이름이고 링크가 아니다(호스트만)
        self.assertIsNone(re.search(r"ca-pub-\d|AKfyc|AIza[0-9A-Za-z_-]{20}|client_secret|refresh_token", text))
        reg = json.loads((ROOT / "pipeline" / "blogs.json").read_text(encoding="utf-8"))
        words = set()
        for blog in reg["blogs"]:                                           # 실제 블로그 식별자 — 시험에 글자로 쓰지 않고 레지스트리에서 읽는다
            host, _, rest = re.sub(r"^https?://", "", blog["url"]).partition("/")
            words.add(host.split(".")[0] if host.endswith(("github.io", "blogspot.com")) else rest.split("/")[0])     # 계정 이름(공개 주소의 앞 조각 또는 첫 경로 조각)
            words.update(re.findall(r"\(([^)]+)\)", blog["name"]))                                                # 이름의 괄호 안 식별자
            words.add(blog["name"])
        words = {w for w in words if len(w) >= 5}
        self.assertGreaterEqual(len(words), 4)                              # 시험이 실제로 식별자를 읽었는지(빈 검사로 통과하지 않게)
        for word in words:
            self.assertNotIn(word.casefold(), text.casefold(), f"실제 블로그 식별자가 허용 목록 파일에 있다: {len(word)}자")

    def test_dates_and_snapshots_of_the_real_file_are_plain_iso_dates(self):
        for p in real_data()["providers"]:
            snap = p["snapshot"]
            if snap["read_at"]:
                self.assertEqual(snap["expires_at"], (datetime.date.fromisoformat(snap["read_at"]) + datetime.timedelta(days=90)).isoformat(), p["provider_id"])
            self.assertEqual(snap["content_hash"], "", p["provider_id"])          # 해시는 빈 값 허용 — 계산 규칙(정규화)이 코드·문서에 아직 없어 정식 약관 감시(완성형)가 채운다
            if p["provider_id"] != "noaa_swpc_json":
                self.assertEqual(p["attribution_template"], "", p["provider_id"])    # 출처 문구는 NOAA 조사로 확인된 noaa_swpc_json 하나만 채웠다(나머지는 조사 전)


class ShapeRulesTest(unittest.TestCase):
    """모양 규칙 S1–S8(모든 Provider, enabled 와 상관없이)."""

    def disabled(self, **overrides):
        return good_provider(enabled=False, **overrides)

    def problems(self, provider, today=TODAY):
        return sr.validate_registry(registry_data(provider), today)

    def test_a_good_provider_has_no_problem_enabled_or_not(self):
        self.assertEqual(self.problems(good_provider()), [])
        self.assertEqual(self.problems(self.disabled()), [])

    def test_a_disabled_provider_with_unknown_cells_and_page_paths_is_fine(self):
        """실제 파일의 대부분이 이 모양이다: 꺼져 있으면 UNKNOWN·rss·html 이어도 문제가 아니다(ACTIVE 조건은 enabled 에만)."""
        provider = self.disabled(strict_tier=3, effective_status="자동화 제외")
        provider["policy"]["ai_input"] = cell("UNKNOWN", "NOT_READ", "", None)
        provider["access"] = [{"kind": "rss", "hosts": [GOOD_HOST], "paths": [], "auth": "UNKNOWN", "rate_limit": None, "robots_checked_at": None}]
        self.assertEqual(self.problems(provider), [])

    def test_s1_missing_or_mistyped_fields(self):
        for key in ("provider_id", "name", "class", "policy", "strict_tier", "effective_status", "access", "snapshot", "enabled"):
            provider = good_provider()
            del provider[key]
            self.assertTrue(has(self.problems(provider), "S1" if key != "enabled" else "S6"), key)
        for key, bad in (("provider_id", "Bad Id"), ("provider_id", "a"), ("provider_id", 7), ("name", "  "), ("strict_tier", "2"), ("strict_tier", True),
                         ("policy", []), ("access", {}), ("snapshot", None), ("attribution_template", 3), ("exceptions", "x"), ("exceptions", [1]), ("reference_hosts", "x")):
            with self.subTest(key=key, bad=bad):
                self.assertTrue(has(self.problems(good_provider(**{key: bad})), "S1"))
        self.assertTrue(has(sr.validate_registry("nope", TODAY), "S1"))
        self.assertTrue(has(sr.validate_registry({"schema_version": 2, "providers": [good_provider()]}, TODAY), "S1", "schema_version"))
        for bad_version in (True, 1.0, "1", None, 0):                               # `True`·`1.0` 은 `== 1` 이라 예전에는 통과했다(P15)
            with self.subTest(schema_version=bad_version):
                self.assertTrue(has(sr.validate_registry({"schema_version": bad_version, "providers": [good_provider()]}, TODAY), "S1", "schema_version"))
        self.assertEqual(sr.validate_registry({"_doc": "메모", "schema_version": 1, "providers": [good_provider()]}, TODAY), [])
        for key in ("provider", "Providers", "version", "extra"):                    # 칸 이름 오타가 조용히 무시되지 않는다
            with self.subTest(top_key=key):
                self.assertTrue(has(sr.validate_registry({"schema_version": 1, "providers": [good_provider()], key: []}, TODAY), "S1", "알 수 없는 칸"))
        with self.assertRaises(sr.SourceRegistryError):
            sr.build_registry({"schema_version": 1, "providers": [good_provider()], "provider": []}, TODAY)
        self.assertTrue(has(sr.validate_registry({"schema_version": 1, "providers": []}, TODAY), "S1", "providers"))
        self.assertTrue(has(sr.validate_registry({"schema_version": 1, "providers": ["x"]}, TODAY), "S1"))

    def test_s1_the_policy_needs_exactly_the_seven_cells(self):
        for name in sr.CELLS:
            provider = good_provider()
            del provider["policy"][name]
            self.assertTrue(has(self.problems(provider), "S1", name), name)
        provider = good_provider()
        provider["policy"]["bonus"] = cell()
        self.assertTrue(has(self.problems(provider), "S1", "알 수 없는 칸"))

    def test_s2_enumerations(self):
        for key, bad in (("class", "robot"), ("effective_status", "활성"), ("strict_tier", 5), ("strict_tier", -1), ("permissive_interpretation", 9), ("permissive_interpretation", True)):
            with self.subTest(key=key, bad=bad):
                self.assertTrue(has(self.problems(good_provider(**{key: bad})), "S2"))
        self.assertEqual(self.problems(good_provider(permissive_interpretation=None)), [])
        for name in sr.CELLS:
            self.assertTrue(has(self.problems(with_cell(good_provider(), name, state="MAYBE")), "S2", name, "state"), name)
            self.assertTrue(has(self.problems(with_cell(good_provider(), name, basis="GUESS")), "S2", name, "basis"), name)
        for bad in ("ftp", "rssfeed", None):
            self.assertTrue(has(self.problems(with_access(good_provider(), kind=bad)), "S2", "kind"), bad)
        for kind in sr.ACCESS_KINDS:
            self.assertFalse(has(self.problems(with_access(good_provider(enabled=False, effective_status="자동화 제외", strict_tier=3), kind=kind)), "S2"), kind)

    def test_s3_duplicate_provider_ids(self):
        problems = sr.validate_registry(registry_data(good_provider(), good_provider()), TODAY)
        self.assertTrue(has(problems, "S3", "fixture_stats"))
        self.assertEqual(sr.validate_registry(registry_data(good_provider(), good_provider(provider_id="fixture_two")), TODAY), [])

    def test_s4_hosts_and_paths(self):
        bad_hosts = ["API.Fixture.example", "https://api.fixture.example", "api.fixture.example/v1", "api.fixture.example:443", "*.fixture.example", "127.0.0.1", "fixture", "api.fixture.example.",
                     "api fixture.example", "", "-bad.example", "api.fixture.exa_mple", "한글.example"]
        for host in bad_hosts:
            with self.subTest(host=host):
                self.assertTrue(has(self.problems(with_access(good_provider(), hosts=[host])), "S4", "hosts"), host)
        self.assertTrue(has(self.problems(with_access(good_provider(), hosts=[])), "S4", "hosts"))
        self.assertTrue(has(self.problems(with_access(good_provider(), hosts="api.fixture.example")), "S4", "hosts"))
        for host in ("api.fixture.example", "a-b.c-d.example", "xn--fixture-9ya.example", "x.io"):
            self.assertFalse(has(self.problems(with_access(good_provider(), hosts=[host])), "S4"), host)
        for path in ("v1/", "/v1/../x", "/a//b", "/v1?x=1", "/v1#f", "/a b", "/%2e%2e/", "/v1/\\x", "", "/한글"):
            with self.subTest(path=path):
                self.assertTrue(has(self.problems(with_access(good_provider(), paths=[path])), "S4", "paths"), path)
        for path in ("/", "/v1/", "/n1/rss/dai-quo/0-eng.atom", "/a_b-c.d~e", "/photo-"):
            self.assertFalse(has(self.problems(with_access(good_provider(), paths=[path])), "S4"), path)
        self.assertTrue(has(self.problems(good_provider(reference_hosts=["Not A Host"])), "S4", "reference_hosts"))

    def test_s5_dates(self):
        for bad in ("2026-13-01", "2026/11/09", "20261109", "2026-11-31", "11-09-2026", "", "2026-1-9", 20261109):
            with self.subTest(bad=bad):
                self.assertTrue(has(self.problems(with_cell(good_provider(), "storage", read_at=bad)), "S5", "read_at"), bad)
                self.assertTrue(has(self.problems(with_access(good_provider(), robots_checked_at=bad)), "S5", "robots_checked_at"), bad)
                provider = good_provider()
                provider["snapshot"]["expires_at"] = bad
                self.assertTrue(has(self.problems(provider), "S5", "expires_at"), bad)
        for good in (None, "2026-02-28", "2028-02-29"):
            self.assertFalse(has(self.problems(with_cell(good_provider(), "storage", read_at=good)), "S5"), good)

    def test_s6_enabled_and_retention(self):
        for bad in ("true", 1, 0, None):
            with self.subTest(enabled=bad):
                self.assertTrue(has(self.problems(good_provider(enabled=bad)), "S6", "enabled"))
        for bad in (-1, "30", True, 1.5):
            with self.subTest(retention=bad):
                self.assertTrue(has(self.problems(good_provider(retention_days=bad)), "S6", "retention_days"))
        for good in (None, 0, 365):
            self.assertFalse(has(self.problems(good_provider(retention_days=good)), "S6"), good)

    def test_s7_the_status_can_never_be_looser_than_the_cells_and_path_types(self):
        """저장된 effective_status 가 7칸·경로 유형 계산보다 느슨하게 적힐 수 없다(자동화 가능을 꾸미지 못한다). 더 엄격하게 적는 것은 허용."""
        rss = with_access(good_provider(enabled=False), kind="rss")
        self.assertTrue(has(self.problems(rss), "S7", "자동화 가능"))
        denied = with_cell(good_provider(enabled=False), "commercial_use", state="DENIED")
        self.assertTrue(has(self.problems(denied), "S7", "완전 제외"))
        unknown = with_cell(good_provider(enabled=False), "ai_input", state="UNKNOWN", basis="NOT_READ")
        self.assertTrue(has(self.problems(unknown), "S7"))
        for stricter in ("자동화 제외", "참고 전용", "완전 제외"):
            self.assertEqual(self.problems(good_provider(enabled=False, effective_status=stricter)), [], stricter)
        self.assertEqual(self.problems(with_access(good_provider(enabled=False, effective_status="참고 전용", strict_tier=3), kind="rss")), [])

    def test_s8_evidence_and_terms_pages_carry_names_not_links(self):
        for text in ("https://agency.example/terms", "ftp://x", "see://y"):
            with self.subTest(text=text):
                self.assertTrue(has(self.problems(with_cell(good_provider(), "license", evidence=text)), "S8", "evidence"))
                provider = good_provider()
                provider["snapshot"]["terms_pages"] = [text]
                self.assertTrue(has(self.problems(provider), "S8", "terms_pages"))
        self.assertEqual(self.problems(with_cell(good_provider(), "license", evidence="Agency Open Licence v3.0")), [])


class ActiveRulesTest(unittest.TestCase):
    """ACTIVE 조건 A0–A10(enabled: true 인 Provider). 규칙마다 통과 예문과 탈락 예문."""

    def problems(self, provider, today=TODAY):
        return sr.validate_registry(registry_data(provider), today)

    def test_the_fixture_passes_every_rule(self):
        self.assertEqual(self.problems(good_provider()), [])
        self.assertEqual(sr.provider_problems(good_provider(), datetime.date(2026, 11, 9)), [])      # 오늘을 date 로 줘도 같다

    def test_a0_only_content_providers_can_be_enabled(self):
        self.assertFalse(has(self.problems(good_provider()), "A0"))
        for klass in ("internal", "ops", "image"):
            with self.subTest(klass=klass):
                self.assertTrue(has(self.problems(good_provider(**{"class": klass})), "A0", klass))

    def test_a1_tier_and_a_structured_path(self):
        for tier, ok in ((0, False), (1, False), (2, True), (3, False), (4, False)):
            with self.subTest(tier=tier):
                self.assertEqual(not has(self.problems(good_provider(strict_tier=tier)), "A1", "strict_tier"), ok)
        open_license = good_provider(strict_tier=1)
        open_license["policy"]["license"] = cell("ALLOWED", "STANDARD_LICENSE")
        self.assertEqual(self.problems(open_license), [])                          # 표준 라이선스 근거 + Tier 1 은 통과
        self.assertTrue(has(self.problems(with_cell(good_provider(strict_tier=1), "license", basis="EXPLICIT")), "A1", "낮게"))    # 공개 라이선스 근거가 없는데 Tier 1 로 적으면 거부
        for kinds in ([], ["rss"], ["html"], ["image"], ["rss", "html"]):
            with self.subTest(kinds=kinds):
                provider = good_provider()
                provider["access"] = [dict(provider["access"][0], kind=k) for k in kinds]
                self.assertTrue(has(self.problems(provider), "A1", "구조화 접근 경로"))
        for kind in ("api", "csv", "dataset"):
            self.assertFalse(has(self.problems(with_access(good_provider(), kind=kind)), "A1"), kind)

    def test_a2_each_cell_must_be_known_and_directly_evidenced(self):
        for name in sr.CELLS:
            with self.subTest(cell=name):
                self.assertTrue(has(self.problems(with_cell(good_provider(), name, state="UNKNOWN")), "A2", name), "UNKNOWN")
                for basis in ("IMPLIED", "NOT_ADDRESSED", "NOT_READ"):
                    self.assertTrue(has(self.problems(with_cell(good_provider(), name, basis=basis)), "A2", name), basis)
                for basis in ("EXPLICIT", "STANDARD_LICENSE", "STATUTE"):
                    for state in ("ALLOWED", "CONDITIONAL"):
                        self.assertFalse(has(self.problems(with_cell(good_provider(), name, state=state, basis=basis)), "A2"), f"{state}/{basis}")

    def test_a3_a_denied_cell_blocks_and_commercial_or_automated_denial_is_named_tier_four(self):
        for name in sr.CELLS:
            with self.subTest(cell=name):
                problems = self.problems(with_cell(good_provider(), name, state="DENIED"))
                self.assertTrue(has(problems, "A3", name))
                self.assertEqual(has(problems, "A3", name, "Tier 4"), name in ("commercial_use", "automated_access"))
        self.assertFalse(has(self.problems(good_provider()), "A3"))

    def test_a4_the_snapshot_must_not_be_expired_and_today_must_be_given(self):
        provider = good_provider()
        provider["snapshot"]["expires_at"] = TODAY
        self.assertFalse(has(self.problems(provider), "A4"))                      # 기한 당일은 아직 유효
        self.assertTrue(has(self.problems(provider, "2026-11-10"), "A4", "지났"))   # 하루 지나면 만료
        self.assertTrue(has(self.problems(provider, datetime.date(2026, 11, 10)), "A4"))
        self.assertFalse(has(self.problems(provider, "2026-11-08"), "A4"))
        self.assertTrue(has(self.problems(good_provider(), None), "A4", "today"))       # 오늘을 못 받으면 확인할 수 없어 거부
        gone = good_provider()
        gone["snapshot"]["expires_at"] = None
        self.assertTrue(has(self.problems(gone), "A4", "expires_at"))
        with self.assertRaises(sr.SourceRegistryError):
            sr.validate_registry(registry_data(), "not-a-date")
        with self.assertRaises(sr.SourceRegistryError):
            sr.validate_registry(registry_data(), 20261109)

    def test_a5_conditional_attribution_needs_a_template(self):
        for state, template, flagged in (("CONDITIONAL", "", True), ("CONDITIONAL", "   ", True), ("CONDITIONAL", "Source: X", False), ("ALLOWED", "", False)):
            with self.subTest(state=state, template=template):
                provider = with_cell(good_provider(attribution_template=template), "attribution", state=state)
                self.assertEqual(has(self.problems(provider), "A5"), flagged)
        missing = good_provider()
        del missing["attribution_template"]
        self.assertTrue(has(self.problems(with_cell(missing, "attribution", state="CONDITIONAL")), "A5"))

    def test_a6_page_feed_and_image_paths_are_excluded_by_type(self):
        for kind in ("rss", "html", "image"):
            with self.subTest(kind=kind):
                self.assertTrue(has(self.problems(with_access(good_provider(strict_tier=2), kind=kind)), "A6", kind))
        mixed = good_provider()
        mixed["access"].append(dict(mixed["access"][0], kind="rss"))
        problems = self.problems(mixed)
        self.assertTrue(has(problems, "A6", "rss"))
        self.assertFalse(has(problems, "A1", "구조화 접근 경로"))                    # 구조화 경로는 있다 — 그래도 한 경로라도 rss 면 Provider 를 켤 수 없다(경로를 나눠 판정)
        self.assertTrue(has(self.problems(good_provider(**{"class": "image"})), "A6", "image"))
        for kind in ("api", "csv", "dataset"):
            self.assertFalse(has(self.problems(with_access(good_provider(), kind=kind)), "A6"), kind)

    def test_a7_tier_four_conditions_are_complete_exclusion(self):
        for name, expect in (("commercial_use", True), ("automated_access", True), ("derivative_use", True), ("ai_input", True), ("storage", False), ("attribution", False),
                             ("license", False)):
            with self.subTest(cell=name):
                self.assertEqual(has(self.problems(with_cell(good_provider(), name, state="DENIED")), "A7"), expect)
        self.assertTrue(has(self.problems(good_provider(strict_tier=4)), "A7"))
        self.assertFalse(has(self.problems(good_provider()), "A7"))

    def test_a8_every_cell_and_the_terms_need_evidence_names_and_dates(self):
        for name in sr.CELLS:
            with self.subTest(cell=name):
                self.assertTrue(has(self.problems(with_cell(good_provider(), name, evidence="")), "A8", name))
                self.assertTrue(has(self.problems(with_cell(good_provider(), name, evidence="   ")), "A8", name))
                self.assertTrue(has(self.problems(with_cell(good_provider(), name, read_at=None)), "A8", name))
        provider = good_provider()
        provider["snapshot"]["terms_pages"] = []
        self.assertTrue(has(self.problems(provider), "A8", "terms_pages"))
        for pages, flagged in (([""], True), (["  "], True), (["\t"], True), (["", "  "], True), (["", "Fixture API Terms"], False), (["Fixture API Terms"], False)):
            with self.subTest(pages=pages):                                          # 빈 이름·공백 이름만 든 목록은 '읽은 약관 문서'가 아니다(P04)
                provider = good_provider()
                provider["snapshot"]["terms_pages"] = pages
                self.assertEqual(has(self.problems(provider), "A8", "terms_pages"), flagged)
        for pages in ([None], [1], [None, "Fixture API Terms"], "Fixture API Terms"):    # 문자열이 아닌 항목은 모양(S1) 단계에서 걸려 Provider 가 만들어지지도 않는다
            with self.subTest(pages=pages):
                provider = good_provider()
                provider["snapshot"]["terms_pages"] = pages
                self.assertTrue(has(self.problems(provider), "S1", "terms_pages"))
                self.assertEqual(sr.build_registry(registry_data(provider), TODAY).active_providers(), [])

    def test_a9_the_status_must_say_automation_is_possible(self):
        for status in ("자동화 제외", "참고 전용", "완전 제외"):
            with self.subTest(status=status):
                self.assertTrue(has(self.problems(good_provider(effective_status=status)), "A9", status))
        self.assertFalse(has(self.problems(good_provider()), "A9"))

    def test_a10_an_active_access_path_needs_path_prefixes(self):
        """P05: 호스트 전체를 여는 접근 경로(paths 가 빈 것)는 켤 수 없다 — ACTIVE 는 실제로 쓰는 경로 접두어를 적어야 한다(꺼져 있으면 상관없다)."""
        self.assertFalse(has(self.problems(good_provider()), "A10"))
        for paths in ([], None):
            with self.subTest(paths=paths):
                provider = good_provider()
                if paths is None:
                    del provider["access"][0]["paths"]
                else:
                    provider["access"][0]["paths"] = paths
                self.assertTrue(has(self.problems(provider), "A10", "access[0]"))
        second = good_provider()
        second["access"].append(dict(second["access"][0], paths=[]))
        self.assertTrue(has(self.problems(second), "A10", "access[1]"))
        self.assertFalse(has(self.problems(second), "A10", "access[0]"))
        self.assertFalse(has(self.problems(with_access(good_provider(enabled=False), paths=[])), "A10"))     # 꺼져 있으면 ACTIVE 규칙은 적용하지 않는다
        registry = sr.build_registry(registry_data(with_access(good_provider(), paths=[])), TODAY)
        self.assertEqual(registry.active_providers(), [])
        self.assertFalse(registry.is_url_allowed(f"https://{GOOD_HOST}/anything", "fact")[0])

    def test_a1_names_a_computed_tier_above_two_even_when_other_rules_fire_too(self):
        """P17(N20): 저장된 strict_tier 가 2 로 적혀 있어도 7칸 계산이 3·4 이면 A1 이 문제 목록에 들어 있다 — A2·A3 이 같이 나와도 A1 이 빠지지 않는다."""
        for sample, tier in ((with_cell(good_provider(), "storage", state="UNKNOWN", basis="NOT_READ"), 3), (with_cell(good_provider(), "storage", state="DENIED"), 3),
                             (with_cell(good_provider(), "commercial_use", state="DENIED"), 4), (with_cell(good_provider(), "ai_input", state="DENIED"), 4),
                             (with_cell(good_provider(), "license", basis="IMPLIED"), 3)):
            with self.subTest(tier=tier):
                self.assertEqual(sample["strict_tier"], 2)
                self.assertTrue(has(self.problems(sample), "A1", f"7칸 계산 {tier}"), tier)

    def test_a_disabled_provider_is_never_judged_by_the_active_rules(self):
        broken = with_cell(good_provider(enabled=False, effective_status="자동화 제외"), "ai_input", state="UNKNOWN", basis="NOT_READ")
        broken["snapshot"]["expires_at"] = "2020-01-01"
        self.assertEqual(self.problems(broken), [])
        broken["enabled"] = True
        self.assertTrue(codes(self.problems(broken)) >= {"A2", "A4", "A9"})

    def test_each_rule_has_its_own_tag_so_a_removed_rule_is_noticed(self):
        """모든 ACTIVE 규칙 태그가 실제로 어떤 입력에서 나온다(규칙 코드를 지우면 이 집합이 줄어 시험이 깨진다)."""
        seen = set()
        samples = [good_provider(**{"class": "ops"}), good_provider(strict_tier=3), with_cell(good_provider(), "storage", state="UNKNOWN"),
                   with_cell(good_provider(), "commercial_use", state="DENIED"), good_provider(effective_status="참고 전용"),
                   with_cell(good_provider(attribution_template=""), "attribution", state="CONDITIONAL"), with_access(good_provider(), kind="rss"),
                   with_cell(good_provider(), "ai_input", state="DENIED"), with_cell(good_provider(), "license", evidence=""), with_access(good_provider(), paths=[])]
        for sample in samples:
            seen |= codes(sr.validate_registry(registry_data(sample), TODAY))
        seen |= codes(sr.validate_registry(registry_data(good_provider()), None))
        self.assertTrue({f"A{n}" for n in range(11)} <= seen, sorted(seen))


class TierAndStatusTest(unittest.TestCase):
    def cells(self, **states):
        out = {name: {"state": "ALLOWED", "basis": "EXPLICIT"} for name in sr.CELLS}
        for name, value in states.items():
            state, _, basis = value.partition("/")
            out[name] = {"state": state, "basis": basis or "EXPLICIT"}
        return out

    def test_computed_tier_table(self):
        table = [
            ({}, 2),
            ({"license": "ALLOWED/STANDARD_LICENSE"}, 1),
            ({"storage": "ALLOWED/STATUTE"}, 1),
            ({"attribution": "ALLOWED/STANDARD_LICENSE"}, 2),         # 출처 표시 칸의 공개 라이선스 근거는 Tier 1 조건이 아니다(라이선스·상업·가공·저장 네 칸만)
            ({"ai_input": "UNKNOWN/NOT_READ"}, 3),
            ({"ai_input": "ALLOWED/IMPLIED"}, 3),
            ({"automated_access": "CONDITIONAL/NOT_ADDRESSED"}, 3),
            ({"storage": "DENIED"}, 3),
            ({"attribution": "DENIED"}, 3),
            ({"license": "DENIED"}, 3),
            ({"commercial_use": "DENIED"}, 4),
            ({"automated_access": "DENIED"}, 4),
            ({"derivative_use": "DENIED"}, 4),
            ({"ai_input": "DENIED"}, 4),
            ({"commercial_use": "DENIED", "storage": "UNKNOWN/NOT_READ"}, 4),
        ]
        for states, expected in table:
            with self.subTest(states=states):
                self.assertEqual(sr.computed_strict_tier(self.cells(**states)), expected)
        self.assertEqual(sr.computed_strict_tier(self.cells(commercial_use="DENIED"), "internal"), 0)

    def test_computed_status_table(self):
        for klass, tier, kinds, expected in (
                ("data", 4, ["api"], "완전 제외"), ("data", 2, ["api"], "자동화 가능"), ("data", 1, ["api", "csv", "dataset"], "자동화 가능"),
                ("data", 1, ["rss"], "자동화 제외"), ("data", 2, ["api", "rss"], "자동화 제외"), ("data", 2, [], "자동화 제외"), ("data", 3, ["api"], "자동화 제외"),
                ("data", 3, [], "참고 전용"), ("image", 1, ["image"], "자동화 제외"), ("image", 4, ["api"], "완전 제외"), ("ops", 2, ["api"], "자동화 제외")):
            with self.subTest(klass=klass, tier=tier, kinds=kinds):
                self.assertEqual(sr.computed_status(klass, tier, kinds), expected)

    def test_cell_known_property(self):
        self.assertTrue(sr.Cell("ALLOWED", "EXPLICIT", "x", None).known)
        self.assertTrue(sr.Cell("CONDITIONAL", "STATUTE", "x", None).known)
        self.assertFalse(sr.Cell("UNKNOWN", "EXPLICIT", "x", None).known)
        self.assertFalse(sr.Cell("ALLOWED", "IMPLIED", "x", None).known)


class UrlSplitTest(unittest.TestCase):
    """split_https_url 과 path_matches — 관문의 첫 방어선."""

    def accepted(self, url):
        host, path, reason = sr.split_https_url(url)
        self.assertIsNone(reason, f"{url[:60]!r}: {reason}")
        return host, path

    def rejected(self, url):
        host, path, reason = sr.split_https_url(url)
        self.assertIsNotNone(reason, f"{str(url)[:60]!r} 가 통과했다")
        for secret in ("SECRET", "token", "frag"):
            self.assertNotIn(secret, reason)                      # 거부 사유에는 주소의 어떤 부분도 넣지 않는다
        return reason

    def test_accepts_plain_https_urls_and_normalizes_case(self):
        self.assertEqual(self.accepted("https://api.fixture-stats.example/v1/data?x=1#f"), (GOOD_HOST, "/v1/data"))
        self.assertEqual(self.accepted("HTTPS://API.Fixture-Stats.EXAMPLE/v1/"), (GOOD_HOST, "/v1/"))
        self.assertEqual(self.accepted("https://api.fixture-stats.example"), (GOOD_HOST, "/"))
        self.assertEqual(self.accepted("https://api.fixture-stats.example:443/v1/"), (GOOD_HOST, "/v1/"))
        self.assertEqual(self.accepted("https://a.example/%7Euser/a%20b"), ("a.example", "/%7Euser/a%20b"))
        self.assertEqual(self.accepted("https://a.example/%ED%95%9C%EA%B8%80/x"), ("a.example", "/%ED%95%9C%EA%B8%80/x"))        # 올바른 UTF-8 퍼센트 인코딩(한글)은 허용

    def test_rejects_the_classic_parser_differential_tricks(self):
        bad = [None, "", b"https://a.example/", 123, ["https://a.example/"], "a.example/v1/", "//a.example/v1/", "/v1/", "http://a.example/v1/", "ftp://a.example/", "javascript:alert(1)",
               "https://user@a.example/", "https://a.example@evil.example/", "https://a.example\\@evil.example/", "https://a.example:8443/v1/", "https://a.example:abc/", "https://a.example:/x",
               "https://127.0.0.1/v1/", "https://[::1]/v1/", "https://2130706433/", "https://0x7f.0.0.1/", "https://a.example./v1/", "https://exa mple.com/", "https://a.example/v1/\n",
               "https://a.example/v1/\t", "https://a.example/\x00", "https://a.example/\x7f", "https://a.example/<x>", "https://a.example/\"x\"", "https://a.example/`x`", "https://a.example/{x}",
               "https://a.example/a|b", "https://a.example/^", "https://е-example.com/", "https://a.example/한글", "https://a.example//v1/", "https://a.example/v1//x",
               "https://a.example/v1/%C0%AE%C0%AE/x", "https://a.example/v1/%C1%9C", "https://a.example/v1/%FF", "https://a.example/v1/%E0%80%AE",      # 과잉 길이 UTF-8 로 쓴 `.`·`\` 같은 우회
               "https://a.example/v1/../admin", "https://a.example/v1/./x", "https://a.example/v1/%2e%2e/admin", "https://a.example/v1/%2E/x", "https://a.example/v1/%2fadmin",
               "https://a.example/v1/%5cadmin", "https://a.example/v1/a%00b", "https://a.example/v1/%zz", "https://a.example/v1/%", "https://.example/", "https://-a.example/", "https://a_b.example/",
               "https://localhost/", "https://a/", "https://a.example/" + "x" * 2100]
        for url in bad:
            with self.subTest(url=str(url)[:50]):
                self.rejected(url)

    def test_semicolon_parameters_cannot_hide_dot_segments_and_double_encoding_is_refused(self):
        """P06: 서버가 `;` 뒤를 떼고 읽는 `..;` 와, 한 번 더 디코딩되면 `..` 이 되는 `%252e` 같은 이중 인코딩."""
        for tail in ("/v1/..;/x", "/v1/.;/x", "/v1/..;x=1/y", "/v1/%2e%2e;/x", "/v1/%2e%2e%3b/x", "/v1/%2E%2E%3B/x", "/v1/%252e%252e/x", "/v1/%252E/x", "/v1/%25/x",
                     "/v1/a%2525b", "/v1/x/..;", "/v1/%2e%2e/x", "/v1/./x", "/v1//x"):
            with self.subTest(tail=tail):
                self.rejected("https://a.example" + tail)
        for tail in ("/v1/a;b=1/x", "/v1/;x/y", "/v1/a;..", "/v1/..a;/x", "/v1/x;.;/y", "/v1/%7Euser", "/v1/a.b/x"):
            with self.subTest(tail=tail):
                self.accepted("https://a.example" + tail)

    def test_the_query_and_fragment_may_carry_characters_that_cannot_change_host_or_path(self):
        """질의·조각의 꺾쇠·따옴표·중괄호·세로선은 호스트·경로를 바꾸지 못해 허용한다(실제 API 주소에 쓰인다). 같은 글자가 경로에 있으면 거부(위 시험)."""
        for url in ("https://a.example/v1/?q=a|b", "https://a.example/v1/?filter={x}&y=<z>", "https://a.example/v1/?q=\"x\"&k='y'", "https://a.example/v1/#frag|{x}", "https://a.example?x=^`",
                    "https://a.example/v1/?next=https://evil.example/"):
            host, path = self.accepted(url)
            self.assertEqual(host, "a.example", url)
        for url in ("https://a.example/v1/?q=a b", "https://a.example/v1/?q=a\\b", "https://a.example/v1/?q=한글", "https://a.example/v1/#a\tb", "https://a.example/v1/?q=\x00",
                    "https://a.example/v1/?q=\x7f", "https://a.example/v1/#\\@evil.example"):
            self.rejected(url)
        for url in ("https://a.example/v1/{x}?q=1", "https://a.example/v1/a|b?q=1", "https://a.example/<x>#f", "https://a.example/\"x\"?q=1"):
            self.rejected(url)                                                      # 같은 글자라도 경로(질의 앞)에 있으면 거부

    def test_the_reason_never_contains_query_token_or_path(self):
        for url in ("http://a.example/private-name?token=SECRET#frag", "https://u:SECRET@a.example/p?token=SECRET", "https://a.example/%2e%2e/private-name?token=SECRET#frag"):
            reason = self.rejected(url)
            self.assertNotIn("private-name", reason)

    def test_path_matching_respects_segment_boundaries(self):
        cases = [("/v1/x", ("/v1/",), True), ("/v1", ("/v1/",), True), ("/v10/x", ("/v1/",), False), ("/V1/x", ("/v1/",), False), ("/feed", ("/feed",), True),
                 ("/feed/x", ("/feed",), True), ("/feedback", ("/feed",), False), ("/", (), True), ("/anything", (), True), ("/a", ("/b/", "/a"), True), ("/n1/rss/x.atom", ("/n1/rss/x.atom",), True),
                 ("/n1/rss/x.atom.evil", ("/n1/rss/x.atom",), False)]
        for path, prefixes, expected in cases:
            with self.subTest(path=path, prefixes=prefixes):
                self.assertEqual(sr.path_matches(path, prefixes), expected)


class RegistryApiTest(unittest.TestCase):
    """load_registry·Registry: get·active_providers·is_url_allowed·inactive_reasons — FACT 와의 인터페이스 약속."""

    def build(self, *providers, today=TODAY):
        return sr.build_registry(registry_data(*providers), today)

    def test_active_and_inactive_providers(self):
        down = with_cell(good_provider(provider_id="fixture_unknown"), "ai_input", state="UNKNOWN", basis="NOT_READ")
        off = good_provider(provider_id="fixture_off", enabled=False)
        registry = self.build(good_provider(), down, off)
        self.assertEqual([p.provider_id for p in registry.active_providers()], ["fixture_stats"])
        self.assertTrue(registry.is_active("fixture_stats"))
        for pid in ("fixture_unknown", "fixture_off", "nope"):
            self.assertFalse(registry.is_active(pid), pid)
        self.assertIsNone(registry.get("nope"))
        self.assertIsNotNone(registry.get("fixture_off"))                          # 꺼져 있어도 get 은 Provider 를 준다(Pew 시험이 쓴다)
        self.assertEqual(sorted(registry.inactive_reasons()), ["fixture_unknown"])    # enabled 인데 ACTIVE 가 못 된 것만 사유를 남긴다
        lines = registry.report_lines()
        self.assertTrue(lines and all("fixture_unknown" in line and "ACTIVE" in line for line in lines))
        self.assertTrue(any("[A2]" in line and "ai_input" in line for line in lines))

    def test_provider_fields_are_the_interface_promised_to_the_fact_path(self):
        provider = self.build().get("fixture_stats")
        for field in ("provider_id", "strict_tier", "effective_status", "access", "attribution_template", "snapshot", "policy", "retention_days"):
            self.assertTrue(hasattr(provider, field), field)
        self.assertEqual((provider.provider_id, provider.strict_tier, provider.effective_status, provider.retention_days, provider.attribution_template),
                         ("fixture_stats", 2, "자동화 가능", 30, "Source: Fixture Agency"))
        self.assertEqual((provider.access[0].kind, provider.access[0].hosts, provider.access[0].paths), ("api", (GOOD_HOST,), ("/v1/",)))
        self.assertEqual(provider.policy.ai_input.state, "ALLOWED")
        self.assertEqual(provider.policy["ai_input"], provider.policy.ai_input)
        self.assertEqual([name for name, _ in provider.policy.items()], list(sr.CELLS))
        self.assertEqual(provider.snapshot.expires_at, "2027-02-07")
        self.assertEqual(provider.snapshot.terms_pages, ("Fixture API Terms",))
        with self.assertRaises(KeyError):
            provider.policy["bonus"]

    def test_providers_are_read_only(self):
        registry = self.build()
        provider = registry.get("fixture_stats")
        for obj, attr in ((provider, "strict_tier"), (provider, "enabled"), (provider.policy, "ai_input"), (provider.policy.ai_input, "state"), (provider.access[0], "kind"),
                          (provider.snapshot, "expires_at")):
            with self.subTest(attr=attr), self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(obj, attr, 0)
        self.assertIsInstance(provider.access, tuple)
        self.assertIsInstance(provider.access[0].hosts, tuple)
        self.assertIsInstance(provider.exceptions, tuple)
        listing = registry.active_providers()
        listing.clear()                                                            # 돌려준 목록을 고쳐도 Registry 는 그대로
        self.assertEqual(len(registry.active_providers()), 1)
        self.assertIsInstance(registry.providers(), tuple)

    def test_url_allowed_only_for_registered_host_and_path_of_an_active_provider(self):
        registry = self.build()
        for url in (f"https://{GOOD_HOST}/v1/series?id=1", f"https://{GOOD_HOST}/v1", f"https://{GOOD_HOST}:443/v1/x", f"HTTPS://{GOOD_HOST.upper()}/v1/x"):
            allowed, reason = registry.is_url_allowed(url, "fact")
            self.assertTrue(allowed, (url, reason))
            self.assertIn("fixture_stats", reason)
        for url in (f"https://{GOOD_HOST}/v2/x", f"https://{GOOD_HOST}/v10/", f"https://{GOOD_HOST}/V1/x", f"https://{GOOD_HOST}/", f"http://{GOOD_HOST}/v1/x", f"https://{GOOD_HOST}:8443/v1/x",
                    f"https://{GOOD_HOST}@evil.example/v1/", f"https://evil.example@{GOOD_HOST}/v1/", f"https://{GOOD_HOST}./v1/", f"https://x.{GOOD_HOST}/v1/", f"https://{GOOD_HOST}.evil.example/v1/",
                    f"https://{GOOD_HOST}/v1/../v2/", f"https://{GOOD_HOST}/v1/%2e%2e/x", f"https://{GOOD_HOST}//v1/", "https://evil.example/v1/", f"https://{GOOD_HOST}\\@evil.example/v1/"):
            allowed, reason = registry.is_url_allowed(url, "fact")
            self.assertFalse(allowed, (url, reason))
            self.assertTrue(reason)
        for bad in (None, 5, b"x", ""):
            self.assertFalse(registry.is_url_allowed(bad, "fact")[0])

    def test_purpose_must_be_well_formed_and_general_web_reading_is_never_allowed(self):
        registry = self.build()
        url = f"https://{GOOD_HOST}/v1/x"
        self.assertTrue(registry.is_url_allowed(url, "fact")[0])
        for purpose in ("ai_input", "terms", "store", "a", "a" * 32, "web", "html", "rss", "crawl", "fetch", "read", "article", "excerpt", "news", "summary", "feeds", "f", "ops", "facts"):
            allowed, reason = registry.is_url_allowed(url, purpose)                # P05: 허용 목적(fact)이 아니면 모양이 맞아도 거부한다 — 허용 목록 방식(모르는 목적은 거부)
            self.assertFalse(allowed, purpose)
            self.assertIn("허용 목적", reason)
        for purpose in ("", "Fact", "fact!", "fact data", "1fact", "_x", "a" * 33, None, 7, b"fact", "한글"):
            allowed, reason = registry.is_url_allowed(url, purpose)
            self.assertFalse(allowed, purpose)
            self.assertIn("purpose", reason)
        for purpose in sorted(sr.GENERAL_WEB_PURPOSES):
            allowed, reason = registry.is_url_allowed(url, purpose)                # 허용 목록에 있는 호스트·경로여도 feed·page·resolve 는 유형만으로 Tier 3
            self.assertFalse(allowed, purpose)
            self.assertIn("Tier 3", reason)
        self.assertEqual(sr.GENERAL_WEB_PURPOSES, frozenset({"feed", "page", "resolve"}))
        self.assertEqual(sr.ALLOWED_PURPOSES, frozenset({"fact"}))
        self.assertTrue(sr.GENERAL_WEB_PURPOSES.isdisjoint(sr.ALLOWED_PURPOSES))

    def test_reasons_name_the_host_and_provider_but_never_the_path_query_or_token(self):
        registry = self.build(good_provider(), good_provider(provider_id="fixture_off", enabled=False, access=[{"kind": "api", "hosts": ["off.fixture.example"], "paths": ["/p/"]}]))
        urls = [f"https://{GOOD_HOST}/v1/private-name?token=SECRET&key=1#frag", f"https://{GOOD_HOST}/v9/private-name?token=SECRET#frag", "https://off.fixture.example/p/private-name?token=SECRET#frag",
                "https://unknown.example/private-name?token=SECRET#frag", f"http://{GOOD_HOST}/v1/private-name?token=SECRET#frag", f"https://{GOOD_HOST}/v1/private-name?token=SECRET#frag"]
        for purpose in ("fact", "feed"):
            for url in urls:
                _, reason = registry.is_url_allowed(url, purpose)
                for leaked in ("private-name", "SECRET", "token", "frag", "key=1"):
                    self.assertNotIn(leaked, reason, (purpose, url[:40]))

    def test_inactive_reasons_explain_why(self):
        off = good_provider(provider_id="fixture_off", enabled=False, effective_status="자동화 제외", strict_tier=3)
        off["access"] = [{"kind": "api", "hosts": ["off.fixture.example"], "paths": [], "auth": "KEY"}]
        expired = good_provider(provider_id="fixture_expired", access=[{"kind": "api", "hosts": ["old.fixture.example"], "paths": [], "auth": "KEY"}])
        expired["snapshot"]["expires_at"] = "2026-01-01"
        registry = self.build(good_provider(), off, expired)
        allowed, reason = registry.is_url_allowed("https://off.fixture.example/x", "fact")
        self.assertEqual(allowed, False)
        self.assertIn("fixture_off", reason)
        self.assertIn("비활성", reason)
        allowed, reason = registry.is_url_allowed("https://old.fixture.example/x", "fact")
        self.assertFalse(allowed)
        self.assertIn("fixture_expired", reason)
        self.assertIn("[A4]", reason)
        allowed, reason = registry.is_url_allowed("https://unknown.example/x", "fact")
        self.assertFalse(allowed)
        self.assertIn("허용 목록(Registry)에 없음", reason)
        allowed, reason = registry.is_url_allowed(f"https://{GOOD_HOST}/other/x", "fact")
        self.assertFalse(allowed)
        self.assertIn("등록된 접근 경로가 아님", reason)

    def test_reference_hosts_are_known_for_explanations_but_never_allowed(self):
        provider = good_provider(provider_id="fixture_ref", enabled=False, effective_status="참고 전용", strict_tier=3, access=[], reference_hosts=["cited.fixture.example"])
        registry = self.build(provider)
        allowed, reason = registry.is_url_allowed("https://cited.fixture.example/page", "fact")
        self.assertFalse(allowed)
        self.assertIn("fixture_ref", reason)
        self.assertIn("참고", reason)                                               # 자동 접근 경로가 없는 참고 호스트라고 알린다

    def test_without_today_nothing_enabled_becomes_active(self):
        registry = sr.build_registry(registry_data(good_provider()), None)
        self.assertEqual(registry.active_providers(), [])
        self.assertTrue(any("[A4]" in line for line in registry.report_lines()))
        self.assertFalse(registry.is_url_allowed(f"https://{GOOD_HOST}/v1/x", "fact")[0])
        for today in (TODAY, datetime.date(2026, 11, 9), datetime.datetime(2026, 11, 9, 12, 0)):
            self.assertEqual(len(sr.build_registry(registry_data(good_provider()), today).active_providers()), 1, today)
        expired = sr.build_registry(registry_data(good_provider()), "2027-02-08")
        self.assertEqual(expired.active_providers(), [])
        self.assertFalse(expired.is_url_allowed(f"https://{GOOD_HOST}/v1/x", "fact")[0])

    def test_a_provider_with_a_broken_shape_is_left_out_with_its_reasons(self):
        broken = good_provider(provider_id="fixture_broken")
        del broken["policy"]
        registry = self.build(good_provider(), broken)
        self.assertIsNone(registry.get("fixture_broken"))
        self.assertEqual([p.provider_id for p in registry.active_providers()], ["fixture_stats"])
        self.assertIn("fixture_broken", registry.inactive_reasons())
        self.assertTrue(any("[S1]" in line for line in registry.report_lines()))
        unnamed = sr.build_registry({"schema_version": 1, "providers": [good_provider(), {"nonsense": True}]}, TODAY)
        self.assertIn("providers[1]", unnamed.inactive_reasons())

    def test_report_lines_tell_a_broken_shape_apart_from_an_enabled_provider_that_misses_a_rule(self):
        """P15: 모양이 틀려 목록에서 빠진 항목은 enabled 가 아니어도 사유가 남는데, 그 줄이 '이 Provider 는 enabled 인데'라고 거짓으로 말하지 않는다."""
        broken_off = good_provider(provider_id="fixture_broken_off", enabled=False)
        del broken_off["policy"]
        broken_on = good_provider(provider_id="fixture_broken_on")
        del broken_on["policy"]
        down = with_cell(good_provider(provider_id="fixture_down"), "ai_input", state="UNKNOWN", basis="NOT_READ")
        registry = self.build(good_provider(), broken_off, broken_on, down)
        lines = registry.report_lines()
        for pid in ("fixture_broken_off", "fixture_broken_on"):
            mine = [line for line in lines if f" {pid} " in line]
            self.assertTrue(mine, pid)
            for line in mine:
                self.assertIn("모양이 올바르지 않아 목록에서 빠짐", line)
                self.assertNotIn("enabled 이지만", line)
        mine = [line for line in lines if " fixture_down " in line]
        self.assertTrue(mine)
        for line in mine:
            self.assertIn("enabled 이지만 ACTIVE 가 아님", line)
            self.assertNotIn("빠짐", line)
        self.assertEqual(sorted(registry.inactive_reasons()), ["fixture_broken_off", "fixture_broken_on", "fixture_down"])

    def test_an_unusable_file_raises_instead_of_falling_back_to_an_empty_list(self):
        for data in ("x", {"schema_version": 9, "providers": [good_provider()]}, {"schema_version": 1, "providers": []}, registry_data(good_provider(), good_provider())):
            with self.subTest(data=str(data)[:40]), self.assertRaises(sr.SourceRegistryError):
                sr.build_registry(data, TODAY)
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in (("empty.json", ""), ("bad.json", "{nope"), ("list.json", "[]"), ("bom.json", "﻿{}")):
                path = Path(tmp) / name
                path.write_text(content, encoding="utf-8")
                with self.subTest(name=name), self.assertRaises(sr.SourceRegistryError):
                    sr.load_registry(path, TODAY)
            with self.assertRaises(sr.SourceRegistryError) as caught:
                sr.load_registry(Path(tmp) / "missing.json", TODAY)
            self.assertNotIn(tmp, str(caught.exception))                          # 오류 문구에 폴더 경로를 싣지 않는다(파일 이름만)

    def test_load_registry_reads_a_file_and_the_default_path_is_the_real_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text(json.dumps(registry_data(good_provider()), ensure_ascii=False), encoding="utf-8")
            registry = sr.load_registry(str(path), today=TODAY)
            self.assertEqual([p.provider_id for p in registry.active_providers()], ["fixture_stats"])
        self.assertEqual(sr.DEFAULT_PATH, REAL_PATH)
        self.assertEqual(sr.AI_POLICY_PATH, AI_PATH)


class AiProcessorPolicyTest(unittest.TestCase):
    """AI 처리기(Gemini 등)는 출처가 아니라 처리기 — 11칸과 풀 수 없는 기본값."""

    def data(self):
        return json.loads(AI_PATH.read_text(encoding="utf-8"))

    def test_the_real_file_has_the_eleven_cells_and_validates(self):
        data = self.data()
        self.assertEqual(sr.validate_ai_policy(data), [])
        self.assertEqual(list(sr.AI_FIELDS), ["professional_business_use", "consumer_use", "free_service_data_use", "paid_service_data_policy", "sensitive_data_allowed", "medical_advice_use",
                                              "input_scope", "raw_source_text_allowed", "credential_storage", "policy_version", "policy_verified_at"])
        for name in sr.AI_FIELDS:
            self.assertIn(name, data)
        policy = sr.load_ai_policy()
        self.assertEqual(policy.processor, "google_gemini_api")
        self.assertIs(policy.raw_source_text_allowed, False)             # 원문 외부 텍스트를 AI 에 넣지 않는다
        self.assertIs(policy.sensitive_data_allowed, False)              # 개인·기밀·자격증명 금지
        self.assertEqual(policy.medical_advice_use, "DENIED")
        self.assertEqual(policy.input_scope, "SIGNAL_AND_VERIFIED_MINIMAL_FACTS")
        self.assertEqual(policy.credential_storage, "WINDOWS_CREDENTIAL_MANAGER_AND_ACTIONS_SECRETS")
        self.assertEqual(policy.free_service_data_use, "USED_FOR_PRODUCT_IMPROVEMENT")      # 무료 등급은 입력이 제품 개선에 쓰인다 → 공개 전 전체 초안을 넣지 않는다
        self.assertEqual(policy.paid_service_data_policy, "NOT_USED_FOR_PRODUCT_IMPROVEMENT")
        self.assertEqual((policy.policy_version, policy.policy_verified_at), ("gemini-api-additional-terms-2026-03-23", "2026-11-09"))

    def test_the_fixed_defaults_cannot_be_loosened_in_the_file(self):
        for name, loosened in (("raw_source_text_allowed", True), ("sensitive_data_allowed", True), ("medical_advice_use", "ALLOWED"), ("input_scope", "UNRESTRICTED"),
                               ("credential_storage", "REPOSITORY")):
            data = self.data()
            data[name] = loosened
            problems = sr.validate_ai_policy(data)
            self.assertTrue(problems, name)
            self.assertTrue(any(name in p for p in problems), name)
        data = self.data()
        data["raw_source_text_allowed"] = True
        self.assertTrue(has(sr.validate_ai_policy(data), "P3", "raw_source_text_allowed"))
        self.assertEqual(sorted(sr.AI_FIXED), ["credential_storage", "input_scope", "medical_advice_use", "raw_source_text_allowed", "sensitive_data_allowed"])

    def test_shape_and_enumeration_rules(self):
        for name in sr.AI_FIELDS:
            data = self.data()
            del data[name]
            self.assertTrue(has(sr.validate_ai_policy(data), "P1", name), name)
        for name, bad in (("professional_business_use", "YES"), ("consumer_use", None), ("free_service_data_use", "MAYBE"), ("paid_service_data_policy", ""), ("sensitive_data_allowed", "false"),
                          ("raw_source_text_allowed", 0), ("policy_verified_at", "2026/11/09"), ("policy_verified_at", None), ("policy_version", ""), ("medical_advice_use", "MAYBE")):
            data = self.data()
            data[name] = bad
            with self.subTest(name=name, bad=bad):
                self.assertTrue(has(sr.validate_ai_policy(data), "P2", name))
        for bad_top in ("x", [], None):
            self.assertTrue(has(sr.validate_ai_policy(bad_top), "P1"))
        data = self.data()
        data["schema_version"] = 2
        self.assertTrue(has(sr.validate_ai_policy(data), "P1", "schema_version"))
        for bad_version in (True, 1.0, "1", None):
            data = self.data()
            data["schema_version"] = bad_version
            self.assertTrue(has(sr.validate_ai_policy(data), "P1", "schema_version"), bad_version)
        data = self.data()
        data["unknown_cell"] = 1
        self.assertTrue(has(sr.validate_ai_policy(data), "P1", "알 수 없는 칸"))
        data = self.data()
        data["processor"] = " "
        self.assertTrue(has(sr.validate_ai_policy(data), "P1", "processor"))
        data = self.data()
        for name in ("professional_business_use", "consumer_use"):
            for value in ("UNKNOWN", "CONDITIONAL", "ALLOWED", "DENIED"):
                data[name] = value
                self.assertEqual(sr.validate_ai_policy(data), [], (name, value))      # 모르는 값은 UNKNOWN 으로 둘 수 있다

    def test_loader_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({**self.data(), "raw_source_text_allowed": True}), encoding="utf-8")
            with self.assertRaises(sr.SourceRegistryError):
                sr.load_ai_policy(bad)
            bad.write_text("{nope", encoding="utf-8")
            with self.assertRaises(sr.SourceRegistryError):
                sr.load_ai_policy(bad)
            with self.assertRaises(sr.SourceRegistryError):
                sr.load_ai_policy(Path(tmp) / "missing.json")
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps(self.data(), ensure_ascii=False), encoding="utf-8")
            self.assertEqual(sr.load_ai_policy(good), sr.load_ai_policy())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            sr.load_ai_policy().raw_source_text_allowed = True

    def test_the_command_line_check_says_the_policy_file_is_not_read_at_run_time(self):
        """P07(D-176): 검증기 명령줄이 성공할 때 '코드는 이 파일을 실행 중에 읽지 않는다'를 한 줄로 알린다."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sr.main(["--today", TODAY])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("검증 통과", text)
        self.assertIn("코드는 실행 중에 읽지 않는다", text)
        self.assertIn("legacy 는 외부 기사 요약이 지금도 AI 입력으로 간다", text)

    def test_gemini_is_not_a_provider_of_the_registry(self):
        self.assertNotIn("gemini", REAL_PATH.read_text(encoding="utf-8").lower().replace("ai_processor_policy", ""))


class ModuleHygieneTest(unittest.TestCase):
    """새 모듈의 위생: 표준 라이브러리만(레지스트리 검증처럼 pip 없이 도는 곳에서도 부른다)·시각과 무작위를 읽지 않음·msvcrt·ctypes·윈도 경로 없음."""
    ALLOWED_IMPORTS = {"argparse", "datetime", "json", "re", "sys", "urllib", "dataclasses", "pathlib", "typing", "pipeline"}

    def tree(self):
        return ast.parse((ROOT / "pipeline" / "source_registry.py").read_text(encoding="utf-8"))

    def test_only_standard_library_modules_are_imported(self):
        names = set()
        for node in ast.walk(self.tree()):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
        self.assertTrue(names <= self.ALLOWED_IMPORTS, sorted(names - self.ALLOWED_IMPORTS))
        self.assertTrue({"msvcrt", "ctypes", "subprocess", "socket", "os"}.isdisjoint(names))

    def test_the_module_never_reads_the_clock_or_randomness(self):
        banned = {"now", "utcnow", "today", "time", "monotonic", "perf_counter", "random", "urandom", "uuid4"}
        for node in ast.walk(self.tree()):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in banned:
                self.fail(f"시각·무작위를 읽는 호출: .{node.func.attr}() (line {node.lineno}) — 오늘은 인자로 받는다")

    def test_no_message_carries_a_tilde(self):
        """P15: 오류 문구는 운영자 화면·마크다운에도 실린다 — 물결표(~)는 취소선으로 렌더링될 수 있어 범위는 –(2026-11-09 사고). 모듈에서 물결표가 든 글자는 경로 정규식 하나뿐이다."""
        found = [node.value for node in ast.walk(self.tree()) if isinstance(node, ast.Constant) and isinstance(node.value, str) and "~" in node.value]
        self.assertEqual(found, ["/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*"])
        texts = []
        for sample in (good_provider(provider_id="a"), good_provider(strict_tier=9), good_provider(permissive_interpretation=9), good_provider(**{"class": "x"})):
            texts += sr.validate_registry(registry_data(sample), TODAY)
        self.assertGreaterEqual(len(texts), 4)
        for text in texts:
            self.assertNotIn("~", text)

    def test_no_windows_path_literals(self):
        for node in ast.walk(self.tree()):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertIsNone(re.match(r"^[A-Za-z]:[\\/]", node.value), node.value[:40])


if __name__ == "__main__":
    unittest.main()
