import copy
import json
import unittest

import _bootstrap  # noqa: F401
from pipeline import registry


def real_registry():
    return registry.load_registry()


class RealRegistryTest(unittest.TestCase):
    def test_real_registry_is_valid(self):
        self.assertEqual(registry.validate_registry(real_registry()), [])

    def test_defaults_are_merged(self):
        blog = registry.get_blog(real_registry(), "blogger_macat")
        self.assertEqual(blog["llm"]["max_retries"], 2)            # defaults 에서 상속
        self.assertEqual(blog["limits"]["max_posts_per_day"], 1)   # 블로그 값이 우선
        self.assertEqual(registry.get_blog(real_registry(), "chance")["limits"]["max_posts_per_day"], 2)

    def test_unknown_blog_raises(self):
        with self.assertRaises(registry.RegistryError):
            registry.get_blog(real_registry(), "nope")

    def test_enabled_blogs_skips_off(self):
        reg = real_registry()
        reg["blogs"][1]["mode"] = "off"
        keys = [b["key"] for b in registry.enabled_blogs(reg)]
        self.assertEqual(keys, ["chance"])
        self.assertEqual([b["key"] for b in registry.enabled_blogs(real_registry(), "blogger")], ["blogger_macat"])

    def test_missing_secret_roles(self):
        blog = registry.get_blog(real_registry(), "blogger_macat")
        self.assertEqual(set(registry.missing_secret_roles(blog, {})),
                         {"llm_api_key", "blog_id", "client_id", "client_secret", "refresh_token"})
        env = {"GEMINI_API_KEY": "a", "BLOGGER_BLOG_ID": "1", "BLOGGER_CLIENT_ID": "b",
               "BLOGGER_CLIENT_SECRET": " c ", "BLOGGER_REFRESH_TOKEN": "d"}
        self.assertEqual(registry.missing_secret_roles(blog, env), [])
        self.assertEqual(registry.resolve_secrets(blog, env)["client_secret"], "c")  # 공백 제거

    def test_role_based_override_wins_but_blank_override_falls_back(self):
        blog = registry.get_blog(real_registry(), "blogger_macat")
        env = {"BLOGGER_BLOG_ID": "named", "PIPELINE_SECRET_BLOG_ID": "override",
               "BLOGGER_CLIENT_ID": "named-cid", "PIPELINE_SECRET_CLIENT_ID": "   "}
        values = registry.resolve_secrets(blog, env)
        self.assertEqual(values["blog_id"], "override")      # 매트릭스가 넘긴 값 우선
        self.assertEqual(values["client_id"], "named-cid")   # 빈 값이면 레지스트리 이름으로 폴백


class InvalidRegistryTest(unittest.TestCase):
    def errors(self, mutate):
        reg = copy.deepcopy(real_registry())
        mutate(reg)
        return registry.validate_registry(reg)

    def assertHas(self, errors, fragment):
        self.assertTrue(any(fragment in e for e in errors), f"{fragment!r} 가 {errors} 에 없음")

    def test_duplicate_key(self):
        self.assertHas(self.errors(lambda r: r["blogs"][1].update(key="chance")), "중복")

    def test_bad_key(self):
        self.assertHas(self.errors(lambda r: r["blogs"][0].update(key="Bad-Key")), "key는")

    def test_unknown_platform(self):
        self.assertHas(self.errors(lambda r: r["blogs"][0].update(platform="tumblr")), "지원하지 않는 platform")

    def test_bad_mode(self):
        self.assertHas(self.errors(lambda r: r["blogs"][0].update(mode="yolo")), "mode는")

    def test_http_url(self):
        self.assertHas(self.errors(lambda r: r["blogs"][0].update(url="http://x.example")), "https://")

    def test_missing_required_secret_role(self):
        self.assertHas(self.errors(lambda r: r["blogs"][1]["secrets"].pop("refresh_token")), "refresh_token")

    def test_secret_name_collision_without_shared(self):
        def mutate(r):
            r["blogs"][0]["secrets"]["unsplash_key"] = "BLOGGER_BLOG_ID"
        self.assertHas(self.errors(mutate), "고유 이름")

    def test_shared_secret_is_allowed(self):
        # GEMINI_API_KEY 는 shared_secrets 에 있어 두 블로그가 함께 써도 된다
        self.assertEqual(self.errors(lambda r: None), [])

    def test_bad_env_name(self):
        self.assertHas(self.errors(lambda r: r["blogs"][1]["secrets"].update(blog_id="lower-case")), "환경변수 이름")

    def test_absolute_and_parent_paths_rejected(self):
        self.assertHas(self.errors(lambda r: r["blogs"][0].update(workflow="/etc/passwd")), "경로가 올바르지 않습니다")
        self.assertHas(self.errors(lambda r: r["blogs"][0].update(prompt="../x.md")), "경로가 올바르지 않습니다")
        self.assertHas(self.errors(lambda r: r["blogs"][0]["state"].update(history="C:/x.json")), "state.history")

    def test_blogger_requires_profile(self):
        self.assertHas(self.errors(lambda r: r["blogs"][1].update(profile=None)), "profile 이 필요")

    def test_missing_file(self):
        self.assertHas(self.errors(lambda r: r["blogs"][0].update(entrypoint="nope.py")), "파일이 없습니다")

    def test_bad_cron(self):
        self.assertHas(self.errors(lambda r: r["blogs"][0]["schedule"].update(cron="every day")), "cron")

    def test_limits_out_of_range(self):
        self.assertHas(self.errors(lambda r: r["blogs"][1]["limits"].update(max_posts_per_day=99)), "max_posts_per_day")

    def test_ad_surface_requires_protected_paths(self):
        self.assertHas(self.errors(lambda r: r["blogs"][0].update(protected_paths=[])), "protected_paths")

    def test_empty_blogs(self):
        self.assertHas(registry.validate_registry({"schema_version": 1, "blogs": []}), "blogs는")

    def test_wrong_schema_version(self):
        self.assertHas(self.errors(lambda r: r.update(schema_version=2)), "schema_version")


class ProfileTest(unittest.TestCase):
    def test_real_profile_valid(self):
        profile = registry.load_profile("blogger_practical_ko")
        self.assertEqual(registry.validate_profile(profile), [])

    def test_bad_regex_detected(self):
        profile = copy.deepcopy(registry.load_profile("blogger_practical_ko"))
        profile["banned_patterns"].append("([unclosed")
        self.assertTrue(any("정규식 오류" in e for e in registry.validate_profile(profile)))

    def test_missing_field_detected(self):
        profile = copy.deepcopy(registry.load_profile("blogger_practical_ko"))
        del profile["disclosure_html"]
        self.assertTrue(any("disclosure_html" in e for e in registry.validate_profile(profile)))

    def test_missing_profile_file(self):
        with self.assertRaises(registry.RegistryError):
            registry.load_profile("does_not_exist")


if __name__ == "__main__":
    unittest.main()
