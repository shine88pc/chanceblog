import os
import json
import datetime
import urllib.request
import urllib.parse
import re
import xml.etree.ElementTree as ET
from datetime import timezone, timedelta
from pathlib import Path
from google import genai

# ============================================================
# 환경 설정
# ============================================================
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY 환경 변수가 없습니다. "
        "GitHub 저장소 Settings > Secrets and variables > Actions 에 등록해주세요."
    )

KST = timezone(timedelta(hours=9))
POSTS_DIR = Path("_posts")
HISTORY_FILE = Path("history.json")

# ============================================================
# 주제별 관련 Unsplash 고화질 이미지 풀
# ============================================================
TOPIC_IMAGE_POOLS = {
    "firefighter": [
        "https://images.unsplash.com/photo-1582139329536-e7284fece509?auto=format&fit=crop&w=1000&q=80",  # 소방관 현장 진압
        "https://images.unsplash.com/photo-1543083477-4f785aeafaa9?auto=format&fit=crop&w=1000&q=80",  # 소방 장비 및 소방차
        "https://images.unsplash.com/photo-1527786356703-4b100091cd2c?auto=format&fit=crop&w=1000&q=80",  # 소방관 헬멧과 장구
    ],
    "rendering_ai": [
        "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1000&q=80",  # 3D 레이트레이싱 그래픽 아트
        "https://images.unsplash.com/photo-1633493106185-3ac82312d8a5?auto=format&fit=crop&w=1000&q=80",  # 컴퓨팅 연산 비주얼
        "https://images.unsplash.com/photo-1677442136019-21780efad99a?auto=format&fit=crop&w=1000&q=80",  # 차세대 AI 신경망 그래픽
    ],
    "hardware": [
        "https://images.unsplash.com/photo-1591488320449-011701bb6704?auto=format&fit=crop&w=1000&q=80",  # GPU 그래픽카드 기판
        "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1000&q=80",  # 반도체 프로세서
        "https://images.unsplash.com/photo-1555680202-c86f0e12f086?auto=format&fit=crop&w=1000&q=80",  # 마이크로칩 회로도
    ],
    "space": [
        "https://images.unsplash.com/photo-1614728894747-a83421e2b9c9?auto=format&fit=crop&w=1000&q=80",  # 화성 및 행성 탐사
        "https://images.unsplash.com/photo-1541185933-ef5d8ed016c2?auto=format&fit=crop&w=1000&q=80",  # 우주 로켓 궤도 발사
        "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1000&q=80",  # 위성 궤도 통신망
    ],
    "security": [
        "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1000&q=80",  # 사이버 보안 및 코드
        "https://images.unsplash.com/photo-1563986768609-322da13575f3?auto=format&fit=crop&w=1000&q=80",  # 보안 네트워크
    ],
    "policy_society": [
        "https://images.unsplash.com/photo-1450133064473-71024230f91b?auto=format&fit=crop&w=1000&q=80",  # 정부/정책/재정 문서
        "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1000&q=80",  # 공공 인프라 건물
    ],
    "default": [
        "https://images.unsplash.com/photo-1488590528505-98d2b5aba04b?auto=format&fit=crop&w=1000&q=80",  # 테크놀로지 전반
        "https://images.unsplash.com/photo-1504639725590-34d0984388bd?auto=format&fit=crop&w=1000&q=80",  # 개발 및 프로그래밍
    ]
}

def select_relevant_image(text: str, used_images: set = None) -> str:
    """글의 제목 및 본문 키워드를 분석하여 내용과 가장 부합하는 고유 이미지를 반환합니다."""
    lower = text.lower()
    used_images = used_images or set()

    if any(k in lower for k in ["소방관", "순직", "화재", "firefighter", "first responder", "소방공무원"]):
        topic = "firefighter"
    elif any(k in lower for k in ["레이 재구성", "레이트레이싱", "ai 렌더링", "ray reconstruction", "dlss", "렌더링"]):
        topic = "rendering_ai"
    elif any(k in lower for k in ["vbios", "오버클럭", "그래픽카드", "rtx", "엔비디아", "라데온", "반도체", "하드웨어", "gpu"]):
        topic = "hardware"
    elif any(k in lower for k in ["starlink", "starshield", "jaxa", "phobos", "우주", "로봇", "위성", "행성", "space", "robotics"]):
        topic = "space"
    elif any(k in lower for k in ["해킹", "보안", "취약점", "security", "firmware"]):
        topic = "security"
    elif any(k in lower for k in ["정책", "재정", "국가직", "예산", "지자체", "법안", "society", "policy"]):
        topic = "policy_society"
    else:
        topic = "default"

    pool = TOPIC_IMAGE_POOLS.get(topic, TOPIC_IMAGE_POOLS["default"])
    for img in pool:
        if img not in used_images:
            return img
    return pool[0]

# ============================================================
# 기존 포스트 이미지 개선 및 중복 해결
# ============================================================
def fix_existing_posts():
    """기존 등록된 게시글 중 소방관 글 이미지 보완 및 중복 이미지를 내용에 맞게 교체합니다."""
    if not POSTS_DIR.exists():
        return

    posts = list(POSTS_DIR.rglob("*.md"))
    used_urls = set()

    for p in posts:
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue

        modified = False

        # 1. 소방관 관련 포스트 (이미지 누락 보완 및 소방관 관련 이미지 적용)
        if "소방관" in content or "Firefighter" in content:
            firefighter_img = TOPIC_IMAGE_POOLS["firefighter"][0]
            if "image:" not in content:
                content = re.sub(r"^---\s*\n", f"---\nimage: \"{firefighter_img}\"\n", content, count=1)
                content = re.sub(r"(---\s*\n\s*\n?)(# )", f"\1![Thumbnail]({firefighter_img})\n\n\2", content, count=1)
                modified = True
            elif any(fb in content for fb in ["photo-1591488320449-011701bb6704", "photo-1541185933-ef5d8ed016c2"]):
                content = re.sub(r"https://images\.unsplash\.com/photo-[^\s\"\)]+", firefighter_img, content)
                modified = True
            used_urls.add(firefighter_img)

        # 2. 레이 재구성 / AI 렌더링 글에 들어간 하드웨어 중복 이미지 교체
        elif "레이 재구성" in content or "Ray Reconstruction" in content or "AI 렌더링" in content:
            rendering_img = TOPIC_IMAGE_POOLS["rendering_ai"][0]
            if "photo-1591488320449-011701bb6704" in content:
                content = content.replace("https://images.unsplash.com/photo-1591488320449-011701bb6704?auto=format&fit=crop&w=1000&q=80", rendering_img)
                modified = True
            used_urls.add(rendering_img)

        if modified:
            p.write_text(content, encoding="utf-8")
            print(f"[Image Fixed] Updated post: {p}")

# ============================================================
# 뉴스 수집 및 히스토리 관리
# ============================================================
def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(history: list):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def fetch_rss_items() -> list:
    urls = [
        "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/search?q=AI+반도체+하드웨어&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en",
    ]
    items = []
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                root = ET.fromstring(resp.read())
                for item in root.findall(".//item")[:5]:
                    title = item.findtext("title") or ""
                    link = item.findtext("link") or ""
                    if title:
                        items.append({"title": title, "link": link})
        except Exception as e:
            print(f"RSS fetch failed ({u}): {e}")
    return items

# ============================================================
# 포스팅 생성
# ============================================================
def generate_post():
    client = genai.Client(api_key=API_KEY)
    history = load_history()
    feed_items = fetch_rss_items()

    # 이미 작성된 토픽 제외
    candidates = [it for it in feed_items if not any(h in it["title"] for h in history)]
    target = candidates[0] if candidates else (feed_items[0] if feed_items else {"title": "AI와 차세대 컴퓨팅 혁신"})

    now = datetime.datetime.now(KST)
    timestamp_str = now.strftime("%Y-%m-%d-%H%M%S")
    date_str = now.strftime("%Y-%m-%d")

    # 기존에 사용된 이미지 파악
    existing_images = set()
    for p in POSTS_DIR.rglob("*.md"):
        try:
            m = re.findall(r"image:\s*\"(https://[^\"]+)\"", p.read_text(encoding="utf-8"))
            existing_images.update(m)
        except Exception:
            pass

    rel_img = select_relevant_image(target["title"], used_images=existing_images)

    prompt = f"""
당신은 수준 높은 기술 블로그 'Chance Blog'의 수석 테크 에디터입니다.
주제: "{target['title']}"

요구사항:
1. 한국어 심층 분석 포스트(KR)를 작성하세요.
2. 기술적 깊이와 사회적/산업적 맥락을 포괄하는 흥미로운 인사이트를 담으세요.
3. 응답은 오직 Jekyll 마크다운 본문만 출력하세요 (코드블록 ```markdown 사용 금지).
4. 카테고리는 KR - 테크 이야기, KR - 하드웨어 인사이트, KR - 사회/정책 중 가장 적합한 것을 선택하세요.

Frontmatter 형식:
---
layout: post
title: "선정된 매력적인 제목"
category: "선정된 카테고리"
tags: ['태그1', '태그2', '태그3']
lang: kr
image: "{rel_img}"
---

![Thumbnail]({rel_img})

# 본문 시작...
"""

    try:
        res = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        text = res.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n", "", text)
            text = re.sub(r"\n```$", "", text)

        cat_match = re.search(r'category:\s*"?([^"\n]+)"?', text)
        category = cat_match.group(1).strip() if cat_match else "KR - 테크 이야기"
        
        save_dir = POSTS_DIR / category
        save_dir.mkdir(parents=True, exist_ok=True)

        file_path = save_dir / f"{date_str}-KR-{timestamp_str[-6:]}.md"
        file_path.write_text(text, encoding="utf-8")
        print(f"[Generated] Successfully created {file_path}")

        history.append(target["title"])
        save_history(history[-50:])
    except Exception as e:
        print(f"Post generation failed: {e}")

if __name__ == "__main__":
    # 1. 기존 게시글들의 소방관 관련 이미지 개선 및 중복 이미지 교체
    fix_existing_posts()
    # 2. 신규 포스트 생성 (필요 시)
    if os.environ.get("RUN_GENERATION") == "true":
        generate_post()
