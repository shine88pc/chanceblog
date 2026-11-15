"""AP14: 스택이 거의 가득 찬 곳에서 기록기를 불러도 기록기 안에서 난 예외가 밖으로 새지 않는지(남은 깊이 1..80 칸마다 시험).
사용: python -B -X utf8 probe_recursion.py <tree 폴더> <임시 작업 폴더>
"""
import os
import sys
import datetime as dt

TREE, WORK = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(TREE, "src"))
sys.path.insert(0, TREE)
from chanceblog_desktop.security import errorlog  # noqa: E402

FIXED = dt.datetime(2026, 11, 15, 7, 41, 5, tzinfo=dt.timezone.utc)
root = os.path.join(WORK, "rec")
log = errorlog.ErrorLog(lambda: root, clock=lambda: FIXED, rate=(10 ** 9, 60.0))

escaped_inside = []      # (남은 칸, 예외 이름) — 기록기(errorlog.py) 안의 프레임이 든 예외가 밖으로 나온 경우
call_site_only = []      # 호출 자리에서 난 것(시험 도구의 호출 자체가 한도를 넘김) — 기록기와 무관
ok_true, ok_false = [], []

state = {"depth": 0, "limit": sys.getrecursionlimit()}


def probe_at_every_headroom():
    """한도에 닿은 RecursionError 를 받은 뒤, 프레임이 하나씩 풀릴 때마다(남은 칸이 하나씩 늘 때마다) 기록기를 부른다. 남은 칸은 호출 없이 센다(깊이 변수 차이)."""
    results = {}
    holder = {}

    def descend(depth):
        try:
            descend(depth + 1)
        except RecursionError as error:
            if "deepest" not in holder:
                holder["deepest"] = depth
            headroom = holder["deepest"] - depth
            if headroom not in results and headroom <= 80:
                try:
                    returned = log.record("main", type(error), error, error.__traceback__)
                    results[headroom] = ("returned", returned)
                except BaseException as exc:  # noqa: BLE001
                    tb = exc.__traceback__
                    inside = False
                    while tb is not None:
                        if tb.tb_frame.f_code.co_filename.endswith("errorlog.py"):
                            inside = True
                        tb = tb.tb_next
                    results[headroom] = ("escaped_inside" if inside else "call_site", type(exc).__name__)
            raise

    try:
        descend(0)
    except RecursionError:
        pass
    return results


results = probe_at_every_headroom()
for headroom in sorted(results):
    kind, value = results[headroom]
    if kind == "escaped_inside":
        escaped_inside.append((headroom, value))
    elif kind == "call_site":
        call_site_only.append((headroom, value))
    elif value:
        ok_true.append(headroom)
    else:
        ok_false.append(headroom)

print("python", sys.version.split()[0], "limit", state["limit"])
print("headrooms probed:", len(results), "min", min(results) if results else None, "max", max(results) if results else None)
print("record returned True at headrooms:", ok_true[:3], "..." if len(ok_true) > 3 else "", "(%d)" % len(ok_true))
print("record returned False (line dropped) at headrooms:", ok_false[:5], "(%d)" % len(ok_false))
print("call-site RecursionError (harness only) at headrooms:", call_site_only[:5], "(%d)" % len(call_site_only))
print("ESCAPED FROM INSIDE errorlog.py:", escaped_inside if escaped_inside else "none")
