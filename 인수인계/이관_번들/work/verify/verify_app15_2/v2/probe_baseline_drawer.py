"""Baseline probe on the UNMODIFIED new head (final2): can a user reach go() while the home drawer is open, and does the stale focus-return reference then raise?
Run with the PySide6 interpreter, QT_QPA_PLATFORM=offscreen. Throw-away verification tool."""
import sys

ROOT = r"C:\work\ai\verify_app15_2\final2"
sys.path[:0] = [ROOT + r"\src", ROOT + r"\scripts", ROOT + r"\tests"]
sys.dont_write_bytecode = True
import ui_offscreen  # noqa: E402

ui_offscreen.prepare_environment()
import shiboken6  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from chanceblog_desktop.ui.core import candidates as cd  # noqa: E402
from chanceblog_desktop.ui.core import services  # noqa: E402
from chanceblog_desktop.ui.qt import app as qapp  # noqa: E402
from chanceblog_desktop.ui.qt import board as board_module  # noqa: E402
from chanceblog_desktop.ui.qt import shell as shell_module  # noqa: E402

fonts = ui_offscreen.install_system_fonts()
app = qapp.make_app()


def make(width):
    window = shell_module.AppShell(services.FakeHomeProvider(), autoload=False, clipboard=lambda t: True, candidates=cd.FakeCandidatesProvider())
    window.resize(width, 900)
    window.show()
    window.reload()
    ui_offscreen.wait_until(app, lambda: window.state.list_state != "loading", 10)
    ui_offscreen.settle(app, 6)
    window.activateWindow()
    ui_offscreen.wait_until(app, window.isActiveWindow, 2)
    return window


def open_home_drawer(window):
    row = window.screen_widget.findChildren(board_module.BoardRow)[0]
    row.setFocus(Qt.TabFocusReason)
    ui_offscreen.settle(app, 2)
    window.open_drawer(row.row["id"])
    ui_offscreen.settle(app, 6)
    return row


for width in (1100, 1920):
    print(f"=== width {width} ===")
    window = make(width)
    open_home_drawer(window)
    print("home drawer open:", window.drawer.is_open, "page:", window.state.page)
    button = window.nav_buttons["topics"]
    center = button.rect().center()
    print("nav button enabled/visible:", button.isEnabled(), button.isVisible(), "focus policy NoFocus:", button.focusPolicy() == Qt.NoFocus)
    # where does a real mouse click on the sidebar button go while the drawer is open?
    target = window.childAt(button.mapTo(window, center))
    print("widget under the click point is the button itself:", target is button, "| it is:", type(target).__name__ if target is not None else None)
    QTest.mouseClick(button, Qt.LeftButton, Qt.NoModifier, center)
    ui_offscreen.settle(app, 6)
    print("after mouse click on the sidebar menu: page =", window.state.page, "| drawer still open:", window.drawer.is_open)
    window.close()
    window.deleteLater()
    ui_offscreen.settle(app, 3)
