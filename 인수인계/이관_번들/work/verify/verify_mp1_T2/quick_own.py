"""Quick in-process source-level run of a selection of my own designed mutants (my_mutants.py, module-file ones only) against the WIP 6 tests.
Each mutant: replace the exact old text once in the module source, exec the mutated source into the live module namespace, run the full behavior+docs suite (failfast), restore."""
import io
import os
import sys
import time
import unittest

ROOT = "C:/work/ai/verify_mp1_T2/tree_lf"
os.chdir(ROOT)
sys.dont_write_bytecode = True
sys.path.insert(0, ROOT + "/tests")
sys.path.insert(0, ROOT)
import _bootstrap  # noqa: E402,F401
from pipeline import merge_policy as mp  # noqa: E402
import test_merge_policy as tmp  # noqa: E402
import test_merge_policy_docs as tdoc  # noqa: E402

MODULE_PATH = ROOT + "/pipeline/merge_policy.py"
SRC = open(MODULE_PATH, encoding="utf-8").read()
MOD = "pipeline/merge_policy.py"
DOC = "docs/AI_MERGE_POLICY.md"


def M(mid, area, what, old, new, path=MOD):
    return {"id": mid, "area": area, "what": what, "path": path, "old": old, "new": new}


ns = {"M": M, "A": None, "MOD": MOD, "DOC": DOC}
exec(open("C:/work/ai/verify_mp1_T2/my_mutants.py", encoding="utf-8").read(), ns)
MY = [m for m in ns["MY_MUTANTS"] if m["path"] == MOD]
WANT = sys.argv[1].split(",") if len(sys.argv) > 1 else [m["id"] for m in MY]


def full_suite():
    suite = unittest.TestSuite()
    for module in (tmp, tdoc):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    return suite


def run(failfast=True):
    res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0, failfast=failfast).run(full_suite())
    bad = res.failures + res.errors
    first = bad[0][0].id().split(".")[-2] + "." + bad[0][0].id().split(".")[-1] if bad else ""
    return res.testsRun, len(bad), first


def load(src):
    exec(compile(src, MODULE_PATH, "exec"), mp.__dict__)


started = time.time()
out = []
for mutant in MY:
    if mutant["id"] not in WANT:
        continue
    if SRC.count(mutant["old"]) != 1:
        out.append("%-5s SPEC-INVALID occurs=%d" % (mutant["id"], SRC.count(mutant["old"])))
        print(out[-1], flush=True)
        continue
    try:
        load(SRC.replace(mutant["old"], mutant["new"]))
        ran, bad, first = run()
    finally:
        load(SRC)
    out.append("%-5s %-9s %-44s %s" % (mutant["id"], "RED" if bad else "SURVIVED", mutant["what"][:44], ("<- " + first) if first else ""))
    print(out[-1], flush=True)
ran, bad, first = run(failfast=False)
print("after restore: ran=%d failed=%d  (%d s)" % (ran, bad, time.time() - started), flush=True)
open("C:/work/ai/verify_mp1_T2/own_inproc_results.txt", "w", encoding="utf-8").write("\n".join(out) + "\nafter restore: ran=%d failed=%d\n" % (ran, bad))
