"""시험용 가짜 Provider `mock_stats` — 오프라인 고정 데이터를 JSON·CSV 로 돌려주는 가짜 opener 와 어댑터. 표준 라이브러리만, 시계·난수·네트워크 없음.

**실제 기관의 이름·주소·자료가 아니다.** 호스트는 예약된 최상위 도메인(`.invalid`)이라 어디에도 연결되지 않고, 지역 이름·수치는 모두 시험을 위해 만든 값이다.
여섯 개 가상 지역 × 열다섯 달(2025년 1월부터 2026년 3월) 시계열 두 계열(`unemp` 실업률 %, `jobs` 취업자 수 명)을 담고, 일부러 이런 모양을 넣었다:
최신 달에 자료 기간 최고인 지역(R01)·최저인 지역(R02)·직전 달과 같은 지역(R03)·한 달이 비어 있는(모름) 지역(R06).

이 모듈은 어댑터 계약(`pipeline/adapters/base.py`)을 시험하고 조립기(`pipeline/fact_assembler.py`)의 골든 글을 만드는 데 쓴다. 운영 경로에서 부르지 않는다.
"""
from dataclasses import dataclass
from decimal import Decimal
import json
import re

from pipeline import facts as F
from pipeline.adapters.base import AdapterError, StructuredAdapter

PROVIDER_ID = "mock_stats"
API_HOST = "stats.mock.invalid"
API_PATH = "/v1/series"
CSV_PATH = "/v1/series.csv"
SOURCE_NAME = "시험용 가상 통계"
SOURCE_URL = "https://stats.mock.invalid/data/labour"
API_VERSION = "v1"

# 우리가 정한 낱말 표(제공처의 설명 문장이 아니다): 계열 코드 → (키, 한국어 라벨, 영어 라벨, 단위)
SERIES = {
    "unemp": ("labour.unemployment_rate", "실업률", "unemployment rate", "%"),
    "jobs": ("labour.employed_persons", "취업자 수", "employed persons", "명"),
}
# 지역 코드 → (한국어 이름, 영어 이름). 모두 가상이다
REGIONS = {
    "R01": ("가상 지역 가", "Mock Region A"),
    "R02": ("가상 지역 나", "Mock Region B"),
    "R03": ("가상 지역 다", "Mock Region C"),
    "R04": ("가상 지역 라", "Mock Region D"),
    "R05": ("가상 지역 마", "Mock Region E"),
    "R06": ("가상 지역 바", "Mock Region F"),
}
REGION_LEVEL = "province"

PERIODS = tuple(f"2025-{m:02d}" for m in range(1, 13)) + ("2026-01", "2026-02", "2026-03")

_UNEMP = {
    "R01": ("3.4", "3.3", "3.3", "3.2", "3.1", "3.0", "3.0", "2.9", "2.9", "3.0", "3.1", "3.2", "3.3", "3.2", "3.5"),
    "R02": ("4.1", "4.0", "4.0", "3.9", "3.8", "3.8", "3.7", "3.7", "3.6", "3.6", "3.5", "3.5", "3.4", "3.4", "3.3"),
    "R03": ("2.8", "2.8", "2.9", "2.9", "3.0", "3.0", "3.1", "3.1", "3.0", "3.0", "2.9", "2.9", "2.8", "2.9", "2.9"),
    "R04": ("3.9", "3.8", "3.8", "3.7", "3.7", "3.6", "3.6", "3.5", "3.5", "3.4", "3.5", "3.6", "3.7", "3.8", "3.8"),
    "R05": ("5.0", "4.9", "4.9", "4.8", "4.7", "4.7", "4.6", "4.6", "4.5", "4.5", "4.4", "4.4", "4.3", "4.2", "4.2"),
    "R06": ("2.5", "2.5", "2.6", "2.6", "2.7", "2.7", "2.8", "2.8", None, "2.7", "2.7", "2.6", "2.6", "2.6", "2.7"),
}
_JOBS_BASE = {"R01": 1204000, "R02": 986500, "R03": 742300}


def _jobs(region, index):
    """취업자 수: 기준값에서 달마다 조금씩 늘고 작은 출렁임이 있는 정수(난수 없이 정수 산식으로)."""
    return str(_JOBS_BASE[region] + 850 * index + ((index * index) % 7 - 3) * 410)


def dataset_rows():
    """고정 데이터 전체를 [{계열, 지역, 기간, 값}] 로(값은 글자나 None). 항상 같은 순서·같은 값이다."""
    rows = []
    for series in ("unemp", "jobs"):
        regions = _UNEMP if series == "unemp" else _JOBS_BASE
        for region in sorted(regions):
            for index, period in enumerate(PERIODS):
                value = _UNEMP[region][index] if series == "unemp" else _jobs(region, index)
                rows.append({"series": series, "region": region, "period": period, "value": value})
    return rows


def _filtered(query):
    wanted = {}
    for part in (query or "").lstrip("?").split("&"):
        if "=" in part:
            name, value = part.split("=", 1)
            wanted[name] = value
    return [row for row in dataset_rows() if all(row.get(name) == value for name, value in wanted.items())]


def json_payload(rows=None):
    """가짜 제공처의 JSON 응답 바이트(값은 숫자 또는 null)."""
    out = []
    for row in rows if rows is not None else dataset_rows():
        value = row["value"]
        out.append({"series": row["series"], "region": row["region"], "period": row["period"],
                    "value": None if value is None else (float(value) if "." in value else int(value))})
    return json.dumps({"api_version": API_VERSION, "rows": out}, ensure_ascii=False, sort_keys=True).encode("utf-8")


def csv_payload(rows=None):
    """가짜 제공처의 CSV 응답 바이트(빈 칸은 값 없음)."""
    lines = ["series,region,period,value"]
    for row in rows if rows is not None else dataset_rows():
        lines.append(",".join((row["series"], row["region"], row["period"], row["value"] or "")))
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_mock_opener(*, calls=None, overrides=None):
    """오프라인 가짜 opener(`opener(url, timeout=…, max_bytes=…) -> bytes`). 네트워크를 쓰지 않는다. calls 목록을 주면 부른 주소를 쌓고,
    overrides({경로: 바이트})로 일부러 망가뜨린 응답을 끼울 수 있다. 모르는 경로는 OSError 로 실패한다."""
    def opener(url, *, timeout, max_bytes):
        if calls is not None:
            calls.append(url)
        match = re.fullmatch(r"https://" + re.escape(API_HOST) + r"(/[^?]*)(?:\?(.*))?", url)
        if not match:
            raise OSError("가짜 opener: 알 수 없는 주소")
        path, query = match.group(1), match.group(2)
        if overrides and path in overrides:
            return overrides[path]
        if path == API_PATH:
            return json_payload(_filtered(query))
        if path == CSV_PATH:
            return csv_payload(_filtered(query))
        raise OSError("가짜 opener: 알 수 없는 경로")
    return opener


@dataclass(frozen=True)
class MockAccess:
    kind: str
    hosts: tuple
    paths: tuple
    auth: str = "none"
    rate_limit: str = "시험용 — 호출 없음"
    robots_checked_at: str = "2026-11-09"


@dataclass(frozen=True)
class MockSnapshot:
    terms_pages: tuple = ("시험용 가상 통계 이용 안내",)
    read_at: str = "2026-11-09"
    content_hash: str = ""
    expires_at: str = "2027-02-07"


@dataclass(frozen=True)
class MockProvider:
    """SRC 의 Provider 와 같은 읽기 전용 필드를 가진 시험용 객체(덕 타이핑). `name`·`reader_notes` 는 조립기가 쓰는 선택 칸이고, `exceptions` 는 SRC 와 같은 모양의 감사 메모(약관 확인 기록)다 —
    조립기는 이것을 글에 옮기지 않는다(독자용 문장은 `reader_notes` 뿐, D-138)."""
    provider_id: str = PROVIDER_ID
    strict_tier: int = 2
    effective_status: str = "자동화 가능"
    access: tuple = (MockAccess("api", (API_HOST,), (API_PATH,)), MockAccess("csv", (API_HOST,), (CSV_PATH,)))
    attribution_template: str = "이 자료는 시험을 위해 만든 가상의 통계입니다. 실제 기관의 통계가 아닙니다."
    snapshot: MockSnapshot = MockSnapshot()
    policy: tuple = ()
    retention_days: int = 365
    exceptions: tuple = ("시험용 감사 메모: 이용 조건 원문은 2026-10-26 자료 기준이며 오늘 다시 확인하지 못함",)
    reader_notes: tuple = ("제3자 자료와 이미지는 이 이용 허락에 포함되지 않습니다",)
    name: str = SOURCE_NAME


class MockStatsAdapter(StructuredAdapter):
    """`mock_stats` 의 어댑터: JSON(api)과 CSV(csv)를 같은 Fact 로 읽는다. 라벨은 위의 낱말 표에서만 온다."""
    allowed_params = frozenset({"series", "region"})

    def build_facts(self, decoded, record, retrieved_at):
        if record.access_kind == "csv":
            rows, version = decoded, None
        else:
            if not isinstance(decoded, dict) or set(decoded) != {"api_version", "rows"} or not isinstance(decoded["rows"], list) \
                    or not isinstance(decoded["api_version"], str):
                raise AdapterError("BAD_SHAPE")
            rows, version = decoded["rows"], decoded["api_version"]
        if len(rows) > self.max_rows:
            raise AdapterError("TOO_MANY_ROWS")
        facts, seen = [], set()
        if version is not None:
            facts.append(F.Fact.create(PROVIDER_ID, record.record_id, F.KIND_API_VERSION, "meta.api_version", version, as_of=retrieved_at[:10]))
        for number, row in enumerate(rows, start=1):
            fact = self._fact_from_row(row, record, number)
            identity = (row["series"], row["region"], row["period"])
            if identity in seen:
                raise AdapterError("DUPLICATE_ROW", f"행 {number}")
            seen.add(identity)
            facts.append(fact)
        return facts

    def _fact_from_row(self, row, record, number):
        if not isinstance(row, dict) or set(row) != {"series", "region", "period", "value"}:
            raise AdapterError("BAD_ROW", f"행 {number}")
        series, region, period, raw = row["series"], row["region"], row["period"], row["value"]
        if not isinstance(series, str) or series not in SERIES:
            raise AdapterError("UNKNOWN_SERIES", f"행 {number}")
        if not isinstance(region, str) or region not in REGIONS:
            raise AdapterError("UNKNOWN_REGION", f"행 {number}")
        parsed = F.parse_as_of(period) if isinstance(period, str) else None
        if parsed is None or parsed.granularity != "month":
            raise AdapterError("BAD_ROW", f"행 {number}")
        value = self._value(raw, number)
        key, label_ko, label_en, unit = SERIES[series]
        region_ko, region_en = REGIONS[region]
        return F.Fact.create(PROVIDER_ID, record.record_id, F.KIND_OBSERVATION, key, value, unit=unit, as_of=period, region=region,
                             region_level=REGION_LEVEL, region_label_ko=region_ko, region_label_en=region_en, label_ko=label_ko, label_en=label_en)

    @staticmethod
    def _value(raw, number):
        if raw is None or raw == "":
            return None      # 비어 있는 칸은 '모름'이다 — 0 으로 채우지 않는다
        if isinstance(raw, bool) or not isinstance(raw, (Decimal, str)):
            raise AdapterError("BAD_ROW", f"행 {number}")
        try:
            return F.to_decimal(raw)
        except F.FactFormatError:
            raise AdapterError("BAD_ROW", f"행 {number}") from None
