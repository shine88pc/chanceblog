"""구조화 Fact 경로의 값 객체·검증·참조 표시 — 순수 함수 모음(표준 라이브러리만, 입출력·시계·난수·네트워크 없음).

흐름(운영자 결정 2026-11-09): 공식 구조화 데이터 → 정규화한 Fact → 자체 계산(`pipeline/calc.py`) → 자체 비교·분석 → 자체 문장(`pipeline/fact_assembler.py`).
외부 본문·기사 문단·해설문·검색 스니펫은 이 경로에 들어오지 않는다. 이 모듈은 그 흐름의 맨 아래, 값이 어디서 왔는지(출처 기록)와 값 자체를 못박는 부분이다.

- `SourceRecord`: 한 번의 수집 기록(Provider·접근 종류·요청 주소·수집 시각·응답 해시·그때의 이용 조건 요약·보관 기한). 시각은 코드가 읽지 않고 **인자로 받는다**.
- `Fact`: 정규화한 값 하나. 값이 없으면 `None`이다 — **모름은 0이 아니다**. 단위·기준일·지역을 달고 다니고, `fact_id` 는 내용 해시다.
- `DerivedFact`: 계산식 번호와 입력 id 를 기록한 계산 결과(`pipeline/calc.py`). AI 는 계산하지 않는다.
- 참조 표시: 본문 틀의 숫자·날짜는 `⟦F:id⟧` 꼴의 표시이고 렌더링할 때 값이 들어간다. 표시 없는 숫자가 틀에 있으면 `UntracedNumber` 로 거부한다(`untraced_numbers`).
  중괄호 두 개·중괄호-퍼센트는 쓰지 않는다(Liquid 오염 방지 — 지킴이 시험이 막는다).
- 숫자 정책(반올림·소수 자리·내부 정밀도)은 이 모듈의 `NUMBER_POLICY` 한 곳에만 있다. 표시 때만 반올림하고 내부는 정밀값(Decimal)을 쓴다.

SRC(허용 목록)와의 인터페이스: `ProviderLike`·`RegistryLike` 는 `pipeline/source_registry.py` 가 만드는 객체의 **최소 모양**(덕 타이핑 프로토콜)이다. 이 모듈은 그 모듈을 import 하지 않는다.
설명: docs/FACT_PATH.md
"""
import datetime
import functools
import hashlib
import json
import re
from dataclasses import dataclass, fields
from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence, runtime_checkable

SCHEMA_VERSION = 1

# ----------------------------------------------------------------------------
# 숫자 정책 — 반올림·소수 자리 규칙은 여기 한 곳에만 둔다(calc 도 여기서 가져다 쓴다)
# ----------------------------------------------------------------------------
NUMBER_POLICY = {
    "display_rounding": ROUND_HALF_UP,     # 표시할 때만 반올림한다(0.5 는 0 에서 먼 쪽으로). 내부 값은 반올림하지 않는다
    "display_decimals": 1,                 # 단위 표에 없는 단위의 표시 소수 자리
    "internal_places": 12,                 # 나눗셈·평균 같은 계산 결과를 이 자리까지 정밀하게 간직한다
    "internal_rounding": ROUND_HALF_EVEN,
    "precision": 60,                       # Decimal 계산 자릿수(넘치면 오류가 아니라 조용히 깎이는 일이 없게 넉넉히)
    "max_abs_value": Decimal(10 ** 15),    # 이보다 큰 값은 정상 자료가 아니라고 본다(정수에서 만들어 어떤 문맥에서도 같은 값)
    "max_display_decimals": 4,             # 자료의 소수 자리가 이를 넘으면 글로 쓰지 않는다(표시는 자료의 정밀도를 깎지 않는다 — D-129)
    "max_digits": 40,                      # 한 값의 유효 숫자 자리 상한 — 넘으면 id 해시·JSON 왕복에서 값이 깎일 수 있어 받지 않는다(`precision` 60 아래)
}


@dataclass(frozen=True)
class UnitSpec:
    """단위 하나의 표시 규칙: decimals 는 표시 소수 자리의 최소값(자료가 더 정밀하면 그 자리까지 — `display_context`), ratio_ok 는 변화율(%)을 만들어도 되는 척도인가
    (섭씨처럼 0 이 임의인 구간척도·순위 같은 순서척도는 False — 절대 차이만 말한다)."""
    decimals: int
    ratio_ok: bool = True


# 단위 표 — 표에 없는 단위는 소수 1자리·비율 가능으로 본다. 세는 단위·원·순위는 정수로, 화폐는 보조 단위까지.
UNIT_TABLE = {
    "명": UnitSpec(0), "건": UnitSpec(0), "개": UnitSpec(0), "곳": UnitSpec(0), "원": UnitSpec(0), "가구": UnitSpec(0), "대": UnitSpec(0), "호": UnitSpec(0),
    "엔": UnitSpec(0), "달러": UnitSpec(2), "유로": UnitSpec(2), "개월": UnitSpec(0), "분기": UnitSpec(0), "년": UnitSpec(0), "일": UnitSpec(0), "주": UnitSpec(0),
    "회": UnitSpec(0), "편": UnitSpec(0), "점": UnitSpec(0), "번": UnitSpec(0), "세": UnitSpec(0),
    "위": UnitSpec(0, False),                 # 순위는 순서척도 — 변화율을 만들지 않는다
    "℃": UnitSpec(1, False),                  # 섭씨는 0 이 임의인 구간척도 — 0.5℃ 에서 3.3℃ 가 '560% 증가'가 아니다
    "%p": UnitSpec(1, False),                 # 퍼센트포인트는 차이다 — 차이의 변화율을 만들지 않는다
    "Kp": UnitSpec(2, False),                 # 지자기 지수는 준로그 등급이라 비율이 뜻이 없다
    "nT": UnitSpec(1, False),                 # 자기장 성분은 부호가 있어 비율이 뜻이 없다
    # 허용 목록(`pipeline/fact_topics.py`)의 단위는 모두 이 표에 명시한다(시험이 확인) — 소수 자리는 최소값이고 자료가 더 정밀하면 그 자리까지 보인다
    "%": UnitSpec(1), "천명": UnitSpec(0), "만명": UnitSpec(0), "시간": UnitSpec(1), "억원": UnitSpec(0), "조원": UnitSpec(0), "억달러": UnitSpec(0), "학급": UnitSpec(0),
    "㎜": UnitSpec(1), "ppm": UnitSpec(1), "m/s": UnitSpec(1), "km/s": UnitSpec(1), "sfu": UnitSpec(1),
    "kW": UnitSpec(1), "MW": UnitSpec(1), "GW": UnitSpec(1), "kWh": UnitSpec(1), "MWh": UnitSpec(1), "GWh": UnitSpec(1), "TWh": UnitSpec(1),
    # 우주날씨(NOAA SWPC 어댑터, S2a): 등급 단계(0–5)는 순서척도라 변화율을 만들지 않는다 · X선 플레어 세기는 nW/㎡ 정수(A1.0 = 10, M1.0 = 10,000)
    "단계": UnitSpec(0, False), "nW/㎡": UnitSpec(0),
}
UNIT_DECIMALS = {unit: spec.decimals for unit, spec in UNIT_TABLE.items()}     # 표시 소수 자리 표(단위 표의 한 칸을 따로 본 것)

# ----------------------------------------------------------------------------
# 명시한 지역 문맥 — 계산·표시는 호출한 쪽의 decimal 전역 정밀도·반올림·지수 한계·함정(trap)에 기대지 않는다(재검증 D5, D-150)
# ----------------------------------------------------------------------------
EXACT_CONTEXT = Context(prec=NUMBER_POLICY["precision"], rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, capitals=1, clamp=0, flags=[],
                        traps=[InvalidOperation, DivisionByZero, Overflow])


def exact(function):
    """Decimal 을 계산·비교·표시하는 함수를 `EXACT_CONTEXT` 의 복사본 안에서 돌린다. 단항 `abs`·`-`·사칙연산은 현재 전역 문맥의 정밀도로 반올림되므로(전역 정밀도 5 에서
    `1,234,567.1` 이 `1,234,600.0` 이 되는 식) 호출한 쪽이 전역 문맥을 바꿔 두어도 결과가 달라지지 않게 모든 진입점을 이 장식자로 감싼다."""
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        with localcontext(EXACT_CONTEXT):
            return function(*args, **kwargs)
    return wrapper

# 순위·개수 계산 결과는 자료의 단위 자리와 상관없이 정수로 보인다(교육 범주의 `곳`·`개` 로 소수 자료를 넣어도 '6.0곳 비교'가 되지 않는다 — 재검증 D9, D-153)
INTEGER_FORMULAS = frozenset({"F04_rank", "F12_count", "F16_count_between"})

# ----------------------------------------------------------------------------
# Fact 종류
# ----------------------------------------------------------------------------
KIND_NUMBER = "NUMBER"                    # 수치
KIND_DATE = "DATE"                        # 날짜
KIND_DATETIME = "DATETIME"                # 시각
KIND_REGION = "REGION"                    # 지역
KIND_OBSERVATION = "OBSERVATION"          # 관측값
KIND_OFFICIAL_STATUS = "OFFICIAL_STATUS"  # 공식 상태
KIND_CLASS_CODE = "CLASS_CODE"            # 분류코드
KIND_PRICE = "PRICE"                      # 가격
KIND_EVENT_START = "EVENT_START"          # 행사 시작일
KIND_EVENT_END = "EVENT_END"              # 행사 종료일
KIND_LAW_EFFECTIVE = "LAW_EFFECTIVE"      # 법령 시행일
KIND_API_VERSION = "API_VERSION"          # API 버전
NUMERIC_KINDS = frozenset({KIND_NUMBER, KIND_OBSERVATION, KIND_PRICE})
DATE_KINDS = frozenset({KIND_DATE, KIND_EVENT_START, KIND_EVENT_END, KIND_LAW_EFFECTIVE})
TEXT_KINDS = frozenset({KIND_REGION, KIND_OFFICIAL_STATUS, KIND_CLASS_CODE, KIND_API_VERSION})
FACT_KINDS = NUMERIC_KINDS | DATE_KINDS | TEXT_KINDS | {KIND_DATETIME}

# 구조화 접근 경로만 읽는다(RSS·HTML·이미지는 이 경로의 입력이 아니다 — 운영자 결정 R5)
STRUCTURED_ACCESS_KINDS = frozenset({"api", "csv", "dataset"})
# SRC 의 Registry 가 쓰는 '자동화 가능' 상태 문자열(인터페이스 약속)과 허용 Tier 상한
ACTIVE_STATUS = "자동화 가능"
MAX_ACTIVE_TIER = 2

# 주제 범주: 키는 `<주제>.<지표>` 꼴이고 주제가 이 목록에 있으면 이 경로가 쓰지 않는다(건강·금융 투자 조언 범주는 틀 자체가 없다)
BLOCKED_TOPICS = frozenset({"health", "medical", "pharma", "drug", "invest", "securities", "stock", "crypto", "legal"})


class FactError(ValueError):
    """이 경로의 모든 예외의 뿌리."""


class FactFormatError(FactError):
    """JSON 을 읽거나 객체를 만들 때 형식이 틀렸다. `problems` 에 문제 목록(값은 싣지 않는다)."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems[:5]) or "형식 오류")


class UnitMismatch(FactError):
    """단위가 다른 값끼리는 계산하지 않는다."""


class UntracedNumber(FactError):
    """틀에 참조 표시 없는 숫자가 있다. `numbers` 에 찾은 글자."""

    def __init__(self, numbers):
        self.numbers = list(numbers)
        super().__init__("참조 표시 없는 숫자: " + ", ".join(self.numbers[:8]))


class UnknownReference(FactError):
    """참조 표시가 가리키는 Fact·출처 기록이 없다."""


class UnboundSlot(FactError):
    """틀의 칸 이름이 묶이지 않았다."""


class MissingValue(FactError):
    """값이 없는(모름) Fact 를 글자로 바꾸려 했다 — 0 으로 채우지 않고 거부한다."""


class TemplateError(FactError):
    """틀의 표시가 깨졌다(닫히지 않음·알 수 없는 종류·남은 표시 문자)."""


class PrecisionLimit(FactError):
    """자료의 소수 자리가 표시 한도를 넘는다 — 값을 깎아 보여 주지 않고 글로 쓰지 않는다."""


# ----------------------------------------------------------------------------
# 숫자 다루기
# ----------------------------------------------------------------------------
_NUMBER_TEXT_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)")      # 아라비아 숫자만(전각·인도 숫자는 받지 않는다)


@exact
def to_decimal(value):
    """int·str·Decimal(·float)을 Decimal 로. 글자는 `-12.50` 같은 평범한 십진 표기만(지수·밑줄·16진·무한·NaN 은 받지 않는다). 불리언·무한·너무 큰 값은 FactFormatError."""
    if isinstance(value, bool):
        raise FactFormatError(["숫자 값이 불리언임"])
    try:
        if isinstance(value, Decimal):
            number = value
        elif isinstance(value, float):
            number = Decimal(repr(value))
        elif isinstance(value, int):
            number = Decimal(value)
        elif isinstance(value, str):
            if not _NUMBER_TEXT_RE.fullmatch(value):
                raise FactFormatError(["숫자 값을 읽을 수 없음"])
            number = Decimal(value)
        else:
            raise FactFormatError(["숫자 값의 형식이 맞지 않음"])
    except InvalidOperation:
        raise FactFormatError(["숫자 값을 읽을 수 없음"]) from None
    if not number.is_finite():
        raise FactFormatError(["숫자 값이 유한하지 않음"])
    if number.copy_abs() >= NUMBER_POLICY["max_abs_value"]:
        raise FactFormatError(["숫자 값이 너무 큼"])
    if len(number.as_tuple().digits) > NUMBER_POLICY["max_digits"]:
        raise FactFormatError(["숫자 값의 자리가 너무 많음"])
    return number


@exact
def canonical_number(value):
    """Decimal 의 결정적 글자 모양(지수 표기 없음, 뒤의 0 제거, 음의 0 없음). 해시·직렬화가 쓴다. 호출한 쪽의 decimal 전역 문맥과 상관없이 같은 글자 — 같은 값이면 같은 id(D-144·D-150)."""
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def unit_spec(unit):
    """단위의 표시 규칙(단위 표에 없으면 소수 1자리·비율 가능)."""
    return UNIT_TABLE.get(unit or "", UnitSpec(NUMBER_POLICY["display_decimals"]))


def ratio_ok(unit):
    """이 단위의 값끼리 변화율(%)을 만들어도 되는가 — 0 이 임의인 구간척도(℃)·순서척도(위)는 아니다."""
    return unit_spec(unit).ratio_ok


def decimals_for(unit, context=None):
    """단위의 표시 소수 자리. context({단위: 자리}, `display_context` 가 만든다)에 있으면 그 자리, 없으면 단위 표의 자리."""
    if context and unit in context:
        return context[unit]
    return unit_spec(unit).decimals


@exact
def value_decimals(value):
    """Decimal 값의 소수 자리(뒤의 0 은 세지 않는다, 정수는 0): 3.50 → 1, 3.46 → 2, 1200 → 0."""
    return max(0, -value.normalize().as_tuple().exponent)


@exact
def display_context(items):
    """글에 쓰는 숫자 Fact 들 → {단위: 표시 소수 자리}. 자리는 **단위 표의 최소 자리와 자료의 소수 자리 중 큰 쪽**이고 한 글 안에서 같은 단위는 같은 자리다 — 그래서 자료의 값은 반올림 없이
    그대로 보이고(3.44 와 3.46 이 둘 다 `3.5` 로 보여 '달라지지 않았다'와 모순되는 일이 없다), 두 값의 차이도 정확히 보인다. 값이 없는(모름) 것은 건너뛴다.
    `%` 가 있으면 `%p`(퍼센트끼리의 차이)도 같은 자리다. 자료의 소수 자리가 `max_display_decimals` 를 넘으면 PrecisionLimit."""
    context = {}
    limit = NUMBER_POLICY["max_display_decimals"]
    for item in items:
        value = getattr(item, "value", None)
        if not isinstance(value, Decimal):
            continue
        places = value_decimals(value)
        if places > limit:
            raise PrecisionLimit(f"값의 소수 자리가 표시 한도({limit}자리)를 넘음")
        context[item.unit] = max(context.get(item.unit, decimals_for(item.unit)), places)
    if "%" in context:
        context["%p"] = max(context.get("%p", 0), context["%"])
    return context


@exact
def round_display(value, decimals):
    """표시용 반올림(0 에서 먼 쪽 반올림). 내부 값은 이 함수로 바꾸지 않는다."""
    return value.quantize(Decimal(1).scaleb(-decimals), rounding=NUMBER_POLICY["display_rounding"])


@exact
def format_decimal(value, decimals, *, signed=False, absolute=False):
    """천 단위 쉼표와 고정 소수 자리로 쓴 숫자. 음수는 `−`(U+2212), signed 이면 양수에 `+`. 반올림해 0 이 되면 부호를 붙이지 않는다. absolute 이면 부호 없이 크기만."""
    rounded = round_display(value, decimals)        # 반올림한 값이 0 이면(`-0.0` 포함) 부호가 붙지 않는다 — 아래 부호는 반올림한 값으로 정한다
    body = format(rounded.copy_abs(), f",.{decimals}f")       # 단항 abs 는 전역 정밀도로 반올림되므로 copy_abs(D5)
    if absolute:
        return body
    if rounded < 0:
        return "−" + body
    if signed and rounded > 0:
        return "+" + body
    return body


@exact
def format_with_unit(value, unit, *, signed=False, absolute=False, context=None):
    return format_decimal(value, decimals_for(unit, context), signed=signed, absolute=absolute) + (unit or "")


def decimals_of(obj, context=None):
    """객체(Fact·계산 결과)를 보일 소수 자리: 순위·개수 계산 결과(`INTEGER_FORMULAS`)는 자료의 단위 자리와 상관없이 정수, 그 밖은 단위 표·자료 정밀도 자리(`display_context`)."""
    if isinstance(obj, DerivedFact) and obj.formula_id in INTEGER_FORMULAS:
        return 0
    return decimals_for(obj.unit, context)


@exact
def format_object(obj, *, signed=False, absolute=False, context=None):
    """`format_with_unit` 의 객체판 — 세는 단위(순위·개수)는 정수로, 그 밖은 `decimals_of` 자리로 쓴다."""
    return format_decimal(obj.value, decimals_of(obj, context), signed=signed, absolute=absolute) + (obj.unit or "")


@exact
def is_half_tie(value, places):
    """value 를 places 자리로 반올림할 때 정확히 반 칸(…5 로 끝나고 그 뒤가 없음)에 걸리는가 — 이때만 반올림 방향이 정해져야 해서 한 칸 어긋난 표시가 나올 수 있다."""
    return (value.scaleb(places).copy_abs() % 1) == Decimal("0.5")


@exact
def settle_context(context, items):
    """표시 자리에서 정확히 반 칸에 걸리는 값(예: 짝수 곳의 평균이 3.45)이 있으면 그 단위의 자리를 한 칸 늘려 값이 반올림 없이 보이게 한다(`%` 와 `%p` 는 같이). 반올림은 평균과
    차이를 따로 하면 방향이 서로 달라 `보이는 값 − 보이는 평균 ≠ 보이는 차이` 가 되기 때문이다(재검증 D6, D-152). 한 값이 걸리는 자리는 하나뿐이라 몇 번 안에 끝난다. 새 사전을 돌려준다."""
    context = dict(context)
    limit = NUMBER_POLICY["internal_places"] - 1
    for _pass in range(limit + 2):                    # 한 값은 많아야 limit 번 늘어난다 — 그 안에 끝난다(바퀴 수에 상한을 둬, 자리표가 늘림을 따르지 않는 이상한 경우에도 무한 반복하지 않는다)
        changed = False
        for item in items:
            value = getattr(item, "value", None)
            if not isinstance(value, Decimal):
                continue
            places = decimals_for(item.unit, context)
            if places < limit and is_half_tie(value, places):
                for unit in (("%", "%p") if item.unit in ("%", "%p") else (item.unit,)):
                    context[unit] = max(decimals_for(unit, context), places + 1)
                changed = True
        if not changed:
            break
    return context


@exact
def display_sign(value, unit, context=None):
    """표시되는(반올림한) 값의 부호: -1·0·1. '올랐다·내렸다·같다' 는 이 값으로 고른다(0.04 가 `0.0` 으로 보이는데 '올랐다' 고 쓰지 않게)."""
    rounded = round_display(value, decimals_for(unit, context))
    return (rounded > 0) - (rounded < 0)


def require_same_unit(a, b):
    """단위가 다른 값끼리는 계산하지 않는다 — 다르면 UnitMismatch. 같으면 그 단위."""
    if a.unit != b.unit:
        raise UnitMismatch("단위가 다른 값끼리는 계산하지 않음")
    return a.unit


def diff_unit(unit):
    """두 값의 차이에 붙는 단위: 퍼센트끼리의 차이는 퍼센트포인트(`%p`)."""
    return "%p" if unit in ("%", "%p") else unit


# ----------------------------------------------------------------------------
# 결정적 직렬화·해시(정렬된 JSON — 해시 시드와 무관)
# ----------------------------------------------------------------------------
def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def content_digest(prefix, content, length=16):
    return prefix + hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()[:length]


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


ID_RE = re.compile(r"[sfd][0-9a-f]{16}")


# ----------------------------------------------------------------------------
# 기준일(as_of) 읽기: 연·분기·월·일·시각
# ----------------------------------------------------------------------------
_YEAR_RE = re.compile(r"([0-9]{4})")                                   # 기준일의 숫자는 아라비아 숫자만(전각 숫자 `２０２５` 는 기준일이 아니다)
_QUARTER_RE = re.compile(r"([0-9]{4})-Q([1-4])")
_MONTH_RE = re.compile(r"([0-9]{4})-(0[1-9]|1[0-2])")
_DAY_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_INSTANT_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?(Z|[+-][0-9]{2}:[0-9]{2})")


@dataclass(frozen=True)
class Period:
    """기준일을 읽은 결과. granularity 는 year·quarter·month·day·instant, ordinal 은 같은 granularity 끼리 견주는 정수(연속한 기간이면 1 차이)."""
    granularity: str
    year: int
    month: Optional[int]
    day: Optional[int]
    quarter: Optional[int]
    ordinal: int
    text: str


def _utc_offset(text):
    if text == "Z":
        return datetime.timedelta(0)
    sign = 1 if text[0] == "+" else -1
    hours, minutes = int(text[1:3]), int(text[4:6])
    if hours > 14 or minutes > 59:
        raise ValueError("시간대 차이가 범위 밖")
    return sign * datetime.timedelta(hours=hours, minutes=minutes)


def parse_as_of(text):
    """기준일 글자를 Period 로. 모양이 맞지 않거나 없는 날짜(2월 30일 등)면 None. 시각을 읽지 않는다 — 글자만 본다."""
    if not isinstance(text, str):
        return None
    try:
        found = _YEAR_RE.fullmatch(text)
        if found:
            year = int(found.group(1))
            return Period("year", year, None, None, None, year, text)
        found = _QUARTER_RE.fullmatch(text)
        if found:
            year, quarter = int(found.group(1)), int(found.group(2))
            return Period("quarter", year, quarter * 3 - 2, None, quarter, year * 4 + quarter - 1, text)
        found = _MONTH_RE.fullmatch(text)
        if found:
            year, month = int(found.group(1)), int(found.group(2))
            return Period("month", year, month, None, (month - 1) // 3 + 1, year * 12 + month - 1, text)
        found = _DAY_RE.fullmatch(text)
        if found:
            year, month, day = (int(part) for part in found.groups())
            ordinal = datetime.date(year, month, day).toordinal()
            return Period("day", year, month, day, (month - 1) // 3 + 1, ordinal, text)
        found = _INSTANT_RE.fullmatch(text)
        if found:
            year, month, day, hour, minute = (int(found.group(i)) for i in range(1, 6))
            second = int(found.group(6) or 0)
            moment = datetime.datetime(year, month, day, hour, minute, second)
            seconds = (moment - datetime.datetime(1970, 1, 1) - _utc_offset(found.group(7))).total_seconds()
            return Period("instant", year, month, day, (month - 1) // 3 + 1, int(seconds), text)
    except ValueError:
        return None
    return None


def period_start(period):
    """기간의 첫날(datetime.date). instant 는 그 날짜."""
    if period.granularity == "year":
        return datetime.date(period.year, 1, 1)
    if period.granularity in ("quarter", "month"):
        return datetime.date(period.year, period.month, 1)
    return datetime.date(period.year, period.month, period.day)


def period_end(period):
    """기간의 마지막 날(datetime.date)."""
    if period.granularity == "year":
        return datetime.date(period.year, 12, 31)
    if period.granularity == "quarter":
        month = period.month + 2
        return _month_end(period.year, month)
    if period.granularity == "month":
        return _month_end(period.year, period.month)
    return datetime.date(period.year, period.month, period.day)


def _month_end(year, month):
    following = datetime.date(year + (month // 12), month % 12 + 1, 1)
    return following - datetime.timedelta(days=1)


def utc_day_of(period):
    """시각(instant) Period 가 속한 **UTC 날짜** 글자(`YYYY-MM-DD`) — 쓴 시간대 표기와 상관없이 UTC 로 센다. 시각이 아니거나 범위를 벗어나면 None."""
    if period is None or period.granularity != "instant":
        return None
    try:
        day = datetime.date(1970, 1, 1) + datetime.timedelta(days=period.ordinal // 86400)
    except (OverflowError, ValueError):
        return None
    return f"{day.year:04d}-{day.month:02d}-{day.day:02d}"


def shift_year(as_of, years):
    """같은 기간의 몇 해 전·후 기준일 글자. 연·분기·월·일만(윤일 2월 29일이 없는 해는 None). instant 는 None."""
    period = parse_as_of(as_of)
    if period is None or period.granularity == "instant":
        return None
    year = period.year + years
    if year < 1 or year > 9999:
        return None
    if period.granularity == "year":
        return f"{year:04d}"
    if period.granularity == "quarter":
        return f"{year:04d}-Q{period.quarter}"
    if period.granularity == "month":
        return f"{year:04d}-{period.month:02d}"
    try:
        datetime.date(year, period.month, period.day)
    except ValueError:
        return None
    return f"{year:04d}-{period.month:02d}-{period.day:02d}"


GRANULARITY_UNIT = {"year": "년", "quarter": "분기", "month": "개월", "day": "일"}   # '최근 N개월' 같은 말의 단위
PERIODS_PER_YEAR = {"year": 1, "quarter": 4, "month": 12}


def format_period_ko(as_of):
    """기준일의 한국어 표기: 2026년·2026년 1분기·2026년 3월·2026년 3월 15일·2026년 3월 15일 9시 30분(UTC)."""
    period = parse_as_of(as_of)
    if period is None:
        raise FactFormatError(["기준일 형식이 맞지 않음"])
    if period.granularity == "year":
        return f"{period.year}년"
    if period.granularity == "quarter":
        return f"{period.year}년 {period.quarter}분기"
    if period.granularity == "month":
        return f"{period.year}년 {period.month}월"
    if period.granularity == "day":
        return f"{period.year}년 {period.month}월 {period.day}일"
    found = _INSTANT_RE.fullmatch(as_of)
    hour, minute, zone = int(found.group(4)), int(found.group(5)), found.group(7)
    if zone in ("Z", "+00:00"):
        label = "UTC"
    elif zone == "+09:00":
        label = "한국 시간"
    else:
        label = f"UTC{zone}"
    return f"{period.year}년 {period.month}월 {period.day}일 {hour}시 {minute}분({label})"


def format_date_ko(text):
    """DATE 류 값(YYYY-MM-DD)의 한국어 표기. 날짜가 아니면 FactFormatError."""
    period = parse_as_of(text)
    if period is None or period.granularity != "day":
        raise FactFormatError(["날짜 형식이 맞지 않음"])
    return f"{period.year}년 {period.month}월 {period.day}일"


# ----------------------------------------------------------------------------
# 값 객체
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class SourceRecord:
    """한 번의 수집 기록. `retrieved_at` 은 인자로 받은 ISO 시각 글자(코드가 시계를 읽지 않는다), `record_id` 는 내용 해시."""
    record_id: str
    provider_id: str
    access_kind: str
    request_url: str
    retrieved_at: str
    response_hash: str
    license_snapshot: str
    retention_days: Optional[int] = None

    @classmethod
    def create(cls, provider_id, access_kind, request_url, retrieved_at, response_hash, license_snapshot, retention_days=None):
        content = {"provider_id": provider_id, "access_kind": access_kind, "request_url": request_url, "retrieved_at": retrieved_at,
                   "response_hash": response_hash, "license_snapshot": license_snapshot, "retention_days": retention_days}
        return cls(content_digest("s", content), provider_id, access_kind, request_url, retrieved_at, response_hash, license_snapshot, retention_days)


def _record_content(record):
    return {"provider_id": record.provider_id, "access_kind": record.access_kind, "request_url": record.request_url,
            "retrieved_at": record.retrieved_at, "response_hash": record.response_hash,
            "license_snapshot": record.license_snapshot, "retention_days": record.retention_days}


@dataclass(frozen=True)
class Fact:
    """정규화한 값 하나. value 가 None 이면 '모름'이다(0 이 아니다). 숫자 종류의 value 는 Decimal, 날짜·시각·글자 종류는 str.
    label_ko·label_en·region_label_* 은 **우리가 정한 낱말**(어댑터의 라벨 표)이고 제공처의 설명 문장이 아니다.
    meta 는 값의 출처 구분·상태 꼬리표(`producer`·`status` 등 이름순 (이름, 값) 튜플) — 없으면 None 이고 id·JSON 이 꼬리표가 생기기 전과 같다."""
    fact_id: str
    provider_id: str
    source_record_id: str
    kind: str
    key: str
    value: Any
    unit: Optional[str] = None
    as_of: Optional[str] = None
    region: Optional[str] = None
    region_level: Optional[str] = None
    region_label_ko: Optional[str] = None
    region_label_en: Optional[str] = None
    label_ko: Optional[str] = None
    label_en: Optional[str] = None
    meta: Optional[tuple] = None

    @classmethod
    def create(cls, provider_id, source_record_id, kind, key, value, unit=None, as_of=None, region=None, region_level=None,
               region_label_ko=None, region_label_en=None, label_ko=None, label_en=None, meta=None):
        if value is not None:
            value = to_decimal(value) if kind in NUMERIC_KINDS else value
        fields_ = {"provider_id": provider_id, "source_record_id": source_record_id, "kind": kind, "key": key, "value": value,
                   "unit": unit, "as_of": as_of, "region": region, "region_level": region_level, "region_label_ko": region_label_ko,
                   "region_label_en": region_label_en, "label_ko": label_ko, "label_en": label_en}
        meta = normalize_meta(meta)
        if meta is not None:
            fields_["meta"] = meta                     # 꼬리표가 없는 Fact 는 칸 자체를 해시에 넣지 않는다 — 꼬리표가 생기기 전과 같은 id
        return cls(compute_fact_id(fields_), **fields_)

    @property
    def topic(self):
        return self.key.split(".", 1)[0]

    def meta_value(self, name, default=None):
        """꼬리표(`meta`)의 한 값. 없으면 default."""
        for pair_name, pair_value in self.meta or ():
            if pair_name == name:
                return pair_value
        return default


# 꼬리표(`meta`): 값이 어디서 왔고 어떤 상태인지를 Fact 에 붙이는 짧은 (이름, 값) 글자쌍 — `producer`(값을 만든 기관)·`status`(observed·estimated·predicted·reference)·`quality`·`satellite` 같은 것.
# 이름순으로 정렬한 튜플이고 해시에 들어간다(꼬리표가 다르면 다른 Fact). 없으면 None 이고 그때의 id 는 꼬리표가 생기기 전과 바이트까지 같다.
META_MAX_ITEMS = 8
_META_NAME_RE = re.compile(r"[a-z][a-z_]{0,23}")
_META_VALUE_RE = re.compile(r"[A-Za-z0-9_.:\-]{1,32}")


def normalize_meta(meta):
    """사전이나 (이름, 값) 쌍의 나열 → 이름순 튜플(비었거나 None 이면 None). 쌍이 아니면 FactFormatError. 이름·값의 모양은 `validate_fact` 가 본다."""
    if meta is None:
        return None
    try:
        items = list(meta.items()) if isinstance(meta, Mapping) else [tuple(pair) for pair in meta]
        if not all(len(pair) == 2 for pair in items):
            raise ValueError("쌍이 아님")
        pairs = tuple(sorted(((pair[0], pair[1]) for pair in items), key=lambda pair: (str(pair[0]), str(pair[1]))))
    except (TypeError, ValueError):
        raise FactFormatError(["꼬리표(meta)의 모양이 맞지 않음"]) from None
    return pairs or None


def _meta_problems(meta):
    if not isinstance(meta, tuple) or not 1 <= len(meta) <= META_MAX_ITEMS:
        return ["`meta` 이(가) 1–8개의 쌍 튜플이 아님"]
    problems, names = [], []
    for pair in meta:
        if not isinstance(pair, tuple) or len(pair) != 2 or not isinstance(pair[0], str) or not isinstance(pair[1], str) \
                or not _META_NAME_RE.fullmatch(pair[0]) or not _META_VALUE_RE.fullmatch(pair[1]):
            return ["`meta` 의 이름이나 값 모양이 맞지 않음"]
        names.append(pair[0])
    if names != sorted(set(names)):
        problems.append("`meta` 의 이름이 정렬돼 있지 않거나 겹침")
    return problems


def _value_text(value):
    return canonical_number(value) if isinstance(value, Decimal) else value


def compute_fact_id(fields_):
    content = dict(fields_)
    content["value"] = _value_text(content.get("value"))
    meta = content.pop("meta", None)
    if meta is not None:
        content["meta"] = {name: value for name, value in meta}          # 정렬된 JSON 이라 순서와 무관 — 칸이 없거나 None 이면 해시에 넣지 않는다(이전과 같은 id)
    return content_digest("f", content)


def fact_content(fact):
    return {f.name: getattr(fact, f.name) for f in fields(fact) if f.name != "fact_id"}


@dataclass(frozen=True)
class DerivedFact:
    """계산식 번호와 입력 id 를 기록한 계산 결과(`pipeline/calc.py`가 만든다). 입력은 Fact 일 수도, 다른 DerivedFact 일 수도 있다.
    key·region·region_level·provider_id 는 입력에서 이어받는다(비교 가능성 판정에 쓰인다)."""
    fact_id: str
    formula_id: str
    input_fact_ids: tuple
    value: Decimal
    unit: str
    as_of: Optional[str] = None
    region: Optional[str] = None
    key: Optional[str] = None
    region_level: Optional[str] = None
    provider_id: Optional[str] = None

    @classmethod
    def create(cls, formula_id, input_fact_ids, value, unit, as_of=None, region=None, key=None, region_level=None, provider_id=None):
        inputs = tuple(input_fact_ids)
        number = to_decimal(value)
        content = {"formula_id": formula_id, "input_fact_ids": list(inputs), "value": canonical_number(number), "unit": unit, "as_of": as_of,
                   "region": region, "key": key, "region_level": region_level, "provider_id": provider_id}
        return cls(content_digest("d", content), formula_id, inputs, number, unit, as_of, region, key, region_level, provider_id)


def derived_content(derived):
    return {"formula_id": derived.formula_id, "input_fact_ids": list(derived.input_fact_ids), "value": canonical_number(derived.value),
            "unit": derived.unit, "as_of": derived.as_of, "region": derived.region, "key": derived.key,
            "region_level": derived.region_level, "provider_id": derived.provider_id}


@dataclass(frozen=True)
class FactBundle:
    """한 번의 수집에서 나온 출처 기록과 Fact 들(+ 계산 결과). JSON 으로 쓰고 읽는 단위."""
    records: tuple
    facts: tuple
    derived: tuple = ()


# ----------------------------------------------------------------------------
# 검증기 — 문제 목록(값은 싣지 않는다). 비어 있으면 정상
# ----------------------------------------------------------------------------
_PROVIDER_ID_RE = re.compile(r"[a-z][a-z0-9_]{1,40}")
_KEY_RE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*")
_REGION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,31}")
_LEVEL_RE = re.compile(r"[a-z][a-z0-9_]{0,23}")
_LABEL_RE = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣA-Za-z][가-힣ㄱ-ㅎㅏ-ㅣA-Za-z ·()/\-]{0,23}")
_LABEL_EN_RE = re.compile(r"[A-Za-z][A-Za-z ()/\-]{0,47}")
_UNIT_RE = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣA-Za-z%℃㎡㎏㎖㎞㎎㎜㎝㎥][가-힣ㄱ-ㅎㅏ-ㅣA-Za-z%℃㎡㎏㎖㎞㎎㎜㎝㎥/·\-]{0,15}")
_TEXT_VALUE_RE = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣA-Za-z0-9_.:\-/ ]{1,64}")
_HASH_RE = re.compile(r"[0-9a-f]{64}")
_SECRET_WORDS = frozenset({"key", "apikey", "token", "secret", "password", "passwd", "pwd", "auth", "authorization", "credential", "credentials",
                           "signature", "sig", "session", "cookie", "bearer"})
_SECRET_SUFFIXES = ("key", "token", "secret", "password", "passwd", "auth", "signature")   # serviceKey·accessToken 같은 붙여 쓴 이름
_URL_BAD_CHARS = re.compile(r"[\s\x00-\x1f\x7f<>\"'`\\|{}\[\]]")
_MARKERS = ("⟦", "⟧")


def _single_spaced(text):
    return text == " ".join(text.split())


def _text_problem(name, value, pattern, *, required=False):
    if value is None:
        return [f"`{name}` 이(가) 없음"] if required else []
    if not isinstance(value, str) or not pattern.fullmatch(value) or not _single_spaced(value):
        return [f"`{name}` 형식이 맞지 않음"]
    return []


def query_has_secret_name(query):
    """질의 문자열(`a=b&c=d`, 앞의 `?` 는 있어도 없어도 된다)에 키·토큰·비밀번호·서명처럼 보이는 이름이 있는가. 이름만 본다(값은 보지 않는다)."""
    for part in query.lstrip("?").split("&"):
        name = part.split("=", 1)[0].strip().lower()
        if not name:
            continue
        words = [w for w in re.split(r"[^a-z0-9]+", name) if w]
        if any(w in _SECRET_WORDS for w in words) or name.endswith(_SECRET_SUFFIXES):
            return True
    return False


def request_url_problems(url):
    """수집 기록에 남기는 주소는 비밀 없는 https 주소뿐이다: 사용자 정보·비밀로 보이는 질의 이름·공백·따옴표·중괄호가 없다."""
    if not isinstance(url, str) or not url:
        return ["`request_url` 이(가) 없음"]
    problems = []
    if len(url) > 500 or _URL_BAD_CHARS.search(url):
        problems.append("`request_url` 에 쓸 수 없는 글자나 너무 긴 글이 있음")
    match = re.fullmatch(r"https://([A-Za-z0-9.\-]+)(:\d{1,5})?(/[^?#]*)?(\?[^#]*)?", url)
    if not match:
        problems.append("`request_url` 이(가) 사용자 정보·조각 없는 https 주소가 아님")
    elif match.group(4) and query_has_secret_name(match.group(4)):
        problems.append("`request_url` 의 질의에 비밀로 보이는 이름이 있음(키는 주소에 넣지 않는다)")
    return problems


def validate_record(record):
    problems = []
    if not isinstance(record, SourceRecord):
        return ["출처 기록이 SourceRecord 가 아님"]
    problems += _text_problem("provider_id", record.provider_id, _PROVIDER_ID_RE, required=True)
    if record.access_kind not in STRUCTURED_ACCESS_KINDS:
        problems.append("`access_kind` 이(가) 구조화 경로(api·csv·dataset)가 아님")
    problems += request_url_problems(record.request_url)
    period = parse_as_of(record.retrieved_at)
    if period is None or period.granularity != "instant":
        problems.append("`retrieved_at` 이(가) 시각(ISO, 시간대 포함)이 아님")
    if not isinstance(record.response_hash, str) or not _HASH_RE.fullmatch(record.response_hash):
        problems.append("`response_hash` 이(가) sha256 16진수 64자가 아님")
    if not isinstance(record.license_snapshot, str) or not record.license_snapshot.strip() or len(record.license_snapshot) > 600:
        problems.append("`license_snapshot` 이(가) 비었거나 600자를 넘음")
    days = record.retention_days
    if days is not None and (isinstance(days, bool) or not isinstance(days, int) or days < 0):
        problems.append("`retention_days` 이(가) 0 이상의 정수가 아님")
    if not problems and record.record_id != content_digest("s", _record_content(record)):
        problems.append("`record_id` 이(가) 내용과 맞지 않음")
    return problems


@exact
def validate_fact(fact):
    problems = []
    if not isinstance(fact, Fact):
        return ["Fact 가 Fact 객체가 아님"]
    problems += _text_problem("provider_id", fact.provider_id, _PROVIDER_ID_RE, required=True)
    if not isinstance(fact.source_record_id, str) or not ID_RE.fullmatch(fact.source_record_id) or not fact.source_record_id.startswith("s"):
        problems.append("`source_record_id` 이(가) 출처 기록 id 모양이 아님")
    if fact.kind not in FACT_KINDS:
        problems.append("`kind` 이(가) 알려진 종류가 아님")
    problems += _text_problem("key", fact.key, _KEY_RE, required=True)
    problems += _text_problem("region", fact.region, _REGION_RE)
    problems += _text_problem("region_level", fact.region_level, _LEVEL_RE)
    problems += _text_problem("region_label_ko", fact.region_label_ko, _LABEL_RE)
    problems += _text_problem("region_label_en", fact.region_label_en, _LABEL_EN_RE)
    problems += _text_problem("label_ko", fact.label_ko, _LABEL_RE)
    problems += _text_problem("label_en", fact.label_en, _LABEL_EN_RE)
    if fact.region is not None and fact.region_level is None:
        problems.append("`region` 이(가) 있는데 `region_level` 이(가) 없음")
    if fact.meta is not None:
        problems += _meta_problems(fact.meta)
    if fact.kind in NUMERIC_KINDS:
        if fact.value is not None:
            if not isinstance(fact.value, Decimal) or not fact.value.is_finite():
                problems.append("숫자 종류의 `value` 이(가) 유한한 Decimal 이 아님")
            elif fact.value.copy_abs() >= NUMBER_POLICY["max_abs_value"]:
                problems.append("`value` 이(가) 너무 큼")
        if not isinstance(fact.unit, str) or not _UNIT_RE.fullmatch(fact.unit):
            problems.append("숫자 종류의 `unit` 이(가) 없거나 형식이 맞지 않음(숫자마다 단위가 있어야 한다)")
        if parse_as_of(fact.as_of) is None:
            problems.append("숫자 종류의 `as_of` 이(가) 없거나 기준일 형식이 아님")
        if fact.label_ko is None:
            problems.append("숫자 종류의 `label_ko` 이(가) 없음(우리가 정한 낱말이 필요하다)")
    else:
        if fact.unit not in (None, ""):
            problems.append("숫자가 아닌 종류에 `unit` 이(가) 있음")
        if fact.as_of is not None and parse_as_of(fact.as_of) is None:
            problems.append("`as_of` 이(가) 기준일 형식이 아님")
        if fact.value is not None:
            if fact.kind in DATE_KINDS:
                if not isinstance(fact.value, str) or parse_as_of(fact.value) is None or parse_as_of(fact.value).granularity != "day":
                    problems.append("날짜 종류의 `value` 이(가) YYYY-MM-DD 가 아님")
            elif fact.kind == KIND_DATETIME:
                if not isinstance(fact.value, str) or parse_as_of(fact.value) is None or parse_as_of(fact.value).granularity != "instant":
                    problems.append("시각 종류의 `value` 이(가) 시간대 포함 ISO 시각이 아님")
            elif not isinstance(fact.value, str) or not _TEXT_VALUE_RE.fullmatch(fact.value):
                problems.append("글자 종류의 `value` 형식이 맞지 않음")
    if not problems:
        expected = compute_fact_id(fact_content(fact))
        if fact.fact_id != expected:
            problems.append("`fact_id` 이(가) 내용과 맞지 않음")
    return problems


def validate_derived(derived):
    problems = []
    if not isinstance(derived, DerivedFact):
        return ["계산 결과가 DerivedFact 가 아님"]
    if not isinstance(derived.formula_id, str) or not re.fullmatch(r"F\d{2}[a-z]?_[a-z_]+", derived.formula_id):
        problems.append("`formula_id` 이(가) 계산식 번호 모양이 아님")
    if not isinstance(derived.input_fact_ids, tuple) or not derived.input_fact_ids \
            or not all(isinstance(i, str) and ID_RE.fullmatch(i) and i[0] in "fd" for i in derived.input_fact_ids):
        problems.append("`input_fact_ids` 이(가) 입력 id 의 비지 않은 튜플이 아님")
    if not isinstance(derived.value, Decimal) or not derived.value.is_finite():
        problems.append("`value` 이(가) 유한한 Decimal 이 아님(계산 결과는 값이 있어야 한다)")
    if not isinstance(derived.unit, str) or not _UNIT_RE.fullmatch(derived.unit):
        problems.append("`unit` 이(가) 없거나 형식이 맞지 않음")
    if derived.as_of is not None and parse_as_of(derived.as_of) is None:
        problems.append("`as_of` 이(가) 기준일 형식이 아님")
    if not problems and derived.fact_id != content_digest("d", derived_content(derived)):
        problems.append("`fact_id` 이(가) 내용과 맞지 않음")
    return problems


def record_expired(record, today):
    """보관 기한이 지났는가: 수집일 + retention_days < 오늘. retention_days 가 없으면 기한 없음(False). today 는 date 또는 ISO 날짜 글자."""
    if record.retention_days is None:
        return False
    started = period_start(parse_as_of(record.retrieved_at))
    return started + datetime.timedelta(days=record.retention_days) < as_date(today)


def as_date(value):
    """datetime.date 나 'YYYY-MM-DD' 글자를 date 로(시계를 읽지 않는다). 아니면 FactFormatError."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    period = parse_as_of(value)
    if period is None or period.granularity != "day":
        raise FactFormatError(["오늘 날짜 형식이 맞지 않음"])
    return period_start(period)


def validate_bundle(bundle):
    """개별 검증에 더해 서로의 참조(출처 기록·입력 id·Provider 일치)와 id 중복을 본다."""
    problems = []
    records = {}
    for record in bundle.records:
        found = validate_record(record)
        problems += [f"출처 기록 {record.record_id[:6] if isinstance(record, SourceRecord) else '?'}: {p}" for p in found]
        if isinstance(record, SourceRecord):
            if record.record_id in records:
                problems.append("출처 기록 id 가 중복됨")
            records[record.record_id] = record
    seen = {}
    for fact in bundle.facts:
        found = validate_fact(fact)
        problems += [f"Fact {fact.fact_id[:6] if isinstance(fact, Fact) else '?'}: {p}" for p in found]
        if not isinstance(fact, Fact):
            continue
        if fact.fact_id in seen:
            problems.append("Fact id 가 중복됨")
        seen[fact.fact_id] = fact
        record = records.get(fact.source_record_id)
        if record is None:
            problems.append(f"Fact {fact.fact_id[:6]}: 출처 기록 `source_record_id` 이(가) 묶음에 없음")
        elif record.provider_id != fact.provider_id:
            problems.append(f"Fact {fact.fact_id[:6]}: Provider 가 출처 기록과 다름")
    known = set(seen)
    for derived in bundle.derived:
        found = validate_derived(derived)
        problems += [f"계산 결과 {derived.fact_id[:6] if isinstance(derived, DerivedFact) else '?'}: {p}" for p in found]
        if isinstance(derived, DerivedFact):
            if derived.fact_id in known:
                problems.append("계산 결과 id 가 Fact id 와 겹치거나 중복됨")
            known.add(derived.fact_id)
    for derived in bundle.derived:
        if isinstance(derived, DerivedFact):
            missing = [i for i in derived.input_fact_ids if i not in known]
            if missing:
                problems.append(f"계산 결과 {derived.fact_id[:6]}: 입력 id 가 묶음에 없음")
    return problems


# ----------------------------------------------------------------------------
# JSON 쓰고 읽기(결정적). 값은 문자열로 적는다 — 읽을 때 실수(float)를 거치지 않는다
# ----------------------------------------------------------------------------
_RECORD_KEYS = ("record_id", "provider_id", "access_kind", "request_url", "retrieved_at", "response_hash", "license_snapshot", "retention_days")
_RECORD_REQUIRED = ("record_id", "provider_id", "access_kind", "request_url", "retrieved_at", "response_hash", "license_snapshot")
_FACT_KEYS = tuple(f.name for f in fields(Fact))
_FACT_REQUIRED = ("fact_id", "provider_id", "source_record_id", "kind", "key", "value")
_DERIVED_KEYS = tuple(f.name for f in fields(DerivedFact))
_DERIVED_REQUIRED = ("fact_id", "formula_id", "input_fact_ids", "value", "unit")


def record_to_dict(record):
    return {name: getattr(record, name) for name in _RECORD_KEYS}


def fact_to_dict(fact):
    data = {name: getattr(fact, name) for name in _FACT_KEYS}
    data["value"] = _value_text(fact.value)
    if fact.meta is None:
        del data["meta"]                                    # 꼬리표가 없는 Fact 의 JSON 은 꼬리표가 생기기 전과 바이트까지 같다
    else:
        data["meta"] = {name: value for name, value in fact.meta}
    return data


def derived_to_dict(derived):
    data = {name: getattr(derived, name) for name in _DERIVED_KEYS}
    data["value"] = canonical_number(derived.value)
    data["input_fact_ids"] = list(derived.input_fact_ids)
    return data


def _dict_problems(data, allowed, required, label):
    if not isinstance(data, dict):
        return [f"{label}: 객체(사전)가 아님"]
    problems = [f"{label}: 필수 칸 `{name}` 이(가) 없음" for name in required if name not in data]
    problems += [f"{label}: 알 수 없는 칸이 있음" for name in sorted(set(data) - set(allowed))[:1]]
    return problems


def record_from_dict(data):
    problems = _dict_problems(data, _RECORD_KEYS, _RECORD_REQUIRED, "출처 기록")
    if problems:
        raise FactFormatError(problems)
    record = SourceRecord(**{name: data.get(name) for name in _RECORD_KEYS})
    problems = validate_record(record)
    if problems:
        raise FactFormatError(problems)
    return record


def fact_from_dict(data):
    problems = _dict_problems(data, _FACT_KEYS, _FACT_REQUIRED, "Fact")
    if problems:
        raise FactFormatError(problems)
    values = {name: data.get(name) for name in _FACT_KEYS}
    kind = values["kind"]
    if kind in NUMERIC_KINDS and values["value"] is not None:
        if not isinstance(values["value"], str):
            raise FactFormatError(["Fact: 숫자 값은 문자열로 적혀 있어야 함"])
        values["value"] = to_decimal(values["value"])
    if values["meta"] is not None:
        if not isinstance(values["meta"], dict):
            raise FactFormatError(["Fact: 꼬리표(meta)는 사전이어야 함"])
        values["meta"] = normalize_meta(values["meta"])
    fact = Fact(**values)
    problems = validate_fact(fact)
    if problems:
        raise FactFormatError(problems)
    return fact


def derived_from_dict(data):
    problems = _dict_problems(data, _DERIVED_KEYS, _DERIVED_REQUIRED, "계산 결과")
    if problems:
        raise FactFormatError(problems)
    values = {name: data.get(name) for name in _DERIVED_KEYS}
    if not isinstance(values["value"], str) or not isinstance(values["input_fact_ids"], list):
        raise FactFormatError(["계산 결과: 값은 문자열, 입력 id 는 목록이어야 함"])
    values["value"] = to_decimal(values["value"])
    values["input_fact_ids"] = tuple(values["input_fact_ids"])
    derived = DerivedFact(**values)
    problems = validate_derived(derived)
    if problems:
        raise FactFormatError(problems)
    return derived


def dumps_bundle(bundle):
    """묶음을 정렬된 JSON 한 줄로(같은 내용이면 바이트까지 같다)."""
    return canonical_json({
        "schema": SCHEMA_VERSION,
        "records": sorted((record_to_dict(r) for r in bundle.records), key=lambda d: d["record_id"]),
        "facts": sorted((fact_to_dict(f) for f in bundle.facts), key=lambda d: d["fact_id"]),
        "derived": sorted((derived_to_dict(d) for d in bundle.derived), key=lambda d: d["fact_id"]),
    })


def _no_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise FactFormatError(["JSON 객체에 같은 키가 두 번 나옴"])
        seen[key] = value
    return seen


def loads_bundle(text):
    """JSON 글을 묶음으로 읽는다. 필수 칸 누락·형식 오류·참조 불일치는 FactFormatError(problems)."""
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys, parse_float=_reject_number,
                          parse_constant=_reject_number)
    except FactFormatError:
        raise
    except (ValueError, RecursionError):
        raise FactFormatError(["JSON 으로 읽을 수 없음"]) from None
    problems = _dict_problems(data, ("schema", "records", "facts", "derived"), ("schema", "records", "facts"), "묶음")
    if problems:
        raise FactFormatError(problems)
    if data["schema"] != SCHEMA_VERSION:
        raise FactFormatError(["묶음: 알 수 없는 schema 버전"])
    for name in ("records", "facts", "derived"):
        if name in data and not isinstance(data[name], list):
            raise FactFormatError([f"묶음: `{name}` 은(는) 목록이어야 함"])
    bundle = FactBundle(tuple(record_from_dict(d) for d in data["records"]), tuple(fact_from_dict(d) for d in data["facts"]),
                        tuple(derived_from_dict(d) for d in data.get("derived", [])))
    problems = validate_bundle(bundle)
    if problems:
        raise FactFormatError(problems)
    return bundle


def _reject_number(_text):
    raise FactFormatError(["JSON 에 실수·무한·NaN 이 있음(값은 문자열로 적어야 한다 — 실수 변환을 거치지 않는다)"])


# ----------------------------------------------------------------------------
# 참조 표시와 렌더링
# ----------------------------------------------------------------------------
# 종류: F 값+단위(날짜·글자 종류는 그 값) · S 부호 있는 값+단위 · A 크기(절댓값)+단위 · V 값만 · U 단위 · D 기준일 · L 낱말 라벨 · R 지역 낱말 · T 수집일(출처 기록)
MARKER_KINDS = "FSAVUDLRT"
REF_RE = re.compile("⟦([" + MARKER_KINDS + r"]):([A-Za-z0-9_]{1,64})⟧")
# 우리말 수 표현 — 틀에 쓰지 않는다('두 배·세 곳·열두 곳·삼 분기·절반·수십·두어 곳'). 흔한 낱말(조건·이번·사건·세대·열대·일명·만원·프로그램 …)을 수로 잡지 않도록 구조로 가른다(재검증 D8, D-154):
#  - 왼쪽 경계: 앞 글자가 한글·영문·숫자가 아니어야 한다('강남구 개발' 의 구, 'A사 번호' 의 사 같은 낱말 끝 글자는 수가 아니다).
#  - 오른쪽 경계: 세는 말 뒤에 한글이 더 이어지면 조사·어미로 시작할 때만 센다('세 곳이'·'두 배로'·'네 곳에서는' 은 잡고 '일 개선'·'한 프로그램'·'일일 건수' 는 놓친다).
#    어미에는 서술격 '이다' 의 꼴이 든다(N2, S2a): 받침 있는 세는 말 뒤는 `이다`·`입니다`·`일 때`·`인데` 로, 받침 없는 세는 말 뒤는 `이` 가 줄어 `다·면·며·죠·든·예요·요·고·지·야` 가 바로 붙는다
#    ('세 곳인데'·'세 곳일 때'·'두 가지다'·'한 해다'·'세 가지면'·'두 가지예요'). 줄어든 꼴은 받침 없는 세는 말 뒤에서만 센다('한 번지'·'한 살다'·'한 분야' 의 번·살·분 은 받침이 있다).
#    '세는 말 + 어미' 가 흔한 낱말이 되는 짝은 센 말에서 뺀다('한 개인'·'한 주인'·'한 해고'·'한 해지'·'한 대지'·'한 대야'·'한 배지'·'한 개요'·'한 주요' — 이때 `인` 은 인데·인지·인가·인걸·인즉 일 때만 센다).
#  - 한 글자 수(한·두·세·네·열, 일·삼·사·오·십·백·천·만 …)는 세는 말과 붙여 쓴 꼴이 흔한 낱말과 겹치므로(세대·열대·두건·사건·조건·일개·오명·만원) 띄어 쓴 꼴은 모든 세는 말과, 붙여 쓴 꼴은 겹치지 않는
#    세는 말(곳·개·번·명·가지·개월·퍼센트 …)만 본다. 두 글자 이상 수(열두·스물·다섯·이십·오륙 …)는 붙여 쓴 꼴도 모두 본다. 지시어 `이`(이 곳·이 점·이 번호)는 한 글자 수로 보지 않는다.
#  - 수 글자로만 된 흔한 낱말(사이·이사·일일·만일·일이 …)은 두 글자 이상 수에서 뺀다.
_NUM_LEFT = r"(?<![가-힣A-Za-z0-9])"
_NUM_PARTICLES = "이가은는을를의에로도만와과나라씩째쯤간뿐입였일으부까보마처밖"      # 조사, 그리고 서술격 '이다' 의 어미 이·입·였·일 로 시작하면 센다
# 받침 없이 끝나는 세는 말(가지·개·해·배·마리·군데·나라·자리·대·호·주·위·번째·차례·단계·분기·가구·학교·퍼센트·포인트·프로·달러·세·이하·초과·초)의 끝 글자 — 시험이 세는 말 목록과 맞춰 본다
_NUM_OPEN = "개해배지리데라대호주위례계기구교트로러세하과째초"
# '이다' 가 줄어 받침 없는 말에 바로 붙는 꼴과, 그 꼴이 흔한 낱말과 겹치는 짝(해고·배고프다 / 해지·대지·주지·배지 / 해야·대야·주야 / 개요·해요·주요·대요·세요)
_NUM_SHORT_COPULA = r"다|면|며|죠|든|예요|(?<![개해주대세])요|(?<![해배])고|(?<![해대주배])지|(?<![해대주])야"
# 세는 말 뒤의 `인`(인데·인지·인가): '개인·주인·살인·달인·위인·대인·원인' 처럼 '세는 말 + 인' 이 흔한 낱말이 되는 끝 글자 뒤에서는 인데·인지·인가·인걸·인즉 일 때만 센다
_NUM_IN_WORDS = "개주살달위대원"
_NUM_RIGHT = (rf"(?:(?![가-힣])|(?=(?:[{_NUM_PARTICLES}]|(?<![{_NUM_IN_WORDS}])인|(?<=[{_NUM_IN_WORDS}])인(?=[데지가걸즉])"
              rf"|(?<=[{_NUM_OPEN}])(?:{_NUM_SHORT_COPULA}))[가-힣]{{0,3}}(?![가-힣])))")
_NATIVE_TENS = "열|스물|스무|서른|마흔|예순|일흔|여든|아흔"
_NATIVE_UNITS = "한|두|세|네|다섯|여섯|일곱|여덟|아홉"
# 두 글자 이상(쉰은 한 글자지만 흔한 낱말과 겹치지 않아 여기 둔다): 열두·열다섯·스물세·서른아홉·스무·다섯·여덟, 대략 수 두어·두세. `두어`·`두세` 는 세는 말이 뒤따를 때만 센다(알아 두세요·그대로 두어 의 동사는 수가 아니다)
_NATIVE_LONG = (rf"(?:(?:{_NATIVE_TENS})(?:{_NATIVE_UNITS})|스물|스무|서른|마흔|쉰|예순|일흔|여든|아흔|다섯|여섯|일곱|여덟|아홉"
                r"|두어|두세)")
_NATIVE_SHORT = "한|두|세|네|열|석|넉"
# 구간·줄·열·날(S2AFIX D12)은 띄어 쓴 꼴만 센다(붙인 꼴은 `_NATIVE_SAFE` 밖). 한 글자 수 `한` 뒤의 `날` 은 아래 정규식에서 뺀다 — '게시를 한 날'·'작업을 한 날' 처럼 하다 의 관형형이 앞에 오는 흔한 말이라서(말뭉치에서 확인).
_NATIVE_COUNTERS = ("개월|번째|퍼센트포인트|퍼센트|분기|주일|자리|지역|기간|구간|차례|단계|가지|군데|마리|사람|가구|학급|학교|기관|나라|시간|곳|개|번|해|달|주|명|건|위|대|호|살|배|줄|열|날")
# 한 글자 순우리말 수와 붙여 써도 흔한 낱말과 겹치지 않는 세는 말(세대·열대·두건·한해·한주·세배 는 빠진다)
_NATIVE_SAFE = "개월|번째|퍼센트|분기|자리|차례|단계|가지|군데|마리|사람|가구|시간|곳|개|번|달|명|살"
_SINO_DIGITS = "영일이삼사오육륙칠팔구십백천만억조"
_SINO_SHORT = "영일삼사오육칠팔구십백천만억조"            # 지시어와 겹치는 `이` 는 한 글자 수에서 뺀다
_SINO_STOP = "사이|이사|구이|오이|일일|일이|만일|만조|백조|조사|구조|영구"      # 수 글자로만 된 흔한 낱말(조사원·조사일·구조 위·영구 단계 …)
_SINO_RUN = rf"(?!(?:{_SINO_STOP}))[{_SINO_DIGITS}]{{2,}}"          # 흔한 낱말로 시작하는 수 글자 덩어리는 수가 아니다(세는 말이 수 글자이기도 한 `조사일`·`구조일` 도)
_SINO_COUNTERS = "퍼센트포인트|퍼센트|프로|포인트|개월|분기|번째|차례|단계|이하|이상|미만|초과|달러|%|곳|개|명|건|위|번|세|살|원|배|년|일|점|분|초"
# 한 글자 한자어 수와 붙여 써도 흔한 낱말과 겹치지 않는 세는 말('백퍼센트·십프로·삼개월·사분기' 는 잡고 '조건·사건·만원·일개·구원' 은 놓친다)
_SINO_SAFE = "퍼센트포인트|퍼센트|프로|포인트|개월|분기|달러|%"
_NUMBER_WORDS = (r"둘째|셋째|넷째|다섯째|여섯째|일곱째|여덟째|아홉째|열째|첫째|첫|절반|반절|반 ?토막|곱절|갑절|서너|두서너|한두|너덧|너더댓|네댓|대여섯|예닐곱|여남은"
                 r"|서넛|한둘|두셋|두엇|여럿"
                 r"|십중팔구|삼삼오오|하나둘|하나하나|하나같이|이틀|사흘|나흘|닷새|엿새|이레|여드레|아흐레|열흘"
                 r"|수십|수백|수천|수억|몇몇|몇|영하|열에 ?(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉)|반 ?(?:이상|이하|미만|초과)")
_ENGLISH_NUMBER_WORDS = ("one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand|million|billion|half|double|triple|twice|thrice|zero|dozen")
_NUMWORD_RE = re.compile("|".join((
    rf"{_NUM_LEFT}(?:{_NATIVE_LONG})[ ]?(?:{_NATIVE_COUNTERS}){_NUM_RIGHT}",
    rf"{_NUM_LEFT}(?!한 날)(?:{_NATIVE_SHORT}) (?:{_NATIVE_COUNTERS}){_NUM_RIGHT}",        # 열한 날·스물한 날 은 위 줄에서 센다
    rf"{_NUM_LEFT}(?:{_NATIVE_SHORT})(?:{_NATIVE_SAFE}){_NUM_RIGHT}",
    rf"{_NUM_LEFT}(?:두|네|열)배{_NUM_RIGHT}",
    rf"{_NUM_LEFT}{_SINO_RUN}[ ]?(?:{_SINO_COUNTERS}){_NUM_RIGHT}",
    rf"{_NUM_LEFT}[{_SINO_SHORT}] (?:{_SINO_COUNTERS}){_NUM_RIGHT}",
    rf"{_NUM_LEFT}[{_SINO_SHORT}](?:{_SINO_SAFE}){_NUM_RIGHT}",
    rf"{_NUM_LEFT}[십백천만억조]배{_NUM_RIGHT}",
    rf"{_NUM_LEFT}[{_SINO_DIGITS}][ ]?분의[ ]?[{_SINO_DIGITS}]{_NUM_RIGHT}",
    rf"{_NUM_LEFT}(?:{_NUMBER_WORDS})",
    rf"{_NUM_LEFT}수[십백천만억]{{1,2}}여?[ ]?(?:{_SINO_COUNTERS}|{_NATIVE_COUNTERS}){_NUM_RIGHT}",        # 수만 은 '글자 수만' 의 수+만 과 겹쳐 세는 말이 뒤따를 때만
    rf"{_NUM_LEFT}(?:하나(?!은행|님|금융|카드|증권|로마트)|(?:둘|셋|넷|제로)(?![가-힣]))",        # 하나 는 뒤가 무엇이든 센다(하나의·하나만·하나라도). 둘·셋·넷·제로 는 뒤에 한글이 붙지 않을 때만(둘의 차이·셋팅·제로섬 은 수가 아니다)
    rf"(?<![A-Za-z0-9])(?i:{_ENGLISH_NUMBER_WORDS})(?![A-Za-z0-9])",
)))
FORBIDDEN_TEMPLATE_CHARS = ("{{", "{%", "%}", "}}")
# 숫자가 들었지만 주장이 아닌 굳은 말('제3자'·공공누리 '제1유형' 같은 이용 조건 용어) — 숫자 검사에서 뺀다
_FIXED_NUMERIC_TERMS = re.compile(r"제3자|제[1-4]유형")


def strip_fixed_numeric_terms(text):
    return _FIXED_NUMERIC_TERMS.sub(" ", text)


def make_ref(kind, ref):
    if kind not in MARKER_KINDS or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", ref):
        raise TemplateError(["참조 표시의 종류나 이름이 맞지 않음"])
    return f"⟦{kind}:{ref}⟧"


def references(template):
    """틀에 든 참조 표시를 차례로 [(종류, 이름)]."""
    return [(m.group(1), m.group(2)) for m in REF_RE.finditer(template)]


def untraced_numbers(template):
    """틀에서 참조 표시 밖에 있는 숫자 글자(아라비아·전각·원 숫자·분수·한자 숫자)와 '두 배·세 곳' 같은 우리말 수 표현을 찾는다. 없으면 빈 목록 — 숫자는 모두 Fact 에서 와야 한다."""
    text = strip_fixed_numeric_terms(REF_RE.sub("", template))
    found, run = [], []
    for ch in text:
        if ch.isnumeric():
            run.append(ch)
        elif run:
            found.append("".join(run))
            run = []
    if run:
        found.append("".join(run))
    found += [m.group(0) for m in _NUMWORD_RE.finditer(text)]
    return found


def bind(template, slots):
    """틀의 칸 이름을 실제 id 로 바꾼다. slots 는 {칸 이름: 객체(Fact·DerivedFact·SourceRecord)}. 이미 id 모양인 참조는 그대로 둔다.
    묶이지 않은 칸 이름이 있으면 UnboundSlot."""
    def swap(match):
        kind, name = match.group(1), match.group(2)
        if name in slots:
            target = slots[name]
            ident = getattr(target, "fact_id", None) or getattr(target, "record_id", None)
            return make_ref(kind, ident)
        if ID_RE.fullmatch(name):
            return match.group(0)
        raise UnboundSlot(f"묶이지 않은 칸 이름: {name}")
    return REF_RE.sub(swap, template)


def _index(objects):
    if isinstance(objects, Mapping):
        return dict(objects)
    index = {}
    for obj in objects:
        ident = getattr(obj, "fact_id", None) or getattr(obj, "record_id", None)
        if ident is None:
            raise UnknownReference("id 가 없는 객체")
        if ident in index and index[ident] != obj:
            raise UnknownReference("같은 id 에 다른 객체가 있음")
        index[ident] = obj
    return index


def _numeric_value(obj, ref):
    numeric = isinstance(obj, DerivedFact) or (isinstance(obj, Fact) and obj.kind in NUMERIC_KINDS)
    if not numeric:
        raise TemplateError([f"숫자 표시가 숫자가 아닌 대상을 가리킴: {ref}"])
    if obj.value is None:
        raise MissingValue(f"값이 없는(모름) Fact 를 글자로 바꿀 수 없음: {ref}")
    return obj.value


def render_marker(kind, ref, obj, context=None):
    """표시 하나를 글자로. 값이 없는 Fact 는 MissingValue(0 으로 채우지 않는다). context 는 `display_context` 가 만든 {단위: 소수 자리}."""
    if kind == "T":
        if not isinstance(obj, SourceRecord):
            raise TemplateError([f"수집일 표시가 출처 기록을 가리키지 않음: {ref}"])
        return format_period_ko(obj.retrieved_at[:10])
    if isinstance(obj, SourceRecord):
        raise TemplateError([f"출처 기록은 수집일(T) 표시로만 쓸 수 있음: {ref}"])
    if kind == "D":
        if obj.as_of is None:
            raise MissingValue(f"기준일이 없는 대상: {ref}")
        return format_period_ko(obj.as_of)
    if kind == "L":
        text = getattr(obj, "label_ko", None)
        if not text:
            raise TemplateError([f"낱말 라벨이 없는 대상: {ref}"])
        return text
    if kind == "R":
        text = getattr(obj, "region_label_ko", None)
        if not text:
            raise TemplateError([f"지역 낱말이 없는 대상: {ref}"])
        return text
    if kind == "U":
        if not isinstance(obj, DerivedFact) and obj.kind not in NUMERIC_KINDS:
            raise TemplateError([f"단위가 없는 대상: {ref}"])
        return obj.unit
    if kind == "F" and isinstance(obj, Fact) and obj.kind not in NUMERIC_KINDS:
        if obj.value is None:
            raise MissingValue(f"값이 없는(모름) Fact 를 글자로 바꿀 수 없음: {ref}")
        if obj.kind in DATE_KINDS:
            return format_date_ko(obj.value)
        if obj.kind == KIND_DATETIME:
            return format_period_ko(obj.value)
        return obj.value
    _numeric_value(obj, ref)
    if kind == "F":
        return format_object(obj, context=context)
    if kind == "S":
        return format_object(obj, signed=True, context=context)
    if kind == "A":
        return format_object(obj, absolute=True, context=context)
    if kind == "V":
        return format_decimal(obj.value, decimals_of(obj, context))
    raise TemplateError([f"알 수 없는 표시 종류: {kind}"])


@exact
def render(template, facts, *, context=None):
    """틀을 글로 바꾼다. facts 는 {id: 객체} 이거나 객체의 나열, context 는 `display_context` 가 만든 {단위: 소수 자리}(없으면 단위 표의 자리).
    참조 없는 숫자가 있으면 UntracedNumber, 모르는 id 면 UnknownReference. 렌더링 결과에 표시 문자(⟦ ⟧)나 Liquid 문자가 남으면 TemplateError."""
    numbers = untraced_numbers(template)
    if numbers:
        raise UntracedNumber(numbers)
    index = _index(facts)

    def swap(match):
        kind, ref = match.group(1), match.group(2)
        if ref not in index:
            raise UnknownReference(f"참조가 가리키는 대상이 없음: {ref}")
        return render_marker(kind, ref, index[ref], context)

    out = REF_RE.sub(swap, template)
    if any(mark in out for mark in _MARKERS):
        raise TemplateError(["렌더링 뒤에 표시 문자가 남음(닫히지 않았거나 알 수 없는 표시)"])
    if any(bad in out for bad in FORBIDDEN_TEMPLATE_CHARS):
        raise TemplateError(["렌더링 결과에 Liquid 문자가 있음"])
    return out


@exact
def describe(obj, context=None):
    """근거 텍스트용 한 줄: 낱말 · 지역 · 기준일 · 값. 본문에 나온 값과 같은 글자 모양을 쓴다(Gate 가 글자로 견준다). id·해시 같은 내부 번호는 싣지 않는다."""
    parts = []
    label = getattr(obj, "label_ko", None)
    if label:
        parts.append(label)
    region = getattr(obj, "region_label_ko", None)
    if region:
        parts.append(region)
    if obj.as_of:
        parts.append(format_period_ko(obj.as_of))
    if obj.value is None:
        parts.append("값 없음(모름)")
    elif isinstance(obj, DerivedFact) or obj.kind in NUMERIC_KINDS:
        parts.append(format_object(obj, context=context))
    elif obj.kind in DATE_KINDS:
        parts.append(format_date_ko(obj.value))
    elif obj.kind == KIND_DATETIME:
        parts.append(format_period_ko(obj.value))
    else:
        parts.append(str(obj.value))
    return " | ".join(parts)


# ----------------------------------------------------------------------------
# SRC(허용 목록) 인터페이스 약속 — 최소 모양의 프로토콜(덕 타이핑). SRC 의 모듈을 import 하지 않는다
# ----------------------------------------------------------------------------
@runtime_checkable
class ProviderLike(Protocol):
    """`Registry.get(provider_id)` 가 돌려주는 객체의 최소 모양(읽기 전용 필드).
    선택 필드(없어도 글이 된다 — 프로토콜에는 올리지 않는다): `name`, `enabled`(있고 True 가 아니면 켜지지 않은 Provider), `reader_notes`(독자에게 보일 수 있게 승인된 숫자 없는 짧은 문장 목록, 기본 비어 있음).
    SRC 의 `exceptions` 는 약관 감사 메모라 독자용 문장이 아니다 — 이 경로는 읽지 않는다(D-138)."""
    provider_id: str
    strict_tier: int
    effective_status: str
    access: Sequence[Any]
    attribution_template: Optional[str]
    snapshot: Any
    policy: Any
    retention_days: Optional[int]


@runtime_checkable
class RegistryLike(Protocol):
    """`Registry` 의 최소 모양."""

    def get(self, provider_id): ...

    def active_providers(self): ...

    def is_url_allowed(self, url, purpose): ...


@runtime_checkable
class Opener(Protocol):
    """주입되는 네트워크 열기 함수의 모양. 어댑터는 이것으로만 바이트를 얻는다(직접 urlopen 을 부르지 않는다 — SRC 의 관문이 나중에 감싼다)."""

    def __call__(self, url, *, timeout, max_bytes): ...


PROVIDER_FIELDS = ("provider_id", "strict_tier", "effective_status", "access", "attribution_template", "snapshot", "policy", "retention_days")


def field_of(obj, name, default=None):
    """사전이든 객체든 같은 방식으로 필드를 읽는다(SRC 의 Provider 는 읽기 전용 객체, 시험용 가짜는 사전일 수 있다)."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def provider_problems(provider):
    """Provider 같은 객체가 약속한 필드를 갖췄는지."""
    problems = [f"Provider 에 `{name}` 필드가 없음" for name in PROVIDER_FIELDS if field_of(provider, name, _MISSING) is _MISSING]
    if problems:
        return problems
    tier = field_of(provider, "strict_tier")
    if isinstance(tier, bool) or not isinstance(tier, int) or not 0 <= tier <= 4:
        problems.append("`strict_tier` 이(가) 0-4 정수가 아님")
    if not isinstance(field_of(provider, "effective_status"), str):
        problems.append("`effective_status` 이(가) 글자가 아님")
    return problems


_MISSING = object()


def provider_active_problem(provider):
    """조립기가 한 번 더 보는 방어선(관문 ①이 이미 걸렀어야 한다): 자동화 가능 상태이고 Tier 가 허용 안인지, 그리고 Provider 에 선택 필드 `enabled` 가 있으면 켜져 있는지
    (SRC 의 Provider 는 `enabled` 가 거짓이면 라벨이 '자동화 가능'이어도 꺼진 것이다 — D-139). 문제 사유 글자 또는 None."""
    problems = provider_problems(provider)
    if problems:
        return problems[0]
    if field_of(provider, "effective_status") != ACTIVE_STATUS:
        return "Provider 의 상태가 '자동화 가능'이 아님"
    if field_of(provider, "strict_tier") > MAX_ACTIVE_TIER:
        return "Provider 의 strict_tier 가 허용 안(2 이하)이 아님"
    enabled = field_of(provider, "enabled", _MISSING)
    if enabled is not _MISSING and enabled is not True:
        return "Provider 가 켜져 있지 않음(enabled)"
    return None


def snapshot_text(provider):
    """수집 기록에 남기는 '그때의 이용 조건 요약' 글자(결정적): Tier·상태와 Snapshot 의 약관 페이지 이름·열람일·해시·기한."""
    snap = field_of(provider, "snapshot", None)
    parts = [f"tier={field_of(provider, 'strict_tier')}", f"status={field_of(provider, 'effective_status')}"]
    if snap is not None:
        pages = field_of(snap, "terms_pages", None) or ()
        if isinstance(pages, str):
            pages = (pages,)
        parts.append("terms=" + ",".join(str(p) for p in pages))
        for name in ("read_at", "content_hash", "expires_at"):
            value = field_of(snap, name, None)
            parts.append(f"{name}={value if value else '-'}")
    return "; ".join(parts)[:600]


def source_domain(url):
    """주소의 호스트(소문자). https 주소가 아니면 None."""
    match = re.fullmatch(r"https://([A-Za-z0-9.\-]+)(?::\d{1,5})?(?:/.*)?", url or "")
    return match.group(1).lower() if match else None


def iter_facts(items):
    """나열에서 Fact 만 꺼낸다(정렬하지 않는다)."""
    return [item for item in items if isinstance(item, Fact)]


def sorted_facts(items):
    """fact_id 순으로 정렬한 Fact 목록 — 입력 순서가 달라도 결과가 같게 하는 데 쓴다."""
    return sorted(iter_facts(items), key=lambda fact: fact.fact_id)

