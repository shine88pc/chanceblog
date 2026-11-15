"""probe helper: import the copy's merge_policy and collect results."""
import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P2")
sys.dont_write_bytecode = True
from pipeline import merge_policy as mp  # noqa: E402

ROWS = []
FAILS = []


def rec(cid, desc, expected, actual, ok=None, note=""):
    if ok is None:
        ok = (expected == actual)
    ROWS.append((cid, desc, expected, actual, ok, note))
    flag = "OK  " if ok else "DIFF"
    line = "%s %-6s | %s | expected=%r | actual=%r" % (flag, cid, desc, expected, actual)
    if note:
        line += " | " + note
    print(line)
    if not ok:
        FAILS.append(cid)


def summary():
    print("---- total=%d diff=%d" % (len(ROWS), len(FAILS)))
    if FAILS:
        print("DIFF ids:", ", ".join(FAILS))
