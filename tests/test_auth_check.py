"""Blogger 인증 점검(pipeline/auth_check.py): 블로그 주소 비교·실패 분류표·점검 함수.

네트워크·구글 라이브러리 없이 가짜 게시자로 확인한다. 어댑터 쪽(토큰 갱신·blogs.get 오류 분류)은 test_publisher_blogger.py,
러너가 이 점검을 어떤 순서로 부르고 실패를 어떻게 알리는지는 test_draft_upload.py 가 본다.
"""
import re
import unittest

import _bootstrap  # noqa: F401
from pipeline import auth_check as ac
from pipeline.publishers.base import PublishError

REAL = _bootstrap.ROOT
HANGUL = re.compile(r"[가-힣]")


class FakePublisher:
    def __init__(self, info=None, error=None):
        self.info, self.error, self.calls = info, error, 0

    def healthcheck(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.info


class NormalizeUrlTest(unittest.TestCase):
    def test_scheme_case_www_and_trailing_slash_do_not_matter(self):
        same = ("https://macat0722.blogspot.com/", "http://macat0722.blogspot.com", "HTTPS://MacAt0722.Blogspot.com//",
                "macat0722.blogspot.com", "https://www.macat0722.blogspot.com/", "  https://macat0722.blogspot.com/  ")
        for url in same:
            with self.subTest(url):
                self.assertEqual(ac.normalize_blog_url(url), "macat0722.blogspot.com")
                self.assertTrue(ac.urls_match(url, "https://macat0722.blogspot.com/"))

    def test_country_blogspot_domains_are_the_same_blog(self):
        for tld in ("kr", "co.uk", "jp", "com.au"):
            self.assertTrue(ac.urls_match(f"https://macat0722.blogspot.{tld}/", "https://macat0722.blogspot.com/"), tld)

    def test_different_blogs_do_not_match(self):
        expected = "https://macat0722.blogspot.com/"
        for other in ("https://other.blogspot.com/", "https://macat0722x.blogspot.com/", "https://xmacat0722.blogspot.com/",
                      "https://macat0722.example.com/", "https://macat0722.blogspot.com.evil.example/",
                      "https://macat0722.blogspot.com/sub", "https://blogspot.com/", "https://evil.example/macat0722.blogspot.com/"):
            with self.subTest(other):
                self.assertFalse(ac.urls_match(other, expected))

    def test_custom_domain_needs_the_registry_to_say_so(self):
        self.assertTrue(ac.urls_match("http://www.example.org/", "https://example.org"))
        self.assertFalse(ac.urls_match("http://www.example.org/", "https://macat0722.blogspot.com/"))

    def test_empty_or_unreadable_values_never_match(self):
        for bad in ("", None, "   ", "http://", "https:///path", "http://[::1"):
            with self.subTest(repr(bad)):
                self.assertFalse(ac.urls_match(bad, "https://macat0722.blogspot.com/"))
                self.assertFalse(ac.urls_match("https://macat0722.blogspot.com/", bad))
                self.assertFalse(ac.urls_match(bad, bad))          # 같은 '읽을 수 없는 값'끼리도 같다고 보지 않는다
                self.assertEqual(ac.normalize_blog_url(bad), "")
        self.assertFalse(ac.urls_match("", ""))        # 둘 다 비어도 '같다'로 보지 않는다(주소를 확인하지 못한 것)


class AuthCheckTest(unittest.TestCase):
    URL = "https://macat0722.blogspot.com/"

    def test_passes_when_the_returned_address_matches_the_registry(self):
        info = {"name": "블로그", "url": "http://macat0722.blogspot.com/"}
        pub = FakePublisher(info)
        self.assertEqual(ac.auth_check(pub, self.URL), info)
        self.assertEqual(pub.calls, 1)                    # 점검은 healthcheck 한 번(토큰 갱신 + blogs.get)

    def test_a_different_blog_is_blog_mismatch_and_its_address_is_never_quoted(self):
        other = "https://private-diary-of-someone.blogspot.com/"
        with self.assertRaises(PublishError) as ctx:
            ac.auth_check(FakePublisher({"name": "개인 일기장", "url": other}), self.URL)
        self.assertEqual(ctx.exception.code, "blog_mismatch")
        text = str(ctx.exception)
        for leaked in (other, "private-diary", "개인 일기장"):   # 같은 계정의 다른 블로그 주소·이름이 공개 로그에 남지 않게
            self.assertNotIn(leaked, text)

    def test_a_response_without_an_address_cannot_be_verified(self):
        for info in ({}, {"name": "블로그"}, {"name": "블로그", "url": ""}, {"url": "  "}, {"url": None}, {"url": 123}, None,
                     "html", []):
            with self.subTest(repr(info)):
                with self.assertRaises(PublishError) as ctx:
                    ac.auth_check(FakePublisher(info), self.URL)
                self.assertEqual(ctx.exception.code, "bad_response")

    def test_adapter_failures_propagate_with_their_own_code(self):
        for code in ("auth_expired", "auth_failed", "network", "api_error"):
            with self.subTest(code):
                with self.assertRaises(PublishError) as ctx:
                    ac.auth_check(FakePublisher(error=PublishError("x", code=code)), self.URL)
                self.assertEqual(ctx.exception.code, code)

    def test_an_empty_registry_address_never_passes(self):
        with self.assertRaises(PublishError):
            ac.auth_check(FakePublisher({"url": "https://macat0722.blogspot.com/"}), "")


class ClassificationTest(unittest.TestCase):
    # docs/ARCHITECTURE.md §4-1 의 표와 같은 값. 바꾸면 문서도 같이 고친다(아래 문서 대조 시험이 알려 준다).
    EXPECTED_EXIT = {"auth_expired": 1, "auth_failed": 2, "blog_mismatch": 2, "network": 1, "bad_response": 1, "api_error": 1,
                     "unexpected": 1}

    def test_exit_codes_follow_the_documented_split(self):
        """2 = 사람이 설정(블로그 ID·계정 권한·클라이언트 값)을 고쳐야 하는 실패, 1 = 시간이 지나 생기는 외부 상태나 일시 오류."""
        self.assertEqual({code: ac.exit_code_for(code) for code in ac.KNOWN_CODES}, self.EXPECTED_EXIT)

    def test_unknown_codes_fold_into_api_error(self):
        for weird in ("something_new", "", None, "::error::x", "auth_failed\n::error::x", 5):
            with self.subTest(repr(weird)):
                self.assertEqual(ac.safe_code(weird), "api_error")
                self.assertEqual(ac.exit_code_for(weird), 1)
        for code in ac.KNOWN_CODES:
            self.assertEqual(ac.safe_code(code), code)

    def test_every_adapter_code_is_classified(self):
        """PublishError 의 docstring 에 적힌 분류(unexpected 는 러너가 붙임)가 모두 표에 있다."""
        documented = set(re.findall(r"^    (\w+)\s*:", PublishError.__doc__, re.M)) - {"post_id"}
        self.assertEqual(documented, set(ac.KNOWN_CODES))

    def test_sentences_are_fixed_korean_text_safe_for_an_annotation(self):
        """::error:: 주석에는 고정 문장만 쓴다: 한 줄이고, 워크플로 명령 표기가 없고, 외부 값이 들어갈 자리가 없다."""
        for code in ac.KNOWN_CODES:
            sentence = ac.sentence_for(code)
            with self.subTest(code):
                self.assertRegex(sentence, HANGUL)
                self.assertRegex(ac.label_for(code), HANGUL)
                for bad in ("\n", "\r", "::", "##[", "{", "%s"):
                    self.assertNotIn(bad, sentence)

    def test_sentences_name_only_secret_names_never_values(self):
        names = set(re.findall(r"BLOGGER_[A-Z_]+", " ".join(ac.sentence_for(c) for c in ac.KNOWN_CODES)))
        names -= {"BLOGGER_API_SETUP"}      # 안내 문서 파일 이름(BLOGGER_API_SETUP.md)
        self.assertTrue(names <= {"BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN"}, names)

    def test_architecture_doc_lists_every_failure_code_with_its_exit_code(self):
        """코드표가 문서에 있다: 코드 이름과 '종료 코드' 가 §4-1 에 적혀 있어야 한다(문서가 코드와 어긋나면 실패)."""
        text = (REAL / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        section = text[text.index("## 4-1."):text.index("## 4-2.")]
        for code, exit_code in self.EXPECTED_EXIT.items():
            rows = [line for line in section.splitlines() if line.lstrip().startswith("|") and f"`{code}`" in line]
            with self.subTest(code):
                self.assertTrue(rows, f"{code} 행이 §4-1 표에 없습니다")
                self.assertTrue(any(re.search(rf"\|\s*{exit_code}\s*\|", row) for row in rows), f"{code} 의 종료 코드 {exit_code} 가 표와 다릅니다")
        for skip in ("AUTH_CHECK_FAILED", "UPLOAD_SKIPPED", "INVALID_PUBLISH", "PUBLISH_FAILED", "SECRETS_MISSING"):
            self.assertIn(f"`{skip}`", section)


if __name__ == "__main__":
    unittest.main()
