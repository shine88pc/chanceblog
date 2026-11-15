"""usage: python make_copy2.py <repo path> <commit> <dest folder under C:/work/ai/verify_app15_2/>
Extracts `git archive <commit>` (autocrlf off => LF) of <repo> into <dest> (fresh). Read-only on <repo>."""
import io
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

repo, commit, dest = sys.argv[1], sys.argv[2], Path(sys.argv[3])
assert str(dest).replace("\\", "/").startswith("C:/work/ai/verify_app15_2/"), dest


def force(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


if dest.exists():
    shutil.rmtree(dest, onexc=force)
dest.mkdir(parents=True)
data = subprocess.run(["git", "-c", "core.autocrlf=false", "-C", repo, "archive", commit], capture_output=True, check=True).stdout
with tarfile.open(fileobj=io.BytesIO(data)) as archive:
    archive.extractall(dest, filter="data")
print("copy ready:", dest, sum(1 for p in dest.rglob("*") if p.is_file()), "files")
