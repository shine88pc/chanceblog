"""확인 필요 모음 — 오래된 항목·의도된 정지 정리(2026-11-11, docs/OPS_INBOX.md §10)의 분류 규칙 시험. 네트워크 없이 pipeline/inbox.py 의 순수 함수만 본다.

운영자 요청 일곱 가지: ① 병합된 PR 은 '병합 필요'·승인 대기에서 뺀다 ② 병합됐거나 닫힌 가지의 'Approve and run' 은 뺀다(못 찾으면 예전처럼 보인다)
③ 일시정지 변수는 정책 파일에 이유·재개 조건이 있으면 '참고: 계획된 일시정지'(재개 Gate 통과 때만 '재개 승인') ④ 멈춘 채널·전체 정지의 초안은 '정지 전에 생성된 초안'(게시 문구 없음)
⑤ Blogger 초안은 신호가 모두 긍정일 때만 '게시 검토' ⑥ 철 지난 초안은 '폐기 또는 재생성 검토' ⑦ 운영자 결정(유지·폐기 후 닫기 권장·무시)을 데이터로 반영.
입출력(가지 PR 상태 조회·정책 파일 읽기·쓰기 범위)은 test_ops_inbox_cleanup_script.py 가 본다.
"""
import copy
import re
import unittest
from datetime import date, datetime, timedelta, timezone

import _bootstrap
import ops_inbox_helpers as h          # 저장소 루트를 import 경로에 올린다(_bootstrap)
import ops_inbox_repro as repro
from pipeline import inbox
from pipeline import inbox_policy as ip
from pipeline.state import KST

NOW, URL, ago = h.NOW, h.REPO_URL, h.ago
# 정지 중인 채널의 초안에 쓰면 안 되는 말(게시·발행·병합을 권하는 문구)
URGING = ("게시", "발행", "병합하면", "복사해", "공개하세요", "공개됩니다", "공개하면")


def one(items):
    assert len(items) == 1, [i.id for i in items]
    return items[0]


def text_of(item):
    return " ".join((item.title, item.detail, item.hint))


def make_policy(planned=None, decisions=None):
    data = {"schema_version": 1}
    if planned is not None:
        data["planned_pause"] = planned
    if decisions is not None:
        data["item_decisions"] = decisions
    return ip.parse_policy(data)


PAUSE = {"active": True, "since": "2026-11-09", "reason": "제한 재개 조건을 보장하기 전까지 일부러 멈춤", "decision_ref": "운영자 결정 2026-11-09, 확인 요청 008",
         "resume_conditions": ["승인 초안 PR 로만 공개", "하루 최대 1편, 주 1–2편", "그림자 모드 3회 통과", "계산이 값을 더하는 글만", "제공처 켜기는 따로"], "resume_gate_passed": False}


def decision(kind, reason="운영자 결정 사유"):
    return {"decision": kind, "date": "2026-11-11", "reason": reason}


def snap(**kw):
    base = dict(now=NOW, repo=h.REPO)
    base.update(kw)
    return inbox.Snapshot(**base)


def pull_raw(number, state="open", merged=None, **kw):
    """GitHub 열린 목록의 PR 하나 + (state·merged 를 알려 주는) 상세로 normalize_pull 한 결과."""
    raw = h.make_pull_raw(number, **kw)
    detail = {"mergeable": True, "mergeable_state": "clean", "state": state}
    if merged is not None:
        detail["merged"] = merged
    return inbox.normalize_pull(raw, detail, [h.make_check("validate")])


# ----------------------------------------------------------------------------
# ① 병합됐거나 닫힌 PR
# ----------------------------------------------------------------------------
class MergedPullTest(unittest.TestCase):
    def test_normalize_pull_keeps_the_state_and_the_merged_flag(self):
        pr = pull_raw(15, "closed", True)
        self.assertEqual((pr["state"], pr["merged"]), ("closed", True))
        pr = pull_raw(16)
        self.assertEqual((pr["state"], pr["merged"]), ("open", False))
        pr = inbox.normalize_pull(h.make_pull_raw(17))
        self.assertEqual((pr["state"], pr["merged"]), ("", False))                   # 아무것도 모르면 끝난 것으로 보지 않는다

    def test_the_detail_is_the_freshest_word_and_the_list_entry_is_the_fallback(self):
        raw = dict(h.make_pull_raw(18), merged_at="2026-11-10T09:00:00Z", state="closed")
        self.assertTrue(inbox.normalize_pull(raw)["merged"])                              # 목록의 merged_at 만 있어도 병합
        self.assertTrue(inbox.normalize_pull(raw, {"merged_at": "2026-11-10T09:00:00Z"})["merged"])
        self.assertFalse(inbox.normalize_pull(raw, {"merged": False})["merged"])         # 상세가 병합 아님이라 하면 그것이 이긴다
        self.assertEqual(inbox.normalize_pull(raw, {"state": "open"})["state"], "open")
        self.assertEqual(inbox.normalize_pull(h.make_pull_raw(19), {"state": None})["state"], "")
        self.assertEqual(inbox.normalize_pull(h.make_pull_raw(19), {"state": "CLOSED"})["state"], "closed")           # 상태 낱말은 소문자로 맞춘다(GraphQL 식 대문자도 같은 뜻)
        self.assertEqual(inbox.normalize_pull(dict(h.make_pull_raw(19), state="Open"))["state"], "open")
        self.assertFalse(inbox.normalize_pull(h.make_pull_raw(20), {"merged": "yes"})["merged"])      # bool 이 아닌 값은 병합으로 믿지 않는다

    def test_a_merged_pull_request_makes_no_merge_item_at_all(self):
        self.assertEqual(inbox.pull_items([pull_raw(176, "closed", True)], NOW, URL), [])

    def test_closed_without_merge_and_the_other_spellings_of_finished_make_no_item_either(self):
        for state, merged in (("closed", False), ("closed", None), ("merged", None), ("MERGED", None), ("Closed", None), ("open", True)):
            self.assertEqual(inbox.pull_items([pull_raw(177, state, merged)], NOW, URL), [], (state, merged))

    def test_an_open_unknown_or_empty_state_still_shows_exactly_as_before(self):
        for state in ("open", "OPEN", "weird", ""):
            item = one(inbox.pull_items([pull_raw(178, state, False)], NOW, URL))
            self.assertEqual((item.id, item.level), ("pr:178:ready", "action"), state)
        before = one(inbox.pull_items([h.make_pull(179)], NOW, URL))
        after = one(inbox.pull_items([pull_raw(179)], NOW, URL))
        self.assertEqual(before, after)                                                  # 상태 칸이 있어도 열린 PR 의 항목은 글자 하나 다르지 않다

    def test_pull_finished_looks_only_at_the_two_fields(self):
        self.assertTrue(inbox.pull_finished({"merged": True}))
        self.assertTrue(inbox.pull_finished({"state": "closed"}))
        self.assertFalse(inbox.pull_finished({}))
        self.assertFalse(inbox.pull_finished({"merged": "yes", "state": "open"}))
        self.assertFalse(inbox.pull_finished({"state": None}))

    def test_a_merged_pull_does_not_take_the_open_pulls_neighbours_with_it(self):
        items = inbox.pull_items([pull_raw(176, "closed", True), pull_raw(177)], NOW, URL)
        self.assertEqual([i.id for i in items], ["pr:177:ready"])

    def test_the_real_case_pr_176_merged_between_the_listing_and_the_check(self):
        listed = h.make_pull_raw(176, title="[M048] 품질 관문", login="github-actions[bot]", user_type="Bot", ref="ai/claude/M048-fact-gate-s2bg")
        merged = inbox.normalize_pull(listed, {"mergeable": None, "mergeable_state": "unknown", "state": "closed", "merged": True}, [h.make_check("validate")])
        before = inbox.normalize_pull(listed, {"mergeable": True, "mergeable_state": "clean", "state": "open", "merged": False}, [h.make_check("validate")])
        self.assertEqual(one(inbox.pull_items([before], NOW, URL)).id, "pr:176:ready")
        self.assertEqual(inbox.pull_items([merged], NOW, URL), [])
        self.assertNotIn("pr:176:ready", [i.id for i in inbox.build_items(snap(pulls=[merged]))])


# ----------------------------------------------------------------------------
# ② 승인 대기 — 가지 PR 상태
# ----------------------------------------------------------------------------
def approvals(*specs):
    """(실행 번호, 가지) 목록 → 승인 대기 실행 목록(실행마다 다른 커밋)."""
    return [h.make_approval_run(run_id, branch=branch, created=ago(hours=100 - index)) for index, (run_id, branch) in enumerate(specs)]


class ApprovalBranchStateTest(unittest.TestCase):
    RUNS = approvals((101, "ai/claude/M029-a"), (102, "ai/claude/M034-b"), (103, "ai/claude/M038-c"), (104, "ai/claude/M048-d"))

    def ids(self, states, runs=None):
        return [i.id for i in inbox.approval_items(runs or self.RUNS, URL, branch_states=states)]

    def test_without_branch_states_every_waiting_run_shows_as_before(self):
        self.assertEqual(len(self.ids(None)), 4)
        self.assertEqual(self.ids({}), self.ids(None))
        self.assertEqual(inbox.approval_items(self.RUNS, URL), inbox.approval_items(self.RUNS, URL, branch_states={}))

    def test_merged_and_closed_branches_are_left_out_and_open_or_unknown_ones_stay(self):
        states = {"ai/claude/M029-a": "merged", "ai/claude/M034-b": "closed", "ai/claude/M038-c": "open"}
        shown = inbox.approval_items(self.RUNS, URL, branch_states=states)
        self.assertEqual([i.url.rsplit("/", 1)[1] for i in shown], ["103", "104"])         # 열린 가지와 모르는 가지(M048)만 남는다
        self.assertTrue(all(i.level == "action" for i in shown))

    def test_every_other_value_is_unknown_and_keeps_the_run(self):
        for value in ("weird", "", None, 5, True, ["merged"], "MERGED", "Merged"):
            self.assertEqual(len(self.ids({"ai/claude/M029-a": value})), 4, repr(value))

    def test_a_finished_branch_is_left_out_whatever_it_has_waiting(self):
        runs = [h.make_approval_run(201, branch="ai/claude/X", sha="a" * 40, name="검사 하나"), h.make_approval_run(202, branch="ai/claude/X", sha="a" * 40, name="검사 둘"),
                h.make_approval_run(203, branch="ai/claude/X", sha="b" * 40, name="검사 하나")]
        self.assertEqual(self.ids({"ai/claude/X": "merged"}, runs), [])
        self.assertEqual(len(self.ids({"ai/claude/X": "open"}, runs)), 2)                  # 같은 커밋의 둘은 한 항목, 다른 커밋은 따로
        self.assertEqual(len(self.ids({}, runs)), 2)

    def test_two_branches_on_the_same_commit_keep_the_open_ones_run(self):
        runs = [h.make_approval_run(301, branch="ai/claude/A", sha="c" * 40), h.make_approval_run(302, branch="ai/claude/B", sha="c" * 40)]
        [item] = inbox.approval_items(runs, URL, branch_states={"ai/claude/A": "merged", "ai/claude/B": "open"})
        self.assertTrue(item.url.endswith("/302"))

    def test_the_summary_item_counts_only_what_is_still_waiting(self):
        runs = approvals(*[(400 + n, f"ai/claude/B{n}") for n in range(9)])
        states = {f"ai/claude/B{n}": "merged" for n in range(3)}
        shown = inbox.approval_items(runs, URL, branch_states=states)
        self.assertEqual(len(shown), 5 + 1)                                                  # 열려 있는 6건 → 5건 + '1건 더'
        self.assertEqual(shown[-1].id, "approve:more")
        self.assertIn("1건 더", shown[-1].title)
        states = {f"ai/claude/B{n}": "closed" for n in range(4)}
        self.assertEqual([i.id for i in inbox.approval_items(runs, URL, branch_states=states) if i.id == "approve:more"], [])     # 5건이 남으면 요약이 필요 없다

    def test_a_branch_name_that_is_not_text_never_breaks_the_rule(self):
        runs = [dict(h.make_approval_run(501), head_branch=None), dict(h.make_approval_run(502, sha="d" * 40), head_branch=["x"]),
                dict(h.make_approval_run(503, sha="e" * 40), head_branch={"a": 1}), dict(h.make_approval_run(504, sha="f" * 40), head_branch=5)]
        self.assertEqual(len(self.ids({"None": "merged", "x": "merged"}, runs)), 4)
        self.assertEqual(len(inbox.approval_items(runs, URL, branch_states={"ai/claude/M029-example": "merged"})), 4)

    def test_branch_states_that_are_not_a_mapping_are_ignored(self):
        for states in ("merged", ["ai/claude/M029-a"], 5, (("ai/claude/M029-a", "merged"),)):
            self.assertEqual(len(self.ids(states)), 4, repr(states))

    def test_approval_runs_is_the_one_filter_both_the_item_rule_and_the_lookup_use(self):
        own = h.make_approval_run(601, path=".github/workflows/ops-inbox.yml")
        plain = dict(h.make_approval_run(602), status="completed", conclusion="success")
        bad = {"id": "x", "status": "action_required"}
        runs = [own, plain, bad, "text", None, h.make_approval_run(603), dict(h.make_approval_run(604), status="action_required", conclusion=None)]
        self.assertEqual([r["id"] for r in inbox.approval_runs(runs)], [603, 604])

    def test_build_items_passes_the_snapshot_branch_states_to_the_rule(self):
        states = {"ai/claude/M029-a": "merged", "ai/claude/M034-b": "merged"}
        items = inbox.build_items(snap(approvals=self.RUNS, branch_prs=states))
        self.assertEqual(sorted(i.url.rsplit("/", 1)[1] for i in items if i.id.startswith("approve:")), ["103", "104"])
        self.assertEqual(len([i for i in inbox.build_items(snap(approvals=self.RUNS)) if i.id.startswith("approve:")]), 4)


# ----------------------------------------------------------------------------
# ③ 의도된 일시정지
# ----------------------------------------------------------------------------
class PlannedPauseTest(unittest.TestCase):
    def plan(self, **changes):
        data = dict(PAUSE, **changes)
        return make_policy(planned=data)

    def test_without_a_policy_the_pause_item_is_exactly_the_old_one(self):
        item = one(inbox.pause_items(True, URL))
        self.assertEqual((item.id, item.level, item.title), ("pause", "action", "자동 발행이 멈춰 있습니다 — 해제 방법"))
        self.assertEqual(item.url, f"{URL}/settings/variables/actions")
        self.assertIn("삭제(또는 false 로 변경)", item.hint)
        self.assertEqual(inbox.pause_items(True, URL, None), inbox.pause_items(True, URL))
        self.assertEqual(inbox.pause_items(False, URL), [])
        self.assertEqual([i.id for i in inbox.pause_items(False, URL, self.plan())], ["pause:unset"])         # 변수는 꺼졌는데 정책은 정지를 선언했다 — 표시만(D10)

    def test_a_declared_pause_is_a_reference_item_that_never_suggests_releasing(self):
        item = one(inbox.pause_items(True, URL, self.plan()))
        self.assertEqual((item.id, item.level), ("pause:planned", "info"))
        self.assertTrue(item.title.startswith("참고: 계획된 일시정지"))
        self.assertEqual(item.url, "")                                                      # '바로 하기'(변수 삭제 링크)가 없다
        for word in ("재개 조건 5가지", "제한 재개 조건을 보장하기 전까지 일부러 멈춤", "운영자 결정 2026-11-09, 확인 요청 008", "2026-11-09부터"):
            self.assertIn(word, item.detail, word)
        self.assertIn("해제하지 마세요", item.hint)
        self.assertNotIn("삭제", text_of(item))
        self.assertNotIn("false", text_of(item))
        self.assertNotIn("settings/variables", repr(item))
        text = inbox.render([item], URL)
        self.assertNotIn("바로 하기", text)
        self.assertIn("## 참고 (1건)", text)

    def test_the_resume_conditions_are_summarised_by_count_and_the_first_three(self):
        item = one(inbox.pause_items(True, URL, self.plan()))
        self.assertIn("승인 초안 PR 로만 공개 / 하루 최대 1편, 주 1–2편 / 그림자 모드 3회 통과 외 2가지", item.detail)
        short = one(inbox.pause_items(True, URL, self.plan(resume_conditions=["하나", "둘"])))
        self.assertIn("재개 조건 2가지: 하나 / 둘 ·", short.detail)
        self.assertNotIn("외 ", short.detail)
        exact = one(inbox.pause_items(True, URL, self.plan(resume_conditions=["가", "나", "다"])))
        self.assertNotIn("외 ", exact.detail)

    def test_a_long_condition_is_clipped_and_the_whole_description_fits_the_limit(self):
        longest = self.plan(reason="가" * ip.REASON_MAX, decision_ref="나" * ip.REF_MAX, resume_conditions=["다" * ip.CONDITION_MAX] * ip.MAX_RESUME_CONDITIONS)
        item = one(inbox.pause_items(True, URL, longest))
        self.assertLessEqual(len(item.detail), inbox.DETAIL_MAX)
        self.assertNotIn("다" * (inbox.RESUME_SHOWN_CHARS + 1), item.detail)
        self.assertIn("외 9가지", item.detail)
        self.assertTrue(inbox.render([item], URL).count("…") >= 3)                         # 줄인 곳마다 말줄임표

    def test_text_from_the_policy_is_neutralised_like_any_external_text(self):
        policy = self.plan(reason="<b>굵게</b> `코드` [링크](x) | 표", decision_ref="& 그리고 <i>", resume_conditions=["[a](b) `c` <d>"])
        text = inbox.render(inbox.pause_items(True, URL, policy), URL)
        for raw in ("<b>", "`코드`", "[링크]", "<i>", "<d>"):
            self.assertNotIn(raw, text)

    def test_the_resume_approval_item_exists_only_when_the_gate_flag_is_set_by_a_human_reviewed_merge(self):
        passed = self.plan(resume_gate_passed=True)
        item = one(inbox.pause_items(True, URL, passed))
        self.assertEqual((item.id, item.level), ("pause:resume_approval", "action"))
        self.assertIn("재개 승인", item.title)
        self.assertIn("5가지", item.detail)
        self.assertEqual(item.url, f"{URL}/settings/variables/actions")
        self.assertIn("운영자가 직접 정합니다", item.hint)
        self.assertIn("변수를 바꾸지 않습니다", item.hint)
        self.assertEqual([i.id for i in inbox.pause_items(False, URL, passed)], ["pause:unset"])         # 이미 풀렸으면 재개 승인은 없고 '정책 선언이 남았다'는 확인 항목만(D10)
        self.assertNotIn("pause", [i.id for i in inbox.pause_items(True, URL, passed)])

    def test_only_a_fully_declared_active_pause_changes_anything(self):
        legacy = inbox.pause_items(True, URL)
        self.assertEqual(inbox.pause_items(True, URL, make_policy()), legacy)                                           # 선언 없음
        self.assertEqual(inbox.pause_items(True, URL, make_policy(planned={"active": False})), legacy)                  # 꺼 둔 선언
        self.assertEqual(inbox.pause_items(True, URL, make_policy(planned=dict(PAUSE, active=False))), legacy)
        self.assertEqual(inbox.pause_items(True, URL, make_policy(decisions={"draft:1": decision("keep")})), legacy)    # 결정만 있는 정책
        for junk in ("x", 5, object(), {}):
            self.assertEqual(inbox.pause_items(True, URL, junk), legacy, repr(junk))

    def test_the_variable_being_off_means_no_planned_or_resume_item_whatever_the_policy_says(self):
        for gate in (False, True):
            ids = [i.id for i in inbox.pause_items(False, URL, self.plan(resume_gate_passed=gate))]
            self.assertEqual(ids, ["pause:unset"], gate)                       # 계획된 정지·재개 승인은 변수가 켜져 있을 때만 — 꺼졌으면 확인 항목 하나뿐(D10)

    def test_in_a_build_the_declared_pause_leaves_the_things_to_do_and_the_old_wording_is_gone(self):
        items = inbox.build_items(snap(paused=True, policy=self.plan()))
        self.assertEqual([i.id for i in items if i.level == "action"], [])
        self.assertIn("pause:planned", [i.id for i in items if i.level == "info"])
        self.assertNotIn("pause", [i.id for i in items])
        passed = inbox.build_items(snap(paused=True, policy=self.plan(resume_gate_passed=True)))
        self.assertEqual([i.id for i in passed if i.level == "action"], ["pause:resume_approval"])

    def test_a_policy_that_is_not_a_policy_object_is_the_same_as_no_policy(self):
        legacy = inbox.build_items(snap(paused=True))
        for junk in ("x", 5, {"planned_pause": PAUSE}, object()):
            self.assertEqual(inbox.build_items(snap(paused=True, policy=junk)), legacy, repr(junk))

    def test_the_new_action_ids_are_a_different_family_from_the_old_pause_id(self):
        self.assertTrue(inbox._ID_RE.fullmatch("pause:resume_approval"))
        self.assertTrue(inbox._ID_RE.fullmatch("pause:planned"))
        new, kept = inbox.plan_notice(inbox.build_items(snap(paused=True, policy=self.plan())), ("pause",))
        self.assertEqual((new, kept), ([], []))                                            # 예전 표식의 pause 는 사라지는 쪽 — 새 알림이 없다
        new, kept = inbox.plan_notice(inbox.build_items(snap(paused=True, policy=self.plan(resume_gate_passed=True))), ("pause",))
        self.assertEqual((new, kept), (["pause:resume_approval"], ["pause:resume_approval"]))


# ----------------------------------------------------------------------------
# ④ 정지 중인 채널의 초안
# ----------------------------------------------------------------------------
def naver_blogs(mode="off"):
    return [h.channel_blog("chance", "Chance", "jekyll-git", "auto"), h.channel_blog("naver_x", "네이버", "naver", mode),
            h.channel_blog("tistory_x", "티스토리", "tistory", "package")]


def draft(number, title="[초안][네이버] 서랍 정리 순서 만들기", channel="네이버", **kw):
    return h.make_draft(number, title, channel, **kw)


class StoppedDraftsTest(unittest.TestCase):
    def ctx(self, **kw):
        return inbox.DraftContext(**kw)

    def test_without_a_context_the_old_rule_is_untouched(self):
        old = inbox.draft_items([draft(41, hours=30), draft(43, hours=100)], NOW, URL)
        self.assertEqual([(i.id, i.level) for i in old], [("draft:41:wait", "action"), ("draft:43:stale", "check")])
        self.assertEqual(inbox.draft_items([draft(41, hours=30)], NOW, URL, None, None), inbox.draft_items([draft(41, hours=30)], NOW, URL))

    def test_a_draft_of_a_stopped_channel_is_an_earlier_draft_to_keep_review_or_discard(self):
        item = one(inbox.draft_items([draft(41, hours=30)], NOW, URL, ctx=self.ctx(stopped=frozenset({"네이버"}))))
        self.assertEqual((item.id, item.level), ("draft:41:paused", "check"))
        self.assertEqual(item.title, "정지 전에 생성된 초안 — 서랍 정리 순서 만들기")
        self.assertIn("채널 네이버 · 이슈 #41", item.detail)
        self.assertIn("유지·검토·폐기 중에서 고르세요", item.detail)
        self.assertIn("공개를 권장하지 않습니다", item.detail)
        self.assertEqual(item.url, f"{URL}/issues/41")
        self.assertIn("라벨 `폐기`", item.hint)
        self.assertIn("자동으로 닫지 않습니다", item.hint)
        for word in URGING:
            self.assertNotIn(word, text_of(item), word)

    def test_a_pull_request_draft_says_pr_and_links_the_pull_request(self):
        item = one(inbox.draft_items([h.make_draft(15, "[초안][Chance] 글", "Chance", pull=True, hours=5)], NOW, URL, ctx=self.ctx(paused=True)))
        self.assertEqual((item.id, item.level, item.url), ("draft:15:paused", "check", f"{URL}/pull/15"))
        self.assertIn("PR #15", item.detail)
        self.assertIn("PR 을 열고", item.hint)
        for word in URGING:
            self.assertNotIn(word, text_of(item), word)

    def test_a_global_pause_covers_every_channel_and_a_draft_without_a_channel_label(self):
        items = inbox.draft_items([draft(41, channel="네이버"), draft(42, "[초안] 글", None), draft(43, "[초안][티스토리] 글", "티스토리")], NOW, URL, ctx=self.ctx(paused=True))
        self.assertEqual([i.id for i in items], ["draft:41:paused", "draft:42:paused", "draft:43:paused"])
        self.assertTrue(all(i.level == "check" for i in items))
        self.assertIn("채널 표시 없음", items[1].detail)

    def test_a_channel_that_is_not_stopped_keeps_the_old_wait_and_stale_items(self):
        ctx = self.ctx(stopped=frozenset({"네이버"}))
        items = inbox.draft_items([draft(41, "[초안][티스토리] 글", "티스토리", hours=30), draft(43, "[초안][티스토리] 오랜 글", "티스토리", hours=100), draft(44, "[초안] 표지 없음", None)], NOW, URL, ctx=ctx)
        self.assertEqual([(i.id, i.level) for i in items], [("draft:41:wait", "action"), ("draft:43:stale", "check"), ("draft:44:wait", "action")])

    def test_the_channel_match_ignores_case_and_a_stale_draft_is_still_one_paused_item(self):
        item = one(inbox.draft_items([h.make_draft(41, "[초안][blogger 영문] 글", "blogger 영문", hours=500)], NOW, URL, ctx=self.ctx(stopped=frozenset({"blogger 영문"}))))
        self.assertEqual(item.id, "draft:41:paused")
        upper = one(inbox.draft_items([h.make_draft(42, "[초안][BLOGGER 영문] 글", "BLOGGER 영문")], NOW, URL, ctx=self.ctx(stopped=frozenset({"blogger 영문"}))))
        self.assertEqual(upper.id, "draft:42:paused")

    def test_closed_and_discarded_drafts_never_become_items(self):
        ctx = self.ctx(paused=True)
        self.assertEqual(inbox.draft_items([draft(1, state="closed"), draft(2, extra_labels=("폐기",)), draft(3, login="stranger", assoc="NONE")], NOW, URL, ctx=ctx), [])

    def test_stopped_channels_come_from_the_registry_mode_off_only(self):
        self.assertEqual(inbox._stopped_channels(naver_blogs("off")), frozenset({"네이버"}))
        self.assertEqual(inbox._stopped_channels(naver_blogs("package")), frozenset())
        self.assertEqual(inbox._stopped_channels([h.make_blog("a", mode="off")]), frozenset())                      # 채널 라벨이 없으면 뺀다
        self.assertEqual(inbox._stopped_channels(None), frozenset())
        self.assertEqual(inbox._stopped_channels(["x", None, 5]), frozenset())

    def test_the_registry_label_and_the_issue_label_match_whatever_their_letter_case(self):
        blogs = [h.channel_blog("naver_x", "Naver Blog", "naver", "off")]
        self.assertEqual(inbox._stopped_channels(blogs), frozenset({"naver blog"}))
        for label in ("Naver Blog", "naver blog", "NAVER BLOG"):
            items = inbox.build_items(snap(blogs=blogs, drafts=[h.make_draft(41, f"[초안][{label}] 글", label, hours=30)]))
            self.assertEqual([i.id for i in items if i.id.startswith("draft:")], ["draft:41:paused"], label)

    def test_in_a_build_a_stopped_channel_removes_its_drafts_from_the_things_to_do(self):
        drafts = [draft(41, hours=30), draft(42, "[초안][티스토리] 글", "티스토리", hours=30)]
        items = inbox.build_items(snap(blogs=naver_blogs("off"), drafts=drafts))
        self.assertEqual({i.id: i.level for i in items if i.id.startswith("draft:")}, {"draft:41:paused": "check", "draft:42:wait": "action"})
        items = inbox.build_items(snap(blogs=naver_blogs("off"), drafts=drafts, paused=True))
        self.assertEqual({i.id: i.level for i in items if i.id.startswith("draft:")}, {"draft:41:paused": "check", "draft:42:paused": "check"})

    def test_a_draft_pull_request_in_a_paused_repository_is_still_one_line_and_hides_the_open_pr_line(self):
        pr = h.make_pull(15, ci="none", mergeable=True)
        items = inbox.build_items(snap(paused=True, pulls=[pr], drafts=[h.make_draft(15, "[초안][Chance] 글", "Chance", pull=True, hours=5)],
                                       blogs=[h.channel_blog("chance", "Chance", "jekyll-git", "auto", publish_flow="pr")]))
        self.assertEqual([i.id for i in items if i.id.endswith((":paused", ":wait", ":stale", ":no_ci", ":ready"))], ["draft:15:paused"])


class StoppedBoardTest(unittest.TestCase):
    def rows(self, **kw):
        board = inbox.draft_board(snap(**kw))
        return [[cell.strip() for cell in line.strip("|").split(" | ")] for line in board.splitlines() if line.startswith("| ") and not line.startswith("| 채널")]

    def test_a_stopped_channel_with_drafts_says_they_are_from_before_the_stop(self):
        row = next(r for r in self.rows(blogs=naver_blogs("off"), drafts=[draft(41), draft(42, "[초안][네이버] 둘째")]) if r[0] == "네이버")
        self.assertEqual(row[:3], ["네이버", "2 (정지 전 초안)", "1일"])
        self.assertNotIn("정지 중", row[1])

    def test_a_stopped_channel_without_drafts_still_just_says_stopped(self):
        row = next(r for r in self.rows(blogs=naver_blogs("off")) if r[0] == "네이버")
        self.assertEqual(row[1:], ["정지", "-", "-"])

    def test_a_global_pause_marks_every_row_that_has_drafts_and_leaves_empty_rows_alone(self):
        rows = {r[0]: r for r in self.rows(blogs=naver_blogs("package"), drafts=[draft(41, "[초안][티스토리] 글", "티스토리")], paused=True)}
        self.assertEqual(rows["티스토리"][1], "1 (정지 전 초안)")
        self.assertEqual(rows["Chance"][1], "자동 공개")
        self.assertEqual(rows["네이버"][1], "0")

    def test_a_blogger_row_under_a_pause_keeps_the_rough_mark_and_adds_the_stop_mark(self):
        blogs = [h.channel_blog("blogger_macat", "Blogger 영문", "blogger", "draft", url="https://macat0722.blogspot.com/")]
        history = [h.make_entry("draft_uploaded", ago(hours=30), post_id="1")]
        rows = self.rows(blogs=blogs, histories={"blogger_macat": history}, paused=True)
        self.assertEqual(rows[0][1], "1 (대략) (정지 전 초안)")
        rows = self.rows(blogs=blogs, histories={"blogger_macat": history}, paused=True, published={"blogger_macat": frozenset()})
        self.assertEqual(rows[0][1], "1 (정지 전 초안)")
        rows = self.rows(blogs=blogs, histories={"blogger_macat": history})
        self.assertEqual(rows[0][1], "1 (대략)")                                           # 정지가 아니면 예전 그대로

    def test_the_notes_under_the_table_stop_telling_to_publish_only_when_stopped_drafts_are_listed(self):
        blogs = naver_blogs("package") + [h.channel_blog("blogger_macat", "Blogger 영문", "blogger", "draft", url="https://macat0722.blogspot.com/")]
        drafts = [draft(41, "[초안][티스토리] 글", "티스토리")]
        history = {"blogger_macat": [h.make_entry("draft_uploaded", ago(hours=30), post_id="1")]}
        paused = inbox.draft_board(snap(blogs=blogs, drafts=drafts, histories=history, paused=True))
        self.assertIn(inbox.BOARD_NOTE_MODEL_PAUSED, paused)
        self.assertIn(inbox.BOARD_NOTE_BLOGGER_PAUSED, paused)
        for note in (inbox.BOARD_NOTE_MODEL_PAUSED, inbox.BOARD_NOTE_BLOGGER_PAUSED):
            for word in URGING:
                self.assertNotIn(word, note, word)
        self.assertNotIn(inbox.BOARD_NOTE_MODEL, paused)
        normal = inbox.draft_board(snap(blogs=blogs, drafts=drafts, histories=history))
        self.assertIn(inbox.BOARD_NOTE_MODEL, normal)
        self.assertNotIn("정지 전", normal)
        empty = inbox.draft_board(snap(blogs=blogs, histories={"blogger_macat": []}, paused=True))
        self.assertIn(inbox.BOARD_NOTE_MODEL, empty)                                         # 정지 중이어도 초안이 없으면 설명은 그대로
        self.assertNotIn(inbox.BOARD_NOTE_MODEL_PAUSED, empty)
        only_off = inbox.draft_board(snap(blogs=naver_blogs("off"), drafts=[draft(42)]))
        self.assertIn(inbox.BOARD_NOTE_MODEL_STOPPED, only_off)                              # 한 채널만 멈춰도 정지 전 초안 칸이 있으면 발행을 안내하는 일반 설명 대신 정지용 설명(D5)
        self.assertNotIn(inbox.BOARD_NOTE_MODEL, only_off)
        self.assertNotIn(inbox.BOARD_NOTE_MODEL_PAUSED, only_off)                            # 전체 정지가 아니므로 '일시정지 중이라 모두'는 아니다
        self.assertIn("정지 전 초안", only_off)
        for word in URGING:
            self.assertNotIn(word, inbox.BOARD_NOTE_MODEL_STOPPED, word)

    def test_the_stop_mark_is_one_constant_the_guide_can_quote(self):
        self.assertEqual(inbox.STOPPED_DRAFTS_TEXT, " (정지 전 초안)")


# ----------------------------------------------------------------------------
# ⑤ Blogger 초안의 게시 검토
# ----------------------------------------------------------------------------
BLOGGER_URL = "https://macat0722.blogspot.com/"
GOOD_SIGNALS = {"review_quality": "pass", "review_safety": "clear"}


def uploaded(hours, post_id="1001", **extra):
    return h.make_entry("draft_uploaded", ago(hours=hours), post_id=post_id, **extra)


def blogger_items(history, published=None, paused=False, policy=None, now=NOW, mode="draft"):
    blog = h.make_blog(mode=mode, url=BLOGGER_URL)
    return inbox.blog_items([blog], {blog["key"]: history}, now, URL, published, paused, policy)


OK_FEED = {"blogger_macat": frozenset()}


def blogger_key(hours, blog="blogger_macat"):
    """정책 파일에 적는 Blogger 초안 결정 키 — 가장 새 대기 초안(올린 지 hours 시간)의 한국 시각 12자리까지."""
    return f"blogger:{blog}:drafts:{(NOW - timedelta(hours=hours)).astimezone(KST).strftime('%Y%m%d%H%M')}"


class BloggerReviewTest(unittest.TestCase):
    def test_only_when_every_signal_is_positive_does_a_draft_become_a_review_action(self):
        item = one(blogger_items([uploaded(30, **GOOD_SIGNALS)], OK_FEED))
        self.assertEqual(item.level, "action")
        self.assertEqual(item.title, "Blogger: 초안 1건 게시 검토")
        self.assertNotIn("게시 대기", item.title)
        self.assertEqual(item.url, "https://www.blogger.com/")
        self.assertIn("품질 Gate 통과와 건강·안전 차단 없음이 기록돼 있어", item.detail)
        self.assertIn(f"{inbox.DRAFT_REMIND_AFTER_HOURS}시간", item.detail)
        self.assertIn("직접 합니다", item.hint)
        self.assertTrue(item.id.startswith("blogger:blogger_macat:drafts:"))

    def test_six_hours_unpublished_alone_is_never_a_review_action(self):
        for history in ([uploaded(30)], [uploaded(30, review_quality="pass")], [uploaded(30, review_safety="clear")], [uploaded(30, review_quality="PASS", review_safety="clear")]):
            item = one(blogger_items(history, OK_FEED))
            self.assertEqual(item.level, "info", history)
            self.assertIn("검토 조건 미확인", item.title)
            self.assertEqual(item.url, "")

    def test_the_item_names_exactly_the_conditions_it_could_not_confirm(self):
        both = one(blogger_items([uploaded(30)], OK_FEED))
        self.assertIn("확인하지 못한 조건: 품질 Gate 통과 · 건강·안전 차단 없음.", both.detail)
        quality = one(blogger_items([uploaded(30, review_safety="clear")], OK_FEED))
        self.assertIn("확인하지 못한 조건: 품질 Gate 통과.", quality.detail)
        self.assertNotIn("건강·안전", quality.detail)
        safety = one(blogger_items([uploaded(30, review_quality="pass")], OK_FEED))
        self.assertIn("확인하지 못한 조건: 건강·안전 차단 없음.", safety.detail)
        self.assertNotIn("품질 Gate", safety.detail)

    def test_every_draft_must_carry_the_signals_not_just_one_of_them(self):
        item = one(blogger_items([uploaded(30, "1", **GOOD_SIGNALS), uploaded(40, "2")], OK_FEED))
        self.assertEqual((item.level, item.title), ("info", "Blogger: 초안 2건 대기(검토 조건 미확인)"))
        item = one(blogger_items([uploaded(30, "1", **GOOD_SIGNALS), uploaded(40, "2", **GOOD_SIGNALS)], OK_FEED))
        self.assertEqual((item.level, item.title), ("action", "Blogger: 초안 2건 게시 검토"))

    def test_a_human_can_review_only_when_the_public_feed_confirmed_it_is_not_out_yet(self):
        item = one(blogger_items([uploaded(30, **GOOD_SIGNALS)], None))                       # 게시 확인을 하지 않은 점검
        self.assertEqual(item.level, "info")
        self.assertIn(inbox.REVIEWABLE_GAP, item.detail)
        self.assertIn("이력으로는 게시했는지 알 수 없어", item.detail)
        item = one(blogger_items([h.make_entry("draft_uploaded", ago(hours=30), **GOOD_SIGNALS)], OK_FEED))        # 글 번호가 없는 항목
        self.assertEqual(item.level, "info")
        self.assertIn(inbox.REVIEWABLE_GAP, item.detail)
        self.assertNotIn("이력으로는 게시했는지 알 수 없어", item.detail)
        self.assertEqual(blogger_items([uploaded(30, **GOOD_SIGNALS)], {"blogger_macat": None}), [])           # 피드를 읽지 못했으면 항목 없음(조회 실패가 알린다)

    def test_a_draft_that_is_already_public_or_too_fresh_is_not_counted(self):
        self.assertEqual(blogger_items([uploaded(30, "7", **GOOD_SIGNALS)], {"blogger_macat": frozenset({"7"})}), [])
        self.assertEqual(blogger_items([uploaded(inbox.DRAFT_REMIND_AFTER_HOURS - 0.01, **GOOD_SIGNALS)], OK_FEED), [])
        self.assertEqual(one(blogger_items([uploaded(inbox.DRAFT_REMIND_AFTER_HOURS, **GOOD_SIGNALS)], OK_FEED)).level, "action")
        self.assertEqual(blogger_items([uploaded(24 * 7 + 1, **GOOD_SIGNALS)], OK_FEED), [])

    def test_a_pause_makes_it_an_earlier_draft_to_choose_about_and_never_a_review(self):
        item = one(blogger_items([uploaded(30, **GOOD_SIGNALS)], OK_FEED, paused=True))
        self.assertEqual((item.level, item.title), ("check", "Blogger: 정지 전에 생성된 초안 1건 — 유지·검토·폐기 중 선택"))
        self.assertEqual(item.url, "")
        self.assertIn("공개를 권장하지 않습니다", item.detail)
        for word in URGING:
            self.assertNotIn(word, text_of(item), word)
        again = one(blogger_items([uploaded(30)], None, paused=True))
        self.assertEqual((again.level, again.id), (item.level, item.id))

    def test_a_stopped_blogger_blog_makes_only_the_old_stopped_item(self):
        self.assertEqual([i.id for i in blogger_items([uploaded(30, **GOOD_SIGNALS)], OK_FEED, mode="off")], ["blog:blogger_macat:off"])

    def test_the_id_and_since_are_what_they_always_were(self):
        item = one(blogger_items([uploaded(70, "1"), uploaded(30, "2")], OK_FEED))
        stamp = (NOW - timedelta(hours=30)).astimezone(KST).strftime("%Y%m%d%H%M")
        self.assertEqual(item.id, f"blogger:blogger_macat:drafts:{stamp}")
        self.assertEqual(item.since, NOW - timedelta(hours=70))

    def test_the_review_conditions_are_constants_the_guide_names(self):
        self.assertEqual(inbox.REVIEWABLE_GAP, "사람 검토 가능 여부(블로그 공개 주소에서 아직 보이지 않는지)")
        self.assertEqual(inbox._review_gaps([((NOW, "time"), {})], "ok"), ["품질 Gate 통과", "건강·안전 차단 없음", inbox.REVIEWABLE_GAP])      # 글 번호도 없으면 사람 검토 조건도 빠진다
        self.assertEqual(inbox._review_gaps([((NOW, "time"), dict(GOOD_SIGNALS, post_id="1"))], "ok"), [])
        self.assertEqual(inbox._review_gaps([((NOW, "time"), dict(GOOD_SIGNALS, post_id="1"))], "unchecked"), [inbox.REVIEWABLE_GAP])


# ----------------------------------------------------------------------------
# ⑥ 철 지난 초안
# ----------------------------------------------------------------------------
SPRING = "[초안][네이버] 봄맞이 대청소를 방별로 나눠 끝내는 분할 계획표 만들기"
AUTUMN = "[초안][네이버] 가을 여행 전 집을 비울 때 확인하는 가전과 가스 쓰레기 정돈법"


def at(year, month, day):
    return datetime(year, month, day, 3, 0, tzinfo=timezone.utc)          # KST 12:00


class SeasonDraftTest(unittest.TestCase):
    CTX = inbox.DraftContext()

    def items(self, title, when, channel="네이버", hours=30, ctx=None):
        return inbox.draft_items([h.make_draft(88, title, channel, created=h.iso(when - timedelta(hours=hours)))], when, URL, ctx=ctx or self.CTX)

    def test_a_spring_draft_in_november_is_out_of_season_and_not_urged(self):
        item = one(self.items(SPRING, at(2026, 11, 11)))
        self.assertEqual((item.id, item.level), ("draft:88:season", "check"))
        self.assertEqual(item.title, "철 지난 초안 — 폐기 또는 재생성 검토 — 봄맞이 대청소를 방별로 나눠 끝내는 분할 계획표 만들기")
        self.assertIn("제목의 철(봄 2월 1일–5월 31일, 끝난 뒤 14일 유예)이 지났습니다", item.detail)
        self.assertIn("채널 네이버 · 이슈 #88", item.detail)
        self.assertNotIn("멈춰 있는 채널", item.detail)
        self.assertIn("지금 공개를 권장하지 않습니다", item.hint)
        self.assertIn("폐기", item.hint)
        for word in URGING:
            self.assertNotIn(word, text_of(item), word)
        self.assertLessEqual(len(item.title), inbox.TITLE_MAX)

    def test_an_autumn_draft_is_still_in_season_that_day_so_the_old_rule_applies(self):
        item = one(self.items(AUTUMN, at(2026, 11, 11)))
        self.assertEqual(item.id, "draft:88:wait")

    def test_the_same_draft_flips_exactly_when_its_window_plus_grace_ends(self):
        title = "[초안][티스토리] 봄맞이 정리"
        for when, expected in ((at(2027, 1, 31), "draft:88:season"), (at(2027, 2, 1), "draft:88:wait"), (at(2027, 5, 31), "draft:88:wait"),
                               (at(2027, 6, 14), "draft:88:wait"), (at(2027, 6, 15), "draft:88:season")):
            self.assertEqual(one(self.items(title, when, "티스토리")).id, expected, when)

    def test_the_korean_calendar_day_decides_not_the_utc_day(self):
        title = "[초안][티스토리] 봄맞이 정리"
        before = datetime(2027, 1, 31, 14, 59, tzinfo=timezone.utc)           # KST 1월 31일 23:59
        after = datetime(2027, 1, 31, 15, 0, tzinfo=timezone.utc)             # KST 2월 1일 00:00
        self.assertEqual(one(self.items(title, before, "티스토리")).id, "draft:88:season")
        self.assertEqual(one(self.items(title, after, "티스토리")).id, "draft:88:wait")

    def test_a_title_with_no_season_word_is_never_marked(self):
        self.assertEqual(one(self.items("[초안][네이버] 서랍 정리 순서 만들기", at(2026, 11, 11))).id, "draft:88:wait")

    def test_the_channel_tag_in_front_is_not_read_as_a_season_word(self):
        item = one(self.items("[초안][봄] 서랍 정리 순서", at(2026, 11, 11), channel="봄"))
        self.assertEqual(item.id, "draft:88:wait")
        item = one(self.items("[초안][봄] 봄맞이 정리", at(2026, 11, 11), channel="봄"))
        self.assertEqual(item.id, "draft:88:season")

    def test_without_a_context_season_words_are_ignored_like_before(self):
        when = at(2026, 11, 11)
        legacy = inbox.draft_items([h.make_draft(88, SPRING, "네이버", created=h.iso(when - timedelta(hours=30)))], when, URL)
        self.assertEqual([i.id for i in legacy], ["draft:88:wait"])

    def test_a_stale_out_of_season_draft_is_one_season_item_and_names_a_stopped_channel(self):
        item = one(self.items(SPRING, at(2026, 11, 11), hours=500, ctx=inbox.DraftContext(stopped=frozenset({"네이버"}))))
        self.assertEqual(item.id, "draft:88:season")
        self.assertIn("멈춰 있는 채널입니다", item.detail)

    def test_a_pull_request_draft_is_not_judged_by_its_season_words_so_the_wait_item_and_its_alert_stay(self):
        when = at(2026, 11, 11)
        item = one(inbox.draft_items([h.make_draft(88, "[초안][Chance] 봄맞이 글", "Chance", pull=True, created=h.iso(when - timedelta(hours=30)))], when, URL, ctx=self.CTX))
        self.assertEqual((item.id, item.level, item.url), ("draft:88:wait", "action", f"{URL}/pull/88"))          # 철이 지난 듯 보여도 새 초안의 알림 대상(D1)
        self.assertIn("PR #88", item.detail)

    def test_several_season_words_are_listed_in_table_order(self):
        item = one(self.items("[초안][네이버] 봄맞이와 여름 준비", at(2026, 11, 11)))
        self.assertIn("철(봄 2월 1일–5월 31일 / 여름 5월 15일–8월 31일, 끝난 뒤 14일 유예)", item.detail)

    def test_in_a_build_the_season_rule_needs_no_policy_and_no_stop(self):
        drafts = [h.make_draft(88, SPRING, "티스토리", created=h.iso(NOW - timedelta(hours=30)))]
        items = inbox.build_items(snap(now=at(2026, 11, 11), drafts=drafts, blogs=naver_blogs("package")))
        self.assertEqual([(i.id, i.level) for i in items if i.id.startswith("draft:")], [("draft:88:season", "check")])
        self.assertNotIn("draft:88:season", inbox.action_ids(items))


# ----------------------------------------------------------------------------
# ⑦ 운영자 결정
# ----------------------------------------------------------------------------
class DecisionTest(unittest.TestCase):
    def build(self, decisions, **kw):
        return inbox.build_items(snap(policy=make_policy(decisions=decisions), **kw))

    def test_discard_close_on_a_draft_is_a_check_item_that_recommends_discarding_and_closing(self):
        items = self.build({"draft:88": decision("discard_close", "계절이 지남")}, drafts=[h.make_draft(88, SPRING, "네이버", hours=300)], blogs=naver_blogs("off"))
        item = next(i for i in items if i.id.startswith("draft:"))
        self.assertEqual((item.id, item.level), ("draft:88:discard", "check"))
        self.assertTrue(item.title.startswith("폐기 후 닫기 권장(운영자 결정) — 봄맞이 대청소"))
        self.assertIn("운영자 결정 2026-11-11 — 계절이 지남", item.detail)
        self.assertIn("채널 네이버 · 이슈 #88", item.detail)
        self.assertIn("라벨 `폐기`를 붙인 뒤 이슈를 닫으세요", item.hint)
        self.assertIn("자동으로 닫거나 라벨을 붙이지 않습니다", item.hint)
        self.assertEqual(item.url, f"{URL}/issues/88")
        self.assertEqual(item.since, NOW - timedelta(hours=300))

    def test_the_decision_wins_over_the_season_the_stop_and_the_age(self):
        for kw in ({"paused": True}, {"blogs": naver_blogs("off")}, {}):
            items = self.build({"draft:88": decision("discard_close")}, drafts=[h.make_draft(88, SPRING, "네이버", hours=300)], **kw)
            self.assertEqual([i.id for i in items if i.id.startswith("draft:")], ["draft:88:discard"], kw)

    def test_keep_is_a_reference_item_and_ignore_removes_the_draft(self):
        drafts = [h.make_draft(88, SPRING, "네이버", hours=300), h.make_draft(89, "[초안][네이버] 다른 글", "네이버", hours=300)]
        items = self.build({"draft:88": decision("keep", "정지 전 초안이라 둔다")}, drafts=drafts)
        keep = next(i for i in items if i.id == "draft:88:keep")
        self.assertEqual(keep.level, "info")
        self.assertTrue(keep.title.startswith("유지(운영자 결정) — "))
        self.assertIn("정지 전 초안이라 둔다", keep.detail)
        self.assertIn("draft:89:stale", [i.id for i in items])                                # 다른 초안은 그대로
        items = self.build({"draft:88": decision("ignore")}, drafts=drafts)
        self.assertEqual([i.id for i in items if i.id.startswith("draft:")], ["draft:89:stale"])

    def test_a_pull_request_draft_decision_says_pr(self):
        items = self.build({"draft:15": decision("discard_close")}, drafts=[h.make_draft(15, "[초안][Chance] 글", "Chance", pull=True)])
        item = next(i for i in items if i.id.startswith("draft:"))
        self.assertIn("PR 을 닫으세요", item.hint)
        self.assertEqual(item.url, f"{URL}/pull/15")

    def test_a_decision_on_an_approval_hides_it_even_when_the_branch_state_is_unknown(self):
        runs = approvals((101, "ai/claude/M029-a"), (102, "ai/claude/M034-b"))
        key = f"approve:{runs[0]['head_sha'][:7]}"
        items = self.build({key: decision("ignore")}, approvals=runs)
        self.assertEqual(len([i for i in items if i.id.startswith("approve:")]), 1)
        self.assertNotIn(key, [i.id for i in items])
        self.assertEqual(len([i for i in inbox.build_items(snap(approvals=runs)) if i.id.startswith("approve:")]), 2)

    def test_an_approval_decision_only_covers_that_commit_so_a_new_commit_shows_again(self):
        old = h.make_approval_run(101, branch="ai/claude/M029-a", sha="1" * 40)
        new = h.make_approval_run(102, branch="ai/claude/M029-a", sha="2" * 40)
        items = self.build({"approve:1111111": decision("ignore")}, approvals=[old, new])
        self.assertEqual([i.id for i in items if i.id.startswith("approve:")], ["approve:2222222"])

    def test_keep_and_discard_on_approvals_and_pulls_lower_the_level_and_name_the_decision(self):
        runs = approvals((101, "ai/claude/M029-a"))
        key = f"approve:{runs[0]['head_sha'][:7]}"
        keep = next(i for i in self.build({key: decision("keep")}, approvals=runs) if i.id == key)
        self.assertEqual(keep.level, "info")
        self.assertTrue(keep.title.startswith("유지(운영자 결정) — 승인 대기(Approve and run)"))
        discard = next(i for i in self.build({key: decision("discard_close")}, approvals=runs) if i.id == key)
        self.assertEqual(discard.level, "check")
        self.assertIn("폐기 후 닫기 권장(운영자 결정)", discard.title)
        self.assertIn("실행을 취소하세요", discard.hint)
        self.assertIn(f"{URL}/actions/runs/101", discard.url)
        pull = self.build({"pr:15": decision("ignore")}, pulls=[h.make_pull(15)])
        self.assertNotIn("pr:15:ready", [i.id for i in pull])

    def test_decisions_never_create_an_action_and_never_raise_a_level(self):
        runs = approvals((101, "ai/claude/M029-a"))
        key = f"approve:{runs[0]['head_sha'][:7]}"
        for kind in ("keep", "discard_close", "ignore"):
            items = self.build({key: decision(kind), "draft:88": decision(kind), blogger_key(30): decision(kind), "pr:15": decision(kind)},
                               approvals=runs, drafts=[h.make_draft(88, SPRING, "네이버")], pulls=[h.make_pull(15)], blogs=[h.make_blog(mode="draft", url=BLOGGER_URL)],
                               histories={"blogger_macat": [uploaded(30, **GOOD_SIGNALS)]}, published=OK_FEED)
            self.assertEqual(inbox.action_ids(items), [], kind)

    def test_a_decision_that_points_at_an_item_that_is_gone_changes_nothing(self):
        policy_decisions = {"draft:999": decision("discard_close"), "approve:abcdef0": decision("ignore"), "pr:999": decision("ignore"), "blogger:nobody:drafts:202601010000": decision("keep")}
        base = snap(drafts=[h.make_draft(41, hours=30)], pulls=[h.make_pull(15)])
        self.assertEqual(inbox.build_items(base), inbox.build_items(snap(drafts=[h.make_draft(41, hours=30)], pulls=[h.make_pull(15)], policy=make_policy(decisions=policy_decisions))))

    def test_decisions_of_the_blogger_draft_override_every_state(self):
        for paused, history, published in ((False, [uploaded(30, **GOOD_SIGNALS)], OK_FEED), (False, [uploaded(30)], OK_FEED), (False, [uploaded(30)], None), (True, [uploaded(30)], OK_FEED)):
            keep = one(blogger_items(history, published, paused, make_policy(decisions={blogger_key(30): decision("keep", "공개하지 않고 유지")})))
            self.assertEqual((keep.level, keep.title.split(" — ")[0]), ("info", "Blogger: 초안 1건 유지"), (paused, published))
            self.assertIn("공개하지 않고 유지합니다(운영자 결정 2026-11-11) — 공개하지 않고 유지", keep.detail)
            for word in URGING:
                self.assertNotIn(word, text_of(keep), word)
            discard = one(blogger_items(history, published, paused, make_policy(decisions={blogger_key(30): decision("discard_close")})))
            self.assertEqual(discard.level, "check")
            self.assertIn("폐기 권장 — 운영자 결정(2026-11-11)", discard.title)
            self.assertIn("자동으로 지우지 않습니다", discard.hint)
            self.assertEqual(blogger_items(history, published, paused, make_policy(decisions={blogger_key(30): decision("ignore")})), [])

    def test_a_decision_bound_to_the_newest_draft_time_ends_when_a_newer_draft_arrives(self):
        older = uploaded(40, "1")
        stamp = (NOW - timedelta(hours=40)).astimezone(KST).strftime("%Y%m%d%H%M")
        policy = make_policy(decisions={f"blogger:blogger_macat:drafts:{stamp}": decision("keep", "그때의 초안")})
        [item] = blogger_items([older], OK_FEED, False, policy)
        self.assertEqual((item.level, item.title.split(" — ")[0]), ("info", "Blogger: 초안 1건 유지"))
        [fresh] = blogger_items([older, uploaded(20, "2")], OK_FEED, False, policy)                    # 새 초안이 오면 id 의 시각이 바뀌어 결정이 맞지 않는다
        self.assertNotIn("유지", fresh.title)
        self.assertIn("초안 2건 대기(검토 조건 미확인)", fresh.title)
        gone = blogger_items([older, uploaded(20, "2")], {"blogger_macat": frozenset({"2"})}, False, policy)     # 새 초안이 공개되면 다시 그 초안만 남아 결정이 맞는다
        self.assertEqual(gone[0].title.split(" — ")[0], "Blogger: 초안 1건 유지")

    def test_a_hand_built_wide_key_still_covers_every_draft_item_of_that_blog_but_the_parser_never_makes_one(self):
        with self.assertRaises(ip.PolicyError):
            make_policy(decisions={"blogger:blogger_macat:drafts": decision("keep")})                  # 넓은 키는 정책 파일로 들어올 수 없다(D8)
        policy = ip.Policy(decisions=(ip.Decision("blogger:blogger_macat:drafts", "keep", "2026-11-11", "사유"),))
        for history in ([uploaded(40, "1")], [uploaded(40, "1"), uploaded(20, "2")]):
            [item] = blogger_items(history, OK_FEED, False, policy)
            self.assertIn("유지", item.title)                                                          # 결정 찾기 자체는 앞부분이 맞으면 모두 가리지만, 파서가 이런 정책을 만들지 않는다

    def test_a_decision_for_one_blog_does_not_touch_the_other(self):
        blogs = [h.make_blog("blogger_macat", mode="draft", url=BLOGGER_URL), h.make_blog("blogger_kcyoon", "Blogger 한글", mode="draft", url="https://kcyoon.blogspot.com/")]
        histories = {"blogger_macat": [uploaded(30)], "blogger_kcyoon": [uploaded(30)]}
        policy = make_policy(decisions={blogger_key(30): decision("keep")})
        items = inbox.blog_items(blogs, histories, NOW, URL, OK_FEED, False, policy)
        self.assertEqual({i.id.split(":")[1]: i.title.split(" — ")[0] for i in items}, {"blogger_macat": "Blogger: 초안 1건 유지", "blogger_kcyoon": "Blogger 한글: 초안 1건 대기(검토 조건 미확인)"})


# ----------------------------------------------------------------------------
# 맨 위 안내와 알림
# ----------------------------------------------------------------------------
class BannerTest(unittest.TestCase):
    def test_no_banner_is_the_old_text_to_the_letter(self):
        items = [inbox.Item("a:1", "action", "할 일"), inbox.Item("i:1", "info", "참고")]
        self.assertEqual(inbox.render(items, URL), inbox.render(items, URL, banner=""))
        self.assertEqual(inbox.render(items, URL, board="## 초안 현황\n"), inbox.render(items, URL, board="## 초안 현황\n", banner=""))
        self.assertEqual(inbox.render([], URL), inbox.render([], URL, banner=""))

    def test_a_banner_is_one_quoted_line_right_under_the_title(self):
        text = inbox.render([inbox.Item("a:1", "action", "할 일")], URL, banner="참고: 정책 파일을 읽지 못했어요")
        lines = text.splitlines()
        self.assertEqual(lines[:4], ["# 확인 필요 모음", "", "> 참고: 정책 파일을 읽지 못했어요", ""])
        self.assertTrue(lines[4].startswith("**지금 해야 할 일 1건**"))
        empty = inbox.render([], URL, banner="안내")
        self.assertEqual(empty.splitlines()[2], "> 안내")

    def test_the_banner_is_neutralised_and_clipped_and_stays_inside_the_length_limit(self):
        text = inbox.render([], URL, banner="@누구 <b>x</b> & ::warning::" + "가" * 500)
        quote = next(line for line in text.splitlines() if line.startswith("> "))
        for raw in ("@", "<b>"):
            self.assertNotIn(raw, quote)
        self.assertLessEqual(len(quote), 2 + inbox.BANNER_MAX)
        items = [inbox.Item(f"a:{n}", "action", "가" * 100, "나" * 400, f"{URL}/pull/{n}", "다" * 250) for n in range(400)]
        body = inbox.render(items, URL, 58000, banner="안내")
        self.assertLessEqual(len(body), 58000)


class AlertCompatibilityTest(unittest.TestCase):
    OLD_MARKER = ("approve:7f2dfdf", "approve:8076dcf", "approve:87fc678", "approve:b27b3fb", "blogger:blogger_kcyoon:drafts:202611081938",
                  "blogger:blogger_macat:drafts:202611081745", "pause", "pr:176:ready")

    def after(self):
        runs = [h.make_approval_run(7001, branch="ai/claude/M029-a", sha="87fc678" + "0" * 33), h.make_approval_run(7002, branch="ai/claude/M034-b", sha="b27b3fb" + "0" * 33),
                h.make_approval_run(7003, branch="ai/claude/M038-c", sha="8076dcf" + "0" * 33), h.make_approval_run(7004, branch="ai/claude/M048-d", sha="7f2dfdf" + "0" * 33)]
        blogs = [h.channel_blog("blogger_macat", "Blogger 영문", "blogger", "draft", url="https://macat0722.blogspot.com/"),
                 h.channel_blog("blogger_kcyoon", "Blogger 한글", "blogger", "draft", url="https://kcyoon.blogspot.com/")]
        history = {"blogger_macat": [h.make_entry("draft_uploaded", "2026-11-08T08:45:00Z", post_id="11")], "blogger_kcyoon": [h.make_entry("draft_uploaded", "2026-11-08T10:38:00Z", post_id="22")]}
        merged = pull_raw(176, "closed", True)
        return snap(now=datetime(2026, 11, 11, 2, 16, tzinfo=timezone.utc), approvals=runs, blogs=blogs, histories=history, pulls=[merged], paused=True,
                    published={"blogger_macat": frozenset(), "blogger_kcyoon": frozenset()}, policy=make_policy(planned=PAUSE),
                    branch_prs={"ai/claude/M029-a": "merged", "ai/claude/M034-b": "merged", "ai/claude/M038-c": "merged", "ai/claude/M048-d": "closed"})

    def test_the_cleanup_only_removes_things_from_the_alert_list_so_nothing_new_is_announced(self):
        items = inbox.build_items(self.after())
        new, kept = inbox.plan_notice(items, self.OLD_MARKER)
        self.assertEqual((new, kept), ([], []))
        self.assertEqual(inbox.plan_notice(items, None), ([], []))                              # 표식이 없는 첫 점검도 알릴 것이 없다

    def test_an_old_marker_still_parses_and_the_body_is_rewritten_once(self):
        items = inbox.build_items(self.after())
        visible = inbox.render(items, URL)
        old_body = inbox.build_body("옛 본문", self.OLD_MARKER)
        marker = inbox.parse_marker(old_body)
        self.assertEqual(marker.items, tuple(sorted(self.OLD_MARKER)))
        self.assertTrue(inbox.needs_update(marker, visible, []))
        new_body = inbox.build_body(visible, [])
        self.assertFalse(inbox.needs_update(inbox.parse_marker(new_body), visible, []))          # 다음 점검부터는 쓰지 않는다

    def test_the_resume_approval_is_the_only_new_alert_the_cleanup_can_make(self):
        policy = make_policy(planned=dict(PAUSE, resume_gate_passed=True))
        snapshot = self.after()
        snapshot.policy = policy
        new, _kept = inbox.plan_notice(inbox.build_items(snapshot), self.OLD_MARKER)
        self.assertEqual(new, ["pause:resume_approval"])


class DuplicateNumberTest(unittest.TestCase):
    def test_an_issue_and_a_pull_request_with_the_same_number_make_one_draft_item_in_every_state(self):
        issue = h.make_draft(41, "[초안][네이버] 이슈 글", "네이버")
        pull = h.make_draft(41, "[초안][네이버] PR 글", "네이버", pull=True)
        contexts = (None, inbox.DraftContext(paused=True), inbox.DraftContext(stopped=frozenset({"네이버"})),
                    inbox.DraftContext(policy=make_policy(decisions={"draft:41": decision("keep")})), inbox.DraftContext(policy=make_policy(decisions={"draft:41": decision("ignore")})))
        for ctx in contexts:
            items = inbox.draft_items([issue, pull], NOW, URL, ctx=ctx)
            self.assertLessEqual(len(items), 1, ctx)
            self.assertEqual(len(items), 0 if ctx is not None and ctx.policy is not None and ctx.policy.decisions[0].kind == "ignore" else 1, ctx)
        first = one(inbox.draft_items([issue, pull], NOW, URL, ctx=inbox.DraftContext(paused=True)))
        self.assertIn("이슈 #41", first.detail)                                  # 먼저 온 항목(이슈)이 이긴다 — 같은 번호는 한 번만 센다


class RealCaseTest(unittest.TestCase):
    """2026-11-11 11시 16분 모음 본문을 만든 입력(tests/ops_inbox_repro.py) — 지금 해야 할 일 8건이 0건이 된다. 승인 대기 넷(M029·M034·M038·M048)은 시험으로 못박는다."""

    def snapshot(self, **extra):
        kwargs = repro.base_kwargs()
        kwargs.update(extra)
        return inbox.Snapshot(**kwargs)

    def real_policy(self):
        return ip.parse_policy_text((_bootstrap.ROOT / ip.POLICY_FILE).read_text(encoding="utf-8"))

    def test_the_four_waiting_runs_of_merged_branches_vanish_by_the_branch_rule_alone(self):
        merged = {run[1]: "merged" for run in repro.APPROVALS}
        items = inbox.build_items(self.snapshot(pulls=[repro.pull_merged()], branch_prs=merged))
        self.assertEqual([i.id for i in items if i.id.startswith("approve:")], [])
        closed = {run[1]: "closed" for run in repro.APPROVALS}
        self.assertEqual([i for i in inbox.build_items(self.snapshot(branch_prs=closed)) if i.id.startswith("approve:")], [])
        unknown = inbox.build_items(self.snapshot(pulls=[repro.pull_merged()]))            # 가지 상태도 정책도 모르면 넷 모두 예전처럼 보인다(숨기지 않는다)
        self.assertEqual(sorted(i.id for i in unknown if i.id.startswith("approve:")), ["approve:7f2dfdf", "approve:8076dcf", "approve:87fc678", "approve:b27b3fb"])

    def test_the_operators_ignore_decisions_alone_remove_them_too_when_the_lookup_could_not_tell(self):
        items = inbox.build_items(self.snapshot(pulls=[repro.pull_merged()], policy=self.real_policy()))
        self.assertEqual([i.id for i in items if i.id.startswith("approve:")], [])

    def test_a_branch_with_an_open_pull_request_keeps_its_waiting_run_even_with_the_real_policy_for_other_commits(self):
        runs = repro.approval_runs() + [h.make_approval_run(777, branch="ai/claude/M050-new", sha="9" * 40)]
        items = inbox.build_items(self.snapshot(approvals=runs, branch_prs={"ai/claude/M050-new": "open"}, policy=self.real_policy(), pulls=[repro.pull_merged()]))
        self.assertEqual([i.id for i in items if i.id.startswith("approve:")], ["approve:9999999"])        # 새 커밋의 승인 대기는 가려지지 않는다

    def test_pull_request_176_is_a_merge_item_while_open_and_green_and_nothing_once_merged(self):
        repo_url = f"https://github.com/{repro.REPO}"
        self.assertEqual([i.id for i in inbox.pull_items([repro.pull_open_and_green()], repro.NOW, repo_url)], ["pr:176:ready"])
        self.assertEqual(inbox.pull_items([repro.pull_merged()], repro.NOW, repo_url), [])

    def test_the_whole_inbox_has_nothing_to_do_and_keeps_the_reference_and_check_lines(self):
        merged = {run[1]: "merged" for run in repro.APPROVALS}
        items = inbox.build_items(self.snapshot(pulls=[repro.pull_merged()], branch_prs=merged, policy=self.real_policy()))
        by_level = {level: sorted(i.id for i in items if i.level == level) for level in ("action", "check", "info")}
        self.assertEqual(by_level["action"], [])
        self.assertEqual(by_level["check"], ["draft:103:discard", "draft:88:discard"])
        self.assertEqual(by_level["info"], ["blog:naver_life_tips:off", "blogger:blogger_kcyoon:drafts:202611081938", "blogger:blogger_macat:drafts:202611081745", "pause:planned",
                                            "stat:blogger_kcyoon", "stat:blogger_macat", "stat:chance"])
        board = inbox.draft_board(self.snapshot(pulls=[repro.pull_merged()], branch_prs=merged, policy=self.real_policy()))
        body = inbox.render(items, f"https://github.com/{repro.REPO}", board=board)
        self.assertIn("**지금 해야 할 일 0건** · 확인하면 좋은 것 2건 · 참고 7건", body)
        for text in [text_of(i) for i in items if i.id.startswith(("draft:", "blogger:"))] + [board]:         # 정지 중인 채널의 초안 항목과 표 어디에도 발행·게시를 권하는 말이 없다
            for word in URGING:
                self.assertNotIn(word, text, word)


class SourceRegistrationTest(unittest.TestCase):
    def test_the_approval_lookup_failure_is_labelled_and_keeps_the_previous_approval_ids(self):
        self.assertIn("approval_prs", inbox.SOURCE_LABELS)
        self.assertEqual(inbox.SOURCE_PREFIXES["approval_prs"], ("approve:",))
        kept = inbox.plan_notice([], ("approve:abcdef0", "pr:1:ready"), [("approval_prs", "x")])[1]
        self.assertEqual(kept, ["approve:abcdef0"])                      # 조회가 실패한 점검은 이전 승인 대기 id 를 표식에 이어 간다 — 복구돼도 같은 항목이 새 알림이 되지 않는다
        self.assertEqual(inbox.plan_notice([], ("approve:abcdef0",), [])[1], [])

    def test_the_failure_item_names_the_source_in_words_and_neutralises_the_branch_name(self):
        item = one(inbox.failure_items([("approval_prs", "ai/claude/<b>x</b>: HTTP 502")], URL))
        self.assertEqual(item.level, "check")
        self.assertIn("조회 실패 — 승인 대기 실행의 PR 상태(가지 이름으로 조회)", item.title)
        self.assertNotIn("<b>", inbox.render([item], URL))


# ----------------------------------------------------------------------------
# 독립 검증 뒤 고침(2026-11-11, 결함 D-280–D-289)
# ----------------------------------------------------------------------------
class PullDraftAlertTest(unittest.TestCase):
    """D1(D-280): 철 지난 초안 판정은 이슈 초안(티스토리·네이버 패키지)에만 쓴다 — Chance 승인 PR 초안은 제목에 계절 낱말이 있어도 새 초안 알림(wait)을 지킨다."""
    CASES = (("올겨울 한파 대비 전력 수요 전망", at(2026, 10, 25)), ("올겨울 한파 대비 전력 수요 전망", at(2027, 3, 20)), ("내년 여름 전력 수급 전망과 요금", at(2026, 11, 11)),
             ("연말 소비 지표와 금리 전망", at(2026, 11, 11)), ("봄맞이 대청소 계획", at(2026, 11, 11)))

    def chance_pr(self, title, when, hours=2):
        return h.make_draft(88, f"[초안][Chance] {title}", "Chance", pull=True, created=h.iso(when - timedelta(hours=hours)))

    def test_each_pull_request_draft_with_a_season_word_stays_a_new_draft_action_with_its_alert(self):
        blogs = [h.channel_blog("chance", "Chance", "jekyll-git", "auto", publish_flow="pr")]
        for title, when in self.CASES:
            items = inbox.build_items(snap(now=when, drafts=[self.chance_pr(title, when)], blogs=blogs))
            self.assertEqual([(i.id, i.level) for i in items if i.id.startswith("draft:")], [("draft:88:wait", "action")], (title, when))
            new, _kept = inbox.plan_notice(items, ())
            self.assertIn("draft:88:wait", new, (title, when))                      # 코멘트(멘션)와 텔레그램 '발행 대기' 알림의 재료가 그대로 남는다

    def test_the_same_titles_as_issue_drafts_are_still_season_checks_without_an_alert(self):
        for title, when in self.CASES:
            issue = h.make_draft(88, f"[초안][네이버] {title}", "네이버", created=h.iso(when - timedelta(hours=2)))
            for blogs in (naver_blogs("package"), naver_blogs("off")):               # 활성 채널도 멈춘 채널도 이슈 초안은 예전 그대로 철 판정
                items = inbox.build_items(snap(now=when, drafts=[issue], blogs=blogs))
                self.assertEqual([(i.id, i.level) for i in items if i.id.startswith("draft:")], [("draft:88:season", "check")], (title, when))
                self.assertEqual(inbox.plan_notice(items, ())[0], [], (title, when))

    def test_a_stale_pull_request_draft_with_a_season_word_is_the_old_stale_check(self):
        when = at(2026, 11, 11)
        item = one(inbox.draft_items([self.chance_pr("봄맞이 글", when, hours=300)], when, URL, ctx=inbox.DraftContext()))
        self.assertEqual((item.id, item.level), ("draft:88:stale", "check"))

    def test_the_stop_rule_and_the_operators_decision_still_apply_to_pull_request_drafts(self):
        when = at(2026, 11, 11)
        stopped = one(inbox.draft_items([self.chance_pr("봄맞이 글", when)], when, URL, ctx=inbox.DraftContext(paused=True)))
        self.assertEqual((stopped.id, stopped.level), ("draft:88:paused", "check"))
        decided = one(inbox.draft_items([self.chance_pr("봄맞이 글", when)], when, URL, ctx=inbox.DraftContext(policy=make_policy(decisions={"draft:88": decision("keep")}))))
        self.assertEqual(decided.id, "draft:88:keep")

    def test_a_pull_request_and_an_issue_with_the_same_title_are_told_apart_by_kind_only(self):
        when = at(2026, 11, 11)
        both = inbox.draft_items([h.make_draft(88, "[초안][네이버] 봄맞이 글", "네이버", created=h.iso(when - timedelta(hours=2))),
                                  h.make_draft(89, "[초안][Chance] 봄맞이 글", "Chance", pull=True, created=h.iso(when - timedelta(hours=2)))], when, URL, ctx=inbox.DraftContext())
        self.assertEqual([i.id for i in both], ["draft:88:season", "draft:89:wait"])


class ApprovalSafetyTest(unittest.TestCase):
    """D2(D-281): 병합됐거나 닫힌 가지의 승인 대기를 뺄 때 이 저장소의 그 PR 에 딸린 실행만 뺀다 — 포크 PR 의 실행·그 PR 의 커밋이 아닌 실행은 새 일이라 보인다."""
    BRANCH = "ai/claude/M029-a"
    SHA = "a" * 40
    STATES = {BRANCH: "merged"}
    HEADS = {BRANCH: frozenset({SHA})}

    def run_(self, run_id=1, sha=None, **kw):
        return h.make_approval_run(run_id, branch=self.BRANCH, sha=sha or self.SHA, **kw)

    def numbers(self, runs, states=None, heads=None):
        shown = inbox.approval_items(runs, URL, branch_states=self.STATES if states is None else states, branch_heads=heads)
        return [i.url.rsplit("/", 1)[1] for i in shown if i.id.startswith("approve:") and i.id != "approve:more"]

    def test_a_run_from_a_fork_with_the_same_branch_name_is_not_hidden(self):
        fork = dict(self.run_(1), head_repository={"full_name": "stranger/blog"})
        self.assertEqual(self.numbers([fork]), ["1"])
        self.assertEqual(self.numbers([fork], heads=self.HEADS), ["1"])
        self.assertEqual(self.numbers([self.run_(2)]), [])                                 # 이 저장소의 실행은 예전처럼 빠진다
        self.assertEqual(self.numbers([dict(self.run_(3), head_repository={"full_name": "OCTO/Blog"})]), [])        # 저장소 이름은 대소문자를 가리지 않는다

    def test_an_unknown_head_repository_of_a_pull_request_run_is_not_hidden_either(self):
        for head in (None, "x", 5, {}, {"full_name": None}, {"full_name": 5}, {"name": "blog"}):
            self.assertEqual(self.numbers([dict(self.run_(1), head_repository=head)]), ["1"], repr(head))
        self.assertEqual(self.numbers([{k: v for k, v in self.run_(1).items() if k != "head_repository"}]), ["1"])

    def test_only_pull_request_events_look_at_the_head_repository(self):
        for event in ("push", "workflow_dispatch", "schedule"):
            run = {k: v for k, v in dict(self.run_(1), event=event).items() if k != "head_repository"}
            self.assertEqual(self.numbers([run]), [], event)                               # foreign_pull_run 과 같은 기준 — 다른 이벤트는 head 저장소를 보지 않는다
        target = dict(self.run_(2), event="pull_request_target", head_repository={"full_name": "stranger/blog"})
        self.assertEqual(self.numbers([target]), ["2"])

    def test_with_the_commits_of_the_finished_pull_requests_only_their_runs_are_hidden(self):
        old, new = self.run_(1), self.run_(2, sha="b" * 40)
        self.assertEqual(self.numbers([old, new], heads=self.HEADS), ["2"])                # 같은 이름의 가지에 올라온 새 커밋의 실행은 새 일이다
        self.assertEqual(self.numbers([old, new]), [])                                      # 커밋 정보가 없는 호출(옛 호출·시험)은 가지 이름만 본다
        self.assertEqual(self.numbers([old, new], heads={self.BRANCH: frozenset({self.SHA, "b" * 40})}), [])

    def test_a_commit_that_is_missing_or_unreadable_is_never_hidden_when_commits_are_checked(self):
        for sha in (None, "", "a" * 39, "g" * 40, "a" * 41, 5):
            run = dict(self.run_(1), head_sha=sha)
            self.assertEqual(self.numbers([run], heads=self.HEADS), ["1"], repr(sha))
        self.assertEqual(self.numbers([self.run_(1, sha="A" * 40)], heads=self.HEADS), [])      # 커밋 글자의 대소문자는 가리지 않는다

    def test_a_commit_that_is_not_a_full_hex_commit_never_matches_even_when_the_set_holds_the_same_text(self):
        for sha in ("a" * 39, "g" * 40, "A" * 39, "a" * 41, ""):
            run = dict(self.run_(1), head_sha=sha)
            heads = {self.BRANCH: frozenset({sha, sha.lower(), "ghost"})}
            self.assertEqual(self.numbers([run], heads=heads), ["1"], repr(sha))

    def test_a_branch_without_known_commits_is_never_hidden_when_commits_are_checked(self):
        for heads in ({}, {self.BRANCH: frozenset()}, {"ai/claude/other": frozenset({self.SHA})}, {self.BRANCH: None}):
            self.assertEqual(self.numbers([self.run_(1)], heads=heads), ["1"], repr(heads))

    def test_heads_that_are_not_a_mapping_are_ignored_like_states_that_are_not_a_mapping(self):
        for junk in ("x", 5, [self.SHA], (self.BRANCH,)):
            self.assertEqual(self.numbers([self.run_(1)], heads=junk), [], repr(junk))

    def test_approval_run_finished_is_the_one_decision_the_rule_and_the_log_line_share(self):
        run = self.run_(1)
        self.assertTrue(inbox.approval_run_finished(run, h.REPO, self.STATES, self.HEADS))
        self.assertTrue(inbox.approval_run_finished(run, h.REPO, {self.BRANCH: "closed"}, None))
        self.assertFalse(inbox.approval_run_finished(run, h.REPO, {self.BRANCH: "open"}, self.HEADS))
        self.assertFalse(inbox.approval_run_finished(run, h.REPO, {}, self.HEADS))
        self.assertFalse(inbox.approval_run_finished(run, "other/repo", self.STATES, self.HEADS))                   # 다른 저장소의 모음이면 이 실행은 포크 쪽 실행이다
        self.assertFalse(inbox.approval_run_finished(dict(run, head_branch=None), h.REPO, self.STATES, self.HEADS))

    def test_the_snapshot_carries_the_commits_and_a_build_uses_them(self):
        self.assertIsNone(snap().branch_pr_heads)
        runs = [self.run_(1), self.run_(2, sha="b" * 40)]
        strict = inbox.build_items(snap(approvals=runs, branch_prs=self.STATES, branch_pr_heads=self.HEADS))
        self.assertEqual([i.url.rsplit("/", 1)[1] for i in strict if i.id.startswith("approve:")], ["2"])
        loose = inbox.build_items(snap(approvals=runs, branch_prs=self.STATES))
        self.assertEqual([i for i in loose if i.id.startswith("approve:")], [])

    def test_the_summary_item_counts_only_what_is_really_still_waiting(self):
        shas = [f"{n + 1:x}" + "0" * 39 for n in range(8)]                                  # 앞 7자가 서로 다른 커밋 여덟(같은 커밋의 실행은 한 항목으로 묶이므로)
        runs = [h.make_approval_run(100 + n, branch=self.BRANCH, sha=sha) for n, sha in enumerate(shas)]
        heads = {self.BRANCH: frozenset(shas[:3])}                                         # 셋은 끝난 PR 의 커밋, 다섯은 새 커밋
        shown = inbox.approval_items(runs, URL, branch_states=self.STATES, branch_heads=heads)
        self.assertEqual(len(shown), 5)
        self.assertNotIn("approve:more", [i.id for i in shown])


class StoppedNoteTest(unittest.TestCase):
    """D5(D-284): 표에 '정지 전 초안' 칸이 하나라도 있으면 발행을 안내하는 일반 설명 대신 정지용 설명이다."""

    def board(self, **kw):
        return inbox.draft_board(snap(**kw))

    def test_a_table_with_one_stopped_channel_and_one_active_channel_gets_the_stopped_note(self):
        drafts = [draft(41), draft(42, "[초안][티스토리] 글", "티스토리")]
        text = self.board(blogs=naver_blogs("off"), drafts=drafts)
        self.assertIn(inbox.BOARD_NOTE_MODEL_STOPPED, text)
        for other in (inbox.BOARD_NOTE_MODEL, inbox.BOARD_NOTE_MODEL_PAUSED):
            self.assertNotIn(other, text)
        lines = [line for line in text.splitlines() if line.startswith("| ") and not line.startswith("| 채널")]
        rows = {cells[0]: cells[1] for cells in ([c.strip() for c in line.strip("|").split(" | ")] for line in lines)}
        self.assertEqual((rows["네이버"], rows["티스토리"]), ("1 (정지 전 초안)", "1"))

    def test_the_stopped_note_names_the_mark_and_tells_nothing_to_publish(self):
        note = inbox.BOARD_NOTE_MODEL_STOPPED
        self.assertIn("(정지 전 초안)", note)
        self.assertIn("공개를 권장하지 않으며 유지·검토·폐기 중에서 고릅니다", note)
        self.assertIn("다른 채널의 초안은 아래 항목의 안내를 따르세요", note)
        for word in URGING + ("올리",):
            self.assertNotIn(word, note, word)
        self.assertNotIn("모두 정지 전에 만든", note)                                      # 일부 채널만 멈췄을 때 '모두'라고 하지 않는다

    def test_a_global_pause_keeps_its_own_note_and_a_stopped_channel_without_drafts_changes_nothing(self):
        paused = self.board(blogs=naver_blogs("package"), drafts=[draft(42, "[초안][티스토리] 글", "티스토리")], paused=True)
        self.assertIn(inbox.BOARD_NOTE_MODEL_PAUSED, paused)
        self.assertNotIn(inbox.BOARD_NOTE_MODEL_STOPPED, paused)
        quiet = self.board(blogs=naver_blogs("off"))                                      # 멈춘 채널에 초안이 없으면 칸은 '정지' 뿐이라 일반 설명 그대로
        self.assertIn(inbox.BOARD_NOTE_MODEL, quiet)
        self.assertNotIn(inbox.BOARD_NOTE_MODEL_STOPPED, quiet)

    def test_the_blogger_note_follows_only_the_global_pause(self):
        blogs = naver_blogs("off") + [h.channel_blog("blogger_macat", "Blogger 영문", "blogger", "draft", url=BLOGGER_URL)]
        history = {"blogger_macat": [h.make_entry("draft_uploaded", ago(hours=30), post_id="1")]}
        only_off = self.board(blogs=blogs, drafts=[draft(41)], histories=history)
        self.assertIn(inbox.BOARD_NOTE_MODEL_STOPPED, only_off)
        self.assertNotIn(inbox.BOARD_NOTE_BLOGGER_PAUSED, only_off)                       # Blogger 채널은 멈추지 않았으니 Blogger 안내는 그대로
        self.assertIn("Blogger 는 초안함에 올린 기록", only_off)


class DraftChannelTypeTest(unittest.TestCase):
    """D7(D-286): 초안의 channel 이 글이 아니어도(참·숫자·목록) 초안 항목 만들기가 죽지 않는다 — 채널 표시가 없는 것처럼 본다."""

    def test_a_channel_that_is_not_text_never_breaks_the_draft_rules(self):
        contexts = (None, inbox.DraftContext(), inbox.DraftContext(paused=True), inbox.DraftContext(stopped=frozenset({"네이버"})),
                    inbox.DraftContext(policy=make_policy(decisions={"draft:88": decision("keep")})))
        for channel in (True, 5, 1.5, ["네이버"], {"a": 1}, b"x"):
            odd = dict(h.make_draft(88, "[초안][네이버] 서랍 정리", "네이버"), channel=channel)
            for ctx in contexts:
                items = inbox.draft_items([odd], NOW, URL, ctx=ctx)
                self.assertEqual(len(items), 1, (channel, ctx))
                self.assertEqual(items[0].url, f"{URL}/issues/88")

    def test_such_a_draft_is_not_taken_for_a_stopped_channel(self):
        odd = dict(h.make_draft(88, "[초안][네이버] 서랍 정리", "네이버"), channel=True)
        item = one(inbox.draft_items([odd], NOW, URL, ctx=inbox.DraftContext(stopped=frozenset({"네이버", "true"}))))
        self.assertTrue(item.id.endswith((":wait", ":stale")), item.id)
        self.assertEqual(one(inbox.draft_items([odd], NOW, URL, ctx=inbox.DraftContext(paused=True))).id, "draft:88:paused")


class PlannedPauseDeclaredTest(unittest.TestCase):
    """D9(D-289): 선언은 켜짐·이유·재개 조건·결정 근거가 모두 있어야 한다(파서가 아니라 값 자체의 규칙)."""
    FULL = dict(active=True, since="2026-11-09", reason="이유", decision_ref="근거", resume_conditions=("조건",))

    def test_every_part_is_needed_for_the_declaration(self):
        self.assertTrue(ip.PlannedPause(**self.FULL).declared)
        for name, empty in (("active", False), ("reason", ""), ("decision_ref", ""), ("resume_conditions", ())):
            self.assertFalse(ip.PlannedPause(**dict(self.FULL, **{name: empty})).declared, name)

    def test_a_hand_built_pause_without_a_basis_or_conditions_is_still_the_old_action(self):
        for name, empty in (("decision_ref", ""), ("reason", ""), ("resume_conditions", ())):
            policy = ip.Policy(planned_pause=ip.PlannedPause(**dict(self.FULL, **{name: empty})))
            self.assertEqual([i.id for i in inbox.pause_items(True, URL, policy)], ["pause"], name)
            self.assertEqual(inbox.pause_items(False, URL, policy), [], name)              # 선언이 아니면 변수가 꺼져도 확인 항목이 없다


class PlannedPauseCheckTest(unittest.TestCase):
    """D10(D-288): 계획된 정지가 길어지거나(21일 초과) 정책은 정지를 선언했는데 변수가 꺼져 있으면 확인 항목(표시만)."""
    SINCE = date(2026, 11, 9)

    def plan(self, **changes):
        return make_policy(planned=dict(PAUSE, **changes))

    def ids(self, paused, policy, today):
        return [(i.id, i.level) for i in inbox.pause_items(paused, URL, policy, today)]

    def test_the_limit_is_one_constant_of_twenty_one_days(self):
        self.assertEqual(inbox.PLANNED_PAUSE_LONG_DAYS, 21)

    def test_a_pause_older_than_the_limit_adds_a_check_item_on_the_twenty_second_day(self):
        policy = self.plan()
        planned = [("pause:planned", "info")]
        self.assertEqual(self.ids(True, policy, self.SINCE + timedelta(days=21)), planned)
        self.assertEqual(self.ids(True, policy, self.SINCE + timedelta(days=22)), planned + [("pause:long", "check")])
        self.assertEqual(self.ids(True, policy, self.SINCE + timedelta(days=400)), planned + [("pause:long", "check")])
        self.assertEqual(self.ids(True, policy, self.SINCE), planned)
        self.assertEqual(self.ids(True, policy, self.SINCE - timedelta(days=3)), planned)             # 시작일이 오늘보다 뒤면 길어진 것이 아니다
        self.assertEqual(self.ids(True, policy, None), planned)                                        # 오늘을 모르는 호출은 예전과 같다

    def test_the_long_pause_item_changes_nothing_and_has_no_day_count_so_the_body_is_stable(self):
        item = inbox.pause_items(True, URL, self.plan(), self.SINCE + timedelta(days=30))[1]
        self.assertEqual(item.title, "계획된 일시정지가 길어졌어요 — 재개 조건을 점검하세요")
        self.assertEqual(item.url, "")
        self.assertIn("2026-11-09부터 21일이 넘도록", item.detail)
        self.assertIn("재개 조건 5가지", item.detail)
        self.assertIn("변수·초안·설정을 바꾸지 않습니다", item.hint)
        self.assertEqual(item, inbox.pause_items(True, URL, self.plan(), self.SINCE + timedelta(days=90))[1])      # 날마다 같은 글자 — 경과 일수를 넣지 않았다
        for word in ("삭제", "false", "settings/variables"):
            self.assertNotIn(word, repr(item), word)
        text = inbox.render([item], URL)
        self.assertNotIn("바로 하기", text)
        self.assertIn("## 확인하면 좋은 것 (1건)", text)

    def test_a_passed_gate_shows_only_the_resume_approval(self):
        self.assertEqual(self.ids(True, self.plan(resume_gate_passed=True), self.SINCE + timedelta(days=100)), [("pause:resume_approval", "action")])

    def test_a_declared_pause_with_the_variable_off_asks_whether_it_was_a_mistake(self):
        item = one(inbox.pause_items(False, URL, self.plan(), self.SINCE + timedelta(days=100)))
        self.assertEqual((item.id, item.level), ("pause:unset", "check"))
        self.assertIn("실수로 해제했나요", item.title)
        self.assertEqual(item.url, "")
        self.assertIn("PIPELINE_PAUSE 는 꺼져 있어", item.detail)
        self.assertIn("제한 재개 조건을 보장하기 전까지 일부러 멈춤", item.detail)
        self.assertIn("정책 파일의 일시정지 선언(planned_pause 의 active)을 끄는 변경을 AI 에게 요청하세요", item.hint)
        self.assertIn("변수를 바꾸지 않습니다", item.hint)
        for word in ("삭제", "false", "settings/variables"):
            self.assertNotIn(word, repr(item), word)
        self.assertEqual(item, one(inbox.pause_items(False, URL, self.plan(), None)))                 # 오늘을 몰라도 같다
        self.assertNotIn("바로 하기", inbox.render([item], URL))

    def test_nothing_is_added_when_the_policy_declares_nothing(self):
        for policy in (None, make_policy(), make_policy(planned={"active": False}), make_policy(planned=dict(PAUSE, active=False)),
                       make_policy(decisions={"draft:1": decision("keep")}), "x", 5, object()):
            self.assertEqual(inbox.pause_items(False, URL, policy, self.SINCE + timedelta(days=100)), [], repr(policy))
        self.assertEqual(inbox.pause_items(True, URL, None, self.SINCE + timedelta(days=100)), inbox.pause_items(True, URL))

    def test_pause_days_reads_only_a_real_date(self):
        self.assertEqual(inbox._pause_days("2026-11-09", date(2026, 11, 12)), 3)
        self.assertEqual(inbox._pause_days("2026-11-09", date(2026, 11, 1)), -8)
        for junk in ("", "x", None, 5, "2026-13-01", "20261109"):
            self.assertIsNone(inbox._pause_days(junk, date(2026, 11, 12)), repr(junk))

    def test_in_a_build_the_checks_are_check_items_and_nothing_alerts(self):
        late = datetime(2026, 12, 5, 3, 0, tzinfo=timezone.utc)
        items = inbox.build_items(snap(now=late, paused=True, policy=self.plan()))
        self.assertEqual([(i.id, i.level) for i in items if i.id.startswith("pause")], [("pause:long", "check"), ("pause:planned", "info")])
        self.assertEqual(inbox.action_ids(items), [])
        unset = inbox.build_items(snap(now=late, paused=False, policy=self.plan()))
        self.assertEqual([(i.id, i.level) for i in unset if i.id.startswith("pause")], [("pause:unset", "check")])
        self.assertEqual(inbox.plan_notice(unset, ()), ([], []))
        self.assertEqual(inbox.build_items(snap(now=late, paused=False)), inbox.build_items(snap(now=late, paused=False, policy=None)))        # 정책이 없으면 예전과 같다
        self.assertEqual([i.id for i in inbox.build_items(snap(now=NOW, paused=True, policy=self.plan())) if i.id.startswith("pause")], ["pause:planned"])   # 정지 초기(NOW 는 시작일 앞)

    def test_the_planned_pause_hint_tells_the_truth_about_what_makes_the_resume_approval_appear(self):
        hint = one(inbox.pause_items(True, URL, self.plan())).hint
        self.assertIn("재개 조건이 모두 통과했다고 정책 파일에 기록되면(AI 가 준비하고 운영자가 병합하는 변경) 재개 승인 항목으로 알립니다", hint)
        self.assertIn("해제하지 마세요", hint)
        for wrong in ("알려 드립니다", "통과하면 이 모음이"):                                 # 모음이 조건 통과를 스스로 아는 것처럼 말하지 않는다(D4)
            self.assertNotIn(wrong, hint, wrong)

    def test_the_korean_midnight_is_the_edge_of_the_day_in_a_build_too(self):
        before = datetime(2026, 11, 30, 14, 59, tzinfo=timezone.utc)                      # KST 11월 30일 23:59 → 시작 뒤 21일
        after = datetime(2026, 11, 30, 15, 0, tzinfo=timezone.utc)                        # KST 12월 1일 00:00 → 시작 뒤 22일(UTC 날짜로는 아직 11월 30일)
        self.assertEqual([i.id for i in inbox.build_items(snap(now=before, paused=True, policy=self.plan())) if i.id.startswith("pause")], ["pause:planned"])
        self.assertEqual([i.id for i in inbox.build_items(snap(now=after, paused=True, policy=self.plan())) if i.id.startswith("pause")], ["pause:long", "pause:planned"])

    def test_the_korean_date_decides_the_day(self):
        before = datetime(2026, 12, 1, 14, 59, tzinfo=timezone.utc)                       # KST 12월 1일 23:59 → 시작 뒤 22일
        self.assertEqual(inbox.kst_date(before), date(2026, 12, 1))
        self.assertEqual(inbox.kst_date(datetime(2026, 12, 1, 15, 0, tzinfo=timezone.utc)), date(2026, 12, 2))
        self.assertEqual(inbox.kst_date(datetime(2026, 12, 1, 15, 0)), date(2026, 12, 2))           # 시간대가 없으면 UTC 로 본다
        long_ids = [i.id for i in inbox.build_items(snap(now=before, paused=True, policy=self.plan())) if i.id.startswith("pause")]
        self.assertEqual(long_ids, ["pause:long", "pause:planned"])
        edge = datetime(2026, 11, 30, 14, 59, tzinfo=timezone.utc)                           # KST 11월 30일 23:59 → 시작 뒤 21일 — 아직 아니다
        self.assertEqual([i.id for i in inbox.build_items(snap(now=edge, paused=True, policy=self.plan())) if i.id.startswith("pause")], ["pause:planned"])


if __name__ == "__main__":
    unittest.main()
