"""이력의 발행일을 읽는 후보 선택(S2b, `fact_candidates.select_candidates`·`made_from_history`) 시험: 순서(가장 오래 전에 낸 글감 먼저·한 번도 안 낸 글감이 맨 앞·같은 묶음은 이어서)·묶음 닫힘·같은 제품 간격(자료 창 길이)·
월 글감의 대기일·일별 제품의 협정 세계시 하한·이력 읽기의 관용·**2026년 52주(53주 해 포함) 시뮬레이션 — 주 상한 1·2 에서 여섯 글감이 모두 나온다**(굶는 글감 없음).
S2a 의 `plan_candidates` 시험(test_space_candidates)은 그대로다 — 그 함수는 이력을 보지 않는 순서 도구로 남았다. 네트워크·시계 없이 돈다(오늘은 인자, 난수는 고정 시드뿐)."""
import datetime
import random
import unittest

import _bootstrap  # noqa: F401

from pipeline import fact_candidates as K
from pipeline import publish_lock

SPEC = {spec.spec_id: spec for spec in K.SPECS}
ALL = [spec.spec_id for spec in K.SPECS]


def entry(spec_id, day, **extra):
    """이력의 Fact 글 항목 하나(그 글감이 `day` 에 낸 글 — 이 날이 속한 기간의 키)."""
    key = K.candidate_key(SPEC[spec_id], day)
    item = {"date": day if isinstance(day, str) else day.isoformat(), "content_source": "facts", "candidate_key": key, "dedupe_key": f"d|{spec_id}|{day}"}
    item.update(extra)
    return item


def ids(today, history=(), minutes_utc=None):
    return [candidate.spec.spec_id for candidate in K.select_candidates(today, K.made_from_history(list(history)), minutes_utc)]


class MadeFromHistoryTest(unittest.TestCase):
    def test_only_fact_entries_with_a_known_key_are_read_and_old_entries_are_left_alone(self):
        history = [{"date": "2026-11-01", "topic": "옛 글"}, "문자열 항목", None, 5, {"date": "2026-11-02", "content_source": "feed", "candidate_key": "space_weather.kp_weekly:2026-W45"},
                   {"date": "2026-11-03", "content_source": "facts"}, {"date": "2026-11-03", "content_source": "facts", "candidate_key": "space_weather.unknown_subject:2026-W45"},
                   {"date": "2026-11-03", "content_source": "facts", "candidate_key": "kp_weekly:2026-W45"}, entry("kp_weekly", "2026-11-04")]
        made = K.made_from_history(history)
        self.assertEqual(made.last, {"kp_weekly": datetime.date(2026, 11, 4)})
        self.assertEqual(made.keys, frozenset({"space_weather.kp_weekly:2026-W45"}))
        self.assertEqual(made.dedupe, frozenset({"d|kp_weekly|2026-11-04"}))

    def test_the_latest_day_per_subject_wins_whatever_the_order(self):
        items = [entry("flares_weekly", "2026-10-05"), entry("flares_weekly", "2026-11-02"), entry("flares_weekly", "2026-10-19")]
        for ordered in (items, list(reversed(items)), [items[1], items[0], items[2]]):
            self.assertEqual(K.made_from_history(ordered).last, {"flares_weekly": datetime.date(2026, 11, 2)})

    def test_an_unreadable_date_becomes_the_latest_possible_day_which_blocks_and_sorts_last(self):
        for bad in (None, "", "어제", "2026-13-40", 20261110, ["2026-11-10"], "2026-11-10T10:00:00"):
            with self.subTest(date=bad):
                history = [entry("kp_weekly", "2026-11-04", date=bad)]
                self.assertEqual(K.made_from_history(history).last, {"kp_weekly": datetime.date.max})
                later = ids("2026-11-20", history)                                                     # 같은 제품(Kp)을 읽는 두 글감이 모두 막힌다 — 다른 제품은 그대로
                self.assertNotIn("kp_weekly", later)
                self.assertNotIn("kp_storm_weekly", later)
                self.assertIn("flares_weekly", later)

    def test_a_history_that_is_not_a_list_reads_as_empty(self):
        for value in (None, "문자열", 5, {}, {"a": 1}, object()):
            made = K.made_from_history(value)
            self.assertEqual((made.last, made.keys, made.dedupe), ({}, frozenset(), frozenset()))

    def test_random_garbage_never_raises(self):
        rng = random.Random(20261111)
        pool = [None, "x", 3, 2.5, True, [], {}, {"content_source": "facts"}, {"content_source": "facts", "candidate_key": 5}, {"content_source": 7, "candidate_key": "space_weather.kp_weekly:2026-W45"},
                {"content_source": "facts", "candidate_key": "space_weather.kp_weekly:2026-W45", "date": 5}, entry("scales_weekly", "2026-11-05")]
        for _ in range(300):
            history = [rng.choice(pool) for _ in range(rng.randint(0, 8))]
            made = K.made_from_history(history)
            for day in ("2026-11-10", "2027-01-03"):
                K.select_candidates(day, made, rng.choice((None, 0, 29, 30, 1439)))

    def test_spec_id_of_key(self):
        self.assertEqual(K.spec_id_of_key("space_weather.kp_weekly:2026-W45"), "kp_weekly")
        self.assertEqual(K.spec_id_of_key("space_weather.sunspot_monthly_monthly:2026-11"), "sunspot_monthly_monthly")
        for bad in ("space_weather.kp_weekly", "space_weather.kp_weekly:2026-W4", "space_weather.nope:2026-W45", "kp_weekly:2026-W45", "space_weather.kp_weekly:2026-W45 ", "", None, 5):
            self.assertIsNone(K.spec_id_of_key(bad), bad)


class OrderTest(unittest.TestCase):
    def test_an_empty_history_gives_every_subject_in_subject_order_with_the_kp_pair_together(self):
        for day in ("2026-11-09", "2026-11-12", "2026-11-15"):
            self.assertEqual(ids(day), ["kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"], day)

    def test_weekly_subjects_wait_for_no_weekday_but_monthly_ones_wait_for_their_day_of_the_month(self):
        self.assertEqual(ids("2026-11-09"), ["kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"])
        self.assertEqual(ids("2026-11-02"), ["kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly"])                            # 월요일이어도 주 글감 넷이 모두 나온다(S2a 는 요일을 기다렸다)
        self.assertEqual(ids("2026-11-03"), ["kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly", "sunspot_daily_monthly"])
        self.assertEqual(ids("2026-11-07"), ["kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly", "sunspot_daily_monthly"])
        self.assertEqual(ids("2026-11-08"), ["kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"])
        self.assertEqual(ids("2026-11-07"), ids("2026-11-03"))                                                         # 월 글감의 대기일은 달의 일이다 — 3일부터 일별, 8일부터 월별
        self.assertNotIn("sunspot_daily_monthly", ids("2026-11-02"))

    def test_the_subject_made_longest_ago_comes_first_and_never_made_comes_before_all_made(self):
        history = [entry("flares_weekly", "2026-10-05"), entry("scales_weekly", "2026-10-12"), entry("kp_weekly", "2026-10-19"), entry("kp_storm_weekly", "2026-10-26")]
        order = ids("2026-12-08", history)
        self.assertEqual(order, ["sunspot_daily_monthly", "sunspot_monthly_monthly", "flares_weekly", "scales_weekly", "kp_weekly", "kp_storm_weekly"])        # 안 낸 둘이 맨 앞(글감 순서), 그 뒤는 오래된 순서 — Kp 묶음은 이어서
        order = ids("2026-12-08", history[:1] + [entry(name, "2026-11-30") for name in ("scales_weekly", "kp_weekly", "kp_storm_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly")])
        self.assertEqual(order[0], "flares_weekly")

    def test_ties_are_broken_by_subject_order(self):
        history = [entry(name, "2026-10-12") for name in ALL]
        self.assertEqual(ids("2026-12-08", history), ["kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"])

    def test_the_members_of_a_group_are_adjacent_and_the_group_sits_where_its_oldest_member_is(self):
        # kp_storm_weekly 를 가장 오래 전에, kp_weekly 는 최근에, 플레어는 그 사이에 냈다 → Kp 묶음이 맨 앞(오래된 kp_storm 의 자리)이고 그 안에서도 오래된 kp_storm 이 먼저다
        history = [entry("kp_storm_weekly", "2026-10-05"), entry("flares_weekly", "2026-10-12"), entry("kp_weekly", "2026-11-02")]
        order = ids("2026-12-08", history)
        self.assertEqual(order[:3], ["scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"])                  # 안 낸 셋이 맨 앞(글감 순서)
        self.assertEqual(order[3:], ["kp_storm_weekly", "kp_weekly", "flares_weekly"])                                       # Kp 묶음이 오래된 kp_storm 의 자리 — 플레어(10-12)보다 앞이고 묶음 안은 오래된 순서
        history = [entry("flares_weekly", "2026-10-05"), entry("kp_storm_weekly", "2026-10-12"), entry("kp_weekly", "2026-11-02"), entry("scales_weekly", "2026-11-09"),
                   entry("sunspot_daily_monthly", "2026-11-10"), entry("sunspot_monthly_monthly", "2026-11-10")]
        order = ids("2026-12-14", history)
        self.assertEqual(order, ["flares_weekly", "kp_storm_weekly", "kp_weekly", "scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"])
        positions = {name: index for index, name in enumerate(order)}
        self.assertEqual(abs(positions["kp_weekly"] - positions["kp_storm_weekly"]), 1)

    def test_the_input_order_of_the_history_does_not_change_the_result(self):
        history = [entry("flares_weekly", "2026-10-05"), entry("scales_weekly", "2026-10-12"), entry("kp_weekly", "2026-10-19")]
        base = ids("2026-12-08", history)
        rng = random.Random(1)
        for _ in range(20):
            shuffled = list(history)
            rng.shuffle(shuffled)
            self.assertEqual(ids("2026-12-08", shuffled), base)

    def test_the_day_may_be_a_date_a_datetime_or_text_and_bad_text_is_an_error(self):
        made = K.made_from_history([])
        base = K.select_candidates("2026-11-10", made)
        self.assertEqual(K.select_candidates(datetime.date(2026, 11, 10), made), base)
        self.assertEqual(K.select_candidates(datetime.datetime(2026, 11, 10, 23, 59), made), base)
        for bad in ("2026-13-01", "어제", None, 20261110, "2026-11"):
            with self.assertRaises(Exception):
                K.select_candidates(bad, made)

    def test_candidates_carry_the_key_the_params_and_the_products(self):
        for candidate in K.select_candidates("2026-11-12", K.made_from_history([])):
            self.assertEqual(candidate.candidate_key, K.candidate_key(candidate.spec, "2026-11-12"))
            self.assertEqual(dict(candidate.params), {"key": candidate.spec.key})
            self.assertEqual(candidate.products, candidate.spec.products)
            self.assertTrue(candidate.ready)


class ClosedAndSpacedTest(unittest.TestCase):
    def test_a_subject_made_this_period_closes_its_whole_group_but_not_the_others(self):
        for done in ("kp_weekly", "kp_storm_weekly"):
            order = ids("2026-11-12", [entry(done, "2026-11-10")])
            self.assertNotIn("kp_weekly", order)
            self.assertNotIn("kp_storm_weekly", order)
            self.assertEqual(order, ["flares_weekly", "scales_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly"], done)
        order = ids("2026-11-12", [entry("flares_weekly", "2026-11-10")])
        self.assertNotIn("flares_weekly", order)
        self.assertIn("kp_weekly", order)

    def test_a_period_key_in_the_history_closes_the_group_even_without_a_matching_date(self):
        item = entry("kp_weekly", "2026-11-10", date="깨진 날짜")
        self.assertNotIn("kp_weekly", ids("2026-11-12", [item]))            # 날짜를 못 읽어도 기간 키는 닫는다(막는 쪽)

    def test_the_same_product_is_spaced_by_the_window_not_by_the_period_name(self):
        """S2a 가 못 막은 이웃 기간 겹침(§14-5): 일요일(46주)에 낸 Kp 글과 이틀 뒤 화요일(47주)의 Kp 글 — 이제 이력의 발행일로 막는다. 같은 제품은 7일 뒤(같은 요일)부터 다시 나온다."""
        history = [entry("kp_weekly", "2026-11-15")]                       # 일요일, 46주
        for day, expected in (("2026-11-16", False), ("2026-11-17", False), ("2026-11-21", False), ("2026-11-22", True), ("2026-11-30", True)):
            with self.subTest(day=day):
                self.assertEqual("kp_storm_weekly" in ids(day, history), expected)
                self.assertEqual("kp_weekly" in ids(day, history), expected)
        self.assertIn("flares_weekly", ids("2026-11-16", history))          # 다른 제품은 그대로다

    def test_the_spacing_follows_the_product_so_either_member_of_a_pair_blocks_the_other(self):
        for done, other in (("kp_weekly", "kp_storm_weekly"), ("kp_storm_weekly", "kp_weekly")):
            self.assertNotIn(other, ids("2026-11-18", [entry(done, "2026-11-12")]))        # 6일 뒤(다음 주)

    def test_monthly_subjects_are_spaced_by_a_month_cycle(self):
        history = [entry("sunspot_daily_monthly", "2026-11-30")]
        self.assertNotIn("sunspot_daily_monthly", ids("2026-12-03", history))             # 3일 뒤: 달은 바뀌었지만 같은 제품을 바로 다시 읽지 않는다
        self.assertNotIn("sunspot_daily_monthly", ids("2026-12-27", history))
        self.assertIn("sunspot_daily_monthly", ids("2026-12-28", history))                # 28일 뒤 — 이달 안이다
        history = [entry("sunspot_monthly_monthly", "2026-01-31")]
        self.assertNotIn("sunspot_monthly_monthly", ids("2026-02-27", history))
        self.assertIn("sunspot_monthly_monthly", ids("2026-02-28", history))              # 28일 뒤가 2월의 마지막 날이어도 나온다(그 달 안에서 못 내는 일이 없다)

    def test_the_spacing_never_blocks_a_monthly_subject_for_a_whole_month_after_a_late_post(self):
        """10월 며칠에 냈든(31일이어도) 11월 안에 두 월 글감이 다시 나올 수 있는 날이 있다 — 28일 간격이 '그 달에 못 내는' 일을 만들지 않는다."""
        for last in range(1, 32):
            made = K.made_from_history([entry("sunspot_daily_monthly", datetime.date(2026, 10, last)), entry("sunspot_monthly_monthly", datetime.date(2026, 10, last))])
            seen = {candidate.spec.spec_id for offset in range(30) for candidate in K.select_candidates(datetime.date(2026, 11, 1) + datetime.timedelta(days=offset), made)}
            self.assertLessEqual({"sunspot_daily_monthly", "sunspot_monthly_monthly"}, seen, f"10월 {last}일에 낸 월 글감이 11월 내내 막혔다")

    def test_a_future_dated_entry_blocks_its_product(self):
        self.assertNotIn("flares_weekly", ids("2026-11-10", [entry("flares_weekly", "2026-11-20")]))


class TimeOfDayTest(unittest.TestCase):
    def test_the_daily_product_is_not_ready_before_00_30_utc(self):
        for minutes, ready in ((0, False), (29, False), (30, True), (31, True), (600, True)):
            with self.subTest(minutes=minutes):
                found = {candidate.spec.spec_id: candidate.ready for candidate in K.select_candidates("2026-11-10", K.made_from_history([]), minutes)}
                self.assertEqual(found["sunspot_daily_monthly"], ready)
                self.assertTrue(all(value for name, value in found.items() if name != "sunspot_daily_monthly"))

    def test_without_a_time_everything_is_ready(self):
        self.assertTrue(all(candidate.ready for candidate in K.select_candidates("2026-11-10", K.made_from_history([]), None)))

    def test_the_limit_comes_from_the_table_in_the_module(self):
        self.assertEqual(K.NOT_BEFORE_UTC_MINUTES, {"ssn_daily": 30})
        self.assertEqual(K.WINDOW_DAYS, {"kp_estimated": 7, "xray_flares": 7, "scales": 7, "ssn_daily": 28, "ssn_monthly": 28})
        for spec in K.SPECS:
            for product in spec.products:
                self.assertIn(product, K.WINDOW_DAYS)


# ----------------------------------------------------------------------------
# 굶는 글감 없음: 2026년 52주(53주 해) 시뮬레이션 — 잠금의 하루 1편·주 상한을 두 모양으로 센다: 굴러가는 7일(publish_lock.weekly_posts 와 같다 — 운영의 잠금)과 달력 주(월–일).
# 달력 주 상한은 매주 첫날(월요일)에 낼 수 있는 글감만 나오는 더 가혹한 경우다(S2a 의 §14-7 2항이 말한 '굶는 글감'은 이 모양에서 나온다).
# ----------------------------------------------------------------------------
def week_count(history, day, model):
    if model == "rolling":
        return publish_lock.weekly_posts(history, [], day).count
    week = day.isocalendar()[:2]
    return sum(1 for item in history if datetime.date.fromisoformat(item["date"]).isocalendar()[:2] == week)


def simulate(start, end, weekly_cap, model="rolling", picker=None, daily_cap=1):
    """start–end(양끝 포함)를 하루씩: 잠금(하루 daily_cap 편·주 상한 weekly_cap 편 — model 이 rolling 이면 굴러가는 7일, calendar 면 달력 주)이 허락하는 날 첫 후보 하나를 낸다.
    picker(day, history) → spec_id 또는 None 이 없으면 S2b 의 선택(select_candidates, 협정 세계시 10시 = 읽어도 되는 시각)이다. 돌려주는 값: [(날짜, spec_id)]."""
    history, posts = [], []
    day = start
    while day <= end:
        if publish_lock.posts_today(history, day.isoformat()) < daily_cap and week_count(history, day, model) < weekly_cap:
            if picker is not None:
                chosen = picker(day, history)
            else:
                ready = [candidate for candidate in K.select_candidates(day, K.made_from_history(history), minutes_utc=600) if candidate.ready]
                chosen = ready[0].spec.spec_id if ready else None
            if chosen:
                history.append(entry(chosen, day))
                posts.append((day, chosen))
        day += datetime.timedelta(days=1)
    return posts


def old_policy(day, history):
    """S2a 의 `plan_candidates`: 하루 한 번 부르고 첫 후보를 낸다(요일 대기·주 번호 회전)."""
    first = K.next_candidate(day, {item["candidate_key"] for item in history})
    return first.spec.spec_id if first is not None else None


class NoStarvationTest(unittest.TestCase):
    YEAR = (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
    MODELS = ("rolling", "calendar")

    def test_every_subject_comes_around_in_2026_with_a_weekly_cap_of_one_and_of_two(self):
        for model in self.MODELS:
            for cap in (1, 2):
                with self.subTest(model=model, cap=cap):
                    posts = simulate(*self.YEAR, weekly_cap=cap, model=model)
                    counts = {spec_id: sum(1 for _day, name in posts if name == spec_id) for spec_id in ALL}
                    self.assertTrue(all(counts.values()), counts)                                   # 여섯 글감이 모두 한 번 이상 나왔다
                    self.assertGreaterEqual(len(posts), 52 * cap, (model, cap, len(posts)))          # 주 상한을 다 쓴다(굶는 주가 없다)
                    self.assertLessEqual(len(posts), 53 * cap + 1)
                    self.assertGreaterEqual(min(counts.values()), 8 if cap == 1 else 12, counts)
                    weekly = [counts[name] for name in ("kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly")]
                    self.assertLessEqual(max(weekly) - min(weekly), 2, counts)                      # 주 글감 넷은 거의 같은 횟수(한쪽으로 쏠리지 않는다)

    def test_no_subject_waits_longer_than_a_bounded_time_between_two_posts(self):
        for model in self.MODELS:
            for cap, bound in ((1, 8 * 7), (2, 6 * 7)):
                posts = simulate(*self.YEAR, weekly_cap=cap, model=model)
                for spec_id in ALL:
                    days = [day for day, name in posts if name == spec_id]
                    gaps = [(b - a).days for a, b in zip(days, days[1:])]
                    self.assertTrue(gaps, (model, cap, spec_id))
                    self.assertLessEqual(max(gaps), bound, (model, cap, spec_id, max(gaps)))

    def test_two_posts_that_read_the_same_product_are_always_a_window_apart(self):
        for model in self.MODELS:
            for cap in (1, 2, 3):
                posts = simulate(*self.YEAR, weekly_cap=cap, model=model)
                last = {}
                for day, spec_id in posts:
                    for product in SPEC[spec_id].products:
                        if product in last:
                            self.assertGreaterEqual((day - last[product]).days, K.WINDOW_DAYS[product], (model, cap, day, spec_id, product))
                        last[product] = day

    def test_a_subject_is_never_made_twice_in_the_same_period_and_a_pair_shares_one_period(self):
        for model in self.MODELS:
            posts = simulate(datetime.date(2026, 1, 1), datetime.date(2027, 3, 31), weekly_cap=2, model=model)
            keys = [K.candidate_key(SPEC[spec_id], day) for day, spec_id in posts]
            self.assertEqual(len(keys), len(set(keys)))
            groups = {}
            for day, spec_id in posts:
                period = (K.GROUP_OF[spec_id][0].spec_id, K.period_id(SPEC[spec_id], day))
                groups[period] = groups.get(period, 0) + 1
            self.assertEqual(max(groups.values()), 1)                                               # 같은 제품을 읽는 글감은 한 기간(주·달)에 하나만

    def test_the_53_week_years_do_not_repeat_one_representative_and_still_cover_every_subject(self):
        """53주 해(2009·2015·2020·2026·2032·2037)에는 W53 과 이듬해 W01 이 모두 홀수라 S2a 의 대표가 두 주 연속 같았다(§14-7 4항). 이제 순서가 주 번호가 아니라 이력이라 그 일이 없다 —
        해마다 연말·연초 여섯 달씩을 시뮬레이션해 Kp 묶음의 두 글감이 같은 글감만 연달아 나오지 않고 번갈아 나오며 모든 글감이 나온다."""
        for year in (2009, 2015, 2020, 2026, 2032, 2037):
            with self.subTest(year=year):
                self.assertEqual(datetime.date(year, 12, 28).isocalendar()[1], 53)
                for model in self.MODELS:
                    posts = simulate(datetime.date(year, 10, 1), datetime.date(year + 1, 3, 31), weekly_cap=2, model=model)
                    kp = [name for _day, name in posts if name in ("kp_weekly", "kp_storm_weekly")]
                    self.assertEqual(set(kp), {"kp_weekly", "kp_storm_weekly"})
                    self.assertTrue(all(first != second for first, second in zip(kp, kp[1:])), (model, kp))
                    self.assertEqual({name for _day, name in posts}, set(ALL))

    def test_the_old_policy_starves_under_a_calendar_week_cap_which_is_the_control_for_the_tests_above(self):
        """대조군(시험이 속이 비지 않게): 같은 시뮬레이션을 S2a 의 `plan_candidates` 로 돌리면 달력 주 상한 1 에서 플레어·등급 글감이, 2 에서 등급 글감이 한 번도 나오지 않고 3 에서 모두 나온다(§14-7 2항이 적은
        현상 그대로). 굴러가는 7일(운영의 잠금)에서는 그 현상이 같은 모양으로 나오지 않지만 요일을 기다리는 규칙이라는 약점은 그대로다 — 새 선택은 요일을 기다리지 않는다."""
        for cap, missing in ((1, {"flares_weekly", "scales_weekly"}), (2, {"scales_weekly"}), (3, set())):
            posts = simulate(*self.YEAR, weekly_cap=cap, model="calendar", picker=old_policy)
            self.assertGreater(len(posts), 40)
            self.assertEqual(set(ALL) - {name for _day, name in posts}, missing, cap)
            self.assertEqual(set(ALL) - {name for _day, name in simulate(*self.YEAR, weekly_cap=cap, model="calendar")}, set())      # 새 선택은 같은 조건에서 모두 나온다


if __name__ == "__main__":
    unittest.main()
