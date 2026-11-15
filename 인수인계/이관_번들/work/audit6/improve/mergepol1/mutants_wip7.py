"""4차(WIP 7) 변이 — mutants_extra.py 가 불러 쓴다. FIXED7: 코드가 바뀌어 옛 글이 안 맞는 기존 변이의 새 (옛 글, 새 글). NEW7: 새 규칙(N-M1·S-N1·S-N2·S-N3·I-N1·I-N3·I-N7·§7-7 보강)마다 둘 이상의 변이.
백슬래시가 든 글은 모두 raw 문자열(r'...')로 적어 모듈 소스의 글과 글자 그대로 같게 한다."""
MOD = "pipeline/merge_policy.py"
DOC = "docs/AI_MERGE_POLICY.md"
REG = "docs/DEFECT_REGISTER.md"


def M(mid, area, what, old, new, path=MOD):
    return {"id": mid, "area": area, "what": what, "path": path, "old": old, "new": new}


PATH_LINE = r'    text = raw.rstrip("\r\n").replace("\\", "/")'
SEGMENT_LINE = '        if segment == ".." or segment != segment.strip():'
CTRL = "any(ord(ch) < 32 or 127 <= ord(ch) <= 159 for ch in text)"
DEP_LIST = '(base.endswith((".txt", ".in")) and any(word in base for word in _DEPENDENCY_LIST_WORDS))'
DEP_NAME = "or any(word in base for word in _DEPENDENCY_NAME_WORDS))"
FILES_TAIL = '    "pipeline/run.py", "pipeline/operator_loop.py", "pipeline/telegram_inbox.py",\n)'
DOCS_TAIL = '"docs/QUALITY_GATE.md", "docs/REQUEST_BRIEFING.md")'
MISSING_LINE = "            missing = sorted(path for path in paths if path not in keyed)\n            if missing:"
S10_OLD = ('SAFETY_GUARD_DOCS = ("docs/SECURITY_GUARDRAILS.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md", "AI_COLLAB.md", "HANDLER.md", "docs/CHARTER.md", "docs/ACTIONS_GUIDE.md", "docs/AGENT_RUNBOOK.md",\n'
           '                     "docs/SESSION_START.md", "docs/ENGINEERING_GUIDE.md", "docs/AGENT_DELEGATION.md", "docs/COPILOT_GUIDE.md", "docs/AI_FLOW.md", "docs/AI_MODEL_GUIDE.md", "docs/SOURCE_POLICY.md",\n'
           '                     "docs/QUALITY_GATE.md", "docs/REQUEST_BRIEFING.md")')

# 코드가 바뀌어 옛 명세가 안 맞는 기존 변이의 새 명세
FIXED7 = {
    "C03": ("    kind_ok = type(repo_kind) is str and repo_kind in REPO_KINDS", "    kind_ok = True"),
    "C06": ("    if any(part in _DEPENDENCY_DIRS for part in segments) or _is_dependency_name(base):", "    if False:"),
    "C19": (PATH_LINE, r'    text = raw.rstrip("\r\n")'),
    "S10": (S10_OLD, "SAFETY_GUARD_DOCS = ()"),
    "N32": ("            if any(not _listed_key(key, paths) for key, _text in items):", "            if False:"),
    "N43": (r'r"constraints[^/]*|package[^/]*\.json', r'r"constraints[^/]*\.txt|package[^/]*\.json'),
    "N45": (DEP_LIST, '(base.endswith(".txt") and any(word in base for word in _DEPENDENCY_LIST_WORDS))'),
    "R203": (CTRL, "any(ord(ch) < 32 or 128 <= ord(ch) <= 159 for ch in text)"),
    "DS15": ("AI 가 읽고 따르는 규칙 문서 18개도 운영자 전용입니다", "AI 가 읽고 따르는 규칙 문서 18개는 AI 가 병합할 수 있습니다"),
}

NEW7 = [
    # ---- N-M1 경로 정규화: 앞뒤 공백·제어 문자
    M("Q01", "경로공백", "경로를 양끝 모두 다듬음(옛 strip 복원 — 맨 앞 공백 우회)", PATH_LINE, r'    text = raw.strip().replace("\\", "/")'),
    M("Q02", "경로공백", "경로의 오른쪽 공백까지 다듬음", PATH_LINE, r'    text = raw.rstrip().replace("\\", "/")'),
    M("Q03", "경로공백", "줄 끝의 줄 바꿈도 떼지 않음", PATH_LINE, r'    text = raw.replace("\\", "/")'),
    M("Q04", "경로공백", "구간 앞뒤 공백 검사를 뺌", SEGMENT_LINE, '        if segment == "..":'),
    M("Q05", "경로공백", "구간 공백 검사를 맨 앞만(lstrip)", SEGMENT_LINE, '        if segment == ".." or segment != segment.lstrip():'),
    M("Q06", "경로공백", "구간 공백 검사를 맨 뒤만(rstrip)", SEGMENT_LINE, '        if segment == ".." or segment != segment.rstrip():'),
    M("Q07", "경로공백", "구간 공백 검사를 ASCII 공백 한 종류만", SEGMENT_LINE, '        if segment == ".." or segment != segment.strip(" "):'),
    M("Q08", "경로공백", "제어 문자 검사에서 C1 범위(128-159) 제외", CTRL, "any(ord(ch) < 32 or ord(ch) == 127 for ch in text)"),
    M("Q09", "경로공백", "경로 입력의 정확한 형 검사를 하위 형식까지 허용", "    if type(raw) is not str:\n        return None\n    text = raw.rstrip", "    if not isinstance(raw, str):\n        return None\n    text = raw.rstrip"),
    M("Q10", "경로공백", "제어 문자 검사를 아예 뺌(공백 검사만 남김)", CTRL, "False"),
    # ---- S-N1 안전 장치 목록: 코드 3개
    M("Q11", "안전목록7", "안전 목록에서 pipeline/run.py 삭제", FILES_TAIL, '    "pipeline/operator_loop.py", "pipeline/telegram_inbox.py",\n)'),
    M("Q12", "안전목록7", "안전 목록에서 pipeline/operator_loop.py 삭제", FILES_TAIL, '    "pipeline/run.py", "pipeline/telegram_inbox.py",\n)'),
    M("Q13", "안전목록7", "안전 목록에서 pipeline/telegram_inbox.py 삭제", FILES_TAIL, '    "pipeline/run.py", "pipeline/operator_loop.py",\n)'),
    # ---- S-N1 규칙 문서 8개 삭제 + 사전·확인 항목을 코드에 더함
    M("Q14", "안전목록7", "규칙 문서 목록에서 docs/ENGINEERING_GUIDE.md 삭제", '"docs/ENGINEERING_GUIDE.md", ', ""),
    M("Q15", "안전목록7", "규칙 문서 목록에서 docs/AGENT_DELEGATION.md 삭제", '"docs/AGENT_DELEGATION.md", ', ""),
    M("Q16", "안전목록7", "규칙 문서 목록에서 docs/COPILOT_GUIDE.md 삭제", '"docs/COPILOT_GUIDE.md", ', ""),
    M("Q17", "안전목록7", "규칙 문서 목록에서 docs/AI_FLOW.md 삭제", '"docs/AI_FLOW.md", ', ""),
    M("Q18", "안전목록7", "규칙 문서 목록에서 docs/AI_MODEL_GUIDE.md 삭제", '"docs/AI_MODEL_GUIDE.md", ', ""),
    M("Q19", "안전목록7", "규칙 문서 목록에서 docs/SOURCE_POLICY.md 삭제", '"docs/SOURCE_POLICY.md",', ""),
    M("Q20", "안전목록7", "규칙 문서 목록에서 docs/QUALITY_GATE.md 삭제", DOCS_TAIL, '"docs/REQUEST_BRIEFING.md")'),
    M("Q21", "안전목록7", "규칙 문서 목록에서 docs/REQUEST_BRIEFING.md 삭제", DOCS_TAIL, '"docs/QUALITY_GATE.md")'),
    M("Q22", "안전목록7", "용어 사전 GLOSSARY 를 규칙 문서 목록에 더함(운영자 확인 대기 항목을 코드에 넣음)", DOCS_TAIL, '"docs/QUALITY_GATE.md", "docs/REQUEST_BRIEFING.md", "docs/GLOSSARY.md")'),
    M("Q23", "안전목록7", "pipeline/drafts.py 를 안전 목록에 더함(운영자 확인 대기 항목을 코드에 넣음)", FILES_TAIL,
      '    "pipeline/run.py", "pipeline/operator_loop.py", "pipeline/telegram_inbox.py", "pipeline/drafts.py",\n)'),
    M("Q24", "안전목록7", "pipeline/shadow_run.py 를 안전 목록에 더함(운영자 확인 대기 항목을 코드에 넣음)", FILES_TAIL,
      '    "pipeline/run.py", "pipeline/operator_loop.py", "pipeline/telegram_inbox.py", "pipeline/shadow_run.py",\n)'),
    # ---- S-N2 사전 형태는 변경 파일마다 키
    M("Q25", "사전키7", "변경 파일마다 키가 있어야 한다는 검사를 뺌", MISSING_LINE, "            missing = sorted(path for path in paths if path not in keyed)\n            if False:"),
    M("Q26", "사전키7", "코드 파일(.py)은 키가 없어도 통과", "            missing = sorted(path for path in paths if path not in keyed)", '            missing = sorted(path for path in paths if path not in keyed and not path.endswith(".py"))'),
    M("Q27", "사전키7", "키가 없는 파일이 둘 이상일 때만 지적", MISSING_LINE, "            missing = sorted(path for path in paths if path not in keyed)\n            if len(missing) > 1:"),
    M("Q28", "사전키7", "시험·문서 파일은 키가 없어도 통과(지시 글자 그대로의 느슨한 해석)", "            missing = sorted(path for path in paths if path not in keyed)",
      '            missing = sorted(path for path in paths if path not in keyed and not path.endswith(DOC_SUFFIXES) and not path.startswith("tests/"))'),
    M("Q29", "사전키7", "키 목록을 정규화 없이 만듦(./ 나 역슬래시 키가 빠짐으로 읽힘)", "            keyed = {normalize_repo_path(key) for key, _text in items if isinstance(key, str)}", "            keyed = {key for key, _text in items if isinstance(key, str)}"),
    M("Q30", "사전키7", "키 없는 파일 지적 문구에서 파일 이름을 안 보임", '", ".join(_shown(item) for item in missing[:3])\n                          + (" 외 "', '"" + (" 외 "'),
    # ---- I-N1 의존성 이름
    M("Q40", "의존성7", "의존성 낱말에서 deps 삭제", '_DEPENDENCY_LIST_WORDS = ("requirements", "deps", "dependencies")', '_DEPENDENCY_LIST_WORDS = ("requirements", "dependencies")'),
    M("Q41", "의존성7", "의존성 낱말에서 requirements 삭제", '_DEPENDENCY_LIST_WORDS = ("requirements", "deps", "dependencies")', '_DEPENDENCY_LIST_WORDS = ("deps", "dependencies")'),
    M("Q42", "의존성7", "의존성 낱말에서 dependencies 삭제", '_DEPENDENCY_LIST_WORDS = ("requirements", "deps", "dependencies")', '_DEPENDENCY_LIST_WORDS = ("requirements", "deps")'),
    M("Q43", "의존성7", "이름 낱말에서 dockerfile 삭제", '_DEPENDENCY_NAME_WORDS = ("dockerfile", "makefile")', '_DEPENDENCY_NAME_WORDS = ("makefile",)'),
    M("Q44", "의존성7", "이름 낱말에서 makefile 삭제", '_DEPENDENCY_NAME_WORDS = ("dockerfile", "makefile")', '_DEPENDENCY_NAME_WORDS = ("dockerfile",)'),
    M("Q45", "의존성7", "의존성 낱말 이름은 .in 끝만(requirements.txt 가 빠짐)", DEP_LIST, '(base.endswith(".in") and any(word in base for word in _DEPENDENCY_LIST_WORDS))'),
    M("Q46", "의존성7", "의존성 낱말을 이름 맨 앞에서만 찾음(dev-requirements.txt 가 빠짐)", DEP_LIST, '(base.endswith((".txt", ".in")) and any(base.startswith(word) for word in _DEPENDENCY_LIST_WORDS))'),
    M("Q47", "의존성7", "이름 낱말을 이름 전체가 같을 때만(prod.Dockerfile 이 빠짐)", DEP_NAME, "or base in _DEPENDENCY_NAME_WORDS)"),
    M("Q48", "의존성7", "의존성 낱말 이름의 .txt·.in 조건을 뺌(docs/dependencies.md 같은 문서도 걸림)", DEP_LIST, "any(word in base for word in _DEPENDENCY_LIST_WORDS)"),
    M("Q49", "의존성7", "이름 낱말을 낱말 일부(앞 4글자)만 비교(docker 만 든 이름도 걸림)", DEP_NAME, 'or any(word[:4] in base for word in _DEPENDENCY_NAME_WORDS))'),
    # ---- I-N3 정확한 형 방어
    M("Q50", "형방어7", "저장소 종류를 str 하위 형식까지 받음", "    kind_ok = type(repo_kind) is str and repo_kind in REPO_KINDS", "    kind_ok = isinstance(repo_kind, str) and repo_kind in REPO_KINDS"),
    M("Q51", "형방어7", "양의 정수를 int 하위 형식까지 받음(bool 만 거절)", "    return type(value) is int and value > 0 ", "    return isinstance(value, int) and not isinstance(value, bool) and value > 0 "),
    M("Q52", "형방어7", "0 이상 정수를 int 하위 형식까지 받음(bool 만 거절)", "    return type(value) is int and value >= 0", "    return isinstance(value, int) and not isinstance(value, bool) and value >= 0"),
    M("Q53", "형방어7", "양의 정수가 bool 을 받음", "    return type(value) is int and value > 0 ", "    return type(value) in (int, bool) and value > 0 "),
    # ---- S-N3 문서: 재계산 과장 정정과 값의 출처
    M("Q60", "문서7", "§6 의 재계산 범위 문장을 과장으로 되돌림", "이 함수가 스스로 다시 계산하는 것은 변경 분류와 머리 커밋 일치뿐이고 나머지 값은 모양만 확인합니다", "넘겨받은 값을 믿지 않고 이 함수가 다시 확인합니다", DOC),
    M("Q61", "문서7", "§6 의 신뢰할 수 있는 워크플로 문장 삭제", " — 그래서 값은 GitHub 에서 직접 읽는 신뢰할 수 있는 워크플로가 만든 것이어야 합니다(§11-3).", ".", DOC),
    M("Q62", "문서7", "§11-3 값의 출처 항목 제목 약화", "- **값의 출처**(켜기 전의 필수 조건):", "- 값의 출처:", DOC),
    M("Q63", "문서7", "§11-3 값의 출처 목록에서 previous_merge_main_check 삭제", "`pr_draft`·`previous_merge_main_check` 는 GitHub 에서 직접 읽는", "`pr_draft` 는 GitHub 에서 직접 읽는", DOC),
    M("Q64", "문서7", "§11-3 값의 출처 목록에서 repo_kind 삭제", "`repo_kind`·`changed_text`·`checks`·`required_checks`", "`changed_text`·`checks`·`required_checks`", DOC),
    M("Q65", "문서7", "§11-3 의 PR 작성자가 채울 수 있으면 안 된다는 문장 삭제", "PR 작성자나 PR 쪽 파일이 채울 수 있으면 안 됩니다", "PR 작성자가 채워도 됩니다", DOC),
    # ---- I-N7 절 머리 한 줄
    M("Q70", "머리줄7", "§6 머리의 켜진 뒤 동작 한 줄 삭제", "## 6. 병합 직전 재확인 8조건\n\n이 절은 켜진 뒤의 동작이며 지금은 꺼져 있습니다.\n\n", "## 6. 병합 직전 재확인 8조건\n\n", DOC),
    M("Q71", "머리줄7", "§8 머리의 켜진 뒤 동작 한 줄 삭제", "## 8. 병합 방식 제한\n\n이 절은 켜진 뒤의 동작이며 지금은 꺼져 있습니다. 다만 main 에 직접 push 하지 않는다는 원칙은 꺼져 있는 지금도 그대로입니다.\n\n", "## 8. 병합 방식 제한\n\n", DOC),
    M("Q72", "머리줄7", "§9 머리의 켜진 뒤 동작 한 줄 삭제", "## 9. 사후 처리\n\n이 절은 켜진 뒤의 동작이며 지금은 꺼져 있습니다.\n\n", "## 9. 사후 처리\n\n", DOC),
    M("Q73", "머리줄7", "§10 머리의 켜진 뒤 동작 한 줄 삭제", "## 10. 첫 운영 3건 시험과 즉시 중지\n\n이 절은 켜진 뒤의 동작이며 지금은 꺼져 있습니다.\n\n", "## 10. 첫 운영 3건 시험과 즉시 중지\n\n", DOC),
    M("Q74", "머리줄7", "§8 머리에서 main 직접 push 금지는 지금도 그대로라는 말 삭제", " 다만 main 에 직접 push 하지 않는다는 원칙은 꺼져 있는 지금도 그대로입니다.", "", DOC),
    # ---- §7-6·§7-7 보강과 §7-2 단락
    M("Q80", "문서7", "§7-7 운영자 확인 대기 항목 표시 삭제", "- **운영자 확인 대기 항목**: 용어 사전", "- 용어 사전", DOC),
    M("Q81", "문서7", "§7-7 셸 명령 이름 목록 삭제", "`openssl s_client`·`socat`·`aria2c`·`npm publish`·`docker push`·`pip install` 같은 것도 따로 잡지 않습니다", "셸 명령도 따로 잡지 않습니다", DOC),
    M("Q82", "문서7", "§7-7 도메인 모양 따옴표 글 항목의 예시 삭제", "(`'row.id'`·`'obj.is'`·`'a.to'`·`'config.dev'`·`'pipeline.store'`)", "(예시 생략)", DOC),
    M("Q83", "문서7", "§7-7 되돌리는 방법 문구는 정확히 같을 때만 거절한다는 말을 약화", "**정확히 같을 때만**", "같을 때", DOC),
    M("Q84", "문서7", "§7-6 의 용어 사전 제외 사유 삭제", " 용어 사전(`docs/GLOSSARY.md`)은 규칙이 아니라 사전이라 넣지 않았습니다(§7-7).", "", DOC),
    M("Q85", "문서7", "§7-6 코드 파일 목록에서 새 세 파일 삭제", "·`pipeline/run.py`·`pipeline/operator_loop.py`·`pipeline/telegram_inbox.py`, 그리고 폴더", ", 그리고 폴더", DOC),
    M("Q86", "문서7", "§7-2 8번 행의 이름 안 requirements 예시 삭제", "(이름 안에 `requirements` 가 든 `dev-requirements.txt`·`pip-requirements.in` 도)", "", DOC),
    M("Q87", "문서7", "§7-2 경로 단락의 앞뒤 공백 거절 문장을 약화", "**어느 구간이든 앞뒤에 공백(유니코드 공백 포함)이 있는 경로**", "공백이 있는 경로", DOC),
    M("Q88", "문서7", "§7-2 사전 단락에서 변경 파일마다 키가 있어야 한다는 말 삭제", "**키가 모두 변경 파일 목록에 있어야 하고 변경 파일마다 키가 있어야**", "키가 모두 변경 파일 목록에 있어야", DOC),
    M("Q89", "문서7", "§7-2 경로 단락의 줄 끝 줄 바꿈만 뗀다는 말 삭제", "(줄 끝의 줄 바꿈만 떼고 경로 자체는 다듬지 않습니다)", "", DOC),
    M("Q90", "문서7", "대장 D-347 행의 규칙 문서 개수를 옛 값으로", "규칙 문서 18개", "규칙 문서 10개", REG),
    # ---- DOCUMENTED_RULE_WORDS 의 새 낱말
    M("Q91", "표7", "문서 규칙 낱말 표에서 deps.txt 삭제", '    "deps.txt", "Dockerfile", "Makefile",\n', '    "Dockerfile", "Makefile",\n'),
    M("Q92", "표7", "문서 규칙 낱말 표에서 Dockerfile 삭제", '    "deps.txt", "Dockerfile", "Makefile",\n', '    "deps.txt", "Makefile",\n'),
    M("Q93", "표7", "문서 규칙 낱말 표에서 Makefile 삭제", '    "deps.txt", "Dockerfile", "Makefile",\n', '    "deps.txt", "Dockerfile",\n'),
]
