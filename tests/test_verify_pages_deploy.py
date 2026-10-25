"""Pages 배포 후 공개 사이트 반영 확인(scripts/verify_pages_deploy.py) 테스트. 네트워크·실제 sleep 없이 돈다.

배경: 배포 워크플로가 초록이어도 새 글이 공개 주소에서 열린다는 보장은 없다(빌드 산출물에서 글이 빠짐, CDN 캐시 지연).
이 확인은 저장소의 가장 새 글(공개될 것)의 공개 주소가 HTTP 200으로 열리는지 본다.
이 확인이 못 잡는 것: 글을 추가하지 않은 커밋(이미지 교체·기존 글 수정)의 반영 실패, Jekyll 빌드 자체의 실패(D-24형 —
build 단계가 먼저 빨강이 되고 verify 잡은 건너뛰어진다).
글 선정·주소 계산은 test_verify_pages_select.py, 이 파일은 요청·재시도·마감·요약·종료 코드·워크플로를 본다.
"""
import email.message
import http.client
import io
import os
import re
import socket
import ssl
import tempfile
import types
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from verify_pages_helpers import (BASE, EN, EN_URL, INDEX, KR, KR_URL, NOW, SITE_CONFIG, FakeClock, FakeSite, Flushy, down,
                                  entries, index_resp, make_repo, page, post_of, v)

KR_POST = post_of("2026-10-25-KR-101307.md", folder="기술·미래")
EN_POST = post_of("2026-10-25-EN-101307.md", folder="Technology & Future")
POSTS = [EN_POST, KR_POST]  # rel 순서
CONFIG = {"timezone": "Asia/Seoul", "permalink": "/posts/:year/:month/:day/:title/"}
OLD_KR, OLD_EN = "a/2020-01-01-KR-101307.md", "b/2020-01-01-EN-101307.md"  # 실제 시계로도 과거인 글(main 테스트용)
OLD_KR_URL, OLD_EN_URL = BASE + "posts/2020/01/01/KR-101307/", BASE + "posts/2020/01/01/EN-101307/"


def full_routes(headers=None):
    return {KR_URL: page(200, headers), EN_URL: page(200, headers),
            INDEX: index_resp(entries((KR, KR_URL), (EN, EN_URL)))}


def check(site, posts=POSTS, config=CONFIG, attempt=1, past_deadline=False, deadline=720, token="t"):
    """check_once 를 가짜 사이트로 한 번 돌린다."""
    clock = FakeClock()
    if site.clock is None:
        site.clock = clock
    request = v.Requester(site, clock, deadline)
    request.attempt = attempt
    if past_deadline:
        clock.t = deadline + 1000.0
    return v.check_once(BASE, posts, config, v.site_timezone(config), request, token)


class FoldTest(unittest.TestCase):
    def test_makes_one_line_and_limits_length(self):
        self.assertEqual(v.fold("a\n\nb  c"), "a b c")
        self.assertEqual(len(v.fold("a" * 500, 50)), 50)
        self.assertEqual(v.fold("a ::error::x"), "a ::error::x")  # 줄 머리만 문제다

    def test_no_line_can_start_a_workflow_command(self):
        for payload in ("::error::x", " ::error::x", "\n::error::x", "\r::warning::x", "\x1c::error::x", "\x0b::error::x",
                        "\u0085::error::x", chr(0x2028) + "::error::x", chr(0x3000) + "::error::x", "   ::set-output name=a::b",
                        "\t::add-mask::s", chr(0xFEFF) + "::error::x"):
            with self.subTest(payload=payload):
                folded = v.fold(payload)
                if folded.lstrip(chr(0xFEFF)) != folded:  # BOM 은 러너도 지우지 않는 보이지 않는 문자라 그대로 두어도 명령이 아니다
                    continue
                self.assertFalse(folded.lstrip().startswith("::"))
                self.assertTrue(folded.startswith("→ "))
                self.assertIn("::", folded)  # 내용은 남긴다

    def test_legacy_command_marker_is_neutralised_anywhere(self):
        for payload in ("##[error]x", "a ##[warning]b", "\n##[group]g", "###[error]x"):
            with self.subTest(payload=payload):
                self.assertNotIn("##[", v.fold(payload))
        self.assertEqual(v.fold("##[error]x"), "# [error]x")

    def test_code_spans_cannot_be_broken_or_autolinked(self):
        self.assertEqual(v.code("a`b"), "`a'b`")
        self.assertEqual(v.code(""), "`(없음)`")
        self.assertEqual(v.code("a\nb"), "`a b`")
        self.assertEqual(v.code("::error::x"), "`→ ::error::x`")
        self.assertEqual(len(v.code("x" * 500, 20)), 22)
        self.assertEqual(v.code("https://a/b"), "`https://a/b`")

    def test_log_folds_and_flushes_each_line(self):
        buf = Flushy()
        with redirect_stdout(buf):
            v.log("한 줄\n::error::가짜")
            v.log("::error::바로")
            v.log("x" * 1000)
        lines = buf.getvalue().splitlines()
        self.assertEqual(lines[0], "한 줄 ::error::가짜")
        self.assertEqual(lines[1], "→ ::error::바로")
        self.assertEqual(len(lines[2]), 400)
        self.assertGreaterEqual(buf.flushes, 3)


class Response:
    """urlopen 이 돌려주는 응답 대역."""

    def __init__(self, status=200, body=b"ok", headers=None, raw_headers=None):
        self.status, self.body = status, body
        if raw_headers is not None:
            self.headers = raw_headers
        else:
            self.headers = email.message.Message()
            for key, value in (headers or {}).items():
                self.headers[key] = value
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return self.body if size < 0 else self.body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_for(result):
    """result 가 예외면 던지고 아니면 돌려주는 opener. 호출 기록은 opener.calls."""
    calls = []

    def opener(req, timeout=None):
        calls.append((req, timeout))
        if isinstance(result, BaseException):
            raise result
        return result

    opener.calls = calls
    return opener


class FetchTest(unittest.TestCase):
    def test_success_returns_status_body_and_only_the_diagnostic_headers(self):
        response = Response(200, b"hello", {"Age": "12", "Last-Modified": "Sun, 25 Oct 2026 01:13:51 GMT",
                                            "Cache-Control": "max-age=600", "X-Cache": "HIT", "Set-Cookie": "secret=1"})
        resp = v.fetch(BASE + "x", opener=opener_for(response))
        self.assertEqual(resp, v.Resp(200, b"hello", {"age": "12", "last-modified": "Sun, 25 Oct 2026 01:13:51 GMT",
                                                      "cache-control": "max-age=600", "x-cache": "HIT"}, ""))

    def test_header_values_are_folded_and_capped(self):
        response = Response(200, raw_headers={"age": "1\n::error::x", "last-modified": "y" * 500, "cache-control": ""})
        headers = v.fetch(BASE + "x", opener=opener_for(response)).headers
        self.assertEqual(headers["age"], "1 ::error::x")
        self.assertEqual(len(headers["last-modified"]), 80)
        self.assertNotIn("cache-control", headers)

    def test_request_carries_user_agent_no_cache_and_the_short_timeout(self):
        opener = opener_for(Response())
        v.fetch(BASE + "x", opener=opener)
        request, timeout = opener.calls[0]
        self.assertEqual(request.get_header("User-agent"), v.USER_AGENT)
        self.assertEqual(request.get_header("Cache-control"), "no-cache")
        self.assertEqual(request.full_url, BASE + "x")
        self.assertEqual(timeout, 15)
        self.assertEqual(v.REQUEST_TIMEOUT, 15)
        opener = opener_for(Response())
        v.fetch(BASE + "x", timeout=3, opener=opener)
        self.assertEqual(opener.calls[0][1], 3)

    def test_body_read_is_bounded_by_the_limit(self):
        response = Response(200, b"x" * 500)
        v.fetch(BASE + "x", opener=opener_for(response))
        self.assertEqual(response.read_sizes, [v.MAX_BYTES + 1])
        response = Response(200, b"x" * 500)
        resp = v.fetch(BASE + "x", opener=opener_for(response), limit=100)
        self.assertEqual(response.read_sizes, [101])
        self.assertEqual(len(resp.body), 101)

    def test_status_is_passed_through(self):
        for status in (200, 204, 206, 301, 302):
            with self.subTest(status=status):
                self.assertEqual(v.fetch(BASE + "x", opener=opener_for(Response(status))).status, status)

    def test_http_errors_become_statuses_with_headers(self):
        headers = email.message.Message()
        headers["Age"] = "5"
        exc = urllib.error.HTTPError(BASE + "x", 404, "nf", headers, None)
        self.assertEqual(v.fetch(BASE + "x", opener=opener_for(exc)), v.Resp(404, b"", {"age": "5"}, ""))
        exc = urllib.error.HTTPError(BASE + "x", 503, "unavailable", None, None)
        self.assertEqual(v.fetch(BASE + "x", opener=opener_for(exc)), v.Resp(503, b"", {}, ""))

    def test_every_other_failure_becomes_status_zero_with_the_error_name(self):
        cases = ((urllib.error.URLError("boom"), "URLError"),
                 (urllib.error.URLError(socket.gaierror(-2, "x")), "URLError/gaierror"),
                 (TimeoutError(), "TimeoutError"), (ConnectionResetError(), "ConnectionResetError"), (OSError("x"), "OSError"),
                 (ssl.SSLError("x"), "SSLError"), (http.client.IncompleteRead(b"x"), "IncompleteRead"),
                 (http.client.BadStatusLine("x"), "BadStatusLine"), (http.client.InvalidURL("x"), "InvalidURL"),
                 (http.client.RemoteDisconnected("x"), "RemoteDisconnected"),
                 (UnicodeEncodeError("ascii", "한", 0, 1, "x"), "UnicodeEncodeError"), (ValueError("x"), "ValueError"))
        for exc, name in cases:
            with self.subTest(error=name):
                resp = v.fetch(BASE + "x", opener=opener_for(exc))
                self.assertEqual((resp.status, resp.body, resp.headers, resp.error), (0, b"", {}, name))

    def test_a_malformed_address_is_a_failure_not_an_exception(self):
        for url in ("not a url", "", "://x"):
            with self.subTest(url=url):
                resp = v.fetch(url)  # Request 생성에서 ValueError 가 나는 주소라 접속하지 않는다
                self.assertEqual((resp.status, resp.error), (0, "ValueError"))

    def test_the_error_message_is_never_copied(self):
        resp = v.fetch(BASE + "x", opener=opener_for(OSError("\n::error::주입")))
        self.assertNotIn("주입", resp.error)

    def test_keyboard_interrupt_is_not_swallowed(self):
        with self.assertRaises(KeyboardInterrupt):
            v.fetch(BASE + "x", opener=opener_for(KeyboardInterrupt()))


class UrlHelpersTest(unittest.TestCase):
    def test_valid_base_requires_https_host_and_no_credentials_query_or_fragment(self):
        for good in ("https://example.github.io/blog/", "https://example.github.io", "https://example.github.io:8443/x/"):
            with self.subTest(base=good):
                self.assertTrue(v.valid_base(good))
        for bad in ("", "http://example.github.io/", "https://", "https:///x", "https://user:pw@example.github.io/",
                    "ftp://example.github.io/", "example.github.io", "https://example.github.io/?a=1",
                    "https://example.github.io/#frag", "https://[abc/"):
            with self.subTest(base=bad):
                self.assertFalse(v.valid_base(bad))

    def test_same_origin_https(self):
        for good in (BASE + "x/", "https://EXAMPLE.github.io/blog/x/", "https://example.github.io:443/x/",
                     "https://example.github.io/other-path/"):
            with self.subTest(url=good):
                self.assertTrue(v.same_origin_https(good, BASE))
        for bad in ("http://example.github.io/blog/x/", "https://other.github.io/blog/x/", "https://sub.example.github.io/x/",
                    "https://example.github.io.evil.com/x", "https://example.github.io:8443/x/", "https://user@example.github.io/x",
                    "https://example.github.io/a b/", "https://example.github.io/a\nb", "https://example.github.io/a\x00b",
                    "https://example.github.io/\x7f", "ftp://example.github.io/x", "file:///x", "javascript:alert(1)", "",
                    None, 5, ["https://example.github.io/"], "https://[abc/", "https://example.github.io:99999999/x",
                    "//example.github.io/x"):
            with self.subTest(url=bad):
                self.assertFalse(v.same_origin_https(bad, BASE))
        self.assertTrue(v.same_origin_https("https://example.github.io:8443/x", "https://example.github.io:8443/blog/"))
        self.assertFalse(v.same_origin_https("https://example.github.io/x", "https://example.github.io:8443/blog/"))

    def test_same_url_ignores_percent_encoding_case_only(self):
        self.assertTrue(v.same_url("https://a/%ed%95%9c/", "https://a/%ED%95%9C/"))
        self.assertTrue(v.same_url("https://a/한/", "https://a/%ED%95%9C/"))
        self.assertFalse(v.same_url("https://a/x/", "https://a/x"))

    def test_cache_buster_keeps_existing_query_and_encodes_the_token(self):
        self.assertEqual(v.with_cache_buster("https://a/b", "x y"), "https://a/b?cb=x%20y")
        self.assertEqual(v.with_cache_buster("https://a/b?q=1", "t"), "https://a/b?q=1&cb=t")
        self.assertEqual(v.with_cache_buster("https://a/b#f", "t"), "https://a/b?cb=t#f")

    def test_status_label(self):
        self.assertEqual(v.status_label(200), "HTTP 200")
        self.assertEqual(v.status_label(0), "연결 실패")
        self.assertEqual(v.status_label(0, "TimeoutError"), "연결 실패(TimeoutError)")
        self.assertEqual(v.status_label(None, "x"), "연결 실패(x)")


class IndexTest(unittest.TestCase):
    def load(self, resp, budgeted=True):
        site = FakeSite({INDEX: resp})
        index = v.load_index(v.Requester(site, FakeClock(), 720), BASE, "t", budgeted)
        return index, site

    def test_a_good_posts_json_becomes_a_path_map(self):
        index, site = self.load(index_resp(entries((KR, KR_URL)), headers={"age": "7"}))
        self.assertEqual(index.status, 200)
        self.assertEqual(index.headers, {"age": "7"})
        self.assertEqual(index.problem, "")
        self.assertEqual(index.entries, {"_posts/" + KR: {"path": "_posts/" + KR, "absoluteUrl": KR_URL}})
        self.assertEqual(site.calls[0][1], INDEX + "?cb=t")
        self.assertEqual(site.calls[0][2], v.MAX_BYTES)

    def test_every_failure_is_a_problem_not_a_crash(self):
        cases = ((page(503), "HTTP 503"), (down("URLError"), "연결 실패(URLError)"), (v.Resp(200, b"not json"), "JSON"),
                 (v.Resp(200, b'{"a": 1}'), "목록이 아님"), (v.Resp(200, b"\xff\xfe"), "JSON"),
                 (v.Resp(200, b"[" * 200000 + b"]" * 200000), "JSON"), (v.Resp(200, b"null"), "목록이 아님"))
        for resp, expected in cases:
            with self.subTest(expected=expected, body=resp.body[:10]):
                index, _ = self.load(resp)
                self.assertIsNone(index.entries)
                self.assertIn(expected, index.problem)

    def test_size_limit(self):
        with mock.patch.object(v, "MAX_BYTES", 50):
            fits, _ = self.load(v.Resp(200, b"[" + b" " * 48 + b"]"))
            self.assertEqual(fits.entries, {})
            too_big, _ = self.load(v.Resp(200, b"[" + b" " * 49 + b"]"))
            self.assertIsNone(too_big.entries)
            self.assertIn("비정상적으로 큼", too_big.problem)

    def test_odd_entries_are_ignored(self):
        odd = [1, "a", None, [1], {"path": ["x"], "absoluteUrl": "https://a/"}, {"path": 5}, {"absoluteUrl": "https://a/"},
               {"path": "_posts/ok.md", "absoluteUrl": KR_URL}]
        index, _ = self.load(index_resp(odd))
        self.assertEqual(list(index.entries), ["_posts/ok.md"])

    def test_address_for_a_post(self):
        base_entry = {"path": KR_POST.rel}
        cases = (
            ({}, None, "posts.json 에 없음"),
            ({KR_POST.rel: dict(base_entry, absoluteUrl=KR_URL)}, KR_URL, ""),
            ({KR_POST.rel: dict(base_entry)}, None, "주소가 없음"),
            ({KR_POST.rel: dict(base_entry, absoluteUrl=None)}, None, "주소가 없음"),
            ({KR_POST.rel: dict(base_entry, absoluteUrl="")}, None, "주소가 없음"),
            ({KR_POST.rel: dict(base_entry, absoluteUrl=["x"])}, None, "주소가 없음"),
            ({KR_POST.rel: dict(base_entry, absoluteUrl=5)}, None, "주소가 없음"),
            ({KR_POST.rel: dict(base_entry, absoluteUrl="http://example.github.io/blog/x/")}, None, "다른 출처"),
            ({KR_POST.rel: dict(base_entry, absoluteUrl="https://evil.example/x/")}, None, "다른 출처"),
            ({KR_POST.rel: dict(base_entry, absoluteUrl="ftp://example.github.io/x")}, None, "다른 출처"),
            ({KR_POST.rel: dict(base_entry, absoluteUrl="file:///etc/passwd")}, None, "다른 출처"),
            ({KR_POST.rel: dict(base_entry, absoluteUrl="javascript:alert(1)")}, None, "다른 출처"),
            ({KR_POST.rel: dict(base_entry, absoluteUrl="https://example.github.io/a b/")}, None, "다른 출처"),
        )
        for mapping, expected_url, expected_why in cases:
            with self.subTest(entry=mapping.get(KR_POST.rel)):
                index = v.Index(200, {}, mapping, "")
                url, why = v.index_address(index, KR_POST, BASE)
                self.assertEqual(url, expected_url)
                self.assertIn(expected_why, why)

    def test_a_failed_index_hands_over_its_reason(self):
        index = v.Index(503, {}, None, "posts.json 을 읽지 못함(HTTP 503)")
        self.assertEqual(v.index_address(index, KR_POST, BASE), (None, "posts.json 을 읽지 못함(HTTP 503)"))


class CheckOnceTest(unittest.TestCase):
    def test_all_reachable_means_no_problems_and_the_index_is_read_last_as_a_reference(self):
        site = FakeSite(full_routes({"age": "3"}))
        att = check(site)
        self.assertTrue(att.ok)
        self.assertEqual(att.problems, [])
        self.assertEqual(att.warnings, [])
        self.assertFalse(att.deadline_hit)
        self.assertEqual([r.url for r in att.results], [EN_URL, KR_URL])
        self.assertEqual([r.how for r in att.results], ["계산", "계산"])
        self.assertEqual(att.results[0].headers, {"age": "3"})
        self.assertEqual(site.bare_urls(), [EN_URL, KR_URL, INDEX])
        self.assertEqual([call[2] for call in site.calls], [v.PAGE_BYTES, v.PAGE_BYTES, v.MAX_BYTES])
        self.assertEqual(len(att.index.entries), 2)

    def test_anything_but_200_is_a_problem(self):
        for status in (404, 410, 403, 429, 500, 502, 503, 301, 302, 204, 206):
            with self.subTest(status=status):
                att = check(FakeSite({KR_URL: page(status), EN_URL: page(200)}), posts=[EN_POST, KR_POST])
                self.assertFalse(att.ok)
                self.assertEqual(len(att.problems), 1)
                self.assertIn(f"HTTP {status}", att.problems[0])
                self.assertEqual(att.results[1].status, status)

    def test_connection_failures_are_problems_with_the_error_name(self):
        for error in ("TimeoutError", "URLError/gaierror", "IncompleteRead"):
            with self.subTest(error=error):
                att = check(FakeSite({KR_URL: down(error), EN_URL: page(200)}))
                self.assertFalse(att.ok)
                self.assertIn(f"연결 실패({error})", att.problems[0])
                self.assertEqual(att.results[1].status, 0)

    def test_the_problem_names_the_post_the_address_and_the_cache_age(self):
        att = check(FakeSite({KR_URL: page(404, {"age": "321"}), EN_URL: page(200)}))
        self.assertEqual(len(att.problems), 1)
        for text in (KR_POST.name, KR_URL, "HTTP 404", "Age 321"):
            self.assertIn(text, att.problems[0])
        self.assertNotIn(EN_POST.name, att.problems[0])

    def test_the_index_is_read_once_per_attempt_even_when_several_posts_fail(self):
        site = FakeSite({})
        att = check(site)
        self.assertEqual(len(att.problems), 2)
        self.assertEqual(site.counts[INDEX], 1)

    def test_a_missing_or_broken_index_never_changes_the_verdict_on_success(self):
        for index in (page(503), down("URLError"), v.Resp(200, b"garbage"), v.Resp(200, b"{}"), index_resp([])):
            with self.subTest(index=index):
                routes = full_routes()
                routes[INDEX] = index
                self.assertTrue(check(FakeSite(routes)).ok)

    def test_an_unexpected_error_while_reading_the_index_is_only_a_warning(self):
        def boom(n):
            raise RuntimeError("x")
        routes = full_routes()
        routes[INDEX] = boom
        att = check(FakeSite(routes))
        self.assertTrue(att.ok)
        self.assertEqual(len(att.warnings), 1)
        self.assertIn("RuntimeError", att.warnings[0])
        self.assertIsNone(att.index)

    def test_when_the_computed_address_fails_the_address_in_posts_json_can_still_prove_publication(self):
        alt = BASE + "posts/other/kr/"
        routes = {KR_URL: page(404), EN_URL: page(200), alt: page(200, {"age": "1"}),
                  INDEX: index_resp(entries((KR, alt), (EN, EN_URL)))}
        att = check(FakeSite(routes))
        self.assertTrue(att.ok)
        kr = att.results[1]
        self.assertEqual((kr.url, kr.how, kr.status, kr.headers), (alt, "posts.json", 200, {"age": "1"}))
        self.assertEqual(len(att.warnings), 1)
        self.assertIn(f"`{KR_URL}`", att.warnings[0])
        self.assertIn(f"`{alt}`", att.warnings[0])
        self.assertIn("점검", att.warnings[0])

    def test_no_second_request_when_posts_json_agrees_with_the_failing_address(self):
        site = FakeSite({KR_URL: page(404), EN_URL: page(200), INDEX: index_resp(entries((KR, KR_URL), (EN, EN_URL)))})
        att = check(site)
        self.assertFalse(att.ok)
        self.assertEqual(site.counts[KR_URL], 1)
        self.assertEqual(att.warnings, [])

    def test_a_different_address_in_posts_json_that_also_fails_is_a_problem_with_a_warning(self):
        alt = BASE + "posts/other/kr/"
        site = FakeSite({KR_URL: page(404), EN_URL: page(200), alt: page(410),
                         INDEX: index_resp(entries((KR, alt), (EN, EN_URL)))})
        att = check(site)
        self.assertFalse(att.ok)
        self.assertEqual(len(att.problems), 1)
        self.assertEqual(len(att.warnings), 1)
        self.assertIn("둘 다 열리지 않음", att.warnings[0])
        self.assertIn("HTTP 410", att.warnings[0])

    def test_unsafe_addresses_in_posts_json_are_never_requested(self):
        for unsafe in ("http://example.github.io/blog/x/", "https://evil.example/x/", "ftp://example.github.io/x",
                       "file:///etc/passwd", "javascript:alert(1)", "https://example.github.io/a b/"):
            with self.subTest(url=unsafe):
                site = FakeSite({KR_URL: page(404), EN_URL: page(200), INDEX: index_resp(entries((KR, unsafe)))})
                att = check(site)
                self.assertFalse(att.ok)
                self.assertEqual(set(site.bare_urls()), {KR_URL, EN_URL, INDEX})

    def test_posts_json_is_the_address_source_when_the_pattern_cannot_be_computed(self):
        alt = BASE + "posts/custom/kr/"
        site = FakeSite({alt: page(200), EN_URL: page(404), INDEX: index_resp(entries((KR, alt)))})
        att = check(site, config={"permalink": "pretty"})
        self.assertFalse(att.ok)
        by_name = {r.post.name: r for r in att.results}
        kr, en = by_name[KR_POST.name], by_name[EN_POST.name]
        self.assertEqual((kr.url, kr.how, kr.status), (alt, "posts.json", 200))
        self.assertIsNone(en.url)
        self.assertIn("posts.json 에 없음", en.note)
        self.assertIn("계산할 수 없고", en.note)
        self.assertEqual(site.counts[INDEX], 1)
        self.assertNotIn(KR_URL, site.bare_urls())

    def test_a_broken_index_in_fallback_mode_is_the_problem(self):
        att = check(FakeSite({INDEX: page(503)}), config={})
        self.assertFalse(att.ok)
        self.assertIn("HTTP 503", att.problems[0])
        self.assertTrue(all(r.url is None for r in att.results))

    def test_fallback_mode_rejects_unusable_addresses(self):
        for bad in ("http://example.github.io/blog/x/", "https://evil.example/x/", "ftp://example.github.io/x",
                    "file:///etc/passwd", "javascript:alert(1)", "https://example.github.io/a b/", None, "", ["x"], 5):
            with self.subTest(url=bad):
                site = FakeSite({INDEX: index_resp([{"path": "_posts/" + KR, "absoluteUrl": bad}])})
                att = check(site, posts=[KR_POST], config={})
                self.assertFalse(att.ok)
                self.assertEqual(site.bare_urls(), [INDEX])  # 글 주소는 요청하지 않는다

    def test_every_request_carries_the_attempt_token(self):
        site = FakeSite(full_routes())
        check(site, token="abc-7")
        self.assertTrue(site.calls)
        self.assertTrue(all(call[1].endswith("?cb=abc-7") for call in site.calls))

    def test_a_deadline_that_has_passed_stops_new_requests_from_the_second_attempt_on(self):
        site = FakeSite(full_routes())
        att = check(site, attempt=2, past_deadline=True)
        self.assertFalse(att.ok)
        self.assertTrue(att.deadline_hit)
        self.assertEqual(site.calls, [])
        self.assertIn("마감", att.problems[0])

    def test_the_first_attempt_ignores_the_deadline(self):
        site = FakeSite(full_routes())
        att = check(site, attempt=1, past_deadline=True)
        self.assertTrue(att.ok)
        self.assertEqual(len(site.calls), 3)

    def test_the_deadline_is_checked_between_requests_of_one_attempt(self):
        clock = FakeClock()
        site = FakeSite(full_routes(), clock=clock, latency=60.0)
        request = v.Requester(site, clock, 100)
        request.attempt = 2
        clock.t = 50.0  # 첫 요청은 마감 전에 나가고 60초가 걸려 마감을 넘긴다
        att = v.check_once(BASE, POSTS, CONFIG, v.site_timezone(CONFIG), request, "t")
        self.assertFalse(att.ok)
        self.assertTrue(att.deadline_hit)
        self.assertEqual(len(site.calls), 1)
        self.assertEqual(len(att.results), 1)

    def test_the_deadline_boundary_counts_as_passed(self):
        clock = FakeClock()
        site = FakeSite(full_routes(), clock=clock, latency=60.0)
        request = v.Requester(site, clock, 100)
        request.attempt = 2
        clock.t = 40.0  # 첫 요청이 끝나면 경과 시간이 마감과 정확히 같다
        att = v.check_once(BASE, POSTS, CONFIG, v.site_timezone(CONFIG), request, "t")
        self.assertTrue(att.deadline_hit)
        self.assertEqual(len(site.calls), 1)

    def test_the_reference_read_after_a_success_is_not_cut_by_the_deadline(self):
        clock = FakeClock()
        site = FakeSite(full_routes(), clock=clock, latency=30.0)
        request = v.Requester(site, clock, 100)
        request.attempt = 2
        clock.t = 50.0  # 두 글은 마감 전에 요청이 나가고, 성공 뒤의 목록 읽기는 마감을 넘겨도 한다
        att = v.check_once(BASE, POSTS, CONFIG, v.site_timezone(CONFIG), request, "t")
        self.assertTrue(att.ok)
        self.assertEqual(site.bare_urls(), [EN_URL, KR_URL, INDEX])
        self.assertIsNotNone(att.index)
        self.assertEqual(att.warnings, [])

    def test_a_deadline_hit_while_looking_up_the_alternative_keeps_the_first_verdict(self):
        clock = FakeClock()
        site = FakeSite({EN_URL: page(404, {"age": "5"}), KR_URL: page(200)}, clock=clock, latency=60.0)
        request = v.Requester(site, clock, 100)
        request.attempt = 2
        clock.t = 50.0
        att = v.check_once(BASE, POSTS, CONFIG, v.site_timezone(CONFIG), request, "t")
        self.assertTrue(att.deadline_hit)
        self.assertEqual([(r.post.name, r.status) for r in att.results], [(EN_POST.name, 404)])
        self.assertIn("HTTP 404", att.problems[0])
        self.assertIn("마감", att.problems[-1])


class VerifyTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name) / "repo")
        patcher = mock.patch.dict(os.environ, {"GITHUB_SHA": "0123456789abcdef"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_verify(self, site, deadline=720, interval=30, now=NOW, token="tok", root=None, clock=None, sleep=None):
        clock = clock or FakeClock()
        if site.clock is None:
            site.clock = clock
        buf = Flushy()
        with redirect_stdout(buf):
            result = v.verify(BASE, root or self.root, deadline, interval, fetcher=site, sleep=sleep or clock.sleep,
                              clock=clock, now=now, token=token)
        return result, buf.getvalue(), clock

    def test_first_try_success_writes_the_commit_the_addresses_and_the_cache_facts(self):
        site = FakeSite(full_routes({"age": "0", "last-modified": "Sun, 25 Oct 2026 01:13:51 GMT"}))
        result, out, clock = self.run_verify(site)
        self.assertTrue(result.ok)
        self.assertFalse(result.skipped)
        self.assertEqual(clock.sleeps, [])
        summary = result.summary
        self.assertIn("- 배포 커밋: `0123456`", summary)
        self.assertNotIn("01234567", summary)
        self.assertIn("**반영됨**", summary)
        self.assertIn("시도 1회·경과 0초", summary)
        self.assertIn(f"`{EN_URL}` — HTTP 200, Age `0`, Last-Modified `Sun, 25 Oct 2026 01:13:51 GMT`", summary)
        self.assertIn(f"`{KR_URL}`", summary)
        self.assertIn("`2026-10-25-EN-101307.md`, `2026-10-25-KR-101307.md`", summary)
        self.assertNotIn("_posts/", summary)  # 이름만, 경로 전체가 아니다
        self.assertIn("공개 `posts.json`", summary)
        self.assertIn("목록에 있고 주소가 같음", summary)
        self.assertIn("범위:", summary)
        self.assertEqual([p.name for p in result.posts], ["2026-10-25-EN-101307.md", "2026-10-25-KR-101307.md"])
        self.assertIn(f"시도 1(경과 0초): 반영 확인 — {EN_URL}, {KR_URL}", out)
        self.assertIn("확인 대상: 2026-10-25-EN-101307.md, 2026-10-25-KR-101307.md (마감 720초, 간격 30초, 요청 제한시간 15초)", out)

    def test_summary_without_a_commit_says_unknown(self):
        with mock.patch.dict(os.environ, {"GITHUB_SHA": ""}):
            result, _, _ = self.run_verify(FakeSite(full_routes()))
        self.assertIn("- 배포 커밋: (알 수 없음)", result.summary)

    def test_a_late_deploy_is_waited_for_and_then_passes(self):
        routes = {KR_URL: [page(404), page(404), page(200)], EN_URL: [page(404), page(404), page(200)],
                  INDEX: [index_resp([]), index_resp([]), index_resp(entries((KR, KR_URL), (EN, EN_URL)))]}
        result, out, clock = self.run_verify(FakeSite(routes))
        self.assertTrue(result.ok)
        self.assertEqual(clock.sleeps, [30, 30])
        self.assertIn("시도 3회·경과 60초", result.summary)
        self.assertIn("시도 1(경과 0초):", out)
        self.assertIn("새 글 주소가 열리지 않음(HTTP 404", out)
        self.assertIn("시도 3(경과 60초): 반영 확인", out)

    def test_server_errors_and_connection_failures_are_retried_until_the_site_recovers(self):
        for first, second in ((page(503), down("TimeoutError")), (page(500), page(502)), (down("URLError/gaierror"), page(404))):
            with self.subTest(first=first.status, second=second.status):
                routes = {KR_URL: [first, second, page(200)], EN_URL: [first, second, page(200)],
                          INDEX: index_resp(entries((KR, KR_URL), (EN, EN_URL)))}
                result, out, clock = self.run_verify(FakeSite(routes))
                self.assertTrue(result.ok)
                self.assertEqual(clock.sleeps, [30, 30])
                self.assertIn("시도 3회·경과 60초", result.summary)

    def test_a_post_that_never_appears_fails_at_the_deadline_with_the_cache_facts(self):
        routes = {KR_URL: page(404, {"age": "250", "last-modified": "Sun, 25 Oct 2026 01:00:00 GMT"}),
                  EN_URL: page(404, {"age": "250"}), INDEX: index_resp([])}
        result, out, clock = self.run_verify(FakeSite(routes))
        self.assertFalse(result.ok)
        self.assertFalse(result.skipped)
        self.assertEqual(clock.sleeps, [30] * 23)  # 마지막 시도 뒤에는 기다리지 않는다
        summary = result.summary
        self.assertIn("**반영 안 됨**", summary)
        self.assertIn("시도 24회·경과 690초(마감 720초)", summary)
        self.assertIn(f"`{KR_URL}` — HTTP 404, Age `250`, Last-Modified `Sun, 25 Oct 2026 01:00:00 GMT`", summary)
        self.assertIn("목록에 아직 없음", summary)
        self.assertIn("- 해석:", summary)
        self.assertIn("- 조치:", summary)
        self.assertEqual(out.count("시도 "), 24)

    def test_elapsed_time_is_measured_from_the_start_of_the_check(self):
        clock = FakeClock()
        clock.t = 5000.0  # 시계가 0 에서 시작한다고 가정하지 않는다(실제 monotonic 시계는 부팅 이후 시간이다)
        site = FakeSite({}, clock=clock)
        result, _, clock = self.run_verify(site, clock=clock)
        self.assertEqual(clock.sleeps, [30] * 23)
        self.assertIn("시도 24회·경과 690초", result.summary)

    def test_attempts_follow_deadline_and_interval(self):
        for deadline, interval, sleeps in ((100, 30, [30, 30, 30]), (60, 30, [30]), (61, 30, [30, 30]), (720, 100, [100] * 7),
                                           (10, 30, []), (0, 30, []), (3, 1, [1, 1])):
            with self.subTest(deadline=deadline, interval=interval):
                _, out, clock = self.run_verify(FakeSite({}), deadline=deadline, interval=interval)
                self.assertEqual(clock.sleeps, sleeps)
                self.assertEqual(out.count("시도 "), len(sleeps) + 1)

    def test_no_new_attempt_or_request_starts_after_the_deadline(self):
        clock = FakeClock()
        site = FakeSite({}, clock=clock, latency=0.4)
        self.run_verify(site, clock=clock)
        self.assertLess(max(site.starts()), 720)
        self.assertGreater(max(site.starts()), 690)

    def test_deadline_zero_means_one_complete_check(self):
        site = FakeSite({KR_URL: page(404), EN_URL: page(404)})
        result, out, clock = self.run_verify(site, deadline=0)
        self.assertFalse(result.ok)
        self.assertEqual(clock.sleeps, [])
        self.assertEqual(site.counts[KR_URL], 1)
        self.assertEqual(site.counts[EN_URL], 1)

    def test_the_deadline_cutting_an_attempt_short_is_reported(self):
        clock = FakeClock()
        site = FakeSite({}, clock=clock, latency=30.0)
        result, _, _ = self.run_verify(site, clock=clock, deadline=100, interval=1)
        self.assertFalse(result.ok)
        self.assertIn("마감(100초)이 지나 일부 확인을 하지 못함", result.summary)

    def test_an_unexpected_error_in_one_attempt_is_recorded_and_retried(self):
        def flaky(n):
            if n == 0:
                raise RuntimeError("::error::주입")
            return page(200)
        routes = full_routes()
        routes[KR_URL] = flaky
        result, out, clock = self.run_verify(FakeSite(routes))
        self.assertTrue(result.ok)
        self.assertEqual(clock.sleeps, [30])
        self.assertIn("예상 못 한 오류(RuntimeError)", out)
        self.assertNotIn("주입", out + result.summary)

    def test_a_persistent_unexpected_error_fails_visibly(self):
        def boom(n):
            raise RuntimeError("::error::주입")
        result, out, _ = self.run_verify(FakeSite({KR_URL: boom, EN_URL: boom}), deadline=60)
        self.assertFalse(result.ok)
        self.assertIn("예상 못 한 오류(RuntimeError)", result.summary)
        self.assertIn("확인을 마치지 못했습니다", result.summary)
        self.assertNotIn("주입", out + result.summary)

    def test_network_and_protocol_failures_never_escape(self):
        failures = (http.client.IncompleteRead(b"x"), http.client.BadStatusLine("GARBAGE"), http.client.InvalidURL("x"),
                    UnicodeEncodeError("ascii", "한", 0, 1, "x"), TimeoutError(), ConnectionResetError(), ValueError("x"),
                    urllib.error.URLError("boom"), http.client.RemoteDisconnected("x"), OSError("x"))
        for exc in failures:
            with self.subTest(error=type(exc).__name__):
                opener = opener_for(exc)

                def fetcher(url, limit=v.MAX_BYTES, opener=opener):
                    return v.fetch(url, opener=opener, limit=limit)  # 가짜 사이트가 아니라 진짜 fetch 가 예외를 상태로 바꾼다
                clock = FakeClock()
                with redirect_stdout(io.StringIO()):
                    result = v.verify(BASE, self.root, 0, 30, fetcher=fetcher, sleep=clock.sleep, clock=clock, now=NOW)
                self.assertFalse(result.ok)
                self.assertIn(f"연결 실패({type(exc).__name__}", result.summary)

    def test_posts_json_with_odd_shapes_never_crashes_the_fallback(self):
        for payload in ([{"path": ["x"], "absoluteUrl": "https://a/"}], ["a", 1, None], [{"path": None}], [], {"a": 1}):
            with self.subTest(payload=payload):
                with tempfile.TemporaryDirectory() as tmp:
                    root = make_repo(Path(tmp) / "r", [KR], config="title: t\n")
                    result, _, _ = self.run_verify(FakeSite({INDEX: index_resp(payload)}), deadline=0, root=root)
                    self.assertFalse(result.ok)

    def test_no_posts_in_the_repository_is_skipped_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "r", [])
            (root / "_posts").mkdir()
            site = FakeSite({})
            result, out, _ = self.run_verify(site, root=root)
        self.assertTrue(result.ok)
        self.assertTrue(result.skipped)
        self.assertEqual(result.posts, [])
        self.assertIn("**건너뜀**", result.summary)
        self.assertIn("확인할 글이 없음", result.summary)
        self.assertEqual(site.calls, [])
        self.assertIn("건너뜁니다", out)

    def test_everything_unpublished_is_skipped_with_the_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "r", [KR, EN], fronts={KR: "published: false\n", EN: "published: no\n"})
            site = FakeSite({})
            result, out, _ = self.run_verify(site, root=root)
        self.assertTrue(result.ok)
        self.assertTrue(result.skipped)
        self.assertIn("**건너뜀**", result.summary)
        self.assertIn("published: false", result.summary)
        self.assertIn("`2026-10-25-KR-101307.md`", result.summary)
        self.assertIn("글 2건", result.summary)
        self.assertEqual(site.calls, [])
        self.assertIn("건너뜀: 2026-10-25-KR-101307.md (published: false)", out)

    def test_a_missing_posts_folder_is_a_configuration_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(v.ConfigError):
                self.run_verify(FakeSite({}), root=Path(tmp))

    def test_unpublished_newest_pair_verifies_the_next_pair_instead(self):
        """F-01: 가장 새 KR/EN 쌍이 published: false 여도 정상 사이트다. 그 쌍은 공개 사이트에 없는 게 맞다."""
        older_kr, older_en = "기술·미래/2026-10-21-KR-135226.md", "Technology & Future/2026-10-21-EN-135226.md"
        older_kr_url, older_en_url = BASE + "posts/2026/10/21/KR-135226/", BASE + "posts/2026/10/21/EN-135226/"
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "r", [KR, EN, older_kr, older_en],
                             fronts={KR: "published: false\n", EN: "published: False\n"})
            site = FakeSite({older_kr_url: page(200), older_en_url: page(200),
                             INDEX: index_resp(entries((older_kr, older_kr_url), (older_en, older_en_url)))})
            result, out, _ = self.run_verify(site, root=root)
        self.assertTrue(result.ok)
        self.assertFalse(result.skipped)
        self.assertEqual({KR_URL, EN_URL} & set(site.bare_urls()), set())
        self.assertIn("더 새 글 중 공개되지 않아 건너뜀", result.summary)
        self.assertIn("`2026-10-25-KR-101307.md`(published: false)", result.summary)
        self.assertIn("`2026-10-21-KR-135226.md`", result.summary)
        self.assertIn("건너뜀: 2026-10-25-KR-101307.md (published: false)", out)

    def test_the_time_zone_in_the_site_config_decides_what_is_already_public(self):
        """한국 시간으로 막 10-26 이 된 시각(UTC 10-25 16:00)에는 10-26 글이 이미 공개된다. UTC 사이트에서는 아직 미래다."""
        names = ["a/2026-10-26-KR-000001.md", "b/2026-10-25-KR-000001.md"]
        now = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)
        for zone, expected in (("Asia/Seoul", "2026-10-26-KR-000001.md"), ("UTC", "2026-10-25-KR-000001.md")):
            with self.subTest(zone=zone):
                with tempfile.TemporaryDirectory() as tmp:
                    root = make_repo(Path(tmp) / "r", names, config=SITE_CONFIG.replace("Asia/Seoul", zone))
                    site = FakeSite({BASE + "posts/2026/10/26/KR-000001/": page(200), BASE + "posts/2026/10/25/KR-000001/": page(200)})
                    result, _, _ = self.run_verify(site, root=root, now=now)
                self.assertEqual([p.name for p in result.posts], [expected])
                self.assertTrue(result.ok)

    def test_a_future_dated_newest_post_is_not_expected_to_be_public(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "r", [KR, "a/2026-10-21-KR-000001.md"], fronts={KR: "date: 2030-01-01\n"})
            older_url = BASE + "posts/2026/10/21/KR-000001/"
            site = FakeSite({older_url: page(200)})
            result, _, _ = self.run_verify(site, root=root)
        self.assertTrue(result.ok)
        self.assertNotIn(KR_URL, site.bare_urls())
        self.assertIn("미래 날짜", result.summary)

    def test_at_most_ten_posts_of_one_moment_are_checked(self):
        names = [f"c{n:02d}/2026-10-25-KR-101307.md" for n in range(12)]
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "r", names)
            site = FakeSite({BASE + "posts/2026/10/25/KR-101307/": page(200)})
            result, _, _ = self.run_verify(site, root=root)
        self.assertTrue(result.ok)
        self.assertEqual(len([c for c in site.calls if c[0] != INDEX]), 10)
        self.assertEqual(len(result.posts), 10)
        self.assertIn("같은 시각의 글이 12건이라 앞의 10건만 확인", result.summary)

    def test_progress_is_logged_per_attempt_before_the_next_wait_and_flushed(self):
        clock = FakeClock()
        site = FakeSite({}, clock=clock)
        buf = Flushy()
        snapshots = []

        def sleep(seconds):
            snapshots.append((len(buf.getvalue().splitlines()), buf.flushes))
            clock.sleep(seconds)
        with redirect_stdout(buf):
            v.verify(BASE, self.root, 100, 30, fetcher=site, sleep=sleep, clock=clock, now=NOW)
        # 첫 줄은 '확인 대상' 안내이고, 시도마다 한 줄이 그다음 대기 전에 이미 찍혀 있다
        self.assertEqual([lines for lines, _ in snapshots], [2, 3, 4])
        self.assertTrue(all(flushes >= lines for lines, flushes in snapshots))

    def test_each_attempt_has_its_own_cache_token(self):
        site = FakeSite({})
        self.run_verify(site, deadline=100, interval=30, token="tok")
        tokens = [call[1].rsplit("cb=", 1)[1] for call in site.calls if call[0] == EN_URL]
        self.assertEqual(tokens, ["tok-1", "tok-2", "tok-3", "tok-4"])

    def test_interpretation_tells_cache_delay_from_a_real_miss(self):
        delay, miss, outage = "캐시 지연", "진짜 미반영", "연결하지 못했거나 서버 오류"
        cases = (
            ({KR_URL: page(404, {"age": "250"}), EN_URL: page(404, {"age": "100"})}, [delay, "Age `250`", "Age `100`", "250초"], [miss, outage]),
            ({KR_URL: page(404, {"age": "0"}), EN_URL: page(404)}, [miss], [delay, outage]),
            ({KR_URL: page(404), EN_URL: page(404)}, [miss], [delay, outage]),
            ({KR_URL: page(503), EN_URL: page(404)}, [outage], [delay, miss]),
            ({KR_URL: down(), EN_URL: down()}, [outage], [delay, miss]),
        )
        for routes, present, absent in cases:
            with self.subTest(present=present, kr=routes[KR_URL].status):
                result, _, _ = self.run_verify(FakeSite(routes), deadline=0)
                self.assertFalse(result.ok)
                for text in present:
                    self.assertIn(text, result.summary)
                for text in absent:
                    self.assertNotIn(text, result.summary)

    def test_a_computed_address_that_differs_from_posts_json_is_a_warning_not_a_failure(self):
        routes = full_routes()
        routes[INDEX] = index_resp(entries((KR, KR_URL.replace("101307", "999999")), (EN, EN_URL)))
        result, _, _ = self.run_verify(FakeSite(routes))
        self.assertTrue(result.ok)
        self.assertIn("경고: 목록의 주소", result.summary)
        self.assertIn("999999", result.summary)
        self.assertIn("주소 계산 규칙 점검 필요", result.summary)

    def test_a_post_that_is_open_but_not_yet_in_posts_json_is_only_noted(self):
        routes = full_routes()
        routes[INDEX] = index_resp(entries((EN, EN_URL)))
        result, _, _ = self.run_verify(FakeSite(routes))
        self.assertTrue(result.ok)
        self.assertIn("목록에 아직 없음(캐시 지연일 수 있음)", result.summary)

    def test_posts_json_failure_is_noted_without_changing_the_verdict(self):
        routes = full_routes()
        routes[INDEX] = page(503, {"age": "9"})
        result, _, _ = self.run_verify(FakeSite(routes))
        self.assertTrue(result.ok)
        self.assertIn("posts.json 을 읽지 못함(HTTP 503)", result.summary)
        self.assertIn("판정에는 쓰지 않음", result.summary)
        self.assertIn("Age `9`", result.summary)

    def test_summary_lists_a_cap_on_skipped_names(self):
        names = [f"x/2026-10-26-KR-{n:06d}.md" for n in range(1, 9)] + ["y/2026-10-20-KR-000001.md"]
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "r", names, fronts={n: "published: false\n" for n in names[:-1]})
            result, _, _ = self.run_verify(FakeSite({BASE + "posts/2026/10/20/KR-000001/": page(200)}),
                                           root=root, now=NOW.replace(year=2027))
        self.assertTrue(result.ok)
        self.assertIn("외 2건", result.summary)


class TimingTest(unittest.TestCase):
    """F-05: 가상 시계로 최악 소요 시간을 확인한다(마감 + 요청 1~2회 + 여유 안, 잡 제한 15분 안)."""

    JOB_LIMIT = 15 * 60
    SETUP = 120  # 러너 준비·checkout·파이썬 시작에 넉넉히 잡은 시간

    def run_case(self, routes, latency, names=(KR, EN)):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "r", names)
            clock = FakeClock()
            site = FakeSite(routes, clock=clock, latency=latency)
            with redirect_stdout(io.StringIO()):
                result = v.verify(BASE, root, fetcher=site, sleep=clock.sleep, clock=clock, now=NOW)
        return result, site, clock

    def assert_bounded(self, site, clock):
        self.assertLess(max(site.starts()), v.DEFAULT_DEADLINE)  # 마감 뒤에는 요청을 시작하지 않는다
        self.assertLessEqual(clock.t, v.DEFAULT_DEADLINE + 2 * v.REQUEST_TIMEOUT)
        self.assertLess(clock.t + self.SETUP, self.JOB_LIMIT)

    def test_ordinary_failures_end_just_before_the_deadline(self):
        result, site, clock = self.run_case({}, 0.4)
        self.assertFalse(result.ok)
        self.assert_bounded(site, clock)
        self.assertGreater(clock.t, v.DEFAULT_DEADLINE - 2 * v.DEFAULT_INTERVAL)

    def test_connection_timeouts_everywhere(self):
        routes = {KR_URL: down("TimeoutError"), EN_URL: down("TimeoutError"), INDEX: down("TimeoutError")}
        result, site, clock = self.run_case(routes, float(v.REQUEST_TIMEOUT))
        self.assertFalse(result.ok)
        self.assert_bounded(site, clock)

    def test_ten_posts_timing_out_still_end_at_the_deadline(self):
        names = [f"c{n:02d}/2026-10-25-KR-101307.md" for n in range(12)]
        url = BASE + "posts/2026/10/25/KR-101307/"
        result, site, clock = self.run_case({url: down("TimeoutError"), INDEX: down("TimeoutError")},
                                            float(v.REQUEST_TIMEOUT), names)
        self.assertFalse(result.ok)
        self.assert_bounded(site, clock)

    def test_slow_pages_with_a_slow_posts_json(self):
        routes = {KR_URL: page(404), EN_URL: page(404), INDEX: index_resp([])}
        result, site, clock = self.run_case(routes, 14.0)
        self.assertFalse(result.ok)
        self.assert_bounded(site, clock)

    def test_the_job_timeout_leaves_room_for_the_whole_window(self):
        worst = v.DEFAULT_DEADLINE + 2 * v.REQUEST_TIMEOUT + self.SETUP
        self.assertLessEqual(worst, self.JOB_LIMIT)

    def test_the_first_attempt_is_always_completed(self):
        clock = FakeClock()
        site = FakeSite({}, clock=clock, latency=15.0)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "r")
            with redirect_stdout(io.StringIO()):
                result = v.verify(BASE, root, 1, 30, fetcher=site, sleep=clock.sleep, clock=clock, now=NOW)
        self.assertFalse(result.ok)
        self.assertEqual(site.bare_urls(), [EN_URL, INDEX, KR_URL])  # 첫 실패 직후 posts.json 을 한 번 읽는다


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name) / "repo", [OLD_KR, OLD_EN])
        self.summary = Path(tmp.name) / "summary.md"
        env = {k: val for k, val in os.environ.items() if k not in ("PAGE_URL", "GITHUB_SHA")}
        env["GITHUB_STEP_SUMMARY"] = str(self.summary)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def routes(self):
        return {OLD_KR_URL: page(200), OLD_EN_URL: page(200),
                INDEX: index_resp([{"path": "_posts/" + OLD_KR, "absoluteUrl": OLD_KR_URL},
                                   {"path": "_posts/" + OLD_EN, "absoluteUrl": OLD_EN_URL}])}

    def run_main(self, argv, site=None, clock=None):
        """main 을 가짜 사이트와 가상 시계로 돌린다. 시계는 언제나 가짜라서, 확인이 실패해도(회귀든 변이든) 실제로 12분을
        기다리며 테스트가 멈추는 일이 없다."""
        buf = Flushy()
        site = site if site is not None else FakeSite(self.routes())
        clock = clock or FakeClock()
        fake_time = types.SimpleNamespace(sleep=clock.sleep, monotonic=clock)
        with mock.patch.object(v, "fetch", site), mock.patch.object(v, "time", fake_time), redirect_stdout(buf):
            code = v.main(argv)
        return code, buf.getvalue(), site, buf

    def argv(self, *extra):
        return ["--base", BASE, "--root", str(self.root), *extra]

    def test_success_exits_zero_and_appends_the_summary_once(self):
        self.summary.write_text("이전 단계 요약\n\n", encoding="utf-8")
        code, out, site, _ = self.run_main(["--base", BASE.rstrip("/"), "--root", str(self.root)])
        self.assertEqual(code, 0)
        text = self.summary.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("이전 단계 요약\n\n"))
        self.assertEqual(text.count("### 공개 사이트 반영 확인"), 1)
        self.assertIn("**반영됨**", text)
        self.assertTrue(text.endswith("\n\n"))
        self.assertTrue(site.calls[0][1].startswith(BASE + "posts/2020/01/01/"))  # 끝 슬래시를 보정한다

    def test_the_base_is_stripped(self):
        code, _, site, _ = self.run_main(["--base", f"  {BASE}  ", "--root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertTrue(site.calls[0][1].startswith(BASE))

    def test_failure_exits_one_with_one_error_annotation_last(self):
        code, out, _, _ = self.run_main(self.argv("--deadline", "0"), FakeSite({}))
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[-1], v.ERROR_LINE)
        self.assertEqual(out.count("::error::"), 1)
        self.assertIn("**반영 안 됨**", self.summary.read_text(encoding="utf-8"))

    def test_a_late_deploy_with_the_default_window_passes_after_waiting(self):
        clock = FakeClock()
        routes = self.routes()
        routes[OLD_KR_URL] = [page(404)] * 5 + [page(200)]
        routes[OLD_EN_URL] = [page(404)] * 5 + [page(200)]
        code, out, _, _ = self.run_main(self.argv(), FakeSite(routes, clock=clock), clock=clock)
        self.assertEqual(code, 0)
        self.assertEqual(clock.sleeps, [30] * 5)
        self.assertIn("시도 6회·경과 150초", self.summary.read_text(encoding="utf-8"))

    def test_page_url_environment_variable_is_the_default_base(self):
        with mock.patch.dict(os.environ, {"PAGE_URL": BASE}):
            code, _, _, _ = self.run_main(["--root", str(self.root)])
        self.assertEqual(code, 0)

    def test_bad_arguments_are_configuration_errors_and_send_no_request(self):
        for argv in ([], ["--base", "http://example.github.io/"], ["--base", "https://"], ["--base", BASE, "--deadline", "-1"],
                     ["--base", BASE, "--interval", "0"], ["--base", BASE, "--interval", "-5"]):
            with self.subTest(argv=argv):
                code, out, site, _ = self.run_main(argv + ["--root", str(self.root)])
                self.assertEqual(code, 2)
                self.assertIn("::error::", out)
                self.assertEqual(site.calls, [])

    def test_non_numeric_options_are_rejected_by_the_parser(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            v.main(self.argv("--deadline", "abc"))
        self.assertEqual(ctx.exception.code, 2)

    def test_a_missing_posts_folder_is_exit_two_with_a_summary(self):
        with tempfile.TemporaryDirectory() as empty:
            code, out, site, _ = self.run_main(["--base", BASE, "--root", empty])
        self.assertEqual(code, 2)
        self.assertEqual(out.count("::error::"), 1)
        self.assertIn("_posts", out)
        self.assertIn("설정 오류", self.summary.read_text(encoding="utf-8"))
        self.assertEqual(site.calls, [])

    def test_no_posts_to_check_exits_zero_with_a_skip_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "r", [])
            (root / "_posts").mkdir()
            code, out, site, _ = self.run_main(["--base", BASE, "--root", str(root)])
        self.assertEqual(code, 0)
        self.assertIn("건너뜀", self.summary.read_text(encoding="utf-8"))
        self.assertEqual(site.calls, [])

    def test_root_defaults_to_the_current_directory(self):
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        code, _, _, _ = self.run_main(["--base", BASE])
        self.assertEqual(code, 0)

    def test_parser_defaults(self):
        args = v.build_parser().parse_args([])
        self.assertEqual((args.base, args.root, args.deadline, args.interval), ("", ".", 720, 30))
        self.assertEqual((v.DEFAULT_DEADLINE, v.DEFAULT_INTERVAL), (720, 30))
        with mock.patch.dict(os.environ, {"PAGE_URL": BASE}):
            self.assertEqual(v.build_parser().parse_args([]).base, BASE)

    def test_console_safety_is_applied_first(self):
        with mock.patch.object(v, "safe_output") as safe:
            self.run_main(self.argv())
        safe.assert_called_once_with()

    def test_summary_write_failure_does_not_change_the_result(self):
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": folder}):  # 폴더라 열 수 없다
                code, out, _, _ = self.run_main(self.argv())
        self.assertEqual(code, 0)
        self.assertIn("실행 요약 쓰기 실패", out)

    def test_works_without_a_summary_file(self):
        with mock.patch.dict(os.environ):
            del os.environ["GITHUB_STEP_SUMMARY"]
            code, _, _, _ = self.run_main(self.argv())
        self.assertEqual(code, 0)
        self.assertFalse(self.summary.exists())

    def test_the_run_token_comes_from_the_commit(self):
        with mock.patch.dict(os.environ, {"GITHUB_SHA": "0123456789abcdef0123"}):
            _, _, site, _ = self.run_main(self.argv())
        self.assertTrue(all("cb=0123456789ab-1" in call[1] for call in site.calls))
        self.assertIn("`0123456`", self.summary.read_text(encoding="utf-8"))
        self.summary.write_text("", encoding="utf-8")
        _, _, site, _ = self.run_main(self.argv())
        self.assertTrue(all(call[1].endswith("cb=run-1") for call in site.calls))
        self.assertIn("(알 수 없음)", self.summary.read_text(encoding="utf-8"))

    def test_an_unexpected_crash_is_reported_and_exits_one(self):
        with mock.patch.object(v, "verify", side_effect=RuntimeError("::error::주입\n::warning::x")):
            code, out, _, _ = self.run_main(self.argv())
        self.assertEqual(code, 1)
        self.assertEqual(out.count("::error::"), 1)
        self.assertNotIn("주입", out)
        text = self.summary.read_text(encoding="utf-8")
        self.assertIn("검사 중단", text)
        self.assertIn("RuntimeError", text)
        self.assertFalse(any(line.lstrip().startswith("::") for line in text.splitlines()))

    def test_every_printed_line_is_flushed(self):
        _, out, _, buf = self.run_main(self.argv("--deadline", "0"), FakeSite({}))
        self.assertGreaterEqual(buf.flushes, len(out.splitlines()))


class InjectionTest(unittest.TestCase):
    """공개 사이트·파일 이름에서 온 문자열이 로그·요약에서 워크플로 명령이나 마크다운 링크가 되지 않는다."""

    PAYLOADS = ("\n::error::가짜", "\r::warning::가짜", "\u0085::error::NEL", "\x1c::error::FS", "x/%0A::error::퍼센트",
                "x/[click](https://evil.example/)![img](https://evil.example/t.png)", "x/<img src=x onerror=alert(1)>",
                "x/" + "A" * 5000, "x/##[error]legacy", "x/`tick`", "   ::set-output name=a::b")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.summary = self.tmp / "summary.md"
        env = {k: val for k, val in os.environ.items() if k not in ("PAGE_URL", "GITHUB_SHA")}
        env["GITHUB_STEP_SUMMARY"] = str(self.summary)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, root, site):
        buf = io.StringIO()
        self.summary.write_text("", encoding="utf-8")
        with mock.patch.object(v, "fetch", site), redirect_stdout(buf):
            code = v.main(["--base", BASE, "--root", str(root), "--deadline", "0"])
        return code, buf.getvalue(), self.summary.read_text(encoding="utf-8")

    CRASH_LINE = "::error::공개 사이트 반영 확인이 예상 못 한 오류로 멈췄습니다(RuntimeError). 실행 로그를 확인하세요."

    def assert_safe(self, out, summary):
        for line in out.splitlines():  # 우리가 만든 고정 주석(실패·중단)만 명령 줄이어도 된다
            self.assertFalse(line.lstrip().startswith("::") and line not in (v.ERROR_LINE, self.CRASH_LINE), repr(line[:80]))
        self.assertNotIn("##[", out + summary)
        for line in summary.splitlines():
            self.assertFalse(line.lstrip().startswith("::"), repr(line[:80]))
        outside_code = re.sub(r"`[^`]*`", "", summary)
        self.assertNotRegex(outside_code, r"https?://")  # 맨 URL 은 자동 링크가 된다
        self.assertNotRegex(outside_code, r"\]\(")

    def test_text_from_posts_json_and_headers_in_every_outcome(self):
        root = make_repo(self.tmp / "repo", [OLD_KR], config="title: t\n")  # permalink 없음: posts.json 주소를 쓴다
        rel = "_posts/" + OLD_KR
        for status in (200, 404, 503, 0):
            for payload in self.PAYLOADS:
                with self.subTest(status=status, payload=payload[:20]):
                    evil = BASE + payload
                    index = index_resp([{"path": rel, "absoluteUrl": evil, "title": payload}])

                    def serve(url, limit=v.MAX_BYTES, index=index, status=status, payload=payload):
                        if url.split("?")[0] == INDEX:
                            return index
                        return v.Resp(status, b"", {"age": payload, "last-modified": payload}, payload if status == 0 else "")
                    code, out, summary = self.run_main(root, serve)
                    self.assertIn(code, (0, 1))
                    self.assert_safe(out, summary)

    def test_text_from_computed_addresses_and_file_names(self):
        for name in ("a/2020-01-01-KR-##[error]x.md", "a/2020-01-01-KR-`tick`.md", "a/2020-01-01-KR-[x](http-evil).md",
                     "a/2020-01-01-KR-한글 제목.md"):
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = make_repo(Path(tmp) / "r", [name])
                    code, out, summary = self.run_main(root, FakeSite({}))
                    self.assertEqual(code, 1)
                    self.assertIn("반영 안 됨", summary)
                    self.assert_safe(out, summary)

    def test_a_crash_message_stays_out_of_the_log(self):
        with mock.patch.object(v, "verify", side_effect=RuntimeError("\n::error::주입")):
            code, out, summary = self.run_main(make_repo(self.tmp / "repo", [OLD_KR]), FakeSite({}))
        self.assertEqual(code, 1)
        self.assert_safe(out, summary)


try:
    import yaml
except ImportError:  # pragma: no cover - CI 는 requirements-dev.txt 로 PyYAML 을 설치한다
    yaml = None


@unittest.skipIf(yaml is None, "PyYAML 이 없다")
class PagesWorkflowTest(unittest.TestCase):
    """verify 잡의 모양을 고정한다(검증기·actionlint 가 못 잡는 변경: 직접 보간, 권한, 조건, env 이름 오타)."""

    PATH = _bootstrap.ROOT / ".github" / "workflows" / "pages.yml"

    def setUp(self):
        self.text = self.PATH.read_text(encoding="utf-8")
        self.jobs = yaml.safe_load(self.text)["jobs"]
        self.verify = self.jobs["verify"]

    def test_verify_runs_after_deploy_with_read_only_access_and_a_job_limit_that_fits_the_window(self):
        self.assertEqual(self.verify["needs"], "deploy")
        self.assertNotIn("if", self.verify)
        self.assertEqual(self.verify["permissions"], {"contents": "read"})
        self.assertEqual(self.verify["timeout-minutes"], 15)
        self.assertLessEqual(v.DEFAULT_DEADLINE + 2 * v.REQUEST_TIMEOUT + 120, self.verify["timeout-minutes"] * 60)
        self.assertEqual(self.jobs["deploy"]["outputs"], {"page_url": "${{ steps.deployment.outputs.page_url }}"})

    def test_checkout_does_not_keep_credentials(self):
        checkout = self.verify["steps"][0]
        self.assertTrue(checkout["uses"].startswith("actions/checkout@"))
        self.assertIs(checkout["with"]["persist-credentials"], False)

    def test_the_command_reads_the_address_from_env_and_is_unbuffered(self):
        step = self.verify["steps"][1]
        self.assertEqual(step["env"], {"PAGE_URL": "${{ needs.deploy.outputs.page_url }}"})
        self.assertEqual(step["run"].strip(), 'python3 -u scripts/verify_pages_deploy.py --base "$PAGE_URL"')
        self.assertNotIn("${{", step["run"])
        self.assertNotIn("continue-on-error", step)
        self.assertEqual(len(self.verify["steps"]), 2)

    def test_the_comment_points_at_the_right_defect(self):
        self.assertIn("D-41", self.text)
        self.assertNotIn("D-37", self.text)


if __name__ == "__main__":
    unittest.main()
