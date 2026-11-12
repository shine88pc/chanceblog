"""제한 재개 잠금(resume_lock) — '사람 승인 없는 공개 경로 0개'를 코드로 지키는 스위치(기본 꺼짐).

배경(운영자 결정 2026-11-09, 확인 요청 007 답 2026-11-09 20:33): 발행 재개(PIPELINE_PAUSE 해제) 전에 Chance 는 승인 흐름(publish_flow: pr), Blogger 는 초안 전용, 자동·직접 게시는 꺼짐,
하루 최대 1편·재개 뒤 일주일에 1–2편이어야 하고, 이것을 코드와 시험으로 보장하지 못하면 정지를 유지한다. 이 모듈이 그 보장의 '잠금'이다. 레지스트리(pipeline/blogs.json) 최상위에
`resume_lock: true` 를 적으면 켜지고(켜는 것은 별도 T3 변경이다), 키가 없거나 false 면 이 모듈은 아무것도 바꾸지 않는다(꺼짐 = 이전과 같은 동작).

켜졌을 때 코드가 강제하는 것(전수조사 표와 각 경로의 잠금 방법은 docs/PUBLISH_PATHS.md)
  1. 레지스트리 규칙 L1–L8(아래 RULES)을 어기는 설정은 검증이 거절한다 — pipeline.registry.validate_registry 가 `lock_errors` 를 부르므로
     `python -m pipeline.registry`·pipeline.plan·pipeline.run·검증기 REG-1 이 같은 규칙을 읽는다.
  2. 실행 시작 가드 `guard_start`(generator.py 의 main() 앞부분 한 줄)가 규칙 위반이면 글을 만들지 않고 `::error::` 로 끝낸다. 같은 가드가
     ① 기존 글 이미지 교체(main 직접 커밋)를 막고 ② 하루 상한(1편)을 정기 실행·수동 실행 모두에 코드로 강제하며(지금은 정기 실행이 슬롯 2개로만 하루 편수를
     지키고 수동 실행은 상한을 따지지 않는다 — docs/DEFECT_REGISTER.md D-54) ③ 열린 초안 상한을 세고 ④ 주간 상한(굴러가는 7일에 최대 `chance.limits.max_posts_per_week` 편, 1–2)을
     센다 — 이력의 글과 이력에 아직 없는 열린 초안 브랜치를 중복 없이 센다(세는 방법·창 경계·이상한 날짜의 처리는 docs/PUBLISH_PATHS.md §4-4). 읽기 전용인 그림자 실행(SHADOW_RUN)과 연습 실행은 상한을 세지 않는다.
  3. Chance 발행 흐름을 읽는 `drafts.chance_flow()`(워크플로의 '발행 흐름 확인' 단계·`draft_flow deliver`·생성기가 쓴다)도 규칙 위반이면 멈춘다 — 그 단계가 실패하면
     뒤의 모든 단계(main 직접 커밋 포함)가 돌지 않는다.
  4. Blogger 러너(pipeline/run.py)는 규칙 위반이면 글을 만들지 않고, 수동 입력 publish(즉시 게시)도 거절한다 — Blogger 는 초안함(draft)·저장소 파일(off)로만 간다.
  5. `python -m pipeline.publish_lock check-direct`(워크플로 단계): main 에 직접 커밋하는 워크플로(chance-fix-images.yml)는 잠금이 켜져 있으면 첫 단계에서 멈춘다.

설계 원칙
  - 순수 규칙(lock_state·lock_errors·posts_today 등)과 읽기 전용 I/O(guard_start 의 레지스트리·이력·원격 브랜치 읽기)를 한 파일 안에서 구역으로 나눴다(ENGINEERING_GUIDE R2).
  - fail closed: `resume_lock` 의 **값**이 true/false 가 아니면(모르는 값) 켜진 것으로 읽고 L0 오류를 낸다 — L0 은 값 오타만 막는다. 레지스트리를 아예 읽지 못하는 경우는 기존 동작을
    바꾸지 않는다(글을 만드는 길은 `drafts.chance_flow()` 가 이미 멈춘다) — 다만 레지스트리를 읽지 않던 직접 커밋 길(기존 글 이미지 교체)은 읽지 못하면 멈춘다.
  - **키 이름 오타·위치 오류는 K1·K2 가 막는다**(검증 지적 1): 키가 없으면 잠금이 꺼진 것이라, `resume_lok`·`Resume_Lock`·`resume-lock`·`resume_lock `(뒤 공백)처럼 적거나 `defaults`·블로그 항목 안에
    두면 켠 줄 알았는데 꺼진 채로 통과한다. 그래서 ① 레지스트리 검증기는 **알려진 최상위 키만** 허용하고(KNOWN_TOP_LEVEL_KEYS — 새 키는 이 목록과 시험을 함께 고쳐 의도적으로 더한다)
    resume_lock 오타로 보이는 키(이름이 resume_lock 과 거의 같은 것 — 줄인 이름이 resumelock 을 품거나 편집 거리 2 이내)에는 그렇게 말해 주고 그 밖의 모르는 키는 '알 수 없는 최상위 키'라고
    말한다(K1) ② 최상위 밖 **어디에든**(`defaults`·블로그 항목 직속은 물론 그 안의 limits·schedule 같은 두 단계 이상 깊은 곳까지) resume_lock 이나 그 오타가 있으면 오류다(K2 — 레지스트리
    전체를 반복문으로 한 번씩만 훑고 깊이는 MAX_KEY_SCAN_DEPTH 까지, 넘으면 그것도 오류) ③ 실행 시에도(가드·chance_flow·Blogger 러너·check·check-direct) 이 둘 중 '잠금 키 문제'(오타로 보이는
    키·잘못된 위치)는 멈춘다. 오류 문장이 아주 많아도 앞 MAX_KEY_MESSAGES 개와 '외 N개' 한 줄뿐이다. 잠금 키가 아예 없는 지금의 레지스트리에서는 어느 쪽도 아무 일도 하지 않는다(꺼짐 = 이전과 같다).
  - 표준 라이브러리와 pipeline.console 만 import 한다(워크플로 단계가 pip 설치 전에 `python -m pipeline.publish_lock` 을 부른다). 레지스트리·드래프트 모듈은 함수 안에서 늦게 읽는다(순환 import 방지).
  - 로그·요약에 쓰는 글은 고정 문장과 숫자·날짜뿐이거나 one_line/md_cell 을 거친 레지스트리 값이다. `::error::`·`::warning::` 주석에는 고정 문장만 쓴다(ENGINEERING_GUIDE R9).
"""
import json
import os
import re
import sys
import unicodedata
from collections import deque, namedtuple
from datetime import date, timedelta
from pathlib import Path

from pipeline.console import md_cell, one_line, safe_output

LOCK_KEY = "resume_lock"
CHANCE_KEY = "chance"
REQUIRED_FLOW = "pr"                      # Chance 는 초안 PR 로만 올라가고 사람이 병합해야 공개된다
SAFE_MODES = ("off", "draft", "package")  # Chance 밖의 블로그에 허용되는 mode — 셋 다 공개되지 않는 쪽이다(auto 만 사람 승인 없이 공개된다)
MAX_POSTS_PER_DAY = 1                     # 잠금이 켜졌을 때의 하루 상한(모든 블로그)
MAX_OPEN_DRAFTS = 3                       # 잠금이 켜졌을 때 chance.limits.max_open_drafts 의 천장
MAX_POSTS_PER_WEEK = 2                    # 잠금이 켜졌을 때 chance.limits.max_posts_per_week 의 천장(Chance 의 일주일 상한 — 운영자 조건 '재개 시 주 1–2편')
WEEK_WINDOW_DAYS = 7                      # 주간 상한을 세는 창: 오늘을 포함해 굴러가는 7일(KST 날짜 기준 — 오늘과 그 6일 전까지). 달력 주(월–일)가 아니다
LANGUAGE_CODES = ("ko", "en")             # chance.languages 에 쓸 수 있는 값(정확히 이 둘 — 시험이 못박는다)
# SHADOW_RUN(읽기 전용 그림자 실행) 값 집합 — GATE 의 pipeline/shadow_run·generator 와 같은 집합이어야 한다(docs/PUBLISH_PATHS.md §4-2 한 곳에 적고 시험이 견준다).
# 대소문자·앞뒤 공백은 무시한다. 켜짐 집합이면 그림자 실행, 꺼짐 집합이면 일반 실행, 그 밖의 값은 잠금이 켜져 있을 때 이 가드가 실행을 거절한다(종료 2).
SHADOW_ON_VALUES = ("1", "true", "yes", "on", "enabled")
SHADOW_OFF_VALUES = ("", "0", "false", "no", "off", "disabled")
# 레지스트리 최상위에 둘 수 있는 키 전부(2026-11-09 pipeline/blogs.json 의 최상위 키 + resume_lock). 새 키를 더하는 변경은 이 목록과 시험(KeyTypoTest)을 함께 고친다.
KNOWN_TOP_LEVEL_KEYS = ("_doc", "schema_version", "shared_secrets", "defaults", "blogs", LOCK_KEY)
LOCK_KEY_SQUASHED = "resumelock"          # LOCK_KEY 를 소문자로 바꾸고 `_`·`-`·공백을 뺀 모양(시험이 _squash(LOCK_KEY) 와 같음을 확인한다)
LOCK_KEY_EDITS = 2                        # '오타로 보임' = 줄인 이름이 resumelock 을 품거나 resumelock 과 편집 거리 이 값 이내
MAX_KEY_SCAN_DEPTH = 16                   # K2 가 레지스트리를 훑는 깊이 상한(정상 레지스트리는 4 이하) — 넘으면 오류(fail closed)
MAX_KEY_MESSAGES = 20                     # K1·K2 문장은 앞 이만큼만 내고 나머지는 '외 N개' 한 줄로 줄인다(출력 상한)

STATE_OFF, STATE_ON, STATE_INVALID, STATE_UNREADABLE = "off", "on", "invalid", "unreadable"

# 건너뜀·멈춤 코드(로그의 `[SKIP] code=…` 줄과 실행 요약에 쓴다)
CODE_BLOCKED = "LOCK_BLOCKED"
CODE_DAILY_CAP = "LOCK_DAILY_CAP"
CODE_WEEKLY_CAP = "LOCK_WEEKLY_CAP"
CODE_OPEN_DRAFTS = "OPEN_DRAFTS_CAP"
CODE_DRAFTS_UNKNOWN = "OPEN_DRAFTS_UNKNOWN"

# 규칙 번호와 뜻(docs/PUBLISH_PATHS.md §3 의 표와 tests/test_publish_paths.py 가 같은지 대조한다)
RULES = (
    ("L0", "resume_lock 의 값은 true 또는 false 여야 한다 — 모르는 값은 잠금이 켜진 것으로 읽는다(fail closed). 값 오타만 막는다: 키 이름 오타·위치 오류는 K1·K2"),
    ("L1", "chance.publish_flow 는 pr 이어야 한다(적지 않으면 direct 로 읽히므로 pr 을 직접 적어야 한다)"),
    ("L2", "Chance 밖의 모든 블로그의 mode 는 off·draft·package 중 하나다(auto 금지)"),
    ("L3", "chance.mode 가 auto 이면 publish_flow: pr 가 함께 적혀 있어야 한다(자동 생성은 초안 PR 로만)"),
    ("L4", "chance.limits.max_posts_per_day 는 1 이다"),
    ("L5", "chance.limits.max_open_drafts(열린 초안 상한)가 있어야 하고 1 이상 3 이하 정수다(잠금이 꺼져 있어도 값이 있으면 1 이상 정수여야 한다)"),
    ("L6", "chance.languages 가 있으면 ko 를 포함하고 ko·en 만 겹침 없이 든 목록이다"),
    ("L7", "Chance 밖의 모든 블로그의 limits.max_posts_per_day 도 1 이다"),
    ("L8", "chance.limits.max_posts_per_week(주간 상한 — 굴러가는 7일에 만드는 글 수)가 있어야 하고 1 이상 2 이하 정수다(잠금이 꺼져 있어도 값이 있으면 1 이상 정수여야 한다). Chance 밖의 블로그에는 주간 상한을 강제하지 않는다"),
)

# 레지스트리 키 규칙(잠금이 꺼져 있어도 적용 — 잠금 키가 아예 없는 지금의 레지스트리는 항상 통과한다)
KEY_RULES = (
    ("K1", "레지스트리 최상위에는 알려진 키(KNOWN_TOP_LEVEL_KEYS)만 둔다 — 모르는 키는 오류이고, 이름이 resume_lock 과 거의 같으면(대소문자·하이픈·뒤 공백·글자 한두 개 오타) 오타로 보인다고 알려 준다"),
    ("K2", "resume_lock 은 최상위에만 둔다 — 최상위 밖 어느 깊이든 resume_lock(이나 그 오타)이 있으면 오류다"),
)

Block = namedtuple("Block", "code lines error")   # code: 건너뜀 코드, lines: 로그 줄들, error: `::error::` 주석에 낼 고정 문장
_KEY_ERROR_HEAD = "레지스트리의 제한 재개 잠금 키(resume_lock)가 잘못 적혀 있어 잠금 상태를 알 수 없습니다 — "
KEY_ERROR = _KEY_ERROR_HEAD + "글을 만들지 않고 멈춥니다. 어긴 규칙은 위 줄과 실행 요약에 있습니다."
KEY_ERROR_DIRECT = _KEY_ERROR_HEAD + "main 에 직접 커밋하는 이 워크플로는 멈춥니다. 어긴 규칙은 위 줄에 있습니다."
LOCK_ERROR = "제한 재개 잠금(resume_lock)이 켜져 있는데 설정이 규칙을 어깁니다 — 글을 만들지 않고 멈춥니다. 어긴 규칙은 위 줄과 실행 요약에 있습니다."
WEEKLY_DATE_ERROR = "이력의 날짜를 읽을 수 없어 일주일 상한을 셀 수 없습니다 — 글을 만들지 않고 멈춥니다. 어느 항목인지는 위 줄과 실행 요약에 있습니다."


# ============================================================================
# 순수 규칙 — 입출력 없음
# ============================================================================
def lock_state(reg):
    """레지스트리 사전에서 잠금 상태: off(키 없음·false) · on(true) · invalid(그 밖의 값 — 켜진 것으로 읽는다) · unreadable(사전이 아님)."""
    if not isinstance(reg, dict):
        return STATE_UNREADABLE
    if LOCK_KEY not in reg:
        return STATE_OFF
    value = reg[LOCK_KEY]
    if value is True:
        return STATE_ON
    if value is False:
        return STATE_OFF
    return STATE_INVALID


def lock_active(reg):
    """잠금이 켜진 것으로 다뤄야 하는가(on 또는 모르는 값)."""
    return lock_state(reg) in (STATE_ON, STATE_INVALID)


def _blogs(reg):
    blogs = reg.get("blogs") if isinstance(reg, dict) else None
    return [raw for raw in blogs if isinstance(raw, dict)] if isinstance(blogs, list) else []


def _defaults(reg):
    defaults = reg.get("defaults") if isinstance(reg, dict) else None
    return defaults if isinstance(defaults, dict) else {}


def _chance(reg):
    return next((raw for raw in _blogs(reg) if raw.get("key") == CHANCE_KEY), None)


def _limits(reg, raw):
    """블로그 항목의 limits(레지스트리 defaults.limits 위에 항목의 값을 얹은 것 — pipeline.registry.deep_merge 와 같다. limits 는 평평한 사전이다)."""
    merged = dict(_defaults(reg).get("limits") if isinstance(_defaults(reg).get("limits"), dict) else {})
    own = raw.get("limits")
    if isinstance(own, dict):
        merged.update(own)
    return merged


def _mode(reg, raw):
    return raw["mode"] if "mode" in raw else _defaults(reg).get("mode")


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _shown(value):
    return one_line(repr(value), 40)


def _msg(rule, text):
    return "제한 재개 잠금 " + rule + ": " + text


def flow_of(reg):
    """레지스트리의 chance.publish_flow(적지 않으면 direct — pipeline.registry.DEFAULT_PUBLISH_FLOW 와 같다). chance 항목이 없으면 None."""
    chance = _chance(reg)
    return None if chance is None else chance.get("publish_flow", "direct")


def open_drafts_limit(reg):
    """레지스트리 chance.limits.max_open_drafts(1 이상 정수). 없거나 올바르지 않으면 None — 이 규칙은 꺼져 있다."""
    chance = _chance(reg)
    if chance is None:
        return None
    value = _limits(reg, chance).get("max_open_drafts")
    return value if _is_int(value) and value >= 1 else None


def weekly_posts_limit(reg):
    """레지스트리 chance.limits.max_posts_per_week(1 이상 정수 — 불리언 제외, defaults.limits 에서 물려받은 값 포함). 없거나 올바르지 않으면 None — 이 규칙은 꺼져 있다.
    잠금이 켜져 있으면 L8 이 값이 1 이상 2 이하임을 보증하므로(어기면 가드가 먼저 멈춘다) 가드가 읽는 값은 1 또는 2 다. Chance 밖의 블로그는 읽지 않는다."""
    chance = _chance(reg)
    if chance is None:
        return None
    value = _limits(reg, chance).get("max_posts_per_week")
    return value if _is_int(value) and value >= 1 else None


def _open_drafts_error(reg, chance, locked):
    limits = _limits(reg, chance)
    if "max_open_drafts" not in limits:
        return _msg("L5", "chance.limits.max_open_drafts(열린 초안 PR 상한)가 없습니다 — 1 이상 %d 이하 정수를 적으세요(기본 권장 %d)."
                    % (MAX_OPEN_DRAFTS, MAX_OPEN_DRAFTS)) if locked else None
    value = limits["max_open_drafts"]
    ceiling = MAX_OPEN_DRAFTS if locked else None
    if _is_int(value) and value >= 1 and (ceiling is None or value <= ceiling):
        return None
    where = "1 이상 %d 이하 정수" % MAX_OPEN_DRAFTS if locked else "1 이상 정수"
    return _msg("L5", "chance.limits.max_open_drafts 는 %s 여야 합니다(지금 %s)." % (where, _shown(value)))


def _weekly_cap_error(reg, chance, locked):
    """L8(주간 상한): 잠금이 켜져 있으면 값이 있어야 하고(없으면 오류 — fail closed) 1 이상 2 이하 정수다. 꺼져 있으면 값이 있을 때만 모양(1 이상 정수)을 본다 —
    L5 의 `_open_drafts_error` 와 같은 방식이다(문장은 따로 둔다: L5 의 출력은 그대로여야 한다). 불리언은 정수가 아니다."""
    limits = _limits(reg, chance)
    if "max_posts_per_week" not in limits:
        return _msg("L8", "chance.limits.max_posts_per_week(일주일 상한 — 굴러가는 7일에 만드는 글 수)가 없습니다 — 1 이상 %d 이하 정수를 적으세요(권장 %d)."
                    % (MAX_POSTS_PER_WEEK, MAX_POSTS_PER_WEEK)) if locked else None
    value = limits["max_posts_per_week"]
    ceiling = MAX_POSTS_PER_WEEK if locked else None
    if _is_int(value) and value >= 1 and (ceiling is None or value <= ceiling):
        return None
    where = "1 이상 %d 이하 정수" % MAX_POSTS_PER_WEEK if locked else "1 이상 정수"
    return _msg("L8", "chance.limits.max_posts_per_week 는 %s 여야 합니다(지금 %s)." % (where, _shown(value)))


def _rule_errors(reg):
    errors = []
    chance = _chance(reg)
    if chance is not None:
        flow = chance.get("publish_flow", "direct")
        if flow != REQUIRED_FLOW:
            errors.append(_msg("L1", "chance.publish_flow 가 pr 이 아닙니다(지금 %s%s). 잠금이 켜져 있으면 Chance 글은 초안 PR 로만 올라가고 사람이 병합해야 공개됩니다."
                               % (_shown(flow), "" if "publish_flow" in chance else ", 적지 않으면 direct 로 읽힙니다")))
        if _mode(reg, chance) == "auto" and chance.get("publish_flow") != REQUIRED_FLOW:
            errors.append(_msg("L3", "chance.mode 가 auto 인데 publish_flow 가 pr 로 적혀 있지 않습니다. 자동 생성은 초안 PR 로만 올라가야 합니다(publish_flow: pr)."))
        per_day = _limits(reg, chance).get("max_posts_per_day")
        if not (_is_int(per_day) and per_day == MAX_POSTS_PER_DAY):
            errors.append(_msg("L4", "chance.limits.max_posts_per_day 는 %d 이어야 합니다(지금 %s)." % (MAX_POSTS_PER_DAY, _shown(per_day))))
        problem = _open_drafts_error(reg, chance, locked=True)
        if problem:
            errors.append(problem)
        problem = _weekly_cap_error(reg, chance, locked=True)
        if problem:
            errors.append(problem)
        languages = chance["languages"] if "languages" in chance else _defaults(reg).get("languages")
        if languages is not None:
            ok = (isinstance(languages, list) and "ko" in languages and len(set(map(str, languages))) == len(languages)
                  and all(isinstance(item, str) and item in LANGUAGE_CODES for item in languages))
            if not ok:
                errors.append(_msg("L6", "chance.languages 가 올바르지 않습니다 — ko 를 포함하고 ko·en 만 겹침 없이 담은 목록이어야 합니다(['ko'] 또는 ['ko', 'en']; 지금 %s)."
                                   % _shown(languages)))
    for raw in _blogs(reg):
        if raw.get("key") == CHANCE_KEY:
            continue
        name = one_line(raw.get("key"), 40)
        mode = _mode(reg, raw)
        if mode not in SAFE_MODES:
            errors.append(_msg("L2", "블로그 '%s' 의 mode 가 %s 입니다. 잠금이 켜져 있으면 Chance 밖의 블로그는 %s 만 쓸 수 있습니다 — auto 는 사람 승인 없이 공개됩니다."
                               % (name, _shown(mode), "·".join(SAFE_MODES))))
        per_day = _limits(reg, raw).get("max_posts_per_day")
        if not (_is_int(per_day) and per_day == MAX_POSTS_PER_DAY):
            errors.append(_msg("L7", "블로그 '%s' 의 limits.max_posts_per_day 는 %d 이어야 합니다(지금 %s)." % (name, MAX_POSTS_PER_DAY, _shown(per_day))))
    return errors


def lock_errors(reg):
    """잠금이 켜져 있을 때(true 이거나 모르는 값) 어긴 규칙의 문장 목록. 꺼져 있으면 빈 목록 — 규칙은 적용되지 않는다. 입력이 어떤 모양이어도 예외를 내지 않는다."""
    state = lock_state(reg)
    if state not in (STATE_ON, STATE_INVALID):
        return []
    errors = []
    if state == STATE_INVALID:
        errors.append(_msg("L0", "resume_lock 은 true 또는 false 여야 합니다(지금 %s). 모르는 값은 잠금이 켜진 것으로 읽습니다." % _shown(reg[LOCK_KEY])))
    return errors + _rule_errors(reg)


def _key_msg(rule, text):
    return "레지스트리 키 " + rule + ": " + text


def _squash(key):
    """키 이름을 비교용으로 줄인다: 전각·호환 글자를 보통 글자로 풀고(NFKC) 소문자로 바꾼 뒤 공백·밑줄·하이픈을 뺀다('Resume-Lock ' → 'resumelock', 전각 'ｒｅｓｕｍｅ＿ｌｏｃｋ' 도 같다)."""
    return re.sub(r"[\s_\-]+", "", unicodedata.normalize("NFKC", str(key)).lower())


def _within_edits(left, right, limit):
    """두 문자열의 편집 거리(글자 하나 삽입·삭제·바꿈이 각 1)가 limit 이하인가. 길이 차이가 limit 를 넘으면 계산하지 않고 거짓이라 아주 긴 이름도 비용은 길이에 비례할 뿐이다."""
    if abs(len(left) - len(right)) > limit:
        return False
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, 1):
        current = [row]
        for column, right_char in enumerate(right, 1):
            current.append(min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + (left_char != right_char)))
        if min(current) > limit:
            return False
        previous = current
    return previous[-1] <= limit


def _looks_like_lock_key(key):
    """이름이 resume_lock 과 거의 같은가(오타로 보이는가): 줄인 이름(소문자·`_`·`-`·공백 제거)이 resumelock 을 품거나 resumelock 과 편집 거리 LOCK_KEY_EDITS 이내다.
    resume_lok·Resume_Lock·resume-lock·'resume_lock '·resumlok·resume_lock_v2 는 걸리고 block·clock·unlock·locked·resumed·blocklist·resume_after·publish_lock·lock·resume 은 안 걸린다
    (독립 재검증 D2 — 예전에는 resume 이나 lock 낱말이 든 모르는 키 전부를 오타라고 안내하고 실행도 멈췄다)."""
    squashed = _squash(key)
    return LOCK_KEY_SQUASHED in squashed or _within_edits(squashed, LOCK_KEY_SQUASHED, LOCK_KEY_EDITS)


def _path_text(path):
    """K2 가 찾은 자리의 사람이 읽는 이름: 'defaults'·"블로그 'chance'"·'defaults.limits'·"블로그 'chance'.limits"·'defaults.x[0]'. path 는 (앞 경로, 칸)을 겹쳐 쌓은 사슬이다."""
    parts = []
    while path is not None:
        path, part = path
        parts.append(part)
    text = ""
    for part in reversed(parts):
        if isinstance(part, tuple):                       # ("블로그", key) — 블로그 항목 하나(앞 경로를 버리고 여기서 시작한다)
            text = "블로그 '%s'" % one_line(part[1], 40)
        elif isinstance(part, int):
            text += "[%d]" % part
        else:
            text += ("." if text else "") + one_line(part, 40)
    return text


def _scan_misplaced_lock_keys(reg):
    """최상위 밖의 모든 사전(defaults·블로그 항목과 그 안의 limits·schedule·state 처럼 얼마나 깊든)에서 resume_lock 처럼 보이는 키를 찾는다.
    → (앞 MAX_KEY_MESSAGES 개의 (자리, 키), 모두 몇 개인가, 깊이 상한을 넘은 곳이 있는가).
    반복문(큐)으로 사전·목록을 한 번씩만 본다 — 순환이나 같은 하위 구조를 여러 곳이 가리키는 입력, 아주 큰 입력에도 입력 크기에 비례하고, 깊이는 MAX_KEY_SCAN_DEPTH 까지만 들어간다."""
    first, hits, too_deep = [], 0, False
    seen = {id(reg)}
    queue = deque((value, (None, key), 1) for key, value in reg.items() if isinstance(value, (dict, list)))
    while queue:
        node, path, depth = queue.popleft()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if depth > MAX_KEY_SCAN_DEPTH:
            too_deep = True
            continue
        if isinstance(node, dict):
            for key, value in node.items():
                if _looks_like_lock_key(key):
                    hits += 1
                    if len(first) < MAX_KEY_MESSAGES:
                        first.append((path, key))
                if isinstance(value, (dict, list)):
                    queue.append((value, (path, key), depth + 1))
        else:
            for index, value in enumerate(node):
                if isinstance(value, (dict, list)):
                    step = ("블로그", value.get("key")) if path == (None, "blogs") and isinstance(value, dict) else index
                    queue.append((value, (path, step), depth + 1))
    return first, hits, too_deep


def _misplaced_lock_key_errors(reg):
    """K2: 최상위 밖 어디에든(깊이 무관) resume_lock(이나 그 오타)이 있다. 잠금은 최상위 키만 읽으므로 거기 두면 꺼진 채로 통과한다. 문장은 앞 MAX_KEY_MESSAGES 개와 '외 N개'."""
    if not isinstance(reg, dict):
        return []
    first, hits, too_deep = _scan_misplaced_lock_keys(reg)
    errors = [_key_msg("K2", "%s 안에 %s 가 있습니다 — resume_lock 은 레지스트리 맨 위(최상위)에만 둡니다. 어느 깊이든 여기 두면 잠금이 꺼진 채로 통과합니다." % (_path_text(path), _shown(key)))
              for path, key in first]
    if hits > len(first):
        errors.append(_key_msg("K2", "… 외 %d개의 resume_lock 모양 이름이 최상위 밖에 더 있습니다(출력은 앞 %d개만 냅니다)." % (hits - len(first), MAX_KEY_MESSAGES)))
    if too_deep:
        errors.append(_key_msg("K2", "레지스트리 구조가 너무 깊어(깊이 %d 초과) 잠금 키의 위치를 끝까지 확인할 수 없습니다 — 구조를 줄이세요." % MAX_KEY_SCAN_DEPTH))
    return errors


def _unknown_top_level_errors(reg, only_lock_like):
    """K1: 알려진 키(KNOWN_TOP_LEVEL_KEYS)가 아닌 최상위 키. only_lock_like 이면 resume_lock 오타로 보이는 것만(실행 시 가드용), 아니면 모르는 키 전부(검증기용).
    문장은 앞 MAX_KEY_MESSAGES 개와 '외 N개' 한 줄이다(모르는 키가 아주 많아도 출력이 커지지 않는다)."""
    errors, extra = [], 0
    if not isinstance(reg, dict):
        return errors
    for key in reg:
        if key in KNOWN_TOP_LEVEL_KEYS:
            continue
        lock_like = _looks_like_lock_key(key)
        if only_lock_like and not lock_like:
            continue
        if len(errors) >= MAX_KEY_MESSAGES:
            extra += 1
            continue
        if lock_like:
            errors.append(_key_msg("K1", "최상위 키 %s 는 알려진 키가 아닙니다 — resume_lock 오타로 보입니다. 이름이 resume_lock 과 거의 같습니다. 잠금 키는 정확히 resume_lock(소문자·밑줄, 앞뒤 공백 없음)이어야 하고, "
                                          "오타면 잠금이 꺼진 채로 통과합니다." % _shown(key)))
        else:
            errors.append(_key_msg("K1", "알 수 없는 최상위 키 %s 가 있습니다 — 허용되는 최상위 키는 %s 뿐입니다(새 키는 pipeline/publish_lock.py 의 KNOWN_TOP_LEVEL_KEYS 와 시험을 함께 고쳐 의도적으로 더합니다)."
                                          % (_shown(key), ", ".join(KNOWN_TOP_LEVEL_KEYS))))
    if extra:
        errors.append(_key_msg("K1", "… 외 %d개의 최상위 키가 더 있습니다(출력은 앞 %d개만 냅니다)." % (extra, MAX_KEY_MESSAGES)))
    return errors


def lock_key_problems(reg):
    """잠금 키가 잘못 적힌 곳(K1 의 오타로 보이는 키 + K2 의 잘못된 위치 — 어느 깊이든). 이것들은 '켠 줄 알았는데 꺼진 채로 통과'하는 길이라 실행 시에도 멈춘다(가드·chance_flow·Blogger 러너·check).
    잠금 키가 없는 지금의 레지스트리에서는 항상 빈 목록. 입력이 어떤 모양이어도 예외를 내지 않는다."""
    if not isinstance(reg, dict):
        return []
    return _unknown_top_level_errors(reg, True) + _misplaced_lock_key_errors(reg)


def registry_errors(reg):
    """레지스트리 검증이 더하는 오류: 알려진 최상위 키만 허용(K1)·잠금 키 위치(K2) — 잠금과 무관하게 항상. 잠금이 켜져 있으면 lock_errors, 꺼져 있어도 값 모양은 본다(값이 있는
    chance.limits.max_open_drafts·max_posts_per_week 는 1 이상 정수 — 잘못 적은 값이 조용히 '규칙 없음'이 되지 않게). 키를 적지 않은 지금의 레지스트리에서는 항상 빈 목록이다."""
    errors = _unknown_top_level_errors(reg, False) + _misplaced_lock_key_errors(reg) if isinstance(reg, dict) else []
    errors += lock_errors(reg)
    chance = _chance(reg)
    if not lock_active(reg) and chance is not None:
        problem = _open_drafts_error(reg, chance, locked=False)
        if problem:
            errors.append(problem)
        problem = _weekly_cap_error(reg, chance, locked=False)
        if problem:
            errors.append(problem)
    return errors


def posts_today(history, today):
    """이력(history.json)에서 날짜(KST, YYYY-MM-DD)가 today 인 항목 수 — 정기·수동·승인 대기·닫힌 초안 모두 센다(만든 글은 이력에 남는다)."""
    return sum(1 for item in history if isinstance(item, dict) and item.get("date") == today)


_DAY_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# count: 창 안에서 센 글 수. 나머지 셋은 '날짜를 믿고 셀 수 없는' 항목 수다 — 하나라도 있으면 count 는 믿을 수 없어 가드가 멈춘다(읽을 수 있는 것만 세지 않는다).
WeeklyPosts = namedtuple("WeeklyPosts", "count unreadable future branch_future")


def parse_day(value):
    """날짜 글(YYYY-MM-DD — 아스키 숫자만, 실제 달력에 있는 날)을 datetime.date 로. 글이 아니거나 그 밖의 모양(시각·시각대 표기·앞뒤 공백·줄바꿈·전각 숫자·달력에 없는 날)이면 None."""
    if not isinstance(value, str) or _DAY_RE.fullmatch(value) is None:
        return None
    try:
        return date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        return None


def week_start(today):
    """주간 상한을 세는 창의 첫 날: today(datetime.date)를 포함해 WEEK_WINDOW_DAYS 일이므로 today 의 6일 전이다(7일 전은 창 밖)."""
    return today - timedelta(days=WEEK_WINDOW_DAYS - 1)


def weekly_posts(history, remote_names, today):
    """굴러가는 7일(week_start(today) 부터 today 까지, 양끝 포함)에 만들어진 Chance 글 수 — **이력 항목**(`date`)과 **이력에 아직 없는 원격 초안 브랜치**(브랜치 이름의 날짜)를 중복 없이 센다.
    이력은 공개된 글도 승인 대기·닫힌 초안도 담는다(draft_flow.deliver 는 이력 항목을 글과 따로 main 에 올린다). 그래도 이력 push 와 롤백이 모두 실패한 드문 경우처럼 원격에는 초안 브랜치가 있는데
    이력에는 없을 수 있어 그런 브랜치는 따로 센다. 두 목록을 잇는 열쇠는 **초안 브랜치 이름**이다(이력 항목의 `branch` = 원격 브랜치 이름, 이력 항목이 flow=pr 이어야 잇는다 —
    drafts.unmerged_draft_branches 와 같은 규칙). 잇는 항목이 있으면 그 브랜치는 이력 항목으로만 센다(날짜는 이력의 `date`).
    세는 단위는 하루 상한과 같다: 이력 항목 하나(한국어·영어 한 쌍) 또는 이력에 없는 브랜치 하나. 사전이 아닌 항목(실제 이력 맨 앞의 옛 형식 제목 문자열 5개 등)은 글 항목이 아니라 건너뛴다(슬롯·하루 상한도 그렇다).
    **날짜를 믿을 수 없는 항목은 세지 않고 따로 알린다**(호출한 쪽이 멈춘다): 사전 항목의 `date` 가 없거나 YYYY-MM-DD 가 아님(unreadable)·오늘보다 뒤 날짜(future), 이력에 없는 브랜치의 이름 날짜가 오늘보다 뒤(branch_future).
    이 흐름이 만들지 않는 이름의 브랜치(drafts.parse_branch 가 None)는 세지 않는다 — 열린 초안 상한과 같다."""
    from pipeline import drafts   # 순환 import 를 피하려고 함수 안에서 읽는다
    start = week_start(today)
    count = unreadable = future = branch_future = 0
    linked = set()
    for item in history:
        if not isinstance(item, dict):
            continue
        branch = item.get("branch")
        if item.get("flow") == drafts.FLOW_PR and isinstance(branch, str):
            linked.add(branch)
        day = parse_day(item.get("date"))
        if day is None:
            unreadable += 1
        elif day > today:
            future += 1
        elif day >= start:
            count += 1
    for name in set(remote_names):
        info = drafts.parse_branch(name)
        if info is None or name in linked:
            continue
        if info.day > today:
            branch_future += 1
        elif info.day >= start:
            count += 1
    return WeeklyPosts(count, unreadable, future, branch_future)


def registry_block(reg):
    """잠금 키가 잘못 적혀 있거나(K1 오타·K2 위치), 잠금이 켜져 있는데 레지스트리가 규칙을 어기면 Block, 아니면 None. 키 문제가 있으면 오류 문장도 '키가 잘못 적혀 있다'로 다르다."""
    key_problems = lock_key_problems(reg)
    errors = lock_errors(reg)
    if not (key_problems or errors):
        return None
    return Block(CODE_BLOCKED, key_problems + errors, KEY_ERROR if key_problems else LOCK_ERROR)


def publish_block(reg, blog_key):
    """잠금이 켜져 있으면 즉시 게시(Blogger 수동 입력 publish 포함)는 할 수 없다: Block, 꺼져 있으면 None. 블로그 key 는 로그 줄에만 쓴다."""
    if not lock_active(reg):
        return None
    return Block(CODE_BLOCKED, ["블로그 '%s': 제한 재개 잠금이 켜져 있어 즉시 게시는 할 수 없습니다 — Blogger 는 초안함(draft)·저장소 파일(off)로만 올립니다." % one_line(blog_key, 40)],
                 "제한 재개 잠금이 켜져 있어 즉시 게시는 하지 않습니다 — publish 입력을 draft 또는 off 로 바꿔 다시 실행하세요.")


# ============================================================================
# 읽기 전용 I/O — 실행 시작 가드(generator.py main() 앞부분 한 줄이 부른다)
# ============================================================================
def shadow_state(environ):
    """환경 변수 SHADOW_RUN 의 상태: on(SHADOW_ON_VALUES) · off(SHADOW_OFF_VALUES — 없거나 비어 있어도 off) · invalid(그 밖의 값). 대소문자·앞뒤 공백은 무시한다."""
    raw = str((environ or {}).get("SHADOW_RUN") or "").strip().lower()
    if raw in SHADOW_ON_VALUES:
        return "on"
    return "off" if raw in SHADOW_OFF_VALUES else "invalid"


def _summary_note(line):
    """실행 요약(GITHUB_STEP_SUMMARY)에 한 줄을 덧붙인다(워크플로 단계의 `check`·`check-direct` 가 잠금 상태를 남긴다). 환경 변수가 없거나 쓰지 못하면 아무 일도 하지 않는다."""
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(line.rstrip() + "\n\n")
    except OSError:
        pass


def _skip_line(code, **fields):
    """generator.skip_line 과 같은 모양: [SKIP] code=CODE key=value …"""
    parts = ["[SKIP] code=" + code]
    parts.extend("%s=%s" % (key, value) for key, value in fields.items())
    return " ".join(parts)


def _load_registry(load):
    """레지스트리 사전. 읽지 못하면 None(RegistryError 만 잡는다 — 다른 예외는 그대로 올라간다)."""
    from pipeline import registry
    try:
        return (load or registry.load_registry)()
    except registry.RegistryError:
        return None


def _stop(out, write_summary, code, lines, error, exit_code):
    """로그 줄·요약을 남기고 프로세스를 끝낸다(SystemExit). 멈춤(exit 1)은 ::error:: 한 줄, 정상 건너뜀(exit 0)은 호출한 쪽이 이미 줄을 냈다."""
    for line in lines:
        out(("[잠금 오류] " if exit_code else "[잠금] ") + line)
    if error:
        out("::error::" + error)
    try:
        write_summary("\n".join(["### Chance_Blog 실행 요약", "- 결과: **%s** — %s" % (code, md_cell(lines[0] if lines else "", 200))]
                                + ["- " + md_cell(line, 200) for line in lines[1:]]))
    except OSError:
        pass   # 요약은 보고용이다 — 쓰지 못해도 멈춤·건너뜀 결과는 바뀌지 않는다(write_step_summary 는 이미 OSError 를 삼키지만 대역이 올릴 수 있다)
    raise SystemExit(exit_code)


def _remote_drafts(remote_drafts):
    """원격의 초안 브랜치 이름 목록. 확인하지 못했으면 None."""
    if remote_drafts is not None:
        return remote_drafts()
    from pipeline import draft_flow
    try:
        return sorted(draft_flow.ls_remote_drafts(draft_flow.Git()))
    except draft_flow.GitError:
        return None


def read_history_strict(path):
    """이력 파일의 목록. 파일이 없으면 [](아직 글이 없다). 읽을 수 없거나(깨짐) 목록이 아니면 None — 하루 상한을 셀 수 없다.
    생성기의 read_history 는 깨진 이력을 빈 기록으로 읽고 계속하지만, 잠금 가드는 센 값이 0 이 되면 상한이 뚫리므로 세지 못하면 멈춘다."""
    target = Path(path)
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, list) else None


def _check_weekly_cap(environ, today, history, names, cap, out, write_summary):
    """주간 상한: 굴러가는 7일(today 포함)에 만들어진 글 수(weekly_posts)가 cap 이상이면 정상 건너뜀(SystemExit 0, 코드 LOCK_WEEKLY_CAP — 정기·수동 실행 모두, 수동이면 `::notice::`),
    날짜를 믿고 셀 수 없으면 멈춤(SystemExit 1, 코드 LOCK_BLOCKED + reason — 읽을 수 있는 항목만 세고 지나가지 않는다). 통과하면 조용히 돌아온다.
    today: 오늘(KST, YYYY-MM-DD 글) · names: 원격 초안 브랜치 이름 목록(None 이 아님 — 모르는 경우는 호출한 쪽이 이미 멈췄다) · cap: 레지스트리 값(1 또는 2)."""
    today_day = parse_day(today)
    try:
        start = week_start(today_day) if today_day is not None else None
    except OverflowError:   # 아주 이른 날짜(서기 1년 첫 주)는 6일 전을 달력에서 셀 수 없다
        start = None
    if start is None:   # 지금 날짜가 달력 날짜로 읽히지 않으면 일주일 창을 정할 수 없다(정상 실행에서는 일어나지 않는다)
        out(_skip_line(CODE_BLOCKED, reason="CLOCK_UNREADABLE"))
        _stop(out, write_summary, CODE_BLOCKED, ["지금 날짜(%s)를 읽을 수 없어 일주일 안의 글 수를 셀 수 없습니다 — 글을 만들지 않고 멈춥니다." % _shown(today)], WEEKLY_DATE_ERROR, 1)
    found = weekly_posts(history, names, today_day)
    problems = []   # (reason, 로그 줄) — 앞의 reason 이 `[SKIP] code=LOCK_BLOCKED reason=…` 줄에 나가고 줄은 모두 로그·요약에 남는다
    if found.unreadable:
        problems.append(("HISTORY_DATE_UNREADABLE", "이력(history.json)의 글 항목 %d개에 날짜가 없거나 YYYY-MM-DD 모양이 아니라 일주일 안의 글 수를 셀 수 없습니다 — 읽을 수 있는 항목만 세고 넘어가지 않고, 글을 만들지 않은 채 멈춥니다."
                         % found.unreadable))
    if found.future:
        problems.append(("HISTORY_DATE_FUTURE", "이력(history.json)의 글 항목 %d개가 오늘(%s)보다 뒤 날짜라 일주일 안의 글 수를 믿고 셀 수 없습니다 — 글을 만들지 않고 멈춥니다." % (found.future, today)))
    if found.branch_future:
        problems.append(("DRAFT_BRANCH_DATE_FUTURE", "이력에 없는 초안 브랜치 %d개의 이름 날짜가 오늘(%s)보다 뒤라 일주일 안의 글 수를 믿고 셀 수 없습니다 — 글을 만들지 않고 멈춥니다." % (found.branch_future, today)))
    if problems:
        out(_skip_line(CODE_BLOCKED, reason=problems[0][0]))
        _stop(out, write_summary, CODE_BLOCKED, [line for _reason, line in problems], WEEKLY_DATE_ERROR, 1)
    if found.count >= cap:
        manual = str(environ.get("EVENT_NAME", "")).strip().lower() != "schedule"
        out(_skip_line(CODE_WEEKLY_CAP, since=start.isoformat(), until=today, week=found.count, cap=cap))
        if manual:
            out("::notice::제한 재개 잠금: 최근 7일 안에 이미 주간 상한만큼 글이 만들어져 이번 수동 실행은 글을 만들지 않았습니다(정상 건너뜀).")
        _stop(out, write_summary, CODE_WEEKLY_CAP,
              ["최근 7일(%s부터 %s까지)에 이미 %d건이 만들어져 주간 상한(%d건)에 도달했습니다(정상 건너뜀) — 잠금이 켜져 있으면 정기·수동 실행 모두, 가장 오래된 글이 7일 창에서 빠져 건수가 줄 때까지 새 글을 만들지 않습니다"
               "(승인 대기·닫은 초안도 건수에 들어갑니다)." % (start.isoformat(), today, found.count, cap)], None, 0)


def guard_start(environ, history_path, now_kst, fix_images, dry_run, write_summary, *, out=print, load=None, remote_drafts=None, exists=None):
    """생성기 실행 시작 가드. 정지(PIPELINE_PAUSE) 검사 직후 한 번 부른다. 아무 문제가 없으면 조용히 돌아온다(잠금이 꺼져 있고 열린 초안 상한 값도 없으면 레지스트리를 읽는 것 말고 아무것도 하지 않는다).
    멈춤은 SystemExit(1) + `::error::`, 정상 건너뜀(하루 상한·열린 초안 상한·주간 상한 도달)은 SystemExit(0) + 로그·요약. 상한을 보는 순서는 하루 → (원격 초안 목록을 못 읽으면 멈춤) → 열린 초안 → 주간이다:
    두 상한이 함께 걸리면 앞의 코드가 나온다(코드 안정 — 주간 상한이 생기기 전에 이미 있던 결과는 바뀌지 않고, 새 코드는 예전에 통과하던 경우에만 나온다).

    environ: 환경 변수(SHADOW_RUN·EVENT_NAME 만 읽는다) · history_path: 이력 파일 경로(읽기만) · now_kst: 지금(KST aware) · fix_images·dry_run: 이 실행의 모드 ·
    write_summary: 실행 요약 쓰기 · load·remote_drafts·exists: 시험용 대체(레지스트리 읽기·원격 초안 브랜치 이름 목록(None = 확인 못 함)·글 파일 존재 확인)."""
    reg = _load_registry(load)
    state = lock_state(reg)
    if state == STATE_UNREADABLE:
        if fix_images and not dry_run:   # 레지스트리를 읽지 않고 직접 커밋하던 길만 막는다(글을 만드는 길은 drafts.chance_flow 가 읽지 못하면 이미 멈춘다)
            _stop(out, write_summary, CODE_BLOCKED, ["레지스트리를 읽을 수 없어 제한 재개 잠금 상태를 알 수 없습니다 — 기존 글 이미지 교체(main 직접 커밋)는 하지 않습니다."],
                  "레지스트리를 읽을 수 없어 제한 재개 잠금 상태를 알 수 없습니다 — 기존 글 이미지 교체를 멈춥니다.", 1)
        return
    block = registry_block(reg)
    if block is not None:
        out(_skip_line(block.code, rules=",".join(sorted({line.split(":")[0].split()[-1] for line in block.lines}))))
        _stop(out, write_summary, block.code, block.lines, block.error, 1)
    locked = lock_active(reg)
    if locked:   # 잠금이 켜져 있을 때만 상태를 남긴다 — 꺼져 있으면(키가 없든 false 든) 출력이 이전과 바이트까지 같아야 한다(기준선과 견줘 확인 — 키가 있을 때 꺼짐까지 남기면 false 인 시나리오가 달라진다). 꺼짐은 `check` 로 본다. 오타·위치 오류는 위에서 이미 멈췄다
        out("[잠금] 제한 재개 잠금: 켜짐")
    shadow = shadow_state(environ)
    if locked and shadow == "invalid":   # 그림자 실행인지 알 수 없으면 실행하지 않는다(GATE 도 같은 값 집합을 쓴다). 꺼짐일 때는 이 가드가 아무것도 하지 않으므로 보지 않는다
        out(_skip_line(CODE_BLOCKED, reason="SHADOW_RUN_VALUE"))
        _stop(out, write_summary, CODE_BLOCKED,
              ["SHADOW_RUN 값을 알 수 없습니다(지금 %s) — 켜짐은 %s, 꺼짐은 비움·%s 입니다. 그림자 실행인지 알 수 없으면 실행하지 않습니다."
               % (_shown(str((environ or {}).get("SHADOW_RUN"))), "·".join(SHADOW_ON_VALUES), "·".join(v for v in SHADOW_OFF_VALUES if v))],
              "SHADOW_RUN 값을 알 수 없어 실행하지 않습니다 — 켜짐(1·true·yes·on·enabled) 또는 꺼짐(비움·0·false·no·off·disabled)으로 적으세요.", 2)
    if locked and fix_images and not dry_run:
        out(_skip_line(CODE_BLOCKED, reason="FIX_IMAGES"))
        _stop(out, write_summary, CODE_BLOCKED, ["제한 재개 잠금이 켜져 있어 기존 글 이미지 교체(main 직접 커밋)는 하지 않습니다 — 이미지 변경은 이슈 수정 요청(수정안 PR)으로 하세요."],
              "제한 재개 잠금이 켜져 있어 기존 글 이미지 교체(main 직접 커밋)를 멈춥니다.", 1)
    if fix_images or dry_run or shadow == "on":
        # 연습·읽기 전용 그림자 실행·이미지 교체 연습은 글을 올리지 않으므로 상한을 세지 않는다.
        # 그림자 실행은 GATE 병합 뒤 순서(정지 검사 → 그림자 분기 → 이 가드)에서 그림자 분기가 읽기 전용으로 처리하고 끝나므로 평소에는 여기까지 오지 않는다 —
        # 이 예외는 그림자 분기를 지나쳐 온 경우를 위한 방어선이다(docs/PUBLISH_PATHS.md §4-2·§7).
        return
    limit = open_drafts_limit(reg)
    counts_open = limit is not None and (locked or flow_of(reg) == REQUIRED_FLOW)
    if not locked and not counts_open:
        return
    history = read_history_strict(history_path)
    if history is None:
        out(_skip_line(CODE_BLOCKED, reason="HISTORY_UNREADABLE"))
        _stop(out, write_summary, CODE_BLOCKED, ["이력 파일(history.json)을 읽을 수 없어 하루 상한·열린 초안 상한을 셀 수 없습니다 — 글을 만들지 않고 멈춥니다(손상된 이력은 덮어쓰지 않습니다)."],
              "이력 파일을 읽을 수 없어 상한을 셀 수 없습니다 — 글을 만들지 않고 멈춥니다.", 1)
    weekly = weekly_posts_limit(reg) if locked else None   # 주간 상한은 잠금이 켜져 있을 때만 센다(꺼짐 = 이전과 같다). 켜져 있으면 L8 이 값이 1 이상 2 이하임을 보증했다
    if locked:
        today = now_kst().strftime("%Y-%m-%d")
        done = posts_today(history, today)
        if done >= MAX_POSTS_PER_DAY:
            manual = str(environ.get("EVENT_NAME", "")).strip().lower() != "schedule"
            out(_skip_line(CODE_DAILY_CAP, date=today, today=done, cap=MAX_POSTS_PER_DAY))
            if manual:
                out("::notice::제한 재개 잠금: 오늘 이미 하루 상한만큼 글이 만들어져 이번 수동 실행은 글을 만들지 않았습니다(정상 건너뜀).")
            _stop(out, write_summary, CODE_DAILY_CAP,
                  ["오늘(%s) 이미 %d건이 만들어져 하루 상한(%d건)에 도달했습니다(정상 건너뜀) — 잠금이 켜져 있으면 정기·수동 실행 모두 오늘은 새 글을 만들지 않습니다." % (today, done, MAX_POSTS_PER_DAY)],
                  None, 0)
    if not counts_open and weekly is None:
        return
    from pipeline import drafts
    names = _remote_drafts(remote_drafts)   # 열린 초안 상한과 주간 상한이 같은 목록을 쓴다(한 번만 읽는다). 못 읽으면 어느 쪽도 셀 수 없어 멈춘다(OPEN_DRAFTS_UNKNOWN — fail closed)
    if names is None:
        out(_skip_line(CODE_DRAFTS_UNKNOWN))
        out("::warning::열린 초안 수를 확인하지 못해 이번 실행은 글을 만들지 않았습니다. 다음 실행에서 다시 시도합니다.")
        _stop(out, write_summary, CODE_DRAFTS_UNKNOWN, ["열린 초안 수를 확인하지 못해 이번 실행은 글을 만들지 않았습니다(다음 실행에서 다시 확인)."], None, 0)
    if counts_open:
        unmerged = drafts.unmerged_draft_branches(names, history, exists or os.path.exists)
        if len(unmerged) >= limit:
            out(_skip_line(CODE_OPEN_DRAFTS, open=len(unmerged), limit=limit))
            _stop(out, write_summary, CODE_OPEN_DRAFTS,
                  ["승인을 기다리는(또는 닫은 지 오래되지 않아 아직 정리되지 않은) 초안 브랜치가 %d개로 상한(%d개)에 도달했습니다(정상 건너뜀) — PR 을 병합하거나 닫아 정리되기 전에는 새 초안을 만들지 않습니다."
                   % (len(unmerged), limit)], None, 0)
    if weekly is not None:
        _check_weekly_cap(environ, today, history, names, weekly, out, write_summary)


# ============================================================================
# CLI — 워크플로 단계가 부른다
# ============================================================================
def main(argv=None):
    """python -m pipeline.publish_lock check          레지스트리가 잠금 규칙을 지키는지 본다(켜져 있을 때만 규칙을 적용). 어기면 종료 1.
       python -m pipeline.publish_lock check-direct   main 에 직접 커밋하는 워크플로의 첫 단계: 잠금이 켜져 있거나 상태를 알 수 없으면 종료 1(실행하지 않는다), 꺼져 있으면 0."""
    safe_output()
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else ""
    if command not in ("check", "check-direct"):
        print("사용법: python -m pipeline.publish_lock {check|check-direct}", file=sys.stderr)
        return 2
    reg = _load_registry(None)
    state = lock_state(reg)
    key_problems = lock_key_problems(reg)
    if command == "check":
        if state == STATE_UNREADABLE:
            print("[오류] 레지스트리를 읽을 수 없습니다.")
            return 1
        errors = key_problems + lock_errors(reg)
        for line in errors:
            print("[잠금 오류] " + line)
        status = "알 수 없음(키가 잘못 적혀 있습니다 — 위 오류를 고치세요)" if key_problems else ("켜짐" if lock_active(reg) else "꺼짐(규칙을 적용하지 않습니다)")
        print("제한 재개 잠금: " + status)
        _summary_note("- 제한 재개 잠금: " + status)
        return 1 if errors else 0
    if state != STATE_UNREADABLE and key_problems:
        for line in key_problems:
            print("[잠금 오류] " + line)
        _summary_note("- 제한 재개 잠금: 알 수 없음(키가 잘못 적혀 있어 직접 커밋 워크플로를 멈췄습니다)")
        print("::error::" + KEY_ERROR_DIRECT)
        return 1
    if state == STATE_OFF:
        print("[잠금] 제한 재개 잠금이 꺼져 있어 이 워크플로를 그대로 실행합니다.")
        _summary_note("- 제한 재개 잠금: 꺼짐 — 직접 커밋 워크플로를 그대로 실행합니다")
        return 0
    if state == STATE_UNREADABLE:
        print("::error::레지스트리를 읽을 수 없어 제한 재개 잠금 상태를 알 수 없습니다 — main 에 직접 커밋하는 이 워크플로는 멈춥니다.")
        _summary_note("- 제한 재개 잠금: 알 수 없음(레지스트리를 읽을 수 없어 직접 커밋 워크플로를 멈췄습니다)")
        return 1
    print("::error::제한 재개 잠금이 켜져 있어 main 에 직접 커밋하는 이 워크플로는 실행하지 않습니다 — 이미지 변경은 이슈 수정 요청(수정안 PR)으로 하세요.")
    _summary_note("- 제한 재개 잠금: 켜짐 — 직접 커밋 워크플로를 멈췄습니다")
    return 1


if __name__ == "__main__":
    sys.exit(main())
