"""Chance_Blog 자동 생성기.

모드
- 기본: 뉴스 주제를 골라 KR/EN 글 한 쌍을 생성
- FIX_IMAGES=1: 새 글 없이 기존 글의 깨진/누락/중복 이미지만 교체
- (이슈 기반 수정은 issue-edit.yml / pipeline/edits 가 처리한다. 옛 LLM 파일 편집 핸들러는 제거됨: D-01)
- DRY_RUN=1: 파일 쓰기/커밋 없이 계획만 로그로 출력
  (API 키가 없으면 Gemini/Unsplash는 스텁으로 동작)
"""
import os
import re
import sys
import copy
import json
import zlib
import html
import random
import time
import difflib
import inspect
import datetime
from email.utils import parsedate_to_datetime
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from collections import namedtuple
from datetime import timezone, timedelta
from pathlib import Path

from pipeline import ai_guard, provenance  # 글 출처 표식(provenance: facts) 읽기와, AI 를 부르기 직전에 표식 글의 글자가 프롬프트에 있으면 부르지 않는 방벽(docs/AI_FLOW.md)
from pipeline import drafts  # 승인 흐름(레지스트리 publish_flow: pr)의 이름·판정 규칙. direct(기본)에서는 흐름을 읽는 것 말고 아무것도 하지 않는다
from pipeline import quality_gate, registry  # 최소 품질 Gate(순수 규칙)와 레지스트리 설정(chance.quality_gate·languages) 읽기. quality_gate 가 off(기본)면 Gate 는 아무것도 하지 않는다
from pipeline import unsplash_credit  # Unsplash 사진의 ixid 유지·작가 출처 줄(순수 함수 — Chance·이슈 수정·Blogger 가 같은 규칙을 쓴다)
from pipeline import source_policy  # 소스 정책(레지스트리 chance.source_policy: legacy 가 기본 — 이전과 같다 / allowlist 는 허용 목록 밖 외부 읽기와 외부 텍스트의 프롬프트·이력·로그 유입을 막는다). legacy 에서는 값을 읽는 것 말고 아무 일도 하지 않는다
from pipeline import egress  # 외부 호출 관문(허용 목록 밖 호스트 거부)·호출 예산 — 구조화 Fact 경로의 연결 코드(fact_opener)가 주입되는 opener 를 감쌀 때만 쓴다
from pipeline import fact_supply  # 구조화 Fact 경로(레지스트리 chance.content_source: facts)의 후보 공급 — 생성기가 Fact 모듈을 부르는 유일한 연결 한 줄이다(시험 NoConnectionTest). 그 분기는 AI 를 부르지 않는다(docs/AI_FLOW.md §12)
from pipeline.llm import CALL_TIMEOUT_SECONDS, CallLog, _run_with_timeout, failure_code, failure_status, scrub  # Gemini 요청 기록·시크릿 가리기·호출 시간 상한은 Blogger·이슈 수정과 같은 코드를 쓴다(D-52·D-83)

# ============================================================
# 환경 설정
# ============================================================
API_KEY = os.environ.get("GEMINI_API_KEY")
UNSPLASH_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")


def _flag(name):
    return os.environ.get(name, "0").strip().lower() in {"1", "true", "yes"}


DRY_RUN = _flag("DRY_RUN")
FIX_IMAGES = _flag("FIX_IMAGES")
EVENT_NAME = os.environ.get("EVENT_NAME", "").strip().lower()

STUB_GEMINI = not API_KEY
STUB_UNSPLASH = not UNSPLASH_KEY

KST = timezone(timedelta(hours=9))
POSTS_DIR = Path("_posts")
HISTORY_FILE = Path("history.json")
EDITORIAL_TEMPLATE_FILE = Path(__file__).resolve().parent / ".github/editorial/CHANCE_BLOG_TEMPLATE.md"
UA = "Mozilla/5.0 (compatible; ChanceBlogBot/2.0)"
MAX_ATTEMPTS = 3
# MAX_ATTEMPTS 는 '한 번의 실행에서 모델에 보내 보는 후보의 총 수'다. 첫 분야의 후보가 모두 탈락해 다음 분야를 이어서 시도해도 분야를 합쳐 이 수를 넘지 않는다(2026-11-04 gfix, A) —
# 무료 한도를 쓰는 모델 호출 수의 상한이다(모델 폴백으로 후보 하나에 SDK 호출이 최대 모델 수만큼 나갈 수 있다는 점은 그대로).
# Minimum body length before source lists and thumbnails. This is a floor against
# thin drafts, not a target or a substitute for editorial review.
MIN_BODY_CHARS = {"kr": 1000, "en": 1500}
# 자동 게시 시각(KST, 시 단위). 출처 확인과 충분한 편집 가치를 위해 하루 2회로 운영합니다.
# 환경변수 POST_HOURS_KST="9,18" 로 변경 가능
SLOT_HOURS = sorted({int(x) for x in os.environ.get("POST_HOURS_KST", "9,18").split(",")
                     if x.strip().isdigit() and 0 <= int(x) <= 23})

MODEL_CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
]
# 모델 호출 하나의 시간 상한(초): Blogger·이슈 수정이 쓰는 pipeline/llm.py 의 장치(_run_with_timeout·CALL_TIMEOUT_SECONDS)를 그대로 쓴다(D-66·D-83).
# 서버가 응답 없이 연결을 붙잡으면 SDK 는 끊길 때까지 기다린다 — 2026-10-26 18시 슬롯의 호출은 283초 뒤 'Server disconnected', 2026-11-01 18:44 실행은 20분 제한에 걸려 취소되어 그 슬롯이 사라졌다.
# 길이는 llm.py 의 값(120초)을 따른다: 이 엔진의 호출은 한국어·영어 글 한 쌍을 한 번에 쓰는 긴 응답이지만 정상 소요가 30~90초(D-66 관측, 2026-11-04 진단 33·56초)라 120초는 정상 응답을 자르지 않는 선이고
# 멈춘 서버를 20분 제한까지 기다리지 않는다. 넘으면 그 모델은 실패(CallTimeout)로 세어 다음 모델로 넘어가고, 모두 실패하면 지금처럼 RuntimeError 다(모델 폴백 흐름 그대로).
GEMINI_CALL_TIMEOUT_SECONDS = CALL_TIMEOUT_SECONDS
# 모델에 JSON 응답을 요청하는 호출 설정: google-genai 의 GenerateContentConfig.response_mime_type(SDK 문서의 JSON 출력 예시가 쓰는 필드, config 는 딕셔너리로도 받는다).
# 프롬프트의 'JSON 객체만 반환' 문장만으로는 줄바꿈·따옴표를 어긴 응답이 후보를 탈락시켰다(extract_json_object 의 ValueError). 프롬프트·본문 검증 기준은 그대로다.
# SDK 의 generate_content 가 config 를 받지 않으면 걸지 않고, 모델이 형식 지정 자체를 거절하면 같은 모델을 지정 없이 한 번 더 부른다(_generate).
JSON_RESPONSE_CONFIG = {"response_mime_type": "application/json"}

# 검색 결과가 전혀 없을 때만 쓰는 최후 폴백 (글 생성 시에만 사용)
POOL_IDS = [
    "1591488320449-011701bb6704", "1550745165-9bc0b252726f",
    "1518770660439-4636190af475", "1526374965328-7f61d4dc18c5",
    "1555680202-c86f0e12f086", "1563770660941-20978e870e26",
    "1677442136019-21780ecad985", "1618005182384-a83a8bd57fbe",
    "1620712943543-bcc4688e7485", "1507146426996-ef05306b995a",
    "1531482615713-2afd69097998", "1541185933-ef5d8ed016c2",
    "1614728894747-a83421e2b9c9", "1451187580459-43490279c0fa",
    "1446776811953-b23d57bd21aa", "1484589065579-248aad0d8b13",
    "1517976487502-5f654b0c2794", "1485827404703-89b55fcc595e",
    "1558494949-ef010cbdcc31", "1563986768609-322da13575f3",
    "1510511459019-5dda7724fd87", "1544197150-b99a580bb7a8",
    "1486406146926-c627a92ad1ab", "1519501025264-65ba15a82390",
    "1504384308090-c894fdcc538d", "1473968512647-3e447244af8f",
    "1508739773434-c26b3d09e071", "1516321318423-f06f85e504b3",
    "1535378917042-10a22c95931a", "1504639725590-34d0984388bd",
    "1518773553398-650c184e0bb3", "1531297484001-80022131f5a1",
]
IMG_PARAMS = "?auto=format&fit=crop&w=1000&q=80"
IMAGE_POOL = [f"https://images.unsplash.com/photo-{i}{IMG_PARAMS}" for i in POOL_IDS]

TECH_KO = (
    "인공지능", "반도체", "로봇", "소프트웨어", "클라우드", "스마트폰", "우주",
    "위성", "로켓", "게임", "보안", "해킹", "데이터", "앱", "개발", "테크",
    "전기차", "배터리", "양자", "엔비디아", "삼성전자", "하이닉스", "구글",
    "애플", "메타", "마이크로소프트", "테슬라", "스타트업", "생성형", "웨어러블",
    "디스플레이", "통신", "네트워크", "플랫폼", "컴퓨터", "서버", "센서", "드론",
    "자율주행", "핵융합", "과학", "기술", "칩", "챗gpt", "오픈ai",
)
# 영문 낱말 경계는 ASCII 글자·숫자 기준이다. 파이썬의 \b 는 한글도 낱말 글자로 봐서 'AI가'·'생성AI' 처럼 한글이 붙은 말을 놓친다(Dubai·Chipotle 처럼 영문 속에 든 것만 거른다).
TECH_EN = re.compile(
    r"(?<![A-Za-z0-9])(ai|gpu|cpu|llm|chatgpt|openai|nvidia|5g|6g|chip|robot|quantum|"
    r"software|cloud|startup|cyber|satellite|rocket)(?![A-Za-z0-9])", re.I)

_client = None
_download_locations = {}
# 사진(image_key = 호스트+경로)별 작가 출처 (이름, 프로필 주소) — search_unsplash·fetch_pool_photo 가 검사·정리를 통과한 것만 적는다. 여기에 없는 사진은 새 글·이미지 교체에 쓰지 않는다.
_credits = {}
STUB_CREDIT = ("Stub Photographer", "https://unsplash.com/@stub_photographer")   # 연습 실행(키 없음)의 가짜 사진에 붙이는 가짜 출처 — 연습 실행은 아무것도 저장하지 않는다
POOL_LOOKUP_MAX_BODY = 1_000_000   # 사진 조회 응답을 이 바이트까지만 읽는다
POOL_LOOKUP_MAX_FAILS = 3   # 고정 목록 사진 조회가 연달아 이만큼 실패하면 더 부르지 않는다(키가 막혔을 때 한도만 쓰지 않게)
POOL_LOOKUP_MAX_TOTAL = 6   # 한 번의 pick_images 호출에서 고정 목록 사진 조회(fetch_pool_photo)를 부르는 총 횟수 상한 — 성공·실패·주소 확인 실패·이미 쓴 사진을 가리지 않고 '조회를 부른 횟수'를 센다(시간당 한도를 지킨다)


# ============================================================
# 공통 유틸
# ============================================================
def get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=API_KEY)
    return _client


def write_text_atomic(path, content):
    path = Path(path)
    if DRY_RUN:
        print(f"[DRY_RUN] 쓰기 생략: {path}")
        return
    if shadow_run_on():     # 그림자 실행(SHADOW_RUN=1)은 읽기 전용이다 — DRY_RUN 과 같은 쓰기 차단을 코드로 강제한다(결과는 shadow_run 의 쓰기 도구가 SHADOW_OUT 아래에만 쓴다)
        print(f"[SHADOW_RUN] 쓰기 생략: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def read_history():
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError) as exc:
        print(f"history.json 읽기 실패, 빈 기록으로 진행: {exc}")
        return []


def write_history(history):
    write_text_atomic(
        HISTORY_FILE,
        json.dumps(history[-200:], ensure_ascii=False, indent=2),
    )


def extract_json_object(raw_text):
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

    start = text.find("{")
    if start < 0:
        raise ValueError(f"JSON 객체를 찾을 수 없습니다: {text[:300]}")
    depth, in_string, escaped = 0, False, False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                parsed = json.loads(text[start:index + 1])
                if not isinstance(parsed, dict):
                    raise ValueError("최상위 JSON 값이 객체가 아닙니다.")
                return parsed
    raise ValueError(f"완전한 JSON 객체를 찾을 수 없습니다: {text[:300]}")


# 이번 실행의 Gemini 모델 호출 횟수. 무료 한도(프로젝트 단위)를 나눠 쓰기 위한 측정값이며 동작에는 영향이 없다.
GEMINI_CALLS = {"attempts": 0, "failed": 0}
# 요청별 기록(요청 모델·응답 모델·결과 종류·소요·토큰, 실패 때는 코드·상태·본문 600자). 로그 한 줄씩 남기고 실행 요약에서 접어 쓴다.
# 장부 파일은 만들지 않는다. 호출 수는 위 GEMINI_CALLS 가 세고, 이 기록은 그 내역이다. 이 실행의 Gemini 키는 로그에 글자 그대로 나가지 않는다.
CALL_LOG = CallLog(label="chance", purpose="post", out=print, secrets=(API_KEY,))


def _scrub(text):
    """로그·예외 문구에 쓰기 전에 비밀을 가린다: 비밀 패턴(mask) + 프로젝트 번호 + 이 실행의 Gemini 키(글자 그대로)."""
    return scrub(text, (API_KEY,))


def _accepts_config(generate):
    """SDK 의 generate_content 가 config 인자를 받는가. 받지 않는 낡은 SDK·단순한 대역에는 형식 지정을 걸지 않는다(지원이 불확실하면 적용하지 않는다)."""
    try:
        params = inspect.signature(generate).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == "config" or p.kind is inspect.Parameter.VAR_KEYWORD for p in params)


def _format_rejected(exc):
    """모델이 JSON 형식 지정(response_mime_type) 자체를 거절한 오류인가: HTTP 400(INVALID_ARGUMENT)이고 문구가 mime 형식·JSON·응답 형식·생성 설정 중 하나를 말한다(문구가 낯설어도 이 낱말 중 하나는 든다 — 독립 검증 지적 2026-11-04). 그 밖의 400(키·요청 오류)은 해당하지 않는다."""
    if failure_code(exc) != 400 and failure_status(exc).upper() != "INVALID_ARGUMENT":
        return False
    return bool(re.search(r"mime|json|response.?format|response.?schema|generation.?config", str(exc), re.I))


def _generate(model_name, prompt, started):
    """SDK 호출 한 번: JSON 응답 형식을 지정하고(SDK 가 config 를 받을 때) 시간 상한(GEMINI_CALL_TIMEOUT_SECONDS)을 건다.
    모델이 형식 지정 자체를 거절하면(_format_rejected) 같은 모델을 지정 없이 한 번 더 부른다 — 형식 지정은 최선 노력이고 글을 못 만드는 쪽으로 번지지 않게 한다.
    거절당한 첫 호출도 한 번의 요청이라 호출 수(GEMINI_CALLS)와 요청 기록(CALL_LOG)에 센다. started 는 첫 호출을 시작한 시각(time.monotonic)이다."""
    sent = {}

    def call(with_config):
        generate = get_client().models.generate_content
        kwargs = {"model": model_name, "contents": prompt}
        if with_config and _accepts_config(generate):
            kwargs["config"] = dict(JSON_RESPONSE_CONFIG)
            sent["config"] = True
        return generate(**kwargs)

    try:
        return _run_with_timeout(lambda: call(True), GEMINI_CALL_TIMEOUT_SECONDS)
    except Exception as exc:
        if not (sent.get("config") and _format_rejected(exc)):
            raise
        print(f"Gemini 모델이 JSON 형식 지정을 거절해 지정 없이 다시 호출합니다: {model_name} - {_one_line(_scrub(exc))}")
        GEMINI_CALLS["failed"] += 1
        CALL_LOG.failure(model_name, time.monotonic() - started, exc)
        GEMINI_CALLS["attempts"] += 1
        return _run_with_timeout(lambda: call(False), GEMINI_CALL_TIMEOUT_SECONDS)


def call_gemini_with_fallback(prompt):
    ai_guard.assert_clean(prompt)    # AI 입구 ①: 표식 글(구조화 공개 자료로 만든 글)의 글자가 프롬프트에 있으면 모델을 한 번도 부르지 않고 AiInputForbidden 을 올린다(재시도·폴백 없음). 표식 글이 없으면 그대로 지나간다
    errors = []
    for model_name in MODEL_CANDIDATES:
        started = time.monotonic()
        response, failure, usable = None, None, False
        try:
            print(f"Gemini 모델 호출 시도: {model_name}")
            GEMINI_CALLS["attempts"] += 1
            response = _generate(model_name, prompt, started)
            text = getattr(response, "text", None)
            usable = bool(text and text.strip())
        except Exception as exc:
            failure = exc
        elapsed = time.monotonic() - started   # 기록은 try 밖에서 한다: 기록 때문에 호출 실패로 오인되는 일이 없게
        if failure is None:
            if usable:
                print(f"Gemini 모델 호출 성공: {model_name}")
                CALL_LOG.success(model_name, elapsed, response)
                return response
            GEMINI_CALLS["failed"] += 1
            errors.append(f"{model_name}: 응답 텍스트 없음")
            CALL_LOG.empty(model_name, elapsed, response)
        else:
            GEMINI_CALLS["failed"] += 1
            errors.append(f"{model_name}: {_scrub(failure)}")   # 이 문구는 예외 메시지(트레이스백·`작업 실패` 줄)로 나가므로 가린 것을 쓴다
            print(f"Gemini 모델 호출 실패: {model_name} - {_one_line(_scrub(failure))}")
            CALL_LOG.failure(model_name, elapsed, failure)
    raise RuntimeError("모든 Gemini 모델 호출 실패\n" + "\n".join(errors))


# ============================================================
# 이미지: 정규화 / 검증 / Unsplash 검색
# ============================================================
def image_key(url):
    """중복 비교 키: 호스트+경로 (쿼리스트링 제외)."""
    if not url:
        return ""
    url = url.strip().strip("\"'")
    p = urllib.parse.urlsplit(url)
    return (p.netloc + p.path).lower()


def build_image_url(raw):
    """urls.raw → 쓸 사진 주소: 호스트·경로에 크기·형식 매개변수(IMG_PARAMS)를 붙인다. Unsplash 가 준 `ixid`(앱의 사진 조회 보고용 추적 값 — Unsplash API 지침은 크기를 바꿔도 남기라고 한다)는
    올바른 모양이면 `?ixid=<값>&auto=format…` 으로 남기고, 없거나 모양이 틀리면 옛 동작(매개변수만)이다 — 글 발행은 막지 않는다. 중복 판정 키(image_key)는 호스트+경로라 그대로다."""
    p = urllib.parse.urlsplit(raw)
    return unsplash_credit.with_ixid(f"{p.scheme}://{p.netloc}{p.path}", p.query, IMG_PARAMS)


def url_ok(url, timeout=10):
    if DRY_RUN and STUB_UNSPLASH and "photo-dry" in url:
        return True
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


# 마지막으로 관측한 Unsplash 응답 헤더(X-Ratelimit-Remaining·X-Ratelimit-Limit). 시간당 한도(데모 앱 50회)를 얼마나 썼는지 보려는
# 측정값이며 동작에는 영향이 없다. 응답에 헤더가 없으면 이전 값을 그대로 둔다.
UNSPLASH_RATE = {"remaining": None, "limit": None}


def _note_unsplash_rate(headers):
    if headers is None:
        return
    for key, header in (("remaining", "X-Ratelimit-Remaining"), ("limit", "X-Ratelimit-Limit")):
        try:
            value = headers.get(header)
        except AttributeError:  # get 을 지원하지 않는 이상한 객체
            return
        if isinstance(value, str) and re.fullmatch(r"\d{1,7}", value.strip()):
            UNSPLASH_RATE[key] = int(value.strip())


def _api_request(url):
    """Unsplash API 요청 한 건(검색·고정 목록 조회·사용 알림이 모두 이것으로 만든다). 키(Authorization)는 '리다이렉트 때 따라가지 않는' 머리글로만 싣는다 —
    응답이 다른 호스트로 보내도 키가 새 요청에 복사되지 않는다(req.headers 에 없고 unredirected_hdrs 에만 있다). 키는 주소·로그·예외 글에 들어가지 않는다."""
    req = urllib.request.Request(url, headers={"Accept-Version": "v1", "User-Agent": UA})
    req.add_unredirected_header("Authorization", f"Client-ID {UNSPLASH_KEY}")
    return req


def _forget_photo(key):
    """이 사진의 기록(작가 출처·사용 알림 주소)을 모두 지운다 — 앞선 응답의 낡은 값이 남아 쓰이지 않게."""
    _credits.pop(key, None)
    _download_locations.pop(key, None)


def _note_skipped(skipped):
    """검사에 걸려 버린 사진을 고정 문구로 묶어 한 번씩 알린다(응답의 값은 로그에 싣지 않는다)."""
    if skipped.get("url"):
        print(f"[참고] 사진 주소가 허용된 형식이 아니어서 쓰지 않은 사진: {skipped['url']}장")
    if skipped.get("ping"):
        print("[참고] 사용 알림 주소가 올바르지 않은 사진은 쓰지 않습니다")


def _record_photo(item, skipped=None):
    """검색·조회 응답의 사진 한 건을 읽어 쓸 주소(ixid 가 든 build_image_url)를 돌려주고, 사용 알림 주소(_download_locations)와 작가 출처(_credits)를 기록한다.

    검사 순서(모두 통과한 뒤에만 기록한다): 주소 만들기 → 주소 검사(photo_url_ok: https·호스트가 정확히 images.unsplash.com·경로 `/photo-<번호>`) →
    사용 알림 주소 검사(safe_download_url: 호스트가 정확히 api.unsplash.com 인 `/photos/<id>/download` — 키가 그 주소로 가므로) → 작가 읽기 → 기록.
    주소 검사나 사용 알림 주소 검사에 걸린 사진은 쓰지 않는다(None, 그 사진의 낡은 기록도 지운다). 사용 알림 주소가 아예 없으면(None·빈 문자열) 사진은 쓰되 알림 호출만 없다.
    출처를 검사·정리하지 못한 사진은 기록부에서 지운다. 주소가 없으면 None. skipped(딕셔너리)를 주면 버린 사진 수를 'url'·'ping' 칸에 더하고 로그 줄은 부르는 쪽이 묶어서 한 번 낸다(search_unsplash·fetch_pool_photo).
    주지 않고 직접 부르면 걸린 그 자리에서 같은 고정 문구를 한 줄 낸다."""
    own = skipped is None
    skipped = skipped if skipped is not None else {}
    if not isinstance(item, dict):
        return None
    urls = item.get("urls")
    raw = urls.get("raw") if isinstance(urls, dict) else None
    if not raw or not isinstance(raw, str):
        return None
    try:
        url = build_image_url(raw)
        key = image_key(url)
    except ValueError:      # 주소를 읽을 수 없는 항목은 건너뛴다(예전에는 검색 전체가 예외로 멈췄다)
        return None
    if not unsplash_credit.photo_url_ok(url):
        _forget_photo(key)
        skipped["url"] = skipped.get("url", 0) + 1
        if own:
            _note_skipped(skipped)
        return None
    links = item.get("links")
    loc = links.get("download_location") if isinstance(links, dict) else None
    ping = ""
    if loc not in (None, ""):
        ping = unsplash_credit.safe_download_url(loc)
        if not ping:
            _forget_photo(key)
            skipped["ping"] = skipped.get("ping", 0) + 1
            if own:
                _note_skipped(skipped)
            return None
    if ping:
        _download_locations[key] = ping
    else:
        _download_locations.pop(key, None)
    author = unsplash_credit.author_of(item)
    if author:
        _credits[key] = author
    else:
        _credits.pop(key, None)
    return url


def search_unsplash(query, per_page=15):
    if STUB_UNSPLASH:
        if DRY_RUN:
            crc = zlib.crc32(query.encode("utf-8")) % 100000
            print(f"[DRY_RUN] Unsplash 스텁 검색: {query!r}")
            urls = [f"https://images.unsplash.com/photo-dry{crc}{i}{IMG_PARAMS}"
                    for i in range(3)]
            for url in urls:
                _credits[image_key(url)] = STUB_CREDIT
            return urls
        print("UNSPLASH_ACCESS_KEY 없음: 검색 생략")
        return []
    params = urllib.parse.urlencode({
        "query": query, "per_page": per_page,
        "orientation": "landscape", "content_filter": "high",
    })
    req = _api_request("https://api.unsplash.com/search/photos?" + params)
    headers = None
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            headers = getattr(resp, "headers", None)
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        _note_unsplash_rate(getattr(exc, "headers", None))
        print(f"Unsplash API 오류 {exc.code} (query={query!r}) "
              "- 403/429면 시간당 호출 한도 초과일 수 있습니다.")
        return []
    except Exception as exc:
        print(f"Unsplash 호출 실패 (query={query!r}): {_one_line(exc, 200)}")
        return []
    _note_unsplash_rate(headers)

    urls, skipped = [], {}
    for item in data.get("results", []):
        url = _record_photo(item, skipped)
        if url:
            urls.append(url)
    _note_skipped(skipped)
    missing = sum(1 for url in urls if "?ixid=" not in url)
    if missing:
        print(f"[IXID] 사진 {missing}장은 주소에 올바른 ixid 가 없어 ixid 없이 씁니다(글은 그대로 올라갑니다)")
    return urls


def trigger_download(url):
    """Unsplash API 가이드라인: 사진 사용 시 download 엔드포인트 호출 (실패해도 무시).
    기록된 주소를 부르기 직전에 한 번 더 검사한다(safe_download_url — 호스트가 정확히 api.unsplash.com 인 `/photos/<id>/download` 만, 키가 그 호스트로만 가게). 검사에 걸리면 어떤 요청도 보내지 않는다."""
    loc = unsplash_credit.safe_download_url(_download_locations.get(image_key(url)))
    if not loc or DRY_RUN or STUB_UNSPLASH or shadow_run_on():
        return
    try:
        urllib.request.urlopen(_api_request(loc), timeout=10).read()
    except Exception:
        pass


def credit_line_for(url):
    """사진의 작가 출처 줄(마크다운 한 줄). 출처를 모르는 사진은 빈 문자열."""
    author = _credits.get(image_key(url))
    return unsplash_credit.credit_markdown(*author) if author else ""


def fetch_pool_photo(pool_url):
    """고정 목록(IMAGE_POOL) 사진 하나를 Unsplash API(GET /photos/photo-<번호>, 같은 키·머리글)로 한 번 조회해 ixid 가 든 주소를 얻고, 작가 출처·사용 알림 주소를 기록한다.
    고정 주소에는 ixid·작가·사용 알림 정보가 없어 조회가 되어야만 쓴다. 키가 없거나(스텁) 조회·검사가 어긋나면 None — 출처를 알 수 없는 사진은 새 글에 쓰지 않는다."""
    match = re.fullmatch(r"/photo-(.+)", urllib.parse.urlsplit(str(pool_url)).path)
    lookup = unsplash_credit.photo_lookup_id(match.group(1)) if match else ""
    if STUB_UNSPLASH or not lookup:
        return None
    req = _api_request(f"https://api.unsplash.com/photos/{lookup}")      # 키는 리다이렉트를 따라가지 않는 머리글로만 간다
    headers = None
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            headers = getattr(resp, "headers", None)
            body = resp.read(POOL_LOOKUP_MAX_BODY + 1)      # 사진 한 장의 응답은 수십 KB — 상한을 두어 엉뚱하게 큰 응답을 읽지 않는다
        if not isinstance(body, (bytes, bytearray)) or len(body) > POOL_LOOKUP_MAX_BODY:
            return None
        data = json.loads(bytes(body).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        _note_unsplash_rate(getattr(exc, "headers", None))
        print(f"Unsplash API 오류 {exc.code} (사진 조회) - 403/429면 시간당 호출 한도 초과일 수 있습니다.")
        return None
    except Exception as exc:
        print(f"Unsplash 호출 실패 (사진 조회): {_one_line(exc, 200)}")
        return None
    _note_unsplash_rate(headers)
    skipped = {}
    url = _record_photo(data, skipped)      # 주소 모양·사용 알림 주소 검사는 _record_photo 가 한다(검색 경로와 같은 검사) — 통과한 주소만 돌려준다
    _note_skipped(skipped)
    if not url or image_key(url) not in _credits:      # 작가 출처를 알 수 없는 사진은 쓰지 않는다
        return None
    return url


def pick_images(queries, used, count=1, allow_pool=False):
    """미사용 + 접근 가능한 이미지를 count개 선택. used 집합에 키를 추가한다."""
    picked = []
    seen_queries = set()
    uncredited = 0
    for q in queries:
        q = (q or "").strip()
        if not q or q.lower() in seen_queries:
            continue
        seen_queries.add(q.lower())
        for url in search_unsplash(q):
            key = image_key(url)
            if key not in _credits:      # 작가 출처를 알 수 없는 사진은 쓰지 않는다(Unsplash API 지침: 작가·Unsplash 표기)
                uncredited += 1
                continue
            if key in used or not url_ok(url):
                continue
            used.add(key)
            picked.append(url)
            print(f"  이미지 선택 (query={q!r}): {url}")
            if len(picked) >= count:
                return picked
    if uncredited:
        print(f"  [참고] 작가 출처 정보가 없어 쓰지 않은 사진: {uncredited}장")
    if allow_pool:
        failed = looked = 0
        for pool_url in IMAGE_POOL:
            if image_key(pool_url) in used:
                continue
            if looked >= POOL_LOOKUP_MAX_TOTAL:     # 연속 실패가 아니어도(주소 확인 실패·이미 쓴 사진이 이어져도) 한 번에 부르는 조회 총 횟수에 상한을 둔다
                print("  [경고] 고정 목록 사진 조회가 한 번에 허용한 횟수에 닿아 더 시도하지 않습니다")
                break
            looked += 1
            url = fetch_pool_photo(pool_url)     # 조회로 ixid·작가 출처·사용 알림 주소를 받아야 쓴다 — 조회가 안 되면 출처 없는 사진을 몰래 쓰지 않는다
            if not url:
                failed += 1
                if failed >= POOL_LOOKUP_MAX_FAILS:
                    print("  [경고] 고정 목록 사진 조회가 연달아 실패해 더 시도하지 않습니다(키·한도·네트워크를 확인하세요)")
                    break
                continue
            failed = 0
            key = image_key(url)
            if key in used or not url_ok(url):
                continue
            used.update((key, image_key(pool_url)))
            picked.append(url)
            print(f"  [경고] 검색 결과 없음, 폴백 풀 이미지 사용: {url}")
            if len(picked) >= count:
                break
    return picked


def make_image_queries(title, tags, category):
    """글 제목/태그로 영어 Unsplash 검색어 3개를 만든다 (구체적 -> 일반적)."""
    fallback = ["technology", "computer hardware"]
    if STUB_GEMINI:
        return fallback
    prompt = f"""
다음 블로그 글의 대표 이미지를 Unsplash에서 찾기 위한 영어 검색어 3개를 만드세요.
- 구체적인 것부터 일반적인 것 순서
- 각 2~4단어, 주제를 시각적으로 보여주는 사물/장면 위주
- 사람 얼굴, 로고, 브랜드명, 글자가 들어간 이미지는 피하는 단어 선택
[제목] {title}
[태그] {tags}
[카테고리] {category}
JSON 객체만 반환: {{"image_queries": ["...", "...", "..."]}}
"""
    try:
        with CALL_LOG.purposed("image-queries"):
            data = extract_json_object(call_gemini_with_fallback(prompt).text)
        qs = [q.strip() for q in data.get("image_queries", [])
              if isinstance(q, str) and q.strip()]
        return qs[:4] or fallback
    except ai_guard.AiInputForbidden:
        raise      # 방벽이 막은 것은 '검색어 생성 실패' 로 삼켜 기본값으로 덮지 않는다 — 입력을 만드는 코드의 결함 신호라 실행이 빨갛게 끝나야 한다
    except Exception as exc:
        print(f"검색어 생성 실패, 기본값 사용: {_one_line(exc, 400)}")
        return fallback


# ============================================================
# 게시글 읽기 / 프론트매터
# ============================================================
FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


def split_front_matter(text):
    m = FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def fm_get(fm, key):
    if not fm:
        return ""
    m = re.search(rf"(?m)^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", fm)
    if not m:
        return ""
    v = m.group(1).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def date_of(path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", Path(path).name)
    return m.group(1) if m else "0000-00-00"


def load_posts(*, for_ai=True):
    """`_posts` 의 글을 읽는다(날짜순). for_ai 는 키워드로만 받는다(위치 인자로 넘기면 TypeError — 정적 규칙이 못 보는 호출 모양을 코드가 막는다).

    for_ai=True(기본)는 **AI 입력이 될 수 있는 읽기**다 — 새 글 프롬프트의 최근 제목·기존 글 이미지 교체의 검색어·그림자 실행이 이 목록에서 나온다. 표식 글(머리말 `provenance`)과
    표식 여부를 알 수 없는 글(머리말이 닫히지 않음·표식 값이 이상함)은 목록에 넣지 않는다(알 수 없으면 막는다). 읽지 못하는 파일(읽기 오류·UTF-8 아님)은 어느 쪽이든 건너뛴다.
    for_ai=False 는 사람·알림·사이트가 읽는 곳 전용이다(모든 글, 글마다 `provenance` 칸에 표식 상태). AI 를 부를 수 있는 함수는 for_ai=False 로 부르지 않는다(tests/ai_flow_scan.py AF6)."""
    posts = []
    if not POSTS_DIR.exists():
        return posts
    withheld = 0
    for p in POSTS_DIR.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"읽기 실패 ({p}): {exc}")
            continue
        mark = provenance.mark_of_text(text)
        if for_ai and provenance.mark_blocks_ai(mark):
            withheld += 1
            continue
        fm, _ = split_front_matter(text)
        posts.append({
            "path": p, "text": text,
            "title": fm_get(fm, "title"),
            "image": fm_get(fm, "image"),
            "tags": fm_get(fm, "tags"),
            "category": fm_get(fm, "category"),
            "provenance": mark,
        })
    if withheld:
        print(f"[참고] 표식 글(구조화 공개 자료로 만든 글)이거나 표식 여부를 알 수 없는 글 {withheld}편은 AI 입력이 될 수 있는 읽기에서 뺐습니다")
    posts.sort(key=lambda x: (date_of(x["path"]), x["path"].name))
    return posts


def apply_image(text, old_url, new_url):
    """글의 대표 이미지를 new_url 로 바꾼다. 새 사진의 작가 출처 줄은 옛 줄(우리 모양)을 지우고 새 이미지 줄 바로 다음에 넣는다(출처를 모르면 옛 줄만 지운다)."""
    credit = credit_line_for(new_url)
    if old_url and old_url in text:
        return unsplash_credit.place_credit(text.replace(old_url, new_url), new_url, credit)
    fm, body = split_front_matter(text)
    if fm is None:
        return text
    if re.search(r"(?m)^image:", fm):
        fm = re.sub(r"(?m)^image:.*$", f'image: "{new_url}"', fm)
    else:
        fm = fm.rstrip() + f'\nimage: "{new_url}"'
    return unsplash_credit.place_credit(f"---\n{fm}\n---\n{body}", new_url, credit)


def used_keys_from_posts(posts, exclude_path=None):
    used = set()
    for post in posts:
        if exclude_path is not None and post["path"] == exclude_path:
            continue
        for u in re.findall(r"https://images\.unsplash\.com/[^\s\"')]+", post["text"]):
            used.add(image_key(u))
        if post["image"]:
            used.add(image_key(post["image"]))
    return used


def diagnose(post, used):
    if provenance.post_blocks_ai(post):      # 표식 글(구조화 공개 자료로 만든 글)은 이미지 점검·교체 대상이 아니다(duplicate·broken·missing 으로 세지 않는다)
        return None
    img = post["image"]
    if not img:
        return "missing"
    if not img.lower().startswith("http"):
        return "local-path"
    if image_key(img) in used:
        return "duplicate"
    if not url_ok(img):
        return "broken"
    return None


def repair(post, used):
    if provenance.post_blocks_ai(post):      # 표식 글의 제목·태그·분류는 AI 검색어 입력이 될 수 없다 — 교체 후보 없음으로 건너뛴다
        return None
    queries = make_image_queries(post["title"], post["tags"], post["category"])
    picked = pick_images(queries, used, 1, allow_pool=False)
    return picked[0] if picked else None


# ============================================================
# FIX_IMAGES 모드
# ============================================================
# 한 번에 처리하는 글 수 상한. 글마다 Gemini(검색어 3개, 모든 모델이 실패하면 글당 모델 수만큼)와 Unsplash 를 부르므로, 문제 글이 많아도
# 이만큼만 처리하고 나머지는 다음 실행으로 넘긴다(무료 한도 보호). chance-fix-images.yml 의 입력 설명에도 같은 숫자가 있다(시험이 대조한다).
FIX_IMAGES_MAX_PER_RUN = 20


def fix_images(keyword=None):
    posts = load_posts(for_ai=True)      # 표식 글은 이 목록에 없다 — 사진 교체(AI 검색어)의 대상도, 중복 판정의 기준도 아니다
    print(f"검사 대상 글: {len(posts)}개 (오래된 글의 이미지를 우선 유지)")
    used, targets = set(), []
    for post in posts:
        problem = diagnose(post, used)
        if not problem and keyword:
            haystack = f"{post['title']} {post['tags']} {post['path']}".lower()
            if keyword.lower() in haystack:
                problem = "requested"
        if problem:
            targets.append((post, problem))
            print(f"- 문제({problem}): {post['path']}  image={post['image'] or '(없음)'}")
        else:
            used.add(image_key(post["image"]))

    # 한 번에 처리하는 글 수에 상한을 둔다(글마다 Gemini 검색어와 Unsplash 를 부른다). 넘는 글은 다음 실행에서 다시 진단해 처리한다.
    batch = targets[:FIX_IMAGES_MAX_PER_RUN]
    deferred = len(targets) - len(batch)
    if deferred:
        print(f"한 번에 최대 {FIX_IMAGES_MAX_PER_RUN}건만 처리합니다. 나머지 {deferred}건은 다음 실행에서 처리합니다.")
    fixed = skipped = 0
    for post, problem in batch:
        new_url = repair(post, used)
        if not new_url:
            print(f"  교체 후보 없음, 건너뜀: {post['path']}")
            skipped += 1
            continue
        print(f"  [{problem}] {post['path']}\n    {post['image'] or '(없음)'}\n    -> {new_url}")
        write_text_atomic(post["path"], apply_image(post["text"], post["image"], new_url))
        trigger_download(new_url)
        fixed += 1
    if DRY_RUN:
        head = f"교체 예정 {len(targets)}건 중 {len(batch)}건 처리 대상"
    else:
        head = f"문제 {len(targets)}건" + (f" 중 {len(batch)}건 처리" if deferred else "")
    summary = (f"완료: {head} / 교체 {fixed}건 / 건너뜀 {skipped}건"
               + (f" / 나머지 {deferred}건은 다음 실행으로 넘김(한 번에 최대 {FIX_IMAGES_MAX_PER_RUN}건)" if deferred else "")
               + (f" (DRY_RUN: 실제 변경 없음, {'가짜 AI 검색어 사용' if STUB_GEMINI else '실제 Gemini 호출'})" if DRY_RUN else ""))
    print(summary)
    return "이미지 점검: " + summary


# ============================================================
# 주제 선정
# ============================================================
def norm_title(s):
    s = re.sub(r"[^\w\s]", " ", (s or "").casefold())
    return re.sub(r"\s+", " ", s).strip()


def similarity(a, b):
    a, b = norm_title(a), norm_title(b)
    if not a or not b:
        return 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    return max(ratio, jac)


def is_similar_to_any(text, existing, threshold):
    return any(similarity(text, e) >= threshold for e in existing)


def existing_titles(history, posts, *, for_ai=True):
    """이력과 글에서 '이미 다룬 제목' 목록(for_ai 는 키워드로만 받는다). 새 글 프롬프트의 최근 제목(titles[-30:])과 그림자 실행이 이 목록을 AI 입력으로 쓴다.
    for_ai=True(기본)는 표식 항목(이력의 `provenance` 칸)과 표식 글(글 사전의 `provenance` 칸)의 제목·주제를 뺀다. for_ai=False 는 사람이 읽는 곳 전용(AI 를 부르는 함수는 쓰지 않는다 — AF6)."""
    titles = []
    for item in history:
        if for_ai and provenance.entry_blocks_ai(item):
            continue
        if isinstance(item, str):
            titles.append(item)
        elif isinstance(item, dict):
            for k in ("topic", "kr_title", "en_title"):
                v = item.get(k)
                if isinstance(v, str) and v.strip():
                    titles.append(v.strip())
    titles += [p["title"] for p in posts if p["title"] and not (for_ai and provenance.post_blocks_ai(p))]
    return titles


def is_tech_title(title):
    low = title.lower()
    return any(k in low for k in TECH_KO) or bool(TECH_EN.search(title))


# 공공기관·개방 라이선스 소스는 주말에 발표가 없어 36시간이면 토·일·월요일 슬롯이 자주 비었다(2026-10-26 조사). 72시간이면 금요일 발표가 월요일 슬롯까지 닿는다.
# 같은 기사를 두 번 쓰지 않는 것은 이력과 제목 유사도 검사가 맡는다.
NEWS_MAX_AGE_HOURS = 72
EPOCH = datetime.datetime.min.replace(tzinfo=timezone.utc)


def _int_env(name, default):
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


# 뽑힌 분야에 후보가 없을 때 다음 분야를 시도하는 총 시간 상한(초). 이 시각이 지나면 새 분야도, 분야 안의 남은 소스도
# 시도하지 않는다. 이미 시작한 소스 하나는 끝까지 기다리므로(소스당 최악 약 2분) 수집은 상한 + 약 2분 안에 끝난다.
LANE_SEARCH_BUDGET_SECONDS = _int_env("LANE_SEARCH_BUDGET_SECONDS", 480)

# 분야 추첨 순서의 시드에 더하는 '실행 시각 구간'의 길이(분). 시드가 날짜·슬롯·이력 길이·마지막 이력뿐이면 같은 날 같은 슬롯의 모든 실행이 같은 분야 순서·같은 후보로 같은 실패를 되풀이했다
# (D-34, 2026-11-04 진단: 11-04 9시 슬롯의 10:24·12:19 실행이 같은 후보 한 건에서 막힘). 구간이 다르면 순서가 달라진다. 분야별 가중치(최근 발행 편중)는 이력만 보므로 같은 분야가 연속되지 않게 하는
# 균형은 그대로다. 정기 실행은 매시 17·47분이고 GitHub 지연으로 간격이 15분~7.6시간이라(진단) 10분 구간이면 서로 다른 실행이 같은 구간에 들 일이 거의 없다. 0 이면 시각 항목을 쓰지 않는다(옛 시드).
LANE_ORDER_BUCKET_MINUTES = 10


def _lane_order_bucket(now):
    """시드 뒤에 붙는 실행 시각 구간 표지('|<하루 안의 구간 번호>'). LANE_ORDER_BUCKET_MINUTES 가 0 이하이면 빈 문자열(옛 시드)."""
    if LANE_ORDER_BUCKET_MINUTES <= 0:
        return ""
    return f"|{(now.hour * 60 + now.minute) // LANE_ORDER_BUCKET_MINUTES}"

# 기사 탈락 사유 코드. 소스별 줄·[SKIP] 줄·실행 요약에 같은 코드로 남는다(docs/ARCHITECTURE.md).
DROP_LABELS = {
    "NO_TITLE": "제목 없음",
    "NOT_TECH": "기술 키워드 아님",
    "EXCLUDED": "소스별 제외 규칙(약관·글감 부적합)",
    "OFF_TOPIC": "이 분야 주제어와 맞지 않음",
    "AGE": f"{NEWS_MAX_AGE_HOURS}시간 초과",
    "UNTRUSTED": "신뢰 목록에 없는 게시자",
    "UNCHECKED": "소스당 5건 검사 한도 초과",
    "UNRESOLVED": "게시자 원문 주소 해석 실패",
    "HOST_MISMATCH": "게시자와 원문 주소 불일치",
    "SHORT_SUMMARY": "요약 100자 미만",
    "DUPLICATE": "기존 글과 제목 유사",
}


def _count(counter, code, n=1):
    counter[code] = counter.get(code, 0) + n


def _format_drops(drops):
    """사유별 개수를 많은 순으로 'UNTRUSTED 60, AGE 11' 형태로."""
    return ", ".join(f"{code} {n}" for code, n in
                     sorted(drops.items(), key=lambda kv: (-kv[1], kv[0])))


def _one_line(text, limit=300):
    """한 줄로 접는다(개행 제거, 길이 제한). 외부·AI 유래 문구를 로그에 찍기 전에 쓴다:
    개행으로 새 줄을 시작해 '::error::' 같은 워크플로 명령을 흉내 내거나 '##[' 를 쓰지 못하게 한다."""
    folded = " ".join(str(text).split()).replace("##[", "# [")
    if folded.startswith("::"):
        folded = "→ " + folded  # 러너는 줄 앞 공백을 지우고 '::' 를 찾으므로 공백이 아니라 눈에 보이는 접두 문자로 막는다
    return folded[:limit]


def _md_cell(text, limit=120):
    """마크다운 표·목록에 안전하게 넣을 한 줄 텍스트(제목·출처처럼 AI·외부에서 온 문구용)."""
    folded = _one_line(text, limit)
    for ch, entity in (("|", "&#124;"), ("`", "'"), ("<", "&lt;"), (">", "&gt;"), ("[", "&#91;"), ("]", "&#93;")):
        folded = folded.replace(ch, entity)
    return folded


_URL_QUERY = re.compile(r"(https?://[^\s?#]*)[?#]\S*")


def _public_text(text, limit):
    """공개 주석·실행 요약에 싣는 모델·피드 유래 글(F): ① 비밀 모양(키·토큰)과 이 실행의 키를 먼저 가리고(_scrub) ② URL 의 질의·조각(?…·#…)을 떼고 ③ 한 줄로 접은(_one_line: 개행 제거,
    '::'·'##[' 무력화) 뒤 ④ 앞 limit 자만 남긴다. 가린 뒤에 자른다 — 자르고 가리면 잘린 키 조각이 비밀 패턴에 걸리지 않아 그대로 남는다."""
    return _one_line(_URL_QUERY.sub(r"\1", _scrub(text)), limit)


# SHADOW_RUN 값: 켜짐으로 읽는 값과 꺼짐으로 읽는 값(앞뒤 공백·대소문자 무시). 둘 어느 쪽도 아닌 값(오타·`2`·`garbage`)은 main() 이 실행을 거절한다(종료 2) — 모르는 값을 '꺼짐'으로
# 읽으면 정지가 풀린 상태에서 일반(쓰기) 실행으로 내려가기 때문이다. 켜짐 집합은 PIPELINE_PAUSE(_pause_on)의 1·true·yes·on 을 포함한다.
SHADOW_RUN_ON_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})
SHADOW_RUN_OFF_VALUES = frozenset({"", "0", "false", "no", "off", "disabled"})


def _shadow_value():
    return os.environ.get("SHADOW_RUN", "").strip().lower()


def shadow_run_on():
    """그림자 실행(환경 변수 SHADOW_RUN 이 1·true·yes·on·enabled)인가. 이 모드는 읽기 전용이다: 저장소 파일·git·gh 에 어떤 쓰기도 하지 않고(write_text_atomic 등을 코드로 막는다)
    후보 글과 보류 사유를 SHADOW_OUT 아래 파일로만 낸다. 호출할 때마다 환경 변수를 읽는다 — 이 변수가 없으면 이전과 동작이 같다."""
    return _shadow_value() in SHADOW_RUN_ON_VALUES


def shadow_run_unrecognized():
    """SHADOW_RUN 에 값이 있는데 켜짐·꺼짐 어느 쪽으로도 읽을 수 없는가(오타·모르는 값)."""
    value = _shadow_value()
    return value not in SHADOW_RUN_ON_VALUES and value not in SHADOW_RUN_OFF_VALUES


def _pause_on():
    """킬 스위치. Blogger 러너(pipeline/run.py)와 같은 값 집합(1/true/yes/on)을 쓴다.
    그림자 실행(SHADOW_RUN=1)은 읽기 전용이라 이 검사를 건너뛴다 — 정지 변수는 건드리지 않고, 건너뛰는 것은 이 모드 안에서만이다(main() 이 곧바로 읽기 전용 경로로 넘긴다)."""
    if shadow_run_on():
        return False
    return os.environ.get("PIPELINE_PAUSE", "").strip().lower() in {"1", "true", "yes", "on"}


def run_shadow():
    """SHADOW_RUN=1: pipeline/shadow_run.py 가 후보를 읽기 전용으로 만들어 평가하고 SHADOW_OUT 아래에만 결과를 쓴다(저장소·git·gh 쓰기 없음). 규칙·출력 형식은 docs/QUALITY_GATE.md."""
    from pipeline import shadow_run    # 읽기 전용 실행 경로 — 이 모드가 아니면 읽지 않는다
    return shadow_run.run(sys.modules[__name__], os.environ)


def skip_line(code, **fields):
    """건너뜀을 로그에서 한 줄로 찾게 하는 규격: [SKIP] code=CODE key=value ..."""
    parts = [f"[SKIP] code={code}"]
    for key, value in fields.items():
        if isinstance(value, dict):
            value = ",".join(f"{k}:{v}" for k, v in sorted(value.items())) or "-"
        parts.append(f"{key}={value}")
    return " ".join(parts)


def write_step_summary(markdown):
    """Actions 실행 화면의 요약 칸(GITHUB_STEP_SUMMARY)에 덧붙인다. 로컬 실행에서는 아무 일도 하지 않는다.
    요약은 보고용이라 쓰기에 실패해도 발행 결과를 바꾸지 않는다(대신 한 줄을 남긴다)."""
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target or shadow_run_on():
        return
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(markdown.rstrip() + "\n\n")
    except OSError as exc:
        print(f"실행 요약 쓰기 실패(발행에는 영향 없음): {exc}")

# 기술을 포함하되 한 분야에 고정되지 않도록, 여러 편집 축의 후보를 둡니다.
EDITORIAL_LANES = {
    "science": {
        "label": "과학·환경", "kr_category": "과학·환경",
        "en_category": "Science & Environment",
        "focus": "과학적 발견, 기후·환경, 공중보건과 그것이 사람과 지역사회에 미치는 변화",
    },
    "economy": {
        "label": "경제·일", "kr_category": "경제·일",
        "en_category": "Economy & Work",
        "focus": "경제, 산업, 소비, 주거, 노동과 일의 변화",
    },
    "society": {
        "label": "사회·정책", "kr_category": "사회·정책",
        "en_category": "Society & Policy",
        "focus": "사회 변화, 공공정책, 교육, 노동권과 공동체",
    },
    "technology": {
        "label": "기술·미래", "kr_category": "기술·미래",
        "en_category": "Technology & Future",
        "focus": "인공지능, 디지털 서비스, 하드웨어, 우주와 신기술",
    },
    "culture": {
        "label": "문화·미디어", "kr_category": "문화·미디어",
        "en_category": "Culture & Media",
        "focus": "문화, 대중매체, 게임, 창작과 콘텐츠 산업",
    },
    "daily_life": {
        "label": "일상·마음", "kr_category": "일상·마음",
        "en_category": "Everyday Life",
        "focus": "일상생활, 심리, 건강, 가족, 도시와 사람들이 매일 겪는 변화",
    },
}

# 소스는 실패해도 건너뛰기만 합니다. 로그의 '소스 ...: N건' 줄로 동작 여부를 확인하고,
# 계속 0건/실패인 소스는 이 목록에서 지우세요. (직접 RSS 주소는 사이트 사정으로 바뀔 수 있음)
#
# 약관 점검(terms): 소스마다 공식 약관·이용 안내를 읽은 결과를 적는다(법률 판단이 아니다).
#   allowed    출처를 밝히고 요약해 새 글을 쓰는 이 용도가 허용된다고 읽은 소스. 확인한 날짜와 근거 쪽 주소를 함께 적는다.
#   pending    약관은 허용하지만 아직 채우지 못한 조건(blocker)이 있어 읽지 않고 건너뛴다(로그에 이유가 한 줄 남는다). 조건을 채우고 운영자가 확인하면 allowed 로 바꾼다.
#   unverified 아직 약관을 읽지 못했거나 허용인지 금지인지 불명확한 기존 소스(유예). 지금은 쓰는 소스가 없다(마지막이던 전자신문을 2026-10-26에 뺐다). 새로 늘릴 수 없다(tests/test_generator_slots.py SourceListTest).
# 이 용도를 금지·허가 필요로 읽은 매체(BBC·Guardian·Nature·MIT Technology Review·AI타임스)와 robots.txt 로 AI 크롤러를 막아 운영자가 접근하지 않기로 한
# 매체(Ars Technica·IEEE)는 TERMS_BLOCKED_DOMAINS 로 막고
# 소스에도 신뢰 목록에도 두지 않는다. 전자신문은 콘텐츠 이용에 정식 계약·사용료가 필요해 운영자 결정(2026-10-26 "무료 자동화 기반" 취지에 맞지 않음)으로 같은 목록에 올렸다.
#
# 소스별 선택 키(모두 생략 가능):
#   exclude_title  제목이 이 정규식과 맞으면 쓰지 않는다(EXCLUDED). 약관이 빼라고 한 것, 글감이 못 되는 공지·퀴즈 등.
#   exclude_link   기사 주소가 이 정규식과 맞으면 쓰지 않는다(EXCLUDED). 글 종류가 주소 경로에 드러나는 피드(뉴스레터 모음, 사진 설명 쪽).
#   exclude_tags   피드 분류 태그 중 하나가 이 정규식과 맞으면 쓰지 않는다(EXCLUDED).
#   topic_regex    제목·분류 태그에 이 정규식과 맞는 말이 없으면 쓰지 않는다(OFF_TOPIC). 여러 주제가 섞인 피드를 분야에 맞춘다.
#   no_page_fetch  요약이 짧아도 기사 페이지를 따로 읽지 않는다(자동 수집을 막는 약관).
#   notice         글 끝에 붙일 고지문(ko·en). 소스 약관이 요구하는 'AI 작성, 검토·승인 받지 않음' 안내.
#   citation       글 끝에 붙일 인용 한 줄의 틀({title}·{date}·{url}). 소스 약관이 정한 인용 형식(Pew).
#   prompt_rule    글 작성 지침에 한 줄 더하는 소스별 약관 조건(요약에 없는 것을 채우지 않는 소스와 무관한 규칙은 GROUNDING_RULES 한 곳에 둔다).
#   display_name   글에 보이는 출처 이름(생략하면 name). 한 게시자의 피드를 분야별로 나눠 읽을 때 name 은 달라야 해서 둔다.
#   page_delay     기사 페이지를 연달아 읽을 때 사이에 기다릴 초(사이트의 Crawl-delay 를 지킨다).
#   summary_max_chars  이 소스의 피드 요약을 모델에 넘기는 최대 글자 수(생략하면 SUMMARY_MAX_CHARS). 소스의 약관이 더 짧은 발췌만 허락하거나, 요약이 보도자료 전문이라 원문 문장을 베끼지 않게 줄이고 싶을 때 그 값을 적는다
#                      (지금 쓰는 소스는 미 FTC 보도자료 하나다 — 약관 때문이 아니라 전문 수준의 요약을 베끼지 않게).
# 해외(미국 외) 소스의 공통 약관 조건(2026-10-26, 조사 보고서 R1·R2에서 약관·robots.txt·피드를 직접 읽어 확인).
#
# 유럽연합 집행위원회 계열: 법적 고지(https://commission.europa.eu/legal-notice_en)는 "달리 표시하지 않은 한 CC BY 4.0이며 적절한 출처 표시와
# 변경 사실 표시를 조건으로 재사용을 허용한다"고 하고, 사람 얼굴이 나오는 자료·제3자 자료·로고·상표는 제외한다(그래서 글만 쓰고 이미지는 쓰지 않는다).
# Energy·Environment·JRC·디지털 전략 사이트는 바닥글이 같은 고지로 연결되고 robots.txt 에 AI 크롤러 제한이 없다. Eurostat 소식은 Eurostat 자체
# 고지(출처 표기·면책 문구 별도)가 있어 `exclude_link` 로 뺀다. 피드에 섞여 드는 EIB·ACER 기사는 이 고지의 대상이 아니라 신뢰 목록에 없는 주소라 떨어진다.
_EC_TERMS = {"status": "allowed", "checked": "2026-10-26", "url": "https://commission.europa.eu/legal-notice_en"}
_CC_BY = "https://creativecommons.org/licenses/by/4.0/"
_EC_NOTICE = {
    "ko": "이 글은 AI 도구가 유럽연합 집행위원회(European Commission)가 공개한 자료를 요약·재구성해 작성했으며 원문에서 바뀐 부분이 있습니다. "
          "원문은 CC BY 4.0 라이선스(" + _CC_BY + "deed.ko)로 제공됩니다. 집행위원회는 이 글을 검토하거나 보증하지 않았습니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published by the European Commission; changes were made to the original. "
          "The original is licensed under CC BY 4.0 (" + _CC_BY + "). The European Commission has not reviewed or endorsed this article."}
# 건강·의료 주제의 안전 지침(Chance 의 일상·마음 분야와 건강 관련 정책·통계 글). 통계·정책 사실만 전하고 의학적 조언은 하지 않는다("의심스러우면 게시하지 않는다").
HEALTH_RULE = "건강·의료 정보는 정책과 통계 사실만 전하고 진단·치료·복용·예방 효과를 조언하지 마세요."
# 글 근거 보강(D-77): 검증된 출처가 있는 모든 글감의 작성 지침에 소스와 상관없이 붙는 공통 규칙(build_post_prompt 가 소스별 규칙 앞에 넣는다).
# 소스별 `prompt_rule` 은 그 소스의 약관 조건(보증 암시 금지·링크 글자 등)과 고유한 구분만 담고, '요약에 없는 것을 채우지 않는다'는 규칙은 여기 한 곳에 둔다
# (예전에는 집행위원회·GOV.UK·통계청 규칙이 같은 말을 따로 적었다). 2026-10-27 9시 슬롯 글(DG Energy)이 요약 한 문장(194자)만 받고 약 5,000자를 쓰면서 원문에 없는
# 원화 환산과 평가 기준·절차 서술을 채웠다. 원문 발췌를 읽을지는 운영자 결정이라 수집 방식은 그대로 두고 지침으로만 막는다.
GROUNDING_RULES = (
    "독자를 위한 것이라도 통화·단위를 환산하거나 숫자를 반올림·추정하지 마세요(예: 유로를 원화로, 마일을 킬로미터로 바꾸지 마세요). 요약에 적힌 수치·단위·기준 시점을 그대로 쓰세요.",
    "요약에 없는 평가 기준·심사 절차·일정·시행 시기·금액·예산 대비 배수·참여 국가 수·법적 효력은 쓰지 마세요. "
    "배경 설명이 필요하면 '일반적으로 …'처럼 출처에 없는 일반론임을 드러내고, 구체적인 수치·고유명사는 지어내지 마세요.",
    "출처에 없는 내용(원인·전망·절차 등)을 출처 기관이 말하거나 밝힌 것, 하기로 한 일처럼 쓰지 마세요.",
)
_EC_PROMPT_RULE = ("집행위원회의 제안·협의·계획과 이미 확정된 법·결정을 구분하세요. "
                   "원문의 의미를 왜곡하지 말고, 집행위원회가 이 글을 검토하거나 보증한 것처럼 쓰지 마세요. " + HEALTH_RULE)
# 집행위원회 피드에서 뺄 기사 주소: Eurostat 소식(Eurostat 자체 고지가 따로 있음), Horizon 매거진 기사(2026-10-26 검증이 DG Environment 피드에 섞여 드는 것을 찾음),
# Press Corner 보도자료(ec.europa.eu/commission/presscorner — 앱 바닥글에 법적 고지·라이선스 링크가 없어 재사용 조건을 확인하지 못했다. 불명확은 유예한다).
# Horizon 은 재게시에 원 기자 이름·원문 링크·바닥글 문구를 요구하는데 피드의 기자 이름(dc:creator)을 아직 읽지 않아 지킬 수 없다.
_EC_EXCLUDE_LINK = r"/eurostat/|/horizon-magazine/|/commission/presscorner/"
# 연설·성명·공동 선언·기자회견 발언은 글감이 못 된다(집행위원회 소스 전부).
_EC_EXCLUDE_STATEMENTS = (r"^(?:joint )?statements?\b|^speech(?:es)?\b|\b(?:opening |closing )?remarks\b|\bleaders[’']? (?:joint )?statement\b"
                          r"|\bjoint declaration\b|\bdeclaration (?:on|by|from)\b|\bjoint press conference\b")
# 위원·부위원장 방문 예고("Commissioner Jørgensen in Hungary to …", "Executive Vice-President Ribera visits …")와 홍보성 신청 안내("Apply now…", "Turning 18? Apply for …")도 글감이 못 된다.
# 제목 가운데의 "must apply for authorisation" 같은 정책 기사는 살린다.
_EC_EXCLUDE_VISITS = r"^(?:(?:executive )?vice-president|commissioner) [\w’'-]+(?: [\w’'-]+)? (?:in|visits?|meets?|travels?|to (?:visit|meet|address))\b"
_EC_EXCLUDE_APPLY = r"\bapply now\b|(?:^|[?:!.] )apply for\b"


def _ec_citation(creator):
    """CC BY 4.0 출처 표시 한 줄: 제목·게시 기관·날짜·원문 주소·저작권 표시·라이선스 링크. {title}·{date}·{url} 은 글을 쓸 때 채운다."""
    return "“{title}.” " + creator + ", {date} <{url}>. © European Union, licensed under CC BY 4.0 (" + _CC_BY + ")."


# Statistics Canada Open Licence(https://www.statcan.gc.ca/en/terms-conditions/open-licence): 상업 이용·재가공(Value-added Products)을 허용하고,
# 재가공물에는 "Adapted from Statistics Canada, <상품명>, <기준일>. This does not constitute an endorsement by Statistics Canada of this product."(코드는 상품명 자리에 피드 제목을, 기준일 자리에 발표일을 채운다)
# 문구를 넣으라고 한다. 정보를 정확히 옮기고(reproduce accurately) 통계청이 보증하는 것처럼 보이게 하지 말며 통계청 이름·로고·문장(紋章)·기타 상징·도메인 이름을 서면 허가 없이 쓰지 말라는 조건("Advertising and Publicity")이 있다.
# 약관에 출처 표기 예외 문구는 없다 — 필수 출처 문구가 통계청 이름을 쓰게 하므로 이름은 출처를 밝히는 용도(필수 문구·고지문·'통계청 발표' 링크 글자·출처 목록)로만 쓰고 제목·홍보 문구에는 쓰지 않는다는 것은 이 코드의 해석이다(2026-10-26 약관 검증 지적).
# 피드 하나(The Daily 전체 주제)를 분야별 주제어로 나눠 세 소스로 읽는다. 항목 제목이 Atom type="xhtml"이라 parse_feed 가 자식 요소까지 읽는다.
_STATCAN_FEED = "https://www150.statcan.gc.ca/n1/rss/dai-quo/0-eng.atom"
_STATCAN_TERMS = {"status": "allowed", "checked": "2026-10-26", "url": "https://www.statcan.gc.ca/en/terms-conditions/open-licence"}
_STATCAN_CITATION = "Adapted from Statistics Canada, {title}, {date}. This does not constitute an endorsement by Statistics Canada of this product."
_STATCAN_NOTICE = {
    "ko": "이 글은 AI 도구가 캐나다 통계청(Statistics Canada)이 발표한 자료를 바탕으로 재구성해 작성했습니다. 통계청은 이 글을 검토하거나 보증하지 않았으며, 수치와 기준 시점은 통계청의 발표를 따릅니다.",
    "en": "This article was written with an AI tool, adapting information published by Statistics Canada. Statistics Canada has not reviewed or endorsed it; figures and reference periods follow Statistics Canada's release."}
_STATCAN_PROMPT_RULE = ("통계청 발표 요약의 수치·단위·기준 시점(월·분기·연도)을 그대로 쓰세요. "
                        "통계청이 이 글을 보증하는 것처럼 쓰지 마세요. 원문 링크의 글자는 '통계청 발표'처럼 설명 문구로 쓰고 주소(statcan.gc.ca)를 글자로 보이게 쓰지 마세요. " + HEALTH_RULE)
# 통계청 사이트 robots.txt 의 Crawl-delay: 2 를 지켜, 기사 페이지를 연달아 읽을 때 사이에 이만큼(초) 기다린다.
_STATCAN_PAGE_DELAY = 2
# 글감이 못 되는 발표(통계 상품 안내·부문별 물가지수·공급 처리표·원자료 모음)와, 자동으로 다시 쓰기에는 민감한 주제(자살·약물 과다복용·마약성 진통제·성폭력·살인·가정·친밀한 관계·성별 기반 폭력·아동 학대)는 쓰지 않는다.
# 소비자물가지수·신규주택가격지수는 글감이라 살린다.
_STATCAN_EXCLUDE = (
    r"(?<!consumer )(?<!housing )\bprice index(?:es)?\b|\bsupply and disposition\b|\bproduction survey\b|\bdata availability\b|\bannouncement\b"
    r"|\bstorage survey\b|\bfuel consumption\b|\bgenerating stations?\b|\bsawmills?\b|\bpost-production\b|\bcredit aggregates\b"
    r"|\binteractive dashboard\b|\bopen database\b|\bdrinking water\b|\bmapping services\b"
    r"|\bsuicid|\boverdose|\bopioid|\bstimulant|\bself-harm|\bsexual (?:assault|behaviou?rs)|\bhomicide"
    r"|\b(?:family|domestic|intimate partner|gender-based) violence\b|\bchild (?:abuse|maltreatment)\b|\bviolent victimi[sz]ation\b")
_STATCAN_ECONOMY = (
    r"consumer price index|labour force survey|retail trade|wholesale trade|gross domestic product|merchandise trade|trade in services"
    r"|employment insurance|job vacanc|payroll|earnings|new housing price index|building permits|monthly survey of manufacturing"
    r"|new motor vehicle sales|travel between canada|international arrivals|business openings|economic contribution"
    r"|household (?:debt|spending|savings|income)|survey of household spending|productivity|cost of living|food (?:price|insecurity)"
    r"|labour market|workforce|\bGDP\b|cybercrime on canadian businesses|housing starts")
_STATCAN_SOCIETY = (
    r"education|graduat|enrolment|postsecondary|student|crime|victimi[sz]ation|police|court|sentenc|indigenous|immigra|newcomer"
    r"|official language|religio|population|census|gender|women|2SLGBTQ|disabilit|youth|children|famil(?:y|ies)"
    r"|older adults|seniors|housing affordability|housing stress|homeless|poverty|inequality|volunteer")
_STATCAN_LIFE = (
    r"health|mental|well-?being|quality of life|sleep|physical activity|nutrition|obesity|chronic|life expectancy|mortality"
    r"|time use|loneliness|social connection|leisure|\bbirths?\b|fertility|baby names|\bdeaths?\b|marriage|divorce")

# 영국 정부(GOV.UK): "GOV.UK 의 대부분의 내용은 왕실 저작권 아래 Open Government Licence(OGL)로 공개된다"(이용약관 https://www.gov.uk/help/terms-conditions, 2024-09-03판 —
# 약관은 버전을 적지 않고, v3.0 이라는 근거는 모든 페이지 바닥글이다. 바닥글은 "달리 표시한 경우는 제외"라고 해서 개별 항목의 별도 표시는 코드가 가려내지 못한다).
# OGL v3.0(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)은 복제·재가공·상업 이용을 허용하고, 조건은 출처 표시 —
# 정보 제공자가 정한 문구가 없으면 "Contains public sector information licensed under the Open Government Licence v3.0." — 와 제공자가 이 이용을 보증하거나
# 공식 지위가 있는 것처럼 보이게 하지 않는 것(Non-endorsement)이다. 개인정보·제3자 권리·로고·왕실 문장은 이 허락의 대상이 아니다. 이용약관에 AI·텍스트 마이닝 조항은 없고, GOV.UK robots.txt 는 AI 크롤러로
# meta-externalagent 를 `/search/all*` 에만 막는다(우리가 읽는 `/search/news-and-communications.atom` 경로가 아니다). 운영자가 이 소스를 쓰기로 결정했다
# (2026-10-26 채팅 "AI 학습을 위한 목적이 아니기에 문제가 없을것으로 보여져"). 피드는 20건이 한도이고 항목 날짜(updated)는 마지막 수정 시각이라 고친 글이 새 글처럼 보일 수 있다 —
# 같은 글을 두 번 쓰지 않는 것은 이력·제목 유사도 검사가 맡는다.
# 피드 요약이 한두 문장이고 기사 페이지의 메타 설명이 그 요약과 같아서(docs/analysis/2026-10-26_overseas-sources.md) 페이지를 따로 읽지 않는다(no_page_fetch): 100자 미만 요약은 SHORT_SUMMARY 로 떨어진다.
_OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
_GOVUK_TERMS = {"status": "allowed", "checked": "2026-10-26", "url": "https://www.gov.uk/help/terms-conditions"}
_GOVUK_CITATION = ("“{title}.” GOV.UK, {date} <{url}>. Contains public sector information licensed under the Open Government Licence v3.0. (" + _OGL_URL + ")")
_GOVUK_NOTICE = {
    "ko": "이 글은 AI 도구가 영국 정부(GOV.UK)가 공개한 자료를 요약·재구성해 작성했으며 원문에서 바뀐 부분이 있습니다. "
          "원문은 Open Government Licence v3.0으로 제공됩니다(Contains public sector information licensed under the Open Government Licence v3.0.). "
          "영국 정부와 해당 부처는 이 글을 검토하거나 보증하지 않았으며, 이 글은 영국 정부의 공식 입장이나 공식 문서가 아닙니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published on GOV.UK; changes were made to the original. "
          "Contains public sector information licensed under the Open Government Licence v3.0. (" + _OGL_URL + ") "
          "The UK Government and the departments concerned have not reviewed or endorsed this article, and it is not an official government publication or position."}
_GOVUK_PROMPT_RULE = ("영국 정부(부처)가 발표한 내용임을 분명히 하고, 정부의 계획·주장과 확인된 사실을 구분하세요. "
                      "정당·선거·장관 개인에 대한 평가는 쓰지 말고, 영국 정부나 해당 부처가 이 글을 검토·보증했거나 정부의 공식 입장·문서인 것처럼 쓰지 마세요. " + HEALTH_RULE)
_GOVUK_FEED = "https://www.gov.uk/search/news-and-communications.atom?"
_GOVUK_ENV_FEED = (_GOVUK_FEED + "organisations%5B%5D=department-for-energy-security-and-net-zero"
                   "&organisations%5B%5D=department-for-environment-food-rural-affairs")
_GOVUK_TECH_FEED = (_GOVUK_FEED + "organisations%5B%5D=ai-security-institute"
                    "&organisations%5B%5D=department-for-science-innovation-and-technology")
# '뉴스와 알림' 피드에는 연설(/speeches/)·정책 문서와 편지(/publications/)·사례 소개(/case-studies/)도 섞여 든다. 보도 기사(/government/news/)만 쓴다.
_GOVUK_EXCLUDE_LINK = r"^(?!https://www\.gov\.uk/government/news/)"
# 인사·위촉 소식(진료 "appointments" 같은 평범한 낱말은 살린다), 신청·의견 모집 안내, 공동 성명·조의 표명, 선거·전쟁·군사·분쟁 소재와 자동으로 다시 쓰기에는 민감한 주제
# (자살·자해·성폭력·아동 성착취·학대·극단주의·테러)는 쓰지 않는다. "defence" 는 사이버 방어 소식이 있어 넣지 않았다.
_GOVUK_EXCLUDE_TITLE = (
    r"\bappoints?\b|\bappointed\b|\bappointments? (?:to|of|as)\b|\breappoint|\bchair recruitment\b|\bnew (?:chair|chief executive)\b|\bsteps? down\b"
    r"|\bapply now\b|(?:^|[?:!.] )apply for\b|\bopens? for applications\b|\bapplications? (?:are )?(?:now )?open\b|\bcall for (?:evidence|views|input|applications)\b"
    r"|\bjoint statement\b|\bstatement (?:from|by|on)\b|\bcondolences\b"
    r"|\belections?\b|\bpolitical parties\b"
    r"|\b(?:military|weapons?|warfare|missiles?|armed forces|ukraine|gaza|russia|iran(?:ian)?|israel|middle east|nato|sanctions?)\b"
    r"|\bsuicid|\bself-harm|\bsexual (?:abuse|exploitation|assault|violence)\b|\bchild (?:sexual|abuse)\b|\bdomestic abuse\b|\bviolence against women\b"
    r"|\bextremis|\bradicali[sz]|\bterror")

# R-119 A(2026-11-05, 결정 요청 R-119 의 기본값 A=1 — 답이 없으면 기본값으로 진행하고 병합이 곧 승인: Chance 글감 소스 1차 6곳). 2026-11-04 조사(docs/analysis/chance-stall-2026-11-04/)에서 공식 기관 피드가 느리고 얇아 후보 풀이 말랐던
# 분야(경제·일·기술·미래·사회·정책)에 미 FTC 보도자료·연준 FEDS Notes·집행위 R&I·집행위 EMPL·미 NSF 뉴스·영국 CMA 를 더한다. 아래 약관 풀이는 2026-11-04 에 사이트 약관·robots.txt 를 읽은 기록이다
# (키워드가 든 문장을 추려 읽은 것이라 법률 판단이 아니다. 이번 구현에서는 다시 읽지 않고 피드만 한 번씩 읽어 모양을 확인했다). 6곳 모두 목록 끝에 붙여 기존 소스의 순서·동작은 그대로이고,
# 기사 페이지를 읽지 않으며(no_page_fetch) 한 번의 수집에서 소스당 요청은 피드 한 번뿐이다. 소스를 이 6곳 밖으로 넓히려면 따로 운영자 승인을 받는다.
#
# 미 FTC 보도자료(소비자 보호) — 약관 https://www.ftc.gov/policy-notices/website-policy: 사이트 자료 대부분이 연방 정부 저작물이라 공공영역(저작권 제한 없음)이고 가능하면 출처를 밝히라고 한다
# (형식 예: "Source: United States Federal Trade Commission, www.ftc.gov"). 기만적 사용은 금지, FTC 의 보증·제휴를 암시하면 안 되며 제3자 저작물(사진·공개 의견)은 따로 허락이 필요하다(글만 쓰고 이미지는 쓰지 않는다).
# robots.txt 는 Crawl-delay 5초만 두고 AI 크롤러 제한이 없다. 보도자료 요약이 전문 수준(중앙 3,520자)이라 summary_max_chars 로 모델에 넘기는 양을 줄이고 문장을 옮기지 말라는 지침을 더한다.
# 소송·조치는 확정 판결이 아니라 FTC 의 '주장'일 수 있어 구분하게 한다.
_FTC_TERMS = {"status": "allowed", "checked": "2026-11-04", "url": "https://www.ftc.gov/policy-notices/website-policy"}
_FTC_CITATION = "“{title}.” Source: United States Federal Trade Commission, www.ftc.gov, {date} <{url}>"
_FTC_NOTICE = {
    "ko": "이 글은 AI 도구가 미국 연방거래위원회(FTC)가 공개한 자료를 요약·재구성해 작성했습니다. FTC는 이 글을 검토하거나 보증하지 않았으며, 이 글은 FTC의 공식 입장이나 공식 문서가 아닙니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published by the U.S. Federal Trade Commission. The FTC has not reviewed or endorsed it, and it is not an official FTC publication or position."}
_FTC_PROMPT_RULE = ("FTC가 제기한 소송·조치와 업체의 해명·합의를 구분하세요. 법원이 확정하기 전의 내용은 'FTC는 …라고 주장했다'(영어 글은 'the FTC alleges')처럼 주장으로 쓰고, "
                    "특정 업체나 사람을 단정적으로 비난하지 마세요. 독자에게 법률·금융 조언을 하지 말고, FTC가 이 글을 검토·보증했거나 FTC의 공식 입장인 것처럼 쓰지 마세요. "
                    "보도자료 문장을 그대로 옮기지 말고 사건의 핵심을 자기 말로 정리하며, 위원·직원이 한 말을 따옴표로 옮겨 쓰지 마세요. "
                    "요약 앞머리의 'By BCP Staff'는 글쓴이 표기이니 글에 쓰지 마세요. " + HEALTH_RULE)
# 독자 글감이 못 되는 공지: 의견 모집·기한 연장·정책 철회·위원 성명·최종 명령 승인·연도별 수수료 안내
_FTC_EXCLUDE_TITLE = (r"\b(?:extends?|seeks?) (?:the )?(?:public )?comments?\b|\bwithdraws?\b|\bcommissioner\b|\bchairman\b"
                      r"|\bstatement (?:from|by|of|on)\b|\bapproves? final\b|\bannounces? 20\d\d\b.*\bfees\b")
_FTC_SUMMARY_MAX_CHARS = 1500

# 연준 FEDS Notes — 연준 이사회 연구진이 쓰는 짧은 분석 글. 약관은 기존 Federal Reserve 소스와 같은 이사회 사이트 고지(https://www.federalreserve.gov/disclaimer.htm: 달리 표시하지 않은 이사회 사이트 정보는
# 공공영역이라 허락 없이 복사·배포할 수 있고, 인장·로고·제3자 저작물은 제외)다. robots.txt 는 없다(404). 노트의 분석과 결론은 저자의 것이고 연준·이사회의 입장이 아니라는 점을 고지문과 지침에 분명히 한다.
_FEDS_TERMS = {"status": "allowed", "checked": "2026-11-04", "url": "https://www.federalreserve.gov/disclaimer.htm"}
_FEDS_CITATION = "“{title}.” FEDS Notes, Board of Governors of the Federal Reserve System, {date} <{url}>"
_FEDS_NOTICE = {
    "ko": "이 글은 AI 도구가 미국 연방준비제도 이사회 연구진이 공개한 FEDS Notes를 참고해 작성했습니다. 노트의 분석과 결론은 저자의 것이며 연준이나 이사회의 공식 입장이 아니고, 이사회는 이 글을 검토하거나 승인하지 않았습니다.",
    "en": "This article was written with an AI tool using FEDS Notes published by staff of the Federal Reserve Board. The analysis and conclusions are the authors' own and do not represent the Board or the Federal Reserve; the Board has not reviewed or approved this article."}
_FEDS_PROMPT_RULE = ("FEDS Notes는 연준 연구진의 분석 글이라 연준이나 이사회의 입장·결정·전망으로 쓰지 마세요('저자들은 …라고 분석했다'처럼 저자의 분석임을 밝히세요). "
                     "피드 요약은 앞머리에 노트 저자들의 이름이 붙어 있으니(예: 'Jane Doe and John Roe Earlier this year, …') 저자로 밝힐 수는 있지만 직함·소속을 덧붙이지 마세요. "
                     "금융 전문 용어는 처음 나올 때 쉬운 말로 풀어 쓰세요. 분석에 쓴 자료·가정·한계와 분석 결과를 구분하고, 독자에게 투자·재테크 조언을 하지 마세요.")

# 미 NSF 뉴스 — 약관 https://www.nsf.gov/policies/digital: NSF 가 만든 글은 정부 직원 저작물이라 자유롭게 복사할 수 있고 출처 크레딧은 선택이다. 이미지·그래픽은 허가가 필요해 쓰지 않는다(글만 쓴다).
# robots.txt 는 통과(AI 크롤러 제한 없음). 2026-11-05 표본 15건 중 8건이 'Podcast: …' 회차 소개(한두 문장)이고 1건은 공동 성명이라, 글감이 못 되는 이 둘은 제목으로 뺀다 —
# 한 번의 실행이 모델에 보내 보는 후보는 분야를 합쳐 3건이라(MAX_ATTEMPTS) 근거가 없는 후보가 시도를 차지하면 다른 분야의 쓸 만한 후보가 밀린다.
_NSF_EXCLUDE_TITLE = r"^podcast\b|\bstatement\b"
_NSF_TERMS = {"status": "allowed", "checked": "2026-11-04", "url": "https://www.nsf.gov/policies/digital"}
_NSF_CITATION = "“{title}.” Source: U.S. National Science Foundation, {date} <{url}>"
_NSF_NOTICE = {
    "ko": "이 글은 AI 도구가 미국 국립과학재단(NSF)이 공개한 자료를 요약·재구성해 작성했습니다. NSF는 이 글을 검토하거나 보증하지 않았으며, 이 글은 NSF의 공식 입장이 아닙니다. 사진·그래픽은 사용하지 않았습니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published by the U.S. National Science Foundation. NSF has not reviewed or endorsed it, and it is not an official NSF position. No NSF images or graphics are used."}
_NSF_PROMPT_RULE = ("NSF가 지원한 연구라고 해서 NSF가 결과를 보증하거나 이 글을 검토한 것처럼 쓰지 마세요. 연구자의 주장과 확인된 결과를 구분하고, "
                    "소개 글에 나오지 않은 연구자의 발언이나 수치를 지어내지 마세요. " + HEALTH_RULE)

# 집행위 R&I(기술·미래)·EMPL(사회·정책) — 기존 집행위 소스와 같은 약관(`_EC_*`: 법적 고지 CC BY 4.0, 출처·변경 표시)·고지문·지침·제외 규칙을 그대로 쓴다. 두 사이트 바닥글 고지 링크와 robots.txt 는 2026-11-04 조사에서 확인했다
# (`/node/2/rss_en` 허용, AI 크롤러 제한 없음). R&I 는 연구 정책·국제 협력 글이 많아(2026-11-05 표본 30건 중 13건만 기술 주제) 기술·미래 분야 주제어로 거른다 — 조사 초안의 주제어에는 'innovation' 이 있었지만
# 이 피드의 분류 태그에 모든 항목이 'Directorate-General for Research and Innovation' 로 붙어 있어 글자 하나도 거르지 못해서 뺐다. 요약이 얇아(중앙 200자 안팎) 100자 미만은 SHORT_SUMMARY 로 떨어진다.
# EMPL 피드에는 Cedefop(별도 EU 기관) 이 쓴 글이 섞여 든다(표본 30건 중 7건, 분류 태그 'Cedefop'). Cedefop 법적 고지는 요약·번역 같은 가공 허용을 적지 않아 R-119 에서 보류한 곳이라 태그로 뺀다.
# 위원 성명(태그 'Statement')과 행사 안내(태그 'Events')도 글감이 못 되어 같은 태그 규칙으로 뺀다.
_RTD_TOPIC = (r"artificial intelligence|\bAI\b|quantum|fusion|supercomput|semiconductor|\bchips?\b|robot|space|satellite|earth observation|digital|\bdata\b|cyber|cloud|biotech|bioeconomy"
              r"|battery|hydrogen|photonic|open science|research infrastructure")
_EC_EXCLUDE_DG_TITLE = (_EC_EXCLUDE_STATEMENTS + "|" + _EC_EXCLUDE_VISITS + "|" + _EC_EXCLUDE_APPLY
                        + r"|\bcall for (?:applications|tenders|proposals|experts|feedback|evidence)\b|\bwebinar\b|\bpodcast\b")
_EC_EXCLUDE_DG_TAGS = r"^cedefop$|^statements?$|^events?$"

# 영국 경쟁시장청(CMA) — 위 GOV.UK 약관·고지문·제외 규칙(`_GOVUK_*`)을 그대로 쓴다. 이름을 'GOV.UK' 로 시작하지 않는 것은 시험이 GOV.UK 소스를 이름 앞머리로 세기 때문이다.
# 경제·일 분야에 재무부·DWP·DBT 피드(정치 발표가 대부분)를 쓰지 않기로 한 결정(2026-10-26)은 그대로이고, `www.gov.uk` 는 이 CMA 한 곳을 위해서만 경제 분야 신뢰 목록에 들어갔다.
# CMA 는 기업을 조사하는 규제 기관이라 조사 착수·잠정 판단을 확정된 결정과 구분하게 한다.
_CMA_FEED = _GOVUK_FEED + "organisations%5B%5D=competition-and-markets-authority"
_CMA_PROMPT_RULE = (_GOVUK_PROMPT_RULE + " 영국 경쟁시장청(CMA)의 조사 착수·잠정 판단·의견 수렴은 확정된 결정이 아님을 구분하고(영어 글은 'the CMA has provisionally found'처럼), "
                    "특정 기업의 위법을 단정하지 마세요.")

NEWS_SOURCES = [
    # 약관을 확인한 직접 RSS(2026-10-26). 분야마다 약관상 쓸 수 있는 소스만 둔다.
    {"name": "NASA", "lane": "science", "url": "https://www.nasa.gov/feed/",
     "terms": {"status": "allowed", "checked": "2026-10-26",
               "url": "https://www.nasa.gov/nasa-brand-center/images-and-media/"},
     # APOD 는 사진마다 저작권자가 따로 있어 약관 예외이고, 취재진 초대·인증·행사 안내와 사진 설명(image-article)·Glenn 센터 음향 연구실 소개 쪽은 글감이 못 된다(센터 소식 기사는 살린다).
     "exclude_title": r"^APOD\b|\binvites? media\b|\bmedia accreditation\b|\bto (?:host|conduct|answer)\b|\bsets? coverage\b",
     "exclude_link": r"/image-article/|/centers-and-facilities/[^/]+/acoustics-",
     # NASA 의 AI 이용 안내: AI 결과물의 정보를 NASA 에 직접 귀속하는 것은 허용되지 않고, NASA 는 AI 결과물의 정확성에 책임지지 않으며,
     # "AI 도구가 NASA 자료를 포함한다"고 밝히되 NASA 가 검토·허가한 것처럼 암시하지 말라고 한다. 작성 지침 한 줄은 AI가 어길 수 있고(코드로
     # 막으면 후보가 계속 탈락해 호출이 낭비된다, D-63) 고지문은 코드가 붙인다.
     "notice": {"ko": "이 글은 AI 도구가 NASA가 공개한 자료를 참고해 작성했습니다. NASA는 이 글을 검토하거나 승인하지 않았고 내용의 정확성에 책임지지 않으며, 글의 내용은 NASA의 입장이 아닙니다.",
                "en": "This article was written with an AI tool using publicly available NASA source material. NASA has not reviewed or approved it, is not responsible for its accuracy, and it does not represent NASA's position."},
     "prompt_rule": "NASA의 AI 이용 안내에 따라 정보를 NASA가 직접 말하거나 보증한 것처럼 쓰지 마세요. "
                    "'NASA에 따르면'·'NASA는 밝혔다'(영어 글은 'according to NASA'·'NASA said') 같은 직접 귀속 표현을 쓰지 말고 "
                    "'공개된 자료에 따르면'(영어 글은 'according to the published material')처럼 자료를 가리키세요."},
    # 보류(pending): UN News 이용 안내는 출처 표기와 링크만 요구하고 재가공을 환영한다. 그러나 ① 유엔 저작권 안내(un.org/en/about-us/copyright)는
    # 뉴스 자료를 쓸 때 유엔에 알릴 것(the United Nations is advised)을 요구하는데 아직 하지 않았고, ② news.un.org 의 robots.txt 는 일반 봇에
    # 이 피드 경로(`*/news/`)를 허용하지 않는다. 알림과 서면 확인(unnews@un.org)을 마치고 운영자가 확인하면 allowed 로 바꾼다(D-63).
    {"name": "UN News", "lane": "society", "url": "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
     "terms": {"status": "pending", "checked": "2026-10-26",
               "url": "https://www.un.org/en/about-us/copyright",  # 알림 조건이 있는 쪽. 재가공 환영 문구는 https://news.un.org/en/content/navigate-news
               "blocker": "유엔에 이용 사실을 알리고(un.org 저작권 안내) 이 피드 경로를 읽어도 되는지 서면 확인을 받아야 한다(news.un.org robots.txt 가 일반 봇에 */news/ 경로를 허용하지 않음)"},
     # 여러 소식을 묶은 요약 기사는 글감이 못 된다.
     "exclude_title": r"^World News in Brief\b",
     "notice": {"ko": "이 글은 UN News의 보도를 바탕으로 AI 도구가 작성했습니다. 유엔은 이 글을 검토하거나 승인하지 않았으며, 글의 내용은 유엔의 공식 입장이 아닙니다.",
                "en": "This article was written with an AI tool based on reporting by UN News. The United Nations has not reviewed or approved it, and it is not an official UN position."}},
    {"name": "Pew Research Center", "lane": "culture", "url": "https://www.pewresearch.org/feed/",
     "terms": {"status": "allowed", "checked": "2026-10-26",
               "url": "https://www.pewresearch.org/about/terms-and-conditions/"},
     # 퀴즈·보고서 부속 쪽(감사의 글·조사 방법 등)과 선거·정당 이야기는 문화·미디어 글감이 아니다.
     "exclude_title": r"\bquiz\b|^(?:acknowledg(?:e)?ments|methodology|additional charts|appendix)\b"
                      r"|\belection|\bvoters?\b|\bballots?\b|\bmidterms?\b|\btrump\b|\bbiden\b|\brepublican|\bdemocrat|\bpartisan",
     # 뉴스레터 모음(/newsletter/)은 다른 매체 소식을 섞은 요약이라 'Pew 조사 결과'가 아니고, 방법론 연구 글과 선거 분류 글도 문화·미디어 글감이 아니다.
     "exclude_link": r"/newsletter/",
     "exclude_tags": r"methodolog|\belections?\b|\bvoters?\b|\bvoting\b|^political issues$|^donald trump$|^politics & policy$",
     # 피드는 정치·사회·종교 등이 섞여 있어 미디어·온라인·기술 주제만 문화·미디어 분야로 보낸다(제목과 분류 태그에서 찾는다).
     "topic_regex": r"social media|internet|online|\bAI\b|artificial intelligence|chatbot|\bnews\b|tiktok|youtube|instagram"
                    r"|facebook|podcast|streaming|influencer|smartphone|\bmobile\b|video game|gaming|music|movie|\bbooks?\b|\breading\b|digital|journalis|television|platform",
     "no_page_fetch": True,  # Pew 이용약관 §3 은 허가 없는 스크래핑(spidering·scraping)을 막는다. §1 이 허락한 RSS 요약만 쓰고 기사 페이지는 읽지 않는다.
     # Pew 이용약관 §2 의 인용 형식과 §1 의 번역물 면책 문장(아래 ko 고지문의 영어 문장은 약관 원문 그대로).
     "citation": "“{title}.” Pew Research Center, Washington, D.C. ({date}) <{url}>",
     "notice": {"ko": "이 글은 AI 도구가 Pew Research Center가 영어로 발표한 자료를 참고해 새로 쓴 해설입니다. "
                      "Pew Research Center has published the original content in English but has not reviewed or approved this translation. "
                      "(Pew Research Center가 영어 원문을 발표했으며, 이 글의 번역·요약을 검토하거나 승인하지 않았습니다.) 분석과 해석의 책임은 이 사이트에 있습니다.",
                "en": "This article is a new explainer written with an AI tool from findings published by Pew Research Center. The Center has not reviewed or approved it, and responsibility for the analysis and interpretation rests with this site."},
     "prompt_rule": "Pew Research Center의 조사 결과를 전하되, Pew가 특정 정책·정당·견해를 지지하거나 주장하는 것처럼 쓰지 마세요. "
                    "조사 결과와 이 사이트의 해석을 구분하세요."},
    {"name": "Federal Reserve", "lane": "economy", "url": "https://www.federalreserve.gov/feeds/press_all.xml",
     "terms": {"status": "allowed", "checked": "2026-10-26",
               "url": "https://www.federalreserve.gov/disclaimer.htm"},
     # 은행 인수·합병 승인과 제재·이의 없음 통보·공동 판단 건은 한 곳의 사업 사정이라 일반 독자의 글감이 못 된다.
     "exclude_title": r"\benforcement actions?\b|\bapprovals? of (?:the |related )?applications?\b|\bdoes not object\b|\bjoint findings\b",
     "notice": {"ko": "이 글은 AI 도구가 미국 연방준비제도 이사회(Federal Reserve Board)가 공개한 자료를 참고해 작성했습니다. 연준은 이 글을 검토하거나 승인하지 않았습니다.",
                "en": "This article was written with an AI tool using materials published by the Federal Reserve Board. The Board has not reviewed or approved it."}},
    # 해외(미국 외) 소스(2026-10-26 운영자 승인 13·14번 — 약관을 확인한 공식·공공 소스만, 라이선스가 출처 표시와 변경 표시를 조건으로 상업 이용·재가공을 허용한다).
    # 글 끝의 인용 한 줄(citation)과 고지문(notice)은 그 조건을 코드가 붙인다. 위 `_EC_*`·`_STATCAN_*` 상수에 약관 근거를 적었다.
    # 유럽연합 집행위원회 소식: 약 1/4(30건 중 8건)이 국채 입찰 결과·신청 안내라 제외하고, 선거·정치광고·민주주의 방패 글은 중립을 위해 쓰지 않는다(Pew와 같은 원칙).
    {"name": "European Commission", "lane": "society", "url": "https://commission.europa.eu/node/2/rss_en",
     "terms": _EC_TERMS,
     "exclude_title": _EC_EXCLUDE_STATEMENTS + "|" + _EC_EXCLUDE_VISITS + "|" + _EC_EXCLUDE_APPLY
                      + r"|\bauctions?\b|\bEU-(?:Bills?|Bonds?)\b|\bcall for (?:applications|tenders|proposals|experts)\b|\bwebinar\b"
                      r"|\belections?\b|\bpolitical (?:ads?|advertising|parties)\b",
     "exclude_link": _EC_EXCLUDE_LINK,
     "exclude_tags": r"^democracy$|\belections?\b",
     "citation": _ec_citation("European Commission"), "notice": _EC_NOTICE, "prompt_rule": _EC_PROMPT_RULE},
    # DG Energy: 에너지·경제 소식이 주 1~2건이 아니라 평일 거의 매일 나온다. 위원 방문·연설문은 글감이 못 된다. EIB·ACER 기사는 신뢰 목록에 없어 떨어진다.
    {"name": "European Commission · Energy", "display_name": "European Commission (DG Energy)", "lane": "economy",
     "url": "https://energy.ec.europa.eu/node/2/rss_en",
     "terms": _EC_TERMS,
     # 연설·성명·공동 선언은 글감이 못 된다(집행위원회 소스 전부에서 제목으로 뺀다). Press Corner 보도자료는 법적 고지를 확인하지 못해 주소로 뺀다(_EC_EXCLUDE_LINK).
     "exclude_title": _EC_EXCLUDE_STATEMENTS + "|" + _EC_EXCLUDE_VISITS + "|" + _EC_EXCLUDE_APPLY
                      + r"|\bcall for (?:feedback|evidence|applications|tenders|proposals)\b|\bwebinar\b",
     "exclude_link": _EC_EXCLUDE_LINK,
     "citation": _ec_citation("European Commission, DG Energy"), "notice": _EC_NOTICE, "prompt_rule": _EC_PROMPT_RULE},
    {"name": "European Commission · Environment", "display_name": "European Commission (DG Environment)", "lane": "science",
     "url": "https://environment.ec.europa.eu/node/92/rss_en",
     "terms": _EC_TERMS,
     "exclude_title": _EC_EXCLUDE_STATEMENTS + "|" + _EC_EXCLUDE_APPLY + r"|\bcall for (?:applications|tenders|proposals)\b|\bwebinar\b",
     "exclude_link": _EC_EXCLUDE_LINK,
     "citation": _ec_citation("European Commission, DG Environment"), "notice": _EC_NOTICE, "prompt_rule": _EC_PROMPT_RULE},
    # JRC: 요약이 짧은 항목은 기사 페이지의 소개 문구를 읽는다. 국방·안보 분류 글은 쓰지 않는다.
    {"name": "European Commission · JRC", "display_name": "European Commission, Joint Research Centre", "lane": "science",
     "url": "https://joint-research-centre.ec.europa.eu/node/2/rss_en",
     "terms": _EC_TERMS,
     "exclude_title": _EC_EXCLUDE_STATEMENTS,
     "exclude_link": _EC_EXCLUDE_LINK,
     "exclude_tags": r"defen[cs]e|^security and law enforcement$",
     "citation": _ec_citation("European Commission, Joint Research Centre (JRC)"), "notice": _EC_NOTICE, "prompt_rule": _EC_PROMPT_RULE},
    # 디지털 전략(AI Act·디지털서비스법 등): 이 사이트의 법적 고지는 출처 표시 방법을 "작품 제목, 유럽연합 귀속, 원문 주소"로 안내한다.
    # 피드 요약은 "Anonymous (not verified) 날짜"로 시작하는 사이트 잡음이 붙어 있다.
    {"name": "EU Digital Strategy", "display_name": "European Commission (Digital Strategy)", "lane": "technology",
     "url": "https://digital-strategy.ec.europa.eu/en/rss.xml",
     "terms": {"status": "allowed", "checked": "2026-10-26", "url": "https://digital-strategy.ec.europa.eu/en/pages/legal-notice"},
     "exclude_title": _EC_EXCLUDE_STATEMENTS + r"|\bcall for (?:tenders|applications|proposals|experts)\b",
     "exclude_link": _EC_EXCLUDE_LINK,
     "citation": _ec_citation("European Union (European Commission, DG CNECT)"), "notice": _EC_NOTICE,
     "prompt_rule": _EC_PROMPT_RULE + " 요약 앞머리의 'Anonymous (not verified)'와 날짜는 사이트가 붙인 잡음이니 글에 쓰지 마세요."},
    # 캐나다 통계청 The Daily(평일 12:30 UTC 발표). 한 피드를 분야별 주제어로 나눠 읽는다(_STATCAN_* 상수).
    {"name": "Statistics Canada · economy", "display_name": "Statistics Canada", "lane": "economy", "url": _STATCAN_FEED,
     "terms": _STATCAN_TERMS, "exclude_title": _STATCAN_EXCLUDE, "topic_regex": _STATCAN_ECONOMY, "page_delay": _STATCAN_PAGE_DELAY,
     "citation": _STATCAN_CITATION, "notice": _STATCAN_NOTICE, "prompt_rule": _STATCAN_PROMPT_RULE},
    {"name": "Statistics Canada · society", "display_name": "Statistics Canada", "lane": "society", "url": _STATCAN_FEED,
     "terms": _STATCAN_TERMS, "exclude_title": _STATCAN_EXCLUDE, "topic_regex": _STATCAN_SOCIETY, "page_delay": _STATCAN_PAGE_DELAY,
     "citation": _STATCAN_CITATION, "notice": _STATCAN_NOTICE, "prompt_rule": _STATCAN_PROMPT_RULE},
    {"name": "Statistics Canada · daily life", "display_name": "Statistics Canada", "lane": "daily_life", "url": _STATCAN_FEED,
     "terms": _STATCAN_TERMS, "exclude_title": _STATCAN_EXCLUDE, "topic_regex": _STATCAN_LIFE, "page_delay": _STATCAN_PAGE_DELAY,
     "citation": _STATCAN_CITATION, "notice": _STATCAN_NOTICE, "prompt_rule": _STATCAN_PROMPT_RULE},
    # 영국 정부 GOV.UK 뉴스(2026-10-26 운영자 결정, _GOVUK_* 상수에 약관 근거). 에너지·환경은 하루 1건 안팎, 과학·기술은 한 달에 서너 건이라 보충용이다.
    {"name": "GOV.UK · Environment & Energy", "display_name": "GOV.UK", "lane": "science", "url": _GOVUK_ENV_FEED,
     "terms": _GOVUK_TERMS, "exclude_title": _GOVUK_EXCLUDE_TITLE, "exclude_link": _GOVUK_EXCLUDE_LINK, "no_page_fetch": True,
     "citation": _GOVUK_CITATION, "notice": _GOVUK_NOTICE, "prompt_rule": _GOVUK_PROMPT_RULE},
    {"name": "GOV.UK · Science & Technology", "display_name": "GOV.UK", "lane": "technology", "url": _GOVUK_TECH_FEED,
     "terms": _GOVUK_TERMS, "exclude_title": _GOVUK_EXCLUDE_TITLE, "exclude_link": _GOVUK_EXCLUDE_LINK, "no_page_fetch": True,
     "citation": _GOVUK_CITATION, "notice": _GOVUK_NOTICE, "prompt_rule": _GOVUK_PROMPT_RULE},
    # R-119 A(2026-11-05): 글감 소스 1차 6곳. 약관 근거는 위 `_FTC_*`·`_FEDS_*`·`_NSF_*`·`_CMA_*` 와 집행위(`_EC_*`)·GOV.UK(`_GOVUK_*`) 상수의 주석에 있다. 목록 끝에 붙여 위 소스의 순서는 그대로다.
    {"name": "FTC · press (consumer protection)", "display_name": "Federal Trade Commission", "lane": "economy",
     "url": "https://www.ftc.gov/feeds/press-release-consumer-protection.xml",
     "terms": _FTC_TERMS, "exclude_title": _FTC_EXCLUDE_TITLE, "no_page_fetch": True, "summary_max_chars": _FTC_SUMMARY_MAX_CHARS,
     "citation": _FTC_CITATION, "notice": _FTC_NOTICE, "prompt_rule": _FTC_PROMPT_RULE},
    {"name": "Federal Reserve · FEDS Notes", "display_name": "Federal Reserve Board (FEDS Notes)", "lane": "economy",
     "url": "https://www.federalreserve.gov/feeds/feds_notes.xml",
     "terms": _FEDS_TERMS, "no_page_fetch": True,
     "citation": _FEDS_CITATION, "notice": _FEDS_NOTICE, "prompt_rule": _FEDS_PROMPT_RULE},
    {"name": "UK CMA · Competition & Markets", "display_name": "GOV.UK (Competition and Markets Authority)", "lane": "economy", "url": _CMA_FEED,
     "terms": _GOVUK_TERMS, "exclude_title": _GOVUK_EXCLUDE_TITLE, "exclude_link": _GOVUK_EXCLUDE_LINK, "no_page_fetch": True,
     "citation": _GOVUK_CITATION, "notice": _GOVUK_NOTICE, "prompt_rule": _CMA_PROMPT_RULE},
    {"name": "European Commission · R&I", "display_name": "European Commission (DG Research and Innovation)", "lane": "technology",
     "url": "https://research-and-innovation.ec.europa.eu/node/2/rss_en",
     "terms": _EC_TERMS, "exclude_title": _EC_EXCLUDE_DG_TITLE, "exclude_link": _EC_EXCLUDE_LINK, "exclude_tags": _EC_EXCLUDE_DG_TAGS,
     "topic_regex": _RTD_TOPIC, "no_page_fetch": True,
     "citation": _ec_citation("European Commission, DG Research and Innovation"), "notice": _EC_NOTICE, "prompt_rule": _EC_PROMPT_RULE},
    {"name": "European Commission · Employment & Social Affairs", "display_name": "European Commission (DG Employment, Social Affairs and Inclusion)",
     "lane": "society", "url": "https://employment-social-affairs.ec.europa.eu/node/2/rss_en",
     "terms": _EC_TERMS, "exclude_title": _EC_EXCLUDE_DG_TITLE, "exclude_link": _EC_EXCLUDE_LINK, "exclude_tags": _EC_EXCLUDE_DG_TAGS, "no_page_fetch": True,
     "citation": _ec_citation("European Commission, DG Employment, Social Affairs and Inclusion"), "notice": _EC_NOTICE, "prompt_rule": _EC_PROMPT_RULE},
    {"name": "U.S. NSF · news", "display_name": "U.S. National Science Foundation", "lane": "technology",
     "url": "https://www.nsf.gov/rss/rss_www_news.xml",
     "terms": _NSF_TERMS, "exclude_title": _NSF_EXCLUDE_TITLE, "no_page_fetch": True,
     "citation": _NSF_CITATION, "notice": _NSF_NOTICE, "prompt_rule": _NSF_PROMPT_RULE},
    # 전자신문(rss.etnews.com)은 2026-10-26에 뺐다: 콘텐츠 이용 안내(info.etnews.com)가 영리·비영리 정보서비스에 사전 협의·정식 계약을 요구하고 무단 사용에는 사용료의
    # 30배 배상을 안내한다. 운영자 결정(2026-10-26 "계약·사용료는 '무료 자동화 기반' 취지에 맞지 않음")으로 TERMS_BLOCKED_DOMAINS 에 올렸다(D-61).
    # 블로터(https://www.bloter.net/feed)는 HTTP 404라 2026-10-25에 뺐다(실행 로그 '수집 실패', 로컬에서도 404/403).
    # 구글 뉴스 검색 소스 14개는 통과율이 0.4%(게시자 원문 주소로 풀리지 않음)라 2026-10-26에 뺐다.
    # MIT Technology Review·BBC Technology 는 약관이 이 용도를 금지·허가 필요로 해서 2026-10-26에 뺐다(TERMS_BLOCKED_DOMAINS).
    # AI타임스는 모든 기사 하단의 'AI학습 및 활용 금지' 표기와 저작권보호정책 때문에 운영자 결정(2026-10-26 "금지된 부분이면 접근하지 않는다")으로 뺐다(TERMS_BLOCKED_DOMAINS, D-61).
    # TechCrunch·The Verge·Hacker News 는 신뢰 목록에 없어 글감이 한 건도 안 되고 약관이 제한적이거나 간접 경로라 같은 날 뺐다(D-61).
    # Ars Technica·IEEE Spectrum 은 robots.txt 가 AI 관련 크롤러(ClaudeBot·anthropic-ai·CCBot 등)를 이름으로 막고 이용약관은 못 읽었거나 복제에 서면 동의를 요구해,
    # 운영자 결정(2026-10-26 "AI 크롤러를 막는 사이트는 접근하지 않는 원칙")으로 같은 날 뺐다(TERMS_BLOCKED_DOMAINS, D-61).
]

# 게시 후보에 사용할 수 있는 출처 도메인. 도메인 이름은 끝 경계까지 비교합니다.
# 보도자료·검색 결과·커뮤니티 링크만으로는 글을 발행하지 않습니다.
TRUSTED_SOURCE_DOMAINS = {
    "science": ("science.org", "pnas.org", "cell.com", "who.int",
                "nih.gov", "noaa.gov", "nasa.gov", "ipcc.ch", "jpl.nasa.gov",
                "ec.europa.eu", "www.gov.uk",
                "reuters.com", "apnews.com"),
    "economy": ("oecd.org", "imf.org", "worldbank.org", "federalreserve.gov",
                "bls.gov", "bok.or.kr", "kostat.go.kr", "kdi.re.kr",
                "ec.europa.eu", "statcan.gc.ca",
                "ftc.gov",       # R-119 A: 미 FTC 보도자료
                "www.gov.uk",    # R-119 A: 영국 CMA 한 곳을 위해서만(재무부·DWP·DBT 같은 정치 발표 피드는 쓰지 않는다 — 2026-10-26 결정)
                "reuters.com", "apnews.com", "ft.com", "bloomberg.com"),
    "society": ("oecd.org", "un.org", "unesco.org", "unicef.org", "korea.kr",
                "kostat.go.kr", "kdi.re.kr",
                "commission.europa.eu", "ec.europa.eu", "statcan.gc.ca",
                "reuters.com", "apnews.com"),
    "technology": ("nist.gov", "acm.org", "arxiv.org",
                   "science.org",
                   "ec.europa.eu", "www.gov.uk",
                   "nsf.gov",       # R-119 A: 미 NSF 뉴스
                   "reuters.com", "apnews.com"),
    "culture": ("unesco.org", "pewresearch.org", "reuters.com", "apnews.com",
                "variety.com", "nytimes.com"),
    "daily_life": ("who.int", "nih.gov", "nhs.uk", "cdc.gov", "apa.org",
                   "kostat.go.kr", "korea.kr", "mfds.go.kr",
                   "foodsafetykorea.go.kr", "kca.go.kr", "consumer.go.kr",
                   "statcan.gc.ca",
                   "reuters.com", "apnews.com"),
}

# 약관을 읽고 이 용도(광고가 붙는 사이트에서 RSS 제목·요약을 AI에 주어 새 글을 쓰는 것)가 금지이거나 허가가 필요하다고 읽은 매체,
# 그리고 robots.txt 로 AI 크롤러를 막아 운영자가 접근하지 않기로 한 매체.
# 신뢰 목록에 실수로 다시 들어와도 _trusted_domain 이 거부한다(법률 판단이 아니다). 근거: docs/analysis/2026-10-25_publish-readiness.md §3-1,
# BBC·MIT TR 은 2026-10-26 약관 재확인.
#   BBC                    사업적 RSS 이용은 허가 필요, RSS·콘텐츠에서 메타데이터를 가져오는 것과 AI·컴퓨터 분석 이용은 허가 필요, 돈을 버는 이용도 허가 대상(이용약관 v1.8 §7(d)·§8·§15, 2022-09-19판)
#   Guardian               사전 서면 승인 없는 상업적 이용·AI로 콘텐츠를 생성·합성하는 것 금지
#   Nature                 상업적 이용에는 허가 필요
#   MIT Technology Review  복제·수정·재게시 금지, 파생물·상업적 이용 금지(서비스에 RSS 포함), 콘텐츠로 AI 시스템을 만들거나 학습·개선하는 것은 사전 서면 동의(Restrictions on Use·Commercial Use·AI and Large Language Model Usage, 2023-09-06판)
#   AI타임스               모든 기사 하단에 "무단전재 및 재배포, AI학습 및 활용 금지", 저작권보호정책은 승낙 없는 복제·출판·전송·배포·판매·변형 금지(2026-10-26 기사 3건 확인). 운영자 결정으로 접근하지 않는다
#   Ars Technica           robots.txt 가 ClaudeBot·anthropic-ai·CCBot·Google-Extended 등 AI 관련 크롤러 약 30개를 이름으로 막는다(`Disallow: /` 대상 34개 중, 2026-10-26 검증 세션이 읽음), Condé Nast 약관은 읽지 못함. 운영자 결정(2026-10-26 "AI 크롤러를 막는 사이트는 접근하지 않는 원칙")으로 접근하지 않는다
#   IEEE(Spectrum 포함)    robots.txt 가 GPTBot·ClaudeBot·anthropic-ai·CCBot·PerplexityBot 등 AI 관련 크롤러 약 21개를 이름으로 막고(33개 중, 사용자 요청형 일부는 명시 허용) 이용약관은 복제에 사전 서면 동의를 요구한다(검증 세션 보고). 같은 결정으로 접근하지 않는다
#   전자신문               콘텐츠 이용 안내(info.etnews.com 콘텐츠 구매 페이지)가 영리·비영리 정보서비스에 사전 협의·정식 계약을 요구하고, 수집해 자체 DB를 만들면 저작권 침해이며 무단 사용에는 사용료의 30배 배상을 안내한다. 운영자 결정(2026-10-26 "계약·사용료는 '무료 자동화 기반' 취지에 맞지 않음")으로 접근하지 않는다
TERMS_BLOCKED_DOMAINS = ("bbc.com", "bbc.co.uk", "bbci.co.uk", "theguardian.com", "guardian.co.uk",
                         "nature.com", "technologyreview.com", "aitimes.com",
                         "arstechnica.com", "ieee.org", "etnews.com")


# 모델에 넘기는 피드 요약의 최대 글자 수(parse_feed 가 자른다). 예전에는 300자였다 — 2026-11-04 진단: EU Digital Strategy 요약은 항목당 403~3,052자(중앙 1,668자)라 모델이 중앙 기준 약 18%만 봤고,
# NASA(374~405자)·통계청(최대 796자)도 잘렸다. 소스에 `summary_max_chars` 를 적으면 그 소스만 이 값 대신 쓴다(소스의 약관이 더 짧은 발췌만 허락하면 그 값으로 낮춘다).
# 약관 점검(2026-11-04, NEWS_SOURCES 의 terms 기록 기준 — 사이트 약관 원문은 다시 읽지 않았다): 읽는 소스(terms.status == "allowed") 모두 이 값으로 늘려도 되는 것으로 읽었다. 조건은 출처 표시·변경 표시·
# 보증 암시 금지·AI 이용 안내(NASA)이고, 피드가 이미 주는 글을 모델에 넘기는 분량의 제한은 기록에 없다. 새 요청은 0건이다(같은 피드 응답을 덜 자르기만 한다). 보류 소스(UN News)는 읽지 않는다.
# 프롬프트 길이 영향은 docs/ARCHITECTURE.md '모델에 넘기는 근거 늘리기'에 계산했다(호출당 최대 +1,500자). 원문을 그대로 옮기지 않게 하는 장치(프롬프트의 '문장을 그대로 옮기지 마세요'·GROUNDING_RULES)는 그대로다.
SUMMARY_MAX_CHARS = 1800

# 증거가 한 문장 수준인 후보는 모델 호출 순서에서 뒤로 미룬다(B). 증거량(evidence_chars) = 요약에서 사이트 틀 문구와 주소를 뺀 글자 수.
# 근거(2026-11-04 진단): 11-04 9시 슬롯이 두 번 모두 막힌 후보 'Web Summit 2026'(EU Digital Strategy 행사 안내)의 요약은 원래 403자였지만 사실 정보는 'DG Connect 가 11월 10~12일 리스본 Web Summit 에 참가한다'는
# 한 문장뿐이고 나머지는 사이트 틀 문구였다(제목 반복, 'Anonymous (not verified) Tue, 11/03/2026 - 11:13', 'Main link https://…', 'Related topics …'). 틀 문구를 빼면 약 118자다.
# 영문 뉴스 한 문장은 보통 100~150자이므로 150자 미만을 '한 문장 수준'으로 본다. 뒤로 미룰 뿐 탈락시키지 않는다 — 얇은 후보만 있는 분야는 그대로 시도하고(마지막 후보로),
# 150자 이상인 정상 후보의 순서는 그대로다. 요약 자체(모델에 넘기는 글)는 바꾸지 않는다. 요약이 100자 미만이면 기존대로 SHORT_SUMMARY(기사 페이지 설명을 읽어 보고도 100자 미만이면 후보에서 빠진다)이고,
# 이 상수는 그 위의 100~149자와 틀 문구를 빼면 150자 미만이 되는 요약을 '얇음'으로 본다 — 두 장치는 겹치지 않는다.
THIN_EVIDENCE_CHARS = 150
_FRAME_HEAD = re.compile(r"Anonymous \(not verified\)\s+(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+)?\d{1,2}/\d{1,2}/\d{4}\s*-\s*\d{1,2}:\d{2}")
_FRAME_TAIL = re.compile(r"\b(?:Main link|Related topics)\b.*", re.S)
_BARE_URL = re.compile(r"https?://\S+")


def evidence_chars(summary):
    """모델에 넘기는 요약에서 사이트 틀 문구(앞의 'Anonymous (not verified) 날짜', 뒤의 'Main link 주소·Related topics …' 꼬리)와 주소를 뺀 글자 수."""
    text = _BARE_URL.sub(" ", _FRAME_HEAD.sub(" ", _FRAME_TAIL.sub(" ", summary or "")))
    return len(" ".join(text.split()))


def _clean_text(s, limit=300):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()[:limit]


def _parse_date(text):
    if not text:
        return None
    text = text.strip()
    try:
        dt_ = parsedate_to_datetime(text)
    except Exception:
        try:
            dt_ = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if dt_ is not None and dt_.tzinfo is None:
        dt_ = dt_.replace(tzinfo=timezone.utc)
    return dt_


def _host(url):
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return ""


# 기사 주소는 글의 출처 목록·인용 줄에 마크다운 링크 `[글](주소)` 로 들어간다. 공백·꺾쇠·따옴표·역슬래시와 괄호·대괄호는 링크를 끊거나 새 링크·HTML 을 만들 수 있어 막는다.
# fullmatch 로 쓴다: `$` 는 끝의 줄바꿈 앞에서도 맞아 Atom href 의 끝 줄바꿈이 통과한다. 실제 피드 링크 335개(16개 피드)에는 이 글자가 하나도 없었다(2026-10-26).
_SAFE_URL = re.compile(r"https?://[^\s<>\"'\\()\[\]]+")


def _host_in(host, domains):
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _trusted_domain(host, lane):
    """게시 후보로 쓸 수 있는 게시자인가. 약관상 쓸 수 없는 도메인(TERMS_BLOCKED_DOMAINS)은 신뢰 목록에 들어와 있어도 거부한다."""
    return not _host_in(host, TERMS_BLOCKED_DOMAINS) and _host_in(host, TRUSTED_SOURCE_DOMAINS.get(lane, ()))


def _resolve_article_url(url):
    """Google News 리디렉션을 따라가 게시자 원문 URL을 얻습니다."""
    if not url:
        return ""
    source_policy.egress_gate(url, "resolve", now_kst)   # allowlist: 일반 웹 읽기(resolve)는 관문이 항상 거부한다(legacy 는 아무 일도 하지 않는다). try 밖 — 거부를 삼켜 빈 값으로 넘어가지 않는다
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as response:
            resolved = response.geturl()
        parsed = urllib.parse.urlparse(resolved)
        return resolved if parsed.scheme in {"http", "https"} and parsed.hostname else ""
    except Exception:
        return ""


def _fetch_source_excerpt(url):
    """원문 페이지의 게시자 요약을 가져옵니다. 본문 전문은 수집하지 않습니다."""
    source_policy.egress_gate(url, "page", now_kst)   # allowlist: 일반 웹 읽기(page)는 관문이 항상 거부한다(legacy 는 아무 일도 하지 않는다). try 밖 — 거부를 삼키지 않는다
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read(700_000).decode("utf-8", errors="replace")
        for pattern in (
            r'<meta[^>]+(?:property|name)=["\'](?:og:description|description)["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:description|description)',
        ):
            match = re.search(pattern, raw, re.I)
            if match:
                return _clean_text(match.group(1), 1200)
    except Exception:
        pass
    return ""


def parse_feed(data, summary_limit=None):
    """RSS 2.0(item)와 Atom(entry)을 모두 처리. 요약은 summary_limit 자(생략하면 SUMMARY_MAX_CHARS)까지 남긴다."""
    root = ET.fromstring(data)
    items = []
    for node in root.iter():
        if node.tag.split("}")[-1] not in ("item", "entry"):
            continue

        def text_of(*names):
            for child in node:
                if child.tag.split("}")[-1] in names:
                    text = (child.text or "").strip()
                    # Atom 의 type="xhtml" 은 글자가 자식 요소(div·span) 안에 들어 있다(Statistics Canada The Daily). 그때만 자식까지 이어 읽는다
                    # (그 밖의 중첩 요소 — 예: <media:content> 안의 <media:description> — 를 요약으로 착각하지 않게).
                    if not text and child.get("type") == "xhtml":
                        text = "".join(child.itertext()).strip()
                    if text:
                        return text
            return ""

        link = ""
        publisher_name = ""
        publisher_url = ""
        categories = []
        for child in node:
            tag = child.tag.split("}")[-1]
            if tag == "link" and not link:
                link = child.get("href") or (child.text or "").strip()
            elif tag == "source":
                publisher_name = _clean_text(child.text or "", 120)
                publisher_url = child.get("url") or ""
            elif tag == "category":
                label = _clean_text(child.get("term") or child.text or "", 80)
                if label:
                    categories.append(label)
        items.append({
            "title": _clean_text(text_of("title"), 300),
            "published": _parse_date(text_of("pubDate", "published", "updated", "date")),
            "summary": _clean_text(text_of("description", "summary", "content", "encoded"),
                                   SUMMARY_MAX_CHARS if summary_limit is None else summary_limit),
            "link": link,
            "publisher_name": publisher_name,
            "publisher_url": publisher_url,
            "categories": categories,
        })
    return items


def _rule_excludes(src, title, item):
    """소스의 제외 규칙(exclude_title·exclude_link·exclude_tags)에 걸리는 기사인가."""
    checks = (("exclude_title", [title]), ("exclude_link", [item.get("link") or ""]), ("exclude_tags", item.get("categories") or []))
    return any(src.get(key) and any(re.search(src[key], text, re.I) for text in texts) for key, texts in checks)


def fetch_news_items(editorial_lane=None, stats=None, deadline=None, clock=time.monotonic):
    """여러 소스에서 최근 기사 후보를 모아, 소스를 번갈아 섞은 목록으로 반환.
    stats(dict)를 넘기면 소스별 수집·탈락 사유 개수를 stats["sources"]에 채운다(동작은 같다).
    deadline(clock 기준 시각)을 넘기면 그 시각이 지난 뒤에는 남은 소스를 시도하지 않는다(느린 장애에서 잡 제한을 넘기지 않도록)."""
    now = datetime.datetime.now(timezone.utc)
    max_age = timedelta(hours=NEWS_MAX_AGE_HOURS)
    per_source, attempted, ok_count, time_skipped = [], 0, 0, 0
    source_mode = source_policy.chance_source_policy()     # legacy(기본)면 아래 허용 목록 분기는 모두 건너뛴다 — 이전과 같다
    policy_registry = source_policy.news_registry(source_mode, now_kst)   # allowlist 일 때만 허용 목록(Registry), 아니면 None
    for src in NEWS_SOURCES:
        if editorial_lane and src.get("lane") != editorial_lane:
            continue
        terms = src.get("terms") or {}
        if terms.get("status") == "pending":
            print(f"  소스 {src['name']}: 보류 — {_one_line(terms.get('blocker', ''), 200)}")
            continue
        if _host_in(_host(src.get("url", "")), TERMS_BLOCKED_DOMAINS):
            print(f"  소스 {src['name']}: 약관상 접근하지 않는 도메인(TERMS_BLOCKED_DOMAINS)이라 읽지 않음")
            continue
        if policy_registry is not None and not policy_registry.is_url_allowed(src.get("url", ""), "feed")[0]:
            print(f"  소스 {src['name']}: 허용 목록(Registry)의 ACTIVE 가 아니라 읽지 않음(source_policy: allowlist)")   # 피드(RSS)는 유형만으로 Tier 3 — 네트워크 호출 0
            continue
        if deadline is not None and clock() > deadline:
            time_skipped += 1
            continue
        attempted += 1
        source_policy.egress_gate(src["url"], "feed", mode=source_mode, registry=policy_registry)   # allowlist 에서는 위 분기가 먼저 걸러 여기에 오지 못한다(관문은 그 보증의 이중 장치). try 밖 — 거부를 수집 실패로 삼키지 않는다
        try:
            req = urllib.request.Request(src["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                parsed = parse_feed(resp.read(), summary_limit=src.get("summary_max_chars"))
            ok_count += 1
        except Exception as exc:
            print(f"  소스 {src['name']}: 수집 실패 ({type(exc).__name__}: {_one_line(exc, 200)})")
            if stats is not None:
                stats.setdefault("sources", []).append(
                    {"name": src["name"], "fetched": 0, "kept": 0, "drops": {},
                     "error": type(exc).__name__})
            continue
        kept = []
        drops = {}
        resolved_count = 0
        topic_re = re.compile(src["topic_regex"], re.I) if src.get("topic_regex") else None
        pages_fetched = 0
        for it in parsed:
            title = it["title"]
            publisher = it.get("publisher_name") or ""
            publisher_url = it.get("publisher_url") or ""
            if src.get("google"):
                if not publisher:
                    match = re.match(r"^(.*)\s+-\s+([^-]+)$", title)
                    if match:
                        title, publisher = match.group(1).strip(), match.group(2).strip()
            else:
                # 직접 RSS 의 <source> 는 피드 자기소개(예: UN News 의 긴 태그라인)라 게시자 표시로 쓰지 않는다 — 게시자는 기사 주소의 호스트다.
                publisher = publisher_url = ""
            if not title:
                _count(drops, "NO_TITLE")
                continue
            if _rule_excludes(src, title, it):
                _count(drops, "EXCLUDED")
                continue
            if topic_re and not topic_re.search(" ".join([title] + it.get("categories", []))):
                _count(drops, "OFF_TOPIC")
                continue
            if src.get("tech_filter") and not is_tech_title(title):
                _count(drops, "NOT_TECH")
                continue
            pub = it["published"]
            if pub and now - pub > max_age:
                _count(drops, "AGE")
                continue
            publisher_host = _host(publisher_url)
            if publisher_host and not _trusted_domain(publisher_host, editorial_lane):
                _count(drops, "UNTRUSTED")
                continue
            if resolved_count >= 5:
                _count(drops, "UNCHECKED")
                continue
            article_url = _resolve_article_url(it["link"]) if src.get("google") else it["link"]
            resolved_count += 1
            publisher_host = publisher_host or _host(article_url)
            if not article_url or not _SAFE_URL.fullmatch(article_url):  # 줄바꿈·꺾쇠·따옴표·괄호가 든 주소는 글에 그대로 들어가면 마크다운·HTML 이 된다
                _count(drops, "UNRESOLVED")
                continue
            if not _trusted_domain(publisher_host, editorial_lane):
                _count(drops, "UNTRUSTED")
                continue
            article_host = _host(article_url)
            same_publisher = (article_host == publisher_host
                              or article_host.endswith("." + publisher_host)
                              or publisher_host.endswith("." + article_host))
            if not same_publisher or not _trusted_domain(article_host, editorial_lane):
                _count(drops, "HOST_MISMATCH")
                continue
            summary = it["summary"]
            if len(summary) < 100 and not src.get("no_page_fetch"):
                if pages_fetched and src.get("page_delay"):
                    time.sleep(src["page_delay"])   # 같은 사이트의 기사 페이지를 연달아 읽을 때 Crawl-delay 를 지킨다
                pages_fetched += 1
                summary = _fetch_source_excerpt(article_url)
            if len(summary) < 100:
                _count(drops, "SHORT_SUMMARY")
                continue
            kept.append({"title": title, "source": publisher or src.get("display_name") or src["name"],
                         "link": article_url, "publisher_domain": publisher_host,
                         "summary": summary, "published": pub,
                         "notice": src.get("notice"), "citation": src.get("citation"),
                         "prompt_rule": src.get("prompt_rule")})
        kept.sort(key=lambda x: x["published"] or EPOCH, reverse=True)
        line = f"  소스 {src['name']}: {len(parsed)}건 중 {len(kept)}건 사용"
        if drops:
            line += f" (탈락: {_format_drops(drops)})"
        print(line)
        if stats is not None:
            stats.setdefault("sources", []).append(
                {"name": src["name"], "fetched": len(parsed), "kept": len(kept),
                 "drops": drops})
        per_source.append(kept[:10])

    if time_skipped:
        print(f"  시간 상한으로 소스 {time_skipped}개를 시도하지 않았습니다.")
        if stats is not None:
            stats["time_skipped"] = time_skipped
    if attempted and ok_count == 0:
        print("::warning::모든 뉴스 소스 수집에 실패했습니다. 네트워크/소스 주소를 확인하세요.")
    merged, seen = [], set()
    for rank in range(10):
        for lst in per_source:
            if rank < len(lst):
                it = lst[rank]
                key = it["title"].casefold()
                if key not in seen:
                    seen.add(key)
                    merged.append(it)
    return merged


def pick_topic_candidates(titles, allow_auto_topic=True, editorial_lane=None, stats=None, deadline=None,
                          clock=time.monotonic):
    """신뢰 출처 검증과 중복 검사를 통과한 기사 후보만 반환합니다.
    증거가 한 문장 수준(evidence_chars < THIN_EVIDENCE_CHARS)인 후보는 증거가 두꺼운 후보 뒤로 보냅니다(순서만 바꾸고 탈락시키지 않으며, 각 묶음 안의 순서는 그대로).
    stats(dict)를 넘기면 소스별 개수와 함께 중복으로 탈락한 수·최종 후보 수·후보 가운데 증거가 얇은 수(thin)를 채웁니다."""
    picked = []
    duplicates = 0
    items = fetch_news_items(editorial_lane, stats=stats, deadline=deadline, clock=clock)
    scored = [(evidence_chars(it.get("summary")) < THIN_EVIDENCE_CHARS, it) for it in items]
    ordered = [it for is_thin, it in scored if not is_thin] + [it for is_thin, it in scored if is_thin]
    thin_ids = {id(it) for is_thin, it in scored if is_thin}
    if any(a is not b for a, b in zip(ordered, items)):
        print(f"  근거가 얇은 후보 {len(thin_ids)}건(증거 {THIN_EVIDENCE_CHARS}자 미만)은 시도 순서를 뒤로 미룸")
    for it in ordered:
        if is_similar_to_any(it["title"], titles, 0.6):
            duplicates += 1
            continue
        picked.append(it)
        if len(picked) >= MAX_ATTEMPTS:
            break
    if stats is not None:
        stats["duplicates"] = duplicates
        stats["candidates"] = len(picked)
        stats["thin"] = sum(1 for it in picked if id(it) in thin_ids)
    # 출처 검증을 통과한 기사가 없으면 AI가 근거 없이 주제를 고르지 않습니다.
    return picked


def editorial_lane_order(slot, history, now=None):
    """최근 발행 편중을 줄이면서 날짜·슬롯·이력·실행 시각 구간별로 재현 가능한 확률 추첨 순서로 모든 분야를 반환합니다.
    첫 번째가 choose_editorial_lane 의 선택과 같고, 뒤쪽은 그 분야에 후보가 없거나 후보가 모두 탈락했을 때 시도할 대체 순서입니다.
    now 는 시계 주입용(생략하면 지금, now_kst)입니다. 같은 슬롯 창 안에서도 실행 시각 구간(LANE_ORDER_BUCKET_MINUTES)이 다르면 순서가 달라져 같은 실패를 되풀이하지 않습니다(D-34).
    분야별 가중치(최근 발행 편중)는 이력만 보므로 구간이 달라져도 같은 분야가 연속되지 않게 하는 균형은 그대로입니다."""
    lanes = list(EDITORIAL_LANES)
    recent = [item.get("lane") for item in history[-12:]
              if isinstance(item, dict) and item.get("lane") in EDITORIAL_LANES]
    counts = {lane: recent.count(lane) for lane in lanes}
    weights = {}
    for lane in lanes:
        # 최근 자주 나온 분야의 확률을 낮추되 0으로 만들지 않아 유행 분야도 계속 후보로 둡니다.
        weights[lane] = 1.0 / (1.0 + counts[lane] * 0.65)
        if recent and recent[-1] == lane:
            weights[lane] *= 0.25
        elif len(recent) > 1 and recent[-2] == lane:
            weights[lane] *= 0.6

    now = now_kst() if now is None else now
    latest = history[-1] if history else None
    latest_key = (latest.get("date", ""), latest.get("topic", "")) if isinstance(latest, dict) else str(latest or "")
    seed = f"{now:%Y-%m-%d}|{slot}|{len(history)}|{latest_key}{_lane_order_bucket(now)}"
    rng = random.Random(seed)
    remaining, order = list(lanes), []
    while remaining:
        picked = rng.choices(remaining, weights=[weights[lane] for lane in remaining], k=1)[0]
        order.append(picked)
        remaining.remove(picked)
    return order


def choose_editorial_lane(slot, history):
    """추첨 순서의 첫 분야."""
    return editorial_lane_order(slot, history)[0]


# ============================================================
# 글 생성
# ============================================================
def load_editorial_template():
    """Load the repository's reviewed writing and revision guide; fail closed if missing."""
    try:
        template = EDITORIAL_TEMPLATE_FILE.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"편집 템플릿을 읽을 수 없습니다: {EDITORIAL_TEMPLATE_FILE}") from exc
    if not template:
        raise RuntimeError("편집 템플릿이 비어 있어 게시글 생성을 중단합니다.")
    return template


def build_post_prompt(item, recent_titles, category_hint="", allow_skip=False,
                      editorial_lane="technology", languages=("ko", "en")):
    lane = EDITORIAL_LANES.get(editorial_lane, EDITORIAL_LANES["technology"])
    # 글의 언어(레지스트리 chance.languages): 기본 ko·en 한 쌍이면 아래 낱말은 모두 예전 글자 그대로이고, ko 만이면 영어를 만들라는 말을 뺀 국문 전용 프롬프트가 된다.
    pair = tuple(languages) == ("ko", "en")
    write_in = "한국어와 영어로 각각" if pair else "한국어로"
    each_post = "각 글의" if pair else "글의"
    natural = "- 한국어/영어 글은 각 언어에 자연스럽게 쓰고 단순 직역은 피하세요.\n" if pair else "- 한국어로 자연스럽게 쓰세요.\n"
    contents = "kr_content, en_content에는" if pair else "kr_content에는"
    en_schema = (f"  \"en_category\": \"{lane['en_category']}\",\n  \"en_title\": \"English Title\",\n  \"en_tags\": [\"Tag1\", \"Tag2\"],\n"
                 "  \"en_content\": \"English Markdown full content\",\n") if pair else ""
    category_rule = (
        f"- 요청된 카테고리 힌트 [{category_hint}]를 우선 사용하되, 주제와 다르면 억지로 적용하지 마세요.\n"
        if category_hint else
        (f"- 본문 카테고리는 한국어에서 \"{lane['kr_category']}\", 영어에서 \"{lane['en_category']}\"를 사용하세요. 글의 핵심 주제가 편집 축과 맞지 않으면 다른 주제로 다시 고르세요.\n" if pair else
         f"- 본문 카테고리는 한국어에서 \"{lane['kr_category']}\"를 사용하세요. 글의 핵심 주제가 편집 축과 맞지 않으면 다른 주제로 다시 고르세요.\n")
    )
    item, recent_titles = source_policy.prompt_inputs(source_policy.chance_source_policy(), item, recent_titles)   # allowlist: 자체 제목만(외부 제목·요약·태그 제거). legacy 는 그대로
    if item:
        topic_text = item["title"]
        if item.get("source"):
            topic_text += f"\n[출처] {item['source']}"
        if item.get("link"):
            topic_text += f"\n[원문 URL] {item['link']}"
        if item.get("published"):
            topic_text += f"\n[원문 게시 시각] {item['published'].isoformat()}"
        if item.get("summary"):
            topic_text += ("\n[기사 요약 - 참고만 하고 문장을 그대로 옮기지 마세요]\n"
                           + item["summary"])
    else:
        topic_text = "검증된 출처가 제공되지 않았습니다. 반드시 skip을 반환하세요."
    skip_rule = ('- 이 주제가 [최근 다룬 주제/제목]과 같은 사건이나 소재라면 글을 쓰지 말고 '
                 '{"skip": true, "reason": "..."} 만 반환하세요.\n') if allow_skip else ""
    if item and item.get("link") and item.get("source"):
        source_rule = ("- 제공된 검증 게시자 원문만 사실 근거로 쓰세요. 원문에서 확인되지 않는 주장·수치·인용·날짜·인과관계는 쓰지 마세요.\n"
                       "- 학술 연구는 동료심사 여부를 명시하고 표본·범위·한계를 설명하세요. arXiv 등의 프리프린트를 동료심사 연구처럼 표현하지 마세요.\n"
                       "- 중요한 사실 문장에는 제공된 원문 URL을 Markdown 인라인 인용으로 붙이세요. 사실과 해석·전망을 명확히 구분하세요.\n"
                       "- 제목·저자·학술지명·DOI·통계·인용문이나 출처를 추정해 만들지 마세요. 근거가 부족하면 skip을 반환하세요.\n"
                       + "".join(f"- {rule}\n" for rule in GROUNDING_RULES))   # 소스와 상관없이 모든 글감에 붙는 '요약에 없는 것을 채우지 않는' 규칙(D-77)
    else:
        source_rule = "- 검증된 출처가 없으면 글을 만들지 말고 skip을 반환하세요.\n"
    extra_rule = f"- {item['prompt_rule']}\n" if item and item.get("prompt_rule") else ""
    hint = f"[카테고리 힌트] {category_hint}\n" if category_hint else ""
    editorial_template = load_editorial_template()
    return f"""
당신은 기술, 경제, 사회, 과학, 문화와 일상을 함께 읽는 교양형 매거진 'Chance_Blog'의 편집자입니다.
선택된 편집 축은 [{lane['label']}]이며, 이번 축의 중심 범위는 다음과 같습니다: {lane['focus']}.
아래 주제를 바탕으로 독창적이고 사실에 신중한 블로그 글을 {write_in} 작성하세요.

[주제]
{topic_text}

{hint}[최근 다룬 주제/제목 - 같은 소재와 관점 금지]
{json.dumps(recent_titles, ensure_ascii=False)}

[중요 지침]
{skip_rule}- 제목, 카테고리, 태그를 주제에 맞게 작성하세요.
- 아래 [편집 템플릿]을 실제 작성과 최종 자가 편집에 모두 적용하세요. 자연스러운 글을 위해 개인 경험이나 사람인 척하는 문장을 만들어 넣지 마세요. AI 사용을 감추거나 탐지기를 속이려 하지 마세요.
- 이 매거진은 IT 전문 매체가 아닙니다. 이번 편집 축의 주제를 중심에 두고, 기술·경제·사회·문화·환경·교육·일상 중 실제로 연결되는 다른 관점 하나를 함께 설명하세요. 억지로 연결하지 말고, 관련이 약하면 주제 자체를 더 적합한 것으로 고르세요.
- 사람들의 선택과 생활에 어떤 차이가 생기는지 구체적으로 설명하고, 누가 이익을 얻거나 비용을 부담하는지 살펴보세요. 한 분야의 전문성은 유지하되 독자가 다른 분야와 연결해 생각할 수 있게 하세요.
{category_rule}- 글은 한 편 안에서 독립적으로 이해되어야 하며, 중요한 사실 근거를 본문에 링크하고 끝에 출처 목록을 제공합니다.
- 독자가 이 주제에서 실제로 알고 싶어 할 질문에 답하고, 제목은 핵심 내용과 근거의 범위를 정확히 나타내세요. 과장·낚시성 표현은 피하세요.
- 독자에게 가장 필요한 형식(사건 설명, 해설, 비교, 연구 요약, 실용 안내 등)을 고르고, 그 형식에 맞춰 글을 구성하세요. 매번 같은 도입, 3개 소제목, 전망형 결말을 반복하지 마세요. 소제목 수와 문단 길이는 자료와 주제에 맞추고, 필요 없는 결론 요약은 생략하세요.
- 첫 문단은 주제를 자연스럽게 소개하고 독자가 얻을 답이나 핵심 사실을 분명히 보여 주세요. 본문에서 확인된 사실, 출처의 주장, 편집자의 해석과 전망을 구분하세요.
- 소스 요약을 문단별로 바꾸어 쓰는 데 그치지 말고, 근거가 허용하는 비교·맥락·한계 또는 실행 가능한 시사점을 제공하세요. 근거가 부족하면 추측으로 채우지 말고 skip을 반환하세요.
- 관용적인 AI 문구, 중요성을 부풀리는 표현, 반복되는 요약, 억지로 넣은 3단 나열은 덜어내세요. 자연스러움은 구체적인 근거와 명료한 문장에서 나오게 하세요. 오탈자·속어·가짜 개인 경험을 추가하거나 AI 사용 사실을 숨기려 하지 마세요.
{natural}- 확인되지 않은 수치, 인용문, 발표 사실을 지어내지 마세요. 기사 문장을 그대로 옮기지 마세요.
{source_rule}{extra_rule}- 본문은 충분한 설명과 분석을 포함하고 Markdown으로 작성하세요.
- {each_post} Front Matter에 layout, title, category, tags, lang을 포함하세요.
- image는 쓰지 마세요. 대표 이미지는 시스템이 따로 채웁니다.
- image_queries: 이 글의 대표 이미지를 Unsplash에서 찾을 영어 검색어 3개.
  구체적인 것부터 일반적인 순서, 각 2~4단어, 주제를 시각적으로 나타내는
  사물/장면 위주, 사람 얼굴/로고/브랜드명/글자는 피하세요.
- {contents} 완전한 Markdown(Front Matter 포함)을 넣으세요.
- JSON 문자열 안의 줄바꿈과 따옴표는 유효한 JSON 규칙을 지키세요.
- JSON 객체만 반환하고 코드 펜스는 쓰지 마세요.

[편집 템플릿]
{editorial_template}

{{
  "kr_category": "{lane['kr_category']}",
  "kr_title": "한국어 제목",
  "kr_tags": ["태그1", "태그2"],
  "kr_content": "한국어 Markdown 전체",
{en_schema}  "image_queries": ["specific query", "broader query", "general query"]
}}
"""


def stub_post_data(topic, link=None):
    """DRY_RUN(API 키 없음)용 가짜 글. 본문 검증(최소 분량 + 원문 링크 인용)을 통과하도록 충분히 길게 만든다.
    예전에는 본문이 2자라 후보가 있으면 검증에서 실패했다(첫 분야가 비면 가려졌던 결함)."""
    t = topic or "stub topic"
    fm = "---\nlayout: post\ntitle: \"{}\"\ncategory: \"{}\"\ntags: []\n---\n\n{}"
    kr_body = "이 문단은 DRY_RUN 연습용 가짜 본문입니다. 실제 글이 아닙니다. " * 50
    en_body = "This paragraph is placeholder text used only by the dry run; it is not a real article. " * 30
    if link:
        kr_body += f"\n\n근거: [원문]({link})\n"
        en_body += f"\n\nSource: [original]({link})\n"
    return {
        "kr_category": "KR - 스텁", "kr_title": f"[스텁] {t}", "kr_tags": ["스텁"],
        "kr_content": fm.format(f"[스텁] {t}", "KR - 스텁", kr_body),
        "en_category": "EN - Stub", "en_title": f"[stub] {t}", "en_tags": ["stub"],
        "en_content": fm.format(f"[stub] {t}", "EN - Stub", en_body),
        "image_queries": ["technology", "computer hardware"],
    }


def _validate_editorial_body(content, lang, verified_source_url):
    """Reject thin drafts or drafts that cite their source only in a source list."""
    match = re.match(r"\A---\s*\n.*?\n---\s*\n(.*)\Z", content, re.S)
    body = match.group(1) if match else content
    story = re.split(r"(?im)^##\s*(?:출처|참고 자료|sources)\s*$", body, maxsplit=1)[0]
    readable = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", story)
    readable = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", readable)
    readable = re.sub(r"<[^>]+>|[`*_>#|~]", " ", readable)
    readable = re.sub(r"\s+", "", readable)
    minimum = MIN_BODY_CHARS.get(lang, MIN_BODY_CHARS["en"])
    if len(readable) < minimum:
        raise ValueError(
            f"{lang.upper()} 본문이 최소 편집 분량({minimum}자)에 미달합니다: "
            f"{len(readable)}자. 억지로 늘리지 말고 근거가 부족하면 발행을 보류하세요."
        )
    if not verified_source_url or verified_source_url not in story:
        raise ValueError(
            f"{lang.upper()} 본문에 검증된 원문 링크를 뒷받침되는 주장 가까이에 인용해야 합니다."
        )


# ============================================================
# 글 머리말(front matter) 검사·복구 (D-80, 사용자 이슈 #59)
# ============================================================
# 모델이 쓴 머리말 줄은 믿지 않는다. 2026-10-27 18시 슬롯의 글 한 쌍은 모델이 `------` 로 시작하는 이중 머리말을, 2026-10-28 9시 슬롯의 한글 글은
# 안쪽 따옴표를 이스케이프하지 않은 제목(`title: ""…": …"`)을 내보냈다. 옛 코드는 그 줄을 그대로 글 파일에 써서 공개 사이트의 글 제목이 파일 이름으로,
# 분야가 General 로 나왔다. 그래서 ① 모델 응답에서 머리말과 본문을 견고하게 가르고(_split_model_content) ② 머리말이 엄격 검사를 통과할 때만 모델이 쓴
# 줄을 보존하고 아니면 구조화된 값(제목·분야·태그)으로 처음부터 다시 쓰며(_front_matter_from_model) ③ 설명·출처 줄까지 더한 최종 글을 한 번 더 검사해
# (front_matter_problems) 깨진 글은 발행하지 않고 그 후보를 거절한다. 운영 환경(requirements-pipeline.txt)에는 PyYAML 이 없으므로 검사는 정규식·JSON 으로만
# 한다: 한 줄 `키: 값`(과 값이 빈 키에 이어지는 블록 목록 항목)만 받아들이고 그 밖의 모양은 모두 '믿지 않는 머리말'이다.
_FM_FENCE = re.compile(r"-{3,}[ \t]*")      # 울타리처럼 보이는 줄(대시만 3개 이상). 정상은 정확히 `---`
_FM_KEY = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]|\Z)")      # 줄 맨 앞의 `키:` — 콜론 뒤가 공백이나 줄 끝이어야 YAML 매핑이다
_FM_ITEM = re.compile(r" *-[ \t]+(.*)")      # 값이 빈 앞 키에 이어지는 블록 목록 항목(`  - 값`)
_FM_SHAPED = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_-]*[ \t]*:|-[ \t]|[ \t#])")      # 머리말 줄처럼 생긴 줄(빈 줄은 따로 센다)
_FM_KNOWN_KEY = re.compile(r"(?:layout|title|category|tags|lang|image|description|provenance)[ \t]*:")      # 글 머리말에만 있는 키(provenance 는 생성기 전용 출처 표식 — 모델이 둘째 머리말에 심으려는 시도를 머리말 한 덩이로 알아보고 걷어내려고 넣었다)
_FM_RESIDUE = re.compile(r"(?:layout|title|category|tags|lang|image|description|provenance|published|date|permalink|slug|source_name|source_url|source_domain)[ \t]*:")      # 본문 앞 세 줄에 남아서는 안 되는 머리말 줄(소문자 키만)
_FM_REQUIRED = ("layout", "title", "category", "lang", "image")
_FM_MAX_LINE = 2000      # 머리말 한 줄의 상한(검사 정규식이 아주 긴 줄에서 오래 걸리지 않게)
# 한 줄 목록의 항목: 큰따옴표(JSON 이 아는 이스케이프만)·작은따옴표·평문. 평문 항목은 공백으로 끝나지 못한다 — 꼬리와 뒤의 `[ \t]*` 가 같은 공백을 겹쳐 먹으면 되돌아가기가
# 항목 수의 지수로 늘어(`tags: [a ,a ,… #]` 22개 1.3초, 하나 늘 때마다 두 배) 슬롯 실행이 멈춘다(검증자 N1). 또 평문 항목은 `?` 를 품지 못한다 — 한 줄 목록 안에서 `?` 는 평문을 끝내는 '키' 표지라
# `[a?b]` 를 PyYAML 이 읽지 못한다(N2). 큰따옴표 항목의 이스케이프를 JSON 이 아는 것으로 좁힌 것도 같은 이유다(`\q` 는 YAML 이 읽지 못한다).
_FM_FLOW_PLAIN = r"""[^\s,\[\]{}"'#&*!|>%@`:?-](?:[^,\[\]{}"'#:?\n]*[^\s,\[\]{}"'#:?\n])?"""
_FM_FLOW_ITEM = r"""(?:"(?:[^"\\\n]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"|'(?:[^'\n]|'')*'|""" + _FM_FLOW_PLAIN + ")"
_FM_FLOW_LIST = re.compile(r"\[[ \t]*(?:" + _FM_FLOW_ITEM + r"(?:[ \t]*,[ \t]*" + _FM_FLOW_ITEM + r")*(?:[ \t]*,)?[ \t]*)?\]")
_YAML_UNPRINTABLE = re.compile(r"[^\x09\x0a\x0d\x20-\x7e\xa0-\U00002027\U0000202a-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")      # PyYAML 이 읽지 못하는 글자 + YAML 이 줄바꿈으로 읽는 U+0085·U+2028·U+2029
# 머리말 한 줄 안의 날 U+0085·U+2028·U+2029 는 큰따옴표 값 안이면 NEL 이 공백으로 접혀 값이 바뀌고, 따옴표 없는 값 안이면 읽지 못하고, 키 줄 사이면 줄이 갈라져 다른 키가 끼어든다(검증자 N3).
_YAML_UNPRINTABLE_PROBLEM = "머리말에 YAML 이 읽지 못하는 제어 문자나 줄바꿈으로 읽는 U+0085·U+2028·U+2029 가 있음"
# 우리가 쓰는 JSON 한 줄에서는 그 세 글자를 `\uXXXX` 로 이스케이프한다: json.dumps(ensure_ascii=False) 는 날 글자로 두지만, JSON 과 YAML 이 같은 이스케이프를 읽어 값은 그대로 보존된다.
_YAML_LINE_BREAK_ESCAPES = {code: "\\u%04x" % code for code in (0x85, 0x2028, 0x2029)}


def _json_line(value):
    """`json.dumps(value, ensure_ascii=False)` — 단, YAML 이 줄바꿈으로 읽는 U+0085·U+2028·U+2029 는 `\\uXXXX` 로 이스케이프한다(머리말의 title·category·tags 와 엔진이 더하는 줄에 쓴다)."""
    return json.dumps(value, ensure_ascii=False).translate(_YAML_LINE_BREAK_ESCAPES)


def _fm_json_string(value):
    """한 줄 JSON 문자열(큰따옴표 안의 따옴표·역슬래시는 이스케이프)이면 그 글자를, 아니면 None 을 돌려준다."""
    if len(value) < 2 or value[0] != '"' or value[-1] != '"':
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        return None
    return parsed if isinstance(parsed, str) else None


def _fm_scalar_text(value):
    """한 줄 스칼라 값을 글자로 푼다(JSON 문자열·작은따옴표 문자열·평문). 풀 수 없는 모양이면 None."""
    if value.startswith('"'):
        return _fm_json_string(value)
    if value.startswith("'"):
        return value[1:-1].replace("''", "'") if re.fullmatch(r"'(?:[^'\n]|'')*'", value) else None
    return value if value and value[0] not in "[{" else None


def _fm_plain_ok(value):
    """따옴표 없는 값이 YAML 평문으로 안전한가: 표지 글자로 시작하지 않고 `: `·` #`·탭이 없다."""
    if value[0] in "[]{},#&*!|>'\"%@`":
        return False
    if value[0] in "-?:" and (len(value) == 1 or value[1] in " \t"):
        return False
    return not re.search(r"[ \t]#|:[ \t]|:\Z|\t", value)


def _fm_flow_list_ok(value):
    """한 줄 목록(`["가", "나"]`·`[가, 나]`·`['가']`)인가. 항목은 글자·숫자뿐이다(안쪽 목록·매핑·`:` 가 든 평문 항목은 받지 않는다)."""
    try:
        parsed = json.loads(value)
    except ValueError:
        return bool(_FM_FLOW_LIST.fullmatch(value))
    return isinstance(parsed, list) and all(item is None or isinstance(item, (str, int, float, bool)) for item in parsed)


def _fm_value_problem(key, value):
    """한 줄 값(앞뒤 공백을 뺀 비어 있지 않은 글)이 안전한 모양이 아닌 이유. 괜찮으면 None. 값의 뜻은 보지 않고 모양만 본다."""
    if len(value) > _FM_MAX_LINE:
        return "너무 김"
    if key == "title":
        text = _fm_json_string(value)
        if text is None:
            return "한 줄 JSON 문자열(큰따옴표 안의 따옴표·역슬래시는 이스케이프)이 아님"
        return None if text.strip() else "비어 있음"
    if key == "tags":      # 태그는 목록이어야 한다(`tags: "가, 나"` 같은 글자는 사이트가 목록으로 읽지 않는다). 값이 빈 블록 목록은 호출한 쪽이 따로 본다
        return None if value[0] == "[" and _fm_flow_list_ok(value) else "한 줄 목록([…])이 아님"
    if value[0] == '"':
        return None if _fm_json_string(value) is not None else "큰따옴표 문자열이 한 줄 JSON 으로 읽히지 않음"
    if value[0] == "'":
        return None if _fm_scalar_text(value) is not None else "작은따옴표 문자열이 닫히지 않음"
    if value[0] == "[":
        return None if _fm_flow_list_ok(value) else "한 줄 목록으로 읽히지 않음"
    return None if _fm_plain_ok(value) else "따옴표 없는 값으로 안전하지 않음(`: `·` #`·탭·YAML 표지 글자)"


def _fm_header_problems(header):
    """머리말 줄들의 모양 검사: (문제 목록, {키: [값, 이어진 목록 항목 수]}). 한 줄에 키 하나(`키: 값`)이고, 값이 빈 키에만 블록 목록 항목(`  - 값`)이 이어질 수 있다.
    문제 문장에는 키 이름만 들어가고 값은 들어가지 않는다(모델이 쓴 글이 로그에 실리지 않게)."""
    problems, keys, pending = [], {}, None
    for line in header:
        if not line.strip():
            continue
        found = _FM_KEY.match(line)
        if found:
            key, value = found.group(1), line[found.end():].strip()
            if key in keys:
                problems.append(f"`{key}` 키가 두 번 나옴")
            keys[key] = [value, 0]
            pending = None if value else keys[key]
            why = _fm_value_problem(key, value) if value else None
            if why:
                problems.append(f"`{key}` 값이 {why}")
            continue
        item = _FM_ITEM.fullmatch(line)
        if item and pending is not None:
            pending[1] += 1
            text = item.group(1).strip()
            if not text or _fm_value_problem("item", text):
                problems.append("블록 목록 항목이 안전한 모양이 아님")
            continue
        problems.append("`키: 값` 한 줄 모양이 아닌 줄이 있음")
    problems += [f"`{key}` 값이 비어 있음" for key, (value, count) in keys.items() if not value and not count]
    return problems, keys


def _fm_layout_problem(keys):
    """`layout` 줄이 있는데 값이 정확히 `post` 가 아니면 그 문제 문장을, 아니면 None. `post`·`"post"`·`'post'` 는 모두 post 로 읽혀 괜찮다. 줄이 없는 것은 여기서 보지 않는다(필수 키 검사와
    엔진이 맨 앞에 넣는 `layout: post` 가 맡는다). `default` 같은 다른 값은 사이트가 글 모양으로 그리지 못한다(검증자 N4)."""
    have = keys.get("layout")
    if have is not None and _fm_scalar_text(have[0]) != "post":
        return "`layout` 값이 post 가 아님"
    return None


def _source_front_fields(source):
    """add_discovery_metadata 가 머리말에 더하는 출처 세 줄의 값 (이름, 주소, 도메인). 더하지 않는 소스(주소가 http(s) 가 아니거나 이름·도메인이 없음)면 None."""
    if not source:
        return None
    source_url = str(source.get("link") or "").strip()
    parsed = urllib.parse.urlparse(source_url)
    if (parsed.scheme in {"http", "https"} and parsed.netloc and source.get("source") and source.get("publisher_domain")):
        return str(source.get("source")), source_url, str(source["publisher_domain"])
    return None


def front_matter_problems(content, source=None, allow_provenance=False):
    """완성된 글 한 편(머리말 + 본문)의 머리말과 본문 머리를 엄격히 검사해 문제 목록을 돌려준다(비어 있으면 정상).
    출처 표식 `provenance`(생성기 전용, docs/AI_FLOW.md)는 기본(allow_provenance=False)에서 머리말에 있으면 문제다 — 모델이 쓴 글에는 표식이 없다. allow_provenance=True 는 표식을 쓰는
    경로(구조화 Fact 글)와 저장소의 완성된 글을 읽는 시험 전용이고, 이때도 표식 키는 하나뿐이고 값이 정확히 facts 여야 한다(모르는 값·둘 이상은 문제).
    검사: 첫 줄이 정확히 `---`·닫는 `---` 줄·CR/BOM/제어 문자 없음·한 줄 한 키·키 중복 없음·값이 안전한 모양(`title` 은 한 줄 JSON 문자열)·필수 키(layout·title·
    category·lang·image)·layout 은 post(줄이 있으면)·lang 은 ko·en·본문이 울타리 줄이나 머리말 줄로 시작하지 않음. source(add_discovery_metadata 에 넘기는 소스 항목)를 주면 엔진이 더하는
    설명(본문에서 뽑을 수 있을 때)과 출처 세 줄이 있고 소스와 같은지도 본다 — `_front_matter_set` 이 머리말을 못 찾아 조용히 지나친 경우가 여기서 드러난다.
    문제 문장에는 값이 들어가지 않는다."""
    text = str(content or "")
    if text.startswith("\ufeff"):
        return ["글이 BOM 으로 시작함"]
    lines = text.split("\n")
    if lines[0] != "---":
        return ["첫 줄이 정확히 `---` 가 아님"]
    end = next((i for i in range(1, len(lines)) if _FM_FENCE.fullmatch(lines[i])), None)
    if end is None:
        return ["머리말을 닫는 `---` 줄이 없음"]
    problems = []
    if lines[end] != "---":
        problems.append("머리말을 닫는 줄이 정확히 `---` 가 아님")
    header, body = lines[1:end], lines[end + 1:]
    joined = "\n".join(header)
    if "\r" in joined:
        problems.append("머리말에 CR 줄바꿈이 섞여 있음")
    if _YAML_UNPRINTABLE.search(joined):
        problems.append(_YAML_UNPRINTABLE_PROBLEM)
    found, keys = _fm_header_problems(header)
    problems += found
    problems += [f"필수 키 `{key}` 줄이 없음" for key in _FM_REQUIRED if key not in keys]
    layout = _fm_layout_problem(keys)
    if layout:
        problems.append(layout)
    marks = [key for key in keys if key.lower() == provenance.KEY]
    if marks and not allow_provenance:
        problems.append("생성기 전용 출처 표식 키(`provenance`)가 머리말에 있음")
    elif marks and (len(marks) != 1 or _fm_scalar_text(keys[marks[0]][0]) != provenance.FACTS or marks[0] != provenance.KEY):
        problems.append("출처 표식(`provenance`)이 하나가 아니거나 값이 정확히 facts 가 아님")
    for key in ("category", "image"):
        have = keys.get(key)
        if have and have[0] and not (_fm_scalar_text(have[0]) or "").strip() and f"`{key}` 값이 비어 있음" not in problems:
            problems.append(f"`{key}` 값이 비어 있음")
    lang = keys.get("lang")
    if lang and lang[0] and _fm_scalar_text(lang[0]) not in ("ko", "en"):
        problems.append("`lang` 값이 ko·en 이 아님")
    head = []       # 본문의 앞 세 줄(빈 줄 제외)
    for line in body:
        if line.strip():
            head.append(line.rstrip("\r").lstrip("\ufeff"))
            if len(head) == 3:
                break
    if head and _FM_FENCE.fullmatch(head[0]):
        problems.append("본문이 `---` 울타리 줄로 시작함(이중 머리말 흔적)")
    elif any(_FM_RESIDUE.match(line) for line in head):
        problems.append("본문이 머리말 줄(`키: 값`)로 시작함")
    expected = _source_front_fields(source)
    if expected:
        for key, want in zip(("source_name", "source_url", "source_domain"), expected):
            have = keys.get(key)
            if have is None or _fm_scalar_text(have[0]) != want:
                problems.append(f"`{key}` 줄이 없거나 원문 정보와 다름")
        if _description_from_markdown(text) and "description" not in keys:
            problems.append("설명(`description`) 줄이 없음")
    return problems


def check_final_front_matter(data, source=None, languages=("ko", "en")):
    """validate_post_data 를 거친 data 의 두 글(languages 가 ko 뿐이면 국문 글 하나)에 설명·출처 줄까지 더해(실제로 파일이 될 모양으로) 머리말을 검사한다. 문제가 있으면 ValueError —
    깨진 글을 발행하느니 그 후보를 거절한다(본문 검증 실패와 같은 길)."""
    for prefix in _prefixes(languages):
        problems = front_matter_problems(add_discovery_metadata(data[f"{prefix}_content"], source), source)
        if problems:
            raise ValueError(f"{prefix.upper()} 글 머리말이 검사를 통과하지 못했습니다: " + " / ".join(problems[:3]))


def _fm_is_header_block(block):
    """울타리 둘 사이의 줄들이 '머리말 한 덩이'인가: 모든 줄이 머리말 모양(`키: 값`·목록 항목·들여쓴 줄·주석·빈 줄)이고 글 머리말의 키(layout·title·…)가 하나 이상 있다.
    키 모양 줄만 있는 글(예: `Note: …` 한 문단)을 머리말로 보고 버리지 않으려고 알려진 키를 요구한다."""
    return (all(not line.strip() or _FM_SHAPED.match(line) for line in block)
            and any(_FM_KNOWN_KEY.match(line) for line in block))


def _fm_extra_block(view, start):
    """view[start] 가 울타리 줄일 때, 다음 울타리 줄까지가 머리말 한 덩이(_fm_is_header_block)면 그 닫는 줄의 번호, 아니면 None.
    여는 울타리를 두 번 쓰거나 머리말을 두 번 쓴 응답을 알아보는 데 쓴다."""
    end = next((i for i in range(start + 1, len(view)) if _FM_FENCE.fullmatch(view[i])), None)
    if end is not None and _fm_is_header_block(view[start + 1:end]):
        return end
    return None


def _fm_body(lines, view):
    """머리말 뒤의 줄들에서 본문을 얻는다: 앞의 빈 줄, 구분선처럼 홀로 놓인 울타리 줄, 두 번째 머리말 한 덩이를 걷어낸다. (본문, 두 번째 머리말이 있었는가).
    view 는 판단에 쓰는 줄(CR 을 뺀 것), lines 는 본문에 쓰는 원래 줄이다 — 본문 글자는 걷어낸 앞부분 말고는 바꾸지 않는다."""
    i, doubled = 0, False
    while i < len(view):
        if not view[i].strip():
            i += 1
        elif _FM_FENCE.fullmatch(view[i]):
            extra = _fm_extra_block(view, i)
            if extra is None:
                i += 1
            else:
                doubled, i = True, extra + 1
        else:
            break
    return "\n".join(lines[i:]), doubled


def _split_model_content(content):
    """모델 응답 하나를 (종류, 머리말 줄 목록, 본문)으로 가른다.
    종류 — "none": 머리말이 없다(맨 앞이 울타리가 아니거나, 울타리가 닫히지 않았거나 사이가 머리말이 아니라 글이라 구분선으로 본 경우) ·
    "clean": 정확한 `---` 울타리 둘 사이의 머리말 하나 · "messy": 머리말은 있으나 울타리가 어긋나 있다(`------`·여는 울타리 두 번·머리말 두 번 …) — 이 줄들은 믿지 않는다.
    본문은 어느 경우에도 울타리(대시) 줄로 시작하지 않는다. 맨 앞이 울타리가 아닌 응답(종류 "none")의 본문은 응답 그대로다."""
    raw = str(content)
    lines = raw.lstrip("\ufeff").lstrip().split("\n")
    view = [line.rstrip("\r") for line in lines]
    if not _FM_FENCE.fullmatch(view[0]):
        return "none", [], raw
    exact = view[0].rstrip() == "---"
    end = next((i for i in range(1, len(view)) if _FM_FENCE.fullmatch(view[i])), None)
    if end is None:
        return "none", [], _fm_body(lines[1:], view[1:])[0]
    block = view[1:end]
    if not any(line.strip() for line in block):
        header = []       # 빈 머리말(`---\n---`)이거나, 여는 울타리를 두 번 쓴 것(`---\n---\n머리말…\n---`)
        extra = _fm_extra_block(view, end)
        if extra is not None:
            header, exact, end = view[end + 1:extra], False, extra
    elif _fm_is_header_block(block):
        header = block
    else:       # 첫 울타리와 다음 울타리 사이가 머리말이 아니라 글이다(구분선으로 시작한 글) — 글 머리말의 키가 하나도 없는 덩이는 머리말로 보고 버리지 않는다
        return "none", [], _fm_body(lines[1:], view[1:])[0]
    body, doubled = _fm_body(lines[end + 1:], view[end + 1:])
    return ("clean" if exact and view[end].rstrip() == "---" and not doubled else "messy"), header, body


def _model_header_problems(header):
    """모델이 쓴 머리말 줄을 그대로 보존해도 되는가: 안 되는 이유 목록(비어 있으면 보존한다). 한 줄 한 키 모양·키 중복 없음·값이 안전한 모양·`title` 이 한 줄 JSON 문자열이어야 하고,
    엔진이 지웠다 다시 쓰는 `lang`·`image` 는 한 줄 값이어야 한다(값이 비면 지우는 정규식이 다음 줄까지 지운다). `layout` 줄이 있으면 값이 정확히 post 여야 한다(없으면 엔진이 넣는다)."""
    problems, keys = _fm_header_problems(header)
    if "title" not in keys:
        problems.append("제목(`title`) 줄이 없음")
    layout = _fm_layout_problem(keys)
    if layout:
        problems.append(layout)
    if any(key.lower() == provenance.KEY for key in keys):      # 출처 표식은 생성기만 쓴다 — 모델이 쓴 표식은 머리말째 믿지 않고 구조화된 값으로 다시 쓴다(표식이 모델 글에 남지 않는다)
        problems.append("생성기 전용 출처 표식 키(`provenance`)가 모델이 쓴 머리말에 있음")
    problems += [f"`{key}` 는 한 줄 값이어야 함" for key in ("lang", "image") if key in keys and keys[key][1]]
    if _YAML_UNPRINTABLE.search("\n".join(header)):
        problems.append(_YAML_UNPRINTABLE_PROBLEM)
    return problems


def _fresh_front_matter(data, prefix, html_lang, image_url):
    """모델이 쓴 머리말을 믿지 않을 때 쓰는, 구조화된 값(제목·분야·태그)과 시스템 값(언어·이미지)으로 처음부터 쓴 머리말(닫는 울타리와 빈 줄까지)."""
    return (
        "---\nlayout: post\n"
        f"title: {_json_line(data[f'{prefix}_title'])}\n"
        f"category: {_json_line(data[f'{prefix}_category'])}\n"
        f"tags: {_json_line(data[f'{prefix}_tags'])}\n"
        f"lang: {html_lang}\nimage: {json.dumps(image_url)}\n---\n\n"
    )


def _front_matter_from_model(data, prefix, html_lang, image_url):
    """모델이 준 글 하나에 머리말을 붙여 (머리말이 붙은 글, 다시 쓴 이유)를 돌려준다. 이유는 모델이 쓴 머리말을 그대로 보존했거나 머리말이 아예 없었으면 None.
    머리말이 엄격 검사를 통과하면 모델이 쓴 줄을 지금까지처럼 보존하고(layout 이 없으면 맨 앞에 `layout: post`, lang·image 는 지웠다가 맨 끝에 다시 씀),
    통과하지 못하면 모델이 쓴 줄은 모두 버리고 구조화된 값으로 처음부터 다시 쓴다. 어느 쪽이든 본문은 걷어낸 앞부분(울타리 찌꺼기) 말고는 그대로다."""
    kind, header, body = _split_model_content(data[f"{prefix}_content"])
    reason = None
    if kind == "clean":
        problems = _model_header_problems(header)
        if not problems:
            front = "".join("\n" + line for line in header)   # 여는 울타리 줄 뒤의 줄들(맨 앞에 줄바꿈 하나)
            front = re.sub(r"(?m)^image:\s*.*$", "", front)
            front = re.sub(r"(?m)^lang:\s*.*$", "", front)
            front = re.sub(r"\n{2,}", "\n", front).rstrip()
            if not re.search(r"(?m)^layout\s*:", front):
                # 모델이 front matter 에서 layout 을 빼먹어도 다른 글·시험·도구와 같게 post 로 보장한다(2026-10-26 18시 글이 그랬다)
                rest = front.strip()
                front = "\nlayout: post" + ("\n" + rest if rest else "")
            front += f'\nlang: {html_lang}\nimage: "{image_url}"'
            return f"---{front}\n---\n\n{body}", None
        reason = problems[0]
    elif kind == "messy":
        reason = "머리말 울타리가 어긋남"
    return _fresh_front_matter(data, prefix, html_lang, image_url) + body, reason


def _prefixes(languages):
    """글 데이터(kr_*·en_*)의 접두사: 기본 ko·en 한 쌍이면 (kr, en), 레지스트리 chance.languages 가 ko 뿐이면 (kr,) — 영문은 만들지도 검사하지도 쓰지도 않는다."""
    return ("kr", "en") if tuple(languages) == ("ko", "en") else ("kr",)


def validate_post_data(data, kr_image, en_image, verified_source_url=None, notes=None, languages=("ko", "en")):
    """notes(목록)를 주면 모델이 쓴 머리말을 믿지 못해 다시 쓴 글마다 한 줄(이유 포함, 값은 없음)을 덧붙인다. languages 가 ko 뿐이면 국문 글만 읽고 검사한다(en_* 키가 없어도 된다)."""
    prefixes = _prefixes(languages)
    for key in tuple(f"{prefix}_{name}" for prefix in prefixes for name in ("category", "title", "content")):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"생성 결과의 {key} 값이 비었거나 문자열이 아닙니다.")
    for key in tuple(f"{prefix}_tags" for prefix in prefixes):
        if not isinstance(data.get(key), list):
            data[key] = []
        data[key] = [str(t).strip() for t in data[key] if str(t).strip()]

    for prefix, image_url in tuple(pair for pair in (("kr", kr_image), ("en", en_image)) if pair[0] in prefixes):
        html_lang = "ko" if prefix == "kr" else "en"
        content, reason = _front_matter_from_model(data, prefix, html_lang, image_url)
        if reason and notes is not None:
            notes.append(_one_line(f"{prefix.upper()} 머리말을 모델이 쓴 줄 대신 구조화된 값으로 다시 썼습니다({reason})"))     # 사유에는 키 이름만 있고 값은 없지만 로그에 찍는 글은 늘 접는다

        content = _front_matter_set(content, "category", data[f"{prefix}_category"])
        _validate_editorial_body(content, prefix, verified_source_url)

        if not re.search(r"(?m)^!\[[^\]]*\]\(", content):
            content = content.rstrip() + f"\n\n![Thumbnail]({image_url})\n"
        else:
            content = re.sub(
                r"(?m)^!\[[^\]]*\]\(https://images\.unsplash\.com/[^)]+\)",
                f"![Thumbnail]({image_url})", content, count=1)
        # 작가 출처 줄을 이미지 줄 바로 다음에 넣는다. 모델이 쓴 본문에 우리 모양의 출처 줄이 먼저 있어도 모두 지우고 우리가 만든 한 줄로 덮어쓴다(모델 출력은 데이터 — 위조 방지).
        content = unsplash_credit.place_credit(content, image_url, credit_line_for(image_url))
        data[f"{prefix}_content"] = content.rstrip() + "\n"
    return data


def _front_matter_set(content, key, value):
    """Set one safely quoted scalar in an existing Markdown front matter block.
    머리말을 찾지 못하면 글을 그대로 돌려준다(예외를 던지지 않는다). 그래서 줄이 조용히 빠질 수 있다 — 최종 머리말 검사(front_matter_problems)가
    첫 줄·필수 키·설명·출처 줄이 있는지 보고 문제로 드러낸다."""
    content = str(content or "").lstrip("\ufeff")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", content, re.S)
    if not match:
        return content
    front, body = match.groups()
    line = f"{key}: {_json_line(str(value))}"
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*:\s*.*$")
    if pattern.search(front):
        front = pattern.sub(lambda _: line, front, count=1)
    else:
        front = front.rstrip() + "\n" + line
    return f"---\n{front}\n---\n\n{body.lstrip()}"


def _description_from_markdown(content, max_chars=155):
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", str(content or ""), count=1, flags=re.S)
    text = unsplash_credit.strip_credit_lines(text)      # 이미지 아래 출처 줄(Photo by …)이 글의 설명이 되지 않게
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", paragraph)
        paragraph = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", paragraph)
        paragraph = re.sub(r"(?m)^\s{0,3}(?:#{1,6}\s*|>\s*)", "", paragraph)
        paragraph = re.sub(r"[*_`~]", "", paragraph)
        paragraph = re.sub(r"<[^>]+>", " ", paragraph)
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if len(paragraph) >= 60:
            if len(paragraph) > max_chars:
                paragraph = paragraph[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
            return paragraph
    return ""


def _content_lang(content, body):
    """글 언어(ko|en). validate_post_data 가 front matter 에 심은 lang 을 먼저 보고, 없으면 본문에 한글이 있는지로 가른다(영어 글에 한글 단어가 섞여도 영어로 본다)."""
    front = re.match(r"\A---\s*\n(.*?)\n---\s*\n", content, re.S)
    found = re.search(r"(?m)^lang:\s*[\"']?(ko|en)\b", front.group(1)) if front else None
    if found:
        return found.group(1)
    return "ko" if re.search(r"[가-힣]", body) else "en"


_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _citation_line(citation, source):
    """소스 약관이 정한 인용 형식(citation 틀의 {title}·{date}·{url})을 채운 한 줄. 제목·게시일·주소 중 하나라도 없으면 빈 문자열."""
    published = source.get("published")
    title = str(source.get("title") or "").strip().rstrip(".").strip()
    link = str(source.get("link") or "").strip()
    if not (isinstance(citation, str) and title and link and hasattr(published, "month")):
        return ""
    line = citation.format(title=title, date=f"{_MONTHS[published.month - 1]} {published.day}, {published.year}", url=link)
    return re.sub(r"([?!])\.(?=[”\"])", r"\1", line)   # 제목이 ?·! 로 끝나면 틀의 마침표를 겹쳐 쓰지 않는다("…warfare?.”" 방지)


def _append_source_notice(content, source):
    """소스 약관이 요구하는 인용 한 줄(citation)과 고지문(AI 작성·검토 안 받음)을 글 끝에 덧붙인다(인용, 고지문 순).
    글 언어(한글 포함 여부)에 맞춰 ko/en 고지문을 고르고, 이미 있는 것은 다시 붙이지 않는다."""
    body_match = re.match(r"\A---\s*\n.*?\n---\s*\n(.*)\Z", content, re.S)
    body = body_match.group(1) if body_match else content
    notice = source.get("notice")
    text = str(notice.get(_content_lang(content, body)) or "").strip() if isinstance(notice, dict) else ""
    for block in (_citation_line(source.get("citation"), source), f"*{text}*" if text else ""):
        if block and block not in content:
            content = content.rstrip() + f"\n\n{block}\n"
    return content


def add_discovery_metadata(content, source=None):
    description = _description_from_markdown(content)
    if description:
        content = _front_matter_set(content, "description", description)
    if source:
        fields = _source_front_fields(source)   # 최종 머리말 검사(front_matter_problems)가 같은 조건으로 이 세 줄이 있는지 본다
        if fields:
            source_name, source_url, source_domain = fields
            content = _front_matter_set(content, "source_name", source_name)
            content = _front_matter_set(content, "source_url", source_url)
            content = _front_matter_set(content, "source_domain", source_domain)
            body_match = re.match(r"\A---\s*\n.*?\n---\s*\n(.*)\Z", content, re.S)
            body = body_match.group(1) if body_match else content
            if source_url not in body:
                heading = "\n\n## 출처\n" if _content_lang(content, body) == "ko" else "\n\n## Sources\n"
                content = content.rstrip() + f"{heading}- [{source['source']}: {source.get('title', '원문 기사')}]({source_url})\n"
        content = _append_source_notice(content, source)
    return content


def safe_category_dir(category, prefix):
    category = str(category).strip()
    category = re.sub(r"[\x00-\x1f/\\]+", "-", category)
    category = re.sub(r"\.\.+", ".", category).strip(" .")
    if not category:
        category = f"{prefix} - Uncategorized"
    return POSTS_DIR / category


def now_kst():
    return datetime.datetime.now(KST)


def slot_state(history, now):
    """(슬롯, 코드)를 반환. 코드: DUE(만들 슬롯 있음) / OUT_OF_WINDOW(첫 게시 시각 전) /
    ALREADY_PUBLISHED(그 슬롯 글이 이미 있음). 두 가지 '할 일 없음'을 구분해 기록하기 위한 것이다."""
    started = [h for h in SLOT_HOURS if now.hour >= h]
    if not started:
        return None, "OUT_OF_WINDOW"
    slot = max(started)
    today = now.strftime("%Y-%m-%d")
    for item in history:
        if isinstance(item, dict) and item.get("date") == today and item.get("slot") == slot:
            return slot, "ALREADY_PUBLISHED"
    return slot, "DUE"


def current_due_slot(history, now):
    """지금 시각 기준으로 '이미 시작됐지만 아직 글이 없는' 가장 최근 슬롯 시각을 반환.
    스케줄 실행이 지연/누락돼도 다음 시간별 실행이 같은 슬롯을 보충한다.
    (오래된 슬롯을 한꺼번에 몰아서 만들지는 않는다)"""
    slot, state = slot_state(history, now)
    return slot if state == "DUE" else None


def _lane_report(lane, stats, found):
    """한 분야의 수집 결과를 요약 한 건으로 줄인다(받은 기사 → 통과 → 후보, 탈락 사유별 개수)."""
    sources = stats.get("sources", [])
    drops = {}
    for src in sources:
        for code, n in src.get("drops", {}).items():
            _count(drops, code, n)
    if stats.get("duplicates"):
        _count(drops, "DUPLICATE", stats["duplicates"])
    return {
        "lane": lane, "label": EDITORIAL_LANES[lane]["label"],
        "sources": len(sources),
        "failed_sources": sum(1 for s in sources if s.get("error")),
        "fetched": sum(s.get("fetched", 0) for s in sources),
        "passed": sum(s.get("kept", 0) for s in sources),
        "candidates": len(found),
        "drops": drops,
    }


def iter_candidate_lanes(titles, allow_auto_topic, lane_order, report, fallback=True,
                         clock=time.monotonic):
    """분야를 추첨 순서대로 시도해 후보가 나온 분야마다 (분야, 후보 목록)을 하나씩 내보내는 제너레이터(A).
    받는 쪽이 그 분야의 후보를 모두 탈락시키고 다음을 요청하면 그제서야 다음 분야를 읽는다 — 앞 분야의 후보가 모두 탈락해도 후보가 있는 다음 분야로 이어진다.
    이 단계는 Gemini 를 부르지 않아 비용은 수집 시간뿐이다. LANE_SEARCH_BUDGET_SECONDS 는 이 제너레이터를 시작한 때부터 센다 — 받는 쪽이 모델을 부르며 쓴 시간도 들어간다.
    넘으면 새 분야도, 분야 안의 남은 소스도 시도하지 않는다(소스 하나가 끝나는 시간만큼은 더 걸린다).
    끝까지 소비되면 report 에 budget_exceeded(시간 상한으로 건너뜀)와 sources_unreachable(시도한 소스가 전부 수집 실패)을 남긴다.
    후보를 하나도 못 냈으면 아무것도 내보내지 않고 끝난다."""
    started = clock()
    deadline = started + LANE_SEARCH_BUDGET_SECONDS
    tried = lane_order if fallback else lane_order[:1]
    attempted = failed = 0
    previous = None     # 앞서 후보를 냈던 분야(그 후보가 모두 탈락해 이어 읽는 중인지 가린다)
    for index, lane in enumerate(tried):
        if index and clock() > deadline:
            report["budget_exceeded"] = True
            print(f"::warning::분야 대체 시도를 시간 상한({LANE_SEARCH_BUDGET_SECONDS}초)에서 멈춥니다. "
                  f"{len(tried) - index}개 분야는 시도하지 못했습니다.")
            break
        if index:
            print(f"편집 축 대체 시도: {EDITORIAL_LANES[lane]['label']}")
        stats = {}
        found = pick_topic_candidates(titles, allow_auto_topic, lane, stats=stats,
                                      deadline=deadline, clock=clock)
        lane_report = _lane_report(lane, stats, found)
        report["lanes"].append(lane_report)
        attempted += lane_report["sources"]
        failed += lane_report["failed_sources"]
        if stats.get("time_skipped"):
            report["budget_exceeded"] = True
        if found:
            if previous is not None:
                print(f"::notice::'{EDITORIAL_LANES[previous]['label']}' 분야의 후보가 모두 탈락해 "
                      f"'{lane_report['label']}' 분야를 이어서 시도합니다.")
            elif index:
                print(f"::notice::'{EDITORIAL_LANES[lane_order[0]]['label']}' 분야에 후보가 없어 "
                      f"'{lane_report['label']}' 분야로 대체했습니다.")
            previous = lane
            yield lane, found
            continue
        print(skip_line("LANE_EMPTY", lane=lane, sources=lane_report["sources"],
                        failed=lane_report["failed_sources"], fetched=lane_report["fetched"],
                        passed=lane_report["passed"], reasons=lane_report["drops"]))
    report["sources_unreachable"] = attempted > 0 and failed == attempted


def collect_candidates(titles, allow_auto_topic, lane_order, report, fallback=True,
                       clock=time.monotonic):
    """분야를 추첨 순서대로 시도해 처음으로 후보가 나온 분야와 그 후보를 반환한다(iter_candidate_lanes 의 첫 항목).
    모든 분야가 비면 ([], 첫 분야). 글 만들기(generate_blog_posts)는 앞 분야의 후보가 모두 탈락해도 이어 가려고 iter_candidate_lanes 를 직접 쓴다."""
    for lane, found in iter_candidate_lanes(titles, allow_auto_topic, lane_order, report, fallback, clock):
        return found, lane
    return [], lane_order[0]


# 후보 탈락 종류(후보별 탈락 기록 report["rejects"] 의 kind). 공개 주석 한 줄과 실행 요약에 같은 이름으로 남는다(2026-11-04 gfix, F).
REJECT_LABELS = {
    "SKIP": "모델이 건너뜀(skip)",
    "FORMAT": "응답 형식 오류",
    "SIMILAR": "제목이 기존 글과 비슷",
    "BODY": "본문 검증 탈락",
}
REJECT_TITLE_CHARS = 40     # 공개 주석·요약에 싣는 후보 제목의 앞 글자 수
REJECT_REASON_CHARS = 80    # 사유(모델이 쓴 skip 사유·응답 형식 오류 종류·검증 문구)의 앞 글자 수
REJECT_LINE_MAX = 3500      # 공개 주석 한 줄의 상한


def _format_error_kind(exc):
    """응답 형식 오류의 종류: 예외 이름과, 모델이 쓴 글 조각이 붙기 전의 앞 문구(`문구: <모델 글 앞부분>` 에서 콜론 앞까지)."""
    return f"{type(exc).__name__}: {str(exc).split(':', 1)[0]}"


def _reject_record(lane, title, kind, detail=""):
    """후보 하나의 탈락 기록: 분야 이름·제목 앞 글자·종류 코드·사유 앞 글자. 공개 주석·실행 요약에 쓰이므로 만들 때 이미 가려 둔다(_public_text)."""
    return {"lane": EDITORIAL_LANES[lane]["label"], "title": _public_text(title or "(자동 선정)", REJECT_TITLE_CHARS),
            "kind": kind, "detail": _public_text(detail, REJECT_REASON_CHARS)}


def _tried_lane_labels(report):
    """후보를 모델에 보내 본 분야의 이름(순서대로, 중복 없음): 탈락한 후보의 분야들에, 글이 만들어졌다면 그 글이 나온 분야를 더한다."""
    labels = [r["lane"] for r in report.get("rejects") or []]
    if report.get("outcome") != "ALL_REJECTED" and report.get("lane_label"):
        labels.append(report["lane_label"])
    return list(dict.fromkeys(labels))


def reject_summary_line(report):
    """후보별 탈락 사유를 공개 주석 한 줄 글로(앞에 `::warning::`·`::notice::` 를 붙여 쓴다). 탈락 기록이 없으면 빈 문자열.
    들어가는 것: 종류별 개수(0 포함) · 시도한 분야와 후보 수 · 모델 호출 수 · 후보마다 분야·제목 앞 40자·종류·사유 앞 80자.
    모델·피드가 만든 글이므로 기록을 만들 때(_reject_record)와 한 줄로 합칠 때 모두 소독한다(비밀·URL 질의 가림, 개행·'::'·'##[' 무력화). 전체는 REJECT_LINE_MAX 자 안이다."""
    rejects = report.get("rejects") or []
    if not rejects:
        return ""
    tried = report.get("attempts") or len(rejects)
    lanes = _tried_lane_labels(report)
    counts = {}
    for r in rejects:
        _count(counts, r["kind"])
    kinds = " · ".join(f"{label} {counts.get(kind, 0)}" for kind, label in REJECT_LABELS.items())
    calls = report.get("gemini_calls") or GEMINI_CALLS
    head = (f"후보 {len(rejects)}건이 모두 탈락했습니다" if report.get("outcome") == "ALL_REJECTED"
            else f"앞선 후보 {len(rejects)}건이 탈락한 뒤 {tried}번째 후보로 글을 만들었습니다")
    scope = (f"분야 {len(lanes)}곳({', '.join(lanes)}) · 후보 {tried}건 시도 · "
             f"Gemini 호출 {calls.get('attempts', 0)}회(실패 {calls.get('failed', 0)}회) · {kinds}")
    parts = [f"[{r['lane']}] {r['title']} → {REJECT_LABELS.get(r['kind'], r['kind'])}" + (f": {r['detail']}" if r.get("detail") else "")
             for r in rejects]
    return _one_line(f"{head}({scope}) — " + " | ".join(parts), REJECT_LINE_MAX)


def reject_detail_lines(report):
    """실행 요약(마크다운)에 넣는 후보별 탈락 사유 줄 목록. 기록이 없으면 빈 목록. 칸마다 _md_cell 로 표·링크 문법을 막는다."""
    rejects = report.get("rejects") or []
    if not rejects:
        return []
    lanes = _tried_lane_labels(report)
    lines = [f"- 후보별 탈락 사유(분야 {len(lanes)}곳 · 후보 {report.get('attempts') or len(rejects)}건 시도):"]
    for r in rejects:
        detail = f": {_md_cell(r['detail'], REJECT_REASON_CHARS + 20)}" if r.get("detail") else ""
        lines.append(f"  - {_md_cell(r['lane'], 30)} · {_md_cell(r['title'], REJECT_TITLE_CHARS + 20)} → "
                     f"{_md_cell(REJECT_LABELS.get(r['kind'], r['kind']), 40)}{detail}")
    return lines


def quality_gate_config(settings):
    """레지스트리 설정(registry.chance_settings)이 quality_gate: hold 면 Gate 설정(건강 프로필을 읽어 넣는다), 아니면 None — 기본(off)에서는 Gate 를 부르지 않아 이전과 출력이 같다.
    건강 프로필을 읽지 못하면 RegistryError 로 멈춘다(약한 검사로 조용히 떨어지지 않고, 모델을 부르기 전에 멈춘다)."""
    if settings.quality_gate != "hold":
        return None
    profiles = tuple(registry.load_profile(name) for name in quality_gate.HEALTH_PROFILE_NAMES)
    return quality_gate.GateConfig(health_profiles=profiles, languages=settings.languages)


def generate_blog_posts(topic_override=None, category_hint="", slot=None,
                        allow_auto_topic=True, report=None, draft_flow=False):
    """KR/EN 글 한 쌍을 만든다(레지스트리 chance.languages 가 ["ko"] 면 국문 글 하나). 만들면 (kr_path, en_path — 국문 전용이면 None), 만들 수 없으면 None.
    report(dict)를 넘기면 분야별 수집 결과와 최종 결과 코드(outcome)를 채워 준다. 후보는 분야를 합쳐 MAX_ATTEMPTS 건까지 시도하고 앞 분야의 후보가 모두 탈락하면 다음 분야로 이어지며(A),
    후보별 탈락 기록(rejects)과 시도한 후보 수(attempts)도 채운다(공개 주석 한 줄과 실행 요약에 쓰인다, F).
    draft_flow=True 는 승인 흐름(publish_flow: pr)이다: 글을 만드는 방법은 같고, 이력 항목에 flow·branch·paths 를 더하며 결과 코드는
    PUBLISHED 대신 DRAFT_CREATED 다(공개는 PR 병합이라 '발행했다'고 쓰지 않는다). 파일 올리기는 pipeline/draft_flow.py 가 맡는다."""
    report = report if report is not None else {}
    report.setdefault("lanes", [])
    settings = registry.chance_settings()           # (quality_gate, languages): 기본 (off, ko·en) — 읽지 못하거나 값이 틀리면 RegistryError 로 멈춘다
    gate_config = quality_gate_config(settings)     # off 면 None
    langs = settings.languages
    prefixes = _prefixes(langs)                     # ("kr", "en") 한 쌍(기본) 또는 ("kr",) 국문 전용
    lang_args = {} if len(prefixes) == 2 else {"languages": langs}      # 기본(한 쌍)에서는 아래 호출이 예전 그대로다 — 국문 전용일 때만 언어를 넘긴다
    if source_policy.chance_content_source() == source_policy.CONTENT_FACTS:      # 구조화 Fact 경로(content_source: facts): 피드·기사·모델·사진을 쓰지 않는 별도 함수가 처음부터 끝까지 맡는다. 기본(feed)에서는 이 줄이 레지스트리 값을 읽을 뿐 아무 일도 하지 않는다
        return generate_fact_post(gate_config, report, slot=slot, draft_flow=draft_flow, topic_override=topic_override)
    posts = load_posts(for_ai=True)      # 표식 글은 빠진 목록 — 아래 titles[-30:] 가 프롬프트의 '최근 다룬 제목' 으로 AI 에 간다
    history = read_history()
    source_mode = source_policy.chance_source_policy()     # 'legacy'(기본 — 이전과 같다) | 'allowlist'
    if source_policy.idle_check(source_mode, report, now_kst, print):   # allowlist 인데 ACTIVE 콘텐츠 Provider 가 0 — 네트워크·모델 호출 없이 초록으로 끝(SOURCE_POLICY_NO_ACTIVE_PROVIDER)
        return None
    lane_order = editorial_lane_order(slot, history)
    editorial_lane = lane_order[0]
    print(f"편집 축: {EDITORIAL_LANES[editorial_lane]['label']}")
    titles = existing_titles(history, posts, for_ai=True)
    used = used_keys_from_posts(posts)
    for item in history:
        if isinstance(item, dict):
            for k in ("kr_image", "en_image"):
                if item.get(k):
                    used.add(image_key(item[k]))

    recent_titles = source_policy.prompt_titles(source_mode, titles, history)[-30:]   # allowlist: 이력의 외부 글 제목은 '최근 다룬 제목'에도 넣지 않는다
    data, selected, selected_item = None, None, None
    if topic_override:
        verified = fetch_news_items(editorial_lane)
        matched = next((it for it in verified
                        if is_similar_to_any(topic_override, [it["title"]], 0.35)), None)
        if not matched:
            print("요청 주제와 직접 연결되고 출처 검증을 통과한 기사가 없습니다. 발행을 중단합니다.")
            report["outcome"] = "NO_MATCH"
            return None
        batches = iter([(editorial_lane, [dict(matched, title=topic_override)])])
    else:
        # 분야별 후보 묶음을 앞에서부터 하나씩 받는다. 앞 분야의 후보가 모두 탈락하면 다음 분야를 이어서 읽는다(분야 합산 MAX_ATTEMPTS 건까지, 시간 상한 안에서 — A).
        batches = iter_candidate_lanes(titles, allow_auto_topic, lane_order, report)
    batches = source_policy.own_title_batches(source_mode, batches, lambda n: print(f"  자체 제목이 없는 후보 {n}건은 쓰지 않음(source_policy: allowlist)"))   # allowlist: 후보는 자체 제목만 가진다
    report["lane"] = editorial_lane
    report["lane_label"] = EDITORIAL_LANES[editorial_lane]["label"]
    gate_rejects = report["gate_rejects"] = []
    rejects = report["rejects"] = []    # 후보별 탈락 기록(분야·제목 앞 글자·종류·사유) — 공개 주석 한 줄과 실행 요약에 쓴다(F)
    attempts = report["attempts"] = 0   # 이번 실행에서 모델에 보내 본 후보 수(분야 합산)

    def attempt_stream():
        """(분야, 후보)를 하나씩 내보낸다. 이 분야의 후보를 다 썼는데도 글이 없으면 그때서야 다음 분야를 읽는다 — 수집은 느리므로 시도 상한에 닿았으면 읽지 않는다."""
        for lane, found in batches:
            for entry in found:
                if attempts >= MAX_ATTEMPTS:
                    return
                yield lane, entry
            if attempts >= MAX_ATTEMPTS:
                return

    for editorial_lane, item in attempt_stream():
        attempts += 1
        report["attempts"] = attempts
        report["lane"] = editorial_lane                 # 글의 분야·프롬프트·이력에는 후보가 실제로 나온 분야가 쓰인다
        report["lane_label"] = EDITORIAL_LANES[editorial_lane]["label"]
        topic = item["title"] if item else None
        src_label = f" [{_one_line(item['source'], 60)}]" if item and item.get("source") else ""
        print(f"주제 시도: {_one_line(topic or '(자동 선정)', 200)}{src_label}")
        try:
            if STUB_GEMINI:
                candidate = stub_post_data(topic, (item or {}).get("link"))
            else:
                # 모든 모델이 실패하면 RuntimeError 로 그대로 올라간다(인프라 장애 = 빨강).
                resp = call_gemini_with_fallback(build_post_prompt(
                    item, recent_titles, category_hint, allow_skip=not topic_override,
                    editorial_lane=editorial_lane, **lang_args))
                candidate = extract_json_object(resp.text)
        except ValueError as exc:  # 모델이 JSON 을 못 맞춘 것은 이 후보의 탈락이다
            reason = _one_line(exc, 200)
            print(f"  Gemini 응답을 읽지 못해 이 후보는 건너뜀: {reason}")
            gate_rejects.append(reason)
            rejects.append(_reject_record(editorial_lane, topic, "FORMAT", _format_error_kind(exc)))
            continue
        if candidate.get("skip") is True:
            print(f"  Gemini가 중복 주제로 판단해 건너뜀: {_one_line(candidate.get('reason', ''))}")
            rejects.append(_reject_record(editorial_lane, topic, "SKIP", candidate.get("reason", "")))
            continue
        kr_t, en_t = str(candidate.get("kr_title", "")), str(candidate.get("en_title", ""))
        if not topic_override and (is_similar_to_any(kr_t, titles, 0.7)
                                   or is_similar_to_any(en_t, titles, 0.7)):
            print(f"  생성된 제목이 기존 글과 비슷해 폐기: {_one_line(kr_t, 150)} / {_one_line(en_t, 150)}")
            best = max(max((similarity(t, e) for e in titles), default=0.0) for t in (kr_t, en_t))
            rejects.append(_reject_record(editorial_lane, topic, "SIMILAR", f"유사도 {best:.2f}(기준 0.70)"))
            continue
        try:
            # 본문 검증(분량·원문 링크 인용)은 이미지를 고르기 전에 먼저 한다: 탈락한 후보에 Unsplash 호출을 쓰지 않고,
            # 첫 후보의 본문이 얇다는 이유로 실행 전체를 빨갛게 만들지 않고 다음 후보를 시도한다(검증 기준은 그대로).
            # 설명·출처 줄까지 더한 최종 머리말도 여기서 미리 검사한다(D-80): 깨진 글을 발행하느니 이 후보를 거절하고 다음 후보를 시도한다.
            checked = validate_post_data(copy.deepcopy(candidate), "https://example.invalid/kr.jpg",
                                         "https://example.invalid/en.jpg",
                                         verified_source_url=(item or {}).get("link"), **lang_args)
            check_final_front_matter(checked, item, **lang_args)
            if gate_config is not None:    # 최소 품질 Gate(chance.quality_gate: hold): 걸리면 QualityHold(ValueError) → 아래에서 '본문 검증 탈락'과 같은 길로 이 후보를 버린다
                quality_gate.require_pass(quality_gate.check_candidate(checked, item, history, gate_config, as_of=now_kst().date()))
        except ValueError as exc:
            reason = _one_line(exc, 200)
            print(f"  본문 검증 탈락: {reason}")
            gate_rejects.append(reason)
            rejects.append(_reject_record(editorial_lane, topic, "BODY", reason))
            continue
        data, selected, selected_item = candidate, topic, item
        break
    if not attempts:
        print("쓸 만한 새 기사가 없습니다. 글을 만들지 않습니다.")
        # 이상 신호(빨강)는 '소스에 접속하지 못함'과 '모든 분야에 검증된 기사가 한 건도 없음'이다.
        # 검증된 기사는 있었지만 전부 기존 글과 비슷하면 뉴스가 뜸한 것이라 경고 수준이고, 시간 상한으로 일부만 시도했을 때도 경고다.
        if report.get("sources_unreachable"):
            report["outcome"] = "SOURCES_UNREACHABLE"
        elif report.get("budget_exceeded"):
            report["outcome"] = "NO_CANDIDATES"
        elif any(lane["passed"] > 0 for lane in report.get("lanes", [])):
            report["outcome"] = "ALL_DUPLICATES"
        else:
            report["outcome"] = "ALL_LANES_EMPTY"
        return None
    if data is None:
        report["outcome"] = "ALL_REJECTED"
        line = reject_summary_line(report)
        if line:
            print(f"::warning::{line}")   # 후보마다 왜 탈락했는지 공개 주석 한 줄로 남긴다(로그인 없이 공개 REST 로 읽힌다)
        if not topic_override and not allow_auto_topic:
            print("통과한 후보가 없습니다(중복·Gemini 건너뜀·본문 검증 탈락). 글을 만들지 않습니다.")
            return None
        # 예외로 끝나는 실행(수동·주제 지정)은 finish_run 의 요약을 쓰지 못하고 run_cli 가 '실패' 요약만 남기므로, 후보별 탈락 사유 블록을 따로 남긴다.
        write_step_summary("\n".join(["### Chance_Blog 후보 탈락 사유"] + reject_detail_lines(report)))
        raise RuntimeError("후보가 모두 탈락해 글을 만들지 못했습니다(중복·Gemini 건너뜀·본문 검증 탈락).")

    if not selected_item or not selected_item.get("link") or not selected_item.get("publisher_domain"):
        raise RuntimeError("검증된 게시자 원문이 없어 글을 저장하지 않습니다.")

    queries = [q for q in data.get("image_queries", []) if isinstance(q, str)]
    if not queries:
        queries = ["technology", "computer hardware"]
    images = pick_images(queries, used, len(prefixes), allow_pool=True)
    if len(images) < len(prefixes):
        raise RuntimeError(f"사용 가능한 대표 이미지를 {len(prefixes)}개 확보하지 못했습니다. "
                           "글을 저장하지 않습니다.")
    kr_image, en_image = images[0], (images[1] if len(prefixes) == 2 else None)
    repairs = []
    data = validate_post_data(
        data, kr_image, en_image,
        verified_source_url=(selected_item or {}).get("link"),
        notes=repairs, **lang_args,
    )
    for repair in repairs:
        print(f"[참고] {repair}")

    now = now_kst()
    date_str, time_str = now.strftime("%Y-%m-%d"), now.strftime("%H%M%S")
    selected_item["title"] = selected_item.get("title") or selected or "원문 기사"
    for prefix in prefixes:
        data[f"{prefix}_content"] = add_discovery_metadata(data[f"{prefix}_content"], selected_item)
    for prefix in prefixes:
        # 마지막 방어선: 위 후보 검사가 통과했어도(자리표시 이미지로 한 검사) 실제 이미지·출처로 완성한 글의 머리말이 깨졌으면 파일을 쓰지 않는다
        problems = front_matter_problems(data[f"{prefix}_content"], selected_item)
        if problems:
            raise RuntimeError(f"{prefix.upper()} 글 머리말이 검사를 통과하지 못해 글을 저장하지 않습니다: " + " / ".join(problems[:3]))
    for prefix, image_url in zip(prefixes, (kr_image, en_image)):
        # 마지막 방어선(출처): 사진 고르기를 통과했어도 작가 출처를 알 수 없는 사진이면 글을 저장하지 않는다(Unsplash 지침 — 출처 없는 사진을 새 글에 쓰지 않는다)
        if not credit_line_for(image_url):
            raise RuntimeError(f"{prefix.upper()} 대표 이미지의 작가 출처를 알 수 없어 글을 저장하지 않습니다.")
    kr_path = safe_category_dir(data["kr_category"], "KR") / f"{date_str}-KR-{time_str}.md"
    en_path = safe_category_dir(data["en_category"], "EN") / f"{date_str}-EN-{time_str}.md" if len(prefixes) == 2 else None
    written = [path for path in (kr_path, en_path) if path is not None]      # 글 파일: 국문 하나 또는 국문·영문 두 개(이 순서)

    write_text_atomic(kr_path, data["kr_content"])
    if en_path is not None:
        try:
            write_text_atomic(en_path, data["en_content"])
        except Exception:
            if not DRY_RUN:
                kr_path.unlink(missing_ok=True)
            raise

    entry = {
        "date": date_str, "topic": selected or "(자동 선정)",
        "kr_title": data["kr_title"], "en_title": data.get("en_title"),
        "kr_image": kr_image, "en_image": en_image, "slot": slot,
        "lane": editorial_lane,
        "source": (selected_item or {}).get("source", ""),
        "source_url": (selected_item or {}).get("link", ""),
    }
    if len(prefixes) == 1:      # 국문 전용(chance.languages = ["ko"]): 영문 칸을 두지 않고 어떤 언어로 만들었는지 적는다
        del entry["en_title"], entry["en_image"]
        entry["languages"] = list(langs)
    if draft_flow:
        entry.update(drafts.entry_fields(date_str, slot, time_str, written))
        report["draft_branch"] = entry["branch"]
    history.append(entry)
    write_history(history)
    trigger_download(kr_image)
    if en_image:
        trigger_download(en_image)
    report.update(outcome="DRAFT_CREATED" if draft_flow else "PUBLISHED", title=data["kr_title"], en_title=data.get("en_title"),
                  source=(selected_item or {}).get("source", ""),
                  paths=[str(path) for path in written])
    notice = reject_summary_line(report)   # 앞선 후보가 탈락한 뒤에 만든 글이면 그 사유를 공개 주석 한 줄로(첫 후보로 만들었으면 아무것도 하지 않는다)
    if notice:
        print(f"::notice::{notice}")
    print("블로그 글 생성 완료" + (" (DRY_RUN: 파일·기록은 저장되지 않았습니다):" if DRY_RUN else ":"))
    print(f"- KR: {kr_path}\n" + (f"- EN: {en_path}\n" if en_path is not None else "")
          + f"- 편집 축: {EDITORIAL_LANES[editorial_lane]['label']}\n- 주제: {_one_line(selected or '(자동 선정)', 200)}")
    print(f"- 이미지: {kr_image}" + (f"\n         {en_image}" if en_image else ""))
    if draft_flow:
        print(f"- 승인 흐름: 연습 실행이라 초안 브랜치 {entry['branch']} 를 올리지 않습니다" if DRY_RUN
              else f"- 승인 흐름: 초안 브랜치 {entry['branch']} 로 올립니다(PR 을 병합하면 공개, 닫으면 폐기)")
    return kr_path, en_path


# ============================================================
# 구조화 Fact 경로(레지스트리 chance.content_source: facts) — S2b
# ============================================================
# 이 구역의 함수는 AI 를 한 번도 부르지 않는다. 진입 함수 generate_fact_post 와 그 함수가 부르는 곳은 정적 규칙 AF4·AF8 이 읽는다(tests/ai_flow_scan.py 의 DEFAULT_ENTRIES) —
# 그러니 이 구역에서 피드·기사 발췌·구글 뉴스 해석기·Gemini 호출·프롬프트 조립·사진 선택·이미지 검색어 함수를 부르거나 이름으로 참조하지 않는다.
# 기본(content_source 가 없거나 feed)에서는 이 구역이 한 번도 실행되지 않는다. 켜는 것은 T3 — 설명: docs/FACT_PATH.md §15
FACT_CARD_PATH = "assets/fact-card.svg"            # 모든 Fact 글이 같이 쓰는 저장소 안 자체 카드 이미지(사진 아님 — 로고·상표·외부 자원이 없는 추상 그림)
FACT_CARD_FILE = Path(__file__).resolve().parent / FACT_CARD_PATH
FACT_CONFIG_FILE = Path(__file__).resolve().parent / "_config.yml"
FACT_LANE_LABEL = "구조화 공개 자료"                 # 실행 요약의 '편집 축' 칸에 쓰는 이름(Fact 글은 편집 분야 추첨을 거치지 않는다)
FACT_USER_AGENT = UA
PreparedFact = namedtuple("PreparedFact", "post candidate content marked gate_source image")      # 파일이 될 글 한 편: 조립된 글·후보·표식 전 글·표식이 든 글·Gate 에 넘기는 source·이미지 주소


def fact_site_url(config_path=None):
    """사이트 주소(`_config.yml` 의 url + baseurl, 끝 슬래시 없음) — 공개 값을 읽기만 한다. 읽을 수 없거나 모양이 올바르지 않으면 RuntimeError(자체 이미지 주소를 만들 수 없어 글을 만들지 않는다)."""
    try:
        text = Path(config_path or FACT_CONFIG_FILE).read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("사이트 설정(_config.yml)을 읽을 수 없어 자체 이미지 주소를 만들지 못합니다.") from exc
    url = re.search(r"(?m)^url:[ \t]*[\"']?([^\"'\s#]+)[\"']?[ \t]*(?:#.*)?$", text)
    base = re.search(r"(?m)^baseurl:[ \t]*[\"']?([^\"'\s#]*)[\"']?[ \t]*(?:#.*)?$", text)
    prefix = base.group(1).rstrip("/") if base else ""
    if not url or not re.fullmatch(r"https://[A-Za-z0-9.\-]+(?::\d{1,5})?", url.group(1).rstrip("/")) or (prefix and not re.fullmatch(r"/[A-Za-z0-9._~\-/]*", prefix)):
        raise RuntimeError("사이트 설정(_config.yml)의 url·baseurl 모양이 올바르지 않아 자체 이미지 주소를 만들지 못합니다.")
    return url.group(1).rstrip("/") + prefix


def fact_card_url(config_path=None):
    """Fact 글 머리말 `image` 에 쓰는 자체 카드 이미지의 https 절대 주소(사이트 주소 + `assets/…`)."""
    return f"{fact_site_url(config_path)}/{FACT_CARD_PATH}"


def _fact_gunzip(body, limit):
    """gzip 으로 온 응답을 풀되 풀린 크기가 limit 를 넘으면 거기서 자른다(압축 폭탄 방어 — 어댑터가 상한 초과(TOO_LARGE)로 거절한다). 풀 수 없는 응답은 ValueError."""
    try:
        unpacked = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(body, limit)
    except zlib.error as exc:
        raise ValueError("gzip 응답을 풀 수 없습니다") from exc
    return unpacked


def make_fact_transport(sources):
    """실제 호출 한 번을 하는 transport(url, *, timeout, max_bytes) -> bytes 를 만든다 — 허용 목록(Registry)이 판정하는 검사된 opener(리다이렉트 0번: 호출 한 번이 요청 한 번)로 보내고
    응답은 max_bytes + 1 바이트까지만 읽는다(넘으면 어댑터가 거절한다). gzip 을 요청하고(호출 한도 own.request_gzip) 받으면 풀어서 돌려준다. 시험은 이 함수를 가짜로 바꾼다(시험은 네트워크에 접속하지 않는다)."""
    opener = egress.build_checked_opener("fact", sources, max_redirects=0)
    return lambda url, *, timeout, max_bytes: _fact_fetch(opener, url, timeout, max_bytes)      # 이름 있는 안쪽 함수 대신 람다: 정적 규칙(AF4)이 호출을 이 함수의 것으로 읽어 전부 훑는다


def _fact_fetch(opener, url, timeout, max_bytes):
    """검사된 opener 로 요청 한 번을 보내 응답 본문을 돌려준다(gzip 이면 풀어서). max_bytes + 1 바이트까지만 읽는다."""
    request = urllib.request.Request(url, headers={"User-Agent": FACT_USER_AGENT, "Accept": "application/json", "Accept-Encoding": "gzip"})
    with opener.open(request, timeout=timeout) as response:
        body = response.read(max_bytes + 1)
        packed = str(response.headers.get("Content-Encoding", "")).strip().lower() == "gzip"
    return _fact_gunzip(body, max_bytes + 1) if packed else body


def fact_opener(sources, provider, access, transport=None):
    """어댑터에 주입하는 opener 와 그 호출 예산(CallBudget)을 만든다 — 연결 코드 한 군데(D-233). transport(실제 호출 한 번)를 ① 허용 목록 관문(`egress.check_url` — 허용 목록 밖·ACTIVE 가 아닌 Provider·
    허용 밖 경로면 어댑터 오류 `EGRESS_DENIED`) ② 호출 예산(`egress.budgeted` — 한 실행의 호출 상한·같은 주소 성공 응답 재사용·403·429 면 그 실행에서 Provider 중지·404 면 그 주소 중지·실패 3회 뒤 건너뜀,
    막히면 어댑터 오류 `BUDGET_DENIED`)으로 감싼다. 호출 한도를 모르는 Provider 는 한 실행의 상한이 0 이라 어떤 호출도 나가지 않는다(닫힌 쪽). transport 를 안 주면 실제 호출(`make_fact_transport`)이다."""
    budget = egress.budget_for(provider.provider_id, access.rate_limit)
    send = egress.budgeted(transport if transport is not None else make_fact_transport(sources), budget)
    return (lambda url, *, timeout, max_bytes: _fact_send(sources, send, url, timeout, max_bytes)), budget


def _fact_send(sources, send, url, timeout, max_bytes):
    """주입되는 opener 한 번의 호출: 관문 판정 → 호출 예산을 거친 호출. 관문·예산이 막으면 어댑터 오류(`EGRESS_DENIED`·`BUDGET_DENIED`)로 바꿔 올린다(요청은 나가지 않았다)."""
    try:
        egress.check_url(url, "fact", sources)
        return send(url, timeout=timeout, max_bytes=max_bytes)
    except egress.EgressDenied:
        raise fact_supply.AdapterError("EGRESS_DENIED") from None
    except egress.CallBudgetDenied as exc:
        raise fact_supply.AdapterError("BUDGET_DENIED", exc.code) from None


def fact_file_text(post, image_url):
    """조립된 Fact 글(AssembledPost)을 파일이 될 모양(머리말 + 본문 + 설명·출처 세 줄)으로 만든다 — 머리말은 생성기의 기존 함수가 쓰고(제목·분류·태그는 조립기 값, 사진은 자체 카드 이미지 주소 하나)
    표식은 아직 없다. 돌려주는 값: (글, 머리말 검사에 넘기는 소스 사전)."""
    data = {"kr_title": post.title, "kr_category": post.category, "kr_tags": list(post.tags)}
    source = {"link": post.source_url, "source": post.source_name, "publisher_domain": post.source_domain, "title": post.source_name}
    content = add_discovery_metadata(_fresh_front_matter(data, "kr", "ko", image_url) + post.body_markdown, source)
    return content.rstrip() + "\n", source


def fact_context(now):
    """facts 분기를 시작해도 되는지 파일에서 읽어 점검한다(읽기만 한다 — 요청을 보내지 않는다). 켜기 전 안전장치(D-232): content_source 가 facts·source_policy 가 allowlist·레지스트리 검증 오류 0·
    Provider 가 ACTIVE(enabled·strict_tier·기한)이고, 더해서 NOAA api 접근 경로와 자체 카드 이미지 파일·그 주소를 만들 사이트 주소(_config.yml)가 있어야 한다. 돌려주는 값: (문제 문장 목록, 허용 목록 Registry 또는 None,
    Provider 또는 None, api 접근 경로 또는 None) — 문제가 하나라도 있으면 호출한 쪽은 글을 만들지 않는다."""
    problems, sources = source_policy.fact_start(now.date(), fact_supply.PROVIDER_ID)
    provider = sources.get(fact_supply.PROVIDER_ID) if sources is not None else None
    access = fact_supply.api_access(provider) if provider is not None else None
    if provider is not None and access is None and not problems:
        problems.append(f"{fact_supply.PROVIDER_ID} 에 NOAA api 접근 경로가 없음")
    if not FACT_CARD_FILE.is_file():
        problems.append(f"자체 카드 이미지 파일({FACT_CARD_PATH})이 없음")
    try:
        fact_card_url()
    except RuntimeError as exc:
        problems.append(str(exc))
    return problems, sources, provider, access


def fact_prepare(now, history, sources, provider, access, limit=1, gate_config=None, transport=None):
    """Fact 글 후보를 만든다 — 읽기 전용(파일·이력에 쓰지 않는다. 그림자 실행도 이 함수를 쓴다). 공급 함수(fact_supply.supply)가 이력의 발행일로 차례를 정하고 후보마다 어댑터 → 조립기를 돌리며,
    후보마다 이 함수가 넘기는 검사(accept)가 ① 머리말·본문·설명·출처 줄·표식까지 더한 최종 글의 머리말 검사(front_matter_problems(…, allow_provenance=True)) ② gate_config 가 있으면(chance.quality_gate: hold)
    최소 품질 Gate 를 돌린다 — Gate 에는 `fact_supply.gate_source` 의 사전(`fact_post`·`evidence_text`·`provider_hosts`…)을 넘긴다. 거절된 후보는 건너뛰고 다음 글감으로 넘어간다.
    표식은 여기 한 군데에서만 쓴다(provenance.with_marker — 시험 MARKER_WRITERS). 돌려주는 값: (PreparedFact 목록, SupplyResult)."""
    image = fact_card_url()
    opener, _budget = fact_opener(sources, provider, access, transport)
    prepared = []
    result = fact_supply.supply(today=now.date(), retrieved_at=now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), history=history, provider=provider, opener=opener, limit=limit,
                                accept=lambda post, candidate: fact_check_post(post, candidate, image, provider, history, now, gate_config, prepared))      # 람다: 이름 있는 안쪽 함수 대신 — 정적 규칙(AF4)이 이 호출도 이 함수의 것으로 읽는다
    return prepared, result


def fact_check_post(post, candidate, image, provider, history, now, gate_config, prepared):
    """후보 글 한 편의 검사(공급 함수의 accept): 파일이 될 글을 만들고(fact_file_text) 표식을 더한 뒤(여기 한 군데 — provenance.with_marker) ① 최종 머리말 검사 ② gate_config 가 있으면 최소 품질 Gate 를 돌린다.
    통과하면 prepared 에 더하고 None, 거절이면 사유 코드(글자). 표식이 든 글이 검사에 넘어가는 것이고 Gate 에는 표식 전 글을 넘긴다(피드 글의 Gate 입력과 같은 모양 — 머리말 한 줄이 본문 규칙에 쓰이지 않는다)."""
    content, source = fact_file_text(post, image)
    try:
        marked = provenance.with_marker(content)
    except ValueError:
        return "MARKER_ERROR"
    if front_matter_problems(marked, source, allow_provenance=True):
        return "FRONT_MATTER"
    gate_source = fact_supply.gate_source(post, provider)
    if gate_config is not None:
        report = quality_gate.check_candidate({"kr_title": post.title, "kr_content": content}, gate_source, history, gate_config, as_of=now.date())
        if report.holds:
            return "GATE:" + "+".join(report.codes())
    prepared.append(PreparedFact(post, candidate, content, marked, gate_source, image))
    return None


def fact_history_entry(item, now, slot):
    """Fact 글의 이력 항목. `topic`·`kr_title` 은 조립기의 자체 제목이고(외부 제목이 없다), 중복 방지·차례 정하기에 쓰는 칸(candidate_key·dedupe_key·recipe_id·as_of·content_source)이 더해지며,
    출처 표식(`provenance: facts`)이 붙는다 — AI 입력을 만드는 읽기(최근 제목 등)가 이 항목을 건너뛴다(docs/AI_FLOW.md). 영문 칸은 없다(국문 단독)."""
    post = item.post
    entry = {"date": now.strftime("%Y-%m-%d"), "topic": post.title, "kr_title": post.title, "kr_image": item.image, "slot": slot,
             "source": post.source_name, "source_url": post.source_url, "languages": ["ko"],
             "candidate_key": item.candidate.candidate_key, "dedupe_key": post.dedupe_key, "recipe_id": post.recipe_id, "as_of": post.as_of, "content_source": source_policy.CONTENT_FACTS}
    return provenance.entry_with_marker(entry)


def fact_notes(result):
    """공급 결과를 사람이 읽는 줄로(고정 글자뿐 — 글감 이름·사유 코드): 건너뛴 글감마다 한 줄, 기다리는 글감이 있으면 한 줄."""
    notes = [f"Fact 글감 {spec_id} 건너뜀: {code}" for spec_id, code in result.skipped]
    if result.waiting:
        notes.append(f"Fact 글감 {result.waiting} 은(는) 일별 제품의 협정 세계시 하한 때문에 기다림")
    return notes


def fact_stop(report, outcome, lines):
    """글을 만들지 않고 끝낸다(예외 없음 — 이력·파일을 바꾸지 않는다). lines 가 있으면 이유를 한 줄로 남기고 결과 코드를 적는다."""
    if lines:
        print("[구조화 Fact] 글을 만들지 않습니다 — " + " / ".join(lines))
    report["outcome"] = outcome
    return None


def generate_fact_post(gate_config, report, slot=None, draft_flow=False, topic_override=None, transport=None):
    """구조화 Fact 경로의 글 만들기(content_source: facts) — 만들면 (국문 글 경로, None), 못 만들면 None. **이 함수는 AI 를 한 번도 부르지 않는다**: 피드·기사 발췌·구글 뉴스 해석기·Gemini·프롬프트·
    사진 선택·사진 사용 알림을 부르지 않는다(정적 규칙 AF4·AF8 의 진입 함수).
    흐름: 켜기 전 안전장치(fact_context — 하나라도 아니면 이유를 한 줄 남기고 정상 종료) → 이력을 읽어 오늘 낼 글감을 차례대로 시도(fact_prepare) → 첫 글 하나를 파일·이력에 쓴다.
    파일 이름·분류 폴더·승인 흐름 항목(draft_flow)은 기존 규칙 그대로다(주 상한·하루 1편·열린 초안 상한·일시정지는 실행 앞의 잠금 가드가 맡는다). 국문 단독이라 영문 짝 글·영문 폴더는 없다.
    transport 는 시험이 실제 호출 대신 넣는 가짜 transport 다(주지 않으면 make_fact_transport)."""
    report.setdefault("lanes", [])
    report["lane_label"] = FACT_LANE_LABEL
    now = now_kst()
    if topic_override:
        return fact_stop(report, source_policy.FACT_NOT_READY_OUTCOME, ["facts 경로는 요청한 주제를 받지 않는다(후보는 이력과 공개 구조화 자료가 정한다)"])
    problems, sources, provider, access = fact_context(now)
    if problems:
        return fact_stop(report, source_policy.FACT_NOT_READY_OUTCOME, problems)
    print("구조화 Fact 경로(content_source: facts): AI 를 부르지 않고 허용 목록의 공개 구조화 자료로 글을 만듭니다.")
    history = read_history()
    prepared, result = fact_prepare(now, history, sources, provider, access, 1, gate_config, transport)
    report["fact_notes"] = fact_notes(result)
    for note in report["fact_notes"]:
        print(f"  {note}")
    if not prepared:
        outcome = (source_policy.FACT_WAITING_OUTCOME if result.waiting else source_policy.FACT_ALL_SKIPPED_OUTCOME if result.skipped else source_policy.FACT_NO_CANDIDATE_OUTCOME)
        return fact_stop(report, outcome, [])
    item = prepared[0]
    post = item.post
    date_str, time_str = now.strftime("%Y-%m-%d"), now.strftime("%H%M%S")
    kr_path = safe_category_dir(post.category, "KR") / f"{date_str}-KR-{time_str}.md"
    if kr_path.exists():
        report["fact_notes"].append(f"Fact 글감 {item.candidate.spec.spec_id} 건너뜀: FILE_EXISTS")
        return fact_stop(report, source_policy.FACT_ALL_SKIPPED_OUTCOME, ["같은 이름의 글 파일이 이미 있어 덮어쓰지 않음"])
    write_text_atomic(kr_path, item.marked)
    entry = fact_history_entry(item, now, slot)
    if draft_flow:
        entry.update(drafts.entry_fields(date_str, slot, time_str, [kr_path]))
        report["draft_branch"] = entry["branch"]
    history.append(entry)
    write_history(history)
    report.update(outcome="DRAFT_CREATED" if draft_flow else "PUBLISHED", title=post.title, en_title=None, source=post.source_name, paths=[str(kr_path)])
    print("블로그 글 생성 완료" + (" (DRY_RUN: 파일·기록은 저장되지 않았습니다):" if DRY_RUN else ":"))
    print(f"- KR: {kr_path}\n- 구조화 자료: {post.source_name} · 글감 {item.candidate.spec.spec_id}\n- 이미지: {item.image}")
    if draft_flow:
        print(f"- 승인 흐름: 연습 실행이라 초안 브랜치 {entry['branch']} 를 올리지 않습니다" if DRY_RUN
              else f"- 승인 흐름: 초안 브랜치 {entry['branch']} 로 올립니다(PR 을 병합하면 공개, 닫으면 폐기)")
    return kr_path, None


# ============================================================
# 진입점
# ============================================================
PRACTICE_PUBLISHED_TEXT = "연습으로 글을 만들어 봤습니다(저장하지 않았습니다)"   # 연습 실행의 PUBLISHED: 아무것도 저장하지 않았는데 발행된 것처럼 읽히지 않게
OUTCOME_TEXT = {
    "PUBLISHED": "글을 만들었습니다",
    "DRAFT_CREATED": "초안을 만들었습니다(승인 흐름: PR 을 병합하면 공개, 닫으면 폐기 — 올리기는 다음 단계)",
    "ALL_LANES_EMPTY": "모든 분야를 시도했지만 검증을 통과한 기사가 한 건도 없습니다",
    "SOURCES_UNREACHABLE": "뉴스 소스에 접속하지 못했습니다(시도한 소스가 모두 수집 실패)",
    "ALL_DUPLICATES": "검증된 기사는 있었지만 모두 이미 쓴 글과 비슷해 새 글감이 없습니다(뉴스가 뜸한 때)",
    "NO_CANDIDATES": "시간 상한으로 일부 분야만 시도했고 후보를 찾지 못했습니다",
    "ALL_REJECTED": "후보는 있었지만 전부 탈락했습니다(Gemini 건너뜀, 제목이 기존 글과 비슷, 또는 본문 검증 탈락)",
    "NO_MATCH": "요청 주제와 연결되는 검증된 기사가 없습니다",
    "SOURCE_POLICY_NO_ACTIVE_PROVIDER": "소스 정책(allowlist)이 켜져 있고 허용 목록에 ACTIVE 콘텐츠 Provider 가 없어 글감을 읽지 않았습니다(정상 — 할 일 없음, 외부 호출 0)",
    source_policy.FACT_NOT_READY_OUTCOME: "구조화 Fact 경로(content_source: facts)의 시작 조건을 채우지 못해 글을 만들지 않았습니다(정상 — 이유는 위 줄, 파일·이력은 그대로)",
    source_policy.FACT_WAITING_OUTCOME: "차례인 Fact 글감이 일별 제품의 협정 세계시 하한 때문에 기다립니다(정상 — 다음 실행이 이어 갑니다)",
    source_policy.FACT_NO_CANDIDATE_OUTCOME: "오늘 낼 수 있는 Fact 글감이 없습니다(정상 — 이번 기간에 이미 냈거나 같은 제품의 글과 간격이 모자랍니다)",
    source_policy.FACT_ALL_SKIPPED_OUTCOME: "Fact 글감 후보는 있었지만 모두 건너뛰었습니다(자료 부족·호출 거부·검사 탈락 — 사유는 위 줄)",
}


def _gemini_count_line(calls):
    """Blogger·이슈 수정 요약과 같은 형식의 호출 수 줄."""
    return f"Gemini 호출: {calls['attempts']}회(실패 {calls.get('failed', 0)}회)"


def _unsplash_line(rate):
    """마지막으로 관측한 Unsplash 시간당 남은 호출 수. 응답에 헤더가 없었으면 None(줄을 만들지 않는다)."""
    remaining = (rate or {}).get("remaining")
    if remaining is None:
        return None
    limit = rate.get("limit")
    return f"Unsplash 남은 호출: {remaining}회" + (f"(시간당 한도 {limit}회)" if limit is not None else "")


def usage_lines():
    """지금까지의 Gemini·Unsplash 사용량 줄. 정상 종료 요약(finish_run)이 아닌 경로 — 예외로 끝난 실행, 이미지 교체 — 에서도 쓴다."""
    lines = [_gemini_count_line(GEMINI_CALLS)]   # 0회도 적는다: 줄이 없으면 '호출 안 함'과 '이 기능이 없는 옛 요약'을 구분할 수 없다
    lines += CALL_LOG.detail_lines()
    unsplash = _unsplash_line(UNSPLASH_RATE)
    if unsplash:
        lines.append(unsplash)
    return lines


def failure_summary(exc):
    """예외로 끝난 실행의 요약. 모든 모델이 실패한 실행에서도 호출 수가 사라지지 않게 사용량 줄을 붙인다(D-52)."""
    return "\n".join(["### Chance_Blog 실행 요약",
                      f"- 결과: **실패** — {type(exc).__name__} (원인은 이 단계의 로그를 보세요)"]
                     + [f"- {line}" for line in usage_lines()])


def render_run_summary(event, now, slot, report):
    """실행 요약(마크다운). 건수와 코드만 쓴다 — 비밀·수익·방문 수치 금지(G-O7)."""
    outcome = report.get("outcome", "UNKNOWN")
    mode = "스케줄" if event == "schedule" else "수동"
    if DRY_RUN:
        mode += " (DRY_RUN: 파일·기록 저장 안 함)"
    created = outcome in ("PUBLISHED", "DRAFT_CREATED")   # 글 한 쌍을 만든 결과(승인 흐름이면 DRAFT_CREATED)
    outcome_text = PRACTICE_PUBLISHED_TEXT if DRY_RUN and created else OUTCOME_TEXT.get(outcome, "알 수 없음")
    lines = ["### Chance_Blog 실행 요약",
             f"- 실행: {mode} · {now:%Y-%m-%d %H:%M} KST" + (f" · {slot}시 슬롯" if slot is not None else ""),
             f"- 결과: **{outcome}** — {outcome_text}"]
    if DRY_RUN:  # 연습 실행이 한도를 썼는지 요약에서 바로 보이게 한다(기본은 가짜 응답, 실제 호출은 real_ai 체크)
        lines.append("- AI 응답: " + ("가짜(스텁) — Gemini를 호출하지 않았습니다(실제 호출로 연습하려면 수동 실행에서 real_ai 를 체크)"
                                      if STUB_GEMINI else "실제 Gemini 호출 — 연습 실행이지만 무료 한도를 씁니다"))
    over = report.get("manual_over_cap")
    if over:
        lines.append(f"- 경고: 수동 실행은 게시 시각·하루 상한을 따지지 않습니다 — 오늘({over['date']}) 이미 {over['posted']}건이 "
                     f"게시되어 상한({over['cap']}건) 이상입니다")
    if created:
        lines.append(f"- 제목: {_md_cell(report.get('title', ''))}")
        lines.append(f"- 편집 축: {report.get('lane_label', '')} · 출처: {_md_cell(report.get('source', ''), 60)}")
        lines.append("- 파일: " + ", ".join(f"`{str(p).replace(chr(96), '')}`" for p in report.get("paths", [])))
        if report.get("draft_branch"):
            branch = str(report["draft_branch"]).replace(chr(96), "")
            lines.append(f"- 승인 흐름: 연습 실행이라 초안 브랜치 `{branch}` 를 올리지 않습니다" if DRY_RUN
                         else f"- 승인 흐름: 초안 브랜치 `{branch}` 로 올립니다 — PR 을 병합하면 공개, 닫으면 폐기")
    calls = report.get("gemini_calls")
    if isinstance(calls, dict) and "attempts" in calls:   # 0회도 적는다(finish_run 이 항상 넣는다). 항목 자체가 없으면 값을 지어내지 않는다
        lines.append(f"- {_gemini_count_line(calls)}")
    lines += [f"- {note}" for note in report.get("gemini_notes", [])]
    lines += [f"- {note}" for note in report.get("fact_notes", [])]      # 구조화 Fact 경로의 건너뜀 줄(기본 실행에는 없다)
    unsplash = _unsplash_line(report.get("unsplash_rate"))
    if unsplash:
        lines.append(f"- {unsplash}")
    rejects = report.get("gate_rejects", [])
    if rejects:
        lines.append(f"- 후보 탈락 {len(rejects)}건(본문 검증·응답 형식): " + " / ".join(_md_cell(r, 100) for r in rejects[:3]))
    lines += reject_detail_lines(report)
    lanes = report.get("lanes", [])
    if lanes:
        lines += ["", "| 분야 | 소스 | 받은 기사 | 검증 통과 | 후보 | 탈락 사유(개수) |",
                  "|---|---|---|---|---|---|"]
        for lane in lanes:
            drops = _format_drops(lane["drops"]) or "-"
            failed = f" (수집 실패 {lane['failed_sources']})" if lane["failed_sources"] else ""
            lines.append(f"| {lane['label']} | {lane['sources']}{failed} | {lane['fetched']} | "
                         f"{lane['passed']} | {lane['candidates']} | {drops} |")
        if len(lanes) > 1:
            lines.append(f"\n분야 {len(lanes)}개를 차례로 시도했습니다(처음 추첨된 분야에 후보가 없거나 그 후보가 모두 탈락하면 다음 분야).")
        codes = sorted({code for lane in lanes for code in lane["drops"]})
        if codes:
            lines.append("\n탈락 사유 코드: " + " · ".join(f"{c}={DROP_LABELS.get(c, c)}" for c in codes))
    return "\n".join(lines)


def finish_run(result, report, event, now, slot=None):
    """실행 결과를 로그·요약으로 남기고 종료 정책을 적용한다(docs/ARCHITECTURE.md '스킵 코드').
    - 글을 만들었음: 정상
    - 후보는 있었으나 전부 탈락, 검증된 기사는 있었지만 모두 중복(뉴스가 뜸함), 시간 상한으로 일부만 시도: 초록 + ::warning::
    - 소스에 접속하지 못함, 또는 모든 분야에 검증된 기사가 한 건도 없음: 빨강(종료 1) — 발행하려던 실행이 0건으로 끝난 이상 신호"""
    if result is not None:
        report.setdefault("outcome", "PUBLISHED")
    outcome = report.get("outcome", "UNKNOWN")
    report.setdefault("gemini_calls", dict(GEMINI_CALLS))
    report.setdefault("gemini_notes", CALL_LOG.detail_lines())
    report.setdefault("unsplash_rate", dict(UNSPLASH_RATE))
    write_step_summary(render_run_summary(event, now, slot, report))
    if result is not None:
        return
    where = f"{slot}시 슬롯" if slot is not None else "수동 실행"
    if outcome == source_policy.NO_ACTIVE_OUTCOME:   # 허용 목록 정책상 읽을 곳이 없는 정상 상태 — 초록 + 안내(ALL_LANES_EMPTY 의 빨강·경고와 구분)
        print(skip_line(outcome, lanes_tried=0))
        print(f"::notice::{where}: {OUTCOME_TEXT[outcome]}.")
        return
    if outcome in source_policy.FACT_QUIET_OUTCOMES:   # 구조화 Fact 경로의 정상 건너뜀(시작 조건 미충족·시각 대기·오늘 낼 글감 없음) — 초록 + 안내. 후보를 모두 건너뛴 FACT_ALL_SKIPPED 는 아래 일반 경고로 간다
        print(skip_line(outcome, lanes_tried=0))
        print(f"::notice::{where}: {OUTCOME_TEXT[outcome]}.")
        return
    if outcome in ("ALL_LANES_EMPTY", "SOURCES_UNREACHABLE"):
        print(skip_line(outcome, lanes_tried=len(report.get("lanes", []))))
        print(f"::error::{where}: {OUTCOME_TEXT[outcome]}. 실행 요약의 탈락 사유와 수집 실패 개수를 확인하세요.")
        raise SystemExit(1)
    print(skip_line(outcome, lanes_tried=len(report.get("lanes", []))))
    print(f"::warning::{where}: {OUTCOME_TEXT.get(outcome, '글을 만들지 못했습니다')}. "
          "다음 실행에서 다시 시도합니다.")


def daily_cap():
    """pipeline/blogs.json 에서 chance 블로그의 하루 게시 상한(limits.max_posts_per_day). 읽지 못하면 None."""
    from pipeline import registry
    try:
        return int(registry.get_blog(registry.load_registry(), "chance")["limits"]["max_posts_per_day"])
    except (registry.RegistryError, KeyError, TypeError, ValueError):
        return None


def note_manual_over_cap(report):
    """수동 실제 실행은 게시 시각 판단(slot_state)과 하루 상한을 모두 건너뛴다. 운영자가 일부러 더 게시하려는 것일 수 있어 막지 않고(동작은
    그대로), 오늘 이미 게시된 글이 상한 이상이면 경고 주석과 요약 줄만 남긴다. 연습 실행은 게시하지 않으므로 하지 않는다."""
    if DRY_RUN:
        return
    cap = daily_cap()
    if cap is None:
        print("하루 게시 상한을 읽지 못해 수동 실행의 상한 초과 경고를 건너뜁니다.")
        return
    today = now_kst().strftime("%Y-%m-%d")
    posted = sum(1 for item in read_history() if isinstance(item, dict) and item.get("date") == today)
    if posted >= cap:
        report["manual_over_cap"] = {"date": today, "posted": posted, "cap": cap}
        print(f"::warning::수동 실행: 오늘({today}) 이미 {posted}건이 게시되어 하루 상한({cap}건) 이상입니다. "
              "수동 실행은 게시 시각·하루 상한을 따지지 않고 글을 만듭니다(막지 않습니다).")


# 승인 흐름(publish_flow: pr)에서만 생기는 건너뜀 코드의 사유 문구(docs/ARCHITECTURE.md §4-1·§4-4). direct 에서는 쓰이지 않는다.
DRAFT_SKIP_REASONS = {
    drafts.STATE_PENDING: "{slot}시 슬롯 초안이 승인(PR 병합)을 기다리는 중이거나 닫혀 폐기됨 — 같은 슬롯을 다시 만들지 않음",
    drafts.STATE_CHECK_FAILED: "초안 브랜치를 확인하지 못함",
}


def draft_flow_on():
    """레지스트리의 chance 발행 흐름이 승인 흐름(pr)인가. direct(기본)면 False. 레지스트리를 읽지 못하거나 값이 올바르지 않으면
    DraftFlowError 로 멈춘다 — 직접 게시로 조용히 떨어지면 승인 없는 게시가 나가기 때문이다."""
    return drafts.chance_flow() == drafts.FLOW_PR


def refine_for_drafts(state, slot, history, now):
    """승인 흐름에서 slot_state 의 결과를 다듬는다(drafts.refine_slot_state): 글이 아직 main 에 없는 초안 슬롯은 DRAFT_PENDING,
    만들 차례인데 그 슬롯의 초안 브랜치가 이미 원격에 있으면 DRAFT_PENDING, 브랜치를 확인하지 못했으면 DRAFT_CHECK_FAILED.
    연습 실행(DRY_RUN)은 네트워크를 쓰지 않으므로 브랜치를 확인하지 않는다."""
    date_str = now.strftime("%Y-%m-%d")
    exists = False
    if state == "DUE" and not DRY_RUN:
        from pipeline import draft_flow   # git 을 부르는 모듈은 승인 흐름에서만 읽는다
        exists = draft_flow.remote_branch_exists(drafts.branch_name(date_str, slot))
    return drafts.refine_slot_state(state, slot, history, date_str, exists)


def facts_without_key():
    """레지스트리 content_source 가 facts 면 True — 구조화 Fact 경로는 AI 를 부르지 않으므로 Gemini 키가 없어도 실행한다(AI 키를 주지 않는 실행 — docs/FACT_PATH.md §15). 레지스트리를 읽지 못하거나 값이
    올바르지 않으면 False(옛 동작 그대로: 키가 없으면 멈춘다). 키가 있으면 main 이 이 함수를 부르지 않는다(레지스트리를 더 읽지 않는다)."""
    try:
        return source_policy.chance_content_source() == source_policy.CONTENT_FACTS
    except Exception:       # noqa: BLE001 — 값을 알 수 없으면 느슨하게 하지 않는다
        return False


def main():
    if shadow_run_unrecognized():     # 모르는 SHADOW_RUN 값은 거절한다(꺼짐으로 읽으면 정지가 풀린 상태에서 일반 쓰기 실행으로 내려간다)
        print(f"::error::SHADOW_RUN 값을 알 수 없어 실행하지 않습니다 — 켜짐: {', '.join(sorted(SHADOW_RUN_ON_VALUES))} / 꺼짐: 비움·{', '.join(sorted(SHADOW_RUN_OFF_VALUES - {''}))}")
        raise SystemExit(2)
    if _pause_on():
        print(skip_line("PAUSED", var="PIPELINE_PAUSE"))
        print("[일시정지] PIPELINE_PAUSE 가 켜져 있어 실행하지 않습니다.")
        print("::notice::PIPELINE_PAUSE 가 켜져 있어 Chance_Blog 실행을 건너뛰었습니다.")
        write_step_summary("### Chance_Blog 실행 요약\n- 결과: **일시정지** — "
                           "저장소 변수 PIPELINE_PAUSE 가 켜져 있습니다.")
        return
    # 병합 순서(제한 재개 잠금의 가드 호출 guard_start 와 같은 자리): 이 그림자 분기가 잠금 가드보다 **앞**에 있어야 한다. 그림자 실행은 읽기 전용이라 잠금 대상이 아니고, 가드가 앞서면
    # 레지스트리 규칙 위반·하루 상한이 그림자 실행까지 멈춘다(docs/QUALITY_GATE.md §6).
    if shadow_run_on():      # 그림자 실행: 정지 변수를 보지 않고(위 _pause_on 이 False) 읽기 전용 경로로만 간다 — 아래 일반 실행(쓰기·게시)으로 내려가지 않는다
        run_shadow()
        return
    # 순서(GATE 의 그림자 분기가 병합된 뒤에도 같다): 정지 검사 → 그림자 분기(SHADOW_RUN, 읽기 전용으로 처리하고 끝난다) → 아래 잠금 가드. 그림자 분기를 이 가드 아래에 두지 않는다 —
    # 그림자 실행은 가드에 닿지 않고, 가드 안의 SHADOW_RUN 예외는 그림자 분기를 지나쳐 온 경우를 위한 방어선일 뿐이다(docs/PUBLISH_PATHS.md §4-2·§7).
    from pipeline import publish_lock   # 제한 재개 잠금(레지스트리 resume_lock — 기본 꺼짐). 꺼져 있으면 레지스트리를 읽는 것 말고 아무 일도 하지 않는다. 설명: docs/PUBLISH_PATHS.md
    publish_lock.guard_start(os.environ, HISTORY_FILE, now_kst, FIX_IMAGES, DRY_RUN, write_step_summary)   # 켜져 있는데 규칙을 어기면 글을 만들지 않고 멈춘다(SystemExit 1), 하루 상한이면 건너뛴다(SystemExit 0)
    if STUB_GEMINI and not DRY_RUN and not facts_without_key():
        raise RuntimeError(
            "GEMINI_API_KEY 환경 변수가 없습니다. "
            "Settings > Secrets and variables > Actions에서 확인하세요.")
    if DRY_RUN:
        print(f"[DRY_RUN] 시작 (Gemini={'스텁' if STUB_GEMINI else '실제'}, "
              f"Unsplash={'스텁' if STUB_UNSPLASH else '실제'}) - 파일은 변경되지 않습니다.")
    if FIX_IMAGES:
        write_step_summary(f"### Chance_Blog 실행 요약\n- {fix_images()}" + "".join(f"\n- {line}" for line in usage_lines()))
    elif EVENT_NAME == "schedule":
        now = now_kst()
        history = read_history()
        slot, state = slot_state(history, now)
        draft_flow = draft_flow_on()
        if draft_flow:
            state = refine_for_drafts(state, slot, history, now)
        if state != "DUE":
            reason = (DRAFT_SKIP_REASONS[state].format(slot=slot) if state in DRAFT_SKIP_REASONS
                      else "첫 게시 시각 전" if state == "OUT_OF_WINDOW"
                      else f"{slot}시 슬롯 글이 이미 있음")
            print(skip_line(state, now=now.isoformat(timespec="minutes"),
                            slots=",".join(str(h) for h in SLOT_HOURS)))
            print(f"[스케줄] {now:%Y-%m-%d %H:%M} KST - 지금 만들 글이 없습니다 "
                  f"({reason}; 게시 시각 KST {SLOT_HOURS}시).")
            if state == drafts.STATE_CHECK_FAILED:
                print("::warning::초안 브랜치를 확인하지 못해 이번 실행은 글을 만들지 않았습니다. 다음 실행에서 다시 시도합니다.")
            write_step_summary(f"### Chance_Blog 실행 요약\n- 실행: 스케줄 · {now:%Y-%m-%d %H:%M} KST\n"
                               f"- 결과: **{state}** — {reason}"
                               f"({'다음 실행에서 다시 확인' if state == drafts.STATE_CHECK_FAILED else '정상 건너뜀'})")
            return
        print(f"[스케줄] {now:%Y-%m-%d %H:%M} KST - {slot}시 슬롯 글을 생성합니다.")
        report = {}
        result = generate_blog_posts(slot=slot, allow_auto_topic=False, report=report, draft_flow=draft_flow)
        finish_run(result, report, "schedule", now, slot)
    else:
        report = {}
        note_manual_over_cap(report)
        result = generate_blog_posts(report=report, draft_flow=draft_flow_on())
        finish_run(result, report, EVENT_NAME or "manual", now_kst())


def run_cli():
    """`python generator.py` 진입점. 예외로 끝나도 요약에 결과와 사용량을 남기고 예외는 그대로 다시 던진다(Actions 빨강)."""
    try:
        main()
    except Exception as exc:
        print(f"작업 실패: {type(exc).__name__}: {_one_line(_scrub(exc), 600)}")
        write_step_summary(failure_summary(exc))
        raise


if __name__ == "__main__":
    run_cli()
