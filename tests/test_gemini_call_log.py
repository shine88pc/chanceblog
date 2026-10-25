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
import json
import os
import random
import tempfile
import time
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
from pipeline.edits import runner
from pipeline.llm import (CallLog, LLMError, call_line, classify_failure, empty_detail, failure_code, failure_detail,
                          make_gemini_llm, purpose, served_model, token_usage)
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
        violations = [{"quotaId": f"Q{i}", "quotaMetric": f"M{i}"} for i in range(5)]
        body = {"error": {"status": "RESOURCE_EXHAUSTED", "details": [
            {"violations": violations}, {"retryDelay": "5s"}, {"retryDelay": "5s"}, {"retryDelay": 7}]}}
        err = ApiError(429, body)
        head = failure_detail(err).split(" | ", 1)[0]
        self.assertIn("quotaId=Q0 quotaId=Q1 retryDelay=5s retryDelay=7 quotaMetric=M0 quotaMetric=M1", head)
        self.assertNotIn("Q2", head)
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
        with self.real_llm([ApiError(429, quota_body())] * 12):
            code, out = self.go(env=self.env(), llm=None)
        self.assertEqual(code, 1)
        self.assertIn("[SKIP] code=LLM_FAILED", out)
        text = self.summary()
        self.assertIn("**LLM_FAILED**", text)
        self.assertIn("- Gemini 호출: 12회(실패 12회)", text)
        self.assertIn("- Gemini 실패 내역: 429(한도 초과) 12회", text)
        self.assertEqual(len(gemini_lines(out)), 12)
        self.assertTrue(all(f"quotaId={DAY_QUOTA_ID}" in line for line in gemini_lines(out)))
        self.assertEqual(self.history()[-1]["status"], "llm_failed")

    def test_topic_expansion_requests_are_labelled_and_a_failure_keeps_the_count(self):
        self.use_all_seeds()
        with self.real_llm([ApiError(503)] * 12):
            code, out = self.go(env=self.env(), llm=None)
        self.assertEqual(code, 1)
        self.assertIn("[SKIP] code=EXPAND_FAILED", out)
        lines = gemini_lines(out)
        self.assertEqual(len(lines), 12)
        self.assertTrue(all("purpose=topic-expansion" in line and "result=5xx" in line for line in lines))
        self.assertIn("- Gemini 호출: 12회(실패 12회)", self.summary())
        self.assertIn("- Gemini 실패 내역: 5xx(서버 오류) 12회", self.summary())

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
        self.assertIn("gemini-3.7-flash→gemini-3.7-flash 1회", text)
        self.assertEqual(self.history()[-1]["model"], "gemini-3.7-flash")

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

    def test_all_models_failing_raises_the_same_error_and_records_every_request(self):
        self.fake_client([ApiError(429, quota_body())] * 4)
        with self.assertRaises(RuntimeError) as ctx:
            capture(g.call_gemini_with_fallback, "프롬프트")
        self.assertTrue(ctx.exception.args[0].startswith("모든 Gemini 모델 호출 실패\ngemini-3.8-flash: 429 RESOURCE_EXHAUSTED."))
        self.assertEqual(g.GEMINI_CALLS, {"attempts": 4, "failed": 4})
        self.assertEqual(self.log.attempts, 4)
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

    def test_no_calls_means_no_gemini_lines_as_before(self):
        text = g.render_run_summary("schedule", self.now(), 9, {"outcome": "ALL_LANES_EMPTY", "lanes": [],
                                                                "gemini_calls": {"attempts": 0, "failed": 0}, "gemini_notes": []})
        self.assertNotIn("Gemini", text)

    def test_failure_summary_keeps_the_call_count_when_every_model_failed(self):
        """모든 모델이 실패해 RuntimeError 로 끝난 실행: 예전 요약에는 '실패 — RuntimeError' 한 줄뿐이라 호출 수가 사라졌다."""
        self.fake_client([ApiError(429, quota_body())] * 4)
        with self.assertRaises(RuntimeError) as ctx:
            capture(g.call_gemini_with_fallback, "프롬프트")
        text = g.failure_summary(ctx.exception)
        self.assertTrue(text.startswith("### Chance_Blog 실행 요약\n- 결과: **실패** — RuntimeError (원인은 이 단계의 로그를 보세요)"))
        self.assertIn("- Gemini 호출: 4회(실패 4회)", text)
        self.assertIn("- Gemini 실패 내역: 429(한도 초과) 4회", text)

    def test_failure_summary_without_any_call_is_the_old_two_lines(self):
        self.assertEqual(g.failure_summary(ValueError("x")),
                         "### Chance_Blog 실행 요약\n- 결과: **실패** — ValueError (원인은 이 단계의 로그를 보세요)")

    def test_run_cli_writes_the_failure_summary_with_the_calls_and_reraises(self):
        self.fake_client([ApiError(503)] * 4)

        def boom():
            g.call_gemini_with_fallback("프롬프트")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "summary.md"
            with mock.patch.object(g, "main", boom), mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(target)}):
                with self.assertRaises(RuntimeError):
                    capture(g.run_cli)
            text = target.read_text(encoding="utf-8")
        self.assertIn("**실패** — RuntimeError", text)
        self.assertIn("- Gemini 호출: 4회(실패 4회)", text)
        self.assertIn("5xx(서버 오류) 4회", text)

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
        client = self.fake_gemini([ApiError(429, quota_body())] * 12)
        self.write_issue(page_body(edit=self.LAYOUT, after="둘째 문단 아래에 강조 문장을 넣어 주세요"))
        code, out = self.run_main()
        self.assertEqual(code, runner.EXIT_INFRA)
        self.assertEqual(len(client.models.calls), 12)
        text = self.summary()
        self.assertIn("**error**", text)
        self.assertIn("- Gemini 호출: 12회(실패 12회)", text)
        self.assertIn("- Gemini 실패 내역: 429(한도 초과) 12회", text)
        lines = runner_gemini_lines(out)
        self.assertEqual(len(lines), 12)
        self.assertTrue(all(f"quotaId={DAY_QUOTA_ID}" in line and "retryDelay=37s" in line for line in lines))   # 300자 안에 한도 구분 필드가 남는다
        self.assertTrue(all(len(line) <= 300 for line in lines))
        self.assertIn(TAG + "   * Gemini 호출: 12회(실패 12회)", out.splitlines())
        for line in out.splitlines():
            self.assertTrue(line.startswith(TAG), line)

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


if __name__ == "__main__":
    unittest.main()
