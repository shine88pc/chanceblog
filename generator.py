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
    """구글 뉴스 RSS를 통해 최근 24시간 이내의 실시간 뉴스 수집"""
    url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        recent_items = []
        now = datetime.now(timezone.utc)
        
        for item in root.findall('.//item'):
            title_el = item.find('title')
            desc_el = item.find('description')
            date_el = item.find('pubDate')
            
            title = title_el.text if title_el is not None else ""
            desc = desc_el.text if desc_el is not None else ""
            pub_date_str = date_el.text if date_el is not None else ""
            
            try:
                pub_date = parsedate_to_datetime(pub_date_str)
                # 최근 24시간 이내 데이터만 필터링
                if now - pub_date <= timedelta(hours=24):
                    recent_items.append(f"제목: {title}\n요약: {desc}")
            except Exception:
                # 날짜 파싱 예외 시 최신 뉴스로 간주하고 포함
                recent_items.append(f"제목: {title}\n요약: {desc}")
                
        return recent_items[:20] # 상위 20개 분석
    except Exception as e:
        print(f"뉴스 RSS 수집 중 오류 발생: {e}")
        return []

def handle_natural_language_issue():
    """모바일 이슈의 자연어 명령을 분석하여 코드, 분류, 글, 댓글 관리 통합 처리"""
    print(f"🔧 모바일 이슈 감지 - 제목: {issue_title}")
    
    files_data = {}
    for root, dirs, files in os.walk("."):
        if ".git" in root or "__pycache__" in root:
            continue
        for file in files:
            if file.endswith((".py", ".yml", ".md", ".json")):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        files_data[filepath] = f.read()
                except Exception:
                    pass

    prompt = f"""
    당신은 100% 자동화 블로그의 수석 관리 AI입니다.
    사용자가 스마트폰 깃허브 이슈를 통해 자연어로 요청을 보냈습니다.
    [코드 관리], [분류 관리], [글 관리], [댓글 관리] 중 적절한 조치를 취하고 파일 변경 내용을 결정하세요.

    [사용자 요청]:
    - 제목: {issue_title}
    - 본문: {issue_body}

    [현재 레포지토리 파일 요약]:
    {json.dumps({k: v[:600] for k, v in files_data.items()}, ensure_ascii=False)}

    [응답 규칙]:
    반드시 순수한 JSON 형식으로만 응답하세요. 마크다운 코드블록(```)이나 인사말을 절대 포함하지 마세요.
    구조:
    {{
      "target_file": "작업할 파일 경로 (예: _posts/... 또는 generator.py 또는 _config.yml)",
      "file_content": "해당 파일에 들어갈 최종 전체 내용",
      "delete_file": false
    }}
    """

    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=prompt
    )
    
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
            print(f"🗑️ 파일 삭제 완료: {target_file}")
        elif target_file and file_content:
            os.makedirs(os.path.dirname(target_file), exist_ok=True) if "/" in target_file else None
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(file_content)
            print(f"✅ 파일 반영 완료: {target_file}")
    except Exception as e:
        print(f"이슈 처리 중 에러 발생: {e}, 응답 원문: {result_text}")

def generate_hot_topic_post():
    """최근 24시간 뉴스 데이터를 분석하여 중복을 피하고 표절 없는 오리지널 핫토픽 글 생성"""
    history = load_history()
    news_pool = fetch_recent_news()
    
    news_text = "\n---\n".join(news_pool) if news_pool else "최근 특별한 뉴스 이슈 없음"

    prompt = f"""
    당신은 전문 트렌드 분석 블로거입니다. 
    아래 제공된 [최근 24시간 실시간 뉴스/블로그 데이터]를 분석하여 가장 주목받는 핫토픽 키워드 및 주제 1개를 선정하세요.

    [이미 작성된 이전 글 주제 목록 (중복 절대 금지)]:
    {json.dumps(history, ensure_ascii=False)}

    [최근 24시간 실시간 뉴스 데이터]:
    {news_text}

    [작성 가이드라인 및 제약사항]:
    1. 위 목록에 있는 이전 주제들과 **절대 중복되지 않는** 새로운 핫토픽을 고를 것.
    2. 뉴스의 원문을 그대로 복사(표절)하거나 단순 인용하지 말고, 독창적인 시각으로 재해석하여 작성할 것.
    3. 근거 없는 허위 사실이나 지어낸 내용(할루시네이션)은 철저히 배제하고 객관적인 사실 기반으로 작성할 것.
    4. 마크다운(Markdown) 형식으로 작성하고, 상단에 표준 템플릿 프론트매터(Frontmatter)를 포함할 것:
       ---
       layout: post
       title: "선정된 핫토픽 제목"
       date: "{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S +0900')}"
       categories: [핫토픽]
       ---
    5. 서론 - 핵심 분석(H2, H3 활용) - 결론 및 인사이트 구조로 가독성 있게 작성할 것.
    """
    
    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=prompt
    )
    
    post_content = response.text
    
    # 제목 추출 시도 (프론트매터 title에서 추출 혹은 기본값)
    topic_title = "최근 핫토픽 트렌드 분석"
    for line in post_content.splitlines():
        if line.startswith("title:"):
            topic_title = line.split(":", 1)[1].strip().strip('"\'')
            break

    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    safe_title = "".join(c if c.isalnum() else "_" for c in topic_title)[:15]
    file_name = f"_posts/{date_str}-{safe_title}.md"
    
    os.makedirs("_posts", exist_ok=True)
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(post_content)
    print(f"핫토픽 포스팅 생성 완료: {file_name}")
    
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
