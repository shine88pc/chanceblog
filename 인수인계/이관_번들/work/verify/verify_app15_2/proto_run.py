"""Run the AP13 prototype scenarios offscreen (3.12 + PySide6). Usage: python proto_run.py [scenario filter substring]
Prints one JSON line per scenario. Throw-away verification tool; works only on proto_copy.
"""
import dataclasses
import json
import sys

ROOT = r"C:\work\ai\verify_app15_2\proto_copy"
sys.path[:0] = [ROOT + r"\src", ROOT + r"\scripts", ROOT + r"\tests"]
import ui_offscreen  # noqa: E402

ui_offscreen.prepare_environment()
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QAbstractButton, QApplication  # noqa: E402
from chanceblog_desktop.ui.core import candidates as cd  # noqa: E402
from chanceblog_desktop.ui.core import services  # noqa: E402
from chanceblog_desktop.ui.qt import app as qapp  # noqa: E402
from chanceblog_desktop.ui.qt import shell as shell_module  # noqa: E402

fonts = ui_offscreen.install_system_fonts()
app = qapp.make_app()


def candidate_ids():
    provider = cd.FakeCandidatesProvider()
    data = provider.load_candidates(lambda *a, **k: None, lambda: False)
    return [row.candidate.candidate_id for row in data.rows]


class AlignedHome(services.FakeHomeProvider):
    """Home provider whose recommendation rows carry real candidate ids of the fake candidates provider (the default fake home uses rA1.. which match nothing)."""

    def __init__(self, ids, aligned=True):
        super().__init__()
        self.ids, self.aligned = ids, aligned

    def load_home(self, progress, cancelled):
        data = super().load_home(progress, cancelled)
        if not self.aligned:
            return data
        index = 0
        channels = []
        for channel in data.board.channels:
            rows = []
            for row in channel.rows:
                rows.append(dataclasses.replace(row, id=self.ids[index % len(self.ids)]))
                index += 1
            channels.append(dataclasses.replace(channel, rows=tuple(rows)))
        return dataclasses.replace(data, board=dataclasses.replace(data.board, channels=tuple(channels)))


def first_row_id(window):
    return [row["id"] for item in window.state.home_view()["board"]["recommend"] for row in item["rows"]][0]


def scenario(name, variant, width, revisit=False, aligned=True, hide=False):
    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda kind, value, trace: errors.append(f"{kind.__name__}: {value}")
    shell_module.AppShell.PROTO_VARIANT = variant
    ids = candidate_ids()
    provider = AlignedHome(ids, aligned)
    window = shell_module.AppShell(provider, autoload=False, clipboard=lambda text: True, candidates=cd.FakeCandidatesProvider())
    window.resize(width, 900)
    window.show()
    window.reload()
    ui_offscreen.wait_until(app, lambda: window.state.list_state != "loading", 10)
    ui_offscreen.settle(app, 6)
    window.activateWindow()
    ui_offscreen.wait_until(app, window.isActiveWindow, 2)
    if revisit:
        window.go("topics")
        ui_offscreen.wait_until(app, lambda: window.state.candidates.state == "normal", 10)
        ui_offscreen.settle(app, 6)
        if hide:
            window.state.candidates.set_query("zzzzqq")          # a filter that hides every card (the user filtered earlier in the session)
        window.go("home")
        ui_offscreen.settle(app, 6)
    row_id = first_row_id(window)
    window.open_drawer(row_id)
    ui_offscreen.settle(app, 6)
    buttons = [b for b in window.drawer.findChildren(QAbstractButton) if str(b.property("focus_key")).startswith("drawer-draft:")]
    result = {"scenario": name, "variant": variant, "width": width, "revisit": revisit, "aligned": aligned, "hidden_by_filter": hide, "row_id_is_candidate": row_id in ids, "draft_buttons": len(buttons)}
    if not buttons:
        result["note"] = "no draft button"
        result["errors"] = errors
        window.close()
        sys.excepthook = old_hook
        return result
    QTest.mouseClick(buttons[0], Qt.LeftButton)
    ui_offscreen.settle(app, 4)
    ui_offscreen.wait_until(app, lambda: window.state.page == "topics" and window.state.candidates.state == "normal", 10)
    ui_offscreen.settle(app, 8)
    cands = window.state.candidates
    detail = cands.detail_view()
    result.update({"page": window.state.page, "mode": cands.mode, "selected_is_target": cands.selected == row_id, "opened": cands.opened, "drawer_open": window.drawer.is_open,
                   "detail_pane_visible": window.detail_pane.isVisible(), "detail_has_view": detail is not None, "toast": window.toast.text() if window.toast.isVisible() else ""})
    errors_before_close = list(errors)
    try:
        window.escape()
        ui_offscreen.settle(app, 6)
    except Exception as error:  # noqa: BLE001
        errors.append(f"direct {type(error).__name__}: {error}")
    result["after_escape"] = {"selected": cands.selected, "drawer_open": window.drawer.is_open, "page": window.state.page}
    result["errors_before_close"] = errors_before_close
    result["errors"] = errors
    window.close()
    window.deleteLater()
    ui_offscreen.settle(app, 3)
    sys.excepthook = old_hook
    return result


SCENARIOS = []
for width, label in ((1920, "fixed"), (1100, "drawer")):
    for revisit in (False, True):
        for variant in ("v1", "v2", "v3", "v4"):
            SCENARIOS.append((f"{variant}-{label}-{'revisit' if revisit else 'first'}", variant, width, revisit, True))
SCENARIOS.append(("v3-drawer-revisit-hidden", "v3", 1100, True, True, True))
SCENARIOS.append(("v3-fixed-revisit-hidden", "v3", 1920, True, True, True))
SCENARIOS.append(("v2-drawer-first-unknown-id", "v2", 1100, False, False))
SCENARIOS.append(("v3-drawer-first-unknown-id", "v3", 1100, False, False))

if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else ""
    for item in SCENARIOS:
        name, variant, width, revisit, aligned = item[:5]
        hide = item[5] if len(item) > 5 else False
        if pattern and pattern not in name:
            continue
        print(json.dumps(scenario(name, variant, width, revisit, aligned, hide), ensure_ascii=False), flush=True)
