import os
import json
import datetime
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import requests
import re
import random
from email.utils import parsedate_to_datetime
from datetime import timezone, timedelta
from google import genai
from google.genai import types
from pathlib import Path

# 환경 변수
API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "shine88pc/chanceblog")
EVENT_NAME = os.environ.get("EVENT_NAME", "").lower()
ISSUE_TITLE = os.environ.get("ISSUE_TITLE", "")
ISSUE_BODY = os.environ.get("ISSUE_BODY", "")
ISSUE_NUMBER = os.environ.get("ISSUE_NUMBER", "")

HISTORY_FILE = Path("history.json")
POSTS_DIR = Path("_posts")

# Fallback용 고품질 테크/과학/사회 Unsplash 고유 이미지 풀
FALLBACK_PHOTO_IDS = [
    "1518770660439-4636190af475",
    "1526374965328-7f61d4dc18c5",
    "1531297484001-80022131f5a1",
    "1550751827-4bd374c3f58b",
    "1519389950473-47ba0277781c",
    "1451187580459-43490279c0fa",
    "1516321318423-f06f85e504b3",
    "1488590528505-98d2b5aba04b",
    "1504384308090-c894fdcc538d",
    "1581091226825-a6a2a5aee158",
    "1535378917042-10a22c95931a",
    "1618005182384-a83a8bd57fbe",
    "1620712943543-bcc4688e7485",
    "1508739773434-c26b3d09e071",
    "1527788263495-3518a5c13425",
    "1541185933-ef5d8ed016c2",
    "1614728894747-a83421e2b9c9",
    "1563770660941-20978e870e26",
    "1558494949-ef010cbdcc31",
    "1517433670267-08bbd4be890f",
    "1515378791036-0648a3ef77b2",
    "1461749280684-dccba630e2f6",
    "1534972195531-a756b1126f24",
    "1581092160607-ee22621dd758",
    "1507413245164-6160d8298b31",
    "1518773553398-650c184e0bb3",
    "1531403009284-440f080d1e12",
    "1522071820081-009f0129c71c",
    "1573164713988-8665fc963095",
    "1573164574572-cb89e39749b4",
    "1550745165-9bc0b252726f",
    "1511512578047-dfb367046420",
    "1563986768-605b11004f84",
    "1551288049-bebda4e38f71",
    "1551836022-d5d88e9218df",
    "1498050108023-c5249f4df085",
    "1565106430482-8f6e74349ca1",
    "1486312338219-ce68d2c6f44d",
    "1531482615713-2afd69097998",
    "1579567761406-4684ee0c75b6",
    "1504639725590-34d0984388bd",
    "1517694712202-14dd9538aa97",
    "1531497865144-0464ef8fb9a9",
    "1516116211227-bbc13c74480c",
    "1525547719571-a2d4ac8945e2"
]

def extract_unsplash_id(url: str) -> str:
    """URL에서 Unsplash 고유 포토 ID 또는 핵심 식별자를 추출합니다."""
    match = re.search(r'photo-([a-zA-Z0-9_\-]+)', url)
    if match:
        return match.group(1)
    clean = url.split('?')[0].rstrip('/')
    return clean.split('/')[-1]

def get_used_images() -> set:
    """기존 포스트 파일 전체를 스캔하여 이미 사용된 이미지 URL 및 식별자를 수집합니다."""
    used = set()
    if POSTS_DIR.exists():
        for file in POSTS_DIR.rglob("*.md"):
            try:
                content = file.read_text(encoding="utf-8")
                # Front Matter 내 image 태그 추출
                fm_matches = re.findall(r'image:\s*["\']?(https?://[^\s"\']+)["\']?', content)
                for img in fm_matches:
                    used.add(img.strip())
                    used.add(extract_unsplash_id(img))
                # 본문 내 마크다운 이미지 문법 추출
                md_matches = re.findall(r'!\[.*?\]\((https?://[^\s\)]+)\)', content)
                for img in md_matches:
                    used.add(img.strip())
                    used.add(extract_unsplash_id(img))
            except Exception as e:
                print(f"[Warning] 포스트 스캔 오류 ({file}): {e}")
    return used

def fetch_unique_image(query: str, used_images: set) -> str:
    """
    한 번도 사용된 적 없는 고유한 이미지를 검색 및 반환합니다.
    Unsplash Search API -> Fallback 고유 풀 -> 타임스탬프 시드 순으로 보증합니다.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    clean_query = re.sub(r'[^a-zA-Z0-9가-힣\s]', '', query).strip()
    search_candidates = [clean_query, "technology", "artificial intelligence", "future computer", "science data"]
    
    # 1. Unsplash 검색 결과 중 미사용 이미지 탐색
    for q in search_candidates:
        if not q:
            continue
        try:
            encoded_q = urllib.parse.quote(q)
            search_url = f"https://unsplash.com/napi/search/photos?query={encoded_q}&per_page=25&page=1"
            req = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                results = data.get("results", [])
                for item in results:
                    raw_id = item.get("id")
                    img_url = item.get("urls", {}).get("raw", "")
                    if not img_url:
                        continue
                    photo_id = extract_unsplash_id(img_url) or raw_id
                    base_url = f"{img_url.split('?')[0]}?auto=format&fit=crop&w=1000&q=80"
                    if photo_id not in used_images and base_url not in used_images:
                        used_images.add(photo_id)
                        used_images.add(base_url)
                        return base_url
        except Exception as e:
            print(f"[Info] Unsplash 쿼리 '{q}' 검색 스킵: {e}")
            
    # 2. Fallback 목록 중 사용되지 않은 고유 이미지 선택
    shuffled_fallbacks = FALLBACK_PHOTO_IDS.copy()
    random.shuffle(shuffled_fallbacks)
    for pid in shuffled_fallbacks:
        if pid not in used_images:
            candidate_url = f"https://images.unsplash.com/photo-{pid}?auto=format&fit=crop&w=1000&q=80"
            if candidate_url not in used_images:
                used_images.add(pid)
                used_images.add(candidate_url)
                return candidate_url
                
    # 3. 모든 풀이 소진된 경우 고유 시드를 적용하여 캐싱/중복 회피
    sig = int(datetime.datetime.now(timezone.utc).timestamp())
    selected_pid = random.choice(FALLBACK_PHOTO_IDS)
    unique_url = f"https://images.unsplash.com/photo-{selected_pid}?auto=format&fit=crop&w=1000&q=80&sig={sig}"
    used_images.add(unique_url)
    return unique_url

def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_history(history: list):
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch_rss_articles():
    """글 생성을 위한 최신 뉴스 피드를 조회합니다."""
    rss_urls = [
        "https://news.google.com/rss/search?q=AI+인공지능+IT+반도체+기술&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.hada.io/rss/news",
        "https://news.google.com/rss/search?q=Artificial+Intelligence+Tech+Science&hl=en-US&gl=US&ceid=US:en"
    ]
    articles = []
    for url in rss_urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as response:
                root = ET.fromstring(response.read())
                for item in root.findall(".//item"):
                    title = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    pub_date = item.findtext("pubDate", "")
                    desc = item.findtext("description", "").strip()
                    if title:
                        articles.append({"title": title, "link": link, "pubDate": pub_date, "desc": desc})
        except Exception as e:
            print(f"[Warning] RSS 피드 파싱 실패 ({url}): {e}")
    return articles

def main():
    # 소스코드 수정 또는 컨트롤 관련 이슈 실행 시 자동 포스팅 방지
    if EVENT_NAME == "issues":
        combined_text = (ISSUE_TITLE + " " + ISSUE_BODY).lower()
        if "[control]" in combined_text or "설정 수정" in combined_text or "소스코드" in combined_text:
            print("[Notice] 블로그 제어/유지보수 이슈로 감지되어 자동 포스팅 생성을 종료합니다.")
            return

    if not API_KEY:
        print("[Error] GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        return

    history = load_history()
    used_images = get_used_images()
    print(f"[Info] 현재 등록된 고유 이미지 식별자 수: {len(used_images)}")

    articles = fetch_rss_articles()
    candidate = None
    for art in articles:
        # 제목 유사도 및 중복 점검
        if not any(art["title"] in h or h in art["title"] for h in history):
            candidate = art
            break

    if not candidate:
        print("[Notice] 처리할 새로운 뉴스 항목이 없습니다.")
        return

    title_query = candidate["title"]
    print(f"[Info] 선택된 주제: {title_query}")

    # 중복되지 않는 단 하나의 고유 이미지 선정
    assigned_image = fetch_unique_image(title_query, used_images)
    print(f"[Success] 선정된 고유 이미지 URL: {assigned_image}")

    # Gemini를 사용한 에세이 및 포스트 생성
    client = genai.Client(api_key=API_KEY)
    is_korean = bool(re.search(r'[가-힣]', title_query))
    lang_code = "kr" if is_korean else "en"
    
    prompt = f"""
당신은 IT/기술 전문 블로그 'Chance_Blog'의 수석 에디터입니다.
다음 주제를 기반으로 통찰력 넘치는 분석형 블로그 에세이를 작성하세요.

주제: {title_query}
참고 요약: {candidate.get('desc', '')}
언어: {'한국어' if is_korean else 'English'}
선정된 대표 이미지: {assigned_image}

[작성 요구사항]
1. Jekyll 호환 마크다운 포맷으로 작성하세요.
2. 반드시 맨 위에 다음과 같은 Front Matter를 포함하세요:
---
layout: post
title: "매력적이고 전문적인 포스트 제목"
category: "{'KR - 하드웨어 인사이트' if is_korean else 'EN - Tech Insights'}"
tags: [관련태그 4~5개]
lang: {lang_code}
image: "{assigned_image}"
---

![Thumbnail]({assigned_image})

# 제목

본문 (소제목, 깊이 있는 시각, 구체적 예시, 결론으로 이어지는 최소 1200자 이상의 완성도 높은 마크다운 본문)
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        post_content = response.text.strip()
        # 코드 블록 감싸기 제거 (필요 시)
        if post_content.startswith("```markdown"):
            post_content = post_content[len("```markdown"):].strip()
        if post_content.startswith("```"):
            post_content = post_content[3:].strip()
        if post_content.endswith("```"):
            post_content = post_content[:-3].strip()

        now = datetime.datetime.now(timezone(timedelta(hours=9)))
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H%M%S")
        prefix = "KR" if is_korean else "EN"
        filename = f"{date_str}-{prefix}-{time_str}.md"
        
        # 카테고리 디렉토리 또는 _posts에 저장
        POSTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = POSTS_DIR / filename
        output_path.write_text(post_content, encoding="utf-8")
        
        history.append(title_query)
        save_history(history)
        print(f"[Success] 신규 포스트가 성공적으로 발행되었습니다: {output_path}")

    except Exception as e:
        print(f"[Error] 포스트 생성 실패: {e}")

if __name__ == "__main__":
    main()
