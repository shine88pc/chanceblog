"""Gemini 호출 시간 상한(D-83) 시험: 서버가 응답 없이 연결을 붙잡아도 호출 하나가 상한 안에 끝나고, 같은 모델을 다시 부르지 않고 다음 모델로 넘어가며,
멈춘 모델은 같은 호출 객체의 다음 호출에서 맨 뒤로 간다. 네트워크도 SDK 도 쓰지 않는다(가짜 클라이언트, 상한은 0.3초로 줄여 쓴다).
"""
import inspect
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import _bootstrap  # noqa: F401
from pipeline import llm
from pipeline.llm import CallTimeout, LLMError, make_gemini_llm

QUICK = 0.3     # 시험용 호출 상한(초): 가짜 클라이언트가 즉시 답하는 호출이 느린 실행기에서도 상한 안에 끝날 만큼은 넉넉하게


class FakeClient:
    """models.generate_content(model, contents) 를 가진 가짜 클라이언트. plan: 모델 이름 → 글자(성공) · 예외(실패) · "hang"(풀어 줄 때까지 붙잡다 연결이 끊긴 것처럼 실패)."""

    def __init__(self, plan):
        self.plan, self.calls, self.release = plan, [], threading.Event()
        self.models = self

    def generate_content(self, model, contents):
        self.calls.append(model)
        action = self.plan[model]
        if action == "hang":
            self.release.wait(10)
            raise OSError("server disconnected")
        if isinstance(action, BaseException):
            raise action
        return SimpleNamespace(text=action, model_version=model, usage_metadata=None)


class TimeoutBase(unittest.TestCase):
    def llm(self, plan, models=("m1", "m2", "m3"), max_retries=2, call_timeout=QUICK):
        client = FakeClient(plan)
        self.addCleanup(client.release.set)      # 시험이 끝나면 붙잡힌 가짜 호출을 풀어 스레드가 남지 않게 한다
        sleeps = []
        call = make_gemini_llm("키", list(models), max_retries, sleep=sleeps.append, client_factory=lambda: client, call_timeout=call_timeout)
        return call, client, sleeps


class RunWithTimeoutTest(unittest.TestCase):
    def test_a_quick_call_returns_its_value_and_a_failing_call_reraises_the_same_exception(self):
        self.assertEqual(llm._run_with_timeout(lambda: 7, 1), 7)
        boom = ValueError("boom")

        def failing():
            raise boom

        with self.assertRaises(ValueError) as caught:
            llm._run_with_timeout(failing, 1)
        self.assertIs(caught.exception, boom)               # 호출한 쪽이 분류할 수 있게 같은 예외 객체다

    def test_a_call_that_never_finishes_in_time_raises_call_timeout_and_the_worker_is_a_daemon(self):
        release = threading.Event()
        self.addCleanup(release.set)
        started = time.monotonic()
        with self.assertRaises(CallTimeout):
            llm._run_with_timeout(lambda: release.wait(10), QUICK)
        self.assertLess(time.monotonic() - started, 6)       # 호출이 상한 근처에서 돌아왔다(가짜 호출은 10초 붙잡힌다 — 끝까지 기다렸다면 10초 이상, 느린 실행기에서도 흔들리지 않게 넉넉히 6초)
        workers = [thread for thread in threading.enumerate() if thread.name == "gemini-call"]
        self.assertTrue(workers and all(thread.daemon for thread in workers))     # 프로세스 종료를 막지 않는다
        self.assertTrue(issubclass(CallTimeout, TimeoutError))

    def test_without_a_limit_the_call_runs_inline_in_the_calling_thread(self):
        seen = []
        for seconds in (None, 0):
            llm._run_with_timeout(lambda: seen.append(threading.current_thread()), seconds)
        self.assertEqual(seen, [threading.current_thread()] * 2)

    def test_the_default_limit_is_long_enough_for_an_article_and_short_enough_for_a_hang(self):
        self.assertTrue(90 <= llm.CALL_TIMEOUT_SECONDS <= 180)

    def test_the_wait_is_exactly_the_limit_without_extra_margin(self):
        """기다리는 시간이 상한 그대로인지(2배·덧셈 없이)를 시간을 재지 않고 `join` 인자로 확인한다 — 시간 단언은 느린 실행기에서 흔들린다."""
        release = threading.Event()
        self.addCleanup(release.set)
        waits = []
        real_join = threading.Thread.join

        def spy(thread, timeout=None):
            if thread.name == "gemini-call":
                waits.append(timeout)
            return real_join(thread, timeout)

        with mock.patch.object(threading.Thread, "join", spy):
            with self.assertRaises(CallTimeout):
                llm._run_with_timeout(lambda: release.wait(10), QUICK)
        self.assertEqual(waits, [QUICK])

    def test_system_exit_and_keyboard_interrupt_reach_the_caller_instead_of_vanishing_with_the_worker_thread(self):
        for exc_type in (SystemExit, KeyboardInterrupt):
            def failing(exc_type=exc_type):
                raise exc_type()

            with self.assertRaises(exc_type):
                llm._run_with_timeout(failing, 1)


class FallbackAfterTimeoutTest(TimeoutBase):
    def test_a_hung_model_is_given_up_once_and_the_next_model_answers_without_retrying_the_hung_one(self):
        call, client, sleeps = self.llm({"m1": "hang", "m2": "글 본문", "m3": "쓰지 않음"})
        started = time.monotonic()
        text, model = call("프롬프트")
        self.assertEqual((text, model), ("글 본문", "m2"))
        self.assertEqual(client.calls, ["m1", "m2"])            # 멈춘 모델은 한 번만 불렀다(재시도 없음), 세 번째 모델은 필요 없었다
        self.assertEqual(sleeps, [])                             # 재시도 대기도 없었다
        self.assertLess(time.monotonic() - started, 6)

    def test_the_hung_model_goes_to_the_back_of_the_line_for_the_next_call_of_the_same_llm_object(self):
        call, client, _sleeps = self.llm({"m1": "hang", "m2": "첫 응답", "m3": "x"})
        self.assertEqual(call("글")[1], "m2")
        client.calls.clear()
        text, model = call("검색어")
        self.assertEqual((text, model), ("첫 응답", "m2"))
        self.assertEqual(client.calls, ["m2"])                   # 두 번째 호출은 멈춘 m1 을 건너뛰고 바로 m2 로 간다
        client.plan["m2"] = RuntimeError("권한 없음")
        client.plan["m3"] = "마지막 모델"
        client.calls.clear()
        self.assertEqual(call("또")[1], "m3")
        self.assertEqual(client.calls, ["m2", "m3"])             # 건강한 모델이 모두 실패해야 멈춘 m1 까지 돌아온다(그 전에 m3 가 답했다)

    def test_when_every_model_hangs_the_call_fails_after_one_wait_per_model(self):
        call, client, sleeps = self.llm({"m1": "hang", "m2": "hang", "m3": "hang"})
        started = time.monotonic()
        with self.assertRaises(LLMError) as caught:
            call("프롬프트")
        self.assertEqual(client.calls, ["m1", "m2", "m3"])
        self.assertEqual(sleeps, [])
        self.assertLess(time.monotonic() - started, 6)
        self.assertEqual(str(caught.exception).count("CallTimeout"), 3)       # 어느 모델이 시간 상한을 넘겼는지 오류 문구에 남는다

    def test_dead_models_are_tried_last_but_still_tried_when_nothing_else_answers(self):
        call, client, _sleeps = self.llm({"m1": "hang", "m2": RuntimeError("실패"), "m3": RuntimeError("실패")})
        with self.assertRaises(LLMError):
            call("첫 호출")
        client.plan["m1"] = "되살아남"
        client.calls.clear()
        self.assertEqual(call("둘째 호출")[1], "m1")
        self.assertEqual(client.calls, ["m2", "m3", "m1"])       # 멈췄던 m1 은 맨 뒤지만 기회가 없어지지는 않는다

    def test_a_timeout_is_never_retried_on_the_same_model_even_if_the_error_text_looks_transient(self):
        """멈춘 서버를 같은 모델로 다시 부르지 않는 것은 오류 문구가 우연히 일시 오류처럼 보여도 지켜진다(시간 상한 처리가 `_is_transient` 에 기대지 않는다)."""
        call, client, sleeps = self.llm({"m1": "hang", "m2": "응답", "m3": "x"})
        with mock.patch.object(llm, "_is_transient", return_value=True):
            self.assertEqual(call("글")[1], "m2")
        self.assertEqual((client.calls, sleeps), (["m1", "m2"], []))

    def test_transient_errors_are_still_retried_as_before(self):
        class Overloaded(Exception):
            code = 503

        calls = []
        plan = {"m1": Overloaded("unavailable"), "m2": "x"}
        client = FakeClient(plan)

        def flaky(model, contents):
            calls.append(model)
            if len(calls) == 1:
                raise Overloaded("unavailable")
            return SimpleNamespace(text="두 번째 시도", model_version=model, usage_metadata=None)

        client.generate_content = flaky
        sleeps = []
        call = make_gemini_llm("키", ["m1", "m2"], 2, sleep=sleeps.append, client_factory=lambda: client, call_timeout=QUICK)
        self.assertEqual(call("글"), ("두 번째 시도", "m1"))
        self.assertEqual((calls, sleeps), (["m1", "m1"], [2]))

    def test_no_limit_means_the_old_behaviour(self):
        call, client, _sleeps = self.llm({"m1": "응답", "m2": "x"}, call_timeout=None)
        self.assertEqual(call("글"), ("응답", "m1"))
        self.assertEqual(client.calls, ["m1"])

    def test_the_timeout_is_recorded_as_a_failed_call_in_the_call_log(self):
        call, _client, _sleeps = self.llm({"m1": "hang", "m2": "응답", "m3": "x"})
        call("글")
        lines = "\n".join(call.call_log.summary_lines())
        self.assertIn("2회", lines)          # 요청 두 번(멈춘 m1 · 성공한 m2)이 기록에 남는다
        self.assertIn("실패 1회", lines)


class DefaultLimitTest(unittest.TestCase):
    def test_callers_that_pass_no_limit_get_the_module_default(self):
        """`pipeline/run.py`·`pipeline/edits/runner.py` 는 call_timeout 을 넘기지 않아 운영의 상한은 시그니처 기본값 한 줄에만 달려 있다 — 그 값을 여기서 고정한다."""
        self.assertEqual(inspect.signature(make_gemini_llm).parameters["call_timeout"].default, llm.CALL_TIMEOUT_SECONDS)
        seen = []
        real = llm._run_with_timeout

        def spy(fn, seconds):
            seen.append(seconds)
            return real(fn, seconds)

        client = FakeClient({"m1": "응답"})
        call = make_gemini_llm("키", ["m1"], 0, sleep=lambda s: None, client_factory=lambda: client)    # call_timeout 을 넘기지 않는다(운영의 호출 방식)
        with mock.patch.object(llm, "_run_with_timeout", spy):
            self.assertEqual(call("글"), ("응답", "m1"))
        self.assertEqual(seen, [llm.CALL_TIMEOUT_SECONDS])


if __name__ == "__main__":
    unittest.main()
