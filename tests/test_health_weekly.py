"""워치독 주 단위 보완(결함 D-169 해소 — 주 1–2편 운영에서는 '글이 며칠 없음'이 정상) 시험: pipeline/health.py 의 evaluate(..., weekly_cap=…).

배경: 운영자 승인 008 의 재개 조건은 '주 1–2편'이고 제한 재개 잠금(M038)이 굴러가는 7일에 최대 2편을 코드로 지킨다. 그런데 워치독의 STALE(Chance 36시간)·NO_POSTS_DAY 는 하루 한 편에 가깝던 때의 기준이라
정상 운영 중에도 며칠씩 울린다 — 켜는 순간부터 거짓 경보가 쌓인다. weekly_cap(기본 None = 이전과 같음)이 주어지면 ① STALE 허용 시간이 설정값에 7일(WEEK_WINDOW_DAYS × 24시간)을 더한 값이 되고
② NO_POSTS_DAY 는 울리지 않는다. 그 밖(FAIL_STREAK·RUN_FAIL_STREAK·REJECT_STREAK·UNPUBLISHED·PAGES_*·NO_ACTIVITY·DRAFT_WAITING 변환)은 그대로다.

여기서 보는 것: ① 꺼진 상태(키워드 없음·None·올바르지 않은 값)의 출력이 수정 전과 바이트까지 같다(입력 격자의 지문 — 지문은 수정 전 코드에서 얻었다) ② 켜진 상태의 허용 시간 경계(정확히·1분 전·1분 뒤)와 문구
③ NO_POSTS_DAY 없음 ④ 나머지 검사는 그대로(격자 전체를 '허용 시간을 늘린 이전 판정'과 견주는 대조) ⑤ 승인 흐름의 DRAFT_WAITING 변환 ⑥ 상한 값(1·2·올바르지 않은 값)과 블로그 속성(mode·post_days·얕은 복제·이력 날짜 이상)
⑦ 두 달 치 흉내(정상 운영·늘 늦게 승인하는 운영에서 거짓 경보 0, 이틀 연속 못 만들면 STALE, 갑자기 밀린 승인은 승인 대기 경고).
네트워크·실제 시계·실제 레지스트리 없이 돈다(시각은 고정값). 경로·줄 끝이 값에 들어가지 않아 윈도·리눅스에서 같다.
"""
import hashlib
import inspect
import itertools
import json
import unittest
from datetime import date, datetime, timedelta, timezone

import _bootstrap  # noqa: F401
from pipeline import health, publish_lock
from pipeline.state import KST

NOW = datetime(2026, 11, 12, 3, 0, tzinfo=timezone.utc)              # KST 2026-11-12(목) 12:00 — 워치독 첫 정기 실행(UTC 03:30)과 같은 시간대
NOW_MIDNIGHT = datetime(2026, 11, 11, 15, 30, tzinfo=timezone.utc)   # KST 2026-11-12 00:30 — 두 번째 정기 실행(UTC 15:30)
GAP, EXTRA = 36, 168                                                 # Chance 설정값 36시간 · 주 단위에서 더하는 7일(시간) — 허용 시간은 204
ALLOWED = GAP + EXTRA
CHANCE = {"key": "chance", "platform": "jekyll-git", "mode": "auto", "publish_flow": "pr",
          "health": {"max_gap_hours": GAP, "max_failure_streak": 3}}
DIRECT_CHANCE = {key: value for key, value in CHANCE.items() if key != "publish_flow"}
BLOGGER = {"key": "b", "platform": "blogger", "mode": "auto", "health": {"max_gap_hours": 50, "max_failure_streak": 3}}
PACKAGE = {"key": "t", "platform": "tistory", "mode": "package", "health": {"max_gap_hours": 50, "max_failure_streak": 3}}


def at(hours_ago, now=NOW):
    return now - timedelta(hours=hours_ago)


def entry(status, hours_ago, now=NOW, date_only=False):
    """KST 시각 now - hours_ago 에 만들어진 이력 항목(date 와 generated_at 이 서로 맞는다)."""
    when = at(hours_ago, now).astimezone(KST)
    item = {"status": status, "date": when.date().isoformat()}
    if not date_only:
        item["generated_at"] = when.isoformat()
    return item


def iso_z(when):
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def waiting(*hours_ago, now=NOW):
    """열린 초안 PR 목록(승인 흐름): 각 초안이 열린 지 hours_ago 시간."""
    return [{"number": 40 + index, "created_at": iso_z(at(hours, now))} for index, hours in enumerate(hours_ago)]


def kst_day(now, offset=0):
    return now.astimezone(KST).date() + timedelta(days=offset)


def pairs(findings):
    return [(f.code, f.severity) for f in findings]


def codes(findings):
    return sorted(f.code for f in findings)


# ---------------------------------------------------------------------------------------------
# 입력 격자 — 꺼진 상태 지문과 대조 시험이 같이 쓴다
# ---------------------------------------------------------------------------------------------
GRID_BLOGS = {
    "chance_pr": CHANCE,
    "chance_direct": DIRECT_CHANCE,
    "blogger_auto": BLOGGER,
    "blogger_draft": {**BLOGGER, "mode": "draft"},
    "package": PACKAGE,
    "off": {**BLOGGER, "mode": "off"},
    "no_health": {"key": "n", "platform": "blogger", "mode": "auto"},                     # 허용 시간을 적지 않으면 기본 48시간
    "short_streak": {**CHANCE, "health": {"max_gap_hours": 12, "max_failure_streak": 2}},
}


def grid_histories(now):
    """이력 변형들(상태·날짜가 정상인 것부터 깨진 것까지)."""
    return {
        "empty": [],
        "fresh": [entry("posted", 5, now)],
        "old_80h": [entry("posted", 80, now)],
        "two_old": [entry("posted", 150, now), entry("posted", 260, now)],
        "failures": [entry("posted", 70, now), entry("publish_failed", 48, now), entry("llm_failed", 24, now), entry("publish_failed", 1, now)],
        "rejects": [entry("posted", 90, now)] + [entry("rejected", hours, now) for hours in (40, 30, 20, 10, 1)],
        "unpublished": [entry("posted", 30, now), entry("generated_unpublished", 2, now)],
        "date_only": [{"date": kst_day(now, -1).isoformat(), "topic": "상태 없는 옛 항목"}, {"date": kst_day(now, -6).isoformat(), "topic": "더 옛 항목"}],
        "package": [entry("package_issued", 60, now), entry("draft_uploaded", 100, now)],
        "garbage": ["문자열 항목", {"date": "garbage"}, {"status": "posted"}, {"status": "posted", "generated_at": "nope", "date": "아님"}, entry("draft", 3, now)],
        "future": [entry("posted", -48, now), entry("posted", 400, now)],
        "pr_flow": [{**entry("posted", 20, now), "flow": "pr"}, {**entry("posted", 200, now), "flow": "pr"}],
    }


def grid_cells(now=NOW, blog_names=None, history_names=None):
    """(블로그, 이력, 지금, 마지막 글 커밋, 글 날짜 집합, 최근 실행, 배포 실행, 열린 초안 PR) 조합 전체."""
    blogs = [GRID_BLOGS[name] for name in (blog_names or GRID_BLOGS)]
    histories = grid_histories(now)
    histories = [histories[name] for name in (history_names or histories)]
    commits = (None, at(3, now), at(40, now), at(100, now), at(250, now))
    day_sets = (None, set(), {kst_day(now, -1)}, {kst_day(now, -5)}, {kst_day(now)})
    runs = ((), [{"conclusion": "failure"}] * 3)
    pages = (None, [{"conclusion": "failure", "created_at": iso_z(at(1, now))}])
    pending = (None, [], waiting(3, now=now), waiting(100, now=now), [{"number": 1}])
    return [(blog, history, now, commit, days, recent, deploy, drafts)
            for blog, history, commit, days, recent, deploy, drafts in itertools.product(blogs, histories, commits, day_sets, runs, pages, pending)]


def evaluate_cell(cell, **extra):
    blog, history, now, commit, days, recent, deploy, drafts = cell
    return health.evaluate(blog, history, now, last_content_commit=commit, recent_runs=recent, post_days=days, pages_runs=deploy, pending_drafts=drafts, **extra)


def digest(cells, **extra):
    """격자 칸마다 evaluate 결과(블로그·코드·심각도·문구)를 한 줄로 적어 sha256 으로 접는다 → (지문, 칸 수)."""
    parts = []
    for cell in cells:
        found = evaluate_cell(cell, **extra)
        parts.append(json.dumps([[f.blog, f.code, f.severity, f.message] for f in found], ensure_ascii=False))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest(), len(parts)


def all_cells():
    return grid_cells(NOW) + grid_cells(NOW_MIDNIGHT, blog_names=("chance_pr", "blogger_auto", "package"))


# 수정 전 코드(origin/main b6b5ea7 의 pipeline/health.py)에서 같은 격자로 얻은 값. 꺼진 상태는 이 지문과 같아야 한다.
OFF_STATE_DIGEST = ("6972e92ae44f8f99ab9a1b3bf941826785b59600d6608f89f604c04151dfe7f2", 66000)


class OffStateUnchangedTest(unittest.TestCase):
    """꺼진 상태 — 키워드를 주지 않거나 None 이거나 올바르지 않은 값이면 모든 칸의 결과가 수정 전과 바이트까지 같다."""

    def test_the_grid_is_big_enough_to_mean_something(self):
        cells = all_cells()
        self.assertGreaterEqual(len(cells), 10000)
        kinds = set()
        for cell in cells[::7]:
            kinds.update(f.code for f in evaluate_cell(cell))
        self.assertTrue({"STALE", "NO_POSTS_DAY", "NO_ACTIVITY", "FAIL_STREAK", "REJECT_STREAK", "UNPUBLISHED", "DRAFT_WAITING", "RUN_FAIL_STREAK", "PAGES_NOT_DEPLOYED", "PAGES_FAILED"} <= kinds, sorted(kinds))

    def test_without_the_keyword_every_cell_is_what_it_was(self):
        self.assertEqual(digest(all_cells()), OFF_STATE_DIGEST)

    def test_with_none_every_cell_is_what_it_was(self):
        self.assertEqual(digest(all_cells(), weekly_cap=None), OFF_STATE_DIGEST)

    def test_with_a_value_that_is_not_a_positive_integer_every_cell_is_what_it_was(self):
        """0·음수·참/거짓·소수·문자열·목록 같은 값은 주 단위로 읽지 않는다(경보가 더 울리는 쪽 — 안전한 쪽)."""
        cells = all_cells()[::25]
        expected = digest(cells)
        self.assertGreaterEqual(expected[1], 2000)
        for value in (0, -1, -36, True, False, 1.0, 2.0, 1.5, "2", "", [2], (2,), {}, {"cap": 2}, object):
            with self.subTest(value=value):
                self.assertEqual(digest(cells, weekly_cap=value), expected)

    def test_the_default_of_the_keyword_is_none_and_it_is_keyword_only(self):
        parameter = inspect.signature(health.evaluate).parameters["weekly_cap"]
        self.assertIsNone(parameter.default)
        self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(list(inspect.signature(health.evaluate).parameters)[:8],
                         ["blog", "history", "now", "last_content_commit", "recent_runs", "post_days", "pages_runs", "pending_drafts"])   # 예전 인자의 순서·이름은 그대로

    def test_a_blog_that_is_off_stays_empty_in_both_modes(self):
        self.assertEqual(health.evaluate({**CHANCE, "mode": "off"}, [], NOW, weekly_cap=2), [])
        self.assertEqual(health.evaluate({**CHANCE, "mode": "off"}, [], NOW), [])


class WeeklyConstantsTest(unittest.TestCase):
    def test_the_extra_time_is_the_lock_window_in_hours_taken_from_the_lock_module(self):
        self.assertEqual(health.WEEK_WINDOW_DAYS, publish_lock.WEEK_WINDOW_DAYS)
        self.assertEqual(health.WEEKLY_EXTRA_HOURS, publish_lock.WEEK_WINDOW_DAYS * 24)
        self.assertEqual(health.WEEKLY_EXTRA_HOURS, EXTRA)
        self.assertEqual(GAP + health.WEEKLY_EXTRA_HOURS, ALLOWED)
        self.assertEqual(ALLOWED, 204)                                                      # 문서가 말하는 Chance 의 허용 시간

    def test_the_cap_reader_accepts_only_positive_integers(self):
        for value in (1, 2, 3, 7, 14, 10 ** 9):
            self.assertEqual(health.weekly_mode_cap(value), value)
        for value in (None, 0, -1, True, False, 1.0, 2.5, "2", "", [1], {}, object):
            self.assertIsNone(health.weekly_mode_cap(value), value)


class WeeklyStaleBoundaryTest(unittest.TestCase):
    """STALE 허용 시간은 설정값 + 168시간(Chance 36 → 204). 경계는 정확히·1분 전·1분 뒤."""

    def run_stale(self, minutes_ago, cap, blog=CHANCE, **kw):
        commit = NOW - timedelta(minutes=minutes_ago)
        return health.evaluate(blog, [], NOW, last_content_commit=commit, weekly_cap=cap, **kw)

    def test_exactly_the_allowed_time_is_fine_one_minute_after_is_stale_one_minute_before_is_fine(self):
        limit = ALLOWED * 60
        for cap in (1, 2):
            with self.subTest(cap=cap):
                self.assertEqual(self.run_stale(limit - 1, cap), [])
                self.assertEqual(self.run_stale(limit, cap), [])
                found = self.run_stale(limit + 1, cap)
                self.assertEqual(pairs(found), [("STALE", "critical")])
                self.assertEqual(found[0].title, "[Watchdog] chance: STALE")

    def test_the_old_limit_is_not_enough_to_raise_it_any_more(self):
        for hours in (GAP + 1, 40, 60, 100, 150, 200, 203):
            with self.subTest(hours=hours):
                self.assertEqual(pairs(self.run_stale(hours * 60, None)), [("STALE", "critical")])        # 예전 기준에서는 울린다
                self.assertEqual(self.run_stale(hours * 60, 2), [])                                      # 주 단위에서는 아니다

    def test_the_old_boundary_is_unchanged_without_the_keyword(self):
        limit = GAP * 60
        self.assertEqual(self.run_stale(limit - 1, None), [])
        self.assertEqual(self.run_stale(limit, None), [])
        self.assertEqual(pairs(self.run_stale(limit + 1, None)), [("STALE", "critical")])

    def test_the_extra_time_is_added_to_the_configured_value_whatever_it_is(self):
        cases = ((12, 180), (48, 216), (36.5, 204.5), (72, 240))
        for gap, allowed in cases:
            blog = {**CHANCE, "health": {"max_gap_hours": gap, "max_failure_streak": 3}}
            minutes = int(allowed * 60)
            with self.subTest(gap=gap):
                self.assertEqual(self.run_stale(minutes, 2, blog=blog), [])
                self.assertEqual(pairs(self.run_stale(minutes + 1, 2, blog=blog)), [("STALE", "critical")])
        no_health = {"key": "chance", "platform": "jekyll-git", "mode": "auto"}                          # health 를 적지 않으면 기본 48시간
        self.assertEqual(self.run_stale((48 + EXTRA) * 60, 2, blog=no_health), [])
        self.assertEqual(pairs(self.run_stale((48 + EXTRA) * 60 + 1, 2, blog=no_health)), [("STALE", "critical")])

    def test_the_cap_value_does_not_change_the_time_only_the_sentence(self):
        for hours in (100, 204, 205, 300):
            with self.subTest(hours=hours):
                self.assertEqual(pairs(self.run_stale(hours * 60, 1)), pairs(self.run_stale(hours * 60, 2)))
                self.assertEqual(pairs(self.run_stale(hours * 60, 1)), pairs(self.run_stale(hours * 60, 14)))

    def test_the_message_names_the_weekly_basis_the_cap_and_both_times(self):
        last = NOW - timedelta(hours=210)
        stamp = last.astimezone(KST).strftime("%Y-%m-%d %H:%M")
        for cap in (1, 2):
            message = self.run_stale(210 * 60, cap)[0].message
            self.assertEqual(message, f"마지막 활동({stamp} KST) 이후 210시간 경과 (허용 204시간 — 주 단위 기준(상한 {cap}편): 설정값 36시간에 7일을 더했습니다).")
        old = self.run_stale(210 * 60, None)[0].message
        self.assertEqual(old, f"마지막 활동({stamp} KST) 이후 210시간 경과 (허용 36시간).")               # 꺼진 상태의 문구는 그대로
        self.assertNotIn("주 단위", old)

    def test_a_stale_alert_keeps_its_severity_and_the_package_hint(self):
        found = self.run_stale(300 * 60, 2, blog={**CHANCE, "mode": "package"})
        self.assertEqual(pairs(found), [("STALE", "critical")])
        self.assertTrue(found[0].message.endswith(health.PACKAGE_STALE_HINT))
        self.assertIn("주 단위 기준(상한 2편)", found[0].message)


class WeeklyNoPostsDayTest(unittest.TestCase):
    """글이 없는 날이 정상 운영이다 — NO_POSTS_DAY 는 주 단위 모드에서 울리지 않는다."""

    def evaluate(self, days, cap, history=(), now=NOW, blog=CHANCE):
        """마지막 글은 30시간 전(STALE 이 아니다), 글 날짜 집합은 days."""
        return health.evaluate(blog, list(history), now, last_content_commit=at(30, now), post_days=days, weekly_cap=cap)

    def test_two_closed_days_without_a_post_were_critical_and_are_silent_now(self):
        days = {kst_day(NOW, -5)}
        self.assertEqual(pairs(self.evaluate(days, None)), [("NO_POSTS_DAY", "critical")])
        for cap in (1, 2):
            self.assertEqual(self.evaluate(days, cap), [])

    def test_yesterday_without_a_post_was_a_warning_and_is_silent_now(self):
        days = {kst_day(NOW, -2)}
        self.assertEqual(pairs(self.evaluate(days, None)), [("NO_POSTS_DAY", "warning")])
        self.assertEqual(self.evaluate(days, 2), [])

    def test_the_same_holds_for_a_history_without_post_days_like_a_shallow_clone(self):
        history = [entry("posted", 24 * 5)]
        self.assertEqual(pairs(self.evaluate(None, None, history)), [("NO_POSTS_DAY", "critical")])
        self.assertEqual(self.evaluate(None, 2, history), [])

    def test_the_midnight_run_is_silent_too(self):
        days = {kst_day(NOW_MIDNIGHT, -4)}
        self.assertEqual(pairs(self.evaluate(days, None, now=NOW_MIDNIGHT)), [("NO_POSTS_DAY", "critical")])
        self.assertEqual(self.evaluate(days, 2, now=NOW_MIDNIGHT), [])

    def test_no_new_alert_is_made_while_resting_at_the_cap(self):
        """상한에 닿아 쉬는 동안(마지막 글 6일 전, 최근 6일 동안 글이 없는 날뿐)에는 아무 경보도 없다 — 정보 알림도 새로 만들지 않는다."""
        history = [entry("posted", 24 * 6)]
        found = health.evaluate(CHANCE, history, NOW, last_content_commit=at(24 * 6), post_days={kst_day(NOW, -6)}, weekly_cap=1)
        self.assertEqual(found, [])

    def test_a_blog_that_is_not_auto_never_had_this_alert(self):
        days = {kst_day(NOW, -5)}
        for mode in ("draft", "package"):
            self.assertEqual(self.evaluate(days, None, blog={**CHANCE, "mode": mode}), [])
            self.assertEqual(self.evaluate(days, 2, blog={**CHANCE, "mode": mode}), [])


class WeeklyKeepsTheOtherChecksTest(unittest.TestCase):
    """살아 있음은 STALE·FAIL_STREAK·RUN_FAIL_STREAK·REJECT_STREAK·UNPUBLISHED·PAGES_*·NO_ACTIVITY 가 그대로 본다."""

    def both(self, blog=CHANCE, history=(), commit=None, post_days=None, **kw):
        """같은 입력을 이전 기준과 주 단위 기준으로. 어제 글이 있는 것으로 둔다(post_days) — 하루 단위 NO_POSTS_DAY 가 끼어 비교가 흐려지지 않게."""
        days = {kst_day(NOW, -1)} if post_days is None else post_days
        off = health.evaluate(blog, list(history), NOW, last_content_commit=commit, post_days=days, **kw)
        weekly = health.evaluate(blog, list(history), NOW, last_content_commit=commit, post_days=days, weekly_cap=2, **kw)
        return off, weekly

    def assertSame(self, off, weekly, code):
        self.assertIn(code, codes(off))
        self.assertEqual(weekly, off)

    def test_failure_streak(self):
        history = [entry("posted", 70), entry("publish_failed", 48), entry("llm_failed", 24), entry("publish_failed", 1)]
        off, weekly = self.both(history=history, commit=at(5))
        self.assertSame(off, weekly, "FAIL_STREAK")

    def test_reject_streak(self):
        history = [entry("rejected", hours) for hours in (40, 30, 20, 10, 1)]
        off, weekly = self.both(history=history, commit=at(5))
        self.assertSame(off, weekly, "REJECT_STREAK")

    def test_unpublished(self):
        off, weekly = self.both(history=[entry("posted", 30), entry("generated_unpublished", 2)], commit=at(2))
        self.assertSame(off, weekly, "UNPUBLISHED")

    def test_workflow_run_failure_streak(self):
        off, weekly = self.both(history=[entry("posted", 5)], commit=at(5), recent_runs=[{"conclusion": "failure"}] * 3)
        self.assertSame(off, weekly, "RUN_FAIL_STREAK")

    def test_site_deployment_checks(self):
        runs = [{"conclusion": "failure", "created_at": iso_z(at(4.8))}, {"conclusion": "success", "created_at": iso_z(at(30))}]
        off, weekly = self.both(commit=at(5), post_days={kst_day(NOW)}, pages_runs=runs)
        self.assertSame(off, weekly, "PAGES_NOT_DEPLOYED")
        self.assertIn("PAGES_FAILED", codes(weekly))

    def test_no_activity_at_all(self):
        off, weekly = self.both()
        self.assertEqual(codes(off), ["NO_ACTIVITY"])
        self.assertEqual(weekly, off)

    def test_the_alerts_that_are_weekly_aware_are_exactly_two(self):
        """주 단위 모드가 바꾸는 코드는 STALE(허용 시간)·NO_POSTS_DAY(없음)·그에 딸린 DRAFT_WAITING 뿐이다 — 새 코드는 없다."""
        seen = set()
        for cell in all_cells()[::3]:
            seen.update(f.code for f in evaluate_cell(cell, weekly_cap=2))
        self.assertTrue(seen <= {"STALE", "NO_ACTIVITY", "FAIL_STREAK", "REJECT_STREAK", "UNPUBLISHED", "DRAFT_WAITING", "RUN_FAIL_STREAK", "PAGES_NOT_DEPLOYED", "PAGES_FAILED"}, sorted(seen))
        self.assertNotIn("NO_POSTS_DAY", seen)


class WeeklyDifferentialTest(unittest.TestCase):
    """격자 전체를 '설정값에 168시간을 더한 이전 판정'과 견준다: 주 단위 모드 = 허용 시간만 늘린 이전 판정에서 NO_POSTS_DAY(와 그 때문에 생긴 DRAFT_WAITING)를 뺀 것이다."""

    BASIS = " — 주 단위 기준(상한 %d편): 설정값 %s시간에 7일을 더했습니다"

    @staticmethod
    def widened(blog):
        gap = blog.get("health", {}).get("max_gap_hours", 48)
        return {**blog, "health": {**blog.get("health", {}), "max_gap_hours": gap + EXTRA}}, gap

    def expected(self, cell, cap):
        """이전 판정(허용 시간만 gap+168 로 늘린 블로그)에서: 승인 대기 변환 전에 STALE 이 울리지 않는 칸이면 NO_POSTS_DAY 와 그것이 바뀐 DRAFT_WAITING 을 뺀다. 울리는 칸은 그대로(STALE 문구에 주 단위 근거만 더한다)."""
        blog, history, now, commit, days, recent, deploy, drafts = cell
        wide, gap = self.widened(blog)
        arguments = dict(last_content_commit=commit, recent_runs=recent, post_days=days, pages_runs=deploy)
        stale_fires = any(f.code == "STALE" for f in health.evaluate(wide, history, now, **arguments))              # 열린 초안 목록이 없는 판정 — 변환 전의 STALE
        reference = health.evaluate(wide, history, now, pending_drafts=drafts, **arguments)
        found = reference if stale_fires else [f for f in reference if f.code not in ("NO_POSTS_DAY", "DRAFT_WAITING")]
        old_basis = "(허용 %s시간)" % (gap + EXTRA)
        new_basis = "(허용 %s시간%s)" % (gap + EXTRA, self.BASIS % (cap, gap))
        return [health.Finding(f.blog, f.code, f.severity, f.message.replace(old_basis, new_basis, 1)) if f.code == "STALE" else f for f in found]

    def test_every_cell_is_the_widened_old_verdict_without_the_daily_alert(self):
        checked = 0
        cells = all_cells()
        for cap, step in ((2, 1), (1, 4)):                           # 상한 2 는 모든 칸, 상한 1 은 네 칸에 하나(허용 시간은 상한 값과 무관하고 문구에만 값이 든다 — 아래 시험이 따로 본다)
            for cell in cells[::step]:
                got = evaluate_cell(cell, weekly_cap=cap)
                want = self.expected(cell, cap)
                if got != want:
                    self.fail("칸 %r 상한 %d: 기대 %r, 실제 %r" % ((cell[0].get("key"), cell[3], cell[4], cell[7]), cap, pairs(want), pairs(got)))
                checked += 1
        self.assertGreaterEqual(checked, 80000)

    def test_the_grid_really_contains_the_places_where_the_two_modes_differ(self):
        """대조가 공허하지 않게: 격자에는 (a) 허용 시간 사이(36 초과 204 이하)에서 갈리는 칸 (b) NO_POSTS_DAY 로 갈리는 칸 (c) DRAFT_WAITING 이 사라지는 칸이 모두 있다."""
        only_old_stale = only_old_npd = old_waiting_gone = 0
        for cell in all_cells()[::3]:
            off = codes(evaluate_cell(cell))
            weekly = codes(evaluate_cell(cell, weekly_cap=2))
            only_old_stale += "STALE" in off and "STALE" not in weekly
            only_old_npd += "NO_POSTS_DAY" in off and "NO_POSTS_DAY" not in weekly
            old_waiting_gone += "DRAFT_WAITING" in off and "DRAFT_WAITING" not in weekly
        self.assertGreater(only_old_stale, 100)
        self.assertGreater(only_old_npd, 50)
        self.assertGreater(old_waiting_gone, 20)


class WeeklyPendingDraftsTest(unittest.TestCase):
    """승인 흐름(publish_flow: pr)의 DRAFT_WAITING 변환은 그대로이고, 새 허용 시간 기준으로 STALE 이 울릴 때만 일어난다."""

    def evaluate(self, drafts, hours=210, cap=2, blog=CHANCE, **kw):
        return health.evaluate(blog, [], NOW, last_content_commit=at(hours), pending_drafts=drafts, weekly_cap=cap, **kw)

    def test_a_draft_waiting_inside_the_weekly_time_makes_no_alert_at_all(self):
        """예전에는 마지막 글 36시간 뒤부터 DRAFT_WAITING(+3일 넘으면 STALE 경고)이 울렸다. 주 단위에서는 204시간 전까지 조용하다."""
        for hours in (40, 100, 150, 203):
            with self.subTest(hours=hours):
                self.assertEqual(pairs(self.evaluate(waiting(100), hours=hours, cap=None)), [("DRAFT_WAITING", "warning"), ("STALE", "warning")])
                self.assertEqual(self.evaluate(waiting(100), hours=hours), [])

    def test_past_the_weekly_time_a_young_draft_gives_waiting_only(self):
        self.assertEqual(pairs(self.evaluate(waiting(30))), [("DRAFT_WAITING", "warning")])
        self.assertEqual(pairs(self.evaluate(waiting(5, 71))), [("DRAFT_WAITING", "warning")])

    def test_past_the_weekly_time_an_old_draft_keeps_a_stale_warning_next_to_waiting(self):
        found = self.evaluate(waiting(100))
        self.assertEqual(pairs(found), [("DRAFT_WAITING", "warning"), ("STALE", "warning")])
        stale = found[1]
        self.assertTrue(stale.message.startswith("마지막 활동("))
        self.assertIn("허용 204시간 — 주 단위 기준(상한 2편)", stale.message)
        self.assertTrue(stale.message.endswith(health.STALL_HINT))

    def test_the_seventy_two_hour_boundary_is_unchanged(self):
        for hours, expected in ((71.9, ["DRAFT_WAITING"]), (72, ["DRAFT_WAITING", "STALE"]), (72.1, ["DRAFT_WAITING", "STALE"])):
            with self.subTest(hours=hours):
                self.assertEqual(codes(self.evaluate(waiting(hours))), expected)
        self.assertEqual(health.DRAFT_STALL_HOURS, 72)

    def test_the_oldest_draft_decides(self):
        self.assertEqual(codes(self.evaluate(waiting(5, 100))), ["DRAFT_WAITING", "STALE"])
        self.assertEqual(codes(self.evaluate(waiting(100, 5))), ["DRAFT_WAITING", "STALE"])

    def test_an_unreadable_waiting_time_keeps_the_stale_warning_with_the_unknown_hint(self):
        for drafts in ([{"number": 1}], [{"number": 1, "created_at": "엉터리"}], ["문자열"]):
            with self.subTest(drafts=drafts):
                found = self.evaluate(drafts)
                self.assertEqual(pairs(found), [("DRAFT_WAITING", "warning"), ("STALE", "warning")])
                self.assertTrue(found[1].message.endswith(health.STALL_HINT_UNKNOWN))

    def test_without_open_drafts_or_with_an_unreadable_list_the_stale_stays_critical(self):
        for drafts in (None, []):
            self.assertEqual(pairs(self.evaluate(drafts)), [("STALE", "critical")])

    def test_the_direct_flow_ignores_the_list(self):
        self.assertEqual(pairs(self.evaluate(waiting(100), blog=DIRECT_CHANCE)), [("STALE", "critical")])
        self.assertEqual(pairs(self.evaluate(waiting(100), blog={**CHANCE, "publish_flow": "direct"})), [("STALE", "critical")])

    def test_the_daily_alert_is_not_turned_into_waiting_any_more(self):
        """예전: 어제·그제 글이 없고 열린 초안이 있으면 NO_POSTS_DAY 가 DRAFT_WAITING 이 됐다. 주 단위: 아무것도 없다(승인 대기 알림은 확인 필요 모음이 맡는다)."""
        days = {kst_day(NOW, -5)}
        old = health.evaluate(CHANCE, [], NOW, last_content_commit=at(30), post_days=days, pending_drafts=waiting(5))
        self.assertEqual(pairs(old), [("DRAFT_WAITING", "warning")])
        new = health.evaluate(CHANCE, [], NOW, last_content_commit=at(30), post_days=days, pending_drafts=waiting(5), weekly_cap=2)
        self.assertEqual(new, [])

    def test_other_alerts_stay_next_to_both(self):
        found = self.evaluate(waiting(100), recent_runs=[{"conclusion": "failure"}] * 3)
        self.assertEqual(codes(found), ["DRAFT_WAITING", "RUN_FAIL_STREAK", "STALE"])


class WeeklyBlogShapeTest(unittest.TestCase):
    """블로그 mode·post_days 있음/없음(얕은 복제)·이력 날짜 이상."""

    def test_mode_off_returns_nothing_even_when_nothing_ever_happened(self):
        self.assertEqual(health.evaluate({**CHANCE, "mode": "off"}, [], NOW, last_content_commit=at(999), weekly_cap=2), [])

    def test_draft_and_package_modes_get_the_wider_time_too(self):
        for mode in ("draft", "package"):
            blog = {**CHANCE, "mode": mode}
            with self.subTest(mode=mode):
                self.assertEqual(health.evaluate(blog, [], NOW, last_content_commit=at(150), weekly_cap=2), [])
                self.assertEqual(pairs(health.evaluate(blog, [], NOW, last_content_commit=at(150))), [("STALE", "critical")])
                self.assertEqual(pairs(health.evaluate(blog, [], NOW, last_content_commit=at(210), weekly_cap=2)), [("STALE", "critical")])

    def test_a_shallow_clone_has_no_post_days_and_no_commit_time_and_only_the_history_counts(self):
        """얕은 복제: post_days 와 last_content_commit 이 모두 없다(None) — 이력의 정확한 시각이 마지막 활동이다."""
        history = [entry("posted", 150)]
        self.assertEqual(health.evaluate(CHANCE, history, NOW, weekly_cap=2), [])
        self.assertEqual(pairs(health.evaluate(CHANCE, history, NOW)), [("STALE", "critical")])
        history = [entry("posted", 210)]
        self.assertEqual(pairs(health.evaluate(CHANCE, history, NOW, weekly_cap=2)), [("STALE", "critical")])

    def test_date_only_entries_assume_the_end_of_that_kst_day_when_no_commit_time_is_known(self):
        history = [{"date": kst_day(NOW, -7).isoformat(), "topic": "t"}]            # 7일 전 23:59 KST = 약 156시간 전
        self.assertEqual(health.evaluate(CHANCE, history, NOW, weekly_cap=2), [])
        history = [{"date": kst_day(NOW, -9).isoformat(), "topic": "t"}]            # 9일 전 23:59 KST = 약 204시간 전 직후
        found = health.evaluate(CHANCE, history, NOW, weekly_cap=2)
        self.assertEqual(pairs(found), [("STALE", "critical")])

    def test_unreadable_or_future_history_dates_do_not_crash_or_change_the_rule(self):
        junk = ["문자열", {"date": "garbage"}, {"status": "posted"}, {"status": "posted", "generated_at": "nope"}, {"status": "posted", "date": "2026-13-45"}, None, 7]
        self.assertEqual(codes(health.evaluate(CHANCE, junk, NOW, weekly_cap=2)), ["NO_ACTIVITY"])          # 읽을 수 있는 시각이 하나도 없다
        self.assertEqual(health.evaluate(CHANCE, junk, NOW, last_content_commit=at(150), weekly_cap=2), [])       # 커밋 시각이 마지막 활동이다
        self.assertEqual(pairs(health.evaluate(CHANCE, junk, NOW, last_content_commit=at(210), weekly_cap=2)), [("STALE", "critical")])
        future = [entry("posted", -72)]                                                                         # 앞으로 3일 뒤의 이력 항목: 경과 시간이 음수라 STALE 은 아니다
        self.assertEqual(health.evaluate(CHANCE, future, NOW, weekly_cap=2), [])
        self.assertEqual(pairs(health.evaluate(CHANCE, future, NOW)), [("NO_POSTS_DAY", "critical")])             # 이전 기준에서는 어제·그제 글이 없어 하루 단위 알림이 울린다

    def test_post_days_given_or_not_changes_nothing_in_weekly_mode(self):
        for days in (None, set(), {kst_day(NOW, -9)}, {kst_day(NOW)}):
            with self.subTest(days=days):
                self.assertEqual(health.evaluate(CHANCE, [], NOW, last_content_commit=at(150), post_days=days, weekly_cap=2), [])
                self.assertEqual(pairs(health.evaluate(CHANCE, [], NOW, last_content_commit=at(210), post_days=days, weekly_cap=2)), [("STALE", "critical")])

    def test_a_blog_that_is_not_chance_gets_the_same_rule_when_the_caller_passes_the_cap(self):
        """evaluate 는 순수 함수라 블로그 이름을 보지 않는다 — 누구에게 넘길지는 부르는 쪽(scripts/watchdog.py: Chance 에만)이 정한다."""
        self.assertEqual(health.evaluate(BLOGGER, [], NOW, last_content_commit=at(100), weekly_cap=2), [])
        self.assertEqual(pairs(health.evaluate(BLOGGER, [], NOW, last_content_commit=at(100))), [("STALE", "critical")])

    def test_the_input_is_not_changed(self):
        blog, history, drafts = json.loads(json.dumps(CHANCE)), [entry("posted", 210)], waiting(100)
        snapshot = json.dumps([blog, history, drafts], sort_keys=True)
        health.evaluate(blog, history, NOW, last_content_commit=at(210), pending_drafts=drafts, weekly_cap=2)
        self.assertEqual(json.dumps([blog, history, drafts], sort_keys=True), snapshot)


# ---------------------------------------------------------------------------------------------
# 두 달 치 흉내 — 가드(publish_lock)가 정하는 만든 날과 워치독(하루 두 번)을 같이 돌린다
# ---------------------------------------------------------------------------------------------
START = date(2026, 11, 2)                          # 월요일 — 켠 직후의 첫 날
SLOTS = ((9, 17), (18, 17))                        # 글 만들기 실행 시각(KST) — 슬롯 9시·18시의 첫 정기 실행
CHECKS = ((0, 30), (12, 30))                       # 워치독 정기 실행(UTC 15:30·03:30)의 한국 시각


def simulate(cap, days=70, failed=(), weekly=True, merge_delay=0, date_only=False, seed_delay=None):
    """매일 두 슬롯에서 가드의 규칙(하루 1편·굴러가는 7일에 cap 편 — publish_lock 의 같은 함수)이 허락하면 글(승인 대기 초안)을 만들고(failed 에 든 날짜는 못 만든다), 하루 두 번 워치독을 돌린다.
    켜기 직전 7일 전에 글 한 편이 있었던 것으로 시작한다(그 글은 만든 지 seed_delay 시간 뒤에 병합됐다 — 기본은 merge_delay 와 같다: 평소처럼 늘 같은 만큼 늦게 승인하는 운영). 운영자는 초안을 만든 지 merge_delay 시간 뒤에 병합한다 —
    글 커밋 시각(마지막 활동)은 병합 시각이고, 병합 전의 초안은 열린 초안 목록으로 넘어간다. 기본(merge_delay 0)은 가장 빠른 경우(만들자마자 병합). date_only 면 이력 항목이 실제 Chance 처럼 날짜만 갖는다(generated_at 없음).
    돌려주는 값: (워치독 실행마다 (KST 시각, 코드 목록), 만든 날짜 목록)."""
    seed = datetime.combine(START - timedelta(days=7), datetime.min.time().replace(hour=9, minute=17), tzinfo=KST)

    def item(day, when, branch):
        base = {"date": day.isoformat(), "flow": "pr", "branch": branch}
        return base if date_only else {**base, "generated_at": when.isoformat()}

    history = [item(seed.date(), seed, "ai/draft/%s-s9" % seed.date().isoformat())]
    seed_merged = seed + timedelta(hours=merge_delay if seed_delay is None else seed_delay)
    commit, post_days, made, runs, unmerged = seed_merged, {seed_merged.astimezone(KST).date()}, [], [], []
    for offset in range(days):
        today = START + timedelta(days=offset)
        events = sorted([(hour, minute, "post") for hour, minute in SLOTS] + [(hour, minute, "check") for hour, minute in CHECKS])
        for hour, minute, kind in events:
            when = datetime(today.year, today.month, today.day, hour, minute, tzinfo=KST)
            for created, merged in list(unmerged):                       # 이 시각까지 병합된 초안: 글 커밋(마지막 활동)이 생기고 목록에서 빠진다
                if merged <= when:
                    commit = max(commit, merged)
                    post_days.add(merged.astimezone(KST).date())
                    unmerged.remove((created, merged))
            if kind == "post":
                allowed = (today not in failed and publish_lock.posts_today(history, today.isoformat()) < publish_lock.MAX_POSTS_PER_DAY
                           and publish_lock.weekly_posts(history, [], today).count < cap)
                if allowed:
                    history.append(item(today, when, "ai/draft/%s-s%d" % (today.isoformat(), hour)))
                    unmerged.append((when, when + timedelta(hours=merge_delay)))
                    made.append(today)
            else:
                waiting_now = [{"created_at": iso_z(created)} for created, _ in unmerged]
                found = health.evaluate(CHANCE, list(history), when, last_content_commit=commit, post_days=set(post_days), pending_drafts=waiting_now or None, weekly_cap=cap if weekly else None)
                runs.append((when, sorted(f.code for f in found)))
    return runs, made


class WeeklySimulationTest(unittest.TestCase):
    def test_the_simulated_guard_makes_what_the_lock_promises(self):
        """흉내 자체가 맞는지: 상한 1 이면 7일마다 한 편, 상한 2 이면 이틀 연속 두 편 뒤 5일 쉰다(어느 7일에도 상한을 넘지 않는다)."""
        _, made = simulate(1)
        self.assertEqual(made[:4], [START + timedelta(days=7 * n) for n in range(4)])
        _, made = simulate(2)
        self.assertEqual(made[:6], [START, START + timedelta(days=1), START + timedelta(days=7), START + timedelta(days=8), START + timedelta(days=14), START + timedelta(days=15)])
        for cap in (1, 2):
            _, made = simulate(cap)
            for first in made:
                window = [day for day in made if first <= day < first + timedelta(days=7)]
                self.assertLessEqual(len(window), cap)

    def test_a_normal_run_of_ten_weeks_raises_no_false_alarm_in_weekly_mode_at_either_cap(self):
        for cap in (1, 2):
            runs, made = simulate(cap)
            self.assertGreaterEqual(len(made), 10)
            self.assertEqual([(when.isoformat(), found) for when, found in runs if found], [], "상한 %d" % cap)

    def test_a_slow_operator_causes_no_false_alarm_either(self):
        """평소 승인이 늘 같은 만큼 늦어도(초안을 만든 뒤 0·30·60·100시간에 병합) 병합 커밋 사이의 간격은 같은 7일이라 주 단위 기준은 조용하다. 이력은 실제 Chance 처럼 날짜만 있고, 병합 전의 초안은 열린 초안 목록으로 같이 넘어간다."""
        for cap in (1, 2):
            for delay in (0, 30, 60, 100):
                with self.subTest(cap=cap, delay=delay):
                    runs, made = simulate(cap, merge_delay=delay, date_only=True)
                    self.assertGreaterEqual(len(made), 10)
                    self.assertEqual([(when.isoformat(), found) for when, found in runs if found], [])

    def test_a_sudden_slowdown_in_approval_gives_a_waiting_warning_and_never_a_critical_alert(self):
        """평소 바로 병합하던 운영자가 한 번 미루면(그 뒤로는 늘 같은 만큼 늦다) 그 한 번은 마지막 병합 뒤 204시간을 넘겨 승인 대기 경고(DRAFT_WAITING)가 울린다 — 심각(STALE critical)이 아니다.
        열린 초안이 3일(72시간) 이상 기다리면 STALE 경고가 그 옆에 함께 남는다(R2-2, 그대로). 그 한 번이 지나면 다시 조용하다."""
        runs, _ = simulate(1, merge_delay=60, seed_delay=0, date_only=True)
        alarms = [(when, found) for when, found in runs if found]
        self.assertEqual(len(alarms), 2)
        self.assertEqual({tuple(found) for _, found in alarms}, {("DRAFT_WAITING",)})
        self.assertTrue(all(when.date() <= START + timedelta(days=3) for when, _ in alarms))                  # 처음 한 번뿐 — 그 뒤로는 조용하다
        runs, _ = simulate(1, merge_delay=100, seed_delay=0, date_only=True)
        alarms = [(when, found) for when, found in runs if found]
        self.assertGreaterEqual(len(alarms), 5)
        self.assertEqual({tuple(found) for _, found in alarms}, {("DRAFT_WAITING",), ("DRAFT_WAITING", "STALE")})   # STALE 은 늘 DRAFT_WAITING 옆의 경고다(승인 대기가 있으면 심각 STALE 은 없다)
        self.assertTrue(all(when.date() <= START + timedelta(days=5) for when, _ in alarms))

    def test_the_old_rule_would_have_cried_wolf_all_the_time_on_the_same_run(self):
        """같은 흉내를 이전 기준(36시간·NO_POSTS_DAY)으로 돌리면 정상 운영 중에도 점검 140번 가운데 90번이 넘게 울린다 — 이 보완이 있는 이유."""
        for cap, at_least in ((1, 100), (2, 80)):
            runs, _ = simulate(cap, weekly=False)
            cried = [found for _, found in runs if found]
            self.assertGreaterEqual(len(cried), at_least, "상한 %d: 울린 횟수 %d" % (cap, len(cried)))
            self.assertTrue({code for found in cried for code in found} <= {"STALE", "NO_POSTS_DAY"})
        runs, _ = simulate(1, weekly=False, merge_delay=60, date_only=True)                        # 늦게 병합하면 열린 초안이 있는 동안 승인 대기 경고로 바뀌어 울린다
        self.assertGreaterEqual(len([found for _, found in runs if found]), 100)

    def test_one_day_without_any_post_is_tolerated(self):
        """열리는 날(7일 뒤)에 하루 종일 못 만들면 다음 날 09:17 에 만든다(마지막 활동 뒤 약 183시간) — 허용 204시간 안이다."""
        runs, made = simulate(1, failed={START + timedelta(days=7)})
        self.assertIn(START + timedelta(days=8), made)
        self.assertEqual([found for _, found in runs if found], [])

    def test_two_days_without_any_post_raise_stale_before_the_third_day(self):
        """이틀 연속 못 만들면 사흘째 00:30 의 점검(마지막 활동 뒤 207시간)이 STALE 을 낸다 — 상한이 열린 뒤 이틀 안에 드러난다."""
        runs, made = simulate(1, failed={START + timedelta(days=7), START + timedelta(days=8)})
        self.assertIn(START + timedelta(days=9), made)
        alarms = [(when, found) for when, found in runs if found]
        self.assertEqual(len(alarms), 1)
        when, found = alarms[0]
        self.assertEqual(found, ["STALE"])
        self.assertEqual((when.date(), when.hour, when.minute), (START + timedelta(days=9), 0, 30))

    def test_a_long_outage_keeps_the_alarm_ringing_until_a_post_is_made(self):
        runs, made = simulate(2, failed={START + timedelta(days=offset) for offset in range(7, 20)}, days=24)
        self.assertEqual(made, [START, START + timedelta(days=1), START + timedelta(days=20), START + timedelta(days=21)])
        ringing = [(when.date(), found) for when, found in runs if found == ["STALE"]]
        self.assertGreaterEqual(len(ringing), 20)
        self.assertEqual([found for when, found in runs if found and when.date() >= START + timedelta(days=21)], [])


if __name__ == "__main__":
    unittest.main()
