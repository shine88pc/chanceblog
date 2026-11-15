import subprocess
import sys

ROOT = "C:/work/ai/verify_mp1_T/tree_lf"
REPO = "C:/work/ai/improve_wt_mergepol1"
sys.dont_write_bytecode = True
sys.path.insert(0, ROOT)
from pipeline import merge_policy as mp  # noqa: E402


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True).stdout.decode("utf-8", "replace")


for sha in ("4b22239", "ca51d49", "b7b5f80", "10e9e09", "6c39942", "a85c04c"):
    names = [n.split("\t")[1:] for n in git("diff-tree", "--no-commit-id", "--name-status", "-r", "-M", sha).split("\n") if n.strip()]
    paths = [p for group in names for p in group]
    diff = git("show", "--unified=0", "--format=", sha)
    added, cur = {}, None
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            cur = line[6:]
            added.setdefault(cur, [])
        elif line.startswith("+") and not line.startswith("+++") and cur:
            added[cur].append(line[1:])
    result = mp.classify_change("blog", paths, {k: "\n".join(v) for k, v in added.items()}, {c: False for c in mp.DECLARED_REQUIRED})
    print(sha, result.tier, paths[:4])
    for reason in result.reasons[:6]:
        print("    ", reason[:170])
