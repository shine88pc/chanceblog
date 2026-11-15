"""Check that every mutant spec (implementer's 182 + my K-series) has its old text exactly once in the LF tree (read-only)."""
import importlib.util
import sys

ROOT = "C:/work/ai/verify_mp1_T/tree_lf/"
sys.argv = ["x"]
spec = importlib.util.spec_from_file_location("mv", "C:/work/ai/verify_mp1_T/mutate_v.py")
mv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mv)


def check(mutants, label):
    bad = 0
    for m in mutants:
        if "append" in m:
            continue
        data = open(ROOT + m["path"], "rb").read()
        count = data.count(m["old"].encode("utf-8"))
        if count != 1:
            bad += 1
            print(label, m["id"], "occurs", count, "|", m["old"][:70].replace("\n", "\\n"))
    print(label, "specs:", len(mutants), "invalid:", bad)


check(mv.MUTANTS, "orig")
mine = mv._load_mine()
check(mine, "mine")
