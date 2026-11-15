"""Effectiveness proofs for survivors (Qt, offscreen): does the mutated code REALLY change what a user sees?
usage: python probe_effect.py <tree root>      (the tree is final2 or a mutated copy; run with the PySide6 interpreter)
Prints: painted ink color of a sub sentence label (rich text, wrap=True), painted ink color of a card summary (ClampedLabel, sub),
border pixel of a PARENTED line edit (real layout) and of a PARENTLESS one (what the AP15 pixel test uses)."""
import sys

ROOT = sys.argv[1]
sys.path[:0] = [ROOT + r"\src", ROOT + r"\scripts", ROOT + r"\tests"]
sys.dont_write_bytecode = True
import ui_offscreen  # noqa: E402

ui_offscreen.prepare_environment()
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget  # noqa: E402
from chanceblog_desktop.ui.qt import app as qapp  # noqa: E402
from chanceblog_desktop.ui.qt import candidate_parts  # noqa: E402
from chanceblog_desktop.ui.qt import components as UI  # noqa: E402

fonts = ui_offscreen.install_system_fonts()
app = qapp.make_app()


def ink_color(widget, width=260, height=60):
    widget.resize(width, height)
    widget.show()
    ui_offscreen.settle(app, 4)
    image = widget.grab().toImage()
    best, best_lum = None, 10 ** 9
    for y in range(image.height()):
        for x in range(image.width()):
            c = QColor(image.pixel(x, y))
            lum = 0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()
            if lum < best_lum:
                best, best_lum = c.name().upper(), lum
    widget.hide()
    return best


sentence = UI.label("점수 구성 정보가 없어요.", "sub", wrap=True)
print("painted ink color of a sub sentence (rich text):", ink_color(sentence))
muted_sentence = UI.label("평가 전", "muted", wrap=True)
print("painted ink color of a muted value (reference)  :", ink_color(muted_sentence))
summary = candidate_parts.ClampedLabel("추천 이유가 아직 없어요", "sub", 2)
print("painted ink color of a sub card summary          :", ink_color(summary))

host = QWidget()
layout = QVBoxLayout(host)
child = QLineEdit()
layout.addWidget(child)
host.resize(300, 80)
host.show()
ui_offscreen.settle(app, 4)
child.style().unpolish(child)
child.style().polish(child)
ui_offscreen.settle(app, 2)
y = child.height() // 2
print("border pixel of a line edit inside a parent window:", child.grab().toImage().pixelColor(0, y).name().upper())
loose = QLineEdit()
loose.resize(240, 40)
loose.style().unpolish(loose)
loose.style().polish(loose)
loose.ensurePolished()
print("border pixel of a parentless line edit (the test's)  :", loose.grab().toImage().pixelColor(0, 20).name().upper())
