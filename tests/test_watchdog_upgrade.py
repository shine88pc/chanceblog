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
import urllib.error
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from pipeline.health import Finding
from watchdog_helpers import build_repo
from watchdog_helpers import FakeGitHub, canned_commit_times

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


class ClosingCommentTest(unittest.TestCase):
    """F-12: 해소 코멘트가 '조건이 해소되어'뿐이면 NO_POSTS_DAY 경고가 STALE 로 대체되어 닫힐 때 오해를 준다."""

    PHRASE = "조건이 해소되었거나 다른 알림(예: STALE)으로 대체되어 자동으로 닫습니다."

    def test_comment_says_resolved_or_replaced(self):
        client, _ = sync([], [open_issue(WARN, number=6)])
        self.assertEqual(client.comments, [(6, self.PHRASE)])

    def test_a_no_posts_warning_replaced_by_stale_is_closed_with_that_explanation(self):
        nopost = Finding("chance", "NO_POSTS_DAY", "warning", "어제 새 글이 0건입니다")
        stale = Finding("chance", "STALE", "critical", "마지막 활동 이후 65시간 경과")
        client, (created, closed, _, new_critical) = sync([stale], [open_issue(nopost, number=6)])
        self.assertEqual((created, closed, new_critical), ([stale.title], [nopost.title], [stale.title]))
        self.assertEqual(client.comments, [(6, self.PHRASE)])
        self.assertEqual(client.closed, [6])


class NewIssueOrderTest(unittest.TestCase):
    """F-13: 새 이슈가 상한을 넘으면 경고가 먼저 만들어져 심각 건이 다음 실행으로 밀리고, 그 실행이 초록이 된다."""

    def test_critical_is_created_first_even_when_listed_after_the_warnings(self):
        warnings = [Finding(f"w{i}", "UNPUBLISHED", "warning", "x") for i in range(5)]
        critical = Finding("chance", "STALE", "critical", "y")
        client, (created, _, _, new_critical) = sync(warnings + [critical], [])     # 기본 상한 5건
        self.assertEqual(len(created), 5)
        self.assertEqual(created[0], critical.title)
        self.assertEqual(new_critical, [critical.title])                         # 실행이 빨갛게 끝나는 근거

    def test_the_finding_that_gets_deferred_is_the_least_severe_one(self):
        findings = [Finding("w0", "UNPUBLISHED", "warning", "x"), Finding("w1", "UNPUBLISHED", "warning", "x"),
                    Finding("c0", "STALE", "critical", "y"), Finding("c1", "STALE", "critical", "y")]
        lines = []
        client = FakeClient()
        created, _, _, new_critical = watchdog.sync_issues(findings, [], client, owner=OWNER, now=NOW, max_new=3,
                                                           out=lines.append)
        self.assertEqual(created, [findings[2].title, findings[3].title, findings[0].title])   # 같은 등급 안에서는 원래 순서
        self.assertEqual(new_critical, [findings[2].title, findings[3].title])
        self.assertEqual([ln for ln in lines if ln.startswith("::warning::")],
                         [f"::warning::새 이슈가 한 번에 너무 많아 다음 실행으로 미룹니다: {findings[1].title}"])

    def test_existing_issues_are_still_updated_when_new_ones_are_deferred(self):
        newer = Finding("chance", "STALE", "critical", "마지막 활동 이후 70시간 경과")
        warnings = [Finding(f"w{i}", "UNPUBLISHED", "warning", "x") for i in range(3)]
        client, (created, _, _, _) = sync(warnings + [newer], [open_issue(CRIT, notified_hours_ago=2)], max_new=1)
        self.assertEqual(created, [warnings[0].title])
        self.assertEqual([n for n, _ in client.updated], [5])


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


class MarkerAndInertTextTest(unittest.TestCase):
    """F-6: 이력에서 인용한 사유 같은 자유 텍스트가 재알림 표식을 위조하거나 다른 사람을 멘션하지 못한다."""

    FORGED = "<!-- watchdog:notified=2099-01-01T00:00:00+00:00 -->"

    def test_marker_is_read_from_the_last_match_at_the_end_of_the_body(self):
        body = f"문제 설명 {self.FORGED} 이어지는 글\n\n<!-- watchdog:notified=2026-10-23T03:00:00+00:00 -->"
        got = watchdog._notified_at({"title": "t", "body": body, "created_at": "2026-10-20T00:00:00Z"})
        self.assertEqual(got, datetime(2026, 10, 23, 3, 0, tzinfo=timezone.utc))

    def test_a_forged_marker_in_the_quoted_reason_cannot_block_the_renotification(self):
        evil = Finding("chance", "STALE", "critical", f"사유 {self.FORGED} 끝")
        issue = open_issue(evil, notified_hours_ago=100)
        self.assertEqual(watchdog._notified_at(issue), NOW - timedelta(hours=100))
        client, (_, _, renotified, _) = sync([evil], [issue])
        self.assertEqual(renotified, [evil.title])

    def test_quoted_text_cannot_mention_other_people_or_open_an_html_comment(self):
        nasty = Finding("blogger_macat", "UNPUBLISHED", "warning", "사유: @octocat 님께 알림 <!-- 숨김 --> <script>")
        body = watchdog.issue_body(nasty, OWNER, "2026-10-25T03:00:00+00:00")
        self.assertNotIn("@octocat", body)
        self.assertIn("\N{FULLWIDTH COMMERCIAL AT}octocat", body)     # 읽을 수는 있게 전각 '＠'(U+FF20)로
        self.assertEqual(body.count("<"), 1)                 # 남은 '<' 는 우리가 붙인 표식 하나뿐
        self.assertEqual(body.count(f"@{OWNER}"), 1)         # 의도한 소유자 멘션은 그대로
        self.assertTrue(body.rstrip().endswith("-->"))

    def test_the_renotify_comment_defuses_the_quoted_text_too(self):
        nasty = Finding("chance", "STALE", "critical", "사유 @octocat <!-- x -->")
        client, _ = sync([nasty], [open_issue(nasty, notified_hours_ago=49)])
        comment = client.comments[0][1]
        self.assertNotIn("@octocat", comment)
        self.assertNotIn("<", comment)
        self.assertIn(f"@{OWNER}", comment)                  # 소유자 멘션은 유지

    def test_ordinary_messages_are_unchanged(self):
        self.assertIn("마지막 활동 이후 65시간 경과", watchdog.issue_body(CRIT, OWNER))


class BodyComparisonTest(unittest.TestCase):
    """F-7: 사람이 웹에서 고쳐 본문이 CRLF 로 저장돼도 내용이 같으면 매 실행 PATCH 하지 않는다."""

    def test_a_crlf_copy_of_the_same_body_is_not_patched_again(self):
        issue = open_issue(CRIT, notified_hours_ago=2)
        issue["body"] = issue["body"].replace("\n", "\r\n")
        client, _ = sync([CRIT], [issue])
        self.assertEqual(client.updated, [])

    def test_a_crlf_body_with_changed_content_is_still_patched_with_an_lf_body(self):
        issue = open_issue(CRIT, notified_hours_ago=2)
        issue["body"] = issue["body"].replace("\n", "\r\n")
        newer = Finding("chance", "STALE", "critical", "마지막 활동 이후 70시간 경과")
        client, _ = sync([newer], [issue])
        self.assertEqual([n for n, _ in client.updated], [5])
        self.assertNotIn("\r", client.updated[0][1])
        self.assertIn("70시간", client.updated[0][1])

    def test_trailing_whitespace_alone_does_not_trigger_a_patch(self):
        issue = open_issue(CRIT, notified_hours_ago=2)
        issue["body"] = issue["body"] + "\r\n\r\n"
        client, _ = sync([CRIT], [issue])
        self.assertEqual(client.updated, [])


class AssigneeRejectingClient(FakeClient):
    """담당자가 있는 이슈 생성을 거절하는 클라이언트(예: 저장소에서 지정할 수 없는 사용자 → HTTP 422)."""

    def __init__(self, code=422, always=False):
        super().__init__()
        self.code, self.always, self.attempts = code, always, []

    def create_issue(self, title, body, assignees=None):
        self.attempts.append((title, assignees))
        if assignees or self.always:
            raise urllib.error.HTTPError("https://api.github.com/repos/o/r/issues", self.code, "error", {},
                                         io.BytesIO(b"{}"))
        super().create_issue(title, body, assignees)


class AssigneeFallbackTest(unittest.TestCase):
    """F-9: 담당자 지정이 거부돼도 이슈는 만든다(담당자 없이, 경고와 함께). 그 밖의 오류는 그대로 올린다(실행이 빨갛게 된다)."""

    def run_sync(self, client, findings=(CRIT,), **kwargs):
        lines = []
        kwargs.setdefault("owner", OWNER)
        result = watchdog.sync_issues(list(findings), [], client, now=NOW, out=lines.append, **kwargs)
        return result, lines

    def test_a_rejected_assignee_retries_without_one_and_warns(self):
        client = AssigneeRejectingClient()
        (created, _, _, new_critical), lines = self.run_sync(client)
        self.assertEqual(created, [CRIT.title])
        self.assertEqual(new_critical, [CRIT.title])
        self.assertEqual(client.attempts, [(CRIT.title, [OWNER]), (CRIT.title, None)])
        self.assertEqual(client.assignees, [None])
        self.assertIn(f"@{OWNER}", client.created[0][1])             # 담당자는 못 붙여도 @멘션으로 알림은 간다
        self.assertEqual([ln for ln in lines if ln.startswith("::warning::")],
                         [f"::warning::담당자({OWNER}) 지정이 거부되어(HTTP 422) 담당자 없이 이슈를 만듭니다: {CRIT.title}"])

    def test_every_new_issue_gets_the_fallback_not_only_the_first(self):
        client = AssigneeRejectingClient()
        (created, _, _, _), _ = self.run_sync(client, findings=(CRIT, WARN))
        self.assertEqual(sorted(created), sorted([CRIT.title, WARN.title]))
        self.assertEqual(len(client.created), 2)

    def test_other_http_errors_are_not_swallowed(self):
        for code in (400, 401, 403, 404, 500, 503):
            with self.subTest(code=code):
                client = AssigneeRejectingClient(code=code)
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    self.run_sync(client)
                self.assertEqual(ctx.exception.code, code)
                self.assertEqual(len(client.attempts), 1)             # 재시도하지 않는다

    def test_non_http_errors_are_not_swallowed(self):
        class Down(FakeClient):
            def create_issue(self, title, body, assignees=None):
                raise OSError("network down")
        with self.assertRaises(OSError):
            self.run_sync(Down())

    def test_a_422_without_an_assignee_is_not_an_assignee_problem(self):
        client = AssigneeRejectingClient(always=True)
        with self.assertRaises(urllib.error.HTTPError):
            self.run_sync(client, owner=None)
        self.assertEqual(client.attempts, [(CRIT.title, None)])

    def test_a_422_on_the_retry_is_raised(self):
        client = AssigneeRejectingClient(always=True)
        with self.assertRaises(urllib.error.HTTPError):
            self.run_sync(client)
        self.assertEqual(client.attempts, [(CRIT.title, [OWNER]), (CRIT.title, None)])

    def test_dry_run_does_not_call_the_api_at_all(self):
        client = AssigneeRejectingClient()
        (created, _, _, _), lines = self.run_sync(client, dry=True)
        self.assertEqual((created, client.attempts), ([CRIT.title], []))


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


class Py310Datetime(datetime):
    """Python 3.10 의 datetime.fromisoformat 흉내: 끝의 'Z' 를 읽지 못한다(3.11 부터 읽는다)."""

    @classmethod
    def fromisoformat(cls, value):
        if isinstance(value, str) and value[-1:] in ("Z", "z"):
            raise ValueError(f"Invalid isoformat string: {value!r}")
        return datetime.fromisoformat(value)


class CommitTimeFormatTest(unittest.TestCase):
    """F-1: git 2.45+ 는 UTC 커밋 시각을 '...Z' 로 낸다. Python 3.10 의 fromisoformat 은 그걸 못 읽어 그 커밋이 조용히 사라졌다.
    시각은 epoch(%ct)로 읽으므로 Z·오프셋·epoch 어느 모양으로 저장된 커밋이든 같은 시각으로 읽혀야 한다."""

    @classmethod
    def setUpClass(cls):
        base = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=3)
        cls.expected = [base, base + timedelta(hours=1), base + timedelta(hours=2)]       # 오래된 순
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.root = Path(tmp.name)
        build_repo(cls.root, [
            (cls.expected[0].astimezone(timezone(timedelta(hours=9))), {"_posts/a.md": "a"}, "offset +09:00"),
            (cls.expected[1], {"_posts/b.md": "b"}, "UTC (git prints a Z suffix)"),
            (f"{int(cls.expected[2].timestamp())} -0500", {"_posts/c.md": "c"}, "raw epoch with -05:00"),
        ])

    def test_z_offset_and_epoch_commit_dates_all_read_as_the_same_instants(self):
        times = watchdog.commit_times(self.root, "_posts", added_only=True)
        self.assertEqual(times, list(reversed(self.expected)))                 # 최신순
        self.assertTrue(all(t.tzinfo is not None for t in times))
        self.assertEqual(watchdog.last_commit_time(self.root, "_posts", added_only=True), self.expected[2])
        self.assertEqual(watchdog.last_commit_time(self.root, "_posts"), self.expected[2])

    def test_it_works_when_fromisoformat_cannot_read_z_like_python_3_10(self):
        with mock.patch.object(watchdog, "datetime", Py310Datetime):
            times = watchdog.commit_times(self.root, "_posts", added_only=True)
            last = watchdog.last_commit_time(self.root, "_posts")
        self.assertEqual(times, list(reversed(self.expected)))                 # Z 커밋이 사라지지 않는다
        self.assertEqual(last, self.expected[2])

    def test_unreadable_lines_are_skipped_not_fatal(self):
        def fake_run(cmd, **kwargs):
            out = "false\n" if cmd[:2] == ["git", "rev-parse"] else "1760003600\n\nnot-a-number\n99999999999999999999\n1760000000\n"
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
        with mock.patch.object(watchdog.subprocess, "run", fake_run):
            times = watchdog.commit_times(".", "_posts")
        self.assertEqual([int(t.timestamp()) for t in times], [1760003600, 1760000000])
        self.assertTrue(all(t.utcoffset() == timedelta(0) for t in times))


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
            def workflow_runs(self, name, branch=None):
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
        # 검사가 꺼진 채 초록이 이어지지 않도록 Actions 화면에 경고 주석으로도 올라간다(F-10)
        warnings = [ln for ln in buf.getvalue().splitlines() if ln.startswith("::warning::")]
        self.assertEqual(len(warnings), 1, buf.getvalue())
        self.assertIn("Pages", warnings[0])
        self.assertIn("조회 실패", warnings[0])


class _Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RecordingOpener:
    """urllib.request.urlopen 대용: 요청의 메서드·주소를 기록하고 빈 실행 목록을 돌려준다."""

    def __init__(self):
        self.calls = []

    def __call__(self, req, timeout=None):
        self.calls.append((req.get_method(), req.full_url))
        return _Reply(b'{"workflow_runs": []}')


JEKYLL_REG = {"blogs": [{"key": "chance", "name": "C", "platform": "jekyll-git", "mode": "auto",
                         "workflow": ".github/workflows/chanceblog.yml",
                         "state": {"history": "history.json", "content_dir": "_posts"},
                         "health": {"max_gap_hours": 36, "max_failure_streak": 3}}], "defaults": {}}


class PagesLookupTest(unittest.TestCase):
    """F-10: Pages 실행 이력은 main 브랜치 것만 본다. 조회가 실패하면 Actions 화면에 경고 주석으로 올린다."""

    def collect(self, client):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(watchdog, "enabled_blogs", return_value=JEKYLL_REG["blogs"]), \
                mock.patch.object(watchdog, "commit_times", canned_commit_times([NOW - timedelta(hours=2)])):
            (Path(tmp) / "history.json").write_text("[]", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                findings, _ = watchdog.collect(JEKYLL_REG, tmp, NOW, client=client)
        return findings, buf.getvalue()

    def test_github_client_can_restrict_runs_to_a_branch(self):
        opener = RecordingOpener()
        client = watchdog.GitHubClient("t", "o/r", opener=opener)
        client.workflow_runs("pages.yml", branch="main")
        client.workflow_runs("chanceblog.yml")
        (_, pages_url), (_, other_url) = opener.calls
        self.assertTrue(pages_url.startswith("https://api.github.com/repos/o/r/actions/workflows/pages.yml/runs?"))
        self.assertIn("status=completed", pages_url)
        self.assertTrue(pages_url.endswith("&branch=main"), pages_url)
        self.assertNotIn("branch=", other_url)                 # 블로그 엔진 실행 이력은 브랜치로 거르지 않는다

    def test_branch_name_is_url_quoted(self):
        opener = RecordingOpener()
        watchdog.GitHubClient("t", "o/r", opener=opener).workflow_runs("pages.yml", branch="feature/x y&z")
        self.assertTrue(opener.calls[0][1].endswith("&branch=feature%2Fx%20y%26z"), opener.calls[0][1])

    def test_collect_asks_for_the_main_branch_runs_of_the_pages_workflow(self):
        gh = FakeGitHub()
        self.collect(gh)
        self.assertEqual(gh.runs_asked[0], (watchdog.PAGES_WORKFLOW, "main"))
        self.assertEqual(watchdog.PAGES_BRANCH, "main")

    def test_a_multiline_error_text_cannot_start_a_workflow_command(self):
        class Evil:
            def workflow_runs(self, name, branch=None):
                raise OSError("down\n::error::pwned\r\n::notice::q\u2028::warning::z\x85::set-output name=a::b")
        findings, out = self.collect(Evil())
        commands = [ln for ln in out.splitlines() if ln.startswith("::")]
        self.assertEqual(len(commands), 1, out)                # 의도한 ::warning:: 한 줄뿐
        self.assertTrue(commands[0].startswith("::warning::Pages 워크플로 실행 이력 조회 실패"), commands[0])
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

    def test_issue_closed_in_this_run_is_not_listed_as_open_in_the_summary(self):
        code, out, client, summary = self.run_main([], open_issues=[open_issue(WARN, number=9)])
        self.assertEqual(client.closed, [9])
        self.assertIn(f"이슈 해소: {WARN.title}", summary)
        self.assertNotIn("열려 있는 워치독 이슈", summary)

    def test_issues_that_stay_open_are_still_listed_in_the_summary(self):
        keep, gone = open_issue(CRIT, number=5, notified_hours_ago=2), open_issue(WARN, number=9)
        code, out, client, summary = self.run_main([CRIT], open_issues=[keep, gone])
        self.assertEqual(client.closed, [9])
        self.assertIn(f"열려 있는 워치독 이슈: #5 {CRIT.title}", summary)
        self.assertNotIn("#9", summary)

    def test_dry_run_still_lists_an_issue_it_would_have_closed(self):
        code, out, client, summary = self.run_main([], open_issues=[open_issue(WARN, number=9)],
                                                   env={"WATCHDOG_DRY_RUN": "1"})
        self.assertEqual((code, client.closed), (0, []))      # 실제로는 닫지 않았으니 아직 열려 있다
        self.assertIn("#9", summary)

    def test_finding_text_cannot_start_a_workflow_command_on_its_own_line(self):
        """사유처럼 이력에서 인용한 텍스트에 줄바꿈이 있어도 '::error::' 같은 줄이 새로 생기지 않는다(F-6)."""
        evil = "x\n::error::pwned\r\n::warning::z\u2028::notice::q\x85::set-output name=a::b"
        findings = [Finding("chance", "STALE", "critical", evil), Finding("blogger_macat", "UNPUBLISHED", "warning", evil)]
        code, out, client, _ = self.run_main(findings)
        commands = [ln for ln in out.splitlines() if ln.startswith("::")]       # splitlines 는 유니코드 줄 구분자도 가른다
        self.assertEqual(len(commands), 2, out)
        self.assertTrue(commands[0].startswith("::warning::[Watchdog] blogger_macat: UNPUBLISHED"), commands[0])
        self.assertTrue(commands[1].startswith("::error::새로 생긴 심각 건:"), commands[1])
        self.assertEqual(code, 1)

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
