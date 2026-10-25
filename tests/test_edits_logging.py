"""로그·공개 코멘트·PR 본문 정책의 회귀 테스트 — docs/DEFECT_REGISTER.md D-39(워크플로 명령 주입 등).

- 러너가 내는 모든 줄은 `issue=#N author=@login(권한)` 으로 시작하고, 어떤 줄도 `::` 로 시작하거나 `##[` 를 포함하지 않는다
- DRY_RUN 출력은 `::stop-commands::<무작위 토큰>` 으로 감싸고 줄마다 무력화·비밀 가림
- AI 실패 원인은 마스킹·300자 제한으로 러너 로그에만(공개 코멘트·result.json 에는 없다)
- 공개 코멘트에 되풀이되는 AI·요청 유래 텍스트는 코드 스팬, PR 본문 diff 는 내용보다 긴 틸드 펜스
"""
import contextlib
import inspect
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import generator
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


# .NET string.TrimStart() 가 지우는 공백(char.IsWhiteSpace): 러너는 줄 앞의 이 문자들을 지운 뒤에 `::` 를 인식한다
DOTNET_WS = {chr(c) for c in (*range(0x09, 0x0E), 0x20, 0x85, 0xA0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F, 0x3000)}


def dotnet_lstrip(text):
    i = 0
    while i < len(text) and text[i] in DOTNET_WS:
        i += 1
    return text[i:]


def run_main(root, iss, extra=(), env=None):
    """runner.main 을 실제 CLI 처럼 돌린다. 개발자 셸의 환경변수(DRY_RUN·GEMINI_API_KEY 등)가 결과를 바꾸지 않게 비운 환경에서 돌린다.
    env: 비운 환경에 넣을 값(예: 가짜 UNSPLASH_ACCESS_KEY)."""
    with tempfile.TemporaryDirectory() as tmp:
        issue_file, out = Path(tmp) / "issue.json", Path(tmp) / "out"
        issue_file.write_text(json.dumps(iss), encoding="utf-8")
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=True), contextlib.redirect_stdout(buf):
            code = runner.main(["--issue-file", str(issue_file), "--out", str(out), "--root", str(root), *extra])
        files = {p.name: p.read_text(encoding="utf-8") for p in out.iterdir()}
    return code, buf.getvalue(), files


class NeutralizeTest(unittest.TestCase):
    def test_line_start_colons_and_legacy_commands_are_broken_everywhere(self):
        for text in ("::warning::x", "  ::error::x", "\t::add-mask::v", "::stop-commands::tok", "a ##[error]b", "##[group]", "###[error]x",
                     "x ##[add-mask]y ##[warning]z", "\n::warning::after newline", "\N{NO-BREAK SPACE}::warning::nbsp"):
            for fn in (safety.one_line, lambda t: safety.log_text(t, 300)):
                self.assertEqual(bad_lines(fn(text)), [], (text, fn(text)))

    def test_neutralize_alone_breaks_a_command_behind_any_kind_of_leading_whitespace(self):
        """검증자 V17: show_output 은 줄을 접지 않고 neutralize 만 거친다. 러너는 앞 공백(탭·NBSP·전각 공백 등 .NET 공백 전부)을 지운 뒤 `::` 를 인식한다."""
        for lead in ("", " ", "   ", "\t", " \t ", "\v", "\f", "\N{NEXT LINE}", "\N{NO-BREAK SPACE}", "\N{OGHAM SPACE MARK}", "\N{EN QUAD}",
                     "\N{EM SPACE}", "\N{HAIR SPACE}", "\N{NARROW NO-BREAK SPACE}", "\N{MEDIUM MATHEMATICAL SPACE}", "\N{IDEOGRAPHIC SPACE}"):
            out = safety.neutralize(lead + "::warning::x")
            self.assertFalse(dotnet_lstrip(out).startswith("::"), repr(lead))
            self.assertEqual(dotnet_lstrip(out), ": :warning::x", repr(lead))        # 한 번만, 앞 공백은 그대로 둔 채 첫 `::` 만 깬다
        self.assertEqual(safety.neutralize("정상 줄"), "정상 줄")
        self.assertEqual(safety.neutralize("a::b"), "a::b")                           # 줄 시작이 아닌 `::` 는 명령이 아니다

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

    def test_a_secret_cut_by_the_length_limit_is_still_hidden(self):
        """검증자 V16: 자른 뒤에 가리면 경계에 걸린 키의 앞부분(패턴이 못 알아보는 길이)이 그대로 남는다. 먼저 가리고 자른다."""
        for secret, marker in ((FAKE_KEY, "AIza"), (FAKE_TOKEN, "ghp_")):
            for limit in (60, 120, 300):
                for cut in (6, 12, 25, 34):                 # 키의 앞 cut 자만 남도록 자르는 위치(앞에 공백: 토큰 패턴은 단어 경계를 요구한다)
                    out = safety.log_text("x" * (limit - cut - 1) + " " + secret + " 뒤", limit)
                    self.assertNotIn(marker, out, (marker, limit, cut))
                    self.assertLessEqual(len(out), limit)

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
        self.assertRegex(tag, r"^issue=#12 author=@[A-Za-z0-9._\[\]-]{1,40}\([A-Z_?]{1,30}\)$")
        self.assertEqual(runner.issue_tag(issue("x", login="github-actions[bot]", assoc="NONE")), "issue=#12 author=@github-actions[bot](NONE)")

    def test_login_and_association_are_length_limited(self):
        """검증자 V44: 로그인 40자·권한 30자까지만(로그 줄 한 줄이 길어지지 않게)."""
        tag = runner.issue_tag(issue("x", login="a" * 500, assoc="B" * 500))
        self.assertEqual(tag, f"issue=#12 author=@{'a' * 40}({'B' * 30})")

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

    def test_every_line_break_variant_is_split_and_neutralized(self):
        """검증자 V51: 줄바꿈 변형(\\v·\\f·\\x1c~\\x1e·\\x85·U+2028·U+2029)도 줄로 나눠 각각 무력화한다 — '\\n' 으로만 나누면 그 뒤의 `::` 가 남는다."""
        for brk in ("\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\N{LINE SEPARATOR}", "\N{PARAGRAPH SEPARATOR}", "\r", "\r\n"):
            with tempfile.TemporaryDirectory() as tmp:
                out = self.make_out(tmp, {"pr_body.md": f"앞 줄{brk}::warning::x{brk}  ::add-mask::v{brk}\t::error::t{brk}##[error]y{brk}끝"})
                lines = []
                runner.show_output(out, write=lines.append, token="t" * 8)
            inner = "\n".join(lines[1:-1])
            pieces = inner.splitlines()                          # 파이썬의 모든 줄바꿈 변형으로 다시 나눠도
            self.assertEqual([p for p in pieces if dotnet_lstrip(p).startswith("::") or "##[" in p], [], repr(brk))
            self.assertEqual(bad_lines(inner), [], repr(brk))

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


class ResultFieldsLogTest(RunnerBase):
    """검증자 V18: 결과의 어떤 필드도 비밀 가림·한 줄 접기·길이 제한(log_text)을 거치지 않고는 러너 로그에 나가지 않는다."""

    HOSTILE = f"::warning::x ##[error]y {FAKE_KEY} {FAKE_TOKEN} @everyone " + "가" * 600

    def test_every_logged_field_goes_through_log_text(self):
        res = runner.Result("rejected", message=self.HOSTILE, reasons=[self.HOSTILE, "::add-mask::z"], edit_type=self.HOSTILE,
                            target=self.HOSTILE, notes=[self.HOSTILE], log_detail=self.HOSTILE)
        with mock.patch.object(runner, "process_issue", return_value=res):
            _code, out, _files = run_main(self.root, issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE)))
        lines = out.splitlines()
        self.assertEqual(len(lines), 1 + 2 + 1 + 1, out)                        # 상태 줄, 사유 2, 참고 1, 원인 1
        for line in lines:
            self.assertTrue(line.startswith("[issue-edit] issue=#12 author=@shine88pc(OWNER)"), line)
            for secret in (FAKE_KEY, FAKE_TOKEN, "AIza", "ghp_"):
                self.assertNotIn(secret, line)
        self.assertEqual(bad_lines(out), [])
        self.assertNotIn("@everyone", out)
        self.assertLessEqual(len(lines[0]), 600, lines[0][:80])
        for line in lines[1:]:
            marker = next(m for m in ("   - ", "   * ", "   ! 원인(로그 전용): ") if m in line)
            self.assertLessEqual(len(line.split(marker, 1)[1]), 300, line[:80])

    def test_error_and_reject_results_fold_their_messages_to_one_line(self):
        """검증자 V48·V49: 오류·거부 사유는 줄바꿈이 든 채로 코멘트에 들어가지 않는다."""
        for make in (lambda text: runner._error(text), lambda text: runner._reject([text])):
            res = make("한 줄\n::warning::x\r##[error]y\n- 가짜 항목")
            self.assertNotRegex(res.message, r"[\r\n]")
            self.assertEqual(bad_lines(res.comment), [])
            self.assertNotIn("\n- 가짜", res.comment)


class UnexpectedFailureTest(RunnerBase):
    BOOM = "::warning::x ##[error]y " + FAKE_KEY + " 요청문 전문 ![x](https://evil.example/p.png)"

    def test_a_crash_inside_the_processor_becomes_an_error_result_without_user_text(self):
        """검증자 F-6: 예상 못 한 예외가 새면 트레이스백으로 죽고 status.txt 도 없어 워크플로가 이슈에 코멘트를 남기지 못한다."""
        with mock.patch.object(runner, "process_issue", side_effect=RuntimeError(self.BOOM)):
            code, out, files = run_main(self.root, issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE)))
        self.assertEqual(code, runner.EXIT_INFRA)
        self.assertEqual(files["status.txt"].strip(), "error")
        self.assertEqual(files["files.txt"], "")
        for text in (out, *files.values()):
            for fragment in (FAKE_KEY, "요청문 전문", "evil.example", "##[error]", "AIza"):
                self.assertNotIn(fragment, text)
        self.assertIn("RuntimeError", out)                                     # 예외 종류(클래스 이름)만 낸다
        self.assertIn("RuntimeError", files["comment.md"])
        self.assertIn("저장소는 변경되지 않았습니다", files["comment.md"])
        for line in out.splitlines():
            self.assertTrue(line.startswith("[issue-edit] issue=#12 author=@shine88pc(OWNER)"), line)
        self.assertEqual(bad_lines(out), [])

    def test_system_exit_and_keyboard_interrupt_are_not_swallowed(self):
        for exc in (KeyboardInterrupt(), SystemExit(3)):
            with mock.patch.object(runner, "process_issue", side_effect=exc):
                with self.assertRaises(type(exc)):
                    run_main(self.root, issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE)))

    def test_malformed_post_addresses_are_rejected_not_crashes(self):
        """검증자 F-6: 게시글 주소 `http://[::1`·`https://[` 는 urlsplit 이 ValueError 를 내 러너가 트레이스백으로 죽었다."""
        for address in ("http://[::1", "https://[", "http://[", "https://example.com\N{FULLWIDTH SOLIDUS}path", "http://\N{ACCOUNT OF}/"):
            iss = issue(image_body(address, "소방관"), labels=("blog-control", "edit:image"), title="[이미지 변경] x")
            code, out, files = run_main(self.root, iss)
            self.assertEqual(code, 0, address)
            self.assertEqual(files["status.txt"].strip(), "rejected", address)
            self.assertIn("올바르지 않습니다", files["comment.md"])
            for line in out.splitlines():
                self.assertTrue(line.startswith("[issue-edit] issue=#12 author=@shine88pc(OWNER)"), line)


def lines_outside_fences(markdown):
    """CommonMark 규칙으로 코드 펜스 밖에 남는 줄(여기 있는 마크다운은 렌더된다)."""
    in_fence, fence, outside = False, "", []
    for line in markdown.split("\n"):
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if opening and not in_fence:
            in_fence, fence = True, opening.group(1)
            continue
        if in_fence and re.match(rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}\s*$", line):
            in_fence = False
            continue
        if not in_fence:
            outside.append(line)
    return outside


LIVE_MARKDOWN = ("![", "](", "evil.example", "@everyone", "@octocat", "<img")


class CodeSpanCutTest(RunnerBase):
    """검증자 F-7: 400자 자르기가 코드 스팬 한가운데를 자르면 닫는 백틱이 사라져 뒤의 AI·요청 유래 텍스트가 마크다운으로 살아난다."""

    HOSTILE = "![x](https://evil.example/p.png) @everyone [링크](https://evil.example/)"

    def test_clip_drops_an_open_span_only_for_markdown(self):
        self.assertEqual(safety.clip("a `b c` d", 4, markdown=True), "a")
        self.assertEqual(safety.clip("a `b c` d", 4), "a `b")
        self.assertEqual(safety.clip("`ab`", 4, markdown=True), "`ab`")               # 스팬이 정확히 끝나는 곳은 그대로
        self.assertEqual(safety.clip("`ab` `cd` e", 8, markdown=True), "`ab`")        # 두 번째 스팬 안에서 잘림 → 그 스팬만 뺀다
        self.assertEqual(safety.clip("스팬 없는 긴 문장입니다", 5, markdown=True), "스팬 없는")
        self.assertEqual(safety.clip("a\n  b", 90, markdown=True), "a b")
        self.assertEqual(safety.one_line("x `y z` w", 4, markdown=True), "x")

    def test_reject_and_error_never_leave_an_unclosed_code_span(self):
        for make in (lambda reason: runner._reject([reason]), lambda reason: runner._error(reason)):
            for prefix_len in range(330, 400, 3):
                reason = "x" * prefix_len + " " + safety.code(self.HOSTILE, 120) + " 끝"
                comment = make(reason).comment
                self.assertEqual(comment.count("`") % 2, 0, prefix_len)
                outside = strip_code_spans(comment)
                for fragment in LIVE_MARKDOWN:
                    self.assertNotIn(fragment, outside, (prefix_len, fragment))

    def test_ambiguous_titles_with_hostile_text_cannot_escape_the_comment(self):
        """검증자 PoC 의 실제 경로: 같은 제목의 글이 여러 편이고 제목이 길면 `여러 글(N건)…` 사유가 400자를 넘는다."""
        pad = "가" * 28
        title = f"{pad} {self.HOSTILE} {pad}"[:118]
        for i in range(6):
            write(self.root, f"_posts/D{i}/2026-10-21-KR-70000{i}.md", post_text(title, img(f"70{i}")))
        res = self.go(issue(image_body(title, "소방관"), labels=("blog-control", "edit:image")))
        self.assertEqual(res.status, "rejected")
        self.assertIn("여러 글(6건)", res.comment)
        self.assertEqual(res.comment.count("`") % 2, 0)
        outside = strip_code_spans(res.comment)
        for fragment in LIVE_MARKDOWN:
            self.assertNotIn(fragment, outside, fragment)

    def test_scope_check_items_close_cut_spans_too(self):
        paths = [f"{'p' * 50}/![x](https://evil.example/{i}.png)" for i in range(8)]
        text = "요청하지 않은 파일이 바뀌었습니다(8개): " + ", ".join(f"`{p}`" for p in paths)
        for limit in range(380, 430):
            flat = scope_check._flat(text, limit)
            self.assertEqual(flat.count("`") % 2, 0, limit)
            self.assertNotIn("](", strip_code_spans(flat), limit)


class ScopeReportMarkdownTest(unittest.TestCase):
    OLD = "첫 번째 문단입니다. 이 문장은 그대로 유지되어야 합니다."
    NEW = "첫 번째 문단입니다. 바뀐 문장입니다."

    def test_item_text_is_folded_and_neutralized(self):
        """검증자 D07: 항목 문장은 한 줄로 접히고 `::`·`##[` 가 무력화된다(PR 파일 이름 등 외부 유래 텍스트가 들어간다)."""
        markdown = scope_check.Report("FAIL", [("❌", "첫 줄\n::warning::x\n##[error]y\n- 가짜 항목")], "제목").markdown()
        self.assertEqual(bad_lines(markdown), [])
        self.assertEqual([ln for ln in markdown.splitlines() if ln.startswith("- 가짜")], [])
        self.assertEqual(len([ln for ln in markdown.splitlines() if ln.startswith("- ❌")]), 1)

    def test_diff_block_cannot_be_closed_by_a_fence_line_inside_the_page(self):
        """검증자 F-8: 기본 파일에 ``` 줄이 있고 수정 위치 바로 옆이면 diff 의 맥락 줄이 백틱 펜스를 닫아 뒤의 +줄이 마크다운으로 살아났다."""
        hostile = "![추적 픽셀](https://evil.example/p.png) [로그인](https://evil.example/login) @octocat"
        ticks = "`" * 3
        before = ABOUT.replace(self.OLD, f"{self.OLD}\n\n{ticks}\n예시 코드\n{ticks}\n끝 문단입니다.")
        after = before.replace(self.OLD, self.NEW).replace("끝 문단입니다.", f"끝 문단입니다. {hostile}")
        files = {"b": before, "h": after}
        with tempfile.TemporaryDirectory() as tmp:
            root = make_edit_root(tmp)
            report = scope_check.check_pull(issue(page_body(before=self.OLD, after=self.NEW)), root, "b", "h",
                                            changes=[("M", "about.md")], show=lambda sha, path: files[sha])
        self.assertEqual((report.verdict, len(report.details)), ("FAIL", 1))
        markdown = report.markdown()
        self.assertEqual([ln for ln in lines_outside_fences(markdown) if any(frag in ln for frag in LIVE_MARKDOWN)], [])
        self.assertRegex(markdown, r"(?m)^~{4,}diff$")                          # 백틱 펜스가 아니라 내용보다 긴 틸드 펜스
        self.assertNotIn("```diff", markdown)

    def test_tilde_lines_in_the_page_cannot_close_the_diff_block_either(self):
        hostile = "![x](https://evil.example/p.png) @octocat"
        tildes = "~" * 6
        before = ABOUT.replace(self.OLD, f"{self.OLD}\n{tildes}\n끝 문단입니다.")
        after = before.replace(self.OLD, self.NEW).replace("끝 문단입니다.", f"끝 문단입니다. {hostile}")
        files = {"b": before, "h": after}
        with tempfile.TemporaryDirectory() as tmp:
            root = make_edit_root(tmp)
            report = scope_check.check_pull(issue(page_body(before=self.OLD, after=self.NEW)), root, "b", "h",
                                            changes=[("M", "about.md")], show=lambda sha, path: files[sha])
        self.assertEqual([ln for ln in lines_outside_fences(report.markdown()) if any(frag in ln for frag in LIVE_MARKDOWN)], [])


class FakeResponse:
    status = 200

    def __init__(self, payload=b""):
        self._payload = payload

    def read(self, *args):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


FAKE_UNSPLASH_KEY = "UNSPLASH" + "k" * 30                 # 가짜 키(외부 접속 없음)


class ImagePickerLogTest(RunnerBase):
    """검증자 F-2: 이미지 변경에서 production 선택기(default_image_picker → generator.pick_images)가 print 한 줄이
    `issue=#N` 머리 없이 러너 로그에 그대로 나갔다(`##[` 도 무력화되지 않았고 검색어 = AI 가 없으면 요청 원문 전체). 가짜 선택기만 쓰던 기존 테스트는 못 잡는다."""

    DESCRIPTION = "소방관 ##[add-mask]NOTASECRET ##[warning]스푸핑 경고 @everyone " + "자세한 설명 " * 20
    PHOTO = "https://images.unsplash.com/photo-1777777777777-abcdef123456?ixid=M3wx&ixlib=rb-4.0.3"
    TAG = "[issue-edit] issue=#12 author=@shine88pc(OWNER)"

    def fake_unsplash(self, behaviour="ok"):
        calls = []

        def fake_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            calls.append(url)
            if "api.unsplash.com/search/photos" in url:
                if behaviour == "forbidden":
                    raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
                body = {"results": [{"urls": {"raw": self.PHOTO}, "links": {"download_location": "https://api.unsplash.com/photos/x/download"}}]}
                return FakeResponse(json.dumps(body).encode("utf-8"))
            return FakeResponse(b"")                                            # HEAD 확인·download 알림
        return calls, fake_urlopen

    def run_image_issue(self, behaviour="ok"):
        calls, fake = self.fake_unsplash(behaviour)
        iss = issue(image_body("첫 번째 글 제목입니다", self.DESCRIPTION), labels=("blog-control", "edit:image"), title="[이미지 변경] x")
        with mock.patch("urllib.request.urlopen", fake), \
                mock.patch.multiple(generator, UNSPLASH_KEY=FAKE_UNSPLASH_KEY, STUB_UNSPLASH=False, DRY_RUN=False):
            code, out, files = run_main(self.root, iss, ["--dry-run"], env={"UNSPLASH_ACCESS_KEY": FAKE_UNSPLASH_KEY})
        return calls, code, out, files

    def assertQuiet(self, out):
        for line in out.splitlines():
            self.assertTrue(line.startswith(self.TAG), line)
        self.assertEqual(bad_lines(out), [])
        for fragment in ("스푸핑", "NOTASECRET", "@everyone", "query=", "이미지 선택", "자세한 설명"):
            self.assertNotIn(fragment, out)

    def test_generator_prints_never_reach_the_runner_log(self):
        calls, code, out, _files = self.run_image_issue()
        self.assertEqual(code, 0, out)
        self.assertGreaterEqual(len(calls), 3)                                   # 검색·HEAD 확인·download 알림 — 실제 선택기가 돌았다
        self.assertTrue(out.splitlines()[0].startswith(f"{self.TAG} status=ok"), out)
        self.assertQuiet(out)
        self.assertTrue(any("그 밖의 출력 1줄" in line for line in out.splitlines()), out)    # 가둔 출력은 줄 수만 알린다

    def test_unsplash_errors_are_summarised_without_the_query(self):
        calls, code, out, files = self.run_image_issue("forbidden")
        self.assertEqual(code, 0, out)
        self.assertTrue(calls)
        self.assertEqual(files["status.txt"].strip(), "rejected")
        self.assertTrue(any(line.startswith(f"{self.TAG}   * Unsplash API 오류 403") for line in out.splitlines()), out)
        self.assertQuiet(out)

    def captured(self, **patches):
        buf = io.StringIO()
        with mock.patch.multiple(generator, **patches), contextlib.redirect_stdout(buf):
            generator.search_unsplash("query ##[x]")
        return buf.getvalue()

    def test_summary_patterns_match_what_generator_really_prints(self):
        """generator.py 의 문구가 바뀌면 요약이 조용히 사라진다 — 실제 출력으로 대조한다."""
        def forbidden(req, timeout=None):
            raise urllib.error.HTTPError("https://api.unsplash.com/x", 403, "Forbidden", {}, None)

        def down(req, timeout=None):
            raise OSError("연결 실패 ##[x]")
        live = dict(UNSPLASH_KEY=FAKE_UNSPLASH_KEY, STUB_UNSPLASH=False, DRY_RUN=False)
        with mock.patch("urllib.request.urlopen", forbidden):
            self.assertEqual(runner.image_search_notes(self.captured(**live)), ["Unsplash API 오류 403 (403·429 이면 시간당 호출 한도 초과일 수 있습니다)"])
        with mock.patch("urllib.request.urlopen", down):
            notes = runner.image_search_notes(self.captured(**live))
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0].startswith("Unsplash 호출 실패"), notes)
        self.assertNotIn("연결 실패", notes[0])
        self.assertEqual(runner.image_search_notes(self.captured(STUB_UNSPLASH=True, DRY_RUN=False)),
                         ["UNSPLASH_ACCESS_KEY 없음: 이미지 검색을 건너뛰었습니다"])
        for needle in ("Unsplash API 오류", "Unsplash 호출 실패", "UNSPLASH_ACCESS_KEY 없음"):
            self.assertIn(needle, inspect.getsource(generator.search_unsplash))

    def test_image_search_notes_only_summarise_known_lines(self):
        self.assertEqual(runner.image_search_notes(""), [])
        self.assertEqual(runner.image_search_notes("\n   \n"), [])
        notes = runner.image_search_notes("  이미지 선택 (query='##[add-mask]x @everyone'): https://images.unsplash.com/photo-1\n"
                                          "  [경고] 검색 결과 없음 ::warning::x\n")
        self.assertEqual(len(notes), 1)
        self.assertIn("2줄", notes[0])
        self.assertNotIn("##[", notes[0])
        self.assertNotIn("everyone", notes[0])
        two = runner.image_search_notes("Unsplash API 오류 403 (query='a') - x\nUnsplash API 오류 403 (query='b') - x\nUnsplash API 오류 429 (query='c') - x\n")
        self.assertEqual(len(two), 2)                                             # 같은 코드는 한 번만, 다른 코드는 따로
        self.assertTrue(two[0].startswith("Unsplash API 오류 403") and two[1].startswith("Unsplash API 오류 429"))

    def test_picker_is_silent_and_restores_stdout_even_when_the_search_raises(self):
        notes, outer = [], io.StringIO()
        with mock.patch.dict(os.environ, {"UNSPLASH_ACCESS_KEY": FAKE_UNSPLASH_KEY}):
            def noisy(queries, used, count=1, allow_pool=False):
                print("  이미지 선택 (query='##[error]x'): https://images.unsplash.com/photo-1")
                raise RuntimeError("boom")
            with mock.patch.object(generator, "pick_images", noisy), contextlib.redirect_stdout(outer):
                picker = runner.default_image_picker(notes)
                inner_stdout = sys.stdout
                with self.assertRaises(RuntimeError):
                    picker(["q"], set())
                self.assertIs(sys.stdout, inner_stdout)                             # 가둔 뒤 되돌려 놓았다
            quiet = runner.default_image_picker()                                    # notes 를 받지 않아도 조용하다
            with mock.patch.object(generator, "pick_images", lambda *a, **k: print("x ##[y]") or []), contextlib.redirect_stdout(outer):
                self.assertIsNone(quiet(["q"], set()))
        self.assertEqual(outer.getvalue(), "")
        self.assertEqual(len(notes), 1)                                              # 실패 직전까지 나온 출력은 요약되어 남는다


if __name__ == "__main__":
    unittest.main()
