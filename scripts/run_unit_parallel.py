"""단위 테스트 병렬 실행기(시제품 — 운영자 승인 전 T3 라 병합하지 않는 안).

CI 의 `python -m unittest discover -s tests -v` 는 시험 모듈 약 200개를 한 프로세스에서 차례로 돌려 칸당 5–10분이 걸리고 칸 제한(10분)에 가깝다.
이 실행기는 같은 시험을 한 job 안의 여러 프로세스로 나눠 돈다. 시험을 지우거나 조용히 건너뛰지 않는다는 것을 아래 장치로 보인다.

동작
 1. 부모가 CI 와 같은 방식(`tests` 폴더가 곧 최상위 폴더 — `unittest` 의 `discover`)으로 **모든 시험을 먼저 모은다**. 시험 줄에 찍히는 이름(`str(시험)`)을 모듈별로 적어 둔다.
    불러오기에 실패한 모듈(`_FailedTest`)이 하나라도 있으면 아무 시험도 돌리지 않고 그대로 실패로 보고하고 끝낸다(조용히 빼지 않는다). 시험이 하나도 없어도 실패다.
    모듈 최상위에서 스스로 `SkipTest` 를 던진 모듈(`discover` 가 `unittest.loader.ModuleSkipped.<모듈>` 시험 하나로 바꿔 돌려주는 것)은 알림에 적고 옛 직렬 흐름처럼 시험 하나·건너뜀 하나로 센다.
    그 밖에 불러오기 기록에도 불러오기 실패·모듈 건너뜀에도 없는 알 수 없는 시험이 있으면 아무것도 돌리지 않고 실패한다.
 2. 모듈을 N개 묶음으로 나눈다. 무거운 모듈부터 가장 가벼운 묶음에 넣고(같은 입력이면 늘 같은 나누기), 한 모듈의 시험은 쪼개지 않는다(클래스·모듈 준비가 깨지지 않게).
    무게는 `--weights`(모듈→초 JSON)의 값, 표에 없는 새 모듈은 표 값의 중앙값, 표가 없으면 시험 개수다. `--serial` 로 적은 모듈은 늘 같은 묶음(같은 프로세스)에서 돈다.
 3. 묶음마다 자식 프로세스 `python -m unittest -v 모듈…` 를 띄워 병렬로 돌린다. 시험 폴더는 PYTHONPATH 로 준다 — 그런데 `python -m` 은 현재 폴더(저장소 루트)를 import 경로 맨 앞에 두므로
    자식의 순서는 저장소 루트, 시험 폴더, 표준 라이브러리다. `discover -s tests` 는 시험 폴더가 저장소 루트보다 앞이므로 두 순서는 **같지 않다**. 두 폴더에 같은 이름이 없으면 결과가 같고,
    그것은 시험(`ImportOrderTest`)이 지킨다. 출력은 자식별로 모아 두었다가 묶음이 끝나는 대로(앞 묶음이 다 찍힌 뒤에) `===== 묶음 i/N =====` 머리글과 함께 한 덩어리씩 번호 순서로 찍는다
    (도는 동안은 몇 초마다 진행 줄만 찍는다. 진행 줄의 시험 이름은 도는 시험이 아니라 마지막으로 읽은 시험 줄이다).
 4. 끝나면 자식 출력의 시험 줄에서 **실제로 돈 시험 이름의 모음**을 읽어 처음에 모은 것과 **정확히 같은지**(빠짐·중복·개수 합) 확인한다(시험 줄 이름과 시험 id 가 일대일인 것은 돌리기 전에 확인한다). 묶음 나누기 자체(모든 모듈이 정확히 한 묶음)도
    돌리기 전에 한 번, 돌린 뒤에 한 번 더 본다. 하나라도 어긋나면 시험이 모두 통과했어도 실패다. 건너뜀(skip)은 지금과 똑같이 합쳐 센다.

사용: python scripts/run_unit_parallel.py [-j N] [--weights 파일] [--serial 모듈 …] [--plan-only] [--only 모듈 …]   (--only 는 실험용 부분 실행이고 CI 는 쓰지 않는다)
종료 코드: 0 모두 통과(대조도 통과) / 1 실패(시험 실패·대조 실패·불러오기 실패·시험 없음) / 2 사용법 오류
파이썬 3.10 이상, 표준 라이브러리만 쓴다.
"""
import argparse
import collections
import importlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import textwrap
import threading
import time
import unittest
from pathlib import Path

MAX_JOBS = 8                  # -j 의 상한
DEFAULT_JOBS_CAP = 4          # -j 기본 = min(CPU 개수, 이 값) — 진짜 CI 러너(리눅스, CPU 4개)에서 서로 CPU 를 빼앗지 않는 개수
HEARTBEAT_SECONDS = 30.0      # 도는 동안 진행 줄을 찍는 간격
BAR = "-" * 70


# ---------------------------------------------------------------------------
# 1. 모으기 — CI 의 discover 와 같은 방식
# ---------------------------------------------------------------------------
Collected = collections.namedtuple("Collected", "tests failed skipped unknown", defaults=((), ()))
ModuleSkip = collections.namedtuple("ModuleSkip", "module reason")
# tests  : {모듈 이름: [(시험 줄 이름, 시험 id), ...]}  — 모듈마다 discover 가 낸 순서, 시험이 없는 모듈은 빈 목록
# failed : [(시험 id, 오류 글), ...]               — 불러오기에 실패한 모듈(_FailedTest)
# skipped: [ModuleSkip(모듈, 이유), ...]            — 불러올 때 모듈 최상위에서 스스로 SkipTest 를 던진 모듈(discover 가 시험 하나로 바꿔 돌려준다)
# unknown: [시험 id, ...]                         — 어느 모듈의 불러오기 기록에도 없는데 불러오기 실패도 모듈 건너뜀도 아닌 시험(알 수 없는 것은 조용히 빼지 않는다)


def iter_tests(suite):
    """TestSuite 안의 시험(낱개)을 차례로 낸다."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_tests(item)
        else:
            yield item


def is_failed_import(test):
    return type(test).__name__ == "_FailedTest"


def _skip_method(test):
    """ModuleSkipped 시험의 시험 메서드(건너뜀 표시가 붙은 함수, 없으면 None). ModuleSkipped 클래스에는 그 메서드 하나뿐이라 클래스 안의 값을 차례로 보며 찾는다 —
    이름을 변수로 `getattr` 하거나 `__dict__.get(변수)` 로 꺼내면 외부 접속 지점 점검 시험(tests/test_egress.py)이 등록 안 된 지점(dyn:getattr·dyn:dict-lookup)으로 보므로
    `getattr` 는 글자 그대로의 이름만 쓴다."""
    for value in type(test).__dict__.values():
        if getattr(value, "__unittest_skip__", False):
            return value
    return None


def is_module_skip(test):
    """모듈을 불러오다 `SkipTest` 가 나서 discover 가 그 모듈 대신 돌려준 시험(`unittest.loader.ModuleSkipped.<모듈>`)인가."""
    return type(test).__name__ == "ModuleSkipped" and bool(getattr(_skip_method(test), "__unittest_skip__", False))


def module_skip_of(test):
    reason = " ".join(str(getattr(_skip_method(test), "__unittest_skip_why__", "") or "").split())[:120]
    return ModuleSkip(getattr(test, "_testMethodName", ""), reason)


class RecordingLoader(unittest.TestLoader):
    """discover 가 모듈마다 부르는 loadTestsFromModule 의 결과를 모듈 이름별로 적어 둔다."""

    def __init__(self):
        super().__init__()
        self.loaded = {}

    def loadTestsFromModule(self, module, *args, **kwargs):
        suite = super().loadTestsFromModule(module, *args, **kwargs)
        self.loaded.setdefault(module.__name__, []).extend(iter_tests(suite))
        return suite


def collect_tests(root, start_dir="tests", pattern="test*.py"):
    """`python -m unittest discover -s tests` 와 같은 방식으로 모든 시험을 모아 Collected 로 돌려준다(시험은 하나도 돌리지 않는다).

    시작 폴더가 곧 최상위 폴더라 import 경로 맨 앞에 들어가고 모듈은 파일 이름(test_x)으로 불린다. 끝나면 import 경로와 이 폴더에서 불러온 모듈을 되돌려
    부모 프로세스가 가벼운 채로(시험 모듈을 들고 있지 않게) 남는다.
    discover 가 돌려준 시험 중 모듈별 기록(RecordingLoader)에 없는 것은 둘로 가른다 — 모듈 불러오기 중 스스로 건너뛴 모듈(skipped)과 그 밖의 알 수 없는 것(unknown).
    """
    tests_dir = Path(root, start_dir).resolve()
    importlib.invalidate_caches()                          # 같은 폴더를 고쳐 가며 다시 모을 때 낡은 목록을 보지 않게
    before_path = list(sys.path)
    old_cwd = os.getcwd()
    loader = RecordingLoader()
    os.chdir(str(root))
    try:
        suite = loader.discover(str(tests_dir), pattern=pattern)
        recorded = {id(test) for items in loader.loaded.values() for test in items}
        failed, skipped, unknown = [], [], []
        for test in iter_tests(suite):
            if is_failed_import(test):
                failed.append((test.id(), str(getattr(test, "_exception", "") or "")))
            elif id(test) not in recorded:                 # 어느 모듈의 loadTestsFromModule 도 거치지 않은 시험: 불러올 때 스스로 건너뛴 모듈이거나, 알 수 없는 것
                if is_module_skip(test):
                    skipped.append(module_skip_of(test))
                else:
                    unknown.append(test.id())
        tests = {}
        for module, items in loader.loaded.items():
            tests[module] = [(str(test), test.id()) for test in items if not is_failed_import(test)]
    finally:
        os.chdir(old_cwd)
        sys.path[:] = before_path
        _forget_modules_under(tests_dir)
    return Collected(tests, failed, skipped, unknown)


def _forget_modules_under(folder):
    folder = str(folder)
    for name, module in list(sys.modules.items()):
        path = getattr(module, "__file__", None)
        if path and os.path.abspath(path).startswith(folder + os.sep):
            sys.modules.pop(name, None)


# ---------------------------------------------------------------------------
# 2. 무게·나누기
# ---------------------------------------------------------------------------
def load_weights(path):
    """모듈→초 JSON 을 읽는다. 돌려주는 값은 (표, None) 또는 (None, 이유). `_` 로 시작하는 키는 설명이라 건너뛴다."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"읽지 못했습니다({type(exc).__name__})"
    if not isinstance(data, dict):
        return None, "모듈 이름 → 초 의 객체가 아닙니다"
    table = {}
    for key, value in data.items():
        if key.startswith("_"):
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            return None, f"{key} 의 값이 0 보다 큰 숫자가 아닙니다"
        table[key] = float(value)
    if not table:
        return None, "모듈 항목이 하나도 없습니다"
    return table, None


def module_weights(counts, table):
    """{모듈: 무게}. 표가 없으면 시험 개수(0개짜리는 1), 표에 없는 모듈은 표 값의 중앙값. 두 번째 값은 표에 없어 중앙값을 받은 모듈 목록."""
    if not table:
        return {module: float(max(count, 1)) for module, count in counts.items()}, []
    fallback = statistics.median(sorted(table.values()))
    unknown = sorted(module for module in counts if module not in table)
    return {module: table.get(module, fallback) for module in counts}, unknown


def build_plan(weights, jobs, serial=()):
    """무거운 것부터 가장 가벼운 묶음에 넣는다(같은 입력이면 늘 같은 나누기). `serial` 모듈은 한 덩어리로 한 묶음에 넣는다.

    weights: {모듈: 무게}(시험이 있는 모듈만). 돌려주는 값은 (묶음 목록, 묶음별 무게 합) — 묶음은 모듈 이름 목록(이름순, discover 의 순서와 같다)이고 빈 묶음은 없다.
    """
    serial = set(serial)
    items = []
    group = sorted(module for module in weights if module in serial)
    if group:
        items.append((sum(weights[module] for module in group), group[0], group))
    for module in sorted(weights):
        if module not in serial:
            items.append((weights[module], module, [module]))
    count = max(1, min(jobs, len(items)))
    items.sort(key=lambda item: (-item[0], item[1]))
    bins = [[] for _ in range(count)]
    loads = [0.0] * count
    for weight, _, modules in items:
        target = min(range(count), key=lambda number: (loads[number], number))
        bins[target].extend(modules)
        loads[target] += weight
    keep = [number for number, modules in enumerate(bins) if modules]
    return [sorted(bins[number]) for number in keep], [loads[number] for number in keep]


def check_plan(plan, tests):
    """나누기가 시험이 있는 모든 모듈을 정확히 한 묶음씩 담았는지 본다 — 빈 묶음·겹침·빠진 모듈·모르는 모듈. 문제 글의 목록(없으면 빈 목록)."""
    problems = []
    seen = collections.Counter()
    for number, modules in enumerate(plan, start=1):
        if not modules:
            problems.append(f"묶음 {number} 이(가) 비어 있습니다")
        seen.update(modules)
    with_tests = sorted(module for module, items in tests.items() if items)
    for module in with_tests:
        if seen[module] == 0:
            problems.append(f"모듈 {module} 이(가) 어느 묶음에도 없습니다")
        elif seen[module] > 1:
            problems.append(f"모듈 {module} 이(가) {seen[module]}개 묶음에 들어 있습니다")
    for module in sorted(set(seen) - set(with_tests)):
        problems.append(f"모듈 {module} 은(는) 처음 모은 시험 목록에 없습니다")
    return problems


# ---------------------------------------------------------------------------
# 3. 읽기 — 자식 출력의 시험 줄과 요약
# ---------------------------------------------------------------------------
Summary = collections.namedtuple("Summary", "ran seconds status counts")
Parsed = collections.namedtuple("Parsed", "executed summary failures last")
# last: 마지막으로 읽은 시험 줄의 이름(없으면 None) — 자식이 요약 없이 끝났을 때 어느 시험 근처에서 끊겼는지 알려 준다

_RAN = re.compile(r"^Ran (\d+) tests? in (\d+(?:\.\d+)?)s\s*$")
_RESULT = re.compile(r"^(OK|FAILED|NO TESTS RAN)(?: \((.*)\))?\s*$")
_FAILURE_HEADER = re.compile(r"^(?:FAIL|ERROR): ")
_SETUP_SKIPPED = re.compile(r"^(?:(?:setUpClass|setUpModule) \(.+?\) \.\.\. )?skipped ['\"]")      # 클래스·모듈 준비에서 건너뛴 줄 — 3.12: `setUpClass (모듈.클래스) ... skipped '이유'`, 3.10: 이름 없이 `skipped '이유'` 한 줄만
COUNT_ORDER = ("failures", "errors", "skipped", "expected failures", "unexpected successes")


def label_of(text, labels):
    """출력 한 줄이 어떤 시험의 시작 줄이면 그 시험 줄 이름을, 아니면 None. 한 줄 모양(`이름 (…) ... 결과`)과 설명이 있는 시험의 첫 줄(`이름 (…)` 만) 둘 다 읽는다."""
    head = text.split(" ... ", 1)[0]
    return head if head in labels else None


def parse_summary(texts):
    """맨 끝의 `Ran N tests in Xs` 와 그 뒤 `OK (skipped=2)`/`FAILED (failures=1, errors=2)` 줄. 없으면 None."""
    last = None
    for number, text in enumerate(texts):
        if _RAN.match(text):
            last = number
    if last is None:
        return None
    ran = _RAN.match(texts[last])
    for text in texts[last + 1:last + 6]:
        found = _RESULT.match(text)
        if found:
            counts = {}
            for part in (found.group(2) or "").split(","):
                if "=" in part:
                    key, _, value = part.strip().rpartition("=")
                    if value.isdigit():
                        counts[key] = int(value)
            return Summary(int(ran.group(1)), float(ran.group(2)), found.group(1), counts)
    return None


def texts_of(lines):
    """자식 출력(줄 목록: 글 또는 (초, 글))의 글만."""
    return [line[1] if isinstance(line, tuple) else line for line in lines]


def parse_child(lines, labels):
    """자식 출력(줄 목록: 글 또는 (초, 글))에서 실제로 시작된 시험 이름의 모음·요약·실패 머리글·마지막 시험 줄을 읽는다."""
    texts = texts_of(lines)
    executed = collections.Counter()
    failures = []
    last = None
    for text in texts:
        label = label_of(text, labels)
        if label is not None:
            executed[label] += 1
            last = label
        elif _FAILURE_HEADER.match(text):
            failures.append(text)
    return Parsed(executed, parse_summary(texts), failures, last)


def missing_hint(missing, texts):
    """돌아야 할 시험이 출력에 없을 때, 옛 직렬 흐름과 읽는 방식이 달라 생기는 알려진 경우를 짚는 글(없으면 빈 글자). 실패는 그대로 실패다 — 원인을 찾기 쉽게 글만 더한다."""
    notes = []
    setups = list(dict.fromkeys(text.strip()[:100] for text in texts if _SETUP_SKIPPED.match(text)))
    if setups:
        notes.append("자식 출력에 클래스·모듈 준비에서 건너뛴 줄이 있습니다: " + " / ".join(setups[:3]) + " — 그 시험들은 시험 줄이 찍히지 않아 이 실행기는 빠짐으로 읽습니다(옛 직렬 흐름은 건너뜀으로 셉니다. 알려진 차이)")
    glued = [label for label in sorted(missing)[:5] if any(label in text and not text.startswith(label) for text in texts)]
    if glued:
        notes.append("출력에 시험 줄 앞에 다른 글이 붙은 줄이 있습니다: " + ", ".join(glued[:3]) + " — 줄바꿈 없는 출력이 시험 줄 앞에 붙으면 시험 줄로 읽지 못합니다(알려진 차이)")
    return "".join(f" [{note}]" for note in notes)


# ---------------------------------------------------------------------------
# 4. 돌리기
# ---------------------------------------------------------------------------
ChildResult = collections.namedtuple("ChildResult", "index modules returncode lines seconds")
# lines: [(자식이 시작한 뒤 몇 초, 글), ...]  — 표준 출력과 표준 오류를 한 줄기로 합친 것


def interpreter_flags():
    """자식 파이썬에 줄 옵션 — 부모와 같은 UTF-8 모드·바이트코드 설정에 더해, 줄이 만들어지는 대로 보내게 한다(시험이 찍는 글과 시험 줄이 섞여도 순서가 같다)."""
    flags = ["-u"]
    if sys.flags.utf8_mode:
        flags += ["-X", "utf8"]
    if sys.dont_write_bytecode:
        flags.append("-B")
    return flags


def child_env(tests_dir):
    """자식이 시험 모듈을 이름(test_x)으로 불러오도록 PYTHONPATH 맨 앞에 시험 폴더를 둔다.
    `discover -s tests` 처럼 시험 폴더가 import 경로 맨 앞에 오는 것은 **아니다**: `python -m unittest` 는 현재 폴더(저장소 루트)를 경로 맨 앞에 두고 PYTHONPATH 는 그 다음이라
    자식의 순서는 저장소 루트, 시험 폴더, 표준 라이브러리다(옛 흐름은 시험 폴더, 저장소 루트). 시험 폴더의 파일·폴더 이름이 저장소 루트의 이름·표준 라이브러리 이름과 겹치지 않으면
    순서가 달라도 같은 모듈을 불러오고, 그것은 시험(ImportOrderTest)이 지킨다. 시험이 띄우는 손자 프로세스도 이 값을 물려받는다."""
    env = dict(os.environ)
    earlier = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(tests_dir) + (os.pathsep + earlier if earlier else "")
    return env


class Child:
    GRACE = 5.0           # 자식이 끝난 뒤에도 출력 줄기가 안 닫히면(시험이 남긴 손자 프로세스가 붙들고 있을 때) 이만큼만 더 기다린다
    JOIN_SECONDS = 5.0    # run_plan 이 마칠 때 출력을 읽는 스레드를 기다리는 최대 시간(줄기를 붙든 손자가 남아 있으면 이만큼 기다리고 넘어간다)

    def __init__(self, index, modules, root, tests_dir, labels):
        if not modules:
            raise ValueError(f"묶음 {index} 에 모듈이 없습니다 — 모듈 없이 unittest 를 띄우면 현재 폴더를 뒤져 다른 시험을 돌린다")
        self.index, self.modules, self.labels = index, list(modules), labels
        self.lines, self.count, self.last = [], 0, ""
        self.exited_at = self.ended = None
        self.started = time.monotonic()
        command = [sys.executable, *interpreter_flags(), "-m", "unittest", "-v", *self.modules]       # 이 한 줄이 자식이 하는 일의 전부다: `python -m unittest -v 모듈…`
        self.proc = subprocess.Popen(command, cwd=str(root), env=child_env(tests_dir), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _pump(self):
        # count·last 는 지금까지 읽은 시험 줄의 수와 마지막 줄이다. 한 줄 모양의 시험은 끝나야(줄바꿈이 와야) 읽히므로 도는 시험이 아니라 마지막으로 끝난 시험이다.
        for raw in iter(self.proc.stdout.readline, b""):
            text = raw.decode("utf-8", "replace").rstrip("\r\n")
            self.lines.append((time.monotonic() - self.started, text))
            label = label_of(text, self.labels)
            if label is not None:
                self.count, self.last = self.count + 1, label
        self.ended = time.monotonic()
        self.proc.stdout.close()

    def finished(self):
        if self.proc.poll() is None:
            return False
        if self.exited_at is None:
            self.exited_at = time.monotonic()
        return not self.thread.is_alive() or time.monotonic() - self.exited_at > self.GRACE

    @property
    def seconds(self):
        end = self.ended if self.ended is not None else (self.exited_at if self.exited_at is not None else time.monotonic())
        return end - self.started

    def result(self):
        return ChildResult(self.index, self.modules, self.proc.returncode, list(self.lines), self.seconds)

    def kill(self):
        if self.proc.poll() is None:
            self.proc.kill()


def run_plan(plan, root, tests_dir, labels, heartbeat=HEARTBEAT_SECONDS, out=None, on_ready=None):
    """묶음마다 자식 프로세스를 띄워 모두 끝날 때까지 기다린다. ChildResult 목록(묶음 순서)을 돌려준다.

    on_ready(번호, 결과) 는 묶음이 끝나는 대로 번호 순서로 부른다(앞 묶음이 아직 도는 동안 끝난 묶음은 기다렸다가 앞 묶음 다음에) — 한 묶음이 멈춰도 그 앞 묶음들의 출력은 이미 로그에 있다.
    """
    out = out or emit
    children = []
    try:
        for number, modules in enumerate(plan, start=1):
            children.append(Child(number, modules, root, tests_dir, labels))
        began = time.monotonic()
        running = list(children)
        next_beat = began + heartbeat
        ready = 0
        while running:
            time.sleep(0.1)
            for child in list(running):
                if child.finished():
                    running.remove(child)
                    out(f"[진행 {time.monotonic() - began:.0f}초] 묶음 {child.index}/{len(plan)} 끝 — 종료 코드 {child.proc.returncode}, 시험 {child.count}개 시작, {child.seconds:.1f}초")
            while on_ready is not None and ready < len(children) and children[ready] not in running:
                on_ready(ready, children[ready].result())
                ready += 1
            if running and heartbeat > 0 and time.monotonic() >= next_beat:
                next_beat += heartbeat
                parts = [f"묶음 {child.index}: " + (f"시험 줄 {child.count}개 읽음, 마지막 읽은 줄 {child.last[:60]}" if child.count else "아직 읽은 시험 줄 없음") for child in running]   # 도는 시험의 이름이 아니라 마지막으로 읽은(끝난) 시험 줄이다
                out(f"[진행 {time.monotonic() - began:.0f}초] " + " | ".join(parts))
        return [child.result() for child in children]
    finally:
        for child in children:
            child.kill()
        for child in children:
            child.proc.wait()
            child.thread.join(timeout=Child.JOIN_SECONDS)


# ---------------------------------------------------------------------------
# 5. 대조 — 시험을 빠뜨리지 않았다는 증거
# ---------------------------------------------------------------------------
BinReport = collections.namedtuple("BinReport", "index modules expected executed ran returncode status seconds failures")
Verdict = collections.namedtuple("Verdict", "problems failed_bins expected_total executed_total ran_total counts reports failures")


def _preview(counter, label_ids, limit=5):
    names = [label_ids.get(label, label) for label in sorted(counter)[:limit]]
    more = len(counter) - len(names)
    return ", ".join(names) + (f" 외 {more}개" if more > 0 else "")


def verify_run(tests, plan, results):
    """처음 모은 시험(tests)과 실제로 돈 시험(자식 출력)을 대조한다. 묶음별로 보고 전체로도 본다(묶음 나누기가 틀려도 전체 대조가 잡는다).

    돌려주는 Verdict.problems 가 비어 있고 failed_bins 도 비어 있어야 통과다. problems 는 빠짐·중복·개수 어긋남·요약 없음·나누기 오류이고,
    failed_bins 는 시험이 실패한(종료 코드가 0 이 아닌) 묶음 번호다.
    """
    label_ids = {}
    for items in tests.values():
        for label, test_id in items:
            label_ids.setdefault(label, test_id)
    expected_by_module = {module: collections.Counter(label for label, _ in items) for module, items in tests.items()}
    problems = check_plan(plan, tests)
    if len(results) != len(plan):
        problems.append(f"묶음은 {len(plan)}개인데 자식 결과가 {len(results)}개입니다")
    all_expected = collections.Counter()
    for counter in expected_by_module.values():
        all_expected.update(counter)
    all_executed = collections.Counter()
    reports, failed_bins, failures = [], [], []
    counts = collections.Counter()
    ran_total = 0
    for number, (modules, result) in enumerate(zip(plan, results), start=1):
        want = collections.Counter()
        for module in modules:
            want.update(expected_by_module.get(module, {}))
        parsed = parse_child(result.lines, label_ids)
        all_executed.update(parsed.executed)
        missing, extra = want - parsed.executed, parsed.executed - want
        if missing:
            problems.append(f"묶음 {number}: 돌아야 할 시험 {sum(missing.values())}개가 출력에 없습니다 — {_preview(missing, label_ids)}{missing_hint(missing, texts_of(result.lines))}")
        if extra:
            problems.append(f"묶음 {number}: 기대보다 더 돈 시험 {sum(extra.values())}개(중복 또는 다른 묶음의 시험) — {_preview(extra, label_ids)}")
        summary = parsed.summary
        if summary is None:
            where = f"마지막으로 읽은 시험 줄: {label_ids.get(parsed.last, parsed.last)}" if parsed.last else "시험 줄을 하나도 읽지 못했습니다"
            problems.append(f"묶음 {number}: 자식 출력에 `Ran N tests` 요약이 없습니다(자식이 중간에 끝났을 수 있습니다, 종료 코드 {result.returncode}) — {where}")
        else:
            ran_total += summary.ran
            counts.update(summary.counts)
            if summary.ran != sum(want.values()):
                problems.append(f"묶음 {number}: 자식이 돌았다고 한 시험 수 {summary.ran} 이 기대 {sum(want.values())} 와 다릅니다")
            if result.returncode == 0 and summary.status != "OK":
                problems.append(f"묶음 {number}: 종료 코드는 0 인데 요약은 {summary.status} 입니다")
            if result.returncode != 0 and summary.status == "OK":
                problems.append(f"묶음 {number}: 종료 코드는 {result.returncode} 인데 요약은 OK 입니다")
        if result.returncode != 0:
            failed_bins.append(number)
        failures.extend(parsed.failures)
        reports.append(BinReport(number, list(modules), sum(want.values()), sum(parsed.executed.values()), summary.ran if summary else None,
                                 result.returncode, summary.status if summary else None, result.seconds, parsed.failures))
    expected_total, executed_total = sum(all_expected.values()), sum(all_executed.values())
    missing_all, extra_all = all_expected - all_executed, all_executed - all_expected
    if missing_all:
        problems.append(f"전체 대조: 처음 모은 시험 중 {sum(missing_all.values())}개가 실제로 돌지 않았습니다 — {_preview(missing_all, label_ids)}")
    if extra_all:
        problems.append(f"전체 대조: 처음 모은 것보다 {sum(extra_all.values())}개가 더(중복) 돌았습니다 — {_preview(extra_all, label_ids)}")
    if ran_total != expected_total:
        problems.append(f"전체 대조: 자식 요약의 시험 수 합 {ran_total} 이 처음 모은 {expected_total} 과 다릅니다")
    return Verdict(problems, failed_bins, expected_total, executed_total, ran_total, counts, reports, failures)


def module_seconds(tests, plan, results):
    """모듈별 걸린 시간(초)을 출력 줄의 도착 시각으로 어림한다(새 가중치 표의 재료).

    시험 줄과 그 뒤 다음 시험 줄 전까지의 줄을 한 토막으로 보고 토막의 마지막 줄이 도착한 때를 그 시험이 끝난 때로 친다(결과 줄은 시험이 끝날 때 찍힌다).
    시험의 시간 = 앞 시험이 끝난 때부터 이 시험이 끝난 때까지다. 첫 시험은 모듈을 불러오는 시간이 섞이므로 0 으로 센다(어림이다).
    """
    owners = collections.defaultdict(list)
    for module, items in tests.items():
        for label, _ in items:
            owners[label].append(module)
    seconds = collections.Counter()
    for modules, result in zip(plan, results):
        segments = []
        for when, text in result.lines:
            label = label_of(text, owners)
            if label is not None:
                segments.append([label, when])
            elif segments:
                segments[-1][1] = when
        previous_end = segments[0][1] if segments else 0.0
        for label, end in segments:
            owner = next((module for module in owners[label] if module in modules), owners[label][0])
            seconds[owner] += max(end - previous_end, 0.0)
            previous_end = end
    return {module: max(round(value, 1), 0.1) for module, value in sorted(seconds.items())}          # 0 이하는 --weights 가 받지 않으므로 바닥을 0.1 로


# ---------------------------------------------------------------------------
# 6. 출력
# ---------------------------------------------------------------------------
def emit(text=""):
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def repro_command(modules):
    names = " ".join(modules[:6]) + (f" … (모듈 {len(modules)}개)" if len(modules) > 6 else "")
    return f"PYTHONPATH=tests python -m unittest -v {names}"


def format_plan(plan, loads, tests, how):
    counts = {module: len(items) for module, items in tests.items()}
    lines = [f"나누기: 묶음 {len(plan)}개 · 모듈 {sum(len(modules) for modules in plan)}개 · 시험 {sum(counts.values())}개 · 무게 기준: {how}"]
    for number, (modules, load) in enumerate(zip(plan, loads), start=1):
        lines.append(f"  묶음 {number}/{len(plan)}: 모듈 {len(modules)}개 · 시험 {sum(counts[m] for m in modules)}개 · 예상 무게 {load:.1f}")
        lines.extend(textwrap.wrap(" ".join(modules), width=118, initial_indent="    ", subsequent_indent="    "))
    return lines


def format_block(number, total, modules, expected, planned_load, result):
    head = [f"===== 묶음 {number}/{total} =====",
            f"모듈 {len(modules)}개 · 시험 {expected}개 · 예상 무게 {planned_load:.1f} · 실제 {result.seconds:.1f}초 · 종료 코드 {result.returncode}",
            f"같은 일을 직접 하려면: {repro_command(modules)}"]
    return head + [text for _, text in result.lines] + [f"----- 묶음 {number}/{total} 끝 -----"]


def format_summary(verdict, seconds, loads=(), partial=False, module_skips=()):
    """module_skips: 불러올 때 스스로 건너뛴 모듈(ModuleSkip 목록) — 옛 직렬 흐름처럼 시험 수와 건너뜀 수에 하나씩 더한다(자식이 돌린 시험이 아니라 부모가 모을 때 본 것이다)."""
    skips = list(module_skips)
    lines = ["", "===== 병렬 실행 요약 ====="]
    for report in verdict.reports:
        state = "통과" if report.returncode == 0 else f"실패(종료 코드 {report.returncode})"
        planned = f" · 예상 무게 {loads[report.index - 1]:.1f}" if len(loads) >= report.index else ""
        lines.append(f"묶음 {report.index}/{len(verdict.reports)}: 시험 {report.expected}개{planned} · 실제 {report.seconds:.1f}초 · {state}")
    expected, executed = verdict.expected_total, verdict.executed_total
    if executed == expected and not any("전체 대조" in text for text in verdict.problems):
        lines.append(f"시험 id 대조: 처음 모은 {expected}개 = 실제로 돈 {executed}개(빠짐 0 · 중복 0), 자식 요약의 시험 수 합 {verdict.ran_total}")
    else:
        lines.append(f"시험 id 대조 실패: 처음 모은 {expected}개 · 실제로 돈 {executed}개 · 자식 요약의 시험 수 합 {verdict.ran_total}")
    if skips:
        lines.append(f"불러올 때 스스로 건너뛴 모듈 {len(skips)}개: 옛 직렬 흐름처럼 시험 수와 건너뜀 수에 하나씩 더했습니다 — " + ", ".join(item.module for item in skips))
    if verdict.problems:
        lines.append("대조 문제:")
        lines.extend(f"  - {text}" for text in verdict.problems)
    if verdict.failures:
        lines.append("실패·오류 시험:")
        lines.extend(f"  {text}" for text in verdict.failures[:100])
        if len(verdict.failures) > 100:
            lines.append(f"  … 외 {len(verdict.failures) - 100}개(묶음 출력을 보세요)")
    counts = collections.Counter(verdict.counts)
    counts["skipped"] += len(skips)
    infos = [f"{key}={counts[key]}" for key in COUNT_ORDER if counts.get(key)]
    if verdict.problems:
        infos.insert(0, f"대조 문제={len(verdict.problems)}")
    if partial:
        lines.append("부분 실행(--only): 고른 모듈의 시험만 돌았습니다 — 전체가 통과했다는 뜻이 아닙니다")
        infos.insert(0, "부분 실행")
    ok = not verdict.problems and not verdict.failed_bins
    lines += ["", BAR, f"Ran {verdict.ran_total + len(skips)} tests in {seconds:.3f}s", "", ("OK" if ok else "FAILED") + (f" ({', '.join(infos)})" if infos else "")]
    return lines


# ---------------------------------------------------------------------------
# 7. 진입점
# ---------------------------------------------------------------------------
def default_jobs():
    return max(1, min(os.cpu_count() or 1, DEFAULT_JOBS_CAP))


def build_parser():
    parser = argparse.ArgumentParser(prog="run_unit_parallel.py", allow_abbrev=False, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=__doc__.split("\n\n")[0] + "\n\n시험 모듈을 여러 프로세스로 나눠 돌리고, 돈 시험이 처음 모은 시험과 정확히 같은지 대조한다.")
    parser.add_argument("-j", "--jobs", type=int, default=None, help=f"묶음(프로세스) 수. 기본 min(CPU 개수, {DEFAULT_JOBS_CAP}), 최대 {MAX_JOBS}")
    parser.add_argument("--plan-only", action="store_true", help="나누기만 보이고 끝낸다(시험은 돌리지 않는다)")
    parser.add_argument("--weights", metavar="FILE", help="모듈→초 JSON. 없으면 시험 개수 비율. 표에 없는 새 모듈은 표 값의 중앙값")
    parser.add_argument("--serial", nargs="+", action="append", default=[], metavar="MODULE", help="늘 같은 프로세스에서 돌 모듈(서로 부딪히는 시험). 여러 번 써도 한 묶음")
    parser.add_argument("--only", nargs="+", action="append", default=[], metavar="MODULE", help="이 모듈만 돈다(부분 실행 — 실험용. 대조도 이 모듈에 대해서만 한다. CI 는 쓰지 않는다)")
    parser.add_argument("--root", default=None, help="저장소 루트(기본: 이 파일의 두 단계 위)")
    parser.add_argument("--start-dir", default="tests", help="시험 폴더(루트 기준, 기본 tests)")
    parser.add_argument("--pattern", default="test*.py", help="시험 파일 이름 패턴(기본 test*.py — `unittest discover` 의 기본값이라 CI 의 옛 명령 `discover -s tests` 와 같은 범위를 모은다)")
    parser.add_argument("--heartbeat", type=float, default=HEARTBEAT_SECONDS, help=f"도는 동안 진행 줄을 찍는 간격(초, 0 이면 끝난 묶음만 알림). 기본 {HEARTBEAT_SECONDS:.0f}")
    parser.add_argument("--timings-out", metavar="FILE", help="이번 실행에서 어림한 모듈별 초를 JSON 으로 쓴다(--weights 에 그대로 쓸 수 있다)")
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):                  # 윈도 한글 콘솔(cp949)이 못 찍는 글자(도움말의 '—' 포함) 때문에 멈추지 않게 — 인자를 읽기 전에
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    jobs = args.jobs if args.jobs is not None else default_jobs()
    if jobs < 1:
        parser.error("-j 는 1 이상이어야 합니다")
    if jobs > MAX_JOBS:
        emit(f"알림: -j {jobs} 는 상한 {MAX_JOBS} 를 넘어 {MAX_JOBS} 로 줄입니다")
        jobs = MAX_JOBS
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    if args.weights:                                       # 파일 인자는 부른 곳(현재 폴더) 기준 — 아래에서 루트로 옮겨 가기 전에 절대 경로로 바꾼다
        args.weights = str(Path(args.weights).resolve())
    if args.timings_out:
        args.timings_out = str(Path(args.timings_out).resolve())
    old_cwd = os.getcwd()
    os.chdir(str(root))                                    # CI 처럼 저장소 루트에서(시험 모듈이 불릴 때 상대 경로를 읽는 것까지 같다)
    try:
        return _run(args, jobs, root)
    except KeyboardInterrupt:                              # run_plan 의 finally 가 자식을 이미 모두 끝냈다
        emit("중단됨: 시험이 다 끝나지 않았으므로 통과로 세지 않습니다(종료 코드 130)")
        return 130
    finally:
        os.chdir(old_cwd)


def _run(args, jobs, root):
    tests_dir = Path(root, args.start_dir).resolve()
    try:
        collected = collect_tests(root, args.start_dir, args.pattern)
    except Exception as exc:                               # noqa: BLE001 — 폴더가 없는 등 모으지 못한 것도 숨기지 않고 실패로 끝낸다
        emit(f"실패: 시험을 모으지 못했습니다({type(exc).__name__}: {exc})")
        return 1
    tests = collected.tests
    if collected.failed:
        emit(f"실패: 불러오기에 실패한 시험 모듈이 {len(collected.failed)}개 있습니다 — 아무 시험도 돌리지 않고 끝냅니다(조용히 빼지 않습니다)")
        for test_id, message in collected.failed:
            emit(f"===== 불러오기 실패: {test_id} =====")
            emit(message.rstrip())
        emit(f"{BAR}\nFAILED (불러오기 실패={len(collected.failed)})")
        return 1
    if collected.unknown:                                   # 알 수 없는 시험은 조용히 빼지 않는다(예: 파이썬이 _FailedTest 의 이름을 바꿔 불러오기 실패를 못 알아보게 된 경우)
        emit(f"실패: 모은 시험 중 알 수 없는 종류가 {len(collected.unknown)}개 있습니다 — 모듈 불러오기 기록에도 불러오기 실패·모듈 건너뜀에도 없어 아무것도 돌리지 않고 끝냅니다: {', '.join(collected.unknown[:5])}")
        emit(f"{BAR}\nFAILED (알 수 없는 시험={len(collected.unknown)})")
        return 1
    with_tests = {module: items for module, items in tests.items() if items}
    total = sum(len(items) for items in with_tests.values())
    if total == 0:
        emit("실패: 모은 시험이 하나도 없습니다(시험 폴더·파일 이름 패턴을 확인하세요) — 조용히 통과하지 않습니다")
        return 1
    ids_of_label = collections.defaultdict(set)
    for items in with_tests.values():
        for label, test_id in items:
            ids_of_label[label].add(test_id)
    clash = sorted(label for label, ids in ids_of_label.items() if len(ids) > 1)
    if clash:                                              # 대조는 시험 줄 이름으로 하므로 이름과 id 가 일대일이어야 한다(보통의 TestCase 는 늘 그렇다 — __str__ 을 바꾼 시험이 이름을 겹치게 하면 여기서 멈춘다)
        emit(f"실패: 서로 다른 시험 id 가 같은 시험 줄 이름을 찍습니다 — 줄 이름으로 돈 시험을 가릴 수 없어 아무것도 돌리지 않습니다: {', '.join(clash[:5])}")
        return 1
    if args.only:                                          # 부분 실행 — 실험·일부만 돌릴 때. 대조도 고른 모듈에 대해 한다(CI 는 이 인자를 쓰지 않는다)
        wanted = sorted({name[:-3] if name.endswith(".py") else name for group in args.only for name in group})
        missing = sorted(set(wanted) - set(with_tests))
        if missing:
            emit(f"사용법 오류: --only 에 시험이 없는 모듈 이름이 있습니다: {', '.join(missing)}")
            return 2
        with_tests = {module: with_tests[module] for module in wanted}
        emit(f"알림: --only 로 고른 모듈 {len(wanted)}개(시험 {sum(len(items) for items in with_tests.values())}개)만 돕니다 — 전체가 아닌 부분 실행입니다")
    serial = [name[:-3] if name.endswith(".py") else name for group in args.serial for name in group]
    unknown_serial = sorted(set(serial) - set(with_tests))
    if unknown_serial:
        emit(f"사용법 오류: --serial 에 시험이 없는 모듈 이름이 있습니다: {', '.join(unknown_serial)}")
        return 2
    table, reason = (None, None)
    if args.weights:
        table, reason = load_weights(args.weights)
        if table is None:
            emit(f"경고: 가중치 파일 {os.path.basename(args.weights)} 을(를) 쓰지 못해 시험 개수 비율로 나눕니다 — {reason}(시험은 그대로 모두 돕니다)")
    weights, unknown = module_weights({module: len(items) for module, items in with_tests.items()}, table)
    plan, loads = build_plan(weights, jobs, serial)
    how = "시험 개수" if table is None else f"가중치 파일({os.path.basename(args.weights)}), 표에 없는 모듈 {len(unknown)}개는 중앙값"
    for line in format_plan(plan, loads, with_tests, how):
        emit(line)
    empty = sorted(module for module, items in tests.items() if not items)
    if empty:
        emit(f"알림: 시험이 없는 모듈 {len(empty)}개는 돌릴 것이 없어 나누기에서 뺐습니다: {', '.join(empty)}")
    skipped_modules = [] if args.only else list(collected.skipped)          # 부분 실행(--only)은 고른 모듈의 시험만 세므로 모듈 건너뜀은 알리기만 한다
    if collected.skipped:
        names = ", ".join(f"{item.module}(이유: {item.reason})" for item in collected.skipped)
        how = "부분 실행(--only)이라 세지 않습니다" if args.only else "옛 직렬 흐름처럼 시험 수와 건너뜀 수에 하나씩 더합니다"
        emit(f"알림: 불러올 때 스스로 건너뛴 모듈 {len(collected.skipped)}개 — {how}: {names}")
    problems = check_plan(plan, with_tests)
    if problems:
        emit("실패: 나누기 검사에 걸렸습니다 — 시험을 돌리지 않습니다")
        for text in problems:
            emit(f"  - {text}")
        return 1
    emit(f"나누기 검사 통과: 시험이 있는 모듈 {len(with_tests)}개가 정확히 한 묶음에 한 번씩 들어 있습니다")
    if args.plan_only:
        emit("--plan-only: 나누기만 보였고 시험은 돌리지 않았습니다")
        return 0
    labels = {label: test_id for items in with_tests.values() for label, test_id in items}

    def show(index, result):                               # 자식 출력은 묶음이 끝나는 대로(번호 순서로) 찍는다 — 대조보다 먼저라서 대조 코드가 예기치 않게 죽어도 로그는 남는다
        modules = plan[index]
        for line in format_block(index + 1, len(plan), modules, sum(len(with_tests[module]) for module in modules), loads[index], result):
            emit(line)

    began = time.monotonic()
    results = run_plan(plan, root, tests_dir, labels, heartbeat=args.heartbeat, on_ready=show)
    seconds = time.monotonic() - began
    verdict = verify_run(with_tests, plan, results)
    for line in format_summary(verdict, seconds, loads, partial=bool(args.only), module_skips=skipped_modules):
        emit(line)
    if args.timings_out:
        Path(args.timings_out).write_text(json.dumps(module_seconds(with_tests, plan, results), ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if not verdict.problems and not verdict.failed_bins else 1


if __name__ == "__main__":
    sys.exit(main())
