"""Gemini 호출: 모델 폴백 + 일시 오류 재시도 + 시크릿 마스킹 + 요청별 호출 기록.

반환값은 (text, model). 호출 호출 가능 객체(callable) 형태라 테스트에서 가짜로 바꿔 끼울 수 있다.
기존 엔진(generator.py)과 같은 호출 방식(genai.Client(...).models.generate_content)을 쓴다.

호출 기록(CallLog): 무료 한도는 프로젝트 단위라 Chance·Blogger·이슈 수정·수동 실행이 한 통을 나눠 쓴다. 실제 소비는 AI Studio 화면에서만
보이므로, 요청 한 번마다 요청 모델·응답 모델(modelVersion)·결과 종류(성공/429/5xx/빈 응답/기타)·소요 시간·토큰 사용량을 메모리에 쌓고
로그 한 줄(`[GEMINI] ...`)로 남긴다. 실행 요약은 이 기록을 접어 쓴다. 장부 파일·커밋은 만들지 않는다(후속 작업).
기록은 호출의 동작(재시도·폴백·반환값·예외)을 바꾸지 않는다 — 측정 전용이다.
"""
import contextlib
import enum
import re
import time
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from pipeline.console import md_cell, one_line
from pipeline.secret_patterns import SECRET_PATTERNS


class LLMError(RuntimeError):
    """모든 모델/재시도가 실패했을 때."""


_SECRET_RX = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|ya29\.[0-9A-Za-z_\-]{20,}|1//[0-9A-Za-z_\-]{20,}|"
                        r"(?i:key|token|secret)=[^\s&'\"]+)")


def mask(text):
    """로그·이력에 쓰기 전에 비밀로 보이는 값을 가린다. 저장소 공용 패턴(secret_patterns)을 함께 쓴다(D-31)."""
    out = _SECRET_RX.sub("***", str(text))
    for _label, rx in SECRET_PATTERNS:
        out = rx.sub("***", out)
    return out


def _is_transient(exc):
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in (429, 500, 502, 503, 504):
        return True
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "503", "unavailable", "resource_exhausted", "overloaded",
                                  "timeout", "timed out", "temporarily"))


# ----------------------------------------------------------------------------
# 호출 기록 (측정 전용: 호출·재시도·폴백·반환값·예외는 바꾸지 않는다)
# ----------------------------------------------------------------------------
OUTCOME_OK = "ok"                # 성공
OUTCOME_RATE_LIMIT = "429"       # 한도 초과(일 한도인지 분 한도인지는 본문을 모은 뒤 별도 작업에서 가른다)
OUTCOME_SERVER_ERROR = "5xx"     # 서버 오류·과부하
OUTCOME_EMPTY = "empty"          # 응답은 왔지만 텍스트가 비어 있음(안전 차단·토큰 소진 등)
OUTCOME_OTHER = "other"          # 그 밖의 실패(인증·모델 없음·네트워크·타임아웃 …)
# 실패 한 건을 로그에 남기는 최대 길이. 예전에는 200~300자로 잘려 429 본문의 한도 구분 필드와 재시도 대기 시간(retryDelay)이 사라졌다.
FAILURE_DETAIL_LIMIT = 600
# 구글 API 오류 본문(QuotaFailure·RetryInfo)에서 일/분 한도 구분과 재시도 대기 시간이 담기는 필드 이름(중요한 순서). 실제 모양은 관측해서
# 확정하므로 찾지 못해도 본문 일부는 그대로 남는다.
_HINT_KEYS = ("quotaId", "retryDelay", "quotaMetric")
_HINT_PER_KEY = 2
_LEADING_CODE_RX = re.compile(r"^\s*(\d{3})\b")


def _safe_str(value):
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - __str__ 이 깨진 예외여도 기록 때문에 호출 결과가 바뀌면 안 된다
        return type(value).__name__


def _field(obj, name):
    """객체(또는 딕셔너리)의 선택 필드. 없거나 읽을 수 없으면 None — 기록은 부가 기능이라 읽기 실패가 호출 결과를 바꾸지 않는다."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    try:
        return getattr(obj, name, None)
    except (LookupError, TypeError, ValueError):  # 속성을 읽다가 예외를 내는 이상한 객체(AttributeError 는 getattr 이 처리한다)
        return None


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def failure_code(exc):
    """실패 예외의 HTTP 상태 코드(정수). google-genai 의 APIError 는 code, 다른 클라이언트는 status_code, 둘 다 없으면 메시지 맨 앞의 세 자리 숫자."""
    for name in ("code", "status_code"):
        value = _count(_field(exc, name))
        if value is not None:
            return value
    match = _LEADING_CODE_RX.match(_safe_str(exc))
    return int(match.group(1)) if match else None


def failure_status(exc):
    """google-genai 오류의 상태 문자열(예: RESOURCE_EXHAUSTED). 없으면 빈 문자열."""
    value = _field(exc, "status")
    return value.strip() if isinstance(value, str) else ""


def classify_failure(exc):
    """실패를 429 / 5xx / 그 밖으로 가른다. 429 안에서 일 한도와 분 한도를 가르는 규칙은 실제 본문을 관측한 뒤 별도 작업이다."""
    code, status = failure_code(exc), failure_status(exc).upper()
    if code == 429 or status == "RESOURCE_EXHAUSTED":
        return OUTCOME_RATE_LIMIT
    if (code is not None and 500 <= code <= 599) or status in ("UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED"):
        return OUTCOME_SERVER_ERROR
    return OUTCOME_OTHER


def _collect_hints(node, found, depth=0):
    """오류 본문(details)을 훑어 _HINT_KEYS 이름의 값을 found(딕셔너리: 이름 → 값 목록)에 모은다(이름마다 중복 제외 최대 _HINT_PER_KEY개)."""
    if depth > 8:
        return
    if isinstance(node, dict):
        children = list(node.items())
    elif isinstance(node, (list, tuple)):
        children = [(None, item) for item in node]
    else:
        return
    for key, value in children:
        if key in _HINT_KEYS and isinstance(value, (str, int, float)) and not isinstance(value, bool):
            values = found.setdefault(key, [])
            shown = one_line(value, 80)
            if shown not in values and len(values) < _HINT_PER_KEY:
                values.append(shown)
        else:
            _collect_hints(value, found, depth + 1)


def _head_tail(text, limit):
    """limit 를 넘으면 앞부분과 뒷부분을 남기고 가운데를 줄인다. 오류 본문에서 코드·메시지는 앞에, 한도 구분·재시도 정보는 뒤에 있는 경우가 많다."""
    if len(text) <= limit:
        return text
    tail = limit // 3
    return text[:limit - tail - 3].rstrip() + " … " + text[-tail:].lstrip()


def failure_detail(exc, limit=FAILURE_DETAIL_LIMIT):
    """실패 한 건의 로그용 설명: `예외이름 code=429 status=RESOURCE_EXHAUSTED quotaId=… retryDelay=… | 본문`.
    비밀은 가리고(mask) 한 줄로 접으며(one_line, `::`·`##[` 무력화) limit 자 안으로 줄인다. 코드·상태·한도 구분 필드는 맨 앞에 두어 잘리지 않는다."""
    head = [type(exc).__name__]
    code, status = failure_code(exc), failure_status(exc)
    if code is not None:
        head.append(f"code={code}")
    if status:
        head.append(f"status={status}")
    found = {}
    _collect_hints(_field(exc, "details"), found)
    hints = [f"{key}={value}" for key in _HINT_KEYS for value in found.get(key, [])]
    prefix = one_line(mask(" ".join(head + hints)), limit * 3 // 5)
    body = one_line(mask(_safe_str(exc)), 100000)   # 여기서는 접기만 한다(길이는 아래에서 앞·뒤를 남기며 줄인다)
    return f"{prefix} | {_head_tail(body, limit - len(prefix) - 3)}"


def _enum_text(value):
    if isinstance(value, str):      # google-genai 의 열거형은 str 을 상속해 값 문자열이 그대로 나온다
        return value.strip()
    if isinstance(value, enum.Enum):
        return str(value.name)
    return ""


def empty_detail(response):
    """빈 응답의 사유로 짐작할 수 있는 값(첫 후보의 finish_reason, 프롬프트 차단 사유). 없으면 '빈 응답'만."""
    candidates = _field(response, "candidates")
    first = candidates[0] if isinstance(candidates, (list, tuple)) and candidates else None
    parts = ["빈 응답"]
    for label, value in (("finish_reason", _field(first, "finish_reason")),
                         ("block_reason", _field(_field(response, "prompt_feedback"), "block_reason"))):
        text = _enum_text(value)
        if text:
            parts.append(f"{label}={text}")
    return one_line(" ".join(parts), 120)


def served_model(response):
    """응답이 알려 주는 실제 모델(modelVersion). 요청한 이름이 다른 모델로 연결됐는지(폐기된 모델 별칭) 볼 때 쓴다. 없으면 빈 문자열."""
    for name in ("model_version", "modelVersion"):
        value = _field(response, name)
        if isinstance(value, str) and value.strip():
            return one_line(value, 80)
    return ""


def token_usage(response):
    """(입력, 출력, 합계) 토큰 수. 응답에 없는 칸은 None."""
    usage = _field(response, "usage_metadata")
    if usage is None:
        usage = _field(response, "usageMetadata")
    found = []
    for snake, camel in (("prompt_token_count", "promptTokenCount"), ("candidates_token_count", "candidatesTokenCount"),
                         ("total_token_count", "totalTokenCount")):
        value = _count(_field(usage, snake))
        found.append(value if value is not None else _count(_field(usage, camel)))
    return tuple(found)


@dataclass(frozen=True)
class CallRecord:
    """요청 한 번의 기록."""
    label: str                     # 호출한 쪽(블로그 키 · chance · issue-edit …)
    purpose: str                   # 용도(generate · topic-expansion · patch · image-queries · post …), 없으면 빈 문자열
    model: str                     # 요청한 모델
    served_model: str              # 응답의 modelVersion(없으면 빈 문자열)
    outcome: str                   # OUTCOME_*
    seconds: float
    prompt_tokens: Optional[int] = None
    candidate_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    detail: str = ""               # 실패일 때만(failure_detail / empty_detail)


def _token(value, limit=60):
    """로그 한 줄의 key=value 칸에 넣을 공백 없는 값(외부·설정 유래 문자열이라 한 줄로 접는다)."""
    return re.sub(r"\s+", "_", one_line(value, limit)) or "-"


def call_line(rec):
    """로그 한 줄(Actions 로그에서 `[GEMINI]`로 찾는다). detail 은 길어서 맨 끝에 둔다."""
    tokens = "-"
    if any(v is not None for v in (rec.prompt_tokens, rec.candidate_tokens, rec.total_tokens)):
        tokens = ",".join(f"{name}:{'-' if value is None else value}" for name, value in
                          (("in", rec.prompt_tokens), ("out", rec.candidate_tokens), ("total", rec.total_tokens)))
    parts = ["[GEMINI]", f"label={_token(rec.label)}", f"purpose={_token(rec.purpose)}", f"model={_token(rec.model)}",
             f"result={rec.outcome}", f"sec={rec.seconds:.1f}", f"served={_token(rec.served_model)}", f"tokens={tokens}"]
    if rec.detail:
        parts.append("detail=" + rec.detail)
    return " ".join(parts)


class CallLog:
    """한 실행의 Gemini 요청 기록(메모리). 로그 한 줄씩 남기고 실행 요약에서 접어 쓴다. 장부 파일은 만들지 않는다."""

    def __init__(self, label="", out=None, purpose=""):
        self.label, self.out, self.purpose = label, out, purpose
        self.records = []

    def configure(self, label=None, out=None, purpose=None):
        """호출 객체를 만든 뒤 어느 블로그·용도의 기록인지와 로그를 어디로 보낼지(out)를 정한다."""
        if label is not None:
            self.label = label
        if out is not None:
            self.out = out
        if purpose is not None:
            self.purpose = purpose

    @contextlib.contextmanager
    def purposed(self, name):
        """with log.purposed("topic-expansion"): … 안에서 기록하는 요청에 용도 라벨을 붙인다."""
        previous, self.purpose = self.purpose, name
        try:
            yield
        finally:
            self.purpose = previous

    @property
    def attempts(self):
        return len(self.records)

    @property
    def failed(self):
        return sum(1 for r in self.records if r.outcome != OUTCOME_OK)

    def add(self, model, outcome, seconds, response=None, exc=None):
        tokens = token_usage(response)
        detail = failure_detail(exc) if exc is not None else (empty_detail(response) if outcome == OUTCOME_EMPTY else "")
        rec = CallRecord(label=self.label, purpose=self.purpose, model=_safe_str(model), served_model=served_model(response),
                         outcome=outcome, seconds=max(float(seconds), 0.0), prompt_tokens=tokens[0],
                         candidate_tokens=tokens[1], total_tokens=tokens[2], detail=detail)
        self.records.append(rec)
        if self.out is not None:
            self.out(call_line(rec))
        return rec

    def success(self, model, seconds, response=None):
        return self.add(model, OUTCOME_OK, seconds, response=response)

    def empty(self, model, seconds, response=None):
        return self.add(model, OUTCOME_EMPTY, seconds, response=response)

    def failure(self, model, seconds, exc):
        return self.add(model, classify_failure(exc), seconds, exc=exc)

    def detail_lines(self):
        """실행 요약에 접어 쓰는 보충 줄(호출이 없으면 빈 목록): 실패 종류별 횟수 · 요청→응답 모델 · 토큰 합계 · 용도별 횟수."""
        lines = []
        failures = Counter(r.outcome for r in self.records if r.outcome != OUTCOME_OK)
        if failures:
            names = ((OUTCOME_RATE_LIMIT, "429(한도 초과)"), (OUTCOME_SERVER_ERROR, "5xx(서버 오류)"),
                     (OUTCOME_EMPTY, "빈 응답"), (OUTCOME_OTHER, "기타"))
            lines.append("Gemini 실패 내역: " + " · ".join(f"{name} {failures[key]}회" for key, name in names if failures[key]))
        served = Counter((r.model, r.served_model) for r in self.records if r.served_model)
        if served:
            lines.append("Gemini 응답 모델(요청→응답): " + ", ".join(
                f"{md_cell(asked, 40)}→{md_cell(got, 40)} {n}회" for (asked, got), n in sorted(served.items())[:4]))
        usage = [(r.prompt_tokens, r.candidate_tokens, r.total_tokens) for r in self.records]
        if any(v is not None for row in usage for v in row):
            sent, received, total = (sum(v for v in column if v is not None) for column in zip(*usage))
            lines.append(f"Gemini 토큰(응답에 값이 있는 호출만): 입력 {sent:,} · 출력 {received:,} · 합계 {total:,}")
        purposes = Counter(r.purpose for r in self.records if r.purpose)
        if len(purposes) > 1:
            lines.append("Gemini 용도별 호출: " + " · ".join(f"{md_cell(name, 40)} {n}회" for name, n in sorted(purposes.items())))
        return lines

    def summary_lines(self):
        """실행 요약용 줄 목록. 첫 줄은 Chance 요약과 같은 `Gemini 호출: N회(실패 K회)`다."""
        return [f"Gemini 호출: {self.attempts}회(실패 {self.failed}회)"] + self.detail_lines()


def call_log_of(llm):
    """호출 객체가 가진 기록 장치(CallLog). 가짜·스텁 호출 객체에는 없다(None)."""
    log = getattr(llm, "call_log", None)
    return log if isinstance(log, CallLog) else None


def purpose(llm, name):
    """with purpose(llm, "topic-expansion"): … 안에서 부른 요청에 용도 라벨을 붙인다. 기록 장치가 없는 호출 객체에는 아무 일도 하지 않는다."""
    log = call_log_of(llm)
    return log.purposed(name) if log is not None else contextlib.nullcontext()


def make_gemini_llm(api_key, models, max_retries=2, sleep=time.sleep, client_factory=None, clock=time.monotonic, log=None):
    """(prompt) -> (text, model) 을 돌려주는 호출 객체를 만든다. 요청별 기록은 호출 객체의 call_log(CallLog)에 쌓인다."""
    holder = {}
    log = CallLog() if log is None else log

    def client():
        if "c" not in holder:
            if client_factory:
                holder["c"] = client_factory()
            else:
                from google import genai
                holder["c"] = genai.Client(api_key=api_key)
        return holder["c"]

    def call(prompt):
        errors = []
        for model in models:
            for attempt in range(max_retries + 1):
                started = clock()
                response, failure, text = None, None, ""
                try:
                    response = client().models.generate_content(model=model, contents=prompt)
                    text = (getattr(response, "text", None) or "").strip()
                except Exception as exc:  # noqa: BLE001 - 라이브러리별 예외를 한곳에서 분류한다
                    failure = exc
                elapsed = clock() - started   # 기록은 try 밖에서 한다: 기록 때문에 호출 실패로 오인되거나 재시도되는 일이 없게
                if failure is None:
                    if text:
                        log.success(model, elapsed, response)
                        return text, model
                    log.empty(model, elapsed, response)
                    errors.append(f"{model}: 빈 응답")
                    break
                log.failure(model, elapsed, failure)
                errors.append(f"{model}: {type(failure).__name__}: {mask(failure)[:200]}")
                if attempt < max_retries and _is_transient(failure):
                    sleep(2 ** attempt * 2)
                    continue
                break
        raise LLMError("모든 모델 호출 실패 | " + " | ".join(errors))

    call.call_log = log
    return call
