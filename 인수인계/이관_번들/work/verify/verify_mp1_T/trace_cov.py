"""Line-execution check for pipeline/merge_policy.py using the stdlib trace module (verifier, read-only on the tree)."""
import io
import os
import sys
import trace
import unittest

ROOT = "C:/work/ai/verify_mp1_T/tree_lf"
os.chdir(ROOT)
sys.dont_write_bytecode = True
sys.path.insert(0, ROOT + "/tests")
sys.path.insert(0, ROOT)
MODE = sys.argv[1] if len(sys.argv) > 1 else "behavior"
TARGET = os.path.normcase(os.path.abspath(ROOT + "/pipeline/merge_policy.py"))


def run():
    import _bootstrap  # noqa: F401
    import test_merge_policy
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_merge_policy)
    if MODE == "both":
        import test_merge_policy_docs
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(test_merge_policy_docs))
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    print("tests run:", result.testsRun, "failures:", len(result.failures), "errors:", len(result.errors))
    for case, text in result.failures + result.errors:
        print("FAILED:", case.id(), "|", text.strip().split(chr(10))[-1][:160])


tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])
tracer.runfunc(run)
counts = tracer.results().counts
executed = {line for (fname, line), _n in counts.items() if os.path.normcase(os.path.abspath(fname)) == TARGET}
executable = set(trace._find_executable_linenos(TARGET))
missing = sorted(executable - executed)
print("mode:", MODE)
print("executable lines:", len(executable), "executed:", len(executable & executed), "missing:", len(missing))
src = open(TARGET, encoding="utf-8").read().split("\n")
for line in missing[:60]:
    print("  MISSING line %d: %s" % (line, src[line - 1].strip()[:120]))
