"""운영자 결정 007(2026-11-09 20:33) 반영 시험 — 'AI 를 쓰지 않는 규칙 기반 경로에서만 AI 입력 칸을 판정에서 뺀다'.

- `ai_use`(BY_CELL 기본·NEVER): 값 검증, 기본값에서 계산 결과가 예전과 바이트까지 같음, NEVER 이면 `ai_input` 칸만 strict 판정(`computed_strict_tier`·A2·A3)에서 빠지고 나머지 6칸은 그대로임.
  이 값은 아무것도 켜지 않는다(enabled 불변).
- 출처 표시 문구(S9)·`own_data_only`(S11): 자리 표시·길이·링크·금지 글자·로고·보증 암시 표현, 공공영역 문구는 제공처가 만든 값만 읽는 항목에서만.
- 호출 한도(S10·A11): 'N/…' 문구와 구조화 객체(official NONE + 우리 자체 상한 own 14칸 + note)의 경계·모르는 값 거절·기본값 없음, ACTIVE api 경로는 한도가 알려져야 켠다.
- A10: 호스트 전체를 여는 접두어('/')는 켤 수 없다(SRCV2 D5).
- 실제 파일: NOAA 조사(2026-11-10)로 확인된 값이 noaa_swpc_json 에 그대로 들어 있고 제3자 자료·조사 전 항목은 따로 꺼져 있다.

네트워크·시계를 쓰지 않는다 — '오늘'은 인자로 준다."""
import copy
import dataclasses
import json
import unittest

import _bootstrap  # noqa: F401
from pipeline import source_registry as sr
from source_registry_helpers import GOOD_HOST, TODAY, cell, codes, good_provider, has, registry_data, with_access, with_cell

ROOT = _bootstrap.ROOT
REAL_PATH = ROOT / "pipeline" / "source_registry.json"
NOAA_FEDERAL_TEMPLATE = ("자료: {title}, 미국 NOAA 우주기상예측센터({date} 열람). NOAA 가 만든 이 자료는 미국 연방정부 저작물이라 저작권 보호 대상이 아닙니다. "
                         "값을 가공해 더한 계산과 설명은 이 블로그의 것이며 NOAA·미국 정부가 인정하거나 보증한 내용이 아닙니다.")
NOAA_PATHS = ["/products/noaa-planetary-k-index.json", "/products/noaa-planetary-k-index-forecast.json", "/products/noaa-scales.json", "/json/solar-cycle/swpc_observed_ssn.json",
              "/json/solar-cycle/observed-solar-cycle-indices.json", "/json/goes/primary/xray-flares-7-day.json"]
SPLIT_IDS = ("statcan_wds", "uk_govuk_api", "noaa_swpc_json")
THIRD_PARTY_IDS = ("swpc_f107_nrc", "swpc_kyoto_dst", "swpc_sidc_penticton_fields")


def real_providers():
    return {p["provider_id"]: p for p in json.loads(REAL_PATH.read_text(encoding="utf-8"))["providers"]}


def own_limit(**overrides):
    out = {"min_gap_same_file_s": 60, "min_gap_other_file_s": 5, "max_products_per_post": 3, "max_calls_per_product_per_post": 1, "max_calls_per_day": 8, "max_calls_per_month": 100,
           "max_retries": 1, "retry_after_s": 60, "stop_hours_on_403_429": 24, "stop_product_on_404": True, "request_gzip": True, "daily_product_not_before_utc": "00:30",
           "daily_product_max_per_day": 1, "fail_closed_on_bad_response": True}
    out.update(overrides)
    return out


def rate_object(**overrides):
    out = {"official": "NONE", "own": own_limit(), "note": "공식 수치 한도 없음. 자체 상한(제안, 공식 값 아님): 같은 파일 60초 이상, 하루 8회, 월 100회 이하"}
    out.update(overrides)
    return out


def old_computed_strict_tier(cells, provider_class="data"):
    """ai_use 가 생기기 전의 7칸 계산(그대로 옮긴 기준 구현) — 기본값에서 새 코드의 결과와 같아야 한다."""
    if provider_class == "internal":
        return 0
    get = lambda name: (cells[name]["state"], cells[name]["basis"])   # noqa: E731
    if any(get(name)[0] == "DENIED" for name in sr.CORE_DENY_CELLS) or get("ai_input")[0] == "DENIED":
        return 4
    if any(get(name)[0] == "DENIED" for name in sr.CELLS):
        return 3
    if any(get(name)[0] == "UNKNOWN" or get(name)[1] not in sr.STRICT_BASES for name in sr.CELLS):
        return 3
    return 1 if any(get(name)[1] in sr.OPEN_LICENSE_BASES for name in ("license", "commercial_use", "derivative_use", "storage")) else 2


class AiUseSchemaTest(unittest.TestCase):
    def problems(self, provider, today=TODAY):
        return sr.validate_registry(registry_data(provider), today)

    def test_the_values_and_the_default(self):
        self.assertEqual(sr.AI_USE_VALUES, ("BY_CELL", "NEVER"))
        self.assertEqual(sr.DEFAULT_AI_USE, "BY_CELL")
        registry = sr.build_registry(registry_data(good_provider(enabled=False)), TODAY)
        self.assertEqual(registry.get("fixture_stats").ai_use, "BY_CELL")               # 적지 않으면 기본값
        for value in sr.AI_USE_VALUES:
            registry = sr.build_registry(registry_data(good_provider(enabled=False, ai_use=value)), TODAY)
            self.assertEqual(registry.get("fixture_stats").ai_use, value)

    def test_unknown_values_are_refused_as_an_enumeration_error(self):
        for bad in ("never", "Never", "ALWAYS", "BY_CELLS", "", None, 0, False, ["NEVER"], {"NEVER": 1}):
            with self.subTest(bad=bad):
                self.assertTrue(has(self.problems(good_provider(ai_use=bad)), "S2", "ai_use"), repr(bad))
        for good in sr.AI_USE_VALUES:
            self.assertFalse(has(self.problems(good_provider(ai_use=good)), "S2"), good)

    def test_the_default_gives_the_same_tier_as_before_ai_use_existed(self):
        """기본값(인자 없음·BY_CELL)에서 7칸 계산은 예전과 같다 — 칸 하나씩 모든 (판정, 근거) 조합 168개와 대표 묶음에서 비교한다."""
        base = {name: {"state": "ALLOWED", "basis": "EXPLICIT"} for name in sr.CELLS}
        samples = [base]
        for name in sr.CELLS:
            for state in sr.STATES:
                for basis in sr.BASES:
                    sample = copy.deepcopy(base)
                    sample[name] = {"state": state, "basis": basis}
                    samples.append(sample)
        for open_name in ("license", "commercial_use", "derivative_use", "storage"):
            sample = copy.deepcopy(base)
            sample[open_name] = {"state": "ALLOWED", "basis": "STANDARD_LICENSE"}
            samples.append(sample)
        for sample in samples:
            expected = old_computed_strict_tier(sample)
            self.assertEqual(sr.computed_strict_tier(sample), expected)
            self.assertEqual(sr.computed_strict_tier(sample, "data"), expected)
            self.assertEqual(sr.computed_strict_tier(sample, "data", "BY_CELL"), expected)
            self.assertEqual(sr.computed_strict_tier(sample, "image", "BY_CELL"), old_computed_strict_tier(sample, "image"))
            self.assertEqual(sr.computed_strict_tier(sample, "data", "never"), expected)              # 모르는 값은 판정을 느슨하게 하지 못한다
        self.assertEqual(sr.computed_strict_tier(base, "internal", "NEVER"), 0)

    def test_never_skips_only_the_ai_input_cell(self):
        base = {name: {"state": "ALLOWED", "basis": "EXPLICIT"} for name in sr.CELLS}
        for state, basis in (("UNKNOWN", "NOT_READ"), ("ALLOWED", "IMPLIED"), ("ALLOWED", "NOT_ADDRESSED"), ("DENIED", "EXPLICIT"), ("UNKNOWN", "EXPLICIT")):
            sample = copy.deepcopy(base)
            sample["ai_input"] = {"state": state, "basis": basis}
            self.assertEqual(sr.computed_strict_tier(sample, "data", "NEVER"), 2, (state, basis))     # ai_input 이 무엇이든 나머지가 알려졌으면 계산이 같다
            self.assertGreaterEqual(sr.computed_strict_tier(sample), 3, (state, basis))
        for name in sr.CELLS:
            if name == "ai_input":
                continue
            for state, basis in (("UNKNOWN", "NOT_READ"), ("ALLOWED", "IMPLIED"), ("ALLOWED", "NOT_ADDRESSED"), ("DENIED", "EXPLICIT")):
                sample = copy.deepcopy(base)
                sample[name] = {"state": state, "basis": basis}
                self.assertEqual(sr.computed_strict_tier(sample, "data", "NEVER"), sr.computed_strict_tier(sample, "data", "BY_CELL"), (name, state, basis))      # 나머지 6칸은 그대로
        sample = copy.deepcopy(base)
        sample["commercial_use"] = {"state": "DENIED", "basis": "EXPLICIT"}
        self.assertEqual(sr.computed_strict_tier(sample, "data", "NEVER"), 4)                       # 상업 이용 금지는 NEVER 여도 Tier 4

    def test_active_rules_skip_only_the_ai_input_cell_under_never(self):
        for state, basis in (("UNKNOWN", "NOT_READ"), ("ALLOWED", "IMPLIED"), ("ALLOWED", "NOT_ADDRESSED"), ("DENIED", "EXPLICIT")):
            sample = with_cell(good_provider(ai_use="NEVER"), "ai_input", state=state, basis=basis)
            self.assertEqual(self.problems(sample), [], (state, basis))                              # ai_input DENIED 여도 우리가 AI 를 안 쓰므로 충돌 없음 — 막지 않는다
            blocked = with_cell(good_provider(), "ai_input", state=state, basis=basis)
            self.assertTrue(codes(self.problems(blocked)) & {"A1", "A2", "A3", "A7"}, (state, basis))   # 기본값(BY_CELL)은 지금처럼 막힌다
        for name in sr.CELLS:
            if name == "ai_input":
                continue
            for state, basis, code in (("UNKNOWN", "NOT_READ", "A2"), ("ALLOWED", "IMPLIED", "A2"), ("DENIED", "EXPLICIT", "A3")):
                sample = with_cell(good_provider(ai_use="NEVER"), name, state=state, basis=basis)
                self.assertTrue(has(self.problems(sample), code, name), (name, state, basis, code))      # 나머지 6칸은 NEVER 여도 그대로 막는다

    def test_never_does_not_loosen_tier_four_or_the_stored_tier(self):
        self.assertTrue(has(self.problems(good_provider(ai_use="NEVER", strict_tier=4)), "A7"))     # 저장된 Tier 4 는 계속 완전 제외
        self.assertTrue(has(self.problems(with_cell(good_provider(ai_use="NEVER"), "commercial_use", state="DENIED")), "A7"))
        self.assertTrue(has(self.problems(with_cell(good_provider(ai_use="NEVER"), "ai_input", state="DENIED", basis="EXPLICIT") | {"strict_tier": 3}), "A1"))
        for name in sr.CELLS:
            sample = with_cell(good_provider(ai_use="NEVER"), name, evidence="")                    # 근거 이름·열람일 기록(A8)은 ai_input 도 그대로 요구한다
            self.assertTrue(has(self.problems(sample), "A8", name), name)

    def test_s7_uses_the_never_aware_status(self):
        """ai_use NEVER 이면 ai_input 이 UNKNOWN 이어도 '자동화 가능'이라고 적을 수 있고(계산이 같다), 기본값이면 거부된다."""
        sample = with_cell(good_provider(enabled=False, ai_use="NEVER"), "ai_input", state="UNKNOWN", basis="NOT_READ")
        self.assertEqual(self.problems(sample), [])
        self.assertTrue(has(self.problems(with_cell(good_provider(enabled=False), "ai_input", state="UNKNOWN", basis="NOT_READ")), "S7"))

    def test_never_enables_nothing(self):
        """이 값은 아무것도 켜지 않는다 — enabled 가 false 면 ACTIVE 가 아니고 어느 호스트도 허용되지 않는다."""
        provider = with_cell(good_provider(enabled=False, ai_use="NEVER"), "ai_input", state="DENIED", basis="EXPLICIT")
        registry = sr.build_registry(registry_data(provider), TODAY)
        self.assertEqual(registry.active_providers(), [])
        self.assertFalse(registry.is_active("fixture_stats"))
        self.assertFalse(registry.get("fixture_stats").enabled)
        self.assertFalse(registry.is_url_allowed(f"https://{GOOD_HOST}/v1/x", "fact")[0])
        on = sr.build_registry(registry_data(dict(provider, enabled=True)), TODAY)
        self.assertEqual([p.provider_id for p in on.active_providers()], ["fixture_stats"])          # 켜는 것은 enabled 한 칸(T3) — ai_use 가 아니다

    def test_the_provider_object_stays_read_only(self):
        registry = sr.build_registry(registry_data(good_provider(enabled=False, ai_use="NEVER")), TODAY)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            registry.get("fixture_stats").ai_use = "BY_CELL"


class AttributionTemplateTest(unittest.TestCase):
    def problems(self, template, **overrides):
        return sr.validate_registry(registry_data(good_provider(attribution_template=template, **overrides)), TODAY)

    def test_good_templates_pass(self):
        for template in ("Source: Fixture Agency", "Adapted from Statistics Canada, {title}, {date}. This does not constitute an endorsement by Statistics Canada of this product.",
                         "{title}, GOV.UK, {date}. Contains public sector information licensed under the Open Government Licence v3.0.",
                         "자료: {title}, 미국 NOAA 우주기상예측센터({date} 열람). 이 글의 계산과 해석은 이 블로그가 한 것이며 NOAA·미국 정부의 공식 자료나 보증이 아닙니다.",
                         "출처 {url} 에서 {title} 을(를) {date} 에 가져와 계산했습니다", "  앞뒤 공백은 잘라서 본다 {title}  ", ""):
            with self.subTest(template=template):
                self.assertFalse(has(self.problems(template), "S9"), template)

    def test_the_real_federal_sentence_passes_the_form_rules_only_for_own_data(self):
        self.assertEqual(self.problems(NOAA_FEDERAL_TEMPLATE, own_data_only=True), [])
        self.assertFalse(has(self.problems(NOAA_FEDERAL_TEMPLATE, own_data_only=True), "S9"))
        self.assertTrue(has(self.problems(NOAA_FEDERAL_TEMPLATE), "S11", "own_data_only"))           # 제3자 자료를 읽을 수 있는 항목은 못 쓴다
        self.assertTrue(has(self.problems(NOAA_FEDERAL_TEMPLATE, own_data_only=False), "S11"))

    def test_bad_templates_are_refused_with_s9(self):
        bad = {"링크": "자료는 https://agency.example/x 에서", "링크 www": "자료는 www.agency.example 에서", "새 줄": "첫 줄\n둘째 줄", "탭": "자료:\t{title}", "꺾쇠": "자료 <b>{title}</b> 입니다",
               "역따옴표": "자료 `{title}` 입니다", "대괄호": "자료 [{title}](x) 입니다", "역슬래시": "자료 {title} \\ 입니다", "세로줄": "자료 | {title} 입니다", "물결표": "자료 {title} 약 3 " + chr(126) + " 5 입니다",
               "전각 물결표": "자료 {title} 약 3" + chr(0xff5e) + "5 입니다", "표시 괄호": "자료 " + chr(0x27e6) + "x" + chr(0x27e7) + " {title} 입니다", "모르는 자리 표시": "자료 {name} 입니다",
               "겹중괄호": "자료 {{title}} 입니다", "닫히지 않은 중괄호": "자료 {title 입니다", "자리 표시만": "{title}{date}{url}", "너무 짧은 일반 문구": "{title} 입니다",
               "너무 긺": "가" * (sr.ATTRIBUTION_MAX + 1)}
        for label, template in bad.items():
            with self.subTest(label=label):
                self.assertTrue(has(self.problems(template), "S9"), label)
        self.assertFalse(has(self.problems("가" * sr.ATTRIBUTION_MAX), "S9"))                          # 상한 경계
        self.assertTrue(has(sr.validate_registry(registry_data(good_provider(enabled=False, attribution_template="자료 <b>x</b>")), TODAY), "S9"))   # 꺼진 항목도 모양은 본다

    def test_logo_and_endorsement_words_are_refused(self):
        words = {"로고": "자료 {title} 로고 사용", "logo": "Source {title} with the agency Logo", "휘장": "자료 {title} 휘장 포함", "emblem": "Source {title} NWS emblem here",
                 "인정한": "NOAA 가 인정한 자료 {title} 입니다", "보증한": "NOAA 가 보증한 자료 {title} 입니다", "승인한": "NOAA 가 승인한 자료 {title} 입니다", "공식 분석": "NOAA 공식 분석 {title} 입니다",
                 "공식 인증": "공식 인증 자료 {title} 입니다", "공식 제휴": "공식 제휴 자료 {title} 입니다", "후원": "NOAA 가 후원한 자료 {title} 입니다", "endorsed by": "Data {title}, endorsed by NOAA",
                 "in partnership with": "Data {title} in partnership with NOAA", "정부가 인정한": "미국 정부가 인정한 자료 {title} 입니다"}
        for label, template in words.items():
            with self.subTest(label=label):
                self.assertTrue(has(self.problems(template), "S9"), label)
        ownership = {"저작권 기호": "자료 {title} \u00a9 이 블로그", "원 안의 c": "자료 {title} \u24d2 이 블로그", "상표 기호": "자료 {title} NOAA\u2122 입니다", "등록 상표 기호": "자료 {title} NOAA\u00ae 입니다",
                     "all rights reserved": "Data {title}. All rights reserved.", "모든 권리": "자료 {title} 모든 권리는 이 블로그에 있습니다", "무단 전재": "자료 {title} 무단 전재 금지", "무단 복제": "자료 {title} 무단 복제 금지",
                     "저작권은 이 블로그": "자료 {title} 저작권은 이 블로그에 있습니다"}
        for label, template in ownership.items():                                                      # 자료를 우리 것이라 주장하지 않는다(NWS 면책 문서의 금지)
            with self.subTest(label=label):
                self.assertTrue(has(self.problems(template), "S9", "권리 주장"), label)
        for template in ("NOAA·미국 정부가 인정하거나 보증한 내용이 아닙니다. {title} 의 계산입니다", "이 글은 {title} 을 가공한 것으로 NOAA 의 공식 자료나 보증이 아닙니다"):    # 부정 문장은 걸리지 않는다
            self.assertFalse(has(self.problems(template), "S9"), template)

    def test_s11_own_data_only_is_a_boolean_and_public_domain_words_need_it(self):
        for bad in ("true", 1, 0, None, []):
            with self.subTest(bad=bad):
                self.assertTrue(has(self.problems("Source: Fixture Agency", own_data_only=bad), "S11", "own_data_only"), repr(bad))
        for value in (True, False):
            self.assertFalse(has(self.problems("Source: Fixture Agency", own_data_only=value), "S11"))
        claims = ("자료는 미국 연방정부 저작물이라 {title} 입니다", "이 자료는 저작권 보호 대상이 아닙니다 {title}", "이 자료는 공공영역에 있습니다 {title}", "퍼블릭 도메인 자료 {title}", "This is in the public domain {title}",
                  "Work of the U.S. Government, 17 U.S.C. 105 {title}", "No copyright applies under 17 USC 105 {title}")
        for claim in claims:
            with self.subTest(claim=claim):
                self.assertTrue(has(self.problems(claim), "S11"), claim)
                self.assertTrue(has(self.problems(claim, own_data_only=False), "S11"), claim)
                self.assertFalse(has(self.problems(claim, own_data_only=True), "S11"), claim)
                self.assertTrue(sr.attribution_claims_public_domain(claim), claim)
        self.assertFalse(sr.attribution_claims_public_domain("Source: Fixture Agency"))
        self.assertFalse(sr.attribution_claims_public_domain(None))


class PathPrefixAndRateLimitTest(unittest.TestCase):
    def problems(self, provider, today=TODAY):
        return sr.validate_registry(registry_data(provider), today)

    # -- A10 (SRCV2 D5) -----------------------------------------------------------------------------------------------------------------------------------------------
    def test_a10_refuses_a_prefix_that_opens_the_whole_host(self):
        for paths in (["/"], ["/", "/v1/"], ["/v1/", "/"], [" / "]):
            with self.subTest(paths=paths):
                provider = with_access(good_provider(), paths=paths)
                if paths == [" / "]:
                    self.assertTrue(has(self.problems(provider), "S4"))                                  # 공백이 든 접두어는 모양(S4)에서 이미 거절
                    continue
                self.assertTrue(has(self.problems(provider), "A10", "access[0]", "호스트 전체"), paths)
                registry = sr.build_registry(registry_data(provider), TODAY)
                self.assertEqual(registry.active_providers(), [])
                self.assertFalse(registry.is_url_allowed(f"https://{GOOD_HOST}/anything/at/all", "fact")[0])
        for paths in (["/v1/"], ["/v1"], ["/a/b/c.json"], ["/v1/", "/v2/"]):
            self.assertFalse(has(self.problems(with_access(good_provider(), paths=paths)), "A10"), paths)
        for paths in ([""], ["."], [".."], ["//"], ["v1"]):                                              # 빈 문자열·점·`//` 는 모양 규칙 S4 가 거절한다
            self.assertTrue(has(self.problems(with_access(good_provider(), paths=paths)), "S4"), paths)
        self.assertFalse(has(self.problems(with_access(good_provider(enabled=False), paths=["/"])), "A10"))   # 꺼져 있으면 ACTIVE 규칙은 적용하지 않는다

    # -- 'N/단위' 문구 -------------------------------------------------------------------------------------------------------------------------------------------------
    def test_the_rate_limit_text_grammar(self):
        good = {"100 per day": ((100, "day"),), "100/day": ((100, "day"),), "100 / Day": ((100, "day"),), "60 requests per minute": ((60, "minute"),), "5 calls per hour": ((5, "hour"),),
                "25 per second": ((25, "second"),), "60/minute, 1000/hour": ((60, "minute"), (1000, "hour")), "10/minute; 500 per day": ((10, "minute"), (500, "day")), "999999999/day": ((999999999, "day"),)}
        for text, expected in good.items():
            with self.subTest(text=text):
                self.assertEqual(sr.parse_rate_limit(text), expected)
        for bad in (None, "", "  ", "UNKNOWN", "확인 필요", "0/day", "-1/day", "1.5/day", "100/week", "100 per", "per day", "100", "abc/day", "1000000000/day", "100/day, UNKNOWN", ",", 5, ["100/day"], {"a": 1}):
            with self.subTest(bad=bad):
                self.assertIsNone(sr.parse_rate_limit(bad))

    # -- A11 ----------------------------------------------------------------------------------------------------------------------------------------------------------
    def test_a11_an_active_api_path_needs_a_known_rate_limit(self):
        for limit in (None, "", "   ", "UNKNOWN", "확인 필요", "0/day", "100/week", 5):
            with self.subTest(limit=limit):
                provider = with_access(good_provider(), rate_limit=limit)
                problems = self.problems(provider)
                if isinstance(limit, int):
                    self.assertTrue(has(problems, "S1", "rate_limit"))                                 # 숫자는 모양 규칙에서 거절
                else:
                    self.assertTrue(has(problems, "A11", "access[0]"), repr(limit))
        for limit in ("100 per day", "60/minute", "5 calls per hour", rate_object(), rate_object(official="100/day"), rate_object(official="100/day", own=None)):
            with self.subTest(limit=limit):
                self.assertEqual(self.problems(with_access(good_provider(), rate_limit=limit)), [], limit)
        missing = good_provider()
        del missing["access"][0]["rate_limit"]
        self.assertTrue(has(self.problems(missing), "A11"))                                            # 칸이 없는 것도 모르는 것이다
        second = good_provider()
        second["access"].append(dict(second["access"][0], rate_limit=None))
        self.assertTrue(has(self.problems(second), "A11", "access[1]"))
        self.assertFalse(has(self.problems(second), "A11", "access[0]"))

    def test_a11_applies_to_api_paths_only_and_only_when_enabled(self):
        for kind in ("csv", "dataset"):
            self.assertFalse(has(self.problems(with_access(good_provider(), kind=kind, rate_limit=None)), "A11"), kind)
        self.assertFalse(has(self.problems(with_access(good_provider(enabled=False), rate_limit=None)), "A11"))
        registry = sr.build_registry(registry_data(with_access(good_provider(), rate_limit=None)), TODAY)
        self.assertEqual(registry.active_providers(), [])
        self.assertIn("A11", registry.inactive_reasons()["fixture_stats"][0])

    # -- S10: 구조화 객체 ------------------------------------------------------------------------------------------------------------------------------------------------
    def shape(self, limit, enabled=False):
        return self.problems(with_access(good_provider(enabled=enabled, effective_status="자동화 가능"), rate_limit=limit))

    def test_a_good_object_passes_and_loads_as_frozen_values(self):
        self.assertEqual(self.shape(rate_object()), [])
        self.assertEqual(self.shape(rate_object(), enabled=True), [])
        registry = sr.build_registry(registry_data(with_access(good_provider(enabled=False), rate_limit=rate_object())), TODAY)
        limit = registry.get("fixture_stats").access[0].rate_limit
        self.assertIsInstance(limit, sr.RateLimit)
        self.assertIsInstance(limit.own, sr.OwnLimit)
        self.assertEqual((limit.official, limit.own.max_calls_per_day, limit.own.daily_product_not_before_utc), ("NONE", 8, "00:30"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            limit.own.max_calls_per_day = 9000
        text_registry = sr.build_registry(registry_data(with_access(good_provider(enabled=False), rate_limit="100 per day")), TODAY)
        self.assertEqual(text_registry.get("fixture_stats").access[0].rate_limit, "100 per day")        # 문구는 그대로 문구
        self.assertEqual({f.name for f in dataclasses.fields(sr.OwnLimit)}, set(sr.OWN_LIMIT_KEYS))
        self.assertEqual(len(sr.OWN_LIMIT_KEYS), 14)

    def test_unknown_keys_and_wrong_shapes_are_refused(self):
        for label, limit in (("최상위 알 수 없는 칸", rate_object(extra=1)), ("official 없음", {k: v for k, v in rate_object().items() if k != "official"}),
                             ("official 이상한 값", rate_object(official="weekly")), ("official 빈 값", rate_object(official="")), ("official 숫자", rate_object(official=5)),
                             ("official 소문자 none", rate_object(official="none")), ("own 이 목록", rate_object(own=[1])), ("own 알 수 없는 칸", rate_object(own=own_limit(bonus=1))),
                             ("note 없음", {k: v for k, v in rate_object().items() if k != "note"}), ("note 빈 값", rate_object(note="  ")), ("note 숫자", rate_object(note=7))):
            with self.subTest(label=label):
                self.assertTrue(has(self.shape(limit), "S10"), label)

    def test_official_none_needs_the_own_limits_and_the_disclosure(self):
        self.assertTrue(has(self.shape(rate_object(own=None)), "S10", "자체 상한"))                      # 공식 한도가 없다고 했으면 자체 상한이 필수 — 한도 없이 켤 수 없다
        without_own = {k: v for k, v in rate_object().items() if k != "own"}
        self.assertTrue(has(self.shape(without_own), "S10", "자체 상한"))
        self.assertTrue(has(self.shape(without_own, enabled=True), "S10"))                              # 모양 오류라 켜기 전에 이미 거절
        for note in ("자체 상한 제안: 하루 8회", "공식 수치 한도 없음. 하루 8회 이하(제안)", "공식 수치 한도 없음. 자체 상한은 하루 8회", "하루 8회"):
            with self.subTest(note=note):
                self.assertTrue(has(self.shape(rate_object(note=note)), "S10", "공식 수치 한도 없음"), note)
        self.assertEqual(self.shape(rate_object(official="100/day", note="제공처 공개 한도 하루 100회", own=None)), [])      # 숫자 한도를 공개했으면 own 은 없어도 된다
        self.assertTrue(has(self.shape(rate_object(note="한 줄\n두 줄")), "S10", "한 줄"))
        self.assertTrue(has(self.shape(rate_object(note="공식 수치 한도 없음. 자체 상한 제안은 https://x.example 참고")), "S10", "한 줄"))
        self.assertTrue(has(self.shape(rate_object(note="공식 수치 한도 없음. 자체 상한(제안) " + "가" * sr.RATE_NOTE_MAX)), "S10", "한 줄"))

    def test_every_own_field_is_required_without_a_default(self):
        for name in sr.OWN_LIMIT_KEYS:
            with self.subTest(missing=name):
                own = own_limit()
                del own[name]
                problems = self.shape(rate_object(own=own))
                self.assertTrue(has(problems, "S10", name, "기본값"), name)
                self.assertFalse(sr.rate_limit_known(rate_object(own=own)))
        self.assertEqual(self.shape(rate_object(own={})), self.shape(rate_object(own={})))              # 빈 own 은 14칸 모두 빠진 것
        self.assertEqual(len([p for p in self.shape(rate_object(own={})) if "기본값" in p]), 14)

    # 자체 상한 정수 칸이 받아들이는 범위. 스키마 상수(OWN_LIMIT_SPEC)에서 읽어 시험하면 상수를 풀어도 시험이 함께 풀려 아무것도 못 잡으므로 값을 여기에 따로 적는다
    # (범위를 바꾸는 것은 의식적인 변경이어야 한다 — 하루 상한 1000 처럼 터무니없는 값을 막는 안전 범위다).
    OWN_INT_RANGES = {
        "min_gap_same_file_s": (1, 86400), "min_gap_other_file_s": (0, 3600), "max_products_per_post": (1, 20), "max_calls_per_product_per_post": (1, 5),
        "max_calls_per_day": (1, 1000), "max_calls_per_month": (1, 100000), "max_retries": (0, 3), "retry_after_s": (1, 86400),
        "stop_hours_on_403_429": (1, 720), "daily_product_max_per_day": (1, 24),
    }

    def test_the_numeric_fields_have_boundaries(self):
        self.assertEqual({name: (low, high) for name, kind, low, high in sr.OWN_LIMIT_SPEC if kind == "int"}, self.OWN_INT_RANGES)
        for name, (low, high) in self.OWN_INT_RANGES.items():
            with self.subTest(name=name):
                for ok in (low, high):                                                                  # 범위 문구만 본다(칸 사이 관계는 따로 시험)
                    self.assertFalse(has(self.shape(rate_object(own=own_limit(**{name: ok}))), "S10", name, "정수여야"), (name, ok))
                for bad in (low - 1, high + 1, True, False, 1.5, "8", None, [8]):
                    self.assertTrue(has(self.shape(rate_object(own=own_limit(**{name: bad}))), "S10", name, "정수여야"), (name, bad))

    def test_the_safety_booleans_and_the_clock_time(self):
        for name in ("stop_product_on_404", "fail_closed_on_bad_response"):
            for bad in (False, 1, "true", None):
                self.assertTrue(has(self.shape(rate_object(own=own_limit(**{name: bad}))), "S10", name, "true"), (name, bad))      # 끌 수 없는 안전 칸
        for ok in (True, False):
            self.assertFalse(has(self.shape(rate_object(own=own_limit(request_gzip=ok))), "S10", "request_gzip"))
        for bad in ("yes", 1, None, "true"):
            self.assertTrue(has(self.shape(rate_object(own=own_limit(request_gzip=bad))), "S10", "request_gzip"), bad)
        for ok in ("00:00", "00:30", "09:05", "23:59"):
            self.assertFalse(has(self.shape(rate_object(own=own_limit(daily_product_not_before_utc=ok))), "S10", "daily_product_not_before_utc"), ok)
        for bad in ("24:00", "0:30", "00:60", "00:30:00", "0030", "12:5", "", None, 30, "ab:cd"):
            self.assertTrue(has(self.shape(rate_object(own=own_limit(daily_product_not_before_utc=bad))), "S10", "daily_product_not_before_utc"), bad)

    def test_the_fields_must_fit_each_other(self):
        self.assertTrue(has(self.shape(rate_object(own=own_limit(max_calls_per_day=8, max_calls_per_month=7))), "S10", "max_calls_per_month"))
        self.assertFalse(has(self.shape(rate_object(own=own_limit(max_calls_per_day=8, max_calls_per_month=8))), "S10", "max_calls_per_month"))
        self.assertTrue(has(self.shape(rate_object(own=own_limit(max_calls_per_day=5))), "S10", "한 편도 끝낼 수 없습니다"))             # 3 × 1 × (1 + 1) = 6 > 5
        self.assertFalse(has(self.shape(rate_object(own=own_limit(max_calls_per_day=6))), "S10", "한 편도"))
        self.assertTrue(has(self.shape(rate_object(own=own_limit(max_retries=3, max_calls_per_day=8))), "S10", "한 편도"))              # 3 × 1 × 4 = 12 > 8

    def test_rate_limit_known_is_the_single_judgement_behind_a11(self):
        for good in ("100/day", rate_object(), rate_object(official="5 per second", own=None)):
            self.assertTrue(sr.rate_limit_known(good), good)
        for bad in (None, "", "UNKNOWN", rate_object(own=None), rate_object(official="NONE", note="x"), {}, {"official": "NONE"}, 7, []):
            self.assertFalse(sr.rate_limit_known(bad), bad)


class RealRegistryAfterTheSplitTest(unittest.TestCase):
    """실제 허용 목록: NOAA 조사(2026-11-10)로 확인된 값이 noaa_swpc_json 에 그대로 들어 있고, 제3자 자료·조사 전 항목은 따로 꺼져 있다."""

    @classmethod
    def setUpClass(cls):
        cls.providers = real_providers()
        cls.noaa = cls.providers["noaa_swpc_json"]

    def test_the_noaa_entry_carries_the_researched_values(self):
        noaa = self.noaa
        self.assertEqual((noaa["class"], noaa["enabled"], noaa["ai_use"], noaa["own_data_only"], noaa["strict_tier"], noaa["effective_status"]), ("data", False, "NEVER", True, 1, "자동화 가능"))
        self.assertEqual(len(noaa["access"]), 1)
        access = noaa["access"][0]
        self.assertEqual((access["kind"], access["hosts"], access["paths"], access["auth"], access["robots_checked_at"]), ("api", ["services.swpc.noaa.gov"], NOAA_PATHS, "NONE", "2026-11-10"))
        expected = {"commercial_use": ("ALLOWED", "EXPLICIT"), "automated_access": ("CONDITIONAL", "EXPLICIT"), "derivative_use": ("CONDITIONAL", "EXPLICIT"), "storage": ("ALLOWED", "STATUTE"),
                    "ai_input": ("ALLOWED", "IMPLIED"), "attribution": ("CONDITIONAL", "EXPLICIT"), "license": ("CONDITIONAL", "STATUTE")}
        self.assertEqual({name: (c["state"], c["basis"]) for name, c in noaa["policy"].items()}, expected)
        self.assertEqual({c["read_at"] for c in noaa["policy"].values()}, {"2026-11-10"})
        for name, c in noaa["policy"].items():
            self.assertIn("Disclaimer (National Weather Service)", c["evidence"], name)
        self.assertEqual(noaa["policy"]["storage"]["evidence"], "Disclaimer (National Weather Service), Service Change Notice 26-21")      # 근거 이름 교정(Data Access 페이지에는 보관 문구가 없다)
        pages = noaa["snapshot"]["terms_pages"]
        for name in ("Disclaimer (National Weather Service)", "Planetary K-index", "F10.7 cm Radio Emissions", "Solar Cycle Progression", "GOES X-ray Flux", "Service Change Notice 26-21"):
            self.assertIn(name, pages)
        self.assertEqual((noaa["snapshot"]["read_at"], noaa["snapshot"]["expires_at"], noaa["snapshot"]["content_hash"]), ("2026-11-10", "2027-02-08", ""))
        self.assertEqual(noaa["attribution_template"], NOAA_FEDERAL_TEMPLATE)
        self.assertEqual(noaa["reference_hosts"], [])

    def test_the_noaa_rate_limit_is_the_proposed_own_limit_and_says_so(self):
        limit = self.noaa["access"][0]["rate_limit"]
        self.assertEqual(limit["official"], "NONE")                                                    # 공식 수치 한도는 없다
        self.assertEqual(limit["own"], own_limit())
        for word in ("공식 수치 한도 없음", "자체 상한", "제안"):
            self.assertIn(word, limit["note"])
        self.assertEqual(sr._rate_limit_object_problems(limit), [])
        self.assertTrue(sr.rate_limit_known(limit))

    def test_the_noaa_paths_leave_out_third_party_and_large_files(self):
        paths = self.noaa["access"][0]["paths"]
        self.assertEqual(len(paths), 6)
        for path in paths:
            self.assertTrue(path.endswith(".json") and path.count("/") >= 2, path)                      # 전부 파일 하나(접두어가 아니다)
            for banned in ("10cm-flux", "f107_cm_flux", "kyoto", "45-day", "planetary_k_index_1m", "euvs", "xrays-7-day", "rtsw", "solar-wind", "magnetometers", "differential", "integral"):
                self.assertNotIn(banned, path, path)
        self.assertNotIn("/json/", paths)
        self.assertEqual({a["kind"] for a in self.noaa["access"]}, {"api"})                            # html 경로(A6)는 원래 항목에 남았다
        original = self.providers["noaa_swpc"]
        self.assertEqual([a["kind"] for a in original["access"]], ["html"])
        self.assertIn("www.swpc.noaa.gov", original["reference_hosts"])
        self.assertTrue(any("301" in text and "www.swpc.noaa.gov" in text for text in original["exceptions"]))      # 옛 주소 주석

    def test_the_exceptions_name_the_third_party_items_and_the_field_whitelist(self):
        text = " ".join(self.noaa["exceptions"])
        for needle in ("observed_swpc_ssn", "smoothed_swpc_ssn", "time-tag", "ssn", "f10.7", "S.I.D.C.", "Penticton", "캐나다 NRC", "kyoto-dst", "USGS", "GFZ", "swpc_f107_nrc", "swpc_kyoto_dst",
                       "swpc_sidc_penticton_fields", "필드 화이트리스트", "NWS 명칭", "로고", "NOAA 추정 Kp", "SCN 26-21"):
            self.assertIn(needle, text, needle)

    def test_third_party_items_are_separate_disabled_and_unknown(self):
        noaa_paths = set(self.noaa["access"][0]["paths"])
        for pid in THIRD_PARTY_IDS:
            provider = self.providers[pid]
            with self.subTest(pid=pid):
                self.assertFalse(provider["enabled"])
                self.assertEqual({c["state"] for c in provider["policy"].values()}, {"UNKNOWN"})
                self.assertEqual({c["basis"] for c in provider["policy"].values()}, {"NOT_READ"})
                self.assertEqual(provider["attribution_template"], "")
                self.assertFalse(provider.get("own_data_only", False))
                self.assertEqual(provider["strict_tier"], 3)
                self.assertNotIn("ai_use", provider)
                self.assertTrue(any("조사 필요" in text for text in provider["exceptions"]))
                for access in provider["access"]:
                    self.assertFalse(noaa_paths & set(access["paths"]), pid)                            # NOAA 항목과 같은 경로를 겹쳐 열지 않는다
        self.assertEqual(self.providers["swpc_f107_nrc"]["access"][0]["paths"], ["/products/10cm-flux-30-day.json", "/json/f107_cm_flux.json"])
        self.assertEqual(self.providers["swpc_kyoto_dst"]["access"][0]["paths"], ["/products/kyoto-dst.json"])
        self.assertEqual(self.providers["swpc_sidc_penticton_fields"]["access"], [])                    # 같은 파일 안의 필드라 따로 열 경로가 없다 — 참고 전용
        self.assertEqual(self.providers["swpc_sidc_penticton_fields"]["effective_status"], "참고 전용")
        self.assertIn("NRC", " ".join(self.providers["swpc_f107_nrc"]["exceptions"]))

    def test_statcan_and_the_uk_government_are_split_but_not_researched_yet(self):
        for pid, original in (("statcan_wds", "statcan"), ("uk_govuk_api", "uk_govuk")):
            provider = self.providers[pid]
            with self.subTest(pid=pid):
                self.assertFalse(provider["enabled"])
                self.assertEqual(provider["ai_use"], "NEVER")
                self.assertEqual(provider["attribution_template"], "")                                  # 값을 채우지 않았다(조사 전)
                self.assertEqual([a["rate_limit"] for a in provider["access"]], [None])
                self.assertEqual((provider["strict_tier"], provider["effective_status"]), (3, "자동화 제외"))     # 조사가 끝나기 전에는 켤 수 없다
                self.assertTrue(any("조사 필요" in text for text in provider["exceptions"]))
                self.assertEqual([a["kind"] for a in provider["access"]], ["api"])
                self.assertNotIn("api", [a["kind"] for a in self.providers[original]["access"]])
                self.assertEqual(provider["policy"], self.providers[original]["policy"])                # 칸은 원래 항목의 값 그대로(재확인 전)
        self.assertEqual(self.providers["uk_govuk_api"]["access"][0]["paths"], [])                      # 쓸 경로를 모르면 비워 둔다

    def test_ai_use_never_is_written_only_on_the_three_split_items(self):
        self.assertEqual({pid for pid, p in self.providers.items() if "ai_use" in p}, set(SPLIT_IDS))
        self.assertEqual({p["ai_use"] for pid, p in self.providers.items() if "ai_use" in p}, {"NEVER"})
        self.assertEqual({pid for pid, p in self.providers.items() if "own_data_only" in p}, {"noaa_swpc_json"})

    def test_the_federal_sentence_is_used_only_by_the_noaa_entry_that_reads_its_own_data(self):
        users = {pid for pid, p in self.providers.items() if sr.attribution_claims_public_domain(p["attribution_template"])}
        self.assertEqual(users, {"noaa_swpc_json"})
        for pid in users:
            self.assertTrue(self.providers[pid]["own_data_only"])
        for pid in THIRD_PARTY_IDS:                                                                     # 제3자 필드를 읽는 항목이 이 템플릿을 쓰면 거절된다
            borrowed = copy.deepcopy(self.providers[pid])
            borrowed["attribution_template"] = NOAA_FEDERAL_TEMPLATE
            self.assertTrue(has(sr.provider_problems(borrowed, TODAY), "S11"), pid)

    def test_the_original_provider_calculations_are_untouched_by_ai_use(self):
        """ai_use 를 적지 않은 모든 항목의 7칸 계산은 예전 계산(기준 구현)과 같다."""
        for pid, p in self.providers.items():
            if "ai_use" in p:
                continue
            with self.subTest(pid=pid):
                tier = old_computed_strict_tier(p["policy"], p["class"])
                self.assertEqual(sr.computed_strict_tier(p["policy"], p["class"], p.get("ai_use", "BY_CELL")), tier)

    def test_only_the_noaa_entry_passes_every_active_rule_if_it_were_enabled(self):
        passing = []
        for pid, p in self.providers.items():
            probe = copy.deepcopy(p)
            probe["enabled"] = True
            if not sr.provider_problems(probe, "2026-11-10"):
                passing.append(pid)
        self.assertEqual(passing, ["noaa_swpc_json"])                                                   # 켜는 것은 enabled 한 칸(T3 — 운영자 승인)이고 지금은 켜지 않았다
        problems = sr.provider_problems(dict(copy.deepcopy(self.providers["statcan_wds"]), enabled=True), "2026-11-10")
        self.assertTrue(codes(problems) >= {"A1", "A5", "A9", "A11"}, codes(problems))                 # 조사 전 항목은 막힌다
        problems = sr.provider_problems(dict(copy.deepcopy(self.providers["uk_govuk_api"]), enabled=True), "2026-11-10")
        self.assertTrue(codes(problems) >= {"A1", "A5", "A9", "A10", "A11"}, codes(problems))
        self.assertTrue(has(sr.provider_problems(dict(copy.deepcopy(self.noaa), enabled=True), "2027-02-09"), "A4"))   # 점검 기한이 지나면 다시 막힌다


if __name__ == "__main__":
    unittest.main()
