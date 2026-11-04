"""안내(info) 요청 파일 만들기 — make_request.py 를 빈 시험·검증 문구로 부른다(PowerShell 은 빈 문자열 인자를 버려 직접 못 부른다).
사용: python -X utf8 make_info_request.py <R-번호> <슬러그> <초안 파일 이름(W 안)>"""
import subprocess
import sys
from pathlib import Path

S = Path(__file__).resolve().parent
number, slug, draft = sys.argv[1:4]
sys.exit(subprocess.run([sys.executable, "-X", "utf8", str(S / "make_request.py"), number, slug, draft, "", "", ""], cwd=str(S)).returncode)
