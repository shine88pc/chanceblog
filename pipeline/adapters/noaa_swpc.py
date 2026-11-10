"""NOAA 우주기상예측센터(SWPC) JSON 데이터 서비스 어댑터 — **네트워크 없는 순수 파서**(S2a). 표준 라이브러리와 이 경로의 모듈만 쓰고 시계·난수·환경 변수·직접 네트워크 호출이 없다.

제품 여섯 개를 읽는다(NOAA 가 만든 값만, 필드 화이트리스트). 모르는 모양·바뀐 필드 이름·형·시각 형식은 그 제품을 `BAD_SHAPE` 로 거절한다(실패 시 닫힘 — 2026년 3월 JSON 구조가
바뀐 전례가 있다):

| 제품 | 읽는 필드 | Fact 키(범주 `space_weather`) |
|---|---|---|
| `kp_estimated` 행성 Kp 3시간 추정 | `time_tag`·`Kp`(`a_running`·`station_count` 는 검증만) | `kp_estimated` · 기준값 `kp_storm_threshold` |
| `kp_outlook` Kp 예보 포함 | `time_tag`·`kp`·`observed`·`noaa_scale` | `kp_estimated`(관측 구간) · `kp_outlook`(추정·예보 구간) · `interval_scale_observed`·`interval_scale_outlook` · 기준값 |
| `scales` NOAA 우주기상 등급 | 전체(따옴표 문자열·null) | `daily_scale_*`(어제·지금) · `outlook_scale_geomagnetic`·`outlook_prob_*`(향후 3일) |
| `ssn_daily` SWPC 일별 흑점수 | `Obsdate`·`swpc_ssn` | `sunspot_daily_swpc`(최근 400일) |
| `ssn_monthly` 월별 태양주기 지수 | `time-tag`·`observed_swpc_ssn`·`smoothed_swpc_ssn` **만** — 제3자 필드(`ssn`·`smoothed_ssn`·`f10.7`·`smoothed_f10.7`)는 값을 읽지도 Fact 로 만들지도 않는다 | `sunspot_monthly_swpc`·`sunspot_monthly_smoothed_swpc`(최근 60개월) |
| `xray_flares` GOES X선 플레어 7일 | `max_time`·`max_class`·`satellite`(나머지는 칸 이름만 확인) | `xray_flare_class`·`xray_flare_flux` · 기준값 `xray_class_floor_*` |

처리 규칙: 시각은 모두 UTC 로 고정(시간대 표기가 없는 시각은 UTC 로 보고 `Z` 를 붙인다) · 결측(null·-1·-1.0·SWPC 일별 흑점수의 '레코드 없음')은 값 없음(`None`, 0 이 아니다)으로 통일하고
평균·개수에서 빠진다 · **문자열 '0' 은 결측이 아니라 값 0 이다**(등급 0 = 없음 — 결측은 null) · 시각으로 정렬하고 같은 시각이 두 번이면 `DUPLICATE_ROW` · 관측 구간이 수집 시각보다 뒤이면 `BAD_SHAPE` ·
모든 Fact 에 꼬리표(`meta`)를 붙인다: `producer=NOAA`(값을 만든 기관)·`status`(observed 관측·estimated 추정·predicted 예보·reference 기준값)·필요하면 `quality=provisional`(월별 최근 6개월 잠정치)·
`satellite`(플레어를 기록한 위성)·`stations`(Kp 를 낸 관측소 수). **예보·추정 구간은 관측과 다른 키(`kp_outlook`)로 나뉘어** 관측 계열에 섞이지 않는다.
기준값 Fact(`status=reference`)는 응답이 아니라 우리 낱말 표(NOAA 지자기 폭풍 첫 등급 = Kp 5, X선 등급의 하한)에서 온 값으로, 개수를 셀 때 어떤 기준으로 셌는지 입력 id 에 남기려고 같은 수집 기록에 붙인다.

계약은 `pipeline/adapters/base.py` 를 따른다: `fetch` 는 주입된 opener 로만 바이트를 얻고(관문은 SRC2 가 병합한 뒤 S2b 가 연결한다) `parse` 는 `(SourceRecord, [Fact])` 를 돌려준다.
어댑터는 요청 경로를 제품 하나로 못박고 호스트가 `services.swpc.noaa.gov` 가 아니면 `BAD_ACCESS` 로 거부한다. 설명: docs/FACT_PATH.md §14
"""
import re
from dataclasses import dataclass
from decimal import Decimal

from pipeline import facts as F
from pipeline.adapters.base import AdapterError, MAX_RESPONSE_BYTES, MAX_ROWS, StructuredAdapter

PRODUCER = "NOAA"
HOST = "services.swpc.noaa.gov"
FUTURE_SKEW_SECONDS = 900             # 서버와 우리 시계가 어긋나도 관측 구간이 '미래'로 거절되지 않는 여유
OUTLOOK_PAST_DAYS = 400               # 예보 파일의 시각이 수집 시각에서 이만큼보다 더 과거이면 정상 자료가 아니다
OUTLOOK_FUTURE_DAYS = 30              # …이만큼보다 더 미래여도 마찬가지(예보는 3일치)
SSN_DAILY_KEEP_DAYS = 400             # 일별 흑점수: 가장 최근 날짜에서 이 일수 안의 기록만 Fact 로
SSN_MONTHLY_KEEP_MONTHS = 60          # 월별 지수: 가장 최근 달에서 이 개월 수 안의 기록만 Fact 로
PROVISIONAL_MONTHS = 6                # 월별 지수의 최근 이 개월은 잠정치
KP_STORM_THRESHOLD = Decimal(5)       # NOAA 지자기 폭풍 첫 등급(G1)에 해당하는 Kp — 기준값 Fact 의 값(우리 낱말 표)
STATUS_OBSERVED, STATUS_ESTIMATED, STATUS_PREDICTED, STATUS_REFERENCE = "observed", "estimated", "predicted", "reference"

# Kp 는 0–9 의 3분의 1 단위(0.33·0.67·1.00 …) 28개 값뿐이다 — 아닌 값이 오면 형식이 바뀐 것으로 본다
KP_THIRDS = frozenset(Decimal(f"{n / 3:.2f}") for n in range(28))
FLARE_CLASS_RE = re.compile(r"([ABCMX])([1-9][0-9]?(?:\.[0-9])?)")
FLARE_EXPONENT = {"A": 1, "B": 2, "C": 3, "M": 4, "X": 5}        # 등급 1.0 의 세기 = 10 의 이 제곱 nW/㎡ (A1.0 = 10, M1.0 = 10,000)
FLARE_FLOORS = (("a", "A급"), ("b", "B급"), ("c", "C급"), ("m", "M급"), ("x", "X급"))
SCALE_G_RE = re.compile(r"G[1-5]")
_NAIVE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}")
_ZULU_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_MIDNIGHT_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T00:00:00")
_CLOCK_RE = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]")
_DIGITS_RE = re.compile(r"[0-9]{1,3}")

# 우리가 정한 낱말 표(제공처의 설명 문장이 아니다): 키 → (한국어 라벨, 영어 라벨, 단위). 영어 라벨에는 허용 목록이 막는 낱말(forecast·predict)을 쓰지 않는다
_BASE_LABELS = {
    "kp_estimated": ("NOAA 추정 Kp", "NOAA estimated Kp", "Kp"),
    "kp_outlook": ("NOAA Kp 예보", "NOAA Kp outlook", "Kp"),
    "interval_scale_observed": ("NOAA 지자기 폭풍 등급", "NOAA geomagnetic storm scale", "단계"),
    "interval_scale_outlook": ("NOAA 지자기 폭풍 등급 예보", "NOAA geomagnetic storm scale outlook", "단계"),
    "daily_scale_radio": ("NOAA 전파 교란 등급", "NOAA radio blackout scale", "단계"),
    "daily_scale_radiation": ("NOAA 방사선 폭풍 등급", "NOAA radiation storm scale", "단계"),
    "daily_scale_geomagnetic": ("NOAA 지자기 폭풍 등급", "NOAA geomagnetic storm scale", "단계"),
    "outlook_scale_geomagnetic": ("NOAA 지자기 폭풍 등급 예보", "NOAA geomagnetic storm scale outlook", "단계"),
    "outlook_prob_radio_minor": ("NOAA 전파 교란 낮은 등급 확률", "NOAA radio blackout lower scale probability", "%"),
    "outlook_prob_radio_major": ("NOAA 전파 교란 높은 등급 확률", "NOAA radio blackout higher scale probability", "%"),
    "outlook_prob_radiation": ("NOAA 방사선 폭풍 확률 예보", "NOAA radiation storm probability outlook", "%"),
    "sunspot_daily_swpc": ("SWPC 일별 흑점수", "SWPC daily sunspot number", "개"),
    "sunspot_monthly_swpc": ("SWPC 월평균 흑점수", "SWPC monthly sunspot number", "개"),
    "sunspot_monthly_smoothed_swpc": ("SWPC 월평균 흑점수 평활", "SWPC smoothed monthly sunspot number", "개"),
    "xray_flare_class": ("GOES X선 플레어 등급", "GOES X-ray flare class", None),
    "xray_flare_flux": ("GOES X선 플레어 세기", "GOES X-ray flare peak flux", "nW/㎡"),
    "kp_storm_threshold": ("지자기 폭풍 기준", "geomagnetic storm threshold", "Kp"),
}
LABELS = {**_BASE_LABELS, **{f"xray_class_floor_{suffix}": (f"GOES X선 {word} 하한", f"GOES X-ray {suffix.upper()} class floor", "nW/㎡") for suffix, word in FLARE_FLOORS}}


@dataclass(frozen=True)
class Product:
    """제품 하나: 요청 경로·글에 밝힐 공식 데이터 이름(괄호·콜론·슬래시 없음)·원자료 행 수 상한(응답 전체 행 — 쓰는 기간만 Fact 가 된다)."""
    product_id: str
    path: str
    source_name: str
    raw_max_rows: int


PRODUCTS = {
    "kp_estimated": Product("kp_estimated", "/products/noaa-planetary-k-index.json", "NOAA SWPC 행성 K 지수 추정값", 500),
    "kp_outlook": Product("kp_outlook", "/products/noaa-planetary-k-index-forecast.json", "NOAA SWPC 행성 K 지수 예보 포함", 500),
    "scales": Product("scales", "/products/noaa-scales.json", "NOAA 우주기상 등급 현황", 5),
    "ssn_daily": Product("ssn_daily", "/json/solar-cycle/swpc_observed_ssn.json", "NOAA SWPC 일별 흑점수", 30000),
    "ssn_monthly": Product("ssn_monthly", "/json/solar-cycle/observed-solar-cycle-indices.json", "NOAA SWPC 월별 태양주기 지수", 6000),
    "xray_flares": Product("xray_flares", "/json/goes/primary/xray-flares-7-day.json", "NOAA GOES X선 플레어 목록", 3000),
}
PRODUCT_IDS = tuple(PRODUCTS)

KP_KEYS = frozenset({"time_tag", "Kp", "a_running", "station_count"})
OUTLOOK_KEYS = frozenset({"time_tag", "kp", "observed", "noaa_scale"})
SCALE_DAYS = ("-1", "0", "1", "2", "3")
SCALE_ENTRY_KEYS = frozenset({"DateStamp", "TimeStamp", "R", "S", "G"})
SCALE_R_KEYS = frozenset({"Scale", "Text", "MinorProb", "MajorProb"})
SCALE_S_KEYS = frozenset({"Scale", "Text", "Prob"})
SCALE_G_KEYS = frozenset({"Scale", "Text"})
SSN_DAILY_KEYS = frozenset({"Obsdate", "swpc_ssn"})
SSN_MONTHLY_REQUIRED = frozenset({"time-tag", "observed_swpc_ssn", "smoothed_swpc_ssn"})
SSN_MONTHLY_IGNORED = frozenset({"ssn", "smoothed_ssn", "f10.7", "smoothed_f10.7"})          # 제3자 필드 — 이름만 알고 값은 읽지 않는다
FLARE_KEYS = frozenset({"time_tag", "begin_time", "begin_class", "max_time", "max_class", "max_xrlong", "max_ratio", "max_ratio_time", "current_int_xrlong",
                        "end_time", "end_class", "satellite"})
OUTLOOK_STATUS_RANK = {"observed": 0, "estimated": 1, "predicted": 2}


def product_source_name(product_id):
    """글에 밝히는 공식 데이터 이름(`SourceInfo.name`). 모르는 제품이면 KeyError."""
    return PRODUCTS[product_id].source_name


def product_url(product_id):
    """제품 파일의 https 주소(`SourceInfo.url`) — 호스트는 허용 목록의 호스트 그대로다."""
    return "https://" + HOST + PRODUCTS[product_id].path


# ----------------------------------------------------------------------------
# 읽기 도우미 — 모두 BAD_SHAPE 로 닫는다(문구에 값·주소를 싣지 않는다: 행 번호뿐)
# ----------------------------------------------------------------------------
def _bad(number=None, detail=None):
    return AdapterError("BAD_SHAPE", f"행 {number}" if number is not None else (detail or ""))


def _rows(decoded, limit):
    """최상위가 비지 않은 목록이고 행 수가 상한 안인지(Fact 를 만들기 전에 본다 — D-128)."""
    if not isinstance(decoded, list) or not decoded:
        raise AdapterError("BAD_SHAPE")
    if len(decoded) > limit:
        raise AdapterError("TOO_MANY_ROWS")
    return decoded


def _exact_keys(row, expected, number):
    if not isinstance(row, dict) or set(row) != expected:
        raise _bad(number)


def _naive_instant(raw, number):
    """시간대 표기 없는 `YYYY-MM-DDTHH:MM:SS` → UTC 로 고정한 `…Z` 글자. 다른 모양(시간대가 붙음 등)은 형식이 바뀐 것이라 거절."""
    if not isinstance(raw, str) or not _NAIVE_RE.fullmatch(raw) or F.parse_as_of(raw + "Z") is None:
        raise _bad(number)
    return raw + "Z"


def _zulu_instant(raw, number):
    if not isinstance(raw, str) or not _ZULU_RE.fullmatch(raw) or F.parse_as_of(raw) is None:
        raise _bad(number)
    return raw


def _day(raw, number):
    period = F.parse_as_of(raw) if isinstance(raw, str) else None
    if period is None or period.granularity != "day":
        raise _bad(number)
    return raw


def _number(raw, number, *, low, high, integer=False, text=False):
    """원자료 값 → Decimal 또는 None(결측: null·-1·-1.0). 불리언·모양이 다른 글·범위 밖·정수여야 하는데 소수는 BAD_SHAPE. `text` 이면 따옴표 문자열 숫자만, 아니면 JSON 숫자만 받는다."""
    if raw is None:
        return None
    if text:
        if not isinstance(raw, str) or not _DIGITS_RE.fullmatch(raw):
            raise _bad(number)
        value = Decimal(raw)
    else:
        if isinstance(raw, bool) or not isinstance(raw, Decimal):
            raise _bad(number)
        value = raw
    if not text and value == -1:
        return None
    if value < low or value > high or (integer and value != value.to_integral_value()):
        raise _bad(number)
    return value


def _kp_value(raw, number):
    value = _number(raw, number, low=0, high=9)
    if value is not None and value not in KP_THIRDS:
        raise _bad(number)
    return value


def _clock(retrieved_at):
    """수집 시각 → (UTC 초, UTC 날짜 글자, 그 날짜의 일 서수, 그 달의 월 서수)."""
    period = F.parse_as_of(retrieved_at)
    day = F.utc_day_of(period)
    return period.ordinal, day, F.parse_as_of(day).ordinal, F.parse_as_of(day[:7]).ordinal


def _unique(seen, ordinal, number):
    if ordinal in seen:
        raise AdapterError("DUPLICATE_ROW", f"행 {number}")
    seen.add(ordinal)


def _meta(status, **extra):
    pairs = {"producer": PRODUCER, "status": status}
    pairs.update({name: value for name, value in extra.items() if value is not None})
    return pairs


class NoaaSwpcAdapter(StructuredAdapter):
    """제품 하나를 읽는 어댑터(`NoaaSwpcAdapter(provider, "kp_estimated")`). 요청 경로는 제품이 정하고 허용 목록의 `paths`(접두어)가 그 경로를 덮어야 한다.
    행 수 상한은 두 가지다 — `raw_max_rows`(응답 전체 행: 일별 흑점수는 1만 줄 가까이)와 `max_rows`(만들어지는 Fact 수)."""
    allowed_params = frozenset()

    def __init__(self, provider, product_id, *, max_bytes=None, max_rows=None):
        product = PRODUCTS.get(product_id) if isinstance(product_id, str) else None
        if product is None:
            raise AdapterError("BAD_PARAMS")
        super().__init__(provider, max_bytes=MAX_RESPONSE_BYTES if max_bytes is None else max_bytes, max_rows=MAX_ROWS if max_rows is None else max_rows)
        self.product = product
        self.raw_max_rows = product.raw_max_rows if max_rows is None else max_rows

    def _access_parts(self, access):
        kind = F.field_of(access, "kind")
        hosts, paths = F.field_of(access, "hosts") or (), F.field_of(access, "paths") or ()
        if kind not in F.STRUCTURED_ACCESS_KINDS:
            raise AdapterError("NOT_STRUCTURED")
        if kind != "api" or not hosts or hosts[0] != HOST or any(not isinstance(path, str) for path in paths):
            raise AdapterError("BAD_ACCESS")
        if paths and not any(self.product.path.startswith(path) for path in paths):
            raise AdapterError("BAD_ACCESS")                 # 허용 목록의 경로(접두어)가 이 제품의 파일을 덮지 않으면 요청하지 않는다
        return kind, HOST, self.product.path

    @F.exact
    def parse(self, raw, access, retrieved_at, params=None):
        return super().parse(raw, access, retrieved_at, params)

    def build_facts(self, decoded, record, retrieved_at):
        return PARSERS[self.product.product_id](self, decoded, record, retrieved_at)

    def make_fact(self, record, kind, key, value, as_of, meta):
        label_ko, label_en, unit = LABELS[key]
        return F.Fact.create(self.provider_id, record.record_id, kind, "space_weather." + key, value, unit=unit, as_of=as_of, label_ko=label_ko, label_en=label_en, meta=meta)

    def kp_threshold_fact(self, record, today_text):
        """기준값 Fact: 지자기 폭풍 첫 등급에 해당하는 Kp(우리 낱말 표). 수집일을 기준일로 달고 `status=reference` 로 표시한다."""
        return self.make_fact(record, F.KIND_NUMBER, "kp_storm_threshold", KP_STORM_THRESHOLD, today_text, _meta(STATUS_REFERENCE))

    def flare_floor_facts(self, record, today_text):
        facts = []
        for suffix, _word in FLARE_FLOORS:
            letter = suffix.upper()
            facts.append(self.make_fact(record, F.KIND_NUMBER, f"xray_class_floor_{suffix}", Decimal(10) ** FLARE_EXPONENT[letter], today_text, _meta(STATUS_REFERENCE)))
        return facts


# ----------------------------------------------------------------------------
# 제품별 파서 — (어댑터, 읽은 구조, 수집 기록, 수집 시각) → Fact 목록
# ----------------------------------------------------------------------------
def _parse_kp_estimated(adapter, decoded, record, retrieved_at):
    rows = _rows(decoded, adapter.raw_max_rows)
    now, today_text, _day_ordinal, _month_ordinal = _clock(retrieved_at)
    seen, parsed = set(), []
    for number, row in enumerate(rows, start=1):
        _exact_keys(row, KP_KEYS, number)
        as_of = _naive_instant(row["time_tag"], number)
        ordinal = F.parse_as_of(as_of).ordinal
        _unique(seen, ordinal, number)
        if ordinal > now + FUTURE_SKEW_SECONDS:
            raise _bad(number)                                   # 아직 시작하지 않은 구간이 '추정'으로 와 있다 — 정상 자료가 아니다
        value = _kp_value(row["Kp"], number)
        _number(row["a_running"], number, low=0, high=400, integer=True)           # 검증만 한다(쓰지 않는다)
        stations = _number(row["station_count"], number, low=0, high=50, integer=True)
        parsed.append((ordinal, as_of, value, stations))
    parsed.sort(key=lambda item: item[0])
    facts = [adapter.make_fact(record, F.KIND_OBSERVATION, "kp_estimated", value, as_of,
                               _meta(STATUS_OBSERVED, stations=None if stations is None else str(int(stations))))
             for _ordinal, as_of, value, stations in parsed]
    facts.append(adapter.kp_threshold_fact(record, today_text))
    return facts


def _parse_kp_outlook(adapter, decoded, record, retrieved_at):
    rows = _rows(decoded, adapter.raw_max_rows)
    now, today_text, _day_ordinal, _month_ordinal = _clock(retrieved_at)
    seen, parsed = set(), []
    for number, row in enumerate(rows, start=1):
        _exact_keys(row, OUTLOOK_KEYS, number)
        as_of = _naive_instant(row["time_tag"], number)
        ordinal = F.parse_as_of(as_of).ordinal
        _unique(seen, ordinal, number)
        status = row["observed"]
        if not isinstance(status, str) or status not in OUTLOOK_STATUS_RANK:
            raise _bad(number)
        if ordinal < now - OUTLOOK_PAST_DAYS * 86400 or ordinal > now + OUTLOOK_FUTURE_DAYS * 86400 or (status == STATUS_OBSERVED and ordinal > now + FUTURE_SKEW_SECONDS):
            raise _bad(number)                                   # 관측이라는 구간이 미래이거나 시각이 말이 안 되는 범위다
        label = row["noaa_scale"]
        if label is not None and (not isinstance(label, str) or not SCALE_G_RE.fullmatch(label)):
            raise _bad(number)
        parsed.append((ordinal, as_of, _kp_value(row["kp"], number), status, label))
    parsed.sort(key=lambda item: item[0])
    ranks = [OUTLOOK_STATUS_RANK[item[3]] for item in parsed]
    if ranks != sorted(ranks):
        raise AdapterError("BAD_SHAPE")                          # 예보 구간이 관측 구간보다 앞서 있으면 관측·예보를 가를 수 없다
    facts = []
    for _ordinal, as_of, value, status, label in parsed:
        measured = status == STATUS_OBSERVED
        facts.append(adapter.make_fact(record, F.KIND_OBSERVATION, "kp_estimated" if measured else "kp_outlook", value, as_of, _meta(status)))
        if label is not None:
            facts.append(adapter.make_fact(record, F.KIND_OBSERVATION, "interval_scale_observed" if measured else "interval_scale_outlook",
                                           Decimal(label[1]), as_of, _meta(status)))
    facts.append(adapter.kp_threshold_fact(record, today_text))
    return facts


def _scale_block(block, expected, number):
    if not isinstance(block, dict) or set(block) != expected:
        raise _bad(number)
    for name in expected:
        if block[name] is not None and not isinstance(block[name], str):
            raise _bad(number)                                   # 이 파일의 값은 전부 따옴표 문자열이거나 null 이다
    return block


def _parse_scales(adapter, decoded, record, retrieved_at):
    if not isinstance(decoded, dict) or set(decoded) != set(SCALE_DAYS):
        raise AdapterError("BAD_SHAPE")
    now, _today_text, today_ordinal, _month_ordinal = _clock(retrieved_at)
    entries, days = {}, []
    for number, name in enumerate(SCALE_DAYS, start=1):
        entry = decoded[name]
        if not isinstance(entry, dict) or set(entry) != SCALE_ENTRY_KEYS:
            raise _bad(number)
        day = _day(entry["DateStamp"], number)
        stamp = entry["TimeStamp"]
        if not isinstance(stamp, str) or not _CLOCK_RE.fullmatch(stamp):
            raise _bad(number)
        days.append(F.parse_as_of(day).ordinal)
        entries[name] = (day, _scale_block(entry["R"], SCALE_R_KEYS, number), _scale_block(entry["S"], SCALE_S_KEYS, number), _scale_block(entry["G"], SCALE_G_KEYS, number), number)
    if days != sorted(days) or not today_ordinal - 1 <= days[1] <= today_ordinal + 1:
        raise AdapterError("BAD_SHAPE")                          # 날짜가 거꾸로이거나 '지금' 칸이 수집일과 하루 넘게 어긋난 오래된 파일
    facts = []
    for name in ("-1", "0"):                                     # 관측: 어제·지금의 등급 단계
        day, block_r, block_s, block_g, number = entries[name]
        for key, block in (("daily_scale_radio", block_r), ("daily_scale_radiation", block_s), ("daily_scale_geomagnetic", block_g)):
            facts.append(adapter.make_fact(record, F.KIND_OBSERVATION, key, _number(block["Scale"], number, low=0, high=5, integer=True, text=True), day, _meta(STATUS_OBSERVED)))
    for name in ("1", "2", "3"):                                 # 예보: 지자기 폭풍 등급과 전파 교란·방사선 폭풍 확률(R·S 의 단계 칸은 예보에서 비어 있다)
        day, block_r, block_s, block_g, number = entries[name]
        facts.append(adapter.make_fact(record, F.KIND_OBSERVATION, "outlook_scale_geomagnetic", _number(block_g["Scale"], number, low=0, high=5, integer=True, text=True), day, _meta(STATUS_PREDICTED)))
        for key, raw in (("outlook_prob_radio_minor", block_r["MinorProb"]), ("outlook_prob_radio_major", block_r["MajorProb"]), ("outlook_prob_radiation", block_s["Prob"])):
            facts.append(adapter.make_fact(record, F.KIND_OBSERVATION, key, _number(raw, number, low=0, high=100, integer=True, text=True), day, _meta(STATUS_PREDICTED)))
    return facts


def _parse_ssn_daily(adapter, decoded, record, retrieved_at):
    rows = _rows(decoded, adapter.raw_max_rows)
    _now, _today_text, today_ordinal, _month_ordinal = _clock(retrieved_at)
    seen, parsed = set(), []
    for number, row in enumerate(rows, start=1):
        _exact_keys(row, SSN_DAILY_KEYS, number)
        stamp = row["Obsdate"]
        if not isinstance(stamp, str) or not _MIDNIGHT_RE.fullmatch(stamp):
            raise _bad(number)
        day = _day(stamp[:10], number)
        ordinal = F.parse_as_of(day).ordinal
        _unique(seen, ordinal, number)
        if ordinal >= today_ordinal:
            raise _bad(number)                                   # 오늘 날짜의 일별 값은 아직 끝나지 않은 날이라 완성된 값이 아니다
        parsed.append((ordinal, day, _number(row["swpc_ssn"], number, low=0, high=1000, integer=True)))
    parsed.sort(key=lambda item: item[0])
    floor = parsed[-1][0] - SSN_DAILY_KEEP_DAYS + 1
    return [adapter.make_fact(record, F.KIND_OBSERVATION, "sunspot_daily_swpc", value, day, _meta(STATUS_OBSERVED)) for ordinal, day, value in parsed if ordinal >= floor]


def _parse_ssn_monthly(adapter, decoded, record, retrieved_at):
    rows = _rows(decoded, adapter.raw_max_rows)
    _now, _today_text, _day_ordinal, month_ordinal = _clock(retrieved_at)
    seen, parsed = set(), []
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not SSN_MONTHLY_REQUIRED <= set(row) or set(row) - SSN_MONTHLY_REQUIRED - SSN_MONTHLY_IGNORED:
            raise _bad(number)                                   # 필요한 칸이 없거나 모르는 칸이 있다 — 제3자 필드의 값은 보지 않는다(이름만)
        month = row["time-tag"]
        period = F.parse_as_of(month) if isinstance(month, str) else None
        if period is None or period.granularity != "month":
            raise _bad(number)
        _unique(seen, period.ordinal, number)
        if period.ordinal >= month_ordinal:
            raise _bad(number)                                   # 진행 중인 달(이번 달)의 월평균은 완성된 값이 아니다
        parsed.append((period.ordinal, month, _number(row["observed_swpc_ssn"], number, low=0, high=1000), _number(row["smoothed_swpc_ssn"], number, low=0, high=1000)))
    parsed.sort(key=lambda item: item[0])
    last = parsed[-1][0]
    facts = []
    for ordinal, month, observed, smoothed in parsed:
        if ordinal <= last - SSN_MONTHLY_KEEP_MONTHS:
            continue
        quality = "provisional" if ordinal > last - PROVISIONAL_MONTHS else None
        facts.append(adapter.make_fact(record, F.KIND_OBSERVATION, "sunspot_monthly_swpc", observed, month, _meta(STATUS_OBSERVED, quality=quality)))
        facts.append(adapter.make_fact(record, F.KIND_OBSERVATION, "sunspot_monthly_smoothed_swpc", smoothed, month, _meta(STATUS_OBSERVED, quality=quality)))
    return facts


def _parse_xray_flares(adapter, decoded, record, retrieved_at):
    rows = _rows(decoded, adapter.raw_max_rows)
    now, today_text, _day_ordinal, _month_ordinal = _clock(retrieved_at)
    seen, parsed = set(), []
    for number, row in enumerate(rows, start=1):
        _exact_keys(row, FLARE_KEYS, number)
        as_of = _zulu_instant(row["max_time"], number)
        ordinal = F.parse_as_of(as_of).ordinal
        _unique(seen, ordinal, number)
        if ordinal > now + FUTURE_SKEW_SECONDS:
            raise _bad(number)
        found = FLARE_CLASS_RE.fullmatch(row["max_class"]) if isinstance(row["max_class"], str) else None
        satellite = _number(row["satellite"], number, low=1, high=99, integer=True)
        if found is None or satellite is None:
            raise _bad(number)
        parsed.append((ordinal, as_of, row["max_class"], F.to_decimal(found.group(2)) * Decimal(10) ** FLARE_EXPONENT[found.group(1)], str(int(satellite))))
    parsed.sort(key=lambda item: item[0])
    facts = []
    for _ordinal, as_of, class_text, flux, satellite in parsed:
        meta = _meta(STATUS_OBSERVED, satellite=satellite)
        facts.append(adapter.make_fact(record, F.KIND_CLASS_CODE, "xray_flare_class", class_text, as_of, meta))
        facts.append(adapter.make_fact(record, F.KIND_OBSERVATION, "xray_flare_flux", flux, as_of, meta))
    facts += adapter.flare_floor_facts(record, today_text)
    return facts


PARSERS = {
    "kp_estimated": _parse_kp_estimated,
    "kp_outlook": _parse_kp_outlook,
    "scales": _parse_scales,
    "ssn_daily": _parse_ssn_daily,
    "ssn_monthly": _parse_ssn_monthly,
    "xray_flares": _parse_xray_flares,
}
