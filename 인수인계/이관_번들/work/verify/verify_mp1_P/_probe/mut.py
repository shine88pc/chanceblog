import hashlib
import pathlib
import subprocess
import sys

PY = "<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe"
ROOT = pathlib.Path("C:/work/ai/verify_mp1_P/_mut")
SRC = ROOT / "pipeline" / "merge_policy.py"
orig = SRC.read_bytes()
H0 = hashlib.sha256(orig).hexdigest()
text0 = orig.decode("utf-8").replace(chr(13) + chr(10), chr(10))

MUTS = [
    ("m01 승인 뒤 아무 말이나 허용", '승인\\.?")', '승인.*")'),
    ("m02 .github 규칙 끄기", 'if ".github" in segments:', 'if False:'),
    ("m03 push_main 허용", 'return isinstance(method, str) and method == ALLOWED_MERGE_METHOD', 'return isinstance(method, str) and method in (ALLOWED_MERGE_METHOD, "push_main")'),
    ("m04 12항목 중 Main Branch 보호 삭제", '    ("branch_protection", "Main Branch 보호 설정"),\n', ''),
    ("m05 머리 커밋 비교 생략", 'if approved != current:\n        return "승인한 뒤에 커밋이', 'if False:\n        return "승인한 뒤에 커밋이'),
    ("m06 PR 번호 비교 생략", 'if approved_pr != pr_number:', 'if False:'),
    ("m07 declared 미응답 통과", '                if value is False:\n                    continue', '                if value is False or value is None:\n                    continue'),
    ("m08 빠진 값 통과", 'absent = [key for key in keys if facts.get(key) is None]', 'absent = []'),
    ("m09 evaluate_trial 위반에도 continue", '    if violations:\n        return TrialReport(TRIAL_STOP', '    if False:\n        return TrialReport(TRIAL_STOP'),
    ("m10 완료 알림 항목 하나 삭제", '"실제 반영된 변화", "main 검사 결과", "이상 유무", "원복 Commit 또는 원복 방법")', '"실제 반영된 변화", "main 검사 결과", "원복 Commit 또는 원복 방법")'),
    ("m11 점검표 예 무시", '            if value != "아니오":', '            if False:'),
    ("m12 이미 쓴 승인 재사용 허용", 'if approved in consumed:', 'if False:'),
    ("m13 불허 문구에서 기본값대로 삭제", '"좋아 보입니다", "기본값대로", "다음 단계 진행")', '"좋아 보입니다", "다음 단계 진행")'),
    ("m14 skipped 를 통과로", 'elif item.get("conclusion") != "success":', 'elif item.get("conclusion") not in ("success", "skipped"):'),
    ("m15 검증자=구현자 허용", 'if verifier.strip().casefold() == implementer.strip().casefold():', 'if False:'),
    ("m16 파일 목록 비교 생략", 'approved_set == current_set', 'True'),
    ("m17 같은 번호 두 번 허용(시험)", 'elif number in seen:', 'elif False:'),
    ("m18 .. 구간 허용", '        if segment == "..":\n            return None\n', ''),
    ("m19 policy_self 끄기", 'if path.casefold() in _POLICY_SELF_FOLDED:', 'if False:'),
    ("m20 extra_flags 무시", 'or classified.categories or classified.extra_flags:', 'or classified.categories:'),
    ("m21 예외를 통과로", 'reason = "확인하는 중 예상하지 못한 오류가 나 실패로 처리합니다"', 'reason = None'),
    ("m22 소문자 m 거절→허용 아님(번호 대소문자 무시 제거는 정상) / M 뒤 3자리 제한 풀기", 'MERGE_NUMBER_DIGITS = r"(?:(?!000)[0-9]{3}|[1-9][0-9]{3})"', 'MERGE_NUMBER_DIGITS = r"(?:[0-9]{2,5})"'),
    ("m23 .env 규칙 삭제(credentials 접미)", '"security" in segments or any(word in part for part in segments for word in _CRED_WORDS)', 'False'),
    ("m24 trial 3건 미만도 continue", 'if len(seen) < TRIAL_SIZE or unknown:', 'if unknown:'),
    ("m25 충돌 모름 통과", 'return "충돌 여부를 알 수 없습니다(값이 없거나 참·거짓이 아닙니다)"', 'return None'),
    ("m26 비밀 모양 0 아님 통과", 'if value != 0:\n        return "비밀 모양이', 'if False:\n        return "비밀 모양이'),
    ("m27 원복 방법 길이 0", 'ROLLBACK_MIN_CHARS = 10', 'ROLLBACK_MIN_CHARS = 0'),
    ("m28 트리 비교 생략", 'if verified != current:', 'if False:'),
    ("m29 필수 지적 남아도 통과", 'if open_findings != 0:', 'if False:'),
    ("m30 광고 낱말 규칙 끄기", 'if _ADS_TEXT_RE.search(text):', 'if False:'),
    ("m31 PIPELINE_PAUSE 낱말 규칙 끄기", 'if _PAUSE_TEXT_RE.search(text):', 'if False:'),
    ("m32 의존성 경로 규칙 끄기", 'if "vendor" in segments or "node_modules" in segments or _DEPENDENCY_BASE_RE.fullmatch(base) is not None:', 'if False:'),
    ("m33 _posts 규칙 끄기", 'if any(part in _PUBLIC_DIRS for part in segments) or segments[0] == "assets"', 'if False or segments[0] == "assets"'),
    ("m34 blogs.json 규칙 끄기", 'for code in _BLOG_SETTINGS.get("/".join(segments), ()):', 'for code in ():'),
]

results = []
for name, old, new in MUTS:
    if text0.count(old) != 1:
        results.append((name, "SKIP (old text count=%d)" % text0.count(old)))
        continue
    SRC.write_bytes(text0.replace(old, new).encode("utf-8"))
    try:
        p = subprocess.run([PY, "-I", "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-p", "test_merge_policy*.py"],
                           cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=300)
        tail = (p.stderr or "").strip().splitlines()[-1] if (p.stderr or "").strip() else ""
        killed = p.returncode != 0
        results.append((name, "KILLED  " + tail if killed else "SURVIVED " + tail))
    finally:
        SRC.write_bytes(orig)
    if hashlib.sha256(SRC.read_bytes()).hexdigest() != H0:
        print("RESTORE FAILED"); sys.exit(1)

for name, res in results:
    print("%-70s %s" % (name, res))
print("restored sha256 equal:", hashlib.sha256(SRC.read_bytes()).hexdigest() == H0)
surv = [n for n, r in results if r.startswith("SURVIVED")]
print("survivors:", surv)
