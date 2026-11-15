"""AP15(안내·결과 문장의 글 색) 변이 정의 — mut_run.py 가 읽는다. 각 항목: id → {item, what, file, old, new(글 치환), modules, py}."""

QT = "src/chanceblog_desktop/ui/qt/"
TOKENS = "src/chanceblog_desktop/ui/core/tokens.py"
MY = ["test_ui_sentence_color"]
MY_AND_CORE = ["test_ui_sentence_color", "test_ui_core"]

MUTATIONS = {}


def add(mid, what, file, old, new, modules=MY, py="qt", regex=False):
    MUTATIONS[mid] = {"item": "AP15", "what": what, "file": file, "old": old, "new": new, "modules": modules, "regex": regex, "py": py}


add("P01", "후보 상세의 `확인이 필요한 표시는 없어요` 문장이 다시 흐린 글(muted)로", QT + "candidate_screen.py", 'inner.addWidget(UI.label(safety["none"], "sub", wrap=True))', 'inner.addWidget(UI.label(safety["none"], "muted", wrap=True))')
add("P02", "초안 작성의 저장 목록 비었음 안내가 다시 muted 로", QT + "draft_screen.py", 'inner.addWidget(UI.label(saved["empty"], "sub", wrap=True))', 'inner.addWidget(UI.label(saved["empty"], "muted", wrap=True))')
add("P03", "후보 카드의 요약 없음 안내가 다시 muted 로", QT + "candidate_parts.py", '"sub" if vm["summary_missing"] else "small"', '"muted" if vm["summary_missing"] else "small"')
add("P04", "`sub` 역할의 색이 흐린 글 토큰으로(역할 표가 틀림)", TOKENS, '"small": "text_secondary", "caption": "text_secondary", "micro": "text_secondary", "sub": "text_secondary", "muted": "text_muted",',
    '"small": "text_secondary", "caption": "text_secondary", "micro": "text_secondary", "sub": "text_muted", "muted": "text_muted",', MY_AND_CORE)
add("P05", "입력 칸 테두리에 새 진한 색(#767676)을 더함 — 승인하지 않은 일", TOKENS, '"border": "#DCE4F0", "border_strong": "#B8C7DA",', '"border": "#DCE4F0", "border_strong": "#767676",')
add("P06", "빈 값 자리(`평가 전`)까지 문장 색으로 바꿈(승인 범위 밖으로 넘침)", QT + "candidate_parts.py", '"muted" if vm["missing"] else "h3"', '"sub" if vm["missing"] else "h3"')
add("P07", "스타일시트의 입력 칸(한 줄) 테두리가 보조 글 색으로", QT + "theme.py", "border: 1px solid {c['border_strong']}; border-radius: {r['input']}px; padding: 0 12px;", "border: 1px solid {c['text_secondary']}; border-radius: {r['input']}px; padding: 0 12px;")
add("P08", "보조 글 토큰이 옅어져 흰 바탕 대비 4.5 미만(#9AA5B5)", TOKENS, '("Text/Secondary", "text_secondary", "#5F6B7A", "보조 설명"),', '("Text/Secondary", "text_secondary", "#9AA5B5", "보조 설명"),', MY_AND_CORE)
add("P09", "`sub` 역할의 글자 모양이 `small` 로 바뀜(배치가 달라짐)", TOKENS, 'ROLE_STYLE = {"sub": "body", "muted": "body"}', 'ROLE_STYLE = {"sub": "small", "muted": "body"}', MY_AND_CORE)
add("P10", "후보 상세의 `점수 구성 정보가 없어요` 문장이 다시 muted 로", QT + "candidate_screen.py", 'inner.addWidget(UI.label(factors["empty"], "sub", wrap=True))', 'inner.addWidget(UI.label(factors["empty"], "muted", wrap=True))', py="dev")


# ---- 2차 지시(검증자 2 의 생존 변이 NM 과 새 규칙마다 둘 이상) ----------------------------------------------------------------------------------
# CI 는 PySide6 가 없어 Qt 없는 시험만 돈다 — Rec 1 의 NM1·NM2·NM4·NM5·NM13 은 `py="dev"`(3.12 Qt 없음)로 빨개져야 하고, 같은 변이를 Qt 있는 쪽(`...q`)도 돌린다.
THEME = QT + "theme.py"
add("NM1", "`_text_card` 분기 뒤집기 — 값이 없을 때 body, 있을 때 sub(낱말은 둘 다 그대로)", QT + "draft_screen.py", 'UI.label(text, "sub" if missing else "body", wrap=True)', 'UI.label(text, "body" if missing else "sub", wrap=True)', py="dev")
add("NM2", "후보 카드 요약이 요약이 있을 때도 sub(작은 글이 아니게 됨)", QT + "candidate_parts.py", '"sub" if vm["summary_missing"] else "small"', '"sub"', py="dev")
add("NM3", "빈 값 칸 하나(Seed 정보)가 sub 로 넘침", QT + "seed_screen.py", 'UI.label(row["value"], "muted" if row["missing"] else "body_lg", wrap=True), value_stretch)', 'UI.label(row["value"], "sub" if row["missing"] else "body_lg", wrap=True), value_stretch)', py="dev")
add("NM4", "변수로 역할을 넘겨 새 muted 안내 문장을 더함(옛 눈의 맹점)", QT + "candidate_screen.py", '    trend = vm["trend"]\n', '    _r = "muted"\n    layout.addWidget(UI.label("새 안내 문장이에요.", _r, wrap=True))\n    trend = vm["trend"]\n', py="dev")
add("NM5", "뒤에 덧붙인 QSS 규칙이 sub 글자 색을 흐린 글로 덮음(옛 눈은 첫 규칙만 읽음)", THEME, "QLabel[trend=\"none\"] {{ color: {c['text_muted']}; }}", "QLabel[trend=\"none\"] {{ color: {c['text_muted']}; }}\nQLabel[role=\"sub\"] {{ color: {c['text_muted']}; }}", py="dev")
add("NM6", "한 줄 입력 칸 테두리를 어둡게 하는 규칙을 원래 규칙 앞에 덧붙임", THEME, "QLabel[trend=\"none\"] {{ color: {c['text_muted']}; }}", "QLabel[trend=\"none\"] {{ color: {c['text_muted']}; }}\nQLineEdit {{ border: 1px solid #767676; }}", py="dev")
add("NM7", "보조 글 토큰이 한 단위 어긋남(#5F6B7A → #5F6B7B)", TOKENS, '("Text/Secondary", "text_secondary", "#5F6B7A", "보조 설명"),', '("Text/Secondary", "text_secondary", "#5F6B7B", "보조 설명"),', py="dev")
add("NM8", "muted 역할이 보조 글 색을 가리킴(어디서나 muted 가 읽기 쉬워짐)", TOKENS, '"sub": "text_secondary", "muted": "text_muted",', '"sub": "text_secondary", "muted": "text_secondary",', py="dev")
add("NM9", "바꾼 문장 하나를 caption 역할로(색은 보조 글이지만 크기가 달라짐)", QT + "candidate_screen.py", 'UI.label(reason["empty"], "sub", wrap=True)', 'UI.label(reason["empty"], "caption", wrap=True)', py="dev")
add("NM10", "라벨 부품이 sub 일 때 자기 스타일시트로 흐린 색을 박음(역할 규칙과 다른 색)", QT + "components.py", '        self._role, self._wrap, self._text = role, wrap, ""\n        self.setProperty("role", role)\n',
    '        self._role, self._wrap, self._text = role, wrap, ""\n        self.setProperty("role", role)\n        if role == "sub":\n            self.setStyleSheet("color: #8491A3;")\n', py="dev")
add("NM11", "편집기(QPlainTextEdit) 테두리가 원래 규칙 안에서 글자 색 토큰으로", THEME, "QPlainTextEdit[editor=\"true\"] {{ background: {c['surface']}; border: 1px solid {c['border_strong']};", "QPlainTextEdit[editor=\"true\"] {{ background: {c['surface']}; border: 1px solid {c['text_secondary']};", py="dev")
add("NM12", "입력 칸 테두리 토큰 값을 어둡게(#B8C7DA → #A0B0C4 — 승인한 목업의 색이 바뀜)", TOKENS, '"border": "#DCE4F0", "border_strong": "#B8C7DA",', '"border": "#DCE4F0", "border_strong": "#A0B0C4",', py="dev")
add("NM13", "진짜 덮어쓰기 — 한 줄 입력 칸 테두리를 어둡게 하는 규칙을 **원래 규칙 뒤에** 덧붙임(뒤 규칙이 이긴다)", THEME, "QPlainTextEdit[editor=\"true\"]:focus {{ border: 2px solid {c['border_focus']}; }}", "QPlainTextEdit[editor=\"true\"]:focus {{ border: 2px solid {c['border_focus']}; }}\nQLineEdit {{ border: 1px solid #767676; }}", py="dev")
for _mid in ("NM1", "NM2", "NM4", "NM5", "NM10", "NM13"):
    _clone = dict(MUTATIONS[_mid])
    _clone["py"] = "qt"
    MUTATIONS[_mid + "q"] = _clone
# 새 규칙마다 내 변이 — 역할 식 못박기·변수 역할·`muted` 글자 세기·스타일시트 소스 규칙·인라인 스타일
add("R01", "확인 권장 줄의 조건 뒤집기(`'small' if lines else 'sub'` → 반대)", QT + "draft_screen.py", 'UI.label("· " + line if group["lines"] else line, "small" if group["lines"] else "sub", wrap=True)',
    'UI.label("· " + line if group["lines"] else line, "sub" if group["lines"] else "small", wrap=True)', py="dev")
add("R02", "후보 카드 요약의 조건 뒤집기(`sub` if 없음 → 있음)", QT + "candidate_parts.py", '"sub" if vm["summary_missing"] else "small"', '"small" if vm["summary_missing"] else "sub"', py="dev")
add("R03", "카테고리 안내가 값이 있을 때도 늘 sub(조건 제거)", QT + "draft_screen.py", 'UI.label(text, "sub" if missing else "body", wrap=True)', 'UI.label(text, "sub", wrap=True)', py="dev")
add("R04", "제목줄 만드는 호출이 `role=\"muted\"` 키워드로 흐린 글을 넘김(`role=` 키워드 길)", QT + "candidate_screen.py", '    outer.addLayout(page_head(vm["title"], vm["sub"], rights))', '    outer.addLayout(page_head(vm["title"], vm["sub"], rights, role="muted"))', py="dev")
add("R05", "백업 카드 안내 글 묶음(튜플)에 muted 가 들어감(역할이 묶음 속 글자로 넘어가는 길)", QT + "backup_parts.py", '(vm["location"], "small"), (vm["copy_tip"], "small")', '(vm["location"], "muted"), (vm["copy_tip"], "small")', py="dev")
add("R06", "제목줄 만드는 함수의 기본 역할이 muted(함수 기본값 길)", QT + "screens.py", 'def page_head(title, sub, rights=(), role="display", note=""):', 'def page_head(title, sub, rights=(), role="muted", note=""):', py="dev")
add("R07", "새 muted 문장을 글자 리터럴로 더함(가장 단순한 길)", QT + "candidate_screen.py", '    trend = vm["trend"]\n', '    layout.addWidget(UI.label("새 안내 문장이에요.", "muted", wrap=True))\n    trend = vm["trend"]\n', py="dev")
add("R08", "손으로 쓴 `QLabel[role=\"muted\"]` 규칙을 덧붙여 muted 를 보조 글 색으로 덮음", THEME, "QLabel[trend=\"none\"] {{ color: {c['text_muted']}; }}", "QLabel[trend=\"none\"] {{ color: {c['text_muted']}; }}\nQLabel[role=\"muted\"] {{ color: {c['text_secondary']}; }}", py="dev")
add("R09", "입력 칸 선택자 하나를 더해 테두리를 어둡게(`QLineEdit[focus_ring=\"true\"]` — 선택자 목록 못박기)", THEME, "QPlainTextEdit[editor=\"true\"]:focus {{ border: 2px solid {c['border_focus']}; }}", "QPlainTextEdit[editor=\"true\"]:focus {{ border: 2px solid {c['border_focus']}; }}\nQLineEdit[focus_ring=\"true\"] {{ border: 1px solid #767676; }}", py="dev")
add("R10", "후보 상세의 안전 없음 문장 라벨에 위젯별 스타일시트로 흐린 색을 박음", QT + "candidate_screen.py", 'inner.addWidget(UI.label(safety["none"], "sub", wrap=True))',
    '_label = UI.label(safety["none"], "sub", wrap=True)\n    _label.setStyleSheet("color: #8491A3;")\n    inner.addWidget(_label)', py="dev")
# Qt 있을 때만 잡히는 것(Qt 없는 시험은 못 보는 길) — 실제 그림·실제 글자 색을 읽는 시험의 몫
add("R11", "역할 규칙을 만드는 반복문이 sub 에 흐린 글 색을 넣음(토큰·소스의 글자 모양은 그대로 — 만들어진 스타일시트만 틀림)", THEME, "color: {K.role_color(c, role)}; }}'", "color: {K.role_color(c, 'muted' if role == 'sub' else role)}; }}'", py="qt")
add("R12", "한 줄 입력 칸에 margin 1px — 테두리가 안쪽으로 한 칸 밀림(스타일시트 글의 border 줄은 그대로라 소스 시험은 못 봄)", THEME, "QLineEdit {{ background: {c['surface']}; border: 1px solid {c['border_strong']};", "QLineEdit {{ margin: 1px; background: {c['surface']}; border: 1px solid {c['border_strong']};", py="qt")
