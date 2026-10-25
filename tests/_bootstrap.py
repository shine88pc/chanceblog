"""테스트 공통: 저장소 루트를 import 경로에 올린다(어디서 실행해도 `import pipeline` 이 되게)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Actions 에서 시험을 돌릴 때 시험이 진짜 실행 요약·출력 파일에 가짜 결과를 쓰지 않게 한다
# (저장소 규칙·테스트 자동 검사의 실행 요약에 시험용 '워치독 CRITICAL STALE'이 찍혀 운영자가 오해할 수 있었다).
# 이 파일들이 필요한 시험은 mock.patch.dict(os.environ, ...)·env 인자로 자기 경로를 직접 준다.
for _name in ("GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_PATH"):
    os.environ.pop(_name, None)
