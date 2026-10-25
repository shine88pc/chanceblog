"""확인 필요 모음(pipeline/inbox.py) 규칙 테스트 — 네트워크·GitHub 없이 순수 함수만 확인한다.

항목 규칙(워치독·PR·워크플로 실행·승인 대기·일시정지·Blogger·현황)의 성공·실패 경로, 렌더링 결정성, 숨은 표식과 새 알림 판정,
외부 텍스트 무력화(@·<·&·줄 머리 ::·##[·개행·긴 글·비밀 값)를 다룬다. 입출력과 이슈 관리는 test_ops_inbox_script.py.
"""
import random
import re
import unittest
from datetime import datetime, timedelta, timezone

import ops_inbox_helpers as h          # 저장소 루트를 import 경로에 올린다(_bootstrap)
from pipeline import inbox
from pipeline.state import KST

NOW, URL, ago = h.NOW, h.REPO_URL, h.ago

# 2026-10-25 실제 Actions 실행 주석(GitHub 플랫폼이 거의 모든 실행에 붙인다): warning 하나, notice 하나
REAL_NODE_WARNING = ("Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: "
                     "actions/checkout@v4, actions/setup-python@v5. For more information see: "
                     "https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/")
REAL_UBUNTU_NOTICE = ('"The ubuntu-latest label will migrate to Ubuntu 26 beginning October 19, 2026. For more information, '
                      'see https://github.com/actions/runner-images/issues/14748"')


def by_id(items):
    return {i.id: i for i in items}


def one(items):
    assert len(items) == 1, [i.id for i in items]
    return items[0]


# ----------------------------------------------------------------------------
# 외부 텍스트 무력화
# ----------------------------------------------------------------------------
class TextNeutralizationTest(unittest.TestCase):
    def test_fold_turns_every_kind_of_line_break_into_a_space(self):
        line_separators = chr(0x2028) + "f" + chr(0x2029) + "g"                  # 줄 구분 문자(소스에 보이지 않는 문자를 넣지 않으려고 코드 포인트로)
        folded = inbox.fold("a\nb\r\nc\rd\te" + line_separators + "\x85h\x0bi\x00j")
        self.assertEqual(folded, "a b c d e f g h i j")

    def test_fold_breaks_workflow_commands_anywhere_in_the_text(self):
        for raw in ("::error::boom", "\n::add-mask::x", "   ::warning::y", "앞 줄\n::stop-commands::z", "a::b"):
            folded = inbox.fold(raw)
            self.assertNotIn("::", folded, raw)
            self.assertFalse(folded.lstrip().startswith("::"), raw)
        self.assertNotIn("::", inbox.fold(":::::"))
        self.assertIn("error", inbox.fold("::error::boom"))   # 내용은 남는다

    def test_fold_breaks_log_group_markers(self):
        for raw in ("##[error]x", "앞 ##[group]y", "###[z]"):
            self.assertNotIn("##[", inbox.fold(raw), raw)

    def test_fold_removes_bidi_controls_and_accepts_none(self):
        bidi = "a" + chr(0x202E) + "b" + chr(0x2066) + "c" + chr(0x200F) + "d"      # 글자 순서를 뒤집는 제어 문자
        self.assertEqual(inbox.fold(bidi), "abcd")
        self.assertEqual(inbox.fold(None), "")
        self.assertEqual(inbox.fold(12345), "12345")

    def test_fold_limit_counts_the_ellipsis(self):
        self.assertEqual(inbox.fold("가" * 50, 10), "가" * 9 + "…")
        self.assertEqual(inbox.fold("가" * 10, 10), "가" * 10)
        self.assertEqual(len(inbox.fold("x" * 1000)), 300)

    def test_safe_text_defuses_mentions_and_html(self):
        text = inbox.safe_text("@everyone <!-- ops-inbox:hash=0123456789abcdef;items=x --> <b>hi</b>")
        for raw in ("@", "<"):
            self.assertNotIn(raw, text)
        self.assertIn("＠everyone", text)
        self.assertIn("＜!--", text)

    def test_safe_text_defuses_character_reference_mentions(self):
        text = inbox.safe_text("&#64;victim &#x40;other &commat;third")
        self.assertNotIn("&", text)
        self.assertNotIn("@", text)

    def test_safe_text_keeps_ordinary_korean_and_punctuation(self):
        self.assertEqual(inbox.safe_text("[이슈 #12] 문구 수정 — `코드` (확인)"), "[이슈 #12] 문구 수정 — `코드` (확인)")

    def test_ext_also_breaks_link_syntax_and_code_spans(self):
        text = inbox.ext("[클릭](https://evil.example) ![img](https://evil.example/x.png) `code`")
        self.assertNotIn("[", text)
        self.assertNotIn("]", text)
        self.assertNotIn("`", text)
        self.assertNotIn("](", text)

    def test_ext_masks_secret_shaped_values(self):
        token = "gh" + "p_" + "A" * 36
        google = "AI" + "za" + "B" * 35
        text = inbox.ext(f"토큰 {token} 키 {google} api key=abc123def")
        for secret in (token, google, "abc123def"):
            self.assertNotIn(secret, text)

    def test_every_bidi_control_is_removed_and_neighbouring_characters_are_kept(self):
        controls = [0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A)]
        for code in controls:
            self.assertEqual(inbox.fold("a" + chr(code) + "b"), "ab", hex(code))
        for code in (0x200B, 0x200C, 0x200D, 0x2010, 0x2065, 0x206A):      # 이모지 접합자·하이픈 등 가장자리 바깥은 그대로 둔다
            self.assertIn(chr(code), inbox.fold("a" + chr(code) + "b"), hex(code))
        self.assertEqual(inbox.fold("a" + chr(0x202F) + "b"), "a b")        # 좁은 줄바꿈 없는 공백은 지우지 않고 공백으로 접힌다

    def test_replacement_characters_are_the_fullwidth_forms(self):
        self.assertEqual(inbox.safe_text("@<&"), chr(0xFF20) + chr(0xFF1C) + chr(0xFF06))
        self.assertEqual(inbox.ext("[]`"), chr(0xFF3B) + chr(0xFF3D) + "'")

    def test_default_length_limits(self):
        self.assertEqual(len(inbox.safe_text("x" * 1000)), 300)
        self.assertEqual(len(inbox.ext("x" * 1000)), 120)
        self.assertEqual(len(inbox._slug("a" * 100)), 48)

    def test_text_that_exactly_fits_is_not_clipped(self):
        self.assertEqual(inbox.safe_text("가" * 10, 10), "가" * 10)
        self.assertEqual(inbox.ext("가" * 10, 10), "가" * 10)
        self.assertEqual(inbox.safe_text("가" * 11, 10), "가" * 9 + "…")
        self.assertEqual(inbox.ext("가" * 11, 10), "가" * 9 + "…")

    def test_ext_limit_and_none(self):
        self.assertEqual(inbox.ext(None), "")
        self.assertEqual(len(inbox.ext("가" * 500, 40)), 40)

    def test_safe_text_is_idempotent_on_ext_output(self):
        once = inbox.ext("[x] @y <z> &w ::q `c`")
        self.assertEqual(inbox.safe_text(once), once)

    def test_safe_url_allows_only_plain_github_and_blogger_https_links(self):
        for good in (f"{URL}/pull/15", f"{URL}/settings/secrets/actions", "https://www.blogger.com/", f"{URL}/actions/runs/1"):
            self.assertEqual(inbox.safe_url(good), good)
        for bad in ("http://github.com/x/y", "https://evil.example/x", "javascript:alert(1)", f"{URL}/a b", f"{URL}/a)b",
                    f"{URL}/a<b", "https://github.com.evil.example/x", "", None, "https://github.com"):
            self.assertEqual(inbox.safe_url(bad), "", bad)

    def test_is_truthy(self):
        for yes in ("1", "true", "TRUE", " yes ", "On"):
            self.assertTrue(inbox.is_truthy(yes), yes)
        for no in ("", "0", "false", "no", "off", None, "tru", "2"):
            self.assertFalse(inbox.is_truthy(no), no)


class TimeTest(unittest.TestCase):
    def test_parse_time_accepts_github_and_history_formats(self):
        self.assertEqual(inbox.parse_time("2026-10-25T06:09:49Z"), datetime(2026, 10, 25, 6, 9, 49, tzinfo=timezone.utc))
        self.assertEqual(inbox.parse_time("2026-10-21T01:03:39.091290+09:00").astimezone(timezone.utc),
                         datetime(2026, 10, 20, 16, 3, 39, 91290, tzinfo=timezone.utc))
        naive = inbox.parse_time(datetime(2026, 1, 1))
        self.assertEqual(naive.tzinfo, timezone.utc)

    def test_parse_time_rejects_garbage_without_raising(self):
        for bad in (None, "", "  ", "어제", "2026-13-45T00:00:00Z", 12345, "2026-10-25"):
            self.assertIsNone(inbox.parse_time(bad), bad)

    def test_fmt_kst_converts_utc_to_korea_time(self):
        self.assertEqual(inbox.fmt_kst(datetime(2026, 10, 25, 6, 0, tzinfo=timezone.utc)), "2026-10-25 15:00 KST")


class DocumentedDefaultsTest(unittest.TestCase):
    """docs/OPS_INBOX.md 에 적힌 기본값이 코드와 같은지 — 값을 바꾸면 문서와 이 표를 함께 고친다."""

    def test_defaults(self):
        expected = {"RUN_WINDOW_HOURS": 48, "RUNS_PER_FILE": 10, "ANNOTATION_RUNS_PER_FILE": 3, "PR_STALE_DAYS": 3, "DRAFT_WAIT_DAYS": 7,
                    "APPROVAL_ITEMS_MAX": 5, "WARNING_MESSAGES_MAX": 3, "BODY_LIMIT": 60000, "SUMMARY_LIMIT": 500000,
                    "COMMENT_ITEMS_MAX": 8, "MARKER_IDS_MAX": 80, "TITLE_MAX": 110, "DETAIL_MAX": 420, "HINT_MAX": 260, "MESSAGE_MAX": 150}
        for name, value in expected.items():
            self.assertEqual(getattr(inbox, name), value, name)
        self.assertEqual((inbox.ISSUE_TITLE, inbox.LABEL, inbox.OWN_WORKFLOW), ("[운영] 확인 필요 모음", "ops-inbox", "ops-inbox.yml"))
        self.assertLess(inbox.BODY_LIMIT, 65000)               # GitHub 이슈 본문 한도(65,536자) 안에서 표식·여유를 남긴다
        self.assertRegex(inbox.LABEL_COLOR, "^[0-9a-f]{6}$")
        self.assertLessEqual(len(inbox.LABEL_DESCRIPTION), 100)
        self.assertFalse(inbox.ISSUE_TITLE.startswith(inbox.WATCHDOG_PREFIX))


class ItemTest(unittest.TestCase):
    def test_id_and_level_are_validated(self):
        inbox.Item("pr:15:ready", "action", "t")
        for bad_id in ("", "PR:15", "pr 15", "pr:15,x", "a-b", "x" * 81, "pr:15;x"):
            with self.assertRaises(ValueError, msg=bad_id):
                inbox.Item(bad_id, "action", "t")
        with self.assertRaises(ValueError):
            inbox.Item("x", "urgent", "t")

    def test_item_is_immutable(self):
        item = inbox.Item("x", "info", "t")
        with self.assertRaises(Exception):
            item.title = "y"


# ----------------------------------------------------------------------------
# 규칙 1: 워치독 이슈
# ----------------------------------------------------------------------------
class WatchdogItemsTest(unittest.TestCase):
    def build(self, issues):
        return inbox.watchdog_items(issues, URL)

    def test_critical_is_action_and_warning_is_check(self):
        items = by_id(self.build([h.make_watchdog(9), h.make_watchdog(10, "blogger_macat", "UNPUBLISHED", "warning", "초안만 생성됨")]))
        self.assertEqual(items["watchdog:9"].level, "action")
        self.assertEqual(items["watchdog:10"].level, "check")

    def test_item_shows_title_message_link_and_start_time(self):
        item = one(self.build([h.make_watchdog(9, created="2026-10-23T08:46:51Z")]))
        self.assertIn("chance: STALE", item.title)
        self.assertNotIn("[Watchdog]", item.title)
        self.assertIn("42시간 경과", item.detail)
        self.assertTrue(item.detail.startswith("심각"))
        self.assertEqual(item.url, f"{URL}/issues/9")
        self.assertEqual(item.since, datetime(2026, 10, 23, 8, 46, 51, tzinfo=timezone.utc))
        self.assertIn("자동으로 닫", item.hint)

    def test_warning_detail_is_labelled_warning(self):
        self.assertTrue(one(self.build([h.make_watchdog(10, severity="warning")])).detail.startswith("경고"))

    def test_unknown_severity_defaults_to_action(self):
        issue = h.make_issue(11, "[Watchdog] chance: X", "심각도를 알 수 없는 본문")
        self.assertEqual(one(self.build([issue])).level, "action")

    def test_severity_is_read_case_insensitively(self):
        issue = h.make_issue(12, "[Watchdog] chance: X", "**심각도**: WARNING\n\n문제")
        self.assertEqual(one(self.build([issue])).level, "check")

    def test_non_watchdog_issues_and_pull_requests_are_ignored(self):
        issues = [h.make_issue(1, "사람이 쓴 이슈", "본문"), h.make_issue(2, "[Watchdog] x: Y", "심각도: critical", pull=True),
                  h.make_issue(3, "워치독 [Watchdog] 중간", "x")]
        self.assertEqual(self.build(issues), [])

    def test_stranger_cannot_forge_a_watchdog_item(self):
        forged = h.make_issue(5, "[Watchdog] chance: STALE", "**심각도**: critical", login="stranger", assoc="NONE")
        self.assertEqual(self.build([forged]), [])
        for assoc in ("OWNER", "MEMBER", "COLLABORATOR"):
            ok = h.make_issue(6, "[Watchdog] chance: STALE", "**심각도**: critical", login="someone", assoc=assoc)
            self.assertEqual(len(self.build([ok])), 1, assoc)

    def test_external_text_in_title_and_message_is_neutralised(self):
        issue = h.make_watchdog(7, blog="@all", code="<b>X</b>", message="@victim ::error::fake\n[링크](https://evil.example)")
        item = one(self.build([issue]))
        for text in (item.title, item.detail):
            self.assertNotIn("@", text)
            self.assertNotIn("<", text)
            self.assertNotIn("::", text)
            self.assertNotIn("](", text)

    def test_message_is_found_when_it_is_the_last_paragraph(self):
        issue = h.make_issue(13, "[Watchdog] x: Y", "**심각도**: warning\n\n마지막 문단이 설명입니다")
        self.assertIn("마지막 문단이 설명입니다", one(self.build([issue])).detail)

    def test_message_without_following_paragraph_falls_back(self):
        issue = h.make_issue(8, "[Watchdog] x: Y", "**심각도**: critical", labels=("watchdog",))
        self.assertIn("이슈 본문을 확인하세요", one(self.build([issue])).detail)

    def test_garbage_entries_do_not_crash(self):
        self.assertEqual(self.build([None, 5, "x", {}, {"title": "[Watchdog] a: B"}, {"title": "[Watchdog] a: B", "number": "7"}]), [])


# ----------------------------------------------------------------------------
# 규칙 2: 열린 PR
# ----------------------------------------------------------------------------
class SummarizeChecksTest(unittest.TestCase):
    def test_all_success_is_pass_and_skipped_neutral_count_as_passing(self):
        self.assertEqual(inbox.summarize_checks([h.make_check("a"), h.make_check("b")]), "pass")
        self.assertEqual(inbox.summarize_checks([h.make_check("a"), h.make_check("b", "skipped"), h.make_check("c", "neutral")]), "pass")

    def test_any_failure_wins_over_pending_and_success(self):
        for bad in ("failure", "timed_out", "startup_failure"):
            runs = [h.make_check("a"), h.make_check("b", bad), h.make_check("c", None, "in_progress")]
            self.assertEqual(inbox.summarize_checks(runs), "fail", bad)

    def test_unfinished_runs_are_pending(self):
        for status in ("queued", "in_progress", "waiting", "pending"):
            self.assertEqual(inbox.summarize_checks([h.make_check("a"), h.make_check("b", None, status)]), "pending", status)
        self.assertEqual(inbox.summarize_checks([h.make_check("a", "action_required")]), "pending")
        self.assertEqual(inbox.summarize_checks([h.make_check("a", None)]), "pending")   # 끝났다는데 결론이 없다

    def test_empty_or_only_cancelled_is_none(self):
        self.assertEqual(inbox.summarize_checks([]), "none")
        self.assertEqual(inbox.summarize_checks(None), "none")
        self.assertEqual(inbox.summarize_checks([h.make_check("a", "cancelled"), h.make_check("b", "stale")]), "none")
        self.assertEqual(inbox.summarize_checks([h.make_check("a", "skipped")]), "none")

    def test_cancelled_next_to_success_is_still_pass(self):
        self.assertEqual(inbox.summarize_checks([h.make_check("a"), h.make_check("b", "cancelled")]), "pass")

    def test_non_dict_entries_are_ignored(self):
        self.assertEqual(inbox.summarize_checks([None, "x", h.make_check("a")]), "pass")


class NormalizePullTest(unittest.TestCase):
    def test_flattens_github_objects(self):
        raw = h.make_pull_raw(15, "제목", login="bot[bot]", assoc="NONE", ref="ai/x", created="2026-10-25T05:57:16Z")
        pr = inbox.normalize_pull(raw, {"mergeable": True, "mergeable_state": "CLEAN"}, [h.make_check("a")])
        self.assertEqual((pr["number"], pr["title"], pr["author"], pr["association"], pr["head_ref"]),
                         (15, "제목", "bot[bot]", "NONE", "ai/x"))
        self.assertEqual((pr["ci"], pr["mergeable"], pr["mergeable_state"], pr["fork"], pr["draft"]), ("pass", True, "clean", False, False))

    def test_fork_is_detected_by_head_repo(self):
        self.assertTrue(inbox.normalize_pull(h.make_pull_raw(1, fork=True))["fork"])
        raw = h.make_pull_raw(2)
        raw["head"]["repo"] = None      # 삭제된 포크
        self.assertTrue(inbox.normalize_pull(raw)["fork"])
        self.assertFalse(inbox.normalize_pull(h.make_pull_raw(3))["fork"])

    def test_missing_pieces_become_unknown_not_errors(self):
        pr = inbox.normalize_pull(h.make_pull_raw(4))
        self.assertEqual((pr["ci"], pr["mergeable"], pr["mergeable_state"]), ("unknown", None, ""))
        pr = inbox.normalize_pull(h.make_pull_raw(5), {"mergeable": "yes"}, [])
        self.assertEqual((pr["ci"], pr["mergeable"]), ("none", None))
        self.assertIsNone(inbox.normalize_pull(None)["number"])
        self.assertEqual(inbox.normalize_pull(h.make_pull_raw(6), error="HTTP 500")["error"], "HTTP 500")


class PullItemsTest(unittest.TestCase):
    def build(self, *pulls, now=NOW):
        return inbox.pull_items(list(pulls), now, URL)

    def test_ci_pass_and_no_conflict_is_action_ready(self):
        item = one(self.build(h.make_pull(15, title="워치독 보강")))
        self.assertEqual((item.id, item.level), ("pr:15:ready", "action"))
        self.assertIn("병합하면 됩니다", item.title)
        self.assertIn("워치독 보강", item.title)
        self.assertEqual(item.url, f"{URL}/pull/15")
        self.assertIn("Merge pull request", item.hint)

    def test_ci_failure_is_action(self):
        item = one(self.build(h.make_pull(16, ci="fail", mergeable=True, state="unstable")))
        self.assertEqual((item.id, item.level), ("pr:16:ci_fail", "action"))
        self.assertIn("검사(CI) 실패", item.title)

    def test_conflict_is_action_and_comes_before_ci_failure(self):
        for kwargs in ({"mergeable": False, "state": "dirty"}, {"mergeable": None, "state": "dirty"}, {"mergeable": False, "state": "clean"}):
            for ci in ("pass", "fail", "pending"):
                item = one(self.build(h.make_pull(17, ci=ci, **kwargs)))
                self.assertEqual((item.id, item.level), ("pr:17:conflict", "action"), (kwargs, ci))
        self.assertIn("충돌", one(self.build(h.make_pull(17, mergeable=False, state="dirty"))).title)

    def test_running_ci_is_info_and_waits(self):
        item = one(self.build(h.make_pull(18, ci="pending", mergeable=None, state="unknown")))
        self.assertEqual((item.id, item.level), ("pr:18:pending", "info"))

    def test_blocked_by_repository_rules_is_check(self):
        item = one(self.build(h.make_pull(19, ci="pass", mergeable=True, state="blocked")))
        self.assertEqual((item.id, item.level), ("pr:19:blocked", "check"))

    def test_no_ci_record_is_check_when_mergeable_and_info_when_unknown(self):
        self.assertEqual(one(self.build(h.make_pull(20, ci="none", mergeable=True))).id, "pr:20:no_ci")
        self.assertEqual(one(self.build(h.make_pull(20, ci="none", mergeable=True))).level, "check")
        unknown = one(self.build(h.make_pull(21, ci="none", mergeable=None, state="")))
        self.assertEqual((unknown.id, unknown.level), ("pr:21:unknown", "info"))

    def test_mergeable_not_computed_yet_is_info_even_when_ci_passes(self):
        item = one(self.build(h.make_pull(22, ci="pass", mergeable=None, state="unknown")))
        self.assertEqual((item.id, item.level), ("pr:22:unknown", "info"))

    def test_unknown_ci_is_info(self):
        item = one(self.build(h.make_pull(23, ci="unknown", mergeable=True)))
        self.assertEqual((item.id, item.level), ("pr:23:unknown", "info"))

    def test_lookup_error_is_a_check_item_that_names_the_reason(self):
        pr = inbox.normalize_pull(h.make_pull_raw(24), None, None, error="HTTP 502")
        item = one(self.build(pr))
        self.assertEqual((item.id, item.level), ("pr:24:unknown", "check"))
        self.assertIn("HTTP 502", item.detail)

    def test_the_lookup_failure_text_is_used_only_for_a_failed_unknown_state(self):
        plain = one(self.build(h.make_pull(40, ci="pass", mergeable=None, state="unknown")))
        self.assertIn("병합 가능 여부를 아직 알 수 없습니다", plain.detail)
        self.assertNotIn("조회하지 못했습니다", plain.detail)
        failed_stranger = inbox.normalize_pull(h.make_pull_raw(41, fork=True, assoc="NONE"), None, None, error="HTTP 502")
        item = one(self.build(failed_stranger))
        self.assertEqual(item.id, "pr:41:external")
        self.assertIn("직접 읽기", item.detail)
        self.assertNotIn("조회하지 못했습니다", item.detail)

    def test_draft_pull_requests_are_skipped(self):
        self.assertEqual(self.build(h.make_pull(25, draft=True)), [])

    def test_bots_and_ai_branches_follow_the_same_rule(self):
        for login, kind, ref in (("github-actions[bot]", "Bot", "issue-edit/12-categories"), ("dependabot[bot]", "Bot", "dependabot/pip/x"),
                                 ("Copilot", "Bot", "copilot/fix"), ("octo", "User", "ai/claude/x")):
            item = one(self.build(h.make_pull(26, login=login, user_type=kind, ref=ref, assoc="CONTRIBUTOR")))
            self.assertEqual((item.id, item.level), ("pr:26:ready", "action"), login)
            self.assertIn(inbox.ext(ref, 50), item.detail)

    def test_pull_request_from_a_stranger_fork_is_never_called_ready(self):
        item = one(self.build(h.make_pull(27, fork=True, assoc="NONE", login="stranger")))
        self.assertEqual((item.id, item.level), ("pr:27:external", "check"))
        self.assertNotIn("병합하면 됩니다", item.title)
        self.assertIn("직접 읽기", item.detail)

    def test_pull_request_from_a_trusted_fork_author_follows_normal_rules(self):
        for assoc in ("OWNER", "MEMBER", "COLLABORATOR"):
            self.assertEqual(one(self.build(h.make_pull(28, fork=True, assoc=assoc))).id, "pr:28:ready", assoc)

    def test_old_pull_requests_are_raised_to_check_and_marked(self):
        created = NOW - timedelta(days=3, seconds=1)
        pending = one(self.build(h.make_pull(29, ci="pending", mergeable=None, created=h.iso(created))))
        self.assertEqual((pending.id, pending.level), ("pr:29:pending", "check"))
        self.assertIn("3일 넘게 열려 있음", pending.detail)
        ready = one(self.build(h.make_pull(30, created=h.iso(created))))
        self.assertEqual(ready.level, "action")           # 이미 action 이면 그대로
        self.assertIn("3일 넘게 열려 있음", ready.detail)

    def test_exactly_three_days_is_not_old_yet(self):
        item = one(self.build(h.make_pull(31, ci="pending", mergeable=None, created=h.iso(NOW - timedelta(days=3)))))
        self.assertEqual(item.level, "info")
        self.assertNotIn("넘게 열려", item.detail)

    def test_missing_created_time_is_not_treated_as_old(self):
        pr = h.make_pull(32, ci="pending", mergeable=None)
        pr["created_at"] = None
        item = one(self.build(pr))
        self.assertEqual(item.level, "info")
        self.assertIsNone(item.since)

    def test_since_is_the_opened_time(self):
        item = one(self.build(h.make_pull(33, created="2026-10-25T05:57:16Z")))
        self.assertEqual(item.since, datetime(2026, 10, 25, 5, 57, 16, tzinfo=timezone.utc))

    def test_external_text_is_neutralised_in_title_and_author(self):
        item = one(self.build(h.make_pull(34, title="@owner [x](http://e.example) <script>", login="ev<il", ref="::b")))
        for text in (item.title, item.detail):
            for raw in ("@", "<", "::", "](", "["):
                self.assertNotIn(raw, text, raw)

    def test_bot_login_is_shown_without_brackets(self):
        item = one(self.build(h.make_pull(35, login="dependabot[bot]", user_type="Bot")))
        self.assertIn("dependabot (bot)", item.detail)

    def test_pull_requests_without_a_number_are_skipped(self):
        broken = h.make_pull(36)
        broken["number"] = None
        self.assertEqual(self.build(broken, None, "x"), [])


# ----------------------------------------------------------------------------
# 규칙 3: 워크플로 실행
# ----------------------------------------------------------------------------
def runs_for(file, *runs):
    return {file: list(runs)}


class RunFailureTest(unittest.TestCase):
    def build(self, runs_by_file, annotations=None):
        return inbox.run_items(runs_by_file, annotations or {}, NOW, URL)

    def test_latest_completed_failure_is_action_with_link(self):
        runs = runs_for("chanceblog.yml", h.make_run(2, ago(hours=1), "failure"), h.make_run(1, ago(hours=4), "success"))
        item = one(self.build(runs))
        self.assertEqual((item.id, item.level), ("run:chanceblog.yml:failed", "action"))
        self.assertEqual(item.url, f"{URL}/actions/runs/2")
        self.assertIn("Chance 글 작성", item.title)
        self.assertIn("chanceblog.yml", item.detail)

    def test_failure_followed_by_success_is_resolved(self):
        runs = runs_for("chanceblog.yml", h.make_run(2, ago(hours=1), "success"), h.make_run(1, ago(hours=4), "failure"))
        self.assertEqual(self.build(runs), [])

    def test_timed_out_and_startup_failure_count_as_failures(self):
        for conclusion, word in (("timed_out", "시간 초과"), ("startup_failure", "시작 실패")):
            item = one(self.build(runs_for("a.yml", h.make_run(1, ago(hours=1), conclusion))))
            self.assertEqual(item.level, "action", conclusion)
            self.assertIn(word, item.detail)

    def test_cancelled_skipped_and_neutral_runs_are_ignored_when_picking_the_latest(self):
        for ignored in ("cancelled", "skipped", "neutral", "stale"):
            runs = runs_for("a.yml", h.make_run(3, ago(minutes=30), ignored), h.make_run(2, ago(hours=1), "failure"))
            self.assertEqual(one(self.build(runs)).level, "action", ignored)         # 취소 앞에 있어도 실패는 그대로
            runs = runs_for("a.yml", h.make_run(3, ago(minutes=30), ignored), h.make_run(2, ago(hours=1), "success"))
            self.assertEqual(self.build(runs), [], ignored)

    def test_runs_still_in_progress_do_not_hide_a_failure_or_create_one(self):
        runs = runs_for("a.yml", h.make_run(3, ago(minutes=5), None, "in_progress"), h.make_run(2, ago(hours=1), "failure"))
        self.assertEqual(one(self.build(runs)).id, "run:a.yml:failed")
        self.assertEqual(self.build(runs_for("a.yml", h.make_run(3, ago(minutes=5), None, "queued"))), [])

    def test_failure_streak_counts_and_starts_at_the_first_failure(self):
        runs = runs_for("a.yml", h.make_run(4, ago(hours=1), "failure"), h.make_run(3, ago(hours=3), "timed_out"),
                        h.make_run(2, ago(hours=5), "failure"), h.make_run(1, ago(hours=7), "success"),
                        h.make_run(0, ago(hours=9), "failure"))
        item = one(self.build(runs))
        self.assertIn("연속 3회", item.detail)
        self.assertEqual(item.since, NOW - timedelta(hours=5))

    def test_two_failures_in_a_row_are_already_a_streak(self):
        runs = runs_for("a.yml", h.make_run(2, ago(hours=1), "failure"), h.make_run(1, ago(hours=3), "failure"))
        item = one(self.build(runs))
        self.assertIn("연속 2회", item.detail)
        self.assertEqual(item.since, NOW - timedelta(hours=3))

    def test_single_failure_has_no_streak_text(self):
        item = one(self.build(runs_for("a.yml", h.make_run(1, ago(hours=1), "failure"))))
        self.assertNotIn("연속", item.detail)
        self.assertEqual(item.since, NOW - timedelta(hours=1))

    def test_input_order_does_not_matter(self):
        newest, older = h.make_run(2, ago(hours=1), "failure"), h.make_run(1, ago(hours=9), "success")
        self.assertEqual(self.build(runs_for("a.yml", older, newest)), self.build(runs_for("a.yml", newest, older)))

    def test_runs_outside_the_48_hour_window_are_ignored(self):
        self.assertEqual(self.build(runs_for("a.yml", h.make_run(1, ago(hours=48, seconds=1), "failure"))), [])
        self.assertEqual(len(self.build(runs_for("a.yml", h.make_run(1, ago(hours=48), "failure")))), 1)

    def test_old_failure_does_not_resurface_behind_a_new_success(self):
        runs = runs_for("a.yml", h.make_run(2, ago(hours=1), "success"), h.make_run(1, ago(hours=50), "failure"))
        self.assertEqual(self.build(runs), [])

    def test_this_workflows_own_runs_are_excluded(self):
        runs = {inbox.OWN_WORKFLOW: [h.make_run(1, ago(hours=1), "failure")], "a.yml": [h.make_run(2, ago(hours=1), "failure")]}
        self.assertEqual([i.id for i in self.build(runs)], ["run:a.yml:failed"])

    def test_each_workflow_file_is_judged_separately_and_ids_are_valid(self):
        runs = {"blogger.yml": [h.make_run(1, ago(hours=1), "failure")], "pr-scope-check.yml": [h.make_run(2, ago(hours=1), "failure")],
                "pages.yml": [h.make_run(3, ago(hours=1), "success")]}
        items = self.build(runs)
        self.assertEqual(sorted(i.id for i in items), ["run:blogger.yml:failed", "run:pr_scope_check.yml:failed"])

    def test_workflow_name_falls_back_to_the_file_name(self):
        run = h.make_run(1, ago(hours=1), "failure")
        run["name"] = None
        self.assertIn("a.yml", one(self.build(runs_for("a.yml", run))).title)

    def test_garbage_runs_do_not_crash(self):
        self.assertEqual(self.build({"a.yml": [None, 5, {}, {"created_at": "x"}, {"created_at": ago(hours=1)}]}), [])
        self.assertEqual(self.build({"a.yml": None}), [])

    def test_failure_link_uses_the_numeric_run_id_not_an_api_url(self):
        run = h.make_run(7, ago(hours=1), "failure")
        run["html_url"] = "https://evil.example/phish"
        self.assertEqual(one(self.build(runs_for("a.yml", run))).url, f"{URL}/actions/runs/7")


class RunWarningTest(unittest.TestCase):
    FILE = "chanceblog.yml"

    def build(self, runs, annotations):
        return inbox.run_items({self.FILE: runs}, annotations, NOW, URL)

    def warn_item(self, items):
        return by_id(items)[f"run:{self.FILE}:warn"]

    def test_warning_on_a_successful_run_is_a_check_item(self):
        runs = [h.make_run(1, ago(hours=1))]
        item = self.warn_item(self.build(runs, {1: [h.make_annotation("[SKIP] code=ALL_REJECTED 후보 전부 탈락")]}))
        self.assertEqual(item.level, "check")
        self.assertIn("ALL_REJECTED", item.detail)
        self.assertEqual(item.url, f"{URL}/actions/runs/1")
        self.assertIn("성공 실행 1회 중 1회", item.detail)
        self.assertIn("Chance 글 작성", item.title)

    def test_only_warning_level_counts(self):
        runs = [h.make_run(1, ago(hours=1))]
        for level in ("notice", "failure"):
            self.assertEqual(self.build(runs, {1: [h.make_annotation("문구", level)]}), [], level)

    def test_runs_without_scanned_annotations_produce_nothing(self):
        self.assertEqual(self.build([h.make_run(1, ago(hours=1))], {}), [])
        self.assertEqual(self.build([h.make_run(1, ago(hours=1))], {1: []}), [])

    def test_failed_runs_are_not_scanned_for_warnings(self):
        items = self.build([h.make_run(1, ago(hours=1), "failure")], {1: [h.make_annotation("경고 문구")]})
        self.assertEqual([i.id for i in items], [f"run:{self.FILE}:failed"])

    def test_distinct_messages_are_folded_and_limited_to_three(self):
        runs = [h.make_run(i, ago(hours=i)) for i in range(1, 6)]
        notes = {i: [h.make_annotation(f"문구 {i}\n줄바꿈 ::error::위조")] for i in range(1, 6)}
        notes[2].append(h.make_annotation("문구 1 줄바꿈 : :error: :위조"))      # 접으면 문구 1 과 같은 문구(중복)
        item = self.warn_item(self.build(runs, notes))
        self.assertEqual(item.detail.count("“"), 3)
        self.assertNotIn("문구 4", item.detail)
        self.assertNotIn("\n", item.detail)
        self.assertNotIn("::", item.detail)
        self.assertIn("성공 실행 5회 중 5회", item.detail)

    def test_same_message_on_many_runs_is_listed_once(self):
        runs = [h.make_run(i, ago(hours=i)) for i in range(1, 4)]
        item = self.warn_item(self.build(runs, {i: [h.make_annotation("같은 경고")] for i in range(1, 4)}))
        self.assertEqual(item.detail.count("같은 경고"), 1)
        self.assertIn("3회 중 3회", item.detail)

    def test_link_points_to_the_newest_run_with_a_warning_and_since_to_the_oldest(self):
        runs = [h.make_run(3, ago(hours=1)), h.make_run(2, ago(hours=3)), h.make_run(1, ago(hours=5))]
        item = self.warn_item(self.build(runs, {3: [], 2: [h.make_annotation("가")], 1: [h.make_annotation("나")]}))
        self.assertEqual(item.url, f"{URL}/actions/runs/2")
        self.assertEqual(item.since, NOW - timedelta(hours=5))
        self.assertIn("3회 중 2회", item.detail)

    def test_real_warnings_next_to_noise_still_show(self):
        runs = [h.make_run(1, ago(hours=1))]
        items = by_id(self.build(runs, {1: [h.make_annotation(REAL_NODE_WARNING), h.make_annotation("진짜 경고")]}))
        self.assertIn("진짜 경고", items[f"run:{self.FILE}:warn"].detail)
        self.assertNotIn("Node.js", items[f"run:{self.FILE}:warn"].detail)
        self.assertIn("run:platform_notice", items)

    def test_failure_level_annotations_are_ignored_even_when_they_look_like_platform_notices(self):
        self.assertEqual(self.build([h.make_run(1, ago(hours=1))], {1: [h.make_annotation(REAL_NODE_WARNING, "failure")]}), [])

    def test_run_totals_count_only_the_runs_whose_annotations_were_read(self):
        runs = [h.make_run(3, ago(hours=1)), h.make_run(2, ago(hours=3)), h.make_run(1, ago(hours=5))]
        item = self.warn_item(self.build(runs, {2: [h.make_annotation("경고")]}))
        self.assertIn("성공 실행 1회 중 1회", item.detail)
        item = self.warn_item(self.build(runs, {3: [], 2: [h.make_annotation("경고")], 1: []}))
        self.assertIn("성공 실행 3회 중 1회", item.detail)

    def test_empty_annotation_messages_are_skipped_and_title_is_the_fallback(self):
        runs = [h.make_run(1, ago(hours=1))]
        self.assertEqual(self.build(runs, {1: [h.make_annotation("   ")]}), [])
        item = self.warn_item(self.build(runs, {1: [h.make_annotation("", title="제목만 있음")]}))
        self.assertIn("제목만 있음", item.detail)

    def test_warning_text_is_neutralised_and_secrets_masked(self):
        token = "gh" + "p_" + "Z" * 36
        text = f"@everyone <b>x</b> [a](http://e.example) 토큰 {token}"
        item = self.warn_item(self.build([h.make_run(1, ago(hours=1))], {1: [h.make_annotation(text)]}))
        for raw in ("@", "<", "](", token):
            self.assertNotIn(raw, item.detail, raw)

    def test_long_warning_is_clipped(self):
        item = self.warn_item(self.build([h.make_run(1, ago(hours=1))], {1: [h.make_annotation("가" * 2000)]}))
        self.assertLess(len(item.detail), 400)
        self.assertIn("…", item.detail)

    def test_runs_outside_the_window_are_not_used_for_warnings(self):
        runs = [h.make_run(1, ago(hours=60))]
        self.assertEqual(self.build(runs, {1: [h.make_annotation("오래된 경고")]}), [])

    def test_own_workflow_warnings_are_ignored(self):
        items = inbox.run_items({inbox.OWN_WORKFLOW: [h.make_run(1, ago(hours=1))]}, {1: [h.make_annotation("자기 경고")]}, NOW, URL)
        self.assertEqual(items, [])


class PlatformNoticeTest(unittest.TestCase):
    """GitHub 가 거의 모든 실행에 붙이는 안내성 주석(실제 문구 2개)은 check 가 아니라 info 한 줄로 합쳐 보여 주고 알림 대상이 아니다."""

    # PLATFORM_NOISE 의 각 정규식에만 걸리는 문구(순서가 정규식 순서와 같다)와, 걸리면 안 되는 우리 쪽 문구
    ONLY_PATTERN_SAMPLES = ("forced to run on Node.js 24", "The ubuntu-latest label will migrate to Ubuntu 26 beginning October 19, 2026.",
                            "자세한 내용: https://github.blog/changelog/2026-01-01-news/", "자세한 내용: https://github.com/actions/runner-images/issues/1",
                            "The `set-output` command is deprecated and will be disabled soon.", "The ubuntu-20.04 image is deprecated")
    OWN_WARNINGS = ("[SKIP] code=ALL_REJECTED 후보는 있었으나 전부 탈락", "[SKIP] code=NO_CANDIDATES lane=technology",
                    "Gemini 모델 gemini-3.5-flash is deprecated — 레지스트리의 모델 목록을 고치세요", "게시 시크릿 미등록: blog_id, client_id",
                    "[blogger_macat] 고를 주제가 없습니다(seed_exhausted)", "노드 20 은 한글이라 걸리지 않는다")

    def world(self, files=("chanceblog.yml", "blogger.yml", "watchdog.yml"), runs_each=2, messages=None, level_of=None):
        messages = messages or [(REAL_NODE_WARNING, "warning"), (REAL_UBUNTU_NOTICE, "notice")]
        runs_by_file, annotations, run_id = {}, {}, 0
        for file in files:
            runs_by_file[file] = []
            for n in range(runs_each):
                run_id += 1
                runs_by_file[file].append(h.make_run(run_id, ago(hours=1 + n + run_id * 0.01), name=f"{file} 이름", path=f".github/workflows/{file}"))
                annotations[run_id] = [h.make_annotation(text, level) for text, level in messages]
        return runs_by_file, annotations

    def items(self, **kw):
        runs_by_file, annotations = self.world(**kw)
        return inbox.run_items(runs_by_file, annotations, NOW, URL)

    def test_both_real_messages_are_platform_notices(self):
        for text in (REAL_NODE_WARNING, REAL_UBUNTU_NOTICE):
            self.assertTrue(inbox._is_noise(text), text)

    def test_they_become_exactly_one_info_item_and_no_check_items(self):
        item = one(self.items())
        self.assertEqual((item.id, item.level), ("run:platform_notice", "info"))
        self.assertIn("플랫폼 경고 2종", item.title)
        self.assertIn("액션 버전 갱신 필요", item.title)
        self.assertIn("당장은 발행에 영향 없음", item.title)

    def test_the_item_names_the_actions_the_workflows_and_links_the_newest_run(self):
        item = one(self.items())
        self.assertIn("액션: actions/checkout v4, actions/setup-python v5 ·", item.detail)       # 문장 끝 마침표는 버전이 아니고, @ 는 멘션으로 읽힐 수 있어 공백으로 쓴다
        self.assertNotIn("@", item.detail)
        for name in ("chanceblog.yml 이름", "blogger.yml 이름", "watchdog.yml 이름"):
            self.assertIn(name, item.detail)
        self.assertEqual(item.url, f"{URL}/actions/runs/1")                  # 가장 최근에 시작한 실행(1시간 전 + run_id 0.01 시간)
        self.assertIn("AI에게", item.hint)
        self.assertIn("지금 할 일은 없습니다", item.hint)

    def test_it_never_becomes_a_new_action_notification(self):
        runs_by_file, annotations = self.world()
        snap = inbox.Snapshot(now=NOW, repo=h.REPO, runs=runs_by_file, annotations=annotations)
        items = inbox.build_items(snap)
        self.assertEqual(inbox.action_ids(items), [])
        self.assertEqual(inbox.plan_notice(items, None), ([], []))
        self.assertEqual([i.level for i in items], ["info"])

    def test_the_same_messages_on_many_runs_and_workflows_count_once_each(self):
        self.assertIn("2종", one(self.items(files=("a.yml",), runs_each=1)).title)
        self.assertIn("2종", one(self.items(files=tuple(f"w{n}.yml" for n in range(8)), runs_each=3)).title)
        spaced = REAL_NODE_WARNING.replace(". ", ".\n   ")           # 줄바꿈·공백만 다른 같은 문구는 같은 종류
        item = one(self.items(messages=[(REAL_NODE_WARNING, "warning"), (spaced, "warning")]))
        self.assertIn("1종", item.title)

    def test_distinct_notices_are_counted_as_kinds(self):
        extra = ("The ubuntu-20.04 image is deprecated and will be removed", "warning")
        self.assertIn("3종", one(self.items(messages=[(REAL_NODE_WARNING, "warning"), (REAL_UBUNTU_NOTICE, "notice"), extra])).title)

    def test_actions_pinned_to_a_commit_show_the_short_hash(self):
        pinned = "Node.js 20 actions are deprecated: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02, actions/cache@v4."
        item = one(self.items(files=("a.yml",), runs_each=1, messages=[(pinned, "warning")]))
        self.assertIn("액션: actions/cache v4, actions/upload-artifact ea165f8 ·", item.detail)

    def test_without_an_action_name_it_is_called_a_platform_change_notice(self):
        item = one(self.items(messages=[(REAL_UBUNTU_NOTICE, "notice")]))
        self.assertIn("플랫폼 경고 1종 — 플랫폼 변경 예고", item.title)
        self.assertNotIn("액션:", item.detail)

    def test_only_platform_notices_are_collected_from_notice_level(self):
        ours = "[blogger_macat] 저장소 변수 PIPELINE_PAUSE 가 켜져 있어 이번 실행을 건너뜁니다."
        self.assertEqual(self.items(files=("a.yml",), runs_each=1, messages=[(ours, "notice")]), [])
        self.assertEqual(self.items(files=("a.yml",), runs_each=1, messages=[("정보 문구", "notice"), ("오류 문구", "failure")]), [])

    def test_our_own_warnings_stay_check_items_and_are_not_mistaken_for_platform_notices(self):
        for text in self.OWN_WARNINGS:
            items = by_id(self.items(files=("a.yml",), runs_each=1, messages=[(text, "warning")]))
            self.assertEqual(list(items), ["run:a.yml:warn"], text)
            self.assertEqual(items["run:a.yml:warn"].level, "check")

    def test_ambiguous_warnings_are_check_items_listed_once_across_runs(self):
        items = by_id(self.items(files=("a.yml",), runs_each=3, messages=[("애매한 경고 문구", "warning"), (REAL_NODE_WARNING, "warning")]))
        self.assertEqual(sorted(items), ["run:a.yml:warn", "run:platform_notice"])
        self.assertEqual(items["run:a.yml:warn"].detail.count("애매한 경고 문구"), 1)
        self.assertEqual(items["run:a.yml:warn"].level, "check")
        self.assertEqual(items["run:platform_notice"].level, "info")

    def test_exactly_four_workflows_need_no_remainder(self):
        item = one(self.items(files=tuple(f"w{n}.yml" for n in range(4)), runs_each=1))
        self.assertNotIn("외", item.detail.split("예:")[0])
        self.assertEqual(item.detail.count(" 이름"), 4)

    def test_workflow_names_are_limited_to_four_with_the_rest_counted(self):
        item = one(self.items(files=tuple(f"w{n}.yml" for n in range(6)), runs_each=1))
        self.assertIn("외 2개", item.detail)
        self.assertEqual(item.detail.count(" 이름"), 4)
        self.assertNotIn("외", one(self.items(files=("a.yml", "b.yml"), runs_each=1)).detail.split("예:")[0])

    def test_the_link_goes_to_the_newest_run_that_carried_a_platform_notice(self):
        old = h.make_run(1, ago(hours=9))
        new_clean = h.make_run(2, ago(hours=1))
        item = one(inbox.run_items({"a.yml": [new_clean, old]}, {1: [h.make_annotation(REAL_NODE_WARNING)], 2: [h.make_annotation("정보", "notice")]}, NOW, URL))
        self.assertEqual(item.url, f"{URL}/actions/runs/1")

    def test_each_pattern_is_pinned_by_a_sample_only_it_matches(self):
        self.assertEqual(len(self.ONLY_PATTERN_SAMPLES), len(inbox.PLATFORM_NOISE))
        for index, sample in enumerate(self.ONLY_PATTERN_SAMPLES):
            matched = [i for i, rx in enumerate(inbox.PLATFORM_NOISE) if rx.search(sample)]
            self.assertEqual(matched, [index], sample)

    def test_our_own_messages_match_no_pattern(self):
        for text in self.OWN_WARNINGS:
            self.assertFalse(inbox._is_noise(text), text)

    def test_the_pattern_list_and_levels_are_single_constants(self):
        self.assertIsInstance(inbox.PLATFORM_NOISE, tuple)
        self.assertEqual(inbox.PLATFORM_LEVELS, ("warning", "notice"))
        self.assertTrue(all(hasattr(rx, "search") for rx in inbox.PLATFORM_NOISE))

    def test_platform_text_is_masked_and_neutralised_like_any_external_text(self):
        token = "gh" + "p_" + "C" * 36
        text = f"Node.js 20 is deprecated @everyone <b>x</b> {token} ::error::z"
        item = one(self.items(files=("a.yml",), runs_each=1, messages=[(text, "warning")]))
        for raw in ("@", "<", "::", token):
            self.assertNotIn(raw, item.detail, raw)

    def test_failed_runs_are_not_scanned_so_their_notices_do_not_count(self):
        runs = {"a.yml": [h.make_run(1, ago(hours=1), "failure")]}
        items = inbox.run_items(runs, {1: [h.make_annotation(REAL_NODE_WARNING)]}, NOW, URL)
        self.assertEqual([i.id for i in items], ["run:a.yml:failed"])


class ApprovalItemsTest(unittest.TestCase):
    def pending(self, run_id, sha="b" * 40, created=None, **kw):
        return h.make_run(run_id, created or ago(hours=2), None, "action_required", event="pull_request", sha=sha, **kw)

    def test_waiting_run_is_action_with_approve_and_run_wording(self):
        run = self.pending(7, title="이슈 12 수정 PR", branch="copilot/fix", name="저장소 규칙·테스트 자동 검사")
        item = one(inbox.approval_items([run], URL))
        self.assertEqual((item.id, item.level), ("approve:bbbbbbb", "action"))
        self.assertIn("Approve and run", item.title)
        self.assertIn("이슈 12 수정 PR", item.title)
        self.assertIn("copilot/fix", item.detail)
        self.assertEqual(item.url, f"{URL}/actions/runs/7")
        self.assertIn("모르는 사람", item.hint)

    def test_conclusion_form_is_also_recognised(self):
        run = h.make_run(8, ago(hours=1), "action_required", "completed", sha="c" * 40)
        self.assertEqual(one(inbox.approval_items([run], URL)).id, "approve:ccccccc")

    def test_runs_of_the_same_commit_are_grouped_in_one_item(self):
        runs = [self.pending(1, name="검사 A"), self.pending(2, name="검사 B"), self.pending(3, name="검사 A")]
        item = one(inbox.approval_items(runs, URL))
        self.assertIn("검사 A", item.detail)
        self.assertIn("검사 B", item.detail)
        self.assertEqual(item.url, f"{URL}/actions/runs/1")

    def test_at_most_five_commits_then_a_summary_item(self):
        runs = [self.pending(i, sha=f"{i:x}" * 40 if i < 16 else "f" * 40, created=ago(hours=20 - i)) for i in range(1, 9)]
        items = inbox.approval_items(runs, URL)
        self.assertEqual(len(items), 6)
        self.assertEqual(items[-1].id, "approve:more")
        self.assertIn("3건 더", items[-1].title)
        self.assertEqual(len([i for i in items if i.id != "approve:more"]), 5)

    def test_at_most_three_workflow_names_are_listed_per_commit(self):
        runs = [self.pending(n, name=f"검사 {n}") for n in range(1, 5)]
        detail = one(inbox.approval_items(runs, URL)).detail
        self.assertEqual(sum(f"검사 {n}" in detail for n in range(1, 5)), 3)

    def test_exactly_five_waiting_commits_need_no_summary_item(self):
        items = inbox.approval_items([self.pending(n, sha=str(n) * 40) for n in range(1, 6)], URL)
        self.assertEqual(len(items), 5)
        self.assertNotIn("approve:more", [i.id for i in items])

    def test_oldest_waiting_commits_are_shown_first(self):
        runs = [self.pending(1, sha="1" * 40, created=ago(hours=1)), self.pending(2, sha="2" * 40, created=ago(hours=9))]
        self.assertEqual([i.id for i in inbox.approval_items(runs, URL)], ["approve:2222222", "approve:1111111"])

    def test_invalid_sha_falls_back_to_the_run_id(self):
        self.assertEqual(one(inbox.approval_items([self.pending(9, sha="not-a-sha")], URL)).id, "approve:r9")

    def test_other_runs_and_own_workflow_are_ignored(self):
        runs = [h.make_run(1, ago(hours=1), "success"), self.pending(2, path=f".github/workflows/{inbox.OWN_WORKFLOW}"), None, {"id": "x"},
                {"status": "action_required"}]
        self.assertEqual(inbox.approval_items(runs, URL), [])


# ----------------------------------------------------------------------------
# 규칙 4: 일시정지
# ----------------------------------------------------------------------------
class PauseItemsTest(unittest.TestCase):
    def test_paused_is_action_with_variables_page_link(self):
        item = one(inbox.pause_items(True, URL))
        self.assertEqual((item.id, item.level), ("pause", "action"))
        self.assertEqual(item.url, f"{URL}/settings/variables/actions")
        self.assertIn("해제 방법", item.title)
        self.assertIn("PIPELINE_PAUSE", item.hint)

    def test_not_paused_makes_nothing(self):
        self.assertEqual(inbox.pause_items(False, URL), [])


# ----------------------------------------------------------------------------
# 규칙 5: Blogger 상태(시크릿·정지·초안 대기) / 규칙 6: 현황
# ----------------------------------------------------------------------------
class EntryMomentTest(unittest.TestCase):
    def test_precision_levels(self):
        when, precision = inbox.entry_moment({"generated_at": "2026-10-24T15:57:51.427286+09:00"})
        self.assertEqual((precision, when.astimezone(KST).hour), ("time", 15))
        when, precision = inbox.entry_moment({"date": "2026-10-25", "slot": 9})
        self.assertEqual((precision, when), ("slot", datetime(2026, 10, 25, 9, tzinfo=KST)))
        when, precision = inbox.entry_moment({"date": "2026-10-25"})
        self.assertEqual((precision, when), ("date", datetime(2026, 10, 25, tzinfo=KST)))

    def test_generated_at_beats_date_and_slot(self):
        entry = {"generated_at": "2026-10-25T01:00:00Z", "date": "2026-10-01", "slot": 18}
        self.assertEqual(inbox.entry_moment(entry)[1], "time")

    def test_date_with_a_time_suffix_still_gives_the_day_and_slot_edges_are_valid(self):
        self.assertEqual(inbox.entry_moment({"date": "2026-10-25T09:00:00+09:00"}), (datetime(2026, 10, 25, tzinfo=KST), "date"))
        self.assertEqual(inbox.entry_moment({"date": "2026-10-25", "slot": 0}), (datetime(2026, 10, 25, 0, tzinfo=KST), "slot"))
        self.assertEqual(inbox.entry_moment({"date": "2026-10-25", "slot": 23}), (datetime(2026, 10, 25, 23, tzinfo=KST), "slot"))

    def test_bad_values_are_ignored(self):
        for entry in (None, "문자열", 5, {}, {"date": "어제"}, {"date": ""}, {"generated_at": "x"}):
            self.assertIsNone(inbox.entry_moment(entry), entry)
        for slot in (True, 24, -1, "9", 9.5):
            self.assertEqual(inbox.entry_moment({"date": "2026-10-25", "slot": slot})[1], "date", slot)


class BlogSecretsItemTest(unittest.TestCase):
    def build(self, history, blog=None, now=NOW):
        blog = blog or h.make_blog()
        return inbox.blog_items([blog], {blog["key"]: history}, now, URL)

    def unpublished(self, hours_ago, reason=h.SECRETS_REASON):
        return h.make_entry("generated_unpublished", ago(hours=hours_ago), [reason])

    def test_unpublished_with_secrets_reason_is_action_listing_secret_names(self):
        item = one(self.build([self.unpublished(30), self.unpublished(6)]))
        self.assertEqual((item.id, item.level), ("blogger:blogger_macat:secrets", "action"))
        self.assertIn("게시 설정(시크릿) 필요", item.title)
        for name in ("BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN"):
            self.assertIn(name, item.detail)
        self.assertNotIn("GEMINI_API_KEY", item.detail)
        self.assertEqual(item.url, f"{URL}/settings/secrets/actions")
        self.assertIn("HANDLER.md", item.hint)
        self.assertIn("2회 연속", item.detail)
        self.assertEqual(item.since, NOW - timedelta(hours=30))

    def test_only_roles_named_in_the_reason_are_listed_with_registry_names(self):
        reason = "[SECRETS] 게시 시크릿 미등록: client_secret, refresh_token"
        detail = one(self.build([self.unpublished(6, reason)])).detail
        self.assertIn("BLOGGER_CLIENT_SECRET, BLOGGER_REFRESH_TOKEN", detail)
        self.assertNotIn("BLOGGER_BLOG_ID", detail)

    def test_unknown_or_malformed_roles_are_dropped_and_never_echoed(self):
        reason = "[SECRETS] 게시 시크릿 미등록: nope, <b>x</b>, client_id, ..//etc"
        detail = one(self.build([self.unpublished(6, reason)])).detail
        self.assertIn("BLOGGER_CLIENT_ID", detail)
        for raw in ("nope", "<b>", "etc"):
            self.assertNotIn(raw, detail, raw)

    def test_no_parsable_roles_gives_a_generic_sentence(self):
        item = one(self.build([self.unpublished(6, "[SECRETS] 게시 시크릿 미등록: ")]))
        self.assertIn("게시용 시크릿이 비어 있습니다", item.detail)

    def test_only_names_never_values(self):
        item = one(self.build([self.unpublished(6)], h.make_blog(secrets={"blog_id": "BLOGGER_BLOG_ID"})))
        self.assertNotIn("=", " ".join((item.title, item.detail, item.hint, item.url)))
        self.assertIn("BLOGGER_BLOG_ID", item.detail)

    def test_a_blog_without_a_secrets_mapping_still_gets_a_generic_item(self):
        blog = h.make_blog()
        blog.pop("secrets")
        item = one(self.build([self.unpublished(6)], blog))
        self.assertIn("게시용 시크릿이 비어 있습니다", item.detail)

    def test_draft_mode_is_covered_too(self):
        self.assertEqual(one(self.build([self.unpublished(6)], h.make_blog(mode="draft"))).level, "action")

    def test_mode_off_is_info_with_registry_note_and_no_secrets_action(self):
        blog = h.make_blog(mode="off", note="OAuth 동의 화면을 프로덕션으로 바꾼 뒤 켠다")
        items = self.build([self.unpublished(6)], blog)
        item = one(items)
        self.assertEqual((item.id, item.level), ("blog:blogger_macat:off", "info"))
        self.assertIn("정지 중", item.title)
        self.assertIn("OAuth 동의 화면", item.detail)

    def test_mode_off_without_note_says_where_it_is_set(self):
        self.assertIn("mode=off", one(self.build([], h.make_blog(mode="off"))).detail)
        self.assertIn("underscore", one(self.build([], h.make_blog(mode="off", _note="underscore note"))).detail)

    def test_latest_publish_stage_entry_decides(self):
        resolved = [self.unpublished(30), h.make_entry("draft", ago(hours=6))]
        self.assertEqual(self.build(resolved), [])
        posted = [self.unpublished(30), h.make_entry("posted", ago(hours=6))]
        self.assertEqual(self.build(posted), [])
        failed = [self.unpublished(30), h.make_entry("publish_failed", ago(hours=6))]
        self.assertEqual(self.build(failed), [])

    def test_runs_that_never_reached_publishing_do_not_hide_the_secrets_problem(self):
        history = [self.unpublished(30), h.make_entry("rejected", ago(hours=20)), h.make_entry("skipped_no_topic", ago(hours=8)),
                   h.make_entry("llm_failed", ago(hours=2))]
        self.assertEqual(one(self.build(history)).id, "blogger:blogger_macat:secrets")

    def test_a_secrets_reason_on_a_latest_entry_that_is_not_unpublished_is_not_flagged(self):
        self.assertEqual(self.build([self.unpublished(30), h.make_entry("draft", ago(hours=6), [h.SECRETS_REASON])]), [])
        self.assertEqual(self.build([self.unpublished(30), h.make_entry("posted", ago(hours=6), [h.SECRETS_REASON])]), [])

    def test_secret_names_must_look_like_environment_variable_names(self):
        blog = h.make_blog(secrets={"blog_id": "bad value!", "client_id": "BLOGGER_CLIENT_ID"})
        detail = one(self.build([self.unpublished(6, "[SECRETS] 게시 시크릿 미등록: blog_id, client_id")], blog)).detail
        self.assertIn("BLOGGER_CLIENT_ID", detail)
        self.assertNotIn("bad value", detail)

    def test_unpublished_without_secrets_reason_is_not_flagged(self):
        self.assertEqual(self.build([h.make_entry("generated_unpublished", ago(hours=6), ["[LLM] 다른 사유"])]), [])
        self.assertEqual(self.build([h.make_entry("generated_unpublished", ago(hours=6), None)]), [])
        self.assertEqual(self.build([h.make_entry("generated_unpublished", ago(hours=6), "문자열 사유")]), [])

    def test_streak_stops_at_the_last_non_unpublished_entry(self):
        history = [self.unpublished(80), self.unpublished(70), h.make_entry("draft", ago(hours=50)), self.unpublished(26), self.unpublished(2)]
        item = one(self.build(history))
        self.assertIn("2회 연속", item.detail)
        self.assertEqual(item.since, NOW - timedelta(hours=26))

    def test_empty_missing_or_malformed_history_is_fine(self):
        self.assertEqual(self.build([]), [])
        self.assertEqual(self.build([None, 5, "x", {"status": 5}]), [])
        self.assertEqual(inbox.blog_items([h.make_blog()], {}, NOW, URL), [])
        self.assertEqual(inbox.blog_items([h.make_blog()], {"blogger_macat": "깨짐"}, NOW, URL), [])

    def test_blogs_with_bad_keys_are_skipped(self):
        self.assertEqual(inbox.blog_items([{"key": "Bad Key", "mode": "off"}, {"mode": "off"}, None, "x"], {}, NOW, URL), [])


class BlogDraftsItemTest(unittest.TestCase):
    def build(self, history, now=NOW, blog=None):
        blog = blog or h.make_blog()
        return inbox.blog_items([blog], {blog["key"]: history}, now, URL)

    def test_uploaded_drafts_within_a_week_are_a_waiting_action(self):
        history = [h.make_entry("draft_uploaded", ago(days=1)), h.make_entry("draft_uploaded", ago(days=3)),
                   h.make_entry("posted", ago(days=2))]
        item = one(self.build(history))
        self.assertEqual(item.level, "action")
        self.assertIn("초안 2건 게시 대기", item.title)
        self.assertEqual(item.url, "https://www.blogger.com/")
        self.assertEqual(item.since, NOW - timedelta(days=3))
        self.assertTrue(item.id.startswith("blogger:blogger_macat:drafts:"))

    def test_drafts_older_than_a_week_fade_away(self):
        self.assertEqual(self.build([h.make_entry("draft_uploaded", ago(days=7, seconds=1))]), [])
        self.assertEqual(len(self.build([h.make_entry("draft_uploaded", ago(days=7))])), 1)

    def test_id_changes_when_a_newer_draft_arrives_but_not_when_old_ones_expire(self):
        base = [h.make_entry("draft_uploaded", ago(days=3))]
        first = one(self.build(base)).id
        newer = one(self.build(base + [h.make_entry("draft_uploaded", ago(hours=2))])).id
        self.assertNotEqual(first, newer)
        later = NOW + timedelta(days=5)          # 가장 오래된 것은 기간이 지나 빠지고 최신 것만 남는다
        expired = one(self.build([h.make_entry("draft_uploaded", ago(days=3)), h.make_entry("draft_uploaded", ago(days=1))], now=later)).id
        still = one(self.build([h.make_entry("draft_uploaded", ago(days=1))], now=later)).id
        self.assertEqual(expired, still)

    def test_mode_off_makes_no_draft_item(self):
        blog = h.make_blog(mode="off")
        self.assertEqual([i.id for i in self.build([h.make_entry("draft_uploaded", ago(days=1))], blog=blog)], ["blog:blogger_macat:off"])

    def test_entries_without_a_readable_time_are_not_counted(self):
        self.assertEqual(self.build([{"status": "draft_uploaded"}, {"status": "draft_uploaded", "generated_at": "x"}]), [])


class StatsItemsTest(unittest.TestCase):
    def stats(self, history, blog=None, now=NOW):
        blog = blog or h.make_blog()
        return inbox.stats_items([blog], {blog["key"]: history}, now)

    def test_blogger_style_history(self):
        history = [h.make_entry("posted", ago(hours=30)), h.make_entry("posted", ago(hours=5)),
                   h.make_entry("draft", ago(hours=2)), h.make_entry("generated_unpublished", ago(hours=3)),
                   h.make_entry("rejected", ago(hours=1))]
        item = one(self.stats(history))
        self.assertEqual((item.id, item.level), ("stat:blogger_macat", "info"))
        self.assertIn("마지막 글 2026-10-25 10:00 KST", item.title)
        self.assertIn("최근 24시간 글 1건", item.detail)
        self.assertIn("초안·미게시 2건", item.detail)

    def test_no_posts_says_none(self):
        item = one(self.stats([h.make_entry("draft", ago(hours=2))]))
        self.assertIn("마지막 글 없음", item.title)
        self.assertIn("글 0건", item.detail)

    def test_empty_and_missing_history(self):
        self.assertIn("마지막 글 없음", one(self.stats([])).title)
        self.assertIn("마지막 글 없음", one(inbox.stats_items([h.make_blog()], {}, NOW)).title)

    def test_chance_style_history_with_slots_dates_and_old_strings(self):
        history = ["옛 제목", {"date": "2026-10-19", "kr_title": "x"}, {"date": "2026-10-24", "slot": 18}, {"date": "2026-10-25", "slot": 9}]
        item = one(self.stats(history, h.make_blog("chance", "Chance_Blog", platform="jekyll-git", history="history.json")))
        self.assertIn("Chance_Blog: 마지막 글 2026-10-25 09시 슬롯(KST)", item.title)
        self.assertIn("최근 24시간 글 2건", item.detail)            # 어제 18시(21시간 전)와 오늘 9시(6시간 전)

    def test_posts_older_than_24_hours_are_not_counted(self):
        item = one(self.stats([h.make_entry("posted", ago(hours=24, seconds=1)), h.make_entry("posted", ago(hours=24))]))
        self.assertIn("글 1건", item.detail)

    def test_date_only_entries_count_when_dated_today_in_kst(self):
        item = one(self.stats([{"date": "2026-10-25"}, {"date": "2026-10-24"}], h.make_blog("chance", platform="jekyll-git")))
        self.assertIn("최근 24시간 글 1건", item.detail)
        self.assertIn("2026-10-25(날짜만 기록됨)", item.title)

    def test_the_kst_day_boundary_uses_korea_time(self):
        late = datetime(2026, 10, 24, 16, 30, tzinfo=timezone.utc)       # KST 10-25 01:30
        item = one(self.stats([{"date": "2026-10-25"}], h.make_blog("chance", platform="jekyll-git"), now=late))
        self.assertIn("글 1건", item.detail)

    def test_last_post_is_the_latest_even_when_listed_out_of_order(self):
        history = [h.make_entry("posted", ago(hours=2)), h.make_entry("posted", ago(hours=40)), h.make_entry("posted", ago(hours=10))]
        self.assertIn("2026-10-25 13:00 KST", one(self.stats(history)).title)

    def test_mode_off_blogs_have_no_stats_item(self):
        self.assertEqual(self.stats([h.make_entry("posted", ago(hours=2))], h.make_blog(mode="off")), [])

    def test_garbage_history_entries_do_not_crash(self):
        item = one(self.stats([None, 5, "x", {}, {"status": "posted"}, {"status": "posted", "generated_at": "깨짐"}, [1, 2]]))
        self.assertIn("마지막 글 없음", item.title)


# ----------------------------------------------------------------------------
# 조회 실패·안내·조립
# ----------------------------------------------------------------------------
class FailureAndNoteItemsTest(unittest.TestCase):
    def test_failed_source_becomes_a_check_item_with_the_reason(self):
        item = one(inbox.failure_items([("pulls", "HTTP 502: Bad Gateway")], URL))
        self.assertEqual((item.id, item.level), ("source:pulls", "check"))
        self.assertIn("열린 PR 목록", item.title)
        self.assertIn("HTTP 502", item.detail)
        self.assertEqual(item.url, f"{URL}/actions/workflows/{inbox.OWN_WORKFLOW}")

    def test_unknown_source_names_are_neutralised(self):
        item = one(inbox.failure_items([("<x>@y", "사유 ::error::z")], URL))
        for text in (item.title, item.detail):
            for raw in ("<", "@", "::"):
                self.assertNotIn(raw, text)

    def test_notes_are_info_items(self):
        item = one(inbox.note_items([("pulls_cap", "열린 PR 12건 중 처음 8건만 확인했습니다.")]))
        self.assertEqual((item.id, item.level), ("note:pulls_cap", "info"))


def sample_snapshot(**kw):
    base = dict(now=NOW, repo=h.REPO)
    base.update(kw)
    return inbox.Snapshot(**base)


class BuildItemsTest(unittest.TestCase):
    def full(self):
        blog = h.make_blog()
        return sample_snapshot(
            issues=[h.make_watchdog(9), h.make_watchdog(10, "blogger_macat", "UNPUBLISHED", "warning")],
            pulls=[h.make_pull(15), h.make_pull(16, ci="pending", mergeable=None, state="unknown")],
            runs={"a.yml": [h.make_run(1, ago(hours=1), "failure")], "b.yml": [h.make_run(2, ago(hours=1))]},
            annotations={2: [h.make_annotation("경고 문구")]},
            approvals=[h.make_run(3, ago(hours=2), None, "action_required", sha="d" * 40)],
            paused=True, blogs=[blog],
            histories={blog["key"]: [h.make_entry("generated_unpublished", ago(hours=6), [h.SECRETS_REASON])]},
            failures=[("annotations", "HTTP 500")], notes=[("pulls_cap", "일부만 확인")])

    def test_all_rules_contribute_with_the_expected_levels(self):
        items = by_id(inbox.build_items(self.full()))
        levels = {i: item.level for i, item in items.items()}
        self.assertEqual(levels["watchdog:9"], "action")
        self.assertEqual(levels["watchdog:10"], "check")
        self.assertEqual(levels["pr:15:ready"], "action")
        self.assertEqual(levels["pr:16:pending"], "info")
        self.assertEqual(levels["run:a.yml:failed"], "action")
        self.assertEqual(levels["run:b.yml:warn"], "check")
        self.assertEqual(levels["approve:ddddddd"], "action")
        self.assertEqual(levels["pause"], "action")
        self.assertEqual(levels["blogger:blogger_macat:secrets"], "action")
        self.assertEqual(levels["stat:blogger_macat"], "info")
        self.assertEqual(levels["source:annotations"], "check")
        self.assertEqual(levels["note:pulls_cap"], "info")

    def test_order_is_level_then_oldest_first_then_id(self):
        items = inbox.build_items(self.full())
        rank = [inbox.LEVELS.index(i.level) for i in items]
        self.assertEqual(rank, sorted(rank))
        actions = [i for i in items if i.level == "action"]
        dated = [i.since for i in actions if i.since]
        self.assertEqual(dated, sorted(dated))
        self.assertEqual([i for i in actions if i.since is None], actions[len(dated):])      # since 없는 것은 뒤로

    def test_build_is_deterministic_and_independent_of_input_order(self):
        snap = self.full()
        first = inbox.build_items(snap)
        snap.issues.reverse()
        snap.pulls.reverse()
        self.assertEqual(first, inbox.build_items(snap))

    def test_duplicate_ids_keep_the_first(self):
        snap = sample_snapshot(failures=[("pulls", "첫째"), ("pulls", "둘째")])
        item = one(inbox.build_items(snap))
        self.assertIn("첫째", item.detail)

    def test_empty_snapshot_has_no_items(self):
        self.assertEqual(inbox.build_items(sample_snapshot()), [])

    def test_bad_repository_name_is_rejected(self):
        for bad in ("", "no-slash", "a/b/c", "a b/c", "../x", "-a/b", "a/..", "a/.", "a/b c", "a/<b>", None):
            with self.assertRaises(ValueError, msg=bad):
                inbox.build_items(sample_snapshot(repo=bad))
            self.assertFalse(inbox.is_valid_repo(bad), bad)
        for good in ("octo/blog", "shine88pc/chanceblog", "a/b.c_d-e", "Org-1/.github"):
            self.assertTrue(inbox.is_valid_repo(good), good)

    def test_naive_now_is_treated_as_utc(self):
        snap = sample_snapshot(now=datetime(2026, 10, 25, 6, 0), pulls=[h.make_pull(15)])
        self.assertEqual(one(inbox.build_items(snap)).id, "pr:15:ready")


# ----------------------------------------------------------------------------
# 렌더링
# ----------------------------------------------------------------------------
class RenderTest(unittest.TestCase):
    def items(self):
        return inbox.build_items(BuildItemsTest().full())

    def test_same_input_gives_the_same_text_regardless_of_order(self):
        items = self.items()
        first = inbox.render(items, URL)
        shuffled = list(items)
        random.Random(7).shuffle(shuffled)
        self.assertEqual(first, inbox.render(shuffled, URL))
        self.assertEqual(first, inbox.render(items, URL))

    def test_text_has_no_clock_dependent_content(self):
        """같은 항목이면 점검 시각이 달라도 같은 글자여야 한다(그래야 변경이 없을 때 본문을 다시 쓰지 않는다)."""
        a = inbox.build_items(sample_snapshot(now=NOW, pulls=[h.make_pull(15, created="2026-10-25T05:00:00Z")]))
        b = inbox.build_items(sample_snapshot(now=NOW + timedelta(hours=2), pulls=[h.make_pull(15, created="2026-10-25T05:00:00Z")]))
        self.assertEqual(inbox.render(a, URL), inbox.render(b, URL))

    def test_sections_in_order_with_counts_and_summary(self):
        text = inbox.render(self.items(), URL)
        positions = [text.index(f"## {title}") for title in ("지금 해야 할 일", "확인하면 좋은 것", "참고")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("## 지금 해야 할 일 (6건)", text)
        self.assertIn("## 확인하면 좋은 것 (3건)", text)
        self.assertIn("## 참고 (3건)", text)
        self.assertIn("**지금 해야 할 일 6건** · 확인하면 좋은 것 3건 · 참고 3건", text)

    def test_each_field_is_clipped_to_its_documented_length_in_the_rendered_block(self):
        item = inbox.Item("a", "action", "T" * 600, "D" * 3000, f"{URL}/x", "H" * 1000)
        lines = inbox.render([item], URL).split("\n")
        start = next(i for i, line in enumerate(lines) if line.startswith("- **"))
        self.assertEqual(len(lines[start]), len("- ****") + 110)
        self.assertEqual(len(lines[start + 1]), len("  - ") + 420)
        self.assertEqual(len(lines[start + 2]), len(f"  - ▶ [바로 하기]({URL}/x) — ") + 260)

    def test_every_section_heading_follows_a_blank_line(self):
        lines = inbox.render(self.items(), URL).split("\n")
        headings = [i for i, line in enumerate(lines) if line.startswith("## ")]
        self.assertEqual(len(headings), 3)
        for index in headings:
            self.assertEqual(lines[index - 1], "", lines[index])

    def test_the_text_never_exceeds_the_limit_whatever_the_limit_is(self):
        items = [inbox.Item(f"pr:{n}:ready", "action", f"PR {n} " + "가" * 30, "나" * 60, f"{URL}/pull/{n}", "다" * 40) for n in range(1, 60)]
        for limit in range(500, 1400, 11):
            self.assertLessEqual(len(inbox.render(items, URL, limit)), limit, limit)

    def test_empty_inbox_says_nothing_to_check(self):
        text = inbox.render([], URL)
        self.assertIn("지금 확인할 것이 없습니다", text)
        self.assertNotIn("## ", text)
        self.assertNotIn("**지금 해야 할 일", text)

    def test_empty_sections_are_left_out(self):
        text = inbox.render([inbox.Item("stat:x", "info", "현황")], URL)
        self.assertIn("## 참고 (1건)", text)
        self.assertNotIn("## 지금 해야 할 일", text)
        self.assertNotIn("## 확인하면 좋은 것", text)
        self.assertIn("**지금 해야 할 일 0건**", text)

    def test_every_item_with_a_link_has_the_go_now_link_and_one_line_hint(self):
        item = inbox.Item("pr:1:ready", "action", "PR 1", "상세", f"{URL}/pull/1", "한 줄 안내")
        text = inbox.render([item], URL)
        self.assertIn(f"  - ▶ [바로 하기]({URL}/pull/1) — 한 줄 안내", text)
        self.assertIn("- **PR 1**", text)
        self.assertIn("  - 상세", text)

    def test_item_without_link_shows_the_hint_as_guidance_and_without_hint_shows_nothing_extra(self):
        text = inbox.render([inbox.Item("a", "info", "제목", hint="안내만")], URL)
        self.assertIn("  - 안내: 안내만", text)
        self.assertNotIn("바로 하기", text)
        bare = inbox.render([inbox.Item("a", "info", "제목")], URL)
        self.assertEqual(bare.count("\n  - "), 0)

    def test_since_is_shown_in_korea_time(self):
        item = inbox.Item("a", "action", "t", "d", since=datetime(2026, 10, 25, 5, 57, tzinfo=timezone.utc))
        self.assertIn("d · 2026-10-25 14:57 KST부터", inbox.render([item], URL))
        only_since = inbox.Item("b", "action", "t2", since=datetime(2026, 10, 25, 5, 57, tzinfo=timezone.utc))
        self.assertIn("  - 2026-10-25 14:57 KST부터", inbox.render([only_since], URL))

    def test_unsafe_link_is_not_rendered_as_a_link(self):
        item = inbox.Item("a", "action", "t", url="javascript:alert(1)", hint="안내")
        text = inbox.render([item], URL)
        self.assertNotIn("javascript", text)
        self.assertNotIn("](", text.split("규칙·끄는 법")[0])

    def test_footer_links_to_the_guide_and_tells_the_inbox_is_public(self):
        text = inbox.render([], URL)
        self.assertIn(f"[docs/OPS_INBOX.md]({URL}/blob/main/docs/OPS_INBOX.md)", text)
        self.assertIn("공개", text)
        self.assertIn("\n---\n", text)

    def test_no_line_can_start_a_workflow_command_or_mention_anyone(self):
        evil = "@everyone\n::error::위조\n##[group]x <img src=x onerror=1> [피싱](https://evil.example)"
        items = [inbox.Item("a", "action", evil, evil, f"{URL}/x", evil)]
        text = inbox.render(items, URL)
        for line in text.splitlines():
            self.assertFalse(line.lstrip().startswith("::"), line)
            self.assertNotIn("##[", line)
        body = text.split("\n---\n")[0]
        for raw in ("@", "<"):
            self.assertNotIn(raw, body)

    def test_long_lists_are_cut_to_the_limit_and_say_how_many_were_dropped(self):
        items = [inbox.Item(f"pr:{n}:ready", "action", f"PR {n} " + "가" * 100, "나" * 400, f"{URL}/pull/{n}", "다" * 200) for n in range(1, 401)]
        items += [inbox.Item(f"stat:{n}", "info", "현황") for n in range(3)]
        text = inbox.render(items, URL)
        self.assertLessEqual(len(text), inbox.BODY_LIMIT)
        self.assertRegex(text, r"… 외 \d+건은 길이 제한으로 줄였습니다")
        self.assertIn("**지금 해야 할 일 400건**", text)           # 요약의 건수는 줄이기 전 전체 건수
        shown = text.count("- **PR ")
        hidden = int(re.search(r"외 (\d+)건", text).group(1))
        self.assertEqual(shown + hidden, 403)
        self.assertNotIn("## 참고", text)                         # 자르면 뒤쪽(참고)부터 사라진다
        self.assertIn(inbox.sort_items(items)[0].title, text)     # 앞쪽(먼저 보여 줄 것)은 남는다

    def test_small_limit_still_returns_header_note_and_footer(self):
        text = inbox.render(self.items(), URL, limit=600)
        self.assertLessEqual(len(text), 600)
        self.assertIn("길이 제한", text)
        self.assertIn("docs/OPS_INBOX.md", text)

    def test_nothing_is_cut_when_it_fits(self):
        self.assertNotIn("길이 제한", inbox.render(self.items(), URL))

    def test_issue_body_with_marker_stays_under_github_limit(self):
        items = [inbox.Item(f"pr:{n}:ready", "action", "가" * 110, "나" * 420, f"{URL}/pull/{n}", "다" * 260) for n in range(1, 700)]
        body = inbox.build_body(inbox.render(items, URL), [i.id for i in items])
        self.assertLess(len(body), 65000)

    def test_summary_limit_renders_everything_the_issue_would_cut(self):
        items = [inbox.Item(f"pr:{n}:ready", "action", "가" * 100, "나" * 400, f"{URL}/pull/{n}", "다" * 200) for n in range(1, 401)]
        self.assertIn("길이 제한", inbox.render(items, URL, inbox.BODY_LIMIT))
        self.assertNotIn("길이 제한", inbox.render(items, URL, inbox.SUMMARY_LIMIT))


# ----------------------------------------------------------------------------
# 표식·새 알림 판정·코멘트
# ----------------------------------------------------------------------------
class MarkerTest(unittest.TestCase):
    def test_roundtrip_sorts_and_dedupes_ids(self):
        body = inbox.build_body("본문\n", ["pr:2:ready", "pr:1:ci_fail", "pr:2:ready"])
        marker = inbox.parse_marker(body)
        self.assertEqual(marker.items, ("pr:1:ci_fail", "pr:2:ready"))
        self.assertEqual(marker.hash, inbox.body_hash("본문\n"))
        self.assertTrue(body.rstrip().endswith("-->"))
        self.assertEqual(body.count("<!-- ops-inbox:"), 1)

    def test_no_ids_gives_an_empty_tuple(self):
        self.assertEqual(inbox.parse_marker(inbox.build_body("x", [])).items, ())

    def test_missing_or_malformed_markers_are_none(self):
        for body in (None, "", "표식 없음", "<!-- ops-inbox:hash=xyz;items=a -->", "<!-- ops-inbox:hash=0123;items=a -->",
                     "<!-- ops-inbox:hash=0123456789abcdef;items=A:B -->", "<!-- other:hash=0123456789abcdef;items=a -->"):
            self.assertIsNone(inbox.parse_marker(body), body)

    def test_the_last_marker_wins(self):
        body = "<!-- ops-inbox:hash=1111111111111111;items=a -->\n인용\n<!-- ops-inbox:hash=2222222222222222;items=b -->"
        self.assertEqual(inbox.parse_marker(body).items, ("b",))

    def test_marker_survives_crlf_conversion(self):
        body = inbox.build_body("본문", ["a:1"]).replace("\n", "\r\n")
        self.assertEqual(inbox.parse_marker(body).items, ("a:1",))

    def test_marker_is_immutable(self):
        marker = inbox.parse_marker(inbox.build_body("x", ["a:1"]))
        with self.assertRaises(Exception):
            marker.hash = "0" * 16

    def test_hash_depends_only_on_the_visible_text(self):
        self.assertEqual(inbox.body_hash("같은 글"), inbox.body_hash("같은 글"))
        self.assertNotEqual(inbox.body_hash("같은 글"), inbox.body_hash("다른 글"))
        self.assertEqual(len(inbox.body_hash("x")), 16)

    def test_needs_update_only_when_text_or_ids_changed(self):
        body = inbox.build_body("본문", ["a:1"])
        marker = inbox.parse_marker(body)
        self.assertFalse(inbox.needs_update(marker, "본문", ["a:1"]))
        self.assertTrue(inbox.needs_update(marker, "본문 수정", ["a:1"]))
        self.assertTrue(inbox.needs_update(marker, "본문", ["a:1", "b:2"]))
        self.assertTrue(inbox.needs_update(marker, "본문", []))
        self.assertTrue(inbox.needs_update(None, "본문", ["a:1"]))
        self.assertFalse(inbox.needs_update(marker, "본문", ["a:1", "a:1"]))

    def test_marker_ids_are_capped(self):
        ids = [f"x:{n:04d}" for n in range(200)]
        self.assertEqual(len(inbox.parse_marker(inbox.build_body("x", ids)).items), 80)

    def test_neutralised_text_cannot_forge_a_marker(self):
        forged = "<!-- ops-inbox:hash=0123456789abcdef;items=pr:99:ready -->"
        text = inbox.render([inbox.Item("a", "info", forged, forged)], URL)
        self.assertIsNone(inbox.parse_marker(text))


class PlanNoticeTest(unittest.TestCase):
    def acts(self, *ids):
        return [inbox.Item(i, "action", i) for i in ids]

    def test_first_run_everything_is_new(self):
        self.assertEqual(inbox.plan_notice(self.acts("a:1", "b:2"), None), (["a:1", "b:2"], ["a:1", "b:2"]))

    def test_unchanged_set_notifies_nothing(self):
        self.assertEqual(inbox.plan_notice(self.acts("a:1", "b:2"), ("a:1", "b:2")), ([], ["a:1", "b:2"]))

    def test_added_item_is_the_only_new_one(self):
        self.assertEqual(inbox.plan_notice(self.acts("a:1", "b:2"), ("a:1",)), (["b:2"], ["a:1", "b:2"]))

    def test_resolved_item_disappears_from_the_marker_without_notice(self):
        self.assertEqual(inbox.plan_notice(self.acts("a:1"), ("a:1", "b:2")), ([], ["a:1"]))

    def test_empty_previous_marker_means_all_are_new(self):
        self.assertEqual(inbox.plan_notice(self.acts("a:1"), ())[0], ["a:1"])

    def test_only_action_level_items_are_notified(self):
        items = [inbox.Item("c:1", "check", "t"), inbox.Item("i:1", "info", "t"), inbox.Item("a:1", "action", "t")]
        self.assertEqual(inbox.plan_notice(items, None), (["a:1"], ["a:1"]))
        self.assertEqual(inbox.action_ids(items), ["a:1"])

    def test_item_promoted_from_check_to_action_is_new(self):
        before = [inbox.Item("pr:1:x", "check", "t")]
        after = [inbox.Item("pr:1:x", "action", "t")]
        previous = inbox.parse_marker(inbox.build_body("v", inbox.action_ids(before))).items
        self.assertEqual(inbox.plan_notice(after, previous)[0], ["pr:1:x"])

    def test_a_changed_state_of_the_same_pr_is_a_new_thing_to_do(self):
        self.assertEqual(inbox.plan_notice(self.acts("pr:15:conflict"), ("pr:15:ready",)), (["pr:15:conflict"], ["pr:15:conflict"]))

    def test_failed_source_keeps_its_previous_ids_so_recovery_is_not_a_new_alert(self):
        failed = [("pulls", "HTTP 500")]
        new, kept = inbox.plan_notice(self.acts("watchdog:9"), ("pr:15:ready", "watchdog:9"), failed)
        self.assertEqual((new, kept), ([], ["pr:15:ready", "watchdog:9"]))
        # 복구되면 같은 항목이 다시 나타나도 새 알림이 아니다
        self.assertEqual(inbox.plan_notice(self.acts("watchdog:9", "pr:15:ready"), tuple(kept))[0], [])

    def test_without_a_failure_a_vanished_id_is_dropped(self):
        self.assertEqual(inbox.plan_notice(self.acts("watchdog:9"), ("pr:15:ready", "watchdog:9"))[1], ["watchdog:9"])

    def test_carry_over_only_covers_the_failed_sources_prefixes(self):
        kept = inbox.plan_notice([], ("pr:1:x", "watchdog:2", "run:a.yml:failed", "approve:abc", "pause"), [("runs", "x")])[1]
        self.assertEqual(kept, ["run:a.yml:failed"])
        kept = inbox.plan_notice([], ("pr:1:x", "watchdog:2"), [("pull_details", "x"), ("issues", "y")])[1]
        self.assertEqual(kept, ["pr:1:x", "watchdog:2"])
        self.assertEqual(inbox.plan_notice([], ("pr:1:x",), [("annotations", "x")])[1], [])      # 주석은 action 을 만들지 않는다

    def test_every_source_with_action_items_has_its_prefix_registered(self):
        for source in ("issues", "pulls", "pull_details", "runs", "approvals", "history", "registry"):
            self.assertIn(source, inbox.SOURCE_PREFIXES)
        self.assertEqual(inbox.SOURCE_PREFIXES["history"], ("blogger:",))


class CommentTextTest(unittest.TestCase):
    def acts(self, *titles):
        return [inbox.Item(f"a:{n}", "action", title) for n, title in enumerate(titles)]

    def test_mentions_the_owner_and_lists_titles_with_a_link(self):
        text = inbox.comment_text("octo-cat", self.acts("PR #15 병합하면 됩니다", "워크플로 실패"), f"{URL}/issues/9")
        self.assertTrue(text.startswith("@octo-cat 새로 해야 할 일이 2건 생겼습니다."))
        self.assertIn("- PR #15 병합하면 됩니다", text)
        self.assertIn("- 워크플로 실패", text)
        self.assertIn(f"▶ [모아 보기]({URL}/issues/9)", text)

    def test_the_owners_mention_is_the_only_mention(self):
        text = inbox.comment_text("octo", self.acts("@victim 님 <b>x</b> &#64;other"), f"{URL}/issues/9")
        self.assertEqual(text.count("@"), 1)
        self.assertNotIn("<", text)
        self.assertNotIn("&", text)

    def test_invalid_or_missing_owner_means_no_mention(self):
        for owner in (None, "", "bad owner", "-bad", "a" * 40, "x@y", "<b>"):
            text = inbox.comment_text(owner, self.acts("t"), "")
            self.assertNotIn("@", text, owner)
            self.assertTrue(text.startswith("새로 해야 할 일이 1건"), owner)

    def test_exactly_the_maximum_number_of_items_has_no_remainder_line(self):
        text = inbox.comment_text("octo", self.acts(*[f"항목 {n}" for n in range(8)]), "")
        self.assertEqual(text.count("\n- 항목"), 8)
        self.assertNotIn("… 외", text)

    def test_long_lists_are_summarised(self):
        text = inbox.comment_text("octo", self.acts(*[f"항목 {n}" for n in range(12)]), "")
        self.assertEqual(text.count("\n- 항목"), 8)
        self.assertIn("… 외 4건", text)

    def test_without_a_link_it_points_at_the_issue_body(self):
        self.assertIn("바로 하기", inbox.comment_text("octo", self.acts("t"), ""))
        self.assertNotIn("모아 보기", inbox.comment_text("octo", self.acts("t"), "javascript:x"))


if __name__ == "__main__":
    unittest.main()
