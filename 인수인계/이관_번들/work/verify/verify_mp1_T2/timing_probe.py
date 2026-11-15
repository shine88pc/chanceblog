"""Stability probe for the input-8x time test (ClassifyExternalConnectionTest.test_long_adversarial_text_is_classified_in_linear_time).
Repeats the test's own measurement (`timed`: best of 2) for every adversarial family and prints the worst big/small ratio against the test's limit (25x, or 20 s when small < 0.01 s)."""
import os
import sys
import time

ROOT = "C:/work/ai/verify_mp1_T2/tree_lf"
os.chdir(ROOT)
sys.dont_write_bytecode = True
sys.path.insert(0, ROOT + "/tests")
sys.path.insert(0, ROOT)
import _bootstrap  # noqa: E402,F401
import test_merge_policy as tmp  # noqa: E402

case = tmp.ClassifyExternalConnectionTest("test_long_adversarial_text_is_classified_in_linear_time")
REPEATS = int(sys.argv[1]) if len(sys.argv) > 1 else 5
worst = []
fast_families = 0
for name, make in case.ADVERSARIAL:
    ratios, smalls, bigs = [], [], []
    for _ in range(REPEATS):
        small, big = case.timed(make(2500)), case.timed(make(20000))
        smalls.append(small)
        bigs.append(big)
        if small >= 0.01:
            ratios.append(big / small)
    if not ratios:
        fast_families += 1
    worst.append((max(ratios) if ratios else 0.0, name, max(smalls), max(bigs)))
worst.sort(reverse=True)
print("families:", len(case.ADVERSARIAL), "repeats:", REPEATS, "families always under the 0.01 s floor:", fast_families)
print("limit: 25x when small >= 0.01 s, else 20 s absolute")
for ratio, name, small, big in worst[:8]:
    print("  %-22s worst ratio %6.1fx  max small %.4f s  max big %.4f s" % (name, ratio, small, big))
print("max big over all families: %.3f s" % max(item[3] for item in worst))
