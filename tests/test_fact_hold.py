"""S2C0-a — 재개 직후 글감 순서 안전장치(`fact_candidates.HELD_SPEC_IDS`·`FIRST_SPEC_IDS`) 시험.

문제: 이력에 Fact 글이 없으면 글감 순서(`order`)가 앞선 글감부터 나와 처음 글이 가장 얇은 주간 글감으로 쏠린다(12주 모의: 24편 중 19편, 79%). 제안: 가장 얇은 둘(등급 현황·Kp 폭풍 기준)을
후보에서 임시로 빼고(수집 호출도 하지 않는다) 월별 흑점수를 첫 글로 한다 — 되돌리기는 상수 두 줄(빈 튜플이면 이전 동작과 바이트까지 같다).

못박는 것: ① 상수 모양(실제 글감 id·튜플·겹침 없음 — 오타로 아무것도 안 빼는 일을 막는 구조 시험과 그 검사가 오타를 정말 잡는다는 증거) ② 빈 상수 = 이전 소스를 그대로 옮긴 기준(골든)과 같은 결과(무작위 600 장면)
③ 기본 상수: 제외한 글감은 후보에 없고 나머지 순서는 정해진 대로이며 처음 낼 글감은 한 번도 안 낸 글감 사이에서만 앞선다 ④ 제외·선호는 이력을 건드리지 않는다 — 제외한 글감의 지난 글은 묶음 닫힘·같은 제품 간격에 그대로 쓰이고
제외했다고 '낸 것'으로 세지 않는다 ⑤ 공급 함수 경로: 제외한 글감의 제품은 부르지 않고 첫 글은 월별이다 ⑥ 12주 모의가 설계안의 숫자(79% → 75%)를 코드에서 그대로 다시 낸다 ⑦ 하루·주 상한·열린 초안 상한은
후보와 상관없이 이력만 센다 ⑧ 생성기 분기와 그림자 실행도 같은 기본 상수를 쓴다.
네트워크·시계 없음(오늘은 인자, 난수는 고정 시드뿐)."""
import ast
import datetime
import random
import unittest
from collections import Counter

import _bootstrap
import fact_branch_helpers as FB
import hold_helpers as HH
import space_helpers as H
import test_fact_shadow as TS
import test_space_recipes as TR

from pipeline import fact_candidates as K
from pipeline import fact_supply as S
from pipeline import facts as F
from pipeline import publish_lock

ROOT = _bootstrap.ROOT
SPEC = K.SPEC_BY_ID
ALL = [spec.spec_id for spec in K.SPECS]
DEFAULT_HELD = ("scales_weekly", "kp_storm_weekly")
DEFAULT_FIRST = ("sunspot_monthly_monthly",)
NON_HELD_ORDER = ["kp_weekly", "flares_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"]      # 기본 상수에서 남는 글감을 글감 순서(order)로 늘어놓은 것


def entry(spec_id, day, **extra):
    """이력의 Fact 글 항목 하나(그 글감이 `day` 에 낸 글 — 이 날이 속한 기간의 키)."""
    key = K.candidate_key(SPEC[spec_id], day)
    item = {"date": day if isinstance(day, str) else day.isoformat(), "content_source": "facts", "candidate_key": key, "dedupe_key": f"d|{spec_id}|{day}"}
    item.update(extra)
    return item


def ids(today, history=(), minutes_utc=None):
    return [candidate.spec.spec_id for candidate in K.select_candidates(today, K.made_from_history(list(history)), minutes_utc)]


def old_select_candidates(today, made, minutes_utc=None):
    """S2b 의 `select_candidates` 를 이 변경 전(기준 main)의 소스 그대로 옮긴 골든. 두 상수를 비운 새 함수가 이것과 **같은 결과**를 내야 한다(후보 객체까지 같다)."""
    day = F.as_date(today)
    closed = {K.GROUP_OF[spec.spec_id] for spec in K.SPECS if K.candidate_key(spec, day) in made.keys}
    last_read = {}
    for spec in K.SPECS:
        when = made.last.get(spec.spec_id)
        for product in spec.products if when is not None else ():
            if product not in last_read or when > last_read[product]:
                last_read[product] = when
    eligible = [spec for spec in sorted(K.SPECS, key=lambda item: item.order)
                if len(spec.products) <= K.MAX_PRODUCTS_PER_POST and K.GROUP_OF[spec.spec_id] not in closed and K._data_ready(spec, day) and K._spaced(spec, day, last_read)]
    eligible.sort(key=lambda spec: (made.last.get(spec.spec_id, datetime.date.min), spec.order))
    out, placed = [], set()
    for spec in eligible:
        group = K.GROUP_OF[spec.spec_id]
        if group in placed:
            continue
        placed.add(group)
        for member in (item for item in eligible if K.GROUP_OF[item.spec_id] is group):
            ready = minutes_utc is None or all(minutes_utc >= K.NOT_BEFORE_UTC_MINUTES.get(product, 0) for product in member.products)
            out.append(K.Candidate(member, K.candidate_key(member, day), tuple(sorted(member.params().items())), member.products, ready))
    return tuple(out)


def unknown_ids(values):
    """상수 값 가운데 실제 글감 id 가 아닌 것(오타)."""
    return [value for value in values if value not in K.SPEC_IDS]


class ConstantShapeTest(unittest.TestCase):
    def test_the_defaults_are_the_two_thin_subjects_and_the_monthly_sunspot_subject(self):
        self.assertEqual(HH.PRODUCTION_HELD, DEFAULT_HELD)
        self.assertEqual(HH.PRODUCTION_FIRST, DEFAULT_FIRST)
        self.assertEqual((K.HELD_SPEC_IDS, K.FIRST_SPEC_IDS), (DEFAULT_HELD, DEFAULT_FIRST))              # 이 모듈은 상수를 대체하지 않는다 — 운영 기본값 그대로

    def test_every_id_is_a_real_subject_and_the_constants_are_tuples_without_overlap(self):
        """오타로 아무것도 안 빼는 일(조용한 실패)을 막는다 — 값이 바뀌어도 이 시험이 실제 글감 id 와 대조한다."""
        for name, value in (("HELD_SPEC_IDS", K.HELD_SPEC_IDS), ("FIRST_SPEC_IDS", K.FIRST_SPEC_IDS)):
            with self.subTest(constant=name):
                self.assertIsInstance(value, tuple)
                self.assertEqual(unknown_ids(value), [], f"{name} 에 실제 글감이 아닌 이름이 있다")
                self.assertEqual(len(set(value)), len(value))
                self.assertTrue(all(isinstance(item, str) for item in value))
        self.assertEqual(set(K.HELD_SPEC_IDS) & set(K.FIRST_SPEC_IDS), set())                            # 뺀 글감을 먼저 내라고 할 수는 없다

    def test_the_typo_check_really_sees_a_typo(self):
        self.assertEqual(unknown_ids(("scales_weekly", "scales_week", "Kp_weekly", "")), ["scales_week", "Kp_weekly", ""])
        self.assertEqual(unknown_ids(K.SPEC_IDS), [])

    def test_something_stays_in_every_period_kind_so_holding_can_never_stop_everything(self):
        left = [spec for spec in K.SPECS if spec.spec_id not in K.HELD_SPEC_IDS]
        self.assertEqual({spec.period for spec in left}, {K.PERIOD_WEEK, K.PERIOD_MONTH})
        self.assertGreaterEqual(len({K.GROUP_OF[spec.spec_id] for spec in left}), 3)
        self.assertEqual([spec.spec_id for spec in sorted(left, key=lambda item: item.order)], NON_HELD_ORDER)

    def test_the_order_values_were_not_moved(self):
        """`order` 는 plan_candidates·묶음 순서(GROUPS)·문서의 글감 순서가 쓴다 — 처음 낼 글감은 별도 상수로 정하고 이 값은 그대로다."""
        self.assertEqual({spec.spec_id: spec.order for spec in K.SPECS},
                         {"kp_weekly": 0, "kp_storm_weekly": 1, "flares_weekly": 2, "scales_weekly": 3, "sunspot_daily_monthly": 4, "sunspot_monthly_monthly": 5})


class EmptyConstantsAreTheOldBehaviourTest(unittest.TestCase):
    """빈 튜플이면 이전 동작과 바이트까지 같다 — 소스를 그대로 옮긴 골든과 무작위 장면 600개를 견준다(후보 객체의 모든 칸이 같다)."""

    def random_scene(self, rng):
        day = datetime.date(2026, 1, 1) + datetime.timedelta(days=rng.randint(0, 500))
        history = []
        for spec_id in ALL:
            if rng.random() < 0.55:
                for _ in range(rng.randint(1, 3)):
                    when = day + datetime.timedelta(days=rng.randint(-90, 12))
                    item = entry(spec_id, when)
                    if rng.random() < 0.05:
                        item["date"] = rng.choice(("어제", None, "", 5))
                    history.append(item)
        rng.shuffle(history)
        return day, K.made_from_history(history), rng.choice((None, 0, 29, 30, 600, 1439))

    def test_the_new_function_with_empty_constants_equals_the_old_source_on_600_random_scenes(self):
        rng = random.Random(20261113)
        with HH.policy_off():
            for case in range(600):
                day, made, minutes = self.random_scene(rng)
                with self.subTest(case=case):
                    self.assertEqual(K.select_candidates(day, made, minutes), old_select_candidates(day, made, minutes))

    def test_the_golden_itself_is_not_vacuous_it_differs_from_the_default_on_an_empty_history(self):
        made = K.made_from_history([])
        old = old_select_candidates("2026-11-20", made)
        self.assertEqual([item.spec.spec_id for item in old], ALL)
        with HH.policy_off():
            self.assertEqual(K.select_candidates("2026-11-20", made), old)
        self.assertNotEqual(K.select_candidates("2026-11-20", made), old)                              # 기본 상수는 이전과 다르다 — 시험이 속이 비지 않게

    def test_the_other_functions_are_untouched_by_the_constants(self):
        """`plan_candidates`·`representative`·`conflict_groups`·묶음 표는 상수와 상관없다(S2a 시험이 그대로다)."""
        with HH.policy_off():
            before = ([item.spec.spec_id for item in K.plan_candidates("2026-11-12", ())], K.GROUPS, [K.representative(spec, "2026-11-12").spec_id for spec in K.SPECS])
        after = ([item.spec.spec_id for item in K.plan_candidates("2026-11-12", ())], K.GROUPS, [K.representative(spec, "2026-11-12").spec_id for spec in K.SPECS])
        self.assertEqual(before, after)


class DefaultPolicyTest(unittest.TestCase):
    def test_the_held_subjects_are_not_candidates_and_the_monthly_sunspot_subject_comes_first_from_an_empty_history(self):
        self.assertEqual(ids("2026-11-20"), ["sunspot_monthly_monthly", "kp_weekly", "flares_weekly", "sunspot_daily_monthly"])
        self.assertEqual(ids("2026-11-08"), ["sunspot_monthly_monthly", "kp_weekly", "flares_weekly", "sunspot_daily_monthly"])             # 월별은 8일부터 읽는다
        self.assertEqual(ids("2026-11-07"), ["kp_weekly", "flares_weekly", "sunspot_daily_monthly"])                                      # 아직 8일 전이면 월별은 대상이 아니라 다음 글감이 첫 글이다
        self.assertEqual(ids("2026-11-03"), ["kp_weekly", "flares_weekly", "sunspot_daily_monthly"])
        self.assertEqual(ids("2026-11-02"), ["kp_weekly", "flares_weekly"])
        for day in ("2026-11-09", "2026-11-12", "2026-11-15", "2027-01-09"):
            found = ids(day)
            self.assertFalse(set(found) & set(K.HELD_SPEC_IDS), day)
            self.assertEqual(sorted(found), sorted(NON_HELD_ORDER), day)

    def test_the_rest_keeps_the_subject_order_with_a_never_made_subject_ahead_of_every_made_one(self):
        history = [entry("kp_weekly", "2026-10-26")]
        self.assertEqual(ids("2026-11-20", history), ["sunspot_monthly_monthly", "flares_weekly", "sunspot_daily_monthly", "kp_weekly"])         # 안 낸 글감이 먼저, 이미 낸 Kp 는 뒤
        history = [entry("flares_weekly", "2026-10-05"), entry("kp_weekly", "2026-10-12")]
        self.assertEqual(ids("2026-11-20", history), ["sunspot_monthly_monthly", "sunspot_daily_monthly", "flares_weekly", "kp_weekly"])         # 그 뒤는 오래된 순서

    def test_the_first_preference_never_pulls_a_made_subject_forward_or_beats_the_oldest_first_rule(self):
        made_long_ago = [entry("sunspot_monthly_monthly", "2026-11-10")]                                    # 40일 전(간격 28일을 넘었다)
        self.assertEqual(ids("2026-12-20", made_long_ago), ["kp_weekly", "flares_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"])         # 이미 냈으면 첫 글 선호는 없다
        everyone = [entry(name, "2026-10-12") for name in ("kp_weekly", "flares_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly")]
        self.assertEqual(ids("2026-12-08", everyone), NON_HELD_ORDER)                                      # 같은 날에 냈으면 선호가 아니라 글감 순서가 가른다
        newest_monthly = [entry("kp_weekly", "2026-10-05"), entry("flares_weekly", "2026-10-12"), entry("sunspot_daily_monthly", "2026-10-19"), entry("sunspot_monthly_monthly", "2026-11-02")]
        self.assertEqual(ids("2026-12-08", newest_monthly), ["kp_weekly", "flares_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"])  # 오래 전에 낸 글감이 먼저 — 월별은 가장 최근에 냈으니 맨 뒤

    def test_a_held_subject_never_becomes_made_and_never_closes_its_group(self):
        made = K.made_from_history([])
        before = (dict(made.last), made.keys, made.dedupe)
        first = K.select_candidates("2026-11-12", made)
        self.assertEqual((dict(made.last), made.keys, made.dedupe), before)                                # 선택은 이력을 바꾸지 않는다 — 제외한 글감을 낸 것으로 적지 않는다
        found = [item.spec.spec_id for item in first]
        self.assertIn("kp_weekly", found)                                                                  # Kp 묶음은 닫히지 않았다 — kp_storm_weekly 가 빠졌다고 묶음이 막히지 않는다
        self.assertNotIn("kp_storm_weekly", found)
        self.assertEqual(K.made_from_history([]).keys, frozenset())

    def test_a_never_made_held_subject_does_not_drag_its_group_to_the_front(self):
        """제외하기 전에는 한 번도 안 낸 kp_storm_weekly 가 Kp 묶음 전체를 맨 앞으로 끌었다. 제외하면 묶음은 kp_weekly 자신의 지난 글 날짜로 자리를 정한다."""
        history = [entry("kp_weekly", "2026-10-26")]
        with HH.policy_off():
            self.assertEqual(ids("2026-11-20", history)[:2], ["kp_storm_weekly", "kp_weekly"])
        self.assertEqual(ids("2026-11-20", history)[-1], "kp_weekly")

    def test_history_of_a_held_subject_still_counts_for_closing_and_for_the_same_product_gap(self):
        """제외하기 전에 이미 낸 글은 이력에 남은 사실이다 — 같은 주 묶음 닫힘과 같은 제품 7일 간격에 그대로 쓰인다."""
        for held_entry in (entry("kp_storm_weekly", "2026-11-10"), entry("kp_weekly", "2026-11-10")):
            found = ids("2026-11-12", [held_entry])
            self.assertNotIn("kp_weekly", found, held_entry["candidate_key"])                              # 같은 주(46주)에 이미 냈다
        self.assertNotIn("kp_weekly", ids("2026-11-16", [entry("kp_storm_weekly", "2026-11-10")]))          # 다음 주여도 6일 전에 읽은 같은 Kp 파일이라 막힌다
        self.assertIn("kp_weekly", ids("2026-11-17", [entry("kp_storm_weekly", "2026-11-10")]))             # 7일 뒤부터 다시 나온다
        history = [entry("scales_weekly", "2026-11-10")]
        found = ids("2026-11-12", history)
        self.assertNotIn("scales_weekly", found)
        self.assertEqual(sorted(found), sorted(NON_HELD_ORDER))                                            # 다른 글감은 그대로

    def test_the_constants_are_read_at_every_call_and_unknown_or_total_holds_do_not_raise(self):
        made = K.made_from_history([])
        with HH.policy(("flares_weekly",), ()):
            self.assertEqual(ids("2026-11-20"), ["kp_weekly", "kp_storm_weekly", "scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"])
        with HH.policy(ALL, ()):
            self.assertEqual(K.select_candidates("2026-11-20", made), ())
        with HH.policy(("scales_week", "nonsense"), ("also_unknown",)):                                    # 오타는 조용히 아무것도 안 뺀다 — 그래서 구조 시험이 실제 id 와 대조한다
            self.assertEqual(ids("2026-11-20"), ALL)
        with HH.policy((), ("scales_weekly", "sunspot_monthly_monthly")):                                  # 처음 낼 글감이 둘이면 목록 순서대로
            self.assertEqual(ids("2026-11-20")[:2], ["scales_weekly", "sunspot_monthly_monthly"])

    def test_the_wait_flag_for_the_daily_product_still_works_and_waiting_is_for_the_daily_subject_only(self):
        found = {candidate.spec.spec_id: candidate.ready for candidate in K.select_candidates("2026-11-20", K.made_from_history([]), 10)}
        self.assertEqual(found, {"sunspot_monthly_monthly": True, "kp_weekly": True, "flares_weekly": True, "sunspot_daily_monthly": False})

    def test_the_result_is_a_pure_function_of_the_inputs(self):
        made = K.made_from_history([entry("flares_weekly", "2026-11-03")])
        first = K.select_candidates("2026-11-12", made, 120)
        self.assertEqual(first, K.select_candidates("2026-11-12", made, 120))
        self.assertEqual(first, K.select_candidates(datetime.date(2026, 11, 12), made, 120))


def twelve_week_picks(start=datetime.date(2026, 11, 20), days=84):
    """재개 직후 12주 모의 — 금요일(2026-11-20) 재개, 주 2편(굴러가는 7일)·하루 1편 상한, 협정 세계시 02시 읽기, 매번 성공 가정(설계안의 같은 가정). 돌려주는 값: [(날짜, 글감 id)]."""
    keys, last, posts = set(), {}, []
    for index in range(days):
        day = start + datetime.timedelta(days=index)
        if len([when for when, _name in posts if (day - when).days < 7]) >= 2 or any(when == day for when, _name in posts):
            continue
        found = K.select_candidates(day, K.Made(dict(last), frozenset(keys), frozenset()), minutes_utc=120)
        if not found:
            continue
        pick = found[0]
        posts.append((day, pick.spec.spec_id))
        keys.add(pick.candidate_key)
        last[pick.spec.spec_id] = day
    return posts


class TwelveWeekResumeTest(unittest.TestCase):
    THIN = ("kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly")

    def share(self, posts):
        counts = Counter(name for _day, name in posts)
        thin = sum(counts[name] for name in self.THIN)
        return counts, thin, round(100 * thin / len(posts))

    def test_without_the_constants_the_first_two_dozen_posts_are_79_percent_thin_weekly_subjects(self):
        """설계안(S2C_PLAN)의 표: 지금 규칙 24편 중 19편(79%) — Kp 일별 5·Kp 폭풍 5·플레어 5·등급 4, 일별 흑점수 3·월별 2, 월별 첫 글은 3주 뒤."""
        with HH.policy_off():
            posts = twelve_week_picks()
        counts, thin, percent = self.share(posts)
        self.assertEqual(len(posts), 24)
        self.assertEqual(dict(counts), {"kp_weekly": 5, "kp_storm_weekly": 5, "flares_weekly": 5, "scales_weekly": 4, "sunspot_daily_monthly": 3, "sunspot_monthly_monthly": 2})
        self.assertEqual((thin, percent), (19, 79))
        self.assertEqual(posts[0][1], "kp_weekly")
        self.assertEqual([day.isoformat() for day, name in posts if name == "sunspot_monthly_monthly"][0], "2026-12-11")

    def test_with_the_default_constants_the_first_post_is_the_monthly_one_and_the_share_goes_79_to_75(self):
        """설계안: 임시 제외 + 월별 먼저는 24편 중 18편(75%) — Kp 일별 9·플레어 9·일별 흑점수 3·월별 3. 효과는 작다(구성비는 거의 안 바뀐다) — 주된 이득은 첫 글이 가장 나은 글이 되는 것이다."""
        posts = twelve_week_picks()
        counts, thin, percent = self.share(posts)
        self.assertEqual(len(posts), 24)
        self.assertEqual(dict(counts), {"kp_weekly": 9, "flares_weekly": 9, "sunspot_daily_monthly": 3, "sunspot_monthly_monthly": 3})
        self.assertEqual((thin, percent), (18, 75))
        self.assertEqual(posts[0], (datetime.date(2026, 11, 20), "sunspot_monthly_monthly"))
        self.assertFalse({name for _day, name in posts} & set(K.HELD_SPEC_IDS))

    def test_holding_alone_changes_the_share_to_75_and_the_first_post_preference_changes_only_the_first_post(self):
        with HH.policy(DEFAULT_HELD, ()):
            held_only = twelve_week_picks()
        self.assertEqual(self.share(held_only)[1:], (18, 75))
        self.assertEqual(held_only[0][1], "kp_weekly")                                                     # 첫 글 선호가 없으면 Kp 일별이 첫 글
        both = twelve_week_picks()
        self.assertEqual(Counter(name for _day, name in held_only), Counter(name for _day, name in both))   # 구성은 같고
        self.assertNotEqual([name for _day, name in held_only][:6], [name for _day, name in both][:6])        # 앞 순서만 다르다

    def test_the_default_policy_still_fills_the_weekly_cap_every_week_and_never_makes_a_subject_twice_in_one_period(self):
        posts = twelve_week_picks()
        by_week = Counter(day.isocalendar()[:2] for day, _name in posts)
        self.assertTrue(all(count <= 2 for count in by_week.values()))
        self.assertEqual(sum(by_week.values()), 24)                                                        # 12주 × 주 2편 — 제외한 글감 때문에 건너뛴 주가 없다
        keys = [K.candidate_key(SPEC[name], day) for day, name in posts]
        self.assertEqual(len(keys), len(set(keys)))


class SupplyPathTest(unittest.TestCase):
    DAY = "2026-11-10"
    RETRIEVED = "2026-11-10T01:12:00Z"

    def run_supply(self, noaa, history=(), day=DAY, retrieved=RETRIEVED, **kwargs):
        kwargs.setdefault("limit", 1)
        return S.supply(today=day, retrieved_at=retrieved, history=list(history), provider=H.provider(attribution_template=H.B_TEMPLATE), opener=noaa.transport, **kwargs)

    def test_the_first_post_is_the_monthly_one_and_only_its_product_is_read(self):
        noaa = FB.FakeNoaa(self.DAY)
        result = self.run_supply(noaa)
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["sunspot_monthly_monthly"])
        self.assertEqual(noaa.products(), ["ssn_monthly"])
        self.assertEqual((result.skipped, result.waiting, result.considered), ((), "", ("sunspot_monthly_monthly",)))

    def test_a_big_limit_reads_each_product_of_the_remaining_subjects_once_and_never_the_held_ones(self):
        noaa = FB.FakeNoaa(self.DAY)
        result = self.run_supply(noaa, limit=10)
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["sunspot_monthly_monthly", "kp_weekly", "flares_weekly", "sunspot_daily_monthly"])
        self.assertEqual(noaa.products(), ["ssn_monthly", "kp_estimated", "xray_flares", "ssn_daily"])
        self.assertNotIn("scales", noaa.products())                                                        # 등급 현황 제품은 부르지 않는다 — 수집 호출도 없다
        self.assertEqual(len(noaa.calls), len(set(noaa.calls)))
        with HH.policy_off():
            every = FB.FakeNoaa(self.DAY)
            self.run_supply(every, limit=10)
        self.assertIn("scales", every.products())                                                           # 대조군: 빈 상수에서는 그 제품을 부른다 — 시험이 속이 비지 않게

    def test_when_every_candidate_is_rejected_only_the_remaining_subjects_appear_in_the_reasons(self):
        result = self.run_supply(FB.FakeNoaa(self.DAY), accept=lambda post, candidate: "ALWAYS", limit=10)
        self.assertEqual(result.posts, ())
        self.assertEqual([spec_id for spec_id, _code in result.skipped], ["sunspot_monthly_monthly", "kp_weekly", "flares_weekly", "sunspot_daily_monthly"])
        self.assertEqual(result.considered, tuple(spec_id for spec_id, _code in result.skipped))

    def test_the_fallback_from_a_flat_kp_week_to_the_threshold_subject_is_gone_and_the_next_group_is_tried(self):
        """제외의 대가(문서화한 한계): Kp 대표(kp_weekly)가 자료 부족이면 같은 응답으로 이어 가던 kp_storm_weekly 가 후보에 없어 그 주 Kp 글은 없고 다음 묶음으로 넘어간다."""
        scene = FB.FakeNoaa(self.DAY)
        scene.by_product["kp_estimated"] = TR.kp_rows_on_days([(f"2026-11-{day:02d}", 3.0) for day in (3, 4, 5, 6, 8, 9)])      # 평평하고 최근 사흘 안에 빠진 날 — R04 는 NO_ANALYSIS
        history = [entry("sunspot_monthly_monthly", "2026-11-09")]                                         # 월별을 이미 냈다고 하고 Kp 가 차례가 되게 한다
        result = self.run_supply(scene, history=history)
        self.assertEqual(result.skipped, (("kp_weekly", "INSUFFICIENT:NO_ANALYSIS"),))
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["flares_weekly"])
        self.assertEqual(result.considered, ("kp_weekly", "flares_weekly"))
        with HH.policy_off():
            scene = FB.FakeNoaa(self.DAY)
            scene.by_product["kp_estimated"] = TR.kp_rows_on_days([(f"2026-11-{day:02d}", 3.0) for day in (3, 4, 5, 6, 8, 9)])
            old = self.run_supply(scene, history=history)
        self.assertEqual([candidate.spec.spec_id for candidate in old.candidates], ["kp_storm_weekly"])      # 대조군: 이전에는 같은 응답으로 R05 가 이어졌다

    def test_the_history_of_a_held_subject_still_decides_the_order_through_the_supply_function(self):
        history = [entry("scales_weekly", "2026-11-03"), entry("kp_storm_weekly", "2026-11-05")]           # 제외한 글감의 지난 글: Kp 파일은 5일 전에 읽었다
        noaa = FB.FakeNoaa(self.DAY)
        result = self.run_supply(noaa, history=history, limit=10)
        self.assertEqual([candidate.spec.spec_id for candidate in result.candidates], ["sunspot_monthly_monthly", "flares_weekly", "sunspot_daily_monthly"])       # 7일 간격이 차지 않아 kp_weekly 는 아직 막혀 있다
        self.assertEqual(noaa.products(), ["ssn_monthly", "xray_flares", "ssn_daily"])

    def test_a_six_week_resume_through_the_supply_function_keeps_the_caps_and_never_reads_a_held_product(self):
        """하루 1편·주 2편(굴러가는 7일, `publish_lock` 의 실제 계산)을 지키며 6주 동안 공급 함수를 하루씩 돌린다 — 제외한 글감은 후보에도 이력에도 수집 호출에도 없다."""
        history, picks, reads = [], [], []
        start = datetime.date(2026, 11, 20)
        for offset in range(42):
            day = start + datetime.timedelta(days=offset)
            if publish_lock.posts_today(history, day.isoformat()) >= 1 or publish_lock.weekly_posts(history, [], day).count >= 2:
                continue
            noaa = FB.FakeNoaa(day)
            result = self.run_supply(noaa, history=history, day=day, retrieved=f"{day.isoformat()}T01:12:00Z")
            reads += noaa.products()
            if not result.posts:
                continue
            candidate, post = result.candidates[0], result.posts[0]
            picks.append((day, candidate.spec.spec_id))
            history.append({"date": day.isoformat(), "content_source": "facts", "candidate_key": candidate.candidate_key, "dedupe_key": post.dedupe_key})
        self.assertEqual(len(picks), 12)                                                                   # 6주 × 2편 — 건너뛴 주가 없다
        self.assertEqual(picks[0], (start, "sunspot_monthly_monthly"))
        self.assertFalse({name for _day, name in picks} & set(K.HELD_SPEC_IDS))
        self.assertNotIn("scales", reads)
        self.assertEqual(sorted(set(reads)), ["kp_estimated", "ssn_daily", "ssn_monthly", "xray_flares"])
        self.assertTrue(all(publish_lock.weekly_posts(history, [], day).count <= 2 for day, _name in picks))
        self.assertFalse(any(item["candidate_key"].split(":")[0].rsplit(".", 1)[-1] in K.HELD_SPEC_IDS for item in history))   # 이력에 제외한 글감의 글이 없다


class CapsCountTheHistoryNotTheCandidatesTest(unittest.TestCase):
    def test_the_day_and_week_counts_include_every_entry_whatever_subject_it_is(self):
        """상한 계산은 이력 항목만 센다 — 제외한 글감의 지난 글도 '낸 글'로 그대로 센다(제외가 계산을 줄이지도 늘리지도 않는다)."""
        today = datetime.date(2026, 11, 12)
        history = [entry(name, today - datetime.timedelta(days=gap)) for gap, name in enumerate(ALL)]       # 오늘부터 하루씩 거슬러 여섯 글감 모두
        self.assertEqual(publish_lock.posts_today(history, today.isoformat()), 1)
        self.assertEqual(publish_lock.weekly_posts(history, [], today).count, 6)
        for name in K.HELD_SPEC_IDS:
            without = [item for item in history if not item["candidate_key"].startswith(K.KEY_PREFIX + name + ":")]
            self.assertEqual(publish_lock.weekly_posts(without, [], today).count, 5, name)

    def test_the_candidate_module_and_the_lock_code_do_not_know_each_other(self):
        """제외 상수는 후보 선택만 안다 — 잠금(하루·주·열린 초안 상한)과 승인 흐름 코드는 이 상수를 읽지도 부르지도 않는다."""
        for rel in ("pipeline/publish_lock.py", "pipeline/drafts.py", "pipeline/draft_flow.py", "pipeline/registry.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for name in ("HELD_SPEC_IDS", "FIRST_SPEC_IDS", "fact_candidates"):
                self.assertNotIn(name, text, f"{rel} 가 {name} 을 안다")
        tree = ast.parse((ROOT / "pipeline" / "fact_candidates.py").read_text(encoding="utf-8"))
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(any(name and "publish_lock" in name for name in imported))


class GeneratorBranchTest(FB.FactEnv):
    """생성기의 Fact 분기(운영과 같은 진입)도 같은 기본 상수를 쓴다 — 이력이 빈 첫 실행의 글은 월별 흑점수 글이다."""

    def test_the_first_draft_is_the_monthly_sunspot_post_and_only_that_product_is_read(self):
        value, report, _out, error = self.run_branch()
        self.assertIsNone(error, error)
        self.assertIsNotNone(value, report)
        entry_written = self.history()[-1]
        self.assertEqual(entry_written["candidate_key"], "space_weather.sunspot_monthly_monthly:2026-11")
        self.assertEqual(self.noaa.products(), ["ssn_monthly"])

    def test_the_second_run_a_week_later_makes_the_kp_post_and_no_run_reads_the_held_products(self):
        self.run_branch()
        self.now = FB.at("2026-11-17")
        self.noaa.by_product = FB.payloads(self.now.date())
        self.noaa.calls.clear()
        value, report, _out, error = self.run_branch()
        self.assertIsNone(error, error)
        self.assertIsNotNone(value, report)
        self.assertEqual([item["candidate_key"] for item in self.history()],
                         ["space_weather.sunspot_monthly_monthly:2026-11", "space_weather.kp_weekly:2026-W47"])
        self.assertEqual(self.noaa.products(), ["kp_estimated"])


class ShadowRunTest(TS.ShadowFactsBase):
    """그림자 실행도 같은 공급 함수를 쓰므로 같은 기본 상수가 걸린다 — 평가하는 후보는 남은 네 글감 가운데서 나온다."""

    def test_five_requested_candidates_give_four_posts_in_the_new_order_without_the_held_products(self):
        info, _lines = self.run_shadow("5")
        self.assertEqual(info["attempts"], 4)
        titles = [result["title_ko"] for result in self.results().values()]
        self.assertEqual(len(titles), 4)
        self.assertIn("월평균 흑점수", titles[0])
        self.assertIn("Kp", titles[1])
        self.assertIn("플레어", titles[2])
        self.assertNotIn("scales", self.noaa.products())
        self.assertEqual(sorted(self.noaa.products()), ["kp_estimated", "ssn_daily", "ssn_monthly", "xray_flares"])


if __name__ == "__main__":
    unittest.main()
