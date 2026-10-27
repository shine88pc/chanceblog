"""고정 페이지 레지스트리(pages.json): 이슈 양식의 '대상 페이지' 드롭다운 원천.

발견 규칙(자동 갱신): 저장소 루트의 .md/.html 중
  (1) front matter 에 `editable: true` 가 있거나
  (2) 명세 targets.page.discover.include 에 적힌 파일
이며 discover.exclude 에 없는 것. 기존 페이지(about 등)는 include 로 지정하므로 파일을 고치지 않는다(광고 표면 보호).
새 페이지는 front matter 에 `editable: true` 만 넣으면 다음 동기화 때 목록에 나타난다.

결과(pages.json)는 결정적이다(시각 등 변하는 값 없음) → `--check` 로 최신 여부를 검사할 수 있다.
`--check` 는 제목(title) 차이는 보지 않는다: 제목만 고치는 PR 이 pages.json 을 같이 고치지 않아도 검사가 통과해야 하고,
제목은 병합 뒤 '[공통] 이슈 양식 페이지 목록 갱신' 워크플로가 반영한다(페이지 추가·삭제·이동은 계속 잡는다).
CLI: python -m pipeline.edits.pages [--check]
"""
import json
import re
import sys
from pathlib import Path

from pipeline.console import safe_output
from pipeline.edits import frontmatter, spec as spec_mod

REGISTRY_FILE = "pages.json"
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class PagesError(ValueError):
    pass


def _candidates(root, discover):
    root = Path(root)
    exclude = set(discover.get("exclude", []))
    found = {}
    for name in discover.get("include", []):
        try:
            rel = spec_mod.normalize_path(name)
        except ValueError as exc:
            raise PagesError(str(exc)) from exc
        if not (root / rel).is_file():
            raise PagesError(f"discover.include 의 파일이 없습니다: {rel}")
        found[rel] = True
    for path in sorted(root.iterdir()):
        if path.is_file() and path.suffix.lower() in (".md", ".html") and path.name not in exclude:
            try:
                text, _ = frontmatter.read_file(path)
            except (OSError, UnicodeDecodeError):
                continue
            fm = frontmatter.parse_front_matter(frontmatter.split_front_matter(text)[0])
            if fm and fm.get("editable") is True:
                found[path.name] = True
    return sorted(rel for rel in found if rel not in exclude)


def discover_pages(root, spec):
    """페이지 항목 목록: id, title, path, url (id 로 정렬)."""
    discover = ((spec.get("targets") or {}).get("page") or {}).get("discover") or {}
    pages, seen = [], {}
    for rel in _candidates(root, discover):
        if spec_mod.is_never_allowed(rel):
            raise PagesError(f"수정 대상이 될 수 없는 경로입니다(절대 금지 경로): {rel}")
        text, _ = frontmatter.read_file(Path(root) / rel)
        fm = frontmatter.parse_front_matter(frontmatter.split_front_matter(text)[0]) or {}
        page_id = str(fm.get("edit_id") or Path(rel).stem)
        if not _ID_RE.match(page_id):
            raise PagesError(f"페이지 id 는 영문·숫자·_- 1~40자여야 합니다: {rel} → {page_id!r} (front matter edit_id 로 지정 가능)")
        if page_id in seen:
            raise PagesError(f"페이지 id 가 중복됩니다: {page_id} ({seen[page_id]}, {rel})")
        seen[page_id] = rel
        title = re.sub(r"\s+", " ", str(fm.get("title") or page_id)).strip()
        url = str(fm.get("permalink") or f"/{Path(rel).stem}/")
        pages.append({"id": page_id, "title": title, "path": rel, "url": url})
    return sorted(pages, key=lambda p: p["id"])


def render_registry(pages):
    return json.dumps({"version": 1, "pages": pages}, ensure_ascii=False, indent=2) + "\n"


def load_registry(root):
    path = Path(root) / REGISTRY_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PagesError(f"{REGISTRY_FILE} 를 읽을 수 없습니다: {exc}") from exc
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, list):
        raise PagesError(f"{REGISTRY_FILE} 형식이 올바르지 않습니다.")
    return pages


def find_page(pages, page_id):
    for page in pages:
        if page.get("id") == page_id:
            return page
    return None


def write_registry(root, spec):
    pages = discover_pages(root, spec)
    (Path(root) / REGISTRY_FILE).write_text(render_registry(pages), encoding="utf-8", newline="\n")
    return pages


def _with_registered_titles(pages, root):
    """발견한 페이지 목록에서 제목만 pages.json 에 적힌 값으로 바꾼 사본(같은 id 가 없거나 읽을 수 없으면 그대로)."""
    try:
        registered = {p.get("id"): p for p in load_registry(root) if isinstance(p, dict)}
    except PagesError:
        return pages
    out = []
    for page in pages:
        old = registered.get(page["id"])
        out.append(dict(page, title=old["title"]) if isinstance(old, dict) and "title" in old else page)
    return out


def check_registry(root, spec, strict_titles=False):
    """pages.json 이 최신이 아니면 사유 목록, 최신이면 빈 목록.

    페이지 제목(front matter 의 title)은 기본적으로 비교하지 않는다. 제목만 고치는 수정 PR(이슈 수정의 SEO 메타 등)은 pages.json·이슈 양식
    드롭다운을 같이 고치지 않고, 그 반영은 병합 뒤 [공통] 이슈 양식 페이지 목록 갱신 워크플로가 한다. 제목 차이를 낡음으로 보면 제목을 바꾸는 모든 PR 의
    '[공통] 저장소 규칙·테스트 자동 검사' 워크플로가 빨강이 된다(2026-10-25 실제 Actions 기준선 시험). 그 밖의 모든 것 — 페이지 추가·삭제, id·path·url 변경, 파일 서식·키 순서 —
    은 글자 단위로 비교하므로 계속 잡힌다. strict_titles=True 면 제목까지 생성기 결과와 같은지 본다(병합 뒤 상태).
    """
    pages = discover_pages(root, spec)
    path = Path(root) / REGISTRY_FILE
    if not path.exists():
        return [f"{REGISTRY_FILE} 가 없습니다."]
    if not strict_titles:
        pages = _with_registered_titles(pages, root)
    current = frontmatter.normalize_newlines(path.read_text(encoding="utf-8"))
    if current != render_registry(pages):
        return [f"{REGISTRY_FILE} 가 최신이 아닙니다 (python scripts/build_pages_registry.py 로 갱신)."]
    return []


def main(argv=None):
    safe_output()
    root = Path(__file__).resolve().parents[2]
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    try:
        spec = spec_mod.load_spec(root)
        problems = spec_mod.validate_spec(spec)
        if problems:
            print("명세 오류:\n  - " + "\n  - ".join(problems))
            return 2
        if check:
            problems = check_registry(root, spec)
            print("\n".join(problems) if problems else "pages.json 최신")
            return 1 if problems else 0
        pages = write_registry(root, spec)
        print(f"pages.json 갱신: {len(pages)}개 — " + ", ".join(p["id"] for p in pages))
        return 0
    except (spec_mod.SpecError, PagesError) as exc:
        print(f"[오류] {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
