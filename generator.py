"""Chance_Blog 자동 생성기.

모드
- 기본: 뉴스 주제를 골라 KR/EN 글 한 쌍을 생성
- FIX_IMAGES=1: 새 글 없이 기존 글의 깨진/누락/중복 이미지만 교체
- Issue 이벤트: 저장소 관리자가 올린 이슈로 파일 수정 (경로 제한 적용)
- DRY_RUN=1: 파일 쓰기/커밋 없이 계획만 로그로 출력
  (API 키가 없으면 Gemini/Unsplash는 스텁으로 동작)
"""
import os
import re
import json
import zlib
import difflib
import datetime
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import timezone, timedelta
from pathlib import Path

# ============================================================
# 환경 설정
# ============================================================
API_KEY = os.environ.get("GEMINI_API_KEY")
UNSPLASH_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")


def _flag(name):
    return os.environ.get(name, "0").strip().lower() in {"1", "true", "yes"}


DRY_RUN = _flag("DRY_RUN")
FIX_IMAGES = _flag("FIX_IMAGES")
EVENT_NAME = os.environ.get("EVENT_NAME", "").strip().lower()
ISSUE_TITLE = os.environ.get("ISSUE_TITLE", "")
ISSUE_BODY = os.environ.get("ISSUE_BODY", "")
ISSUE_ASSOC = os.environ.get("ISSUE_AUTHOR_ASSOCIATION", "").strip().upper()

STUB_GEMINI = not API_KEY
STUB_UNSPLASH = not UNSPLASH_KEY

KST = timezone(timedelta(hours=9))
POSTS_DIR = Path("_posts")
HISTORY_FILE = Path("history.json")
UA = "Mozilla/5.0 (compatible; ChanceBlogBot/2.0)"
MAX_ATTEMPTS = 3

MODEL_CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
]

# 검색 결과가 전혀 없을 때만 쓰는 최후 폴백 (글 생성 시에만 사용)
POOL_IDS = [
    "1591488320449-011701bb6704", "1550745165-9bc0b252726f",
    "1518770660439-4636190af475", "1526374965328-7f61d4dc18c5",
    "1555680202-c86f0e12f086", "1563770660941-20978e870e26",
    "1677442136019-21780ecad985", "1618005182384-a83a8bd57fbe",
    "1620712943543-bcc4688e7485", "1507146426996-ef05306b995a",
    "1531482615713-2afd69097998", "1541185933-ef5d8ed016c2",
    "1614728894747-a83421e2b9c9", "1451187580459-43490279c0fa",
    "1446776811953-b23d57bd21aa", "1484589065579-248aad0d8b13",
    "1517976487502-5f654b0c2794", "1485827404703-89b55fcc595e",
    "1558494949-ef010cbdcc31", "1563986768609-322da13575f3",
    "1510511459019-5dda7724fd87", "1544197150-b99a580bb7a8",
    "1486406146926-c627a92ad1ab", "1519501025264-65ba15a82390",
    "1504384308090-c894fdcc538d", "1473968512647-3e447244af8f",
    "1508739773434-c26b3d09e071", "1516321318423-f06f85e504b3",
    "1535378917042-10a22c95931a", "1504639725590-34d0984388bd",
    "1518773553398-650c184e0bb3", "1531297484001-80022131f5a1",
]
IMG_PARAMS = "?auto=format&fit=crop&w=1000&q=80"
IMAGE_POOL = [f"https://images.unsplash.com/photo-{i}{IMG_PARAMS}" for i in POOL_IDS]

TECH_KO = (
    "인공지능", "반도체", "로봇", "소프트웨어", "클라우드", "스마트폰", "우주",
    "위성", "로켓", "게임", "보안", "해킹", "데이터", "앱", "개발", "테크",
    "전기차", "배터리", "양자", "엔비디아", "삼성전자", "하이닉스", "구글",
    "애플", "메타", "마이크로소프트", "테슬라", "스타트업", "생성형", "웨어러블",
    "디스플레이", "통신", "네트워크", "플랫폼", "컴퓨터", "서버", "센서", "드론",
    "자율주행", "핵융합", "과학", "기술", "칩", "챗gpt", "오픈ai",
)
TECH_EN = re.compile(
    r"\b(ai|gpu|cpu|llm|chatgpt|openai|nvidia|5g|6g|chip|robot|quantum|"
    r"software|cloud|startup|cyber|satellite|rocket)\b", re.I)

_client = None
_download_locations = {}


# ============================================================
# 공통 유틸
# ============================================================
def get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=API_KEY)
    return _client


def write_text_atomic(path, content):
    path = Path(path)
    if DRY_RUN:
        print(f"[DRY_RUN] 쓰기 생략: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def read_history():
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError) as exc:
        print(f"history.json 읽기 실패, 빈 기록으로 진행: {exc}")
        return []


def write_history(history):
    write_text_atomic(
        HISTORY_FILE,
        json.dumps(history[-200:], ensure_ascii=False, indent=2),
    )


def extract_json_object(raw_text):
    if not raw_text or not raw_text.strip():
        raise ValueError("Gemini 응답이 비어 있습니다.")
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start < 0:
        raise ValueError(f"JSON 객체를 찾을 수 없습니다: {text[:300]}")
    depth, in_string, escaped = 0, False, False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                parsed = json.loads(text[start:index + 1])
                if not isinstance(parsed, dict):
                    raise ValueError("최상위 JSON 값이 객체가 아닙니다.")
                return parsed
    raise ValueError(f"완전한 JSON 객체를 찾을 수 없습니다: {text[:300]}")


def call_gemini_with_fallback(prompt):
    errors = []
    for model_name in MODEL_CANDIDATES:
        try:
            print(f"Gemini 모델 호출 시도: {model_name}")
            response = get_client().models.generate_content(
                model=model_name, contents=prompt)
            text = getattr(response, "text", None)
            if text and text.strip():
                print(f"Gemini 모델 호출 성공: {model_name}")
                return response
            errors.append(f"{model_name}: 응답 텍스트 없음")
        except Exception as exc:
            errors.append(f"{model_name}: {exc}")
            print(f"Gemini 모델 호출 실패: {model_name} - {exc}")
    raise RuntimeError("모든 Gemini 모델 호출 실패\n" + "\n".join(errors))


def safe_repo_path(raw_path):
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("target_file 값이 비어 있습니다.")
    candidate = Path(raw_path.strip())
    if candidate.is_absolute():
        raise ValueError("절대 경로는 허용되지 않습니다.")
    root = Path(".").resolve()
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError("저장소 외부 경로는 허용되지 않습니다.")
    forbidden = {".git", ".github", "node_modules", "_site", ".jekyll-cache"}
    if forbidden.intersection(candidate.parts):
        raise ValueError("보호된 디렉터리는 수정할 수 없습니다.")
    return target


# ============================================================
# 이미지: 정규화 / 검증 / Unsplash 검색
# ============================================================
def image_key(url):
    """중복 비교 키: 호스트+경로 (쿼리스트링 제외)."""
    if not url:
        return ""
    url = url.strip().strip("\"'")
    p = urllib.parse.urlsplit(url)
    return (p.netloc + p.path).lower()


def build_image_url(raw):
    p = urllib.parse.urlsplit(raw)
    return f"{p.scheme}://{p.netloc}{p.path}{IMG_PARAMS}"


def url_ok(url, timeout=10):
    if DRY_RUN and STUB_UNSPLASH and "photo-dry" in url:
        return True
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def search_unsplash(query, per_page=15):
    if STUB_UNSPLASH:
        if DRY_RUN:
            crc = zlib.crc32(query.encode("utf-8")) % 100000
            print(f"[DRY_RUN] Unsplash 스텁 검색: {query!r}")
            return [f"https://images.unsplash.com/photo-dry{crc}{i}{IMG_PARAMS}"
                    for i in range(3)]
        print("UNSPLASH_ACCESS_KEY 없음: 검색 생략")
        return []
    params = urllib.parse.urlencode({
        "query": query, "per_page": per_page,
        "orientation": "landscape", "content_filter": "high",
    })
    req = urllib.request.Request(
        "https://api.unsplash.com/search/photos?" + params,
        headers={"Authorization": f"Client-ID {UNSPLASH_KEY}",
                 "Accept-Version": "v1", "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        print(f"Unsplash API 오류 {exc.code} (query={query!r}) "
              "- 403/429면 시간당 호출 한도 초과일 수 있습니다.")
        return []
    except Exception as exc:
        print(f"Unsplash 호출 실패 (query={query!r}): {exc}")
        return []

    urls = []
    for item in data.get("results", []):
        raw = (item.get("urls") or {}).get("raw")
        if not raw:
            continue
        url = build_image_url(raw)
        urls.append(url)
        loc = (item.get("links") or {}).get("download_location")
        if loc:
            _download_locations[image_key(url)] = loc
    return urls


def trigger_download(url):
    """Unsplash API 가이드라인: 사진 사용 시 download 엔드포인트 호출 (실패해도 무시)."""
    loc = _download_locations.get(image_key(url))
    if not loc or DRY_RUN or STUB_UNSPLASH:
        return
    try:
        req = urllib.request.Request(
            loc, headers={"Authorization": f"Client-ID {UNSPLASH_KEY}", "User-Agent": UA})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass


def pick_images(queries, used, count=1, allow_pool=False):
    """미사용 + 접근 가능한 이미지를 count개 선택. used 집합에 키를 추가한다."""
    picked = []
    seen_queries = set()
    for q in queries:
        q = (q or "").strip()
        if not q or q.lower() in seen_queries:
            continue
        seen_queries.add(q.lower())
        for url in search_unsplash(q):
            key = image_key(url)
            if key in used or not url_ok(url):
                continue
            used.add(key)
            picked.append(url)
            print(f"  이미지 선택 (query={q!r}): {url}")
            if len(picked) >= count:
                return picked
    if allow_pool:
        for url in IMAGE_POOL:
            key = image_key(url)
            if key in used or not url_ok(url):
                continue
            used.add(key)
            picked.append(url)
            print(f"  [경고] 검색 결과 없음, 폴백 풀 이미지 사용: {url}")
            if len(picked) >= count:
                break
    return picked


def make_image_queries(title, tags, category):
    """글 제목/태그로 영어 Unsplash 검색어 3개를 만든다 (구체적 -> 일반적)."""
    fallback = ["technology", "computer hardware"]
    if STUB_GEMINI:
        return fallback
    prompt = f"""
다음 블로그 글의 대표 이미지를 Unsplash에서 찾기 위한 영어 검색어 3개를 만드세요.
- 구체적인 것부터 일반적인 것 순서
- 각 2~4단어, 주제를 시각적으로 보여주는 사물/장면 위주
- 사람 얼굴, 로고, 브랜드명, 글자가 들어간 이미지는 피하는 단어 선택
[제목] {title}
[태그] {tags}
[카테고리] {category}
JSON 객체만 반환: {{"image_queries": ["...", "...", "..."]}}
"""
    try:
        data = extract_json_object(call_gemini_with_fallback(prompt).text)
        qs = [q.strip() for q in data.get("image_queries", [])
              if isinstance(q, str) and q.strip()]
        return qs[:4] or fallback
    except Exception as exc:
        print(f"검색어 생성 실패, 기본값 사용: {exc}")
        return fallback


# ============================================================
# 게시글 읽기 / 프론트매터
# ============================================================
FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


def split_front_matter(text):
    m = FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def fm_get(fm, key):
    if not fm:
        return ""
    m = re.search(rf"(?m)^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", fm)
    if not m:
        return ""
    v = m.group(1).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def date_of(path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", Path(path).name)
    return m.group(1) if m else "0000-00-00"


def load_posts():
    posts = []
    if not POSTS_DIR.exists():
        return posts
    for p in POSTS_DIR.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"읽기 실패 ({p}): {exc}")
            continue
        fm, _ = split_front_matter(text)
        posts.append({
            "path": p, "text": text,
            "title": fm_get(fm, "title"),
            "image": fm_get(fm, "image"),
            "tags": fm_get(fm, "tags"),
            "category": fm_get(fm, "category"),
        })
    posts.sort(key=lambda x: (date_of(x["path"]), x["path"].name))
    return posts


def apply_image(text, old_url, new_url):
    if old_url and old_url in text:
        return text.replace(old_url, new_url)
    fm, body = split_front_matter(text)
    if fm is None:
        return text
    if re.search(r"(?m)^image:", fm):
        fm = re.sub(r"(?m)^image:.*$", f'image: "{new_url}"', fm)
    else:
        fm = fm.rstrip() + f'\nimage: "{new_url}"'
    return f"---\n{fm}\n---\n{body}"


def used_keys_from_posts(posts, exclude_path=None):
    used = set()
    for post in posts:
        if exclude_path is not None and post["path"] == exclude_path:
            continue
        for u in re.findall(r"https://images\.unsplash\.com/[^\s\"')]+", post["text"]):
            used.add(image_key(u))
        if post["image"]:
            used.add(image_key(post["image"]))
    return used


def diagnose(post, used):
    img = post["image"]
    if not img:
        return "missing"
    if not img.lower().startswith("http"):
        return "local-path"
    if image_key(img) in used:
        return "duplicate"
    if not url_ok(img):
        return "broken"
    return None


def repair(post, used):
    queries = make_image_queries(post["title"], post["tags"], post["category"])
    picked = pick_images(queries, used, 1, allow_pool=False)
    return picked[0] if picked else None


# ============================================================
# FIX_IMAGES 모드
# ============================================================
def fix_images():
    posts = load_posts()
    print(f"검사 대상 글: {len(posts)}개 (오래된 글의 이미지를 우선 유지)")
    used, targets = set(), []
    for post in posts:
        problem = diagnose(post, used)
        if problem:
            targets.append((post, problem))
            print(f"- 문제({problem}): {post['path']}  image={post['image'] or '(없음)'}")
        else:
            used.add(image_key(post["image"]))

    # lang: ko -> kr 정규화 (프런트엔드 필터와 맞추기 위함)
    for post in posts:
        fixed_text = re.sub(r"(?m)^lang:[ \t]*[\"']?ko[\"']?[ \t]*$", "lang: kr", post["text"], count=1)
        if fixed_text != post["text"]:
            print(f"- lang ko -> kr: {post['path']}")
            write_text_atomic(post["path"], fixed_text)
            post["text"] = fixed_text

    fixed = skipped = 0
    for post, problem in targets:
        new_url = repair(post, used)
        if not new_url:
            print(f"  교체 후보 없음, 건너뜀: {post['path']}")
            skipped += 1
            continue
        print(f"  [{problem}] {post['path']}\n    {post['image'] or '(없음)'}\n    -> {new_url}")
        write_text_atomic(post["path"], apply_image(post["text"], post["image"], new_url))
        trigger_download(new_url)
        fixed += 1
    print(f"완료: 문제 {len(targets)}건 / 교체 {fixed}건 / 건너뜀 {skipped}건"
          + (" (DRY_RUN: 실제 변경 없음)" if DRY_RUN else ""))


# ============================================================
# Issue 처리
# ============================================================
def handle_issue_event():
    if ISSUE_ASSOC not in {"OWNER", "MEMBER", "COLLABORATOR"}:
        print(f"이슈 작성자 권한({ISSUE_ASSOC or '알 수 없음'})이 없어 처리하지 않습니다.")
        return

    excluded = {".git", ".github", "_site", "node_modules", ".jekyll-cache",
                ".venv", "venv", "__pycache__"}
    files_data = {}
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in excluded]
        for name in files:
            fp = Path(root) / name
            if name in {".env", "credentials.json"}:
                continue
            if fp.suffix.lower() not in {".md", ".html", ".yml", ".yaml",
                                         ".json", ".css", ".js", ".py", ".txt"}:
                continue
            try:
                files_data[str(fp)] = fp.read_text(encoding="utf-8", errors="replace")[:500]
            except OSError:
                continue

    prompt = f"""
당신은 Chance 기술 블로그 저장소의 파일 편집 도우미입니다.
Issue 요청에 필요한 파일 하나를 수정하거나 삭제할 변경안을 JSON으로 반환하세요.
파일 경로는 저장소 내부의 상대 경로만 사용하세요.
보호된 .git, .github, node_modules, _site 디렉터리는 수정하지 마세요.
기존 형식과 프로젝트 구조를 유지하세요.
글을 새로 만들 때 front matter의 image는 비워 두세요 (시스템이 채웁니다).

[Issue Title]
{ISSUE_TITLE}

[Issue Body]
{ISSUE_BODY}

[Repository File Samples]
{json.dumps(files_data, ensure_ascii=False)}

JSON 객체만 반환하세요. 마크다운 코드 펜스 금지.
{{
  "target_file": "relative/path/to/file",
  "file_content": "전체 파일 내용 또는 삭제 시 빈 문자열",
  "delete_file": false
}}
"""
    data = extract_json_object(call_gemini_with_fallback(prompt).text)
    target = safe_repo_path(data.get("target_file"))
    delete_file = data.get("delete_file", False)
    if not isinstance(delete_file, bool):
        raise ValueError("delete_file은 true/false여야 합니다.")

    if delete_file:
        if target.exists() and target.is_file():
            if DRY_RUN:
                print(f"[DRY_RUN] 삭제 생략: {target}")
            else:
                target.unlink()
                print(f"파일 삭제 완료: {target}")
        else:
            print(f"삭제 대상 파일이 없습니다: {target}")
        return

    content = data.get("file_content")
    if not isinstance(content, str):
        raise ValueError("file_content가 문자열이 아닙니다.")
    write_text_atomic(target, content)
    print(f"파일 저장 완료: {target}")

    # _posts 글이면 이미지 검증 (로컬 경로/누락/중복/깨짐이면 교체)
    rel = target.relative_to(Path(".").resolve())
    if rel.parts and rel.parts[0] == "_posts" and rel.suffix == ".md" and not DRY_RUN:
        post_path = Path(*rel.parts)
        posts = load_posts()
        mine = next((p for p in posts if p["path"] == post_path), None)
        if mine:
            used = used_keys_from_posts(posts, exclude_path=post_path)
            problem = diagnose(mine, used)
            if problem:
                print(f"이슈로 만든 글의 이미지 문제({problem}) - 교체 시도")
                new_url = repair(mine, used)
                if new_url:
                    write_text_atomic(post_path, apply_image(mine["text"], mine["image"], new_url))
                    trigger_download(new_url)
                else:
                    print("교체 후보가 없어 이미지를 그대로 둡니다.")


# ============================================================
# 주제 선정
# ============================================================
def norm_title(s):
    s = re.sub(r"[^\w\s]", " ", (s or "").casefold())
    return re.sub(r"\s+", " ", s).strip()


def similarity(a, b):
    a, b = norm_title(a), norm_title(b)
    if not a or not b:
        return 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    return max(ratio, jac)


def is_similar_to_any(text, existing, threshold):
    return any(similarity(text, e) >= threshold for e in existing)


def existing_titles(history, posts):
    titles = []
    for item in history:
        if isinstance(item, str):
            titles.append(item)
        elif isinstance(item, dict):
            for k in ("topic", "kr_title", "en_title"):
                v = item.get(k)
                if isinstance(v, str) and v.strip():
                    titles.append(v.strip())
    titles += [p["title"] for p in posts if p["title"]]
    return titles


def is_tech_title(title):
    low = title.lower()
    return any(k in low for k in TECH_KO) or bool(TECH_EN.search(title))


def fetch_news_items():
    rss_urls = [
        "https://news.google.com/rss/search?q=AI+%ED%85%8C%ED%81%AC+%EA%B8%B0%EC%88%A0&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtdHZHZ0pMVWlnQVAB?hl=ko&gl=KR&ceid=KR:ko",
    ]
    items, seen = [], set()
    for url in rss_urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                root = ET.fromstring(resp.read())
            for item in root.findall(".//item"):
                node = item.find("title")
                if node is None or not node.text:
                    continue
                title = re.sub(r"\s*-\s*[^-]+$", "", node.text).strip()
                key = title.casefold()
                if title and key not in seen and is_tech_title(title):
                    items.append(title)
                    seen.add(key)
        except Exception as exc:
            print(f"RSS 수집 실패 ({url}): {exc}")
    return items


def pick_topic_candidates(titles):
    """기존 글과 비슷하지 않은 뉴스 제목 최대 MAX_ATTEMPTS개. 부족하면 None(자동 선정) 추가."""
    picked = []
    for t in fetch_news_items():
        if is_similar_to_any(t, titles, 0.6):
            continue
        picked.append(t)
        if len(picked) >= MAX_ATTEMPTS:
            break
    if len(picked) < MAX_ATTEMPTS:
        picked.append(None)
    return picked


# ============================================================
# 글 생성
# ============================================================
def build_post_prompt(topic, recent_titles):
    topic_text = topic or ("최신 AI/기술 트렌드 중 아래 제외 목록과 겹치지 않는 "
                           "새로운 주제를 직접 하나 선정하세요.")
    return f"""
당신은 개인 기술 전문 블로거 'Chance'입니다.
아래 주제를 바탕으로 독창적이고 사실에 신중한 블로그 글을 한국어와 영어로 각각 작성하세요.

[주제]
{topic_text}

[최근 다룬 주제/제목 - 같은 소재와 관점 금지]
{json.dumps(recent_titles, ensure_ascii=False)}

[중요 지침]
- 제목, 카테고리, 태그를 주제에 맞게 작성하세요.
- 한국어/영어 글은 각 언어에 자연스럽게 쓰고 단순 직역은 피하세요.
- 확인되지 않은 수치, 인용문, 발표 사실을 지어내지 마세요.
- 본문은 충분한 설명과 분석을 포함하고 Markdown으로 작성하세요.
- 각 글의 Front Matter에 layout, title, category, tags, lang을 포함하세요.
- image는 쓰지 마세요. 대표 이미지는 시스템이 따로 채웁니다.
- image_queries: 이 글의 대표 이미지를 Unsplash에서 찾을 영어 검색어 3개.
  구체적인 것부터 일반적인 순서, 각 2~4단어, 주제를 시각적으로 나타내는
  사물/장면 위주, 사람 얼굴/로고/브랜드명/글자는 피하세요.
- kr_content, en_content에는 완전한 Markdown(Front Matter 포함)을 넣으세요.
- JSON 문자열 안의 줄바꿈과 따옴표는 유효한 JSON 규칙을 지키세요.
- JSON 객체만 반환하고 코드 펜스는 쓰지 마세요.

{{
  "kr_category": "KR - 카테고리명",
  "kr_title": "한국어 제목",
  "kr_tags": ["태그1", "태그2"],
  "kr_content": "한국어 Markdown 전체",
  "en_category": "EN - CategoryName",
  "en_title": "English Title",
  "en_tags": ["Tag1", "Tag2"],
  "en_content": "English Markdown full content",
  "image_queries": ["specific query", "broader query", "general query"]
}}
"""


def stub_post_data(topic):
    t = topic or "stub topic"
    fm = "---\nlayout: post\ntitle: \"{}\"\ncategory: \"{}\"\ntags: []\n---\n\n본문"
    return {
        "kr_category": "KR - 스텁", "kr_title": f"[스텁] {t}", "kr_tags": ["스텁"],
        "kr_content": fm.format(f"[스텁] {t}", "KR - 스텁"),
        "en_category": "EN - Stub", "en_title": f"[stub] {t}", "en_tags": ["stub"],
        "en_content": fm.format(f"[stub] {t}", "EN - Stub"),
        "image_queries": ["technology", "computer hardware"],
    }


def validate_post_data(data, kr_image, en_image):
    for key in ("kr_category", "kr_title", "kr_content",
                "en_category", "en_title", "en_content"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"생성 결과의 {key} 값이 비었거나 문자열이 아닙니다.")
    for key in ("kr_tags", "en_tags"):
        if not isinstance(data.get(key), list):
            data[key] = []
        data[key] = [str(t).strip() for t in data[key] if str(t).strip()]

    for prefix, image_url in (("kr", kr_image), ("en", en_image)):
        content = data[f"{prefix}_content"]
        if not content.lstrip().startswith("---"):
            content = (
                "---\nlayout: post\n"
                f"title: {json.dumps(data[f'{prefix}_title'], ensure_ascii=False)}\n"
                f"category: {json.dumps(data[f'{prefix}_category'], ensure_ascii=False)}\n"
                f"tags: {json.dumps(data[f'{prefix}_tags'], ensure_ascii=False)}\n"
                f"lang: {prefix}\nimage: {json.dumps(image_url)}\n---\n\n" + content
            )
        else:
            end = content.find("\n---", 3)
            if end != -1:
                front = content[3:end]
                body = content[end + 4:].lstrip("\n")
                front = re.sub(r"(?m)^image:\s*.*$", "", front)
                front = re.sub(r"(?m)^lang:\s*.*$", "", front)
                front = re.sub(r"\n{2,}", "\n", front).rstrip()
                front += f'\nlang: {prefix}\nimage: "{image_url}"'
                content = f"---{front}\n---\n\n{body}"

        if not re.search(r"(?m)^!\[[^\]]*\]\(", content):
            content = content.rstrip() + f"\n\n![Thumbnail]({image_url})\n"
        else:
            content = re.sub(
                r"(?m)^!\[[^\]]*\]\(https://images\.unsplash\.com/[^)]+\)",
                f"![Thumbnail]({image_url})", content, count=1)
        data[f"{prefix}_content"] = content.rstrip() + "\n"
    return data


def safe_category_dir(category, prefix):
    category = str(category).strip()
    category = re.sub(r"[\x00-\x1f/\\]+", "-", category)
    category = re.sub(r"\.\.+", ".", category).strip(" .")
    if not category:
        category = f"{prefix} - Uncategorized"
    return POSTS_DIR / category


def generate_blog_posts():
    posts = load_posts()
    history = read_history()
    titles = existing_titles(history, posts)
    used = used_keys_from_posts(posts)
    for item in history:
        if isinstance(item, dict):
            for k in ("kr_image", "en_image"):
                if item.get(k):
                    used.add(image_key(item[k]))

    recent_titles = titles[-30:]
    data, selected = None, None
    for topic in pick_topic_candidates(titles):
        print(f"주제 시도: {topic or '(자동 선정)'}")
        if STUB_GEMINI:
            candidate = stub_post_data(topic)
        else:
            resp = call_gemini_with_fallback(build_post_prompt(topic, recent_titles))
            candidate = extract_json_object(resp.text)
        kr_t, en_t = str(candidate.get("kr_title", "")), str(candidate.get("en_title", ""))
        if is_similar_to_any(kr_t, titles, 0.7) or is_similar_to_any(en_t, titles, 0.7):
            print(f"  생성된 제목이 기존 글과 비슷해 폐기: {kr_t} / {en_t}")
            continue
        data, selected = candidate, topic
        break
    if data is None:
        raise RuntimeError("기존 글과 겹치지 않는 주제를 만들지 못했습니다.")

    queries = [q for q in data.get("image_queries", []) if isinstance(q, str)]
    if not queries:
        queries = ["technology", "computer hardware"]
    images = pick_images(queries, used, 2, allow_pool=True)
    if len(images) < 2:
        raise RuntimeError("사용 가능한 대표 이미지를 2개 확보하지 못했습니다. "
                           "글을 저장하지 않습니다.")
    kr_image, en_image = images
    data = validate_post_data(data, kr_image, en_image)

    now = datetime.datetime.now(KST)
    date_str, time_str = now.strftime("%Y-%m-%d"), now.strftime("%H%M%S")
    kr_path = safe_category_dir(data["kr_category"], "KR") / f"{date_str}-KR-{time_str}.md"
    en_path = safe_category_dir(data["en_category"], "EN") / f"{date_str}-EN-{time_str}.md"

    write_text_atomic(kr_path, data["kr_content"])
    try:
        write_text_atomic(en_path, data["en_content"])
    except Exception:
        if not DRY_RUN:
            kr_path.unlink(missing_ok=True)
        raise

    history.append({
        "date": date_str, "topic": selected or "(자동 선정)",
        "kr_title": data["kr_title"], "en_title": data["en_title"],
        "kr_image": kr_image, "en_image": en_image,
    })
    write_history(history)
    trigger_download(kr_image)
    trigger_download(en_image)
    print("블로그 글 생성 완료:")
    print(f"- KR: {kr_path}\n- EN: {en_path}\n- 주제: {selected or '(자동 선정)'}")
    print(f"- 이미지: {kr_image}\n         {en_image}")


# ============================================================
# 진입점
# ============================================================
def main():
    if STUB_GEMINI and not DRY_RUN:
        raise RuntimeError(
            "GEMINI_API_KEY 환경 변수가 없습니다. "
            "Settings > Secrets and variables > Actions에서 확인하세요.")
    if DRY_RUN:
        print(f"[DRY_RUN] 시작 (Gemini={'스텁' if STUB_GEMINI else '실제'}, "
              f"Unsplash={'스텁' if STUB_UNSPLASH else '실제'}) - 파일은 변경되지 않습니다.")
    if FIX_IMAGES:
        fix_images()
    elif EVENT_NAME == "issues" or ISSUE_TITLE.strip():
        handle_issue_event()
    else:
        generate_blog_posts()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"작업 실패: {type(exc).__name__}: {exc}")
        raise
