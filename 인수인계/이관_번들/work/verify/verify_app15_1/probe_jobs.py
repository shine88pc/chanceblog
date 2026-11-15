"""AP14 범위 확인 — 작업 스레드(ui/core/jobs.py)가 삼킨 예기치 못한 오류는 오류 기록 파일에 남는가?
사용: python -B -X utf8 probe_jobs.py <tree 폴더> <임시 작업 폴더>
"""
import os
import sys
import threading

tree, work = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(tree, "src"))
from chanceblog_desktop.security import boundary  # noqa: E402
from chanceblog_desktop.ui.core import jobs  # noqa: E402

root = os.path.join(work, "jobs_data")
installed = boundary.install_gui(qt=False)
boundary.arm_error_log(lambda: root)
seen = {}
done = threading.Event()


def boom(progress, cancelled):
    raise KeyError("CANARY_JOB_MESSAGE 가짜 글")


def on_error(failure, payload):
    seen["failure"] = {"code": failure.code, "user_message_given": bool(failure.user_message)}
    done.set()


runner = jobs.JobRunner()
runner.start("probe", boom, on_error=on_error)
finished = done.wait(10)
print("작업 실패가 화면으로 올라갔나:", finished, seen.get("failure"))
print("그때 logs 폴더가 생겼나:", os.path.exists(os.path.join(root, "logs")), "| 데이터 폴더가 생겼나:", os.path.exists(root))
installed.uninstall()
