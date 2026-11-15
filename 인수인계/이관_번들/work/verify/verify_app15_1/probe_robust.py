"""AP14 견고성 시험 — 쓰기 실패·한도·속도 제한·동시성·경계 연결.
사용: python -B -X utf8 probe_robust.py <tree 폴더> <임시 작업 폴더>
"""
import builtins
import contextlib
import datetime as dt
import errno
import io
import os
import stat
import subprocess
import sys
import threading
import time
import types

TREE, WORK = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(TREE, "src"))
sys.path.insert(0, os.path.join(TREE, "tests"))
sys.path.insert(0, TREE)
from chanceblog_desktop.security import boundary, errorlog  # noqa: E402

FIXED = dt.datetime(2026, 11, 15, 7, 41, 5, tzinfo=dt.timezone.utc)
counter = [0]
rows = []


def say(key, what, result, verdict):
    rows.append((key, what, result, verdict))
    print("%s | %s | %s | %s" % (key, what, result, verdict), flush=True)


def fresh(**options):
    counter[0] += 1
    root = os.path.join(WORK, "r%03d" % counter[0])
    options.setdefault("clock", lambda: FIXED)
    options.setdefault("rate", (10 ** 9, 60.0))
    return errorlog.ErrorLog(lambda: root, **options), root


def boom():
    try:
        raise ValueError("m")
    except ValueError as error:
        return error


def rec(log, source="main"):
    error = boom()
    return log.record(source, type(error), error, error.__traceback__)


def logs_of(root):
    folder = os.path.join(root, "logs")
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


def sizes(root):
    folder = os.path.join(root, "logs")
    return {name: os.path.getsize(os.path.join(folder, name)) for name in logs_of(root)} if os.path.isdir(folder) else {}


MAX = errorlog.MAX_BYTES

# ---- R1 읽기 전용 파일 ------------------------------------------------------------------------------------------------------------------
log, root = fresh()
assert rec(log) is True
path = os.path.join(root, "logs", "errors.log")
os.chmod(path, stat.S_IREAD)
try:
    ret = rec(log)
    say("R01", "errors.log 가 읽기 전용(파일 속성)", "record 반환 %r, 예외 없음" % ret, "OK" if ret is False else "CHECK")
finally:
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
say("R01b", "읽기 전용을 풀면 다시 씀", "record 반환 %r" % rec(log), "OK")

# ---- R2 폴더 자리에 같은 이름 파일 -----------------------------------------------------------------------------------------------------
log, root = fresh()
os.makedirs(root)
with open(os.path.join(root, "logs"), "w") as handle:
    handle.write("나는 폴더가 아니라 파일")
ret = rec(log)
say("R02", "logs 가 폴더가 아니라 같은 이름의 파일", "record 반환 %r, 예외 없음, 파일 그대로 %r" % (ret, open(os.path.join(root, 'logs')).read()[:6]), "OK" if ret is False else "CHECK")

# ---- R3 errors.log 자리에 폴더 --------------------------------------------------------------------------------------------------------
log, root = fresh()
os.makedirs(os.path.join(root, "logs", "errors.log"))
ret = rec(log)
say("R03", "errors.log 자리에 같은 이름의 폴더", "record 반환 %r, 예외 없음" % ret, "OK" if ret is False else "CHECK")

# ---- R4 다른 프로세스가 파일을 잡아 이름 바꾸기 실패 ------------------------------------------------------------------------------------
HOLDER = "import sys,time\nh=open(sys.argv[1],'rb')\nprint('held',flush=True)\nsys.stdin.readline()\n"
log, root = fresh()
os.makedirs(os.path.join(root, "logs"))
path = os.path.join(root, "logs", "errors.log")
with open(path, "wb") as handle:
    handle.write(b"a" * (MAX - 10))
proc = subprocess.Popen([sys.executable, "-B", "-X", "utf8", "-c", HOLDER, path], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
try:
    proc.stdout.readline()
    ret = rec(log)
    st = sizes(root)
    verdict = "OK" if (ret is False and st.get("errors.log") == MAX - 10 and len(st) == 1) else "CHECK"
    say("R04", "다른 프로세스가 errors.log 를 연 채(한도 직전) 새 줄", "record 반환 %r, 파일 %s" % (ret, st), verdict)
finally:
    with contextlib.suppress(Exception):
        proc.stdin.write(b"\n")
        proc.stdin.flush()
    proc.wait(timeout=10)
ret2 = rec(log)
say("R04b", "잡고 있던 프로세스가 끝나면 돌려쓰고 다시 씀", "record 반환 %r, 파일 %s" % (ret2, sizes(root)), "OK" if ret2 is True else "CHECK")

# ---- R5 부분 돌려쓰기(.1 만 잡힘): 가장 오래된 것은 이미 지워진 뒤 ---------------------------------------------------------------------------
log, root = fresh()
folder = os.path.join(root, "logs")
os.makedirs(folder)
for name, fill in (("errors.log", b"c" * (MAX - 10)), ("errors.log.1", b"b" * 1000), ("errors.log.2", b"a" * 1000)):
    with open(os.path.join(folder, name), "wb") as handle:
        handle.write(fill)
proc = subprocess.Popen([sys.executable, "-B", "-X", "utf8", "-c", HOLDER, os.path.join(folder, "errors.log.1")], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
try:
    proc.stdout.readline()
    ret = rec(log)
    st = sizes(root)
finally:
    with contextlib.suppress(Exception):
        proc.stdin.write(b"\n")
        proc.stdin.flush()
    proc.wait(timeout=10)
say("R05", ".1 이 다른 프로세스에 잡힌 채 돌려쓰기 시도", "record 반환 %r, 파일 %s (가장 오래된 .2 가 먼저 지워졌는지 확인)" % (ret, st), "INFO(.2 유실 가능)" if "errors.log.2" not in st else "OK")

# ---- R6 디스크 가득(부분 쓰기) ---------------------------------------------------------------------------------------------------------
log, root = fresh()
assert rec(log) is True
real_open = builtins.open


class HalfWriter:
    def __init__(self, handle):
        self.handle = handle

    def write(self, data):
        self.handle.write(data[:12])
        self.handle.flush()
        raise OSError(errno.ENOSPC, "No space left on device")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.handle.close()
        return False


def half_open(file, mode="r", *args, **kwargs):
    handle = real_open(file, mode, *args, **kwargs)
    return HalfWriter(handle) if "a" in mode and "errors.log" in str(file) else handle


builtins.open = half_open
try:
    ret_half = rec(log)
finally:
    builtins.open = real_open
ret_after = rec(log)
text = real_open(os.path.join(root, "logs", "errors.log"), "rb").read().decode()
lines = text.split("\n")
say("R06", "디스크 가득: 12바이트만 쓰고 ENOSPC", "첫 시도 %r, 다음 시도 %r, 줄 %d개, 줄 길이 %s" % (ret_half, ret_after, len(lines) - 1, [len(x) for x in lines]), "INFO(잘린 줄 뒤에 다음 줄이 이어붙음)" if len(lines) - 1 == 2 and not lines[1].startswith("2026") else "OK")

# ---- R7 한도: 실제 상수 경계 ------------------------------------------------------------------------------------------------------------
log, root = fresh()
rec(log)
line_len = os.path.getsize(os.path.join(root, "logs", "errors.log"))
base = os.path.join(root, "logs", "errors.log")
with open(base, "wb") as handle:
    handle.write(b"x" * (MAX - line_len))                           # 새 줄이 들어가면 정확히 MAX
ret = rec(log)
st_fit = sizes(root)
with open(base, "wb") as handle:
    handle.write(b"x" * (MAX - line_len + 1))                       # 새 줄이 들어가면 MAX+1
ret2 = rec(log)
st_over = sizes(root)
say("R07", "경계: 새 줄이 정확히 256 KB 가 되는 경우 / 1 바이트 넘는 경우", "맞는 경우 %s, 넘는 경우 %s" % (st_fit, st_over),
    "OK" if st_fit.get("errors.log") == MAX and "errors.log.1" in st_over and max(st_over.values()) <= MAX else "CHECK")

# ---- R8 많은 줄: 파일 셋·각 256 KB 이하 -------------------------------------------------------------------------------------------------
log, root = fresh()
total = 0
for number in range(12000):
    total += 1 if rec(log) else 0
st = sizes(root)
say("R08", "실제 상수로 12,000 줄(속도 제한 풀고)", "기록 %d줄, 파일 %s, 합계 %d 바이트" % (total, st, sum(st.values())), "OK" if len(st) <= 3 and max(st.values()) <= MAX and sum(st.values()) <= 3 * MAX else "CHECK")

# ---- R9 속도 제한 ------------------------------------------------------------------------------------------------------------------------
log, root = fresh(rate=(errorlog.RATE_COUNT, errorlog.RATE_SECONDS))
flags = [rec(log) for _ in range(100)]
say("R09", "실제 속도 제한(30/60초)으로 100번 연속", "기록 %d줄" % sum(flags), "OK" if sum(flags) == 30 else "CHECK")
clock = [1000.0]
log, root = fresh(rate=(30, 60.0), monotonic=lambda: clock[0])
first = sum(1 for _ in range(30) if rec(log))
clock[0] = 1059.999
denied = rec(log)
clock[0] = 1060.0
burst = sum(1 for _ in range(30) if rec(log))
say("R09b", "창 경계: 59.999초에 거절, 60.0초에 30줄 다시", "처음 %d, 59.999초 %r, 60.0초 뒤 %d (경계를 낀 1초 안에 %d줄)" % (first, denied, burst, first + burst), "INFO(고정 창: 경계에서 최대 60줄)")
clock[0] = 5000.0
log, root = fresh(rate=(3, 60.0), monotonic=lambda: clock[0])
sum(1 for _ in range(3) if rec(log))
clock[0] = 100.0                                                    # 시간이 되돌아감(진짜 monotonic 은 안 그렇다)
back = rec(log)
clock[0] = 5059.0
back2 = rec(log)
clock[0] = 5060.0
back3 = rec(log)
say("R09c", "시계 되돌림(주입된 monotonic): 5000에서 100으로", "되돌린 직후 %r, 창 안 5059 %r, 5060 %r" % (back, back2, back3), "INFO(되돌린 만큼 오래 침묵, 그래도 한도 안)" if back is False else "CHECK")

# ---- R10 여러 스레드 + 돌려쓰기 동시 ---------------------------------------------------------------------------------------------------
log, root = fresh(max_bytes=4000)
orig_wait = errorlog.LOCK_WAIT
errorlog.LOCK_WAIT = 60.0
errs = []


def work():
    for _ in range(300):
        try:
            rec(log)
        except BaseException as exc:  # noqa: BLE001
            errs.append(type(exc).__name__)


threads = [threading.Thread(target=work) for _ in range(8)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()
errorlog.LOCK_WAIT = orig_wait
st = sizes(root)
say("R10", "스레드 8개가 한도 4000 바이트에서 동시에 돌려쓰기", "예외 %s, 파일 %s" % (errs or "없음", st), "OK" if not errs and len(st) <= 3 and max(st.values()) <= 4000 else "CHECK")

# ---- R11 켜기만으로는 아무것도 안 만든다 / 첫 오류에 처음 만든다 -------------------------------------------------------------------------
root = os.path.join(WORK, "arm_only")
asked = []
installed = boundary.install_gui(qt=False)
try:
    ok = boundary.arm_error_log(lambda: asked.append(1) or root)
    say("R11a", "install_gui + arm_error_log 만으로", "arm=%r, 해석 함수 호출 %d번, 폴더 존재 %r" % (ok, len(asked), os.path.exists(root)), "OK" if ok and not asked and not os.path.exists(root) else "CHECK")
    errorlog.active()._clock = lambda: FIXED
    err = boom()
    sink = io.StringIO()
    with contextlib.redirect_stderr(sink):
        sys.excepthook(type(err), err, err.__traceback__)
    say("R11b", "첫 오류(sys.excepthook)", "해석 %d번, 만들어진 것 %s, 데이터 폴더 안 %s" % (len(asked), logs_of(root), sorted(os.listdir(root))), "OK" if logs_of(root) == ["errors.log"] and sorted(os.listdir(root)) == ["logs"] else "CHECK")
finally:
    installed.uninstall()

# ---- R12 경계: 기존 동작(표준 오류에 가린 추적) 유지, KeyboardInterrupt/SystemExit ---------------------------------------------------------
GKEY = "AI" + "za" + "Sy" + "CANARY" + "x" * 27


def stderr_of(armed, kind=ValueError, message="x " + GKEY):
    sink = io.StringIO()
    with contextlib.redirect_stderr(sink):
        installed = boundary.install_gui(qt=False)
        try:
            if armed:
                boundary.arm_error_log(lambda: os.path.join(WORK, "hook_cmp"))
            try:
                raise kind(message)
            except BaseException as error:  # noqa: BLE001
                sys.excepthook(type(error), error, error.__traceback__)
        finally:
            installed.uninstall()
    return sink.getvalue()


def normalize(text):
    import re
    return re.sub(r"line \d+", "line N", text.replace("\\", "/"))


plain, armed = stderr_of(False), stderr_of(True)
say("R12a", "표준 오류 글: 켜기 전 vs 켠 뒤(ValueError+가짜 키)", "같음=%r, 키 노출=%r, 길이 %d/%d" % (normalize(plain) == normalize(armed), GKEY in armed, len(plain), len(armed)), "OK" if normalize(plain) == normalize(armed) and GKEY not in armed else "CHECK")
for kind in (KeyboardInterrupt, SystemExit):
    p, a = stderr_of(False, kind, ""), stderr_of(True, kind, "")
    say("R12-" + kind.__name__, "%s 를 sys.excepthook 에: 표준 오류 글 켜기 전 vs 켠 뒤" % kind.__name__, "같음=%r, 기록 파일 %s" % (normalize(p) == normalize(a), logs_of(os.path.join(WORK, "hook_cmp"))), "OK" if normalize(p) == normalize(a) else "CHECK")

# ---- R13 스레드 훅: SystemExit 조용히, 일반 오류는 기록 + 표준 오류 -----------------------------------------------------------------------
root = os.path.join(WORK, "thread_hook")
installed = boundary.install_gui(qt=False)
try:
    boundary.arm_error_log(lambda: root)
    errorlog.active()._clock = lambda: FIXED
    sink = io.StringIO()
    with contextlib.redirect_stderr(sink):
        def thread_main():
            raise RuntimeError("스레드에서 난 오류 " + GKEY)
        t = threading.Thread(target=thread_main, name="worker")
        t.start()
        t.join()
        def thread_exit():
            sys.exit(3)
        t2 = threading.Thread(target=thread_exit)
        t2.start()
        t2.join()
    text = open(os.path.join(root, "logs", "errors.log")).read()
    say("R13", "실제 스레드에서 RuntimeError / SystemExit", "기록 줄 %d (%s), 표준 오류 길이 %d, 키 노출 %r" % (len(text.splitlines()), text.split()[1:3], len(sink.getvalue()), GKEY in sink.getvalue() or GKEY in text), "OK" if len(text.splitlines()) == 1 and "thread RuntimeError" in text and "RuntimeError" in sink.getvalue() else "CHECK")
finally:
    installed.uninstall()

# ---- R14 두 번 켜기·켠 뒤 되돌리기·켜기 전 arm ----------------------------------------------------------------------------------------
installed = boundary.install_gui(qt=False)
a1 = boundary.arm_error_log(lambda: os.path.join(WORK, "a1"))
first_log = errorlog.active()
a2 = boundary.arm_error_log(lambda: os.path.join(WORK, "a2"))
second_log = errorlog.active()
installed.uninstall()
after = errorlog.active()
say("R14", "arm_error_log 두 번 → uninstall", "arm %r/%r, 두 번째가 새 기록기 %r, 되돌린 뒤 active=%r" % (a1, a2, second_log is not first_log, after), "OK" if a1 and a2 and after is None else "CHECK")
say("R14b", "경계가 없을 때 arm_error_log", "반환 %r, active=%r" % (boundary.arm_error_log(lambda: WORK), errorlog.active()), "OK" if errorlog.active() is None else "CHECK")
installed = boundary.install_gui(qt=False)
boundary.arm_error_log(lambda: os.path.join(WORK, "a3"))
installed.uninstall()
installed = boundary.install_gui(qt=False)
say("R14c", "uninstall 뒤 다시 install_gui", "active(기록기)=%r (켜지 않았으니 None 이어야)" % (errorlog.active(),), "OK" if errorlog.active() is None else "CHECK")
installed.uninstall()

# ---- R15 훅 안의 재진입: 쓰는 도중 같은 스레드에서 다시 부름 ------------------------------------------------------------------------------
log, root = fresh()
real_append = errorlog.ErrorLog._append
state = {"n": 0}


def nested(self, line):
    if state["n"] < 3:
        state["n"] += 1
        rec(self, "unraisable")
    return real_append(self, line)


errorlog.ErrorLog._append = nested
try:
    result = []
    t = threading.Thread(target=lambda: result.append(rec(log)))
    t.start()
    t.join(15)
finally:
    errorlog.ErrorLog._append = real_append
say("R15", "쓰는 도중 같은 스레드가 3단 재진입", "스레드 살아있음=%r, 결과 %r, 줄 %d" % (t.is_alive(), result, len(open(os.path.join(root, 'logs', 'errors.log')).read().splitlines())), "OK" if not t.is_alive() and result == [True] else "CHECK")

# ---- R16 훅 안에서 기록기가 KeyboardInterrupt 를 맞음 -------------------------------------------------------------------------------------
log, root = fresh()


def raise_ki(self, line):
    raise KeyboardInterrupt()


errorlog.ErrorLog._append = raise_ki
try:
    try:
        ret = rec(log)
        outcome = "삼킴 %r" % ret
    except KeyboardInterrupt:
        outcome = "KeyboardInterrupt 가 밖으로 전달됨(의도된 동작)"
finally:
    errorlog.ErrorLog._append = real_append
lock_free = log._lock.acquire(timeout=1)
if lock_free:
    log._lock.release()
say("R16", "쓰는 중 KeyboardInterrupt", "%s, 잠금은 풀림=%r" % (outcome, lock_free), "OK" if lock_free else "CHECK")

print("DONE", len(rows))
