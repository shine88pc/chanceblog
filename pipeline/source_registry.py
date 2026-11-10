"""허용 목록(Source Registry) — 자동으로 쓰는 외부 자료를 '권리·약관·상업·AI 이용이 분명한 구조화 데이터'로만 제한하는 정본(docs/SOURCE_POLICY.md).

운영자 결정(2026-11-09): 외부 자료는 이 목록에 등록되고 이용 조건 7칸이 모두 확인된(UNKNOWN 0) 구조화 데이터(API·CSV·데이터셋)만 자동으로 쓴다. 외부 RSS 요약·기사·해설문·
검색 스니펫·외부 사진은 발행자가 정부여도 **유형만으로 Tier 3** 이라 목록에 있어도 자동화하지 않는다. 한 칸이라도 UNKNOWN·근거 없음이면 그 Provider 는 자동화에서 꺼진다.

이 모듈은 표준 라이브러리만 쓰고(레지스트리 검증처럼 pip 없이 도는 곳에서도 불러야 한다) 입출력은 `load_registry`·`load_ai_policy`·`main` 에만 있다. 시각은 읽지 않는다 —
점검 기한(`snapshot.expires_at`)을 보는 '오늘'은 부르는 쪽이 인자로 준다(`today`).

구성
- `validate_registry(data, today=None) -> list[str]` : 순수 함수. 모양 검사(모든 Provider)와 ACTIVE 조건(enabled 인 Provider) 문제 목록. 문제 문장은 `provider_id: [규칙번호] 설명` 꼴이다.
- `load_registry(path=None, today=None) -> Registry` : 파일을 읽어 Provider 를 만든다. 문제가 있는 Provider 는 ACTIVE 로 올리지 않고 사유를 `Registry.inactive_reasons()` 에 남긴다(한 줄씩, `report_lines()`).
- `Registry.get / active_providers / is_url_allowed` : FACT(구조화 Fact 경로)와의 인터페이스 약속 — 이름·모양을 바꾸지 않는다. `Provider` 는 읽기 전용(frozen dataclass).
- `split_https_url` : 관문(pipeline/egress.py)과 `is_url_allowed` 가 함께 쓰는 엄격한 주소 분해(https·호스트·경로만, 사용자 정보·포트·IP·역슬래시·퍼센트 우회 거부).
- `validate_ai_policy` / `load_ai_policy` : AI 처리기(Gemini 등)는 출처가 아니라 처리기라 이 목록에 넣지 않고 pipeline/ai_processor_policy.json 의 11칸으로 따로 둔다.

ACTIVE 규칙(enabled: true 로 저장할 수 있는 조건 — 하나라도 어기면 그 Provider 는 ACTIVE 가 아니다)
  A0 class 는 data(콘텐츠 Provider)만.  A1 strict_tier ≤ 2 이고 7칸 계산도 ≤ 2, 구조화 접근 경로(api·csv·dataset)가 있다.
  A2 7칸 모두 state 가 UNKNOWN 이 아니고 basis 가 EXPLICIT·STANDARD_LICENSE·STATUTE 다(IMPLIED·NOT_ADDRESSED·NOT_READ 는 엄격 해석에서 UNKNOWN).
  A3 어느 칸도 DENIED 가 아니다(상업 이용·자동 접근이 DENIED 이면 특히 Tier 4).  A4 snapshot.expires_at 이 오늘보다 앞서지 않는다(오늘을 못 받으면 확인할 수 없어 거부).
  A5 출처 표시가 CONDITIONAL 이면 attribution_template 이 있다.  A6 경로 유형 규칙: rss·html·image 경로가 하나라도 있으면 strict_tier 가 1이어도 자동화 제외다.
  A7 Tier 4(상업 금지·자동 수집 금지·AI 입력 금지 등)는 완전 제외다.  A8 7칸마다 근거 이름·열람일이 있고 비어 있지 않은 약관 문서 이름이 하나 이상 있다.  A9 effective_status 가 '자동화 가능'이다.
  A10 접근 경로마다 경로 접두어(paths)가 비어 있지 않고 호스트 전체를 여는 `/` 한 개가 아니다(호스트 전체를 여는 항목은 켜지 못한다).
  A11 api 접근 경로마다 호출 한도(rate_limit)가 알려져 있다 — 제공처가 공개한 'N/second|minute|hour|day' 문구이거나, 공식 수치 한도가 없다고 확인한 객체(official NONE + 우리 자체 상한 own 14칸 + 한 줄 설명 note)다.
      없거나(null) 읽을 수 없으면 켤 수 없다 — 모르면 비워 두고 '확인 필요'.
모양 규칙: S1 필드·형식(최상위 알 수 없는 칸 포함)  S2 열거값(`ai_use` 포함)  S3 provider_id 중복  S4 호스트·경로 모양  S5 날짜 모양  S6 enabled·retention_days 형식  S7 effective_status 가 '자동화 가능'인데 7칸·경로 유형 계산은 아님  S8 근거 칸에 링크 금지
  S9 attribution_template 모양(자리 표시는 {title}·{date}·{url} 만, 한 줄·길이 상한·링크·금지 글자·로고·보증·제휴 암시 표현 없음, 자리 표시만으로는 안 됨)
  S10 rate_limit 객체 모양(알 수 없는 칸·빠진 칸·범위 밖 값 거절, 기본값 없음)  S11 own_data_only 는 true/false 이고, 제공처가 만든 값에만 맞는 '공공영역·연방정부 저작물' 문구는 own_data_only true 인 Provider 만 쓸 수 있다.

우리 쪽 약속 칸 `ai_use`(Provider 마다 하나, 없으면 BY_CELL): BY_CELL(기본) 은 7칸을 모두 판정한다. NEVER 는 '이 Provider 의 자료는 AI 처리기에 넘기지 않는다 — 규칙 기반 경로에서만 쓴다'는 약속이라
strict 판정(computed_strict_tier·A2·A3)이 `ai_input` 칸만 건너뛴다(나머지 6칸은 그대로 — 하나라도 UNKNOWN·IMPLIED·DENIED 면 막힌다). 대신 egress.check_ai_input 이 그 자료의 AI 입력을 항상 거부한다.
이 값은 아무것도 켜지 않는다(enabled 는 따로) — 운영자 결정 007(2026-11-09 20:33).
`own_data_only`(선택, 기본 false): true 는 '이 항목이 읽는 값은 모두 제공처 자신이 만든 것이다 — 제3자가 제공한 필드·파일은 읽지 않는다(어댑터의 필드 화이트리스트가 지킨다)'는 약속이다.
"""
import argparse
import datetime
import json
import re
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

DEFAULT_PATH = Path(__file__).resolve().parent / "source_registry.json"
AI_POLICY_PATH = Path(__file__).resolve().parent / "ai_processor_policy.json"
SCHEMA_VERSION = 1

STATES = ("ALLOWED", "CONDITIONAL", "DENIED", "UNKNOWN")
BASES = ("EXPLICIT", "STANDARD_LICENSE", "STATUTE", "IMPLIED", "NOT_ADDRESSED", "NOT_READ")
STRICT_BASES = frozenset({"EXPLICIT", "STANDARD_LICENSE", "STATUTE"})      # 엄격 해석에서 '그 칸을 직접 말한' 근거
OPEN_LICENSE_BASES = frozenset({"STANDARD_LICENSE", "STATUTE"})              # 표준 공개 라이선스·법령 근거 — Tier 1 의 조건
CELLS = ("commercial_use", "automated_access", "derivative_use", "storage", "ai_input", "attribution", "license")
CORE_DENY_CELLS = ("commercial_use", "automated_access", "derivative_use")   # 이 칸이 DENIED 이면 Tier 4(감사표 계산과 같다)
CLASSES = ("data", "internal", "ops", "image")
ACTIVE_CLASS = "data"
ACCESS_KINDS = ("api", "csv", "dataset", "rss", "html", "image")
STRUCTURED_KINDS = frozenset({"api", "csv", "dataset"})
STATUS_OK, STATUS_EXCLUDED, STATUS_REFERENCE, STATUS_BLOCKED = "자동화 가능", "자동화 제외", "참고 전용", "완전 제외"
STATUSES = (STATUS_OK, STATUS_EXCLUDED, STATUS_REFERENCE, STATUS_BLOCKED)
NON_AUTOMATED = frozenset({STATUS_EXCLUDED, STATUS_REFERENCE})
# 허용 목적(허용 목록 방식): 허용 목록(Registry)으로 판정하는 호출 목적은 이 이름들뿐이고, 그 밖의 이름(article·rss·web·crawl·fetch·read·news·summary 등 모르는 목적)은 모두 거부한다.
# 구조화 Fact 호출은 `fact`. 목적을 더하려면 이 값과 docs/SOURCE_POLICY.md 6절을 함께 바꾼다(T2).
ALLOWED_PURPOSES = frozenset({"fact"})
# 일반 웹 읽기 목적: 외부 RSS·기사 페이지 본문·웹 중계 해석은 유형만으로 Tier 3 이라 허용 목록에 무엇이 있든 자동으로 읽지 않는다 — 허용 목적이 아니라서 어차피 거부되지만 사유 문구를 구체적으로 하려고 이름을 따로 둔다.
GENERAL_WEB_PURPOSES = frozenset({"feed", "page", "resolve"})
AI_USE_VALUES = ("BY_CELL", "NEVER")                                              # Provider 의 `ai_use`: BY_CELL = 7칸 모두 판정(기본, 지금 동작) · NEVER = 이 자료는 AI 에 넘기지 않음(strict 판정이 ai_input 칸을 건너뜀)
DEFAULT_AI_USE = "BY_CELL"
RATE_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}              # rate_limit 문구의 단위 → 초
ATTRIBUTION_MAX = 300                                                             # attribution_template 길이 상한(자리 표시 포함)
ATTRIBUTION_MIN_PLAIN = 8                                                         # 자리 표시를 뺀 일반 문구의 최소 글자 수
ATTRIBUTION_PLACEHOLDERS = ("{title}", "{date}", "{url}")
# 출처 문구에 쓰면 안 되는 표현(공백을 뺀 글자로 비교, 영문은 소문자): 로고·휘장 같은 상표 표시와 보증·제휴·공식 승인을 암시하는 알려진 말. 부정 문장('인정하거나 보증한 내용이 아닙니다')은 걸리지 않게 '가·이 + 동사' 꼴만 적었다 —
# 목록은 알려진 표현만이라 사람 검토가 마지막이다(docs/SOURCE_POLICY.md 5절).
ATTRIBUTION_LOGO_WORDS = ("로고", "logo", "휘장", "emblem", "시각식별자", "상표")
ATTRIBUTION_ENDORSE_WORDS = ("가인정한", "이인정한", "가보증한", "이보증한", "가승인한", "이승인한", "가후원", "이후원", "가추천한", "이추천한", "공식분석", "공식인증", "공식승인", "공식제휴", "공식파트너", "공식후원",
                             "officiallyendorsed", "endorsedby", "inpartnershipwith", "sponsoredby", "approvedby", "certifiedby")
# 제공처 자료를 우리 것이라 주장하는 표현(저작권 표시·무단 전재 금지 등)과 상표 기호 — 공공영역 자료의 출처 문구에 있으면 안 된다(NWS 면책 문서의 금지: 자기 것이라 주장·보증 암시).
ATTRIBUTION_OWNERSHIP_WORDS = ("\u00a9", "\u24d2", "\u2122", "\u00ae", "allrightsreserved", "모든권리", "무단전재", "무단복제", "저작권은이블로그", "저작권은당사")
# 제공처가 만든 값에만 맞는 법적 주장(공공영역·연방정부 저작물) — own_data_only true 인 Provider 의 템플릿에서만 쓴다(S11).
ATTRIBUTION_PUBLIC_DOMAIN_WORDS = ("연방정부저작물", "저작권보호대상이아닙", "저작권보호를받지", "공공영역", "퍼블릭도메인", "publicdomain", "17u.s.c", "17usc", "federalwork", "worksofthegovernment")
# 호출 한도 객체(rate_limit)의 우리 자체 상한(own) 14칸: (이름, 종류, 최솟값, 최댓값). 빠진 칸을 기본값으로 채우지 않는다(S10). 종류 true 는 반드시 true 여야 하는 안전 칸이다.
OWN_LIMIT_SPEC = (
    ("min_gap_same_file_s", "int", 1, 86400),
    ("min_gap_other_file_s", "int", 0, 3600),
    ("max_products_per_post", "int", 1, 20),
    ("max_calls_per_product_per_post", "int", 1, 5),
    ("max_calls_per_day", "int", 1, 1000),
    ("max_calls_per_month", "int", 1, 100000),
    ("max_retries", "int", 0, 3),
    ("retry_after_s", "int", 1, 86400),
    ("stop_hours_on_403_429", "int", 1, 720),
    ("stop_product_on_404", "true", None, None),
    ("request_gzip", "bool", None, None),
    ("daily_product_not_before_utc", "hhmm", None, None),
    ("daily_product_max_per_day", "int", 1, 24),
    ("fail_closed_on_bad_response", "true", None, None),
)
OWN_LIMIT_KEYS = tuple(spec[0] for spec in OWN_LIMIT_SPEC)
RATE_LIMIT_KEYS = ("official", "own", "note")
RATE_OFFICIAL_NONE = "NONE"                                                       # 제공처가 공식 수치 한도가 없다고 밝힌(우리가 확인한) 값 — 이때 own 이 반드시 있어야 한다
RATE_NOTE_MAX = 300
_HHMM_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
ALLOWED_TOP_KEYS = frozenset({"_doc", "schema_version", "providers"})           # 허용 목록 파일 최상위에 허용하는 칸(오타로 칸 이름이 틀려도 조용히 무시되지 않게)
AI_TOP_KEYS = frozenset({"_doc", "schema_version", "processor", "notes"})       # AI 처리기 정책 파일 최상위에서 11칸 말고 허용하는 칸(AI_FIELDS 는 아래)

_ID_RE = re.compile(r"[a-z][a-z0-9_]{1,63}")
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOST_RE = re.compile(r"(?:" + _LABEL + r"\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?")    # 마지막 칸이 글자로 시작 — 숫자뿐인 IP 꼴(127.0.0.1·2130706433)은 호스트가 아니다
_PATH_RE = re.compile(r"/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*")
_PURPOSE_RE = re.compile(r"[a-z][a-z0-9_]{0,31}")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ATTRIBUTION_BAD_RE = re.compile(r"[\x00-\x1f\x7f<>`\[\]\\|\x7e\uff5e\u301c\u27e6\u27e7]")      # 제어 글자(줄바꿈 포함)·꺾쇠·역따옴표·대괄호·역슬래시·세로줄·물결표 셋·표시 괄호 — 조립기가 글에 그대로 싣는 한 줄이라 마크업이 될 글자는 안 된다
_RATE_RE = re.compile(r"(\d{1,9})\s*(?:/|per|requests?\s+per|calls?\s+per)\s*(second|minute|hour|day)", re.I)
_URL_BAD_RE = re.compile(r"[\x00-\x20\x7f\\<>\"'`^{}|]|[^\x00-\x7f]")             # 주소의 앞부분(스킴·호스트·경로)에서 거부: 공백·제어·역슬래시·꺾쇠·따옴표·비 ASCII — 파서마다 다르게 읽는 주소
_TAIL_BAD_RE = re.compile(r"[\x00-\x20\x7f\\]|[^\x00-\x7f]")                       # 질의·조각에서 거부: 공백·제어·역슬래시·비 ASCII 만(꺾쇠·중괄호·세로선처럼 호스트·경로를 바꾸지 못하는 글자는 실제 API 주소에 쓰인다)
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_URL_MAX = 2048
UNKNOWN_HOST = "(알 수 없음)"


class SourceRegistryError(ValueError):
    """허용 목록·AI 처리기 정책 파일을 읽을 수 없거나 전체가 쓸 수 없는 모양일 때(Provider 하나의 문제는 이 예외가 아니라 ACTIVE 제외와 사유다)."""


# ----------------------------------------------------------------------------
# 값 객체(읽기 전용)
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Cell:
    """이용 조건 한 칸: 판정(state)·근거 유형(basis)·근거 문서 이름(evidence, 링크 없음)·열람일(read_at, 없으면 None)."""
    state: str
    basis: str
    evidence: str
    read_at: Optional[str]

    @property
    def known(self):
        """엄격 해석에서 '알려진' 칸인가: UNKNOWN 이 아니고 그 칸을 직접 말한 근거(EXPLICIT·STANDARD_LICENSE·STATUTE)가 있다."""
        return self.state != "UNKNOWN" and self.basis in STRICT_BASES


@dataclass(frozen=True)
class Policy:
    """7칸 묶음. `policy.ai_input` 과 `policy["ai_input"]` 이 같은 칸을 돌려준다."""
    commercial_use: Cell
    automated_access: Cell
    derivative_use: Cell
    storage: Cell
    ai_input: Cell
    attribution: Cell
    license: Cell

    def __getitem__(self, name):
        if name not in CELLS:
            raise KeyError(name)
        return getattr(self, name)

    def items(self):
        return tuple((name, getattr(self, name)) for name in CELLS)


@dataclass(frozen=True)
class OwnLimit:
    """우리 자체 호출 상한 14칸(OWN_LIMIT_SPEC 과 같은 이름). 제공처가 공식 수치 한도를 두지 않을 때 우리가 스스로 정한 값이다(제안 — 공식 값이 아니다)."""
    min_gap_same_file_s: int
    min_gap_other_file_s: int
    max_products_per_post: int
    max_calls_per_product_per_post: int
    max_calls_per_day: int
    max_calls_per_month: int
    max_retries: int
    retry_after_s: int
    stop_hours_on_403_429: int
    stop_product_on_404: bool
    request_gzip: bool
    daily_product_not_before_utc: str
    daily_product_max_per_day: int
    fail_closed_on_bad_response: bool


@dataclass(frozen=True)
class RateLimit:
    """구조화 호출 한도: official(제공처가 공개한 'N/…' 문구 또는 NONE=공식 수치 한도 없음)·own(우리 자체 상한 — official 이 NONE 이면 반드시 있다)·note(사람이 읽는 한 줄)."""
    official: str
    own: Optional[OwnLimit]
    note: str


@dataclass(frozen=True)
class Access:
    """접근 경로: 종류·호스트(정확 일치)·경로 접두어(비면 호스트 전체)·인증·호출 한도(문구 'N/minute' 꼴, 구조화 RateLimit, 또는 None=모름)·robots 점검일."""
    kind: str
    hosts: Tuple[str, ...]
    paths: Tuple[str, ...]
    auth: str
    rate_limit: object
    robots_checked_at: Optional[str]


@dataclass(frozen=True)
class Snapshot:
    """약관 판독 기록: 읽은 문서 이름·열람일·내용 해시(빈 값 허용)·점검 기한."""
    terms_pages: Tuple[str, ...]
    read_at: Optional[str]
    content_hash: str
    expires_at: Optional[str]


@dataclass(frozen=True)
class Provider:
    """허용 목록의 한 항목(이용 조건이 같은 묶음). FACT 와의 약속 필드: provider_id·strict_tier·effective_status·access·attribution_template·snapshot·policy·retention_days."""
    provider_id: str
    name: str
    provider_class: str
    policy: Policy
    strict_tier: int
    permissive_interpretation: Optional[int]       # 참고용 — 실행에 쓰지 않는다
    effective_status: str
    access: Tuple[Access, ...]
    snapshot: Snapshot
    attribution_template: str
    exceptions: Tuple[str, ...]
    retention_days: Optional[int]
    enabled: bool
    reference_hosts: Tuple[str, ...]               # 글이 인용만 하는 호스트(자동 접근 경로 아님) — 거부 사유를 설명하는 데만 쓴다
    ai_use: str = DEFAULT_AI_USE                   # 우리 쪽 약속: BY_CELL(기본) = 7칸 모두 판정 · NEVER = 이 자료는 AI 에 넘기지 않음(strict 판정이 ai_input 칸을 건너뛰고 egress.check_ai_input 이 항상 거부)
    own_data_only: bool = False                    # 우리 쪽 약속: true = 이 항목이 읽는 값은 모두 제공처 자신이 만든 것(제3자 필드·파일은 읽지 않음) — 공공영역·연방정부 저작물 출처 문구의 조건


# ----------------------------------------------------------------------------
# 순수 규칙
# ----------------------------------------------------------------------------
def _tag(code, text):
    return f"[{code}] {text}"


def _is_date(value):
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def to_date(value):
    """날짜 인자(date 또는 ISO 문자열)를 date 로. None 은 None. 그 밖은 SourceRegistryError."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if _is_date(value):
        return datetime.date.fromisoformat(value)
    raise SourceRegistryError(f"today 는 날짜(date 또는 YYYY-MM-DD)여야 합니다: {type(value).__name__}")


def valid_host(host):
    return isinstance(host, str) and bool(_HOST_RE.fullmatch(host)) and len(host) <= 253


def valid_path_prefix(path):
    if not isinstance(path, str) or not _PATH_RE.fullmatch(path) or "//" in path or "%" in path:
        return False
    return all(seg not in (".", "..") for seg in path.split("/"))


def path_matches(path, prefixes):
    """경로가 접두어 중 하나에 경계를 지켜 맞는가(접두어가 없으면 True). `/api/` 는 `/api/x` 와 `/api` 에, `/feed` 는 `/feed`·`/feed/x` 에 맞고 `/feedback` 에는 맞지 않는다."""
    if not prefixes:
        return True
    for prefix in prefixes:
        if prefix.endswith("/"):
            if path.startswith(prefix) or path == prefix.rstrip("/"):
                return True
        elif path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def split_https_url(url):
    """주소를 (호스트, 경로, 거부 사유)로 엄격하게 나눈다. 사유가 None 이 아니면 경로를 쓰지 않는다(호스트는 거부 문구에 '어느 호스트로 가려던 주소인지'만 알리려고 알 수 있을 때 돌려줄 뿐
    허용 근거가 아니다). 사유 문장에는 주소의 어떤 부분도 넣지 않는다.

    거부: 문자열이 아님·빈 값·2048자 초과·공백/제어/역슬래시/비 ASCII 글자(질의 앞에서는 꺾쇠·따옴표·중괄호·세로선도)·https 가 아닌 스킴·사용자 정보(@)·443 이 아닌(또는 빈) 포트·IP 주소·
    호스트 모양 오류(끝 점 포함)·`.`/`..` 경로 조각(퍼센트 인코딩 포함, `..;x` 처럼 세미콜론 매개변수가 붙은 것도 — 서버가 `;` 뒤를 떼고 읽는다)·`//`·인코딩된 슬래시·널·이중 인코딩(`%25`)·깨진 퍼센트.
    질의·조각은 판정에 쓰지 않는다(쓰지도, 돌려주지도 않는다)."""
    if not isinstance(url, str) or not url:
        return None, None, "주소가 비어 있거나 문자열이 아님"
    if len(url) > _URL_MAX:
        return None, None, "주소가 너무 김"
    cut = re.search(r"[?#]", url)
    head, tail = (url[:cut.start()], url[cut.start():]) if cut else (url, "")
    if _URL_BAD_RE.search(head) or _TAIL_BAD_RE.search(tail):
        return None, None, "주소에 허용되지 않는 글자(공백·제어·역슬래시·비 ASCII, 질의 앞에서는 꺾쇠·따옴표·중괄호 등도)가 있음"
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return None, None, "주소를 해석할 수 없음"
    seen = parts.hostname if valid_host(parts.hostname or "") else None       # 거부 문구에 '어느 호스트로 가려던 주소인지'만 알려 주려고(연결될 호스트 — 사용자 정보가 있으면 @ 뒤)
    if parts.scheme != "https":
        return seen, None, "https 주소만 허용"
    if "@" in parts.netloc:
        return seen, None, "사용자 정보(@)가 든 주소는 허용하지 않음"
    try:
        port = parts.port
    except ValueError:
        return seen, None, "포트 모양 오류"
    if parts.netloc.endswith(":"):                        # `host:` 처럼 포트 자리가 비어 있는 꼴은 파서마다 기본 포트로 읽거나 거부해 모호하다
        return seen, None, "포트 모양 오류"
    if port not in (None, 443):
        return seen, None, "443 이 아닌 포트는 허용하지 않음"
    host = parts.hostname or ""
    if not valid_host(host):
        return None, None, "호스트 모양이 올바르지 않음(IP 주소·끝 점·잘못된 글자)"
    path = parts.path or "/"
    if not path.startswith("/") or "//" in path or _BAD_PERCENT_RE.search(path):
        return host, None, "경로 모양이 올바르지 않음"
    try:
        decoded = urllib.parse.unquote_to_bytes(path).decode("utf-8")          # 퍼센트 인코딩이 올바른 UTF-8 이 아니면(과잉 길이 인코딩 `%C0%AE` 같은 `..` 우회 포함) 거부한다
    except UnicodeDecodeError:
        return host, None, "경로의 퍼센트 인코딩이 올바른 UTF-8 이 아님"
    if "\\" in decoded or "\x00" in decoded or re.search(r"%2f|%5c|%25", path, re.I) or any(seg.split(";", 1)[0] in (".", "..") for seg in decoded.split("/")):
        return host, None, "경로에 우회 형태(.·..·;가 붙은 ..·인코딩된 슬래시·역슬래시·널·이중 인코딩)가 있음"
    return host, path, None


def computed_strict_tier(cells, provider_class="data", ai_use=DEFAULT_AI_USE):
    """7칸에서 계산한 엄격 Tier(0–4). `cells` 는 칸 이름 → {state, basis} 매핑. 실행 기준은 이 값과 저장된 strict_tier 중 느슨한 쪽이 아니라 **둘 다**다(ACTIVE 는 둘 다 ≤ 2).
    4: 상업 이용·자동 접근·가공이 DENIED, 또는 AI 입력이 DENIED(운영자 Tier 4 정의의 'AI 입력 금지'). 3: 그 밖의 DENIED 또는 UNKNOWN·근거 없음(IMPLIED·NOT_ADDRESSED·NOT_READ)이 있음.
    1: 모두 알려졌고 표준 공개 라이선스·법령 근거가 있음. 2: 모두 알려졌고 공식 API 약관 근거만 있음. class internal 은 0.
    `ai_use` 가 "NEVER" 이면(이 자료는 AI 에 넘기지 않는다는 우리 쪽 약속) `ai_input` 칸만 판정에서 뺀다 — 그 칸이 DENIED·UNKNOWN·IMPLIED 여도 Tier 에 영향이 없고 나머지 6칸은 그대로다.
    그 밖의 값(기본 BY_CELL 포함)은 7칸 모두 본다 — 기본값에서는 이 함수의 결과가 `ai_use` 가 생기기 전과 같다."""
    if provider_class == "internal":
        return 0
    get = lambda name: (cells[name]["state"], cells[name]["basis"])   # noqa: E731
    judged = tuple(name for name in CELLS if not (ai_use == "NEVER" and name == "ai_input"))
    if any(get(name)[0] == "DENIED" for name in CORE_DENY_CELLS) or ("ai_input" in judged and get("ai_input")[0] == "DENIED"):
        return 4
    if any(get(name)[0] == "DENIED" for name in judged):
        return 3
    if any(get(name)[0] == "UNKNOWN" or get(name)[1] not in STRICT_BASES for name in judged):
        return 3
    return 1 if any(get(name)[1] in OPEN_LICENSE_BASES for name in ("license", "commercial_use", "derivative_use", "storage")) else 2


def computed_status(provider_class, tier, kinds):
    """7칸 계산 Tier 와 경로 종류로 계산한 effective_status. 저장된 값이 '자동화 가능' 이면 이 계산도 '자동화 가능' 이어야 한다(S7), 켜려면(A9) 저장된 값이 '자동화 가능' 이어야 한다. 그 밖의 라벨은 어느 쪽으로 적어도 켜지 못하므로 더 엄격하게 적는 것은 허용한다.
    완전 제외: Tier 4. 자동화 제외: 외부 사진(image) 분류, 또는 Tier ≤ 2 인데 경로가 전부 구조화가 아님(경로 유형 규칙), 또는 Tier 3 인데 경로가 있음.
    자동화 가능: Tier ≤ 2 이고 모든 경로가 구조화(api·csv·dataset). 참고 전용: Tier 3 인데 자동 접근 경로가 없음(글이 인용만 하는 출처)."""
    if tier == 4:
        return STATUS_BLOCKED
    if provider_class != ACTIVE_CLASS:
        return STATUS_EXCLUDED
    kinds = tuple(kinds)
    if tier <= 2:
        return STATUS_OK if kinds and all(kind in STRUCTURED_KINDS for kind in kinds) else STATUS_EXCLUDED
    return STATUS_EXCLUDED if kinds else STATUS_REFERENCE


def parse_rate_limit(text):
    """제공처가 공개한 호출 한도 글자를 ((횟수, 단위), …) 로. 단위는 second·minute·hour·day. `100/day`·`100 per day`·`60 requests per minute` 꼴이고 쉼표·세미콜론으로 여러 개를 이을 수 있다.
    없거나(None) 글자가 아니거나 읽을 수 없거나(`UNKNOWN`·`확인 필요`) 횟수가 1 미만이면 None — 한도를 모르는 것이고 ACTIVE api 경로에서는 켤 수 없다(A11)."""
    if not isinstance(text, str):
        return None
    parts = [part.strip() for part in re.split(r"[;,]", text) if part.strip()]
    if not parts:
        return None
    out = []
    for part in parts:
        match = _RATE_RE.fullmatch(part)
        if not match or int(match.group(1)) < 1:
            return None
        out.append((int(match.group(1)), match.group(2).lower()))
    return tuple(out)


def _rate_limit_object_problems(value):
    """rate_limit 이 객체일 때의 모양 문제 목록(S10, 순수): 알 수 없는 칸 거절, official 은 'N/…' 문구 또는 NONE, NONE 이면 own 필수, own 은 14칸을 모두(기본값 없음) 적고 값이 범위 안이어야 하며
    note 는 사람이 읽는 한 줄이다(NONE 이면 '공식 수치 한도 없음'·'자체 상한'·'제안'을 밝힌다). 칸 사이 관계: 월 상한 ≥ 하루 상한 ≥ 글 하나가 재시도까지 쓰는 호출 수."""
    out = []
    for extra in sorted(str(key)[:30] for key in set(value) - set(RATE_LIMIT_KEYS)):
        out.append(_tag("S10", f"rate_limit 에 알 수 없는 칸이 있습니다: {extra!r}"))
    official = value.get("official")
    numeric = parse_rate_limit(official) if _str(official) else None
    if not _str(official) or not (official == RATE_OFFICIAL_NONE or numeric):
        out.append(_tag("S10", f"rate_limit.official 은 제공처가 공개한 'N/second|minute|hour|day' 문구이거나 {RATE_OFFICIAL_NONE}(공식 수치 한도 없음을 확인함)이어야 합니다"))
    own = value.get("own")
    if own is None:
        if official == RATE_OFFICIAL_NONE:
            out.append(_tag("S10", "공식 수치 한도가 없다고 했으면(official NONE) 우리 자체 상한(own)이 반드시 있어야 합니다 — 한도 없이 켤 수 없습니다"))
    elif not isinstance(own, dict):
        out.append(_tag("S10", "rate_limit.own 은 객체여야 합니다"))
    else:
        for extra in sorted(str(key)[:30] for key in set(own) - set(OWN_LIMIT_KEYS)):
            out.append(_tag("S10", f"rate_limit.own 에 알 수 없는 칸이 있습니다: {extra!r}"))
        for name, kind, low, high in OWN_LIMIT_SPEC:
            if name not in own:
                out.append(_tag("S10", f"rate_limit.own.{name} 칸이 없습니다 — 빠진 칸을 기본값으로 채우지 않습니다"))
                continue
            got = own[name]
            if kind == "int" and (isinstance(got, bool) or not isinstance(got, int) or not low <= got <= high):
                out.append(_tag("S10", f"rate_limit.own.{name} 는 {low}–{high} 정수여야 합니다"))
            elif kind == "bool" and not isinstance(got, bool):
                out.append(_tag("S10", f"rate_limit.own.{name} 는 true/false 여야 합니다"))
            elif kind == "true" and got is not True:
                out.append(_tag("S10", f"rate_limit.own.{name} 는 true 여야 합니다(안전 칸 — 끌 수 없습니다)"))
            elif kind == "hhmm" and not (_str(got) and _HHMM_RE.fullmatch(got)):
                out.append(_tag("S10", f"rate_limit.own.{name} 는 'HH:MM'(UTC) 이어야 합니다"))
        ints = {name: own.get(name) for name, kind, _, _ in OWN_LIMIT_SPEC if kind == "int" and isinstance(own.get(name), int) and not isinstance(own.get(name), bool)}
        if {"max_calls_per_day", "max_calls_per_month"} <= set(ints) and ints["max_calls_per_month"] < ints["max_calls_per_day"]:
            out.append(_tag("S10", "rate_limit.own.max_calls_per_month 는 max_calls_per_day 보다 작을 수 없습니다"))
        needed = {"max_products_per_post", "max_calls_per_product_per_post", "max_retries", "max_calls_per_day"}
        if needed <= set(ints) and ints["max_products_per_post"] * ints["max_calls_per_product_per_post"] * (1 + ints["max_retries"]) > ints["max_calls_per_day"]:
            out.append(_tag("S10", "rate_limit.own.max_calls_per_day 가 글 하나의 호출(제품 수 × 제품당 호출 × (1 + 재시도))보다 작아 한 편도 끝낼 수 없습니다"))
    note = value.get("note")
    if not _str(note) or not note.strip():
        out.append(_tag("S10", "rate_limit.note 는 사람이 읽는 한 줄이어야 합니다"))
    else:
        if len(note) > RATE_NOTE_MAX or "\n" in note or "\r" in note or "://" in note:
            out.append(_tag("S10", f"rate_limit.note 는 링크 없는 한 줄({RATE_NOTE_MAX}자 이하)이어야 합니다"))
        if official == RATE_OFFICIAL_NONE and not all(word in note for word in ("공식 수치 한도 없음", "자체 상한", "제안")):
            out.append(_tag("S10", "official 이 NONE 이면 note 에 '공식 수치 한도 없음'·'자체 상한'·'제안'을 밝혀야 합니다(공식 값이 아니라 우리가 정한 제안 값임을 숨기지 않는다)"))
    return out


def rate_limit_known(value):
    """호출 한도가 알려져 있는가(A11): 제공처가 공개한 'N/…' 문구이거나, 모양이 올바른 구조화 객체(공식 수치 한도 없음을 확인하고 우리 자체 상한을 적은 것 포함). None·읽을 수 없는 값은 모르는 것이다."""
    if isinstance(value, dict):
        return not _rate_limit_object_problems(value)
    return parse_rate_limit(value) is not None


def _build_rate_limit(value):
    """JSON 값 → 문구(그대로)·None·RateLimit(구조화, 모양이 올바르다고 이미 확인된 것)."""
    if not isinstance(value, dict):
        return value
    own = value.get("own")
    return RateLimit(value["official"], OwnLimit(**own) if own else None, value["note"])


def _attribution_problems(text):
    """attribution_template(조립기가 글 끝 출처 줄에 그대로 붙이는 사람이 쓴 일반 문구 — AI 를 거치지 않는다)의 모양 문제 목록(S9): 한 줄·길이 상한·링크 없음·마크업 글자 없음·
    자리 표시는 {title}·{date}·{url} 뿐·자리 표시만으로 이뤄지지 않음."""
    out = []
    one = text.strip()
    if len(one) > ATTRIBUTION_MAX:
        out.append(_tag("S9", f"attribution_template 이 너무 깁니다({len(one)}자 — 상한 {ATTRIBUTION_MAX}자)"))
    if _ATTRIBUTION_BAD_RE.search(one):
        out.append(_tag("S9", "attribution_template 에 쓸 수 없는 글자가 있습니다 — 한 줄 일반 문구여야 합니다(줄바꿈·제어 글자·꺾쇠·역따옴표·대괄호·역슬래시·세로줄·물결표·표시 괄호 금지)"))
    if "://" in one or re.search(r"www\.", one, re.I):
        out.append(_tag("S9", "attribution_template 에 링크가 있습니다 — 링크 아닌 일반 문구만 적습니다(주소는 {url} 자리가 대신합니다)"))
    squeezed = re.sub(r"\s+", "", one).lower()
    for word in ATTRIBUTION_LOGO_WORDS:
        if word in squeezed:
            out.append(_tag("S9", "attribution_template 에 로고·상표 표시 표현이 있습니다 — 기관 이름은 사실 표기로만 쓰고 로고·이미지·시각 식별자를 암시하지 않습니다"))
            break
    for word in ATTRIBUTION_ENDORSE_WORDS:
        if word in squeezed:
            out.append(_tag("S9", "attribution_template 에 제공처의 보증·승인·제휴·후원을 암시하는 표현이 있습니다 — 우리 계산을 공식 자료처럼 보이게 하지 않습니다"))
            break
    for word in ATTRIBUTION_OWNERSHIP_WORDS:
        if word in squeezed:
            out.append(_tag("S9", "attribution_template 에 우리 것이라는 권리 주장이나 상표 기호가 있습니다(저작권 표시·무단 전재 금지 등) — 제공처 자료를 우리 것이라 주장하지 않습니다"))
            break
    plain = one
    for placeholder in ATTRIBUTION_PLACEHOLDERS:
        plain = plain.replace(placeholder, "")
    if "{" in plain or "}" in plain:
        out.append(_tag("S9", f"attribution_template 의 자리 표시는 {'·'.join(ATTRIBUTION_PLACEHOLDERS)} 뿐입니다(그 밖의 중괄호 금지)"))
    elif len(plain.strip()) < ATTRIBUTION_MIN_PLAIN:
        out.append(_tag("S9", f"attribution_template 은 자리 표시만으로 이뤄질 수 없습니다 — 자리 표시를 뺀 일반 문구가 {ATTRIBUTION_MIN_PLAIN}자 이상 있어야 합니다"))
    return out


def attribution_claims_public_domain(text):
    """출처 문구가 '공공영역·연방정부 저작물이라 저작권 보호 대상이 아니다' 같은 법적 주장을 담았는가(공백을 뺀 글자 비교)."""
    squeezed = re.sub(r"\s+", "", text).lower() if isinstance(text, str) else ""
    return any(word in squeezed for word in ATTRIBUTION_PUBLIC_DOMAIN_WORDS)


def _str(value):
    return isinstance(value, str)


def _is_schema_version(value):
    """정수 SCHEMA_VERSION 만. `True`(== 1)·`1.0`(== 1)이 같은 값으로 통과하지 않게 형식을 먼저 본다."""
    return isinstance(value, int) and not isinstance(value, bool) and value == SCHEMA_VERSION


def _shape_problems(raw):
    """모양 규칙 S1·S2·S4·S5·S6·S8(모든 Provider). 모양이 틀리면 Provider 를 만들 수 없다."""
    if not isinstance(raw, dict):
        return [_tag("S1", "Provider 항목은 객체여야 합니다")]
    out = []

    def need(key, check, what):
        if key not in raw or not check(raw[key]):
            out.append(_tag("S1", f"{key} 가 없거나 {what} 이(가) 아닙니다"))
            return False
        return True

    need("provider_id", lambda v: _str(v) and bool(_ID_RE.fullmatch(v)), "영소문자로 시작하는 [a-z0-9_] 2–64자")
    need("name", lambda v: _str(v) and bool(v.strip()), "비어 있지 않은 문자열")
    if need("class", _str, "문자열") and raw["class"] not in CLASSES:
        out.append(_tag("S2", f"class 는 {'·'.join(CLASSES)} 중 하나여야 합니다: {str(raw['class'])[:30]!r}"))
    if need("strict_tier", lambda v: isinstance(v, int) and not isinstance(v, bool), "정수") and not 0 <= raw["strict_tier"] <= 4:
        out.append(_tag("S2", "strict_tier 는 0–4 여야 합니다"))
    pi = raw.get("permissive_interpretation")
    if pi is not None and (isinstance(pi, bool) or not isinstance(pi, int) or not 0 <= pi <= 4):
        out.append(_tag("S2", "permissive_interpretation 은 0–4 정수 또는 null 이어야 합니다"))
    if need("effective_status", _str, "문자열") and raw["effective_status"] not in STATUSES:
        out.append(_tag("S2", f"effective_status 는 {'·'.join(STATUSES)} 중 하나여야 합니다: {str(raw['effective_status'])[:30]!r}"))
    if not isinstance(raw.get("enabled"), bool):
        out.append(_tag("S6", "enabled 는 true/false 여야 합니다(없으면 안 됩니다 — 켜는 것은 명시적이어야 합니다)"))
    retention = raw.get("retention_days")
    if retention is not None and (isinstance(retention, bool) or not isinstance(retention, int) or retention < 0):
        out.append(_tag("S6", "retention_days 는 0 이상 정수 또는 null 이어야 합니다"))
    if "own_data_only" in raw and not isinstance(raw["own_data_only"], bool):
        out.append(_tag("S11", "own_data_only 는 true/false 여야 합니다(없으면 false)"))
    if _str(raw.get("attribution_template")) and attribution_claims_public_domain(raw["attribution_template"]) and raw.get("own_data_only") is not True:
        out.append(_tag("S11", "attribution_template 이 '공공영역·연방정부 저작물' 같은 법적 주장을 담고 있는데 own_data_only 가 true 가 아닙니다 — 제3자 자료를 읽을 수 있는 항목은 이 문구를 쓸 수 없습니다"))
    if "ai_use" in raw and not (_str(raw["ai_use"]) and raw["ai_use"] in AI_USE_VALUES):
        out.append(_tag("S2", f"ai_use 는 {'·'.join(AI_USE_VALUES)} 중 하나여야 합니다(없으면 {DEFAULT_AI_USE}): {str(raw['ai_use'])[:30]!r}"))
    if "attribution_template" in raw and not _str(raw["attribution_template"]):
        out.append(_tag("S1", "attribution_template 은 문자열이어야 합니다"))
    elif _str(raw.get("attribution_template")) and raw["attribution_template"].strip():
        out.extend(_attribution_problems(raw["attribution_template"]))
    for key in ("exceptions", "reference_hosts"):
        if key in raw and not (isinstance(raw[key], list) and all(_str(v) for v in raw[key])):
            out.append(_tag("S1", f"{key} 는 문자열 배열이어야 합니다"))
    for host in raw.get("reference_hosts", []) if isinstance(raw.get("reference_hosts", []), list) else []:
        if not valid_host(host):
            out.append(_tag("S4", f"reference_hosts 의 호스트 모양이 올바르지 않습니다: {str(host)[:60]!r}"))

    policy = raw.get("policy")
    if not isinstance(policy, dict):
        out.append(_tag("S1", "policy 는 7칸 객체여야 합니다"))
    else:
        for name in CELLS:
            cell = policy.get(name)
            if not isinstance(cell, dict):
                out.append(_tag("S1", f"policy.{name} 칸이 없습니다"))
                continue
            if cell.get("state") not in STATES:
                out.append(_tag("S2", f"policy.{name}.state 는 {'·'.join(STATES)} 중 하나여야 합니다"))
            if cell.get("basis") not in BASES:
                out.append(_tag("S2", f"policy.{name}.basis 는 {'·'.join(BASES)} 중 하나여야 합니다"))
            if not _str(cell.get("evidence", "")):
                out.append(_tag("S1", f"policy.{name}.evidence 는 문자열이어야 합니다"))
            elif "://" in cell.get("evidence", ""):
                out.append(_tag("S8", f"policy.{name}.evidence 에 링크가 있습니다 — 기관·문서 이름만 적습니다"))
            read_at = cell.get("read_at")
            if read_at is not None and not _is_date(read_at):
                out.append(_tag("S5", f"policy.{name}.read_at 는 YYYY-MM-DD 또는 null 이어야 합니다"))
        for extra in sorted(set(policy) - set(CELLS)):
            out.append(_tag("S1", f"policy 에 알 수 없는 칸이 있습니다: {str(extra)[:30]!r}"))

    access = raw.get("access")
    if not isinstance(access, list):
        out.append(_tag("S1", "access 는 배열이어야 합니다(자동 접근 경로가 없으면 빈 배열)"))
    else:
        for index, entry in enumerate(access):
            if not isinstance(entry, dict):
                out.append(_tag("S1", f"access[{index}] 는 객체여야 합니다"))
                continue
            if entry.get("kind") not in ACCESS_KINDS:
                out.append(_tag("S2", f"access[{index}].kind 는 {'·'.join(ACCESS_KINDS)} 중 하나여야 합니다"))
            hosts = entry.get("hosts")
            if not (isinstance(hosts, list) and hosts and all(valid_host(h) for h in hosts)):
                out.append(_tag("S4", f"access[{index}].hosts 는 소문자 호스트 이름(스킴·경로·포트·와일드카드 없음)의 비어 있지 않은 배열이어야 합니다"))
            paths = entry.get("paths", [])
            if not (isinstance(paths, list) and all(valid_path_prefix(p) for p in paths)):
                out.append(_tag("S4", f"access[{index}].paths 는 '/'로 시작하는 경로 접두어 배열이어야 합니다(.. · // · % 없음)"))
            if entry.get("auth") is not None and not _str(entry.get("auth")):
                out.append(_tag("S1", f"access[{index}].auth 는 문자열 또는 null 이어야 합니다"))
            limit = entry.get("rate_limit")
            if isinstance(limit, dict):
                out.extend(f"access[{index}]: {problem}" for problem in _rate_limit_object_problems(limit))
            elif limit is not None and not _str(limit):
                out.append(_tag("S1", f"access[{index}].rate_limit 는 문자열·객체 또는 null 이어야 합니다"))
            checked = entry.get("robots_checked_at")
            if checked is not None and not _is_date(checked):
                out.append(_tag("S5", f"access[{index}].robots_checked_at 는 YYYY-MM-DD 또는 null 이어야 합니다"))

    snapshot = raw.get("snapshot")
    if not isinstance(snapshot, dict):
        out.append(_tag("S1", "snapshot 은 객체여야 합니다"))
    else:
        pages = snapshot.get("terms_pages", [])
        if not (isinstance(pages, list) and all(_str(p) for p in pages)):
            out.append(_tag("S1", "snapshot.terms_pages 는 문서 이름 문자열의 배열이어야 합니다"))
        elif any("://" in p for p in pages):
            out.append(_tag("S8", "snapshot.terms_pages 에 링크가 있습니다 — 문서 이름만 적습니다"))
        for key in ("read_at", "expires_at"):
            if snapshot.get(key) is not None and not _is_date(snapshot.get(key)):
                out.append(_tag("S5", f"snapshot.{key} 는 YYYY-MM-DD 또는 null 이어야 합니다"))
        if not _str(snapshot.get("content_hash", "")):
            out.append(_tag("S1", "snapshot.content_hash 는 문자열(빈 값 허용)이어야 합니다"))
    return out


def _kinds(raw):
    return [entry.get("kind") for entry in raw.get("access", []) if isinstance(entry, dict)]


def _status_claim_problems(raw):
    """S7: 저장된 effective_status 가 '자동화 가능' 인데 7칸·경로 유형 계산은 그렇지 않으면 거부한다('자동화 가능'을 꾸밀 수 없다). 다른 라벨(자동화 제외·참고 전용·완전 제외)은 어느 쪽으로
    적어도 켜지 못하므로 허용한다 — 예: 운영자 결정으로 Pew 를 Tier 3 대표 사례로 '자동화 제외' 라고 적은 행(7칸 계산은 Tier 4). 모양이 올바른 Provider 에만 부른다."""
    tier = computed_strict_tier(raw["policy"], raw["class"], raw.get("ai_use", DEFAULT_AI_USE))
    computed = computed_status(raw["class"], tier, _kinds(raw))
    stored = raw["effective_status"]
    if stored == STATUS_OK and computed != STATUS_OK:
        return [_tag("S7", f"effective_status 가 '{STATUS_OK}' 인데 7칸·경로 유형 계산은 '{computed}' 입니다")]
    return []


def _active_problems(raw, today):
    """ACTIVE 조건 A0–A9(enabled 인 Provider). 모양이 올바른 Provider 에만 부른다. today 가 None 이면 기한을 확인할 수 없어 A4 로 거부한다."""
    out = []
    cells = raw["policy"]
    ai_use = raw.get("ai_use", DEFAULT_AI_USE)
    tier_computed = computed_strict_tier(cells, raw["class"], ai_use)
    kinds = _kinds(raw)
    if raw["class"] != ACTIVE_CLASS:
        out.append(_tag("A0", f"class {raw['class']} 는 ACTIVE 로 켤 수 없습니다 — 콘텐츠 Provider(class data)만 켭니다"))
    stored = raw["strict_tier"]
    if stored > 2 or tier_computed > 2:
        out.append(_tag("A1", f"strict_tier {stored}·7칸 계산 {tier_computed} — 둘 다 2 이하여야 합니다(Tier 0–2 만 허용 목록)"))
    elif stored < tier_computed:
        out.append(_tag("A1", f"strict_tier {stored} 가 7칸 계산({tier_computed})보다 낮게 적혀 있습니다"))
    if not any(kind in STRUCTURED_KINDS for kind in kinds):
        out.append(_tag("A1", "구조화 접근 경로(api·csv·dataset)가 없습니다"))
    for name in CELLS:
        if ai_use == "NEVER" and name == "ai_input":
            continue                                       # 우리가 AI 에 넣지 않는다(ai_use NEVER) — 이 칸은 판정에서만 뺀다(근거 이름·열람일 기록 A8 은 그대로)
        cell = cells[name]
        if cell["state"] == "UNKNOWN" or cell["basis"] not in STRICT_BASES:
            out.append(_tag("A2", f"{name} 칸이 알려지지 않았습니다({cell['state']}/{cell['basis']}) — UNKNOWN·IMPLIED·NOT_ADDRESSED·NOT_READ 는 켤 수 없습니다"))
    for name in CELLS:
        if ai_use == "NEVER" and name == "ai_input":
            continue
        if cells[name]["state"] == "DENIED":
            hard = " — 상업 이용·자동 접근 금지는 Tier 4" if name in ("commercial_use", "automated_access") else ""
            out.append(_tag("A3", f"{name} 칸이 DENIED 입니다{hard}"))
    snapshot = raw["snapshot"]
    expires = snapshot.get("expires_at")
    if today is None:
        out.append(_tag("A4", "기준 날짜(today)를 받지 못해 snapshot.expires_at 을 확인할 수 없습니다"))
    elif not expires:
        out.append(_tag("A4", "snapshot.expires_at 이 없습니다 — 점검 기한이 있어야 켤 수 있습니다"))
    elif today > datetime.date.fromisoformat(expires):
        out.append(_tag("A4", f"snapshot.expires_at({expires})이 지났습니다(오늘 {today.isoformat()}) — 약관을 다시 읽어 기한을 갱신해야 합니다"))
    if cells["attribution"]["state"] == "CONDITIONAL" and not str(raw.get("attribution_template", "")).strip():
        out.append(_tag("A5", "출처 표시가 CONDITIONAL 인데 attribution_template 이 없습니다"))
    bad_kinds = sorted({kind for kind in kinds if kind not in STRUCTURED_KINDS})
    if bad_kinds or raw["class"] == "image":
        out.append(_tag("A6", f"경로 유형 규칙: {'·'.join(bad_kinds) or raw['class']} 경로는 strict_tier 와 상관없이 자동화 제외입니다(외부 RSS·페이지·사진은 유형만으로 Tier 3)"))
    if tier_computed == 4 or stored == 4:
        out.append(_tag("A7", "Tier 4(상업 금지·자동 수집 금지·AI 입력 금지 등)는 완전 제외입니다"))
    for name in CELLS:
        if not str(cells[name].get("evidence", "")).strip() or not cells[name].get("read_at"):
            out.append(_tag("A8", f"{name} 칸에 근거 문서 이름(evidence)이나 열람일(read_at)이 없습니다"))
    if not any(isinstance(page, str) and page.strip() for page in snapshot.get("terms_pages") or ()):
        out.append(_tag("A8", "snapshot.terms_pages 에 비어 있지 않은 약관 문서 이름이 없습니다 — 읽은 약관 문서 이름이 하나 이상 있어야 합니다(빈 문자열·공백은 이름이 아님)"))
    if raw["effective_status"] != STATUS_OK:
        out.append(_tag("A9", f"effective_status 가 '{raw['effective_status']}' 입니다 — '{STATUS_OK}' 이어야 켤 수 있습니다"))
    for index, entry in enumerate(raw["access"]):
        paths = entry.get("paths") or []
        if not paths:
            out.append(_tag("A10", f"access[{index}] 의 paths 가 비어 있습니다 — 켜려면 호스트 전체가 아니라 실제로 쓰는 경로 접두어를 적어야 합니다"))
        elif any(not str(path).strip("/") for path in paths):
            out.append(_tag("A10", f"access[{index}] 의 paths 에 호스트 전체를 여는 접두어('/')가 있습니다 — 실제로 쓰는 경로 접두어를 적어야 합니다(SRCV2 D5)"))
    for index, entry in enumerate(raw["access"]):
        if entry.get("kind") == "api" and not rate_limit_known(entry.get("rate_limit")):
            out.append(_tag("A11", f"access[{index}] 는 api 경로인데 호출 한도(rate_limit)를 알 수 없습니다 — 제공처가 공개한 'N/minute'·'N/hour'·'N/day' 문구이거나, 공식 수치 한도가 없다고 확인한 객체(official NONE + 자체 상한 own + note)여야 합니다(모르면 비워 두고 '확인 필요' — 켤 수 없습니다)"))
    return out


def provider_problems(raw, today=None):
    """Provider 하나(JSON 객체)의 문제 목록: (모양 규칙) + (모양이 맞으면 S7) + (enabled 이고 모양이 맞으면 ACTIVE 조건). `today` 는 date·ISO 문자열·None."""
    today = to_date(today)
    problems = _shape_problems(raw)
    if problems:
        return problems
    problems = _status_claim_problems(raw)
    if raw["enabled"]:
        problems += _active_problems(raw, today)
    return problems


def _top_problems(data):
    """파일 전체가 쓸 수 없는 모양인지(S1)와 provider_id 중복(S3). 비어 있으면 Provider 별 검사로 넘어간다."""
    if not isinstance(data, dict):
        return [_tag("S1", "최상위는 객체여야 합니다")]
    out = []
    if not _is_schema_version(data.get("schema_version")):
        out.append(_tag("S1", f"schema_version 은 정수 {SCHEMA_VERSION} 이어야 합니다(true·1.0·문자열은 안 됩니다)"))
    for extra in sorted(str(key)[:30] for key in set(data) - ALLOWED_TOP_KEYS):
        out.append(_tag("S1", f"최상위에 알 수 없는 칸이 있습니다(칸 이름 오타일 수 있음): {extra!r}"))
    providers = data.get("providers")
    if not isinstance(providers, list) or not providers:
        out.append(_tag("S1", "providers 는 비어 있지 않은 배열이어야 합니다"))
        return out
    seen = set()
    for raw in providers:
        pid = raw.get("provider_id") if isinstance(raw, dict) else None
        if _str(pid) and pid in seen:
            out.append(_tag("S3", f"provider_id 가 중복됩니다: {pid}"))
        if _str(pid):
            seen.add(pid)
    return out


def _label(raw, index):
    pid = raw.get("provider_id") if isinstance(raw, dict) else None
    return pid if _str(pid) and pid else f"providers[{index}]"


def validate_registry(data, today=None):
    """허용 목록 데이터(JSON 을 읽은 값)의 문제 목록. 비어 있으면 정상. `today` 는 date·ISO 문자열·None(없으면 enabled 인 Provider 는 기한을 확인할 수 없어 거부).
    문제 문장은 `provider_id: [규칙번호] 설명` 꼴이다. 시각을 읽지 않는 순수 함수다."""
    today = to_date(today)
    top = _top_problems(data)
    if top:
        return top
    out = []
    for index, raw in enumerate(data["providers"]):
        label = _label(raw, index)
        out.extend(f"{label}: {problem}" for problem in provider_problems(raw, today))
    return out


# ----------------------------------------------------------------------------
# 읽기 전용 Registry
# ----------------------------------------------------------------------------
def _build_provider(raw):
    policy = Policy(**{name: Cell(raw["policy"][name]["state"], raw["policy"][name]["basis"], raw["policy"][name].get("evidence", ""), raw["policy"][name].get("read_at"))
                       for name in CELLS})
    access = tuple(Access(entry["kind"], tuple(entry["hosts"]), tuple(entry.get("paths", [])), entry.get("auth") or "UNKNOWN", _build_rate_limit(entry.get("rate_limit")),
                          entry.get("robots_checked_at")) for entry in raw["access"])
    snap = raw["snapshot"]
    snapshot = Snapshot(tuple(snap.get("terms_pages", [])), snap.get("read_at"), snap.get("content_hash", ""), snap.get("expires_at"))
    return Provider(raw["provider_id"], raw["name"], raw["class"], policy, raw["strict_tier"], raw.get("permissive_interpretation"), raw["effective_status"], access, snapshot,
                    raw.get("attribution_template", ""), tuple(raw.get("exceptions", [])), raw.get("retention_days"), raw["enabled"], tuple(raw.get("reference_hosts", [])),
                    raw.get("ai_use", DEFAULT_AI_USE), raw.get("own_data_only", False))


class Registry:
    """읽어 들인 허용 목록. 만든 뒤에는 바뀌지 않는다(Provider 는 frozen, 목록은 tuple). `load_registry` 가 만든다."""

    def __init__(self, providers, active_ids, reasons, today, malformed=()):
        self._providers = tuple(providers)
        self._by_id = {p.provider_id: p for p in self._providers}
        self._active = frozenset(active_ids)
        self._reasons = {pid: tuple(rs) for pid, rs in reasons.items()}
        self._malformed = frozenset(malformed)         # 모양이 틀려 Provider 를 만들 수 없어 목록에서 빠진 항목(enabled 여부와 상관없이 사유가 남는다)
        self.today = today
        index = {}
        for provider in self._providers:
            for access in provider.access:
                for host in access.hosts:
                    index.setdefault(host, []).append((provider, access))
            for host in provider.reference_hosts:
                index.setdefault(host, []).append((provider, None))
        self._hosts = index

    def get(self, provider_id):
        """Provider(ACTIVE 가 아니어도) 또는 None."""
        return self._by_id.get(provider_id)

    def providers(self):
        return self._providers

    def is_active(self, provider_id):
        return provider_id in self._active

    def active_providers(self):
        """검증을 통과한 enabled Provider(파일 순서)."""
        return [p for p in self._providers if p.provider_id in self._active]

    def inactive_reasons(self):
        """enabled 인데 ACTIVE 가 되지 못한 Provider(와 모양이 틀려 목록에서 빠진 항목) → 사유 목록."""
        return dict(self._reasons)

    def report_lines(self):
        """ACTIVE 가 못 된 사유를 한 줄씩(로그용): enabled 인데 조건을 못 채운 Provider, 그리고 모양이 틀려 목록에서 빠진 항목(enabled 가 아니어도 — 그 경우 문구가 다르다). 문제가 없으면 비어 있다."""
        return [(f"허용 목록: {pid} 는 모양이 올바르지 않아 목록에서 빠짐(Provider 로 읽을 수 없음) — {reason}" if pid in self._malformed
                 else f"허용 목록: {pid} 는 enabled 이지만 ACTIVE 가 아님 — {reason}") for pid, reasons in self._reasons.items() for reason in reasons]

    def is_url_allowed(self, url, purpose):
        """(허용 여부, 사유). 허용 호스트·경로이고 그 Provider 가 ACTIVE 일 때만 True. 사유에는 호스트와 Provider 이름만 쓴다 — 쿼리·토큰·경로는 쓰지 않는다.
        purpose 는 [a-z][a-z0-9_]{0,31} 모양이어야 하고 허용 목적(ALLOWED_PURPOSES — 지금은 fact 뿐)이어야 한다. 일반 웹 읽기(feed·page·resolve)를 포함한 그 밖의 목적은 허용 목록에 있어도 거부한다(유형만으로 Tier 3·모르는 목적은 거부)."""
        if not isinstance(purpose, str) or not _PURPOSE_RE.fullmatch(purpose):
            return False, "purpose 모양이 올바르지 않음"
        host, path, reason = split_https_url(url)
        if reason is not None:
            return False, f"주소 거부: {reason}" + (f" (호스트 {host})" if host else "")
        if purpose in GENERAL_WEB_PURPOSES:
            return False, f"일반 웹 읽기({purpose})는 유형만으로 Tier 3 이라 허용 목록에 있어도 자동화하지 않음 (호스트 {host})"
        if purpose not in ALLOWED_PURPOSES:
            return False, f"목적 {purpose} 는 허용 목적({'·'.join(sorted(ALLOWED_PURPOSES))})이 아니라 거부 (호스트 {host})"
        entries = self._hosts.get(host)
        if not entries:
            return False, f"호스트 {host} 는 허용 목록(Registry)에 없음"
        if all(a is None for _, a in entries):
            return False, f"호스트 {host} 는 {'·'.join(sorted({p.provider_id for p, _ in entries}))} 의 참고 호스트(자동 접근 경로 없음 — 참고 전용)"
        matched = [(p, a) for p, a in entries if a is not None and path_matches(path, a.paths)]
        if not matched:
            names = sorted({p.provider_id for p, _ in entries})
            return False, f"호스트 {host} 는 {'·'.join(names)} 의 것이지만 이 경로는 등록된 접근 경로가 아님"
        for provider, _ in matched:
            if provider.provider_id in self._active:
                return True, f"허용: {provider.provider_id} (ACTIVE, Tier {provider.strict_tier}) 호스트 {host}"
        provider = matched[0][0]
        if provider.enabled:
            first = (self._reasons.get(provider.provider_id) or ("활성 조건을 통과하지 못함",))[0]
            return False, f"{provider.provider_id} 는 enabled 이지만 ACTIVE 가 아님 — {first} (호스트 {host})"
        return False, f"{provider.provider_id} 는 비활성(enabled=false, {provider.effective_status}) (호스트 {host})"


def build_registry(data, today=None):
    """JSON 을 읽은 값 → Registry(입출력 없음). 전체가 쓸 수 없는 모양이면 SourceRegistryError, Provider 하나의 문제는 그 Provider 를 ACTIVE 로 올리지 않고 사유로 남긴다.
    모양이 틀려 만들 수 없는 Provider 는 목록에서 빠지고 사유는 inactive_reasons 에 provider_id(또는 순번)로 남는다."""
    today = to_date(today)
    top = _top_problems(data)
    if top:
        raise SourceRegistryError("허용 목록을 쓸 수 없습니다: " + "; ".join(top))
    providers, active, reasons, malformed = [], [], {}, set()
    for index, raw in enumerate(data["providers"]):
        label = _label(raw, index)
        shape = _shape_problems(raw)
        if shape:
            reasons[label] = shape
            malformed.add(label)
            continue
        provider = _build_provider(raw)
        providers.append(provider)
        if raw["enabled"]:                                # 꺼져 있는 Provider 는 실행에 영향이 없어 사유를 남기지 않는다
            problems = provider_problems(raw, today)
            if problems:
                reasons[label] = problems
            else:
                active.append(provider.provider_id)
    return Registry(providers, active, reasons, today, malformed)


def load_registry(path=None, today=None):
    """파일(기본 pipeline/source_registry.json)을 읽어 Registry 를 만든다. 읽을 수 없거나 JSON 이 아니거나 전체가 쓸 수 없는 모양이면 SourceRegistryError(조용히 빈 목록으로 떨어지지 않는다).
    `today` 는 date·ISO 문자열·None(None 이면 enabled 인 Provider 는 기한을 확인할 수 없어 ACTIVE 가 되지 못한다)."""
    target = Path(path) if path else DEFAULT_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SourceRegistryError(f"허용 목록을 읽을 수 없습니다 ({target.name}): {type(exc).__name__}") from exc
    return build_registry(data, today)


# ----------------------------------------------------------------------------
# AI 처리기 정책(Gemini 등 — 출처가 아니라 처리기)
# ----------------------------------------------------------------------------
AI_FIELDS = ("professional_business_use", "consumer_use", "free_service_data_use", "paid_service_data_policy", "sensitive_data_allowed", "medical_advice_use",
             "input_scope", "raw_source_text_allowed", "credential_storage", "policy_version", "policy_verified_at")
_AI_ENUMS = {
    "professional_business_use": ("ALLOWED", "CONDITIONAL", "DENIED", "UNKNOWN"),
    "consumer_use": ("ALLOWED", "CONDITIONAL", "DENIED", "UNKNOWN"),
    "free_service_data_use": ("USED_FOR_PRODUCT_IMPROVEMENT", "NOT_USED", "UNKNOWN"),
    "paid_service_data_policy": ("NOT_USED_FOR_PRODUCT_IMPROVEMENT", "USED_FOR_PRODUCT_IMPROVEMENT", "UNKNOWN"),
    "medical_advice_use": ("DENIED", "ALLOWED", "UNKNOWN"),
    "input_scope": ("SIGNAL_AND_VERIFIED_MINIMAL_FACTS",),
    "credential_storage": ("WINDOWS_CREDENTIAL_MANAGER_AND_ACTIONS_SECRETS",),
}
# 풀 수 없는 기본값(운영자 결정 2026-11-09): 이 값이 바뀐 파일은 검증이 거부한다 — 완화하려면 코드·문서·승인이 함께 바뀌어야 한다(T3).
AI_FIXED = {"raw_source_text_allowed": False, "sensitive_data_allowed": False, "medical_advice_use": "DENIED",
            "input_scope": "SIGNAL_AND_VERIFIED_MINIMAL_FACTS", "credential_storage": "WINDOWS_CREDENTIAL_MANAGER_AND_ACTIONS_SECRETS"}


@dataclass(frozen=True)
class AiProcessorPolicy:
    """AI 처리기 정책 11칸(읽기 전용). 값은 pipeline/ai_processor_policy.json 에서 온다."""
    processor: str
    professional_business_use: str
    consumer_use: str
    free_service_data_use: str
    paid_service_data_policy: str
    sensitive_data_allowed: bool
    medical_advice_use: str
    input_scope: str
    raw_source_text_allowed: bool
    credential_storage: str
    policy_version: str
    policy_verified_at: str


def validate_ai_policy(data):
    """AI 처리기 정책 파일의 문제 목록(순수). 11칸이 모두 있고 값이 열거값이며, 풀 수 없는 기본값(원문 외부 텍스트·민감 정보 입력 금지, 의료 조언 금지,
    입력 범위 = Signal·검증된 최소 Fact, 키는 Windows 자격 증명 관리자·Actions 시크릿)이 그대로여야 한다."""
    if not isinstance(data, dict):
        return [_tag("P1", "최상위는 객체여야 합니다")]
    out = []
    if not _is_schema_version(data.get("schema_version")):
        out.append(_tag("P1", f"schema_version 은 정수 {SCHEMA_VERSION} 이어야 합니다(true·1.0·문자열은 안 됩니다)"))
    for extra in sorted(str(key)[:30] for key in set(data) - AI_TOP_KEYS - set(AI_FIELDS)):
        out.append(_tag("P1", f"최상위에 알 수 없는 칸이 있습니다(칸 이름 오타일 수 있음): {extra!r}"))
    if not (_str(data.get("processor")) and data["processor"].strip()):
        out.append(_tag("P1", "processor 는 비어 있지 않은 문자열이어야 합니다"))
    for name in AI_FIELDS:
        if name not in data:
            out.append(_tag("P1", f"{name} 칸이 없습니다"))
            continue
        value = data[name]
        if name in ("sensitive_data_allowed", "raw_source_text_allowed"):
            if not isinstance(value, bool):
                out.append(_tag("P2", f"{name} 는 true/false 여야 합니다"))
        elif name == "policy_verified_at":
            if not _is_date(value):
                out.append(_tag("P2", "policy_verified_at 는 YYYY-MM-DD 여야 합니다"))
        elif name == "policy_version":
            if not (_str(value) and value.strip()):
                out.append(_tag("P2", "policy_version 은 비어 있지 않은 문자열이어야 합니다"))
        elif value not in _AI_ENUMS[name]:
            out.append(_tag("P2", f"{name} 는 {'·'.join(_AI_ENUMS[name])} 중 하나여야 합니다: {str(value)[:40]!r}"))
    for name, fixed in AI_FIXED.items():
        if name in data and data[name] != fixed:
            out.append(_tag("P3", f"{name} 는 {fixed!r} 로 고정입니다(운영자 결정 2026-11-09 — 바꾸려면 코드·문서·승인이 함께 바뀌어야 합니다)"))
    return out


def load_ai_policy(path=None):
    """pipeline/ai_processor_policy.json 을 읽어 AiProcessorPolicy 로. 읽을 수 없거나 검증을 통과하지 못하면 SourceRegistryError."""
    target = Path(path) if path else AI_POLICY_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SourceRegistryError(f"AI 처리기 정책을 읽을 수 없습니다 ({target.name}): {type(exc).__name__}") from exc
    problems = validate_ai_policy(data)
    if problems:
        raise SourceRegistryError("AI 처리기 정책 오류: " + "; ".join(problems))
    return AiProcessorPolicy(data["processor"], *(data[name] for name in AI_FIELDS))


# ----------------------------------------------------------------------------
# 명령줄(요약 출력 — 입출력은 여기뿐)
# ----------------------------------------------------------------------------
def main(argv=None):
    from pipeline.console import safe_output
    safe_output()
    parser = argparse.ArgumentParser(description="허용 목록(Source Registry)·AI 처리기 정책 검증과 요약")
    parser.add_argument("--path", default=None, help="허용 목록 파일(기본 pipeline/source_registry.json)")
    parser.add_argument("--today", default=None, help="기준 날짜 YYYY-MM-DD(없으면 enabled 인 Provider 는 기한을 확인할 수 없어 거부)")
    args = parser.parse_args(argv)
    try:
        today = to_date(args.today)
        target = Path(args.path) if args.path else DEFAULT_PATH
        data = json.loads(target.read_text(encoding="utf-8"))
        problems = validate_registry(data, today)
        load_ai_policy()
    except (SourceRegistryError, OSError, ValueError) as exc:
        print(f"[오류] {exc}")
        return 1
    providers = data["providers"]
    tiers = {}
    for raw in providers:
        tiers[raw.get("strict_tier")] = tiers.get(raw.get("strict_tier"), 0) + 1
    print(f"Provider {len(providers)}개 · enabled {sum(1 for raw in providers if raw.get('enabled') is True)}개 · Tier 분포 "
          + " ".join(f"{tier}:{n}" for tier, n in sorted(tiers.items(), key=lambda kv: str(kv[0]))))
    if problems:
        print(f"\n허용 목록 문제 {len(problems)}건:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\n허용 목록·AI 처리기 정책 검증 통과")
    print("참고: AI 처리기 정책 파일은 이 검증과 FACT 2단계의 기준이고 코드는 실행 중에 읽지 않는다 — allowlist 만 같은 원칙을 프롬프트 조립부에서 지키며 legacy 는 외부 기사 요약이 지금도 AI 입력으로 간다(docs/SOURCE_POLICY.md 10절).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
