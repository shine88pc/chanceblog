"""워치독 주 단위 보완(결함 D-169) 시험 — scripts/watchdog.py: 어떤 레지스트리에서 Chance 를 주 단위로 보는가(chance_weekly_cap)와 collect() 의 배선.

규칙(pipeline/health.py 의 evaluate(weekly_cap=…)는 tests/test_health_weekly.py 가 본다): 제한 재개 잠금이 켜져 있고(lock_active) 잠금 키가 잘못 적혀 있지 않고(lock_key_problems 없음) 규칙을 어기지 않고(lock_errors 없음)
chance.limits.max_posts_per_week 가 1 이상 정수일 때만 그 값을 **Chance 에만** 넘긴다. 그 밖(잠금 꺼짐·상한 없음·키 문제·규칙 위반·레지스트리를 읽지 못함·Chance 아닌 블로그)은 키워드 자체를 넘기지 않아
evaluate 호출의 모양과 출력이 이전과 바이트까지 같다(경보가 더 울리는 쪽 — 안전한 쪽). 읽는 함수는 잠금 가드가 쓰는 publish_lock 의 것을 그대로 가져다 쓴다.
주 단위가 아닌 모든 레지스트리(고정 값 다섯 가지)에서 collect() 의 문제 목록·현황 표·출력이 수정 전 코드와 바이트까지 같다는 것은 지문(OFF_COLLECT_DIGEST — 수정 전 b6b5ea7 에서 얻은 값)으로 견준다.
네트워크·실제 시계·실제 레지스트리 파일의 변경 없이 돈다(실제 레지스트리는 사본만 쓴다 — 켜는 변경이 이 시험을 깨뜨리지 않는다).
"""
import contextlib
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _bootstrap
from lock_helpers import (CHANCE, DEEP_PLACES, KEY_TYPOS, MACAT, VIOLATIONS, blog_of, drop_limit, lock_ready, mutated, put_in, set_limit, today_registry,
                          with_lock_off)
from pipeline import health, publish_lock, registry
from watchdog_helpers import FakeGitHub, run_record

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402

NOW = datetime(2026, 11, 12, 3, 0, tzinfo=timezone.utc)              # KST 2026-11-12 12:00
NOW_MIDNIGHT = datetime(2026, 11, 11, 15, 30, tzinfo=timezone.utc)   # KST 2026-11-12 00:30


def at(hours_ago, now=NOW):
    return now - timedelta(hours=hours_ago)


def iso_z(when):
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pairs(findings):
    return [(f.code, f.severity) for f in findings]


def small_registry(cap=2, locked=True):
    """진짜 레지스트리의 사본에서 Chance 와 영문 Blogger 둘만 남긴 것. locked 면 잠금 켬 + 규칙 전부 지킴(max_posts_per_week=cap), 아니면 잠금 키가 없는 오늘의 모양에 같은 상한 값만 적힌 것."""
    reg = lock_ready() if locked else with_lock_off(lock_ready())
    reg["blogs"] = [blog_of(reg, CHANCE), blog_of(reg, MACAT)]
    set_limit(reg, CHANCE, max_posts_per_week=cap)
    # 허용 시간·상태 파일·모드는 이 시험이 정한 값으로 고정한다 — 진짜 레지스트리 값이 나중에 바뀌어도(예: Chance 의 max_gap_hours) 시험의 숫자가 흔들리지 않게
    chance, blogger = blog_of(reg, CHANCE), blog_of(reg, MACAT)
    chance.update(mode="auto", health={"max_gap_hours": 36, "max_failure_streak": 3}, state={"history": "history.json", "content_dir": "_posts"})
    blogger.update(mode="draft", health={"max_gap_hours": 50, "max_failure_streak": 3}, state={"history": "blogger_history.json", "content_dir": "_blogger_drafts"})
    return reg


def commit_fake(table):
    """git 대신 글 파일 경로(content_dir)마다 정해 둔 커밋 시각 목록(최신순)을 돌려주는 commit_times 대체품. 값이 None 이면 얕은 복제처럼 '알 수 없음'(None)을 돌려준다."""
    def fake(root, path, added_only=False, limit=None, since="30 days ago"):
        times = table.get(path, [])
        if times is None:
            return None
        ordered = sorted(times, reverse=True)
        return ordered[:limit] if limit else ordered
    return fake


def collect_with(reg, table, now=NOW, client=None, history=None):
    """collect() 를 임시 폴더에서 돌린다. history 는 {이력 파일 이름: 항목 목록} — 쓰지 않은 이력 파일은 없는 것(빈 목록)으로 읽힌다."""
    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp, mock.patch.object(watchdog, "commit_times", commit_fake(table)), contextlib.redirect_stdout(buf):
        for name, items in (history or {}).items():
            (Path(tmp) / name).write_text(json.dumps(items), encoding="utf-8")
        findings, stats = watchdog.collect(reg, Path(tmp), now, client)
    return findings, stats, buf.getvalue()


def literal_blog(key, platform, mode, workflow, history, content_dir, gap, **extra):
    """진짜 레지스트리 파일과 무관한 고정 블로그 항목(collect 가 읽는 칸만)."""
    blog = {"key": key, "platform": platform, "mode": mode, "workflow": ".github/workflows/" + workflow, "state": {"history": history, "content_dir": content_dir},
            "health": {"max_gap_hours": gap, "max_failure_streak": 3}}
    blog.update(extra)
    return blog


def not_weekly_registries():
    """주 단위로 읽지 않는 레지스트리들(고정 값): 잠금 키 없음 · 잠금 false 인데 상한 값이 적힘 · 잠금 켜짐인데 규칙이 빠짐 · 상한 3(L8 위반) · 잠금 키 오타(K1)."""
    def chance(**extra):
        return literal_blog("chance", "jekyll-git", "auto", "chanceblog.yml", "history.json", "_posts", 36, **extra)

    def blogger(**extra):
        return literal_blog("blogger_macat", "blogger", "draft", "blogger-en.yml", "blogger_history.json", "_blogger_drafts", 50, **extra)

    ready = {"max_posts_per_day": 1, "max_open_drafts": 3, "max_posts_per_week": 2}
    one_a_day = {"max_posts_per_day": 1}
    return {
        "no_lock_keys": {"blogs": [chance(), blogger()], "defaults": {}},
        "lock_false_with_cap": {"resume_lock": False, "blogs": [chance(publish_flow="pr", limits=dict(ready)), blogger(limits=dict(one_a_day))], "defaults": {}},
        "lock_on_rules_missing": {"resume_lock": True, "blogs": [chance(), blogger()], "defaults": {}},
        "lock_on_cap_3": {"resume_lock": True, "blogs": [chance(publish_flow="pr", limits={**ready, "max_posts_per_week": 3}), blogger(limits=dict(one_a_day))], "defaults": {}},
        "lock_key_typo": {"resume_lok": True, "blogs": [chance(publish_flow="pr", limits=dict(ready)), blogger(limits=dict(one_a_day))], "defaults": {}},
    }


def collect_digest():
    """주 단위가 아닌 레지스트리 x 입력(마지막 글 시각·이력·열린 초안 목록·얕은 복제)마다 collect() 를 돌려 (문제 목록·현황 표·출력)을 한 줄씩 적어 sha256 으로 접는다 → (지문, 건수)."""
    cases = [("stale60", NOW, {"_posts": [at(60)], "_blogger_drafts": [at(2)]}, None, None),
             ("fresh", NOW, {"_posts": [at(5)], "_blogger_drafts": [at(2)]}, None, None),
             ("late210", NOW, {"_posts": [at(210)], "_blogger_drafts": [at(2)]}, None, None),
             ("midnight30", NOW_MIDNIGHT, {"_posts": [at(30, NOW_MIDNIGHT)], "_blogger_drafts": [at(2, NOW_MIDNIGHT)]}, None, None),
             ("shallow", NOW, {"_posts": None, "_blogger_drafts": [at(2)]}, {"history.json": [{"date": "2026-11-05", "slot": 9}]}, None),
             ("drafts100", NOW, {"_posts": [at(150)], "_blogger_drafts": [at(2)]}, None, (150, [100])),
             ("drafts30_late", NOW, {"_posts": [at(210)], "_blogger_drafts": [at(2)]}, None, (210, [30]))]
    parts = []
    for reg_name, reg in sorted(not_weekly_registries().items()):
        for name, now, table, history, drafts in cases:
            client = None
            if drafts is not None:
                post_hours, waits = drafts
                client = DraftsGithub([{"number": 40 + index, "created_at": iso_z(at(wait, now))} for index, wait in enumerate(waits)], post_hours, now=now)
            findings, stats, out = collect_with(copy.deepcopy(reg), table, now, client, history)
            parts.append(json.dumps({"registry": reg_name, "case": name, "findings": [[f.blog, f.code, f.severity, f.message] for f in findings],
                                     "stats": [[s["key"], s["mode"], s["last_post"].isoformat() if s["last_post"] else None, s["posts_7d"], s["codes"]] for s in stats], "out": out}, ensure_ascii=False))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest(), len(parts)


# 수정 전 코드(origin/main b6b5ea7 의 scripts/watchdog.py·pipeline/health.py)에서 같은 입력으로 얻은 값. 주 단위가 아닌 레지스트리는 모두 이 지문과 같아야 한다.
OFF_COLLECT_DIGEST = ("75efc125a795ee8fbc06b9750113b9991e3dca30f24704c9ce0480597f08a3e6", 35)


class OffStateCollectUnchangedTest(unittest.TestCase):
    """꺼진 상태(주 단위가 아닌 모든 레지스트리)에서 collect() 의 문제 목록·현황 표·출력이 수정 전과 바이트까지 같다."""

    def test_none_of_those_registries_is_weekly(self):
        for name, reg in not_weekly_registries().items():
            with self.subTest(registry=name):
                self.assertIsNone(watchdog.chance_weekly_cap(reg))

    def test_every_one_of_them_gives_what_the_code_before_the_change_gave(self):
        self.assertEqual(collect_digest(), OFF_COLLECT_DIGEST)


class ChanceWeeklyCapTest(unittest.TestCase):
    def test_a_locked_registry_that_keeps_every_rule_gives_its_cap(self):
        self.assertEqual(watchdog.chance_weekly_cap(lock_ready()), 2)
        for cap in (1, 2):
            with self.subTest(cap=cap):
                self.assertEqual(watchdog.chance_weekly_cap(small_registry(cap)), cap)

    def test_the_registry_the_flip_will_write_passes_the_real_validation_and_is_read_as_weekly(self):
        """켜는 변경이 적을 값 다섯(lock_ready)은 진짜 검증(python -m pipeline.registry 와 같은 validate_registry)을 통과하고, 그 레지스트리로 워치독은 Chance 를 주 단위로 본다."""
        reg = lock_ready()
        self.assertEqual(registry.validate_registry(reg), [])
        self.assertEqual(watchdog.chance_weekly_cap(reg), 2)

    def test_it_is_the_value_the_lock_guard_reads(self):
        for cap in (1, 2):
            reg = small_registry(cap)
            self.assertEqual(watchdog.chance_weekly_cap(reg), publish_lock.weekly_posts_limit(reg))

    def test_the_cap_can_be_inherited_from_the_registry_defaults(self):
        reg = lock_ready()
        drop_limit(reg, CHANCE, "max_posts_per_week")
        reg["defaults"].setdefault("limits", {})["max_posts_per_week"] = 1
        self.assertEqual(watchdog.chance_weekly_cap(reg), 1)

    def test_with_the_lock_off_there_is_no_weekly_mode_even_when_the_cap_is_written(self):
        self.assertIsNone(watchdog.chance_weekly_cap(with_lock_off(lock_ready())))                  # 키가 없다(오늘의 레지스트리 모양)
        reg = lock_ready()
        reg["resume_lock"] = False
        self.assertIsNone(watchdog.chance_weekly_cap(reg))                                          # false
        reg = today_registry()
        set_limit(reg, CHANCE, max_posts_per_week=2)
        self.assertIsNone(watchdog.chance_weekly_cap(reg))

    def test_a_locked_registry_without_a_usable_cap_is_not_weekly(self):
        """상한이 없거나 올바르지 않으면 잠금 규칙 L8 을 어긴 것이라 가드가 글을 만들지 않고 멈춘다 — 그 상태에서 경보를 늦추지 않는다."""
        for label, mutate in VIOLATIONS["L8"]:
            with self.subTest(case=label):
                self.assertIsNone(watchdog.chance_weekly_cap(mutated(mutate)))
        for bad in (0, -1, True, False, "2", 2.0, 2.5, None, [2]):
            with self.subTest(value=bad):
                self.assertIsNone(watchdog.chance_weekly_cap(mutated(lambda reg, bad=bad: set_limit(reg, CHANCE, max_posts_per_week=bad))))

    def test_every_lock_rule_violation_makes_it_not_weekly(self):
        for rule, cases in VIOLATIONS.items():
            for label, mutate in cases:
                with self.subTest(rule=rule, case=label):
                    reg = mutated(mutate)
                    self.assertTrue(publish_lock.lock_active(reg))
                    self.assertTrue(publish_lock.lock_errors(reg))
                    self.assertIsNone(watchdog.chance_weekly_cap(reg))

    def test_a_misspelled_or_misplaced_lock_key_makes_it_not_weekly(self):
        for label, mutate in KEY_TYPOS:
            with self.subTest(case=label):
                reg = mutated(mutate)
                self.assertTrue(publish_lock.lock_key_problems(reg))
                self.assertIsNone(watchdog.chance_weekly_cap(reg))
        for path in DEEP_PLACES:
            with self.subTest(place=path):
                reg = lock_ready()
                put_in(reg, path)
                self.assertTrue(publish_lock.lock_key_problems(reg))
                self.assertIsNone(watchdog.chance_weekly_cap(reg))

    def test_a_registry_that_cannot_be_read_as_a_registry_is_not_weekly_and_never_raises(self):
        for reg in (None, [], "text", 7, {}, {"blogs": "x"}, {"resume_lock": True}, {"resume_lock": True, "blogs": []}, {"resume_lock": True, "blogs": ["x", 1, None]},
                    {"resume_lock": True, "blogs": [{"key": "chance"}]}, {"resume_lock": True, "defaults": "x", "blogs": [{"key": "chance", "limits": "x"}]}):
            with self.subTest(reg=reg):
                self.assertIsNone(watchdog.chance_weekly_cap(reg))

    def test_a_locked_registry_without_chance_has_no_cap(self):
        reg = lock_ready()
        reg["blogs"] = [blog for blog in reg["blogs"] if blog["key"] != CHANCE]
        self.assertTrue(publish_lock.lock_active(reg))
        self.assertIsNone(watchdog.chance_weekly_cap(reg))

    def test_reading_changes_nothing(self):
        reg = lock_ready()
        before = copy.deepcopy(reg)
        watchdog.chance_weekly_cap(reg)
        self.assertEqual(reg, before)


class CollectWiringTest(unittest.TestCase):
    """collect() 가 evaluate() 에 weekly_cap 을 Chance 에만, 켜졌을 때만, 이전과 같은 호출 모양으로 넘긴다."""

    TABLE = {"_posts": [at(60)], "_blogger_drafts": [at(60)]}        # Chance·영문 Blogger 모두 마지막 글 60시간 전(허용: Chance 36·Blogger 50)

    def run_spy(self, reg, table=None, now=NOW, client=None):
        with mock.patch.object(watchdog, "evaluate", wraps=health.evaluate) as spy:
            result = collect_with(reg, table or self.TABLE, now, client)
        return spy, result

    def test_weekly_mode_reaches_chance_and_only_chance(self):
        spy, _ = self.run_spy(small_registry(2))
        calls = {call.args[0]["key"]: call for call in spy.call_args_list}
        self.assertEqual(sorted(calls), ["blogger_macat", "chance"])
        self.assertEqual(calls["chance"].kwargs["weekly_cap"], 2)
        self.assertNotIn("weekly_cap", calls["blogger_macat"].kwargs)

    def test_the_cap_value_of_the_registry_is_what_is_passed(self):
        spy, _ = self.run_spy(small_registry(1))
        self.assertEqual(next(call for call in spy.call_args_list if call.args[0]["key"] == "chance").kwargs["weekly_cap"], 1)

    def test_with_the_lock_off_the_calls_have_exactly_the_old_shape(self):
        for reg in (small_registry(2, locked=False), today_registry()):
            with self.subTest(blogs=len(reg["blogs"])):
                spy, _ = self.run_spy(reg)
                self.assertGreaterEqual(len(spy.call_args_list), 2)
                for call in spy.call_args_list:
                    self.assertEqual(len(call.args), 3)
                    self.assertEqual(sorted(call.kwargs), ["last_content_commit", "pages_runs", "pending_drafts", "post_days", "recent_runs"])

    def test_with_a_key_problem_or_a_rule_violation_the_calls_have_the_old_shape_too(self):
        broken = [mutated(KEY_TYPOS[0][1]), mutated(VIOLATIONS["L8"][0][1]), mutated(VIOLATIONS["L4"][0][1])]
        for reg in broken:
            reg["blogs"] = [blog_of(reg, CHANCE), blog_of(reg, MACAT)]
            spy, _ = self.run_spy(reg)
            for call in spy.call_args_list:
                self.assertNotIn("weekly_cap", call.kwargs)

    def test_a_sixty_hour_gap_alerts_in_the_old_mode_and_not_for_chance_in_weekly_mode(self):
        old, _, old_out = collect_with(small_registry(2, locked=False), self.TABLE)
        self.assertEqual(sorted(pairs(old)), [("STALE", "critical"), ("STALE", "critical")])
        self.assertEqual({f.blog for f in old}, {"chance", "blogger_macat"})
        new, stats, new_out = collect_with(small_registry(2), self.TABLE)
        self.assertEqual(pairs(new), [("STALE", "critical")])
        self.assertEqual(new[0].blog, "blogger_macat")                                               # 영문 Blogger 는 그대로 50시간 기준이다
        self.assertEqual({row["key"]: row["codes"] for row in stats}, {"chance": [], "blogger_macat": ["STALE"]})

    def test_chance_alerts_after_the_widened_time_with_the_weekly_message(self):
        table = {"_posts": [at(210)], "_blogger_drafts": [at(2)]}
        findings, _, _ = collect_with(small_registry(2), table)
        self.assertEqual(pairs(findings), [("STALE", "critical")])
        self.assertIn("주 단위 기준(상한 2편)", findings[0].message)
        self.assertIn("허용 204시간", findings[0].message)
        table = {"_posts": [at(200)], "_blogger_drafts": [at(2)]}
        self.assertEqual(collect_with(small_registry(2), table)[0], [])

    def test_the_daily_alert_is_silent_in_weekly_mode_and_unchanged_otherwise(self):
        """한국 시각 00:30 의 점검: 마지막 글이 그제 18:30(30시간 전)이라 어제 새 글이 0건 — 이전 기준에서는 NO_POSTS_DAY 경고."""
        table = {"_posts": [at(30, NOW_MIDNIGHT)], "_blogger_drafts": [at(2, NOW_MIDNIGHT)]}
        old, _, _ = collect_with(small_registry(2, locked=False), table, now=NOW_MIDNIGHT)
        self.assertEqual(pairs(old), [("NO_POSTS_DAY", "warning")])
        new, _, _ = collect_with(small_registry(2), table, now=NOW_MIDNIGHT)
        self.assertEqual(new, [])

    def test_a_shallow_clone_has_no_git_times_and_the_history_alone_decides_in_both_modes(self):
        """얕은 복제: 글 커밋 시각과 글 날짜 집합을 알 수 없다(None) — 이력 항목의 날짜(그날 KST 23:59)가 마지막 활동이다."""
        table = {"_posts": None, "_blogger_drafts": [at(2)]}
        history = {"history.json": [{"date": "2026-11-05", "slot": 9}]}                              # 11-05 23:59 KST 는 지금(11-12 12:00)보다 약 156시간 전
        old, _, _ = collect_with(small_registry(2, locked=False), table, history=history)
        self.assertEqual(pairs(old), [("STALE", "critical")])
        new, _, _ = collect_with(small_registry(2), table, history=history)
        self.assertEqual(new, [])
        history = {"history.json": [{"date": "2026-11-02", "slot": 9}]}                              # 약 228시간 전
        new, _, _ = collect_with(small_registry(2), table, history=history)
        self.assertEqual(pairs(new), [("STALE", "critical")])
        self.assertIn("주 단위 기준(상한 2편)", new[0].message)

    def test_a_corrupt_history_file_is_still_reported_as_before(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(watchdog, "commit_times", commit_fake(self.TABLE)), contextlib.redirect_stdout(buf):
            (Path(tmp) / "history.json").write_text("{깨짐", encoding="utf-8")
            findings, _ = watchdog.collect(small_registry(2), Path(tmp), NOW, None)
        self.assertIn(("STATE_CORRUPT", "critical"), pairs(findings))

    def test_a_log_line_names_the_weekly_basis_only_when_it_is_on(self):
        _, _, out = collect_with(small_registry(2), self.TABLE)
        self.assertEqual(out.count("주 단위 기준으로 점검합니다"), 1)
        self.assertIn("[참고] chance: 주 단위 기준으로 점검합니다(주간 상한 2편", out)
        self.assertNotIn("blogger_macat", out)
        _, _, out = collect_with(small_registry(2, locked=False), self.TABLE)
        self.assertEqual(out, "")                                                                    # 꺼진 상태는 아무것도 더 찍지 않는다

    def test_the_run_summary_table_has_no_new_column_or_row(self):
        findings, stats, _ = collect_with(small_registry(2), self.TABLE)
        self.assertEqual(sorted(stats[0]), ["codes", "key", "last_post", "mode", "posts_7d"])
        summary = watchdog.render_summary(stats, findings, [], [], [])
        self.assertIn("| 블로그 | 모드 | 마지막 글(KST) | 최근 7일 글 수 | 이번 점검 결과 |", summary)
        self.assertNotIn("주 단위", summary)

    def test_the_weekly_message_reaches_the_issue_body(self):
        table = {"_posts": [at(300)], "_blogger_drafts": [at(2)]}
        findings, _, _ = collect_with(small_registry(1), table)
        gh = FakeGitHub(now=NOW)
        created, closed, _, new_critical = watchdog.sync_issues(findings, [], gh, owner="octo", now=NOW, out=lambda text: None)
        self.assertEqual((created, closed, new_critical), (["[Watchdog] chance: STALE"], [], ["[Watchdog] chance: STALE"]))
        body = next(iter(gh.issues.values()))["body"]
        self.assertIn("주 단위 기준(상한 1편)", body)
        self.assertIn("허용 204시간", body)
        self.assertNotIn("<", body.replace("<!-- watchdog:notified=", ""))                           # 본문에 새 HTML 이 끼지 않는다

    def test_an_open_old_stale_issue_is_updated_with_the_new_sentence_not_closed(self):
        table = {"_posts": [at(300)], "_blogger_drafts": [at(2)]}
        findings, _, _ = collect_with(small_registry(2), table)
        gh = FakeGitHub(now=NOW)
        old = health.Finding("chance", "STALE", "critical", "마지막 활동 이후 100시간 경과 (허용 36시간).")
        number = gh.add_issue(old.title, watchdog.issue_body(old, "octo", NOW.isoformat(timespec="seconds")))
        created, closed, _, new_critical = watchdog.sync_issues(findings, gh.list_open_issues(), gh, owner="octo", now=NOW, out=lambda text: None)
        self.assertEqual((created, closed, new_critical), ([], [], []))
        self.assertEqual(gh.issues[number]["state"], "open")
        self.assertIn("주 단위 기준(상한 2편)", gh.issues[number]["body"])

    def test_the_old_stale_issue_closes_when_weekly_mode_makes_the_alert_unnecessary(self):
        """마지막 글 60시간 전: 이전 기준으로는 열려 있던 STALE 이 주 단위 기준에서는 해소돼 자동으로 닫힌다(켜는 날 쌓인 거짓 경보가 사라진다)."""
        findings, _, _ = collect_with(small_registry(2), {"_posts": [at(60)], "_blogger_drafts": [at(2)]})
        self.assertEqual(findings, [])
        gh = FakeGitHub(now=NOW)
        old = health.Finding("chance", "STALE", "critical", "마지막 활동 이후 60시간 경과 (허용 36시간).")
        number = gh.add_issue(old.title, watchdog.issue_body(old, "octo", NOW.isoformat(timespec="seconds")))
        _, closed, _, _ = watchdog.sync_issues(findings, gh.list_open_issues(), gh, owner="octo", now=NOW, out=lambda text: None)
        self.assertEqual(closed, ["[Watchdog] chance: STALE"])
        self.assertEqual(gh.issues[number]["state"], "closed")


class DraftsGithub(FakeGitHub):
    """열린 초안 PR 목록(drafts)을 돌려주는 가짜 GitHub. post_hours 시간 전의 글이 배포된 상태(성공한 사이트 배포 실행)라 PAGES_NOT_DEPLOYED 가 끼지 않는다."""

    def __init__(self, drafts, post_hours, **kw):
        kw.setdefault("runs", {"pages.yml": [run_record("success", at(post_hours, kw.get("now", NOW)) + timedelta(minutes=2))]})
        super().__init__(**kw)
        self.drafts = drafts

    def list_open_draft_pulls(self):
        self.calls.append(("draft-pulls",))
        return list(self.drafts)


class CollectApprovalFlowTest(unittest.TestCase):
    """승인 흐름: 열린 초안 PR 을 읽어 DRAFT_WAITING 변환을 하는 것은 그대로고, 새 허용 시간으로 STALE 이 울릴 때만 일어난다."""

    Github = DraftsGithub

    def drafts(self, *hours):
        return [{"number": 40 + index, "created_at": iso_z(at(h))} for index, h in enumerate(hours)]

    def test_inside_the_weekly_time_a_waiting_draft_makes_no_alert(self):
        client = self.Github(self.drafts(100), 150, now=NOW)
        findings, _, _ = collect_with(small_registry(2), {"_posts": [at(150)], "_blogger_drafts": [at(2)]}, client=client)
        self.assertEqual(findings, [])
        self.assertIn(("draft-pulls",), client.calls)                                                # 목록은 이전처럼 읽는다

    def test_past_the_weekly_time_the_waiting_draft_replaces_the_stale_alert(self):
        client = self.Github(self.drafts(30), 210, now=NOW)
        findings, _, _ = collect_with(small_registry(2), {"_posts": [at(210)], "_blogger_drafts": [at(2)]}, client=client)
        self.assertEqual(pairs(findings), [("DRAFT_WAITING", "warning")])
        client = self.Github(self.drafts(100), 210, now=NOW)
        findings, _, _ = collect_with(small_registry(2), {"_posts": [at(210)], "_blogger_drafts": [at(2)]}, client=client)
        self.assertEqual(pairs(findings), [("DRAFT_WAITING", "warning"), ("STALE", "warning")])
        self.assertIn("주 단위 기준(상한 2편)", findings[1].message)

    def test_an_unreadable_draft_list_leaves_the_stale_alert_critical_and_says_so_in_the_log(self):
        class Broken(self.Github):
            def list_open_draft_pulls(self):
                raise RuntimeError("목록을 읽지 못함")
        client = Broken([], 210, now=NOW)
        findings, _, out = collect_with(small_registry(2), {"_posts": [at(210)], "_blogger_drafts": [at(2)]}, client=client)
        self.assertEqual(pairs(findings), [("STALE", "critical")])
        self.assertIn("초안 PR 목록 조회 실패", out)

    def test_the_old_mode_still_reads_the_list_and_converts_at_the_old_time(self):
        client = self.Github(self.drafts(100), 150, now=NOW)
        findings, _, _ = collect_with(small_registry(2, locked=False), {"_posts": [at(150)], "_blogger_drafts": [at(2)]}, client=client)
        self.assertEqual(pairs(findings), [("DRAFT_WAITING", "warning"), ("STALE", "warning")])


class MainWeeklyTest(unittest.TestCase):
    """watchdog.main() 을 끝까지: 잠금이 켜진 레지스트리에서 점검 요약과 종료 코드(토큰이 없어 이슈는 만들지 않는 dry-run)."""

    CONTROL_ENV = ("PIPELINE_PAUSE", "WATCHDOG_DRY_RUN", "GITHUB_TOKEN", "GITHUB_REPOSITORY", "GITHUB_REPOSITORY_OWNER", "GITHUB_STEP_SUMMARY")

    def run_main(self, reg, chance_hours_ago, env=None):
        """Chance 의 마지막 글이 chance_hours_ago 시간 전(영문 Blogger 는 2시간 전)인 상태로 main() 을 돌린다. 시각은 실제 지금을 기준으로 만든다."""
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        summary = Path(folder.name) / "summary.md"
        now = datetime.now(timezone.utc)
        table = {"_posts": [now - timedelta(hours=chance_hours_ago)], "_blogger_drafts": [now - timedelta(hours=2)]}
        environ = {key: value for key, value in os.environ.items() if key not in self.CONTROL_ENV}
        environ["GITHUB_STEP_SUMMARY"] = str(summary)
        environ.update(env or {})
        buf = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, environ, clear=True))
            stack.enter_context(mock.patch.object(watchdog, "ROOT", Path(folder.name)))
            stack.enter_context(mock.patch.object(watchdog, "load_registry", return_value=reg))
            stack.enter_context(mock.patch.object(watchdog, "validate_registry", return_value=[]))
            stack.enter_context(mock.patch.object(watchdog, "commit_times", commit_fake(table)))
            with contextlib.redirect_stdout(buf):
                code = watchdog.main()
        text = summary.read_text(encoding="utf-8") if summary.exists() else ""
        return SimpleNamespace(code=code, out=buf.getvalue(), summary=text)

    def test_a_sixty_hour_gap_is_all_quiet_for_chance_when_the_lock_is_on(self):
        result = self.run_main(small_registry(2), 60)
        self.assertEqual(result.code, 0)
        self.assertIn("[참고] chance: 주 단위 기준으로 점검합니다", result.out)
        self.assertIn("이상 없음", result.out)
        self.assertIn("| chance | auto |", result.summary)
        self.assertIn("정상", result.summary)

    def test_the_same_run_with_the_lock_off_reports_the_stale_alert_like_before(self):
        result = self.run_main(small_registry(2, locked=False), 60)
        self.assertEqual(result.code, 0)                                                             # 토큰이 없어 dry-run 으로 끝난다(종료 0)
        self.assertIn("STALE", result.out)
        self.assertIn("(허용 36시간).", result.out)
        self.assertNotIn("주 단위", result.out)

    def test_the_pause_variable_still_wins(self):
        result = self.run_main(small_registry(2), 300, env={"PIPELINE_PAUSE": "true"})
        self.assertEqual(result.code, 0)
        self.assertIn("[일시정지]", result.out)
        self.assertNotIn("주 단위", result.out)


if __name__ == "__main__":
    unittest.main()
