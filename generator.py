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
                    recent_items.append(f"제목: {title}\n요약: {desc}")
            except Exception:
                recent_items.append(f"제목: {title}\n요약: {desc}")
        return recent_items[:20]
    except Exception as e:
        print(f"뉴스 수집 오류: {e}")
        return []

def handle_natural_language_issue():
    print(f"모바일 이슈 제어 접수 - 제목: {issue_title}")
    print(f"상세 본문:\n{issue_body}")
    
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
    당신은 Chance_Blog 수석 관리자 AI입니다. 사용자가 모바일 이슈 템플릿을 통해 보낸 요청을 분석하여 블로그 파일(코드, 포스트 등)을 생성, 수정 또는 삭제하세요.
    
    [이슈 제목]: {issue_title}
    [이슈 본문 (사용자 선택 및 지시사항)]: {issue_body}
    
    [현재 레포지토리 파일 현황]: {json.dumps({k: v[:500] for k, v in files_data.items()}, ensure_ascii=False)}
    
    [응답 규칙]: 반드시 아래 JSON 형식으로만 순수하게 응답하세요 (마크다운 백틱 ```json 등은 생략).
    {{
      "target_file": "생성 또는 수정할 파일 경로 (예: _posts/2026-06-07-title.md 또는 index.html 등)",
      "file_content": "파일에 들어갈 전체 내용",
      "delete_file": false
    }}
    """
    
    response = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    result_text = response.text.strip()
    
    if result_text.startswith("```"):
        lines = result_text.splitlines()
        if lines[0].startswith("```"): 
            lines = lines[1:]
        if lines and lines[-1].startswith("```"): 
            lines = lines[:-1]
        result_text = "\n".join(lines)
        
    try:
        action_data = json.loads(result_text)
        target_file = action_data.get("target_file")
        file_content = action_data.get("file_content")
        is_delete = action_data.get("delete_file", False)
        
        if is_delete and target_file and os.path.exists(target_file):
            os.remove(target_file)
            print(f"파일 삭제 완료: {target_file}")
        elif target_file and file_content:
            os.makedirs(os.path.dirname(target_file), exist_ok=True) if "/" in target_file else None
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(file_content)
            print(f"파일 생성/수정 완료: {target_file}")
    except Exception as e:
        print(f"이슈 처리 중 파싱 오류 발생: {e}")
        print(f"AI 응답 원본: {result_text}")

def generate_hot_topic_post():
    history = load_history()
    news_pool = fetch_recent_news()
    news_text = "\n---\n".join(news_pool) if news_pool else "최근 트렌드 뉴스 없음"

    prompt = f"""
    최근 24시간 실시간 뉴스를 분석하여 독창적인 블로그 글 1개를 작성하세요.
    [이전 주제 목록 (중복 금지)]: {json.dumps(history, ensure_ascii=False)}
    [뉴스 데이터]: {news_text}
    [조건]:
    1. 마크다운 형식 작성.
    2. 독창적이고 유익한 가독성 높은 분석 글.
    """
    response = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    post_content = response.text

    topic_title = "실시간 트렌드 핫토픽 분석"
    lines = post_content.splitlines()
    for line in lines:
        if line.startswith("# "):
            topic_title = line.replace("# ", "").strip()
            break

    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    safe_title = "".join(c if c.isalnum() else "_" for c in topic_title)[:15]
    file_name = f"_posts/{date_str}-{safe_title}.md"

    os.makedirs("_posts", exist_ok=True)
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(post_content)

    if topic_title not in history:
        history.append(topic_title)
        save_history(history)

def main():
    if event_name == "issues" and issue_title:
        handle_natural_language_issue()
    else:
        generate_hot_topic_post()

if __name__ == "__main__":
    main()
