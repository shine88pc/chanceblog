"""Chance_Blog 자동 생성기.

모드
- 기본: 뉴스 주제를 골라 KR/EN 글 한 쌍을 생성
- FIX_IMAGES=1: 새 글 없이 기존 글의 깨진/누락/중복 이미지만 교체
- (이슈 기반 수정은 issue-edit.yml / pipeline/edits 가 처리한다. 옛 LLM 파일 편집 핸들러는 제거됨: D-01)
- DRY_RUN=1: 파일 쓰기/커밋 없이 계획만 로그로 출력
  (API 키가 없으면 Gemini/Unsplash는 스텁으로 동작)
"""
import os
import re
import copy
import json
import zlib
import html
import random
import time
import difflib
import datetime
from email.utils import parsedate_to_datetime
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

STUB_GEMINI = not API_KEY
STUB_UNSPLASH = not UNSPLASH_KEY

KST = timezone(timedelta(hours=9))
POSTS_DIR = Path("_posts")
HISTORY_FILE = Path("history.json")
EDITORIAL_TEMPLATE_FILE = Path(__file__).resolve().parent / ".github/editorial/CHANCE_BLOG_TEMPLATE.md"
UA = "Mozilla/5.0 (compatible; ChanceBlogBot/2.0)"
MAX_ATTEMPTS = 3
# Minimum body length before source lists and thumbnails. This is a floor against
# thin drafts, not a target or a substitute for editorial review.
MIN_BODY_CHARS = {"kr": 1000, "en": 1500}
# 자동 게시 시각(KST, 시 단위). 출처 확인과 충분한 편집 가치를 위해 하루 2회로 운영합니다.
# 환경변수 POST_HOURS_KST="9,18" 로 변경 가능
SLOT_HOURS = sorted({int(x) for x in os.environ.get("POST_HOURS_KST", "9,18").split(",")
                     if x.strip().isdigit() and 0 <= int(x) <= 23})

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


# 이번 실행의 Gemini 모델 호출 횟수. 무료 한도(프로젝트 단위)를 나눠 쓰기 위한 측정값이며 동작에는 영향이 없다.
GEMINI_CALLS = {"attempts": 0, "failed": 0}


def call_gemini_with_fallback(prompt):
    errors = []
    for model_name in MODEL_CANDIDATES:
        try:
            print(f"Gemini 모델 호출 시도: {model_name}")
            GEMINI_CALLS["attempts"] += 1
            response = get_client().models.generate_content(
                model=model_name, contents=prompt)
            text = getattr(response, "text", None)
            if text and text.strip():
                print(f"Gemini 모델 호출 성공: {model_name}")
                return response
            GEMINI_CALLS["failed"] += 1
            errors.append(f"{model_name}: 응답 텍스트 없음")
        except Exception as exc:
            GEMINI_CALLS["failed"] += 1
            errors.append(f"{model_name}: {exc}")
            print(f"Gemini 모델 호출 실패: {model_name} - {_one_line(exc)}")
    raise RuntimeError("모든 Gemini 모델 호출 실패\n" + "\n".join(errors))


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
        print(f"Unsplash 호출 실패 (query={query!r}): {_one_line(exc, 200)}")
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
        print(f"검색어 생성 실패, 기본값 사용: {_one_line(exc, 400)}")
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
# 한 번에 처리하는 글 수 상한. 글마다 Gemini(검색어 3개, 모든 모델이 실패하면 글당 모델 수만큼)와 Unsplash 를 부르므로, 문제 글이 많아도
# 이만큼만 처리하고 나머지는 다음 실행으로 넘긴다(무료 한도 보호). chance-fix-images.yml 의 입력 설명에도 같은 숫자가 있다(시험이 대조한다).
FIX_IMAGES_MAX_PER_RUN = 20


def fix_images(keyword=None):
    posts = load_posts()
    print(f"검사 대상 글: {len(posts)}개 (오래된 글의 이미지를 우선 유지)")
    used, targets = set(), []
    for post in posts:
        problem = diagnose(post, used)
        if not problem and keyword:
            haystack = f"{post['title']} {post['tags']} {post['path']}".lower()
            if keyword.lower() in haystack:
                problem = "requested"
        if problem:
            targets.append((post, problem))
            print(f"- 문제({problem}): {post['path']}  image={post['image'] or '(없음)'}")
        else:
            used.add(image_key(post["image"]))

    # 한 번에 처리하는 글 수에 상한을 둔다(글마다 Gemini 검색어와 Unsplash 를 부른다). 넘는 글은 다음 실행에서 다시 진단해 처리한다.
    batch = targets[:FIX_IMAGES_MAX_PER_RUN]
    deferred = len(targets) - len(batch)
    if deferred:
        print(f"한 번에 최대 {FIX_IMAGES_MAX_PER_RUN}건만 처리합니다. 나머지 {deferred}건은 다음 실행에서 처리합니다.")
    fixed = skipped = 0
    for post, problem in batch:
        new_url = repair(post, used)
        if not new_url:
            print(f"  교체 후보 없음, 건너뜀: {post['path']}")
            skipped += 1
            continue
        print(f"  [{problem}] {post['path']}\n    {post['image'] or '(없음)'}\n    -> {new_url}")
        write_text_atomic(post["path"], apply_image(post["text"], post["image"], new_url))
        trigger_download(new_url)
        fixed += 1
    if DRY_RUN:
        head = f"교체 예정 {len(targets)}건 중 {len(batch)}건 처리 대상"
    else:
        head = f"문제 {len(targets)}건" + (f" 중 {len(batch)}건 처리" if deferred else "")
    summary = (f"완료: {head} / 교체 {fixed}건 / 건너뜀 {skipped}건"
               + (f" / 나머지 {deferred}건은 다음 실행으로 넘김(한 번에 최대 {FIX_IMAGES_MAX_PER_RUN}건)" if deferred else "")
               + (f" (DRY_RUN: 실제 변경 없음, {'가짜 AI 검색어 사용' if STUB_GEMINI else '실제 Gemini 호출'})" if DRY_RUN else ""))
    print(summary)
    return "이미지 점검: " + summary


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


NEWS_MAX_AGE_HOURS = 36
EPOCH = datetime.datetime.min.replace(tzinfo=timezone.utc)


def _int_env(name, default):
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


# 뽑힌 분야에 후보가 없을 때 다음 분야를 시도하는 총 시간 상한(초). 이 시각이 지나면 새 분야도, 분야 안의 남은 소스도
# 시도하지 않는다. 이미 시작한 소스 하나는 끝까지 기다리므로(소스당 최악 약 2분) 수집은 상한 + 약 2분 안에 끝난다.
LANE_SEARCH_BUDGET_SECONDS = _int_env("LANE_SEARCH_BUDGET_SECONDS", 480)

# 기사 탈락 사유 코드. 소스별 줄·[SKIP] 줄·실행 요약에 같은 코드로 남는다(docs/ARCHITECTURE.md).
DROP_LABELS = {
    "NO_TITLE": "제목 없음",
    "NOT_TECH": "기술 키워드 아님",
    "AGE": f"{NEWS_MAX_AGE_HOURS}시간 초과",
    "UNTRUSTED": "신뢰 목록에 없는 게시자",
    "UNCHECKED": "소스당 5건 검사 한도 초과",
    "UNRESOLVED": "게시자 원문 주소 해석 실패",
    "HOST_MISMATCH": "게시자와 원문 주소 불일치",
    "SHORT_SUMMARY": "요약 100자 미만",
    "DUPLICATE": "기존 글과 제목 유사",
}


def _count(counter, code, n=1):
    counter[code] = counter.get(code, 0) + n


def _format_drops(drops):
    """사유별 개수를 많은 순으로 'UNTRUSTED 60, AGE 11' 형태로."""
    return ", ".join(f"{code} {n}" for code, n in
                     sorted(drops.items(), key=lambda kv: (-kv[1], kv[0])))


def _one_line(text, limit=300):
    """한 줄로 접는다(개행 제거, 길이 제한). 외부·AI 유래 문구를 로그에 찍기 전에 쓴다:
    개행으로 새 줄을 시작해 '::error::' 같은 워크플로 명령을 흉내 내거나 '##[' 를 쓰지 못하게 한다."""
    folded = " ".join(str(text).split()).replace("##[", "# [")
    if folded.startswith("::"):
        folded = "→ " + folded  # 러너는 줄 앞 공백을 지우고 '::' 를 찾으므로 공백이 아니라 눈에 보이는 접두 문자로 막는다
    return folded[:limit]


def _md_cell(text, limit=120):
    """마크다운 표·목록에 안전하게 넣을 한 줄 텍스트(제목·출처처럼 AI·외부에서 온 문구용)."""
    folded = _one_line(text, limit)
    for ch, entity in (("|", "&#124;"), ("`", "'"), ("<", "&lt;"), (">", "&gt;"), ("[", "&#91;"), ("]", "&#93;")):
        folded = folded.replace(ch, entity)
    return folded


def _pause_on():
    """킬 스위치. Blogger 러너(pipeline/run.py)와 같은 값 집합(1/true/yes/on)을 쓴다."""
    return os.environ.get("PIPELINE_PAUSE", "").strip().lower() in {"1", "true", "yes", "on"}


def skip_line(code, **fields):
    """건너뜀을 로그에서 한 줄로 찾게 하는 규격: [SKIP] code=CODE key=value ..."""
    parts = [f"[SKIP] code={code}"]
    for key, value in fields.items():
        if isinstance(value, dict):
            value = ",".join(f"{k}:{v}" for k, v in sorted(value.items())) or "-"
        parts.append(f"{key}={value}")
    return " ".join(parts)


def write_step_summary(markdown):
    """Actions 실행 화면의 요약 칸(GITHUB_STEP_SUMMARY)에 덧붙인다. 로컬 실행에서는 아무 일도 하지 않는다.
    요약은 보고용이라 쓰기에 실패해도 발행 결과를 바꾸지 않는다(대신 한 줄을 남긴다)."""
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(markdown.rstrip() + "\n\n")
    except OSError as exc:
        print(f"실행 요약 쓰기 실패(발행에는 영향 없음): {exc}")

# 기술을 포함하되 한 분야에 고정되지 않도록, 여러 편집 축의 후보를 둡니다.
EDITORIAL_LANES = {
    "science": {
        "label": "과학·환경", "kr_category": "과학·환경",
        "en_category": "Science & Environment",
        "focus": "과학적 발견, 기후·환경, 공중보건과 그것이 사람과 지역사회에 미치는 변화",
    },
    "economy": {
        "label": "경제·일", "kr_category": "경제·일",
        "en_category": "Economy & Work",
        "focus": "경제, 산업, 소비, 주거, 노동과 일의 변화",
    },
    "society": {
        "label": "사회·정책", "kr_category": "사회·정책",
        "en_category": "Society & Policy",
        "focus": "사회 변화, 공공정책, 교육, 노동권과 공동체",
    },
    "technology": {
        "label": "기술·미래", "kr_category": "기술·미래",
        "en_category": "Technology & Future",
        "focus": "인공지능, 디지털 서비스, 하드웨어, 우주와 신기술",
    },
    "culture": {
        "label": "문화·미디어", "kr_category": "문화·미디어",
        "en_category": "Culture & Media",
        "focus": "문화, 대중매체, 게임, 창작과 콘텐츠 산업",
    },
    "daily_life": {
        "label": "일상·마음", "kr_category": "일상·마음",
        "en_category": "Everyday Life",
        "focus": "일상생활, 심리, 건강, 가족, 도시와 사람들이 매일 겪는 변화",
    },
}
_GN_KO = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
_GN_EN = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

# 소스는 실패해도 건너뛰기만 합니다. 로그의 '소스 ...: N건' 줄로 동작 여부를 확인하고,
# 계속 0건/실패인 소스는 이 목록에서 지우세요. (직접 RSS 주소는 사이트 사정으로 바뀔 수 있음)
NEWS_SOURCES = [
    # 분야별 Google News 검색. 실행 슬롯은 해당 분야의 소스만 읽습니다.
    {"name": "Google뉴스 KR 과학·환경", "google": True, "lane": "science",
     "url": _GN_KO.format(q=urllib.parse.quote_plus("과학 기후 환경 보건 연구 when:2d"))},
    {"name": "Google뉴스 US Science & Climate", "google": True, "lane": "science",
     "url": _GN_EN.format(q=urllib.parse.quote_plus("science climate environment public health research when:2d"))},
    {"name": "Google뉴스 KR 경제·일", "google": True, "lane": "economy",
     "url": _GN_KO.format(q=urllib.parse.quote_plus("경제 소비 일자리 산업 주거 when:2d"))},
    {"name": "Google뉴스 US Economy & Work", "google": True, "lane": "economy",
     "url": _GN_EN.format(q=urllib.parse.quote_plus("economy jobs wages housing cost of living when:2d"))},
    {"name": "Google뉴스 KR 사회·정책", "google": True, "lane": "society",
     "url": _GN_KO.format(q=urllib.parse.quote_plus("사회 정책 교육 노동 공동체 when:2d"))},
    {"name": "Google뉴스 US Society & Policy", "google": True, "lane": "society",
     "url": _GN_EN.format(q=urllib.parse.quote_plus("education labor public policy social change when:2d"))},
    {"name": "Google뉴스 KR 문화·미디어", "google": True, "lane": "culture",
     "url": _GN_KO.format(q=urllib.parse.quote_plus("문화 콘텐츠 미디어 게임 출판 when:2d"))},
    {"name": "Google뉴스 US Culture & Media", "google": True, "lane": "culture",
     "url": _GN_EN.format(q=urllib.parse.quote_plus("culture media entertainment games publishing when:2d"))},
    {"name": "Google뉴스 KR 일상·마음", "google": True, "lane": "daily_life",
     "url": _GN_KO.format(q=urllib.parse.quote_plus("생활 건강 심리 가족 도시 when:2d"))},
    {"name": "Google뉴스 US Everyday Life", "google": True, "lane": "daily_life",
     "url": _GN_EN.format(q=urllib.parse.quote_plus("everyday life psychology health family cities when:2d"))},
    # Google News 검색 (국내/해외, 가장 안정적인 기반)
    {"name": "Google뉴스 KR AI·테크", "google": True, "lane": "technology",
     "url": _GN_KO.format(q="AI+%ED%85%8C%ED%81%AC+%EA%B8%B0%EC%88%A0")},
    {"name": "Google뉴스 KR 과학기술 토픽", "google": True, "lane": "technology", "tech_filter": True,
     "url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtdHZHZ0pMVWlnQVAB?hl=ko&gl=KR&ceid=KR:ko"},
    {"name": "Google뉴스 US AI", "google": True, "lane": "technology",
     "url": _GN_EN.format(q="artificial+intelligence+when%3A1d")},
    {"name": "Google뉴스 US 반도체·로봇·우주", "google": True, "lane": "technology",
     "url": _GN_EN.format(q="semiconductor+OR+robotics+OR+spaceflight+when%3A1d")},
    # 해외 직접 RSS
    {"name": "TechCrunch", "lane": "technology", "url": "https://techcrunch.com/feed/"},
    {"name": "The Verge", "lane": "technology", "url": "https://www.theverge.com/rss/index.xml"},
    {"name": "Ars Technica", "lane": "technology", "url": "https://feeds.arstechnica.com/arstechnica/index"},
    {"name": "MIT Technology Review", "lane": "technology", "url": "https://www.technologyreview.com/feed/"},
    {"name": "IEEE Spectrum", "lane": "technology", "url": "https://spectrum.ieee.org/feeds/feed.rss"},
    {"name": "Hacker News", "lane": "technology", "url": "https://news.ycombinator.com/rss"},
    {"name": "BBC Technology", "lane": "technology", "url": "https://feeds.bbci.co.uk/news/technology/rss.xml"},
    # 국내 직접 RSS
    {"name": "AI타임스", "lane": "technology", "url": "https://www.aitimes.com/rss/allArticle.xml"},
    {"name": "전자신문", "lane": "technology", "url": "https://rss.etnews.com/Section901.xml"},
    # 블로터(https://www.bloter.net/feed)는 HTTP 404라 2026-10-25에 뺐다(실행 로그 '수집 실패', 로컬에서도 404/403).
]

# 게시 후보에 사용할 수 있는 출처 도메인. 도메인 이름은 끝 경계까지 비교합니다.
# 보도자료·검색 결과·커뮤니티 링크만으로는 글을 발행하지 않습니다.
TRUSTED_SOURCE_DOMAINS = {
    "science": ("nature.com", "science.org", "pnas.org", "cell.com", "who.int",
                "nih.gov", "noaa.gov", "nasa.gov", "ipcc.ch", "jpl.nasa.gov",
                "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk"),
    "economy": ("oecd.org", "imf.org", "worldbank.org", "federalreserve.gov",
                "bls.gov", "bok.or.kr", "kostat.go.kr", "kdi.re.kr",
                "reuters.com", "apnews.com", "ft.com", "bloomberg.com",
                "bbc.com", "bbc.co.uk"),
    "society": ("oecd.org", "un.org", "unesco.org", "unicef.org", "korea.kr",
                "kostat.go.kr", "kdi.re.kr", "reuters.com", "apnews.com",
                "bbc.com", "bbc.co.uk", "theguardian.com"),
    "technology": ("nist.gov", "acm.org", "ieee.org", "arxiv.org", "nature.com",
                   "science.org", "technologyreview.com", "arstechnica.com",
                   "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
                   "aitimes.com", "etnews.com"),
    "culture": ("unesco.org", "pewresearch.org", "reuters.com", "apnews.com",
                "bbc.com", "bbc.co.uk", "theguardian.com", "variety.com",
                "nytimes.com"),
    "daily_life": ("who.int", "nih.gov", "nhs.uk", "cdc.gov", "apa.org",
                   "kostat.go.kr", "korea.kr", "mfds.go.kr",
                   "foodsafetykorea.go.kr", "kca.go.kr", "consumer.go.kr",
                   "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk"),
}


def _clean_text(s, limit=300):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()[:limit]


def _parse_date(text):
    if not text:
        return None
    text = text.strip()
    try:
        dt_ = parsedate_to_datetime(text)
    except Exception:
        try:
            dt_ = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if dt_ is not None and dt_.tzinfo is None:
        dt_ = dt_.replace(tzinfo=timezone.utc)
    return dt_


def _host(url):
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return ""


def _trusted_domain(host, lane):
    return any(host == domain or host.endswith("." + domain)
               for domain in TRUSTED_SOURCE_DOMAINS.get(lane, ()))


def _resolve_article_url(url):
    """Google News 리디렉션을 따라가 게시자 원문 URL을 얻습니다."""
    if not url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as response:
            resolved = response.geturl()
        parsed = urllib.parse.urlparse(resolved)
        return resolved if parsed.scheme in {"http", "https"} and parsed.hostname else ""
    except Exception:
        return ""


def _fetch_source_excerpt(url):
    """원문 페이지의 게시자 요약을 가져옵니다. 본문 전문은 수집하지 않습니다."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read(700_000).decode("utf-8", errors="replace")
        for pattern in (
            r'<meta[^>]+(?:property|name)=["\'](?:og:description|description)["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:description|description)',
        ):
            match = re.search(pattern, raw, re.I)
            if match:
                return _clean_text(match.group(1), 1200)
    except Exception:
        pass
    return ""


def parse_feed(data):
    """RSS 2.0(item)와 Atom(entry)을 모두 처리."""
    root = ET.fromstring(data)
    items = []
    for node in root.iter():
        if node.tag.split("}")[-1] not in ("item", "entry"):
            continue

        def text_of(*names):
            for child in node:
                if child.tag.split("}")[-1] in names and (child.text or "").strip():
                    return child.text.strip()
            return ""

        link = ""
        publisher_name = ""
        publisher_url = ""
        for child in node:
            tag = child.tag.split("}")[-1]
            if tag == "link" and not link:
                link = child.get("href") or (child.text or "").strip()
            elif tag == "source":
                publisher_name = _clean_text(child.text or "", 120)
                publisher_url = child.get("url") or ""
        items.append({
            "title": _clean_text(text_of("title"), 300),
            "published": _parse_date(text_of("pubDate", "published", "updated", "date")),
            "summary": _clean_text(text_of("description", "summary", "content", "encoded")),
            "link": link,
            "publisher_name": publisher_name,
            "publisher_url": publisher_url,
        })
    return items


def fetch_news_items(editorial_lane=None, stats=None, deadline=None, clock=time.monotonic):
    """여러 소스에서 최근 기사 후보를 모아, 소스를 번갈아 섞은 목록으로 반환.
    stats(dict)를 넘기면 소스별 수집·탈락 사유 개수를 stats["sources"]에 채운다(동작은 같다).
    deadline(clock 기준 시각)을 넘기면 그 시각이 지난 뒤에는 남은 소스를 시도하지 않는다(느린 장애에서 잡 제한을 넘기지 않도록)."""
    now = datetime.datetime.now(timezone.utc)
    max_age = timedelta(hours=NEWS_MAX_AGE_HOURS)
    per_source, attempted, ok_count, time_skipped = [], 0, 0, 0
    for src in NEWS_SOURCES:
        if editorial_lane and src.get("lane") != editorial_lane:
            continue
        if deadline is not None and clock() > deadline:
            time_skipped += 1
            continue
        attempted += 1
        try:
            req = urllib.request.Request(src["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                parsed = parse_feed(resp.read())
            ok_count += 1
        except Exception as exc:
            print(f"  소스 {src['name']}: 수집 실패 ({type(exc).__name__}: {_one_line(exc, 200)})")
            if stats is not None:
                stats.setdefault("sources", []).append(
                    {"name": src["name"], "fetched": 0, "kept": 0, "drops": {},
                     "error": type(exc).__name__})
            continue
        kept = []
        drops = {}
        resolved_count = 0
        for it in parsed:
            title = it["title"]
            publisher = it.get("publisher_name") or ""
            publisher_url = it.get("publisher_url") or ""
            if src.get("google"):
                if not publisher:
                    match = re.match(r"^(.*)\s+-\s+([^-]+)$", title)
                    if match:
                        title, publisher = match.group(1).strip(), match.group(2).strip()
            if not title:
                _count(drops, "NO_TITLE")
                continue
            if src.get("tech_filter") and not is_tech_title(title):
                _count(drops, "NOT_TECH")
                continue
            pub = it["published"]
            if pub and now - pub > max_age:
                _count(drops, "AGE")
                continue
            publisher_host = _host(publisher_url)
            if publisher_host and not _trusted_domain(publisher_host, editorial_lane):
                _count(drops, "UNTRUSTED")
                continue
            if resolved_count >= 5:
                _count(drops, "UNCHECKED")
                continue
            article_url = _resolve_article_url(it["link"]) if src.get("google") else it["link"]
            resolved_count += 1
            publisher_host = publisher_host or _host(article_url)
            if not article_url:
                _count(drops, "UNRESOLVED")
                continue
            if not _trusted_domain(publisher_host, editorial_lane):
                _count(drops, "UNTRUSTED")
                continue
            article_host = _host(article_url)
            same_publisher = (article_host == publisher_host
                              or article_host.endswith("." + publisher_host)
                              or publisher_host.endswith("." + article_host))
            if not same_publisher or not _trusted_domain(article_host, editorial_lane):
                _count(drops, "HOST_MISMATCH")
                continue
            summary = it["summary"]
            if len(summary) < 100:
                summary = _fetch_source_excerpt(article_url)
            if len(summary) < 100:
                _count(drops, "SHORT_SUMMARY")
                continue
            kept.append({"title": title, "source": publisher or src["name"],
                         "link": article_url, "publisher_domain": publisher_host,
                         "summary": summary, "published": pub})
        kept.sort(key=lambda x: x["published"] or EPOCH, reverse=True)
        line = f"  소스 {src['name']}: {len(parsed)}건 중 {len(kept)}건 사용"
        if drops:
            line += f" (탈락: {_format_drops(drops)})"
        print(line)
        if stats is not None:
            stats.setdefault("sources", []).append(
                {"name": src["name"], "fetched": len(parsed), "kept": len(kept),
                 "drops": drops})
        per_source.append(kept[:10])

    if time_skipped:
        print(f"  시간 상한으로 소스 {time_skipped}개를 시도하지 않았습니다.")
        if stats is not None:
            stats["time_skipped"] = time_skipped
    if attempted and ok_count == 0:
        print("::warning::모든 뉴스 소스 수집에 실패했습니다. 네트워크/소스 주소를 확인하세요.")
    merged, seen = [], set()
    for rank in range(10):
        for lst in per_source:
            if rank < len(lst):
                it = lst[rank]
                key = it["title"].casefold()
                if key not in seen:
                    seen.add(key)
                    merged.append(it)
    return merged


def pick_topic_candidates(titles, allow_auto_topic=True, editorial_lane=None, stats=None, deadline=None,
                          clock=time.monotonic):
    """신뢰 출처 검증과 중복 검사를 통과한 기사 후보만 반환합니다.
    stats(dict)를 넘기면 소스별 개수와 함께 중복으로 탈락한 수·최종 후보 수를 채웁니다."""
    picked = []
    duplicates = 0
    for it in fetch_news_items(editorial_lane, stats=stats, deadline=deadline, clock=clock):
        if is_similar_to_any(it["title"], titles, 0.6):
            duplicates += 1
            continue
        picked.append(it)
        if len(picked) >= MAX_ATTEMPTS:
            break
    if stats is not None:
        stats["duplicates"] = duplicates
        stats["candidates"] = len(picked)
    # 출처 검증을 통과한 기사가 없으면 AI가 근거 없이 주제를 고르지 않습니다.
    return picked


def editorial_lane_order(slot, history):
    """최근 발행 편중을 줄이면서 슬롯별로 재현 가능한 확률 추첨 순서로 모든 분야를 반환합니다.
    첫 번째가 choose_editorial_lane 의 선택과 같고, 뒤쪽은 그 분야에 후보가 없을 때 시도할 대체 순서입니다."""
    lanes = list(EDITORIAL_LANES)
    recent = [item.get("lane") for item in history[-12:]
              if isinstance(item, dict) and item.get("lane") in EDITORIAL_LANES]
    counts = {lane: recent.count(lane) for lane in lanes}
    weights = {}
    for lane in lanes:
        # 최근 자주 나온 분야의 확률을 낮추되 0으로 만들지 않아 유행 분야도 계속 후보로 둡니다.
        weights[lane] = 1.0 / (1.0 + counts[lane] * 0.65)
        if recent and recent[-1] == lane:
            weights[lane] *= 0.25
        elif len(recent) > 1 and recent[-2] == lane:
            weights[lane] *= 0.6

    now = now_kst()
    latest = history[-1] if history else None
    latest_key = (latest.get("date", ""), latest.get("topic", "")) if isinstance(latest, dict) else str(latest or "")
    seed = f"{now:%Y-%m-%d}|{slot}|{len(history)}|{latest_key}"
    rng = random.Random(seed)
    remaining, order = list(lanes), []
    while remaining:
        picked = rng.choices(remaining, weights=[weights[lane] for lane in remaining], k=1)[0]
        order.append(picked)
        remaining.remove(picked)
    return order


def choose_editorial_lane(slot, history):
    """추첨 순서의 첫 분야."""
    return editorial_lane_order(slot, history)[0]


# ============================================================
# 글 생성
# ============================================================
def load_editorial_template():
    """Load the repository's reviewed writing and revision guide; fail closed if missing."""
    try:
        template = EDITORIAL_TEMPLATE_FILE.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"편집 템플릿을 읽을 수 없습니다: {EDITORIAL_TEMPLATE_FILE}") from exc
    if not template:
        raise RuntimeError("편집 템플릿이 비어 있어 게시글 생성을 중단합니다.")
    return template


def build_post_prompt(item, recent_titles, category_hint="", allow_skip=False,
                      editorial_lane="technology"):
    lane = EDITORIAL_LANES.get(editorial_lane, EDITORIAL_LANES["technology"])
    category_rule = (
        f"- 요청된 카테고리 힌트 [{category_hint}]를 우선 사용하되, 주제와 다르면 억지로 적용하지 마세요.\n"
        if category_hint else
        f"- 본문 카테고리는 한국어에서 \"{lane['kr_category']}\", 영어에서 \"{lane['en_category']}\"를 사용하세요. 글의 핵심 주제가 편집 축과 맞지 않으면 다른 주제로 다시 고르세요.\n"
    )
    if item:
        topic_text = item["title"]
        if item.get("source"):
            topic_text += f"\n[출처] {item['source']}"
        if item.get("link"):
            topic_text += f"\n[원문 URL] {item['link']}"
        if item.get("published"):
            topic_text += f"\n[원문 게시 시각] {item['published'].isoformat()}"
        if item.get("summary"):
            topic_text += ("\n[기사 요약 - 참고만 하고 문장을 그대로 옮기지 마세요]\n"
                           + item["summary"])
    else:
        topic_text = "검증된 출처가 제공되지 않았습니다. 반드시 skip을 반환하세요."
    skip_rule = ('- 이 주제가 [최근 다룬 주제/제목]과 같은 사건이나 소재라면 글을 쓰지 말고 '
                 '{"skip": true, "reason": "..."} 만 반환하세요.\n') if allow_skip else ""
    source_rule = ("- 제공된 검증 게시자 원문만 사실 근거로 쓰세요. 원문에서 확인되지 않는 주장·수치·인용·날짜·인과관계는 쓰지 마세요.\n"
                   "- 학술 연구는 동료심사 여부를 명시하고 표본·범위·한계를 설명하세요. arXiv 등의 프리프린트를 동료심사 연구처럼 표현하지 마세요.\n"
                   "- 중요한 사실 문장에는 제공된 원문 URL을 Markdown 인라인 인용으로 붙이세요. 사실과 해석·전망을 명확히 구분하세요.\n"
                   "- 제목·저자·학술지명·DOI·통계·인용문이나 출처를 추정해 만들지 마세요. 근거가 부족하면 skip을 반환하세요.\n"
                   if item and item.get("link") and item.get("source") else
                   "- 검증된 출처가 없으면 글을 만들지 말고 skip을 반환하세요.\n")
    hint = f"[카테고리 힌트] {category_hint}\n" if category_hint else ""
    editorial_template = load_editorial_template()
    return f"""
당신은 기술, 경제, 사회, 과학, 문화와 일상을 함께 읽는 교양형 매거진 'Chance_Blog'의 편집자입니다.
선택된 편집 축은 [{lane['label']}]이며, 이번 축의 중심 범위는 다음과 같습니다: {lane['focus']}.
아래 주제를 바탕으로 독창적이고 사실에 신중한 블로그 글을 한국어와 영어로 각각 작성하세요.

[주제]
{topic_text}

{hint}[최근 다룬 주제/제목 - 같은 소재와 관점 금지]
{json.dumps(recent_titles, ensure_ascii=False)}

[중요 지침]
{skip_rule}- 제목, 카테고리, 태그를 주제에 맞게 작성하세요.
- 아래 [편집 템플릿]을 실제 작성과 최종 자가 편집에 모두 적용하세요. 자연스러운 글을 위해 개인 경험이나 사람인 척하는 문장을 만들어 넣지 마세요. AI 사용을 감추거나 탐지기를 속이려 하지 마세요.
- 이 매거진은 IT 전문 매체가 아닙니다. 이번 편집 축의 주제를 중심에 두고, 기술·경제·사회·문화·환경·교육·일상 중 실제로 연결되는 다른 관점 하나를 함께 설명하세요. 억지로 연결하지 말고, 관련이 약하면 주제 자체를 더 적합한 것으로 고르세요.
- 사람들의 선택과 생활에 어떤 차이가 생기는지 구체적으로 설명하고, 누가 이익을 얻거나 비용을 부담하는지 살펴보세요. 한 분야의 전문성은 유지하되 독자가 다른 분야와 연결해 생각할 수 있게 하세요.
{category_rule}- 글은 한 편 안에서 독립적으로 이해되어야 하며, 중요한 사실 근거를 본문에 링크하고 끝에 출처 목록을 제공합니다.
- 독자가 이 주제에서 실제로 알고 싶어 할 질문에 답하고, 제목은 핵심 내용과 근거의 범위를 정확히 나타내세요. 과장·낚시성 표현은 피하세요.
- 독자에게 가장 필요한 형식(사건 설명, 해설, 비교, 연구 요약, 실용 안내 등)을 고르고, 그 형식에 맞춰 글을 구성하세요. 매번 같은 도입, 3개 소제목, 전망형 결말을 반복하지 마세요. 소제목 수와 문단 길이는 자료와 주제에 맞추고, 필요 없는 결론 요약은 생략하세요.
- 첫 문단은 주제를 자연스럽게 소개하고 독자가 얻을 답이나 핵심 사실을 분명히 보여 주세요. 본문에서 확인된 사실, 출처의 주장, 편집자의 해석과 전망을 구분하세요.
- 소스 요약을 문단별로 바꾸어 쓰는 데 그치지 말고, 근거가 허용하는 비교·맥락·한계 또는 실행 가능한 시사점을 제공하세요. 근거가 부족하면 추측으로 채우지 말고 skip을 반환하세요.
- 관용적인 AI 문구, 중요성을 부풀리는 표현, 반복되는 요약, 억지로 넣은 3단 나열은 덜어내세요. 자연스러움은 구체적인 근거와 명료한 문장에서 나오게 하세요. 오탈자·속어·가짜 개인 경험을 추가하거나 AI 사용 사실을 숨기려 하지 마세요.
- 한국어/영어 글은 각 언어에 자연스럽게 쓰고 단순 직역은 피하세요.
- 확인되지 않은 수치, 인용문, 발표 사실을 지어내지 마세요. 기사 문장을 그대로 옮기지 마세요.
{source_rule}- 본문은 충분한 설명과 분석을 포함하고 Markdown으로 작성하세요.
- 각 글의 Front Matter에 layout, title, category, tags, lang을 포함하세요.
- image는 쓰지 마세요. 대표 이미지는 시스템이 따로 채웁니다.
- image_queries: 이 글의 대표 이미지를 Unsplash에서 찾을 영어 검색어 3개.
  구체적인 것부터 일반적인 순서, 각 2~4단어, 주제를 시각적으로 나타내는
  사물/장면 위주, 사람 얼굴/로고/브랜드명/글자는 피하세요.
- kr_content, en_content에는 완전한 Markdown(Front Matter 포함)을 넣으세요.
- JSON 문자열 안의 줄바꿈과 따옴표는 유효한 JSON 규칙을 지키세요.
- JSON 객체만 반환하고 코드 펜스는 쓰지 마세요.

[편집 템플릿]
{editorial_template}

{{
  "kr_category": "{lane['kr_category']}",
  "kr_title": "한국어 제목",
  "kr_tags": ["태그1", "태그2"],
  "kr_content": "한국어 Markdown 전체",
  "en_category": "{lane['en_category']}",
  "en_title": "English Title",
  "en_tags": ["Tag1", "Tag2"],
  "en_content": "English Markdown full content",
  "image_queries": ["specific query", "broader query", "general query"]
}}
"""


def stub_post_data(topic, link=None):
    """DRY_RUN(API 키 없음)용 가짜 글. 본문 검증(최소 분량 + 원문 링크 인용)을 통과하도록 충분히 길게 만든다.
    예전에는 본문이 2자라 후보가 있으면 검증에서 실패했다(첫 분야가 비면 가려졌던 결함)."""
    t = topic or "stub topic"
    fm = "---\nlayout: post\ntitle: \"{}\"\ncategory: \"{}\"\ntags: []\n---\n\n{}"
    kr_body = "이 문단은 DRY_RUN 연습용 가짜 본문입니다. 실제 글이 아닙니다. " * 50
    en_body = "This paragraph is placeholder text used only by the dry run; it is not a real article. " * 30
    if link:
        kr_body += f"\n\n근거: [원문]({link})\n"
        en_body += f"\n\nSource: [original]({link})\n"
    return {
        "kr_category": "KR - 스텁", "kr_title": f"[스텁] {t}", "kr_tags": ["스텁"],
        "kr_content": fm.format(f"[스텁] {t}", "KR - 스텁", kr_body),
        "en_category": "EN - Stub", "en_title": f"[stub] {t}", "en_tags": ["stub"],
        "en_content": fm.format(f"[stub] {t}", "EN - Stub", en_body),
        "image_queries": ["technology", "computer hardware"],
    }


def _validate_editorial_body(content, lang, verified_source_url):
    """Reject thin drafts or drafts that cite their source only in a source list."""
    match = re.match(r"\A---\s*\n.*?\n---\s*\n(.*)\Z", content, re.S)
    body = match.group(1) if match else content
    story = re.split(r"(?im)^##\s*(?:출처|참고 자료|sources)\s*$", body, maxsplit=1)[0]
    readable = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", story)
    readable = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", readable)
    readable = re.sub(r"<[^>]+>|[`*_>#|~]", " ", readable)
    readable = re.sub(r"\s+", "", readable)
    minimum = MIN_BODY_CHARS.get(lang, MIN_BODY_CHARS["en"])
    if len(readable) < minimum:
        raise ValueError(
            f"{lang.upper()} 본문이 최소 편집 분량({minimum}자)에 미달합니다: "
            f"{len(readable)}자. 억지로 늘리지 말고 근거가 부족하면 발행을 보류하세요."
        )
    if not verified_source_url or verified_source_url not in story:
        raise ValueError(
            f"{lang.upper()} 본문에 검증된 원문 링크를 뒷받침되는 주장 가까이에 인용해야 합니다."
        )


def validate_post_data(data, kr_image, en_image, verified_source_url=None):
    for key in ("kr_category", "kr_title", "kr_content",
                "en_category", "en_title", "en_content"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"생성 결과의 {key} 값이 비었거나 문자열이 아닙니다.")
    for key in ("kr_tags", "en_tags"):
        if not isinstance(data.get(key), list):
            data[key] = []
        data[key] = [str(t).strip() for t in data[key] if str(t).strip()]

    for prefix, image_url in (("kr", kr_image), ("en", en_image)):
        html_lang = "ko" if prefix == "kr" else "en"
        content = data[f"{prefix}_content"]
        if not content.lstrip().startswith("---"):
            content = (
                "---\nlayout: post\n"
                f"title: {json.dumps(data[f'{prefix}_title'], ensure_ascii=False)}\n"
                f"category: {json.dumps(data[f'{prefix}_category'], ensure_ascii=False)}\n"
                f"tags: {json.dumps(data[f'{prefix}_tags'], ensure_ascii=False)}\n"
                f"lang: {html_lang}\nimage: {json.dumps(image_url)}\n---\n\n" + content
            )
        else:
            end = content.find("\n---", 3)
            if end != -1:
                front = content[3:end]
                body = content[end + 4:].lstrip("\n")
                front = re.sub(r"(?m)^image:\s*.*$", "", front)
                front = re.sub(r"(?m)^lang:\s*.*$", "", front)
                front = re.sub(r"\n{2,}", "\n", front).rstrip()
                front += f'\nlang: {html_lang}\nimage: "{image_url}"'
                content = f"---{front}\n---\n\n{body}"

        content = _front_matter_set(content, "category", data[f"{prefix}_category"])
        _validate_editorial_body(content, prefix, verified_source_url)

        if not re.search(r"(?m)^!\[[^\]]*\]\(", content):
            content = content.rstrip() + f"\n\n![Thumbnail]({image_url})\n"
        else:
            content = re.sub(
                r"(?m)^!\[[^\]]*\]\(https://images\.unsplash\.com/[^)]+\)",
                f"![Thumbnail]({image_url})", content, count=1)
        data[f"{prefix}_content"] = content.rstrip() + "\n"
    return data


def _front_matter_set(content, key, value):
    """Set one safely quoted scalar in an existing Markdown front matter block."""
    content = str(content or "").lstrip("\ufeff")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", content, re.S)
    if not match:
        return content
    front, body = match.groups()
    line = f"{key}: {json.dumps(str(value), ensure_ascii=False)}"
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*:\s*.*$")
    if pattern.search(front):
        front = pattern.sub(lambda _: line, front, count=1)
    else:
        front = front.rstrip() + "\n" + line
    return f"---\n{front}\n---\n\n{body.lstrip()}"


def _description_from_markdown(content, max_chars=155):
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", str(content or ""), count=1, flags=re.S)
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", paragraph)
        paragraph = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", paragraph)
        paragraph = re.sub(r"(?m)^\s{0,3}(?:#{1,6}\s*|>\s*)", "", paragraph)
        paragraph = re.sub(r"[*_`~]", "", paragraph)
        paragraph = re.sub(r"<[^>]+>", " ", paragraph)
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if len(paragraph) >= 60:
            if len(paragraph) > max_chars:
                paragraph = paragraph[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
            return paragraph
    return ""


def add_discovery_metadata(content, source=None):
    description = _description_from_markdown(content)
    if description:
        content = _front_matter_set(content, "description", description)
    if source:
        source_url = str(source.get("link") or "").strip()
        parsed = urllib.parse.urlparse(source_url)
        if (parsed.scheme in {"http", "https"} and parsed.netloc
                and source.get("source") and source.get("publisher_domain")):
            content = _front_matter_set(content, "source_name", source.get("source") or "원문")
            content = _front_matter_set(content, "source_url", source_url)
            content = _front_matter_set(content, "source_domain", source["publisher_domain"])
            body_match = re.match(r"\A---\s*\n.*?\n---\s*\n(.*)\Z", content, re.S)
            body = body_match.group(1) if body_match else content
            if source_url not in body:
                heading = "\n\n## 출처\n" if re.search(r"[가-힣]", body) else "\n\n## Sources\n"
                content = content.rstrip() + f"{heading}- [{source['source']}: {source.get('title', '원문 기사')}]({source_url})\n"
    return content


def safe_category_dir(category, prefix):
    category = str(category).strip()
    category = re.sub(r"[\x00-\x1f/\\]+", "-", category)
    category = re.sub(r"\.\.+", ".", category).strip(" .")
    if not category:
        category = f"{prefix} - Uncategorized"
    return POSTS_DIR / category


def now_kst():
    return datetime.datetime.now(KST)


def slot_state(history, now):
    """(슬롯, 코드)를 반환. 코드: DUE(만들 슬롯 있음) / OUT_OF_WINDOW(첫 게시 시각 전) /
    ALREADY_PUBLISHED(그 슬롯 글이 이미 있음). 두 가지 '할 일 없음'을 구분해 기록하기 위한 것이다."""
    started = [h for h in SLOT_HOURS if now.hour >= h]
    if not started:
        return None, "OUT_OF_WINDOW"
    slot = max(started)
    today = now.strftime("%Y-%m-%d")
    for item in history:
        if isinstance(item, dict) and item.get("date") == today and item.get("slot") == slot:
            return slot, "ALREADY_PUBLISHED"
    return slot, "DUE"


def current_due_slot(history, now):
    """지금 시각 기준으로 '이미 시작됐지만 아직 글이 없는' 가장 최근 슬롯 시각을 반환.
    스케줄 실행이 지연/누락돼도 다음 시간별 실행이 같은 슬롯을 보충한다.
    (오래된 슬롯을 한꺼번에 몰아서 만들지는 않는다)"""
    slot, state = slot_state(history, now)
    return slot if state == "DUE" else None


def _lane_report(lane, stats, found):
    """한 분야의 수집 결과를 요약 한 건으로 줄인다(받은 기사 → 통과 → 후보, 탈락 사유별 개수)."""
    sources = stats.get("sources", [])
    drops = {}
    for src in sources:
        for code, n in src.get("drops", {}).items():
            _count(drops, code, n)
    if stats.get("duplicates"):
        _count(drops, "DUPLICATE", stats["duplicates"])
    return {
        "lane": lane, "label": EDITORIAL_LANES[lane]["label"],
        "sources": len(sources),
        "failed_sources": sum(1 for s in sources if s.get("error")),
        "fetched": sum(s.get("fetched", 0) for s in sources),
        "passed": sum(s.get("kept", 0) for s in sources),
        "candidates": len(found),
        "drops": drops,
    }


def collect_candidates(titles, allow_auto_topic, lane_order, report, fallback=True,
                       clock=time.monotonic):
    """분야를 추첨 순서대로 시도해 처음으로 후보가 나온 분야와 그 후보를 반환한다.
    모든 분야가 비면 ([], 첫 분야). 이 단계는 Gemini 를 부르지 않아 비용은 수집 시간뿐이다.
    LANE_SEARCH_BUDGET_SECONDS 를 넘으면 새 분야도, 분야 안의 남은 소스도 시도하지 않는다(소스 하나가 끝나는 시간만큼은 더 걸린다).
    report 에 budget_exceeded(시간 상한으로 건너뜀)와 sources_unreachable(시도한 소스가 전부 수집 실패)을 남긴다."""
    started = clock()
    deadline = started + LANE_SEARCH_BUDGET_SECONDS
    tried = lane_order if fallback else lane_order[:1]
    attempted = failed = 0
    for index, lane in enumerate(tried):
        if index and clock() > deadline:
            report["budget_exceeded"] = True
            print(f"::warning::분야 대체 시도를 시간 상한({LANE_SEARCH_BUDGET_SECONDS}초)에서 멈춥니다. "
                  f"{len(tried) - index}개 분야는 시도하지 못했습니다.")
            break
        if index:
            print(f"편집 축 대체 시도: {EDITORIAL_LANES[lane]['label']}")
        stats = {}
        found = pick_topic_candidates(titles, allow_auto_topic, lane, stats=stats,
                                      deadline=deadline, clock=clock)
        lane_report = _lane_report(lane, stats, found)
        report["lanes"].append(lane_report)
        attempted += lane_report["sources"]
        failed += lane_report["failed_sources"]
        if stats.get("time_skipped"):
            report["budget_exceeded"] = True
        if found:
            if index:
                print(f"::notice::'{EDITORIAL_LANES[lane_order[0]]['label']}' 분야에 후보가 없어 "
                      f"'{lane_report['label']}' 분야로 대체했습니다.")
            return found, lane
        print(skip_line("LANE_EMPTY", lane=lane, sources=lane_report["sources"],
                        failed=lane_report["failed_sources"], fetched=lane_report["fetched"],
                        passed=lane_report["passed"], reasons=lane_report["drops"]))
    report["sources_unreachable"] = attempted > 0 and failed == attempted
    return [], lane_order[0]


def generate_blog_posts(topic_override=None, category_hint="", slot=None,
                        allow_auto_topic=True, report=None):
    """KR/EN 글 한 쌍을 만든다. 만들면 (kr_path, en_path), 만들 수 없으면 None.
    report(dict)를 넘기면 분야별 수집 결과와 최종 결과 코드(outcome)를 채워 준다."""
    report = report if report is not None else {}
    report.setdefault("lanes", [])
    posts = load_posts()
    history = read_history()
    lane_order = editorial_lane_order(slot, history)
    editorial_lane = lane_order[0]
    print(f"편집 축: {EDITORIAL_LANES[editorial_lane]['label']}")
    titles = existing_titles(history, posts)
    used = used_keys_from_posts(posts)
    for item in history:
        if isinstance(item, dict):
            for k in ("kr_image", "en_image"):
                if item.get(k):
                    used.add(image_key(item[k]))

    recent_titles = titles[-30:]
    data, selected, selected_item = None, None, None
    if topic_override:
        verified = fetch_news_items(editorial_lane)
        matched = next((it for it in verified
                        if is_similar_to_any(topic_override, [it["title"]], 0.35)), None)
        if not matched:
            print("요청 주제와 직접 연결되고 출처 검증을 통과한 기사가 없습니다. 발행을 중단합니다.")
            report["outcome"] = "NO_MATCH"
            return None
        candidates = [dict(matched, title=topic_override)]
    else:
        candidates, editorial_lane = collect_candidates(
            titles, allow_auto_topic, lane_order, report)
    report["lane"] = editorial_lane
    report["lane_label"] = EDITORIAL_LANES[editorial_lane]["label"]
    if not candidates:
        print("쓸 만한 새 기사가 없습니다. 글을 만들지 않습니다.")
        # 이상 신호(빨강)는 '소스에 접속하지 못함'과 '모든 분야에 검증된 기사가 한 건도 없음'이다.
        # 검증된 기사는 있었지만 전부 기존 글과 비슷하면 뉴스가 뜸한 것이라 경고 수준이고, 시간 상한으로 일부만 시도했을 때도 경고다.
        if report.get("sources_unreachable"):
            report["outcome"] = "SOURCES_UNREACHABLE"
        elif report.get("budget_exceeded"):
            report["outcome"] = "NO_CANDIDATES"
        elif any(lane["passed"] > 0 for lane in report.get("lanes", [])):
            report["outcome"] = "ALL_DUPLICATES"
        else:
            report["outcome"] = "ALL_LANES_EMPTY"
        return None
    gate_rejects = report["gate_rejects"] = []
    for item in candidates:
        topic = item["title"] if item else None
        src_label = f" [{_one_line(item['source'], 60)}]" if item and item.get("source") else ""
        print(f"주제 시도: {_one_line(topic or '(자동 선정)', 200)}{src_label}")
        try:
            if STUB_GEMINI:
                candidate = stub_post_data(topic, (item or {}).get("link"))
            else:
                # 모든 모델이 실패하면 RuntimeError 로 그대로 올라간다(인프라 장애 = 빨강).
                resp = call_gemini_with_fallback(build_post_prompt(
                    item, recent_titles, category_hint, allow_skip=not topic_override,
                    editorial_lane=editorial_lane))
                candidate = extract_json_object(resp.text)
        except ValueError as exc:  # 모델이 JSON 을 못 맞춘 것은 이 후보의 탈락이다
            reason = _one_line(exc, 200)
            print(f"  Gemini 응답을 읽지 못해 이 후보는 건너뜀: {reason}")
            gate_rejects.append(reason)
            continue
        if candidate.get("skip") is True:
            print(f"  Gemini가 중복 주제로 판단해 건너뜀: {_one_line(candidate.get('reason', ''))}")
            continue
        kr_t, en_t = str(candidate.get("kr_title", "")), str(candidate.get("en_title", ""))
        if not topic_override and (is_similar_to_any(kr_t, titles, 0.7)
                                   or is_similar_to_any(en_t, titles, 0.7)):
            print(f"  생성된 제목이 기존 글과 비슷해 폐기: {_one_line(kr_t, 150)} / {_one_line(en_t, 150)}")
            continue
        try:
            # 본문 검증(분량·원문 링크 인용)은 이미지를 고르기 전에 먼저 한다: 탈락한 후보에 Unsplash 호출을 쓰지 않고,
            # 첫 후보의 본문이 얇다는 이유로 실행 전체를 빨갛게 만들지 않고 다음 후보를 시도한다(검증 기준은 그대로).
            validate_post_data(copy.deepcopy(candidate), "https://example.invalid/kr.jpg",
                               "https://example.invalid/en.jpg",
                               verified_source_url=(item or {}).get("link"))
        except ValueError as exc:
            reason = _one_line(exc, 200)
            print(f"  본문 검증 탈락: {reason}")
            gate_rejects.append(reason)
            continue
        data, selected, selected_item = candidate, topic, item
        break
    if data is None:
        report["outcome"] = "ALL_REJECTED"
        if not topic_override and not allow_auto_topic:
            print("통과한 후보가 없습니다(중복·Gemini 건너뜀·본문 검증 탈락). 글을 만들지 않습니다.")
            return None
        raise RuntimeError("후보가 모두 탈락해 글을 만들지 못했습니다(중복·Gemini 건너뜀·본문 검증 탈락).")

    if not selected_item or not selected_item.get("link") or not selected_item.get("publisher_domain"):
        raise RuntimeError("검증된 게시자 원문이 없어 글을 저장하지 않습니다.")

    queries = [q for q in data.get("image_queries", []) if isinstance(q, str)]
    if not queries:
        queries = ["technology", "computer hardware"]
    images = pick_images(queries, used, 2, allow_pool=True)
    if len(images) < 2:
        raise RuntimeError("사용 가능한 대표 이미지를 2개 확보하지 못했습니다. "
                           "글을 저장하지 않습니다.")
    kr_image, en_image = images
    data = validate_post_data(
        data, kr_image, en_image,
        verified_source_url=(selected_item or {}).get("link"),
    )

    now = now_kst()
    date_str, time_str = now.strftime("%Y-%m-%d"), now.strftime("%H%M%S")
    selected_item["title"] = selected_item.get("title") or selected or "원문 기사"
    data["kr_content"] = add_discovery_metadata(data["kr_content"], selected_item)
    data["en_content"] = add_discovery_metadata(data["en_content"], selected_item)
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
        "kr_image": kr_image, "en_image": en_image, "slot": slot,
        "lane": editorial_lane,
        "source": (selected_item or {}).get("source", ""),
        "source_url": (selected_item or {}).get("link", ""),
    })
    write_history(history)
    trigger_download(kr_image)
    trigger_download(en_image)
    report.update(outcome="PUBLISHED", title=data["kr_title"], en_title=data["en_title"],
                  source=(selected_item or {}).get("source", ""),
                  paths=[str(kr_path), str(en_path)])
    print("블로그 글 생성 완료" + (" (DRY_RUN: 파일·기록은 저장되지 않았습니다):" if DRY_RUN else ":"))
    print(f"- KR: {kr_path}\n- EN: {en_path}\n- 편집 축: {EDITORIAL_LANES[editorial_lane]['label']}\n- 주제: {_one_line(selected or '(자동 선정)', 200)}")
    print(f"- 이미지: {kr_image}\n         {en_image}")
    return kr_path, en_path


# ============================================================
# 진입점
# ============================================================
OUTCOME_TEXT = {
    "PUBLISHED": "글을 만들었습니다",
    "ALL_LANES_EMPTY": "모든 분야를 시도했지만 검증을 통과한 기사가 한 건도 없습니다",
    "SOURCES_UNREACHABLE": "뉴스 소스에 접속하지 못했습니다(시도한 소스가 모두 수집 실패)",
    "ALL_DUPLICATES": "검증된 기사는 있었지만 모두 이미 쓴 글과 비슷해 새 글감이 없습니다(뉴스가 뜸한 때)",
    "NO_CANDIDATES": "시간 상한으로 일부 분야만 시도했고 후보를 찾지 못했습니다",
    "ALL_REJECTED": "후보는 있었지만 전부 탈락했습니다(Gemini 건너뜀, 제목이 기존 글과 비슷, 또는 본문 검증 탈락)",
    "NO_MATCH": "요청 주제와 연결되는 검증된 기사가 없습니다",
}


def render_run_summary(event, now, slot, report):
    """실행 요약(마크다운). 건수와 코드만 쓴다 — 비밀·수익·방문 수치 금지(G-O7)."""
    outcome = report.get("outcome", "UNKNOWN")
    mode = "스케줄" if event == "schedule" else "수동"
    if DRY_RUN:
        mode += " (DRY_RUN: 파일·기록 저장 안 함)"
    lines = ["### Chance_Blog 실행 요약",
             f"- 실행: {mode} · {now:%Y-%m-%d %H:%M} KST" + (f" · {slot}시 슬롯" if slot is not None else ""),
             f"- 결과: **{outcome}** — {OUTCOME_TEXT.get(outcome, '알 수 없음')}"]
    if DRY_RUN:  # 연습 실행이 한도를 썼는지 요약에서 바로 보이게 한다(기본은 가짜 응답, 실제 호출은 real_ai 체크)
        lines.append("- AI 응답: " + ("가짜(스텁) — Gemini를 호출하지 않았습니다(실제 호출로 연습하려면 수동 실행에서 real_ai 를 체크)"
                                      if STUB_GEMINI else "실제 Gemini 호출 — 연습 실행이지만 무료 한도를 씁니다"))
    over = report.get("manual_over_cap")
    if over:
        lines.append(f"- 경고: 수동 실행은 게시 시각·하루 상한을 따지지 않습니다 — 오늘({over['date']}) 이미 {over['posted']}건이 "
                     f"게시되어 상한({over['cap']}건) 이상입니다")
    if outcome == "PUBLISHED":
        lines.append(f"- 제목: {_md_cell(report.get('title', ''))}")
        lines.append(f"- 편집 축: {report.get('lane_label', '')} · 출처: {_md_cell(report.get('source', ''), 60)}")
        lines.append("- 파일: " + ", ".join(f"`{str(p).replace(chr(96), '')}`" for p in report.get("paths", [])))
    calls = report.get("gemini_calls") or {}
    if calls.get("attempts"):
        lines.append(f"- Gemini 호출: {calls['attempts']}회(실패 {calls.get('failed', 0)}회)")
    rejects = report.get("gate_rejects", [])
    if rejects:
        lines.append(f"- 후보 탈락 {len(rejects)}건(본문 검증·응답 형식): " + " / ".join(_md_cell(r, 100) for r in rejects[:3]))
    lanes = report.get("lanes", [])
    if lanes:
        lines += ["", "| 분야 | 소스 | 받은 기사 | 검증 통과 | 후보 | 탈락 사유(개수) |",
                  "|---|---|---|---|---|---|"]
        for lane in lanes:
            drops = _format_drops(lane["drops"]) or "-"
            failed = f" (수집 실패 {lane['failed_sources']})" if lane["failed_sources"] else ""
            lines.append(f"| {lane['label']} | {lane['sources']}{failed} | {lane['fetched']} | "
                         f"{lane['passed']} | {lane['candidates']} | {drops} |")
        if len(lanes) > 1:
            lines.append(f"\n분야 {len(lanes)}개를 차례로 시도했습니다(처음 추첨된 분야에 후보가 없으면 다음 분야).")
        codes = sorted({code for lane in lanes for code in lane["drops"]})
        if codes:
            lines.append("\n탈락 사유 코드: " + " · ".join(f"{c}={DROP_LABELS.get(c, c)}" for c in codes))
    return "\n".join(lines)


def finish_run(result, report, event, now, slot=None):
    """실행 결과를 로그·요약으로 남기고 종료 정책을 적용한다(docs/ARCHITECTURE.md '스킵 코드').
    - 글을 만들었음: 정상
    - 후보는 있었으나 전부 탈락, 검증된 기사는 있었지만 모두 중복(뉴스가 뜸함), 시간 상한으로 일부만 시도: 초록 + ::warning::
    - 소스에 접속하지 못함, 또는 모든 분야에 검증된 기사가 한 건도 없음: 빨강(종료 1) — 발행하려던 실행이 0건으로 끝난 이상 신호"""
    if result is not None:
        report.setdefault("outcome", "PUBLISHED")
    outcome = report.get("outcome", "UNKNOWN")
    report.setdefault("gemini_calls", dict(GEMINI_CALLS))
    write_step_summary(render_run_summary(event, now, slot, report))
    if result is not None:
        return
    where = f"{slot}시 슬롯" if slot is not None else "수동 실행"
    if outcome in ("ALL_LANES_EMPTY", "SOURCES_UNREACHABLE"):
        print(skip_line(outcome, lanes_tried=len(report.get("lanes", []))))
        print(f"::error::{where}: {OUTCOME_TEXT[outcome]}. 실행 요약의 탈락 사유와 수집 실패 개수를 확인하세요.")
        raise SystemExit(1)
    print(skip_line(outcome, lanes_tried=len(report.get("lanes", []))))
    print(f"::warning::{where}: {OUTCOME_TEXT.get(outcome, '글을 만들지 못했습니다')}. "
          "다음 실행에서 다시 시도합니다.")


def daily_cap():
    """pipeline/blogs.json 에서 chance 블로그의 하루 게시 상한(limits.max_posts_per_day). 읽지 못하면 None."""
    from pipeline import registry
    try:
        return int(registry.get_blog(registry.load_registry(), "chance")["limits"]["max_posts_per_day"])
    except (registry.RegistryError, KeyError, TypeError, ValueError):
        return None


def note_manual_over_cap(report):
    """수동 실제 실행은 게시 시각 판단(slot_state)과 하루 상한을 모두 건너뛴다. 운영자가 일부러 더 게시하려는 것일 수 있어 막지 않고(동작은
    그대로), 오늘 이미 게시된 글이 상한 이상이면 경고 주석과 요약 줄만 남긴다. 연습 실행은 게시하지 않으므로 하지 않는다."""
    if DRY_RUN:
        return
    cap = daily_cap()
    if cap is None:
        print("하루 게시 상한을 읽지 못해 수동 실행의 상한 초과 경고를 건너뜁니다.")
        return
    today = now_kst().strftime("%Y-%m-%d")
    posted = sum(1 for item in read_history() if isinstance(item, dict) and item.get("date") == today)
    if posted >= cap:
        report["manual_over_cap"] = {"date": today, "posted": posted, "cap": cap}
        print(f"::warning::수동 실행: 오늘({today}) 이미 {posted}건이 게시되어 하루 상한({cap}건) 이상입니다. "
              "수동 실행은 게시 시각·하루 상한을 따지지 않고 글을 만듭니다(막지 않습니다).")


def main():
    if _pause_on():
        print(skip_line("PAUSED", var="PIPELINE_PAUSE"))
        print("[일시정지] PIPELINE_PAUSE 가 켜져 있어 실행하지 않습니다.")
        print("::notice::PIPELINE_PAUSE 가 켜져 있어 Chance_Blog 실행을 건너뛰었습니다.")
        write_step_summary("### Chance_Blog 실행 요약\n- 결과: **일시정지** — "
                           "저장소 변수 PIPELINE_PAUSE 가 켜져 있습니다.")
        return
    if STUB_GEMINI and not DRY_RUN:
        raise RuntimeError(
            "GEMINI_API_KEY 환경 변수가 없습니다. "
            "Settings > Secrets and variables > Actions에서 확인하세요.")
    if DRY_RUN:
        print(f"[DRY_RUN] 시작 (Gemini={'스텁' if STUB_GEMINI else '실제'}, "
              f"Unsplash={'스텁' if STUB_UNSPLASH else '실제'}) - 파일은 변경되지 않습니다.")
    if FIX_IMAGES:
        write_step_summary(f"### Chance_Blog 실행 요약\n- {fix_images()}")
    elif EVENT_NAME == "schedule":
        now = now_kst()
        slot, state = slot_state(read_history(), now)
        if state != "DUE":
            reason = ("첫 게시 시각 전" if state == "OUT_OF_WINDOW"
                      else f"{slot}시 슬롯 글이 이미 있음")
            print(skip_line(state, now=now.isoformat(timespec="minutes"),
                            slots=",".join(str(h) for h in SLOT_HOURS)))
            print(f"[스케줄] {now:%Y-%m-%d %H:%M} KST - 지금 만들 글이 없습니다 "
                  f"({reason}; 게시 시각 KST {SLOT_HOURS}시).")
            write_step_summary(f"### Chance_Blog 실행 요약\n- 실행: 스케줄 · {now:%Y-%m-%d %H:%M} KST\n"
                               f"- 결과: **{state}** — {reason}(정상 건너뜀)")
            return
        print(f"[스케줄] {now:%Y-%m-%d %H:%M} KST - {slot}시 슬롯 글을 생성합니다.")
        report = {}
        result = generate_blog_posts(slot=slot, allow_auto_topic=False, report=report)
        finish_run(result, report, "schedule", now, slot)
    else:
        report = {}
        note_manual_over_cap(report)
        result = generate_blog_posts(report=report)
        finish_run(result, report, EVENT_NAME or "manual", now_kst())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"작업 실패: {type(exc).__name__}: {_one_line(exc, 600)}")
        write_step_summary("### Chance_Blog 실행 요약\n"
                           f"- 결과: **실패** — {type(exc).__name__} (원인은 이 단계의 로그를 보세요)")
        raise
