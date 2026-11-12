"""어댑터 계약 — 구조화 응답(JSON·CSV)만 읽는 Provider 어댑터의 공통 뼈대. 표준 라이브러리만, 시계·난수·직접 네트워크 호출 없음.

계약:
- `fetch(access, params, opener) -> bytes`: 네트워크는 **주입된 `opener`** 로만 쓴다(`opener(url, timeout=…, max_bytes=…) -> bytes`). 이 모듈은 `urlopen` 을 부르지도
  `urllib`·`socket`·`http` 를 import 하지도 않는다 — SRC 의 외부 호출 관문이 나중에 `opener` 를 감싸 허용 목록 밖 호스트를 거부한다. 요청 주소는 비밀 없는 https 주소뿐이고(키는 주소에
  넣지 않는다 — 관문이 헤더로 붙인다) 요청 변수는 어댑터가 허용한 이름·안전한 값만 쓴다.
- `parse(raw, access, retrieved_at, params=None) -> (SourceRecord, [Fact])`: 구조화 응답(JSON·CSV)만 읽는다. HTML·RSS 본문 파서는 두지 않는다. 수집 시각 `retrieved_at` 은 인자로 받는다.
  응답 크기·행 수 상한과 형식 오류는 `AdapterError` 로 거부한다. 오류 메시지에는 요청 주소·질의 문자열·토큰·응답 본문을 넣지 않는다(고정 문장과 짧은 코드뿐).
- Fact 의 라벨·지역 낱말은 어댑터가 가진 **우리가 정한 낱말 표**에서 온다(제공처의 설명 문장을 복사하지 않는다). 표에 없는 계열·지역 코드는 거부한다(fail closed).

설명: docs/FACT_PATH.md
"""
import csv
import io
import json
import re
from decimal import Decimal
from typing import Protocol, runtime_checkable

from pipeline import facts as F

MAX_RESPONSE_BYTES = 1_048_576      # 응답 상한(1 MiB). 어댑터마다 더 낮출 수 있다
MAX_ROWS = 5000                     # 행 수 상한
MAX_COLUMNS = 64
FETCH_TIMEOUT_SECONDS = 20

MESSAGES = {
    "NOT_STRUCTURED": "구조화 경로(api·csv·dataset)가 아니라 읽지 않음",
    "BAD_ACCESS": "접근 정보에 호스트나 경로가 없거나 모양이 맞지 않음",
    "BAD_PARAMS": "요청 변수가 허용 목록에 없거나 값이 안전하지 않음",
    "OPENER_FAILED": "응답을 가져오지 못함",
    "BAD_RESPONSE_TYPE": "응답이 바이트가 아님",
    "TOO_LARGE": "응답이 크기 상한을 넘음",
    "BAD_ENCODING": "응답이 UTF-8 글자가 아님",
    "BAD_JSON": "응답이 JSON 으로 읽히지 않음",
    "BAD_CSV": "응답이 CSV 로 읽히지 않음",
    "BAD_SHAPE": "응답의 구조가 약속과 다름",
    "TOO_MANY_ROWS": "행 수가 상한을 넘음",
    "BAD_ROW": "행의 칸이 약속과 다름",
    "UNKNOWN_SERIES": "라벨 표에 없는 계열 코드",
    "UNKNOWN_REGION": "라벨 표에 없는 지역 코드",
    "DUPLICATE_ROW": "같은 계열·지역·기간의 행이 둘 이상 있음",
    "BAD_RETRIEVED_AT": "수집 시각이 시간대 포함 ISO 시각이 아님",
    "BAD_PROVIDER": "Provider 객체가 약속한 필드를 갖추지 않았거나 자동화 가능 상태가 아님",
    "EGRESS_DENIED": "외부 호출 관문이 허용 목록 밖이라 거부함",
    "BUDGET_DENIED": "호출 예산(한 실행의 호출 상한·실패 건너뜀·403·429 중지)이 막아 호출하지 않음",
}
_DETAIL_RE = re.compile(r"[가-힣A-Za-z0-9 _()\-:]{1,40}")


class AdapterError(Exception):
    """어댑터가 응답이나 요청을 거부했다. code 는 짧은 영문 코드. 메시지는 `MESSAGES` 의 고정 문장이고 detail 은 우리 낱말(행 번호·칸 이름)만 — 주소·질의·토큰·응답 본문은 담지 않는다."""

    def __init__(self, code, detail=""):
        self.code = code
        safe = detail if isinstance(detail, str) and _DETAIL_RE.fullmatch(detail) else ""
        super().__init__(f"{code}: {MESSAGES.get(code, '거부됨')}" + (f" ({safe})" if safe else ""))


def _no_constant(_name):
    raise AdapterError("BAD_JSON")


def _no_duplicate_pairs(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise AdapterError("BAD_JSON")
        seen[key] = value
    return seen


def _decode_text(raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise AdapterError("BAD_ENCODING") from None
    return text[1:] if text.startswith("﻿") else text


MAX_JSON_DEPTH = 64


def _too_deep(value, limit=MAX_JSON_DEPTH):
    """중첩 깊이가 limit 를 넘는지 반복문으로 센다. 파이썬 재귀 한계는 버전·운영체제마다 달라(같은 5,000겹 글이 윈도우 3.12 와 3.10 에서는 RecursionError, 리눅스 3.12 에서는 정상 파싱)
    같은 응답이 어디서는 BAD_JSON, 어디서는 구조 오류가 되던 것을 없앤다 — 깊이 상한은 이 숫자 하나로 정해진다."""
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, dict):
            children = item.values()
        elif isinstance(item, list):
            children = item
        else:
            continue
        if depth > limit:
            return True
        stack.extend((child, depth + 1) for child in children if isinstance(child, (dict, list)))
    return False


def decode_json(raw):
    """JSON 바이트를 읽는다. 숫자는 Decimal(실수 변환 없음), 같은 키 두 번·NaN·무한은 거부. `{` 나 `[` 로 시작하지 않는 응답(HTML·XML·글)은 읽지 않는다."""
    text = _decode_text(raw)
    if text.lstrip()[:1] not in ("{", "["):
        raise AdapterError("BAD_JSON")
    try:
        value = json.loads(text, parse_float=Decimal, parse_int=Decimal, parse_constant=_no_constant, object_pairs_hook=_no_duplicate_pairs)
    except AdapterError:
        raise
    except (ValueError, RecursionError, ArithmeticError):        # 아주 큰 지수(`1e99999999999999999999`)는 Decimal 이 InvalidOperation(ArithmeticError 계열)을 올린다 — 이것도 BAD_JSON(S2AFIX D3)
        raise AdapterError("BAD_JSON") from None
    if _too_deep(value):
        raise AdapterError("BAD_JSON")
    return value


def decode_csv(raw, *, max_rows=MAX_ROWS):
    """CSV 바이트를 [{머리글: 값}] 로 읽는다. 첫 줄은 머리글(중복 불가), 모든 행의 칸 수가 머리글과 같아야 한다. `<` 로 시작하는 응답(HTML·XML)은 읽지 않는다."""
    text = _decode_text(raw)
    if not text.strip() or text.lstrip()[:1] == "<":
        raise AdapterError("BAD_CSV")
    rows = []
    try:
        for index, row in enumerate(csv.reader(io.StringIO(text, newline=""), strict=True)):
            if index > max_rows:
                raise AdapterError("TOO_MANY_ROWS")
            rows.append(row)
    except csv.Error:
        raise AdapterError("BAD_CSV") from None
    header = [name.strip() for name in rows[0]]
    if len(header) > MAX_COLUMNS or len(set(header)) != len(header) or not all(header):
        raise AdapterError("BAD_CSV")
    records = []
    for number, row in enumerate(rows[1:], start=1):
        if not row:
            continue
        if len(row) != len(header):
            raise AdapterError("BAD_ROW", f"행 {number}")
        records.append(dict(zip(header, row)))
    return records


_HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.\-]{0,251}[A-Za-z0-9])?")
_PATH_RE = re.compile(r"/[A-Za-z0-9_./\-]{0,200}")
_PARAM_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,23}")
_PARAM_VALUE_RE = re.compile(r"[A-Za-z0-9_.:\-]{1,40}")


@runtime_checkable
class Adapter(Protocol):
    """어댑터 프로토콜(덕 타이핑): `fetch` 로 바이트를 얻고(네트워크는 주입된 opener 로만) `parse` 로 (SourceRecord, [Fact]) 를 만든다.
    `StructuredAdapter` 가 구조화 응답(JSON·CSV) 어댑터를 위한 공통 구현이다 — 새 어댑터는 그것을 이어받는 것이 보통이지만 이 두 메서드만 갖추면 된다."""

    def fetch(self, access, params, opener): ...

    def parse(self, raw, access, retrieved_at, params=None): ...


class StructuredAdapter:
    """구조화 응답만 읽는 어댑터의 공통 뼈대. 하위 클래스는 `allowed_params`(요청 변수 이름 허용 목록)와 `build_facts` 를 채운다.

    provider 는 SRC 의 Provider 와 같은 모양의 객체(`provider_id`·`strict_tier`·`effective_status`·`access`·`attribution_template`·`snapshot`·`policy`·`retention_days`)다.
    어댑터가 Provider 를 갖는 것은 수집 기록(SourceRecord)에 provider_id·이용 조건 요약·보관 기한을 남기기 위해서다 — 켜도 되는지의 판단은 SRC 의 관문 ①이 한다.

    SRC 와 맞물리는 규칙(독립 검증 V-08): `access.paths` 는 허용 **접두어**(비면 호스트 전체)이므로 요청 경로는 `paths[0] + endpoint_suffix` 다 — 어댑터가 자기 끝 경로를 `endpoint_suffix` 로 정한다.
    SRC 의 외부 호출 관문이 허용 목록 밖 주소를 거부하면 연결 코드가 `opener` 안에서 `AdapterError("EGRESS_DENIED")` 를 올린다 — `fetch` 는 `AdapterError` 를 그대로 올려
    '허용 목록 밖이라 거부함'이라는 사유가 `OPENER_FAILED` 에 뭉개지지 않는다.
    """
    allowed_params = frozenset()
    endpoint_suffix = ""

    def __init__(self, provider, *, max_bytes=MAX_RESPONSE_BYTES, max_rows=MAX_ROWS):
        if F.provider_active_problem(provider):
            raise AdapterError("BAD_PROVIDER")
        self.provider = provider
        self.max_bytes = max_bytes
        self.max_rows = max_rows

    @property
    def provider_id(self):
        return F.field_of(self.provider, "provider_id")

    # -- 주소 ---------------------------------------------------------------
    def _access_parts(self, access):
        kind = F.field_of(access, "kind")
        hosts, paths = F.field_of(access, "hosts") or (), F.field_of(access, "paths") or ()
        if kind not in F.STRUCTURED_ACCESS_KINDS:
            raise AdapterError("NOT_STRUCTURED")
        if not hosts or not isinstance(hosts[0], str) or not _HOST_RE.fullmatch(hosts[0]) or (paths and not isinstance(paths[0], str)):
            raise AdapterError("BAD_ACCESS")
        path = (paths[0] if paths else "") + self.endpoint_suffix
        if not _PATH_RE.fullmatch(path) or ".." in path:
            raise AdapterError("BAD_ACCESS")
        return kind, hosts[0], path

    def build_url(self, access, params=None):
        """비밀 없는 https 요청 주소. 변수 이름은 `allowed_params` 안이고 값은 안전한 글자뿐이며 정렬해 붙인다(같은 입력이면 같은 주소)."""
        _kind, host, path = self._access_parts(access)
        items = []
        for name in sorted(params or {}):
            value = (params or {})[name]
            if name not in self.allowed_params or not _PARAM_NAME_RE.fullmatch(name) or F.query_has_secret_name(name) \
                    or not isinstance(value, str) or not _PARAM_VALUE_RE.fullmatch(value):
                raise AdapterError("BAD_PARAMS")
            items.append(f"{name}={value}")
        url = f"https://{host}{path}" + ("?" + "&".join(items) if items else "")
        if F.request_url_problems(url):
            raise AdapterError("BAD_ACCESS")
        return url

    # -- 가져오기 -----------------------------------------------------------
    def fetch(self, access, params, opener):
        """주입된 opener 로 응답 바이트를 얻는다. opener 의 어떤 예외도 `OPENER_FAILED` 로 바꿔(원래 예외·주소는 싣지 않는다) 크기 상한을 넘으면 거부한다."""
        url = self.build_url(access, params)
        try:
            raw = opener(url, timeout=FETCH_TIMEOUT_SECONDS, max_bytes=self.max_bytes)
        except AdapterError:
            raise
        except Exception:      # noqa: BLE001 — 어떤 예외든 주소·토큰이 문구에 실려 있을 수 있어 분류만 남긴다
            raise AdapterError("OPENER_FAILED") from None
        if not isinstance(raw, (bytes, bytearray)):
            raise AdapterError("BAD_RESPONSE_TYPE")
        if len(raw) > self.max_bytes:
            raise AdapterError("TOO_LARGE")
        return bytes(raw)

    # -- 읽기 ---------------------------------------------------------------
    def decode(self, raw, kind):
        """응답 바이트를 구조화 값으로: csv 는 행 목록, 그 밖(api·dataset)은 JSON."""
        return decode_csv(raw, max_rows=self.max_rows) if kind == "csv" else decode_json(raw)

    def build_facts(self, decoded, record, retrieved_at):
        """하위 클래스가 구현한다: 읽은 구조 → Fact 목록(정해진 라벨 표에서 낱말을 붙인다)."""
        raise NotImplementedError

    def parse(self, raw, access, retrieved_at, params=None):
        """(SourceRecord, [Fact]). 구조화 경로가 아니거나 응답이 상한을 넘거나 형식이 틀리면 AdapterError."""
        kind, _host, _path = self._access_parts(access)
        period = F.parse_as_of(retrieved_at)
        if period is None or period.granularity != "instant":
            raise AdapterError("BAD_RETRIEVED_AT")
        if not isinstance(raw, (bytes, bytearray)):
            raise AdapterError("BAD_RESPONSE_TYPE")
        if len(raw) > self.max_bytes:
            raise AdapterError("TOO_LARGE")
        url = self.build_url(access, params)
        decoded = self.decode(bytes(raw), kind)
        record = F.SourceRecord.create(
            self.provider_id, kind, url, retrieved_at, F.sha256_hex(bytes(raw)), F.snapshot_text(self.provider),
            F.field_of(self.provider, "retention_days"))
        problems = F.validate_record(record)
        if problems:
            raise AdapterError("BAD_ACCESS")
        facts = self.build_facts(decoded, record, retrieved_at)
        if sum(1 for fact in facts if fact.kind != F.KIND_API_VERSION) > self.max_rows:          # JSON 과 CSV 가 같은 행 수에서 거부된다(API 버전 Fact 는 행이 아니다)
            raise AdapterError("TOO_MANY_ROWS")
        seen = set()
        for number, fact in enumerate(facts, start=1):
            if F.validate_fact(fact):
                raise AdapterError("BAD_ROW", f"Fact {number}")
            if fact.fact_id in seen:
                raise AdapterError("DUPLICATE_ROW")
            seen.add(fact.fact_id)
        return record, facts
