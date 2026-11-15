"""Light probes of current behavior on edge inputs (read-only; imports the LF tree module)."""
import os
import sys

ROOT = "C:/work/ai/verify_mp1_T/tree_lf"
sys.dont_write_bytecode = True
sys.path.insert(0, ROOT)
from pipeline import merge_policy as mp  # noqa: E402


def facts():
    paths = ["pipeline/topics.py", "tests/test_topics.py"]
    return {
        "approved_number": "M075", "approved_pr_number": 198, "pr_number": 198, "pr_title_label": "M075", "consumed_numbers": [],
        "approved_head_sha": "1" * 40, "current_head_sha": "1" * 40, "current_tree": "3" * 40,
        "approved_paths": list(paths), "current_paths": list(paths),
        "checks": [{"name": "a", "conclusion": "success"}],
        "independent_verification": {"verdict": "pass", "verifier": "v", "implementer": "i", "verified_tree": "3" * 40, "open_required_findings": 0},
        "has_conflict": False,
        "classification": mp.classify_change("blog", paths, "x = 1\n", {c: False for c in mp.DECLARED_REQUIRED}).to_dict(),
        "secret_findings": 0,
        "rollback_method": "문제가 생기면 M075 병합 커밋 하나만 되돌립니다.",
    }


print("DEL path:", mp.normalize_repo_path("a" + chr(127) + "b"))
f = facts()
print("good:", mp.check_preconditions(f).ok)
for value in (False, 0.0):
    g = facts()
    g["independent_verification"]["open_required_findings"] = value
    print("open_required_findings=%r ->" % (value,), mp.check_preconditions(g).failed_codes)
    g = facts()
    g["secret_findings"] = value
    print("secret_findings=%r ->" % (value,), mp.check_preconditions(g).failed_codes)
g = facts()
g["checks"] = [{"name": "   ", "conclusion": "success"}]
print("whitespace-only check name ->", mp.check_preconditions(g).failed_codes)
g = facts()
g["independent_verification"]["verdict"] = "fix_required"
print("verdict fix_required ->", mp.check_preconditions(g).failed_codes)
for path in ("assets/.ppk", "keys/server.ppk", "vault.kdbx", "pnpm-lock.yaml", "blogger_ko_history.json", "src/app.msi", "dist/app.exe"):
    for kind in ("blog", "desktop"):
        r = mp.classify_change(kind, [path], "", {c: False for c in mp.DECLARED_REQUIRED})
        print("%-8s %-28s -> %s %s %s" % (kind, path, r.tier, r.categories, r.extra_flags))
print("approval texts:")
for text in ("M075 승인", "M075 승인\n", "m075 승인.", "M075  승인", "M075 승인!", "M075 승인 감사", "확인했습니다", "M075 M076 승인", "M0075 승인", "승인"):
    c = mp.check_approval_text(text)
    print("  %-20r -> %s %s" % (text, c.number, c.reason))
