"""주제 선정: 시드 주제 + LLM 확장, 쿨다운과 교차 중복 방지.

고정 주제 목록을 무한 반복하면 같은 글이 나온다(저품질·중복). 그래서
(1) 쿨다운 안에 다룬 주제는 건너뛰고 (2) 금지 주제를 거르고 (3) 다른 블로그와 겹치면 건너뛰며
(4) 시드를 다 쓰면 LLM으로 새 주제를 제안받는다(같은 필터를 통과해야 채택).
"""
import json
import re
from datetime import date

from pipeline.gates import most_similar, similarity, topic_allowed

TOPIC_MIN_CHARS, TOPIC_MAX_CHARS = 8, 60


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


def expand_prompt(profile, recent_topics, n):
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


def pick_topic(profile, history, today, avoid_titles, rng, llm=None, expand_n=8):
    """(topic, source). 고를 주제가 없으면 (None, 'exhausted')."""
    seeds = list(profile.get("seed_topics", []))
    rng.shuffle(seeds)
    for seed in seeds:
        if _acceptable(seed, profile, history, today, avoid_titles):
            return seed, "seed"
    if llm is not None:
        recent = [e.get("topic") for e in history if isinstance(e, dict) and e.get("topic")]
        try:
            raw, _model = llm(expand_prompt(profile, recent, expand_n))
        except Exception:  # noqa: BLE001 - 확장 실패는 '주제 없음'으로 처리하고 호출자가 기록한다
            return None, "expand_failed"
        for candidate in parse_topic_list(raw):
            if _acceptable(candidate, profile, history, today, avoid_titles):
                return candidate, "llm"
    return None, "exhausted"
