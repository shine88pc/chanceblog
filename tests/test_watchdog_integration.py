"""워치독 통합 테스트: 가짜 GitHub + 임시 git 저장소로 collect()·main() 을 끝까지 돌린다.

배경(독립 검증 F-3): 단위 테스트가 sync_issues()·evaluate() 를 따로 점검하느라, 둘을 잇는 배선을 끊어도 테스트가 통과했다 —
collect() 가 post_days·pages_runs 를 evaluate() 에 넘기는 것, main() 이 소유자를 sync_issues() 에 넘기는 것,
드라이런이 이슈를 건드리지 않는 것, KST 날짜 경계, 사이트 배포 워크플로 파일 이름 등. 여기서는 실제 collect()/
sync_issues()/main() 코드를 그대로 거쳐 그 배선을 고정한다.

git 이력이 필요한 점검(collect 배선, KST, 얕은 복제, main 한 건)은 실제 임시 저장소를 쓴다. 이슈·Pages 쪽 동작만 보는
테스트는 git 프로세스를 띄우지 않고 글 커밋 시각만 대체한다(canned_commit_times). 시각은 실제 시계 기준으로 만든다:
워치독이 `git log --since="30 days ago"` 로 읽기 때문이다.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _bootstrap  # noqa: F401
from pipeline.health import Finding
from pipeline.registry import enabled_blogs, load_registry
from pipeline.state import KST
from watchdog_helpers import WORKFLOW_DIR, FakeGitHub, build_repo, canned_commit_times, kst_time, run_record, today_kst
from watchdog_helpers import shallow_clone

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402

OWNER = "shine88pc"
CHANCE = {"key": "chance", "name": "Chance_Blog", "platform": "jekyll-git", "mode": "auto",
          "workflow": ".github/workflows/chanceblog.yml",
          "state": {"history": "history.json", "content_dir": "_posts"},
          "health": {"max_gap_hours": 36, "max_failure_streak": 3}}
DEFAULT_ENV = {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": f"{OWNER}/chanceblog", "GITHUB_REPOSITORY_OWNER": OWNER}
CONTROL_ENV = ("PIPELINE_PAUSE", "WATCHDOG_DRY_RUN", "GITHUB_TOKEN", "GITHUB_REPOSITORY", "GITHUB_REPOSITORY_OWNER",
               "GITHUB_STEP_SUMMARY")


def registry(max_gap_hours=None):
    blog = json.loads(json.dumps(CHANCE))
    if max_gap_hours is not None:
        blog["health"]["max_gap_hours"] = max_gap_hours
    return {"blogs": [blog], "defaults": {}}


def new_repo(add_cleanup, posts=(), history=None, extra=()):
    """임시 git 저장소: 기본 커밋(history.json) 뒤에 posts 시각마다 글 파일을 추가하는 커밋을 쌓는다(extra 는 그 뒤 커밋).
    작업 트리에는 history.json 만 쓴다(워치독은 이력 파일을 작업 트리에서 읽고, 글 커밋은 git 이력에서 읽는다)."""
    tmp = tempfile.TemporaryDirectory()
    add_cleanup(tmp.cleanup)
    root = Path(tmp.name)
    history_json = json.dumps(history or [], ensure_ascii=False)
    commits = [(datetime.now(timezone.utc) - timedelta(days=20), {"history.json": history_json, "README.txt": "base"}, "base")]
    commits += [(when, {f"_posts/post-{n}.md": f"post {n}"}, f"add post {n}") for n, when in enumerate(sorted(posts))]
    build_repo(root, commits + list(extra))
    (root / "history.json").write_text(history_json, encoding="utf-8")
    return root


def collect(root, now, client=None, max_gap_hours=None):
    buf = io.StringIO()
    with redirect_stdout(buf):
        findings, stats = watchdog.collect(registry(max_gap_hours), root, now, client)
    return findings, stats, buf.getvalue()


def summarize(findings):
    return [(f.code, f.severity) for f in findings]


class WorkflowNamesTest(unittest.TestCase):
    """PAGES_WORKFLOW 이름이 틀리면 GitHub 이 404 를 내고 배포 검사가 조용히 꺼진다 — 실제 파일과 맞는지 고정한다."""

    def test_pages_workflow_is_a_real_workflow_file(self):
        path = WORKFLOW_DIR / watchdog.PAGES_WORKFLOW
        self.assertTrue(path.is_file(), f"{path} 가 없다: 사이트 배포 점검이 항상 건너뛰어진다")
        self.assertIn("name: Deploy GitHub Pages", path.read_text(encoding="utf-8"))  # 점검 메시지가 부르는 이름

    def test_every_registered_blog_workflow_is_a_real_workflow_file(self):
        for blog in enabled_blogs(load_registry()):
            name = Path(blog["workflow"]).name
            self.assertTrue((WORKFLOW_DIR / name).is_file(), f"{blog['key']}: {name}")

    def test_the_fake_github_answers_404_for_unknown_workflows_like_the_real_api(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            FakeGitHub().workflow_runs("page.yml")
        self.assertEqual(ctx.exception.code, 404)


class CollectWiringTest(unittest.TestCase):
    """collect() 가 이력·글 커밋·실행 이력을 evaluate() 에 제대로 넘기는지(끊으면 해당 알림이 사라진다). 실제 git 이력 사용."""

    @classmethod
    def setUpClass(cls):
        today = today_kst()
        cls.now = kst_time(today, 12)                        # KST 정오(UTC 03:00)
        cls.committed = cls.now - timedelta(hours=5)         # 오늘 KST 07:00 에 글 1건
        cls.recent_post = new_repo(cls.addClassCleanup, posts=[cls.committed])
        cls.old_post = new_repo(cls.addClassCleanup, posts=[kst_time(today - timedelta(days=3), 10)])

    def pages(self, *runs):
        return FakeGitHub(runs={"pages.yml": list(runs)})

    def test_two_days_without_a_new_post_reach_the_evaluation_through_post_days(self):
        findings, stats, _ = collect(self.old_post, self.now, max_gap_hours=200)
        self.assertEqual(summarize(findings), [("NO_POSTS_DAY", "critical")])
        self.assertEqual(stats[0]["posts_7d"], 1)
        self.assertEqual(stats[0]["codes"], ["NO_POSTS_DAY"])

    def test_no_deploy_after_the_post_commit_reaches_the_evaluation_through_pages_runs(self):
        findings, _, _ = collect(self.recent_post, self.now, self.pages())
        self.assertEqual(summarize(findings), [("PAGES_NOT_DEPLOYED", "critical")])

    def test_a_deploy_after_the_post_commit_keeps_everything_quiet(self):
        findings, stats, _ = collect(self.recent_post, self.now, self.pages(
            run_record("success", self.committed + timedelta(minutes=2))))
        self.assertEqual(findings, [])            # 오늘 글 있음 + 배포됨
        self.assertEqual(stats[0]["last_post"], self.committed)

    def test_only_main_branch_runs_count_as_a_deployment(self):
        """다른 ref 에서 workflow_dispatch 로 돌린 성공은 사이트 배포가 아니다(F-10)."""
        gh = self.pages(run_record("success", self.committed + timedelta(minutes=2), head_branch="feature/x"))
        findings, _, _ = collect(self.recent_post, self.now, gh)
        self.assertEqual(summarize(findings), [("PAGES_NOT_DEPLOYED", "critical")])
        self.assertIn((watchdog.PAGES_WORKFLOW, "main"), gh.runs_asked)

    def test_workflow_run_history_reaches_the_evaluation(self):
        gh = FakeGitHub(runs={
            "pages.yml": [run_record("success", self.committed + timedelta(minutes=2))],
            "chanceblog.yml": [run_record("failure", self.now - timedelta(hours=h)) for h in (1, 2, 3)]})
        findings, _, _ = collect(self.recent_post, self.now, gh)
        self.assertEqual(summarize(findings), [("RUN_FAIL_STREAK", "critical")])
        self.assertIn(("chanceblog.yml", None), gh.runs_asked)


class KstBoundaryTest(unittest.TestCase):
    """날짜 경계는 KST 다. 워치독은 UTC 15:30(= KST 00:30, 날짜가 막 바뀐 시각)에도 돈다."""

    @classmethod
    def setUpClass(cls):
        day = today_kst()
        # (1) UTC 15:30 = KST 다음 날 00:30. KST 어제(day-1) 20:00 에 글 1건.
        cls.midnight_day = day
        cls.midnight_now = datetime.combine(day, time(15, 30), tzinfo=timezone.utc)
        cls.midnight_repo = new_repo(cls.addClassCleanup, posts=[kst_time(day - timedelta(days=1), 20)])
        # (2) KST 01:00(= UTC 전날 16:00)에 나온 글, 그 다음 날 KST 정오에 점검.
        cls.post_day = day - timedelta(days=1)
        cls.after_midnight_commit = kst_time(cls.post_day, 1, 0)
        cls.after_midnight_now = kst_time(day, 12)
        cls.after_midnight_repo = new_repo(cls.addClassCleanup, posts=[cls.after_midnight_commit])

    def test_midnight_run_judges_the_kst_day_that_just_closed(self):
        self.assertEqual(self.midnight_now.astimezone(KST).date(), self.midnight_day + timedelta(days=1))
        findings, _, _ = collect(self.midnight_repo, self.midnight_now, max_gap_hours=200)
        # KST 로는 막 끝난 어제(midnight_day)에 글이 없다. UTC 날짜로 계산하면 그 전날 글이 '어제 글'이 되어 이 경고가 사라진다.
        self.assertEqual(summarize(findings), [("NO_POSTS_DAY", "warning")])
        self.assertIn(f"어제({self.midnight_day})", findings[0].message)

    def test_a_post_commit_just_after_kst_midnight_belongs_to_that_kst_day(self):
        self.assertEqual(self.after_midnight_commit.date(), self.post_day - timedelta(days=1))   # UTC 로는 전날
        findings, _, _ = collect(self.after_midnight_repo, self.after_midnight_now, max_gap_hours=200)
        # 글 날짜를 UTC 로 모으면 글이 하루 일찍 잡혀 '어제 새 글 0건' 경고가 오탐으로 뜬다.
        self.assertEqual(findings, [])


class MainCase(unittest.TestCase):
    def make_dir(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def run_main(self, fake, root=None, env=None, findings=None, times=None):
        """watchdog.main() 을 가짜 GitHub 로 돌린다(ROOT·레지스트리·환경변수는 임시 값).
        findings 를 주면 collect 를, times 를 주면 git 의 글 커밋 시각(commit_times)을 대체한다."""
        summary = self.make_dir() / "summary.md"
        environ = {k: v for k, v in os.environ.items() if k not in CONTROL_ENV}
        environ["GITHUB_STEP_SUMMARY"] = str(summary)
        for key, value in {**DEFAULT_ENV, **(env or {})}.items():
            if value is None:
                environ.pop(key, None)
            else:
                environ[key] = value
        client_cls = mock.MagicMock(return_value=fake)
        buf = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, environ, clear=True))
            stack.enter_context(mock.patch.object(watchdog, "ROOT", Path(root) if root else self.make_dir()))
            stack.enter_context(mock.patch.object(watchdog, "load_registry", return_value=registry()))
            stack.enter_context(mock.patch.object(watchdog, "validate_registry", return_value=[]))
            stack.enter_context(mock.patch.object(watchdog, "GitHubClient", client_cls))
            if findings is not None:
                stack.enter_context(mock.patch.object(watchdog, "collect", return_value=(findings, [])))
            if times is not None:
                stack.enter_context(mock.patch.object(watchdog, "commit_times", canned_commit_times(times)))
            with redirect_stdout(buf):
                code = watchdog.main()
        text = summary.read_text(encoding="utf-8") if summary.exists() else ""
        return SimpleNamespace(code=code, out=buf.getvalue(), summary=text, client_cls=client_cls)

    def stale(self, hours=100):
        """마지막 글이 hours 시간 전(허용 36시간이라 STALE)이고 그 글은 배포된 상태: (글 커밋 시각 목록, Pages 실행 이력)."""
        committed = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [committed], {"pages.yml": [run_record("success", committed + timedelta(minutes=2))]}


class MainEndToEndTest(MainCase):
    """실제 git 저장소 → collect → sync_issues → 가짜 GitHub. 소유자(담당자·@멘션)가 끝까지 전달되는지."""

    @classmethod
    def setUpClass(cls):
        cls.repo = new_repo(cls.addClassCleanup, posts=[datetime.now(timezone.utc) - timedelta(hours=100)])
        cls.runs = {"pages.yml": [run_record("success", datetime.now(timezone.utc) - timedelta(hours=99))]}

    def test_a_new_critical_issue_is_assigned_mentions_the_owner_and_fails_the_run(self):
        fake = FakeGitHub(runs=self.runs)
        res = self.run_main(fake, root=self.repo)
        self.assertEqual(res.code, 1)
        issues = list(fake.issues.values())
        self.assertEqual([i["title"] for i in issues], ["[Watchdog] chance: STALE"])
        self.assertEqual(issues[0]["assignees"], [OWNER])
        self.assertTrue(issues[0]["body"].startswith(f"@{OWNER} "), issues[0]["body"][:80])
        self.assertIn("::error::새로 생긴 심각 건: [Watchdog] chance: STALE", res.out)
        self.assertIn("| chance | auto |", res.summary)

    def test_owner_defaults_to_the_repository_owner_when_the_variable_is_missing(self):
        fake = FakeGitHub(runs=self.runs)
        self.run_main(fake, root=self.repo, env={"GITHUB_REPOSITORY_OWNER": None})
        issue = list(fake.issues.values())[0]
        self.assertEqual(issue["assignees"], [OWNER])
        self.assertTrue(issue["body"].startswith(f"@{OWNER} "))

    def test_no_owner_means_no_assignee_and_no_mention(self):
        fake = FakeGitHub(runs=self.runs)
        self.run_main(fake, root=self.repo, env={"GITHUB_REPOSITORY_OWNER": None, "GITHUB_REPOSITORY": "chanceblog"})
        issue = list(fake.issues.values())[0]
        self.assertEqual(issue["assignees"], [])
        self.assertNotIn("@", issue["body"])


class DryRunTest(MainCase):
    """드라이런(WATCHDOG_DRY_RUN 또는 토큰 없음)은 이슈를 만들지도 고치지도 닫지도 않고, 실패(exit 1)로 끝나지도 않는다."""

    def scenario(self):
        """STALE 이슈는 열려 있는데 본문이 낡고 48시간이 지났다(재알림 대상). 이미 풀린 UNPUBLISHED 이슈도 열려 있다.
        Pages 실행 이력이 없어 새 심각 건(PAGES_NOT_DEPLOYED)도 생긴다."""
        times, _ = self.stale()
        fake = FakeGitHub(runs={})
        now = datetime.now(timezone.utc)
        stale_body = watchdog.issue_body(Finding("chance", "STALE", "critical", "옛 메시지"), OWNER,
                                         (now - timedelta(hours=100)).isoformat(timespec="seconds"))
        fake.add_issue("[Watchdog] chance: STALE", stale_body, created_at=now - timedelta(days=5))
        fake.add_issue("[Watchdog] blogger_macat: UNPUBLISHED", "옛 본문", created_at=now - timedelta(days=2))
        return fake, times

    def test_control_without_dry_run_writes_and_fails_on_the_new_critical(self):
        fake, times = self.scenario()
        res = self.run_main(fake, times=times)
        self.assertEqual(res.code, 1)
        self.assertEqual(Counter(fake.verbs()), Counter({"comment": 2, "patch": 1, "create": 1, "close": 1}))

    def test_dry_run_variable_changes_nothing_even_with_open_issues(self):
        for value in ("1", "true"):
            with self.subTest(WATCHDOG_DRY_RUN=value):
                fake, times = self.scenario()
                res = self.run_main(fake, times=times, env={"WATCHDOG_DRY_RUN": value})
                self.assertEqual(fake.verbs(), [])                          # 본문 PATCH·코멘트·닫기·생성 모두 없음
                self.assertEqual(res.code, 0)                               # 새 심각 건이 있어도 빨강이 아니다
                self.assertNotIn("::error::", res.out)
                for plan in ("[알림 생성] [Watchdog] chance: PAGES_NOT_DEPLOYED", "[재알림] [Watchdog] chance: STALE",
                             "[알림 해소] [Watchdog] blogger_macat: UNPUBLISHED"):
                    self.assertIn(plan, res.out)                            # 계획은 출력에 보인다

    def test_without_a_token_the_github_client_is_never_built(self):
        times, _ = self.stale()
        res = self.run_main(FakeGitHub(), times=times, env={"GITHUB_TOKEN": None})
        self.assertEqual(res.code, 0)
        res.client_cls.assert_not_called()
        self.assertIn("dry-run", res.out)
        self.assertIn("| chance | auto |", res.summary)


class ShallowCloneTest(unittest.TestCase):
    """F-14: 얕은 복제에서는 가장 위 커밋이 모든 파일을 '새로 추가'한 것처럼 보인다 — 새 글로 오인하지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.now = datetime.now(timezone.utc)
        cls.post_time = cls.now - timedelta(hours=100)
        local = cls.post_time.astimezone(KST)
        history = [{"date": local.date().isoformat(), "status": "posted", "generated_at": local.isoformat()}]
        docs_only = (cls.now - timedelta(hours=1), {"notes.txt": "글이 아닌 커밋"}, "docs only")   # 맨 위 커밋
        cls.source = new_repo(cls.addClassCleanup, posts=[cls.post_time], history=history, extra=[docs_only])
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.shallow = Path(tmp.name) / "shallow"
        shallow_clone(cls.source, cls.shallow)

    def test_commit_times_says_unknown_for_a_shallow_clone_and_warns(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            added = watchdog.commit_times(self.shallow, "_posts", added_only=True)
            newest_added = watchdog.last_commit_time(self.shallow, "_posts", added_only=True)
            newest = watchdog.last_commit_time(self.shallow, "_posts")
        self.assertIsNone(added)                      # 빈 목록([])이 아니라 '알 수 없음'
        self.assertIsNone(newest_added)
        self.assertIsNone(newest)
        self.assertIn("::warning::얕은 복제", buf.getvalue())
        self.assertIn("fetch-depth: 0", buf.getvalue())
        self.assertTrue(all(ln.startswith("::warning::") for ln in buf.getvalue().splitlines()))

    def test_the_full_repository_still_counts_the_post_commit(self):
        added = watchdog.commit_times(self.source, "_posts", added_only=True)
        self.assertEqual(len(added), 1)               # 글을 추가한 커밋 하나(맨 위의 글 아닌 커밋은 세지 않는다)
        self.assertEqual(int(added[0].timestamp()), int(self.post_time.timestamp()))

    def test_not_a_git_repo_is_an_empty_list_not_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(watchdog.commit_times(tmp, "_posts"), [])

    def test_the_watchdog_workflow_checks_out_the_full_history(self):
        """얕은 복제에서는 git 기반 판정을 건너뛰고 경고만 남기므로, 워크플로가 전체 이력을 받아 오는 것이 전제다."""
        self.assertIn("fetch-depth: 0", (WORKFLOW_DIR / "watchdog.yml").read_text(encoding="utf-8"))

    def test_head_commit_of_a_shallow_clone_is_not_mistaken_for_a_new_post(self):
        full_findings, _, _ = collect(self.source, self.now)
        self.assertEqual(summarize(full_findings), [("STALE", "critical")])        # 대조군: 전체 이력
        findings, stats, out = collect(self.shallow, self.now)
        # 얕은 복제에서 HEAD(1시간 전, 글 아님)를 새 글로 세면 STALE 이 가려진다. 이력 파일로 같은 판단을 해야 한다.
        self.assertEqual(summarize(findings), [("STALE", "critical")])
        self.assertEqual(stats[0]["posts_7d"], 1)                                   # 이력 파일 기준 현황
        self.assertEqual(stats[0]["last_post"], self.post_time)
        self.assertIn("::warning::얕은 복제", out)

    def test_a_shallow_clone_still_reports_a_failed_deploy(self):
        """글 커밋 시각이 필요한 배포 확인만 건너뛴다. 최근 배포 실패(PAGES_FAILED)는 git 과 무관하므로 계속 본다."""
        gh = FakeGitHub(runs={"pages.yml": [run_record("failure", self.now - timedelta(hours=1))]})
        findings, _, _ = collect(self.shallow, self.now, gh)
        self.assertEqual(sorted(summarize(findings)), [("PAGES_FAILED", "warning"), ("STALE", "critical")])


if __name__ == "__main__":
    unittest.main()
