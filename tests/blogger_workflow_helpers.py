"""Blogger 워크플로 분리(작업 D) 시험 공용 도구.

blogger.yml 은 재사용 워크플로(on: workflow_call)이고, 채널별 래퍼 blogger-en.yml·blogger-ko.yml 이 `with:`·`secrets:` 로 값을 넘겨 부른다.
GitHub Actions 를 실행할 수 없는 환경에서도 '이벤트·입력 → 래퍼의 with 식 → 공용 워크플로의 환경변수 식'을 끝에서 끝까지 평가해 러너가 받는 환경변수를 구한다.
분리 전 blogger.yml 이 같은 이벤트·입력에서 낸 값(OLD_ENV 의 식)과 모든 조합에서 같은지는 tests/test_blogger_split.py 가 대조한다.
"""
import re

from test_workflow_names import _Parser, load, render      # 이름 시험이 쓰는 같은 식 해석기(그 모듈이 _bootstrap 을 불러 경로를 맞춘다)

REUSABLE = "blogger.yml"
# 레지스트리 블로그 key → 그 블로그를 부르는 채널별 래퍼 파일(레지스트리 workflow 필드와 같아야 한다 — 시험이 확인한다)
WRAPPERS = {"blogger_macat": "blogger-en.yml", "blogger_kcyoon": "blogger-ko.yml"}
WRAPPER_LABELS = {"blogger-en.yml": "Blogger 영문", "blogger-ko.yml": "Blogger 한글"}
CALL_INPUTS = ("blog", "topic", "dry_run", "publish", "auth_check")
BOOLEAN_INPUTS = ("dry_run", "auth_check")

# 분리 전 blogger.yml(2026-10-27, main c6c9acd)이 환경변수에 넘기던 식 그대로. 새 구조가 모든 이벤트·입력 조합에서 같은 값을 내는지 대조하는 기준이다.
OLD_ENV = {
    "AUTH_CHECK_ONLY": "${{ github.event_name == 'workflow_dispatch' && github.event.inputs.auth_check == 'true' && '1' || '' }}",
    "DRY_RUN": "${{ github.event.inputs.dry_run == 'true' && 'true' || 'false' }}",
    "BLOGGER_TOPIC": "${{ github.event.inputs.topic }}",
    "BLOGGER_PUBLISH": "${{ github.event_name == 'workflow_dispatch' && github.event.inputs.publish || '' }}",
    "BLOGGER_AUTH_CHECK": "${{ github.event_name == 'workflow_dispatch' && github.event.inputs.auth_check == 'true' && '1' || '' }}",
}


def call_job(wrapper):
    """래퍼의 (잡 id, 잡) — 공용 워크플로를 부르는 잡은 정확히 하나다."""
    jobs = load(wrapper)["jobs"]
    calls = [(job_id, job) for job_id, job in jobs.items() if str(job.get("uses", "")).endswith("/blogger.yml")]
    assert len(calls) == 1, (wrapper, list(jobs))
    return calls[0]


def event_context(event, event_inputs):
    """GitHub 가 래퍼에 주는 컨텍스트. github.event.inputs 는 문자열이고(수동 실행에만 있다), inputs 는 형이 있는 값이다."""
    event_inputs = dict(event_inputs or {})
    typed = {name: (value == "true" if name in BOOLEAN_INPUTS and isinstance(value, str) else value) for name, value in event_inputs.items()}
    payload = {"inputs": event_inputs} if event == "workflow_dispatch" else {}
    return {"github": {"event_name": event, "event": payload}, "inputs": typed if event == "workflow_dispatch" else {}}


def typed(template, ctx):
    """`${{ 식 }}` 한 덩어리면 식의 값 그대로(불리언·문자열), 아니면 문장 속 식을 풀어 쓴 문자열."""
    match = re.fullmatch(r"\s*\$\{\{(.*)\}\}\s*", template, re.S)
    return _Parser(match.group(1), ctx).parse() if match else render(template, ctx)


def wrapper_with(wrapper, event, event_inputs=None):
    """래퍼가 공용 워크플로에 넘기는 입력 값(`with:` 를 이벤트·입력으로 평가). 문자열 입력의 null 은 빈 문자열이 된다(GitHub 도 그렇게 넘긴다)."""
    ctx = event_context(event, event_inputs)
    given = {}
    for name, template in call_job(wrapper)[1]["with"].items():
        value = typed(template, ctx) if isinstance(template, str) else template
        given[name] = ("" if value is None else value) if name not in BOOLEAN_INPUTS else value
    return given


def _only(items, predicate):
    found = [item for item in items if predicate(item)]
    assert len(found) == 1, found
    return found[0]


def callee_steps():
    """공용 워크플로에서 환경변수를 만드는 세 곳: plan 단계(id=plan)·generate 잡 env·러너 단계(pipeline.run)."""
    jobs = load(REUSABLE)["jobs"]
    plan_step = _only(jobs["plan"]["steps"], lambda step: step.get("id") == "plan")
    run_step = _only(jobs["generate"]["steps"], lambda step: "pipeline.run" in str(step.get("run", "")))
    return plan_step, jobs["generate"], run_step


def callee_env(inputs):
    """공용 워크플로가 inputs(래퍼가 넘긴 값)에서 만드는 환경변수 — 러너·plan 단계가 받는 값."""
    plan_step, generate, run_step = callee_steps()
    ctx = {"inputs": inputs}
    return {"ONLY_BLOG": render(plan_step["env"]["ONLY_BLOG"], ctx), "AUTH_CHECK_ONLY": render(plan_step["env"]["AUTH_CHECK_ONLY"], ctx),
            "DRY_RUN": render(generate["env"]["DRY_RUN"], ctx), "BLOGGER_TOPIC": render(run_step["env"]["BLOGGER_TOPIC"], ctx),
            "BLOGGER_PUBLISH": render(run_step["env"]["BLOGGER_PUBLISH"], ctx), "BLOGGER_AUTH_CHECK": render(run_step["env"]["BLOGGER_AUTH_CHECK"], ctx)}


def end_to_end_env(wrapper, event, event_inputs=None):
    """이벤트·수동 입력 → 래퍼 → 공용 워크플로 → 러너가 받는 환경변수(문자열)."""
    return callee_env(wrapper_with(wrapper, event, event_inputs))


def old_env(event, event_inputs=None):
    """분리 전 blogger.yml 이 같은 이벤트·입력에서 만든 환경변수 값(OLD_ENV 의 식을 같은 해석기로 평가)."""
    ctx = event_context(event, event_inputs)
    return {name: render(template, ctx) for name, template in OLD_ENV.items()}


def dispatch_combinations():
    """수동 실행 입력 조합 전부: 연습·publish 3택·인증 점검·주제를 각각 '값 없음'까지 포함해 센다(GitHub 는 생략된 입력에 기본값을 채우지만 API 호출 등 값이 비는 경우도 센다)."""
    for dry_run in ("true", "false", None):
        for publish in ("off", "draft", "publish", None):
            for auth_check in ("true", "false", None):
                for topic in ("", "직접 정한 주제", None):
                    yield {name: value for name, value in (("dry_run", dry_run), ("publish", publish), ("auth_check", auth_check), ("topic", topic))
                           if value is not None}
