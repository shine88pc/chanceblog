"""항목별 독립 병합 확인 — 시작점(origin/main 41ce292)의 깨끗한 사본에 **한 항목의 커밋들만** 입혀(`git diff` 패치를 차례로 `git apply` — 두 항목이 함께 덧붙이는 결정 기록·변경 이력·사진 문서는 뺀다)
그 항목의 새 시험과 영향 모듈이 통과하는지 본다.
사용: python -X utf8 indep_check.py <항목 이름: AP15|AP14> <시작 커밋>..<끝 커밋> [<시작 커밋>..<끝 커밋> ...]
2차 지시 뒤에는 한 항목의 커밋이 가지 위에 두 덩어리로 흩어져 있다(1차 → 다른 항목의 1차 → 이 항목의 2차). 그래서 덩어리마다 범위를 하나씩 준다:
  AP15 = 41ce292..65a4ede(1차) b31a50e..<AP15 3 커밋>(2차)       AP14 = 65a4ede..b31a50e(1차) <AP15 3 커밋>..<AP14 4 커밋>(2차)
읽기만 하는 도구다(작업 폴더·저장소는 고치지 않는다). 사본은 보고서 폴더 `indep_<항목>` 에 만든다."""
import shutil
import subprocess
import sys
from pathlib import Path

name, ranges = sys.argv[1], sys.argv[2:]
WORK = "C:/work/ai/improve_wt_app15"
HERE = Path("C:/work/ai/audit6/improve/app15")
tree = HERE / f"indep_{name}"
if tree.exists():
    shutil.rmtree(tree)
tree.mkdir(parents=True)
archive = subprocess.run(["git", "-C", WORK, "archive", "41ce292"], capture_output=True, check=True).stdout
subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
# 두 항목이 함께 덧붙이는 문서(결정 기록·변경 이력·사진 문서 — 맨 끝이나 같은 자리에 줄을 더한다)는 병합 때 글자 충돌이 날 수 있는 곳이라 이 확인에서 뺀다(코드·시험·나머지 문서만 본다)
SHARED = (":(exclude)docs/DECISIONS.md", ":(exclude)CHANGELOG.md", ":(exclude)docs/UI_VISUAL_QA.md")
for index, span in enumerate(ranges, 1):
    first, last = span.split("..")
    patch = subprocess.run(["git", "-C", WORK, "diff", "--binary", first, last, "--", ".", *SHARED], capture_output=True, check=True).stdout
    patch_file = HERE / f"indep_{name}_{index}.patch"
    patch_file.write_bytes(patch)
    done = subprocess.run(["git", "apply", "--whitespace=nowarn", str(patch_file)], cwd=tree, capture_output=True, text=True, encoding="utf-8")
    print(f"덩어리 {index} ({span}): 패치 {len(patch)} 바이트 —", "적용 성공" if done.returncode == 0 else "적용 실패 " + (done.stderr or done.stdout)[:300])
    if done.returncode:
        sys.exit(1)
