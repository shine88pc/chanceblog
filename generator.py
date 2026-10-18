import os
import json
import datetime
import urllib.request
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

def load_history():
    if os.path.exists("history.json"):
        with open("history.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def fetch_recent_news():
    url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
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
                    recent_items.append(f"Title: {title}\nSummary: {desc}")
            except Exception:
                recent_items.append(f"Title: {title}\nSummary: {desc}")
        return recent_items[:20]
    except Exception as e:
        print(f"뉴스 수집 오류: {e}")
        return []

def handle_natural_language_issue():
    print(f"모바일 이슈 제어 접수 - 제목: {issue_title}")
    
    files_data = {}
    for root, dirs, files in os.walk("."):
        if ".git" in root or "__pycache__" in root or "downloads" in root:
            continue
        for file in files:
            if file.endswith((".py", ".yml", ".md", ".json", ".html")):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        files_data[filepath] = f.read()
                except Exception:
                    pass

    prompt = f"""
    You are Chance, a passionate personal tech blogger. Analyze the user's mobile issue request and manage the blog repository files.
    [Issue Title]: {issue_title}
    [Issue Body]: {issue_body}
    [Files Data]: {json.dumps({k: v[:500] for k, v in files_data.items()}, ensure_ascii=False)}
    
    Return ONLY a pure JSON object without markdown formatting.
    {{
      "target_file": "path/to/file",
      "file_content": "file content",
      "delete_file": false
    }}
    """
    
    response = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    result_text = response.text.strip()
    if result_text.startswith("```"):
        lines = result_text.splitlines()
        if lines[0].startswith("```"): lines = lines[1:]
        if lines and lines[-1].startswith("```"): lines = lines[:-1]
        result_text = "\n".join(lines)
        
    try:
        action_data = json.loads(result_text)
        target_file = action_data.get("target_file")
        file_content = action_data.get("file_content")
        is_delete = action_data.get("delete_file", False)
        
        if is_delete and target_file and os.path.exists(target_file):
            os.remove(target_file)
        elif target_file and file_content:
            os.makedirs(os.path.dirname(target_file), exist_ok=True) if "/" in target_file else None
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(file_content)
    except Exception as e:
        print(f"이슈 처리 오류: {e}")

def generate_hot_topic_post():
    history = load_history()
    news_pool = fetch_recent_news()
    news_text = "\n---\n".join(news_pool) if news_pool else "No recent trend news"

    prompt = f"""
    You are 'Chance', a seasoned tech enthusiast and writer running a personal blog.
    Write TWO in-depth, engaging personal blog posts (one in Korean, one in English) based on real-time news trends.
    
    [Previous Topics (Avoid exact repetition)]: {json.dumps(history, ensure_ascii=False)}
    [News Data]: {news_text}
    
    [WRITING STYLE & GUIDELINES]:
    1. Write like a HUMAN TECH BLOGGER sharing insightful thoughts, not an AI summarizer.
    2. Make the posts LONG, IN-DEPTH, and DETAILED (3-4 comprehensive sections). Include background context, key analytical points, and personal takeaways.
    3. Category guidelines:
       - Korean Category MUST start with "KR - " (e.g., "KR - 테크 이야기", "KR - AI인사이트")
       - English Category MUST start with "EN - " (e.g., "EN - Tech Stories", "EN - AI Insights")
    4. Provide 3~5 SEO keywords/tags for search engines (e.g. ["인공지능", "테크", "트렌드"]).
    5. Include an Unsplash copyright-free image thumbnail URL.
    
    [CRITICAL FORMAT RULE]:
    Output MUST be a pure JSON object ONLY without markdown code blocks (` ```json `).
    
    {{
      "kr_title": "자연스러운 한글 블로그 제목",
      "kr_category": "KR - 카테고리명",
      "kr_tags": ["키워드1", "키워드2", "키워드3"],
      "kr_image": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1000&q=80",
      "kr_content": "---\\nlayout: post\\ntitle: \\"자연스러운 한글 블로그 제목\\"\\ncategory: \\"KR - 카테고리명\\"\\ntags: [\\'키워드1\\', \\'키워드2\\']\\nlang: kr\\nimage: \\"https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1000&q=80\\"\\n---\\n\\n![Thumbnail](https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1000&q=80)\\n\\n# 자연스러운 한글 블로그 제목\\n\\n깊이있는 본문 에세이 내용...",
      
      "en_title": "Engaging Personal English Title",
      "en_category": "EN - CategoryName",
      "en_tags": ["Keyword1", "Keyword2"],
      "en_image": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1000&q=80",
      "en_content": "---\\nlayout: post\\ntitle: \\"Engaging Personal English Title\\"\\ncategory: \\"EN - CategoryName\\"\\ntags: [\\'Keyword1\\', \\'Keyword2\\']\\nlang: en\\nimage: \\"https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1000&q=80\\"\\n---\\n\\n![Thumbnail](https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1000&q=80)\\n\\n# Engaging Personal English Title\\n\\nDetailed essay content..."
    }}
    """
    
    response = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    result_text = response.text.strip()
    
    if result_text.startswith("```"):
        lines = result_text.splitlines()
        if lines[0].startswith("```"): lines = lines[1:]
        if lines and lines[-1].startswith("```"): lines = lines[:-1]
        result_text = "\n".join(lines)
        
    try:
        data = json.loads(result_text)
        date_str = datetime.datetime.now().strftime('%Y-%m-%d')
        timestamp = datetime.datetime.now().strftime('%H%M%S')
        
        os.makedirs("_posts", exist_ok=True)
        
        kr_filename = f"_posts/{date_str}-KR-{timestamp}.md"
        with open(kr_filename, "w", encoding="utf-8") as f:
            f.write(data["kr_content"])
            
        en_filename = f"_posts/{date_str}-EN-{timestamp}.md"
        with open(en_filename, "w", encoding="utf-8") as f:
            f.write(data["en_content"])
            
        print(f"개인 블로그 톤 포스트 생성 완료 ({data.get('kr_category')})")
        
        if data.get("kr_title") not in history:
            history.append(data.get("kr_title"))
            save_history(history)
            
    except Exception as e:
        print(f"포스트 생성 실패: {e}\n응답 원본: {result_text}")

def main():
    if event_name == "issues" and issue_title:
        handle_natural_language_issue()
    else:
        generate_hot_topic_post()

if __name__ == "__main__":
    main()
