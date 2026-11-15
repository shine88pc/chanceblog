import sys
sys.argv = [sys.argv[0]]
exec(open(r"C:\work\ai\verify_app15_2\proto_run.py", encoding="utf-8").read().split("SCENARIOS = []")[0])
import shiboken6
from chanceblog_desktop.ui.qt import board as board_module

def probe(variant, width, hide):
    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda k, v, t: errors.append(f"{k.__name__}: {v}")
    shell_module.AppShell.PROTO_VARIANT = variant
    ids = candidate_ids()
    window = shell_module.AppShell(AlignedHome(ids, True), autoload=False, clipboard=lambda t: True, candidates=cd.FakeCandidatesProvider())
    window.resize(width, 900); window.show(); window.reload()
    ui_offscreen.wait_until(app, lambda: window.state.list_state != "loading", 10)
    ui_offscreen.settle(app, 6); window.activateWindow(); ui_offscreen.wait_until(app, window.isActiveWindow, 2)
    if hide:
        window.go("topics")
        ui_offscreen.wait_until(app, lambda: window.state.candidates.state == "normal", 10); ui_offscreen.settle(app, 6)
        window.state.candidates.set_query("zzzzqq")
        window.go("home"); ui_offscreen.settle(app, 6)
    row = window.screen_widget.findChildren(board_module.BoardRow)[0]
    row.setFocus(Qt.TabFocusReason); ui_offscreen.settle(app, 2)           # keyboard/mouse path: focus is on the row when the drawer opens
    window.open_drawer(row.row["id"]); ui_offscreen.settle(app, 6)
    held = window._drawer_return
    print(f"[{variant} w={width} hide={hide}] home drawer open: focus holder is a BoardRow = {isinstance(held, board_module.BoardRow)}")
    button = [b for b in window.drawer.findChildren(QAbstractButton) if str(b.property("focus_key")).startswith("drawer-draft:")][0]
    QTest.mouseClick(button, Qt.LeftButton); ui_offscreen.settle(app, 4)
    ui_offscreen.wait_until(app, lambda: window.state.page == "topics" and window.state.candidates.state == "normal", 10); ui_offscreen.settle(app, 10)
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); ui_offscreen.settle(app, 3)      # flush deferred deletes like the real event loop does
    ref = window._drawer_return
    print(f"   on topics: _drawer_return kept={ref is not None}, widget still alive={shiboken6.isValid(ref) if ref is not None else None}, selected={window.state.candidates.selected is not None}, drawer_open={window.drawer.is_open}")
    try:
        window.escape(); ui_offscreen.settle(app, 6)
        print("   Esc handled; focus widget present:", QApplication.focusWidget() is not None)
    except Exception as e:
        print("   Esc raised:", type(e).__name__, str(e)[:100])
    window.close(); window.deleteLater(); ui_offscreen.settle(app, 3)
    sys.excepthook = old_hook
    print("   slot errors:", errors)

for width in (1100, 1920):
    for hide in (False, True):
        probe("v3", width, hide)
