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
    You are the lead manager AI of Chance_Blog. Analyze the user's mobile issue request and create, update, or delete blog files accordingly.
    [Issue Title]: {issue_title}
    [Issue Body]: {issue_body}
    [File Data]: {json.dumps({k: v[:500] for k, v in files_data.items()}, ensure_ascii=False)}
    [Response Rule]: Return ONLY a pure JSON object without markdown formatting.
    {{
      "target_file": "file path",
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
    Analyze the recent 24-hour real-time news trends and generate TWO distinct blog posts: one in KOREAN and one in ENGLISH.
    
    [Previous Topics (Do not duplicate)]: {json.dumps(history, ensure_ascii=False)}
    [News Data]: {news_text}
    
    [CRITICAL INSTRUCTIONS]:
    1. Output MUST be a pure JSON object ONLY. No markdown code blocks.
    2. 'kr_content' MUST be 100% written in natural Korean. Category must start with "KR - ".
    3. 'en_content' MUST be 100% written in natural English. Category must start with "EN - ".
    4. Format Markdown headers and paragraphs with clear spacing (\\n\\n).
    
    {{
      "kr_title": "한글 제목",
      "kr_category": "KR - IT/테크",
      "kr_content": "---\\nlayout: post\\ntitle: \\"한글 제목\\"\\ncategory: \\"KR - IT/테크\\"\\nlang: kr\\n---\\n\\n# 한글 제목\\n\\n본문 내용...",
      
      "en_title": "English Title",
      "en_category": "EN - IT/Tech",
      "en_content": "---\\nlayout: post\\ntitle: \\"English Title\\"\\ncategory: \\"EN - IT/Tech\\"\\nlang: en\\n---\\n\\n# English Title\\n\\nBody content..."
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
        # 현재 연도(2026년) 기준 타임스탬프 적용
        date_str = datetime.datetime.now().strftime('%Y-%m-%d')
        timestamp = datetime.datetime.now().strftime('%H%M%S')
        
        os.makedirs("_posts", exist_ok=True)
        
        kr_filename = f"_posts/{date_str}-KR-{timestamp}.md"
        with open(kr_filename, "w", encoding="utf-8") as f:
            f.write(data["kr_content"])
            
        en_filename = f"_posts/{date_str}-EN-{timestamp}.md"
        with open(en_filename, "w", encoding="utf-8") as f:
            f.write(data["en_content"])
            
        print(f"포스트 생성 완료: {kr_filename}, {en_filename}")
        
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
