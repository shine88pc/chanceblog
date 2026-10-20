"""Blogger 분기 생성기 (초안)

Chance_Blog 자동화의 연장선으로, 공통 주제에서 실용·실행형 글을 생성한다.
- 대상: Blogger (macat0722.blogspot.com)
- 프롬프트: .github/editorial/BLOGGER_PROMPT.md
- 현재 단계: 글 생성 + 로컬/로그 출력 (게시 API는 추후 연동)

환경변수
- GEMINI_API_KEY : 필수
- BLOGGER_TOPIC  : 지정 시 해당 주제 사용, 없으면 내장 목록에서 선택
- DRY_RUN=1      : API 호출 없이 스텁 응답
"""

import os
import re
import json
import random
import datetime
from pathlib import Path

# ============================================================
# 설정
# ============================================================
API_KEY = os.environ.get("GEMINI_API_KEY")
DRY_RUN = os.environ.get("DRY_RUN", "0").strip().lower() in {"1", "true", "yes"}
TOPIC_OVERRIDE = os.environ.get("BLOGGER_TOPIC", "").strip()

PROMPT_FILE = Path(__file__).resolve().parent / ".github/editorial/BLOGGER_PROMPT.md"
LOG_FILE = Path("blogger_history.json")

# Chance_Blog와 겹치지 않도록 실용 각도 주제 위주
DEFAULT_TOPICS = [
    "잠이 안 올 때 바로 해볼 수 있는 간단한 방법",
    "아침에 일어나기 힘든 사람을 위한 가벼운 루틴",
    "스트레스 받을 때 1분 만에 할 수 있는 호흡법",
    "집에서 쉽게 하는 스트레칭 루틴",
    "배달 음식 줄이는 간단한 습관",
    "하루 10분으로 시작하는 가벼운 운동",
    "자기 전 스마트폰 대신 할 수 있는 것",
    "피곤할 때 에너지 올리는 간단한 방법",
    "물 자주 마시는 습관 만드는 팁",
    "저녁에 소화 잘 되는 가벼운 식사 아이디어",
]

MODEL_CANDIDATES = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
]


# ============================================================
# 유틸
# ============================================================
def load_prompt_template():
    """BLOGGER_PROMPT.md에서 기본 프롬프트 블록을 추출한다."""
    if not PROMPT_FILE.exists():
        return _fallback_prompt()
    text = PROMPT_FILE.read_text(encoding="utf-8")
    m = re.search(r"```text\n(.*?)```", text, re.S)
    if m:
        return m.group(1).strip()
    return _fallback_prompt()


def _fallback_prompt():
    return """[대상: Blogger]

너는 건강·음식·생활 중심의 실용 블로그 작가다.
독자가 오늘 바로 실천할 수 있는 글을 쓴다.

주제: {topic}

작성 규칙:
1. 톤: 친근하고 실용적. 친구에게 말하듯 쉽게 쓴다.
2. 학술적·분석적·교양형 톤 금지.
3. 글 길이: 1,200~2,000자.
4. 구조: 도입(일상 고민) → 팁 3~5개 → 체크리스트 → 가벼운 마무리
5. 과장된 건강 주장 금지.
6. 제목은 자극적이지 않게.

출력 형식:
제목: (제목)
라벨: (쉼표로 구분)
내용:
(HTML 형식. <p>, <h3>, <ul>, <li> 사용)"""


def call_gemini(prompt: str) -> str:
    if DRY_RUN or not API_KEY:
        print("[DRY_RUN/STUB] Gemini 호출 생략")
        return _stub_response()

    from google import genai
    client = genai.Client(api_key=API_KEY)
    errors = []
    for model in MODEL_CANDIDATES:
        try:
            print(f"Gemini 호출: {model}")
            resp = client.models.generate_content(model=model, contents=prompt)
            text = getattr(resp, "text", None)
            if text and text.strip():
                return text.strip()
            errors.append(f"{model}: 빈 응답")
        except Exception as e:
            errors.append(f"{model}: {e}")
            print(f"실패: {model} - {e}")
    raise RuntimeError("모든 Gemini 모델 실패\n" + "\n".join(errors))


def _stub_response():
    return """제목: 잠이 안 올 때 바로 해볼 수 있는 3가지 방법
라벨: 수면, 건강, 생활습관
내용:
<p>요즘 유난히 잠이 안 오는 날이 많으신가요?</p>
<p>침대에 누웠는데 머릿속이 복잡하거나, 스마트폰을 보다가 시간이 훌쩍 지나버린 경험, 한 번쯤은 있으실 거예요.</p>
<h3>1. 스마트폰을 멀리하는 15분 룰</h3>
<p>잠들기 15분 전부터 스마트폰을 멀리 두세요. 파란빛이 멜라토닌을 방해할 수 있어요.</p>
<h3>2. 따뜻한 물로 손과 발 녹이기</h3>
<p>미지근한 물로 손발을 녹이면 몸이 이완되는 데 도움이 됩니다.</p>
<h3>3. 4-7-8 호흡</h3>
<p>4초 들이마시고, 7초 참고, 8초 내쉬기를 3~4회 반복해 보세요.</p>
<h3>오늘부터 해볼 수 있는 체크리스트</h3>
<ul>
<li>잠자기 15분 전 스마트폰 멀리 두기</li>
<li>미지근한 물로 손·발 적시기</li>
<li>4-7-8 호흡 3회</li>
</ul>
<p>처음부터 완벽하게 하려고 하지 말고, 오늘 하나만 시도해 보세요.</p>"""


def parse_response(raw: str) -> dict:
    title = ""
    labels = ""
    content = ""

    title_m = re.search(r"제목:\s*(.+)", raw)
    labels_m = re.search(r"라벨:\s*(.+)", raw)
    content_m = re.search(r"내용:\s*([\s\S]+)", raw)

    if title_m:
        title = title_m.group(1).strip()
    if labels_m:
        labels = labels_m.group(1).strip()
    if content_m:
        content = content_m.group(1).strip()
    else:
        content = raw

    return {
        "title": title or "제목 없음",
        "labels": labels or "건강,생활",
        "content": content,
        "raw": raw,
    }


def choose_topic() -> str:
    if TOPIC_OVERRIDE:
        return TOPIC_OVERRIDE
    return random.choice(DEFAULT_TOPICS)


def append_log(entry: dict):
    history = []
    if LOG_FILE.exists():
        try:
            history = json.loads(LOG_FILE.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except (OSError, json.JSONDecodeError):
            history = []
    history.append(entry)
    LOG_FILE.write_text(
        json.dumps(history[-100:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ============================================================
# 메인
# ============================================================
def generate_blogger_post(topic: str | None = None) -> dict:
    topic = topic or choose_topic()
    template = load_prompt_template()
    prompt = template.replace("{topic}", topic)

    print(f"[대상: Blogger] 주제: {topic}")
    raw = call_gemini(prompt)
    result = parse_response(raw)
    result["topic"] = topic
    result["generated_at"] = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=9))
    ).isoformat()

    append_log({
        "topic": topic,
        "title": result["title"],
        "labels": result["labels"],
        "generated_at": result["generated_at"],
        "status": "generated",
    })

    print("=== 생성 결과 ===")
    print(f"제목: {result['title']}")
    print(f"라벨: {result['labels']}")
    print(f"내용 길이: {len(result['content'])}자")
    return result


def main():
    result = generate_blogger_post()
    # 추후: Blogger API 게시 로직 추가
    # post_to_blogger(result["title"], result["content"], result["labels"])
    print("완료. (게시는 아직 미연동)")


if __name__ == "__main__":
    main()
