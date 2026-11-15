"""AP14 2차 — 생존한 변이가 진짜 어떤 결과를 내는지 보인다(복사본 tree2 의 errorlog.py 를 메모리에서 일부러 틀리게 해 verify_app15_1/demo2 아래에 파일로 쓰고 불러온다).
사용: python -B -X utf8 demo_survivors2.py
"""
import datetime as dt
import importlib.util
import os
import sys
import traceback

HERE = "C:/work/ai/verify_app15_1"
TREE = HERE + "/tree2"
OUT = HERE + "/demo2"
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, TREE + "/src")
import chanceblog_desktop.security  # noqa: E402,F401  (부모 패키지)

SRC = open(TREE + "/src/chanceblog_desktop/security/errorlog.py", encoding="utf-8", newline="").read()
FIXED = dt.datetime(2026, 11, 15, 7, 41, 5, tzinfo=dt.timezone.utc)


def mutate(name, old, new):
    old_t, new_t = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    text = SRC if (old_t not in SRC) else SRC
    use_old, use_new = (old_t, new_t) if old_t in SRC else (old, new)
    assert SRC.count(use_old) == 1, (name, SRC.count(use_old))
    path = f"{OUT}/errorlog_{name}.py"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(SRC.replace(use_old, use_new))
    spec = importlib.util.spec_from_file_location(f"chanceblog_desktop.security.errorlog_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


real = importlib.import_module("chanceblog_desktop.security.errorlog")
x01 = mutate("X01", '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-]{0,63}")', '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-' + chr(0x2212) + ']{0,63}")')
x02 = mutate("X02", '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")', '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_' + chr(0xFF21) + "-" + chr(0xFF3A) + ']{0,63}")')
x03 = mutate("X03", "while trace is not None and steps < 10_000:", "while trace is not None and steps < 100:")
x07 = mutate("X07", "if size > 0 and size + len(data) > self._max_bytes:", "if size > 0 and size + len(data) > self._max_bytes + 5:")
x09 = mutate("X09", "rate=(RATE_COUNT, RATE_SECONDS)", "rate=(10 ** 6, RATE_SECONDS)")
x19 = mutate("X19", 'name = getattr(kind, "__name__", None) if isinstance(kind, type) else None', 'name = getattr(kind, "__name__", None)')

print("X01 파일 이름 'a\u2212b.py'(마이너스 기호):  원본 =", repr(real._short_file("C:/x/a" + chr(0x2212) + "b.py")), "| 변이 =", repr(x01._short_file("C:/x/a" + chr(0x2212) + "b.py")), "(비ASCII 가 줄에 들어감)")
fw = type("E" + chr(0xFF21), (Exception,), {})
print("X02 클래스 이름 'E전각A':                 원본 =", repr(real._class_name(fw, None)), "| 변이 =", repr(x02._class_name(fw, None)))
print("X19 클래스가 아닌 것(len 함수)을 kind 로:   원본 =", repr(real._class_name(len, None)), "| 변이 =", repr(x19._class_name(len, None)))


def deep(count):
    if count == 0:
        raise RuntimeError("깊다")
    deep(count - 1)


try:
    deep(400)
except RuntimeError as error:
    true_inner = [f"{os.path.basename(f.filename)}:{f.lineno}" for f in traceback.extract_tb(error.__traceback__)][-6:][::-1]
    got = {}
    for label, module in (("원본", real), ("X03 변이", x03)):
        places = module._frames(error.__traceback__)
        got[label] = places
print("X03 깊이 400 추적(진짜 가장 안쪽 여섯):", true_inner)
for label, places in got.items():
    print("    %s ->" % label, places, "(맞음)" if places == true_inner else "(틀림 — 가장 안쪽이 아니다)")


def run_limit(module, label):
    root = f"{HERE}/demo2/limit_{label}"
    log = module.ErrorLog(lambda: root, clock=lambda: FIXED, rate=(10 ** 9, 60.0))
    try:
        raise ValueError("m")
    except ValueError as err:
        log.record("main", ValueError, err, err.__traceback__)
    path = root + "/logs/errors.log"
    line_len = os.path.getsize(path)
    with open(path, "wb") as handle:
        handle.write(b"x" * (module.MAX_BYTES - line_len + 3))           # 새 줄이 들어오면 한도보다 3 바이트 크다
    try:
        raise ValueError("m")
    except ValueError as err:
        log.record("main", ValueError, err, err.__traceback__)
    sizes = {n: os.path.getsize(f"{root}/logs/{n}") for n in sorted(os.listdir(root + "/logs"))}
    return sizes


for label, module in (("원본", real), ("X07 변이", x07)):
    sizes = run_limit(module, label.replace(" ", "_"))
    print("X07 한도보다 3바이트 큰 줄 — %s: 파일 %s, 최대 %d (한도 %d)" % (label, sizes, max(sizes.values()), real.MAX_BYTES))


def rate_run(module):
    root = f"{HERE}/demo2/rate_{module.__name__.split('.')[-1]}"
    log = module.ErrorLog(lambda: root, clock=lambda: FIXED)
    count = 0
    for _ in range(100):
        try:
            raise ValueError("m")
        except ValueError as err:
            count += 1 if log.record("main", ValueError, err, err.__traceback__) else 0
    return count


print("X09 기본값으로 100번 연속 — 원본 기록 %d줄 | 변이 기록 %d줄" % (rate_run(real), rate_run(x09)))
