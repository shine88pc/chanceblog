"""발행 정지 변수 PIPELINE_PAUSE 를 읽는 곳 하나 — 읽는 모든 곳(생성기·Blogger 러너·초안 올리기·이슈 수정 처리기·그림자 실행 안내·워치독·확인 필요 모음)이 이 함수를 부른다(BP-S1-3, 결함 D-412).

값 해석(앞뒤 공백·대소문자 무시):
- 켜짐   1·true·yes·on            -> 정지
- 꺼짐   0·false·no·off, 비어 있음·없음 -> 정지 아님(이전과 같다)
- 그 밖의 값(enabled·paused·y·ture·2 …)  -> **정지로 읽고** 이유를 한 줄(::error::)로 알린다

왜: 예전에는 읽는 곳마다 {1,true,yes,on} 복사본이 있고 나머지를 모두 '정지 아님' 으로 읽었다 — 값 오타 하나로 킬 스위치가 조용히 꺼졌다. 그림자 변수 SHADOW_RUN 은 모르는 값을 거절하는데(generator.py) 킬 스위치가
열려 있던 것을 같은 결(fail closed)로 맞춘다. **지금 정지가 걸리는 값은 하나도 풀리지 않는다**(켜짐 집합 동작 불변). 워크플로·변수 값은 이 모듈이 바꾸지 않는다.

이 모듈은 표준 라이브러리도 부르지 않는 순수 함수만 둔다(다른 pipeline 모듈을 import 하지 않아 어느 쪽에서 불러도 순환이 생기지 않는다). 설명: docs/SECURITY_GUARDRAILS.md·docs/PUBLISH_PATHS.md.
"""

VAR = "PIPELINE_PAUSE"
ON_VALUES = frozenset({"1", "true", "yes", "on"})
OFF_VALUES = frozenset({"0", "false", "no", "off"})
ON, OFF, UNKNOWN = "on", "off", "unknown"

# 값을 알 수 없을 때 로그·요약에 한 줄로 싣는 고정 문장(받은 값은 싣지 않는다 — 변수 값이 여러 줄이거나 '::' 로 시작해도 워크플로 명령이 되지 않게)
SENTENCE = ("저장소 변수 PIPELINE_PAUSE 의 값을 알 수 없어 정지로 읽습니다(켜짐 1·true·yes·on, 꺼짐 0·false·no·off 또는 비움). "
            "값을 고치거나 변수를 지우세요.")


def classify(value):
    """값 하나의 판정: ON · OFF · UNKNOWN. 값이 없거나(None) 비어 있거나 공백뿐이면 OFF."""
    text = ("" if value is None else str(value)).strip().lower()
    if text in ON_VALUES:
        return ON
    if text == "" or text in OFF_VALUES:
        return OFF
    return UNKNOWN


def state(env):
    """환경(os.environ 이나 사전)에서 PIPELINE_PAUSE 를 읽어 ON · OFF · UNKNOWN 으로 돌려준다."""
    return classify(env.get(VAR))


def is_paused(env):
    """정지로 읽는가: 켜짐이거나 알 수 없는 값이면 참(fail closed)."""
    return state(env) != OFF


def is_unrecognized(env):
    """값이 있는데 켜짐·꺼짐 어느 쪽으로도 읽을 수 없는가."""
    return state(env) == UNKNOWN


def error_line(tag=""):
    """알 수 없는 값을 알리는 ::error:: 한 줄. tag 는 '[블로그키] ' 처럼 줄 앞에 붙일 고정 머리."""
    return "::error::" + tag + SENTENCE
