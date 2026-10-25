"""워치독 규칙 보강: 하루 단위 NO_POSTS_DAY, 첫 번째부터 UNPUBLISHED, 사이트 배포 검사(PAGES_*), 날짜만 있는 항목 처리.

배경(Task 4 진단): 워크플로는 초록인데 글이 없던 것을 워치독이 약 52시간 뒤에야, 그것도 담당자 없는 이슈 한 건으로만
알렸다. 초안을 정상 활동으로 세어 Blogger 중단도 가려졌다. 여기서는 그 빈틈을 규칙으로 고정한다.
"""
import unittest
from datetime import date, datetime, timedelta, timezone

import _bootstrap  # noqa: F401
from pipeline import health
from pipeline.state import KST

NOW = datetime(2026, 10, 25, 3, 0, tzinfo=timezone.utc)  # KST 2026-10-25 12:00
# 워치독의 두 번째 정기 실행(UTC 15:30)은 KST 로 날짜가 막 바뀐 00:30 이다. UTC 로는 아직 10-24 다.
NOW_MIDNIGHT = datetime(2026, 10, 24, 15, 30, tzinfo=timezone.utc)  # KST 2026-10-25 00:30
AUTO = {"key": "b", "platform": "blogger", "mode": "auto",
        "health": {"max_gap_hours": 200, "max_failure_streak": 3}}
CHANCE = {"key": "chance", "platform": "jekyll-git", "mode": "auto",
          "health": {"max_gap_hours": 200, "max_failure_streak": 3}}


def entry(status, days_ago, hour=10, reasons=None):
    when = (NOW.astimezone(KST) - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0, microsecond=0)
    item = {"status": status, "generated_at": when.isoformat(), "date": when.date().isoformat()}
    if reasons is not None:
        item["reasons"] = reasons
    return item


def kst_entry(status, when_kst):
    """KST 시각 when_kst 에 만들어진 이력 항목(date·generated_at 이 서로 맞는다)."""
    return {"status": status, "generated_at": when_kst.isoformat(), "date": when_kst.date().isoformat()}


def codes(findings):
    return sorted(f.code for f in findings)


class NoPostsDayTest(unittest.TestCase):
    def test_no_post_yesterday_is_a_warning(self):
        findings = health.evaluate(AUTO, [entry("posted", 2)], NOW)
        self.assertEqual(codes(findings), ["NO_POSTS_DAY"])
        self.assertEqual(findings[0].severity, "warning")
        self.assertIn("2026-10-24", findings[0].message)

    def test_two_days_without_posts_is_critical(self):
        findings = health.evaluate(AUTO, [entry("posted", 3)], NOW)
        self.assertEqual(codes(findings), ["NO_POSTS_DAY"])
        self.assertEqual(findings[0].severity, "critical")
        self.assertIn("2026-10-23", findings[0].message)
        self.assertIn("2026-10-24", findings[0].message)

    def test_a_post_yesterday_is_fine(self):
        self.assertEqual(health.evaluate(AUTO, [entry("posted", 1)], NOW), [])

    def test_a_post_today_means_recovered_even_after_a_gap(self):
        """복구 직후(오늘 글이 나옴)에는 지난 공백으로 다시 알리지 않는다."""
        history = [entry("posted", 5), entry("posted", 0)]
        self.assertEqual(health.evaluate(AUTO, history, NOW), [])

    def test_drafts_and_unpublished_are_not_posts(self):
        """저장소 초안이 쌓이는 것을 '글이 나왔다'로 세지 않는다(예전 워치독의 맹점)."""
        history = [entry("posted", 5), entry("draft", 1), entry("generated_unpublished", 0)]
        found = codes(health.evaluate(AUTO, history, NOW))
        self.assertIn("UNPUBLISHED", found)
        self.assertIn("NO_POSTS_DAY", found)

    def test_blogger_draft_uploaded_counts_as_a_real_post_on_its_day(self):
        """draft_uploaded 는 Blogger 초안 모드(후속 작업)용 예약 상태 이름이다. 그 상태의 항목이 있는 날이 '글이 있는 날'이어야 하고,
        상수에서 빼면 이 테스트가 실패해야 한다(예전 단언은 항목 하나만 두고 []를 기대해서, 빼도 통과하는 공허한 테스트였다)."""
        older = entry("posted", 5)        # 이전 글이 있어야 '글이 하루도 없는 블로그'(NO_ACTIVITY 쪽)로 빠지지 않는다
        self.assertEqual(health.evaluate(AUTO, [older, entry("draft_uploaded", 1)], NOW), [])    # 어제 글 있음
        found = health.evaluate(AUTO, [older, entry("draft_uploaded", 3)], NOW)                  # 어제·그제 글 없음
        self.assertEqual(codes(found), ["NO_POSTS_DAY"])
        self.assertEqual(found[0].severity, "critical")
        self.assertEqual(health.post_days_from_history([entry("draft_uploaded", 1)]), {date(2026, 10, 24)})
        self.assertIn("draft_uploaded", health.REAL_POST_STATUSES)

    def test_which_statuses_make_a_day_a_post_day(self):
        """글이 있는 날로 세는 상태와 세지 않는 상태를 한 번에 고정한다."""
        statuses = {"posted": True, "draft_uploaded": True, "draft": False, "generated_unpublished": False,
                    "rejected": False, "llm_failed": False, "publish_failed": False, "skipped_no_topic": False}
        for status, counts in statuses.items():
            with self.subTest(status=status):
                days = health.post_days_from_history([entry(status, 1)])
                self.assertEqual(days, {date(2026, 10, 24)} if counts else set())

    def test_draft_mode_blog_is_not_checked(self):
        self.assertEqual(health.evaluate({**AUTO, "mode": "draft"}, [entry("posted", 5)], NOW), [])

    def test_stale_already_covers_it(self):
        blog = {**AUTO, "health": {"max_gap_hours": 24, "max_failure_streak": 3}}
        found = codes(health.evaluate(blog, [entry("posted", 4)], NOW))
        self.assertEqual(found, ["STALE"])  # 같은 원인으로 이슈를 두 개 만들지 않는다

    def test_git_post_days_are_used_for_jekyll_blogs(self):
        yesterday = NOW.astimezone(KST).date() - timedelta(days=1)
        commit = NOW - timedelta(hours=20)
        findings = health.evaluate(CHANCE, [], NOW, last_content_commit=commit, post_days={yesterday})
        self.assertEqual(findings, [])
        older = {yesterday - timedelta(days=3)}
        findings = health.evaluate(CHANCE, [], NOW, last_content_commit=commit, post_days=older)
        self.assertEqual(codes(findings), ["NO_POSTS_DAY"])

    def test_legacy_status_less_entries_count_as_posts_on_their_date(self):
        """Chance 의 history.json 항목에는 status 가 없다 — 정상 발행으로 보고 그 날짜를 '글이 있는 날'로 센다.
        (예전 단언은 항목 하나만 두고 []를 기대해서, 상태 없는 항목을 세지 않아도 통과했다.)"""
        older = {"date": "2026-10-20", "topic": "상태 없는 더 옛 항목"}
        self.assertEqual(health.evaluate(CHANCE, [older, {"date": "2026-10-24", "topic": "어제 글"}], NOW), [])
        found = health.evaluate(CHANCE, [older, {"date": "2026-10-23", "topic": "그제 글"}], NOW)   # 어제만 비었다
        self.assertEqual(codes(found), ["NO_POSTS_DAY"])
        self.assertEqual(found[0].severity, "warning")
        self.assertEqual(health.post_days_from_history([older, {"date": "2026-10-23"}, {"date": "2026-10-24"}]),
                         {date(2026, 10, 20), date(2026, 10, 23), date(2026, 10, 24)})

    def test_a_blog_that_never_posted_is_left_to_no_activity(self):
        self.assertEqual(codes(health.evaluate(AUTO, [], NOW)), ["NO_ACTIVITY"])

    def test_a_run_just_after_kst_midnight_judges_the_kst_day_that_just_closed(self):
        """UTC 15:30 에 도는 점검은 KST 로는 날짜가 바뀐 직후다. '오늘/어제/그제'는 KST 날짜로 잡는다(UTC 날짜로 잡으면
        한 칸씩 밀려 아래 경고가 사라진다)."""
        self.assertEqual(NOW_MIDNIGHT.astimezone(KST).date(), date(2026, 10, 25))
        history = [kst_entry("posted", datetime(2026, 10, 23, 20, 0, tzinfo=KST))]        # 그제 저녁에 글 1건
        found = health.evaluate(AUTO, history, NOW_MIDNIGHT)
        self.assertEqual(codes(found), ["NO_POSTS_DAY"])
        self.assertEqual(found[0].severity, "warning")                                     # 막 끝난 어제(10-24)에 글이 없다
        self.assertIn("2026-10-24", found[0].message)
        # 같은 시각, 글 날짜 집합(Chance 는 git 에서 구해 넘긴다)으로도 마찬가지
        commit = NOW_MIDNIGHT - timedelta(hours=28)
        found = health.evaluate(CHANCE, [], NOW_MIDNIGHT, last_content_commit=commit, post_days={date(2026, 10, 23)})
        self.assertEqual(codes(found), ["NO_POSTS_DAY"])
        self.assertEqual(health.evaluate(CHANCE, [], NOW_MIDNIGHT, last_content_commit=commit,
                                         post_days={date(2026, 10, 24)}), [])             # 어제 글이 있으면 정상

    def test_two_closed_kst_days_without_posts_at_the_midnight_run_is_critical(self):
        history = [kst_entry("posted", datetime(2026, 10, 22, 20, 0, tzinfo=KST))]
        found = health.evaluate(AUTO, history, NOW_MIDNIGHT)
        self.assertEqual([(f.code, f.severity) for f in found], [("NO_POSTS_DAY", "critical")])
        self.assertIn("2026-10-23", found[0].message)
        self.assertIn("2026-10-24", found[0].message)


class UnpublishedTest(unittest.TestCase):
    def test_first_unpublished_run_warns_and_quotes_the_reason(self):
        history = [entry("posted", 0, hour=1),
                   entry("generated_unpublished", 0, reasons=["[SECRETS] 게시 시크릿 미등록: blog_id"])]
        findings = health.evaluate(AUTO, history, NOW)
        unpub = [f for f in findings if f.code == "UNPUBLISHED"]
        self.assertEqual(len(unpub), 1)
        self.assertEqual(unpub[0].severity, "warning")
        self.assertIn("게시 시크릿 미등록: blog_id", unpub[0].message)

    def test_later_success_clears_it(self):
        history = [entry("generated_unpublished", 1), entry("posted", 0)]
        self.assertNotIn("UNPUBLISHED", codes(health.evaluate(AUTO, history, NOW)))

    def test_reason_text_is_folded_to_one_line_and_capped(self):
        long_reason = "줄1\n줄2 " + "가" * 500
        history = [entry("posted", 0, hour=1), entry("generated_unpublished", 0, reasons=[long_reason])]
        message = [f for f in health.evaluate(AUTO, history, NOW) if f.code == "UNPUBLISHED"][0].message
        self.assertNotIn("\n", message)
        self.assertLess(len(message), 400)

    def test_not_flagged_in_draft_mode(self):
        history = [entry("generated_unpublished", 0)]
        self.assertEqual(health.evaluate({**AUTO, "mode": "draft"}, history, NOW), [])


class DateOnlyEntryTest(unittest.TestCase):
    def test_date_only_entries_do_not_hide_staleness_when_a_commit_time_is_known(self):
        """Chance 이력은 날짜만 있어 '그날 23:59'로 가정했다. 글 커밋 시각이 있으면 그 가정을 쓰지 않는다."""
        blog = {**CHANCE, "health": {"max_gap_hours": 36, "max_failure_streak": 3}}
        legacy = {"date": "2026-10-24", "topic": "t"}  # 가정하면 어제 23:59 KST = 12시간 전
        old_commit = NOW - timedelta(hours=100)
        found = codes(health.evaluate(blog, [legacy], NOW, last_content_commit=old_commit))
        self.assertIn("STALE", found)
        self.assertNotIn("STALE", codes(health.evaluate(blog, [legacy], NOW)))  # 커밋 정보가 없으면 예전 가정

    def test_entry_time_option(self):
        item = {"date": "2026-10-24"}
        self.assertIsNone(health.entry_time(item, end_of_day=False))
        self.assertEqual(health.entry_time(item).astimezone(KST).hour, 23)
        self.assertEqual(health.entry_day(item), date(2026, 10, 24))


class EntryDayTest(unittest.TestCase):
    """이력 항목이 어느 날에 속하는가. pipeline/run.py 는 date 를 KST 달력 날짜로 적고(일일 상한도 date 로 센다)
    generated_at 에 같은 순간의 KST 시각을 적는다. 둘이 어긋나면 date 가 이긴다(상한을 센 기준이 date 이므로).
    entry_time(순간)은 반대로 generated_at 이 먼저다."""

    def test_date_wins_over_generated_at_when_they_disagree(self):
        item = {"date": "2026-10-24", "generated_at": "2026-10-25T01:00:00+09:00"}
        self.assertEqual(health.entry_day(item), date(2026, 10, 24))
        self.assertEqual(health.entry_time(item), datetime(2026, 10, 25, 1, 0, tzinfo=KST))   # 시각은 generated_at

    def test_generated_at_is_used_in_kst_when_date_is_missing_or_unreadable(self):
        utc_evening = "2026-10-24T15:30:00Z"                      # UTC 로는 10-24, KST 로는 10-25 00:30
        self.assertEqual(health.entry_day({"generated_at": utc_evening}), date(2026, 10, 25))
        self.assertEqual(health.entry_day({"date": "어제", "generated_at": utc_evening}), date(2026, 10, 25))
        self.assertEqual(health.entry_day({"date": "", "generated_at": "2026-10-24T08:00:00+09:00"}),
                         date(2026, 10, 24))

    def test_nothing_usable_gives_none(self):
        self.assertIsNone(health.entry_day({"topic": "x"}))
        self.assertIsNone(health.entry_day({"date": "garbage", "generated_at": "also garbage"}))

    def test_the_day_a_post_is_booked_on_follows_the_date_field(self):
        """date 가 어제이고 generated_at 이 그제 밤이면, 그 글은 어제 글이다 → 어제는 '글이 있는 날'(date 가 이긴다)."""
        booked_yesterday = {"status": "posted", "date": "2026-10-24", "generated_at": "2026-10-23T23:30:00+09:00"}
        history = [entry("posted", 5), booked_yesterday]
        self.assertEqual(health.evaluate(AUTO, history, NOW), [])
        self.assertEqual(health.post_days_from_history([booked_yesterday]), {date(2026, 10, 24)})


def run(conclusion, hours_ago):
    created = (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"conclusion": conclusion, "created_at": created}


def run_at(created, conclusion="success"):
    return {"conclusion": conclusion, "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ")}


class PagesDeployTest(unittest.TestCase):
    POST_DAYS = {date(2026, 10, 25), date(2026, 10, 24)}

    def evaluate(self, pages_runs, commit_hours_ago=5, blog=CHANCE):
        return health.evaluate(blog, [], NOW, last_content_commit=NOW - timedelta(hours=commit_hours_ago),
                               post_days=self.POST_DAYS, pages_runs=pages_runs)

    def test_success_after_the_commit_is_healthy(self):
        self.assertEqual(self.evaluate([run("success", 4.9)]), [])

    def test_no_deploy_after_the_commit_is_critical(self):
        findings = self.evaluate([run("success", 30)])
        self.assertEqual(codes(findings), ["PAGES_NOT_DEPLOYED"])
        self.assertEqual(findings[0].severity, "critical")

    def test_recent_commit_gets_a_grace_period(self):
        self.assertEqual(self.evaluate([], commit_hours_ago=0.2), [])

    def test_latest_failure_is_a_warning(self):
        findings = self.evaluate([run("failure", 4.8), run("success", 30)])
        self.assertIn("PAGES_FAILED", codes(findings))
        self.assertEqual([f for f in findings if f.code == "PAGES_FAILED"][0].severity, "warning")

    def test_cancelled_runs_are_ignored(self):
        self.assertEqual(self.evaluate([run("cancelled", 4.8), run("success", 4.7)]), [])

    def test_clock_skew_between_runner_and_github_is_not_a_missing_deploy(self):
        """글 커밋 시각은 러너 시계, Pages 실행 생성 시각은 GitHub 서버 시계다. 정상 배포는 커밋 2~3초 뒤에 시작하지만
        시계가 어긋나면 '배포가 커밋보다 먼저'로 보여 PAGES_NOT_DEPLOYED(심각)를 오판했다(F-11)."""
        committed = NOW - timedelta(hours=5)
        for seconds_before in (2, 3, 60, 119):
            with self.subTest(seconds_before=seconds_before):
                self.assertEqual(self.evaluate([run_at(committed - timedelta(seconds=seconds_before))]), [])

    def test_a_deploy_started_well_before_the_commit_is_not_that_commits_deploy(self):
        committed = NOW - timedelta(hours=5)
        for seconds_before in (121, 300, 3600):
            with self.subTest(seconds_before=seconds_before):
                findings = self.evaluate([run_at(committed - timedelta(seconds=seconds_before))])
                self.assertEqual([(f.code, f.severity) for f in findings], [("PAGES_NOT_DEPLOYED", "critical")])

    def test_a_deploy_just_after_the_commit_is_healthy(self):
        committed = NOW - timedelta(hours=5)
        self.assertEqual(self.evaluate([run_at(committed + timedelta(seconds=3))]), [])
        self.assertEqual(health.PAGES_CLOCK_SKEW_SECONDS, 120)

    def test_a_failed_run_inside_the_skew_window_does_not_count_as_a_deploy(self):
        committed = NOW - timedelta(hours=5)
        findings = self.evaluate([run_at(committed + timedelta(seconds=3), "failure")])
        self.assertEqual(sorted(f.code for f in findings), ["PAGES_FAILED", "PAGES_NOT_DEPLOYED"])

    def test_a_success_run_without_a_readable_created_at_counts_as_deployed(self):
        """응답 형식 문제로 created_at 이 없거나 읽을 수 없는 성공 실행은 '지금'으로 본다 — 정상 배포를 미배포(심각)로
        오판하지 않는다(오탐 쪽을 줄이는 의도). created_at 이 읽히고 커밋보다 한참 전이면 미배포다."""
        for bad in ({"conclusion": "success"}, {"conclusion": "success", "created_at": None},
                    {"conclusion": "success", "created_at": ""}, {"conclusion": "success", "created_at": "어제쯤"}):
            with self.subTest(run=bad):
                self.assertEqual(self.evaluate([bad]), [])
        self.assertEqual(codes(self.evaluate([run("success", 30)])), ["PAGES_NOT_DEPLOYED"])

    def test_not_checked_without_runs_data_or_for_other_platforms(self):
        self.assertEqual(health.evaluate(CHANCE, [], NOW, last_content_commit=NOW - timedelta(hours=5),
                                         post_days=self.POST_DAYS, pages_runs=None), [])
        self.assertEqual(self.evaluate([run("failure", 1)], blog=AUTO), [])


if __name__ == "__main__":
    unittest.main()
