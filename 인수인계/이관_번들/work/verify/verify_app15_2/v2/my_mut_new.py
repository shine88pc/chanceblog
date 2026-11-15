"""Verifier's NEW mutants (round 2) against the strengthened tests/test_ui_sentence_color.py at head 4692990.
Each one targets a different gap class. 'FP' ids are false-positive probes: harmless/legit changes (RED there = the test is brittle or over-broad; GREEN = it lets normal work through)."""
QT = "src/chanceblog_desktop/ui/qt/"
TOKENS = "src/chanceblog_desktop/ui/core/tokens.py"
MY = ["test_ui_sentence_color"]

MUTATIONS = {}


def add(mid, what, file=None, old=None, new=None, modules=MY, edits=None):
    spec = {"what": what, "modules": modules}
    if edits:
        spec["edits"] = edits
    else:
        spec.update({"file": file, "old": old, "new": new})
    MUTATIONS[mid] = spec


TREND = "QLabel[trend=\"none\"] {{ color: {c['text_muted']}; }}"
EDITOR_FOCUS = "QPlainTextEdit[editor=\"true\"]:focus {{ border: 2px solid {c['border_focus']}; }}"
ANCHOR_TREND_VAR = '    trend = vm["trend"]\n'
LABEL_INIT = '        self._role, self._wrap, self._text = role, wrap, ""\n        self.setProperty("role", role)\n'

# ---- role passing / census gaps
add("N01", "Label.__init__ sets the role property through an inline dict whose VALUE is 'muted' (dict values are not counted by the census; not a label-constructor call)", QT + "components.py",
    LABEL_INIT, '        self._role, self._wrap, self._text = role, wrap, ""\n        self.setProperty("role", {"sub": "muted"}.get(role, role))\n')
add("N22", "pass-through function components.label rewrites its role first through a dict-VALUE alias, then returns Label(text, role, ...) (call expression stays `role`)", QT + "components.py",
    'def label(text, role="body", wrap=False, mono=False):\n    return Label(text, role, wrap, mono)\n',
    'def label(text, role="body", wrap=False, mono=False):\n    role = {"sub": "muted"}.get(role, role)\n    return Label(text, role, wrap, mono)\n')
add("N21", "pass-through function components.label passes a different role EXPRESSION to Label (inline alias at the call)", QT + "components.py",
    'def label(text, role="body", wrap=False, mono=False):\n    return Label(text, role, wrap, mono)\n', 'def label(text, role="body", wrap=False, mono=False):\n    return Label(text, {"sub": "muted"}.get(role, role), wrap, mono)\n')
add("N18", "a NEW muted sentence label created with **{'role': 'muted'} keyword unpacking (invisible to role_sites; the muted string sits in a dict)", QT + "candidate_screen.py",
    ANCHOR_TREND_VAR, '    layout.addWidget(UI.label("새 안내 문장이에요.", **{"role": "muted"}, wrap=True))\n' + ANCHOR_TREND_VAR)
add("N08", "NEW role alias `hint` -> text_muted in ROLE_TEXT plus a NEW sentence label with role 'hint' (no 'muted' string anywhere in the screens)", edits=[
    {"file": TOKENS, "old": '"sub": "text_secondary", "muted": "text_muted",', "new": '"sub": "text_secondary", "muted": "text_muted", "hint": "text_muted",'},
    {"file": QT + "candidate_screen.py", "old": ANCHOR_TREND_VAR, "new": '    layout.addWidget(UI.label("새 안내 문장이에요.", "hint", wrap=True))\n' + ANCHOR_TREND_VAR}])

# ---- stylesheet override gaps (sentence color)
add("N02", "hand-written QWidget[role=\"sub\"] rule appended after the generated role rules, sub text turns muted (selector not matched by the QLabel[role=...] census)", QT + "theme.py",
    TREND, TREND + "\nQWidget[role=\"sub\"] {{ color: {c['text_muted']}; }}")
add("N03", "hand-written QLabel[role=sub] (unquoted value) rule appended after the generated rules, sub text turns muted", QT + "theme.py",
    TREND, TREND + "\nQLabel[role=sub] {{ color: {c['text_muted']}; }}")
add("N25", "tokens.role_color returns the muted color for role sub (table ROLE_TEXT stays correct, only the function that builds the stylesheet is wrong)", TOKENS,
    "def role_color(colors, role):\n    return colors[ROLE_TEXT[role]]\n", "def role_color(colors, role):\n    return colors[\"text_muted\" if role == \"sub\" else ROLE_TEXT[role]]\n")

# ---- stylesheet override gaps (input box border)
add("N04", "descendant selector `QWidget QLineEdit` placed after the input rules darkens the border with a non-text token (line does not start with QLineEdit)", QT + "theme.py",
    EDITOR_FOCUS, EDITOR_FOCUS + "\nQWidget QLineEdit {{ border: 1px solid {c['primary_700']}; }}")
add("N05", "border-color with a non-text token appended INSIDE the original QLineEdit rule line (the `border: 1px solid border_strong` text is still there)", QT + "theme.py",
    "QLineEdit {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-radius: {r['input']}px;",
    "QLineEdit {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-color: {c['primary_700']}; border-radius: {r['input']}px;")
add("N06", "multi-selector rule `QPushButton, QLineEdit` appended after the input rules (line starts with QPushButton) darkens the input border", QT + "theme.py",
    EDITOR_FOCUS, EDITOR_FOCUS + "\nQPushButton, QLineEdit {{ border: 1px solid {c['primary_700']}; }}")

# ---- widget level colour routes (actual colour)
add("N07", "Label.__init__ writes the stylesheet through setProperty('styleSheet', ...) for sub labels with a token color (the AST test looks only for setStyleSheet attribute calls)", QT + "components.py",
    LABEL_INIT, LABEL_INIT + '        if role == "sub":\n            self.setProperty("styleSheet", "color: " + theme.colors()["text_muted"] + ";")\n')
add("N09", "rich-text HTML inside Label.set_text carries color:muted for sub labels (palette stays secondary, painted text becomes muted)", QT + "components.py",
    "            self.setText(f'<div style=\"line-height:{percent}%\">{body}</div>')",
    "            self.setText(f'<div style=\"line-height:{percent}%; color:{theme.colors()[\"text_muted\"] if self._role == \"sub\" else \"inherit\"}\">{body}</div>')")
add("N10", "ClampedLabel (card summary) paints with QPalette.Mid instead of WindowText (palette/property/stylesheet stay correct)", QT + "candidate_parts.py",
    "        painter.setPen(self.palette().color(QPalette.WindowText))\n        width, pitch = self.width(), self._pitch()\n",
    "        painter.setPen(self.palette().color(QPalette.Mid))\n        width, pitch = self.width(), self._pitch()\n")
add("N11", "muted BADGE text color switched to the muted token (text_muted used elsewhere in the stylesheet; outside the seven sentences)", QT + "theme.py",
    "QLabel[badge=\"muted\"] {{ background: {c['surface_2']}; color: {c['text_secondary']}; border: 1px solid {c['border']}; }}",
    "QLabel[badge=\"muted\"] {{ background: {c['surface_2']}; color: {c['text_muted']}; border: 1px solid {c['border']}; }}")

# ---- direct pins (should be RED everywhere)
add("N13", "ROLE_TEXT sub -> text_primary (darker than approved)", TOKENS, '"sub": "text_secondary", "muted": "text_muted",', '"sub": "text_primary", "muted": "text_muted",')
add("N14", "one of the seven sentences (score factors empty) switched to body", QT + "candidate_screen.py", 'UI.label(factors["empty"], "sub", wrap=True)', 'UI.label(factors["empty"], "body", wrap=True)')
add("N15", "one of the seven sentences (saved list empty) switched to small", QT + "draft_screen.py", 'UI.label(saved["empty"], "sub", wrap=True)', 'UI.label(saved["empty"], "small", wrap=True)')
add("N16", "text_muted token value shifted by one unit", TOKENS, '("Text/Muted", "text_muted", "#8491A3",', '("Text/Muted", "text_muted", "#8491A4",')
add("N17", "border_strong token value shifted by one unit", TOKENS, '"border": "#DCE4F0", "border_strong": "#B8C7DA",', '"border": "#DCE4F0", "border_strong": "#B8C7DB",')
add("N19", "ROLE_STYLE sub -> small (layout would move)", TOKENS, 'ROLE_STYLE = {"sub": "body", "muted": "body"}', 'ROLE_STYLE = {"sub": "small", "muted": "body"}')

# ---- false-positive probes (harmless / legitimate changes)
add("FP1", "FP: a harmless hand-written QLabel[role=\"note\"] rule for an unrelated role", QT + "theme.py", TREND, TREND + "\nQLabel[role=\"note\"] {{ color: {c['text_primary']}; }}")
add("FP2", "FP: a harmless extra input selector rule QLineEdit[search=\"true\"] (padding only)", QT + "theme.py", EDITOR_FOCUS, EDITOR_FOCUS + "\nQLineEdit[search=\"true\"] {{ padding: 0 8px; }}")
add("FP3", "FP: a second app.setStyleSheet call in theme.py (identical value)", QT + "theme.py", "    app.setStyleSheet(build_qss(colors()))", "    app.setStyleSheet(build_qss(colors()))\n    app.setStyleSheet(app.styleSheet())")
add("FP4", "FP: an ordinary new label with a literal h3 role in a detail screen", QT + "candidate_screen.py", ANCHOR_TREND_VAR, '    layout.addWidget(UI.label("제목 한 줄", "h3"))\n' + ANCHOR_TREND_VAR)
add("FP5", "FP: harmless refactor of a pinned call through a local variable (same role)", QT + "candidate_screen.py",
    'inner.addWidget(UI.label(reason["empty"], "sub", wrap=True))', 'reason_text = reason["empty"]\n        inner.addWidget(UI.label(reason_text, "sub", wrap=True))')
add("FP6", "FP: harmless style change of a pinned call (role= keyword instead of positional)", QT + "candidate_screen.py",
    'UI.label(reason["empty"], "sub", wrap=True)', 'UI.label(reason["empty"], role="sub", wrap=True)')
add("FP7", "FP: a legit second pass-through helper in a screen file that forwards a role variable", QT + "candidate_screen.py",
    ANCHOR_TREND_VAR, '    layout.addWidget((lambda text, role: UI.label(text, role, wrap=True))("보조 안내", "caption"))\n' + ANCHOR_TREND_VAR)

# ---- extra direct probes (appended after the first pass)
add("N20", "an input selector rule deleted (QLineEdit:disabled) - the pinned selector list shrinks", QT + "theme.py",
    "QLineEdit:disabled {{ background: {c['disabled_bg']}; color: {c['text_disabled']}; }}\n", "")
add("N23", "a widget-level setStyleSheet('') call added in a screen component (outside theme.py)", QT + "components.py",
    LABEL_INIT, LABEL_INIT + '        self.setStyleSheet("")\n')
add("N24", "a pinned sentence site passes its (correct, 'sub') role through a local variable", QT + "candidate_screen.py",
    'inner.addWidget(UI.label(reason["empty"], "sub", wrap=True))', '_r = "sub"\n        inner.addWidget(UI.label(reason["empty"], _r, wrap=True))')
add("FP8", "FP: an unrelated typography change in a pinned value call (normal value text body_lg -> body; the missing branch stays muted)", QT + "candidate_screen.py",
    'UI.label(row["value"], "muted" if row["missing"] else "body_lg", wrap=True), 5)', 'UI.label(row["value"], "muted" if row["missing"] else "body", wrap=True), 5)')
add("N27", "a NEW muted sentence created through a local alias of the label factory (`_lbl = UI.label`) with the role hidden in a dict value", QT + "candidate_screen.py",
    ANCHOR_TREND_VAR, '    _lbl = UI.label\n    layout.addWidget(_lbl("새 안내 문장이에요.", {"r": "muted"}["r"], wrap=True))\n' + ANCHOR_TREND_VAR)
add("N28", "NEW role alias `hint` (ROLE_TEXT -> text_muted and ROLE_STYLE -> body, so the stylesheet still builds) plus a NEW sentence label with role 'hint'", edits=[
    {"file": TOKENS, "old": '"sub": "text_secondary", "muted": "text_muted",', "new": '"sub": "text_secondary", "muted": "text_muted", "hint": "text_muted",'},
    {"file": TOKENS, "old": 'ROLE_STYLE = {"sub": "body", "muted": "body"}', "new": 'ROLE_STYLE = {"sub": "body", "muted": "body", "hint": "body"}'},
    {"file": QT + "candidate_screen.py", "old": ANCHOR_TREND_VAR, "new": '    layout.addWidget(UI.label("새 안내 문장이에요.", "hint", wrap=True))\n' + ANCHOR_TREND_VAR}])
