"""승인 흐름(publish_flow: pr)을 켜기 전 AI 후속(R2, 2026-11-09)의 재현 시험 — 작업 내용 §3 24번이 적은 후속 중 다섯 가지.

① 초안 PR 알림 중복 방지(항목 id 통일) ② 건강 경고 DRAFT_WAITING 이 STALE 을 가리지 않게 ④ 초안 생성 직후 확인 필요 모음 즉시 실행과 텔레그램 발행 대기 알림
⑤ 초안 라벨 한 곳 ⑥ 승인 흐름에서 새 글 알림이 안 도는 점(경로별 알림 표).
각 절은 '고치기 전에 빨강이던 시험'(재현)과 '꺼진 상태(direct·초안 PR 없음)에서 출력이 예전과 같음'을 못박는 시험을 함께 둔다. 네트워크·실제 시크릿을 쓰지 않는다.
맨 아래 'R2 수정' 절은 독립 검증(2026-11-09)이 지적한 P1(라벨 붙이기 실패의 무음 누락·거짓 성공 문구와 정리 단계의 라벨 재부착)·P2(3일 넘은 초안 PR 의 재알림)·
P3(공용 `초안` 라벨 설명)·P4(72시간 경계의 말과 시각을 모를 때의 문구)를 같은 방식으로 재현하고 못박는다.
"""
import contextlib
import hashlib
import io
import itertools
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import _bootstrap
import ops_inbox_helpers as h
import ops_inbox as oi
from notify_helpers import ENV as TELEGRAM_ENV, FakeNet
from pipeline import draft_flow, draft_labels, health, inbox, notify
from pipeline import drafts as drafts_mod            # 시험 안의 지역 변수 이름 drafts(목록)와 겹치지 않게 별칭을 쓴다
from pipeline.console import one_line
from test_notify_integration import patched_network
from draft_helpers import REPO as REAL_REPO
from watchdog_helpers import FakeGitHub as WatchdogGitHub, canned_commit_times, iso_z, run_record

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402

NOW, URL, ago = h.NOW, h.REPO_URL, h.ago
OPS_ENV = {"GITHUB_REPOSITORY": h.REPO, "GITHUB_TOKEN": "gh" + "s_" + "Q" * 36, "GITHUB_REPOSITORY_OWNER": "octo"}


def snap(**kw):
    base = dict(now=NOW, repo=h.REPO)
    base.update(kw)
    return inbox.Snapshot(**base)


def pr_draft(number=15, **kw):
    kw.setdefault("hours", 3)
    return h.make_draft(number, "[초안][Chance] 승인 대기 글", "Chance", pull=True, **kw)


# 열린 PR 규칙이 읽는 PR 상태 아홉 가지(검사·병합 상태의 모든 조합)
PULL_STATES = {
    "ready": lambda n=15: h.make_pull(n),
    "conflict": lambda n=15: h.make_pull(n, mergeable=False, state="dirty"),
    "ci_fail": lambda n=15: h.make_pull(n, ci="fail"),
    "no_ci": lambda n=15: h.make_pull(n, ci="none"),
    "pending": lambda n=15: h.make_pull(n, ci="pending"),
    "unknown": lambda n=15: h.make_pull(n, ci="unknown"),
    "blocked": lambda n=15: h.make_pull(n, state="blocked"),
    "calculating": lambda n=15: h.make_pull(n, mergeable=None),
    "error": lambda n=15: dict(h.make_pull(n), error="HTTP 500"),
}


# ----------------------------------------------------------------------------
# ① 초안 PR 알림 중복 방지 — 항목 id 통일
# ----------------------------------------------------------------------------
class UnifiedDraftPullIdTest(unittest.TestCase):
    def announcements(self, snapshots):
        """점검을 차례로 돌렸을 때 '새로 알릴 action' 의 총 수(알림 = 코멘트 한 개 + 텔레그램 한 통)."""
        previous, total = None, 0
        for snapshot in snapshots:
            items = inbox.build_items(snapshot)
            new, kept = inbox.plan_notice(items, previous, snapshot.failures)
            total += len(new)
            previous = kept
        return total

    def test_the_same_draft_pull_request_is_announced_once_however_its_state_flaps(self):
        """재현(R2-1): 병합 가능 여부가 계산 중으로 돌아오거나 검사 결과가 오가는 것만으로 같은 초안이 새 id 가 되어 알림이 되풀이됐다."""
        drafts = [pr_draft()]
        order = ("no_ci", "ready", "calculating", "ready", "pending", "conflict", "no_ci", "ci_fail", "unknown", "ready")
        snapshots = [snap(pulls=[PULL_STATES[name]()], drafts=drafts) for name in order]
        self.assertEqual(self.announcements(snapshots), 1)

    def test_a_failed_pull_lookup_in_between_is_not_a_new_announcement_either(self):
        drafts = [pr_draft()]
        snapshots = [snap(pulls=[PULL_STATES["ready"]()], drafts=drafts),
                     snap(pulls=[], drafts=drafts, failures=[("pulls", "HTTP 500")]),
                     snap(pulls=[], drafts=drafts, failures=[("pull_details", "HTTP 500")]),
                     snap(pulls=[PULL_STATES["ready"]()], drafts=drafts)]
        self.assertEqual(self.announcements(snapshots), 1)

    def test_every_pull_state_gives_exactly_one_line_with_the_draft_id(self):
        for name, make in PULL_STATES.items():
            with self.subTest(state=name):
                items = [i for i in inbox.build_items(snap(pulls=[make()], drafts=[pr_draft()])) if "15" in i.id]
                self.assertEqual([(i.id, i.level) for i in items], [("draft:15:wait", "action")])

    def test_a_stale_draft_pull_request_is_one_check_line_in_every_state(self):
        for name, make in PULL_STATES.items():
            with self.subTest(state=name):
                items = [i for i in inbox.build_items(snap(pulls=[make()], drafts=[pr_draft(hours=100)])) if "15" in i.id]
                self.assertEqual([(i.id, i.level) for i in items], [("draft:15:stale", "check")])

    def test_conflicts_and_failed_checks_are_told_in_the_text_and_never_in_the_id(self):
        quiet, = [i for i in inbox.build_items(snap(pulls=[PULL_STATES["no_ci"]()], drafts=[pr_draft()])) if i.id.startswith("draft:")]
        self.assertEqual(quiet.detail, "채널 Chance · PR #15 · 검토·병합을 기다립니다")
        for name, phrase in (("conflict", "충돌"), ("ci_fail", "자동 검사가 실패")):
            with self.subTest(state=name):
                item, = [i for i in inbox.build_items(snap(pulls=[PULL_STATES[name]()], drafts=[pr_draft()])) if i.id.startswith("draft:")]
                self.assertEqual(item.id, "draft:15:wait")
                self.assertTrue(item.detail.startswith(quiet.detail + " · "), item.detail)
                self.assertIn(phrase, item.detail)
                self.assertEqual(item.title, quiet.title)
        for name in ("ready", "pending", "unknown", "blocked", "calculating", "error"):
            with self.subTest(state=name):
                item, = [i for i in inbox.build_items(snap(pulls=[PULL_STATES[name]()], drafts=[pr_draft()])) if i.id.startswith("draft:")]
                self.assertEqual(item.detail, quiet.detail)          # 사람이 손댈 일이 아닌 상태는 설명을 바꾸지 않는다

    def test_the_text_changes_the_body_but_never_the_announced_ids(self):
        before = inbox.build_items(snap(pulls=[PULL_STATES["no_ci"]()], drafts=[pr_draft()]))
        after = inbox.build_items(snap(pulls=[PULL_STATES["conflict"]()], drafts=[pr_draft()]))
        self.assertNotEqual(inbox.render(before, URL), inbox.render(after, URL))          # 본문(설명)은 바뀐다 — 본문 수정은 알림이 없다
        self.assertEqual(inbox.action_ids(before), inbox.action_ids(after))

    def test_pull_requests_that_are_not_drafts_keep_their_state_ids(self):
        read_as = {"calculating": "unknown", "error": "unknown"}               # 병합 가능 여부 계산 중·상세 조회 실패는 열린 PR 규칙이 '상태 확인 중'으로 읽는다
        for name, make in PULL_STATES.items():
            with self.subTest(state=name):
                items = inbox.build_items(snap(pulls=[make()], drafts=[]))
                self.assertEqual([i.id for i in items if i.id.startswith(("pr:", "draft:"))], [f"pr:15:{read_as.get(name, name)}"])

    def test_only_the_draft_pull_requests_own_line_is_dropped(self):
        pulls = [PULL_STATES["no_ci"](15), PULL_STATES["no_ci"](16), PULL_STATES["ready"](17), PULL_STATES["conflict"](18)]
        ids = {i.id for i in inbox.build_items(snap(pulls=pulls, drafts=[pr_draft(15), pr_draft(18)]))}
        self.assertEqual({i for i in ids if i[:3] in ("pr:", "dra")}, {"draft:15:wait", "draft:18:wait", "pr:16:no_ci", "pr:17:ready"})

    def test_an_issue_draft_with_the_same_number_never_hides_a_pull_line(self):
        ids = {i.id for i in inbox.build_items(snap(pulls=[PULL_STATES["ready"]()], drafts=[h.make_draft(15)]))}
        self.assertEqual({i for i in ids if i[:3] in ("pr:", "dra")}, {"pr:15:ready", "draft:15:wait"})

    def test_issue_drafts_and_draft_pull_requests_without_a_pull_entry_are_unchanged(self):
        drafts = [h.make_draft(41, hours=30), h.make_draft(43, "[초안][네이버] 오래된 글", "네이버", hours=100), pr_draft(15), pr_draft(16, hours=100)]
        items = inbox.draft_items(drafts, NOW, URL)
        self.assertEqual([(i.id, i.level) for i in items], [("draft:15:wait", "action"), ("draft:16:stale", "check"), ("draft:41:wait", "action"), ("draft:43:stale", "check")])
        self.assertEqual(inbox.draft_items(drafts, NOW, URL), inbox.draft_items(drafts, NOW, URL, {}))
        self.assertEqual(inbox.draft_items(drafts, NOW, URL), inbox.draft_items(drafts, NOW, URL, pull_states=None))
        self.assertEqual(inbox.draft_items(drafts, NOW, URL), inbox.draft_items(drafts, NOW, URL, ()))       # 예전 호출 모양(네 번째 자리에 빈 값)도 같은 결과

    def test_a_state_for_an_issue_draft_is_ignored(self):
        item, = inbox.draft_items([h.make_draft(15)], NOW, URL, {15: "conflict"})
        self.assertEqual(item.detail, "채널 티스토리 · 이슈 #15 · 발행을 기다립니다")


# ----------------------------------------------------------------------------
# ① 전체 실행(가짜 GitHub·가짜 텔레그램): 상태가 오가는 세 번의 점검이 코멘트 한 개·텔레그램 한 통
# ----------------------------------------------------------------------------
def registry_text(flow="pr"):
    reg = json.loads(h.CHANNEL_REGISTRY)
    reg["blogs"][0]["publish_flow"] = flow
    return json.dumps(reg, ensure_ascii=False)


class FlappingRunTest(unittest.TestCase):
    def setUp(self):
        notify.reset_budget()
        self.addCleanup(notify.reset_budget)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.out = []

    def world(self):
        root = h.make_root(self.tmp / "repo", histories={"history.json": [], "blogger_history.json": []}, blogs_json=registry_text())
        fake = h.FakeGitHub()
        fake.runs = {name: [h.make_run(i, h.ago(hours=1 + i))] for i, name in enumerate(("chanceblog.yml", "blogger.yml", "watchdog.yml", "guardrails.yml"), start=1)}
        title = "[초안][Chance] 승인 대기 글 / Waiting post"
        fake.issues.append(h.make_issue(15, title, labels=["초안", "채널:Chance"], created=h.ago(hours=3), pull=True))
        fake.pulls = [h.make_pull_raw(15, title=title, sha="c" * 40, login=h.BOT, user_type="Bot", assoc="CONTRIBUTOR")]
        return fake, root

    def check(self, fake, root, net, detail, checks):
        fake.details = {15: detail}
        fake.check_runs = {"c" * 40: checks}
        environ = dict(OPS_ENV, GITHUB_STEP_SUMMARY=str(self.tmp / "summary.md"), **TELEGRAM_ENV)
        with patched_network(net):
            return oi.run(environ, fake, h.NOW, root, self.out.append, sleep=lambda seconds: None)

    def test_three_checks_with_a_changing_pull_state_send_one_comment_and_one_phone_message(self):
        """재현(R2-1): 검사 없음 → 검사 통과 → 병합 가능 여부 계산 중, 세 번의 점검에서 코멘트와 텔레그램이 세 번씩 갔다."""
        fake, root = self.world()
        net = FakeNet()
        clean = {"mergeable": True, "mergeable_state": "clean"}
        steps = ((clean, []), (clean, [h.make_check("validate")]), ({"mergeable": None, "mergeable_state": "unknown"}, [h.make_check("validate")]),
                 (clean, [h.make_check("validate")]))
        for detail, checks in steps:
            self.assertEqual(self.check(fake, root, net, detail, checks), 0)
        number = next(i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE)["number"]
        self.assertEqual(len(fake.comments[number]), 1)
        self.assertEqual(net.calls, 1)
        body = next(i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE)["body"]
        self.assertEqual(inbox.parse_marker(body).items, ("draft:15:wait",))


# ----------------------------------------------------------------------------
# ② 건강 경고 DRAFT_WAITING 이 STALE 을 가리지 않게
# ----------------------------------------------------------------------------
HEALTH_NOW = datetime(2026, 10, 28, 3, 0, tzinfo=timezone.utc)                 # KST 12시
PR_BLOG = {"key": "chance", "platform": "jekyll-git", "mode": "auto", "publish_flow": "pr",
           "state": {"history": "history.json", "content_dir": "_posts"}, "workflow": ".github/workflows/chanceblog.yml",
           "health": {"max_gap_hours": 36, "max_failure_streak": 3}}
DIRECT_BLOG = {**PR_BLOG, "publish_flow": "direct"}
LEGACY_BLOG = {k: v for k, v in PR_BLOG.items() if k != "publish_flow"}


def waiting(*hours_ago):
    return [{"number": 40 + i, "created_at": iso_z(HEALTH_NOW - timedelta(hours=hours))} for i, hours in enumerate(hours_ago)]


def pairs(findings):
    return sorted((f.code, f.severity) for f in findings)


class DraftWaitingKeepsStaleTest(unittest.TestCase):
    STALE_COMMIT = HEALTH_NOW - timedelta(hours=80)                           # 마지막 활동 80시간 전(허용 36시간) → STALE

    def evaluate(self, drafts, blog=PR_BLOG, commit=STALE_COMMIT, **kw):
        return health.evaluate(blog, [], HEALTH_NOW, last_content_commit=commit, pending_drafts=drafts, **kw)

    def test_a_draft_left_for_days_with_nothing_new_since_keeps_a_stale_warning_next_to_the_waiting_one(self):
        """재현(R2-2): 초안이 3일 넘게 열려 있고 그 뒤 새 초안·병합이 하나도 없으면 STALE 이 DRAFT_WAITING 에 통째로 가려졌다."""
        findings = self.evaluate(waiting(100, 90))
        self.assertEqual(pairs(findings), [("DRAFT_WAITING", "warning"), ("STALE", "warning")])

    def test_the_boundary_is_three_days_exactly(self):
        for hours, expected in ((71.9, ["DRAFT_WAITING"]), (72, ["DRAFT_WAITING", "STALE"]), (72.1, ["DRAFT_WAITING", "STALE"]), (30, ["DRAFT_WAITING"])):
            with self.subTest(hours=hours):
                self.assertEqual(sorted(f.code for f in self.evaluate(waiting(hours))), expected)
        self.assertEqual(health.DRAFT_STALL_HOURS, 72)

    def test_the_oldest_draft_decides_not_the_newest(self):
        self.assertEqual(sorted(f.code for f in self.evaluate(waiting(5, 100))), ["DRAFT_WAITING", "STALE"])
        self.assertEqual(sorted(f.code for f in self.evaluate(waiting(100, 5))), ["DRAFT_WAITING", "STALE"])

    def test_the_kept_stale_is_a_warning_titled_like_the_old_one_and_says_why_it_stays(self):
        findings = self.evaluate(waiting(100))
        stale = next(f for f in findings if f.code == "STALE")
        old = next(f for f in health.evaluate(PR_BLOG, [], HEALTH_NOW, last_content_commit=self.STALE_COMMIT) if f.code == "STALE")
        self.assertEqual((stale.blog, stale.severity, stale.title), ("chance", "warning", "[Watchdog] chance: STALE"))
        self.assertEqual(old.severity, "critical")                                   # 대조: 초안이 없으면 예전처럼 심각
        self.assertTrue(stale.message.startswith(old.message))                       # 마지막 활동 시각·경과·허용 시간은 그대로
        self.assertIn("3일 넘게 대기 중", stale.message)
        self.assertIn("워크플로 실행을 확인하세요", stale.message)

    def test_a_listing_without_readable_times_cannot_prove_the_drafts_are_fresh_so_stale_stays(self):
        for drafts in ([{"number": 1}], [{"number": 1, "created_at": "엉터리"}], ["문자열"]):
            with self.subTest(drafts=drafts):
                self.assertEqual(sorted(f.code for f in self.evaluate(drafts)), ["DRAFT_WAITING", "STALE"])

    def test_no_posts_day_alone_is_still_swallowed_by_waiting_whatever_the_age(self):
        days = {(HEALTH_NOW - timedelta(days=5)).date()}                           # 어제·그제 글 없음 → NO_POSTS_DAY(심각), 최근 활동은 있어 STALE 은 없다
        recent = HEALTH_NOW - timedelta(hours=30)
        for drafts in (waiting(5), waiting(200)):
            with self.subTest(drafts=drafts):
                findings = health.evaluate(PR_BLOG, [], HEALTH_NOW, last_content_commit=recent, post_days=days, pending_drafts=drafts)
                self.assertEqual(pairs(findings), [("DRAFT_WAITING", "warning")])

    def test_both_triggers_with_old_drafts_leave_waiting_and_the_stale_warning_only(self):
        days = {(HEALTH_NOW - timedelta(days=5)).date()}
        findings = health.evaluate(PR_BLOG, [], HEALTH_NOW, last_content_commit=self.STALE_COMMIT, post_days=days, pending_drafts=waiting(100))
        self.assertEqual(pairs(findings), [("DRAFT_WAITING", "warning"), ("STALE", "warning")])         # NO_POSTS_DAY 는 예전처럼 STALE 이 있으면 따로 안 울린다

    def test_nothing_changes_without_stale_or_without_the_approval_flow_or_without_pending_drafts(self):
        recent = HEALTH_NOW - timedelta(hours=5)
        self.assertEqual(self.evaluate(waiting(100), commit=recent), [])                                       # 최근 활동이 있으면 아무것도 없다
        for blog in (DIRECT_BLOG, LEGACY_BLOG):
            self.assertEqual(pairs(self.evaluate(waiting(100), blog=blog)), [("STALE", "critical")])           # 직접 게시는 초안 목록을 무시한다
        for drafts in (None, []):
            self.assertEqual(pairs(self.evaluate(drafts)), [("STALE", "critical")])                            # 초안이 없거나 목록을 못 읽으면 예전처럼 심각
        self.assertEqual(health.evaluate({**PR_BLOG, "mode": "off"}, [], HEALTH_NOW, pending_drafts=waiting(100)), [])

    def test_unrelated_findings_are_kept_next_to_both(self):
        findings = self.evaluate(waiting(100), recent_runs=[{"conclusion": "failure"}] * 3)
        self.assertEqual(sorted(f.code for f in findings), ["DRAFT_WAITING", "RUN_FAIL_STREAK", "STALE"])

    def test_the_hour_count_equals_the_inbox_three_day_rule(self):
        """이 모듈은 순수 함수라 inbox 를 가져오지 않는다 — '3일'이 두 곳에서 같은 값이어야 한다."""
        self.assertEqual(health.DRAFT_STALL_HOURS, inbox.DRAFT_STALE_DAYS * 24)


class WatchdogKeepsStaleTest(unittest.TestCase):
    """워치독 전체(scripts/watchdog.py collect + sync_issues): 경고 둘이 이슈 둘이 되고 실행은 초록이며, 이미 열린 심각 STALE 이슈는 닫히지 않고 경고로 갱신된다."""

    class Github(WatchdogGitHub):
        def __init__(self, drafts, **kw):
            kw.setdefault("runs", {"pages.yml": [run_record("success", HEALTH_NOW - timedelta(hours=80) + timedelta(minutes=2))]})
            super().__init__(**kw)
            self.drafts = drafts

        def list_open_draft_pulls(self):
            self.calls.append(("draft-pulls",))
            return list(self.drafts)

    def collect(self, client):
        reg = {"blogs": [json.loads(json.dumps(PR_BLOG))], "defaults": {}}
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "history.json").write_text("[]", encoding="utf-8")
            with mock.patch.object(watchdog, "commit_times", canned_commit_times([HEALTH_NOW - timedelta(hours=80)])), contextlib.redirect_stdout(io.StringIO()):
                return watchdog.collect(reg, Path(tmp), HEALTH_NOW, client)

    def test_old_drafts_open_two_warning_issues_and_the_run_stays_green(self):
        client = self.Github(waiting(100))
        findings, stats = self.collect(client)
        self.assertEqual(pairs(findings), [("DRAFT_WAITING", "warning"), ("STALE", "warning")])
        self.assertEqual(sorted(stats[0]["codes"]), ["DRAFT_WAITING", "STALE"])
        gh = WatchdogGitHub(now=HEALTH_NOW)
        created, closed, _, new_critical = watchdog.sync_issues(findings, [], gh, owner="octo", now=HEALTH_NOW, out=lambda text: None)
        self.assertEqual((sorted(created), closed, new_critical), (["[Watchdog] chance: DRAFT_WAITING", "[Watchdog] chance: STALE"], [], []))

    def test_an_open_critical_stale_issue_is_updated_to_a_warning_not_closed(self):
        findings, _ = self.collect(self.Github(waiting(100)))
        gh = WatchdogGitHub(now=HEALTH_NOW)
        old = health.Finding("chance", "STALE", "critical", "옛 문구")
        number = gh.add_issue(old.title, watchdog.issue_body(old, "octo"))
        created, closed, renotified, new_critical = watchdog.sync_issues(findings, gh.list_open_issues(), gh, owner="octo", now=HEALTH_NOW, out=lambda text: None)
        self.assertEqual((created, closed, renotified, new_critical), (["[Watchdog] chance: DRAFT_WAITING"], [], [], []))
        self.assertEqual(gh.issues[number]["state"], "open")
        self.assertIn("심각도**: warning", gh.issues[number]["body"])


def health_grid():
    """초안 PR 이 없거나 어려서 '예전과 같아야 하는' 입력들의 격자(수정 전 코드에서 같은 지문이 나온다). 오래된 초안 + STALE 칸(바뀌는 곳)은 not_changed_region 이 뺀다."""
    blogs = (PR_BLOG, DIRECT_BLOG, LEGACY_BLOG, {**PR_BLOG, "mode": "off"}, {**PR_BLOG, "mode": "draft"}, {**PR_BLOG, "health": {"max_gap_hours": 120}})
    commits = (None, HEALTH_NOW - timedelta(hours=5), HEALTH_NOW - timedelta(hours=40), HEALTH_NOW - timedelta(hours=80), HEALTH_NOW - timedelta(days=9))
    drafts = (None, [], waiting(3), waiting(30, 5), waiting(71), waiting(71.5, 2, 40), waiting(100), waiting(100, 5), [{"number": 1}])
    days = (None, {(HEALTH_NOW - timedelta(days=5)).date()}, {(HEALTH_NOW - timedelta(days=2)).date()}, {HEALTH_NOW.astimezone(timezone(timedelta(hours=9))).date()})
    runs = ((), [{"conclusion": "failure"}] * 3)
    return list(itertools.product(blogs, commits, drafts, days, runs))


def health_digest(include):
    """include(blog, commit, pending) 가 참인 격자 칸의 evaluate 결과 지문과 칸 수."""
    parts = []
    for blog, commit, pending, day_set, recent in health_grid():
        if not include(blog, commit, pending):
            continue
        found = health.evaluate(blog, [], HEALTH_NOW, last_content_commit=commit, post_days=day_set, recent_runs=recent, pending_drafts=pending)
        parts.append(json.dumps([[f.blog, f.code, f.severity, f.message] for f in found], ensure_ascii=False))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest(), len(parts)


def not_changed_region(blog, commit, pending):
    """바뀌는 칸 = 승인 흐름 + 열린 초안이 72시간 이상(또는 시각 모름) + 마지막 활동이 허용 시간보다 오래된(STALE) 칸. 그 밖은 모두 같아야 한다."""
    if blog.get("publish_flow") != "pr" or not isinstance(pending, list) or not pending:
        return True
    times = [health._parse_utc(d.get("created_at")) if isinstance(d, dict) else None for d in pending]
    old_or_unknown = None in times or max(HEALTH_NOW - t for t in times) >= timedelta(hours=72)        # 하나라도 시각을 못 읽으면 오래됐는지 모른다(R2 수정 P4)
    gap = blog.get("health", {}).get("max_gap_hours", 48)
    stale = commit is not None and (HEALTH_NOW - commit) > timedelta(hours=gap)        # 마지막 활동 기록이 없으면 STALE 이 아니라 NO_ACTIVITY 다
    return not (old_or_unknown and stale)


HEALTH_OFF_DIGEST = ("9759b2d1e965de29aae507df9fd75adffb42ed0951312d2474d648ed01b93d81", 1920)


class HealthOffStateUnchangedTest(unittest.TestCase):
    def test_everywhere_the_new_rule_does_not_apply_the_findings_are_byte_for_byte_what_they_were(self):
        """꺼진 상태(직접 게시·초안 없음·젊은 초안·STALE 없음)의 출력은 수정 전(origin/main 611b2d2)과 같다 — 같은 입력 격자의 지문으로 확인한다."""
        self.assertEqual(health_digest(not_changed_region), HEALTH_OFF_DIGEST)


# ----------------------------------------------------------------------------
# ⑤ 초안 라벨 한 곳 — 이름·색·설명
# ----------------------------------------------------------------------------
def made_by_chance_pr():
    """Chance 승인 PR 이 라벨을 만들 때(draft_flow.attach_labels) 보내는 값 {이름: (색, 설명)}."""
    from draft_helpers import FakeGitHub as DraftGitHub
    from pipeline import draft_flow
    client = DraftGitHub()
    client.add_pr(41, "ai/draft/2026-10-28-s9")
    draft_flow.attach_labels(client, 41, lambda text: None)
    return dict(client.labels)


def made_by_package_issues():
    """티스토리·네이버 초안 이슈 어댑터가 라벨을 만들 때 보내는 값."""
    from test_issue_package import make_draft as package_draft, publisher
    made = {}
    for platform in ("tistory", "naver"):
        pub, github, _ = publisher()
        pub.publish_package(package_draft(platform))
        made.update({name: (payload["color"], payload["description"]) for name, payload in github.labels.items()})
    return made


def made_by_the_inbox():
    """확인 필요 모음이 라벨을 만들 때(ops_inbox.ensure_draft_labels) 보내는 값(레지스트리 채널 전부 + 초안·폐기)."""
    fake = h.FakeGitHub()
    blogs = [h.channel_blog(f"{key}_x", label, platform) for key, label, platform in
             (("chance", "Chance", "jekyll-git"), ("blogger_en", "Blogger 영문", "blogger"), ("blogger_ko", "Blogger 한글", "blogger"),
              ("tistory", "티스토리", "tistory"), ("naver", "네이버", "naver"))]
    oi.ensure_draft_labels(fake, inbox.draft_label_specs(blogs), lambda text: None)
    return {name: (payload["color"], payload["description"]) for name, payload in fake.label_payloads.items()}


class OneLabelTableTest(unittest.TestCase):
    def test_the_same_label_gets_the_same_colour_and_description_whoever_creates_it(self):
        """재현(R2-5): 같은 이름의 라벨(`초안` 등)을 만드는 세 곳이 서로 다른 색·설명을 보내서 먼저 도는 쪽의 것이 남았다."""
        sources = {"Chance PR": made_by_chance_pr(), "초안 이슈": made_by_package_issues(), "확인 필요 모음": made_by_the_inbox()}
        names = {name for made in sources.values() for name in made}
        shared = 0
        for name in sorted(names):
            seen = {source: made[name] for source, made in sources.items() if name in made}
            if len(seen) > 1:
                shared += 1
                self.assertEqual(len(set(seen.values())), 1, f"{name} 라벨이 곳마다 다르다: {seen}")
        self.assertGreaterEqual(shared, 4)                       # 초안·채널:Chance·채널:티스토리·채널:네이버가 둘 이상의 곳에서 만들어진다

    def test_every_label_the_three_places_create_has_the_names_colours_and_descriptions_of_the_table(self):
        from pipeline import draft_labels
        chance, package, board = made_by_chance_pr(), made_by_package_issues(), made_by_the_inbox()
        for made in (chance, package, board):
            for name, (color, description) in made.items():
                self.assertEqual((color, description), draft_labels.style_of(name), name)

    def test_the_three_modules_read_the_table_instead_of_keeping_their_own_values(self):
        from pipeline import draft_labels, drafts
        from pipeline.publishers import issue_package
        self.assertEqual(drafts.LABELS, draft_labels.specs_for(["Chance"]))
        self.assertEqual(drafts.LABELS, ((draft_labels.DRAFT_LABEL, draft_labels.DRAFT_COLOR, draft_labels.BASE_LABELS[0][2]),
                                         ("채널:Chance", draft_labels.CHANNEL_COLOR, "초안이 속한 채널: Chance")))
        self.assertIs(inbox.DRAFT_LABEL_SPECS, draft_labels.BASE_LABELS)
        self.assertEqual(inbox.CHANNEL_LABEL_COLOR, draft_labels.CHANNEL_COLOR)
        self.assertEqual(inbox.LABEL_NAME_MAX, draft_labels.LABEL_NAME_MAX)
        self.assertEqual((issue_package.DRAFT_LABEL, issue_package.DISCARD_LABEL, issue_package.CHANNEL_LABEL_PREFIX),
                         (draft_labels.DRAFT_LABEL, draft_labels.DISCARD_LABEL, draft_labels.CHANNEL_LABEL_PREFIX))
        self.assertEqual((drafts.LABEL_DRAFT, drafts.LABEL_CHANNEL), ("초안", "채널:Chance"))
        self.assertEqual(drafts.PR_TITLE_PREFIX, "[초안][Chance]")

    def test_the_table_values_are_valid_for_github_and_in_plain_words(self):
        from pipeline import draft_labels
        specs = list(draft_labels.BASE_LABELS) + [draft_labels.channel_spec(label) for label in ("Chance", "Blogger 영문", "Blogger 한글", "티스토리", "네이버")]
        self.assertEqual(len({name.casefold() for name, _c, _d in specs}), len(specs))
        for name, color, description in specs:
            with self.subTest(label=name):
                self.assertRegex(color, r"^[0-9a-f]{6}$")
                self.assertLessEqual(len(name), draft_labels.LABEL_NAME_MAX)
                self.assertTrue(0 < len(description) <= draft_labels.DESCRIPTION_MAX)
                for jargon in ("확인 필요 모음", "초안 현황", "pipeline", "라벨 `", "::", "@", "<"):         # 운영자가 휴대폰에서 읽는 말에 내부 이름·표시 문자를 쓰지 않는다
                    self.assertNotIn(jargon, description)
        self.assertEqual(len({color for _n, color, _d in draft_labels.BASE_LABELS} | {draft_labels.CHANNEL_COLOR}), 3)       # 초안·폐기·채널 색은 서로 구분된다

    def test_every_registry_channel_label_has_a_table_row_so_a_new_channel_fails_here_first(self):
        from pipeline import draft_labels, registry
        for label in registry.CHANNEL_LABELS:
            name, color, description = draft_labels.channel_spec(label)
            self.assertEqual((name, draft_labels.style_of(name)), (f"채널:{label}", (color, description)))

    def test_style_of_knows_only_the_base_and_channel_labels(self):
        from pipeline import draft_labels
        for unknown in ("bug", "채널:", "채널:   ", "", None, 7, "초안 ", "폐기됨"):
            with self.subTest(name=unknown):
                self.assertIsNone(draft_labels.style_of(unknown))
        self.assertEqual(draft_labels.style_of("초안")[0], draft_labels.DRAFT_COLOR)
        self.assertEqual(draft_labels.style_of("폐기")[0], draft_labels.DISCARD_COLOR)
        self.assertEqual(draft_labels.style_of("채널:아무개"), (draft_labels.CHANNEL_COLOR, "초안이 속한 채널: 아무개"))

    def test_specs_for_lists_the_draft_label_and_one_row_per_distinct_channel(self):
        from pipeline import draft_labels
        names = [name for name, _c, _d in draft_labels.specs_for(["티스토리", "Chance", "티스토리", "chance"])]
        self.assertEqual(names, ["초안", "채널:티스토리", "채널:Chance"])                       # 폐기는 운영자가 붙이는 라벨이라 만드는 쪽 묶음에 없다
        self.assertEqual([name for name, _c, _d in draft_labels.specs_for([])], ["초안"])

    def test_a_long_channel_label_description_is_cut_to_the_github_limit(self):
        from pipeline import draft_labels
        name, _color, description = draft_labels.channel_spec("가" * 300)
        self.assertEqual(len(description), draft_labels.DESCRIPTION_MAX)

    def test_the_pull_request_table_in_the_architecture_guide_has_the_table_colours(self):
        from pipeline import draft_labels
        text = (_bootstrap.ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| 라벨 | `초안`(색"))
        self.assertIn(f"`초안`(색 `{draft_labels.DRAFT_COLOR}`)", row)
        self.assertIn(f"`채널:Chance`(색 `{draft_labels.CHANNEL_COLOR}`)", row)
        self.assertIn("pipeline/draft_labels.py", row)

    def test_the_board_guide_names_the_one_place_and_no_longer_asks_for_the_unification(self):
        text = (_bootstrap.ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
        self.assertIn("pipeline/draft_labels.py", text)
        self.assertNotIn("켜기 전에 한 곳(`pipeline/inbox.py`의 `DRAFT_LABEL_SPECS`)으로 통일하면 좋습니다", text)


def label_digest():
    """꺼진 상태(Chance 직접 게시, 초안 PR 없음)에서 확인 필요 모음이 라벨을 만드는 길 — 만드는 라벨 이름·색·호출 순서. 수정 전 코드에서 같은 값이 나온다(설명 글은 R2-5 가 쉬운 말로 바꿨으니 뺀다)."""
    fake = h.FakeGitHub()
    blogs = [h.channel_blog(f"{key}_x", label, platform) for key, label, platform in
             (("chance", "Chance", "jekyll-git"), ("blogger_en", "Blogger 영문", "blogger"), ("tistory", "티스토리", "tistory"), ("naver", "네이버", "naver"))]
    out = []
    oi.ensure_draft_labels(fake, inbox.draft_label_specs(blogs), out.append)
    fake.labels = {"초안"}
    oi.ensure_draft_labels(fake, inbox.draft_label_specs(blogs), out.append)               # 이미 있는 이름은 건드리지 않는다
    parts = {"specs": [[spec["name"], spec["color"], len(spec["description"]) > 0] for spec in inbox.draft_label_specs(blogs)],
             "log": [[entry[0], entry[1], sorted(k for k in (entry[2] or {}) if k != "description") if isinstance(entry[2], dict) else entry[2]] for entry in fake.log],
             "created": {name: payload["color"] for name, payload in fake.label_payloads.items()},
             "out": [line.split("(")[0] for line in out]}
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


LABEL_OFF_DIGEST = "4005877325904d70da68007adf10175dd3864168a95ee093a763b983b496947d"


class LabelOffStateUnchangedTest(unittest.TestCase):
    def test_the_inbox_creates_the_same_labels_in_the_same_order_with_the_same_colours_as_before(self):
        self.assertEqual(label_digest(), LABEL_OFF_DIGEST)


# ----------------------------------------------------------------------------
# ④ 초안 생성 직후 확인 필요 모음 즉시 실행 + 텔레그램 '발행 대기' 알림
# ----------------------------------------------------------------------------
class DispatchBase(unittest.TestCase):
    """가짜 git·가짜 GitHub 로 draft_flow.run 을 돌린다(test_draft_flow 와 같은 도구)."""

    def setUp(self):
        from draft_helpers import FakeGit, FakeGitHub as DraftGitHub
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "history.json").write_bytes(b"[]\n")
        self.git, self.gh = FakeGit(self.root), DraftGitHub()
        self.out = []
        self.env = {"GITHUB_REPOSITORY": REAL_REPO, "GITHUB_REPOSITORY_OWNER": REAL_REPO.split("/")[0], "GITHUB_TOKEN": "ghs_" + "T" * 36}

    def draft(self, **kw):
        from draft_helpers import write_draft
        return write_draft(self.root, **kw)

    def run_it(self, env=None, flow="pr"):
        from pipeline import draft_flow, drafts
        with mock.patch.object(drafts, "chance_flow", return_value=flow):
            return draft_flow.run(self.env if env is None else env, git=self.git, client=self.gh, out=self.out.append, sleep=lambda seconds: None,
                                  now=datetime(2026, 10, 28, 9, 20, tzinfo=timezone(timedelta(hours=9))))

    def dispatches(self):
        return [call for call in self.gh.calls if call[0] == "dispatch"]


class InboxRefreshRightAfterTheDraftTest(DispatchBase):
    def test_a_new_draft_pull_request_asks_the_inbox_to_refresh_right_away(self):
        """재현(R2-4): 저장소 기본 토큰이 연 PR 은 확인 필요 모음을 이벤트로 시작시키지 못해 '초안 대기'가 정기 갱신(보통 3–6시간)에야 떴다."""
        self.draft()
        summary = self.root / "summary.md"
        self.assertEqual(self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)}), 0)
        self.assertEqual(self.dispatches(), [("dispatch", "ops-inbox.yml", "main")])
        self.assertIn("[초안] 확인 필요 모음을 바로 갱신하도록 요청했습니다", "\n".join(self.out))
        self.assertIn("- 확인 필요 모음: 바로 갱신하도록 요청했습니다", summary.read_text(encoding="utf-8"))

    def test_it_asks_only_after_the_pull_request_and_its_labels_exist(self):
        """모음은 라벨 `초안` 으로 초안 PR 을 알아본다 — 라벨이 붙기 전에 돌면 PR 이 초안으로 보이지 않는다."""
        self.draft()
        self.run_it()
        verbs = self.gh.verbs()
        self.assertLess(verbs.index("create"), verbs.index("add_labels"))
        self.assertLess(verbs.index("add_labels"), verbs.index("dispatch"))
        self.assertEqual(verbs.count("dispatch"), 1)

    def test_the_request_goes_to_the_branch_the_draft_was_made_on(self):
        from draft_helpers import FakeGit
        self.git = FakeGit(self.root, branch="release")
        self.draft()
        self.run_it()
        self.assertEqual(self.dispatches(), [("dispatch", "ops-inbox.yml", "release")])

    def test_a_refused_request_changes_neither_the_result_nor_the_exit_code(self):
        from pipeline import draft_flow, drafts
        for error in (drafts.GitHubError("HTTP 403: Resource not accessible by integration", 403), drafts.GitHubError("HTTP 404", 404),
                      drafts.GitHubError("HTTP 422: Workflow does not have 'workflow_dispatch' trigger", 422), drafts.GitHubError("URLError: 연결 실패")):
            with self.subTest(error=str(error)[:20]):
                self.setUp()
                self.gh.dispatch_error = error
                self.draft()
                summary = self.root / "summary.md"
                self.assertEqual(self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)}), 0)
                self.assertIn(draft_flow.WARN_INBOX, self.out)
                reason = self.out[self.out.index(draft_flow.WARN_INBOX) - 1]              # 경고 문장이 '이유는 로그의 바로 앞 줄에 있습니다'라고 말한다 — 정말 그 줄에 있다
                self.assertEqual(reason, f"[초안] 확인 필요 모음을 바로 갱신하도록 요청하지 못했습니다: {draft_flow.failure_detail(error)}")
                text = summary.read_text(encoding="utf-8")
                self.assertIn("- 확인 필요 모음: 바로 갱신하도록 요청하지 못했습니다", text)
                self.assertIn("**DRAFT_OPENED**", text)

    def test_the_warning_annotation_is_a_fixed_sentence_without_outside_text(self):
        from pipeline import draft_flow, drafts
        self.gh.dispatch_error = drafts.GitHubError("HTTP 403: ::error::위조 @everyone <b>x</b>", 403)
        self.draft()
        self.run_it()
        lines = [line for line in self.out if line.startswith("::")]
        self.assertEqual(lines, [draft_flow.WARN_INBOX])
        for line in self.out:
            self.assertFalse(line.lstrip().startswith("::error::"), line)

    def test_an_unexpected_error_is_contained_and_only_its_class_name_is_logged(self):
        from pipeline import draft_flow
        self.gh.dispatch_error = KeyError("깨짐 @everyone")
        self.draft()
        self.assertEqual(self.run_it(), 0)
        text = "\n".join(self.out)
        self.assertIn("확인 필요 모음 즉시 갱신 중 예상 밖 오류: KeyError", text)
        self.assertNotIn("깨짐", text)
        self.assertIn(draft_flow.WARN_INBOX, self.out)

    def test_no_request_when_there_is_no_new_pull_request(self):
        from pipeline import drafts
        self.assertEqual(self.run_it(), 0)                                           # ① 만든 초안이 없는 실행
        self.assertEqual(self.dispatches(), [])
        self.setUp()                                                                 # ② PR 을 열지 못한 실행(branch_only, 빨강)
        self.draft()
        self.gh.create_errors = [drafts.GitHubError("HTTP 403", 403)]
        self.assertEqual(self.run_it(), 1)
        self.assertEqual(self.dispatches(), [])
        for env, flow in (({"PIPELINE_PAUSE": "true"}, "pr"), ({}, "direct"), ({"DRY_RUN": "1"}, "pr")):       # ③ 멈춤·직접 게시·연습 실행은 GitHub 를 아예 부르지 않는다
            with self.subTest(env=env, flow=flow):
                self.setUp()
                self.draft()
                self.assertEqual(self.run_it({**self.env, **env}, flow), 0)
                self.assertEqual(self.gh.calls, [])

    def test_a_reopened_pull_request_also_asks_once_even_next_to_a_new_one(self):
        from draft_helpers import post_text
        entry = self.draft(date="2026-10-27")
        self.git.remote[entry["branch"]] = "b" * 40
        self.git.branch_files = {entry["paths"][0]: post_text("가"), entry["paths"][1]: post_text("나")}
        import json as _json
        self.git.history_head = _json.dumps([entry], ensure_ascii=False)
        (self.root / "history.json").write_text(_json.dumps([entry], ensure_ascii=False), encoding="utf-8")
        self.assertEqual(self.run_it(), 0)
        self.assertEqual(self.gh.verbs().count("create"), 1)                  # 정리가 PR 없는 브랜치에 PR 을 다시 열었다
        self.assertEqual(len(self.dispatches()), 1)
        # 같은 실행에 새 초안도 있으면 요청은 여전히 한 번
        self.setUp()
        old = self.draft(date="2026-10-27")
        self.git.remote[old["branch"]] = "b" * 40
        self.git.branch_files = {old["paths"][0]: post_text("가"), old["paths"][1]: post_text("나")}
        self.git.history_head = _json.dumps([old], ensure_ascii=False)
        fresh = self.draft(date="2026-10-28")
        self.assertEqual(self.run_it(), 0)
        self.assertEqual(self.gh.verbs().count("create"), 2)
        self.assertEqual(len(self.dispatches()), 1)

    def test_when_git_cannot_name_the_branch_the_workflow_ref_variable_is_used_or_the_request_is_skipped(self):
        from pipeline import draft_flow
        self.git.branch = "HEAD"                                                       # 분리된 HEAD — git 이 브랜치 이름을 말하지 못한다
        self.assertTrue(draft_flow.request_inbox_refresh_safely(self.git, self.gh, {"GITHUB_REF_NAME": "main"}, self.out.append))
        self.assertEqual(self.dispatches(), [("dispatch", "ops-inbox.yml", "main")])
        self.gh.calls.clear()
        self.assertFalse(draft_flow.request_inbox_refresh_safely(self.git, self.gh, {}, self.out.append))
        self.assertEqual(self.dispatches(), [])
        self.assertIn("브랜치를 알 수 없어 건너뜁니다", "\n".join(self.out))

    def test_the_workflow_it_calls_exists_and_accepts_a_manual_start(self):
        """수동 실행 요청은 대상 워크플로에 수동 실행(workflow_dispatch) 트리거가 있어야 받아들여진다(없으면 422). 대상은 확인 필요 모음 하나뿐이다."""
        from pipeline import draft_flow
        from test_workflow_names import load as load_workflow
        self.assertEqual(draft_flow.INBOX_WORKFLOW, "ops-inbox.yml")
        wf = load_workflow(draft_flow.INBOX_WORKFLOW)
        self.assertIn("workflow_dispatch", wf["on"])
        self.assertEqual(wf["name"], "[공통] 확인 필요 모음")


class DispatchWorkflowClientTest(unittest.TestCase):
    """drafts.GitHubClient.dispatch_workflow — 요청 모양과 입력 검사(네트워크 없음)."""

    class Opener:
        def __init__(self, error=None):
            self.requests, self.error = [], error

        def __call__(self, request, timeout=None):
            self.requests.append(request)
            if self.error is not None:
                raise self.error

            class Response:
                def read(self):
                    return b""

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False
            return Response()

    def client(self, **kw):
        from pipeline import drafts
        opener = self.Opener(**kw)
        return drafts.GitHubClient(REAL_REPO, "ghs_" + "T" * 36, opener=opener), opener

    def test_it_posts_the_ref_to_the_dispatch_endpoint_with_an_empty_answer_as_success(self):
        client, opener = self.client()
        self.assertIsNone(client.dispatch_workflow("ops-inbox.yml", "main"))
        request = opener.requests[0]
        self.assertEqual((request.get_method(), request.full_url),
                         ("POST", f"https://api.github.com/repos/{REAL_REPO}/actions/workflows/ops-inbox.yml/dispatches"))
        self.assertEqual(json.loads(request.data.decode("utf-8")), {"ref": "main"})

    def test_unsafe_file_or_branch_names_never_leave_the_process(self):
        from pipeline import drafts
        for workflow, ref in (("../x.yml", "main"), ("ops-inbox", "main"), ("a/b.yml", "main"), ("ops-inbox.yml?x=1", "main"), ("ops-inbox.yml\n", "main"),
                              ("ops-inbox.yml", ""), ("ops-inbox.yml", "../main"), ("ops-inbox.yml", "a b"), ("ops-inbox.yml", "main\n"), ("ops-inbox.yml", "-x"),
                              ("ops-inbox.yml", "a..b"), ("ops-inbox.yml", "x" * 101), (None, "main"), ("ops-inbox.yml", None)):
            with self.subTest(workflow=workflow, ref=ref):
                client, opener = self.client()
                with self.assertRaises(drafts.GitHubError):
                    client.dispatch_workflow(workflow, ref)
                self.assertEqual(opener.requests, [])

    def test_ordinary_branch_names_pass(self):
        for ref in ("main", "release", "ai/claude/M123-x", "feature/a.b-c_d"):
            client, opener = self.client()
            client.dispatch_workflow("ops-inbox.yml", ref)
            self.assertEqual(len(opener.requests), 1, ref)

    def test_http_errors_become_github_errors_without_the_token(self):
        import io
        import urllib.error
        from pipeline import drafts
        token = "ghs_" + "T" * 36
        for code in (403, 404, 422):
            error = urllib.error.HTTPError("https://api.github.com/x", code, "err", {}, io.BytesIO(json.dumps({"message": "거부 " + token}).encode("utf-8")))
            client, _ = self.client(error=error)
            with self.assertRaises(drafts.GitHubError) as caught:
                client.dispatch_workflow("ops-inbox.yml", "main")
            self.assertEqual(caught.exception.status, code)
            self.assertNotIn(token, str(caught.exception))


class InboxSendsTheWaitingAlertTest(unittest.TestCase):
    """확인 필요 모음의 점검이 새 초안 PR 을 알아보면 `📝 발행 대기`를 한 건씩 텔레그램으로 보내고(일반 '확인 필요' 통에서는 뺀다) 코멘트는 그대로 하나다."""

    def setUp(self):
        notify.reset_budget()
        self.addCleanup(notify.reset_budget)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.out = []

    def world(self, pr_numbers=(15,), issue_drafts=False):
        root = h.make_root(self.tmp / "repo", histories={"history.json": [], "blogger_history.json": []}, blogs_json=registry_text())
        fake = h.FakeGitHub()
        fake.runs = {name: [h.make_run(i, h.ago(hours=1 + i))] for i, name in enumerate(("chanceblog.yml", "blogger.yml", "watchdog.yml", "guardrails.yml"), start=1)}
        fake.pulls, fake.details, fake.check_runs = [], {}, {}
        for n in pr_numbers:
            title = f"[초안][Chance] 승인 대기 글 {n} / Waiting post {n}"
            fake.issues.append(h.make_issue(n, title, labels=["초안", "채널:Chance"], created=h.ago(hours=3), pull=True))
            fake.pulls.append(h.make_pull_raw(n, title=title, sha=("%x" % n).rjust(40, "c"), login=h.BOT, user_type="Bot", assoc="CONTRIBUTOR"))
            fake.details[n] = {"mergeable": True, "mergeable_state": "clean"}
            fake.check_runs[("%x" % n).rjust(40, "c")] = []
        if issue_drafts:
            fake.issues.append(h.make_draft_raw(41, "[초안][티스토리] 맛집 지도 만드는 법", "티스토리", hours=3))
        return fake, root

    def check(self, fake, root, net, env=None):
        environ = dict(OPS_ENV, GITHUB_STEP_SUMMARY=str(self.tmp / "summary.md"), **(TELEGRAM_ENV if env is None else env))
        with patched_network(net):
            return oi.run(environ, fake, h.NOW, root, self.out.append, sleep=lambda seconds: None)

    def inbox_number(self, fake):
        return next(i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE)["number"]

    def test_a_new_draft_pull_request_is_one_waiting_message_with_a_button_and_no_general_message(self):
        """재현(R2-4): 새 초안 PR 은 일반 '확인 필요 모음 — 새로 해야 할 일 N건' 통으로만 갔다(PR 이 무엇이고 무엇을 하면 되는지 한 줄이 없고 버튼도 모음 이슈로만 갔다)."""
        fake, root = self.world()
        net = FakeNet()
        self.assertEqual(self.check(fake, root, net), 0)
        self.assertEqual(net.calls, 1)
        body = net.bodies()[0]
        self.assertEqual(body["text"], f"{notify.MEMO_MARK} <b>발행 대기</b> — Chance: 승인 대기 글 15 / Waiting post 15\n→ PR #15 — 읽고 병합하면 공개, 닫으면 폐기됩니다")
        self.assertEqual(body["parse_mode"], "HTML")
        self.assertNotIn("확인 필요 모음 — 새로 해야 할 일", body["text"])
        self.assertEqual(len(fake.comments[self.inbox_number(fake)]), 1)                 # 코멘트(@멘션)는 그대로 하나

    def test_the_button_opens_the_pull_request_not_the_inbox_for_the_real_repository(self):
        fake, root = self.world()
        fake.repo = REAL_REPO
        net = FakeNet()
        environ = dict(OPS_ENV, GITHUB_REPOSITORY=REAL_REPO, GITHUB_STEP_SUMMARY=str(self.tmp / "summary.md"), **TELEGRAM_ENV)
        with patched_network(net):
            oi.run(environ, fake, h.NOW, root, self.out.append, sleep=lambda seconds: None)
        buttons = net.bodies()[0]["reply_markup"]["inline_keyboard"][0]
        self.assertEqual([(button["text"], button["url"]) for button in buttons], [("열기", f"https://github.com/{REAL_REPO}/pull/15")])

    def test_the_next_check_and_a_changed_pull_state_send_nothing_more(self):
        fake, root = self.world()
        net = FakeNet()
        self.check(fake, root, net)
        fake.check_runs = {key: [h.make_check("validate")] for key in fake.check_runs}          # 상태가 바뀌어도(검사 통과) 같은 초안이다
        self.check(fake, root, net)
        self.check(fake, root, net)
        self.assertEqual(net.calls, 1)
        self.assertEqual(len(fake.comments[self.inbox_number(fake)]), 1)

    def test_an_issue_draft_next_to_a_pull_request_draft_keeps_the_general_message_for_the_issue_only(self):
        fake, root = self.world(issue_drafts=True)
        net = FakeNet()
        self.check(fake, root, net)
        texts = [body["text"] for body in net.bodies()]
        self.assertEqual(len(texts), 2)
        self.assertTrue(texts[0].startswith(f"{notify.MEMO_MARK} <b>발행 대기</b> — Chance: "))
        self.assertTrue(texts[1].startswith(f"{notify.PIN_MARK} 확인 필요 모음 — 새로 해야 할 일 1건\n"))
        self.assertIn("초안 대기 — 맛집 지도 만드는 법", texts[1])
        self.assertNotIn("승인 대기 글", texts[1])                                      # PR 초안은 일반 통에 되풀이되지 않는다
        self.assertEqual(len(fake.comments[self.inbox_number(fake)]), 1)
        self.assertIn("승인 대기 글", fake.comments[self.inbox_number(fake)][0])         # 코멘트에는 둘 다 있다

    def test_many_new_pull_requests_are_three_waiting_messages_and_the_rest_in_one_general_message(self):
        fake, root = self.world(pr_numbers=(11, 12, 13, 14, 15))
        net = FakeNet()
        self.check(fake, root, net)
        texts = [body["text"] for body in net.bodies()]
        self.assertEqual(len(texts), inbox.DRAFT_ALERTS_MAX + 1)
        self.assertTrue(all(text.startswith(f"{notify.MEMO_MARK} <b>발행 대기</b>") for text in texts[:3]))
        self.assertTrue(texts[3].startswith(f"{notify.PIN_MARK} 확인 필요 모음 — 새로 해야 할 일 2건\n"))
        shown = "".join(texts[:3])
        for number in (11, 12, 13):
            self.assertIn(f"PR #{number} — ", shown)
        self.assertIn("승인 대기 글 14", texts[3])
        self.assertIn("승인 대기 글 15", texts[3])

    def test_without_the_telegram_secrets_nothing_is_sent_and_the_comment_is_the_same(self):
        fake, root = self.world(issue_drafts=True)
        net = FakeNet()
        self.assertEqual(self.check(fake, root, net, env={}), 0)
        self.assertEqual(net.calls, 0)
        self.assertEqual(len(fake.comments[self.inbox_number(fake)]), 1)
        self.assertNotIn("텔레그램", "\n".join(self.out))

    def test_a_telegram_failure_changes_neither_the_comment_nor_the_marker_nor_the_exit_code(self):
        from notify_helpers import http_error
        fake, root = self.world()
        net = FakeNet(http_error(401, "Unauthorized"))
        self.assertEqual(self.check(fake, root, net), 0)
        number = self.inbox_number(fake)
        self.assertEqual(len(fake.comments[number]), 1)
        self.assertEqual(inbox.parse_marker(next(i for i in fake.issues if i["number"] == number)["body"]).items, ("draft:15:wait",))
        self.assertTrue(any("텔레그램" in line for line in self.out))

    def test_the_old_two_argument_alert_callback_sends_the_general_message_only(self):
        """make_alert(environ, out) 로 부르던 옛 호출(시험·다른 호출 자리)은 글자 하나 다르지 않다."""
        net = FakeNet()
        items = inbox.build_items(snap(drafts=[pr_draft(15)]))
        new_items = [i for i in items if i.level == "action"]
        with patched_network(net):
            oi.make_alert(TELEGRAM_ENV, self.out.append)(new_items, URL + "/issues/1")
        self.assertEqual(net.calls, 1)
        self.assertTrue(net.bodies()[0]["text"].startswith(f"{notify.PIN_MARK} 확인 필요 모음 — 새로 해야 할 일 1건\n"))


class DraftWaitingAlertsPureTest(unittest.TestCase):
    def new_items(self, drafts, pulls=()):
        return [i for i in inbox.build_items(snap(drafts=drafts, pulls=list(pulls))) if i.level == "action" and i.id.startswith("draft:")]

    def test_only_waiting_pull_request_drafts_become_waiting_alerts(self):
        drafts = [pr_draft(15), h.make_draft(41, hours=3), pr_draft(16, hours=100)]
        items = self.new_items(drafts)
        alerts, handled = inbox.draft_waiting_alerts(items, drafts, URL)
        self.assertEqual(handled, {"draft:15:wait"})
        self.assertEqual(alerts, [{"channel": "Chance", "title": "승인 대기 글", "where": "PR #15 — 읽고 병합하면 공개, 닫으면 폐기됩니다", "url": f"{URL}/pull/15"}])

    def test_the_limit_and_the_order_follow_the_items(self):
        drafts = [pr_draft(n) for n in (21, 22, 23, 24)]
        items = self.new_items(drafts)
        alerts, handled = inbox.draft_waiting_alerts(items, drafts, URL)
        self.assertEqual([one["url"] for one in alerts], [f"{URL}/pull/{n}" for n in (21, 22, 23)])
        self.assertEqual(handled, {"draft:21:wait", "draft:22:wait", "draft:23:wait"})
        self.assertEqual(len(inbox.draft_waiting_alerts(items, drafts, URL, limit=1)[0]), 1)
        self.assertEqual(inbox.draft_waiting_alerts(items, drafts, URL, limit=0), ([], set()))

    def test_items_that_are_not_draft_waits_or_whose_draft_is_gone_are_ignored(self):
        odd = [inbox.Item("pr:15:ready", "action", "x"), inbox.Item("draft:15:stale", "check", "x"), inbox.Item("draft:99:wait", "action", "x"),
               inbox.Item("draft:x:wait", "action", "x"), inbox.Item("run:chanceblog.yml:1", "action", "x")]
        self.assertEqual(inbox.draft_waiting_alerts(odd, [pr_draft(15)], URL), ([], set()))
        self.assertEqual(inbox.draft_waiting_alerts([], [pr_draft(15)], URL), ([], set()))
        self.assertEqual(inbox.draft_waiting_alerts(self.new_items([pr_draft(15)]), [], URL), ([], set()))
        self.assertEqual(inbox.draft_waiting_alerts(self.new_items([pr_draft(15)]), None, URL), ([], set()))

    def test_an_issue_draft_with_the_same_number_is_never_turned_into_a_pull_alert(self):
        drafts = [h.make_draft(15, hours=3)]
        self.assertEqual(inbox.draft_waiting_alerts(self.new_items(drafts), drafts, URL), ([], set()))

    def test_a_draft_without_a_channel_label_and_hostile_text_stay_inert(self):
        evil = "[초안] @everyone <b>x</b> [피싱](https://evil.example/x) ::error::위조"
        drafts = [h.make_draft(15, evil, None, pull=True, hours=3)]
        alerts, _ = inbox.draft_waiting_alerts(self.new_items(drafts), drafts, URL)
        one, = alerts
        self.assertEqual(one["channel"], "채널 표시 없음")
        for raw in ("@", "<", "](", "::"):
            self.assertNotIn(raw, one["title"])
        self.assertEqual(one["url"], f"{URL}/pull/15")

    def test_the_text_is_what_the_operator_reads_in_plain_words(self):
        self.assertEqual(inbox.DRAFT_ALERTS_MAX, 3)
        drafts = [pr_draft(15)]
        alerts, _ = inbox.draft_waiting_alerts(self.new_items(drafts), drafts, URL)
        self.assertIn("읽고 병합하면 공개, 닫으면 폐기", alerts[0]["where"])


# ----------------------------------------------------------------------------
# ④ 꺼진 상태(초안 PR 이 새로 열리지 않는 실행·점검)의 출력은 예전과 같다 — 같은 입력의 결과를 지문으로 못박는다
# ----------------------------------------------------------------------------
def draft_flow_off_digest():
    """draft_flow.run 을 새 초안 PR 이 열리지 않는 상황 넷(① 만든 초안 없음 + 오래된 브랜치 정리 ② PR 열기 거부(빨강) ③ 직접 게시 ④ 멈춤)에서 돌린 종료 코드·출력·요약·git·GitHub 호출의 지문.
    수정 전 코드(origin/main 611b2d2)에서 같은 지문이 나온다."""
    from draft_helpers import FakeGit, FakeGitHub as DraftGitHub, write_draft
    from pipeline import draft_flow, drafts
    parts = []
    for name in ("cleanup_only", "pr_refused", "direct", "paused"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "history.json").write_bytes(b"[]\n")
            git, gh, out = FakeGit(root), DraftGitHub(), []
            env = {"GITHUB_REPOSITORY": REAL_REPO, "GITHUB_REPOSITORY_OWNER": REAL_REPO.split("/")[0], "GITHUB_TOKEN": "ghs_" + "T" * 36,
                   "GITHUB_STEP_SUMMARY": str(root / "summary.md")}
            flow = "direct" if name == "direct" else "pr"
            if name == "paused":
                env["PIPELINE_PAUSE"] = "true"
            if name == "cleanup_only":
                git.remote["ai/draft/2026-10-01-s9"] = "b" * 40
            else:
                write_draft(root)
            if name == "pr_refused":
                gh.create_errors = [drafts.GitHubError("HTTP 403", 403)]
            with mock.patch.object(drafts, "chance_flow", return_value=flow):
                code = draft_flow.run(env, git=git, client=gh, out=out.append, sleep=lambda seconds: None,
                                      now=datetime(2026, 10, 28, 9, 20, tzinfo=timezone(timedelta(hours=9))))
            summary = (root / "summary.md").read_text(encoding="utf-8") if (root / "summary.md").exists() else ""
            parts.append(json.dumps({"case": name, "code": code, "out": out, "summary": summary, "git": [list(call) for call in git.calls],
                                     "gh": [list(call) for call in gh.calls]}, ensure_ascii=False, sort_keys=True))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def inbox_alert_off_digest():
    """확인 필요 모음의 점검을 초안 PR 이 없는 네 세계(초안 이슈·실패한 워크플로·정지+워치독·병합 대기 일반 PR)에서 돌린 코멘트·텔레그램 본문·이슈 본문·로그의 지문."""
    parts = []
    for name in ("issue_draft", "failed_run", "paused_watchdog", "plain_pull_ready"):
        notify.reset_budget()
        with tempfile.TemporaryDirectory() as tmp:
            root = h.make_root(Path(tmp) / "repo", histories={"history.json": [], "blogger_history.json": []}, blogs_json=registry_text())
            fake = h.FakeGitHub()
            fake.runs = {file: [h.make_run(i, h.ago(hours=1 + i))] for i, file in enumerate(("chanceblog.yml", "blogger.yml", "watchdog.yml", "guardrails.yml"), start=1)}
            env = dict(OPS_ENV, GITHUB_STEP_SUMMARY=str(Path(tmp) / "summary.md"), **TELEGRAM_ENV)
            if name == "issue_draft":
                fake.issues.append(h.make_draft_raw(41, "[초안][티스토리] 맛집 지도 만드는 법", "티스토리", hours=3))
            elif name == "failed_run":
                fake.runs["chanceblog.yml"] = [h.make_run(1, h.ago(hours=1), conclusion="failure")]
            elif name == "paused_watchdog":
                env["PIPELINE_PAUSE"] = "true"
                fake.issues.append(h.make_watchdog(7))
            else:
                fake.pulls = [h.make_pull_raw(20, title="병합 부탁", sha="d" * 40)]
                fake.details = {20: {"mergeable": True, "mergeable_state": "clean"}}
                fake.check_runs = {"d" * 40: [h.make_check("validate")]}
            net, out = FakeNet(), []
            with patched_network(net):
                code = oi.run(env, fake, h.NOW, root, out.append, sleep=lambda seconds: None)
            inbox_issue = next(i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE)
            parts.append(json.dumps({"case": name, "code": code, "telegram": net.bodies(), "comments": {str(k): v for k, v in fake.comments.items()},
                                     "body": inbox_issue["body"], "out": out}, ensure_ascii=False, sort_keys=True))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


DRAFT_FLOW_OFF_DIGEST = "91b2cf89f43ed84def71a6e78e15628272d521677da2fc03544068a43e647d80"
INBOX_ALERT_OFF_DIGEST = "982f4b343c456b32aab33d6d46c6bdbcde1d902b36de5b6d1f83b89eead2caac"


class DispatchOffStateUnchangedTest(unittest.TestCase):
    def test_runs_that_open_no_new_pull_request_print_and_call_exactly_what_they_did(self):
        self.assertEqual(draft_flow_off_digest(), DRAFT_FLOW_OFF_DIGEST)

    def test_checks_without_a_new_draft_pull_request_send_and_write_exactly_what_they_did(self):
        self.assertEqual(inbox_alert_off_digest(), INBOX_ALERT_OFF_DIGEST)


# ----------------------------------------------------------------------------
# ⑥ 승인 흐름에서 새 글 알림이 안 도는 점 — 경로별 알림 표(문서)가 코드가 하는 일과 같은지
# ----------------------------------------------------------------------------
def path_table():
    """docs/ARCHITECTURE.md §4-5 의 '경로별 알림' 표 → {첫 칸: (직접 게시 칸, 승인 흐름 칸, 보내는 곳)}와 그 아래 '남은 빈틈' 줄."""
    text = (_bootstrap.ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    start = text.index("**경로별 알림 — Chance 직접 게시와 승인 흐름(R2-6, 2026-11-09)**")
    block = text[start:text.index("\n**실패 격리**", start)]
    rows = {}
    for line in block.splitlines():
        if line.startswith("| ") and not line.startswith(("| 알림 |", "|---")):
            cells = [cell.strip() for cell in line.strip("|").split(" | ")]
            rows[cells[0].strip()] = tuple(cells[1:4])
    gaps = next(line for line in block.splitlines() if line.startswith("남은 빈틈:"))
    return rows, gaps


class AlertPathTableTest(unittest.TestCase):
    def test_the_table_lists_every_notification_with_what_each_flow_does(self):
        rows, gaps = path_table()
        self.assertEqual(list(rows), ["새 글이 발행됐습니다(한·영 한 쌍·주소 버튼)", "발행 대기(`📝`, PR 번호·병합하면 공개)", "확인 필요 모음의 새 해야 할 일(코멘트 @멘션 + `📌`)",
                                      "워치독 이슈", "실패 알림", "사이트 배포·반영 확인"])
        new_post, waiting, board, watchdog, failure, deploy = rows.values()
        self.assertTrue(new_post[0].startswith("**간다**"))
        self.assertTrue(new_post[1].startswith("**안 간다**"))                                # 승인 흐름의 빈틈 — 표가 숨기지 않는다
        self.assertEqual(waiting[0], "해당 없음")
        self.assertTrue(waiting[1].startswith("**간다**(R2-4)"))
        self.assertTrue(board[0].startswith("간다") and board[1].startswith("간다"))
        self.assertTrue(watchdog[0].startswith("간다") and watchdog[1].startswith("간다"))
        self.assertIn("DRAFT_WAITING", watchdog[1])
        self.assertIn("`STALE`(경고)이 함께 남는다(R2-2)", watchdog[1])
        for cells in rows.values():
            self.assertTrue(all(cells), cells)
        for gap in ("병합 뒤 '새 글 공개' 텔레그램이 없다", "티스토리·네이버 초안 패키지는 즉시 갱신·`발행 대기`가 아직 이어지지 않았다", "점검이 실패하면 정기 갱신", "켠 뒤 처음 관측한다"):
            self.assertIn(gap, gaps)

    def test_the_new_post_alert_row_is_what_the_workflow_does(self):
        """표의 첫 줄: 직접 게시는 간다, 승인 흐름은 안 간다 — 워크플로 조건을 GitHub 규칙대로 계산해 확인한다."""
        from test_chance_draft_workflow import evaluate, steps_of
        alert = next(step for step in steps_of() if step.get("name") == "텔레그램 알림(새 글)")
        commit = next(step for step in steps_of() if step.get("id") == "commit")
        for event, inputs in (("schedule", {}), ("workflow_dispatch", {"dry_run": False})):
            for flow, expected in (("direct", True), ("pr", False)):
                with self.subTest(event=event, flow=flow):
                    pushed = "true" if evaluate(commit["if"], event, inputs, flow) else ""
                    self.assertEqual(evaluate(alert["if"], event, inputs, flow, pushed=pushed), expected)

    def test_the_waiting_row_is_what_the_code_does_only_for_pull_request_drafts(self):
        drafts = [pr_draft(15), h.make_draft(41, hours=3)]
        items = [i for i in inbox.build_items(snap(drafts=drafts)) if i.level == "action"]
        alerts, handled = inbox.draft_waiting_alerts(items, drafts, URL)
        self.assertEqual((len(alerts), handled), (1, {"draft:15:wait"}))                    # 이슈 초안(티스토리·네이버 패키지)은 아직 이어지지 않았다

    def test_every_row_that_names_a_workflow_or_script_names_an_existing_one(self):
        rows, _gaps = path_table()
        root = _bootstrap.ROOT
        for where in ("chanceblog.yml", "ops-inbox.yml", "watchdog.yml", "pages.yml"):
            self.assertTrue((root / ".github" / "workflows" / where).is_file(), where)
        self.assertTrue((root / "scripts" / "ops_inbox.py").is_file())
        sources = " ".join(cells[2] for cells in rows.values())
        for word in ("chanceblog.yml", "ops_inbox.py", "ops-inbox.yml", "watchdog.yml", "pages.yml"):
            self.assertIn(word, sources)


class DraftListFailureTest(unittest.TestCase):
    """초안 목록(drafts)만 읽지 못한 점검: 초안 PR 이 일반 PR 처럼 보여 열린 PR 규칙의 id 로 올라오는데, 이미 초안으로 알린(표식에 draft:<번호>:wait 가 남은) PR 이면 또 알리지 않는다(R2-1).
    표식만 보는 이 가드는 3일 이내 초안에만 통한다 — 3일 넘은 초안은 확인 수준이라 표식에 흔적이 없다. 그쪽은 브랜치 이름으로 알아보는 StaleDraftListFailureTest 가 맡는다(R2 수정 P2)."""

    def test_a_pull_request_announced_as_a_draft_is_not_announced_again_while_only_the_draft_list_cannot_be_read(self):
        """재현(R2-1): 초안 PR 을 알린 뒤 초안 목록 조회만 실패한 점검에서 같은 PR 이 pr:<번호>:ready 로 새로 알려졌다."""
        drafts = [pr_draft()]
        first = inbox.build_items(snap(pulls=[PULL_STATES["no_ci"]()], drafts=drafts))
        new_first, kept_first = inbox.plan_notice(first, None)
        self.assertEqual(new_first, ["draft:15:wait"])
        failing = snap(pulls=[PULL_STATES["ready"]()], drafts=[], failures=[("drafts", "HTTP 500")])
        items = inbox.build_items(failing)
        self.assertEqual([i.id for i in items if i.level == "action"], ["pr:15:ready"])         # 초안으로 알아보지 못해 일반 PR 줄로 보인다
        new_failing, kept_failing = inbox.plan_notice(items, kept_first, failing.failures)
        self.assertEqual(new_failing, [])                                                       # 같은 PR 을 또 알리지 않는다
        self.assertEqual(kept_failing, ["draft:15:wait", "pr:15:ready"])                        # 초안 id 는 표식에 이어지고 일반 줄 id 도 적혀 다음 점검이 새것으로 보지 않는다
        recovered = inbox.build_items(snap(pulls=[PULL_STATES["ready"]()], drafts=drafts))
        self.assertEqual(inbox.plan_notice(recovered, kept_failing)[0], [])                     # 복구돼도 조용하다

    def test_the_guard_is_only_for_the_same_pull_request_and_only_while_the_draft_list_fails(self):
        previous = ["draft:15:wait"]
        other = snap(pulls=[PULL_STATES["ready"](16)], drafts=[], failures=[("drafts", "HTTP 500")])
        self.assertEqual(inbox.plan_notice(inbox.build_items(other), previous, other.failures)[0], ["pr:16:ready"])        # 다른 PR 은 새 알림이다
        same_but_readable = snap(pulls=[PULL_STATES["ready"]()], drafts=[])                    # 초안 목록을 읽었는데 15번이 초안이 아니다(라벨을 뗐다) → 일반 PR 의 새 알림
        self.assertEqual(inbox.plan_notice(inbox.build_items(same_but_readable), previous, ())[0], ["pr:15:ready"])
        other_source = snap(pulls=[PULL_STATES["ready"]()], drafts=[], failures=[("issues", "HTTP 500")])
        self.assertEqual(inbox.plan_notice(inbox.build_items(other_source), previous, other_source.failures)[0], ["pr:15:ready"])

    def test_without_a_previous_marker_or_branch_numbers_nothing_is_hidden_and_only_real_markers_count(self):
        """표식 가드(draft_pulls 를 모르는 옛 호출)는 표식에 실제로 남을 수 있는 id 만으로 시험한다 — 표식에는 action 수준 id 만 남으므로 `draft:<번호>:stale`(확인 수준)은 나올 수 없다(R2 수정 P2)."""
        failing = snap(pulls=[PULL_STATES["ready"]()], drafts=[], failures=[("drafts", "HTTP 500")])
        items = inbox.build_items(failing)
        self.assertEqual(inbox.plan_notice(items, None, failing.failures)[0], ["pr:15:ready"])                              # 표식이 없으면 처음이라 모두 새것이다
        self.assertEqual(inbox.plan_notice(items, ["draft:15:wait"], failing.failures)[0], [])                              # 초안으로 알린 표식(실제로 남는 id)이 있으면 같은 PR 이다
        self.assertEqual(inbox.plan_notice(items, ["pr:15:ready"], failing.failures)[0], [])                                # 일반 PR 줄로 이미 알린 id 는 원래 새것이 아니다
        self.assertEqual(inbox.plan_notice(items, ["draft:16:wait", "watchdog:7"], failing.failures)[0], ["pr:15:ready"])   # 다른 번호의 표식은 아무것도 가리지 않는다
        for odd in (["draft:x"], ["draft:15"], ["draft:15:wait:x"], [""]):
            self.assertEqual(inbox.plan_notice(items, odd, failing.failures)[0], ["pr:15:ready"], odd)                      # 모양이 틀린 옛 표식은 아무것도 가리지 않는다


# ----------------------------------------------------------------------------
# 꺼진 상태(초안 PR 이 없을 때)의 출력은 예전과 같다 — 같은 입력의 결과를 지문으로 못박는다
# ----------------------------------------------------------------------------
def off_state_cases():
    """초안 PR 이 하나도 없는 입력들(열린 PR·초안 이슈·워치독·정지·조회 실패가 섞인 열두 가지). 수정 전 코드(origin/main 611b2d2)에서 뽑은 지문과 같아야 한다."""
    cases = []
    pulls_by_state = [PULL_STATES[name](20 + i) for i, name in enumerate(PULL_STATES)]
    cases.append(snap(pulls=pulls_by_state))
    cases.append(snap(pulls=pulls_by_state, drafts=[h.make_draft(41, hours=30), h.make_draft(43, "[초안][네이버] 오래된 글", "네이버", hours=100)]))
    cases.append(snap(pulls=[h.make_pull(15, ci="none")], drafts=[h.make_draft(15)]))                      # 이슈 초안과 PR 번호가 같아도 PR 줄은 그대로
    cases.append(snap(pulls=[h.make_pull(15, ci="none")], drafts=[pr_draft(15, state="closed"), pr_draft(16, extra_labels=("폐기",))]))
    cases.append(snap(issues=[h.make_watchdog(7), h.make_watchdog(8, code="NO_POSTS_DAY", severity="warning")], paused=True))
    cases.append(snap(drafts=[h.make_draft(1, hours=2), h.make_draft(2, hours=80)], failures=[("drafts", "HTTP 500"), ("pulls", "HTTP 500")]))
    cases.append(snap(pulls=[h.make_pull(5, login="stranger", assoc="NONE", fork=True)], drafts=[pr_draft(5, login="stranger", assoc="NONE")]))
    cases.append(snap(pulls=[h.make_pull(5, created=ago(days=5), ci="none"), h.make_pull(6, draft=True)]))
    cases.append(snap(drafts=[h.make_draft(41, "[초안][티스토리] " + "가" * 200, "티스토리"), h.make_draft(42, "[초안] @멘션 <b>x</b>", None)]))
    cases.append(snap(notes=[("pulls_cap", "열린 PR 12건 중 처음 8건만 확인했습니다.")], drafts=[h.make_draft(n, hours=n) for n in range(1, 8)]))
    cases.append(snap())
    cases.append(snap(pulls=[h.make_pull(15, mergeable=False, state="dirty")], drafts=[h.make_draft(30, hours=5)], failures=[("pull_details", "HTTP 500")]))
    return cases


def digest_of(cases):
    parts = []
    for snapshot in cases:
        items = inbox.build_items(snapshot)
        new, kept = inbox.plan_notice(items, None, snapshot.failures)
        new2, kept2 = inbox.plan_notice(items, kept, snapshot.failures)
        parts.append(json.dumps({"items": [[i.id, i.level, i.title, i.detail, i.url, i.hint, str(i.since)] for i in items],
                                 "render": inbox.render(items, URL), "plan": [new, kept, new2, kept2],
                                 "alerts": inbox.alert_lines(items), "comment": inbox.comment_text("octo", items, URL + "/issues/1")}, ensure_ascii=False, sort_keys=True))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


# origin/main 611b2d2 의 pipeline/inbox.py 로 같은 off_state_cases() 를 돌린 결과의 지문(수정 전). 이 값이 바뀌면 '초안 PR 이 없을 때 출력이 달라졌다'는 뜻이다.
OFF_STATE_DIGEST = "e81caca50259174c007f64098337e13ab030e57c3d9de434cd85fa537e4d33d2"


class OffStateUnchangedTest(unittest.TestCase):
    def test_without_draft_pull_requests_the_inbox_output_is_byte_for_byte_what_it_was(self):
        self.assertEqual(digest_of(off_state_cases()), OFF_STATE_DIGEST)


# ----------------------------------------------------------------------------
# R2 수정 — 독립 검증(2026-11-09)의 지적 P1–P4 반영. 각 절은 '수정 전에 빨강이던 재현'과 '꺼진 상태·정상 상태의 출력이 그대로임'을 함께 못박는다.
# ----------------------------------------------------------------------------
BRANCH = "ai/draft/2026-10-28-s9"
BRANCH_B = "ai/draft/2026-10-28-s18"
LABEL_ERROR_403 = "HTTP 403: Resource not accessible by integration"


# ---- P1 ① 라벨 붙이기가 실패하면 조용히 넘기지도, 성공 문구를 찍지도 않는다 ------------------------------------------
class LabelFailureIsNotSilentTest(DispatchBase):
    def run_with_label_error(self, error):
        self.gh.label_error = error
        self.draft()
        summary = self.root / "summary.md"
        code = self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)})
        return code, summary.read_text(encoding="utf-8")

    def test_a_failed_label_call_leaves_a_warning_annotation_and_a_plain_summary_line(self):
        """재현(R2 수정 P1): 라벨 붙이기 실패는 일반 로그 한 줄뿐이었고, 실행 요약에는 라벨과 무관하게 '모음 이슈에 초안 대기가 곧 나타납니다' 라는 성공 문구가 찍혔다."""
        error = drafts_mod.GitHubError(LABEL_ERROR_403, 403)
        code, text = self.run_with_label_error(error)
        self.assertEqual(code, 0)                                                        # 발행·PR 은 그대로 — 빨강이 아니다
        self.assertIn(draft_flow.WARN_LABELS, self.out)
        reason = self.out[self.out.index(draft_flow.WARN_LABELS) - 1]                    # 경고 문장이 '이유는 로그의 바로 앞 줄에 있습니다' 라고 말한다 — 정말 그 줄에 있다
        self.assertEqual(reason, f"[초안] 라벨을 붙이지 못했습니다(PR 은 열렸습니다): {one_line(error, 200)}")
        self.assertIn(draft_flow.SUMMARY_LABELS, text.splitlines())
        self.assertIn("**DRAFT_OPENED**", text)
        for success_sentence in ("바로 갱신하도록 요청했습니다", "곧 나타납니다"):
            self.assertNotIn(success_sentence, text)
            self.assertNotIn(success_sentence, "\n".join(self.out))

    def test_the_summary_line_and_the_annotation_are_in_plain_words_and_say_what_to_do(self):
        self.assertIn("발행 대기 알림이 가지 않을 수 있습니다", draft_flow.SUMMARY_LABELS)
        self.assertIn("라벨 `초안`·`채널:Chance`", draft_flow.SUMMARY_LABELS)                  # 급하면 휴대폰에서 직접 붙이는 길을 알려 준다
        self.assertIn("발행 대기 알림이 가지 않을 수 있습니다", draft_flow.WARN_LABELS)
        self.assertIn("다음 실행이 라벨을 다시 붙여 봅니다", draft_flow.WARN_LABELS)
        self.assertTrue(draft_flow.WARN_LABELS.startswith("::warning::"))
        for text in (draft_flow.SUMMARY_LABELS, draft_flow.WARN_LABELS):
            for jargon in ("housekeeping", "attach_labels", "pipeline", "dispatch", "@", "<"):
                self.assertNotIn(jargon, text)

    def test_the_inbox_is_not_asked_to_refresh_for_a_pull_request_it_cannot_recognize(self):
        """모음은 라벨 `초안` 으로만 초안 PR 을 알아본다 — 라벨 없는 PR 때문에 지금 모음을 돌려도 나타나지 않으니 요청도 성공 문구도 없다."""
        code, text = self.run_with_label_error(drafts_mod.GitHubError("HTTP 500", 500))
        self.assertEqual(code, 0)
        self.assertEqual(self.dispatches(), [])
        self.assertIn("[초안] 라벨이 붙지 않아 확인 필요 모음을 바로 갱신하도록 요청하지 않았습니다", "\n".join(self.out))
        self.assertNotIn("- 확인 필요 모음:", text)

    def test_the_annotation_is_a_fixed_sentence_whatever_the_error_text_says(self):
        self.gh.label_error = drafts_mod.GitHubError("HTTP 403: ::error::위조 @everyone <b>x</b>\n::warning::또 위조", 403)
        self.draft()
        self.run_it()
        self.assertEqual([line for line in self.out if line.startswith("::")], [draft_flow.WARN_LABELS])
        for line in self.out:
            self.assertFalse(line.lstrip().startswith(("::error::", "::warning::")) and line != draft_flow.WARN_LABELS, line)

    def test_deliver_returns_whether_the_labels_went_on_and_the_pull_request_is_opened_either_way(self):
        for name, setup in (("정상", lambda: None), ("라벨 만들기 실패", lambda: setattr(self.gh, "ensure_label", mock.Mock(side_effect=drafts_mod.GitHubError("HTTP 500", 500)))),
                            ("라벨 붙이기 실패", lambda: setattr(self.gh, "add_labels", mock.Mock(side_effect=drafts_mod.GitHubError("HTTP 422: x", 422)))),
                            ("네트워크 오류", lambda: setattr(self.gh, "label_error", drafts_mod.GitHubError("URLError: 연결 실패")))):
            with self.subTest(case=name):
                self.setUp()
                setup()
                self.draft()
                result = draft_flow.deliver(self.git, self.gh, self.env, out=self.out.append, sleep=lambda seconds: None)
                self.assertEqual((result.status, result.code, result.labeled), ("opened", 0, name == "정상"))
                self.assertEqual(self.out.count(draft_flow.WARN_LABELS), 0 if name == "정상" else 1)

    def test_with_the_labels_in_place_the_output_has_no_label_warning_and_the_inbox_is_asked_once(self):
        self.draft()
        summary = self.root / "summary.md"
        self.assertEqual(self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)}), 0)
        text = summary.read_text(encoding="utf-8")
        self.assertNotIn(draft_flow.WARN_LABELS, self.out)
        self.assertNotIn(draft_flow.SUMMARY_LABELS, text)
        self.assertIn("- 확인 필요 모음: 바로 갱신하도록 요청했습니다", text)
        self.assertEqual(len(self.dispatches()), 1)
        self.assertEqual(self.gh.prs[41]["labels"], ["초안", "채널:Chance"])

    def test_attach_labels_returns_true_or_false_and_never_raises(self):
        self.gh.add_pr(41, BRANCH, labels=[])
        self.assertIs(draft_flow.attach_labels(self.gh, 41, lambda text: None), True)
        for error in (drafts_mod.GitHubError("HTTP 403", 403), drafts_mod.GitHubError("HTTP 500", 500), drafts_mod.GitHubError("x")):
            self.gh.label_error = error
            lines = []
            self.assertIs(draft_flow.attach_labels(self.gh, 41, lines.append), False)
            self.assertEqual(lines[-1], draft_flow.WARN_LABELS)

    def test_the_result_tuple_still_takes_six_values_and_the_summary_reader_tolerates_an_old_shape(self):
        import types
        self.assertTrue(draft_flow.Result("opened", "b", 1, "", 0, "t").labeled)
        old_shape = types.SimpleNamespace(status="opened", branch=BRANCH, number=1, detail="", code=0, title="t")           # labeled 칸이 없는 옛 모양
        self.assertNotIn(draft_flow.SUMMARY_LABELS, draft_flow.summary_lines(old_shape, REAL_REPO))
        self.assertIn(draft_flow.SUMMARY_LABELS, draft_flow.summary_lines(draft_flow.Result("opened", BRANCH, 1, "", 0, "t", False), REAL_REPO).splitlines())
        for status in ("branch_only", "no_draft"):
            self.assertNotIn(draft_flow.SUMMARY_LABELS, draft_flow.summary_lines(draft_flow.Result(status, BRANCH, None, "x", 1, "t", False), REAL_REPO))


# ---- P1 ② 정리 단계가 라벨 없는 열린 초안 PR 에 라벨을 다시 붙인다 --------------------------------------------------
class RelabelInHousekeepingTest(DispatchBase):
    TODAY = date(2026, 10, 28)

    def housekeeping(self):
        stats = {}
        result = draft_flow.housekeeping(self.git, self.gh, self.env, self.TODAY, out=self.out.append, sleep=lambda seconds: None, stats=stats)
        return result, stats

    def open_pr(self, number=7, branch=BRANCH, labels=None):
        """원격 브랜치와 열린 PR 하나. labels 를 안 주면 정상인 PR(두 라벨이 붙음), labels=[] 면 라벨 붙이기가 실패한 PR."""
        self.git.remote[branch] = "b" * 40
        self.gh.add_pr(number, branch, labels=labels)

    def test_an_open_draft_pull_request_without_any_of_our_labels_gets_them_back(self):
        """재현(R2 수정 P1): 라벨 붙이기가 한 번 실패한 PR 은 다음 실행의 정리 단계도 라벨을 다시 붙이지 않아 영영 무라벨로 남았다."""
        self.open_pr(labels=[])
        (notes, failures), stats = self.housekeeping()
        self.assertEqual((notes, failures), (["라벨 다시 붙이기 1건"], 0))
        self.assertEqual(self.gh.prs[7]["labels"], ["초안", "채널:Chance"])
        self.assertEqual(self.gh.verbs(), ["list", "label", "label", "add_labels"])                  # 있던 라벨 호출만 쓴다(새 종류의 호출·권한 없음)
        self.assertEqual(self.gh.calls[-1], ("add_labels", 7))
        self.assertIn(f"[초안] {BRANCH}: PR #7 에 라벨이 없어 다시 붙였습니다.", self.out)
        self.assertEqual((stats["reopened"], stats["labeled"]), (0, 1))

    def test_nothing_is_called_when_the_labels_are_there_unknown_or_chosen_by_the_operator(self):
        """꺼진 상태의 보증: 라벨이 있거나, 목록이 라벨을 알려 주지 않았거나, 운영자가 일부러 `초안` 만 뗀 PR 은 호출 0 — 목록 읽기 한 번뿐."""
        cases = {"정상": ["초안", "채널:Chance"], "초안만": ["초안"], "운영자가 초안을 뗌(채널 라벨만 남음)": ["채널:Chance"], "폐기": ["폐기"],
                 "폐기와 다른 라벨": ["bug", "폐기"], "다른 채널 라벨": ["채널:티스토리"], "다른 라벨과 초안": ["bug", "초안"],
                 "알 수 없음(None)": None, "목록이 아님(글자)": "초안", "목록이 아님(숫자)": 7}
        for name, labels in cases.items():
            with self.subTest(case=name):
                self.setUp()
                self.open_pr()
                self.gh.prs[7]["labels"] = labels
                (notes, failures), stats = self.housekeeping()
                self.assertEqual((notes, failures, self.gh.calls), ([], 0, [("list", "all")]), name)
                self.assertEqual(stats, {"reopened": 0, "labeled": 0}, name)

    def test_only_a_pull_request_with_a_foreign_label_and_none_of_ours_counts_as_unlabeled(self):
        self.open_pr(labels=["bug", "문서"])
        (notes, failures), _stats = self.housekeeping()
        self.assertEqual((notes, failures), (["라벨 다시 붙이기 1건"], 0))
        self.assertEqual(self.gh.prs[7]["labels"], ["초안", "채널:Chance"])

    def test_a_closed_or_merged_pull_request_without_labels_is_left_alone(self):
        for state, merged in (("closed", False), ("closed", True)):
            with self.subTest(state=state, merged=merged):
                self.setUp()
                self.git.remote[BRANCH] = "b" * 40
                self.gh.add_pr(7, BRANCH, state, merged, labels=[])
                (notes, failures), _stats = self.housekeeping()
                self.assertEqual((notes, failures, self.gh.calls), ([], 0, [("list", "all")]))

    def test_a_pull_request_without_a_readable_number_is_not_touched(self):
        for number in (None, True, "7"):
            with self.subTest(number=number):
                self.setUp()
                self.open_pr()
                self.gh.prs[7]["labels"] = []
                self.gh.prs[7]["number"] = number
                (notes, failures), _stats = self.housekeeping()
                self.assertEqual((notes, failures, self.gh.calls), ([], 0, [("list", "all")]))

    def test_a_failed_relabel_is_warned_counted_and_does_not_stop_the_other_pull_requests(self):
        self.open_pr(7, BRANCH, labels=[])
        self.open_pr(8, BRANCH_B, labels=[])
        real_add = self.gh.add_labels

        def flaky(number, labels):
            if number == 7:
                self.gh.calls.append(("add_labels", number))
                raise drafts_mod.GitHubError(LABEL_ERROR_403, 403)
            return real_add(number, labels)
        self.gh.add_labels = flaky
        (notes, failures), stats = self.housekeeping()
        self.assertEqual(failures, 1)
        self.assertEqual(notes, ["라벨 다시 붙이기 1건", "라벨을 붙이지 못한 PR 1건(발행 대기 알림이 가지 않을 수 있음)", "정리 실패 1건(다음 실행에서 다시 시도)"])
        self.assertEqual(self.out.count(draft_flow.WARN_LABELS), 1)
        self.assertEqual((self.gh.prs[7]["labels"], self.gh.prs[8]["labels"]), ([], ["초안", "채널:Chance"]))
        self.assertEqual(stats["labeled"], 1)

    def test_through_the_run_the_repair_is_in_the_summary_and_the_inbox_is_asked_once_after_the_labels(self):
        self.open_pr(labels=[])
        summary = self.root / "summary.md"
        self.assertEqual(self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)}), 0)
        self.assertEqual(self.gh.verbs(), ["list", "label", "label", "add_labels", "dispatch"])
        text = summary.read_text(encoding="utf-8")
        self.assertIn("- 정리: 라벨 다시 붙이기 1건", text)
        self.assertIn("- 확인 필요 모음: 바로 갱신하도록 요청했습니다", text)
        self.assertNotIn(draft_flow.WARN_HOUSEKEEPING, self.out)

    def test_the_labels_can_be_repaired_even_when_a_new_draft_is_delivered_in_the_same_run(self):
        self.open_pr(labels=[])
        self.draft(date="2026-10-28", slot=18)
        self.assertEqual(self.run_it(), 0)
        self.assertEqual(self.gh.prs[7]["labels"], ["초안", "채널:Chance"])
        self.assertEqual(self.gh.prs[41]["labels"], ["초안", "채널:Chance"])                      # 이번에 연 PR 도 라벨이 붙었다
        self.assertEqual(len(self.dispatches()), 1)                                              # 요청은 여전히 한 번

    def test_a_label_failure_on_the_new_pull_request_and_a_repair_of_an_older_one_in_the_same_run(self):
        """한 실행에 둘이 겹치면: 새 PR 의 라벨 실패는 경고·요약 줄로 드러나고, 옛 PR 의 라벨은 붙으며 모음 요청은 그 옛 PR 때문에 한 번 간다."""
        self.open_pr(7, BRANCH_B, labels=[])
        self.draft(date="2026-10-28", slot=9)
        real_add = self.gh.add_labels

        def only_the_old_one_works(number, labels):
            if number == 7:
                return real_add(number, labels)
            self.gh.calls.append(("add_labels", number))
            raise drafts_mod.GitHubError(LABEL_ERROR_403, 403)
        self.gh.add_labels = only_the_old_one_works
        summary = self.root / "summary.md"
        self.assertEqual(self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)}), 0)
        text = summary.read_text(encoding="utf-8")
        self.assertEqual((self.gh.prs[7]["labels"], self.gh.prs[41]["labels"]), (["초안", "채널:Chance"], []))
        self.assertIn(draft_flow.SUMMARY_LABELS, text.splitlines())
        self.assertIn("- 정리: 라벨 다시 붙이기 1건", text)
        self.assertEqual(len(self.dispatches()), 1)
        self.assertEqual(self.out.count(draft_flow.WARN_LABELS), 1)

    def story_setup(self):
        """초안 하나를 올렸고 정리가 PR 없는 그 브랜치에 PR 을 다시 여는 상황(이전 실행에서 PR 열기가 거부됐던 날)."""
        from draft_helpers import post_text
        entry = self.draft(date="2026-10-27")
        self.git.remote[entry["branch"]] = "b" * 40
        self.git.branch_files = {entry["paths"][0]: post_text("가"), entry["paths"][1]: post_text("나")}
        self.git.history_head = json.dumps([entry], ensure_ascii=False)
        (self.root / "history.json").write_text(json.dumps([entry], ensure_ascii=False), encoding="utf-8")
        return entry

    def test_a_reopened_pull_request_whose_labels_failed_is_counted_and_the_next_tick_repairs_it(self):
        """이야기 한 토막: 정리가 PR 을 다시 열었는데 라벨이 안 붙음 → 실패로 세고 성공 문구·모음 요청이 없다 → 다음 틱이 라벨을 다시 붙이고 그제야 모음을 부른다."""
        self.story_setup()
        self.gh.label_error = drafts_mod.GitHubError(LABEL_ERROR_403, 403)
        summary = self.root / "summary.md"
        self.assertEqual(self.run_it({**self.env, "GITHUB_STEP_SUMMARY": str(summary)}), 0)
        text = summary.read_text(encoding="utf-8")
        self.assertIn("- 정리: PR 다시 열기 1건 · 라벨을 붙이지 못한 PR 1건(발행 대기 알림이 가지 않을 수 있음) · 정리 실패 1건(다음 실행에서 다시 시도)", text)
        self.assertNotIn("- 확인 필요 모음:", text)
        self.assertEqual(self.dispatches(), [])
        self.assertEqual(self.out.count(draft_flow.WARN_LABELS), 1)
        self.assertIn(draft_flow.WARN_HOUSEKEEPING, self.out)
        self.assertEqual(self.gh.prs[41]["labels"], [])
        self.gh.label_error = None                                                                 # 다음 틱: 같은 PR 은 열려 있고 라벨이 없다
        self.gh.calls.clear()
        self.out.clear()
        self.assertEqual(self.run_it(), 0)
        self.assertEqual(self.gh.verbs(), ["list", "label", "label", "add_labels", "dispatch"])
        self.assertEqual(self.gh.prs[41]["labels"], ["초안", "채널:Chance"])
        self.gh.calls.clear()                                                                      # 그다음 틱은 할 일이 없다
        self.assertEqual(self.run_it(), 0)
        self.assertEqual(self.gh.calls, [("list", "all")])

    def test_one_failed_label_call_at_delivery_is_repaired_by_the_next_tick(self):
        """이야기 한 토막(검증 보고서 재현 probe_label_gap): 올리는 실행에서 라벨이 한 번 실패 → 다음 틱의 정리가 라벨을 붙이고 모음을 부른다."""
        entry = self.draft()
        self.gh.label_error = drafts_mod.GitHubError(LABEL_ERROR_403, 403)
        self.assertEqual(self.run_it(), 0)
        self.assertEqual((self.gh.prs[41]["labels"], self.dispatches()), ([], []))
        self.git.history_head = json.dumps([entry], ensure_ascii=False)                            # 이력은 이미 main 에 올라가 있다(새 초안 없음)
        self.gh.label_error = None
        self.gh.calls.clear()
        self.out.clear()
        self.assertEqual(self.run_it(), 0)
        self.assertEqual(self.gh.verbs(), ["list", "label", "label", "add_labels", "dispatch"])
        self.assertEqual(self.gh.prs[41]["labels"], ["초안", "채널:Chance"])

    def test_without_unlabeled_pull_requests_the_summary_notes_are_exactly_what_they_were(self):
        self.open_pr()
        (notes, failures), stats = self.housekeeping()
        self.assertEqual((notes, failures, stats), ([], 0, {"reopened": 0, "labeled": 0}))


class DraftPullListCarriesLabelsTest(unittest.TestCase):
    """GitHubClient 의 PR 요약이 라벨 이름 목록을 담는다(모르면 None) — 정리 단계가 '라벨이 없다'와 '라벨을 모른다'를 구별하게."""

    class Opener:
        def __init__(self, body):
            self.body, self.requests = body, []

        def __call__(self, request, timeout=None):
            self.requests.append(request)
            payload = json.dumps(self.body).encode("utf-8")

            class Response:
                def read(self):
                    return payload

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False
            return Response()

    def raw(self, number, **extra):
        return {"number": number, "state": "open", "merged_at": None, "title": f"t{number}", "created_at": "2026-10-28T00:00:00Z",
                "head": {"ref": BRANCH, "repo": {"full_name": REAL_REPO}}, **extra}

    def listing(self, *items):
        client = drafts_mod.GitHubClient(REAL_REPO, "ghs_" + "T" * 36, opener=self.Opener(list(items)))
        return client.list_draft_pull_requests()

    def test_the_label_names_come_through_and_anything_unreadable_is_unknown_not_empty(self):
        found = self.listing(self.raw(1, labels=[{"name": "초안", "color": "c2e0c6"}, {"name": "채널:Chance"}]), self.raw(2, labels=[]), self.raw(3),
                             self.raw(4, labels="초안"), self.raw(5, labels=[{"name": 5}]), self.raw(6, labels=["초안"]), self.raw(7, labels=[{"name": "초안"}, "x"]))
        self.assertEqual([(p["number"], p["labels"]) for p in found],
                         [(1, ["초안", "채널:Chance"]), (2, []), (3, None), (4, None), (5, None), (6, None), (7, None)])

    def test_the_other_fields_are_unchanged(self):
        found = self.listing(self.raw(1, labels=[]))
        self.assertEqual(found[0], {"number": 1, "state": "open", "merged": False, "head_ref": BRANCH, "head_repo": REAL_REPO,
                                    "created_at": "2026-10-28T00:00:00Z", "title": "t1", "labels": []})

    def test_lacks_labels_reads_the_summary_the_way_the_cleanup_needs(self):
        base = {"number": 7, "state": "open"}
        for labels, expected in ((None, False), ([], True), (["초안"], False), (["채널:Chance"], False), (["폐기"], False), (["bug"], True), ("초안", False)):
            self.assertIs(draft_flow.lacks_labels({**base, "labels": labels}), expected, labels)
        self.assertIs(draft_flow.lacks_labels({**base, "labels": []}), True)
        self.assertIs(draft_flow.lacks_labels({"number": 7, "state": "closed", "labels": []}), False)
        self.assertIs(draft_flow.lacks_labels({"number": 7, "labels": []}), False)
        self.assertIs(draft_flow.lacks_labels({"number": None, "state": "open", "labels": []}), False)
        self.assertIs(draft_flow.lacks_labels({"number": True, "state": "open", "labels": []}), False)


# ---- P2 초안 목록 조회 실패 점검에서 3일 넘은 초안 PR 도 일반 PR 알림으로 다시 가지 않는다 -------------------------------
class StaleDraftListFailureTest(unittest.TestCase):
    REF = "ai/draft/2026-10-26-s9"

    def test_draft_branch_pulls_takes_the_numbers_of_pull_requests_from_draft_branches_inside_this_repository(self):
        pulls = [h.make_pull(15, ref=self.REF), h.make_pull(16, ref="ai/draft/2026-10-26-m091722"), h.make_pull(17, ref="ai/claude/x"),
                 h.make_pull(18, ref=self.REF, login="stranger", assoc="NONE", fork=True), h.make_pull(19, ref="ai/drafts/x"),
                 {"number": 20, "head_ref": None}, {"number": None, "head_ref": "ai/draft/x"}, {"head_ref": "ai/draft/y"}, {"number": True, "head_ref": "ai/draft/z"},
                 "junk", None]
        self.assertEqual(inbox.draft_branch_pulls(pulls), {15, 16})
        for empty in (None, [], (), "abc", 5, {15: 1}):
            self.assertEqual(inbox.draft_branch_pulls(empty), set())
        self.assertEqual(inbox.DRAFT_BRANCH_PREFIX, drafts_mod.BRANCH_PREFIX)

    def test_a_stale_draft_pull_request_is_not_announced_again_when_only_the_draft_list_fails(self):
        """재현(R2 수정 P2): 3일 넘은 초안은 확인 수준(draft:<번호>:stale)이라 표식에 흔적이 없다 — 표식만 보던 가드는 이 PR 을 못 알아보고 일반 PR 알림을 한 번 더 보냈다."""
        pull = h.make_pull(15, ref=self.REF)                                           # 검사 통과·병합 가능: 일반 PR 로 보이면 '병합하면 됩니다' action
        normal = snap(pulls=[pull], drafts=[pr_draft(15, hours=100)])
        items = inbox.build_items(normal)
        self.assertEqual([(i.id, i.level) for i in items if "15" in i.id], [("draft:15:stale", "check")])
        new1, kept1 = inbox.plan_notice(items, None, normal.failures, inbox.draft_branch_pulls(normal.pulls))
        self.assertEqual((new1, kept1), ([], []))                                       # 표식에는 action id 만 남는다 — 이 초안은 흔적이 없다
        failing = snap(pulls=[pull], drafts=[], failures=[("drafts", "HTTP 500")])
        failing_items = inbox.build_items(failing)
        self.assertEqual([i.id for i in failing_items if i.level == "action"], ["pr:15:ready"])         # 초안으로 알아보지 못해 일반 PR 줄로 보인다
        self.assertEqual(inbox.plan_notice(failing_items, kept1, failing.failures)[0], ["pr:15:ready"])  # 브랜치 번호를 모르는 옛 호출(표식만 봄)은 한 번 더 알린다
        new2, kept2 = inbox.plan_notice(failing_items, kept1, failing.failures, inbox.draft_branch_pulls(failing.pulls))
        self.assertEqual(new2, [])                                                      # 브랜치 이름으로 알아보면 표식에 기대지 않고 막는다
        self.assertEqual(kept2, ["pr:15:ready"])                                        # 표식에는 남는다 — 복구돼도 조용하다
        self.assertEqual(inbox.plan_notice(inbox.build_items(normal), kept2, normal.failures, inbox.draft_branch_pulls(normal.pulls))[0], [])

    def test_only_pull_requests_from_draft_branches_and_only_while_the_draft_list_fails(self):
        pulls = [h.make_pull(15, ref=self.REF), h.make_pull(16, ref="ai/claude/x")]
        picked = inbox.draft_branch_pulls(pulls)
        failing = snap(pulls=pulls, drafts=[], failures=[("drafts", "HTTP 500")])
        self.assertEqual(inbox.plan_notice(inbox.build_items(failing), None, failing.failures, picked)[0], ["pr:16:ready"])       # 다른 브랜치의 PR 은 새 알림이다
        readable = snap(pulls=pulls, drafts=[])                                         # 초안 목록을 읽었는데 15번에 라벨이 없다(라벨 붙이기가 실패한 PR): 일반 PR 알림 그대로
        self.assertEqual(inbox.plan_notice(inbox.build_items(readable), None, readable.failures, picked)[0], ["pr:15:ready", "pr:16:ready"])
        other_source = snap(pulls=pulls, drafts=[], failures=[("issues", "HTTP 500")])
        self.assertEqual(inbox.plan_notice(inbox.build_items(other_source), None, other_source.failures, picked)[0], ["pr:15:ready", "pr:16:ready"])
        self.assertEqual(inbox.plan_notice(inbox.build_items(failing), None, failing.failures, None)[0], ["pr:15:ready", "pr:16:ready"])   # 번호를 주지 않거나 이상하면 예전과 같다
        self.assertEqual(inbox.plan_notice(inbox.build_items(failing), None, failing.failures, [True, "15", None])[0], ["pr:15:ready", "pr:16:ready"])

    def test_the_guard_changes_nothing_when_no_draft_branch_numbers_are_given(self):
        """꺼진 상태의 보증: draft_pulls 를 주지 않은 호출(옛 호출·시험)의 결과는 예전과 글자 하나 다르지 않다 — 이전 표식이 있든 없든."""
        for failures in ((), [("drafts", "HTTP 500")], [("pulls", "HTTP 500")]):
            for previous in (None, [], ["draft:15:wait"], ["pr:15:ready"], ["watchdog:7"]):
                with self.subTest(failures=failures, previous=previous):
                    state = snap(pulls=[PULL_STATES["ready"]()], drafts=[], failures=list(failures))
                    items = inbox.build_items(state)
                    self.assertEqual(inbox.plan_notice(items, previous, state.failures), inbox.plan_notice(items, previous, state.failures, ()))


class StaleDraftListFailureRunTest(unittest.TestCase):
    """같은 일을 모음 전체 실행(가짜 GitHub·가짜 텔레그램)으로."""

    def setUp(self):
        notify.reset_budget()
        self.addCleanup(notify.reset_budget)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.out = []

    def world(self, hours):
        root = h.make_root(self.tmp / "repo", histories={"history.json": [], "blogger_history.json": []}, blogs_json=registry_text())
        fake = h.FakeGitHub()
        fake.runs = {name: [h.make_run(i, h.ago(hours=1 + i))] for i, name in enumerate(("chanceblog.yml", "blogger.yml", "watchdog.yml", "guardrails.yml"), start=1)}
        title = "[초안][Chance] 승인 대기 글 / Waiting post"
        fake.issues.append(h.make_issue(15, title, labels=["초안", "채널:Chance"], created=h.ago(hours=hours), pull=True))
        fake.pulls = [h.make_pull_raw(15, title=title, sha="c" * 40, login=h.BOT, user_type="Bot", assoc="CONTRIBUTOR", ref="ai/draft/2026-10-26-s9")]
        fake.details = {15: {"mergeable": True, "mergeable_state": "clean"}}
        fake.check_runs = {"c" * 40: [h.make_check("validate")]}
        return fake, root

    def check(self, fake, root, net):
        environ = dict(OPS_ENV, GITHUB_STEP_SUMMARY=str(self.tmp / "summary.md"), **TELEGRAM_ENV)
        with patched_network(net):
            return oi.run(environ, fake, h.NOW, root, self.out.append, sleep=lambda seconds: None)

    DRAFT_LIST_DOWN = [(r"GET /issues\?.*labels=%EC%B4%88%EC%95%88", oi.ApiError("HTTP 500", status=500))]          # labels=초안 인 읽기만 실패

    def inbox_number(self, fake):
        return next(i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE)["number"]

    def test_a_stale_draft_pull_request_sends_nothing_when_the_draft_list_fails_once_in_between(self):
        """재현(R2 수정 P2): 3일 넘은 초안 PR 이 있는 채로 초안 목록 조회가 한 번 실패한 점검에서 일반 PR 알림(코멘트 + 텔레그램)이 한 번 더 갔다."""
        fake, root = self.world(hours=100)
        net = FakeNet()
        self.assertEqual(self.check(fake, root, net), 0)                                 # ① 정상: 3일 넘은 초안은 확인 수준 — 알림 없음
        fake.fail = list(self.DRAFT_LIST_DOWN)
        self.assertEqual(self.check(fake, root, net), 0)                                 # ② 초안 목록만 실패
        fake.fail = []
        self.assertEqual(self.check(fake, root, net), 0)                                 # ③ 복구
        self.assertEqual(fake.comments.get(self.inbox_number(fake), []), [])
        self.assertEqual(net.calls, 0)

    def test_a_new_draft_pull_request_first_seen_while_the_draft_list_is_down_is_announced_once_at_the_recovery(self):
        """막기만 하고 잃지는 않는다: 조회 실패 중에 처음 본 새 초안은 복구된 점검에서 `📝 발행 대기` 한 통과 코멘트 한 개로 알린다."""
        fake, root = self.world(hours=3)
        fake.fail = list(self.DRAFT_LIST_DOWN)
        net = FakeNet()
        self.assertEqual(self.check(fake, root, net), 0)
        self.assertEqual(net.calls, 0)
        number = self.inbox_number(fake)
        self.assertEqual(fake.comments.get(number, []), [])
        fake.fail = []
        self.assertEqual(self.check(fake, root, net), 0)
        self.assertEqual(net.calls, 1)
        self.assertTrue(net.bodies()[0]["text"].startswith(f"{notify.MEMO_MARK} <b>발행 대기</b> — Chance: "))
        self.assertEqual(len(fake.comments[number]), 1)
        self.check(fake, root, net)
        self.assertEqual((net.calls, len(fake.comments[number])), (1, 1))

    def test_a_plain_pull_request_is_still_announced_while_the_draft_list_fails(self):
        fake, root = self.world(hours=100)
        fake.pulls.append(h.make_pull_raw(16, title="병합 부탁", sha="d" * 40))
        fake.details[16] = {"mergeable": True, "mergeable_state": "clean"}
        fake.check_runs["d" * 40] = [h.make_check("validate")]
        fake.fail = list(self.DRAFT_LIST_DOWN)
        net = FakeNet()
        self.assertEqual(self.check(fake, root, net), 0)
        number = self.inbox_number(fake)
        self.assertEqual(len(fake.comments[number]), 1)
        self.assertIn("PR #16", fake.comments[number][0])
        self.assertNotIn("PR #15", fake.comments[number][0])


# ---- P3 공용 `초안` 라벨 설명은 이슈 초안과 PR 초안 어느 쪽에도 틀리지 않는다 -----------------------------------------------
class SharedDraftLabelDescriptionTest(unittest.TestCase):
    def test_the_description_names_how_each_kind_of_draft_ends_and_does_not_claim_approval_publishes_it(self):
        """재현(R2 수정 P3): 예전 문장 '읽고 승인하면 공개됩니다'는 티스토리·네이버 초안 이슈에는 틀렸다 — 이슈는 승인해도 공개되지 않고 운영자가 본문을 복사해 직접 발행한 뒤 닫는다."""
        _color, description = draft_labels.style_of("초안")
        self.assertIn("PR 은 병합하고", description)
        self.assertIn("이슈는 직접 발행하면 끝납니다", description)
        self.assertNotIn("승인하면 공개", description)
        self.assertLessEqual(len(description), draft_labels.DESCRIPTION_MAX)

    def test_every_place_that_creates_the_label_sends_that_one_sentence(self):
        _color, description = draft_labels.style_of("초안")
        for source, made in (("Chance PR", made_by_chance_pr()), ("초안 이슈", made_by_package_issues()), ("확인 필요 모음", made_by_the_inbox())):
            self.assertEqual(made["초안"][1], description, source)

    def test_the_guide_table_has_the_same_sentence(self):
        text = (_bootstrap.ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| `초안` | 발행을 기다리는 초안"))
        self.assertIn(draft_labels.style_of("초안")[1], row)
        self.assertNotIn("읽고 승인하면 공개됩니다", text)

    def test_the_discard_description_fits_both_kinds_of_draft(self):
        self.assertEqual(draft_labels.style_of("폐기")[1], "쓰지 않기로 한 초안 — 붙이면 발행 대기 목록에서 빠집니다")


# ---- P4 DRAFT_STALL_HOURS 경계의 말과 '시각을 모를 때'의 문구 ---------------------------------------------------------------
class StallBoundaryWordingTest(unittest.TestCase):
    STALE_COMMIT = HEALTH_NOW - timedelta(hours=80)

    def stale_finding(self, drafts):
        findings = health.evaluate(PR_BLOG, [], HEALTH_NOW, last_content_commit=self.STALE_COMMIT, pending_drafts=drafts)
        return next((f for f in findings if f.code == "STALE"), None), sorted(f.code for f in findings)

    def test_the_hint_names_three_days_only_when_the_wait_is_known(self):
        """재현(R2 수정 P4): 대기 시간을 읽지 못해 STALE 이 남을 때도 문구가 '3일 넘게 대기 중'이라고 단정했다."""
        for ages in ((100,), (72,), (100, 5), (200, 90)):
            with self.subTest(ages=ages):
                stale, _codes = self.stale_finding(waiting(*ages))
                self.assertTrue(stale.message.endswith(health.STALL_HINT), ages)
                self.assertIn("3일 넘게 대기 중", stale.message)
        for drafts in ([{"number": 1}], [{"number": 1, "created_at": "엉터리"}], ["문자열"], [{"number": 1}, *waiting(5)], [*waiting(100), {"number": 1}]):
            with self.subTest(drafts=drafts):
                stale, _codes = self.stale_finding(drafts)
                self.assertTrue(stale.message.endswith(health.STALL_HINT_UNKNOWN), drafts)
                self.assertNotIn("3일 넘게 대기 중", stale.message)
                self.assertIn("알 수 없고", stale.message)

    def test_one_unreadable_time_among_young_ones_keeps_the_stale_warning(self):
        """재현(R2 수정 P4): 읽을 수 없는 시각이 섞이고 읽을 수 있는 초안이 모두 어리면 STALE 을 가렸다 — 못 읽은 초안이 오래됐는지 모르는데."""
        young = waiting(5, 30)
        for odd in ({"number": 9}, {"number": 9, "created_at": "엉터리"}, {"number": 9, "created_at": None}, "문자열", None, 7):
            with self.subTest(odd=odd):
                _stale, codes = self.stale_finding(young + [odd])
                self.assertEqual(codes, ["DRAFT_WAITING", "STALE"])
        self.assertEqual(self.stale_finding(young)[1], ["DRAFT_WAITING"])                           # 대조: 모두 읽을 수 있고 어리면 예전처럼 가린다
        self.assertEqual(self.stale_finding(waiting(71.9))[1], ["DRAFT_WAITING"])

    def test_the_oldest_wait_is_unknown_when_any_time_is_unreadable(self):
        now = HEALTH_NOW
        self.assertEqual(health._oldest_wait_hours(waiting(5, 30), now), 30)
        self.assertEqual(health._oldest_wait_hours(waiting(100, 5), now), 100)
        self.assertEqual(health._oldest_wait_hours(waiting(-5), now), 0)                              # 미래 시각은 0 시간으로 본다(예전과 같다)
        for pending in ([{"number": 1}], [{"number": 1}, *waiting(5)], ["문자열", *waiting(5)], [None]):
            self.assertIsNone(health._oldest_wait_hours(pending, now), pending)

    def test_the_boundary_stays_at_exactly_seventy_two_hours_included(self):
        self.assertEqual(health.DRAFT_STALL_HOURS, 72)
        self.assertEqual(self.stale_finding(waiting(72))[1], ["DRAFT_WAITING", "STALE"])
        self.assertEqual(self.stale_finding(waiting(71.99))[1], ["DRAFT_WAITING"])

    def test_the_guides_say_at_least_three_days_where_the_code_includes_the_boundary(self):
        root = _bootstrap.ROOT / "docs"
        architecture = (root / "ARCHITECTURE.md").read_text(encoding="utf-8")
        row = next(line for line in architecture.splitlines() if line.startswith("| `DRAFT_WAITING` |"))
        self.assertIn("72시간(3일, `health.DRAFT_STALL_HOURS`) 이상 방치됐거나", row)
        self.assertNotIn("72시간(3일, `health.DRAFT_STALL_HOURS`) 넘게", row)
        guide = (root / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")
        row = next(line for line in guide.splitlines() if line.startswith("| `DRAFT_WAITING` |"))
        self.assertIn("초안이 3일(72시간) 이상 열려 있고", row)


# ---- P1 ③·P2·P6 문서가 사실대로 적혔는지 ------------------------------------------------------------------------------------
class FixDocsTest(unittest.TestCase):
    def architecture(self):
        return (_bootstrap.ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")

    def test_the_failure_table_tells_what_happens_when_the_labels_fail(self):
        """재현(R2 수정 P1): 표가 라벨 실패를 '다음 실행이 다시 시도' 로 뭉뚱그렸지만 예전에는 다시 시도하지 않았다(라벨 없는 PR 은 알림이 조용히 사라짐)."""
        text = self.architecture()
        self.assertNotIn("| 라벨 실패·정리 실패·정리 중 예상 밖 오류 |", text)
        row = next(line for line in text.splitlines() if line.startswith("| 라벨 붙이기 실패"))
        for phrase in ("::warning::", "발행 대기 알림이 가지 않을 수 있", "정리 단계", "다시 붙", "모음을 바로 갱신하도록 요청하지 않는다"):
            self.assertIn(phrase, row)
        other = next(line for line in text.splitlines() if line.startswith("| 정리 실패·정리 중 예상 밖 오류"))
        self.assertIn("다음 실행이 다시 시도", other)

    def test_the_remaining_gaps_name_the_label_gap_with_its_real_state(self):
        _rows, gaps = path_table()
        self.assertIn("⑤", gaps)
        self.assertIn("라벨", gaps.split("⑤", 1)[1])
        self.assertIn("정리", gaps.split("⑤", 1)[1])

    def test_the_inbox_guide_says_the_draft_list_failure_guard_reads_the_branch_name(self):
        text = (_bootstrap.ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
        self.assertIn("초안 브랜치(`ai/draft/…`)에서 이 저장소 안으로 연 PR", text)
        self.assertNotIn("그 번호가 이미 초안 항목(`draft:<번호>:…`)으로 알려져 있었다면 새 알림에서 뺍니다", text)

    def test_the_guides_say_label_colours_and_descriptions_change_only_for_new_labels(self):
        """R2 수정 P6: '꺼진 상태에서는 출력이 같다'에는 단서가 하나 있다 — 라벨 색·설명은 세 경로에서 정의상 바뀐다(이미 있는 라벨은 그대로)."""
        text = (_bootstrap.ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
        self.assertIn("새로 만드는 라벨", text)
        self.assertIn("이미 있는 라벨은 바뀌지 않습니다", text)
        row = next(line for line in self.architecture().splitlines() if line.startswith("| 라벨 | `초안`(색"))
        self.assertIn("이미 있는 라벨은 바뀌지 않는다", row)


if __name__ == "__main__":
    unittest.main()
