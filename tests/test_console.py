import io
import os
import subprocess
import sys
import unittest

import _bootstrap  # noqa: F401
from pipeline.console import md_cell, one_line, safe_output


class SafeOutputTest(unittest.TestCase):
    def setUp(self):
        self._saved = (sys.stdout, sys.stderr)

    def tearDown(self):
        sys.stdout, sys.stderr = self._saved

    def test_unencodable_characters_do_not_raise(self):
        raw = io.BytesIO()
        sys.stdout = io.TextIOWrapper(raw, encoding="cp949", errors="strict", write_through=True)
        with self.assertRaises(UnicodeEncodeError):  # 전제: 보호 전에는 실제로 예외가 난다
            print("통과 — 끝")
        safe_output()
        print("통과 — 끝 ✅")
        out = raw.getvalue()
        self.assertIn("통과".encode("cp949"), out)  # 한글은 그대로
        self.assertIn(b"?", out)                    # 표현 못 하는 문자만 대체

    def test_streams_without_reconfigure_are_left_alone(self):
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        safe_output()  # StringIO 에는 reconfigure 가 없다 — 예외 없이 지나가야 한다
        print("ok")
        self.assertEqual(sys.stdout.getvalue(), "ok\n")

    def test_fresh_interpreter_with_cp949_stdout(self):
        env = dict(os.environ, PYTHONIOENCODING="cp949", PYTHONPATH=_bootstrap.ROOT.as_posix())
        env.pop("PYTHONUTF8", None)
        proc = subprocess.run(
            [sys.executable, "-c", "from pipeline.console import safe_output; safe_output(); print('통과 — ✅')"],
            capture_output=True, env=env, cwd=_bootstrap.ROOT.as_posix(), timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("cp949", "replace"))
        self.assertIn("통과".encode("cp949"), proc.stdout)


class OneLineTest(unittest.TestCase):
    """외부 유래 문자열(LLM 제목, 피드에서 온 다른 블로그 이력 제목, API 오류 문구)을 로그에 넣기 전의 정화."""

    def test_every_line_break_and_control_character_becomes_one_space(self):
        raw = "가\n나\r다\r\n라\u2028마\u2029바\x85사\t아\x0b자\x0c차\x1b카\x00타"
        self.assertEqual(one_line(raw), "가 나 다 라 마 바 사 아 자 차 카 타")
        self.assertEqual(one_line("  앞뒤   공백\u00a0\u00a0정리  "), "앞뒤 공백 정리")

    def test_workflow_command_markers_are_defanged_wherever_they_appear(self):
        # 러너는 줄 맨 앞(앞 공백은 무시)의 '::' 를 명령으로 읽는다. 앞에 공백을 붙이는 방식으로는 막을 수 없다.
        for raw in ("::error::위조", "앞 줄\n::warning::위조", "   ::add-mask::x", "a::b", ":::x", "##[error]위조", "###[group]x"):
            flat = one_line(raw)
            self.assertNotIn("::", flat, raw)
            self.assertNotIn("##[", flat, raw)
            self.assertFalse(flat.lstrip().startswith(("::", "##[")), raw)
        self.assertIn("error", one_line("::error::위조"))  # 내용은 읽을 수 있게 남는다

    def test_length_limit_includes_the_ellipsis_and_non_strings_are_accepted(self):
        flat = one_line("가" * 500, 100)
        self.assertEqual(len(flat), 100)
        self.assertTrue(flat.endswith("…"))
        self.assertEqual(one_line("짧은 글", 100), "짧은 글")
        self.assertEqual(one_line(None), "")
        self.assertEqual(one_line(["a\nb", 3]).splitlines(), [one_line(["a\nb", 3])])

    def test_md_cell_removes_table_link_html_and_code_syntax(self):
        cell = md_cell("제목 | 표 `코드` <b>굵게</b> [클릭](https://evil.example)\n| --- | --- |\n## 가짜 제목")
        for char in "|`<>[]":
            self.assertNotIn(char, cell)
        self.assertNotIn("](", cell)
        self.assertEqual(cell.splitlines(), [cell])
        self.assertIn("클릭", cell)  # 내용은 읽을 수 있게 남는다
        self.assertLessEqual(len(md_cell("가" * 500)), 120)


if __name__ == "__main__":
    unittest.main()
