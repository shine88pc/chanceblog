"""초안 현황(작업요청서 5 PR-B) 시험 — 초안 모델·항목·현황 표(pipeline/inbox.py, 순수 함수), 초안 읽기·라벨 만들기·전체 실행(scripts/ops_inbox.py,
가짜 GitHub), 워크플로 구조(.github/workflows/ops-inbox.yml)를 네트워크 없이 확인한다.

초안 모델: 초안 1건 = 이슈 1개 또는 PR 1개, 라벨 `초안` + `채널:<채널 라벨>`, 쓰지 않을 초안은 라벨 `폐기` 또는 닫기.
기존 모음 시험(test_ops_inbox.py·test_ops_inbox_script.py)은 board 인자·초안 읽기가 생기기 전과 같은 입력에서 같은 결과를 내는지의 회귀 시험이다.
"""
import copy
import json
import random
import re
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

import yaml

import _bootstrap
import ops_inbox_helpers as h
import ops_inbox as oi
from pipeline import inbox

NOW, URL, ago = h.NOW, h.REPO_URL, h.ago
TOKEN = "gh" + "s_" + "Q" * 36          # 런타임에 조합한 가짜 토큰(소스에 비밀 모양 리터럴을 두지 않는다)
WORKFLOW = _bootstrap.ROOT / ".github" / "workflows" / "ops-inbox.yml"
EVIL = ("@everyone <img src=x onerror=1> [피싱](https://evil.example/x) `코드` | 칸 &#64;user\n::error::위조 ##[group]g " + TOKEN)


def table_rows(board):
    """초안 현황 표의 줄 → 칸 목록(머리·구분선 제외)."""
    rows = []
    for line in board.splitlines():
        if line.startswith("| ") and not line.startswith("| 채널 |"):
            rows.append([cell.strip() for cell in line[2:-2].split(" | ")])
    return rows


def snap(**kw):
    base = dict(now=NOW, repo=h.REPO)
    base.update(kw)
    return inbox.Snapshot(**base)


def blogs4(chance_flow=None, blogger_mode="draft"):
    chance = h.channel_blog("chance", "Chance", "jekyll-git", "auto", name="Chance_Blog")
    if chance_flow:
        chance["publish_flow"] = chance_flow
    return [chance, h.channel_blog("blogger_macat", "Blogger", "blogger", blogger_mode, name="Blogger (macat0722)"),
            h.channel_blog("tistory_x", "티스토리", "tistory", "package"), h.channel_blog("naver_x", "네이버", "naver", "off")]


# ----------------------------------------------------------------------------
# 초안 모델
# ----------------------------------------------------------------------------
class DraftModelTest(unittest.TestCase):
    def test_documented_defaults(self):
        """값을 바꾸면 docs/OPS_INBOX.md 와 이 표를 함께 고친다(다른 시험이 상수를 그대로 읽어 쓰므로 값 자체는 여기서 고정한다)."""
        expected = {"DRAFT_STALE_DAYS": 3, "DRAFT_WINDOW_DAYS": 14, "BOARD_ROWS_MAX": 12, "BOARD_TITLE_MAX": 24, "DRAFT_TITLE_MAX": 80, "LABEL_NAME_MAX": 50}
        for name, value in expected.items():
            self.assertEqual(getattr(inbox, name), value, name)
        self.assertEqual(inbox.PR_STALE_DAYS, inbox.DRAFT_STALE_DAYS)             # 오래 열린 PR 과 같은 기준

    def test_label_names_prefix_and_fixed_label_specs(self):
        self.assertEqual((inbox.DRAFT_LABEL, inbox.DISCARD_LABEL, inbox.CHANNEL_LABEL_PREFIX), ("초안", "폐기", "채널:"))
        self.assertEqual(inbox.channel_label_name("티스토리"), "채널:티스토리")
        self.assertEqual(inbox.channel_label_name("Blogger 영문"), "채널:Blogger 영문")
        names = [name for name, _color, _text in inbox.DRAFT_LABEL_SPECS]
        self.assertEqual(names, ["초안", "폐기"])
        for _name, color, text in inbox.DRAFT_LABEL_SPECS:
            self.assertRegex(color, "^[0-9a-f]{6}$")
            self.assertTrue(0 < len(text) <= 100)
        self.assertRegex(inbox.CHANNEL_LABEL_COLOR, "^[0-9a-f]{6}$")
        self.assertEqual(len({color for _n, color, _t in inbox.DRAFT_LABEL_SPECS} | {inbox.CHANNEL_LABEL_COLOR, inbox.LABEL_COLOR}), 4)   # 서로 구분된다

    def test_label_specs_are_draft_discard_and_one_label_per_registry_channel(self):
        specs = inbox.draft_label_specs(blogs4())
        self.assertEqual([spec["name"] for spec in specs], ["초안", "폐기", "채널:Chance", "채널:Blogger", "채널:티스토리", "채널:네이버"])
        for spec in specs[:2]:
            self.assertEqual(set(spec), {"name", "color", "description"})
        for spec in specs[2:]:
            self.assertEqual(spec["color"], inbox.CHANNEL_LABEL_COLOR)
            self.assertIn(spec["name"][len("채널:"):], spec["description"])
            self.assertLessEqual(len(spec["description"]), 100)

    def test_label_specs_skip_blogs_without_a_channel_duplicates_and_names_too_long_for_github(self):
        blogs = [h.make_blog("a", "이름 없는 채널"), h.channel_blog("b", "Chance", "jekyll-git", "auto"), h.channel_blog("c", "chance", "jekyll-git", "auto"),
                 h.channel_blog("d", "가" * 60, "tistory", "package"), {"key": "e", "channel": {"label": 5}}, "문자열", None,
                 h.channel_blog("f", "  티스토리  ", "tistory", "package")]
        self.assertEqual([spec["name"] for spec in inbox.draft_label_specs(blogs)], ["초안", "폐기", "채널:Chance", "채널:티스토리"])
        self.assertEqual([spec["name"] for spec in inbox.draft_label_specs([])], ["초안", "폐기"])

    def test_normalize_reads_number_kind_title_channel_labels_state_and_trust(self):
        raw = h.make_draft_raw(41, "[초안][티스토리] 제목", "티스토리", hours=30)
        draft = inbox.normalize_draft(raw)
        self.assertEqual((draft["number"], draft["kind"], draft["title"], draft["channel"], draft["state"]), (41, "issue", "[초안][티스토리] 제목", "티스토리", "open"))
        self.assertEqual(draft["labels"], ("초안", "채널:티스토리"))
        self.assertEqual(draft["created_at"], ago(hours=30))
        self.assertIs(draft["trusted"], True)                               # 작성자가 github-actions 봇
        self.assertEqual(inbox.normalize_draft(h.make_draft_raw(42, pull=True))["kind"], "pull")

    def test_normalize_accepts_plain_string_labels_and_takes_the_first_channel_in_sort_order(self):
        raw = h.make_draft_raw(5, channel=None)
        raw["labels"] = ["초안", "채널:티스토리", "채널:Chance", {"name": "bug"}, {"name": ""}, 7, None]
        draft = inbox.normalize_draft(raw)
        self.assertEqual(draft["labels"], ("초안", "채널:티스토리", "채널:Chance", "bug"))
        self.assertEqual(draft["channel"], "Chance")

    def test_a_channel_label_without_a_name_is_no_channel(self):
        raw = h.make_draft_raw(5, channel=None, extra_labels=("채널:", "채널:  "))
        self.assertIsNone(inbox.normalize_draft(raw)["channel"])

    def test_normalize_rejects_what_has_no_usable_number(self):
        for bad in (None, "x", [], {}, {"number": "7"}, {"number": True}, {"number": 0}, {"number": -3}, {"number": 1.5}):
            self.assertIsNone(inbox.normalize_draft(bad), bad)

    def test_normalize_survives_missing_pieces(self):
        draft = inbox.normalize_draft({"number": 9})
        self.assertEqual((draft["kind"], draft["state"], draft["labels"], draft["channel"], draft["trusted"]), ("issue", "open", (), None, False))
        self.assertEqual(inbox.normalize_draft({"number": 9, "labels": "초안"})["labels"], ())

    def test_trust_follows_the_watchdog_rule(self):
        self.assertTrue(inbox.normalize_draft(h.make_draft_raw(1, login=h.BOT))["trusted"])
        for assoc in ("OWNER", "MEMBER", "COLLABORATOR"):
            self.assertTrue(inbox.normalize_draft(h.make_draft_raw(1, login="someone", assoc=assoc))["trusted"], assoc)
        for assoc in ("NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", ""):
            self.assertFalse(inbox.normalize_draft(h.make_draft_raw(1, login="stranger", assoc=assoc))["trusted"], assoc)

    def test_no_url_is_carried_from_the_api_response(self):
        raw = h.make_draft_raw(5)
        raw["html_url"] = "https://evil.example/phish"
        self.assertNotIn("evil.example", json.dumps(inbox.normalize_draft(raw), ensure_ascii=False))


class PendingDraftsTest(unittest.TestCase):
    def test_only_open_labelled_not_discarded_trusted_drafts_count(self):
        drafts = [
            h.make_draft(1),                                              # 센다
            h.make_draft(2, state="closed"),                              # 닫힘(발행 완료·폐기)
            h.make_draft(3, draft_label=False),                           # 라벨 초안이 없음
            h.make_draft(4, extra_labels=("폐기",)),                      # 폐기
            h.make_draft(5, login="stranger", assoc="NONE"),              # 낯선 사람의 위장
            h.make_draft(6, pull=True),                                   # PR 도 센다
        ]
        self.assertEqual([d["number"] for d in inbox.pending_drafts(drafts)], [1, 6])

    def test_numbers_are_sorted_and_counted_once(self):
        drafts = [h.make_draft(9), h.make_draft(3), h.make_draft(9, pull=True), h.make_draft(5)]
        self.assertEqual([d["number"] for d in inbox.pending_drafts(drafts)], [3, 5, 9])

    def test_a_draft_dict_must_say_it_is_trusted_and_open_by_itself(self):
        base = h.make_draft(1)
        self.assertEqual(len(inbox.pending_drafts([base])), 1)
        self.assertEqual(inbox.pending_drafts([{k: v for k, v in base.items() if k != "trusted"}]), [])        # 모르면 믿지 않는다
        self.assertEqual(len(inbox.pending_drafts([{k: v for k, v in base.items() if k != "state"}])), 1)       # 상태를 모르면 열린 것으로 읽는다(목록이 열린 것만 요청)
        self.assertEqual(inbox.pending_drafts([dict(base, trusted="yes")]), [])

    def test_garbage_does_not_crash(self):
        for bad in (None, "x", 5, {}, [None, "x", 3, {}, {"number": "1"}, {"number": 1, "labels": None}]):
            self.assertEqual(inbox.pending_drafts(bad), [], bad)


# ----------------------------------------------------------------------------
# 초안 항목(action / check)
# ----------------------------------------------------------------------------
class DraftItemsTest(unittest.TestCase):
    def items(self, drafts, now=NOW):
        return inbox.draft_items(drafts, now, URL)

    def test_a_new_draft_issue_is_an_action_with_a_link_since_time_and_instructions(self):
        item, = self.items([h.make_draft(41, "[초안][티스토리] 맛집 지도 만드는 법", hours=30)])
        self.assertEqual((item.id, item.level), ("draft:41:wait", "action"))
        self.assertEqual(item.title, "초안 대기 — 맛집 지도 만드는 법")
        self.assertEqual(item.detail, "채널 티스토리 · 이슈 #41 · 발행을 기다립니다")
        self.assertEqual(item.url, f"{URL}/issues/41")
        self.assertEqual(item.since, inbox.parse_time(ago(hours=30)))
        self.assertIn("이슈를 닫으세요", item.hint)
        self.assertIn("`폐기`", item.hint)

    def test_exactly_three_days_is_still_new_and_a_minute_more_is_stale(self):
        edge = NOW - timedelta(days=3)
        self.assertEqual(self.items([h.make_draft(1, created=edge.strftime("%Y-%m-%dT%H:%M:%SZ"))])[0].level, "action")
        over = NOW - timedelta(days=3, minutes=1)
        item, = self.items([h.make_draft(1, created=over.strftime("%Y-%m-%dT%H:%M:%SZ"))])
        self.assertEqual((item.id, item.level), ("draft:1:stale", "check"))
        self.assertEqual(inbox.DRAFT_STALE_DAYS, 3)

    def test_a_stale_draft_is_a_check_item_that_says_what_to_do(self):
        item, = self.items([h.make_draft(43, "[초안][네이버] 오래된 글", "네이버", hours=100)])
        self.assertEqual((item.id, item.level), ("draft:43:stale", "check"))
        self.assertEqual(item.title, "초안 3일 넘게 대기 — 오래된 글")
        self.assertEqual(item.detail, "채널 네이버 · 이슈 #43 · 3일 넘게 열려 있음")
        self.assertIn("닫", item.hint)
        self.assertIn("`폐기`", item.hint)

    def test_the_state_is_in_the_id_so_ageing_moves_a_draft_without_a_new_alert(self):
        early = {i.id for i in self.items([h.make_draft(7, hours=70)], NOW) if i.level == "action"}
        late_items = self.items([h.make_draft(7, hours=70)], NOW + timedelta(hours=4))
        self.assertEqual(early, {"draft:7:wait"})
        self.assertEqual([(i.id, i.level) for i in late_items], [("draft:7:stale", "check")])
        new, kept = inbox.plan_notice(late_items, sorted(early))
        self.assertEqual((new, kept), ([], []))                              # 알림 없음, 표식에서는 빠진다

    def test_a_new_pull_request_draft_is_an_action_with_a_pull_link_and_merge_instructions(self):
        item, = self.items([h.make_draft(15, "[초안][Chance] 승인 대기 글", "Chance", hours=3, pull=True)])
        self.assertEqual((item.id, item.level), ("draft:15:wait", "action"))
        self.assertEqual(item.title, "초안 대기 — 승인 대기 글")
        self.assertEqual(item.detail, "채널 Chance · PR #15 · 검토·병합을 기다립니다")
        self.assertEqual(item.url, f"{URL}/pull/15")                          # PR 은 /pull/번호 — 이슈 주소로 열면 PR 로 넘어가긴 하지만 링크는 바르게 만든다
        self.assertEqual(item.since, inbox.parse_time(ago(hours=3)))
        self.assertIn("병합하면 공개", item.hint)
        self.assertIn("`폐기`", item.hint)
        self.assertNotIn("이슈", item.hint + item.detail)                      # 이슈 초안의 '복사해 발행하고 닫기' 안내가 섞이지 않는다
        self.assertNotIn("복사", item.hint)

    def test_a_stale_pull_request_draft_is_a_check_item_that_says_to_merge_or_discard(self):
        item, = self.items([h.make_draft(15, "[초안][Chance] 오래된 승인 글", "Chance", hours=100, pull=True)])
        self.assertEqual((item.id, item.level), ("draft:15:stale", "check"))
        self.assertEqual(item.title, "초안 3일 넘게 대기 — 오래된 승인 글")
        self.assertEqual(item.detail, "채널 Chance · PR #15 · 3일 넘게 열려 있음")
        self.assertEqual(item.url, f"{URL}/pull/15")
        self.assertIn("병합", item.hint)
        self.assertIn("`폐기`", item.hint)
        self.assertNotIn("이슈", item.hint + item.detail)

    def test_an_issue_and_a_pull_request_draft_say_where_they_are_in_their_own_words(self):
        issue, pull = self.items([h.make_draft(16, channel="티스토리"), h.make_draft(15, channel="Chance", pull=True)])[::-1]
        self.assertEqual((issue.detail, pull.detail), ("채널 티스토리 · 이슈 #16 · 발행을 기다립니다", "채널 Chance · PR #15 · 검토·병합을 기다립니다"))
        self.assertEqual((issue.url, pull.url), (f"{URL}/issues/16", f"{URL}/pull/15"))
        self.assertNotEqual(issue.hint, pull.hint)

    def test_a_pull_request_the_pull_rule_already_alerts_on_gets_no_second_item(self):
        both = [h.make_draft(15, pull=True, channel="Chance"), h.make_draft(16, channel="티스토리"), h.make_draft(17, pull=True, channel="Chance")]
        self.assertEqual([i.id for i in inbox.draft_items(both, NOW, URL, acting_pulls={15})], ["draft:16:wait", "draft:17:wait"])
        self.assertEqual([i.id for i in inbox.draft_items(both, NOW, URL, acting_pulls={15, 17})], ["draft:16:wait"])
        self.assertEqual([i.id for i in inbox.draft_items(both, NOW, URL)], ["draft:15:wait", "draft:16:wait", "draft:17:wait"])      # 기본값: 모두 만든다

    def test_the_skip_list_is_for_pull_requests_only_an_issue_with_the_same_number_keeps_its_item(self):
        # 이슈와 PR 은 번호를 함께 쓰므로 실제로는 겹치지 않는다 — 종류를 번호만으로 가리지 않는다는 방어
        self.assertEqual([i.id for i in inbox.draft_items([h.make_draft(15)], NOW, URL, acting_pulls={15})], ["draft:15:wait"])

    def test_a_pull_request_draft_keeps_no_item_when_it_is_closed_discarded_or_from_a_stranger(self):
        drafts = [h.make_draft(1, pull=True, state="closed"), h.make_draft(2, pull=True, extra_labels=("폐기",)),
                  h.make_draft(3, pull=True, login="stranger", assoc="NONE"), h.make_draft(4, pull=True, draft_label=False)]
        self.assertEqual(self.items(drafts), [])

    def test_closed_discarded_and_stranger_drafts_make_no_item(self):
        drafts = [h.make_draft(1, state="closed"), h.make_draft(2, extra_labels=("폐기",)), h.make_draft(3, login="stranger", assoc="NONE"),
                  h.make_draft(4, draft_label=False)]
        self.assertEqual(self.items(drafts), [])

    def test_a_missing_or_unreadable_created_time_is_never_stale_and_has_no_since(self):
        for value in (None, "", "어제", "2026-10-20"):
            draft = h.make_draft(8)
            draft["created_at"] = value
            item, = self.items([draft])
            self.assertEqual((item.id, item.level, item.since), ("draft:8:wait", "action", None), value)

    def test_a_draft_dated_in_the_future_is_new(self):
        item, = self.items([h.make_draft(8, created=(NOW + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))])
        self.assertEqual(item.level, "action")

    def test_title_tags_are_removed_only_when_they_are_ours(self):
        cases = {"[초안][티스토리] 글": "글", "[초안] 글": "글", "[티스토리] 글": "글", "[초안][Chance] 글": "［Chance］ 글", "글 [초안]": "글 ［초안］",
                 "[속보] 글": "［속보］ 글", "": "제목 없음", "[초안][티스토리]": "제목 없음", "   ": "제목 없음"}
        for title, shown in cases.items():
            item, = self.items([h.make_draft(1, title, "티스토리")])
            self.assertEqual(item.title, f"초안 대기 — {shown}", title)

    def test_a_draft_without_a_channel_label_says_so(self):
        item, = self.items([h.make_draft(1, "제목", None)])
        self.assertEqual(item.detail, "채널 채널 표시 없음 · 이슈 #1 · 발행을 기다립니다")

    def test_external_text_cannot_mention_inject_html_forge_commands_or_leak_secrets(self):
        item, = self.items([h.make_draft(41, "[초안][티스토리] " + EVIL, "티스토리" + EVIL)])
        text = "\n".join((item.id, item.title, item.detail, item.hint, item.url))
        self.assertNotIn(TOKEN, text)
        for raw in ("@", "<", "&", "\n", "](", "`코드`"):
            self.assertNotIn(raw, item.title + item.detail, raw)
        self.assertNotIn("::", item.title + item.detail)
        self.assertNotIn("##[", item.title + item.detail)
        self.assertRegex(item.id, r"^draft:41:wait$")                            # 외부 글은 id 에 들어가지 않는다
        block = inbox.render([item], URL)
        for line in block.splitlines():
            self.assertFalse(line.lstrip().startswith("::"), line)

    def test_a_long_title_is_clipped(self):
        item, = self.items([h.make_draft(1, "[초안][티스토리] " + "가" * 500)])
        self.assertLessEqual(len(item.title), len("초안 대기 — ") + inbox.DRAFT_TITLE_MAX)
        self.assertTrue(item.title.endswith("…"))

    def test_build_items_includes_the_draft_rule_and_orders_by_level_then_oldest(self):
        drafts = [h.make_draft(1, hours=20), h.make_draft(2, hours=50), h.make_draft(3, hours=100)]
        items = [i for i in inbox.build_items(snap(drafts=drafts)) if i.id.startswith("draft:")]
        self.assertEqual([(i.id, i.level) for i in items], [("draft:2:wait", "action"), ("draft:1:wait", "action"), ("draft:3:stale", "check")])

    def test_the_drafts_source_is_registered_for_failures(self):
        self.assertEqual(inbox.SOURCE_LABELS["drafts"], "열린 초안(이슈·PR) 목록")
        self.assertEqual(inbox.SOURCE_PREFIXES["drafts"], ("draft:",))
        item, = inbox.failure_items([("drafts", "HTTP 500")], URL)
        self.assertEqual((item.id, item.level, item.title), ("source:drafts", "check", "조회 실패 — 열린 초안(이슈·PR) 목록"))


class PullRequestDraftAlertTest(unittest.TestCase):
    """초안 PR 한 건은 한 줄만 남는다: 열린 PR 규칙이 이미 action 이면 그 줄, 아니면 초안 항목.
    저장소 기본 토큰이 연 PR 은 검사가 돌지 않아 열린 PR 규칙으로는 알림 없는 '검사 결과 없음'(check)으로 남기 때문이다(GitHub 규칙)."""

    def ids(self, pulls=(), drafts=(), **kw):
        return {i.id for i in inbox.build_items(snap(pulls=list(pulls), drafts=list(drafts), **kw))}

    def pr_draft(self, number=15, **kw):
        kw.setdefault("hours", 3)
        return h.make_draft(number, "[초안][Chance] 승인 대기 글", "Chance", pull=True, **kw)

    def test_a_pull_request_without_checks_is_announced_by_the_draft_item_and_the_silent_pull_item_goes(self):
        alone = inbox.build_items(snap(pulls=[h.make_pull(15, ci="none")]))
        self.assertEqual([(i.id, i.level) for i in alone], [("pr:15:no_ci", "check")])                # 초안 표시가 없으면 알림 없는 확인 항목
        items = inbox.build_items(snap(pulls=[h.make_pull(15, ci="none")], drafts=[self.pr_draft()]))
        self.assertEqual([(i.id, i.level) for i in items], [("draft:15:wait", "action")])
        self.assertEqual(inbox.plan_notice(items, None), (["draft:15:wait"], ["draft:15:wait"]))

    def test_every_pull_state_that_is_not_an_action_is_replaced_by_the_draft_item(self):
        states = {"no_ci": h.make_pull(15, ci="none"), "pending": h.make_pull(15, ci="pending"), "unknown": h.make_pull(15, ci="unknown"),
                  "blocked": h.make_pull(15, state="blocked"), "calculating": h.make_pull(15, mergeable=None), "error": dict(h.make_pull(15), error="HTTP 500")}
        for name, pull in states.items():
            alone = {i.level for i in inbox.build_items(snap(pulls=[pull]))}
            self.assertNotIn("action", alone, name)                                                # 대조: 초안 표시가 없으면 어느 것도 알림이 아니다
            self.assertEqual(self.ids([pull], [self.pr_draft()]), {"draft:15:wait"}, name)

    def test_every_pull_state_the_pull_rule_alerts_on_stays_and_the_draft_item_steps_aside(self):
        states = {"ready": h.make_pull(15), "conflict": h.make_pull(15, mergeable=False, state="dirty"), "ci_fail": h.make_pull(15, ci="fail")}
        for name, pull in states.items():
            self.assertEqual(self.ids([pull], [self.pr_draft()]), {f"pr:15:{name}"}, name)         # 같은 PR 이 두 번 알림이 되지 않는다
            self.assertEqual(self.ids([pull], [self.pr_draft(hours=100)]), {f"pr:15:{name}"}, name)

    def test_a_github_draft_pull_request_or_an_unlisted_one_is_still_announced(self):
        # 열린 PR 규칙은 GitHub 의 draft 상태 PR 을 건너뛰므로 초안 항목이 유일한 알림이다
        self.assertEqual(self.ids([h.make_pull(15, draft=True)], [self.pr_draft()]), {"draft:15:wait"})
        self.assertEqual(self.ids([], [self.pr_draft()]), {"draft:15:wait"})

    def test_only_the_draft_pull_requests_own_item_is_replaced(self):
        pulls = [h.make_pull(15, ci="none"), h.make_pull(16, ci="none"), h.make_pull(17)]
        self.assertEqual(self.ids(pulls, [self.pr_draft(15)]), {"draft:15:wait", "pr:16:no_ci", "pr:17:ready"})

    def test_an_issue_draft_never_replaces_a_pull_item_even_with_the_same_number(self):
        self.assertEqual(self.ids([h.make_pull(15, ci="none")], [h.make_draft(15)]), {"draft:15:wait", "pr:15:no_ci"})

    def test_a_pull_request_that_is_not_a_pending_draft_keeps_its_pull_item(self):
        for kw in ({"state": "closed"}, {"extra_labels": ("폐기",)}, {"login": "stranger", "assoc": "NONE"}, {"draft_label": False}):
            draft = h.make_draft(15, "[초안][Chance] 글", "Chance", pull=True, **kw)
            self.assertEqual(self.ids([h.make_pull(15, ci="none")], [draft]), {"pr:15:no_ci"}, kw)

    def test_a_stranger_pull_request_with_the_label_is_never_hidden_or_announced_as_a_draft(self):
        # 라벨은 누구든 흉내 낼 수 있는 표시다: 낯선 작성자의 포크 PR 은 라벨이 있어도 '외부 사용자의 PR' 확인 항목 그대로다
        fork = h.make_pull(15, login="stranger", assoc="NONE", fork=True)
        draft = h.make_draft(15, "[초안][Chance] 글", "Chance", pull=True, login="stranger", assoc="NONE")
        self.assertEqual({(i.id, i.level) for i in inbox.build_items(snap(pulls=[fork], drafts=[draft]))}, {("pr:15:external", "check")})

    def test_a_stale_pull_request_draft_is_one_check_line_and_not_a_new_alert(self):
        pull = h.make_pull(15, ci="none", created=ago(hours=100))
        items = inbox.build_items(snap(pulls=[pull], drafts=[self.pr_draft(hours=100)]))
        self.assertEqual([(i.id, i.level) for i in items], [("draft:15:stale", "check")])
        self.assertEqual(inbox.plan_notice(items, ["draft:15:wait"]), ([], []))

    def test_when_the_checks_finish_the_pull_rule_takes_over_and_that_is_announced_as_a_new_state(self):
        waiting = inbox.build_items(snap(pulls=[h.make_pull(15, ci="pending")], drafts=[self.pr_draft()]))
        _, kept = inbox.plan_notice(waiting, None)
        self.assertEqual(kept, ["draft:15:wait"])
        done = inbox.build_items(snap(pulls=[h.make_pull(15)], drafts=[self.pr_draft()]))
        self.assertEqual(inbox.plan_notice(done, kept), (["pr:15:ready"], ["pr:15:ready"]))

    def test_a_failed_pull_lookup_still_announces_the_draft(self):
        for source in ("pulls", "pull_details"):
            items = inbox.build_items(snap(pulls=[], drafts=[self.pr_draft()], failures=[(source, "HTTP 500")]))
            self.assertIn(("draft:15:wait", "action"), [(i.id, i.level) for i in items], source)

    def test_the_result_does_not_depend_on_input_order_or_repeats(self):
        pulls = [h.make_pull(n, ci="none") for n in (17, 15, 16)]
        drafts = [self.pr_draft(16), self.pr_draft(15), self.pr_draft(15)]
        first = inbox.build_items(snap(pulls=pulls, drafts=drafts))
        self.assertEqual([i.id for i in first], ["draft:15:wait", "draft:16:wait", "pr:17:no_ci"])
        self.assertEqual(first, inbox.build_items(snap(pulls=list(reversed(pulls)), drafts=list(reversed(drafts)))))

    def test_the_pull_helper_reads_only_pull_item_ids(self):
        read = inbox._pull_number
        item = lambda item_id: inbox.Item(item_id, "info", "x")
        self.assertEqual([read(item(i)) for i in ("pr:15:ready", "pr:7:no_ci", "pr:x:ready", "draft:15:wait", "pr:15", "pr:15:a:b", "run:15:x", "pr::x")],
                         [15, 7, None, None, None, None, None, None])


class DraftNoticeTest(unittest.TestCase):
    """새 초안만 코멘트로 알리는 규칙(기존 표식 방식 그대로)."""

    def test_a_new_draft_is_announced_once_and_not_again(self):
        items = inbox.build_items(snap(drafts=[h.make_draft(41)]))
        new, kept = inbox.plan_notice(items, None)
        self.assertEqual((new, kept), (["draft:41:wait"], ["draft:41:wait"]))
        self.assertEqual(inbox.plan_notice(items, kept)[0], [])

    def test_closing_a_draft_removes_it_and_reopening_announces_it_again(self):
        listed = inbox.build_items(snap(drafts=[h.make_draft(41)]))
        _, kept = inbox.plan_notice(listed, None)
        gone = inbox.build_items(snap(drafts=[]))
        new, kept_after = inbox.plan_notice(gone, kept)
        self.assertEqual((new, kept_after), ([], []))
        self.assertEqual(inbox.plan_notice(listed, kept_after)[0], ["draft:41:wait"])

    def test_a_failed_draft_lookup_keeps_the_announced_ids_so_recovery_is_silent(self):
        listed = inbox.build_items(snap(drafts=[h.make_draft(41)]))
        _, kept = inbox.plan_notice(listed, None)
        failing = inbox.build_items(snap(drafts=[], failures=[("drafts", "HTTP 500")]))
        new, kept_while_failing = inbox.plan_notice(failing, kept, [("drafts", "HTTP 500")])
        self.assertEqual((new, kept_while_failing), ([], ["draft:41:wait"]))
        self.assertEqual(inbox.plan_notice(listed, kept_while_failing)[0], [])         # 복구돼도 같은 초안을 또 알리지 않는다

    def test_a_failed_draft_lookup_does_not_hide_other_sources_ids(self):
        _, kept = inbox.plan_notice(inbox.build_items(snap(pulls=[h.make_pull(15)], drafts=[h.make_draft(41)])), None)
        self.assertEqual(kept, ["draft:41:wait", "pr:15:ready"])
        new, kept_now = inbox.plan_notice(inbox.build_items(snap(pulls=[h.make_pull(15)], failures=[("drafts", "x")])), kept, [("drafts", "x")])
        self.assertEqual((new, kept_now), ([], ["draft:41:wait", "pr:15:ready"]))
        new, kept_now = inbox.plan_notice(inbox.build_items(snap(pulls=[], failures=[("drafts", "x")])), kept, [("drafts", "x")])
        self.assertEqual(kept_now, ["draft:41:wait"])                                  # PR 이 사라진 것은 그대로 반영된다


# ----------------------------------------------------------------------------
# 초안 현황 표
# ----------------------------------------------------------------------------
class DraftBoardTest(unittest.TestCase):
    HEADER = "| 채널 | 대기 초안 | 가장 오래된 | 최신 초안 |"

    def board(self, **kw):
        kw.setdefault("blogs", blogs4())
        return inbox.draft_board(snap(**kw))

    def test_every_registry_channel_has_a_row_even_with_nothing_pending(self):
        board = self.board(histories={"blogger_macat": []})
        self.assertTrue(board.startswith("## 초안 현황\n\n" + self.HEADER + "\n|---|---|---|---|\n"))
        self.assertEqual(table_rows(board), [["Chance", "자동 공개", "-", "-"], ["Blogger", "0", "-", "-"], ["티스토리", "0", "-", "-"], ["네이버", "정지", "-", "-"]])

    def test_rows_follow_the_registry_order_and_stopped_channels_say_stopped(self):
        blogs = list(reversed(blogs4()))
        self.assertEqual([row[0] for row in table_rows(self.board(blogs=blogs, histories={"blogger_macat": []}))], ["네이버", "티스토리", "Blogger", "Chance"])
        stopped = table_rows(self.board(blogs=blogs4(blogger_mode="off")))
        self.assertEqual(stopped[1], ["Blogger", "정지", "-", "-"])

    def test_github_drafts_are_counted_per_channel_with_oldest_age_and_the_newest_as_a_link(self):
        drafts = [h.make_draft(41, "[초안][티스토리] 맛집 지도 만드는 법", hours=30), h.make_draft(43, "[초안][티스토리] 최신 글", hours=100),
                  h.make_draft(45, "[초안][티스토리] 가장 최근 글", hours=2)]
        rows = table_rows(self.board(drafts=drafts, histories={"blogger_macat": []}))
        self.assertEqual(rows[2], ["티스토리", "3", "4일", f"[#45 가장 최근 글]({URL}/issues/45)"])
        self.assertEqual(rows[3], ["네이버", "정지", "-", "-"])

    def test_the_oldest_age_counts_whole_days_and_under_a_day_says_so(self):
        for hours, shown in ((1, "1일 미만"), (23, "1일 미만"), (24, "1일"), (47, "1일"), (48, "2일"), (24 * 10 + 5, "10일")):
            row = table_rows(self.board(drafts=[h.make_draft(41, hours=hours)], histories={"blogger_macat": []}))[2]
            self.assertEqual(row[2], shown, hours)

    def test_a_pull_request_draft_links_to_the_pull_page(self):
        row = table_rows(self.board(drafts=[h.make_draft(15, "[초안][Chance] 승인 대기 글", "Chance", hours=3, pull=True)], histories={"blogger_macat": []}))[0]
        self.assertEqual(row, ["Chance", "1", "1일 미만", f"[#15 승인 대기 글]({URL}/pull/15)"])

    def test_chance_is_automatic_publishing_unless_the_registry_says_pr(self):
        self.assertEqual(table_rows(self.board(blogs=blogs4("direct")))[0][1], "자동 공개")
        self.assertEqual(table_rows(self.board(blogs=blogs4("pr")))[0][1], "0")
        self.assertEqual(table_rows(self.board(blogs=blogs4("pr"), drafts=[h.make_draft(15, "[초안][Chance] 글", "Chance", pull=True)]))[0][1], "1")

    def test_drafts_that_exist_are_never_hidden_behind_the_automatic_publishing_label(self):
        row = table_rows(self.board(drafts=[h.make_draft(15, "[초안][Chance] 글", "Chance", pull=True)]))[0]
        self.assertEqual(row[1], "1")

    def test_a_stopped_channel_with_pending_drafts_shows_the_count_and_says_stopped(self):
        row = table_rows(self.board(drafts=[h.make_draft(51, "[초안][네이버] 글", "네이버", hours=3)]))[3]
        self.assertEqual(row[:3], ["네이버", "1 (정지 중)", "1일 미만"])

    def test_channel_names_match_ignoring_case(self):
        row = table_rows(self.board(drafts=[h.make_draft(41, channel="티스토리"), h.make_draft(42, channel="Chance")]))
        self.assertEqual(row[2][1], "1")
        blogs = [h.channel_blog("b", "Blogger 영문", "tistory", "package")]
        self.assertEqual(table_rows(inbox.draft_board(snap(blogs=blogs, drafts=[h.make_draft(1, channel="blogger 영문")])))[0][1], "1")

    # --- Blogger: 이력의 draft_uploaded 를 센 대략치
    def blogger_row(self, history, **kw):
        return table_rows(self.board(histories={"blogger_macat": history}, **kw))[1]

    def test_blogger_counts_uploaded_drafts_of_the_last_14_days_as_an_estimate(self):
        history = [h.make_entry("draft_uploaded", ago(days=2)), h.make_entry("draft_uploaded", ago(days=5)), h.make_entry("draft_uploaded", ago(days=13, hours=23)),
                   h.make_entry("draft_uploaded", ago(days=15)), h.make_entry("posted", ago(days=1)), h.make_entry("draft", ago(days=1)),
                   h.make_entry("generated_unpublished", ago(days=1)), h.make_entry("publish_failed", ago(days=1)), h.make_entry("rejected", ago(days=1))]
        row = self.blogger_row(history)
        self.assertEqual(row[:3], ["Blogger", "3 (대략)", "13일"])
        self.assertEqual(row[3], inbox.fmt_kst(inbox.parse_time(ago(days=2))))      # 마지막 초안함 업로드 시각(링크 없음)
        self.assertNotIn("](", row[3])
        self.assertEqual(inbox.DRAFT_WINDOW_DAYS, 14)

    def test_blogger_window_edge_and_unreadable_entries(self):
        edge = NOW - timedelta(days=14)
        history = [h.make_entry("draft_uploaded", edge.strftime("%Y-%m-%dT%H:%M:%SZ")),
                   h.make_entry("draft_uploaded", (edge - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")),
                   h.make_entry("draft_uploaded", None), "문자열", None, {"status": "draft_uploaded", "date": "bad"}]
        self.assertEqual(self.blogger_row(history)[1], "1 (대략)")

    def test_blogger_without_uploaded_drafts_is_zero_and_without_a_history_it_is_a_lookup_failure(self):
        self.assertEqual(self.blogger_row([h.make_entry("posted", ago(days=1))])[1:], ["0", "-", "-"])
        self.assertEqual(self.blogger_row([])[1:], ["0", "-", "-"])
        row = table_rows(self.board(histories={}))[1]
        self.assertEqual(row, ["Blogger", "조회 실패", "-", "-"])
        self.assertEqual(table_rows(self.board(histories={"blogger_macat": "깨짐"}))[1][1], "조회 실패")

    def test_a_stopped_blogger_ignores_its_history(self):
        history = [h.make_entry("draft_uploaded", ago(days=1))]
        self.assertEqual(table_rows(self.board(blogs=blogs4(blogger_mode="off"), histories={"blogger_macat": history}))[1], ["Blogger", "정지", "-", "-"])

    def test_blogger_history_entries_with_only_a_slot_or_a_date_are_counted_with_their_precision(self):
        history = [h.make_entry("draft_uploaded", date="2026-10-24", slot=11), h.make_entry("draft_uploaded", date="2026-10-20")]
        row = self.blogger_row(history)
        self.assertEqual(row[1], "2 (대략)")
        self.assertEqual(row[3], "2026-10-24 11시 슬롯(KST)")

    def test_the_blogger_note_explains_the_estimate_without_a_link(self):
        board = self.board(histories={"blogger_macat": []})
        self.assertIn("Blogger 대시보드 → 글 → 초안", board)
        self.assertIn("대략치", board)
        self.assertIn("이미 게시했는지는 Blogger 쪽 사실이라 여기서는 알 수 없습니다", board)
        self.assertIn("최근 14일", board)
        note = next(line for line in board.splitlines() if "Blogger 대시보드" in line)
        self.assertNotIn("](", note)
        self.assertNotIn("blogger.com", board)

    def test_the_model_note_says_how_an_issue_draft_and_a_pull_request_draft_each_leave_the_table(self):
        board = self.board(histories={"blogger_macat": []})
        note = next(line for line in board.splitlines() if "라벨 `초안`과" in line)
        self.assertEqual(note, f"- {inbox.BOARD_NOTE_MODEL}")
        for phrase in ("열린 이슈·PR 입니다", "이슈 초안은 발행한 뒤 닫고", "PR 초안은 병합하면 빠지며", "라벨 `폐기`를 붙이거나 닫으세요", "하루에 한 번 바뀝니다"):
            self.assertIn(phrase, note, phrase)

    def test_the_blogger_note_is_left_out_when_no_blogger_channel_exists(self):
        blogs = [b for b in blogs4() if b["platform"] != "blogger"]
        self.assertNotIn("Blogger 대시보드", self.board(blogs=blogs))

    def test_the_blogger_note_is_left_out_while_the_blogger_channel_is_stopped_and_comes_back_when_it_runs(self):
        stopped = self.board(blogs=blogs4(blogger_mode="off"))
        self.assertNotIn("Blogger 대시보드", stopped)
        self.assertNotIn("대략치", stopped)
        self.assertEqual(table_rows(stopped)[1], ["Blogger", "정지", "-", "-"])
        for mode in ("draft", "auto"):
            self.assertIn("Blogger 대시보드", self.board(blogs=blogs4(blogger_mode=mode), histories={"blogger_macat": []}), mode)
        self.assertEqual(inbox.board_rows(snap(blogs=blogs4(blogger_mode="off")))[2], False)
        self.assertEqual(inbox.board_rows(snap(blogs=blogs4(blogger_mode="draft"), histories={"blogger_macat": []}))[2], True)

    # --- 조회 실패
    def test_a_failed_draft_lookup_marks_the_github_rows_but_not_the_static_ones(self):
        rows = table_rows(self.board(failures=[("drafts", "HTTP 500")], histories={"blogger_macat": []}))
        self.assertEqual([r[1] for r in rows], ["자동 공개", "0", "조회 실패", "정지"])

    def test_a_failed_draft_lookup_marks_chance_when_it_uses_pull_requests(self):
        rows = table_rows(self.board(blogs=blogs4("pr"), failures=[("drafts", "x")], histories={"blogger_macat": []}))
        self.assertEqual(rows[0][1], "조회 실패")

    def test_a_lookup_failure_of_another_source_changes_nothing(self):
        rows = table_rows(self.board(failures=[("pulls", "x"), ("runs", "y")], histories={"blogger_macat": []}))
        self.assertEqual([r[1] for r in rows], ["자동 공개", "0", "0", "정지"])

    # --- 레지스트리에 없는 채널·채널 표시 없음
    def test_drafts_of_an_unregistered_channel_get_their_own_row_after_the_registry_rows(self):
        drafts = [h.make_draft(61, "[초안][새채널] 글", "새채널"), h.make_draft(62, "[초안] 표시 없음", None), h.make_draft(63, "[초안][가나] 글", "가나")]
        rows = table_rows(self.board(drafts=drafts, histories={"blogger_macat": []}))
        self.assertEqual([r[0] for r in rows], ["Chance", "Blogger", "티스토리", "네이버", "가나 (미등록)", "새채널 (미등록)", "(채널 표시 없음)"])
        self.assertEqual(rows[-1][1], "1")
        self.assertEqual(rows[-3][3], f"[#63 글]({URL}/issues/63)")

    def test_only_unregistered_drafts_still_make_a_table_when_the_registry_has_no_channels(self):
        board = inbox.draft_board(snap(blogs=[h.make_blog()], drafts=[h.make_draft(61, channel="새채널")]))
        self.assertEqual([r[0] for r in table_rows(board)], ["새채널 (미등록)"])
        self.assertEqual(inbox.draft_board(snap(blogs=[h.make_blog()])), "")
        self.assertEqual(inbox.draft_board(snap()), "")

    def test_the_table_is_capped_and_extra_unregistered_channels_are_merged_into_one_row(self):
        drafts = [h.make_draft(100 + n, f"[초안] 글 {n}", f"채널{n:02d}") for n in range(30)]
        rows = table_rows(self.board(drafts=drafts, histories={"blogger_macat": []}))
        self.assertEqual(len(rows), inbox.BOARD_ROWS_MAX)
        self.assertEqual([r[0] for r in rows[:4]], ["Chance", "Blogger", "티스토리", "네이버"])
        merged = rows[-1]
        self.assertEqual(merged[0], f"그 밖의 채널 {30 - (inbox.BOARD_ROWS_MAX - 4 - 1)}개")
        self.assertEqual(int(merged[1]), 30 - (inbox.BOARD_ROWS_MAX - 4 - 1))
        self.assertEqual(sum(int(r[1]) for r in rows[4:]), 30)                                    # 줄여도 합계는 그대로

    def test_registry_rows_are_never_dropped_by_the_cap(self):
        many = [h.channel_blog(f"b{n}", f"채널{n}", "tistory", "package") for n in range(20)]
        rows = table_rows(inbox.draft_board(snap(blogs=many, drafts=[h.make_draft(1, channel="미등록")])))
        self.assertEqual(len(rows), 21)
        self.assertEqual(rows[-1][0], "미등록 (미등록)")

    def test_a_blog_that_repeats_a_channel_label_or_has_none_adds_no_row(self):
        blogs = blogs4() + [h.channel_blog("dup", "Chance", "jekyll-git", "auto"), h.make_blog("nochannel"), {"key": "x", "channel": "문자열"}, None]
        self.assertEqual([r[0] for r in table_rows(inbox.draft_board(snap(blogs=blogs, histories={"blogger_macat": []})))], ["Chance", "Blogger", "티스토리", "네이버"])

    # --- 외부 글
    def test_external_text_in_titles_and_labels_cannot_break_the_table_or_the_page(self):
        drafts = [h.make_draft(41, "[초안][티스토리] " + EVIL), h.make_draft(42, "[초안] x", "새채널" + EVIL)]
        board = self.board(drafts=drafts, histories={"blogger_macat": []})
        self.assertNotIn(TOKEN, board)
        for line in board.splitlines():
            self.assertFalse(line.lstrip().startswith("::"), line)
            self.assertNotIn("##[", line)
            self.assertNotIn("@", line)
            self.assertNotIn("<", line)
        for row in table_rows(board):
            self.assertEqual(len(row), 4, row)
        self.assertEqual(len([line for line in board.splitlines() if line.startswith("| ")]), 6)                # 머리 1 + 줄 5(레지스트리 4 + 미등록 1)
        self.assertNotIn("](https://evil", board)

    def test_pipes_in_titles_become_full_width_bars(self):
        row = table_rows(self.board(drafts=[h.make_draft(41, "[초안][티스토리] 가 | 나 | 다")], histories={"blogger_macat": []}))[2]
        self.assertEqual(len(row), 4)
        self.assertIn("가 ｜ 나 ｜ 다", row[3])

    def test_a_long_title_is_clipped_in_the_table(self):
        row = table_rows(self.board(drafts=[h.make_draft(41, "[초안][티스토리] " + "가" * 200)], histories={"blogger_macat": []}))[2]
        self.assertTrue(row[3].startswith("[#41 " + "가" * 23 + "…]("), row[3])                  # 표 안의 제목은 24자(…까지)

    # --- 모바일 필터 링크
    def test_mobile_filter_links_are_percent_encoded_search_urls(self):
        self.assertEqual(inbox.draft_filter_url(URL), f"{URL}/issues?q=is%3Aopen+label%3A%EC%B4%88%EC%95%88")
        self.assertEqual(urllib.parse.unquote_plus(inbox.draft_filter_url(URL, "티스토리").split("?q=")[1]), 'is:open label:초안 label:"채널:티스토리"')
        self.assertEqual(urllib.parse.unquote_plus(inbox.draft_filter_url(URL, "Blogger 영문").split("?q=")[1]), 'is:open label:초안 label:"채널:Blogger 영문"')
        self.assertTrue(inbox.draft_filter_url(URL, "티스토리", pulls=True).startswith(f"{URL}/pulls?q="))
        quoted = urllib.parse.unquote_plus(inbox.draft_filter_url(URL, '가"나').split("?q=")[1])
        self.assertEqual(quoted, 'is:open label:초안 label:"채널:가나"')                  # 라벨 안의 따옴표는 검색어의 따옴표 짝을 깨므로 뺀다(짝은 정확히 둘)
        self.assertEqual(quoted.count('"'), 2)
        for url in (inbox.draft_filter_url(URL), inbox.draft_filter_url(URL, "Blogger 영문", pulls=True), inbox.draft_filter_url(URL, "새채널")):
            self.assertEqual(inbox.safe_url(url), url)                                    # 링크로 쓸 수 있는 모양

    def test_the_section_ends_with_filter_links_for_all_drafts_and_for_each_github_channel(self):
        board = self.board(histories={"blogger_macat": []})
        last = board.rstrip("\n").splitlines()[-1]
        self.assertTrue(last.startswith("- 휴대폰에서 거르기: "))
        links = re.findall(r"\[([^\]]+)\]\((https://[^)]+)\)", last)
        self.assertEqual([text for text, _url in links], ["대기 초안 전체(이슈)", "대기 초안 전체(PR)", "티스토리", "네이버"])      # Blogger·자동 공개 Chance 는 GitHub 에 초안이 없다
        decoded = [urllib.parse.unquote_plus(url.split("?q=")[1]) for _text, url in links]
        self.assertEqual(decoded[2], 'is:open label:초안 label:"채널:티스토리"')

    def test_pull_request_channels_get_a_pull_link_too(self):
        board = self.board(blogs=blogs4("pr"), histories={"blogger_macat": []})
        links = re.findall(r"\[([^\]]+)\]\((https://[^)]+)\)", board.rstrip("\n").splitlines()[-1])
        self.assertEqual([text for text, _url in links], ["대기 초안 전체(이슈)", "대기 초안 전체(PR)", "Chance", "Chance PR", "티스토리", "네이버"])
        self.assertIn("/pulls?q=", dict(links)["Chance PR"])
        self.assertIn("/issues?q=", dict(links)["Chance"])

    def test_unregistered_channels_with_drafts_are_linked_too(self):
        board = self.board(drafts=[h.make_draft(61, channel="새채널", pull=True)], histories={"blogger_macat": []})
        links = re.findall(r"\[([^\]]+)\]\((https://[^)]+)\)", board.rstrip("\n").splitlines()[-1])
        self.assertIn("새채널", [text for text, _url in links])
        self.assertIn("새채널 PR", [text for text, _url in links])

    def test_a_channel_label_that_is_not_plain_text_gets_a_row_but_no_link(self):
        """주소에는 ext() 를 쓸 수 없어, 레지스트리에 없는 채널 라벨이 평범한 글자가 아니면(멘션·HTML·비밀 값 모양·너무 긺) 링크를 만들지 않는다."""
        odd = ["새채널@everyone", "새<b>채널", "새&#64;채널", "새채널\n::error::x", 'a"b', "채널|칸", "[피싱](https://evil.example)", "가" * 41, "ghs_" + "Q" * 36,
               "-시작", ".시작", "슬래시/채널", "채널:중복"]
        for label in odd:
            board = self.board(drafts=[h.make_draft(61, channel=label)], histories={"blogger_macat": []})
            self.assertEqual(len(table_rows(board)), 5, label)                           # 줄은 남는다(레지스트리 4 + 미등록 1)
            urls = re.findall(r"\((https://[^)]+)\)", board.rstrip("\n").splitlines()[-1])
            self.assertEqual(len(urls), 4, label)                                       # 전체 2 + 티스토리·네이버. 이 라벨의 링크는 없다
            self.assertNotIn(TOKEN, board)
            self.assertNotIn("evil", board.rstrip("\n").splitlines()[-1], label)

    def test_plain_labels_are_linked_including_spaces_digits_and_dots(self):
        for label in ("Blogger 영문", "채널2", "a.b-c_d", "가" * 40, "A"):
            board = self.board(drafts=[h.make_draft(61, channel=label)], histories={"blogger_macat": []})
            last = board.rstrip("\n").splitlines()[-1]
            decoded = [urllib.parse.unquote_plus(url) for url in re.findall(r"\((https://[^)]+)\)", last)]
            self.assertTrue(any(f'label:"채널:{label}"' in url for url in decoded), label)

    def test_a_registry_channel_with_an_odd_label_has_a_row_but_no_link(self):
        blogs = [h.channel_blog("a", "티스토리@x", "tistory", "package")]
        board = inbox.draft_board(snap(blogs=blogs))
        self.assertEqual(len(table_rows(board)), 1)
        self.assertEqual(len(re.findall(r"\((https://[^)]+)\)", board.rstrip("\n").splitlines()[-1])), 2)

    def test_the_channel_cell_of_a_registry_channel_is_neutralised_and_clipped_like_any_external_text(self):
        """레지스트리는 검증 없이 읽으므로(검증은 CI) 채널 라벨도 외부 글처럼 다룬다: 멘션·HTML·표 구분자는 바뀌고 30자를 넘으면 잘린다."""
        blogs = [h.channel_blog("a", "티스토리@x <b>|", "tistory", "package"), h.channel_blog("b", "나" * 45, "naver", "package")]
        rows = table_rows(inbox.draft_board(snap(blogs=blogs)))
        self.assertEqual(rows[0][0], "티스토리＠x ＜b>｜")
        self.assertEqual(rows[1][0], "나" * 29 + "…")

    def test_link_text_is_clipped_to_30_characters_while_the_address_keeps_the_whole_label(self):
        label = "가" * 35
        board = self.board(drafts=[h.make_draft(61, channel=label)], histories={"blogger_macat": []})
        links = re.findall(r"\[([^\]]+)\]\((https://[^)]+)\)", board.rstrip("\n").splitlines()[-1])
        text, url = links[-1]
        self.assertEqual(text, "가" * 29 + "…")
        self.assertIn(urllib.parse.quote_plus(label), url)

    def test_of_drafts_with_the_same_created_time_the_higher_number_is_the_newest(self):
        same = ago(hours=10)
        drafts = [h.make_draft(51, "[초안][티스토리] 뒤 번호", created=same), h.make_draft(50, "[초안][티스토리] 앞 번호", created=same)]
        row = table_rows(self.board(drafts=drafts, histories={"blogger_macat": []}))[2]
        self.assertIn("[#51 뒤 번호]", row[3])
        self.assertEqual(row[1], "2")

    def test_a_draft_with_an_unreadable_created_time_counts_but_is_never_the_newest_or_the_oldest(self):
        unknown = h.make_draft(60, "[초안][티스토리] 시각 모름")
        unknown["created_at"] = None
        known = h.make_draft(61, "[초안][티스토리] 시각 있음", hours=30)
        row = table_rows(self.board(drafts=[unknown, known], histories={"blogger_macat": []}))[2]
        self.assertEqual((row[1], row[2]), ("2", "1일"))                                   # 가장 오래된은 시각을 아는 것 중에서
        self.assertIn("[#61 시각 있음]", row[3])                                            # 시각을 모르는 것은 최신으로 뽑히지 않는다
        only = table_rows(self.board(drafts=[unknown], histories={"blogger_macat": []}))[2]
        self.assertEqual(only[1:3], ["1", "-"])                                           # 시각을 하나도 모르면 일수는 '-'
        self.assertIn("[#60 시각 모름]", only[3])

    # --- 결정성
    def test_same_input_gives_the_same_text_in_any_order(self):
        drafts = [h.make_draft(n, f"[초안][티스토리] 글 {n}", "티스토리" if n % 2 else "네이버", hours=n * 7) for n in range(1, 12)]
        first = self.board(drafts=drafts, histories={"blogger_macat": []})
        shuffled = list(drafts)
        random.Random(3).shuffle(shuffled)
        self.assertEqual(first, self.board(drafts=shuffled, histories={"blogger_macat": []}))
        reversed_blogs = self.board(blogs=blogs4(), drafts=drafts, histories={"blogger_macat": []})
        self.assertEqual(first, reversed_blogs)

    def test_the_text_does_not_depend_on_the_clock_except_through_whole_days(self):
        drafts = [h.make_draft(41, hours=30)]
        a = inbox.draft_board(snap(now=NOW, blogs=blogs4(), drafts=drafts, histories={"blogger_macat": []}))
        b = inbox.draft_board(snap(now=NOW + timedelta(hours=3), blogs=blogs4(), drafts=drafts, histories={"blogger_macat": []}))
        self.assertEqual(a, b)                                                               # 같은 날 안(1일 → 1일)이면 글자가 같다
        c = inbox.draft_board(snap(now=NOW + timedelta(hours=20), blogs=blogs4(), drafts=drafts, histories={"blogger_macat": []}))
        self.assertNotEqual(a, c)                                                            # 하루가 바뀌면 가장 오래된 칸만 바뀐다
        self.assertEqual(a.replace("| 1일 |", "| 2일 |"), c)

    def test_bad_repository_names_are_rejected(self):
        for bad in ("", "no-slash", "../x", None):
            with self.assertRaises(ValueError, msg=bad):
                inbox.draft_board(snap(repo=bad))

    def test_a_naive_now_is_treated_as_utc(self):
        naive = inbox.draft_board(snap(now=datetime(2026, 10, 25, 6, 0), blogs=blogs4(), drafts=[h.make_draft(41)], histories={"blogger_macat": []}))
        self.assertEqual(naive, self.board(drafts=[h.make_draft(41)], histories={"blogger_macat": []}))

    def test_rows_and_links_helper_returns_the_data_behind_the_markdown(self):
        rows, links, blogger = inbox.board_rows(snap(blogs=blogs4(), drafts=[h.make_draft(41)], histories={"blogger_macat": []}))
        self.assertEqual([r[0] for r in rows], ["Chance", "Blogger", "티스토리", "네이버"])
        self.assertTrue(blogger)
        self.assertEqual([text for text, _url in links], ["티스토리", "네이버"])


# ----------------------------------------------------------------------------
# render(board=…)
# ----------------------------------------------------------------------------
class RenderBoardTest(unittest.TestCase):
    def full(self):
        snapshot = snap(blogs=blogs4(), drafts=[h.make_draft(41, hours=30), h.make_draft(43, hours=100)], pulls=[h.make_pull(15)],
                        histories={"blogger_macat": []}, issues=[h.make_watchdog(9)])
        return snapshot, inbox.build_items(snapshot), inbox.draft_board(snapshot)

    def test_without_a_board_the_text_is_what_it_was_before(self):
        _snapshot, items, _board = self.full()
        self.assertEqual(inbox.render(items, URL), inbox.render(items, URL, inbox.BODY_LIMIT, board=""))
        self.assertEqual(inbox.render(items, URL), inbox.render(items, URL, board=None))
        self.assertNotIn("초안 현황", inbox.render(items, URL))

    def test_the_board_sits_between_the_summary_header_and_the_item_sections(self):
        _snapshot, items, board = self.full()
        text = inbox.render(items, URL, board=board)
        header = text.index("**지금 해야 할 일")
        at = text.index("## 초안 현황")
        sections = [text.index(f"## {title}") for title in ("지금 해야 할 일", "확인하면 좋은 것", "참고")]
        self.assertLess(header, at)
        self.assertLess(at, min(sections))
        self.assertEqual(sections, sorted(sections))
        self.assertIn(board.strip(), text)
        self.assertIn("\n\n## 지금 해야 할 일", text)
        self.assertIn(inbox.render(items, URL).split("## 지금 해야 할 일")[1], text)           # 항목 구역은 그대로

    def test_the_item_counts_in_the_summary_include_the_draft_items(self):
        _snapshot, items, board = self.full()
        self.assertEqual(sum(1 for i in items if i.id.startswith("draft:")), 2)
        text = inbox.render(items, URL, board=board)
        counts = {level: sum(1 for i in items if i.level == level) for level in inbox.LEVELS}
        self.assertIn(f"**지금 해야 할 일 {counts['action']}건** · 확인하면 좋은 것 {counts['check']}건 · 참고 {counts['info']}건", text)
        self.assertIn("초안 대기 — 시험 글", text)
        self.assertIn("초안 3일 넘게 대기 — 시험 글", text)

    def test_an_empty_item_list_still_shows_the_board(self):
        text = inbox.render([], URL, board=inbox.draft_board(snap(blogs=blogs4(), histories={"blogger_macat": []})))
        self.assertIn("지금 확인할 것이 없습니다", text)
        self.assertIn("## 초안 현황", text)

    def test_the_text_never_exceeds_the_limit_and_the_board_is_dropped_before_it_could_break_it(self):
        _snapshot, items, board = self.full()
        for limit in range(560, 5200, 37):
            text = inbox.render(items, URL, limit, board=board)
            self.assertLessEqual(len(text), limit, limit)
        big = inbox.render(items, URL, inbox.BODY_LIMIT, board=board)
        self.assertIn("## 초안 현황", big)

    def test_a_board_that_does_not_fit_is_replaced_by_one_line(self):
        _snapshot, items, board = self.full()
        limits = range(560, 12000, 7)
        omitted = [limit for limit in limits if inbox.BOARD_OMITTED in inbox.render(items, URL, limit, board=board)]
        full = [limit for limit in limits if "| 채널 |" in inbox.render(items, URL, limit, board=board)]
        self.assertTrue(omitted and full)
        self.assertLess(max(omitted), min(full))                                      # 길이가 늘면 '없음 → 한 줄 안내 → 표' 순서로 바뀌고 되돌아가지 않는다
        self.assertFalse(set(omitted) & set(full))
        for limit in omitted:
            self.assertNotIn("| 채널 |", inbox.render(items, URL, limit, board=board))
        self.assertIn("실행 요약(Actions)", inbox.BOARD_OMITTED)

    def test_the_board_takes_its_place_before_items_so_items_are_cut_first(self):
        _snapshot, _items, board = self.full()
        items = [inbox.Item(f"pr:{n}:ready", "action", f"PR {n} " + "가" * 100, "나" * 400, f"{URL}/pull/{n}", "다" * 200) for n in range(1, 401)]
        text = inbox.render(items, URL, board=board)
        self.assertLessEqual(len(text), inbox.BODY_LIMIT)
        self.assertIn("## 초안 현황", text)
        self.assertRegex(text, r"… 외 \d+건은 길이 제한으로 줄였습니다")

    def test_the_summary_limit_keeps_the_board_whole(self):
        _snapshot, items, board = self.full()
        self.assertIn(board.strip(), inbox.render(items, URL, inbox.SUMMARY_LIMIT, board=board))

    def test_the_body_with_a_board_still_fits_the_github_limit_with_a_full_marker(self):
        _snapshot, _items, board = self.full()
        ids = [("x" * 77 + f"{n:03d}") for n in range(inbox.MARKER_IDS_MAX)]
        items = [inbox.Item(i, "action", "가" * 110, "나" * 420, f"{URL}/pull/{n}", "다" * 260) for n, i in enumerate(ids)]
        items += [inbox.Item(f"stat:{n}", "info", "라" * 110, "마" * 420) for n in range(300)]
        body = inbox.build_body(inbox.render(items, URL, board=board), ids)
        self.assertLessEqual(len(body), 65536)

    def test_the_board_text_is_part_of_the_body_hash_so_a_changed_table_is_rewritten(self):
        snapshot, items, board = self.full()
        a = inbox.render(items, URL, board=board)
        other = inbox.draft_board(snap(blogs=blogs4(), drafts=[h.make_draft(41, hours=30)], histories={"blogger_macat": []}))
        b = inbox.render(items, URL, board=other)
        self.assertTrue(inbox.needs_update(inbox.parse_marker(inbox.build_body(a, [])), b, []))
        self.assertFalse(inbox.needs_update(inbox.parse_marker(inbox.build_body(a, [])), a, []))

    def test_no_line_of_the_board_can_start_a_workflow_command_or_mention_anyone(self):
        drafts = [h.make_draft(41, "[초안][티스토리] " + EVIL), h.make_draft(42, "[초안] x", "새채널" + EVIL)]
        snapshot = snap(blogs=blogs4(), drafts=drafts, histories={"blogger_macat": []})
        text = inbox.render(inbox.build_items(snapshot), URL, board=inbox.draft_board(snapshot))
        for line in text.splitlines():
            self.assertFalse(line.lstrip().startswith("::"), line)
            self.assertNotIn("##[", line)
        body = text.split("\n---\n")[0]
        for raw in ("@", "<"):
            self.assertNotIn(raw, body)
        self.assertNotIn(TOKEN, text)


# ----------------------------------------------------------------------------
# scripts/ops_inbox.py — 읽기
# ----------------------------------------------------------------------------
class FetchDraftsTest(unittest.TestCase):
    def setUp(self):
        self.fake = h.FakeGitHub()
        self.failures, self.notes = [], []

    def fetch(self):
        return oi.fetch_drafts(self.fake, self.failures, self.notes)

    def test_it_asks_for_open_issues_and_pull_requests_with_the_draft_label_one_page_at_a_time(self):
        self.fake.issues = [h.make_draft_raw(41), h.make_draft_raw(42, pull=True, channel="Chance"), h.make_issue(7, "다른 이슈", labels=("bug",)),
                            h.make_draft_raw(43, state="closed"), h.make_issue(8, "[Watchdog] x", labels=("watchdog",))]
        drafts = self.fetch()
        self.assertEqual(self.fake.log, [("GET", "/issues", {"state": "open", "labels": "초안", "per_page": 100, "page": 1})])
        self.assertEqual([(d["number"], d["kind"]) for d in drafts], [(41, "issue"), (42, "pull")])
        self.assertEqual((self.failures, self.notes), ([], []))

    def test_a_short_first_page_costs_one_call_and_full_pages_continue(self):
        self.fake.issues = [h.make_draft_raw(n) for n in range(1, 251)]
        drafts = self.fetch()
        self.assertEqual(len(drafts), 250)
        self.assertEqual([entry[2]["page"] for entry in self.fake.log], [1, 2, 3])
        self.assertEqual(self.notes, [])
        self.assertEqual(len({d["number"] for d in drafts}), 250)

    def test_exactly_one_full_page_asks_for_the_next_page_and_stops_when_it_is_empty(self):
        self.fake.issues = [h.make_draft_raw(n) for n in range(1, 101)]
        self.assertEqual(len(self.fetch()), 100)
        self.assertEqual([entry[2]["page"] for entry in self.fake.log], [1, 2])
        self.assertEqual(self.notes, [])

    def test_at_most_three_pages_are_read_and_a_note_says_there_may_be_more(self):
        self.fake.issues = [h.make_draft_raw(n) for n in range(1, 401)]
        drafts = self.fetch()
        self.assertEqual(len(drafts), 300)
        self.assertEqual(len(self.fake.log), oi.MAX_DRAFT_PAGES)
        self.assertEqual(self.notes[0][0], "drafts_cap")
        self.assertIn("300", self.notes[0][1])

    def test_exactly_three_full_pages_also_get_the_note_because_a_fourth_page_could_exist(self):
        self.fake.issues = [h.make_draft_raw(n) for n in range(1, 301)]
        self.assertEqual(len(self.fetch()), 300)
        self.assertEqual([n[0] for n in self.notes], ["drafts_cap"])

    def test_a_failed_call_discards_everything_and_leaves_one_failure(self):
        self.fake.issues = [h.make_draft_raw(n) for n in range(1, 151)]
        self.fake.fail = [(r"GET /issues\?.*page=2", oi.ApiError("HTTP 500", status=500))]
        self.assertEqual(self.fetch(), [])
        self.assertEqual(self.failures, [("drafts", "HTTP 500")])
        self.assertEqual(self.notes, [])

    def test_a_failure_on_the_first_page_is_recorded_the_same_way(self):
        self.fake.fail = [(r"GET /issues", oi.ApiError("HTTP 403: 한도", status=403))]
        self.assertEqual(self.fetch(), [])
        self.assertEqual(self.failures, [("drafts", "HTTP 403: 한도")])

    def test_budget_exhaustion_is_a_failure_not_a_crash(self):
        fake = h.FakeGitHub(max_calls=0)
        failures = []
        self.assertEqual(oi.fetch_drafts(fake, failures, []), [])
        self.assertEqual(failures[0][0], "drafts")

    def test_an_answer_that_is_not_a_list_is_a_failure(self):
        class Odd(h.FakeGitHub):
            def get(self, path, **params):
                return {"message": "이상한 응답"}
        failures = []
        self.assertEqual(oi.fetch_drafts(Odd(), failures, []), [])
        self.assertEqual(failures, [("drafts", "응답이 목록이 아닙니다")])

    def test_entries_without_a_number_are_skipped_and_the_rest_is_normalised(self):
        class Odd(h.FakeGitHub):
            def get(self, path, **params):
                return [{"title": "번호 없음"}, "문자열", None, h.make_draft_raw(41)]
        drafts = oi.fetch_drafts(Odd(), [], [])
        self.assertEqual([d["number"] for d in drafts], [41])

    def test_the_documented_page_constants(self):
        self.assertEqual((oi.MAX_DRAFT_PAGES, oi.DRAFTS_PER_PAGE, oi.MAX_LABEL_CREATES), (3, 100, 10))


# ----------------------------------------------------------------------------
# scripts/ops_inbox.py — 초안 모델 라벨 만들기
# ----------------------------------------------------------------------------
class DraftLabelsTest(unittest.TestCase):
    def setUp(self):
        self.fake = h.FakeGitHub()
        self.out = []
        self.specs = inbox.draft_label_specs(blogs4())

    def ensure(self, specs=None):
        oi.ensure_draft_labels(self.fake, self.specs if specs is None else specs, self.out.append)

    def test_missing_labels_are_created_with_the_fixed_colour_and_description(self):
        self.ensure()
        self.assertEqual(self.fake.labels, {"초안", "폐기", "채널:Chance", "채널:Blogger", "채널:티스토리", "채널:네이버"})
        self.assertEqual(self.fake.log[0], ("GET", "/labels", {"per_page": 100}))
        self.assertEqual(len(self.fake.writes()), 6)
        for name, payload in self.fake.label_payloads.items():
            self.assertEqual(set(payload), {"name", "color", "description"})
        self.assertEqual(self.fake.label_payloads["초안"]["color"], inbox.DRAFT_LABEL_SPECS[0][1])
        self.assertEqual(self.fake.label_payloads["폐기"]["description"], inbox.DRAFT_LABEL_SPECS[1][2])
        self.assertEqual(self.fake.label_payloads["채널:티스토리"], {"name": "채널:티스토리", "color": inbox.CHANNEL_LABEL_COLOR, "description": "초안이 속한 채널: 티스토리"})
        self.assertEqual(len([line for line in self.out if line.startswith("[라벨]")]), 1)
        self.assertIn("6개", self.out[0])

    def test_labels_that_exist_are_not_created_again_and_the_second_run_costs_one_read(self):
        self.ensure()
        calls = len(self.fake.log)
        self.out.clear()
        self.ensure()
        self.assertEqual(len(self.fake.log), calls + 1)
        self.assertEqual(self.fake.log[-1][:2], ("GET", "/labels"))
        self.assertEqual(self.out, [])

    def test_existing_labels_are_found_ignoring_case_and_only_the_missing_ones_are_created(self):
        self.fake.labels = {"초안", "채널:chance"}
        self.ensure()
        self.assertEqual([entry[2]["name"] for entry in self.fake.writes()], ["폐기", "채널:Blogger", "채널:티스토리", "채널:네이버"])

    def test_an_unreadable_list_makes_it_try_everything_and_an_existing_label_ends_in_422_quietly(self):
        self.fake.labels = {"초안"}
        self.fake.fail = [(r"GET /labels", oi.ApiError("HTTP 500", status=500))]
        self.ensure()
        self.assertEqual(len(self.fake.writes()), 6)
        self.assertEqual(self.fake.labels, {"초안", "폐기", "채널:Chance", "채널:Blogger", "채널:티스토리", "채널:네이버"})
        self.assertEqual(len([line for line in self.out if line.startswith("[참고]")]), 0)
        self.assertIn("5개", self.out[0])

    def test_a_list_that_is_not_a_list_is_treated_as_unreadable(self):
        class Odd(h.FakeGitHub):
            def get(self, path, **params):
                self._enter("GET", path, params)
                return {"message": "이상함"}
        fake = Odd()
        oi.ensure_draft_labels(fake, self.specs, self.out.append)
        self.assertEqual(len(fake.writes()), 6)

    def test_a_non_422_failure_stops_after_one_plain_line_and_the_rest_waits_for_the_next_run(self):
        self.fake.fail = [(r"POST /labels", oi.ApiError("HTTP 500: " + TOKEN + "\n::error::위조 @everyone <b>x</b>", status=403))]
        self.ensure()
        self.assertEqual(len(self.fake.writes()), 1)                                # 첫 실패에서 멈춘다
        lines = [line for line in self.out if line.startswith("[참고]")]
        self.assertEqual(len(lines), 1)
        for raw in ("\n", "::", "@", "<", TOKEN):
            self.assertNotIn(raw, lines[0], raw)
        self.assertIn("초안", lines[0])
        self.assertEqual(self.fake.labels, set())

    def test_a_failure_after_some_labels_were_made_reports_both(self):
        original = self.fake.post

        def post(path, payload):
            if payload["name"] == "채널:Blogger":
                raise oi.ApiError("HTTP 500", status=500)
            return original(path, payload)
        self.fake.post = post
        self.ensure()
        self.assertEqual(self.fake.labels, {"초안", "폐기", "채널:Chance"})
        self.assertTrue(any(line.startswith("[라벨]") and "3개" in line for line in self.out))
        self.assertTrue(any(line.startswith("[참고]") and "채널:Blogger" in line for line in self.out))

    def test_a_422_in_the_middle_is_skipped_without_a_line_and_the_rest_continues(self):
        self.fake.fail = [(r"POST /labels", oi.ApiError("HTTP 422: already_exists", status=422))]
        self.ensure()
        self.assertEqual(len(self.fake.writes()), 6)
        self.assertEqual(self.out, [])

    def test_the_call_budget_stops_it_quietly_with_one_line(self):
        fake = h.FakeGitHub(max_calls=3)
        oi.ensure_draft_labels(fake, self.specs, self.out.append)
        self.assertEqual(fake.calls, 3)
        self.assertEqual(len(fake.labels), 2)
        self.assertEqual(len([line for line in self.out if line.startswith("[참고]")]), 1)

    def test_no_budget_at_all_skips_the_whole_step_with_one_line(self):
        fake = h.FakeGitHub(max_calls=0)
        oi.ensure_draft_labels(fake, self.specs, self.out.append)
        self.assertEqual(fake.log, [])
        self.assertEqual(len(self.out), 1)
        self.assertIn("건너뜁니다", self.out[0])

    def test_at_most_ten_labels_are_created_in_one_run(self):
        specs = [{"name": f"채널:가{n}", "color": "bfdadc", "description": "x"} for n in range(25)]
        self.ensure(specs)
        self.assertEqual(len(self.fake.writes()), oi.MAX_LABEL_CREATES)

    def test_no_specs_means_one_read_and_nothing_else(self):
        self.ensure([])
        self.assertEqual([entry[:2] for entry in self.fake.log], [("GET", "/labels")])
        self.assertEqual(self.out, [])


# ----------------------------------------------------------------------------
# scripts/ops_inbox.py — 전체 실행(가짜 GitHub)
# ----------------------------------------------------------------------------
ENV = {"GITHUB_REPOSITORY": h.REPO, "GITHUB_TOKEN": TOKEN, "GITHUB_REPOSITORY_OWNER": "octo"}


class RunWithDraftsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.summary = self.tmp / "summary.md"
        self.out = []

    def world(self, drafts=(), history=None, registry=None):
        root = h.make_root(self.tmp / "repo", histories={"history.json": [], "blogger_history.json": history or []},
                           blogs_json=h.CHANNEL_REGISTRY if registry is None else registry)
        fake = h.FakeGitHub()
        fake.issues = list(drafts)
        fake.runs = {name: [h.make_run(i, ago(hours=1 + i))] for i, name in enumerate(("chanceblog.yml", "blogger.yml", "watchdog.yml", "guardrails.yml"), start=1)}
        return fake, root

    def run_script(self, fake, root, env=None, now=NOW):
        environ = dict(ENV, GITHUB_STEP_SUMMARY=str(self.summary), **(env or {}))
        return oi.run(environ, fake, now, root, self.out.append, sleep=lambda seconds: None)

    def inbox_issue(self, fake):
        return [i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE][0]

    def body(self, fake):
        return self.inbox_issue(fake)["body"]

    def test_a_new_tistory_draft_shows_in_the_board_the_items_and_one_alert(self):
        fake, root = self.world([h.make_draft_raw(41, "[초안][티스토리] 맛집 지도 만드는 법", "티스토리", hours=30)])
        self.assertEqual(self.run_script(fake, root), 0)
        body = self.body(fake)
        self.assertIn("## 초안 현황", body)
        rows = table_rows(body)
        self.assertEqual([r[0] for r in rows], ["Chance", "Blogger", "티스토리", "네이버"])
        self.assertEqual(rows[2], ["티스토리", "1", "1일", f"[#41 맛집 지도 만드는 법]({URL}/issues/41)"])
        self.assertIn("초안 대기 — 맛집 지도 만드는 법", body)
        comments = fake.comments[self.inbox_issue(fake)["number"]]
        self.assertEqual(len(comments), 1)
        self.assertIn("초안 대기 — 맛집 지도 만드는 법", comments[0])
        self.assertTrue(comments[0].startswith("@octo "))
        self.assertIn("draft:41:wait", inbox.parse_marker(body).items)

    def test_the_run_summary_has_the_same_board(self):
        fake, root = self.world([h.make_draft_raw(41, "[초안][티스토리] 글", "티스토리")])
        self.run_script(fake, root)
        text = self.summary.read_text(encoding="utf-8")
        self.assertIn("## 초안 현황", text)
        self.assertEqual(table_rows(text), table_rows(self.body(fake)))

    def test_the_draft_lookup_asks_once_and_only_once_per_run_when_it_fits_in_one_page(self):
        fake, root = self.world([h.make_draft_raw(41)])
        self.run_script(fake, root)
        asks = [entry for entry in fake.log if entry[0] == "GET" and entry[1] == "/issues" and entry[2].get("labels") == "초안"]
        self.assertEqual(len(asks), 1)

    def test_a_second_run_changes_nothing_and_writes_nothing_even_for_labels(self):
        fake, root = self.world([h.make_draft_raw(41)])
        self.run_script(fake, root)
        before = copy.deepcopy(fake.issues)
        writes = len(fake.writes())
        self.out.clear()
        self.run_script(fake, root)
        self.assertEqual(len(fake.writes()), writes)
        self.assertEqual(fake.issues, before)
        self.assertTrue(any("변경 없음" in line for line in self.out))

    def test_closing_the_draft_removes_it_from_the_board_and_the_items_without_an_alert(self):
        fake, root = self.world([h.make_draft_raw(41)])
        self.run_script(fake, root)
        number = self.inbox_issue(fake)["number"]
        fake.find(41)["state"] = "closed"
        self.run_script(fake, root)
        body = self.body(fake)
        self.assertEqual(table_rows(body)[2][:2], ["티스토리", "0"])
        self.assertNotIn("초안 대기", body)
        self.assertEqual(len(fake.comments[number]), 1)                                     # 새 알림 없음

    def test_discarding_by_label_also_removes_it(self):
        fake, root = self.world([h.make_draft_raw(41)])
        self.run_script(fake, root)
        fake.find(41)["labels"].append({"name": "폐기"})
        self.run_script(fake, root)
        self.assertEqual(table_rows(self.body(fake))[2][:2], ["티스토리", "0"])

    def test_an_old_draft_is_a_check_item_and_does_not_alert(self):
        fake, root = self.world([h.make_draft_raw(43, "[초안][티스토리] 오래된 글", "티스토리", hours=100)])
        self.run_script(fake, root)
        body = self.body(fake)
        self.assertIn("초안 3일 넘게 대기 — 오래된 글", body)
        self.assertIn("## 확인하면 좋은 것", body)
        self.assertEqual(self.inbox_issue(fake)["number"] in fake.comments, False)
        self.assertEqual(table_rows(body)[2][:3], ["티스토리", "1", "4일"])

    def pull_world(self, checks, **pull_kw):
        """Chance 승인 흐름의 초안 PR 한 건(작성자 github-actions 봇)과 그 PR 의 열린 PR 목록·상세·검사 기록."""
        draft = h.make_draft_raw(15, "[초안][Chance] 승인 대기 글", "Chance", hours=3, pull=True)
        fake, root = self.world([draft])
        fake.pulls = [h.make_pull_raw(15, title="[초안][Chance] 승인 대기 글", sha="c" * 40, login=h.BOT, user_type="Bot", assoc="CONTRIBUTOR", **pull_kw)]
        fake.details = {15: {"mergeable": True, "mergeable_state": "clean"}}
        fake.check_runs = {"c" * 40: checks}
        return fake, root

    def test_a_pull_request_draft_the_pull_rule_alerts_on_is_counted_but_alerted_only_once(self):
        fake, root = self.pull_world([h.make_check("validate")])
        self.run_script(fake, root)
        body = self.body(fake)
        self.assertEqual(table_rows(body)[0][:3], ["Chance", "1", "1일 미만"])
        self.assertEqual(body.count("PR #15 병합하면 됩니다"), 1)
        self.assertNotIn("초안 대기", body)
        self.assertEqual(inbox.parse_marker(body).items, ("pr:15:ready",))

    def test_a_pull_request_draft_without_checks_is_announced_as_a_draft_with_one_comment(self):
        # 저장소 기본 토큰이 연 PR 은 검사가 돌지 않는다 — 열린 PR 규칙만으로는 알림 없는 '검사 결과 없음'이 되던 경우
        fake, root = self.pull_world([])
        self.assertEqual(self.run_script(fake, root), 0)
        body = self.body(fake)
        self.assertIn("초안 대기 — 승인 대기 글", body)
        self.assertIn("PR #15", body)
        self.assertIn(f"{URL}/pull/15", body)
        self.assertNotIn("검사 결과 없음", body)                                   # 같은 PR 의 열린 PR 줄은 빠졌다
        self.assertEqual(body.count("#15"), body.count("PR #15") + body.count("[#15 "))     # 번호는 PR 로만 나온다(이슈 #15 로 읽히지 않는다)
        self.assertEqual(table_rows(body)[0][:3], ["Chance", "1", "1일 미만"])
        self.assertEqual(inbox.parse_marker(body).items, ("draft:15:wait",))
        comments = fake.comments[self.inbox_issue(fake)["number"]]
        self.assertEqual(len(comments), 1)
        self.assertTrue(comments[0].startswith("@octo "))
        self.assertIn("초안 대기 — 승인 대기 글", comments[0])
        before = len(fake.writes())
        self.run_script(fake, root)
        self.assertEqual(len(fake.writes()), before)                              # 두 번째 점검은 아무것도 쓰지 않는다

    def test_a_github_draft_state_pull_request_with_the_label_is_announced(self):
        fake, root = self.pull_world([], draft=True)
        self.run_script(fake, root)
        body = self.body(fake)
        self.assertIn("초안 대기 — 승인 대기 글", body)
        self.assertEqual(inbox.parse_marker(body).items, ("draft:15:wait",))

    def test_a_failed_draft_lookup_shows_in_the_board_and_as_a_check_item_and_keeps_the_marker(self):
        fake, root = self.world([h.make_draft_raw(41)])
        self.run_script(fake, root)
        number = self.inbox_issue(fake)["number"]
        original_get = fake.get

        def get(path, **params):
            if path == "/issues" and params.get("labels") == "초안":
                fake._enter("GET", path, params)
                raise oi.ApiError("HTTP 500", status=500)
            return original_get(path, **params)
        fake.get = get
        self.run_script(fake, root)
        body = self.body(fake)
        self.assertEqual(table_rows(body)[2][1], "조회 실패")
        self.assertIn("조회 실패 — 열린 초안(이슈·PR) 목록", body)
        self.assertIn("draft:41:wait", inbox.parse_marker(body).items)                     # 알린 것은 표식에 남는다
        fake.get = original_get
        self.run_script(fake, root)
        self.assertEqual(len(fake.comments[number]), 1)                                      # 복구돼도 같은 초안을 또 알리지 않는다
        self.assertEqual(table_rows(self.body(fake))[2][:2], ["티스토리", "1"])

    def test_blogger_uploaded_drafts_show_as_an_estimate_in_the_board(self):
        history = [h.make_entry("draft_uploaded", ago(days=2)), h.make_entry("draft_uploaded", ago(days=3))]
        fake, root = self.world(history=history)
        self.run_script(fake, root)
        row = table_rows(self.body(fake))[1]
        self.assertEqual(row[:3], ["Blogger", "2 (대략)", "3일"])
        self.assertIn("Blogger 대시보드 → 글 → 초안", self.body(fake))

    def test_stranger_drafts_are_not_counted_or_alerted(self):
        fake, root = self.world([h.make_draft_raw(41, login="stranger", assoc="NONE"), h.make_draft_raw(42, login="octo", assoc="OWNER")])
        self.run_script(fake, root)
        body = self.body(fake)
        self.assertEqual(table_rows(body)[2][1], "1")
        self.assertIn("#42", body)
        self.assertNotIn("#41", body)

    def test_the_board_is_not_written_when_the_registry_has_no_channels(self):
        fake, root = self.world(registry=h.SYNTHETIC_REGISTRY)
        self.run_script(fake, root)
        self.assertNotIn("초안 현황", self.body(fake))
        self.assertNotIn("초안 현황", self.summary.read_text(encoding="utf-8"))

    def test_the_real_registry_gives_chance_and_blogger_rows_with_nothing_pending(self):
        fake, root = self.world(registry=(_bootstrap.ROOT / "pipeline" / "blogs.json").read_text(encoding="utf-8"))
        self.run_script(fake, root)
        rows = table_rows(self.body(fake))
        self.assertEqual(rows[0], ["Chance", "자동 공개", "-", "-"])
        self.assertEqual(rows[1], ["Blogger", "정지", "-", "-"])
        self.assertEqual(len(rows), 2)
        self.assertNotIn("Blogger 대시보드", self.body(fake))                          # 정지 중인 Blogger 의 대략치 안내는 붙이지 않는다
        self.assertEqual(self.body(fake).count("- 휴대폰에서 거르기:"), 1)

    # --- 라벨
    def test_the_draft_labels_are_created_after_the_issue_is_written(self):
        fake, root = self.world()
        self.run_script(fake, root)
        self.assertEqual(fake.labels, {"ops-inbox", "초안", "폐기", "채널:Chance", "채널:Blogger", "채널:티스토리", "채널:네이버"})
        names = [entry[2]["name"] for entry in fake.writes() if entry[1] == "/labels"]
        issue_write = next(i for i, entry in enumerate(fake.log) if entry[0] == "POST" and entry[1] == "/issues")
        first_label = next(i for i, entry in enumerate(fake.log) if entry[0] == "POST" and entry[1] == "/labels" and entry[2]["name"] == "초안")
        self.assertGreater(first_label, issue_write)
        self.assertEqual(names[0], "ops-inbox")
        self.assertTrue(any(line.startswith("[라벨] 초안 모델의 라벨 6개") for line in self.out))

    def test_a_dry_run_and_a_run_without_a_token_never_create_labels(self):
        fake, root = self.world([h.make_draft_raw(41)])
        self.assertEqual(self.run_script(fake, root, env={"INBOX_DRY_RUN": "true"}), 0)
        self.assertEqual(fake.writes(), [])
        self.assertFalse(any(entry[1] == "/labels" for entry in fake.log))
        self.assertTrue(any("(연습)" in line for line in self.out))
        env = {k: v for k, v in ENV.items() if k != "GITHUB_TOKEN"}
        self.assertEqual(oi.run(env, fake, NOW, root, self.out.append, sleep=lambda seconds: None), 0)
        self.assertEqual(fake.writes(), [])
        self.assertFalse(any(entry[1] == "/labels" for entry in fake.log))

    def test_a_dry_run_still_prints_the_board(self):
        fake, root = self.world([h.make_draft_raw(41, "[초안][티스토리] 연습 글", "티스토리")])
        self.run_script(fake, root, env={"INBOX_DRY_RUN": "true"})
        printed = "\n".join(self.out)
        self.assertIn("## 초안 현황", printed)
        self.assertIn("[#41 연습 글]", printed)

    def test_when_the_issue_write_fails_no_label_is_created_and_the_exit_code_is_one(self):
        fake, root = self.world()
        fake.fail = [(r"POST /issues$", oi.ApiError("HTTP 403", status=403))]
        self.assertEqual(self.run_script(fake, root), 1)
        self.assertFalse(any(entry[0] == "POST" and entry[1] == "/labels" and entry[2]["name"] == "초안" for entry in fake.log))

    def test_a_failing_label_step_never_changes_the_exit_code_or_the_issue(self):
        fake, root = self.world([h.make_draft_raw(41)])
        original = fake.post

        def post(path, payload):
            if path == "/labels" and payload["name"] != "ops-inbox":
                raise oi.ApiError("HTTP 500", status=500)
            return original(path, payload)
        fake.post = post
        self.assertEqual(self.run_script(fake, root), 0)
        self.assertIn("초안 대기", self.body(fake))
        self.assertTrue(any(line.startswith("[참고] 초안 라벨") for line in self.out))
        self.assertEqual(len([line for line in self.out if line.startswith("::")]), 0)

    def test_a_comment_failure_still_exits_one_after_the_label_step(self):
        fake, root = self.world([h.make_draft_raw(41)])
        fake.fail = [(r"POST /issues/\d+/comments", oi.ApiError("HTTP 500", status=500))]
        self.assertEqual(self.run_script(fake, root), 1)
        self.assertIn("초안", fake.labels)

    def test_the_call_budget_is_enough_for_a_normal_run(self):
        fake, root = self.world([h.make_draft_raw(n) for n in range(41, 51)])
        self.assertEqual(self.run_script(fake, root), 0)
        self.assertLessEqual(fake.calls, 40)

    def test_with_the_write_reserve_the_label_step_is_best_effort_and_the_issue_still_gets_written(self):
        fake, root = self.world([h.make_draft_raw(41)])
        fake.max_calls, fake.reserve = 40, oi.WRITE_RESERVE
        code = self.run_script(fake, root)
        self.assertEqual(code, 0)
        self.assertIn("초안 대기", self.body(fake))

    def test_hostile_draft_text_never_reaches_the_issue_the_comment_or_the_log_unneutralised(self):
        fake, root = self.world([h.make_draft_raw(41, "[초안][티스토리] " + EVIL, "티스토리"), h.make_draft_raw(42, "[초안] x", "새채널" + EVIL)])
        self.run_script(fake, root)
        issue = self.inbox_issue(fake)
        everything = "\n".join(self.out) + self.summary.read_text(encoding="utf-8") + issue["title"] + issue["body"] + json.dumps(fake.comments, ensure_ascii=False)
        self.assertNotIn(TOKEN, everything)                    # 초안 이슈들의 원본(가짜 GitHub 자료)이 아니라 이 모음이 쓴 곳만 본다
        for block in (self.body(fake).split("\n\n<!--")[0], *fake.comments[self.inbox_issue(fake)["number"]], self.summary.read_text(encoding="utf-8")):
            for line in block.splitlines():
                self.assertFalse(line.lstrip().startswith("::"), line)
                self.assertNotIn("##[", line)
        for comment in fake.comments[self.inbox_issue(fake)["number"]]:
            self.assertEqual(comment.count("@"), 1)                                         # 소유자 멘션 하나뿐
            self.assertNotIn("<", comment)


# ----------------------------------------------------------------------------
# 워크플로 구조
# ----------------------------------------------------------------------------
class _Expr:
    """워크플로 job `if` 식(`||`·`&&`·`==`·`!=`·괄호·문자열·`contains()`·`a.b.*.c` 참조)을 GitHub 규칙대로 계산하는 작은 해석기."""
    TOKEN = re.compile(r"\s*(?:(?P<op>\|\||&&|==|!=|[(),!])|'(?P<str>(?:[^']|'')*)'|(?P<id>[A-Za-z_][A-Za-z0-9_.*\-]*))")

    def __init__(self, source, context):
        self.tokens, pos, src = [], 0, source.strip()
        while pos < len(src):
            match = self.TOKEN.match(src, pos)
            if not match:
                raise ValueError(f"읽을 수 없는 식: {src[pos:pos + 30]!r}")
            pos = match.end()
            if match.group("op"):
                self.tokens.append(("op", match.group("op")))
            elif match.group("str") is not None:
                self.tokens.append(("val", match.group("str").replace("''", "'")))
            else:
                self.tokens.append(("id", match.group("id")))
        self.i, self.context = 0, context

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        self.i += 1
        return token

    @staticmethod
    def truthy(value):
        return not (value is None or value is False or value == 0 or value == "" or value == [])

    def parse(self):
        value = self.or_()
        if self.i != len(self.tokens):
            raise ValueError("식 끝에 남은 토큰이 있습니다")
        return value

    def or_(self):
        value = self.and_()
        while self.peek() == ("op", "||"):
            self.take()
            right = self.and_()
            value = value if self.truthy(value) else right
        return value

    def and_(self):
        value = self.eq()
        while self.peek() == ("op", "&&"):
            self.take()
            right = self.eq()
            value = right if self.truthy(value) else value
        return value

    def eq(self):
        value = self.unary()
        while self.peek() in (("op", "=="), ("op", "!=")):
            op = self.take()[1]
            right = self.unary()
            same = value.casefold() == right.casefold() if isinstance(value, str) and isinstance(right, str) else value == right
            value = same if op == "==" else not same
        return value

    def unary(self):
        if self.peek() == ("op", "!"):
            self.take()
            return not self.truthy(self.unary())
        return self.primary()

    def primary(self):
        kind, text = self.take()
        if (kind, text) == ("op", "("):
            value = self.or_()
            assert self.take() == ("op", ")")
            return value
        if kind == "val":
            return text
        if kind == "id" and self.peek() == ("op", "("):
            self.take()
            args = [self.or_()]
            while self.peek() == ("op", ","):
                self.take()
                args.append(self.or_())
            assert self.take() == ("op", ")")
            assert text == "contains", text
            haystack, needle = args
            if isinstance(haystack, list):
                return any(isinstance(item, str) and isinstance(needle, str) and item.casefold() == needle.casefold() for item in haystack)
            return isinstance(haystack, str) and isinstance(needle, str) and needle.casefold() in haystack.casefold()
        if kind == "id":
            return {"true": True, "false": False, "null": None}[text] if text in ("true", "false", "null") else self.lookup(text)
        raise ValueError(f"예상하지 못한 토큰 {kind} {text}")

    def lookup(self, path):
        nodes = [self.context]
        for part in path.split("."):
            nxt = []
            for node in nodes:
                if part == "*":
                    nxt += node if isinstance(node, list) else []
                elif isinstance(node, dict):
                    nxt.append(node.get(part))
                else:
                    nxt.append(None)
            nodes = nxt
        return nodes if ".*." in path else (nodes[0] if nodes else None)


def load_workflow():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


def job_runs(event_name, issue_labels=None, pr_labels=None, event_label=None, head_repo=h.REPO, repo=h.REPO):
    """주어진 이벤트에서 job 이 도는가(job `if` 계산)."""
    wf = load_workflow()
    event = {}
    if issue_labels is not None:
        event["issue"] = {"labels": [{"name": n} for n in issue_labels]}
    if pr_labels is not None:
        event["pull_request"] = {"labels": [{"name": n} for n in pr_labels], "head": {"repo": {"full_name": head_repo}}}
    if event_label is not None:
        event["label"] = {"name": event_label}
    context = {"github": {"event_name": event_name, "event": event, "repository": repo}}
    return bool(_Expr(wf["jobs"]["inbox"]["if"], context).parse() is True)


class DraftWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.wf = load_workflow()
        self.job = self.wf["jobs"]["inbox"]
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_the_event_triggers_are_exactly_the_five_draft_event_types_and_nothing_else(self):
        on = self.wf["on"]
        self.assertEqual(set(on), {"schedule", "workflow_dispatch", "issues", "pull_request"})
        self.assertEqual(on["issues"], {"types": ["opened", "closed", "reopened", "labeled", "unlabeled"]})
        self.assertEqual(on["pull_request"], {"types": ["opened", "closed", "reopened", "labeled", "unlabeled"]})
        self.assertNotIn("pull_request_target", on)
        self.assertNotIn("workflow_run", on)
        self.assertNotIn("issue_comment", on)
        self.assertEqual([entry["cron"] for entry in on["schedule"]], ["40 */2 * * *"])               # 예약은 그대로

    def test_manual_dispatch_keeps_its_dry_run_input(self):
        inputs = self.wf["on"]["workflow_dispatch"]["inputs"]
        self.assertEqual(list(inputs), ["dry_run"])
        self.assertEqual((inputs["dry_run"]["type"], inputs["dry_run"]["default"]), ("boolean", False))

    def test_the_job_runs_for_schedule_and_manual_runs_always(self):
        self.assertTrue(job_runs("schedule"))
        self.assertTrue(job_runs("workflow_dispatch"))

    def test_issue_events_run_only_for_issues_that_carry_the_draft_label(self):
        for event in ("opened", "closed", "reopened", "labeled"):
            self.assertTrue(job_runs("issues", issue_labels=["초안", "채널:티스토리"]), event)
        self.assertTrue(job_runs("issues", issue_labels=["bug", "초안"]))
        self.assertFalse(job_runs("issues", issue_labels=[]))
        self.assertFalse(job_runs("issues", issue_labels=["bug", "ops-inbox", "watchdog", "blog-control", "폐기", "채널:티스토리"]))
        self.assertFalse(job_runs("issues", issue_labels=["초안 아님", "draft"]))

    def test_removing_the_draft_label_still_refreshes_the_board(self):
        self.assertTrue(job_runs("issues", issue_labels=["채널:티스토리"], event_label="초안"))                  # unlabeled: 라벨을 막 뗐다
        self.assertFalse(job_runs("issues", issue_labels=["채널:티스토리"], event_label="채널:티스토리"))         # 다른 라벨을 뗀 것
        self.assertFalse(job_runs("issues", issue_labels=[], event_label="bug"))

    def test_labelling_with_something_else_matters_only_when_the_draft_label_is_there(self):
        self.assertTrue(job_runs("issues", issue_labels=["초안", "폐기"], event_label="폐기"))                  # 폐기를 붙이면 표에서 빠진다
        self.assertFalse(job_runs("issues", issue_labels=["bug"], event_label="bug"))

    def test_pull_request_events_run_only_for_this_repositorys_draft_pull_requests(self):
        self.assertTrue(job_runs("pull_request", pr_labels=["초안", "채널:Chance"]))
        self.assertTrue(job_runs("pull_request", pr_labels=["채널:Chance"], event_label="초안"))
        self.assertFalse(job_runs("pull_request", pr_labels=["bug"]))
        self.assertFalse(job_runs("pull_request", pr_labels=[]))
        self.assertFalse(job_runs("pull_request", pr_labels=["bug"], event_label="bug"))

    def test_fork_pull_requests_never_run_even_with_the_draft_label(self):
        self.assertFalse(job_runs("pull_request", pr_labels=["초안"], head_repo="stranger/blog"))
        self.assertFalse(job_runs("pull_request", pr_labels=["채널:Chance"], event_label="초안", head_repo="stranger/blog"))
        self.assertFalse(job_runs("pull_request", pr_labels=["초안"], head_repo=""))
        self.assertFalse(job_runs("pull_request", pr_labels=["초안"], head_repo="Octo/Blog-x"))
        self.assertTrue(job_runs("pull_request", pr_labels=["초안"], head_repo="octo/blog"))

    def test_other_events_never_run_the_job(self):
        for event in ("push", "issue_comment", "pull_request_target", "workflow_run", "release", ""):
            self.assertFalse(job_runs(event, issue_labels=["초안"], pr_labels=["초안"], event_label="초안"), event)

    def test_the_condition_text_reads_only_labels_the_event_label_the_head_repository_and_the_event_name(self):
        refs = set(re.findall(r"github\.[A-Za-z_.*]+", self.job["if"]))
        self.assertEqual(refs, {"github.event_name", "github.event.issue.labels.*.name", "github.event.label.name",
                               "github.event.pull_request.head.repo.full_name", "github.repository", "github.event.pull_request.labels.*.name"})

    def test_event_values_are_never_written_into_a_shell_command_or_the_environment(self):
        for step in self.job["steps"]:
            if "run" in step:
                self.assertNotIn("${{", step["run"])
            for value in (step.get("env") or {}).values():
                self.assertNotRegex(str(value), r"github\.event\.(issue|pull_request|comment|label|head_commit)")
        for forbidden in ("github.event.issue.title", "github.event.issue.body", "github.event.pull_request.title", "github.event.pull_request.body",
                          "github.head_ref", "github.event.pull_request.head.ref", "github.event.pull_request.head.label", "github.event.label.description"):
            self.assertNotIn(forbidden, self.text, forbidden)

    def test_pull_request_events_check_out_the_default_branch_not_the_pull_request_code(self):
        checkout = next(s for s in self.job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@"))
        ref = checkout["with"]["ref"]
        self.assertIn("github.event_name == 'pull_request'", ref)
        self.assertIn("github.event.repository.default_branch", ref)
        self.assertIn("github.sha", ref)                                                       # 다른 이벤트는 그 이벤트의 커밋(기본 동작)
        self.assertIs(checkout["with"]["persist-credentials"], False)
        context = {"github": {"event_name": "pull_request", "event": {"repository": {"default_branch": "main"}}, "sha": "abc123"}}
        self.assertEqual(_Expr(ref.strip("${} "), {"github": {"event_name": "pull_request", "event": {"repository": {"default_branch": "main"}}, "sha": "abc"}}).parse(), "main")
        for event in ("schedule", "issues", "workflow_dispatch"):
            self.assertEqual(_Expr(ref.strip("${} "), {"github": {**context["github"], "event_name": event}}).parse(), "abc123", event)

    def test_permissions_concurrency_and_timeout_stay_minimal_and_safe(self):
        self.assertEqual(self.wf["permissions"], {"contents": "read", "actions": "read", "checks": "read", "pull-requests": "read", "issues": "write"})
        self.assertNotIn("permissions", self.job)
        self.assertNotIn("concurrency", self.wf)                                              # 워크플로 수준이 아니라 job 수준(건너뛰는 이벤트가 진짜 갱신을 밀어내지 않게)
        self.assertEqual(self.job["concurrency"], {"group": "ops-inbox", "cancel-in-progress": False})
        self.assertEqual(self.job["timeout-minutes"], 12)
        self.assertEqual(self.job["runs-on"], "ubuntu-latest")

    def test_the_workflow_only_runs_the_inbox_script_so_it_cannot_start_itself(self):
        """이 워크플로는 스크립트 한 줄만 돌리고 파일·브랜치·PR 을 만들지 않는다(쓰는 것은 이슈·코멘트·라벨뿐). 기본 토큰이 만든 이벤트는 워크플로를 시작시키지 않는다(GitHub 규칙)."""
        runs = [step["run"].strip() for step in self.job["steps"] if "run" in step]
        self.assertEqual(runs, ["python scripts/ops_inbox.py"])
        for forbidden in ("git push", "git commit", "gh pr", "gh workflow", "gh issue", "gh api"):
            self.assertNotIn(forbidden, self.text, forbidden)

    def test_run_name_tells_the_event_and_uses_only_the_event_kind_and_the_dry_run_flag(self):
        run_name = self.wf["run-name"]
        self.assertTrue(run_name.startswith("[공통] 확인 필요 모음 갱신 · "))
        for body in re.findall(r"\$\{\{(.*?)\}\}", run_name):
            code = re.sub(r"'(?:[^']|'')*'", "''", body)
            refs = set(re.findall(r"[A-Za-z_][A-Za-z0-9_\-]*(?:\.[A-Za-z0-9_\-]+)+", code))
            self.assertLessEqual(refs, {"github.event_name", "inputs.dry_run"})
        template = run_name.split("${{")[1].split("}}")[0]

        def title(event, dry=None):
            ctx = {"github": {"event_name": event}, "inputs": {} if dry is None else {"dry_run": dry}}
            return _Expr(template, ctx).parse()
        self.assertEqual(title("schedule"), "정기")
        self.assertEqual(title("workflow_dispatch", False), "수동")
        self.assertEqual(title("workflow_dispatch", True), "수동(연습: 이슈·코멘트 안 씀)")
        self.assertEqual(title("issues"), "이슈 변경(초안만 점검)")
        self.assertEqual(title("pull_request"), "PR 변경(초안만 점검)")

    def test_the_dry_run_flag_is_only_ever_true_for_a_manual_dry_run(self):
        step = next(s for s in self.job["steps"] if "run" in s)
        expr = step["env"]["INBOX_DRY_RUN"].strip()[3:-2].strip()
        for event in ("schedule", "issues", "pull_request"):
            self.assertEqual(_Expr(expr, {"github": {"event_name": event}, "inputs": {"dry_run": True}}).parse(), "false", event)
        self.assertEqual(_Expr(expr, {"github": {"event_name": "workflow_dispatch"}, "inputs": {"dry_run": True}}).parse(), "true")
        self.assertEqual(_Expr(expr, {"github": {"event_name": "workflow_dispatch"}, "inputs": {"dry_run": False}}).parse(), "false")

    def test_the_header_comment_warns_that_default_token_events_do_not_start_runs(self):
        self.assertIn("GITHUB_TOKEN", self.text)
        self.assertIn("workflow_dispatch", self.text.split("jobs:")[0])
        self.assertIn("초안을 자동으로 만드는 워크플로", self.text)


class DraftGuideMatchesCodeTest(unittest.TestCase):
    """docs/OPS_INBOX.md·ACTIONS_GUIDE·ARCHITECTURE·HANDLER 가 말하는 초안 모델의 값·약속이 코드와 같은지(값을 바꾸면 문서도 고친다)."""

    def setUp(self):
        docs = _bootstrap.ROOT / "docs"
        self.doc = (docs / "OPS_INBOX.md").read_text(encoding="utf-8")
        self.guide = (docs / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")
        self.arch = (docs / "ARCHITECTURE.md").read_text(encoding="utf-8")
        self.handler = (_bootstrap.ROOT / "HANDLER.md").read_text(encoding="utf-8")

    def test_the_label_table_lists_each_label_with_its_fixed_colour_and_description(self):
        for name, color, text in inbox.DRAFT_LABEL_SPECS:
            row = next(line for line in self.doc.splitlines() if line.startswith(f"| `{name}` |"))
            self.assertIn(f"`{color}`", row, name)
            self.assertIn(text, row, name)
        row = next(line for line in self.doc.splitlines() if line.startswith("| `채널:<채널 라벨>` |"))
        self.assertIn(f"`{inbox.CHANNEL_LABEL_COLOR}`", row)
        self.assertIn("초안이 속한 채널:", row)

    def test_the_numbers_in_the_guide_are_the_constants(self):
        self.assertIn(f"열린 지 {inbox.DRAFT_STALE_DAYS}일 이하", self.doc)
        self.assertIn(f"열린 지 {inbox.DRAFT_STALE_DAYS}일(`DRAFT_STALE_DAYS`) 넘음", self.doc)
        self.assertIn(f"최근 {inbox.DRAFT_WINDOW_DAYS}일(`DRAFT_WINDOW_DAYS`)", self.doc)
        self.assertIn(f"`BOARD_ROWS_MAX`={inbox.BOARD_ROWS_MAX}줄", self.doc)
        self.assertIn(f"100건씩 최대 {oi.MAX_DRAFT_PAGES}쪽({oi.MAX_DRAFT_PAGES * oi.DRAFTS_PER_PAGE}건)", self.doc)
        self.assertIn(f"한 번에 최대 {oi.MAX_LABEL_CREATES}개", self.doc)
        self.assertIn(f"{oi.DRAFTS_PER_PAGE}건씩 {oi.MAX_DRAFT_PAGES}쪽까지", self.guide)
        self.assertIn(f"최근 {inbox.DRAFT_WINDOW_DAYS}일 초안함 업로드", self.guide)

    def test_the_table_cell_words_in_the_guide_are_the_ones_the_code_prints(self):
        for word in ("자동 공개", "정지", "조회 실패", "(대략)", "(미등록)", "(채널 표시 없음)", "1일 미만", "(정지 중)", "그 밖의 채널"):
            self.assertIn(word, self.doc, word)
        source = (_bootstrap.ROOT / "pipeline" / "inbox.py").read_text(encoding="utf-8")
        for word in ("자동 공개", "조회 실패", "(대략)", "(미등록)", "(채널 표시 없음)", "1일 미만", "(정지 중)", "그 밖의 채널"):
            self.assertIn(word, source, word)
        self.assertIn("채널 | 대기 초안 | 가장 오래된 | 최신 초안", self.doc)
        self.assertEqual(inbox.BOARD_HEADER, ("채널", "대기 초안", "가장 오래된", "최신 초안"))

    def test_the_item_ids_and_levels_in_the_guide_are_what_the_rules_make(self):
        for needle in ("draft:<번호>:wait", "draft:<번호>:stale", "draft:"):
            self.assertIn(needle, self.doc, needle)
        items = inbox.draft_items([h.make_draft(41, hours=30), h.make_draft(43, hours=100)], NOW, URL)
        wait, stale = sorted(items, key=lambda item: item.id)
        self.assertEqual((wait.id, wait.level, stale.id, stale.level), ("draft:41:wait", "action", "draft:43:stale", "check"))

    def test_the_pull_request_draft_rule_in_the_guide_is_what_the_code_does(self):
        rows = [line for line in self.doc.splitlines() if line.startswith("| 초안(PR) |")]
        self.assertEqual(len(rows), 1)
        for phrase in ("열린 PR 줄(`pr:<번호>:…`)은 빼서", "`draft:<번호>:wait`", "`/pull/번호`", "검사 결과 없음"):
            self.assertIn(phrase, rows[0], phrase)
        for phrase in ("`pr:<번호>:ready`·`conflict`·`ci_fail`", "새 id라 **한 번 더** 알립니다", "초안 PR은 한 줄만 남깁니다"):
            self.assertIn(phrase, self.doc, phrase)
        self.assertIn("초안 PR은 한 줄만 남긴다", self.arch)
        # 문서가 action 으로 꼽은 세 상태가 실제로 열린 PR 규칙의 action 이다(그 밖의 상태는 action 이 아니다)
        made = {i.id.rsplit(":", 1)[1] for i in inbox.pull_items([h.make_pull(15), h.make_pull(16, mergeable=False, state="dirty"), h.make_pull(17, ci="fail")], NOW, URL)
                if i.level == "action"}
        self.assertEqual(made, {"ready", "conflict", "ci_fail"})
        quiet = {i.id.rsplit(":", 1)[1] for i in inbox.pull_items([h.make_pull(18, ci="none"), h.make_pull(19, ci="pending"), h.make_pull(20, state="blocked")], NOW, URL)}
        self.assertEqual(quiet, {"no_ci", "pending", "blocked"})

    def test_the_event_types_and_the_run_titles_are_in_the_guide(self):
        wf = load_workflow()
        for kind in wf["on"]["issues"]["types"]:
            self.assertIn(kind, "opened closed reopened labeled unlabeled".split())
        for title in ("이슈 변경(초안만 점검)", "PR 변경(초안만 점검)"):
            self.assertIn(title, self.doc, title)
            self.assertIn(title, self.guide, title)
            self.assertIn(title, WORKFLOW.read_text(encoding="utf-8"), title)
        self.assertIn("issues", self.handler)
        self.assertIn("pull_request", self.handler)
        self.assertIn("직접 불러야 한다", self.handler)

    def test_every_description_of_the_inbox_mentions_the_draft_board(self):
        self.assertIn("초안 현황", self.doc)
        self.assertIn("초안 현황", self.guide)
        self.assertIn("초안 현황", self.arch)
        self.assertIn("초안 현황", self.handler)
        self.assertIn("### 3-1. 초안 모델과 초안 현황 표", self.doc)
        self.assertIn("### 4-2-1. 초안 모델과 초안 현황", self.arch)

    def test_the_limits_about_default_token_events_are_written_down(self):
        self.assertIn("기본 토큰(`GITHUB_TOKEN`)이 만들거나 고친 이슈·PR은 이 워크플로를 시작시키지 않습니다", self.doc)
        self.assertIn("만든 직후 `workflow_dispatch`로 `ops-inbox.yml`을 불러", self.doc)
        self.assertIn("기본 토큰이 만든 이슈·PR은 이 이벤트를 일으키지 않으므로", self.handler)
        self.assertIn("Actions 실행은 하지 못했습니다", self.guide)

    def test_the_security_section_names_the_event_trigger_rules_the_workflow_follows(self):
        wf_text = WORKFLOW.read_text(encoding="utf-8")
        for phrase in ("이벤트 트리거", "head.repo.full_name == github.repository", "pull_request_target", "기본 브랜치의 코드", "concurrency"):
            self.assertIn(phrase, self.doc, phrase)
        self.assertIn("github.repository", wf_text)

    def test_the_blogger_summary_head_is_documented_where_the_runner_summary_is(self):
        self.assertIn("### [채널 라벨] 블로그 이름", self.arch)
        self.assertIn("### [Blogger] Blogger (macat0722)", self.guide)
        self.assertIn("summary_head", self.arch)


class ExpressionHelperSelfTest(unittest.TestCase):
    """위 해석기가 GitHub 규칙을 따르는지(워크플로 시험이 이 해석기에 기대므로)."""

    def ev(self, src, ctx=None):
        return _Expr(src, ctx or {}).parse()

    def test_contains_over_a_label_projection_and_over_strings(self):
        ctx = {"a": {"labels": [{"name": "초안"}, {"name": "채널:x"}]}}
        self.assertTrue(self.ev("contains(a.labels.*.name, '초안')", ctx))
        self.assertFalse(self.ev("contains(a.labels.*.name, '초')", ctx))                       # 배열은 정확히 같은 원소만
        self.assertTrue(self.ev("contains('Hello', 'ell')"))
        self.assertFalse(self.ev("contains(a.missing.*.name, 'x')", ctx))

    def test_operators_follow_github_precedence_and_return_operands(self):
        self.assertEqual(self.ev("true && 'a' || 'b'"), "a")
        self.assertEqual(self.ev("false && 'a' || 'b'"), "b")
        self.assertEqual(self.ev("null || 'c'"), "c")
        self.assertTrue(self.ev("'A' == 'a'"))
        self.assertTrue(self.ev("!false"))
        self.assertEqual(self.ev("false || true && 'x'"), "x")

    def test_missing_references_are_null_and_bad_text_raises(self):
        self.assertIsNone(self.ev("github.event.label.name", {"github": {"event": {}}}))
        for bad in ("a &&", "(a", "'x", "f(x)"):
            with self.assertRaises((ValueError, AssertionError, TypeError)):
                self.ev(bad, {"a": 1, "x": 1})


if __name__ == "__main__":
    unittest.main()
