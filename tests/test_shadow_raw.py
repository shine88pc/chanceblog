"""S2C0-c — 그림자 실행(구조화 Fact 분기)이 받은 원본 응답을 SHADOW_OUT 아래에 함께 남기는 것(`shadow_run.RawRecorder`)의 시험.

문제: 그림자 산출물에는 글과 판정만 있고 NOAA 가 준 원본 응답이 없어 개선 전 기준선을 바이트까지 같게 다시 만들려면 글의 표에서 입력을 복원해야 했다(불완전). 해결: 어댑터에 넣는 transport 를 감싸 받은 바이트를 그대로 남긴다.

못박는 것: ① 남긴 파일의 바이트가 transport 가 돌려준 바이트와 같고 색인(제품 id·바이트 수·sha256·수집 시각 UTC)이 맞다 ② 새 네트워크 호출이 0 이고 감싼 transport 는 같은 바이트 객체를 돌려준다(전송 예외는 그대로 올라간다)
③ 쓰는 곳은 SHADOW_OUT 안뿐이고(경로 이탈은 `ShadowViolation` 이며 삼키지 않는다) 저장소 작업 폴더의 바이트는 그대로다 ④ 기존 `result.json`·`run.json`·글 파일은 바이트까지 그대로다(보관 없이 돌린 결과와 같다 — 하위 폴더를 만들지
않아 폴더마다 `result.json` 을 읽는 소비자가 멈추지 않는다) ⑤ 보관이 실패해도 본 결과는 같고 실패 사실이 `run.json` 메모에만 남는다 ⑥ 크기 상한 ⑦ 워크플로(T3 — 이 묶음은 바꾸지 않았다)가 결과 폴더 전체를 올리고 후보 집계는 번호 폴더의
`result.json` 만 센다는 것을 읽어서 확인한다 ⑧ 남긴 파일을 읽는 코드가 어디에도 없다(AI 입력 방어).
네트워크·시계 없음(가짜 transport)."""
import ast
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap
import fact_branch_helpers as FB
import hold_helpers as HH
import test_fact_shadow as TS

from pipeline import fact_supply as S
from pipeline import shadow_run
from pipeline.adapters import noaa_swpc as N

ROOT = _bootstrap.ROOT
setUpModule, tearDownModule = HH.module_fixtures()      # 이 모듈은 글감 여섯 전부를 읽는 흐름에서 보관 장치를 본다 — 기본 상수에서의 보관은 DefaultPolicyTest 가 따로 본다
RUN_KEYS = {"schema", "requested", "attempts", "passed", "held_or_rejected", "languages", "outcome", "lanes_tried", "notes", "generated_at", "attempts_summary"}
RESULT_KEYS = {"schema", "attempt", "passed", "outcome", "hold_reasons", "hold_codes", "validation", "gate", "source_text_chars", "model", "lane", "source_url", "source_name", "source_domain",
               "title_ko", "title_en", "languages", "files", "published", "generated_at"}
THREE_PRODUCTS = ["kp_estimated", "xray_flares", "scales"]       # 글감 순서대로 첫 셋(kp_weekly·flares_weekly·scales_weekly)이 읽는 제품
RETRIEVED, TODAY = "2026-11-10T01:12:00Z", "2026-11-10"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree_bytes(folder, skip=()):
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in sorted(Path(folder).rglob("*")) if path.is_file() and path.relative_to(folder).as_posix() not in skip}


class PassThrough:
    """보관기를 끈 대역: transport 를 그대로 돌려주는 '보관기'(보관 없이 돌린 그림자 결과를 얻는 기준)."""

    def __init__(self, send, *args, **kwargs):
        self.send, self.files, self.total = send, [], 0

    def __call__(self, url, *, timeout, max_bytes):
        return self.send(url, timeout=timeout, max_bytes=max_bytes)

    def check(self):
        return None

    def notes(self):
        return []


class RawBase(TS.ShadowFactsBase):
    def expected_bytes(self, product):
        return json.dumps(self.noaa.by_product[product], ensure_ascii=False).encode("utf-8")

    def index(self):
        return json.loads((self.out_dir / shadow_run.RAW_INDEX_FILE).read_text(encoding="utf-8"))

    def spy_retrieved_at(self):
        """공급 함수가 받은 수집 시각을 적는 감시자 — 색인에 남은 값과 같아야 한다."""
        seen = []
        real = S.supply
        spy = lambda **kwargs: (seen.append(kwargs["retrieved_at"]), real(**kwargs))[1]      # noqa: E731
        return seen, mock.patch.object(S, "supply", spy)

    def run_plain(self, name):
        """보관기를 끄고(감쌈만 하는 대역) 돌린 결과 폴더."""
        self.out_dir = self.out_dir.parent / name
        with mock.patch.object(shadow_run, "RawRecorder", PassThrough):
            info, lines = self.run_shadow("3")
        return self.out_dir, info, lines


class StoredResponsesTest(RawBase):
    def test_every_response_is_kept_byte_for_byte_with_its_size_and_sha256_in_the_index(self):
        seen, patch = self.spy_retrieved_at()
        with patch:
            info, lines = self.run_shadow("3")
        self.assertEqual(info["attempts"], 3)
        self.assertEqual(self.noaa.products(), THREE_PRODUCTS)
        index = self.index()
        self.assertEqual([item["product"] for item in index["responses"]], THREE_PRODUCTS)                  # 받은 순서대로
        for item in index["responses"]:
            with self.subTest(product=item["product"]):
                data = (self.out_dir / item["file"]).read_bytes()
                self.assertEqual(item["file"], f"raw_{item['product']}.json")
                self.assertEqual(data, self.expected_bytes(item["product"]))                                  # transport 가 돌려준 바이트 그대로
                self.assertEqual((item["bytes"], item["sha256"]), (len(data), sha(data)))
        self.assertEqual(index["total_bytes"], sum(item["bytes"] for item in index["responses"]))
        self.assertEqual((index["schema"], index["not_stored"], index["total_limit_bytes"]), (1, [], shadow_run.RAW_MAX_TOTAL_BYTES))
        self.assertEqual(seen, [index["retrieved_at"]])                                                      # 수집 시각은 공급 함수가 어댑터에 넘긴 값과 같다
        self.assertEqual((index["retrieved_at"], index["today_kst"]), (RETRIEVED, TODAY))
        self.assertTrue(any(line.startswith("[그림자] 받은 원본 응답 3건(") and "새 네트워크 호출은 없습니다" in line for line in lines), lines)

    def test_the_only_new_files_are_the_index_and_one_file_per_product_directly_under_the_out_folder(self):
        before = TS.snapshot(self.work)
        self.run_shadow("3")
        self.assertEqual(TS.snapshot(self.work), before)                                                    # 저장소 작업 폴더의 바이트는 그대로
        names = sorted(path.relative_to(self.out_dir).as_posix() for path in self.out_dir.rglob("*") if path.is_file())
        self.assertEqual(names, ["01/2026-11-10-KR-101200.md", "01/result.json", "02/2026-11-10-KR-101201.md", "02/result.json", "03/2026-11-10-KR-101202.md", "03/result.json",
                                 "raw_index.json", "raw_kp_estimated.json", "raw_scales.json", "raw_xray_flares.json", "run.json"])
        self.assertEqual([path for path in self.out_dir.rglob("*.tmp")], [])                                  # 임시 파일이 남지 않는다
        self.assertEqual([path for path in self.out_dir.rglob("*.md") if "raw" in path.name], [])             # 측정 도구가 읽는 글 파일 이름(.md)이 아니다

    def test_there_is_no_subfolder_besides_the_numbered_ones_and_each_has_a_result_json(self):
        """하위 폴더마다 `result.json` 을 읽는 소비자(후보 표를 만드는 점검 도구)가 있다 — 그래서 원본 응답은 폴더가 아니라 파일로 둔다. 워크플로의 통과 집계 글롭은 번호 폴더만 센다."""
        self.run_shadow("5")
        folders = [path for path in self.out_dir.iterdir() if path.is_dir()]
        self.assertTrue(folders)
        for folder in folders:
            self.assertRegex(folder.name, r"\A\d{2}\Z")
            self.assertTrue((folder / "result.json").is_file(), folder.name)
        self.assertEqual(len(list(self.out_dir.glob("*/result.json"))), len(folders))                      # 워크플로가 후보 수로 세는 글롭(*/result.json)은 번호 폴더만 센다


class MainResultUnchangedTest(RawBase):
    def test_result_run_and_post_files_are_byte_for_byte_what_a_run_without_the_recorder_makes(self):
        plain_dir, plain_info, _lines = self.run_plain("plain")
        self.out_dir = self.out_dir.parent / "with_raw"
        info, _lines = self.run_shadow("3")
        raw_names = {shadow_run.RAW_INDEX_FILE} | {f"raw_{product}.json" for product in THREE_PRODUCTS}
        self.assertEqual(tree_bytes(self.out_dir, skip=raw_names), tree_bytes(plain_dir))                    # 보관 파일을 뺀 모든 파일이 같다(run.json·result.json·글 파일)
        self.assertEqual(info, plain_info)
        self.assertEqual(set(self.run_info()), RUN_KEYS)                                                     # 새 필드가 없다 — 기존 소비자가 보던 칸 그대로
        for result in self.results().values():
            self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(self.run_info()["notes"], [])                                                       # 보관이 잘 되면 메모도 없다

    def test_a_run_without_any_response_leaves_no_raw_file(self):
        self.use(FB.facts_registry(), FB.real_sources(noaa_enabled=False))
        info, _lines = self.run_shadow("3")
        self.assertEqual((info["attempts"], info["outcome"]), (0, "NO_CANDIDATES"))
        self.assertEqual([path.name for path in self.out_dir.iterdir()], ["run.json"])
        self.assertEqual(self.noaa.factory_calls, 0)                                                         # 전송 객체를 만들지도 않았다


class FailureTest(RawBase):
    def test_a_failing_write_changes_nothing_in_the_main_result_but_the_notes(self):
        plain_dir, plain_info, _lines = self.run_plain("plain")
        self.out_dir = self.out_dir.parent / "failing"
        with mock.patch.object(shadow_run.ShadowWriter, "write_bytes", side_effect=OSError("디스크가 가득 SECRET-PATH-TEXT")):
            info, _lines = self.run_shadow("3")
        failed_notes = [f"원본 응답을 남기지 않았습니다({product}, WRITE_FAILED)" for product in THREE_PRODUCTS]
        self.assertEqual(self.run_info()["notes"], failed_notes)
        self.assertEqual({key: value for key, value in info.items() if key != "notes"}, {key: value for key, value in plain_info.items() if key != "notes"})
        self.assertEqual(tree_bytes(self.out_dir, skip={shadow_run.RAW_INDEX_FILE, "run.json"}), tree_bytes(plain_dir, skip={"run.json"}))
        self.assertNotIn("SECRET", json.dumps(self.run_info(), ensure_ascii=False))                          # 예외 문장은 어디에도 남지 않는다
        self.assertEqual([item["reason"] for item in self.index()["not_stored"]], ["WRITE_FAILED"] * 3)

    def test_a_failing_index_write_is_noted_and_the_run_still_ends_normally(self):
        plain_dir, plain_info, _lines = self.run_plain("plain")
        self.out_dir = self.out_dir.parent / "no_index"
        real_write_json = shadow_run.ShadowWriter.write_json
        picky = lambda writer, relative, value: (_ for _ in ()).throw(OSError("색인을 쓸 수 없다")) if relative == shadow_run.RAW_INDEX_FILE else real_write_json(writer, relative, value)      # noqa: E731
        with mock.patch.object(shadow_run.ShadowWriter, "write_json", picky):
            info, _lines = self.run_shadow("3")
        self.assertEqual(self.run_info()["notes"], ["원본 응답 보관에 실패했습니다(OSError) — 본 결과에는 영향이 없습니다"] * 3)
        self.assertEqual(tree_bytes(self.out_dir, skip={"run.json"} | {f"raw_{product}.json" for product in THREE_PRODUCTS}), tree_bytes(plain_dir, skip={"run.json"}))
        self.assertEqual(info["attempts"], plain_info["attempts"])

    def test_a_violation_is_never_swallowed_even_though_the_adapter_turns_every_transport_error_into_a_skip(self):
        """어댑터는 전송 중의 모든 예외를 `OPENER_FAILED` 로 바꾼다 — 보관기가 그 자리에서 `ShadowViolation` 을 올리면 조용히 건너뛴 것이 된다. 그래서 기억했다가 공급이 끝난 뒤 올린다(실행은 빨강)."""
        with mock.patch.object(shadow_run.ShadowWriter, "write_bytes", side_effect=shadow_run.ShadowViolation("밖")):
            with self.assertRaises(shadow_run.ShadowViolation):
                self.run_shadow("3")

    def test_a_transport_error_goes_up_unchanged_and_nothing_is_kept_for_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []

            def broken(url, *, timeout, max_bytes):
                calls.append(url)
                raise TimeoutError("응답이 늦다")
            recorder = shadow_run.RawRecorder(broken, shadow_run.ShadowWriter(tmp), S.product_id_of_url, RETRIEVED, TODAY)
            with self.assertRaises(TimeoutError):
                recorder(N.product_url("kp_estimated"), timeout=5, max_bytes=100)
            self.assertEqual((len(calls), recorder.files, recorder.not_stored, recorder.problems), (1, [], [], []))
            self.assertEqual(list(Path(tmp).iterdir()), [])


class RecorderUnitTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / "out"
        self.root.mkdir()

    def make(self, send, product_of=S.product_id_of_url):
        return shadow_run.RawRecorder(send, shadow_run.ShadowWriter(self.root), product_of, RETRIEVED, TODAY)

    def test_the_wrapped_transport_returns_the_very_same_bytes_object_and_receives_the_same_arguments(self):
        payload, received = b"[1, 2, 3]", []

        def send(url, *, timeout, max_bytes):
            received.append((url, timeout, max_bytes))
            return payload
        recorder = self.make(send)
        url = N.product_url("scales")
        self.assertIs(recorder(url, timeout=7, max_bytes=1000), payload)
        self.assertEqual(received, [(url, 7, 1000)])
        self.assertEqual((self.root / "raw_scales.json").read_bytes(), payload)

    def test_the_same_product_twice_gets_a_numbered_name_and_both_are_listed(self):
        recorder = self.make(lambda url, *, timeout, max_bytes: b"[1]")
        url = N.product_url("kp_estimated")
        recorder(url, timeout=5, max_bytes=100)
        recorder(url, timeout=5, max_bytes=100)
        self.assertEqual([item["file"] for item in recorder.files], ["raw_kp_estimated.json", "raw_kp_estimated_2.json"])
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["raw_index.json", "raw_kp_estimated.json", "raw_kp_estimated_2.json"])

    def test_a_response_that_is_not_bytes_is_returned_untouched_and_not_kept(self):
        recorder = self.make(lambda url, *, timeout, max_bytes: "글자 응답")
        self.assertEqual(recorder(N.product_url("scales"), timeout=1, max_bytes=10), "글자 응답")
        self.assertEqual((list(self.root.iterdir()), recorder.files, recorder.not_stored), ([], [], []))

    def test_an_unknown_address_is_not_kept_and_no_address_text_is_written(self):
        recorder = self.make(lambda url, *, timeout, max_bytes: b"[]")
        for url in ("https://services.swpc.noaa.gov/products/noaa-scales.json?token=SECRETWORD", "https://other.example/x.json", "https://services.swpc.noaa.gov/../etc/passwd", ""):
            recorder(url, timeout=1, max_bytes=10)
        self.assertEqual([item["reason"] for item in recorder.not_stored], ["UNKNOWN_PRODUCT"] * 4)
        index_text = (self.root / shadow_run.RAW_INDEX_FILE).read_text(encoding="utf-8")
        for needle in ("SECRETWORD", "other.example", "passwd", "http"):
            self.assertNotIn(needle, index_text)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), [shadow_run.RAW_INDEX_FILE])

    def test_a_product_id_that_could_name_a_path_is_never_used_as_a_file_name(self):
        for hostile in ("../escape", "a/b", "..", "", "UPPER", "x" * 41, "a.b", None, 5, "kp estimated"):
            with self.subTest(product=hostile):
                recorder = self.make(lambda url, *, timeout, max_bytes: b"[1]", product_of=lambda url: hostile)
                recorder(N.product_url("scales"), timeout=1, max_bytes=10)
                self.assertEqual([item["reason"] for item in recorder.not_stored], ["UNKNOWN_PRODUCT"])
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), [shadow_run.RAW_INDEX_FILE])
        self.assertEqual(sorted(path.name for path in self.base.iterdir()), ["out"])                         # 바깥에는 아무것도 쓰지 않았다

    def test_the_writer_refuses_a_path_outside_the_root_and_the_recorder_reports_it_after_the_call(self):
        writer = shadow_run.ShadowWriter(self.root)
        for bad in ("../escape.json", "/abs/escape.json", "a/../../escape.json"):
            with self.assertRaises(shadow_run.ShadowViolation):
                writer.write_bytes(bad, b"x")
        self.assertEqual(sorted(path.name for path in self.base.iterdir()), ["out"])
        recorder = self.make(lambda url, *, timeout, max_bytes: b"[1]")
        with mock.patch.object(shadow_run.ShadowWriter, "write_bytes", side_effect=shadow_run.ShadowViolation("밖")):
            self.assertEqual(recorder(N.product_url("scales"), timeout=1, max_bytes=10), b"[1]")             # 호출은 정상으로 끝난다(어댑터가 삼키지 못하게)
        with self.assertRaises(shadow_run.ShadowViolation):
            recorder.check()

    def test_the_size_limits_a_single_response_over_the_call_limit_and_the_total(self):
        with mock.patch.object(shadow_run, "RAW_MAX_TOTAL_BYTES", 100):
            recorder = self.make(lambda url, *, timeout, max_bytes: b"x" * 60)
            recorder(N.product_url("kp_estimated"), timeout=1, max_bytes=100)                              # 60 — 남긴다
            recorder(N.product_url("xray_flares"), timeout=1, max_bytes=100)                               # 60 + 60 > 100 — 남기지 않는다
            recorder(N.product_url("scales"), timeout=1, max_bytes=50)                                      # 응답이 호출 상한(50)을 넘는다 — 남기지 않는다
            self.assertEqual([(item["product"], item["reason"]) for item in recorder.not_stored], [("xray_flares", "OVER_TOTAL_LIMIT"), ("scales", "TOO_LARGE")])
            self.assertEqual(recorder.total, 60)
            self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["raw_index.json", "raw_kp_estimated.json"])
            self.assertEqual(recorder.notes(), ["원본 응답을 남기지 않았습니다(xray_flares, OVER_TOTAL_LIMIT)", "원본 응답을 남기지 않았습니다(scales, TOO_LARGE)"])
        recorder = self.make(lambda url, *, timeout, max_bytes: b"y" * 100)                                 # 정확히 상한이면 남긴다(경계)
        with mock.patch.object(shadow_run, "RAW_MAX_TOTAL_BYTES", 100):
            recorder(N.product_url("ssn_monthly"), timeout=1, max_bytes=100)
        self.assertEqual((recorder.total, recorder.not_stored), (100, []))

    def test_bytes_with_crlf_a_lone_cr_and_non_utf8_are_kept_exactly_and_the_same_object_is_returned(self):
        payload = b'{"a":1}' + bytes([13, 10, 13, 255, 254, 0, 10])                                          # CRLF·홑 CR·UTF-8 이 아닌 바이트·NUL 이 섞인 응답
        recorder = self.make(lambda url, *, timeout, max_bytes: payload)
        returned = recorder(N.product_url("scales"), timeout=1, max_bytes=1000)
        self.assertIs(returned, payload)
        self.assertEqual((self.root / "raw_scales.json").read_bytes(), payload)                                # 저장된 파일이 받은 바이트와 한 바이트도 다르지 않다(기준선 재생의 목적)
        self.assertEqual(recorder.files[0]["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(recorder.files[0]["bytes"], len(payload))

    def test_a_response_exactly_at_the_call_limit_is_kept_and_one_byte_over_is_not(self):
        recorder = self.make(lambda url, *, timeout, max_bytes: b"z" * 50)
        recorder(N.product_url("scales"), timeout=1, max_bytes=50)                                            # 정확히 호출 상한 — 남긴다(경계)
        self.assertEqual(([item["file"] for item in recorder.files], recorder.not_stored), (["raw_scales.json"], []))
        recorder = self.make(lambda url, *, timeout, max_bytes: b"z" * 51)
        recorder(N.product_url("kp_estimated"), timeout=1, max_bytes=50)                                      # 상한보다 1바이트 큼 — 남기지 않는다
        self.assertEqual([(item["product"], item["reason"]) for item in recorder.not_stored], [("kp_estimated", "TOO_LARGE")])
        self.assertEqual(recorder.files, [])

    def test_the_total_limit_holds_the_real_daily_file_with_room_to_spare(self):
        self.assertGreaterEqual(shadow_run.RAW_MAX_TOTAL_BYTES, 478190 * 2)                                  # 실제 일별 흑점수 사본(478,190 바이트)이 다른 제품과 함께 들어간다
        self.assertLessEqual(shadow_run.RAW_MAX_TOTAL_BYTES, 4 * 1024 * 1024)


class ProductLookupTest(unittest.TestCase):
    def test_the_lookup_knows_exactly_the_six_product_addresses(self):
        for product_id in N.PRODUCTS:
            self.assertEqual(S.product_id_of_url(N.product_url(product_id)), product_id)
        self.assertEqual(len({S.product_id_of_url(N.product_url(product_id)) for product_id in N.PRODUCTS}), 6)
        for bad in ("", None, 5, "https://services.swpc.noaa.gov/products/noaa-scales.json?x=1", "https://services.swpc.noaa.gov/products/noaa-scales.json#a", "http://services.swpc.noaa.gov/products/noaa-scales.json",
                    "https://SERVICES.swpc.noaa.gov/products/noaa-scales.json", "https://services.swpc.noaa.gov/products/noaa-scales.json ", "https://services.swpc.noaa.gov/products/"):
            self.assertIsNone(S.product_id_of_url(bad), bad)


class DefaultPolicyTest(RawBase):
    def test_under_the_default_constants_no_raw_file_exists_for_a_held_product(self):
        with HH.policy(HH.PRODUCTION_HELD, HH.PRODUCTION_FIRST):
            info, _lines = self.run_shadow("5")
        names = sorted(path.name for path in self.out_dir.iterdir() if path.is_file())
        self.assertEqual(info["attempts"], 4)
        self.assertEqual(names, ["raw_index.json", "raw_kp_estimated.json", "raw_ssn_daily.json", "raw_ssn_monthly.json", "raw_xray_flares.json", "run.json"])
        self.assertEqual([item["product"] for item in self.index()["responses"]], ["ssn_monthly", "kp_estimated", "xray_flares", "ssn_daily"])


class WorkflowAndReadersTest(unittest.TestCase):
    """읽기 확인(워크플로 T3 는 바꾸지 않았다): 결과 폴더 전체를 올리고, 후보 집계는 번호 폴더의 result.json 만 세고, 측정 도구는 .md 만 읽는다. 남긴 파일을 읽는 코드는 없다."""
    READING = {"read_text", "read_bytes", "open", "load", "loads", "iterdir", "glob", "rglob", "scandir", "listdir", "walk"}

    def test_the_workflow_uploads_the_whole_out_folder_and_counts_only_numbered_result_files(self):
        text = (ROOT / ".github" / "workflows" / "chance-shadow.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
        upload = text[text.index("uses: actions/upload-artifact"):]
        self.assertIn("${{ runner.temp }}/chance_shadow_out\n", upload)                                      # 폴더 전체(파일 목록이 아니다)
        self.assertNotRegex(upload, r"chance_shadow_out/\S*\.(?:json|md)")
        self.assertIn('results=("$SHADOW_OUT"/*/result.json)', text)                                           # 번호 폴더의 result.json 만 센다
        self.assertIn('posts=("$SHADOW_OUT"/**/*.md)', text)                                                   # 측정 도구는 .md 만 읽는다 — 원본 응답은 .json

    def test_nobody_reads_the_kept_files_the_names_appear_only_in_the_shadow_module_and_only_as_writes(self):
        owners = []
        for path in sorted((ROOT / "pipeline").rglob("*.py")) + [ROOT / "generator.py", ROOT / "blogger_generator.py"] + sorted((ROOT / "scripts").glob("*.py")):
            if re.search(r"RAW_PREFIX|RAW_INDEX_FILE|raw_index|RawRecorder", path.read_text(encoding="utf-8")):
                owners.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(owners, ["pipeline/shadow_run.py"])
        tree = ast.parse((ROOT / "pipeline" / "shadow_run.py").read_text(encoding="utf-8"))
        scanned = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in ("RawRecorder", "run_facts", "_run_clock")]
        self.assertEqual(sorted(node.name for node in scanned), ["RawRecorder", "_run_clock", "run_facts"])
        for node in scanned:
            calls = {child.func.attr if isinstance(child.func, ast.Attribute) else getattr(child.func, "id", "") for child in ast.walk(node) if isinstance(child, ast.Call)}
            self.assertEqual(calls & self.READING, set(), node.name)

    def test_the_shadow_module_text_still_follows_its_own_rules(self):
        text = (ROOT / "pipeline" / "shadow_run.py").read_text(encoding="utf-8")
        for banned in ("draft_flow", "from pipeline import drafts", "import drafts", "write_text_atomic(", "write_history(", "msvcrt", "ctypes", "quality_shadow", "import urllib", "import socket"):
            self.assertNotIn(banned, text, banned)


if __name__ == "__main__":
    unittest.main()
