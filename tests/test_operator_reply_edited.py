"""운영자 응답 이슈가 접수 뒤에 고쳐질 때도 폰으로 알린다 — 확인 032 ①(운영자 승인, 이슈 #254), 결함 D-437.

배경: 접수 워크플로(`operator-reply.yml`)는 `issues: opened` 하나라, 소유자가 연 `[답변]` 이슈의 본문이 나중에 고쳐지면(`선택 안 함` → 승인 보기) 접수 코멘트는 '확인함(승인 아님)' 으로
남은 채 본문만 바뀌고 폰 알림도 없었다(G-S9a). 이제 `edited` 도 받아 **알림 한 통만** 보낸다 — 접수 코멘트·라벨·승인·GitHub 읽기와 쓰기는 없다.

이 시험이 지키는 것
 1. 알림의 모양: 번호와 고정 문장뿐이다(제목·본문·선택·작성자 글이 폰·로그·요약 어디에도 없다). 고친 계정이 소유자가 아니면 문장이 달라진다.
 2. 거르기: 저장소 소유자 login 과 `OWNER` 가 아닌 이슈·양식이 아닌 제목·같은 글로 다시 저장한 편집·다른 이벤트 이름은 아무것도 하지 않는다(위조 이벤트 흉내 포함).
 3. 새 길을 열지 않는다: GitHub 에 아무 요청도 가지 않고(접수 코멘트·라벨·읽기 모두 0), 승인으로 읽는 코드가 없고, 한 실행은 한 통만 보낸다.
 4. 워크플로: 트리거가 `issues: [opened, edited]` 뿐이고 나머지 모양은 그대로이며, 검증기 WF-14 가 새 모양만 허용하고 다른 종류 추가·`edited` 빼기를 잡는다.
 5. 문서: 한계 문장이 정정됐고(AI 가 읽는 네 곳과 규칙 표·가이드), 결함 행이 있다.
GitHub·텔레그램은 가짜(FakeGitHub·FakeNet)이고 실제 호출은 없다.
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import _bootstrap
import notify_helpers as nh
import operator_loop_helpers as oh
from notify_helpers import FakeNet, http_error as tg_error, leaks
from operator_loop_helpers import GH_TOKEN, OWNER, FakeGitHub, ack_env, issue_event, reply_body, task_body
from pipeline import notify
from pipeline import operator_loop as ol
from workflow_expr_helpers import Expr

try:
    import yaml
except ImportError:  # pragma: no cover - CI 에는 항상 있다
    yaml = None

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

NEEDS_YAML = unittest.skipUnless(yaml is not None, "PyYAML(requirements-dev.txt)이 필요합니다(CI 에서는 항상 실행됩니다)")


def load(name):
    """`.github/workflows/<name>` 을 읽는다(YAML 1.1 은 키 `on` 을 True 로 읽어 `on` 으로 되돌린다)."""
    data = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


OPERATOR_REPLY, AI_REQUEST = vr.OPERATOR_REPLY_WORKFLOW, vr.AI_REQUEST_WORKFLOW
RLO, PDF = chr(0x202E), chr(0x202C)
LOOKALIKE = OWNER.replace("s", chr(0x17F), 1)     # 소유자 이름의 첫 s 를 닮은 글자(U+017F)로 바꾼 이름 — 소문자 접기(casefold)로 비교하면 소유자와 같아지므로 소유자로 통과하면 안 된다
HOSTILE = ["$(touch /tmp/pwned)", "::set-output name=x::1", "::error::가짜 오류", "##[warning]가짜", "@everyone", "<!-- ack:v1 -->", "<script>alert(1)</script>",
           "`rm -rf /`", "javascript:alert(1)", RLO + "반전" + PDF, "[클릭](" + "x" + ")"]

# 폰 글의 고정 문장(네 가지) — 글자 그대로 못박는다
WHO_OWNER = "소유자 계정이 고쳤습니다."
WHO_OTHER = "소유자 계정이 아닌 계정이 고쳤거나 알 수 없습니다. 본인이 고친 것이 아니면 알려 주세요."
TAIL_ANSWER = "접수 때의 대상번호·선택과 달라졌을 수 있어 AI 가 다시 대조하며, 달라졌으면 승인으로 읽지 않습니다."
TAIL_TASK = "접수 때의 내용과 달라졌을 수 있어 AI 가 다시 읽습니다. 이 양식은 승인이 아닙니다."


def phone(number, kind, by_owner):
    head = f"{notify.WARN_MARK} 답변이 고쳐졌습니다(이슈 #{number})" if kind == "answer" else f"{notify.WARN_MARK} 새 일 요청이 고쳐졌습니다(이슈 #{number})"
    return f"{head} — {WHO_OWNER if by_owner else WHO_OTHER} {TAIL_ANSWER if kind == 'answer' else TAIL_TASK}"


def edited_event(number=12, title="[답변] ", body=None, login=OWNER, association="OWNER", sender=OWNER, changes="before", labels=(), sender_raw=None):
    """GitHub 가 `issues: edited` 로 주는 이벤트 모양: action·issue(고친 뒤의 글)·changes(바뀐 칸의 **이전** 글 `from`)·sender(고친 계정).
    changes 기본값 `before` 는 본문이 달라진 편집이고, 사전을 주면 그대로 쓰고, None 이면 칸 자체를 뺀다. sender_raw 를 주면 sender 칸을 그 값 그대로 쓴다."""
    event = issue_event(number=number, title=title, body=body, login=login, association=association, labels=labels, action="edited")
    if changes == "before":
        changes = {"body": {"from": "고치기 전의 본문"}}
    if changes is not None:
        event["changes"] = changes
    if sender_raw is not None:
        event["sender"] = sender_raw
    elif sender is not None:
        event["sender"] = {"login": sender, "type": "User"}
    return event


class EditedAlertCliTest(unittest.TestCase):
    """`python -m pipeline.operator_loop ack` 를 `edited` 이벤트로 돌린다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo_root = self.tmp / "repo"
        (self.repo_root / ol.REQUEST_DIR).mkdir(parents=True)
        self.summary = self.tmp / "summary.md"

    def edit(self, event=None, github=None, net=None, **env):
        event = event if event is not None else edited_event()
        environ = ack_env(self.tmp, event, GITHUB_STEP_SUMMARY=str(self.summary), **env)
        return oh.run_cli("ack", environ=environ, net=net, root=self.repo_root, github=github)

    def assert_nothing_done(self, result, expected_line):
        code, lines, net, github = result
        self.assertEqual(code, 0)
        self.assertEqual(github.requests, [], "GitHub 에 아무것도 쓰거나 읽지 않는다")
        self.assertEqual(net.calls, 0)
        self.assertEqual(lines, [expected_line])
        self.assertFalse(self.summary.exists())

    # ---- 정상: 한 통의 고정 알림, 다른 일은 없다 ----
    def test_the_owner_editing_an_answer_gets_one_fixed_message_and_nothing_else_happens(self):
        code, lines, net, github = self.edit(edited_event(body=reply_body(choice="B", memo="비밀 메모 입니다")))
        self.assertEqual(code, 0)
        self.assertEqual(github.requests, [])                          # 접수 코멘트·라벨·읽기 어느 것도 없다
        self.assertEqual(net.calls, 1)
        body = net.bodies()[0]
        self.assertEqual(body["text"], phone(12, "answer", True))
        self.assertEqual(body["text"], notify.format_issue_edited(12, "answer", True))
        self.assertNotIn("parse_mode", body)
        self.assertEqual(body["reply_markup"]["inline_keyboard"], [[{"text": "이슈 열기", "url": f"{notify.REPO_URL}/issues/12"}]])
        self.assertEqual(lines, ["운영자 응답 접수(고쳐짐): 텔레그램으로 고쳐졌다는 알림을 보냈습니다"])
        self.assertEqual(self.summary.read_text(encoding="utf-8").strip(),
                         "### 운영자 응답 접수\n\n- 이슈 #12: 고쳐졌다는 알림을 보냈습니다(접수·승인이 아니고 코멘트·라벨은 없습니다)")

    def test_a_new_task_request_that_was_edited_gets_its_own_sentence(self):
        code, lines, net, github = self.edit(edited_event(number=13, title="[요청] ", body=task_body(what="PR 을 정리해 주세요", approval=oh.TASK_SCOPE["yes"])))
        self.assertEqual((code, github.requests, net.calls), (0, [], 1))
        self.assertEqual(net.bodies()[0]["text"], phone(13, "task", True))
        self.assertIn("새 일 요청이 고쳐졌습니다(이슈 #13)", net.bodies()[0]["text"])
        self.assertIn("이 양식은 승인이 아닙니다", net.bodies()[0]["text"])

    def test_an_editor_who_is_not_the_owner_account_changes_the_sentence_never_hides_the_alert(self):
        """소유자가 쓴 이슈를 다른 계정(쓰기 권한 협업자·소유자 이름이 아닌 토큰)이 고치는 것이 이 알림이 가장 잡아야 할 경우다 — 보내지 않는 쪽이 아니라 더 분명히 알리는 쪽."""
        cases = {"다른 사람": {"sender": "someone-else"}, "봇": {"sender": "github-actions[bot]"}, "고친 계정 칸 없음": {"sender": None},
                 "로그인이 빈 글": {"sender_raw": {"login": ""}}, "로그인이 숫자": {"sender_raw": {"login": 12345}}, "sender 가 글": {"sender_raw": OWNER},
                 "sender 가 목록": {"sender_raw": [OWNER]}, "닮은 글자(U+017F)": {"sender": LOOKALIKE}, "뒤에 글이 붙은 이름": {"sender": OWNER + " "}}
        for label, kwargs in cases.items():
            with self.subTest(label):
                code, lines, net, github = self.edit(edited_event(**kwargs))
                self.assertEqual((code, github.requests, net.calls), (0, [], 1))
                self.assertEqual(net.bodies()[0]["text"], phone(12, "answer", False))

    def test_the_owner_name_in_other_letter_case_is_still_the_owner(self):
        for name in (OWNER.upper(), OWNER.capitalize(), OWNER.title()):
            with self.subTest(name=name):
                code, lines, net, github = self.edit(edited_event(sender=name))
                self.assertEqual(net.bodies()[0]["text"], phone(12, "answer", True))

    def test_an_edit_that_only_changes_the_title_is_alerted(self):
        event = edited_event(title="[답변] 새 제목", changes={"title": {"from": "[답변] 옛 제목"}})
        code, lines, net, github = self.edit(event)
        self.assertEqual((net.calls, github.requests), (1, []))

    def test_an_answer_whose_new_body_has_the_wrong_shape_is_still_alerted(self):
        code, lines, net, github = self.edit(edited_event(body="양식을 쓰지 않고 직접 쓴 글"))
        self.assertEqual((code, net.calls, github.requests), (0, 1, []))
        self.assertEqual(net.bodies()[0]["text"], phone(12, "answer", True))

    def test_odd_changes_are_alerted_because_a_missed_alert_is_worse_than_one_extra(self):
        omit = object()
        odd = (("칸 없음", omit), ("null", None), ("목록", ["body"]), ("글", "body"), ("빈 사전", {}), ("칸이 글", {"body": "이전"}), ("from 없음", {"body": {}}),
               ("from 이 숫자", {"body": {"from": 5}}), ("from 이 목록", {"body": {"from": ["a"]}}), ("모르는 칸", {"labels": {"from": []}}),
               ("본문은 같고 모르는 칸이 더", {"body": {"from": reply_body()}, "x": {"from": "y"}}))
        for label, changes in odd:
            with self.subTest(label):
                event = edited_event(changes=None)                                  # changes 칸을 뺀 이벤트
                if changes is not omit:
                    event["changes"] = changes
                code, lines, net, github = self.edit(event)
                self.assertEqual((code, net.calls, github.requests), (0, 1, []), lines)

    # ---- 같은 글로 다시 저장한 편집은 알리지 않는다 ----
    def test_saving_the_same_text_again_sends_nothing(self):
        body = reply_body(choice="B")
        same = "운영자 응답 접수(고쳐짐): 제목·본문이 그대로라 알리지 않습니다(같은 글로 다시 저장)"
        for label, changes in {"본문이 같음": {"body": {"from": body}}, "제목이 같음": {"title": {"from": "[답변] "}},
                               "둘 다 같음": {"title": {"from": "[답변] "}, "body": {"from": body}}}.items():
            with self.subTest(label):
                self.assert_nothing_done(self.edit(edited_event(body=body, changes=changes)), same)

    def test_an_empty_body_before_and_after_counts_as_the_same_text(self):
        event = edited_event(changes={"body": {"from": None}})
        event["issue"]["body"] = None
        self.assert_nothing_done(self.edit(event), "운영자 응답 접수(고쳐짐): 제목·본문이 그대로라 알리지 않습니다(같은 글로 다시 저장)")

    def test_one_changed_field_among_unchanged_ones_is_enough_to_alert(self):
        body = reply_body()
        code, lines, net, github = self.edit(edited_event(body=body, changes={"title": {"from": "[답변] 옛"}, "body": {"from": body}}))
        self.assertEqual(net.calls, 1)

    # ---- 거르기: 소유자·양식이 아니면 아무것도 하지 않는다(위조 흉내 포함) ----
    def test_an_issue_by_someone_else_gets_nothing_even_if_the_owner_is_the_editor(self):
        for login, association in (("stranger", "NONE"), ("stranger", "OWNER"), ("stranger", "CONTRIBUTOR"), ("github-actions[bot]", "NONE"), ("", "OWNER")):
            for sender in (OWNER, login or "x"):
                with self.subTest(login=login, association=association, sender=sender):
                    self.assert_nothing_done(self.edit(edited_event(login=login, association=association, sender=sender)), ol.EDIT_LOG_PREFIX + ol.EDIT_REFUSAL_LINES["not_owner"])

    def test_the_owner_login_without_the_owner_association_gets_nothing(self):
        for association in ("MEMBER", "COLLABORATOR", "NONE", "owner", "", None):
            with self.subTest(association=association):
                self.assert_nothing_done(self.edit(edited_event(association=association)), ol.EDIT_LOG_PREFIX + ol.EDIT_REFUSAL_LINES["not_owner_association"])

    def test_an_owner_issue_that_is_not_one_of_the_forms_gets_nothing(self):
        for title in ("[페이지 수정] 소개", "[이미지 변경] x", "그냥 질문", "", "[운영] 확인 필요 모음", "x [답변] "):
            with self.subTest(title=title):
                self.assert_nothing_done(self.edit(edited_event(title=title)), ol.EDIT_LOG_PREFIX + ol.EDIT_REFUSAL_LINES["not_form"])

    def test_without_a_known_owner_nothing_is_done(self):
        environ = ack_env(self.tmp, edited_event(), owner="")
        del environ["GITHUB_REPOSITORY_OWNER"]
        environ["GITHUB_REPOSITORY"] = ""
        self.assert_nothing_done(oh.run_cli("ack", environ=environ, root=self.repo_root), ol.EDIT_LOG_PREFIX + ol.EDIT_REFUSAL_LINES["no_owner"])

    def test_a_bad_issue_number_stops_after_the_owner_check(self):
        for number in (None, 0, -1, True, "12", 1.5):
            with self.subTest(number=number):
                event = edited_event()
                event["issue"]["number"] = number
                self.assert_nothing_done(self.edit(event), ol.EDIT_LOG_PREFIX + "이슈 번호를 읽지 못해 아무것도 하지 않습니다")

    def test_a_forged_event_name_never_alerts_even_with_an_edited_action_and_an_owner_issue(self):
        """`issue_comment`·`pull_request_target` 등 다른 이벤트가 `edited` 모양을 흉내 내도 이 접수는 이벤트 이름이 `issues` 일 때만 본다."""
        line = "운영자 응답 접수: 이 실행은 새로 열린 이슈 이벤트가 아니어서 아무것도 하지 않습니다"
        for name in ("issue_comment", "pull_request_target", "pull_request", "push", "workflow_dispatch", "schedule", ""):
            with self.subTest(name=name):
                self.assert_nothing_done(self.edit(edited_event(), event_name=name), line)

    def test_other_issue_actions_still_do_nothing(self):
        line = "운영자 응답 접수: 이 실행은 새로 열린 이슈 이벤트가 아니어서 아무것도 하지 않습니다"
        for action in ("closed", "reopened", "labeled", "unlabeled", "deleted", "transferred", "pinned", "assigned", "milestoned", "locked", "Edited", "EDITED", " edited", ""):
            with self.subTest(action=action):
                event = edited_event()
                event["action"] = action
                self.assert_nothing_done(self.edit(event), line)

    def test_a_missing_or_broken_event_file_does_nothing(self):
        line = "운영자 응답 접수: 이 실행은 새로 열린 이슈 이벤트가 아니어서 아무것도 하지 않습니다"
        environ = ack_env(self.tmp, edited_event())
        for broken in (lambda e: e.pop("GITHUB_EVENT_PATH"), lambda e: e.update(GITHUB_EVENT_PATH=str(self.tmp / "none.json"))):
            broken(environ)
            self.assert_nothing_done(oh.run_cli("ack", environ=environ, root=self.repo_root), line)

    def test_a_malformed_event_never_crashes_the_run(self):
        for issue in (None, [], "text", {"title": "[답변] "}, {"number": 3, "title": "[답변] ", "user": "x", "author_association": "OWNER", "labels": "a"}):
            event = {"action": "edited", "issue": issue, "changes": {"body": {"from": "x"}}, "sender": {"login": OWNER}}
            code, lines, net, github = self.edit(event)
            self.assertEqual((code, net.calls, github.requests), (0, 0, []), issue)
            self.assertFalse(any("예기치 않은 오류" in line for line in lines), (issue, lines))

    # ---- 새 길을 열지 않는다 ----
    def test_a_burst_of_runs_is_one_message_per_run_and_the_run_keeps_no_state(self):
        """한 실행은 한 통만 보낸다(통 수 상한과 별개로 코드가 한 번만 부른다). 코드는 GitHub 에 아무것도 쓰지 않아 실행 사이에 남는 상태가 없으므로 같은 이벤트를 두 번 돌리면 두 통이다 —
        폭주는 워크플로의 동시 실행 그룹(이슈마다 한 줄, 대기 중인 실행은 하나로 합쳐짐)이 막는다(문서 시험 참고)."""
        github = FakeGitHub()
        for _ in range(2):
            code, lines, net, github = self.edit(github=github)
            self.assertEqual((code, net.calls, github.requests), (0, 1, []))

    def test_a_hostile_issue_never_reaches_the_phone_the_log_or_the_summary(self):
        for text in HOSTILE:
            with self.subTest(text=text):
                event = edited_event(title="[답변] " + text, body=reply_body(request_id="R-001", memo=text), changes={"body": {"from": text}, "title": {"from": text}},
                                     sender=OWNER)
                event["sender"]["name"] = text
                event["issue"]["user"]["name"] = text
                code, lines, net, github = self.edit(event)
                self.assertEqual((code, net.calls, github.requests), (0, 1, []))
                shown = net.bodies()[0]["text"] + "\n".join(lines) + self.summary.read_text(encoding="utf-8")
                self.assertEqual(net.bodies()[0]["text"], phone(12, "answer", True))
                for word in (text, "pwned", "set-output", "가짜", "everyone", "alert(1)", "rm -rf", "반전", "ack:v1"):
                    if word in text:
                        self.assertNotIn(word, shown, word)

    def test_an_edited_approval_is_never_read_as_one_and_its_choice_and_number_are_not_repeated(self):
        """승인 보기로 고쳐진 본문이 와도 알림에는 대상번호·선택이 없다 — 고친 글을 승인으로 읽는 코드가 없고 GitHub 에도 아무것도 쓰지 않는다."""
        body = "### 대상번호\n\n019\n\n### 선택\n\n②\n\n### 내용\n\n승인합니다"
        code, lines, net, github = self.edit(edited_event(body=body.replace("\n", "\r\n")))
        self.assertEqual((code, net.calls, github.requests), (0, 1, []))
        text = net.bodies()[0]["text"]
        self.assertEqual(text, phone(12, "answer", True))
        for word in ("019", "②", "승인합니다", "R-", "r019"):
            self.assertNotIn(word, text, word)
        self.assertFalse(any("019" in line or "②" in line for line in lines))
        self.assertNotIn("019", self.summary.read_text(encoding="utf-8"))

    def test_the_edited_path_needs_no_github_token_and_never_uses_it(self):
        code, lines, net, github = oh.run_cli("ack", environ=ack_env(self.tmp, edited_event(), token=""), root=self.repo_root)
        self.assertEqual((code, github.requests, net.calls), (0, [], 1))
        self.assertEqual(leaks("\n".join(lines), net.bodies()[0]["text"]), [])
        self.assertNotIn(GH_TOKEN, "\n".join(lines) + json.dumps(net.bodies(), ensure_ascii=False))

    def test_the_opened_path_is_unchanged(self):
        code, lines, net, github = self.edit(issue_event(action="opened"))
        self.assertEqual(code, 0)
        self.assertEqual([(item["method"], item["path"]) for item in github.requests], [("POST", "/labels"), ("POST", "/issues/12/labels"), ("GET", "/issues/12/comments"), ("POST", "/issues/12/comments")])
        self.assertEqual(net.bodies()[0]["text"], f"{notify.OK_MARK} 답변 접수 r001 → 승인(이슈 #12)")

    # ---- 알림이 실패하거나 꺼져 있을 때 ----
    def test_without_telegram_secrets_it_says_so_and_does_nothing_else(self):
        code, lines, net, github = oh.run_cli("ack", environ=ack_env(self.tmp, edited_event(), telegram=False), root=self.repo_root)
        self.assertEqual((code, net.calls, github.requests), (0, 0, []))
        self.assertEqual(lines, [notify.SKIP_LINE])

    def test_a_telegram_failure_is_a_warning_and_the_exit_code_is_still_zero(self):
        code, lines, net, github = self.edit(net=FakeNet(tg_error(401, "Unauthorized " + nh.TOKEN)))
        self.assertEqual((code, github.requests), (0, []))
        self.assertTrue(any("텔레그램 알림을 보내지 못했습니다" in line for line in lines), lines)
        self.assertEqual(lines[-1], ol.ACK_WARNING)
        self.assertEqual(leaks(*lines), [])
        self.assertFalse(self.summary.exists())


class IssueEditedMessageTest(unittest.TestCase):
    """`notify.format_issue_edited` — 폰 글은 번호와 고정 문장뿐이다."""

    def test_the_four_sentences_are_exactly_these(self):
        for number in (1, 12, 145, 999999999):
            for kind in ("answer", "task"):
                for by_owner in (True, False):
                    self.assertEqual(notify.format_issue_edited(number, kind, by_owner), phone(number, kind, by_owner), (number, kind, by_owner))

    def test_it_is_one_plain_line_with_the_warning_mark_and_no_markup(self):
        for kind in ("answer", "task"):
            for by_owner in (True, False):
                text = notify.format_issue_edited(7, kind, by_owner)
                self.assertEqual(len(text.splitlines()), 1)
                self.assertTrue(text.startswith(notify.WARN_MARK))
                for bad in ("`", "<", ">", "&", "::", "@", "http"):
                    self.assertNotIn(bad, text, bad)

    def test_the_answer_sentence_says_it_will_be_checked_again_and_a_changed_answer_is_not_read_as_approval(self):
        text = notify.format_issue_edited(7, "answer", True)
        for needle in ("답변이 고쳐졌습니다(이슈 #7)", "접수 때의 대상번호·선택과 달라졌을 수 있어", "AI 가 다시 대조", "달라졌으면 승인으로 읽지 않습니다"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("접수했습니다", text)

    def test_bad_values_are_refused(self):
        for kind in ("", "reply", "Answer", None, 3, "answer "):
            with self.assertRaises(ValueError, msg=repr(kind)):
                notify.format_issue_edited(5, kind, True)
        for number in (0, -1, True, "5", None, 1.5):
            with self.assertRaises(ValueError, msg=repr(number)):
                notify.format_issue_edited(number, "answer", True)

    def test_the_notifier_method_sends_one_plain_message_with_the_button_and_never_raises(self):
        notifier, net, _clock = nh.make_notifier()
        result = notifier.notify_issue_edited(12, "answer", False, buttons=[("이슈 열기", f"{notify.REPO_URL}/issues/12")])
        self.assertTrue(result.sent)
        body = net.bodies()[0]
        self.assertEqual(body["text"], phone(12, "answer", False))
        self.assertNotIn("parse_mode", body)
        self.assertEqual(body["reply_markup"]["inline_keyboard"][0][0]["text"], "이슈 열기")
        broken = notifier.notify_issue_edited(12, "nonsense", True)
        self.assertEqual((broken.sent, broken.reason), (False, notify.INTERNAL_ERROR))
        self.assertEqual(net.calls, 1)

    def test_the_module_level_wrapper_uses_the_given_notifier(self):
        notifier, net, _clock = nh.make_notifier()
        self.assertTrue(notify.notify_issue_edited(12, "task", True, notifier=notifier).sent)
        self.assertEqual(net.bodies()[0]["text"], phone(12, "task", True))


class EditChangedTest(unittest.TestCase):
    """`ol.edit_changed` — '같은 글로 다시 저장' 이라고 확실할 때만 거짓이다."""

    def test_only_a_proven_same_text_is_not_a_change(self):
        issue = {"title": "[답변] ", "body": "본문"}
        self.assertFalse(ol.edit_changed({"changes": {"body": {"from": "본문"}}}, issue))
        self.assertFalse(ol.edit_changed({"changes": {"title": {"from": "[답변] "}, "body": {"from": "본문"}}}, issue))
        self.assertTrue(ol.edit_changed({"changes": {"body": {"from": "다른 본문"}}}, issue))
        self.assertTrue(ol.edit_changed({"changes": {"title": {"from": "다른"}, "body": {"from": "본문"}}}, issue))
        for odd in (None, {}, [], "x", {"body": 1}, {"body": {"from": 1}}, {"body": {}}, {"title": {"from": "[답변] "}, "other": {"from": ""}}):
            self.assertTrue(ol.edit_changed({"changes": odd}, issue), odd)
        self.assertTrue(ol.edit_changed({}, issue))

    def test_line_ends_count_as_text(self):
        """줄 끝(CRLF·LF)·앞뒤 공백·끝 줄바꿈만 달라져도 고쳐진 것(참)이다 — 글자 그대로 비교한다. 비교 전에 공백을 다듬으면(strip) 이런 편집을 같은 글로 보고 알림을 놓친다(독립 검증 Q 의 권고 R1)."""
        self.assertTrue(ol.edit_changed({"changes": {"body": {"from": "a\r\nb"}}}, {"body": "a\nb"}))
        self.assertFalse(ol.edit_changed({"changes": {"body": {"from": "a\r\nb"}}}, {"body": "a\r\nb"}))
        self.assertTrue(ol.edit_changed({"changes": {"body": {"from": " 본문 "}}}, {"body": "본문"}))            # 앞뒤 공백만 다른 편집(두 방향)
        self.assertTrue(ol.edit_changed({"changes": {"body": {"from": "본문"}}}, {"body": "  본문"}))
        self.assertTrue(ol.edit_changed({"changes": {"body": {"from": "본문\n"}}}, {"body": "본문"}))            # 끝 줄바꿈만 다른 편집(두 방향)
        self.assertTrue(ol.edit_changed({"changes": {"body": {"from": "본문"}}}, {"body": "본문\r\n"}))
        self.assertTrue(ol.edit_changed({"changes": {"title": {"from": "[답변] "}}}, {"title": "[답변]"}))        # 제목도 같다

    def test_a_null_body_is_an_empty_text(self):
        self.assertFalse(ol.edit_changed({"changes": {"body": {"from": None}}}, {"body": None}))
        self.assertFalse(ol.edit_changed({"changes": {"body": {"from": ""}}}, {"body": None}))
        self.assertTrue(ol.edit_changed({"changes": {"body": {"from": "x"}}}, {"body": None}))
        self.assertTrue(ol.edit_changed({"changes": {"body": {"from": None}}}, {"body": "x"}))

    def test_the_editor_is_the_owner_only_for_an_exact_account_name(self):
        for sender, expected in (({"login": OWNER}, True), ({"login": OWNER.upper()}, True), ({"login": LOOKALIKE}, False), ({"login": OWNER + "x"}, False), ({"login": ""}, False),
                                 ({"login": None}, False), ({"login": 5}, False), ({}, False), (None, False), (OWNER, False), ([OWNER], False)):
            self.assertIs(ol.editor_is_owner({"sender": sender}, OWNER), expected, sender)
        self.assertFalse(ol.editor_is_owner({}, OWNER))


# ----------------------------------------------------------------------------
# 워크플로 모양과 검증기 WF-14
# ----------------------------------------------------------------------------
JOB_IF = "github.event.issue.user.login == github.repository_owner && github.event.issue.author_association == 'OWNER'"


def issue_context(login=OWNER, association="OWNER", action="edited", sender=OWNER, owner=OWNER):
    return {"github": {"event_name": "issues", "repository_owner": owner,
                       "event": {"action": action, "sender": {"login": sender}, "issue": {"user": {"login": login}, "author_association": association, "title": "[답변] "}}}}


@NEEDS_YAML
class EditedWorkflowTest(unittest.TestCase):
    def test_the_trigger_is_issues_opened_and_edited_and_nothing_else(self):
        on = load("operator-reply.yml")["on"]
        self.assertEqual(on, {"issues": {"types": ["opened", "edited"]}})
        for event in ("issue_comment", "pull_request", "pull_request_target", "workflow_run", "push", "workflow_dispatch", "schedule", "repository_dispatch"):
            self.assertNotIn(event, on)

    def test_everything_but_the_trigger_is_the_approved_shape(self):
        data = load("operator-reply.yml")
        self.assertEqual(data["permissions"], {"contents": "read", "issues": "write"})
        self.assertEqual(data["concurrency"], {"group": "operator-reply-${{ github.event.issue.number }}", "cancel-in-progress": False})
        job = data["jobs"]["ack"]
        self.assertEqual(" ".join(job["if"].split()), JOB_IF)
        self.assertEqual((job["runs-on"], job["timeout-minutes"]), ("ubuntu-latest", 5))
        self.assertEqual([step.get("uses") or step.get("run") for step in job["steps"]], ["actions/checkout@v6", "actions/setup-python@v6", "python -m pipeline.operator_loop ack"])
        self.assertEqual(job["steps"][0]["with"], {"persist-credentials": False})
        self.assertEqual(set(job["steps"][2]["env"]), {"GITHUB_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"})

    def test_the_job_if_gates_an_edited_event_on_the_issue_author_like_an_opened_one(self):
        """`edited` 이벤트의 `issue.user` 는 이슈를 쓴 사람이다(고친 사람은 `sender`) — 낯선 사람의 이슈는 누가 고쳐도 job 이 건너뛰어지고, 소유자가 쓴 이슈는 누가 고쳐도 job 이 돌아 코드가 고친 계정을 가른다."""
        condition = " ".join(load("operator-reply.yml")["jobs"]["ack"]["if"].split())
        cases = ((OWNER, "OWNER", True), ("stranger", "NONE", False), ("stranger", "OWNER", False), (OWNER, "MEMBER", False), (OWNER, "COLLABORATOR", False),
                 ("github-actions[bot]", "NONE", False), ("", "OWNER", False))
        for login, association, expected in cases:
            for action in ("opened", "edited"):
                for sender in (OWNER, "someone-else"):
                    with self.subTest(login=login, association=association, action=action, sender=sender):
                        ctx = issue_context(login=login, association=association, action=action, sender=sender)
                        self.assertEqual(bool(Expr(condition, ctx).parse()), expected)        # 같은 식이 두 이벤트·두 고친 계정에서 같은 답이다(식은 sender·action 을 읽지 않는다)
        for word in ("sender", "actor", "action", "changes"):
            self.assertNotIn(word, condition)

    def test_the_header_comment_states_the_edited_rule_the_burst_limit_and_what_it_never_does(self):
        text = (ROOT / ".github" / "workflows" / "operator-reply.yml").read_text(encoding="utf-8")
        header = text.split("\non:")[0]
        for needle in ("edited", "고쳐지면", "알림 한 통만", "승인으로 읽지 않는다", "코멘트·라벨·GitHub 읽기·쓰기가 전혀 없다", "대기 중인 실행은 하나로", "한 실행은 한 통만", "D-437", "확인 032"):
            self.assertIn(needle, header, needle)


def reply_files(mutate=None):
    """진짜 두 워크플로의 글. 접수 워크플로는 **새 승인 모양**(`types: [opened, edited]`)으로 맞춰 쓴다 — 구현 전의 파일이어도 같은 모양 위에서 변이를 만들고 검증기를 시험하게."""
    texts = {rel: (ROOT / rel).read_text(encoding="utf-8") for rel in (AI_REQUEST, OPERATOR_REPLY)}
    texts[OPERATOR_REPLY] = texts[OPERATOR_REPLY].replace("types: [opened]\n", "types: [opened, edited]\n")
    assert texts[OPERATOR_REPLY].count("types: [opened, edited]\n") == 1
    if mutate:
        mutate(texts)
    return texts


@NEEDS_YAML
class EditedRuleTest(unittest.TestCase):
    def errors(self, mutate=None):
        with tempfile.TemporaryDirectory() as tmp:
            texts = reply_files(mutate)
            for rel, text in texts.items():
                path = Path(tmp) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
            return vr.check_operator_workflows(Path(tmp), sorted(texts))

    def swap(self, old, new):
        def mutate(texts):
            self.assertEqual(texts[OPERATOR_REPLY].count(old), 1, old)
            texts[OPERATOR_REPLY] = texts[OPERATOR_REPLY].replace(old, new)
        return mutate

    def test_the_new_approved_trigger_shape_passes_the_rule(self):
        self.assertEqual([f.line() for f in self.errors()], [])

    def test_the_real_files_pass_the_rule(self):
        self.assertEqual(vr.check_operator_workflows(ROOT, [AI_REQUEST, OPERATOR_REPLY]), [])

    def test_only_opened_and_edited_in_that_order_is_the_allowed_trigger(self):
        trigger = "types: [opened, edited]"
        wrong = {"edited 를 뺌": "types: [opened]", "opened 를 뺌": "types: [edited]", "순서를 바꿈": "types: [edited, opened]", "다시 열림 추가": "types: [opened, edited, reopened]",
                 "삭제 추가": "types: [opened, edited, deleted]", "라벨 추가": "types: [opened, edited, labeled]", "닫힘 추가": "types: [opened, edited, closed]",
                 "옮김 추가": "types: [opened, edited, transferred]", "담당자 추가": "types: [opened, edited, assigned]", "edited 두 번": "types: [opened, edited, edited]",
                 "글 하나": "types: edited", "종류 칸 없음": "types: []"}
        for label, new in wrong.items():
            with self.subTest(label):
                found = self.errors(self.swap(trigger, new))
                self.assertTrue(found, f"WF-14 가 잡지 못했다: {label}")
                self.assertTrue(all(f.check == "WF-14" and f.level == "ERROR" and f.path == OPERATOR_REPLY for f in found), [f.line() for f in found])
                self.assertIn("[opened, edited]", found[0].message)

    def test_the_trigger_line_can_not_be_dropped_either(self):
        found = self.errors(self.swap("  issues:\n    types: [opened, edited]\n", "  issues:\n"))
        self.assertTrue(found and all(f.check == "WF-14" for f in found))

    def test_other_events_next_to_the_new_trigger_are_still_errors(self):
        extras = {"issue_comment": "  issue_comment:\n    types: [created, edited]\n", "pull_request_target": "  pull_request_target:\n    types: [edited]\n",
                  "workflow_run": "  workflow_run:\n    workflows: ['x']\n", "push": "  push:\n    branches: [main]\n", "workflow_dispatch": "  workflow_dispatch:\n"}
        for label, block in extras.items():
            with self.subTest(label):
                found = self.errors(self.swap("permissions:\n  contents: read\n  issues: write\n", block + "\npermissions:\n  contents: read\n  issues: write\n"))
                self.assertTrue(found, label)
                self.assertTrue(all(f.check == "WF-14" for f in found))

    def test_nothing_else_the_rule_pins_was_loosened(self):
        """새 트리거를 허용하면서 소유자 조건·권한·단계·env·그룹 규칙은 그대로다."""
        wrong = {"소유자 조건 뺌": (" && github.event.issue.author_association == 'OWNER'", ""), "조건에 편집자 추가": ("== 'OWNER'", "== 'OWNER' || github.event.sender.login == github.repository_owner"),
                 "쓰기 권한 추가": ("  issues: write\n\nconcurrency", "  issues: write\n  pull-requests: write\n\nconcurrency"), "취소함": ("cancel-in-progress: false", "cancel-in-progress: true"),
                 "단계 추가": ("        run: python -m pipeline.operator_loop ack\n", "        run: python -m pipeline.operator_loop ack\n\n      - run: echo hi\n"),
                 "run 에 표현식": ("python -m pipeline.operator_loop ack", "python -m pipeline.operator_loop ack ${{ github.event.changes.body.from }}")}
        for label, (old, new) in wrong.items():
            with self.subTest(label):
                found = self.errors(self.swap(old, new))
                self.assertTrue(found, f"WF-14 가 잡지 못했다: {label}")

    def test_the_other_workflow_rules_do_not_flag_the_real_file(self):
        findings = vr.check_workflows(ROOT, [".github/workflows/operator-reply.yml"])
        self.assertEqual([f.line() for f in findings], [])
        self.assertEqual(vr.check_workflow_write_permissions(ROOT, [".github/workflows/operator-reply.yml"]), [])
        self.assertEqual(vr.check_telegram_secrets(ROOT, [".github/workflows/operator-reply.yml"]), [])


# ----------------------------------------------------------------------------
# 문서: 한계 문장 정정과 결함 행
# ----------------------------------------------------------------------------
def doc(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def row(text, start):
    found = [line for line in text.splitlines() if line.startswith(start)]
    assert len(found) == 1, (start, len(found))
    return found[0]


class EditedDocsTest(unittest.TestCase):
    NEW = ("고쳐졌습니다", "확인 032", "D-437")

    def test_the_security_row_no_longer_says_the_trigger_is_pinned_to_opened_and_states_the_new_alert(self):
        security = doc("docs/SECURITY_GUARDRAILS.md")
        g = row(security, "| G-S9a |")
        for stale in ("트리거를 `opened` 하나로 못박고 있어", "(제안만)", "운영자 승인과 함께 고쳐야 한다"):
            self.assertNotIn(stale, g, stale)
        for needle in ("`edited`", "알림 한 통", "승인으로 읽지 않", "접수 코멘트·라벨·승인·GitHub 읽기와 쓰기는 없", "소유자 계정이 아닌 계정", "같은 글로 다시 저장", "동시 실행 그룹", "한 실행은 한 통",
                       *self.NEW):
            self.assertIn(needle, g, needle)
        self.assertIn("`issues: opened·edited` 둘", row(security, "| WF-14 |"))
        self.assertNotIn("`issues: opened` 하나", row(security, "| WF-14 |"))

    def test_the_places_the_ai_reads_say_the_new_alert_and_keep_the_comparison_rule(self):
        for rel, start in (("AGENTS.md", "**승인 채널 보충**"), ("docs/AGENT_RUNBOOK.md", "7. **열린 뒤에 고쳐진 이슈**"), ("인수인계/요청함/README.md", "7. **열린 뒤에 고쳐진 이슈**")):
            line = row(doc(rel), start)
            for needle in ("고쳐졌습니다", "알림 한 통", "접수 코멘트(봇)가 되풀이한 대상번호·선택과 지금 본문을 읽은 값이 같을 때만", "D-437"):
                self.assertIn(needle, line, (rel, needle))
            for stale in ("새 접수도 폰 알림도 없", "새 접수·폰 알림이 없다", "(제안만", "편집에도 폰 알림을 보내려면"):
                self.assertNotIn(stale, line, (rel, stale))

    def test_the_status_tool_comments_say_the_same(self):
        text = doc("scripts/github_status.py")
        self.assertNotIn("새 접수도 폰 알림도 없다", text)
        self.assertIn("고쳐졌다는 폰 알림", text)

    def test_the_guides_describe_the_edited_trigger(self):
        actions = doc("docs/ACTIONS_GUIDE.md")
        start = actions.index("### 6-16.")
        section = actions[start:actions.index("### 6-17.")]
        for needle in ("`opened`", "`edited`", "고쳐졌습니다", "알림 한 통", "코멘트·라벨"):
            self.assertIn(needle, section, needle)
        self.assertNotIn("이슈를 고치거나 코멘트를 달면 돌지 않습니다", section)
        architecture = doc("docs/ARCHITECTURE.md")
        self.assertIn("(operator-reply.yml, issues: opened·edited)", architecture)
        self.assertIn("`issues: [opened, edited]` 뿐", architecture)
        runbook = row(doc("docs/AGENT_RUNBOOK.md"), "| `operator-reply.yml` |")
        self.assertIn("이슈가 열릴 때", runbook)
        self.assertIn("고쳐질 때", runbook)
        self.assertIn("고쳐졌습니다", doc("인수인계/운영자_요청함_사용법.md"))               # 운영자가 읽는 안내. (.github 아래의 폰 알림 목록 문서는 승인 범위 밖이라 이 묶음이 고치지 않았다 — 보고서의 제안)
        self.assertNotIn("고쳐도 접수 확인은 다시 오지 않습니다**(처음 올린 순간에만 한 번 옵니다). 바꾸려면", doc("인수인계/운영자_요청함_사용법.md"))

    def test_the_defect_row_for_the_edited_alert_is_after_d_428_and_names_the_files_and_the_tests(self):
        register = doc("docs/DEFECT_REGISTER.md")
        ids = re.findall(r"^\| \*\*(D-\d+)\*\* \|", register, re.M)
        self.assertIn("D-437", ids)
        self.assertGreater(register.index("| **D-437** |"), register.index("| **D-428** |"))
        line = row(register, "| **D-437** |")
        for needle in ("`edited`", "operator-reply.yml", "확인 032", "한 통", "WF-14", "tests/test_operator_reply_edited.py", "해결"):
            self.assertIn(needle, line, needle)
        for needle in ("이론상의 경쟁", "밀려 취소될 수 있다", "안전 쪽 실패", "후속 T3"):                    # 이벤트 도착 순서가 뒤바뀌는 경쟁의 한계(독립 검증 S 의 권고 R2)
            self.assertIn(needle, line, needle)
        self.assertLess(line.index("이론상의 경쟁"), line.index("**열림**"))                                  # 한계 문장 안에 있다(열림 앞)
        checklist = register.split("## 운영 중 확인할 것", 1)[1]                                           # 관측 체크리스트의 새 행(독립 검증 S 의 권고 R2) — 맨 끝 자리는 다른 갈래 행이 이어 붙을 수 있어 따지지 않는다
        quick = row(checklist, "| 접수 워크플로 `edited` 알림(D-437) 병합 뒤 짧은 간격")
        self.assertEqual(quick.count("|"), 4, "시점·확인·정상 세 칸")
        for needle in ("짧은 간격(몇 초)", "`opened` 접수 실행", "취소", "접수 코멘트", "실행 목록", "한 번도 못 본 가정", "후속 T3"):
            self.assertIn(needle, quick, needle)


if __name__ == "__main__":
    unittest.main()
