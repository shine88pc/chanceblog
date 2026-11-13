"""Fact 글 후보 순서와 중복 방지 키 — 어느 날 어떤 Recipe 로 어느 제품(글감)의 글을 만들지 정하는 **순수 함수**(S2a). 표준 라이브러리와 이 경로의 모듈만 쓰고 입출력·시계·난수·네트워크가 없다 —
'오늘 날짜'는 인자다. 생성기·이력과의 연결(이미 낸 글의 키 읽기·후보를 한 함수로 공급)은 S2b 다.

- 후보(`CandidateSpec`)는 글감 하나다: Recipe·Fact 키·읽을 제품(글 하나에 최대 3개 — 호출 한도 H3)·기간 종류(주·달)·그 기간 안에서 대기하기 시작하는 날(주는 ISO 요일, 달은 일)·순서.
- **중복 방지 키** `candidate_key(spec, today)` 는 `space_weather.kp_weekly:2026-W45` 꼴이다 — 글감 이름과 **발행하는 날이 속한 기간**(ISO 주·달)으로 결정적이라 같은 기간의 같은 글감은 같은 키다.
  이미 낸 키(`done_keys`)에 있으면 후보에서 빠진다. 조립기의 `AssembledPost.dedupe_key`(`recipe|key|region|as_of`)는 글이 쓴 자료의 마지막 기준일까지 담아 같은 주 안에서도 날마다 달라지므로 같은 기간 중복 방지에는
  이 키를 쓴다(S2b 가 이력에 이 키를 남긴다).
- `plan_candidates(today, done_keys)` 는 오늘 만들 수 있는 후보를 순서대로 돌려준다: 대기 중(오늘이 기간 안의 대기 시작일 이후)이고 이미 내지 않은 것만, 순서는 글감 순서를 ISO 주 번호만큼 돌려 정한다
  (같은 글감만 늘 앞서지 않는다 — 한 기간 안에서는 어느 글감을 이미 냈는지와 상관없이 순서가 같다).
- **같은 제품을 읽는 글감은 한 기간에 하나만 낸다**(S2AFIX D4). 같은 기간 종류(주·달)에서 읽는 제품이 겹치는 글감은 한 묶음이고(`conflict_groups`), 한 기간에는 묶음마다 그 기간의 대표 글감 하나만
  후보가 된다 — 대표는 묶음 안에서 기간 번호(ISO 주 번호·달 번호)만큼 돌려 정해 같은 제품을 읽는 글감이 기간마다 번갈아 나온다. 묶음 안의 어느 글감이든 같은 기간의 키가 `done_keys` 에 있으면 그 묶음은
  후보에서 빠진다. 같은 제품의 같은 7일 자료로 만든 두 글은 표의 (날짜, 값)이 모두 같아 거의 같은 글이 되기 때문이다. **이웃 기간(일요일 발행과 다음 날 월요일 발행)의 자료 창이 겹치는 것은 이 함수가 막지
  못한다** — 키가 날짜가 아니라 기간 이름이라서다. 이력에 글을 낸 날짜를 함께 남겨 같은 제품의 다음 글을 자료 창 길이만큼 띄우는 것은 S2b 의 몫이다(docs/FACT_PATH.md §14-5).
- 켜기·실제 발행 수(주 1–2편)·사람 승인은 이 함수의 일이 아니다.

**S2b — 이력의 발행일을 읽는 후보 선택 `select_candidates`(순수)**: 위 `plan_candidates` 는 이력을 보지 않고 주 번호만큼 돌려 정해 이웃 기간의 자료 창 겹침을 막지 못하고 요일 대기 때문에 굶는 글감이 있었다
(§14-7). 공급 함수(`fact_supply.supply`)는 대신 이 함수를 쓴다 — 이력에서 글감마다 가장 최근에 낸 날(KST 날짜)을 읽어 ① **가장 오래 전에 낸 글감이 먼저**(한 번도 안 낸 글감이 맨 앞, 같으면 글감 순서)
② **같은 묶음은 이어서**(대표가 `Insufficient` 면 같은 묶음의 다음 글감 — 같은 제품이라 이미 받은 응답을 다시 쓴다) ③ 이번 기간에 이미 낸 글감과 같은 묶음은 닫힌다 ④ **같은 제품을 읽은 글과 자료 창 길이만큼 띄운다**
(Kp·플레어·등급은 7일, 월 글감 두 제품은 한 달 주기 28일) ⑤ 요일 대기는 월 글감(달의 일)에만 남는다 — 주 글감은 그 주 어느 요일에나 낼 수 있어야 주 상한 1–2편에서도 모든 글감이 차례가 온다(D-231).
시각은 읽지 않는다(오늘과 협정 세계시 분은 인자). `plan_candidates` 와 `representative` 는 이전 그대로 두고 S2a 시험도 그대로다.

**S2c-0(S2C0-a) — 재개 직후 글감 순서 안전장치**: 이력에 Fact 글이 없으면 글감 순서(`order`)가 앞선 글감부터 나와 처음 글이 가장 얇은 주간 글감(Kp 일별·플레어·Kp 폭풍 기준·등급 현황)으로 쏠린다.
`HELD_SPEC_IDS`(기본 `scales_weekly`·`kp_storm_weekly`)에 든 글감은 `select_candidates` 가 후보에서 빼고(수집 호출도 하지 않는다) `FIRST_SPEC_IDS`(기본 `sunspot_monthly_monthly`)는 이력에 한 번도 안 낸
글감들 사이에서 먼저 나온다. 이력은 그대로 읽는다 — 제외한 글감의 지난 글도 묶음 닫힘·같은 제품 간격에 그대로 쓰이고, 제외했다고 '낸 것'으로 세지 않는다. 두 상수를 빈 튜플로 바꾸면 이전 동작과 바이트까지 같다.
`plan_candidates`(S2a)와 `order` 값은 바꾸지 않았다.

설명: docs/FACT_PATH.md §14·§15·§16
"""
import datetime
import re
from dataclasses import dataclass

from pipeline import facts as F
from pipeline import recipes as R
from pipeline import recipes_noregion as RN

MAX_PRODUCTS_PER_POST = 3          # 글 하나가 읽는 제품 수 상한(호출 한도 제안 H3)
PERIOD_WEEK, PERIOD_MONTH = "week", "month"
KEY_PREFIX = "space_weather."


@dataclass(frozen=True)
class CandidateSpec:
    """글감 하나. `due` 는 기간 안에서 대기하기 시작하는 날(주: ISO 요일 1–7, 달: 일 1–28), `order` 는 순서 기본값(작을수록 앞)."""
    spec_id: str
    recipe_id: str
    key: str
    products: tuple
    period: str
    due: int
    order: int

    def params(self):
        return {"key": self.key}


@dataclass(frozen=True)
class Candidate:
    """오늘 만들 수 있는 후보: 글감·중복 방지 키·글을 만들 때 쓸 변수·읽을 제품. `ready` 는 지금 시각에 읽어도 되는가(S2b — 일별 제품의 협정 세계시 하한. 기본 True)."""
    spec: CandidateSpec
    candidate_key: str
    params: tuple
    products: tuple
    ready: bool = True

    @property
    def recipe_id(self):
        return self.spec.recipe_id


SPECS = (
    CandidateSpec("kp_weekly", "R04_NOREGION_SERIES", RN.KEY_KP, ("kp_estimated",), PERIOD_WEEK, 1, 0),
    CandidateSpec("kp_storm_weekly", "R05_THRESHOLD_COUNT", RN.KEY_KP, ("kp_estimated",), PERIOD_WEEK, 2, 1),
    CandidateSpec("flares_weekly", "R05_THRESHOLD_COUNT", RN.KEY_FLARE_FLUX, ("xray_flares",), PERIOD_WEEK, 3, 2),
    CandidateSpec("scales_weekly", "R06_SCALE_OUTLOOK", RN.KEY_SCALE_GEOMAGNETIC, ("scales",), PERIOD_WEEK, 4, 3),
    CandidateSpec("sunspot_daily_monthly", "R04_NOREGION_SERIES", RN.KEY_SSN_DAILY, ("ssn_daily",), PERIOD_MONTH, 3, 4),
    CandidateSpec("sunspot_monthly_monthly", "R04_NOREGION_SERIES", RN.KEY_SSN_MONTHLY, ("ssn_monthly",), PERIOD_MONTH, 8, 5),
)
SPEC_IDS = tuple(spec.spec_id for spec in SPECS)


def conflict_groups(specs=SPECS):
    """같은 기간 종류에서 읽는 제품이 겹치는 글감끼리의 묶음(연결 성분) — 글감 순서대로, 묶음 안도 글감 순서대로. 한 기간에는 한 묶음에서 글 하나만 낸다(S2AFIX D4)."""
    groups = []
    for spec in sorted(specs, key=lambda item: item.order):
        merged = [spec]
        for group in list(groups):
            if group[0].period == spec.period and any(set(member.products) & set(spec.products) for member in group):
                merged = group + merged
                groups.remove(group)
        groups.append(sorted(merged, key=lambda item: item.order))
    return tuple(tuple(group) for group in sorted(groups, key=lambda group: group[0].order))


GROUPS = conflict_groups()
GROUP_OF = {spec.spec_id: group for group in GROUPS for spec in group}

RECIPES_BY_ID = {**R.RECIPES, **RN.NOREGION_RECIPES}


def get_recipe(recipe_id):
    """Recipe id → Recipe(지역 있는 틀 R01–R03 과 지역 없는 틀 R04–R06 모두). 모르는 id 면 None."""
    return RECIPES_BY_ID.get(recipe_id) if isinstance(recipe_id, str) else None


def _day(today):
    return F.as_date(today)


def period_id(spec, today):
    """오늘이 속한 기간의 이름: 주는 ISO 주(`2026-W45`, 연도는 ISO 주-연도), 달은 `2026-11`."""
    day = _day(today)
    if spec.period == PERIOD_WEEK:
        year, week, _weekday = day.isocalendar()
        return f"{year:04d}-W{week:02d}"
    return f"{day.year:04d}-{day.month:02d}"


def candidate_key(spec, today):
    """같은 기간의 같은 글감은 같은 키: `space_weather.kp_weekly:2026-W45`."""
    return f"{KEY_PREFIX}{spec.spec_id}:{period_id(spec, today)}"


def is_due(spec, today):
    """오늘이 이 글감이 대기하기 시작하는 날 이후인가(주: ISO 요일, 달: 일)."""
    day = _day(today)
    return (day.isoweekday() if spec.period == PERIOD_WEEK else day.day) >= spec.due


def _period_number(spec, today):
    """기간 번호: 주는 ISO 주 번호, 달은 달 번호."""
    day = _day(today)
    return day.isocalendar()[1] if spec.period == PERIOD_WEEK else day.month


def representative(spec, today):
    """이 기간에 spec 이 속한 묶음에서 글을 낼 대표 글감 — 묶음 안에서 기간 번호만큼 돌려 정한다(같은 제품을 읽는 글감이 기간마다 번갈아 나온다). 묶음에 글감이 하나뿐이면 그 글감이다."""
    group = GROUP_OF[spec.spec_id]
    return group[_period_number(spec, today) % len(group)]


def _rank(spec, today):
    """글감 순서를 ISO 주 번호만큼 돌린 순위(작을수록 앞) — 이미 낸 글감이 있어도 같은 주 안의 순서는 변하지 않는다."""
    week = _day(today).isocalendar()[1]
    return ((spec.order - week) % len(SPECS), spec.order)


def plan_candidates(today, done_keys=()):
    """오늘 만들 수 있는 후보(`Candidate`)를 순서대로. 대기 중이고(`is_due`) 그 기간의 대표 글감이며 같은 묶음의 어느 글감도 이 기간에 이미 내지 않은 것만. 같은 제품을 읽는 글감은 한 기간에 하나만
    나온다. 같은 입력이면 항상 같은 목록이다."""
    done = set(done_keys)
    out = []
    for spec in sorted(SPECS, key=lambda item: _rank(item, today)):
        key = candidate_key(spec, today)
        if representative(spec, today) is not spec or any(candidate_key(member, today) in done for member in GROUP_OF[spec.spec_id]):
            continue
        if is_due(spec, today) and len(spec.products) <= MAX_PRODUCTS_PER_POST:
            out.append(Candidate(spec, key, tuple(sorted(spec.params().items())), spec.products))
    return out


def next_candidate(today, done_keys=()):
    """`plan_candidates` 의 첫 후보(없으면 None)."""
    found = plan_candidates(today, done_keys)
    return found[0] if found else None


def week_start(today):
    """오늘이 속한 ISO 주의 월요일(`datetime.date`) — 후보 기간의 시작일을 문서·시험이 확인하는 데 쓴다."""
    day = _day(today)
    return day - datetime.timedelta(days=day.isoweekday() - 1)


# ----------------------------------------------------------------------------
# S2b: 이력의 발행일을 읽는 후보 선택
# ----------------------------------------------------------------------------
SPEC_BY_ID = {spec.spec_id: spec for spec in SPECS}
# S2c-0(S2C0-a): 재개 직후 글감 순서 안전장치 — 값이 없으면(빈 튜플) 이전 동작과 바이트까지 같다. 되돌리기는 이 두 줄을 빈 튜플로 바꾸는 것뿐이다. docs/FACT_PATH.md §16·docs/S2C_PLAN.md
HELD_SPEC_IDS = ("scales_weekly", "kp_storm_weekly")       # 보강(S2c-1·2) 전까지 후보에서 임시로 뺀 얇은 글감: 등급 현황(표 재배열뿐)·Kp 폭풍 기준(같은 Kp 파일로 일별 최대값 글과 겹침). 수집 호출도 하지 않는다
FIRST_SPEC_IDS = ("sunspot_monthly_monthly",)             # 이력에 한 번도 안 낸 글감들 사이에서 먼저 낼 글감(목록 순서대로) — 이력이 비었을 때 첫 글을 가장 나은 글감으로. 이미 낸 글감의 순서·`order` 값은 건드리지 않는다
WINDOW_DAYS = {"kp_estimated": 7, "xray_flares": 7, "scales": 7, "ssn_daily": 28, "ssn_monthly": 28}      # 같은 제품을 읽은 두 글 사이의 최소 간격(일) = 글이 읽는 자료 창 길이(주 글감은 7일, 월 글감은 한 달 주기)
DEFAULT_WINDOW_DAYS = 7
NOT_BEFORE_UTC_MINUTES = {"ssn_daily": 30}           # 일별 제품은 협정 세계시 0시 30분 이후에 읽는다(조사 보고서 H8 — 레지스트리 자체 상한 `daily_product_not_before_utc`)
FACTS_MARK = "facts"                                 # 이력 항목의 `content_source` 값(provenance 표식과 같은 낱말)
_KEY_RE = re.compile(r"space_weather\.([a-z_]+):(\d{4}-(?:W\d{2}|\d{2}))")


@dataclass(frozen=True)
class Made:
    """이력이 말해 주는 지난 글: last(글감 spec_id → 가장 최근에 낸 날 — 읽을 수 없는 날짜는 datetime.date.max 로 둔다, 막는 쪽)·keys(낸 candidate_key 들)·dedupe(낸 글의 dedupe_key 들)."""
    last: dict
    keys: frozenset
    dedupe: frozenset


def spec_id_of_key(candidate_key):
    """`space_weather.kp_weekly:2026-W45` → `kp_weekly`. 알려진 글감의 키 모양이 아니면 None."""
    found = _KEY_RE.fullmatch(candidate_key) if isinstance(candidate_key, str) else None
    return found.group(1) if found and found.group(1) in SPEC_BY_ID else None


def made_from_history(history):
    """이력(history.json 의 항목 목록)에서 Fact 글(`content_source` 가 facts 이고 candidate_key 가 있는 항목)만 읽는다. 다른 항목·깨진 항목은 건너뛴다(옛 항목은 그대로 읽힌다).
    날짜(`date`)를 읽을 수 없으면 date.max 로 둔다 — 그 글감과 같은 제품은 막히고(막는 쪽) 순서에서는 가장 최근에 낸 것이 된다."""
    last, keys, dedupe = {}, set(), set()
    for entry in history if isinstance(history, (list, tuple)) else ():
        if not isinstance(entry, dict) or entry.get("content_source") != FACTS_MARK:
            continue
        key = entry.get("candidate_key")
        spec_id = spec_id_of_key(key)
        if spec_id is None:
            continue
        keys.add(key)
        try:
            day = F.as_date(entry.get("date"))
        except F.FactFormatError:
            day = datetime.date.max
        if spec_id not in last or day > last[spec_id]:
            last[spec_id] = day
        dedupe_key = entry.get("dedupe_key")
        if isinstance(dedupe_key, str) and dedupe_key:
            dedupe.add(dedupe_key)
    return Made(last, frozenset(keys), frozenset(dedupe))


def _data_ready(spec, day):
    """자료가 준비된 기간인가: 월 글감은 달의 `due` 일부터, 주 글감은 그 주 어느 요일에나(S2a 의 요일 대기는 굶는 글감을 만들어 이 선택에서는 쓰지 않는다 — D-231)."""
    return spec.period == PERIOD_WEEK or day.day >= spec.due


def _spaced(spec, day, last_read):
    """같은 제품을 읽은 지난 글과 자료 창 길이만큼 떨어졌는가."""
    for product in spec.products:
        previous = last_read.get(product)
        if previous is not None and (day - previous).days < WINDOW_DAYS.get(product, DEFAULT_WINDOW_DAYS):
            return False
    return True


def _first_rank(spec, last):
    """정렬 키의 둘째 칸(S2C0-a): **이력에 한 번도 안 낸 글감 사이에서만** FIRST_SPEC_IDS 에 든 글감이 먼저다(목록 순서대로). 나머지 글감과 이미 낸 글감은 모두 같은 값이라 글감 순서(`order`)가 그대로 이긴다 —
    FIRST_SPEC_IDS 가 비면 모든 글감이 같은 값(0)이라 정렬 결과가 이전과 같다."""
    if spec.spec_id in last or spec.spec_id not in FIRST_SPEC_IDS:
        return len(FIRST_SPEC_IDS)
    return FIRST_SPEC_IDS.index(spec.spec_id)


def select_candidates(today, made, minutes_utc=None):
    """오늘 낼 수 있는 후보를 **먼저 낼 차례** 순서로(순수 함수 — 시각은 인자). 대상: 이번 기간에 같은 묶음에서 아직 내지 않았고, 자료가 준비됐고(`_data_ready`), 같은 제품을 읽은 지난 글과 자료 창 길이만큼 떨어진 글감.
    순서: 이력에서 가장 오래 전에 낸 글감이 먼저(한 번도 안 낸 글감이 맨 앞, 같으면 글감 순서), 같은 묶음의 글감은 묶음에서 가장 앞선 글감의 자리에 이어 붙여 묶음 안 폴백이 한 번 받은 응답을 다시 쓰게 한다.
    `HELD_SPEC_IDS` 의 글감은 대상이 아니고(S2C0-a) 한 번도 안 낸 글감 사이에서는 `FIRST_SPEC_IDS` 의 글감이 먼저다.
    minutes_utc(그날 협정 세계시 0시부터의 분)를 주면 일별 제품(`NOT_BEFORE_UTC_MINUTES`)을 읽는 글감은 그 시각 전에는 `ready=False` 로 돌려준다(차례를 건너뛰지 않고 기다리게 하려는 표시 — 판단은 공급 함수의 일)."""
    day = F.as_date(today)
    held = frozenset(HELD_SPEC_IDS)          # 임시 제외(S2C0-a): 후보 목록에서만 뺀다 — 아래 closed·last_read 는 이력 전체를 그대로 읽는다(제외한 글감도 이력에 남은 글은 '낸 것'이고, 제외했다고 '낸 것'이 되지는 않는다)
    closed = {GROUP_OF[spec.spec_id] for spec in SPECS if candidate_key(spec, day) in made.keys}
    last_read = {}
    for spec in SPECS:
        when = made.last.get(spec.spec_id)
        for product in spec.products if when is not None else ():
            if product not in last_read or when > last_read[product]:
                last_read[product] = when
    eligible = [spec for spec in sorted(SPECS, key=lambda item: item.order)
                if spec.spec_id not in held and len(spec.products) <= MAX_PRODUCTS_PER_POST and GROUP_OF[spec.spec_id] not in closed and _data_ready(spec, day) and _spaced(spec, day, last_read)]
    eligible.sort(key=lambda spec: (made.last.get(spec.spec_id, datetime.date.min), _first_rank(spec, made.last), spec.order))
    out, placed = [], set()
    for spec in eligible:
        group = GROUP_OF[spec.spec_id]
        if group in placed:
            continue
        placed.add(group)
        for member in (item for item in eligible if GROUP_OF[item.spec_id] is group):
            ready = minutes_utc is None or all(minutes_utc >= NOT_BEFORE_UTC_MINUTES.get(product, 0) for product in member.products)
            out.append(Candidate(member, candidate_key(member, day), tuple(sorted(member.params().items())), member.products, ready))
    return tuple(out)
