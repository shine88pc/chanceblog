import os
import json
import datetime
from google import genai

# 1. 환경 변수에서 Gemini API 키 가져오기
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")

# 최신 구글 공식 클라이언트 초기화
client = genai.Client(api_key=API_KEY)

# 2. 주제 풀 (Pool) 설정
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
    return TOPIC_POOL[len(history) % len(TOPIC_POOL)]

def generate_blog_post(topic):
    """서버 과부하(503) 시 대체 모델을 순서대로 시도하는 안전 장치 적용"""
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
    
    # 시도할 모델 리스트 (앞 모델이 503 에러 등으로 막히면 다음 모델로 자동 전환)
    models_to_try = ['gemini-3.8-flash', 'gemini-2.5-flash', 'gemini-1.5-flash']
    
    last_error = None
    for model_name in models_to_try:
        try:
            print(f"시도 중인 AI 모델: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            if response and response.text:
                return response.text
        except Exception as e:
            print(f"모델 {model_name} 실패: {e}")
            last_error = e
            continue
            
    raise Exception(f"모든 Gemini 모델 호출에 실패했습니다. 마지막 에러: {last_error}")

def main():
    history = load_history()
    topic = select_topic(history)
    print(f"선정된 주제: {topic}")
    
    # 블로그 글 생성
    post_content = generate_blog_post(topic)
    
    # 파일명 생성
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    file_name = f"posts/{date_str}-{abs(hash(topic)) % 10000}.md"
    
    os.makedirs("posts", exist_ok=True)
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(post_content)
    print(f"글 작성 완료 및 저장: {file_name}")
    
    # 히스토리 업데이트
    history.append(topic)
    save_history(history)

if __name__ == "__main__":
    main()
