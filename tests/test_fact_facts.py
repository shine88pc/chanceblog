"""구조화 Fact 경로 1단계 — `pipeline/facts.py` 시험: 불변성·해시 결정성·검증기·모름≠0·단위 불일치·직렬화 왕복·참조 렌더링(자리 수·반올림 경계·음수·퍼센트·큰 수·날짜)·UntracedNumber.
네트워크·시계·난수 없이 돈다."""
import dataclasses
import datetime
import json
import os
import subprocess
import sys
import types
import unittest
from decimal import Decimal

import _bootstrap
import fact_helpers as H

from pipeline import facts as F

ROOT = _bootstrap.ROOT
RECORD_ID = "s0123456789abcdef"


def sample_record(**over):
    values = dict(provider_id="mock_stats", access_kind="api", request_url="https://stats.mock.invalid/v1/series?series=unemp",
                  retrieved_at="2026-04-18T02:30:00Z", response_hash="a" * 64, license_snapshot="tier=2; status=자동화 가능", retention_days=365)
    values.update(over)
    return F.SourceRecord.create(**values)


def sample_fact(record=None, **over):
    values = dict(provider_id="mock_stats", source_record_id=(record or sample_record()).record_id, kind=F.KIND_OBSERVATION,
                  key="labour.unemployment_rate", value="3.25", unit="%", as_of="2026-03", region="R01", region_level="province",
                  region_label_ko="가상 지역 가", region_label_en="Mock Region A", label_ko="실업률", label_en="unemployment rate")
    values.update(over)
    return F.Fact.create(**values)


class ImmutabilityTest(unittest.TestCase):
    def test_value_objects_are_frozen(self):
        record, fact = sample_record(), sample_fact()
        derived = F.DerivedFact.create("F01_change", (fact.fact_id,), "0.3", "%p", as_of="2026-03")
        for obj, name in ((record, "provider_id"), (fact, "value"), (fact, "fact_id"), (derived, "value"), (derived, "formula_id")):
            with self.subTest(obj=type(obj).__name__, field=name):
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(obj, name, "x")

    def test_replace_makes_a_new_object_and_the_old_id_no_longer_matches(self):
        fact = sample_fact()
        changed = dataclasses.replace(fact, value=Decimal("9.9"))
        self.assertEqual(fact.value, Decimal("3.25"))
        self.assertTrue(F.validate_fact(fact) == [])
        self.assertIn("`fact_id` 이(가) 내용과 맞지 않음", F.validate_fact(changed))

    def test_objects_are_hashable_and_equal_by_content(self):
        self.assertEqual(sample_fact(), sample_fact())
        self.assertEqual(len({sample_fact(), sample_fact()}), 1)
        self.assertIsInstance(F.DerivedFact.create("F01_change", ("f" + "0" * 16,), "1", "%p").input_fact_ids, tuple)

    def test_the_input_ids_of_a_derived_fact_are_a_tuple_even_if_given_a_list(self):
        derived = F.DerivedFact.create("F08_mean", ["f" + "1" * 16, "f" + "2" * 16], "2", "%")
        self.assertEqual(derived.input_fact_ids, ("f" + "1" * 16, "f" + "2" * 16))


class HashDeterminismTest(unittest.TestCase):
    def test_same_content_same_id_and_the_formats(self):
        a, b = sample_fact(), sample_fact()
        self.assertEqual(a.fact_id, b.fact_id)
        self.assertRegex(a.fact_id, r"\Af[0-9a-f]{16}\Z")
        self.assertRegex(sample_record().record_id, r"\As[0-9a-f]{16}\Z")
        self.assertRegex(F.DerivedFact.create("F01_change", (a.fact_id,), "1", "%p").fact_id, r"\Ad[0-9a-f]{16}\Z")

    def test_every_content_field_changes_the_id(self):
        base = sample_fact()
        changes = {"provider_id": "other_stats", "kind": F.KIND_NUMBER, "key": "labour.other", "value": "3.26", "unit": "명", "as_of": "2026-02",
                   "region": "R02", "region_level": "city", "region_label_ko": "가상 지역 나", "region_label_en": "Mock Region B",
                   "label_ko": "고용률", "label_en": "employment rate", "source_record_id": "s" + "f" * 16}
        for name, value in changes.items():
            with self.subTest(field=name):
                self.assertNotEqual(sample_fact(**{name: value}).fact_id, base.fact_id)

    def test_numerically_equal_values_have_one_id(self):
        self.assertEqual(sample_fact(value="3.50").fact_id, sample_fact(value="3.5").fact_id)
        self.assertEqual(sample_fact(value=Decimal("3.5")).fact_id, sample_fact(value=3.5).fact_id)
        self.assertEqual(F.canonical_number(Decimal("100")), "100")
        self.assertEqual(F.canonical_number(Decimal("1E+2")), "100")
        self.assertEqual(F.canonical_number(Decimal("-0.0")), "0")
        self.assertEqual(F.canonical_number(Decimal("0.5000")), "0.5")

    def test_the_id_does_not_depend_on_dict_order(self):
        forward = {"provider_id": "p", "source_record_id": RECORD_ID, "kind": "NUMBER", "key": "a.b", "value": Decimal("1"), "unit": "%"}
        backward = dict(reversed(list(forward.items())))
        self.assertEqual(F.compute_fact_id(forward), F.compute_fact_id(backward))
        self.assertEqual(F.canonical_json({"b": 1, "a": [2, {"d": 1, "c": 2}]}), '{"a":[2,{"c":2,"d":1}],"b":1}')

    def test_ids_and_bundle_bytes_do_not_depend_on_the_hash_seed(self):
        code = (
            "import sys\nsys.path.insert(0, sys.argv[1])\nsys.path.insert(0, sys.argv[1] + '/tests')\n"
            "import fact_helpers as H\nfrom pipeline import facts as F\n"
            "provider, record, facts = H.mock_bundle()\n"
            "print(record.record_id)\nprint(F.sha256_hex(F.dumps_bundle(F.FactBundle((record,), facts)).encode('utf-8')))\n"
            "print(','.join(f.fact_id for f in facts[:5]))\n")
        outputs = set()
        for seed in ("0", "1", "4242"):
            env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONUTF8="1")
            done = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", code, str(ROOT)], capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(done.returncode, 0, done.stderr[-400:])
            outputs.add(done.stdout)
        self.assertEqual(len(outputs), 1, outputs)

    def test_bundle_json_is_identical_for_any_input_order(self):
        record, facts = sample_record(), [sample_fact(value=str(v)) for v in range(5)]
        forward = F.dumps_bundle(F.FactBundle((record,), tuple(facts)))
        backward = F.dumps_bundle(F.FactBundle((record,), tuple(reversed(facts))))
        self.assertEqual(forward, backward)


class ValidatorTest(unittest.TestCase):
    def test_a_good_record_fact_and_derived_have_no_problems(self):
        record = sample_record()
        fact = sample_fact(record)
        derived = F.DerivedFact.create("F01_change", (fact.fact_id,), "0.3", "%p", as_of="2026-03", region="R01", key=fact.key, region_level="province")
        self.assertEqual(F.validate_record(record), [])
        self.assertEqual(F.validate_fact(fact), [])
        self.assertEqual(F.validate_derived(derived), [])
        self.assertEqual(F.validate_bundle(F.FactBundle((record,), (fact,), (derived,))), [])

    def test_every_kind_has_a_valid_example_and_a_bad_one(self):
        good = {F.KIND_NUMBER: ("12", "개"), F.KIND_OBSERVATION: ("3.5", "%"), F.KIND_PRICE: ("1500", "원"),
                F.KIND_DATE: ("2026-03-05", None), F.KIND_EVENT_START: ("2026-05-01", None), F.KIND_EVENT_END: ("2026-05-03", None),
                F.KIND_LAW_EFFECTIVE: ("2026-07-01", None), F.KIND_DATETIME: ("2026-03-05T09:30:00Z", None),
                F.KIND_REGION: ("KR-11", None), F.KIND_OFFICIAL_STATUS: ("경보", None), F.KIND_CLASS_CODE: ("A1", None), F.KIND_API_VERSION: ("v2", None)}
        self.assertEqual(set(good), set(F.FACT_KINDS))
        for kind, (value, unit) in good.items():
            with self.subTest(kind=kind):
                fact = F.Fact.create("mock_stats", RECORD_ID, kind, "meta.example", value, unit=unit,
                                     as_of="2026-03" if kind in F.NUMERIC_KINDS else None, label_ko="낱말" if kind in F.NUMERIC_KINDS else None)
                self.assertEqual(F.validate_fact(fact), [])
        bad = {F.KIND_DATE: "2026-03", F.KIND_EVENT_START: "내일", F.KIND_DATETIME: "2026-03-05T09:30:00", F.KIND_REGION: "줄\n바꿈",
               F.KIND_OFFICIAL_STATUS: "<b>x</b>", F.KIND_API_VERSION: ""}
        for kind, value in bad.items():
            with self.subTest(bad_kind=kind):
                fact = F.Fact.create("mock_stats", RECORD_ID, kind, "meta.example", value)
                self.assertTrue(F.validate_fact(fact), kind)

    def test_fact_problems_are_found_one_by_one(self):
        record = sample_record()
        cases = {
            "소스 기록 id 모양": dict(source_record_id="s12"),
            "알려진 종류가 아님": dict(kind="SENTENCE"),
            "키 형식": dict(key="Labour Rate"),
            "단위 없음": dict(unit=None),
            "단위 모양": dict(unit="10%"),
            "기준일 없음": dict(as_of=None),
            "기준일 모양": dict(as_of="2026/03"),
            "낱말 라벨 없음": dict(label_ko=None),
            "라벨에 숫자": dict(label_ko="소비자물가지수2020"),
            "라벨이 문장": dict(label_ko="이 지표는 실업자를 경제활동인구로 나눈 값입니다."),
            "라벨이 너무 김": dict(label_ko="가" * 25),
            "라벨에 표시 문자": dict(label_ko="실업률⟦F:x⟧"),
            "라벨에 중괄호": dict(label_ko="실업률{x}"),
            "라벨에 물결표": dict(label_ko="실업률~"),
            "라벨에 줄바꿈": dict(label_ko="실업\n률"),
            "지역 이름에 표시 문자": dict(region_label_ko="지역|가"),
            "지역은 있고 수준 없음": dict(region_level=None),
            "영어 라벨에 숫자": dict(label_en="rate 2020"),
        }
        for name, over in cases.items():
            with self.subTest(case=name):
                self.assertTrue(F.validate_fact(sample_fact(record, **over)), name)

    def test_a_value_that_is_too_large_is_refused_when_the_fact_is_made(self):
        with self.assertRaises(F.FactFormatError):
            sample_fact(value="1" + "0" * 16)
        self.assertEqual(F.validate_fact(sample_fact(value="9" * 14)), [])

    def test_a_text_fact_cannot_carry_a_unit_and_a_numeric_fact_cannot_hide_its_value_type(self):
        self.assertTrue(F.validate_fact(F.Fact.create("mock_stats", RECORD_ID, F.KIND_API_VERSION, "meta.v", "v1", unit="%")))
        fact = sample_fact()
        self.assertTrue(F.validate_fact(dataclasses.replace(fact, value="3.5")))             # 숫자 종류에 글자 값
        self.assertTrue(F.validate_fact(dataclasses.replace(fact, value=float("nan"))))
        self.assertTrue(F.validate_fact(dataclasses.replace(fact, value=Decimal("NaN"))))

    def test_a_tampered_id_is_found(self):
        fact = sample_fact()
        self.assertTrue(F.validate_fact(dataclasses.replace(fact, fact_id="f" + "0" * 16)))
        derived = F.DerivedFact.create("F01_change", (fact.fact_id,), "0.3", "%p")
        self.assertTrue(F.validate_derived(dataclasses.replace(derived, value=Decimal("9"))))

    def test_derived_problems(self):
        fact = sample_fact()
        base = F.DerivedFact.create("F01_change", (fact.fact_id,), "0.3", "%p", as_of="2026-03")
        for name, over in {"계산식 번호 모양": dict(formula_id="change"), "입력 비어 있음": dict(input_fact_ids=()), "입력 id 모양": dict(input_fact_ids=("x",)),
                           "입력이 리스트": dict(input_fact_ids=[fact.fact_id]), "값이 None": dict(value=None), "단위 없음": dict(unit=""),
                           "기준일 모양": dict(as_of="내일")}.items():
            with self.subTest(case=name):
                self.assertTrue(F.validate_derived(dataclasses.replace(base, **over)), name)

    def test_record_problems(self):
        cases = {
            "http 주소": dict(request_url="http://stats.mock.invalid/v1"),
            "사용자 정보": dict(request_url="https://user:secretvalue@stats.mock.invalid/v1"),
            "조각": dict(request_url="https://stats.mock.invalid/v1#frag"),
            "키 이름 질의(api_key)": dict(request_url="https://stats.mock.invalid/v1?api_key=abc"),
            "키 이름 질의(serviceKey)": dict(request_url="https://stats.mock.invalid/v1?serviceKey=abc"),
            "토큰 이름 질의": dict(request_url="https://stats.mock.invalid/v1?a=1&access_token=abc"),
            "서명 이름 질의": dict(request_url="https://stats.mock.invalid/v1?sig=abc"),
            "공백": dict(request_url="https://stats.mock.invalid/v1 x"),
            "따옴표": dict(request_url='https://stats.mock.invalid/v1?a="b'),
            "너무 긴 주소": dict(request_url="https://stats.mock.invalid/" + "a" * 600),
            "RSS 경로": dict(access_kind="rss"),
            "HTML 경로": dict(access_kind="html"),
            "이미지 경로": dict(access_kind="image"),
            "수집 시각이 날짜뿐": dict(retrieved_at="2026-04-18"),
            "수집 시각에 시간대 없음": dict(retrieved_at="2026-04-18T02:30:00"),
            "해시 길이": dict(response_hash="abc"),
            "해시 대문자": dict(response_hash="A" * 64),
            "이용 조건 요약 없음": dict(license_snapshot="  "),
            "보관 기한이 음수": dict(retention_days=-1),
            "보관 기한이 실수": dict(retention_days=1.5),
        }
        for name, over in cases.items():
            with self.subTest(case=name):
                self.assertTrue(F.validate_record(sample_record(**over)), name)
        self.assertEqual(F.validate_record(sample_record(request_url="https://stats.mock.invalid/v1?keyword=abc&series=unemp")), [])   # 이름이 key 가 아니라 keyword
        self.assertEqual(F.validate_record(sample_record(retention_days=None)), [])
        self.assertTrue(F.validate_record(dataclasses.replace(sample_record(), record_id="s" + "0" * 16)))

    def test_bundle_cross_references(self):
        record, other = sample_record(), sample_record(retrieved_at="2026-04-19T02:30:00Z")
        fact = sample_fact(record)
        self.assertTrue(F.validate_bundle(F.FactBundle((), (fact,))), "기록 없는 Fact")
        self.assertTrue(F.validate_bundle(F.FactBundle((record,), (fact, fact))), "Fact id 중복")
        self.assertTrue(F.validate_bundle(F.FactBundle((record, record), (fact,))), "기록 id 중복")
        wrong_provider = F.Fact.create("other_stats", record.record_id, F.KIND_OBSERVATION, "labour.x", "1", unit="%", as_of="2026-03", label_ko="낱말")
        self.assertTrue(F.validate_bundle(F.FactBundle((record,), (wrong_provider,))), "제공처가 기록과 다름")
        derived = F.DerivedFact.create("F01_change", ("f" + "9" * 16,), "1", "%p")
        self.assertTrue(F.validate_bundle(F.FactBundle((record,), (fact,), (derived,))), "입력 id 가 묶음에 없음")
        self.assertEqual(F.validate_bundle(F.FactBundle((record, other), (fact,))), [])

    def test_retention_expiry_uses_the_injected_date(self):
        record = sample_record(retention_days=10)
        self.assertFalse(F.record_expired(record, "2026-04-28"))
        self.assertTrue(F.record_expired(record, "2026-04-29"))
        self.assertFalse(F.record_expired(sample_record(retention_days=None), "2099-01-01"))
        self.assertTrue(F.record_expired(record, datetime.date(2026, 5, 1)))
        with self.assertRaises(F.FactFormatError):
            F.record_expired(record, "내일")


class UnknownIsNotZeroTest(unittest.TestCase):
    def test_a_missing_value_stays_none_and_is_valid(self):
        fact = sample_fact(value=None)
        self.assertIsNone(fact.value)
        self.assertEqual(F.validate_fact(fact), [])
        self.assertNotEqual(fact.fact_id, sample_fact(value="0").fact_id)
        self.assertEqual(F.describe(fact).split(" | ")[-1], "값 없음(모름)")

    def test_a_missing_value_is_never_printed_as_zero(self):
        fact = sample_fact(value=None)
        for kind in "FSAV":
            with self.subTest(kind=kind):
                with self.assertRaises(F.MissingValue):
                    F.render(f"⟦{kind}:{fact.fact_id}⟧", [fact])
        self.assertEqual(F.render(f"⟦D:{fact.fact_id}⟧", [fact]), "2026년 3월")      # 기준일은 값이 아니라 읽을 수 있다

    def test_the_round_trip_keeps_none(self):
        record, fact = sample_record(), sample_fact(value=None)
        bundle = F.loads_bundle(F.dumps_bundle(F.FactBundle((record,), (fact,))))
        self.assertIsNone(bundle.facts[0].value)

    def test_to_decimal_does_not_turn_none_or_blank_into_zero(self):
        for bad in (None, "", " ", "abc", "1e5", "1_000", "0x10", "NaN", "Infinity", "--1", True, [], {}):
            with self.subTest(value=bad):
                with self.assertRaises(F.FactFormatError):
                    F.to_decimal(bad)
        self.assertEqual(F.to_decimal("-12.50"), Decimal("-12.50"))
        self.assertEqual(F.to_decimal(3), Decimal(3))
        self.assertEqual(F.to_decimal(0.1), Decimal("0.1"))


class UnitAndPeriodTest(unittest.TestCase):
    def test_different_units_raise_unit_mismatch(self):
        with self.assertRaises(F.UnitMismatch):
            F.require_same_unit(H.make_fact("3", unit="%"), H.make_fact("3", unit="명"))
        self.assertEqual(F.require_same_unit(H.make_fact("3"), H.make_fact("4")), "%")

    def test_the_unit_of_a_difference(self):
        self.assertEqual(F.diff_unit("%"), "%p")
        self.assertEqual(F.diff_unit("%p"), "%p")
        self.assertEqual(F.diff_unit("명"), "명")

    def test_period_parsing(self):
        good = {"2026": "year", "2026-Q1": "quarter", "2026-03": "month", "2026-03-05": "day", "2026-03-05T09:30:00Z": "instant",
                "2026-03-05T09:30+09:00": "instant", "2024-02-29": "day"}
        for text, granularity in good.items():
            with self.subTest(text=text):
                self.assertEqual(F.parse_as_of(text).granularity, granularity)
        for text in ("2026-13", "2026-00", "2026-Q5", "2026-Q0", "2026-02-30", "2025-02-29", "26-03", "", None, 2026, "2026-03-05T25:00:00Z",
                     "2026-03-05T09:30:00+25:00", "2026-03-05T09:30:00", "2026-3", "2026-03-05 09:30:00Z", "2026-03\n"):
            with self.subTest(bad=text):
                self.assertIsNone(F.parse_as_of(text))

    def test_consecutive_periods_differ_by_one(self):
        pairs = [("2026-01", "2025-12"), ("2026-Q1", "2025-Q4"), ("2026", "2025"), ("2026-03-01", "2026-02-28"), ("2024-03-01", "2024-02-29")]
        for later, earlier in pairs:
            with self.subTest(pair=(later, earlier)):
                self.assertEqual(F.parse_as_of(later).ordinal - F.parse_as_of(earlier).ordinal, 1)
        self.assertEqual(F.parse_as_of("2026-03-05T10:30:00+01:00").ordinal, F.parse_as_of("2026-03-05T09:30:00Z").ordinal)

    def test_shift_year(self):
        self.assertEqual(F.shift_year("2026-03", -1), "2025-03")
        self.assertEqual(F.shift_year("2026-Q2", -1), "2025-Q2")
        self.assertEqual(F.shift_year("2026", -1), "2025")
        self.assertEqual(F.shift_year("2026-03-05", -1), "2025-03-05")
        self.assertEqual(F.shift_year("2024-02-29", 4), "2028-02-29")
        self.assertIsNone(F.shift_year("2024-02-29", -1))
        self.assertIsNone(F.shift_year("2026-03-05T09:30:00Z", -1))
        self.assertIsNone(F.shift_year("garbage", -1))

    def test_period_start_and_end(self):
        def edge(text):
            period = F.parse_as_of(text)
            return F.period_start(period).isoformat(), F.period_end(period).isoformat()
        self.assertEqual(edge("2026-02"), ("2026-02-01", "2026-02-28"))
        self.assertEqual(edge("2024-02"), ("2024-02-01", "2024-02-29"))
        self.assertEqual(edge("2026-Q4"), ("2026-10-01", "2026-12-31"))
        self.assertEqual(edge("2026-Q1"), ("2026-01-01", "2026-03-31"))
        self.assertEqual(edge("2026"), ("2026-01-01", "2026-12-31"))
        self.assertEqual(edge("2026-12"), ("2026-12-01", "2026-12-31"))
        self.assertEqual(edge("2026-03-05"), ("2026-03-05", "2026-03-05"))


class SerializationTest(unittest.TestCase):
    def bundle(self):
        record = sample_record()
        fact = sample_fact(record)
        other = sample_fact(record, value="3.1", as_of="2026-02")
        derived = F.DerivedFact.create("F01_change", (fact.fact_id, other.fact_id), "0.15", "%p", as_of="2026-03", region="R01",
                                       key=fact.key, region_level="province", provider_id="mock_stats")
        return F.FactBundle((record,), (fact, other), (derived,))

    def test_round_trip_is_exact_and_stable(self):
        bundle = self.bundle()
        text = F.dumps_bundle(bundle)
        back = F.loads_bundle(text)
        self.assertEqual(set(back.facts), set(bundle.facts))
        self.assertEqual(back.records, bundle.records)
        self.assertEqual(back.derived, bundle.derived)
        self.assertEqual(F.dumps_bundle(back), text)
        data = json.loads(text)
        self.assertEqual(data["schema"], 1)
        self.assertIsInstance(data["facts"][0]["value"], str)        # 값은 문자열로 적는다(실수를 거치지 않는다)

    def test_the_real_mock_bundle_survives_the_round_trip(self):
        _provider, record, facts = H.mock_bundle()
        bundle = F.FactBundle((record,), facts)
        back = F.loads_bundle(F.dumps_bundle(bundle))
        self.assertEqual(sorted(f.fact_id for f in back.facts), sorted(f.fact_id for f in facts))
        self.assertEqual(sum(1 for f in back.facts if f.value is None), sum(1 for f in facts if f.value is None))

    def test_bad_json_is_rejected_with_problems(self):
        good = json.loads(F.dumps_bundle(self.bundle()))

        def with_(edit):
            data = json.loads(json.dumps(good))
            edit(data)
            return json.dumps(data)

        cases = {
            "JSON 아님": "not json {",
            "최상위가 목록": "[]",
            "schema 없음": with_(lambda d: d.pop("schema")),
            "schema 다름": with_(lambda d: d.update(schema=2)),
            "records 없음": with_(lambda d: d.pop("records")),
            "facts 없음": with_(lambda d: d.pop("facts")),
            "facts 가 목록 아님": with_(lambda d: d.update(facts={})),
            "알 수 없는 최상위 칸": with_(lambda d: d.update(extra=1)),
            "Fact 필수 칸 누락": with_(lambda d: d["facts"][0].pop("key")),
            "Fact 알 수 없는 칸": with_(lambda d: d["facts"][0].update(summary="외부 문장")),
            "숫자 값이 숫자 모양": with_(lambda d: d["facts"][0].update(value=3.25)),
            "숫자 값을 읽을 수 없음": with_(lambda d: d["facts"][0].update(value="abc")),
            "id 가 내용과 다름": with_(lambda d: d["facts"][0].update(fact_id="f" + "0" * 16)),
            "기록 id 가 내용과 다름": with_(lambda d: d["records"][0].update(record_id="s" + "0" * 16)),
            "기록 필수 칸 누락": with_(lambda d: d["records"][0].pop("response_hash")),
            "계산 입력 누락": with_(lambda d: d["derived"][0].update(input_fact_ids=["f" + "9" * 16])),
            "계산 값이 숫자 모양": with_(lambda d: d["derived"][0].update(value=1.5)),
            "http 주소": with_(lambda d: d["records"][0].update(request_url="http://stats.mock.invalid/x")),
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(F.FactFormatError) as caught:
                    F.loads_bundle(text)
                self.assertTrue(caught.exception.problems, name)

    def test_duplicate_keys_floats_and_constants_are_rejected(self):
        for text in ('{"schema":1,"schema":1,"records":[],"facts":[]}', '{"schema":1.0,"records":[],"facts":[]}', '{"schema":NaN,"records":[],"facts":[]}',
                     '{"schema":1,"records":[],"facts":[],"derived":[],"x":Infinity}'):
            with self.subTest(text=text[:30]):
                with self.assertRaises(F.FactFormatError):
                    F.loads_bundle(text)

    def test_absurdly_deep_or_huge_json_is_refused_not_crashed(self):
        for text in ("[" * 5000 + "]" * 5000, '{"schema":1,"records":[],"facts":' + "[" * 4000 + "]" * 4000 + "}", "", "   ", "null", "123", '"x"'):
            with self.subTest(text=text[:20]):
                with self.assertRaises(F.FactFormatError):
                    F.loads_bundle(text)

    def test_problem_texts_do_not_echo_the_values(self):
        data = json.loads(F.dumps_bundle(self.bundle()))
        data["facts"][0]["label_ko"] = "비밀값ZZZ"
        with self.assertRaises(F.FactFormatError) as caught:          # 라벨을 바꿨으니 id 가 내용과 맞지 않다
            F.loads_bundle(json.dumps(data))
        self.assertNotIn("비밀값ZZZ", str(caught.exception))
        data["facts"][0]["label_ko"] = "실업률"
        data["facts"][0]["value"] = "abcSECRET"
        with self.assertRaises(F.FactFormatError) as caught:
            F.loads_bundle(json.dumps(data))
        self.assertNotIn("abcSECRET", " ".join(caught.exception.problems))


class NumberFormatTest(unittest.TestCase):
    def test_rounding_boundaries_are_half_away_from_zero(self):
        cases = [("2.25", "%", "2.3%"), ("2.35", "%", "2.4%"), ("0.05", "%", "0.1%"), ("0.049", "%", "0.0%"), ("1.05", "%", "1.1%"),
                 ("-2.25", "%", "−2.3%"), ("-0.05", "%", "−0.1%"), ("-0.049", "%", "0.0%"), ("-0.04", "%p", "0.0%p"), ("9.95", "%", "10.0%"),
                 ("99.95", "%", "100.0%"), ("2.675", "달러", "2.68달러"), ("1.005", "유로", "1.01유로"), ("1234.5", "명", "1,235명"),
                 ("1234.4", "명", "1,234명"), ("-1234.5", "명", "−1,235명"), ("0.5", "건", "1건"), ("-0.5", "건", "−1건")]
        for value, unit, expected in cases:
            with self.subTest(value=value, unit=unit):
                self.assertEqual(F.format_with_unit(Decimal(value), unit), expected)

    def test_the_rounding_matches_an_independent_integer_oracle(self):
        """-20.00 에서 20.00 까지 0.01 간격 4001개를 소수 첫째 자리로: 정수 산술로 따로 구한 값과 같다(반올림 방식을 바꾸면 5 로 끝나는 값에서 어긋난다)."""
        for hundredths in range(-2000, 2001):
            tenths = (abs(hundredths) + 5) // 10
            expected = ("−" if hundredths < 0 and tenths else "") + f"{tenths // 10},{tenths % 10}".replace(",", ".")
            got = F.format_decimal(Decimal(hundredths) / Decimal(100), 1)
            self.assertEqual(got, expected, hundredths)

    def test_separators_signs_and_big_numbers(self):
        self.assertEqual(F.format_decimal(Decimal("123456789012.34"), 1), "123,456,789,012.3")
        self.assertEqual(F.format_decimal(Decimal("1000"), 0), "1,000")
        self.assertEqual(F.format_decimal(Decimal("999.99"), 0), "1,000")
        self.assertEqual(F.format_decimal(Decimal("0"), 1), "0.0")
        self.assertEqual(F.format_decimal(Decimal("-0.0"), 1), "0.0")
        self.assertEqual(F.format_decimal(Decimal("0.4"), 1, signed=True), "+0.4")
        self.assertEqual(F.format_decimal(Decimal("-0.4"), 1, signed=True), "−0.4")
        self.assertEqual(F.format_decimal(Decimal("0.04"), 1, signed=True), "0.0")
        self.assertEqual(F.format_decimal(Decimal("-0.4"), 1, absolute=True), "0.4")
        self.assertEqual(F.format_with_unit(Decimal("0.4"), "%p", signed=True), "+0.4%p")
        self.assertEqual(F.format_with_unit(Decimal("-12"), "개월", absolute=True), "12개월")

    def test_decimals_follow_the_unit_table(self):
        self.assertEqual(F.decimals_for("%"), F.NUMBER_POLICY["display_decimals"])
        self.assertEqual(F.decimals_for("명"), 0)
        self.assertEqual(F.decimals_for("달러"), 2)
        self.assertEqual(F.decimals_for("포인트"), 1)
        self.assertEqual(F.decimals_for(None), 1)
        self.assertEqual(F.NUMBER_POLICY["display_decimals"], 1)

    def test_display_sign_uses_the_rounded_value(self):
        self.assertEqual(F.display_sign(Decimal("0.04"), "%p"), 0)
        self.assertEqual(F.display_sign(Decimal("-0.04"), "%p"), 0)
        self.assertEqual(F.display_sign(Decimal("0.05"), "%p"), 1)
        self.assertEqual(F.display_sign(Decimal("-0.05"), "%p"), -1)
        self.assertEqual(F.display_sign(Decimal("0.4"), "명"), 0)       # 정수 단위는 0.4 가 0 으로 보인다
        self.assertEqual(F.display_sign(Decimal("0.5"), "명"), 1)

    def test_internal_values_are_not_rounded_by_formatting(self):
        value = Decimal("3.3333333333")
        F.format_with_unit(value, "%")
        self.assertEqual(value, Decimal("3.3333333333"))


class DateFormatTest(unittest.TestCase):
    def test_korean_dates(self):
        cases = {"2026": "2026년", "2026-Q1": "2026년 1분기", "2026-03": "2026년 3월", "2026-03-05": "2026년 3월 5일",
                 "2026-03-05T09:30:00Z": "2026년 3월 5일 9시 30분(UTC)", "2026-03-05T09:30:00+00:00": "2026년 3월 5일 9시 30분(UTC)",
                 "2026-03-05T18:30:00+09:00": "2026년 3월 5일 18시 30분(한국 시간)", "2026-03-05T09:30:00+05:30": "2026년 3월 5일 9시 30분(UTC+05:30)"}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(F.format_period_ko(text), expected)
        self.assertEqual(F.format_date_ko("2026-12-31"), "2026년 12월 31일")
        for bad in ("2026-03", "x", None):
            with self.assertRaises(F.FactFormatError):
                F.format_date_ko(bad)
        with self.assertRaises(F.FactFormatError):
            F.format_period_ko("2026-13")


class ReferenceRenderingTest(unittest.TestCase):
    def setUp(self):
        self.record = sample_record()
        self.fact = sample_fact(self.record)
        self.diff = F.DerivedFact.create("F01_change", (self.fact.fact_id,), "-0.04", "%p", as_of="2026-03", region="R01", key=self.fact.key, region_level="province")
        self.pool = {self.fact.fact_id: self.fact, self.diff.fact_id: self.diff, self.record.record_id: self.record}

    def ref(self, kind, obj):
        return F.make_ref(kind, getattr(obj, "fact_id", None) or obj.record_id)

    def test_each_marker_kind(self):
        f, d, r = self.fact, self.diff, self.record
        cases = [("F", f, "3.3%"), ("S", f, "+3.3%"), ("A", d, "0.0%p"), ("V", f, "3.3"), ("U", f, "%"), ("D", f, "2026년 3월"),
                 ("L", f, "실업률"), ("R", f, "가상 지역 가"), ("T", r, "2026년 4월 18일"), ("F", d, "0.0%p"), ("S", d, "0.0%p"), ("U", d, "%p")]
        for kind, obj, expected in cases:
            with self.subTest(kind=kind, obj=type(obj).__name__):
                self.assertEqual(F.render(self.ref(kind, obj), self.pool), expected)

    def test_text_and_date_facts_render_their_value_with_F(self):
        date = F.Fact.create("mock_stats", self.record.record_id, F.KIND_EVENT_START, "economy.event", "2026-05-01")
        status = F.Fact.create("mock_stats", self.record.record_id, F.KIND_OFFICIAL_STATUS, "environment.alert", "경보")
        when = F.Fact.create("mock_stats", self.record.record_id, F.KIND_DATETIME, "environment.obs_time", "2026-05-01T03:00:00Z")
        self.assertEqual(F.render(self.ref("F", date), [date]), "2026년 5월 1일")
        self.assertEqual(F.render(self.ref("F", status), [status]), "경보")
        self.assertEqual(F.render(self.ref("F", when), [when]), "2026년 5월 1일 3시 0분(UTC)")
        for kind in "SAVU":
            with self.subTest(kind=kind):
                with self.assertRaises(F.TemplateError):
                    F.render(self.ref(kind, status), [status])

    def test_markers_on_the_wrong_object_are_errors(self):
        with self.assertRaises(F.TemplateError):
            F.render(self.ref("F", self.record), self.pool)
        with self.assertRaises(F.TemplateError):
            F.render(self.ref("T", self.fact), self.pool)
        bare = F.Fact.create("mock_stats", self.record.record_id, F.KIND_NUMBER, "economy.x", "5", unit="개", as_of="2026", label_ko="낱말")
        with self.assertRaises(F.TemplateError):                # 지역 낱말이 없는 Fact
            F.render(self.ref("R", bare), [bare])
        status = F.Fact.create("mock_stats", self.record.record_id, F.KIND_OFFICIAL_STATUS, "environment.alert", "경보")
        with self.assertRaises(F.TemplateError):                # 라벨이 없는 Fact
            F.render(self.ref("L", status), [status])
        for kind in "LR":                                        # 계산 결과는 라벨·지역 낱말을 갖지 않는다(기본 Fact 의 칸을 쓴다)
            with self.subTest(kind=kind):
                with self.assertRaises(F.TemplateError):
                    F.render(self.ref(kind, self.diff), [self.diff])

    def test_untraced_numbers_are_rejected(self):
        for text in ("값은 3.2 입니다", "2026년", "10%", "두 배 올랐다", "세 곳", "네 번", "한 해", "열 개", "①번", "½", "１２", "一곳", "제5호", "에서 5까지"):
            with self.subTest(text=text):
                self.assertTrue(F.untraced_numbers(text), text)
                with self.assertRaises(F.UntracedNumber):
                    F.render(text, [])
        error = None
        try:
            F.render("값은 3.2 입니다", [])
        except F.UntracedNumber as exc:
            error = exc
        self.assertEqual(error.numbers, ["3", "2"])

    def test_clean_templates_have_no_untraced_numbers(self):
        for text in ("", "숫자가 없는 문장입니다", f"값은 {self.ref('F', self.fact)} 입니다", "한눈에 보는 요약", "한국의 하루", "제3자 자료", "공공누리 제1유형",
                     "열차가 지나갑니다", "세계 곳곳", "하루", f"{self.ref('V', self.fact)}{self.ref('U', self.fact)}"):
            with self.subTest(text=text):
                self.assertEqual(F.untraced_numbers(text), [], text)

    def test_ids_inside_markers_are_not_counted_as_numbers(self):
        text = f"⟦F:{self.fact.fact_id}⟧ 와 ⟦D:{self.fact.fact_id}⟧"
        self.assertEqual(F.untraced_numbers(text), [])
        self.assertEqual(F.references(text), [("F", self.fact.fact_id), ("D", self.fact.fact_id)])

    def test_unknown_references_and_stray_markers(self):
        with self.assertRaises(F.UnknownReference):
            F.render("⟦F:f0000000000000000⟧", [])
        for stray in ("열린 ⟦F:abc", "닫힌 abc⟧", "⟦X:abc⟧", "⟦F abc⟧", "⟦⟧"):
            with self.subTest(stray=stray):
                with self.assertRaises(F.FactError):
                    F.render(stray, [self.fact])

    def test_the_output_has_no_marker_or_liquid_characters(self):
        text = F.render(f"{self.ref('R', self.fact)}의 {self.ref('L', self.fact)} 값은 {self.ref('F', self.fact)}입니다.", [self.fact])
        for mark in ("⟦", "⟧", "{{", "{%", "}}", "%}"):
            self.assertNotIn(mark, text)
        for liquid in ("값 {{ x }}", "{% if x %}", "열 {{"):
            with self.subTest(liquid=liquid):
                with self.assertRaises(F.TemplateError):
                    F.render(liquid, [])

    def test_bind_replaces_slot_names_with_ids(self):
        bound = F.bind("⟦F:main⟧ ⟦D:main⟧ ⟦T:rec⟧", {"main": self.fact, "rec": self.record})
        self.assertEqual(bound, f"⟦F:{self.fact.fact_id}⟧ ⟦D:{self.fact.fact_id}⟧ ⟦T:{self.record.record_id}⟧")
        self.assertEqual(F.render(bound, self.pool), "3.3% 2026년 3월 2026년 4월 18일")
        self.assertEqual(F.bind(f"⟦F:{self.fact.fact_id}⟧", {}), f"⟦F:{self.fact.fact_id}⟧")        # 이미 id 인 참조는 그대로
        with self.assertRaises(F.UnboundSlot):
            F.bind("⟦F:missing⟧", {"main": self.fact})

    def test_make_ref_validates(self):
        for kind, ref in (("Z", "abc"), ("F", ""), ("F", "a b"), ("F", "a" * 65), ("F", "한글")):
            with self.subTest(kind=kind, ref=ref):
                with self.assertRaises(F.TemplateError):
                    F.make_ref(kind, ref)

    def test_render_accepts_a_mapping_or_a_list_but_not_two_objects_with_one_id(self):
        self.assertEqual(F.render(self.ref("F", self.fact), {self.fact.fact_id: self.fact}), "3.3%")
        self.assertEqual(F.render(self.ref("F", self.fact), [self.fact, self.fact]), "3.3%")
        twin = dataclasses.replace(self.fact, value=Decimal("9"))
        with self.assertRaises(F.UnknownReference):
            F.render(self.ref("F", self.fact), [self.fact, twin])

    def test_describe_uses_the_same_text_as_the_body(self):
        self.assertEqual(F.describe(self.fact), "실업률 | 가상 지역 가 | 2026년 3월 | 3.3%")
        self.assertEqual(F.describe(self.diff), "2026년 3월 | 0.0%p")


class ProviderProtocolTest(unittest.TestCase):
    def provider(self, **over):
        values = dict(provider_id="x_stats", strict_tier=2, effective_status="자동화 가능", access=[], attribution_template=None, snapshot=None,
                      policy=None, retention_days=30)
        values.update(over)
        return types.SimpleNamespace(**values)

    def test_a_duck_typed_object_is_a_provider(self):
        self.assertIsInstance(self.provider(), F.ProviderLike)
        self.assertEqual(F.provider_problems(self.provider()), [])
        self.assertEqual(F.provider_problems(dict(vars(self.provider()))), [])           # 사전도 같은 필드를 가지면 받는다
        self.assertEqual(F.field_of({"a": 1}, "a"), 1)
        self.assertEqual(F.field_of(types.SimpleNamespace(a=2), "a"), 2)
        self.assertEqual(F.field_of(types.SimpleNamespace(), "a", "d"), "d")

    def test_missing_fields_and_bad_values_are_problems(self):
        for name in F.PROVIDER_FIELDS:
            with self.subTest(missing=name):
                data = dict(vars(self.provider()))
                data.pop(name)
                self.assertTrue(F.provider_problems(types.SimpleNamespace(**data)))
        for over in ({"strict_tier": 5}, {"strict_tier": "2"}, {"strict_tier": True}, {"effective_status": 3}):
            with self.subTest(over=over):
                self.assertTrue(F.provider_problems(self.provider(**over)))

    def test_only_an_active_low_tier_provider_passes_the_assembler_guard(self):
        self.assertIsNone(F.provider_active_problem(self.provider()))
        self.assertIsNone(F.provider_active_problem(self.provider(strict_tier=0)))
        for over in ({"strict_tier": 3}, {"strict_tier": 4}, {"effective_status": "자동화 제외"}, {"effective_status": "참고 전용"}, {"effective_status": "완전 제외"}):
            with self.subTest(over=over):
                self.assertTrue(F.provider_active_problem(self.provider(**over)))
        self.assertTrue(F.provider_active_problem(types.SimpleNamespace()))

    def test_snapshot_text_is_deterministic_and_bounded(self):
        snapshot = types.SimpleNamespace(terms_pages=("이용 안내",), read_at="2026-11-09", content_hash="", expires_at="2027-02-07")
        text = F.snapshot_text(self.provider(snapshot=snapshot))
        self.assertEqual(text, F.snapshot_text(self.provider(snapshot=snapshot)))
        self.assertIn("tier=2", text)
        self.assertIn("expires_at=2027-02-07", text)
        self.assertIn("content_hash=-", text)
        self.assertLessEqual(len(F.snapshot_text(self.provider(snapshot={"terms_pages": "가" * 900}))), 600)
        self.assertEqual(F.snapshot_text(self.provider(snapshot=None)), "tier=2; status=자동화 가능")

    def test_source_domain(self):
        self.assertEqual(F.source_domain("https://Stats.Mock.Invalid/data/x"), "stats.mock.invalid")
        for bad in ("http://a.invalid/", "ftp://a.invalid", "", None, "https://"):
            self.assertIsNone(F.source_domain(bad))

    def test_the_registry_and_opener_protocols_have_the_agreed_shape(self):
        registry = types.SimpleNamespace(get=lambda i: None, active_providers=lambda: [], is_url_allowed=lambda url, purpose: (True, ""))
        self.assertIsInstance(registry, F.RegistryLike)
        self.assertNotIsInstance(types.SimpleNamespace(get=lambda i: None), F.RegistryLike)
        self.assertIsInstance(lambda url, *, timeout, max_bytes: b"", F.Opener)


class TextFieldSafetyTest(unittest.TestCase):
    def test_label_and_unit_charsets_keep_markup_out(self):
        for label in ("실업률", "취업자 수", "소비자 물가(지수)", "GDP 성장률", "전년/전월"):
            with self.subTest(good=label):
                self.assertEqual(F.validate_fact(sample_fact(label_ko=label)), [])
        for label in ("실업률|", "[실업률]", "실업률`", "실업률*", "실업률_", "실업률#", "<b>실업률</b>", "실업률\\", "실업률&nbsp;", " 실업률", "실업률 ", "실업  률", "실업률.", "실업률,"):
            with self.subTest(bad=label):
                self.assertTrue(F.validate_fact(sample_fact(label_ko=label)), label)
        for unit in ("%", "%p", "명", "℃", "㎡", "kWh", "개월", "명/월", "달러"):
            with self.subTest(good_unit=unit):
                self.assertEqual(F.validate_fact(sample_fact(unit=unit)), [])
        for unit in ("", "1%", "%²", "m²", "명 ", "a b", "|"):
            with self.subTest(bad_unit=unit):
                self.assertTrue(F.validate_fact(sample_fact(unit=unit)), unit)


if __name__ == "__main__":
    unittest.main()
