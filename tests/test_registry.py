import copy
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from pipeline import registry
from test_run import make_root


def real_registry():
    return registry.load_registry()


class RealRegistryTest(unittest.TestCase):
    def test_real_registry_is_valid(self):
        self.assertEqual(registry.validate_registry(real_registry()), [])

    def test_every_blog_declares_its_channel_and_ads(self):
        """채널(워크플로 이름 접두사와 같은 라벨)과 광고 선언(D6, 2026-10-27 운영자 승인). 바꾸려면 이 표와 문서를 함께 고친다 —
        ads 를 pending_gate·on 으로 올리는 것은 T3(사용자 승인)다."""
        reg = real_registry()
        self.assertEqual({b["key"]: b["channel"] for b in reg["blogs"]},
                         {"chance": {"key": "chance", "label": "Chance"}, "blogger_macat": {"key": "blogger_en", "label": "Blogger 영문"},
                          "blogger_kcyoon": {"key": "blogger_ko", "label": "Blogger 한글"},
                          "tistory_it_tips": {"key": "tistory", "label": "티스토리"}, "naver_life_tips": {"key": "naver", "label": "네이버"}})   # 초안 패키지 채널은 platform 마다 자기 라벨 하나
        self.assertEqual({b["key"]: registry.get_blog(reg, b["key"])["ads"] for b in reg["blogs"]},
                         {"chance": "on", "blogger_macat": "off", "blogger_kcyoon": "off", "tistory_it_tips": "off", "naver_life_tips": "off"})     # 지금 사실: Chance 홈에는 광고 스크립트가 있고 Blogger 둘·티스토리·네이버에는 켜지 않았다(새 채널은 광고 없이 시작)
        self.assertEqual({b["key"]: registry.get_blog(reg, b["key"])["ad_surface"] for b in reg["blogs"]},
                         {"chance": True, "blogger_macat": False, "blogger_kcyoon": False, "tistory_it_tips": False, "naver_life_tips": False})      # 광고 표면(AdSense 심사 대상)은 Chance 만이다
        self.assertEqual(reg["defaults"]["ads"], "off")                # 새 채널은 광고 없이 시작한다
        self.assertEqual(registry.ADS_STATES, ("off", "pending_gate", "on"))
        # 영문·한글로 나누기 전의 임시 라벨 `Blogger` 는 없앴다(채널 라벨 5종 + 워크플로 구분 공통·내부)
        self.assertEqual(registry.CHANNEL_LABELS, ("Chance", "Blogger 영문", "Blogger 한글", "티스토리", "네이버"))

    def test_defaults_are_merged(self):
        blog = registry.get_blog(real_registry(), "blogger_macat")
        self.assertEqual(blog["llm"]["max_retries"], 2)            # defaults 에서 상속
        self.assertEqual(blog["limits"]["max_posts_per_day"], 1)   # 블로그 값이 우선
        self.assertEqual(registry.get_blog(real_registry(), "chance")["limits"]["max_posts_per_day"], 2)

    def test_defaults_mode_is_draft_so_a_blog_without_its_own_mode_never_publishes_by_itself(self):
        # 2026-10-25 20:26 에 auto 로 바뀌었던 것을 2026-10-26 운영자 답변으로 draft 로 되돌렸다. mode 없이 추가한 새 블로그가 곧바로 자동 게시되지 않게 한다.
        self.assertEqual(real_registry()["defaults"]["mode"], "draft")
        self.assertEqual({b["key"]: b.get("mode") for b in real_registry()["blogs"]},
                         {"chance": "auto", "blogger_macat": "draft", "blogger_kcyoon": "draft",         # 영문·한글 모두 2026-10-28 운영자 승인으로 draft
                          "tistory_it_tips": "package", "naver_life_tips": "package"})                   # 초안 패키지(GitHub 이슈로 보여 주기만 한다 — 공개되지 않는 mode)

    def test_model_chain_has_no_retired_model_and_matches_the_engine(self):
        import generator
        models = real_registry()["defaults"]["llm"]["models"]
        self.assertEqual(models, ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"])
        self.assertNotIn("gemini-3.7-flash", models)  # 2026-10-08 폐기, 요청이 3.8로 전달돼 같은 모델을 두 번 부르게 된다
        self.assertEqual(list(generator.MODEL_CANDIDATES), models)  # 두 목록은 한 곳처럼 같이 바뀐다(REG-4)

    def test_unknown_blog_raises(self):
        with self.assertRaises(registry.RegistryError):
            registry.get_blog(real_registry(), "nope")

    def test_enabled_blogs_skips_off(self):
        reg = real_registry()
        reg["blogs"][1]["mode"] = "off"
        keys = [b["key"] for b in registry.enabled_blogs(reg)]
        self.assertEqual(keys, ["chance", "blogger_kcyoon", "tistory_it_tips", "naver_life_tips"])     # 한글은 draft(2026-10-28 승인)라 켜져 있고, 초안 패키지 채널(package)도 off 가 아니라 켜져 있다
        reg["blogs"][2]["mode"] = "off"
        self.assertEqual([b["key"] for b in registry.enabled_blogs(reg)], ["chance", "tistory_it_tips", "naver_life_tips"])
        for blog in reg["blogs"][3:]:
            blog["mode"] = "off"                                  # 티스토리·네이버도 off 로 정지할 수 있다(package ↔ off)
        self.assertEqual([b["key"] for b in registry.enabled_blogs(reg)], ["chance"])
        reg = real_registry()
        for blog in reg["blogs"]:
            blog["mode"] = "auto"  # 운영 중 일시 정지(mode off)와 무관하게 platform 필터만 본다
        self.assertEqual([b["key"] for b in registry.enabled_blogs(reg, "blogger")], ["blogger_macat", "blogger_kcyoon"])

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

    def test_every_blog_must_write_its_own_mode(self):
        """defaults.mode 에 기대면 새 블로그가 곧바로 auto 로 글을 올릴 수 있다 — 항목마다 mode 를 직접 적게 한다."""
        for index in (0, 1):
            errors = self.errors(lambda r, i=index: r["blogs"][i].pop("mode"))
            self.assertHas(errors, "mode")
            self.assertHas(errors, "직접")

    def test_a_missing_mode_is_reported_whatever_the_default_is(self):
        """기본값이 무엇이든(off·draft·auto) 빠진 mode 는 오류다. 기본값이 바뀌어도 판정이 같아야 한다."""
        for default in ("off", "draft", "auto"):
            def mutate(r, d=default):
                r["defaults"]["mode"] = d
                r["blogs"][1].pop("mode")
            self.assertHas(self.errors(mutate), "직접")

    def test_the_default_mode_value_itself_is_not_judged(self):
        """운영자가 defaults.mode 를 바꿔도(예: draft -> auto) 블로그가 mode 를 직접 적었다면 통과한다."""
        for default in ("off", "draft", "auto"):
            self.assertEqual(self.errors(lambda r, d=default: r["defaults"].update(mode=d)), [], default)

    def test_the_message_names_the_blog_so_the_operator_knows_which_entry_to_fix(self):
        errors = self.errors(lambda r: r["blogs"][1].pop("mode"))
        self.assertTrue(any("blogger_macat" in e and "직접" in e for e in errors), errors)

    def test_every_current_blog_writes_its_mode_in_the_file(self):
        """실제 파일의 모든 항목(Chance·Blogger 둘·티스토리·네이버)이 mode 를 직접 적고 있고, 그 값이 지금 사실과 같다."""
        raw = registry.load_registry()["blogs"]
        self.assertEqual({b["key"]: b["mode"] for b in raw},
                         {"chance": "auto", "blogger_macat": "draft", "blogger_kcyoon": "draft", "tistory_it_tips": "package", "naver_life_tips": "package"})

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

    # ---- channel: 필수·모양 / 허용 라벨 / 중복 없음 / 워크플로 name 접두사 ----
    def test_channel_is_required_and_must_be_written_in_the_entry(self):
        for index in (0, 1):
            errors = self.errors(lambda r, i=index: r["blogs"][i].pop("channel"))
            self.assertHas(errors, "channel이 필요합니다")
            self.assertHas(errors, "허용 라벨")
        def inherit(r):
            r["defaults"]["channel"] = {"key": "inherited", "label": "Chance"}   # defaults 에 두어도 항목이 직접 적은 것이 아니다
            r["blogs"][0].pop("channel")
        self.assertHas(self.errors(inherit), "channel이 필요합니다")

    def test_channel_must_be_an_object(self):
        for bad in (None, "Chance", ["Chance"], 3, True):
            self.assertHas(self.errors(lambda r, b=bad: r["blogs"][0].update(channel=b)), "channel이 필요합니다")

    def test_channel_key_must_have_the_registry_key_shape(self):
        for key in (None, "", "A", "Bad-Key", "1abc", "x" * 40, 7, ["chance"]):
            self.assertHas(self.errors(lambda r, k=key: r["blogs"][0]["channel"].update(key=k)), "channel.key는")
        self.assertHas(self.errors(lambda r: r["blogs"][0]["channel"].pop("key")), "channel.key는")
        for key in ("ab", "blogger_zz", "x" + "y" * 30):
            self.assertEqual(self.errors(lambda r, k=key: r["blogs"][0]["channel"].update(key=k)), [], key)

    def test_channel_label_must_be_one_of_the_allowed_labels(self):
        for label in (None, "", "chance", "Blogger EN", "공통", "내부", "Chance ", " Chance", ["Chance"], 3):
            self.assertHas(self.errors(lambda r, l=label: r["blogs"][0]["channel"].update(label=l)), "channel.label은")
        self.assertHas(self.errors(lambda r: r["blogs"][0]["channel"].pop("label")), "channel.label은")
        errors = self.errors(lambda r: r["blogs"][0]["channel"].update(label="공통"))
        for label in registry.CHANNEL_LABELS:
            self.assertHas(errors, label)                                       # 허용 목록을 보여 준다

    def test_a_channel_label_or_key_cannot_be_shared_between_blogs(self):
        errors = self.errors(lambda r: r["blogs"][1]["channel"].update(label="Chance"))
        self.assertHas(errors, "channel.label이 다른 블로그('chance')와 같습니다")
        self.assertHas(errors, "blogger_macat")
        errors = self.errors(lambda r: r["blogs"][1]["channel"].update(key="chance"))
        self.assertHas(errors, "channel.key가 다른 블로그('chance')와 같습니다")

    def test_the_workflow_name_must_start_with_the_channel_label(self):
        errors = self.errors(lambda r: r["blogs"][0]["channel"].update(label="Blogger 영문"))   # chanceblog.yml 의 name 은 [Chance] 로 시작한다
        self.assertHas(errors, "chanceblog.yml")
        self.assertHas(errors, '"[Blogger 영문] 이름"')
        for label in ("티스토리", "네이버", "Blogger 한글"):                     # 영문 블로그의 워크플로(blogger-en.yml)는 `[Blogger 영문]` 으로 시작하므로 다른 라벨은 모두 어긋난다
            self.assertHas(self.errors(lambda r, l=label: r["blogs"][1]["channel"].update(label=l)), "blogger-en.yml")
        self.assertHas(self.errors(lambda r: r["blogs"][2]["channel"].update(label="Blogger 영문")), "blogger-ko.yml")

    def test_a_missing_workflow_file_is_reported_once_without_a_name_complaint(self):
        errors = self.errors(lambda r: r["blogs"][0].update(workflow=".github/workflows/nope.yml"))
        self.assertHas(errors, "파일이 없습니다")
        self.assertFalse(any("name" in e and "nope.yml" in e for e in errors), errors)

    # ---- ads: 값·플랫폼 규칙·defaults ----
    def test_ads_must_be_one_of_the_three_states(self):
        for bad in ("ON", "yes", True, None, "", "pending", ["on"]):
            self.assertHas(self.errors(lambda r, b=bad: r["blogs"][0].update(ads=b)), "ads는 off · pending_gate · on 중 하나")
        for ads in registry.ADS_STATES:
            self.assertEqual(self.errors(lambda r, a=ads: r["blogs"][0].update(ads=a)), [], ads)   # chance(jekyll-git)는 세 값 모두 구조상 허용

    def test_on_is_only_for_jekyll_git(self):
        errors = self.errors(lambda r: r["blogs"][1].update(ads="on"))
        self.assertHas(errors, "ads를 on으로 둘 수 없습니다")
        self.assertHas(errors, "blogger_macat")
        for ads in ("off", "pending_gate"):
            self.assertEqual(self.errors(lambda r, a=ads: r["blogs"][1].update(ads=a)), [], ads)
        # jekyll-git 만 on 이 된다 — 모르는 platform 값도 마찬가지다(블로그 플랫폼 목록에 기대지 않는다)
        errors = self.errors(lambda r: r["blogs"][1].update(platform="tumblr", ads="on"))
        self.assertHas(errors, "platform 'tumblr' 블로그는 ads를 on으로 둘 수 없습니다")

    def test_ad_surface_is_only_for_jekyll_git(self):
        errors = self.errors(lambda r: r["blogs"][1].update(ad_surface=True, protected_paths=["index.html"]))
        self.assertHas(errors, "ad_surface=true는 platform jekyll-git")
        errors = self.errors(lambda r: r["blogs"][1].update(platform="tumblr", ad_surface=True, protected_paths=["index.html"]))
        self.assertHas(errors, "ad_surface=true는 platform jekyll-git")        # 모르는 platform 값도 jekyll-git 이 아니다
        self.assertEqual(self.errors(lambda r: r["blogs"][1].update(ad_surface=False, protected_paths=["index.html"])), [])

    def test_a_blog_that_omits_ads_inherits_off(self):
        reg = copy.deepcopy(real_registry())
        del reg["blogs"][1]["ads"]
        self.assertEqual(registry.get_blog(reg, "blogger_macat")["ads"], "off")
        self.assertEqual(registry.validate_registry(reg), [])

    def test_defaults_ads_must_be_off(self):
        """ads 를 적지 않은 새 블로그가 광고를 켠(또는 켜려는) 상태로 시작하지 않게 defaults.ads 는 off 로 고정한다."""
        for value in ("pending_gate", "on", None, "OFF", ""):
            self.assertHas(self.errors(lambda r, v=value: r["defaults"].update(ads=v)), "defaults.ads는 off여야 합니다")
        self.assertHas(self.errors(lambda r: r["defaults"].pop("ads")), "defaults.ads는 off여야 합니다")
        self.assertHas(self.errors(lambda r: r["defaults"].pop("ads")), "G-C10")


class WorkflowNameLineTest(unittest.TestCase):
    """channel.label ↔ 워크플로 name 접두사(④): registry.py 는 표준 라이브러리만 쓰므로 YAML 을 해석하지 않고 최상위 `name:` 줄을 읽는다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_root(Path(tmp.name))
        self.reg = registry.load_registry(self.root / "pipeline" / "blogs.json")

    def check(self, content, as_bytes=False):
        path = self.root / ".github" / "workflows" / "blogger-en.yml"
        path.write_bytes(content if as_bytes else content.encode("utf-8"))
        return [e for e in registry.validate_registry(self.reg, self.root) if "blogger_macat" in e]

    def test_accepted_shapes(self):
        for text in ('name: "[Blogger 영문] 글 자동 작성"\non: push\n',
                     "name: '[Blogger 영문] 글 자동 작성'\non: push\n",
                     'name: "[Blogger 영문] 글" # 주석\n',
                     'name:   "[Blogger 영문] 글"   \n',
                     'name :"[Blogger 영문] 글"\n',
                     '# 머리 주석\n# name: 가짜\n\nname: "[Blogger 영문] 글"\non: push\n',
                     'name: "[Blogger 영문] 글"\r\non: push\r\n',
                     "\ufeff" + 'name: "[Blogger 영문] 글"\n',
                     'on: push\nname: "[Blogger 영문] 글"\n'):
            self.assertEqual(self.check(text), [], text)

    def test_rejected_shapes(self):
        for text, hint in (("name: [Blogger 영문] 글 자동 작성\n", "[Blogger 영문] 글 자동 작성"),    # 따옴표 없는 대괄호 값은 YAML 문법 오류다
                           ('name: "[Chance] 글"\n', "[Chance] 글"),
                           ('name: "[blogger 영문] 글"\n', "[blogger 영문] 글"),
                           ('name: "[Blogger 영문]글"\n', "[Blogger 영문]글"),
                           ('name: "[Blogger 영문] "\n', "[Blogger 영문] "),
                           ('name: "[Blogger 영문]  글"\n', "[Blogger 영문]  글"),                  # 공백이 둘이면 접두사 뒤 이름이 공백으로 시작한다
                           ('name: "[Blogger 영문]"\n', "[Blogger 영문]"),
                           ('name: " [Blogger 영문] 글"\n', "[Blogger 영문] 글"),
                           ('name: "글 [Blogger 영문]"\n', "글 [Blogger 영문]"),
                           ("name: 글 자동 작성\n", "글 자동 작성"),
                           ("name:\n", "name:"),
                           ('name: ["[Blogger 영문] 글"]\n', "name:")):
            errors = self.check(text)
            self.assertEqual(len(errors), 1, text)
            self.assertIn("blogger-en.yml", errors[0], text)
            self.assertIn('"[Blogger 영문] 이름"', errors[0], text)
            self.assertIn(hint, errors[0], text)

    def test_only_the_top_level_name_counts(self):
        for text in ('on: push\njobs:\n  j:\n    name: "[Blogger 영문] 글"\n', '  name: "[Blogger 영문] 글"\n', 'x:\n  name: "[Blogger 영문] 글"\n'):
            errors = self.check(text)
            self.assertEqual(len(errors), 1, text)
            self.assertIn("찾지 못했습니다", errors[0], text)
        self.assertEqual(len(self.check("")), 1)

    def test_the_first_top_level_name_line_is_the_one_that_counts(self):
        self.assertEqual(self.check('name: "[Blogger 영문] 글"\nname: "다른 이름"\n'), [])
        self.assertEqual(len(self.check('name: "다른 이름"\nname: "[Blogger 영문] 글"\n')), 1)

    def test_an_unreadable_file_is_an_error_not_a_crash(self):
        errors = self.check('name: "[Blogger 영문] '.encode("utf-8") + b'\xff\xfe"\n', as_bytes=True)
        self.assertEqual(len(errors), 1)
        self.assertIn("읽을 수 없어", errors[0])

    def test_the_korean_wrapper_name_line_is_read_the_same_way(self):
        path = self.root / ".github" / "workflows" / "blogger-ko.yml"
        for text, ok in (('name: "[Blogger 한글] 글 자동 작성"\non: push\n', True), ('name: "[Blogger 영문] 글 자동 작성"\n', False), ('name: "[Blogger] 글 자동 작성"\n', False)):
            path.write_text(text, encoding="utf-8")
            errors = [e for e in registry.validate_registry(self.reg, self.root) if "blogger_kcyoon" in e]
            self.assertEqual(errors == [], ok, (text, errors))
            if not ok:
                self.assertIn("blogger-ko.yml", errors[0])
                self.assertIn('"[Blogger 한글] 이름"', errors[0])

    def test_name_label_helper(self):
        for name, label in (("[Chance] 글", "Chance"), ("[Blogger 영문] 글", "Blogger 영문"), ("[공통] 사이트 자동 배포", "공통"), ("[내부] 공용 실행(직접 실행하지 마세요)", "내부")):
            self.assertEqual(registry.name_label(name), label, name)
        for name in ("[Chance]글", "[Chance] ", "[Chance]  글", "[Chance]", " [Chance] 글", "[] 글", "[[Chance]] 글", "[Chance 글", "Chance] 글", "글", "", None, 7, ["[Chance] 글"]):
            self.assertIsNone(registry.name_label(name), name)


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

    def test_english_profile_valid_and_every_profile_file_is_valid(self):
        self.assertEqual(registry.validate_profile(registry.load_profile("blogger_practical_en")), [])
        for path in sorted(registry.PROFILE_DIR.glob("*.json")):
            self.assertEqual(registry.validate_profile(registry.load_profile(path.stem)), [], path.name)

    def test_unknown_language_and_empty_matching_pattern_are_reported(self):
        profile = copy.deepcopy(registry.load_profile("blogger_practical_ko"))
        profile["language"] = "ja"
        self.assertTrue(any("language" in e for e in registry.validate_profile(profile)))
        profile = copy.deepcopy(registry.load_profile("blogger_practical_ko"))
        profile["body_safe_patterns"].append("전문가|")
        self.assertTrue(any("빈 문자열" in e for e in registry.validate_profile(profile)))


if __name__ == "__main__":
    unittest.main()
