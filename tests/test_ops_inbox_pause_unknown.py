"""확인 필요 모음의 '정지 변수의 값을 알 수 없다' 확인 항목 `pause:unknown`(2차 검증 BP2S-2, 결함 D-423). 네트워크 없이 돈다.

배경: 정지 변수 `PIPELINE_PAUSE` 의 값이 켜짐(1·true·yes·on)도 꺼짐(0·false·no·off·비움)도 아니면 이제 모든 읽는 곳이 정지로 읽는다(BP-S1-3, D-412 — 오타 하나로 킬 스위치가 조용히 꺼지던 것을 닫았다).
그러면 반대로 '오타로 걸린 정지'를 운영자가 알아볼 길이 필요하다: 이 모음의 '자동 발행이 멈춰 있습니다 — 해제 방법'(pause) 항목은 일부러 켠 정지와 같은 글이었고, 값이 틀렸다는 사실은
각 실행의 ::error:: 줄과 실행 요약에만 있었다. 이제 알 수 없는 값일 때만 확인 항목(check — 알림 없음) 하나가 더 붙는다: "변수 PIPELINE_PAUSE 의 값을 알 수 없어 정지로 읽고 있습니다 — 값을 고치거나 지우세요".
지키는 것: ① 받은 값은 어디에도 싣지 않는다 ② 정지의 방향·기존 항목(pause·pause:planned·pause:long·pause:resume_approval·pause:unset)·알림 개수는 그대로다(워치독은 일부러 조용하다)
③ 알 수 없는 값이 아닐 때(기본값)는 예전과 글자 하나 다르지 않다 ④ 이 모음은 변수를 바꾸지 않는다.
"""
import dataclasses
import inspect
import json
import tempfile
import unittest
from pathlib import Path

import _bootstrap
import ops_inbox_helpers as h
import ops_inbox as oi
from pipeline import inbox, pause
from pipeline import inbox_policy as ip

NOW, URL, ago = h.NOW, h.REPO_URL, h.ago
ENV = {"GITHUB_REPOSITORY": h.REPO, "GITHUB_TOKEN": "CANARY_" + "INBOX_" + "TOKEN_" + "VALUE_0123456789", "GITHUB_REPOSITORY_OWNER": "octo"}
TITLE = "변수 PIPELINE_PAUSE 의 값을 알 수 없어 정지로 읽고 있습니다 — 값을 고치거나 지우세요"
PAUSE_POLICY = {"active": True, "since": "2026-09-01", "reason": "제한 재개 조건을 보장하기 전까지 일부러 멈춤", "decision_ref": "운영자 결정 2026-09-01, 확인 요청 008",
                "resume_conditions": ["승인 초안 PR 로만 공개", "하루 최대 1편", "그림자 모드 3회 통과"], "resume_gate_passed": False}


def policy_with(**changes):
    return ip.parse_policy({"schema_version": 1, "planned_pause": dict(PAUSE_POLICY, **changes)})


def snap(**kw):
    base = dict(now=NOW, repo=h.REPO)
    base.update(kw)
    return inbox.Snapshot(**base)


def ids(items):
    return [item.id for item in items]


class PauseUnknownItemTest(unittest.TestCase):
    def test_without_the_flag_the_items_are_exactly_the_old_ones(self):
        """기본값(unknown 을 안 줌·False)은 예전과 같다 — 정책 없음·계획된 정지·재개 승인·꺼짐 모두."""
        today = NOW.date()
        for paused, policy in ((True, None), (True, policy_with()), (True, policy_with(resume_gate_passed=True)), (False, None), (False, policy_with())):
            with self.subTest(paused=paused, declared=policy is not None):
                old = inbox.pause_items(paused, URL, policy, today)
                self.assertEqual(inbox.pause_items(paused, URL, policy, today, False), old)
                self.assertEqual(inbox.pause_items(paused, URL, policy, today, unknown=False), old)
                self.assertNotIn("pause:unknown", ids(old))

    def test_an_unknown_value_adds_exactly_one_check_item_after_the_usual_ones(self):
        items = inbox.pause_items(True, URL, None, None, True)
        self.assertEqual(ids(items), ["pause", "pause:unknown"])
        item = items[-1]
        self.assertEqual(item.level, "check")
        self.assertEqual(item.title, TITLE)
        self.assertEqual(item.title, inbox.PAUSE_UNKNOWN_TITLE)
        self.assertEqual(item.url, f"{URL}/settings/variables/actions")
        self.assertIsNone(item.since)

    def test_the_text_names_the_cause_the_accepted_values_and_what_to_do_without_changing_the_variable(self):
        item = inbox.pause_items(True, URL, None, None, True)[-1]
        for word in ("알 수 없어", "정지로 읽", "고치거나 지우세요"):
            self.assertIn(word, item.title, word)
        for word in ("켜짐(1·true·yes·on)", "꺼짐(0·false·no·off·비움)", "정지로 읽고", "오타일 수 있습니다", "받은 값은 이 모음에 싣지 않습니다"):
            self.assertIn(word, item.detail, word)
        for word in ("true 로 고치세요", "삭제(또는 false 로 변경)", "이 모음은 변수를 바꾸지 않습니다"):
            self.assertIn(word, item.hint, word)

    def test_the_other_pause_items_and_their_order_are_unchanged_when_the_flag_is_on(self):
        today = NOW.date()
        for name, policy, expected in (("정책 없음", None, ["pause", "pause:unknown"]),
                                       ("계획된 정지", policy_with(), ["pause:planned", "pause:long", "pause:unknown"]),
                                       ("재개 승인", policy_with(resume_gate_passed=True), ["pause:resume_approval", "pause:unknown"])):
            with self.subTest(case=name):
                usual = inbox.pause_items(True, URL, policy, today)
                with_flag = inbox.pause_items(True, URL, policy, today, True)
                self.assertEqual(ids(with_flag), expected)
                self.assertEqual(with_flag[:-1], usual)                                   # 기존 항목은 글자 하나 다르지 않다
                self.assertEqual(with_flag[-1].level, "check")

    def test_a_short_pause_has_no_long_item_so_only_the_planned_one_and_the_unknown_one_appear(self):
        policy = policy_with(since="2026-10-20")
        self.assertEqual(ids(inbox.pause_items(True, URL, policy, NOW.date(), True)), ["pause:planned", "pause:unknown"])

    def test_the_item_exists_only_when_the_variable_is_read_as_paused(self):
        """unknown 인데 paused 가 거짓인 호출은 말이 안 되는 입력이다 — 예전 항목만 돌려준다(없음, 선언이 있으면 pause:unset)."""
        self.assertEqual(inbox.pause_items(False, URL, None, None, True), [])
        self.assertEqual(ids(inbox.pause_items(False, URL, policy_with(), NOW.date(), True)), ["pause:unset"])

    def test_the_id_is_valid_distinct_and_the_function_has_no_way_to_receive_the_value(self):
        self.assertTrue(inbox._ID_RE.fullmatch("pause:unknown"))
        self.assertNotIn("pause:unknown", {"pause", "pause:planned", "pause:long", "pause:resume_approval", "pause:unset"})
        parameters = inspect.signature(inbox.pause_items).parameters
        self.assertEqual(list(parameters), ["paused", "repo_url", "policy", "today", "unknown"])
        self.assertIs(parameters["unknown"].default, False)

    def test_the_snapshot_field_is_last_and_false_by_default_so_old_callers_do_not_change(self):
        fields = dataclasses.fields(inbox.Snapshot)
        self.assertEqual(fields[-1].name, "pause_unknown")
        self.assertIs(fields[-1].default, False)
        self.assertIs(snap().pause_unknown, False)


class BuildItemsTest(unittest.TestCase):
    def test_a_snapshot_with_an_unknown_pause_value_gets_the_item_once(self):
        items = inbox.build_items(snap(paused=True, pause_unknown=True))
        self.assertEqual(ids(items).count("pause:unknown"), 1)
        self.assertEqual([i.level for i in items if i.id == "pause:unknown"], ["check"])
        self.assertIn("pause", ids(items))                                                # 방향은 그대로 — 정지 항목이 그대로 있다

    def test_everything_else_in_the_build_is_unchanged(self):
        for policy in (None, policy_with(), policy_with(resume_gate_passed=True)):
            with self.subTest(declared=policy is not None):
                plain = inbox.build_items(snap(paused=True, policy=policy))
                flagged = inbox.build_items(snap(paused=True, policy=policy, pause_unknown=True))
                self.assertEqual([i for i in flagged if i.id != "pause:unknown"], plain)
                self.assertNotIn("pause:unknown", ids(plain))

    def test_a_known_or_off_pause_never_gets_it(self):
        self.assertNotIn("pause:unknown", ids(inbox.build_items(snap(paused=True))))
        self.assertNotIn("pause:unknown", ids(inbox.build_items(snap(paused=False))))
        self.assertEqual(inbox.build_items(snap(paused=False, pause_unknown=True)), inbox.build_items(snap(paused=False)))      # 꺼짐으로 읽었는데 알 수 없다는 말은 무시한다

    def test_an_object_without_the_field_is_read_as_not_unknown(self):
        """옛 호출·시험이 만든 스냅숏 비슷한 객체에도 죽지 않는다(getattr 기본값)."""
        real = snap(paused=True)
        proxy = type("OldSnapshot", (), {name: getattr(real, name) for name in (f.name for f in dataclasses.fields(inbox.Snapshot)) if name != "pause_unknown"})()
        self.assertFalse(hasattr(proxy, "pause_unknown"))
        self.assertEqual(inbox.build_items(proxy), inbox.build_items(real))

    def test_no_new_notification_and_no_new_marker_id(self):
        """check 수준이라 알림도 표식도 늘지 않는다 — 알림 개수는 예전과 같다."""
        for policy in (None, policy_with(), policy_with(resume_gate_passed=True)):
            plain = inbox.build_items(snap(paused=True, policy=policy))
            flagged = inbox.build_items(snap(paused=True, policy=policy, pause_unknown=True))
            self.assertEqual(inbox.action_ids(flagged), inbox.action_ids(plain))
            for marker in (None, (), ("pause",), ("pause", "pause:unknown"), ("pause:resume_approval",)):
                with self.subTest(declared=policy is not None, marker=marker):
                    self.assertEqual(inbox.plan_notice(flagged, marker), inbox.plan_notice(plain, marker))
                    self.assertNotIn("pause:unknown", inbox.plan_notice(flagged, marker)[1])

    def test_the_render_shows_the_title_in_the_check_section_and_never_asks_to_release(self):
        text = inbox.render(inbox.build_items(snap(paused=True, pause_unknown=True)), URL)
        self.assertIn(TITLE, text)
        self.assertIn("이 모음은 변수를 바꾸지 않습니다", text)
        plain = inbox.render(inbox.build_items(snap(paused=True)), URL)
        self.assertNotIn(TITLE, plain)


class RunTest(unittest.TestCase):
    """scripts/ops_inbox.py 의 실제 실행(가짜 GitHub): 환경 변수의 값이 켜짐·꺼짐·알 수 없음 중 무엇인지에 따라 실행 요약·이슈 본문이 어떻게 달라지는가."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.summary = self.tmp / "summary.md"
        self.out = []

    def run_with(self, value):
        workflows = ("chanceblog.yml", "blogger.yml")
        root = h.make_root(self.tmp / "repo", workflows=workflows)
        fake = h.FakeGitHub()
        fake.issues = [h.make_watchdog(9)]
        fake.runs = {name: [h.make_run(i, ago(hours=1 + i), name=f"{name} 이름")] for i, name in enumerate(workflows, start=1)}
        environ = dict(ENV, GITHUB_STEP_SUMMARY=str(self.summary))
        if value is not None:
            environ["PIPELINE_PAUSE"] = value
        code = oi.run(environ, fake, NOW, root, self.out.append, sleep=lambda seconds: None)
        summary = self.summary.read_text(encoding="utf-8") if self.summary.exists() else ""
        everything = "\n".join(self.out) + summary + json.dumps(fake.issues, ensure_ascii=False) + json.dumps(fake.log, ensure_ascii=False)
        return code, summary, fake, everything

    def test_an_unknown_value_shows_the_pause_item_and_the_unknown_item_in_the_summary_and_the_issue(self):
        for value in ("pause", "2", "enabled", "truee", "정지", "on!"):
            with self.subTest(value=value):
                self.out.clear()
                code, summary, fake, _ = self.run_with(value)
                self.assertEqual(code, 0)
                self.assertIn("자동 발행이 멈춰 있습니다", summary)                          # 방향은 그대로 — 정지로 읽는다
                self.assertIn(TITLE, summary)
                issue = [i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE][0]
                self.assertIn(TITLE, issue["body"])
                self.assertTrue(any(line.startswith("::error::") for line in self.out), self.out)    # 로그의 ::error:: 줄도 그대로 있다

    def test_known_values_never_show_the_unknown_item(self):
        for value in ("true", "1", "yes", "on", " TRUE ", "false", "0", "no", "off", "", "  ", None):
            with self.subTest(value=value):
                self.out.clear()
                _, summary, fake, everything = self.run_with(value)
                self.assertNotIn(TITLE, summary)
                self.assertNotIn("값을 알 수 없어", everything)
                self.assertFalse(any(line.startswith("::error::") for line in self.out), self.out)
        self.out.clear()
        _, summary, _, _ = self.run_with("true")
        self.assertIn("자동 발행이 멈춰 있습니다", summary)                                  # 켜짐은 예전 그대로

    def test_the_received_value_is_never_written_anywhere(self):
        canary = "CANARY_" + "PAUSE_" + "TYPO_" + "VALUE_0123456789"
        _, summary, fake, everything = self.run_with(canary)
        self.assertIn(TITLE, summary)
        self.assertNotIn(canary, everything)
        self.assertNotIn(canary.lower(), everything.lower())
        self.assertNotIn("0123456789", "\n".join(self.out) + summary)

    def test_an_unknown_value_makes_no_new_notification_compared_with_a_plain_pause(self):
        _, _, plain_fake, _ = self.run_with("true")
        plain_comments = {number: list(bodies) for number, bodies in plain_fake.comments.items()}
        self.out.clear()
        self.setUp()
        _, _, odd_fake, _ = self.run_with("pause")
        self.assertEqual({number: list(bodies) for number, bodies in odd_fake.comments.items()}, plain_comments)
        self.assertEqual(len(odd_fake.writes()), len(plain_fake.writes()))                  # 쓰기 호출 수도 같다 — 항목 하나가 더 있을 뿐 알림·코멘트는 늘지 않는다

    def test_the_script_passes_the_unknown_flag_from_the_shared_reader_and_not_by_reading_the_name(self):
        text = (_bootstrap.ROOT / "scripts" / "ops_inbox.py").read_text(encoding="utf-8")
        self.assertIn("pause_unknown=pause.is_unrecognized(environ)", text)
        self.assertIn("paused=pause.is_paused(environ)", text)
        self.assertNotIn('"PIPELINE_PAUSE"', text)                                         # 변수 이름을 직접 읽지 않는다(읽는 곳은 pipeline/pause.py 한 곳 — BP-S1-3)
        self.assertEqual(pause.state({"PIPELINE_PAUSE": "pause"}), pause.UNKNOWN)


class DocsTest(unittest.TestCase):
    def test_the_guide_and_the_register_describe_the_item(self):
        guide = (_bootstrap.ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
        for word in ("`pause:unknown`", TITLE, "알 수 없는 값", "받은 값은 싣지 않", "워치독은 일부러 조용"):
            self.assertIn(word, guide, word)
        register = (_bootstrap.ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
        self.assertIn("| **D-423** |", register)
        row = [line for line in register.splitlines() if line.startswith("| **D-423** |")][0]
        for word in ("pause:unknown", "BP2S-2", "tests/test_ops_inbox_pause_unknown.py"):
            self.assertIn(word, row, word)


if __name__ == "__main__":
    unittest.main()
