import importlib.util
import sys

ROOT = "C:/work/ai/verify_mp1_T/tree_lf/"
sys.argv = ["x"]
spec = importlib.util.spec_from_file_location("mv2", "C:/work/ai/verify_mp1_T/mutate_v2.py")
mv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mv)
mine = mv._load_mine()
bad = 0
for m in mine:
    data = open(ROOT + m["path"], "rb").read()
    count = data.count(m["old"].encode("utf-8"))
    if count != 1:
        bad += 1
        print(m["id"], "occurs", count, "|", m["old"][:80])
print("round2 specs:", len(mine), "invalid:", bad)
