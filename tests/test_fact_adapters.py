"""구조화 Fact 경로 1단계 — `pipeline/adapters/` 시험: 가짜 Provider 파싱 성공·형식 오류 거부·크기·행 수 상한·직접 `urlopen` 호출 금지(AST)·HTML·RSS 파서 없음·오류 메시지에 주소·토큰·응답 본문 없음.
네트워크 없이(주입한 가짜 opener 만) 돈다."""
import ast
import dataclasses
import json
import re
import types
import unittest
from decimal import Decimal
from unittest import mock

import _bootstrap
import fact_helpers as H

from pipeline import facts as F
from pipeline.adapters import base as B
from pipeline.adapters import mock_stats as M

ROOT = _bootstrap.ROOT
ADAPTER_FILES = sorted((ROOT / "pipeline" / "adapters").glob("*.py"))
NOW = H.RETRIEVED_AT


def adapter(**kw):
    return M.MockStatsAdapter(M.MockProvider(), **kw)


def api_access():
    return M.MockProvider().access[0]


def csv_access():
    return M.MockProvider().access[1]


def parse_json(payload, **kw):
    return adapter(**kw).parse(payload, api_access(), NOW, {})


def rows_payload(rows, version="v1"):
    return json.dumps({"api_version": version, "rows": rows}).encode("utf-8")


GOOD_ROW = {"series": "unemp", "region": "R01", "period": "2026-03", "value": 3.5}


class ParseSuccessTest(unittest.TestCase):
    def test_the_mock_response_parses_into_a_valid_bundle(self):
        provider, record, facts = H.mock_bundle()
        self.assertEqual(F.validate_bundle(F.FactBundle((record,), facts)), [])
        self.assertEqual(len(facts), 1 + 6 * 15 + 3 * 15)
        self.assertEqual({f.provider_id for f in facts}, {"mock_stats"})
        self.assertEqual({f.source_record_id for f in facts}, {record.record_id})
        meta = [f for f in facts if f.kind == F.KIND_API_VERSION]
        self.assertEqual([(m.key, m.value, m.as_of) for m in meta], [("meta.api_version", "v1", "2026-04-18")])
        kinds = {f.kind for f in facts if f.kind != F.KIND_API_VERSION}
        self.assertEqual(kinds, {F.KIND_OBSERVATION})

    def test_the_record_remembers_where_and_when_without_secrets(self):
        _provider, record, _facts = H.mock_bundle()
        self.assertEqual((record.provider_id, record.access_kind, record.retrieved_at, record.retention_days), ("mock_stats", "api", NOW, 365))
        self.assertEqual(record.request_url, "https://stats.mock.invalid/v1/series")
        self.assertEqual(len(record.response_hash), 64)
        self.assertIn("tier=2", record.license_snapshot)
        self.assertIn("expires_at=2027-02-07", record.license_snapshot)
        self.assertEqual(F.validate_record(record), [])

    def test_values_units_labels_and_missing_months(self):
        _provider, _record, facts = H.mock_bundle()
        latest = H.obs("R01", "2026-03")
        self.assertEqual((latest.value, latest.unit, latest.label_ko, latest.region_label_ko, latest.region_level, latest.key),
                         (Decimal("3.5"), "%", "실업률", "가상 지역 가", "province", "labour.unemployment_rate"))
        self.assertEqual(H.obs("R01", "2025-01", series="jobs").value, Decimal("1202770"))
        self.assertEqual(H.obs("R01", "2025-01", series="jobs").unit, "명")
        missing = H.obs("R06", "2025-09")
        self.assertIsNone(missing.value)                                  # 비어 있는 칸은 모름 — 0 이 아니다
        self.assertEqual(sum(1 for f in facts if f.value is None), 1)
        self.assertEqual(F.validate_fact(missing), [])

    def test_labels_come_only_from_our_own_table(self):
        _provider, _record, facts = H.mock_bundle()
        allowed_labels = {label for _key, label, _en, _unit in M.SERIES.values()} | {None}
        allowed_regions = {ko for ko, _en in M.REGIONS.values()} | {None}
        for fact in facts:
            self.assertIn(fact.label_ko, allowed_labels)
            self.assertIn(fact.region_label_ko, allowed_regions)

    def test_csv_and_json_give_the_same_values(self):
        provider, adapter_ = M.MockProvider(), adapter()
        op = M.make_mock_opener()
        json_record, json_facts = adapter_.parse(adapter_.fetch(provider.access[0], {}, op), provider.access[0], NOW, {})
        csv_record, csv_facts = adapter_.parse(adapter_.fetch(provider.access[1], {}, op), provider.access[1], NOW, {})
        shape = lambda facts: sorted((f.key, f.region, f.as_of, f.value, f.unit, f.label_ko) for f in facts if f.kind == F.KIND_OBSERVATION)    # noqa: E731
        self.assertEqual(shape(json_facts), shape(csv_facts))
        self.assertEqual(csv_record.access_kind, "csv")
        self.assertNotEqual(json_record.record_id, csv_record.record_id)
        self.assertEqual(sum(1 for f in csv_facts if f.value is None), 1)                  # CSV 의 빈 칸도 모름
        self.assertFalse([f for f in csv_facts if f.kind == F.KIND_API_VERSION])

    def test_params_filter_and_sorted_url(self):
        provider, adapter_ = M.MockProvider(), adapter()
        op, calls = None, []
        op = M.make_mock_opener(calls=calls)
        raw = adapter_.fetch(provider.access[0], {"series": "unemp", "region": "R02"}, op)
        record, facts = adapter_.parse(raw, provider.access[0], NOW, {"series": "unemp", "region": "R02"})
        self.assertEqual(calls, ["https://stats.mock.invalid/v1/series?region=R02&series=unemp"])
        self.assertEqual(record.request_url, calls[0])
        observations = [f for f in facts if f.kind == F.KIND_OBSERVATION]
        self.assertEqual(len(observations), 15)
        self.assertEqual({f.region for f in observations}, {"R02"})

    def test_parsing_is_deterministic_and_the_time_is_an_argument(self):
        raw = M.json_payload()
        first, second = adapter().parse(raw, api_access(), NOW, {}), adapter().parse(raw, api_access(), NOW, {})
        self.assertEqual(first, second)
        later = adapter().parse(raw, api_access(), "2026-04-19T02:30:00Z", {})
        self.assertNotEqual(first[0].record_id, later[0].record_id)
        self.assertNotEqual(first[1][0].fact_id, later[1][0].fact_id)
        shape = lambda facts: [(f.key, f.region, f.as_of, f.value) for f in facts if f.kind == F.KIND_OBSERVATION]      # noqa: E731
        self.assertEqual(shape(first[1]), shape(later[1]))
        self.assertEqual([f.as_of for f in first[1] if f.kind == F.KIND_API_VERSION], ["2026-04-18"])        # 버전 Fact 의 기준일은 수집일이다
        self.assertEqual([f.as_of for f in later[1] if f.kind == F.KIND_API_VERSION], ["2026-04-19"])

    def test_the_dataset_is_fixed_and_shaped_as_documented(self):
        rows = M.dataset_rows()
        self.assertEqual(len(rows), 6 * 15 + 3 * 15)
        self.assertEqual(M.dataset_rows(), rows)
        self.assertEqual(len({(r["series"], r["region"], r["period"]) for r in rows}), len(rows))
        r01 = [float(r["value"]) for r in rows if r["series"] == "unemp" and r["region"] == "R01"]
        self.assertEqual(r01[-1], max(r01))                                # 최신 달에 자료 기간 최고
        r02 = [float(r["value"]) for r in rows if r["series"] == "unemp" and r["region"] == "R02"]
        self.assertEqual(r02[-1], min(r02))
        r03 = [r["value"] for r in rows if r["series"] == "unemp" and r["region"] == "R03"]
        self.assertEqual(r03[-1], r03[-2])                                 # 직전 달과 같음
        self.assertIsNone([r["value"] for r in rows if r["series"] == "unemp" and r["region"] == "R06"][8])


class FetchTest(unittest.TestCase):
    def test_the_network_is_only_the_injected_opener(self):
        seen = []

        def opener(url, *, timeout, max_bytes):
            seen.append((url, timeout, max_bytes))
            return M.json_payload()
        raw = adapter().fetch(api_access(), {"series": "unemp"}, opener)
        self.assertEqual(raw, M.json_payload())
        self.assertEqual(seen, [("https://stats.mock.invalid/v1/series?series=unemp", B.FETCH_TIMEOUT_SECONDS, B.MAX_RESPONSE_BYTES)])

    def test_any_opener_failure_becomes_one_fixed_error_without_the_original_text(self):
        for exc in (OSError("https://stats.mock.invalid/v1/series?api_key=SECRETKEY123 failed"), RuntimeError("token=SECRETTOKEN"), TimeoutError("x"), ValueError("y")):
            with self.subTest(exc=type(exc).__name__):
                def opener(url, *, timeout, max_bytes, exc=exc):
                    raise exc
                with self.assertRaises(B.AdapterError) as caught:
                    adapter().fetch(api_access(), {}, opener)
                self.assertEqual(caught.exception.code, "OPENER_FAILED")
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertIsNone(caught.exception.__cause__)
                self.assertTrue(caught.exception.__suppress_context__)

    def test_the_response_type_and_size_are_checked(self):
        with self.assertRaises(B.AdapterError) as caught:
            adapter().fetch(api_access(), {}, lambda url, *, timeout, max_bytes: "문자열")
        self.assertEqual(caught.exception.code, "BAD_RESPONSE_TYPE")
        with self.assertRaises(B.AdapterError) as caught:
            adapter(max_bytes=100).fetch(api_access(), {}, M.make_mock_opener())
        self.assertEqual(caught.exception.code, "TOO_LARGE")
        self.assertEqual(adapter().fetch(api_access(), {}, lambda url, *, timeout, max_bytes: bytearray(b"[]")), b"[]")

    def test_the_adapter_hands_its_size_limit_to_the_opener(self):
        seen = []
        adapter(max_bytes=4096).fetch(api_access(), {}, lambda url, *, timeout, max_bytes: seen.append(max_bytes) or b"[]")
        self.assertEqual(seen, [4096])

    def test_url_building_rules(self):
        a = adapter()
        self.assertEqual(a.build_url(api_access(), {"region": "R01", "series": "unemp"}), "https://stats.mock.invalid/v1/series?region=R01&series=unemp")
        self.assertEqual(a.build_url(api_access(), None), "https://stats.mock.invalid/v1/series")
        for params in ({"unknown": "x"}, {"api_key": "abc"}, {"series": "a b"}, {"series": "a&b=c"}, {"series": ""}, {"series": "x" * 41}, {"series": 3},
                       {"Series": "unemp"}, {"series": "../x"}, {"series": "a#b"}):
            with self.subTest(params=params):
                with self.assertRaises(B.AdapterError) as caught:
                    a.build_url(api_access(), params)
                self.assertEqual(caught.exception.code, "BAD_PARAMS")

    def test_only_structured_access_kinds_are_used(self):
        for kind in ("rss", "html", "image", "feed", ""):
            with self.subTest(kind=kind):
                access = M.MockAccess(kind, (M.API_HOST,), (M.API_PATH,))
                with self.assertRaises(B.AdapterError) as caught:
                    adapter().build_url(access, {})
                self.assertEqual(caught.exception.code, "NOT_STRUCTURED")
                with self.assertRaises(B.AdapterError):
                    adapter().parse(M.json_payload(), access, NOW, {})
        for kind in ("api", "csv", "dataset"):
            self.assertTrue(adapter().build_url(M.MockAccess(kind, (M.API_HOST,), (M.API_PATH,)), {}))

    def test_bad_access_entries(self):
        for access in (M.MockAccess("api", (), (M.API_PATH,)), M.MockAccess("api", (M.API_HOST,), ()), M.MockAccess("api", ("bad host",), (M.API_PATH,)),
                       M.MockAccess("api", ("user@host.invalid",), (M.API_PATH,)), M.MockAccess("api", (M.API_HOST,), ("v1/series",)),
                       M.MockAccess("api", (M.API_HOST,), ("/v1/../x",)), M.MockAccess("api", (M.API_HOST,), ("/v1/series?x=1",)), M.MockAccess("api", (None,), (M.API_PATH,))):
            with self.subTest(access=access):
                with self.assertRaises(B.AdapterError) as caught:
                    adapter().build_url(access, {})
                self.assertEqual(caught.exception.code, "BAD_ACCESS")

    def test_a_dict_access_entry_works_too(self):
        access = {"kind": "api", "hosts": [M.API_HOST], "paths": [M.API_PATH]}
        self.assertEqual(adapter().build_url(access, {}), "https://stats.mock.invalid/v1/series")


class ParseRejectionTest(unittest.TestCase):
    def reject(self, payload, code, *, access=None, **kw):
        with self.assertRaises(B.AdapterError) as caught:
            adapter(**kw).parse(payload, access or api_access(), NOW, {})
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def test_not_json(self):
        for payload in (b"", b"   ", b"not json", b"<html><body>hello</body></html>", b'<?xml version="1.0"?><rss version="2.0"></rss>', b"{broken",
                        b"\xef\xbb\xbf<html>", b'"just a string"', b"123", b"null"):
            with self.subTest(payload=payload[:20]):
                self.reject(payload, "BAD_JSON")

    def test_bad_encoding(self):
        self.reject(b'{"api_version": "v1", "rows": []}\xff\xfe', "BAD_ENCODING")

    def test_json_traps(self):
        for payload in (b'{"api_version": "v1", "api_version": "v2", "rows": []}', b'{"api_version": "v1", "rows": [NaN]}',
                        b'{"api_version": "v1", "rows": [Infinity]}', b'[' * 5000 + b']' * 5000):
            with self.subTest(payload=payload[:30]):
                self.reject(payload, "BAD_JSON")

    def test_nesting_depth_limit_is_explicit_and_platform_independent(self):
        # 파이썬 재귀 한계는 버전·운영체제마다 달라 5,000겹 글이 리눅스 3.12 에서는 파싱되고 윈도우에서는 RecursionError 였다 — 깊이 상한은 MAX_JSON_DEPTH 하나로 정해진다
        deepest_allowed = b"[" * B.MAX_JSON_DEPTH + b"]" * B.MAX_JSON_DEPTH
        self.assertIsInstance(B.decode_json(deepest_allowed), list)
        for depth in (B.MAX_JSON_DEPTH + 1, 100, 1000, 5000):
            with self.subTest(depth=depth):
                self.reject(b"[" * depth + b"]" * depth, "BAD_JSON")
        too_deep_mixed = b'{"a": ' * (B.MAX_JSON_DEPTH + 1) + b"1" + b"}" * (B.MAX_JSON_DEPTH + 1)
        with self.assertRaises(B.AdapterError) as caught:
            B.decode_json(too_deep_mixed)
        self.assertEqual(caught.exception.code, "BAD_JSON")
        wide = b"[" + b",".join([b"[1, 2]"] * 5000) + b"]"          # 폭이 넓은 것은 깊이와 무관하게 읽힌다
        self.assertEqual(len(B.decode_json(wide)), 5000)

    def test_numbers_with_huge_exponents_are_bad_json_not_an_arithmetic_error(self):
        """S2AFIX D3: Decimal 이 받을 수 없는 아주 큰 지수는 InvalidOperation(ArithmeticError 계열)이 아니라 BAD_JSON 이다 — 어댑터 계약은 '어떤 입력에서도 AdapterError'."""
        for payload in (b"[1e99999999999999999999]", b"[1e-99999999999999999999]", b"[-1e99999999999999999999]", b"[1.5E99999999999999999999]",
                        b'{"api_version": "v1", "rows": [1e99999999999999999999]}'):
            with self.subTest(payload=payload[:32]):
                self.reject(payload, "BAD_JSON")
                with self.assertRaises(B.AdapterError) as caught:
                    B.decode_json(payload)
                self.assertEqual(caught.exception.code, "BAD_JSON")

    def test_a_byte_order_mark_is_tolerated(self):
        record, facts = adapter().parse(b"\xef\xbb\xbf" + rows_payload([GOOD_ROW]), api_access(), NOW, {})
        self.assertEqual(len(facts), 2)

    def test_wrong_shape(self):
        for payload in (b"[]", b"{}", b'{"rows": []}', b'{"api_version": "v1"}', b'{"api_version": 1, "rows": []}',
                        b'{"api_version": "v1", "rows": {}}', b'{"api_version": "v1", "rows": [], "extra": 1}'):
            with self.subTest(payload=payload[:40]):
                self.reject(payload, "BAD_SHAPE")

    def test_bad_rows(self):
        bad = {"행이 사전이 아님": 5, "칸 누락": {"series": "unemp", "region": "R01", "period": "2026-03"},
               "알 수 없는 칸": dict(GOOD_ROW, summary="외부 문장"), "기간이 일 단위": dict(GOOD_ROW, period="2026-03-05"),
               "기간이 연 단위": dict(GOOD_ROW, period="2026"), "기간이 숫자": dict(GOOD_ROW, period=202603), "값이 불리언": dict(GOOD_ROW, value=True),
               "값이 목록": dict(GOOD_ROW, value=[1]), "값이 글자": dict(GOOD_ROW, value="abc"), "값이 지수 표기": dict(GOOD_ROW, value="1e3"),
               "값이 너무 큼": dict(GOOD_ROW, value=10 ** 16)}
        for name, row in bad.items():
            with self.subTest(case=name):
                self.reject(rows_payload([row]), "BAD_ROW")

    def test_unknown_series_and_regions_are_refused_without_echoing_them(self):
        error = self.reject(rows_payload([dict(GOOD_ROW, series="SECRETSERIES")]), "UNKNOWN_SERIES")
        self.assertNotIn("SECRETSERIES", str(error))
        self.assertIn("행 1", str(error))
        error = self.reject(rows_payload([dict(GOOD_ROW), dict(GOOD_ROW, period="2026-02", region="SECRETREGION")]), "UNKNOWN_REGION")
        self.assertNotIn("SECRETREGION", str(error))
        self.assertIn("행 2", str(error))
        self.reject(rows_payload([dict(GOOD_ROW, series=5)]), "UNKNOWN_SERIES")

    def test_duplicate_rows_are_refused(self):
        self.reject(rows_payload([GOOD_ROW, dict(GOOD_ROW, value=3.6)]), "DUPLICATE_ROW")
        self.reject(rows_payload([GOOD_ROW, GOOD_ROW]), "DUPLICATE_ROW")

    def test_size_and_row_limits(self):
        self.reject(M.json_payload(), "TOO_LARGE", max_bytes=1000)
        self.reject(M.json_payload(), "TOO_MANY_ROWS", max_rows=10)
        record, facts = adapter(max_rows=len(M.dataset_rows()) + 1).parse(M.json_payload(), api_access(), NOW, {})
        self.assertEqual(len(facts), 1 + len(M.dataset_rows()))
        self.reject(M.csv_payload(), "TOO_MANY_ROWS", access=csv_access(), max_rows=10)
        self.reject(b"x" * 2000, "TOO_LARGE", max_bytes=1000)
        with self.assertRaises(B.AdapterError):
            adapter().parse("문자열", api_access(), NOW, {})

    def test_too_many_rows_are_refused_before_any_fact_is_made(self):
        """행 수 상한은 Fact 를 만들기 전에 본다 — 상한을 넘는 응답에 일을 시키지 않는다(결과 오류 코드만으로는 구별되지 않는 점이라 호출 수로 확인)."""
        made, real = [], F.Fact.create
        with mock.patch.object(F.Fact, "create", side_effect=lambda *args, **kwargs: made.append(1) or real(*args, **kwargs)):
            with self.assertRaises(B.AdapterError) as caught:
                adapter(max_rows=10).parse(M.json_payload(), api_access(), NOW, {})
            self.assertEqual(caught.exception.code, "TOO_MANY_ROWS")
            self.assertEqual(made, [])
            adapter().parse(rows_payload([GOOD_ROW]), api_access(), NOW, {})       # 상한 안이면 Fact 를 만든다(대조)
            self.assertEqual(len(made), 2)

    def test_the_retrieval_time_must_be_an_iso_instant(self):
        for bad in ("2026-04-18", "2026-04-18T02:30:00", "어제", "", None, 20260418):
            with self.subTest(bad=bad):
                with self.assertRaises(B.AdapterError) as caught:
                    adapter().parse(M.json_payload(), api_access(), bad, {})
                self.assertEqual(caught.exception.code, "BAD_RETRIEVED_AT")

    def test_csv_rejections(self):
        header = b"series,region,period,value\n"
        cases = {"HTML": b"<html><body>x</body></html>", "빈 응답": b"", "머리글 중복": b"series,series,period,value\nunemp,R01,2026-03,3.5\n",
                 "머리글 비어 있음": b"series,,period,value\nunemp,R01,2026-03,3.5\n", "칸 수 부족": header + b"unemp,R01,2026-03\n",
                 "칸 수 초과": header + b"unemp,R01,2026-03,3.5,9\n", "따옴표가 닫히지 않음": header + b'unemp,"R01,2026-03,3.5\n'}
        for name, payload in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(B.AdapterError) as caught:
                    adapter().parse(payload, csv_access(), NOW, {})
                self.assertIn(caught.exception.code, ("BAD_CSV", "BAD_ROW"), name)
        self.reject(header + b"unemp,R01,2026-03,abc\n", "BAD_ROW", access=csv_access())
        self.reject(header + b"unemp,R99,2026-03,3.5\n", "UNKNOWN_REGION", access=csv_access())
        self.reject(header + b"unemp,R01,2026-03,3.5\nunemp,R01,2026-03,3.6\n", "DUPLICATE_ROW", access=csv_access())
        record, facts = adapter().parse(header + b"unemp,R01,2026-03,3.5\nunemp,R02,2026-03,\n", csv_access(), NOW, {})
        self.assertEqual([f.value for f in facts], [Decimal("3.5"), None])

    def test_error_messages_never_carry_urls_queries_tokens_or_response_text(self):
        poison = b'{"api_version": "v1", "rows": [{"series": "unemp", "region": "R01", "period": "2026-03", "value": "https://evil.invalid/?token=SECRETTOKENVALUE"}]}'
        error = self.reject(poison, "BAD_ROW")
        for needle in ("http", "SECRET", "token", "evil", "stats.mock", "?"):
            self.assertNotIn(needle, str(error))
        html = b"<html><script>alert('SECRETSCRIPT')</script></html>"
        self.assertNotIn("SECRETSCRIPT", str(self.reject(html, "BAD_JSON")))
        self.assertEqual(str(B.AdapterError("BAD_ROW", "https://a.invalid/?k=SECRET")), "BAD_ROW: " + B.MESSAGES["BAD_ROW"])
        self.assertEqual(str(B.AdapterError("BAD_ROW", "행 3")), "BAD_ROW: " + B.MESSAGES["BAD_ROW"] + " (행 3)")
        self.assertTrue(str(B.AdapterError("SOMETHING_NEW")).startswith("SOMETHING_NEW"))

    def test_every_error_code_has_a_fixed_sentence_without_urls_or_queries(self):
        for code, text in B.MESSAGES.items():
            with self.subTest(code=code):
                self.assertTrue(text)
                self.assertFalse(re.search(r"http|://|[?&=]", text))


class ProviderGuardTest(unittest.TestCase):
    def test_a_provider_that_is_not_active_cannot_get_an_adapter(self):
        provider = M.MockProvider()
        for over in ({"strict_tier": 3}, {"strict_tier": 4}, {"effective_status": "자동화 제외"}, {"effective_status": "완전 제외"}):
            with self.subTest(over=over):
                with self.assertRaises(B.AdapterError) as caught:
                    M.MockStatsAdapter(dataclasses.replace(provider, **over))
                self.assertEqual(caught.exception.code, "BAD_PROVIDER")
        with self.assertRaises(B.AdapterError):
            M.MockStatsAdapter(types.SimpleNamespace(provider_id="x"))

    def test_the_mock_provider_has_the_registry_shape(self):
        provider = M.MockProvider()
        self.assertIsInstance(provider, F.ProviderLike)
        self.assertEqual(F.provider_problems(provider), [])
        self.assertIsNone(F.provider_active_problem(provider))
        self.assertEqual(provider.provider_id, "mock_stats")
        self.assertTrue(provider.attribution_template)
        self.assertTrue(provider.reader_notes)
        self.assertFalse(re.search(r"\d", " ".join(provider.reader_notes).replace("제3자", "")))      # 독자용으로 승인된 문장에는 숫자가 없다
        self.assertTrue(provider.exceptions)                                                            # 감사 메모 모양의 칸(조립기는 읽지 않는다)

    def test_a_dict_provider_works_for_the_adapter(self):
        provider = dataclasses.asdict(M.MockProvider())
        self.assertEqual(provider["provider_id"], "mock_stats")
        M.MockStatsAdapter(provider)


class AdapterProtocolTest(unittest.TestCase):
    def test_the_structured_adapter_and_any_duck_typed_object_are_adapters(self):
        self.assertIsInstance(adapter(), B.Adapter)

        class Duck:
            def fetch(self, access, params, opener):
                return b""

            def parse(self, raw, access, retrieved_at, params=None):
                return None, []
        self.assertIsInstance(Duck(), B.Adapter)
        self.assertNotIsInstance(object(), B.Adapter)
        self.assertNotIsInstance(types.SimpleNamespace(fetch=lambda *a: b""), B.Adapter)


class MockOpenerTest(unittest.TestCase):
    def test_unknown_addresses_fail_and_overrides_are_served(self):
        op = M.make_mock_opener()
        for url in ("https://other.invalid/v1/series", "https://stats.mock.invalid/nothing", "http://stats.mock.invalid/v1/series", "garbage"):
            with self.subTest(url=url):
                with self.assertRaises(OSError):
                    op(url, timeout=1, max_bytes=10)
        served = M.make_mock_opener(overrides={M.API_PATH: b"<html>x</html>"})("https://stats.mock.invalid/v1/series", timeout=1, max_bytes=10)
        self.assertEqual(served, b"<html>x</html>")

    def test_the_calls_are_recorded(self):
        calls = []
        op = M.make_mock_opener(calls=calls)
        op("https://stats.mock.invalid/v1/series?series=jobs", timeout=1, max_bytes=10)
        self.assertEqual(calls, ["https://stats.mock.invalid/v1/series?series=jobs"])


class StructureOfAdaptersTest(unittest.TestCase):
    """어댑터 코드 자체에 대한 구조 시험: 직접 네트워크 호출·HTML/RSS 파서·시계·난수가 없다."""

    @staticmethod
    def tree(path):
        return ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 10))

    def test_there_are_adapter_files_to_check(self):
        self.assertEqual([p.name for p in ADAPTER_FILES], ["__init__.py", "base.py", "mock_stats.py", "noaa_swpc.py"])

    def test_no_adapter_calls_urlopen_or_imports_a_network_module(self):
        banned = {"urllib", "http", "socket", "ssl", "requests", "httpx", "aiohttp", "ftplib", "smtplib", "xmlrpc", "subprocess"}
        for path in ADAPTER_FILES:
            tree = self.tree(path)
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [(node.module or "").split(".")[0]]
                self.assertFalse(set(names) & banned, f"{path.name}: {names}")
                if isinstance(node, ast.Call):
                    callee = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                    self.assertNotIn(callee, ("urlopen", "urlretrieve", "create_connection", "getaddrinfo", "request", "Popen", "system"), f"{path.name}:{node.lineno}")

    def test_there_is_no_html_or_rss_parser(self):
        banned = {"html", "xml", "bs4", "lxml", "feedparser", "htmlparser", "markdown", "pyquery", "selectolax"}
        for path in ADAPTER_FILES:
            tree = self.tree(path)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    module = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                    for name in module:
                        self.assertNotIn(name.split(".")[0], banned, f"{path.name}: {name}")
                if isinstance(node, ast.ClassDef):
                    self.assertFalse(any(getattr(base, "id", getattr(base, "attr", "")) in ("HTMLParser", "ParserBase") for base in node.bases), node.name)
                if isinstance(node, ast.FunctionDef):
                    self.assertNotRegex(node.name, r"(?i)html|rss|atom|feed|scrape|crawl", f"{path.name}: {node.name}")

    def test_no_clock_randomness_or_environment_in_adapters(self):
        for path in ADAPTER_FILES:
            for node in ast.walk(self.tree(path)):
                if isinstance(node, ast.Import):
                    self.assertFalse({a.name.split(".")[0] for a in node.names} & {"time", "random", "os", "sys", "secrets", "uuid"}, path.name)
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], {"time", "random", "os", "sys", "secrets", "uuid"}, path.name)
                if isinstance(node, ast.Attribute) and node.attr in ("now", "today", "utcnow", "environ", "getenv"):
                    self.fail(f"{path.name}:{node.lineno} {node.attr}")

    def test_the_parse_contract_reads_only_structured_formats(self):
        source = (ROOT / "pipeline" / "adapters" / "base.py").read_text(encoding="utf-8")
        self.assertIn("STRUCTURED_ACCESS_KINDS", source)
        self.assertEqual(F.STRUCTURED_ACCESS_KINDS, frozenset({"api", "csv", "dataset"}))
        self.assertTrue(hasattr(B.StructuredAdapter, "fetch") and hasattr(B.StructuredAdapter, "parse") and hasattr(B.StructuredAdapter, "build_url"))

    def test_the_label_tables_hold_words_not_sentences(self):
        for key, label, label_en, unit in M.SERIES.values():
            self.assertRegex(label, r"\A[가-힣 ]{1,12}\Z")
            self.assertNotRegex(label, r"[.,;:!?]")
            self.assertRegex(label_en, r"\A[a-z ]{1,40}\Z")
            self.assertRegex(unit, F._UNIT_RE.pattern)
            self.assertRegex(key, r"\A[a-z]+\.[a-z_]+\Z")
        for ko, en in M.REGIONS.values():
            self.assertRegex(ko, r"\A[가-힣 ]{1,12}\Z")
            self.assertRegex(en, r"\A[A-Za-z ]{1,24}\Z")
        for text in [M.SOURCE_NAME, M.MockProvider().attribution_template, *M.MockProvider().exceptions]:
            self.assertNotIn("http", text)
        self.assertEqual(M.SOURCE_URL.split("/")[2], M.API_HOST)
        self.assertTrue(M.API_HOST.endswith(".invalid"))



class SrcAccessShapeTest(unittest.TestCase):
    """V-08(b)(d): SRC 의 `paths` 는 허용 접두어(비면 호스트 전체)다 — 어댑터가 자기 끝 경로를 붙인다. 외부 호출 관문의 거부는 `EGRESS_DENIED` 로 그대로 올라간다."""

    class WithSuffix(M.MockStatsAdapter):
        endpoint_suffix = "/v1/series"

    def access(self, paths, hosts=("stats.mock.invalid",)):
        return types.SimpleNamespace(kind="api", hosts=hosts, paths=paths)

    def test_the_path_is_the_allowed_prefix_plus_the_adapters_own_suffix(self):
        a = self.WithSuffix(M.MockProvider())
        self.assertEqual(a.build_url(self.access(("/api",))), "https://stats.mock.invalid/api/v1/series")
        self.assertEqual(a.build_url(self.access(())), "https://stats.mock.invalid/v1/series")                  # 빈 paths(호스트 전체 허용)도 끝 경로가 있으면 쓴다
        self.assertEqual(a.build_url(self.access(("/api",)), {"series": "unemp"}), "https://stats.mock.invalid/api/v1/series?series=unemp")
        self.assertEqual(a.build_url(api_access()), "https://stats.mock.invalid/v1/series/v1/series")         # 접두어 + 끝 경로(접두어가 이미 전체 경로면 어댑터가 끝 경로를 정하지 않는다)

    def test_without_a_suffix_the_old_behaviour_is_kept(self):
        plain = adapter()
        self.assertEqual(plain.build_url(api_access()), "https://stats.mock.invalid/v1/series")
        for paths in ((), (5,), ("api",), ("/a/../b",), ("/a b",), ("",)):
            with self.subTest(paths=paths):
                with self.assertRaises(B.AdapterError) as caught:
                    plain.build_url(self.access(paths))
                self.assertEqual(caught.exception.code, "BAD_ACCESS")                                        # 접두어도 끝 경로도 없으면 주소를 만들 수 없다
        for hosts in ((), (5,), ("bad host",), ("",)):
            with self.subTest(hosts=hosts):
                with self.assertRaises(B.AdapterError) as caught:
                    plain.build_url(self.access(("/v1",), hosts))
                self.assertEqual(caught.exception.code, "BAD_ACCESS")

    def test_a_denial_from_the_gate_keeps_its_reason(self):
        def opener(url, *, timeout, max_bytes):
            raise B.AdapterError("EGRESS_DENIED")
        with self.assertRaises(B.AdapterError) as caught:
            adapter().fetch(api_access(), {}, opener)
        self.assertEqual(caught.exception.code, "EGRESS_DENIED")
        self.assertIn("허용 목록 밖", str(caught.exception))
        self.assertIn("EGRESS_DENIED", B.MESSAGES)

    def test_json_and_csv_are_refused_at_the_same_row_count(self):
        rows = M.dataset_rows()[:20]
        for payload, access in ((M.json_payload(rows), api_access()), (M.csv_payload(rows), csv_access())):
            record, facts = adapter(max_rows=20).parse(payload, access, NOW, {})
            self.assertEqual(len([f for f in facts if f.kind != F.KIND_API_VERSION]), 20)
        for payload, access in ((M.json_payload(M.dataset_rows()[:21]), api_access()), (M.csv_payload(M.dataset_rows()[:21]), csv_access())):
            with self.assertRaises(B.AdapterError) as caught:
                adapter(max_rows=20).parse(payload, access, NOW, {})
            self.assertEqual(caught.exception.code, "TOO_MANY_ROWS")


if __name__ == "__main__":
    unittest.main()
