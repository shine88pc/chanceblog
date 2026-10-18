import os
import json
import datetime
import urllib.request
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
        "GitHub 저장소 Settings > Secrets and variables > Actions에서 확인하세요."
    )

client = genai.Client(api_key=API_KEY)

EVENT_NAME = os.environ.get("EVENT_NAME", "").strip().lower()
ISSUE_TITLE = os.environ.get("ISSUE_TITLE", "")
ISSUE_BODY = os.environ.get("ISSUE_BODY", "")

KST = timezone(timedelta(hours=9))
POSTS_DIR = Path("_posts")
HISTORY_FILE = Path("history.json")

# 현재 사용 가능한 모델부터 순서대로 시도합니다.
# 모델 접근 권한/쿼터는 Gemini API 프로젝트 설정에 따라 달라질 수 있습니다.
MODEL_CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
]

IMAGE_POOL = [
    "https://images.unsplash.com/photo-1591488320449-011701bb6704?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1550745165-9bc0b252726f?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1555680202-c86f0e12f086?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1563770660941-20978e870e26?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1677442136019-21780ecad985?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1507146426996-ef05306b995a?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1531482615713-2afd69097998?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1541185933-ef5d8ed016c2?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1614728894747-a83421e2b9c9?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1484589065579-248aad0d8b13?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1517976487502-5f654b0c2794?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1563986768609-322da13575f3?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1510511459019-5dda7724fd87?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1544197150-b99a580bb7a8?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1519501025264-65ba15a82390?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1473968512647-3e447244af8f?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1508739773434-c26b3d09e071?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1535378917042-10a22c95931a?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1504639725590-34d0984388bd?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1518773553398-650c184e0bb3?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1531297484001-80022131f5a1?auto=format&fit=crop&w=1000&q=80",
    "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1000&q=80",
]


# ============================================================
# 공통 유틸리티
# ============================================================
def extract_photo_id(url):
    match = re.search(r"photo-([a-zA-Z0-9_-]+)", url or "")
    return match.group(1) if match else (url or "")


def read_history():
    if not HISTORY_FILE.exists():
        return []
    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError) as exc:
        print(f"history.json 읽기 실패. 빈 기록으로 진행합니다: {exc}")
        return []


def write_history(history):
    # 중복을 줄이고 최근 100개만 보관합니다.
    history = history[-100:]
    temp_path = HISTORY_FILE.with_suffix(".json.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)
    temp_path.replace(HISTORY_FILE)


def get_all_used_images():
    used = set()
    if not POSTS_DIR.exists():
        return used

    for path in POSTS_DIR.rglob("*.md"):
        try:
            content = path.read_text(encoding="utf-8")
            urls = re.findall(
                r'https://images\.unsplash\.com/[^\s"\'\)]+',
                content
            )
            used.update(extract_photo_id(url) for url in urls)
        except OSError as exc:
            print(f"이미지 사용 기록 확인 실패 ({path}): {exc}")
    return used


def select_unique_image(used_ids):
    for image_url in IMAGE_POOL:
        photo_id = extract_photo_id(image_url)
        if photo_id and photo_id not in used_ids:
            used_ids.add(photo_id)
            return image_url

    # 이미지 풀이 모두 소진된 경우에도 URL의 이미지 ID는 명시적으로 알립니다.
    # sig 값은 이미지 자체를 바꾸지 않으므로 중복 방지 수단으로 간주하지 않습니다.
    raise RuntimeError(
        "IMAGE_POOL의 고유 이미지가 모두 사용되었습니다. "
        "IMAGE_POOL에 새 Unsplash 사진 URL을 추가하세요."
    )


def fix_existing_duplicate_images():
    """기존 게시물의 대표 이미지 중복을 찾아 가능한 경우 새 이미지로 교체."""
    if not POSTS_DIR.exists():
        return

    seen_ids = set()
    for path in sorted(POSTS_DIR.rglob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
            urls = re.findall(
                r'https://images\.unsplash\.com/[^\s"\'\)]+',
                content
            )
            if not urls:
                continue

            current_url = urls[0]
            current_id = extract_photo_id(current_url)

            if current_id in seen_ids:
                replacement = select_unique_image(seen_ids)
                updated = content.replace(current_url, replacement)
                path.write_text(updated, encoding="utf-8")
                print(f"중복 이미지 교체: {path} -> {replacement}")
            else:
                seen_ids.add(current_id)
        except (OSError, RuntimeError) as exc:
            # 중복 이미지 정리 실패가 새 글 생성까지 무조건 중단시키지 않도록 기록합니다.
            print(f"기존 이미지 정리 실패 ({path}): {exc}")


def extract_json_object(raw_text):
    """모델 응답에 코드 펜스나 설명이 섞여도 JSON 객체를 찾아 파싱."""
    if not raw_text or not raw_text.strip():
        raise ValueError("Gemini 응답이 비어 있습니다.")

    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 중괄호를 단순 정규식으로 자르면 본문 속 중괄호에 취약하므로
    # 문자열/이스케이프 상태를 추적하며 첫 번째 완전한 JSON 객체를 찾습니다.
    start = text.find("{")
    if start < 0:
        raise ValueError(f"응답에서 JSON 객체를 찾을 수 없습니다: {text[:300]}")

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:index + 1]
                parsed = json.loads(candidate)
                if not isinstance(parsed, dict):
                    raise ValueError("응답 JSON의 최상위 값이 객체가 아닙니다.")
                return parsed

    raise ValueError(f"완전한 JSON 객체를 찾을 수 없습니다: {text[:300]}")


def call_gemini_with_fallback(prompt):
    """현재 모델부터 순서대로 호출하고, 실패 시 원인을 기록해 다음 모델을 시도."""
    errors = []

    for model_name in MODEL_CANDIDATES:
        try:
            print(f"Gemini 모델 호출 시도: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )

            response_text = getattr(response, "text", None)
            if response_text and response_text.strip():
                print(f"Gemini 모델 호출 성공: {model_name}")
                return response

            errors.append(f"{model_name}: 응답 텍스트 없음")
            print(f"{model_name}: 응답 텍스트 없음")

        except Exception as exc:
            message = str(exc)
            errors.append(f"{model_name}: {message}")
            print(f"Gemini 모델 호출 실패: {model_name} — {message}")

    raise RuntimeError(
        "모든 Gemini 모델 호출에 실패했습니다.\n" + "\n".join(errors)
    )


def safe_repo_path(raw_path):
    """Issue 요청으로 저장소 밖 파일을 수정하지 못하도록 경로를 제한."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("target_file 값이 비어 있습니다.")

    candidate = Path(raw_path.strip())
    if candidate.is_absolute():
        raise ValueError("절대 경로는 허용되지 않습니다.")

    resolved_root = Path(".").resolve()
    resolved_target = (resolved_root / candidate).resolve()

    try:
        resolved_target.relative_to(resolved_root)
    except ValueError:
        raise ValueError("저장소 외부 경로는 허용되지 않습니다.")

    forbidden_parts = {".git", ".github", "node_modules", "_site", ".jekyll-cache"}
    if forbidden_parts.intersection(candidate.parts):
        raise ValueError("보호된 디렉터리는 Issue를 통해 수정할 수 없습니다.")

    return resolved_target


# ============================================================
# GitHub Issues를 통한 파일 관리
# ============================================================
def handle_issue_event():
    files_data = {}
    excluded_dirs = {
        ".git", ".github", "_site", "node_modules", ".jekyll-cache",
        ".venv", "venv", "__pycache__"
    }

    for root, dirs, files in os.walk("."):
        dirs[:] = [directory for directory in dirs if directory not in excluded_dirs]
        for filename in files:
            filepath = Path(root) / filename
            try:
                # 프롬프트 크기와 비밀정보 노출 위험을 줄이기 위해 일부 파일은 제외합니다.
                if filepath.name in {".env", "credentials.json"}:
                    continue
                if filepath.suffix.lower() not in {
                    ".md", ".html", ".yml", ".yaml", ".json", ".css", ".js", ".py", ".txt"
                }:
                    continue
                files_data[str(filepath)] = filepath.read_text(
                    encoding="utf-8", errors="replace"
                )[:500]
            except OSError:
                continue

    prompt = f"""
당신은 Chance 기술 블로그 저장소의 파일 편집 도우미입니다.
Issue 요청에 필요한 파일 하나를 수정하거나 삭제할 변경안을 JSON으로 반환하세요.
파일 경로는 저장소 내부의 상대 경로만 사용하세요.
보호된 .git, .github, node_modules, _site 디렉터리는 수정하지 마세요.
파일 내용이 필요하면 기존 형식과 프로젝트 구조를 유지하세요.

[Issue Title]
{ISSUE_TITLE}

[Issue Body]
{ISSUE_BODY}

[Repository File Samples]
{json.dumps(files_data, ensure_ascii=False)}

JSON 객체만 반환하세요. 마크다운 코드 펜스를 사용하지 마세요.
스키마:
{{
  "target_file": "relative/path/to/file",
  "file_content": "전체 파일 내용 또는 삭제 시 빈 문자열",
  "delete_file": false
}}
"""

    response = call_gemini_with_fallback(prompt)
    data = extract_json_object(response.text)

    target = safe_repo_path(data.get("target_file"))
    delete_file = data.get("delete_file", False)
    if not isinstance(delete_file, bool):
        raise ValueError("delete_file은 true 또는 false여야 합니다.")

    if delete_file:
        if target.exists() and target.is_file():
            target.unlink()
            print(f"파일 삭제 완료: {target}")
        else:
            print(f"삭제 대상 파일이 없습니다: {target}")
        return

    file_content = data.get("file_content")
    if not isinstance(file_content, str):
        raise ValueError("file_content가 문자열이 아닙니다.")

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_name(target.name + ".tmp")
    temp_target.write_text(file_content, encoding="utf-8")
    temp_target.replace(target)
    print(f"파일 저장 완료: {target}")


# ============================================================
# RSS 뉴스 수집 및 한/영 블로그 글 생성
# ============================================================
def fetch_news_items(history):
    rss_urls = [
        "https://news.google.com/rss/search?q=AI+%ED%85%8C%ED%81%AC+%EA%B8%B0%EC%88%A0&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtdHZHZ0pMVWlnQVAB?hl=ko&gl=KR&ceid=KR:ko",
    ]

    history_set = set()
    for item in history:
        if isinstance(item, str):
            history_set.add(item.strip().casefold())
        elif isinstance(item, dict):
            for key in ("topic", "kr_title", "en_title"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    history_set.add(value.strip().casefold())
    news_items = []
    seen = set()

    for url in rss_urls:
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; ChanceBlogBot/1.0)"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                root = ET.fromstring(response.read())

            for item in root.findall(".//item"):
                title_node = item.find("title")
                if title_node is None or not title_node.text:
                    continue

                title = re.sub(r"\s*-\s*[^-]+$", "", title_node.text).strip()
                key = title.casefold()
                if title and key not in history_set and key not in seen:
                    news_items.append(title)
                    seen.add(key)

        except Exception as exc:
            print(f"RSS 수집 실패 ({url}): {exc}")

    return news_items


def build_post_prompt(topic, history, kr_image, en_image):
    recent_history = history[-20:] if history else []

    return f"""
당신은 개인 기술 전문 블로거 'Chance'입니다.
아래 주제를 바탕으로 독창적이고 사실에 신중한 블로그 글을 한국어와 영어로 각각 작성하세요.

[주제]
{topic}

[최근 다룬 주제 — 중복 금지]
{json.dumps(recent_history, ensure_ascii=False)}

[중요 지침]
- 주제에 맞는 제목, 카테고리, 태그를 작성하세요.
- 한국어 글과 영어 글은 각 언어에 자연스럽게 작성하고, 단순 직역에 그치지 마세요.
- 확인되지 않은 수치, 인용문, 발표 사실을 지어내지 마세요.
- 본문은 충분한 설명과 분석을 포함하고 Markdown으로 작성하세요.
- 각 글의 Front Matter에 layout, title, category, tags, lang, image를 포함하세요.
- 이미지 URL은 지정된 URL을 그대로 사용하세요. 다른 이미지 URL을 추가하지 마세요.
- kr_content와 en_content에는 각각 완전한 Markdown 파일 내용(Front Matter 포함)을 넣으세요.
- JSON 문자열 안의 줄바꿈과 따옴표는 유효한 JSON 규칙을 지켜 반환하세요.
- JSON 객체만 반환하고 Markdown 코드 펜스는 사용하지 마세요.

한국어 대표 이미지: {kr_image}
영어 대표 이미지: {en_image}

반드시 다음 스키마를 지키세요:
{{
  "kr_category": "KR - 카테고리명",
  "kr_title": "한국어 포스트 제목",
  "kr_tags": ["태그1", "태그2"],
  "kr_content": "한국어 Markdown 전체 내용",
  "en_category": "EN - CategoryName",
  "en_title": "English Post Title",
  "en_tags": ["Tag1", "Tag2"],
  "en_content": "English Markdown full content"
}}
"""


def validate_post_data(data, kr_image, en_image):
    required_strings = [
        "kr_category", "kr_title", "kr_content",
        "en_category", "en_title", "en_content",
    ]
    for key in required_strings:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"생성 결과의 {key} 값이 비어 있거나 문자열이 아닙니다.")

    for key in ("kr_tags", "en_tags"):
        if not isinstance(data.get(key), list):
            data[key] = []
        data[key] = [
            str(tag).strip() for tag in data[key]
            if str(tag).strip()
        ]

    # 모델이 이미지/Front Matter를 누락하거나 임의로 변경한 경우 지정 URL로 보정합니다.
    for prefix, image_url, language in (
        ("kr", kr_image, "kr"),
        ("en", en_image, "en"),
    ):
        content_key = f"{prefix}_content"
        content = data[content_key]

        if not content.lstrip().startswith("---"):
            content = (
                "---\n"
                f"layout: post\n"
                f"title: {json.dumps(data[f'{prefix}_title'], ensure_ascii=False)}\n"
                f"category: {json.dumps(data[f'{prefix}_category'], ensure_ascii=False)}\n"
                f"tags: {json.dumps(data[f'{prefix}_tags'], ensure_ascii=False)}\n"
                f"lang: {language}\n"
                f"image: {json.dumps(image_url)}\n"
                "---\n\n"
                + content
            )
        else:
            # 대표 이미지 및 언어를 Front Matter와 본문에 일관되게 적용합니다.
            front_matter_end = content.find("\n---", 3)
            if front_matter_end != -1:
                front = content[3:front_matter_end]
                body = content[front_matter_end + 4:].lstrip("\n")
                front = re.sub(r"(?m)^image:\s*.*$", "", front)
                front = re.sub(r"(?m)^lang:\s*.*$", "", front)
                front = front.rstrip()
                front += f'\nlang: {language}\nimage: "{image_url}"'
                content = f"---{front}\n---\n\n{body}"

        # 파일 대표 이미지와 본문 썸네일을 지정 URL로 고정합니다.
        if not re.search(r"(?m)^!\[[^\]]*\]\(", content):
            content = content.rstrip() + f"\n\n![Thumbnail]({image_url})\n"
        else:
            content = re.sub(
                r"(?m)^!\[[^\]]*\]\(https://images\.unsplash\.com/[^)]+\)",
                f"![Thumbnail]({image_url})",
                content,
                count=1,
            )

        data[content_key] = content.rstrip() + "\n"

    return data


def safe_category_dir(category, prefix):
    """카테고리 문자열을 경로로 직접 사용하지 않도록 안전하게 정리."""
    category = str(category).strip()
    category = re.sub(r"[\x00-\x1f/\\]+", "-", category)
    category = re.sub(r"\.\.+", ".", category).strip(" .")
    if not category:
        category = f"{prefix} - Uncategorized"
    return POSTS_DIR / category


def write_post(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def generate_blog_posts():
    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    # 기존 중복 이미지를 정리하되, 새 글 생성은 계속 시도합니다.
    fix_existing_duplicate_images()
    used_images = get_all_used_images()
    history = read_history()

    news_items = fetch_news_items(history)
    selected_news = (
        news_items[0]
        if news_items
        else "최신 AI 혁신 및 테크 아키텍처 트렌드 분석"
    )

    # 한국어/영어 게시물은 서로 다른 이미지를 사용합니다.
    kr_image = select_unique_image(used_images)
    en_image = select_unique_image(used_images)

    now = datetime.datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")

    prompt = build_post_prompt(selected_news, history, kr_image, en_image)
    response = call_gemini_with_fallback(prompt)
    post_data = extract_json_object(response.text)
    post_data = validate_post_data(post_data, kr_image, en_image)

    kr_dir = safe_category_dir(post_data["kr_category"], "KR")
    en_dir = safe_category_dir(post_data["en_category"], "EN")

    kr_path = kr_dir / f"{date_str}-KR-{time_str}.md"
    en_path = en_dir / f"{date_str}-EN-{time_str}.md"

    # 두 파일 모두 내용을 검증한 뒤 원자적으로 각각 저장합니다.
    write_post(kr_path, post_data["kr_content"])
    try:
        write_post(en_path, post_data["en_content"])
    except Exception:
        # 영어 글 저장에 실패하면 반쪽짜리 실행 흔적을 남기지 않도록 한국어 글도 제거합니다.
        try:
            kr_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    history.append({
        "date": date_str,
        "topic": selected_news,
        "kr_title": post_data["kr_title"],
        "en_title": post_data["en_title"],
    })
    write_history(history)

    print("블로그 글 생성 완료:")
    print(f"- KR: {kr_path}")
    print(f"- EN: {en_path}")
    print(f"- 주제: {selected_news}")


if __name__ == "__main__":
    try:
        if EVENT_NAME == "issues" or ISSUE_TITLE.strip():
            handle_issue_event()
        else:
            generate_blog_posts()
    except Exception as exc:
        print(f"작업 실패: {type(exc).__name__}: {exc}")
        raise
