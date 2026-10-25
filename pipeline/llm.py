"""Gemini 호출: 모델 폴백 + 일시 오류 재시도 + 시크릿 마스킹.

반환값은 (text, model). 호출 호출 가능 객체(callable) 형태라 테스트에서 가짜로 바꿔 끼울 수 있다.
기존 엔진(generator.py)과 같은 호출 방식(genai.Client(...).models.generate_content)을 쓴다.
"""
import re
import time

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


def make_gemini_llm(api_key, models, max_retries=2, sleep=time.sleep, client_factory=None):
    """(prompt) -> (text, model) 을 돌려주는 호출 객체를 만든다."""
    holder = {}

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
                try:
                    response = client().models.generate_content(model=model, contents=prompt)
                    text = (getattr(response, "text", None) or "").strip()
                    if text:
                        return text, model
                    errors.append(f"{model}: 빈 응답")
                    break
                except Exception as exc:  # noqa: BLE001 - 라이브러리별 예외를 한곳에서 분류한다
                    errors.append(f"{model}: {type(exc).__name__}: {mask(exc)[:200]}")
                    if attempt < max_retries and _is_transient(exc):
                        sleep(2 ** attempt * 2)
                        continue
                    break
        raise LLMError("모든 모델 호출 실패 | " + " | ".join(errors))

    return call
