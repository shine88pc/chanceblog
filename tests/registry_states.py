"""레지스트리의 알려진 상태 셋과 켜기 전 고정 표본 — 켜는 변경(T3)과 시험을 떼어 놓는 장치(S2BFIX, 결정 D-308).

배경: 생성기·그림자 실행·잠금 가드를 진짜 레지스트리(`pipeline/blogs.json`)로 돌리던 시험은 레지스트리 값(콘텐츠 출처·허용 목록 모드·국문 단독·승인 흐름·상한·Gate·제한 재개 잠금)이 켜는 변경으로 바뀌면
한꺼번에 빨개진다 — 켜는 값을 저장소 밖 임시 사본에 적용해 보니 시험 25모듈 수백 건이 빨개졌다(독립 검증이 짚은 둘이 아니었다). 켜기 전 경로(피드·두 언어·직접 게시)를 시험하는 클래스는 진짜 값에 기댈 이유가 없으므로
이 파일의 **고정 표본**(켜기 전 진짜 레지스트리와 같은 사본 — `tests/fixtures/registry_states/pre_flip_blogs.json`)을 가리키게 했다(`lock_helpers.pre_flip`·`today_registry`·`lock_ready`·`pre_flip_registry`).
그러면 이 시험들은 켜기 전·후 어느 상태에서도 초록이고, 켜는 PR 은 진짜 값과 진짜 값을 못박은 소수 시험만 고친다.

알려진 상태 — 진짜 `pipeline/blogs.json` 은 언제나 이 셋 중 **정확히 하나**이고 아래 `EXPECTED_STATE` 가 그것이다(`tests/test_registry_state.py` 가 못박는다):
 - `pre_flip`: 켜기 전(지금) — 고정 표본 그대로.
 - `p2`: 값을 켠 뒤(콘텐츠 출처 facts·허용 목록 모드·국문 단독·승인 흐름·주간 상한 2, 허용 목록의 NOAA 켜짐) — 잠금·Gate 는 아직 꺼짐.
 - `p3`: 최소 품질 Gate(hold)와 제한 재개 잠금까지 켠 뒤(하루 1편·주 2편·열린 초안 3개).
켜는 PR 은 진짜 파일 값을 고치면서 **`EXPECTED_STATE` 를 한 칸 옮긴다** — 그 한 줄이 의도를 드러낸다. 진짜 값이 알려진 상태와 어긋나면(슬쩍 바뀌면) 가드 시험이 빨개진다.
표본이 진짜 값과 어긋난 채 시험이 가짜로 초록이 되는 일도 이 가드가 막는다(표본은 켜기 전 진짜 값과 같아야 하고, 켠 상태는 표본에 아래 값을 얹은 것과 같아야 한다).
"""
import json

import _bootstrap

ROOT = _bootstrap.ROOT
FIXTURE = ROOT / "tests" / "fixtures" / "registry_states" / "pre_flip_blogs.json"
REAL_BLOGS = ROOT / "pipeline" / "blogs.json"
REAL_SOURCES = ROOT / "pipeline" / "source_registry.json"

STATE_NAMES = ("pre_flip", "p2", "p3")
EXPECTED_STATE = "pre_flip"                         # 켜는 PR 이 이 한 줄을 한 칸 옮긴다(pre_flip → p2 → p3)
ENABLED_PROVIDERS = {"pre_flip": [], "p2": ["noaa_swpc_json"], "p3": ["noaa_swpc_json"]}      # 허용 목록(pipeline/source_registry.json)에서 켜진 제공처


def pre_flip_registry():
    """켜기 전 고정 표본(진짜 파일이 아니라 tests/fixtures 의 사본)의 새 사본 — 시험이 마음대로 고쳐도 파일은 그대로다."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def chance_of(reg):
    return next(blog for blog in reg["blogs"] if blog["key"] == "chance")


def state_registry(name):
    """알려진 상태 `name` 의 레지스트리: 켜기 전 고정 표본에 켜는 값을 얹은 새 사본(값은 T3 패치 02·03 이 진짜 파일에 적는 것과 같다)."""
    if name not in STATE_NAMES:
        raise KeyError(name)
    reg = pre_flip_registry()
    chance = chance_of(reg)
    if name in ("p2", "p3"):
        chance.update(languages=["ko"], publish_flow="pr", source_policy="allowlist", content_source="facts")
        chance["limits"] = {"max_posts_per_day": 2, "max_posts_per_week": 2}
    if name == "p3":
        reg["resume_lock"] = True
        chance["quality_gate"] = "hold"
        chance["limits"] = {"max_posts_per_day": 1, "max_posts_per_week": 2, "max_open_drafts": 3}
    return reg
