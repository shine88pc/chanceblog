"""그림자 모드(품질 측정) — 게시와 무관한 오프라인 측정 도구. 정의·한계·사용법: docs/QUALITY_SHADOW.md

글 파일(`_posts/**/*.md`)이나 후보 글(머리말 + 본문 + 선택적으로 원문 텍스트)을 받아 운영자가 지정한 9가지를 계산해 JSON·마크다운 보고서로 낸다.
  1 핵심 사실 주장 수 · 2 공식 근거로 지원되는 주장 수 · 3 출처 수 · 4 원문 대비 추가 가치 신호 · 5 한·영 유사도 ·
  6 보도자료·회사 발표 단순 요약 여부 · 7 행사 안내 중심 여부 · 8 건강 위험 판정 · 9 주제 적합성

이 모듈은 측정만 한다.
  ① 생성기(generator.py)·실행기(pipeline/run.py)·워크플로 어디에서도 불러오지 않는다(tests/test_quality_shadow_guards.py 의 소스 규칙 시험이 지킨다).
  ② 네트워크를 쓰지 않는다. 입출력은 입력 글·원문 텍스트·건강 프로필 파일 읽기와 `--out` 보고서 쓰기뿐이다.
  ③ 파일 쓰기는 `--out` 으로 받은 보고서 경로 하나뿐이다(입력 폴더 안으로는 쓰지 않는다).
  ④ 측정할 수 없는 값은 0 이 아니라 null 이고 같은 묶음의 `null_reasons` 에 이유가 적힌다.
  ⑤ 같은 입력에는 같은 출력이다 — 시각·난수·절대 경로를 쓰지 않으며 날짜 기준은 `--as-of` 필수 인자다.
결과는 판정이 아니라 '사람이 먼저 볼 순서'를 정하는 신호다(docs/analysis/chance-content-2026-11-04/11_generator_improvement_plan.md §5 의 교훈:
신호를 판정에 쓰면 거의 모든 글이 걸려 게시가 멈춘다).
"""
import argparse
import datetime
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from pipeline import console, gates

SCHEMA_VERSION = 1
TOOL_NAME = "quality_shadow"
NOT_A_VERDICT = "게시와 무관한 측정 전용 보고서입니다. 생성·게시·초안 흐름에 연결돼 있지 않으며 판정이 아니라 사람이 먼저 볼 순서를 정하는 신호입니다."

# ----------------------------------------------------------------------------
# 임계값 — docs/QUALITY_SHADOW.md 표와 tests/test_quality_shadow_guards.py(문서·코드 일치 시험)가 같은 값을 본다(바꾸면 셋을 같이 고친다).
# 되돌려보기(공개 50편·비공개 14편 + 감사 결과 50편)로 보정한 시작값이며 눈대중이다. 보정 근거는 문서에 있다.
# ----------------------------------------------------------------------------
CLONE_STRUCTURE_TOLERANCE = 1                # 소제목·문단·불릿 수 세 가지가 모두 이만큼(±) 이내로 같으면 구조가 같다(번역이 문단 하나를 합치거나 쪼개는 정도)
CLONE_NUMBER_JACCARD_MIN = 0.5               # 의미 있는 숫자 집합의 겹침(자카드) — 이 이상이면 숫자가 같다
CLONE_LENGTH_RATIO_BAND = (1.2, 3.0)         # 영문 글자 수 ÷ 국문 글자 수(공백 제외, 본문만). 번역이면 보통 이 안(잡은 번역 쌍의 중앙값 약 2.2)
EVENT_SENTENCE_RATIO_MIN = 0.2               # 행사 신호어가 든 문장 비율 — 이 이상이고 아래 종류 수를 채우면 행사 안내 중심
EVENT_DISTINCT_TERMS_MIN = 3                 # 서로 다른 행사 신호어 종류 수
EVENT_TITLE_RATIO_MIN = 0.15                 # 제목에 행사 신호어가 있으면 문장 비율이 이만큼만 돼도 행사 안내 중심
HEALTH_CAUTION_DISTINCT_MIN = 2              # 약한 의료어·안전 인접어가 이만큼 서로 달라야 '주의'(강한 의료어는 하나만 있어도 '주의')
SOURCE_SNIPPET_CHARS = 120                   # 보고서에 싣는 문장 발췌의 최대 글자 수

# 의미 있는 숫자: 날짜의 일·순번 같은 작은 정수(31 이하)와 연도는 한·영 숫자 비교에서 뺀다(11-04 개선안 §5-4 의 보정을 그대로 따름)
SMALL_INTEGER_MAX = 31

# ----------------------------------------------------------------------------
# 도메인 분류표 — 운영자 기준(결정 12): Chance 중심 주제 = 공공기관 1차 자료·연구기관 자료·공식 통계·정부 정책·법령·국제기구 자료·공식 관측자료.
# generator.py 의 NEWS_SOURCES·TRUSTED_SOURCE_DOMAINS·TERMS_BLOCKED_DOMAINS 의 모든 도메인이 여기서 분류되는지는 시험이 대조한다(표가 낡지 않게).
# 분류 못 한 도메인은 'unknown' 이다 — 회사라고 짐작하지 않는다. 공식(official) = public_agency + research.
# ----------------------------------------------------------------------------
CATEGORY_PUBLIC = "public_agency"      # 정부·공공기관·공식 통계·국제기구·공식 관측
CATEGORY_RESEARCH = "research"         # 연구기관·대학·학회·여론조사 연구소·학술지
CATEGORY_COMPANY = "company"           # 회사·기업
CATEGORY_NEWS = "news_media"           # 언론
CATEGORY_OTHER = "other"               # 이미지 제공처·블로그·SNS·위키 같은 기타
CATEGORY_UNKNOWN = "unknown"           # 분류하지 못함
OFFICIAL_CATEGORIES = frozenset({CATEGORY_PUBLIC, CATEGORY_RESEARCH})
CATEGORIES = (CATEGORY_PUBLIC, CATEGORY_RESEARCH, CATEGORY_COMPANY, CATEGORY_NEWS, CATEGORY_OTHER, CATEGORY_UNKNOWN)

# (도메인 끝부분, 분류, 설명). 가장 긴 끝부분이 이긴다(예: spectrum.ieee.org 는 언론, ieee.org 는 연구, nst.re.kr 은 공공, re.kr 은 연구).
DOMAIN_RULES = (
    # 정부·공공기관·통계·국제기구·관측
    ("nasa.gov", CATEGORY_PUBLIC, "미 항공우주국"), ("noaa.gov", CATEGORY_PUBLIC, "미 해양대기청(공식 관측)"),
    ("spaceweather.gov", CATEGORY_PUBLIC, "미 우주기상예측센터(공식 관측)"), ("nih.gov", CATEGORY_PUBLIC, "미 국립보건원"),
    ("nist.gov", CATEGORY_PUBLIC, "미 국립표준기술연구소"), ("nsf.gov", CATEGORY_PUBLIC, "미 국립과학재단"),
    ("cdc.gov", CATEGORY_PUBLIC, "미 질병통제예방센터"), ("fda.gov", CATEGORY_PUBLIC, "미 식품의약국"),
    ("ftc.gov", CATEGORY_PUBLIC, "미 연방거래위원회"), ("federalreserve.gov", CATEGORY_PUBLIC, "미 연방준비제도"),
    ("bls.gov", CATEGORY_PUBLIC, "미 노동통계국(공식 통계)"), ("census.gov", CATEGORY_PUBLIC, "미 인구조사국(공식 통계)"),
    ("epa.gov", CATEGORY_PUBLIC, "미 환경보호청"), ("energy.gov", CATEGORY_PUBLIC, "미 에너지부"),
    ("usgs.gov", CATEGORY_PUBLIC, "미 지질조사국(공식 관측)"), ("usa.gov", CATEGORY_PUBLIC, "미 정부 포털"),
    ("europa.eu", CATEGORY_PUBLIC, "유럽연합 기관"), ("esa.int", CATEGORY_PUBLIC, "유럽우주국"),
    ("gov.uk", CATEGORY_PUBLIC, "영국 정부"), ("nhs.uk", CATEGORY_PUBLIC, "영국 국가보건서비스"), ("ukri.org", CATEGORY_PUBLIC, "영국 연구혁신기구"),
    ("gc.ca", CATEGORY_PUBLIC, "캐나다 정부(통계청 포함)"), ("canada.ca", CATEGORY_PUBLIC, "캐나다 정부"),
    ("go.kr", CATEGORY_PUBLIC, "한국 정부·공공기관"), ("korea.kr", CATEGORY_PUBLIC, "한국 정책브리핑"),
    ("bok.or.kr", CATEGORY_PUBLIC, "한국은행"), ("nst.re.kr", CATEGORY_PUBLIC, "국가과학기술연구회"),
    ("go.jp", CATEGORY_PUBLIC, "일본 정부"), ("jaxa.jp", CATEGORY_PUBLIC, "일본 우주항공연구개발기구"),
    ("who.int", CATEGORY_PUBLIC, "세계보건기구"), ("un.org", CATEGORY_PUBLIC, "국제연합"), ("unesco.org", CATEGORY_PUBLIC, "유네스코"),
    ("unicef.org", CATEGORY_PUBLIC, "유니세프"), ("oecd.org", CATEGORY_PUBLIC, "경제협력개발기구"), ("imf.org", CATEGORY_PUBLIC, "국제통화기금"),
    ("worldbank.org", CATEGORY_PUBLIC, "세계은행"), ("ipcc.ch", CATEGORY_PUBLIC, "기후변화에 관한 정부간 협의체"),
    ("wto.org", CATEGORY_PUBLIC, "세계무역기구"), ("iea.org", CATEGORY_PUBLIC, "국제에너지기구"), ("itu.int", CATEGORY_PUBLIC, "국제전기통신연합"),
    ("iaea.org", CATEGORY_PUBLIC, "국제원자력기구"),
    # 연구기관·학회·학술지·여론조사 연구소
    ("pewresearch.org", CATEGORY_RESEARCH, "퓨리서치센터(여론조사 연구소)"), ("brookings.edu", CATEGORY_RESEARCH, "브루킹스 연구소"),
    ("rand.org", CATEGORY_RESEARCH, "랜드 연구소"), ("nber.org", CATEGORY_RESEARCH, "미 경제연구소"), ("arxiv.org", CATEGORY_RESEARCH, "논문 사전 공개"),
    ("science.org", CATEGORY_RESEARCH, "학술지"), ("pnas.org", CATEGORY_RESEARCH, "학술지"), ("cell.com", CATEGORY_RESEARCH, "학술지"),
    ("nature.com", CATEGORY_RESEARCH, "학술지"), ("acm.org", CATEGORY_RESEARCH, "학회"), ("apa.org", CATEGORY_RESEARCH, "미국심리학회"),
    ("ieee.org", CATEGORY_RESEARCH, "학회"), ("kdi.re.kr", CATEGORY_RESEARCH, "한국개발연구원"), ("kimm.re.kr", CATEGORY_RESEARCH, "한국기계연구원"),
    ("re.kr", CATEGORY_RESEARCH, "한국 정부출연연구기관"),
    # 회사(명시한 것만)
    ("openai.com", CATEGORY_COMPANY, "회사"), ("onepredict.ai", CATEGORY_COMPANY, "회사"), ("anthropic.com", CATEGORY_COMPANY, "회사"),
    ("nvidia.com", CATEGORY_COMPANY, "회사"), ("amd.com", CATEGORY_COMPANY, "회사"), ("intel.com", CATEGORY_COMPANY, "회사"),
    ("google.com", CATEGORY_COMPANY, "회사"), ("microsoft.com", CATEGORY_COMPANY, "회사"), ("apple.com", CATEGORY_COMPANY, "회사"),
    ("amazon.com", CATEGORY_COMPANY, "회사"), ("meta.com", CATEGORY_COMPANY, "회사"), ("tesla.com", CATEGORY_COMPANY, "회사"),
    ("spacex.com", CATEGORY_COMPANY, "회사"), ("samsung.com", CATEGORY_COMPANY, "회사"), ("lg.com", CATEGORY_COMPANY, "회사"),
    ("huggingface.co", CATEGORY_COMPANY, "회사"),
    # 언론
    ("apnews.com", CATEGORY_NEWS, "통신사"), ("reuters.com", CATEGORY_NEWS, "통신사"), ("bloomberg.com", CATEGORY_NEWS, "언론"),
    ("ft.com", CATEGORY_NEWS, "언론"), ("nytimes.com", CATEGORY_NEWS, "언론"), ("variety.com", CATEGORY_NEWS, "언론"),
    ("wsj.com", CATEGORY_NEWS, "언론"), ("cnn.com", CATEGORY_NEWS, "언론"), ("washingtonpost.com", CATEGORY_NEWS, "언론"),
    ("bbc.com", CATEGORY_NEWS, "언론"), ("bbc.co.uk", CATEGORY_NEWS, "언론"), ("bbci.co.uk", CATEGORY_NEWS, "언론"),
    ("theguardian.com", CATEGORY_NEWS, "언론"), ("guardian.co.uk", CATEGORY_NEWS, "언론"), ("technologyreview.com", CATEGORY_NEWS, "언론"),
    ("aitimes.com", CATEGORY_NEWS, "언론"), ("arstechnica.com", CATEGORY_NEWS, "언론"), ("spectrum.ieee.org", CATEGORY_NEWS, "학회 매거진(언론)"),
    ("etnews.com", CATEGORY_NEWS, "언론"), ("edaily.co.kr", CATEGORY_NEWS, "언론"), ("techcrunch.com", CATEGORY_NEWS, "언론"),
    ("theverge.com", CATEGORY_NEWS, "언론"), ("yna.co.kr", CATEGORY_NEWS, "통신사"), ("hani.co.kr", CATEGORY_NEWS, "언론"),
    ("chosun.com", CATEGORY_NEWS, "언론"), ("joongang.co.kr", CATEGORY_NEWS, "언론"), ("donga.com", CATEGORY_NEWS, "언론"),
    ("hankyung.com", CATEGORY_NEWS, "언론"), ("mk.co.kr", CATEGORY_NEWS, "언론"), ("zdnet.co.kr", CATEGORY_NEWS, "언론"),
    # 기타(이미지 제공처·블로그·SNS·위키)
    ("unsplash.com", CATEGORY_OTHER, "이미지 제공처"), ("github.com", CATEGORY_OTHER, "코드 저장소"), ("wikipedia.org", CATEGORY_OTHER, "위키"),
    ("medium.com", CATEGORY_OTHER, "블로그 플랫폼"), ("youtube.com", CATEGORY_OTHER, "동영상"), ("youtu.be", CATEGORY_OTHER, "동영상"),
    ("x.com", CATEGORY_OTHER, "SNS"), ("twitter.com", CATEGORY_OTHER, "SNS"), ("linkedin.com", CATEGORY_OTHER, "SNS"),
    ("facebook.com", CATEGORY_OTHER, "SNS"), ("reddit.com", CATEGORY_OTHER, "커뮤니티"),
)
_DOMAIN_RULE_MAP = {suffix: (category, detail) for suffix, category, detail in DOMAIN_RULES}
# 표에 없을 때 쓰는 최상위·공공 접미사 규칙(모양만으로 공식 기관이라고 볼 수 있는 것). 회사·언론은 이런 규칙이 없다.
GENERIC_SUFFIX_RULES = (
    (".gov", CATEGORY_PUBLIC, "미국 정부 도메인(.gov)"), (".mil", CATEGORY_PUBLIC, "미국 군 도메인(.mil)"),
    (".int", CATEGORY_PUBLIC, "국제기구 도메인(.int)"), (".gov.au", CATEGORY_PUBLIC, "호주 정부"),
    (".edu", CATEGORY_RESEARCH, "대학 도메인(.edu)"), (".ac.kr", CATEGORY_RESEARCH, "한국 대학·학술"),
    (".ac.uk", CATEGORY_RESEARCH, "영국 대학·학술"), (".ac.jp", CATEGORY_RESEARCH, "일본 대학·학술"), (".edu.au", CATEGORY_RESEARCH, "호주 대학"),
)
# 등록 가능한 도메인을 셋째 칸까지 잡는 두 칸짜리 공공 접미사(예: statcan.gc.ca, mfds.go.kr, www.gov.uk). 이 밖의 호스트는 끝 두 칸이다.
_MULTI_LABEL_SUFFIXES = frozenset({
    "co.kr", "or.kr", "go.kr", "re.kr", "ac.kr", "ne.kr", "pe.kr", "co.uk", "org.uk", "gov.uk", "ac.uk", "co.jp", "go.jp", "or.jp", "ac.jp",
    "gc.ca", "com.au", "gov.au", "edu.au", "com.cn", "gov.cn", "com.sg", "gov.sg", "com.br", "gov.br"})
# 이미지 크레딧 링크로 쓰이는 도메인 — 출처 수에서 뺀다(Unsplash 작가·사이트 링크)
IMAGE_CREDIT_DOMAINS = ("unsplash.com",)

# 보도자료·발표 형식을 알리는 주소 조각. 강한 조각은 어떤 도메인이든, 약한 조각은 공식 기관이 아닌 도메인에서만 센다
# (공식 기관의 '/news/' 는 보도자료가 아니라 기사·소식 쪽인 경우가 많다).
PRESS_STRONG_TOKENS = frozenset({"press", "pressrelease", "pressreleases", "release", "releases", "newsroom", "prnewswire", "businesswire", "보도자료"})
PRESS_WEAK_TOKENS = frozenset({"news", "announcement", "announcements", "media", "pr", "story", "stories", "notice"})
# 약한 조각 가운데 이것 하나만으로는 보도자료 형식이 아니다 — 언론 기사·소식 주소에 흔한 낱말이다(독립 검증 P10: 기사 주소의 /news/ 만으로 '보도자료 형식 요약'이 켜지던 것).
PRESS_GENERIC_TOKENS = frozenset({"news"})
RELEASE_WORDS_IN_SOURCE_NAME = re.compile(r"보도자료|press release|newsroom|news release|발표|공지|announce", re.I)

# ----------------------------------------------------------------------------
# 입력 읽기
# ----------------------------------------------------------------------------
_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
_FRONT_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):[ \t]*(.*)$")
_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(KR|EN|AI)(?:-(\d{6}))?$")
MAX_TEXT_BYTES = 2 * 1024 * 1024        # 글·원문 텍스트 한 파일의 읽기 상한(손상 파일·잘못 준 큰 파일 방지)
MAX_LINE_CHARS = 5000                   # 본문 한 줄에서 읽는 최대 글자 수 — 이보다 긴 줄은 잘라 읽고 `long_lines_truncated` 로 알린다(정규식 시간 상한)


class QualityShadowError(Exception):
    """입력·인자 문제(설정 오류 — 종료 코드 2)."""


class PostReadError(QualityShadowError):
    """글 파일을 읽을 수 없거나 머리말이 없다."""


@dataclass
class Post:
    rel: str                       # 입력 폴더 기준 상대 경로(슬래시)
    name: str                      # 파일 이름에서 .md 를 뺀 것
    front: dict
    body: str
    date: str                      # YYYY-MM-DD(파일 이름 → 머리말 date → '')
    kind: str                      # KR · EN · AI · ''
    pair_key: str                  # 파일 이름 끝 6자리('' 이면 짝 없음)
    lang: str                      # ko · en · ''
    published: bool
    title: str = ""
    source_url: str = ""
    source_name: str = ""
    source_domain: str = ""


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        if value[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return value


def normalize_newlines(text):
    """CRLF·단독 CR 을 LF 로(저장소는 Windows 에서 autocrlf 로 CRLF 가 되고, 보이지 않는 BOM 도 뺀다)."""
    return (text or "").lstrip(chr(0xFEFF)).replace("\r\n", "\n").replace("\r", "\n")


def parse_front_matter(text):
    """(머리말 사전, 본문). 머리말이 없으면 ({}, 전체) — 한 줄 `키: 값` 만 읽는다(표준 라이브러리만, 중첩 값은 문자열 그대로)."""
    text = normalize_newlines(text)
    found = _FRONT_MATTER_RE.match(text)
    if not found:
        return {}, text
    front = {}
    for line in found.group(1).split("\n"):
        pair = _FRONT_KEY_RE.match(line)
        if pair:
            front[pair.group(1)] = _unquote(pair.group(2))
    return front, text[found.end():]


def _lang_from(front, kind, body):
    lang = (front.get("lang") or "").strip().lower()
    if lang in ("ko", "en"):
        return lang
    if kind == "KR":
        return "ko"
    if kind == "EN":
        return "en"
    letters = [ch for ch in body if ch.isalpha()]
    if not letters:
        return ""
    hangul = sum(1 for ch in letters if "가" <= ch <= "힣")
    return "ko" if hangul / len(letters) > 0.3 else "en"


def parse_post(text, rel="post.md"):
    """글 텍스트 → Post. 머리말이 없으면 PostReadError(측정 대상 글이 아니다)."""
    front, body = parse_front_matter(text)
    if not front:
        raise PostReadError("머리말(---)이 없어 글이 아니다")
    name = rel.rsplit("/", 1)[-1]
    if name.endswith(".md"):
        name = name[:-3]
    found = _FILENAME_RE.match(name)
    date, kind, pair_key = (found.group(1), found.group(2), found.group(3) or "") if found else ("", "", "")
    if not date:
        match = re.match(r"(\d{4}-\d{2}-\d{2})", (front.get("date") or "").strip())
        date = match.group(1) if match else ""
    published = (front.get("published") or "").strip().lower() != "false"
    return Post(rel=rel, name=name, front=front, body=body, date=date, kind=kind, pair_key=pair_key,
                lang=_lang_from(front, kind, body), published=published, title=front.get("title", ""),
                source_url=front.get("source_url", ""), source_name=front.get("source_name", ""),
                source_domain=front.get("source_domain", ""))


def read_text_file(path):
    """UTF-8 텍스트 파일 읽기(크기 상한). 못 읽으면 PostReadError."""
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            raise PostReadError(f"파일이 {MAX_TEXT_BYTES} 바이트를 넘는다")
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PostReadError(f"UTF-8 이 아니다: {exc.reason}") from exc
    except OSError as exc:
        raise PostReadError(f"읽을 수 없다: {exc.strerror or exc.__class__.__name__}") from exc


# ----------------------------------------------------------------------------
# 영역 나누기: 본문(main) · 출처 목록(sources) · 이미지·크레딧·인용 줄·고지 줄(tail)
# ----------------------------------------------------------------------------
# 열기 부분만 정규식으로 본다. 제목 뒤의 공백·닫는 `#` 은 문자열 메서드로 한 번씩만 뗀다 — 꼬리를 `[ \t]*#*[ \t]*` 로 받으면
# 공백이 긴 줄에서 3차 역추적이 일어난다(독립 검증 P3: 공백 3,000칸 한 줄에 56초).
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})[ \t]+(.*)$")
_BOLD_ONLY_RE = re.compile(r"^\s*\*\*([^*\n]+?)\*\*\s*(?:[:：]\s*)?$")           # 꼬리를 `\s*[:：]?\s*` 로 받으면 공백이 긴 줄에서 제곱 시간이 된다
_SOURCE_TITLE_RE = re.compile(
    r"(?:sources?|references?|출처|참고\s*자료|참고\s*문헌|참고)(?:\s*(?:and|&|및|와|과)\s*(?:sources?|references?|출처|참고\s*자료|참고자료))?",
    re.I)
_IMAGE_CREDIT_TITLE_RE = re.compile(r"(?:이미지|사진|image|photo)\s*(?:출처|크레딧|credits?)", re.I)
_RULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_LIST_RE = re.compile(r"^(\s*)(?:[-*+]|\d{1,3}[.)])[ \t]+(.*)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|?\s*$")
# `\s*\|?\s*` 처럼 선택 글자 하나를 사이에 둔 `\s*` 두 개는 공백이 긴 줄에서 제곱 시간이 된다(독립 재탐색: 4,000칸에 0.28초) — `\s*(?:\|\s*)?` 로 한 번씩만 받는다(받아들이는 줄은 같다)
_TABLE_SEPARATOR_RE = re.compile(r"^\s*(?:\|\s*)?:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*(?:\|\s*)?$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_IMAGE_LINE_RE = re.compile(r"^\s*(?:!\[[^\]\n]*\]\([^)\n]*\)|<img\b[^>\n]*>)\s*$", re.I)
_ITALIC_ONLY_RE = re.compile(r"^\s*[*_](?![*_])\s*\S.*\S\s*[*_]\s*$")
# `\s*[*_]*\s*` 도 같은 문제라 `\s*(?:[*_]+\s*)?` 로 받는다(받아들이는 줄은 같다). 인용 줄 정규식은 앞 공백을 정규식 대신 lstrip 으로 떼고 쓴다(`\s*` 뒤의 `.*` 가 겹쳐 제곱 시간)
_CREDIT_START_RE = re.compile(r"^\s*(?:[*_]+\s*)?(?:photo\s+by|image\s+by|photo\s*:|사진\s*[:：]?|이미지\s*[:：]?)", re.I)
_CITATION_RE = re.compile(r"^(?:[“\"].*(?:<https?://|Source:)|Adapted from\b|.*Contains public sector information)")        # 줄의 앞 공백을 뗀 글에 match 한다


@dataclass
class Zones:
    main: list = field(default_factory=list)            # 본문 줄(출처 목록·이미지·고지 줄을 뺀 것)
    sources_heading: str = ""                           # 출처 제목 줄('' 이면 출처 절 없음)
    sources_items: list = field(default_factory=list)   # 출처 목록 항목 텍스트
    citation_lines: list = field(default_factory=list)  # 인용 줄(“제목.” … <주소> / Adapted from …)
    notice_lines: list = field(default_factory=list)    # 기울임 한 줄(AI 고지·참고 문구)
    image_lines: int = 0                                # 본문 이미지 줄 수
    credit_lines: list = field(default_factory=list)    # 사진 크레딧 줄
    truncated_lines: int = 0                            # MAX_LINE_CHARS 를 넘어 잘라 읽은 줄 수


# 정규식 `\s` 와 같은 글자 집합(str.isspace). 제목 앞뒤를 정규식이 아니라 strip 으로 뗀다 — `[\s:：*#_]+$` 는 공백 연속 뒤에 다른 글자가 오면 제곱 시간이다.
_WHITESPACE_CHARS = "".join(chr(code) for code in range(0x10000) if chr(code).isspace())
_TITLE_LEAD_CHARS = _WHITESPACE_CHARS + "*#_"
_TITLE_TAIL_CHARS = _WHITESPACE_CHARS + ":：*#_"


def _plain_title(raw):
    return (raw or "").lstrip(_TITLE_LEAD_CHARS).rstrip(_TITLE_TAIL_CHARS).strip()


def heading_text(line):
    """소제목 줄(`## 제목`, 닫는 `##` 는 있어도 된다)이면 제목 글자, 아니면 None. 빈 제목은 빈 문자열이다.
    꼬리의 공백→닫는 `#`→공백을 정규식이 아니라 문자열 메서드로 한 번씩만 뗀다(공백이 긴 줄에서도 입력 길이에 비례해서만 느려진다)."""
    found = _HEADING_RE.match(line)
    if not found:
        return None
    return found.group(2).rstrip(" \t").rstrip("#").rstrip(" \t")


def _heading_title(line):
    """소제목 줄(`## 제목`)이거나 굵은 글씨만 있는 줄(`**제목**`)이면 제목 글자, 아니면 None."""
    heading = heading_text(line)
    if heading is not None:
        return _plain_title(heading)
    bold = _BOLD_ONLY_RE.match(line)
    return _plain_title(bold.group(1)) if bold else None


def is_sources_heading(line):
    """출처 절의 제목 줄인가: `## 출처`·`### Sources`·`**Source**`·`**출처 및 참고자료**` … (`## 이미지 출처` 는 아니다)."""
    title = _heading_title(line)
    return bool(title) and _SOURCE_TITLE_RE.fullmatch(title) is not None


def _is_image_credit_heading(line):
    heading = heading_text(line)
    return heading is not None and _IMAGE_CREDIT_TITLE_RE.fullmatch(_plain_title(heading)) is not None


def split_zones(body):
    """본문 줄을 영역으로 나눈다. 줄 단위 상태 기계 — 출처 제목 뒤의 목록은 출처 항목, 그 밖의 이미지·크레딧·인용·기울임 줄은 꼬리로 뺀다.
    출처 절 뒤에 다른 소제목이 나오면 본문으로 돌아간다."""
    zones = Zones()
    in_sources = False
    in_credit_section = False
    last_item = None
    for line in normalize_newlines(body).split("\n"):
        if len(line) > MAX_LINE_CHARS:
            line = line[:MAX_LINE_CHARS]
            zones.truncated_lines += 1
        stripped = line.strip()
        if is_sources_heading(line):
            in_sources, in_credit_section, last_item = True, False, None
            if not zones.sources_heading:
                zones.sources_heading = _heading_title(line)
            while zones.main and not zones.main[-1].strip():
                zones.main.pop()
            if zones.main and _RULE_RE.match(zones.main[-1]):               # 출처 앞의 가로줄은 본문이 아니다
                zones.main.pop()
            continue
        if _is_image_credit_heading(line):
            in_sources, in_credit_section, last_item = False, True, None
            continue
        if (in_sources or in_credit_section) and heading_text(line) is not None:
            in_sources, in_credit_section, last_item = False, False, None      # 출처·크레딧 절 뒤의 새 소제목 → 본문으로 복귀
        if not stripped:
            if in_sources or in_credit_section:
                last_item = None
            else:
                zones.main.append(line)
            continue
        if _RULE_RE.match(line):
            if not (in_sources or in_credit_section):
                zones.main.append(line)
            continue
        if _IMAGE_LINE_RE.match(line):
            zones.image_lines += 1
            continue
        if _CREDIT_START_RE.match(line) and "unsplash" in line.lower():
            zones.credit_lines.append(stripped)
            continue
        if _CITATION_RE.match(line.lstrip()):
            zones.citation_lines.append(stripped)
            continue
        if _ITALIC_ONLY_RE.match(line):
            zones.notice_lines.append(stripped)
            continue
        if in_credit_section:
            zones.credit_lines.append(stripped)
            continue
        if in_sources:
            item = _LIST_RE.match(line)
            if item:
                zones.sources_items.append(item.group(2).strip())
                last_item = len(zones.sources_items) - 1
            elif last_item is not None and line.startswith((" ", "\t")):
                zones.sources_items[last_item] += " " + stripped
            else:
                zones.notice_lines.append(stripped)                              # 출처 목록 뒤의 설명 문단(본문이 아니다)
            continue
        zones.main.append(line)
    while zones.main and (not zones.main[-1].strip() or _RULE_RE.match(zones.main[-1])):
        zones.main.pop()
    return zones


# ----------------------------------------------------------------------------
# 링크·도메인
# ----------------------------------------------------------------------------
# 길이를 제한한 반복({0,n})으로 짠다 — 닫는 괄호가 없는 긴 줄에서 정규식이 입력 길이의 제곱으로 느려지지 않게(R5)
_MD_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]{0,300})\]\((https?://[^)\s]{1,2000})(?:\s+(?:\"[^\"]{0,300}\"|'[^']{0,300}'))?\)")
_MD_IMAGE_RE = re.compile(r"!\[[^\]\n]{0,300}\]\([^)\n]{0,2000}\)")
_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]{1,2000})>")
_BARE_URL_RE = re.compile(r"https?://[^\s<>()\[\]\"'“”]+")
_TRAILING_URL_PUNCT = ".,;:!?)]}”’'\""
_MARK_OPEN, _MARK_CLOSE = "\x01", "\x02"
_MARK_RE = re.compile(_MARK_OPEN + r"(\d+)" + _MARK_CLOSE)


def _clean_url(url):
    return url.rstrip(_TRAILING_URL_PUNCT)


def replace_links(raw):
    """마크다운 링크·자동 링크·맨 주소를 `텍스트\\x01번호\\x02` 표지로 바꾼다 → (텍스트, 주소 목록). 이미지 링크는 지운다.
    문장을 나눈 뒤에도 어느 문장에 어느 링크가 붙었는지 알기 위한 장치다."""
    urls = []

    def mark(url, anchor=""):
        urls.append(_clean_url(url))
        return f"{anchor}{_MARK_OPEN}{len(urls) - 1}{_MARK_CLOSE}"

    text = _MD_IMAGE_RE.sub(" ", raw)
    text = _MD_LINK_RE.sub(lambda m: mark(m.group(2), m.group(1)), text)
    text = _AUTOLINK_RE.sub(lambda m: mark(m.group(1)), text)
    text = _BARE_URL_RE.sub(lambda m: mark(m.group(0)), text)
    return text, urls


def urls_in(raw):
    return replace_links(raw)[1]


def host_of(url):
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def registrable_domain(host):
    labels = [label for label in (host or "").split(".") if label]
    if len(labels) <= 2:
        return ".".join(labels)
    if ".".join(labels[-2:]) in _MULTI_LABEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


MAX_RULE_LABELS = 6                              # 분류표 규칙은 최대 세 칸(spectrum.ieee.org·bbc.co.uk)이다 — 끝의 여섯 칸까지만 후보로 만든다


def _suffix_candidates(host):
    """호스트의 끝부분 후보(긴 것부터). 라벨이 수천 개인 호스트에서 후보 문자열을 전부 만들면 라벨 수의 제곱 시간이라(독립 재탐색: 점 3,000개에 0.17초)
    끝의 `MAX_RULE_LABELS` 칸까지만 만든다 — 분류표 규칙은 그보다 짧으므로 맞는 규칙은 같다."""
    labels = (host or "").split(".")[-MAX_RULE_LABELS:]
    return [".".join(labels[i:]) for i in range(len(labels))]


def classify_host(host):
    """(분류, 설명, 맞은 규칙). 가장 구체적인(긴) 도메인 끝부분이 이긴다. 표에 없으면 모양 규칙, 그래도 없으면 unknown."""
    host = (host or "").lower().rstrip(".")
    host = host[4:] if host.startswith("www.") else host
    if not host:
        return CATEGORY_UNKNOWN, "도메인 없음", ""
    for candidate in _suffix_candidates(host):
        if candidate in _DOMAIN_RULE_MAP:
            category, detail = _DOMAIN_RULE_MAP[candidate]
            return category, detail, candidate
    for suffix, category, detail in sorted(GENERIC_SUFFIX_RULES, key=lambda rule: -len(rule[0])):
        if host.endswith(suffix):
            return category, detail, suffix
    return CATEGORY_UNKNOWN, "표에 없는 도메인", ""


def is_image_credit_host(host):
    return any(host == domain or host.endswith("." + domain) for domain in IMAGE_CREDIT_DOMAINS)


# 주소를 견줄 때 지우는 추적용 쿼리 이름(utm_* 는 접두어로 따로 지운다)
TRACKING_QUERY_KEYS = frozenset({"ref", "ref_src", "ref_url", "referrer", "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "igshid", "spm"})


def normalize_url(url):
    """공유 링크 비교용: 소문자 호스트(앞의 www. 제거)·http 와 https 를 같게·fragment 제거·끝 슬래시 제거·추적 쿼리(utm_*·ref·fbclid …) 제거·남은 쿼리는 정렬.
    표기만 다른 같은 주소가 다른 주소로 갈리지 않게 한다(독립 검증 P6: www.·http·`&ref=` 한 글자 차이로 번역 짝 판정이 풀렸다)."""
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        pairs = parse_qsl(parts.query, keep_blank_values=True)
    except ValueError:
        return url.strip()
    if host.startswith("www."):
        host = host[4:]
    kept = sorted((key, value) for key, value in pairs if not (key.lower().startswith("utm_") or key.lower() in TRACKING_QUERY_KEYS))
    scheme = parts.scheme.lower()
    return urlunsplit(("https" if scheme == "http" else scheme, host, parts.path.rstrip("/") or "/", urlencode(kept), ""))


def press_format_signals(url):
    """주소 경로가 보도자료·발표 형식인가 → (강한 조각 목록, 약한 조각 목록). 조각은 경로·호스트를 `/`·`-`·`_`·`.` 로 쪼갠 낱말이다."""
    if not url:
        return [], []
    try:
        parts = urlsplit(url)
    except ValueError:
        return [], []
    pieces = [p for p in re.split(r"[/\-_.+]", (parts.path or "").lower()) if p]
    pieces += [p for p in (parts.hostname or "").lower().split(".") if p and p != "www"][:1]
    pieces += [p for p in re.split(r"[/\-_.+]", unquote(parts.path or "").lower()) if p]      # %EB%B3%B4... 처럼 퍼센트 인코딩된 한글 경로
    strong = sorted({p for p in pieces if p in PRESS_STRONG_TOKENS})
    weak = sorted({p for p in pieces if p in PRESS_WEAK_TOKENS})
    return strong, weak


# ----------------------------------------------------------------------------
# 블록·문장·주장 단위
# ----------------------------------------------------------------------------
@dataclass
class Block:
    kind: str                # heading · paragraph · list · table_row · table_header · quote
    raw: str
    index: int               # 문단 번호(같은 문단의 문장은 같은 번호)


def build_blocks(main_lines):
    """본문 줄 → 블록 목록(소제목·문단·목록 항목·표 행·인용). 표의 첫 행은 table_header, 구분선은 버린다."""
    blocks = []
    paragraph = []
    in_table = False

    def flush():
        if paragraph:
            blocks.append(Block("paragraph", " ".join(paragraph), len(blocks)))
            paragraph.clear()

    for line in main_lines:
        if not line.strip():
            flush()
            in_table = False
            continue
        if _RULE_RE.match(line):
            flush()
            in_table = False
            continue
        heading = heading_text(line)
        if heading is not None:
            flush()
            in_table = False
            blocks.append(Block("heading", heading.strip(), len(blocks)))
            continue
        quote = _QUOTE_RE.match(line)
        if quote:
            flush()
            in_table = False
            blocks.append(Block("quote", quote.group(1).strip(), len(blocks)))
            continue
        if _TABLE_ROW_RE.match(line):
            flush()
            if _TABLE_SEPARATOR_RE.match(line):
                continue
            blocks.append(Block("table_row" if in_table else "table_header", line.strip(), len(blocks)))
            in_table = True
            continue
        in_table = False
        item = _LIST_RE.match(line)
        if item:
            flush()
            blocks.append(Block("list", item.group(2).strip(), len(blocks)))
            continue
        if blocks and blocks[-1].kind == "list" and line.startswith((" ", "\t")) and not paragraph:
            blocks[-1].raw += " " + line.strip()                      # 목록 항목의 이어지는 줄
            continue
        paragraph.append(line.strip())
    flush()
    return blocks


_ABBREVIATIONS = ("U.S.", "U.K.", "E.U.", "U.N.", "No.", "Nos.", "Dr.", "Mr.", "Mrs.", "Ms.", "Prof.", "Inc.", "Corp.", "Ltd.", "Co.", "St.",
                  "vs.", "etc.", "e.g.", "i.e.", "approx.", "Jan.", "Feb.", "Mar.", "Apr.", "Jun.", "Jul.", "Aug.", "Sept.", "Sep.", "Oct.", "Nov.",
                  "Dec.", "Gov.", "Sen.", "Rep.", "Fig.", "Vol.")
_ABBR_PLACEHOLDER = "\x03"
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])[\"'”’)\]]*\s+(?=[\"'“‘(\[]?[A-Z0-9가-힣\x01])")


def split_sentences(text):
    """문단 텍스트 → 문장 목록. 영어 약어(U.S.·No.·Dr. …)는 문장 끝으로 보지 않고, 소수점·주소의 점은 뒤에 공백이 없어 나뉘지 않는다."""
    protected = text
    for abbreviation in _ABBREVIATIONS:
        protected = protected.replace(abbreviation, abbreviation.replace(".", _ABBR_PLACEHOLDER))
    pieces = _SENTENCE_SPLIT_RE.split(protected)
    return [piece.replace(_ABBR_PLACEHOLDER, ".").strip() for piece in pieces if piece.strip()]


_MD_EMPHASIS_RE = re.compile(r"(\*\*|__)(.+?)\1|(?<![\w*])[*_]([^*_\n]+?)[*_](?![\w*])")
_INLINE_CODE_RE = re.compile(r"`([^`\n]*)`")


def to_plain(text):
    """마크다운 표시를 걷어낸 글(링크 표지·강조·코드 표시 제거)."""
    text = _MARK_RE.sub("", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    text = _MD_EMPHASIS_RE.sub(lambda m: m.group(2) or m.group(3) or "", text)
    text = text.replace("|", " ")
    return re.sub(r"\s+", " ", text).strip()


def chars_nospace(text):
    return sum(1 for ch in text if not ch.isspace())


# ----------------------------------------------------------------------------
# 앵커: 숫자·날짜·퍼센트·금액·고유명사
# ----------------------------------------------------------------------------
_MONTHS = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
           "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
           "nov": 11, "november": 11, "dec": 12, "december": 12}
_MONTH_PATTERN = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_RANGE_JOIN = r"(?:-|–|—|\x7e|to|through|until|부터|에서)"          # \x7e 는 물결표다(문서·보고서에 글자로 쓰면 마크다운이 취소선으로 오인하는 사고가 있어 소스에도 글자로 적지 않는다)
# 숫자 바로 뒤에 붙어 개수·값을 세는 낱말(닫힌 목록 — 없는 낱말은 못 읽는 쪽을 택한다). 두 곳에서 쓴다:
# ① 한글 글자에 붙여 쓴 숫자('총3명'·'연2회')는 이런 낱말이 따라올 때만 숫자로 읽는다(이름에 붙은 '코로나19' 같은 식별자는 읽지 않는다)
# ② 일(日) 표시 없이 월 뒤에 오는 수('3월 20개'·'6월 30%')는 이런 낱말이 따라오면 날짜가 아니다
_KO_COUNTERS = ("명", "건", "개", "회", "배", "곳", "대", "가구", "세대", "세", "살", "년", "월", "일", "시간", "시", "분", "초", "주", "차", "위", "점", "번", "권", "편", "종", "채",
                "호", "층", "평", "톤", "인", "마리", "퍼센트", "포인트", "%", "％", "원", "달러", "유로", "엔", "위안", "파운드", "조", "억", "만", "천", "백")
_DATE_PATTERNS = (
    ("iso", re.compile(r"(?<![\d.])(?P<y>(?:19|20)\d{2})[-./](?P<m>\d{1,2})[-./](?P<d>\d{1,2})(?![\d])")),
    ("ko_full", re.compile(r"(?P<y>(?:19|20)\d{2})\s?년\s?(?P<m>\d{1,2})\s?월"
                           r"(?:\s?(?P<d>\d{1,2})\s?일(?:\s?" + _RANGE_JOIN + r"\s?(?:(?P<m2>\d{1,2})\s?월\s?)?(?P<d2>\d{1,2})\s?일?)?)?")),
    ("en_md", re.compile(r"\b(?P<m>" + _MONTH_PATTERN + r")\.?\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?(?![\d])"
                         r"(?:\s*" + _RANGE_JOIN + r"\s*(?:(?P<m2>" + _MONTH_PATTERN + r")\.?\s+)?(?P<d2>\d{1,2})(?:st|nd|rd|th)?(?![\d]))?"
                         r"(?:,?\s+(?P<y>(?:19|20)\d{2})\b)?")),
    ("en_dm", re.compile(r"\b(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+(?P<m>" + _MONTH_PATTERN + r")\b\.?(?:,?\s+(?P<y>(?:19|20)\d{2})\b)?")),
    ("en_my", re.compile(r"\b(?P<m>" + _MONTH_PATTERN + r")\.?,?\s+(?P<y>(?:19|20)\d{2})\b")),          # 'November 2026'(일 없이 월만 — 월 단위 날짜)
    ("ko_md", re.compile(r"(?<![\d.])(?P<m>\d{1,2})\s?월\s?(?P<d>\d{1,2})\s?(?P<il>일)?"
                         r"(?:\s?" + _RANGE_JOIN + r"\s?(?:(?P<m2>\d{1,2})\s?월\s?)?(?P<d2>\d{1,2})\s?(?P<il2>일)?)?")),
)


_NUMERIC_MONTH_PATTERNS = ("iso", "ko_full", "ko_md")


@dataclass
class DateMention:
    start: datetime.date
    end: datetime.date
    precision: str          # day · month
    text: str
    span: tuple


def _month_number(token):
    return _MONTHS.get(token.lower().rstrip("."))


def _safe_date(year, month, day):
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _nearest_year_date(month, day, ref):
    """연도가 없는 날짜는 글 날짜(ref)에서 가장 가까운 해의 그 날로 본다(12월 글의 '1월 3일'은 다음 해, 11월 글의 '8월 19일'은 올해)."""
    candidates = [candidate for candidate in (_safe_date(ref.year + delta, month, day) for delta in (-1, 0, 1)) if candidate]
    return min(candidates, key=lambda candidate: abs((candidate - ref).days)) if candidates else None


def _is_count_not_date(match, text):
    """`3월 20개 사업`·`5월 15명`·`6월 30% 증가`·`9월 10건` — 월 뒤의 수가 일(日) 표시 없이 개수·퍼센트 낱말을 달고 있으면 날짜가 아니다(독립 검증 P12).
    마지막 숫자(기간이면 끝 숫자)에 `일` 이 붙어 있으면 날짜다. `일` 이 없고 뒤에 단위 낱말이 오지 않을 때만 예전처럼 날짜로 읽는다."""
    last = "d2" if match.group("d2") else "d"
    if match.group("il2" if last == "d2" else "il"):
        return False
    return text[match.end(last):match.end(last) + 8].lstrip().startswith(_KO_COUNTERS)


def _resolve_dates(name, groups, month, ref):
    """한 표기의 (시작일, 끝일) 또는 None. 연도가 있으면 그 해를 쓰고, 없으면 글 날짜(ref)에서 가장 가까운 해로 정한다.
    연도 없는 기간은 **끝 날짜의 해를 먼저** 정하고 시작은 같은 해(끝보다 늦으면 그 전해)로 둔다 — 시작만 가까운 해로 잡으면
    10월 30일 글의 `1월 1일–10월 24일` 이 다음 해(2027년)로 읽혀 '아직 열리지 않은 행사'가 되던 오류(독립 검증 P12)를 막는다."""
    day_text, year_text = groups.get("d"), groups.get("y")
    day = int(day_text) if day_text else 1
    if groups.get("d2"):
        month2 = (int(groups["m2"]) if name in _NUMERIC_MONTH_PATTERNS else _month_number(groups["m2"])) if groups.get("m2") else month
    else:
        month2 = None
    if year_text:
        start = _safe_date(int(year_text), month, day)
        if start is None:
            return None
        end = start
        if month2 is not None:
            end_year = start.year + (1 if month2 and month2 < month else 0)
            end = _safe_date(end_year, month2 or month, int(groups["d2"])) or start
        return start, end
    if month2 is None:
        start = _nearest_year_date(month, day, ref)
        return (start, start) if start else None
    end = _nearest_year_date(month2 or month, int(groups["d2"]), ref)
    if end is None:                                    # 끝 날짜가 달력에 없으면 시작 하루만 본다
        start = _nearest_year_date(month, day, ref)
        return (start, start) if start else None
    start = _safe_date(end.year, month, day)
    if start is None or start > end:
        start = _safe_date(end.year - 1, month, day)
    return (start, end) if start else (end, end)


def find_dates(text, ref_date=None):
    """글 속 날짜 표기를 찾는다(국문·영문·ISO). 연도가 없는 '11월 3일'·'November 3' 은 글 날짜(ref_date)에서 가장 가까운 해로 본다
    (글 날짜가 없으면 1970년). 겹치는 표기는 먼저 잡힌 것(긴 형식)이 이긴다. 월 뒤의 수가 일(日) 표시 없이 개수 낱말을 달면 날짜가 아니다."""
    ref = ref_date or datetime.date(1970, 1, 1)
    covered = bytearray(len(text))                      # 이미 날짜로 잡힌 글자(겹침 검사가 날짜 수가 아니라 표기 길이에만 비례한다 — 독립 검증 P8)
    mentions = []
    for name, pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            span = match.span()
            if covered.find(1, span[0], span[1]) >= 0:
                continue
            groups = match.groupdict()
            month = int(groups["m"]) if name in _NUMERIC_MONTH_PATTERNS else _month_number(groups["m"])
            if not month or not 1 <= month <= 12:
                continue
            if name == "ko_md" and _is_count_not_date(match, text):
                continue
            precision = "day" if groups.get("d") else "month"
            resolved = _resolve_dates(name, groups, month, ref)
            if resolved is None:
                continue
            start, end = resolved
            if precision == "month":
                next_month = (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
                end = next_month - datetime.timedelta(days=1)
            covered[span[0]:span[1]] = b"\x01" * (span[1] - span[0])
            mentions.append(DateMention(start, end, precision, match.group(0).strip(), span))
    mentions.sort(key=lambda mention: mention.span)
    return mentions


_KO_SCALE = {"조": 10 ** 12, "억": 10 ** 8, "만": 10 ** 4, "천": 10 ** 3, "백": 10 ** 2}
_EN_SCALE = {"thousand": 10 ** 3, "million": 10 ** 6, "billion": 10 ** 9, "trillion": 10 ** 12, "bn": 10 ** 9, "tn": 10 ** 12}
_PERCENT_WORDS = ("%p", "%", "퍼센트", "percent", "per cent", "percentage point", "percentage points")
_CURRENCY_WORDS = ("달러", "유로", "원", "엔", "위안", "파운드", "dollar", "dollars", "euro", "euros", "won", "yen", "pound", "pounds")
# 숫자에 바로 붙은 영문 단위(길이·무게·전력·주파수·용량 …). 값은 쓴 그대로 읽는다(단위 환산은 하지 않는다: 5km 는 5, 100MW 는 100).
# 목록에 없는 영문자가 붙으면(G1·COP31·5G·21st·3x) 식별자·서수로 보고 숫자로 읽지 않는다. 한 글자 단위는 m(미터)·W(와트)만 받는다 — 5G·5g 는 식별자다.
_LATIN_UNITS = ("km", "cm", "mm", "nm", "µm", "μm", "kg", "mg", "lbs", "lb", "oz", "ft", "ha", "mt", "gt", "kwh", "mwh", "gwh", "twh", "wh", "kw", "mw", "gw", "tw",
                "khz", "mhz", "ghz", "thz", "hz", "rpm", "kbps", "mbps", "gbps", "bps", "kb", "mb", "gb", "tb", "pb", "ms", "fps", "ppm", "ppb", "db", "mph", "ml", "kcal")
# 한 글자 규모 약어. 통화 기호 뒤($5M·€3M·$2.5B·$300K — 소문자 $5m 도)에서만 값(천·백만·십억)으로 읽는다. 기호 없는 3M(회사 이름)·4K(해상도)·401K 는 모호해서 읽지 않는다.
_SCALE_ABBREVIATIONS = {"K": 10 ** 3, "M": 10 ** 6, "B": 10 ** 9}
_LATIN_UNIT_PATTERN = "|".join(sorted((re.escape(unit) for unit in _LATIN_UNITS), key=len, reverse=True)) + r"|w(?!\d)"        # 와트 W — 5W1H(육하원칙)는 단위가 아니다
_NUMBER_RE = re.compile(
    # 앞: 숫자 바로 앞이 낱말 글자·점이 아니거나 한글 글자('약5%'·'총3명') / '제N조' 같은 조문 번호는 숫자가 아니다
    r"(?P<pre>[$€£¥₩])?\s?(?:(?<![\w.])|(?<=[가-힣]))(?<!제)"
    # 수: 소수점 뒤에 숫자가 이어지거나(3.5GHz) 천 단위 쉼표 묶음이 이어지면(1,000x·12,246xyz — 쉼표 뒤 정확히 세 자리가 끝나는 경우) 그 전체가 한 수다.
    # 앞부분(3·1·12)만 잘라 읽어 값을 틀리게 내지 않는다(독립 검증 P5). `2026,2027`·`1,2,3` 처럼 쉼표로 이은 목록은 묶음이 아니라 따로 읽는다.
    r"(?P<num>\d{1,3}(?:,\d{3}){1,5}(?:\.\d{1,15})?|\d{1,15}(?:\.\d{1,15})?)(?!\d)(?!\.\d)(?!,\d{3}(?!\d))"
    r"(?P<ko>[조억만천백]{1,3})?"
    r"(?P<post>\s?(?:%p|%|퍼센트|percentage points?|percent|per cent"
    r"|(?:thousand|million|billion|trillion|bn|tn)(?:\s(?:dollars?|euros?|won|yen|pounds?))?"
    r"|달러|유로|원|엔|위안|파운드|dollars?|euros?|won|yen|pounds?))?"
    r"(?P<latin>(?(pre)[kmb]|(?-i:[KMB]))|(?-i:m)|" + _LATIN_UNIT_PATTERN + r")?(?![A-Za-z])", re.I)
_YEAR_RANGE = (1900, 2099)


@dataclass
class NumberToken:
    value: float
    kind: str               # number · percent · money · year
    text: str
    span: tuple
    scale: int = 0          # 한국어 단위의 가장 큰 자리(합산용)


def _ko_multiplier(unit):
    multiplier = 1
    for ch in unit:
        multiplier *= _KO_SCALE[ch]
    return multiplier


def find_numbers(text):
    """글 속 숫자 표기를 찾는다 — 퍼센트·금액·한국어 단위(조·억·만·천)·영어 단위(million·billion·bn)를 값으로 바꾸고,
    영문 단위가 바로 붙은 수(3.5GHz·5km·100MW·155mm)는 쓴 그대로의 값으로, 통화 기호 뒤의 규모 약어($5M·$2.5B·€3M)는 값으로 읽는다.
    한글 글자에 붙은 수('약5%'·'총3명')는 단위·퍼센트·개수 낱말이 따라올 때만 읽는다. 목록에 없는 영문자가 붙은 식별자(G1·COP31·5G·21st)·
    이름에 붙은 수(코로나19)·'제10조' 같은 조문 번호는 숫자로 세지 않는다."""
    tokens = []
    for match in _NUMBER_RE.finditer(text):
        unit = match.group("ko") or ""
        post = (match.group("post") or "").strip()
        latin = match.group("latin") or ""
        start = match.start("num")
        if start > 0 and "가" <= text[start - 1] <= "힣" and not (unit or post or latin or text.startswith(_KO_COUNTERS, match.end())):
            continue                                                  # 이름에 붙은 수('코로나19')는 식별자다
        scale_factor = 1
        if len(latin) == 1 and latin in "KMBkmb":
            if match.group("pre"):
                if unit or post:
                    continue                                          # 다른 단위와 겹친 약어($5만M)는 읽지 않는다
                scale_factor = _SCALE_ABBREVIATIONS[latin.upper()]    # $5M·$2.5B·€3M·$300K(소문자 $5m 도)
            elif latin != "m":
                continue                                              # 통화 기호 없는 3M(회사 이름)·4K(해상도)는 모호하다 — 소문자 m 은 미터라서 읽는다
        base = float(match.group("num").replace(",", ""))
        post_low = post.lower()
        value = base * (_ko_multiplier(unit) if unit else 1) * scale_factor
        scale_word = next((word for word in _EN_SCALE if post_low.startswith(word)), None)      # million·billion 같은 영어 단위(뒤에 통화가 붙을 수 있다)
        rest = post_low
        if scale_word:
            value *= _EN_SCALE[scale_word]
            rest = post_low[len(scale_word):].strip()
        kind = "number"
        if rest in _PERCENT_WORDS or rest.startswith("percentage"):
            kind = "percent"
        elif match.group("pre") or rest in _CURRENCY_WORDS:
            kind = "money"
        elif (not unit and not post and not latin and "," not in match.group("num") and "." not in match.group("num")
              and _YEAR_RANGE[0] <= int(base) <= _YEAR_RANGE[1]):
            kind = "year"
        top = max((_KO_SCALE[ch] for ch in unit), default=0)
        tokens.append(NumberToken(value, kind, match.group(0).strip(), match.span(), top))
    return _merge_korean_compounds(tokens, text)


def _merge_korean_compounds(tokens, text):
    """'4조 2천억' 처럼 이어 붙은 한국어 단위는 합친다(4조 + 2천억 = 4.2조)."""
    merged = []
    for token in tokens:
        if merged:
            previous = merged[-1]
            gap = text[previous.span[1]:token.span[0]]
            if previous.scale and token.scale and gap.strip() == "" and len(gap) <= 1 and token.scale < previous.scale:
                kind = "money" if "money" in (previous.kind, token.kind) else previous.kind
                merged[-1] = NumberToken(previous.value + token.value, kind, (previous.text + " " + token.text).strip(),
                                         (previous.span[0], token.span[1]), token.scale)
                continue
        merged.append(token)
    return merged


def numeric_key(value):
    """언어·표기가 달라도 같은 값이면 같은 키(유효숫자 6자리)."""
    if value == 0:
        return "0"
    if not math.isfinite(value):
        return "inf"
    digits = 5 - int(math.floor(math.log10(abs(value))))
    return repr(round(value, digits)) if digits > 0 else repr(round(value))


_STOP_CAPITALIZED = frozenset((
    "The A An In On At By For From With This That These Those It Its He She They We You I As While However But And Or If When Where Why How What Who "
    "Which Although Because Since Under Over After Before During Despite According Meanwhile Furthermore Moreover Additionally Instead Overall "
    "Generally Typically Often Some Many Most All Each Both Such Other Another Several One Two Three Four Five Six Seven Eight Nine Ten First Second "
    "Third Next Last Finally Also Still Yet So Then There Here Today Now Recent Recently Currently Earlier Later Not No Yes Our Their His Her Of To "
    "Is Are Was Were Be Been Has Have Had Will Would Can Could May Might Should Must Do Does Did Any Every Within Without Between Among Through "
    "Across Against Beyond Upon Per Via Whether Once Until Unless Though Whereas Thus Hence Therefore Rather Even Just Only More Less Much Very "
    "Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April June July August September October November December "
    "Jan Feb Mar Apr Jun Jul Aug Sep Sept Oct Nov Dec").split())
_GENERIC_ACRONYMS = frozenset("AI IT TV PC CEO CFO CTO SNS KR EN QR OK URL PDF FAQ API USB HTML DIY PR UX UI AM PM".split())
_LATIN_ENTITY_RE = re.compile(r"(?:[A-Z]\.){2,}|[A-Z][A-Za-z’'\-]*(?:\s+(?:(?:of|de|von|van|del|da|&)\s+)?[A-Z][A-Za-z’'\-]*)*")
# 국문 기관 이름: 접미사로 끝나는 한 낱말(앞 낱말은 잡지 않는다 — '이는 미국 연방거래위원회' 같은 군더더기가 붙는다). '청'·'처' 한 글자 접미사는 낱말이 4자 이상일 때만.
_KO_ORG_RE = re.compile(
    r"[가-힣]{1,20}(?:위원회|집행위|연구소|연구원|연구회|연구센터|재단|협회|협의회|대학교|은행|연맹|기구|통계청|기상청|항공우주국|우주항공청|준비제도|이사회|행정부|공동연구센터)"
    r"|[가-힣]{3,20}(?:청|처)(?![가-힣])")
# '이란'(Iran)·'인도'(India)는 '…이란'(이라는 뜻)·'인도하다' 와 겹쳐 오탐이 많아 뺐다(못 찾는 쪽을 택함)
_KO_PLACES = ("미국", "캐나다", "유럽연합", "유럽", "영국", "한국", "대한민국", "일본", "중국", "독일", "프랑스", "스페인", "이탈리아", "호주", "러시아",
              "브라질", "멕시코", "네덜란드", "스웨덴", "노르웨이", "핀란드", "덴마크", "폴란드", "벨기에", "오스트리아", "스위스", "아일랜드", "포르투갈", "그리스",
              "튀르키예", "이스라엘", "사우디아라비아", "싱가포르", "대만", "베트남", "태국", "인도네시아", "필리핀", "바르셀로나", "런던", "파리", "베를린",
              "도쿄", "서울", "부산", "뉴욕", "워싱턴", "브뤼셀", "오타와", "토론토", "온타리오", "앨버타", "퀘벡", "브리티시컬럼비아", "노바스코샤", "서스캐처원",
              "매니토바", "애리조나", "콜로라도", "인디애나", "유타", "캘리포니아", "텍사스", "플로리다")
_KO_PLACE_RE = re.compile(r"(?<![가-힣])(?:" + "|".join(sorted(_KO_PLACES, key=lambda name: -len(name))) + r")")


def find_entities(text, number_spans=()):
    """고유명사 후보(기관·인물·지명). 규칙 기반이라 오탐·누락이 있다 — 영문은 대문자로 시작하는 낱말열·약어(문장 첫 낱말 하나만 대문자인 경우는 제외),
    국문은 기관 접미사(…위원회·…연구소·…통계청 등)와 나라·지역 이름표다. 한글로 적은 인명은 찾지 못한다."""
    entities = []
    for match in _LATIN_ENTITY_RE.finditer(text):
        words = [re.sub(r"[’']s$", "", word) for word in match.group(0).split()]      # 소유격 's 는 뗀다
        while words and words[0] in _STOP_CAPITALIZED:
            words = words[1:]
        if not words:
            continue
        sentence_initial = text[:match.start()].strip() == ""
        if len(words) == 1:
            word = words[0]
            if word in _GENERIC_ACRONYMS or len(word) < 2:
                continue
            is_acronym = word.isupper() and len(word) >= 2
            if sentence_initial and not is_acronym:
                continue
        entities.append(" ".join(words))
    for match in _KO_ORG_RE.finditer(text):
        entities.append(match.group(0))
    for match in _KO_PLACE_RE.finditer(text):
        entities.append(match.group(0))
    return entities


# ----------------------------------------------------------------------------
# 주장(핵심 사실 진술 문장)
# ----------------------------------------------------------------------------
@dataclass
class Claim:
    text: str
    para: int
    numbers: list
    dates: list
    entities: list
    urls: list
    block_kind: str

    @property
    def numeric(self):
        return bool(self.numbers or self.dates)


_ORDINAL_PREFIX_RE = re.compile(r"^\s*\d{1,3}[.)]\s+")
_LEADING_LABEL_RE = re.compile(r"^\s*\*\*[^*\n]{1,200}\*\*\s*[:：]?")
# 따옴표로 시작해 따옴표로 끝나는 문장은 인용문 자체라 주장 문장으로 세지 않는다(인용 뒤에 '…라고 말했다' 가 붙으면 인용이 아니라 서술이다)
_PURE_QUOTE_RE = re.compile(r"[“\"‘'«「『].{0,2000}?[”\"’'»」』][.!?。]?")


def extract_claims(blocks, ref_date=None):
    """본문 블록 → 주장 문장 목록. 주장 = 숫자·날짜·퍼센트·금액·고유명사가 하나라도 든 서술 문장.
    제목·인용 블록·표 머리·물음표로 끝나는 문장·12자 미만 조각은 뺀다(출처 목록·고지·크레딧은 영역을 나눌 때 이미 빠졌다)."""
    claims = []
    for block in blocks:
        if block.kind in ("heading", "quote", "table_header"):
            continue
        marked, urls = replace_links(block.raw)
        if block.kind == "table_row":
            marked = " ; ".join(cell.strip() for cell in marked.strip().strip("|").split("|"))
            sentences = [marked]
        else:
            sentences = split_sentences(marked)
        for sentence in sentences:
            linked = [urls[int(i)] for i in _MARK_RE.findall(sentence)]
            plain = to_plain(sentence)
            plain = _ORDINAL_PREFIX_RE.sub("", plain)
            if len(plain) < 12 or plain.endswith(("?", "？")) or _PURE_QUOTE_RE.fullmatch(plain):
                continue
            dates = find_dates(plain, ref_date)
            masked = _blank_spans(plain, [mention.span for mention in dates])
            numbers = find_numbers(masked)
            label = _LEADING_LABEL_RE.match(sentence)               # 목록 항목 맨 앞의 굵은 소제목('**허위 광고:** …')은 고유명사 후보에서 뺀다
            label_plain = to_plain(label.group(0)) if label else ""
            entity_text = masked[len(label_plain):] if label_plain and masked.startswith(label_plain) else masked
            entities = find_entities(entity_text)
            if not (numbers or dates or entities):
                continue
            claims.append(Claim(plain, block.index, numbers, dates, entities, linked, block.kind))
    return claims


def _blank_spans(text, spans):
    """겹치지 않는 구간들을 같은 길이의 공백으로 바꾼다. 구간을 정렬해 한 번에 이어 붙인다 — 구간 하나마다 글 전체를 새로 이어 붙이면
    날짜가 많은 단락에서 입력 크기의 제곱 시간이 된다(독립 검증 P8)."""
    pieces, position = [], 0
    for start, end in sorted(spans):
        if start < position:
            continue
        pieces.append(text[position:start])
        pieces.append(" " * (end - start))
        position = end
    pieces.append(text[position:])
    return "".join(pieces)


def snippet(text, limit=SOURCE_SNIPPET_CHARS):
    return console.one_line(text, limit)


# ----------------------------------------------------------------------------
# 분석 준비: 글 하나를 영역·블록·주장·링크로 풀어 둔다
# ----------------------------------------------------------------------------
def _ref_date(post):
    try:
        return datetime.date.fromisoformat(post.date) if post.date else None
    except ValueError:
        return None


@dataclass
class Prepared:
    post: Post
    zones: Zones
    blocks: list
    claims: list
    main_plain: str
    main_chars: int
    ref_date: object
    body_urls: list              # 본문 링크(이미지 크레딧·라이선스 링크 제외, 순서대로·중복 포함)
    list_urls: list              # 출처 목록의 링크
    citation_urls: list          # 인용 줄의 링크(라이선스 링크 제외)
    credit_urls_excluded: int    # 빼 버린 이미지 크레딧 링크 수(Unsplash 작가·사이트)
    license_urls_excluded: int   # 빼 버린 라이선스 링크 수(CC BY·OGL 본문)
    own_urls_excluded: int = 0   # 빼 버린 자기 사이트 링크 수(`--own-domain`)
    own_domains: tuple = ()      # 자기 사이트 도메인(소문자)

    def usable(self, url):
        """출처로 셀 수 있는 링크인가: 이미지 크레딧·라이선스 본문·자기 사이트 링크가 아니다."""
        host = host_of(url)
        return not (is_image_credit_host(host) or is_license_url(url) or is_own_host(host, self.own_domains))


def is_own_host(host, own_domains):
    return any(host == domain or host.endswith("." + domain) for domain in own_domains)


def is_license_url(url):
    """라이선스 본문을 가리키는 링크인가(출처가 아니라 이용 조건 안내): creativecommons.org, 경로에 licen(s|c)e 가 든 주소."""
    host = host_of(url)
    if host == "creativecommons.org" or host.endswith(".creativecommons.org"):
        return True
    try:
        path = urlsplit(url).path.lower()
    except ValueError:                      # `http://[abc/x` 같은 깨진 주소(IPv6 괄호) — 라이선스 본문으로 보지 않고 넘어간다(분석을 멈추지 않는다, 독립 검증 P2)
        return False
    return re.search(r"/licen[sc]es?(?:/|$)|open-government-licence", path) is not None


def prepare(post, own_domains=()):
    own = tuple(domain.lower().strip(".") for domain in own_domains)
    zones = split_zones(post.body)
    blocks = build_blocks(zones.main)
    ref = _ref_date(post)
    claims = extract_claims(blocks, ref)
    plain_parts = []
    for block in blocks:
        if block.kind in ("heading", "table_header"):
            continue
        marked, _ = replace_links(block.raw)
        plain_parts.append(to_plain(marked))
    main_plain = "\n".join(part for part in plain_parts if part)
    dropped = Counter()

    def keep(urls):
        kept = []
        for url in urls:
            if is_image_credit_host(host_of(url)):
                dropped["credit"] += 1
            elif is_license_url(url):
                dropped["license"] += 1
            elif is_own_host(host_of(url), own):
                dropped["own"] += 1
            else:
                kept.append(url)
        return kept

    body_urls = keep([url for block in blocks if block.kind != "heading" for url in urls_in(block.raw)])
    list_urls = keep([url for item in zones.sources_items for url in urls_in(item)])
    citation_urls = keep([url for line in zones.citation_lines for url in urls_in(line)])
    dropped["credit"] += sum(1 for line in zones.credit_lines for url in urls_in(line) if is_image_credit_host(host_of(url)))
    return Prepared(post, zones, blocks, claims, main_plain, chars_nospace(main_plain), ref, body_urls, list_urls, citation_urls,
                    dropped["credit"], dropped["license"], dropped["own"], own)


def _null(result, key, reason):
    result[key] = None
    result.setdefault("null_reasons", {})[key] = reason


# ----------------------------------------------------------------------------
# 항목 1 — 핵심 사실 주장 수
# ----------------------------------------------------------------------------
def measure_claims(prep, detail=False):
    claims = prep.claims
    by_anchor = Counter()
    for claim in claims:
        if any(token.kind == "percent" for token in claim.numbers):
            by_anchor["percent"] += 1
        if any(token.kind == "money" for token in claim.numbers):
            by_anchor["money"] += 1
        if any(token.kind in ("number", "year") for token in claim.numbers):
            by_anchor["number"] += 1
        if claim.dates:
            by_anchor["date"] += 1
        if claim.entities:
            by_anchor["entity"] += 1
    sentence_count = sum(len(split_sentences(replace_links(block.raw)[0])) for block in prep.blocks
                         if block.kind in ("paragraph", "list", "table_row"))
    numeric = sum(1 for claim in claims if claim.numeric)
    result = {
        "total": len(claims),
        "numeric": numeric,
        "entity_only": len(claims) - numeric,
        "by_anchor": {key: by_anchor.get(key, 0) for key in ("number", "percent", "money", "date", "entity")},
        "sentences_considered": sentence_count,
        "null_reasons": {},
    }
    if sentence_count:
        result["claim_ratio"] = round(len(claims) / sentence_count, 3)
    else:
        _null(result, "claim_ratio", "본문 문장이 없다")
    if detail:
        result["detail"] = [{"text": snippet(claim.text, 160), "numbers": [token.text for token in claim.numbers],
                             "dates": [mention.text for mention in claim.dates], "entities": claim.entities[:6], "linked": bool(claim.urls)}
                            for claim in claims]
    return result


# ----------------------------------------------------------------------------
# 항목 3 — 출처 수 (항목 2·4·6·9 가 이 결과를 쓴다)
# ----------------------------------------------------------------------------
def collect_source_domains(prep):
    """출처 도메인 집계: 머리말 source_url·본문 링크·출처 목록 링크·인용 줄 링크의 합(이미지 크레딧·라이선스·자기 사이트 링크 제외)."""
    urls = []
    if prep.post.source_url and prep.usable(prep.post.source_url):
        urls.append(prep.post.source_url)
    urls += prep.body_urls + prep.list_urls + prep.citation_urls
    hosts = sorted({host_of(url) for url in urls if host_of(url)})
    domains = sorted({registrable_domain(host) for host in hosts})
    return urls, hosts, domains


def measure_sources(prep):
    post = prep.post
    urls, hosts, domains = collect_source_domains(prep)
    body_unique = sorted({normalize_url(url) for url in prep.body_urls})
    source_url_host = host_of(post.source_url)
    counted_items = [item for item in prep.zones.sources_items                                  # 이미지 크레딧 링크뿐인 항목은 출처 목록 항목으로 세지 않는다
                     if not (urls_in(item) and all(is_image_credit_host(host_of(url)) for url in urls_in(item)))]
    in_body = None
    if post.source_url:
        in_body = normalize_url(post.source_url) in set(body_unique) or normalize_url(post.source_url) in {normalize_url(u) for u in prep.list_urls}
    result = {
        "distinct_domains": len(domains),
        "distinct_hosts": len(hosts),
        "domains": domains,
        "official_domains": sorted({registrable_domain(host) for host in hosts if classify_host(host)[0] in OFFICIAL_CATEGORIES}),
        "categories": sorted({classify_host(host)[0] for host in hosts}),
        "body_links": len(prep.body_urls),
        "body_links_unique": len(body_unique),
        "front_matter_source_url": bool(post.source_url),
        "source_url_domain": registrable_domain(source_url_host) if source_url_host else "",
        "source_url_in_text": in_body,
        "sources_section_present": bool(prep.zones.sources_heading),
        "sources_list_items": len(counted_items),
        "citation_line": bool(prep.zones.citation_lines),
        "image_credit_links_excluded": prep.credit_urls_excluded,
        "license_links_excluded": prep.license_urls_excluded,
        "own_site_links_excluded": prep.own_urls_excluded,
        "null_reasons": {},
    }
    if in_body is None:
        _null(result, "source_url_in_text", "머리말에 source_url 이 없다")
    return result


# ----------------------------------------------------------------------------
# 항목 2 — 공식 근거로 지원되는 주장 수
# ----------------------------------------------------------------------------
_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


@dataclass
class SourceText:
    text: str
    lower: str
    number_keys: set          # 숫자 값(언어·표기와 무관한 키)
    year_keys: set            # 글에 나온 연도(숫자로도, 날짜로도)
    month_keys: set           # (연, 월)
    day_keys: set             # 날짜(일 단위, 기간이면 시작·끝 둘 다)
    hangul: bool


def _mask_spans(text, spans):
    return _blank_spans(text, spans)


def build_source_text(text, ref_date=None):
    """원문 텍스트를 대조용 색인(숫자 값·날짜·연도)으로 바꾼다."""
    text = normalize_newlines(text)
    dates = find_dates(text, ref_date)
    numbers = find_numbers(_mask_spans(text, [mention.span for mention in dates]))
    letters = [ch for ch in text if ch.isalpha()]
    hangul = bool(letters) and sum(1 for ch in letters if "가" <= ch <= "힣") / len(letters) > 0.3
    years = {int(token.value) for token in numbers if token.kind == "year"} | {mention.start.year for mention in dates} | {mention.end.year for mention in dates}
    days = {mention.start for mention in dates if mention.precision == "day"} | {mention.end for mention in dates if mention.precision == "day"}
    return SourceText(text, text.lower(), {numeric_key(token.value) for token in numbers}, years,
                      {(mention.start.year, mention.start.month) for mention in dates}, days, hangul)


def _number_supported(token, source):
    if token.kind == "year" and int(token.value) in source.year_keys:
        return True
    if numeric_key(token.value) in source.number_keys:
        return True
    if token.kind == "number" and token.value == int(token.value) and int(token.value) in _NUMBER_WORDS:
        return re.search(r"\b" + _NUMBER_WORDS[int(token.value)] + r"\b", source.lower) is not None
    return False


def _date_supported(mention, source):
    if mention.precision == "day":
        return mention.start in source.day_keys and mention.end in source.day_keys
    return (mention.start.year, mention.start.month) in source.month_keys


def _entity_supported(entity, source):
    """고유명사는 낱말 하나(앞 6글자)라도 원문에 있으면 지지로 본다 — 숫자·날짜보다 느슨한 확인이다."""
    for word in re.findall(r"[A-Za-z][A-Za-z’'\-]{2,}|[가-힣]{2,}", entity):
        if word.lower() in ("the", "and", "for", "of"):
            continue
        if word[:6].lower() in source.lower:
            return True
    return False


def check_claim_against_source(claim, source):
    """'supported' · 'unsupported' · 'unverifiable'. 숫자·날짜는 모두 원문에 있어야 하고(값으로 비교 — 4,975만 = $49.75 million),
    숫자·날짜가 없는 문장은 고유명사가 원문에 있는지만 본다. 한글 고유명사는 원문이 영어이면 비교할 수 없다."""
    checkable_entities = [entity for entity in claim.entities if re.search(r"[A-Za-z]", entity) or source.hangul]
    if not (claim.numbers or claim.dates or checkable_entities):
        return "unverifiable"
    for token in claim.numbers:
        if not _number_supported(token, source):
            return "unsupported"
    for mention in claim.dates:
        if not _date_supported(mention, source):
            return "unsupported"
    if not (claim.numbers or claim.dates):
        if not all(_entity_supported(entity, source) for entity in checkable_entities):
            return "unsupported"
    return "supported"


def measure_grounding(prep, source_text=None, detail=False):
    post = prep.post
    claims = prep.claims
    result = {"claims_checked": len(claims), "null_reasons": {}, "unsupported_examples": []}
    if source_text is not None:
        source = build_source_text(source_text, prep.ref_date)
        counts = Counter()
        for claim in claims:
            status = check_claim_against_source(claim, source)
            counts[status] += 1
            if status == "unsupported" and len(result["unsupported_examples"]) < 5:
                result["unsupported_examples"].append(snippet(claim.text))
        verifiable = counts["supported"] + counts["unsupported"]
        result.update({"mode": "source_text", "approximate": False, "basis": "주장의 숫자·날짜·고유명사가 원문 텍스트에 있는가",
                       "supported": counts["supported"], "unsupported": counts["unsupported"], "unverifiable": counts["unverifiable"],
                       "supported_ratio": round(counts["supported"] / verifiable, 3) if verifiable else None})
        if not verifiable:
            result["null_reasons"]["supported_ratio"] = "원문과 대조할 수 있는 주장이 없다"
        result["linked_in_sentence"] = result["linked_in_paragraph"] = result["linked_official_in_paragraph"] = None
        for key in ("linked_in_sentence", "linked_in_paragraph", "linked_official_in_paragraph"):
            result["null_reasons"][key] = "원문 텍스트로 대조했으므로 링크 근사치는 내지 않는다"
        return result
    has_any_source = bool(post.source_url or prep.body_urls or prep.list_urls)
    if not has_any_source:
        result.update({"mode": "unavailable", "basis": "원문 텍스트·source_url·본문 링크가 모두 없다"})
        for key in ("approximate", "supported", "unsupported", "unverifiable", "supported_ratio", "linked_in_sentence", "linked_in_paragraph", "linked_official_in_paragraph"):
            _null(result, key, "원문이 전혀 없다(원문 텍스트·머리말 source_url·본문 링크 모두 없음)")
        return result
    paragraph_urls = {}
    for claim in claims:
        paragraph_urls.setdefault(claim.para, [])
        paragraph_urls[claim.para] += claim.urls
    for block in prep.blocks:                                         # 주장이 아닌 문장에 붙은 링크도 같은 문단의 링크다
        if block.kind in ("paragraph", "list", "table_row"):
            paragraph_urls.setdefault(block.index, [])
            paragraph_urls[block.index] += [url for url in urls_in(block.raw) if url not in paragraph_urls[block.index]]
    in_sentence = in_paragraph = official_in_paragraph = 0
    for claim in claims:
        usable_sentence = [url for url in claim.urls if prep.usable(url)]
        usable_paragraph = [url for url in paragraph_urls.get(claim.para, []) if prep.usable(url)]
        if usable_sentence:
            in_sentence += 1
        if usable_paragraph:
            in_paragraph += 1
            if any(classify_host(host_of(url))[0] in OFFICIAL_CATEGORIES for url in usable_paragraph):
                official_in_paragraph += 1
    result.update({"mode": "inline_link_approx", "approximate": True,
                   "basis": "근사치: 같은 문단에 공식 기관·연구기관 본문 링크가 붙은 주장 수(링크가 있다고 그 주장을 뒷받침하는 것은 아니다)",
                   "supported": official_in_paragraph, "linked_in_sentence": in_sentence, "linked_in_paragraph": in_paragraph,
                   "linked_official_in_paragraph": official_in_paragraph})
    result["supported_ratio"] = round(official_in_paragraph / len(claims), 3) if claims else None
    if not claims:
        result["null_reasons"]["supported_ratio"] = "주장이 없다"
    for key in ("unsupported", "unverifiable"):
        _null(result, key, "원문 텍스트가 없어 어긋남을 판정할 수 없다(근사 모드)")
    return result


# ----------------------------------------------------------------------------
# 항목 4 — 원문 대비 추가 가치(신호를 나눠 낸다: 하나의 점수로 합치지 않는다)
# ----------------------------------------------------------------------------
# 글쓴이가 직접 계산했다고 밝히는 표현만 센다('통계청이 산출한' 같은 출처의 계산·'환산'이라는 낱말 자체는 세지 않는다 —
# 원문에 없는 환산은 가치가 아니라 근거 없는 추가다). 비교 표시는 흔한 낱말이라 신호로만 보고하고 '직접 작업' 판정에는 쓰지 않는다.
_CALC_MARKERS = re.compile(
    r"직접\s?(?:계산|산출|구한|구해)|계산(?:해|하)\s?보면|계산하면|환산하면|\bwe (?:calculat|comput)ed\b|\bour (?:own )?(?:calculations?|analysis|estimates?)\b"
    r"|\bcalculated (?:here|by us)\b|\bif we (?:calculate|compute|convert)\b", re.I)
_COMPARE_MARKERS = re.compile(r"비교|대비|차이|compar|versus|\bvs\b|difference between", re.I)


def measure_added_value(prep, sources, grounding):
    table_rows = sum(1 for block in prep.blocks if block.kind == "table_row")
    result = {"null_reasons": {}}
    if grounding.get("mode") == "source_text":
        verifiable = grounding["supported"] + grounding["unsupported"]
        result["unsupported_addition_ratio"] = round(grounding["unsupported"] / verifiable, 3) if verifiable else None
        if not verifiable:
            result["null_reasons"]["unsupported_addition_ratio"] = "원문과 대조할 수 있는 주장이 없다"
    else:
        _null(result, "unsupported_addition_ratio", "원문 텍스트가 없어 원문에 없는 주장 비율을 낼 수 없다")
    official = sources["official_domains"]
    result.update({
        "table_data_rows": table_rows,
        "own_calculation_markers": len(_CALC_MARKERS.findall(prep.main_plain)),
        "comparison_markers": len(_COMPARE_MARKERS.findall(prep.main_plain)),
        "distinct_domains": sources["distinct_domains"],
        "distinct_official_domains": len(official),
    })
    result["own_work_signals_present"] = bool(table_rows or result["own_calculation_markers"] or result["distinct_official_domains"] >= 2)
    return result


# ----------------------------------------------------------------------------
# 항목 6 — 보도자료·회사 발표 단순 요약 여부
# ----------------------------------------------------------------------------
def primary_source(post, prep):
    """첫째 근거: 머리말 source_url, 없으면 본문 첫 링크. → (url, 도메인, 분류, 설명)."""
    declared = post.source_url if post.source_url and prep.usable(post.source_url) else ""
    url = declared or next(iter(prep.body_urls), "") or next(iter(prep.list_urls), "")
    host = host_of(url)
    category, detail, _ = classify_host(host)
    return url, registrable_domain(host) if host else "", category, detail


def measure_press_release(prep, sources, added):
    post = prep.post
    url, domain, category, detail = primary_source(post, prep)
    reasons = []
    result = {"flag": None, "kind": None, "primary_source_domain": domain, "primary_source_category": category, "press_format_tokens": [],
              "release_wording_in_source_name": bool(RELEASE_WORDS_IN_SOURCE_NAME.search(post.source_name or "")), "reasons": reasons, "null_reasons": {}}
    if not url:
        reason = "근거 주소(머리말 source_url·본문 링크)가 없어 출처 성격을 판단할 수 없다"
        _null(result, "flag", reason)
        _null(result, "kind", reason)
        return result
    strong, weak = press_format_signals(url)
    decisive_weak = [token for token in weak if token not in PRESS_GENERIC_TOKENS]               # `/news/` 하나만으로는 보도자료 형식이 아니다
    press_format = bool(strong) or (category not in OFFICIAL_CATEGORIES and bool(decisive_weak))
    result["press_format_tokens"] = strong + weak if press_format else []
    domains = sources["domains"]
    single = len(domains) <= 1
    categories = sources["categories"]
    company_only = CATEGORY_COMPANY in categories and not any(c in OFFICIAL_CATEGORIES for c in categories)
    weak_own_work = not added["own_work_signals_present"]
    reasons.append(f"첫째 근거 도메인 {domain}({category}: {detail})")
    reasons.append("출처 도메인 1곳" if single else f"출처 도메인 {len(domains)}곳")
    if company_only:
        reasons.append("공식 기관·연구기관 출처가 없고 회사 도메인뿐")
    if press_format:
        reasons.append("주소가 보도자료·발표 형식(" + ", ".join(strong + weak) + ")")
    if weak_own_work:
        reasons.append("표·계산 표시·공식 출처 2곳 이상 같은 직접 작업 신호가 없다")
    if category == CATEGORY_COMPANY and (single or company_only) and weak_own_work:
        result.update({"flag": True, "kind": "company_release_summary"})
    elif category in OFFICIAL_CATEGORIES and press_format and single and weak_own_work and bool(strong):
        result.update({"flag": True, "kind": "official_press_release_summary"})
    elif category in (CATEGORY_NEWS, CATEGORY_UNKNOWN, CATEGORY_OTHER) and press_format and single and weak_own_work:
        result.update({"flag": True, "kind": "press_format_summary"})
    else:
        result.update({"flag": False, "kind": "none"})
    return result


# ----------------------------------------------------------------------------
# 항목 7 — 행사 안내 중심 여부
# ----------------------------------------------------------------------------
# (표시 이름, 정규식). '부스트'(boost)·'참가국' 같은 다른 뜻의 낱말은 정규식에서 뺀다.
EVENT_TERMS = (
    ("행사", r"행사"), ("개최", r"개최"), ("개막", r"개막"), ("폐막", r"폐막"), ("성료", r"성료"), ("참가", r"참가(?!국)"), ("참석", r"참석"),
    ("접수", r"접수"), ("부스", r"부스(?!트)"), ("박람회", r"박람회"), ("엑스포", r"엑스포"), ("컨퍼런스", r"컨퍼런스|콘퍼런스"), ("세미나", r"세미나"),
    ("웨비나", r"웨비나"), ("워크숍", r"워크숍|워크샵"), ("포럼", r"포럼"), ("심포지엄", r"심포지엄"), ("기조연설", r"기조연설"), ("오픈랩", r"오픈랩"),
    ("열리는", r"열리는|열린다|열릴|열렸"), ("전시회", r"전시회"), ("행사 일정", r"일정(?:을|이|은|표|에 따라)"), ("신청 기간", r"신청(?:서|\s?기간|\s?마감)"),
    ("event", r"\bevents?\b"), ("expo", r"\bexpo\b"), ("conference", r"\bconferences?\b"), ("congress", r"\bcongress\b"), ("summit", r"\bsummits?\b"),
    ("webinar", r"\bwebinars?\b"), ("workshop", r"\bworkshops?\b"), ("symposium", r"\bsymposium\b"), ("exhibition", r"\bexhibitions?\b"),
    ("trade fair", r"\btrade fair\b"), ("booth", r"\bbooth\b"), ("keynote", r"\bkeynote\b"), ("agenda", r"\bagenda\b"),
    ("register", r"\bregist(?:er|ration)\b"), ("take place", r"will take place|takes? place|will be held|to be held"),
    ("attend", r"\battend(?:s|ing|ees?)?\b"), ("open lab", r"\bopen lab\b"), ("ceremony", r"\bceremony\b"),
    ("joins ... expo", r"\bjoins?\b.{0,40}\b(?:expo|congress|summit)\b"),
    # 독립 검증 P10 — 공청회·브리핑·타운홀·오픈하우스 같은 행사 안내가 신호어에 없어 행사 안내 중심으로 잡히지 않던 미탐을 줄인다
    ("설명회", r"설명회"), ("공청회", r"공청회"), ("간담회", r"간담회"), ("토론회", r"토론회"),
    ("seminar", r"\bseminars?\b"), ("forum", r"\bforums?\b"), ("hearing", r"\bhearings?\b"), ("briefing", r"\bbriefings?\b"),
    ("town hall", r"\btown halls?\b"), ("open house", r"\bopen houses?\b"), ("roundtable", r"\bround[\s-]?tables?\b"))
_EVENT_RX = tuple((label, re.compile(pattern, re.I)) for label, pattern in EVENT_TERMS)


def _event_terms_in(text):
    return [label for label, rx in _EVENT_RX if rx.search(text)]


def measure_event_focus(prep, as_of):
    post = prep.post
    units = [claim_text for claim_text in _unit_texts(prep.blocks)]
    result = {"as_of": as_of.isoformat(), "null_reasons": {}}
    hit_units = 0
    term_counts = Counter()
    for unit in units:
        found = _event_terms_in(unit)
        if found:
            hit_units += 1
            term_counts.update(found)
    title_terms = _event_terms_in(post.title)
    dates = []
    for block in prep.blocks:
        if block.kind in ("heading", "quote", "table_header"):
            continue
        dates += [mention for mention in find_dates(to_plain(replace_links(block.raw)[0]), prep.ref_date) if mention.precision == "day"]
    after_as_of = sorted({mention.end.isoformat() for mention in dates if mention.end > as_of})
    after_post = sorted({mention.end.isoformat() for mention in dates if prep.ref_date and mention.end > prep.ref_date})
    result.update({
        "sentences_considered": len(units),
        "event_sentences": hit_units,
        "event_term_hits": sum(term_counts.values()),
        "distinct_event_terms": len(term_counts),
        "top_terms": [term for term, _ in term_counts.most_common(5)],
        "title_event_terms": title_terms,
        "dates_after_post_date": after_post,
        "dates_after_as_of": after_as_of,
    })
    if units:
        ratio = round(hit_units / len(units), 3)
        result["event_sentence_ratio"] = ratio
        flag = (ratio >= EVENT_SENTENCE_RATIO_MIN and len(term_counts) >= EVENT_DISTINCT_TERMS_MIN) or (bool(title_terms) and ratio >= EVENT_TITLE_RATIO_MIN)
        result["flag"] = flag
    else:
        _null(result, "event_sentence_ratio", "본문 문장이 없다")
        _null(result, "flag", "본문 문장이 없다")
        flag = False
    if after_as_of:
        status = "upcoming"
    elif after_post:
        status = "past_event_dates"
    else:
        status = "no_event_dates"
    result["date_status"] = status
    reasons = []
    if result.get("flag"):
        reasons.append(f"행사 신호어가 든 문장 {hit_units}/{len(units)}개({', '.join(result['top_terms'])})")
        if title_terms:
            reasons.append("제목에 행사 신호어(" + ", ".join(title_terms) + ")")
        if status == "upcoming":
            reasons.append(f"기준일({as_of.isoformat()}) 이후 날짜 {len(after_as_of)}개 — 아직 열리지 않은 행사")
        elif status == "past_event_dates":
            reasons.append("글에 적힌 행사 날짜가 모두 기준일 이전 — 지난 행사 안내(낡은 글)")
    result["reasons"] = reasons
    return result


def _unit_texts(blocks):
    for block in blocks:
        if block.kind in ("heading", "quote", "table_header"):
            continue
        marked, _ = replace_links(block.raw)
        sentences = [marked] if block.kind == "table_row" else split_sentences(marked)
        for sentence in sentences:
            plain = to_plain(sentence)
            if len(plain) >= 8:
                yield plain


# ----------------------------------------------------------------------------
# 항목 8 — 건강 위험 판정
# ----------------------------------------------------------------------------
HEALTH_PROFILE_FILES = {"ko": "blogger_practical_ko.json", "en": "blogger_practical_en.json"}
_PROFILE_DIR = Path(__file__).resolve().parent / "profiles"
_PROFILE_CACHE = {}

# 신호어 사전: (표시 이름, 정규식). strong = 질환·치료·약·보충제·체중 감량·임신·영유아·증상 같은 의료 낱말(하나만 있어도 '주의'),
# weak = 정책·산업 글에서도 흔한 의료 인접어, safety = 사망·사고·식품 안전 같은 안전 인접어. weak·safety 는 서로 다른 것이 둘 이상이어야 '주의'.
# 영문은 낱말 경계를 지킨다(diagnostics 는 의료 '진단'이 아니다). 한글 '진단'은 설비 진단·현황 진단처럼 의료가 아닌 쓰임이 많아 weak 이다.
HEALTH_LEXICON = {
    "ko": {
        "strong": (("질환", r"질환"), ("질병", r"질병"), ("치료", r"치료"), ("약물", r"약물"), ("복용", r"복용"), ("보충제", r"보충제"), ("영양제", r"영양제"),
                   ("건강기능식품", r"건강기능식품"), ("체중 감량", r"체중\s?감량"), ("다이어트", r"다이어트"), ("임신", r"임신|임산부"), ("영유아", r"영유아|신생아"),
                   ("증상", r"증상"), ("감염", r"감염"), ("환자", r"환자"), ("수술", r"수술"), ("항암", r"항암"), ("당뇨", r"당뇨"), ("혈압", r"혈압"),
                   ("우울증", r"우울증"), ("정신건강", r"정신\s?건강"), ("자살", r"자살"), ("과다복용", r"과다\s?복용"), ("의약품", r"의약품"), ("백신", r"백신"),
                   ("알레르기", r"알레르기"), ("식중독", r"식중독"), ("암", r"(?<![가-힣])암(?![가-힣])")),
        "weak": (("진단", r"진단"), ("부작용", r"부작용"), ("처방", r"처방"), ("중독", r"중독"), ("접종", r"접종"), ("의료", r"의료"), ("병원", r"병원"),
                 ("건강", r"건강"), ("의사", r"(?<![가-힣])의사(?!결정|소통|표시|록|일정)")),
        "safety": (("사망", r"사망"), ("사고", r"사고(?!방식|력)"), ("부상", r"부상"), ("유통기한", r"유통기한"), ("소비기한", r"소비기한"), ("섭취", r"섭취"),
                   ("독성", r"독성"), ("식품 안전", r"식품\s?안전"), ("재난", r"재난"), ("폭력", r"폭력"), ("학대", r"학대")),
    },
    "en": {
        "strong": (("disease", r"\bdiseases?\b"), ("illness", r"\billness(?:es)?\b"), ("therapy", r"\btherap(?:y|ies)\b"), ("prescription", r"\bprescri(?:be|bed|ption|ptions)\b"),
                   ("medication", r"\bmedications?\b"), ("dosage", r"\bdosages?\b"), ("supplement", r"\b(?:dietary )?supplements?\b"), ("weight loss", r"\bweight[\s-]loss\b"),
                   ("pregnancy", r"\bpregnan(?:t|cy)\b"), ("infant", r"\binfants?\b|\bnewborns?\b"), ("symptom", r"\bsymptoms?\b"),
                   ("diagnosis", r"\bdiagnos(?:is|es|ed|e|ing)\b"), ("infection", r"\binfections?\b"), ("patient", r"\bpatients?\b"), ("surgery", r"\bsurgery\b|\bsurgical\b"),
                   ("cancer", r"\bcancers?\b"), ("diabetes", r"\bdiabet(?:es|ic)\b"), ("blood pressure", r"\bblood pressure\b"), ("depression", r"\bdepression\b"),
                   ("mental health", r"\bmental health\b"), ("suicide", r"\bsuicid(?:e|al)\b"), ("overdose", r"\boverdos(?:e|es|ed)\b"), ("vaccine", r"\bvaccin(?:e|es|ation|ations)\b"),
                   ("allergy", r"\ballerg(?:y|ies|ic)\b"), ("food poisoning", r"\bfood poisoning\b")),
        "weak": (("side effect", r"\bside effects?\b"), ("addiction", r"\baddict(?:ion|ed|ive)\b"), ("hospital", r"\bhospitals?\b"), ("medical", r"\bmedical(?:ly)?\b"),
                 ("health", r"\bhealth\b"), ("drug", r"\bdrugs?\b"), ("treatment", r"\btreatments?\b")),
        "safety": (("mortality", r"\bmortality\b"), ("death", r"\bdeaths?\b"), ("fatal", r"\bfatal(?:ly|ities|ity)?\b"), ("injury", r"\binjur(?:y|ies|ed)\b"),
                   ("accident", r"\baccidents?\b"), ("shelf life", r"\bshelf[\s-]life\b"), ("expiry", r"\bexpir(?:y|ation|ed)\b"), ("food safety", r"\bfood safety\b"),
                   ("toxic", r"\btoxic(?:ity)?\b"), ("violence", r"\bviolen(?:ce|t)\b"), ("abuse", r"\babuse\b")),
    },
}
_HEALTH_RX = {lang: {group: tuple((label, re.compile(pattern, re.I)) for label, pattern in specs) for group, specs in groups.items()}
              for lang, groups in HEALTH_LEXICON.items()}
_ASSERTIVE_RX = tuple(re.compile(pattern, re.I) for pattern in (
    r"반드시", r"확실(?:히|하)", r"입증", r"증명", r"틀림없", r"분명히", r"명백", r"100\s*%", r"절대", r"완치", r"보장", r"예외 없이", r"의심의 여지",
    r"\bdefinitely\b", r"\bcertainly\b", r"\bundoubtedly\b", r"\bproves?\b", r"\bproven\b", r"\bguarantee[sd]?\b", r"\balways\b", r"\bnever\b",
    r"\bcures?\b", r"\bwithout (?:a )?doubt\b", r"\bno doubt\b"))
# 행동 지시: '복용하세요'·'드세요'·'끊으세요'·'복용하는 것이 좋습니다' / 'you should take'·'stop taking'
_ADVICE_RX = re.compile(
    r"(?:복용|섭취|투여|중단|감량|증량)(?:하)?(?:세요|십시오|지 마세요|지 마십시오|셔야|야 합니다)"
    r"|(?:드세요|드십시오|드시기 바랍니다|먹으세요|먹지 마세요|끊으세요|끊지 마세요|줄이세요|늘리세요)"
    r"|(?:복용|섭취|투여)(?:하는|하시는) 것이 좋습니다"
    r"|\b(?:you (?:should|must|need to)|stop taking|start taking|take \d)\b", re.I)
_DISCLAIMER_RX = re.compile(
    r"상담|문의|전문가|전문의|의사와|약사와|의료진|진료|대신하지|\bconsult\b|\bdoctor\b|\bphysician\b|\bpharmacist\b|healthcare (?:provider|professional)|medical advice|not a substitute",
    re.I)


def _load_health_profile(lang):
    """언어별 Blogger 실용 프로필(본문 위험 규칙)을 읽기 전용으로 읽는다 → (파일 이름, 프로필 또는 None, 이유 또는 None)."""
    name = HEALTH_PROFILE_FILES.get(lang)
    if not name:
        return None, None, "언어를 알 수 없어 건강 규칙 프로필을 고를 수 없다"
    if name not in _PROFILE_CACHE:
        path = _PROFILE_DIR / name
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
            _PROFILE_CACHE[name] = (profile, None) if isinstance(profile, dict) and profile.get("body_banned_patterns") else (None, "프로필에 body_banned_patterns 가 없다")
        except (OSError, ValueError) as exc:
            _PROFILE_CACHE[name] = (None, f"프로필을 읽을 수 없다({exc.__class__.__name__})")
    profile, reason = _PROFILE_CACHE[name]
    return name, profile, reason


def _count_terms(text, specs):
    found = {}
    for label, rx in specs:
        count = len(rx.findall(text))
        if count:
            found[label] = count
    return found


_LONG_DIGIT_RUN_RE = re.compile(r"\d{21,}")


def _clip_digit_runs(text):
    """20자리를 넘는 숫자 연속은 앞 20자리만 남긴다. 빌려 쓰는 프로필 규칙 중 국문 용량 규칙(`\\d+(?:\\.\\d+)?\\s?(?:mg|mcg|…)`)은 숫자가 길게 이어지면
    연속 길이의 제곱 시간이라(4,000자리 한 줄에 0.74초 — 체계적 재탐색에서 찾았다) 그 규칙에 넘기는 글에서만 줄인다. 20자리가 넘는 숫자는 실제 글에 없고,
    규칙이 찾는 '숫자 + 단위'(`9…9mg`)는 줄인 뒤에도 그대로 찾힌다. 규칙 파일(`pipeline/gates.py`·프로필)은 이 도구가 고치지 않는다."""
    return _LONG_DIGIT_RUN_RE.sub(lambda found: found.group(0)[:20], text)


def _word_in_lexicon(word, lexicon):
    """프로필 규칙이 맞춘 낱말을 이 모듈의 의료어 사전(강·약·안전 어느 쪽이든)이 이미 알고 있는가(낱말 단위 중복 제거용)."""
    return bool(word) and any(rx.search(word) for specs in lexicon.values() for _, rx in specs)


def measure_health(prep):
    post = prep.post
    text = prep.main_plain
    lexicon = _HEALTH_RX.get(post.lang) or _HEALTH_RX["en"]
    strong = _count_terms(text, lexicon["strong"])
    weak = _count_terms(text, lexicon["weak"])
    safety = _count_terms(text, lexicon["safety"])
    assertive_hits = []
    advice_hits = []
    for unit in _unit_texts(prep.blocks):
        if not _count_terms(unit, lexicon["strong"]):
            continue
        if any(rx.search(unit) for rx in _ASSERTIVE_RX):
            assertive_hits.append(snippet(unit))
        if _ADVICE_RX.search(unit) and not _DISCLAIMER_RX.search(unit):
            advice_hits.append(snippet(unit))
    profile_name, profile, profile_reason = _load_health_profile(post.lang)
    body_rule_hits = []          # 프로필 본문 위험 규칙(질환·치료·약 …)에 걸린 첫 낱말 — 없으면 빈 목록(측정은 했다), 프로필을 못 읽었으면 null
    banned_hits = []             # 효능 단정 규칙(완치·특효·부작용 없음 …)에 걸린 첫 낱말
    profile_word = ""
    if profile:
        profile_text = _clip_digit_runs(text)
        pattern, word = gates.body_risk_hit(profile_text, profile)
        if pattern:
            body_rule_hits.append({"pattern": snippet(pattern, 60), "word": snippet(word, 40)})
            profile_word = word
        banned_pattern, banned_word = gates.first_match(profile.get("banned_patterns"), profile_text)
        if banned_pattern:
            banned_hits.append({"pattern": snippet(banned_pattern, 60), "word": snippet(banned_word, 40)})
    # 프로필 규칙이 맞춘 낱말이 이미 이 모듈의 의료어 사전(강·약·안전)에 있으면 같은 낱말을 서로 다른 신호 둘로 세지 않는다 — 사전에 없는 낱말일 때만
    # 약한 신호 하나로 더한다(독립 검증 P4: '진단' 한 낱말이 사전과 프로필에서 두 번 세어져 설비 '진단' 글이 주의가 됐다).
    profile_adds_signal = bool(body_rule_hits) and not _word_in_lexicon(profile_word, lexicon)
    weak_signals = set(weak) | set(safety) | ({"프로필 본문 규칙"} if profile_adds_signal else set())
    reasons = []
    if banned_hits:
        reasons.append(f"효능 단정 규칙에 걸림({banned_hits[0]['word']})")
    if assertive_hits:
        reasons.append(f"강한 의료어와 단정 표현이 한 문장에 있음({len(assertive_hits)}문장)")
    if advice_hits:
        reasons.append(f"의료어와 행동 지시가 한 문장에 있고 상담 안내가 없음({len(advice_hits)}문장)")
    if banned_hits or assertive_hits or advice_hits:
        level = "high"
    elif strong or len(weak_signals) >= HEALTH_CAUTION_DISTINCT_MIN:
        level = "caution"
        if strong:
            reasons.append("강한 의료어 " + ", ".join(sorted(strong)))
        if len(weak_signals) >= HEALTH_CAUTION_DISTINCT_MIN:
            reasons.append("약한 의료어·안전 인접어 " + ", ".join(sorted(weak_signals)))
    else:
        level = "none"
    result = {"level": level, "medical_strong_terms": dict(sorted(strong.items())), "medical_weak_terms": dict(sorted(weak.items())),
              "safety_adjacent_terms": dict(sorted(safety.items())), "assertive_with_medical": assertive_hits[:3], "advice_with_medical": advice_hits[:3],
              "profile": profile_name, "profile_body_rule_hits": body_rule_hits, "profile_banned_hits": banned_hits,
              "profile_adds_signal": profile_adds_signal, "reasons": reasons, "null_reasons": {}}
    if profile is None:
        _null(result, "profile_body_rule_hits", profile_reason)
        _null(result, "profile_banned_hits", profile_reason)
    return result


# ----------------------------------------------------------------------------
# 항목 9 — 주제 적합성
# ----------------------------------------------------------------------------
def measure_topic_fit(prep, sources, press, event):
    url, domain, category, detail = primary_source(prep.post, prep)
    reasons = []
    result = {"fit": None, "primary_source_domain": domain, "primary_source_category": category, "reasons": reasons, "null_reasons": {}}
    if not url:
        _null(result, "fit", "근거 주소(머리말 source_url·본문 링크)가 없어 출처 도메인을 분류할 수 없다")
        return result
    categories = sources["categories"]
    any_official = any(c in OFFICIAL_CATEGORIES for c in categories)
    if category in OFFICIAL_CATEGORIES:
        reasons.append(f"첫째 근거가 공식 출처({domain}: {detail})")
        if event.get("flag"):
            result["fit"] = "borderline"
            reasons.append("그러나 행사 안내 중심(항목 7)")
        elif press.get("flag"):
            result["fit"] = "borderline"
            reasons.append("그러나 보도자료 형식을 요약만 한 글(항목 6)")
        else:
            result["fit"] = "core"
    elif category == CATEGORY_UNKNOWN:
        result["fit"] = "borderline"
        reasons.append(f"첫째 근거 도메인({domain})이 분류표에 없다 — 사람이 확인")
    elif any_official:
        result["fit"] = "borderline"
        reasons.append(f"첫째 근거는 {category}({domain})이지만 다른 출처에 공식 도메인이 있다")
    else:
        result["fit"] = "off"
        reasons.append(f"공식 기관·연구기관 출처가 없고 첫째 근거가 {category}({domain})")
        if event.get("flag"):
            reasons.append("행사 안내 중심(항목 7)")
    return result


# ----------------------------------------------------------------------------
# 항목 5 — 한·영 유사도(짝)
# ----------------------------------------------------------------------------
def structure_counts(prep):
    kinds = Counter(block.kind for block in prep.blocks)
    return {"headings": kinds["heading"], "paragraphs": kinds["paragraph"], "bullets": kinds["list"]}


def significant_numbers(prep):
    values = set()
    for claim in prep.claims:
        for token in claim.numbers:
            if token.kind == "year":
                continue
            if token.kind == "number" and token.value == int(token.value) and abs(token.value) <= SMALL_INTEGER_MAX:
                continue
            values.add(numeric_key(token.value))
    return values


def _link_set(prep):
    return {normalize_url(url) for url in prep.body_urls + prep.list_urls}


def _reference_anchors(prep):
    """번역 짝의 참고 신호용 집합(판정에는 쓰지 않는다): ① 본문의 모든 숫자 값과 날짜(연도·31 이하 정수도 포함 — 판정용 숫자 집합보다 넓다)
    ② 영문 고유명사(대문자 낱말열·약어. 한글 이름은 찾지 못한다)."""
    plain = prep.main_plain
    dates = find_dates(plain, prep.ref_date)
    numbers = find_numbers(_mask_spans(plain, [mention.span for mention in dates]))
    values = {"n" + numeric_key(token.value) for token in numbers} | {"d" + mention.start.isoformat() for mention in dates}
    names = {entity.lower() for claim in prep.claims for entity in claim.entities if re.search(r"[A-Za-z]", entity)}
    return values, names


def _overlap(result, key, shared_key, left, right, reason):
    """두 집합의 자카드를 result[key] 에(합집합이 비면 null + 이유), 공유 개수를 result[shared_key] 에 적는다."""
    union = left | right
    result[shared_key] = len(left & right)
    if union:
        result[key] = round(len(left & right) / len(union), 3)
    else:
        _null(result, key, reason)


def pair_metrics(ko_prep, en_prep):
    ko_post, en_post = ko_prep.post, en_prep.post
    ko_structure, en_structure = structure_counts(ko_prep), structure_counts(en_prep)
    matched = sum(1 for key in ko_structure if ko_structure[key] == en_structure[key])
    within = sum(1 for key in ko_structure if abs(ko_structure[key] - en_structure[key]) <= CLONE_STRUCTURE_TOLERANCE)
    ko_numbers, en_numbers = significant_numbers(ko_prep), significant_numbers(en_prep)
    ko_links, en_links = _link_set(ko_prep), _link_set(en_prep)
    result = {"null_reasons": {}, "pair_key": ko_post.pair_key, "date": ko_post.date, "ko": ko_post.rel, "en": en_post.rel,
              "structure": {"ko": ko_structure, "en": en_structure, "matched": matched, "within_tolerance": within},
              "shared_links": len(ko_links & en_links), "ko_links": len(ko_links), "en_links": len(en_links),
              "both_published": ko_post.published and en_post.published}
    union = ko_numbers | en_numbers
    if union:
        result["number_jaccard"] = round(len(ko_numbers & en_numbers) / len(union), 3)
    else:
        _null(result, "number_jaccard", "양쪽 글에 의미 있는 숫자가 없다")
    result["ko_numbers"], result["en_numbers"] = len(ko_numbers), len(en_numbers)
    if ko_prep.main_chars:
        result["length_ratio_en_per_ko"] = round(en_prep.main_chars / ko_prep.main_chars, 3)
    else:
        _null(result, "length_ratio_en_per_ko", "국문 본문 글자 수가 0 이다")
    same_url = None
    if ko_post.source_url and en_post.source_url:
        same_url = normalize_url(ko_post.source_url) == normalize_url(en_post.source_url)
    result["same_source_url"] = same_url
    if same_url is None:
        result["null_reasons"]["same_source_url"] = "한쪽 또는 양쪽 머리말에 source_url 이 없다"
    # 참고 신호(판정 임계값에는 쓰지 않는다): 구조 하나에만 기대지 않도록 두 글이 같은 숫자·날짜·영문 이름을 얼마나 나누는지 적어 둔다
    ko_values, ko_names = _reference_anchors(ko_prep)
    en_values, en_names = _reference_anchors(en_prep)
    _overlap(result, "ref_numbers_jaccard", "ref_shared_numbers", ko_values, en_values, "양쪽 글에 읽을 숫자·날짜가 없다")
    _overlap(result, "ref_names_jaccard", "ref_shared_names", ko_names, en_names, "양쪽 글에 영문 고유명사가 없다")
    structure_same = within == 3
    number_same = result.get("number_jaccard") is None or result["number_jaccard"] >= CLONE_NUMBER_JACCARD_MIN
    ratio = result.get("length_ratio_en_per_ko")
    in_band = ratio is not None and CLONE_LENGTH_RATIO_BAND[0] <= ratio <= CLONE_LENGTH_RATIO_BAND[1]
    reasons = [f"소제목·문단·불릿 수 차이가 모두 {CLONE_STRUCTURE_TOLERANCE} 이하인 항목 {within}/3(기준 3/3, 정확히 같은 항목 {matched}/3)"]
    if result.get("number_jaccard") is None:
        reasons.append("숫자 겹침은 비교할 숫자가 없어 제외")
    else:
        reasons.append(f"숫자 겹침 {result['number_jaccard']}(기준 {CLONE_NUMBER_JACCARD_MIN})")
    reasons.append(f"길이 비율 {ratio}(번역 범위 {CLONE_LENGTH_RATIO_BAND[0]}–{CLONE_LENGTH_RATIO_BAND[1]})")
    reasons.append("참고(판정에 쓰지 않음): 모든 숫자·날짜 겹침 "
                   + ("측정 불가" if result["ref_numbers_jaccard"] is None else str(result["ref_numbers_jaccard"]))
                   + ", 영문 이름 겹침 " + ("측정 불가" if result["ref_names_jaccard"] is None else str(result["ref_names_jaccard"])))
    if same_url is False:
        # 출처 주소가 달라도(정규화 뒤에도) '번역 짝이 아니다'로 단정하지 않는다 — 판정을 보류해 null + 이유로 둔다(독립 검증 P6)
        suspected = None
        result["null_reasons"]["translation_clone_suspected"] = ("source_url_differs: 출처 주소가 달라 같은 글의 번역 짝인지 판정하지 않는다"
                                                                 "(파일 이름 끝 6자리만 같은 다른 글일 수 있다. 구조·숫자·길이는 참고로만 적는다)")
        reasons.insert(0, "source_url_differs: 출처 주소가 다르다 — 번역 짝이 아니라고 단정하지 않고 판정을 보류한다")
    else:
        suspected = structure_same and number_same and in_band
    result["translation_clone_suspected"] = suspected
    result["reasons"] = reasons
    return result


# ----------------------------------------------------------------------------
# 조립
# ----------------------------------------------------------------------------
def analyze_prepared(prep, as_of, source_text=None, detail=False):
    sources = measure_sources(prep)
    claims = measure_claims(prep, detail)
    grounding = measure_grounding(prep, source_text, detail)
    added = measure_added_value(prep, sources, grounding)
    press = measure_press_release(prep, sources, added)
    event = measure_event_focus(prep, as_of)
    health = measure_health(prep)
    topic = measure_topic_fit(prep, sources, press, event)
    post = prep.post
    return {
        "path": post.rel, "date": post.date or None, "kind": post.kind or None, "lang": post.lang or None, "pair_key": post.pair_key or None,
        "published": post.published, "title": snippet(post.title, 200),
        "body": {"main_chars_nospace": prep.main_chars, **structure_counts(prep), "table_data_rows": added["table_data_rows"],
                 "long_lines_truncated": prep.zones.truncated_lines},
        "claims": claims, "grounding": grounding, "sources": sources, "added_value": added,
        "press_release_summary": press, "event_focus": event, "health_risk": health, "topic_fit": topic,
    }


def analyze_post(post, as_of, source_text=None, detail=False):
    return analyze_prepared(prepare(post), as_of, source_text, detail)


def find_source_text(post, sources_dir):
    """원문 텍스트 파일 찾기: `<이름>.txt|md` → `<날짜>-<6자리>.txt|md` → `<6자리>.txt|md`. 없으면 None."""
    if sources_dir is None:
        return None
    candidates = [post.name]
    if post.pair_key:
        candidates += [f"{post.date}-{post.pair_key}" if post.date else post.pair_key, post.pair_key]
    for stem in candidates:
        for suffix in (".txt", ".md"):
            path = sources_dir / (stem + suffix)
            if path.is_file():
                return read_text_file(path)
    return None


def collect_posts(posts_path):
    """(글 목록, 건너뜀·읽기 오류 목록). 폴더면 `*.md` 를 재귀로 읽고, 파일이면 그 하나만 읽는다. 정렬은 상대 경로(코드 포인트) 순서."""
    posts, problems = [], []
    if posts_path.is_file():
        files = [(posts_path, posts_path.name)]
    elif posts_path.is_dir():
        files = sorted(((p, p.relative_to(posts_path).as_posix()) for p in posts_path.rglob("*.md") if p.is_file()), key=lambda item: item[1])
    else:
        raise QualityShadowError(f"글 경로가 없다: {posts_path.name}")
    for path, rel in files:
        try:
            posts.append(parse_post(read_text_file(path), rel))
        except PostReadError as exc:
            problems.append({"path": rel, "error": console.one_line(str(exc), 160)})
    return posts, problems


def pair_posts(posts):
    """(날짜, 6자리) 키로 국문·영문 쌍을 만든다(6자리만으로는 10-26 과 10-29 의 글이 겹친다). → (쌍 목록, 짝 없는 글 목록)"""
    groups = {}
    for post in posts:
        if post.pair_key and post.lang in ("ko", "en"):
            groups.setdefault((post.date, post.pair_key), {}).setdefault(post.lang, []).append(post)
    pairs, paired = [], set()
    for key in sorted(groups):
        group = groups[key]
        if len(group.get("ko", [])) == 1 and len(group.get("en", [])) == 1:
            pairs.append((group["ko"][0], group["en"][0]))
            paired.update((group["ko"][0].rel, group["en"][0].rel))
    return pairs, [post for post in posts if post.rel not in paired]


def _count(values):
    return dict(sorted(Counter(str(value) for value in values).items()))


def summarize(post_results, pair_results, problems):
    def block(results):
        return {
            "posts": len(results),
            "claims_total": sum(r["claims"]["total"] for r in results),
            "claims_numeric": sum(r["claims"]["numeric"] for r in results),
            "press_release_summary": _count(r["press_release_summary"]["kind"] for r in results),
            "event_focus_flag": _count(r["event_focus"].get("flag") for r in results),
            "health_level": _count(r["health_risk"]["level"] for r in results),
            "topic_fit": _count(r["topic_fit"]["fit"] for r in results),
        }
    published = [r for r in post_results if r["published"]]
    private = [r for r in post_results if not r["published"]]
    null_counts = Counter()
    for result in post_results:
        for section in ("claims", "grounding", "sources", "added_value", "press_release_summary", "event_focus", "health_risk", "topic_fit"):
            for key in result[section].get("null_reasons", {}):
                null_counts[f"{section}.{key}"] += 1
    both_published = [p for p in pair_results if p["both_published"]]
    return {"all": block(post_results), "published": block(published), "private": block(private),
            "pairs": len(pair_results), "translation_clone_suspected": sum(1 for p in pair_results if p["translation_clone_suspected"]),
            "translation_clone_undetermined": sum(1 for p in pair_results if p["translation_clone_suspected"] is None),
            "pairs_both_published": len(both_published),
            "translation_clone_suspected_both_published": sum(1 for p in both_published if p["translation_clone_suspected"]),
            "unpaired_posts": sum(1 for r in post_results if r["pair"] is None), "read_problems": len(problems),
            "null_counts": dict(sorted(null_counts.items()))}


def _guarded(problems, rel, step, function, *args):
    """글 하나를 처리하다 예외가 나면 그 글만 `read_problems` 에 적고 계속한다(일괄 실행을 멈추지 않는다, 독립 검증 P2) → 결과 또는 None.
    메시지는 같은 입력에 같은 글이 되도록 예외 종류(또는 이 도구가 만든 안전한 문구)만 싣고, 입력 글의 내용이나 절대 경로는 싣지 않는다."""
    try:
        return function(*args)
    except QualityShadowError as exc:
        problems.append({"path": rel, "error": console.one_line(f"{step}: {exc}", 160)})
    except Exception as exc:                       # noqa: BLE001 — 입력이 아무리 이상해도 다른 글의 측정을 막지 않는다
        problems.append({"path": rel, "error": f"{step} 중 예외({exc.__class__.__name__})"})
    return None


def _analyze_one(prep, as_of, single_source_text, sources_dir, detail):
    source_text = single_source_text if single_source_text is not None else find_source_text(prep.post, sources_dir)
    return analyze_prepared(prep, as_of, source_text, detail)


def analyze_corpus(posts, as_of, sources_dir=None, single_source_text=None, detail=False, problems=(), own_domains=()):
    """글 목록 → 보고서 사전. 입력 글·원문 파일은 읽기만 한다. `own_domains` 는 자기 사이트 도메인(그 링크는 외부 출처로 세지 않는다).
    글 하나를 준비·비교·분석하다 예외가 나면 그 글(또는 그 짝)만 `read_problems` 에 적고 나머지는 계속 잰다."""
    own = tuple(sorted({domain.lower().strip(".") for domain in own_domains}))
    problems = list(problems)
    preps = {}
    for post in posts:
        prep = _guarded(problems, post.rel, "준비", prepare, post, own)
        if prep is not None:
            preps[post.rel] = prep
    measured = [post for post in posts if post.rel in preps]
    pairs, _ = pair_posts(measured)
    pair_by_rel = {}
    pair_results = []
    for ko_post, en_post in pairs:
        result = _guarded(problems, ko_post.rel, f"짝 비교(짝 글 {en_post.rel})", pair_metrics, preps[ko_post.rel], preps[en_post.rel])
        if result is None:
            continue
        pair_results.append(result)
        pair_by_rel[ko_post.rel] = pair_by_rel[en_post.rel] = result
    post_results = []
    for post in measured:
        result = _guarded(problems, post.rel, "분석", _analyze_one, preps[post.rel], as_of, single_source_text, sources_dir, detail)
        if result is None:
            continue
        pair = pair_by_rel.get(post.rel)
        if pair is None:
            result["pair"] = None
            result["null_reasons"] = {"pair": "같은 날짜·같은 6자리 키의 국문·영문 짝이 없다" if post.pair_key else "파일 이름에 6자리 짝 키가 없다"}
        else:
            partner = pair["en"] if post.rel == pair["ko"] else pair["ko"]
            result["pair"] = {"partner": partner, "translation_clone_suspected": pair["translation_clone_suspected"],
                              "same_source_url": pair["same_source_url"]}
            result["null_reasons"] = {}
        post_results.append(result)
    report = {
        "tool": TOOL_NAME, "schema_version": SCHEMA_VERSION, "as_of": as_of.isoformat(), "note": NOT_A_VERDICT,
        "thresholds": {"clone_structure_tolerance": CLONE_STRUCTURE_TOLERANCE, "clone_number_jaccard_min": CLONE_NUMBER_JACCARD_MIN,
                       "clone_length_ratio_band": list(CLONE_LENGTH_RATIO_BAND), "event_sentence_ratio_min": EVENT_SENTENCE_RATIO_MIN,
                       "event_distinct_terms_min": EVENT_DISTINCT_TERMS_MIN, "event_title_ratio_min": EVENT_TITLE_RATIO_MIN,
                       "health_caution_distinct_min": HEALTH_CAUTION_DISTINCT_MIN, "small_integer_max": SMALL_INTEGER_MAX},
        "options": {"own_domain_count": len(own), "detail": bool(detail)},
        "posts": post_results, "pairs": pair_results, "read_problems": problems,
        "summary": summarize(post_results, pair_results, problems),
    }
    return report


# ----------------------------------------------------------------------------
# 보고서 출력
# ----------------------------------------------------------------------------
def render_json(report):
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


PRESS_LABELS = {"company_release_summary": "회사 발표 요약", "official_press_release_summary": "공식 보도자료 요약", "press_format_summary": "보도자료 형식 요약",
                "none": "해당 없음", None: "측정 불가"}
HEALTH_LABELS = {"none": "없음", "caution": "주의", "high": "높음"}
FIT_LABELS = {"core": "핵심", "borderline": "경계", "off": "비핵심", None: "측정 불가"}


def _flag_text(value):
    return "측정 불가" if value is None else ("예" if value else "아니오")


def _clone_text(suspected, same_url):
    """번역 복제 의심 칸: 출처 주소가 달라 판정을 보류한 쌍은 '측정 불가'가 아니라 이유를 보인다."""
    return "보류(주소 다름)" if suspected is None and same_url is False else _flag_text(suspected)


def _count_text(counter, labels):
    """{'none': 5, 'caution': 2} → '없음 5 · 주의 2' (JSON 키가 문자열이라 None 은 'None' 으로 들어온다)."""
    pieces = []
    for key, count in counter.items():
        label = labels.get(None if key == "None" else key, key)
        pieces.append(f"{label} {count}")
    return " · ".join(pieces) if pieces else "-"


def render_markdown(report):
    cell = console.md_cell
    summary = report["summary"]
    lines = [f"# 품질 측정 보고서(그림자 모드) — 기준일 {report['as_of']}", "", f"> {NOT_A_VERDICT}", "",
             "## 요약", "", "| 구분 | 글 | 주장(숫자 주장) | 보도자료·발표 요약 | 행사 안내 중심 | 건강 위험 | 주제 적합성 |", "|---|---|---|---|---|---|---|"]
    for name, key in (("전체", "all"), ("공개", "published"), ("비공개", "private")):
        block = summary[key]
        lines.append("| {} | {} | {}({}) | {} | {} | {} | {} |".format(
            name, block["posts"], block["claims_total"], block["claims_numeric"], _count_text(block["press_release_summary"], PRESS_LABELS),
            _count_text(block["event_focus_flag"], {"True": "예", "False": "아니오", None: "측정 불가"}), _count_text(block["health_level"], HEALTH_LABELS),
            _count_text(block["topic_fit"], FIT_LABELS)))
    lines += ["", f"한·영 짝 {summary['pairs']}쌍(둘 다 공개 {summary['pairs_both_published']}쌍) 중 번역 복제 의심 {summary['translation_clone_suspected']}쌍"
                  f"(둘 다 공개한 쌍 중 {summary['translation_clone_suspected_both_published']}쌍), 판정 보류(출처 주소가 달라서) {summary['translation_clone_undetermined']}쌍, "
                  f"짝 없는 글 {summary['unpaired_posts']}편, 읽기 문제 {summary['read_problems']}건.", ""]
    lines += ["## 글별", "",
              "| 글 | 공개 | 주장(숫자) | 근거 | 출처(도메인·본문 링크) | 직접 작업 신호 | 보도자료·발표 | 행사 | 건강 | 주제 | 번역 복제 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in report["posts"]:
        g = r["grounding"]
        if g.get("mode") == "source_text":
            ground = f"원문 대조 지지 {g['supported']}·어긋남 {g['unsupported']}·확인 불가 {g['unverifiable']}"
        elif g.get("mode") == "inline_link_approx":
            ground = f"근사 {g['supported']}/{g['claims_checked']}"
        else:
            ground = "측정 불가(원문 없음)"
        s, a = r["sources"], r["added_value"]
        own = f"표 {a['table_data_rows']}·직접 계산 {a['own_calculation_markers']}·공식 도메인 {a['distinct_official_domains']}"
        pair = r["pair"]
        lines.append("| {} | {} | {}({}) | {} | {}·{} | {} | {} | {} | {} | {} | {} |".format(
            cell(r["path"], 80), "공개" if r["published"] else "비공개", r["claims"]["total"], r["claims"]["numeric"], cell(ground, 60),
            s["distinct_domains"], s["body_links"], own, PRESS_LABELS.get(r["press_release_summary"]["kind"], "-"), _flag_text(r["event_focus"].get("flag")),
            HEALTH_LABELS.get(r["health_risk"]["level"], "-"), FIT_LABELS.get(r["topic_fit"]["fit"], "-"),
            "짝 없음" if pair is None else _clone_text(pair["translation_clone_suspected"], pair["same_source_url"])))
    lines += ["", "## 한·영 짝", "", "| 날짜·키 | 정확히 같은 항목 | 차이 ±1 이내 항목 | 숫자 겹침 | 공유 링크 | 길이 비율(영/국) | 같은 출처 주소 | 번역 복제 의심 |", "|---|---|---|---|---|---|---|---|"]
    for p in report["pairs"]:
        lines.append("| {} {} | {}/3 | {}/3 | {} | {} | {} | {} | {} |".format(
            p["date"], p["pair_key"], p["structure"]["matched"], p["structure"]["within_tolerance"],
            "측정 불가" if p.get("number_jaccard") is None else p["number_jaccard"], p["shared_links"],
            "측정 불가" if p.get("length_ratio_en_per_ko") is None else p["length_ratio_en_per_ko"], _flag_text(p["same_source_url"]),
            _clone_text(p["translation_clone_suspected"], p["same_source_url"])))
    lines += ["", "## 측정 불가(null)가 나온 항목 수", ""]
    for key, count in summary["null_counts"].items():
        lines.append(f"- `{key}`: {count}편")
    if not summary["null_counts"]:
        lines.append("- 없음")
    if report["read_problems"]:
        lines += ["", "## 읽거나 분석하지 못한 파일", ""] + [f"- {cell(item['path'], 100)}: {cell(item['error'], 120)}" for item in report["read_problems"]]
    lines += ["", "정의·한계·임계값: docs/QUALITY_SHADOW.md", ""]
    return "\n".join(lines)


def write_report(path, text):
    """보고서 한 파일만 쓴다(이 모듈이 파일을 쓰는 유일한 자리). 상위 폴더는 만들지 않는다.
    이미 있는 폴더이거나 쓸 수 없는 위치면 트레이스백이 아니라 설정 오류(종료 2)로 알린다(독립 검증 P1)."""
    if not path.parent.is_dir():
        raise QualityShadowError(f"--out 의 상위 폴더가 없다: {path.parent.name}")
    if path.is_dir():
        raise QualityShadowError(f"--out 이 이미 있는 폴더다: {path.name}")
    try:
        path.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise QualityShadowError(f"--out 에 쓸 수 없다: {exc.strerror or exc.__class__.__name__}") from exc


# ----------------------------------------------------------------------------
# 명령줄
# ----------------------------------------------------------------------------
def _parse_as_of(value):
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--as-of 는 YYYY-MM-DD 이어야 한다: {console.one_line(value, 40)}") from exc


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.quality_shadow",
        description="글 품질 9항목을 측정하는 그림자 모드 도구(게시와 무관, 네트워크 없음, 쓰기는 --out 하나뿐).")
    parser.add_argument("--posts", required=True, help="글 폴더(_posts) 또는 글 파일 하나")
    parser.add_argument("--as-of", required=True, type=_parse_as_of, dest="as_of", help="날짜 기준 YYYY-MM-DD(필수 — 같은 입력에 같은 출력을 주기 위해)")
    parser.add_argument("--out", help="보고서를 쓸 파일(없으면 표준 출력). 입력 폴더 안은 안 된다")
    parser.add_argument("--sources-dir", dest="sources_dir", help="원문 텍스트 폴더(<글 이름>.txt 또는 <날짜>-<6자리>.txt 또는 <6자리>.txt)")
    parser.add_argument("--source-text", dest="source_text", help="글 파일 하나를 잴 때 쓰는 원문 텍스트 파일")
    parser.add_argument("--format", choices=("json", "md"), help="출력 형식(기본: --out 확장자가 .md 면 md, 아니면 json)")
    parser.add_argument("--detail", action="store_true", help="주장 문장별 목록도 싣는다")
    parser.add_argument("--own-domain", action="append", default=[], dest="own_domains", metavar="DOMAIN",
                        help="자기 사이트 도메인(여러 번 쓸 수 있다). 이 도메인으로 가는 링크는 외부 출처로 세지 않는다(보고서에는 개수만 남는다)")
    return parser


_OWN_DOMAIN_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+")


def _own_domains(values):
    """--own-domain 값 검사: 소문자로 바꾼 도메인 모양(점이 있는 이름)만 받는다. 주소(https://…)나 경로는 거절한다(R15: fullmatch)."""
    domains = []
    for value in values:
        domain = value.strip().lower().strip(".")
        if not _OWN_DOMAIN_RE.fullmatch(domain):
            raise QualityShadowError(f"--own-domain 은 도메인 이름이어야 한다(예: example.github.io): {console.one_line(value, 40)}")
        domains.append(domain)
    return tuple(sorted(set(domains)))


def _resolved(path):
    try:
        return path.resolve()
    except (OSError, RuntimeError) as exc:                       # 심볼릭 링크 순환 같은 풀 수 없는 경로 — 트레이스백이 아니라 설정 오류(종료 2)로 멈춘다
        raise QualityShadowError(f"경로를 해석할 수 없다: {path.name}") from exc


def _inside(path, folder):
    try:
        _resolved(path).relative_to(_resolved(folder))
        return True
    except ValueError:
        return False


def _same_file(path, other):
    """둘이 같은 파일인가(이름이 달라도 하드 링크·짧은 이름이면 같다). 어느 한쪽이 없거나 비교할 수 없으면 False."""
    try:
        return path.is_file() and other.is_file() and path.samefile(other)
    except OSError:
        return False


def _input_files(posts_path, sources_dir, source_text):
    """이 실행이 읽는 입력 파일들(글 파일·글 폴더의 .md·원문 폴더의 파일·원문 파일 하나)."""
    if posts_path.is_file():
        yield posts_path
    elif posts_path.is_dir():
        yield from (path for path in posts_path.rglob("*.md") if path.is_file())
    if sources_dir is not None and sources_dir.is_dir():
        yield from (path for path in sources_dir.rglob("*") if path.is_file())
    if source_text is not None:
        yield source_text


def _check_out_path(out_path, posts_path, sources_dir=None, source_text=None):
    """--out 이 입력을 덮어쓰거나 입력 폴더에 섞이지 못하게 막는다(독립 검증 P1). 막는 것:
    ① 글 폴더 안(글 파일 하나를 줬으면 그 파일이 든 폴더 안·그 파일 자체) — 글이 `_posts` 아래에 있으면 `_posts` 전체(`.md` 보고서가 거기 생기면 글로 발행될 수 있다)
    ② 원문 폴더(--sources-dir) 안 ③ 원문 파일(--source-text) 자체 ④ 이미 있는 폴더 ⑤ 상위 폴더가 없는 경로 ⑥ 이름은 달라도 입력과 같은 파일(하드 링크)."""
    guarded = []
    if posts_path.is_dir():
        guarded.append(posts_path)
    elif posts_path.is_file():
        guarded.append(posts_path.parent)
    guarded += [parent for parent in _resolved(posts_path).parents if parent.name == "_posts"]
    if any(_inside(out_path, folder) for folder in guarded):
        raise QualityShadowError("--out 이 입력 글 폴더 안이다(단일 글이면 그 글이 든 폴더·_posts 안) — 글을 덮어쓰거나 글 폴더에 보고서를 섞지 않도록 막았다")
    if _resolved(out_path) == _resolved(posts_path):
        raise QualityShadowError("--out 이 입력 글 경로 자체다 — 글을 덮어쓰지 않도록 막았다")
    if sources_dir is not None and _inside(out_path, sources_dir):
        raise QualityShadowError("--out 이 원문 폴더(--sources-dir) 안이다 — 원문을 덮어쓰지 않도록 막았다")
    if source_text is not None and _resolved(out_path) == _resolved(source_text):
        raise QualityShadowError("--out 이 원문 파일(--source-text) 자체다 — 원문을 덮어쓰지 않도록 막았다")
    if out_path.is_dir():
        raise QualityShadowError(f"--out 이 이미 있는 폴더다: {out_path.name}")
    if not out_path.parent.is_dir():
        raise QualityShadowError(f"--out 의 상위 폴더가 없다: {out_path.parent.name}")
    if out_path.is_file() and any(_same_file(out_path, path) for path in _input_files(posts_path, sources_dir, source_text)):
        raise QualityShadowError("--out 이 입력 파일과 같은 파일이다(링크) — 입력을 덮어쓰지 않도록 막았다")


def main(argv=None):
    console.safe_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        posts_path = Path(args.posts)
        out_path = Path(args.out) if args.out else None
        sources_dir = Path(args.sources_dir) if args.sources_dir else None
        source_text_path = Path(args.source_text) if args.source_text else None
        if out_path is not None:
            _check_out_path(out_path, posts_path, sources_dir, source_text_path)
        if sources_dir is not None and not sources_dir.is_dir():
            raise QualityShadowError(f"--sources-dir 폴더가 없다: {sources_dir.name}")
        single_source = None
        if source_text_path is not None:
            if not posts_path.is_file():
                raise QualityShadowError("--source-text 는 --posts 가 글 파일 하나일 때만 쓸 수 있다")
            single_source = read_text_file(source_text_path)
        own_domains = _own_domains(args.own_domains)
        posts, problems = collect_posts(posts_path)
        report = analyze_corpus(posts, args.as_of, sources_dir, single_source, args.detail, problems, own_domains)
        fmt = args.format or ("md" if out_path is not None and out_path.suffix.lower() == ".md" else "json")
        text = render_markdown(report) if fmt == "md" else render_json(report)
        measured, problem_count = len(report["posts"]), len(report["read_problems"])           # 읽지 못한 글과 분석 중 예외가 난 글을 모두 센다
        if out_path is not None:
            write_report(out_path, text)
            print(f"보고서를 썼다: {out_path.name} (글 {measured}편, 한·영 짝 {len(report['pairs'])}쌍, 읽기 문제 {problem_count}건)")
        else:
            sys.stdout.write(text)
        if not measured:                                               # 폴더를 잘못 줬을 때 조용히 빈 보고서만 내지 않는다
            print("경고: 측정한 글이 하나도 없다(머리말이 있는 .md 파일을 찾지 못했거나 모두 읽지·분석하지 못했다)", file=sys.stderr)
        return 1 if (problem_count or not measured) else 0
    except QualityShadowError as exc:
        print(f"오류: {console.one_line(str(exc), 300)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
