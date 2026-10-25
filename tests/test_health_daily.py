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

    def test_blogger_draft_uploaded_counts_as_a_real_post(self):
        self.assertEqual(health.evaluate(AUTO, [entry("draft_uploaded", 1)], NOW), [])

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

    def test_legacy_date_only_entries_count_as_posts_on_their_date(self):
        legacy = {"date": "2026-10-24", "topic": "상태 없는 옛 항목"}
        self.assertEqual(health.evaluate(CHANCE, [legacy], NOW), [])

    def test_a_blog_that_never_posted_is_left_to_no_activity(self):
        self.assertEqual(codes(health.evaluate(AUTO, [], NOW)), ["NO_ACTIVITY"])


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


def run(conclusion, hours_ago):
    created = (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"conclusion": conclusion, "created_at": created}


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

    def test_not_checked_without_runs_data_or_for_other_platforms(self):
        self.assertEqual(health.evaluate(CHANCE, [], NOW, last_content_commit=NOW - timedelta(hours=5),
                                         post_days=self.POST_DAYS, pages_runs=None), [])
        self.assertEqual(self.evaluate([run("failure", 1)], blog=AUTO), [])


if __name__ == "__main__":
    unittest.main()
