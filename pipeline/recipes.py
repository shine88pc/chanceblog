"""규칙 기반 한국어 초안의 Recipe(틀) — 어떤 Fact 가 필요한지·어떤 계산을 하는지·어떤 절과 문장 틀을 쓰는지·제목 틀·분류·태그·주의 문구를 선언하는 데이터와 함수. AI 없음.

표준 라이브러리와 이 경로의 새 모듈(`pipeline/facts.py`·`pipeline/calc.py`·`pipeline/fact_topics.py`)만 쓴다. 입출력·시계·난수 없음 — `today` 는 인자다.

글 틀의 규칙(시험이 모두 확인한다):
- 틀 안의 숫자·날짜는 모두 참조 표시(`⟦F:칸이름⟧` 꼴)다. 틀에 아라비아 숫자나 '두 배·세 곳·절반·첫째' 같은 수 표현을 직접 쓰지 않는다(`facts.untraced_numbers`).
- 외부 문장을 쓰지 않는다. 라벨·지역 이름은 Fact 가 가진 우리 낱말이고 제공처의 설명 문장은 어디에도 복사하지 않는다.
- 참조 표시 바로 뒤에 은·는·이·가·을·를·과·와·(으)로 같이 앞말의 받침에 따라 달라지는 조사를 붙이지 않는다(`의`·`에`·`에서`·`보다`·`까지`·`입니다` 같은 안 변하는 말만).
  라벨 뒤에는 '값은' 같은 고정 낱말을 둔다. 받침 판정 코드를 두지 않고 틀을 짜서 피한다.
- 과장·단정·원인 단정·예측·투자·법률·건강 조언 표현을 쓰지 않는다(`FORBIDDEN_PHRASES`). '해석'은 '이 글의 해석'으로 밝히고 원인을 말하지 않는다 — 이 글이 아는 것은 숫자뿐이다.
- 문장 변주는 입력에서 계산되는 결정적 규칙(부호·같음·동률·기록 여부·자료 유무)으로만 한다. 난수 없음.
- 비교할 수 없는 값(단위·정의·기준일·지역 수준이 다름)이 있으면 그 문장을 만들지 않는다.
- '같다·달라지지 않았다·높다·낮다' 는 **글에 보이는 두 값**을 기준으로 정한다(`verdict`). 보이는 값과 어긋나는 말이 나오게 되면 글을 만들지 않는다(`DISPLAY_INCONSISTENT`).
- 동률인 최고·최저는 한 곳·한 기간으로 단정하지 않고 '같은 값 N곳(번)'으로 쓴다. 관측 개수를 기간으로 말하지 않는다(불규칙한 기간이면 '관측 N개').

설명: docs/FACT_PATH.md
"""
from dataclasses import dataclass, field
from typing import Any, Callable

from pipeline import calc as C
from pipeline import fact_topics as T
from pipeline import facts as F

MIN_STORY_CHARS = 1000      # 생성기 하한(국문, 공백·표시 기호 제외, 출처 목록 제외)과 같다
MAX_TITLE_CHARS = 60
DESCRIPTION_MIN, DESCRIPTION_MAX = 60, 155
TABLE_ROWS = 12             # 시계열 표의 최근 기간 수
CONTEXT_ROWS = 6            # 기록 표의 최근 기간 수
COMPARE_ROWS = 12           # 지역 비교 표의 최대 지역 수
OBSERVATION_UNIT = "개"     # 기간이 이어지지 않는 자료의 개수를 세는 말('관측 N개')
TIE_UNIT = "번"             # 같은 값이 몇 번 나오는지 세는 말

# ----------------------------------------------------------------------------
# 글에 쓰지 않는 표현(규칙 하나가 시험 하나에 걸린다). 부분 문자열로 찾고, 공백·가운뎃점을 지운 글에서도 찾는다(`무 조건` 도 `무조건` 이다)
# ----------------------------------------------------------------------------
FORBIDDEN_PHRASES = {
    "건강": ("치료", "완치", "처방", "복용", "예방 효과", "효능", "부작용", "환자", "질환", "질병", "증상", "진단"),
    "단정": ("보장", "반드시", "확실히", "확실하게", "무조건", "틀림없이", "분명히", "단언", "명백히", "의심의 여지"),
    "즉시 효과": ("즉시 효과", "바로 효과", "즉각적인 효과", "당장 효과"),
    "과장": ("역대급", "폭등", "폭락", "급등", "급락", "사상 최고", "사상 최저", "충격", "대박", "놀라운", "경악", "쇼크", "초유", "전무후무"),
    "원인 단정": ("때문입니다", "때문에", "때문이다", "탓입니다", "덕분에", "덕분입니다", "원인은", "영향으로", "로 인해", "으로 인해", "으로 인한"),
    "투자·권유": ("투자 추천", "매수", "매도", "수익률", "유망", "사야 합니다", "팔아야", "추천합니다", "권합니다", "권유", "주식", "코인", "펀드", "증권"),
    "법률": ("위법입니다", "불법입니다", "처벌", "법적 책임", "소송", "판결", "재판"),
    "예측": ("예상됩니다", "전망됩니다", "전망입니다", "예측됩니다", "오를 것", "내릴 것", "곧 오", "계속 오"),
    "번역투": ("에 의해", "를 통해", "을 통해", "에 대한", "것으로 나타났"),
}
# 앞말의 받침에 따라 달라지는 조사 — 참조 표시 바로 뒤에 두지 않는다
_VARYING_AFTER_MARKER = r"(?:은|는|이|가|을|를|과|와|으로|로|였)"
VARYING_PARTICLE_PATTERNS = (
    F.REF_RE.pattern + _VARYING_AFTER_MARKER,
    r"[)]" + _VARYING_AFTER_MARKER,
    r"은\(는\)|는\(은\)|이\(가\)|가\(이\)|을\(를\)|를\(을\)|과\(와\)|와\(과\)|\(으\)로|\(이\)다",
)
# 같은 글에서 다른 글자 체계가 섞이지 않게: 틀의 글자는 한글·숫자 표시·문장 부호·표 기호뿐이고 영문자는 우리 낱말(라벨·단위)에서만 온다
BLOCKED_TEXT_CHARS = ("~", "～", "〜", "⟦", "⟧", "{", "}")

# ----------------------------------------------------------------------------
# 글의 뼈대(절 제목)와 모든 글에 같은 안내
# ----------------------------------------------------------------------------
H_GLANCE = "한눈에"
H_NUMBERS = "숫자로 보기"
H_READING = "비교·해석"
H_CAUTION = "이 숫자를 읽을 때 주의"
H_SOURCE = "출처"
SECTION_ORDER = (H_GLANCE, H_NUMBERS, H_READING, H_CAUTION, H_SOURCE)

# 제목 정책(R18, 운영자 승인 2026-11-10 — 결정 D-200): **모든 Fact 글의 제목에는 값(숫자)을 넣지 않고 이름(`L`)·지역(`R`)·기준일(`D`·`T`)만 쓴다.** 값이 제목에 있으면 제목이
# 이력·태그·분류와 함께 AI 입력이 되는 길(감사 R18)이 열리기 때문이다. 기준일 참조는 허용한 칸 이름에서만 — 최신 기준일(`main`·`cur`)·표의 처음·끝 줄(`first_row`·`last_row`)·읽은 자료의 처음(`first`)·수집일(`record`).
# 설명(description)과 본문에는 값이 있어도 된다(설명은 AI 입력이 아니다 — 감사 보고서 §4·§5-2: AI 가 읽는 칸은 제목·태그·분류뿐).
TITLE_KINDS = frozenset("LRDT")
TITLE_DATE_SLOTS = frozenset({("D", "main"), ("D", "cur"), ("D", "first_row"), ("D", "last_row"), ("D", "first"), ("T", "record")})
TITLE_POLICY_R01 = ("⟦R:main⟧ ⟦L:main⟧, ⟦D:first_row⟧부터 ⟦D:last_row⟧까지 — 숫자로 읽기", "⟦R:main⟧ ⟦L:main⟧, ⟦D:main⟧ 기준 — 숫자로 읽기", "⟦L:main⟧, ⟦D:main⟧ 기준 — 숫자로 읽기")
TITLE_POLICY_R02 = ("⟦D:main⟧ ⟦L:main⟧ 지역 비교 — 숫자로 읽기", "⟦D:main⟧ ⟦L:main⟧ 지역 비교")
TITLE_POLICY_R03 = ("⟦R:main⟧ ⟦L:main⟧ 기록 위치, ⟦D:first⟧부터 ⟦D:main⟧까지 — 숫자로 읽기", "⟦R:main⟧ ⟦L:main⟧ 기록 위치, ⟦D:main⟧ 기준 — 숫자로 읽기",
                    "⟦L:main⟧ 기록 위치, ⟦D:main⟧ 기준 — 숫자로 읽기")


def title_template_problem(template):
    """제목 틀이 정책을 어기는가: 값 참조(`F`·`S`·`A`·`V`·`U`)나 허용하지 않은 기준일 칸이 있으면 사유 글자, 없으면 None."""
    for kind, ref in F.references(template):
        if kind not in TITLE_KINDS:
            return "제목에 값 참조 표시가 있음"
        if kind in "DT" and (kind, ref) not in TITLE_DATE_SLOTS:
            return "제목에 허용하지 않은 기준일 칸이 있음"
    return None

SOURCE_LINK_TOKEN = "@SOURCE_LINK@"
INTRO_TEMPLATE = (f"이 글의 값은 {SOURCE_LINK_TOKEN}에서 ⟦T:record⟧에 받아 옮긴 구조화 데이터입니다. "
                  "증감·변화율·평균·순위 같은 값은 이 글이 그 숫자로 직접 계산했습니다.")
# 안 변하는 조사(에서)로 이어지게: `[공식 자료](주소)에서`
CAUTION_COMMON = (
    "- 지표와 단위: ⟦L:main⟧(단위 ⟦U:main⟧). 다른 기관의 같은 이름 지표와는 정의가 다를 수 있어 직접 견주지 않았습니다.",
    "- 잠정치와 개정: 가장 최근 기간의 값은 잠정치일 수 있고 나중에 고쳐질 수 있습니다. 이 글은 ⟦T:record⟧에 받은 값을 그대로 옮겼으며 이후 개정 여부는 확인하지 않았습니다.",
    "- 계산한 값: 증감·변화율·평균·순위는 이 글이 직접 계산했습니다. 계산은 정밀한 값으로 하고 보여 줄 때만 반올림하므로, 보이는 값끼리 다시 계산하면 끝자리가 다를 수 있습니다.",
    "- 이 글이 아는 것: 이 글이 아는 것은 위 숫자뿐입니다. 숫자가 달라진 원인을 이 자료만으로는 알 수 없어 설명하지 않았습니다.",
)
# 글이 실제로 계산한 것만 말하는 안내(S2AFIX2 N5): `Recipe.calc_from_formulas` 가 참이면(지역 없는 틀 R04–R06) 위 두 문장('증감·변화율·평균·순위 …')의 계산 목록을 이 글이 쓴 계산식에서 만든다 —
# Kp 글은 증감·변화율·순위를 계산하지 않는데 고정 문장은 그것을 나열해 같은 글의 주의 줄('날짜 사이의 증감은 계산하지 않았고')과 어긋났다. 기존 틀 R01–R03 은 고정 문장 그대로다(출력 불변).
# 계산식 번호 → 독자용 낱말(표시 순서대로). 같은 낱말(평균)은 한 번만 쓴다. 숫자·수 낱말은 없다.
CALC_WORDS = (
    ("F15_day_max", "하루 최대값"), ("F01_change", "증감"), ("F02_pct_change", "변화율"), ("F03_yoy", "전년 대비 변화율"), ("F04_rank", "순위"), ("F05_share", "비중"),
    ("F07_rolling_mean", "평균"), ("F08_mean", "평균"), ("F14_median", "중앙값"), ("F06_diff_from_mean", "평균과의 차이"), ("F13_gap", "격차"), ("F09_max", "최고값"), ("F10_min", "최저값"),
    ("F11_range_position", "범위 안의 위치"), ("F12_count", "개수"), ("F16_count_between", "기준별 개수"),
)
CALC_WORD_OF = dict(CALC_WORDS)
INTRO_CALC_SENTENCE = "{words} 같은 값은 이 글이 그 숫자로 직접 계산했습니다."
CAUTION_CALC_LINE = "- 계산한 값: {words} 같은 값은 이 글이 직접 계산했습니다. 계산은 정밀한 값으로 하고 보여 줄 때만 반올림하므로, 보이는 값끼리 다시 계산하면 끝자리가 다를 수 있습니다."


def calc_words(formula_ids):
    """글이 쓴 계산식 번호(집합·목록) → '평균·최고값·개수' 같은 독자용 낱말 목록(표시 순서·같은 낱말은 한 번만). 비었거나 모르는 계산식이 있으면 None — 이때는 기존 고정 문장을 그대로 쓴다."""
    wanted = set(formula_ids or ())
    if not wanted or not wanted <= set(CALC_WORD_OF):
        return None
    words = []
    for formula_id, word in CALC_WORDS:
        if formula_id in wanted and word not in words:
            words.append(word)
    return "·".join(words)


def intro_template(words=None):
    """첫 문단 뒤의 자료 안내 틀: words 가 있으면 계산 목록을 이 글이 쓴 것으로, 없으면 고정 문장."""
    if words is None:
        return INTRO_TEMPLATE
    return INTRO_TEMPLATE.replace("증감·변화율·평균·순위 같은 값은 이 글이 그 숫자로 직접 계산했습니다.", INTRO_CALC_SENTENCE.format(words=words))


def caution_common(words=None):
    """모든 글이 나누는 주의 줄 넷: words 가 있으면 '계산한 값' 줄의 목록을 이 글이 쓴 것으로 바꾼다."""
    if words is None:
        return CAUTION_COMMON
    return tuple(CAUTION_CALC_LINE.format(words=words) if line.startswith("- 계산한 값:") else line for line in CAUTION_COMMON)


NOTICE_TEMPLATE = ("*이 글은 사람이 쓴 글이 아니라, 공개된 구조화 통계를 정해진 규칙으로 자동 정리해 만든 글입니다. "
                   "일반 정보이며 어떤 결정의 근거로 쓰도록 만든 글이 아닙니다. 최신 값은 위 출처에서 직접 확인해 주세요.*")
READER_NOTE_PREFIX = "- 제공처 안내: "      # Provider 의 `reader_notes`(독자용으로 승인된 문장)만 이 줄이 된다 — SRC 의 `exceptions`(감사 메모)는 읽지 않는다
MISSING_CELL = "자료 없음"      # 값이 없는(모름) 칸 — 0 으로 채우지 않는다
NA_CELL = "해당 없음"           # 비교할 값이 없어 계산하지 않은 칸

# 범주 → 글 분류(생성기의 한국어 분류 이름). 허용 목록(`pipeline/fact_topics.py`)의 범주만 있다 — 건강·금융 투자 조언 범주는 틀 자체가 없다
TOPIC_CATEGORY = {domain_id: domain.category for domain_id, domain in T.DOMAINS.items()}


class Insufficient:
    """글을 만들지 않은 이유(조립기의 결과). 거짓으로 읽힌다. code 는 짧은 영문 코드, detail 은 우리 문장."""
    __slots__ = ("code", "detail")

    def __init__(self, code, detail=""):
        self.code, self.detail = code, detail

    def __bool__(self):
        return False

    def __eq__(self, other):
        return isinstance(other, Insufficient) and (self.code, self.detail) == (other.code, other.detail)

    def __hash__(self):
        return hash((self.code, self.detail))

    def __repr__(self):
        return f"Insufficient({self.code!r}, {self.detail!r})"


@dataclass(frozen=True)
class Recipe:
    """글의 종류 하나. plan 은 (ctx) -> Draft 또는 Insufficient 를 돌려주는 순수 함수다. allowed_domains 는 이 Recipe 가 글로 쓰는 범주(허용 목록 `vocabulary` 안의 범주 id)다."""
    recipe_id: str
    version: int
    name_ko: str
    summary: str
    allowed_domains: tuple
    formulas: tuple
    min_points: int
    max_age_days: int
    plan: Callable
    min_story_chars: int = MIN_STORY_CHARS
    vocabulary: Any = T.VOCABULARY
    calc_from_formulas: bool = False          # 참이면 공통 안내 두 문장의 계산 목록을 글이 쓴 계산식에서 만든다(지역 없는 틀 R04–R06, S2AFIX2 N5)


@dataclass(frozen=True)
class PlanContext:
    recipe: Recipe
    facts: tuple          # 검증을 통과한 Fact(fact_id 순)
    today: Any            # datetime.date
    params: dict


@dataclass
class Draft:
    """plan 의 결과: 글의 재료(칸 이름으로 적은 틀). 조립기가 칸을 id 로 묶고(bind) 글로 바꾼다(render)."""
    main: Any
    slots: dict
    titles: list              # 선호 순서의 제목 틀
    leads: list               # 선호 순서의 첫 문단 틀(= description, 한 문장)
    sections: list            # [(절 제목, [블록 틀])]
    caveats: list             # 이 Recipe 만의 주의 줄 틀
    tags: list
    topic: str
    as_of: str
    registry: dict            # 만든 계산 결과 전부(id → DerivedFact) — 출처 추적용
    skipped: list             # [(칸, 계산식, 사유)]
    dedupe: tuple
    context: dict = field(default_factory=dict)      # 표시 소수 자리 {단위: 자리}(`facts.display_context`) — 글의 모든 숫자를 이 자리로 보인다


class Builder:
    """plan 안에서 칸과 계산 결과를 모으는 도우미."""

    def __init__(self):
        self.slots, self.registry, self.skipped = {}, {}, []

    def put(self, name, obj):
        self.slots[name] = obj
        return obj

    def derive(self, name, result):
        """계산 결과가 DerivedFact 면 칸에 담아 돌려주고, Skipped 면 기록하고 None(그 문장은 만들지 않는다)."""
        if isinstance(result, F.DerivedFact):
            self.registry[result.fact_id] = result
            self.slots[name] = result
            return result
        self.skipped.append((name, result.formula_id, result.reason))
        return None


# ----------------------------------------------------------------------------
# 도우미
# ----------------------------------------------------------------------------
def md_table(header, rows, aligns=None):
    """마크다운 표. aligns 는 칸마다 'l'·'r'(숫자 칸은 오른쪽)."""
    aligns = aligns or ["l"] * len(header)
    rule = ["---:" if a == "r" else "---" for a in aligns]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(rule) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def md_bullets(lines):
    return "\n".join(lines)


def direction(obj, context=None):
    """표시되는(반올림한) 값의 부호: 1·0·-1. 문장의 '높습니다·낮습니다·같습니다' 는 이것으로 고른다."""
    return F.display_sign(obj.value, obj.unit, context)


def verdict(cur, ref, diff, context=None):
    """두 값(cur 와 ref)을 **글에 보이는 모양**으로 견준 판정: 'SAME'(보이는 두 값이 같다)·'UP'·'DOWN'. 같음과 방향을 두 값의 표시값과 그 차이(diff)의 표시값이 모두 받쳐 주지 않으면
    (예: 보이는 값은 다른데 차이가 0.0 으로 보인다) None — 보이는 숫자와 어긋나는 말을 쓰지 않는다. 표시 소수 자리가 자료의 정밀도 이상이면(`facts.display_context`) None 은 나오지 않는다."""
    shown_cur = F.format_with_unit(cur.value, cur.unit, context=context)
    shown_ref = F.format_with_unit(ref.value, ref.unit, context=context)
    sign = F.display_sign(diff.value, diff.unit, context)
    if shown_cur == shown_ref:
        return "SAME" if sign == 0 else None
    order = (cur.value > ref.value) - (cur.value < ref.value)
    if sign == 0 or sign != order:
        return None
    return "UP" if sign > 0 else "DOWN"


def ordinal_of(fact):
    return F.parse_as_of(fact.as_of).ordinal


def topic_problem(recipe, facts):
    """Fact(또는 Fact 목록)의 키·라벨·단위·지역 낱말이 Recipe 가 허용한 범주의 허용 목록 안인지. 문제가 있으면 Insufficient(TOPIC_NOT_ALLOWED·UNKNOWN_TOPIC), 없으면 None."""
    if isinstance(facts, F.Fact):
        facts = (facts,)
    for fact in facts:
        found = T.fact_problem(fact, recipe.allowed_domains, recipe.vocabulary)
        if found is not None:
            return Insufficient(*found)
    return None


def freshness_problem(ctx, latest):
    """최신 기준일이 오늘보다 앞서 있으면(미래 자료) FUTURE_DATA, 너무 오래됐으면 STALE."""
    period = F.parse_as_of(latest.as_of)
    if F.period_start(period) > ctx.today:
        return Insufficient("FUTURE_DATA", "기준일이 오늘보다 뒤라 쓰지 않는다")
    if (ctx.today - F.period_end(period)).days > ctx.recipe.max_age_days:
        return Insufficient("STALE", "가장 최근 기준일이 너무 오래돼 새 글로 쓰지 않는다")
    return None


def numeric_groups(facts):
    """숫자 Fact 를 (제공처·지표·지역·지역 수준·단위) 계열로 묶는다. 값이 없는(모름) 것도 포함한다. {계열 키: [Fact(기준일 순)]}"""
    groups = {}
    for fact in facts:
        if fact.kind in F.NUMERIC_KINDS and F.parse_as_of(fact.as_of) is not None:
            groups.setdefault((fact.provider_id, fact.key, fact.region or "", fact.region_level or "", fact.unit), []).append(fact)
    for items in groups.values():
        items.sort(key=lambda f: (ordinal_of(f), f.fact_id))
    return groups


def _group_label(group_key):
    return f"{group_key[1]}/{group_key[2] or '-'}"


def is_regular(facts):
    """값이 있는 Fact 들의 기준일이 빠짐없이 이어지는가(월이면 매달, 분기면 매 분기). 이어질 때만 개수를 '개월·분기·년' 이라는 기간으로 말할 수 있다."""
    ordinals = sorted({ordinal_of(f) for f in facts})
    return bool(ordinals) and ordinals[-1] - ordinals[0] + 1 == len(ordinals)


def pick_series(ctx, *, min_points):
    """시계열 Recipe 가 쓸 계열 하나를 고른다. 인자(`key`·`region`)로 지정할 수 있고, 없으면 가장 최근 기준일·가장 많은 점·키·지역 순으로 정한다(결정적).
    허용 목록 밖 계열·지역 없는 계열은 고르지 않는다. 돌려주는 것: (계열 키, 모든 항목 목록) 또는 Insufficient."""
    groups = numeric_groups(ctx.facts)
    if not groups:
        return Insufficient("NO_FACTS", "쓸 수 있는 숫자 Fact 가 없다")
    want_key, want_region = ctx.params.get("key"), ctx.params.get("region")
    allowed, blocked, no_region = [], None, None
    for gkey, items in groups.items():
        if (want_key and gkey[1] != want_key) or (want_region and gkey[2] != want_region):
            continue
        problem = topic_problem(ctx.recipe, items)
        if problem is not None:
            if blocked is None:
                blocked = problem               # 가장 먼저 막힌 계열의 사유(막힌 주제인지 허용 목록 밖인지)를 그대로 돌려준다(Insufficient 는 거짓으로 읽히므로 `or` 로 고르지 않는다)
            continue
        if not gkey[2]:
            if no_region is None:
                no_region = Insufficient("NO_REGION_SERIES", "지역이 없는 계열은 이 Recipe 의 틀이 쓰지 않아 글로 만들지 않는다")
            continue
        valid = [f for f in items if f.value is not None]
        allowed.append((gkey, items, valid))
    if not allowed:
        for reason in (blocked, no_region):
            if reason is not None:
                return reason
        return Insufficient("NO_FACTS", "조건에 맞는 계열이 없다")
    enough = [entry for entry in allowed if len(entry[2]) >= min_points]
    if not enough:
        return Insufficient("TOO_FEW_POINTS", "값이 있는 기간이 모자라 시계열 글을 만들지 않는다")
    enough.sort(key=lambda e: (-ordinal_of(e[2][-1]), -len(e[2]), e[0][1], e[0][2]))
    gkey, items, valid = enough[0]
    kinds = {F.parse_as_of(f.as_of).granularity for f in items}
    if len(kinds) != 1 or kinds & {"instant"}:
        return Insufficient("MIXED_PERIOD_KIND", "기간 단위가 섞였거나 시각 자료라 시계열 글을 만들지 않는다")
    ordinals = [ordinal_of(f) for f in items]
    if len(set(ordinals)) != len(ordinals):
        return Insufficient("DUPLICATE_PERIOD", "같은 기간의 값이 둘 이상이라 시계열 글을 만들지 않는다")
    if len({f.label_ko for f in items}) != 1 or len({f.region_label_ko for f in items}) != 1:
        return Insufficient("INCONSISTENT_LABELS", "같은 계열인데 라벨이나 지역 이름이 서로 달라 글로 만들지 않는다")
    return gkey, items


def _tags(main, extra=("공개 통계", "숫자로 읽기")):
    out = [t for t in (main.label_ko, getattr(main, "region_label_ko", None)) if t]
    return out + list(extra)


def _dedupe(recipe_id, main):
    return (recipe_id, main.key, main.region or "-", main.as_of)


# ----------------------------------------------------------------------------
# Recipe 1 — 시계열 변화
# ----------------------------------------------------------------------------
@F.exact
def plan_time_series(ctx):
    recipe = ctx.recipe
    picked = pick_series(ctx, min_points=recipe.min_points)
    if isinstance(picked, Insufficient):
        return picked
    _gkey, items = picked
    valid = [f for f in items if f.value is not None]
    cur = valid[-1]
    stale = freshness_problem(ctx, cur)
    if stale is not None:
        return stale
    context = F.display_context(valid)          # 한 글의 모든 숫자는 단위 표와 자료의 정밀도 중 큰 자리로 보인다(자료의 값을 깎지 않는다)
    granularity = F.parse_as_of(cur.as_of).granularity
    regular = is_regular(valid)
    count_unit = F.GRANULARITY_UNIT[granularity] if regular else OBSERVATION_UNIT       # 기간이 빠진 자료는 '15개월'이 아니라 '관측 13개'
    obs = "" if regular else "관측 "
    ratio = F.ratio_ok(cur.unit)
    b = Builder()
    b.put("main", cur)
    by_ord = {ordinal_of(f): f for f in valid}
    cur_ord = ordinal_of(cur)
    window_unit = F.GRANULARITY_UNIT[granularity]

    prev = by_ord.get(cur_ord - 1)
    chg = pct = None
    if prev is not None:
        b.put("prev", prev)
        chg = b.derive("chg", C.f01_change(cur, prev))
        pct = b.derive("pct", C.f02_pct_change(cur, prev)) if ratio else None
    yago = next((f for f in valid if f.as_of == F.shift_year(cur.as_of, -1)), None)
    yoy = yoy_chg = None
    if yago is not None:
        b.put("yago", yago)
        yoy = b.derive("yoy", C.f03_yoy(cur, yago)) if ratio else None
        yoy_chg = b.derive("yoy_chg", C.f01_change(cur, yago, require="earlier"))
    window = [by_ord[o] for o in (cur_ord - 2, cur_ord - 1, cur_ord) if o in by_ord]
    mean3 = n3 = dmean = None
    if len(window) == 3:
        mean3 = b.derive("mean3", C.f07_rolling_mean(window))
        n3 = b.derive("n3", C.f12_count(window, window_unit))
        if mean3 is not None:
            dmean = b.derive("dmean", C.f06_diff_from_mean(cur, mean3))

    chg_verdict = verdict(cur, prev, chg, context) if chg is not None else None
    yoy_verdict = verdict(cur, yago, yoy_chg, context) if yoy_chg is not None else None
    if (chg is not None and chg_verdict is None) or (yoy_chg is not None and yoy_verdict is None):
        return Insufficient("DISPLAY_INCONSISTENT", "보이는 값과 어긋나는 같음·높낮이 표현이 나오게 되어 글을 만들지 않는다")

    shown = [f for f in items if ordinal_of(f) > cur_ord - TABLE_ROWS]
    shown_valid = [f for f in shown if f.value is not None]
    hi = b.derive("hi", C.f09_max(shown_valid))
    lo = b.derive("lo", C.f10_min(shown_valid))
    first_row, last_row = shown[0], shown[-1]
    b.put("first_row", first_row)
    b.put("last_row", last_row)
    n_all = b.derive("n_all", C.f12_count(valid, count_unit))

    rows = []
    for number, fact in enumerate(reversed(shown), start=1):
        slot = f"r{number}"
        b.put(slot, fact)
        if fact.value is None:
            rows.append([f"⟦D:{slot}⟧", MISSING_CELL, NA_CELL] + ([NA_CELL] if ratio else []))
            continue
        before = by_ord.get(ordinal_of(fact) - 1)
        row_chg = row_pct = None
        if before is not None:
            row_chg = b.derive(f"c{number}", C.f01_change(fact, before))
            row_pct = b.derive(f"p{number}", C.f02_pct_change(fact, before)) if ratio else None
        row = [f"⟦D:{slot}⟧", f"⟦F:{slot}⟧", f"⟦S:c{number}⟧" if row_chg else NA_CELL]
        if ratio:
            row.append(f"⟦S:p{number}⟧" if row_pct else NA_CELL)
        rows.append(row)

    # 같은 값이 표에 몇 번 나오는지(동률) — 최고·최저를 한 기간으로 단정하지 않는다
    has_range = hi is not None and lo is not None and len(shown_valid) >= 2 and hi.value != lo.value
    flat_table = hi is not None and lo is not None and len(shown_valid) >= 2 and hi.value == lo.value
    hi_ties = [f for f in shown_valid if hi is not None and f.value == hi.value]
    lo_ties = [f for f in shown_valid if lo is not None and f.value == lo.value]
    n_hi = b.derive("n_hi", C.f12_count(hi_ties, TIE_UNIT)) if has_range and len(hi_ties) > 1 else None
    n_lo = b.derive("n_lo", C.f12_count(lo_ties, TIE_UNIT)) if has_range and len(lo_ties) > 1 else None

    # -- 제목·첫 문단(= 설명, 한 문장) --------------------------------------
    titles, leads = [], []
    span = f", 이 글이 읽은 {obs}⟦V:n_all⟧⟦U:n_all⟧ 자료의 마지막 값" if n_all is not None else ""      # 날짜 표기가 짧은 연·분기 자료나 짧은 라벨이면 첫 문단이 60자에 못 미쳐 이 덧말이 있는 후보로 넘어간다
    if chg is not None:
        if chg_verdict == "SAME":
            head = "⟦R:main⟧의 ⟦L:main⟧ 값은 ⟦D:prev⟧(⟦F:prev⟧)에서 달라지지 않은 ⟦F:main⟧입니다"
        else:
            up = chg_verdict == "UP"
            head = f"⟦R:main⟧의 ⟦L:main⟧ 값은 ⟦D:prev⟧(⟦F:prev⟧)보다 ⟦A:chg⟧ {'높은' if up else '낮은'} ⟦F:main⟧입니다"
        leads.append(head + "(⟦D:main⟧ 기준).")
        if span:
            leads.append(head + f"(⟦D:main⟧ 기준{span}).")
    titles += TITLE_POLICY_R01        # 제목에는 값을 넣지 않는다(이름·지역·기준일만) — 값은 설명과 본문에(D-200)
    if n_all is not None:
        leads.append(f"⟦D:main⟧ 기준 ⟦R:main⟧의 ⟦L:main⟧ 값은 ⟦F:main⟧입니다(이 글이 읽은 {obs}⟦V:n_all⟧⟦U:n_all⟧ 자료의 마지막 값).")
        if has_range:
            leads.append(f"⟦D:main⟧ 기준 ⟦R:main⟧의 ⟦L:main⟧ 값은 ⟦F:main⟧입니다(이 글이 읽은 {obs}⟦V:n_all⟧⟦U:n_all⟧ 자료의 마지막 값이며 최저는 ⟦F:lo⟧, 최고는 ⟦F:hi⟧입니다).")

    # -- 한눈에 ---------------------------------------------------------------
    glance = ["- 최신 값: ⟦F:main⟧(⟦D:main⟧ 기준)"]
    if chg is not None:
        tail = ", 변화율 ⟦S:pct⟧" if pct is not None else ""
        glance.append(f"- 바로 앞 기간 대비: ⟦S:chg⟧{tail} (견준 기간 ⟦D:prev⟧, 그때 값 ⟦F:prev⟧)")
    if yoy_chg is not None:
        tail = ", 변화율 ⟦S:yoy⟧" if yoy is not None else ""
        glance.append(f"- 전년 같은 {'달' if granularity == 'month' else '기간'} 대비: ⟦S:yoy_chg⟧{tail} (견준 기간 ⟦D:yago⟧, 그때 값 ⟦F:yago⟧)")
    if mean3 is not None and n3 is not None:
        glance.append("- 최근 ⟦V:n3⟧⟦U:n3⟧ 평균: ⟦F:mean3⟧")
    if has_range:
        lo_part = "최저 ⟦F:lo⟧(⟦D:lo⟧)" if n_lo is None else "최저 ⟦F:lo⟧(같은 값 ⟦V:n_lo⟧⟦U:n_lo⟧, 가장 나중 ⟦D:lo⟧)"       # 동률이면 한 기간으로 단정하지 않는다(D-151)
        hi_part = "최고 ⟦F:hi⟧(⟦D:hi⟧)" if n_hi is None else "최고 ⟦F:hi⟧(같은 값 ⟦V:n_hi⟧⟦U:n_hi⟧, 가장 나중 ⟦D:hi⟧)"
        glance.append(f"- 표시한 기간 안의 범위: {lo_part}에서 {hi_part}까지")

    # -- 숫자로 보기 ----------------------------------------------------------
    columns = "'바로 앞 기간 대비'와 '변화율' 열은" if ratio else "'바로 앞 기간 대비' 열은"
    numbers = [f"아래 표는 ⟦R:main⟧의 ⟦L:main⟧ 값을 ⟦D:first_row⟧부터 ⟦D:last_row⟧까지 보여 줍니다. 값은 제공처 자료 그대로이고, {columns} 이 글이 직접 계산했습니다. 최근 기간이 맨 위입니다.",
               md_table(["기준 기간", "값", "바로 앞 기간 대비 증감"] + (["바로 앞 기간 대비 변화율"] if ratio else []), rows, ["l", "r", "r"] + (["r"] if ratio else []))]
    notes = []
    if chg is not None:
        notes.append("증감의 단위는 ⟦U:chg⟧입니다.")
    notes.append("값이 비어 있는 기간은 '자료 없음'으로 적고, 제공처 자료에 기간 자체가 없으면 표에서 건너뜁니다. "
                 + ("앞 기간의 값이 없으면 증감과 변화율을 계산하지 않았습니다." if ratio else "앞 기간의 값이 없으면 증감을 계산하지 않았습니다. 이 단위는 기준점이 임의인 척도라 변화율은 계산하지 않았습니다."))
    if last_row is not cur:
        notes.append("가장 최근 기간(⟦D:last_row⟧)의 값은 자료에 없어, 값이 있는 마지막 기간 ⟦D:main⟧ 기준으로 최신 값을 정했습니다.")
    numbers.append(" ".join(notes))

    # -- 비교·해석(이 글의 해석) ------------------------------------------------
    reading = []
    sentences = []
    if dmean is not None:
        sign = direction(dmean, context)
        if sign > 0:
            sentences.append("최신 값은 최근 ⟦V:n3⟧⟦U:n3⟧ 평균 ⟦F:mean3⟧보다 ⟦A:dmean⟧ 높아서 직전 흐름의 위쪽에 있습니다.")
        elif sign < 0:
            sentences.append("최신 값은 최근 ⟦V:n3⟧⟦U:n3⟧ 평균 ⟦F:mean3⟧보다 ⟦A:dmean⟧ 낮아서 직전 흐름의 아래쪽에 있습니다.")
        else:
            sentences.append("최신 값은 최근 ⟦V:n3⟧⟦U:n3⟧ 평균 ⟦F:mean3⟧에서 거의 벗어나지 않았습니다.")
    if yoy_chg is not None:
        if yoy_verdict == "SAME":
            sentences.append("전년 같은 기간(⟦D:yago⟧)의 ⟦F:yago⟧에서도 달라지지 않았습니다.")
        else:
            sentences.append(f"전년 같은 기간(⟦D:yago⟧)의 ⟦F:yago⟧보다는 ⟦A:yoy_chg⟧ {'높습니다' if yoy_verdict == 'UP' else '낮습니다'}.")
    if flat_table:
        sentences.append("표에 적은 값이 모두 같아 가장 높은 값과 가장 낮은 값을 가르지 않았습니다.")
    elif has_range:
        if cur.value == hi.value:
            sentences.append("표에서 가장 높은 값이 바로 최신 값입니다." if n_hi is None
                             else "최신 값은 표에서 가장 높은 값과 같고, 그 값은 표에 ⟦V:n_hi⟧⟦U:n_hi⟧ 나옵니다.")
        elif cur.value == lo.value:
            sentences.append("표에서 가장 낮은 값이 바로 최신 값입니다." if n_lo is None
                             else "최신 값은 표에서 가장 낮은 값과 같고, 그 값은 표에 ⟦V:n_lo⟧⟦U:n_lo⟧ 나옵니다.")
        else:
            high = "표에서 가장 높은 값은 ⟦D:hi⟧의 ⟦F:hi⟧입니다." if n_hi is None else "표에서 가장 높은 값은 ⟦F:hi⟧입니다. 이 값은 표에 ⟦V:n_hi⟧⟦U:n_hi⟧ 나오며 가장 나중은 ⟦D:hi⟧입니다."
            low = "가장 낮은 값은 ⟦D:lo⟧의 ⟦F:lo⟧입니다." if n_lo is None else "가장 낮은 값은 ⟦F:lo⟧입니다. 이 값은 표에 ⟦V:n_lo⟧⟦U:n_lo⟧ 나오며 가장 나중은 ⟦D:lo⟧입니다."
            sentences.append(high + " " + low)
    reading.append("**이 글의 해석**: " + " ".join(sentences) if sentences else "**이 글의 해석**: 비교할 수 있는 값이 모자라 숫자만 옮겼습니다.")
    reading.append("짧은 오르내림만으로 흐름이 바뀌었다고 말하기는 어렵습니다. 이 자료만으로는 움직임의 원인을 알 수 없어, 여러 기간을 함께 놓고 평균과 범위만 계산했습니다.")

    caveats = ["- 계절과 달력: 기간마다 길이와 계절이 달라 연중에도 값이 오르내릴 수 있습니다. 자료가 있으면 전년 같은 기간과도 견주어 그 영향을 줄여 보았습니다."]
    return Draft(cur, b.slots, titles, leads,
                 [(H_GLANCE, [md_bullets(glance)]), (H_NUMBERS, numbers), (H_READING, reading)],
                 caveats, _tags(cur), cur.topic, cur.as_of, b.registry, b.skipped, _dedupe(recipe.recipe_id, cur), context)


# ----------------------------------------------------------------------------
# Recipe 2 — 지역 비교
# ----------------------------------------------------------------------------
def pick_cross_section(ctx, *, min_points):
    """같은 기준일·같은 지표·같은 단위·같은 지역 수준·같은 제공처의 지역 묶음 하나. 인자(`key`·`as_of`)로 지정하고, 없으면 가장 최근 기준일·가장 많은 지역·키 순.
    값이 없는(모름) 지역과 이 묶음과 견줄 수 없는 Fact 는 묶음에서 뺀다. 허용 목록 밖 지표는 고르지 않는다. 돌려주는 것: 묶음 항목 목록 또는 Insufficient."""
    want_key, want_as_of = ctx.params.get("key"), ctx.params.get("as_of")
    cells, refused, regionless = {}, {}, False
    for fact in ctx.facts:
        if fact.kind not in F.NUMERIC_KINDS or F.parse_as_of(fact.as_of) is None:
            continue
        if (want_key and fact.key != want_key) or (want_as_of and fact.as_of != want_as_of):
            continue
        if fact.region is None:
            if topic_problem(ctx.recipe, fact) is None:
                regionless = True
            continue
        cell = (fact.provider_id, fact.key, fact.as_of, fact.region_level, fact.unit)
        problem = topic_problem(ctx.recipe, fact)
        if problem is not None:
            refused.setdefault(cell, problem)            # 허용 목록 밖 낱말이 든 지역이 하나라도 있으면 그 묶음 전체를 쓰지 않는다 — 그 지역만 빼면 '가장 높은 곳'이 거짓이 될 수 있다
            continue
        cells.setdefault(cell, []).append(fact)
    for cell in refused:
        cells.pop(cell, None)
    blocked = next(iter(refused.values()), None)
    if not cells:
        if blocked is not None:
            return blocked
        if regionless:
            return Insufficient("NO_REGION_SERIES", "지역이 없는 계열이라 지역 비교 글을 만들지 않는다")
        return Insufficient("NO_FACTS", "지역별 숫자 Fact 가 없다")
    best = []
    for ckey, items in cells.items():
        usable = [f for f in items if f.value is not None]
        regions = {f.region for f in usable}
        if len(regions) != len(usable):
            return Insufficient("DUPLICATE_REGION", "같은 지역의 값이 둘 이상이라 지역 비교 글을 만들지 않는다")
        best.append((ckey, usable))
    enough = [entry for entry in best if len(entry[1]) >= min_points]
    if not enough:
        return Insufficient("TOO_FEW_REGIONS", "같은 기준일에 값이 있는 지역이 모자라 지역 비교 글을 만들지 않는다")
    enough.sort(key=lambda e: (-F.parse_as_of(e[0][2]).ordinal, -len(e[1]), e[0][1]))
    return enough[0][1]


@F.exact
def plan_region_compare(ctx):
    recipe = ctx.recipe
    group = pick_cross_section(ctx, min_points=recipe.min_points)
    if isinstance(group, Insufficient):
        return group
    ordered = sorted(group, key=lambda f: (f.value.copy_negate(), f.region, f.fact_id))       # 단항 `-` 는 전역 정밀도로 반올림되므로 copy_negate(D5)
    top = ordered[0]
    stale = freshness_problem(ctx, top)
    if stale is not None:
        return stale
    if len({f.label_ko for f in group}) != 1:
        return Insufficient("INCONSISTENT_LABELS", "같은 지표인데 라벨이 서로 달라 지역 비교 글을 만들지 않는다")
    context = F.display_context(group)
    b = Builder()
    mean = b.derive("mean", C.f08_mean(group))        # 같은 묶음(제공처·지표·기준일·단위·지역 수준이 같고 넷 이상)이라 계산할 수 없는 경우는 없다 — 그래도 못 만들면 아래 칸이 비어 틀 단계에서 글이 거절된다
    median = b.derive("median", C.f14_median(group))
    hi, lo = C.select_extreme(group, highest=True), C.select_extreme(group, highest=False)
    if hi.value == lo.value:
        return Insufficient("NO_VARIATION", "모든 지역의 값이 같아 순위와 최고·최저를 가를 수 없어 지역 비교 글을 만들지 않는다")
    b.put("main", hi)
    b.put("hi", hi)
    b.put("lo", lo)
    hi_set = [f for f in group if f.value == hi.value]
    lo_set = [f for f in group if f.value == lo.value]
    n_hi = b.derive("n_hi", C.f12_count(hi_set, "곳")) if len(hi_set) > 1 else None        # 동률이면 한 곳으로 단정하지 않고 '같은 값 N곳'
    n_lo = b.derive("n_lo", C.f12_count(lo_set, "곳")) if len(lo_set) > 1 else None
    n = b.derive("n", C.f12_count(group, "곳"))
    gap = b.derive("gap", C.f13_gap(hi, lo))
    mean_med = b.derive("mean_med", C.f13_gap(mean, median)) if mean is not None and median is not None else None
    hi_dm = b.derive("hi_dm", C.f06_diff_from_mean(hi, mean))
    lo_dm = b.derive("lo_dm", C.f06_diff_from_mean(lo, mean))
    diffs = [C.f06_diff_from_mean(fact, mean) for fact in ordered]
    # 지역이 짝수 곳이면 평균·중앙값이 표시 자리의 반 칸에 정확히 걸칠 수 있다(값 3.4·3.4·3.5·3.5 의 평균 3.45, 값 3.3·3.3·3.4·3.6 의 중앙값 3.35). 평균 3.45 는 3.5 로, 3.5 인 지역과의 차이
    # +0.05 는 +0.1 로 반올림되면 '같은 3.5 인데 평균보다 높다'가 되고, 평균 3.4 와 중앙값 3.35(→3.4)의 차이 0.05(→0.1)는 '같은 3.4 인데 차이가 있다'가 된다 — 그런 값이 있으면 그 단위의
    # 표시 자리를 한 칸 늘려 반올림 없이 보인다(D-152). 평균·중앙값·평균과의 차이·평균과 중앙값의 차이를 본다(N3). 평균과 중앙값의 차이는 자료 정밀도의 값에서는 평균·중앙값이 걸치지 않으면
    # 걸치지 않지만(시험이 확인한다) 같은 줄에서 견주는 말이 있으므로 빼지 않는다
    context = F.settle_context(context, [item for item in (mean, median, mean_med, hi_dm, lo_dm, *diffs) if isinstance(item, F.DerivedFact)])
    above, below, level, rows = [], [], [], []
    for number, fact in enumerate(ordered, start=1):
        b.put(f"v{number}", fact)
        diff = diffs[number - 1]
        if isinstance(diff, F.DerivedFact):
            (above if direction(diff, context) > 0 else below if direction(diff, context) < 0 else level).append(number)
        if number > COMPARE_ROWS:
            continue
        rank = b.derive(f"rk{number}", C.f04_rank(fact, group))
        shown = b.derive(f"dm{number}", diff)
        rows.append([f"⟦F:rk{number}⟧" if rank else NA_CELL, f"⟦R:v{number}⟧", f"⟦F:v{number}⟧", f"⟦S:dm{number}⟧" if shown else NA_CELL])
    n_above = b.derive("n_above", C.f12_count([ordered[i - 1] for i in above], "곳")) if above else None
    n_below = b.derive("n_below", C.f12_count([ordered[i - 1] for i in below], "곳")) if below else None
    clipped = len(ordered) > COMPARE_ROWS
    n_rows = b.derive("n_rows", C.f12_count(ordered[:COMPARE_ROWS], "곳")) if clipped else None

    hi_part = "가장 높은 곳은 ⟦R:hi⟧(⟦F:hi⟧)" if n_hi is None else "가장 높은 값은 ⟦F:hi⟧(같은 값 ⟦V:n_hi⟧⟦U:n_hi⟧)"
    lo_part = "가장 낮은 곳은 ⟦R:lo⟧(⟦F:lo⟧)" if n_lo is None else "가장 낮은 값은 ⟦F:lo⟧(같은 값 ⟦V:n_lo⟧⟦U:n_lo⟧)"
    titles = list(TITLE_POLICY_R02)        # 제목에는 값(곳 수·최고·최저)을 넣지 않는다(D-200)
    leads = [f"⟦D:hi⟧ 기준 ⟦V:n⟧⟦U:n⟧의 ⟦L:hi⟧ 값을 견주면 {hi_part}, {lo_part}입니다.",
             f"⟦D:hi⟧ 기준 ⟦V:n⟧⟦U:n⟧의 ⟦L:hi⟧ 값을 견주면 {hi_part}, {lo_part}입니다(평균 ⟦F:mean⟧)."]
    glance = ["- 가장 높은 곳: ⟦R:hi⟧ ⟦F:hi⟧" if n_hi is None else "- 가장 높은 값: ⟦F:hi⟧(같은 값 ⟦V:n_hi⟧⟦U:n_hi⟧)",
              "- 가장 낮은 곳: ⟦R:lo⟧ ⟦F:lo⟧" if n_lo is None else "- 가장 낮은 값: ⟦F:lo⟧(같은 값 ⟦V:n_lo⟧⟦U:n_lo⟧)",
              "- 평균: ⟦F:mean⟧(⟦V:n⟧⟦U:n⟧ 단순 평균), 중앙값: ⟦F:median⟧"]
    if gap is not None:
        glance.append("- 최고와 최저의 격차: ⟦A:gap⟧")
    if n_above is not None or n_below is not None:
        parts = []
        if n_above is not None:
            parts.append("평균보다 높은 곳 ⟦V:n_above⟧⟦U:n_above⟧")
        if n_below is not None:
            parts.append("낮은 곳 ⟦V:n_below⟧⟦U:n_below⟧")
        glance.append("- " + ", ".join(parts))
    numbers = ["아래 표는 ⟦D:hi⟧ 기준 ⟦L:hi⟧ 값을 높은 순서로 놓은 것입니다. 값은 제공처 자료 그대로이고, 순위와 '평균과의 차이' 열은 이 글이 직접 계산했습니다.",
               md_table(["순위", "지역", "값", "평균과의 차이"], rows, ["r", "l", "r", "r"]),
               "값이 같은 지역은 같은 순위로 적고 다음 순위를 건너뜁니다. 값이 없는 지역은 비교에서 뺐습니다. '평균과의 차이'가 플러스이면 평균보다 높고 마이너스이면 낮다는 뜻입니다."]
    if clipped:
        numbers.append("표에는 값이 높은 ⟦V:n_rows⟧⟦U:n_rows⟧만 적었고(전체 ⟦V:n⟧⟦U:n⟧), 아래 목록도 표에 적은 곳만 적었습니다.")
    sentences = []
    if n_above is not None and n_below is not None:
        sentences.append("평균 ⟦F:mean⟧ 기준으로 위에 있는 곳은 ⟦V:n_above⟧⟦U:n_above⟧, 아래에 있는 곳은 ⟦V:n_below⟧⟦U:n_below⟧입니다.")
    if hi_dm is not None and lo_dm is not None:
        hi_name = "가장 높은 곳(⟦R:hi⟧)" if n_hi is None else "가장 높은 값"
        lo_name = "가장 낮은 곳(⟦R:lo⟧)" if n_lo is None else "가장 낮은 값"
        sentences.append(f"평균과 {hi_name}의 차이는 ⟦A:hi_dm⟧, {lo_name}의 차이는 ⟦A:lo_dm⟧입니다.")
    if mean_med is not None:
        sentences.append("지역 값의 중앙값은 ⟦F:median⟧입니다. 평균과 중앙값의 차이는 ⟦A:mean_med⟧입니다.")
    reading = ["**이 글의 해석**: " + " ".join(sentences) if sentences else "**이 글의 해석**: 비교할 수 있는 값이 모자라 숫자만 옮겼습니다."]
    members = []
    for title, numbers_in_group in (("평균보다 높은 곳", above), ("평균보다 낮은 곳", below), ("평균과 같은 곳", level)):
        listed = [number for number in numbers_in_group if number <= COMPARE_ROWS]
        if listed:
            members.append(f"- {title}: " + ", ".join(f"⟦R:v{number}⟧" for number in listed))
    if members:
        reading.append(md_bullets(members))
    reading.append("순위는 같은 기준일의 값을 크기순으로 놓은 것일 뿐이며, 어느 지역이 더 낫다는 뜻은 아닙니다.")
    caveats = ["- 지역 규모 차이: 지역마다 크기와 구성이 달라 순위만으로 좋고 나쁨을 가를 수 없습니다. 이 글은 그 차이를 보정하지 않았습니다.",
               "- 같은 기준일만 비교: 이 글은 같은 기준일·같은 단위의 값만 한 표에 놓고, 기준일이나 단위가 다른 값은 비교에서 뺍니다.",
               "- 평균과 중앙값: 평균은 값이 유난히 큰 지역이 있으면 크게 움직이지만 중앙값은 덜 움직입니다. 둘의 차이가 크면 값이 한쪽으로 치우쳐 있다는 신호일 수 있습니다."]
    return Draft(hi, b.slots, titles, leads,
                 [(H_GLANCE, [md_bullets(glance)]), (H_NUMBERS, numbers), (H_READING, reading)],
                 caveats, [t for t in (hi.label_ko, "지역 비교", "공개 통계") if t], hi.topic, hi.as_of, b.registry, b.skipped,
                 (recipe.recipe_id, hi.key, "-", hi.as_of), context)


# ----------------------------------------------------------------------------
# Recipe 3 — 임계값·기록(자료 기간 안의 최고·최저 대비 현재 위치)
# ----------------------------------------------------------------------------
@F.exact
def plan_record_position(ctx):
    recipe = ctx.recipe
    picked = pick_series(ctx, min_points=recipe.min_points)
    if isinstance(picked, Insufficient):
        return picked
    _gkey, items = picked
    valid = [f for f in items if f.value is not None]
    cur = valid[-1]
    stale = freshness_problem(ctx, cur)
    if stale is not None:
        return stale
    context = F.display_context(valid)
    regular = is_regular(valid)
    count_unit = F.GRANULARITY_UNIT[F.parse_as_of(cur.as_of).granularity] if regular else OBSERVATION_UNIT
    obs = "" if regular else "관측 "
    ratio = F.ratio_ok(cur.unit)
    b = Builder()
    b.put("main", cur)
    b.put("first", valid[0])
    hi = b.derive("hi", C.f09_max(valid))
    lo = b.derive("lo", C.f10_min(valid))
    pos = b.derive("pos", C.f11_range_position(cur, valid))
    n_all = b.derive("n_all", C.f12_count(valid, count_unit))
    if hi is None or lo is None or pos is None or n_all is None:
        return Insufficient("NOT_COMPARABLE", "자료 기간의 범위를 계산할 수 없어 기록 글을 만들지 않는다(최고와 최저가 같거나 견줄 수 없다)")
    is_high, is_low = cur.value == hi.value, cur.value == lo.value          # 최신 값이 최고(최저)와 같은가 — 같은 값이 더 있으면 '공동'이다
    hi_ties = [f for f in valid if f.value == hi.value]
    lo_ties = [f for f in valid if f.value == lo.value]
    n_hi = b.derive("n_hi", C.f12_count(hi_ties, TIE_UNIT)) if len(hi_ties) > 1 else None        # 최신 값이 최고·최저가 아니어도 같은 값이 여러 번이면 한 기간으로 단정하지 않는다(D-151)
    n_lo = b.derive("n_lo", C.f12_count(lo_ties, TIE_UNIT)) if len(lo_ties) > 1 else None
    to_hi = None if is_high else b.derive("to_hi", C.f01_change(cur, hi, require="any"))
    pct_hi = None if is_high or not ratio else b.derive("pct_hi", C.f02_pct_change(cur, hi, require="any"))
    to_lo = None if is_low else b.derive("to_lo", C.f01_change(cur, lo, require="any"))

    recent = [f for f in valid if ordinal_of(f) > ordinal_of(cur) - CONTEXT_ROWS][-CONTEXT_ROWS:]
    rows = []
    for number, fact in enumerate(reversed(recent), start=1):
        slot = f"r{number}"
        b.put(slot, fact)
        up = b.derive(f"u{number}", C.f01_change(fact, hi, require="any"))
        down = b.derive(f"d{number}", C.f01_change(fact, lo, require="any"))
        rows.append([f"⟦D:{slot}⟧", f"⟦F:{slot}⟧", f"⟦S:u{number}⟧" if up else NA_CELL, f"⟦S:d{number}⟧" if down else NA_CELL])

    if is_high:
        where = "안에서 가장 높은" if n_hi is None else "안에서 가장 높은 값과 같은"
    elif is_low:
        where = "안에서 가장 낮은" if n_lo is None else "안에서 가장 낮은 값과 같은"
    else:
        where = "안에서 최저와 최고 사이 ⟦F:pos⟧ 지점에 놓인"
    titles = list(TITLE_POLICY_R03)        # 제목에는 값(위치·최고·최저)을 넣지 않는다(D-200)
    leads = [f"⟦D:main⟧ 기준 ⟦R:main⟧의 ⟦L:main⟧ 값은 이 글이 읽은 자료(⟦D:first⟧부터 ⟦D:main⟧까지) {where} ⟦F:main⟧입니다."]      # 가장 짧은 라벨·날짜(연)로도 60자 하한을 넘는다(시험이 확인)

    glance = ["- 최신 값: ⟦F:main⟧(⟦D:main⟧ 기준)",
              "- 자료 기간의 최고: ⟦F:hi⟧(⟦D:hi⟧)" if n_hi is None else "- 자료 기간의 최고: ⟦F:hi⟧(같은 값 ⟦V:n_hi⟧⟦U:n_hi⟧, 가장 나중 ⟦D:hi⟧)",
              "- 자료 기간의 최저: ⟦F:lo⟧(⟦D:lo⟧)" if n_lo is None else "- 자료 기간의 최저: ⟦F:lo⟧(같은 값 ⟦V:n_lo⟧⟦U:n_lo⟧, 가장 나중 ⟦D:lo⟧)",
              "- 범위 안의 위치: ⟦F:pos⟧(낮을수록 최저에, 높을수록 최고에 가깝습니다)"]
    if to_hi is not None:
        tail = ", 최고 대비 변화율 ⟦S:pct_hi⟧" if pct_hi is not None else ""
        glance.append(f"- 최고와의 차이: ⟦S:to_hi⟧{tail}")
    if to_lo is not None:
        glance.append("- 최저와의 차이: ⟦S:to_lo⟧")
    numbers = ["위쪽 표는 이 글이 읽은 자료 기간의 최고·최저와 최신 값을, 아래쪽 표는 최근 값을 최고·최저와 견준 결과입니다. 최고·최저는 제공처 자료 그대로이고 차이는 이 글이 직접 계산했습니다.",
               md_table(["구분", "기준 기간", "값"], [["최고", "⟦D:hi⟧" if n_hi is None else "⟦D:hi⟧(가장 나중, 같은 값 ⟦V:n_hi⟧⟦U:n_hi⟧)", "⟦F:hi⟧"],
                                                    ["최저", "⟦D:lo⟧" if n_lo is None else "⟦D:lo⟧(가장 나중, 같은 값 ⟦V:n_lo⟧⟦U:n_lo⟧)", "⟦F:lo⟧"],
                                                    ["최신", "⟦D:main⟧", "⟦F:main⟧"]], ["l", "l", "r"]),
               md_table(["기준 기간", "값", "최고와의 차이", "최저와의 차이"], rows, ["l", "r", "r", "r"]),
               "차이는 그 기간의 값에서 최고나 최저의 값을 뺀 것입니다. 그래서 최고와의 차이는 플러스가 아니고, 최저와의 차이는 마이너스가 아닙니다."]
    sentences = [f"이 글이 읽은 자료는 ⟦D:first⟧부터 ⟦D:main⟧까지 {obs}⟦V:n_all⟧⟦U:n_all⟧입니다."]
    if is_high:
        sentences.append("최신 값이 이 기간에서 가장 높은 값이라 범위의 맨 위에 있습니다." if n_hi is None
                         else "최신 값이 이 기간에서 가장 높은 값과 같아 범위의 맨 위에 있고, 그 값은 자료에 ⟦V:n_hi⟧⟦U:n_hi⟧ 나옵니다.")
    elif is_low:
        sentences.append("최신 값이 이 기간에서 가장 낮은 값이라 범위의 맨 아래에 있습니다." if n_lo is None
                         else "최신 값이 이 기간에서 가장 낮은 값과 같아 범위의 맨 아래에 있고, 그 값은 자료에 ⟦V:n_lo⟧⟦U:n_lo⟧ 나옵니다.")
    elif to_hi is not None and to_lo is not None:
        sentences.append("최신 값은 최고보다 ⟦A:to_hi⟧ 낮고 최저보다 ⟦A:to_lo⟧ 높아, 범위의 안쪽에 있습니다.")
    reading = ["**이 글의 해석**: " + " ".join(sentences),
               "범위의 어느 쪽에 있든 앞으로도 같은 방향으로 움직인다는 뜻은 아닙니다. 이 글은 앞날을 내다보지 않고 읽은 숫자만 옮겼습니다."]
    caveats = ["- 기록의 범위: '가장 높다·가장 낮다'는 이 글이 읽은 자료 기간 안에서만 말할 수 있습니다. 더 오래된 자료가 있다면 결과가 달라질 수 있습니다.",
               "- 위치 값: 위치는 최저와 최고 사이를 같은 간격으로 보았을 때의 비율이라, 자료 기간이 달라지면 같은 값도 위치가 달라집니다."]
    return Draft(cur, b.slots, titles, leads,
                 [(H_GLANCE, [md_bullets(glance)]), (H_NUMBERS, numbers), (H_READING, reading)],
                 caveats, _tags(cur, ("자료 기간 안의 위치", "공개 통계")), cur.topic, cur.as_of, b.registry, b.skipped, _dedupe(recipe.recipe_id, cur), context)


ALLOWED_DOMAINS = tuple(sorted(T.DOMAINS))

R01_TIME_SERIES = Recipe(
    "R01_time_series", 1, "시계열 변화",
    "한 지표·한 지역의 시계열에서 최신값·바로 앞 기간 대비·전년 같은 기간 대비·최근 평균·최근 기간 추이 표를 만든다.",
    ALLOWED_DOMAINS, ("F01_change", "F02_pct_change", "F03_yoy", "F06_diff_from_mean", "F07_rolling_mean", "F09_max", "F10_min", "F12_count"),
    6, 450, plan_time_series)
R02_REGION_COMPARE = Recipe(
    "R02_region_compare", 1, "지역 비교",
    "같은 기준일의 지역 값을 순위 표로 놓고 평균과의 차이·최고와 최저·격차를 만든다.",
    ALLOWED_DOMAINS, ("F04_rank", "F06_diff_from_mean", "F08_mean", "F12_count", "F13_gap", "F14_median"),
    4, 450, plan_region_compare)
R03_RECORD_POSITION = Recipe(
    "R03_record_position", 1, "임계값·기록",
    "한 지표·한 지역의 자료 기간 안 최고·최저 대비 현재 위치를 만든다('역대'가 아니라 읽은 자료 기간 안에서만 말한다).",
    ALLOWED_DOMAINS, ("F01_change", "F02_pct_change", "F09_max", "F10_min", "F11_range_position", "F12_count"),
    8, 450, plan_record_position)

RECIPES = {r.recipe_id: r for r in (R01_TIME_SERIES, R02_REGION_COMPARE, R03_RECORD_POSITION)}
