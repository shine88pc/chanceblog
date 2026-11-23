"""초안 패키지 채널(티스토리·네이버)의 `llm_api_key` 시크릿 이름 좁히기(독립 감사 BA-S1-5, 결함 D-410).

이 채널의 시크릿 역할은 `llm_api_key` 하나뿐이고 그 값은 Gemini 호출의 키로 구글에 전송된다. 옛 검증은 이름에 계정 정보 낱말(PASSWORD·COOKIE …)이 든 것만 막아 `TELEGRAM_BOT_TOKEN`·`GITHUB_TOKEN`·
`UNSPLASH_ACCESS_KEY` 같은 이름도 통과했다(감사 탐침 probe_registry). 지금은 이름에 `GEMINI` 가 든 대문자 이름이거나, 여러 블로그가 같이 쓰는 LLM 키로 `shared_secrets` 에 적힌 이름(다른 블로그가 llm_api_key 가 아닌
역할로 쓰는 이름은 제외)만 통과한다. 레지스트리의 값은 바꾸지 않는다(검증 코드만). 이 시험은 임시 레지스트리(실제 파일을 건드리지 않음)에서 돈다. 가짜 값만 쓴다.
"""
import copy
import tempfile
import unittest

import _bootstrap  # noqa: F401
from package_helpers import REAL, entry_of, make_package_root, registry_of
from pipeline import registry

FRAGMENT = "Gemini 키 이름이 아닙니다"


class RegistryCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_package_root(tmp.name)
        self.reg = registry_of(self.root)

    def errors(self, mutate=None):
        reg = copy.deepcopy(self.reg)
        if mutate:
            mutate(reg)
        return registry.validate_registry(reg, self.root)

    def llm_errors(self, name, platform="tistory", shared=(), also=()):
        """package 채널 항목의 llm_api_key 를 name 으로 바꾼 레지스트리의 오류. shared 는 shared_secrets 에 더할 이름, also 는 같은 이름을 쓰게 할 다른 package 항목의 플랫폼."""
        def mutate(reg):
            entry_of(reg, f"{platform}_test")["secrets"]["llm_api_key"] = name
            for other in also:
                entry_of(reg, f"{other}_test")["secrets"]["llm_api_key"] = name
            reg["shared_secrets"] = list(reg.get("shared_secrets", [])) + list(shared)
        return self.errors(mutate)

    def has(self, errors, fragment):
        return any(fragment in error for error in errors)


class RefusedNamesTest(RegistryCase):
    def test_the_names_the_audit_probe_used_are_refused_on_both_channels(self):
        for platform in ("tistory", "naver"):
            for name in ("TELEGRAM_BOT_TOKEN", "GITHUB_TOKEN", "UNSPLASH_ACCESS_KEY", "BLOGGER_REFRESH_TOKEN"):
                with self.subTest(platform=platform, name=name):
                    errors = self.llm_errors(name, platform)
                    self.assertTrue(self.has(errors, FRAGMENT), errors)
                    self.assertTrue(self.has(errors, f"이름 {name}은(는)"), errors)

    def test_other_names_that_are_not_gemini_keys_are_refused(self):
        for name in ("TELEGRAM_CHAT_ID", "GH_TOKEN", "OPENAI_API_KEY", "NAVER_LLM_API_KEY", "LLM_API_KEY", "API_KEY", "UNIQUE_LLM_KEY", "BLOGGER_BLOG_ID", "TOKEN_X", "GEMIN_API_KEY", "GEMNI_KEY"):
            with self.subTest(name=name):
                self.assertTrue(self.has(self.llm_errors(name), FRAGMENT), name)

    def test_the_message_says_what_to_do(self):
        message = next(error for error in self.llm_errors("TELEGRAM_BOT_TOKEN") if FRAGMENT in error)
        for word in ("secrets.llm_api_key", "구글에 전송", "GEMINI", "shared_secrets", "운영자가 정합니다", "블로그 'tistory_test'"):
            self.assertIn(word, message)

    def test_a_trailing_newline_is_not_part_of_a_gemini_name(self):
        """환경변수 이름 검사(`$`)는 끝의 개행을 봐준다 — Gemini 이름 검사는 이름 전체가 맞아야 한다(fullmatch)."""
        errors = self.llm_errors("GEMINI_API_KEY" + chr(10), shared=())
        self.assertTrue(self.has(errors, FRAGMENT), errors)

    def test_a_name_that_is_not_a_valid_environment_name_gets_only_the_older_error(self):
        errors = self.llm_errors("gemini_api_key")
        self.assertTrue(self.has(errors, "올바른 환경변수 이름이 아닙니다"), errors)
        self.assertFalse(self.has(errors, FRAGMENT), errors)                   # 같은 원인으로 오류를 두 번 내지 않는다


class AllowedNamesTest(RegistryCase):
    def test_names_with_gemini_in_them_are_accepted(self):
        for platform in ("tistory", "naver"):
            for name in ("GEMINI_API_KEY", "TISTORY_GEMINI_KEY", "MY_GEMINI", "GEMINI", "GEMINI2", "X_GEMINI_Y_1", "NAVER_GEMINI_KEY"):
                with self.subTest(platform=platform, name=name):
                    self.assertEqual(self.llm_errors(name, platform), [])

    def test_a_shared_name_is_accepted_when_no_other_role_uses_it(self):
        """여러 블로그가 같이 쓰는 LLM 키로 shared_secrets 에 적힌 이름 — 두 package 블로그가 같은 이름을 llm_api_key 로 쓰는 것은 괜찮다."""
        self.assertEqual(self.llm_errors("SHARED_LLM_KEY", "tistory", shared=("SHARED_LLM_KEY",), also=("naver",)), [])
        self.assertEqual(self.llm_errors("SHARED_LLM_KEY", "naver", shared=("SHARED_LLM_KEY",)), [])

    def test_a_shared_name_that_another_blog_uses_for_a_different_role_is_refused(self):
        errors = self.llm_errors("UNSPLASH_ACCESS_KEY", shared=("UNSPLASH_ACCESS_KEY",))
        self.assertTrue(self.has(errors, FRAGMENT), errors)
        # 다른 블로그가 llm_api_key 가 아닌 다른 역할로 쓰는 이름이면 shared_secrets 에 있어도 LLM 키가 아니다
        def mutate(reg):
            entry_of(reg, "tistory_test")["secrets"]["llm_api_key"] = "SHARED_LLM_KEY"
            entry_of(reg, "blogger_macat")["secrets"]["unsplash_key"] = "SHARED_LLM_KEY"
            reg["shared_secrets"] = list(reg["shared_secrets"]) + ["SHARED_LLM_KEY"]
        self.assertTrue(self.has(self.errors(mutate), FRAGMENT))

    def test_a_role_that_a_blog_inherits_from_defaults_counts_as_another_role(self):
        """검증자 Q 의 N1(Q40): 이름이 쓰이는 역할은 defaults 를 합친 항목에서 모은다 — defaults 가 모든 블로그에 준 역할(예: unsplash_key)도 '다른 역할' 이다."""
        def mutate(reg):
            entry_of(reg, "tistory_test")["secrets"]["llm_api_key"] = "SHARED_LLM_KEY"
            reg["shared_secrets"] = list(reg["shared_secrets"]) + ["SHARED_LLM_KEY"]
            reg.setdefault("defaults", {}).setdefault("secrets", {})["unsplash_key"] = "SHARED_LLM_KEY"
        self.assertTrue(self.has(self.errors(mutate), FRAGMENT))

    def test_a_name_that_is_neither_gemini_nor_shared_is_refused_even_when_it_is_unique(self):
        self.assertTrue(self.has(self.llm_errors("UNIQUE_LLM_KEY"), FRAGMENT))
        self.assertEqual(self.llm_errors("UNIQUE_LLM_KEY", shared=("UNIQUE_LLM_KEY",)), [])      # shared_secrets 에 적으면(운영자 결정) 통과한다


class UnchangedBehaviourTest(RegistryCase):
    def test_the_real_registry_passes_the_rule(self):
        """실제 레지스트리가 이름 규칙을 통과한다(회귀 0)만 지킨다 — 현재 값 목록은 못박지 않는다(검증자 Q 의 R1): 운영자가 합법적으로 이름을 바꾸거나 package 블로그를 더해도 규칙을 지키면 초록이다.
        규칙의 거절 시험은 위의 임시 레지스트리(시험 안의 가짜 값)가 맡는다."""
        real = registry.load_registry()
        self.assertEqual(registry.validate_registry(real), [])
        package = [blog for blog in real["blogs"] if blog["platform"] in registry.PACKAGE_PLATFORMS]
        self.assertTrue(package)

    def test_the_temporary_registry_fixtures_are_valid(self):
        self.assertEqual(self.errors(), [])

    def test_the_rule_is_limited_to_the_package_channels(self):
        """Blogger·jekyll-git 항목의 llm_api_key 이름은 이 규칙의 대상이 아니다(옛 동작 그대로)."""
        def mutate(reg):
            entry_of(reg, "blogger_macat")["secrets"]["llm_api_key"] = "MACAT_LLM_KEY"
            entry_of(reg, "chance")["secrets"]["llm_api_key"] = "CHANCE_LLM_KEY"
        self.assertFalse(self.has(self.errors(mutate), FRAGMENT))

    def test_the_older_rules_still_work_next_to_the_new_one(self):
        def extra_role(reg):
            entry_of(reg, "tistory_test")["secrets"]["blog_id"] = "X_BLOG_ID"
        self.assertTrue(self.has(self.errors(extra_role), "허용되지 않는 역할: blog_id"))
        errors = self.llm_errors("GEMINI_PASSWD")
        self.assertTrue(self.has(errors, "계정 정보를 뜻하는 낱말(PASSWD)"), errors)
        self.assertFalse(self.has(errors, FRAGMENT), errors)                    # GEMINI 가 든 이름이라 새 규칙에는 걸리지 않는다(계정 낱말 규칙이 따로 막는다)
        self.assertTrue(self.has(self.errors(lambda reg: entry_of(reg, "tistory_test")["secrets"].clear()), "필요한 secrets 역할 누락: llm_api_key"))

    def test_validation_does_not_change_the_registry_and_survives_malformed_entries(self):
        reg = copy.deepcopy(self.reg)
        before = copy.deepcopy(reg)
        registry.validate_registry(reg, self.root)
        self.assertEqual(reg, before)
        for label, mutate in (("non-dict blog", lambda r: r["blogs"].append("not a blog")),
                              ("secrets list", lambda r: entry_of(r, "naver_test").__setitem__("secrets", ["x"])),
                              ("unhashable name", lambda r: entry_of(r, "naver_test")["secrets"].__setitem__("llm_api_key", ["GEMINI_API_KEY"])),
                              ("number name", lambda r: entry_of(r, "naver_test")["secrets"].__setitem__("llm_api_key", 7)),
                              ("no secrets", lambda r: entry_of(r, "naver_test").pop("secrets"))):
            with self.subTest(label=label):
                self.assertTrue(self.errors(mutate))                            # 예외 없이 오류 목록을 돌려준다

    def test_the_constants_and_function_are_the_documented_ones(self):
        self.assertEqual(registry._GEMINI_NAME_RE.pattern, "[A-Z0-9_]*GEMINI[A-Z0-9_]*")
        self.assertTrue(registry._llm_key_name_ok("GEMINI_API_KEY", set(), {}))
        self.assertFalse(registry._llm_key_name_ok("TELEGRAM_BOT_TOKEN", set(), {}))
        self.assertTrue(registry._llm_key_name_ok("SHARED", {"SHARED"}, {"SHARED": {"llm_api_key"}}))
        self.assertFalse(registry._llm_key_name_ok("SHARED", {"SHARED"}, {"SHARED": {"llm_api_key", "unsplash_key"}}))
        self.assertFalse(registry._llm_key_name_ok("SHARED", set(), {"SHARED": {"llm_api_key"}}))


if __name__ == "__main__":
    unittest.main()
