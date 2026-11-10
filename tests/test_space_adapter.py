"""우주날씨(NOAA SWPC) 어댑터 시험 — 표본(실제 응답을 앞 12건 + 뒤 3건으로 줄인 것)과 모양만 같은 가상 응답으로 제품 여섯 개의 파서를 확인한다: 정상 파싱·결측 표기별 처리·상태 꼬리표 보존·제3자 필드를 읽지 않음·
모양 변형(키 이름·배열↔객체·문자열 숫자·시각 형식)·빈 응답·거대 응답·중첩 깊이·중복 시각·미래 시각·정렬 뒤섞임·접근 정보 검사. 어떤 입력에서도 예외는 `AdapterError`(고정 문장) 뿐이다.
네트워크·시계 없이 돈다(주입한 가짜 opener 만)."""
import ast
import copy
import datetime
import hashlib
import json
import re
import unittest
from decimal import Decimal

import _bootstrap
import space_helpers as H

from pipeline import facts as F
from pipeline import fact_topics as T
from pipeline.adapters import base as B
from pipeline.adapters import noaa_swpc as N

ROOT = _bootstrap.ROOT
ALLOWED_CODES = {"BAD_SHAPE", "BAD_JSON", "BAD_ENCODING", "DUPLICATE_ROW", "TOO_MANY_ROWS", "TOO_LARGE", "BAD_ACCESS", "BAD_PARAMS", "NOT_STRUCTURED", "BAD_ROW"}


def fixture(product_id):
    return json.loads(H.fixture_bytes(H.FIXTURE_FILES[product_id]).decode("utf-8"))


def reject(testcase, product_id, value, code="BAD_SHAPE", *, raw=None, **kw):
    """value(파이썬 구조)나 raw(바이트)를 읽게 해 AdapterError(code) 가 나는지 확인하고 오류를 돌려준다."""
    with testcase.assertRaises(B.AdapterError) as caught:
        H.parse_bytes(product_id, raw if raw is not None else H.dumps(value), **kw)
    testcase.assertEqual(caught.exception.code, code, str(caught.exception))
    return caught.exception


class FixtureParseTest(unittest.TestCase):
    def test_every_fixture_parses_into_a_valid_bundle(self):
        expected = {"kp_estimated": 16, "kp_outlook": 16, "scales": 18, "ssn_daily": 3, "ssn_monthly": 6, "xray_flares": 35}
        for product_id in H.FIXTURE_FILES:
            with self.subTest(product=product_id):
                record, facts = H.parse_fixture(product_id)
                self.assertEqual(len(facts), expected[product_id])
                self.assertEqual(F.validate_bundle(F.FactBundle((record,), tuple(facts))), [])
                self.assertEqual({f.provider_id for f in facts}, {"noaa_swpc_json"})
                self.assertEqual({f.source_record_id for f in facts}, {record.record_id})
                self.assertEqual({f.meta_value("producer") for f in facts}, {"NOAA"})
                self.assertTrue(all(f.meta_value("status") for f in facts))
                self.assertEqual(record.request_url, N.product_url(product_id))
                self.assertEqual((record.access_kind, record.provider_id, record.retrieved_at), ("api", "noaa_swpc_json", H.RETRIEVED_AT))
                self.assertIn("tier=1", record.license_snapshot)

    def test_kp_estimated_values_times_and_threshold(self):
        _record, facts = H.parse_fixture("kp_estimated")
        kp = [f for f in facts if f.key == "space_weather.kp_estimated"]
        self.assertEqual(len(kp), 15)
        self.assertEqual((kp[0].value, kp[0].unit, kp[0].as_of, kp[0].label_ko, kp[0].kind), (Decimal("0.67"), "Kp", "2026-11-03T00:00:00Z", "NOAA 추정 Kp", F.KIND_OBSERVATION))
        self.assertEqual((kp[-1].value, kp[-1].as_of), (Decimal("2.0"), "2026-11-09T21:00:00Z"))
        self.assertEqual([f.as_of for f in kp], sorted(f.as_of for f in kp))
        self.assertEqual([f.meta_value("stations") for f in kp][:2], ["6", "6"])
        self.assertEqual(kp[-1].meta_value("stations"), "8")
        self.assertEqual({f.meta_value("status") for f in kp}, {"observed"})
        threshold = [f for f in facts if f.key == "space_weather.kp_storm_threshold"]
        self.assertEqual(len(threshold), 1)
        self.assertEqual((threshold[0].value, threshold[0].unit, threshold[0].as_of, threshold[0].meta_value("status")), (Decimal("5"), "Kp", "2026-11-10", "reference"))
        self.assertEqual(threshold[0].kind, F.KIND_NUMBER)

    def test_kp_outlook_keeps_observed_estimated_and_predicted_apart(self):
        _record, facts = H.parse_fixture("kp_outlook")
        measured = [f for f in facts if f.key == "space_weather.kp_estimated"]
        outlook = [f for f in facts if f.key == "space_weather.kp_outlook"]
        self.assertEqual((len(measured), len(outlook)), (12, 3))
        self.assertEqual({f.meta_value("status") for f in measured}, {"observed"})
        self.assertEqual({f.meta_value("status") for f in outlook}, {"predicted"})
        self.assertEqual(outlook[0].label_ko, "NOAA Kp 예보")
        self.assertEqual([f.as_of for f in outlook], ["2026-11-12T18:00:00Z", "2026-11-12T21:00:00Z", "2026-11-13T00:00:00Z"])

    def test_the_three_states_each_land_where_they_belong_and_labels_follow_them(self):
        rows = [{"time_tag": "2026-11-09T18:00:00", "kp": 5.33, "observed": "observed", "noaa_scale": "G1"},
                {"time_tag": "2026-11-09T21:00:00", "kp": 4.67, "observed": "observed", "noaa_scale": None},
                {"time_tag": "2026-11-10T00:00:00", "kp": 2.33, "observed": "estimated", "noaa_scale": None},
                {"time_tag": "2026-11-10T03:00:00", "kp": 5.0, "observed": "estimated", "noaa_scale": "G1"},
                {"time_tag": "2026-11-10T06:00:00", "kp": 6.67, "observed": "predicted", "noaa_scale": "G3"}]
        _record, facts = H.parse_value("kp_outlook", rows)
        by_key = {}
        for fact in facts:
            by_key.setdefault(fact.key, []).append(fact)
        self.assertEqual([(f.as_of, f.value, f.meta_value("status")) for f in by_key["space_weather.kp_estimated"]],
                         [("2026-11-09T18:00:00Z", Decimal("5.33"), "observed"), ("2026-11-09T21:00:00Z", Decimal("4.67"), "observed")])
        self.assertEqual([(f.as_of, f.meta_value("status")) for f in by_key["space_weather.kp_outlook"]],
                         [("2026-11-10T00:00:00Z", "estimated"), ("2026-11-10T03:00:00Z", "estimated"), ("2026-11-10T06:00:00Z", "predicted")])
        self.assertEqual([(f.value, f.meta_value("status")) for f in by_key["space_weather.interval_scale_observed"]], [(Decimal(1), "observed")])
        self.assertEqual([(f.value, f.meta_value("status")) for f in by_key["space_weather.interval_scale_outlook"]], [(Decimal(1), "estimated"), (Decimal(3), "predicted")])
        for fact in by_key["space_weather.interval_scale_outlook"]:
            self.assertEqual(fact.label_ko, "NOAA 지자기 폭풍 등급 예보")

    def test_scales_observed_and_forecast_days(self):
        _record, facts = H.parse_fixture("scales")
        by_key = {}
        for fact in facts:
            by_key.setdefault(fact.key, []).append(fact)
        self.assertEqual(sorted(by_key), sorted("space_weather." + name for name in (
            "daily_scale_radio", "daily_scale_radiation", "daily_scale_geomagnetic", "outlook_scale_geomagnetic", "outlook_prob_radio_minor", "outlook_prob_radio_major", "outlook_prob_radiation")))
        radio = by_key["space_weather.daily_scale_radio"]
        self.assertEqual([(f.as_of, f.value, f.unit, f.meta_value("status")) for f in radio], [("2026-11-09", Decimal(0), "단계", "observed"), ("2026-11-10", Decimal(0), "단계", "observed")])
        minor = by_key["space_weather.outlook_prob_radio_minor"]
        self.assertEqual([(f.as_of, f.value, f.unit, f.meta_value("status")) for f in minor],
                         [("2026-11-10", Decimal(60), "%", "predicted"), ("2026-11-11", Decimal(60), "%", "predicted"), ("2026-11-12", Decimal(60), "%", "predicted")])
        self.assertEqual([f.value for f in by_key["space_weather.outlook_prob_radio_major"]], [Decimal(15)] * 3)
        self.assertEqual([f.value for f in by_key["space_weather.outlook_prob_radiation"]], [Decimal(15)] * 3)

    def test_sunspot_windows_keep_only_the_recent_rows_but_check_all_of_them(self):
        _record, daily = H.parse_fixture("ssn_daily")
        self.assertEqual([(f.as_of, f.value, f.unit) for f in daily], [("2026-11-07", Decimal(93), "개"), ("2026-11-08", Decimal(72), "개"), ("2026-11-09", Decimal(94), "개")])
        _record, monthly = H.parse_fixture("ssn_monthly")
        observed = [f for f in monthly if f.key == "space_weather.sunspot_monthly_swpc"]
        smoothed = [f for f in monthly if f.key == "space_weather.sunspot_monthly_smoothed_swpc"]
        self.assertEqual([(f.as_of, f.value) for f in observed], [("2026-08", Decimal("81.32")), ("2026-09", Decimal("68.73")), ("2026-10", Decimal("61.71"))])
        self.assertEqual([f.value for f in smoothed], [None, None, None])                                 # -1.0 은 값 없음(모름)이다
        self.assertEqual({f.meta_value("quality") for f in monthly}, {"provisional"})
        rows = fixture("ssn_daily")
        rows[0]["swpc_ssn"] = 12.5                                                                         # 오래된 행의 이상도 거절한다(모양이 바뀐 것)
        reject(self, "ssn_daily", rows)

    def test_flare_classes_flux_and_floors(self):
        _record, facts = H.parse_fixture("xray_flares")
        classes = [f for f in facts if f.key == "space_weather.xray_flare_class"]
        fluxes = [f for f in facts if f.key == "space_weather.xray_flare_flux"]
        floors = {f.key.rsplit("_", 1)[1]: f for f in facts if "xray_class_floor" in f.key}
        self.assertEqual((len(classes), len(fluxes), sorted(floors)), (15, 15, ["a", "b", "c", "m", "x"]))
        self.assertEqual([floors[letter].value for letter in "abcmx"], [Decimal(10), Decimal(100), Decimal(1000), Decimal(10000), Decimal(100000)])
        self.assertEqual((classes[0].value, classes[0].kind, classes[0].unit, fluxes[0].value, fluxes[0].unit), ("B4.8", F.KIND_CLASS_CODE, None, Decimal(480), "nW/㎡"))
        self.assertEqual({f.meta_value("satellite") for f in classes + fluxes}, {"18"})
        self.assertEqual({f.meta_value("status") for f in floors.values()}, {"reference"})
        self.assertEqual([f.as_of for f in classes], [f.as_of for f in fluxes])

    def test_flux_follows_the_class_exactly(self):
        events = [("2026-11-04T06:15:00Z", "A1.0"), ("2026-11-04T07:15:00Z", "B9.9"), ("2026-11-04T08:15:00Z", "C10.5"), ("2026-11-04T09:15:00Z", "M5.0"), ("2026-11-04T10:15:00Z", "X28.0")]
        _record, facts = H.parse_value("xray_flares", H.flare_rows(events))
        fluxes = {f.as_of: f.value for f in facts if f.key == "space_weather.xray_flare_flux"}
        self.assertEqual(list(fluxes.values()), [Decimal(10), Decimal(990), Decimal(10500), Decimal(50000), Decimal(2800000)])

    def test_parsing_is_deterministic_and_the_time_is_an_argument(self):
        raw = H.fixture_bytes(H.FIXTURE_FILES["kp_estimated"])
        first, second = H.parse_bytes("kp_estimated", raw), H.parse_bytes("kp_estimated", raw)
        self.assertEqual(first, second)
        later = H.parse_bytes("kp_estimated", raw, retrieved_at="2026-11-10T02:10:00Z")
        self.assertNotEqual(first[0].record_id, later[0].record_id)
        shape = lambda facts: [(f.key, f.as_of, f.value, f.meta) for f in facts if f.key.endswith("kp_estimated")]      # noqa: E731
        self.assertEqual(shape(first[1]), shape(later[1]))
        self.assertEqual([f.as_of for f in first[1] if f.key.endswith("threshold")], ["2026-11-10"])

    def test_the_utc_day_of_a_retrieval_time_with_an_offset_is_used(self):
        raw = H.fixture_bytes(H.FIXTURE_FILES["kp_estimated"])
        _record, facts = H.parse_bytes("kp_estimated", raw, retrieved_at="2026-11-10T09:10:00+09:00")           # 같은 순간의 한국 시각
        self.assertEqual([f.as_of for f in facts if f.key.endswith("threshold")], ["2026-11-10"])
        _record, facts = H.parse_bytes("kp_estimated", raw, retrieved_at="2026-11-10T23:30:00-05:00")           # UTC 로는 이튿날
        self.assertEqual([f.as_of for f in facts if f.key.endswith("threshold")], ["2026-11-11"])


class FixtureFilesTest(unittest.TestCase):
    def test_the_fixtures_are_small_public_samples_with_provenance(self):
        provenance = json.loads((H.FIXTURE_DIR / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(set(provenance["files"]), set(H.FIXTURE_FILES.values()))
        for name, entry in provenance["files"].items():
            data = H.fixture_bytes(name)                                                                   # 줄 끝 LF 로 맞춘 바이트 — 윈도우 autocrlf 사본에서도 같은 해시
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
                self.assertNotIn(b"http", data.lower())                                                    # 본문에 링크 글자가 없다(출처는 이 파일과 파일 이름에)
                value = json.loads(data.decode("utf-8"))
                self.assertLessEqual(len(value), 15)
                self.assertIn(entry["product"], H.FIXTURE_FILES)
                self.assertEqual(H.FIXTURE_FILES[entry["product"]], name)
                self.assertTrue(N.PRODUCTS[entry["product"]].path.endswith(entry["path"]))
                self.assertNotRegex(json.dumps(entry, ensure_ascii=False), r"(?i)https?://|www\.|~")
        self.assertEqual({p.name for p in H.FIXTURE_DIR.iterdir()}, set(H.FIXTURE_FILES.values()) | {"provenance.json"})


class MissingValueTest(unittest.TestCase):
    def test_each_missing_marker_becomes_a_value_that_is_not_there_never_zero(self):
        rows = H.kp_rows("2026-11-08", 1)
        rows[0]["Kp"], rows[1]["Kp"], rows[2]["Kp"] = None, -1, Decimal("-1.0")
        rows[2]["Kp"] = -1.0
        _record, facts = H.parse_value("kp_estimated", rows)
        kp = [f for f in facts if f.key == "space_weather.kp_estimated"]
        self.assertEqual([f.value for f in kp[:3]], [None, None, None])
        self.assertTrue(all(f.value is not None for f in kp[3:]))
        self.assertEqual(F.validate_bundle(F.FactBundle((_record,), tuple(facts))), [])
        ssn = H.ssn_daily_rows("2026-11-09", 3)
        ssn[0]["swpc_ssn"], ssn[1]["swpc_ssn"] = -1, None
        _record, facts = H.parse_value("ssn_daily", ssn)
        self.assertEqual([f.value for f in facts][:2], [None, None])
        monthly = H.ssn_monthly_rows("2026-10", 12)
        _record, facts = H.parse_value("ssn_monthly", monthly)
        self.assertIn(None, [f.value for f in facts if f.key.endswith("smoothed_swpc")])

    def test_the_string_zero_is_a_value_and_null_is_the_gap(self):
        obj = H.scales_object()
        self.assertEqual(obj["0"]["G"]["Scale"], "0")
        _record, facts = H.parse_value("scales", obj)
        zero = [f for f in facts if f.key == "space_weather.daily_scale_geomagnetic"]
        self.assertEqual([f.value for f in zero], [Decimal(0), Decimal(0)])                              # 문자열 '0' = 등급 0(없음)
        obj["0"]["G"]["Scale"] = None
        _record, facts = H.parse_value("scales", obj)
        self.assertEqual([f.value for f in facts if f.key == "space_weather.daily_scale_geomagnetic"], [Decimal(0), None])
        obj = H.scales_object()
        obj["2"]["R"]["MinorProb"] = None
        _record, facts = H.parse_value("scales", obj)
        minor = [f.value for f in facts if f.key == "space_weather.outlook_prob_radio_minor"]
        self.assertEqual(minor, [Decimal(60), None, Decimal(60)])

    def test_records_that_are_absent_are_not_filled_in(self):
        rows = H.ssn_daily_rows("2026-11-09", 10, gaps=(3, 4))
        _record, facts = H.parse_value("ssn_daily", rows)
        self.assertEqual(len(facts), 8)
        days = [f.as_of for f in facts]
        self.assertNotIn("2026-11-03", days)
        self.assertTrue(all(f.value is not None for f in facts))

    def test_a_flare_without_its_class_or_satellite_is_refused_not_guessed(self):
        rows = H.flare_rows([("2026-11-04T06:15:00Z", "C1.0"), ("2026-11-04T07:15:00Z", "C1.2")])
        for field, bad in (("max_class", None), ("satellite", None), ("satellite", -1)):
            broken = copy.deepcopy(rows)
            broken[1][field] = bad
            with self.subTest(field=field, bad=bad):
                reject(self, "xray_flares", broken)


class WhitelistTest(unittest.TestCase):
    THIRD_PARTY = ("ssn", "smoothed_ssn", "f10.7", "smoothed_f10.7")

    def test_third_party_fields_are_never_read_or_made_into_facts(self):
        rows = H.ssn_monthly_rows("2026-10", 12)
        poison = [{"nested": [1, 2, {"x": "SECRET"}]}, "not a number", True, [], -999999999999, "NaN"]
        for index, row in enumerate(rows):
            for name in self.THIRD_PARTY:
                row[name] = poison[(index + len(name)) % len(poison)]
        record, facts = H.parse_value("ssn_monthly", rows)
        self.assertEqual({f.key for f in facts}, {"space_weather.sunspot_monthly_swpc", "space_weather.sunspot_monthly_smoothed_swpc"})
        clean, clean_facts = H.parse_value("ssn_monthly", H.ssn_monthly_rows("2026-10", 12, third_party=False))
        self.assertEqual([(f.key, f.as_of, f.value, f.meta) for f in facts], [(f.key, f.as_of, f.value, f.meta) for f in clean_facts])
        for fact in facts:
            self.assertNotIn("ssn", fact.key.replace("sunspot", ""))
            self.assertEqual(fact.meta_value("producer"), "NOAA")

    def test_the_third_party_columns_may_be_missing_but_no_other_column_is_tolerated(self):
        rows = H.ssn_monthly_rows("2026-10", 8, third_party=False)
        H.parse_value("ssn_monthly", rows)
        rows[2]["predicted_swpc_ssn"] = 70.0
        reject(self, "ssn_monthly", rows)
        rows = H.ssn_monthly_rows("2026-10", 8)
        del rows[3]["observed_swpc_ssn"]
        reject(self, "ssn_monthly", rows)

    def test_no_adapter_source_names_a_third_party_value_as_something_it_reads(self):
        source = (ROOT / "pipeline" / "adapters" / "noaa_swpc.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        subscripts = [node.slice.value for node in ast.walk(tree) if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)]
        for name in self.THIRD_PARTY:
            self.assertNotIn(name, subscripts)                      # row["ssn"] 같은 읽기가 없다(이름 집합에 올라 있을 뿐)
        self.assertNotIn("max_xrlong", subscripts)


class ShapeRejectionTest(unittest.TestCase):
    def test_not_json_or_not_the_expected_container(self):
        for product_id in H.FIXTURE_FILES:
            for raw in (b"", b"   ", b"not json", b"<html>x</html>", b'"text"', b"123", b"null", b"{broken", b"[1e99999999999999999999]", b"[-1e-99999999999999999999]"):       # 마지막 둘: 아주 큰 지수(S2AFIX D3)
                with self.subTest(product=product_id, raw=raw[:12]):
                    reject(self, product_id, None, "BAD_JSON", raw=raw)
            container = {} if product_id != "scales" else []
            with self.subTest(product=product_id, shape="wrong container"):
                reject(self, product_id, container)
            with self.subTest(product=product_id, shape="empty"):
                reject(self, product_id, [] if product_id != "scales" else {})
            with self.subTest(product=product_id, shape="rows are not objects"):
                reject(self, product_id, [5] if product_id != "scales" else {"a": 1})

    def test_the_curated_variants_that_must_be_refused(self):
        kp = fixture("kp_estimated")
        cases = {"kp_estimated": [], "kp_outlook": [], "scales": [], "ssn_daily": [], "ssn_monthly": [], "xray_flares": []}

        def vary(product_id, label, change):
            value = fixture(product_id)
            change(value)
            cases[product_id].append((label, value))

        vary("kp_estimated", "시간대가 붙은 시각", lambda v: v[0].update(time_tag="2026-11-03T00:00:00Z"))
        vary("kp_estimated", "공백으로 나뉜 시각", lambda v: v[0].update(time_tag="2026-11-03 00:00:00"))
        vary("kp_estimated", "없는 달", lambda v: v[0].update(time_tag="2026-13-03T00:00:00"))
        vary("kp_estimated", "24시", lambda v: v[0].update(time_tag="2026-11-03T24:00:00"))
        vary("kp_estimated", "Kp 범위 밖", lambda v: v[0].update(Kp=12.0))
        vary("kp_estimated", "Kp 가 3분의 1 단위가 아님", lambda v: v[0].update(Kp=2.5))
        vary("kp_estimated", "Kp 9.33(9 를 넘는 3분의 1 값)", lambda v: v[0].update(Kp=9.33))                # 상한 9 와 3분의 1 표(0–9.00) 두 방벽을 함께 풀어도 걸리게(S2AFIX D14)
        vary("kp_estimated", "Kp 9.67", lambda v: v[0].update(Kp=9.67))
        vary("kp_outlook", "Kp 9.33(예보 파일)", lambda v: v[0].update(kp=9.33))
        vary("kp_estimated", "Kp 가 글자", lambda v: v[0].update(Kp="2.0"))
        vary("kp_estimated", "Kp 가 불리언", lambda v: v[0].update(Kp=True))
        vary("kp_estimated", "키 이름이 바뀜", lambda v: v[0].update({"kp": v[0].pop("Kp")}))
        vary("kp_estimated", "칸이 빠짐", lambda v: v[0].pop("a_running"))
        vary("kp_estimated", "모르는 칸", lambda v: v[0].update(extra=1))
        vary("kp_estimated", "아직 시작하지 않은 구간", lambda v: v[0].update(time_tag="2026-11-11T00:00:00"))
        vary("kp_estimated", "배열의 배열(옛 형식)", lambda v: v.__setitem__(slice(None), [["time_tag", "Kp"], ["2026-11-03T00:00:00", "0.67"]]))
        vary("kp_outlook", "상태 낱말", lambda v: v[0].update(observed="forecast"))
        vary("kp_outlook", "등급 라벨", lambda v: v[0].update(noaa_scale="G9"))
        vary("kp_outlook", "등급 라벨이 숫자", lambda v: v[0].update(noaa_scale=1))
        vary("kp_outlook", "예보가 관측보다 앞", lambda v: (v[0].update(observed="predicted"), v[1].update(observed="observed")))
        vary("kp_outlook", "관측이 미래", lambda v: v[0].update(observed="observed", time_tag="2026-11-20T00:00:00"))
        vary("kp_outlook", "관측만 있는 파일의 미래 구간", lambda v: ([row.update(observed="observed") for row in v], v[-1].update(time_tag="2026-11-20T00:00:00")))      # 순서 검사에 안 걸려 미래 검사만이 막는다
        vary("kp_outlook", "너무 먼 과거", lambda v: v[0].update(time_tag="2019-01-01T00:00:00"))
        vary("kp_outlook", "너무 먼 미래", lambda v: v[-1].update(observed="predicted", time_tag="2026-12-20T00:00:00"))                 # 예보는 3일치 — 30일을 넘는 미래는 정상 자료가 아니다
        vary("kp_outlook", "관측 파일의 키 이름", lambda v: v[0].update({"Kp": v[0].pop("kp")}))
        vary("scales", "키가 빠짐", lambda v: v.pop("3"))
        vary("scales", "모르는 키", lambda v: v.update({"4": v["3"]}))
        vary("scales", "숫자로 바뀐 등급", lambda v: v["0"]["G"].update(Scale=1))
        vary("scales", "범위 밖 등급", lambda v: v["0"]["G"].update(Scale="7"))
        vary("scales", "범위 밖 확률", lambda v: v["1"]["R"].update(MinorProb="101"))
        vary("scales", "날짜가 거꾸로", lambda v: v["2"].update(DateStamp="2026-11-01"))
        vary("scales", "오래된 파일", lambda v: [v[name].update(DateStamp="2026-10-01") for name in v])
        vary("scales", "시각 모양", lambda v: v["0"].update(TimeStamp="24:00:00"))
        vary("scales", "R 의 칸이 빠짐", lambda v: v["0"]["R"].pop("MinorProb"))
        vary("scales", "G 가 객체가 아님", lambda v: v["0"].update(G="0"))
        vary("scales", "하루가 아닌 날짜(시각 형식)", lambda v: v["3"].update(DateStamp="2026-11-12T00:00:00Z"))               # 날짜 순서·신선도 검사에 안 걸려 하루 단위 검사만이 막는다
        vary("ssn_daily", "자정이 아닌 시각", lambda v: v[0].update(Obsdate="1996-03-12T12:00:00"))
        vary("ssn_daily", "소수", lambda v: v[-1].update(swpc_ssn=94.5))
        vary("ssn_daily", "범위 밖", lambda v: v[-1].update(swpc_ssn=1001))
        vary("ssn_daily", "음수", lambda v: v[-1].update(swpc_ssn=-5))
        vary("ssn_daily", "모르는 칸", lambda v: v[0].update(extra=1))
        vary("ssn_daily", "미래 날짜", lambda v: v[-1].update(Obsdate="2026-11-12T00:00:00"))
        vary("ssn_monthly", "필수 칸이 없음", lambda v: v[0].pop("time-tag"))
        vary("ssn_monthly", "월 형식", lambda v: v[0].update({"time-tag": "1749-13"}))
        vary("ssn_monthly", "미래 달", lambda v: v[-1].update({"time-tag": "2026-12"}))
        vary("ssn_monthly", "이번 달(진행 중)", lambda v: v[-1].update({"time-tag": "2026-11"}))
        vary("ssn_monthly", "값이 글자", lambda v: v[-1].update(observed_swpc_ssn="61.7"))
        vary("xray_flares", "등급 문자", lambda v: v[0].update(max_class="Z1.0"))
        vary("xray_flares", "등급에 수가 없음", lambda v: v[0].update(max_class="M"))
        vary("xray_flares", "Z 가 없는 시각", lambda v: v[0].update(max_time="2026-11-03T06:15:00"))
        vary("xray_flares", "칸이 빠짐", lambda v: v[0].pop("end_class"))
        vary("xray_flares", "위성 번호가 글자", lambda v: v[0].update(satellite="GOES"))
        vary("xray_flares", "위성 번호 0", lambda v: v[0].update(satellite=0))
        vary("xray_flares", "미래 시각", lambda v: v[-1].update(max_time="2026-11-20T00:00:00Z"))
        self.assertGreaterEqual(sum(len(items) for items in cases.values()), 45)
        for product_id, items in cases.items():
            for label, value in items:
                with self.subTest(product=product_id, case=label):
                    reject(self, product_id, value)
        self.assertEqual(kp[0]["time_tag"], "2026-11-03T00:00:00")                        # 불러온 표본은 건드리지 않았다

    def test_every_single_field_change_is_either_a_good_parse_or_a_fixed_refusal(self):
        """표본의 첫 행·마지막 행의 모든 칸을 지우고·이름을 바꾸고·형을 바꿔도 AdapterError(허용 코드) 아니면 정상 파싱이다 — 다른 예외는 없다."""
        swaps = ("x", True, [], {}, None, 0, -1, 1e99, "2026-11-03T00:00:00Z", "")
        made = 0
        for product_id in H.FIXTURE_FILES:
            base = fixture(product_id)
            rows = [(base, key) for key in base] if isinstance(base, dict) else [(base[index], key) for index in (0, -1) for key in base[index]]
            for target, key in rows:
                variants = [("지움", lambda t, k: t.pop(k)), ("이름", lambda t, k: t.update({k + "_x": t.pop(k)}))] + [(f"형 {n}", (lambda s: lambda t, k: t.update({k: s}))(swap)) for n, swap in enumerate(swaps)]
                for label, change in variants:
                    value = copy.deepcopy(base)
                    holder = value if isinstance(base, dict) else value[0 if target is base[0] else -1]
                    change(holder, key)
                    made += 1
                    try:
                        record, facts = H.parse_bytes(product_id, H.dumps(value))
                    except B.AdapterError as error:
                        self.assertIn(error.code, ALLOWED_CODES, (product_id, key, label))
                    else:
                        self.assertEqual(F.validate_bundle(F.FactBundle((record,), tuple(facts))), [], (product_id, key, label))
        self.assertGreater(made, 500)

    def test_error_messages_never_carry_values_addresses_or_response_text(self):
        poison = "SECRETVALUE"
        read_field = {"kp_estimated": "Kp", "kp_outlook": "kp", "ssn_daily": "swpc_ssn", "ssn_monthly": "observed_swpc_ssn", "xray_flares": "max_class"}
        for product_id in H.FIXTURE_FILES:
            value = fixture(product_id)
            if product_id == "scales":
                value["0"]["G"]["Scale"] = poison
            else:
                value[0][read_field[product_id]] = poison
            with self.assertRaises(B.AdapterError) as caught:
                H.parse_bytes(product_id, H.dumps(value))
            text = str(caught.exception)
            for needle in (poison, "http", "services", "noaa", "swpc", "?"):
                self.assertNotIn(needle.lower(), text.lower(), product_id)
        error = reject(self, "kp_estimated", None, "BAD_JSON", raw=b"<html><script>SECRETSCRIPT</script></html>")
        self.assertNotIn("SECRET", str(error))


class OrderDuplicateFutureTest(unittest.TestCase):
    def test_shuffled_rows_give_the_same_facts(self):
        for product_id, make in (("kp_estimated", lambda: H.kp_rows("2026-11-02", 4)), ("ssn_daily", lambda: H.ssn_daily_rows("2026-11-09", 30)),
                                 ("ssn_monthly", lambda: H.ssn_monthly_rows("2026-10", 24)),
                                 ("xray_flares", lambda: H.flare_rows([("2026-11-04T06:15:00Z", "C1.2"), ("2026-11-05T07:00:00Z", "M1.1"), ("2026-11-06T08:00:00Z", "B2.0"), ("2026-11-07T09:30:00Z", "C4.4")]))):
            ordered = make()
            shuffled = list(reversed(ordered))
            shuffled = shuffled[1::2] + shuffled[0::2]
            first, second = H.parse_value(product_id, ordered), H.parse_value(product_id, shuffled)
            shape = lambda result: [(f.key, f.as_of, f.value, f.unit, f.label_ko, f.meta) for f in result[1]]      # noqa: E731
            with self.subTest(product=product_id):
                self.assertEqual(shape(first), shape(second))                      # 응답 바이트가 달라 수집 기록 id 는 다르지만 Fact 의 내용과 순서는 같다
                self.assertEqual([f.as_of for f in first[1]], sorted(f.as_of for f in first[1] if f.kind != F.KIND_NUMBER) + [f.as_of for f in first[1] if f.kind == F.KIND_NUMBER])

    def test_the_same_time_twice_is_refused(self):
        cases = {"kp_estimated": H.kp_rows("2026-11-08", 1), "ssn_daily": H.ssn_daily_rows("2026-11-09", 5), "ssn_monthly": H.ssn_monthly_rows("2026-10", 12),
                 "xray_flares": H.flare_rows([("2026-11-04T06:15:00Z", "C1.2"), ("2026-11-05T07:00:00Z", "M1.1")]),
                 "kp_outlook": H.kp_rows("2026-11-08", 1, keys="outlook")}
        for product_id, rows in cases.items():
            twice = rows + [copy.deepcopy(rows[1])]
            with self.subTest(product=product_id):
                reject(self, product_id, twice, "DUPLICATE_ROW")
                changed = copy.deepcopy(rows[1])
                key = next(name for name in changed if name not in ("time_tag", "Obsdate", "time-tag", "max_time", "observed", "noaa_scale"))
                changed[key] = rows[1][key] if not isinstance(rows[1][key], (int, float)) else rows[1][key] + 1
                reject(self, product_id, rows + [changed], "DUPLICATE_ROW")          # 같은 시각에 다른 값이어도 거절한다

    def test_future_observed_rows_are_refused_but_forecast_rows_may_be_ahead(self):
        rows = H.kp_rows("2026-11-09", 1)
        rows.append({"time_tag": "2026-11-10T03:00:00", "Kp": 1.0, "a_running": 4, "station_count": 8})           # 수집 01:10Z — 아직 시작하지 않은 구간
        reject(self, "kp_estimated", rows)
        near = H.kp_rows("2026-11-09", 1)
        near.append({"time_tag": "2026-11-10T01:15:00", "Kp": 1.0, "a_running": 4, "station_count": 8})              # 시계 어긋남 여유(15분) 안
        H.parse_value("kp_estimated", near)
        ahead = [{"time_tag": "2026-11-09T21:00:00", "kp": 2.0, "observed": "observed", "noaa_scale": None}, {"time_tag": "2026-11-10T00:00:00", "kp": 2.33, "observed": "estimated", "noaa_scale": None},
                 {"time_tag": "2026-11-12T21:00:00", "kp": 3.0, "observed": "predicted", "noaa_scale": None}]
        H.parse_value("kp_outlook", ahead)
        ahead[0]["time_tag"] = "2026-11-10T21:00:00"
        reject(self, "kp_outlook", ahead)
        flares = H.flare_rows([("2026-11-04T06:15:00Z", "C1.2"), ("2026-11-10T01:30:00Z", "C1.3")])
        reject(self, "xray_flares", flares)
        daily = H.ssn_daily_rows("2026-11-10", 5)
        reject(self, "ssn_daily", daily)                                                                             # 오늘 날짜의 일별 값은 아직 없다
        H.parse_value("ssn_daily", H.ssn_daily_rows("2026-11-09", 5))

    def test_a_retrieval_time_that_is_not_an_instant_is_refused(self):
        for bad in ("2026-11-10", "2026-11-10T01:10:00", "어제", "", None, 20261110):
            with self.subTest(bad=bad):
                with self.assertRaises(B.AdapterError) as caught:
                    H.parse_fixture("kp_estimated", retrieved_at=bad)
                self.assertEqual(caught.exception.code, "BAD_RETRIEVED_AT")


class LimitsTest(unittest.TestCase):
    def test_too_large_too_deep_and_too_many_rows(self):
        raw = H.fixture_bytes(H.FIXTURE_FILES["kp_estimated"])
        with self.assertRaises(B.AdapterError) as caught:
            H.parse_bytes("kp_estimated", raw, max_bytes=100)
        self.assertEqual(caught.exception.code, "TOO_LARGE")
        with self.assertRaises(B.AdapterError) as caught:
            H.parse_bytes("kp_estimated", b" " * (B.MAX_RESPONSE_BYTES + 1))
        self.assertEqual(caught.exception.code, "TOO_LARGE")
        for depth in (B.MAX_JSON_DEPTH + 1, 100, 1000, 5000):
            reject(self, "kp_estimated", None, "BAD_JSON", raw=b"[" * depth + b"]" * depth)
        reject(self, "ssn_monthly", None, "BAD_JSON", raw=b'[{"a": ' * (B.MAX_JSON_DEPTH + 1) + b"1" + b"}]" * (B.MAX_JSON_DEPTH + 1))
        reject(self, "kp_estimated", H.kp_rows("2026-11-01", 8)[:], "TOO_MANY_ROWS", max_rows=10)
        reject(self, "xray_flares", H.flare_rows([(f"2026-11-04T{hour:02d}:15:00Z", "C1.0") for hour in range(12)]), "TOO_MANY_ROWS", max_rows=5)

    def test_the_raw_row_limit_is_checked_before_any_fact_is_made(self):
        made = []
        real = F.Fact.create

        def counting(*args, **kwargs):
            made.append(1)
            return real(*args, **kwargs)
        rows = H.kp_rows("2026-11-01", 8)
        F.Fact.create = counting
        try:
            reject(self, "kp_estimated", rows, "TOO_MANY_ROWS", max_rows=10)
            self.assertEqual(made, [])
            H.parse_value("kp_estimated", rows[:8])
            self.assertGreater(len(made), 0)
        finally:
            F.Fact.create = real

    def test_the_daily_sunspot_file_with_thousands_of_rows_still_parses(self):
        rows = H.ssn_daily_rows("2026-11-09", 9904, gaps=(5, 700, 701))
        record, facts = H.parse_value("ssn_daily", rows)
        self.assertEqual(len(facts), 400)                                         # 최근 400일 — 빠진 날은 오래된 쪽에만 있어 400개가 모두 있다
        self.assertEqual(facts[-1].as_of, "2026-11-09")
        self.assertEqual(facts[0].as_of, str(datetime.date(2026, 11, 9) - datetime.timedelta(days=399)))
        self.assertEqual(F.validate_bundle(F.FactBundle((record,), tuple(facts))), [])
        reject(self, "ssn_daily", H.ssn_daily_rows("2026-11-09", 150), "TOO_MANY_ROWS", max_rows=100)

    def test_the_monthly_window_is_sixty_months_with_six_provisional(self):
        rows = H.ssn_monthly_rows("2026-10", 3334)
        _record, facts = H.parse_value("ssn_monthly", rows)
        observed = [f for f in facts if f.key == "space_weather.sunspot_monthly_swpc"]
        self.assertEqual((len(facts), len(observed), observed[0].as_of, observed[-1].as_of), (120, 60, "2021-11", "2026-10"))
        self.assertEqual([f.as_of for f in observed if f.meta_value("quality") == "provisional"], [f"2026-{month:02d}" for month in range(5, 11)])


class AccessTest(unittest.TestCase):
    def test_the_url_is_fixed_by_the_product_and_the_network_is_only_the_injected_opener(self):
        seen = []

        def opener(url, *, timeout, max_bytes):
            seen.append((url, timeout, max_bytes))
            return H.fixture_bytes(H.FIXTURE_FILES["scales"])
        a = H.adapter("scales")
        raw = a.fetch(H.access_of(), {}, opener)
        self.assertEqual(seen, [("https://services.swpc.noaa.gov/products/noaa-scales.json", B.FETCH_TIMEOUT_SECONDS, B.MAX_RESPONSE_BYTES)])
        record, _facts = a.parse(raw, H.access_of(), H.RETRIEVED_AT, {})
        self.assertEqual(record.request_url, seen[0][0])
        self.assertEqual(N.product_url("scales"), seen[0][0])

    def test_every_product_url_is_inside_the_registrys_six_files(self):
        self.assertEqual(sorted(N.PRODUCTS), sorted(H.FIXTURE_FILES))
        self.assertEqual({N.product_url(p) for p in N.PRODUCTS}, {"https://services.swpc.noaa.gov" + path for path in H.ALL_PATHS})
        for path in H.ALL_PATHS:
            self.assertTrue(path.startswith(("/products/", "/json/")))
            self.assertNotEqual(path.rstrip("/"), "/json")                       # 넓은 접두어가 아니라 파일 경로다

    def test_a_host_or_path_outside_the_product_is_refused(self):
        raw = H.fixture_bytes(H.FIXTURE_FILES["kp_estimated"])
        a = H.adapter("kp_estimated")
        for access in (H.Access("api", ("other.example.invalid",), H.ALL_PATHS), H.Access("api", (), H.ALL_PATHS), H.Access("api", ("services.swpc.noaa.gov.evil.invalid",), H.ALL_PATHS),
                       H.Access("api", (N.HOST,), ("/json/goes/primary/xray-flares-7-day.json",)), H.Access("api", (N.HOST,), (5,)),
                       H.Access("csv", (N.HOST,), H.ALL_PATHS), H.Access("dataset", (N.HOST,), H.ALL_PATHS)):
            with self.subTest(access=access):
                with self.assertRaises(B.AdapterError) as caught:
                    a.parse(raw, access, H.RETRIEVED_AT, {})
                self.assertIn(caught.exception.code, ("BAD_ACCESS", "NOT_STRUCTURED"))
        for access in (H.Access("rss", (N.HOST,), H.ALL_PATHS), H.Access("html", (N.HOST,), H.ALL_PATHS)):
            with self.assertRaises(B.AdapterError) as caught:
                a.build_url(access)
            self.assertEqual(caught.exception.code, "NOT_STRUCTURED")
        self.assertEqual(a.build_url(H.Access("api", (N.HOST,), ("/products/",))), N.product_url("kp_estimated"))          # 접두어가 파일을 덮으면 된다
        self.assertEqual(a.build_url(H.Access("api", (N.HOST,), ())), N.product_url("kp_estimated"))                       # 빈 paths(호스트 전체)는 어댑터가 파일을 정한다
        self.assertEqual(a.build_url({"kind": "api", "hosts": [N.HOST], "paths": list(H.ALL_PATHS)}), N.product_url("kp_estimated"))

    def test_query_variables_are_not_allowed_at_all(self):
        a = H.adapter("kp_estimated")
        for params in ({"x": "1"}, {"api_key": "abc"}, {"series": "unemp"}):
            with self.assertRaises(B.AdapterError) as caught:
                a.build_url(H.access_of(), params)
            self.assertEqual(caught.exception.code, "BAD_PARAMS")

    def test_unknown_product_and_inactive_provider_are_refused(self):
        for bad in ("nope", "", None, 5, "KP_ESTIMATED"):
            with self.assertRaises(B.AdapterError) as caught:
                N.NoaaSwpcAdapter(H.NoaaProvider(), bad)
            self.assertEqual(caught.exception.code, "BAD_PARAMS")
        for changes in ({"strict_tier": 3}, {"effective_status": "참고 전용"}, {"enabled": False}):
            with self.subTest(changes=changes):
                with self.assertRaises(B.AdapterError) as caught:
                    H.adapter("kp_estimated", provider=H.provider(**changes))
                self.assertEqual(caught.exception.code, "BAD_PROVIDER")

    def test_any_opener_failure_becomes_one_fixed_error(self):
        for exc in (OSError("https://services.swpc.noaa.gov/x?key=SECRET failed"), RuntimeError("token=SECRET"), TimeoutError("x")):
            def opener(url, *, timeout, max_bytes, exc=exc):
                raise exc
            with self.assertRaises(B.AdapterError) as caught:
                H.adapter("kp_estimated").fetch(H.access_of(), {}, opener)
            self.assertEqual(caught.exception.code, "OPENER_FAILED")
            self.assertNotIn("SECRET", str(caught.exception))

        def denied(url, *, timeout, max_bytes):
            raise B.AdapterError("EGRESS_DENIED")
        with self.assertRaises(B.AdapterError) as caught:
            H.adapter("kp_estimated").fetch(H.access_of(), {}, denied)
        self.assertEqual(caught.exception.code, "EGRESS_DENIED")

    def test_the_adapter_follows_the_adapter_protocol(self):
        self.assertIsInstance(H.adapter("kp_estimated"), B.Adapter)
        self.assertIsInstance(H.NoaaProvider(), F.ProviderLike)
        self.assertEqual(F.provider_problems(H.NoaaProvider()), [])
        self.assertIsNone(F.provider_active_problem(H.NoaaProvider()))


class LabelTableTest(unittest.TestCase):
    def test_labels_are_words_from_our_own_table_and_pass_the_topic_allow_list(self):
        domain = T.DOMAINS["space_weather"]
        for key, (label_ko, label_en, unit) in N.LABELS.items():
            with self.subTest(key=key):
                self.assertRegex(label_ko, F._LABEL_RE.pattern)
                self.assertRegex(label_en, F._LABEL_EN_RE.pattern)
                self.assertNotRegex(label_ko + label_en, r"[.,;:!?0-9]")
                self.assertEqual(T.blocked_in(label_ko), [])
                self.assertEqual(T.blocked_in(label_en, english=True), [])
                if unit is not None:
                    self.assertIn(unit, domain.units)
                    self.assertIn(unit, F.UNIT_TABLE)
                    self.assertRegex(unit, F._UNIT_RE.pattern)
                self.assertTrue(all(word in domain.label_words for word in T.words(label_ko)), label_ko)
                self.assertTrue(all(word in domain.key_words for word in re.split(r"[._]+", key) if word), key)
        _record, facts = H.parse_fixture("scales")
        for fact in facts:
            self.assertIsNone(T.fact_problem(fact, ("space_weather",)), fact.key)
        for product_id in ("kp_estimated", "kp_outlook", "ssn_daily", "ssn_monthly", "xray_flares"):
            for fact in H.parse_fixture(product_id)[1]:
                self.assertIsNone(T.fact_problem(fact, ("space_weather",)), (product_id, fact.key))

    def test_the_vocabulary_has_no_blocked_pair(self):
        words = sorted(T.DOMAINS["space_weather"].label_words)
        for first in words:
            for second in words:
                self.assertEqual(T.blocked_in(f"{first} {second}"), [], (first, second))

    def test_there_is_no_text_taken_from_the_provider_in_the_label_table(self):
        for label_ko, label_en, _unit in N.LABELS.values():
            self.assertLessEqual(len(label_ko), 24)
            self.assertNotRegex(label_ko, r"(?i)logo|로고|nws|national weather")
            self.assertNotRegex(label_en, r"(?i)logo|nws|national weather")
        for product in N.PRODUCTS.values():
            self.assertRegex(product.source_name, r"\A[가-힣A-Za-z0-9 ·.,&'\-]{1,80}\Z")
            self.assertNotRegex(product.source_name, r"(?i)logo|로고|nws")


class StructureTest(unittest.TestCase):
    NEW = ("pipeline/adapters/noaa_swpc.py", "pipeline/recipes_noregion.py", "pipeline/fact_candidates.py")

    def test_the_new_modules_import_nothing_that_can_reach_an_ai_client_or_the_network(self):
        banned_roots = {"generator", "blogger_generator", "google", "openai", "anthropic", "urllib", "http", "socket", "ssl", "requests", "subprocess", "importlib", "os", "sys", "time", "random", "pathlib", "logging"}
        banned_pipeline = {"llm", "run", "main_image", "publishers", "edits", "draft_flow", "drafts", "state", "gates", "notify", "inbox", "topics", "stubs", "profiles"}
        for rel in self.NEW:
            tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = [(alias.name.split(".")[0], alias.name) for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    roots = [((node.module or "").split(".")[0], node.module or "")]
                    if node.module == "pipeline":
                        for alias in node.names:
                            self.assertNotIn(alias.name, banned_pipeline, rel)
                else:
                    continue
                for root, full in roots:
                    self.assertNotIn(root, banned_roots, f"{rel}: {full}")
                    if root == "pipeline":
                        self.assertNotIn(full.split(".")[1] if "." in full else "", banned_pipeline, f"{rel}: {full}")

    def test_no_dynamic_call_clock_randomness_file_or_environment_in_the_new_modules(self):
        banned_names = {"getattr", "setattr", "exec", "eval", "compile", "__import__", "open", "print", "input", "globals", "locals", "vars"}
        banned_attributes = {"now", "today", "utcnow", "sleep", "urlopen", "getenv", "system", "Popen", "read", "write", "mkdir", "unlink"}
        for rel in self.NEW:
            text = (ROOT / rel).read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        self.assertNotIn(node.func.attr, banned_attributes, f"{rel}:{node.lineno}")
                    elif isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, banned_names, f"{rel}:{node.lineno}")
            self.assertNotRegex(text, r"(?i)\b(?:gemini|openai|anthropic|generate_content|llm|genai|prompt)\b", rel)       # AI 를 부르거나 가리키는 이름이 없다
            self.assertNotRegex(re.sub(r'"""[\s\S]*?"""', "", text), r"(?i)https?://[a-z0-9.-]+\.[a-z]{2,}", rel)          # 주소 글자는 호스트 이름 상수와 스킴을 이어 만든다(링크 글자를 통째로 두지 않는다)

    def test_the_new_modules_define_no_entry_that_writes_or_reads_files(self):
        for rel in self.NEW:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"\b(?:read_text|write_text|read_bytes|write_bytes|Path|json\.load|json\.dump)\b", rel)


if __name__ == "__main__":
    unittest.main()
