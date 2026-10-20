import io
import os
import subprocess
import sys
import unittest

import _bootstrap  # noqa: F401
from pipeline.console import safe_output


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


if __name__ == "__main__":
    unittest.main()
