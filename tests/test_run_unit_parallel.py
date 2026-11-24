"""병렬 시험 실행기(scripts/run_unit_parallel.py) 시험 — '시험을 지우거나 조용히 빠뜨리지 않는다'는 약속을 지킨다.

실행기는 CI 의 `python -m unittest discover -s tests -v` 한 프로세스를 여러 프로세스로 나눠 돈다. 나누면 시험이 조용히 사라질 길이 생기므로(묶음이 비거나, 모듈이 두 번 들어가거나,
자식이 중간에 끝나거나, 출력에서 시험 줄이 빠지는 것) 이 시험은 그 길마다 **빠짐을 만드는 변이**를 일부러 만들어 실행기가 반드시 실패한다는 것을 보인다.
작은 가짜 시험 폴더(임시 폴더)에서 진짜 자식 프로세스로 돌리고, 시험이 돌 때 파일 하나씩을 남기게 해 실행기의 출력과 따로 '진짜로 돈 시험'을 센다(독립된 증거).
변이는 복사본(깊은 복사·복사한 폴더)에서만 하고 끝나면 원본의 sha256 이 그대로인지 본다. 네트워크는 쓰지 않는다.
"""
import ast
import contextlib
import copy
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

import yaml

import _bootstrap

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import run_unit_parallel as rup  # noqa: E402

RUNNER = _bootstrap.ROOT / "scripts" / "run_unit_parallel.py"
WEIGHTS = _bootstrap.ROOT / "scripts" / "unit_test_weights.json"
GUARDRAILS = _bootstrap.ROOT / ".github" / "workflows" / "guardrails.yml"

SUPPORT = '''import os
from pathlib import Path


def mark(case):
    """진짜로 돈 증거: 시험이 돌 때 FAKE_RUN_DIR 폴더에 `시험id.프로세스번호` 빈 파일을 만든다(실행기의 출력과 따로 센다)."""
    folder = os.environ.get("FAKE_RUN_DIR")
    if folder:
        Path(folder, "%s.%d" % (case.id(), os.getpid())).touch()
'''
ALPHA = '''import unittest

from fake_support import mark


class AlphaTest(unittest.TestCase):
    def test_one(self):
        mark(self)

    def test_with_docstring(self):
        """설명이 있는 시험은 이름 줄과 설명 줄이 둘로 나뉘어 찍힌다."""
        mark(self)
        print("alpha stdout noise")

    @unittest.skip("건너뜀 한 개")
    def test_skipped(self):
        mark(self)
'''
BETA = '''import unittest

from fake_support import mark


class BetaTest(unittest.TestCase):
    def test_sub(self):
        mark(self)
        for number in range(3):
            with self.subTest(number=number):
                self.assertGreaterEqual(number, 0)

    def test_two(self):
        mark(self)
'''
GAMMA = '''import unittest

from fake_support import mark


class GammaTest(unittest.TestCase):
    def test_g1(self):
        mark(self)

    def test_g2(self):
        mark(self)

    def test_g3(self):
        mark(self)
'''
DELTA = '''import unittest

from fake_support import mark


class DeltaTest(unittest.TestCase):
    def test_d1(self):
        mark(self)
'''
FAILING = '''import unittest

from fake_support import mark


class FailingTest(unittest.TestCase):
    def test_bad(self):
        mark(self)
        self.assertEqual(1, 2)

    def test_fine(self):
        mark(self)
'''
SLOW = '''import time
import unittest


class SlowTest(unittest.TestCase):
    def test_slow(self):
        time.sleep(1.0)
'''
BROKEN = "import fake_module_that_does_not_exist_zzz\n"

FAKE_FILES = {"fake_support.py": SUPPORT, "test_fake_alpha.py": ALPHA, "test_fake_beta.py": BETA, "test_fake_gamma.py": GAMMA, "test_fake_delta.py": DELTA}
ALPHA_IDS = ["test_fake_alpha.AlphaTest.test_one", "test_fake_alpha.AlphaTest.test_skipped", "test_fake_alpha.AlphaTest.test_with_docstring"]
BETA_IDS = ["test_fake_beta.BetaTest.test_sub", "test_fake_beta.BetaTest.test_two"]
GAMMA_IDS = ["test_fake_gamma.GammaTest.test_g1", "test_fake_gamma.GammaTest.test_g2", "test_fake_gamma.GammaTest.test_g3"]
DELTA_IDS = ["test_fake_delta.DeltaTest.test_d1"]
ALL_IDS = sorted(ALPHA_IDS + BETA_IDS + GAMMA_IDS + DELTA_IDS)
SKIPPED_IDS = {"test_fake_alpha.AlphaTest.test_skipped"}                # 돌지 않으므로 증거 파일도 남기지 않는다


def make_root(files=None):
    """가짜 저장소 루트(임시 폴더)를 만든다 — 안에 tests 폴더. 돌려주는 값은 폴더 경로(호출한 쪽이 지운다)."""
    root = Path(tempfile.mkdtemp(prefix="rup_fake_"))
    (root / "tests").mkdir()
    for name, source in (files or FAKE_FILES).items():
        (root / "tests" / name).write_text(source, encoding="utf-8")
    return root


def folder_digest(folder):
    """폴더 안 모든 파일의 (상대 경로, sha256) 목록 하나의 해시 — 변이가 원본을 건드리지 않았는지 보는 데 쓴다(바이트코드 캐시는 뺀다)."""
    sums = []
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            sums.append((path.relative_to(folder).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    return hashlib.sha256(repr(sums).encode("utf-8")).hexdigest()


def data_digest(*values):
    return hashlib.sha256(repr(values).encode("utf-8")).hexdigest()


def evidence(run_dir):
    """FAKE_RUN_DIR 의 증거 파일에서 {시험 id: [프로세스 번호, ...]}."""
    found = {}
    for path in Path(run_dir).iterdir():
        test_id, _, pid = path.name.rpartition(".")
        found.setdefault(test_id, []).append(pid)
    return found


def execute(root, jobs, between=None, mutate_plan=None, serial=()):
    """실행기의 단계(모으기 → 나누기 → 돌리기)를 그대로 거쳐 (tests, plan, results) 를 돌려준다. between 은 모은 뒤·돌리기 전에 부르는 곳(파일을 몰래 고치는 변이용),
    mutate_plan 은 나눈 뒤의 나누기를 바꾸는 곳이다."""
    collected = rup.collect_tests(root)
    assert not collected.failed, collected.failed
    tests = {module: items for module, items in collected.tests.items() if items}
    weights, _ = rup.module_weights({module: len(items) for module, items in tests.items()}, None)
    plan, _ = rup.build_plan(weights, jobs, serial)
    if between:
        between()
    if mutate_plan:
        plan = mutate_plan(plan)
    labels = {label: test_id for items in tests.values() for label, test_id in items}
    results = rup.run_plan(plan, root, Path(root, "tests").resolve(), labels, heartbeat=0, out=lambda text: None)
    return tests, plan, results


def run_main(*args):
    """실행기 main 을 이 프로세스 안에서 부른다(자식은 진짜 프로세스). (종료 코드, 출력 글)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = rup.main(["--heartbeat", "0", *args])
    return code, buffer.getvalue()


# ----------------------------------------------------------------------------
# 1. 출력 읽기
# ----------------------------------------------------------------------------
LABELS = {"test_a (mod.A.test_a)": "mod.A.test_a", "test_b (mod.A.test_b)": "mod.A.test_b", "test_old (mod.B)": "mod.B.test_old"}


class ParseTest(unittest.TestCase):
    def test_a_one_line_result_a_two_line_description_and_a_line_with_noise_are_all_start_lines(self):
        lines = ["test_a (mod.A.test_a) ... ok",                              # 한 줄 모양(3.12)
                 "test_b (mod.A.test_b)", "첫 줄 설명 ... noise from the test", "ok",       # 설명이 있는 시험: 이름 줄이 따로, 소음이 같은 줄에 붙고 결과는 다음 줄
                 "test_old (mod.B) ... skipped 'x'"]                          # 3.10 모양
        parsed = rup.parse_child(lines, LABELS)
        self.assertEqual(parsed.executed, Counter({"test_a (mod.A.test_a)": 1, "test_b (mod.A.test_b)": 1, "test_old (mod.B)": 1}))

    def test_lines_that_only_look_like_tests_are_not_counted(self):
        lines = ["  test_a (mod.A.test_a) [x=1] ... FAIL",                     # 실패한 하위 시험 줄(들여쓰기·꼬리표)
                 "unknown (mod.Z.unknown) ... ok", "an ordinary log line", "", "test_a (mod.A.test_a) was mentioned in a log"]
        self.assertEqual(rup.parse_child(lines, LABELS).executed, Counter())

    def test_a_test_started_twice_is_counted_twice(self):
        self.assertEqual(rup.parse_child(["test_a (mod.A.test_a) ... ok", "test_a (mod.A.test_a) ... ok"], LABELS).executed["test_a (mod.A.test_a)"], 2)

    def test_lines_with_arrival_seconds_are_read_the_same_way(self):
        self.assertEqual(rup.parse_child([(0.5, "test_a (mod.A.test_a) ... ok")], LABELS).executed["test_a (mod.A.test_a)"], 1)

    def test_failure_headers_are_collected_for_the_recap(self):
        lines = ["FAIL: test_a (mod.A.test_a)", "ERROR: test_b (mod.A.test_b)", "FAIL", "FAILED (failures=1)", "a FAIL: in the middle"]
        self.assertEqual(rup.parse_child(lines, LABELS).failures, ["FAIL: test_a (mod.A.test_a)", "ERROR: test_b (mod.A.test_b)"])

    def test_summary_shapes(self):
        cases = [(["Ran 3 tests in 0.004s", "", "OK"], (3, "OK", {})),
                 (["Ran 10 tests in 1.5s", "", "OK (skipped=2)"], (10, "OK", {"skipped": 2})),
                 (["Ran 7 tests in 0.2s", "", "FAILED (failures=1, errors=2, skipped=3)"], (7, "FAILED", {"failures": 1, "errors": 2, "skipped": 3})),
                 (["Ran 4 tests in 0.2s", "", "OK (skipped=1, expected failures=2)"], (4, "OK", {"skipped": 1, "expected failures": 2})),
                 (["Ran 0 tests in 0.000s", "", "NO TESTS RAN"], (0, "NO TESTS RAN", {})),
                 (["Ran 1 test in 0.000s", "", "FAILED (unexpected successes=1)"], (1, "FAILED", {"unexpected successes": 1}))]
        for lines, (ran, status, counts) in cases:
            with self.subTest(lines[-1]):
                summary = rup.parse_summary(lines)
                self.assertEqual((summary.ran, summary.status, summary.counts), (ran, status, counts))

    def test_the_last_summary_wins_and_a_missing_summary_is_none(self):
        text = ["Ran 99 tests in 0.1s", "", "OK", "some log", "Ran 3 tests in 0.004s", "", "FAILED (failures=1)"]
        self.assertEqual((rup.parse_summary(text).ran, rup.parse_summary(text).status), (3, "FAILED"))
        self.assertIsNone(rup.parse_summary(["test_a (mod.A.test_a) ... ok", "Traceback (most recent call last):"]))
        self.assertIsNone(rup.parse_summary(["Ran 3 tests in 0.1s", "no result line follows"]))

    def test_the_real_unittest_output_of_this_python_is_read_correctly(self):
        """이 파이썬(3.10·3.12 등)이 실제로 찍는 한 줄·두 줄 모양을 그대로 읽는다 — 이름 줄 모양이 버전마다 다르다(`(모듈.클래스)` 와 `(모듈.클래스.시험)`)."""
        root = make_root()
        self.addCleanup(shutil.rmtree, root, True)
        code = "import sys, unittest; sys.path.insert(0, %r); unittest.main(module=None)" % str(root / "tests")
        done = subprocess.run([sys.executable, "-c", code, "-v", "test_fake_alpha"], cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        lines = done.stdout.decode("utf-8", "replace").splitlines()
        collected = rup.collect_tests(root)
        labels = {label: test_id for items in collected.tests.values() for label, test_id in items}
        parsed = rup.parse_child(lines, labels)
        self.assertEqual(sorted(labels[label] for label in parsed.executed.elements()), ALPHA_IDS)
        self.assertEqual((parsed.summary.ran, parsed.summary.status, parsed.summary.counts), (3, "OK", {"skipped": 1}))


# ----------------------------------------------------------------------------
# 2. 무게·나누기
# ----------------------------------------------------------------------------
class WeightsTest(unittest.TestCase):
    def write(self, text):
        folder = Path(tempfile.mkdtemp(prefix="rup_w_"))
        self.addCleanup(shutil.rmtree, folder, True)
        path = folder / "w.json"
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_valid_table_is_read_and_underscore_keys_are_notes(self):
        table, reason = rup.load_weights(self.write('{"_note": "x", "a": 1.5, "b": 3}'))
        self.assertEqual((table, reason), ({"a": 1.5, "b": 3.0}, None))

    def test_broken_tables_are_refused_with_a_reason(self):
        for text in ("not json", "[1, 2]", "{}", '{"_only": "note"}', '{"a": 0}', '{"a": -1}', '{"a": "3"}', '{"a": null}', '{"a": true}', '{"a": NaN}', '{"a": Infinity}'):
            with self.subTest(text):
                table, reason = rup.load_weights(self.write(text))
                self.assertIsNone(table)
                self.assertTrue(reason)
        self.assertIsNone(rup.load_weights(Path(tempfile.gettempdir()) / "rup_no_such_file_zzz.json")[0])

    def test_without_a_table_the_weight_is_the_test_count_and_never_zero(self):
        weights, unknown = rup.module_weights({"a": 10, "b": 0, "c": 3}, None)
        self.assertEqual((weights, unknown), ({"a": 10.0, "b": 1.0, "c": 3.0}, []))

    def test_a_module_missing_from_the_table_gets_the_median_of_the_table(self):
        weights, unknown = rup.module_weights({"a": 1, "b": 1, "c": 1, "new": 1}, {"a": 1.0, "b": 9.0, "c": 4.0, "gone": 100.0})
        self.assertEqual(unknown, ["new"])
        self.assertEqual(weights, {"a": 1.0, "b": 9.0, "c": 4.0, "new": 6.5})            # 표 값 1·4·9·100 의 중앙값 6.5(표에만 있는 모듈 'gone' 도 중앙값에 든다)

    def test_the_shipped_table_does_not_spell_out_the_name_of_the_ai_merge_rule_module(self):
        """AI 병합 정책 모듈의 이름 글자가 저장소 파일에 그대로 있으면 NotWiredTest(tests 의 정책 문서 시험, '아무도 이 모듈을 부르지 않는다')가 빨개진다.
        그래서 그 이름이 든 시험 모듈 둘은 표에 적지 않았다(표에 없는 모듈은 중앙값을 받으니 시험은 빠지지 않는다). 표를 다시 만들 때 그 둘을 넣지 않는다."""
        text = WEIGHTS.read_text(encoding="utf-8")
        self.assertNotIn("merge_" + "policy", text)
        table, _ = rup.load_weights(WEIGHTS)
        self.assertGreater(len(table), 150)

    def test_the_shipped_table_is_valid_and_names_test_modules(self):
        table, reason = rup.load_weights(WEIGHTS)
        self.assertIsNone(reason)
        self.assertGreater(len(table), 150)
        self.assertTrue(all(name.startswith("test_") for name in table), [name for name in table if not name.startswith("test_")])
        self.assertTrue(all(0 < value < 100 for value in table.values()))


def spread(weights, jobs, serial=()):
    plan, loads = rup.build_plan(weights, jobs, serial)
    return plan, loads


WEIGHTS_ALPHA = {"m%02d" % number: float(1 + (number * 7) % 13) for number in range(30)}


class PlanTest(unittest.TestCase):
    def test_every_module_is_in_exactly_one_bin_for_every_job_count(self):
        for jobs in range(1, 12):
            with self.subTest(jobs=jobs):
                plan, loads = spread(WEIGHTS_ALPHA, jobs)
                flat = [module for modules in plan for module in modules]
                self.assertEqual(sorted(flat), sorted(WEIGHTS_ALPHA))
                self.assertEqual(len(flat), len(set(flat)))
                self.assertTrue(all(plan), "빈 묶음이 없다")
                self.assertEqual(len(plan), min(jobs, len(WEIGHTS_ALPHA)))
                self.assertEqual(len(loads), len(plan))
                self.assertAlmostEqual(sum(loads), sum(WEIGHTS_ALPHA.values()))

    def test_the_same_input_always_gives_the_same_plan_in_any_input_order(self):
        reference = spread(WEIGHTS_ALPHA, 4)
        shuffled = dict(reversed(list(WEIGHTS_ALPHA.items())))
        self.assertEqual(spread(shuffled, 4), reference)
        self.assertEqual(spread(dict(sorted(WEIGHTS_ALPHA.items(), key=lambda item: (item[1], item[0]))), 4), reference)
        self.assertEqual([spread(WEIGHTS_ALPHA, 4) for _ in range(3)], [reference] * 3)

    def test_the_heaviest_modules_start_in_different_bins_and_the_load_is_balanced(self):
        weights = {"huge1": 40.0, "huge2": 35.0, "huge3": 30.0, "huge4": 25.0}
        weights.update({"small%02d" % number: 1.0 for number in range(40)})
        plan, loads = spread(weights, 4)
        owners = [next(number for number, modules in enumerate(plan) if heavy in modules) for heavy in ("huge1", "huge2", "huge3", "huge4")]
        self.assertEqual(sorted(owners), [0, 1, 2, 3], "무거운 넷은 서로 다른 묶음에서 먼저 시작한다")
        self.assertLessEqual(max(loads) - min(loads), 1.0 + 1e-9)
        total, biggest = sum(weights.values()), max(weights.values())
        self.assertLessEqual(max(loads), total / 4 + biggest)                           # 목록 스케줄링의 일반 한계

    def test_modules_inside_a_bin_keep_the_sorted_order_of_the_serial_run(self):
        plan, _ = spread(WEIGHTS_ALPHA, 3)
        for modules in plan:
            self.assertEqual(modules, sorted(modules))

    def test_serial_modules_always_share_one_bin_even_when_they_are_heavy(self):
        weights = {"a": 50.0, "b": 50.0, "c": 50.0, "d": 1.0, "e": 1.0, "f": 1.0}
        for jobs in (2, 3, 4, 8):
            with self.subTest(jobs=jobs):
                plan, _ = spread(weights, jobs, serial=["a", "b"])
                bins = [number for number, modules in enumerate(plan) if "a" in modules or "b" in modules]
                self.assertEqual(len(bins), 1)
                self.assertTrue({"a", "b"} <= set(plan[bins[0]]))
                self.assertEqual(sorted(module for modules in plan for module in modules), sorted(weights))

    def test_a_new_module_without_a_weight_still_gets_into_a_bin(self):
        weights, _ = rup.module_weights({"m1": 5, "m2": 5, "brand_new": 5}, {"m1": 10.0, "m2": 2.0})
        plan, _ = rup.build_plan(weights, 2)
        self.assertIn("brand_new", [module for modules in plan for module in modules])

    def test_check_plan_accepts_a_correct_plan_and_names_every_kind_of_fault(self):
        tests = {"a": [("a1", "a.1")], "b": [("b1", "b.1")], "c": [("c1", "c.1")], "empty": []}
        self.assertEqual(rup.check_plan([["a", "b"], ["c"]], tests), [])
        self.assertTrue(any("비어" in text for text in rup.check_plan([["a", "b"], ["c"], []], tests)))
        self.assertTrue(any("어느 묶음에도 없" in text and "c" in text for text in rup.check_plan([["a", "b"]], tests)))
        self.assertTrue(any("2개 묶음" in text for text in rup.check_plan([["a", "b"], ["b", "c"]], tests)))
        self.assertTrue(any("목록에 없" in text for text in rup.check_plan([["a", "b"], ["c", "ghost"]], tests)))


# ----------------------------------------------------------------------------
# 3. 모으기 — discover 와 같고, 불러오기 실패·시험 없음을 숨기지 않는다
# ----------------------------------------------------------------------------
class CollectTest(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_the_ids_are_exactly_what_unittest_discover_finds(self):
        collected = rup.collect_tests(self.root)
        ours = sorted(test_id for items in collected.tests.values() for _, test_id in items)
        code = ("import unittest\n"
                "def flat(suite):\n"
                "    for item in suite:\n"
                "        if isinstance(item, unittest.TestSuite):\n"
                "            yield from flat(item)\n"
                "        else:\n"
                "            yield item\n"
                "print('\\n'.join(sorted(test.id() for test in flat(unittest.TestLoader().discover('tests')))))\n")     # CI 가 쓰는 discover 를 다른 프로세스에서 그대로
        done = subprocess.run([sys.executable, "-c", code], cwd=str(self.root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        theirs = done.stdout.decode("utf-8", "replace").split()
        self.assertEqual(ours, theirs)
        self.assertEqual(ours, ALL_IDS)
        self.assertEqual(collected.failed, [])
        self.assertEqual(sorted(collected.tests), ["test_fake_alpha", "test_fake_beta", "test_fake_delta", "test_fake_gamma"])   # 도우미 파일(fake_support)은 시험 모듈이 아니다

    def test_the_label_is_what_unittest_prints_and_maps_to_the_id(self):
        collected = rup.collect_tests(self.root)
        labels = dict(collected.tests["test_fake_alpha"])
        self.assertEqual(sorted(labels.values()), ALPHA_IDS)
        for label, test_id in labels.items():
            self.assertIn(label.split(" ")[0], test_id)
            self.assertTrue(label.startswith("test_"), label)

    def test_collecting_leaves_the_process_as_it_was(self):
        before = (list(sys.path), os.getcwd())
        rup.collect_tests(self.root)
        self.assertEqual((list(sys.path), os.getcwd()), before)
        folder = str(self.root.resolve())
        leftovers = sorted(name for name, module in list(sys.modules.items()) if str(getattr(module, "__file__", "") or "").startswith(folder))
        self.assertEqual(leftovers, [], "가짜 시험 모듈이 이 프로세스에 남지 않는다")

    def test_an_import_failure_is_reported_and_not_dropped(self):
        (self.root / "tests" / "test_fake_broken.py").write_text(BROKEN, encoding="utf-8")
        collected = rup.collect_tests(self.root)
        self.assertEqual(len(collected.failed), 1)
        self.assertIn("test_fake_broken", collected.failed[0][0])
        self.assertIn("fake_module_that_does_not_exist_zzz", collected.failed[0][1])
        self.assertEqual(sorted(test_id for items in collected.tests.values() for _, test_id in items), ALL_IDS)     # 나머지는 그대로 모은다

    def test_a_module_without_tests_is_listed_with_an_empty_list(self):
        (self.root / "tests" / "test_fake_empty.py").write_text("import unittest\n\nVALUE = 1\n", encoding="utf-8")
        self.assertEqual(rup.collect_tests(self.root).tests["test_fake_empty"], [])

    def test_a_missing_start_folder_is_an_error_not_an_empty_list(self):
        shutil.rmtree(self.root / "tests")
        with self.assertRaises(Exception):
            rup.collect_tests(self.root)


# ----------------------------------------------------------------------------
# 4. 처음부터 끝까지 — 진짜 자식 프로세스로
# ----------------------------------------------------------------------------
class EndToEndTest(unittest.TestCase):
    """같은 가짜 폴더를 -j 3 으로 한 번 돌려 두고(클래스에서 한 번) 여러 시험이 그 결과를 읽는다."""

    @classmethod
    def setUpClass(cls):
        cls.root = make_root()
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        cls.run_dir = Path(tempfile.mkdtemp(prefix="rup_run_"))
        cls.addClassCleanup(shutil.rmtree, cls.run_dir, True)
        broken_weights = cls.root / "bad_weights.json"
        broken_weights.write_text('{"test_fake_alpha": -5}', encoding="utf-8")                 # 못 읽는 가중치 파일 — 경고만 하고 시험은 그대로 모두 돈다
        with mock.patch.dict(os.environ, {"FAKE_RUN_DIR": str(cls.run_dir)}):
            cls.code, cls.out = run_main("--root", str(cls.root), "-j", "3", "--weights", str(broken_weights))
        cls.evidence = evidence(cls.run_dir)

    def test_it_passes_and_every_test_really_ran_once_by_the_independent_evidence(self):
        self.assertEqual(self.code, 0, self.out)
        self.assertEqual(sorted(self.evidence), sorted(set(ALL_IDS) - SKIPPED_IDS))
        self.assertTrue(all(len(pids) == 1 for pids in self.evidence.values()), self.evidence)      # 한 시험은 정확히 한 번

    def test_the_bins_are_printed_in_order_with_headers_and_the_summary_matches(self):
        headers = [line for line in self.out.splitlines() if line.startswith("===== 묶음 ")]
        self.assertEqual(headers[:3], ["===== 묶음 1/3 =====", "===== 묶음 2/3 =====", "===== 묶음 3/3 ====="])
        self.assertIn("시험 id 대조: 처음 모은 9개 = 실제로 돈 9개(빠짐 0 · 중복 0)", self.out)
        self.assertIn("Ran 9 tests in", self.out)
        self.assertTrue(self.out.rstrip().endswith("OK (skipped=1)"), self.out[-200:])

    def test_the_skip_is_counted_like_the_serial_run_does(self):
        self.assertIn("skipped '건너뜀 한 개'", self.out)
        self.assertEqual(self.out.count("OK (skipped=1)"), 2)                    # 자식 요약 한 번 + 합친 요약 한 번

    def test_an_unreadable_weights_file_only_warns(self):
        self.assertIn("경고: 가중치 파일 bad_weights.json 을(를) 쓰지 못해 시험 개수 비율로 나눕니다", self.out)

    def test_the_output_of_every_child_stays_together_and_in_bin_order(self):
        position = 0
        for number in (1, 2, 3):
            start = self.out.index(f"===== 묶음 {number}/3 =====")
            end = self.out.index(f"----- 묶음 {number}/3 끝 -----")
            self.assertLess(position, start, "묶음은 번호 순서로 찍힌다")
            self.assertLess(start, end)
            self.assertEqual(self.out[start:end].count("Ran "), 1, "한 덩어리 안에 자식 하나의 요약만 있다(섞이지 않았다)")
            position = end
        self.assertLess(position, self.out.index("===== 병렬 실행 요약 ====="))

    def test_the_description_line_and_the_noise_do_not_hide_a_test(self):
        self.assertIn("alpha stdout noise", self.out)
        self.assertIn("test_fake_alpha.AlphaTest.test_with_docstring", sorted(self.evidence))             # 설명이 있는 시험도 실제로 돌았고 대조에서 빠지지 않았다(통과 + 대조 9 = 9)


class SerialAndPlanOnlyTest(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.run_dir = Path(tempfile.mkdtemp(prefix="rup_run_"))
        self.addCleanup(shutil.rmtree, self.run_dir, True)

    def run_with_evidence(self, *args):
        with mock.patch.dict(os.environ, {"FAKE_RUN_DIR": str(self.run_dir)}):
            return run_main("--root", str(self.root), *args)

    def test_plan_only_shows_the_plan_and_runs_nothing(self):
        code, out = self.run_with_evidence("-j", "2", "--plan-only")
        self.assertEqual(code, 0, out)
        self.assertIn("--plan-only", out)
        self.assertIn("나누기 검사 통과: 시험이 있는 모듈 4개가 정확히 한 묶음에 한 번씩 들어 있습니다", out)
        self.assertNotIn("===== 묶음", out)
        self.assertNotIn("Ran ", out)
        self.assertEqual(list(self.run_dir.iterdir()), [], "시험이 하나도 돌지 않았다")

    def test_serial_modules_run_in_the_same_process(self):
        code, out = self.run_with_evidence("-j", "4", "--serial", "test_fake_alpha", "test_fake_gamma.py")
        self.assertEqual(code, 0, out)
        found = evidence(self.run_dir)
        pids = {module: {pid for test_id, values in found.items() if test_id.startswith(module + ".") for pid in values}
                for module in ("test_fake_alpha", "test_fake_beta", "test_fake_gamma", "test_fake_delta")}
        self.assertEqual(len(pids["test_fake_alpha"]), 1)
        self.assertEqual(pids["test_fake_alpha"], pids["test_fake_gamma"], "묶어 둔 모듈은 같은 프로세스에서 돈다")
        self.assertTrue(pids["test_fake_beta"].isdisjoint(pids["test_fake_alpha"]))
        self.assertIn("묶음 3개", out)                                              # alpha+gamma 가 한 덩어리라 항목은 셋(덩어리·beta·delta)

    def test_a_weights_file_puts_the_heaviest_module_in_a_bin_of_its_own(self):
        weights = self.root / "w.json"
        weights.write_text('{"_note": "x", "test_fake_alpha": 1, "test_fake_beta": 50, "test_fake_gamma": 1, "test_fake_delta": 1}', encoding="utf-8")
        code, out = self.run_with_evidence("-j", "2", "--plan-only", "--weights", str(weights))
        self.assertEqual(code, 0, out)
        self.assertIn("묶음 1/2: 모듈 1개", out)
        self.assertIn("test_fake_beta", out.split("묶음 2/2")[0])
        self.assertIn("가중치 파일(w.json)", out)

    def test_only_runs_just_the_chosen_modules_and_compares_against_them(self):
        code, out = self.run_with_evidence("-j", "2", "--only", "test_fake_gamma", "test_fake_delta.py")
        self.assertEqual(code, 0, out)
        self.assertIn("알림: --only 로 고른 모듈 2개(시험 4개)만 돕니다 — 전체가 아닌 부분 실행입니다", out)
        self.assertEqual(sorted(evidence(self.run_dir)), sorted(GAMMA_IDS + DELTA_IDS), "고른 모듈의 시험만 돌았다(독립 증거)")
        self.assertIn("시험 id 대조: 처음 모은 4개 = 실제로 돈 4개", out)
        self.assertIn("Ran 4 tests in", out)
        self.assertIn("부분 실행(--only): 고른 모듈의 시험만 돌았습니다", out)
        self.assertTrue(out.rstrip().endswith("OK (부분 실행)"), out[-200:])                   # 부분 실행은 맨 끝 줄에서 전체 통과와 구별된다

    def test_only_with_a_name_that_has_no_tests_is_a_usage_error(self):
        code, out = self.run_with_evidence("-j", "2", "--only", "test_fake_gamma", "test_fake_typo")
        self.assertEqual(code, 2, out)
        self.assertIn("test_fake_typo", out)
        self.assertEqual(list(self.run_dir.iterdir()), [], "오타가 있으면 일부만 조용히 돌지 않고 아무것도 돌리지 않는다")

    def test_a_job_count_above_the_limit_is_lowered_and_noted(self):
        code, out = self.run_with_evidence("-j", "99", "--plan-only")
        self.assertEqual(code, 0, out)
        self.assertIn(f"알림: -j 99 는 상한 {rup.MAX_JOBS} 를 넘어 {rup.MAX_JOBS} 로 줄입니다", out)
        self.assertIn("묶음 4개", out)                                              # 모듈이 4개라 묶음도 4개

    def test_a_serial_name_that_has_no_tests_is_a_usage_error_not_ignored(self):
        code, out = self.run_with_evidence("-j", "2", "--serial", "test_fake_typo")
        self.assertEqual(code, 2, out)
        self.assertIn("test_fake_typo", out)
        self.assertEqual(list(self.run_dir.iterdir()), [])

    def test_a_job_count_below_one_is_a_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            rup.main(["--root", str(self.root), "-j", "0", "--plan-only"])
        self.assertEqual(caught.exception.code, 2)

    def test_the_default_job_count_never_exceeds_the_cpu_count_or_the_runner_limit(self):
        for cpus, expected in ((1, 1), (2, 2), (4, 4), (6, 4), (64, 4)):
            with self.subTest(cpus=cpus), mock.patch.object(rup.os, "cpu_count", return_value=cpus):
                self.assertEqual(rup.default_jobs(), expected)
        with mock.patch.object(rup.os, "cpu_count", return_value=None):
            self.assertEqual(rup.default_jobs(), 1)


class TimingsTest(unittest.TestCase):
    """--timings-out 의 재료: 출력 줄 도착 시각으로 모듈별 초를 어림한다(새 가중치 표를 만들 때 쓴다)."""

    TESTS = {"mod_a": [("a1 (mod_a.A.a1)", "mod_a.A.a1"), ("a2 (mod_a.A.a2)", "mod_a.A.a2")], "mod_b": [("b1 (mod_b.B.b1)", "mod_b.B.b1")]}

    def test_seconds_go_to_the_module_of_the_test_that_just_ended(self):
        lines = [(1.0, "a1 (mod_a.A.a1) ... ok"), (3.0, "a2 (mod_a.A.a2) ... ok"),
                 (3.5, "b1 (mod_b.B.b1)"), (4.0, "설명 줄 ... noise"), (9.0, "ok")]               # 설명이 있는 시험: 이름 줄은 시작에, 결과 줄은 끝에 도착한다
        results = [rup.ChildResult(1, ["mod_a", "mod_b"], 0, lines, 9.0)]
        self.assertEqual(rup.module_seconds(self.TESTS, [["mod_a", "mod_b"]], results), {"mod_a": 2.0, "mod_b": 6.0})      # 첫 시험(불러오는 시간이 섞임)은 0

    def test_an_empty_output_gives_an_empty_table(self):
        self.assertEqual(rup.module_seconds(self.TESTS, [["mod_a"]], [rup.ChildResult(1, ["mod_a"], 0, [], 0.0)]), {})

    def test_the_command_line_writes_a_table_that_can_be_used_as_weights(self):
        root = make_root()
        self.addCleanup(shutil.rmtree, root, True)
        out_file = root / "timings.json"
        code, out = run_main("--root", str(root), "-j", "2", "--only", "test_fake_gamma", "test_fake_delta", "--timings-out", str(out_file))
        self.assertEqual(code, 0, out)
        table, reason = rup.load_weights(out_file)                                            # 그대로 --weights 에 쓸 수 있는 모양(0 이하 값이 없다)
        self.assertIsNone(reason)
        self.assertTrue(set(table) <= {"test_fake_gamma", "test_fake_delta"} and table, table)


class FailureReportTest(unittest.TestCase):
    def test_a_failing_test_fails_the_run_but_every_test_still_runs_and_is_listed_in_the_recap(self):
        files = dict(FAKE_FILES, **{"test_fake_failing.py": FAILING})
        root = make_root(files)
        self.addCleanup(shutil.rmtree, root, True)
        run_dir = Path(tempfile.mkdtemp(prefix="rup_run_"))
        self.addCleanup(shutil.rmtree, run_dir, True)
        with mock.patch.dict(os.environ, {"FAKE_RUN_DIR": str(run_dir)}):
            code, out = run_main("--root", str(root), "-j", "2")
        self.assertEqual(code, 1, out)
        self.assertIn("FAILED (failures=1, skipped=1)", out)
        self.assertIn("실패·오류 시험:", out)
        self.assertIn("FAIL: test_bad (test_fake_failing.FailingTest", out)
        self.assertIn("시험 id 대조: 처음 모은 11개 = 실제로 돈 11개", out)             # 실패해도 대조는 통과 — 빠뜨린 것이 아니다
        self.assertEqual(sorted(evidence(run_dir)), sorted(set(ALL_IDS + ["test_fake_failing.FailingTest.test_bad", "test_fake_failing.FailingTest.test_fine"]) - SKIPPED_IDS))

    def test_an_import_failure_runs_nothing_and_fails(self):
        files = dict(FAKE_FILES, **{"test_fake_broken.py": BROKEN})
        root = make_root(files)
        self.addCleanup(shutil.rmtree, root, True)
        run_dir = Path(tempfile.mkdtemp(prefix="rup_run_"))
        self.addCleanup(shutil.rmtree, run_dir, True)
        with mock.patch.dict(os.environ, {"FAKE_RUN_DIR": str(run_dir)}):
            code, out = run_main("--root", str(root), "-j", "2")
        self.assertEqual(code, 1, out)
        self.assertIn("불러오기에 실패한 시험 모듈이 1개", out)
        self.assertIn("fake_module_that_does_not_exist_zzz", out)
        self.assertIn("FAILED (불러오기 실패=1)", out)
        self.assertNotIn("===== 묶음", out)
        self.assertEqual(list(run_dir.iterdir()), [], "불러오기에 실패하면 나머지 시험도 돌리지 않고 끝낸다(조용히 빼지 않는다)")

    def test_the_child_output_is_printed_before_the_comparison_so_a_crash_in_it_keeps_the_log(self):
        root = make_root()
        self.addCleanup(shutil.rmtree, root, True)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), mock.patch.object(rup, "verify_run", side_effect=RuntimeError("대조 중 예기치 않은 오류")), self.assertRaises(RuntimeError):
            rup.main(["--heartbeat", "0", "--root", str(root), "-j", "2"])
        out = buffer.getvalue()
        self.assertIn("===== 묶음 1/2 =====", out)
        self.assertIn("Ran ", out)                                                  # 자식의 요약까지 이미 찍혀 있다(예외는 숨기지 않고 그대로 올라가 종료 코드는 0 이 아니다)
        self.assertNotIn("병렬 실행 요약", out)

    def test_a_plan_that_fails_the_plan_check_runs_nothing(self):
        """나누기 함수가 틀린 나누기(빈 묶음)를 내도 돌리기 전에 나누기 검사가 막는다 — 시험은 하나도 돌지 않고 실패."""
        root = make_root()
        self.addCleanup(shutil.rmtree, root, True)
        run_dir = Path(tempfile.mkdtemp(prefix="rup_run_"))
        self.addCleanup(shutil.rmtree, run_dir, True)
        with mock.patch.object(rup, "build_plan", return_value=([["test_fake_alpha"], []], [3.0, 1.0])), mock.patch.dict(os.environ, {"FAKE_RUN_DIR": str(run_dir)}):
            code, out = run_main("--root", str(root), "-j", "2")
        self.assertEqual(code, 1, out)
        self.assertIn("실패: 나누기 검사에 걸렸습니다", out)
        self.assertIn("묶음 2 이(가) 비어 있습니다", out)
        self.assertIn("모듈 test_fake_gamma 이(가) 어느 묶음에도 없습니다", out)
        self.assertEqual(list(run_dir.iterdir()), [], "나누기 검사에 걸리면 어떤 시험도 돌리지 않는다")

    def test_no_tests_at_all_is_a_failure_not_a_quiet_pass(self):
        root = make_root({"fake_support.py": SUPPORT})
        self.addCleanup(shutil.rmtree, root, True)
        code, out = run_main("--root", str(root), "-j", "2")
        self.assertEqual(code, 1, out)
        self.assertIn("시험이 하나도 없습니다", out)

    def test_a_folder_with_only_empty_modules_is_also_a_failure(self):
        root = make_root({"test_fake_empty.py": "import unittest\n"})
        self.addCleanup(shutil.rmtree, root, True)
        code, out = run_main("--root", str(root), "-j", "2")
        self.assertEqual(code, 1, out)

    def test_a_missing_tests_folder_is_a_failure(self):
        root = Path(tempfile.mkdtemp(prefix="rup_fake_"))
        self.addCleanup(shutil.rmtree, root, True)
        code, out = run_main("--root", str(root), "-j", "2")
        self.assertEqual(code, 1, out)
        self.assertIn("시험을 모으지 못했습니다", out)


class HeartbeatTest(unittest.TestCase):
    def test_a_progress_line_is_printed_while_a_child_is_still_running(self):
        root = make_root({"test_fake_slow.py": SLOW, "test_fake_gamma.py": GAMMA, "fake_support.py": SUPPORT})
        self.addCleanup(shutil.rmtree, root, True)
        collected = rup.collect_tests(root)
        tests = {module: items for module, items in collected.tests.items() if items}
        labels = {label: test_id for items in tests.values() for label, test_id in items}
        plan = [["test_fake_slow"], ["test_fake_gamma"]]
        lines = []
        results = rup.run_plan(plan, root, Path(root, "tests").resolve(), labels, heartbeat=0.25, out=lines.append)
        self.assertTrue(any(line.startswith("[진행") and "묶음 1:" in line for line in lines), lines)
        self.assertTrue(any("묶음 2/2 끝" in line for line in lines), lines)
        self.assertEqual(rup.verify_run(tests, plan, results).problems, [])

    def test_a_finished_bin_is_handed_over_as_soon_as_the_bins_before_it_are_done_and_always_in_order(self):
        root = make_root({"test_fake_slow.py": SLOW, "test_fake_gamma.py": GAMMA, "fake_support.py": SUPPORT})
        self.addCleanup(shutil.rmtree, root, True)
        collected = rup.collect_tests(root)
        labels = {label: test_id for items in collected.tests.values() for label, test_id in items}
        tests_dir = Path(root, "tests").resolve()
        for plan, early in ((([["test_fake_gamma"], ["test_fake_slow"]]), True), (([["test_fake_slow"], ["test_fake_gamma"]]), False)):
            with self.subTest(plan=plan):
                stamps = []
                began = time.monotonic()
                rup.run_plan(plan, root, tests_dir, labels, heartbeat=0, out=lambda text: None, on_ready=lambda index, result: stamps.append((index, time.monotonic() - began)))
                self.assertEqual([index for index, _ in stamps], [0, 1], "묶음 번호 순서로 넘어온다")
                if early:
                    self.assertLess(stamps[0][1] + 0.3, stamps[1][1], stamps)           # 빠른 첫 묶음은 느린 둘째 묶음이 끝나기 전에 이미 넘어왔다(한 묶음이 멈춰도 앞 묶음의 출력은 로그에 있다)

    def test_a_bin_without_modules_is_refused_because_unittest_would_then_search_the_current_folder(self):
        with self.assertRaises(ValueError):
            rup.Child(1, [], Path(tempfile.gettempdir()), Path(tempfile.gettempdir()), {})


# ----------------------------------------------------------------------------
# 5. 빠짐을 만드는 변이 — 모두 잡혀야 한다
# ----------------------------------------------------------------------------
class CompletenessMutationTest(unittest.TestCase):
    """한 번 제대로 돌려 둔 결과(나누기·자식 출력)를 복사해서 시험이 빠지는 모양으로 틀리게 만든다 — 원본은 그대로여야 한다(sha256)."""

    @classmethod
    def setUpClass(cls):
        cls.root = make_root()
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        cls.tests, cls.plan, cls.results = execute(cls.root, 3)
        cls.fingerprint = (data_digest(cls.plan, cls.results), folder_digest(cls.root))

    @classmethod
    def tearDownClass(cls):
        assert (data_digest(cls.plan, cls.results), folder_digest(cls.root)) == cls.fingerprint, "변이가 원본을 건드렸다"

    def verdict(self, plan=None, results=None):
        return rup.verify_run(self.tests, self.plan if plan is None else plan, self.results if results is None else results)

    def texts(self, verdict):
        return " | ".join(verdict.problems)

    def start_line_position(self, results, module, bin_index=None):
        """결과 속에서 module 의 시험 시작 줄 하나의 (묶음 번호, 줄 번호)."""
        owned = {label for label, _ in self.tests[module]}
        for number, result in enumerate(results):
            for position, (_, text) in enumerate(result.lines):
                if text.split(" ... ", 1)[0] in owned:
                    return number, position
        raise AssertionError(module)

    def test_the_unmutated_run_is_clean(self):
        verdict = self.verdict()
        self.assertEqual((verdict.problems, verdict.failed_bins), ([], []))
        self.assertEqual((verdict.expected_total, verdict.executed_total, verdict.ran_total), (9, 9, 9))
        self.assertEqual(verdict.counts["skipped"], 1)

    def test_mutation_an_empty_bin_is_caught(self):
        plan = copy.deepcopy(self.plan)
        lost = plan[1][:]
        plan[1] = []
        problems = self.texts(self.verdict(plan=plan))
        self.assertIn("묶음 2 이(가) 비어 있습니다", problems)
        for module in lost:
            self.assertIn(f"모듈 {module} 이(가) 어느 묶음에도 없습니다", problems)

    def test_mutation_a_module_in_two_bins_is_caught(self):
        plan = copy.deepcopy(self.plan)
        twice = plan[0][0]
        plan[1].append(twice)
        self.assertIn(f"모듈 {twice} 이(가) 2개 묶음에 들어 있습니다", self.texts(self.verdict(plan=plan)))

    def test_mutation_a_module_dropped_from_the_plan_is_caught(self):
        plan = copy.deepcopy(self.plan)
        dropped = plan[2].pop()
        verdict = self.verdict(plan=plan)
        self.assertIn(f"모듈 {dropped} 이(가) 어느 묶음에도 없습니다", self.texts(verdict))
        self.assertTrue(any("묶음 3: 기대보다 더 돈 시험" in text for text in verdict.problems), "나누기 검사 말고 묶음별 대조도 따로 잡는다")

    def test_mutation_a_module_that_was_never_collected_is_caught(self):
        plan = copy.deepcopy(self.plan)
        plan[0].append("test_fake_ghost")
        self.assertIn("test_fake_ghost 은(는) 처음 모은 시험 목록에 없습니다", self.texts(self.verdict(plan=plan)))

    def test_mutation_deleting_one_test_line_from_a_child_output_is_caught(self):
        results = copy.deepcopy(self.results)
        number, position = self.start_line_position(results, "test_fake_gamma")
        deleted = results[number].lines.pop(position)[1]
        verdict = self.verdict(results=results)
        self.assertTrue(any(f"묶음 {number + 1}: 돌아야 할 시험 1개가 출력에 없습니다" in text for text in verdict.problems), verdict.problems)
        self.assertTrue(any("전체 대조: 처음 모은 시험 중 1개가 실제로 돌지 않았습니다" in text for text in verdict.problems), (deleted, verdict.problems))
        self.assertEqual((verdict.expected_total, verdict.executed_total), (9, 8))

    def test_mutation_duplicating_a_test_line_is_caught(self):
        results = copy.deepcopy(self.results)
        number, position = self.start_line_position(results, "test_fake_beta")
        results[number].lines.insert(position, results[number].lines[position])
        verdict = self.verdict(results=results)
        self.assertTrue(any("기대보다 더 돈 시험 1개" in text for text in verdict.problems), verdict.problems)
        self.assertTrue(any("전체 대조: 처음 모은 것보다 1개가 더(중복) 돌았습니다" in text for text in verdict.problems), verdict.problems)

    def test_mutation_swapping_a_test_line_for_another_tests_name_is_caught(self):
        results = copy.deepcopy(self.results)
        number, position = self.start_line_position(results, "test_fake_gamma")
        other = next(label for label, _ in self.tests["test_fake_delta"])
        results[number].lines[position] = (results[number].lines[position][0], other + " ... ok")
        verdict = self.verdict(results=results)
        self.assertTrue(any("돌아야 할 시험 1개가 출력에 없습니다" in text for text in verdict.problems), verdict.problems)
        self.assertTrue(any("기대보다 더 돈 시험 1개" in text or "전체 대조: 처음 모은 것보다 1개가 더" in text for text in verdict.problems), verdict.problems)

    def test_mutation_a_child_that_ended_early_without_a_summary_is_caught(self):
        results = copy.deepcopy(self.results)
        cut = next(position for position, (_, text) in enumerate(results[1].lines) if text.startswith("Ran "))
        del results[1].lines[cut - 1:]
        problems = self.texts(self.verdict(results=results))
        self.assertIn("묶음 2: 자식 출력에 `Ran N tests` 요약이 없습니다", problems)

    def test_mutation_an_emptied_child_output_is_caught(self):
        results = copy.deepcopy(self.results)
        results[0].lines.clear()
        problems = self.texts(self.verdict(results=results))
        self.assertIn("묶음 1: 돌아야 할 시험", problems)
        self.assertIn("요약이 없습니다", problems)

    def test_mutation_a_summary_count_that_disagrees_is_caught(self):
        for delta in (1, -1):
            with self.subTest(delta=delta):
                results = copy.deepcopy(self.results)
                lines = results[2].lines
                position = next(index for index, (_, text) in enumerate(lines) if text.startswith("Ran "))
                words = lines[position][1].split(" ")
                words[1] = str(int(words[1]) + delta)
                lines[position] = (lines[position][0], " ".join(words))
                self.assertIn("자식이 돌았다고 한 시험 수", self.texts(self.verdict(results=results)))

    def test_mutation_a_zero_exit_code_with_a_failed_summary_is_caught(self):
        results = copy.deepcopy(self.results)
        lines = results[0].lines
        position = max(index for index, (_, text) in enumerate(lines) if text.startswith("OK"))
        lines[position] = (lines[position][0], "FAILED (failures=1)")
        self.assertIn("종료 코드는 0 인데 요약은 FAILED 입니다", self.texts(self.verdict(results=results)))

    def test_mutation_a_failing_exit_code_with_an_ok_summary_is_caught(self):
        results = copy.deepcopy(self.results)
        results[0] = results[0]._replace(returncode=1)
        verdict = self.verdict(results=results)
        self.assertIn("종료 코드는 1 인데 요약은 OK 입니다", self.texts(verdict))
        self.assertEqual(verdict.failed_bins, [1])

    def test_mutation_too_few_child_results_for_the_plan_is_caught(self):
        verdict = self.verdict(results=copy.deepcopy(self.results)[:-1])
        self.assertTrue(any("자식 결과가" in text for text in verdict.problems), verdict.problems)

    def test_the_per_bin_comparison_alone_catches_a_plan_that_lies(self):
        """나누기 검사(check_plan)가 없다고 해도 묶음별 대조가 따로 잡는다 — 방어가 한 겹이 아니다(전체 대조만 따로 보이는 것은 아래 RealMutationTest)."""
        plan = copy.deepcopy(self.plan)
        plan[0].pop()
        with mock.patch.object(rup, "check_plan", return_value=[]):
            verdict = self.verdict(plan=plan)
        self.assertTrue(any("묶음 1: 기대보다 더 돈 시험" in text for text in verdict.problems), verdict.problems)


class RealMutationTest(unittest.TestCase):
    """진짜 자식 프로세스로 만드는 변이: 거짓말하는 나누기를 그대로 돌린 경우, 모은 뒤에 시험 파일이 바뀐 경우. 변이는 이 시험의 사본 폴더에서만 하고 끝나면 원복해 sha256 을 견준다."""

    def setUp(self):
        self.root = make_root()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.original = folder_digest(self.root)

    def test_a_plan_that_omits_a_module_and_runs_another_twice_is_caught_by_the_global_comparison_alone(self):
        def mutate(plan):
            flat = sorted(module for modules in plan for module in modules)
            self.assertEqual(flat, ["test_fake_alpha", "test_fake_beta", "test_fake_delta", "test_fake_gamma"])
            return [["test_fake_beta", "test_fake_gamma"], ["test_fake_beta", "test_fake_delta"]]        # alpha 는 빠지고 beta 는 두 번(자식도 그대로 돈다)

        run_dir = Path(tempfile.mkdtemp(prefix="rup_run_"))
        self.addCleanup(shutil.rmtree, run_dir, True)
        with mock.patch.dict(os.environ, {"FAKE_RUN_DIR": str(run_dir)}):
            tests, plan, results = execute(self.root, 2, mutate_plan=mutate)
        found = evidence(run_dir)
        self.assertFalse(any(test_id.startswith("test_fake_alpha.") for test_id in found), "alpha 는 실제로 돌지 않았다(독립 증거)")
        self.assertEqual({len(found[test_id]) for test_id in BETA_IDS}, {2}, "beta 는 실제로 두 번 돌았다(독립 증거)")
        with mock.patch.object(rup, "check_plan", return_value=[]):                  # 나누기 검사를 빼도 — 각 묶음은 시킨 대로 돌았으니 묶음별 대조는 맞다 — 전체 대조가 잡는다
            verdict = rup.verify_run(tests, plan, results)
        text = " | ".join(verdict.problems)
        self.assertIn("전체 대조: 처음 모은 시험 중 3개가 실제로 돌지 않았습니다", text)          # alpha 의 세 줄
        self.assertIn("전체 대조: 처음 모은 것보다 2개가 더(중복) 돌았습니다", text)             # beta 의 두 줄이 한 번 더
        self.assertIn("전체 대조: 자식 요약의 시험 수 합 8 이 처음 모은 9 과 다릅니다", text)         # 각 자식은 시킨 대로 돌았으니 묶음별 요약은 맞고, 합만 모자란다
        self.assertFalse(any(problem.startswith("묶음 ") for problem in verdict.problems), "묶음별 대조는 거짓말한 계획을 믿으므로 통과한다")
        full = rup.verify_run(tests, plan, results)                                  # 나누기 검사까지 켜면 계획의 거짓말도 직접 짚는다
        self.assertTrue(any("모듈 test_fake_beta 이(가) 2개 묶음에 들어 있습니다" in problem for problem in full.problems), full.problems)
        self.assertTrue(any("모듈 test_fake_alpha 이(가) 어느 묶음에도 없습니다" in problem for problem in full.problems), full.problems)
        self.assertEqual(self.original, folder_digest(self.root))

    def test_a_test_removed_added_and_a_module_deleted_after_collecting_are_all_caught_and_restoring_gives_the_same_sha256(self):
        tests_dir = self.root / "tests"

        def tamper():
            (tests_dir / "test_fake_beta.py").write_text(BETA.replace("    def test_two(self):\n        mark(self)\n", ""), encoding="utf-8")        # 시험 하나 삭제
            (tests_dir / "test_fake_gamma.py").write_text(GAMMA + "\n    def test_g4(self):\n        mark(self)\n", encoding="utf-8")               # 시험 하나 추가
            (tests_dir / "test_fake_delta.py").unlink()                                                                                         # 모듈 통째로 삭제

        tests, plan, results = execute(self.root, 3, between=tamper)
        self.assertNotEqual(self.original, folder_digest(self.root), "변이가 실제로 들어갔다")
        verdict = rup.verify_run(tests, plan, results)
        text = " | ".join(verdict.problems)
        self.assertIn("test_fake_beta.BetaTest.test_two", text, "삭제된 시험이 빠졌다고 이름까지 짚는다")
        self.assertIn("test_fake_delta.DeltaTest.test_d1", text, "지워진 모듈의 시험이 빠졌다고 짚는다")
        self.assertIn("자식이 돌았다고 한 시험 수", text, "추가된 시험은 시험 수 어긋남으로 잡힌다")
        self.assertTrue(verdict.failed_bins, "지워진 모듈은 자식의 불러오기 오류(종료 코드 0 아님)로도 드러난다")
        for name in ("test_fake_beta.py", "test_fake_gamma.py", "test_fake_delta.py"):               # 원복
            (tests_dir / name).write_text(FAKE_FILES[name], encoding="utf-8")
        self.assertEqual(self.original, folder_digest(self.root), "원복하면 sha256 이 처음과 같다")
        tests, plan, results = execute(self.root, 3)
        self.assertEqual(rup.verify_run(tests, plan, results).problems, [], "원복한 폴더는 다시 깨끗하게 통과한다")


# ----------------------------------------------------------------------------
# 6. 약속과 배선 — 표준 라이브러리만·3.10 문법·워크플로가 부르는 모양
# ----------------------------------------------------------------------------
class ContractTest(unittest.TestCase):
    def test_the_runner_imports_only_the_standard_library(self):
        tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names.add((node.module or "").split(".")[0])
        self.assertTrue(names)
        self.assertEqual(sorted(name for name in names if name not in sys.stdlib_module_names), [])

    def test_the_runner_source_is_valid_python_3_10_syntax(self):
        ast.parse(RUNNER.read_text(encoding="utf-8"), feature_version=(3, 10))

    def test_the_command_line_has_help_and_rejects_unknown_flags(self):
        done = subprocess.run([sys.executable, str(RUNNER), "-h"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        text = done.stdout.decode("utf-8", "replace")
        self.assertEqual(done.returncode, 0, text)
        for flag in ("--plan-only", "--weights", "--serial", "-j"):
            self.assertIn(flag, text)
        bad = subprocess.run([sys.executable, str(RUNNER), "--no-such-flag"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(bad.returncode, 2)
        shortened = subprocess.run([sys.executable, str(RUNNER), "--plan"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(shortened.returncode, 2, "줄임말(--plan)로 다른 옵션을 부르지 않는다")

    def test_the_workflow_unit_test_step_calls_this_runner_with_files_that_exist(self):
        steps = yaml.safe_load(GUARDRAILS.read_text(encoding="utf-8"))["jobs"]["validate"]["steps"]
        step = next(step for step in steps if step.get("name") == "단위 테스트")
        words = step["run"].split()
        self.assertEqual(words[:2], ["python", "scripts/run_unit_parallel.py"])
        self.assertTrue((_bootstrap.ROOT / words[1]).is_file())
        self.assertIn("--weights", words)
        self.assertTrue((_bootstrap.ROOT / words[words.index("--weights") + 1]).is_file())
        self.assertNotIn("--plan-only", words, "계획만 보이고 끝내는 인자로는 시험이 돌지 않는다")


if __name__ == "__main__":
    unittest.main()
