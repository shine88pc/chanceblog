"""Gemini 호출 기록(pipeline/llm.py CallLog)·Blogger·이슈 수정·Chance 실행 요약의 호출 수 줄 테스트. 네트워크 없이 돈다.

배경(무료 한도 진단 2026-10-25): 한도는 프로젝트 단위이고 숫자는 AI Studio 화면에서만 보인다. 우리는 같은 키를 Chance·Blogger·이슈 수정·
수동 실행이 나눠 쓰는데, 호출 수를 세는 곳은 Chance 요약뿐이었고(예외로 끝나면 그마저 사라짐) 실패 사유는 200~300자로 잘려 429 본문의
한도 구분 필드와 재시도 대기 시간이 사라졌다. 이 테스트는 (1) 기록이 동작을 바꾸지 않는다는 것(옛 구현과 나란히 실행해 비교)과
(2) 요청마다 모델·결과·토큰·소요가 남고 실패 사유가 600자까지 마스킹·한 줄로 남는다는 것, (3) 어느 종료 경로에서도 호출 수가 요약에
남는다는 것을 고정한다. 실제 비밀처럼 보이는 문자열은 런타임에 조합한다(검증기 SEC-2 회피용 allow 표시에 기대지 않는다).
"""
import contextlib
import enum
import inspect
import io
import itertools
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import types
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest import mock

import _bootstrap
import generator as g
from edits_helpers import image_body, issue, make_edit_root, page_body
from pipeline import llm as llm_mod
from pipeline import run as run_mod
from pipeline.edits import runner, safety
from pipeline.llm import (CallLog, CallRecord, LLMError, call_line, classify_failure, empty_detail, failure_code,
                          failure_detail, make_gemini_llm, purpose, scrub, served_model, token_usage)
from pipeline.stubs import stub_llm
from test_run import RunBase

REAL = _bootstrap.ROOT

FAKE_KEY = "AIza" + "x" * 35               # 구글 API 키 형식(런타임 조합)
FAKE_TOKEN = "ya29." + "y" * 40            # 구글 액세스 토큰 형식(런타임 조합)
FAKE_NEW_KEY = "AQ" + "." + "z" * 45       # 새 형식 키(런타임 조합)
# 줄 구분 문자(U+2028·U+2029)는 소스에 직접 쓰지 않고 chr() 로 만든다(편집 도구가 이스케이프를 실제 문자로 바꿔 쓰는 일이 있다)
LS = chr(0x2028)
PS = chr(0x2029)

WHITESPACE = "  " + chr(10) + " "   # 공백과 줄바꿈뿐인 응답 텍스트

# 운영 모델 사슬의 길이와 모델당 시도 횟수(max_retries 2 → 최대 3번). 목록이 바뀌어도(2026-10-26 gemini-3.7-flash 제거) 호출 수 시험이 따라가게 한다.
MODEL_COUNT = len(g.MODEL_CANDIDATES)
TRIES_PER_MODEL = 3
ALL_TRIES = MODEL_COUNT * TRIES_PER_MODEL

DAY_QUOTA_ID = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
MINUTE_QUOTA_ID = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"


def quota_body(quota_id=DAY_QUOTA_ID, retry="37s", message=None, status="RESOURCE_EXHAUSTED", code=429):
    """구글 API 429 본문의 모양(QuotaFailure·RetryInfo)을 흉내 낸 가짜. 실제 모양은 관측해서 확정한다."""
    message = message if message is not None else (
        "You exceeded your current quota, please check your plan and billing details. For more information on this error, "
        "head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: "
        "https://ai.dev/usage?tab=rate-limit.\n* Quota exceeded for metric: generativelanguage.googleapis.com/"
        "generate_content_free_tier_requests, limit: 20, model: gemini-3.8-flash\nPlease retry in 37.5s.")
    return {"error": {"code": code, "message": message, "status": status, "details": [
        {"@type": "type.googleapis.com/google.rpc.Help",
         "links": [{"description": "Learn more about Gemini API quotas", "url": "https://ai.google.dev/gemini-api/docs/rate-limits"}]},
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                         "quotaId": quota_id,
                         "quotaDimensions": {"location": "global", "model": "gemini-3.8-flash"}, "quotaValue": "20"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry},
    ]}}


class ApiError(Exception):
    """google-genai 의 APIError 와 같은 필드(code·status·message·details)를 가진 가짜. 문자열은 '코드 상태. 본문'이다."""

    def __init__(self, code, body=None):
        body = body if body is not None else {"error": {"code": code, "message": f"오류 {code}", "status": "ERR", "details": []}}
        self.code = code
        self.status = body["error"].get("status")
        self.message = body["error"].get("message")
        self.details = body
        super().__init__(f"{code} {self.status}. {body}")


class FinishReason(str, enum.Enum):
    """google-genai 의 열거형처럼 str 을 상속한 열거형."""
    STOP = "STOP"
    SAFETY = "SAFETY"


class Plain(enum.Enum):
    BLOCKED = 1


class Usage:
    def __init__(self, prompt=None, candidates=None, total=None):
        self.prompt_token_count, self.candidates_token_count, self.total_token_count = prompt, candidates, total


class Candidate:
    def __init__(self, finish_reason=None):
        self.finish_reason = finish_reason


class Feedback:
    def __init__(self, block_reason=None):
        self.block_reason = block_reason


class Resp:
    """generate_content 응답의 가짜(.text · .model_version · .usage_metadata · .candidates · .prompt_feedback)."""

    def __init__(self, text="응답", model_version=None, usage=None, candidates=None, prompt_feedback=None):
        self.text, self.model_version, self.usage_metadata = text, model_version, usage
        self.candidates, self.prompt_feedback = candidates, prompt_feedback


class Models:
    """script 의 항목을 차례로 쓴다: 예외면 던지고, 함수면 (model, contents)로 불러 결과를 쓰고, 아니면 그대로 돌려준다."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def generate_content(self, model, contents):
        self.calls.append((model, contents))
        step = self.script.pop(0)
        if inspect.isfunction(step):          # Mock 은 callable 이지만 '응답'이다
            step = step(model, contents)
        if isinstance(step, BaseException):
            raise step
        return step


class Client:
    def __init__(self, script):
        self.models = Models(script)


class Clock:
    """부를 때마다 step 초 흐르는 가짜 시계(호출 한 번의 소요는 항상 step)."""

    def __init__(self, step=0.5):
        self.now, self.step = 0.0, step

    def __call__(self):
        self.now += self.step
        return self.now


def build(script, models=("a", "b"), max_retries=2, step=0.5, out=None, label=""):
    client, sleeps = Client(script), []
    call = make_gemini_llm("키", list(models), max_retries, sleep=sleeps.append, client_factory=lambda: client, clock=Clock(step))
    call.call_log.configure(label=label or None, out=out)
    return call, client, sleeps


def capture(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        value = fn(*args, **kwargs)
    return value, buf.getvalue()


def gemini_lines(text):
    return [line for line in text.splitlines() if line.startswith("[GEMINI]")]


TAG = "[issue-edit] issue=#12 author=@shine88pc(OWNER)"        # 이슈 수정 러너의 모든 로그 줄 머리(하드닝 #19 규칙)


def runner_gemini_lines(text):
    """이슈 수정 러너는 요청 줄에도 머리를 달고 300자로 자른다: `머리   * [GEMINI] …` 의 `[GEMINI] …` 부분만 돌려준다."""
    marker = TAG + "   * "
    return [line[len(marker):] for line in text.splitlines() if line.startswith(marker + "[GEMINI]")]


# ----------------------------------------------------------------------------
# 1) 실패 분류와 실패 사유(마스킹·한 줄·600자)
# ----------------------------------------------------------------------------
class ClassifyFailureTest(unittest.TestCase):
    def test_429_by_code_status_text_or_status_code(self):
        self.assertEqual(classify_failure(ApiError(429, quota_body())), "429")
        only_status = ApiError(500, quota_body())
        only_status.code = None
        only_status.status = "RESOURCE_EXHAUSTED"
        self.assertEqual(classify_failure(only_status), "429")
        self.assertEqual(classify_failure(RuntimeError("429 RESOURCE_EXHAUSTED. quota")), "429")
        err = RuntimeError("x")
        err.status_code = 429
        self.assertEqual(classify_failure(err), "429")

    def test_5xx_by_code_status_or_text(self):
        for code in (500, 502, 503, 504, 599):
            self.assertEqual(classify_failure(ApiError(code)), "5xx", code)
        err = RuntimeError("x")
        err.status = "UNAVAILABLE"
        self.assertEqual(classify_failure(err), "5xx")
        for status in ("INTERNAL", "DEADLINE_EXCEEDED"):
            err.status = status.lower()                  # 대소문자는 가리지 않는다
            self.assertEqual(classify_failure(err), "5xx", status)
        self.assertEqual(classify_failure(RuntimeError("503 Service Unavailable")), "5xx")

    def test_everything_else_is_other(self):
        for code in (400, 401, 403, 404, 499, 600):
            self.assertEqual(classify_failure(ApiError(code)), "other", code)
        for exc in (RuntimeError("timed out"), ValueError("x"), RuntimeError("")):
            self.assertEqual(classify_failure(exc), "other", repr(exc))

    def test_only_structured_fields_or_a_leading_code_count(self):
        """메시지 중간의 숫자(요청 번호 등)는 상태 코드로 보지 않는다. 재시도 판단(_is_transient)은 그 옛 동작 그대로다."""
        self.assertEqual(classify_failure(RuntimeError("request 4291 failed with 429 somewhere")), "other")
        self.assertEqual(failure_code(RuntimeError("  503 later")), 503)
        self.assertIsNone(failure_code(RuntimeError("abc 503")))

    def test_code_wins_over_status_code_and_status_code_is_only_the_fallback(self):
        """google-genai 의 APIError 는 code, 다른 클라이언트는 status_code 를 쓴다. 둘이 다르면 code 가 이긴다(독립 검증 M004)."""
        both = RuntimeError("x")
        both.code, both.status_code = 429, 500
        self.assertEqual((failure_code(both), classify_failure(both)), (429, "429"))
        both.code, both.status_code = 500, 429
        self.assertEqual((failure_code(both), classify_failure(both)), (500, "5xx"))
        only_rest = RuntimeError("x")
        only_rest.status_code = 503
        self.assertEqual(failure_code(only_rest), 503)
        invalid_code = RuntimeError("x")
        invalid_code.code, invalid_code.status_code = "abc", 429          # code 가 정수가 아니면 status_code 를 본다
        self.assertEqual(failure_code(invalid_code), 429)

    def test_bool_negative_and_mock_codes_are_not_status_codes(self):
        for bad in (True, False, -429, "429", 4.29, mock.Mock()):
            err = RuntimeError("no leading code")
            err.code = bad
            self.assertIsNone(failure_code(err), repr(bad))
            self.assertEqual(classify_failure(err), "other", repr(bad))

    def test_exception_with_a_broken_str_is_still_classified(self):
        class Broken(Exception):
            def __str__(self):
                raise RuntimeError("str 이 깨졌다")
        self.assertEqual(classify_failure(Broken()), "other")
        self.assertIn("Broken", failure_detail(Broken()))


class FailureDetailTest(unittest.TestCase):
    def test_code_status_and_quota_hints_come_first_for_a_real_shaped_429(self):
        detail = failure_detail(ApiError(429, quota_body()))
        head = detail.split(" | ", 1)[0]
        self.assertTrue(head.startswith("ApiError code=429 status=RESOURCE_EXHAUSTED "), head)
        self.assertIn(f"quotaId={DAY_QUOTA_ID}", head)         # 일 한도인지 분 한도인지 가르는 필드
        self.assertIn("retryDelay=37s", head)
        self.assertIn("quotaMetric=generativelanguage.googleapis.com/generate_content_free_tier_requests", head)
        self.assertLessEqual(len(detail), 600)

    def test_minute_and_day_quotas_are_distinguishable_in_the_log(self):
        day = failure_detail(ApiError(429, quota_body(DAY_QUOTA_ID)))
        minute = failure_detail(ApiError(429, quota_body(MINUTE_QUOTA_ID, retry="9s")))
        self.assertIn("PerDay", day)
        self.assertNotIn("PerMinute", day.split(" | ", 1)[0])
        self.assertIn("PerMinute", minute.split(" | ", 1)[0])
        self.assertIn("retryDelay=9s", minute)

    def test_hints_survive_even_when_the_message_is_huge(self):
        """예전 구현은 앞 200자만 남겨 quotaId·retryDelay 가 사라졌다. 본문이 수천 자여도 앞쪽 요약에는 남는다."""
        detail = failure_detail(ApiError(429, quota_body(message="한도 초과 " * 2000)))
        self.assertLessEqual(len(detail), 600)
        head = detail.split(" | ", 1)[0]
        self.assertIn(DAY_QUOTA_ID, head)
        self.assertIn("retryDelay=37s", head)

    def test_old_cut_would_have_lost_the_fields_the_new_one_keeps(self):
        err = ApiError(429, quota_body())
        self.assertNotIn("retryDelay", llm_mod.mask(err)[:200])      # 옛 로그(앞 200자)에는 없었다
        self.assertIn("retryDelay", failure_detail(err))

    def test_length_limit_default_and_custom_and_both_ends_are_kept(self):
        long_text = "첫머리표식 " + "가" * 3000 + " 꼬리표식"
        err = RuntimeError(long_text)
        detail = failure_detail(err)
        self.assertLessEqual(len(detail), llm_mod.FAILURE_DETAIL_LIMIT)
        self.assertEqual(llm_mod.FAILURE_DETAIL_LIMIT, 600)
        self.assertIn("첫머리표식", detail)
        self.assertTrue(detail.endswith("꼬리표식"))
        self.assertIn(" … ", detail)
        small = failure_detail(err, limit=200)
        self.assertLessEqual(len(small), 200)
        self.assertTrue(small.endswith("꼬리표식"))

    def test_the_cut_keeps_two_thirds_in_front_and_one_third_behind(self):
        self.assertEqual(llm_mod._head_tail("H" * 50 + "T" * 50, 30), "H" * 17 + " … " + "T" * 10)
        self.assertEqual(llm_mod._head_tail("가" * 10, 30), "가" * 10)                 # 길이 안이면 그대로
        self.assertEqual(len(llm_mod._head_tail("x" * 1000, 600)), 600)

    def test_short_text_is_not_cut(self):
        self.assertEqual(failure_detail(RuntimeError("짧은 오류")), "RuntimeError | 짧은 오류")
        self.assertNotIn("…", failure_detail(RuntimeError("짧은 오류")))

    def test_a_text_exactly_at_the_limit_is_kept_whole_and_one_more_is_cut(self):
        """경계값(독립 검증 M026): 길이가 정확히 limit 이면 자르지 않는다."""
        self.assertEqual(llm_mod._head_tail("x" * 30, 30), "x" * 30)
        cut = llm_mod._head_tail("x" * 31, 30)
        self.assertEqual(len(cut), 30)
        self.assertIn(" … ", cut)
        body = "나" * 100
        prefix = "RuntimeError"
        exact = failure_detail(RuntimeError(body), limit=len(prefix) + 3 + len(body))        # 본문이 남은 칸에 딱 맞는다
        self.assertEqual(exact, f"{prefix} | {body}")
        self.assertNotIn("…", exact)
        self.assertIn("…", failure_detail(RuntimeError(body), limit=len(prefix) + 3 + len(body) - 1))

    def test_secrets_are_masked_everywhere_including_the_hints_and_the_tail(self):
        for secret in (FAKE_KEY, FAKE_TOKEN, FAKE_NEW_KEY):
            body = quota_body(message=f"앞 {secret} 중간 " + "나" * 900 + f" 뒤 key={secret}")
            body["error"]["details"][2]["retryDelay"] = f"37s {secret}"
            detail = failure_detail(ApiError(429, body))
            self.assertNotIn(secret, detail)
            self.assertNotIn(secret[:20], detail)
            self.assertIn("***", detail)

    def test_secret_in_the_exception_type_text_is_masked_too(self):
        class Weird(Exception):
            pass
        detail = failure_detail(Weird(f"api_key={FAKE_KEY}"))
        self.assertNotIn(FAKE_KEY, detail)

    def test_one_line_and_no_workflow_commands(self):
        hostile = f"줄1\n줄2\r줄3{LS}줄4\u0085줄5\t탭\x1b[31m ::error::위조 ##[group]가짜"
        detail = failure_detail(ApiError(500, quota_body(message=hostile)))
        for ch in ("\n", "\r", LS, PS, "\u0085", "\t", "\x1b"):
            self.assertNotIn(ch, detail)
        self.assertNotIn("::", detail)
        self.assertNotIn("##[", detail)
        self.assertEqual(detail, " ".join(detail.split()))

    def test_odd_details_values_do_not_break_it(self):
        for details in (None, "문자열", 7, [], [1, 2, "x"], {"a": {"b": [{"quotaId": None}]}}, {"quotaId": True}):
            err = RuntimeError("본문")
            err.details = details
            detail = failure_detail(err)
            self.assertIn("본문", detail)
            self.assertNotIn("quotaId=", detail)

    def test_hint_values_are_deduplicated_capped_and_ordered_by_importance(self):
        """한 키마다 5개까지(실제 429 는 위반이 3개까지 나와 2개로는 일 한도 id 가 잘렸다). 순서: 일 한도 id(…PerDay…) → 재시도 대기 →
        나머지 id → 지표. 같은 값은 한 번만."""
        violations = [{"quotaId": f"Q{i}", "quotaMetric": f"M{i}"} for i in range(8)]
        violations[5]["quotaId"] = "Q5PerDay"
        body = {"error": {"status": "RESOURCE_EXHAUSTED", "details": [
            {"violations": violations}, {"retryDelay": "5s"}, {"retryDelay": "5s"}, {"retryDelay": 7}]}}
        err = ApiError(429, body)
        head = failure_detail(err).split(" | ", 1)[0]
        self.assertIn("quotaId=Q5PerDay retryDelay=5s retryDelay=7 quotaId=Q0 quotaId=Q1 quotaId=Q2 quotaId=Q3 "
                      "quotaMetric=M0 quotaMetric=M1 quotaMetric=M2 quotaMetric=M3 quotaMetric=M4", head)
        for left_out in ("Q4", "Q6", "Q7", "M5", "M6", "M7"):
            self.assertNotIn(left_out, head)
        self.assertEqual(head.count("retryDelay=5s"), 1)

    def test_a_very_long_hint_value_is_shortened(self):
        err = ApiError(429, {"error": {"status": "X", "details": [{"quotaId": "Q" * 500}]}})
        head = failure_detail(err).split(" | ", 1)[0]
        self.assertLess(len(head), 200)

    def test_a_long_summary_part_is_cut_at_three_fifths_and_the_whole_still_fits(self):
        violations = [{"quotaId": f"Q{i}-" + "q" * 100, "quotaMetric": f"M{i}-" + "m" * 100} for i in range(3)]
        body = {"error": {"status": "RESOURCE_EXHAUSTED", "message": "가" * 2000,
                          "details": [{"violations": violations}, {"retryDelay": "1" * 100}]}}
        err = ApiError(429, body)
        detail = failure_detail(err)
        head, rest = detail.split(" | ", 1)
        self.assertLessEqual(len(head), 600 * 3 // 5)              # 앞쪽 요약은 360자까지
        self.assertLessEqual(len(detail), 600)
        self.assertTrue(head.endswith("…"))                         # 잘렸다는 표시
        self.assertTrue(detail.endswith(llm_mod.one_line(str(err), 100000)[-20:]))   # 본문 꼬리는 남는다
        small = failure_detail(err, limit=100)
        self.assertLessEqual(len(small), 100)


# ----------------------------------------------------------------------------
# 2) 응답에서 읽는 값(응답 모델·토큰·빈 응답 사유)
# ----------------------------------------------------------------------------
class ResponseFieldsTest(unittest.TestCase):
    def test_served_model_reads_the_sdk_field_the_rest_name_and_dicts(self):
        self.assertEqual(served_model(Resp(model_version="gemini-3.8-flash")), "gemini-3.8-flash")
        camel = mock.Mock(spec=["modelVersion"])
        camel.modelVersion = "gemini-3.6-flash"
        self.assertEqual(served_model(camel), "gemini-3.6-flash")
        self.assertEqual(served_model({"modelVersion": "gemini-3.5-flash-lite"}), "gemini-3.5-flash-lite")
        self.assertEqual(served_model(Resp(model_version="  ")), "")
        self.assertEqual(served_model({"model_version": "  ", "modelVersion": "gemini-3.5-flash-lite"}), "gemini-3.5-flash-lite")
        self.assertEqual(served_model(Resp()), "")
        self.assertEqual(served_model(None), "")

    def test_served_model_prefers_the_sdk_name_when_both_names_exist(self):
        """독립 검증 M038: 두 이름이 다 있으면 SDK 이름(model_version)이 이긴다. 앞의 값이 비면 다음 이름을 본다."""
        self.assertEqual(served_model({"model_version": "sdk-name", "modelVersion": "rest-name"}), "sdk-name")
        both = mock.Mock(spec=["model_version", "modelVersion"])
        both.model_version, both.modelVersion = "sdk-name", "rest-name"
        self.assertEqual(served_model(both), "sdk-name")
        self.assertEqual(served_model({"model_version": "", "modelVersion": "rest-name"}), "rest-name")
        self.assertEqual(served_model({"model_version": None, "modelVersion": "rest-name"}), "rest-name")

    def test_served_model_ignores_non_strings_and_folds_hostile_text(self):
        self.assertEqual(served_model(mock.Mock(text="응답")), "")          # Mock 의 자동 속성은 값이 아니다
        self.assertEqual(served_model(Resp(model_version=123)), "")
        shown = served_model(Resp(model_version="m\n::error::x" + "y" * 200))
        self.assertNotIn("\n", shown)
        self.assertNotIn("::", shown)
        self.assertLessEqual(len(shown), 80)

    def test_token_usage_from_sdk_objects_rest_names_and_partial_values(self):
        self.assertEqual(token_usage(Resp(usage=Usage(10, 20, 30))), (10, 20, 30))
        self.assertEqual(token_usage(Resp(usage=Usage(total=5))), (None, None, 5))
        self.assertEqual(token_usage({"usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 2, "totalTokenCount": 3}}),
                         (1, 2, 3))
        self.assertEqual(token_usage(Resp(usage=Usage(0, 0, 0))), (0, 0, 0))          # 0 은 값이 있는 것이다
        self.assertEqual(token_usage(Resp()), (None, None, None))
        self.assertEqual(token_usage(None), (None, None, None))

    def test_token_usage_ignores_bad_values(self):
        self.assertEqual(token_usage(Resp(usage=Usage(True, -1, "3"))), (None, None, None))
        self.assertEqual(token_usage(mock.Mock(text="응답")), (None, None, None))
        self.assertEqual(token_usage(Resp(usage=mock.Mock())), (None, None, None))

    def test_objects_that_raise_while_being_read_are_treated_as_missing(self):
        class Exploding:
            @property
            def model_version(self):
                raise ValueError("boom")

            @property
            def usage_metadata(self):
                raise KeyError("boom")
        self.assertEqual(served_model(Exploding()), "")
        self.assertEqual(token_usage(Exploding()), (None, None, None))

    def test_empty_detail_names_the_reason_when_the_response_has_one(self):
        self.assertEqual(empty_detail(Resp(text="")), "빈 응답")
        self.assertEqual(empty_detail(Resp(text="", candidates=[Candidate(FinishReason.SAFETY)])), "빈 응답 finish_reason=SAFETY")
        self.assertEqual(empty_detail(Resp(text="", candidates=[Candidate("MAX_TOKENS")])), "빈 응답 finish_reason=MAX_TOKENS")
        self.assertEqual(empty_detail(Resp(text="", prompt_feedback=Feedback(Plain.BLOCKED))), "빈 응답 block_reason=BLOCKED")
        both = Resp(text="", candidates=[Candidate(FinishReason.STOP)], prompt_feedback=Feedback("OTHER"))
        self.assertEqual(empty_detail(both), "빈 응답 finish_reason=STOP block_reason=OTHER")
        self.assertEqual(empty_detail(Resp(text="", candidates=[])), "빈 응답")
        self.assertEqual(empty_detail(Resp(text="", candidates=[Candidate(7)])), "빈 응답")
        self.assertEqual(empty_detail(mock.Mock(text="")), "빈 응답")
        self.assertEqual(empty_detail(None), "빈 응답")

    def test_empty_detail_reads_the_first_candidate_only(self):
        """독립 검증 M035: 후보가 둘 이상이어도 사유는 첫 후보의 것이다(둘째·마지막 후보의 값을 읽지 않는다)."""
        two = Resp(text="", candidates=[Candidate(FinishReason.SAFETY), Candidate(FinishReason.STOP)])
        self.assertEqual(empty_detail(two), "빈 응답 finish_reason=SAFETY")
        three = Resp(text="", candidates=[Candidate(None), Candidate(FinishReason.SAFETY), Candidate(FinishReason.STOP)])
        self.assertEqual(empty_detail(three), "빈 응답")                 # 첫 후보에 사유가 없으면 뒤 후보를 뒤지지 않는다
        as_tuple = Resp(text="", candidates=(Candidate("MAX_TOKENS"), Candidate("STOP")))
        self.assertEqual(empty_detail(as_tuple), "빈 응답 finish_reason=MAX_TOKENS")


# ----------------------------------------------------------------------------
# 3) CallLog: 기록·로그 한 줄·요약 줄
# ----------------------------------------------------------------------------
class CallLogTest(unittest.TestCase):
    def test_a_success_record_keeps_model_served_model_tokens_and_time(self):
        log = CallLog(label="blogger_macat", purpose="generate")
        rec = log.success("gemini-3.7-flash", 3.26, Resp(model_version="gemini-3.8-flash", usage=Usage(1234, 567, 1801)))
        self.assertEqual((rec.label, rec.purpose, rec.model, rec.served_model, rec.outcome),
                         ("blogger_macat", "generate", "gemini-3.7-flash", "gemini-3.8-flash", "ok"))
        self.assertEqual((rec.prompt_tokens, rec.candidate_tokens, rec.total_tokens), (1234, 567, 1801))
        self.assertEqual((rec.seconds, rec.detail), (3.26, ""))
        self.assertEqual((log.attempts, log.failed), (1, 0))
        self.assertIs(log.records[0], rec)

    def test_log_line_format_success_and_failure(self):
        log = CallLog(label="blogger_macat", purpose="generate")
        ok = log.success("gemini-3.8-flash", 3.26, Resp(model_version="gemini-3.8-flash", usage=Usage(100, 50, 150)))
        self.assertEqual(call_line(ok), "[GEMINI] label=blogger_macat purpose=generate model=gemini-3.8-flash result=ok sec=3.3 "
                                        "served=gemini-3.8-flash tokens=in:100,out:50,total:150")
        bad = log.failure("gemini-3.8-flash", 0.8, ApiError(429, quota_body()))
        line = call_line(bad)
        self.assertTrue(line.startswith("[GEMINI] label=blogger_macat purpose=generate model=gemini-3.8-flash result=429 sec=0.8 "
                                        "served=- tokens=- detail=ApiError code=429 status=RESOURCE_EXHAUSTED "), line)
        self.assertNotIn("\n", line)

    def test_missing_values_are_dashes_and_partial_tokens_show_dashes(self):
        log = CallLog()
        rec = log.success("m", 0.0, Resp(usage=Usage(total=9)))
        self.assertEqual(call_line(rec), "[GEMINI] label=- purpose=- model=m result=ok sec=0.0 served=- tokens=in:-,out:-,total:9")

    def test_fields_with_spaces_or_hostile_text_stay_one_token_each(self):
        log = CallLog(label="블로그 키\n::error::x", purpose="용도 a b")
        rec = log.failure("모델 이름", 1.0, RuntimeError("실패"))
        line = call_line(rec)
        self.assertTrue(line.startswith("[GEMINI] label=블로그_키_:_:error:_:x purpose=용도_a_b model=모델_이름 result=other "), line)
        self.assertNotIn("\n", line)

    def test_out_gets_exactly_one_line_per_record(self):
        lines = []
        log = CallLog(label="x", out=lines.append)
        log.success("a", 1, Resp())
        log.failure("b", 1, RuntimeError("e"))
        log.empty("c", 1, Resp(text=""))
        self.assertEqual(len(lines), 3)
        self.assertEqual([line.split()[3] for line in lines], ["model=a", "model=b", "model=c"])
        self.assertEqual([line.split()[4] for line in lines], ["result=ok", "result=other", "result=empty"])
        self.assertIn("detail=빈 응답", lines[2])

    def test_no_out_means_no_output_but_records_are_kept(self):
        log = CallLog()
        _, printed = capture(log.success, "a", 1, Resp())
        self.assertEqual(printed, "")
        self.assertEqual(log.attempts, 1)

    def test_configure_sets_only_what_is_given(self):
        lines = []
        log = CallLog(label="old", purpose="p")
        log.configure(out=lines.append)
        self.assertEqual((log.label, log.purpose), ("old", "p"))
        log.configure(label="new", purpose="q")
        self.assertEqual((log.label, log.purpose), ("new", "q"))
        log.success("a", 1, Resp())
        self.assertEqual(len(lines), 1)
        log.configure(label="")                       # 빈 문자열도 '준 값'이다
        self.assertEqual(log.label, "")

    def test_purposed_restores_the_previous_purpose_even_on_error_and_nests(self):
        log = CallLog(purpose="generate")
        with log.purposed("topic-expansion"):
            self.assertEqual(log.purpose, "topic-expansion")
            with log.purposed("inner"):
                self.assertEqual(log.purpose, "inner")
            self.assertEqual(log.purpose, "topic-expansion")
        self.assertEqual(log.purpose, "generate")
        with self.assertRaises(ValueError):
            with log.purposed("x"):
                raise ValueError("fail")
        self.assertEqual(log.purpose, "generate")
        log.success("a", 1, Resp())
        with log.purposed("expand"):
            log.success("a", 1, Resp())
        self.assertEqual([r.purpose for r in log.records], ["generate", "expand"])

    def test_negative_seconds_and_odd_models_do_not_break_the_record(self):
        log = CallLog()
        self.assertEqual(log.success("a", -3, Resp()).seconds, 0.0)
        self.assertEqual(log.success(None, 1, Resp()).model, "None")
        self.assertEqual(log.success(12, 1, Resp()).model, "12")

    def test_failed_counts_every_non_ok_outcome(self):
        log = CallLog()
        log.success("a", 1, Resp())
        log.failure("a", 1, ApiError(429, quota_body()))
        log.failure("a", 1, ApiError(503))
        log.failure("a", 1, ApiError(404))
        log.empty("a", 1, Resp(text=""))
        self.assertEqual((log.attempts, log.failed), (5, 4))
        self.assertEqual([r.outcome for r in log.records], ["ok", "429", "5xx", "other", "empty"])

    def test_summary_first_line_matches_the_chance_format_and_zero_calls_has_no_details(self):
        log = CallLog()
        self.assertEqual(log.summary_lines(), ["Gemini 호출: 0회(실패 0회)"])
        log.success("a", 1, Resp())
        log.failure("a", 1, ApiError(429, quota_body()))
        self.assertEqual(log.summary_lines()[0], "Gemini 호출: 2회(실패 1회)")

    def test_failure_tally_names_every_kind_that_happened_in_a_fixed_order(self):
        log = CallLog()
        for exc in (ApiError(404), ApiError(503), ApiError(429, quota_body()), ApiError(429, quota_body())):
            log.failure("m", 1, exc)
        log.empty("m", 1, Resp(text=""))
        self.assertIn("Gemini 실패 내역: 429(한도 초과) 2회 · 5xx(서버 오류) 1회 · 빈 응답 1회 · 기타 1회", log.detail_lines())
        only = CallLog()
        only.failure("m", 1, ApiError(503))
        self.assertEqual(only.detail_lines(), ["Gemini 실패 내역: 5xx(서버 오류) 1회"])

    def test_all_successful_run_has_no_failure_line(self):
        log = CallLog()
        log.success("m", 1, Resp())
        self.assertFalse(any("실패 내역" in line for line in log.detail_lines()))

    def test_served_models_line_shows_which_request_was_answered_by_which_model(self):
        log = CallLog()
        log.success("gemini-3.7-flash", 1, Resp(model_version="gemini-3.8-flash"))
        log.success("gemini-3.8-flash", 1, Resp(model_version="gemini-3.8-flash"))
        log.success("gemini-3.8-flash", 1, Resp(model_version="gemini-3.8-flash"))
        log.success("gemini-3.6-flash", 1, Resp())          # 응답 모델이 없는 호출은 이 줄에 넣지 않는다
        self.assertIn("Gemini 응답 모델(요청→응답): gemini-3.7-flash→gemini-3.8-flash 1회, "
                      "gemini-3.8-flash→gemini-3.8-flash 2회", log.detail_lines())

    def test_served_models_line_is_capped_at_four_pairs_and_markdown_safe(self):
        log = CallLog()
        for i in range(6):
            log.success(f"m{i}", 1, Resp(model_version=f"v{i}"))
        line = next(row for row in log.detail_lines() if row.startswith("Gemini 응답 모델"))
        self.assertEqual(line.split("): ", 1)[1].count("→"), 4)       # 머리말의 화살표를 빼고 쌍은 네 개까지
        hostile = CallLog()
        hostile.success("a|b", 1, Resp(model_version="x|<b>[y](http://e.example)"))
        shown = next(row for row in hostile.detail_lines() if row.startswith("Gemini 응답 모델"))
        for ch in "|<>[]":
            self.assertNotIn(ch, shown.split(":", 1)[1])

    def test_token_line_sums_only_values_that_exist(self):
        log = CallLog()
        log.success("m", 1, Resp(usage=Usage(1000, 200, 1200)))
        log.success("m", 1, Resp(usage=Usage(None, 34, 34)))
        log.success("m", 1, Resp())
        self.assertIn("Gemini 토큰(응답에 값이 있는 호출만): 입력 1,000 · 출력 234 · 합계 1,234", log.detail_lines())
        none = CallLog()
        none.success("m", 1, Resp())
        self.assertFalse(any("토큰" in line for line in none.detail_lines()))

    def test_purpose_line_only_appears_when_more_than_one_purpose_was_used(self):
        log = CallLog(purpose="generate")
        log.success("m", 1, Resp())
        log.success("m", 1, Resp())
        self.assertFalse(any("용도별" in line for line in log.detail_lines()))
        with log.purposed("topic-expansion"):
            log.success("m", 1, Resp())
        self.assertIn("Gemini 용도별 호출: generate 2회 · topic-expansion 1회", log.detail_lines())
        blank = CallLog()
        blank.success("m", 1, Resp())
        with blank.purposed("x"):
            blank.success("m", 1, Resp())
        self.assertFalse(any("용도별" in line for line in blank.detail_lines()))    # 용도 없는 기록은 세지 않는다

    def test_call_log_of_and_purpose_ignore_objects_without_a_real_log(self):
        for fake in (stub_llm, lambda prompt: ("t", "m"), mock.Mock(), object()):
            self.assertIsNone(llm_mod.call_log_of(fake))
            with purpose(fake, "x"):                       # 아무 일도 하지 않고 지나간다
                pass
        call, _, _ = build([Resp()])
        self.assertIs(llm_mod.call_log_of(call), call.call_log)
        with purpose(call, "patch"):
            self.assertEqual(call.call_log.purpose, "patch")
        self.assertEqual(call.call_log.purpose, "")


# ----------------------------------------------------------------------------
# 4) make_gemini_llm: 기록이 붙었지만 동작은 그대로
# ----------------------------------------------------------------------------
def legacy_make_gemini_llm(api_key, models, max_retries=2, sleep=time.sleep, client_factory=None):
    """기록을 붙이기 전(main 0f509d2 이후 c00eb4f)의 구현을 그대로 옮긴 기준. 새 구현과 나란히 실행해 동작이 같은지 비교한다."""
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
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{model}: {type(exc).__name__}: {llm_mod.mask(exc)[:200]}")
                    if attempt < max_retries and llm_mod._is_transient(exc):
                        sleep(2 ** attempt * 2)
                        continue
                    break
        raise LLMError("모든 모델 호출 실패 | " + " | ".join(errors))

    return call


class MakeGeminiLlmTest(unittest.TestCase):
    def test_success_on_the_first_try_returns_text_and_model_and_records_one_request(self):
        lines = []
        call, client, sleeps = build([Resp("  본문  ", "gemini-3.8-flash", Usage(10, 20, 30))], models=("a", "b"),
                                     out=lines.append, label="blogger_macat")
        self.assertEqual(call("프롬프트"), ("본문", "a"))
        self.assertEqual(client.models.calls, [("a", "프롬프트")])
        self.assertEqual(sleeps, [])
        rec = call.call_log.records[0]
        self.assertEqual((rec.model, rec.served_model, rec.outcome, rec.seconds), ("a", "gemini-3.8-flash", "ok", 0.5))
        self.assertEqual((rec.prompt_tokens, rec.candidate_tokens, rec.total_tokens), (10, 20, 30))
        self.assertEqual(lines, ["[GEMINI] label=blogger_macat purpose=- model=a result=ok sec=0.5 served=gemini-3.8-flash "
                                 "tokens=in:10,out:20,total:30"])

    def test_a_429_is_retried_on_the_same_model_and_both_requests_are_recorded(self):
        call, client, sleeps = build([ApiError(429, quota_body()), Resp("본문")], models=("a",))
        self.assertEqual(call("p"), ("본문", "a"))
        self.assertEqual(sleeps, [2])                              # 동작 불변: 같은 모델을 2초 뒤 다시 부른다
        self.assertEqual([m for m, _ in client.models.calls], ["a", "a"])
        self.assertEqual([r.outcome for r in call.call_log.records], ["429", "ok"])
        self.assertEqual(call.call_log.summary_lines()[:2], ["Gemini 호출: 2회(실패 1회)", "Gemini 실패 내역: 429(한도 초과) 1회"])

    def test_every_model_failing_with_429_makes_twelve_recorded_requests_and_the_same_error_text(self):
        models = ("m1", "m2", "m3", "m4")
        call, client, sleeps = build([ApiError(429, quota_body())] * 12, models=models)
        with self.assertRaises(LLMError) as ctx:
            call("p")
        self.assertEqual(len(client.models.calls), 12)
        self.assertEqual(sleeps, [2, 4] * 4)
        self.assertEqual((call.call_log.attempts, call.call_log.failed), (12, 12))
        self.assertEqual(call.call_log.summary_lines()[1], "Gemini 실패 내역: 429(한도 초과) 12회")
        legacy_message = ctx.exception.args[0]
        self.assertTrue(legacy_message.startswith("모든 모델 호출 실패 | m1: ApiError: 429 RESOURCE_EXHAUSTED."))
        for rec in call.call_log.records:
            self.assertIn(DAY_QUOTA_ID, rec.detail)                # 본문은 요청마다 로그에 남는다

    def test_a_400_is_not_retried_and_is_recorded_as_other(self):
        call, client, sleeps = build([ApiError(400), ApiError(404)], models=("a", "b"))
        with self.assertRaises(LLMError):
            call("p")
        self.assertEqual(sleeps, [])
        self.assertEqual([r.outcome for r in call.call_log.records], ["other", "other"])
        self.assertEqual([m for m, _ in client.models.calls], ["a", "b"])

    def test_a_5xx_is_retried_and_recorded_as_5xx(self):
        call, _, sleeps = build([ApiError(503), ApiError(503), Resp("본문")], models=("a",))
        self.assertEqual(call("p"), ("본문", "a"))
        self.assertEqual(sleeps, [2, 4])
        self.assertEqual([r.outcome for r in call.call_log.records], ["5xx", "5xx", "ok"])

    def test_every_request_of_a_run_is_timed_on_its_own(self):
        """독립 검증 N007: 요청마다 자기 시작·끝 시각으로 소요를 잰다 — 재시도·폴백의 둘째 요청부터도 첫 요청의 시작에 이어 붙지 않는다."""
        call, _, _ = build([ApiError(503), ApiError(503), Resp("본문")], models=("a",), step=0.25)
        call("p")
        self.assertEqual([r.seconds for r in call.call_log.records], [0.25, 0.25, 0.25])
        call, _, _ = build([ApiError(400), Resp(""), Resp("본문")], models=("a", "b", "c"), step=0.25)
        call("p")
        self.assertEqual([r.seconds for r in call.call_log.records], [0.25, 0.25, 0.25])
        self.assertEqual([r.outcome for r in call.call_log.records], ["other", "empty", "ok"])

    def test_an_empty_answer_moves_to_the_next_model_without_retrying(self):
        empty = Resp("", candidates=[Candidate(FinishReason.SAFETY)])
        call, client, sleeps = build([empty, Resp("본문")], models=("a", "b"))
        self.assertEqual(call("p"), ("본문", "b"))
        self.assertEqual(sleeps, [])
        self.assertEqual([m for m, _ in client.models.calls], ["a", "b"])
        self.assertEqual([r.outcome for r in call.call_log.records], ["empty", "ok"])
        self.assertEqual(call.call_log.records[0].detail, "빈 응답 finish_reason=SAFETY")

    def test_a_response_without_usage_or_model_version_is_recorded_with_dashes(self):
        call, _, _ = build([mock.Mock(text="응답")], models=("a",))
        self.assertEqual(call("p"), ("응답", "a"))
        rec = call.call_log.records[0]
        self.assertEqual((rec.served_model, rec.prompt_tokens, rec.candidate_tokens, rec.total_tokens), ("", None, None, None))

    def test_call_log_attribute_is_the_log_and_an_outside_log_can_be_supplied(self):
        mine = CallLog(label="issue-edit")
        client = Client([Resp("본문")])
        call = make_gemini_llm("키", ["a"], sleep=lambda s: None, client_factory=lambda: client, log=mine)
        self.assertIs(call.call_log, mine)
        call("p")
        self.assertEqual(mine.attempts, 1)
        self.assertIsInstance(make_gemini_llm("키", ["a"], client_factory=lambda: client).call_log, CallLog)

    def test_the_client_is_created_once_and_a_factory_failure_is_recorded_as_a_failed_request(self):
        made = []

        def factory():
            made.append(1)
            return Client([Resp("1"), Resp("2")])
        call = make_gemini_llm("키", ["a"], client_factory=factory, sleep=lambda s: None, clock=Clock())
        call("p")
        call("p")
        self.assertEqual(len(made), 1)

        def broken():
            raise ImportError("google-genai 가 없다")
        failing = make_gemini_llm("키", ["a"], max_retries=0, client_factory=broken, sleep=lambda s: None, clock=Clock())
        with self.assertRaises(LLMError):
            failing("p")
        self.assertEqual(failing.call_log.records[0].outcome, "other")

    def test_recording_never_changes_what_the_call_does_old_and_new_run_side_by_side(self):
        """무작위 시나리오 300개를 옛 구현과 새 구현에 똑같이 먹여 반환값·예외 문구·모델 호출 순서·대기 시간이 같은지 본다."""
        pool = [lambda: Resp("본문"), lambda: Resp(""), lambda: Resp(WHITESPACE), lambda: Resp(None), lambda: mock.Mock(text="응답"),
                lambda: ApiError(429, quota_body()), lambda: ApiError(503), lambda: ApiError(404), lambda: ApiError(500),
                lambda: RuntimeError("503"), lambda: RuntimeError("boom"), lambda: ValueError("timeout happened"),
                lambda: RuntimeError(f"api_key={FAKE_KEY}"), lambda: RuntimeError("")]
        for seed in range(300):
            rng = random.Random(seed)
            models = rng.sample(["a", "b", "c", "d"], rng.randint(1, 4))
            retries = rng.choice([0, 1, 2])
            steps = [pool[rng.randrange(len(pool))]() for _ in range(16)]
            outcomes = []
            for factory in (legacy_make_gemini_llm, make_gemini_llm):
                client, sleeps = Client(list(steps)), []
                kwargs = {"clock": Clock()} if factory is make_gemini_llm else {}
                call = factory("키", models, retries, sleep=sleeps.append, client_factory=lambda c=client: c, **kwargs)
                try:
                    result = ("ok",) + call("프롬프트")
                except LLMError as exc:
                    result = ("llm-error", str(exc))
                outcomes.append((result, client.models.calls, sleeps))
            self.assertEqual(outcomes[0], outcomes[1], f"seed {seed}")

    def test_failure_text_in_the_error_message_is_still_cut_at_200_and_masked(self):
        """LLMError 문구(이력 파일에 일부가 들어가는 쪽)는 예전 그대로다: 모델마다 200자·마스킹. 길게 남기는 것은 로그 줄뿐이다."""
        call, _, _ = build([RuntimeError("가" * 1000 + FAKE_KEY)], models=("a",), max_retries=0)
        with self.assertRaises(LLMError) as ctx:
            call("p")
        message = ctx.exception.args[0]
        self.assertLess(len(message), 260)
        self.assertNotIn(FAKE_KEY, message)
        self.assertGreater(len(call.call_log.records[0].detail), 300)


# ----------------------------------------------------------------------------
# 5) Blogger 실행(pipeline/run.py): 모든 종료 경로의 요약에 호출 수가 남는다
# ----------------------------------------------------------------------------
class BloggerRunSummaryTest(RunBase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.summary_path = Path(tmp.name) / "summary.md"
        self.NO_PUBLISH = {"BLOGGER_PUBLISH": "0"}

    def env(self, **extra):
        return {"GITHUB_STEP_SUMMARY": str(self.summary_path), "GEMINI_API_KEY": "fake-llm-key", **self.NO_PUBLISH, **extra}

    def summary(self):
        return self.summary_path.read_text(encoding="utf-8") if self.summary_path.exists() else ""

    def real_llm(self, script, step=0.5, max_retries=2):
        """러너가 만드는 실제 호출 객체(make_gemini_llm)에 가짜 클라이언트만 끼운다. 대기는 건너뛴다."""
        client = Client(script)

        def factory(api_key, models, retries=2):
            return make_gemini_llm(api_key, models, retries, sleep=lambda s: None, client_factory=lambda: client, clock=Clock(step))
        self.client = client
        return mock.patch.object(run_mod, "make_gemini_llm", factory)

    def stub_answer(self, usage=Usage(100, 200, 300)):
        return lambda model, contents: Resp(stub_llm(contents)[0], model_version=model, usage=usage)

    def use_all_seeds(self):
        seeds = json.loads((REAL / "pipeline" / "profiles" / "blogger_practical_ko.json").read_text(
            encoding="utf-8"))["seed_topics"]
        (self.root / "blogger_history.json").write_text(
            json.dumps([{"topic": t, "date": "2026-10-20", "status": "posted"} for t in seeds], ensure_ascii=False),
            encoding="utf-8")

    def test_a_successful_run_reports_its_calls_in_the_summary_and_the_log(self):
        with self.real_llm([self.stub_answer()]):
            code, out = self.go(env=self.env(), llm=None)
        self.assertEqual(code, 0, out)
        text = self.summary()
        self.assertIn("- 결과: **draft**", text)
        self.assertIn("- Gemini 호출: 1회(실패 0회)", text)
        self.assertIn("- Gemini 응답 모델(요청→응답): gemini-3.8-flash→gemini-3.8-flash 1회", text)
        self.assertIn("- Gemini 토큰(응답에 값이 있는 호출만): 입력 100 · 출력 200 · 합계 300", text)
        lines = gemini_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("[GEMINI] label=blogger_macat purpose=generate model=gemini-3.8-flash result=ok "), lines[0])
        self.assertEqual(len(self.client.models.calls), 1)

    def test_all_models_failing_with_429_still_leaves_the_call_count_in_the_summary(self):
        """이전: LLM_FAILED 요약에는 호출 수가 없었다(Chance 는 예외 시 호출 수가 사라지던 것과 같은 계열). 이제 12회·429 12회가 남는다."""
        with self.real_llm([ApiError(429, quota_body())] * ALL_TRIES):
            code, out = self.go(env=self.env(), llm=None)
        self.assertEqual(code, 1)
        self.assertIn("[SKIP] code=LLM_FAILED", out)
        text = self.summary()
        self.assertIn("**LLM_FAILED**", text)
        self.assertIn(f"- Gemini 호출: {ALL_TRIES}회(실패 {ALL_TRIES}회)", text)
        self.assertIn(f"- Gemini 실패 내역: 429(한도 초과) {ALL_TRIES}회", text)
        self.assertEqual(len(gemini_lines(out)), ALL_TRIES)
        self.assertTrue(all(f"quotaId={DAY_QUOTA_ID}" in line for line in gemini_lines(out)))
        self.assertEqual(self.history()[-1]["status"], "llm_failed")

    def test_topic_expansion_requests_are_labelled_and_a_failure_keeps_the_count(self):
        self.use_all_seeds()
        with self.real_llm([ApiError(503)] * ALL_TRIES):
            code, out = self.go(env=self.env(), llm=None)
        self.assertEqual(code, 1)
        self.assertIn("[SKIP] code=EXPAND_FAILED", out)
        lines = gemini_lines(out)
        self.assertEqual(len(lines), ALL_TRIES)
        self.assertTrue(all("purpose=topic-expansion" in line and "result=5xx" in line for line in lines))
        self.assertIn(f"- Gemini 호출: {ALL_TRIES}회(실패 {ALL_TRIES}회)", self.summary())
        self.assertIn(f"- Gemini 실패 내역: 5xx(서버 오류) {ALL_TRIES}회", self.summary())

    def test_expansion_then_generation_shows_both_purposes(self):
        self.use_all_seeds()
        with self.real_llm([self.stub_answer(), self.stub_answer()]):
            code, out = self.go(env=self.env(), llm=None)
        purposes = [line.split()[2] for line in gemini_lines(out)]
        self.assertEqual(purposes[0], "purpose=topic-expansion")
        self.assertEqual(purposes[1:], ["purpose=generate"] * (len(purposes) - 1))
        self.assertIn("- Gemini 용도별 호출: generate", self.summary())
        self.assertIn("topic-expansion 1회", self.summary())

    def test_no_topic_after_an_unusable_expansion_still_keeps_the_count(self):
        self.use_all_seeds()
        with self.real_llm([Resp("[]")]):
            code, out = self.go(env=self.env(), llm=None)
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=NO_TOPIC", out)
        self.assertIn("**NO_TOPIC**", self.summary())
        self.assertIn("- Gemini 호출: 1회(실패 0회)", self.summary())
        self.assertEqual([line.split()[2] for line in gemini_lines(out)], ["purpose=topic-expansion"])

    def test_gate_rejection_keeps_the_count_of_every_rewrite_attempt(self):
        short = lambda model, contents: Resp("제목: 충분히 긴 제목입니다 정말로\n라벨: 가\n내용:\n<p>너무 짧음</p>", model)
        with self.real_llm([short, short, short]):
            code, out = self.go(env=self.env(), llm=None)
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=GATE_REJECTED", out)
        self.assertIn("- Gemini 호출: 3회(실패 0회)", self.summary())

    def test_a_fallback_run_shows_failures_and_which_model_answered(self):
        with self.real_llm([ApiError(429, quota_body()), ApiError(429, quota_body()), ApiError(429, quota_body()),
                            self.stub_answer()]):
            code, out = self.go(env=self.env(), llm=None)
        self.assertEqual(code, 0)
        text = self.summary()
        self.assertIn("- Gemini 호출: 4회(실패 3회)", text)
        self.assertIn("- Gemini 실패 내역: 429(한도 초과) 3회", text)
        second = g.MODEL_CANDIDATES[1]  # 첫 모델이 429 로 세 번 실패한 뒤 답하는 둘째 모델
        self.assertIn(f"{second}→{second} 1회", text)
        self.assertEqual(self.history()[-1]["model"], second)

    def test_a_dry_run_says_the_ai_answers_were_fake_and_no_gemini_was_called(self):
        code, out = self.go(env=self.env(), llm=None, extra=["--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("**DRY_RUN**", self.summary())
        self.assertIn("- Gemini 호출: 0회(가짜 AI 응답 사용)", self.summary())
        self.assertEqual(gemini_lines(out), [])

    def test_paths_that_end_before_the_llm_exists_have_no_gemini_lines(self):
        code, _ = self.go(env=self.env(PIPELINE_PAUSE="true"), llm=None)
        self.assertEqual(code, 0)
        self.assertIn("PAUSED", self.summary())
        self.assertNotIn("Gemini", self.summary())

    def test_missing_llm_key_has_no_gemini_lines_either(self):
        env = self.env()
        del env["GEMINI_API_KEY"]
        code, _ = self.go(env=env, llm=None)
        self.assertEqual(code, 2)
        self.assertIn("SECRETS_MISSING", self.summary())
        self.assertNotIn("Gemini 호출", self.summary())

    def test_injected_fake_llms_leave_the_old_summary_untouched(self):
        """주입된 가짜 llm 에는 기록 장치가 없어 요약 줄이 늘지 않는다(기존 요약 줄 수 시험이 그대로 통과하는 이유)."""
        code, _ = self.go(env=self.env(), llm=stub_llm)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.summary().splitlines()), 3)
        self.assertNotIn("Gemini", self.summary())

    def test_secrets_in_failures_never_reach_the_log_the_summary_or_the_history(self):
        body = quota_body(message=f"키 {FAKE_KEY} 와 토큰 {FAKE_TOKEN} 가 오류에 섞임")
        with self.real_llm([ApiError(429, body)] * 12):
            code, out = self.go(env=self.env(), llm=None)
        everything = out + self.summary() + json.dumps(self.history(), ensure_ascii=False)
        for secret in (FAKE_KEY, FAKE_TOKEN, FAKE_KEY[:20], FAKE_TOKEN[:20]):
            self.assertNotIn(secret, everything)
        self.assertIn("***", out)

    def test_every_log_line_is_a_single_line_and_never_a_workflow_command(self):
        hostile = f"줄1\n::error::위조\r::warning::위조{LS}##[group]위조"
        with self.real_llm([ApiError(500, quota_body(message=hostile))] * 12):
            code, out = self.go(env=self.env(), llm=None)
        self.assertEqual([line for line in out.splitlines() if line.lstrip().startswith(("::", "##["))],
                         ["::error::[blogger_macat] LLM 호출이 실패했습니다. LLM 키·할당량·모델 이름을 확인하세요."])
        for char in ("\r", LS):
            self.assertNotIn(char, out)


# ----------------------------------------------------------------------------
# 6) Chance(generator.py): 예외로 끝나도 호출 수가 남고, 요청별 기록과 Unsplash 남은 호출이 요약에 들어간다
# ----------------------------------------------------------------------------
def legacy_call_gemini_with_fallback(prompt, get_client, models, calls, one_line):
    """기록을 붙이기 전 generator.call_gemini_with_fallback 을 그대로 옮긴 기준(전역 대신 인자로 받는다)."""
    errors = []
    for model_name in models:
        try:
            print(f"Gemini 모델 호출 시도: {model_name}")
            calls["attempts"] += 1
            response = get_client().models.generate_content(model=model_name, contents=prompt)
            text = getattr(response, "text", None)
            if text and text.strip():
                print(f"Gemini 모델 호출 성공: {model_name}")
                return response
            calls["failed"] += 1
            errors.append(f"{model_name}: 응답 텍스트 없음")
        except Exception as exc:
            calls["failed"] += 1
            errors.append(f"{model_name}: {exc}")
            print(f"Gemini 모델 호출 실패: {model_name} - {one_line(exc)}")
    raise RuntimeError("모든 Gemini 모델 호출 실패\n" + "\n".join(errors))


class ChanceBase(unittest.TestCase):
    LOG_OUT = None      # 요청 줄을 화면에 내보내는 시험만 print 로 바꾼다(capture 가 받아 간다)

    def setUp(self):
        self.log = CallLog(label="chance", purpose="post", out=self.LOG_OUT)
        for patcher in (mock.patch.object(g, "CALL_LOG", self.log),
                        mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0}),
                        mock.patch.dict(g.UNSPLASH_RATE, {"remaining": None, "limit": None})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_client(self, script):
        client = Client(script)
        patcher = mock.patch.object(g, "get_client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client


class ChanceCallRecordTest(ChanceBase):
    LOG_OUT = print

    def test_each_request_is_logged_and_the_count_dict_is_unchanged(self):
        self.fake_client([ApiError(429, quota_body()), Resp("본문", "gemini-3.7-flash", Usage(1, 2, 3))])
        with mock.patch.object(g, "MODEL_CANDIDATES", ["gemini-3.8-flash", "gemini-3.7-flash"]):
            response, out = capture(g.call_gemini_with_fallback, "프롬프트")
        self.assertEqual(response.text, "본문")
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 2, "failed": 1})
        lines = gemini_lines(out)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("[GEMINI] label=chance purpose=post model=gemini-3.8-flash result=429 "), lines[0])
        self.assertIn(f"quotaId={DAY_QUOTA_ID}", lines[0])
        self.assertIn("result=ok", lines[1])
        self.assertIn("served=gemini-3.7-flash tokens=in:1,out:2,total:3", lines[1])
        self.assertEqual([r.outcome for r in self.log.records], ["429", "ok"])

    def test_each_request_line_carries_its_own_duration(self):
        """독립 검증 N027·N028: 성공·빈 응답·실패 어느 경우든 `sec=` 는 그 요청의 소요이고 요청마다 따로 잰다."""
        clock = Clock(0.25)
        self.fake_client([ApiError(503), Resp(""), Resp("본문")])
        with mock.patch.object(g, "time", types.SimpleNamespace(monotonic=clock)), \
                mock.patch.object(g, "MODEL_CANDIDATES", ["a", "b", "c"]):
            _, out = capture(g.call_gemini_with_fallback, "프롬프트")
        self.assertEqual([r.seconds for r in self.log.records], [0.25, 0.25, 0.25])
        self.assertEqual([r.outcome for r in self.log.records], ["5xx", "empty", "ok"])
        self.assertEqual([line.split()[5] for line in gemini_lines(out)], ["sec=0.2", "sec=0.2", "sec=0.2"])   # 0.25 → 한 자리 반올림(짝수로)
        clock = Clock(1.5)
        self.fake_client([ApiError(503), Resp("본문")])
        with mock.patch.object(g, "time", types.SimpleNamespace(monotonic=clock)), \
                mock.patch.object(g, "MODEL_CANDIDATES", ["a", "b"]):
            _, out = capture(g.call_gemini_with_fallback, "프롬프트")
        self.assertEqual([line.split()[5] for line in gemini_lines(out)], ["sec=1.5", "sec=1.5"])

    def test_all_models_failing_raises_the_same_error_and_records_every_request(self):
        self.fake_client([ApiError(429, quota_body())] * MODEL_COUNT)
        with self.assertRaises(RuntimeError) as ctx:
            capture(g.call_gemini_with_fallback, "프롬프트")
        self.assertTrue(ctx.exception.args[0].startswith("모든 Gemini 모델 호출 실패\ngemini-3.8-flash: 429 RESOURCE_EXHAUSTED."))
        self.assertEqual(g.GEMINI_CALLS, {"attempts": MODEL_COUNT, "failed": MODEL_COUNT})
        self.assertEqual(self.log.attempts, MODEL_COUNT)
        self.assertEqual([r.model for r in self.log.records], list(g.MODEL_CANDIDATES))

    def test_an_empty_answer_is_counted_as_failed_and_recorded_as_empty(self):
        self.fake_client([Resp(""), Resp("본문")])
        response, out = capture(g.call_gemini_with_fallback, "프롬프트")
        self.assertEqual(response.text, "본문")
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 2, "failed": 1})
        self.assertEqual([r.outcome for r in self.log.records], ["empty", "ok"])

    def test_the_failure_line_is_now_masked_and_the_request_line_has_the_long_detail(self):
        self.fake_client([RuntimeError(f"오류 key={FAKE_KEY} 와 {FAKE_TOKEN} " + "가" * 800 + " 끝표식")] + [Resp("본문")])
        response, out = capture(g.call_gemini_with_fallback, "프롬프트")
        self.assertNotIn(FAKE_KEY, out)
        self.assertNotIn(FAKE_TOKEN, out)
        failure = next(line for line in out.splitlines() if line.startswith("Gemini 모델 호출 실패:"))
        self.assertLessEqual(len(failure), len("Gemini 모델 호출 실패: gemini-3.8-flash - ") + 300)
        detail = next(line for line in gemini_lines(out) if "result=other" in line)
        self.assertGreater(len(detail), 450)                  # 로그 줄은 600자까지(앞 요약 포함)
        self.assertTrue(detail.endswith("끝표식"))              # 뒤쪽도 남는다

    def test_old_and_new_behave_the_same_for_random_scenarios(self):
        pool = [lambda: Resp("본문"), lambda: Resp(""), lambda: Resp(WHITESPACE), lambda: Resp(None), lambda: mock.Mock(text="응답"),
                lambda: ApiError(429, quota_body()), lambda: ApiError(503), lambda: RuntimeError("boom"),
                lambda: RuntimeError("::error::x\n줄"), lambda: RuntimeError("")]
        for seed in range(200):
            rng = random.Random(seed)
            models = rng.sample(["a", "b", "c", "d"], rng.randint(1, 4))
            steps = [pool[rng.randrange(len(pool))]() for _ in range(6)]
            results = []
            for new in (False, True):
                client = Client(list(steps))
                calls = {"attempts": 0, "failed": 0}
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), mock.patch.object(g, "get_client", return_value=client), \
                        mock.patch.object(g, "MODEL_CANDIDATES", models), mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0}):
                    try:
                        if new:
                            value = ("ok", g.call_gemini_with_fallback("p").text)
                        else:
                            value = ("ok", legacy_call_gemini_with_fallback("p", g.get_client, models, g.GEMINI_CALLS, g._one_line).text)
                    except RuntimeError as exc:
                        value = ("err", str(exc))
                    calls = dict(g.GEMINI_CALLS)
                shown = [line for line in buf.getvalue().splitlines() if not line.startswith("[GEMINI]")]
                results.append((value, client.models.calls, calls, shown))
            self.assertEqual(results[0], results[1], f"seed {seed}")

    def test_image_query_requests_carry_their_own_purpose_and_restore_the_default(self):
        self.fake_client([Resp(json.dumps({"image_queries": ["a b", "c d"]}))])
        with mock.patch.object(g, "STUB_GEMINI", False):
            queries, out = capture(g.make_image_queries, "제목", "태그", "분류")
        self.assertEqual(queries, ["a b", "c d"])
        self.assertEqual([r.purpose for r in self.log.records], ["image-queries"])
        self.assertEqual(self.log.purpose, "post")
        self.assertIn("purpose=image-queries", gemini_lines(out)[0])

    def test_image_query_failure_also_restores_the_purpose(self):
        self.fake_client([RuntimeError("x")] * 4)
        with mock.patch.object(g, "STUB_GEMINI", False):
            queries, _ = capture(g.make_image_queries, "제목", "태그", "분류")
        self.assertEqual(queries, ["technology", "computer hardware"])      # 실패하면 기본 검색어(동작 불변)
        self.assertEqual(self.log.purpose, "post")
        self.assertEqual({r.purpose for r in self.log.records}, {"image-queries"})


class ChanceSummaryTest(ChanceBase):
    def now(self):
        return datetime(2026, 10, 25, 10, 12, tzinfo=g.KST)

    def test_summary_lists_failure_kinds_models_tokens_and_unsplash_remaining(self):
        self.log.failure("gemini-3.8-flash", 1, ApiError(429, quota_body()))
        self.log.success("gemini-3.7-flash", 1, Resp(model_version="gemini-3.8-flash", usage=Usage(1000, 200, 1200)))
        g.GEMINI_CALLS.update(attempts=2, failed=1)
        g.UNSPLASH_RATE.update(remaining=37, limit=50)
        report = {"outcome": "ALL_REJECTED", "lanes": []}
        with mock.patch.object(g, "write_step_summary") as write:
            capture(g.finish_run, None, report, "schedule", self.now(), 9)
        text = write.call_args[0][0]
        self.assertIn("- Gemini 호출: 2회(실패 1회)", text)
        self.assertIn("- Gemini 실패 내역: 429(한도 초과) 1회", text)
        self.assertIn("- Gemini 응답 모델(요청→응답): gemini-3.7-flash→gemini-3.8-flash 1회", text)
        self.assertIn("- Gemini 토큰(응답에 값이 있는 호출만): 입력 1,000 · 출력 200 · 합계 1,200", text)
        self.assertIn("- Unsplash 남은 호출: 37회(시간당 한도 50회)", text)
        # 줄 순서: Gemini 호출 → 보충 줄 → Unsplash → 후보 탈락·분야 표
        order = [text.index(part) for part in ("- Gemini 호출", "- Gemini 실패 내역", "- Gemini 토큰", "- Unsplash")]
        self.assertEqual(order, sorted(order))

    def test_unsplash_line_without_a_limit_header_and_without_any_header(self):
        report = {"outcome": "ALL_LANES_EMPTY", "lanes": [], "unsplash_rate": {"remaining": 12, "limit": None}}
        self.assertIn("- Unsplash 남은 호출: 12회\n", g.render_run_summary("schedule", self.now(), 9, report) + "\n")
        self.assertNotIn("시간당 한도", g.render_run_summary("schedule", self.now(), 9, report))
        for rate in (None, {}, {"remaining": None, "limit": 50}):
            report["unsplash_rate"] = rate
            self.assertNotIn("Unsplash", g.render_run_summary("schedule", self.now(), 9, report))
        self.assertNotIn("Unsplash", g.render_run_summary("schedule", self.now(), 9, {"outcome": "ALL_LANES_EMPTY", "lanes": []}))

    def test_zero_remaining_is_shown_not_hidden(self):
        report = {"outcome": "ALL_LANES_EMPTY", "lanes": [], "unsplash_rate": {"remaining": 0, "limit": 50}}
        self.assertIn("- Unsplash 남은 호출: 0회(시간당 한도 50회)", g.render_run_summary("schedule", self.now(), 9, report))

    def test_no_calls_says_zero_explicitly_like_blogger_and_issue_edit(self):
        """독립 검증 F-09: 호출이 없던 실행도 `0회`를 적는다 — 줄이 없으면 '호출 안 함'과 '이 기능이 없는 옛 요약'을 구분할 수 없다.
        (이전에는 0회면 줄을 생략했다. Blogger·이슈 수정은 처음부터 0회를 적었다.) 보충 줄(실패 내역·토큰 …)은 호출이 있을 때만 나온다."""
        text = g.render_run_summary("schedule", self.now(), 9, {"outcome": "ALL_LANES_EMPTY", "lanes": [],
                                                                "gemini_calls": {"attempts": 0, "failed": 0}, "gemini_notes": []})
        self.assertIn("- Gemini 호출: 0회(실패 0회)", text)
        self.assertEqual([line for line in text.splitlines() if "Gemini" in line], ["- Gemini 호출: 0회(실패 0회)"])

    def test_a_summary_built_without_the_call_count_has_no_gemini_line(self):
        """finish_run 이 아닌 곳(시험 등)에서 보고서에 호출 수 항목 자체가 없으면 줄을 만들지 않는다(없는 값을 0으로 지어내지 않는다)."""
        for report in ({"outcome": "ALL_LANES_EMPTY", "lanes": []},
                       {"outcome": "ALL_LANES_EMPTY", "lanes": [], "gemini_calls": {}},
                       {"outcome": "ALL_LANES_EMPTY", "lanes": [], "gemini_calls": None}):
            self.assertNotIn("Gemini", g.render_run_summary("schedule", self.now(), 9, report))

    def test_finish_run_writes_the_zero_line_for_a_run_that_never_called_gemini(self):
        report = {"outcome": "ALL_REJECTED", "lanes": []}
        with mock.patch.object(g, "write_step_summary") as write:
            capture(g.finish_run, None, report, "schedule", self.now(), 9)
        self.assertIn("- Gemini 호출: 0회(실패 0회)", write.call_args[0][0])

    def test_failure_summary_keeps_the_call_count_when_every_model_failed(self):
        """모든 모델이 실패해 RuntimeError 로 끝난 실행: 예전 요약에는 '실패 — RuntimeError' 한 줄뿐이라 호출 수가 사라졌다."""
        self.fake_client([ApiError(429, quota_body())] * MODEL_COUNT)
        with self.assertRaises(RuntimeError) as ctx:
            capture(g.call_gemini_with_fallback, "프롬프트")
        text = g.failure_summary(ctx.exception)
        self.assertTrue(text.startswith("### Chance_Blog 실행 요약\n- 결과: **실패** — RuntimeError (원인은 이 단계의 로그를 보세요)"))
        self.assertIn(f"- Gemini 호출: {MODEL_COUNT}회(실패 {MODEL_COUNT}회)", text)
        self.assertIn(f"- Gemini 실패 내역: 429(한도 초과) {MODEL_COUNT}회", text)

    def test_failure_summary_without_any_call_adds_only_the_zero_line(self):
        """Gemini 를 부르기 전에 죽은 실행(예: 뉴스 수집 예외)도 `0회`를 적어 '호출은 없었다'가 요약에서 보이게 한다(F-09)."""
        self.assertEqual(g.failure_summary(ValueError("x")),
                         "### Chance_Blog 실행 요약\n- 결과: **실패** — ValueError (원인은 이 단계의 로그를 보세요)\n"
                         "- Gemini 호출: 0회(실패 0회)")

    def test_run_cli_writes_the_failure_summary_with_the_calls_and_reraises(self):
        self.fake_client([ApiError(503)] * MODEL_COUNT)

        def boom():
            g.call_gemini_with_fallback("프롬프트")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "summary.md"
            with mock.patch.object(g, "main", boom), mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(target)}):
                with self.assertRaises(RuntimeError):
                    capture(g.run_cli)
            text = target.read_text(encoding="utf-8")
        self.assertIn("**실패** — RuntimeError", text)
        self.assertIn(f"- Gemini 호출: {MODEL_COUNT}회(실패 {MODEL_COUNT}회)", text)
        self.assertIn(f"5xx(서버 오류) {MODEL_COUNT}회", text)

    def test_run_cli_prints_the_folded_error_and_lets_exit_codes_pass_through(self):
        def boom():
            raise ValueError("줄1\n::error::위조")
        out = io.StringIO()
        with mock.patch.object(g, "main", boom), contextlib.redirect_stdout(out):
            with self.assertRaises(ValueError):
                g.run_cli()
        self.assertFalse(any(line.startswith("::") for line in out.getvalue().splitlines()))
        with mock.patch.object(g, "main", mock.Mock(side_effect=SystemExit(1))):
            with self.assertRaises(SystemExit):
                g.run_cli()

    def test_fix_images_run_also_reports_gemini_and_unsplash_usage(self):
        def fake_fix(keyword=None):
            g.GEMINI_CALLS.update(attempts=3, failed=1)
            g.UNSPLASH_RATE.update(remaining=40, limit=50)
            self.log.failure("m", 1, ApiError(429, quota_body()))
            return "이미지 점검: 완료: 문제 2건 / 교체 2건 / 건너뜀 0건"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "summary.md"
            env = {k: v for k, v in os.environ.items() if k != "PIPELINE_PAUSE"}
            env["GITHUB_STEP_SUMMARY"] = str(target)
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(g, "FIX_IMAGES", True), \
                    mock.patch.object(g, "DRY_RUN", False), mock.patch.object(g, "STUB_GEMINI", False), \
                    mock.patch.object(g, "fix_images", fake_fix):
                capture(g.main)
            text = target.read_text(encoding="utf-8")
        self.assertIn("- 이미지 점검: 완료: 문제 2건", text)
        self.assertIn("- Gemini 호출: 3회(실패 1회)", text)
        self.assertIn("- Unsplash 남은 호출: 40회(시간당 한도 50회)", text)


class ChanceModuleDefaultsTest(unittest.TestCase):
    """시험이 CALL_LOG 를 갈아 끼우지 않는 실제 실행과 같은 조건(모듈 수준 기본 기록 장치)."""

    def test_the_default_call_log_prints_every_request_with_the_chance_label(self):
        saved_records, saved_calls = list(g.CALL_LOG.records), dict(g.GEMINI_CALLS)

        def restore():
            g.CALL_LOG.records[:] = saved_records
            g.GEMINI_CALLS.update(saved_calls)
        self.addCleanup(restore)
        client = Client([ApiError(503), Resp("본문")])
        with mock.patch.object(g, "get_client", return_value=client), mock.patch.object(g, "MODEL_CANDIDATES", ["a", "b"]):
            _, out = capture(g.call_gemini_with_fallback, "프롬프트")
        lines = gemini_lines(out)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("[GEMINI] label=chance purpose=post model=a result=5xx "), lines[0])
        self.assertTrue(lines[1].startswith("[GEMINI] label=chance purpose=post model=b result=ok "), lines[1])
        self.assertEqual((g.CALL_LOG.label, g.CALL_LOG.purpose), ("chance", "post"))


class FakeUnsplashResponse:
    def __init__(self, headers=None, body=None):
        self.headers = headers
        self._body = json.dumps(body if body is not None else {"results": []}).encode("utf-8")

    def read(self, *args):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class UnsplashRateTest(ChanceBase):
    def search(self, response=None, error=None, query="q"):
        def fake_urlopen(req, timeout=0):
            if error is not None:
                raise error
            return response
        with mock.patch.object(g, "STUB_UNSPLASH", False), mock.patch.object(g, "UNSPLASH_KEY", "fake-unsplash-key"), \
                mock.patch.object(g.urllib.request, "urlopen", fake_urlopen):
            return capture(g.search_unsplash, query)

    def test_remaining_and_limit_are_read_from_a_successful_response(self):
        self.search(FakeUnsplashResponse({"X-Ratelimit-Remaining": "37", "X-Ratelimit-Limit": "50"}))
        self.assertEqual(g.UNSPLASH_RATE, {"remaining": 37, "limit": 50})

    def test_the_last_observed_value_wins_and_a_missing_header_keeps_the_previous_value(self):
        self.search(FakeUnsplashResponse({"X-Ratelimit-Remaining": "37", "X-Ratelimit-Limit": "50"}))
        self.search(FakeUnsplashResponse({"X-Ratelimit-Remaining": "36", "X-Ratelimit-Limit": "50"}))
        self.assertEqual(g.UNSPLASH_RATE["remaining"], 36)
        self.search(FakeUnsplashResponse({}))
        self.assertEqual(g.UNSPLASH_RATE, {"remaining": 36, "limit": 50})
        self.search(FakeUnsplashResponse(None))                       # headers 속성 자체가 없는 응답
        self.assertEqual(g.UNSPLASH_RATE, {"remaining": 36, "limit": 50})

    def test_header_names_are_case_insensitive_for_real_http_headers(self):
        from email.message import Message
        headers = Message()
        headers["x-ratelimit-remaining"] = "12"
        self.search(FakeUnsplashResponse(headers))
        self.assertEqual(g.UNSPLASH_RATE["remaining"], 12)

    def test_garbage_values_are_ignored(self):
        for bad in ("abc", "-1", "1e3", "", "12 13", "99999999", None, 5):
            g.UNSPLASH_RATE.update(remaining=None, limit=None)
            self.search(FakeUnsplashResponse({"X-Ratelimit-Remaining": bad, "X-Ratelimit-Limit": bad}))
            self.assertEqual(g.UNSPLASH_RATE, {"remaining": None, "limit": None}, repr(bad))

    def test_values_with_three_to_seven_digits_are_read_whole(self):
        """독립 검증 M081: 승격된 앱은 시간당 5000회처럼 네 자리 한도를 받는다. 7자리까지 읽고 8자리부터는 버린다(앞뒤 공백은 무시)."""
        for text, number in (("5000", 5000), ("4999", 4999), ("12345", 12345), ("100", 100), ("1000000", 1000000),
                             ("9999999", 9999999), ("007", 7), ("0", 0), (" 4200 ", 4200)):
            g.UNSPLASH_RATE.update(remaining=None, limit=None)
            self.search(FakeUnsplashResponse({"X-Ratelimit-Remaining": text, "X-Ratelimit-Limit": "5000"}))
            self.assertEqual(g.UNSPLASH_RATE, {"remaining": number, "limit": 5000}, repr(text))
        g.UNSPLASH_RATE.update(remaining=None, limit=None)
        self.search(FakeUnsplashResponse({"X-Ratelimit-Remaining": "10000000", "X-Ratelimit-Limit": "50000000"}))
        self.assertEqual(g.UNSPLASH_RATE, {"remaining": None, "limit": None})
        self.assertEqual(g._unsplash_line({"remaining": 4999, "limit": 5000}), "Unsplash 남은 호출: 4999회(시간당 한도 5000회)")

    def test_an_error_response_still_tells_how_many_calls_are_left(self):
        error = urllib.error.HTTPError("https://api.unsplash.com/x", 403, "Rate Limit Exceeded",
                                       {"X-Ratelimit-Remaining": "0", "X-Ratelimit-Limit": "50"}, io.BytesIO(b""))
        urls, out = self.search(error=error)
        self.assertEqual(urls, [])                                    # 동작 불변: 실패하면 빈 목록
        self.assertIn("Unsplash API 오류 403", out)
        self.assertEqual(g.UNSPLASH_RATE, {"remaining": 0, "limit": 50})

    def test_other_failures_leave_the_values_alone_and_results_are_unchanged(self):
        g.UNSPLASH_RATE.update(remaining=5, limit=50)
        urls, out = self.search(error=OSError("연결 실패"))
        self.assertEqual(urls, [])
        self.assertEqual(g.UNSPLASH_RATE, {"remaining": 5, "limit": 50})
        body = {"results": [{"urls": {"raw": "https://images.unsplash.com/photo-1"}, "links": {"download_location": "https://api.unsplash.com/d"}}]}
        urls, _ = self.search(FakeUnsplashResponse({"X-Ratelimit-Remaining": "4"}, body))
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].startswith("https://images.unsplash.com/photo-1"))
        self.assertEqual(g.UNSPLASH_RATE["remaining"], 4)

    def test_objects_whose_get_does_not_exist_are_ignored(self):
        self.search(FakeUnsplashResponse(object()))
        self.assertEqual(g.UNSPLASH_RATE, {"remaining": None, "limit": None})


# ----------------------------------------------------------------------------
# 7) 이슈 수정 러너: 요약에 호출 수가 남는다
# ----------------------------------------------------------------------------
class EditsRunnerCallLogTest(unittest.TestCase):
    LAYOUT = "layout | 섹션/레이아웃 변경 (해당 페이지 안에서만)"
    PATCH = {"patches": [{"old": "두 번째 문단입니다.", "new": "두 번째 문단입니다.\n\n**강조 문장입니다.**"}]}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_edit_root(self._tmp.name)
        self.summary_path = Path(self._tmp.name) / "summary.md"
        self.issue_path = Path(self._tmp.name) / "issue.json"

    def fake_gemini(self, script):
        """build_llm 이 쓰는 make_gemini_llm 에 가짜 클라이언트를 끼운다(대기 없음, 고정 시계)."""
        client, real = Client(script), llm_mod.make_gemini_llm

        def wrapped(key, models, max_retries=2, **kw):
            return real(key, models, max_retries=max_retries, sleep=lambda s: None, client_factory=lambda: client,
                        clock=Clock(), **kw)
        patcher = mock.patch.object(llm_mod, "make_gemini_llm", wrapped)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def write_issue(self, body):
        self.issue_path.write_text(json.dumps(issue(body)), encoding="utf-8")

    def run_main(self, extra_env=None):
        env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "PIPELINE_PAUSE", "DRY_RUN")}
        env.update({"GITHUB_STEP_SUMMARY": str(self.summary_path), "GEMINI_API_KEY": "fake-llm-key", **(extra_env or {})})
        out = Path(self._tmp.name) / "out"
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(buf):
            code = runner.main(["--issue-file", str(self.issue_path), "--out", str(out), "--root", str(self.root)])
        return code, buf.getvalue()

    def summary(self):
        return self.summary_path.read_text(encoding="utf-8") if self.summary_path.exists() else ""

    def test_an_ai_patch_reports_one_call_in_the_log_and_the_step_summary(self):
        client = self.fake_gemini([Resp(json.dumps(self.PATCH), "gemini-3.8-flash", Usage(500, 40, 540))])
        self.write_issue(page_body(edit=self.LAYOUT, after="둘째 문단 아래에 강조 문장을 넣어 주세요"))
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertEqual(len(client.models.calls), 1)
        self.assertIn(TAG + "   * Gemini 호출: 1회(실패 0회)", out.splitlines())
        lines = runner_gemini_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("[GEMINI] label=issue-edit purpose=patch model=gemini-3.8-flash result=ok "), lines[0])
        self.assertEqual(gemini_lines(out), [])                       # 머리 없는 요청 줄은 없다
        for line in out.splitlines():                                  # 하드닝의 규칙: 이 단계가 내는 모든 줄은 머리로 시작한다
            self.assertTrue(line.startswith(TAG), line)
        text = self.summary()
        self.assertIn("### 이슈 수정 요청 처리 요약\n- 결과: **ok**\n- Gemini 호출: 1회(실패 0회)", text)
        self.assertIn("- Gemini 토큰(응답에 값이 있는 호출만): 입력 500 · 출력 40 · 합계 540", text)

    def test_a_literal_replacement_uses_no_gemini_and_says_zero(self):
        self.fake_gemini([])
        self.write_issue(page_body(before="두 번째 문단입니다.", after="두 번째 문단을 고쳤습니다."))
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertNotIn("Gemini", out)                              # AI 를 부르지 않은 처리는 로그 줄을 늘리지 않는다
        self.assertEqual(len(out.splitlines()), 1)                   # 상태 줄 하나뿐(하드닝 시험이 줄 수를 세는 것과 같은 조건)
        self.assertIn("- Gemini 호출: 0회(실패 0회)", self.summary())  # 0회는 실행 요약에만 남는다

    def test_every_model_failing_leaves_the_count_and_the_failure_kind_in_the_summary(self):
        client = self.fake_gemini([ApiError(429, quota_body())] * ALL_TRIES)
        self.write_issue(page_body(edit=self.LAYOUT, after="둘째 문단 아래에 강조 문장을 넣어 주세요"))
        code, out = self.run_main()
        self.assertEqual(code, runner.EXIT_INFRA)
        self.assertEqual(len(client.models.calls), ALL_TRIES)
        text = self.summary()
        self.assertIn("**error**", text)
        self.assertIn(f"- Gemini 호출: {ALL_TRIES}회(실패 {ALL_TRIES}회)", text)
        self.assertIn(f"- Gemini 실패 내역: 429(한도 초과) {ALL_TRIES}회", text)
        lines = runner_gemini_lines(out)
        self.assertEqual(len(lines), ALL_TRIES)
        self.assertTrue(all(f"quotaId={DAY_QUOTA_ID}" in line and "retryDelay=37s" in line for line in lines))   # 300자 안에 한도 구분 필드가 남는다
        self.assertTrue(all(len(line) <= 300 for line in lines))
        self.assertIn(TAG + f"   * Gemini 호출: {ALL_TRIES}회(실패 {ALL_TRIES}회)", out.splitlines())
        for line in out.splitlines():
            self.assertTrue(line.startswith(TAG), line)

    def test_a_three_violation_429_keeps_the_day_limit_and_the_wait_in_every_runner_line(self):
        """독립 검증 F-01: 러너의 요청 줄은 300자로 잘린다. 실제 모양(위반 3개)의 429 에서도 일 한도 id 와 재시도 대기가 줄 안에 남아야 한다."""
        client = self.fake_gemini([ClientError(429, three_violation_body())] * ALL_TRIES)
        self.write_issue(page_body(edit=self.LAYOUT, after="둘째 문단 아래에 강조 문장을 넣어 주세요"))
        code, out = self.run_main()
        self.assertEqual(len(client.models.calls), ALL_TRIES)
        lines = runner_gemini_lines(out)
        self.assertEqual(len(lines), ALL_TRIES)
        for line in lines:
            self.assertIn(f"quotaId={DAY_QUOTA_ID} retryDelay=55s", line)
            self.assertLessEqual(len(line), 300)

    def test_the_api_key_from_the_environment_is_replaced_in_the_gemini_lines(self):
        """독립 검증 F-05: 환경의 GEMINI_API_KEY 값은 비밀 패턴에 걸리지 않는 모양이어도 요청 줄에서 글자 그대로 가려진다."""
        self.fake_gemini([RuntimeError("credential fake-llm-key rejected")] * MODEL_COUNT)       # 일시 오류가 아니라 모델마다 한 번씩만 시도한다
        self.write_issue(page_body(edit=self.LAYOUT, after="둘째 문단 아래에 강조 문장을 넣어 주세요"))
        code, out = self.run_main()
        lines = runner_gemini_lines(out)
        self.assertEqual(len(lines), MODEL_COUNT)
        self.assertTrue(all("credential *** rejected" in line and "fake-llm-key" not in line for line in lines), lines[0])

    def test_secrets_and_commands_in_failures_stay_out_of_the_runner_log(self):
        body = quota_body(message=f"키 {FAKE_KEY} {FAKE_TOKEN} ::error::위조 ##[group]위조")
        self.fake_gemini([ApiError(429, body)] * 12)
        self.write_issue(page_body(edit=self.LAYOUT, after="둘째 문단 아래에 강조 문장을 넣어 주세요"))
        code, out = self.run_main()
        for secret in (FAKE_KEY, FAKE_TOKEN, FAKE_KEY[:20], FAKE_TOKEN[:20]):
            self.assertNotIn(secret, out)
        self.assertNotIn("##[", out)
        self.assertEqual([line for line in out.splitlines() if line.lstrip().startswith("::")], [])

    def test_image_query_requests_get_their_own_purpose(self):
        self.fake_gemini([Resp(json.dumps({"image_queries": ["fire rescue", "firefighter"]}))])
        post = "https://shine88pc.github.io/chanceblog/posts/2026/10/18/kr-111111/"
        iss = issue(image_body(post, "소방관 구조 활동"), labels=("blog-control", "edit:image"), title="[이미지 변경] x")
        picked = []

        def picker(queries, used):
            picked.append(list(queries))
            return "https://images.unsplash.com/photo-777?auto=format&fit=crop&w=1000&q=80"
        calls = CallLog(label="issue-edit", out=print)
        result, out = capture(runner.process_issue, iss, self.root, env={"GEMINI_API_KEY": "fake-llm-key"},
                              image_picker=picker, calls=calls)
        self.assertEqual(result.status, "ok", result.reasons)
        self.assertEqual([r.purpose for r in calls.records], ["image-queries"])
        self.assertIn("purpose=image-queries", gemini_lines(out)[0])
        self.assertEqual(picked[0][:2], ["fire rescue", "firefighter"])

    def test_without_a_call_log_process_issue_works_as_before(self):
        self.fake_gemini([Resp(json.dumps(self.PATCH))])
        iss = issue(page_body(edit=self.LAYOUT, after="둘째 문단 아래에 강조 문장을 넣어 주세요"))
        result = runner.process_issue(iss, self.root, env={"GEMINI_API_KEY": "fake-llm-key"})
        self.assertEqual(result.status, "ok")

    def test_an_injected_fake_llm_is_not_counted(self):
        calls = CallLog(label="issue-edit")
        iss = issue(page_body(edit=self.LAYOUT, after="둘째 문단 아래에 강조 문장을 넣어 주세요"))
        result = runner.process_issue(iss, self.root, llm=lambda prompt: (json.dumps(self.PATCH), "m"), calls=calls)
        self.assertEqual(result.status, "ok")
        self.assertEqual(calls.attempts, 0)

    def test_a_summary_write_failure_never_changes_the_result_or_the_exit_code(self):
        self.fake_gemini([])
        self.write_issue(page_body(before="두 번째 문단입니다.", after="두 번째 문단을 고쳤습니다."))
        folder = Path(self._tmp.name) / "not-a-file"
        folder.mkdir()
        self.summary_path = folder                                    # 파일이 아니라 폴더라 열기에 실패한다
        code, out = self.run_main()
        self.assertEqual(code, 0)
        notes = [line for line in out.splitlines() if "실행 요약 쓰기 실패(처리 결과에는 영향 없음)" in line]
        self.assertEqual(len(notes), 1, out)
        self.assertTrue(notes[0].startswith(TAG + "   * "), notes[0])
        self.assertTrue(notes[0].endswith(("PermissionError", "IsADirectoryError")), notes[0])          # 예외 종류만, 원문은 없다
        for line in out.splitlines():
            self.assertTrue(line.startswith(TAG), line)

    def test_without_the_summary_variable_nothing_is_written(self):
        self.fake_gemini([])
        self.write_issue(page_body(before="두 번째 문단입니다.", after="두 번째 문단을 고쳤습니다."))
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_STEP_SUMMARY", "GEMINI_API_KEY")}
        out = Path(self._tmp.name) / "out2"
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()):
            code = runner.main(["--issue-file", str(self.issue_path), "--out", str(out), "--root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertFalse(self.summary_path.exists())

    def test_a_broken_issue_file_still_leaves_the_zero_call_summary(self):
        self.issue_path.write_text("{깨진 json", encoding="utf-8")
        code, out = self.run_main()
        self.assertEqual(code, runner.EXIT_CONFIG)
        self.assertNotIn("Gemini", out)
        self.assertIn("**error**", self.summary())
        self.assertIn("- Gemini 호출: 0회(실패 0회)", self.summary())

    def test_hostile_status_text_cannot_inject_markdown_into_the_summary(self):
        self.write_issue(page_body(before="두 번째 문단입니다.", after="두 번째 문단을 고쳤습니다."))
        hostile = runner.Result("ok|<b>[x](http://e.example)")
        with mock.patch.object(runner, "process_issue", return_value=hostile) as fake:
            code, out = self.run_main()
        self.assertEqual(fake.call_count, 1)                             # 전제: 가짜 결과가 실제로 쓰였다
        lines = self.summary().splitlines()
        self.assertEqual(lines[0], "### 이슈 수정 요청 처리 요약")
        self.assertIn("ok", lines[1])
        for ch in "|<>[]":
            self.assertNotIn(ch, lines[1])


# ----------------------------------------------------------------------------
# 8) 독립 검증(2026-10-25) 지적 반영: 한도 구분 필드 보존(F-01) · 기록 실패가 호출을 바꾸지 않음(F-02) · 마스킹(F-03~F-06)
# ----------------------------------------------------------------------------
TOKENS_QUOTA_ID = "GenerateContentInputTokensPerModelPerMinute-FreeTier"
THREE_MESSAGE = (
    "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: "
    "https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/usage?tab=rate-limit. \n"
    "* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_input_token_count, limit: 250000, "
    "model: gemini-2.5-flash\n"
    "* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 5, model: gemini-2.5-flash\n"
    "* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-2.5-flash\n"
    "Please retry in 55.2s.")


def violation(metric, quota_id, value):
    return {"quotaMetric": "generativelanguage.googleapis.com/" + metric, "quotaId": quota_id,
            "quotaDimensions": {"location": "global", "model": "gemini-2.5-flash"}, "quotaValue": value}


THREE_VIOLATIONS = {
    "tokens": violation("generate_content_free_tier_input_token_count", TOKENS_QUOTA_ID, "250000"),
    "rpm": violation("generate_content_free_tier_requests", MINUTE_QUOTA_ID, "5"),
    "rpd": violation("generate_content_free_tier_requests", DAY_QUOTA_ID, "20"),
}


def three_violation_body(order=("tokens", "rpm", "rpd"), retry="55s"):
    """실제 429 의 모양: 한도 위반이 여러 개(분당 토큰 → 분당 요청 → 일 요청: 공개된 gemini-cli 이슈의 표본 순서)이고
    재시도 대기는 RetryInfo 에 따로 있다. 이 모양에서 위반 수를 2개로 자르면 마지막(일 한도)이 사라졌다."""
    body = quota_body(message=THREE_MESSAGE, retry=retry)
    body["error"]["details"][1]["violations"] = [dict(THREE_VIOLATIONS[key]) for key in order]
    return body


class ClientError(ApiError):
    """google-genai 의 4xx 오류 클래스 이름(로그 줄 머리의 길이를 실제와 같게 맞춘다)."""


class QuotaHintsTest(unittest.TestCase):
    """독립 검증 F-01: 위반이 3개인 실제 모양의 429 에서도 일 한도 id 와 재시도 대기가 두 가지 로그 줄(Blogger 600자·이슈 수정 300자)에 남는다."""

    def head(self, order=("tokens", "rpm", "rpd")):
        return failure_detail(ClientError(429, three_violation_body(order))).split(" | ", 1)[0]

    def test_the_day_limit_id_and_the_wait_survive_in_every_order_of_the_violations(self):
        for order in itertools.permutations(("tokens", "rpm", "rpd")):
            head = self.head(order)
            self.assertIn(f"quotaId={DAY_QUOTA_ID}", head, order)
            self.assertIn("retryDelay=55s", head, order)

    def test_the_head_lists_the_day_limit_then_the_wait_then_the_other_limits_then_the_metrics(self):
        head = self.head()
        parts = (f"quotaId={DAY_QUOTA_ID}", "retryDelay=55s", f"quotaId={TOKENS_QUOTA_ID}", f"quotaId={MINUTE_QUOTA_ID}", "quotaMetric=")
        positions = [head.index(part) for part in parts]
        self.assertEqual(positions, sorted(positions), head)
        self.assertTrue(head.startswith(f"ClientError code=429 status=RESOURCE_EXHAUSTED quotaId={DAY_QUOTA_ID} retryDelay=55s "), head)

    def test_a_single_violation_shows_the_id_the_wait_and_the_metric(self):
        day = failure_detail(ClientError(429, quota_body(DAY_QUOTA_ID, retry="37s"))).split(" | ", 1)[0]
        self.assertEqual(day, f"ClientError code=429 status=RESOURCE_EXHAUSTED quotaId={DAY_QUOTA_ID} retryDelay=37s "
                              "quotaMetric=generativelanguage.googleapis.com/generate_content_free_tier_requests")
        minute = failure_detail(ClientError(429, quota_body(MINUTE_QUOTA_ID, retry="9s"))).split(" | ", 1)[0]
        self.assertEqual(minute, "ClientError code=429 status=RESOURCE_EXHAUSTED retryDelay=9s "
                                 f"quotaId={MINUTE_QUOTA_ID} "
                                 "quotaMetric=generativelanguage.googleapis.com/generate_content_free_tier_requests")

    def test_two_day_limit_ids_both_come_first(self):
        body = three_violation_body(("rpm", "rpd", "tokens"))
        body["error"]["details"][1]["violations"].append(violation("generate_content_free_tier_requests",
                                                                   "GenerateContentTokensPerDayPerModel-FreeTier", "1000000"))
        head = failure_detail(ClientError(429, body)).split(" | ", 1)[0]
        order = [head.index(f"quotaId={DAY_QUOTA_ID}"), head.index("quotaId=GenerateContentTokensPerDayPerModel-FreeTier"),
                 head.index("retryDelay=55s"), head.index(f"quotaId={MINUTE_QUOTA_ID}")]
        self.assertEqual(order, sorted(order), head)

    def test_the_day_mark_is_matched_without_regard_to_case_and_only_for_ids(self):
        body = {"error": {"status": "RESOURCE_EXHAUSTED", "details": [
            {"violations": [{"quotaId": "ReqPerMinute-A", "quotaMetric": "perday-metric"}, {"quotaId": "reqperday-b"}]}]}}
        head = failure_detail(ApiError(429, body)).split(" | ", 1)[0]
        self.assertLess(head.index("quotaId=reqperday-b"), head.index("quotaId=ReqPerMinute-A"))
        self.assertIn("quotaMetric=perday-metric", head)             # 지표 이름에 perday 가 있어도 순서는 id 만 본다
        upper = {"error": {"status": "RESOURCE_EXHAUSTED", "details": [{"violations": [{"quotaId": "A-PERDAY-X"}, {"quotaId": "B-PerMinute"}]}]}}
        head = failure_detail(ApiError(429, upper)).split(" | ", 1)[0]
        self.assertEqual(head.count("quotaId=A-PERDAY-X"), 1)        # 일 한도 id 는 한 번만(나머지 목록에 다시 들어가지 않는다)
        self.assertLess(head.index("quotaId=A-PERDAY-X"), head.index("quotaId=B-PerMinute"))

    def test_only_the_first_twenty_distinct_values_of_a_key_are_scanned(self):
        ids = [{"quotaId": f"Q{i}"} for i in range(30)]
        ids[19]["quotaId"] = "Q19PerDay"            # 스무 번째까지는 읽는다
        ids[20]["quotaId"] = "Q20PerDay"            # 스물한 번째부터는 읽지 않는다
        ids[25]["quotaId"] = "Q25PerDay"
        head = failure_detail(ApiError(429, {"error": {"status": "X", "details": [{"violations": ids}]}})).split(" | ", 1)[0]
        self.assertIn("quotaId=Q19PerDay", head)
        self.assertNotIn("Q20PerDay", head)
        self.assertNotIn("Q25PerDay", head)
        self.assertEqual(head.count("quotaId="), 5)

    def test_the_head_may_use_three_fifths_of_the_limit_before_it_is_cut(self):
        """앞쪽 요약은 limit 의 3/5(600자면 360자)까지 자르지 않는다: 335자짜리는 그대로, 3/5 를 넘으면 `…` 로 자른다."""
        body = {"error": {"status": "X", "details": [{"retryDelay": "9" * 60}, {"violations": [{"quotaId": c * 70} for c in "ABC"]}]}}
        head = failure_detail(ApiError(429, body)).split(" | ", 1)[0]
        self.assertEqual(len(head), 335)
        self.assertNotIn("…", head)
        longer = {"error": {"status": "X", "details": [{"retryDelay": "9" * 60}, {"violations": [{"quotaId": c * 70} for c in "ABCDE"]}]}}
        cut = failure_detail(ApiError(429, longer)).split(" | ", 1)[0]
        self.assertEqual(len(cut), 360)
        self.assertTrue(cut.endswith("…"))

    def test_at_most_five_values_per_key_are_shown(self):
        body = {"error": {"status": "X", "details": [{"violations": [{"quotaId": f"Q{i}", "quotaMetric": f"M{i}"} for i in range(9)]},
                                                      {"retryDelay": "1s"}, {"retryDelay": "2s"}, {"retryDelay": "3s"}, {"retryDelay": "4s"},
                                                      {"retryDelay": "5s"}, {"retryDelay": "6s"}, {"retryDelay": "7s"}]}}
        head = failure_detail(ApiError(429, body)).split(" | ", 1)[0]
        self.assertEqual((head.count("quotaId="), head.count("retryDelay="), head.count("quotaMetric=")), (5, 5, 5))

    def test_the_blogger_line_of_600_characters_keeps_both(self):
        log = CallLog(label="blogger_macat", purpose="generate")
        rec = log.failure("gemini-3.8-flash", 0.4, ClientError(429, three_violation_body()))
        self.assertLessEqual(len(rec.detail), 600)
        self.assertIn(f"quotaId={DAY_QUOTA_ID} retryDelay=55s", call_line(rec))

    def test_the_issue_edit_line_of_300_characters_keeps_both_with_the_longest_label_purpose_and_model(self):
        """이슈 수정 러너는 요청마다 `safety.log_text(call_line(…), 300)` 으로 자른다. 용도와 모델 이름이 가장 긴 경우에도 들어와야 한다."""
        longest_model = max(runner.registry_models(REAL), key=len)
        for purpose_name in ("patch", "image-queries"):
            log = CallLog(label="issue-edit", purpose=purpose_name)
            rec = log.failure(longest_model, 12.3, ClientError(429, three_violation_body()))
            capped = safety.log_text(call_line(rec), 300)
            self.assertIn(f"quotaId={DAY_QUOTA_ID} retryDelay=55s", capped, purpose_name)
            self.assertLessEqual(len(capped), 300)

    def test_a_429_without_a_day_limit_id_still_shows_the_wait_before_the_ids(self):
        head = self.head(("tokens", "rpm"))
        self.assertNotIn("PerDay", head)
        self.assertLess(head.index("retryDelay=55s"), head.index("quotaId="))


class HintAndFieldMaskTest(unittest.TestCase):
    """독립 검증 F-03: 값을 자르기 전에 먼저 가린다 — 80자에서 잘린 키 조각은 비밀 패턴에 걸리지 않아 그대로 남았다."""

    def test_a_key_straddling_the_80_character_cut_is_masked_first(self):
        for name in ("quotaId", "retryDelay", "quotaMetric"):
            value = "Q" * 60 + FAKE_KEY                 # 키가 60~99자 구간이라 80자에서 자르면 키의 앞 20자가 남는다
            body = {"error": {"status": "X", "details": [{name: value}]}}
            head = failure_detail(ApiError(429, body)).split(" | ", 1)[0]
            self.assertNotIn("AIza", head, name)
            self.assertIn(f"{name}={'Q' * 60}***", head, name)

    def test_numbers_and_long_plain_values_are_still_cut_at_80(self):
        body = {"error": {"status": "X", "details": [{"retryDelay": 12.5}, {"quotaId": "P" * 200}]}}
        head = failure_detail(ApiError(429, body)).split(" | ", 1)[0]
        self.assertIn("retryDelay=12.5", head)
        self.assertIn("quotaId=" + "P" * 79 + "…", head)

    def test_the_status_and_the_class_name_part_of_the_head_is_masked_too(self):
        err = ApiError(429, quota_body())
        err.status = f"BAD {FAKE_KEY}"
        head = failure_detail(err).split(" | ", 1)[0]
        self.assertNotIn("AIza", head)
        self.assertIn("status=BAD ***", head)
        verbatim = ApiError(429, quota_body())
        verbatim.status = "REJECTED fake-llm-key-0123"
        head = failure_detail(verbatim, secrets=("fake-llm-key-0123",)).split(" | ", 1)[0]
        self.assertNotIn("fake-llm-key-0123", head)

    def test_the_empty_answer_reason_hides_the_real_key_too(self):
        log = CallLog(secrets=("fake-llm-key-0123",))
        rec = log.empty("a", 1, Resp(text="", candidates=[Candidate("STOP fake-llm-key-0123")]))
        self.assertEqual(rec.detail, "빈 응답 finish_reason=STOP ***")

    def test_served_model_is_masked_before_it_is_cut_at_80(self):
        shown = served_model(Resp(model_version="v" * 70 + FAKE_KEY))
        self.assertNotIn("AIza", shown)
        self.assertEqual(shown, "v" * 70 + "***")

    def test_empty_detail_is_masked_before_it_is_cut_at_120(self):
        reason = "R" * 90 + FAKE_KEY                       # 접두 16자 + 90 + 키 → 120자에서 키가 잘린다
        shown = empty_detail(Resp(text="", candidates=[Candidate(reason)]))
        self.assertNotIn("AIza", shown)
        self.assertTrue(shown.endswith("***"), shown)


class CallLineMaskTest(unittest.TestCase):
    """독립 검증 F-04: 줄의 label·purpose·model·served 칸도 가린다(60자에서 자르기 전에)."""

    def test_every_free_text_field_is_masked_before_being_cut(self):
        text = "L" * 50 + FAKE_KEY                         # 60자에서 자르면 키 앞 10자(`AIza`+6)가 남는다
        record = CallRecord(label=text, purpose=text, model=text, served_model=text, outcome="ok", seconds=1.0)
        line = call_line(record)
        self.assertNotIn("AIza", line)
        self.assertEqual(line.count("L" * 50 + "***"), 4)
        for name in ("label", "purpose", "model", "served"):
            self.assertIn(f"{name}={'L' * 50}***", line)

    def test_missing_values_are_dashes_not_the_word_none(self):
        record = CallRecord(label=None, purpose=None, model="m", served_model=None, outcome="ok", seconds=0.0)
        self.assertEqual(call_line(record), "[GEMINI] label=- purpose=- model=m result=ok sec=0.0 served=- tokens=-")

    def test_folding_and_the_60_character_limit_still_apply(self):
        record = CallRecord(label="a b\nc", purpose="p" * 100, model="m", served_model="", outcome="ok", seconds=0.0)
        line = call_line(record)
        self.assertIn("label=a_b_c ", line)
        self.assertIn("purpose=" + "p" * 59 + "… ", line)
        self.assertIn("served=- ", line)

    def test_records_built_by_the_log_carry_no_secret_in_any_field_or_summary_line(self):
        log = CallLog(label=f"b-{FAKE_KEY}", purpose=f"p-{FAKE_TOKEN}")
        rec = log.success(f"m-{FAKE_NEW_KEY}", 1, Resp(model_version=f"v-{FAKE_KEY}", usage=Usage(1, 2, 3)))
        log.failure(f"m-{FAKE_NEW_KEY}", 1, RuntimeError("x"))
        shown = " ".join([call_line(r) for r in log.records] + [str(vars(rec))] + log.summary_lines())
        for secret in (FAKE_KEY, FAKE_TOKEN, FAKE_NEW_KEY, FAKE_KEY[:20], FAKE_TOKEN[:20], FAKE_NEW_KEY[:20]):
            self.assertNotIn(secret, shown)
        self.assertEqual((rec.label, rec.purpose, rec.model, rec.served_model), ("b-***", "p-***", "m-***", "v-***"))


class ScrubTest(unittest.TestCase):
    """독립 검증 F-05: 호출 기록용 글자 가리기 — 비밀 패턴 + 실행 중인 키의 글자 그대로 + 프로젝트 번호."""

    def test_a_secret_value_is_replaced_verbatim_when_it_is_long_enough(self):
        self.assertEqual(scrub("앞 fake-llm-key 뒤 fake-llm-key 끝", ("fake-llm-key",)), "앞 *** 뒤 *** 끝")
        self.assertEqual(scrub("a abcdef b", ("abcdef",)), "a *** b")                  # 6자는 가린다
        self.assertEqual(scrub("a abcde b", ("abcde",)), "a abcde b")                  # 5자는 일반 낱말과 겹쳐 그대로 둔다
        self.assertEqual(scrub("x one-key two-key y", ("one-key", "two-key")), "x *** *** y")

    def test_empty_none_and_non_string_secrets_are_ignored(self):
        for secrets in ((), (None,), ("",), (0,), (None, "", " "), None):
            self.assertEqual(scrub("plain text here", secrets), "plain text here", secrets)
        self.assertEqual(scrub("n 1234567 n", (1234567,)), "n *** n")                   # 숫자 값도 글자로 본다

    def test_patterns_still_apply_and_input_may_be_an_exception(self):
        self.assertEqual(scrub(f"앞 {FAKE_KEY} 뒤"), "앞 *** 뒤")
        self.assertEqual(scrub(RuntimeError("bad fake-llm-key"), ("fake-llm-key",)), "bad ***")
        self.assertEqual(scrub(None), "None")

    def test_project_numbers_are_masked_in_both_shapes_and_the_label_stays(self):
        self.assertEqual(scrub("consumer 'project_number:123456789012'."), "consumer 'project_number:***'.")
        self.assertEqual(scrub("name: projects/123456789012/locations/x"), "name: projects/***/locations/x")
        self.assertEqual(scrub("PROJECT_NUMBER:99 Projects/7"), "PROJECT_NUMBER:*** Projects/***")
        self.assertEqual(scrub("project_number: abc projects/name project_number:"), "project_number: abc projects/name project_number:")

    def test_the_shared_mask_is_unchanged_by_this_change(self):
        """프로젝트 번호 가리기는 호출 기록 쪽에만 있다(공용 비밀 패턴·mask 는 건드리지 않는다)."""
        self.assertEqual(llm_mod.mask("project_number:123456789012 projects/123456789012"), "project_number:123456789012 projects/123456789012")

    def test_failure_detail_masks_project_numbers_in_the_body_and_the_hints(self):
        body = quota_body(message="Quota exceeded for consumer 'project_number:123456789012' on projects/123456789012")
        body["error"]["details"][1]["violations"][0]["quotaId"] = "Q-project_number:123456789012"
        detail = failure_detail(ApiError(429, body))
        self.assertNotIn("123456789012", detail)
        self.assertIn("quotaId=Q-project_number:***", detail)


class ApiKeyReplacementTest(unittest.TestCase):
    KEY = "fake-llm-key-0123456789"          # 비밀 패턴(AIza…·ya29.… 등)에 걸리지 않는 값이라 글자 그대로 바꿔야만 가려진다

    def run_failing_call(self, key, text, log=None):
        client = Client([RuntimeError(text)])
        lines = []
        call = make_gemini_llm(key, ["a"], max_retries=0, sleep=lambda s: None, client_factory=lambda: client, clock=Clock(), log=log)
        call.call_log.configure(out=lines.append)
        with self.assertRaises(LLMError):
            call("p")
        return call, lines

    def test_the_key_given_to_make_gemini_llm_never_reaches_the_log_line_or_the_record(self):
        call, lines = self.run_failing_call(self.KEY, f"credential {self.KEY} rejected for {self.KEY}")
        self.assertEqual(len(lines), 1)
        self.assertNotIn(self.KEY, lines[0])
        self.assertIn("credential *** rejected for ***", lines[0])
        self.assertNotIn(self.KEY, call.call_log.records[0].detail)

    def test_a_log_supplied_from_outside_gets_the_key_too(self):
        outside = CallLog(label="issue-edit")
        call, lines = self.run_failing_call(self.KEY, f"credential {self.KEY} rejected", log=outside)
        self.assertIs(call.call_log, outside)
        self.assertNotIn(self.KEY, lines[0])
        self.assertEqual(outside.secrets, [self.KEY])

    def test_the_key_is_also_replaced_inside_the_hint_values(self):
        body = {"error": {"status": "X", "details": [{"quotaId": f"Q-{self.KEY}"}]}}
        client = Client([ApiError(429, body)])
        call = make_gemini_llm(self.KEY, ["a"], max_retries=0, sleep=lambda s: None, client_factory=lambda: client, clock=Clock())
        with self.assertRaises(LLMError):
            call("p")
        self.assertNotIn(self.KEY, call.call_log.records[0].detail)
        self.assertIn("quotaId=Q-***", call.call_log.records[0].detail)

    def test_a_key_straddling_the_hint_cut_is_replaced_before_the_cut(self):
        """키가 힌트 값의 80자 경계에 걸쳐도(앞 70자 + 키) 자르기 전에 먼저 바꾸므로 키 조각이 남지 않는다 — 안쪽 본문을 훑을 때도 같다."""
        for details in ([{"quotaId": "Q" * 70 + self.KEY}], [{"violations": [{"quotaId": "Q" * 70 + self.KEY}]}]):
            body = {"error": {"status": "X", "details": details}}
            client = Client([ApiError(429, body)])
            call = make_gemini_llm(self.KEY, ["a"], max_retries=0, sleep=lambda s: None, client_factory=lambda: client, clock=Clock())
            with self.assertRaises(LLMError):
                call("p")
            head = call.call_log.records[0].detail.split(" | ", 1)[0]
            self.assertNotIn("fake-llm", head)
            self.assertIn("quotaId=" + "Q" * 70 + "***", head)

    def test_every_field_of_a_record_hides_the_real_key(self):
        log = CallLog(label=f"b-{self.KEY}", purpose=f"p-{self.KEY}", secrets=(self.KEY,))
        rec = log.success(f"m-{self.KEY}", 1, Resp(model_version=f"v-{self.KEY}"))
        self.assertEqual((rec.label, rec.purpose, rec.model, rec.served_model), ("b-***", "p-***", "m-***", "v-***"))
        self.assertNotIn(self.KEY, " ".join(log.summary_lines() + [call_line(rec)]))

    def test_short_keys_are_not_replaced_and_registering_twice_keeps_one_copy(self):
        call, lines = self.run_failing_call("abc", "the abc key")
        self.assertIn("the abc key", lines[0])
        self.assertEqual(call.call_log.secrets, [])
        edge = CallLog()
        edge.add_secret("abcde")                       # 5자: 일반 낱말과 겹칠 수 있어 등록하지 않는다
        edge.add_secret("abcdef")                      # 6자: 등록한다
        self.assertEqual(edge.secrets, ["abcdef"])
        log = CallLog(secrets=("secret-value-1",))
        log.add_secret("secret-value-1")
        log.add_secret("secret-value-2")
        log.add_secret("")
        log.add_secret(None)
        self.assertEqual(log.secrets, ["secret-value-1", "secret-value-2"])

    def test_the_error_text_given_to_callers_is_unchanged_by_the_replacement(self):
        """호출 기록용 가리기가 호출 결과를 바꾸면 안 된다: LLMError 문구는 예전 그대로 mask 만 거친다(패턴에 안 걸리는 값은 그대로)."""
        def failing_client():
            return Client([RuntimeError(f"credential {self.KEY} rejected")])
        legacy = legacy_make_gemini_llm(self.KEY, ["a"], max_retries=0, sleep=lambda s: None, client_factory=failing_client)
        new = make_gemini_llm(self.KEY, ["a"], max_retries=0, sleep=lambda s: None, client_factory=failing_client, clock=Clock())
        with self.assertRaises(LLMError) as old_ctx:
            legacy("p")
        with self.assertRaises(LLMError) as new_ctx:
            new("p")
        self.assertEqual(str(new_ctx.exception), str(old_ctx.exception))
        self.assertIn(self.KEY, str(new_ctx.exception))             # 알려진 한계(D-31): 패턴에 안 걸리는 값은 호출 결과의 문구에서는 그대로다

    def test_the_chance_module_registers_its_key_with_the_default_log(self):
        """실제 실행처럼 환경 변수에 키를 두고 generator 를 불러 오면 기본 기록 장치가 그 키를 안다 — 패턴에 안 걸리는 키도 로그에 안 나온다."""
        script = (
            "import generator as g\n"
            "class M:\n"
            "    def generate_content(self, model, contents):\n"
            "        raise RuntimeError('credential ' + g.API_KEY + ' rejected')\n"
            "class C:\n"
            "    models = M()\n"
            "g.get_client = lambda: C()\n"
            "g.MODEL_CANDIDATES = ['m1']\n"
            "print('SECRETS', g.CALL_LOG.secrets)\n"
            "try:\n"
            "    g.call_gemini_with_fallback('p')\n"
            "except RuntimeError as exc:\n"
            "    print('RAISED', str(exc).replace(chr(10), ' / '))\n")
        env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "PIPELINE_PAUSE", "DRY_RUN", "FIX_IMAGES")}
        env.update({"GEMINI_API_KEY": self.KEY, "PYTHONUTF8": "1"})
        proc = subprocess.run([sys.executable, "-c", script], cwd=str(REAL), env=env, capture_output=True, text=True,
                              encoding="utf-8", timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(self.KEY, proc.stdout.replace("SECRETS ['" + self.KEY + "']", ""))     # 알려 주는 첫 줄을 빼면 어디에도 없다
        self.assertIn("SECRETS ['" + self.KEY + "']", proc.stdout)
        self.assertIn("result=other", proc.stdout)
        self.assertIn("credential *** rejected", proc.stdout)


# ----------------------------------------------------------------------------
# 9) 기록은 best-effort: 기록·로그 출력이 실패해도 호출의 반환값·예외는 바뀌지 않는다(독립 검증 F-02)
# ----------------------------------------------------------------------------
class RaisingUsage:
    """응답 본문은 멀쩡하고 usage_metadata 만 읽으면 RuntimeError 가 나는 응답."""
    text = "응답 본문"
    model_version = "gemini-3.8-flash"

    @property
    def usage_metadata(self):
        raise RuntimeError("usage_metadata 를 읽을 수 없다")


class RaisingServed:
    text = "응답 본문"
    usage_metadata = Usage(1, 2, 3)

    @property
    def model_version(self):
        raise RuntimeError("model_version 을 읽을 수 없다")


class RaisingReason:
    """빈 응답인데 사유(candidates·prompt_feedback)를 읽으면 RuntimeError 가 난다."""
    text = ""

    @property
    def candidates(self):
        raise RuntimeError("candidates 를 읽을 수 없다")

    @property
    def prompt_feedback(self):
        raise RuntimeError("prompt_feedback 를 읽을 수 없다")


class BrokenAttrsError(Exception):
    """code·status·details 를 읽으면 RuntimeError 가 나는 예외(깨진 SDK 오류 객체)."""

    @property
    def code(self):
        raise RuntimeError("code 를 읽을 수 없다")

    @property
    def status(self):
        raise RuntimeError("status 를 읽을 수 없다")

    @property
    def details(self):
        raise RuntimeError("details 를 읽을 수 없다")


class ExplodingDict(dict):
    def items(self):
        raise RuntimeError("items 를 읽을 수 없다")


class ExplodingList(list):
    def __getitem__(self, index):
        raise RuntimeError("후보를 읽을 수 없다")


class InterruptingResponse:
    text = "응답 본문"

    @property
    def usage_metadata(self):
        raise KeyboardInterrupt()


def failing_sink(line):
    raise BrokenPipeError("로그 출력이 닫혔다")


SINK_ERRORS = (OSError("pipe"), BrokenPipeError("closed"), UnicodeEncodeError("cp949", "x", 0, 1, "illegal multibyte sequence"),
               ValueError("v"), RuntimeError("r"), LookupError("l"))


def raising_out(exc):
    def out(line):
        raise exc
    return out


class BestEffortRecordingTest(unittest.TestCase):
    def test_a_broken_log_sink_never_changes_what_a_successful_call_returns(self):
        for exc in SINK_ERRORS:
            call, client, sleeps = build([Resp("본문")], models=("a", "b"), out=raising_out(exc))
            self.assertEqual(call("p"), ("본문", "a"), repr(exc))
            self.assertEqual((len(client.models.calls), sleeps), (1, []))
            self.assertEqual(call.call_log.attempts, 1)          # 줄은 못 냈어도 기록은 남는다

    def test_a_broken_log_sink_does_not_change_retry_fallback_or_the_final_error(self):
        for exc in SINK_ERRORS:
            call, client, sleeps = build([ApiError(429, quota_body()), Resp("본문")], models=("a",), out=raising_out(exc))
            self.assertEqual(call("p"), ("본문", "a"), repr(exc))
            self.assertEqual(sleeps, [2])
            messages = []
            for out in (raising_out(exc), None):
                failing, _, _ = build([ApiError(503)] * 6, models=("a", "b"), out=out)
                with self.assertRaises(LLMError) as ctx:
                    failing("p")
                messages.append(str(ctx.exception))
                self.assertEqual(failing.call_log.attempts, 6)
            self.assertEqual(messages[0], messages[1], repr(exc))

    def test_the_record_is_returned_and_kept_when_the_sink_fails(self):
        log = CallLog(label="x", out=failing_sink)
        rec = log.success("a", 1.5, Resp(model_version="v", usage=Usage(1, 2, 3)))
        self.assertIs(rec, log.records[0])
        self.assertEqual((rec.model, rec.served_model, rec.seconds, rec.total_tokens), ("a", "v", 1.5, 3))
        self.assertEqual(log.failure("a", 1, RuntimeError("e")).outcome, "other")
        self.assertEqual(log.empty("a", 1, Resp(text="")).outcome, "empty")
        self.assertEqual((log.attempts, log.failed), (3, 2))

    def test_unreadable_response_fields_cost_only_those_fields(self):
        for response, expected in ((RaisingUsage(), ("gemini-3.8-flash", None, None, None)),
                                   (RaisingServed(), ("", 1, 2, 3))):
            call, _, _ = build([response], models=("a",))
            self.assertEqual(call("p"), ("응답 본문", "a"))
            rec = call.call_log.records[0]
            self.assertEqual((rec.served_model, rec.prompt_tokens, rec.candidate_tokens, rec.total_tokens), expected)
            self.assertEqual(rec.outcome, "ok")

    def test_an_empty_answer_whose_reason_cannot_be_read_is_still_recorded_as_empty(self):
        call, _, _ = build([RaisingReason(), Resp("본문")], models=("a", "b"))
        self.assertEqual(call("p"), ("본문", "b"))
        self.assertEqual([r.outcome for r in call.call_log.records], ["empty", "ok"])
        self.assertEqual(call.call_log.records[0].detail, "빈 응답")

    def test_a_failure_whose_attributes_cannot_be_read_is_still_classified_and_recorded(self):
        log = CallLog(label="x")
        rec = log.failure("a", 1, BrokenAttrsError("깨진 오류"))
        self.assertEqual(rec.outcome, "other")
        self.assertIn("BrokenAttrsError", rec.detail)
        self.assertIn("깨진 오류", rec.detail)

    def test_a_failure_that_breaks_the_body_walk_keeps_the_count_and_the_outcome(self):
        """_field 가 아니라 본문을 훑는 코드 자체가 실패하는 경우: 기록 전체의 마지막 방어선이 받아 최소 기록을 남긴다."""
        err = ApiError(429, ExplodingDict({"error": {"status": "RESOURCE_EXHAUSTED", "message": "m", "details": []}}))
        log = CallLog(label="x", purpose="p")
        rec = log.failure("gemini-3.8-flash", 2.5, err)
        self.assertEqual((rec.outcome, rec.model, rec.label, rec.purpose, rec.seconds), ("429", "gemini-3.8-flash", "x", "p", 2.5))
        self.assertEqual(rec.detail, llm_mod.PARTIAL_DETAIL)
        self.assertEqual((log.attempts, log.failed), (1, 1))
        empty = log.empty("a", 1, Resp(text="", candidates=ExplodingList([Candidate("STOP")])))
        self.assertEqual((empty.outcome, empty.detail), ("empty", llm_mod.PARTIAL_DETAIL))

    def test_the_last_line_of_defence_also_covers_a_value_that_cannot_be_a_number(self):
        log = CallLog(label="x")
        rec = log.success("a", None, Resp())
        self.assertEqual((rec.outcome, rec.seconds, rec.detail), ("ok", 0.0, llm_mod.PARTIAL_DETAIL))
        self.assertEqual(log.attempts, 1)
        lines = []
        log.configure(out=lines.append)
        log.success("a", "abc", Resp())
        self.assertEqual(len(lines), 1)
        self.assertIn(f"detail={llm_mod.PARTIAL_DETAIL}", lines[0])

    def test_classification_failure_falls_back_to_other_inside_the_log(self):
        with mock.patch.object(llm_mod, "classify_failure", side_effect=RuntimeError("분류 실패")):
            log = CallLog()
            rec = log.failure("a", 1, RuntimeError("x"))
        self.assertEqual((rec.outcome, log.attempts), ("other", 1))

    def test_interrupts_and_exits_are_never_swallowed(self):
        for exc in (KeyboardInterrupt(), SystemExit(3)):
            log = CallLog(out=raising_out(exc))
            with self.assertRaises(type(exc)):
                log.success("a", 1, Resp())
            with self.assertRaises(type(exc)):
                log.failure("a", 1, RuntimeError("e"))
            call, _, _ = build([Resp("본문")], models=("a",), out=raising_out(exc))
            with self.assertRaises(type(exc)):
                call("p")
        with self.assertRaises(KeyboardInterrupt):
            CallLog().success("a", 1, InterruptingResponse())

    def test_a_broken_error_object_keeps_the_old_behaviour_and_is_still_counted(self):
        """`code` 를 읽으면 터지는 예외: 재시도 판단(_is_transient)은 옛날부터 그 RuntimeError 를 그대로 내보낸다. 기록은 그 전에 남는다."""
        call, _, _ = build([BrokenAttrsError("깨진 오류")], models=("a",))
        with self.assertRaises(RuntimeError) as ctx:
            call("p")
        self.assertEqual(str(ctx.exception), "code 를 읽을 수 없다")
        self.assertEqual((call.call_log.attempts, call.call_log.failed), (1, 1))
        no_retry, _, _ = build([BrokenAttrsError("깨진 오류"), Resp("본문")], models=("a", "b"), max_retries=0)
        self.assertEqual(no_retry("p"), ("본문", "b"))


class BestEffortChanceTest(ChanceBase):
    def test_a_broken_sink_does_not_change_the_response_the_counts_or_the_error(self):
        for exc in SINK_ERRORS:
            self.log.out = raising_out(exc)
            g.GEMINI_CALLS.update(attempts=0, failed=0)
            self.fake_client([ApiError(429, quota_body()), Resp("본문")])
            with mock.patch.object(g, "MODEL_CANDIDATES", ["a", "b"]):
                response, out = capture(g.call_gemini_with_fallback, "프롬프트")
            self.assertEqual(response.text, "본문", repr(exc))
            self.assertEqual(g.GEMINI_CALLS, {"attempts": 2, "failed": 1})
            self.assertIn("Gemini 모델 호출 성공: b", out)
        self.log.out = failing_sink
        self.fake_client([ApiError(503)] * 4)
        with self.assertRaises(RuntimeError) as ctx:
            capture(g.call_gemini_with_fallback, "프롬프트")
        self.assertTrue(ctx.exception.args[0].startswith("모든 Gemini 모델 호출 실패\ngemini-3.8-flash: 503"))

    def test_a_response_with_unreadable_fields_is_still_returned(self):
        self.fake_client([RaisingUsage()])
        response, _ = capture(g.call_gemini_with_fallback, "프롬프트")
        self.assertEqual(response.text, "응답 본문")
        self.assertEqual(self.log.records[0].outcome, "ok")

    def test_a_broken_error_object_moves_on_to_the_next_model_as_before(self):
        self.fake_client([BrokenAttrsError("깨진 오류"), Resp("본문")])
        with mock.patch.object(g, "MODEL_CANDIDATES", ["a", "b"]):
            response, _ = capture(g.call_gemini_with_fallback, "프롬프트")
        self.assertEqual(response.text, "본문")
        self.assertEqual([r.outcome for r in self.log.records], ["other", "ok"])


def hostile_pool(with_secret=True):
    """with_secret: 비밀 모양 문구를 담은 오류를 넣는다(Chance 의 옛 구현은 오류 문구를 가리지 않았으므로 Chance 비교에서는 뺀다)."""
    pool = [lambda: Resp("본문"), lambda: Resp(""), lambda: RaisingUsage(), lambda: RaisingServed(), lambda: RaisingReason(),
            lambda: ApiError(429, quota_body()), lambda: ApiError(503), lambda: ApiError(404), lambda: RuntimeError("boom"),
            lambda: BrokenAttrsError("깨진 오류"),
            lambda: ApiError(429, ExplodingDict({"error": {"status": "RESOURCE_EXHAUSTED", "message": "m", "details": []}})),
            lambda: Resp("", candidates=ExplodingList([Candidate("STOP")])), lambda: mock.Mock(text="응답")]
    if with_secret:
        pool.append(lambda: RuntimeError(f"api_key={FAKE_KEY}"))
    return pool


class HostileDifferentialTest(unittest.TestCase):
    """깨진 응답·오류 객체와 고장 난 로그 출력을 섞어도 옛 구현과 반환값·예외·호출 순서·대기가 같다(기록은 측정 전용)."""

    @staticmethod
    def outcome(call, prompt):
        try:
            return ("ok",) + tuple(call(prompt))
        except LLMError as exc:
            return ("llm-error", str(exc))
        except Exception as exc:  # noqa: BLE001 - 깨진 오류 객체가 옛 구현에서도 내보내는 예외까지 같은지 본다
            return ("raised", type(exc).__name__, str(exc))

    def test_make_gemini_llm_matches_the_legacy_implementation(self):
        pool = hostile_pool()
        for seed in range(300):
            rng = random.Random(seed)
            models = rng.sample(["a", "b", "c", "d"], rng.randint(1, 4))
            retries = rng.choice([0, 1, 2])
            steps = [pool[rng.randrange(len(pool))]() for _ in range(16)]
            outcomes = []
            for new in (False, True):
                client, sleeps = Client(list(steps)), []
                if new:
                    call = make_gemini_llm("키", models, retries, sleep=sleeps.append, client_factory=lambda c=client: c, clock=Clock(),
                                           log=CallLog(out=failing_sink))
                else:
                    call = legacy_make_gemini_llm("키", models, retries, sleep=sleeps.append, client_factory=lambda c=client: c)
                outcomes.append((self.outcome(call, "프롬프트"), client.models.calls, sleeps))
            self.assertEqual(outcomes[0], outcomes[1], f"seed {seed}")

    def test_chance_call_matches_the_legacy_implementation(self):
        pool = hostile_pool(with_secret=False)
        for seed in range(200):
            rng = random.Random(seed)
            models = rng.sample(["a", "b", "c", "d"], rng.randint(1, 4))
            steps = [pool[rng.randrange(len(pool))]() for _ in range(6)]
            results = []
            for new in (False, True):
                client = Client(list(steps))
                buf = io.StringIO()
                log = CallLog(label="chance", purpose="post", out=failing_sink)
                with contextlib.redirect_stdout(buf), mock.patch.object(g, "get_client", return_value=client), \
                        mock.patch.object(g, "MODEL_CANDIDATES", models), mock.patch.object(g, "CALL_LOG", log), \
                        mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0}):
                    try:
                        if new:
                            value = ("ok", g.call_gemini_with_fallback("p").text)
                        else:
                            value = ("ok", legacy_call_gemini_with_fallback("p", g.get_client, models, g.GEMINI_CALLS, g._one_line).text)
                    except Exception as exc:  # noqa: BLE001
                        value = ("err", type(exc).__name__, str(exc))
                    calls = dict(g.GEMINI_CALLS)
                results.append((value, client.models.calls, calls, buf.getvalue()))
            self.assertEqual(results[0], results[1], f"seed {seed}")


# ----------------------------------------------------------------------------
# 10) Chance: 오류 문구가 키를 담아도 예외 문구·로그·마지막 줄에 나가지 않는다(독립 검증 F-06)
# ----------------------------------------------------------------------------
class ChanceLeakTest(ChanceBase):
    REAL_KEY = "fake-gemini-key-0123456789"      # 비밀 패턴에 걸리지 않는 값

    def run_all_models_failing(self, text, key=None):
        self.fake_client([RuntimeError(text)] * 4)
        buf = io.StringIO()
        with mock.patch.object(g, "API_KEY", key), contextlib.redirect_stdout(buf), self.assertRaises(RuntimeError) as ctx:
            g.call_gemini_with_fallback("프롬프트")
        return ctx.exception.args[0], buf.getvalue()

    def test_pattern_secrets_in_model_errors_are_masked_in_the_raised_error(self):
        message, out = self.run_all_models_failing(f"bad request key={FAKE_KEY} and {FAKE_TOKEN} and {FAKE_NEW_KEY}")
        for secret in (FAKE_KEY, FAKE_TOKEN, FAKE_NEW_KEY, FAKE_KEY[:20], FAKE_TOKEN[:20], FAKE_NEW_KEY[:20]):
            self.assertNotIn(secret, message)
            self.assertNotIn(secret, out)
        self.assertTrue(message.startswith("모든 Gemini 모델 호출 실패\ngemini-3.8-flash: bad request"), message)
        self.assertEqual(message.count("\n"), MODEL_COUNT)             # 모델마다 한 줄 — 형식은 그대로

    def test_the_real_key_is_replaced_even_when_no_pattern_matches_it(self):
        message, out = self.run_all_models_failing(f"credential {self.REAL_KEY} rejected", key=self.REAL_KEY)
        self.assertNotIn(self.REAL_KEY, message)
        self.assertNotIn(self.REAL_KEY, out)
        self.assertIn("gemini-3.8-flash: credential *** rejected", message)

    def test_without_a_secret_the_error_text_is_exactly_the_old_one(self):
        message, _ = self.run_all_models_failing("plain failure text")
        self.assertEqual(message, "모든 Gemini 모델 호출 실패\n" + "\n".join(f"{m}: plain failure text" for m in g.MODEL_CANDIDATES))

    def test_the_final_failure_line_is_masked(self):
        for text, key in ((f"요청 실패 {FAKE_KEY} / key={FAKE_TOKEN}", None), (f"요청 실패 {self.REAL_KEY}", self.REAL_KEY)):
            def boom(text=text):
                raise ValueError(text)
            out = io.StringIO()
            with mock.patch.object(g, "main", boom), mock.patch.object(g, "API_KEY", key), contextlib.redirect_stdout(out):
                with self.assertRaises(ValueError):
                    g.run_cli()
            shown = out.getvalue()
            for secret in (FAKE_KEY, FAKE_TOKEN, self.REAL_KEY):
                self.assertNotIn(secret, shown)
            self.assertIn("작업 실패: ValueError: 요청 실패 ***", shown)

    def test_the_final_failure_line_is_still_cut_at_600_after_masking(self):
        def boom():
            raise ValueError("가" * 2000)
        out = io.StringIO()
        with mock.patch.object(g, "main", boom), contextlib.redirect_stdout(out):
            with self.assertRaises(ValueError):
                g.run_cli()
        line = next(line for line in out.getvalue().splitlines() if line.startswith("작업 실패:"))
        self.assertEqual(len(line), len("작업 실패: ValueError: ") + 600)

    def test_the_zero_count_line_is_part_of_the_usage_lines(self):
        self.assertEqual(g.usage_lines(), ["Gemini 호출: 0회(실패 0회)"])
        g.GEMINI_CALLS.update(attempts=2, failed=1)
        self.log.failure("m", 1, RuntimeError("x"))
        self.assertEqual(g.usage_lines()[0], "Gemini 호출: 2회(실패 1회)")
        self.assertEqual(g.usage_lines()[1], "Gemini 실패 내역: 기타 1회")


if __name__ == "__main__":
    unittest.main()
