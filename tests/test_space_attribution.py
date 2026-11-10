"""출처 문구 자동 첨부(R14)와 범위 한정 시험(S2a): 템플릿을 입력으로 받는 순수 함수 `attribution_line`·NOAA 조사 보고서 B안 문구를 시험 입력으로 써서 모든 글에 정확히 한 줄이 붙음·
출처 표시가 조건부(CONDITIONAL)인데 템플릿이 비면 글을 내지 않음·공공영역 주장이 든 문구는 그 기관이 만든 값에만(제3자 필드를 읽은 Fact 는 거절)·여러 모양의 `policy`.
네트워크·시계 없이 돈다."""
import collections
import dataclasses
import inspect
import re
import types
import unittest
from typing import Mapping

import _bootstrap  # noqa: F401
import space_helpers as H
import test_space_recipes as TR

from pipeline import fact_assembler as A
from pipeline import facts as F
from pipeline import recipes as R
from pipeline import recipes_noregion as RN

NAME = "NOAA 우주기상 등급 현황"
DATE = "2026년 11월 10일"
URL = "https://services.swpc.noaa.gov/products/noaa-scales.json"
B_LINE = H.B_TEMPLATE.replace("{title}", TR.TEST_SOURCE_NAME).replace("{date}", DATE)


def provider_with(**changes):
    return H.provider(**changes)


def post_with(name, *, provider_=None, mutate=None):
    return TR.build(name, mutate=mutate, provider_=provider_)


def conditions_line(post):
    lines = [line for line in post.body_markdown.split("\n") if line.startswith(A.ATTRIBUTION_PREFIX)]
    return lines


class AttributionLineTest(unittest.TestCase):
    def test_the_function_takes_the_template_as_an_input(self):
        parameters = inspect.signature(A.attribution_line).parameters
        self.assertEqual(list(parameters), ["template", "title", "date", "url"])
        self.assertEqual([parameters[name].kind for name in ("title", "date", "url")], [inspect.Parameter.KEYWORD_ONLY] * 3)

    def test_only_title_date_and_url_are_replaced_and_the_rest_is_kept_word_for_word(self):
        line = A.attribution_line(H.B_TEMPLATE, title=NAME, date=DATE, url=URL)
        self.assertEqual(line, H.B_TEMPLATE.replace("{title}", NAME).replace("{date}", DATE))
        self.assertTrue(line.startswith("자료: NOAA 우주기상 등급 현황, 미국 NOAA 우주기상예측센터(2026년 11월 10일 열람)."))
        self.assertIn("NOAA 가 만든 이 자료는 미국 연방정부 저작물이라 저작권 보호 대상이 아닙니다.", line)
        self.assertIn("값을 가공해 더한 계산과 설명은 이 블로그의 것이며 NOAA·미국 정부가 인정하거나 보증한 내용이 아닙니다.", line)
        self.assertEqual(A.attribution_line("{url} {url} {title}", title="이름", date=DATE, url=URL), f"{URL} {URL} 이름")
        self.assertEqual(A.attribution_line("  앞  뒤\n줄  ", title="x", date=DATE, url=URL), "앞 뒤 줄")             # 공백은 한 칸으로

    def test_an_empty_template_is_empty_and_an_unusable_one_is_none(self):
        for empty in ("", None):
            self.assertEqual(A.attribution_line(empty, title=NAME, date=DATE, url=URL), "")
        self.assertEqual(A.attribution_line("   ", title=NAME, date=DATE, url=URL), "")
        for bad in ("{unknown} 문구", "{title", "title}", "문구 {{ x }}", "문구 ⟦F:x⟧", "문구 ~ 범위", "{DATE}", "{title} {Date}", "문구 }"):
            with self.subTest(template=bad):
                self.assertIsNone(A.attribution_line(bad, title=NAME, date=DATE, url=URL))
        for not_text in (5, ["a"], {"title": "x"}, b"bytes"):
            self.assertIsNone(A.attribution_line(not_text, title=NAME, date=DATE, url=URL))

    def test_the_report_templates_are_all_usable_inputs(self):
        for template in (H.B_TEMPLATE, "자료: {title}, 미국 NOAA 우주기상예측센터 제공({date} 열람). 이 글의 계산과 해석은 이 블로그가 한 것이며 NOAA·미국 정부의 공식 자료나 보증이 아닙니다.",
                         "출처: {title} (Prepared by the U.S. Dept. of Commerce, NOAA, Space Weather Prediction Center), {date} 열람. 집계와 계산은 이 블로그가 했으며 공식 발표와 다릅니다."):
            line = A.attribution_line(template, title=NAME, date=DATE, url=URL)
            self.assertIsInstance(line, str)
            self.assertNotIn("{", line)
            self.assertIn(DATE, line)


def old_cell_state(provider, name):
    """S2AFIX2 전의 읽기 방식(이름이 동적인 `getattr`)을 글자 그대로 옮긴 기준 구현 — 새 구현이 모든 모양에서 같은 값을 돌려주는지 견주는 데만 쓴다."""
    policy = F.field_of(provider, "policy", None)
    if policy is None or isinstance(policy, (str, bytes, tuple, list)):
        return None
    cell = policy.get(name) if isinstance(policy, Mapping) else getattr(policy, name, None)
    state = F.field_of(cell, "state", None) if cell is not None else None
    return state if isinstance(state, str) else None


def policy_shapes(cell):
    """한 칸(`cell`)을 `attribution` 자리에 넣은 정책의 여러 모양: 사전·사전이 아닌 Mapping·속성 객체·데이터클래스."""
    return {"사전": {"attribution": cell}, "읽기 전용 Mapping": types.MappingProxyType({"attribution": cell}), "순서 사전": collections.OrderedDict(attribution=cell),
            "속성 객체": types.SimpleNamespace(attribution=cell), "데이터클래스": dataclasses.replace(H.Policy(), attribution=cell)}


class PolicyCellReadingTest(unittest.TestCase):
    """S2AFIX2 N1: `_policy_cell_state` 가 이름이 동적인 `getattr` 대신 `F.field_of` 로 정책 칸을 읽는다 — 허용 목록 가지의 외부 접속 등록 시험은 등록 안 된 동적 속성 읽기를 막는다. 읽는 값은 바뀌지 않아야 한다."""
    CELLS = {"사전 ALLOWED": {"state": "ALLOWED"}, "속성 ALLOWED": types.SimpleNamespace(state="ALLOWED"), "데이터클래스 조건부": H.Cell("CONDITIONAL"), "알 수 없음": H.Cell("UNKNOWN", "NOT_READ"),
             "없음": None, "글자": "ALLOWED", "state 없음": {"state": None}, "state 숫자": {"state": 5}, "빈 사전": {}, "소문자": {"state": "allowed"}, "빈 속성 객체": types.SimpleNamespace()}

    def providers(self, policy):
        return {"사전 제공처": {"policy": policy}, "속성 제공처": types.SimpleNamespace(policy=policy), "데이터클래스 제공처": dataclasses.replace(H.NoaaProvider(), policy=policy)}

    def test_every_shape_gives_the_same_value_as_the_dynamic_getattr_version(self):
        checked = 0
        for cell_label, cell in self.CELLS.items():
            for shape_label, policy in policy_shapes(cell).items():
                for provider_label, provider in self.providers(policy).items():
                    for name in ("attribution", "license", "no_such_cell"):                   # 칸이 있는 이름·다른 칸·없는 칸
                        with self.subTest(cell=cell_label, policy=shape_label, provider=provider_label, name=name):
                            self.assertEqual(A._policy_cell_state(provider, name), old_cell_state(provider, name))
                            checked += 1
        self.assertEqual(checked, len(self.CELLS) * 5 * 3 * 3)

    def test_policies_that_are_not_a_mapping_or_an_object_with_cells_give_none_like_before(self):
        for policy in (None, (), [], "text", b"bytes", 5, 2.5, True, frozenset({"attribution"}), object()):
            for provider in self.providers(policy).values():
                with self.subTest(policy=repr(policy)[:30]):
                    self.assertEqual(A._policy_cell_state(provider, "attribution"), old_cell_state(provider, "attribution"))
                    self.assertIsNone(A._policy_cell_state(provider, "attribution"))
        self.assertIsNone(A._policy_cell_state({}, "attribution"))                                   # policy 필드 자체가 없는 사전
        self.assertIsNone(A._policy_cell_state(types.SimpleNamespace(), "attribution"))              # policy 필드 자체가 없는 객체

    def test_the_known_values_are_read(self):
        self.assertEqual(A._policy_cell_state({"policy": {"attribution": {"state": "ALLOWED"}}}, "attribution"), "ALLOWED")
        self.assertEqual(A._policy_cell_state(types.SimpleNamespace(policy=types.SimpleNamespace(attribution=types.SimpleNamespace(state="CONDITIONAL"))), "attribution"), "CONDITIONAL")
        self.assertEqual(A._policy_cell_state(H.NoaaProvider(), "attribution"), H.NoaaProvider().policy.attribution.state)
        self.assertEqual(A._policy_cell_state(types.SimpleNamespace(policy=types.MappingProxyType({"attribution": {"state": "UNKNOWN"}})), "attribution"), "UNKNOWN")     # 사전이 아닌 Mapping 도 get 으로 읽는다
        self.assertTrue(A.attribution_required({"policy": {"attribution": {"state": "UNKNOWN"}}}))
        self.assertFalse(A.attribution_required({"policy": {"attribution": {"state": "ALLOWED"}}}))


class RequiredTest(unittest.TestCase):
    def test_a_conditional_provider_with_an_empty_template_makes_no_post(self):
        for template in ("", "   ", None):
            result = post_with("r04_kp", provider_=provider_with(attribution_template=template))
            with self.subTest(template=template):
                self.assertIsInstance(result, R.Insufficient)
                self.assertEqual(result.code, "ATTRIBUTION_REQUIRED")

    def test_every_subject_gets_the_report_template_as_exactly_one_line(self):
        for name in TR.golden_cases():
            post = post_with(name, provider_=provider_with(attribution_template=H.B_TEMPLATE))
            with self.subTest(post=name):
                self.assertIsInstance(post, A.AssembledPost, post)
                self.assertEqual(conditions_line(post), [A.ATTRIBUTION_PREFIX + B_LINE])
                sources = post.body_markdown.split("## 출처\n")[1]
                self.assertTrue(sources.index("- [") < sources.index(A.ATTRIBUTION_PREFIX))
                self.assertEqual(sources.count("이용 조건"), 1)
                self.assertNotIn("{", post.body_markdown)
                self.assertEqual(A.forbidden_found(post.body_markdown), [])                                # 법적 표시 줄만 금지 표현 검사에서 빠진다(예측센터 이름의 '예측')
                self.assertEqual(A.blocked_found(post.body_markdown), [])
                self.assertEqual(A.post_problems(post, allowed_latin={"NOAA", "SWPC", "GOES", "Kp", "UTC", "nW"}), [])

    def test_the_attribution_line_is_not_part_of_the_numbers_or_the_story(self):
        post = post_with("r05_flares", provider_=provider_with(attribution_template=H.B_TEMPLATE))
        self.assertNotIn("저작권 보호 대상", story_of(post))
        self.assertNotIn("저작권", post.evidence_text)
        self.assertEqual(sorted(set(A.number_tokens(story_of(post))) - A.traceable_numbers(post)), [])

    def test_only_an_explicit_allowed_attribution_cell_lets_an_empty_template_through(self):
        """S2AFIX D8: '모르면 막는다' — 출처 표시 칸이 명시적으로 `ALLOWED`(표시 의무 없음)일 때만 빈 템플릿이 글이 되고, 그 밖(조건부·모름·거절·칸 없음·정책 읽기 불가)은 ATTRIBUTION_REQUIRED."""
        for policy in (dataclasses.replace(H.Policy(), attribution=H.Cell("ALLOWED")), {"attribution": {"state": "ALLOWED"}}, types.SimpleNamespace(attribution=types.SimpleNamespace(state="ALLOWED")),
                       {"attribution": {"state": "ALLOWED"}, "license": {"state": "CONDITIONAL"}}):
            result = post_with("r04_kp", provider_=provider_with(attribution_template="", policy=policy))
            with self.subTest(allowed=policy):
                self.assertIsInstance(result, A.AssembledPost, result)
                self.assertEqual(conditions_line(result), [])
        for policy in ({"attribution": {"state": "CONDITIONAL"}}, types.SimpleNamespace(attribution=types.SimpleNamespace(state="CONDITIONAL")),
                       types.SimpleNamespace(attribution={"state": "CONDITIONAL"}), H.Policy(), dataclasses.replace(H.Policy(), attribution=H.Cell("UNKNOWN", "NOT_READ")),
                       dataclasses.replace(H.Policy(), attribution=H.Cell("DENIED")), (), None, "text", {"other": {"state": "CONDITIONAL"}}, {"attribution": "ALLOWED"}, {"attribution": {"state": None}},
                       {"attribution": {"state": "allowed"}}, {}):
            result = post_with("r04_kp", provider_=provider_with(attribution_template="", policy=policy))
            with self.subTest(blocked=policy):
                self.assertIsInstance(result, R.Insufficient)
                self.assertEqual(result.code, "ATTRIBUTION_REQUIRED")

    def test_attribution_required_reads_only_the_attribution_cell(self):
        self.assertTrue(A.attribution_required(H.NoaaProvider()))
        self.assertTrue(A.attribution_required({"policy": {"attribution": {"state": "CONDITIONAL"}}}))
        self.assertFalse(A.attribution_required({"policy": {"attribution": {"state": "ALLOWED"}}}))
        self.assertFalse(A.attribution_required({"policy": {"attribution": {"state": "ALLOWED"}, "license": {"state": "CONDITIONAL"}}}))          # 다른 칸은 보지 않는다
        self.assertTrue(A.attribution_required({"policy": {"license": {"state": "ALLOWED"}}}))                                                  # 출처 표시 칸이 없으면 모르는 것 — 막는다(S2AFIX D8)
        self.assertTrue(A.attribution_required(types.SimpleNamespace()))
        self.assertTrue(A.attribution_required({}))
        self.assertTrue(A.attribution_required(provider_with(policy=H.Policy(attribution=H.Cell("DENIED")))))
        self.assertTrue(A.attribution_required(provider_with(policy=H.Policy(attribution=H.Cell("UNKNOWN", "NOT_READ")))))

    def test_an_unusable_template_is_refused_even_when_attribution_is_not_conditional(self):
        for template in ("{unknown} 문구", "문구 ~ 끝"):
            for policy in (H.Policy(), (), dataclasses.replace(H.Policy(), attribution=H.Cell("ALLOWED"))):
                result = post_with("r04_kp", provider_=provider_with(attribution_template=template, policy=policy))
                with self.subTest(template=template):
                    self.assertEqual(result.code, "ATTRIBUTION_TEMPLATE_INVALID")

    def test_the_old_mock_provider_still_gets_its_line(self):
        from pipeline.adapters import mock_stats as M
        post = TR.FH.run("R01_time_series", params=TR.FH.R01_PARAMS)
        self.assertEqual(conditions_line(post), [A.ATTRIBUTION_PREFIX + M.MockProvider().attribution_template])
        self.assertTrue(A.attribution_required(M.MockProvider()))                                           # 가짜 Provider 의 정책은 비어 있다 — 모르는 것이라 템플릿이 있어야 하고, 가짜 Provider 는 템플릿이 있어 글이 나온다
        blank = TR.FH.run("R01_time_series", params=TR.FH.R01_PARAMS, provider=dataclasses.replace(M.MockProvider(), attribution_template=""))
        self.assertIsInstance(blank, R.Insufficient)
        self.assertEqual(blank.code, "ATTRIBUTION_REQUIRED")


def story_of(post):
    return A.story_of(post.body_markdown)


# S2a 두 번째 독립 검증의 우회 입력 40개(잡아야 함)와 정상 문구 22개(잡으면 오탐) — 공공영역 표지 검사의 낱말 목록이 이 입력에서 어떻게 움직이는지 못박는다(S2AFIX2 N3)
MUST_FLAG = ("Public Domain", "public\u00a0domain", "public\u200bdomain", "pub\u00adlic domain", "PUBLIC_DOMAIN", "public/domain", "public.domain", "p u b l i c d o m a i n", "publicdomain", "Public-Domain",
             "Ｐｕｂｌｉｃ\u3000Ｄｏｍａｉｎ", "ｐｕｂｌｉｃ-ｄｏｍａｉｎ", "퍼블릭 도메인", "퍼블릭-도메인", "퍼블릭\u200b도메인", "공공 영역", "공공영역", "공공·영역", "공공_영역", "공공영역에 속함",
             "17 U.S.C. 105", "17-USC-105", "17usc105", "17 U.S.C", "연방정부 저작물", "연방 정부 저작물", "연방정부의 저작물", "works of the government", "U.S. Federal Work", "federal work",
             "저작권 보호 대상이 아닙니다", "저작권 보호 대상이 아니다", "저작권 보호를 받지 않는", "저작권이 없습니다", "저작권이 없는 자료", "저작권이 없다", "누구나 자유롭게 쓸 수 있는", "자유롭게 쓸 수 있습니다",
             "자유롭게  쓸  수  있", "자유롭게\n쓸 수 있")
NORMAL = ("자료: {title}, 미국 NOAA 우주기상예측센터({date} 열람). 이 글의 계산과 해석은 이 블로그가 한 것입니다.", "자료: {title}, {date} 열람", "NOAA 가 만든 값을 가공했습니다", "저작권은 제공처에 있습니다 {title}",
          "public data {title}", "공공 기관의 자료 {title}", "이 자료는 공공누리 제1유형 조건에 따라 출처를 밝히고 이용했습니다", "출처를 밝히고 쓸 수 있는 자료입니다", "상업적 이용이 가능한 자료입니다 {title}",
          "자료 이용 조건: 출처 표시", "미국 기상청(NWS) 명칭은 쓰지 않았습니다", "이 블로그는 제공처와 무관합니다", "공공데이터포털에서 받은 자료 {title}", "저작권법에 따라 인용했습니다",
          "공공의 영역에서 쓰이는 자료", "연방 기관의 공개 자료를 정리했습니다", "정부 공개 자료 {title}", "이 자료의 저작권은 공공기관에 있고 출처 표시 조건으로 이용할 수 있습니다",
          "저작권이 있는 자료이므로 출처를 밝힙니다", "저작권 보호 기간이 남아 있습니다", "자유롭게 이용하려면 조건을 확인하세요", "자유로운 이용이 허락되는지 확인하지 않았습니다")


class ScopeTest(unittest.TestCase):
    """공공영역·연방정부 저작물 문구는 그 기관(NOAA)이 만든 값에만 맞는다."""

    def producer(self, value):
        def mutate(facts):
            first = next(f for f in facts if f.key == TR.KP_KEY)
            return [TR.revalue(f, meta=(dict(f.meta, producer=value) if value is not None else {name: v for name, v in f.meta if name != "producer"})) if f is first else f for f in facts]
        return mutate

    def test_a_value_from_a_third_party_blocks_the_public_domain_sentence(self):
        for value in ("SIDC", "NRC", "Penticton", "GFZ"):
            result = post_with("r04_kp", provider_=provider_with(attribution_template=H.B_TEMPLATE), mutate=self.producer(value))
            with self.subTest(producer=value):
                self.assertIsInstance(result, R.Insufficient)
                self.assertEqual(result.code, "ATTRIBUTION_SCOPE_MISMATCH")

    def test_the_informal_endings_and_the_possessive_form_are_found_too(self):
        """S2AFIX2 N3: `저작권 보호 대상이 아니다`(비격식 끝맺음 전부)와 `연방정부의 저작물`(조사 의)이 낱말 목록의 틈이었다. 목록에 `저작권보호대상이아니`·`연방정부의저작물` 을 더해 막는다."""
        for claim in ("저작권 보호 대상이 아니다", "저작권 보호 대상이 아니며 자유로운 자료", "저작권 보호 대상이 아니라서 쓸 수 있다", "저작권 보호 대상이 아니에요", "저작권 보호 대상이 아니고", "저작권  보호  대상이  아니다",
                      "저작권 보호 대상이 아닙니다", "연방정부의 저작물", "연방 정부의 저작물입니다", "연방정부의 저작물이라서", "미국 연방정부의 저작물을 정리했습니다", "연방정부의\u200b저작물"):
            with self.subTest(claim=claim):
                self.assertTrue(A.claims_public_domain(claim), claim)
        for word in ("저작권보호대상이아니", "연방정부의저작물"):
            self.assertIn(word, A.PUBLIC_DOMAIN_CLAIM_WORDS)
        post = TR.build("r04_kp", provider_=provider_with(attribution_template="자료: {title}, {date} 열람. 이 자료는 저작권 보호 대상이 아니다.", own_data_only=False))
        self.assertEqual(post.code, "ATTRIBUTION_SCOPE_MISMATCH")                                       # 비격식 끝맺음도 제3자 값에 붙는 공공영역 문구로 막힌다

    def test_the_second_verifiers_matrix_forty_bypasses_are_caught_and_twenty_two_normal_lines_are_not(self):
        self.assertEqual((len(MUST_FLAG), len(NORMAL)), (40, 22))
        missed = [text for text in MUST_FLAG if A.claims_public_domain(text) is not True]
        self.assertEqual(missed, [])
        flagged = [text for text in NORMAL if A.claims_public_domain(text) is not False]
        self.assertEqual(flagged, [])                                                                      # 정상 문구 오탐 0
        for text in NORMAL:                                                                                # 정상 문구는 제3자 값 글에도 거절되지 않는다
            post = TR.build("r04_kp", provider_=provider_with(attribution_template=text, own_data_only=False))
            with self.subTest(text=text):
                self.assertNotEqual(getattr(post, "code", ""), "ATTRIBUTION_SCOPE_MISMATCH")

    def test_a_value_with_no_producer_cannot_be_shown_to_be_the_agencys_own(self):
        result = post_with("r05_kp_storm", provider_=provider_with(attribution_template=H.B_TEMPLATE), mutate=self.producer(None))
        self.assertEqual(result.code, "ATTRIBUTION_SCOPE_MISMATCH")
        no_meta = lambda facts: [TR.revalue(f, meta={"status": "observed"}) if f.key == TR.KP_KEY else f for f in facts]      # noqa: E731
        self.assertEqual(post_with("r04_kp", provider_=provider_with(attribution_template=H.B_TEMPLATE), mutate=no_meta).code, "ATTRIBUTION_SCOPE_MISMATCH")

    def test_the_claim_is_found_in_the_other_wordings_too(self):
        for claim in ("이 자료는 공공영역에 속합니다. {title} {date}", "자료는 퍼블릭 도메인입니다 {title}", "17 U.S.C. 403 에 따라 {title}", "Public Domain work: {title}", "works of the government {title}",
                      "연방정부 저작물입니다 {title} {date}", "저작권 보호를 받지 않는 자료 {title}",
                      "Public-Domain work: {title}", "public\u2011domain {title}", "PUBLIC.DOMAIN {title}", "퍼블릭-도메인 자료 {title}", "공공·영역에 속합니다 {title}", "17-U.S.C.-403 {title}",
                      "이 자료는 저작권이 없습니다 {title}", "누구나 자유롭게 쓸 수 있는 자료 {title}", "Ｐｕｂｌｉｃ　Ｄｏｍａｉｎ {title}"):                    # S2AFIX D8: 글자·숫자만 남겨 비교한다
            self.assertTrue(A.claims_public_domain(claim), claim)
            result = post_with("r04_kp", provider_=provider_with(attribution_template=claim), mutate=self.producer("SIDC"))
            with self.subTest(claim=claim):
                self.assertEqual(result.code, "ATTRIBUTION_SCOPE_MISMATCH")
        for plain in (H.TEST_TEMPLATE, "자료: {title}, {date} 열람", "NOAA 가 만든 값을 가공했습니다", "", "저작권은 제공처에 있습니다 {title}", "public data {title}", "공공 기관의 자료 {title}"):
            self.assertFalse(A.claims_public_domain(plain), plain)
        for not_text in (None, 5, b"public domain", ["공공영역"]):
            self.assertFalse(A.claims_public_domain(not_text), not_text)                                       # 글자가 아니면 주장을 읽지 않는다

    def test_a_template_without_the_claim_is_not_blocked_by_a_third_party_value(self):
        result = post_with("r04_kp", provider_=provider_with(attribution_template="자료: {title}, 미국 NOAA 우주기상예측센터 제공({date} 열람). 이 글의 계산과 해석은 이 블로그가 한 것입니다."),
                           mutate=self.producer("SIDC"))
        self.assertIsInstance(result, A.AssembledPost, result)

    def test_the_provider_may_say_it_reads_only_its_own_values(self):
        denied = post_with("r04_kp", provider_=provider_with(attribution_template=H.B_TEMPLATE, own_data_only=False))
        self.assertIsInstance(denied, R.Insufficient)
        self.assertEqual(denied.code, "ATTRIBUTION_SCOPE_MISMATCH")
        self.assertIsInstance(post_with("r04_kp", provider_=provider_with(attribution_template=H.B_TEMPLATE, own_data_only=True)), A.AssembledPost)
        for flag in (None, False, "yes", 1, 0, ""):                                                          # S2AFIX D8: 명시적으로 참이 아니면(모르면) 공공영역 주장이 든 문구는 막는다
            result = post_with("r04_kp", provider_=provider_with(attribution_template=H.B_TEMPLATE, own_data_only=flag))
            with self.subTest(own_data_only=flag):
                self.assertIsInstance(result, R.Insufficient)
                self.assertEqual(result.code, "ATTRIBUTION_SCOPE_MISMATCH")
            self.assertIsInstance(post_with("r04_kp", provider_=provider_with(attribution_template=H.TEST_TEMPLATE, own_data_only=flag)), A.AssembledPost)       # 주장이 없는 문구는 이 칸을 보지 않는다
        record, facts = H.parse_value("kp_estimated", H.kp_rows("2026-11-02", 8, partial_last=0))
        as_dict = dataclasses.asdict(provider_with(attribution_template=H.B_TEMPLATE))
        del as_dict["own_data_only"]                                                                         # 칸이 없는 Provider(옛 레지스트리)는 공공영역 주장이 든 문구가 막힌다(SRC2 가 이 칸을 채울 때까지)
        source = A.SourceInfo(as_dict, TR.TEST_SOURCE_NAME, TR.TEST_SOURCE_URL)
        blocked = A.assemble(RN.R04_NOREGION_SERIES, facts, H.TODAY, records=[record], source=source, params={"key": TR.KP_KEY})
        self.assertEqual(blocked.code, "ATTRIBUTION_SCOPE_MISMATCH")
        as_dict["attribution_template"] = H.TEST_TEMPLATE
        plain = A.assemble(RN.R04_NOREGION_SERIES, facts, H.TODAY, records=[record], source=A.SourceInfo(as_dict, TR.TEST_SOURCE_NAME, TR.TEST_SOURCE_URL), params={"key": TR.KP_KEY})
        self.assertIsInstance(plain, A.AssembledPost, plain)

    def test_the_scope_function_reads_the_producer_name_from_the_sentence(self):
        _record, facts = H.parse_fixture("kp_estimated")
        provider = H.NoaaProvider()
        self.assertIsNone(A.attribution_scope_problem(provider, B_LINE, facts))
        self.assertIsNone(A.attribution_scope_problem(provider, "", facts))
        self.assertIsNotNone(A.attribution_scope_problem(provider, B_LINE, [TR.revalue(facts[0], meta={"producer": "SIDC"})]))
        self.assertIsNotNone(A.attribution_scope_problem(provider, B_LINE, [TR.revalue(facts[0], meta=None)]))
        self.assertIsNone(A.attribution_scope_problem(provider, "공공영역이 아닌 문구 SIDC", [TR.revalue(facts[0], meta={"producer": "SIDC"})]))          # 주장이 없으면 검사하지 않는다


class LogoAndImageTest(unittest.TestCase):
    def test_posts_never_use_logos_images_or_nws_names(self):
        for name in TR.golden_cases():
            post = post_with(name, provider_=provider_with(attribution_template=H.B_TEMPLATE))
            text = post.body_markdown
            with self.subTest(post=name):
                self.assertNotRegex(text, r"!\[|<img|\.png|\.svg|\.jpg|\.gif")
                self.assertNotRegex(text, r"(?i)\bNWS\b|national weather service|로고를 쓰|공식 로고")
                self.assertNotRegex(text, r"(?i)endorse|공식 분석|공식 승인|공식 제휴")
                self.assertEqual(len(re.findall(r"\(https://services\.swpc\.noaa\.gov/", text)), 0)             # 시험용 글의 주소는 시험용 가상 주소다


class OfficialNameLatinWordsTest(unittest.TestCase):
    """D-209: 한글 글의 영문은 라벨·단위·`UTC` 에 더해 **공식 데이터 이름의 영문 낱말**(NOAA·SWPC)만 허용한다 — 안내 문장(`reader_notes`)이 그 이름을 부를 수 있고 다른 영문 낱말은 거절된다(변이 U12 가 살아남던 구멍)."""

    def assembled(self, notes):
        record, facts = H.parse_value("kp_estimated", H.kp_rows("2026-11-02", 8, storm_days=(2,), partial_last=3))
        return H.assemble("R04_NOREGION_SERIES", "kp_estimated", facts, record, params={"key": "space_weather.kp_estimated"}, provider_=H.provider(reader_notes=notes))

    def test_a_reader_note_may_use_the_latin_words_of_the_official_name(self):
        post = self.assembled(("NOAA SWPC 자료의 날짜는 협정 세계시 기준입니다",))
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertIn("- 제공처 안내: NOAA SWPC 자료의 날짜는 협정 세계시 기준입니다.", post.body_markdown)
        self.assertEqual(A.post_problems(post, allowed_latin={"NOAA", "SWPC", "Kp", "UTC"}), [])

    def test_a_latin_word_that_is_neither_in_the_name_nor_a_label_is_refused(self):
        result = self.assembled(("FOO 자료의 날짜는 협정 세계시 기준입니다",))
        self.assertIsInstance(result, R.Insufficient)
        self.assertEqual(result.code, "QUALITY_CHECK_FAILED")
        self.assertIn("LANGUAGE", result.detail)


if __name__ == "__main__":
    unittest.main()
