"""초안 패키지(티스토리·네이버) 이력이 현황·감시에서 '글이 하나도 없는 블로그'로 읽히던 일(D-86)의 시험.

`package_issued` 는 공개된 글이 아니라 GitHub 초안 이슈를 만든 이력이다. 확인 필요 모음의 '블로그별 현황'(pipeline/inbox.py `stats_items`)과 워치독 실행 요약의
점검 결과 표(scripts/watchdog.py `render_summary`)가 이 상태를 몰라 초안이 쌓여 있어도 '마지막 글 없음'·'없음'을 보여 줬다(감시 판정 pipeline/health.py 는 이미 알고 있었다).
이 파일이 못박는 것:
  ① 실제 러너가 쓴 이력 항목이 두 화면에 실제 시각으로 보인다(생산자-소비자 계약 — 러너가 상태 이름·시각 칸을 바꾸면 여기서 깨진다)
  ② 성공 경로(시각이 보임)와 실패 경로(실패·건너뜀·깨진 항목만 있으면 여전히 '없음')
  ③ 기존 블로그(Blogger·Chance)의 표시는 그대로다
  ④ 같은 채널에 열린 초안 이슈가 3건 이상이라 러너가 새 초안을 기록 없이 건너뛴 뒤, 감시가 며칠 만에 어떻게 말하는지(STALE 문구에 원인과 푸는 법이 붙는다)
네트워크·GitHub·실제 시크릿 없음.
"""
import json
import random
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import ops_inbox_helpers as h          # 저장소 루트를 import 경로에 올린다(_bootstrap)
import package_helpers as ph
from pipeline import health, inbox, registry
from pipeline import run as run_mod
from pipeline.publishers import issue_package
from pipeline.state import KST, read_json_list
from pipeline.stubs import stub_llm

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402

NOW = h.NOW                     # 2026-10-25 06:00 UTC = KST 15:00
ago = h.ago
ALL_STATUSES = ("posted", "draft", "draft_uploaded", "generated_unpublished", "package_issued", "publish_failed", "llm_failed", "rejected", "skipped_no_topic")


def pkg(**kw):
    return h.make_entry("package_issued", url="https://github.com/o/r/issues/7", post_id="7", **kw)


def package_blog(mode="package"):
    return h.make_blog("tistory_it_tips", "티스토리 (IT 생활 팁)", mode=mode, platform="tistory", history="tistory_history.json",
                       secrets={"llm_api_key": "GEMINI_API_KEY"})


def one(items):
    assert len(items) == 1, [i.id for i in items]
    return items[0]


def stats(history, blog=None, now=NOW):
    blog = blog or package_blog()
    return inbox.stats_items([blog], {blog["key"]: history}, now)


# ----------------------------------------------------------------------------
# 확인 필요 모음의 '블로그별 현황'
# ----------------------------------------------------------------------------
class InboxStatsTest(unittest.TestCase):
    def test_a_blog_with_only_draft_packages_shows_the_last_draft_time_not_none(self):
        item = one(stats([pkg(generated_at=ago(hours=30)), pkg(generated_at=ago(hours=5))]))
        self.assertEqual((item.id, item.level), ("stat:tistory_it_tips", "info"))
        self.assertEqual(item.title, "티스토리 (IT 생활 팁): 마지막 초안 2026-10-25 10:00 KST")
        self.assertNotIn("마지막 글 없음", item.title)
        self.assertEqual(item.detail, "최근 24시간 글 0건 · 초안·미게시 1건")        # 5시간 전 초안만 24시간 안(30시간 전 것은 밖)

    def test_an_old_draft_package_still_shows_when_it_was_made(self):
        item = one(stats([pkg(generated_at=ago(days=3))]))
        self.assertEqual(item.title, "티스토리 (IT 생활 팁): 마지막 초안 2026-10-22 15:00 KST")
        self.assertEqual(item.detail, "최근 24시간 글 0건")

    def test_the_latest_draft_wins_even_when_listed_out_of_order(self):
        history = [pkg(generated_at=ago(hours=2)), pkg(generated_at=ago(hours=40)), pkg(generated_at=ago(hours=10))]
        self.assertIn("마지막 초안 2026-10-25 13:00 KST", one(stats(history)).title)

    def test_date_only_entries_say_so_and_count_when_dated_today_in_kst(self):
        item = one(stats([pkg(date="2026-10-24"), pkg(date="2026-10-25")]))
        self.assertIn("마지막 초안 2026-10-25(날짜만 기록됨)", item.title)
        self.assertIn("초안·미게시 1건", item.detail)

    def test_failures_skips_and_broken_entries_alone_still_say_none(self):
        failing = [h.make_entry(status, ago(hours=3)) for status in ("publish_failed", "llm_failed", "rejected", "skipped_no_topic")]
        broken = [None, 5, "x", {}, [1, 2], {"status": "package_issued"}, {"status": "package_issued", "generated_at": "깨짐"}]
        for history in ([], failing, broken, failing + broken):
            item = one(stats(history))
            self.assertEqual(item.title, "티스토리 (IT 생활 팁): 마지막 글 없음", history)
            self.assertEqual(item.detail, "최근 24시간 글 0건", history)
        self.assertEqual(one(inbox.stats_items([package_blog()], {}, NOW)).title, "티스토리 (IT 생활 팁): 마지막 글 없음")      # 이력 파일 자체가 없을 때

    def test_a_failure_after_a_draft_does_not_hide_the_draft(self):
        history = [pkg(generated_at=ago(hours=30)), h.make_entry("publish_failed", ago(hours=1))]
        self.assertIn("마지막 초안 2026-10-24 09:00 KST", one(stats(history)).title)

    def test_real_posts_keep_the_last_post_title(self):
        """공개된 글이 하나라도 있으면 지금까지처럼 '마지막 글'이다. 초안 패키지는 초안·미게시 건수에만 더해진다."""
        item = one(stats([h.make_entry("posted", ago(hours=20)), pkg(generated_at=ago(hours=1))]))
        self.assertIn("마지막 글 2026-10-24 19:00 KST", item.title)
        self.assertNotIn("마지막 초안", item.title)
        self.assertIn("최근 24시간 글 1건", item.detail)
        self.assertIn("초안·미게시 1건", item.detail)

    def test_a_stopped_package_blog_has_no_stats_item(self):
        self.assertEqual(stats([pkg(generated_at=ago(hours=1))], package_blog(mode="off")), [])

    def test_other_draft_statuses_are_unchanged(self):
        """Blogger 의 초안(draft·generated_unpublished·draft_uploaded)은 예전처럼 '마지막 글 없음'과 초안·미게시 건수다 — 이번 변경은 초안 패키지에만 닿는다."""
        for status in ("draft", "generated_unpublished", "draft_uploaded"):
            item = one(stats([h.make_entry(status, ago(hours=2))], h.make_blog()))
            self.assertEqual(item.title, "Blogger: 마지막 글 없음", status)
            self.assertEqual(item.detail, "최근 24시간 글 0건 · 초안·미게시 1건", status)

    def test_blog_stats_keeps_its_old_keys_and_adds_one(self):
        result = inbox.blog_stats([h.make_entry("posted", ago(hours=5)), h.make_entry("draft", ago(hours=2))], NOW)
        self.assertEqual(sorted(result), ["drafts_24h", "last", "last_package", "posts_24h"])
        self.assertEqual((result["posts_24h"], result["drafts_24h"], result["last_package"]), (1, 1, None))

    def test_the_package_status_name_is_the_one_the_runner_and_the_watchdog_use(self):
        self.assertEqual(inbox.PACKAGE_STATUS, "package_issued")
        self.assertIn(inbox.PACKAGE_STATUS, health.REAL_POST_STATUSES)
        self.assertIn(inbox.PACKAGE_STATUS, run_mod.COUNTED_STATUSES)


# ----------------------------------------------------------------------------
# 워치독 실행 요약의 점검 결과 표
# ----------------------------------------------------------------------------
WD_NOW = datetime(2026, 10, 25, 3, 0, tzinfo=timezone.utc)        # KST 12:00


def kst_entry(status, hours_ago, **extra):
    when = (WD_NOW - timedelta(hours=hours_ago)).astimezone(KST)
    return {"v": 1, "date": when.date().isoformat(), "generated_at": when.isoformat(), "status": status, **extra}


class WatchdogStatsTest(unittest.TestCase):
    def test_package_issued_counts_for_the_last_time_and_the_seven_day_count(self):
        history = [kst_entry("package_issued", 200), kst_entry("package_issued", 30), kst_entry("package_issued", 5)]
        count, last = watchdog._history_post_stats(history, WD_NOW)
        self.assertEqual(count, 2)                                     # 200시간(8일 남짓) 전 것은 7일 밖
        self.assertEqual(last, WD_NOW - timedelta(hours=5))

    def test_failures_and_broken_entries_alone_give_none(self):
        history = [kst_entry(s, 3) for s in ("publish_failed", "llm_failed", "rejected", "skipped_no_topic")]
        history += [None, "x", 7, {}, {"status": "package_issued"}, {"status": "package_issued", "generated_at": "깨짐", "date": "깨짐"}]
        self.assertEqual(watchdog._history_post_stats(history, WD_NOW), (0, None))

    def test_the_summary_counts_exactly_the_statuses_health_calls_real_posts(self):
        """같은 집합을 두 곳에 따로 적다가 어긋난 일(D-86)의 재발 방지: 모든 알려진 상태를 하나씩 넣어 센 것이 health.REAL_POST_STATUSES 와 같아야 한다."""
        counted = {status for status in ALL_STATUSES if watchdog._history_post_stats([kst_entry(status, 1)], WD_NOW)[0] == 1}
        self.assertEqual(counted, set(health.REAL_POST_STATUSES))
        self.assertEqual(counted, {"posted", "draft_uploaded", "package_issued"})
        self.assertTrue(set(health.OK_STATUSES | health.FAIL_STATUSES) <= set(ALL_STATUSES))      # 새 상태가 생기면 이 목록에도 넣어야 위 비교가 그것을 본다
        legacy = {"date": "2026-10-25", "generated_at": (WD_NOW - timedelta(hours=1)).isoformat()}       # 상태 칸이 없는 옛 항목은 정상 발행으로 센다
        self.assertEqual(watchdog._history_post_stats([legacy], WD_NOW)[0], 1)

    def test_summary_row_for_a_package_blog_says_the_numbers_are_draft_issues(self):
        stats_ = [{"key": "tistory_it_tips", "mode": "package", "last_post": WD_NOW - timedelta(hours=5), "posts_7d": 2, "codes": []},
                  {"key": "naver_life_tips", "mode": "package", "last_post": None, "posts_7d": 0, "codes": ["NO_ACTIVITY"]}]
        text = watchdog.render_summary(stats_, [], [], [], [])
        self.assertIn("| tistory_it_tips | package | 2026-10-25 07:00 (초안 이슈) | 2 (초안 이슈) | 정상 |", text)
        self.assertIn("| naver_life_tips | package | 없음 | 0 (초안 이슈) | NO_ACTIVITY |", text)
        self.assertIn("| 블로그 | 모드 | 마지막 글(KST) | 최근 7일 글 수 | 이번 점검 결과 |", text)                  # 머리글은 그대로

    def test_summary_rows_of_existing_blogs_are_unchanged(self):
        stats_ = [{"key": "chance", "mode": "auto", "last_post": WD_NOW - timedelta(hours=14), "posts_7d": 3, "codes": []},
                  {"key": "blogger_macat", "mode": "draft", "last_post": WD_NOW - timedelta(hours=26), "posts_7d": 1, "codes": ["STALE"]},
                  {"key": "blogger_kcyoon", "mode": "auto", "last_post": None, "posts_7d": 0, "codes": ["UNPUBLISHED", "NO_ACTIVITY"]}]
        text = watchdog.render_summary(stats_, [], [], [], [])
        self.assertIn("| chance | auto | 2026-10-24 22:00 | 3 | 정상 |", text)
        self.assertIn("| blogger_macat | draft | 2026-10-24 10:00 | 1 | STALE |", text)
        self.assertIn("| blogger_kcyoon | auto | 없음 | 0 | UNPUBLISHED, NO_ACTIVITY |", text)
        self.assertNotIn("초안 이슈", text)

    def test_blogger_draft_uploads_are_still_counted_as_posts_and_drafts_are_not(self):
        history = [kst_entry("draft_uploaded", 6), kst_entry("draft", 2), kst_entry("generated_unpublished", 1)]
        self.assertEqual(watchdog._history_post_stats(history, WD_NOW), (1, WD_NOW - timedelta(hours=6)))


PACKAGE_REG = {"blogs": [{"key": "tistory_it_tips", "name": "티스토리", "platform": "tistory", "mode": "package",
                          "workflow": ".github/workflows/tistory.yml",
                          "state": {"history": "tistory_history.json", "content_dir": "_tistory_drafts"},
                          "health": {"max_gap_hours": 50, "max_failure_streak": 3}}], "defaults": {}}


class WatchdogCollectTest(unittest.TestCase):
    """collect() 가 초안 패키지 이력을 읽어 현황·판정에 넘기는 곳(가짜 저장소 파일, git 은 부르지 않는다)."""

    def collect(self, history, blogs=None):
        reg = {"blogs": blogs or PACKAGE_REG["blogs"], "defaults": {}}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(watchdog, "enabled_blogs", return_value=reg["blogs"]), \
                mock.patch.object(watchdog, "last_commit_time", return_value=None):
            (Path(tmp) / "tistory_history.json").write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
            return watchdog.collect(reg, tmp, WD_NOW, client=None)

    def test_a_recent_draft_package_is_healthy_and_visible(self):
        findings, stats_ = self.collect([kst_entry("package_issued", 30), kst_entry("package_issued", 10)])
        self.assertEqual(findings, [])
        self.assertEqual((stats_[0]["mode"], stats_[0]["posts_7d"], stats_[0]["last_post"]), ("package", 2, WD_NOW - timedelta(hours=10)))
        text = watchdog.render_summary(stats_, findings, [], [], [])
        self.assertIn("| tistory_it_tips | package | 2026-10-25 02:00 (초안 이슈) | 2 (초안 이슈) | 정상 |", text)
        self.assertNotIn("없음", text.split("점검 결과 |")[1])

    def test_only_failures_stay_none_and_are_reported_as_no_activity(self):
        findings, stats_ = self.collect([kst_entry("publish_failed", 20), kst_entry("rejected", 10)])
        self.assertEqual([(f.code, f.severity) for f in findings], [("NO_ACTIVITY", "warning")])
        self.assertEqual((stats_[0]["last_post"], stats_[0]["posts_7d"], stats_[0]["codes"]), (None, 0, ["NO_ACTIVITY"]))
        self.assertIn("| tistory_it_tips | package | 없음 | 0 (초안 이슈) | NO_ACTIVITY |", watchdog.render_summary(stats_, findings, [], [], []))

    def test_an_old_draft_package_still_shows_its_time_next_to_the_stale_finding(self):
        findings, stats_ = self.collect([kst_entry("package_issued", 60)])
        self.assertEqual([(f.code, f.severity) for f in findings], [("STALE", "critical")])
        self.assertEqual(stats_[0]["last_post"], WD_NOW - timedelta(hours=60))
        self.assertIn("| tistory_it_tips | package | 2026-10-23 00:00 (초안 이슈) | 1 (초안 이슈) | STALE |", watchdog.render_summary(stats_, findings, [], [], []))

    def test_a_stopped_package_blog_is_not_listed(self):
        off = [{**PACKAGE_REG["blogs"][0], "mode": "off"}]
        reg = {"blogs": off, "defaults": {}}
        with tempfile.TemporaryDirectory() as tmp:
            findings, stats_ = watchdog.collect(reg, tmp, WD_NOW, client=None)          # enabled_blogs 는 mode off 를 뺀다(가짜를 끼우지 않음)
        self.assertEqual((findings, stats_), ([], []))


# ----------------------------------------------------------------------------
# 감시 판정의 STALE 문구(pipeline/health.py)
# ----------------------------------------------------------------------------
HEALTH_NOW = datetime(2026, 10, 22, 0, 0, tzinfo=timezone.utc)


def health_entry(status, hours_ago):
    return {"status": status, "generated_at": (HEALTH_NOW - timedelta(hours=hours_ago)).isoformat()}


def health_blog(mode, platform):
    return {"key": "b", "platform": platform, "mode": mode, "health": {"max_gap_hours": 50, "max_failure_streak": 3}}


def codes(findings):
    return sorted(f.code for f in findings)


class StaleHintTest(unittest.TestCase):
    PACKAGE = health_blog("package", "tistory")

    def test_a_package_blog_gets_the_backlog_hint_on_stale(self):
        for platform in ("tistory", "naver"):                                                       # 두 초안 패키지 채널 모두
            (finding,) = health.evaluate(health_blog("package", platform), [health_entry("package_issued", 80)], HEALTH_NOW)
            self.assertEqual((finding.code, finding.severity), ("STALE", "critical"), platform)    # 분류·심각도는 그대로다
            self.assertTrue(finding.message.startswith("마지막 활동(2026-10-19 01:00 KST) 이후 80시간 경과 (허용 50시간)."), finding.message)
            self.assertTrue(finding.message.endswith(health.PACKAGE_STALE_HINT), finding.message)
            for needle in ("초안", "건너뛰", "이슈를 닫거나", "`폐기` 라벨", "워크플로 실행을 확인"):
                self.assertIn(needle, finding.message)

    def test_other_blogs_get_exactly_the_old_message(self):
        for mode, platform in (("auto", "blogger"), ("draft", "blogger"), ("auto", "jekyll-git")):
            (finding,) = health.evaluate(health_blog(mode, platform), [health_entry("posted", 80)], HEALTH_NOW)
            self.assertEqual(finding.message, "마지막 활동(2026-10-19 01:00 KST) 이후 80시간 경과 (허용 50시간).", (mode, platform))

    def test_the_hint_number_is_the_runners_backlog_limit(self):
        limit = issue_package.OPEN_DRAFT_LIMIT
        self.assertIn(f"{limit}건 이상", health.PACKAGE_STALE_HINT)
        self.assertIn(f"{limit}건 미만", health.PACKAGE_STALE_HINT)
        self.assertEqual(limit, 3)

    def test_the_alarm_starts_only_after_max_gap_hours_since_the_last_draft(self):
        """적체로 건너뛰면 이력이 늘지 않으므로(아래 러너 시험) 마지막 package_issued 로부터 허용 시간이 지나야 울린다."""
        self.assertEqual(health.evaluate(self.PACKAGE, [health_entry("package_issued", 49)], HEALTH_NOW), [])
        self.assertEqual(codes(health.evaluate(self.PACKAGE, [health_entry("package_issued", 51)], HEALTH_NOW)), ["STALE"])

    def test_a_recent_draft_package_has_no_findings_and_no_hint(self):
        self.assertEqual(health.evaluate(self.PACKAGE, [health_entry("package_issued", 2)], HEALTH_NOW), [])

    def test_the_hint_is_only_on_stale(self):
        failing = [health_entry("publish_failed", 30), health_entry("publish_failed", 20), health_entry("publish_failed", 10)]
        findings = health.evaluate(self.PACKAGE, failing, HEALTH_NOW, recent_runs=[{"conclusion": "failure"}] * 3)
        self.assertEqual(codes(findings), ["FAIL_STREAK", "NO_ACTIVITY", "RUN_FAIL_STREAK"])
        for finding in findings:
            self.assertNotIn(health.PACKAGE_STALE_HINT.strip(), finding.message, finding.code)

    def test_a_stopped_package_blog_is_not_checked(self):
        self.assertEqual(health.evaluate(health_blog("off", "tistory"), [health_entry("package_issued", 500)], HEALTH_NOW), [])


# ----------------------------------------------------------------------------
# 진짜 러너가 쓴 이력으로(생산자-소비자 계약), 그리고 적체로 건너뛴 뒤의 며칠
# ----------------------------------------------------------------------------
class RealRunnerTest(unittest.TestCase):
    key = "tistory_test"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = ph.make_package_root(self.tmp / "repo")
        patcher = mock.patch.object(watchdog, "last_commit_time", return_value=None)         # 임시 저장소는 git 저장소가 아니다
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_runner(self, now, open_drafts=0):
        out = []
        env = {"GITHUB_STEP_SUMMARY": str(self.tmp / "summary.md"), **ph.package_env()}
        publisher = ph.FakePackagePublisher(open_drafts=open_drafts)
        code = run_mod.run(["--blog", self.key, "--root", str(self.root)], environ=env, now=now, llm=stub_llm,
                           publisher_factory=lambda blog, environ: publisher, rng=random.Random(1), out=out.append)
        return code, "\n".join(out), publisher

    def history(self):
        return read_json_list(self.root / "tistory_test_history.json")

    def reg(self):
        return registry.load_registry(self.root / "pipeline" / "blogs.json")

    def watch(self, now):
        findings, stats_ = watchdog.collect(self.reg(), self.root, now, client=None)
        return [f for f in findings if f.blog == self.key], next(s for s in stats_ if s["key"] == self.key)

    def test_the_runners_own_entry_shows_up_in_both_views(self):
        code, out, publisher = self.run_runner(ph.NOW)
        self.assertEqual((code, len(publisher.created)), (0, 1), out)
        (entry,) = self.history()
        self.assertEqual(entry["status"], "package_issued")
        later = ph.NOW + timedelta(hours=2)
        blog = registry.get_blog(self.reg(), self.key)
        item = one(inbox.stats_items([blog], {self.key: self.history()}, later))
        self.assertTrue(item.title.endswith(": 마지막 초안 2026-10-21 14:20 KST"), item.title)
        self.assertEqual(item.detail, "최근 24시간 글 0건 · 초안·미게시 1건")
        findings, row = self.watch(later)
        self.assertEqual((findings, row["mode"], row["posts_7d"], row["last_post"]), ([], "package", 1, ph.NOW))
        self.assertIn("| tistory_test | package | 2026-10-21 14:20 (초안 이슈) | 1 (초안 이슈) | 정상 |", watchdog.render_summary([row], findings, [], [], []))

    def test_a_backlog_skip_leaves_no_trace_so_the_watchdog_says_stale_after_the_allowed_gap(self):
        """확인 결과(D-86 ②): 열린 초안 3건 이상이면 러너는 이력·초안 사본 없이 건너뛴다(종료 0). 감시는 마지막 package_issued 만 보므로 허용 시간(레지스트리
        기본 48시간)이 지나면 STALE(심각)을 낸다 — 파이프라인이 멈춘 것이 아니라 운영자의 발행·정리를 기다리는 상태인데도. 그래서 문구에 원인 후보와 푸는 법을 붙였다."""
        self.assertEqual(self.run_runner(ph.NOW)[0], 0)
        self.assertEqual(len(self.history()), 1)
        for days in (1, 2):
            code, out, publisher = self.run_runner(ph.NOW + timedelta(days=days), open_drafts=3)
            self.assertEqual(code, 0, out)
            self.assertIn("[SKIP] code=PACKAGE_BACKLOG", out)
            self.assertEqual(publisher.created, [])
        self.assertEqual(len(self.history()), 1)                                      # 건너뛴 날은 이력에 아무것도 남지 않는다
        self.assertEqual(self.watch(ph.NOW + timedelta(hours=47))[0], [])           # 마지막 초안 47시간 뒤: 아직 조용하다
        findings, row = self.watch(ph.NOW + timedelta(hours=49))                    # 49시간 뒤: 허용 48시간을 넘겼다
        self.assertEqual([(f.code, f.severity) for f in findings], [("STALE", "critical")])
        self.assertTrue(findings[0].message.endswith(health.PACKAGE_STALE_HINT), findings[0].message)
        self.assertEqual((row["last_post"], row["posts_7d"], row["codes"]), (ph.NOW, 1, ["STALE"]))      # 표는 마지막 초안 시각을 그대로 보여 준다

    def test_clearing_the_backlog_lets_the_next_run_create_a_draft_and_the_alarm_ends(self):
        self.run_runner(ph.NOW)
        self.assertEqual(self.run_runner(ph.NOW + timedelta(days=1), open_drafts=3)[0], 0)
        later = ph.NOW + timedelta(days=3)
        self.assertEqual([f.code for f in self.watch(later)[0]], ["STALE"])
        code, out, publisher = self.run_runner(later, open_drafts=0)                  # 운영자가 초안을 발행해 이슈를 닫은 뒤의 다음 실행
        self.assertEqual((code, len(publisher.created)), (0, 1), out)
        self.assertEqual(self.watch(later + timedelta(hours=1))[0], [])


if __name__ == "__main__":
    unittest.main()
