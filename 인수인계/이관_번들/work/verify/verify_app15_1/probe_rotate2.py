"""AP14 2차 — 새 `_rotate`(이름 바꾸기만, `.2` 를 먼저 지우지 않음)가 한도·보존·막힘 처리·옛 파일 0개 설정에서 안전한지 진짜 파일 잠금으로 본다.
사용: python -B -X utf8 probe_rotate2.py <tree 폴더> <임시 작업 폴더>   (작업 폴더는 verify_app15_1 아래여야 한다)
"""
import builtins
import contextlib
import datetime as dt
import errno
import hashlib
import os
import random
import stat
import subprocess
import sys
import threading

TREE, WORK = sys.argv[1], sys.argv[2]
assert WORK.replace("\\", "/").startswith("C:/work/ai/verify_app15_1/"), "쓰기는 verify_app15_1 아래만"
sys.path.insert(0, os.path.join(TREE, "src"))
from chanceblog_desktop.security import errorlog  # noqa: E402

FIXED = dt.datetime(2026, 11, 15, 7, 41, 5, tzinfo=dt.timezone.utc)
MAX = errorlog.MAX_BYTES
counter = [0]
HOLDER = "import sys\nh=open(sys.argv[1],'rb')\nprint('held',flush=True)\nsys.stdin.readline()\n"


def fresh(**options):
    counter[0] += 1
    root = os.path.join(WORK, "p%03d" % counter[0])
    options.setdefault("clock", lambda: FIXED)
    options.setdefault("rate", (10 ** 9, 60.0))
    return errorlog.ErrorLog(lambda: root, **options), root


def boom():
    try:
        raise ValueError("m")
    except ValueError as error:
        return error


def rec(log):
    error = boom()
    return log.record("main", type(error), error, error.__traceback__)


def snapshot(root):
    folder = os.path.join(root, "logs")
    out = {}
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                with open(path, "rb") as handle:
                    data = handle.read()
                out[name] = (len(data), hashlib.sha256(data).hexdigest()[:10])
            else:
                out[name] = ("DIR", "")
    return out


def plant(root, current_fill=MAX - 10):
    folder = os.path.join(root, "logs")
    os.makedirs(folder, exist_ok=True)
    for name, data in (("errors.log", b"a" * current_fill), ("errors.log.1", b"b" * 60), ("errors.log.2", b"c" * 50)):
        with open(os.path.join(folder, name), "wb") as handle:
            handle.write(data)
    return folder


@contextlib.contextmanager
def held(path):
    proc = subprocess.Popen([sys.executable, "-B", "-X", "utf8", "-c", HOLDER, path], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        proc.stdout.readline()
        yield proc
    finally:
        with contextlib.suppress(Exception):
            proc.stdin.write(b"\n")
            proc.stdin.flush()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def say(key, what, result, verdict):
    print("%s | %s | %s | %s" % (key, what, result, verdict), flush=True)


def short(snap):
    return {name: (value[0] if value[0] != "DIR" else "DIR") for name, value in snap.items()}


# ---- A/B/C: 진짜 잠금 — .1 / .2 / errors.log 를 다른 프로세스가 연 채 --------------------------------------------------------------------------
for key, target, label in (("S4a", "errors.log.1", ".1"), ("S4b", "errors.log.2", ".2"), ("S4c", "errors.log", "errors.log(현재 파일)")):
    log, root = fresh()
    folder = plant(root)
    before = snapshot(root)
    with held(os.path.join(folder, target)):
        ret = rec(log)
        during = snapshot(root)
    unchanged = during == before
    ret2 = rec(log)
    after = snapshot(root)
    say(key, "%s 를 다른 프로세스가 연 채 한도 직전에 새 줄" % label,
        "record=%r, 막힌 동안 파일 셋 그대로=%r %s, 풀린 뒤 record=%r 파일 %s" % (ret, unchanged, short(during) if not unchanged else "", ret2, short(after)),
        "OK(.2 보존)" if unchanged else "옛 `.2` 가 덮어 쓰였다(첫 단계가 먼저 끝난 뒤 막힘)")
    if not unchanged:
        # .2 의 내용이 옛 .1 로 바뀌었는지, 옛 .2 가 어디에도 없는지
        folder_files = {n: open(os.path.join(folder, n), "rb").read()[:1] for n in os.listdir(folder)}
        say(key + "-detail", "막힌 동안 첫 글자 표", {n: v for n, v in folder_files.items()}, "(옛 .2 의 'c' 는 어디에도 없으면 유실)")

# ---- D: 옛 파일 0개 설정 --------------------------------------------------------------------------------------------------------------------
log, root = fresh(max_bytes=300, backups=0)
ok = [rec(log) for _ in range(30)]
snap = snapshot(root)
say("S4d", "옛 파일 0개(backups=0), 한도 300 B 로 30줄", "기록 %d줄, 파일 %s, 최대 크기 %d" % (sum(ok), short(snap), max(v[0] for v in snap.values())), "OK" if list(snap) == ["errors.log"] and max(v[0] for v in snap.values()) <= 300 else "CHECK")
log, root = fresh(max_bytes=300, backups=0)
for _ in range(5):
    rec(log)
path = os.path.join(root, "logs", "errors.log")
with held(path):
    before = snapshot(root)
    results = [rec(log) for _ in range(10)]
    after = snapshot(root)
say("S4e", "옛 파일 0개 + 현재 파일을 다른 프로세스가 연 채 한도를 넘기는 줄들", "결과 %s, 파일 크기 전후 %s → %s" % (results, short(before), short(after)), "OK(한도 안, 예외 없음)" if max(v[0] for v in after.values()) <= 300 else "한도 초과")
log, root = fresh(max_bytes=300, backups=-1)
ok = [rec(log) for _ in range(10)]
say("S4e2", "backups=-1 (음수) 설정", "기록 %d줄, 파일 %s" % (sum(ok), short(snapshot(root))), "OK(0과 같게 동작)" if list(snapshot(root)) == ["errors.log"] else "CHECK")

# ---- E: 정확한 경계 262,144 B -----------------------------------------------------------------------------------------------------------------
log, root = fresh()
rec(log)
line_len = snapshot(root)["errors.log"][0]
path = os.path.join(root, "logs", "errors.log")
with open(path, "wb") as handle:
    handle.write(b"x" * (MAX - line_len))
r_fit = rec(log)
fit = snapshot(root)
with open(path, "wb") as handle:
    handle.write(b"x" * (MAX - line_len + 1))
r_over = rec(log)
over = snapshot(root)
say("S4f", "새 줄이 정확히 262,144 B 가 되는 경우 / 1 B 넘는 경우", "맞는 경우 %s, 넘는 경우 %s" % (short(fit), short(over)),
    "OK" if fit.get("errors.log", (0,))[0] == MAX and "errors.log.1" in over and max(v[0] for v in over.values()) <= MAX else "CHECK")

# ---- F: 읽기 전용 속성·폴더가 자리를 차지 ------------------------------------------------------------------------------------------------------
log, root = fresh()
folder = plant(root)
os.chmod(os.path.join(folder, "errors.log.2"), stat.S_IREAD)
before = snapshot(root)
ret = rec(log)
after = snapshot(root)
os.chmod(os.path.join(folder, "errors.log.2"), stat.S_IWRITE | stat.S_IREAD)
say("S4g", "`.2` 가 읽기 전용 속성", "record=%r, 파일 셋 그대로=%r" % (ret, before == after), "OK(막힘, 안 바뀜)" if before == after else "바뀜: %s → %s" % (short(before), short(after)))
log, root = fresh()
folder = plant(root)
os.remove(os.path.join(folder, "errors.log.2"))
os.makedirs(os.path.join(folder, "errors.log.2"))
before = snapshot(root)
ret = rec(log)
after = snapshot(root)
say("S4h", "`.2` 자리에 같은 이름의 폴더", "record=%r, 파일 셋 그대로=%r" % (ret, before == after), "OK(막힘, 안 바뀜)" if before == after else "바뀜: %s → %s" % (short(before), short(after)))

# ---- G: 같은 폴더에 기록기 둘(자물쇠가 다름)이 동시에 돌려씀 -------------------------------------------------------------------------------------
root = os.path.join(WORK, "twolog")
logs = [errorlog.ErrorLog(lambda: root, clock=lambda: FIXED, max_bytes=4000, rate=(10 ** 9, 60.0)) for _ in range(2)]
orig_wait = errorlog.LOCK_WAIT
errorlog.LOCK_WAIT = 60.0
errors = []
flags = []


def work(log):
    for _ in range(300):
        try:
            flags.append(rec(log))
        except BaseException as exc:  # noqa: BLE001
            errors.append(type(exc).__name__)


threads = [threading.Thread(target=work, args=(logs[i % 2],)) for i in range(8)]
for t in threads:
    t.start()
for t in threads:
    t.join()
errorlog.LOCK_WAIT = orig_wait
snap = snapshot(root)
say("S4i", "서로 다른 기록기 둘이 같은 폴더에서 스레드 8개로 한도 4000 B 돌려쓰기", "예외 %s, 쓴 줄 %d/%d, 파일 %s" % (errors or "없음", sum(flags), len(flags), short(snap)),
    "OK(예외 0, 파일 ≤3, 각 ≤4000)" if not errors and len(snap) <= 3 and max(v[0] for v in snap.values()) <= 4000 else "CHECK")

# ---- H: 무작위 막힘을 섞은 압박 시험 --------------------------------------------------------------------------------------------------------
rng = random.Random(20261115)
real_replace = os.replace
problems = []
for backups in (0, 1, 2, 3):
    root = os.path.join(WORK, "stress_b%d" % backups)
    log = errorlog.ErrorLog(lambda root=root: root, clock=lambda: FIXED, max_bytes=1000, backups=backups, rate=(10 ** 9, 60.0))

    def flaky_replace(src, dst, rng=rng):
        if rng.random() < 0.25:
            raise PermissionError(errno.EACCES, "무작위 막힘")
        return real_replace(src, dst)

    errorlog.os.replace = flaky_replace
    written = 0
    try:
        for _ in range(1500):
            try:
                written += 1 if rec(log) else 0
            except BaseException as exc:  # noqa: BLE001
                problems.append((backups, type(exc).__name__))
    finally:
        errorlog.os.replace = real_replace
    snap = snapshot(root)
    folder = os.path.join(root, "logs")
    torn = 0
    for name in snap:
        for line in open(os.path.join(folder, name), "rb").read().decode().splitlines():
            if not line.startswith("2026-11-15T07:41:05Z main ValueError "):
                torn += 1
    if len(snap) > backups + 1 or max(v[0] for v in snap.values()) > 1000 or torn:
        problems.append((backups, "files=%d max=%d torn=%d" % (len(snap), max(v[0] for v in snap.values()), torn)))
    say("S4j-b%d" % backups, "무작위 25%% 이름 바꾸기 막힘 + 1500줄, 보관 수 %d, 한도 1000 B" % backups, "기록 %d줄, 파일 %s, 찢어진 줄 %d" % (written, short(snap), torn), "OK" if not problems else "CHECK")
say("S4j", "압박 시험 종합", "문제 %s" % (problems or "없음"), "OK" if not problems else "문제 있음")

# ---- I: 쓰다 실패한 조각(I3)은 여전히 이어붙는가 ---------------------------------------------------------------------------------------------
log, root = fresh()
rec(log)
real_open = builtins.open


class Half:
    def __init__(self, handle):
        self.h = handle

    def write(self, data):
        self.h.write(data[:12])
        self.h.flush()
        raise OSError(errno.ENOSPC, "No space left on device")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.h.close()
        return False


def half_open(file, mode="r", *a, **k):
    h = real_open(file, mode, *a, **k)
    return Half(h) if "a" in mode and "errors.log" in str(file) else h


builtins.open = half_open
try:
    r1 = rec(log)
finally:
    builtins.open = real_open
r2 = rec(log)
text = real_open(os.path.join(root, "logs", "errors.log"), "rb").read().decode()
say("S4k", "쓰다 12바이트에서 ENOSPC 뒤 다음 줄(I3)", "첫 %r, 다음 %r, 줄 길이 %s" % (r1, r2, [len(x) for x in text.split("\n")]), "여전히 이어붙음(정보)" if len(text.splitlines()) == 2 and not text.splitlines()[1].startswith("2026") else "OK")
print("DONE")
