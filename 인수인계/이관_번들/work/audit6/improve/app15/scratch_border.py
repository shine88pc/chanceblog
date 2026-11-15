"""AP15 시험 보강 연습 — 입력 칸 테두리를 진짜로 그려 한 점의 색을 읽을 수 있는지, 라벨의 진짜 글자 색을 팔레트에서 읽을 수 있는지 본다."""
import os
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests"), str(ROOT / "scripts")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import ui_offscreen  # noqa: E402

ui_offscreen.prepare_environment()
from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit  # noqa: E402

from chanceblog_desktop.ui.qt import app as qapp  # noqa: E402
from chanceblog_desktop.ui.qt import components as UI  # noqa: E402

ui_offscreen.install_system_fonts()
app = qapp.make_app()
edit = QLineEdit()
edit.resize(240, 40)
edit.ensurePolished()
image = edit.grab().toImage()
print("size", image.width(), image.height())
for x, y in ((0, 20), (1, 20), (2, 20), (120, 0), (120, 1), (120, 39), (239, 20)):
    color = image.pixelColor(x, y)
    print((x, y), color.name().upper(), color.alpha())
plain = QPlainTextEdit()
plain.setProperty("editor", "true")
plain.resize(240, 90)
plain.style().unpolish(plain)
plain.style().polish(plain)
plain.ensurePolished()
image2 = plain.grab().toImage()
for x, y in ((0, 45), (1, 45), (120, 0)):
    color = image2.pixelColor(x, y)
    print("plain", (x, y), color.name().upper(), color.alpha())
for role in ("sub", "muted", "body", "small"):
    label = UI.label("글", role)
    label.ensurePolished()
    print(role, label.palette().color(QPalette.WindowText).name().upper())
