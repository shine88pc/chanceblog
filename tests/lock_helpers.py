"""제한 재개 잠금(pipeline/publish_lock.py) 시험 공용 도구: 잠금 규칙을 모두 지키는 레지스트리 사본, 규칙을 하나씩 어기는 변형, 임시 레지스트리 파일.

이 도구가 만드는 '잠금 켬' 레지스트리는 운영자가 나중에 승인해 켤 때(별도 T3 변경) 바뀔 값들과 같다: resume_lock true · chance.publish_flow pr · chance.limits
max_posts_per_day 1 · max_open_drafts 3 · max_posts_per_week 2(주간 상한 — 규칙 L8). 진짜 pipeline/blogs.json 은 이 시험이 바꾸지 않는다(사본만 만든다). 네트워크·실제 시크릿 없이 돈다.
"""
import copy
import json
from pathlib import Path
from unittest import mock

import _bootstrap
from pipeline import publish_lock, registry

ROOT = _bootstrap.ROOT

CHANCE, MACAT, KCYOON, NAVER = "chance", "blogger_macat", "blogger_kcyoon", "naver_life_tips"


def real_registry():
    """진짜 레지스트리의 사본(시험이 마음대로 고쳐도 파일은 그대로다)."""
    return copy.deepcopy(registry.load_registry())


def guard_off():
    """생성기(generator.main)의 동작을 보는 기존 시험이 쓴다: 앞머리의 잠금 가드(publish_lock.guard_start)만 건너뛰는 패치(`with guard_off():` 또는 start/stop).
    그 시험들은 진짜 레지스트리와 임시 폴더(저장소가 아님)로 main() 을 돌린다. 운영자가 잠금을 켜는 변경(T3)으로 레지스트리 값이 바뀌어도 시험이
    가드의 하루 상한·열린 초안 수 확인(git ls-remote)에 걸려 멈추지 않게 한다 — 같은 이유로 draft_flow_on 도 시험 쪽에서 고정해 왔다.
    가드 자체와 main() 이 가드를 부르는 모양은 test_publish_lock 이 잠금 켬·꺼짐 모두 고정한다(그쪽은 이 패치를 쓰지 않는다)."""
    return mock.patch.object(publish_lock, "guard_start", lambda *args, **kwargs: None)


def today_registry():
    """진짜 레지스트리를 '제한 재개 잠금이 꺼진 오늘의 값'으로 맞춘 사본(resume_lock 키 없음 · chance.publish_flow direct · chance.limits 하루 2편) —
    '꺼져 있으면 이전과 같다'를 보는 시험의 기준이다. 진짜 레지스트리를 그대로 쓰지 않는 까닭: 켜는 변경(T3)이 레지스트리 값을 바꿔도 그 시험들이 흔들리지 않게 하려는 것이다.
    진짜 값이 이것과 같은지는 한 곳(`LockStateTest.test_the_real_registry_has_the_lock_off_today`)만 못박는다 — 켜는 변경은 그 시험 하나를 함께 고친다."""
    reg = real_registry()
    reg.pop("resume_lock", None)
    chance = blog_of(reg, CHANCE)
    chance["publish_flow"] = "direct"
    chance["limits"] = {"max_posts_per_day": 2}
    return reg


def blog_of(reg, key):
    return next(raw for raw in reg["blogs"] if raw["key"] == key)


def lock_ready(reg=None):
    """진짜 레지스트리 사본을 '잠금 켬 + 규칙 전부 지킴' 으로 바꾼다. 전체 레지스트리 검증도 통과해야 한다(시험이 확인한다)."""
    reg = real_registry() if reg is None else copy.deepcopy(reg)
    reg["resume_lock"] = True
    chance = blog_of(reg, CHANCE)
    chance["publish_flow"] = "pr"
    chance["limits"] = {"max_posts_per_day": 1, "max_open_drafts": 3, "max_posts_per_week": 2}
    return reg


def with_lock_off(reg):
    """같은 레지스트리의 잠금만 끈 사본(키를 지운다 — 지금 진짜 레지스트리와 같은 모양)."""
    reg = copy.deepcopy(reg)
    reg.pop("resume_lock", None)
    return reg


def mutated(mutate, base=None):
    """잠금 켬 레지스트리에 변형 하나를 적용한 사본."""
    reg = lock_ready(base)
    mutate(reg)
    return reg


def set_in(reg, key, **fields):
    blog_of(reg, key).update(fields)


def set_limit(reg, key, **limits):
    blog = blog_of(reg, key)
    blog["limits"] = {**blog.get("limits", {}), **limits}


def drop_limit(reg, key, name):
    blog_of(reg, key)["limits"].pop(name, None)


# 규칙 번호 → (설명, 그 규칙 하나만 어기는 변형 목록). 변형마다 '이 규칙의 메시지가 나와야 한다'를 시험이 확인하고, 같은 변형을 잠금 꺼짐에 적용하면 규칙 오류가 없어야 한다.
# 같은 변형이 다른 규칙도 함께 어기는 경우(L1 의 direct 는 L3 도 어긴다 — chance.mode 가 auto 라서)는 EXTRA 에 적는다.
VIOLATIONS = {
    "L0": [("resume_lock 이 문자열", lambda r: r.update(resume_lock="true")),
           ("resume_lock 이 숫자 1", lambda r: r.update(resume_lock=1)),
           ("resume_lock 이 null", lambda r: r.update(resume_lock=None))],
    "L1": [("publish_flow 가 direct", lambda r: set_in(r, CHANCE, publish_flow="direct")),
           ("publish_flow 를 적지 않음", lambda r: blog_of(r, CHANCE).pop("publish_flow")),
           ("publish_flow 가 모르는 값", lambda r: set_in(r, CHANCE, publish_flow="PR"))],
    "L2": [("영문 Blogger 가 auto", lambda r: set_in(r, MACAT, mode="auto")),
           ("한글 Blogger 가 auto", lambda r: set_in(r, KCYOON, mode="auto")),
           ("mode 가 모르는 값", lambda r: set_in(r, MACAT, mode="publish")),
           ("mode 를 적지 않고 기본값이 auto", lambda r: (blog_of(r, MACAT).pop("mode"), r["defaults"].update(mode="auto")))],
    "L3": [("auto 인데 publish_flow 가 direct", lambda r: set_in(r, CHANCE, publish_flow="direct")),
           ("auto 인데 publish_flow 가 없음", lambda r: blog_of(r, CHANCE).pop("publish_flow"))],
    "L4": [("하루 상한 2", lambda r: set_limit(r, CHANCE, max_posts_per_day=2)),
           ("하루 상한 0", lambda r: set_limit(r, CHANCE, max_posts_per_day=0)),
           ("하루 상한이 문자열", lambda r: set_limit(r, CHANCE, max_posts_per_day="1")),
           ("하루 상한이 참/거짓", lambda r: set_limit(r, CHANCE, max_posts_per_day=True))],
    "L5": [("열린 초안 상한이 없음", lambda r: drop_limit(r, CHANCE, "max_open_drafts")),
           ("열린 초안 상한이 4", lambda r: set_limit(r, CHANCE, max_open_drafts=4)),
           ("열린 초안 상한이 0", lambda r: set_limit(r, CHANCE, max_open_drafts=0)),
           ("열린 초안 상한이 문자열", lambda r: set_limit(r, CHANCE, max_open_drafts="3")),
           ("열린 초안 상한이 참/거짓", lambda r: set_limit(r, CHANCE, max_open_drafts=True))],
    "L6": [("languages 에 ko 가 없음", lambda r: set_in(r, CHANCE, languages=["en"])),
           ("languages 가 겹침", lambda r: set_in(r, CHANCE, languages=["ko", "ko"])),
           ("languages 에 모르는 언어", lambda r: set_in(r, CHANCE, languages=["ko", "fr"])),
           ("languages 가 문자열", lambda r: set_in(r, CHANCE, languages="ko")),
           ("languages 가 빈 목록", lambda r: set_in(r, CHANCE, languages=[])),
           ("languages 에 ja", lambda r: set_in(r, CHANCE, languages=["ko", "ja"]))],
    "L7": [("한글 Blogger 하루 상한 2", lambda r: set_limit(r, KCYOON, max_posts_per_day=2)),
           ("영문 Blogger 하루 상한 3", lambda r: set_limit(r, MACAT, max_posts_per_day=3)),
           ("네이버 하루 상한 2", lambda r: set_limit(r, NAVER, max_posts_per_day=2))],
    # L8 은 '잠금이 켜졌을 때만 위반'인 모양만 둔다(값이 없음·천장 2 를 넘음 — 레지스트리 범위 1–14 안이라 검증기의 일반 검사는 통과한다). 값 모양이 틀린 경우(0·불리언·문자열·소수·음수)는
    # 잠금이 꺼져 있어도 L8 의 모양 검사가 거절하므로 이 표(꺼짐에서 규칙 오류가 없어야 하는 시험들이 같이 쓴다)가 아니라 WeeklyLimitRuleTest 가 따로 본다.
    "L8": [("주간 상한이 없음", lambda r: drop_limit(r, CHANCE, "max_posts_per_week")),
           ("주간 상한이 3", lambda r: set_limit(r, CHANCE, max_posts_per_week=3)),
           ("주간 상한이 14", lambda r: set_limit(r, CHANCE, max_posts_per_week=14))],
}
# 잠금 키를 잘못 적는 변형(검증 지적 1): 잠금 키가 없으면 잠금이 꺼진 것이라, 이름 오타·위치 오류가 켠 줄 알았는데 꺼진 채로 통과하던 길이다. 켠 레지스트리(lock_ready)에도,
# 지금의 레지스트리(today_registry — 키 없음)에도 적용한다(후자는 '이제 잠금을 적어 넣으려다 오타를 낸' 경우).
def _move_lock_key(new_name):
    def mutate(reg):
        reg[new_name] = reg.pop(LOCK_KEY, True)
    return mutate


def put_in(reg, path, key="resume_lock", value=True):
    """사본 안의 자리 path 에 키를 둔다. path 의 첫 칸은 'defaults' 이거나 블로그 key, 그다음 칸은 그 안의 사전 이름(없으면 만든다)이다 — 예: ('chance', 'limits')."""
    node = reg["defaults"] if path[0] == "defaults" else blog_of(reg, path[0])
    for step in path[1:]:
        node = node.setdefault(step, {})
    node[key] = value


def _lock_key_into(*path):
    def mutate(reg):
        reg.pop(LOCK_KEY, None)
        put_in(reg, path)
    return mutate


LOCK_KEY = "resume_lock"
KEY_TYPOS = [
    ("키 이름 오타 resume_lok", _move_lock_key("resume_lok")),
    ("첫 글자 대문자 Resume_Lock", _move_lock_key("Resume_Lock")),
    ("전부 대문자 RESUME_LOCK", _move_lock_key("RESUME_LOCK")),
    ("하이픈 resume-lock", _move_lock_key("resume-lock")),
    ("뒤 공백 'resume_lock '", _move_lock_key("resume_lock ")),
    ("defaults 안에 둠", _lock_key_into("defaults")),
    ("chance 블로그 항목 안에 둠", _lock_key_into("chance")),
    ("defaults.limits 안(두 단계)에 둠", _lock_key_into("defaults", "limits")),
    ("chance.limits 안(두 단계)에 둠", _lock_key_into("chance", "limits")),
]
# 두 단계 이상 깊은 자리(독립 재검증 D1): 정상 레지스트리에 있는 사전 안과 세 단계 깊이까지
DEEP_PLACES = [("defaults", "limits"), ("defaults", "llm"), ("defaults", "health"), ("chance", "limits"), ("chance", "schedule"), ("chance", "state"), ("chance", "health"),
               ("blogger_macat", "limits"), ("naver_life_tips", "secrets"), ("defaults", "llm", "nested"), ("chance", "state", "a", "b")]
# 변형 하나가 함께 어기는 다른 규칙(시험이 둘 다 나와야 한다고 확인한다)
EXTRA = {("L1", "publish_flow 가 direct"): ("L3",), ("L1", "publish_flow 를 적지 않음"): ("L3",), ("L1", "publish_flow 가 모르는 값"): ("L3",),
         ("L3", "auto 인데 publish_flow 가 direct"): ("L1",), ("L3", "auto 인데 publish_flow 가 없음"): ("L1",)}


def write_registry(folder, reg, name="blogs.json"):
    """임시 폴더에 레지스트리 파일을 쓴다. 돌려주는 값: 경로(registry.REGISTRY_PATH 를 이것으로 바꿔 쓴다)."""
    path = Path(folder) / name
    path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    return path


def rules_in(messages):
    """오류 문장 목록에서 어긴 규칙 번호 집합(문장 앞 '제한 재개 잠금 L1:' 꼴)."""
    found = set()
    for message in messages:
        head = message.split(":")[0]
        if head.startswith("제한 재개 잠금 "):
            found.add(head.split()[-1])
    return found
