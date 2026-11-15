"""변이 시험 도구 — 작업 폴더의 일부를 임시 폴더(mut_tree)로 복사해 한 번에 한 곳씩 일부러 틀리게 하고, 새 시험 두 모듈이 빨개지는지 본다. 원복 뒤 sha256 이 같은지도 확인한다.
작업 폴더는 읽기만 한다(쓰지 않는다). 사용: mutate.py [--only ID,ID] [--list]  — 결과는 mutation_results.txt 와 표준 출력.
시험은 한 번에 하나(시작 전 memfree 0.6)."""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

REPO = "C:/work/ai/verify_mp1_T/tree_lf"
HERE = "C:/work/ai/verify_mp1_T"
WORK = HERE + "/mut_tree3"
PY = "<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe"
MEMFREE = "C:/work/ai/audit6/n2/tools/memfree.py"
MOD = "pipeline/merge_policy.py"
DOC = "docs/AI_MERGE_POLICY.md"


def M(mid, area, what, old, new, path=MOD):
    return {"id": mid, "area": area, "what": what, "path": path, "old": old, "new": new}


def A(mid, area, what, path, text):
    """파일 끝에 글을 덧붙이는 변이(연결·부작용 시험용)."""
    return {"id": mid, "area": area, "what": what, "path": path, "append": text}


NL = "\n"
OUT_NAME = "mutation_results_v.txt"
MUTANTS = [
    # ---- 승인 글 읽기 ----
    M("A01", "승인 글", "불허 문구를 승인으로 인정", """        return ApprovalCheck(None, "rejected_phrase", "'확인했습니다'·'진행하세요' 같은 말만으로는 병합 승인으로 보지 않습니다. " + _APPROVAL_GUIDE)""",
      """        return ApprovalCheck("M075", "ok", "")"""),
    M("A02", "승인 글", "번호 없는 승인 인정", """        return ApprovalCheck(None, "no_number", "승인에 병합 번호가 없습니다. " + _APPROVAL_GUIDE)""", """        return ApprovalCheck("M075", "ok", "")"""),
    M("A03", "승인 글", "번호가 둘 이상인 글을 첫 번호로 인정", """        return ApprovalCheck(None, "several_numbers", "번호가 둘 이상 들어 있어 어느 병합인지 알 수 없습니다. " + _APPROVAL_GUIDE)""",
      """        return ApprovalCheck(numbers[0].upper(), "ok", "")"""),
    M("A04", "승인 글", "번호 뒤에 다른 말이 붙어도 인정(fullmatch → match)", "    match = _APPROVAL_RE.fullmatch(body)", "    match = _APPROVAL_RE.match(body)"),
    M("A05", "승인 글", "표준이 아닌 번호(M0075·M000) 인정", 'MERGE_NUMBER_DIGITS = r"(?:(?!000)[0-9]{3}|[1-9][0-9]{3})"', 'MERGE_NUMBER_DIGITS = r"(?:[0-9]{3,4})"'),
    M("A06", "승인 글", "소문자 m 거절(승인 인정을 더 좁게)", '_APPROVAL_RE = re.compile(r"[Mm](" + MERGE_NUMBER_DIGITS', '_APPROVAL_RE = re.compile(r"M(" + MERGE_NUMBER_DIGITS'),
    M("A07", "승인 글", "번호와 승인 사이 공백 없이도 인정", r'''+ r")[ \t]+승인\.?")''', r'''+ r")[ \t]*승인\.?")'''),
    M("A08", "승인 글", "번호와 승인 사이 줄 바꿈도 인정", r'''+ r")[ \t]+승인\.?")''', r'''+ r")\s+승인\.?")'''),
    M("A09", "승인 글", "끝의 마침표를 여러 개 인정", r'''+ r")[ \t]+승인\.?")''', r'''+ r")[ \t]+승인\.*")'''),
    M("A10", "승인 글", "앞뒤 공백을 모든 유니코드 공백으로 확대(strip 인자 제거)", "    body = text.strip(_ASCII_SPACE)\n    if len(body) > APPROVAL_TEXT_MAX:", "    body = text.strip()\n    if len(body) > APPROVAL_TEXT_MAX:"),
    # ---- 승인의 유효성 ----
    M("B01", "유효성", "SHA 비교 생략(승인 뒤 커밋 추가 허용)", "    if approved_sha is None or current_sha is None or approved_sha != current_sha:", "    if approved_sha is None or current_sha is None:"),
    M("B02", "유효성", "변경 파일 목록 비교 생략", "len(approved_set) > 0 and approved_set == current_set", "len(approved_set) > 0"),
    M("B03", "유효성", "번호 비교 생략", "    return approved is not None and approved == _standard_label(pr_number_label)", "    return approved is not None"),
    M("B04", "유효성", "한 번 쓴 승인 번호 재사용 허용", "        if number in self._numbers:", "        if False:"),
    M("B05", "유효성", "이미 승인으로 처리한 PR 의 두 번째 승인 허용", "        if pr_number in self._prs:", "        if False:"),
    M("B06", "유효성", "PR 제목에 번호 태그가 둘이어도 인정", "    if len(tags) != 1 or not title.startswith(tags[0]):", "    if len(tags) < 1 or not title.startswith(tags[0]):"),
    M("B07", "유효성", "빈 변경 파일 목록의 승인을 유효로", "len(approved_set) > 0 and approved_set == current_set", "approved_set == current_set"),
    # ---- 변경 분류 ----
    M("C01", "분류", ".github 를 허용", '    if ".github" in segments:', '    if False and ".github" in segments:'),
    M("C02", "분류", "declared 미응답을 통과로", "                if value is False:\n                    continue", "                if value is not True:\n                    continue"),
    M("C03", "분류", "알 수 없는 저장소 종류를 그냥 분류", "    kind_ok = isinstance(repo_kind, str) and repo_kind in REPO_KINDS", "    kind_ok = True"),
    M("C04", "분류", "키·토큰·비밀번호 낱말 규칙 제거", "    if _CRED_WORD_RE.search(text):", "    if False:"),
    M("C05", "분류", "adsbygoogle·ca-pub- 규칙 제거", "    if _ADS_TEXT_RE.search(text):", "    if False:"),
    M("C06", "분류", "의존성 파일·vendor 허용", '    if "vendor" in segments or "node_modules" in segments or _DEPENDENCY_BASE_RE.fullmatch(base) is not None:', "    if False:"),
    M("C07", "분류", "공개 글(_posts 등) 허용", '        if any(part in _PUBLIC_DIRS for part in segments) or segments[0] == "assets" or', "        if False and any(part in _PUBLIC_DIRS for part in segments) or segments[0] == \"assets\" or"),
    M("C08", "분류", "정책 파일 자체 변경 허용", "    if path.casefold() in _POLICY_SELF_FOLDED:", "    if False:"),
    M("C09", "분류", "경로의 .. 구간 허용", "            return None\n        parts.append(segment)", "            continue\n        parts.append(segment)"),
    M("C10", "분류", "경로 대소문자를 구분(casefold 제거)", '    segments = [part.casefold() for part in path.split("/")]', '    segments = [part for part in path.split("/")]'),
    M("C11", "분류", "빈 변경 파일 목록을 ai_ok 로", "    elif not paths:", "    elif False:"),
    M("C12", "분류", "상수 DECLARED_REQUIRED 에서 main 보호 설정 삭제", '"provider_activation", "publish_mode", "branch_protection")', '"provider_activation", "publish_mode")'),
    M("C13", "분류", "비밀 값 모양 규칙 제거", "    for label, rx in _SECRET_VALUE_RES:\n        if rx.search(text):", "    for label, rx in ():\n        if rx.search(text):"),
    M("C14", "분류", "PIPELINE_PAUSE 낱말 규칙 제거", "    if _PAUSE_TEXT_RE.search(text):", "    if False:"),
    M("C15", "분류", "발행 설정 파일(blogs.json 등) 허용", '        for code in _BLOG_SETTINGS.get("/".join(segments), ()):', "        for code in ():"),
    M("C16", "분류", "삭제·마이그레이션 낱말 규칙 제거", "    if _DESTRUCTIVE_TEXT_RE.search(text):", "    if False:"),
    M("C17", "분류", "선언의 알 수 없는 항목 이름 허용", "        if any(key not in _ITEM_LABELS for key in given):", "        if False:"),
    M("C18", "분류", "비밀 낱말 token 규칙을 복수형까지 넓히기가 아니라 token 을 제거", '|token(?![A-Za-z0-9])"', '"'),
    M("C19", "분류", "경로의 역슬래시를 슬래시로 바꾸지 않음", r'''    text = raw.strip().replace("\\", "/")''', r'''    text = raw.strip()'''),
    M("C20", "분류", "키·인증서 파일 확장자 규칙 제거", "    if base.endswith(_CRED_SUFFIXES) or _CRED_BASE_RE.fullmatch(base) is not None or", "    if False and base.endswith(_CRED_SUFFIXES) or _CRED_BASE_RE.fullmatch(base) is not None or"),
    M("C21", "분류", "security 폴더 규칙 제거", ' or "security" in segments or any(word in part', " or any(word in part"),
    M("C22", "분류", "이름에 secret·credential 이 든 경로 규칙 제거", " or any(word in part for part in segments for word in _CRED_WORDS):", ":"),
    M("C23", "분류", "데스크톱 패키징 폴더 규칙 제거", "base.endswith(_PACKAGING_SUFFIXES) or any(part in _PACKAGING_DIRS for part in segments):", "base.endswith(_PACKAGING_SUFFIXES):"),
    M("C24", "분류", "데스크톱 VERSION 파일 규칙 제거", "        if base in _PACKAGING_FILES or base.endswith(_PACKAGING_SUFFIXES)", "        if base.endswith(_PACKAGING_SUFFIXES)"),
    M("B08", "유효성", "원장이 쓴 번호 목록을 비워서 돌려줌", "        return tuple(sorted(self._numbers))", "        return ()"),
    M("B09", "유효성", "PR 제목의 비표준 번호([M75])도 번호로 돌려줌", "    return _standard_label(tags[0][1:-1])", "    return tags[0][1:-1]"),
    # ---- 병합 직전 재확인 ----
    M("D01", "재확인", "누락 값을 통과로(_need)", "    absent = [key for key in keys if facts.get(key) is None]", "    absent = []"),
    M("D02", "재확인", "충돌 여부 모름을 통과로", '    return "충돌 여부를 알 수 없습니다(값이 없거나 참·거짓이 아닙니다)"', "    return None"),
    M("D03", "재확인", "건너뜀·중립 검사를 통과로", '        elif item.get("conclusion") != "success":', '        elif item.get("conclusion") not in ("success", "skipped", "neutral"):'),
    M("D04", "재확인", "검증자와 구현자가 같아도 통과", "    if verifier.strip().casefold() == implementer.strip().casefold():", "    if False:"),
    M("D05", "재확인", "독립 검증 트리 비교 생략", "    if verified != current:", "    if False:"),
    M("D06", "재확인", "필수 지적이 남아도 통과", "    if open_findings != 0:", "    if False:"),
    M("D07", "재확인", "운영자 전용 분류여도 통과", "    if classified.tier != TIER_AI_OK or classified.categories or classified.extra_flags:", "    if False:"),
    M("D08", "재확인", "낡은 분류(파일 목록이 다른 분류) 통과", "    if frozenset(classified.paths) != current:", "    if False:"),
    M("D09", "재확인", "비밀 발견이 있어도 통과", "    if value != 0:", "    if False:"),
    M("D10", "재확인", "구체적이지 않은 되돌리기 방법도 통과", "    if len(body) < ROLLBACK_MIN_CHARS or body.casefold() in _ROLLBACK_PLACEHOLDERS:", "    if False:"),
    M("D11", "재확인", "승인 이후 커밋 추가를 통과", '    if approved != current:\n        return "승인한 뒤에', '    if False:\n        return "승인한 뒤에'),
    M("D12", "재확인", "승인 번호와 PR 번호 불일치를 통과", "    if not approval_matches(approved, label):", "    if False:"),
    M("D13", "재확인", "확인 중 예외를 통과로", '                reason = "확인하는 중 예상하지 못한 오류가 나 실패로 처리합니다"', "                reason = None"),
    M("D14", "재확인", "이미 쓴 승인의 재사용 통과", "    if approved in consumed:", "    if False:"),
    M("D15", "재확인", "검사 결과가 하나도 없어도 통과", "    if not isinstance(checks, (list, tuple)) or not checks:", "    if not isinstance(checks, (list, tuple)):"),
    M("D16", "재확인", "승인 때 PR 번호와 지금 PR 번호 불일치 통과", "    if approved_pr != pr_number:", "    if False:"),
    M("D17", "재확인", "비밀 모양 검사 결과가 없어도 통과(누락=통과)", '    if value is None:\n        return "비밀 모양 검사 결과가 없습니다"', "    if value is None:\n        return None"),
    M("D18", "재확인", "되돌리는 방법 문장이 없어도 통과(누락=통과)", '    if not isinstance(text, str):\n        return "되돌리는 방법 문장이 없습니다"', "    if not isinstance(text, str):\n        return None"),
    M("D19", "재확인", "독립 검증 기록이 없어도 통과(누락=통과)", '    problem = _need(facts, "independent_verification", "current_tree")\n    if problem:\n        return problem', '    problem = _need(facts, "independent_verification", "current_tree")\n    if problem:\n        return None'),
    M("D20", "재확인", "변경 분류가 없어도 통과(누락=통과)", '    problem = _need(facts, "approved_paths", "current_paths", "classification")\n    if problem:\n        return problem', '    problem = _need(facts, "approved_paths", "current_paths", "classification")\n    if problem:\n        return None'),
    M("D21", "재확인", "검사 결과가 없어도 통과(누락=통과)", '    problem = _need(facts, "checks")\n    if problem:\n        return problem', '    problem = _need(facts, "checks")\n    if problem:\n        return None'),
    # ---- 병합 방식 ----
    M("E01", "병합 방식", "push_main 허용", "    return isinstance(method, str) and method == ALLOWED_MERGE_METHOD", '    return isinstance(method, str) and method in (ALLOWED_MERGE_METHOD, "push_main")'),
    M("E02", "병합 방식", "모든 글자 값 허용", "    return isinstance(method, str) and method == ALLOWED_MERGE_METHOD", "    return isinstance(method, str)"),
    M("E03", "병합 방식", "대소문자·공백을 고쳐 읽어 허용", "    return isinstance(method, str) and method == ALLOWED_MERGE_METHOD", "    return isinstance(method, str) and method.strip().lower() == ALLOWED_MERGE_METHOD"),
    M("E04", "병합 방식", "상수 FORBIDDEN_MERGE_METHODS 에서 force_push 삭제", 'FORBIDDEN_MERGE_METHODS = ("push_main", "direct_push", "force_push")', 'FORBIDDEN_MERGE_METHODS = ("push_main", "direct_push")'),
    # ---- 쉬운 병합 설명 ----
    M("F01", "설명", "점검표 '예'를 무시", '            if value != "아니오":', "            if False:"),
    M("F02", "설명", "6항목 중 마지막 항목 점검 생략", "    for item in EXPLANATION_ITEMS:\n        answers = _label_lines(lines, item)", "    for item in EXPLANATION_ITEMS[:-1]:\n        answers = _label_lines(lines, item)"),
    M("F03", "설명", "승인 예 번호와 첫 줄 번호 불일치 무시", "    elif number is not None and examples[0] != number:", "    elif False:"),
    M("F04", "설명", "글 속 다른 번호의 승인 문구 무시", "        if stray:", "        if False:"),
    M("F05", "설명", "PR 제목 번호 불일치 무시", "        if pr_title is not None and pr_title_label(pr_title) != number:", "        if False:"),
    M("F06", "설명", "보이지 않는 글자 허용(설명)", '    if _INVISIBLE_RE.search(text):\n        problems.append("보이지 않는 글자(방향을 바꾸는 글자·너비 없는 글자)가 들어 있습니다")\n    lines = _split_lines(text)\n    nonblank',
      '    if False:\n        problems.append("보이지 않는 글자(방향을 바꾸는 글자·너비 없는 글자)가 들어 있습니다")\n    lines = _split_lines(text)\n    nonblank'),
    M("F07", "설명", "render 가 줄 바꿈을 접지 않음", '    text = _INVISIBLE_RE.sub("", " ".join(value.split()))', '    text = _INVISIBLE_RE.sub("", value)'),
    M("F08", "설명", "변경 파일 개수 불일치 무시", "        elif declared_count != len(listed):", "        elif False:"),
    M("F09", "설명", "한글 문장 검사 생략", "    if len(answer) < ANSWER_MIN_CHARS or len(_HANGUL_RE.findall(answer)) < ANSWER_MIN_HANGUL:", "    if len(answer) < ANSWER_MIN_CHARS:"),
    M("F10", "설명", "병합 방식 줄 점검 생략", "    if len(ways) != 1 or (AI_MERGE_OFF_NOTICE not in ways[0] and AI_MERGE_ON_NOTICE not in ways[0]):", "    if False:"),
    M("F11", "설명", "상수 EXPLANATION_ITEMS 에서 되돌리기 삭제", '"위험은 무엇인가요?", "검사 결과", "되돌리기")', '"위험은 무엇인가요?", "검사 결과")'),
    M("F12", "설명", "점검표에 빠진 항목 무시", '            if name not in table:\n                problems.append("점검표에 빠진 항목: " + name)', '            if False:\n                problems.append("점검표에 빠진 항목: " + name)'),
    M("F13", "설명", "승인 안내 줄 점검 생략", "    if lines.count(APPROVAL_GUIDE_LINE) != 1:", "    if False:"),
    M("F14", "설명", "같은 항목이 두 번 나와도 통과", "        elif len(answers) > 1:", "        elif False:"),
    M("F15", "설명", "render 가 경로의 보이지 않는 글자를 거절하지 않음", "    if any(_INVISIBLE_RE.search(path) for path in paths):", "    if False:"),
    M("F16", "설명", "render 가 제어 문자를 지우지 않음", '    text = "".join(ch for ch in text if ord(ch) >= 32 and ord(ch) != 127)', "    text = text"),
    M("F17", "설명", "대상 PR 번호 0 허용", "    if len(prs) != 1 or int(prs[0]) < 1:", "    if len(prs) != 1:"),
    M("F18", "설명", "머리 커밋 점검 생략", "    if len(commits) != 1:", "    if False:"),
    M("F19", "설명", "첫 줄 번호의 표준 모양 점검 생략", "    number = head.group(1) if head is not None and _standard_label(head.group(1)) is not None else None", "    number = head.group(1) if head is not None else None"),
    M("F20", "설명", "점검표 값이 빈 글이어도 통과(예 뿐 아니라 알 수 없는 값도 허용)", '            if value != "아니오":', '            if value == "예":'),
    # ---- 병합 완료 알림 ----
    M("G01", "완료 알림", "7항목 중 마지막 항목을 안 봄", "    for item in COMPLETION_ITEMS:\n        values = _labeled_values(lines, item)", "    for item in COMPLETION_ITEMS[:-1]:\n        values = _labeled_values(lines, item)"),
    M("G02", "완료 알림", "빈 값 허용", "        if not value:", "        if False:"),
    M("G03", "완료 알림", "병합 번호 모양 점검 생략", '        elif item == "병합 번호" and _standard_label(value) is None:', "        elif False:"),
    M("G04", "완료 알림", "콜론 없는 줄도 항목으로 인정", '            if rest and rest[0] in ":：":', "            if rest:"),
    M("G05", "완료 알림", "중복 항목 허용", "        if len(values) > 1:", "        if False:"),
    M("G06", "완료 알림", "상수 COMPLETION_ITEMS 에서 이상 유무 삭제", '"main 검사 결과", "이상 유무", "원복 Commit 또는 원복 방법")', '"main 검사 결과", "원복 Commit 또는 원복 방법")'),
    M("G07", "완료 알림", "병합된 Commit 해시 모양 점검 생략", '        elif item == "병합된 Commit" and _COMMIT_VALUE_RE.fullmatch(value) is None:', "        elif False:"),
    M("G08", "완료 알림", "PR 번호 0 허용", '        elif item == "PR 번호" and int(value.lstrip("#")) < 1:', "        elif False:"),
    M("G09", "완료 알림", "보이지 않는 글자 허용(알림)", '    if _INVISIBLE_RE.search(text):\n        problems.append("보이지 않는 글자(방향을 바꾸는 글자·너비 없는 글자)가 들어 있습니다")\n    lines = _split_lines(text)\n    for item in COMPLETION_ITEMS:',
      '    if False:\n        problems.append("보이지 않는 글자(방향을 바꾸는 글자·너비 없는 글자)가 들어 있습니다")\n    lines = _split_lines(text)\n    for item in COMPLETION_ITEMS:'),
    # ---- 첫 운영 3건 시험 ----
    M("H01", "시험 3건", "한 건 위반에도 continue", "    if violations:\n        return TrialReport(TRIAL_STOP", "    if len(violations) > 1:\n        return TrialReport(TRIAL_STOP"),
    M("H02", "시험 3건", "3건 미만도 continue", "    if len(seen) < TRIAL_SIZE or unknown:", "    if unknown:"),
    M("H03", "시험 3건", "main 검사 결과 모름을 continue 로", "    if len(seen) < TRIAL_SIZE or unknown:", "    if len(seen) < TRIAL_SIZE:"),
    M("H04", "시험 3건", "키가 없는 기록을 충족으로", "            value = record.get(key, _ABSENT)", "            value = record.get(key, True)"),
    M("H05", "시험 3건", "같은 번호 두 번 기록 허용", "        elif number in seen:", "        elif False:"),
    M("H06", "시험 3건", "모든 기준에서 None 을 모름으로 허용", '            if key == "main_checks_passed" and value is None:', "            if value is None:"),
    M("H07", "시험 3건", "상수 TRIAL_CRITERIA 에서 항목 삭제", '    ("no_operator_only_path_change", "운영자 전용 경로 변경 0건"),\n)', ")"),
    M("H08", "시험 3건", "시험 건수 TRIAL_SIZE 를 2 로", "TRIAL_SIZE = 3", "TRIAL_SIZE = 2"),
    M("H09", "시험 3건", "표준이 아닌 번호의 기록을 그냥 셈", "        if _standard_label(number) is None:\n            violations.append(name + \": 병합 번호가 표준 모양이 아닙니다\")\n        elif number in seen:",
      "        if False:\n            violations.append(name + \": 병합 번호가 표준 모양이 아닙니다\")\n        elif number in seen:"),
    M("H10", "시험 3건", "기록이 목록이 아니어도 평가 시도", "    if not isinstance(records, (list, tuple)):", "    if False:"),
    # ---- 상수(운영자 원문 목록) ----
    M("I01", "상수", "운영자 전용 12항목에서 Main Branch 보호 설정 삭제", '    ("branch_protection", "Main Branch 보호 설정"),\n', ""),
    M("I02", "상수", "재확인 8조건에서 원복 방법 확인 삭제", '    ("rollback_confirmed", "원복 방법 확인"),\n', ""),
    M("I03", "상수", "불허 문구 5개에서 다음 단계 진행 삭제", ', "기본값대로", "다음 단계 진행")', ', "기본값대로")'),
    M("I04", "상수", "AI 병합 가능 7종에서 접근성·성능 개선 삭제", ', "오류 수정", "접근성·성능 개선")', ', "오류 수정")'),
    M("I05", "상수", "운영자 전용 항목 이름을 바꿔치기", '("provider_activation", "Provider 활성화")', '("provider_activation", "Provider 켜기")'),
    M("I06", "상수", "FACT_KEYS 에서 rollback_method 삭제", '"secret_findings", "rollback_method",\n)', '"secret_findings",\n)'),
    M("I07", "상수", "운영자 전용 12항목에서 광고 항목 삭제", '    ("ads", "광고·AdSense·ads.txt"),\n', ""),
    M("I08", "상수", "저장소 종류에서 desktop 삭제", 'REPO_KINDS = ("blog", "desktop")', 'REPO_KINDS = ("blog",)'),
    M("I09", "상수", "정책 파일 목록에서 문서 시험 파일 삭제", ', "tests/test_merge_policy.py", "tests/test_merge_policy_docs.py")', ', "tests/test_merge_policy.py")'),
    M("I10", "상수", "되돌리기 방법 최소 글자 수를 1 로", "ROLLBACK_MIN_CHARS = 10", "ROLLBACK_MIN_CHARS = 1"),
    M("I11", "상수", "설명 항목 최소 글자 수를 1 로", "ANSWER_MIN_CHARS = 8", "ANSWER_MIN_CHARS = 1"),
    # ---- 문서(docs/AI_MERGE_POLICY.md) ----
    M("J01", "문서", "§8 의 main 직접 push 금지 문구 삭제", "- **main 직접 push 금지.**", "- **직접 올리는 방식 제한.**", DOC),
    M("J02", "문서", "§5-2 에서 불허 문구 하나 삭제", "- 진행하세요\n", "", DOC),
    M("J03", "문서", "상태를 켜져 있음으로 바꿈", "**상태: 꺼져 있음.**", "**상태: 켜져 있음.**", DOC),
    M("J04", "문서", "§7-2 표에서 12번 행 삭제", "| 12 | Main Branch 보호 설정 | 사람의 선언(워크플로 파일은 1번에서 걸림) |\n", "", DOC),
    M("J05", "문서", "§4-2 예시의 승인 예 번호를 바꿈", "승인 예: M075 승인\n```", "승인 예: M076 승인\n```", DOC),
    M("J06", "문서", "§11-1 에서 별도 병합 요청 문구 삭제", "AI 병합을 실제로 켜는 변경은 **별도 병합 요청**으로 보내고", "AI 병합을 실제로 켜는 변경은 **따로 요청**으로 보내고", DOC),
    M("J07", "문서", "§9 알림 예시의 이상 유무를 바꿈", "이상 유무: 이상 없음", "이상 유무: 있음", DOC),
    M("J08", "문서", "§6 표에서 조건 하나(충돌 없음) 삭제", "| 5 | 충돌 없음 | 충돌 여부가 정확히 거짓(모르면 실패) |\n", "", DOC),
    M("J09", "문서", "§10 에서 즉시 중지 규칙 문구를 약하게", "**즉시 중지 규칙:** 문제가 한 건이라도 발생하면 AI 병합을 **즉시 중지**하고", "**참고:** 문제가 한 건이라도 발생하면 AI 병합을 조정하고", DOC),
    M("J10", "문서", "머리의 꺼져 있음 표시 삭제", "> **지금 이 정책은 꺼져 있음** — ", "> **지금 이 정책은 사용 중** — ", DOC),
    M("J11", "문서", "§9 의 '추가 변경 자동 병합 금지' 약속을 뒤집음", "**main 검사에서 문제가 나오면** 추가 변경을 자동 병합하지 않습니다.", "**main 검사에서 문제가 나오면** 추가 변경도 이어서 병합합니다.", DOC),
    M("J12", "문서", "§8 의 운영자 PC Git 자격 증명 금지 문장 삭제", "AI 가 운영자 PC 의 Git 자격 증명을 이용해 main 에 직접 push 하는 방식은 쓰지 않습니다.", "직접 올리는 방식은 쓰지 않습니다.", DOC),
    M("J13", "문서", "§5-4 의 '기존 승인은 무효' 를 약하게", "기존 승인은 **무효**이고, 새 설명과 새 승인을 받아야 합니다", "기존 승인은 **참고**이고, 새 설명과 새 승인을 받아야 합니다", DOC),
    M("J14", "문서", "§10 의 '운영자 직접 병합으로 돌아감' 약속을 뒤집음", "**즉시 중지**하고 기존 운영자 직접 병합 방식으로 돌아갑니다.", "**즉시 중지**하고 그대로 계속 씁니다.", DOC),
    M("J15", "문서", "§11-2 의 '병합 자격 증명을 갖지 않음' 설계 원칙을 뒤집음", "**AI 세션은 병합 자격 증명을 갖지 않습니다.**", "**AI 세션이 병합 자격 증명을 씁니다.**", DOC),
    M("J16", "문서", "§7-6 의 '시험 폴더도 면제하지 않습니다' 문장 삭제", "- **시험 폴더도 면제하지 않습니다.** 안전 장치를 지키는 시험이 바로 이 파일들이라, 시험을 고쳐 장치를 약하게 만드는 길을 막습니다.\n", "", DOC),
    M("J17", "문서", "§7-5 표 external_connection 행의 보수적 판단 출처 문구 삭제", "| `external_connection` | 새 외부 접속 코드(§7-6) | 운영자 결정 D-347 의 보수적 판단(총괄 11-15) — ", "| `external_connection` | 새 외부 접속 코드(§7-6) | ", DOC),
    M("J18", "문서", "§7-6 의 '예시 주소는 걸리지 않습니다' 문장을 반대로", "**예시 주소는 걸리지 않습니다**", "**예시 주소도 걸립니다**", DOC),
    M("J19", "문서", "결함 대장 D-347 을 열림으로 되돌림", "**해결**(보수적 판단 — 총괄 2026-11-15", "**열림**(보수적 판단 — 총괄 2026-11-15", "docs/DEFECT_REGISTER.md"),
    M("J20", "문서", "§7-6 네트워크 모듈 목록에서 socket 한 낱말 삭제", "`http.server`·`socket`·`socketserver`", "`http.server`·`socketserver`", DOC),
    M("J21", "문서", "§7-6 스킴 목록에서 tg 삭제", "`git`·`tg`·`smtp`", "`git`·`smtp`", DOC),
    M("J22", "문서", "§7-6 의 '모두 시험·문서일 때만 건너뜁니다' 면제 규칙을 느슨하게", "바뀐 파일이 **모두** 시험·문서일 때만 건너뜁니다", "바뀐 파일 중 하나라도 시험·문서면 건너뜁니다", DOC),
    # ---- 12항목 밖 표시: 안전 장치 파일(safety_guard) ----
    M("S01", "안전 장치", "새 표시를 빼기 — safety_guard 를 붙이지 않음", "    elif _is_safety_path(segments, base, path):", "    elif False:"),
    M("S02", "안전 장치", "낱말 일부 삭제(egress)", 'SAFETY_GUARD_WORDS = ("validate_repo", "guardrail", "guard", "security", "secret", "egress", "policy",', 'SAFETY_GUARD_WORDS = ("validate_repo", "guardrail", "guard", "security", "secret", "policy",'),
    M("S03", "안전 장치", "시험 파일만 면제하는 실수(tests 폴더 면제)", "    return any(word in part for part in segments for word in SAFETY_GUARD_WORDS)", '    return segments[0] != "tests" and any(word in part for part in segments for word in SAFETY_GUARD_WORDS)'),
    M("S04", "안전 장치", "이름이 정해진 문서 한 파일 규칙 삭제", "    if path.casefold() in _SAFETY_DOC_FILES:\n        return True", "    if False:\n        return True"),
    M("S05", "안전 장치", "문서 면제 삭제(모든 문서가 낱말에 걸림)", "    if base.endswith(DOC_SUFFIXES):\n        return False\n    return any(word in part for part in segments for word in SAFETY_GUARD_WORDS)", "    return any(word in part for part in segments for word in SAFETY_GUARD_WORDS)"),
    M("S06", "안전 장치", "정책 파일에 policy_self 와 safety_guard 를 함께 붙임(elif → if)", "    elif _is_safety_path(segments, base, path):", "    if _is_safety_path(segments, base, path):"),
    M("S07", "안전 장치", "낱말을 파일 이름에만 적용(폴더 구간 무시)", "    return any(word in part for part in segments for word in SAFETY_GUARD_WORDS)", "    return any(word in base for word in SAFETY_GUARD_WORDS)"),
    M("S08", "안전 장치", "문서 한 파일 규칙의 대소문자 구분", "    if path.casefold() in _SAFETY_DOC_FILES:", "    if path in SAFETY_GUARD_DOCS:"),
    M("S09", "안전 장치", "상수 EXTRA_FLAGS 에서 safety_guard 삭제", '    ("safety_guard", "안전 장치 파일"),\n', ""),
    M("S10", "안전 장치", "상수 SAFETY_GUARD_DOCS 를 비움", 'SAFETY_GUARD_DOCS = ("docs/SECURITY_GUARDRAILS.md",)', "SAFETY_GUARD_DOCS = ()"),
    # ---- 12항목 밖 표시: 새 외부 접속 코드(external_connection) ----
    M("X01", "외부 접속", "새 표시를 빼기 — 외부 접속 검사를 부르지 않음", "        for why in _external_findings(_added_text_items(added_text), paths):", "        for why in ():"),
    M("X02", "외부 접속", "패턴 일부 삭제: 네트워크 모듈 socket", '"http.server", "socket", "socketserver", "ssl",', '"http.server", "socketserver", "ssl",'),
    M("X03", "외부 접속", "패턴 일부 삭제: 서비스 SDK openai", '"google_auth_oauthlib", "openai", "anthropic",', '"google_auth_oauthlib", "anthropic",'),
    M("X04", "외부 접속", "시험 파일 면제 실수(이름에 test 가 든 모든 경로 면제)", '    return (len(parts) > 1 and parts[0] == "tests") or parts[-1].casefold().endswith(DOC_SUFFIXES)', '    return "test" in path or parts[-1].casefold().endswith(DOC_SUFFIXES)'),
    M("X05", "외부 접속", "글자 하나 면제 착오(코드 파일이 섞여도 건너뜀)", "            if paths and not code_paths:\n                continue", "            if paths and len(code_paths) < len(paths):\n                continue"),
    M("X06", "외부 접속", "사전 형식에서 파일별 면제 무시", "            if normal is not None and _external_exempt(normal):\n                continue", "            if False:\n                continue"),
    M("X07", "외부 접속", "예시 주소 면제 삭제", '    return host in EXAMPLE_HOSTS or host.endswith(tuple("." + name for name in EXAMPLE_HOSTS)) or host.rsplit(".", 1)[-1] in EXAMPLE_TOP_LEVELS', "    return False"),
    M("X08", "외부 접속", "예시 하위 주소를 점 없이 비교(notexample.com 면제 실수)", 'host.endswith(tuple("." + name for name in EXAMPLE_HOSTS))', "host.endswith(EXAMPLE_HOSTS)"),
    M("X09", "외부 접속", "루프백(localhost)을 예시로 면제", "    return host in EXAMPLE_HOSTS or", '    return host in EXAMPLE_HOSTS or host in ("localhost", "127.0.0.1") or'),
    M("X10", "외부 접속", "스킴 일부 삭제(tg)", '"ssh", "git", "tg", "smtp",', '"ssh", "git", "smtp",'),
    M("X11", "외부 접속", "따옴표 안 도메인 이름 검사 삭제", "    for match in _QUOTED_HOST_RE.finditer(text):", "    for match in ():"),
    M("X12", "외부 접속", "널리 쓰는 서비스 도메인 검사 삭제", "    hosts += [match.group(0).lower() for match in _KNOWN_HOST_RE.finditer(text)]", "    hosts += []"),
    M("X13", "외부 접속", "도메인 접미사 gov 삭제", "|eu|gov|edu|", "|eu|edu|"),
    M("X14", "외부 접속", "동적 import·코드 실행 검사 삭제", "    if _DYNAMIC_RE.search(text):", "    if False:"),
    M("X15", "외부 접속", "네트워크 호출 모양 검사 삭제", "    if _NET_CALL_RE.search(text):", "    if False:"),
    M("X16", "외부 접속", "네트워크 명령 검사 삭제", "    if _NET_CLI_RE.search(text):", "    if False:"),
    M("X17", "외부 접속", "자바스크립트 네트워크 호출 검사 삭제", "    if any(hint.casefold().endswith(_JS_SUFFIXES) for hint in hints) and _JS_NET_RE.search(text):", "    if False:"),
    M("X18", "외부 접속", "from X import Y 의 하위 모듈(X.Y) 무시", '            found += [base + "." + item.strip("() \\t").split()[0] for item in names.split(",") if item.strip("() \\t")]', "            found += []"),
    M("X19", "외부 접속", "import a, b 의 둘째 모듈부터 무시", '            found += [item.split()[0] for item in plain.split(",") if item.strip()]', '            found += [plain.split(",")[0].split()[0]]'),
    M("X20", "외부 접속", "세미콜론으로 이은 문장 무시", '    for raw in re.split(r"[\\n;]", text):', '    for raw in re.split(r"[\\n]", text):'),
    M("X21", "외부 접속", "주소의 사용자 정보를 호스트로 착각", '    host = authority.rsplit("@", 1)[-1]', "    host = authority"),
    M("X22", "외부 접속", "빈 호스트(스킴만 적은 정규식 따위)도 걸리게", "        if host and not _is_example_host(host):", "        if not _is_example_host(host):"),
    M("X23", "외부 접속", "문서 확장자 .txt 면제 삭제", 'DOC_SUFFIXES = (".md", ".rst", ".txt", ".adoc")', 'DOC_SUFFIXES = (".md", ".rst", ".adoc")'),
    M("X24", "외부 접속", "상수 EXTERNAL_MODULES 에서 서비스 SDK 목록 빠짐", "EXTERNAL_MODULES = NETWORK_MODULES + SERVICE_SDK_MODULES", "EXTERNAL_MODULES = NETWORK_MODULES"),
    M("X25", "외부 접속", "상수 EXTRA_FLAGS 에서 external_connection 삭제", '    ("external_connection", "새 외부 접속 코드"),\n', ""),
    M("X26", "외부 접속", "예시 최상위 이름(.test) 면제 삭제", 'EXAMPLE_TOP_LEVELS = ("example", "test", "invalid")', 'EXAMPLE_TOP_LEVELS = ("example", "invalid")'),
    # ---- 정적 성질(순수성·미연결) ----
    M("L01", "정적", "모듈에 import os 추가", "import re\nfrom dataclasses import dataclass\n", "import os\nimport re\nfrom dataclasses import dataclass\n"),
    M("L02", "정적", "모듈 함수에 print 호출 추가", 'def _clip(text, limit):\n    text = " ".join(str(text).split())', 'def _clip(text, limit):\n    print(text)\n    text = " ".join(str(text).split())'),
    A("L03", "정적", "다른 모듈(operator_loop)이 정책 모듈을 import", "pipeline/operator_loop.py", "\nfrom pipeline import merge_policy  # noqa: E402\n"),
    A("L04", "정적", "모듈 맨 끝에 import 시점 실행 줄 추가", MOD, '\nprint("loaded")\n'),
    M("L05", "정적", "모듈에 환경 변수 읽기 추가", 'def _clip(text, limit):\n    text = " ".join(str(text).split())', 'def _clip(text, limit):\n    text = " ".join(str(text).split()) + str(__import__("os").environ)'),
    A("L06", "정적", "워크플로 파일이 정책 함수를 부름", ".github/workflows/pages.yml", "\n# parse_approval(\n"),
]


def _load_mine():
    import importlib.util
    spec = importlib.util.spec_from_file_location("my_mutants", HERE + "/my_mutants3.py")
    mod = importlib.util.module_from_spec(spec)
    mod.M, mod.A, mod.MOD, mod.DOC = M, A, MOD, DOC
    spec.loader.exec_module(mod)
    return mod.MY_MUTANTS


if "--mine" in sys.argv:
    MUTANTS = _load_mine()
    OUT_NAME = "mutation_results_mine3.txt"


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def setup():
    if os.path.exists(WORK):
        shutil.rmtree(WORK)
    ignore = shutil.ignore_patterns("__pycache__", ".git", "*.pyc")
    for sub in ("pipeline", "scripts", ".github"):
        shutil.copytree(REPO + "/" + sub, WORK + "/" + sub, ignore=ignore)
    os.makedirs(WORK + "/tests")
    for name in os.listdir(REPO + "/tests"):
        if name.endswith(".py"):
            shutil.copy2(REPO + "/tests/" + name, WORK + "/tests/" + name)
    os.makedirs(WORK + "/docs")
    for name in ("AI_MERGE_POLICY.md", "DEFECT_REGISTER.md"):
        shutil.copy2(REPO + "/docs/" + name, WORK + "/docs/" + name)
    for name in os.listdir(REPO):
        if name.endswith((".py", ".json", ".yml")) and os.path.isfile(REPO + "/" + name):
            shutil.copy2(REPO + "/" + name, WORK + "/" + name)


def run_tests():
    subprocess.run([sys.executable, "-X", "utf8", MEMFREE, "0.6"], capture_output=True)
    done = subprocess.run([PY, "-X", "utf8", "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_merge_policy*.py"], cwd=WORK, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)
    out = done.stdout + done.stderr
    ran = re.search(r"Ran (\d+) tests?", out)
    failed = re.findall(r"^(?:FAIL|ERROR): (\S+) \(([\w.]+)", out, re.M)
    return done.returncode, int(ran.group(1)) if ran else 0, failed, out


def compiles(path):
    done = subprocess.run([PY, "-X", "utf8", "-B", "-c", "import ast,sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())", path], capture_output=True, text=True)
    return done.returncode == 0


def main():
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    if "--list" in sys.argv:
        for mutant in MUTANTS:
            print(mutant["id"], mutant["area"], mutant["what"])
        print(len(MUTANTS), "mutants")
        return
    started = time.time()
    setup()
    for rel in {MOD, DOC, "pipeline/operator_loop.py", ".github/workflows/pages.yml"}:
        assert sha256(WORK + "/" + rel) == sha256(REPO + "/" + rel), rel
    code, ran, failed, out = run_tests()
    print("baseline: rc=%d ran=%d failed=%d" % (code, ran, len(failed)))
    if code != 0:
        print(out[-3000:])
        sys.exit(1)
    rows = []
    bad = 0
    for mutant in MUTANTS:
        if only and mutant["id"] not in only:
            continue
        path = WORK + "/" + mutant["path"]
        original = open(path, "rb").read()
        before = hashlib.sha256(original).hexdigest()
        if "append" in mutant:
            changed = original + mutant["append"].encode("utf-8")
            note = ""
        else:
            old, new = mutant["old"].encode("utf-8"), mutant["new"].encode("utf-8")
            count = original.count(old)
            if count != 1:
                rows.append((mutant, "SPEC INVALID (옛 글이 %d번 나옴)" % count, "-", "-", False))
                bad += 1
                print(mutant["id"], "SPEC INVALID occurs", count)
                continue
            changed = original.replace(old, new)
        open(path, "wb").write(changed)
        try:
            if mutant["path"].endswith(".py") and not compiles(path):
                result = "문법 오류(유효한 변이 아님)"
                bad += 1
                failed_classes, red = "-", False
            else:
                code, ran, failed, out = run_tests()
                red = code != 0
                classes = sorted({name.split(".")[1] if name.count(".") >= 2 else name for _test, name in failed})
                failed_classes = ", ".join(classes) if classes else "-"
                result = ("빨강 %d건" % len(failed)) if red else "**초록 — 시험이 못 잡음**"
                if not red:
                    bad += 1
        finally:
            open(path, "wb").write(original)
        after = sha256(path)
        same = after == before
        if not same:
            bad += 1
        rows.append((mutant, result, failed_classes, after[:12], same))
        print("%-4s %-8s %-28s %s | %s" % (mutant["id"], mutant["area"], result, failed_classes[:80], "원복 동일" if same else "원복 불일치!"))
    lines = ["# 변이 시험 결과 (mergepol1)", "", "작업 폴더는 읽기만 했고, 복사본(mut_tree)에서 한 번에 한 곳씩 일부러 틀리게 한 뒤 새 시험 두 모듈(test_merge_policy·test_merge_policy_docs)을 돌렸다. 원복 뒤 파일의 sha256 이 변이 전과 같은지 확인했다.", "",
             "| ID | 영역 | 변이 | 결과 | 빨개진 시험 클래스 | 원복 sha256(앞 12자) | 원복 동일 |", "|---|---|---|---|---|---|---|"]
    for mutant, result, failed_classes, short, same in rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (mutant["id"], mutant["area"], mutant["what"], result, failed_classes, short, "예" if same else "아니오"))
    total = len(rows)
    red_count = sum(1 for row in rows if row[1].startswith("빨강"))
    lines += ["", "합계: 변이 %d개 중 빨강 %d개, 문제 %d개(시험이 못 잡았거나 형식이 잘못된 변이·원복 불일치). 걸린 시간 %d초." % (total, red_count, bad, time.time() - started)]
    open(HERE + "/" + OUT_NAME, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("total", total, "red", red_count, "problems", bad)


if __name__ == "__main__":
    main()
