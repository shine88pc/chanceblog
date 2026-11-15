"""usage: python make_eff.py <mutant id from my_mut_new.py> <dest under C:/work/ai/verify_app15_2/v2/>
Copies final2 to <dest> and applies the mutant's edit(s) there (never touches final2 or the real worktree)."""
import importlib.util
import os
import shutil
import stat
import sys
from pathlib import Path

sys.dont_write_bytecode = True
mid, dest = sys.argv[1], Path(sys.argv[2])
assert str(dest).replace("\\", "/").startswith("C:/work/ai/verify_app15_2/v2/"), dest
spec = importlib.util.spec_from_file_location("d", "C:/work/ai/verify_app15_2/v2/my_mut_new.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
definition = module.MUTATIONS[mid]
edits = definition["edits"] if "edits" in definition else [{"file": definition["file"], "old": definition["old"], "new": definition["new"]}]


def force(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


if dest.exists():
    shutil.rmtree(dest, onexc=force)
shutil.copytree("C:/work/ai/verify_app15_2/final2", dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for edit in edits:
    path = dest / edit["file"]
    data = path.read_bytes()
    assert data.count(edit["old"].encode("utf-8")) == 1, (edit["file"], "anchor")
    path.write_bytes(data.replace(edit["old"].encode("utf-8"), edit["new"].encode("utf-8")))
print("mutant", mid, "applied in", dest)
