"""전체 시험 개수 세기(실행하지 않고 찾기만) — 사용: <파이썬> -X utf8 count_tests.py <작업 폴더>
CI 와 같은 방식(`unittest discover -s tests`)으로 찾아 개수와 PySide6 가 있는지를 적는다. 시험은 돌리지 않는다."""
import os
import sys
import unittest

root = os.path.abspath(sys.argv[1])
tests = os.path.join(root, "tests")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.path[:0] = [os.path.join(root, "src"), tests, root]
suite = unittest.TestLoader().discover(tests, pattern="test*.py", top_level_dir=tests)
try:
    import importlib.util
    have_qt = importlib.util.find_spec("PySide6") is not None
except Exception:
    have_qt = False
print(f"python={sys.version.split()[0]} pyside6={have_qt} tests={suite.countTestCases()}")
