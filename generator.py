import os
import json
import datetime
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")

client = genai.Client(api_key=API_KEY)

# GitHub Actions 환경 변수에서 이슈 정보 가져오기
event_name = os.environ.get("EVENT_NAME")
issue_title = os.environ.get("ISSUE_TITLE")

# 기본 주제 풀 (스케줄 실행용)
TOPIC_POOL = [
    {"topic": "초보자를 위한 파이썬 자동화 팁 3가지", "category": "파이썬자동화"},
    {"topic": "직장인 업무 효율을 2배 높여주는 AI 활용법", "category": "AI활용법"},
    {"topic": "개발 지식 없이 시작하는 1인 블로그 자동화", "category": "1인블로그"}
]

def load_history():
    if os.path.exists("history.json"):
        with open("history.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def select_item(history):
    # 💡 핵심: 모바일에서 이슈를 통해 요청한 경우, 이슈 제목을 주제로 즉시 사용!
    if event_name == "issues" and issue_title:
        print(f"모바일 이슈 요청 감지! 요청 주제: {issue_title}")
        return {"topic": issue_title, "category": "요청사항"}
    
    # 평소 스케줄 실행인 경우 기존 풀에서 순서대로 선택
    for item in TOPIC_POOL:
        if item["topic"] not in history:
            return item
    return TOPIC_POOL[len(history) % len(TOPIC_POOL)]

def generate_blog_post(topic, category):
    prompt = f"""
    당신은 전문 블로거입니다. 다음 주제에 대해 독자에게 유익하고 가독성이 좋은 블로그 포스팅을 작성해 주세요.
    
    [주제]: {topic}
    
    [요청 조건]:
    1. 마크다운(Markdown) 형식으로 작성할 것.
    2. 상단에 프론트매터(Frontmatter)를 정확히 포함할 것:
       ---
       layout: post
       title: "{topic}"
       date: "{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S +0900')}"
       categories: [{category}]
       ---
    3. 서론 - 본문(H2, H3 활용한 3가지 핵심 내용) - 결론 구조로 작성할 것.
    4. 친근하고 전문적인 어조를 사용할 것.
    """
    
    models_to_try = ['gemini-3.8-flash', 'gemini-2.5-flash', 'gemini-1.5-flash']
    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            if response and response.text:
                return response.text
        except Exception as e:
            last_error = e
            continue
    raise Exception(f"모든 모델 호출 실패: {last_error}")

def main():
    history = load_history()
    item = select_item(history)
    topic = item["topic"]
    category = item["category"]
    print(f"선정된 주제: {topic} (카테고리: {category})")
    
    post_content = generate_blog_post(topic, category)
    
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    safe_title = "".join(c if c.isalnum() else "_" for c in topic)[:15]
    file_name = f"_posts/{date_str}-{safe_title}.md"
    
    os.makedirs("_posts", exist_ok=True)
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(post_content)
    print(f"글 작성 완료 및 저장: {file_name}")
    
    if topic not in history:
        history.append(topic)
        save_history(history)

if __name__ == "__main__":
    main()
