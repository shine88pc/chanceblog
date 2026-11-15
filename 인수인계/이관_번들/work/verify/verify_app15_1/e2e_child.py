"""AP14 직접 짠 끝에서 끝까지 시험의 자식 프로세스 — 진짜 launcher.main(--data-dir 임시 폴더)을 offscreen Qt 로 돌린다.
사용: <python 또는 pythonw> -X utf8 e2e_child.py <tree> <데이터 폴더> <결과 json>
- 화면을 켠 지 300ms 때 logs 폴더가 없어야 한다(켜기만으로는 만들지 않음)
- 500ms 슬롯(타이머 콜백) 오류, 700ms 작업 스레드 오류, 900ms Qt 치명적 메시지, 1500ms 에 기록 파일을 읽어 결과를 쓰고 종료
"""
import json
import os
import sys
import threading

tree, data, result = sys.argv[1], sys.argv[2], sys.argv[3]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["LOCALAPPDATA"] = data + "_localappdata"             # 기본 데이터 폴더가 진짜 프로필로 가지 않게
sys.path.insert(0, os.path.join(tree, "src"))

facts = {"stderr_is_none": sys.stderr is None, "stdout_is_none": sys.stdout is None}
GKEY = "AI" + "za" + "Sy" + "CANARY" + "x" * 27


def save():
    with open(result, "w", encoding="utf-8") as handle:
        json.dump(facts, handle, ensure_ascii=False, indent=1)


try:
    from PySide6.QtCore import QTimer, qCritical
    from PySide6.QtWidgets import QApplication
    app = QApplication(["e2e"])

    def listing(path):
        return sorted(os.listdir(path)) if os.path.isdir(path) else None

    def before():
        facts["at300_logs_exists"] = os.path.exists(os.path.join(data, "logs"))
        facts["at300_data_listing"] = listing(data)

    def slot_error():
        raise RuntimeError("CANARY_SLOT_MSG " + GKEY + " C:/Users/CANARY_u/Secret Folder/x.txt")

    def thread_error():
        def run():
            raise ValueError("CANARY_THREAD_MSG " + GKEY)
        worker = threading.Thread(target=run, name="e2e-worker")
        worker.start()
        worker.join()

    def qt_critical():
        qCritical("CANARY_QT_CRITICAL " + GKEY + " C:/Users/CANARY_u/q.txt")

    def finish():
        logs = os.path.join(data, "logs")
        facts["end_logs_listing"] = listing(logs)
        facts["end_data_listing"] = listing(data)
        path = os.path.join(logs, "errors.log")
        facts["lines"] = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else None
        from chanceblog_desktop.security import errorlog
        facts["errorlog_active_before_quit"] = errorlog.active() is not None
        save()
        app.quit()

    QTimer.singleShot(300, before)
    QTimer.singleShot(500, slot_error)
    QTimer.singleShot(700, thread_error)
    QTimer.singleShot(900, qt_critical)
    QTimer.singleShot(1500, finish)

    from chanceblog_desktop.ui import launcher
    facts["exit_code"] = launcher.main(["--data-dir", data])
except BaseException as error:  # noqa: BLE001
    facts["child_exception"] = type(error).__name__
    import traceback
    facts["child_trace_tail"] = traceback.format_exc()[-1500:]
save()
