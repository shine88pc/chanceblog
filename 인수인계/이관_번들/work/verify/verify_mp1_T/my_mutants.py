# Verifier-designed mutants (lens T). Loaded by mutate_v.py --mine ; M/A/MOD/DOC are injected by the loader.
LAMBDA = "(lambda facts: None)"

MY_MUTANTS = [
    # ---- operator-only words / lists (delete one word) ----
    M("K01", "12항목", "광고 낱말에서 ca-pub- 삭제", 'r"adsbygoogle|ca-pub-", re.I)', 'r"adsbygoogle", re.I)'),
    M("K02", "12항목", "광고 낱말에서 adsbygoogle 삭제", 'r"adsbygoogle|ca-pub-", re.I)', 'r"ca-pub-", re.I)'),
    M("K03", "12항목", "PIPELINE_PAUSE 낱말을 대소문자 구분", '_PAUSE_TEXT_RE = re.compile(r"PIPELINE_PAUSE", re.I)', '_PAUSE_TEXT_RE = re.compile(r"PIPELINE_PAUSE")'),
    M("K04", "12항목", "삭제 낱말에서 rmtree 삭제", "|rmtree|마이그레이션|", "|마이그레이션|"),
    M("K05", "12항목", "스킴 정규식에서 amqps 만 빼기(상수는 그대로)", "sorted(EXTERNAL_SCHEMES, key=len, reverse=True)", 'sorted((s for s in EXTERNAL_SCHEMES if s != "amqps"), key=len, reverse=True)'),
    M("K06", "12항목", "스킴 정규식에서 ldaps 만 빼기(상수는 그대로)", "sorted(EXTERNAL_SCHEMES, key=len, reverse=True)", 'sorted((s for s in EXTERNAL_SCHEMES if s != "ldaps"), key=len, reverse=True)'),
    M("K07", "12항목", "의존성 폴더 규칙을 맨 위 vendor 만으로", '    if "vendor" in segments or "node_modules" in segments or', '    if segments[0] == "vendor" or "node_modules" in segments or'),
    M("K08", "12항목", ".github 규칙을 맨 위 폴더만으로", '    if ".github" in segments:', '    if segments[0] == ".github":'),
    M("K09", "12항목", "안전 장치 문서 면제를 .md 만으로 좁힘", "    if base.endswith(DOC_SUFFIXES):\n        return False\n", '    if base.endswith(".md"):\n        return False\n'),
    M("K10", "12항목", "정책 파일 자체 판정을 대소문자 구분으로", "    if path.casefold() in _POLICY_SELF_FOLDED:", "    if path in POLICY_SELF_FILES:"),
    # ---- 8 conditions: each one always passes ----
    M("K11", "8조건", "조건 1(번호 일치)을 항상 통과", '"number_match": _c_number_match', '"number_match": ' + LAMBDA),
    M("K12", "8조건", "조건 2(커밋 추가 없음)를 항상 통과", '"no_new_commit": _c_no_new_commit', '"no_new_commit": ' + LAMBDA),
    M("K13", "8조건", "조건 3(검사 전체 통과)을 항상 통과", '"checks_pass": _c_checks_pass', '"checks_pass": ' + LAMBDA),
    M("K14", "8조건", "조건 4(독립 검증)를 항상 통과", '"independent_verified": _c_independent', '"independent_verified": ' + LAMBDA),
    M("K15", "8조건", "조건 5(충돌 없음)를 항상 통과", '"no_conflict": _c_no_conflict', '"no_conflict": ' + LAMBDA),
    M("K16", "8조건", "조건 6(변경 범위 일치)을 항상 통과", '"scope_matches": _c_scope', '"scope_matches": ' + LAMBDA),
    M("K17", "8조건", "조건 7(비밀정보 노출 없음)을 항상 통과", '"no_secret_exposure": _c_no_secret', '"no_secret_exposure": ' + LAMBDA),
    M("K18", "8조건", "조건 8(원복 방법)을 항상 통과", '"rollback_confirmed": _c_rollback', '"rollback_confirmed": ' + LAMBDA),
    # ---- 8 conditions: weakened inside ----
    M("K19", "8조건", "조건 6 에서 승인 때 파일 목록과 지금 목록 비교를 생략", '    if approved != current:\n        return "승인할 때 설명한 파일 목록과', '    if False:\n        return "승인할 때 설명한 파일 목록과'),
    M("K20", "8조건", "조건 4 의 남은 지적 수 형 검사를 뺌(False·0.0 허용)", '    if not _non_negative_int(open_findings):\n        return "남은 필수 지적 수가 올바른 숫자가 아닙니다"\n', ""),
    M("K21", "8조건", "조건 7 의 발견 수 형 검사를 뺌(False·0.0 허용)", '    if not _non_negative_int(value):\n        return "비밀 모양 발견 수가 올바른 숫자가 아닙니다"\n', ""),
    M("K22", "8조건", "조건 5 에서 거짓처럼 보이는 값(None·0)도 통과", '    value = facts.get("has_conflict")\n    if value is False:', '    value = facts.get("has_conflict")\n    if not value:'),
    M("K23", "8조건", "조건 3 의 이름 검사에서 공백만 있는 이름 허용", "if not isinstance(name, str) or not name.strip():", "if not isinstance(name, str) or not name:"),
    M("K24", "8조건", "조건 8 의 최소 글자 경계(10 → 초과)", "    if len(body) < ROLLBACK_MIN_CHARS or", "    if len(body) <= ROLLBACK_MIN_CHARS or"),
    M("K25", "8조건", "조건 8 의 모름 문구 집합 제거(10자 규칙과 겹치는지)", " or body.casefold() in _ROLLBACK_PLACEHOLDERS:", ":"),
    M("K26", "8조건", "조건 4 의 결과 비교를 pass 아님 → fail 만 거절로 약화", '    if record["verdict"] != "pass":', '    if record["verdict"] == "fail":'),
    M("K27", "8조건", "조건 4 의 검증자·구현자 비교에서 공백·대소문자 접기 제거", "    if verifier.strip().casefold() == implementer.strip().casefold():", "    if verifier == implementer:"),
    M("K28", "8조건", "조건 3 의 결과 비교를 대소문자 무시로 약화", '        elif item.get("conclusion") != "success":', '        elif str(item.get("conclusion")).lower() != "success":'),
    # ---- first-operation 3 records ----
    M("K29", "시험 3건", "건수 경계 한 칸 아래(2건이면 continue)", "    if len(seen) < TRIAL_SIZE or unknown:", "    if len(seen) < TRIAL_SIZE - 1 or unknown:"),
    M("K30", "시험 3건", "건수 경계 한 칸 위(3건이어도 pending)", "    if len(seen) < TRIAL_SIZE or unknown:", "    if len(seen) <= TRIAL_SIZE or unknown:"),
    M("K31", "시험 3건", "참인 값(1·'예')도 충족으로", '            if value is True:\n                continue\n            if key == "main_checks_passed" and value is None:', '            if value:\n                continue\n            if key == "main_checks_passed" and value is None:'),
    # ---- approval scope / case ----
    M("K32", "승인 한정", "한 번 쓴 번호 재사용 거절을 PR 도 같을 때만으로 풀기", "        if number in self._numbers:", "        if number in self._numbers and pr_number in self._prs:"),
    M("K33", "승인 한정", "approval_matches 가 소문자 승인 번호를 대문자로 고쳐 읽음", "    approved = _standard_label(approved_number)\n    return approved is not None and approved == _standard_label(pr_number_label)",
      "    approved = _standard_label(approved_number.upper() if isinstance(approved_number, str) else approved_number)\n    return approved is not None and approved == _standard_label(pr_number_label)"),
    M("K34", "승인 한정", "변경 파일 목록 비교를 대소문자 무시로", "        found.add(normal)", "        found.add(normal.casefold())"),
    M("K35", "승인 한정", "tests 폴더 면제를 대소문자 무시로", '    return (len(parts) > 1 and parts[0] == "tests") or', '    return (len(parts) > 1 and parts[0].casefold() == "tests") or'),
    M("K36", "승인 한정", "머리 커밋 비교를 대소문자 구분으로", "    return value.lower() if isinstance(value, str) and _SHA_RE.fullmatch(value) is not None else None", "    return value if isinstance(value, str) and _SHA_RE.fullmatch(value) is not None else None"),
    M("K37", "승인 한정", "PR 제목 번호가 맨 앞 태그가 아니어도 인정", "    if len(tags) != 1 or not title.startswith(tags[0]):", "    if len(tags) != 1:"),
    M("K38", "승인 한정", "_positive_int 가 불리언을 양의 정수로 인정", "    return isinstance(value, int) and not isinstance(value, bool) and value > 0", "    return isinstance(value, int) and value > 0"),
    # ---- declared ----
    M("K39", "선언", "선언 거짓 판정을 == False 로(0 도 거짓)", "                if value is False:\n                    continue", "                if value == False:\n                    continue"),
    M("K40", "선언", "나머지 6항목은 정확히 True 일 때만 표시", "            elif value is not None and value is not False:", "            elif value is True:"),
    # ---- merge method ----
    M("K41", "병합 방식", "pr_merge 로 시작하는 값도 허용", "    return isinstance(method, str) and method == ALLOWED_MERGE_METHOD", "    return isinstance(method, str) and method.startswith(ALLOWED_MERGE_METHOD)"),
    # ---- explanation / notice ----
    M("K42", "설명", "점검표 값 해석: 거짓처럼 보이는 값(None·0)을 아니오로", '    return "아니오" if marks[code] is False else "예"', '    return "예" if marks[code] else "아니오"'),
    M("K43", "설명", "답의 최소 글자 경계(8 → 초과)", "    if len(answer) < ANSWER_MIN_CHARS or", "    if len(answer) <= ANSWER_MIN_CHARS or"),
    M("K44", "설명", "답의 최소 한글 수 경계(4 → 초과)", "len(_HANGUL_RE.findall(answer)) < ANSWER_MIN_HANGUL", "len(_HANGUL_RE.findall(answer)) <= ANSWER_MIN_HANGUL"),
    M("K45", "알림", "알림 항목 콜론에서 전각 콜론 허용 제거", '            if rest and rest[0] in ":：":', '            if rest and rest[0] in ":":'),
    # ---- normalize ----
    M("K46", "경로", "제어 문자 검사에서 DEL(127) 제외", "any(ord(ch) < 32 or ord(ch) == 127 for ch in text)", "any(ord(ch) < 32 for ch in text)"),
    M("K47", "경로", "경로의 드라이브 글자 검사 제거", ' or re.match(r"[A-Za-z]:", text) or any(', " or any("),
    M("K48", "경로", "경로의 앞 슬래시(절대 경로) 검사 제거", '    if not text or text.startswith("/") or', "    if not text or"),
]
