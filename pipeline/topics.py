"""주제 선정: 시드 주제 + LLM 확장, 쿨다운과 교차 중복 방지.

고정 주제 목록을 무한 반복하면 같은 글이 나온다(저품질·중복). 그래서
(1) 쿨다운 안에 다룬 주제는 건너뛰고 (2) 금지 주제를 거르고 (3) 다른 블로그와 겹치면 건너뛰며
(4) 시드를 다 쓰면 LLM으로 새 주제를 제안받는다(같은 필터를 통과해야 채택).
(5) 지금 시기(계절·명절)에 맞지 않는 주제는 건너뛴다 — 가을에 '봄맞이 대청소'가 나오지 않게(이슈 #92). 시드는 프로필의 seed_months 가,
    그 밖의 주제(LLM 이 제안한 것·달 표시가 없는 시드)는 주제에 쓰인 계절 낱말이 정한다(아래 season_fits).
"""
import json
import re
from datetime import date

from pipeline.gates import most_similar, similarity, topic_allowed

TOPIC_MIN_CHARS, TOPIC_MAX_CHARS = 8, 60

# 계절 = 달 묶음(한국 기상 기준: 봄 3~5월·여름 6~8월·가을 9~11월·겨울 12~2월). 영어 블로그도 같은 달로 센다(북반구).
SEASONS = ("spring", "summer", "autumn", "winter")      # 한 해의 흐름 순서 — 다음 계절은 다음 칸(겨울 다음은 봄)
SEASON_MONTHS = {"spring": (3, 4, 5), "summer": (6, 7, 8), "autumn": (9, 10, 11), "winter": (12, 1, 2)}
SEASON_LABELS = {"ko": {"spring": "봄", "summer": "여름", "autumn": "가을", "winter": "겨울"},
                 "en": {"spring": "spring", "summer": "summer", "autumn": "autumn", "winter": "winter"}}
# 주제에 이 낱말이 있으면 그 계절 이야기다. 한국어는 낱말 첫머리에서만 맞춘다('돌봄'의 '봄'은 계절이 아니다). 계절 이름 앞의 초·늦·올·지난·이른·한(한여름·한겨울)은 같은 계절로 본다.
# 영어 'fall' 은 'fall asleep' 처럼 계절이 아닌 쓰임이 많아 뺐다. 모든 계절 낱말을 담을 수는 없다 — 여기 없는 계절 이야기는 주제 확장 지시문의 시기 안내가 막는 데까지만 막힌다(docs/ARCHITECTURE.md 한계).
_SEASON_WORDS = {
    "ko": {
        "spring": re.compile(r"(?<![가-힣])(?:(?:초|늦|올|지난|이른)?봄|꽃구경|벚꽃|꽃샘|개나리|황사|입춘|식목일|어린이날|어버이날|새 ?학기)"),
        "summer": re.compile(r"(?<![가-힣])(?:(?:초|늦|올|지난|이른|한)?여름|장마|폭염|무더위|찜통더위|더위|열대야|피서|휴가철|물놀이|모기(?!지|업)|삼복|복날|초복|말복|단오|해수욕)"),
        "autumn": re.compile(r"(?<![가-힣])(?:(?:초|늦|올|지난|이른)?가을|단풍|김장|추석|한가위|낙엽|추수|수능)"),
        "winter": re.compile(r"(?<![가-힣])(?:(?:초|늦|올|지난|이른|한)?겨울|한파|폭설|보일러|난방|설날|설 ?연휴|설 ?명절|구정(?!물)|정월|대보름|크리스마스|성탄|연말|동지(?!애|역))"),
    },
    "en": {
        "spring": re.compile(r"\b(?:spring|springtime)\b", re.IGNORECASE),
        "summer": re.compile(r"\b(?:summer|summertime|heat ?wave)\b", re.IGNORECASE),
        "autumn": re.compile(r"\b(?:autumn|halloween|thanksgiving)\b", re.IGNORECASE),
        "winter": re.compile(r"\b(?:winter|wintertime|christmas)\b", re.IGNORECASE),
    },
}


def clean_topic(raw):
    """주제 문자열 정리(개행 제거·길이 제한). 운영자 입력이나 LLM 출력을 프롬프트에 넣기 전에 쓴다."""
    topic = re.sub(r"\s+", " ", str(raw or "")).strip().strip("\"'“”")
    return topic[:120]


def recently_used(topic, history, today, cooldown_days, threshold=0.8):
    for entry in history:
        if not isinstance(entry, dict):
            continue
        past, when = entry.get("topic"), entry.get("date")
        if not past or not when:
            continue
        try:
            age = (today - date.fromisoformat(when)).days
        except ValueError:
            continue
        if age < cooldown_days and similarity(topic, past) >= threshold:
            return True
    return False


def season_of(day):
    """날짜(date) → 계절 이름('spring'·'summer'·'autumn'·'winter')."""
    return next(name for name in SEASONS if day.month in SEASON_MONTHS[name])


def mentioned_seasons(topic, language):
    """주제 글에 계절 낱말이 쓰인 계절들의 집합(없으면 빈 집합 = 사철 주제). language 는 프로필의 language(ko·en)."""
    table = _SEASON_WORDS.get(language)
    return {season for season, pattern in table.items() if pattern.search(str(topic or ""))} if table else set()


def season_fits(topic, profile, today):
    """주제가 오늘(date) 시기에 맞는가. 프로필 seed_months 에 이 주제가 있으면 그 달 목록이 정한다(오늘 달이 들어 있어야 한다).
    없으면 주제에 쓰인 계절 낱말로 본다: 계절 낱말이 하나도 없으면(사철 주제) 맞고, 있으면 지금 계절이나 다음 계절(미리 준비)이 하나라도 들어 있어야 맞다.
    예: 가을(11월)에 '봄맞이 대청소'는 아니고, '겨울이 오기 전에 창가 점검'은 맞다. 수동으로 정한 주제(--topic)는 이 검사를 거치지 않는다."""
    months = profile.get("seed_months")
    listed = months.get(topic) if isinstance(months, dict) else None
    if listed is not None:
        return today.month in listed
    seasons = mentioned_seasons(topic, profile.get("language"))
    if not seasons:
        return True
    current = season_of(today)
    return bool(seasons & {current, SEASONS[(SEASONS.index(current) + 1) % len(SEASONS)]})


def season_hint(profile, today):
    """주제 확장 지시문 맨 앞에 붙이는 시기 안내(프로필 언어로)."""
    english = profile.get("language") == "en"
    label = SEASON_LABELS["en" if english else "ko"][season_of(today)]
    if english:
        return (f"Today is {today.isoformat()} ({label} in the Northern Hemisphere). Only suggest ideas that fit the current season or the one coming next; "
                "skip seasonal events, weather or preparations from other seasons (for example spring cleaning in autumn).")
    return (f"오늘은 {today.isoformat()}이고 한국은 {label}이다. 지금 계절이나 곧 올 계절에 맞는 주제만 제안한다. 지난 계절이나 먼 계절의 행사·날씨·준비는 제외한다"
            "(예: 가을에 봄맞이 대청소).")


def season_note(profile, today):
    """글 쓰기 프롬프트 뒤에 붙이는 시기 안내(프로필 언어로). 글이 지금 시기와 맞지 않는 계절 이야기를 하지 않게 한다."""
    english = profile.get("language") == "en"
    label = SEASON_LABELS["en" if english else "ko"][season_of(today)]
    if english:
        return (f"[Timing]\n- Today is {today.isoformat()} ({label} in the Northern Hemisphere). Mention weather, clothing, events and preparations only if they fit "
                "this time of year, and do not write about a season that does not match it (for example spring cleaning in autumn). "
                "If the subject is an upcoming season or holiday, present it as something coming up.")
    return (f"[작성 시점]\n- 오늘은 {today.isoformat()}이고 한국은 {label}이다. 날씨·옷차림·행사·준비물은 지금 시기에 맞는 것만 지금 이야기로 쓴다. "
            "지금과 맞지 않는 계절 이야기(예: 가을에 봄맞이 대청소, 겨울에 한여름 더위)는 쓰지 않는다. "
            "주제가 앞으로 올 계절이나 명절이면 '곧 다가오는 일'로 쓴다.")


def _acceptable(topic, profile, history, today, avoid_titles):
    if not (TOPIC_MIN_CHARS <= len(topic) <= TOPIC_MAX_CHARS):
        return False
    if not topic_allowed(topic, profile):
        return False
    if recently_used(topic, history, today, profile.get("topic_cooldown_days", 60)):
        return False
    score, _ = most_similar(topic, avoid_titles)
    return score < profile.get("similarity", {}).get("other_blogs", 0.6)


def parse_topic_list(raw):
    """LLM 응답에서 JSON 문자열 배열을 꺼낸다. 형식이 틀리면 빈 목록."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.I)
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, str):
            item = clean_topic(item)
            if item and item not in out:
                out.append(item)
    return out


def _expand_prompt_base(profile, recent_topics, n):
    recent = "\n".join(f"- {t}" for t in recent_topics[-40:])
    template = profile.get("topic_expand_prompt")
    if template:
        # 영어 등 한국어가 아닌 블로그는 프로필이 주제 확장 지시문(자리표시자 {n}·{min}·{max}·{avoid})을 가진다. 새 언어를 코드 수정 없이 붙이기 위한 것
        return (template.replace("{n}", str(n)).replace("{min}", str(TOPIC_MIN_CHARS))
                .replace("{max}", str(TOPIC_MAX_CHARS)).replace("{avoid}", recent or "- (none)"))
    avoid = recent or "- (없음)"
    return (
        "너는 건강·음식·생활 중심 실용 블로그의 편집자다. 독자가 오늘 바로 실천할 수 있는 "
        f"가벼운 생활 습관 주제 {n}개를 제안한다.\n"
        "조건: 질병 치료, 약, 보충제, 진단, 임신·영유아, 체중 감량, 의료 조언 관련 주제는 제외한다. "
        f"각 주제는 제목형 한 문장({TOPIC_MIN_CHARS}~{TOPIC_MAX_CHARS}자)으로 쓴다.\n"
        f"이미 다룬 주제와 겹치지 않게 한다:\n{avoid}\n"
        '출력: JSON 문자열 배열만 출력한다(설명·코드 블록 금지). 예: ["주제1", "주제2"]'
    )


def expand_prompt(profile, recent_topics, n, today=None):
    """주제 확장 지시문. today(date)를 주면 맨 앞에 지금 시기 안내를 붙인다(주지 않으면 예전과 글자 하나 다르지 않다)."""
    prompt = _expand_prompt_base(profile, recent_topics, n)
    return prompt if today is None else season_hint(profile, today) + "\n\n" + prompt


def pick_topic(profile, history, today, avoid_titles, rng, llm=None, expand_n=8):
    """(topic, source). 고를 주제가 없으면 (None, 'exhausted'). 지금 시기에 맞지 않는 주제는 시드든 LLM 제안이든 고르지 않는다(season_fits)."""
    seeds = [seed for seed in profile.get("seed_topics", []) if season_fits(seed, profile, today)]
    rng.shuffle(seeds)
    for seed in seeds:
        if _acceptable(seed, profile, history, today, avoid_titles):
            return seed, "seed"
    if llm is not None:
        recent = [e.get("topic") for e in history if isinstance(e, dict) and e.get("topic")]
        try:
            raw, _model = llm(expand_prompt(profile, recent, expand_n, today))
        except Exception:  # noqa: BLE001 - 확장 실패는 '주제 없음'으로 처리하고 호출자가 기록한다
            return None, "expand_failed"
        for candidate in parse_topic_list(raw):
            if season_fits(candidate, profile, today) and _acceptable(candidate, profile, history, today, avoid_titles):
                return candidate, "llm"
    return None, "exhausted"
