"""pages.json(고정 페이지 레지스트리)을 만든다/검사한다.

  python scripts/build_pages_registry.py           # 갱신
  python scripts/build_pages_registry.py --check   # 최신 여부만 검사(종료 코드 1이면 최신 아님)

발견 규칙은 pipeline/edits/pages.py 와 .github/editorial/edit-spec.yml 의 targets.page.discover 참고.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.edits.pages import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
