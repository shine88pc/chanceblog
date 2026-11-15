"""Verifier's own new mutants for AP15 (test_ui_sentence_color). Each aims at a different weakness class.
Module list is only the new test unless noted, to measure the new test's own power."""
QT = "src/chanceblog_desktop/ui/qt/"
TOKENS = "src/chanceblog_desktop/ui/core/tokens.py"
MY = ["test_ui_sentence_color"]

MUTATIONS = {}


def add(mid, what, file, old, new, modules=MY, regex=False):
    MUTATIONS[mid] = {"what": what, "file": file, "old": old, "new": new, "modules": modules, "regex": regex}


add("NM1", "inverted branch order in _text_card: missing text becomes body, present text becomes sub (both words still present)", QT + "draft_screen.py",
    'UI.label(text, "sub" if missing else "body", wrap=True)', 'UI.label(text, "body" if missing else "sub", wrap=True)')
add("NM2", "card summary uses sub even when a real summary exists (summary no longer small)", QT + "candidate_parts.py",
    '"sub" if vm["summary_missing"] else "small"', '"sub"')
add("NM3", "value-cell overflow at another site: seed info row value becomes sub instead of muted", QT + "seed_screen.py",
    'UI.label(row["value"], "muted" if row["missing"] else "body_lg", wrap=True), value_stretch)', 'UI.label(row["value"], "sub" if row["missing"] else "body_lg", wrap=True), value_stretch)')
add("NM4", "NEW muted sentence added through a variable role (scanner blind spot probe)", QT + "candidate_screen.py",
    '    trend = vm["trend"]\n', '    _r = "muted"\n    layout.addWidget(UI.label("새 안내 문장이에요.", _r, wrap=True))\n    trend = vm["trend"]\n')
add("NM5", "appended QSS rule overrides QLabel[role=sub] color with the muted token (first-match blind spot)", QT + "theme.py",
    "QLabel[trend=\"none\"] {{ color: {c['text_muted']}; }}", "QLabel[trend=\"none\"] {{ color: {c['text_muted']}; }}\nQLabel[role=\"sub\"] {{ color: {c['text_muted']}; }}")
add("NM6", "appended QSS rule darkens the single-line input border (#767676) after the original rule (first-match blind spot)", QT + "theme.py",
    "QLabel[trend=\"none\"] {{ color: {c['text_muted']}; }}", "QLabel[trend=\"none\"] {{ color: {c['text_muted']}; }}\nQLineEdit {{ border: 1px solid #767676; }}")
add("NM7", "secondary text token shifted by one unit (#5F6B7A -> #5F6B7B)", TOKENS,
    '("Text/Secondary", "text_secondary", "#5F6B7A", "보조 설명"),', '("Text/Secondary", "text_secondary", "#5F6B7B", "보조 설명"),')
add("NM8", "muted ROLE maps to the secondary color (muted would silently become readable everywhere)", TOKENS,
    '"sub": "text_secondary", "muted": "text_muted",', '"sub": "text_secondary", "muted": "text_secondary",')
add("NM9", "one converted sentence switched to caption role (still secondary color, smaller size)", QT + "candidate_screen.py",
    'UI.label(reason["empty"], "sub", wrap=True)', 'UI.label(reason["empty"], "caption", wrap=True)')
add("NM10", "inline widget stylesheet pins sub labels to the muted hex (runtime color differs from QSS role rule)", QT + "components.py",
    '        self._role, self._wrap, self._text = role, wrap, ""\n        self.setProperty("role", role)\n',
    '        self._role, self._wrap, self._text = role, wrap, ""\n        self.setProperty("role", role)\n        if role == "sub":\n            self.setStyleSheet("color: #8491A3;")\n')
add("NM11", "input editor border (QPlainTextEdit) switched to a text token inside the original rule", QT + "theme.py",
    "QPlainTextEdit[editor=\"true\"] {{ background: {c['surface']}; border: 1px solid {c['border_strong']};", "QPlainTextEdit[editor=\"true\"] {{ background: {c['surface']}; border: 1px solid {c['text_secondary']};")
add("NM12", "border_strong token value darkened (#B8C7DA -> #A0B0C4): the approved mockup color changes", TOKENS,
    '"border": "#DCE4F0", "border_strong": "#B8C7DA",', '"border": "#DCE4F0", "border_strong": "#A0B0C4",')
add("NM13", "REAL override: QLineEdit border darkened by a rule placed AFTER the original rule (later rule wins in QSS; tests that read the first match still see the original)", QT + "theme.py",
    "QPlainTextEdit[editor=\"true\"]:focus {{ border: 2px solid {c['border_focus']}; }}", "QPlainTextEdit[editor=\"true\"]:focus {{ border: 2px solid {c['border_focus']}; }}\nQLineEdit {{ border: 1px solid #767676; }}")
