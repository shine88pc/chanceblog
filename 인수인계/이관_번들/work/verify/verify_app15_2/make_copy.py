"""usage: python make_copy.py <ref in replay repo> <dest folder>
Extracts `git archive <ref>` of the throw-away replay repo into <dest> (fresh). LF line endings (autocrlf off).
"""
import io
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

REPLAY = "C:/work/ai/verify_app15_2/replay"
ref, dest = sys.argv[1], Path(sys.argv[2])
assert str(dest).replace("\\", "/").startswith("C:/work/ai/verify_app15_2/"), dest


def force(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


if dest.exists():
    shutil.rmtree(dest, onexc=force)
dest.mkdir(parents=True)
data = subprocess.run(["git", "-c", "core.autocrlf=false", "-C", REPLAY, "archive", ref], capture_output=True, check=True).stdout
with tarfile.open(fileobj=io.BytesIO(data)) as archive:
    archive.extractall(dest, filter="data")
print("copy ready:", dest, sum(1 for _ in dest.rglob("*") if _.is_file()), "files")
