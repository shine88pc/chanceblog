import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P2/_probe")
from h import mp, rec, summary

S1 = "a" * 40
S2 = "b" * 39 + "a"
P = ["src/a.py", "tests/test_a.py"]

# ---- approval_matches
rec("B01", "matches same number", True, mp.approval_matches("M075", "M075"))
rec("B02", "matches different number", False, mp.approval_matches("M075", "M076"))
rec("B03", "matches lowercase approved", False, mp.approval_matches("m075", "M075"))
rec("B04", "matches both None", False, mp.approval_matches(None, None))
rec("B05", "matches trailing space", False, mp.approval_matches("M075 ", "M075"))
rec("B06", "matches PR label with brackets", False, mp.approval_matches("M075", "[M075]"))
rec("B07", "matches int", False, mp.approval_matches(75, 75))
rec("B08", "matches M0075 non-standard on both sides", False, mp.approval_matches("M0075", "M0075"))
rec("B09", "matches M75 non-standard both sides", False, mp.approval_matches("M75", "M75"))
rec("B10", "matches approved ok, label None", False, mp.approval_matches("M075", None))

# ---- pr_title_label
rec("B11", "title label standard", "M075", mp.pr_title_label("[M075] 앱 초안 저장"))
rec("B12", "title label not leading", None, mp.pr_title_label("fix [M075] x"))
rec("B13", "title label two tags", None, mp.pr_title_label("[M075] [M076] x"))
rec("B14", "title label lowercase", None, mp.pr_title_label("[m075] x"))
rec("B15", "title label None", None, mp.pr_title_label(None))
rec("B16", "title label M0075", None, mp.pr_title_label("[M0075] x"))
rec("B17", "title label leading space", None, mp.pr_title_label(" [M075] x"))
rec("B18", "title label NO-MERGE style", None, mp.pr_title_label("NO-MERGE x [M075]"))

# ---- approval_still_valid
rec("C01", "valid same sha+paths", True, mp.approval_still_valid(S1, S1, P, P))
rec("C02", "new commit (sha differs)", False, mp.approval_still_valid(S1, S2, P, P))
rec("C03", "paths differ (extra file)", False, mp.approval_still_valid(S1, S1, P, P + ["x.py"]))
rec("C04", "paths differ (missing file)", False, mp.approval_still_valid(S1, S1, P, P[:1]))
rec("C05", "empty path lists", False, mp.approval_still_valid(S1, S1, [], []))
rec("C06", "short sha", False, mp.approval_still_valid("abc1234", "abc1234", P, P))
rec("C07", "None sha", False, mp.approval_still_valid(None, None, P, P))
rec("C08", "sha trailing newline", False, mp.approval_still_valid(S1 + "\n", S1, P, P))
rec("C09", "upper vs lower sha same value", True, mp.approval_still_valid(S1.upper(), S1, P, P))
rec("C10", "paths str instead of list", False, mp.approval_still_valid(S1, S1, "src/a.py", "src/a.py"))
rec("C11", "path with .. segment", False, mp.approval_still_valid(S1, S1, ["a/../b.py"], ["a/../b.py"]))
rec("C12", "sha non-hex 40", False, mp.approval_still_valid("z" * 40, "z" * 40, P, P))
rec("C13", "same file list different order", True, mp.approval_still_valid(S1, S1, P, list(reversed(P))))
rec("C14", "path case differs (A.py vs a.py) - treated different", False, mp.approval_still_valid(S1, S1, ["src/A.py"], ["src/a.py"]))
rec("C15", "path normalisation ./a.py vs a.py", True, mp.approval_still_valid(S1, S1, ["./src/a.py"], ["src/a.py"]))
rec("C16", "sha int", False, mp.approval_still_valid(1, 1, P, P))
rec("C17", "sha one off at last char", False, mp.approval_still_valid(S1, "a" * 39 + "b", P, P))

# ---- ApprovalLedger
led = mp.ApprovalLedger()
d = led.consume("M075", 198)
rec("D01", "ledger first use ok", True, d.ok)
d = led.consume("M075", 199)
rec("D02", "reuse of number for other PR refused", False, d.ok)
d = led.consume("M076", 198)
rec("D03", "same PR under new number refused", False, d.ok)
rec("D04", "ledger state unchanged after refusals", ("M075",), led.consumed_numbers)
d = led.consume("m077", 200)
rec("D05", "lowercase number refused", False, d.ok)
d = led.consume("M077", True)
rec("D06", "bool PR number refused", False, d.ok)
d = led.consume("M077", 0)
rec("D07", "zero PR number refused", False, d.ok)
d = led.consume("M077", "200")
rec("D08", "str PR number refused", False, d.ok)
d = led.consume("M077", 200)
rec("D09", "fresh pair accepted", True, d.ok)
d = led.consume("M0078", 201)
rec("D10", "non-standard number refused", False, d.ok)
d = led.consume(None, None)
rec("D11", "None refused without exception", False, d.ok)
led2 = mp.ApprovalLedger(consumed=[("M075", 198)])
rec("D12", "ledger seeded from history refuses reuse", False, led2.consume("M075", 300).ok)
try:
    mp.ApprovalLedger(consumed=[("bad", 1)])
    rec("D13", "bad history raises ValueError", "ValueError", "no error")
except ValueError:
    rec("D13", "bad history raises ValueError", "ValueError", "ValueError")
try:
    mp.ApprovalLedger(consumed=42)
    rec("D14", "non-iterable history raises ValueError", "ValueError", "no error")
except ValueError:
    rec("D14", "non-iterable history raises ValueError", "ValueError", "ValueError")
# Interleaving case: attacker re-uses the SAME number M075 but with the same PR again
rec("D15", "same number & same PR twice refused", False, led.consume("M075", 198).ok)

# ---- merge_method_allowed
rec("E01", "pr_merge allowed", True, mp.merge_method_allowed("pr_merge"))
for i, v in enumerate(["push_main", "direct_push", "force_push", "squash", "merge", "rebase", "PR_MERGE", " pr_merge", "pr_merge ", "pr_merge\n",
                        "git push origin main", "push", "", "main", "force-push", "push_main_with_pc_credentials"], 2):
    rec("E%02d" % i, "method %r refused" % (v,), False, mp.merge_method_allowed(v))
for i, v in enumerate([None, 123, ["pr_merge"], b"pr_merge", True, object()], 20):
    rec("E%02d" % i, "method non-str %r refused" % (type(v).__name__,), False, mp.merge_method_allowed(v))

class EqAll(str):
    def __eq__(self, other):
        return True
    __hash__ = str.__hash__

rec("E30", "str subclass with always-true __eq__ (artificial)", False, mp.merge_method_allowed(EqAll("x")))
summary()
