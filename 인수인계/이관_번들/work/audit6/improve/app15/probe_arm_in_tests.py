"""기존 시험 중 어느 것이 오류 기록을 실제로 켜는지 세는 도구(읽기만 — 시험 코드는 고치지 않는다).
사용: <파이썬> -X utf8 probe_arm_in_tests.py <작업 폴더> <시험 모듈> [<시험 모듈> ...]
방법: `errorlog.arm` 을 감싸 부르는 횟수와 그때 건넨 '폴더 알려 주기' 함수가 푸는 폴더를 센다. 기본 데이터 폴더가 시험 PC 의 진짜 폴더를 건드리지 않도록
`LOCALAPPDATA`·`XDG_DATA_HOME`·`CHANCEBLOG_DESKTOP_DATA` 를 임시 폴더로 돌려 놓고, 시험이 끝난 뒤 그 임시 폴더에 `logs` 가 생겼는지 본다(생겼다면 시험이 켜 둔 채 오류를 냈다는 뜻)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

root = Path(sys.argv[1]).resolve()
modules = sys.argv[2:]
tmp = tempfile.TemporaryDirectory()
base = Path(tmp.name)
os.environ["LOCALAPPDATA"] = str(base / "local")
os.environ["XDG_DATA_HOME"] = str(base / "xdg")
os.environ.pop("CHANCEBLOG_DESKTOP_DATA", None)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path[:0] = [str(root / "src"), str(root / "tests"), str(root)]
os.chdir(root / "tests")

from chanceblog_desktop.security import errorlog  # noqa: E402

calls = []
real_arm = errorlog.arm


def spy(resolve_folder, **options):
    log = real_arm(resolve_folder, **options)
    calls.append(log)
    return log


errorlog.arm = spy
suite = unittest.TestSuite()
for module in modules:
    suite.addTests(unittest.defaultTestLoader.loadTestsFromName(module))
result = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w", encoding="utf-8")).run(suite)
folders = []
for log in calls:
    try:
        folders.append(str(log._folder))
    except Exception:
        folders.append("?")
created = sorted(str(path.relative_to(base)) for path in base.rglob("logs"))
print(f"modules={modules} ran={result.testsRun} failures={len(result.failures)} errors={len(result.errors)} skipped={len(result.skipped)}")
print(f"arm calls={len(calls)} folder_resolved_by_any={[f for f in folders if f != 'None']} logs_dirs_created_under_temp_default={created}")
print(f"armed_at_end={errorlog.active() is not None}")
tmp.cleanup()
