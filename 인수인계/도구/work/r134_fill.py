"""R-134(NAVER API HUB '안전 틀', 데스크톱) 병합 부탁 요청 파일을 만든다(검사 관문 포함).
사용: python -X utf8 r134_fill.py <R-번호> <검사 시작 HH:MM> <검사 끝 HH:MM> <걸린 시간 예: "21분 40초"> <브랜치 이름> "<변경 범위 문구>"
검증 문구는 `r134_verify.txt`(독립 검증 결과 — 검증 보고를 읽고 내가 쓴다)에서 읽는다.
먼저 할 일(보내기 전): 데스크톱 main 이 3b1294b 인지 확인(움직였으면 새 main 위에서 가지 -2 를 다시 만든다), 병합 가지(한 커밋, 부모 origin/main)의 검사 4칸이 초록인지 본다(`make_request.py` 가 한 번 더 확인한다).
이 스크립트는 자리표시자나 <…> 가 남아 있으면 실패한다."""
import datetime
import re
import subprocess
import sys
from pathlib import Path

S = Path(__file__).resolve().parent
NUMBER, START, END, ELAPSED, BRANCH, FILES = sys.argv[1:7]

stat = subprocess.run(["git", "-C", str(S / "cd_repo"), "diff", "--shortstat", "origin/main", f"refs/heads/{BRANCH}"], capture_output=True, text=True, encoding="utf-8").stdout.strip()
tests = (f"4칸(Windows·Ubuntu × 파이썬 3.10·3.12) 모두 초록 — {START} 에 시작해 {END} 에 끝났고 {ELAPSED} 걸렸습니다. PR 화면의 검사도 이 결과를 그대로 보여 줍니다.")
verify = (S / "r134_verify.txt").read_text(encoding="utf-8").strip()
files = f"{FILES} ({stat})"
text = (S / "r134_draft.md").read_text(encoding="utf-8").replace("@DATE@", datetime.date.today().isoformat()).replace("@BRANCH@", BRANCH).replace("@RID_TYPED@", NUMBER.lower().replace("-", "")).replace("R-134", NUMBER)
run_name = "r134_draft_run.md"
(S / run_name).write_text(text.replace("@FILES@", files), encoding="utf-8", newline="\n")
leftover = re.findall(r"<[^>\n]{1,40}>|@[A-Z_]{3,}@", tests + verify + text.replace("@TESTS@", "").replace("@VERIFY@", "").replace("@FILES@", ""))
if leftover:
    sys.exit("채우지 않은 자리: " + ", ".join(leftover))
cmd = [sys.executable, "-X", "utf8", str(S / "make_request.py"), NUMBER, "merge-desktop-naver-hub-safety", run_name, tests, verify, "", f"shine88pc/chanceblog-desktop:{BRANCH}"]
sys.exit(subprocess.run(cmd, cwd=str(S)).returncode)
