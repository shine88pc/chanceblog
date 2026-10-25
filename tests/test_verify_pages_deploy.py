"""Pages 배포 후 공개 사이트 반영 확인(scripts/verify_pages_deploy.py) 테스트. 네트워크 없이 돈다.

배경: 배포 워크플로가 초록이어도 글이 공개 사이트에 보인다는 보장은 없다(D-24 같은 빌드 실패, 캐시, 권한).
이 확인은 저장소의 가장 새 글이 공개 posts.json에 있고 그 주소가 열리는지를 본다.
"""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import verify_pages_deploy as v  # noqa: E402

BASE = "https://example.github.io/blog/"


def make_posts(root, names):
    """names: 'category/2026-10-25-KR-101307.md' 형태의 경로 목록을 임시 저장소의 _posts 아래에 만든다."""
    for name in names:
        path = Path(root) / "_posts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\ntitle: t\n---\n본문\n", encoding="utf-8")


def entry(rel, base=BASE):
    slug = Path(rel).name[11:-3]
    return {"path": rel, "absoluteUrl": f"{base}posts/{slug}/"}


class FakeSite:
    """공개 사이트 대역. posts: 공개 posts.json에 들어 있는 항목, pages: {주소: 상태}, 시도별로 달라지게 할 수 있다."""

    def __init__(self, posts_by_call, page_status=200):
        self.posts_by_call, self.page_status = posts_by_call, page_status
        self.requested, self.posts_calls = [], 0

    def __call__(self, url):
        self.requested.append(url)
        if "posts.json" in url:
            index = min(self.posts_calls, len(self.posts_by_call) - 1)
            self.posts_calls += 1
            value = self.posts_by_call[index]
            if isinstance(value, tuple):  # (상태, 본문 바이트)
                return value
            return 200, json.dumps(value, ensure_ascii=False).encode("utf-8")
        return self.page_status, b"<html></html>"


class NewestPostsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_returns_the_kr_en_pair_made_at_the_same_time(self):
        make_posts(self.root, ["기술·미래/2026-10-25-KR-101307.md", "Technology & Future/2026-10-25-EN-101307.md",
                               "기술·미래/2026-10-21-KR-135226.md"])
        self.assertEqual(v.newest_posts(self.root),
                         ["_posts/Technology & Future/2026-10-25-EN-101307.md", "_posts/기술·미래/2026-10-25-KR-101307.md"])

    def test_date_beats_time_and_time_breaks_ties_within_a_day(self):
        make_posts(self.root, ["a/2026-10-24-KR-235959.md", "a/2026-10-25-KR-000100.md", "a/2026-10-25-KR-090000.md"])
        self.assertEqual(v.newest_posts(self.root), ["_posts/a/2026-10-25-KR-090000.md"])

    def test_files_without_a_time_tail_count_as_midnight(self):
        make_posts(self.root, ["2026-10-19-AI.md", "2026-10-19-KR-000001.md"])
        self.assertEqual(v.newest_posts(self.root), ["_posts/2026-10-19-KR-000001.md"])

    def test_non_post_files_and_empty_tree_are_ignored(self):
        make_posts(self.root, ["README.md", "notes.txt"])
        self.assertEqual(v.newest_posts(self.root), [])
        self.assertEqual(v.newest_posts(self.root / "missing"), [])


class CheckOnceTest(unittest.TestCase):
    EXPECTED = ["_posts/기술·미래/2026-10-25-KR-101307.md", "_posts/Technology & Future/2026-10-25-EN-101307.md"]

    def run_check(self, site):
        return v.check_once(BASE, self.EXPECTED, "t", site)

    def test_all_present_and_reachable_has_no_problems(self):
        site = FakeSite([[entry(p) for p in self.EXPECTED]])
        problems, urls = self.run_check(site)
        self.assertEqual(problems, [])
        self.assertEqual(len(urls), 2)

    def test_missing_post_is_reported_by_path(self):
        site = FakeSite([[entry(self.EXPECTED[0])]])
        problems, urls = self.run_check(site)
        self.assertEqual(len(problems), 1)
        self.assertIn("공개 posts.json 에 없음", problems[0])
        self.assertIn("2026-10-25-EN-101307.md", problems[0])
        self.assertEqual(len(urls), 1)

    def test_page_that_does_not_open_is_a_problem(self):
        site = FakeSite([[entry(p) for p in self.EXPECTED]], page_status=404)
        problems, _ = self.run_check(site)
        self.assertEqual(len(problems), 2)
        self.assertIn("HTTP 404", problems[0])

    def test_posts_json_failures_are_problems_not_crashes(self):
        for value, expected in (((503, b""), "HTTP 503"), ((0, b"URLError"), "연결 실패"),
                                ((200, b"not json"), "JSON"), ((200, b'{"a": 1}'), "목록이 아님")):
            with self.subTest(value=value):
                problems, urls = self.run_check(FakeSite([value]))
                self.assertEqual(urls, [])
                self.assertIn(expected, problems[0])

    def test_entry_without_an_address_is_a_problem(self):
        site = FakeSite([[{"path": p} for p in self.EXPECTED]])
        problems, _ = self.run_check(site)
        self.assertEqual(len(problems), 2)
        self.assertIn("주소가 없음", problems[0])

    def test_every_request_carries_a_cache_buster(self):
        site = FakeSite([[entry(p) for p in self.EXPECTED]])
        self.run_check(site)
        self.assertTrue(site.requested)
        self.assertTrue(all("cb=t" in url for url in site.requested))


class VerifyTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        make_posts(self.root, ["기술·미래/2026-10-25-KR-101307.md", "Technology & Future/2026-10-25-EN-101307.md"])
        self.expected = v.newest_posts(self.root)
        patcher = mock.patch.dict(os.environ, {"GITHUB_SHA": "0123456789abcdef"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_verify(self, site, attempts=4, wait=30):
        sleeps = []
        buf = io.StringIO()
        with redirect_stdout(buf):
            ok, summary, lines, expected = v.verify(BASE, self.root, attempts, wait, fetcher=site,
                                                    sleep=sleeps.append)
        return ok, summary, sleeps, buf.getvalue(), expected

    def test_first_try_success_writes_the_commit_and_urls(self):
        site = FakeSite([[entry(p) for p in self.expected]])
        ok, summary, sleeps, out, _ = self.run_verify(site)
        self.assertTrue(ok)
        self.assertEqual(sleeps, [])
        self.assertIn("배포 커밋: 0123456", summary)
        self.assertIn("**반영됨**", summary)
        self.assertIn("시도 1회", summary)
        self.assertIn(BASE + "posts/KR-101307/", summary)

    def test_a_late_deploy_is_waited_for_and_then_passes(self):
        site = FakeSite([[], [entry(self.expected[0])], [entry(p) for p in self.expected]])
        ok, summary, sleeps, out, _ = self.run_verify(site, attempts=5, wait=7)
        self.assertTrue(ok)
        self.assertEqual(sleeps, [7, 7])
        self.assertIn("시도 3회", summary)
        self.assertIn("시도 1/5", out)

    def test_a_post_that_never_appears_fails_after_all_attempts(self):
        site = FakeSite([[]])
        ok, summary, sleeps, out, _ = self.run_verify(site, attempts=3, wait=30)
        self.assertFalse(ok)
        self.assertEqual(sleeps, [30, 30])  # 마지막 시도 뒤에는 기다리지 않는다
        self.assertIn("**반영 안 됨**", summary)
        self.assertIn("시도 3회(약 60초)", summary)
        self.assertIn("공개 posts.json 에 없음", summary)

    def test_no_posts_in_the_repository_is_skipped_not_failed(self):
        with tempfile.TemporaryDirectory() as empty:
            ok, summary, lines, expected = v.verify(BASE, empty, 3, 1, fetcher=FakeSite([[]]), sleep=lambda s: None)
        self.assertTrue(ok)
        self.assertEqual(expected, [])
        self.assertIn("건너뜀", summary)

    def test_summary_never_contains_external_text_beyond_paths_and_urls(self):
        evil = {"path": self.expected[0], "absoluteUrl": BASE + "x/\n::error::가짜", "title": "\n::error::제목"}
        for status in (200, 404):
            with self.subTest(page_status=status):
                site = FakeSite([[evil, entry(self.expected[1])]], page_status=status)
                ok, summary, sleeps, out, _ = self.run_verify(site, attempts=1)
                self.assertEqual(ok, status == 200)
                self.assertNotIn("\n::error::", summary)
                self.assertNotIn("\n::error::", out)


class FetchTest(unittest.TestCase):
    def test_http_errors_become_status_codes(self):
        def opener(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
        self.assertEqual(v.fetch(BASE + "x", opener=opener), (404, b""))

    def test_network_errors_become_status_zero(self):
        def opener(req, timeout=0):
            raise urllib.error.URLError("boom")
        status, body = v.fetch(BASE + "x", opener=opener)
        self.assertEqual(status, 0)
        self.assertEqual(body, b"URLError")

    def test_success_returns_status_and_body(self):
        class Resp:
            status = 200

            def read(self, n=-1):
                return b"ok"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        self.assertEqual(v.fetch(BASE + "x", opener=lambda req, timeout=0: Resp()), (200, b"ok"))


class HelpersTest(unittest.TestCase):
    def test_valid_base_requires_https_host_and_no_credentials(self):
        self.assertTrue(v.valid_base("https://example.github.io/blog/"))
        for bad in ("", "http://example.github.io/", "https://", "https://user:pw@example.github.io/",
                    "ftp://example.github.io/", "example.github.io"):
            with self.subTest(base=bad):
                self.assertFalse(v.valid_base(bad))

    def test_cache_buster_keeps_existing_query_and_encodes_the_token(self):
        self.assertEqual(v.with_cache_buster("https://a/b", "x y"), "https://a/b?cb=x%20y")
        self.assertEqual(v.with_cache_buster("https://a/b?q=1", "t"), "https://a/b?q=1&cb=t")

    def test_fold_makes_one_line_and_neutralises_commands(self):
        self.assertEqual(v.fold("a\n\nb  c"), "a b c")
        self.assertFalse(v.fold("::error::x").startswith("::"))
        self.assertEqual(len(v.fold("a" * 500, 50)), 50)


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        make_posts(self.root, ["a/2026-10-25-KR-101307.md"])
        self.summary = self.root / "summary.md"
        env = {k: val for k, val in os.environ.items() if k not in ("PAGE_URL", "GITHUB_SHA")}
        env["GITHUB_STEP_SUMMARY"] = str(self.summary)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, argv, site):
        buf = io.StringIO()
        with mock.patch.object(v, "fetch", site), mock.patch.object(v.time, "sleep", lambda s: None), \
                redirect_stdout(buf):
            code = v.main(argv)
        return code, buf.getvalue()

    def test_success_exit_zero_and_summary_file(self):
        site = FakeSite([[entry("_posts/a/2026-10-25-KR-101307.md")]])
        code, out = self.run_main(["--base", BASE.rstrip("/"), "--root", str(self.root)], site)
        self.assertEqual(code, 0)
        self.assertIn("반영됨", self.summary.read_text(encoding="utf-8"))
        self.assertTrue(site.requested[0].startswith(BASE + "posts.json"))  # 끝 슬래시를 보정한다

    def test_failure_exit_one_with_an_error_annotation(self):
        code, out = self.run_main(["--base", BASE, "--root", str(self.root), "--attempts", "2", "--wait", "0"],
                                  FakeSite([[]]))
        self.assertEqual(code, 1)
        self.assertIn("::error::공개 사이트에 최신 글이 반영되지 않았습니다", out)
        self.assertIn("반영 안 됨", self.summary.read_text(encoding="utf-8"))

    def test_page_url_environment_variable_is_the_default_base(self):
        site = FakeSite([[entry("_posts/a/2026-10-25-KR-101307.md")]])
        with mock.patch.dict(os.environ, {"PAGE_URL": BASE}):
            code, _ = self.run_main(["--root", str(self.root)], site)
        self.assertEqual(code, 0)

    def test_bad_base_or_counts_are_configuration_errors(self):
        for argv in (["--base", "http://example.github.io/"], [], ["--base", BASE, "--attempts", "0"],
                     ["--base", BASE, "--wait", "-1"]):
            with self.subTest(argv=argv):
                code, out = self.run_main(argv + ["--root", str(self.root)], FakeSite([[]]))
                self.assertEqual(code, 2)
                self.assertIn("::error::", out)


if __name__ == "__main__":
    unittest.main()
