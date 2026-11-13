"""지역 없는 글 틀(Recipe) — NOAA 우주날씨처럼 **지역이 없는** 시계열·개수·예보 자료용 틀 셋(S2a). 표준 라이브러리와 이 경로의 모듈(`facts`·`calc`·`fact_topics`·`recipes`)만 쓰고
입출력·시계·난수·네트워크가 없다 — `today` 는 인자다. 기존 틀(`recipes.py` R01–R03)의 규칙을 **그대로** 지킨다: 틀 안의 숫자·날짜는 모두 참조 표시, 외부 문장 금지, 받침에 따라 달라지는 조사를
참조 표시 바로 뒤에 두지 않기, 금지 표현·원인 단정 금지, 비교할 수 없는 값은 그 문장을 만들지 않기, 동률은 한 곳(기간)으로 단정하지 않기, 개수를 기간으로 말하지 않기.

| Recipe | 글감 | 계산식 |
|---|---|---|
| `R04_NOREGION_SERIES` 지역 없는 시계열 | 일별 최대 Kp(구간 값을 하루 최댓값으로) · SWPC 일별 흑점수 · 월평균 흑점수 추이(+ 같은 달 순위·마지막으로 낮았던 달, S2c-1) | F01 F02 F03 F06 F07 F09 F10 F12 F15 F17 F18 F19 |
| `R05_THRESHOLD_COUNT` 기준 이상 개수 | 폭풍 기준 이상인 날(Kp) · 플레어 등급별 건수 | F09 F12 F15 F16 |
| `R06_SCALE_OUTLOOK` 등급 현황과 예보 | NOAA 우주기상 등급(어제·지금)과 향후 3일 확률·등급 예보 | F01 F07 F09 F12 |

**우주날씨 문장 규칙**: 관측·추정·예보를 낱말로 구분하고 예보를 사실처럼 쓰지 않는다(예보 값이 있는 줄에는 '예보'가 있다) · Kp 는 'NOAA 추정 Kp'(다른 기관이 확정해 발표하는 Kp 가 아니다) ·
G 등급 기준(Kp 값)을 글에 밝힌다 · 위성·잠정치 주의 문구 · **태양 활동이 지구에 미치는 영향(오로라·전파 장애·통신·설비)을 단정하지 않는다** — 이 글이 아는 것은 숫자뿐이다. 값의 꼬리표(`meta`)의
`status` 가 이 틀이 기대한 상태가 아니면 글을 만들지 않는다(`STATUS_MISMATCH` — 예보·추정 값이 관측 계열에 섞이지 않는다).

제목에는 값을 넣지 않는다(D-200): 이름(`L`)·기준일(`D`·`T`)뿐이다. 설명: docs/FACT_PATH.md §14
"""
from dataclasses import dataclass

from pipeline import calc as C
from pipeline import facts as F
from pipeline import recipes as R
from pipeline.recipes import Builder, Draft, Insufficient, Recipe, md_bullets, md_table

SPACE = "space_weather."
KEY_KP = SPACE + "kp_estimated"
KEY_KP_THRESHOLD = SPACE + "kp_storm_threshold"
KEY_SSN_DAILY = SPACE + "sunspot_daily_swpc"
KEY_SSN_MONTHLY = SPACE + "sunspot_monthly_swpc"
KEY_SSN_SMOOTHED = SPACE + "sunspot_monthly_smoothed_swpc"
KEY_FLARE_CLASS = SPACE + "xray_flare_class"
KEY_FLARE_FLUX = SPACE + "xray_flare_flux"
KEY_SCALE_RADIO = SPACE + "daily_scale_radio"
KEY_SCALE_RADIATION = SPACE + "daily_scale_radiation"
KEY_SCALE_GEOMAGNETIC = SPACE + "daily_scale_geomagnetic"
KEY_OUTLOOK_GEOMAGNETIC = SPACE + "outlook_scale_geomagnetic"
KEY_OUTLOOK_RADIO_MINOR = SPACE + "outlook_prob_radio_minor"
KEY_OUTLOOK_RADIO_MAJOR = SPACE + "outlook_prob_radio_major"
KEY_OUTLOOK_RADIATION = SPACE + "outlook_prob_radiation"
FLARE_FLOOR_LETTERS = ("a", "b", "c", "m", "x")

KP_INTERVALS_PER_DAY = 8        # 3시간 구간 하루치 — 이 개수가 모두 있는 날만 일별 값을 만든다(구간이 모자란 날은 건너뛴다)
DAY_TABLE_ROWS = 14
MONTH_TABLE_ROWS = 12
SEASON_TABLE_ROWS = 8           # 같은 달 해마다 표의 최대 줄 수(가까운 해부터) — 월별 글감(S2c-1)
SEASON_COUNT_UNIT = "년"         # 같은 달 값이 몇 해에 있는지 세는 말
SPACE_DOMAINS = ("space_weather",)
MEASURED = frozenset({"observed"})
FORECAST = frozenset({"predicted", "estimated"})
REFERENCE = frozenset({"reference"})
COUNT_DAY, COUNT_INTERVAL, COUNT_EVENT = "일", "구간", "건"
TIE_UNIT = R.TIE_UNIT

# ----------------------------------------------------------------------------
# 배경 문장(S2AFIX D5) — '이 값은 무엇인가·어떻게 읽나·무엇을 말해 주지 않나'. 우리 말로 쓴 고정 문장이고 숫자·수 낱말이 없다(숫자가 필요한 자리는 참조 표시뿐).
# 정의는 NOAA 조사 보고서 4절(제품 목록의 '값이 문서에 어떻게 해석되는지' 줄)과 5절을 따르고, 영향·원인을 단정하지 않는다. 글마다 둘에서 넷 문장이다.
# ----------------------------------------------------------------------------
KP_ABOUT = ("Kp는 지구 자기장이 일정한 시간 구간 동안 얼마나 흔들렸는지를 숫자로 나타낸 지수입니다. 값이 낮으면 비교적 고요했다는 뜻이고 높을수록 더 크게 흔들렸다는 뜻이며, "
            "NOAA는 이 값이 일정 수준 이상으로 올라가면 지자기 폭풍으로 분류합니다. 하루 값은 그날 구간별 값 가운데 가장 높은 것이라, 그날 자기장이 가장 크게 흔들린 구간의 크기를 보여 줍니다.")
KP_STORM_ABOUT = ("Kp는 지구 자기장이 일정한 시간 구간 동안 얼마나 흔들렸는지를 숫자로 나타낸 지수이고, 값이 높을수록 더 크게 흔들렸다는 뜻입니다. "
                  "NOAA는 이 값이 ⟦F:thr⟧ 이상이면 가장 낮은 단계의 지자기 폭풍으로 분류하며, 이 글은 하루의 가장 높은 값이 이 기준에 닿았는지 견주어 날과 구간을 셌습니다.")
KP_LIMIT = "Kp는 여러 관측소 자료를 모아 지구 전체의 흔들림을 대표하게 만든 값이라, 특정 지역이나 설비에 어떤 영향이 있었는지는 알려 주지 않습니다."
SSN_ABOUT_DAILY = ("흑점수는 태양 표면에 나타나는 어두운 점인 흑점을 관측해 얻는 지표로, 태양 활동을 가늠하는 데 쓰입니다. 값이 클수록 관측된 흑점이 많았다는 뜻이고, 이 글의 값은 SWPC가 날마다 관측해 낸 일별 값입니다. "
                   "하루 값은 날마다 달라지므로 어느 하루의 값보다 여러 날의 평균과 함께 볼 때 흐름을 읽기 쉽습니다.")
SSN_ABOUT_MONTHLY = ("흑점수는 태양 표면에 나타나는 어두운 점인 흑점을 관측해 얻는 지표로, 태양 활동을 가늠하는 데 쓰입니다. "
                     "이 글의 값은 SWPC가 달마다 그 달의 일별 흑점수를 평균해 낸 월별 값이라, 하루하루의 들쭉날쭉함이 덜해 흐름을 읽기 쉽습니다.")
SSN_LIMIT = "흑점수는 태양에서 관측된 흑점의 양만 나타낼 뿐, 그 값이 지구의 통신이나 설비에 어떤 영향을 주었는지는 알려 주지 않습니다."
# 월별 글의 '더 긴 기록 속 위치'(S2c-1): '이 글이 읽은 자료 안에서만' 말하고 '역대'·'기록적'·원인·영향을 말하지 않는다. 같은 달 순위는 높은 값이 앞서고 같은 값은 같은 순위다.
SEASON_RANK_BULLET = "- 같은 달 순위: 이 글이 읽은 같은 달 ⟦V:same_n⟧⟦U:same_n⟧ 가운데 최신 값은 ⟦F:same_rank⟧입니다(높은 값이 앞서고 값이 같으면 같은 순위입니다)"
SEASON_LOW_BULLET = "- 최신 값보다 낮았던 마지막 달(이 글이 읽은 자료 안에서): ⟦D:last_low⟧(⟦F:last_low⟧), ⟦V:last_since⟧⟦U:last_since⟧ 전"
SEASON_TABLE_INTRO = ("같은 달의 값은 아래 표에서 해마다 견줍니다. 표는 같은 달의 이전 해 값을 가까운 해부터 보여 주고, '최신 값과의 차이'는 ⟦D:cur⟧의 값 ⟦F:cur⟧에서 그 해의 값을 뺀 것입니다.")
SEASON_SENTENCE_BOTH = ("같은 달끼리 견주면 최신 값은 이 글이 읽은 ⟦V:same_n⟧⟦U:same_n⟧ 가운데 ⟦F:same_rank⟧에 놓이고, 이 글이 읽은 자료에서 이보다 낮은 달이 마지막으로 나온 것은 "
                        "⟦V:last_since⟧⟦U:last_since⟧ 전인 ⟦D:last_low⟧입니다.")
SEASON_SENTENCE_RANK = "같은 달끼리 견주면 최신 값은 이 글이 읽은 ⟦V:same_n⟧⟦U:same_n⟧ 가운데 ⟦F:same_rank⟧에 놓입니다."
SEASON_SENTENCE_LOW = "이 글이 읽은 자료에서 최신 값보다 낮은 달이 마지막으로 나온 것은 ⟦V:last_since⟧⟦U:last_since⟧ 전인 ⟦D:last_low⟧입니다."
SEASON_CAUTION = ("- 순위와 마지막으로 낮았던 달: 이 글이 읽은 자료 안에서만 견준 것이라 더 오래된 달은 알지 못합니다. 가장 최근 달의 값은 잠정치일 수 있어 나중에 고쳐지면 순위와 달이 달라질 수 있습니다.")
FLARE_ABOUT = ("X선 플레어는 태양이 내는 X선의 세기가 가파르게 올랐다가 가라앉는 사건입니다. 플레어는 가장 셌던 순간의 세기에 따라 A·B·C·M·X로 나누고, "
               "글자가 뒤로 갈수록 센 플레어이며 같은 글자 안에서는 글자 뒤에 붙은 수가 클수록 더 셉니다.")
FLARE_LIMIT = "플레어의 건수와 등급은 태양에서 일어난 사건을 정리한 것일 뿐, 그 플레어가 지구의 통신이나 설비에 어떤 영향을 주었는지는 알려 주지 않습니다."
SCALE_ABOUT = ("NOAA는 우주기상을 전파 교란·태양 방사선 폭풍·지자기 폭풍 갈래로 나누어 단계로 알립니다. 전파 교란 단계는 X선 플레어의 세기로, 방사선 폭풍 단계는 고에너지 입자의 양으로, "
               "지자기 폭풍 단계는 지구 자기장이 흔들린 정도로 정해집니다. 단계는 높을수록 센 현상을 뜻하는 순서 값이라, 단계 사이의 차이를 비율로 읽을 수 없습니다.")


# ----------------------------------------------------------------------------
# 도우미
# ----------------------------------------------------------------------------
def facts_with_key(ctx, key):
    return sorted((f for f in ctx.facts if f.key == key), key=lambda f: (_ordinal(f), f.fact_id))


def _ordinal(item):
    period = F.parse_as_of(item.as_of)
    return period.ordinal if period is not None else 0


def checked_facts(ctx, key, allowed_status, *, numeric=True):
    """키가 key 인 Fact 를 기준일 순으로. 없으면 NO_FACTS · 허용 목록 밖이면 TOPIC · 지역이 있으면 HAS_REGION · 꼬리표의 상태가 allowed_status 밖이면 STATUS_MISMATCH(예보·추정이 관측 계열에 섞이지
    않게) · 라벨·단위가 하나가 아니면 INCONSISTENT_LABELS. 문제 없으면 Fact 목록."""
    found = facts_with_key(ctx, key)
    if not found:
        return Insufficient("NO_FACTS", "이 글감의 Fact 가 없다")
    problem = R.topic_problem(ctx.recipe, found)
    if problem is not None:
        return problem
    if any(f.region is not None for f in found):
        return Insufficient("HAS_REGION", "지역이 있는 계열이라 지역 없는 틀을 쓰지 않는다")
    if any(f.meta_value("status") not in allowed_status for f in found):
        return Insufficient("STATUS_MISMATCH", "값의 상태(관측·추정·예보·기준값)가 이 틀이 기대한 것과 달라 글을 만들지 않는다")
    if numeric and (any(F.parse_as_of(f.as_of) is None for f in found) or len({f.unit for f in found}) != 1):
        return Insufficient("INCONSISTENT_LABELS", "기준일을 읽을 수 없거나 단위가 섞여 글로 만들지 않는다")
    if len({f.label_ko for f in found}) != 1:
        return Insufficient("INCONSISTENT_LABELS", "같은 계열인데 라벨이 서로 달라 글로 만들지 않는다")
    return found


def within_age(ctx, latest, limit_days):
    """최신 기준일이 오늘보다 앞서 있으면(미래 자료) FUTURE_DATA, limit_days 보다 오래됐으면 STALE."""
    period = F.parse_as_of(latest.as_of)
    if F.period_start(period) > ctx.today:
        return Insufficient("FUTURE_DATA", "기준일이 오늘보다 뒤라 쓰지 않는다")
    if (ctx.today - F.period_end(period)).days > limit_days:
        return Insufficient("STALE", "가장 최근 기준일이 너무 오래돼 새 글로 쓰지 않는다")
    return None


def day_groups(raw):
    """시각(instant) Fact → {UTC 날짜: [Fact]}(같은 시각이 둘이면 Insufficient(DUPLICATE_PERIOD), 시각이 아니면 MIXED_PERIOD_KIND)."""
    groups, seen = {}, set()
    for fact in raw:
        period = F.parse_as_of(fact.as_of)
        if period is None or period.granularity != "instant":
            return Insufficient("MIXED_PERIOD_KIND", "시각 자료가 아니라 하루 값을 만들지 않는다")
        if period.ordinal in seen:
            return Insufficient("DUPLICATE_PERIOD", "같은 시각의 값이 둘 이상이라 글을 만들지 않는다")
        seen.add(period.ordinal)
        groups.setdefault(F.utc_day_of(period), []).append(fact)
    return groups


def day_max_items(groups):
    """날짜별 묶음 → 하루 최댓값(F15) 목록(날짜순). 구간이 모두 있지 않은 날은 만들지 않는다(건너뛴 날은 목록에서 빠진다). (항목 목록, 그 항목이 쓴 날짜 목록)."""
    items, days = [], []
    for day in sorted(groups):
        result = C.f15_day_max(groups[day], expected_count=KP_INTERVALS_PER_DAY)
        if isinstance(result, F.DerivedFact):
            items.append(result)
            days.append(day)
    return items, days


def plain_items(raw, granularity):
    """기간 Fact(일·월) → 같은 단위·같은 기간 두 번 없음 확인. Fact 목록 또는 Insufficient."""
    seen = set()
    for fact in raw:
        period = F.parse_as_of(fact.as_of)
        if period.granularity != granularity:
            return Insufficient("MIXED_PERIOD_KIND", "기간 단위가 섞였거나 이 글감의 단위가 아니라 글을 만들지 않는다")
        if period.ordinal in seen:
            return Insufficient("DUPLICATE_PERIOD", "같은 기간의 값이 둘 이상이라 글을 만들지 않는다")
        seen.add(period.ordinal)
    return list(raw)


def one_threshold(ctx, key, unit):
    """기준값 Fact 하나(상태 reference, 단위 일치). 없거나 값이 서로 다른 둘 이상이면 Insufficient. 값이 같은 여럿이면 가장 나중 수집의 것."""
    found = checked_facts(ctx, key, REFERENCE)
    if isinstance(found, Insufficient):
        return Insufficient("NO_THRESHOLD", "기준값 Fact 가 없거나 모양이 맞지 않아 기준 이상 개수를 세지 않는다") if found.code in ("NO_FACTS", "STATUS_MISMATCH") else found
    if any(f.value is None or f.unit != unit for f in found) or len({f.value for f in found}) != 1:
        return Insufficient("NO_THRESHOLD", "기준값이 하나로 정해지지 않아 기준 이상 개수를 세지 않는다")
    return found[-1]


def register(builder, items):
    """조립기가 칸에서 값을 찾을 수 있게 만든 계산 결과(하루 최댓값 같은)를 빌더의 계산 결과 표에 올린다. 계산 결과가 아닌 것(Fact)은 이미 조립기가 갖고 있다."""
    for item in items:
        if isinstance(item, F.DerivedFact):
            builder.registry[item.fact_id] = item


def ties_of(items, extreme):
    return [item for item in items if item.value == extreme.value]


def _cell(item, kind="F"):
    return f"⟦{kind}:{item}⟧"


# ----------------------------------------------------------------------------
# Recipe 4 — 지역 없는 시계열(일별·월별)
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class SeriesSubject:
    """시계열 글감 하나: 키·기간 단위·구간 값을 일별로 묶는 법·평균 창(기간 수)·앞 창과 견주는 길이·전년 같은 기간 대비·최소 점·신선도 한도(일)·표의 줄 수·이 글감만의 주의 줄 틀·태그."""
    key: str
    granularity: str
    bucket: str
    value_word: str
    title_word: str
    window: int
    compare: int
    yoy: bool
    min_points: int
    max_age_days: int
    table_rows: int
    cautions: tuple
    tags: tuple
    smoothed_key: str = ""
    provisional: bool = False         # 표에 '잠정치 표시' 열을 둔다(꼬리표 `quality=provisional` 인 값)
    intro_object: str = ""            # 표 소개 문장의 목적어('일별 최대값을'·'추이를') — 제목어가 본문에 들어가게 한다(Gate 의 약속어 `추이`, S2AFIX D2)
    show_change: bool = True          # '바로 앞 기간 대비' 증감·변화율 열과 줄을 둔다. Kp 는 거짓 — 제공처가 3분의 1 단위 값을 소수로 줄여 적어 두 값의 차이가 한 끝자리 어긋난다(S2AFIX D9)
    about: str = ""                   # '이 값은 무엇인가·어떻게 읽나' 배경 문단 — 숫자 칸 맨 앞(S2AFIX D5)
    limit: str = ""                   # '이 값이 말해 주지 않는 것' 문장 — 해석 둘째 문단 끝(S2AFIX D5)
    season: bool = False              # 월 단위 글감만: 같은 달 순위·마지막으로 낮았던 달·같은 달 해마다 표를 더한다(S2c-1 — 어댑터가 360개월을 보관해야 뜻이 있다)
    count_window: int = 0             # 0 이면 '이 글이 읽은 N개월' 이 읽은 값 전체를 세고, 양수면 최근 그만큼의 기간(표 창)만 센다 — 보관이 360개월이라 전체를 세면 먼 달 하나의 빈칸이 머리 문장의 '개월' 을 '관측 N개' 로 바꾼다(S2c-1)


SERIES_SUBJECTS = (
    SeriesSubject(
        KEY_KP, "day", "day_max", "일별 최대값", "일별 최대값", 3, 0, False, 5, 10, DAY_TABLE_ROWS,
        ("- 추정 Kp: 이 값은 NOAA가 지상 관측소 자료로 스스로 추정한 것이라 다른 기관이 확정해 발표하는 Kp 와 다를 수 있습니다.",
         "- 하루 값: 하루를 이루는 구간이 모두 있는 날만 그날 가장 높은 구간 값을 그날의 값으로 삼았습니다. 구간이 모자란 날은 표에서 건너뛰었습니다(보통 아직 끝나지 않은 날입니다).",
         "- 단위와 반올림: Kp 는 단위 없는 지수라 값끼리 비율로 견주지 않았습니다. 제공처는 잘게 나뉜 눈금의 값을 소수로 줄여 적어 두므로, 날짜 사이의 증감은 계산하지 않았고 평균은 적힌 값으로 계산했습니다. 날짜는 협정 세계시 UTC 기준의 하루입니다."),
        ("우주날씨", "일별 최대값", "숫자로 읽기"), intro_object="일별 최대값을", show_change=False, about=KP_ABOUT, limit=KP_LIMIT),
    SeriesSubject(
        KEY_SSN_DAILY, "day", "", "값", "추이", 7, 30, False, 10, 10, DAY_TABLE_ROWS,
        ("- 흑점수: SWPC가 자체 방식으로 센 일별 값이라 다른 기관의 흑점수와는 직접 견주지 않았습니다.",
         "- 빠진 날: 제공처 자료에 기록이 없는 날은 값이 없는 것으로 보고 평균과 변화에서 뺐습니다. 날짜는 협정 세계시(UTC)입니다."),
        ("우주날씨", "흑점수 추이", "숫자로 읽기"), intro_object="추이를", about=SSN_ABOUT_DAILY, limit=SSN_LIMIT),
    SeriesSubject(
        KEY_SSN_MONTHLY, "month", "", "값", "추이", 3, 12, True, 8, 120, MONTH_TABLE_ROWS,
        ("- 월평균: 제공처가 달마다 그 달의 일별 흑점수를 평균해 낸 값이고, 평활값은 제공처가 여러 달에 걸쳐 따로 평활해 준 값입니다. 평활값이 없는 달은 '자료 없음'으로 적었습니다.",
         "- 잠정치 표시: 표의 '잠정치 표시' 열이 '잠정'인 달은 제공처가 잠정치로 표시한 달이라 나중에 고쳐질 수 있고, 그 달이 들어간 증감과 평균도 같은 한계가 있습니다."),
        ("우주날씨", "흑점수 추이", "숫자로 읽기"), KEY_SSN_SMOOTHED, True, intro_object="추이를", about=SSN_ABOUT_MONTHLY, limit=SSN_LIMIT, season=True, count_window=MONTH_TABLE_ROWS),
)
SERIES_BY_KEY = {subject.key: subject for subject in SERIES_SUBJECTS}


def _subject_of(ctx):
    want = ctx.params.get("key")
    if want:
        return SERIES_BY_KEY.get(want) or Insufficient("UNKNOWN_SUBJECT", "이 틀이 다루는 글감이 아니다")
    for subject in SERIES_SUBJECTS:
        if any(f.key == subject.key for f in ctx.facts):
            return subject
    return Insufficient("NO_FACTS", "쓸 수 있는 숫자 Fact 가 없다")


def _unit_word(granularity):
    return F.GRANULARITY_UNIT[granularity]


@F.exact
def plan_noregion_series(ctx):
    recipe = ctx.recipe
    subject = _subject_of(ctx)
    if isinstance(subject, Insufficient):
        return subject
    raw = checked_facts(ctx, subject.key, MEASURED)
    if isinstance(raw, Insufficient):
        return raw
    if subject.bucket == "day_max":
        groups = day_groups(raw)
        if isinstance(groups, Insufficient):
            return groups
        items, _days = day_max_items(groups)
    else:
        items = plain_items(raw, subject.granularity)
        if isinstance(items, Insufficient):
            return items
    valid = [f for f in items if f.value is not None]
    if len(valid) < subject.min_points:
        return Insufficient("TOO_FEW_POINTS", "값이 있는 기간이 모자라 시계열 글을 만들지 않는다")
    cur = valid[-1]
    stale = within_age(ctx, cur, subject.max_age_days)
    if stale is not None:
        return stale
    lbl = raw[-1]
    context = F.display_context(valid)
    granularity = subject.granularity
    counted = [f for f in valid if _ordinal(f) > _ordinal(cur) - subject.count_window] if subject.count_window else valid        # '이 글이 읽은 N개월' 이 세는 값: 월별 글감은 표 창(12개월)으로 한정한다(S2c-1)
    regular = R.is_regular(counted)
    count_unit = _unit_word(granularity) if regular else R.OBSERVATION_UNIT
    obs = "" if regular else "관측 "
    ratio = F.ratio_ok(cur.unit)
    day_word = "날" if granularity == "day" else "달"
    b = Builder()
    register(b, items)
    b.put("cur", cur)                  # 최신 항목(계산 결과일 수 있다) — 값·기준일 표시용. `main` 은 모든 글이 같이 쓰는 주의 줄이 라벨·단위를 읽는 Fact 다
    b.put("main", lbl)
    b.put("lbl", lbl)
    by_ord = {_ordinal(f): f for f in valid}
    cur_ord = _ordinal(cur)
    window_unit = _unit_word(granularity)

    prev = by_ord.get(cur_ord - 1)
    chg = pct = None
    if prev is not None:
        b.put("prev", prev)
        if subject.show_change:
            chg = b.derive("chg", C.f01_change(cur, prev))
            pct = b.derive("pct", C.f02_pct_change(cur, prev)) if ratio else None
    prev_order = (cur.value > prev.value) - (cur.value < prev.value) if prev is not None and not subject.show_change else None       # 증감 칸이 없는 글감은 바로 앞 날과의 높낮이만 말한다
    yago = next((f for f in valid if f.as_of == F.shift_year(cur.as_of, -1)), None) if subject.yoy else None
    yoy = yoy_chg = None
    if yago is not None:
        b.put("yago", yago)
        yoy = b.derive("yoy", C.f03_yoy(cur, yago)) if ratio else None
        yoy_chg = b.derive("yoy_chg", C.f01_change(cur, yago, require="earlier"))
    window = [by_ord[o] for o in range(cur_ord - subject.window + 1, cur_ord + 1) if o in by_ord]
    mean_w = n_w = dmean = None
    if len(window) == subject.window:
        mean_w = b.derive("mean_w", C.f07_rolling_mean(window))
        n_w = b.derive("n_w", C.f12_count(window, window_unit))
        if mean_w is not None:
            dmean = b.derive("dmean", C.f06_diff_from_mean(cur, mean_w))
    mean_c = mean_p = n_c = chg_c = pct_c = None
    if subject.compare:
        win_c = [by_ord[o] for o in range(cur_ord - subject.compare + 1, cur_ord + 1) if o in by_ord]
        win_p = [by_ord[o] for o in range(cur_ord - 2 * subject.compare + 1, cur_ord - subject.compare + 1) if o in by_ord]
        if len(win_c) == subject.compare and len(win_p) == subject.compare:
            mean_c = b.derive("mean_c", C.f07_rolling_mean(win_c))
            mean_p = b.derive("mean_p", C.f07_rolling_mean(win_p))
            n_c = b.derive("n_c", C.f12_count(win_c, window_unit))
            if mean_c is not None and mean_p is not None:
                chg_c = b.derive("chg_c", C.f01_change(mean_c, mean_p, require="earlier"))
                pct_c = b.derive("pct_c", C.f02_pct_change(mean_c, mean_p, require="earlier")) if ratio else None
            else:
                mean_c = mean_p = n_c = None
    # 평균(창이 짝수 일이면 합이 반 칸에 정확히 걸칠 수 있다 — 30일 평균 100.5)과 그 차이가 표시 자리의 반 칸에 걸리면 그 단위의 표시 자리를 한 칸 늘려 반올림 없이 보인다(R02 의 D-152 와 같은 규칙):
    # '같은 101 인데 평균보다 1 낮다'가 되지 않게 한다
    context = F.settle_context(context, [item for item in (mean_w, dmean, mean_c, mean_p, chg_c) if isinstance(item, F.DerivedFact)])

    chg_verdict = R.verdict(cur, prev, chg, context) if chg is not None else None
    yoy_verdict = R.verdict(cur, yago, yoy_chg, context) if yoy_chg is not None else None
    if (chg is not None and chg_verdict is None) or (yoy_chg is not None and yoy_verdict is None):
        return Insufficient("DISPLAY_INCONSISTENT", "보이는 값과 어긋나는 같음·높낮이 표현이 나오게 되어 글을 만들지 않는다")

    shown = [f for f in items if _ordinal(f) > cur_ord - subject.table_rows]
    shown_valid = [f for f in shown if f.value is not None]
    hi = b.derive("hi", C.f09_max(shown_valid))
    lo = b.derive("lo", C.f10_min(shown_valid))
    first_row, last_row = shown[0], shown[-1]
    b.put("first_row", first_row)
    b.put("last_row", last_row)
    n_all = b.derive("n_all", C.f12_count(counted, count_unit))
    smoothed = {f.as_of: f for f in facts_with_key(ctx, subject.smoothed_key)} if subject.smoothed_key else {}
    if smoothed and (R.topic_problem(recipe, list(smoothed.values())) is not None or any(f.meta_value("status") not in MEASURED for f in smoothed.values())):
        smoothed = {}

    rows = []
    for number, fact in enumerate(reversed(shown), start=1):
        slot = f"r{number}"
        b.put(slot, fact)
        extra = []
        if smoothed:
            partner = smoothed.get(fact.as_of)
            if partner is not None:
                b.put(f"s{number}", partner)
            extra = [f"⟦F:s{number}⟧" if partner is not None and partner.value is not None else R.MISSING_CELL]
        if subject.provisional:
            extra = extra + ["잠정" if fact.meta_value("quality") == "provisional" else "표시 없음"]
        if fact.value is None:
            rows.append([f"⟦D:{slot}⟧", R.MISSING_CELL] + ([R.NA_CELL] + ([R.NA_CELL] if ratio else []) if subject.show_change else []) + extra)
            continue
        row = [f"⟦D:{slot}⟧", f"⟦F:{slot}⟧"]
        if subject.show_change:
            before = by_ord.get(_ordinal(fact) - 1)
            row_chg = row_pct = None
            if before is not None:
                row_chg = b.derive(f"c{number}", C.f01_change(fact, before))
                row_pct = b.derive(f"p{number}", C.f02_pct_change(fact, before)) if ratio else None
            row.append(f"⟦S:c{number}⟧" if row_chg else R.NA_CELL)
            if ratio:
                row.append(f"⟦S:p{number}⟧" if row_pct else R.NA_CELL)
        rows.append(row + extra)

    has_range = hi is not None and lo is not None and len(shown_valid) >= 2 and hi.value != lo.value
    flat_table = hi is not None and lo is not None and len(shown_valid) >= 2 and hi.value == lo.value
    hi_ties = [f for f in shown_valid if hi is not None and f.value == hi.value]
    lo_ties = [f for f in shown_valid if lo is not None and f.value == lo.value]
    n_hi = b.derive("n_hi", C.f12_count(hi_ties, TIE_UNIT)) if has_range and len(hi_ties) > 1 else None
    n_lo = b.derive("n_lo", C.f12_count(lo_ties, TIE_UNIT)) if has_range and len(lo_ties) > 1 else None

    # 더 긴 기록 속 위치(S2c-1, 월별 글감만): 같은 달 순위(F17)·이 글이 읽은 자료에서 마지막으로 이보다 낮았던 달(F18)과 몇 개월 전인지(F19)·같은 달 해마다 값 표. 이번 달 행은 어댑터가 이미 뺐다
    same_rank = same_n = last_low = last_since = None
    season_rows = []
    if subject.season:
        cur_month = F.parse_as_of(cur.as_of).month
        same_month = [f for f in valid if F.parse_as_of(f.as_of).month == cur_month]
        same_rank = b.derive("same_rank", C.f17_season_rank(cur, same_month))
        same_n = b.derive("same_n", C.f12_count(same_month, SEASON_COUNT_UNIT)) if same_rank is not None else None
        last_low = b.derive("last_low", C.f18_last_lower(cur, [f for f in valid if _ordinal(f) < cur_ord]))
        last_since = b.derive("last_since", C.f19_months_between(cur, last_low)) if last_low is not None else None
        if same_rank is not None:
            for number, fact in enumerate(reversed([f for f in same_month if _ordinal(f) < cur_ord][-SEASON_TABLE_ROWS:]), start=1):
                b.put(f"ys{number}", fact)
                diff = b.derive(f"yd{number}", C.f01_change(cur, fact, require="earlier"))
                season_rows.append([f"⟦D:ys{number}⟧", f"⟦F:ys{number}⟧", f"⟦S:yd{number}⟧" if diff else R.NA_CELL])

    # -- 제목(값 없음)·첫 문단(= 설명, 한 문장) --------------------------------
    word = subject.value_word
    titles = [f"⟦L:lbl⟧ {subject.title_word}, ⟦D:first_row⟧부터 ⟦D:last_row⟧까지 — 숫자로 읽기", f"⟦L:lbl⟧ {subject.title_word}, ⟦D:cur⟧ 기준 — 숫자로 읽기",
              f"⟦L:lbl⟧ {subject.title_word}, ⟦D:cur⟧ 기준"]
    leads = []
    span = f", 이 글이 읽은 {obs}⟦V:n_all⟧⟦U:n_all⟧ 자료의 마지막 값" if n_all is not None else ""
    if chg is not None:
        if chg_verdict == "SAME":
            head = f"⟦L:lbl⟧의 {word}은 ⟦D:prev⟧(⟦F:prev⟧)에서 달라지지 않은 ⟦F:cur⟧입니다"
        else:
            up = chg_verdict == "UP"
            head = f"⟦L:lbl⟧의 {word}은 ⟦D:prev⟧(⟦F:prev⟧)보다 ⟦A:chg⟧ {'높은' if up else '낮은'} ⟦F:cur⟧입니다"
        leads.append(head + "(⟦D:cur⟧ 기준).")
        if span:
            leads.append(head + f"(⟦D:cur⟧ 기준{span}).")
    elif prev_order is not None:
        head = (f"⟦L:lbl⟧의 {word}은 ⟦D:prev⟧(⟦F:prev⟧)에서 달라지지 않은 ⟦F:cur⟧입니다" if prev_order == 0
                else f"⟦L:lbl⟧의 {word}은 ⟦D:prev⟧(⟦F:prev⟧)보다 {'높은' if prev_order > 0 else '낮은'} ⟦F:cur⟧입니다")
        leads.append(head + "(⟦D:cur⟧ 기준).")
        if span:
            leads.append(head + f"(⟦D:cur⟧ 기준{span}).")
    if n_all is not None:
        leads.append(f"⟦D:cur⟧ 기준 ⟦L:lbl⟧의 {word}은 ⟦F:cur⟧입니다(이 글이 읽은 {obs}⟦V:n_all⟧⟦U:n_all⟧ 자료의 마지막 값).")
        if has_range:
            leads.append(f"⟦D:cur⟧ 기준 ⟦L:lbl⟧의 {word}은 ⟦F:cur⟧입니다(이 글이 읽은 {obs}⟦V:n_all⟧⟦U:n_all⟧ 자료의 마지막 값이며 최저는 ⟦F:lo⟧, 최고는 ⟦F:hi⟧입니다).")

    # -- 한눈에 ---------------------------------------------------------------
    glance = [f"- 최신 값: ⟦F:cur⟧(⟦D:cur⟧ 기준)"]
    if chg is not None:
        tail = ", 변화율 ⟦S:pct⟧" if pct is not None else ""
        glance.append(f"- 바로 앞 {day_word} 대비: ⟦S:chg⟧{tail} (견준 기간 ⟦D:prev⟧, 그때 값 ⟦F:prev⟧)")
    elif prev_order is not None:
        glance.append(f"- 바로 앞 {day_word}: ⟦F:prev⟧(⟦D:prev⟧)")
    if yoy_chg is not None:
        tail = ", 변화율 ⟦S:yoy⟧" if yoy is not None else ""
        glance.append(f"- 전년 같은 달 대비: ⟦S:yoy_chg⟧{tail} (견준 기간 ⟦D:yago⟧, 그때 값 ⟦F:yago⟧)")
    if mean_w is not None and n_w is not None:
        glance.append("- 최근 ⟦V:n_w⟧⟦U:n_w⟧ 평균: ⟦F:mean_w⟧")
    if mean_c is not None and n_c is not None and chg_c is not None:
        tail = ", 변화율 ⟦S:pct_c⟧" if pct_c is not None else ""
        glance.append(f"- 최근 ⟦V:n_c⟧⟦U:n_c⟧ 평균 ⟦F:mean_c⟧, 그 앞 ⟦V:n_c⟧⟦U:n_c⟧ 평균 ⟦F:mean_p⟧ 대비 ⟦S:chg_c⟧{tail}")
    if has_range:
        lo_part = "최저 ⟦F:lo⟧(⟦D:lo⟧)" if n_lo is None else "최저 ⟦F:lo⟧(같은 값 ⟦V:n_lo⟧⟦U:n_lo⟧, 가장 나중 ⟦D:lo⟧)"
        hi_part = "최고 ⟦F:hi⟧(⟦D:hi⟧)" if n_hi is None else "최고 ⟦F:hi⟧(같은 값 ⟦V:n_hi⟧⟦U:n_hi⟧, 가장 나중 ⟦D:hi⟧)"
        glance.append(f"- 표시한 기간 안의 범위: {lo_part}에서 {hi_part}까지")
    if same_rank is not None and same_n is not None:
        glance.append(SEASON_RANK_BULLET)
    if last_low is not None and last_since is not None:
        glance.append(SEASON_LOW_BULLET)

    # -- 숫자로 보기 ----------------------------------------------------------
    calc_columns = "'바로 앞 기간 대비' 열" if not ratio else "'바로 앞 기간 대비'와 '변화율' 열"
    day_max = subject.bucket == "day_max"
    if subject.show_change:
        how = ("값은 제공처의 구간 값에서 이 글이 하루 최댓값을 직접 골랐고" if day_max else "값은 제공처 자료 그대로이고") + f", {calc_columns}은 이 글이 직접 계산했습니다."
    else:
        how = "값은 제공처의 구간 값에서 이 글이 하루 최댓값을 직접 골랐습니다." if day_max else "값은 제공처 자료 그대로입니다."
    head_columns = ["기준 기간", "값"] + (["바로 앞 기간 대비 증감"] + (["바로 앞 기간 대비 변화율"] if ratio else []) if subject.show_change else []) + (["평활값(제공처)"] if smoothed else []) \
        + (["잠정치 표시"] if subject.provisional else [])
    aligns = ["l", "r"] + (["r"] + (["r"] if ratio else []) if subject.show_change else []) + (["r"] if smoothed else []) + (["l"] if subject.provisional else [])
    numbers = ([subject.about] if subject.about else []) + [f"아래 표는 ⟦L:lbl⟧의 {subject.intro_object or word + '을'} ⟦D:first_row⟧부터 ⟦D:last_row⟧까지 보여 줍니다. {how} 최근 기간이 맨 위입니다.",
                                                          md_table(head_columns, rows, aligns)]
    notes = []
    if chg is not None:
        notes.append("증감의 단위는 ⟦U:chg⟧입니다.")
    gap_note = "값이 비어 있는 기간은 '자료 없음'으로 적고, 제공처 자료에 기간 자체가 없으면 표에서 건너뜁니다."
    if subject.show_change:
        gap_note += " " + ("앞 기간의 값이 없으면 증감과 변화율을 계산하지 않았습니다." if ratio else "앞 기간의 값이 없으면 증감을 계산하지 않았습니다. 이 단위는 기준점이 임의인 척도라 변화율은 계산하지 않았습니다.")
    notes.append(gap_note)
    if last_row is not cur:
        notes.append("가장 최근 기간(⟦D:last_row⟧)의 값은 자료에 없어, 값이 있는 마지막 기간 ⟦D:cur⟧ 기준으로 최신 값을 정했습니다.")
    numbers.append(" ".join(notes))
    if season_rows:
        numbers.append(SEASON_TABLE_INTRO)
        numbers.append(md_table(["기준 기간", "값", "최신 값과의 차이"], season_rows, ["l", "r", "r"]))

    # -- 비교·해석(이 글의 해석) ------------------------------------------------
    sentences = []
    if prev_order is not None:
        if prev_order == 0:
            sentences.append(f"최신 값은 바로 앞 {day_word}(⟦D:prev⟧)의 ⟦F:prev⟧에서 달라지지 않았습니다.")
        else:
            sentences.append(f"최신 값은 바로 앞 {day_word}(⟦D:prev⟧)의 ⟦F:prev⟧보다 {'높습니다' if prev_order > 0 else '낮습니다'}.")
    if dmean is not None:
        sign = R.direction(dmean, context)
        if sign > 0:
            sentences.append("최신 값은 최근 ⟦V:n_w⟧⟦U:n_w⟧ 평균 ⟦F:mean_w⟧보다 ⟦A:dmean⟧ 높아서 직전 흐름의 위쪽에 있습니다.")
        elif sign < 0:
            sentences.append("최신 값은 최근 ⟦V:n_w⟧⟦U:n_w⟧ 평균 ⟦F:mean_w⟧보다 ⟦A:dmean⟧ 낮아서 직전 흐름의 아래쪽에 있습니다.")
        else:
            sentences.append("최신 값은 최근 ⟦V:n_w⟧⟦U:n_w⟧ 평균 ⟦F:mean_w⟧에서 거의 벗어나지 않았습니다.")
    if chg_c is not None:
        sign = R.direction(chg_c, context)
        if sign > 0:
            sentences.append("최근 ⟦V:n_c⟧⟦U:n_c⟧ 평균은 그 앞 ⟦V:n_c⟧⟦U:n_c⟧ 평균보다 ⟦A:chg_c⟧ 높습니다.")
        elif sign < 0:
            sentences.append("최근 ⟦V:n_c⟧⟦U:n_c⟧ 평균은 그 앞 ⟦V:n_c⟧⟦U:n_c⟧ 평균보다 ⟦A:chg_c⟧ 낮습니다.")
        else:
            sentences.append("최근 ⟦V:n_c⟧⟦U:n_c⟧ 평균은 그 앞 ⟦V:n_c⟧⟦U:n_c⟧ 평균과 거의 같습니다.")
    if yoy_chg is not None:
        if yoy_verdict == "SAME":
            sentences.append("전년 같은 기간(⟦D:yago⟧)의 ⟦F:yago⟧에서도 달라지지 않았습니다.")
        else:
            sentences.append(f"전년 같은 기간(⟦D:yago⟧)의 ⟦F:yago⟧보다는 ⟦A:yoy_chg⟧ {'높습니다' if yoy_verdict == 'UP' else '낮습니다'}.")
    if flat_table:
        sentences.append("표에 적은 값이 모두 같아 가장 높은 값과 가장 낮은 값을 가르지 않았습니다.")
    elif has_range:
        if cur.value == hi.value:
            sentences.append("표에서 가장 높은 값이 바로 최신 값입니다." if n_hi is None else "최신 값은 표에서 가장 높은 값과 같고, 그 값은 표에 ⟦V:n_hi⟧⟦U:n_hi⟧ 나옵니다.")
        elif cur.value == lo.value:
            sentences.append("표에서 가장 낮은 값이 바로 최신 값입니다." if n_lo is None else "최신 값은 표에서 가장 낮은 값과 같고, 그 값은 표에 ⟦V:n_lo⟧⟦U:n_lo⟧ 나옵니다.")
        else:
            high = "표에서 가장 높은 값은 ⟦D:hi⟧의 ⟦F:hi⟧입니다." if n_hi is None else "표에서 가장 높은 값은 ⟦F:hi⟧입니다. 이 값은 표에 ⟦V:n_hi⟧⟦U:n_hi⟧ 나오며 가장 나중은 ⟦D:hi⟧입니다."
            low = "가장 낮은 값은 ⟦D:lo⟧의 ⟦F:lo⟧입니다." if n_lo is None else "가장 낮은 값은 ⟦F:lo⟧입니다. 이 값은 표에 ⟦V:n_lo⟧⟦U:n_lo⟧ 나오며 가장 나중은 ⟦D:lo⟧입니다."
            sentences.append(high + " " + low)
    if same_rank is not None and same_n is not None and last_low is not None and last_since is not None:
        sentences.append(SEASON_SENTENCE_BOTH)
    elif same_rank is not None and same_n is not None:
        sentences.append(SEASON_SENTENCE_RANK)
    elif last_low is not None and last_since is not None:
        sentences.append(SEASON_SENTENCE_LOW)
    reading = ["**이 글의 해석**: " + " ".join(sentences) if sentences else "**이 글의 해석**: 비교할 수 있는 값이 모자라 숫자만 옮겼습니다.",
               "짧은 오르내림만으로 흐름이 바뀌었다고 말하기는 어렵습니다. "
               + ("이 글은 여러 기간을 함께 놓고 평균과 범위만 계산했습니다. " + subject.limit if subject.limit
                  else "이 글은 지구에 어떤 영향이 있는지도 말하지 않으며, 여러 기간을 함께 놓고 평균과 범위만 계산했습니다.")]      # 원인을 알 수 없다는 말은 주의 줄 '이 글이 아는 것' 이 한 번만 한다(S2c-1 S1-b)
    tags = [lbl.label_ko] + list(subject.tags)
    cautions = list(subject.cautions) + ([SEASON_CAUTION] if same_rank is not None or last_low is not None else [])
    return Draft(cur, b.slots, titles, leads, [(R.H_GLANCE, [md_bullets(glance)]), (R.H_NUMBERS, numbers), (R.H_READING, reading)],
                 cautions, tags, lbl.topic, cur.as_of, b.registry, b.skipped, (recipe.recipe_id, subject.key, "-", cur.as_of), context)


# ----------------------------------------------------------------------------
# Recipe 5 — 기준 이상 개수(폭풍 기준 이상인 날·플레어 등급별 건수)
# ----------------------------------------------------------------------------
@F.exact
def _plan_kp_storm(ctx):
    recipe = ctx.recipe
    raw = checked_facts(ctx, KEY_KP, MEASURED)
    if isinstance(raw, Insufficient):
        return raw
    unit = raw[0].unit
    thr = one_threshold(ctx, KEY_KP_THRESHOLD, unit)
    if isinstance(thr, Insufficient):
        return thr
    groups = day_groups(raw)
    if isinstance(groups, Insufficient):
        return groups
    days, day_keys = day_max_items(groups)
    if len(days) < recipe.min_points:
        return Insufficient("TOO_FEW_POINTS", "하루 구간이 모두 있는 날이 모자라 기준 이상 개수 글을 만들지 않는다")
    cur = days[-1]
    stale = within_age(ctx, cur, 10)
    if stale is not None:
        return stale
    usable = [f for day in day_keys for f in groups[day]]
    context = F.display_context([*days, thr])
    regular = R.is_regular(days)
    b = Builder()
    register(b, days)
    lbl = raw[-1]
    b.put("cur", cur)
    b.put("main", lbl)
    b.put("lbl", lbl)
    b.put("thr", thr)
    n_days = b.derive("n_days", C.f12_count(days, COUNT_DAY))
    n_storm = b.derive("n_storm", C.f16_count_between(days, thr, None, COUNT_DAY))
    n_int_all = b.derive("n_int_all", C.f12_count(usable, COUNT_INTERVAL))
    n_int_storm = b.derive("n_int_storm", C.f16_count_between(usable, thr, None, COUNT_INTERVAL))
    hi = b.derive("hi", C.f09_max(days))
    lo = b.derive("lo", C.f10_min(days))
    if any(item is None for item in (n_days, n_storm, n_int_all, n_int_storm, hi, lo)):
        return Insufficient("NOT_COMPARABLE", "기준 이상 개수를 계산할 수 없어 글을 만들지 않는다")
    mean_days = b.derive("mean_days", C.f07_rolling_mean(days)) if regular and len(days) >= 2 else None
    hi_set = ties_of(days, hi)
    lo_set = ties_of(days, lo)
    flat = hi.value == lo.value                   # 읽은 날의 하루 최대값이 모두 같다 — 가장 높은 날·가장 낮은 날을 가르지 않는다(S2AFIX D6)
    n_hi = b.derive("n_hi", C.f12_count(hi_set, TIE_UNIT)) if len(hi_set) > 1 and not flat else None
    n_lo = b.derive("n_lo", C.f12_count(lo_set, TIE_UNIT)) if len(lo_set) > 1 and not flat else None
    first_day, last_day = days[0], days[-1]
    b.put("first_row", first_day)
    b.put("last_row", last_day)
    shown = days[-R.CONTEXT_ROWS * 2:]
    day_of = {item.fact_id: day for item, day in zip(days, day_keys)}
    rows = []
    for number, day_item in enumerate(reversed(shown), start=1):
        day = day_of[day_item.fact_id]
        b.put(f"d{number}", day_item)
        per_day = b.derive(f"k{number}", C.f16_count_between(groups[day], thr, None, COUNT_INTERVAL))
        flag = "기준 이상" if day_item.value >= thr.value else "기준 미만"
        rows.append([f"⟦D:d{number}⟧", f"⟦F:d{number}⟧", f"⟦F:k{number}⟧" if per_day is not None else R.NA_CELL, flag])

    titles = [f"⟦L:lbl⟧ 기준 이상인 날 수, ⟦D:first_row⟧부터 ⟦D:last_row⟧까지", f"⟦L:lbl⟧ 기준 이상인 날, ⟦D:cur⟧ 기준 — 숫자로 읽기", f"⟦L:lbl⟧ 기준 이상인 날, ⟦D:cur⟧ 기준"]
    leads = [f"⟦D:first_row⟧부터 ⟦D:last_row⟧까지 하루 최대값이 기준 ⟦F:thr⟧ 이상인 날은 이 글이 읽은 ⟦V:n_days⟧⟦U:n_days⟧ 가운데 ⟦V:n_storm⟧⟦U:n_storm⟧입니다.",
             f"⟦D:first_row⟧부터 ⟦D:last_row⟧까지 ⟦L:lbl⟧의 하루 최대값이 기준 ⟦F:thr⟧ 이상인 날은 이 글이 읽은 ⟦V:n_days⟧⟦U:n_days⟧ 가운데 ⟦V:n_storm⟧⟦U:n_storm⟧입니다."]
    glance = ["- 기준: 하루 최대값이 ⟦F:thr⟧ 이상이면 '기준 이상인 날'로 셌습니다(NOAA가 가장 낮은 지자기 폭풍 등급으로 삼는 값이며 센 것은 이 글입니다).",
              "- 이 글이 읽은 ⟦V:n_days⟧⟦U:n_days⟧ 가운데 기준 이상인 날: ⟦V:n_storm⟧⟦U:n_storm⟧",
              "- 구간 단위로는 ⟦V:n_int_all⟧⟦U:n_int_all⟧ 가운데 기준 이상인 구간: ⟦V:n_int_storm⟧⟦U:n_int_storm⟧"]
    if flat:
        glance.append("- 하루 최대값의 범위: 읽은 ⟦V:n_days⟧⟦U:n_days⟧ 모두 같은 ⟦F:hi⟧입니다(가장 높은 날과 가장 낮은 날을 가르지 않았습니다)")
    else:
        glance.append("- 가장 높은 하루 최대값: ⟦F:hi⟧(⟦D:hi⟧)" if n_hi is None else "- 가장 높은 하루 최대값: ⟦F:hi⟧(같은 값 ⟦V:n_hi⟧⟦U:n_hi⟧, 가장 나중 ⟦D:hi⟧)")
        glance.append("- 가장 낮은 하루 최대값: ⟦F:lo⟧(⟦D:lo⟧)" if n_lo is None else "- 가장 낮은 하루 최대값: ⟦F:lo⟧(같은 값 ⟦V:n_lo⟧⟦U:n_lo⟧, 가장 나중 ⟦D:lo⟧)")
    if mean_days is not None:
        glance.append("- 하루 최대값의 평균: ⟦F:mean_days⟧")
    numbers = [KP_STORM_ABOUT, "아래 표는 ⟦L:lbl⟧의 하루 최대값을 ⟦D:first_row⟧부터 ⟦D:last_row⟧까지의 날마다 보여 줍니다. 하루 최대값은 하루를 이루는 구간 값 가운데 가장 높은 값을 이 글이 직접 고른 것이고, "
               "'기준 이상 구간'과 '판정'은 하루 최대값이 기준 ⟦F:thr⟧ 이상인지 이 글이 직접 견주어 센 것입니다. 최근 날짜가 맨 위입니다.",
               md_table(["기준일", "하루 최대값", "기준 이상 구간", "판정"], rows, ["l", "r", "r", "l"]),
               "구간이 모두 있지 않은 날은 세지 않고 표에서 건너뛰었습니다(보통 아직 끝나지 않은 날입니다). 값이 기준과 같으면 기준 이상으로 셌습니다."]
    sentences = []
    if n_storm.value == 0:
        if flat:
            top = "읽은 날의 하루 최대값은 모두 같은 ⟦F:hi⟧입니다."
        elif n_hi is None:
            top = "가장 높은 하루 최대값은 ⟦D:hi⟧의 ⟦F:hi⟧입니다."
        else:
            top = "가장 높은 하루 최대값은 ⟦F:hi⟧입니다. 이 값은 ⟦V:n_hi⟧⟦U:n_hi⟧ 나옵니다."
        sentences.append("이 글이 읽은 날 가운데 하루 최대값이 기준 ⟦F:thr⟧ 이상인 날은 없었습니다. " + top)
    else:
        sentences.append("이 글이 읽은 날 가운데 하루 최대값이 기준 ⟦F:thr⟧ 이상인 날은 모두 ⟦V:n_storm⟧⟦U:n_storm⟧입니다. 그런 날의 기준 이상 구간은 모두 합쳐 ⟦V:n_int_storm⟧⟦U:n_int_storm⟧입니다.")
        if flat:
            sentences.append("읽은 날의 하루 최대값은 모두 같은 ⟦F:hi⟧입니다.")
        else:
            sentences.append("가장 높은 하루 최대값은 ⟦D:hi⟧의 ⟦F:hi⟧입니다." if n_hi is None else "가장 높은 하루 최대값은 ⟦F:hi⟧입니다. 이 값은 ⟦V:n_hi⟧⟦U:n_hi⟧ 나오며 가장 나중은 ⟦D:hi⟧입니다.")
    reading = ["**이 글의 해석**: " + " ".join(sentences),
               "기준 이상인 날이 많거나 적다는 것이 앞으로도 그렇다는 뜻은 아닙니다. 이 글은 읽은 기간의 숫자를 세기만 했고 많고 적은 이유는 설명하지 않았습니다. " + KP_LIMIT]
    caveats = ["- 세는 기준: 이 글이 정한 세기 기준은 ⟦F:thr⟧입니다. NOAA가 구간마다 붙인 등급이 아니라 이 글이 값을 기준과 견주어 센 것이라 경계에서 다를 수 있습니다.",
               "- 추정 Kp: 이 값은 NOAA가 지상 관측소 자료로 스스로 추정한 것이라 다른 기관이 확정해 발표하는 Kp 와 다를 수 있습니다. 구간과 날짜는 협정 세계시(UTC)입니다.",
               "- 읽은 기간: ⟦D:first_row⟧부터 ⟦D:last_row⟧까지이며 이 자료에서 구간이 모두 있는 날만 셌습니다. 더 긴 기간의 폭풍 일수는 이 글이 알지 못합니다."]
    return Draft(cur, b.slots, titles, leads, [(R.H_GLANCE, [md_bullets(glance)]), (R.H_NUMBERS, numbers), (R.H_READING, reading)], caveats,
                 [lbl.label_ko, "폭풍 기준", "우주날씨", "숫자로 읽기"], lbl.topic, cur.as_of, b.registry, b.skipped, (recipe.recipe_id, KEY_KP, "-", cur.as_of), context)


@F.exact
def _plan_flare_classes(ctx):
    recipe = ctx.recipe
    flux = checked_facts(ctx, KEY_FLARE_FLUX, MEASURED)
    if isinstance(flux, Insufficient):
        return flux
    classes = checked_facts(ctx, KEY_FLARE_CLASS, MEASURED, numeric=False)
    if isinstance(classes, Insufficient):
        return classes
    unit = flux[0].unit
    floors = {}
    for letter in FLARE_FLOOR_LETTERS:
        floors[letter] = one_threshold(ctx, SPACE + "xray_class_floor_" + letter, unit)
        if isinstance(floors[letter], Insufficient):
            return floors[letter]
    by_time = {f.as_of: f for f in classes}
    if len(by_time) != len(classes) or {f.as_of for f in flux} != set(by_time):
        return Insufficient("INCONSISTENT_LABELS", "플레어 등급과 세기가 서로 짝이 맞지 않아 글을 만들지 않는다")
    if len(flux) < recipe.min_points:
        return Insufficient("TOO_FEW_POINTS", "플레어 기록이 모자라 글을 만들지 않는다")
    if any(f.value is None for f in flux) or any(f.value is None for f in classes):
        return Insufficient("MISSING_VALUE", "값이 없는 플레어 기록이 있어 글을 만들지 않는다")
    first, last = flux[0], flux[-1]
    stale = within_age(ctx, last, 10)
    if stale is not None:
        return stale
    context = F.display_context([first])
    satellites = {f.meta_value("satellite") for f in flux}
    b = Builder()
    lbl = classes[-1]
    b.put("cur", last)
    b.put("main", last)
    b.put("lbl", lbl)
    b.put("first", first)
    b.put("last", last)
    n_all = b.derive("n_all", C.f12_count(flux, COUNT_EVENT))
    bounds = [floors[letter] for letter in FLARE_FLOOR_LETTERS]
    counts = []
    for index, letter in enumerate(FLARE_FLOOR_LETTERS):
        upper = bounds[index + 1] if index + 1 < len(bounds) else None
        counts.append(b.derive(f"n_{letter}", C.f16_count_between(flux, bounds[index], upper, COUNT_EVENT)))
    n_m_up = b.derive("n_m_up", C.f16_count_between(flux, floors["m"], None, COUNT_EVENT))
    hi = b.derive("hi", C.f09_max(flux))
    if n_all is None or n_m_up is None or hi is None or any(item is None for item in counts):
        return Insufficient("NOT_COMPARABLE", "플레어 개수를 계산할 수 없어 글을 만들지 않는다")
    top_class = by_time[hi.as_of]
    b.put("cls_hi", top_class)
    hi_ties = ties_of(flux, hi)
    n_hi = b.derive("n_hi", C.f12_count(hi_ties, TIE_UNIT)) if len(hi_ties) > 1 else None
    rows = []
    for letter, count in zip(FLARE_FLOOR_LETTERS, counts):
        rows.append([f"{letter.upper()}급", f"⟦F:n_{letter}⟧"])
    rows.append(["M급 이상 합계", "⟦F:n_m_up⟧"])
    rows.append(["전체", "⟦F:n_all⟧"])
    titles = ["⟦L:lbl⟧별 건수, ⟦T:record⟧ 기준 — 숫자로 읽기", "⟦L:lbl⟧별 건수, ⟦T:record⟧ 기준"]
    leads = ["이 글이 읽은 X선 플레어 ⟦V:n_all⟧⟦U:n_all⟧ 가운데 M급 이상은 ⟦V:n_m_up⟧⟦U:n_m_up⟧입니다(가장 큰 플레어는 ⟦D:hi⟧의 ⟦F:cls_hi⟧입니다).",
             "⟦D:first⟧부터 ⟦D:last⟧까지 기록된 X선 플레어 ⟦V:n_all⟧⟦U:n_all⟧ 가운데 M급 이상은 ⟦V:n_m_up⟧⟦U:n_m_up⟧입니다(가장 큰 플레어는 ⟦F:cls_hi⟧입니다)."]
    glance = ["- 읽은 플레어: ⟦V:n_all⟧⟦U:n_all⟧(처음 ⟦D:first⟧, 마지막 ⟦D:last⟧)",
              "- M급 이상: ⟦V:n_m_up⟧⟦U:n_m_up⟧(그 가운데 X급 ⟦V:n_x⟧⟦U:n_x⟧)",
              "- 가장 큰 플레어: ⟦F:cls_hi⟧(⟦D:hi⟧)" if n_hi is None else "- 가장 큰 플레어: ⟦F:cls_hi⟧(같은 세기 ⟦V:n_hi⟧⟦U:n_hi⟧, 가장 나중 ⟦D:hi⟧)",
              "- 등급별 건수는 아래 표에 적었습니다."]
    numbers = [FLARE_ABOUT, "아래 표는 읽은 기간에 기록된 X선 플레어를 등급 문자별로 나누어 센 것입니다. 등급은 제공처 자료 그대로이고 건수는 이 글이 직접 센 것입니다.",
               md_table(["등급", "건수"], rows, ["l", "r"]),
               "각 등급은 최대 세기가 그 등급의 하한 이상이고 바로 위 등급의 하한 미만인 플레어를 셌습니다. 해당하는 플레어가 없는 등급도 건수 칸을 비우지 않고 센 결과를 그대로 적었습니다."]
    sentences = ["M급 이상 플레어는 모두 ⟦V:n_m_up⟧⟦U:n_m_up⟧입니다. 그 가운데 X급은 ⟦V:n_x⟧⟦U:n_x⟧입니다.",
                 "읽은 기간에서 가장 큰 플레어는 ⟦D:hi⟧의 ⟦F:cls_hi⟧입니다." if n_hi is None else "읽은 기간에서 가장 큰 세기는 ⟦F:cls_hi⟧입니다. 같은 세기가 ⟦V:n_hi⟧⟦U:n_hi⟧ 있으며 가장 나중은 ⟦D:hi⟧입니다."]
    reading = ["**이 글의 해석**: " + " ".join(sentences),
               "플레어가 많거나 적다는 것이 앞으로도 그렇다는 뜻은 아닙니다. 이 글은 기록된 건수를 세기만 했고 많고 적은 이유는 설명하지 않았습니다. " + FLARE_LIMIT]
    one_satellite = len(satellites) == 1 and None not in satellites
    caveats = ["- 기록된 플레어: 이 글의 플레어는 제공처가 자동 감지로 기록한 목록이며 감지가 놓친 느린 상승은 빠질 수 있습니다. 시각은 협정 세계시(UTC)입니다.",
               "- 기록한 위성: 이 목록의 플레어는 같은 위성의 기록입니다. 위성이 바뀌면 같은 등급이라도 세기를 곧바로 견주기 어려울 수 있습니다." if one_satellite
               else "- 기록한 위성: 이 목록에는 여러 위성의 기록이 섞여 있어 위성이 다르면 같은 등급이라도 세기를 곧바로 견주기 어려울 수 있습니다.",
               "- 읽은 기간: 이 글은 제공처의 최근 기록 목록에 있는 플레어만 셌습니다. 그보다 긴 기간의 건수는 이 글이 알지 못합니다."]
    return Draft(last, b.slots, titles, leads, [(R.H_GLANCE, [md_bullets(glance)]), (R.H_NUMBERS, numbers), (R.H_READING, reading)], caveats,
                 [lbl.label_ko, "플레어 건수", "우주날씨", "숫자로 읽기"], lbl.topic, F.utc_day_of(F.parse_as_of(last.as_of)), b.registry, b.skipped,
                 (recipe.recipe_id, KEY_FLARE_FLUX, "-", F.utc_day_of(F.parse_as_of(last.as_of))), context)


@F.exact
def plan_threshold_count(ctx):
    want = ctx.params.get("key")
    if want == KEY_KP or (not want and any(f.key == KEY_KP for f in ctx.facts)):
        return _plan_kp_storm(ctx)
    if want == KEY_FLARE_FLUX or (not want and any(f.key == KEY_FLARE_FLUX for f in ctx.facts)):
        return _plan_flare_classes(ctx)
    return Insufficient("UNKNOWN_SUBJECT" if want else "NO_FACTS", "이 틀이 다루는 글감이 아니거나 쓸 수 있는 Fact 가 없다")


# ----------------------------------------------------------------------------
# Recipe 6 — NOAA 우주기상 등급 현황과 예보(어제·지금의 등급 + 향후 확률·등급 예보)
# ----------------------------------------------------------------------------
def _by_day(facts):
    return {_ordinal(f): f for f in facts}


@F.exact
def plan_scale_outlook(ctx):
    recipe = ctx.recipe
    observed, forecast = {}, {}
    for name, key in (("radio", KEY_SCALE_RADIO), ("radiation", KEY_SCALE_RADIATION), ("geomagnetic", KEY_SCALE_GEOMAGNETIC)):
        found = checked_facts(ctx, key, MEASURED)
        if isinstance(found, Insufficient):
            return found
        observed[name] = found
    for name, key in (("g", KEY_OUTLOOK_GEOMAGNETIC), ("minor", KEY_OUTLOOK_RADIO_MINOR), ("major", KEY_OUTLOOK_RADIO_MAJOR), ("s", KEY_OUTLOOK_RADIATION)):
        found = checked_facts(ctx, key, FORECAST)
        if isinstance(found, Insufficient):
            return found
        forecast[name] = found
    now = {name: items[-1] for name, items in observed.items()}
    if any(item.value is None for item in now.values()) or len({item.as_of for item in now.values()}) != 1:
        return Insufficient("NOT_COMPARABLE", "지금의 등급이 비어 있거나 기준일이 서로 달라 글을 만들지 않는다")
    days = {name: [f for f in items if f.value is not None] for name, items in forecast.items()}
    if any(len(items) < recipe.min_points for items in days.values()) or len({tuple(f.as_of for f in items) for items in days.values()}) != 1:
        return Insufficient("TOO_FEW_POINTS", "예보 날짜가 모자라거나 서로 달라 글을 만들지 않는다")
    if any(F.parse_as_of(f.as_of).granularity != "day" for items in (*observed.values(), *days.values()) for f in items):
        return Insufficient("MIXED_PERIOD_KIND", "일 단위 자료가 아니라 글을 만들지 않는다")
    if not R.is_regular(days["g"]):
        return Insufficient("NOT_COMPARABLE", "예보 날짜가 이어지지 않아 글을 만들지 않는다")
    stale = within_age(ctx, now["geomagnetic"], 3)
    if stale is not None:
        return stale
    context = F.display_context([*now.values(), *(f for items in days.values() for f in items)])
    b = Builder()
    b.put("cur", now["geomagnetic"])
    b.put("main", now["geomagnetic"])
    b.put("now_r", now["radio"])
    b.put("now_s", now["radiation"])
    b.put("now_g", now["geomagnetic"])
    b.put("lbl", now["geomagnetic"])
    for name in ("radio", "radiation", "geomagnetic"):
        before = _by_day(observed[name]).get(_ordinal(now[name]) - 1)
        if before is not None and before.value is not None:
            b.put(f"yd_{name}", before)
            b.derive(f"chg_{name}", C.f01_change(now[name], before))
    n_f = b.derive("n_f", C.f12_count(days["g"], COUNT_DAY))
    stats = {}
    for name in ("minor", "major", "s"):
        series = days[name]
        stats[name] = (b.derive(f"max_{name}", C.f09_max(series)), b.derive(f"mean_{name}", C.f07_rolling_mean(series)), b.derive(f"chg_{name}_f", C.f01_change(series[-1], series[0], require="earlier")))
    max_g = b.derive("max_g", C.f09_max(days["g"]))
    if n_f is None or max_g is None or any(item is None for item in (stats["minor"][0], stats["major"][0], stats["s"][0])):
        return Insufficient("NOT_COMPARABLE", "예보 값을 계산할 수 없어 글을 만들지 않는다")
    for number, day_index in enumerate(range(len(days["g"])), start=1):
        for name in ("g", "minor", "major", "s"):
            b.put(f"f{name}{number}", days[name][day_index])
    obs_rows = [["⟦D:now_g⟧(지금)", "⟦F:now_r⟧", "⟦F:now_s⟧", "⟦F:now_g⟧"]]
    if all(f"yd_{name}" in b.slots for name in ("radio", "radiation", "geomagnetic")):
        obs_rows.append(["⟦D:yd_geomagnetic⟧(어제)", "⟦F:yd_radio⟧", "⟦F:yd_radiation⟧", "⟦F:yd_geomagnetic⟧"])
    fc_rows = [[f"⟦D:fg{number}⟧", f"⟦F:fminor{number}⟧", f"⟦F:fmajor{number}⟧", f"⟦F:fs{number}⟧", f"⟦F:fg{number}⟧"] for number in range(1, len(days["g"]) + 1)]

    titles = ["NOAA 우주기상 등급 현황과 예보, ⟦D:cur⟧ 기준 — 숫자로 읽기", "NOAA 우주기상 등급 현황과 예보, ⟦D:cur⟧ 기준"]
    leads = ["⟦D:cur⟧ 기준 NOAA가 관측한 지자기 폭풍 등급은 ⟦F:now_g⟧입니다(향후 ⟦V:n_f⟧⟦U:n_f⟧ 예보에서 전파 교란 낮은 등급 확률의 최댓값은 ⟦F:max_minor⟧입니다)."]
    glance = ["- 관측(⟦D:now_g⟧): 전파 교란 등급 ⟦F:now_r⟧, 방사선 폭풍 등급 ⟦F:now_s⟧, 지자기 폭풍 등급 ⟦F:now_g⟧",
              "- 예보 기간: 향후 ⟦V:n_f⟧⟦U:n_f⟧(관측이 아니라 NOAA가 낸 예보입니다)",
              "- 예보 — 전파 교란 낮은 등급 확률의 최댓값 ⟦F:max_minor⟧, 평균 ⟦F:mean_minor⟧",
              "- 예보 — 전파 교란 높은 등급 확률의 최댓값 ⟦F:max_major⟧, 평균 ⟦F:mean_major⟧",
              "- 예보 — 방사선 폭풍 확률의 최댓값 ⟦F:max_s⟧, 평균 ⟦F:mean_s⟧",
              "- 예보 — 지자기 폭풍 등급의 최댓값 ⟦F:max_g⟧"]
    numbers = [SCALE_ABOUT, "위쪽 표는 NOAA가 관측한 등급(어제와 지금), 아래쪽 표는 NOAA가 낸 예보(날짜별 확률과 지자기 폭풍 등급 예보)입니다. 값은 제공처 자료 그대로이고 최댓값·평균·차이는 이 글이 직접 계산했습니다.",
               md_table(["기준일", "전파 교란 등급", "방사선 폭풍 등급", "지자기 폭풍 등급"], obs_rows, ["l", "r", "r", "r"]),
               md_table(["예보 날짜", "전파 교란 낮은 등급 확률 예보", "전파 교란 높은 등급 확률 예보", "방사선 폭풍 확률 예보", "지자기 폭풍 등급 예보"], fc_rows, ["l", "r", "r", "r", "r"]),
               "확률 열은 NOAA가 내놓은 예보 확률이고 관측값이 아닙니다. 낮은 등급은 가장 낮은 단계와 그다음 단계를 묶은 구간이고 높은 등급은 그보다 위의 단계 전체를 묶은 구간입니다."]
    sentences = ["예보 기간 동안 전파 교란 낮은 등급 확률의 예보는 최대 ⟦F:max_minor⟧, 평균 ⟦F:mean_minor⟧입니다. 높은 등급 확률의 예보는 최대 ⟦F:max_major⟧, 평균 ⟦F:mean_major⟧입니다.",
                 "방사선 폭풍 확률의 예보는 최대 ⟦F:max_s⟧, 평균 ⟦F:mean_s⟧입니다. 지자기 폭풍 등급 예보의 최댓값은 ⟦F:max_g⟧입니다."]
    sign = R.direction(stats["minor"][2], context) if stats["minor"][2] is not None else None
    if sign is not None:
        word = "높아지는" if sign > 0 else "낮아지는" if sign < 0 else "같은"
        sentences.append(f"예보 시작 날에서 마지막 날까지 전파 교란 낮은 등급 확률의 예보는 ⟦A:chg_minor_f⟧ {word} 쪽입니다." if sign != 0 else "예보 시작 날과 마지막 날의 전파 교란 낮은 등급 확률 예보는 같습니다.")
    reading = ["**이 글의 해석**: " + " ".join(sentences),
               "예보는 관측이 아니라 NOAA가 낸 값이라 틀릴 수 있습니다. 이 글은 예보 숫자를 옮기고 계산만 했고 지구에 어떤 영향이 있을지, 실제로 어떤 일이 일어날지는 말하지 않습니다."]
    caveats = ["- 관측과 예보: 어제와 지금의 등급은 관측이고, 날짜별 확률과 등급은 예보입니다. 예보를 관측처럼 읽지 마세요. 날짜는 협정 세계시(UTC)입니다.",
               "- 확률의 뜻: 확률은 그 날짜에 해당 등급의 사건이 일어날 가능성을 NOAA가 숫자로 낸 값입니다. 이 글은 확률의 근거를 알지 못합니다.",
               "- 등급은 순서 척도: 등급 단계는 크기 순서만 뜻하는 값이라 비율로 견주지 않고 차이만 적었습니다."]
    return Draft(now["geomagnetic"], b.slots, titles, leads, [(R.H_GLANCE, [md_bullets(glance)]), (R.H_NUMBERS, numbers), (R.H_READING, reading)], caveats,
                 [now["geomagnetic"].label_ko, "등급 현황", "예보", "우주날씨"], now["geomagnetic"].topic, now["geomagnetic"].as_of, b.registry, b.skipped,
                 (recipe.recipe_id, KEY_SCALE_GEOMAGNETIC, "-", now["geomagnetic"].as_of), context)


R04_NOREGION_SERIES = Recipe(
    "R04_NOREGION_SERIES", 1, "지역 없는 시계열",
    "지역이 없는 한 지표의 일별·월별 시계열(구간 값은 하루 최댓값으로)에서 최신값·바로 앞 기간 대비·최근 평균·앞 창과의 비교·전년 같은 달 대비·표시 기간의 범위를 만든다.",
    SPACE_DOMAINS, ("F01_change", "F02_pct_change", "F03_yoy", "F06_diff_from_mean", "F07_rolling_mean", "F09_max", "F10_min", "F12_count", "F15_day_max", "F17_season_rank", "F18_last_lower", "F19_months_between"),
    5, 120, plan_noregion_series, calc_from_formulas=True)
R05_THRESHOLD_COUNT = Recipe(
    "R05_THRESHOLD_COUNT", 1, "기준 이상 개수",
    "하루 최대 Kp 가 폭풍 기준 이상인 날·구간 수, 또는 X선 플레어의 등급별 건수를 기준값 Fact 와 견주어 센다(0 도 값이다).",
    SPACE_DOMAINS, ("F07_rolling_mean", "F09_max", "F10_min", "F12_count", "F15_day_max", "F16_count_between"),
    5, 10, plan_threshold_count, calc_from_formulas=True)
R06_SCALE_OUTLOOK = Recipe(
    "R06_SCALE_OUTLOOK", 1, "등급 현황과 예보",
    "NOAA 우주기상 등급(어제·지금)과 향후 며칠의 확률·지자기 폭풍 등급 예보를 표로 놓고 최댓값·평균·변화를 만든다(예보는 관측과 구분해 쓴다).",
    SPACE_DOMAINS, ("F01_change", "F07_rolling_mean", "F09_max", "F12_count"),
    2, 3, plan_scale_outlook, calc_from_formulas=True)

NOREGION_RECIPES = {r.recipe_id: r for r in (R04_NOREGION_SERIES, R05_THRESHOLD_COUNT, R06_SCALE_OUTLOOK)}
