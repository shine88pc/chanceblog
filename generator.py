import os
import json
import datetime
import urllib.request
import xml.etree.ElementTree as ET
import re
from email.utils import parsedate_to_datetime
from datetime import timezone, timedelta
from pathlib import Path
import difflib

# Optional imports
try:
    import requests
except Exception:
    requests = None

# 환경 변수
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "shine88pc/chanceblog")
EVENT_NAME = os.environ.get("EVENT_NAME", "").lower()
ISSUE_TITLE = os.environ.get("ISSUE_TITLE", "")
ISSUE_BODY = os.environ.get("ISSUE_BODY", "")
ISSUE_NUMBER = os.environ.get("ISSUE_NUMBER")

# Mode flags
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
FIX_IMAGES = os.environ.get("FIX_IMAGES", "0") == "1"

# Constants and paths
ROOT = Path('.')
POSTS_DIR = ROOT / '_posts'
HISTORY_FILE = ROOT / 'history.json'

# Keep a small IMAGE_POOL but per requirements it will NOT be used as a silent fallback
IMAGE_POOL = [
    'https://images.unsplash.com/photo-1518770660439-4636190af475',
    'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe',
    'https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5',
    'https://images.unsplash.com/photo-1451187580459-43490279c0fa',
    'https://images.unsplash.com/photo-1677442136019-21780ecad985',
]

KST = timezone(timedelta(hours=9))

SAFE_REPO_PATH = ['_posts']  # allowed paths for generators to write into
MODEL_FALLBACKS = ['gemini-3.8-flash', 'gpt-4o-mini']

TECH_KEYWORDS = ['AI', '인공지능', '기술', '테크', 'robot', 'space', 'rocket', 'satellite', 'gpu', 'hardware']


# ----------------------- Utilities -----------------------

def load_history():
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []


def save_history(history):
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')


def normalize_text(s):
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


def normalize_image_url_to_path(url):
    """Return scheme://netloc/path (no query, no fragment) for comparison."""
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        path_only = urlunparse((p.scheme, p.netloc, p.path, '', '', ''))
        return path_only
    except Exception:
        return url


def is_local_path(url):
    return url.startswith('/') or url.startswith('./') or url.startswith('../')


# ----------------------- Unsplash -----------------------

def search_unsplash(query, per_page=10):
    """Search Unsplash. If DRY_RUN: Gemini is stubbed but Unsplash should be called unless no key.
    If UNSPLASH_ACCESS_KEY missing -> behave as stub.
    Returns list of result dicts with 'id' and 'url' (normalized path) and 'raw_url'."""
    if not UNSPLASH_ACCESS_KEY:
        # stub
        print(f"[Unsplash Stub] no key, search('{query}')")
        return []
    if requests is None:
        print("requests 패키지 없음: Unsplash 호출 불가")
        return []
    url = 'https://api.unsplash.com/search/photos'
    headers = {'Authorization': f'Client-ID {UNSPLASH_ACCESS_KEY}', 'Accept-Version': 'v1'}
    params = {'query': query, 'per_page': per_page, 'orientation': 'landscape'}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code != 200:
            print(f"Unsplash API error {r.status_code}: {r.text[:200]}")
            return []
        data = r.json()
        results = []
        for it in data.get('results', []):
            raw = it.get('urls', {}).get('raw') or it.get('urls', {}).get('full') or it.get('urls', {}).get('regular')
            if not raw:
                continue
            norm = normalize_image_url_to_path(raw)
            results.append({'id': it.get('id'), 'path': norm, 'raw': raw})
        return results
    except Exception as e:
        print(f"Unsplash request failed: {e}")
        return []


# ----------------------- File & Image bookkeeping -----------------------

def get_used_images_paths():
    """Collect normalized image paths used across _posts and history."""
    used = set()
    if not POSTS_DIR.exists():
        return used
    for p in POSTS_DIR.rglob('*.md'):
        try:
            txt = p.read_text(encoding='utf-8')
        except Exception:
            continue
        # find urls
        for m in re.findall(r'https?://[^)"\s]+', txt):
            if 'images.unsplash.com' in m:
                used.add(normalize_image_url_to_path(m))
        # frontmatter local images
        m_local = re.findall(r'image:\s*["\']?([^\n"\']+)', txt)
        for im in m_local:
            if is_local_path(im):
                # check existence
                loc = (ROOT / im.lstrip('/'))
                if loc.exists():
                    # local file; we do not use local images for selection, but note path
                    used.add(im)
                else:
                    used.add(im)
    # history.json may contain URLs (best-effort)
    hist = load_history()
    for h in hist:
        if isinstance(h, str) and h.startswith('http') and 'images.unsplash.com' in h:
            used.add(normalize_image_url_to_path(h))
    return used


def check_url_head_ok(url):
    """HEAD request to verify URL reachable. Returns True if status 200."""
    if is_local_path(url):
        p = ROOT / url.lstrip('/')
        return p.exists()
    if requests is None:
        return False
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False


# ----------------------- Gemini -----------------------

def call_gemini(prompt, model=None):
    """If DRY_RUN: stub Gemini only. Otherwise try real client via genai if available or stub fallback."""
    if DRY_RUN:
        print(f"[DRY_RUN] call_gemini(prompt[:60]) -> stub response")
        # Return a simple markdown with frontmatter stub
        stub = ('---\nlayout: post\ntitle: "DRY_RUN Sample"\ncategory: General\ntags: []\nlang: kr\nimage: ""\n---\n\n# DRY_RUN Sample\n\n내용')
        return stub
    # Real call: attempt genai client if available
    try:
        from google import genai
        if not GEMINI_API_KEY:
            print('GEMINI_API_KEY 없음: Gemini 호출 불가')
            return ''
        client = genai.Client(api_key=GEMINI_API_KEY)
        model_to_use = model or MODEL_FALLBACKS[0]
        resp = client.models.generate_content(model=model_to_use, contents=prompt)
        return getattr(resp, 'text', '')
    except Exception as e:
        print(f"Gemini 호출 실패: {e}")
        return ''


# ----------------------- Helpers for generation -----------------------

def safe_filename(title, lang=None):
    """Format: {date}-{KR|EN}-{HHMMSS}.md to avoid overwriting when title sanitized duplicates."""
    now = datetime.datetime.now(KST)
    date_str = now.strftime('%Y-%m-%d')
    hh = now.strftime('%H%M%S')
    L = 'KR' if (lang or '').lower().startswith('k') else 'EN'
    return f"{date_str}-{L}-{hh}.md"


def write_post_file(filename, content):
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    path = POSTS_DIR / filename
    if DRY_RUN:
        print(f"[DRY_RUN] would write file: {path}")
        return path
    path_tmp = path.with_suffix('.md.tmp')
    path_tmp.write_text(content, encoding='utf-8')
    path_tmp.replace(path)
    print(f"파일 생성/수정: {path}")
    return path


# ----------------------- Post generation logic -----------------------

def build_image_queries(post_title, tags):
    """Return list of candidate English 2-4 word queries derived from title+tags. Exclude face/logo terms heuristically."""
    candidates = []
    # prefer tags first
    for t in tags:
        if isinstance(t, str):
            candidates.append(t)
    # extract english words from title
    words = re.findall(r"[A-Za-z]+", post_title)
    if words:
        # create 2-4 word phrases
        for n in range(4,1,-1):
            if len(words) >= n:
                candidates.append(' '.join(words[:n]))
    # fallback: split title into words and pick first 2
    if not candidates:
        candidates.append(' '.join(words[:2]) or post_title)
    # filter out face/logo words
    filtered = [c for c in candidates if not re.search(r'face|portrait|logo|emblem|trademark', c, flags=re.I)]
    return filtered[:6]


def select_unique_unsplash_image(post, used_paths):
    """Try queries and pick the first Unsplash result whose normalized path is not in used_paths and HEAD ok.
    If no result -> return None (caller must abort saving)."""
    queries = build_image_queries(post.get('title',''), post.get('tags', []))
    for q in queries:
        results = search_unsplash(q)
        for r in results:
            path = r.get('path')
            raw = r.get('raw')
            if not path or path in used_paths:
                continue
            # verify HEAD reachable
            if check_url_head_ok(raw):
                used_paths.add(path)
                return raw, path
    # no candidate found
    return None, None


def parse_frontmatter(txt):
    match = re.match(r'^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$', txt)
    if not match:
        return {}, txt
    yaml = match.group(1)
    body = match.group(2)
    meta = {}
    for line in yaml.split('\n'):
        if ':' in line:
            k, v = line.split(':',1)
            k = k.strip()
            v = v.strip()
            if v.startswith('[') and v.endswith(']'):
                try:
                    meta[k] = [s.strip().strip('"\'') for s in v[1:-1].split(',') if s.strip()]
                except Exception:
                    meta[k] = []
            else:
                v = v.strip('"').strip("'")
                meta[k] = v
    return meta, body


def ensure_frontmatter_image_and_lang(raw_md, chosen_image_url, lang_override=None):
    meta, body = parse_frontmatter(raw_md)
    if not meta:
        fm = f"---\nlayout: post\ntitle: \"{meta.get('title','') or 'Untitled'}\"\ncategory: General\ntags: []\nlang: {lang_override or 'kr'}\nimage: \"{chosen_image_url}\"\n---\n\n"
        return fm + raw_md
    # always overwrite image with ours
    meta['image'] = chosen_image_url
    if lang_override:
        meta['lang'] = lang_override
    # rebuild frontmatter
    fm_lines = []
    for k, v in meta.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}: [{', '.join(v)}]")
        else:
            fm_lines.append(f"{k}: \"{v}\"" if ' ' in str(v) else f"{k}: {v}")
    fm = '---\n' + '\n'.join(fm_lines) + '\n---\n\n'
    return fm + body


# ----------------------- Duplicate image fixer -----------------------

def fix_existing_duplicate_images():
    """Identify duplicated normalized image paths and replace images for newer posts.
    Keeps oldest (by filename/date) and replaces others using Unsplash selection. Aborts saving if no candidate found for a post.
    """
    used = get_used_images_paths()
    # collect posts with their image path and date
    posts = []
    for p in POSTS_DIR.rglob('*.md'):
        try:
            txt = p.read_text(encoding='utf-8')
        except Exception:
            continue
        meta, _ = parse_frontmatter(txt)
        image = meta.get('image','')
        norm = normalize_image_url_to_path(image) if image and image.startswith('http') else image
        posts.append({'path':p, 'meta':meta, 'norm_image':norm, 'raw':txt})
    # group by norm_image
    groups = {}
    for it in posts:
        key = it['norm_image']
        if not key:
            continue
        groups.setdefault(key, []).append(it)
    to_replace = []
    for key, items in groups.items():
        if len(items) <= 1:
            continue
        # sort by filename or date; keep oldest
        items.sort(key=lambda x: x['path'].name)
        keeper = items[0]
        others = items[1:]
        for o in others:
            to_replace.append((o, keeper))
    # perform replacements (simulate if DRY_RUN)
    replace_plan = []
    for target, keeper in to_replace:
        post_meta = target['meta']
        chosen_raw, chosen_path = select_unique_unsplash_image({'title': post_meta.get('title', ''), 'tags': post_meta.get('tags', [])}, used)
        if not chosen_raw:
            raise RuntimeError(f"No Unsplash candidate for {target['path']}; aborting as per policy")
        replace_plan.append({'target':str(target['path']), 'new_image_raw':chosen_raw, 'new_image_norm':chosen_path})
        if not DRY_RUN:
            new_text = ensure_frontmatter_image_and_lang(target['raw'], chosen_raw, lang_override=post_meta.get('lang'))
            target['path'].write_text(new_text, encoding='utf-8')
    # Logging
    for r in replace_plan:
        print(f"Replace planned: {r['target']} -> {r['new_image_norm']}")
    return replace_plan


# ----------------------- Main generator (hot topic) -----------------------

def fetch_recent_news():
    url = 'https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        recent_items = []
        now = datetime.datetime.now(datetime.timezone.utc)
        for item in root.findall('.//item'):
            title = item.find('title').text or ''
            desc = item.find('description').text or ''
            pub_date_str = item.find('pubDate').text or ''
            try:
                pub_date = parsedate_to_datetime(pub_date_str)
                if now - pub_date <= timedelta(hours=24):
                    # technical keyword filter
                    if any(k.lower() in (title+desc).lower() for k in TECH_KEYWORDS):
                        recent_items.append(f"{title} - {desc}")
            except Exception:
                if any(k.lower() in (title+desc).lower() for k in TECH_KEYWORDS):
                    recent_items.append(f"{title} - {desc}")
        return recent_items[:40]
    except Exception as e:
        print(f"뉴스 수집 오류: {e}")
        return []


def title_similar(a, b):
    a_n = normalize_text(a)
    b_n = normalize_text(b)
    # token overlap
    a_tokens = set(re.findall(r"\w+", a_n))
    b_tokens = set(re.findall(r"\w+", b_n))
    if not a_tokens or not b_tokens:
        return False
    overlap = len(a_tokens & b_tokens) / max(len(a_tokens), len(b_tokens))
    if overlap >= 0.6:
        return True
    # difflib fallback
    ratio = difflib.SequenceMatcher(None, a_n, b_n).ratio()
    return ratio >= 0.75


def generate_hot_topic_post():
    history = load_history()
    normalized = {normalize_text(h): h for h in history}
    news_pool = fetch_recent_news()
    news_text = '\n---\n'.join(news_pool) if news_pool else '최근 트렌드 뉴스 없음'

    prompt = f"""
최근 24시간 실시간 뉴스를 분석하여 독창적인 블로그 글 1개를 작성하세요.
[이전 주제 목록 (중복 금지)]: {history}
[뉴스 데이터]: {news_text}
[조건]:
1. 마크다운 형식 작성(Front Matter 포함).
2. 제목은 # 으로 시작.
3. Front Matter에 layout, title, category, tags, lang, image 를 포함.
4. 제목이 기존 기록과 중복되는 경우 다른 주제를 선택하세요.
"""
    resp = call_gemini(prompt)
    if not resp:
        print("Gemini 응답 없음 — 생성 건너뜀")
        return
    title = None
    for line in resp.splitlines():
        if line.startswith('# '):
            title = line.replace('# ', '').strip()
            break
    if not title:
        title = f"실시간 트렌드 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if normalize_text(title) in normalized:
        print("제목이 이전 기록과 중복되어 생성하지 않습니다.")
        return
    used = get_used_images_paths()
    # choose image
    chosen_raw, chosen_norm = select_unique_unsplash_image({'title': title, 'tags': []}, used)
    if not chosen_raw:
        print("이미지 후보 없음: 글 저장을 중단합니다.")
        return
    # ensure frontmatter image overwritten
    content = resp
    content = ensure_frontmatter_image_and_lang(content, chosen_raw, lang_override='kr')
    filename = safe_filename(title, lang='kr')
    write_post_file(filename, content)
    history.append(title)
    if not DRY_RUN:
        save_history(history)


# ----------------------- Issue handling -----------------------

def get_issue_author(repo, issue_number):
    if not GITHUB_TOKEN:
        return None
    if requests is None:
        return None
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    headers = {'Authorization': f'token {GITHUB_TOKEN}', 'Accept': 'application/vnd.github+json'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get('user', {}).get('login')
    except Exception:
        return None
    return None


def handle_issue_with_params(title, body, issue_number=None):
    repo_owner = GITHUB_REPOSITORY.split('/')[0]
    # only process if issue author is repo owner
    author = None
    if issue_number:
        author = get_issue_author(GITHUB_REPOSITORY, issue_number)
    if author != repo_owner:
        print(f"이슈 작성자({author})가 저장소 소유자({repo_owner})가 아니므로 처리하지 않습니다.")
        return
    print(f"이슈 처리: {title} (by {author})")

    # collect candidate files to create/modify in allowed paths only
    files_data = {}
    for root, dirs, files in os.walk('.'):
        # protect paths
        if any(root.startswith(p) for p in ['.github', '.git']):
            continue
        for f in files:
            if f.endswith(('.py', '.yml', '.md', '.json', '.html')):
                p = os.path.join(root, f)
                try:
                    with open(p, 'r', encoding='utf-8') as fh:
                        files_data[p] = fh.read()[:600]
                except Exception:
                    continue

    prompt = f"""
당신은 Chance_Blog 수석 관리자 AI입니다. 사용자의 이슈 지시를 분석하여 저장소 내부 파일을 생성, 수정 또는 삭제하세요.
[이슈 제목]: {title}
[이슈 본문]: {body}
[레포지토리 파일 샘플]: {json.dumps(files_data, ensure_ascii=False)}
[응답 규칙]: 오직 JSON 객체만 반환하세요.
{{
  "target_file": "_posts/2026-xx-xx-example.md",
  "file_content": "파일 전체 내용 (마크다운, Front Matter 포함)",
  "delete_file": false
}}
"""
    resp = call_gemini(prompt)
    if not resp:
        print("Gemini 응답 없음 - 이슈 처리 실패")
        return
    try:
        obj_text = re.search(r'\{.*\}', resp, re.S).group(0)
        data = json.loads(obj_text)
    except Exception as e:
        print(f"AI 응답 파싱 실패: {e}")
        return
    target = data.get('target_file')
    content = data.get('file_content')
    delete_flag = data.get('delete_file', False)
    if target:
        # enforce safe repo path
        if not any(target.startswith(p) for p in SAFE_REPO_PATH):
            print(f"허용되지 않은 경로: {target} — 무시")
            return
        # prevent protected folders
        if target.startswith('.github'):
            print('.github 수정 금지 — 무시')
            return
        p = Path(target)
        # remove flattening: preserve subfolders
        if delete_flag and p.exists():
            p.unlink()
            print(f"파일 삭제: {p}")
            return
        if content:
            # after write, validate image as for other posts
            # extract frontmatter image
            meta, body = parse_frontmatter(content)
            img = meta.get('image','')
            lang = meta.get('lang','kr')
            chosen_raw = None
            if not img or is_local_path(img) or (img and not img.startswith('http')):
                # find unsplash candidate
                used = get_used_images_paths()
                chosen_raw, chosen_norm = select_unique_unsplash_image({'title': meta.get('title',''), 'tags': meta.get('tags',[])}, used)
                if not chosen_raw:
                    print(f"이슈 처리 중 이미지 후보 없음: {target} — 중단")
                    return
                # overwrite frontmatter image
                content = ensure_frontmatter_image_and_lang(content, chosen_raw, lang_override=lang)
            # write
            if DRY_RUN:
                print(f"[DRY_RUN] would write issue target: {p}")
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding='utf-8')
                print(f"파일 생성/수정: {p}")

    # comment & close issue if requested and token provided
    if issue_number and GITHUB_TOKEN:
        try:
            comment_url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/{issue_number}/comments"
            headers = {'Authorization': f'token {GITHUB_TOKEN}', 'Accept': 'application/vnd.github+json'}
            body_text = '이슈를 반영하여 파일을 생성/수정했습니다. 페이지 반영 확인 후 문제가 있으면 알려주세요.'
            requests.post(comment_url, headers=headers, json={'body': body_text}, timeout=10)
        except Exception as e:
            print(f"이슈 댓글 작성 실패: {e}")


# ----------------------- Main flow -----------------------

def main():
    try:
        if EVENT_NAME == 'issues' and ISSUE_TITLE:
            handle_issue_with_params(ISSUE_TITLE, ISSUE_BODY, issue_number=ISSUE_NUMBER)
            return
        # scheduled / push / workflow_dispatch
        # If FIX_IMAGES mode -> run duplicate fixer and ensure imageless posts get image
        if FIX_IMAGES:
            # include imageless posts in target list
            # first, generate replacement plan for duplicates and missing images
            used = get_used_images_paths()
            replace_plan = []
            for p in POSTS_DIR.rglob('*.md'):
                try:
                    txt = p.read_text(encoding='utf-8')
                except Exception:
                    continue
                meta, body = parse_frontmatter(txt)
                img = meta.get('image','')
                norm = normalize_image_url_to_path(img) if img and img.startswith('http') else img
                # missing or local or duplicate of an existing used path
                needs_replace = False
                if not img:
                    needs_replace = True
                elif is_local_path(img):
                    needs_replace = True
                else:
                    if norm in used and list(used).count(norm) > 1:
                        needs_replace = True
                if needs_replace:
                    chosen_raw, chosen_norm = select_unique_unsplash_image({'title': meta.get('title',''), 'tags': meta.get('tags',[])}, used)
                    if not chosen_raw:
                        raise RuntimeError(f"No Unsplash candidate for {p}; abort as required")
                    replace_plan.append({'path':str(p), 'new_raw':chosen_raw, 'new_norm':chosen_norm})
                    if not DRY_RUN:
                        new_text = ensure_frontmatter_image_and_lang(txt, chosen_raw, lang_override=meta.get('lang'))
                        p.write_text(new_text, encoding='utf-8')
            for r in replace_plan:
                print(f"FIX_IMAGES planned: {r['path']} -> {r['new_norm']}")
            return
        # normal generate
        generate_hot_topic_post()
    except Exception as exc:
        print(f"작업 실패: {type(exc).__name__}: {exc}")
        raise


if __name__ == '__main__':
    main()
