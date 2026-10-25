"""워치독 알림 보강 테스트: 담당자·@멘션, 본문 갱신, 재알림, 새 심각 건에만 빨강, 정지 중 침묵, 글 추가 커밋만 새 글로 세기.

배경(Task 4 진단): 워치독은 문제를 잡았지만 담당자 없는 이슈 한 건뿐이었고 감시 실행은 항상 초록이라
운영자에게 닿지 않았다(이슈 #9·#10, 마지막 글 뒤 약 52시간).
"""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from pipeline.health import Finding

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402

NOW = datetime(2026, 10, 25, 3, 0, tzinfo=timezone.utc)
OWNER = "shine88pc"
CRIT = Finding("chance", "STALE", "critical", "마지막 활동 이후 65시간 경과")
WARN = Finding("blogger_macat", "UNPUBLISHED", "warning", "초안만 남겼습니다")


class FakeClient:
    def __init__(self):
        self.created, self.comments, self.closed, self.updated, self.assignees = [], [], [], [], []

    def create_issue(self, title, body, assignees=None):
        self.created.append((title, body))
        self.assignees.append(assignees)

    def comment(self, number, body):
        self.comments.append((number, body))

    def close(self, number):
        self.closed.append(number)

    def update_body(self, number, body):
        self.updated.append((number, body))


def sync(findings, issues, client=None, **kwargs):
    client = client or FakeClient()
    kwargs.setdefault("owner", OWNER)
    kwargs.setdefault("now", NOW)
    result = watchdog.sync_issues(findings, issues, client, out=lambda s: None, **kwargs)
    return client, result


def open_issue(finding, number=5, notified_hours_ago=1.0, body=None):
    """열려 있는 이슈(본문 표식으로 마지막 알림 시각을 기록)."""
    stamp = (NOW - timedelta(hours=notified_hours_ago)).isoformat(timespec="seconds")
    return {"title": finding.title, "number": number,
            "body": body if body is not None else watchdog.issue_body(finding, OWNER, stamp),
            "created_at": (NOW - timedelta(days=3)).isoformat()}


class CreateTest(unittest.TestCase):
    def test_new_issue_is_assigned_mentions_the_owner_and_records_the_time(self):
        client, (created, closed, renotified, new_critical) = sync([CRIT], [])
        self.assertEqual(created, [CRIT.title])
        title, body = client.created[0]
        self.assertEqual(client.assignees[0], [OWNER])
        self.assertIn(f"@{OWNER}", body)
        self.assertIn("watchdog:notified=2026-10-25T03:00:00+00:00", body)
        self.assertEqual(new_critical, [CRIT.title])

    def test_warning_issue_is_created_but_is_not_a_new_critical(self):
        client, (created, _, _, new_critical) = sync([WARN], [])
        self.assertEqual(created, [WARN.title])
        self.assertEqual(new_critical, [])

    def test_without_an_owner_nothing_is_assigned(self):
        client, _ = sync([CRIT], [], owner=None)
        self.assertIsNone(client.assignees[0])
        self.assertNotIn("@", client.created[0][1])

    def test_body_explains_pause_covers_both_engines(self):
        body = watchdog.issue_body(CRIT, OWNER)
        self.assertIn("Chance·Blogger 모두", body)
        self.assertIn("PIPELINE_PAUSE=true", body)

    def test_new_issues_per_run_are_capped_and_deferred(self):
        findings = [Finding(f"b{i}", "STALE", "critical", "x") for i in range(8)]
        buf = io.StringIO()
        client = FakeClient()
        with redirect_stdout(buf):
            result = watchdog.sync_issues(findings, [], client, owner=OWNER, now=NOW, max_new=3, out=print)
        self.assertEqual(len(result[0]), 3)
        self.assertIn("::warning::새 이슈가 한 번에 너무 많아", buf.getvalue())

    def test_default_cap_is_five_new_issues_per_run(self):
        """상한 기본값이 바뀌면(예: 500) 한 번에 이슈가 쏟아진다. 호출자가 max_new 를 주지 않아도 5건에서 멈춘다."""
        self.assertEqual(watchdog.MAX_NEW_ISSUES_PER_RUN, 5)
        findings = [Finding(f"b{i}", "STALE", "critical", "x") for i in range(8)]
        client, (created, _, _, new_critical) = sync(findings, [])
        self.assertEqual(len(created), 5)
        self.assertEqual(len(client.created), 5)
        self.assertEqual(len(new_critical), 5)

    def test_dry_run_calls_nothing_but_still_reports(self):
        client, (created, closed, renotified, new_critical) = sync(
            [CRIT], [open_issue(WARN, number=9)], dry=True)
        self.assertEqual(created, [CRIT.title])
        self.assertEqual(closed, [WARN.title])
        self.assertEqual((client.created, client.closed, client.comments, client.updated), ([], [], [], []))


class ExistingIssueTest(unittest.TestCase):
    def test_unchanged_open_issue_is_left_alone(self):
        issue = open_issue(CRIT, notified_hours_ago=2)
        client, (created, closed, renotified, _) = sync([CRIT], [issue])
        self.assertEqual((created, closed, renotified), ([], [], []))
        self.assertEqual((client.created, client.comments, client.updated), ([], [], []))

    def test_changed_message_updates_the_body_without_a_new_comment(self):
        issue = open_issue(CRIT, notified_hours_ago=2)
        newer = Finding("chance", "STALE", "critical", "마지막 활동 이후 70시간 경과")
        client, (_, _, renotified, _) = sync([newer], [issue])
        self.assertEqual(renotified, [])
        self.assertEqual([n for n, _ in client.updated], [5])
        self.assertIn("70시간", client.updated[0][1])
        self.assertEqual(client.comments, [])

    def test_unresolved_critical_issue_is_renotified_after_two_days(self):
        issue = open_issue(CRIT, notified_hours_ago=49)
        client, (_, _, renotified, new_critical) = sync([CRIT], [issue])
        self.assertEqual(renotified, [CRIT.title])
        self.assertEqual(new_critical, [])                     # 이미 열린 건은 새 심각 건이 아니다(실행은 초록)
        number, comment = client.comments[0]
        self.assertEqual(number, 5)
        self.assertIn(f"@{OWNER}", comment)
        self.assertIn("아직 해결되지 않았습니다", comment)
        self.assertIn("watchdog:notified=2026-10-25T03:00:00+00:00", client.updated[0][1])  # 표식도 갱신

    def test_not_renotified_before_two_days(self):
        client, (_, _, renotified, _) = sync([CRIT], [open_issue(CRIT, notified_hours_ago=47)])
        self.assertEqual((renotified, client.comments), ([], []))

    def test_warning_issues_are_never_renotified(self):
        client, (_, _, renotified, _) = sync([WARN], [open_issue(WARN, notified_hours_ago=200)])
        self.assertEqual((renotified, client.comments), ([], []))

    def test_issue_without_marker_falls_back_to_creation_time(self):
        issue = open_issue(CRIT, body="옛 형식 본문(표식 없음)")  # created_at 은 3일 전
        client, (_, _, renotified, _) = sync([CRIT], [issue])
        self.assertEqual(renotified, [CRIT.title])

    def test_resolved_issue_is_closed_with_a_comment_and_other_issues_are_untouched(self):
        issues = [open_issue(WARN, number=6), {"title": "사람이 연 일반 이슈", "number": 7, "body": ""}]
        client, (created, closed, _, _) = sync([], issues)
        self.assertEqual(closed, [WARN.title])
        self.assertEqual(client.closed, [6])
        self.assertEqual([n for n, _ in client.comments], [6])

    def test_dry_run_never_patches_or_comments_on_an_open_issue_but_still_reports(self):
        newer = Finding("chance", "STALE", "critical", "마지막 활동 이후 70시간 경과")   # 본문이 바뀐다
        client, (_, _, renotified, _) = sync([newer], [open_issue(CRIT, notified_hours_ago=49)], dry=True)
        self.assertEqual(renotified, [CRIT.title])                      # 계획(재알림)은 보고한다
        self.assertEqual((client.updated, client.comments, client.created, client.closed), ([], [], [], []))
        client, _ = sync([newer], [open_issue(CRIT, notified_hours_ago=2)], dry=True)   # 본문만 바뀐 경우
        self.assertEqual(client.updated, [])
        client, _ = sync([newer], [open_issue(CRIT, notified_hours_ago=2)])             # 대조군: 드라이런이 아니면 PATCH
        self.assertEqual(len(client.updated), 1)


class NotifiedAtTest(unittest.TestCase):
    """_notified_at: 표식 → 이슈를 연 시각 → None. 읽을 수 없는 값은 건너뛴다."""

    def at(self, body=None, created_at=None):
        issue = {"title": "t", "number": 1}
        if body is not None:
            issue["body"] = body
        if created_at is not None:
            issue["created_at"] = created_at
        return watchdog._notified_at(issue)

    def test_marker_wins_over_created_at(self):
        got = self.at("<!-- watchdog:notified=2026-10-24T03:00:00+00:00 -->", "2026-10-20T00:00:00Z")
        self.assertEqual(got, datetime(2026, 10, 24, 3, 0, tzinfo=timezone.utc))

    def test_falls_back_to_created_at_with_a_z_suffix(self):
        self.assertEqual(self.at("옛 형식 본문", "2026-10-20T00:00:00Z"), datetime(2026, 10, 20, tzinfo=timezone.utc))

    def test_unreadable_marker_falls_back_to_created_at(self):
        self.assertEqual(self.at("<!-- watchdog:notified=어제쯤 -->", "2026-10-20T00:00:00Z"),
                         datetime(2026, 10, 20, tzinfo=timezone.utc))

    def test_a_naive_marker_time_is_taken_as_utc(self):
        self.assertEqual(self.at("<!-- watchdog:notified=2026-10-24T03:00:00 -->"),
                         datetime(2026, 10, 24, 3, 0, tzinfo=timezone.utc))

    def test_nothing_readable_gives_none(self):
        self.assertIsNone(self.at("옛 형식 본문"))
        self.assertIsNone(self.at(None, "아무 때나"))
        self.assertIsNone(self.at())

    def test_issue_with_neither_marker_nor_created_at_is_not_renotified_and_does_not_crash(self):
        """알림 시각을 알 수 없으면 재알림하지 않는다(48시간을 셀 기준이 없다). 예외로 실행이 죽어서도 안 된다."""
        issue = {"title": CRIT.title, "number": 5, "body": "옛 형식 본문(표식 없음)"}          # created_at 도 없다
        client, (created, closed, renotified, new_critical) = sync([CRIT], [issue])
        self.assertEqual((created, closed, renotified, new_critical), ([], [], [], []))
        self.assertEqual(client.comments, [])
        client, (_, _, renotified, _) = sync([CRIT], [{**issue, "created_at": None}])
        self.assertEqual((renotified, client.comments), ([], []))

class CommitTimesTest(unittest.TestCase):
    def git(self, root, *args, date=None):
        env = dict(os.environ)
        if date:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
                        *args], cwd=root, check=True, capture_output=True, env=env)

    def make_repo(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.git(root, "init", "-q")
        (root / "_posts").mkdir()
        recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        later = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        (root / "_posts" / "a.md").write_text("one", encoding="utf-8")
        self.git(root, "add", "-A")
        self.git(root, "commit", "-q", "-m", "add post", date=recent)
        (root / "_posts" / "a.md").write_text("one edited (image fix)", encoding="utf-8")
        self.git(root, "add", "-A")
        self.git(root, "commit", "-q", "-m", "fix image", date=later)
        return root

    def test_added_only_ignores_edits_of_existing_posts(self):
        root = self.make_repo()
        every = watchdog.commit_times(root, "_posts")
        added = watchdog.commit_times(root, "_posts", added_only=True)
        self.assertEqual(len(every), 2)
        self.assertEqual(len(added), 1)
        self.assertGreater(every[0], added[0])  # 최신 커밋은 이미지 교체, 새 글 커밋은 더 오래됨

    def test_last_commit_time_added_only(self):
        root = self.make_repo()
        self.assertEqual(watchdog.last_commit_time(root, "_posts", added_only=True),
                         watchdog.commit_times(root, "_posts", added_only=True)[0])
        self.assertGreater(watchdog.last_commit_time(root, "_posts"),
                           watchdog.last_commit_time(root, "_posts", added_only=True))

    def test_not_a_git_repo_gives_an_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(watchdog.commit_times(tmp, "_posts"), [])
            self.assertIsNone(watchdog.last_commit_time(tmp, "_posts"))


class CollectTest(unittest.TestCase):
    def test_jekyll_blog_counts_only_added_commits_as_new_posts(self):
        reg = {"blogs": [{"key": "chance", "name": "C", "platform": "jekyll-git", "mode": "auto",
                          "workflow": ".github/workflows/chanceblog.yml",
                          "state": {"history": "history.json", "content_dir": "_posts"},
                          "health": {"max_gap_hours": 36, "max_failure_streak": 3}}],
               "defaults": {}}
        added = [NOW - timedelta(hours=14), NOW - timedelta(days=2, hours=6)]
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(watchdog, "enabled_blogs", return_value=reg["blogs"]), \
                mock.patch.object(watchdog, "commit_times", return_value=added) as ct:
            (Path(tmp) / "history.json").write_text("[]", encoding="utf-8")
            findings, stats = watchdog.collect(reg, tmp, NOW, client=None)
        ct.assert_called_with(tmp, "_posts", added_only=True)
        self.assertEqual(findings, [])
        self.assertEqual(stats[0]["posts_7d"], 2)
        self.assertEqual(stats[0]["last_post"], added[0])

    def test_pages_runs_lookup_failure_only_skips_the_deploy_check(self):
        class BrokenClient:
            def workflow_runs(self, name):
                raise OSError("network down")
        reg = {"blogs": [{"key": "chance", "platform": "jekyll-git", "mode": "auto",
                          "workflow": ".github/workflows/chanceblog.yml",
                          "state": {"history": "history.json", "content_dir": "_posts"},
                          "health": {"max_gap_hours": 36, "max_failure_streak": 3}}]}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(watchdog, "enabled_blogs", return_value=reg["blogs"]), \
                mock.patch.object(watchdog, "commit_times", return_value=[NOW - timedelta(hours=2)]):
            (Path(tmp) / "history.json").write_text("[]", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                findings, _ = watchdog.collect(reg, tmp, NOW, client=BrokenClient())
        self.assertIn("조회 실패", buf.getvalue())
        self.assertNotIn("PAGES_NOT_DEPLOYED", [f.code for f in findings])


class SummaryTest(unittest.TestCase):
    def test_summary_lists_findings_and_blog_status_without_secrets(self):
        stats = [{"key": "chance", "mode": "auto", "last_post": NOW - timedelta(hours=14), "posts_7d": 3,
                  "codes": []},
                 {"key": "blogger_macat", "mode": "auto", "last_post": None, "posts_7d": 0, "codes": ["UNPUBLISHED"]}]
        text = watchdog.render_summary(stats, [WARN], ["[Watchdog] x: NEW"], ["[Watchdog] y: OLD"], [],
                                       [{"number": 10, "title": WARN.title}])
        self.assertIn("UNPUBLISHED", text)
        self.assertIn("| chance | auto | 2026-10-24 22:00 | 3 | 정상 |", text)
        self.assertIn("없음", text)
        self.assertIn("이슈 생성: [Watchdog] x: NEW", text)
        self.assertIn("#10", text)

    def test_all_clear_summary(self):
        text = watchdog.render_summary([], [], [], [], [])
        self.assertIn("이상 없음", text)


class MainPolicyTest(unittest.TestCase):
    """main(): 정지 중 침묵, 새 심각 건에만 빨강, 지속 중인 건은 초록."""

    def run_main(self, findings, open_issues=(), env=None):
        client = FakeClient()
        client.list_open_issues = lambda: list(open_issues)
        base = {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": f"{OWNER}/chanceblog", "GITHUB_REPOSITORY_OWNER": OWNER}
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            full = {**base, "GITHUB_STEP_SUMMARY": str(summary), **(env or {})}
            with mock.patch.dict(os.environ, full, clear=False), \
                    mock.patch.object(watchdog, "load_registry", return_value={"blogs": []}), \
                    mock.patch.object(watchdog, "validate_registry", return_value=[]), \
                    mock.patch.object(watchdog, "collect", return_value=(findings, [])), \
                    mock.patch.object(watchdog, "GitHubClient", return_value=client):
                os.environ.pop("PIPELINE_PAUSE", None) if not (env and "PIPELINE_PAUSE" in env) else None
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = watchdog.main()
            text = summary.read_text(encoding="utf-8") if summary.exists() else ""
        return code, buf.getvalue(), client, text

    def test_new_critical_finding_fails_the_run(self):
        code, out, client, summary = self.run_main([CRIT])
        self.assertEqual(code, 1)
        self.assertIn("::error::새로 생긴 심각 건", out)
        self.assertEqual(len(client.created), 1)
        self.assertIn("워치독 점검 결과", summary)

    def test_ongoing_critical_issue_keeps_the_run_green(self):
        code, out, client, _ = self.run_main([CRIT], open_issues=[open_issue(CRIT, notified_hours_ago=2)])
        self.assertEqual(code, 0)
        self.assertEqual(client.created, [])

    def test_new_warning_keeps_the_run_green_with_an_annotation(self):
        code, out, client, _ = self.run_main([WARN])
        self.assertEqual(code, 0)
        self.assertIn("::warning::[Watchdog] blogger_macat: UNPUBLISHED", out)
        self.assertEqual(len(client.created), 1)

    def test_pause_creates_nothing_and_says_so(self):
        code, out, client, summary = self.run_main([CRIT], env={"PIPELINE_PAUSE": "true"})
        self.assertEqual(code, 0)
        self.assertIn("[일시정지]", out)
        self.assertEqual(client.created, [])
        self.assertIn("일시정지", summary)

    def test_all_clear_is_green_and_closes_nothing_extra(self):
        code, out, client, _ = self.run_main([])
        self.assertEqual(code, 0)
        self.assertIn("이상 없음", out)

    def test_without_token_it_is_a_dry_run(self):
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "", "GITHUB_REPOSITORY": ""}), \
                mock.patch.object(watchdog, "load_registry", return_value={"blogs": []}), \
                mock.patch.object(watchdog, "validate_registry", return_value=[]), \
                mock.patch.object(watchdog, "collect", return_value=([CRIT], [])):
            os.environ.pop("PIPELINE_PAUSE", None)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = watchdog.main()
        self.assertEqual(code, 0)
        self.assertIn("dry-run", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
