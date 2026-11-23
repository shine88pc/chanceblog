"""Chance 엔진(generator.py)의 비밀 가리기가 Unsplash 키도 글자 그대로 가린다(독립 감사 BA-S1-10, 결함 D-411).

옛 `_scrub` 은 이 실행의 Gemini 키만 글자 그대로 바꿨다. Unsplash 접근 키는 접두사가 없어 모양 패턴(secret_patterns)이 없고, `Unsplash 호출 실패 … {_one_line(exc, 200)}` 두 줄은 `_scrub` 을 거치지 않았다.
지금은 키가 요청 머리글(`Authorization`)로만 가고 머리글 오류도 정리(clean_secret)해서 새는 길을 못 찾았지만, 방어선 하나가 '예외 문구에 키가 안 들어간다' 에만 기대고 있었다 — 다음 변경이 머리글이 아닌 곳에 키를
넣으면 가려지지 않는다. 그래서 `_scrub` 의 정확값 목록에 `UNSPLASH_KEY` 도 더하고(6자 이상일 때만 — `pipeline.llm.scrub` 의 규칙) 두 줄이 `_scrub` 을 거치게 했다.
시험은 네트워크 없이 `urllib.request.urlopen` 을 예외를 던지는 가짜로 바꾸고 표준 출력을 모아 본다. 가짜 키는 `CANARY` 로 시작하는 조립 문자열이다(소스에 완성된 키 모양을 두지 않는다).
"""
import ast
import contextlib
import io
import unittest
import urllib.error
from unittest import mock

import _bootstrap

import generator as g
from pipeline.llm import mask

ROOT = _bootstrap.ROOT
UNSPLASH = "CANARY" + "_" + "unsplash" + "KEY" + "-" + "zz99"
GEMINI = "CANARY" + "_" + "gemini" + "KEY" + "-" + "yy88"


class ScrubTest(unittest.TestCase):
    def scrub(self, text, unsplash=UNSPLASH, gemini=GEMINI):
        with mock.patch.object(g, "UNSPLASH_KEY", unsplash), mock.patch.object(g, "API_KEY", gemini):
            return g._scrub(text)

    def test_the_unsplash_key_is_replaced_literally_and_so_is_the_gemini_key(self):
        out = self.scrub(f"앞 {UNSPLASH} 가운데 {GEMINI} 뒤 {UNSPLASH}")
        self.assertNotIn(UNSPLASH, out)
        self.assertNotIn(GEMINI, out)
        self.assertEqual(out, "앞 *** 가운데 *** 뒤 ***")

    def test_the_unsplash_key_is_replaced_even_when_it_has_no_secret_shape(self):
        """모양 패턴에 안 걸리는 키(접두사 없는 긴 글자)여도 이 실행의 키이면 가린다 — 패턴이 아니라 정확값이 한다."""
        shapeless = "abcdefghijklmnopqrstuvwx0123456789"
        self.assertEqual(mask(shapeless), shapeless)                                   # 모양 패턴은 이 값을 못 본다
        self.assertEqual(self.scrub(f"Client-ID {shapeless}", unsplash=shapeless), "Client-ID ***")

    def test_a_key_shorter_than_six_characters_is_not_replaced_and_six_is(self):
        """짧은 값은 일반 낱말과 겹쳐 엉뚱한 곳이 가려지므로 바꾸지 않는다(pipeline.llm.scrub 의 최소 길이 6)."""
        self.assertEqual(self.scrub("abcde fgh", unsplash="abcde"), "abcde fgh")
        self.assertEqual(self.scrub("abcdef fgh", unsplash="abcdef"), "*** fgh")

    def test_a_missing_or_empty_key_is_ignored(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.assertEqual(self.scrub("그냥 글", unsplash=value, gemini=None), "그냥 글")

    def test_secret_shaped_text_is_still_masked_by_the_patterns(self):
        fake = "gh" + "p_" + "CANARY" + "F" * 30
        self.assertNotIn(fake, self.scrub(f"토큰 {fake}"))

    def test_a_non_text_exception_object_can_be_scrubbed(self):
        out = self.scrub(OSError(f"fail {UNSPLASH}"))
        self.assertNotIn(UNSPLASH, out)
        self.assertIn("fail", out)


class FailureLogTest(unittest.TestCase):
    """Unsplash 호출이 예외로 실패할 때 로그에 키가 글자 그대로 남지 않는다(검색 경로와 고정 목록 사진 조회 경로 둘 다)."""

    EXCEPTIONS = (OSError(f"connection with Client-ID {UNSPLASH} failed"), ValueError(f"Invalid header value b'Client-ID {UNSPLASH}\\n'"), RuntimeError(UNSPLASH),
                  Exception("앞 " + UNSPLASH + " 뒤 " + UNSPLASH), urllib.error.URLError(f"tunnel {UNSPLASH}"))

    def run_call(self, call, exc):
        out = io.StringIO()
        with (mock.patch.object(g, "UNSPLASH_KEY", UNSPLASH), mock.patch.object(g, "STUB_UNSPLASH", False), mock.patch.object(g, "DRY_RUN", False),
              mock.patch.object(g.urllib.request, "urlopen", side_effect=exc), contextlib.redirect_stdout(out)):
            result = call()
        return result, out.getvalue()

    def test_a_failed_search_logs_the_failure_without_the_key(self):
        for exc in self.EXCEPTIONS:
            with self.subTest(exc=type(exc).__name__):
                result, text = self.run_call(lambda: g.search_unsplash("cats"), exc)
                self.assertEqual(result, [])
                self.assertIn("Unsplash 호출 실패", text)
                self.assertNotIn(UNSPLASH, text)
                self.assertIn("***", text)                                              # 가린 자리는 남아 읽을 수 있다

    def test_a_failed_pool_photo_lookup_logs_the_failure_without_the_key(self):
        for exc in self.EXCEPTIONS:
            with self.subTest(exc=type(exc).__name__):
                result, text = self.run_call(lambda: g.fetch_pool_photo(g.IMAGE_POOL[0]), exc)
                self.assertIsNone(result)
                self.assertIn("Unsplash 호출 실패 (사진 조회)", text)
                self.assertNotIn(UNSPLASH, text)
                self.assertIn("***", text)

    def test_http_errors_print_only_the_status_code(self):
        error = urllib.error.HTTPError("https://example.invalid/x", 403, f"Client-ID {UNSPLASH}", {}, None)
        for call in (lambda: g.search_unsplash("cats"), lambda: g.fetch_pool_photo(g.IMAGE_POOL[0])):
            result, text = self.run_call(call, error)
            self.assertNotIn(UNSPLASH, text)
            self.assertIn("Unsplash API 오류 403", text)

    def test_the_log_line_is_one_line_and_cut(self):
        long_text = "앞 " + UNSPLASH + "가" * 1000 + UNSPLASH + "나" * 1000                  # 키가 앞 200자 안에도 있어 가리지 않으면 잘린 글에도 남는다
        result, text = self.run_call(lambda: g.search_unsplash("cats"), RuntimeError(long_text))
        failure = [line for line in text.splitlines() if "Unsplash 호출 실패" in line]
        self.assertEqual(len(failure), 1)
        self.assertLess(len(failure[0]), 400)
        self.assertNotIn(UNSPLASH, text)

    def test_the_whole_run_failure_line_also_hides_the_unsplash_key(self):
        """`작업 실패` 줄은 이미 `_scrub` 을 거친다 — 정확값 목록이 늘어 Unsplash 키도 가려진다."""
        with mock.patch.object(g, "UNSPLASH_KEY", UNSPLASH), mock.patch.object(g, "API_KEY", GEMINI):
            line = g._one_line(g._scrub(RuntimeError(f"boom {UNSPLASH} {GEMINI}")), 600)
        self.assertNotIn(UNSPLASH, line)
        self.assertNotIn(GEMINI, line)


class SourceGuardTest(unittest.TestCase):
    """소스 점검: 'Unsplash 호출 실패' 를 찍는 모든 줄이 `_scrub` 을 거친다(다음 변경이 한 줄을 빼먹지 못하게)."""

    def prints_with(self, needle):
        tree = ast.parse((ROOT / "generator.py").read_text(encoding="utf-8"))
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                text = ast.unparse(node)
                if needle in text:
                    found.append(text)
        return found

    def test_every_unsplash_failure_print_goes_through_scrub(self):
        lines = self.prints_with("Unsplash 호출 실패")
        self.assertEqual(len(lines), 2)                                                  # 검색 경로와 사진 조회 경로
        for text in lines:
            self.assertIn("_scrub(exc)", text)

    def test_the_scrub_function_lists_both_keys(self):
        tree = ast.parse((ROOT / "generator.py").read_text(encoding="utf-8"))
        scrub_def = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_scrub")
        source = ast.unparse(scrub_def)
        self.assertIn("API_KEY", source)
        self.assertIn("UNSPLASH_KEY", source)

    def test_the_source_check_really_sees_a_missing_scrub(self):
        bad = 'print(f"Unsplash 호출 실패 (query={query!r}): {_one_line(exc, 200)}")'
        self.assertNotIn("_scrub(exc)", ast.unparse(ast.parse(bad).body[0]))


if __name__ == "__main__":
    unittest.main()
