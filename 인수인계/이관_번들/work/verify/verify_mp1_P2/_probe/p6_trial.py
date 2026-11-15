import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P2/_probe")
import copy
import time
from h import mp, rec, summary

KEYS = [k for k, _ in mp.TRIAL_CRITERIA]


def r(number, **over):
    d = {"number": number}
    for k in KEYS:
        d[k] = True
    d.update(over)
    return d


def ev(records):
    try:
        return mp.evaluate_trial(records)
    except Exception as exc:
        return "EXC:" + type(exc).__name__


G3 = [r("M075"), r("M076"), r("M077")]
rec("Z01", "3 good distinct", "continue", ev(G3))
rec("Z02", "2 good", "pending", ev(G3[:2]))
rec("Z03", "1 good", "pending", ev(G3[:1]))
rec("Z04", "0 records", "pending", ev([]))
rec("Z05", "4 good", "continue", ev(G3 + [r("M078")]))
rec("Z06", "3 good + 1 bad (4th records violation)", "stop_immediately", ev(G3 + [r("M078", no_revert=False)]))
rec("Z07", "1 bad only (fewer than 3)", "stop_immediately", ev([r("M075", no_wrong_merge=False)]))
for key, label in mp.TRIAL_CRITERIA:
    for pos in range(3):
        recs = copy.deepcopy(G3)
        recs[pos][key] = False
        rec("Z10_%s_%d" % (key, pos), "criterion %s False at position %d of 3" % (key, pos), "stop_immediately", ev(recs))
    rec("Z11_" + key, "criterion %s False on a single early record (1 record)" % key, "stop_immediately", ev([r("M075", **{key: False})]))
    rec("Z12_" + key, "criterion %s missing key" % key, "stop_immediately", ev([{k: v for k, v in G3[0].items() if k != key}, G3[1], G3[2]]))
    rec("Z13_" + key, "criterion %s string 'true'" % key, "stop_immediately", ev([r("M075", **{key: "true"}), G3[1], G3[2]]))
    rec("Z14_" + key, "criterion %s int 1" % key, "stop_immediately", ev([r("M075", **{key: 1}), G3[1], G3[2]]))
    if key != "main_checks_passed":
        rec("Z15_" + key, "criterion %s None" % key, "stop_immediately", ev([r("M075", **{key: None}), G3[1], G3[2]]))
rec("Z20", "main_checks_passed None in 3rd (still unknown)", "pending", ev([r("M075"), r("M076"), r("M077", main_checks_passed=None)]))
rec("Z21", "main None + another False => stop", "stop_immediately", ev([r("M075", main_checks_passed=None), r("M076", no_revert=False), r("M077")]))
rec("Z22", "duplicate number", "stop_immediately", ev([r("M075"), r("M075"), r("M077")]))
rec("Z23", "non-standard number M75", "stop_immediately", ev([r("M75"), r("M076"), r("M077")]))
rec("Z24", "lowercase number m075", "stop_immediately", ev([r("m075"), r("M076"), r("M077")]))
rec("Z25", "record not a dict", "stop_immediately", ev([G3[0], "x", G3[2]]))
rec("Z26", "records None", "stop_immediately", ev(None))
rec("Z27", "records dict", "stop_immediately", ev({"a": 1}))
rec("Z28", "records str", "stop_immediately", ev("abc"))
rec("Z29", "records tuple of 3 good", "continue", ev(tuple(G3)))
rec("Z30", "records generator (not list/tuple) -> stop", "stop_immediately", ev(x for x in G3))
rec("Z31", "3 good records with same number across 3 entries -> stop", "stop_immediately", ev([r("M075")] * 3))
rec("Z32", "4 good + 2nd record violation in the middle", "stop_immediately", ev([r("M075"), r("M076", approved_only=False), r("M077"), r("M078")]))
rec("Z33", "no number key", "stop_immediately", ev([{k: True for k in KEYS}, G3[1], G3[2]]))
rec("Z34", "extra unknown keys ignored", "continue", ev([dict(g, extra=1) for g in G3]))
rec("Z35", "number None", "stop_immediately", ev([r(None), G3[1], G3[2]]))
t = time.time(); res = ev([r("M%d" % (100 + i)) for i in range(5000) if 100 + i <= 9999]); dt = time.time() - t
rec("Z36", "4900 good records fast", "continue", res, note="%.2fs" % dt)
# good records plus a 'pending' unknown mixed with fewer than 3 distinct
rec("Z37", "2 good + 1 unknown-main => pending", "pending", ev([r("M075"), r("M076"), r("M077", main_checks_passed=None)]))
rec("Z38", "3 good where first main None (3rd all fine) => pending", "pending", ev([r("M075", main_checks_passed=None), r("M076"), r("M077")]))
rec("Z39", "report violations name the record", True, any("M075" in v for v in mp.trial_report([r("M075", no_revert=False)]).violations))
rec("Z40", "report counted for 3 good", 3, mp.trial_report(G3).counted)
# trial_report(records=[bool-True subclass]) etc
class T(int):
    pass
rec("Z41", "criterion value True-like int subclass -> stop (identity check)", "stop_immediately", ev([r("M075", no_revert=T(1)), G3[1], G3[2]]))
summary()
