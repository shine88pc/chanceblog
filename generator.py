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

from pipeline import drafts  # 승인 흐름(레지스트리 publish_flow: pr)의 이름·판정 규칙. direct(기본)에서는 흐름을 읽는 것 말고 아무것도 하지 않는다
from pipeline.llm import CallLog, scrub  # Gemini 요청 기록·시크릿 가리기는 Blogger·이슈 수정과 같은 코드를 쓴다(D-52)

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
# 영문 낱말 경계는 ASCII 글자·숫자 기준이다. 파이썬의 \b 는 한글도 낱말 글자로 봐서 'AI가'·'생성AI' 처럼 한글이 붙은 말을 놓친다(Dubai·Chipotle 처럼 영문 속에 든 것만 거른다).
TECH_EN = re.compile(
    r"(?<![A-Za-z0-9])(ai|gpu|cpu|llm|chatgpt|openai|nvidia|5g|6g|chip|robot|quantum|"
    r"software|cloud|startup|cyber|satellite|rocket)(?![A-Za-z0-9])", re.I)

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
# 요청별 기록(요청 모델·응답 모델·결과 종류·소요·토큰, 실패 때는 코드·상태·본문 600자). 로그 한 줄씩 남기고 실행 요약에서 접어 쓴다.
# 장부 파일은 만들지 않는다. 호출 수는 위 GEMINI_CALLS 가 세고, 이 기록은 그 내역이다. 이 실행의 Gemini 키는 로그에 글자 그대로 나가지 않는다.
CALL_LOG = CallLog(label="chance", purpose="post", out=print, secrets=(API_KEY,))


def _scrub(text):
    """로그·예외 문구에 쓰기 전에 비밀을 가린다: 비밀 패턴(mask) + 프로젝트 번호 + 이 실행의 Gemini 키(글자 그대로)."""
    return scrub(text, (API_KEY,))


def call_gemini_with_fallback(prompt):
    errors = []
    for model_name in MODEL_CANDIDATES:
        started = time.monotonic()
        response, failure, usable = None, None, False
        try:
            print(f"Gemini 모델 호출 시도: {model_name}")
            GEMINI_CALLS["attempts"] += 1
            response = get_client().models.generate_content(
                model=model_name, contents=prompt)
            text = getattr(response, "text", None)
            usable = bool(text and text.strip())
        except Exception as exc:
            failure = exc
        elapsed = time.monotonic() - started   # 기록은 try 밖에서 한다: 기록 때문에 호출 실패로 오인되는 일이 없게
        if failure is None:
            if usable:
                print(f"Gemini 모델 호출 성공: {model_name}")
                CALL_LOG.success(model_name, elapsed, response)
                return response
            GEMINI_CALLS["failed"] += 1
            errors.append(f"{model_name}: 응답 텍스트 없음")
            CALL_LOG.empty(model_name, elapsed, response)
        else:
            GEMINI_CALLS["failed"] += 1
            errors.append(f"{model_name}: {_scrub(failure)}")   # 이 문구는 예외 메시지(트레이스백·`작업 실패` 줄)로 나가므로 가린 것을 쓴다
            print(f"Gemini 모델 호출 실패: {model_name} - {_one_line(_scrub(failure))}")
            CALL_LOG.failure(model_name, elapsed, failure)
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


# 마지막으로 관측한 Unsplash 응답 헤더(X-Ratelimit-Remaining·X-Ratelimit-Limit). 시간당 한도(데모 앱 50회)를 얼마나 썼는지 보려는
# 측정값이며 동작에는 영향이 없다. 응답에 헤더가 없으면 이전 값을 그대로 둔다.
UNSPLASH_RATE = {"remaining": None, "limit": None}


def _note_unsplash_rate(headers):
    if headers is None:
        return
    for key, header in (("remaining", "X-Ratelimit-Remaining"), ("limit", "X-Ratelimit-Limit")):
        try:
            value = headers.get(header)
        except AttributeError:  # get 을 지원하지 않는 이상한 객체
            return
        if isinstance(value, str) and re.fullmatch(r"\d{1,7}", value.strip()):
            UNSPLASH_RATE[key] = int(value.strip())


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
    headers = None
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            headers = getattr(resp, "headers", None)
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        _note_unsplash_rate(getattr(exc, "headers", None))
        print(f"Unsplash API 오류 {exc.code} (query={query!r}) "
              "- 403/429면 시간당 호출 한도 초과일 수 있습니다.")
        return []
    except Exception as exc:
        print(f"Unsplash 호출 실패 (query={query!r}): {_one_line(exc, 200)}")
        return []
    _note_unsplash_rate(headers)

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
        with CALL_LOG.purposed("image-queries"):
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


# 공공기관·개방 라이선스 소스는 주말에 발표가 없어 36시간이면 토·일·월요일 슬롯이 자주 비었다(2026-10-26 조사). 72시간이면 금요일 발표가 월요일 슬롯까지 닿는다.
# 같은 기사를 두 번 쓰지 않는 것은 이력과 제목 유사도 검사가 맡는다.
NEWS_MAX_AGE_HOURS = 72
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
    "EXCLUDED": "소스별 제외 규칙(약관·글감 부적합)",
    "OFF_TOPIC": "이 분야 주제어와 맞지 않음",
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

# 소스는 실패해도 건너뛰기만 합니다. 로그의 '소스 ...: N건' 줄로 동작 여부를 확인하고,
# 계속 0건/실패인 소스는 이 목록에서 지우세요. (직접 RSS 주소는 사이트 사정으로 바뀔 수 있음)
#
# 약관 점검(terms): 소스마다 공식 약관·이용 안내를 읽은 결과를 적는다(법률 판단이 아니다).
#   allowed    출처를 밝히고 요약해 새 글을 쓰는 이 용도가 허용된다고 읽은 소스. 확인한 날짜와 근거 쪽 주소를 함께 적는다.
#   pending    약관은 허용하지만 아직 채우지 못한 조건(blocker)이 있어 읽지 않고 건너뛴다(로그에 이유가 한 줄 남는다). 조건을 채우고 운영자가 확인하면 allowed 로 바꾼다.
#   unverified 아직 약관을 읽지 못했거나 허용인지 금지인지 불명확한 기존 소스(유예). 지금은 쓰는 소스가 없다(마지막이던 전자신문을 2026-10-26에 뺐다). 새로 늘릴 수 없다(tests/test_generator_slots.py SourceListTest).
# 이 용도를 금지·허가 필요로 읽은 매체(BBC·Guardian·Nature·MIT Technology Review·AI타임스)와 robots.txt 로 AI 크롤러를 막아 운영자가 접근하지 않기로 한
# 매체(Ars Technica·IEEE)는 TERMS_BLOCKED_DOMAINS 로 막고
# 소스에도 신뢰 목록에도 두지 않는다. 전자신문은 콘텐츠 이용에 정식 계약·사용료가 필요해 운영자 결정(2026-10-26 "무료 자동화 기반" 취지에 맞지 않음)으로 같은 목록에 올렸다.
#
# 소스별 선택 키(모두 생략 가능):
#   exclude_title  제목이 이 정규식과 맞으면 쓰지 않는다(EXCLUDED). 약관이 빼라고 한 것, 글감이 못 되는 공지·퀴즈 등.
#   exclude_link   기사 주소가 이 정규식과 맞으면 쓰지 않는다(EXCLUDED). 글 종류가 주소 경로에 드러나는 피드(뉴스레터 모음, 사진 설명 쪽).
#   exclude_tags   피드 분류 태그 중 하나가 이 정규식과 맞으면 쓰지 않는다(EXCLUDED).
#   topic_regex    제목·분류 태그에 이 정규식과 맞는 말이 없으면 쓰지 않는다(OFF_TOPIC). 여러 주제가 섞인 피드를 분야에 맞춘다.
#   no_page_fetch  요약이 짧아도 기사 페이지를 따로 읽지 않는다(자동 수집을 막는 약관).
#   notice         글 끝에 붙일 고지문(ko·en). 소스 약관이 요구하는 'AI 작성, 검토·승인 받지 않음' 안내.
#   citation       글 끝에 붙일 인용 한 줄의 틀({title}·{date}·{url}). 소스 약관이 정한 인용 형식(Pew).
#   prompt_rule    글 작성 지침에 한 줄 더하는 소스별 약관 조건(요약에 없는 것을 채우지 않는 소스와 무관한 규칙은 GROUNDING_RULES 한 곳에 둔다).
#   display_name   글에 보이는 출처 이름(생략하면 name). 한 게시자의 피드를 분야별로 나눠 읽을 때 name 은 달라야 해서 둔다.
#   page_delay     기사 페이지를 연달아 읽을 때 사이에 기다릴 초(사이트의 Crawl-delay 를 지킨다).
# 해외(미국 외) 소스의 공통 약관 조건(2026-10-26, 조사 보고서 R1·R2에서 약관·robots.txt·피드를 직접 읽어 확인).
#
# 유럽연합 집행위원회 계열: 법적 고지(https://commission.europa.eu/legal-notice_en)는 "달리 표시하지 않은 한 CC BY 4.0이며 적절한 출처 표시와
# 변경 사실 표시를 조건으로 재사용을 허용한다"고 하고, 사람 얼굴이 나오는 자료·제3자 자료·로고·상표는 제외한다(그래서 글만 쓰고 이미지는 쓰지 않는다).
# Energy·Environment·JRC·디지털 전략 사이트는 바닥글이 같은 고지로 연결되고 robots.txt 에 AI 크롤러 제한이 없다. Eurostat 소식은 Eurostat 자체
# 고지(출처 표기·면책 문구 별도)가 있어 `exclude_link` 로 뺀다. 피드에 섞여 드는 EIB·ACER 기사는 이 고지의 대상이 아니라 신뢰 목록에 없는 주소라 떨어진다.
_EC_TERMS = {"status": "allowed", "checked": "2026-10-26", "url": "https://commission.europa.eu/legal-notice_en"}
_CC_BY = "https://creativecommons.org/licenses/by/4.0/"
_EC_NOTICE = {
    "ko": "이 글은 AI 도구가 유럽연합 집행위원회(European Commission)가 공개한 자료를 요약·재구성해 작성했으며 원문에서 바뀐 부분이 있습니다. "
          "원문은 CC BY 4.0 라이선스(" + _CC_BY + "deed.ko)로 제공됩니다. 집행위원회는 이 글을 검토하거나 보증하지 않았습니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published by the European Commission; changes were made to the original. "
          "The original is licensed under CC BY 4.0 (" + _CC_BY + "). The European Commission has not reviewed or endorsed this article."}
# 건강·의료 주제의 안전 지침(Chance 의 일상·마음 분야와 건강 관련 정책·통계 글). 통계·정책 사실만 전하고 의학적 조언은 하지 않는다("의심스러우면 게시하지 않는다").
HEALTH_RULE = "건강·의료 정보는 정책과 통계 사실만 전하고 진단·치료·복용·예방 효과를 조언하지 마세요."
# 글 근거 보강(D-77): 검증된 출처가 있는 모든 글감의 작성 지침에 소스와 상관없이 붙는 공통 규칙(build_post_prompt 가 소스별 규칙 앞에 넣는다).
# 소스별 `prompt_rule` 은 그 소스의 약관 조건(보증 암시 금지·링크 글자 등)과 고유한 구분만 담고, '요약에 없는 것을 채우지 않는다'는 규칙은 여기 한 곳에 둔다
# (예전에는 집행위원회·GOV.UK·통계청 규칙이 같은 말을 따로 적었다). 2026-10-27 9시 슬롯 글(DG Energy)이 요약 한 문장(194자)만 받고 약 5,000자를 쓰면서 원문에 없는
# 원화 환산과 평가 기준·절차 서술을 채웠다. 원문 발췌를 읽을지는 운영자 결정이라 수집 방식은 그대로 두고 지침으로만 막는다.
GROUNDING_RULES = (
    "독자를 위한 것이라도 통화·단위를 환산하거나 숫자를 반올림·추정하지 마세요(예: 유로를 원화로, 마일을 킬로미터로 바꾸지 마세요). 요약에 적힌 수치·단위·기준 시점을 그대로 쓰세요.",
    "요약에 없는 평가 기준·심사 절차·일정·시행 시기·금액·예산 대비 배수·참여 국가 수·법적 효력은 쓰지 마세요. "
    "배경 설명이 필요하면 '일반적으로 …'처럼 출처에 없는 일반론임을 드러내고, 구체적인 수치·고유명사는 지어내지 마세요.",
    "출처에 없는 내용(원인·전망·절차 등)을 출처 기관이 말하거나 밝힌 것, 하기로 한 일처럼 쓰지 마세요.",
)
_EC_PROMPT_RULE = ("집행위원회의 제안·협의·계획과 이미 확정된 법·결정을 구분하세요. "
                   "원문의 의미를 왜곡하지 말고, 집행위원회가 이 글을 검토하거나 보증한 것처럼 쓰지 마세요. " + HEALTH_RULE)
# 집행위원회 피드에서 뺄 기사 주소: Eurostat 소식(Eurostat 자체 고지가 따로 있음), Horizon 매거진 기사(2026-10-26 검증이 DG Environment 피드에 섞여 드는 것을 찾음),
# Press Corner 보도자료(ec.europa.eu/commission/presscorner — 앱 바닥글에 법적 고지·라이선스 링크가 없어 재사용 조건을 확인하지 못했다. 불명확은 유예한다).
# Horizon 은 재게시에 원 기자 이름·원문 링크·바닥글 문구를 요구하는데 피드의 기자 이름(dc:creator)을 아직 읽지 않아 지킬 수 없다.
_EC_EXCLUDE_LINK = r"/eurostat/|/horizon-magazine/|/commission/presscorner/"
# 연설·성명·공동 선언·기자회견 발언은 글감이 못 된다(집행위원회 소스 전부).
_EC_EXCLUDE_STATEMENTS = (r"^(?:joint )?statements?\b|^speech(?:es)?\b|\b(?:opening |closing )?remarks\b|\bleaders[’']? (?:joint )?statement\b"
                          r"|\bjoint declaration\b|\bdeclaration (?:on|by|from)\b|\bjoint press conference\b")
# 위원·부위원장 방문 예고("Commissioner Jørgensen in Hungary to …", "Executive Vice-President Ribera visits …")와 홍보성 신청 안내("Apply now…", "Turning 18? Apply for …")도 글감이 못 된다.
# 제목 가운데의 "must apply for authorisation" 같은 정책 기사는 살린다.
_EC_EXCLUDE_VISITS = r"^(?:(?:executive )?vice-president|commissioner) [\w’'-]+(?: [\w’'-]+)? (?:in|visits?|meets?|travels?|to (?:visit|meet|address))\b"
_EC_EXCLUDE_APPLY = r"\bapply now\b|(?:^|[?:!.] )apply for\b"


def _ec_citation(creator):
    """CC BY 4.0 출처 표시 한 줄: 제목·게시 기관·날짜·원문 주소·저작권 표시·라이선스 링크. {title}·{date}·{url} 은 글을 쓸 때 채운다."""
    return "“{title}.” " + creator + ", {date} <{url}>. © European Union, licensed under CC BY 4.0 (" + _CC_BY + ")."


# Statistics Canada Open Licence(https://www.statcan.gc.ca/en/terms-conditions/open-licence): 상업 이용·재가공(Value-added Products)을 허용하고,
# 재가공물에는 "Adapted from Statistics Canada, <상품명>, <기준일>. This does not constitute an endorsement by Statistics Canada of this product."(코드는 상품명 자리에 피드 제목을, 기준일 자리에 발표일을 채운다)
# 문구를 넣으라고 한다. 정보를 정확히 옮기고(reproduce accurately) 통계청이 보증하는 것처럼 보이게 하지 말며 통계청 이름·로고·문장(紋章)·기타 상징·도메인 이름을 서면 허가 없이 쓰지 말라는 조건("Advertising and Publicity")이 있다.
# 약관에 출처 표기 예외 문구는 없다 — 필수 출처 문구가 통계청 이름을 쓰게 하므로 이름은 출처를 밝히는 용도(필수 문구·고지문·'통계청 발표' 링크 글자·출처 목록)로만 쓰고 제목·홍보 문구에는 쓰지 않는다는 것은 이 코드의 해석이다(2026-10-26 약관 검증 지적).
# 피드 하나(The Daily 전체 주제)를 분야별 주제어로 나눠 세 소스로 읽는다. 항목 제목이 Atom type="xhtml"이라 parse_feed 가 자식 요소까지 읽는다.
_STATCAN_FEED = "https://www150.statcan.gc.ca/n1/rss/dai-quo/0-eng.atom"
_STATCAN_TERMS = {"status": "allowed", "checked": "2026-10-26", "url": "https://www.statcan.gc.ca/en/terms-conditions/open-licence"}
_STATCAN_CITATION = "Adapted from Statistics Canada, {title}, {date}. This does not constitute an endorsement by Statistics Canada of this product."
_STATCAN_NOTICE = {
    "ko": "이 글은 AI 도구가 캐나다 통계청(Statistics Canada)이 발표한 자료를 바탕으로 재구성해 작성했습니다. 통계청은 이 글을 검토하거나 보증하지 않았으며, 수치와 기준 시점은 통계청의 발표를 따릅니다.",
    "en": "This article was written with an AI tool, adapting information published by Statistics Canada. Statistics Canada has not reviewed or endorsed it; figures and reference periods follow Statistics Canada's release."}
_STATCAN_PROMPT_RULE = ("통계청 발표 요약의 수치·단위·기준 시점(월·분기·연도)을 그대로 쓰세요. "
                        "통계청이 이 글을 보증하는 것처럼 쓰지 마세요. 원문 링크의 글자는 '통계청 발표'처럼 설명 문구로 쓰고 주소(statcan.gc.ca)를 글자로 보이게 쓰지 마세요. " + HEALTH_RULE)
# 통계청 사이트 robots.txt 의 Crawl-delay: 2 를 지켜, 기사 페이지를 연달아 읽을 때 사이에 이만큼(초) 기다린다.
_STATCAN_PAGE_DELAY = 2
# 글감이 못 되는 발표(통계 상품 안내·부문별 물가지수·공급 처리표·원자료 모음)와, 자동으로 다시 쓰기에는 민감한 주제(자살·약물 과다복용·마약성 진통제·성폭력·살인·가정·친밀한 관계·성별 기반 폭력·아동 학대)는 쓰지 않는다.
# 소비자물가지수·신규주택가격지수는 글감이라 살린다.
_STATCAN_EXCLUDE = (
    r"(?<!consumer )(?<!housing )\bprice index(?:es)?\b|\bsupply and disposition\b|\bproduction survey\b|\bdata availability\b|\bannouncement\b"
    r"|\bstorage survey\b|\bfuel consumption\b|\bgenerating stations?\b|\bsawmills?\b|\bpost-production\b|\bcredit aggregates\b"
    r"|\binteractive dashboard\b|\bopen database\b|\bdrinking water\b|\bmapping services\b"
    r"|\bsuicid|\boverdose|\bopioid|\bstimulant|\bself-harm|\bsexual (?:assault|behaviou?rs)|\bhomicide"
    r"|\b(?:family|domestic|intimate partner|gender-based) violence\b|\bchild (?:abuse|maltreatment)\b|\bviolent victimi[sz]ation\b")
_STATCAN_ECONOMY = (
    r"consumer price index|labour force survey|retail trade|wholesale trade|gross domestic product|merchandise trade|trade in services"
    r"|employment insurance|job vacanc|payroll|earnings|new housing price index|building permits|monthly survey of manufacturing"
    r"|new motor vehicle sales|travel between canada|international arrivals|business openings|economic contribution"
    r"|household (?:debt|spending|savings|income)|survey of household spending|productivity|cost of living|food (?:price|insecurity)"
    r"|labour market|workforce|\bGDP\b|cybercrime on canadian businesses|housing starts")
_STATCAN_SOCIETY = (
    r"education|graduat|enrolment|postsecondary|student|crime|victimi[sz]ation|police|court|sentenc|indigenous|immigra|newcomer"
    r"|official language|religio|population|census|gender|women|2SLGBTQ|disabilit|youth|children|famil(?:y|ies)"
    r"|older adults|seniors|housing affordability|housing stress|homeless|poverty|inequality|volunteer")
_STATCAN_LIFE = (
    r"health|mental|well-?being|quality of life|sleep|physical activity|nutrition|obesity|chronic|life expectancy|mortality"
    r"|time use|loneliness|social connection|leisure|\bbirths?\b|fertility|baby names|\bdeaths?\b|marriage|divorce")

# 영국 정부(GOV.UK): "GOV.UK 의 대부분의 내용은 왕실 저작권 아래 Open Government Licence(OGL)로 공개된다"(이용약관 https://www.gov.uk/help/terms-conditions, 2024-09-03판 —
# 약관은 버전을 적지 않고, v3.0 이라는 근거는 모든 페이지 바닥글이다. 바닥글은 "달리 표시한 경우는 제외"라고 해서 개별 항목의 별도 표시는 코드가 가려내지 못한다).
# OGL v3.0(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)은 복제·재가공·상업 이용을 허용하고, 조건은 출처 표시 —
# 정보 제공자가 정한 문구가 없으면 "Contains public sector information licensed under the Open Government Licence v3.0." — 와 제공자가 이 이용을 보증하거나
# 공식 지위가 있는 것처럼 보이게 하지 않는 것(Non-endorsement)이다. 개인정보·제3자 권리·로고·왕실 문장은 이 허락의 대상이 아니다. 이용약관에 AI·텍스트 마이닝 조항은 없고, GOV.UK robots.txt 는 AI 크롤러로
# meta-externalagent 를 `/search/all*` 에만 막는다(우리가 읽는 `/search/news-and-communications.atom` 경로가 아니다). 운영자가 이 소스를 쓰기로 결정했다
# (2026-10-26 채팅 "AI 학습을 위한 목적이 아니기에 문제가 없을것으로 보여져"). 피드는 20건이 한도이고 항목 날짜(updated)는 마지막 수정 시각이라 고친 글이 새 글처럼 보일 수 있다 —
# 같은 글을 두 번 쓰지 않는 것은 이력·제목 유사도 검사가 맡는다.
# 피드 요약이 한두 문장이고 기사 페이지의 메타 설명이 그 요약과 같아서(docs/analysis/2026-10-26_overseas-sources.md) 페이지를 따로 읽지 않는다(no_page_fetch): 100자 미만 요약은 SHORT_SUMMARY 로 떨어진다.
_OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
_GOVUK_TERMS = {"status": "allowed", "checked": "2026-10-26", "url": "https://www.gov.uk/help/terms-conditions"}
_GOVUK_CITATION = ("“{title}.” GOV.UK, {date} <{url}>. Contains public sector information licensed under the Open Government Licence v3.0. (" + _OGL_URL + ")")
_GOVUK_NOTICE = {
    "ko": "이 글은 AI 도구가 영국 정부(GOV.UK)가 공개한 자료를 요약·재구성해 작성했으며 원문에서 바뀐 부분이 있습니다. "
          "원문은 Open Government Licence v3.0으로 제공됩니다(Contains public sector information licensed under the Open Government Licence v3.0.). "
          "영국 정부와 해당 부처는 이 글을 검토하거나 보증하지 않았으며, 이 글은 영국 정부의 공식 입장이나 공식 문서가 아닙니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published on GOV.UK; changes were made to the original. "
          "Contains public sector information licensed under the Open Government Licence v3.0. (" + _OGL_URL + ") "
          "The UK Government and the departments concerned have not reviewed or endorsed this article, and it is not an official government publication or position."}
_GOVUK_PROMPT_RULE = ("영국 정부(부처)가 발표한 내용임을 분명히 하고, 정부의 계획·주장과 확인된 사실을 구분하세요. "
                      "정당·선거·장관 개인에 대한 평가는 쓰지 말고, 영국 정부나 해당 부처가 이 글을 검토·보증했거나 정부의 공식 입장·문서인 것처럼 쓰지 마세요. " + HEALTH_RULE)
_GOVUK_FEED = "https://www.gov.uk/search/news-and-communications.atom?"
_GOVUK_ENV_FEED = (_GOVUK_FEED + "organisations%5B%5D=department-for-energy-security-and-net-zero"
                   "&organisations%5B%5D=department-for-environment-food-rural-affairs")
_GOVUK_TECH_FEED = (_GOVUK_FEED + "organisations%5B%5D=ai-security-institute"
                    "&organisations%5B%5D=department-for-science-innovation-and-technology")
# '뉴스와 알림' 피드에는 연설(/speeches/)·정책 문서와 편지(/publications/)·사례 소개(/case-studies/)도 섞여 든다. 보도 기사(/government/news/)만 쓴다.
_GOVUK_EXCLUDE_LINK = r"^(?!https://www\.gov\.uk/government/news/)"
# 인사·위촉 소식(진료 "appointments" 같은 평범한 낱말은 살린다), 신청·의견 모집 안내, 공동 성명·조의 표명, 선거·전쟁·군사·분쟁 소재와 자동으로 다시 쓰기에는 민감한 주제
# (자살·자해·성폭력·아동 성착취·학대·극단주의·테러)는 쓰지 않는다. "defence" 는 사이버 방어 소식이 있어 넣지 않았다.
_GOVUK_EXCLUDE_TITLE = (
    r"\bappoints?\b|\bappointed\b|\bappointments? (?:to|of|as)\b|\breappoint|\bchair recruitment\b|\bnew (?:chair|chief executive)\b|\bsteps? down\b"
    r"|\bapply now\b|(?:^|[?:!.] )apply for\b|\bopens? for applications\b|\bapplications? (?:are )?(?:now )?open\b|\bcall for (?:evidence|views|input|applications)\b"
    r"|\bjoint statement\b|\bstatement (?:from|by|on)\b|\bcondolences\b"
    r"|\belections?\b|\bpolitical parties\b"
    r"|\b(?:military|weapons?|warfare|missiles?|armed forces|ukraine|gaza|russia|iran(?:ian)?|israel|middle east|nato|sanctions?)\b"
    r"|\bsuicid|\bself-harm|\bsexual (?:abuse|exploitation|assault|violence)\b|\bchild (?:sexual|abuse)\b|\bdomestic abuse\b|\bviolence against women\b"
    r"|\bextremis|\bradicali[sz]|\bterror")

NEWS_SOURCES = [
    # 약관을 확인한 직접 RSS(2026-10-26). 분야마다 약관상 쓸 수 있는 소스만 둔다.
    {"name": "NASA", "lane": "science", "url": "https://www.nasa.gov/feed/",
     "terms": {"status": "allowed", "checked": "2026-10-26",
               "url": "https://www.nasa.gov/nasa-brand-center/images-and-media/"},
     # APOD 는 사진마다 저작권자가 따로 있어 약관 예외이고, 취재진 초대·인증·행사 안내와 사진 설명(image-article)·Glenn 센터 음향 연구실 소개 쪽은 글감이 못 된다(센터 소식 기사는 살린다).
     "exclude_title": r"^APOD\b|\binvites? media\b|\bmedia accreditation\b|\bto (?:host|conduct|answer)\b|\bsets? coverage\b",
     "exclude_link": r"/image-article/|/centers-and-facilities/[^/]+/acoustics-",
     # NASA 의 AI 이용 안내: AI 결과물의 정보를 NASA 에 직접 귀속하는 것은 허용되지 않고, NASA 는 AI 결과물의 정확성에 책임지지 않으며,
     # "AI 도구가 NASA 자료를 포함한다"고 밝히되 NASA 가 검토·허가한 것처럼 암시하지 말라고 한다. 작성 지침 한 줄은 AI가 어길 수 있고(코드로
     # 막으면 후보가 계속 탈락해 호출이 낭비된다, D-63) 고지문은 코드가 붙인다.
     "notice": {"ko": "이 글은 AI 도구가 NASA가 공개한 자료를 참고해 작성했습니다. NASA는 이 글을 검토하거나 승인하지 않았고 내용의 정확성에 책임지지 않으며, 글의 내용은 NASA의 입장이 아닙니다.",
                "en": "This article was written with an AI tool using publicly available NASA source material. NASA has not reviewed or approved it, is not responsible for its accuracy, and it does not represent NASA's position."},
     "prompt_rule": "NASA의 AI 이용 안내에 따라 정보를 NASA가 직접 말하거나 보증한 것처럼 쓰지 마세요. "
                    "'NASA에 따르면'·'NASA는 밝혔다'(영어 글은 'according to NASA'·'NASA said') 같은 직접 귀속 표현을 쓰지 말고 "
                    "'공개된 자료에 따르면'(영어 글은 'according to the published material')처럼 자료를 가리키세요."},
    # 보류(pending): UN News 이용 안내는 출처 표기와 링크만 요구하고 재가공을 환영한다. 그러나 ① 유엔 저작권 안내(un.org/en/about-us/copyright)는
    # 뉴스 자료를 쓸 때 유엔에 알릴 것(the United Nations is advised)을 요구하는데 아직 하지 않았고, ② news.un.org 의 robots.txt 는 일반 봇에
    # 이 피드 경로(`*/news/`)를 허용하지 않는다. 알림과 서면 확인(unnews@un.org)을 마치고 운영자가 확인하면 allowed 로 바꾼다(D-63).
    {"name": "UN News", "lane": "society", "url": "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
     "terms": {"status": "pending", "checked": "2026-10-26",
               "url": "https://www.un.org/en/about-us/copyright",  # 알림 조건이 있는 쪽. 재가공 환영 문구는 https://news.un.org/en/content/navigate-news
               "blocker": "유엔에 이용 사실을 알리고(un.org 저작권 안내) 이 피드 경로를 읽어도 되는지 서면 확인을 받아야 한다(news.un.org robots.txt 가 일반 봇에 */news/ 경로를 허용하지 않음)"},
     # 여러 소식을 묶은 요약 기사는 글감이 못 된다.
     "exclude_title": r"^World News in Brief\b",
     "notice": {"ko": "이 글은 UN News의 보도를 바탕으로 AI 도구가 작성했습니다. 유엔은 이 글을 검토하거나 승인하지 않았으며, 글의 내용은 유엔의 공식 입장이 아닙니다.",
                "en": "This article was written with an AI tool based on reporting by UN News. The United Nations has not reviewed or approved it, and it is not an official UN position."}},
    {"name": "Pew Research Center", "lane": "culture", "url": "https://www.pewresearch.org/feed/",
     "terms": {"status": "allowed", "checked": "2026-10-26",
               "url": "https://www.pewresearch.org/about/terms-and-conditions/"},
     # 퀴즈·보고서 부속 쪽(감사의 글·조사 방법 등)과 선거·정당 이야기는 문화·미디어 글감이 아니다.
     "exclude_title": r"\bquiz\b|^(?:acknowledg(?:e)?ments|methodology|additional charts|appendix)\b"
                      r"|\belection|\bvoters?\b|\bballots?\b|\bmidterms?\b|\btrump\b|\bbiden\b|\brepublican|\bdemocrat|\bpartisan",
     # 뉴스레터 모음(/newsletter/)은 다른 매체 소식을 섞은 요약이라 'Pew 조사 결과'가 아니고, 방법론 연구 글과 선거 분류 글도 문화·미디어 글감이 아니다.
     "exclude_link": r"/newsletter/",
     "exclude_tags": r"methodolog|\belections?\b|\bvoters?\b|\bvoting\b|^political issues$|^donald trump$|^politics & policy$",
     # 피드는 정치·사회·종교 등이 섞여 있어 미디어·온라인·기술 주제만 문화·미디어 분야로 보낸다(제목과 분류 태그에서 찾는다).
     "topic_regex": r"social media|internet|online|\bAI\b|artificial intelligence|chatbot|\bnews\b|tiktok|youtube|instagram"
                    r"|facebook|podcast|streaming|influencer|smartphone|\bmobile\b|video game|gaming|music|movie|\bbooks?\b|\breading\b|digital|journalis|television|platform",
     "no_page_fetch": True,  # Pew 이용약관 §3 은 허가 없는 스크래핑(spidering·scraping)을 막는다. §1 이 허락한 RSS 요약만 쓰고 기사 페이지는 읽지 않는다.
     # Pew 이용약관 §2 의 인용 형식과 §1 의 번역물 면책 문장(아래 ko 고지문의 영어 문장은 약관 원문 그대로).
     "citation": "“{title}.” Pew Research Center, Washington, D.C. ({date}) <{url}>",
     "notice": {"ko": "이 글은 AI 도구가 Pew Research Center가 영어로 발표한 자료를 참고해 새로 쓴 해설입니다. "
                      "Pew Research Center has published the original content in English but has not reviewed or approved this translation. "
                      "(Pew Research Center가 영어 원문을 발표했으며, 이 글의 번역·요약을 검토하거나 승인하지 않았습니다.) 분석과 해석의 책임은 이 사이트에 있습니다.",
                "en": "This article is a new explainer written with an AI tool from findings published by Pew Research Center. The Center has not reviewed or approved it, and responsibility for the analysis and interpretation rests with this site."},
     "prompt_rule": "Pew Research Center의 조사 결과를 전하되, Pew가 특정 정책·정당·견해를 지지하거나 주장하는 것처럼 쓰지 마세요. "
                    "조사 결과와 이 사이트의 해석을 구분하세요."},
    {"name": "Federal Reserve", "lane": "economy", "url": "https://www.federalreserve.gov/feeds/press_all.xml",
     "terms": {"status": "allowed", "checked": "2026-10-26",
               "url": "https://www.federalreserve.gov/disclaimer.htm"},
     # 은행 인수·합병 승인과 제재·이의 없음 통보·공동 판단 건은 한 곳의 사업 사정이라 일반 독자의 글감이 못 된다.
     "exclude_title": r"\benforcement actions?\b|\bapprovals? of (?:the |related )?applications?\b|\bdoes not object\b|\bjoint findings\b",
     "notice": {"ko": "이 글은 AI 도구가 미국 연방준비제도 이사회(Federal Reserve Board)가 공개한 자료를 참고해 작성했습니다. 연준은 이 글을 검토하거나 승인하지 않았습니다.",
                "en": "This article was written with an AI tool using materials published by the Federal Reserve Board. The Board has not reviewed or approved it."}},
    # 해외(미국 외) 소스(2026-10-26 운영자 승인 13·14번 — 약관을 확인한 공식·공공 소스만, 라이선스가 출처 표시와 변경 표시를 조건으로 상업 이용·재가공을 허용한다).
    # 글 끝의 인용 한 줄(citation)과 고지문(notice)은 그 조건을 코드가 붙인다. 위 `_EC_*`·`_STATCAN_*` 상수에 약관 근거를 적었다.
    # 유럽연합 집행위원회 소식: 약 1/4(30건 중 8건)이 국채 입찰 결과·신청 안내라 제외하고, 선거·정치광고·민주주의 방패 글은 중립을 위해 쓰지 않는다(Pew와 같은 원칙).
    {"name": "European Commission", "lane": "society", "url": "https://commission.europa.eu/node/2/rss_en",
     "terms": _EC_TERMS,
     "exclude_title": _EC_EXCLUDE_STATEMENTS + "|" + _EC_EXCLUDE_VISITS + "|" + _EC_EXCLUDE_APPLY
                      + r"|\bauctions?\b|\bEU-(?:Bills?|Bonds?)\b|\bcall for (?:applications|tenders|proposals|experts)\b|\bwebinar\b"
                      r"|\belections?\b|\bpolitical (?:ads?|advertising|parties)\b",
     "exclude_link": _EC_EXCLUDE_LINK,
     "exclude_tags": r"^democracy$|\belections?\b",
     "citation": _ec_citation("European Commission"), "notice": _EC_NOTICE, "prompt_rule": _EC_PROMPT_RULE},
    # DG Energy: 에너지·경제 소식이 주 1~2건이 아니라 평일 거의 매일 나온다. 위원 방문·연설문은 글감이 못 된다. EIB·ACER 기사는 신뢰 목록에 없어 떨어진다.
    {"name": "European Commission · Energy", "display_name": "European Commission (DG Energy)", "lane": "economy",
     "url": "https://energy.ec.europa.eu/node/2/rss_en",
     "terms": _EC_TERMS,
     # 연설·성명·공동 선언은 글감이 못 된다(집행위원회 소스 전부에서 제목으로 뺀다). Press Corner 보도자료는 법적 고지를 확인하지 못해 주소로 뺀다(_EC_EXCLUDE_LINK).
     "exclude_title": _EC_EXCLUDE_STATEMENTS + "|" + _EC_EXCLUDE_VISITS + "|" + _EC_EXCLUDE_APPLY
                      + r"|\bcall for (?:feedback|evidence|applications|tenders|proposals)\b|\bwebinar\b",
     "exclude_link": _EC_EXCLUDE_LINK,
     "citation": _ec_citation("European Commission, DG Energy"), "notice": _EC_NOTICE, "prompt_rule": _EC_PROMPT_RULE},
    {"name": "European Commission · Environment", "display_name": "European Commission (DG Environment)", "lane": "science",
     "url": "https://environment.ec.europa.eu/node/92/rss_en",
     "terms": _EC_TERMS,
     "exclude_title": _EC_EXCLUDE_STATEMENTS + "|" + _EC_EXCLUDE_APPLY + r"|\bcall for (?:applications|tenders|proposals)\b|\bwebinar\b",
     "exclude_link": _EC_EXCLUDE_LINK,
     "citation": _ec_citation("European Commission, DG Environment"), "notice": _EC_NOTICE, "prompt_rule": _EC_PROMPT_RULE},
    # JRC: 요약이 짧은 항목은 기사 페이지의 소개 문구를 읽는다. 국방·안보 분류 글은 쓰지 않는다.
    {"name": "European Commission · JRC", "display_name": "European Commission, Joint Research Centre", "lane": "science",
     "url": "https://joint-research-centre.ec.europa.eu/node/2/rss_en",
     "terms": _EC_TERMS,
     "exclude_title": _EC_EXCLUDE_STATEMENTS,
     "exclude_link": _EC_EXCLUDE_LINK,
     "exclude_tags": r"defen[cs]e|^security and law enforcement$",
     "citation": _ec_citation("European Commission, Joint Research Centre (JRC)"), "notice": _EC_NOTICE, "prompt_rule": _EC_PROMPT_RULE},
    # 디지털 전략(AI Act·디지털서비스법 등): 이 사이트의 법적 고지는 출처 표시 방법을 "작품 제목, 유럽연합 귀속, 원문 주소"로 안내한다.
    # 피드 요약은 "Anonymous (not verified) 날짜"로 시작하는 사이트 잡음이 붙어 있다.
    {"name": "EU Digital Strategy", "display_name": "European Commission (Digital Strategy)", "lane": "technology",
     "url": "https://digital-strategy.ec.europa.eu/en/rss.xml",
     "terms": {"status": "allowed", "checked": "2026-10-26", "url": "https://digital-strategy.ec.europa.eu/en/pages/legal-notice"},
     "exclude_title": _EC_EXCLUDE_STATEMENTS + r"|\bcall for (?:tenders|applications|proposals|experts)\b",
     "exclude_link": _EC_EXCLUDE_LINK,
     "citation": _ec_citation("European Union (European Commission, DG CNECT)"), "notice": _EC_NOTICE,
     "prompt_rule": _EC_PROMPT_RULE + " 요약 앞머리의 'Anonymous (not verified)'와 날짜는 사이트가 붙인 잡음이니 글에 쓰지 마세요."},
    # 캐나다 통계청 The Daily(평일 12:30 UTC 발표). 한 피드를 분야별 주제어로 나눠 읽는다(_STATCAN_* 상수).
    {"name": "Statistics Canada · economy", "display_name": "Statistics Canada", "lane": "economy", "url": _STATCAN_FEED,
     "terms": _STATCAN_TERMS, "exclude_title": _STATCAN_EXCLUDE, "topic_regex": _STATCAN_ECONOMY, "page_delay": _STATCAN_PAGE_DELAY,
     "citation": _STATCAN_CITATION, "notice": _STATCAN_NOTICE, "prompt_rule": _STATCAN_PROMPT_RULE},
    {"name": "Statistics Canada · society", "display_name": "Statistics Canada", "lane": "society", "url": _STATCAN_FEED,
     "terms": _STATCAN_TERMS, "exclude_title": _STATCAN_EXCLUDE, "topic_regex": _STATCAN_SOCIETY, "page_delay": _STATCAN_PAGE_DELAY,
     "citation": _STATCAN_CITATION, "notice": _STATCAN_NOTICE, "prompt_rule": _STATCAN_PROMPT_RULE},
    {"name": "Statistics Canada · daily life", "display_name": "Statistics Canada", "lane": "daily_life", "url": _STATCAN_FEED,
     "terms": _STATCAN_TERMS, "exclude_title": _STATCAN_EXCLUDE, "topic_regex": _STATCAN_LIFE, "page_delay": _STATCAN_PAGE_DELAY,
     "citation": _STATCAN_CITATION, "notice": _STATCAN_NOTICE, "prompt_rule": _STATCAN_PROMPT_RULE},
    # 영국 정부 GOV.UK 뉴스(2026-10-26 운영자 결정, _GOVUK_* 상수에 약관 근거). 에너지·환경은 하루 1건 안팎, 과학·기술은 한 달에 서너 건이라 보충용이다.
    {"name": "GOV.UK · Environment & Energy", "display_name": "GOV.UK", "lane": "science", "url": _GOVUK_ENV_FEED,
     "terms": _GOVUK_TERMS, "exclude_title": _GOVUK_EXCLUDE_TITLE, "exclude_link": _GOVUK_EXCLUDE_LINK, "no_page_fetch": True,
     "citation": _GOVUK_CITATION, "notice": _GOVUK_NOTICE, "prompt_rule": _GOVUK_PROMPT_RULE},
    {"name": "GOV.UK · Science & Technology", "display_name": "GOV.UK", "lane": "technology", "url": _GOVUK_TECH_FEED,
     "terms": _GOVUK_TERMS, "exclude_title": _GOVUK_EXCLUDE_TITLE, "exclude_link": _GOVUK_EXCLUDE_LINK, "no_page_fetch": True,
     "citation": _GOVUK_CITATION, "notice": _GOVUK_NOTICE, "prompt_rule": _GOVUK_PROMPT_RULE},
    # 전자신문(rss.etnews.com)은 2026-10-26에 뺐다: 콘텐츠 이용 안내(info.etnews.com)가 영리·비영리 정보서비스에 사전 협의·정식 계약을 요구하고 무단 사용에는 사용료의
    # 30배 배상을 안내한다. 운영자 결정(2026-10-26 "계약·사용료는 '무료 자동화 기반' 취지에 맞지 않음")으로 TERMS_BLOCKED_DOMAINS 에 올렸다(D-61).
    # 블로터(https://www.bloter.net/feed)는 HTTP 404라 2026-10-25에 뺐다(실행 로그 '수집 실패', 로컬에서도 404/403).
    # 구글 뉴스 검색 소스 14개는 통과율이 0.4%(게시자 원문 주소로 풀리지 않음)라 2026-10-26에 뺐다.
    # MIT Technology Review·BBC Technology 는 약관이 이 용도를 금지·허가 필요로 해서 2026-10-26에 뺐다(TERMS_BLOCKED_DOMAINS).
    # AI타임스는 모든 기사 하단의 'AI학습 및 활용 금지' 표기와 저작권보호정책 때문에 운영자 결정(2026-10-26 "금지된 부분이면 접근하지 않는다")으로 뺐다(TERMS_BLOCKED_DOMAINS, D-61).
    # TechCrunch·The Verge·Hacker News 는 신뢰 목록에 없어 글감이 한 건도 안 되고 약관이 제한적이거나 간접 경로라 같은 날 뺐다(D-61).
    # Ars Technica·IEEE Spectrum 은 robots.txt 가 AI 관련 크롤러(ClaudeBot·anthropic-ai·CCBot 등)를 이름으로 막고 이용약관은 못 읽었거나 복제에 서면 동의를 요구해,
    # 운영자 결정(2026-10-26 "AI 크롤러를 막는 사이트는 접근하지 않는 원칙")으로 같은 날 뺐다(TERMS_BLOCKED_DOMAINS, D-61).
]

# 게시 후보에 사용할 수 있는 출처 도메인. 도메인 이름은 끝 경계까지 비교합니다.
# 보도자료·검색 결과·커뮤니티 링크만으로는 글을 발행하지 않습니다.
TRUSTED_SOURCE_DOMAINS = {
    "science": ("science.org", "pnas.org", "cell.com", "who.int",
                "nih.gov", "noaa.gov", "nasa.gov", "ipcc.ch", "jpl.nasa.gov",
                "ec.europa.eu", "www.gov.uk",
                "reuters.com", "apnews.com"),
    "economy": ("oecd.org", "imf.org", "worldbank.org", "federalreserve.gov",
                "bls.gov", "bok.or.kr", "kostat.go.kr", "kdi.re.kr",
                "ec.europa.eu", "statcan.gc.ca",
                "reuters.com", "apnews.com", "ft.com", "bloomberg.com"),
    "society": ("oecd.org", "un.org", "unesco.org", "unicef.org", "korea.kr",
                "kostat.go.kr", "kdi.re.kr",
                "commission.europa.eu", "ec.europa.eu", "statcan.gc.ca",
                "reuters.com", "apnews.com"),
    "technology": ("nist.gov", "acm.org", "arxiv.org",
                   "science.org",
                   "ec.europa.eu", "www.gov.uk",
                   "reuters.com", "apnews.com"),
    "culture": ("unesco.org", "pewresearch.org", "reuters.com", "apnews.com",
                "variety.com", "nytimes.com"),
    "daily_life": ("who.int", "nih.gov", "nhs.uk", "cdc.gov", "apa.org",
                   "kostat.go.kr", "korea.kr", "mfds.go.kr",
                   "foodsafetykorea.go.kr", "kca.go.kr", "consumer.go.kr",
                   "statcan.gc.ca",
                   "reuters.com", "apnews.com"),
}

# 약관을 읽고 이 용도(광고가 붙는 사이트에서 RSS 제목·요약을 AI에 주어 새 글을 쓰는 것)가 금지이거나 허가가 필요하다고 읽은 매체,
# 그리고 robots.txt 로 AI 크롤러를 막아 운영자가 접근하지 않기로 한 매체.
# 신뢰 목록에 실수로 다시 들어와도 _trusted_domain 이 거부한다(법률 판단이 아니다). 근거: docs/analysis/2026-10-25_publish-readiness.md §3-1,
# BBC·MIT TR 은 2026-10-26 약관 재확인.
#   BBC                    사업적 RSS 이용은 허가 필요, RSS·콘텐츠에서 메타데이터를 가져오는 것과 AI·컴퓨터 분석 이용은 허가 필요, 돈을 버는 이용도 허가 대상(이용약관 v1.8 §7(d)·§8·§15, 2022-09-19판)
#   Guardian               사전 서면 승인 없는 상업적 이용·AI로 콘텐츠를 생성·합성하는 것 금지
#   Nature                 상업적 이용에는 허가 필요
#   MIT Technology Review  복제·수정·재게시 금지, 파생물·상업적 이용 금지(서비스에 RSS 포함), 콘텐츠로 AI 시스템을 만들거나 학습·개선하는 것은 사전 서면 동의(Restrictions on Use·Commercial Use·AI and Large Language Model Usage, 2023-09-06판)
#   AI타임스               모든 기사 하단에 "무단전재 및 재배포, AI학습 및 활용 금지", 저작권보호정책은 승낙 없는 복제·출판·전송·배포·판매·변형 금지(2026-10-26 기사 3건 확인). 운영자 결정으로 접근하지 않는다
#   Ars Technica           robots.txt 가 ClaudeBot·anthropic-ai·CCBot·Google-Extended 등 AI 관련 크롤러 약 30개를 이름으로 막는다(`Disallow: /` 대상 34개 중, 2026-10-26 검증 세션이 읽음), Condé Nast 약관은 읽지 못함. 운영자 결정(2026-10-26 "AI 크롤러를 막는 사이트는 접근하지 않는 원칙")으로 접근하지 않는다
#   IEEE(Spectrum 포함)    robots.txt 가 GPTBot·ClaudeBot·anthropic-ai·CCBot·PerplexityBot 등 AI 관련 크롤러 약 21개를 이름으로 막고(33개 중, 사용자 요청형 일부는 명시 허용) 이용약관은 복제에 사전 서면 동의를 요구한다(검증 세션 보고). 같은 결정으로 접근하지 않는다
#   전자신문               콘텐츠 이용 안내(info.etnews.com 콘텐츠 구매 페이지)가 영리·비영리 정보서비스에 사전 협의·정식 계약을 요구하고, 수집해 자체 DB를 만들면 저작권 침해이며 무단 사용에는 사용료의 30배 배상을 안내한다. 운영자 결정(2026-10-26 "계약·사용료는 '무료 자동화 기반' 취지에 맞지 않음")으로 접근하지 않는다
TERMS_BLOCKED_DOMAINS = ("bbc.com", "bbc.co.uk", "bbci.co.uk", "theguardian.com", "guardian.co.uk",
                         "nature.com", "technologyreview.com", "aitimes.com",
                         "arstechnica.com", "ieee.org", "etnews.com")


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


# 기사 주소는 글의 출처 목록·인용 줄에 마크다운 링크 `[글](주소)` 로 들어간다. 공백·꺾쇠·따옴표·역슬래시와 괄호·대괄호는 링크를 끊거나 새 링크·HTML 을 만들 수 있어 막는다.
# fullmatch 로 쓴다: `$` 는 끝의 줄바꿈 앞에서도 맞아 Atom href 의 끝 줄바꿈이 통과한다. 실제 피드 링크 335개(16개 피드)에는 이 글자가 하나도 없었다(2026-10-26).
_SAFE_URL = re.compile(r"https?://[^\s<>\"'\\()\[\]]+")


def _host_in(host, domains):
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _trusted_domain(host, lane):
    """게시 후보로 쓸 수 있는 게시자인가. 약관상 쓸 수 없는 도메인(TERMS_BLOCKED_DOMAINS)은 신뢰 목록에 들어와 있어도 거부한다."""
    return not _host_in(host, TERMS_BLOCKED_DOMAINS) and _host_in(host, TRUSTED_SOURCE_DOMAINS.get(lane, ()))


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
                if child.tag.split("}")[-1] in names:
                    text = (child.text or "").strip()
                    # Atom 의 type="xhtml" 은 글자가 자식 요소(div·span) 안에 들어 있다(Statistics Canada The Daily). 그때만 자식까지 이어 읽는다
                    # (그 밖의 중첩 요소 — 예: <media:content> 안의 <media:description> — 를 요약으로 착각하지 않게).
                    if not text and child.get("type") == "xhtml":
                        text = "".join(child.itertext()).strip()
                    if text:
                        return text
            return ""

        link = ""
        publisher_name = ""
        publisher_url = ""
        categories = []
        for child in node:
            tag = child.tag.split("}")[-1]
            if tag == "link" and not link:
                link = child.get("href") or (child.text or "").strip()
            elif tag == "source":
                publisher_name = _clean_text(child.text or "", 120)
                publisher_url = child.get("url") or ""
            elif tag == "category":
                label = _clean_text(child.get("term") or child.text or "", 80)
                if label:
                    categories.append(label)
        items.append({
            "title": _clean_text(text_of("title"), 300),
            "published": _parse_date(text_of("pubDate", "published", "updated", "date")),
            "summary": _clean_text(text_of("description", "summary", "content", "encoded")),
            "link": link,
            "publisher_name": publisher_name,
            "publisher_url": publisher_url,
            "categories": categories,
        })
    return items


def _rule_excludes(src, title, item):
    """소스의 제외 규칙(exclude_title·exclude_link·exclude_tags)에 걸리는 기사인가."""
    checks = (("exclude_title", [title]), ("exclude_link", [item.get("link") or ""]), ("exclude_tags", item.get("categories") or []))
    return any(src.get(key) and any(re.search(src[key], text, re.I) for text in texts) for key, texts in checks)


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
        terms = src.get("terms") or {}
        if terms.get("status") == "pending":
            print(f"  소스 {src['name']}: 보류 — {_one_line(terms.get('blocker', ''), 200)}")
            continue
        if _host_in(_host(src.get("url", "")), TERMS_BLOCKED_DOMAINS):
            print(f"  소스 {src['name']}: 약관상 접근하지 않는 도메인(TERMS_BLOCKED_DOMAINS)이라 읽지 않음")
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
        topic_re = re.compile(src["topic_regex"], re.I) if src.get("topic_regex") else None
        pages_fetched = 0
        for it in parsed:
            title = it["title"]
            publisher = it.get("publisher_name") or ""
            publisher_url = it.get("publisher_url") or ""
            if src.get("google"):
                if not publisher:
                    match = re.match(r"^(.*)\s+-\s+([^-]+)$", title)
                    if match:
                        title, publisher = match.group(1).strip(), match.group(2).strip()
            else:
                # 직접 RSS 의 <source> 는 피드 자기소개(예: UN News 의 긴 태그라인)라 게시자 표시로 쓰지 않는다 — 게시자는 기사 주소의 호스트다.
                publisher = publisher_url = ""
            if not title:
                _count(drops, "NO_TITLE")
                continue
            if _rule_excludes(src, title, it):
                _count(drops, "EXCLUDED")
                continue
            if topic_re and not topic_re.search(" ".join([title] + it.get("categories", []))):
                _count(drops, "OFF_TOPIC")
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
            if not article_url or not _SAFE_URL.fullmatch(article_url):  # 줄바꿈·꺾쇠·따옴표·괄호가 든 주소는 글에 그대로 들어가면 마크다운·HTML 이 된다
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
            if len(summary) < 100 and not src.get("no_page_fetch"):
                if pages_fetched and src.get("page_delay"):
                    time.sleep(src["page_delay"])   # 같은 사이트의 기사 페이지를 연달아 읽을 때 Crawl-delay 를 지킨다
                pages_fetched += 1
                summary = _fetch_source_excerpt(article_url)
            if len(summary) < 100:
                _count(drops, "SHORT_SUMMARY")
                continue
            kept.append({"title": title, "source": publisher or src.get("display_name") or src["name"],
                         "link": article_url, "publisher_domain": publisher_host,
                         "summary": summary, "published": pub,
                         "notice": src.get("notice"), "citation": src.get("citation"),
                         "prompt_rule": src.get("prompt_rule")})
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
    if item and item.get("link") and item.get("source"):
        source_rule = ("- 제공된 검증 게시자 원문만 사실 근거로 쓰세요. 원문에서 확인되지 않는 주장·수치·인용·날짜·인과관계는 쓰지 마세요.\n"
                       "- 학술 연구는 동료심사 여부를 명시하고 표본·범위·한계를 설명하세요. arXiv 등의 프리프린트를 동료심사 연구처럼 표현하지 마세요.\n"
                       "- 중요한 사실 문장에는 제공된 원문 URL을 Markdown 인라인 인용으로 붙이세요. 사실과 해석·전망을 명확히 구분하세요.\n"
                       "- 제목·저자·학술지명·DOI·통계·인용문이나 출처를 추정해 만들지 마세요. 근거가 부족하면 skip을 반환하세요.\n"
                       + "".join(f"- {rule}\n" for rule in GROUNDING_RULES))   # 소스와 상관없이 모든 글감에 붙는 '요약에 없는 것을 채우지 않는' 규칙(D-77)
    else:
        source_rule = "- 검증된 출처가 없으면 글을 만들지 말고 skip을 반환하세요.\n"
    extra_rule = f"- {item['prompt_rule']}\n" if item and item.get("prompt_rule") else ""
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
{source_rule}{extra_rule}- 본문은 충분한 설명과 분석을 포함하고 Markdown으로 작성하세요.
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


# ============================================================
# 글 머리말(front matter) 검사·복구 (D-80, 사용자 이슈 #59)
# ============================================================
# 모델이 쓴 머리말 줄은 믿지 않는다. 2026-10-27 18시 슬롯의 글 한 쌍은 모델이 `------` 로 시작하는 이중 머리말을, 2026-10-28 9시 슬롯의 한글 글은
# 안쪽 따옴표를 이스케이프하지 않은 제목(`title: ""…": …"`)을 내보냈다. 옛 코드는 그 줄을 그대로 글 파일에 써서 공개 사이트의 글 제목이 파일 이름으로,
# 분야가 General 로 나왔다. 그래서 ① 모델 응답에서 머리말과 본문을 견고하게 가르고(_split_model_content) ② 머리말이 엄격 검사를 통과할 때만 모델이 쓴
# 줄을 보존하고 아니면 구조화된 값(제목·분야·태그)으로 처음부터 다시 쓰며(_front_matter_from_model) ③ 설명·출처 줄까지 더한 최종 글을 한 번 더 검사해
# (front_matter_problems) 깨진 글은 발행하지 않고 그 후보를 거절한다. 운영 환경(requirements-pipeline.txt)에는 PyYAML 이 없으므로 검사는 정규식·JSON 으로만
# 한다: 한 줄 `키: 값`(과 값이 빈 키에 이어지는 블록 목록 항목)만 받아들이고 그 밖의 모양은 모두 '믿지 않는 머리말'이다.
_FM_FENCE = re.compile(r"-{3,}[ \t]*")      # 울타리처럼 보이는 줄(대시만 3개 이상). 정상은 정확히 `---`
_FM_KEY = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]|\Z)")      # 줄 맨 앞의 `키:` — 콜론 뒤가 공백이나 줄 끝이어야 YAML 매핑이다
_FM_ITEM = re.compile(r" *-[ \t]+(.*)")      # 값이 빈 앞 키에 이어지는 블록 목록 항목(`  - 값`)
_FM_SHAPED = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_-]*[ \t]*:|-[ \t]|[ \t#])")      # 머리말 줄처럼 생긴 줄(빈 줄은 따로 센다)
_FM_KNOWN_KEY = re.compile(r"(?:layout|title|category|tags|lang|image|description)[ \t]*:")      # 글 머리말에만 있는 키
_FM_RESIDUE = re.compile(r"(?:layout|title|category|tags|lang|image|description|published|date|permalink|slug|source_name|source_url|source_domain)[ \t]*:")      # 본문 앞 세 줄에 남아서는 안 되는 머리말 줄(소문자 키만)
_FM_REQUIRED = ("layout", "title", "category", "lang", "image")
_FM_MAX_LINE = 2000      # 머리말 한 줄의 상한(검사 정규식이 아주 긴 줄에서 오래 걸리지 않게)
# 한 줄 목록의 항목: 큰따옴표(JSON 이 아는 이스케이프만)·작은따옴표·평문. 평문 항목은 공백으로 끝나지 못한다 — 꼬리와 뒤의 `[ \t]*` 가 같은 공백을 겹쳐 먹으면 되돌아가기가
# 항목 수의 지수로 늘어(`tags: [a ,a ,… #]` 22개 1.3초, 하나 늘 때마다 두 배) 슬롯 실행이 멈춘다(검증자 N1). 또 평문 항목은 `?` 를 품지 못한다 — 한 줄 목록 안에서 `?` 는 평문을 끝내는 '키' 표지라
# `[a?b]` 를 PyYAML 이 읽지 못한다(N2). 큰따옴표 항목의 이스케이프를 JSON 이 아는 것으로 좁힌 것도 같은 이유다(`\q` 는 YAML 이 읽지 못한다).
_FM_FLOW_PLAIN = r"""[^\s,\[\]{}"'#&*!|>%@`:?-](?:[^,\[\]{}"'#:?\n]*[^\s,\[\]{}"'#:?\n])?"""
_FM_FLOW_ITEM = r"""(?:"(?:[^"\\\n]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"|'(?:[^'\n]|'')*'|""" + _FM_FLOW_PLAIN + ")"
_FM_FLOW_LIST = re.compile(r"\[[ \t]*(?:" + _FM_FLOW_ITEM + r"(?:[ \t]*,[ \t]*" + _FM_FLOW_ITEM + r")*(?:[ \t]*,)?[ \t]*)?\]")
_YAML_UNPRINTABLE = re.compile(r"[^\x09\x0a\x0d\x20-\x7e\x85\xa0-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")      # PyYAML 이 읽지 못하는 글자


def _fm_json_string(value):
    """한 줄 JSON 문자열(큰따옴표 안의 따옴표·역슬래시는 이스케이프)이면 그 글자를, 아니면 None 을 돌려준다."""
    if len(value) < 2 or value[0] != '"' or value[-1] != '"':
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        return None
    return parsed if isinstance(parsed, str) else None


def _fm_scalar_text(value):
    """한 줄 스칼라 값을 글자로 푼다(JSON 문자열·작은따옴표 문자열·평문). 풀 수 없는 모양이면 None."""
    if value.startswith('"'):
        return _fm_json_string(value)
    if value.startswith("'"):
        return value[1:-1].replace("''", "'") if re.fullmatch(r"'(?:[^'\n]|'')*'", value) else None
    return value if value and value[0] not in "[{" else None


def _fm_plain_ok(value):
    """따옴표 없는 값이 YAML 평문으로 안전한가: 표지 글자로 시작하지 않고 `: `·` #`·탭이 없다."""
    if value[0] in "[]{},#&*!|>'\"%@`":
        return False
    if value[0] in "-?:" and (len(value) == 1 or value[1] in " \t"):
        return False
    return not re.search(r"[ \t]#|:[ \t]|:\Z|\t", value)


def _fm_flow_list_ok(value):
    """한 줄 목록(`["가", "나"]`·`[가, 나]`·`['가']`)인가. 항목은 글자·숫자뿐이다(안쪽 목록·매핑·`:` 가 든 평문 항목은 받지 않는다)."""
    try:
        parsed = json.loads(value)
    except ValueError:
        return bool(_FM_FLOW_LIST.fullmatch(value))
    return isinstance(parsed, list) and all(item is None or isinstance(item, (str, int, float, bool)) for item in parsed)


def _fm_value_problem(key, value):
    """한 줄 값(앞뒤 공백을 뺀 비어 있지 않은 글)이 안전한 모양이 아닌 이유. 괜찮으면 None. 값의 뜻은 보지 않고 모양만 본다."""
    if len(value) > _FM_MAX_LINE:
        return "너무 김"
    if key == "title":
        text = _fm_json_string(value)
        if text is None:
            return "한 줄 JSON 문자열(큰따옴표 안의 따옴표·역슬래시는 이스케이프)이 아님"
        return None if text.strip() else "비어 있음"
    if key == "tags":      # 태그는 목록이어야 한다(`tags: "가, 나"` 같은 글자는 사이트가 목록으로 읽지 않는다). 값이 빈 블록 목록은 호출한 쪽이 따로 본다
        return None if value[0] == "[" and _fm_flow_list_ok(value) else "한 줄 목록([…])이 아님"
    if value[0] == '"':
        return None if _fm_json_string(value) is not None else "큰따옴표 문자열이 한 줄 JSON 으로 읽히지 않음"
    if value[0] == "'":
        return None if _fm_scalar_text(value) is not None else "작은따옴표 문자열이 닫히지 않음"
    if value[0] == "[":
        return None if _fm_flow_list_ok(value) else "한 줄 목록으로 읽히지 않음"
    return None if _fm_plain_ok(value) else "따옴표 없는 값으로 안전하지 않음(`: `·` #`·탭·YAML 표지 글자)"


def _fm_header_problems(header):
    """머리말 줄들의 모양 검사: (문제 목록, {키: [값, 이어진 목록 항목 수]}). 한 줄에 키 하나(`키: 값`)이고, 값이 빈 키에만 블록 목록 항목(`  - 값`)이 이어질 수 있다.
    문제 문장에는 키 이름만 들어가고 값은 들어가지 않는다(모델이 쓴 글이 로그에 실리지 않게)."""
    problems, keys, pending = [], {}, None
    for line in header:
        if not line.strip():
            continue
        found = _FM_KEY.match(line)
        if found:
            key, value = found.group(1), line[found.end():].strip()
            if key in keys:
                problems.append(f"`{key}` 키가 두 번 나옴")
            keys[key] = [value, 0]
            pending = None if value else keys[key]
            why = _fm_value_problem(key, value) if value else None
            if why:
                problems.append(f"`{key}` 값이 {why}")
            continue
        item = _FM_ITEM.fullmatch(line)
        if item and pending is not None:
            pending[1] += 1
            text = item.group(1).strip()
            if not text or _fm_value_problem("item", text):
                problems.append("블록 목록 항목이 안전한 모양이 아님")
            continue
        problems.append("`키: 값` 한 줄 모양이 아닌 줄이 있음")
    problems += [f"`{key}` 값이 비어 있음" for key, (value, count) in keys.items() if not value and not count]
    return problems, keys


def _source_front_fields(source):
    """add_discovery_metadata 가 머리말에 더하는 출처 세 줄의 값 (이름, 주소, 도메인). 더하지 않는 소스(주소가 http(s) 가 아니거나 이름·도메인이 없음)면 None."""
    if not source:
        return None
    source_url = str(source.get("link") or "").strip()
    parsed = urllib.parse.urlparse(source_url)
    if (parsed.scheme in {"http", "https"} and parsed.netloc and source.get("source") and source.get("publisher_domain")):
        return str(source.get("source")), source_url, str(source["publisher_domain"])
    return None


def front_matter_problems(content, source=None):
    """완성된 글 한 편(머리말 + 본문)의 머리말과 본문 머리를 엄격히 검사해 문제 목록을 돌려준다(비어 있으면 정상).
    검사: 첫 줄이 정확히 `---`·닫는 `---` 줄·CR/BOM/제어 문자 없음·한 줄 한 키·키 중복 없음·값이 안전한 모양(`title` 은 한 줄 JSON 문자열)·필수 키(layout·title·
    category·lang·image)·lang 은 ko·en·본문이 울타리 줄이나 머리말 줄로 시작하지 않음. source(add_discovery_metadata 에 넘기는 소스 항목)를 주면 엔진이 더하는
    설명(본문에서 뽑을 수 있을 때)과 출처 세 줄이 있고 소스와 같은지도 본다 — `_front_matter_set` 이 머리말을 못 찾아 조용히 지나친 경우가 여기서 드러난다.
    문제 문장에는 값이 들어가지 않는다."""
    text = str(content or "")
    if text.startswith("\ufeff"):
        return ["글이 BOM 으로 시작함"]
    lines = text.split("\n")
    if lines[0] != "---":
        return ["첫 줄이 정확히 `---` 가 아님"]
    end = next((i for i in range(1, len(lines)) if _FM_FENCE.fullmatch(lines[i])), None)
    if end is None:
        return ["머리말을 닫는 `---` 줄이 없음"]
    problems = []
    if lines[end] != "---":
        problems.append("머리말을 닫는 줄이 정확히 `---` 가 아님")
    header, body = lines[1:end], lines[end + 1:]
    joined = "\n".join(header)
    if "\r" in joined:
        problems.append("머리말에 CR 줄바꿈이 섞여 있음")
    if _YAML_UNPRINTABLE.search(joined):
        problems.append("머리말에 YAML 이 읽지 못하는 제어 문자가 있음")
    found, keys = _fm_header_problems(header)
    problems += found
    problems += [f"필수 키 `{key}` 줄이 없음" for key in _FM_REQUIRED if key not in keys]
    for key in ("category", "image"):
        have = keys.get(key)
        if have and have[0] and not (_fm_scalar_text(have[0]) or "").strip() and f"`{key}` 값이 비어 있음" not in problems:
            problems.append(f"`{key}` 값이 비어 있음")
    lang = keys.get("lang")
    if lang and lang[0] and _fm_scalar_text(lang[0]) not in ("ko", "en"):
        problems.append("`lang` 값이 ko·en 이 아님")
    head = []       # 본문의 앞 세 줄(빈 줄 제외)
    for line in body:
        if line.strip():
            head.append(line.rstrip("\r").lstrip("\ufeff"))
            if len(head) == 3:
                break
    if head and _FM_FENCE.fullmatch(head[0]):
        problems.append("본문이 `---` 울타리 줄로 시작함(이중 머리말 흔적)")
    elif any(_FM_RESIDUE.match(line) for line in head):
        problems.append("본문이 머리말 줄(`키: 값`)로 시작함")
    expected = _source_front_fields(source)
    if expected:
        for key, want in zip(("source_name", "source_url", "source_domain"), expected):
            have = keys.get(key)
            if have is None or _fm_scalar_text(have[0]) != want:
                problems.append(f"`{key}` 줄이 없거나 원문 정보와 다름")
        if _description_from_markdown(text) and "description" not in keys:
            problems.append("설명(`description`) 줄이 없음")
    return problems


def check_final_front_matter(data, source=None):
    """validate_post_data 를 거친 data 의 두 글에 설명·출처 줄까지 더해(실제로 파일이 될 모양으로) 머리말을 검사한다. 문제가 있으면 ValueError —
    깨진 글을 발행하느니 그 후보를 거절한다(본문 검증 실패와 같은 길)."""
    for prefix in ("kr", "en"):
        problems = front_matter_problems(add_discovery_metadata(data[f"{prefix}_content"], source), source)
        if problems:
            raise ValueError(f"{prefix.upper()} 글 머리말이 검사를 통과하지 못했습니다: " + " / ".join(problems[:3]))


def _fm_is_header_block(block):
    """울타리 둘 사이의 줄들이 '머리말 한 덩이'인가: 모든 줄이 머리말 모양(`키: 값`·목록 항목·들여쓴 줄·주석·빈 줄)이고 글 머리말의 키(layout·title·…)가 하나 이상 있다.
    키 모양 줄만 있는 글(예: `Note: …` 한 문단)을 머리말로 보고 버리지 않으려고 알려진 키를 요구한다."""
    return (all(not line.strip() or _FM_SHAPED.match(line) for line in block)
            and any(_FM_KNOWN_KEY.match(line) for line in block))


def _fm_extra_block(view, start):
    """view[start] 가 울타리 줄일 때, 다음 울타리 줄까지가 머리말 한 덩이(_fm_is_header_block)면 그 닫는 줄의 번호, 아니면 None.
    여는 울타리를 두 번 쓰거나 머리말을 두 번 쓴 응답을 알아보는 데 쓴다."""
    end = next((i for i in range(start + 1, len(view)) if _FM_FENCE.fullmatch(view[i])), None)
    if end is not None and _fm_is_header_block(view[start + 1:end]):
        return end
    return None


def _fm_body(lines, view):
    """머리말 뒤의 줄들에서 본문을 얻는다: 앞의 빈 줄, 구분선처럼 홀로 놓인 울타리 줄, 두 번째 머리말 한 덩이를 걷어낸다. (본문, 두 번째 머리말이 있었는가).
    view 는 판단에 쓰는 줄(CR 을 뺀 것), lines 는 본문에 쓰는 원래 줄이다 — 본문 글자는 걷어낸 앞부분 말고는 바꾸지 않는다."""
    i, doubled = 0, False
    while i < len(view):
        if not view[i].strip():
            i += 1
        elif _FM_FENCE.fullmatch(view[i]):
            extra = _fm_extra_block(view, i)
            if extra is None:
                i += 1
            else:
                doubled, i = True, extra + 1
        else:
            break
    return "\n".join(lines[i:]), doubled


def _split_model_content(content):
    """모델 응답 하나를 (종류, 머리말 줄 목록, 본문)으로 가른다.
    종류 — "none": 머리말이 없다(맨 앞이 울타리가 아니거나, 울타리가 닫히지 않았거나 사이가 머리말이 아니라 글이라 구분선으로 본 경우) ·
    "clean": 정확한 `---` 울타리 둘 사이의 머리말 하나 · "messy": 머리말은 있으나 울타리가 어긋나 있다(`------`·여는 울타리 두 번·머리말 두 번 …) — 이 줄들은 믿지 않는다.
    본문은 어느 경우에도 울타리(대시) 줄로 시작하지 않는다. 맨 앞이 울타리가 아닌 응답(종류 "none")의 본문은 응답 그대로다."""
    raw = str(content)
    lines = raw.lstrip("\ufeff").lstrip().split("\n")
    view = [line.rstrip("\r") for line in lines]
    if not _FM_FENCE.fullmatch(view[0]):
        return "none", [], raw
    exact = view[0].rstrip() == "---"
    end = next((i for i in range(1, len(view)) if _FM_FENCE.fullmatch(view[i])), None)
    if end is None:
        return "none", [], _fm_body(lines[1:], view[1:])[0]
    block = view[1:end]
    if not any(line.strip() for line in block):
        header = []       # 빈 머리말(`---\n---`)이거나, 여는 울타리를 두 번 쓴 것(`---\n---\n머리말…\n---`)
        extra = _fm_extra_block(view, end)
        if extra is not None:
            header, exact, end = view[end + 1:extra], False, extra
    elif _fm_is_header_block(block):
        header = block
    else:       # 첫 울타리와 다음 울타리 사이가 머리말이 아니라 글이다(구분선으로 시작한 글) — 글 머리말의 키가 하나도 없는 덩이는 머리말로 보고 버리지 않는다
        return "none", [], _fm_body(lines[1:], view[1:])[0]
    body, doubled = _fm_body(lines[end + 1:], view[end + 1:])
    return ("clean" if exact and view[end].rstrip() == "---" and not doubled else "messy"), header, body


def _model_header_problems(header):
    """모델이 쓴 머리말 줄을 그대로 보존해도 되는가: 안 되는 이유 목록(비어 있으면 보존한다). 한 줄 한 키 모양·키 중복 없음·값이 안전한 모양·`title` 이 한 줄 JSON 문자열이어야 하고,
    엔진이 지웠다 다시 쓰는 `lang`·`image` 는 한 줄 값이어야 한다(값이 비면 지우는 정규식이 다음 줄까지 지운다)."""
    problems, keys = _fm_header_problems(header)
    if "title" not in keys:
        problems.append("제목(`title`) 줄이 없음")
    problems += [f"`{key}` 는 한 줄 값이어야 함" for key in ("lang", "image") if key in keys and keys[key][1]]
    if _YAML_UNPRINTABLE.search("\n".join(header)):
        problems.append("머리말에 YAML 이 읽지 못하는 제어 문자가 있음")
    return problems


def _fresh_front_matter(data, prefix, html_lang, image_url):
    """모델이 쓴 머리말을 믿지 않을 때 쓰는, 구조화된 값(제목·분야·태그)과 시스템 값(언어·이미지)으로 처음부터 쓴 머리말(닫는 울타리와 빈 줄까지)."""
    return (
        "---\nlayout: post\n"
        f"title: {json.dumps(data[f'{prefix}_title'], ensure_ascii=False)}\n"
        f"category: {json.dumps(data[f'{prefix}_category'], ensure_ascii=False)}\n"
        f"tags: {json.dumps(data[f'{prefix}_tags'], ensure_ascii=False)}\n"
        f"lang: {html_lang}\nimage: {json.dumps(image_url)}\n---\n\n"
    )


def _front_matter_from_model(data, prefix, html_lang, image_url):
    """모델이 준 글 하나에 머리말을 붙여 (머리말이 붙은 글, 다시 쓴 이유)를 돌려준다. 이유는 모델이 쓴 머리말을 그대로 보존했거나 머리말이 아예 없었으면 None.
    머리말이 엄격 검사를 통과하면 모델이 쓴 줄을 지금까지처럼 보존하고(layout 이 없으면 맨 앞에 `layout: post`, lang·image 는 지웠다가 맨 끝에 다시 씀),
    통과하지 못하면 모델이 쓴 줄은 모두 버리고 구조화된 값으로 처음부터 다시 쓴다. 어느 쪽이든 본문은 걷어낸 앞부분(울타리 찌꺼기) 말고는 그대로다."""
    kind, header, body = _split_model_content(data[f"{prefix}_content"])
    reason = None
    if kind == "clean":
        problems = _model_header_problems(header)
        if not problems:
            front = "".join("\n" + line for line in header)   # 여는 울타리 줄 뒤의 줄들(맨 앞에 줄바꿈 하나)
            front = re.sub(r"(?m)^image:\s*.*$", "", front)
            front = re.sub(r"(?m)^lang:\s*.*$", "", front)
            front = re.sub(r"\n{2,}", "\n", front).rstrip()
            if not re.search(r"(?m)^layout\s*:", front):
                # 모델이 front matter 에서 layout 을 빼먹어도 다른 글·시험·도구와 같게 post 로 보장한다(2026-10-26 18시 글이 그랬다)
                rest = front.strip()
                front = "\nlayout: post" + ("\n" + rest if rest else "")
            front += f'\nlang: {html_lang}\nimage: "{image_url}"'
            return f"---{front}\n---\n\n{body}", None
        reason = problems[0]
    elif kind == "messy":
        reason = "머리말 울타리가 어긋남"
    return _fresh_front_matter(data, prefix, html_lang, image_url) + body, reason


def validate_post_data(data, kr_image, en_image, verified_source_url=None, notes=None):
    """notes(목록)를 주면 모델이 쓴 머리말을 믿지 못해 다시 쓴 글마다 한 줄(이유 포함, 값은 없음)을 덧붙인다."""
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
        content, reason = _front_matter_from_model(data, prefix, html_lang, image_url)
        if reason and notes is not None:
            notes.append(_one_line(f"{prefix.upper()} 머리말을 모델이 쓴 줄 대신 구조화된 값으로 다시 썼습니다({reason})"))     # 사유에는 키 이름만 있고 값은 없지만 로그에 찍는 글은 늘 접는다

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
    """Set one safely quoted scalar in an existing Markdown front matter block.
    머리말을 찾지 못하면 글을 그대로 돌려준다(예외를 던지지 않는다). 그래서 줄이 조용히 빠질 수 있다 — 최종 머리말 검사(front_matter_problems)가
    첫 줄·필수 키·설명·출처 줄이 있는지 보고 문제로 드러낸다."""
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


def _content_lang(content, body):
    """글 언어(ko|en). validate_post_data 가 front matter 에 심은 lang 을 먼저 보고, 없으면 본문에 한글이 있는지로 가른다(영어 글에 한글 단어가 섞여도 영어로 본다)."""
    front = re.match(r"\A---\s*\n(.*?)\n---\s*\n", content, re.S)
    found = re.search(r"(?m)^lang:\s*[\"']?(ko|en)\b", front.group(1)) if front else None
    if found:
        return found.group(1)
    return "ko" if re.search(r"[가-힣]", body) else "en"


_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _citation_line(citation, source):
    """소스 약관이 정한 인용 형식(citation 틀의 {title}·{date}·{url})을 채운 한 줄. 제목·게시일·주소 중 하나라도 없으면 빈 문자열."""
    published = source.get("published")
    title = str(source.get("title") or "").strip().rstrip(".").strip()
    link = str(source.get("link") or "").strip()
    if not (isinstance(citation, str) and title and link and hasattr(published, "month")):
        return ""
    line = citation.format(title=title, date=f"{_MONTHS[published.month - 1]} {published.day}, {published.year}", url=link)
    return re.sub(r"([?!])\.(?=[”\"])", r"\1", line)   # 제목이 ?·! 로 끝나면 틀의 마침표를 겹쳐 쓰지 않는다("…warfare?.”" 방지)


def _append_source_notice(content, source):
    """소스 약관이 요구하는 인용 한 줄(citation)과 고지문(AI 작성·검토 안 받음)을 글 끝에 덧붙인다(인용, 고지문 순).
    글 언어(한글 포함 여부)에 맞춰 ko/en 고지문을 고르고, 이미 있는 것은 다시 붙이지 않는다."""
    body_match = re.match(r"\A---\s*\n.*?\n---\s*\n(.*)\Z", content, re.S)
    body = body_match.group(1) if body_match else content
    notice = source.get("notice")
    text = str(notice.get(_content_lang(content, body)) or "").strip() if isinstance(notice, dict) else ""
    for block in (_citation_line(source.get("citation"), source), f"*{text}*" if text else ""):
        if block and block not in content:
            content = content.rstrip() + f"\n\n{block}\n"
    return content


def add_discovery_metadata(content, source=None):
    description = _description_from_markdown(content)
    if description:
        content = _front_matter_set(content, "description", description)
    if source:
        fields = _source_front_fields(source)   # 최종 머리말 검사(front_matter_problems)가 같은 조건으로 이 세 줄이 있는지 본다
        if fields:
            source_name, source_url, source_domain = fields
            content = _front_matter_set(content, "source_name", source_name)
            content = _front_matter_set(content, "source_url", source_url)
            content = _front_matter_set(content, "source_domain", source_domain)
            body_match = re.match(r"\A---\s*\n.*?\n---\s*\n(.*)\Z", content, re.S)
            body = body_match.group(1) if body_match else content
            if source_url not in body:
                heading = "\n\n## 출처\n" if _content_lang(content, body) == "ko" else "\n\n## Sources\n"
                content = content.rstrip() + f"{heading}- [{source['source']}: {source.get('title', '원문 기사')}]({source_url})\n"
        content = _append_source_notice(content, source)
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
                        allow_auto_topic=True, report=None, draft_flow=False):
    """KR/EN 글 한 쌍을 만든다. 만들면 (kr_path, en_path), 만들 수 없으면 None.
    report(dict)를 넘기면 분야별 수집 결과와 최종 결과 코드(outcome)를 채워 준다.
    draft_flow=True 는 승인 흐름(publish_flow: pr)이다: 글을 만드는 방법은 같고, 이력 항목에 flow·branch·paths 를 더하며 결과 코드는
    PUBLISHED 대신 DRAFT_CREATED 다(공개는 PR 병합이라 '발행했다'고 쓰지 않는다). 파일 올리기는 pipeline/draft_flow.py 가 맡는다."""
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
            # 설명·출처 줄까지 더한 최종 머리말도 여기서 미리 검사한다(D-80): 깨진 글을 발행하느니 이 후보를 거절하고 다음 후보를 시도한다.
            checked = validate_post_data(copy.deepcopy(candidate), "https://example.invalid/kr.jpg",
                                         "https://example.invalid/en.jpg",
                                         verified_source_url=(item or {}).get("link"))
            check_final_front_matter(checked, item)
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
    repairs = []
    data = validate_post_data(
        data, kr_image, en_image,
        verified_source_url=(selected_item or {}).get("link"),
        notes=repairs,
    )
    for repair in repairs:
        print(f"[참고] {repair}")

    now = now_kst()
    date_str, time_str = now.strftime("%Y-%m-%d"), now.strftime("%H%M%S")
    selected_item["title"] = selected_item.get("title") or selected or "원문 기사"
    data["kr_content"] = add_discovery_metadata(data["kr_content"], selected_item)
    data["en_content"] = add_discovery_metadata(data["en_content"], selected_item)
    for prefix in ("kr", "en"):
        # 마지막 방어선: 위 후보 검사가 통과했어도(자리표시 이미지로 한 검사) 실제 이미지·출처로 완성한 글의 머리말이 깨졌으면 파일을 쓰지 않는다
        problems = front_matter_problems(data[f"{prefix}_content"], selected_item)
        if problems:
            raise RuntimeError(f"{prefix.upper()} 글 머리말이 검사를 통과하지 못해 글을 저장하지 않습니다: " + " / ".join(problems[:3]))
    kr_path = safe_category_dir(data["kr_category"], "KR") / f"{date_str}-KR-{time_str}.md"
    en_path = safe_category_dir(data["en_category"], "EN") / f"{date_str}-EN-{time_str}.md"

    write_text_atomic(kr_path, data["kr_content"])
    try:
        write_text_atomic(en_path, data["en_content"])
    except Exception:
        if not DRY_RUN:
            kr_path.unlink(missing_ok=True)
        raise

    entry = {
        "date": date_str, "topic": selected or "(자동 선정)",
        "kr_title": data["kr_title"], "en_title": data["en_title"],
        "kr_image": kr_image, "en_image": en_image, "slot": slot,
        "lane": editorial_lane,
        "source": (selected_item or {}).get("source", ""),
        "source_url": (selected_item or {}).get("link", ""),
    }
    if draft_flow:
        entry.update(drafts.entry_fields(date_str, slot, time_str, [kr_path, en_path]))
        report["draft_branch"] = entry["branch"]
    history.append(entry)
    write_history(history)
    trigger_download(kr_image)
    trigger_download(en_image)
    report.update(outcome="DRAFT_CREATED" if draft_flow else "PUBLISHED", title=data["kr_title"], en_title=data["en_title"],
                  source=(selected_item or {}).get("source", ""),
                  paths=[str(kr_path), str(en_path)])
    print("블로그 글 생성 완료" + (" (DRY_RUN: 파일·기록은 저장되지 않았습니다):" if DRY_RUN else ":"))
    print(f"- KR: {kr_path}\n- EN: {en_path}\n- 편집 축: {EDITORIAL_LANES[editorial_lane]['label']}\n- 주제: {_one_line(selected or '(자동 선정)', 200)}")
    print(f"- 이미지: {kr_image}\n         {en_image}")
    if draft_flow:
        print(f"- 승인 흐름: 연습 실행이라 초안 브랜치 {entry['branch']} 를 올리지 않습니다" if DRY_RUN
              else f"- 승인 흐름: 초안 브랜치 {entry['branch']} 로 올립니다(PR 을 병합하면 공개, 닫으면 폐기)")
    return kr_path, en_path


# ============================================================
# 진입점
# ============================================================
PRACTICE_PUBLISHED_TEXT = "연습으로 글을 만들어 봤습니다(저장하지 않았습니다)"   # 연습 실행의 PUBLISHED: 아무것도 저장하지 않았는데 발행된 것처럼 읽히지 않게
OUTCOME_TEXT = {
    "PUBLISHED": "글을 만들었습니다",
    "DRAFT_CREATED": "초안을 만들었습니다(승인 흐름: PR 을 병합하면 공개, 닫으면 폐기 — 올리기는 다음 단계)",
    "ALL_LANES_EMPTY": "모든 분야를 시도했지만 검증을 통과한 기사가 한 건도 없습니다",
    "SOURCES_UNREACHABLE": "뉴스 소스에 접속하지 못했습니다(시도한 소스가 모두 수집 실패)",
    "ALL_DUPLICATES": "검증된 기사는 있었지만 모두 이미 쓴 글과 비슷해 새 글감이 없습니다(뉴스가 뜸한 때)",
    "NO_CANDIDATES": "시간 상한으로 일부 분야만 시도했고 후보를 찾지 못했습니다",
    "ALL_REJECTED": "후보는 있었지만 전부 탈락했습니다(Gemini 건너뜀, 제목이 기존 글과 비슷, 또는 본문 검증 탈락)",
    "NO_MATCH": "요청 주제와 연결되는 검증된 기사가 없습니다",
}


def _gemini_count_line(calls):
    """Blogger·이슈 수정 요약과 같은 형식의 호출 수 줄."""
    return f"Gemini 호출: {calls['attempts']}회(실패 {calls.get('failed', 0)}회)"


def _unsplash_line(rate):
    """마지막으로 관측한 Unsplash 시간당 남은 호출 수. 응답에 헤더가 없었으면 None(줄을 만들지 않는다)."""
    remaining = (rate or {}).get("remaining")
    if remaining is None:
        return None
    limit = rate.get("limit")
    return f"Unsplash 남은 호출: {remaining}회" + (f"(시간당 한도 {limit}회)" if limit is not None else "")


def usage_lines():
    """지금까지의 Gemini·Unsplash 사용량 줄. 정상 종료 요약(finish_run)이 아닌 경로 — 예외로 끝난 실행, 이미지 교체 — 에서도 쓴다."""
    lines = [_gemini_count_line(GEMINI_CALLS)]   # 0회도 적는다: 줄이 없으면 '호출 안 함'과 '이 기능이 없는 옛 요약'을 구분할 수 없다
    lines += CALL_LOG.detail_lines()
    unsplash = _unsplash_line(UNSPLASH_RATE)
    if unsplash:
        lines.append(unsplash)
    return lines


def failure_summary(exc):
    """예외로 끝난 실행의 요약. 모든 모델이 실패한 실행에서도 호출 수가 사라지지 않게 사용량 줄을 붙인다(D-52)."""
    return "\n".join(["### Chance_Blog 실행 요약",
                      f"- 결과: **실패** — {type(exc).__name__} (원인은 이 단계의 로그를 보세요)"]
                     + [f"- {line}" for line in usage_lines()])


def render_run_summary(event, now, slot, report):
    """실행 요약(마크다운). 건수와 코드만 쓴다 — 비밀·수익·방문 수치 금지(G-O7)."""
    outcome = report.get("outcome", "UNKNOWN")
    mode = "스케줄" if event == "schedule" else "수동"
    if DRY_RUN:
        mode += " (DRY_RUN: 파일·기록 저장 안 함)"
    created = outcome in ("PUBLISHED", "DRAFT_CREATED")   # 글 한 쌍을 만든 결과(승인 흐름이면 DRAFT_CREATED)
    outcome_text = PRACTICE_PUBLISHED_TEXT if DRY_RUN and created else OUTCOME_TEXT.get(outcome, "알 수 없음")
    lines = ["### Chance_Blog 실행 요약",
             f"- 실행: {mode} · {now:%Y-%m-%d %H:%M} KST" + (f" · {slot}시 슬롯" if slot is not None else ""),
             f"- 결과: **{outcome}** — {outcome_text}"]
    if DRY_RUN:  # 연습 실행이 한도를 썼는지 요약에서 바로 보이게 한다(기본은 가짜 응답, 실제 호출은 real_ai 체크)
        lines.append("- AI 응답: " + ("가짜(스텁) — Gemini를 호출하지 않았습니다(실제 호출로 연습하려면 수동 실행에서 real_ai 를 체크)"
                                      if STUB_GEMINI else "실제 Gemini 호출 — 연습 실행이지만 무료 한도를 씁니다"))
    over = report.get("manual_over_cap")
    if over:
        lines.append(f"- 경고: 수동 실행은 게시 시각·하루 상한을 따지지 않습니다 — 오늘({over['date']}) 이미 {over['posted']}건이 "
                     f"게시되어 상한({over['cap']}건) 이상입니다")
    if created:
        lines.append(f"- 제목: {_md_cell(report.get('title', ''))}")
        lines.append(f"- 편집 축: {report.get('lane_label', '')} · 출처: {_md_cell(report.get('source', ''), 60)}")
        lines.append("- 파일: " + ", ".join(f"`{str(p).replace(chr(96), '')}`" for p in report.get("paths", [])))
        if report.get("draft_branch"):
            branch = str(report["draft_branch"]).replace(chr(96), "")
            lines.append(f"- 승인 흐름: 연습 실행이라 초안 브랜치 `{branch}` 를 올리지 않습니다" if DRY_RUN
                         else f"- 승인 흐름: 초안 브랜치 `{branch}` 로 올립니다 — PR 을 병합하면 공개, 닫으면 폐기")
    calls = report.get("gemini_calls")
    if isinstance(calls, dict) and "attempts" in calls:   # 0회도 적는다(finish_run 이 항상 넣는다). 항목 자체가 없으면 값을 지어내지 않는다
        lines.append(f"- {_gemini_count_line(calls)}")
    lines += [f"- {note}" for note in report.get("gemini_notes", [])]
    unsplash = _unsplash_line(report.get("unsplash_rate"))
    if unsplash:
        lines.append(f"- {unsplash}")
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
    report.setdefault("gemini_notes", CALL_LOG.detail_lines())
    report.setdefault("unsplash_rate", dict(UNSPLASH_RATE))
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


# 승인 흐름(publish_flow: pr)에서만 생기는 건너뜀 코드의 사유 문구(docs/ARCHITECTURE.md §4-1·§4-4). direct 에서는 쓰이지 않는다.
DRAFT_SKIP_REASONS = {
    drafts.STATE_PENDING: "{slot}시 슬롯 초안이 승인(PR 병합)을 기다리는 중이거나 닫혀 폐기됨 — 같은 슬롯을 다시 만들지 않음",
    drafts.STATE_CHECK_FAILED: "초안 브랜치를 확인하지 못함",
}


def draft_flow_on():
    """레지스트리의 chance 발행 흐름이 승인 흐름(pr)인가. direct(기본)면 False. 레지스트리를 읽지 못하거나 값이 올바르지 않으면
    DraftFlowError 로 멈춘다 — 직접 게시로 조용히 떨어지면 승인 없는 게시가 나가기 때문이다."""
    return drafts.chance_flow() == drafts.FLOW_PR


def refine_for_drafts(state, slot, history, now):
    """승인 흐름에서 slot_state 의 결과를 다듬는다(drafts.refine_slot_state): 글이 아직 main 에 없는 초안 슬롯은 DRAFT_PENDING,
    만들 차례인데 그 슬롯의 초안 브랜치가 이미 원격에 있으면 DRAFT_PENDING, 브랜치를 확인하지 못했으면 DRAFT_CHECK_FAILED.
    연습 실행(DRY_RUN)은 네트워크를 쓰지 않으므로 브랜치를 확인하지 않는다."""
    date_str = now.strftime("%Y-%m-%d")
    exists = False
    if state == "DUE" and not DRY_RUN:
        from pipeline import draft_flow   # git 을 부르는 모듈은 승인 흐름에서만 읽는다
        exists = draft_flow.remote_branch_exists(drafts.branch_name(date_str, slot))
    return drafts.refine_slot_state(state, slot, history, date_str, exists)


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
        write_step_summary(f"### Chance_Blog 실행 요약\n- {fix_images()}" + "".join(f"\n- {line}" for line in usage_lines()))
    elif EVENT_NAME == "schedule":
        now = now_kst()
        history = read_history()
        slot, state = slot_state(history, now)
        draft_flow = draft_flow_on()
        if draft_flow:
            state = refine_for_drafts(state, slot, history, now)
        if state != "DUE":
            reason = (DRAFT_SKIP_REASONS[state].format(slot=slot) if state in DRAFT_SKIP_REASONS
                      else "첫 게시 시각 전" if state == "OUT_OF_WINDOW"
                      else f"{slot}시 슬롯 글이 이미 있음")
            print(skip_line(state, now=now.isoformat(timespec="minutes"),
                            slots=",".join(str(h) for h in SLOT_HOURS)))
            print(f"[스케줄] {now:%Y-%m-%d %H:%M} KST - 지금 만들 글이 없습니다 "
                  f"({reason}; 게시 시각 KST {SLOT_HOURS}시).")
            if state == drafts.STATE_CHECK_FAILED:
                print("::warning::초안 브랜치를 확인하지 못해 이번 실행은 글을 만들지 않았습니다. 다음 실행에서 다시 시도합니다.")
            write_step_summary(f"### Chance_Blog 실행 요약\n- 실행: 스케줄 · {now:%Y-%m-%d %H:%M} KST\n"
                               f"- 결과: **{state}** — {reason}"
                               f"({'다음 실행에서 다시 확인' if state == drafts.STATE_CHECK_FAILED else '정상 건너뜀'})")
            return
        print(f"[스케줄] {now:%Y-%m-%d %H:%M} KST - {slot}시 슬롯 글을 생성합니다.")
        report = {}
        result = generate_blog_posts(slot=slot, allow_auto_topic=False, report=report, draft_flow=draft_flow)
        finish_run(result, report, "schedule", now, slot)
    else:
        report = {}
        note_manual_over_cap(report)
        result = generate_blog_posts(report=report, draft_flow=draft_flow_on())
        finish_run(result, report, EVENT_NAME or "manual", now_kst())


def run_cli():
    """`python generator.py` 진입점. 예외로 끝나도 요약에 결과와 사용량을 남기고 예외는 그대로 다시 던진다(Actions 빨강)."""
    try:
        main()
    except Exception as exc:
        print(f"작업 실패: {type(exc).__name__}: {_one_line(_scrub(exc), 600)}")
        write_step_summary(failure_summary(exc))
        raise


if __name__ == "__main__":
    run_cli()
