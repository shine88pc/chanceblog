import os
import json
import datetime
import requests

# 1. 환경 변수에서 Gemini API 키 가져오기
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")

# 2. 주제 풀 (Pool) 설정 (원하는 카테고리나 키워드로 수정 가능)
TOPIC_POOL = [
    "초보자를 위한 파이썬 자동화 팁 3가지",
    "직장인 업무 효율을 2배 높여주는 AI 활용법",
    "개발 지식 없이 시작하는 1인 블로그 자동화",
    "GitHub Actions를 활용한 무료 업무 자동화 스케줄링",
    "Gemini API 무료 요금제로 실용적인 앱 만드는 방법"
]

def load_history():
    """이미 작성된 주제 기록 불러오기"""
    if os.path.exists("history.json"):
        with open("history.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    """작성된 주제 기록 저장하기"""
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def select_topic(history):
    """아직 다루지 않은 새로운 주제 1개 선정"""
    for topic in TOPIC_POOL:
        if topic not in history:
            return topic
    # 모든 주제를 다 썼다면 순환
    return TOPIC_POOL[len(history) % len(TOPIC_POOL)]

def generate_blog_post(topic):
    """Gemini API를 이용해 마크다운 형식의 블로그 글 생성"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
    
    prompt = f"""
    당신은 전문 블로거입니다. 다음 주제에 대해 독자에게 유익하고 가독성이 좋은 블로그 포스팅을 작성해 주세요.
    
    [주제]: {topic}
    
    [요청 조건]:
    1. 마크다운(Markdown) 형식으로 작성할 것.
    2. 상단에 프론트매터(Frontmatter)를 포함할 것:
       ---
       title: "글 제목"
       date: "{datetime.datetime.now().strftime('%Y-%m-%d')}"
       tags: ["태그1", "태그2"]
       ---
    3. 서론 - 본문(H2, H3 활용한 3가지 핵심 내용) - 결론 구조로 작성할 것.
    4. 친근하고 전문적인 어조를 사용할 것.
    """
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        result = response.json()
        try:
            return result['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            raise Exception("Gemini 응답 구조가 올바르지 않습니다.")
    else:
        raise Exception(f"API 호출 실패: {response.status_code} - {response.text}")

def main():
    history = load_history()
    topic = select_topic(history)
    print(f"선정된 주제: {topic}")
    
    # 블로그 글 생성
    post_content = generate_blog_post(topic)
    
    # 파일명 생성 (날짜 + 주제 키워드 기반)
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    file_name = f"posts/{date_str}-{hash(topic) % 10000}.md"
    
    os.makedirs("posts", exist_ok=True)
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(post_content)
    print(f"글 작성 완료 및 저장: {file_name}")
    
    # 히스토리 업데이트
    history.append(topic)
    save_history(history)

if __name__ == "__main__":
    main()
