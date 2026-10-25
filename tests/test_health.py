import unittest
from datetime import datetime, timedelta, timezone

import _bootstrap  # noqa: F401
from pipeline import health

NOW = datetime(2026, 10, 22, 0, 0, tzinfo=timezone.utc)
BLOG = {"key": "b", "platform": "blogger", "mode": "auto",
        "health": {"max_gap_hours": 50, "max_failure_streak": 3, "max_unpublished_days": 3}}


def entry(status, hours_ago):
    when = (NOW - timedelta(hours=hours_ago)).isoformat()
    return {"status": status, "generated_at": when}


def codes(findings):
    return sorted(f.code for f in findings)


class EvaluateTest(unittest.TestCase):
    def test_healthy(self):
        self.assertEqual(health.evaluate(BLOG, [entry("posted", 5)], NOW), [])

    def test_stale(self):
        findings = health.evaluate(BLOG, [entry("posted", 80)], NOW)
        self.assertEqual(codes(findings), ["STALE"])
        self.assertEqual(findings[0].severity, "critical")
        self.assertEqual(findings[0].title, "[Watchdog] b: STALE")

    def test_no_activity(self):
        self.assertEqual(codes(health.evaluate(BLOG, [], NOW)), ["NO_ACTIVITY"])

    def test_recent_commit_rescues_staleness(self):
        findings = health.evaluate(BLOG, [entry("posted", 80)], NOW, last_content_commit=NOW - timedelta(hours=3))
        self.assertNotIn("STALE", codes(findings))  # 하루 단위 NO_POSTS_DAY 는 test_health_daily.py 에서 따로 본다

    def test_failure_streak(self):
        history = [entry("posted", 70), entry("publish_failed", 48), entry("llm_failed", 24), entry("publish_failed", 1)]
        self.assertIn("FAIL_STREAK", codes(health.evaluate(BLOG, history, NOW)))

    def test_failure_streak_needs_consecutive(self):
        history = [entry("publish_failed", 48), entry("posted", 24), entry("publish_failed", 1)]
        self.assertNotIn("FAIL_STREAK", codes(health.evaluate(BLOG, history, NOW)))

    def test_reject_streak(self):
        history = [entry("rejected", h) for h in (40, 30, 20, 10, 1)]
        self.assertIn("REJECT_STREAK", codes(health.evaluate(BLOG, history, NOW)))

    def test_unpublished_streak_hints_missing_secrets(self):
        history = [entry("generated_unpublished", h) for h in (48, 24, 1)]
        self.assertEqual(codes(health.evaluate(BLOG, history, NOW)), ["UNPUBLISHED"])

    def test_unpublished_is_not_flagged_in_draft_mode(self):
        draft_blog = {**BLOG, "mode": "draft"}
        history = [entry("generated_unpublished", h) for h in (48, 24, 1)]
        self.assertEqual(health.evaluate(draft_blog, history, NOW), [])

    def test_run_failure_streak_ignores_cancelled(self):
        runs = [{"conclusion": "failure"}, {"conclusion": "cancelled"}, {"conclusion": "failure"}, {"conclusion": "failure"}]
        self.assertIn("RUN_FAIL_STREAK", codes(health.evaluate(BLOG, [entry("posted", 1)], NOW, recent_runs=runs)))

    def test_one_success_breaks_run_streak(self):
        runs = [{"conclusion": "failure"}, {"conclusion": "success"}, {"conclusion": "failure"}]
        self.assertNotIn("RUN_FAIL_STREAK", codes(health.evaluate(BLOG, [entry("posted", 1)], NOW, recent_runs=runs)))

    def test_legacy_entries_without_status_use_date(self):
        legacy = {"date": "2026-10-21", "topic": "x"}  # status 없음 = 정상으로 취급, 시각은 그 날 KST 끝
        self.assertEqual(health.evaluate(BLOG, [legacy], NOW), [])
        old = {"date": "2026-10-10", "topic": "x"}
        self.assertEqual(codes(health.evaluate(BLOG, [old, "문자열 항목"], NOW)), ["STALE"])

    def test_mode_off_is_ignored(self):
        self.assertEqual(health.evaluate({**BLOG, "mode": "off"}, [], NOW), [])


if __name__ == "__main__":
    unittest.main()
