"""초안 패키지 채널(mode package, platform tistory·naver)의 레지스트리 규칙 시험.

실제 `pipeline/blogs.json` 에는 티스토리·네이버 항목이 없다(블로그 주소·주제를 받기 전 — 대상 0개). 그래서 임시 레지스트리에 시험용 항목을 더해
검증 경로(새 모드·플랫폼·금지 시크릿 역할·허용 조합)와 매트릭스·검증기가 이 항목을 올바르게 다루는지 증명한다.
"""
import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import _bootstrap  # noqa: F401
from package_helpers import REAL, entry_of, make_package_root, registry_of, with_entry
from pipeline import plan, registry

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402


class PackageRegistryBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_package_root(tmp.name)
        self.reg = registry_of(self.root)

    def errors(self, mutate=None, root=None):
        reg = copy.deepcopy(self.reg)
        if mutate:
            mutate(reg)
        return registry.validate_registry(reg, root or self.root)

    def assertHas(self, errors, fragment):
        self.assertTrue(any(fragment in e for e in errors), f"{fragment!r} 가 {errors} 에 없음")

    def entry(self, platform="tistory"):
        return entry_of(self.reg, f"{platform}_test")


class NewValuesTest(PackageRegistryBase):
    def test_the_real_registry_has_no_package_blog_yet(self):
        """블로그 주소·주제(사용자 입력)를 받기 전이라 실제 레지스트리에는 티스토리·네이버가 없다 — 정기 실행은 '대상 0개'로 끝난다."""
        real = registry.load_registry()
        self.assertEqual([blog["key"] for blog in real["blogs"]], ["chance", "blogger_macat"])
        self.assertFalse({registry.merged_blog(real, blog)["platform"] for blog in real["blogs"]} & set(registry.PACKAGE_PLATFORMS))
        self.assertNotIn("package", {blog["mode"] for blog in real["blogs"]})
        self.assertEqual(registry.validate_registry(real), [])

    def test_modes_platforms_and_the_package_table(self):
        self.assertEqual(registry.MODES, ("off", "draft", "package", "auto"))
        self.assertEqual(registry.PACKAGE_MODES, ("off", "package"))
        self.assertEqual(registry.PACKAGE_PLATFORMS, {"tistory": "티스토리", "naver": "네이버"})
        for platform in ("tistory", "naver"):
            self.assertEqual(registry.PLATFORMS[platform], {"required_secrets": ["llm_api_key"], "optional_secrets": []})
        self.assertLessEqual(set(registry.PACKAGE_PLATFORMS.values()), set(registry.CHANNEL_LABELS))
        self.assertEqual(registry.ACCOUNT_SECRET_WORDS[:4], ("PASSWORD", "PASSWD", "PWD", "COOKIE"))
        self.assertTrue({"PASSWORD", "COOKIE", "SESSION", "LOGIN"} <= set(registry.ACCOUNT_SECRET_WORDS))

    def test_both_channels_pass_validation_in_package_and_off_modes(self):
        self.assertEqual(self.errors(), [])
        for mode in ("package", "off"):
            def mutate(reg, mode=mode):
                for blog in reg["blogs"][2:]:
                    blog["mode"] = mode
            self.assertEqual(self.errors(mutate), [], mode)

    def test_the_other_blogs_are_unaffected_by_the_new_platforms(self):
        errors = self.errors(lambda reg: reg["blogs"][1].update(mode="off"))
        self.assertEqual(errors, [])

    def test_the_mode_message_lists_package(self):
        errors = self.errors(lambda reg: reg["blogs"][0].update(mode="yolo"))
        self.assertHas(errors, "package")


class ModeRulesTest(PackageRegistryBase):
    def test_package_mode_is_only_for_tistory_and_naver(self):
        for index, platform in ((0, "jekyll-git"), (1, "blogger")):
            errors = self.errors(lambda reg, i=index: reg["blogs"][i].update(mode="package"))
            self.assertHas(errors, "mode package 는 platform tistory · naver 에서만")
            self.assertHas(errors, repr(platform))

    def test_a_package_channel_has_no_draft_or_auto_mode(self):
        for platform in ("tistory", "naver"):
            for mode in ("draft", "auto"):
                errors = self.errors(with_entry(lambda blog, m=mode: blog.update(mode=m), platform))
                self.assertHas(errors, f"platform {platform} 블로그의 mode는 off · package 중 하나여야 합니다")
                self.assertEqual(len([e for e in errors if "mode" in e]), 1, (platform, mode, errors))      # 같은 잘못을 두 번 알리지 않는다
            for mode in ("off", "package"):
                self.assertEqual(self.errors(with_entry(lambda blog, m=mode: blog.update(mode=m), platform)), [], (platform, mode))

    def test_an_unknown_mode_is_one_error_not_two(self):
        errors = self.errors(with_entry(lambda blog: blog.update(mode="yolo")))
        self.assertEqual(len([e for e in errors if "mode" in e]), 1, errors)

    def test_the_entry_must_write_its_own_mode(self):
        errors = self.errors(with_entry(lambda blog: blog.pop("mode")))
        self.assertHas(errors, "mode를 이 항목에 직접 적어야")

    def test_a_package_channel_needs_a_profile(self):
        for platform in ("tistory", "naver"):
            self.assertHas(self.errors(with_entry(lambda blog: blog.update(profile=None), platform)), f"platform {platform} 는 profile 이 필요합니다.")
            self.assertHas(self.errors(with_entry(lambda blog: blog.pop("profile"), platform)), f"platform {platform} 는 profile 이 필요합니다.")
        self.assertHas(self.errors(lambda reg: reg["blogs"][1].update(profile=None)), "platform blogger 는 profile 이 필요합니다.")   # Blogger 문구는 그대로다

    def test_the_profile_language_must_match_the_blog_languages(self):
        errors = self.errors(with_entry(lambda blog: blog.update(languages=["en"])))
        self.assertHas(errors, "language('ko')가 이 블로그의 languages ['en'] 에 없습니다")


class ChannelAndAdsTest(PackageRegistryBase):
    def test_the_channel_label_must_be_the_channels_own_label(self):
        for platform, wrong in (("tistory", "네이버"), ("tistory", "Blogger"), ("tistory", "Chance"), ("naver", "티스토리"), ("naver", "Blogger 한글")):
            errors = self.errors(with_entry(lambda blog, w=wrong: blog["channel"].update(label=w), platform))
            self.assertHas(errors, f"channel.label은 {registry.PACKAGE_PLATFORMS[platform]!r} 이어야 합니다")
            self.assertHas(errors, "채널:<라벨>")

    def test_the_workflow_name_prefix_must_match_the_channel_label(self):
        errors = self.errors(with_entry(lambda blog: blog.update(workflow=".github/workflows/naver.yml")))     # [네이버] 로 시작하는 파일
        self.assertHas(errors, "naver.yml")
        self.assertHas(errors, '"[티스토리] 이름"')

    def test_the_real_workflow_files_start_with_their_channel_label(self):
        for platform, label in registry.PACKAGE_PLATFORMS.items():
            text = (REAL / ".github" / "workflows" / f"{platform}.yml").read_text(encoding="utf-8")
            self.assertIsNone(registry._workflow_name_problem(text, label), platform)
            self.assertIsNotNone(registry._workflow_name_problem(text, "공통"), platform)

    def test_a_channel_label_cannot_be_used_twice(self):
        errors = self.errors(lambda reg: entry_of(reg, "naver_test")["channel"].update(label="티스토리"))
        self.assertHas(errors, "channel.label이 다른 블로그('tistory_test')와 같습니다")

    def test_new_channels_start_without_ads(self):
        for platform in ("tistory", "naver"):
            self.assertHas(self.errors(with_entry(lambda blog: blog.update(ads="on"), platform)), "ads를 on으로 둘 수 없습니다")
            self.assertEqual(self.errors(with_entry(lambda blog: blog.update(ads="pending_gate"), platform)), [])
            self.assertEqual(self.errors(with_entry(lambda blog: blog.pop("ads"), platform)), [])             # 생략하면 defaults.ads = off
            self.assertEqual(registry.get_blog(self._without_ads(platform), f"{platform}_test")["ads"], "off")
            self.assertHas(self.errors(with_entry(lambda blog: blog.update(ad_surface=True, protected_paths=["a.html"]), platform)),
                           "ad_surface=true는 platform jekyll-git")

    def _without_ads(self, platform):
        reg = copy.deepcopy(self.reg)
        entry_of(reg, f"{platform}_test").pop("ads")
        return reg


class SecretRulesTest(PackageRegistryBase):
    def test_the_only_secret_role_is_the_llm_key(self):
        for role in ("blog_id", "client_id", "client_secret", "refresh_token", "unsplash_key", "api_token", "login_id", "access_token"):
            for platform in ("tistory", "naver"):
                errors = self.errors(with_entry(lambda blog, r=role: blog["secrets"].update({r: "SOME_EXTRA_NAME"}), platform))
                self.assertHas(errors, f"허용되지 않는 역할: {role}")
                self.assertHas(errors, "계정 정보")

    def test_the_whole_blogger_secret_set_is_refused_on_these_channels(self):
        def mutate(blog):
            blog["secrets"].update({"blog_id": "X_BLOG_ID", "client_id": "X_CLIENT_ID", "client_secret": "X_CLIENT_SECRET", "refresh_token": "X_REFRESH_TOKEN"})
        errors = self.errors(with_entry(mutate))
        for role in ("blog_id", "client_id", "client_secret", "refresh_token"):
            self.assertHas(errors, f"허용되지 않는 역할: {role}")

    def test_secret_names_that_look_like_account_information_are_refused(self):
        for name, word in (("TISTORY_PASSWORD", "PASSWORD"), ("NAVER_LOGIN_KEY", "LOGIN"), ("MY_COOKIE_JAR", "COOKIE"), ("A_SESSION_ID", "SESSION"),
                           ("GEMINI_PASSWD", "PASSWD"), ("GEMINI_PWD_X", "PWD"), ("TISTORY_CREDENTIALS", "CREDENTIAL")):
            errors = self.errors(with_entry(lambda blog, n=name: blog["secrets"].update(llm_api_key=n)))
            self.assertHas(errors, f"이름 {name}에 계정 정보를 뜻하는 낱말({word})")

    def test_a_plain_gemini_key_name_is_fine_even_if_it_is_not_the_shared_one(self):
        for name in ("GEMINI_API_KEY", "TISTORY_GEMINI_KEY", "NAVER_LLM_API_KEY"):
            self.assertEqual(self.errors(with_entry(lambda blog, n=name: blog["secrets"].update(llm_api_key=n))), [], name)

    def test_the_llm_key_is_required(self):
        self.assertHas(self.errors(with_entry(lambda blog: blog["secrets"].clear())), "platform tistory에 필요한 secrets 역할 누락: llm_api_key")

    def test_a_secret_name_cannot_be_borrowed_from_another_blog_unless_shared(self):
        errors = self.errors(with_entry(lambda blog: blog["secrets"].update(llm_api_key="BLOGGER_BLOG_ID")))
        self.assertHas(errors, "고유 이름")

    def test_missing_secret_roles_asks_for_the_llm_key_only(self):
        blog = registry.get_blog(self.reg, "tistory_test")
        self.assertEqual(registry.missing_secret_roles(blog, {}), ["llm_api_key"])
        self.assertEqual(registry.missing_secret_roles(blog, {"GEMINI_API_KEY": "k"}), [])
        self.assertEqual(registry.missing_secret_roles(blog, {"PIPELINE_SECRET_LLM_API_KEY": "k"}), [])
        self.assertEqual(registry.resolve_secrets(blog, {"GEMINI_API_KEY": " k "}), {"llm_api_key": "k"})


class PlanAndEnabledTest(PackageRegistryBase):
    def test_enabled_blogs_include_package_blogs_but_not_off_ones(self):
        self.assertEqual([b["key"] for b in registry.enabled_blogs(self.reg, "tistory")], ["tistory_test"])
        self.assertEqual([b["key"] for b in registry.enabled_blogs(self.reg, "naver")], ["naver_test"])
        reg = copy.deepcopy(self.reg)
        entry_of(reg, "tistory_test")["mode"] = "off"
        self.assertEqual(registry.enabled_blogs(reg, "tistory"), [])

    def test_the_matrix_carries_secret_names_only_and_only_the_llm_role(self):
        matrix = plan.build_matrix(self.reg, "tistory")
        self.assertEqual(matrix, {"include": [{
            "key": "tistory_test", "platform": "tistory", "mode": "package", "history": "tistory_test_history.json", "content_dir": "_tistory_test_drafts",
            "secret_llm_api_key": "GEMINI_API_KEY", "secret_blog_id": "", "secret_client_id": "", "secret_client_secret": "", "secret_refresh_token": ""}]})
        self.assertEqual([i["key"] for i in plan.build_matrix(self.reg, "naver")["include"]], ["naver_test"])
        self.assertEqual(plan.build_matrix(self.reg, "blogger")["include"], [])                     # macat 은 off
        self.assertEqual([i["key"] for i in plan.build_matrix(self.reg, "tistory", only="tistory_test")["include"]], ["tistory_test"])
        self.assertEqual(plan.build_matrix(self.reg, "tistory", only="naver_test")["include"], [])

    def test_with_no_package_blog_the_matrix_is_empty_and_that_is_green_not_an_error(self):
        real = registry.load_registry()
        for platform in ("tistory", "naver"):
            self.assertEqual(plan.build_matrix(real, platform), {"include": []})
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                self.assertEqual(plan.main(["--platform", platform, "--count"]), 0)
            self.assertEqual(buffer.getvalue().strip(), "0")

    def test_the_plan_cli_rejects_a_key_of_another_platform(self):
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            self.assertEqual(plan.main(["--platform", "tistory", "--only", "chance"]), 1)
        self.assertIn("jekyll-git 플랫폼 블로그입니다", err.getvalue())


class ValidatorTest(PackageRegistryBase):
    """scripts/validate_repo.py 의 레지스트리 검사(REG-1~3)와 워크플로 검사(WF-*)가 새 항목·새 워크플로를 올바르게 다루는지."""

    def check(self, mutate=None):
        root = self.root
        if mutate:
            reg = copy.deepcopy(self.reg)
            mutate(reg)
            (root / "pipeline" / "blogs.json").write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        return vr.check_registry(root, vr.list_files(root))

    @staticmethod
    def about_package_blogs(findings):
        return [f for f in findings if f.path in (".github/workflows/tistory.yml", ".github/workflows/naver.yml")]

    def test_the_registry_check_passes_with_the_real_workflows(self):
        """임시 저장소의 chance·blogger 워크플로는 이름 한 줄짜리 스텁이라 그 블로그의 cron 불일치는 나온다 — 새 항목에 대한 지적만 본다."""
        findings = self.check()
        self.assertEqual(self.about_package_blogs(findings), [])           # cron 이 워크플로와 같고 시크릿이 매트릭스로 연결돼 있고 이름 접두사가 맞다
        self.assertEqual([f for f in findings if f.check == "REG-1"], [])

    def test_the_cron_must_equal_the_workflows_schedule(self):
        findings = self.check(with_entry(lambda blog: blog["schedule"].update(cron="0 0 * * *")))
        self.assertTrue(any(f.check == "REG-2" and "tistory_test" in f.message for f in self.about_package_blogs(findings)), findings)
        for platform, cron in (("tistory", "20 5 * * *"), ("naver", "20 6 * * *")):
            self.assertEqual(vr._workflow_crons(self.root, f".github/workflows/{platform}.yml"), [cron])
            self.assertEqual(entry_of(self.reg, f"{platform}_test")["schedule"]["cron"], cron)

    def test_the_new_workflows_pass_the_workflow_checks(self):
        files = vr.list_files(self.root)
        wf = [f for f in files if f.endswith(("tistory.yml", "naver.yml"))]
        self.assertEqual(len(wf), 2)
        for check in (vr.check_workflows, vr.check_workflow_names, vr.check_workflow_prefixes):
            self.assertEqual([f.line() for f in check(self.root, files) if f.path in wf], [], check.__name__)

    def test_the_real_repository_has_the_two_new_workflows_and_no_workflow_error(self):
        findings = vr.run_checks(REAL)
        self.assertEqual([f.line() for f in findings if f.level == "ERROR"], [])
        files = vr.list_files(REAL)
        for name in ("tistory.yml", "naver.yml"):
            self.assertIn(f".github/workflows/{name}", files)


if __name__ == "__main__":
    unittest.main()
