import os
import json
import datetime
import urllib.request
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import timezone, timedelta
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")

client = genai.Client(api_key=API_KEY)

event_name = os.environ.get("EVENT_NAME")
issue_title = os.environ.get("ISSUE_TITLE", "")
issue_body = os.environ.get("ISSUE_BODY", "")

KST = timezone(timedelta(hours=9))

IMAGE_POOL = [
    "https://images.unsplash.com/photo-1591488320449-011701bb6704?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1550745165-9bc0b252726f?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1555680202-c86f0e12f086?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1563770660941-20978e870e26?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1507146426996-ef05306b995a?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1531482615713-2afd69097998?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1541185933-ef5d8ed016c2?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1614728894747-a83421e2b9c9?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1484589065579-248aad0d8b13?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1517976487502-5f654b0c2794?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1563986768609-322da13575f3?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1510511459019-5dda7724fd87?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1544197150-b99a580bb7a8?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1519501025264-65ba15a82390?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1473968512647-3e447244af8f?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1508739773434-c26b3d09e071?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1535378917042-10a22c95931a?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1504639725590-34d0984388bd?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1518773553398-650c184e0bb3?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1531297484001-80022131f5a1?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1000&q=80"
]

def extract_photo_id(url):
    m = re.search(r'photo-([a-zA-Z0-9_-]+)', url)
    return m.group(1) if m else url

def get_all_used_images():
    used = set()
    if os.path.exists("_posts"):
        for root, _, files in os.walk("_posts"):
            for file in files:
                if file.endswith(".md"):
                    fpath = os.path.join(root, file)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            text = f.read()
                            urls = re.findall(r'https://images\.unsplash\.com/[^\s"\'\)]+', text)
                            for u in urls:
                                used.add(extract_photo_id(u))
                    except Exception:
                        pass
    return used

def select_unique_image(used_ids):
    for img_url in IMAGE_POOL:
        pid = extract_photo_id(img_url)
        if pid not in used_ids:
            used_ids.add(pid)
            return img_url
    now_ts = int(datetime.datetime.now().timestamp())
    fallback_url = f"https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1000&q=80&sig={now_ts}"
    return fallback_url

def fix_existing_duplicate_images():
    if not os.path.exists("_posts"):
        return
    seen_ids = set()
    for root, _, files in sorted(os.walk("_posts")):
        for file in sorted(files):
            if file.endswith(".md"):
                fpath = os.path.join(root, file)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    urls = re.findall(r'https://images\.unsplash\.com/[^\s"\'\)]+', content)
                    if not urls:
                        continue
                    curr_url = urls[0]
                    curr_id = extract_photo_id(curr_url)
                    if curr_id in seen_ids:
                        new_img = select_unique_image(seen_ids)
                        new_content = re.sub(re.escape(curr_url), new_img, content)
                        with open(fpath, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        print(f"Fixed duplicate image in {fpath}: replaced with {new_img}")
                    else:
                        seen_ids.add(curr_id)
                except Exception as e:
                    print(f"Error inspecting {fpath}: {e}")

def handle_issue_event():
    files_data = {}
    for root, dirs, files in os.walk("."):
        if any(p in root for p in [".git", ".github", "_site", "node_modules", ".jekyll-cache"]):
            continue
        for file in files:
            filepath = os.path.join(root, file)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    files_data[filepath] = f.read(500)
            except Exception:
                pass

    prompt = f"""
    You are Chance, a passionate personal tech blogger. Analyze the user's mobile issue request and manage the blog repository files.
    [Issue Title]: {issue_title}
    [Issue Body]: {issue_body}
    [Files Data]: {json.dumps(files_data, ensure_ascii=False)}
    
    Return ONLY a pure JSON object without markdown formatting.
    {{
      "target_file": "path/to/file",
      "file_content": "file content",
      "delete_file": false
    }}
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    text = response.text.strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        data = json.loads(match.group(0))
        target_file = data.get("target_file")
        file_content = data.get("file_content")
        delete_file = data.get("delete_file", False)
        if target_file:
            if delete_file:
                if os.path.exists(target_file):
                    os.remove(target_file)
                    print(f"Deleted: {target_file}")
            else:
                dirname = os.path.dirname(target_file)
                if dirname:
                    os.makedirs(dirname, exist_ok=True)
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(file_content)
                print(f"Updated: {target_file}")

def generate_blog_posts():
    fix_existing_duplicate_images()
    used_images = get_all_used_images()

    history = []
    if os.path.exists("history.json"):
        try:
            with open("history.json", "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    news_items = []
    rss_urls = [
        "https://news.google.com/rss/search?q=AI+%ED%85%8C%ED%81%AC+%EA%B8%B0%EC%88%A0&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtdHZHZ0pMVWlnQVAB?hl=ko&gl=KR&ceid=KR:ko"
    ]
    for url in rss_urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                root = ET.fromstring(resp.read())
                for item in root.findall(".//item"):
                    t = item.find("title")
                    if t is not None and t.text:
                        title_clean = re.sub(r"\s*-[^-]+$", "", t.text).strip()
                        if title_clean and title_clean not in history:
                            news_items.append(title_clean)
        except Exception as e:
            print(f"RSS fetch error: {e}")

    selected_news = news_items[0] if news_items else "최신 AI 혁신 및 테크 아키텍처 트렌드 분석"
    selected_image = select_unique_image(used_images)

    now = datetime.datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")

    post_prompt = f"""
당신은 개인 기술 전문 블로거 'Chance'입니다.
선정된 뉴스 주제를 바탕으로 깊이 있는 분석과 통찰이 담긴 블로그 포스트를 한국어(KR)와 영어(EN) 각각 1개씩 작성해주세요.

주제: {selected_news}
이전에 다룬 주제 목록 (중복 금지): {json.dumps(history[-10:], ensure_ascii=False)}

대표 이미지 URL로 다음 URL을 사용해야 합니다: {selected_image}
(이미 한번 사용된 다른 이미지나 임의의 중복 이미지는 절대 사용하지 마세요)

결과는 반드시 아래 JSON 형식으로만 응답해주세요:
{{
  "kr_category": "KR - 카테고리명",
  "kr_title": "한국어 포스트 제목",
  "kr_tags": ["태그1", "태그2"],
  "kr_content": "---\nlayout: post\ntitle: ...\ncategory: ...\ntags: ...\nlang: kr\nimage: \"{selected_image}\"\n---\n\n![Thumbnail]({selected_image})\n\n본문 내용...",
  "en_category": "EN - CategoryName",
  "en_title": "English Post Title",
  "en_tags": ["Tag1", "Tag2"],
  "en_content": "---\nlayout: post\ntitle: ...\ncategory: ...\ntags: ...\nlang: en\nimage: \"{selected_image}\"\n---\n\n![Thumbnail]({selected_image})\n\nPost body..."
}}
"""

    resp = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=post_prompt
    )
    raw_json = resp.text.strip()
    match = re.search(r'\{.*\}', raw_json, re.DOTALL)
    if not match:
        print("Failed to parse post generation response.")
        return

    post_data = json.loads(match.group(0))

    kr_cat = post_data.get("kr_category", "KR - 테크 이야기")
    kr_content = post_data.get("kr_content", "")
    en_cat = post_data.get("en_category", "EN - Tech Insights")
    en_content = post_data.get("en_content", "")

    kr_dir = os.path.join("_posts", kr_cat)
    en_dir = os.path.join("_posts", en_cat)
    os.makedirs(kr_dir, exist_ok=True)
    os.makedirs(en_dir, exist_ok=True)

    kr_path = os.path.join(kr_dir, f"{date_str}-KR-{time_str}.md")
    en_path = os.path.join(en_dir, f"{date_str}-EN-{time_str}.md")

    with open(kr_path, "w", encoding="utf-8") as f:
        f.write(kr_content)
    with open(en_path, "w", encoding="utf-8") as f:
        f.write(en_content)

    history.append(post_data.get("kr_title", selected_news))
    if len(history) > 100:
        history = history[-100:]
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated posts:\n- {kr_path}\n- {en_path}")

if __name__ == "__main__":
    if event_name == "issues" or (issue_title and issue_title.strip()):
        handle_issue_event()
    else:
        generate_blog_posts()
