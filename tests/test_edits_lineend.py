"""줄 끝(LF/CRLF) 처리의 회귀 테스트 — docs/DEFECT_REGISTER.md D-23(줄 끝만 바뀐 PR이 통과로 보임).

실제 git 임시 저장소(autocrlf 끔)로 PR 변경 범위 검사의 판정을 확인하고, 러너는 줄 끝이 섞인 파일을 거부(fail closed)한다.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from edits_helpers import ABOUT, issue, make_edit_root, page_body, write
from pipeline.edits import frontmatter, runner, scope_check
from test_edits_runner import NEW_SENTENCE, OLD_SENTENCE, RunnerBase


def crlf(text):
    return text.replace("\n", "\r\n")


def git(root, *args):
    """autocrlf 를 끈 git(줄 끝 변환이 없어 우리가 쓴 바이트가 그대로 커밋된다)."""
    cmd = ["git", "-c", "core.autocrlf=false", "-c", "core.safecrlf=false", "-c", "user.name=t", "-c", "user.email=t@example.com", *args]
    return subprocess.run(cmd, cwd=root, check=True, capture_output=True).stdout.decode("utf-8", "replace").strip()


class LineEndingKindTest(unittest.TestCase):
    def test_kinds(self):
        table = [("", "none"), ("한 줄", "none"), ("a\n", "lf"), ("a\nb\nc", "lf"), ("a\r\n", "crlf"), ("a\r\nb\r\n", "crlf"),
                 ("a\rb", "cr"), ("a\r\nb\n", "mixed"), ("a\nb\r\n", "mixed"), ("a\n\rb", "mixed"), ("a\r\r\nb", "mixed"),
                 ("a\r\n\r\n", "crlf")]
        for text, want in table:
            self.assertEqual(frontmatter.line_ending_kind(text), want, repr(text))

    def test_strict_read_refuses_mixed_and_cr_but_plain_read_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, raw, strict_fails in (("lf.md", b"a\nb\n", False), ("crlf.md", b"a\r\nb\r\n", False), ("none.md", b"a", False),
                                            ("mixed.md", b"a\r\nb\n", True), ("cr.md", b"a\rb\r", True)):
                path = Path(tmp) / name
                path.write_bytes(raw)
                if strict_fails:
                    with self.assertRaises(frontmatter.LineEndingError):
                        frontmatter.read_file(path, strict=True)
                    frontmatter.read_file(path)      # 읽기만 하는 다른 호출자(페이지 목록 등)는 영향이 없다
                else:
                    text, newline = frontmatter.read_file(path, strict=True)
                    self.assertEqual(newline, "\r\n" if raw.count(b"\r\n") else "\n")
                    self.assertNotIn("\r", text)


class RunnerRefusesMixedLineEndingsTest(RunnerBase):
    def literal(self):
        return self.go(issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE)))

    def test_mixed_and_cr_only_targets_are_refused_and_left_untouched(self):
        for name, raw in (("mixed", ABOUT.replace("\n", "\r\n", 4)), ("cr only", ABOUT.replace("\n", "\r")),
                          ("lf then crlf", ABOUT + "\r\n마지막 줄\r\n")):
            write(self.root, "about.md", raw)
            before = (self.root / "about.md").read_bytes()
            res = self.literal()
            self.assertEqual((res.status, res.exit_code), ("error", runner.EXIT_CONFIG), name)
            self.assertIn("줄 끝", res.message, name)
            self.assertEqual(res.files, [], name)
            self.assertEqual((self.root / "about.md").read_bytes(), before, name)

    def test_consistent_lf_and_crlf_targets_are_still_edited_and_keep_their_endings(self):
        for newline in ("\n", "\r\n"):
            write(self.root, "about.md", ABOUT.replace("\n", newline))
            res = self.literal()
            self.assertEqual(res.status, "ok", repr(newline))
            raw = (self.root / "about.md").read_bytes().decode("utf-8")
            self.assertEqual(frontmatter.line_ending_kind(raw), "crlf" if newline == "\r\n" else "lf")
            self.assertIn(NEW_SENTENCE, raw)


class RealGitScopeCheckLineEndingTest(unittest.TestCase):
    """실제 git 임시 저장소(autocrlf 끔) 4 시나리오: 정규화해서 비교하던 때는 2·3번이 '변경 없음'·거짓 문구 PASS 로 보였다.

    git 프로세스 생성이 느린 환경(Windows 보안 프로그램)에서 시간을 아끼려고 시나리오별 커밋을 `git fast-import` 한 번으로 만든다.
    blob 은 우리가 쓴 바이트 그대로다(autocrlf 를 끈 저장소와 같다)."""

    SCENARIOS = {
        "s1": (ABOUT, ABOUT.replace(OLD_SENTENCE, NEW_SENTENCE)),                         # 교체만
        "s2": (ABOUT, crlf(ABOUT)),                                                        # 줄 끝만 CRLF 로
        "s3": (ABOUT, crlf(ABOUT.replace(OLD_SENTENCE, NEW_SENTENCE))),                    # 교체 + 전체 CRLF
        "s4": (crlf(ABOUT), crlf(ABOUT.replace(OLD_SENTENCE, NEW_SENTENCE))),              # CRLF 로 저장된 파일을 CRLF 그대로 교체
    }

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.root = make_edit_root(cls._tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=cls.root, check=True, capture_output=True)
        with open(Path(cls.root) / ".git" / "config", "ab") as fh:     # autocrlf 끔(저장소 로컬 설정이 시스템 설정보다 우선)
            fh.write(b"[core]\n\tautocrlf = false\n\tsafecrlf = false\n")
        stream = b""
        for mark, (name, (base, head)) in enumerate(cls.SCENARIOS.items(), 1):
            for kind, raw, parent in (("base", base, None), ("head", head, f"refs/heads/{name}_base")):
                body = raw.encode("utf-8")
                message = f"{name} {kind}".encode()
                stream += b"commit refs/heads/%s_%s\n" % (name.encode(), kind.encode())
                stream += b"committer t <t@example.com> %d +0000\n" % (1700000000 + mark)
                stream += b"data %d\n%s\n" % (len(message), message)
                if parent:
                    stream += b"from %s\n" % parent.encode()
                stream += b"M 100644 inline about.md\ndata %d\n%s\n\n" % (len(body), body)
        subprocess.run(["git", "fast-import", "--quiet"], cwd=cls.root, input=stream, check=True, capture_output=True)
        cls.autocrlf = git(cls.root, "config", "core.autocrlf")

    def scope(self, name):
        iss = issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE))
        return scope_check.check_pull(iss, self.root, f"refs/heads/{name}_base", f"refs/heads/{name}_head")

    def test_autocrlf_is_off_and_blobs_keep_their_bytes(self):
        self.assertEqual(self.autocrlf, "false")
        for name, (base, head) in self.SCENARIOS.items():
            self.assertEqual(scope_check.git_show(self.root, f"refs/heads/{name}_base", "about.md"), base)
            self.assertEqual(scope_check.git_show(self.root, f"refs/heads/{name}_head", "about.md"), head)

    def test_1_replacement_only_passes(self):
        report = self.scope("s1")
        self.assertEqual(report.verdict, "PASS", report.items)
        self.assertIn("정확히 일치", report.markdown())

    def test_2_line_endings_only_change_fails_with_an_accurate_message(self):
        report = self.scope("s2")
        text = report.markdown()
        self.assertEqual(report.verdict, "FAIL", report.items)
        self.assertIn("줄 끝(LF/CRLF)만 바뀌었습니다", text)
        self.assertIn("LF → CRLF", text)
        self.assertNotIn("바뀐 내용이 없습니다", text)     # 예전의 부정확한 문구
        self.assertNotIn("정확히 일치", text)

    def test_3_replacement_plus_whole_file_crlf_fails_and_makes_no_false_claim(self):
        report = self.scope("s3")
        text = report.markdown()
        self.assertEqual(report.verdict, "FAIL", report.items)
        self.assertIn("줄 끝 형식이 바뀌었", text)
        self.assertNotIn("하나도 바뀌지 않았습니다", text)   # 예전에는 이 거짓 문구와 함께 PASS 였다
        self.assertNotIn("정확히 일치하는 변경입니다", text)

    def test_4_crlf_stored_file_edited_consistently_passes(self):
        report = self.scope("s4")
        self.assertEqual(report.verdict, "PASS", report.items)
        self.assertIn("정확히 일치", report.markdown())


class LineEndingJudgementTest(unittest.TestCase):
    """git 없이(파일 원본을 주입) 나머지 변형을 확인한다."""

    def judge(self, before, after):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_edit_root(tmp)
            files = {"b": before, "h": after}
            return scope_check.check_pull(issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE)), root, "b", "h",
                                          changes=[("M", "about.md")], show=lambda sha, path: files[sha])

    def test_crlf_to_lf_conversion_fails(self):
        report = self.judge(crlf(ABOUT), ABOUT.replace(OLD_SENTENCE, NEW_SENTENCE))
        self.assertEqual(report.verdict, "FAIL", report.items)
        self.assertIn("CRLF → LF", report.markdown())

    def test_mixed_line_endings_cannot_be_proven_and_fail(self):
        replaced = ABOUT.replace(OLD_SENTENCE, NEW_SENTENCE)
        for before, after in ((ABOUT, replaced.replace("\n", "\r\n", 2)),
                              (ABOUT.replace("\n", "\r\n", 2), replaced.replace("\n", "\r\n", 2))):
            report = self.judge(before, after)
            self.assertEqual(report.verdict, "FAIL", report.items)
            self.assertIn("혼합", report.markdown())

    def test_cr_only_files_cannot_be_proven_even_when_both_sides_are_cr_only(self):
        """검증자 V05: 유형이 달라서가 아니라 CR 단독 자체가 문제다 — 같은 CR 단독끼리의 변경도 줄 단위로 증명할 수 없어 거부한다."""
        before = ABOUT.replace("\n", "\r")
        report = self.judge(before, before.replace(OLD_SENTENCE, NEW_SENTENCE))
        self.assertEqual(report.verdict, "FAIL", report.items)
        self.assertIn("CR 단독", report.markdown())
        report = self.judge(ABOUT, before.replace(OLD_SENTENCE, NEW_SENTENCE))             # LF → CR 단독은 유형 변경이기도 하다
        self.assertEqual(report.verdict, "FAIL", report.items)

    def test_files_without_any_newline_are_not_flagged(self):
        report = self.judge("한 줄 " + OLD_SENTENCE, "한 줄 " + NEW_SENTENCE)
        self.assertNotIn("줄 끝", report.markdown())

    def test_going_from_or_to_no_newline_at_all_is_not_a_line_ending_change(self):
        """줄바꿈이 하나도 없던 파일에 끝 줄바꿈이 생기거나 그 반대인 것은 '줄 끝 형식 변경'이 아니다(다른 검사가 판단한다)."""
        for before, after in (("한 줄 " + OLD_SENTENCE, "한 줄 " + NEW_SENTENCE + "\n"), ("한 줄 " + OLD_SENTENCE + "\n", "한 줄 " + NEW_SENTENCE),
                              ("한 줄 " + OLD_SENTENCE, "한 줄 " + NEW_SENTENCE + "\r\n")):
            text = self.judge(before, after).markdown()
            self.assertNotIn("줄 끝", text, (before, after))


if __name__ == "__main__":
    unittest.main()
