"""로그·공개 코멘트·PR 본문 정책의 회귀 테스트 — docs/DEFECT_REGISTER.md D-39(워크플로 명령 주입 등).

- 러너가 내는 모든 줄은 `issue=#N author=@login(권한)` 으로 시작하고, 어떤 줄도 `::` 로 시작하거나 `##[` 를 포함하지 않는다
- DRY_RUN 출력은 `::stop-commands::<무작위 토큰>` 으로 감싸고 줄마다 무력화·비밀 가림
- AI 실패 원인은 마스킹·300자 제한으로 러너 로그에만(공개 코멘트·result.json 에는 없다)
- 공개 코멘트에 되풀이되는 AI·요청 유래 텍스트는 코드 스팬, PR 본문 diff 는 내용보다 긴 틸드 펜스
"""
import contextlib
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from edits_helpers import ABOUT, image_body, img, issue, make_edit_root, page_body, post_text, write
from pipeline.edits import checks, ops, runner, safety, scope_check
from test_edits_runner import NEW_SENTENCE, OLD_SENTENCE, RunnerBase, llm_returning

FAKE_KEY = "AIza" + "B" * 35                        # 소스에 비밀 모양 리터럴을 쓰지 않는다(런타임 조립)
FAKE_TOKEN = "gh" + "p_" + "C" * 36
HOSTILE = "::warning::boom\n##[error]x\n  ::add-mask::VALUE\n::stop-commands::tok\r::error::y\N{LINE SEPARATOR}::notice::z\u0085::warning::w ##[group]g"


def strip_code_spans(markdown):
    return re.sub(r"`[^`\n]*`", "", markdown)


def bad_lines(text):
    """워크플로 명령으로 해석될 수 있는 줄(러너는 줄 앞 공백을 지운 뒤 `::` 를, 줄 어디서든 `##[` 를 인식한다)."""
    out = []
    for raw in text.replace("\r", "\n").split("\n"):
        if raw.lstrip().startswith("::") or "##[" in raw:
            out.append(raw)
    return out


def run_main(root, iss, extra=()):
    """runner.main 을 실제 CLI 처럼 돌린다. 개발자 셸의 환경변수(DRY_RUN·GEMINI_API_KEY 등)가 결과를 바꾸지 않게 비운 환경에서 돌린다."""
    with tempfile.TemporaryDirectory() as tmp:
        issue_file, out = Path(tmp) / "issue.json", Path(tmp) / "out"
        issue_file.write_text(json.dumps(iss), encoding="utf-8")
        buf = io.StringIO()
        with mock.patch.dict(os.environ, clear=True), contextlib.redirect_stdout(buf):
            code = runner.main(["--issue-file", str(issue_file), "--out", str(out), "--root", str(root), *extra])
        files = {p.name: p.read_text(encoding="utf-8") for p in out.iterdir()}
    return code, buf.getvalue(), files


class NeutralizeTest(unittest.TestCase):
    def test_line_start_colons_and_legacy_commands_are_broken_everywhere(self):
        for text in ("::warning::x", "  ::error::x", "\t::add-mask::v", "::stop-commands::tok", "a ##[error]b", "##[group]", "###[error]x",
                     "x ##[add-mask]y ##[warning]z", "\n::warning::after newline", "\N{NO-BREAK SPACE}::warning::nbsp"):
            for fn in (safety.one_line, lambda t: safety.log_text(t, 300)):
                self.assertEqual(bad_lines(fn(text)), [], (text, fn(text)))

    def test_one_line_still_folds_truncates_and_defuses_mentions(self):
        self.assertEqual(safety.one_line("a\n  b\t\tc"), "a b c")
        self.assertEqual(len(safety.one_line("가" * 500, 90)), 90)
        self.assertNotIn("@everyone", safety.one_line("@everyone 안녕"))
        self.assertEqual(safety.one_line("정상 문장입니다."), "정상 문장입니다.")

    def test_log_text_never_exceeds_its_limit_even_after_neutralizing(self):
        """무력화(`##[`→`# #[`, 줄 시작 `::`→`: :`)가 글자를 늘려도 로그 한 줄은 limit 자를 넘지 않는다(AI 실패 원인은 300자 제한)."""
        for text in ("a" * 296 + "##[b", "::" + "a" * 400, "a" * 295 + "##[##[x", "x" * 1000):
            for limit in (300, 120):
                out = safety.log_text(text, limit)
                self.assertLessEqual(len(out), limit, (text[:12], limit))
                self.assertEqual(bad_lines(out), [])
        self.assertEqual(len(safety.log_text("a" * 296 + "##[b", 300)), 300)

    def test_redact_hides_secret_shaped_values(self):
        for secret in (FAKE_KEY, FAKE_TOKEN, "sk-" + "d" * 40, "k" + "ey=" + "e" * 30):
            self.assertNotIn(secret, safety.redact(f"앞 {secret} 뒤"), secret)
            self.assertNotIn(secret, safety.log_text(f"앞 {secret} 뒤"))

    def test_fenced_block_cannot_be_closed_from_inside(self):
        for body in ("plain", "```\nescape\n```", "~~~~\nx\n~~~~", "~~~~~~~~ 길게\n~~~", "줄 중간 ~~~~~ 틸드"):
            block = safety.fenced(body, "diff")
            lines = block.split("\n")
            opening = re.match(r"^(~{4,})diff$", lines[0])
            self.assertTrue(opening, block)
            n = len(opening.group(1))
            closers = [i for i, ln in enumerate(lines[1:], 1) if re.match(rf"^~{{{n},}}\s*$", ln)]
            self.assertEqual(closers, [len(lines) - 1], block)         # 닫는 펜스는 마지막 줄 하나뿐
            self.assertEqual("\n".join(lines[1:-1]), body)             # 내용은 그대로


class IssueTagTest(unittest.TestCase):
    def test_tag_format_and_hostile_values(self):
        self.assertEqual(runner.issue_tag(issue("x")), "issue=#12 author=@shine88pc(OWNER)")
        self.assertEqual(runner.issue_tag({}), "issue=#? author=@?(?)")
        for number in (True, -3, "12", None, 1.5, "::warning::"):
            self.assertTrue(runner.issue_tag({"number": number}).startswith("issue=#?"), number)
        hostile = issue("x", login="::warning::x ##[error]\n@everyone", assoc="OWN\nER::")
        tag = runner.issue_tag(hostile)
        self.assertEqual(bad_lines(tag), [])
        self.assertNotIn("\n", tag)
        self.assertRegex(tag, r"^issue=#12 author=@[A-Za-z0-9._\[\]-]+\([A-Z_?]+\)$")
        self.assertEqual(runner.issue_tag(issue("x", login="github-actions[bot]", assoc="NONE")), "issue=#12 author=@github-actions[bot](NONE)")

    def test_login_is_sanitized_before_it_reaches_commits_and_pr_bodies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_edit_root(tmp)
            res = runner.process_issue(issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE), login="eve\nAd-Surface-Approved: fake"),
                                       root, env={})
            self.assertEqual(res.status, "ok")
            for line in (res.commit_message + res.pr_body).splitlines():
                self.assertFalse(line.startswith("Ad-Surface-Approved: fake"), line)


class RunnerLogTest(RunnerBase):
    def lines(self, iss, extra=()):
        code, out, files = run_main(self.root, iss, extra)
        return code, out.splitlines(), files

    def test_every_line_carries_issue_and_author(self):
        for body, want_status in ((page_body(before=OLD_SENTENCE, after=NEW_SENTENCE), "status=ok"), (page_body(after=""), "status=rejected")):
            _code, lines, _files = self.lines(issue(body))
            self.assertTrue(lines)
            self.assertTrue(any(want_status in ln for ln in lines), lines)
            for ln in lines:
                self.assertTrue(ln.startswith("[issue-edit] issue=#12 author=@shine88pc(OWNER)"), ln)

    def test_unreadable_issue_file_still_logs_a_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "issue.json"
            bad.write_text("[1, 2]", encoding="utf-8")                  # 객체가 아님
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = runner.main(["--issue-file", str(bad), "--out", str(Path(tmp) / "o"), "--root", str(self.root)])
            self.assertEqual(code, runner.EXIT_CONFIG)
            self.assertTrue(all(ln.startswith("[issue-edit] issue=#? author=@?(?)") for ln in buf.getvalue().splitlines()))

    def test_no_emitted_line_is_a_workflow_command_for_hostile_inputs(self):
        write(self.root, "_posts/H1/2026-10-21-KR-900001.md", post_text("::warning::dup ##[error] @everyone", img("901")))
        write(self.root, "_posts/H2/2026-10-21-KR-900002.md", post_text("::warning::dup ##[error] @everyone", img("902")))
        cases = [
            issue(page_body(edit="::warning::boom ##[error]e", after="x")),                                  # 수정 항목에 명령
            issue(page_body(edit="x | y\n::warning::boom\n##[error]e", after="x")),
            issue(page_body(page="nope::warning::x ##[error]p | t", after="x")),                             # 페이지 id 에 명령
            issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE + "\n" + HOSTILE)),                      # 요청문에 명령(정상 처리 경로)
            issue(page_body(before=HOSTILE, after="x")),                                                     # 변경 전에 명령
            issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE), login="::warning::x##[error]", assoc="OWNER"),
            issue(image_body("::warning::dup ##[error] @everyone", HOSTILE), labels=("blog-control", "edit:image"), title="[이미지 변경] ##[error]"),
            issue(image_body("없는 글 " + HOSTILE, "x"), labels=("blog-control", "edit:image")),
            issue("::warning::양식 아님 ##[error]", labels=(), title="::warning::무제"),
        ]
        for iss in cases:
            _code, lines, files = self.lines(iss)
            self.assertEqual(bad_lines("\n".join(lines)), [], iss["body"][:60])
            # 공개 코멘트(rejected/error)에 되풀이된 텍스트도 줄 시작 명령이 아니다
            self.assertEqual([ln for ln in files.get("comment.md", "").splitlines() if ln.lstrip().startswith("::")], [])

    def test_ambiguous_post_titles_are_code_spans_in_the_public_comment(self):
        write(self.root, "_posts/H1/2026-10-21-KR-900001.md", post_text("![x](https://evil.example/p.png) @everyone", img("901")))
        write(self.root, "_posts/H2/2026-10-21-KR-900002.md", post_text("![x](https://evil.example/p.png) @everyone", img("902")))
        res = self.go(issue(image_body("![x](https://evil.example/p.png) @everyone", "소방관"), labels=("blog-control", "edit:image")))
        self.assertEqual(res.status, "rejected")
        self.assertIn("여러 글", res.comment)
        outside = strip_code_spans(res.comment)
        for fragment in ("![", "](", "evil.example", "@everyone"):
            self.assertNotIn(fragment, outside)

    def test_secret_values_are_never_printed(self):
        iss = issue(page_body(before=OLD_SENTENCE, after=f"{NEW_SENTENCE} {FAKE_KEY} {FAKE_TOKEN}"))
        code, out, files = run_main(self.root, iss)
        self.assertEqual(code, 0)
        for text in [out, *files.values()]:
            for secret in (FAKE_KEY, FAKE_TOKEN):
                self.assertNotIn(secret, text)
                self.assertNotIn(secret[:12], text)             # 앞 4자 미리보기 이상은 어디에도 나오지 않는다
        self.assertIn("비밀 값", out)                              # 거부 사유는 라벨과 4자 미리보기만


class PublicTextTest(RunnerBase):
    def assertNoLiveMarkdown(self, text):
        outside = strip_code_spans(text)
        for fragment in ("![", "](", "evil.example", "@everyone", "<img"):
            self.assertNotIn(fragment, outside, text)

    def test_unknown_edit_item_and_page_id_are_code_spans(self):
        hostile = "![x](https://evil.example/p.png) @everyone"
        for body in (page_body(edit=f"{hostile} | y", after="x"), page_body(page=f"{hostile} | t", after="x")):
            res = self.go(issue(body))
            self.assertEqual(res.status, "rejected")
            self.assertNoLiveMarkdown(res.comment)
            self.assertIn("`", res.comment)

    def test_ai_refusal_reason_is_a_code_span_in_the_comment(self):
        hostile = "![x](https://evil.example/p.png) @everyone [링크](https://evil.example/)"
        res = self.go(issue(page_body(edit="layout | 섹션/레이아웃 변경 (해당 페이지 안에서만)", after="둘째 문단을 고쳐 주세요")),
                      llm=llm_returning({"patches": [], "reason": hostile}))
        self.assertEqual(res.status, "rejected")
        self.assertIn("AI 가 수정하지 않기로 했습니다", res.comment)
        self.assertNoLiveMarkdown(res.comment)
        self.assertIn("evil.example", res.comment)               # 사유 자체는 보여 준다(코드 스팬 안에서)

    def test_check_reasons_put_derived_text_in_code_spans(self):
        limits = {"max_changed_files": 1, "max_changed_lines": 80, "max_file_chars": 80000}
        before = "---\ntitle: t\n---\n본문\n"
        hostile_key = "![x](https://evil.example/p.png)"
        after = f'---\ntitle: t\n"{hostile_key}": 1\n---\n본문\n'
        reasons = checks.verify_changes({"about.md": (before, after)}, ["about.md"], limits, mode="front_matter", only_fields=["title"])
        self.assertTrue(reasons)
        self.assertNoLiveMarkdown("\n".join(reasons))
        reasons = checks.verify_changes({"about.md": ("본문\n", "본문\n[x](https://evil.example/a)\n")}, ["about.md"], limits, ai_patch=True)
        self.assertTrue(any("`evil.example`" in r for r in reasons), reasons)
        reasons = checks.verify_changes({"about.md": ("본문\n", "본문\nhttp://insecure.example/a\n")}, ["about.md"], limits)
        self.assertTrue(any("`http://insecure.example/a`" in r for r in reasons), reasons)


class DiffFenceTest(RunnerBase):
    @staticmethod
    def diff_block(body):
        """### 변경 내용 아래 첫 코드 펜스의 (펜스, 내용, 닫는 줄 번호). CommonMark: 닫는 펜스는 같은 문자로 열린 펜스 이상 길이."""
        lines = body.split("\n")
        start = next(i for i, ln in enumerate(lines) if ln.startswith("### 변경 내용")) + 1
        opening = re.match(r"^(~{3,}|`{3,})(\w*)$", lines[start])
        assert opening, lines[start]
        fence = opening.group(1)
        close = next(i for i in range(start + 1, len(lines)) if re.match(rf"^{re.escape(fence[0])}{{{len(fence)},}}\s*$", lines[i]))
        return fence, "\n".join(lines[start + 1:close]), close, lines

    def test_diff_uses_a_tilde_fence_of_at_least_four(self):
        res = self.go(issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE)))
        fence, content, _close, _lines = self.diff_block(res.pr_body)
        self.assertEqual(set(fence), {"~"})
        self.assertGreaterEqual(len(fence), 4)
        self.assertIn(NEW_SENTENCE, content)

    def test_page_text_with_backtick_and_tilde_fences_cannot_close_the_diff_early(self):
        hostile = ABOUT.replace("\n문의는", "\n```\n~~~~~\n문의는", 1).replace(f"{OLD_SENTENCE}\n", f"{OLD_SENTENCE}\n~~~~~~\n```\n", 1)
        write(self.root, "about.md", hostile)
        res = self.go(issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE)))
        self.assertEqual(res.status, "ok")
        fence, content, close, lines = self.diff_block(res.pr_body)
        self.assertGreaterEqual(len(fence), 7)                      # 내용 속 가장 긴 틸드(6개)보다 길다
        self.assertIn("```", content)
        self.assertIn("~~~~~~", content)
        self.assertEqual(lines[close + 2], "### 리뷰 체크리스트")      # 닫는 펜스 뒤에 곧바로 다음 절이 이어진다(탈출 없음)
        self.assertEqual(content, checks.unified_diff(hostile.replace("\r\n", "\n"), hostile.replace(OLD_SENTENCE, NEW_SENTENCE), "about.md"))


class AiFailureLogTest(RunnerBase):
    EDIT = "layout | 섹션/레이아웃 변경 (해당 페이지 안에서만)"

    def failing_llm(self, message):
        def boom(prompt):
            raise RuntimeError(message)
        return boom

    def run_failing(self, message):
        iss = issue(page_body(edit=self.EDIT, after="둘째 문단을 고쳐 주세요"))
        with mock.patch.object(runner, "build_llm", return_value=self.failing_llm(message)):
            return run_main(self.root, iss)

    def test_reason_is_masked_capped_and_only_in_the_runner_log(self):
        noise = "why-it-failed " + "z" * 600
        message = f"{noise} {FAKE_KEY} token={FAKE_TOKEN} ::error::x ##[error]y"
        code, out, files = self.run_failing(message)
        self.assertEqual(code, runner.EXIT_INFRA)
        detail = [ln for ln in out.splitlines() if "원인(로그 전용)" in ln]
        self.assertEqual(len(detail), 1, out)
        self.assertIn("RuntimeError", detail[0])
        self.assertIn("why-it-failed", detail[0])
        self.assertLessEqual(len(detail[0].split("원인(로그 전용): ", 1)[1]), 300)
        for secret in (FAKE_KEY, FAKE_TOKEN):
            self.assertNotIn(secret, out)
        self.assertEqual(bad_lines(out), [])
        # 공개 코멘트·산출물에는 예외 종류까지만(원인 상세는 없다)
        for name, text in files.items():
            self.assertNotIn("why-it-failed", text, name)
            self.assertNotIn("zzzz", text, name)
        self.assertIn("AI 호출 실패: RuntimeError", files["comment.md"])
        self.assertNotIn("log_detail", files["result.json"])

    def test_infra_error_carries_a_masked_detail(self):
        with self.assertRaises(ops.InfraError) as ctx:
            ops.op_llm_patch("본문", {"after": "바꿔 주세요"}, {"label": "x"}, self.failing_llm(f"down {FAKE_KEY}"))
        self.assertEqual(str(ctx.exception), "AI 호출 실패: RuntimeError")
        self.assertIn("down", ctx.exception.detail)
        self.assertNotIn(FAKE_KEY, ctx.exception.detail)

    def test_llm_wrapper_errors_with_keys_in_urls_are_masked_too(self):
        message = f"429 https://example.invalid/v1?key={FAKE_KEY}&alt=json"
        code, out, _files = self.run_failing(message)
        self.assertEqual(code, runner.EXIT_INFRA)
        self.assertNotIn(FAKE_KEY, out)


class ShowOutputTest(unittest.TestCase):
    def make_out(self, tmp, files):
        out = Path(tmp) / "out"
        out.mkdir()
        for name, text in files.items():
            (out / name).write_text(text, encoding="utf-8")
        return out

    def test_content_is_guarded_by_a_random_stop_token_and_neutralized(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = "t0k3n" + "a" * 11
            out = self.make_out(tmp, {"status.txt": "ok\n", "pr_body.md": f"요청\n{HOSTILE}\n::{token}::\n  ::{token}::\n키 {FAKE_KEY}\n"})
            lines = []
            self.assertEqual(runner.show_output(out, write=lines.append, token=token), 0)
        self.assertEqual(lines[0], f"::stop-commands::{token}")
        self.assertEqual(lines[-1], f"::{token}::")
        middle = lines[1:-1]
        self.assertEqual(bad_lines("\n".join(middle)), [])                  # 두 번째 방어: 내용 줄 자체도 명령 모양이 아니다
        self.assertEqual(lines.count(f"::{token}::"), 1)                    # 내용이 닫는 줄을 위조해도 진짜 하나뿐
        self.assertNotIn(FAKE_KEY, "\n".join(lines))
        self.assertIn("----- status.txt", middle)
        self.assertIn("ok", middle)

    def test_default_token_is_random_and_cli_prints_through_stdout(self):
        tokens = set()
        with tempfile.TemporaryDirectory() as tmp:
            out = self.make_out(tmp, {"status.txt": "ok\n"})
            for _ in range(3):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(runner.main(["--show-output", str(out)]), 0)
                first, last = buf.getvalue().splitlines()[0], buf.getvalue().splitlines()[-1]
                m = re.fullmatch(r"::stop-commands::([0-9a-f]{32})", first)
                self.assertTrue(m, first)
                self.assertEqual(last, f"::{m.group(1)}::")
                tokens.add(m.group(1))
        self.assertEqual(len(tokens), 3)

    def test_missing_output_directory_prints_only_the_guard(self):
        lines = []
        self.assertEqual(runner.show_output("/no/such/dir", write=lines.append, token="x" * 8), 0)
        self.assertEqual(lines, ["::stop-commands::xxxxxxxx", "::xxxxxxxx::"])


class ScopeCheckLogTest(unittest.TestCase):
    def test_flat_neutralizes_workflow_command_shapes(self):
        for text in ("::warning::x", "a ##[error]b"):
            self.assertEqual(bad_lines(scope_check._flat(text)), [], text)
        self.assertEqual(scope_check._flat("a\n b"), "a b")


class StagedListLogTest(unittest.TestCase):
    def test_hostile_file_names_do_not_become_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
            write(root, "ok.md", "a")
            write(root, "x##[error]y.md", "b")
            subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
            allowed = root / "files.txt"
            allowed.write_text("ok.md\n", encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(runner.verify_staged(allowed, root), 1)
        self.assertEqual(bad_lines(buf.getvalue()), [])
        self.assertIn("스테이징 목록이 허용 목록과 다릅니다", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
