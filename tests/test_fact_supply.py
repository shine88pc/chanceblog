"""구조화 Fact 후보 공급(S2b, `pipeline/fact_supply.py`) 시험: 순수 오케스트레이터가 이력의 발행일로 차례를 정하고 → 어댑터(주입된 opener 로만 네트워크) → 조립기를 돌려 글 후보를 만든다.
못박는 것: 첫 글 하나·묶음 안 폴백(대표가 못 만들면 같은 묶음의 다음 글감)·한 제품은 한 실행에서 한 번만 부름(성공도 실패도 기억 — 실패 뒤 곧바로 되부르는 재시도 없음)·어댑터 오류·`Insufficient`·중복·`accept` 거절은
그 글감만 건너뛰고 다음으로 넘어감·시각 때문에 기다리는 글감(일별 제품 00:30 UTC)은 건너뛰지 않고 기다림·Gate 에 넘기는 `source` 사전의 모양(레지스트리에서만 채움)·입력이 이상해도 예외 없음·이력을 바꾸지 않음.
네트워크·시계 없음 — 응답은 시험이 만든 가상 값이다."""
import copy
import dataclasses
import datetime
import json
import random
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import fact_branch_helpers as FB
import hold_helpers as HH
import space_helpers as H
import test_space_recipes as TR

from pipeline import fact_assembler as A
from pipeline import fact_candidates as K
from pipeline import fact_supply as S
from pipeline.adapters import noaa_swpc as N
from pipeline.adapters.base import AdapterError

# S2C0-a: 이 모듈은 임시 제외·처음 낼 글감과 상관없는 정책(글감 여섯 전부)을 시험한다 — 두 상수를 비운 이전 동작으로 돌린다(단언은 하나도 바꾸지 않았다). 기본 상수의 동작은 tests/test_fact_hold.py 가 시험한다
setUpModule, tearDownModule = HH.module_fixtures()

DAY = "2026-11-10"
RETRIEVED = "2026-11-10T01:12:00Z"
PROVIDER = H.provider(attribution_template=H.B_TEMPLATE)


def entry(spec_id, day, **extra):
    key = K.candidate_key(K.SPEC_BY_ID[spec_id], day)
    item = {"date": day, "content_source": "facts", "candidate_key": key, "dedupe_key": f"d|{spec_id}|{day}"}
    item.update(extra)
    return item


class Scene:
    """공급을 한 번 돌리는 도구: 가상 응답·가짜 opener(호출한 주소를 적는다)."""

    def __init__(self, day=DAY, **fail):
        self.noaa = FB.FakeNoaa(day)
        self.noaa.fail.update(fail)

    def run(self, history=(), retrieved_at=RETRIEVED, today=DAY, provider=PROVIDER, **kwargs):
        kwargs.setdefault("limit", 1)
        return S.supply(today=today, retrieved_at=retrieved_at, history=list(history), provider=provider, opener=self.noaa.transport, **kwargs)


class HappyPathTest(unittest.TestCase):
    def test_the_first_post_is_the_head_of_the_line_and_only_its_product_is_read(self):
        scene = Scene()
        result = scene.run()
        self.assertEqual(len(result.posts), 1)
        self.assertIsInstance(result.posts[0], A.AssembledPost)
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["kp_weekly"])
        self.assertEqual(result.candidates[0].candidate_key, K.candidate_key(K.SPEC_BY_ID["kp_weekly"], DAY))
        self.assertEqual(result.posts[0].recipe_id, result.candidates[0].recipe_id)
        self.assertEqual(result.skipped, ())
        self.assertEqual(result.waiting, "")
        self.assertEqual(result.considered, ("kp_weekly",))
        self.assertEqual(scene.noaa.products(), ["kp_estimated"])                              # 첫 글 하나를 만드는 데 필요한 제품 하나만 읽었다

    def test_with_a_larger_limit_one_post_per_group_comes_out_and_each_product_is_read_once(self):
        scene = Scene()
        result = scene.run(limit=10)
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["kp_weekly", "flares_weekly", "scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"])
        self.assertEqual(len(result.posts), 5)
        self.assertEqual(sorted(scene.noaa.products()), sorted({"kp_estimated", "xray_flares", "scales", "ssn_daily", "ssn_monthly"}))
        self.assertEqual(len(scene.noaa.calls), len(set(scene.noaa.calls)))                    # 같은 주소를 두 번 부르지 않았다
        self.assertEqual(len({post.dedupe_key for post in result.posts}), 5)
        self.assertNotIn("kp_storm_weekly", [candidate.spec.spec_id for candidate in result.candidates])      # 같은 묶음에서는 한 편만

    def test_the_order_follows_the_history_oldest_first(self):
        history = [entry("kp_weekly", "2026-10-26"), entry("kp_storm_weekly", "2026-10-26"), entry("flares_weekly", "2026-11-03")]
        result = Scene().run(history=history, limit=3)
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"])        # 안 낸 셋이 먼저
        result = Scene().run(history=history, limit=5)
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly", "kp_weekly", "flares_weekly"])

    def test_every_post_is_a_real_assembled_post_with_the_source_of_its_first_product(self):
        scene = Scene()
        result = scene.run(limit=10)
        for post, candidate in zip(result.posts, result.candidates):
            first = candidate.products[0]
            self.assertEqual(post.source_name, N.product_source_name(first))
            self.assertEqual(post.source_url, N.product_url(first))
            self.assertEqual(post.source_domain, N.HOST)
            self.assertEqual(post.lang, "ko")
            self.assertTrue(post.evidence_text)


class FallbackTest(unittest.TestCase):
    def flat_kp_scene(self):
        scene = Scene()
        scene.noaa.by_product["kp_estimated"] = TR.kp_rows_on_days([(f"2026-11-{day:02d}", 3.0) for day in (3, 4, 5, 6, 8, 9)])      # 평평하고 최근 사흘 안에 빠진 날 — R04 는 NO_ANALYSIS, R05 는 글이 난다
        return scene

    def test_when_the_head_of_a_group_cannot_make_a_post_the_next_subject_of_the_same_group_is_tried_with_the_response_already_read(self):
        scene = self.flat_kp_scene()
        result = scene.run()
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["kp_storm_weekly"])
        self.assertEqual(result.skipped, (("kp_weekly", "INSUFFICIENT:NO_ANALYSIS"),))
        self.assertEqual(result.considered, ("kp_weekly", "kp_storm_weekly"))
        self.assertEqual(scene.noaa.products(), ["kp_estimated"])                              # 같은 제품 — 다시 부르지 않고 받은 응답을 썼다
        self.assertEqual(result.posts[0].recipe_id, "R05_THRESHOLD_COUNT")

    def test_when_the_whole_group_fails_the_next_group_is_tried(self):
        scene = Scene()
        scene.noaa.by_product["kp_estimated"] = H.kp_rows("2026-11-08", 2)                    # 이틀치 — 두 글감 모두 자료 부족
        result = scene.run()
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["flares_weekly"])
        self.assertEqual(result.skipped, (("kp_weekly", "INSUFFICIENT:TOO_FEW_POINTS"), ("kp_storm_weekly", "INSUFFICIENT:TOO_FEW_POINTS")))
        self.assertEqual(scene.noaa.products(), ["kp_estimated", "xray_flares"])

    def test_a_rejection_by_the_caller_is_a_skip_and_the_next_subject_continues(self):
        seen = []

        def accept(post, candidate):
            seen.append((candidate.spec.spec_id, type(post).__name__))
            return "NO" if candidate.spec.spec_id == "kp_weekly" else None
        result = Scene().run(accept=accept)
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["kp_storm_weekly"])
        self.assertEqual(result.skipped, (("kp_weekly", "REJECTED:NO"),))
        self.assertEqual(seen, [("kp_weekly", "AssembledPost"), ("kp_storm_weekly", "AssembledPost")])

    def test_every_candidate_failing_gives_no_posts_and_a_reason_each(self):
        result = Scene().run(accept=lambda post, candidate: "ALWAYS", limit=5)
        self.assertEqual(result.posts, ())
        self.assertEqual({spec_id for spec_id, _code in result.skipped}, {"kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"})
        self.assertTrue(all(code == "REJECTED:ALWAYS" for _spec, code in result.skipped))

    def test_a_reason_from_the_caller_is_turned_into_fixed_characters(self):
        for given, shown in (("a b\n<x>", "REJECTED:a_b__x_"), ("한글 사유", "REJECTED:_____"), ("GATE:QG0-NO-SOURCE+QG3-LINK", "REJECTED:GATE:QG0-NO-SOURCE_QG3-LINK"), ("x" * 200, "REJECTED:" + "x" * 60)):
            with self.subTest(given=given):
                self.assertEqual(Scene().run(accept=lambda post, candidate: given).skipped[0][1], shown)


class AdapterFailureTest(unittest.TestCase):
    def test_an_adapter_error_skips_only_the_subjects_that_read_that_product(self):
        scene = Scene(kp_estimated=AdapterError("EGRESS_DENIED"))
        result = scene.run()
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["flares_weekly"])
        self.assertEqual(result.skipped, (("kp_weekly", "ADAPTER:EGRESS_DENIED"), ("kp_storm_weekly", "ADAPTER:EGRESS_DENIED")))
        self.assertEqual(scene.noaa.products(), ["kp_estimated", "xray_flares"])             # 실패한 제품을 같은 실행에서 다시 부르지 않았다(실패 뒤 곧바로 되부르는 재시도 없음)

    def test_a_failure_is_remembered_so_a_product_is_read_once_even_when_two_subjects_need_it(self):
        scene = Scene(kp_estimated=RuntimeError("연결 끊김"))
        result = scene.run(limit=1)
        self.assertEqual(scene.noaa.products().count("kp_estimated"), 1)
        self.assertEqual(result.skipped[:2], (("kp_weekly", "ADAPTER:OPENER_FAILED"), ("kp_storm_weekly", "ADAPTER:OPENER_FAILED")))

    def test_any_exception_from_the_opener_becomes_an_opener_failure_without_its_text(self):
        for error in (RuntimeError("https://x.example/?token=SECRET"), OSError("끊김"), TimeoutError(), KeyError("k"), ValueError("v")):
            with self.subTest(error=type(error).__name__):
                result = Scene(kp_estimated=error).run(limit=1)
                self.assertEqual(result.skipped[0], ("kp_weekly", "ADAPTER:OPENER_FAILED"))
                for _spec, code in result.skipped:
                    self.assertNotIn("SECRET", code)

    def test_a_broken_or_changed_response_skips_the_subject_and_never_makes_a_post(self):
        cases = (("깨진 JSON", b"{not json", "ADAPTER:BAD_JSON"), ("HTML", b"<html><body>x</body></html>", "ADAPTER:BAD_JSON"), ("빈 응답", b"", "ADAPTER:BAD_JSON"),
                 ("모양이 바뀜", json.dumps([{"time": "x"}]).encode(), "ADAPTER:BAD_SHAPE"), ("빈 목록", b"[]", "ADAPTER:BAD_SHAPE"), ("글자가 아님", b"\xff\xfe\x00", "ADAPTER:BAD_ENCODING"),
                 ("너무 큼", b"[" + b"0," * 700_000 + b"0]", "ADAPTER:TOO_LARGE"))
        for label, raw, code in cases:
            with self.subTest(case=label):
                scene = Scene()
                scene.noaa.raw["kp_estimated"] = raw
                result = scene.run()
                self.assertEqual(result.skipped[0], ("kp_weekly", code))
                self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["flares_weekly"])

    def test_a_provider_that_is_not_active_gets_no_adapter_and_the_opener_is_never_called(self):
        scene = Scene()
        for changes in ({"enabled": False}, {"strict_tier": 3}, {"effective_status": "자동화 제외"}):
            with self.subTest(changes=changes):
                result = scene.run(provider=H.provider(**changes), limit=5)
                self.assertEqual(result.posts, ())
                self.assertTrue(result.skipped)
                self.assertTrue(all(code == "ADAPTER:BAD_PROVIDER" for _spec, code in result.skipped))
        self.assertEqual(scene.noaa.calls, [])

    def test_a_provider_without_the_api_access_skips_every_candidate_without_a_call(self):
        scene = Scene()
        for access in ((), (H.Access("rss", (N.HOST,), ("/",)),), (H.Access("api", ("other.example",), ("/",)),)):
            with self.subTest(access=access):
                result = scene.run(provider=H.provider(access=access), limit=5)
                self.assertEqual(result.posts, ())
                self.assertTrue(all(code == "ADAPTER:BAD_ACCESS" for _spec, code in result.skipped))
        self.assertEqual(scene.noaa.calls, [])


def synthetic(**changes):
    """실제 글감은 모두 제품 하나만 읽고 틀 이름도 모두 안다. 공급 함수가 제품 여럿·모르는 틀을 다루는 길은 합성 후보(선택 함수를 가짜로 바꿔 넣음)로 시험한다."""
    spec = dataclasses.replace(K.SPEC_BY_ID["kp_weekly"], **changes)
    return K.Candidate(spec, K.candidate_key(spec, DAY), tuple(sorted(spec.params().items())), spec.products)


class SyntheticCandidateTest(unittest.TestCase):
    def run_with(self, candidate, scene=None, **kwargs):
        scene = scene or Scene()
        with mock.patch.object(K, "select_candidates", lambda today, made, minutes_utc=None: (candidate,)):
            return scene, scene.run(**kwargs)

    def test_a_candidate_that_reads_two_products_stops_at_the_first_failed_one(self):
        candidate = synthetic(products=("kp_estimated", "scales"))
        scene, result = self.run_with(candidate, Scene(kp_estimated=OSError("끊김")))
        self.assertEqual(scene.noaa.products(), ["kp_estimated"])                                    # 첫 제품이 실패하면 둘째는 부르지 않는다
        self.assertEqual(result.skipped, (("kp_weekly", "ADAPTER:OPENER_FAILED"),))
        self.assertEqual(result.posts, ())
        scene, result = self.run_with(candidate, Scene(scales=OSError("끊김")))                       # 둘째 제품이 실패하면 첫 제품이 성공했어도 글이 없다
        self.assertEqual(scene.noaa.products(), ["kp_estimated", "scales"])
        self.assertEqual(result.skipped, (("kp_weekly", "ADAPTER:OPENER_FAILED"),))
        self.assertEqual(result.posts, ())

    def test_the_source_of_a_post_comes_from_the_first_product_and_every_record_is_passed_on(self):
        captured = {}
        real = A.assemble

        def spy(recipe, facts, day, **kwargs):
            captured.update(kwargs)
            return real(recipe, facts, day, **kwargs)
        with mock.patch.object(S.A, "assemble", spy):
            scene, _result = self.run_with(synthetic(products=("kp_estimated", "scales")))
        self.assertEqual(scene.noaa.products(), ["kp_estimated", "scales"])
        self.assertEqual((captured["source"].name, captured["source"].url), (N.product_source_name("kp_estimated"), N.product_url("kp_estimated")))
        self.assertEqual(len(captured["records"]), 2)

    def test_an_unknown_recipe_is_a_fixed_reason_and_never_an_exception(self):
        scene, result = self.run_with(synthetic(recipe_id="R99_UNKNOWN"))
        self.assertEqual(result.skipped, (("kp_weekly", "INSUFFICIENT:UNKNOWN_RECIPE"),))
        self.assertEqual(result.posts, ())

    def test_an_unexpected_exception_inside_the_adapter_becomes_a_fixed_reason_and_only_that_product_fails(self):
        real = N.NoaaSwpcAdapter.parse

        def broken(adapter, raw, access, retrieved_at, params=None):
            if adapter.product.product_id == "kp_estimated":
                raise RuntimeError("비밀 문장 SECRET-TEXT")
            return real(adapter, raw, access, retrieved_at, params)
        scene = Scene()
        with mock.patch.object(N.NoaaSwpcAdapter, "parse", broken):
            result = scene.run(limit=2)
        self.assertIn(("kp_weekly", "ADAPTER:UNEXPECTED_ERROR"), result.skipped)
        self.assertIn(("kp_storm_weekly", "ADAPTER:UNEXPECTED_ERROR"), result.skipped)               # 같은 제품이라 기억한 실패
        self.assertEqual(len(result.posts), 2)                                                        # 다음 묶음들은 계속된다
        self.assertEqual(scene.noaa.products().count("kp_estimated"), 1)                             # 실패한 제품도 한 번만 불렀다
        self.assertNotIn("SECRET-TEXT", repr(result))                                                 # 예외 글이 사유에 섞이지 않는다


class DuplicateTest(unittest.TestCase):
    def test_a_post_whose_dedupe_key_is_already_in_the_history_is_skipped(self):
        first = Scene().run()
        self.assertEqual(first.candidates[0].spec.spec_id, "kp_weekly")
        key = first.posts[0].dedupe_key
        others = [entry("flares_weekly", "2026-11-03"), entry("scales_weekly", "2026-11-03"), entry("sunspot_daily_monthly", "2026-10-09"), entry("sunspot_monthly_monthly", "2026-10-09")]
        history = [{"date": "2026-10-01", "content_source": "facts", "candidate_key": "space_weather.kp_weekly:2026-W40", "dedupe_key": key}, entry("kp_storm_weekly", "2026-10-08")] + others      # kp_weekly 가 차례 맨 앞이다
        result = Scene().run(history=history)
        self.assertEqual(result.skipped[0], ("kp_weekly", "DUPLICATE:DEDUPE_KEY"))
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["kp_storm_weekly"])                                                                        # 같은 묶음의 다음 글감이 이어진다

    def test_entries_that_are_not_fact_posts_never_count_as_duplicates(self):
        first = Scene().run()
        history = [{"date": "2026-10-01", "topic": "옛 글", "dedupe_key": first.posts[0].dedupe_key}]
        self.assertEqual([candidate.spec.spec_id for candidate in Scene().run(history=history).candidates], ["kp_weekly"])


class WaitingTest(unittest.TestCase):
    EARLY = "2026-11-10T00:10:00Z"

    def history_where_the_daily_sunspot_subject_is_oldest(self):
        history = [entry(name, "2026-11-02") for name in ("kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly")]
        return history + [entry("sunspot_daily_monthly", "2026-10-05"), entry("sunspot_monthly_monthly", "2026-10-08")]

    def test_a_subject_that_must_wait_for_the_time_of_day_is_waited_for_not_skipped(self):
        history = self.history_where_the_daily_sunspot_subject_is_oldest()
        scene = Scene()
        result = scene.run(history=history, retrieved_at=self.EARLY)
        self.assertEqual(result.waiting, "sunspot_daily_monthly")
        self.assertEqual(result.posts, ())                                                    # 다른 글감을 먼저 내지 않는다 — 건너뛰면 그 글감이 새벽 실행에 늘 밀려 굶는다
        self.assertEqual(scene.noaa.calls, [])
        later = Scene().run(history=history, retrieved_at="2026-11-10T00:30:00Z")
        self.assertEqual(later.waiting, "")
        self.assertEqual([candidate.spec.spec_id for candidate in later.candidates], ["sunspot_daily_monthly"])

    def test_a_subject_that_needs_no_waiting_goes_ahead_of_a_later_subject_that_waits(self):
        scene = Scene()
        result = scene.run(retrieved_at=self.EARLY, limit=4)
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["kp_weekly", "flares_weekly", "scales_weekly"])
        self.assertEqual(result.waiting, "sunspot_daily_monthly")
        self.assertEqual(result.considered[-1], "sunspot_daily_monthly")

    def test_an_offset_in_the_time_is_read_as_the_instant_it_is(self):
        history = self.history_where_the_daily_sunspot_subject_is_oldest()
        self.assertEqual(Scene().run(history=history, retrieved_at="2026-11-10T09:10:00+09:00").waiting, "sunspot_daily_monthly")      # 협정 세계시 0시 10분
        self.assertEqual(Scene().run(history=history, retrieved_at="2026-11-10T09:30:00+09:00").waiting, "")                            # 0시 30분


class BadInputTest(unittest.TestCase):
    def test_a_bad_day_or_time_gives_a_reason_and_never_an_exception(self):
        scene = Scene()
        for today in ("2026-13-01", "어제", None, 20261110, ""):
            result = scene.run(today=today)
            self.assertEqual((result.posts, result.skipped), ((), (("(all)", "BAD_INPUT:TODAY"),)))
        for retrieved in ("2026-11-10", "어제", None, "2026-11-10T01:12:00", 5, ""):
            result = scene.run(retrieved_at=retrieved)
            self.assertEqual((result.posts, result.skipped), ((), (("(all)", "BAD_INPUT:RETRIEVED_AT"),)))
        self.assertEqual(scene.noaa.calls, [])

    def test_a_limit_that_is_not_a_positive_integer_means_one(self):
        for limit in (0, -3, None, "2", 2.5, True):
            result = Scene().run(limit=limit)
            self.assertEqual(len(result.posts), 1, limit)

    def test_a_garbage_history_is_tolerated(self):
        rng = random.Random(7)
        pool = [None, "x", 3, [], {}, {"content_source": "facts"}, {"content_source": "facts", "candidate_key": 5}, {"date": "?", "content_source": "facts", "candidate_key": "space_weather.kp_weekly:2026-W46"}]
        for _ in range(30):
            history = [rng.choice(pool) for _ in range(rng.randint(0, 5))]
            result = Scene().run(history=history)
            self.assertLessEqual(len(result.posts), 1)

    def test_the_history_is_not_changed_and_the_result_is_a_pure_function_of_the_inputs(self):
        history = [entry("kp_weekly", "2026-10-26"), entry("flares_weekly", "2026-11-03")]
        before = copy.deepcopy(history)
        first, second = Scene().run(history=history, limit=3), Scene().run(history=history, limit=3)
        self.assertEqual(history, before)
        self.assertEqual([post.title for post in first.posts], [post.title for post in second.posts])
        self.assertEqual([post.body_markdown for post in first.posts], [post.body_markdown for post in second.posts])
        self.assertEqual((first.skipped, first.waiting, first.considered), (second.skipped, second.waiting, second.considered))
        self.assertTrue(dataclasses.is_dataclass(first))


class GateSourceTest(unittest.TestCase):
    def post(self):
        return Scene().run().posts[0]

    def test_the_source_dictionary_has_exactly_the_agreed_nine_keys(self):
        source = S.gate_source(self.post(), PROVIDER)
        self.assertEqual(tuple(source), S.GATE_SOURCE_KEYS)
        self.assertEqual(S.GATE_SOURCE_KEYS, ("fact_post", "evidence_text", "source_url", "source_domain", "source_name", "provider_hosts", "dedupe_key", "recipe_id", "as_of"))
        self.assertIs(source["fact_post"], True)
        json.dumps(source, ensure_ascii=False)                                                # 글자·목록뿐이다(JSON 으로 쓸 수 있다)

    def test_the_values_come_from_the_assembled_post_and_the_provider_hosts_only_from_the_registry_provider(self):
        post = self.post()
        source = S.gate_source(post, PROVIDER)
        self.assertEqual((source["evidence_text"], source["source_url"], source["source_domain"], source["source_name"], source["dedupe_key"], source["recipe_id"], source["as_of"]),
                         (post.evidence_text, post.source_url, post.source_domain, post.source_name, post.dedupe_key, post.recipe_id, post.as_of))
        self.assertEqual(source["provider_hosts"], [N.HOST])
        evil = dataclasses.replace(post, source_domain="evil.example", source_url="https://evil.example/x")
        self.assertEqual(S.gate_source(evil, PROVIDER)["provider_hosts"], [N.HOST])           # 글에 적힌 도메인이 레지스트리 호스트 목록에 들어가지 않는다

    def test_provider_hosts_are_all_hosts_of_all_access_entries_without_duplicates_and_skip_non_text(self):
        access = (H.Access("api", ("a.example", N.HOST), ("/",)), H.Access("csv", (N.HOST, "b.example", 5, None, ""), ("/",)))
        self.assertEqual(S.provider_hosts(H.provider(access=access)), ["a.example", N.HOST, "b.example"])
        for bad in ((), None, "x", 5):
            self.assertEqual(S.provider_hosts(H.provider(access=bad)), [])
        self.assertEqual(S.provider_hosts({"access": [{"hosts": ["x.example"]}]}), ["x.example"])


class ModuleShapeTest(unittest.TestCase):
    def test_the_module_exposes_what_the_generator_needs_and_the_provider_id_is_the_registry_one(self):
        self.assertEqual(S.PROVIDER_ID, FB.PROVIDER_ID)
        self.assertIs(S.AdapterError, AdapterError)
        self.assertEqual({spec.products[0] for spec in K.SPECS} - set(N.PRODUCTS), set())
        self.assertTrue(callable(S.supply) and callable(S.gate_source) and callable(S.api_access) and callable(S.provider_hosts))
        self.assertEqual(S.api_access(PROVIDER), PROVIDER.access[0])
        self.assertIsNone(S.api_access(H.provider(access=())))


if __name__ == "__main__":
    unittest.main()
