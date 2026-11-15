"""AP15 시험을 짜기 전에 후보 상세·초안 카드를 직접 만들어 보는 연습 — 작업 폴더를 고치지 않는다."""
import os
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests"), str(ROOT / "scripts")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import ui_offscreen  # noqa: E402

ui_offscreen.prepare_environment()
from PySide6.QtWidgets import QLabel  # noqa: E402

from chanceblog_desktop.ui.core import candidates as cd  # noqa: E402
from chanceblog_desktop.ui.core import candidates_view as cv  # noqa: E402
from chanceblog_desktop.ui.core import jobs  # noqa: E402
from chanceblog_desktop.ui.core.text import T  # noqa: E402
from chanceblog_desktop.ui.qt import app as qapp  # noqa: E402
from chanceblog_desktop.ui.qt import candidate_screen, draft_screen, theme  # noqa: E402
from chanceblog_desktop.ui.qt import components as UI  # noqa: E402

ui_offscreen.install_system_fonts()
app = qapp.make_app()
provider = cd.FakeCandidatesProvider()
controller = cv.CandidatesController(provider, jobs.JobRunner())
controller.apply_loaded(provider.load_candidates(lambda *a, **k: None, lambda: False))
print("rows", len(controller.rows()))
for row in controller.rows():
    print(row.candidate.candidate_id[:8], row.candidate.topic[:30])
none_id = next(row.candidate.candidate_id for row in controller.rows() if "아 —" in row.candidate.topic)
controller.select(none_id)
vm = controller.detail_view()
print("detail keys", sorted(vm)[:30])


class Shell:
    def __getattr__(self, name):
        return lambda *a, **k: None


widget = candidate_screen.detail_content(Shell(), vm)
print(type(widget))
body = widget[0] if isinstance(widget, tuple) else widget
for label in body.findChildren(QLabel):
    text = label.plain_text() if isinstance(label, UI.Label) else label.text()
    if text in (T["cand_factor_none"], T["cand_reason_none"], T["cand_safety_none"]):
        print("FOUND", repr(text), label.property("role"))
qss = theme.build_qss(theme.colors())
import re  # noqa: E402

for role in ("sub", "muted"):
    print(role, re.search(r'QLabel\[role="' + role + r'"\] \{[^}]*?color: (#[0-9A-Fa-f]{6})', qss).group(1))
print(re.search(r"\nQLineEdit \{[^}]*border: 1px solid (#[0-9A-Fa-f]{6})", qss).group(1))
