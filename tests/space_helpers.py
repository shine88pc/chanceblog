"""우주날씨(NOAA SWPC) 어댑터·지역 없는 글 틀 시험의 공통 도구. 네트워크·시계 없음 — 응답은 `tests/fixtures/noaa_swpc/` 의 표본(실제 응답을 앞 12건 + 뒤 3건으로 줄인 것)이거나
**시험용으로 만든 가상 값**(`synthetic_*` — NOAA 자료가 아니다, 모양만 같다)이고, 가상 값도 진짜 어댑터를 거쳐 Fact 가 된다(운영과 같은 Fact 모양).

고정 시각은 시험이 정한다: 수집 2026-11-10T01:10:00Z, 오늘 2026-11-10.
"""
import dataclasses
import datetime
import functools
import json
import random
from dataclasses import dataclass

import _bootstrap  # noqa: F401

from pipeline import fact_assembler as A
from pipeline import facts as F
from pipeline import recipes as R
from pipeline import recipes_noregion as RN
from pipeline.adapters import noaa_swpc as N

FIXTURE_DIR = _bootstrap.ROOT / "tests" / "fixtures" / "noaa_swpc"
RETRIEVED_AT = "2026-11-10T01:10:00Z"
TODAY = "2026-11-10"
FIXTURE_FILES = {
    "kp_estimated": "noaa-planetary-k-index.json",
    "kp_outlook": "noaa-planetary-k-index-forecast.json",
    "scales": "noaa-scales.json",
    "ssn_daily": "swpc_observed_ssn.json",
    "ssn_monthly": "observed-solar-cycle-indices.json",
    "xray_flares": "xray-flares-7-day.json",
}
B_TEMPLATE = ("자료: {title}, 미국 NOAA 우주기상예측센터({date} 열람). NOAA 가 만든 이 자료는 미국 연방정부 저작물이라 저작권 보호 대상이 아닙니다. "
              "값을 가공해 더한 계산과 설명은 이 블로그의 것이며 NOAA·미국 정부가 인정하거나 보증한 내용이 아닙니다.")
TEST_TEMPLATE = "이 자료는 시험을 위해 모양만 흉내 낸 가상의 우주날씨 자료입니다. 실제 기관의 자료가 아닙니다."
ALL_PATHS = tuple(product.path for product in N.PRODUCTS.values())


# ----------------------------------------------------------------------------
# 가짜 Provider(레지스트리 모양 — 덕 타이핑)
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Access:
    kind: str
    hosts: tuple
    paths: tuple
    auth: str = "NONE"
    rate_limit: str = "시험용 — 호출 없음"
    robots_checked_at: str = "2026-11-10"


@dataclass(frozen=True)
class Cell:
    state: str
    basis: str = "EXPLICIT"
    evidence: str = "시험용 근거 문서 이름"
    read_at: str = "2026-11-10"


@dataclass(frozen=True)
class Policy:
    """SRC 의 7칸 묶음과 같은 모양: `policy.attribution` 과 `policy["attribution"]` 이 같은 칸."""
    commercial_use: Cell = Cell("ALLOWED")
    automated_access: Cell = Cell("CONDITIONAL")
    derivative_use: Cell = Cell("CONDITIONAL")
    storage: Cell = Cell("ALLOWED", "STATUTE")
    ai_input: Cell = Cell("ALLOWED", "IMPLIED")
    attribution: Cell = Cell("CONDITIONAL")
    license: Cell = Cell("CONDITIONAL", "STATUTE")

    def __getitem__(self, name):
        return getattr(self, name)


@dataclass(frozen=True)
class Snapshot:
    terms_pages: tuple = ("시험용 이용 안내",)
    read_at: str = "2026-11-10"
    content_hash: str = ""
    expires_at: str = "2027-02-08"


@dataclass(frozen=True)
class NoaaProvider:
    """레지스트리의 `noaa_swpc_json` 항목과 같은 모양의 시험용 객체(값은 시험용). 출처 문구 템플릿은 시험용 가상 문구 — 보고서 B안 문구는 시험이 `attribution_template` 로 갈아 끼운다."""
    provider_id: str = "noaa_swpc_json"
    strict_tier: int = 1
    effective_status: str = "자동화 가능"
    access: tuple = (Access("api", (N.HOST,), ALL_PATHS),)
    attribution_template: str = TEST_TEMPLATE
    snapshot: Snapshot = Snapshot()
    policy: Policy = Policy()
    retention_days: object = None
    enabled: bool = True
    own_data_only: bool = True
    ai_use: str = "NEVER"
    reader_notes: tuple = ("이 글은 제공처가 만든 값만 쓰고 제3자가 제공한 지수와 로고·이미지는 쓰지 않았습니다",)
    name: str = "시험용 우주날씨 가상 자료"


def provider(**changes):
    return dataclasses.replace(NoaaProvider(), **changes) if changes else NoaaProvider()


def adapter(product_id, **kw):
    return N.NoaaSwpcAdapter(kw.pop("provider", None) or NoaaProvider(), product_id, **kw)


def access_of(provider_=None):
    return (provider_ or NoaaProvider()).access[0]


def fixture_bytes(name):
    """표본 파일의 바이트. 줄 끝은 LF 로 맞춘다 — 윈도우의 자동 줄바꿈 변환(autocrlf)으로 CRLF 가 된 작업 사본에서도 `provenance.json` 의 sha256(저장소·리눅스의 LF 바이트)과 같게 한다."""
    return (FIXTURE_DIR / name).read_bytes().replace(b"\r\n", b"\n")


def parse_bytes(product_id, raw, *, retrieved_at=RETRIEVED_AT, provider_=None, **kw):
    """어댑터로 바이트를 읽는다 → (SourceRecord, [Fact])."""
    provider_ = provider_ or NoaaProvider()
    return adapter(product_id, provider=provider_, **kw).parse(raw, access_of(provider_), retrieved_at, {})


def parse_fixture(product_id, **kw):
    return parse_bytes(product_id, fixture_bytes(FIXTURE_FILES[product_id]), **kw)


def dumps(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


# ----------------------------------------------------------------------------
# 시험용 가상 응답(모양만 NOAA 응답과 같다) — 고정 시드, 난수는 여기서만
# ----------------------------------------------------------------------------
def _iso_day(ordinal):
    day = datetime.date.fromordinal(ordinal)
    return f"{day.year:04d}-{day.month:02d}-{day.day:02d}"


def day_ordinal(day):
    return F.parse_as_of(day).ordinal


def synthetic_kp_values(count, *, seed=7, storm_days=(), per_day=8):
    """가상 Kp 값(3분의 1 단위, float) count 개. storm_days 는 (처음부터 센 날 번호) 그날 어느 한 구간을 5.33 으로 올린다."""
    rng = random.Random(seed)
    values = []
    for index in range(count):
        step = rng.choice((0, 1, 2, 2, 3, 3, 4, 5, 6, 7, 8))                  # 0–2.67
        values.append(round(step / 3, 2))
    for day in storm_days:
        spot = day * per_day + 3
        if spot < count:
            values[spot] = 5.33
    return values


def kp_rows(first_day, days, *, seed=7, storm_days=(), partial_last=0, keys="estimated", stations=8):
    """3시간 Kp 응답 행(`kp_estimated` 모양 또는 `kp_outlook` 모양). days 일치를 만들고 partial_last>0 이면 마지막 날은 그 구간 수만큼만."""
    base = day_ordinal(first_day)
    count = days * 8
    values = synthetic_kp_values(count, seed=seed, storm_days=storm_days)
    rows = []
    for index in range(count):
        day, slot = divmod(index, 8)
        if partial_last and day == days - 1 and slot >= partial_last:
            break
        stamp = f"{_iso_day(base + day)}T{slot * 3:02d}:00:00"
        if keys == "estimated":
            rows.append({"time_tag": stamp, "Kp": values[index], "a_running": 5, "station_count": stations})
        else:
            rows.append({"time_tag": stamp, "kp": values[index], "observed": "observed", "noaa_scale": "G1" if values[index] >= 5 else None})
    return rows


def synthetic_ssn_values(count, *, seed=11, level=80):
    rng = random.Random(seed)
    out, value = [], level
    for _ in range(count):
        value = max(0, min(400, value + rng.choice((-9, -6, -3, -1, 0, 1, 2, 4, 7, 10))))
        out.append(value)
    return out


def ssn_daily_rows(last_day, count, *, gaps=(), seed=11):
    base = day_ordinal(last_day) - count + 1
    values = synthetic_ssn_values(count, seed=seed)
    return [{"Obsdate": f"{_iso_day(base + index)}T00:00:00", "swpc_ssn": values[index]} for index in range(count) if index not in gaps]


def ssn_daily_rows_from(values, last_day="2026-11-09"):
    """주어진 값(오래된 날부터)으로 만든 일별 흑점수 행 — 마지막 값이 last_day 의 값이다."""
    base = day_ordinal(last_day) - len(values) + 1
    return [{"Obsdate": f"{_iso_day(base + index)}T00:00:00", "swpc_ssn": value} for index, value in enumerate(values)]


def ssn_monthly_rows(last_month, count, *, seed=13, third_party=True):
    year, month = (int(part) for part in last_month.split("-"))
    start = year * 12 + month - 1 - (count - 1)
    values = synthetic_ssn_values(count, seed=seed, level=70)
    rows = []
    for index in range(count):
        total = start + index
        tag = f"{total // 12:04d}-{total % 12 + 1:02d}"
        smoothed = -1.0 if index < 6 or index >= count - 6 else round(sum(values[index - 6:index + 7]) / 13 + 0.05, 2)
        row = {"time-tag": tag, "observed_swpc_ssn": float(values[index]) + 0.25, "smoothed_swpc_ssn": smoothed}
        if third_party:
            row.update({"ssn": float(values[index]) / 2, "smoothed_ssn": -1.0, "f10.7": 100.5, "smoothed_f10.7": -1.0})
        rows.append(row)
    return rows


FLARE_FILLER = {"begin_time": "2026-11-03T06:08:00Z", "begin_class": "B3.3", "max_xrlong": 4.8857e-07, "max_ratio": 4.1, "max_ratio_time": "2026-11-03T06:11:41Z",
                "current_int_xrlong": 0.0003079, "end_time": "2026-11-03T06:19:00Z", "end_class": "B3.9", "satellite": 18}


def flare_rows(events):
    """events: [(UTC 시각 `2026-11-04T06:15:00Z`, 등급 `C1.2`)] → 응답 행."""
    return [dict(FLARE_FILLER, time_tag=stamp, max_time=stamp, max_class=class_text) for stamp, class_text in events]


def scales_object(*, date_now="2026-11-10", g_now="0", r_prob=("60", "15"), s_prob="15", g_forecast=("0", "0", "0"), probs=None):
    """`noaa-scales.json` 모양의 가상 응답. probs 는 {"1": (R낮은, R높은, S), …} 로 날마다 바꿀 때."""
    def day(offset):
        base = day_ordinal(date_now)
        return _iso_day(base + offset)

    def observed(name, offset, scale_g):
        return {"DateStamp": day(offset), "TimeStamp": "00:52:00", "R": {"Scale": "0", "Text": "none", "MinorProb": None, "MajorProb": None},
                "S": {"Scale": "0", "Text": "none", "Prob": None}, "G": {"Scale": scale_g, "Text": "none"}}

    def forecast(name, offset, scale_g):
        minor, major, sprob = (probs or {}).get(name, (r_prob[0], r_prob[1], s_prob))
        return {"DateStamp": day(offset), "TimeStamp": "00:52:00" if offset == 0 else "00:00:00",
                "R": {"Scale": None, "Text": None, "MinorProb": minor, "MajorProb": major}, "S": {"Scale": None, "Text": None, "Prob": sprob}, "G": {"Scale": scale_g, "Text": "none"}}
    return {"-1": observed("-1", -1, "0"), "0": observed("0", 0, g_now), "1": forecast("1", 0, g_forecast[0]), "2": forecast("2", 1, g_forecast[1]), "3": forecast("3", 2, g_forecast[2])}


# ----------------------------------------------------------------------------
# 글 조립 도구
# ----------------------------------------------------------------------------
def source_info(product_id, provider_=None):
    return A.SourceInfo(provider_ or NoaaProvider(), N.product_source_name(product_id), N.product_url(product_id))


def assemble(recipe, product_id, facts, record, *, params=None, today=TODAY, provider_=None):
    recipe = recipe if isinstance(recipe, R.Recipe) else RN.NOREGION_RECIPES[recipe]
    return A.assemble(recipe, facts, today, records=[record], source=source_info(product_id, provider_), params=params)


@functools.lru_cache(maxsize=None)
def cached_parse(product_id, payload_text, retrieved_at=RETRIEVED_AT):
    """같은 가상 응답을 여러 시험이 다시 읽지 않게 하는 캐시(응답은 글자로 받는다)."""
    return parse_bytes(product_id, payload_text.encode("utf-8"), retrieved_at=retrieved_at)


def parse_value(product_id, value, **kw):
    return parse_bytes(product_id, dumps(value), **kw)
