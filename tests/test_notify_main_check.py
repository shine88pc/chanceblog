"""main 검사 실패 즉시 알림(이슈 #90) — `python -m pipeline.notify main-check-failed` 와 guardrails.yml 의 alert 잡.

2026-10-31 main 에 직접 올라간 변경이 발행 프로그램을 망가뜨렸는데 검사 실패는 GitHub 알림으로만 갔고, 운영자는 텔레그램 요청만 본다.
이제 main 에 올라간 변경이 규칙·시험 검사에 떨어지면 한 통이 곧바로 간다. 값(커밋·올린 사람·실행 주소)은 명령 줄이 아니라 Actions 가 주는 환경변수에서만 읽는다.
텔레그램 요청은 전부 가짜(FakeNet)이고 토큰·채팅 ID 는 런타임에 조합한 가짜 값이다.
"""
import contextlib
import io
import sys
import unittest
import urllib.error
from pathlib import Path

import yaml

import _bootstrap
import notify_helpers as nh
from notify_helpers import ENV, FakeNet, Clock, http_error, leaks
from pipeline import notify

SHA = "c4a0853" + "e1f0a2b3c4d5e6f708192a3b4c5d6e7f"
RUN_ENV = dict(ENV, GITHUB_SHA=SHA, GITHUB_ACTOR="shine88pc", GITHUB_REPOSITORY="shine88pc/chanceblog", GITHUB_RUN_ID="41401574943")
RUN_URL = "https://github.com/shine88pc/chanceblog/actions/runs/41401574943"
SENT_LINE = "텔레그램 알림: main 검사 실패를 알렸습니다"
WORKFLOW = _bootstrap.ROOT / ".github" / "workflows" / "guardrails.yml"


def run_cli(*argv, environ=None, net=None):
    lines, clock = [], Clock()
    net = net if net is not None else FakeNet()
    code = notify.main(list(argv), environ=dict(RUN_ENV if environ is None else environ), out=lines.append, opener=net, sleep=clock.sleep,
                       clock=clock.clock, budget=notify.Budget())
    return code, lines, net


class FormatTest(unittest.TestCase):
    def test_the_message_names_the_change_the_author_and_what_to_do(self):
        text = notify.format_main_check_failed(SHA, "shine88pc")
        self.assertTrue(text.startswith(notify.ALERT_MARK + " main 검사 실패"))
        self.assertIn("(c4a0853, 올린 사람 shine88pc)", text)
        self.assertIn("저장소 규칙·시험을 통과하지 못했습니다", text)
        self.assertIn("Blogger·네이버 발행이 멈췄을 수 있습니다", text)
        self.assertIn("AI 에게 [요청]으로", text)

    def test_values_that_are_not_a_commit_or_a_login_are_never_put_into_the_text(self):
        for sha in (None, "", "HEAD", "zzzzzzz", "c4a085", "c4a0853; rm -rf /", "<b>c4a0853</b>", SHA + "0" * 10):
            self.assertIn("(알 수 없음, 올린 사람", notify.format_main_check_failed(sha, "shine88pc"), repr(sha))
        for actor in (None, "", "a b", "<script>", "a" * 40, "-bad", "bad-", "https://evil.example", "x\ny", "github-actions[bot]x", "a.b", "@x", "a/b", "a_b",
                      "a[bot][bot]", "Github-Actions[BOT]", "한글", "a@x", "a" * 38 + "\u212a"):
            self.assertIn("올린 사람 알 수 없음)", notify.format_main_check_failed(SHA, actor), repr(actor))
        self.assertIn("올린 사람 github-actions[bot])", notify.format_main_check_failed(SHA, "github-actions[bot]"))
        self.assertIn("올린 사람 a)", notify.format_main_check_failed(SHA, "a"))


class CommandTest(unittest.TestCase):
    def test_without_the_secrets_it_prints_one_line_and_sends_nothing(self):
        for env in ({}, {"TELEGRAM_BOT_TOKEN": nh.TOKEN}, {"TELEGRAM_CHAT_ID": nh.CHAT}):
            code, lines, net = run_cli("main-check-failed", environ=dict(env, GITHUB_SHA=SHA))
            self.assertEqual((code, lines, net.calls), (0, ["텔레그램 알림: 건너뜀(시크릿 없음)"], 0))

    def test_one_plain_message_with_an_open_run_button(self):
        code, lines, net = run_cli("main-check-failed")
        self.assertEqual((code, lines, net.calls), (0, [SENT_LINE], 1))
        body = net.bodies()[0]
        self.assertNotIn("parse_mode", body)                                    # 평문 — 값은 코드가 모양을 확인한 것뿐이다
        self.assertIn("(c4a0853, 올린 사람 shine88pc)", body["text"])
        self.assertEqual(body["reply_markup"], {"inline_keyboard": [[{"text": "실행 열기", "url": RUN_URL}, {"text": "AI 에게 요청하기", "url": notify.NEW_ISSUE_URL}]]})
        self.assertEqual(leaks(*lines), [])

    def test_hostile_environment_values_are_not_echoed_and_add_no_link(self):
        env = dict(RUN_ENV, GITHUB_SHA="<b>x</b>", GITHUB_ACTOR="https://evil.example/x", GITHUB_REPOSITORY="evil.example/x/../y", GITHUB_RUN_ID="1")
        code, lines, net = run_cli("main-check-failed", environ=env)
        self.assertEqual((code, net.calls), (0, 1))
        body = net.bodies()[0]
        self.assertNotIn("evil", body["text"])
        self.assertNotIn("<b>", body["text"])
        self.assertEqual([button["text"] for button in body["reply_markup"]["inline_keyboard"][0]], ["AI 에게 요청하기"])         # 실행 주소가 이상하면 그 버튼만 빠진다

    def test_a_run_environment_that_is_missing_still_sends_the_message_with_only_the_request_button(self):
        code, lines, net = run_cli("main-check-failed", environ=ENV)
        self.assertEqual((code, lines, net.calls), (0, [SENT_LINE], 1))
        self.assertEqual(net.bodies()[0]["reply_markup"], {"inline_keyboard": [[{"text": "AI 에게 요청하기", "url": notify.NEW_ISSUE_URL}]]})
        self.assertIn("(알 수 없음, 올린 사람 알 수 없음)", net.bodies()[0]["text"])

    def test_a_failed_send_warns_but_never_fails_the_step(self):
        for reason, outcome in (("unauthorized", http_error(401, "Unauthorized")), ("network", urllib.error.URLError("x")), ("server", http_error(502, "Bad Gateway"))):
            with self.subTest(reason=reason):
                code, lines, net = run_cli("main-check-failed", net=FakeNet(outcome))
                self.assertEqual(code, 0)
                self.assertEqual(lines[-1], notify.WARNING_LINE)
                self.assertTrue(lines[0].startswith("텔레그램 알림: main 검사 실패 알림을 보내지 못했습니다"))
                self.assertEqual(leaks(*lines), [])

    def test_an_unexpected_error_stays_inside_the_command(self):
        lines = []
        from unittest import mock
        with mock.patch.object(notify, "run_main_check_failed", side_effect=RuntimeError(nh.SEND_URL)):
            code = notify.main(["main-check-failed"], environ=dict(RUN_ENV), out=lines.append)
        self.assertEqual(code, 0)
        self.assertEqual(leaks(*lines), [])

    def test_no_option_accepts_an_external_value(self):
        parser = notify.build_parser()
        subparsers = [action for action in parser._actions if action.dest == "event"][0].choices
        self.assertIn("main-check-failed", subparsers)
        options = sorted(opt for action in subparsers["main-check-failed"]._actions for opt in action.option_strings if opt not in ("-h", "--help"))
        self.assertEqual(options, [])
        for argv in (["main-check-failed", "--sha", "x"], ["main-check-failed", "--actor", "x"], ["main-check-failed", nh.TOKEN]):
            err = io.StringIO()
            with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(err):
                notify.main(argv, environ=dict(ENV), out=lambda line: None)
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(leaks(err.getvalue()), [])
            self.assertIn(notify.USAGE_ERROR_LINE, err.getvalue())

    def test_the_usage_line_lists_the_new_command(self):
        self.assertIn("main-check-failed", notify.USAGE_ERROR_LINE)

    def test_the_module_function_sends_through_a_given_notifier(self):
        net, clock = FakeNet(), Clock()
        notifier = notify.Notifier(dict(ENV), opener=net, sleep=clock.sleep, clock=clock.clock, budget=notify.Budget())
        result = notify.notify_main_check_failed(SHA, "shine88pc", RUN_URL, notifier=notifier)
        self.assertTrue(result.sent)
        self.assertEqual(net.bodies()[0]["reply_markup"]["inline_keyboard"][0][0]["url"], RUN_URL)
        result = notify.notify_main_check_failed(SHA, "shine88pc", "https://evil.example/runs/1", notifier=notifier)
        self.assertTrue(result.sent)
        self.assertEqual([b["text"] for b in net.bodies()[1]["reply_markup"]["inline_keyboard"][0]], ["AI 에게 요청하기"])      # 허용 목록 밖 주소는 버튼이 되지 않는다


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.data = yaml.safe_load(self.text)
        self.job = self.data["jobs"]["alert"]

    def test_the_alert_job_runs_once_only_for_a_failed_push_to_main(self):
        self.assertEqual(self.job["needs"], "validate")
        condition = self.job["if"]
        self.assertEqual(condition, "${{ always() && github.event_name == 'push' && needs.validate.result == 'failure' }}")      # 조건 전체를 고정한다(|| true 같은 덧붙임을 잡는다)
        self.assertNotIn("matrix", self.job.get("strategy", {}))                    # 3.10·3.12 두 칸이 둘 다 떨어져도 알림은 한 번
        self.assertIn("push", self.data[True])                                       # PyYAML 은 on 을 True 로 읽는다
        self.assertEqual(self.data[True]["push"]["branches"], ["main"])

    def test_pull_request_failures_do_not_send_a_phone_alert(self):
        self.assertIn("github.event_name == 'push'", self.job["if"])
        self.assertNotIn("pull_request", self.job["if"])

    def test_the_secrets_are_only_in_the_step_env_and_the_step_cannot_fail_the_run(self):
        notify_steps = [step for step in self.job["steps"] if "run" in step]
        self.assertEqual(len(notify_steps), 1)
        step = notify_steps[0]
        self.assertEqual(step["run"], "python -m pipeline.notify main-check-failed")
        self.assertEqual(step["env"], {"TELEGRAM_BOT_TOKEN": "${{ secrets.TELEGRAM_BOT_TOKEN }}", "TELEGRAM_CHAT_ID": "${{ secrets.TELEGRAM_CHAT_ID }}"})
        self.assertIs(step.get("continue-on-error"), True)
        self.assertLessEqual(step.get("timeout-minutes", 99), 2)
        self.assertEqual(self.text.count("secrets.TELEGRAM_BOT_TOKEN"), 1)
        self.assertEqual(self.text.count("secrets.TELEGRAM_CHAT_ID"), 1)

    def test_the_job_only_reads_the_repository_and_has_a_time_limit(self):
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        self.assertNotIn("permissions", self.job)                                     # 잡이 더 넓은 권한을 달라고 하지 않는다
        self.assertLessEqual(self.job["timeout-minutes"], 10)
        self.assertEqual(self.job["steps"][0]["uses"], "actions/checkout@v6")                         # 알림 잡도 Node 24 판(이슈 #91)
        self.assertEqual(self.job["steps"][0]["with"], {"persist-credentials": False})                  # 텔레그램 시크릿과 함께 도는 잡이라 저장소 토큰을 남기지 않는다
        self.assertEqual(self.job["steps"][1]["uses"], "actions/setup-python@v6")
        self.assertEqual(self.job["steps"][1]["with"], {"python-version": "3.12"})

    def test_the_validation_job_itself_is_unchanged_in_its_checks(self):
        names = [step.get("name") or step["uses"] for step in self.data["jobs"]["validate"]["steps"]]
        self.assertEqual(names[2:], ["검증 도구 설치", "저장소 가드레일 검증", "단위 테스트", "워크플로 정적 분석 (actionlint)"])

    def test_the_repository_validator_accepts_the_new_secret_use_and_the_step_shape(self):
        sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
        import validate_repo as vr
        self.assertEqual(vr.check_telegram_secrets(_bootstrap.ROOT, vr.list_files(_bootstrap.ROOT)), [])           # WF-13: 시크릿은 단계 env 에만
        step = next(item for item in self.job["steps"] if "run" in item)
        self.assertTrue(vr._is_alert_step(step))                                                                      # WF-6: 알림 단계 모양이라 continue-on-error 경고가 없다


class DocumentationTest(unittest.TestCase):
    def test_the_architecture_doc_lists_the_event(self):
        doc = (_bootstrap.ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        for phrase in ("notify_main_check_failed", "main-check-failed", "guardrails.yml", "alert", "secret_patterns}.py", "다섯 파일", "`AI 에게 요청하기`"):
            self.assertIn(phrase, doc, phrase)
        setup = (_bootstrap.ROOT / ".github" / "editorial" / "TELEGRAM_SETUP.md").read_text(encoding="utf-8")
        for phrase in ("main 검사 실패", "실행 열기 · AI 에게 요청하기"):
            self.assertIn(phrase, setup, phrase)


if __name__ == "__main__":
    unittest.main()
