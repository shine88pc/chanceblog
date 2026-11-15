"""AP14 진짜 앱 한 번 — 창을 띄우지 않고(offscreen) 진짜 화면 진입점(`ui.launcher.main`)으로 앱을 열어 ① 켜기만 해서는 데이터 폴더에 `logs/` 가 안 생기고
② 슬롯에서 처리하지 못한 오류가 나면 `logs/errors.log` 에 오류 이름과 코드 위치만 처음 남는지(메시지 글·가짜 경로·가짜 비밀 한 글자 없음) 확인한다.
사용: QT_QPA_PLATFORM=offscreen python -X utf8 e2e_errorlog.py <작업 폴더 또는 사본>   (임시 데이터 폴더만 쓰고 끝나면 지운다)"""
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1])
sys.path[:0] = [str(root / "src"), str(root / "tests"), str(root / "scripts")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import ui_offscreen  # noqa: E402

ui_offscreen.prepare_environment()
from PySide6.QtCore import QTimer  # noqa: E402

from chanceblog_desktop.security import boundary, errorlog  # noqa: E402
from chanceblog_desktop.ui import launcher  # noqa: E402
from chanceblog_desktop.ui.qt import app as qapp  # noqa: E402

KEY = "AI" + "za" + ("CANARY_E2E_" + hashlib.sha256(b"app15-e2e").hexdigest())[:35]
MESSAGE = "CANARY_E2E_MESSAGE 오늘의 비밀 글 본문 " + KEY + " C:\\Users\\CANARY_E2E_USER\\Secret Folder\\note.txt"
tmp = Path(tempfile.mkdtemp(prefix="app15-e2e-"))
data = tmp / "data"
seen = {}


def run(provider, argv=None):
    ui_offscreen.install_system_fonts()
    app = qapp.make_app(argv)
    window = qapp.AppShell(provider)
    sys.excepthook = qapp.make_excepthook(window)
    window.show()
    seen["armed"] = errorlog.active() is not None
    seen["logs_before_error"] = (data / "logs").exists()
    seen["entries_before_error"] = sorted(path.name for path in data.iterdir()) if data.exists() else None

    def boom():
        raise RuntimeError(MESSAGE)

    QTimer.singleShot(300, boom)
    QTimer.singleShot(900, app.quit)
    code = app.exec()
    seen["logs_after_error"] = (data / "logs").exists()
    return code


qapp.run = run
try:
    code = launcher.main(["--data-dir", str(data)])
    log = data / "logs" / "errors.log"
    print("종료 코드:", code)
    print("켜 있었나:", seen.get("armed"), "| 오류 전에 logs 가 있었나:", seen.get("logs_before_error"), "| 오류 전 데이터 폴더 항목:", seen.get("entries_before_error"))
    print("오류 뒤 logs 가 생겼나:", seen.get("logs_after_error"))
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    print("기록 파일 줄 수:", len(text.splitlines()))
    for line in text.splitlines():
        print("  줄:", line)
    print("가짜 글·비밀·경로가 파일에 있나:", any(piece in text for piece in ("CANARY", "Secret Folder", "note.txt", "Users", KEY, "비밀 글")))
    print("logs 안의 파일:", sorted(path.name for path in (data / "logs").iterdir()) if (data / "logs").exists() else None)
finally:
    installed = boundary.active()
    if installed is not None:
        installed.uninstall()
    from chanceblog_desktop.ui import single_instance
    single_instance.release_all()
    shutil.rmtree(tmp, ignore_errors=True)
