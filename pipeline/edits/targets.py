"""게시글 대상 해석: _posts 를 직접 스캔해 URL·파일명·제목으로 한 편을 찾는다.

저장소의 posts.json 은 Jekyll 템플릿(빌드할 때만 JSON 이 됨)이라 데이터로 읽을 수 없다. 그래서
`_posts` 의 front matter 와 `_config.yml` 의 permalink/baseurl 로 공개 URL 을 계산해 매칭한다.
"""
import re
from pathlib import Path
from urllib.parse import urlsplit

from pipeline.edits import frontmatter

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

POSTS_DIR = "_posts"
_NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+?)\.(?:md|markdown)$")
MAX_QUERY_CHARS = 300
MIN_CONTAINS_CHARS = 8


def site_config(root):
    cfg = {}
    path = Path(root) / "_config.yml"
    if yaml is not None and path.exists():
        try:
            cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            cfg = {}
    return {"permalink": str(cfg.get("permalink") or "/:categories/:year/:month/:day/:title:output_ext"),
            "baseurl": str(cfg.get("baseurl") or "").rstrip("/"), "url": str(cfg.get("url") or "").rstrip("/")}


def slugify(text):
    return re.sub(r"[^\w]+", "-", text.lower(), flags=re.UNICODE).strip("-")


def post_url_path(filename, permalink):
    """Jekyll permalink 로 계산한 URL 경로(끝 슬래시 없음). 알 수 없는 자리표시자가 있으면 None."""
    m = _NAME_RE.match(filename)
    if not m:
        return None
    year, month, day, title = m.groups()
    out = (permalink.replace(":year", year).replace(":month", month).replace(":day", day)
           .replace(":title", slugify(title)))
    if re.search(r":[a-z_]+", out):
        return None
    return "/" + out.strip("/")


def load_post_index(root):
    root = Path(root)
    site = site_config(root)
    index = []
    for path in sorted((root / POSTS_DIR).rglob("*.md")):
        text, _ = frontmatter.read_file(path)
        fm = frontmatter.parse_front_matter(frontmatter.split_front_matter(text)[0]) or {}
        rel = path.relative_to(root).as_posix()
        url_path = post_url_path(path.name, site["permalink"])
        index.append({
            "path": rel,
            "title": re.sub(r"\s+", " ", str(fm.get("title") or path.stem)).strip(),
            "published": fm.get("published") is not False,
            "url_path": (site["baseurl"] + url_path) if url_path else None,
            "image": str(fm.get("image") or ""),
        })
    return index


def _norm_title(text):
    return re.sub(r"\s+", " ", re.sub(r"[\"'“”‘’「」『』]", "", text or "")).strip().casefold()


def match_post(query, index):
    """(일치한 글 목록, 방식). 방식: url | filename | title | contains | none | invalid."""
    q = frontmatter.normalize_newlines(query).strip()
    if not q or "\n" in q or len(q) > MAX_QUERY_CHARS:
        return [], "invalid"
    if re.match(r"^https?://", q, re.I) or q.startswith("/"):
        path = urlsplit(q).path if q.lower().startswith("http") else q.split("#")[0].split("?")[0]
        norm = "/" + path.strip("/").lower()
        hits = [e for e in index if e["published"] and e["url_path"] and e["url_path"].lower() == norm]
        if not hits:
            hits = [e for e in index if e["published"] and e["url_path"] and norm.endswith(e["url_path"].lower())]
        return hits, ("url" if hits else "none")
    base = q.replace("\\", "/")
    hits = [e for e in index if e["path"] == base or e["path"].rsplit("/", 1)[-1] in (base, base + ".md")]
    if hits:
        return hits, "filename"
    nq = _norm_title(q)
    hits = [e for e in index if _norm_title(e["title"]) == nq]
    if hits:
        return hits, "title"
    if len(nq) >= MIN_CONTAINS_CHARS:
        hits = [e for e in index if nq in _norm_title(e["title"])]
        if hits:
            return hits, "contains"
    return [], "none"


def describe(entries, limit=5):
    return [f"{e['title']} ({e['path']})" for e in entries[:limit]]
