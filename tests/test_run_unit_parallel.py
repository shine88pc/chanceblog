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
import inspect
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

import yaml

import _bootstrap

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import run_unit_parallel as rup  # noqa: E402

RUNNER = _bootstrap.ROOT / "scripts" / "run_unit_parallel.py"
WEIGHTS = _bootstrap.ROOT / "tests" / "unit_test_weights.json"
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
CLASH = '''import unittest

from fake_support import mark


class SameNameCase(unittest.TestCase):
    def __str__(self):
        return "every test prints this same name"

    def test_first(self):
        mark(self)

    def test_second(self):
        mark(self)
'''
WAIT_FOR_GO = '''import os
import time
import unittest
from pathlib import Path


class WaitTest(unittest.TestCase):
    def test_waits_for_the_go_file(self):
        # 부모 시험이 필요한 일(진행 줄 찍기·앞 묶음 넘기기·오류 뒤 정리)을 마치고 신호 파일을 만들 때까지 기다린다 — 시계에 기대지 않는다. 신호가 안 오면 25초 뒤 스스로 실패한다.
        # 설명 문장(docstring)을 일부러 쓰지 않는다: 그러면 시험 이름 줄이 시작하자마자 한 줄로 읽혀 '아직 읽은 시험 줄 없음' 이 시간에 따라 달라진다 — 없으면 이름 줄은 끝나야 읽힌다.
        go = Path(os.environ["FAKE_GO_FILE"])
        deadline = time.monotonic() + 25
        while not go.exists():
            if time.monotonic() > deadline:
                self.fail("the go file never appeared")
            time.sleep(0.02)
'''
BROKEN = "import fake_module_that_does_not_exist_zzz\n"

FAKE_FILES = {"fake_support.py": SUPPORT, "test_fake_alpha.py": ALPHA, "test_fake_beta.py": BETA, "test_fake_gamma.py": GAMMA, "test_fake_delta.py": DELTA}
ALPHA_IDS = ["test_fake_alpha.AlphaTest.test_one", "test_fake_alpha.AlphaTest.test_skipped", "test_fake_alpha.AlphaTest.test_with_docstring"]
BETA_IDS = ["test_fake_beta.BetaTest.test_sub", "test_fake_beta.BetaTest.test_two"]
GAMMA_IDS = ["test_fake_gamma.GammaTest.test_g1", "test_fake_gamma.GammaTest.test_g2", "test_fake_gamma.GammaTest.test_g3"]
DELTA_IDS = ["test_fake_delta.DeltaTest.test_d1"]
ALL_IDS = sorted(ALPHA_IDS + BETA_IDS + GAMMA_IDS + DELTA_IDS)
SKIPPED_IDS = {"test_fake_alpha.AlphaTest.test_skipped"}                # 돌지 않으므로 증거 파일도 남기지 않는다

# 재작업(독립 검증 S·Q 지적)에서 더한 가짜 시험 모듈들 — 모두 FAKE_FILES 에 더해 쓴다(FAKE_FILES 자체와 위의 개수는 그대로)
QUIT = '''import os
import unittest

from fake_support import mark


class QuitTest(unittest.TestCase):
    def test_a_first(self):
        mark(self)

    def test_b_quits_the_whole_process_with_exit_code_zero(self):
        mark(self)
        os._exit(0)

    def test_c_would_run_after_it(self):
        mark(self)
'''
SHARED_BASE = '''import unittest

from fake_support import mark


class SharedCases(unittest.TestCase):
    def test_shared_one(self):
        mark(self)

    def test_shared_two(self):
        mark(self)
'''
SHARED_A = '''import unittest

from fake_shared import SharedCases  # noqa: F401  (부모 시험 클래스를 가져온다 — 두 모듈에서 같은 시험 줄이 나온다)


class OwnATest(unittest.TestCase):
    def test_own_a(self):
        pass
'''
SHARED_B = SHARED_A.replace("OwnATest", "OwnBTest").replace("test_own_a", "test_own_b")
SHARED_C = '''from fake_shared import SharedCases  # noqa: F401
from fake_shared import SharedCases as SharedCasesAgain  # noqa: F401  (같은 클래스를 이름 둘로 가져온다 — 한 모듈 안에서 같은 시험 줄이 두 번 나온다)
'''
EXTRA_MATCHING = '''import unittest

from fake_support import mark


class ExtraTest(unittest.TestCase):
    def test_extra(self):
        mark(self)
'''                                                                         # 파일 이름이 test* 로 시작하지만 test_ 는 아니다(testing_extra.py) — 좁힌 패턴은 놓친다
OTHER_NOT_MATCHING = '''import unittest


class OtherTest(unittest.TestCase):
    def test_other(self):
        pass
'''                                                                         # 시험이 들어 있지만 이름이 test* 가 아니다(check_other.py) — 넓힌 패턴은 모은다


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

    def test_two_tests_that_print_the_same_line_name_stop_the_run_because_the_comparison_could_not_tell_them_apart(self):
        root = make_root(dict(FAKE_FILES, **{"test_fake_clash.py": CLASH}))
        self.addCleanup(shutil.rmtree, root, True)
        run_dir = Path(tempfile.mkdtemp(prefix="rup_run_"))
        self.addCleanup(shutil.rmtree, run_dir, True)
        with mock.patch.dict(os.environ, {"FAKE_RUN_DIR": str(run_dir)}):
            code, out = run_main("--root", str(root), "-j", "2")
        self.assertEqual(code, 1, out)
        self.assertIn("서로 다른 시험 id 가 같은 시험 줄 이름을 찍습니다", out)
        self.assertIn("every test prints this same name", out)
        self.assertEqual(list(run_dir.iterdir()), [], "대조할 수 없으면 아무것도 돌리지 않는다")

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
    """진행 줄과 묶음 넘기기 — 시계에 기대지 않는다. 기다리는 시험(WAIT_FOR_GO)이 부모가 할 일을 마치고 신호 파일을 만들 때까지 기다리게 해 순서를 강제한다
    (일이 안 되면 그 시험이 25초 뒤 스스로 실패해 시험이 빨개지고, 되면 시계와 상관없이 늘 통과한다)."""

    def prepare(self, files):
        root = make_root(files)
        self.addCleanup(shutil.rmtree, root, True)
        collected = rup.collect_tests(root)
        tests = {module: items for module, items in collected.tests.items() if items}
        labels = {label: test_id for items in tests.values() for label, test_id in items}
        return root, tests, labels, Path(root, "tests").resolve()

    def test_a_progress_line_is_printed_while_a_child_is_still_running(self):
        root, tests, labels, tests_dir = self.prepare({"test_fake_wait.py": WAIT_FOR_GO, "test_fake_gamma.py": GAMMA, "fake_support.py": SUPPORT})
        go = root / "go.signal"
        plan = [["test_fake_wait"], ["test_fake_gamma"]]
        lines = []

        def out(text):
            lines.append(text)
            if text.startswith("[진행") and "묶음 1:" in text:                    # 첫 묶음이 도는 동안 진행 줄이 찍혔다 — 이제 기다리던 시험을 놓아 준다
                go.write_text("go")

        with mock.patch.dict(os.environ, {"FAKE_GO_FILE": str(go)}):
            results = rup.run_plan(plan, root, tests_dir, labels, heartbeat=0.25, out=out)
        self.assertTrue(any(line.startswith("[진행") and "묶음 1:" in line for line in lines), lines)
        self.assertTrue(any("묶음 2/2 끝" in line for line in lines), lines)
        self.assertEqual([result.returncode for result in results], [0, 0], "기다리던 시험이 신호를 받고 통과했다 = 진행 줄은 그 시험이 도는 동안 찍혔다")
        self.assertEqual(rup.verify_run(tests, plan, results).problems, [])

    def test_a_finished_bin_is_handed_over_as_soon_as_the_bins_before_it_are_done_and_always_in_order(self):
        root, tests, labels, tests_dir = self.prepare({"test_fake_wait.py": WAIT_FOR_GO, "test_fake_gamma.py": GAMMA, "fake_support.py": SUPPORT})
        with self.subTest(case="빠른 묶음이 앞"):
            early_go = root / "early.signal"
            order = []

            def handed(index, result):
                order.append((index, result.returncode))
                if index == 0:                                                      # 앞 묶음이 넘어오는 순간 뒤 묶음(기다리는 시험)을 놓아 준다
                    early_go.write_text("go")

            with mock.patch.dict(os.environ, {"FAKE_GO_FILE": str(early_go)}):
                rup.run_plan([["test_fake_gamma"], ["test_fake_wait"]], root, tests_dir, labels, heartbeat=0, out=lambda text: None, on_ready=handed)
            self.assertEqual(order, [(0, 0), (1, 0)], "묶음 번호 순서로 넘어오고, 뒤 묶음이 끝나기 전에 앞 묶음이 이미 넘어왔다(뒤 묶음의 종료 코드 0 = 신호를 받았다)")
        with self.subTest(case="빠른 묶음이 뒤"):
            late_go = root / "late.signal"
            order = []

            def out(text):
                if "묶음 2/2 끝" in text:                                            # 뒤 묶음이 먼저 끝났다 — 이제 앞 묶음(기다리는 시험)을 놓아 준다
                    late_go.write_text("go")

            with mock.patch.dict(os.environ, {"FAKE_GO_FILE": str(late_go)}):
                rup.run_plan([["test_fake_wait"], ["test_fake_gamma"]], root, tests_dir, labels, heartbeat=0, out=out, on_ready=lambda index, result: order.append((index, result.returncode)))
            self.assertEqual(order, [(0, 0), (1, 0)], "뒤 묶음이 먼저 끝나도 앞 묶음 다음에 넘어온다")

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

    def test_every_exit_code_that_is_not_zero_marks_the_bin_as_failed(self):
        """변이 Q38(종료 코드 5 = 시험 0개를 통과로 셈)·Q39(신호로 죽은 자식의 음수 종료 코드를 무시)."""
        for code in (1, 2, 5, 130, -9, -15):
            with self.subTest(returncode=code):
                results = copy.deepcopy(self.results)
                results[0] = results[0]._replace(returncode=code)
                self.assertEqual(self.verdict(results=results).failed_bins, [1])

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
        for flag in ("--only", "--pattern", "--start-dir", "--root"):
            self.assertNotIn(flag, words, f"{flag} 는 일부만 돌리거나 모으는 범위를 바꾼다 — 부분 실행은 CI 줄에 쓰지 않는다")


# ----------------------------------------------------------------------------
# 7. 재작업 — 독립 검증(안전 S·시험 Q)의 지적을 시험으로: 종료 코드·기본값·모듈 건너뜀·출력 읽기·자식 환경·붙들린 줄기·진행 줄·정리·import 순서
#    (아래 시험은 변이 표의 살아남은 변이를 그대로 단언으로 옮긴 것이다 — 각 시험 설명에 어느 변이를 잡는지 적었다)
# ----------------------------------------------------------------------------
def plain_discover(root):
    """CI 의 옛 명령(`python -m unittest discover -s tests -v`)이 이 가짜 저장소에서 내는 출력 줄(다른 프로세스에서 — 실행기를 거치지 않는다)."""
    done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return done.stdout.decode("utf-8", "replace").splitlines()


def plain_discover_modules(root):
    """실행기를 거치지 않는 평범한 discover 가 모으는 시험 모듈 이름들(시험이 든 모듈만)."""
    code = ("import unittest\n"
            "def flat(suite):\n"
            "    for item in suite:\n"
            "        if isinstance(item, unittest.TestSuite):\n"
            "            yield from flat(item)\n"
            "        else:\n"
            "            yield item\n"
            "print('\\n'.join(sorted(test.id() for test in flat(unittest.TestLoader().discover('tests')))))\n")
    done = subprocess.run([sys.executable, "-c", code], cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return sorted({test_id.split(".")[0] for test_id in done.stdout.decode("utf-8", "replace").split()})


class ExitCodeTest(unittest.TestCase):
    """종료 코드의 마지막 연결(변이 Q01·Q02·Q04): 자식이 모두 종료 코드 0 이어도 대조가 어긋나면 1 이고, 중단은 통과가 아니다. 옛 직렬 실행은 같은 일을 아무 글 없이 초록으로 두었다."""

    def setUp(self):
        self.run_dir = Path(tempfile.mkdtemp(prefix="rup_run_"))
        self.addCleanup(shutil.rmtree, self.run_dir, True)

    def run_with(self, files, *args):
        root = make_root(files)
        self.addCleanup(shutil.rmtree, root, True)
        with mock.patch.dict(os.environ, {"FAKE_RUN_DIR": str(self.run_dir)}):
            return run_main("--root", str(root), *args)

    def test_a_test_that_ends_the_whole_process_with_exit_code_zero_still_fails_the_run(self):
        """중간에 os._exit(0) 하는 시험: 그 자식의 종료 코드는 0 이고 요약만 없다(= 실패한 묶음은 없고 대조 문제만 있다). 그래도 1 이어야 한다."""
        code, out = self.run_with(dict(FAKE_FILES, **{"test_fake_quit.py": QUIT}), "-j", "5")
        self.assertNotIn("실패(종료 코드", out, "모든 자식이 종료 코드 0 으로 끝났다 — 실패한 묶음은 없다")
        self.assertEqual(code, 1, out)
        self.assertIn("자식 출력에 `Ran N tests` 요약이 없습니다", out)
        self.assertIn("돌아야 할 시험 1개가 출력에 없습니다 — test_fake_quit.QuitTest.test_c_would_run_after_it", out)
        self.assertTrue(out.rstrip().splitlines()[-1].startswith("FAILED"), out[-300:])
        found = evidence(self.run_dir)
        self.assertIn("test_fake_quit.QuitTest.test_b_quits_the_whole_process_with_exit_code_zero", found, "그 시험까지는 돌았다(독립 증거)")
        self.assertNotIn("test_fake_quit.QuitTest.test_c_would_run_after_it", found, "뒤 시험은 정말 돌지 않았다(독립 증거)")


    def test_a_comparison_problem_alone_makes_the_exit_code_one_and_the_last_line_failed(self):
        """대조 문제만 있고 실패한 묶음이 없는 판정을 main 에 먹인다(변이 Q01: 종료 코드에서 문제 항을 뺌, Q02: 맨 끝 줄의 OK/FAILED 에서 뺌)."""
        root = make_root()
        self.addCleanup(shutil.rmtree, root, True)
        only_problems = rup.Verdict(["묶음 1: 돌아야 할 시험 1개가 출력에 없습니다"], [], 9, 8, 9, Counter(), [], [])           # failed_bins 가 비어 있다 = 자식은 모두 통과
        with mock.patch.object(rup, "verify_run", return_value=only_problems):
            code, out = run_main("--root", str(root), "-j", "2")
        self.assertEqual(code, 1, out)
        self.assertTrue(out.rstrip().splitlines()[-1].startswith("FAILED"), out[-300:])
        self.assertIn("대조 문제:", out)

    def test_a_clean_verdict_is_exit_code_zero_and_an_ok_last_line(self):
        root = make_root()
        self.addCleanup(shutil.rmtree, root, True)
        clean = rup.Verdict([], [], 9, 9, 9, Counter(), [], [])
        with mock.patch.object(rup, "verify_run", return_value=clean):
            code, out = run_main("--root", str(root), "-j", "2")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.rstrip().splitlines()[-1].startswith("OK"), out[-300:])

    def test_an_interrupt_is_never_reported_as_a_pass(self):
        """변이 Q04: 중단(KeyboardInterrupt)의 종료 코드를 0 으로 바꿈."""
        with mock.patch.object(rup, "_run", side_effect=KeyboardInterrupt):
            code, out = run_main("--plan-only")
        self.assertEqual(code, 130, out)
        self.assertIn("통과로 세지 않습니다", out)


class DefaultsTest(unittest.TestCase):
    """모으는 범위의 기본값(변이 Q22 — 패턴을 좁힘): 아무 인자 없이 부르면 CI 의 옛 명령 `discover -s tests` 와 같은 범위를 모은다."""

    def test_the_command_line_defaults_cover_the_whole_suite_like_the_ci_discover_command(self):
        args = rup.build_parser().parse_args([])
        self.assertEqual((args.start_dir, args.pattern, args.only, args.serial, args.plan_only), ("tests", "test*.py", [], [], False))
        self.assertEqual(args.pattern, inspect.signature(unittest.TestLoader.discover).parameters["pattern"].default, "unittest discover 의 기본 패턴과 같다")
        self.assertEqual(inspect.signature(rup.collect_tests).parameters["pattern"].default, args.pattern)
        self.assertEqual(inspect.signature(rup.collect_tests).parameters["start_dir"].default, args.start_dir)

    def test_with_no_pattern_argument_the_run_collects_exactly_the_modules_the_ci_discover_command_collects(self):
        root = make_root(dict(FAKE_FILES, **{"testing_extra.py": EXTRA_MATCHING, "check_other.py": OTHER_NOT_MATCHING}))
        self.addCleanup(shutil.rmtree, root, True)
        theirs = plain_discover_modules(root)
        self.assertIn("testing_extra", theirs, "이 시험의 전제: test_ 로 시작하지 않아도 test 로 시작하는 파일은 CI 의 명령이 모은다")
        self.assertNotIn("check_other", theirs, "이 시험의 전제: test 로 시작하지 않는 파일은 CI 의 명령이 모으지 않는다")
        code, out = run_main("--root", str(root), "-j", "2", "--plan-only")                     # 범위를 바꾸는 인자를 하나도 주지 않는다
        self.assertEqual(code, 0, out)
        self.assertIn(f"나누기 검사 통과: 시험이 있는 모듈 {len(theirs)}개가 정확히 한 묶음에 한 번씩 들어 있습니다", out)
        for module in theirs:
            self.assertIn(module, out)
        self.assertNotIn("check_other", out, "넓힌 패턴이면 시험이 든 다른 이름 파일까지 모은다")


class OutputShapeTest(unittest.TestCase):
    """출력 줄 모양에 기댄 대조가 옛 직렬 흐름과 다르게 반응하는 길(Q 권고 R6) — 거짓 경보는 안전한 방향이라 고치지 않고, 알려진 차이로 못박고 진단 글을 붙였다. 시험 없는 모듈 하나는 정상 통과한다."""

    def run_with(self, files, *args):
        root = make_root(files)
        self.addCleanup(shutil.rmtree, root, True)
        return run_main("--root", str(root), *args)


    def test_a_module_without_tests_is_left_out_of_the_plan_and_the_run_passes(self):
        """(d) 변이 Q20: 시험 없는 모듈을 나누기에 그대로 둠 → 나누기 검사가 '목록에 없는 모듈'로 거짓 빨강을 낸다."""
        code, out = self.run_with(dict(FAKE_FILES, **{"test_fake_empty.py": "import unittest\n\nVALUE = 1\n"}), "-j", "2")
        self.assertEqual(code, 0, out)
        self.assertIn("알림: 시험이 없는 모듈 1개는 돌릴 것이 없어 나누기에서 뺐습니다: test_fake_empty", out)
        self.assertIn("나누기 검사 통과: 시험이 있는 모듈 4개가 정확히 한 묶음에 한 번씩 들어 있습니다", out)
        self.assertIn("시험 id 대조: 처음 모은 9개 = 실제로 돈 9개", out)


class SharedBaseTest(unittest.TestCase):
    """같은 시험 줄이 여러 번 나올 때(검증 Q 권고 R3, 변이 Q12): 부모 시험 클래스를 가져온 모듈 둘(모듈마다 한 번씩)과, 같은 클래스를 이름 둘로 가져온 모듈 하나(한 모듈 안에서 두 번)가 있어도
    옛 직렬 흐름과 같은 횟수를 기대한다 — 묶음 하나에 몰려도, 묶음마다 나뉘어도."""

    FILES = {"fake_support.py": SUPPORT, "fake_shared.py": SHARED_BASE, "test_fake_shared_a.py": SHARED_A, "test_fake_shared_b.py": SHARED_B, "test_fake_shared_c.py": SHARED_C}

    def test_the_counts_agree_with_the_serial_flow_for_one_bin_and_for_separate_bins(self):
        root = make_root(self.FILES)
        self.addCleanup(shutil.rmtree, root, True)
        serial = rup.parse_summary(plain_discover(root))
        self.assertEqual((serial.ran, serial.status), (10, "OK"), "이 시험의 전제: 옛 직렬 흐름은 가져온 부모 시험 클래스의 시험을 모듈 a·b 에서 한 번씩, 모듈 c 에서 두 번씩 — 모두 열 번 돈다")
        for jobs in ("1", "2", "3"):
            with self.subTest(jobs=jobs):
                code, out = run_main("--root", str(root), "-j", jobs)
                self.assertEqual(code, 0, out)
                self.assertIn("시험 id 대조: 처음 모은 10개 = 실제로 돈 10개(빠짐 0 · 중복 0)", out)
                self.assertIn("Ran 10 tests in", out)


class ChildShapeTest(unittest.TestCase):
    """자식 프로세스가 옛 모양과 같게 뜨는지(검증 Q 권고 R8, 변이 Q28–Q31): 가짜 Popen 으로 인자·작업 폴더·환경·표준 입출력을 받아 단언한다."""

    def spawn(self, modules=("test_x",)):
        captured = {}

        def fake_popen(command, **kwargs):
            captured["command"], captured["kwargs"] = command, kwargs
            return types.SimpleNamespace(stdout=io.BytesIO(b""), poll=lambda: 0, returncode=0, wait=lambda: 0, kill=lambda: None)

        root, tests_dir = Path(tempfile.gettempdir(), "rup_shape_root"), Path(tempfile.gettempdir(), "rup_shape_root", "tests")
        with mock.patch.object(rup.subprocess, "Popen", side_effect=fake_popen):
            child = rup.Child(1, list(modules), root, tests_dir, {})
        child.thread.join(5)
        return captured["command"], captured["kwargs"], root, tests_dir

    def test_the_command_is_python_unbuffered_dash_m_unittest_verbose_and_the_modules(self):
        command, kwargs, root, tests_dir = self.spawn(("test_x", "test_y"))
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[-5:], ["-m", "unittest", "-v", "test_x", "test_y"])
        self.assertIn("-u", command[1:command.index("-m")], "줄이 만들어지는 대로 보내게 한다(변이 Q29)")
        self.assertNotIn("shell", kwargs)
        self.assertNotIn("-c", command)

    def test_the_child_starts_in_the_repository_root_like_the_serial_run(self):
        _, kwargs, root, _ = self.spawn()
        self.assertEqual(kwargs["cwd"], str(root), "변이 Q28")

    def test_the_tests_folder_is_first_on_pythonpath_and_an_earlier_value_is_kept_after_it(self):
        with mock.patch.dict(os.environ, {"PYTHONPATH": "/opt/extra"}):
            _, kwargs, _, tests_dir = self.spawn()
        self.assertEqual(kwargs["env"]["PYTHONPATH"].split(os.pathsep), [str(tests_dir), "/opt/extra"], "변이 Q30")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PYTHONPATH", None)
            _, kwargs, _, tests_dir = self.spawn()
        self.assertEqual(kwargs["env"]["PYTHONPATH"], str(tests_dir))

    def test_the_child_cannot_read_the_parents_standard_input_and_its_output_is_one_piped_stream(self):
        _, kwargs, _, _ = self.spawn()
        self.assertIs(kwargs.get("stdin"), subprocess.DEVNULL, "변이 Q31")
        self.assertIs(kwargs["stdout"], subprocess.PIPE)
        self.assertIs(kwargs["stderr"], subprocess.STDOUT)

    def test_the_interpreter_flags_follow_the_parents_utf8_and_bytecode_settings(self):
        shaped = {"utf8": (1, True, ["-u", "-X", "utf8", "-B"]), "plain": (0, False, ["-u"])}
        for name, (utf8_mode, no_bytecode, expected) in shaped.items():
            with self.subTest(name), mock.patch.object(rup, "sys", types.SimpleNamespace(flags=types.SimpleNamespace(utf8_mode=utf8_mode), dont_write_bytecode=no_bytecode)):
                self.assertEqual(rup.interpreter_flags(), expected)


class FinishedLogicTest(unittest.TestCase):
    """자식 출력을 끝까지 읽는 논리(검증 Q 권고 R4, 변이 Q26·Q32): 자식이 끝나도 읽는 스레드가 남은 줄을 다 읽을 때까지 기다리되, 손자가 줄기를 붙들면 GRACE 만큼만 기다린다.
    가짜 프로세스·가짜 스레드·제어하는 시계로 본다(시간에 기대지 않는다)."""

    class Proc:
        def __init__(self, returncode):
            self.returncode = returncode

        def poll(self):
            return self.returncode

    class Thread:
        def __init__(self, alive):
            self.alive = alive

        def is_alive(self):
            return self.alive

    def child(self, returncode, alive):
        child = rup.Child.__new__(rup.Child)
        child.proc, child.thread = self.Proc(returncode), self.Thread(alive)
        child.exited_at = child.ended = None
        return child

    def test_a_process_that_is_still_running_is_not_finished(self):
        self.assertFalse(self.child(None, alive=True).finished())
        self.assertFalse(self.child(None, alive=False).finished())

    def test_an_exited_process_whose_reader_is_still_alive_is_finished_only_after_the_grace(self):
        clock = [1000.0]
        fake_time = types.SimpleNamespace(monotonic=lambda: clock[0], sleep=time.sleep)
        with mock.patch.object(rup, "time", fake_time):
            child = self.child(0, alive=True)
            self.assertFalse(child.finished(), "끝난 순간에는 읽는 스레드가 남은 줄을 읽을 때까지 기다린다(변이 Q32: 곧바로 True)")
            clock[0] += rup.Child.GRACE - 0.5
            self.assertFalse(child.finished())
            clock[0] += 1.0
            self.assertTrue(child.finished(), "말미가 지나면 줄기를 붙든 손자를 더는 기다리지 않는다(변이 Q26: 말미가 사실상 무한)")

    def test_an_exited_process_whose_reader_has_ended_is_finished_at_once(self):
        self.assertTrue(self.child(0, alive=False).finished())


class FlushTest(unittest.TestCase):
    """출력 비우기(검증 Q 권고 R5, 변이 Q27): 표준 출력이 진짜 파이프(CI 처럼)일 때 진행 줄이 시험이 도는 동안 바로 도착한다 — 안 비우면 끝난 뒤에야 한꺼번에 온다.
    시계에 기대지 않는다: 도는 시험이 부모 시험이 '진행 줄을 받았다'는 신호 파일을 만들 때까지 기다린다(줄이 안 오면 그 시험이 25초 뒤 스스로 실패한다)."""

    def test_the_progress_line_reaches_a_reader_of_the_pipe_while_a_test_is_still_running(self):
        root = make_root({"fake_support.py": SUPPORT, "test_fake_wait.py": WAIT_FOR_GO})
        self.addCleanup(shutil.rmtree, root, True)
        go = root / "go.signal"
        env = {key: value for key, value in os.environ.items() if key != "PYTHONUNBUFFERED"}          # 버퍼를 풀어 두는 환경이면 이 시험이 아무것도 못 보인다
        env["FAKE_GO_FILE"] = str(go)
        proc = subprocess.Popen([sys.executable, str(RUNNER), "--root", str(root), "-j", "1", "--heartbeat", "0.3"], cwd=str(root), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        seen = []
        for raw in iter(proc.stdout.readline, b""):
            text = raw.decode("utf-8", "replace").rstrip("\r\n")
            seen.append(text)
            if text.startswith("[진행") and "묶음 1" in text and not go.exists():
                go.write_text("go")                                               # 진행 줄이 시험이 끝나기 전에 도착했다
        proc.stdout.close()
        proc.wait(timeout=60)
        self.assertEqual(proc.returncode, 0, "\n".join(seen[-30:]))
        self.assertTrue(go.exists())


class CleanupTest(unittest.TestCase):
    """오류 뒤 정리(검증 Q 참고 I2, 변이 Q33): 넘기는 쪽 호출이 실패해도 아직 도는 자식은 끝내고 기다리지 않는다."""

    def test_children_that_are_still_running_are_killed_when_the_hand_over_fails(self):
        root = make_root({"fake_support.py": SUPPORT, "test_fake_gamma.py": GAMMA, "test_fake_wait.py": WAIT_FOR_GO})
        self.addCleanup(shutil.rmtree, root, True)
        labels = {label: test_id for items in rup.collect_tests(root).tests.values() for label, test_id in items}

        def boom(index, result):
            raise RuntimeError("the hand-over callback failed")

        never = root / "never.signal"                                         # 만들지 않는다 — 기다리는 시험은 25초 뒤에야 스스로 끝난다
        with mock.patch.dict(os.environ, {"FAKE_GO_FILE": str(never)}):
            began = time.monotonic()
            with self.assertRaises(RuntimeError):
                rup.run_plan([["test_fake_gamma"], ["test_fake_wait"]], root, Path(root, "tests").resolve(), labels, heartbeat=0, out=lambda text: None, on_ready=boom)
            elapsed = time.monotonic() - began
        self.assertLess(elapsed, 18, "남은 자식을 끝내고 나왔다(안 끝냈다면 기다리는 시험이 스스로 실패하는 25초를 기다린다)")


class ImportOrderTest(unittest.TestCase):
    """import 경로 순서(검증 S-4): 자식은 `python -m unittest` 라 저장소 루트, 시험 폴더, 표준 라이브러리 순서이고 옛 흐름(discover -s tests)은 시험 폴더, 저장소 루트 순서다.
    두 폴더에 같은 이름의 모듈·패키지가 없으면 어느 순서든 같은 것을 불러온다 — 이 시험이 그것을 지킨다(시험 폴더에 저장소 루트와 같은 이름의 파일을 두면 실행기만 엉뚱한 모듈로 시험하게 된다)."""

    @staticmethod
    def importable_names(folder):
        """폴더 바로 아래에서 최상위 이름으로 불릴 수 있는 것: `이름.py` 의 이름과 하위 폴더 이름(숨김·바이트코드 캐시 폴더는 뺀다)."""
        names = set()
        for path in Path(folder).iterdir():
            if path.name.startswith(".") or path.name == "__pycache__":
                continue
            if path.is_file() and path.suffix == ".py":
                names.add(path.stem)
            elif path.is_dir():
                names.add(path.name)
        return names

    def test_no_name_in_the_tests_folder_is_also_in_the_repository_root_or_the_standard_library(self):
        tests_names = self.importable_names(_bootstrap.ROOT / "tests")
        self.assertGreater(len(tests_names), 1)
        self.assertEqual(sorted(tests_names & self.importable_names(_bootstrap.ROOT)), [], "저장소 루트와 같은 이름 — 자식은 루트를 시험 폴더보다 먼저 본다")
        self.assertEqual(sorted(tests_names & set(sys.stdlib_module_names)), [], "표준 라이브러리와 같은 이름")

    def test_the_check_does_find_a_clash_when_there_is_one(self):
        """음성 대조: 같은 이름이 있으면 위 비교가 실제로 비어 있지 않게 나온다(시험이 아무것도 못 잡는 껍데기가 아니다)."""
        folder = Path(tempfile.mkdtemp(prefix="rup_order_"))
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / "tests").mkdir()
        (folder / "helper.py").write_text("WHERE = 'ROOT'\n", encoding="utf-8")
        (folder / "tests" / "helper.py").write_text("WHERE = 'TESTS'\n", encoding="utf-8")
        (folder / "tests" / "json.py").write_text("WHERE = 'TESTS'\n", encoding="utf-8")
        tests_names = self.importable_names(folder / "tests")
        self.assertEqual(sorted(tests_names & self.importable_names(folder)), ["helper"])
        self.assertEqual(sorted(tests_names & set(sys.stdlib_module_names)), ["json"])


if __name__ == "__main__":
    unittest.main()
