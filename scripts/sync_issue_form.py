"""이슈 양식(page-edit.yml)의 드롭다운을 pages.json / edit-spec.yml 기준으로 다시 쓴다.

  python scripts/sync_issue_form.py           # 마커(# PAGES:START~END, # EDITS:START~END) 사이만 갱신
  python scripts/sync_issue_form.py --check   # 최신 여부만 검사(종료 코드 1이면 최신 아님)

pages.json 이 먼저 최신이어야 한다: python scripts/build_pages_registry.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.console import safe_output  # noqa: E402
from pipeline.edits import forms, pages, spec as spec_mod  # noqa: E402


def main(argv=None):
    safe_output()
    check ="--check" in (argv if argv is not None else sys.argv[1:])
    try:
        spec = spec_mod.load_spec(ROOT)
        problems = spec_mod.validate_spec(spec)
        if problems:
            print("명세 오류:\n  - " + "\n  - ".join(problems))
            return 2
        changed = forms.sync_page_form(ROOT, spec, pages.load_registry(ROOT), write=not check)
    except (spec_mod.SpecError, pages.PagesError, forms.FormError) as exc:
        print(f"[오류] {exc}")
        return 2
    if check:
        print("이슈 양식이 최신이 아닙니다 (python scripts/sync_issue_form.py)" if changed else "이슈 양식 최신")
        return 1 if changed else 0
    print("이슈 양식 갱신" if changed else "이슈 양식 변경 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
