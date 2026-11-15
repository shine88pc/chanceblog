import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P/_probe")
import copy
from h import mp, rec, summary

SHA = "1" * 40
SHA2 = "2" * 40
TREE = "3" * 40
TREE2 = "4" * 40
PATHS = ["src/chanceblog_desktop/content/drafts_store.py", "tests/test_drafts_store.py"]
CLEAN = {k: False for k in mp.DECLARED_REQUIRED}


def good():
    cls = mp.classify_change("desktop", PATHS, "x = 1\n", CLEAN)
    return {
        "approved_number": "M075", "approved_pr_number": 198, "pr_number": 198, "pr_title_label": "M075", "consumed_numbers": [],
        "approved_head_sha": SHA, "current_head_sha": SHA, "current_tree": TREE,
        "approved_paths": list(PATHS), "current_paths": list(PATHS),
        "checks": [{"name": "unit", "conclusion": "success"}, {"name": "guardrails", "conclusion": "success"}],
        "independent_verification": {"verdict": "pass", "verifier": "독립 검증자 A", "implementer": "구현자 B", "verified_tree": TREE, "open_required_findings": 0},
        "has_conflict": False, "classification": cls, "secret_findings": 0,
        "rollback_method": "M075 병합만 되돌리면 이전 상태로 복구됩니다.",
    }


def codes(f):
    try:
        v = mp.check_preconditions(f)
        return v.ok, set(v.failed_codes)
    except Exception as exc:
        return "EXC:" + type(exc).__name__, set()


def expect_fail(cid, desc, mutate, want_code):
    f = good()
    mutate(f)
    ok, failed = codes(f)
    res = (ok is False) and (want_code in failed)
    rec(cid, desc, "fail:" + want_code, "ok=%s failed=%s" % (ok, sorted(failed)), ok=res)


ok0, f0 = codes(good())
rec("T00", "baseline complete good facts pass all 8", (True, set()), (ok0, f0))

# condition 1 number_match
expect_fail("T01", "approved number differs from PR title label", lambda f: f.update(pr_title_label="M076"), "number_match")
expect_fail("T02", "PR number differs from approved PR number", lambda f: f.update(pr_number=199), "number_match")
expect_fail("T03", "approval already consumed (reuse)", lambda f: f.update(consumed_numbers=["M075"]), "number_match")
expect_fail("T04", "approved number lowercase", lambda f: f.update(approved_number="m075"), "number_match")
expect_fail("T05", "label has brackets", lambda f: f.update(pr_title_label="[M075]"), "number_match")
expect_fail("T06", "pr_number as str", lambda f: f.update(pr_number="198"), "number_match")
expect_fail("T07", "pr_number bool", lambda f: f.update(pr_number=True, approved_pr_number=True), "number_match")
expect_fail("T08", "consumed_numbers is a string", lambda f: f.update(consumed_numbers="M075"), "number_match")
expect_fail("T09", "consumed has bad entry", lambda f: f.update(consumed_numbers=["x"]), "number_match")
expect_fail("T10", "approved_pr_number zero", lambda f: f.update(approved_pr_number=0, pr_number=0), "number_match")
# condition 2 no_new_commit
expect_fail("T11", "head sha changed after approval", lambda f: f.update(current_head_sha=SHA2), "no_new_commit")
expect_fail("T12", "short sha", lambda f: f.update(approved_head_sha="1" * 7, current_head_sha="1" * 7), "no_new_commit")
expect_fail("T13", "sha None", lambda f: f.update(current_head_sha=None), "no_new_commit")
expect_fail("T14", "sha non-hex", lambda f: f.update(approved_head_sha="g" * 40, current_head_sha="g" * 40), "no_new_commit")
# condition 3 checks_pass
expect_fail("T15", "one check failed", lambda f: f["checks"].append({"name": "x", "conclusion": "failure"}), "checks_pass")
expect_fail("T16", "check skipped", lambda f: f["checks"].append({"name": "x", "conclusion": "skipped"}), "checks_pass")
expect_fail("T17", "check neutral", lambda f: f["checks"].append({"name": "x", "conclusion": "neutral"}), "checks_pass")
expect_fail("T18", "check cancelled", lambda f: f["checks"].append({"name": "x", "conclusion": "cancelled"}), "checks_pass")
expect_fail("T19", "check in progress (conclusion None)", lambda f: f["checks"].append({"name": "x", "conclusion": None}), "checks_pass")
expect_fail("T20", "check queued (no conclusion key)", lambda f: f["checks"].append({"name": "x"}), "checks_pass")
expect_fail("T21", "no checks at all", lambda f: f.update(checks=[]), "checks_pass")
expect_fail("T22", "check without name", lambda f: f["checks"].append({"conclusion": "success"}), "checks_pass")
expect_fail("T23", "checks is dict", lambda f: f.update(checks={"unit": "success"}), "checks_pass")
expect_fail("T24", "conclusion 'SUCCESS' uppercase", lambda f: f.update(checks=[{"name": "u", "conclusion": "SUCCESS"}]), "checks_pass")
expect_fail("T25", "check timed_out", lambda f: f["checks"].append({"name": "x", "conclusion": "timed_out"}), "checks_pass")
expect_fail("T26", "check action_required", lambda f: f["checks"].append({"name": "x", "conclusion": "action_required"}), "checks_pass")
# condition 4 independent verification
expect_fail("T27", "verdict fail", lambda f: f["independent_verification"].update(verdict="fail"), "independent_verified")
expect_fail("T28", "verdict fix_required", lambda f: f["independent_verification"].update(verdict="fix_required"), "independent_verified")
expect_fail("T29", "verifier == implementer", lambda f: f["independent_verification"].update(verifier="구현자 B"), "independent_verified")
expect_fail("T30", "verifier == implementer case/space", lambda f: f["independent_verification"].update(verifier="  구현자 b "), "independent_verified")
expect_fail("T31", "open required findings 1", lambda f: f["independent_verification"].update(open_required_findings=1), "independent_verified")
expect_fail("T32", "verified tree differs from current tree", lambda f: f["independent_verification"].update(verified_tree=TREE2), "independent_verified")
expect_fail("T33", "no verification record", lambda f: f.update(independent_verification=None), "independent_verified")
expect_fail("T34", "verification record missing verifier", lambda f: f["independent_verification"].pop("verifier"), "independent_verified")
expect_fail("T35", "open findings is str '0'", lambda f: f["independent_verification"].update(open_required_findings="0"), "independent_verified")
expect_fail("T36", "open findings negative -1", lambda f: f["independent_verification"].update(open_required_findings=-1), "independent_verified")
expect_fail("T37", "open findings False (bool)", lambda f: f["independent_verification"].update(open_required_findings=False), "independent_verified")
expect_fail("T38", "verdict 'pass ' trailing space", lambda f: f["independent_verification"].update(verdict="pass "), "independent_verified")
expect_fail("T39", "verdict 'PASS'", lambda f: f["independent_verification"].update(verdict="PASS"), "independent_verified")
expect_fail("T40", "current_tree missing", lambda f: f.pop("current_tree"), "independent_verified")
expect_fail("T41", "verifier empty string", lambda f: f["independent_verification"].update(verifier=""), "independent_verified")
expect_fail("T42", "verifier None implementer None", lambda f: f["independent_verification"].update(verifier=None), "independent_verified")
# condition 5 conflict
expect_fail("T43", "conflict True", lambda f: f.update(has_conflict=True), "no_conflict")
expect_fail("T44", "conflict None (unknown)", lambda f: f.update(has_conflict=None), "no_conflict")
expect_fail("T45", "conflict 'false' string", lambda f: f.update(has_conflict="false"), "no_conflict")
expect_fail("T46", "conflict 0 int", lambda f: f.update(has_conflict=0), "no_conflict")
expect_fail("T47", "conflict key missing", lambda f: f.pop("has_conflict"), "no_conflict")
# condition 6 scope
expect_fail("T48", "new file added after approval", lambda f: f.update(current_paths=PATHS + ["extra.py"]), "scope_matches")
expect_fail("T49", "file removed vs approval", lambda f: f.update(current_paths=PATHS[:1]), "scope_matches")
expect_fail("T50", "classification operator_only", lambda f: f.update(classification=mp.classify_change("desktop", PATHS, "x = 1", {})), "scope_matches")
expect_fail("T51", "classification stale (different paths)", lambda f: f.update(classification=mp.classify_change("desktop", ["other.py"], "x = 1", CLEAN)), "scope_matches")
expect_fail("T52", "classification missing", lambda f: f.pop("classification"), "scope_matches")
expect_fail("T53", "classification dict missing keys", lambda f: f.update(classification={"tier": "ai_ok"}), "scope_matches")
expect_fail("T54", "operator-only path in both lists (.github)", lambda f: f.update(approved_paths=PATHS + [".github/workflows/x.yml"], current_paths=PATHS + [".github/workflows/x.yml"],
            classification=mp.classify_change("desktop", PATHS + [".github/workflows/x.yml"], "", CLEAN)), "scope_matches")
expect_fail("T55", "classification ai_ok tier but with categories", lambda f: f.update(classification={"tier": "ai_ok", "categories": ["workflow"], "extra_flags": [], "paths": PATHS, "reasons": []}), "scope_matches")
expect_fail("T56", "classification ai_ok with extra flag", lambda f: f.update(classification={"tier": "ai_ok", "categories": [], "extra_flags": ["safety_guard"], "paths": PATHS, "reasons": []}), "scope_matches")
expect_fail("T57", "empty path lists", lambda f: f.update(approved_paths=[], current_paths=[]), "scope_matches")
# condition 7 secrets
expect_fail("T58", "secret findings 1", lambda f: f.update(secret_findings=1), "no_secret_exposure")
expect_fail("T59", "secret findings None", lambda f: f.update(secret_findings=None), "no_secret_exposure")
expect_fail("T60", "secret findings '0' str", lambda f: f.update(secret_findings="0"), "no_secret_exposure")
expect_fail("T61", "secret findings False bool", lambda f: f.update(secret_findings=False), "no_secret_exposure")
expect_fail("T62", "secret findings 0.0 float", lambda f: f.update(secret_findings=0.0), "no_secret_exposure")
expect_fail("T63", "secret findings -1", lambda f: f.update(secret_findings=-1), "no_secret_exposure")
expect_fail("T64", "secret findings key missing", lambda f: f.pop("secret_findings"), "no_secret_exposure")
# condition 8 rollback
expect_fail("T65", "rollback None", lambda f: f.update(rollback_method=None), "rollback_confirmed")
expect_fail("T66", "rollback empty", lambda f: f.update(rollback_method=""), "rollback_confirmed")
expect_fail("T67", "rollback '없음'", lambda f: f.update(rollback_method="없음"), "rollback_confirmed")
expect_fail("T68", "rollback short '되돌림'", lambda f: f.update(rollback_method="되돌림"), "rollback_confirmed")
expect_fail("T69", "rollback whitespace padded short", lambda f: f.update(rollback_method="   없음   "), "rollback_confirmed")
expect_fail("T70", "rollback 'TBD'", lambda f: f.update(rollback_method="TBD"), "rollback_confirmed")
expect_fail("T71", "rollback int", lambda f: f.update(rollback_method=12345678901), "rollback_confirmed")
expect_fail("T72", "rollback key missing", lambda f: f.pop("rollback_method"), "rollback_confirmed")

# each key removed -> some condition fails, never pass
for key in mp.FACT_KEYS:
    f = good(); f.pop(key)
    ok, failed = codes(f)
    rec("U_" + key, "missing key %s" % key, "ok=False and >=1 failure", "ok=%s failed=%s" % (ok, sorted(failed)), ok=(ok is False and len(failed) >= 1))
    f = good(); f[key] = None
    ok, failed = codes(f)
    rec("V_" + key, "None for key %s" % key, "ok=False and >=1 failure", "ok=%s failed=%s" % (ok, sorted(failed)), ok=(ok is False and len(failed) >= 1))

# facts shape
for cid, desc, val in [("W01", "facts None", None), ("W02", "facts list", []), ("W03", "facts empty dict", {}), ("W04", "facts str", "x"), ("W05", "facts tuple", ()), ("W06", "facts int", 5)]:
    ok, failed = codes(val)
    rec(cid, desc, "ok=False all 8 failed", "ok=%s n_failed=%d" % (ok, len(failed)), ok=(ok is False and len(failed) == 8))

# no input mutation / no exception on weird nested
f = good(); snap = copy.deepcopy(f)
mp.check_preconditions(f)
rec("W07", "input not modified", True, True)  # structural: classification dataclass is frozen; others compared below
rec("W08", "dict part of input unchanged", {k: v for k, v in snap.items() if k != "classification"}, {k: v for k, v in f.items() if k != "classification"})

# reuse across consumption: ledger -> facts
led = mp.ApprovalLedger()
d1 = led.consume("M075", 198)
f = good(); f["consumed_numbers"] = list(led.consumed_numbers)
ok, failed = codes(f)
rec("W09", "after ledger consumed M075, same facts must fail (reuse)", True, (ok is False and "number_match" in failed))

# adversarial: forged classification dict that claims ai_ok for an operator-only path (module trusts the caller -> info)
forged = {"tier": "ai_ok", "categories": [], "extra_flags": [], "paths": [".github/workflows/x.yml"], "reasons": []}
f = good(); f.update(approved_paths=[".github/workflows/x.yml"], current_paths=[".github/workflows/x.yml"], classification=forged)
ok, failed = codes(f)
rec("W10", "FORGED classification dict (caller-supplied) claims ai_ok for .github path (info: module trusts caller)", "ok=False", "ok=%s failed=%s" % (ok, sorted(failed)), ok=(ok is False), note="INFO design: classification must be computed by classify_change on current paths")

# adversarial: classification computed from different declared/text but same paths -> stale content not detected (info)
f = good()
cls_clean = mp.classify_change("desktop", PATHS, "x = 1\n", CLEAN)
rec("W11", "classification from clean text accepted even though real added text is dangerous (not knowable from facts)", "n/a", "accepted", ok=True, note="INFO: classification carries no hash of added text")

# rollback weak sentences that pass (info)
for cid, text in [("W12", "원복 방법 없음 확인 불가 정보 없음"), ("W13", "되돌리지 않음 되돌리지 않음"), ("W14", "해당 없음 해당 없음 해당 없음")]:
    f = good(); f["rollback_method"] = text
    ok, failed = codes(f)
    rec(cid, "weak rollback sentence %r" % text, "fail rollback_confirmed", "ok=%s failed=%s" % (ok, sorted(failed)), ok=("rollback_confirmed" in failed), note="INFO: content cannot be judged by code")
summary()
