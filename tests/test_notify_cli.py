"""텔레그램 알림 명령 줄(python -m pipeline.notify …) 시험: 새 글 알림(chance-published)·시크릿 등록 여부(status)·연결 시험(test).

chance-published 는 대부분 가짜 git(FakeGit: rev-list·diff-tree -z·cat-file 세 명령의 출력 모양을 그대로 흉내 냄)으로 시험하고 — 이 컴퓨터에서는 git 한 번이
0.3초가 넘게 걸린다 — 실제 git 저장소(임시 폴더)로는 RealGitTest 가 출력 모양(한글·공백이 든 경로, -z)과 부모 없는 커밋을 확인한다.
텔레그램 요청은 전부 가짜(FakeNet)이고 토큰·채팅 ID 는 런타임에 조합한 가짜 값이다. 출력·실행 요약·단계 출력 파일 어디에도 값이 없어야 한다.
"""
import contextlib
import http.client
import io
import itertools
import os
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import notify_helpers as nh
from notify_helpers import CHAT, ENV, TOKEN, Clock, FakeGit, FakeNet, http_error, leaks, ok_reply
from pipeline import notify

KR_URL = "https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-093056/"
EN_URL = "https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-093056/"
SENT_LINE = "텔레그램 알림: 새 글 2편을 알렸습니다"


class CliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.counter = itertools.count()

    def run_cli(self, *argv, environ=None, net=None, root=None, runner=None, now=None):
        lines, clock = [], Clock()
        net = net if net is not None else FakeNet()
        kwargs = {} if runner is None else {"runner": runner}
        code = notify.main(list(argv), environ=dict(ENV if environ is None else environ), out=lines.append, root=root, opener=net,
                           sleep=clock.sleep, clock=clock.clock, budget=notify.Budget(), now=now, **kwargs)
        return code, lines, net


class ChancePublishedTest(CliCase):
    def setUp(self):
        super().setUp()
        self.root = nh.make_root(self.tmp / "site")

    def announce(self, files=None, environ=None, net=None, git=None, argv=("chance-published", "--commit", "HEAD"), root=None):
        git = git if git is not None else FakeGit.adding(nh.pair_files() if files is None else files)
        code, lines, net = self.run_cli(*argv, environ=environ, net=net, root=root or self.root, runner=git)
        return code, lines, net, git

    def test_without_secrets_it_prints_one_line_and_touches_nothing(self):
        def refuse(*args, **kwargs):
            raise AssertionError("시크릿이 없으면 git 도 부르지 않는다")
        for env in ({}, {"TELEGRAM_BOT_TOKEN": TOKEN}, {"TELEGRAM_CHAT_ID": CHAT}):
            code, lines, net = self.run_cli("chance-published", "--commit", "HEAD", environ=env, root=self.root, runner=refuse)
            self.assertEqual((code, lines, net.calls), (0, ["텔레그램 알림: 건너뜀(시크릿 없음)"], 0))

    def test_a_new_pair_is_announced_in_one_message_with_real_front_matter(self):
        code, lines, net, _ = self.announce()
        self.assertEqual((code, lines, net.calls), (0, [SENT_LINE], 1))
        body = net.bodies()[0]
        self.assertEqual(body["parse_mode"], "HTML")
        text = body["text"]
        self.assertIn(nh.KR_TITLE, text)
        self.assertIn(nh.EN_TITLE, text)
        self.assertIn("분야: 경제·일 · Economy &amp; Work", text)
        self.assertIn("출처: 유럽연합 CINEA", text)
        self.assertIn(KR_URL, text)
        self.assertIn(EN_URL, text)
        self.assertEqual(body["reply_markup"], {"inline_keyboard": [[{"text": "한글 글", "url": KR_URL}, {"text": "English", "url": EN_URL}]]})
        self.assertEqual(leaks(*lines), [])

    def test_the_actions_run_link_is_added_from_public_environment_values(self):
        env = dict(ENV, GITHUB_REPOSITORY="shine88pc/chanceblog", GITHUB_RUN_ID="12345")
        _, _, net, _ = self.announce(environ=env)
        self.assertIn('<a href="https://github.com/shine88pc/chanceblog/actions/runs/12345">열기</a>', net.bodies()[0]["text"])

    def test_a_malformed_run_environment_adds_no_link(self):
        for repo, run_id in (("evil.example/x/../y", "1"), ("shine88pc/chanceblog", "abc"), ("shine88pc", "1"), ("a b/c", "1"), ("someone/else", "9"), ("shine88pc/chanceblog", "")):
            _, _, net, _ = self.announce(environ=dict(ENV, GITHUB_REPOSITORY=repo, GITHUB_RUN_ID=run_id))
            self.assertNotIn("실행 기록", net.bodies()[0]["text"], (repo, run_id))

    def test_a_commit_hash_is_passed_to_git_as_given(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        for value in (sha, sha[:7], sha.upper(), "HEAD"):
            code, lines, net, git = self.announce(argv=("chance-published", "--commit", value))
            self.assertEqual((code, net.calls), (0, 1), value)
            self.assertEqual(git.calls[0][0], ["git", "rev-list", "--parents", "-n", "1", value])

    def test_the_default_commit_is_head(self):
        _, _, _, git = self.announce(argv=("chance-published",))
        self.assertEqual(git.calls[0][0][-1], "HEAD")

    def test_a_commit_without_new_posts_sends_nothing(self):
        code, lines, net, _ = self.announce(git=FakeGit([("A", "history.json", "[]"), ("M", "history.json", "[]")]))
        self.assertEqual((code, net.calls), (0, 0))
        self.assertEqual(lines, ["텔레그램 알림: 이 커밋에 새로 공개되는 글이 없어 보내지 않았습니다"])

    def test_editing_deleting_or_renaming_a_post_is_not_a_new_post(self):
        files = nh.pair_files()
        for status in ("M", "D", "R100", "C75", "T"):
            code, lines, net, _ = self.announce(git=FakeGit([(status, rel, text) for rel, text in files.items()]))
            self.assertEqual((code, net.calls), (0, 0), status)

    def test_files_outside_posts_or_with_other_names_are_ignored(self):
        post = nh.pair_files()[nh.KR_PATH]
        ignored = {"docs/2026-10-27-KR-093056.md": post, "_posts/readme.md": post, "_posts/a/note.txt": post, "_drafts/2026-10-27-KR-093056.md": post,
                   "_posts/a/2026-13-45-x.txt": post, "posts/2026-10-27-KR-093056.md": post}
        self.assertEqual(self.announce(ignored)[2].calls, 0)

    def test_unpublished_posts_are_not_announced(self):
        for value in ("false", "False", "no", "off", "null", "~", ""):
            with self.subTest(published=value):
                code, lines, net, _ = self.announce(nh.pair_files(kr_extra=f"published: {value}\n", en_extra=f"published: {value}\n"))
                self.assertEqual((code, net.calls), (0, 0))

    def test_only_the_published_post_of_a_pair_is_announced(self):
        _, _, net, _ = self.announce(nh.pair_files(en_extra="published: false\n"))
        text = net.bodies()[0]["text"]
        self.assertIn(nh.KR_TITLE, text)
        self.assertNotIn("Demand Surges", text)
        self.assertEqual([b["text"] for b in net.bodies()[0]["reply_markup"]["inline_keyboard"][0]], ["한글 글"])

    def test_a_quoted_false_is_treated_as_unpublished_like_the_deploy_check_does(self):
        """Jekyll 은 따옴표 친 "false" 를 문자열(참)로 보아 공개하지만, 배포 확인(verify_pages_deploy)과 같이 의심스러우면 비공개로 본다 — 안 열리는 주소를 알리는 쪽이 더 나쁘다."""
        _, lines, net, _ = self.announce(nh.pair_files(kr_extra="published: true\n", en_extra='published: "false"\n'))
        self.assertEqual((net.calls, lines), (1, ["텔레그램 알림: 새 글 1편을 알렸습니다"]))
        self.assertNotIn("Demand Surges", net.bodies()[0]["text"])

    def test_two_pairs_in_one_commit_make_two_messages_in_time_order(self):
        files = nh.pair_files("두 번째 한글", "Second English", stamp="183000")
        files.update(nh.pair_files("첫째 한글", "First English", stamp="093056"))
        code, lines, net, _ = self.announce(files)
        self.assertEqual((code, net.calls, lines), (0, 2, [SENT_LINE] * 2))
        self.assertIn("첫째 한글", net.bodies()[0]["text"])
        self.assertIn("두 번째 한글", net.bodies()[1]["text"])

    def test_a_lone_korean_post_is_announced(self):
        _, lines, net, _ = self.announce({nh.KR_PATH: nh.pair_files()[nh.KR_PATH]})
        self.assertEqual((net.calls, lines), (1, ["텔레그램 알림: 새 글 1편을 알렸습니다"]))

    def test_an_old_style_post_without_a_time_in_its_name_is_still_announced(self):
        _, lines, net, _ = self.announce({"_posts/2026-10-19-AI.md": nh.post_text("옛 형식 글", "ko", "산업 AI")})
        self.assertEqual((net.calls, lines), (1, ["텔레그램 알림: 새 글 1편을 알렸습니다"]))
        self.assertIn("https://shine88pc.github.io/chanceblog/posts/2026/10/19/AI/", net.bodies()[0]["text"])

    def test_the_language_falls_back_to_the_file_name_when_front_matter_has_none(self):
        text = nh.post_text("영어 글", "xx", "Cat")
        _, _, net, _ = self.announce({"_posts/Cat/2026-10-27-EN-093056.md": text})
        self.assertEqual([b["text"] for b in net.bodies()[0]["reply_markup"]["inline_keyboard"][0]], ["English"])

    def test_an_explicit_permalink_in_front_matter_decides_the_address(self):
        _, _, net, _ = self.announce(nh.pair_files(kr_extra="permalink: /posts/2026/10/20/korean-food-date-labels/\n"))
        self.assertIn("https://shine88pc.github.io/chanceblog/posts/2026/10/20/korean-food-date-labels/", net.bodies()[0]["text"])

    def test_titles_with_quotes_and_escapes_are_read_like_yaml(self):
        _, _, net, _ = self.announce(nh.pair_files('인용 "따옴표" 와 \\ 역슬래시 & <태그>', "It's a \"test\""))
        text = net.bodies()[0]["text"]
        self.assertIn('인용 "따옴표" 와 \\ 역슬래시 &amp; &lt;태그&gt;', text)
        self.assertIn("It's a \"test\"", text)

    def test_a_missing_config_still_announces_without_addresses(self):
        root = nh.make_root(self.tmp / "noconfig", config=None)
        code, lines, net, _ = self.announce(root=root)
        self.assertEqual((code, net.calls), (0, 1))
        self.assertNotIn("https://", net.bodies()[0]["text"])
        self.assertNotIn("reply_markup", net.bodies()[0])

    def test_at_most_ten_new_files_are_read(self):
        files = {}
        for i in range(7):
            files.update(nh.pair_files(f"한글 {i}", f"English {i}", stamp=f"{i:06d}"))
        self.assertEqual(len(files), 14)
        git = FakeGit.adding(files)
        self.assertEqual(len(notify.added_posts(self.root, "HEAD", runner=git)), 10)
        code, lines, net, git = self.announce(files)
        self.assertEqual(sum(1 for args, _ in git.calls if args[1] == "cat-file"), 10)

    def test_a_commit_without_a_parent_is_not_announced(self):
        code, lines, net, git = self.announce(git=FakeGit.adding(nh.pair_files(), parents=()))
        self.assertEqual((code, net.calls), (0, 0))
        self.assertIn("부모 커밋이 없어", lines[0])
        self.assertEqual(lines[-1], notify.WARNING_LINE)
        self.assertEqual([args[1] for args, _ in git.calls], ["rev-list"])           # diff-tree 는 부르지 않는다(저장소 전체를 새 글로 오인하지 않게)

    def test_merge_commits_with_two_parents_are_still_read(self):
        code, lines, net, _ = self.announce(git=FakeGit.adding(nh.pair_files(), parents=("b" * 40, "c" * 40)))
        self.assertEqual((code, net.calls), (0, 1))

    def test_a_broken_git_call_is_reported_and_does_not_fail_the_step(self):
        for broken in ("rev-list", "diff-tree", "cat-file"):
            with self.subTest(broken=broken):
                code, lines, net, _ = self.announce(git=FakeGit.adding(nh.pair_files(), broken={broken}))
                self.assertEqual((code, net.calls), (0, 0))
                self.assertIn("git 명령이 실패했습니다", lines[0])
                self.assertEqual(lines[-1], notify.WARNING_LINE)

    def test_a_missing_git_program_or_a_timeout_is_reported_and_does_not_fail_the_step(self):
        for exc in (FileNotFoundError(f"git not found {nh.SEND_URL}"), subprocess.TimeoutExpired("git", 30), PermissionError("x")):
            def failing(args, **kwargs):
                raise exc
            code, lines, net, _ = self.announce(git=failing)
            self.assertEqual((code, net.calls), (0, 0))
            self.assertIn("git 을 실행하지 못했습니다", lines[0])
            self.assertEqual(leaks(*lines), [])

    def test_git_is_called_without_a_shell_and_only_with_fixed_arguments(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        _, _, _, git = self.announce(argv=("chance-published", "--commit", sha))
        self.assertEqual(len(git.calls), 4)
        for args, kwargs in git.calls:
            self.assertIsInstance(args, list)
            self.assertEqual(args[0], "git")
            self.assertFalse(kwargs.get("shell", False))
            self.assertEqual(kwargs["timeout"], 30)
            self.assertEqual(Path(kwargs["cwd"]), self.root)
            self.assertIs(kwargs["capture_output"], True)
        self.assertEqual(git.calls[0][0], ["git", "rev-list", "--parents", "-n", "1", sha])
        self.assertEqual(git.calls[1][0], ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", "-z", sha])
        self.assertEqual(git.calls[2][0], ["git", "cat-file", "blob", f"{sha}:{nh.KR_PATH}"])
        self.assertEqual(git.calls[3][0], ["git", "cat-file", "blob", f"{sha}:{nh.EN_PATH}"])

    def test_unsafe_commit_arguments_are_refused_before_git_runs(self):
        def refuse(*args, **kwargs):
            raise AssertionError("git 을 부르면 안 된다")
        for value in ("--output=x", "HEAD; ls", "zzzzzzz", "", "head", "HEAD~1", "abc12", "a" * 41, "HEAD\n", "$(id)", "-1", "HEAD HEAD"):
            with self.subTest(value=value):
                code, lines, net = self.run_cli("chance-published", f"--commit={value}", root=self.root, runner=refuse)
                self.assertEqual((code, net.calls), (2, 0))
                self.assertIn("사용법 오류", lines[0])

    def test_a_send_failure_is_a_warning_and_exit_zero_without_leaking(self):
        for outcome, reason in ((http_error(401, "Unauthorized"), "unauthorized"), (http_error(400, "Bad Request: chat not found"), "chat_not_found"),
                                (http_error(403, "Forbidden: bot was blocked by the user"), "forbidden"), (urllib.error.URLError(nh.SEND_URL), "network")):
            with self.subTest(reason=reason):
                code, lines, net, _ = self.announce(net=FakeNet(outcome))
                self.assertEqual(code, 0)
                self.assertTrue(any(notify.REASON_TEXT[reason] in line for line in lines), lines)
                self.assertEqual(lines[-1], notify.WARNING_LINE)
                self.assertEqual(leaks(*lines), [])

    def test_invalid_secret_shapes_are_reported_as_a_warning(self):
        code, lines, net, _ = self.announce(environ={"TELEGRAM_BOT_TOKEN": "no", "TELEGRAM_CHAT_ID": CHAT})
        self.assertEqual((code, net.calls), (0, 0))
        self.assertIn("토큰 모양이 올바르지 않습니다", "\n".join(lines))
        self.assertEqual(lines[-1], notify.WARNING_LINE)

    def test_the_rate_limit_retry_is_used_and_still_reports_success(self):
        code, lines, net, _ = self.announce(net=FakeNet(http_error(429, retry_after=1), ok_reply()))
        self.assertEqual((code, net.calls, lines), (0, 2, [SENT_LINE]))

    def test_one_failed_pair_among_two_still_sends_the_other_and_warns_once(self):
        files = nh.pair_files("첫째 한글", "First English", stamp="093056")
        files.update(nh.pair_files("둘째 한글", "Second English", stamp="183000"))
        code, lines, net, _ = self.announce(files, net=FakeNet(http_error(403, "Forbidden"), ok_reply()))
        self.assertEqual((code, net.calls), (0, 2))
        self.assertEqual(lines.count(notify.WARNING_LINE), 1)
        self.assertEqual(lines[-1], notify.WARNING_LINE)
        self.assertIn(SENT_LINE, lines)

    def test_an_unexpected_error_inside_the_command_exits_zero_with_the_class_name_only(self):
        with mock.patch.object(notify, "collect_new_posts", side_effect=RuntimeError(nh.SEND_URL)):
            code, lines, net = self.run_cli("chance-published", root=self.root, runner=FakeGit())
        self.assertEqual(code, 0)
        self.assertIn("RuntimeError", lines[0])
        self.assertEqual(lines[-1], notify.WARNING_LINE)
        self.assertEqual(leaks(*lines), [])


class RealGitTest(unittest.TestCase):
    """실제 git 의 출력 모양(-z 로 읽는 한글·공백이 든 경로, 부모 없는 커밋)을 확인한다. 준비에 git 호출이 많아 저장소는 한 번만 만든다."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = nh.make_repo(Path(cls._tmp.name) / "repo")
        cls.pair_sha = nh.commit_files(cls.repo, nh.pair_files())
        cls.other_sha = nh.commit_files(cls.repo, {"history.json": "[]\n", nh.KR_PATH: nh.post_text("수정된 제목", "ko", "경제·일"), "docs/x.md": "x\n"})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_cli(self, *argv, root=None):
        lines, clock, net = [], Clock(), FakeNet()
        code = notify.main(list(argv), environ=dict(ENV), out=lines.append, root=root or self.repo, opener=net, sleep=clock.sleep, clock=clock.clock,
                           budget=notify.Budget())
        return code, lines, net

    def test_a_real_commit_with_a_korean_directory_and_a_space_is_announced(self):
        code, lines, net = self.run_cli("chance-published", "--commit", self.pair_sha)
        self.assertEqual((code, lines, net.calls), (0, [SENT_LINE], 1))
        text = net.bodies()[0]["text"]
        self.assertIn(nh.KR_TITLE, text)
        self.assertIn(KR_URL, text)
        self.assertIn(EN_URL, text)

    def test_a_real_commit_that_only_edits_files_announces_nothing(self):
        code, lines, net = self.run_cli("chance-published", "--commit", self.other_sha)
        self.assertEqual((code, net.calls), (0, 0))
        self.assertEqual(lines, ["텔레그램 알림: 이 커밋에 새로 공개되는 글이 없어 보내지 않았습니다"])

    def test_head_and_an_abbreviated_hash_resolve_in_the_real_repository(self):
        self.assertEqual(sorted(notify.added_posts(self.repo, self.pair_sha[:8])), sorted([nh.KR_PATH, nh.EN_PATH]))
        self.assertEqual(notify.added_posts(self.repo, self.other_sha), [])

    def test_a_real_root_commit_has_no_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            nh.git(repo, "init", "-q", "-b", "main")
            for rel, text in {"_config.yml": nh.CONFIG, **nh.pair_files()}.items():
                (repo / rel).parent.mkdir(parents=True, exist_ok=True)
                (repo / rel).write_text(text, encoding="utf-8", newline="\n")
            nh.git(repo, "add", "-A")
            nh.git(repo, "commit", "-q", "-m", "only")
            code, lines, net = self.run_cli("chance-published", root=repo)
        self.assertEqual((code, net.calls), (0, 0))
        self.assertIn("부모 커밋이 없어", lines[0])
        self.assertEqual(lines[-1], notify.WARNING_LINE)


class SiteAddressTest(CliCase):
    def test_site_base_from_the_config(self):
        for config, expected in ((nh.CONFIG, "https://shine88pc.github.io/chanceblog/"), ('url: "https://a.example/"\nbaseurl: ""\n', "https://a.example/"),
                                 ("url: https://a.example\nbaseurl: /b/c/\n", "https://a.example/b/c/"), ("baseurl: /x\n", ""), ("title: t\n", ""),
                                 ("  url: https://nested.example\n", ""), ("url: https://a.example # 주석\nbaseurl: '/q'\n", "https://a.example/q/")):
            with self.subTest(config=config[:25]):
                root = nh.make_root(self.tmp / f"c{next(self.counter)}", config=config)
                self.assertEqual(notify.site_base(root), expected)
        self.assertEqual(notify.site_base(self.tmp / "nowhere"), "")

    def test_the_expected_address_follows_the_same_rule_as_the_deploy_check(self):
        root = nh.make_root(self.tmp / "site")
        files = nh.pair_files()
        kr, en = notify.parse_front_matter(files[nh.KR_PATH]), notify.parse_front_matter(files[nh.EN_PATH])
        self.assertEqual(notify.expected_post_url(root, nh.KR_PATH, kr), KR_URL)
        self.assertEqual(notify.expected_post_url(root, nh.EN_PATH, en), EN_URL)
        self.assertEqual(notify.expected_post_url(root, "_posts/x/not-a-post.md", kr), "")
        self.assertEqual(notify.expected_post_url(root, nh.KR_PATH, {"permalink": None}), "")

    def test_the_address_uses_the_front_matter_date_in_site_time(self):
        root = nh.make_root(self.tmp / "site")
        front = {"date": "2026-10-20 23:30:00 -0500"}                # 사이트 시간(KST)으로는 다음 날 13:30
        self.assertEqual(notify.expected_post_url(root, "_posts/a/2026-10-20-KR-000001.md", front),
                         "https://shine88pc.github.io/chanceblog/posts/2026/10/21/KR-000001/")

    def test_a_missing_deploy_check_module_means_no_address(self):
        root = nh.make_root(self.tmp / "site")
        front = notify.parse_front_matter(nh.pair_files()[nh.KR_PATH])
        with mock.patch.object(notify, "_pages_module", return_value=None):
            self.assertEqual(notify.expected_post_url(root, nh.KR_PATH, front), "")

    def test_the_deploy_check_module_is_loaded_from_its_file_once_under_a_private_name(self):
        notify._PAGES = None
        module = notify._pages_module()
        self.assertIsNotNone(module)
        self.assertEqual(module.__name__, "_chanceblog_verify_pages_deploy")
        self.assertEqual(Path(module.__file__).resolve(), (_bootstrap.ROOT / "scripts" / "verify_pages_deploy.py").resolve())
        self.assertTrue(hasattr(module, "expected_url"))
        self.assertIs(notify._pages_module(), module)                                  # 한 번만 읽는다


class FrontMatterTest(unittest.TestCase):
    def test_reads_the_fields_the_alert_needs_from_real_shapes(self):
        text = ('---\nlayout: post\npublished: false\ntitle: "제목: \\"따옴표\\" 포함"\ncategory: "기술·미래"\ntags: ["a"]\nlang: ko\nsource_name: \'작은 따옴표\'\n'
                'date: 2026-10-20 08:30:00 +0900\npermalink: /posts/2026/10/20/x/\nslug: x\nimage: "https://example.com/a.jpg"\n---\n\n본문: title: 가짜\n')
        self.assertEqual(notify.parse_front_matter(text), {
            "published": "false", "title": '제목: "따옴표" 포함', "category": "기술·미래", "lang": "ko", "source_name": "작은 따옴표",
            "date": "2026-10-20 08:30:00 +0900", "permalink": "/posts/2026/10/20/x/", "slug": "x"})

    def test_no_front_matter_or_unreadable_shapes(self):
        self.assertEqual(notify.parse_front_matter("본문만 있다"), {})
        self.assertEqual(notify.parse_front_matter(""), {})
        self.assertEqual(notify.parse_front_matter(chr(0xFEFF) + "---\ntitle: x\n---\n"), {"title": "x"})
        self.assertEqual(notify.parse_front_matter("---\ntitle: [a, b]\ncategory: |\n  x\n---\n"), {"title": None, "category": None})
        self.assertEqual(notify.parse_front_matter('---\ntitle: "닫는 따옴표 없음\n---\n'), {"title": None})
        self.assertEqual(notify.parse_front_matter("---\n  title: 들여쓴 줄은 무시\n---\n"), {})
        self.assertEqual(notify.parse_front_matter("---\ntitle: 값 # 주석\n---\n"), {"title": "값"})
        self.assertEqual(notify.parse_front_matter("---\n'title': 키에 따옴표\n---\n"), {"title": "키에 따옴표"})

    def test_front_matter_ends_at_the_closing_fence(self):
        self.assertEqual(notify.parse_front_matter("---\ntitle: a\n---\ntitle: b\n"), {"title": "a"})
        self.assertEqual(notify.parse_front_matter("---\ntitle: a\n...\ntitle: b\n"), {"title": "a"})

    def test_a_blank_published_value_means_unpublished(self):
        self.assertEqual(notify.parse_front_matter("---\npublished:\n---\n"), {"published": "null"})
        self.assertEqual(notify.parse_front_matter("---\npublished: # 주석뿐\n---\n"), {"published": "null"})
        self.assertTrue(notify.is_unpublished({"published": "null"}))
        self.assertTrue(notify.is_unpublished({"published": "FALSE"}))
        self.assertFalse(notify.is_unpublished({"published": "true"}))
        self.assertFalse(notify.is_unpublished({}))
        self.assertFalse(notify.is_unpublished({"published": None}))


class BrokenFrontMatterAlertTest(CliCase):
    """공개된 글의 머리말이 깨졌을 때(결함 D-80, 이슈 #59)의 새 글 알림. 사이트는 제목 대신 파일 이름을 보여 줬지만 알림은 파일 이름을 제목으로 쓴 적이 없다 —
    따옴표가 깨진 제목은 빈 줄로 나가던 것을 '(제목을 읽지 못했습니다 …)' 로 바꿨고, 여는 울타리가 깨진 글(`------`)은 지금도 알림이 가지 않는다(아래 시험이 현재 동작을 고정한다)."""
    BROKEN_KR = ('---\nlayout: post\ntitle: ""너에게 무엇이 중요한지 결정하는 것": 우주 공학 현장에서 멘토링이 갖는 의미"\ncategory: "과학·환경"\ntags:\n  - 멘토링\n'
                 'lang: ko\nsource_name: "NASA"\n---\n\n본문입니다.\n')
    KR_PATH = "_posts/과학·환경/2026-10-28-KR-111851.md"
    EN_PATH = "_posts/Science & Environment/2026-10-28-EN-111851.md"

    def setUp(self):
        super().setUp()
        self.root = nh.make_root(self.tmp / "site")

    def announce(self, files):
        code, lines, net = self.run_cli("chance-published", "--commit", "HEAD", root=self.root, runner=FakeGit.adding(files))
        return code, lines, net

    def good_en(self):
        return nh.post_text('"You Decide What’s Important": How Mentorship Shapes Aerospace Engineering Talent', "en", "Science & Environment", "NASA")

    def test_a_json_escaped_title_with_quotes_is_read_whole(self):
        front = notify.parse_front_matter(self.good_en())
        self.assertEqual(front["title"], '"You Decide What’s Important": How Mentorship Shapes Aerospace Engineering Talent')
        _, _, net = self.announce({self.EN_PATH: self.good_en()})
        self.assertIn('"You Decide What’s Important": How Mentorship Shapes Aerospace Engineering Talent', net.bodies()[0]["text"])      # 알림은 HTML 이라도 따옴표는 이스케이프하지 않는다(escape_html quote=False)

    def test_a_title_whose_inner_quotes_are_not_escaped_is_shown_as_unreadable_and_never_as_a_file_name(self):
        self.assertEqual(notify.parse_front_matter(self.BROKEN_KR)["title"], "")      # 첫 따옴표 쌍만 읽혀 빈 글자가 된다
        code, lines, net = self.announce({self.KR_PATH: self.BROKEN_KR, self.EN_PATH: self.good_en()})
        self.assertEqual((code, net.calls), (0, 1))
        text = net.bodies()[0]["text"]
        self.assertIn(chr(0x1F1F0) + chr(0x1F1F7) + " " + notify.UNREADABLE_TITLE, text)
        title_lines = [line for line in text.split("\n") if line[:1] in (chr(0x1F1F0), chr(0x1F1FA))]      # 국기로 시작하는 제목 줄(주소 줄에는 글 주소가 있어 슬러그가 보인다)
        self.assertEqual(len(title_lines), 2)
        for line in title_lines:
            for forbidden in ("111851", "2026-10-28", ".md", "Kr "):
                self.assertNotIn(forbidden, line)

    def test_a_title_that_cannot_be_read_or_is_blank_gets_the_same_placeholder(self):
        for title_line in ('title: "닫는 따옴표 없음', "title: [a, b]", 'title: ""', 'title: "   "', "title:"):
            with self.subTest(title_line=title_line):
                text = f'---\nlayout: post\n{title_line}\ncategory: "x"\nlang: ko\nsource_name: "NASA"\n---\n\n본문\n'
                _, _, net = self.announce({self.KR_PATH: text})
                self.assertIn(notify.UNREADABLE_TITLE, net.bodies()[0]["text"])

    def test_a_readable_title_never_gets_the_placeholder(self):
        _, _, net = self.announce(nh.pair_files())
        self.assertNotIn(notify.UNREADABLE_TITLE, net.bodies()[0]["text"])
        self.assertIn(chr(0x1F1F0) + chr(0x1F1F7) + " " + nh.KR_TITLE + "\n", net.bodies()[0]["text"])

    def test_a_post_whose_opening_fence_is_broken_is_not_announced_at_all(self):
        """현재 한계를 고정한다: `------` 로 시작하는 글은 머리말을 읽을 수 없어(`{}`) 알림이 가지 않는다. 생성기가 그런 글을 더는 만들지 않게 막았다(D-80)."""
        broken = self.BROKEN_KR.replace("---\nlayout", "------\nlayout", 1)
        self.assertEqual(notify.parse_front_matter(broken), {})
        code, lines, net = self.announce({self.KR_PATH: broken})
        self.assertEqual((code, net.calls), (0, 0))
        self.assertEqual(lines, ["텔레그램 알림: 이 커밋에 새로 공개되는 글이 없어 보내지 않았습니다"])


class StatusCommandTest(CliCase):
    def run_status(self, environ, with_files=True):
        summary, output = self.tmp / f"summary{next(self.counter)}.md", self.tmp / f"output{next(self.counter)}.txt"
        env = dict(environ)
        if with_files:
            env.update(GITHUB_STEP_SUMMARY=str(summary), GITHUB_OUTPUT=str(output))
        code, lines, net = self.run_cli("status", environ=env)
        read = lambda path: path.read_text(encoding="utf-8") if path.exists() else ""  # noqa: E731
        return code, lines, read(summary), read(output), net

    def test_both_registered(self):
        code, lines, summary, output, net = self.run_status(ENV)
        self.assertEqual((code, net.calls), (0, 0))
        self.assertEqual(lines, ["TELEGRAM_BOT_TOKEN: 등록됨", "TELEGRAM_CHAT_ID: 등록됨"])
        self.assertIn("| `TELEGRAM_BOT_TOKEN` | 등록됨 |", summary)
        self.assertIn("| `TELEGRAM_CHAT_ID` | 등록됨 |", summary)
        self.assertEqual(output, "ready=true\n")
        self.assertEqual(leaks(*lines, summary, output), [])

    def test_one_or_both_missing(self):
        for env, expected in (({}, ("없음", "없음")), ({"TELEGRAM_BOT_TOKEN": TOKEN}, ("등록됨", "없음")), ({"TELEGRAM_CHAT_ID": CHAT}, ("없음", "등록됨")),
                              ({"TELEGRAM_BOT_TOKEN": "  ", "TELEGRAM_CHAT_ID": CHAT}, ("없음", "등록됨"))):
            with self.subTest(env=sorted(env)):
                code, lines, summary, output, _ = self.run_status(env)
                self.assertEqual(lines, [f"TELEGRAM_BOT_TOKEN: {expected[0]}", f"TELEGRAM_CHAT_ID: {expected[1]}"])
                self.assertEqual(output, "ready=false\n")
                self.assertIn("시험 메시지를 보내지 않습니다", summary)
                self.assertEqual(leaks(*lines, summary, output), [])

    def test_the_status_never_reveals_length_prefix_or_shape(self):
        for token in (TOKEN, "x", "bot" + TOKEN, TOKEN + "x" * 50):
            code, lines, summary, output, _ = self.run_status({"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": CHAT})
            self.assertEqual((lines, output), (["TELEGRAM_BOT_TOKEN: 등록됨", "TELEGRAM_CHAT_ID: 등록됨"], "ready=true\n"))
            text = "\n".join(lines) + summary + output
            self.assertEqual([ch for ch in text if ch.isdigit()], [])                       # 길이·숫자 어떤 것도 나오지 않는다
            self.assertNotIn(token[:3], text.replace("TELEGRAM", "").replace("텔레그램", ""))

    def test_without_the_actions_files_it_only_prints(self):
        code, lines, summary, output, _ = self.run_status(ENV, with_files=False)
        self.assertEqual((code, len(lines), summary, output), (0, 2, "", ""))

    def test_unwritable_files_do_not_fail_the_step(self):
        directory = self.tmp / "dir"
        directory.mkdir()
        code, lines, net = self.run_cli("status", environ=dict(ENV, GITHUB_STEP_SUMMARY=str(directory), GITHUB_OUTPUT=str(directory)))
        self.assertEqual(code, 0)
        self.assertTrue(any("실행 요약 쓰기 실패(" in line for line in lines))
        self.assertTrue(any("단계 출력 쓰기 실패(" in line for line in lines))
        self.assertEqual(leaks(*lines), [])


class LeakShapes:
    """test 명령이 요약에 쓰는 글에서 값이 새는지 보는 실패 모양들(test_notify.LeakTest 와 같은 모양)."""

    @staticmethod
    def scenarios():
        import test_notify
        return {**test_notify.LeakTest().scenarios(), "RemoteDisconnected": http.client.RemoteDisconnected(f"closed {nh.SEND_URL}"),
                "timeout 에 주소": socket.timeout(f"timed out {nh.SEND_URL}")}


class TestCommandTest(CliCase):
    def run_test_command(self, outcome=None, environ=None, with_summary=True):
        summary = self.tmp / f"summary{next(self.counter)}.md"
        env = dict(ENV if environ is None else environ)
        if with_summary:
            env["GITHUB_STEP_SUMMARY"] = str(summary)
        net = FakeNet(outcome) if outcome is not None else FakeNet()
        code, lines, net = self.run_cli("test", environ=env, net=net)
        return code, lines, (summary.read_text(encoding="utf-8") if summary.exists() else ""), net

    def test_success(self):
        code, lines, summary, net = self.run_test_command()
        self.assertEqual((code, net.calls), (0, 1))
        self.assertEqual(lines, ["텔레그램 알림 시험: 성공 — 휴대폰에서 '알림 연결 확인' 메시지를 확인하세요"])
        self.assertIn("결과: **성공**", summary)
        self.assertIn("알림 연결 확인", net.bodies()[0]["text"])
        self.assertEqual(leaks(*lines, summary), [])

    def test_without_secrets_it_is_a_quiet_success(self):
        code, lines, summary, net = self.run_test_command(environ={})
        self.assertEqual((code, lines, net.calls), (0, ["텔레그램 알림: 건너뜀(시크릿 없음)"], 0))
        self.assertIn("시크릿 없음", summary)

    FAILURES = (
        ("unauthorized", http_error(401, "Unauthorized"), 401),
        ("chat_not_found", http_error(400, "Bad Request: chat not found"), 400),
        ("forbidden", http_error(403, "Forbidden: bot can't initiate conversation with a user"), 403),
        ("network", urllib.error.URLError("x"), None),
        ("timeout", TimeoutError("x"), None),
        ("rate_limited", http_error(429, "Too Many Requests", retry_after=1), 429),
        ("server_error", http_error(502, "Bad Gateway"), 502),
        ("not_found", http_error(404, "Not Found"), 404),
    )

    def test_each_failure_is_classified_in_the_summary_with_its_remedy(self):
        for reason, outcome, status in self.FAILURES:
            with self.subTest(reason=reason):
                code, lines, summary, _ = self.run_test_command(outcome)
                self.assertEqual(code, 1)
                self.assertEqual(lines[-1], notify.ERROR_LINE)
                self.assertIn("결과: **실패**", summary)
                self.assertIn(f"분류: `{reason}`", summary)
                self.assertIn(notify.REASON_TEXT[reason].replace("`", "'"), summary.replace("`", "'"))
                if status:
                    self.assertIn(f"HTTP {status}", summary)
                self.assertEqual(leaks(*lines, summary), [])

    def test_the_description_telegram_gave_is_markdown_safe_in_the_summary(self):
        """독립 검증 X11: 텔레그램이 준 설명은 외부 글이다 — 실행 요약(마크다운)에는 표·링크·HTML 문법 문자를 바꿔서 싣는다."""
        code, lines, summary, _ = self.run_test_command(http_error(400, "Bad Request: <b>x</b> | [click](https://evil.example)"))
        self.assertEqual(code, 1)
        line = next(item for item in summary.splitlines() if item.startswith("- 텔레그램이 준 설명:"))
        for raw in ("<b>", "|", "[click]"):
            self.assertNotIn(raw, line)
        for safe in ("&lt;b&gt;", "&#124;", "&#91;click&#93;"):
            self.assertIn(safe, line)

    def test_failure_shapes_that_carry_the_request_address_do_not_leak_into_the_summary(self):
        for name, outcome in LeakShapes.scenarios().items():
            with self.subTest(name=name):
                code, lines, summary, _ = self.run_test_command(outcome)
                self.assertEqual(leaks(*lines, summary), [], name)
                self.assertEqual(code, 1, name)

    def test_a_malformed_token_fails_before_any_request_with_a_clear_reason(self):
        code, lines, summary, net = self.run_test_command(environ={"TELEGRAM_BOT_TOKEN": "bot" + TOKEN, "TELEGRAM_CHAT_ID": CHAT})
        self.assertEqual((code, net.calls), (1, 0))
        self.assertIn("분류: `invalid_token`", summary)
        self.assertEqual(leaks(*lines, summary), [])

    def test_the_summary_does_not_need_the_actions_file(self):
        code, lines, summary, _ = self.run_test_command(environ=ENV, with_summary=False)
        self.assertEqual((code, summary), (0, ""))

    def test_the_test_time_is_shown_in_korean_time(self):
        code, lines, net = self.run_cli("test", now=datetime(2026, 1, 2, 15, 30, tzinfo=timezone.utc))
        self.assertIn("시험 시각: 2026-01-03 00:30 KST", net.bodies()[0]["text"])


class ParserTest(unittest.TestCase):
    def test_no_option_accepts_external_values(self):
        parser = notify.build_parser()
        subparsers = [action for action in parser._actions if action.dest == "event"][0].choices
        self.assertEqual(sorted(subparsers), ["chance-published", "status", "test"])
        options = {name: sorted(opt for action in sub._actions for opt in action.option_strings if opt not in ("-h", "--help"))
                   for name, sub in subparsers.items()}
        self.assertEqual(options, {"chance-published": ["--commit"], "status": [], "test": []})

    def test_usage_errors_exit_two(self):
        for argv in ([], ["nope"], ["test", "--commit", "HEAD"], ["status", "--token", "x"], ["chance-published", "--title", "x"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as caught:
                with contextlib.redirect_stderr(io.StringIO()):
                    notify.main(argv, environ=dict(ENV), out=lambda line: None)
            self.assertEqual(caught.exception.code, 2)

    def test_a_value_passed_by_mistake_is_never_echoed_in_the_usage_error(self):
        """argparse 의 기본 오류는 틀린 인자를 그대로 메시지에 싣는다. 실수로 명령 줄에 토큰·채팅 ID 를 넘겨도 오류 출력에 나오지 않는다."""
        for argv in (["status", "--token", TOKEN], ["test", TOKEN], ["chance-published", f"--chat={CHAT}"], [TOKEN], ["--bot", TOKEN, "test"],
                     ["chance-published", "--commit", TOKEN, "--extra", CHAT]):
            with self.subTest(argv=len(argv)):
                err = io.StringIO()
                with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(err):
                    notify.main(argv, environ=dict(ENV), out=lambda line: None)
                self.assertEqual(caught.exception.code, 2)
                self.assertEqual(leaks(err.getvalue()), [])
                self.assertIn(notify.USAGE_ERROR_LINE, err.getvalue())
                self.assertIn("usage:", err.getvalue())

    def test_unexpected_errors_in_status_and_test_commands_stay_inside_the_command(self):
        for argv, expected_code, patched in ((["status"], 0, "run_status"), (["test"], 1, "run_test")):
            lines = []
            with mock.patch.object(notify, patched, side_effect=RuntimeError(nh.SEND_URL)):
                code = notify.main(argv, environ=dict(ENV), out=lines.append, budget=notify.Budget())
            self.assertEqual(code, expected_code)
            self.assertIn("RuntimeError", lines[0])
            self.assertEqual(leaks(*lines), [])

    def test_the_module_runs_with_python_dash_m_and_prints_the_skip_line(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith("TELEGRAM_")}
        done = subprocess.run([sys.executable, "-X", "utf8", "-m", "pipeline.notify", "chance-published", "--commit", "HEAD"], cwd=str(_bootstrap.ROOT),
                              capture_output=True, env=env, timeout=60)
        self.assertEqual((done.returncode, done.stdout.decode("utf-8").strip(), done.stderr), (0, "텔레그램 알림: 건너뜀(시크릿 없음)", b""))

    def test_a_process_with_a_malformed_token_makes_no_network_call_and_prints_no_value(self):
        env = dict(os.environ, TELEGRAM_BOT_TOKEN="bot" + TOKEN, TELEGRAM_CHAT_ID=CHAT)
        done = subprocess.run([sys.executable, "-X", "utf8", "-m", "pipeline.notify", "test"], cwd=str(_bootstrap.ROOT), capture_output=True, env=env, timeout=60)
        output = done.stdout.decode("utf-8") + done.stderr.decode("utf-8")
        self.assertEqual(done.returncode, 1)
        self.assertIn("토큰 모양이 올바르지 않습니다", output)
        self.assertEqual(leaks(output), [])


if __name__ == "__main__":
    unittest.main()
