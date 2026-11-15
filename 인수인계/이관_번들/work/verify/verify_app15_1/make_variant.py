"""생존한 변이가 진짜 새는지 보이려고 tree 의 사본(variant_<이름>)을 만들어 한 곳만 틀리게 한다. 사용: python make_variant.py <이름> <파일(상대)> <옛 글> <새 글>"""
import shutil
import sys
from pathlib import Path

HERE = Path("C:/work/ai/verify_app15_1")
name, rel, old, new = sys.argv[1:5]
target = HERE / ("variant_" + name)
if target.exists():
    shutil.rmtree(target)
shutil.copytree(HERE / "tree", target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
path = target / rel
data = path.read_bytes()
old_b, new_b = old.encode("utf-8"), new.encode("utf-8")
if data.count(old_b) != 1:
    raise SystemExit("옛 글이 %d번 나온다" % data.count(old_b))
path.write_bytes(data.replace(old_b, new_b))
print("만듦:", target)
