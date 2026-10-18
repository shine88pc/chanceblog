import os
import json
import datetime
import urllib.request
import xml.etree.ElementTree as ET
import requests
import re
from email.utils import parsedate_to_datetime
from datetime import timezone, timedelta
from google import genai
from pathlib import Path

# 환경 변수
API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "shine88pc/chanceblog")
EVENT_NAME = os.environ.get("EVENT_NAME", "").lower()
ISSUE_TITLE = os.environ.get("ISSUE_TITLE", "")
ISSUE_BODY = os.environ.get("ISSUE_BODY", "")
ISSUE_NUMBER = os.environ.get("ISSUE_NUMBER")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY 환경 변수가 없습니다.")

client = genai.Client(api_key=API_KEY)

# 경로
ROOT = Path(".")
POSTS_DIR = ROOT / "_posts"
HISTORY_FILE = ROOT / "history.json"

# 이미지 풀 (필요 시 확장)
IMAGE_POOL = [
    "https://images.unsplash.com/photo-1591488320449-011701bb6704?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1555680202-c86f0e12f086?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1563770660941-20978e870e26?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1677442136019-21780ecad985?auto=format&fit=crop&w=1000&q=80",
]

KST = timezone(timedelta(hours=9))

# 유틸리티

def load_history():
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_history(history):
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_recent_news():
    url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        recent_items = []
        now = datetime.datetime.now(timezone.utc)
        for item in root.findall('.//item'):
            title = item.find('title').text if item.find('title') is not None else ""
            desc = item.find('description').text if item.find('description') is not None else ""
            pub_date_str = item.find('pubDate').text if item.find('pubDate') is not None else ""
            try:
                pub_date = parsedate_to_datetime(pub_date_str)
                if now - pub_date <= timedelta(hours=24):
                    recent_items.append(f"{title} - {desc}")
            except Exception:
                recent_items.append(f"{title} - {desc}")
        return recent_items[:40]
    except Exception as e:
        print(f"뉴스 수집 오류: {e}")
        return []


def normalize_text(s):
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


def get_used_image_ids():
    used = set()
    if not POSTS_DIR.exists():
        return used
    for p in POSTS_DIR.rglob("*.md"):
        try:
            txt = p.read_text(encoding="utf-8")
            matches = re.findall(r'https://images\.unsplash\.com/[^)"\s]+', txt)
            for m in matches:
                used.add(m)
        except Exception:
            continue
    return used


def select_unique_image(used_set):
    for url in IMAGE_POOL:
        if url not in used_set:
            used_set.add(url)
            return url
    # fallback: return first with timestamp sig to reduce exact duplicates
    ts = int(datetime.datetime.now().timestamp())
    return IMAGE_POOL[0] + f"&sig={ts}"


def safe_filename(title):
    # Jekyll _posts 규칙: YYYY-MM-DD-title.md
    safe = re.sub(r"[^0-9A-Za-z-_ ]", "", title)
    safe = "-".join(safe.split())
    safe = safe[:50]
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    return f"{date_str}-{safe}.md"


def write_post_file(filename, content):
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    path = POSTS_DIR / filename
    tmp = path.with_suffix('.md.tmp')
    tmp.write_text(content, encoding='utf-8')
    tmp.replace(path)
    print(f"파일 생성/수정: {path}")
    return path


# Gemini 호출(간단한 wrapper)
def call_gemini(prompt, model='gemini-3.8-flash'):
    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        return getattr(resp, 'text', '')
    except Exception as e:
        print(f"Gemini 호출 실패: {e}")
        return ''


# 자동 포스트 생성

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

    # 제목 추출
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

    # 이미지 선택
    used = get_used_image_ids()
    image = select_unique_image(used)

    # Ensure front matter contains image and title
    if resp.lstrip().startswith('---'):
        content = resp
        if 'image:' not in resp:
            # insert image into front matter
            content = re.sub(r'---\n(.*?)\n---', lambda m: f"---\n{m.group(1)}\nimage: \"{image}\"\n---", resp, flags=re.S)
    else:
        # add front matter
        content = f"---\nlayout: post\ntitle: \"{title}\"\ncategory: General\ntags: []\nlang: kr\nimage: \"{image}\"\n---\n\n" + resp

    filename = safe_filename(title)
    path = write_post_file(filename, content)

    # update history
    history.append(title)
    save_history(history)


# 이슈 처리 (AI에게 명령 전달하여 파일 수정/삭제)

def handle_issue_with_params(title, body, issue_number=None):
    print(f"이슈 처리: {title}")
    files_data = {}
    for root, dirs, files in os.walk('.'):
        if any(x in root for x in ['.git', '__pycache__']):
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

    # attempt to extract JSON
    try:
        obj_text = re.search(r'\{.*\}', resp, re.S).group(0)
        data = json.loads(obj_text)
    except Exception as e:
        print(f"AI 응답 파싱 실패: {e}")
        return

    target = data.get('target_file')
    content = data.get('file_content')
    delete_flag = data.get('delete_file', False)

    if delete_flag and target and os.path.exists(target):
        os.remove(target)
        print(f"파일 삭제: {target}")
    elif target and content:
        # ensure it's within repo and in _posts or allowed paths
        # if target is under _posts subdir, normalize to root _posts
        if target.startswith('_posts/') and '/' in target[7:]:
            # move to root _posts
            base = os.path.basename(target)
            target = f"_posts/{base}"
        # write file
        p = Path(target)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        print(f"파일 생성/수정: {p}")

    # 댓글 및 이슈 닫기
    if issue_number and GITHUB_TOKEN:
        headers = {'Authorization': f'token {GITHUB_TOKEN}', 'Accept': 'application/vnd.github+json'}
        repo = GITHUB_REPOSITORY
        comment_url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
        close_url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
        try:
            requests.post(comment_url, headers=headers, json={"body": "이슈를 반영해서 파일을 수정했습니다. 페이지 반영 확인 후 문제가 있으면 다시 알려주세요."})
            requests.patch(close_url, headers=headers, json={"state": "closed"})
            print(f"이슈 댓글 작성 및 닫기 완료: {issue_number}")
        except Exception as e:
            print(f"이슈 처리 후 댓글/닫기 실패: {e}")


# 오픈된 이미지 관련 이슈 자동 처리

def process_open_control_issues():
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN 없음: 오픈 이슈 자동 처리 불가")
        return
    headers = {'Authorization': f'token {GITHUB_TOKEN}', 'Accept': 'application/vnd.github+json'}
    repo = GITHUB_REPOSITORY
    issues_url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page=100"
    try:
        resp = requests.get(issues_url, headers=headers, timeout=15)
        items = resp.json()
    except Exception as e:
        print(f"이슈 목록 조회 실패: {e}")
        return

    for it in items:
        title = it.get('title','')
        number = it.get('number')
        body = it.get('body','') or ''
        if title and '[Control]' in title and ('이미지' in title or '이미지' in body):
            try:
                handle_issue_with_params(title, body, issue_number=number)
            except Exception as e:
                print(f"이슈 처리 중 오류 ({number}): {e}")


def main():
    try:
        # 이벤트 기반 실행
        if EVENT_NAME == 'issues' and ISSUE_TITLE:
            # when triggered by an issue event, workflow provides ISSUE_NUMBER
            num = ISSUE_NUMBER
            handle_issue_with_params(ISSUE_TITLE, ISSUE_BODY, issue_number=num)
            return

        # For schedule/push/workflow_dispatch: generate post and process open control issues
        generate_hot_topic_post()
        process_open_control_issues()

    except Exception as exc:
        print(f"작업 실패: {type(exc).__name__}: {exc}")
        raise


if __name__ == '__main__':
    main()
