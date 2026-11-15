"""AP14 2차 — 문서가 말한 '기록이 닿지 않는 길' 중 시험 없이 확인할 수 있는 둘: ③ 네이티브 충돌(충돌 덤프를 켜지 않는다) ④ 데이터 폴더를 풀지 못하면 그 줄을 버린다.
사용: python -B -X utf8 probe_limits2.py <tree 폴더> <임시 작업 폴더>
"""
import datetime as dt
import faulthandler
import os
import sys

TREE, WORK = sys.argv[1], sys.argv[2]
assert WORK.replace("\\", "/").startswith("C:/work/ai/verify_app15_1/")
sys.path.insert(0, os.path.join(TREE, "src"))
from chanceblog_desktop.security import boundary, errorlog  # noqa: E402
from chanceblog_desktop.ui import launcher  # noqa: E402

FIXED = dt.datetime(2026, 11, 15, 7, 41, 5, tzinfo=dt.timezone.utc)

# ③ 충돌 덤프: 경계를 깔고 오류 기록을 켠 뒤에도 faulthandler 가 꺼져 있다(앱이 켜지 않는다)
installed = boundary.install_gui(qt=False)
boundary.arm_error_log(lambda: os.path.join(WORK, "limit3"))
print("③ 경계+오류 기록을 켠 뒤 faulthandler.is_enabled() =", faulthandler.is_enabled(), "(False 면 앱이 충돌 덤프를 켜지 않음)")
installed.uninstall()

# ④ 데이터 폴더를 풀지 못하는 경우 — 진짜 launcher 의 폴더 알려 주기 + git 저장소 안의 폴더(DATA_DIR_UNSAFE)
repo = os.path.join(WORK, "gitroot")
os.makedirs(os.path.join(repo, ".git"), exist_ok=True)
unsafe = os.path.join(repo, "data")
resolver = launcher._data_folder_of(unsafe)
try:
    resolver()
    print("④ 폴더 해석 결과: 풀림(예상과 다름)")
except Exception as error:
    print("④ 폴더 해석이 거절함:", type(error).__name__, "(AppError 코드 DATA_DIR_UNSAFE 면 설계대로)")
log = errorlog.ErrorLog(resolver, clock=lambda: FIXED)
try:
    raise ValueError("m")
except ValueError as error:
    ret = log.record("main", type(error), error, error.__traceback__)
print("④ 그 폴더로 기록기를 쓰면 record =", ret, "| git 저장소 안에 logs 가 생겼나:", os.path.exists(os.path.join(unsafe, "logs")), "| data 폴더가 생겼나:", os.path.exists(unsafe))

# ④-b 같은 해석 함수가 정상 폴더에서는 풀리고 첫 오류 때 처음 만든다
ok_dir = os.path.join(WORK, "okdata")
resolver2 = launcher._data_folder_of(ok_dir)
log2 = errorlog.ErrorLog(resolver2, clock=lambda: FIXED)
before = os.path.exists(ok_dir)
try:
    raise ValueError("m")
except ValueError as error:
    ret2 = log2.record("main", type(error), error, error.__traceback__)
print("④-b 정상 폴더: 첫 오류 전 폴더 있음=%r, record=%r, 뒤에 logs 있음=%r" % (before, ret2, os.path.isdir(os.path.join(ok_dir, "logs"))))
