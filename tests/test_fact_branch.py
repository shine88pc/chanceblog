"""생성기의 구조화 Fact 분기(S2b, 레지스트리 chance.content_source: facts)의 시험 — 실제 `generate_blog_posts` 를 임시 작업 폴더에서 돌린다. 네트워크·시계·진짜 키 없음(가짜 transport·가짜 시계).

못박는 것
1. **켜기 전 안전장치**: content_source 값 모양·`facts` 인데 allowlist 아님·국문 단독 아님·승인 흐름 아님·레지스트리 오류·Provider 꺼짐(지금 저장소의 실제 상태)·strict_tier·기한·호출 한도·카드 이미지 없음·요청 주제 —
   하나라도 아니면 글을 만들지 않고 이유를 한 줄로 남기고 **정상 종료**(예외 없음·파일·이력 그대로·요청 0·피드 경로로 되돌아가지 않음)한다.
2. **만든 글**: 파일 이름·분류 폴더·머리말(출처 표식 한 줄·자체 카드 이미지 https 주소·설명·출처 세 줄)·이력 항목(자체 제목·candidate_key·dedupe_key·recipe_id·as_of·content_source·표식)·승인 흐름 항목.
3. **AI 0**: 피드·기사 발췌·모델·프롬프트·사진·이미지 검색어 함수를 한 번도 부르지 않고(부르면 시험이 실패하는 감시자) 모델 호출 횟수가 0 이다.
4. **연결 코드**(`fact_opener`): 허용 목록 관문·호출 예산 — 허용 밖 호스트·ACTIVE 가 아닌 Provider·호출 예산 소진·429/403 중지·404·실패 3회 뒤 건너뜀·같은 주소 응답 재사용·응답 깨짐.
5. **Gate 연결**: 후보 사전의 모양(아홉 키)·보류되면 다음 글감·현재 Gate 가 그 모양을 몰라도 예외 없음.
6. 기본(feed)에서는 이 분기가 한 번도 실행되지 않는다(옛 생성기와의 바이트 비교는 `test_generator_source_policy` 의 GOLDEN 이 맡는다)."""
import ast
import contextlib
import io
import json
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import fact_branch_helpers as FB
import generator as g

from pipeline import drafts, draft_flow, egress, provenance, publish_lock, quality_gate, registry, source_policy, source_registry
from pipeline import fact_candidates as K
from pipeline import fact_supply
from pipeline.adapters import noaa_swpc as N


def edit_provider(data, change):
    for item in data["providers"]:
        if item["provider_id"] == FB.PROVIDER_ID:
            change(item)
    return data


class HttpStatus(Exception):
    """urllib.error.HTTPError 대역 — 호출 예산이 읽는 것은 `code` 하나뿐이다."""

    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


class RegistryRulesTest(unittest.TestCase):
    def errors(self, **chance):
        return source_policy.content_source_errors({"content_source": "facts", **chance}, "블로그 'chance'", "jekyll-git")

    def test_the_real_registry_is_valid_and_holds_no_value_for_the_switch(self):
        reg = registry.load_registry()
        self.assertEqual(registry.validate_registry(reg), [])
        self.assertEqual(source_policy.chance_content_source(), "feed")
        self.assertNotIn("content_source", json.dumps(reg))

    def test_facts_needs_allowlist_korean_only_and_the_approval_flow(self):
        self.assertEqual(self.errors(source_policy="allowlist", languages=["ko"], publish_flow="pr"), [])
        found = self.errors()
        self.assertEqual(len(found), 3)
        for needle in ("source_policy 는 allowlist", 'languages 는 ["ko"]', "publish_flow 는 pr"):
            self.assertTrue(any(needle in line for line in found), (needle, found))
        for broken in ({"source_policy": "legacy"}, {"languages": ["ko", "en"]}, {"languages": ["en"]}, {"languages": "ko"}, {"publish_flow": "direct"}):
            good = {"source_policy": "allowlist", "languages": ["ko"], "publish_flow": "pr", **broken}
            self.assertEqual(len(self.errors(**good)), 1, broken)

    def test_the_value_must_be_feed_or_facts_and_only_on_the_jekyll_blog(self):
        self.assertEqual(source_policy.CONTENT_SOURCES, ("feed", "facts"))                       # 허용 값은 둘뿐 — 하나를 더하면 레지스트리가 모르는 값을 받게 된다
        for bad in ("Facts", "fact", "FEED", "", " facts", None, 1, True, ["facts"], {"facts": 1}, "both", "feed,facts", "none"):
            found = source_policy.content_source_errors({"content_source": bad}, "블로그 'chance'", "jekyll-git")
            self.assertEqual(len(found), 1, bad)
            self.assertIn("feed", found[0])
            self.assertIn("facts", found[0])
        self.assertEqual(source_policy.content_source_errors({"content_source": "feed"}, "x", "jekyll-git"), [])
        self.assertEqual(source_policy.content_source_errors({}, "x", "jekyll-git"), [])
        self.assertEqual(source_policy.content_source_errors({"source_policy": "legacy"}, "x", "blogger"), [])           # 값이 없으면 어느 플랫폼이든 문제 없다
        for value in ("feed", "facts"):
            found = source_policy.content_source_errors({"content_source": value}, "블로그 'x'", "blogger")
            self.assertEqual(len(found), 1)
            self.assertIn("jekyll-git", found[0])

    def test_the_registry_validator_applies_the_rules_through_the_merged_blog(self):
        good = FB.facts_registry()
        self.assertEqual(registry.validate_registry(good), [])
        for change, needle in (({"source_policy": "legacy"}, "allowlist"), ({"languages": ["ko", "en"]}, "languages"), ({"publish_flow": "direct"}, "publish_flow"), ({"content_source": "fact"}, "content_source")):
            with self.subTest(change=change):
                found = registry.validate_registry(FB.facts_registry(**change))
                self.assertTrue(any(needle in line for line in found), found)
        feed = FB.facts_registry(content_source="feed", source_policy=None, languages=["ko", "en"], publish_flow="direct")
        self.assertEqual(registry.validate_registry(feed), [])                                                       # feed 는 어떤 값과도 함께 쓸 수 있다

    def test_the_reader_is_one_function_with_a_default_and_a_registry_error_for_bad_values(self):
        self.assertEqual(source_policy.content_source_of({}), "feed")
        self.assertEqual(source_policy.content_source_of({"content_source": "facts"}), "facts")
        self.assertEqual(source_policy.content_source_of("사전이 아님"), "feed")
        for bad in ("fact", None, 1):
            with self.assertRaises(ValueError):
                source_policy.content_source_of({"content_source": bad})
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(registry, "REGISTRY_PATH", FB.write_json(Path(tmp) / "b.json", FB.facts_registry(content_source="x"))):
                with self.assertRaises(registry.RegistryError):
                    source_policy.chance_content_source()


class StartGuardTest(FB.FactEnv):
    """켜기 전 안전장치: 하나라도 아니면 글을 만들지 않고 이유를 한 줄로 남기고 정상 종료한다."""

    def assert_not_ready(self, reason=None, **kwargs):
        before = self.files()
        value, report, out, error = self.run_branch(**kwargs)
        self.assertIsNone(error, error)                                                          # 예외로 죽지 않는다
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], source_policy.FACT_NOT_READY_OUTCOME)
        self.assertEqual(self.files(), before)                                                    # 글·이력을 만들거나 바꾸지 않았다
        self.assertEqual(self.noaa.factory_calls, 0)                                              # 요청 도구를 만들지도 않았다
        self.assertEqual(self.noaa.calls, [])
        lines = [line for line in out.splitlines() if line.startswith("[구조화 Fact] 글을 만들지 않습니다")]
        self.assertEqual(len(lines), 1, out)                                                      # 이유는 한 줄
        if reason:
            self.assertIn(reason, lines[0])
        for name, spy in self.spies.items():
            spy.assert_not_called()                                                               # 피드 경로로 되돌아가지도 않았다
        return out, report

    def test_the_ready_state_makes_a_post_so_the_guard_cases_below_are_not_vacuous(self):
        value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertEqual(report["outcome"], "DRAFT_CREATED")
        self.assertEqual(len(self.posts()), 1)

    def test_the_provider_off_which_is_the_real_state_of_the_repository_makes_nothing(self):
        real_sources = json.loads((FB.ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8"))
        self.assertFalse(any(item["enabled"] for item in real_sources["providers"]))                 # 62곳 모두 꺼진 채
        self.use(FB.facts_registry(), real_sources)
        out, _report = self.assert_not_ready("ACTIVE 가 아님")
        self.assertIn(FB.PROVIDER_ID, out)

    def test_the_real_registry_files_with_only_the_switch_flipped_still_make_nothing(self):
        """켜는 값 하나(content_source·source_policy 등)를 실수로 바꿔도 Provider 가 꺼져 있는 한 새 글이 나올 수 없다 — 지금 저장소의 상태 그대로."""
        self.use(FB.facts_registry(), json.loads((FB.ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8")))
        self.assert_not_ready()
        self.use(FB.facts_registry(source_policy=None), json.loads((FB.ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8")))
        self.assert_not_ready("allowlist")

    def test_source_policy_must_be_allowlist(self):
        self.use(FB.facts_registry(source_policy="legacy"), FB.sources_registry())
        self.assert_not_ready("source_policy")
        self.use(FB.facts_registry(source_policy=None), FB.sources_registry())
        self.assert_not_ready("source_policy")

    def test_an_invalid_registry_stops_it_whatever_the_reason(self):
        for change in ({"languages": ["ko", "en"]}, {"publish_flow": "direct"}, {"ads": "maybe"}, {"mode": "weird"}):
            with self.subTest(change=change):
                self.use(FB.facts_registry(**change), FB.sources_registry())
                self.assert_not_ready("레지스트리 검증 오류")

    def test_the_file_reading_start_function_says_so_when_the_registry_cannot_be_read(self):
        problems, sources = source_policy.fact_start("2026-11-10", FB.PROVIDER_ID, registry_path=self.tmp / "없는 레지스트리.json", sources_path=self.tmp / "sources.json")
        self.assertTrue(any("레지스트리 검증 오류" in line for line in problems), problems)        # 읽지 못한 사실이 다른 조건에 묻히지 않고 문제로 남는다
        self.assertTrue(any("content_source" in line for line in problems), problems)             # 스위치 값을 몰라 시작하지 않는다는 말도 같이 나온다
        self.assertIsNotNone(sources)                                                               # 허용 목록은 따로 읽힌다

    def test_a_provider_that_is_active_but_has_no_noaa_api_path_stops_it_with_its_own_reason(self):
        with mock.patch.object(fact_supply, "api_access", lambda provider: None):
            self.assert_not_ready("NOAA api 접근 경로")

    def test_an_active_provider_is_required_in_every_way(self):
        cases = {
            "꺼짐": FB.sources_registry(enabled=False),
            "strict_tier 3": FB.sources_registry(strict_tier=3),
            "자동화 제외": FB.sources_registry(effective_status="자동화 제외"),
            "약관 점검 기한이 지남": edit_provider(FB.sources_registry(), lambda item: item["snapshot"].update(expires_at="2026-11-09")),
            "호출 한도를 모름": edit_provider(FB.sources_registry(), lambda item: item["access"][0].update(rate_limit=None)),
            "접근 경로 없음": edit_provider(FB.sources_registry(), lambda item: item.update(access=[{"kind": "rss", "hosts": ["services.swpc.noaa.gov"], "paths": ["/x"], "auth": "NONE", "rate_limit": None, "robots_checked_at": "2026-11-10"}])),
        }
        for label, data in cases.items():
            with self.subTest(case=label):
                self.use(FB.facts_registry(), data)
                self.assert_not_ready(FB.PROVIDER_ID)

    def test_a_provider_missing_from_the_list_or_an_unreadable_list_stops_it(self):
        data = FB.sources_registry()
        data["providers"] = [item for item in data["providers"] if item["provider_id"] != FB.PROVIDER_ID]
        self.use(FB.facts_registry(), data)
        self.assert_not_ready("가 없음")
        self.use(FB.facts_registry(), FB.sources_registry())
        (self.tmp / "sources.json").write_text("{깨진", encoding="utf-8")
        self.assert_not_ready("허용 목록(Registry)을 읽지 못함")

    def test_the_card_image_file_and_the_site_address_must_be_there(self):
        self.patch_value(g, "FACT_CARD_FILE", self.tmp / "없는 카드.svg")
        self.assert_not_ready("카드 이미지 파일")

    def test_an_unreadable_site_config_stops_it_before_any_request(self):
        self.patch_value(g, "FACT_CONFIG_FILE", self.tmp / "없는 설정.yml")
        self.assert_not_ready("_config.yml")
        broken = self.tmp / "설정.yml"
        broken.write_text("title: x\nurl: http://insecure.example\nbaseurl: /x\n", encoding="utf-8")
        self.patch_value(g, "FACT_CONFIG_FILE", broken)
        self.assert_not_ready("_config.yml")

    def test_a_requested_topic_is_refused_without_reading_anything(self):
        self.assert_not_ready("요청한 주제", topic_override="아무 주제")

    def test_finish_run_ends_green_with_a_notice_for_the_quiet_outcomes_and_a_warning_for_all_skipped(self):
        for outcome in source_policy.FACT_QUIET_OUTCOMES:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                g.finish_run(None, {"outcome": outcome, "lanes": []}, "schedule", self.now, 9)          # SystemExit 이 나지 않는다
            self.assertIn("::notice::", out.getvalue())
            self.assertIn(f"code={outcome}", out.getvalue())
            self.assertNotIn("::warning::", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            g.finish_run(None, {"outcome": source_policy.FACT_ALL_SKIPPED_OUTCOME, "lanes": []}, "schedule", self.now, 9)
        self.assertIn("::warning::", out.getvalue())
        for outcome in (*source_policy.FACT_QUIET_OUTCOMES, source_policy.FACT_ALL_SKIPPED_OUTCOME):
            self.assertIn(outcome, g.OUTCOME_TEXT)

    def test_the_pure_start_function_reports_each_condition(self):
        class Provider:
            enabled, strict_tier, effective_status = True, 1, "자동화 가능"

        class Sources:
            def __init__(self, active):
                self.active = active

            def get(self, pid):
                return Provider() if pid == "p" else None

            def is_active(self, pid):
                return self.active

            def inactive_reasons(self):
                return {"p": ["[A4] 기한이 지남"]}
        ok = source_policy.fact_start_problems("facts", "allowlist", [], Sources(True), "p")
        self.assertEqual(ok, [])
        self.assertEqual(len(source_policy.fact_start_problems("feed", "allowlist", [], Sources(True), "p")), 1)
        self.assertEqual(len(source_policy.fact_start_problems("facts", "legacy", [], Sources(True), "p")), 1)
        self.assertEqual(len(source_policy.fact_start_problems("facts", "allowlist", ["a", "b"], Sources(True), "p")), 1)
        self.assertEqual(len(source_policy.fact_start_problems("facts", "allowlist", [], None, "p")), 1)
        inactive = source_policy.fact_start_problems("facts", "allowlist", [], Sources(False), "p")
        self.assertEqual(len(inactive), 1)
        self.assertIn("A4", inactive[0])
        self.assertEqual(len(source_policy.fact_start_problems("facts", "allowlist", [], Sources(True), "q")), 1)
        self.assertEqual(len(source_policy.fact_start_problems("feed", "legacy", ["x"], None, "p")), 4)                 # 넷 모두 따로 말한다


class CreatedPostTest(FB.FactEnv):
    def run_ok(self, **kwargs):
        value, report, out, error = self.run_branch(**kwargs)
        self.assertIsNone(error, error)
        self.assertIsNotNone(value, (report, out))
        return value, report, out

    def test_the_first_run_makes_one_korean_post_in_the_category_folder_with_the_standard_file_name(self):
        value, report, out = self.run_ok()
        path, english = value
        self.assertIsNone(english)
        self.assertEqual(path.as_posix(), "_posts/과학·환경/2026-11-10-KR-101200.md")
        self.assertEqual([p.relative_to(self.work).as_posix() for p in self.posts()], [path.as_posix()])
        self.assertEqual(report["outcome"], "DRAFT_CREATED")
        self.assertEqual(report["lane_label"], g.FACT_LANE_LABEL)
        self.assertEqual(report["paths"], [str(path)])
        self.assertFalse(any("-EN-" in name or "/EN " in name or "EN - " in name for name in self.files()), self.files())       # 영문 글·영문 폴더가 없다

    def test_the_file_has_the_marker_the_own_card_image_and_passes_the_final_checks(self):
        value, _report, _out = self.run_ok()
        text = (self.work / value[0]).read_text(encoding="utf-8")
        self.assertEqual(g.front_matter_problems(text, allow_provenance=True), [])
        self.assertTrue(any("provenance" in problem for problem in g.front_matter_problems(text)))   # 표식은 모델 글에는 없어야 하므로 기본 검사는 표식을 문제로 센다
        self.assertEqual(provenance.mark_of_text(text), provenance.MARK_FACTS)
        self.assertEqual(text.count('provenance: "facts"'), 1)
        front = text.split("\n---\n", 1)[0]
        self.assertIn('lang: ko', front)
        card = g.fact_card_url()
        self.assertIn(f'image: "{card}"', front)
        self.assertRegex(card, r"^https://[^/]+/.*assets/fact-card\.svg$")
        for needle in ("description:", "source_name:", "source_url:", "source_domain:"):
            self.assertIn(needle, front)
        tags = json.loads(next(line for line in front.splitlines() if line.startswith("tags:"))[len("tags:"):])
        self.assertTrue(len(tags) >= 3 and all(isinstance(tag, str) and tag for tag in tags), tags)    # 조립기의 태그가 머리말에 들어간다
        self.assertIn("우주날씨", tags)
        self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"))                            # 글 끝은 줄바꿈 하나
        for banned in ("unsplash", "Photo by", "![Thumbnail]"):
            self.assertNotIn(banned, text)
        self.assertTrue((g.FACT_CARD_FILE).is_file())

    def test_the_card_address_follows_the_site_config_and_matches_the_registry_url(self):
        reg_url = next(blog["url"] for blog in json.loads((FB.ROOT / "pipeline" / "blogs.json").read_text(encoding="utf-8"))["blogs"] if blog["key"] == "chance")
        self.assertEqual(g.fact_site_url(), reg_url.rstrip("/"))
        self.assertEqual(g.fact_card_url(), reg_url.rstrip("/") + "/assets/fact-card.svg")
        other = self.tmp / "cfg.yml"
        for text, expected in (('url: "https://a.example"\nbaseurl: "/x"\n', "https://a.example/x"), ("url: https://a.example/\nbaseurl: /x/\n", "https://a.example/x"), ("url: https://a.example\nbaseurl: ''\n", "https://a.example"),
                               ("title: t\r\nurl: 'https://a.example'\r\nbaseurl: \"/y\"  # 주석\r\n", "https://a.example/y"), ("url: https://a.example\n", "https://a.example")):
            other.write_bytes(text.encode("utf-8"))
            self.assertEqual(g.fact_site_url(other), expected, text)
        for bad in ("baseurl: /x\n", "url: http://a.example\n", "url: https://a.example/path\n", "url: https://a.example\nbaseurl: x\n", "url: https://a b.example\n", ""):
            other.write_bytes(bad.encode("utf-8"))
            with self.assertRaises(RuntimeError):
                g.fact_site_url(other)

    def test_the_history_entry_has_the_own_title_the_keys_the_marker_and_the_draft_fields(self):
        value, _report, _out = self.run_ok()
        entries = self.history()
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        text = (self.work / value[0]).read_text(encoding="utf-8")
        title = next(line for line in text.splitlines() if line.startswith("title:"))
        self.assertEqual(json.loads(title[len("title: "):]), entry["topic"])
        self.assertEqual(entry["topic"], entry["kr_title"])
        self.assertEqual(entry["date"], "2026-11-10")
        self.assertEqual((entry["slot"], entry["languages"], entry["content_source"], entry["provenance"]), (9, ["ko"], "facts", "facts"))
        self.assertEqual(entry["candidate_key"], "space_weather.kp_weekly:2026-W46")
        self.assertEqual(entry["recipe_id"], "R04_NOREGION_SERIES")
        self.assertRegex(entry["as_of"], r"^\d{4}-\d{2}-\d{2}")
        self.assertTrue(entry["dedupe_key"].startswith("R04_NOREGION_SERIES|space_weather.kp_estimated"))
        self.assertEqual(entry["kr_image"], g.fact_card_url())
        self.assertEqual((entry["source"], entry["source_url"]), (N.product_source_name("kp_estimated"), N.product_url("kp_estimated")))
        self.assertNotIn("en_title", entry)
        self.assertNotIn("en_image", entry)
        self.assertEqual((entry["flow"], entry["branch"], entry["paths"]), ("pr", "ai/draft/2026-11-10-s9", ["_posts/과학·환경/2026-11-10-KR-101200.md"]))
        self.assertTrue(provenance.entry_blocks_ai(entry))
        self.assertNotIn("lane", entry)

    def test_the_fact_post_goes_the_approval_flow_the_existing_way(self):
        value, report, out = self.run_ok()
        entry = self.history()[0]
        draft_flow.check_entry(entry)                                                             # 승인 흐름 항목답다(글 파일 경로 하나 = 국문 전용)
        text = (self.work / value[0]).read_text(encoding="utf-8")
        self.assertEqual(report["draft_branch"], entry["branch"])
        self.assertIn("승인 흐름: 초안 브랜치 ai/draft/2026-11-10-s9", out)
        self.assertTrue(drafts.build_pr_title(entry["kr_title"], None, ko_only=True).startswith(drafts.PR_TITLE_PREFIX))
        body = drafts.build_pr_body(entry, text, None, owner="owner")
        self.assertIn(entry["kr_title"], body)
        self.assertIn(N.product_url("kp_estimated"), body)                                        # 승인 PR 본문에 공식 자료 링크가 있다
        self.assertNotIn("English", body)
        self.assertEqual(g.slot_state(self.history(), self.now), (9, "ALREADY_PUBLISHED"))
        self.assertEqual(drafts.refine_slot_state("ALREADY_PUBLISHED", 9, self.history(), "2026-11-10", exists=lambda path: False), drafts.STATE_PENDING)        # 글이 main 에 아직 없으면(병합 전) 승인 대기로 보인다 — 같은 슬롯을 다시 만들지 않는다
        self.assertEqual(drafts.refine_slot_state("ALREADY_PUBLISHED", 9, self.history(), "2026-11-10", exists=lambda path: True), "ALREADY_PUBLISHED")                 # 병합돼 글이 main 에 있으면 그냥 발행됨
        self.assertEqual(publish_lock.weekly_posts(self.history(), [], self.now.date()).count, 1)
        self.assertEqual(publish_lock.posts_today(self.history(), "2026-11-10"), 1)

    def test_without_the_approval_flow_argument_the_run_ends_as_published_and_has_no_branch(self):
        self.use(FB.facts_registry(), FB.sources_registry())
        value, report, _out = self.run_ok(draft_flow=False)
        entry = self.history()[0]
        self.assertEqual(report["outcome"], "PUBLISHED")
        for key in ("flow", "branch", "paths"):
            self.assertNotIn(key, entry)
        self.assertNotIn("draft_branch", report)

    def test_a_manual_run_without_a_slot_uses_a_time_stamped_branch(self):
        _value, _report, _out = self.run_ok(slot=None)
        entry = self.history()[0]
        self.assertIsNone(entry["slot"])
        self.assertEqual(entry["branch"], "ai/draft/2026-11-10-m101200")

    def test_no_feed_page_model_prompt_photo_or_search_function_is_ever_called_and_the_model_call_count_is_zero(self):
        urlopen = mock.patch("urllib.request.urlopen", side_effect=AssertionError("네트워크 직접 접속"))
        with urlopen, mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0}):
            _value, _report, _out = self.run_ok()
            self.assertEqual(g.GEMINI_CALLS, {"attempts": 0, "failed": 0})
        for name, spy in self.spies.items():
            spy.assert_not_called()
        self.assertEqual(self.noaa.products(), ["kp_estimated"])

    def test_a_practice_run_writes_nothing_but_reports_what_it_would_make(self):
        self.patch_value(g, "DRY_RUN", True)
        value, report, out = self.run_ok()
        self.assertEqual(self.files(), [])
        self.assertIn("DRY_RUN: 파일·기록은 저장되지 않았습니다", out)
        self.assertEqual(report["outcome"], "DRAFT_CREATED")
        self.assertIn("연습 실행이라 초안 브랜치", out)

    def test_an_existing_file_with_the_same_name_is_not_overwritten(self):
        target = self.work / "_posts" / "과학·환경"
        target.mkdir(parents=True)
        (target / "2026-11-10-KR-101200.md").write_text("기존 글", encoding="utf-8")
        before = self.files()
        value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], source_policy.FACT_ALL_SKIPPED_OUTCOME)
        self.assertEqual((target / "2026-11-10-KR-101200.md").read_text(encoding="utf-8"), "기존 글")
        self.assertEqual(self.files(), before)
        self.assertIn("FILE_EXISTS", " ".join(report["fact_notes"]))

    def test_english_is_never_made_even_when_the_registry_settings_say_so(self):
        """영문 요청: 레지스트리가 ko·en 이면 레지스트리 검증이 facts 를 거절해 시작 점검이 막는다(영문 짝 글·영문 폴더는 어떤 경우에도 만들어지지 않는다)."""
        self.use(FB.facts_registry(languages=["ko", "en"]), FB.sources_registry())
        value, report, out, error = self.run_branch()
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], source_policy.FACT_NOT_READY_OUTCOME)
        self.assertEqual(self.files(), [])

    def test_the_summary_for_a_made_post_says_zero_model_calls_and_names_the_skipped_subjects(self):
        self.noaa.by_product["kp_estimated"] = FB.TR.kp_rows_on_days([(f"2026-11-{day:02d}", 3.0) for day in (3, 4, 5, 6, 8, 9)])
        value, report, out = self.run_ok()
        self.assertEqual(report["fact_notes"], ["Fact 글감 kp_weekly 건너뜀: INSUFFICIENT:NO_ANALYSIS"])
        self.assertEqual(self.history()[0]["candidate_key"], "space_weather.kp_storm_weekly:2026-W46")                     # 같은 묶음의 다음 글감이 이어졌다
        report["gemini_calls"] = {"attempts": 0, "failed": 0}
        summary = g.render_run_summary("schedule", self.now, 9, report)
        self.assertIn("- 결과: **DRAFT_CREATED**", summary)
        self.assertIn("- Gemini 호출: 0회(실패 0회)", summary)
        self.assertIn("- Fact 글감 kp_weekly 건너뜀: INSUFFICIENT:NO_ANALYSIS", summary)
        self.assertIn(g.FACT_LANE_LABEL, summary)
        self.assertIn("편집 축: 구조화 공개 자료", summary)                                                     # 운영자가 요약에서 읽는 이름


class RotationThroughHistoryTest(FB.FactEnv):
    def run_day(self, day, hour=10):
        self.now = FB.at(day, hour)
        self.noaa.by_product = FB.payloads(self.now.date())
        value, report, out, error = self.run_branch(slot=9)
        self.assertIsNone(error, error)
        return value, report

    def test_successive_days_walk_through_the_subjects_oldest_first_and_stop_when_nothing_is_left(self):
        picked = []
        for day in ("2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"):
            value, report = self.run_day(day)
            self.assertIsNotNone(value, (day, report))
            picked.append(self.history()[-1]["candidate_key"].split(":")[0].replace("space_weather.", ""))
        self.assertEqual(picked, ["kp_weekly", "flares_weekly", "scales_weekly", "sunspot_daily_monthly"])
        value, report = self.run_day("2026-11-14")
        self.assertEqual(self.history()[-1]["candidate_key"], "space_weather.sunspot_monthly_monthly:2026-11")
        value, report = self.run_day("2026-11-15")
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], source_policy.FACT_NO_CANDIDATE_OUTCOME)                       # 이번 기간의 글감은 다 냈다 — 정상 건너뜀
        self.assertEqual(len(self.posts()), 5)
        self.assertEqual(len(self.history()), 5)

    def test_the_daily_sunspot_subject_waits_for_00_30_utc_by_the_korean_clock_and_says_so(self):
        """한국 시각 09:10 은 협정 세계시 00:10 이다. 일별 흑점수(하한 00:30 UTC)가 차례인 날은 기다린다(FACT_WAITING·기다림 한 줄·요청 0·이력 그대로). 09:40(= 00:40 UTC)이면 글이 나온다 —
        수집 시각을 협정 세계시로 바꾸지 않고 한국 시각에 Z 만 붙여 넘기면 이 판정이 어긋난다."""
        spec_ids = ("kp_weekly", "kp_storm_weekly", "flares_weekly", "scales_weekly", "sunspot_monthly_monthly")
        history = [{"date": "2026-11-02", "content_source": "facts", "candidate_key": K.candidate_key(K.SPEC_BY_ID[spec_id], "2026-11-02"), "dedupe_key": f"d|{spec_id}",
                    "topic": f"지난 글 {spec_id}", "provenance": "facts"} for spec_id in spec_ids]
        self.set_history(history)
        self.now = FB.at("2026-11-10", 9, 10)
        value, report, out, error = self.run_branch(slot=9)
        self.assertIsNone(error, error)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], source_policy.FACT_WAITING_OUTCOME)
        self.assertEqual(self.noaa.calls, [])                                                               # 기다리는 글감이 맨 앞이라 아무것도 부르지 않았다
        self.assertEqual(report["fact_notes"], ["Fact 글감 sunspot_daily_monthly 은(는) 일별 제품의 협정 세계시 하한 때문에 기다림"])
        self.assertEqual(self.history(), history)
        self.now = FB.at("2026-11-10", 9, 40)
        value, report, out, error = self.run_branch(slot=9)
        self.assertIsNone(error, error)
        self.assertIsNotNone(value)
        self.assertEqual(self.history()[-1]["candidate_key"], "space_weather.sunspot_daily_monthly:2026-11")
        self.assertEqual(self.noaa.products(), ["ssn_daily"])

    def test_the_same_product_is_not_read_again_for_a_week_even_across_the_period_boundary(self):
        self.run_day("2026-11-15")                                                                          # 일요일(46주)에 낸 Kp 글
        calls_before = len(self.noaa.calls)
        picked = []
        for day in ("2026-11-16", "2026-11-17"):
            value, report = self.run_day(day)
            picked.append(self.history()[-1]["candidate_key"] if value else None)
        self.assertTrue(all(key and not key.startswith(("space_weather.kp_weekly", "space_weather.kp_storm_weekly")) for key in picked), picked)
        self.assertNotIn("kp_estimated", self.noaa.products()[calls_before:])                              # Kp 제품은 부르지도 않았다


class FailureModesTest(FB.FactEnv):
    def sources_with(self, **own):
        data = FB.sources_registry()
        edit_provider(data, lambda item: item["access"][0]["rate_limit"]["own"].update(own))
        self.use(FB.facts_registry(), data)

    def test_a_host_outside_the_allowlist_is_refused_by_the_gate_and_never_requested(self):
        with mock.patch.object(egress, "check_url", side_effect=egress.EgressDenied("services.swpc.noaa.gov", "fact", "시험: 허용 목록 밖")):
            value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], source_policy.FACT_ALL_SKIPPED_OUTCOME)
        self.assertEqual(self.noaa.calls, [])
        self.assertTrue(all(note.endswith("ADAPTER:EGRESS_DENIED") for note in report["fact_notes"]), report["fact_notes"])
        self.assertEqual(self.files(), [])

    def test_a_path_the_registry_does_not_list_is_skipped_while_a_listed_one_still_makes_a_post(self):
        data = FB.sources_registry()
        edit_provider(data, lambda item: item["access"][0].update(paths=[N.PRODUCTS["scales"].path]))
        self.use(FB.facts_registry(), data)
        value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertEqual(self.history()[0]["candidate_key"], "space_weather.scales_weekly:2026-W46")
        self.assertEqual(self.noaa.products(), ["scales"])
        self.assertTrue(any("kp_weekly" in note and "BAD_ACCESS" in note for note in report["fact_notes"]), report["fact_notes"])

    def test_the_run_call_cap_stops_further_products_and_is_reported_as_a_budget_denial(self):
        self.sources_with(max_products_per_post=1, max_calls_per_product_per_post=1, max_retries=0)       # 한 실행에 한 번뿐
        self.noaa.by_product["kp_estimated"] = FB.H.kp_rows("2026-11-08", 2)                                # Kp 는 자료 부족 — 다음 제품으로 넘어가야 한다
        value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertIsNone(value)
        self.assertEqual(self.noaa.products(), ["kp_estimated"])                                           # 첫 호출만 나갔다
        self.assertEqual(report["outcome"], source_policy.FACT_ALL_SKIPPED_OUTCOME)
        denied = [note for note in report["fact_notes"] if "BUDGET_DENIED" in note]
        self.assertTrue(denied, report["fact_notes"])
        self.assertTrue(any("flares_weekly" in note for note in denied))

    def test_a_429_or_403_stops_the_provider_for_the_rest_of_the_run(self):
        for code in (429, 403):
            with self.subTest(code=code):
                self.noaa.calls.clear()
                self.noaa.fail["kp_estimated"] = HttpStatus(code)
                value, report, out, error = self.run_branch()
                self.assertIsNone(error)
                self.assertIsNone(value)
                self.assertEqual(self.noaa.products(), ["kp_estimated"])                                   # 그 뒤 어떤 제품도 부르지 않았다
                self.assertEqual(report["outcome"], source_policy.FACT_ALL_SKIPPED_OUTCOME)
                self.assertTrue(any("BUDGET_DENIED" in note for note in report["fact_notes"]))
                self.assertEqual(self.files(), [])

    def test_a_404_stops_only_that_address_and_the_other_products_go_on(self):
        self.noaa.fail["kp_estimated"] = HttpStatus(404)
        value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertEqual(self.history()[0]["candidate_key"], "space_weather.flares_weekly:2026-W46")
        self.assertEqual(self.noaa.products(), ["kp_estimated", "xray_flares"])

    def test_three_failures_stop_the_run_and_the_rest_are_not_requested(self):
        for product in ("kp_estimated", "xray_flares", "scales"):
            self.noaa.fail[product] = OSError("끊김")
        value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertIsNone(value)
        self.assertEqual(self.noaa.products(), ["kp_estimated", "xray_flares", "scales"])                  # 세 번째 실패 뒤 월 글감 둘은 호출이 나가지 않았다
        self.assertTrue(any("SKIPPED_AFTER_FAILURES" in note or "BUDGET_DENIED" in note for note in report["fact_notes"]))

    def test_a_broken_response_never_makes_a_post(self):
        for product in ("kp_estimated", "xray_flares", "scales", "ssn_daily", "ssn_monthly"):
            self.noaa.raw[product] = b"{broken"
        value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], source_policy.FACT_ALL_SKIPPED_OUTCOME)
        self.assertEqual(self.files(), [])
        self.assertTrue(all("ADAPTER:BAD_JSON" in note for note in report["fact_notes"]))


class OpenerTest(unittest.TestCase):
    """연결 코드 `fact_opener`·`make_fact_transport` 의 직접 시험."""

    def setUp(self):
        self.sources = source_registry.build_registry(FB.sources_registry(), "2026-11-10")
        self.provider = self.sources.get(FB.PROVIDER_ID)
        self.access = fact_supply.api_access(self.provider)
        self.sent = []

    def transport(self, url, *, timeout, max_bytes):
        self.sent.append((url, timeout, max_bytes))
        return b"[]"

    def test_the_gate_refuses_hosts_paths_and_purposes_outside_the_allowlist_without_counting_a_call(self):
        opener, budget = g.fact_opener(self.sources, self.provider, self.access, self.transport)
        for url in ("https://other.example/products/noaa-scales.json", "https://services.swpc.noaa.gov/json/other.json", "http://services.swpc.noaa.gov/products/noaa-scales.json",
                    "https://services.swpc.noaa.gov:8443/products/noaa-scales.json", "https://user@services.swpc.noaa.gov/products/noaa-scales.json"):
            with self.subTest(url=url):
                with self.assertRaises(fact_supply.AdapterError) as caught:
                    opener(url, timeout=5, max_bytes=10)
                self.assertEqual(caught.exception.code, "EGRESS_DENIED")
        self.assertEqual((self.sent, budget.calls, budget.failures), ([], 0, 0))                          # 거부는 요청이 아니다 — 호출 수·실패로 세지 않는다

    def test_a_listed_address_is_sent_once_and_the_same_address_reuses_the_answer(self):
        opener, budget = g.fact_opener(self.sources, self.provider, self.access, self.transport)
        url = N.product_url("scales")
        self.assertEqual(opener(url, timeout=5, max_bytes=100), b"[]")
        self.assertEqual(opener(url, timeout=5, max_bytes=100), b"[]")
        self.assertEqual(self.sent, [(url, 5, 100)])
        self.assertEqual(budget.calls, 1)

    def test_an_inactive_provider_cannot_pass_the_gate(self):
        data = FB.sources_registry(enabled=False)
        sources = source_registry.build_registry(data, "2026-11-10")
        provider = sources.get(FB.PROVIDER_ID)
        opener, _budget = g.fact_opener(sources, provider, fact_supply.api_access(provider), self.transport)
        with self.assertRaises(fact_supply.AdapterError) as caught:
            opener(N.product_url("scales"), timeout=5, max_bytes=100)
        self.assertEqual(caught.exception.code, "EGRESS_DENIED")
        self.assertEqual(self.sent, [])

    def test_the_budget_comes_from_the_registry_limit_and_an_unknown_limit_means_no_call_at_all(self):
        _opener, budget = g.fact_opener(self.sources, self.provider, self.access, self.transport)
        self.assertEqual(budget.max_calls, 6)
        self.assertEqual(budget.max_retries, 1)
        data = FB.sources_registry()
        edit_provider(data, lambda item: item["access"][0].update(rate_limit=None))
        sources = source_registry.build_registry(data, "2026-11-10")
        provider = sources.get(FB.PROVIDER_ID)
        opener, budget = g.fact_opener(sources, provider, provider.access[0], self.transport)
        self.assertEqual(budget.max_calls, 0)
        with self.assertRaises(fact_supply.AdapterError) as caught:
            opener(N.product_url("scales"), timeout=5, max_bytes=100)
        self.assertEqual(caught.exception.code, "EGRESS_DENIED")                                          # (제공처가 ACTIVE 가 아니라 관문이 먼저 거부한다)

    def test_when_the_gate_passes_the_budget_decides_and_says_why(self):
        provider = mock.Mock(provider_id=FB.PROVIDER_ID)
        access = mock.Mock(rate_limit="1/day")                                                             # 문구 한도 1/day → 한 실행 몫 0
        with mock.patch.object(egress, "check_url", lambda url, purpose, sources: None):
            opener, budget = g.fact_opener(self.sources, provider, access, self.transport)
            self.assertEqual(budget.max_calls, 0)
            with self.assertRaises(fact_supply.AdapterError) as caught:
                opener("https://services.swpc.noaa.gov/a", timeout=5, max_bytes=10)
        self.assertEqual(caught.exception.code, "BUDGET_DENIED")
        self.assertIn("RUN_CAP", str(caught.exception))
        self.assertEqual(self.sent, [])

    def test_a_status_error_passes_through_once_and_then_the_provider_is_stopped_for_the_run(self):
        provider = mock.Mock(provider_id=FB.PROVIDER_ID)
        access = mock.Mock(rate_limit="10/hour")
        calls = []

        def failing(url, *, timeout, max_bytes):
            calls.append(url)
            raise HttpStatus(429)
        with mock.patch.object(egress, "check_url", lambda url, purpose, sources: None):
            opener, budget = g.fact_opener(self.sources, provider, access, failing)
            with self.assertRaises(HttpStatus):
                opener("https://services.swpc.noaa.gov/a", timeout=5, max_bytes=10)                       # 어댑터가 OPENER_FAILED 로 바꾼다
            with self.assertRaises(fact_supply.AdapterError) as caught:
                opener("https://services.swpc.noaa.gov/b", timeout=5, max_bytes=10)
        self.assertEqual(caught.exception.code, "BUDGET_DENIED")
        self.assertIn("STOPPED_BY_STATUS", str(caught.exception))
        self.assertEqual(calls, ["https://services.swpc.noaa.gov/a"])
        self.assertTrue(budget.blocked)

    def test_the_real_transport_asks_for_gzip_reads_one_byte_more_than_the_limit_and_unpacks(self):
        class Response:
            def __init__(self, body, encoding=""):
                self.body, self.headers, self.read_sizes = body, {"Content-Encoding": encoding}, []

            def read(self, size=-1):
                self.read_sizes.append(size)
                return self.body[:size]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class Opener:
            def __init__(self, response):
                self.response, self.requests = response, []

            def open(self, request, timeout=None):
                self.requests.append((request, timeout))
                return self.response
        raw = b'{"a": 1}' * 50
        packed = zlib.compress(raw, 9)
        gz = zlib.compressobj(wbits=31)
        gzipped = gz.compress(raw) + gz.flush()
        for response, expected in ((Response(raw), raw), (Response(gzipped, "gzip"), raw)):
            fake = Opener(response)
            seen = []
            with mock.patch.object(egress, "build_checked_opener", lambda *args, **kwargs: (seen.append((args, kwargs)), fake)[1]):
                transport = g.make_fact_transport(self.sources)
                body = transport("https://services.swpc.noaa.gov/products/noaa-scales.json", timeout=7, max_bytes=1000)
            self.assertEqual(body, expected)
            self.assertEqual(seen[0][0][0], "fact")
            self.assertEqual(seen[0][1], {"max_redirects": 0})
            request, timeout = fake.requests[0]
            self.assertEqual(timeout, 7)
            self.assertEqual(request.get_header("Accept-encoding"), "gzip")
            self.assertTrue(request.get_header("User-agent"))
            self.assertEqual(response.read_sizes, [1001])
        self.assertTrue(packed)
        bomb = zlib.compressobj(wbits=31)
        zipped = bomb.compress(b"0" * 5_000_000) + bomb.flush()
        fake = Opener(Response(zipped, "gzip"))
        with mock.patch.object(egress, "build_checked_opener", lambda *args, **kwargs: fake):
            body = g.make_fact_transport(self.sources)("https://services.swpc.noaa.gov/x", timeout=7, max_bytes=1000)
        self.assertEqual(len(body), 1001)                                                                 # 압축을 푼 크기가 한도 + 1 에서 잘려 어댑터가 거절한다(압축 폭탄 방어)
        with self.assertRaises(ValueError):
            g._fact_gunzip(b"not gzip at all", 100)


class GateConnectionTest(FB.FactEnv):
    def setUp(self):
        super().setUp()
        self.use(FB.facts_registry(quality_gate="hold"), FB.sources_registry())

    def test_the_candidate_source_given_to_the_gate_has_the_agreed_shape_and_the_unmarked_text(self):
        seen = []

        def spy(data, source, history=(), config=None, as_of=None):
            seen.append((data, source, list(history), config, as_of))
            return quality_gate.GateReport()
        with mock.patch.object(quality_gate, "check_candidate", spy):
            value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertEqual(report["outcome"], "DRAFT_CREATED")
        data, source, history, config, as_of = seen[0]
        self.assertEqual(tuple(source), fact_supply.GATE_SOURCE_KEYS)
        self.assertIs(source["fact_post"], True)
        self.assertEqual(source["provider_hosts"], [N.HOST])
        self.assertEqual(source["source_domain"], N.HOST)
        self.assertTrue(source["evidence_text"] and source["dedupe_key"] and source["recipe_id"] and source["as_of"])
        self.assertEqual(set(data), {"kr_title", "kr_content"})
        self.assertNotIn("provenance", data["kr_content"])                                                   # Gate 에는 표식 전 글을 넘긴다
        self.assertTrue(data["kr_content"].startswith("---\nlayout: post"))
        self.assertEqual(as_of, self.now.date())
        self.assertEqual(history, [])
        self.assertEqual(config.languages, ("ko",))

    def test_a_held_candidate_is_skipped_with_its_codes_and_the_next_subject_continues(self):
        def spy(data, source, history=(), config=None, as_of=None):
            report = quality_gate.GateReport()
            if source["recipe_id"] == "R04_NOREGION_SERIES":
                report.holds.append(quality_gate.Hold("QG1-NUMBER", 1, "ko", "시험 보류"))
            return report
        with mock.patch.object(quality_gate, "check_candidate", spy):
            value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertEqual(self.history()[0]["candidate_key"], "space_weather.kp_storm_weekly:2026-W46")
        self.assertEqual(report["fact_notes"], ["Fact 글감 kp_weekly 건너뜀: REJECTED:GATE:QG1-NUMBER"])

    def test_when_every_candidate_is_held_nothing_is_written(self):
        def spy(data, source, history=(), config=None, as_of=None):
            report = quality_gate.GateReport()
            report.holds.append(quality_gate.Hold("QG0-NO-SOURCE", 0, "post", "시험 보류"))
            return report
        with mock.patch.object(quality_gate, "check_candidate", spy):
            value, report, out, error = self.run_branch()
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], source_policy.FACT_ALL_SKIPPED_OUTCOME)
        self.assertEqual(self.files(), [])
        self.assertEqual(len(report["fact_notes"]), 6)

    def test_the_gate_off_by_default_is_never_called(self):
        self.use(FB.facts_registry(), FB.sources_registry())
        with mock.patch.object(quality_gate, "check_candidate", side_effect=AssertionError("꺼진 Gate 를 불렀다")):
            value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertEqual(report["outcome"], "DRAFT_CREATED")

    def test_the_gate_that_does_not_know_the_shape_yet_never_makes_the_run_crash(self):
        """S2BG 가 병합되기 전의 Gate(Fact 후보 사전을 모른다)는 근거를 읽지 못해 보류한다 — 어느 쪽이든(보류든 통과든) 예외 없이 끝난다. 이 시험은 병합 전후 모두 초록이다."""
        value, report, out, error = self.run_branch()
        self.assertIsNone(error, error)
        self.assertIn(report["outcome"], ("DRAFT_CREATED", source_policy.FACT_ALL_SKIPPED_OUTCOME))
        if value is None:
            self.assertEqual(self.files(), [])
            self.assertTrue(all("REJECTED:GATE:" in note for note in report["fact_notes"]))


class NoNamedInnerFunctionTest(unittest.TestCase):
    """AF4 의 알려진 사각지대 B16(docs/AI_FLOW.md 사각지대 표): 정적 규칙은 이름 있는 안쪽 함수를 **부르는 줄** 만 따라가고 값으로 넘기거나 담기만 하는 안쪽 함수의 몸통은 읽지 않는다.
    그래서 Fact 구역은 콜백을 이름 있는 안쪽 함수가 아니라 람다나 최상위 함수로 넘기고, 이 시험이 그 규칙을 지킨다 — 사각지대를 사람이 쓰는 코드의 규칙으로 막는다."""
    ZONE = ("fact_", "_fact_", "make_fact_", "generate_fact_")

    def inner_functions(self, text, only=None):
        found = []
        for node in ast.parse(text).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (only is None or only(node.name)):
                found += [(node.name, inner.name) for inner in ast.walk(node) if inner is not node and isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef))]
        return found

    def read(self, rel):
        return (_bootstrap.ROOT / rel).read_text(encoding="utf-8")

    def test_the_fact_zone_of_the_generator_the_supply_module_and_the_shadow_branch_have_no_named_function_inside_a_function(self):
        zone = lambda name: name.startswith(self.ZONE)        # noqa: E731
        names = [node.name for node in ast.parse(self.read("generator.py")).body if isinstance(node, ast.FunctionDef) and zone(node.name)]
        self.assertTrue({"generate_fact_post", "fact_prepare", "fact_check_post", "fact_opener", "fact_history_entry", "make_fact_transport"} <= set(names), names)      # 검사 대상이 비어 통과하지 않게
        self.assertEqual(self.inner_functions(self.read("generator.py"), zone), [])
        self.assertEqual(self.inner_functions(self.read("pipeline/fact_supply.py")), [])
        self.assertEqual(self.inner_functions(self.read("pipeline/shadow_run.py"), lambda name: name in ("run_facts", "facts_branch_on")), [])

    def test_the_check_really_sees_a_named_function_inside_a_function_but_not_a_lambda(self):
        sample = "def fact_a():\n    def inner():\n        return 1\n    return inner\n\n\ndef fact_b():\n    return (lambda: 1)()\n\n\ndef other():\n    def inner():\n        return 2\n"
        self.assertEqual(self.inner_functions(sample, lambda name: name.startswith("fact_")), [("fact_a", "inner")])
        self.assertEqual(self.inner_functions(sample), [("fact_a", "inner"), ("other", "inner")])


if __name__ == "__main__":
    unittest.main()
