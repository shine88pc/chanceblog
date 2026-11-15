import sys
sys.argv = [sys.argv[0]]
exec(open(r"C:\work\ai\verify_app15_2\proto_run.py", encoding="utf-8").read().split("SCENARIOS = []")[0])
import shiboken6
def probe(variant, width):
    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda k, v, t: errors.append(f"{k.__name__}: {v}")
    shell_module.AppShell.PROTO_VARIANT = variant
    ids = candidate_ids()
    window = shell_module.AppShell(AlignedHome(ids, True), autoload=False, clipboard=lambda t: True, candidates=cd.FakeCandidatesProvider())
    window.resize(width, 900); window.show(); window.reload()
    ui_offscreen.wait_until(app, lambda: window.state.list_state != "loading", 10)
    ui_offscreen.settle(app, 6); window.activateWindow(); ui_offscreen.wait_until(app, window.isActiveWindow, 2)
    window.open_drawer(first_row_id(window)); ui_offscreen.settle(app, 6)
    print("home drawer open: _drawer_return valid =", shiboken6.isValid(window._drawer_return) if window._drawer_return is not None else None)
    button = [b for b in window.drawer.findChildren(QAbstractButton) if str(b.property("focus_key")).startswith("drawer-draft:")][0]
    QTest.mouseClick(button, Qt.LeftButton); ui_offscreen.settle(app, 4)
    ui_offscreen.wait_until(app, lambda: window.state.page == "topics" and window.state.candidates.state == "normal", 10); ui_offscreen.settle(app, 8)
    ref = window._drawer_return
    print(f"{variant} width={width}: after arriving on topics: _drawer_return is None={ref is None}; valid={shiboken6.isValid(ref) if ref is not None else None}; focus widget valid={QApplication.focusWidget() is not None}")
    # simulate the failing branch directly: restore focus finds nothing and focus is None
    try:
        if ref is not None and not shiboken6.isValid(ref):
            ref.setFocus(Qt.OtherFocusReason)
    except Exception as e:
        print("  direct setFocus on the stale reference raises:", type(e).__name__, str(e)[:80])
    window.close(); window.deleteLater(); ui_offscreen.settle(app, 3)
    sys.excepthook = old_hook
    print("  slot errors:", errors)
probe("v3", 1100)
probe("v3", 1920)
