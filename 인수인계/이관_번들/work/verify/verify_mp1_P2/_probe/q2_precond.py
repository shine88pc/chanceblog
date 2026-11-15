import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P2/_probe")
import copy
from h import mp, rec, summary

A, B, C = "1" * 40, "2" * 40, "9" * 40
TREE, TREE2 = "3" * 40, "4" * 40
PATHS = ["pipeline/calc.py", "tests/test_calc.py"]
TEXT = "def f(x):\n    return x + 1\n"
CLEAN = {k: False for k in mp.DECLARED_REQUIRED}


def good(kind="blog", paths=PATHS, text=TEXT):
    cls = mp.classify_change(kind, paths, text, CLEAN)
    return {
        "approved_number": "M075", "approved_pr_number": 198, "pr_number": 198, "pr_title_label": "M075", "consumed_numbers": [],
        "approved_head_sha": A, "current_head_sha": A, "head_sha_at_approval": A, "current_tree": TREE,
        "approved_paths": list(paths), "current_paths": list(paths),
        "checks": [{"name": "unit", "conclusion": "success"}, {"name": "guardrails", "conclusion": "success"}],
        "required_checks": ["unit", "guardrails"], "previous_merge_main_check": "success", "pr_state": "open", "pr_draft": False,
        "independent_verification": {"verdict": "pass", "verifier": "독립 검증자 A", "implementer": "구현자 B", "verified_tree": TREE, "open_required_findings": 0},
        "has_conflict": False, "classification": cls, "secret_findings": 0, "rollback_method": "M075 병합만 되돌리면 이전 상태로 복구됩니다.",
        "repo_kind": kind, "changed_text": text,
    }


def codes(f):
    try:
        v = mp.check_preconditions(f)
        return v.ok, set(v.failed_codes)
    except Exception as exc:
        return "EXC:" + type(exc).__name__, set()


def expect_fail(cid, desc, mutate, want_code, kind="blog", paths=PATHS, text=TEXT):
    f = good(kind, paths, text)
    mutate(f)
    ok, failed = codes(f)
    rec(cid, desc, "fail:" + want_code, "ok=%s failed=%s" % (ok, sorted(failed)), ok=(ok is False and want_code in failed))


ok0, f0 = codes(good())
rec("T00", "baseline (23 facts) passes all 8", (True, set()), (ok0, f0))
rec("T00b", "FACT_KEYS has 23 keys and the baseline supplies exactly them", True, set(good().keys()) == set(mp.FACT_KEYS) and len(mp.FACT_KEYS) == 23)
ok1, f1 = codes(good("desktop", ["src/chanceblog_desktop/content/drafts_store.py", "tests/test_drafts_store.py"]))
rec("T00c", "desktop baseline passes", (True, set()), (ok1, f1))

# ---- old mutations still failing
expect_fail("T01", "title label differs", lambda f: f.update(pr_title_label="M076"), "number_match")
expect_fail("T02", "PR number differs", lambda f: f.update(pr_number=199), "number_match")
expect_fail("T03", "approval already consumed", lambda f: f.update(consumed_numbers=["M075"]), "number_match")
expect_fail("T04", "approved number lowercase", lambda f: f.update(approved_number="m075"), "number_match")
expect_fail("T05", "label with brackets", lambda f: f.update(pr_title_label="[M075]"), "number_match")
expect_fail("T11", "head changed after approval", lambda f: f.update(current_head_sha=B), "no_new_commit")
expect_fail("T15", "a check failed", lambda f: f["checks"].append({"name": "x", "conclusion": "failure"}), "checks_pass")
expect_fail("T16", "a check skipped", lambda f: f["checks"].append({"name": "x", "conclusion": "skipped"}), "checks_pass")
expect_fail("T21", "no checks", lambda f: f.update(checks=[]), "checks_pass")
expect_fail("T27", "verdict fail", lambda f: f["independent_verification"].update(verdict="fail"), "independent_verified")
expect_fail("T29", "verifier == implementer", lambda f: f["independent_verification"].update(verifier="구현자 B"), "independent_verified")
expect_fail("T31", "open required findings", lambda f: f["independent_verification"].update(open_required_findings=2), "independent_verified")
expect_fail("T32", "verified tree differs", lambda f: f["independent_verification"].update(verified_tree=TREE2), "independent_verified")
expect_fail("T43", "conflict", lambda f: f.update(has_conflict=True), "no_conflict")
expect_fail("T44", "conflict unknown", lambda f: f.update(has_conflict=None), "no_conflict")
expect_fail("T48", "file added after approval", lambda f: f.update(current_paths=PATHS + ["pipeline/new.py"]), "scope_matches")
expect_fail("T49", "file removed vs approval", lambda f: f.update(current_paths=PATHS[:1]), "scope_matches")
expect_fail("T58", "secret findings", lambda f: f.update(secret_findings=1), "no_secret_exposure")
expect_fail("T65", "rollback None", lambda f: f.update(rollback_method=None), "rollback_confirmed")
expect_fail("T67", "rollback short", lambda f: f.update(rollback_method="없음"), "rollback_confirmed")
for i, text in enumerate(["해당 사항이 없습니다", "원복 방법이 없습니다", "원복 방법 확인 불가", "추후 결정 예정입니다", "되돌릴 필요가 없습니다", "별도로 정하지 않았습니다", "To Be Decided", "NOT APPLICABLE"], 1):
    expect_fail("T7%d" % i, "rollback placeholder %r" % text, lambda f, t=text: f.update(rollback_method=t), "rollback_confirmed")

# ---- W10: forged classification (the old hole) must fail now
forged = {"tier": "ai_ok", "categories": [], "extra_flags": [], "paths": [".github/workflows/x.yml"], "reasons": []}
expect_fail("F01", "FORGED classification (ai_ok) for a .github path, repo_kind and text given", lambda f: f.update(approved_paths=[".github/workflows/x.yml"], current_paths=[".github/workflows/x.yml"],
            classification=forged, changed_text="on: push"), "scope_matches")
expect_fail("F02", "forged classification for README.md in a blog repo", lambda f: f.update(approved_paths=["README.md"], current_paths=["README.md"],
            classification={"tier": "ai_ok", "categories": [], "extra_flags": [], "paths": ["README.md"], "reasons": []}, changed_text="문서"), "scope_matches")
expect_fail("F03", "forged classification for index.html", lambda f: f.update(approved_paths=["index.html"], current_paths=["index.html"],
            classification={"tier": "ai_ok", "categories": [], "extra_flags": [], "paths": ["index.html"], "reasons": []}, changed_text="<p>x</p>"), "scope_matches")
expect_fail("F04", "forged classification for a new page faq.md", lambda f: f.update(approved_paths=["faq.md"], current_paths=["faq.md"],
            classification={"tier": "ai_ok", "categories": [], "extra_flags": [], "paths": ["faq.md"], "reasons": []}, changed_text="문서"), "scope_matches")
expect_fail("F05", "forged classification for pipeline/publish_lock.py (named safety file)", lambda f: f.update(approved_paths=["pipeline/publish_lock.py"], current_paths=["pipeline/publish_lock.py"],
            classification={"tier": "ai_ok", "categories": [], "extra_flags": [], "paths": ["pipeline/publish_lock.py"], "reasons": []}, changed_text="x = 1"), "scope_matches")
# classification computed from clean text while the real changed_text carries a forbidden word (stale content) -> recompute catches it
expect_fail("F06", "classification from clean text, real changed_text has adsbygoogle", lambda f: f.update(changed_text="adsbygoogle"), "scope_matches")
expect_fail("F07", "classification from clean text, real changed_text has PIPELINE_PAUSE in code", lambda f: f.update(changed_text="os.environ.get('PIPELINE_PAUSE')"), "scope_matches")
expect_fail("F08", "classification from clean text, real changed_text imports requests", lambda f: f.update(changed_text="import requests"), "scope_matches")
expect_fail("F09", "classification from clean text, real changed_text has a secret shape", lambda f: f.update(changed_text="k = '" + "AI" + "za" + "CANARY_" + "A" * 28 + "'"), "scope_matches")
expect_fail("F10", "changed_text is a dict whose key is not in the change list", lambda f: f.update(changed_text={"docs/other.md": "x"}), "scope_matches")
expect_fail("F11", "changed_text missing key", lambda f: f.pop("changed_text"), "scope_matches")
expect_fail("F12", "changed_text None", lambda f: f.update(changed_text=None), "scope_matches")
expect_fail("F13", "changed_text int", lambda f: f.update(changed_text=5), "scope_matches")
expect_fail("F14", "repo_kind missing", lambda f: f.pop("repo_kind"), "scope_matches")
expect_fail("F15", "repo_kind invalid 'Blog'", lambda f: f.update(repo_kind="Blog"), "scope_matches")
expect_fail("F16", "repo_kind None", lambda f: f.update(repo_kind=None), "scope_matches")
expect_fail("F17", "repo_kind int", lambda f: f.update(repo_kind=1), "scope_matches")
expect_fail("F18", "recompute with a deleted ad line (removed line text) in a code file", lambda f: f.update(changed_text="-<ins class=\"adsbygoogle\"></ins>"), "scope_matches")
expect_fail("F19", "classification declared operator_only via declared item (human): caller classification says external_cost", lambda f: f.update(
    classification=mp.classify_change("blog", PATHS, TEXT, dict(CLEAN, external_cost=True))), "scope_matches")
# the trust boundary on repo_kind (info): a blog change with README.md + faq.md passes if the caller says desktop
f = good("desktop", ["README.md", "faq.md"], "문서")
ok, failed = codes(f)
rec("F20", "INFO: caller lies repo_kind=desktop for blog files README.md+faq.md (module cannot know the repo)", "ok=True", "ok=%s failed=%s" % (ok, sorted(failed)), ok=(ok is True), note="INFO trust boundary: repo_kind must be a constant of the repo's workflow")
# classification with declared True forged False (human-only) -> cannot be recomputed (documented 7-3)
f = good()
rec("F21", "declared items cannot be recomputed (documented) -- no check", "n/a", "n/a", ok=True, note="INFO documented 7-3")

# ---- required_checks
expect_fail("R01", "required_checks missing", lambda f: f.pop("required_checks"), "checks_pass")
expect_fail("R02", "required_checks empty list", lambda f: f.update(required_checks=[]), "checks_pass")
expect_fail("R03", "required_checks None", lambda f: f.update(required_checks=None), "checks_pass")
expect_fail("R04", "required_checks has empty-string name", lambda f: f.update(required_checks=["unit", ""]), "checks_pass")
expect_fail("R05", "required_checks has whitespace name", lambda f: f.update(required_checks=["unit", "   "]), "checks_pass")
expect_fail("R06", "required_checks names a check that never ran", lambda f: f.update(required_checks=["unit", "guardrails", "never-ran"]), "checks_pass")
expect_fail("R07", "required_checks is a string", lambda f: f.update(required_checks="unit"), "checks_pass")
expect_fail("R08", "required_checks has a non-str name", lambda f: f.update(required_checks=["unit", 5]), "checks_pass")
expect_fail("R09", "required name present but its check failed", lambda f: f.update(checks=[{"name": "unit", "conclusion": "failure"}, {"name": "guardrails", "conclusion": "success"}]), "checks_pass")
expect_fail("R10", "required name differs by case", lambda f: f.update(required_checks=["Unit", "guardrails"]), "checks_pass")
expect_fail("R11", "required name differs by trailing space in result", lambda f: f.update(checks=[{"name": "unit ", "conclusion": "success"}, {"name": "guardrails", "conclusion": "success"}]), "checks_pass")
expect_fail("R12", "check with whitespace name", lambda f: f["checks"].append({"name": "   ", "conclusion": "success"}), "checks_pass")
expect_fail("R13", "duplicate name: one failure one success", lambda f: f["checks"].append({"name": "unit", "conclusion": "failure"}), "checks_pass")
ok, failed = codes((lambda f: (f.update(required_checks=("unit",)), f)[1])(good()))
rec("R14", "required_checks as tuple accepted", (True, set()), (ok, failed))
ok, failed = codes((lambda f: (f.update(required_checks={"unit", "guardrails"}), f)[1])(good()))
rec("R15", "required_checks as set accepted", (True, set()), (ok, failed))
ok, failed = codes((lambda f: (f.update(required_checks=["unit"], checks=[{"name": "unit", "conclusion": "success"}]), f)[1])(good()))
rec("R16", "INFO: caller chooses required_checks (a one-item list passes) -- must come from a trusted constant", (True, set()), (ok, failed), note="INFO trust boundary")

# ---- previous_merge_main_check (post-merge gate)
for cid, val, exp_ok in [("P01", "success", True), ("P02", "none", True), ("P03", "failure", False), ("P04", "pending", False), ("P05", None, False), ("P06", "", False), ("P07", "SUCCESS", False),
                         ("P08", " success", False), ("P09", True, False), ("P10", 1, False), ("P11", ["success"], False), ("P12", "unknown", False), ("P13", "cancelled", False), ("P14", "None", False)]:
    f = good(); f["previous_merge_main_check"] = val
    ok, failed = codes(f)
    rec(cid, "previous_merge_main_check=%r" % (val,), exp_ok, ok is True, note="failed=%s" % sorted(failed))
f = good(); f.pop("previous_merge_main_check")
ok, failed = codes(f)
rec("P15", "previous_merge_main_check key missing", False, ok is True, note="failed=%s" % sorted(failed))
f = good(); f["previous_merge_main_check"] = "failure"
ok, failed = codes(f)
rec("P16", "failure => checks_pass fails (every merge refused)", True, (ok is False and "checks_pass" in failed))
f = good(); f["previous_merge_main_check"] = "pending"
ok, failed = codes(f)
rec("P17", "pending => checks_pass fails", True, (ok is False and "checks_pass" in failed))

# ---- evaluate_post_merge table
for cid, val, may, actions in [("E01", "success", True, None), ("E02", "none", True, None), ("E03", "pending", False, ()), ("E04", "failure", False, mp.POST_MERGE_REVERT_ACTIONS)]:
    d = mp.evaluate_post_merge(val)
    rec(cid, "evaluate_post_merge(%r)" % val, (may, actions), (d.may_merge_next, d.only_actions))
for i, val in enumerate([None, "", "SUCCESS", " success", "Success", "failed", True, 1, ["success"], b"success", "none ", "FAILURE", "Pending"], 5):
    d = mp.evaluate_post_merge(val)
    rec("E%02d" % i, "evaluate_post_merge(%r) unknown => no merge, no actions" % (val,), (False, (), None), (d.may_merge_next, d.only_actions, d.state))


class S(str):
    pass


d = mp.evaluate_post_merge(S("success"))
rec("E20", "str subclass 'success' => unknown", (False, ()), (d.may_merge_next, d.only_actions))
rec("E21", "POST_MERGE_REVERT_ACTIONS has exactly the 2 documented actions", ("send_revert_request", "send_cause_explanation"), mp.POST_MERGE_REVERT_ACTIONS)
rec("E22", "failure reason mentions revert request + explanation", True, ("되돌리기 요청" in mp.evaluate_post_merge("failure").reason and "원인 설명" in mp.evaluate_post_merge("failure").reason))

# ---- ApprovalRecord and heads
rec("AR1", "ApprovalRecord same heads valid", True, mp.ApprovalRecord("M075", 198, A, A).valid)
rec("AR2", "ApprovalRecord heads differ => invalid", False, mp.ApprovalRecord("M075", 198, A, B).valid)
rec("AR3", "ApprovalRecord head None => invalid", False, mp.ApprovalRecord("M075", 198, None, A).valid)
rec("AR4", "ApprovalRecord short sha => invalid", False, mp.ApprovalRecord("M075", 198, "abc1234", "abc1234").valid)
rec("AR5", "ApprovalRecord bad number => invalid", False, mp.ApprovalRecord("m075", 198, A, A).valid)
rec("AR6", "ApprovalRecord bad pr => invalid", False, mp.ApprovalRecord("M075", True, A, A).valid)
rec("AR7", "ApprovalRecord problems() is a list of easy-language strings", True, all(isinstance(x, str) and len(x) > 5 for x in mp.ApprovalRecord("M075", 198, A, B).problems()))
rec("AR8", "ApprovalRecord str-subclass head => invalid", False, mp.ApprovalRecord("M075", 198, S(A), A).valid)
rec("AR9", "ApprovalRecord is frozen (immutable)", True, True)
try:
    mp.ApprovalRecord("M075", 198, A, A).number = "M076"
    rec("AR9", "ApprovalRecord is frozen (immutable)", True, False)
except Exception:
    rec("AR9", "ApprovalRecord is frozen (immutable)", True, True)
# head sequences through check_preconditions
for cid, (ap, ar, cu), exp in [("H1", (A, A, A), True), ("H2", (A, B, B), False), ("H3", (A, A, B), False), ("H4", (A, B, A), False), ("H5", (A, C, C), False), ("H6", (B, A, A), False)]:
    f = good(); f.update(approved_head_sha=ap, head_sha_at_approval=ar, current_head_sha=cu)
    ok, failed = codes(f)
    rec(cid, "heads explained=%s arrived=%s current=%s" % (ap[0], ar[0], cu[0]), exp, ok is True, note="failed=%s" % sorted(failed))
f = good(); f.pop("head_sha_at_approval")
ok, failed = codes(f)
rec("H7", "head_sha_at_approval missing", False, ok is True, note="failed=%s" % sorted(failed))
f = good(); f["head_sha_at_approval"] = A.upper()
ok, failed = codes(f)
rec("H8", "uppercase hex sha equal value accepted", True, ok is True)
f = good(); f["head_sha_at_approval"] = A + "\n"
ok, failed = codes(f)
rec("H9", "sha with trailing newline rejected", False, ok is True)

# ---- PR state / draft
for cid, val, exp in [("S1", "open", True), ("S2", "closed", False), ("S3", "merged", False), ("S4", "OPEN", False), ("S5", None, False), ("S6", "draft", False), ("S7", "", False), ("S8", True, False), ("S9", " open", False)]:
    f = good(); f["pr_state"] = val
    ok, failed = codes(f)
    rec(cid, "pr_state=%r" % (val,), exp, ok is True, note="failed=%s" % sorted(failed))
for cid, val, exp in [("D1", False, True), ("D2", True, False), ("D3", None, False), ("D4", "false", False), ("D5", 0, False), ("D6", "", False), ("D7", "False", False)]:
    f = good(); f["pr_draft"] = val
    ok, failed = codes(f)
    rec(cid, "pr_draft=%r" % (val,), exp, ok is True, note="failed=%s" % sorted(failed))
f = good(); f.pop("pr_state")
rec("S10", "pr_state key missing", False, codes(f)[0] is True)
f = good(); f.pop("pr_draft")
rec("D8", "pr_draft key missing", False, codes(f)[0] is True)

# ---- all 23 keys removed / None -> never passes
for key in mp.FACT_KEYS:
    f = good(); f.pop(key)
    ok, failed = codes(f)
    rec("U_" + key, "missing key %s" % key, "ok=False and >=1 failure", "ok=%s failed=%s" % (ok, sorted(failed)), ok=(ok is False and len(failed) >= 1))
    f = good(); f[key] = None
    ok, failed = codes(f)
    rec("V_" + key, "None for key %s" % key, "ok=False and >=1 failure", "ok=%s failed=%s" % (ok, sorted(failed)), ok=(ok is False and len(failed) >= 1))
for cid, val in [("W01", None), ("W02", []), ("W03", {}), ("W04", "x"), ("W05", ()), ("W06", 5)]:
    ok, failed = codes(val)
    rec(cid, "facts=%r" % (val,), "ok=False all 8", "ok=%s n=%d" % (ok, len(failed)), ok=(ok is False and len(failed) == 8))


class Boom(dict):
    def get(self, *a, **k):
        raise RuntimeError("boom")


ok, failed = codes(Boom(good()))
rec("W07", "dict subclass whose get() raises => fail closed (all 8 fail, no exception)", "ok=False all 8", "ok=%s n=%d" % (ok, len(failed)), ok=(ok is False and len(failed) == 8))
f = good(); snap = {k: copy.deepcopy(v) for k, v in f.items() if k != "classification"}
mp.check_preconditions(f)
rec("W08", "facts not modified", snap, {k: v for k, v in f.items() if k != "classification"})
# reuse after ledger
led = mp.ApprovalLedger()
led.consume("M075", 198)
f = good(); f["consumed_numbers"] = list(led.consumed_numbers)
ok, failed = codes(f)
rec("W09", "after ledger consumed M075 the same facts fail", True, (ok is False and "number_match" in failed))
summary()
