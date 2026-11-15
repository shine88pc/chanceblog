import hashlib
import subprocess

WT = "C:/work/ai/improve_wt_mergepol1/"
AR = "C:/work/ai/verify_mp1_T/tree/"
for f in ["pipeline/merge_policy.py", "tests/test_merge_policy.py", "tests/test_merge_policy_docs.py", "docs/AI_MERGE_POLICY.md", "docs/DEFECT_REGISTER.md"]:
    a = open(WT + f, "rb").read()
    b = open(AR + f, "rb").read()
    same_after_norm = a.replace(b"\r\n", b"\n") == b
    print("%-34s wt=%d archive=%d wt_CRLF=%d wt_LF=%d equal_after_CRLF_to_LF=%s" % (f, len(a), len(b), a.count(b"\r\n"), a.count(b"\n"), same_after_norm))
for key in ("core.autocrlf", "core.eol"):
    out = subprocess.run(["git", "-C", WT, "config", "--get", key], capture_output=True, text=True).stdout.strip()
    print(key, "=", out or "(unset)")
