p = "C:/work/ai/improve_wt_mergepol1/pipeline/merge_policy.py"
t = open(p, encoding="utf-8", newline="").read()


def rep(old, new, count=1):
    global t
    assert t.count(old) == count, (t.count(old), old[:100])
    t = t.replace(old, new)


# ---- S-N1 안전 장치 목록: 코드 3개와 규칙 문서 8개
rep('''SAFETY_GUARD_DOCS = ("docs/SECURITY_GUARDRAILS.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md", "AI_COLLAB.md", "HANDLER.md", "docs/CHARTER.md", "docs/ACTIONS_GUIDE.md", "docs/AGENT_RUNBOOK.md",
                     "docs/SESSION_START.md")''',
    '''SAFETY_GUARD_DOCS = ("docs/SECURITY_GUARDRAILS.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md", "AI_COLLAB.md", "HANDLER.md", "docs/CHARTER.md", "docs/ACTIONS_GUIDE.md", "docs/AGENT_RUNBOOK.md",
                     "docs/SESSION_START.md", "docs/ENGINEERING_GUIDE.md", "docs/AGENT_DELEGATION.md", "docs/COPILOT_GUIDE.md", "docs/AI_FLOW.md", "docs/AI_MODEL_GUIDE.md", "docs/SOURCE_POLICY.md",
                     "docs/QUALITY_GATE.md", "docs/REQUEST_BRIEFING.md")''')
rep('''"scripts/get_blogger_token.py", "scripts/watchdog.py", "tests/test_site_cleanup.py",
)''', '''"scripts/get_blogger_token.py", "scripts/watchdog.py", "tests/test_site_cleanup.py",
    "pipeline/run.py", "pipeline/operator_loop.py", "pipeline/telegram_inbox.py",
)''')
rep('''# 문서(DOC_SUFFIXES)는 SAFETY_GUARD_DOCS 의 파일(AI 가 읽고 따르는 규칙 문서 — 총괄(AI)의 판단 R5)만 해당한다.''',
    '''# 문서(DOC_SUFFIXES)는 SAFETY_GUARD_DOCS 의 파일(AI 가 읽고 따르는 규칙 문서 — 총괄(AI)의 판단 R5. 용어 사전 GLOSSARY 는 제외)만 해당한다.''')

# ---- I-N1 의존성 이름
rep('''_DEPENDENCY_BASE_RE = re.compile(r"requirements[^/]*\\.(?:txt|in)|constraints[^/]*|package[^/]*\\.json|pnpm-lock\\.yaml|pyproject\\.toml|setup\\.py|setup\\.cfg|pipfile[^/]*|gemfile[^/]*|[^/]*\\.lock"
                                 r"|\\.gitmodules|environment[^/]*\\.ya?ml|conda[^/]*")''',
    '''_DEPENDENCY_BASE_RE = re.compile(r"constraints[^/]*|package[^/]*\\.json|pnpm-lock\\.yaml|pyproject\\.toml|setup\\.py|setup\\.cfg|pipfile[^/]*|gemfile[^/]*|[^/]*\\.lock"
                                 r"|\\.gitmodules|environment[^/]*\\.ya?ml|conda[^/]*")
# 이름 안에 낱말이 들어 있으면 걸리는 의존성 이름 — 글자 찾기로 한다(정규식으로 쓰면 아주 긴 이름에서 시간이 제곱으로 늘 수 있다)
_DEPENDENCY_LIST_WORDS = ("requirements", "deps", "dependencies")            # + 끝이 .txt 나 .in 일 때(dev-requirements.txt·deps.txt·pip-requirements.in)
_DEPENDENCY_NAME_WORDS = ("dockerfile", "makefile")                          # 이름 안에 있기만 하면(Dockerfile·Makefile·prod.Dockerfile)''')
rep('''    if any(part in _DEPENDENCY_DIRS for part in segments) or _DEPENDENCY_BASE_RE.fullmatch(base) is not None:''',
    '''    if any(part in _DEPENDENCY_DIRS for part in segments) or _is_dependency_name(base):''')
rep('''def _path_findings(repo_kind, path):''', '''def _is_dependency_name(base):
    """의존성 목록·잠금·설치 파일 이름인가(소문자로 접은 파일 이름)."""
    return (_DEPENDENCY_BASE_RE.fullmatch(base) is not None or (base.endswith((".txt", ".in")) and any(word in base for word in _DEPENDENCY_LIST_WORDS))
            or any(word in base for word in _DEPENDENCY_NAME_WORDS))


def _path_findings(repo_kind, path):''')
rep('''    "os.remove", "unlink(", "rm -rf", "DROP COLUMN", "DROP INDEX", "Authorization", "sk_live_", "sk_test_",
)''', '''    "os.remove", "unlink(", "rm -rf", "DROP COLUMN", "DROP INDEX", "Authorization", "sk_live_", "sk_test_",
    "deps.txt", "Dockerfile", "Makefile",
)''')

# ---- I-N3 저장소 종류의 정확한 형식
rep('''    kind_ok = isinstance(repo_kind, str) and repo_kind in REPO_KINDS''', '''    kind_ok = type(repo_kind) is str and repo_kind in REPO_KINDS''')

# ---- S-N2 사전 형태는 변경 파일마다 키가 있어야 한다
rep('''        if isinstance(changed_text, dict) and any(not _listed_key(key, paths) for key, _text in items):
            add_plain("invalid_input", "바뀐 줄의 글이 변경 파일 목록에 없는 경로에 붙어 있습니다")''',
    '''        if isinstance(changed_text, dict):
            if any(not _listed_key(key, paths) for key, _text in items):
                add_plain("invalid_input", "바뀐 줄의 글이 변경 파일 목록에 없는 경로에 붙어 있습니다")
            keyed = {normalize_repo_path(key) for key, _text in items if isinstance(key, str)}
            missing = sorted(path for path in paths if path not in keyed)
            if missing:
                add_plain("invalid_input", "변경 파일 중 바뀐 줄의 글이 없는 파일이 있습니다(글이 없으면 빈 글을 넣어야 합니다): " + ", ".join(_shown(item) for item in missing[:3])
                          + (" 외 " + str(len(missing) - 3) + "개" if len(missing) > 3 else ""))''')
rep('''(예전 이름 added_text 도 받지만 두 이름을 함께 쓰면 입력 오류다). 사전의 키는 모두 변경 파일 목록에 있어야 한다(없으면 입력 오류).''',
    '''(예전 이름 added_text 도 받지만 두 이름을 함께 쓰면 입력 오류다). 사전으로 받으면 키는 모두 변경 파일 목록에 있어야 하고 변경 파일마다 키가 있어야 한다(글이 없는 파일은 빈 글 — 없으면 입력 오류).''')
rep('''        add_plain("invalid_input", "변경 파일 목록의 모양이 올바르지 않습니다(글자 목록이어야 하고 .. 구간이 든 경로·절대 경로는 안 됩니다)")''',
    '''        add_plain("invalid_input", "변경 파일 목록의 모양이 올바르지 않습니다(글자 목록이어야 하고 .. 구간이 든 경로·절대 경로·구간 앞뒤에 공백이 있는 경로는 안 됩니다)")''')
open(p, "w", encoding="utf-8", newline="").write(t)
print("ok")
