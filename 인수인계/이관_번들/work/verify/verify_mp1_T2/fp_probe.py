"""Empirical probe: classify the last N merged commits of origin/main (read-only git) with the new module, to see how broad the operator_only net is."""
import subprocess
import sys

ROOT = "C:/work/ai/verify_mp1_T2/tree_lf"
REPO = "C:/work/ai/improve_wt_mergepol1"
sys.dont_write_bytecode = True
sys.path.insert(0, ROOT)
from pipeline import merge_policy as mp  # noqa: E402


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True).stdout.decode("utf-8", "replace")


N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
shas = git("log", "-n", str(N), "--format=%H", "4b22239").split()
tally = {"ai_ok": 0, "operator_only": 0}
cat_count = {}
rows = []
for sha in shas:
    subject = git("log", "-n", "1", "--format=%s", sha).strip()[:70]
    names = [n for n in git("diff-tree", "--no-commit-id", "--name-status", "-r", "-M", sha).split("\n") if n.strip()]
    paths = []
    for entry in names:
        parts = entry.split("\t")
        paths += parts[1:]
    diff = git("show", "--unified=0", "--format=", sha)
    added = {}
    cur = None
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            cur = line[6:]
            added.setdefault(cur, [])
        elif line.startswith("+") and not line.startswith("+++") and cur:
            added[cur].append(line[1:])
    added_text = {k: "\n".join(v) for k, v in added.items()}
    if not paths:
        continue
    result = mp.classify_change("blog", paths, added_text, {c: False for c in mp.DECLARED_REQUIRED})
    tally[result.tier] += 1
    for c in result.categories + result.extra_flags:
        cat_count[c] = cat_count.get(c, 0) + 1
    rows.append((sha[:7], result.tier, ",".join(result.categories + result.extra_flags), len(paths), subject))
for r in rows:
    print("%s %-13s %-60s files=%-3d %s" % r)
print(tally, cat_count)
