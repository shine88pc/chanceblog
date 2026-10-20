"""테스트 공통: 저장소 루트를 import 경로에 올린다(어디서 실행해도 `import pipeline` 이 되게)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
