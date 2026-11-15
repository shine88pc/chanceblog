import importlib.util
import sys

sys.path.insert(0, "C:/work/ai/verify_mp1_T2")
sys.argv = ["x"]
import mutants_extra  # noqa: E402

spec = importlib.util.spec_from_file_location("mv", "C:/work/ai/verify_mp1_T2/mutate_v.py")
mv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mv)
new = [m["id"] for m in mutants_extra.NEW]
allids = [m["id"] for m in mv.MUTANTS]
old = [i for i in allids if i not in set(new)]
open("C:/work/ai/verify_mp1_T2/new_ids.txt", "w").write(",".join(new))
open("C:/work/ai/verify_mp1_T2/old_ids.txt", "w").write(",".join(old))
print("new", len(new), "old", len(old), "all", len(allids))
