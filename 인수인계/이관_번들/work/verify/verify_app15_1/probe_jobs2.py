"""AP14 2차 — 문서 한계 ② 의 나머지 반쪽: 화면 콜백 안의 예외(Job._emit)는 이름만 기억하고 삼키며 오류 기록에도 남지 않는다.
사용: python -B -X utf8 probe_jobs2.py <tree 폴더> <임시 작업 폴더>
"""
import os
import sys
import threading

tree, work = sys.argv[1], sys.argv[2]
assert work.replace("\\", "/").startswith("C:/work/ai/verify_app15_1/")
sys.path.insert(0, os.path.join(tree, "src"))
from chanceblog_desktop.security import boundary  # noqa: E402
from chanceblog_desktop.ui.core import jobs  # noqa: E402

root = os.path.join(work, "jobs2_data")
installed = boundary.install_gui(qt=False)
boundary.arm_error_log(lambda: root)
finished = threading.Event()


def work_ok(progress, cancelled):
    return "결과"


def on_done(result, payload):
    finished.set()
    raise ValueError("CANARY_CALLBACK_MESSAGE 화면 콜백의 실수")


runner = jobs.JobRunner()
job = runner.start("cb", work_ok, on_done=on_done)
finished.wait(10)
job.join(10)
print("콜백이 예외를 낸 뒤 작업 상태:", job.state, "| callback_error(이름만 기억):", job.callback_error)
print("그때 logs 폴더가 생겼나:", os.path.exists(os.path.join(root, "logs")), "| 데이터 폴더가 생겼나:", os.path.exists(root))
installed.uninstall()
