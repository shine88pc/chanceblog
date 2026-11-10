"""운영자 결정 007 반영 시험(관문 쪽) — AI 입력 거부와 호출 예산.

- `egress.check_ai_input`: ai_use NEVER 인 Provider 의 자료는 AI 처리기 정책의 input_scope 와 상관없이 **항상 거부**한다. BY_CELL 은 ACTIVE 이고 범위가 정책의 input_scope 일 때만 허용한다.
- `egress.run_call_cap`·`CallBudget`·`budgeted`·`budget_for`: 한 실행 안의 호출 상한(레지스트리 호출 한도에서 계산)·실패 3회 건너뜀·재시도 상한·403·429 중지·404 주소 중지·같은 주소 성공 응답 재사용·
  호출 전 선행 조건(하루·주간 상한이 이미 막았으면 호출 0). 새 영구 상태를 만들지 않는다.

네트워크를 쓰지 않는다 — 가짜 opener 와 가짜 전송 처리기만 쓴다."""
import copy
import json
import unittest
import urllib.error

import _bootstrap  # noqa: F401
from pipeline import egress, source_registry as sr
from source_registry_helpers import GOOD_HOST, TODAY, good_provider, registry_data, with_cell
from test_egress import FakeHttps
from test_source_registry_007 import NOAA_PATHS, own_limit, rate_object

ROOT = _bootstrap.ROOT
SCOPE = sr.AI_FIXED["input_scope"]


def registry_of(*providers):
    return sr.build_registry(registry_data(*providers), TODAY)


class CheckAiInputTest(unittest.TestCase):
    def deny(self, provider_id, scope, registry):
        with self.assertRaises(egress.AiInputDenied) as caught:
            egress.check_ai_input(provider_id, scope, registry)
        return caught.exception

    def test_a_by_cell_provider_passes_only_when_active_and_in_the_policy_scope(self):
        registry = registry_of(good_provider())
        self.assertIsNone(egress.check_ai_input("fixture_stats", SCOPE, registry))
        for scope in ("FULL_TEXT", "SIGNAL", "", None, 5, ["x"], SCOPE.lower(), SCOPE + " "):
            with self.subTest(scope=scope):
                self.deny("fixture_stats", scope, registry)

    def test_a_provider_that_is_not_active_never_passes(self):
        for ai_use in ("BY_CELL", "NEVER"):
            registry = registry_of(good_provider(enabled=False, ai_use=ai_use))
            self.deny("fixture_stats", SCOPE, registry)
        expired = registry_of(good_provider())                                                   # 오늘이 점검 기한을 넘기면 ACTIVE 가 아니다
        late = sr.build_registry(registry_data(good_provider()), "2027-03-01")
        self.assertIsNone(egress.check_ai_input("fixture_stats", SCOPE, expired))
        self.deny("fixture_stats", SCOPE, late)

    def test_never_is_refused_for_every_scope_even_the_policy_scope_and_even_when_active(self):
        provider = good_provider(ai_use="NEVER")
        registry = registry_of(provider)
        self.assertEqual([p.provider_id for p in registry.active_providers()], ["fixture_stats"])   # ACTIVE 인데도
        for scope in (SCOPE, "FULL_TEXT", "", None, "ANY"):
            with self.subTest(scope=scope):
                error = self.deny("fixture_stats", scope, registry)
                self.assertIn("NEVER", error.reason)
                self.assertIn("input_scope", error.reason)                                         # AI 처리기 정책의 범위와 상관없이 거부한다고 말한다
        denied = with_cell(good_provider(ai_use="NEVER"), "ai_input", state="DENIED", basis="EXPLICIT")
        self.deny("fixture_stats", SCOPE, registry_of(denied))                                       # ai_input 이 DENIED 여도(판정에서 빠져 ACTIVE) 자료는 AI 에 안 간다

    def test_unknown_providers_and_missing_registries_are_refused(self):
        registry = registry_of(good_provider())
        for provider_id in ("nobody", "", None, 7, ["fixture_stats"], "FIXTURE_STATS"):
            with self.subTest(provider_id=provider_id):
                self.deny(provider_id, SCOPE, registry)
        self.deny("fixture_stats", SCOPE, None)

    def test_the_denial_names_only_the_provider_and_the_scope_never_the_data(self):
        error = self.deny("fixture_stats", "FULL_TEXT", registry_of(good_provider()))
        self.assertEqual((error.provider_id, error.scope), ("fixture_stats", "FULL_TEXT"))
        self.assertIn("fixture_stats", str(error))
        self.assertIn("FULL_TEXT", str(error))
        weird = self.deny("not a provider id!", "secret-token=abc 123", registry_of(good_provider()))
        self.assertEqual((weird.provider_id, weird.scope), ("(형식 오류)", "(형식 오류)"))             # 이상한 글자는 문구에 싣지 않는다
        self.assertNotIn("secret", str(weird))
        self.assertNotIn("token", str(weird))

    def test_it_judges_without_reading_the_policy_file_or_the_clock(self):
        original = sr.load_ai_policy

        def boom(*args, **kwargs):
            raise AssertionError("AI 처리기 정책 파일을 읽으면 안 된다")
        sr.load_ai_policy = boom
        try:
            self.assertIsNone(egress.check_ai_input("fixture_stats", SCOPE, registry_of(good_provider())))
            self.deny("fixture_stats", SCOPE, registry_of(good_provider(ai_use="NEVER")))
        finally:
            sr.load_ai_policy = original

    def test_the_real_noaa_entry_is_refused_even_if_it_were_enabled(self):
        data = json.loads((ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8"))
        for provider in data["providers"]:
            provider["enabled"] = provider["provider_id"] == "noaa_swpc_json"
        registry = sr.build_registry(data, "2026-11-10")
        self.assertEqual([p.provider_id for p in registry.active_providers()], ["noaa_swpc_json"])
        self.assertEqual(registry.get("noaa_swpc_json").ai_use, "NEVER")
        error = self.deny("noaa_swpc_json", SCOPE, registry)
        self.assertIn("NEVER", error.reason)
        for pid in ("statcan_wds", "uk_govuk_api"):
            self.assertEqual(registry.get(pid).ai_use, "NEVER")
            self.deny(pid, SCOPE, registry)


class RunCallCapTest(unittest.TestCase):
    def test_text_limits(self):
        table = {None: 0, "": 0, "UNKNOWN": 0, "확인 필요": 0, "100 per day": 3, "10/day": 0, "29/day": 0, "30/day": 1, "90/day": 3, "1000/hour": 20, "10/minute": 10, "5/hour": 4,
                 "60/minute, 1000/hour": 20, "2/second": 2, "0/day": 0, "5": 0}
        for text, expected in table.items():
            with self.subTest(text=text):
                self.assertEqual(egress.run_call_cap(text), expected, text)
        self.assertEqual(egress.run_call_cap("100 per day", runs_per_day=10), 10)
        self.assertEqual(egress.run_call_cap("100 per day", runs_per_day=10, hard_cap=4), 4)
        self.assertEqual(egress.run_call_cap("1000/hour", hard_cap=7), 7)
        self.assertEqual(egress.run_call_cap("10/minute, 5/hour"), 4)                                 # 여럿이면 가장 빡빡한 쪽

    def test_the_structured_limit_uses_the_own_limits_and_does_not_divide_by_runs(self):
        noaa = rate_object()
        self.assertEqual(egress.run_call_cap(noaa), 6)                                               # 3 × 1 × (1 + 1) = 6 ≤ 하루 8 — 글 하나를 재시도까지 끝낼 만큼
        self.assertEqual(egress.run_call_cap(sr._build_rate_limit(noaa)), 6)                         # 읽어 들인 값 객체도 같다
        self.assertEqual(egress.run_call_cap(rate_object(own=own_limit(max_retries=0, max_products_per_post=1, max_calls_per_day=1, max_calls_per_month=1))), 1)
        self.assertEqual(egress.run_call_cap(rate_object(own=own_limit(max_calls_per_day=6))), 6)
        self.assertEqual(egress.run_call_cap(noaa, hard_cap=2), 2)
        self.assertEqual(egress.run_call_cap(rate_object(official="100/day", own=None)), 3)         # 문구만 있으면 문구의 몫
        self.assertEqual(egress.run_call_cap(rate_object(official="5/hour")), 4)                      # 문구와 자체 상한이 함께 있으면 더 작은 쪽
        self.assertEqual(egress.run_call_cap(rate_object(own=own_limit(max_calls_per_day=6)), runs_per_day=1), 6)

    def test_an_unknown_or_malformed_limit_means_no_calls(self):
        for bad in (None, {}, {"official": "NONE"}, rate_object(own=None), rate_object(note=""), rate_object(own=own_limit(max_calls_per_day=0)), rate_object(official="weekly"),
                    object(), [], 5, rate_object(own={})):
            with self.subTest(bad=bad):
                self.assertEqual(egress.run_call_cap(bad), 0)

    def test_budget_for_reads_the_retry_count_from_the_own_limit(self):
        budget = egress.budget_for("noaa_swpc_json", sr._build_rate_limit(rate_object()))
        self.assertEqual((budget.max_calls, budget.max_retries, budget.max_failures), (6, 1, 3))
        budget = egress.budget_for("fixture_stats", "100 per day")
        self.assertEqual((budget.max_calls, budget.max_retries), (3, 1))
        budget = egress.budget_for("fixture_stats", None)
        self.assertEqual(budget.max_calls, 0)
        with self.assertRaises(egress.CallBudgetDenied) as caught:
            budget.before("https://x.example/")
        self.assertEqual(caught.exception.code, "RUN_CAP")
        budget = egress.budget_for("noaa_swpc_json", sr._build_rate_limit(rate_object(own=own_limit(max_retries=0, max_products_per_post=1, max_calls_per_day=1, max_calls_per_month=1))))
        self.assertEqual((budget.max_calls, budget.max_retries), (1, 0))
        pre = egress.budget_for("fixture_stats", "100 per day", precondition=lambda: "일 상한")
        with self.assertRaises(egress.CallBudgetDenied):
            pre.before("https://x.example/")


class CallBudgetTest(unittest.TestCase):
    URL = "https://api.fixture.example/v1/a"
    URL2 = "https://api.fixture.example/v1/b"

    def denied(self, budget, url=None):
        with self.assertRaises(egress.CallBudgetDenied) as caught:
            budget.before(url or self.URL)
        return caught.exception

    def test_constructor_refuses_bad_numbers(self):
        for kwargs in ({"max_calls": -1}, {"max_calls": True}, {"max_calls": 1.5}, {"max_calls": "3"}, {"max_calls": 3, "max_failures": 0}, {"max_calls": 3, "max_failures": True},
                       {"max_calls": 3, "max_retries": -1}, {"max_calls": 3, "max_retries": True}, {"max_calls": 3, "precondition": "x"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    egress.CallBudget("fixture_stats", **kwargs)
        self.assertEqual(egress.CallBudget("fixture_stats", 0).max_calls, 0)

    def test_the_run_cap_is_counted_and_a_denial_never_names_the_address(self):
        budget = egress.CallBudget("fixture_stats", 2)
        budget.before(self.URL)
        budget.before(self.URL2)
        error = self.denied(budget, "https://api.fixture.example/v1/secret-token-9")
        self.assertEqual((error.code, error.provider_id, budget.calls), ("RUN_CAP", "fixture_stats", 2))
        self.assertNotIn("secret", str(error))
        self.assertNotIn("api.fixture.example", str(error))
        self.assertIn("RUN_CAP", str(error))
        zero = egress.CallBudget("fixture_stats", 0)
        self.assertEqual(self.denied(zero).code, "RUN_CAP")
        self.assertEqual(zero.calls, 0)

    def test_three_failures_skip_the_provider_for_the_rest_of_the_run(self):
        budget = egress.CallBudget("fixture_stats", 20, max_retries=5)
        for index in range(3):
            self.assertFalse(budget.skipped)
            budget.before(f"{self.URL}{index}")
            budget.failed()
        self.assertTrue(budget.skipped)
        self.assertEqual(self.denied(budget, self.URL2).code, "SKIPPED_AFTER_FAILURES")
        two = egress.CallBudget("fixture_stats", 20, max_failures=2)
        two.failed()
        self.assertFalse(two.skipped)
        two.failed()
        self.assertTrue(two.skipped)

    def test_the_same_address_may_be_retried_only_as_often_as_allowed(self):
        once = egress.CallBudget("fixture_stats", 20, max_retries=1)
        once.before(self.URL)
        once.before(self.URL)                                                                         # 재시도 1번
        self.assertEqual(self.denied(once).code, "RETRY_CAP")
        once.before(self.URL2)                                                                        # 다른 주소는 따로 센다
        none = egress.CallBudget("fixture_stats", 20, max_retries=0)
        none.before(self.URL)
        self.assertEqual(self.denied(none).code, "RETRY_CAP")

    def test_403_and_429_stop_the_provider_and_404_stops_only_that_address(self):
        for status in (403, 429):
            budget = egress.CallBudget("fixture_stats", 20)
            budget.before(self.URL)
            budget.failed(status, self.URL)
            self.assertTrue(budget.blocked, status)
            self.assertEqual(self.denied(budget, self.URL2).code, "STOPPED_BY_STATUS")
        budget = egress.CallBudget("fixture_stats", 20)
        budget.before(self.URL)
        budget.failed(404, self.URL)
        self.assertFalse(budget.blocked)
        self.assertEqual(self.denied(budget, self.URL).code, "STOPPED_URL")
        budget.before(self.URL2)                                                                      # 그 제품만 중지 — 다른 주소는 계속
        for status in (500, 503, None, 401):
            other = egress.CallBudget("fixture_stats", 20)
            other.before(self.URL)
            other.failed(status, self.URL)
            self.assertFalse(other.blocked, status)
            self.assertEqual(other.failures, 1)
        no_url = egress.CallBudget("fixture_stats", 20)
        no_url.failed(404)
        self.assertEqual((no_url.failures, no_url.blocked), (1, False))

    def test_the_precondition_runs_first_and_a_blocked_day_means_zero_calls(self):
        reasons = iter(["오늘 이미 1편 발행", None, "", "다시 막힘"])
        budget = egress.CallBudget("fixture_stats", 5, precondition=lambda: next(reasons))
        self.assertEqual(self.denied(budget).code, "PRECONDITION")
        self.assertEqual(budget.calls, 0)
        budget.before(self.URL)                                                                       # None 은 막지 않는다
        budget.before(self.URL2)                                                                      # 빈 글자도 막지 않는다
        self.assertEqual(self.denied(budget).code, "PRECONDITION")
        self.assertEqual(budget.calls, 2)
        blocked = egress.CallBudget("fixture_stats", 5, precondition=lambda: "주간 상한")
        blocked.failures = 99
        blocked.blocked = True
        self.assertEqual(self.denied(blocked).code, "PRECONDITION")                                   # 다른 거부 사유보다 먼저 본다

    def test_a_precondition_that_cannot_be_checked_fails_closed_without_leaking_its_error(self):
        def broken():
            raise RuntimeError("secret-token-in-error")
        budget = egress.CallBudget("fixture_stats", 5, precondition=broken)
        error = self.denied(budget)
        self.assertEqual(error.code, "PRECONDITION")
        self.assertNotIn("secret", str(error))
        self.assertEqual(budget.calls, 0)

    def test_unsent_gives_the_call_back_and_the_cache_is_bounded(self):
        budget = egress.CallBudget("fixture_stats", 1)
        budget.before(self.URL)
        budget.unsent(self.URL)
        budget.before(self.URL)                                                                       # 요청이 나가지 않았으니 호출 수·시도 수를 되돌렸다
        self.assertEqual(budget.calls, 1)
        budget.unsent()
        budget.unsent()
        self.assertEqual(budget.calls, 0)                                                             # 0 아래로 내려가지 않는다
        for index in range(egress.CACHE_MAX_ENTRIES + 5):
            budget.remember(f"https://x.example/{index}", b"body")
        self.assertEqual(sum(1 for index in range(egress.CACHE_MAX_ENTRIES + 5) if budget.cached(f"https://x.example/{index}") is not None), egress.CACHE_MAX_ENTRIES)
        budget.remember("https://x.example/0", b"new")                                                # 이미 있는 주소는 갱신된다
        self.assertEqual(budget.cached("https://x.example/0"), b"new")
        self.assertIsNone(budget.cached("https://never.example/"))


class BudgetedOpenerTest(unittest.TestCase):
    URL = "https://api.fixture.example/v1/a"
    URL2 = "https://api.fixture.example/v1/b"

    def fake(self, outcomes):
        calls = []

        def opener(url, *, timeout, max_bytes):
            calls.append((url, timeout, max_bytes))
            outcome = outcomes.get(url, b"ok") if isinstance(outcomes, dict) else outcomes
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return opener, calls

    def test_a_successful_answer_is_reused_inside_the_same_run_without_another_call(self):
        opener, calls = self.fake({})
        budget = egress.CallBudget("fixture_stats", 3)
        call = egress.budgeted(opener, budget)
        self.assertEqual(call(self.URL, timeout=5, max_bytes=100), b"ok")
        self.assertEqual(call(self.URL, timeout=5, max_bytes=100), b"ok")
        self.assertEqual(len(calls), 1)
        self.assertEqual(budget.calls, 1)                                                              # 재사용은 호출 수에 세지 않는다
        self.assertEqual(call(self.URL2, timeout=5, max_bytes=100), b"ok")
        self.assertEqual((len(calls), budget.calls), (2, 2))
        self.assertEqual(calls[0], (self.URL, 5, 100))                                                 # opener 에 시간 제한·크기 상한을 그대로 넘긴다

    def test_the_cap_denies_before_the_opener_is_called(self):
        opener, calls = self.fake({})
        budget = egress.CallBudget("fixture_stats", 1)
        call = egress.budgeted(opener, budget)
        call(self.URL, timeout=5, max_bytes=100)
        with self.assertRaises(egress.CallBudgetDenied):
            call(self.URL2, timeout=5, max_bytes=100)
        self.assertEqual(len(calls), 1)
        zero, zero_calls = self.fake({}), None
        none_budget = egress.CallBudget("fixture_stats", 0)
        with self.assertRaises(egress.CallBudgetDenied):
            egress.budgeted(zero[0], none_budget)(self.URL, timeout=5, max_bytes=100)
        self.assertEqual(zero[1], [])

    def test_a_blocked_day_means_the_opener_is_never_called(self):
        opener, calls = self.fake({})
        call = egress.budgeted(opener, egress.CallBudget("fixture_stats", 5, precondition=lambda: "오늘 이미 상한"))
        with self.assertRaises(egress.CallBudgetDenied):
            call(self.URL, timeout=5, max_bytes=100)
        self.assertEqual(calls, [])

    def test_429_and_403_stop_the_provider_and_the_original_error_is_raised_as_it_was(self):
        for status in (429, 403):
            error = urllib.error.HTTPError(self.URL, status, "Too Many Requests", {}, None)
            opener, calls = self.fake({self.URL: error})
            budget = egress.CallBudget("fixture_stats", 5)
            call = egress.budgeted(opener, budget)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                call(self.URL, timeout=5, max_bytes=100)
            self.assertIs(caught.exception, error)
            self.assertTrue(budget.blocked)
            with self.assertRaises(egress.CallBudgetDenied) as denied:
                call(self.URL2, timeout=5, max_bytes=100)
            self.assertEqual(denied.exception.code, "STOPPED_BY_STATUS")
            self.assertEqual(len(calls), 1)

    def test_404_stops_only_that_address(self):
        opener, calls = self.fake({self.URL: urllib.error.HTTPError(self.URL, 404, "Not Found", {}, None)})
        budget = egress.CallBudget("fixture_stats", 5)
        call = egress.budgeted(opener, budget)
        with self.assertRaises(urllib.error.HTTPError):
            call(self.URL, timeout=5, max_bytes=100)
        with self.assertRaises(egress.CallBudgetDenied) as denied:
            call(self.URL, timeout=5, max_bytes=100)
        self.assertEqual(denied.exception.code, "STOPPED_URL")
        self.assertEqual(call(self.URL2, timeout=5, max_bytes=100), b"ok")
        self.assertEqual(len(calls), 2)

    def test_other_failures_count_and_three_of_them_skip_the_provider(self):
        failures = {f"{self.URL}{n}": OSError("boom") for n in range(3)}
        opener, calls = self.fake(failures)
        budget = egress.CallBudget("fixture_stats", 20)
        call = egress.budgeted(opener, budget)
        for n in range(3):
            with self.assertRaises(OSError):
                call(f"{self.URL}{n}", timeout=5, max_bytes=100)
        self.assertEqual((budget.failures, budget.skipped), (3, True))
        with self.assertRaises(egress.CallBudgetDenied) as denied:
            call(self.URL2, timeout=5, max_bytes=100)
        self.assertEqual(denied.exception.code, "SKIPPED_AFTER_FAILURES")
        self.assertEqual(len(calls), 3)

    def test_a_retry_is_allowed_once_and_a_failure_is_not_cached(self):
        outcomes = iter([OSError("first"), b"second"])
        calls = []

        def opener(url, *, timeout, max_bytes):
            calls.append(url)
            outcome = next(outcomes)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        budget = egress.CallBudget("fixture_stats", 5, max_retries=1)
        call = egress.budgeted(opener, budget)
        with self.assertRaises(OSError):
            call(self.URL, timeout=5, max_bytes=100)
        self.assertEqual(call(self.URL, timeout=5, max_bytes=100), b"second")
        self.assertEqual(call(self.URL, timeout=5, max_bytes=100), b"second")                          # 성공은 저장돼 다시 부르지 않는다
        self.assertEqual(len(calls), 2)

    def test_a_denial_by_the_gate_is_not_a_provider_failure_and_gives_the_call_back(self):
        registry = registry_of(good_provider())
        fake = FakeHttps({})
        director = egress.build_checked_opener("fact", registry, max_redirects=0, https_handler=fake)

        def opener(url, *, timeout, max_bytes):
            response = director.open(url, timeout=timeout)
            try:
                return response.read(max_bytes + 1)
            finally:
                response.close()
        budget = egress.CallBudget("fixture_stats", 2)
        call = egress.budgeted(opener, budget)
        for _ in range(4):                                                                             # 허용 목록 밖 주소를 거듭 불러도 실패 수·호출 수가 쌓이지 않는다
            with self.assertRaises(egress.EgressDenied):
                call("https://evil.example/x", timeout=5, max_bytes=100)
        self.assertEqual((budget.calls, budget.failures, budget.skipped), (0, 0, False))
        self.assertEqual(fake.sent, [])                                                                # 요청은 한 번도 나가지 않았다

    def test_it_works_on_top_of_a_checked_opener_that_does_not_follow_redirects(self):
        registry = registry_of(good_provider())
        good = f"https://{GOOD_HOST}/v1/a"
        fake = FakeHttps({good: (200, {}), f"https://{GOOD_HOST}/v1/moved": (302, {"Location": f"https://{GOOD_HOST}/v1/a"})})
        director = egress.build_checked_opener("fact", registry, max_redirects=0, https_handler=fake)

        def opener(url, *, timeout, max_bytes):
            response = director.open(url, timeout=timeout)
            try:
                return response.read(max_bytes + 1)
            finally:
                response.close()
        budget = egress.CallBudget("fixture_stats", 3)
        call = egress.budgeted(opener, budget)
        self.assertEqual(call(good, timeout=5, max_bytes=100), b"body")
        self.assertEqual(call(good, timeout=5, max_bytes=100), b"body")
        self.assertEqual(fake.sent, [good])                                                            # 두 번째는 재사용
        with self.assertRaises(urllib.error.HTTPError):
            call(f"https://{GOOD_HOST}/v1/moved", timeout=5, max_bytes=100)                           # 리다이렉트를 따라가지 않으니 호출 한 번이 요청 한 번이다
        self.assertEqual(len(fake.sent), 2)

    def test_the_budget_keeps_no_persistent_state(self):
        """새 영구 상태를 만들지 않는다 — 예산 객체는 메모리뿐이고 파일을 만들거나 읽지 않는다(모듈에 파일 열기·쓰기 호출이 없다)."""
        import ast
        tree = ast.parse((ROOT / "pipeline" / "egress.py").read_text(encoding="utf-8"))
        names = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        attrs = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertFalse(names & {"open"}, names)
        self.assertFalse(attrs & {"write_text", "write_bytes", "open", "mkdir", "dump", "dumps"}, attrs)
        budget = egress.CallBudget("fixture_stats", 3)
        self.assertEqual(sorted(vars(copy.copy(budget))), sorted(vars(budget)))


if __name__ == "__main__":
    unittest.main()
