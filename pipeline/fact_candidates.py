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
- 켜기·실제 발행 수(주 1–2편)·사람 승인은 이 함수의 일이 아니다. 이 모듈은 호출하는 곳이 없다(연결 금지 — 시험이 확인).

설명: docs/FACT_PATH.md §14
"""
import datetime
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
    """오늘 만들 수 있는 후보: 글감·중복 방지 키·글을 만들 때 쓸 변수·읽을 제품."""
    spec: CandidateSpec
    candidate_key: str
    params: tuple
    products: tuple

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
