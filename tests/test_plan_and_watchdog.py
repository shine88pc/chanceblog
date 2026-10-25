import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from unittest import mock

import _bootstrap  # noqa: F401
from pipeline import plan, registry
from pipeline.health import Finding

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402


def registry_all_auto():
    """실제 레지스트리의 모든 블로그를 켜 둔 사본. 운영 중 일시 정지(mode off)와 무관하게 로직을 시험한다."""
    reg = registry.load_registry()
    for blog in reg["blogs"]:
        blog["mode"] = "auto"
    return reg


class PlanTest(unittest.TestCase):
    def test_matrix_for_blogger(self):
        matrix = plan.build_matrix(registry_all_auto(), "blogger")
        self.assertEqual(len(matrix["include"]), 1)
        item = matrix["include"][0]
        self.assertEqual(item["key"], "blogger_macat")
        self.assertEqual(item["secret_refresh_token"], "BLOGGER_REFRESH_TOKEN")
        self.assertEqual(item["history"], "blogger_history.json")
        self.assertNotIn("value", json.dumps(item))  # 이름만 있고 값은 없다

    def test_only_filters_to_one_blog(self):
        reg = registry_all_auto()
        self.assertEqual([i["key"] for i in plan.build_matrix(reg, "blogger", only="blogger_macat")["include"]],
                         ["blogger_macat"])
        self.assertEqual(plan.build_matrix(reg, "blogger", only="nope")["include"], [])

    def test_matrix_excludes_off_and_filters_platform(self):
        reg = registry_all_auto()
        self.assertEqual([i["key"] for i in plan.build_matrix(reg)["include"]], ["chance", "blogger_macat"])
        reg["blogs"][1]["mode"] = "off"
        self.assertEqual(plan.build_matrix(reg, "blogger")["include"], [])

    def test_cli_outputs_compact_json_and_count(self):
        with mock.patch.object(plan, "load_registry", return_value=registry_all_auto()):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(plan.main(["--platform", "blogger"]), 0)
            self.assertEqual(json.loads(buf.getvalue())["include"][0]["key"], "blogger_macat")
            self.assertNotIn("\n", buf.getvalue().strip())
            buf = io.StringIO()
            with redirect_stdout(buf):
                plan.main(["--platform", "blogger", "--count"])
            self.assertEqual(buf.getvalue().strip(), "1")

    def test_unknown_only_key_is_an_error_not_an_empty_matrix(self):
        """오타로 대상이 0개가 되어 generate 잡이 조용히 건너뛰어지던 문제(E8)."""
        with mock.patch.object(plan, "load_registry", return_value=registry_all_auto()):
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = plan.main(["--platform", "blogger", "--only", "blogger_macta"])
        self.assertEqual(code, 1)
        self.assertIn("blogger_macta", err.getvalue())
        self.assertIn("blogger_macat", err.getvalue())   # 유효한 key 안내
        self.assertIn("chance", err.getvalue())

    def test_paused_blog_is_zero_targets_without_error(self):
        """mode=off 로 정지한 블로그는 오류가 아니라 대상 0개다(워크플로가 notice 를 남긴다)."""
        reg = registry_all_auto()
        reg["blogs"][1]["mode"] = "off"
        with mock.patch.object(plan, "load_registry", return_value=reg):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(plan.main(["--platform", "blogger", "--count"]), 0)
            self.assertEqual(buf.getvalue().strip(), "0")
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(plan.main(["--platform", "blogger", "--only", "blogger_macat", "--count"]), 0)
            self.assertEqual(buf.getvalue().strip(), "0")


class FakeClient:
    def __init__(self):
        self.created, self.comments, self.closed = [], [], []

    def create_issue(self, title, body):
        self.created.append((title, body))

    def comment(self, number, body):
        self.comments.append(number)

    def close(self, number):
        self.closed.append(number)


F1 = Finding("blogger_macat", "STALE", "critical", "멈춤")
F2 = Finding("chance", "FAIL_STREAK", "critical", "연속 실패")


class SyncIssuesTest(unittest.TestCase):
    def test_creates_missing_and_does_not_duplicate(self):
        client = FakeClient()
        created, closed = watchdog.sync_issues([F1, F2], [{"title": F1.title, "number": 5}], client, out=lambda s: None)
        self.assertEqual(created, [F2.title])
        self.assertEqual(closed, [])
        self.assertEqual([t for t, _ in client.created], [F2.title])
        self.assertIn("HANDLER.md", client.created[0][1])

    def test_closes_resolved_watchdog_issues_only(self):
        client = FakeClient()
        issues = [{"title": F1.title, "number": 5}, {"title": "[Watchdog] x: GONE", "number": 6},
                  {"title": "사람이 연 일반 이슈", "number": 7}]
        created, closed = watchdog.sync_issues([F1], issues, client, out=lambda s: None)
        self.assertEqual(closed, ["[Watchdog] x: GONE"])
        self.assertEqual(client.closed, [6])
        self.assertEqual(client.comments, [6])

    def test_dry_run_calls_nothing(self):
        client = FakeClient()
        created, closed = watchdog.sync_issues([F1], [{"title": "[Watchdog] x: GONE", "number": 6}], client,
                                               dry=True, out=lambda s: None)
        self.assertEqual((created, closed), ([F1.title], ["[Watchdog] x: GONE"]))
        self.assertEqual((client.created, client.closed, client.comments), ([], [], []))


class CollectFindingsTest(unittest.TestCase):
    def test_corrupt_history_is_reported(self):
        reg = registry.load_registry()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "history.json").write_text("{broken", encoding="utf-8")
            findings = watchdog.collect_findings(reg, tmp, datetime(2026, 10, 22, tzinfo=timezone.utc))
        self.assertIn(("chance", "STATE_CORRUPT"), [(f.blog, f.code) for f in findings])

    def test_empty_repo_reports_no_activity(self):
        reg = registry_all_auto()
        with tempfile.TemporaryDirectory() as tmp:
            findings = watchdog.collect_findings(reg, tmp, datetime(2026, 10, 22, tzinfo=timezone.utc))
        self.assertEqual(sorted((f.blog, f.code) for f in findings),
                         [("blogger_macat", "NO_ACTIVITY"), ("chance", "NO_ACTIVITY")])


if __name__ == "__main__":
    unittest.main()
