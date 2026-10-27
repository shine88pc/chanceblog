"""초안 패키지 러너 경로 시험(pipeline/run.py, mode package · platform tistory·naver).

가짜 LLM(스텁)과 가짜 게시자(어댑터 자리) 또는 진짜 어댑터 + 가짜 GitHub(urllib 오프너)로 흐름을 증명한다: 이슈 생성 1회, 같은 날 재실행 멱등,
적체 건너뜀, API 오류의 종료 코드·고정 문장·비밀 가림, 연습 실행의 호출 0회, Blogger 경로를 쓰지 않음. 네트워크·실제 시크릿 없음.
"""
import json
import random
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from package_helpers import (KST_DAY, NOW, REPO, FakeGitHub, FakePackagePublisher, fake_token, make_package_root, package_env)
from pipeline import health, registry
from pipeline import run as run_mod
from pipeline.llm import LLMError
from pipeline.publishers import issue_package as ip
from pipeline.publishers.base import PublishError, PublishResult
from pipeline.stubs import stub_llm

REAL = _bootstrap.ROOT
_FAKE = object()
LABEL = {"tistory": "티스토리", "naver": "네이버"}


def spy_llm():
    calls = []

    def llm(prompt):
        calls.append(prompt)
        return stub_llm(prompt)
    llm.calls = calls
    return llm


class PackageRunBase(unittest.TestCase):
    key = "tistory_test"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = make_package_root(self.tmp / "repo")
        self.summary_path = self.tmp / "summary.md"

    def env(self, **extra):
        return {"GITHUB_STEP_SUMMARY": str(self.summary_path), **package_env(**extra)}

    def go(self, env=None, llm=stub_llm, publisher=_FAKE, extra=(), now=NOW, seed=1, root=None, key=None):
        """publisher: 생략하면 가짜 게시자(적체 0), None 이면 러너가 기본 게시자를 만든다(진짜 어댑터 — 시험은 mock 으로 가짜 GitHub 를 끼운다)."""
        out = []
        if publisher is _FAKE:
            publisher = FakePackagePublisher()
        factory = (lambda blog, environ: publisher) if publisher is not None else None
        code = run_mod.run(["--blog", key or self.key, "--root", str(root or self.root), *extra], environ=self.env() if env is None else env, now=now, llm=llm,
                           publisher_factory=factory, rng=random.Random(seed), out=out.append)
        return code, "\n".join(out)

    def real_adapter_factory(self, github, token=None):
        return lambda blog, environ: ip.IssuePackagePublisher(environ["GITHUB_REPOSITORY"], token or environ["GITHUB_TOKEN"], opener=github, sleep=lambda s: None)

    def history(self, key=None):
        path = self.root / f"{(key or self.key).split('_')[0]}_test_history.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def drafts(self, key=None):
        folder = self.root / f"_{(key or self.key).split('_')[0]}_test_drafts"
        return sorted(folder.glob("*.md")) if folder.exists() else []

    def summary(self):
        return self.summary_path.read_text(encoding="utf-8") if self.summary_path.exists() else ""

    def annotations(self, out):
        return [line for line in out.splitlines() if line.lstrip().startswith(("::", "##["))]


class FlowTest(PackageRunBase):
    def test_a_run_creates_one_draft_issue_and_records_package_issued(self):
        for platform in ("tistory", "naver"):
            with self.subTest(platform):
                key = f"{platform}_test"
                pub = FakePackagePublisher()
                code, out = self.go(env=self.env(GITHUB_RUN_ID="4242"), publisher=pub, key=key)
                self.assertEqual(code, 0, out)
                self.assertEqual(pub.counted, [LABEL[platform]])
                self.assertEqual(len(pub.created), 1)
                draft = pub.created[0]
                entry = self.history(key)[-1]
                self.assertEqual((draft.blog_key, draft.platform, draft.channel_label, draft.date), (key, platform, LABEL[platform], KST_DAY))
                self.assertEqual((draft.title, draft.tags), (entry["title"], entry["labels"]))
                self.assertIn("AI의 도움", draft.html)                       # 면책·AI 사용 문구가 붙은 최종 본문이다
                self.assertNotIn("<script", draft.html.lower())
                self.assertFalse(draft.allow_links)
                self.assertEqual(draft.run_url, f"https://github.com/{REPO}/actions/runs/4242")
                self.assertEqual((draft.gate["attempts"], draft.gate["model"]), (1, "stub"))
                self.assertEqual(draft.gate["min_chars"], 900)
                self.assertGreater(draft.gate["chars"], 900)
                self.assertEqual((entry["status"], entry["url"], entry["post_id"]), ("package_issued", f"https://github.com/{REPO}/issues/1", "1"))
                self.assertEqual((entry["blog"], entry["date"], entry["v"], entry["topic_source"]), (key, KST_DAY, 1, "seed"))
                self.assertEqual(len(self.drafts(key)), 1)
                self.assertIn("status: package_issued", self.drafts(key)[0].read_text(encoding="utf-8"))
                self.assertIn(f"https://github.com/{REPO}/issues/1", out)
                self.assertIn("**package_issued**", self.summary())

    def test_the_summary_tells_the_operator_what_to_do_and_that_nothing_was_published(self):
        self.go()
        text = self.summary()
        self.assertEqual(text.splitlines()[0], f"### {self.key}")
        self.assertIn("공개된 글이 아닙니다", text)
        self.assertIn("티스토리에 직접 발행하고 이슈를 닫으세요", text)
        self.assertIn("docs/ACTIONS_GUIDE.md 3-17", text)
        self.summary_path.unlink()
        self.go(key="naver_test")
        self.assertIn("네이버 블로그에 직접 발행하고 이슈를 닫으세요", self.summary())

    def test_blogger_machinery_is_never_touched(self):
        with mock.patch("pipeline.publishers.blogger.BloggerPublisher", side_effect=AssertionError("Blogger 게시자를 만들면 안 된다")), \
                mock.patch.object(run_mod, "auth_check", side_effect=AssertionError("Blogger 인증 점검을 하면 안 된다")):
            code, out = self.go()
        self.assertEqual(code, 0, out)
        self.assertNotIn("Blogger", out)
        self.assertNotIn("인증 점검", out)

    def test_only_the_llm_key_and_the_github_token_are_needed(self):
        code, out = self.go(env={"GITHUB_STEP_SUMMARY": str(self.summary_path), "GEMINI_API_KEY": "k", "GITHUB_TOKEN": fake_token(), "GITHUB_REPOSITORY": REPO})
        self.assertEqual(code, 0, out)
        workflow_style = {"GITHUB_STEP_SUMMARY": str(self.summary_path), "PIPELINE_SECRET_LLM_API_KEY": "k", "GITHUB_TOKEN": fake_token(), "GITHUB_REPOSITORY": REPO}
        self.summary_path.unlink()
        (self.root / "tistory_test_history.json").unlink()
        code, out = self.go(env=workflow_style)                       # 워크플로가 넘기는 이름만으로도 돈다
        self.assertEqual(code, 0, out)

    def test_the_daily_cap_blocks_a_second_run_the_same_day_without_any_api_call(self):
        self.go()
        pub, llm = FakePackagePublisher(), spy_llm()
        code, out = self.go(publisher=pub, llm=llm)
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=DAILY_CAP", out)
        self.assertIn("package_issued", out)                              # 어떤 기록이 상한을 채웠는지 보인다
        self.assertEqual((llm.calls, pub.counted, pub.created), ([], [], []))
        self.assertEqual(len(self.history()), 1)

    def test_the_next_day_runs_again_with_a_different_topic(self):
        self.go()
        later = datetime(2026, 10, 22, 5, 20, tzinfo=timezone.utc)
        pub = FakePackagePublisher()
        self.go(now=later, publisher=pub)
        self.assertEqual([e["date"] for e in self.history()], ["2026-10-21", "2026-10-22"])
        self.assertNotEqual(self.history()[0]["topic"], self.history()[1]["topic"])
        self.assertEqual(len(pub.created), 1)

    def test_a_manual_topic_bypasses_the_daily_cap_but_not_the_backlog(self):
        self.go()
        pub = FakePackagePublisher()
        code, out = self.go(publisher=pub, extra=["--topic", "수동으로 지정한 오늘의 생활 습관 주제"])
        self.assertEqual(code, 0, out)
        self.assertEqual((len(pub.created), self.history()[-1]["topic_source"]), (1, "override"))
        pub = FakePackagePublisher(open_drafts=3)
        code, out = self.go(publisher=pub, extra=["--topic", "또 다른 수동 생활 습관 주제입니다"])
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=PACKAGE_BACKLOG", out)
        self.assertEqual(pub.created, [])

    def test_a_rejected_post_makes_no_issue(self):
        def short(prompt):
            return "제목: 충분히 긴 제목입니다 정말로\n라벨: 가\n내용:\n<p>너무 짧음</p>", "m"
        pub = FakePackagePublisher()
        code, out = self.go(llm=short, publisher=pub)
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=GATE_REJECTED", out)
        self.assertEqual(pub.created, [])
        self.assertEqual((self.history()[-1]["status"], self.history()[-1]["attempts"]), ("rejected", 3))
        self.assertEqual(self.drafts(), [])
        self.assertEqual(len(pub.counted), 1)                              # 적체 점검은 글을 만들기 전에 이미 했다

    def test_an_llm_failure_is_an_infra_failure_and_makes_no_issue(self):
        def down(prompt):
            raise LLMError("all models failed")
        pub = FakePackagePublisher()
        code, out = self.go(llm=down, publisher=pub)
        self.assertEqual(code, 1)
        self.assertIn("[SKIP] code=LLM_FAILED", out)
        self.assertEqual((pub.created, self.history()[-1]["status"]), ([], "llm_failed"))

    def test_the_gate_info_reports_the_attempt_that_passed_and_the_sanitizing(self):
        calls = []

        def flaky(prompt):
            calls.append(prompt)
            text, model = stub_llm(prompt)
            if len(calls) == 1:
                return text.replace("<p>처음부터", "<p>이 방법으로 완치됩니다. 처음부터"), model                # 금지 표현 → 탈락
            return text.replace("<h3>1.", "<script>x()</script><h3>1."), "stub-2"                      # 통과하지만 정화로 script 블록이 지워진다
        pub = FakePackagePublisher()
        self.go(llm=flaky, publisher=pub)
        gate = pub.created[0].gate
        self.assertEqual((gate["attempts"], gate["model"]), (2, "stub-2"))
        self.assertEqual(gate["removed"], {"dropped_blocks": 1})
        self.assertTrue(any("SANITIZED" in warning for warning in gate["warnings"]))
        self.assertNotIn("<script", pub.created[0].html)

    def test_rerunning_after_a_lost_history_file_does_not_make_a_second_issue(self):
        """이력 파일이 사라진 날 같은 글이 다시 만들어져도 숨은 표지로 같은 이슈를 찾아 쓴다(진짜 어댑터 + 가짜 GitHub)."""
        github = FakeGitHub()
        factory = self.real_adapter_factory(github)
        out1, out2 = [], []
        for out in (out1, out2):
            code = run_mod.run(["--blog", self.key, "--root", str(self.root)], environ=self.env(), now=NOW, llm=stub_llm, publisher_factory=factory,
                               rng=random.Random(1), out=out.append)
            self.assertEqual(code, 0, out)
            if out is out1:
                (self.root / "tistory_test_history.json").unlink()                # 이력이 사라졌다
        self.assertEqual(len(github.issues), 1)
        self.assertEqual(len(github.calls("POST", r"^/issues$")), 1)
        self.assertTrue(any("이미 있어 새로 만들지 않았습니다" in line for line in out2))
        self.assertEqual([e["post_id"] for e in self.history()], ["1"])
        self.assertEqual(self.history()[-1]["status"], "package_issued")


class EndToEndTest(PackageRunBase):
    def test_a_real_run_through_the_real_adapter_and_a_fake_github(self):
        github = FakeGitHub()
        token = fake_token()
        out = []
        code = run_mod.run(["--blog", self.key, "--root", str(self.root)], environ=self.env(GITHUB_RUN_ID="77"), now=NOW, llm=stub_llm,
                           publisher_factory=self.real_adapter_factory(github, token), rng=random.Random(1), out=out.append)
        text = "\n".join(out)
        self.assertEqual(code, 0, text)
        self.assertEqual(len(github.issues), 1)
        issue = github.issues[0]
        self.assertTrue(issue["title"].startswith("[초안][티스토리] "))
        self.assertEqual([label["name"] for label in issue["labels"]], ["초안", "채널:티스토리"])
        marker = re.match(r"^<!-- draft-id: (tistory_test-2026-10-21-[0-9a-f]{12}) -->$", issue["body"].split("\n", 1)[0])
        self.assertIsNotNone(marker)                                       # 본문 첫 줄이 숨은 표지다
        self.assertIn(f"https://github.com/{REPO}/actions/runs/77", issue["body"])
        # 첫 호출은 적체 점검(열린 초안 수), 그다음 같은 표지 찾기, 라벨, 이슈 만들기 순서다
        self.assertEqual([(r["method"], r["path"], r["query"].get("state")) for r in github.requests[:2]], [("GET", "/issues", "open"), ("GET", "/issues", "all")])
        self.assertEqual(github.requests[-1]["method"] + " " + github.requests[-1]["path"], "POST /issues")
        for request in github.requests:
            self.assertEqual(request["headers"]["authorization"], f"Bearer {token}")
        self.assertNotIn(token, text + self.summary() + json.dumps(self.history()) + "".join(p.read_text(encoding="utf-8") for p in self.drafts()))

    def test_hostile_model_output_reaches_the_issue_only_in_a_sanitized_form(self):
        def evil(prompt):
            text, model = stub_llm(prompt)
            text = text.replace("<h3>1.", "<script>steal()</script><img src=x onerror=alert(1)><h3>@octocat #12 1.")
            first = text.split("\n", 1)[0]
            return text.replace(first, "제목: @everyone ::error::위조된 제목 #99 <b>굵게</b> 입니다 충분히 길게"), model
        github = FakeGitHub()
        out = []
        code = run_mod.run(["--blog", self.key, "--root", str(self.root)], environ=self.env(), now=NOW, llm=evil,
                           publisher_factory=self.real_adapter_factory(github), rng=random.Random(1), out=out.append)
        text = "\n".join(out)
        self.assertEqual(code, 0, text)
        issue = github.issues[0]
        body = issue["body"]
        self.assertNotIn("<script", body.lower())
        self.assertNotIn("onerror", body)
        self.assertNotIn("steal()", body)
        self.assertNotRegex(re.sub(r"https?://\S+", "", body), r"(?<![A-Za-z0-9_])@[A-Za-z0-9]")
        self.assertNotRegex(re.sub(r"https?://\S+", "", body), r"#\d")
        self.assertNotRegex(re.sub(r"https?://\S+", "", issue["title"]), r"(?<![A-Za-z0-9_])@[A-Za-z0-9]|#\d")
        self.assertEqual(len(self.annotations(text)), 0, self.annotations(text))                    # 제목에 숨긴 ::error:: 가 로그의 명령이 되지 않았다
        self.assertEqual(self.summary().count("### "), 1)
        self.assertEqual([line for line in self.summary().splitlines() if line.lstrip().startswith("::")], [])

    def test_naver_end_to_end_makes_the_rendered_copy_section(self):
        github = FakeGitHub()
        out = []
        code = run_mod.run(["--blog", "naver_test", "--root", str(self.root)], environ=self.env(), now=NOW, llm=stub_llm,
                           publisher_factory=self.real_adapter_factory(github), rng=random.Random(1), out=out.append)
        self.assertEqual(code, 0, "\n".join(out))
        issue = github.issues[0]
        self.assertEqual([label["name"] for label in issue["labels"]], ["초안", "채널:네이버"])
        self.assertIn("본문 — 서식 있는 글(이 화면에서 복사)", issue["body"])
        self.assertIn("#### 1. 먼저 지금 상태를 가볍게 확인하기", issue["body"])

    def test_the_backlog_counts_the_channels_own_label_through_the_real_adapter(self):
        github = FakeGitHub()
        for _ in range(3):
            github.add_issue(labels=["초안", "채널:네이버"])
        factory = self.real_adapter_factory(github)
        out = []
        code = run_mod.run(["--blog", "tistory_test", "--root", str(self.root)], environ=self.env(), now=NOW, llm=stub_llm,
                           publisher_factory=factory, rng=random.Random(1), out=out.append)
        self.assertEqual(code, 0, "\n".join(out))
        self.assertEqual(len(github.issues), 4)                                # 네이버 초안은 티스토리를 막지 않는다
        out = []
        code = run_mod.run(["--blog", "naver_test", "--root", str(self.root)], environ=self.env(), now=NOW, llm=stub_llm,
                           publisher_factory=factory, rng=random.Random(1), out=out.append)
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=PACKAGE_BACKLOG blog=naver_test open=3 limit=3", "\n".join(out))
        self.assertEqual(len(github.issues), 4)

    def test_the_default_factory_builds_the_issue_adapter_for_these_platforms(self):
        for platform in ("tistory", "naver"):
            blog = registry.get_blog(registry.load_registry(self.root / "pipeline" / "blogs.json"), f"{platform}_test")
            created = run_mod.default_publisher_factory(blog, {"GITHUB_REPOSITORY": REPO, "GITHUB_TOKEN": "tok-1234567"})
            self.assertIsInstance(created, ip.IssuePackagePublisher)
            self.assertEqual(created.repo, REPO)


class BacklogTest(PackageRunBase):
    def test_three_open_drafts_skip_the_run_before_any_llm_call(self):
        pub, llm = FakePackagePublisher(open_drafts=3), spy_llm()
        code, out = self.go(publisher=pub, llm=llm)
        self.assertEqual(code, 0, out)
        self.assertIn("[SKIP] code=PACKAGE_BACKLOG blog=tistory_test open=3 limit=3", out)
        notices = [line for line in self.annotations(out) if line.startswith("::notice::")]
        self.assertEqual(len(notices), 1, out)
        self.assertIn("열린 초안 이슈가 3건(상한 3건)", notices[0])
        self.assertEqual((llm.calls, pub.created, self.history(), self.drafts()), ([], [], [], []))
        self.assertIn("PACKAGE_BACKLOG", self.summary())
        self.assertIn("`채널:티스토리`", self.summary())

    def test_more_than_three_also_skips_and_fewer_than_three_runs(self):
        self.assertIn("PACKAGE_BACKLOG", self.go(publisher=FakePackagePublisher(open_drafts=9))[1])
        pub = FakePackagePublisher(open_drafts=2)
        code, out = self.go(publisher=pub)
        self.assertEqual((code, len(pub.created)), (0, 1))
        self.assertIn("초안 이슈 점검 통과: 열린 초안 2건(상한 3건 미만)", out)

    def test_open_drafts_marked_as_discarded_do_not_block_a_new_draft_with_the_real_adapter(self):
        """폐기 = 라벨 `폐기` 또는 닫기. 라벨만 붙인 열린 이슈 셋은 적체가 아니다(현황판과 같은 규칙) — 진짜 어댑터와 가짜 GitHub 로 끝까지 본다."""
        github = FakeGitHub()
        for _ in range(3):
            github.add_issue(labels=["초안", "채널:티스토리", "폐기"])
        code, out = self.go(publisher=self.real_adapter_factory(github)(None, self.env()))
        self.assertEqual(code, 0, out)
        self.assertNotIn("PACKAGE_BACKLOG", out)
        self.assertIn("열린 초안 0건(상한 3건 미만)", out)
        self.assertEqual(len(github.issues), 4)
        self.assertEqual(self.history()[-1]["status"], "package_issued")
        for _ in range(3):
            github.add_issue(labels=["초안", "채널:티스토리"])                       # 폐기 표시가 없는 열린 초안 셋이면 막는다
        (self.root / "tistory_test_history.json").unlink()                              # 같은 날 상한을 지워 적체 점검까지 가게 한다
        code, out = self.go(publisher=self.real_adapter_factory(github)(None, self.env()))
        self.assertEqual(code, 0, out)
        self.assertIn("[SKIP] code=PACKAGE_BACKLOG blog=tistory_test open=4 limit=3", out)       # 방금 만든 초안 하나 + 새로 만든 셋(폐기 셋은 제외)
        self.assertEqual(len(github.issues), 7)

    def test_the_daily_cap_is_reported_before_the_backlog_and_costs_no_api_call(self):
        self.go()
        pub = FakePackagePublisher(open_drafts=5)
        code, out = self.go(publisher=pub)
        self.assertIn("[SKIP] code=DAILY_CAP", out)
        self.assertNotIn("PACKAGE_BACKLOG", out)
        self.assertEqual(pub.counted, [])


class DryRunTest(PackageRunBase):
    def dry_env(self):
        return {"GITHUB_STEP_SUMMARY": str(self.summary_path)}              # 토큰도 저장소도 없다

    def test_a_dry_run_builds_the_issue_but_makes_no_github_call_and_writes_nothing_but_the_summary(self):
        def forbidden(blog, environ):
            raise AssertionError("연습 실행은 게시자를 만들지 않는다")
        before = {p for p in self.root.rglob("*")}
        out = []
        code = run_mod.run(["--blog", self.key, "--root", str(self.root), "--dry-run"], environ=self.dry_env(), now=NOW, llm=stub_llm,
                           publisher_factory=forbidden, rng=random.Random(1), out=out.append)
        text = "\n".join(out)
        self.assertEqual(code, 0, text)
        self.assertEqual({p for p in self.root.rglob("*")}, before)           # 이력·초안 사본 없음
        self.assertIn("[DRY_RUN] 게이트 통과 — 이슈·저장 없이 종료합니다(GitHub API 호출 0회).", text)
        self.assertIn("이슈 제목: [초안][티스토리] ", text)
        self.assertIn("이슈 라벨: 초안, 채널:티스토리", text)
        self.assertNotIn("draft-id", text)                                     # 본문은 로그가 아니라 실행 요약에만 있다
        self.assertNotIn("복사용 제목", text)
        summary = self.summary()
        self.assertIn("**DRY_RUN**", summary)
        self.assertIn("GitHub API 호출: 0회", summary)
        self.assertIn("<!-- draft-id: tistory_test-2026-10-21-", summary)
        self.assertIn("## 1. 복사용 제목", summary)
        self.assertIn("## 7. 발행 체크리스트", summary)
        self.assertIn("- [ ] 발행 후 주소 기록하고 이 이슈 닫기", summary)

    def test_the_dry_run_summary_shows_the_issue_title_as_plain_text_and_not_inside_a_code_span(self):
        """실행 요약은 마크다운이다. md_cell 이 바꾼 `&#91;` 같은 표기는 코드 스팬(백틱) 안에서는 글자 그대로 보이므로 백틱 밖에 둔다."""
        code, out = self.go(env={**self.dry_env()}, extra=["--dry-run"])
        self.assertEqual(code, 0, out)
        line = next(line for line in self.summary().splitlines() if line.startswith("- 이슈 제목:"))
        self.assertTrue(line.startswith("- 이슈 제목: &#91;초안&#93;&#91;티스토리&#93; "), line)
        self.assertNotIn("`", line)

    def test_a_dry_run_with_the_real_adapter_still_makes_no_request(self):
        github = FakeGitHub()
        out = []
        code = run_mod.run(["--blog", self.key, "--root", str(self.root)], environ={**self.env(), "DRY_RUN": "true"}, now=NOW, llm=stub_llm,
                           publisher_factory=self.real_adapter_factory(github), rng=random.Random(1), out=out.append)
        self.assertEqual(code, 0, "\n".join(out))
        self.assertEqual((github.requests, github.issues), ([], []))
        self.assertEqual(self.history(), [])

    def test_a_dry_run_with_no_llm_uses_the_fake_ai_and_says_so(self):
        out = []
        code = run_mod.run(["--blog", self.key, "--root", str(self.root), "--dry-run"], environ=self.dry_env(), now=NOW, llm=None,
                           rng=random.Random(1), out=out.append)
        self.assertEqual(code, 0, "\n".join(out))
        self.assertIn("Gemini 호출: 0회(가짜 AI 응답 사용)", self.summary())

    def test_the_dry_run_body_is_exactly_what_a_real_run_posts(self):
        github = FakeGitHub()
        out = []
        env = self.env(GITHUB_RUN_ID="9")
        run_mod.run(["--blog", self.key, "--root", str(self.root)], environ=env, now=NOW, llm=stub_llm, publisher_factory=self.real_adapter_factory(github),
                    rng=random.Random(1), out=out.append)
        posted = github.issues[0]["body"]
        self.summary_path.unlink()
        (self.root / "tistory_test_history.json").unlink()                            # 연습도 하루 상한을 지키므로 같은 날 이력을 지워야 같은 글을 만든다
        run_mod.run(["--blog", self.key, "--root", str(self.root), "--dry-run"], environ=env, now=NOW, llm=stub_llm, rng=random.Random(1), out=out.append)
        self.assertIn(posted, self.summary())
        self.assertEqual(self.summary().count(posted), 1)

    def test_a_dry_run_ignores_the_daily_cap_state_of_the_history_but_never_writes_it(self):
        self.go()
        history = (self.root / "tistory_test_history.json").read_text(encoding="utf-8")
        out = []
        run_mod.run(["--blog", self.key, "--root", str(self.root), "--dry-run"], environ=self.dry_env(), now=NOW, llm=stub_llm, rng=random.Random(1), out=out.append)
        self.assertIn("DAILY_CAP", "\n".join(out))                              # 이력은 그대로 읽는다(연습도 상한을 지킨다)
        self.assertEqual((self.root / "tistory_test_history.json").read_text(encoding="utf-8"), history)

    def test_a_body_that_cannot_fit_fails_the_dry_run_the_same_way_as_a_real_run(self):
        """게이트가 길이를 막으므로 실제로는 거의 없지만(프로필 length.max_chars), 안전 한도를 줄여 같은 설정 오류로 끝나는지 본다."""
        github = FakeGitHub()
        with mock.patch.object(ip, "BODY_BUDGET", 600):
            code, out = self.go(env={**self.dry_env()}, extra=["--dry-run"])
            self.assertEqual(code, 2, out)
            self.assertIn("[SKIP] code=PACKAGE_FAILED blog=tistory_test stage=build reason=too_long exit=2", out)
            self.assertEqual(self.history(), [])                                       # 연습은 이력을 쓰지 않는다
            real_code, real_out = self.go(publisher=self.real_adapter_factory(github)(None, self.env()))
            self.assertEqual(real_code, 2, real_out)
            self.assertIn("stage=issue reason=too_long exit=2", real_out)
        self.assertEqual(self.history()[-1]["status"], "publish_failed")
        self.assertEqual(github.issues, [])                                              # 잘린 글을 올리지 않는다
        self.assertEqual(len(self.drafts()), 1)                                          # 만든 글은 저장소 사본으로 남는다


class ConfigTest(PackageRunBase):
    def test_the_run_link_is_built_only_from_a_well_formed_repository_and_a_numeric_run_id(self):
        """실행 주소는 이슈 본문의 링크가 된다. 저장소 이름이 `소유자/이름` 모양이고 실행 번호가 숫자일 때만 만들고, 아니면 링크 없이 둔다(어댑터도 한 번 더 본다)."""
        for repo, run_id, expected in ((REPO, "4242", f"https://github.com/{REPO}/actions/runs/4242"), (REPO, " 4242 ", f"https://github.com/{REPO}/actions/runs/4242"),
                                       (REPO, "12a", ""), (REPO, "1 2", ""), (REPO, "../x", ""), (REPO, "", ""), (REPO, None, ""),
                                       ("not a repo", "1", ""), ("a/b/c", "1", ""), ("", "1", ""), (None, "1", "")):
            with self.subTest(repo=repo, run_id=run_id):
                self.assertEqual(run_mod._run_url({"GITHUB_REPOSITORY": repo, "GITHUB_RUN_ID": run_id}), expected)

    def test_missing_github_token_or_repository_stops_before_gemini_with_names_only(self):
        for missing, expect in ((("GITHUB_TOKEN",), "missing=GITHUB_TOKEN"), (("GITHUB_REPOSITORY",), "missing=GITHUB_REPOSITORY"),
                                (("GITHUB_TOKEN", "GITHUB_REPOSITORY"), "missing=GITHUB_TOKEN,GITHUB_REPOSITORY")):
            with self.subTest(missing):
                env = {k: v for k, v in self.env().items() if k not in missing}
                llm, pub = spy_llm(), FakePackagePublisher()
                code, out = self.go(env=env, llm=llm, publisher=pub)
                self.assertEqual(code, 2, out)
                self.assertIn(f"[SKIP] code=SECRETS_MISSING blog=tistory_test {expect}", out)
                self.assertEqual((llm.calls, pub.counted, pub.created, self.history()), ([], [], [], []))
                errors = [line for line in out.splitlines() if line.startswith("::error::")]
                self.assertEqual(len(errors), 1)
                self.assertNotIn(fake_token(), out + self.summary())
                self.assertIn("SECRETS_MISSING", self.summary())
                self.summary_path.unlink(missing_ok=True)

    def test_an_empty_token_counts_as_missing(self):
        code, out = self.go(env=self.env(GITHUB_TOKEN="   "))
        self.assertEqual(code, 2)
        self.assertIn("missing=GITHUB_TOKEN", out)

    def test_a_missing_llm_key_is_a_config_error_naming_the_secret(self):
        out = []
        code = run_mod.run(["--blog", self.key, "--root", str(self.root)], environ={"GITHUB_TOKEN": fake_token(), "GITHUB_REPOSITORY": REPO,
                           "GITHUB_STEP_SUMMARY": str(self.summary_path)}, now=NOW, llm=None, rng=random.Random(1), out=out.append)
        self.assertEqual(code, 2)
        self.assertIn("GEMINI_API_KEY", "\n".join(out))
        self.assertIn("[SKIP] code=SECRETS_MISSING", "\n".join(out))

    def test_the_blogger_publish_switch_is_refused_on_these_channels(self):
        for label, extra, env in (("BLOGGER_PUBLISH=publish", [], {"BLOGGER_PUBLISH": "publish"}), ("BLOGGER_PUBLISH=draft", [], {"BLOGGER_PUBLISH": "draft"}),
                                  ("BLOGGER_PUBLISH=off", [], {"BLOGGER_PUBLISH": "off"}), ("BLOGGER_PUBLISH=1", [], {"BLOGGER_PUBLISH": "1"}),
                                  ("--publish draft", ["--publish", "draft"], {}), ("--publish on", ["--publish", "on"], {}), ("--publish off", ["--publish", "off"], {})):
            with self.subTest(label):
                llm, pub = spy_llm(), FakePackagePublisher()
                code, out = self.go(env=self.env(**env), llm=llm, publisher=pub, extra=extra)
                self.assertEqual(code, 2, out)
                self.assertIn("[SKIP] code=INVALID_PUBLISH blog=tistory_test", out)
                self.assertIn("초안 패키지", out)
                self.assertEqual((llm.calls, pub.counted, pub.created, self.history()), ([], [], [], []))

    def test_auto_and_an_empty_switch_are_fine_and_a_garbage_value_keeps_the_blogger_message(self):
        for value in ("", "auto", " AUTO "):
            code, out = self.go(env=self.env(BLOGGER_PUBLISH=value))
            self.assertEqual(code, 0, (value, out))
            (self.root / "tistory_test_history.json").unlink()
        code, out = self.go(env=self.env(BLOGGER_PUBLISH="yolo"))
        self.assertEqual(code, 2)
        self.assertIn("BLOGGER_PUBLISH 값을 알 수 없습니다", out)

    def test_the_auth_check_is_refused_instead_of_quietly_making_an_issue(self):
        for label, extra, env in (("--auth-check", ["--auth-check"], {}), ("BLOGGER_AUTH_CHECK", [], {"BLOGGER_AUTH_CHECK": "1"}),
                                  ("dry-run + --auth-check", ["--auth-check", "--dry-run"], {})):
            with self.subTest(label):
                llm, pub = spy_llm(), FakePackagePublisher()
                before = {p for p in self.root.rglob("*")}
                code, out = self.go(env=self.env(**env), llm=llm, publisher=pub, extra=extra)
                self.assertEqual(code, 2, out)
                self.assertIn("[SKIP] code=AUTH_CHECK_UNSUPPORTED blog=tistory_test platform=tistory", out)
                self.assertEqual((llm.calls, pub.counted, pub.created), ([], [], []))
                self.assertEqual({p for p in self.root.rglob("*")}, before)
                self.assertEqual(len([line for line in out.splitlines() if line.startswith("::error::")]), 1)

    def test_a_stopped_channel_does_nothing_and_says_so(self):
        root = make_package_root(self.tmp / "off", mode="off")
        pub = FakePackagePublisher()
        code, out = self.go(root=root, publisher=pub)
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=MODE_OFF blog=tistory_test", out)
        self.assertEqual((pub.counted, pub.created), ([], []))
        self.assertFalse((root / "tistory_test_history.json").exists())
        code, out = self.go(root=root, publisher=pub, extra=["--auth-check"])        # 정지 중이어도 인증 점검 요청은 거절한다
        self.assertEqual(code, 2)
        self.assertIn("AUTH_CHECK_UNSUPPORTED", out)

    def test_the_kill_switch_stops_everything(self):
        pub, llm = FakePackagePublisher(), spy_llm()
        code, out = self.go(env=self.env(PIPELINE_PAUSE="true"), publisher=pub, llm=llm)
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=PAUSED", out)
        self.assertEqual((pub.counted, pub.created, llm.calls, self.history()), ([], [], [], []))

    def test_a_blocked_manual_topic_stops_before_gemini_and_github(self):
        pub, llm = FakePackagePublisher(), spy_llm()
        code, out = self.go(publisher=pub, llm=llm, extra=["--topic", "혈압 낮추는 아침 습관"])
        self.assertEqual(code, 2, out)
        self.assertIn("[SKIP] code=TOPIC_BLOCKED blog=tistory_test word=혈압", out)
        self.assertEqual((pub.counted, pub.created, llm.calls, self.history()), ([], [], [], []))

    def test_other_platforms_are_still_refused_with_an_accurate_message(self):
        out = []
        code = run_mod.run(["--blog", "chance", "--root", str(self.root)], environ={}, now=NOW, llm=stub_llm, out=out.append)
        self.assertEqual(code, 2)
        text = "\n".join(out)
        self.assertIn("platform=blogger·tistory·naver 만 지원합니다 (jekyll-git)", text)

    def test_an_invalid_package_registry_is_a_config_error(self):
        reg_path = self.root / "pipeline" / "blogs.json"
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["blogs"][2]["secrets"]["login_password"] = "TISTORY_PASSWORD"
        reg_path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        pub = FakePackagePublisher()
        code, out = self.go(publisher=pub)
        self.assertEqual(code, 2)
        self.assertIn("레지스트리 검증 실패", out)
        self.assertIn("계정 정보", out)
        self.assertEqual((pub.counted, self.history()), ([], []))


class FailureTest(PackageRunBase):
    PRECHECK = (("auth_failed", 2), ("network", 1), ("api_error", 1), ("bad_response", 1))
    ISSUE = (("auth_failed", 2), ("too_long", 2), ("network", 1), ("api_error", 1), ("bad_response", 1))

    def test_precheck_failures_stop_before_gemini_with_the_right_exit_code(self):
        for code_name, exit_code in self.PRECHECK:
            with self.subTest(code_name):
                llm, pub = spy_llm(), FakePackagePublisher(check=PublishError("외부 문구 위조", code=code_name))
                code, out = self.go(publisher=pub, llm=llm)
                self.assertEqual(code, exit_code, out)
                self.assertIn(f"[SKIP] code=PACKAGE_FAILED blog=tistory_test stage=precheck reason={code_name} exit={exit_code}", out)
                self.assertEqual(llm.calls, [])
                entry = self.history()[-1]
                self.assertEqual((entry["status"], entry["topic"], entry["reasons"][0].split("]")[0]), ("publish_failed", "", f"[{code_name}"))
                errors = [line for line in out.splitlines() if line.startswith("::error::")]
                self.assertEqual(errors, [f"::error::[tistory_test] {run_mod.PACKAGE_FAILURES[code_name][1]}"])      # 고정 문장(외부 문구 없음)
                self.assertIn("PACKAGE_FAILED", self.summary())
                (self.root / "tistory_test_history.json").unlink()
                self.summary_path.unlink(missing_ok=True)

    def test_an_unclassified_exception_in_the_precheck_is_recorded_as_unexpected_infra_failure(self):
        class Boom(FakePackagePublisher):
            def count_open_drafts(self, channel_label):
                raise RuntimeError("뜻밖")
        code, out = self.go(publisher=Boom())
        self.assertEqual(code, 1)
        self.assertIn("stage=precheck reason=unexpected exit=1", out)
        self.assertIn("RuntimeError: 뜻밖", out)
        self.assertEqual(self.history()[-1]["status"], "publish_failed")

    def test_a_publisher_that_returns_no_issue_number_or_address_is_not_recorded_as_a_success(self):
        """어댑터는 자기 응답을 스스로 검사하지만, 러너도 번호나 주소가 빈 결과를 성공(package_issued)으로 적지 않는다 — 어떤 게시자가 와도 같다."""
        url = f"https://github.com/{REPO}/issues/1"
        for name, result in (("번호 없음", PublishResult(post_id="", url=url, draft=True)), ("주소 없음", PublishResult(post_id="1", url="", draft=True)),
                             ("둘 다 없음", PublishResult(post_id="  ", url=" ", draft=True))):
            with self.subTest(name):
                code, out = self.go(publisher=FakePackagePublisher(result=result))
                self.assertEqual(code, 1, out)
                self.assertIn("stage=issue reason=bad_response exit=1", out)
                self.assertIn("재실행 전에 라벨 `초안` 이슈 목록을 확인하세요", out)           # 이슈가 만들어졌을 수 있다
                entry = self.history()[-1]
                self.assertEqual((entry["status"], entry["post_id"], entry["url"]), ("publish_failed", "", ""))
                self.assertNotIn("package_issued", json.dumps(self.history()))
                (self.root / "tistory_test_history.json").unlink()
                for path in self.drafts():
                    path.unlink()

    def test_an_unknown_error_code_is_folded_into_api_error(self):
        code, out = self.go(publisher=FakePackagePublisher(fail=PublishError("x", code="something_new")))
        self.assertEqual(code, 1)
        self.assertIn("stage=issue reason=api_error exit=1", out)

    def test_issue_failures_keep_the_draft_and_exit_with_the_right_code(self):
        for code_name, exit_code in self.ISSUE:
            with self.subTest(code_name):
                pub = FakePackagePublisher(fail=PublishError("외부 문구 위조", code=code_name))
                code, out = self.go(publisher=pub)
                self.assertEqual(code, exit_code, out)
                self.assertIn(f"[SKIP] code=PACKAGE_FAILED blog=tistory_test stage=issue reason={code_name} exit={exit_code}", out)
                entry = self.history()[-1]
                self.assertEqual((entry["status"], entry["post_id"], entry["url"]), ("publish_failed", "", ""))
                self.assertTrue(entry["reasons"][0].startswith(f"[{code_name}]"))
                self.assertEqual(len(self.drafts()), 1)                       # 만든 글은 저장소 사본으로 남는다
                self.assertIn("status: publish_failed", self.drafts()[0].read_text(encoding="utf-8"))
                errors = [line for line in out.splitlines() if line.startswith("::error::")]
                self.assertEqual(len(errors), 1)
                self.assertTrue(errors[0].startswith(f"::error::[tistory_test] {run_mod.PACKAGE_FAILURES[code_name][1]}"))
                hint = "재실행 전에 라벨 `초안` 이슈 목록을 확인하세요" in errors[0]
                self.assertEqual(hint, code_name not in ("auth_failed", "too_long"), code_name)          # 이슈가 만들어졌을 수 있는 실패에만 확인 안내
                self.assertEqual(self.summary().count("### tistory_test"), 1)                              # 요약은 한 블록이다
                self.assertIn("사유:", self.summary())
                (self.root / "tistory_test_history.json").unlink()
                for path in self.drafts():
                    path.unlink()
                self.summary_path.unlink(missing_ok=True)

    def test_an_unclassified_exception_while_creating_is_infra_and_keeps_the_draft(self):
        class Boom(FakePackagePublisher):
            def publish_package(self, draft):
                raise ValueError("뜻밖의 오류\r::error::위조된 줄")
        code, out = self.go(publisher=Boom())
        self.assertEqual(code, 1)
        self.assertIn("stage=issue reason=unexpected exit=1", out)
        self.assertNotIn("\r", out)
        self.assertEqual(len(self.annotations(out)), 1)
        self.assertEqual(len(self.drafts()), 1)

    def test_a_failed_issue_does_not_use_up_the_daily_cap(self):
        self.go(publisher=FakePackagePublisher(fail=PublishError("x", code="network")))
        pub = FakePackagePublisher()
        code, out = self.go(publisher=pub)
        self.assertEqual(code, 0, out)
        self.assertEqual((len(pub.created), self.history()[-1]["status"]), (1, "package_issued"))
        self.assertEqual([e["status"] for e in self.history()], ["publish_failed", "package_issued"])

    def test_error_text_never_leaks_the_tokens_or_forges_log_lines(self):
        token, gemini = fake_token(), "gm-secret-value-123456"
        evil = f"boom {token} {gemini}\r::error::위조된 명령\n## 가짜 제목\n[x](https://evil.example)"
        for stage_pub in (FakePackagePublisher(check=PublishError(evil, code="api_error")), FakePackagePublisher(fail=PublishError(evil, code="network"))):
            self.summary_path.unlink(missing_ok=True)
            code, out = self.go(env=self.env(GEMINI_API_KEY=gemini), publisher=stage_pub)
            self.assertEqual(code, 1)
            everything = out + self.summary() + json.dumps(self.history(), ensure_ascii=False) + "".join(p.read_text(encoding="utf-8") for p in self.drafts())
            self.assertNotIn(token, everything)
            self.assertNotIn(gemini, everything)
            self.assertNotIn("\r", out)
            self.assertEqual(len(self.annotations(out)), 1, self.annotations(out))                       # 고정 문장의 ::error:: 한 줄뿐
            self.assertNotIn("위조된", self.annotations(out)[0])
            self.assertNotIn("](", self.summary())
            self.assertEqual([line for line in self.summary().splitlines() if line.startswith("## ")], [])
            (self.root / "tistory_test_history.json").unlink()
            for path in self.drafts():
                path.unlink()

    def test_the_runner_masks_the_github_token_value_itself_even_when_it_does_not_look_like_a_token(self):
        """어댑터는 자기 토큰을 스스로 가리지만, 러너도 환경의 GITHUB_TOKEN 값을 글자 그대로 비밀 목록에 넣어 어댑터 밖에서 새는 것까지 가린다.
        토큰 모양 규칙(`ghs_…`)에 기대지 않도록 모양이 없는 값으로 본다."""
        plain = "plain-value-98765-without-any-token-shape"
        self.assertEqual(run_mod.redact("앞 " + plain + " 뒤"), "앞 " + plain + " 뒤")           # 모양 규칙만으로는 가려지지 않는 값인지 먼저 확인한다

        class CountBoom(FakePackagePublisher):
            def count_open_drafts(self, channel_label):
                raise RuntimeError(f"조회 중 뜻밖 {plain}")

        class CreateBoom(FakePackagePublisher):
            def publish_package(self, draft):
                raise ValueError(f"만들다 뜻밖 {plain}")

        cases = (("점검 PublishError", FakePackagePublisher(check=PublishError(f"조회 실패 {plain}", code="network"))), ("점검 예외", CountBoom()),
                 ("만들기 PublishError", FakePackagePublisher(fail=PublishError(f"만들기 실패 {plain}", code="api_error"))), ("만들기 예외", CreateBoom()),
                 ("참고 문구", FakePackagePublisher(notes=[f"참고 {plain}"])))
        for name, pub in cases:
            with self.subTest(name):
                self.summary_path.unlink(missing_ok=True)
                code, out = self.go(env=self.env(GITHUB_TOKEN=plain), publisher=pub)
                everything = out + self.summary() + json.dumps(self.history(), ensure_ascii=False) + "".join(p.read_text(encoding="utf-8") for p in self.drafts())
                self.assertNotIn(plain, everything)
                self.assertIn("***", everything)                                         # 가렸다는 표시는 남는다
                history = self.root / "tistory_test_history.json"
                if history.exists():
                    history.unlink()
                for path in self.drafts():
                    path.unlink()

    def test_a_history_write_failure_after_the_issue_exists_points_at_the_issue_list_not_blogger(self):
        pub = FakePackagePublisher()
        with mock.patch.object(run_mod, "write_json_atomic", side_effect=OSError("disk full")):
            code, out = self.go(publisher=pub)
        self.assertEqual(code, 1)
        self.assertEqual(len(pub.created), 1)
        self.assertIn("[SKIP] code=HISTORY_WRITE_FAILED blog=tistory_test status=package_issued", out)
        self.assertIn(f"https://github.com/{REPO}/issues/1", out)
        self.assertIn("라벨 `초안` 이슈 목록", out)
        self.assertNotIn("Blogger", out)
        self.assertNotIn("Blogger", self.summary())
        self.assertIn("이력 기록 실패", self.summary())

    def test_a_draft_copy_failure_is_a_warning_when_the_issue_exists(self):
        with mock.patch.object(run_mod, "save_draft", side_effect=OSError("no space")):
            code, out = self.go()
        self.assertEqual(code, 0, out)
        self.assertEqual(len([line for line in self.annotations(out) if line.startswith("::warning::")]), 1)
        self.assertIn("초안 파일 저장 실패", self.summary())

    def test_adapter_notes_are_printed_masked_and_folded(self):
        leaky = f"참고 {fake_token()}\r::error::위조\n둘째 줄"
        code, out = self.go(publisher=FakePackagePublisher(notes=[leaky]))
        self.assertEqual(code, 0)
        self.assertIn("[참고] 참고 ***", out)
        self.assertNotIn(fake_token(), out + self.summary())
        self.assertEqual(self.annotations(out), [])

    def test_the_title_in_the_log_and_summary_is_folded_and_escaped(self):
        def evil(prompt):
            text, model = stub_llm(prompt)
            first = text.split("\n", 1)[0]
            return text.replace(first, "제목: [클릭](https://evil.example)|<b>굵게</b>\r::error::위조된 제목 줄"), model
        code, out = self.go(llm=evil)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.annotations(out), [])
        lines = self.summary().splitlines()
        self.assertEqual(lines[0], "### tistory_test")
        for char in "|<>`":
            self.assertNotIn(char, lines[1])
        self.assertNotIn("](", self.summary())


class StatusTest(PackageRunBase):
    def test_package_issued_counts_toward_the_daily_cap_like_the_other_unpublished_drafts(self):
        self.assertIn("package_issued", run_mod.COUNTED_STATUSES)
        self.assertTrue(run_mod._counts_toward_cap({"status": "package_issued"}))
        self.assertFalse(run_mod._counts_toward_cap({"status": "publish_failed"}))                          # 이슈 번호가 없는 실패는 세지 않는다
        self.assertTrue(run_mod._counts_toward_cap({"status": "publish_failed", "post_id": "7"}))
        self.assertEqual(run_mod.COUNTED_STATUSES, {"posted", "draft", "draft_uploaded", "generated_unpublished", "package_issued"})

    def test_the_delivery_table_has_a_package_row_and_blogger_rows_are_unchanged(self):
        self.assertEqual(run_mod.decide_delivery("auto", "package"), "package")
        table = {("on", "auto"): "publish", ("on", "draft"): "publish", ("draft", "auto"): "draft", ("draft", "draft"): "draft",
                 ("off", "auto"): "file", ("off", "draft"): "file", ("auto", "auto"): "publish", ("auto", "draft"): "draft", ("auto", "off"): "file"}
        for (policy, mode), expected in table.items():
            self.assertEqual(run_mod.decide_delivery(policy, mode), expected, (policy, mode))

    def test_the_watchdog_does_not_call_a_package_blog_stale_or_inactive_after_an_issue(self):
        reg = registry.load_registry(self.root / "pipeline" / "blogs.json")
        blog = registry.get_blog(reg, "tistory_test")
        self.go()
        history = self.history()
        later = datetime(2026, 10, 21, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(health.evaluate(blog, history, later), [])
        self.assertIn("package_issued", health.OK_STATUSES)
        self.assertEqual(health.post_days_from_history(history), {datetime(2026, 10, 21).date()})
        stale = health.evaluate(blog, history, datetime(2026, 10, 25, 20, 0, tzinfo=timezone.utc))
        self.assertEqual([f.code for f in stale], ["STALE"])                                                # 오래 안 만들면 감시가 알린다


if __name__ == "__main__":
    unittest.main()
