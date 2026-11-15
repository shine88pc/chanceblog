"""Runtime check (offscreen Qt): effective foreground color of the seven sentence labels and the five kept value labels.
usage: python render_colors.py <copy root>      (run with the PySide6 interpreter, QT_QPA_PLATFORM=offscreen)
Reads the palette of each polished label (what the user would actually see), not the stylesheet text.
"""
import sys

ROOT = sys.argv[1]
sys.path[:0] = [ROOT + r"\src", ROOT + r"\scripts"]
import ui_offscreen  # noqa: E402

ui_offscreen.prepare_environment()
from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QLabel  # noqa: E402
from chanceblog_desktop.ui.core import candidates as cd  # noqa: E402
from chanceblog_desktop.ui.core import candidates_view as cv  # noqa: E402
from chanceblog_desktop.ui.core import jobs  # noqa: E402
from chanceblog_desktop.ui.core.text import T  # noqa: E402
from chanceblog_desktop.ui.qt import app as qapp  # noqa: E402
from chanceblog_desktop.ui.qt import candidate_parts, candidate_screen, draft_screen  # noqa: E402
from chanceblog_desktop.ui.qt import components as UI  # noqa: E402

fonts = ui_offscreen.install_system_fonts()
app = qapp.make_app()
print("application stylesheet applied:", bool(app.styleSheet()))


class Shell:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def text_of(label):
    return label.plain_text() if isinstance(label, (UI.Label, candidate_parts.ClampedLabel)) else label.text()


def colors(widget):
    found = {}
    for label in widget.findChildren(QLabel):
        label.ensurePolished()
        found[text_of(label)] = (label.property("role"), label.palette().color(QPalette.WindowText).name().upper())
    return found


def controller():
    provider = cd.FakeCandidatesProvider()
    ctl = cv.CandidatesController(provider, jobs.JobRunner())
    ctl.apply_loaded(provider.load_candidates(lambda *a, **k: None, lambda: False))
    return ctl


def detail(part):
    ctl = controller()
    cid = [row.candidate.candidate_id for row in ctl.rows() if part in row.candidate.topic][0]
    ctl.select(cid)
    return candidate_screen.detail_content(Shell(), ctl.detail_view())[0]


report = []
no_score = colors(detail("점수 계산 전인 예"))
no_safety = colors(detail("자주 묻는 것 모음"))
for key in ("cand_factor_none", "cand_reason_none"):
    report.append((key, no_score.get(T[key])))
report.append(("cand_safety_none", no_safety.get(T["cand_safety_none"])))
report.append(("cand_factor_missing(value cell, kept muted)", no_score.get(T["cand_factor_missing"])))
ctl = controller()
cards = {vm["title"]: vm for vm in ctl.view()["grid"]["cards"]}
card = candidate_parts.CandidateCard(cards["예시 후보 아 — 점수 계산 전인 예"])
report.append(("cand_summary_none (card)", colors(card).get(T["cand_summary_none"])))
report.append(("drf_category_none", colors(draft_screen._text_card("추천 카테고리", T["drf_category_none"], True)).get(T["drf_category_none"])))
saved = {"count_text": "0", "title": T["drf_saved_title"], "a11y": "x", "sub": "x", "notice": None, "state": "ok", "rows": [], "empty": T["drf_saved_empty"], "unreadable_note": "", "loading": "", "loading_a11y": "", "error": {}}
report.append(("drf_saved_empty", colors(draft_screen._saved_card(Shell(), saved, draft_screen.DraftsUi())).get(T["drf_saved_empty"])))
vm = {"title": T["drf_side_checks"], "status": "x", "open_text": "펼치기", "closed_text": "접기",
      "specific": {"key": "specific", "title": T["drf_chk_specific"], "lines": [], "open": True, "empty": T["drf_chk_specific_none"], "chip": "0", "tone": "muted"},
      "common": {"key": "common", "title": T["drf_chk_common"], "lines": ["x"], "open": False, "chip": "1", "tone": "muted"}}
report.append(("drf_chk_specific_none", colors(draft_screen._checks_card(Shell(), vm, draft_screen.DraftsUi())).get(T["drf_chk_specific_none"])))
for name, value in report:
    print(f"{name:48s} role/color = {value}")
