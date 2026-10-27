"""승인 흐름(publish_flow: pr)에서 워치독이 '글이 안 나옴'을 멈춤이 아니라 승인 대기로 보는 규칙(DRAFT_WAITING) 시험. 네트워크 없이 돈다(병합 시각 시험 하나만 임시 저장소에서 git 을 네 번 부른다).

pipeline/health.py 의 evaluate(pending_drafts=…)와 scripts/watchdog.py 의 collect()·GitHubClient.list_open_draft_pulls 를 본다.
규칙: pr 흐름인 블로그에서 열린 초안 PR 이 있고 STALE·NO_POSTS_DAY 가 울릴 상황이면 그 둘을 빼고 DRAFT_WAITING(경고 = 확인 수준)을 낸다.
이 규칙이 맞게 돌도록 두 가지를 함께 고정한다: ① 글이 올라온 시각은 병합 시각이다(commit_times 의 --first-parent) ② 병합하지 않은 초안의 이력 항목은
'글이 나온 날'로 세지 않는다(post_days_from_history 의 drafts_count).
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from draft_helpers import HermeticGit
from pipeline import health
from watchdog_helpers import FakeGitHub, canned_commit_times, iso_z, run_record

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402

NOW = datetime(2026, 10, 28, 3, 0, tzinfo=timezone.utc)        # KST 12시
PR_BLOG = {"key": "chance", "platform": "jekyll-git", "mode": "auto", "publish_flow": "pr",
           "state": {"history": "history.json", "content_dir": "_posts"}, "workflow": ".github/workflows/chanceblog.yml",
           "health": {"max_gap_hours": 36, "max_failure_streak": 3}}
DIRECT_BLOG = {**PR_BLOG, "publish_flow": "direct"}
LEGACY_BLOG = {k: v for k, v in PR_BLOG.items() if k != "publish_flow"}


def pending(*hours_ago):
    return [{"number": 40 + i, "created_at": iso_z(NOW - timedelta(hours=h))} for i, h in enumerate(hours_ago)]


def codes(findings):
    return sorted(f.code for f in findings)


STALE_COMMIT = NOW - timedelta(hours=80)               # 마지막 새 글 커밋: 80시간 전(허용 36시간)


class DraftWaitingEvaluateTest(unittest.TestCase):
    def evaluate(self, blog=PR_BLOG, drafts=None, commit=STALE_COMMIT, history=(), **kwargs):
        return health.evaluate(blog, list(history), NOW, last_content_commit=commit, pending_drafts=drafts, **kwargs)

    def test_stale_becomes_a_waiting_warning_when_drafts_are_pending(self):
        findings = self.evaluate(drafts=pending(30, 5))
        self.assertEqual([(f.code, f.severity) for f in findings], [("DRAFT_WAITING", "warning")])
        self.assertEqual(findings[0].title, "[Watchdog] chance: DRAFT_WAITING")
        message = findings[0].message
        self.assertIn("승인(PR 병합)을 기다리는 초안이 2건 있습니다(가장 오래된 것 1일 전)", message)
        self.assertIn("멈춤이 아니라 승인 대기", message)
        self.assertIn("병합하면 공개, 닫으면 폐기", message)

    def test_without_pending_drafts_stale_stays_critical(self):
        for drafts in (None, []):
            findings = self.evaluate(drafts=drafts)
            self.assertEqual([(f.code, f.severity) for f in findings], [("STALE", "critical")], drafts)

    def test_a_direct_flow_blog_ignores_the_pending_list_entirely(self):
        for blog in (DIRECT_BLOG, LEGACY_BLOG):
            findings = self.evaluate(blog=blog, drafts=pending(3))
            self.assertEqual([(f.code, f.severity) for f in findings], [("STALE", "critical")])

    def test_recent_posts_mean_no_waiting_finding_at_all(self):
        findings = self.evaluate(drafts=pending(3), commit=NOW - timedelta(hours=5))
        self.assertEqual(findings, [])

    def test_no_posts_day_is_replaced_too_at_both_severities(self):
        days = {(NOW - timedelta(days=5)).date()}                      # 어제·그제 모두 글이 없음 → 심각
        findings = health.evaluate(PR_BLOG, [], NOW, last_content_commit=NOW - timedelta(hours=30), post_days=days, pending_drafts=pending(3))
        self.assertEqual(codes(findings), ["DRAFT_WAITING"])
        self.assertEqual(codes(health.evaluate(PR_BLOG, [], NOW, last_content_commit=NOW - timedelta(hours=30), post_days=days)), ["NO_POSTS_DAY"])
        yesterday_only = {(NOW - timedelta(days=2)).date()}            # 그제만 글이 있음 → 어제 0건은 경고
        findings = health.evaluate(PR_BLOG, [], NOW, last_content_commit=NOW - timedelta(hours=30), post_days=yesterday_only, pending_drafts=pending(3))
        self.assertEqual([(f.code, f.severity) for f in findings], [("DRAFT_WAITING", "warning")])

    def test_only_one_waiting_finding_even_when_both_triggers_fire(self):
        days = {(NOW - timedelta(days=5)).date()}
        findings = health.evaluate(PR_BLOG, [], NOW, last_content_commit=STALE_COMMIT, post_days=days, pending_drafts=pending(3))
        # STALE 이 울리면 NO_POSTS_DAY 는 중복 알림을 만들지 않는다(기존 규칙). 어느 쪽이든 DRAFT_WAITING 하나만 남는다
        self.assertEqual(codes(findings), ["DRAFT_WAITING"])

    def test_unrelated_findings_are_kept(self):
        runs = [{"conclusion": "failure"}] * 3
        findings = self.evaluate(drafts=pending(3), recent_runs=runs)
        self.assertEqual(codes(findings), ["DRAFT_WAITING", "RUN_FAIL_STREAK"])
        pages = [{"conclusion": "failure", "created_at": iso_z(NOW)}]
        self.assertIn("PAGES_FAILED", codes(self.evaluate(drafts=pending(3), pages_runs=pages)))

    def test_no_activity_is_not_a_missing_post_and_is_kept(self):
        findings = health.evaluate(PR_BLOG, [], NOW, pending_drafts=pending(3))
        self.assertEqual(codes(findings), ["NO_ACTIVITY"])

    def test_the_waiting_time_is_in_days_from_a_day_on_and_in_hours_below(self):
        self.assertIn("가장 오래된 것 5시간 전", health._waiting_message(pending(5, 1), NOW))
        self.assertIn("가장 오래된 것 0시간 전", health._waiting_message(pending(0.2), NOW))
        self.assertIn("가장 오래된 것 1일 전", health._waiting_message(pending(24), NOW))
        self.assertIn("가장 오래된 것 1일 전", health._waiting_message(pending(47), NOW))
        self.assertIn("가장 오래된 것 2일 전", health._waiting_message(pending(48), NOW))
        self.assertIn("가장 오래된 것 9일 전", health._waiting_message(pending(9 * 24 + 5, 2), NOW))

    def test_the_oldest_draft_decides_the_age_whatever_the_list_order(self):
        for order in ((70, 3), (3, 70)):
            self.assertIn("가장 오래된 것 2일 전", health._waiting_message(pending(*order), NOW))

    def test_unreadable_times_still_count_the_drafts(self):
        message = health._waiting_message([{"number": 1, "created_at": "엉터리"}, {"number": 2}, "문자열"], NOW)
        self.assertIn("초안이 3건 있습니다", message)
        self.assertNotIn("가장 오래된", message)

    def test_a_future_creation_time_does_not_print_a_negative_age(self):
        message = health._waiting_message([{"created_at": iso_z(NOW + timedelta(hours=3))}], NOW)
        self.assertIn("가장 오래된 것 0시간 전", message)

    def test_mode_off_still_returns_nothing(self):
        self.assertEqual(health.evaluate({**PR_BLOG, "mode": "off"}, [], NOW, pending_drafts=pending(3)), [])

    def drafts_in_history(self, *days_ago):
        return [{"date": str((NOW - timedelta(days=d)).date()), "slot": 9, "flow": "pr", "branch": f"ai/draft/x{d}", "paths": []} for d in days_ago]

    def test_unmerged_draft_entries_are_not_post_days_when_the_commit_days_are_known(self):
        """초안을 만들면 이력 항목이 생기지만 글은 병합할 때 main 에 올라간다. 글 커밋 날짜를 알면 병합하지 않은 초안 항목이 '글이 나온 날'로 세어져
        NO_POSTS_DAY 를 가리면 안 된다."""
        history = self.drafts_in_history(1, 2)                               # 어제·그제 초안(병합하지 않음)
        kw = dict(last_content_commit=NOW - timedelta(hours=30), post_days={(NOW - timedelta(days=5)).date()})
        self.assertEqual(codes(health.evaluate(PR_BLOG, history, NOW, **kw)), ["NO_POSTS_DAY"])
        self.assertEqual(codes(health.evaluate(PR_BLOG, history, NOW, pending_drafts=pending(3), **kw)), ["DRAFT_WAITING"])
        direct = [{k: v for k, v in e.items() if k not in ("flow", "branch", "paths")} for e in history]
        self.assertEqual(health.evaluate(PR_BLOG, direct, NOW, **kw), [])        # flow 표시가 없는 항목(직접 게시)은 예전처럼 글이 나온 날이다

    def test_a_merged_draft_counts_through_its_commit_day(self):
        kw = dict(last_content_commit=NOW - timedelta(hours=5), post_days={NOW.astimezone(timezone(timedelta(hours=9))).date()})
        self.assertEqual(health.evaluate(PR_BLOG, self.drafts_in_history(1, 2), NOW, **kw), [])

    def test_without_commit_days_the_draft_entries_count_as_before(self):
        """얕은 복제라 글 커밋 날짜를 모르면(post_days 없음) 이력만으로 판단한다 — 승인 흐름 항목도 예전처럼 센다."""
        older = {"date": str((NOW - timedelta(days=5)).date()), "slot": 9}                   # 날짜가 있는 다른 글이 있어야 '글 없는 날' 판정이 켜진다
        history = [older] + self.drafts_in_history(1)
        self.assertEqual(health.evaluate(PR_BLOG, history, NOW, last_content_commit=None, post_days=None), [])
        self.assertEqual(codes(health.evaluate(PR_BLOG, [older], NOW, last_content_commit=None, post_days=None)), ["STALE"])    # 대조: 초안 항목이 없으면 울린다
        self.assertEqual(health.post_days_from_history(self.drafts_in_history(1, 2)), {(NOW - timedelta(days=1)).date(), (NOW - timedelta(days=2)).date()})
        self.assertEqual(health.post_days_from_history(self.drafts_in_history(1, 2), drafts_count=False), set())

    def test_the_waiting_text_never_contains_external_text(self):
        findings = self.evaluate(drafts=[{"number": 1, "created_at": iso_z(NOW - timedelta(hours=30)), "title": "@evil ::error::x"}])
        self.assertNotIn("evil", findings[0].message)
        self.assertNotIn("::", findings[0].message)


class DraftGitHub(FakeGitHub):
    """워치독용 가짜 GitHub 에 열린 초안 PR 목록을 더한다."""

    def __init__(self, drafts=None, error=None, **kwargs):
        # 글 커밋(80시간 전) 뒤에 성공한 배포가 있어 PAGES_NOT_DEPLOYED 가 끼어들지 않는다
        kwargs.setdefault("runs", {"pages.yml": [run_record("success", STALE_COMMIT + timedelta(minutes=2))]})
        super().__init__(**kwargs)
        self.drafts, self.error = drafts, error

    def list_open_draft_pulls(self):
        self.calls.append(("draft-pulls",))
        if self.error is not None:
            raise self.error
        return list(self.drafts or [])


class DraftWaitingCollectTest(unittest.TestCase):
    def collect(self, blog, client, commits=(STALE_COMMIT,), history=()):
        reg = {"blogs": [json.loads(json.dumps(blog))], "defaults": {}}
        buf = io.StringIO()
        with tempfile_root(history) as root, mock.patch.object(watchdog, "commit_times", canned_commit_times(list(commits))), contextlib.redirect_stdout(buf):
            findings, stats = watchdog.collect(reg, root, NOW, client)
        return findings, stats, buf.getvalue()

    def test_pending_drafts_turn_stale_into_a_waiting_warning(self):
        gh = DraftGitHub(drafts=pending(30, 5))
        findings, stats, _ = self.collect(PR_BLOG, gh)
        self.assertEqual([(f.code, f.severity) for f in findings], [("DRAFT_WAITING", "warning")])
        self.assertEqual(stats[0]["codes"], ["DRAFT_WAITING"])
        self.assertIn(("draft-pulls",), gh.calls)

    def test_an_empty_list_leaves_the_critical_stale(self):
        findings, _, _ = self.collect(PR_BLOG, DraftGitHub(drafts=[]))
        self.assertEqual([(f.code, f.severity) for f in findings], [("STALE", "critical")])

    def test_a_listing_failure_falls_back_to_the_old_rules_and_says_so(self):
        gh = DraftGitHub(error=urllib.error.HTTPError("https://api.github.com/x", 500, "err", {}, io.BytesIO(b"{}")))
        findings, _, out = self.collect(PR_BLOG, gh)
        self.assertEqual([(f.code, f.severity) for f in findings], [("STALE", "critical")])
        self.assertIn("초안 PR 목록 조회 실패(승인 대기 구분을 건너뜀)", out)

    def test_a_direct_flow_blog_never_lists_pull_requests(self):
        for blog in (DIRECT_BLOG, LEGACY_BLOG):
            gh = DraftGitHub(drafts=pending(3))
            findings, _, _ = self.collect(blog, gh)
            self.assertEqual([(f.code, f.severity) for f in findings], [("STALE", "critical")])
            self.assertNotIn(("draft-pulls",), gh.calls)

    def test_without_a_client_nothing_is_listed(self):
        findings, _, _ = self.collect(PR_BLOG, None)
        self.assertEqual([(f.code, f.severity) for f in findings], [("STALE", "critical")])

    def test_a_waiting_warning_does_not_turn_the_watchdog_run_red(self):
        """심각 건이 새로 생겼을 때만 실행이 빨강이다. 승인 대기는 경고라 이슈는 열리지만 실행은 초록이다."""
        findings, _, _ = self.collect(PR_BLOG, DraftGitHub(drafts=pending(30)))
        gh = FakeGitHub(now=NOW)
        created, closed, renotified, new_critical = watchdog.sync_issues(findings, [], gh, owner="shine88pc", now=NOW, out=lambda text: None)
        self.assertEqual((created, new_critical), (["[Watchdog] chance: DRAFT_WAITING"], []))
        body = next(iter(gh.issues.values()))["body"]
        self.assertIn("심각도**: warning", body)
        self.assertIn("승인(PR 병합)을 기다리는 초안이 1건", body)

    def test_the_stale_issue_is_closed_when_the_state_turns_into_waiting(self):
        stale_finding = health.Finding("chance", "STALE", "critical", "x")
        gh = FakeGitHub(now=NOW)
        number = gh.add_issue(stale_finding.title, watchdog.issue_body(stale_finding, "shine88pc"))
        findings, _, _ = self.collect(PR_BLOG, DraftGitHub(drafts=pending(30)))
        created, closed, _, _ = watchdog.sync_issues(findings, gh.list_open_issues(), gh, owner="shine88pc", now=NOW, out=lambda text: None)
        self.assertEqual((created, closed), (["[Watchdog] chance: DRAFT_WAITING"], ["[Watchdog] chance: STALE"]))
        self.assertEqual(gh.issues[number]["state"], "closed")


class MergeTimeTest(unittest.TestCase):
    """승인 흐름의 글은 PR 병합 커밋으로 main 에 들어온다. '글이 올라온 시각'은 초안을 만든 시각이 아니라 병합 시각이어야 한다(임시 저장소, git 4번)."""
    SEED, DRAFT, MERGE = 1792454400, 1792540800, 1792710000               # 2026-10-20 · 10-21 · 10-23 (UTC 자정)

    @staticmethod
    def stream(seed, draft, merge):
        """git fast-import 입력: main(시드) ← draft(글 추가) 를 시각이 다른 병합 커밋으로 합친 저장소 하나(커밋 시각을 마음대로 정할 수 있어 git 호출이 적다)."""
        def data(text):
            raw = text.encode("utf-8")
            return b"data %d\n%s\n" % (len(raw), raw)
        who = b"t <t@e.test>"
        path = b"_posts/tech/2026-10-21-KR-090000.md"
        parts = [b"blob\nmark :1\n" + data("keep\n"), b"blob\nmark :2\n" + data("새 글\n"),
                 b"commit refs/heads/main\nmark :10\ncommitter %s %d +0000\n" % (who, seed) + data("seed") + b"M 100644 :1 _posts/keep.txt\n\n",
                 b"commit refs/heads/draft\nmark :11\ncommitter %s %d +0000\n" % (who, draft) + data("draft") + b"from :10\nM 100644 :2 " + path + b"\n\n",
                 b"commit refs/heads/main\nmark :12\ncommitter %s %d +0000\n" % (who, merge) + data("Merge pull request")
                 + b"from :10\nmerge :11\nM 100644 :2 " + path + b"\n\n"]
        return b"".join(parts)

    def test_the_added_post_time_is_the_merge_time_not_the_draft_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            hermetic = HermeticGit(tmp)
            repo = Path(tmp) / "r"
            repo.mkdir()
            hermetic.run(repo, "init", "-q", "-b", "main")
            subprocess.run(["git", "fast-import", "--quiet"], cwd=str(repo), env={**os.environ, **hermetic.env},
                           input=self.stream(self.SEED, self.DRAFT, self.MERGE), check=True, capture_output=True)
            times = watchdog.commit_times(repo, "_posts", added_only=True, since="2000-01-01")
        merge, draft = (datetime.fromtimestamp(t, timezone.utc) for t in (self.MERGE, self.DRAFT))
        self.assertEqual(times, [merge, datetime.fromtimestamp(self.SEED, timezone.utc)])      # 병합 시각이 글을 더한 시각이다
        self.assertNotIn(draft, times)


@contextlib.contextmanager
def tempfile_root(history):
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "history.json").write_text(json.dumps(list(history)), encoding="utf-8")
        yield Path(tmp)


class ListOpenDraftPullsTest(unittest.TestCase):
    class Opener:
        def __init__(self, payload):
            self.payload, self.requests = payload, []

        def __call__(self, request, timeout=None):
            self.requests.append(request)
            outer = self

            class Response:
                def read(self):
                    return json.dumps(outer.payload).encode("utf-8")

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False
            return Response()

    def pr(self, number, ref, repo="shine88pc/chanceblog", created="2026-10-27T00:00:00Z"):
        return {"number": number, "created_at": created, "head": {"ref": ref, "repo": {"full_name": repo}}}

    def client(self, payload):
        opener = self.Opener(payload)
        return watchdog.GitHubClient("t", "shine88pc/chanceblog", opener=opener), opener

    def test_only_open_draft_branch_prs_of_this_repository(self):
        client, opener = self.client([self.pr(1, "ai/draft/2026-10-27-s9"), self.pr(2, "ai/claude/x"), self.pr(3, "ai/draft/2026-10-27-s18", repo="fork/chanceblog"),
                                      self.pr(4, "ai/draft/2026-10-26-s18", repo="Shine88PC/ChanceBlog"), {"head": None}, "junk"])
        self.assertEqual(client.list_open_draft_pulls(), [{"number": 1, "created_at": "2026-10-27T00:00:00Z"}, {"number": 4, "created_at": "2026-10-27T00:00:00Z"}])
        self.assertIn("state=open", opener.requests[0].full_url)
        self.assertTrue(opener.requests[0].full_url.startswith("https://api.github.com/repos/shine88pc/chanceblog/pulls"))

    def test_an_empty_answer_is_an_empty_list(self):
        client, _ = self.client(None)
        self.assertEqual(client.list_open_draft_pulls(), [])


if __name__ == "__main__":
    unittest.main()
