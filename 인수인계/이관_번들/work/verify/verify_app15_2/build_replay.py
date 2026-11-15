"""Build a throw-away git repo that replays the six commits (tree for tree) from `git archive` output.
Read-only on the real worktree (only `git archive` / `git rev-parse`). Writes only under C:/work/ai/verify_app15_2/replay.
"""
import io
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

SRC = "C:/work/ai/improve_wt_app15"
T = Path("C:/work/ai/verify_app15_2/replay")
COMMITS = ["41ce292", "bb6b433", "65a4ede", "d028aeb", "0cc89c6", "b31a50e"]


def run(args, cwd, check=True):
    return subprocess.run(args, cwd=cwd, capture_output=True, check=check)


def out(args, cwd):
    return run(args, cwd).stdout.decode("utf-8", "replace").strip()


def _force(func, path, _exc):
    import os
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)


if T.exists():
    shutil.rmtree(T, onexc=_force)
T.mkdir(parents=True)
run(["git", "init", "-q"], T)
for key, value in (("user.name", "verifier"), ("user.email", "<이메일>"), ("core.autocrlf", "false"), ("core.safecrlf", "false")):
    run(["git", "config", key, value], T)

ok = True
for commit in COMMITS:
    for child in T.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    data = run(["git", "-c", "core.autocrlf=false", "-C", SRC, "archive", commit], ".").stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(T, filter="data")
    run(["git", "add", "-A", "-f"], T)
    run(["git", "commit", "-q", "--allow-empty", "-m", f"replay {commit}"], T)
    run(["git", "tag", f"r_{commit}"], T)
    mine = out(["git", "rev-parse", "HEAD^{tree}"], T)
    real = out(["git", "-C", SRC, "rev-parse", commit + "^{tree}"], ".")
    same = mine == real
    ok = ok and same
    print(f"{commit} replay tree {mine[:12]} real tree {real[:12]} {'SAME' if same else 'DIFFERENT'}")
print("ALL TREES IDENTICAL" if ok else "TREE MISMATCH")
sys.exit(0 if ok else 1)
