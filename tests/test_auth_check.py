"""Blogger 인증 점검(pipeline/auth_check.py): 블로그 주소 비교·실패 분류표·점검 함수.

네트워크·구글 라이브러리 없이 가짜 게시자로 확인한다. 어댑터 쪽(토큰 갱신·blogs.get 오류 분류)은 test_publisher_blogger.py,
러너가 이 점검을 어떤 순서로 부르고 실패를 어떻게 알리는지는 test_draft_upload.py 가 본다.
"""
import ast
import re
import unittest

import _bootstrap  # noqa: F401
from pipeline import auth_check as ac
from pipeline import registry
from pipeline.publishers.base import PublishError

REAL = _bootstrap.ROOT
HANGUL = re.compile(r"[가-힣]")
_REGISTRY = registry.load_registry(REAL / "pipeline" / "blogs.json")
EN_SECRETS = registry.get_blog(_REGISTRY, "blogger_macat")["secrets"]      # 영문 Blogger: BLOGGER_*
KO_SECRETS = registry.get_blog(_REGISTRY, "blogger_kcyoon")["secrets"]     # 한글 Blogger: BLOGGER_KO_*
ROLES = ("blog_id", "client_id", "client_secret", "refresh_token")
# 안내 문장을 시크릿 이름 자리표시자로 바꾸기 전(작업 D, 6dca5d7)의 영문 Blogger 문장 일곱 개 그대로. 영문 블로그의 실행 화면이 바이트 단위로 같아야 한다(독립 검증 N3).
ENGLISH_SENTENCES_BEFORE_THE_CHANGE = {
    "api_error": "Blogger API 가 오류를 돌려줬습니다. 이 단계의 로그를 확인하고 잠시 뒤 다시 실행하세요.",
    "auth_expired": "Blogger 인증(refresh token)이 만료되었거나 폐기되었습니다. OAuth 동의 화면이 '프로덕션' 상태인지 확인하고 토큰을 새로 발급해 "
                    "BLOGGER_REFRESH_TOKEN 시크릿을 갱신하세요(.github/editorial/BLOGGER_API_SETUP.md).",
    "auth_failed": "Blogger 인증 또는 블로그 접근 권한 확인에 실패했습니다. BLOGGER_BLOG_ID·BLOGGER_CLIENT_ID·BLOGGER_CLIENT_SECRET 시크릿, "
                   "Blogger API 사용 설정, 로그인한 계정의 블로그 권한을 확인하세요.",
    "bad_response": "Blogger 가 필요한 값이 빠진 응답을 돌려줬습니다. 이 단계의 로그를 확인하고 잠시 뒤 다시 실행하세요.",
    "blog_mismatch": "인증은 통과했지만 BLOGGER_BLOG_ID 가 가리키는 블로그의 주소가 레지스트리(pipeline/blogs.json)의 url 과 다릅니다. "
                     "엉뚱한 블로그에 쓰지 않도록 멈췄습니다. 블로그 ID 시크릿을 확인하세요.",
    "network": "Blogger 서버에 연결하지 못했습니다(연결 실패·시간 초과). 잠시 뒤 다시 실행하세요.",
    "unexpected": "인증 점검 중 예기치 않은 오류가 났습니다. 이 단계의 로그를 확인하세요.",
}
BLOG_MISMATCH_MESSAGE_BEFORE_THE_CHANGE = ("BLOGGER_BLOG_ID 가 가리키는 블로그의 주소가 레지스트리의 url 과 다릅니다"
                                           "(응답 주소는 다른 블로그일 수 있어 출력하지 않습니다)")


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


class SecretNamesInSentencesTest(unittest.TestCase):
    """독립 검증 N3: 인증 실패 안내가 영문 시크릿 이름(BLOGGER_BLOG_ID 등)만 말해, 한글 Blogger 실행의 실패를 보고 영문 값을 갱신하러 갈 수 있었다.
    이제 문장 속 이름은 그 블로그(레지스트리 항목의 secrets)의 이름이고, 영문 블로그의 문장은 바뀌기 전과 바이트 단위로 같다."""
    NAMED_ROLES = {"auth_expired": {"refresh_token"}, "auth_failed": {"blog_id", "client_id", "client_secret"}, "blog_mismatch": {"blog_id"}}

    def test_the_english_blog_gets_exactly_the_sentences_it_got_before_the_change(self):
        self.assertEqual(set(ENGLISH_SENTENCES_BEFORE_THE_CHANGE), set(ac.KNOWN_CODES))     # 분류를 더하거나 빼면 이 표와 영문 바이트 불변을 같이 본다
        for code, before in ENGLISH_SENTENCES_BEFORE_THE_CHANGE.items():
            with self.subTest(code):
                self.assertEqual(ac.sentence_for(code), before)                              # 이름을 주지 않으면 영문 이름
                self.assertEqual(ac.sentence_for(code, EN_SECRETS), before)                  # 영문 블로그의 레지스트리 항목을 줘도 같다

    def test_the_korean_blog_gets_the_same_sentences_with_only_the_secret_names_replaced(self):
        for code, before in ENGLISH_SENTENCES_BEFORE_THE_CHANGE.items():
            expected = before
            for role in ROLES:
                expected = expected.replace(EN_SECRETS[role], KO_SECRETS[role])
            with self.subTest(code):
                self.assertEqual(ac.sentence_for(code, KO_SECRETS), expected)
                if code in self.NAMED_ROLES:
                    self.assertNotEqual(expected, before)                                    # 이름이 있는 문장은 실제로 바뀐다(대조가 헛돌지 않는다)

    def test_each_sentence_names_exactly_the_secrets_it_is_about_and_only_that_blogs(self):
        for label, own_secrets, other_secrets in (("영문", EN_SECRETS, KO_SECRETS), ("한글", KO_SECRETS, EN_SECRETS)):
            foreign = {other_secrets[role] for role in ROLES} - {own_secrets[role] for role in ROLES}
            for code in sorted(ac.KNOWN_CODES):
                text = ac.sentence_for(code, own_secrets)
                found = set(re.findall(r"BLOGGER_[A-Z_]+", text)) - {"BLOGGER_API_SETUP"}        # 안내 문서 파일 이름은 시크릿이 아니다
                with self.subTest(label=label, code=code):
                    self.assertEqual(found, {own_secrets[role] for role in self.NAMED_ROLES.get(code, ())})
                    self.assertEqual(found & foreign, set())

    def test_no_placeholder_is_left_unfilled_and_every_variant_is_still_safe_for_an_annotation(self):
        for secrets in (None, EN_SECRETS, KO_SECRETS, {}, {"blog_id": "BLOGGER_KO_BLOG_ID"}, {"blog_id": "x\n::error::위조", "refresh_token": "{blog_id}"}):
            for code in sorted(ac.KNOWN_CODES):
                sentence = ac.sentence_for(code, secrets)
                with self.subTest(code=code, secrets=secrets):
                    for bad in ("\n", "\r", "::", "##[", "{", "}", "%s", "$"):
                        self.assertNotIn(bad, sentence)

    def test_the_templates_use_only_the_four_known_placeholders(self):
        for code, row in ac.FAILURES.items():
            with self.subTest(code):
                self.assertLessEqual(set(re.findall(r"\{(\w*)\}", row[2])), set(ROLES))
                self.assertEqual(len(re.findall(r"[{}]", row[2])), 2 * len(re.findall(r"\{\w+\}", row[2])))   # 짝이 안 맞는 중괄호가 없다

    def test_the_default_names_are_the_english_registry_names_and_a_given_name_wins(self):
        self.assertEqual(ac.DEFAULT_SECRET_NAMES, {role: EN_SECRETS[role] for role in ROLES})
        self.assertEqual(ac.secret_names_for(None), ac.DEFAULT_SECRET_NAMES)
        self.assertEqual(ac.secret_names_for(KO_SECRETS), {role: KO_SECRETS[role] for role in ROLES})    # LLM 키 역할은 쓰지 않는다
        self.assertEqual(ac.secret_names_for({"blog_id": "MY_OWN_BLOG_ID"})["blog_id"], "MY_OWN_BLOG_ID")
        self.assertEqual(ac.secret_names_for({"blog_id": "MY_OWN_BLOG_ID"})["client_id"], EN_SECRETS["client_id"])   # 없는 역할만 기본 이름

    def test_a_secret_name_that_is_not_an_environment_variable_name_is_never_put_into_a_sentence(self):
        """이름은 ::error:: 주석에 그대로 들어간다 — 모양이 틀린 값(소문자·공백·줄바꿈·명령 표기·너무 짧거나 긴 것·문자열이 아닌 것)은 그 역할만 영문 기본 이름으로 되돌린다."""
        hostile = ["blogger_blog_id", "BLOGGER BLOG ID", "X\n::error::위조", "::set-output name=x::y", "A" * 80, "AB", "BLOGGER_KO_BLOG_ID\n", "${{ secrets.X }}",
                   "", None, 5, ["BLOGGER_KO_BLOG_ID"], "한글이름", "1ABC"]
        for bad in hostile:
            with self.subTest(repr(bad)):
                names = ac.secret_names_for({"blog_id": bad, "client_id": "BLOGGER_KO_CLIENT_ID"})
                self.assertEqual(names["blog_id"], EN_SECRETS["blog_id"])
                self.assertEqual(names["client_id"], "BLOGGER_KO_CLIENT_ID")                 # 올바른 역할은 그대로
                for code in ("auth_failed", "blog_mismatch"):
                    self.assertNotIn("\n", ac.sentence_for(code, {"blog_id": bad}))

    def test_secrets_that_are_not_a_dictionary_or_have_no_such_roles_fall_back_to_the_english_names(self):
        for given in (None, "BLOGGER_KO_BLOG_ID", [], 5, {}, {"llm_api_key": "GEMINI_API_KEY"}):
            with self.subTest(repr(given)):
                self.assertEqual(ac.secret_names_for(given), ac.DEFAULT_SECRET_NAMES)

    def test_the_check_names_the_blog_id_secret_of_the_blog_in_its_blog_mismatch_message(self):
        other = "https://private-diary-of-someone.blogspot.com/"
        for secrets, expected in ((None, "BLOGGER_BLOG_ID"), (EN_SECRETS, "BLOGGER_BLOG_ID"), (KO_SECRETS, "BLOGGER_KO_BLOG_ID")):
            with self.subTest(expected=expected, secrets=secrets):
                with self.assertRaises(PublishError) as ctx:
                    ac.auth_check(FakePublisher({"name": "개인 일기장", "url": other}), "https://kcyoon.blogspot.com/", secrets)
                self.assertEqual(ctx.exception.code, "blog_mismatch")
                text = str(ctx.exception)
                self.assertTrue(text.startswith(f"{expected} 가 가리키는 블로그의 주소가 레지스트리의 url 과 다릅니다"), text)
                for leaked in (other, "private-diary", "개인 일기장"):                         # 같은 계정의 다른 블로그 주소·이름은 여전히 쓰지 않는다
                    self.assertNotIn(leaked, text)
        with self.assertRaises(PublishError) as ctx:
            ac.auth_check(FakePublisher({"name": "x", "url": other}), "https://macat0722.blogspot.com/")
        self.assertEqual(str(ctx.exception), BLOG_MISMATCH_MESSAGE_BEFORE_THE_CHANGE)          # 영문(기본)은 바뀌기 전 문구 그대로
        with self.assertRaises(PublishError) as ctx:
            ac.auth_check(FakePublisher({"name": "x", "url": other}), "https://kcyoon.blogspot.com/", KO_SECRETS)
        self.assertNotIn("BLOGGER_BLOG_ID", str(ctx.exception))                                  # 한글 실행 문구에 영문 이름이 없다


def hardcoded_secret_names(source, allowed_assignment=None):
    """소스 안의 문자열 상수(독스트링 제외)에 박힌 영문 Blogger 시크릿 이름 [(줄, 앞부분)]. allowed_assignment 이름의 대입문 안은 허용한다(기본 이름표)."""
    pattern = re.compile(r"BLOGGER_(?:BLOG_ID|CLIENT_ID|CLIENT_SECRET|REFRESH_TOKEN)")
    tree = ast.parse(source)
    docs, allowed = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docs.add(id(first.value))
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == allowed_assignment for t in node.targets):
            allowed.update(range(node.lineno, node.end_lineno + 1))
    return [(node.lineno, node.value[:40]) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs and pattern.search(node.value) and node.lineno not in allowed]


class NoHardcodedSecretNamesTest(unittest.TestCase):
    """안내·오류 문구를 만드는 모듈에 영문 시크릿 이름이 글자로 박히면(문구 끝에 이름을 덧붙이다가 흔히 생긴다) 한글 실행이 영문 이름을 말한다 — 이름은 이름표
    DEFAULT_SECRET_NAMES 한 곳에만 있어야 하고, 문구는 그 블로그의 이름(sentence_for·secret_names_for)으로 채운다."""

    def test_the_scan_finds_a_hardcoded_name_and_skips_docstrings_and_the_allowed_table(self):
        self.assertEqual(len(hardcoded_secret_names('def f():\n    return f"BLOGGER_BLOG_ID 시크릿을 확인하세요 {1}"\n')), 1)
        self.assertEqual(len(hardcoded_secret_names('MSG = "인증은 통과했지만 BLOGGER_BLOG_ID 가 가리키는"\n')), 1)
        self.assertEqual(hardcoded_secret_names('"""BLOGGER_BLOG_ID 를 설명하는 독스트링"""\ndef f():\n    """BLOGGER_REFRESH_TOKEN"""\n'), [])
        self.assertEqual(hardcoded_secret_names('NAMES = {"blog_id": "BLOGGER_BLOG_ID"}\nx = 1\n', "NAMES"), [])
        self.assertEqual(len(hardcoded_secret_names('NAMES = {"blog_id": "BLOGGER_BLOG_ID"}\nx = "BLOGGER_BLOG_ID"\n', "NAMES")), 1)

    def test_the_modules_that_build_the_messages_name_no_english_secret_outside_the_default_table(self):
        for relative, allowed in (("pipeline/auth_check.py", "DEFAULT_SECRET_NAMES"), ("pipeline/publishers/blogger.py", None), ("pipeline/run.py", None)):
            with self.subTest(relative):
                self.assertEqual(hardcoded_secret_names((REAL / relative).read_text(encoding="utf-8"), allowed), [])

    def test_the_adapters_expired_hint_names_no_secret_so_it_is_right_for_every_blog(self):
        """EXPIRED_HINT 는 'refresh token' 이라고만 말하고 시크릿 이름은 말하지 않는다 — 이름을 더하려면 어댑터가 알아야 하므로 여기서 막아 같은 문제를 다시 만들지 않게 한다."""
        from pipeline.publishers import blogger
        self.assertNotRegex(blogger.EXPIRED_HINT, r"BLOGGER_|GEMINI_API_KEY|PIPELINE_SECRET_")


if __name__ == "__main__":
    unittest.main()
