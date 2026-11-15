"""작업 폴더의 현재 모습을 시험용 사본으로 복사한다(.git·__pycache__ 제외) — 시험이 도는 동안 작업 폴더를 고칠 수 있게. 사용: python snapshot.py <사본 폴더>"""
import shutil
import sys
from pathlib import Path

WORK = Path("C:/work/ai/improve_wt_app15")
dst = Path(sys.argv[1])
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(WORK, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
print("복사 끝", dst)
