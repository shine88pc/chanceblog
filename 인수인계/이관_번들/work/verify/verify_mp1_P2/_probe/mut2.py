import hashlib
import pathlib
import subprocess
import sys

PY = "<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe"
ROOT = pathlib.Path("C:/work/ai/verify_mp1_P2/_mut2")
SRC = ROOT / "pipeline" / "merge_policy.py"
orig = SRC.read_bytes()
H0 = hashlib.sha256(orig).hexdigest()
text0 = orig.decode("utf-8").replace(chr(13) + chr(10), chr(10))

MUTS = [
    ("n01 기본 거부 끄기", "        if not found and parts[0] not in SITE_INTERNAL_ENTRIES:", "        if False:"),
    ("n02 문서 면제를 항상 켬", "for code, why in _text_findings(text, _doc_only_text(key, paths)):", "for code, why in _text_findings(text, True):"),
    ("n03 문서 면제를 항상 끔", "for code, why in _text_findings(text, _doc_only_text(key, paths)):", "for code, why in _text_findings(text, False):"),
    ("n04 문서에서 강한 비밀 모양 무시", "    for label, rx in _SECRET_VALUE_RES:\n        if rx.search(text):", "    for label, rx in _SECRET_VALUE_RES:\n        if not doc_only and rx.search(text):"),
    ("n05 문서에서 광고 낱말 무시", "    if _ADS_TEXT_RE.search(text):\n        found.append((\"ads\"", "    if not doc_only and _ADS_TEXT_RE.search(text):\n        found.append((\"ads\""),
    ("n06 재계산 결과 무시", "    if again.tier != TIER_AI_OK:", "    if False:"),
    ("n07 필수 검사 누락 무시", "        missing = sorted(name for name in required if name not in passed)", "        missing = []"),
    ("n08 직전 병합 main 검사 무시", "    if not after.may_merge_next:", "    if False:"),
    ("n09 설명 때 머리와 승인 때 머리 비교 생략", "    if approved != arrived:\n        return \"쉬운 설명을 보낸 뒤", "    if False:\n        return \"쉬운 설명을 보낸 뒤"),
    ("n10 PR 상태 open 확인 생략", "    if state != \"open\":", "    if False:"),
    ("n11 초안 확인 생략", "    if draft is not False:", "    if False:"),
    ("n12 pending 이어도 다음 병합 허용", "PostMergeDecision(state, False, (), \"직전 병합의 main 검사가 아직 끝나지 않았습니다", "PostMergeDecision(state, True, (), \"직전 병합의 main 검사가 아직 끝나지 않았습니다"),
    ("n13 점검표를 분류와 상관없이 전부 아니오", "lines += [\"- \" + name + \": \" + (\"예\" if code in classified.categories else \"아니오\") for code, name in OPERATOR_ONLY_ITEMS]",
     "lines += [\"- \" + name + \": 아니오\" for code, name in OPERATOR_ONLY_ITEMS]"),
    ("n14 점검표 중복 행 허용", "            elif names.count(name) > 1:", "            elif False:"),
    ("n15 병합 방식 줄을 부분 문자열로", "    elif way_body not in (AI_MERGE_OFF_NOTICE, AI_MERGE_ON_NOTICE):", "    elif not any(n in way_body for n in (AI_MERGE_OFF_NOTICE, AI_MERGE_ON_NOTICE)):"),
    ("n16 사전 키가 변경 목록에 있는지 확인 생략", "        if isinstance(changed_text, dict) and any(not _listed_key(key, paths) for key, _text in items):", "        if False:"),
    ("n17 사전을 경로 목록으로 받음", "    if paths is None or isinstance(paths, (str, bytes)) or hasattr(paths, \"keys\"):", "    if paths is None or isinstance(paths, (str, bytes)):"),
    ("n18 publishers 폴더 목록 끄기", "or folded.startswith(_SAFETY_DIR_PREFIXES)", "or False"),
    ("n19 draft_flow.py 를 안전 목록에서 뺌", "    \"pipeline/draft_flow.py\", \"pipeline/edits/runner.py\",", "    \"pipeline/edits/runner.py\","),
    ("n20 AGENTS.md 를 규칙 문서 목록에서 뺌", "SAFETY_GUARD_DOCS = (\"docs/SECURITY_GUARDRAILS.md\", \"AGENTS.md\", ", "SAFETY_GUARD_DOCS = (\"docs/SECURITY_GUARDRAILS.md\", "),
    ("n21 셸 따옴표 없는 명령 끄기", "    if any(hint.casefold().endswith(SHELL_SUFFIXES) for hint in hints) and _SHELL_NET_RE.search(text):", "    if False:"),
    ("n22 ru 도메인을 파일 이름 도메인으로", "FILE_NAME_TLDS = (\"py\", \"sh\", \"md\", \"rs\", \"pl\", \"so\", \"cc\", \"ps\", \"pm\", \"ml\")", "FILE_NAME_TLDS = (\"py\", \"sh\", \"md\", \"rs\", \"pl\", \"so\", \"cc\", \"ps\", \"pm\", \"ml\", \"ru\")"),
    ("n23 승인 글에서 str 하위 형식 허용", "    if type(text) is not str or not text.strip(_ASCII_SPACE):", "    if not isinstance(text, str) or not text.strip(_ASCII_SPACE):"),
    ("n24 README.md 를 내부 항목으로", "    \"AGENTS.md\", \"AI_COLLAB.md\", \"CLAUDE.md\", \"GEMINI.md\", \"HANDLER.md\", \"WORKLOG.md\", \"docs\",", "    \"README.md\", \"AGENTS.md\", \"AI_COLLAB.md\", \"CLAUDE.md\", \"GEMINI.md\", \"HANDLER.md\", \"WORKLOG.md\", \"docs\","),
    ("n25 failure 이어도 다음 병합 허용", "PostMergeDecision(state, False, POST_MERGE_REVERT_ACTIONS,", "PostMergeDecision(state, True, POST_MERGE_REVERT_ACTIONS,"),
    ("n26 ApprovalRecord 머리 비교 생략", "        elif explained != arrived:", "        elif False:"),
    ("n27 두 이름 동시 입력 허용", "        if changed_text is not None:\n            add_plain(\"invalid_input\", \"바뀐 줄의 글을 두 이름", "        if False:\n            add_plain(\"invalid_input\", \"바뀐 줄의 글을 두 이름"),
    ("n28 os.remove 낱말 규칙 삭제", "|(?<![A-Za-z0-9_])os[ \\t]*\\.[ \\t]*(?:remove|removedirs|rmdir)(?![A-Za-z0-9_])", ""),
    ("n29 Authorization 헤더 규칙 끄기", "    if not doc_only and _AUTH_HEADER_RE.search(text):", "    if False:"),
    ("n30 .py 를 문서 확장자로", "DOC_SUFFIXES = (\".md\", \".rst\", \".txt\", \".adoc\")", "DOC_SUFFIXES = (\".md\", \".rst\", \".txt\", \".adoc\", \".py\")"),
    ("n31 필수 검사 목록이 비어도 통과", "or not required or any(not isinstance(name, str) or not name.strip() for name in required):", "or any(not isinstance(name, str) or not name.strip() for name in required):"),
    ("n32 통과 못 한 검사 무시", "    if bad:\n        found.append(\"통과하지 않은 검사가 있습니다", "    if False:\n        found.append(\"통과하지 않은 검사가 있습니다"),
    ("n33 문서 사전 키가 변경 목록에 있는지 생략", "    return normal is not None and normal in paths and _is_doc_path(normal)", "    return normal is not None and _is_doc_path(normal)"),
    ("n34 트리 비교 생략", "    if verified != current:\n        return \"독립 검증한 내용", "    if False:\n        return \"독립 검증한 내용"),
    ("n35 글자 하나일 때 문서가 하나라도 있으면 면제", "        return bool(paths) and all(_is_doc_path(path) for path in paths)", "        return bool(paths) and any(_is_doc_path(path) for path in paths)"),
    ("n36 추가 줄만 아니라 면제 없이 시험 폴더 면제 확대(tests 안쪽도 면제)", "    return (len(parts) > 1 and parts[0] == \"tests\") or", "    return (len(parts) > 1 and \"tests\" in parts[:-1]) or"),
    ("n37 안전 목록 이름 비교를 대소문자 구분으로", "    folded = path.casefold()\n    if folded in _SAFETY_DOC_FILES", "    folded = path\n    if folded in _SAFETY_DOC_FILES"),
    ("n38 ads 경로 규칙 끄기", "        if base in _ADS_FILES or any(part in _ADS_DIRS for part in segments):", "        if False:"),
    ("n39 PR 제목 번호 확인에서 str 하위 형식 허용", "    if type(title) is not str:", "    if not isinstance(title, str):"),
    ("n40 병합 방식 str 하위 형식 허용", "    return type(method) is str and method == ALLOWED_MERGE_METHOD", "    return isinstance(method, str) and method == ALLOWED_MERGE_METHOD"),
]

results = []
for name, old, new in MUTS:
    if text0.count(old) != 1:
        results.append((name, "SKIP (old text count=%d)" % text0.count(old)))
        continue
    SRC.write_bytes(text0.replace(old, new).encode("utf-8"))
    try:
        p = subprocess.run([PY, "-I", "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-p", "test_merge_policy*.py"],
                           cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=600)
        tail = (p.stderr or "").strip().splitlines()[-1] if (p.stderr or "").strip() else ""
        results.append((name, ("KILLED   " if p.returncode != 0 else "SURVIVED ") + tail))
    finally:
        SRC.write_bytes(orig)
    if hashlib.sha256(SRC.read_bytes()).hexdigest() != H0:
        print("RESTORE FAILED")
        sys.exit(1)
    print("%-70s %s" % (results[-1][0], results[-1][1]), flush=True)

print("restored sha256 equal:", hashlib.sha256(SRC.read_bytes()).hexdigest() == H0)
print("survivors:", [n for n, r in results if r.startswith("SURVIVED")])
print("skipped:", [n for n, r in results if r.startswith("SKIP")])
print("killed: %d / %d" % (sum(1 for n, r in results if r.startswith("KILLED")), len(MUTS)))
