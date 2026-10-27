"""텔레그램 알림이 붙는 곳의 시험: Blogger 러너(pipeline/run.py)·확인 필요 모음(scripts/ops_inbox.py)·워크플로 파일 구조·문서와 코드의 일치.

핵심은 '알림은 보조다': 시크릿이 없으면 아무 일도 하지 않고(출력도 그대로), 알림이 실패하거나 예외가 나도 게시 결과·이력·점검 이슈·종료 코드는 바뀌지 않으며,
연습 실행과 게시 실패에서는 알리지 않고, 토큰·채팅 ID 가 어떤 출력에도 나오지 않는다. 네트워크는 쓰지 않는다(urllib.request.urlopen 자리에 가짜를 끼운다).
"""
import copy
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import yaml

import _bootstrap
import notify_helpers as nh
import ops_inbox_helpers as h          # scripts/ 를 import 경로에 올린다(아래 ops_inbox·validate_repo)
import ops_inbox as oi  # noqa: E402
from notify_helpers import CHAT, ENV, TOKEN, FakeNet, http_error, leaks
from pipeline import inbox, notify
from pipeline.publishers.base import PublishResult
from test_run import BLOG_URL, FULL_ENV, FakePublisher, RunBase
from test_workflow_names import context, load, render

ROOT = _bootstrap.ROOT
WORKFLOWS = ROOT / ".github" / "workflows"
sys.path.insert(0, str(ROOT / "scripts"))


def patched_network(net):
    """urllib.request.urlopen 과 time.sleep 을 가짜로 바꾸는 컨텍스트(실제 네트워크·실제 대기 없음)."""
    stack = mock.patch("urllib.request.urlopen", net)
    sleeper = mock.patch("time.sleep", lambda seconds: None)

    class Both:
        def __enter__(self):
            stack.__enter__()
            sleeper.__enter__()
            return net

        def __exit__(self, *exc):
            sleeper.__exit__(*exc)
            return stack.__exit__(*exc)
    return Both()


# ----------------------------------------------------------------------------
# Blogger 러너
# ----------------------------------------------------------------------------
class BloggerRunnerAlertTest(RunBase):
    ENV_ON = dict(FULL_ENV, **ENV)

    def setUp(self):
        super().setUp()
        notify.reset_budget()                         # 한 실행 5통 상한은 프로세스 전체가 나눠 쓴다 — 다른 시험이 쓴 몫을 비운다
        self.addCleanup(notify.reset_budget)

    def go_alert(self, net=None, env=None, publisher=None, extra=()):
        net = net if net is not None else FakeNet()
        with patched_network(net):
            code, out = self.go(env=self.ENV_ON if env is None else env, publisher=publisher if publisher is not None else FakePublisher(), extra=extra)
        return code, out, net

    def test_an_immediate_post_is_announced_after_it_succeeds(self):
        pub = FakePublisher(result=PublishResult(post_id="p1", url=BLOG_URL + "2026/10/x.html"))
        code, out, net = self.go_alert(publisher=pub)
        self.assertEqual(code, 0)
        self.assertEqual(net.calls, 1)
        body = net.bodies()[0]
        self.assertTrue(body["text"].startswith(f"{notify.OK_MARK} <b>게시됨</b> — Blogger: "))
        self.assertEqual(body["reply_markup"]["inline_keyboard"][0][0], {"text": "글 보기", "url": BLOG_URL + "2026/10/x.html"})
        self.assertIn("[참고] 텔레그램 알림: 보냈습니다", out)
        self.assertEqual(self.history()[-1]["status"], "posted")

    def test_a_draft_upload_is_announced_as_waiting_for_publishing(self):
        pub = FakePublisher()
        code, out, net = self.go_alert(publisher=pub, extra=("--publish", "draft"))
        self.assertEqual((code, net.calls), (0, 1))
        self.assertTrue(pub.published[0]["draft"])
        text = net.bodies()[0]["text"]
        self.assertTrue(text.startswith(f"{notify.MEMO_MARK} <b>발행 대기</b> — Blogger: "))
        self.assertIn("초안함에 올라왔습니다 — Blogger 대시보드 → 초안에서 확인하고 게시하세요", text)
        self.assertEqual(self.history()[-1]["status"], "draft_uploaded")

    def test_the_title_in_the_message_is_the_generated_title(self):
        code, out, net = self.go_alert()
        title = self.history()[-1]["title"]
        self.assertIn(title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), net.bodies()[0]["text"])

    def test_without_secrets_nothing_is_sent_and_the_output_has_no_trace(self):
        with patched_network(FakeNet()) as net:
            code, out = self.go(env=FULL_ENV, publisher=FakePublisher())
        self.assertEqual((code, net.calls), (0, 0))
        self.assertNotIn("텔레그램", out)

    def test_with_only_half_of_the_secrets_nothing_is_sent(self):
        for env in (dict(FULL_ENV, TELEGRAM_BOT_TOKEN=TOKEN), dict(FULL_ENV, TELEGRAM_CHAT_ID=CHAT), dict(FULL_ENV, TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID=CHAT)):
            with patched_network(FakeNet()) as net:
                code, out = self.go(env=env, publisher=FakePublisher())
            self.assertEqual((code, net.calls), (0, 0))
            self.assertNotIn("텔레그램", out)

    def test_a_practice_run_never_sends(self):
        pub = FakePublisher()
        code, out, net = self.go_alert(publisher=pub, extra=("--dry-run",))
        self.assertEqual((code, net.calls, pub.published), (0, 0, []))
        self.assertNotIn("텔레그램", out)

    def test_a_failed_publish_never_reaches_the_alert_function(self):
        """바깥 조건(러너가 성공했을 때만 부름)을 따로 고정한다 — 알림 함수 쪽에도 같은 걸러내기가 있어 결과만 보면 둘을 가를 수 없다."""
        from pipeline.publishers.base import PublishError
        for kwargs in ({"publisher": FakePublisher(fail=PublishError("boom", code="api_error"))}, {"extra": ("--dry-run",)}, {"extra": ("--publish", "off")}):
            with self.subTest(case=sorted(kwargs)):
                with mock.patch.object(notify.Notifier, "notify_blogger_result", autospec=True) as spy:
                    code, out, net = self.go_alert(**kwargs)
                self.assertEqual((spy.call_count, net.calls), (0, 0))

    def test_a_successful_publish_calls_the_alert_function_once_with_the_result(self):
        with mock.patch.object(notify.Notifier, "notify_blogger_result", autospec=True, return_value=notify.Result(True, False, None, "not_applicable", "")) as spy:
            code, out, net = self.go_alert(extra=("--publish", "draft"))
        self.assertEqual(spy.call_count, 1)
        args, kwargs = spy.call_args
        self.assertEqual(args[1], "draft_uploaded")
        self.assertEqual(kwargs["blog_label"], "Blogger")
        self.assertEqual(kwargs["extra_prefixes"], (BLOG_URL,))
        self.assertEqual(args[2], self.history()[-1]["title"])

    def test_without_secrets_the_alert_function_is_not_even_entered(self):
        with patched_network(FakeNet()) as net, mock.patch.object(notify.Notifier, "notify_blogger_result", side_effect=AssertionError("부르면 안 된다")) as spy:
            code, out = self.go(env=FULL_ENV, publisher=FakePublisher())
        self.assertEqual((code, spy.call_count, net.calls), (0, 0, 0))
        self.assertNotIn("텔레그램", out)

    def test_a_failed_publish_does_not_send(self):
        from pipeline.publishers.base import PublishError
        code, out, net = self.go_alert(publisher=FakePublisher(fail=PublishError("boom", code="api_error")))
        self.assertEqual((code, net.calls), (1, 0))

    def test_a_failed_auth_check_does_not_send(self):
        from pipeline.publishers.base import PublishError
        code, out, net = self.go_alert(publisher=FakePublisher(check=PublishError("expired", code="auth_expired")))
        self.assertEqual((code, net.calls), (1, 0))

    def test_saving_to_the_repository_only_does_not_send(self):
        code, out, net = self.go_alert(extra=("--publish", "off"))
        self.assertEqual((code, net.calls), (0, 0))
        self.assertEqual(self.history()[-1]["status"], "draft")

    def test_a_telegram_failure_changes_nothing_but_adds_a_note_and_a_warning(self):
        baseline_code, baseline_out = self.go(env=FULL_ENV, publisher=FakePublisher())
        baseline_history = copy.deepcopy(self.history())
        baseline_drafts = [p.read_text(encoding="utf-8") for p in self.drafts()]
        for p in self.drafts():
            p.unlink()
        (self.root / "blogger_history.json").unlink()
        for outcome in (http_error(401, f"Unauthorized {TOKEN}"), http_error(403, "Forbidden"), http_error(400, "Bad Request: chat not found"),
                        urllib.error.URLError(nh.SEND_URL), RuntimeError(nh.SEND_URL)):
            with self.subTest(outcome=type(outcome).__name__):
                for p in self.drafts():
                    p.unlink()
                history_file = self.root / "blogger_history.json"
                if history_file.exists():
                    history_file.unlink()
                code, out, net = self.go_alert(net=FakeNet(outcome))
                self.assertEqual(code, baseline_code)
                self.assertEqual(self.history(), baseline_history)
                self.assertEqual([p.read_text(encoding="utf-8") for p in self.drafts()], baseline_drafts)
                self.assertIn("[참고] 텔레그램 알림을 보내지 못했습니다", out)
                self.assertIn(notify.WARNING_LINE, out)
                self.assertEqual(leaks(out, json.dumps(self.history(), ensure_ascii=False)), [])

    def test_an_exception_inside_the_alert_code_cannot_change_the_result(self):
        baseline_code, baseline_out = self.go(env=FULL_ENV, publisher=FakePublisher())
        baseline_history = copy.deepcopy(self.history())
        (self.root / "blogger_history.json").unlink()
        for p in self.drafts():
            p.unlink()
        with patched_network(FakeNet()), mock.patch.object(notify.Notifier, "notify_blogger_result", side_effect=RuntimeError(nh.SEND_URL)):
            code, out = self.go(env=self.ENV_ON, publisher=FakePublisher())
        self.assertEqual(code, baseline_code)
        self.assertEqual(self.history(), baseline_history)
        self.assertIn("[참고] 텔레그램 알림 중 예기치 않은 오류(RuntimeError) — 게시 결과에는 영향이 없습니다", out)
        self.assertEqual(leaks(out), [])

    def test_a_broken_notifier_constructor_cannot_change_the_result(self):
        with patched_network(FakeNet()), mock.patch.object(notify, "Notifier", side_effect=RuntimeError(nh.SEND_URL)):
            code, out = self.go(env=self.ENV_ON, publisher=FakePublisher())
        self.assertEqual(code, 0)
        self.assertIn("RuntimeError", out)
        self.assertEqual(leaks(out), [])

    def test_the_run_summary_is_the_same_with_and_without_the_alert(self):
        summaries = []
        for env in (FULL_ENV, self.ENV_ON):
            for p in self.drafts():
                p.unlink()
            history_file = self.root / "blogger_history.json"
            if history_file.exists():
                history_file.unlink()
            summary = self.root / "summary.md"
            if summary.exists():
                summary.unlink()
            with patched_network(FakeNet()):
                self.go(env=dict(env, GITHUB_STEP_SUMMARY=str(summary)), publisher=FakePublisher())
            summaries.append(summary.read_text(encoding="utf-8"))
        self.assertEqual(summaries[0], summaries[1])
        self.assertEqual(leaks(summaries[1]), [])

    def test_the_blogger_message_uses_the_registry_channel_label(self):
        code, out, net = self.go_alert(extra=("--publish", "draft"))
        self.assertIn("Blogger: ", net.bodies()[0]["text"])

    def relabel_the_channel(self, label):
        """레지스트리의 blogger_macat 채널 라벨을 바꾼다(예: 두 번째 Blogger 채널 'Blogger 한글'). 레지스트리 검증이 워크플로 name 의 [라벨] 접두사를 읽으므로 스텁도 맞춘다."""
        path = self.root / "pipeline" / "blogs.json"
        reg = json.loads(path.read_text(encoding="utf-8"))
        for blog in reg["blogs"]:
            if blog["key"] == "blogger_macat":
                blog["channel"] = {"key": "blogger_ko", "label": label}
        path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        (self.root / ".github" / "workflows" / "blogger.yml").write_text(f'name: "[{label}] 글 자동 작성(초안함 업로드)"\n', encoding="utf-8")

    def test_the_draft_message_uses_the_label_of_the_blogs_own_channel(self):
        """독립 검증 H12: 한글 Blogger 처럼 두 번째 Blogger 채널이 켜지면 알림은 그 블로그의 채널 라벨을 쓴다(상수 'Blogger' 가 아니라)."""
        self.relabel_the_channel("Blogger 한글")
        code, out, net = self.go_alert(extra=("--publish", "draft"))
        self.assertEqual((code, net.calls), (0, 1), out)
        self.assertIn("<b>발행 대기</b> — Blogger 한글: ", net.bodies()[0]["text"])

    def test_the_posted_message_uses_the_label_of_the_blogs_own_channel(self):
        self.relabel_the_channel("Blogger 한글")
        code, out, net = self.go_alert()
        self.assertEqual((code, net.calls), (0, 1), out)
        self.assertIn("<b>게시됨</b> — Blogger 한글: ", net.bodies()[0]["text"])

    def test_the_alert_is_sent_last_after_the_history_the_draft_file_and_the_summary_are_written(self):
        """독립 검증 N-1: 알림이 오래 걸리거나 그 사이 프로세스가 끊겨도, 이미 올라간 글·초안의 이력·초안 파일·실행 요약은 남아 있어야 한다 — 같은 날 재실행이
        하루 상한·중복 방지를 볼 수 있게. 알림 요청이 나가는 순간의 파일 상태를 본다."""
        summary = self.root / "summary.md"
        test = self
        for extra, status in ((("--publish", "draft"), "draft_uploaded"), ((), "posted")):
            with self.subTest(status=status):
                for leftover in self.drafts() + [self.root / "blogger_history.json", summary]:
                    if leftover.exists():
                        leftover.unlink()
                seen = []

                class Spy(FakeNet):
                    def __call__(self, request, timeout=None):
                        seen.append({"history": test.history(), "drafts": len(test.drafts()),
                                     "summary": summary.read_text(encoding="utf-8") if summary.exists() else ""})
                        return super().__call__(request, timeout=timeout)
                code, out, net = self.go_alert(net=Spy(), env=dict(self.ENV_ON, GITHUB_STEP_SUMMARY=str(summary)), extra=extra)
                self.assertEqual((code, net.calls, len(seen)), (0, 1, 1), out)
                self.assertEqual([entry["status"] for entry in seen[0]["history"]], [status])
                self.assertEqual(seen[0]["drafts"], 1)
                self.assertIn(f"- 결과: **{status}**", seen[0]["summary"])

    def test_the_run_never_prints_the_values_even_when_telegram_answers_with_them(self):
        code, out, net = self.go_alert(net=FakeNet(http_error(401, f"Unauthorized: {TOKEN} {CHAT}")))
        self.assertEqual(leaks(out), [])


# ----------------------------------------------------------------------------
# 확인 필요 모음
# ----------------------------------------------------------------------------
OPS_ENV = {"GITHUB_REPOSITORY": "shine88pc/chanceblog", "GITHUB_TOKEN": "gh" + "s_" + "Q" * 36, "GITHUB_REPOSITORY_OWNER": "shine88pc"}
ISSUE_URL = "https://github.com/shine88pc/chanceblog/issues/"


def action_items(*titles):
    return [inbox.Item(f"a:{i}", "action", title) for i, title in enumerate(titles, start=1)]


class OpsInboxAlertTest(unittest.TestCase):
    def setUp(self):
        notify.reset_budget()
        self.addCleanup(notify.reset_budget)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.out, self.summary = [], self.tmp / "summary.md"

    def world(self):
        root = h.make_root(self.tmp / "repo", workflows=("chanceblog.yml", "blogger.yml"))
        fake = h.FakeGitHub()
        fake.issues = [h.make_watchdog(9)]
        fake.pulls = [h.make_pull_raw(15, title="워치독 보강", sha="c" * 40)]
        fake.details = {15: {"mergeable": True, "mergeable_state": "clean"}}
        fake.check_runs = {"c" * 40: [h.make_check("validate")]}
        fake.runs = {name: [h.make_run(i, h.ago(hours=1 + i), name=f"{name} 이름")] for i, name in enumerate(("chanceblog.yml", "blogger.yml"), start=1)}
        return fake, root

    def run_script(self, fake, root, env, net=None):
        net = net if net is not None else FakeNet()
        environ = dict(OPS_ENV, GITHUB_STEP_SUMMARY=str(self.summary), **env)
        with patched_network(net):
            code = oi.run(environ, fake, h.NOW, root, self.out.append, sleep=lambda seconds: None)
        return code, net

    def comment_titles(self, fake, number):
        return fake.comments[number][0]

    def everything(self, fake):
        return "\n".join(self.out) + (self.summary.read_text(encoding="utf-8") if self.summary.exists() else "") + \
            json.dumps(fake.log, ensure_ascii=False) + json.dumps(fake.issues, ensure_ascii=False) + json.dumps(fake.comments, ensure_ascii=False)

    def test_without_secrets_the_output_and_the_writes_are_unchanged_and_nothing_is_sent(self):
        fake, root = self.world()
        code, net = self.run_script(fake, root, {})
        self.assertEqual((code, net.calls), (0, 0))
        self.assertNotIn("텔레그램", self.everything(fake))

    def test_a_new_action_item_is_sent_once_with_the_same_summary_as_the_comment(self):
        fake, root = self.world()
        code, net = self.run_script(fake, root, ENV)
        self.assertEqual((code, net.calls), (0, 1))
        issue = [i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE][0]
        body = net.bodies()[0]
        self.assertNotIn("parse_mode", body)
        self.assertTrue(body["text"].startswith(f"{notify.PIN_MARK} 확인 필요 모음 — 새로 해야 할 일 2건\n"))
        comment = fake.comments[issue["number"]][0]
        for line in body["text"].split("\n")[1:]:
            self.assertTrue(line.startswith("• "))
            self.assertIn(line[2:], comment)               # 코멘트에 있는 항목 제목과 같다
        self.assertEqual(body["reply_markup"]["inline_keyboard"][0], [{"text": "확인 필요 모음 열기", "url": f"{ISSUE_URL}{issue['number']}"}])
        self.assertIn("[참고] 텔레그램 알림: 보냈습니다", self.out)
        self.assertEqual(leaks(self.everything(fake)), [])

    def test_the_same_items_are_not_sent_again_on_the_next_check(self):
        fake, root = self.world()
        self.run_script(fake, root, ENV)
        code, net = self.run_script(fake, root, ENV)
        self.assertEqual((code, net.calls), (0, 0))

    def test_only_the_new_item_is_sent_when_one_more_appears(self):
        fake, root = self.world()
        self.run_script(fake, root, ENV)
        fake.pulls.append(h.make_pull_raw(16, title="새 변경", sha="d" * 40))
        fake.details[16] = {"mergeable": True, "mergeable_state": "clean"}
        fake.check_runs["d" * 40] = [h.make_check("validate")]
        code, net = self.run_script(fake, root, ENV)
        self.assertEqual((code, net.calls), (0, 1))
        text = net.bodies()[0]["text"]
        self.assertIn("새로 해야 할 일 1건", text)
        self.assertIn("PR #16", text)
        self.assertNotIn("PR #15", text)

    def test_a_practice_run_sends_nothing(self):
        fake, root = self.world()
        code, net = self.run_script(fake, root, dict(ENV, INBOX_DRY_RUN="true"))
        self.assertEqual((code, net.calls), (0, 0))
        self.assertNotIn("텔레그램", self.everything(fake))

    def test_without_a_github_token_the_run_ends_read_only_and_sends_nothing(self):
        fake, root = self.world()
        environ = dict(OPS_ENV, **ENV)
        environ.pop("GITHUB_TOKEN")
        with patched_network(FakeNet()) as net:
            code = oi.run(environ, fake, h.NOW, root, self.out.append, sleep=lambda seconds: None)
        self.assertEqual((code, net.calls), (0, 0))

    def test_a_telegram_failure_changes_neither_the_issue_the_comment_nor_the_exit_code(self):
        baseline, root0 = self.world()
        self.run_script(baseline, root0, {})
        baseline_issue = copy.deepcopy([i for i in baseline.issues if i["title"] == inbox.ISSUE_TITLE][0])
        baseline_comments = copy.deepcopy(baseline.comments)
        baseline_writes = [entry[:2] for entry in baseline.writes()]
        for outcome in (http_error(401, f"Unauthorized {TOKEN}"), http_error(403, "Forbidden"), urllib.error.URLError(nh.SEND_URL),
                        RuntimeError(nh.SEND_URL)):
            with self.subTest(outcome=type(outcome).__name__):
                self.tmp = Path(tempfile.mkdtemp(dir=str(self._tmp.name)))
                self.out.clear()
                fake, root = self.world()
                code, net = self.run_script(fake, root, ENV, net=FakeNet(outcome))
                self.assertEqual(code, 0)
                issue = [i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE][0]
                self.assertEqual(issue["body"], baseline_issue["body"])
                self.assertEqual(fake.comments, baseline_comments)
                self.assertEqual([entry[:2] for entry in fake.writes()], baseline_writes)
                self.assertTrue(any("[참고] 텔레그램 알림을 보내지 못했습니다" in line for line in self.out))
                self.assertIn(notify.WARNING_LINE, self.out)
                self.assertEqual(leaks(self.everything(fake)), [])

    def test_an_exception_in_the_alert_callback_cannot_change_the_result(self):
        fake, root = self.world()
        with patched_network(FakeNet()), mock.patch.object(notify.Notifier, "notify_ops_alert", side_effect=RuntimeError(nh.SEND_URL)):
            code = oi.run(dict(OPS_ENV, **ENV), fake, h.NOW, root, self.out.append, sleep=lambda seconds: None)
        self.assertEqual(code, 0)
        alert_lines = list(self.out)
        issue = [i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE][0]
        baseline, root0 = self.world()
        self.out.clear()
        self.run_script(baseline, root0, {})
        baseline_issue = [i for i in baseline.issues if i["title"] == inbox.ISSUE_TITLE][0]
        self.assertEqual(issue["body"], baseline_issue["body"])                       # 표식·본문은 알림 없이 돈 것과 같다
        self.assertEqual(fake.comments, baseline.comments)
        self.assertTrue(any("텔레그램 알림 중 예기치 않은 오류(RuntimeError)" in line for line in alert_lines), alert_lines)
        self.assertEqual(leaks(self.everything(fake)), [])

    def test_a_failed_comment_does_not_stop_the_phone_alert_and_the_phone_alert_does_not_hide_the_failure(self):
        """코멘트와 휴대폰 알림은 서로 영향을 주지 않는다: 코멘트가 실패해도(종료 코드 1, 다음 점검이 다시 시도) 휴대폰 알림은 간다."""
        fake, root = self.world()
        fake.fail = [(r"POST /issues/\d+/comments", oi.ApiError("HTTP 500", status=500))]
        code, net = self.run_script(fake, root, ENV)
        self.assertEqual(code, 1)
        self.assertEqual(net.calls, 1)
        self.assertIn(oi.ERROR_COMMENT_FAILED, self.out)

    def test_a_dry_issue_listing_without_new_items_sends_nothing(self):
        fake, root = self.world()
        fake.issues, fake.pulls, fake.runs, fake.details, fake.check_runs = [], [], {}, {}, {}
        code, net = self.run_script(fake, root, ENV)
        self.assertEqual((code, net.calls), (0, 0))

    def test_alert_lines_are_the_comment_lines_without_the_mention(self):
        items = action_items(*[f"항목 {i}" for i in range(12)])
        lines = inbox.alert_lines(items)
        self.assertEqual(len(lines), 9)
        self.assertEqual(lines[:8], [f"항목 {i}" for i in range(8)])
        self.assertEqual(lines[8], "… 외 4건")
        comment = inbox.comment_text("octo", items, "https://github.com/octo/blog/issues/1")
        self.assertEqual([line[2:] for line in comment.split("\n") if line.startswith("- ")], lines)
        self.assertEqual(inbox.alert_lines(action_items("@누군가 <b>x</b> & y")), [inbox.safe_text("@누군가 <b>x</b> & y")])
        self.assertEqual(inbox.alert_lines([]), [])

    def test_make_alert_returns_nothing_without_both_secrets(self):
        for env in ({}, {"TELEGRAM_BOT_TOKEN": TOKEN}, {"TELEGRAM_CHAT_ID": CHAT}):
            self.assertIsNone(oi.make_alert(env, self.out.append))
        self.assertTrue(callable(oi.make_alert(ENV, self.out.append)))

    def test_send_alert_swallows_callback_errors_and_names_only_the_class(self):
        def boom(items, url):
            raise ValueError(nh.SEND_URL)
        oi.send_alert(boom, [], "", self.out.append)
        self.assertEqual(len(self.out), 1)
        self.assertIn("ValueError", self.out[0])
        self.assertEqual(leaks(*self.out), [])
        self.out.clear()
        oi.send_alert(None, [], "", self.out.append)
        self.assertEqual(self.out, [])


# ----------------------------------------------------------------------------
# 워크플로 파일 구조
# ----------------------------------------------------------------------------
def steps_of(name, job):
    return load(name)["jobs"][job]["steps"]


TELEGRAM_ENV = {"TELEGRAM_BOT_TOKEN": "${{ secrets.TELEGRAM_BOT_TOKEN }}", "TELEGRAM_CHAT_ID": "${{ secrets.TELEGRAM_CHAT_ID }}"}


class WorkflowStructureTest(unittest.TestCase):
    def test_the_secret_names_appear_only_in_the_four_expected_workflows(self):
        found = sorted(p.name for p in WORKFLOWS.iterdir() if "TELEGRAM_" in p.read_text(encoding="utf-8"))
        self.assertEqual(found, ["blogger.yml", "chanceblog.yml", "ops-inbox.yml", "telegram-test.yml"])

    def test_every_use_of_the_secrets_passes_the_validator_rule(self):
        import validate_repo
        self.assertEqual(validate_repo.check_telegram_secrets(ROOT, validate_repo.list_files(ROOT)), [])

    def test_chanceblog_alert_step_is_last_runs_only_after_a_push_and_cannot_fail_the_run(self):
        steps = steps_of("chanceblog.yml", "build")
        step = steps[-1]
        self.assertEqual(step["name"], "텔레그램 알림(새 글)")
        self.assertEqual(step["if"], "steps.commit.outputs.pushed == 'true'")
        self.assertIs(step["continue-on-error"], True)
        self.assertEqual(step["timeout-minutes"], 2)
        self.assertEqual(step["env"], TELEGRAM_ENV)
        self.assertEqual(step["run"], "python -m pipeline.notify chance-published --commit HEAD")
        self.assertEqual(set(step), {"name", "if", "continue-on-error", "timeout-minutes", "env", "run"})
        deploy = steps[-2]
        self.assertIn("gh workflow run pages.yml", deploy["run"])             # 배포 요청 단계가 바로 앞에 그대로 있다
        self.assertEqual(deploy["if"], "steps.commit.outputs.pushed == 'true'")

    def test_the_alert_never_runs_for_a_practice_run(self):
        """연습 실행(수동 + dry_run)은 커밋 단계가 돌지 않아 pushed 출력이 없고, 알림 단계는 그 출력이 'true' 일 때만 돈다."""
        steps = steps_of("chanceblog.yml", "build")
        commit = next(s for s in steps if s.get("id") == "commit")
        for event, inputs, expected in (("workflow_dispatch", {"dry_run": True}, "false"), ("workflow_dispatch", {"dry_run": False}, "true"), ("schedule", {}, "true")):
            self.assertEqual(render(commit["if"], context(event, inputs)), expected, (event, inputs))
        self.assertIn('echo "pushed=true" >> "$GITHUB_OUTPUT"', commit["run"])
        self.assertEqual(commit["run"].count("pushed=true"), 1)                # 커밋할 변경이 없을 때는 출력이 없다

    def test_the_other_chanceblog_steps_did_not_change(self):
        names = [s.get("name") or s.get("uses") for s in steps_of("chanceblog.yml", "build")]
        self.assertEqual(names, ["actions/checkout@v4", "actions/setup-python@v5", "의존성 설치", "AI 블로그 제너레이터 실행", "변경 사항 커밋",
                                 "Pages 배포 실행 (새 커밋이 있을 때만)", "텔레그램 알림(새 글)"])
        wf = load("chanceblog.yml")
        self.assertEqual(wf["permissions"], {"contents": "write", "actions": "write"})
        self.assertEqual(wf["concurrency"], {"group": "chanceblog", "cancel-in-progress": False})
        self.assertEqual(wf["jobs"]["build"]["timeout-minutes"], 20)
        python = steps_of("chanceblog.yml", "build")[1]
        self.assertEqual(python["with"]["python-version"], "3.10")                  # 알림 모듈은 3.10 에서 돈다

    def test_the_image_replacement_workflow_has_no_alert(self):
        text = (WORKFLOWS / "chance-fix-images.yml").read_text(encoding="utf-8")
        self.assertNotIn("TELEGRAM", text)
        self.assertNotIn("pipeline.notify", text)

    def test_blogger_passes_the_two_secrets_only_to_the_runner_step(self):
        wf = load("blogger.yml")
        carriers = [(job, step.get("name")) for job, body in wf["jobs"].items() for step in body["steps"] if "TELEGRAM_BOT_TOKEN" in step.get("env", {})]
        self.assertEqual(carriers, [("generate", "생성 → 검증 → 게시/초안")])
        env = steps_of("blogger.yml", "generate")[3]["env"]
        for name, value in TELEGRAM_ENV.items():
            self.assertEqual(env[name], value)
        self.assertEqual(steps_of("blogger.yml", "generate")[3]["run"], 'python -m pipeline.run --blog "$BLOG_KEY"')
        self.assertEqual(wf["permissions"], {"contents": "read"})
        self.assertNotIn("TELEGRAM", json.dumps(wf["jobs"]["plan"]))

    def test_ops_inbox_passes_the_two_secrets_to_the_script_step_only(self):
        wf = load("ops-inbox.yml")
        step = wf["jobs"]["inbox"]["steps"][-1]
        self.assertEqual(step["run"], "python scripts/ops_inbox.py")
        for name, value in TELEGRAM_ENV.items():
            self.assertEqual(step["env"][name], value)
        self.assertEqual(wf["permissions"], {"contents": "read", "actions": "read", "checks": "read", "pull-requests": "read", "issues": "write"})
        self.assertEqual(sum("TELEGRAM_BOT_TOKEN" in json.dumps(s) for s in wf["jobs"]["inbox"]["steps"]), 1)

    def test_the_test_workflow(self):
        wf = load("telegram-test.yml")
        self.assertEqual(wf["name"], "[공통] 텔레그램 알림 시험")
        self.assertEqual(list(wf["on"]), ["workflow_dispatch"])
        self.assertNotIn("inputs", wf["on"]["workflow_dispatch"] or {})
        self.assertEqual(wf["permissions"], {"contents": "read"})
        self.assertEqual(wf["concurrency"], {"group": "telegram-test", "cancel-in-progress": False})
        job = wf["jobs"]["test"]
        self.assertEqual((job["name"], job["timeout-minutes"]), ("알림 연결 시험", 5))
        self.assertNotIn("permissions", job)
        steps = job["steps"]
        self.assertEqual(steps[0]["uses"], "actions/checkout@v4")
        self.assertIs(steps[0]["with"]["persist-credentials"], False)
        self.assertTrue(steps[1]["uses"].startswith("actions/setup-python@"))
        status, send = steps[2], steps[3]
        self.assertEqual((status["id"], status["name"], status["run"], status["env"]), ("status", "시크릿 등록 여부 확인", "python -m pipeline.notify status", TELEGRAM_ENV))
        self.assertNotIn("if", status)
        self.assertEqual((send["name"], send["run"], send["env"]), ("시험 메시지 보내기", "python -m pipeline.notify test", TELEGRAM_ENV))
        self.assertEqual(send["if"], "steps.status.outputs.ready == 'true'")
        self.assertEqual(len(steps), 4)
        text = (WORKFLOWS / "telegram-test.yml").read_text(encoding="utf-8")
        self.assertNotIn("continue-on-error", text)                           # 시험은 실패하면 빨강이어야 한다
        self.assertEqual(text.count("secrets."), 4)

    def test_the_test_workflow_is_manual_only_and_has_no_schedule(self):
        text = (WORKFLOWS / "telegram-test.yml").read_text(encoding="utf-8")
        for forbidden in ("schedule:", "push:", "pull_request", "issues:", "issue_comment"):
            self.assertNotIn(forbidden, text)

    def test_no_run_script_mentions_the_secret_names(self):
        seen = 0
        for path in sorted(WORKFLOWS.glob("*.yml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            for job in data["jobs"].values():
                for step in job.get("steps", []):
                    seen += 1
                    self.assertNotIn("TELEGRAM", str(step.get("run", "")), path.name)
        self.assertGreater(seen, 30)


# ----------------------------------------------------------------------------
# 문서와 코드의 일치
# ----------------------------------------------------------------------------
def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class DocsMatchCodeTest(unittest.TestCase):
    def test_the_operator_guide_covers_every_step_and_names(self):
        guide = read(".github/editorial/TELEGRAM_SETUP.md")
        for needle in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "/start", "[공통] 텔레그램 알림 시험", "Settings", "Secrets and variables", "Actions",
                       "/revoke", "BotFather", "종단간", "휴대폰", "회사 PC", "@chance_auto_post_bot", "AI", "삭제"):
            self.assertIn(needle, guide, needle)

    def test_the_guide_has_no_values_or_token_shapes(self):
        guide = read(".github/editorial/TELEGRAM_SETUP.md")
        self.assertEqual(leaks(guide), [])
        from pipeline.secret_patterns import find_secrets
        self.assertEqual(find_secrets(guide), [])
        self.assertNotRegex(guide, r"[0-9]{7,}")                        # 채팅 ID·봇 번호처럼 보이는 긴 숫자를 적지 않는다
        self.assertNotIn("api.telegram.org/bot", guide.replace("api.telegram.org/bot<", ""))

    def test_the_guide_numbers_match_the_code(self):
        guide = read(".github/editorial/TELEGRAM_SETUP.md") + read("docs/ARCHITECTURE.md")
        self.assertIn(f"{notify.MAX_MESSAGES}통", guide)
        self.assertIn(f"{notify.TIMEOUT_SECONDS}초", guide)
        self.assertIn(f"{notify.RETRY_AFTER_MAX}초", guide)
        self.assertIn("3,800", guide)
        self.assertIn("1.1초", guide)

    def test_the_docs_give_the_deploy_wait_and_the_cached_404_advice(self):
        """독립 검증 N-2: 알림 문구·안내서·구조 문서가 같은 말(약 3분 뒤에 열기, 404 가 최대 약 18분 보관, 후속 후보)을 한다."""
        for needle in ("약 3분", "404", "약 18분", "3분 뒤에 열어"):
            self.assertIn(needle, notify.DEPLOY_WAIT_NOTE, needle)
        guide = read(".github/editorial/TELEGRAM_SETUP.md")
        for needle in ("약 3분", "404", "약 18분", "3분 뒤에 열어", "D-41", "후속", "pages.yml"):
            self.assertIn(needle, guide, needle)
        architecture = read("docs/ARCHITECTURE.md")
        for needle in ("약 18분", "3분 뒤에 열어", "후속 후보", "pages.yml"):
            self.assertIn(needle, architecture, needle)
        self.assertNotIn("1~3분", guide + architecture + read("docs/ACTIONS_GUIDE.md"))

    def test_the_known_limits_from_the_independent_review_are_written_down(self):
        """독립 검증 N-4·N-8·N-10·N-11: 코드를 바꾸지 않고 문서에 한계로 적기로 한 것들."""
        security = read("docs/SECURITY_GUARDRAILS.md")
        for needle in ("toJSON(secrets)", "secrets: inherit", "외부 `uses:`", "재사용 워크플로"):
            self.assertIn(needle, security, needle)
        architecture = read("docs/ARCHITECTURE.md")
        for needle in ("toJSON(secrets)", "작업 D", "jobs.<잡>.secrets", "Pages 배포 실행", "`main` 에서만"):
            self.assertIn(needle, architecture, needle)
        guide = read(".github/editorial/TELEGRAM_SETUP.md")
        for needle in ("Pages 배포 실행", "Actions 실패 알림", "사칭", "마지막 선택지", "`main` 에서만"):
            self.assertIn(needle, guide, needle)
        actions = read("docs/ACTIONS_GUIDE.md")
        for needle in ("Pages 배포 실행", "`main` 에서만", "`main` 이 아닌 브랜치"):
            self.assertIn(needle, actions, needle)

    def test_the_architecture_documents_the_alert_layer(self):
        text = read("docs/ARCHITECTURE.md")
        for needle in ("pipeline/notify.py", "chance-published", "notify_draft_waiting", "텔레그램", "continue-on-error", "WF-13",
                       "[공통] 텔레그램 알림 시험", "telegram-test.yml"):
            self.assertIn(needle, text, needle)

    def test_the_security_guardrails_have_the_token_rule_and_the_validator_rule(self):
        text = read("docs/SECURITY_GUARDRAILS.md")
        self.assertRegex(text, r"\| G-C12 \|")
        self.assertRegex(text, r"\| WF-13 ")
        for needle in ("TELEGRAM_BOT_TOKEN", "requests", "/revoke", "env"):
            self.assertIn(needle, text, needle)

    def test_the_actions_guide_lists_the_test_workflow_and_the_alert_kinds(self):
        text = read("docs/ACTIONS_GUIDE.md")
        for needle in ("[공통] 텔레그램 알림 시험", "telegram-test.yml", "새 글", "발행 대기", "확인 필요", "TELEGRAM_SETUP.md"):
            self.assertIn(needle, text, needle)

    def test_the_ops_inbox_guide_explains_the_relation_to_the_comment(self):
        text = read("docs/OPS_INBOX.md")
        for needle in ("텔레그램", "TELEGRAM_BOT_TOKEN", "코멘트 성공 여부와 무관", "한 번 더"):
            self.assertIn(needle, text, needle)

    def test_the_engineering_guide_allows_continue_on_error_only_for_the_alert_step(self):
        text = read("docs/ENGINEERING_GUIDE.md")
        self.assertIn("pipeline.notify", text)
        self.assertIn("WF-13", text)

    def test_the_handler_mentions_the_telegram_alerts(self):
        self.assertIn("텔레그램", read("HANDLER.md"))


if __name__ == "__main__":
    unittest.main()
