"""시크릿 값의 보이지 않는 문자(작업 H-0, 결함 D-79, 이슈 #58): 채팅 앱·문서에서 복사해 붙인 값에 섞이는 폭 없는 공백(U+200B)·단어 결합자(U+2060)·BOM(U+FEFF) 같은 문자와
제어 문자를 지우고 쓰되, 어느 시크릿이었는지는 **이름만** 알린다.

구성: ① console.clean_secret(문자 종류 전부·시작·가운데·끝·보이지 않는 문자가 없는 값은 `.strip()` 과 똑같음) ② registry.resolve_secrets·cleaned_secret_names(우선순위·이름만)
③ Blogger 러너(`::notice::`·인증 점검 요약·값은 어디에도 없음·깨끗한 값의 출력은 그대로) ④ 텔레그램 값(Notifier·status). 네트워크·실제 시크릿은 없다.
"""
import random
import tempfile
import unittest
import unicodedata
from unittest import mock

import _bootstrap
import notify_helpers as nh
from notify_helpers import CHAT, TOKEN, leaks
from pipeline import console, notify, registry
from pipeline import run as run_mod
from pipeline.console import INVISIBLE_CODEPOINTS, clean_secret, secret_was_cleaned
from test_draft_upload import ALL_ENV, GEMINI_VALUE, SECRET_VALUES, Runner
from test_run import FakePublisher

ROOT = _bootstrap.ROOT
ZW = chr(0x200B)
WJ = chr(0x2060)
BOM = chr(0xFEFF)
BLOG = registry.get_blog(registry.load_registry(ROOT / "pipeline" / "blogs.json"), "blogger_macat")
EXTRA_FORMAT_CHARS = [chr(code) for code in (0x061C, 0x180E, 0x206A, 0x206B, 0x206C, 0x206D, 0x206E, 0x206F, 0xFFF9, 0xFFFA, 0xFFFB, 0xE0001, 0xE0041, 0xE007F, 0x0600, 0x06DD, 0x110BD)]
CONTROL_CHARS = [chr(code) for code in (0x00, 0x01, 0x07, 0x08, 0x0B, 0x0C, 0x1B, 0x1F, 0x7F, 0x80, 0x85, 0x9F)]
INTERIOR_WHITESPACE_CONTROLS = ["\t", "\n", "\r", "\r\n"]


def dirty(value, char=ZW):
    """값의 시작·가운데·끝에 보이지 않는 문자를 끼운다."""
    middle = len(value) // 2
    return char + value[:middle] + char + value[middle:] + char


class CleanSecretTest(unittest.TestCase):
    def test_the_shared_list_is_the_one_the_alert_text_cleaner_uses(self):
        self.assertIs(notify._INVISIBLE_CODEPOINTS, console.INVISIBLE_CODEPOINTS)
        self.assertIs(notify._INVISIBLE_RE, console.INVISIBLE_RE)
        expected = [0x00AD, *range(0x200B, 0x2010), *range(0x202A, 0x202F), *range(0x2060, 0x2065), *range(0x2066, 0x206A), 0xFEFF]
        self.assertEqual(list(INVISIBLE_CODEPOINTS), expected)
        for code in (0x2065, 0x202F, 0x2010, 0x2028, 0x00A0, 0x3164):
            self.assertNotIn(code, INVISIBLE_CODEPOINTS, hex(code))                    # 눈에 보이는 공백류나 줄 구분자는 이 목록이 아니다

    def test_every_listed_character_is_removed_at_the_start_in_the_middle_and_at_the_end(self):
        self.assertEqual(len(INVISIBLE_CODEPOINTS), 21)
        for code in INVISIBLE_CODEPOINTS:
            char = chr(code)
            self.assertEqual(clean_secret(f"{char}abc123"), "abc123", hex(code))
            self.assertEqual(clean_secret(f"abc{char}123"), "abc123", hex(code))
            self.assertEqual(clean_secret(f"abc123{char}"), "abc123", hex(code))
            self.assertEqual(clean_secret(f"{char}a{char}b{char}c{char}{char}"), "abc", hex(code))
            self.assertEqual(clean_secret(char * 5), "", hex(code))

    def test_the_named_cases_from_issue_58(self):
        for name, char in (("폭 없는 공백", chr(0x200B)), ("폭 없는 비결합자", chr(0x200C)), ("폭 없는 결합자", chr(0x200D)), ("왼쪽→오른쪽 표시", chr(0x200E)),
                           ("오른쪽→왼쪽 표시", chr(0x200F)), ("단어 결합자", chr(0x2060)), ("함수 적용", chr(0x2061)), ("보이지 않는 곱셈", chr(0x2062)),
                           ("보이지 않는 구분자", chr(0x2063)), ("보이지 않는 덧셈", chr(0x2064)), ("방향 덮어쓰기", chr(0x202E)), ("방향 격리", chr(0x2066)),
                           ("BOM", chr(0xFEFF)), ("소프트 하이픈", chr(0x00AD))):
            self.assertEqual(clean_secret(dirty("GOCSPX-abcDEF123_-xyz", char)), "GOCSPX-abcDEF123_-xyz", name)

    def test_control_characters_are_removed_anywhere(self):
        for char in CONTROL_CHARS:
            self.assertEqual(clean_secret(f"ab{char}cd"), "abcd", hex(ord(char)))
            self.assertEqual(clean_secret(f"{char}abcd{char}"), "abcd", hex(ord(char)))
        for char in INTERIOR_WHITESPACE_CONTROLS:
            self.assertEqual(clean_secret(f"ab{char}cd"), "abcd", repr(char))                # 줄 바꿈·탭이 값 가운데 끼어도 지운다

    def test_other_format_characters_and_lone_surrogates_are_removed_too(self):
        for char in EXTRA_FORMAT_CHARS:
            self.assertEqual(unicodedata.category(char), "Cf", hex(ord(char)))
            self.assertEqual(clean_secret(f"a{char}b"), "ab", hex(ord(char)))
        for char in (chr(0xD800), chr(0xDC80), chr(0xDFFF)):
            self.assertEqual(clean_secret(f"a{char}b"), "ab", hex(ord(char)))

    def test_a_value_without_invisible_characters_is_exactly_what_strip_gave_before(self):
        samples = ["", " ", "abc", "  abc  ", "\tabc\n", " abc ", "　abc　", " abc ", "ab cd", "ab cd", "AIza" + "B" * 35, "1//0" + "d" * 45,
                   "GOCSPX-" + "c" * 24, "123456789012-abc.apps.googleusercontent.com", "한글 값", "emoji \U0001F600 ok", "a-b_c.d/e+f=g", "tel:0101234", "\r\n \x20 key \x20\r\n"]
        for sample in samples:
            self.assertEqual(clean_secret(sample), sample.strip(), repr(sample))
            self.assertFalse(secret_was_cleaned(sample), repr(sample))

    def test_random_values_without_invisible_characters_are_unchanged_from_strip(self):
        rng = random.Random(20261028)
        alphabet = "abcXYZ019-_./:+= \t\n한글가나" + chr(0xA0) + chr(0x3000)
        for _ in range(2000):
            sample = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
            if any(unicodedata.category(ch) in ("Cc", "Cf", "Cs") and ch not in " \t\n" for ch in sample):
                continue
            stripped = sample.strip()
            without_controls = "".join(ch for ch in stripped if unicodedata.category(ch) != "Cc")      # 값 가운데의 줄 바꿈·탭은 제어 문자라 지운다
            self.assertEqual(clean_secret(sample), without_controls, repr(sample))
            if without_controls == stripped:
                self.assertEqual(clean_secret(sample), stripped, repr(sample))                         # 제어 문자가 없으면 예전의 strip 과 똑같다
                self.assertFalse(secret_was_cleaned(sample), repr(sample))

    def test_ordinary_and_non_ascii_spaces_inside_a_value_are_kept(self):
        for space in (" ", chr(0xA0), chr(0x3000), chr(0x2003)):
            self.assertEqual(clean_secret("ab" + space + "cd"), "ab" + space + "cd", hex(ord(space)))

    def test_none_and_non_text_values(self):
        self.assertEqual(clean_secret(None), "")
        self.assertEqual(clean_secret(123), "123")
        self.assertEqual(clean_secret(b"x".decode()), "x")
        self.assertFalse(secret_was_cleaned(None))
        self.assertFalse(secret_was_cleaned(""))

    def test_secret_was_cleaned_is_true_only_when_more_than_the_ends_was_removed(self):
        self.assertTrue(secret_was_cleaned("ab" + ZW))
        self.assertTrue(secret_was_cleaned(WJ + "ab"))
        self.assertTrue(secret_was_cleaned("a\x07b"))
        self.assertTrue(secret_was_cleaned("a\tb"))
        self.assertTrue(secret_was_cleaned(ZW))                                          # 보이지 않는 문자뿐인 값
        self.assertFalse(secret_was_cleaned("  ab  "))
        self.assertFalse(secret_was_cleaned("ab\n"))                                     # 끝의 줄 바꿈은 예전에도 잘렸다

    def test_the_cleaner_never_returns_a_character_it_should_have_removed(self):
        rng = random.Random(7)
        pool = [chr(code) for code in INVISIBLE_CODEPOINTS] + CONTROL_CHARS + EXTRA_FORMAT_CHARS + list("abcXYZ019-_")
        for _ in range(500):
            sample = "".join(rng.choice(pool) for _ in range(rng.randint(0, 30)))
            result = clean_secret(sample)
            self.assertFalse(any(unicodedata.category(ch) in ("Cc", "Cf", "Cs") for ch in result), repr(sample))
            self.assertEqual(result, "".join(ch for ch in sample if ch in "abcXYZ019-_"), repr(sample))


class ResolveSecretsTest(unittest.TestCase):
    ROLES = BLOG["secrets"]                                     # {역할: 환경변수 이름}

    def environ(self, **named):
        return dict(named)

    def test_every_role_gets_its_cleaned_value(self):
        environ = {name: dirty(f"value-{role}") for role, name in self.ROLES.items()}
        resolved = registry.resolve_secrets(BLOG, environ)
        self.assertEqual(resolved, {role: f"value-{role}" for role in self.ROLES})

    def test_clean_values_resolve_exactly_as_before(self):
        environ = {self.ROLES["client_id"]: "  cid  ", self.ROLES["blog_id"]: "123\n", self.ROLES["refresh_token"]: ""}
        resolved = registry.resolve_secrets(BLOG, environ)
        self.assertEqual((resolved["client_id"], resolved["blog_id"], resolved["refresh_token"], resolved["client_secret"], resolved["llm_api_key"]), ("cid", "123", "", "", ""))

    def test_the_workflow_override_wins_and_is_cleaned(self):
        environ = {"PIPELINE_SECRET_CLIENT_ID": dirty("override-id"), self.ROLES["client_id"]: "named-id"}
        self.assertEqual(registry.resolve_secrets(BLOG, environ)["client_id"], "override-id")

    def test_an_override_that_is_only_invisible_characters_falls_back_to_the_named_secret(self):
        environ = {"PIPELINE_SECRET_CLIENT_ID": ZW + WJ + BOM, self.ROLES["client_id"]: dirty("named-id")}
        self.assertEqual(registry.resolve_secrets(BLOG, environ)["client_id"], "named-id")
        self.assertEqual(registry.resolve_secrets(BLOG, {"PIPELINE_SECRET_CLIENT_ID": ZW})["client_id"], "")

    def test_missing_roles_count_a_value_made_only_of_invisible_characters_as_missing(self):
        environ = {name: "v" for name in self.ROLES.values()}
        environ[self.ROLES["client_secret"]] = ZW + WJ
        self.assertEqual(registry.missing_secret_roles(BLOG, environ), ["client_secret"])

    def test_resolving_does_not_change_the_environment(self):
        environ = {self.ROLES["client_id"]: dirty("x")}
        snapshot = dict(environ)
        registry.resolve_secrets(BLOG, environ)
        registry.cleaned_secret_names(BLOG, environ)
        self.assertEqual(environ, snapshot)


class CleanedNamesTest(unittest.TestCase):
    ROLES = BLOG["secrets"]

    def test_names_are_the_registry_secret_names_not_the_values(self):
        environ = {self.ROLES["client_id"]: dirty("abc-id"), self.ROLES["refresh_token"]: dirty("abc-refresh"), self.ROLES["blog_id"]: "clean"}
        names = registry.cleaned_secret_names(BLOG, environ)
        self.assertEqual(names, [self.ROLES["client_id"], self.ROLES["refresh_token"]])
        self.assertTrue(set(names) <= set(self.ROLES.values()))
        self.assertEqual(leaks(" ".join(names)), [])
        self.assertNotIn("abc-id", " ".join(names))

    def test_nothing_is_reported_for_clean_or_missing_values(self):
        self.assertEqual(registry.cleaned_secret_names(BLOG, {}), [])
        self.assertEqual(registry.cleaned_secret_names(BLOG, {name: " v \n" for name in self.ROLES.values()}), [])

    def test_the_workflow_override_is_reported_under_the_registry_name(self):
        """워크플로 래퍼는 GitHub 시크릿 `BLOGGER_CLIENT_ID` 를 PIPELINE_SECRET_CLIENT_ID 로 넘긴다 — 운영자가 다시 등록할 이름은 앞쪽이다."""
        environ = {"PIPELINE_SECRET_CLIENT_ID": dirty("override-id")}
        self.assertEqual(registry.cleaned_secret_names(BLOG, environ), [self.ROLES["client_id"]])

    def test_only_the_value_that_is_actually_used_counts(self):
        environ = {"PIPELINE_SECRET_CLIENT_ID": "clean-override", self.ROLES["client_id"]: dirty("unused-dirty")}
        self.assertEqual(registry.cleaned_secret_names(BLOG, environ), [])                 # 우선순위에서 밀린 값은 쓰이지 않는다
        environ = {"PIPELINE_SECRET_CLIENT_ID": ZW, self.ROLES["client_id"]: dirty("named")}
        self.assertEqual(registry.cleaned_secret_names(BLOG, environ), [self.ROLES["client_id"]])

    def test_a_shared_name_is_listed_once(self):
        blog = {"secrets": {"a": "SAME_NAME", "b": "SAME_NAME"}}
        self.assertEqual(registry.cleaned_secret_names(blog, {"SAME_NAME": dirty("x")}), ["SAME_NAME"])

    def test_the_real_registry_names_are_safe_to_print(self):
        reg = registry.load_registry(ROOT / "pipeline" / "blogs.json")
        for raw in reg["blogs"]:
            for name in registry.merged_blog(reg, raw)["secrets"].values():
                self.assertRegex(name, r"^[A-Z][A-Z0-9_]{2,63}$")


class RunnerNoticeTest(unittest.TestCase):
    def setUp(self):
        self.r = Runner(self)

    def dirty_env(self, only=None):
        env = dict(ALL_ENV)
        for name in (only or [n for n in SECRET_VALUES]):
            env[name] = dirty(env[name])
        return env

    def notice_lines(self, res):
        return [line for line in res.lines if line.startswith("::notice::") and "보이지 않는 문자" in line]

    def test_the_auth_check_says_which_secrets_were_cleaned_in_the_log_and_the_summary(self):
        names = ["BLOGGER_CLIENT_ID", "BLOGGER_REFRESH_TOKEN"]
        pub = FakePublisher()
        res = self.r.run("draft", self.dirty_env(names), pub, extra=["--auth-check"])
        self.assertEqual((res.code, pub.health_calls), (0, 1), res.out)
        expected = run_mod.CLEANED_NOTICE.format(key="blogger_macat", names="BLOGGER_CLIENT_ID, BLOGGER_REFRESH_TOKEN")
        self.assertEqual(self.notice_lines(res), [expected])
        self.assertIn("시크릿 값에 보이지 않는 문자", expected)
        summary = res.summary_lines
        self.assertEqual(len(summary), 5, res.summary)
        self.assertIn("**AUTH_CHECK_OK**", summary[1])
        self.assertEqual(summary[4], "- " + run_mod.CLEANED_SUMMARY.format(names="BLOGGER_CLIENT_ID, BLOGGER_REFRESH_TOKEN"))
        self.assertIn("다시 등록하는 것을 권장", summary[4])

    def test_no_value_dirty_or_clean_appears_anywhere(self):
        env = self.dirty_env()
        res = self.r.run("draft", env, FakePublisher(), extra=["--auth-check"])
        everything = res.everything()
        for name, value in env.items():
            clean = clean_secret(value)
            self.assertNotIn(value, everything, name)
            self.assertNotIn(clean, everything, name)
        self.assertEqual(len(self.notice_lines(res)), 1)
        self.assertIn("BLOGGER_BLOG_ID, BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET, BLOGGER_REFRESH_TOKEN", self.notice_lines(res)[0])

    def test_the_gemini_key_is_cleaned_by_the_same_function_and_reported_by_name(self):
        env = dict(ALL_ENV, GEMINI_API_KEY=dirty(GEMINI_VALUE))
        res = self.r.run("draft", env, FakePublisher(), extra=["--auth-check"])
        self.assertEqual(self.notice_lines(res), [run_mod.CLEANED_NOTICE.format(key="blogger_macat", names="GEMINI_API_KEY")])
        self.assertEqual(registry.resolve_secrets(BLOG, env)["llm_api_key"], GEMINI_VALUE)

    def test_clean_secrets_make_the_same_output_as_before_with_no_notice(self):
        res = self.r.run("draft", ALL_ENV, FakePublisher(), extra=["--auth-check"])
        self.assertEqual(self.notice_lines(res), [])
        self.assertEqual(len(res.summary_lines), 4)
        self.assertNotIn("보이지 않는 문자", res.out + res.summary)
        padded = dict(ALL_ENV, BLOGGER_CLIENT_ID="  " + ALL_ENV["BLOGGER_CLIENT_ID"] + "\n")
        res = self.r.run("draft", padded, FakePublisher(), extra=["--auth-check"])
        self.assertEqual(self.notice_lines(res), [])                                     # 앞뒤 공백은 예전에도 잘렸다 — 알릴 일이 아니다

    def test_a_failed_auth_check_also_carries_the_hint_in_its_summary(self):
        pub = FakePublisher(blog_url="https://other.blogspot.com/")
        res = self.r.run("draft", self.dirty_env(["BLOGGER_BLOG_ID"]), pub, extra=["--auth-check"])
        self.assertEqual(res.code, 2)
        self.assertIn("**AUTH_CHECK_FAILED**", res.summary_lines[1])
        self.assertEqual(res.summary_lines[-1], "- " + run_mod.CLEANED_SUMMARY.format(names="BLOGGER_BLOG_ID"))
        self.assertEqual(len(self.notice_lines(res)), 1)

    def test_a_normal_run_announces_it_once_in_the_log_before_the_pre_check(self):
        pub = FakePublisher()
        res = self.r.run("draft", self.dirty_env(["BLOGGER_CLIENT_SECRET"]), pub)
        self.assertEqual((res.code, res.last["status"]), (0, "draft_uploaded"), res.out)
        self.assertEqual(self.notice_lines(res), [run_mod.CLEANED_NOTICE.format(key="blogger_macat", names="BLOGGER_CLIENT_SECRET")])
        self.assertLess(res.lines.index(self.notice_lines(res)[0]), next(index for index, line in enumerate(res.lines) if "인증 점검 통과" in line))

    def test_a_practice_run_does_not_announce_because_it_uses_no_secret(self):
        res = self.r.run("draft", self.dirty_env(), FakePublisher(), extra=["--dry-run"])
        self.assertEqual(self.notice_lines(res), [])

    def test_a_failed_pre_check_of_a_normal_run_carries_the_hint_in_its_summary(self):
        pub = FakePublisher(blog_url="https://other.blogspot.com/")
        res = self.r.run("draft", self.dirty_env(["BLOGGER_BLOG_ID"]), pub)
        self.assertEqual(res.code, 2)
        self.assertEqual(res.summary_lines[-1], "- " + run_mod.CLEANED_SUMMARY.format(names="BLOGGER_BLOG_ID"))

    def test_the_default_publisher_receives_the_cleaned_values(self):
        seen = []

        class Recorder:
            def __init__(self, blog_id, client_id, client_secret, refresh_token, secret_names=None):    # secret_names: D-FIX(N3) 가 기본 게시자 생성에 더한 선택 인자
                seen.append((blog_id, client_id, client_secret, refresh_token))

        env = self.dirty_env()
        with mock.patch("pipeline.publishers.blogger.BloggerPublisher", Recorder):
            run_mod.default_publisher_factory(BLOG, env)
        self.assertEqual(seen, [tuple(SECRET_VALUES[name] for name in ("BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN"))])

    def test_error_messages_hide_the_cleaned_values_too(self):
        env = self.dirty_env()
        values = run_mod._secret_values(BLOG, env)
        for name in SECRET_VALUES:
            self.assertIn(SECRET_VALUES[name], values)
            self.assertNotIn(env[name], values)

    def test_the_notice_is_one_line_with_no_value_and_no_forged_command(self):
        line = run_mod.CLEANED_NOTICE.format(key="blogger_macat", names="BLOGGER_CLIENT_ID")
        self.assertEqual(len(line.splitlines()), 1)
        self.assertTrue(line.startswith("::notice::"))
        self.assertEqual(line.count("::"), 2)                                              # `::notice::` 자신의 두 번뿐 — 값에서 온 `::` 는 없다


class TelegramValuesTest(unittest.TestCase):
    def test_a_token_and_chat_id_pasted_with_invisible_characters_still_work(self):
        environ = {"TELEGRAM_BOT_TOKEN": dirty(TOKEN), "TELEGRAM_CHAT_ID": dirty(CHAT, WJ)}
        notifier, net, _ = nh.make_notifier(environ=environ)
        self.assertTrue(notifier.enabled)
        result = notifier.send_message("확인")
        self.assertTrue(result.sent)
        self.assertEqual(net.requests[0].full_url, nh.SEND_URL)
        self.assertEqual(net.bodies()[0]["chat_id"], int(CHAT))

    def test_a_value_made_only_of_invisible_characters_is_not_a_secret(self):
        for environ in ({"TELEGRAM_BOT_TOKEN": ZW, "TELEGRAM_CHAT_ID": CHAT}, {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": WJ + BOM}):
            notifier, net, _ = nh.make_notifier(environ=environ)
            self.assertFalse(notifier.enabled)
            self.assertEqual((notifier.send_message("x").reason, net.calls), (notify.DISABLED, 0))

    def test_the_cleaned_token_is_still_scrubbed_from_every_output(self):
        notifier, _, _ = nh.make_notifier(environ={"TELEGRAM_BOT_TOKEN": dirty(TOKEN), "TELEGRAM_CHAT_ID": CHAT})
        self.assertEqual(leaks(notifier.scrub(f"오류 {TOKEN} 와 {nh.SECRET_HALF}")), [])

    def test_status_names_the_secret_with_invisible_characters_and_never_the_value(self):
        lines, summary = [], []
        environ = {"TELEGRAM_BOT_TOKEN": dirty(TOKEN), "TELEGRAM_CHAT_ID": CHAT}
        with mock.patch.object(notify, "_write_summary", lambda env, text, out: summary.append(text)):
            notify.run_status(notify.Notifier(environ), environ, lines.append)
        self.assertEqual(lines[:2], ["TELEGRAM_BOT_TOKEN: 등록됨", "TELEGRAM_CHAT_ID: 등록됨"])
        self.assertEqual(lines[2], "[참고] " + notify.CLEANED_HINT.format(names="TELEGRAM_BOT_TOKEN"))
        self.assertIn("`TELEGRAM_BOT_TOKEN`", summary[0])
        self.assertIn("원본에서 바로 복사해 다시 등록하는 것을 권장합니다", summary[0])
        self.assertEqual(leaks("\n".join(lines) + summary[0]), [])

    def test_status_is_the_same_as_before_for_clean_values(self):
        lines, summary = [], []
        environ = {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT}
        with mock.patch.object(notify, "_write_summary", lambda env, text, out: summary.append(text)):
            notify.run_status(notify.Notifier(environ), environ, lines.append)
        self.assertEqual(lines, ["TELEGRAM_BOT_TOKEN: 등록됨", "TELEGRAM_CHAT_ID: 등록됨"])
        self.assertNotIn("보이지 않는 문자", summary[0])

    def test_status_counts_invisible_only_values_as_not_registered(self):
        lines = []
        environ = {"TELEGRAM_BOT_TOKEN": ZW, "TELEGRAM_CHAT_ID": CHAT}
        with mock.patch.object(notify, "_write_summary", lambda env, text, out: None):
            notify.run_status(notify.Notifier(environ), environ, lines.append)
        self.assertEqual(lines[0], "TELEGRAM_BOT_TOKEN: 없음")

    def test_status_exit_code_and_ready_output_for_dirty_but_complete_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_file = f"{tmp}/out.txt"
            environ = {"TELEGRAM_BOT_TOKEN": dirty(TOKEN), "TELEGRAM_CHAT_ID": dirty(CHAT), "GITHUB_OUTPUT": out_file}
            code = notify.main(["status"], environ=environ, out=lambda text: None)
            self.assertEqual(code, 0)
            with open(out_file, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "ready=true\n")


if __name__ == "__main__":
    unittest.main()
