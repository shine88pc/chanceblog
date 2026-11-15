"""Is RETIRED mutant D15 really equivalent? Differential test of check_preconditions: original module vs the module with D15 applied, over a cross product of
`checks` x `required_checks` x `previous_merge_main_check` (+ the other 7 conditions staying valid). Compares failed codes and the condition-3 reason text."""
import itertools
import os
import sys
import types

ROOT = "C:/work/ai/verify_mp1_T2/tree_lf"
sys.dont_write_bytecode = True
sys.path.insert(0, ROOT + "/tests")
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import _bootstrap  # noqa: E402,F401
import test_merge_policy as tmp  # noqa: E402  (only for good_facts())

SRC = open(ROOT + "/pipeline/merge_policy.py", encoding="utf-8").read()
OLD = "    if not isinstance(checks, (list, tuple)) or not checks:"
NEW = "    if not isinstance(checks, (list, tuple)):"
assert SRC.count(OLD) == 1


def load(source, name):
    mod = types.ModuleType(name)
    mod.__file__ = ROOT + "/pipeline/merge_policy.py"
    exec(compile(source, mod.__file__, "exec"), mod.__dict__)
    return mod


orig, mutant = load(SRC, "orig_mp"), load(SRC.replace(OLD, NEW), "d15_mp")
CHECKS = ([], [{"name": "a", "conclusion": "success"}], [{"name": "a", "conclusion": "failure"}], [{"name": "a", "conclusion": "success"}, {"name": "b", "conclusion": "skipped"}],
          None, "x", (), [{"name": "a"}], [{"name": "b", "conclusion": "success"}], [{"name": "a", "conclusion": "success"}, {"name": "b", "conclusion": "success"}], 5, [None])
REQUIRED = (["a"], [], None, ["x"], ["a", "b"], "a", [""], [" "], ("a",), {"a"}, [1], ["b"])
PREVIOUS = ("success", "none", "failure", "pending", None, "x", "", 5)
codes_diff, reason_diff, total, empty_only = 0, 0, 0, 0
examples = []
for checks, required, previous in itertools.product(CHECKS, REQUIRED, PREVIOUS):
    facts = tmp.good_facts()
    facts["checks"], facts["required_checks"], facts["previous_merge_main_check"] = checks, required, previous
    a, b = orig.check_preconditions(facts), mutant.check_preconditions(facts)
    total += 1
    if a.failed_codes != b.failed_codes:
        codes_diff += 1
        if len(examples) < 5:
            examples.append((checks, required, previous, a.failed_codes, b.failed_codes))
    elif a.explain() != b.explain():
        reason_diff += 1
        if isinstance(checks, (list, tuple)) and not checks:
            empty_only += 1
print("combinations:", total)
print("failed-codes differences:", codes_diff)
print("reason-text-only differences:", reason_diff, "(of which checks empty:", empty_only, ")")
for example in examples:
    print("  DIFF", example)
# also show the single empty-checks case in words
facts = tmp.good_facts()
facts["checks"] = []
print("orig  empty checks ->", orig.check_preconditions(facts).explain())
print("D15   empty checks ->", mutant.check_preconditions(facts).explain())
