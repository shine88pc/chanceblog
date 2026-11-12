"""생성기의 구조화 Fact 분기(S2b, 레지스트리 chance.content_source: facts)의 시험 — 실제 `generate_blog_posts` 를 임시 작업 폴더에서 돌린다. 네트워크·시계·진짜 키 없음(가짜 transport·가짜 시계).

못박는 것
1. **켜기 전 안전장치**: content_source 값 모양·`facts` 인데 allowlist 아님·국문 단독 아님·승인 흐름 아님·레지스트리 오류·Provider 꺼짐(지금 저장소의 실제 상태)·strict_tier·기한·호출 한도·카드 이미지 없음·요청 주제 —
   하나라도 아니면 글을 만들지 않고 이유를 한 줄로 남기고 **정상 종료**(예외 없음·파일·이력 그대로·요청 0·피드 경로로 되돌아가지 않음)한다.
2. **만든 글**: 파일 이름·분류 폴더·머리말(출처 표식 한 줄·자체 카드 이미지 https 주소·설명·출처 세 줄)·이력 항목(자체 제목·candidate_key·dedupe_key·recipe_id·as_of·content_source·표식)·승인 흐름 항목.
3. **AI 0**: 피드·기사 발췌·모델·프롬프트·사진·이미지 검색어 함수를 한 번도 부르지 않고(부르면 시험이 실패하는 감시자) 모델 호출 횟수가 0 이다.
4. **연결 코드**(`fact_opener`): 허용 목록 관문·호출 예산 — 허용 밖 호스트·ACTIVE 가 아닌 Provider·호출 예산 소진·429/403 중지·404·실패 3회 뒤 건너뜀·같은 주소 응답 재사용·응답 깨짐.
5. **Gate 연결**: 후보 사전의 모양(아홉 키)·보류되면 다음 글감·현재 Gate 가 그 모양을 몰라도 예외 없음.
6. 기본(feed)에서는 이 분기가 한 번도 실행되지 않는다(옛 생성기와의 바이트 비교는 `test_generator_source_policy` 의 GOLDEN 이 맡는다).
7. **S2BFIX(독립 검증 S2b 의 후속)**: 응답 읽기 전체 시간 상한(D2)·깨진 이력이면 멈춤(D7)·승인 흐름이 아니면 멈춤(D9)·승인 PR 본문의 계산 글 문구(D-254)·이력 200개 한계(D-256)·
   Fact 구역이 사진·기사 읽기를 부르지 않음(D5)."""
import ast
import contextlib
import datetime
import io
import itertools
import json
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import fact_branch_helpers as FB
import generator as g

from pipeline import ai_guard, drafts, draft_flow, egress, provenance, publish_lock, quality_gate, registry, source_policy, source_registry
from pipeline import fact_candidates as K
from pipeline import fact_supply
from pipeline.adapters import noaa_swpc as N

FEED_SIMILARITY_LINE = "- 제목 유사도: 기존 글·대기 중인 초안과 비슷하지 않음(후보 0.6·생성 제목 0.7 기준, 생성기가 검사함)"          # 피드 글 승인 PR 본문의 줄(바이트 불변 — 이 묶음이 바꾸지 않았다)
FACT_SIMILARITY_LINE = "- 제목 유사도: 해당 없음(계산 글은 제목을 견주지 않고, 같은 기간·같은 자료로 이미 낸 글이 있으면 후보에서 빼는 중복 키로 막음)"      # N1(D-320): 계산 글 본문의 줄


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


class FakeClock:
    """가짜 단조 시계(진짜 시간에 기대지 않는다): 부를 때마다 지금 값을 돌려주고 `advance` 로 앞으로 보낸다."""

    def __init__(self, start=500.0):
        self.now, self.calls = start, 0

    def __call__(self):
        self.calls += 1
        return self.now

    def advance(self, seconds):
        self.now += seconds


class DrippingResponse:
    """응답 대역: 읽을 때마다 시계를 step 초 앞으로 보내고 조각 하나를 돌려준다(pieces 가 바닥나면 빈 조각 = 끝, 끝없는 이터레이터도 된다). 요청한 크기는 asked 에 남고 요청보다 큰 조각은 잘라 나눠 준다.
    `read1`(소켓 읽기 한 번 — 진짜 HTTPResponse 가 가진 것)과 `read` 가 같은 동작이다. 소켓·진짜 시간 없음."""

    def __init__(self, clock, pieces, step, encoding=""):
        self.clock, self.pieces, self.step = clock, iter(pieces), step
        self.headers, self.asked, self.pending = {"Content-Encoding": encoding}, [], b""

    def _next(self, size=-1):
        self.asked.append(size)
        self.clock.advance(self.step)
        if not self.pending:
            self.pending = next(self.pieces, b"")
        out, self.pending = self.pending[:size], self.pending[size:]
        return out

    read1 = read = _next

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ReadOnlyResponse(DrippingResponse):
    """`read1` 이 없는 응답 대역(`read` 만 있다) — 연결 코드는 read 로 물러난다."""
    read1 = None


class DrippingOpener:
    """`opener.open` 대역: 요청을 적고(requests) 시계를 open_seconds 만큼 보낸 뒤(연결·머리글에 걸린 시간) 응답 대역을 돌려준다."""

    def __init__(self, response, clock=None, open_seconds=0):
        self.response, self.clock, self.open_seconds, self.requests = response, clock, open_seconds, []

    def open(self, request, timeout=None):
        self.requests.append((request, timeout))
        if self.clock is not None:
            self.clock.advance(self.open_seconds)
        return self.response


class RegistryRulesTest(unittest.TestCase):
    def errors(self, **chance):
        return source_policy.content_source_errors({"content_source": "facts", **chance}, "블로그 'chance'", "jekyll-git")

    def test_the_real_registry_is_valid_and_sets_the_switch_to_facts_on_the_chance_entry_only_with_its_three_companions(self):
        """켜는 변경(T3, 패치 02): 진짜 레지스트리가 유효하고 Chance 항목에만 스위치 `facts` 와 그 짝 셋(허용 목록 모드·국문 단독·승인 흐름)이 있다. 전에는 값이 없고 `feed` 였다."""
        reg = registry.load_registry()
        self.assertEqual(registry.validate_registry(reg), [])
        self.assertEqual(source_policy.chance_content_source(), "facts")
        chance = registry.get_blog(reg, "chance")
        self.assertEqual((chance["content_source"], chance["source_policy"], chance["languages"], chance["publish_flow"]), ("facts", "allowlist", ["ko"], "pr"))
        self.assertEqual([blog["key"] for blog in reg["blogs"] if "content_source" in blog], ["chance"])
        self.assertNotIn("content_source", reg["defaults"])

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

    def test_in_the_real_allowlist_every_provider_except_the_one_the_path_reads_is_still_off(self):
        """전에는 '허용 목록의 62곳이 모두 꺼져 있다' 를 단언했다 — 켜는 변경(T3, 패치 02)이 NOAA 를 켜므로 '이 경로가 읽는 제공처(`noaa_swpc_json`)를 뺀 나머지가 모두 꺼져 있다' 로 바꿨다:
        켜지면 안 되는 제공처는 여전히 못박힌다(단언을 약하게 만들지 않는다). NOAA 의 켜짐 자체는 값으로 보지 않고 아래 두 시험이 행동으로 보인다(진짜 두 파일 그대로면 초안이 나오고 NOAA 를 끈 사본이면 아무것도 나오지 않는다).
        다른 제공처를 켜는 별건 PR 은 이 시험을 자기 제공처 이름으로 고친다(켜는 PR 이 의도적으로 고치는 값 표지판)."""
        self.assertEqual(fact_supply.PROVIDER_ID, FB.PROVIDER_ID)
        on = sorted(item["provider_id"] for item in FB.real_sources()["providers"] if item["enabled"] and item["provider_id"] != FB.PROVIDER_ID)
        self.assertEqual(on, [])

    def test_turning_off_the_one_provider_the_path_reads_in_the_real_allowlist_makes_nothing(self):
        """진짜 허용 목록 사본에서 이 경로가 읽는 제공처 하나(`noaa_swpc_json`)를 끄면 글이 나오지 않는다(켜는 변경 뒤의 실제 파일에서는 그 하나가 켜져 있다)."""
        self.use(FB.real_blogs(), FB.real_sources(noaa_enabled=False))
        out, _report = self.assert_not_ready("ACTIVE 가 아님")
        self.assertIn(FB.PROVIDER_ID, out)

    def test_the_real_registry_files_as_they_are_make_a_draft_and_each_companion_value_removed_makes_nothing(self):
        """진짜 두 파일 그대로(켜는 변경 뒤)는 초안이 만들어지고, 짝 값(허용 목록 모드·국문 단독·승인 흐름)이나 NOAA 켜짐 하나를 사본에서 빼면 아무 글도 나오지 않는다."""
        self.use(FB.real_blogs(), FB.real_sources())
        value, report, out, error = self.run_branch()
        self.assertIsNone(error, error)
        self.assertEqual(report["outcome"], "DRAFT_CREATED")
        for post in self.posts():
            post.unlink()
        (self.work / "history.json").unlink()
        self.noaa.calls.clear()                                                              # 한 시험 안에서 여러 번 돌리므로 가짜 NOAA 의 기록을 비운다('요청 도구도 만들지 않았다' 확인이 처음 실행에 걸리지 않게)
        self.noaa.factory_calls = 0
        self.use(FB.real_blogs(source_policy=None), FB.real_sources())
        self.assert_not_ready("allowlist")
        self.use(FB.real_blogs(languages=["ko", "en"]), FB.real_sources())
        self.assert_not_ready("레지스트리 검증 오류")
        self.use(FB.real_blogs(publish_flow="direct"), FB.real_sources())
        self.assert_not_ready("레지스트리 검증 오류")

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

    def test_without_the_approval_flow_the_run_stops_and_writes_nothing(self):
        """D9 — **의도적으로 바꾼 시험**(S2BFIX). 예전 이름은 `…_without_the_approval_flow_argument_the_run_ends_as_published_and_has_no_branch`: draft_flow=False 로 부르면 flow·branch·paths 가 없는
        직접 게시 모양의 글·이력이 써지고 `PUBLISHED` 로 끝나는 것을 기대했다. 독립 검증(S2b D9)이 그것을 '함수 수준에서는 승인 흐름이 강제되지 않는다' 는 구멍으로 짚었다 — 자동 공개 경로가 없는 것은
        레지스트리 검증(publish_flow: pr)과 main 이 넘기는 값의 합성뿐이었다. 이제 `generate_fact_post` 는 승인 흐름(draft_flow 참)이 아니면 `FACT_NOT_READY` 로 멈추고 글·이력·요청을 만들지 않는다(방어 한 겹).
        대조군(속이 비지 않게): 같은 설정에서 승인 흐름이면 초안이 만들어진다."""
        self.use(FB.facts_registry(), FB.sources_registry())
        before = self.files()
        for flow in (False, None, 0, ""):
            with self.subTest(draft_flow=flow):
                value, report, out, error = self.run_branch(draft_flow=flow)
                self.assertIsNone(error, error)
                self.assertIsNone(value)
                self.assertEqual(report["outcome"], source_policy.FACT_NOT_READY_OUTCOME)
                self.assertNotIn("draft_branch", report)
                self.assertEqual(self.files(), before)                                                # 글·이력 파일이 생기지 않았다
                self.assertEqual((self.noaa.factory_calls, self.noaa.calls), (0, []))                  # 요청 도구도 만들지 않았다
                lines = [line for line in out.splitlines() if line.startswith("[구조화 Fact] 글을 만들지 않습니다")]
                self.assertEqual(len(lines), 1, out)                                                   # 이유는 한 줄
                self.assertIn("승인 흐름", lines[0])
        for spy in self.spies.values():
            spy.assert_not_called()
        report = {}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(g.generate_fact_post(None, report))                                    # 인자를 안 주면(기본값 False) 멈춘다 — 열린 쪽이 기본값이 아니다
        self.assertEqual((report["outcome"], self.files()), (source_policy.FACT_NOT_READY_OUTCOME, before))
        value, report, _out = self.run_ok(draft_flow=True)
        self.assertEqual(report["outcome"], "DRAFT_CREATED")                                           # 대조군
        self.assertEqual(len(self.posts()), 1)
        for key in ("flow", "branch", "paths"):
            self.assertIn(key, self.history()[0])

    def test_the_approval_pr_body_calls_a_calculated_draft_what_it_is_and_every_other_body_keeps_the_old_words(self):
        """D-254: 승인 PR 본문은 사람이 병합 전에 읽는다. 규칙 기반 계산 글에 'AI 가 만든 초안'·AI 고지문 점검 줄이 나오면 거짓 안내다. 글 머리말과 이력 항목에 표식이 **둘 다** 있을 때만 문구를 바꾸고
        (하나라도 없으면 옛 문구 — AI 미사용이라고 잘못 말하지 않는 쪽), 피드 글(표식 없음)의 본문은 바이트까지 그대로다.
        N1(D-320): 같은 본문의 '제목 유사도' 줄도 하지 않은 검사를 했다고 안내하지 않도록 계산 글에서만 '해당 없음' 이고 표식이 하나뿐인 본문·피드 글은 옛 줄이다."""
        value, _report, _out = self.run_ok()
        entry = self.history()[0]
        text = (self.work / value[0]).read_text(encoding="utf-8")
        self.assertTrue(drafts.is_fact_draft(entry, text))
        body = drafts.build_pr_body(entry, text, None, owner="owner")
        lines = body.splitlines()
        self.assertEqual(lines[-1], "- 이 글은 계산으로 만든 초안(AI 미사용)이고 이 PR 은 `[Chance] 글 자동 작성·게시` 워크플로가 만들었습니다.")
        self.assertNotIn("AI 가 만든 초안", body)
        self.assertNotIn("출처 고지문", body)                                                           # 계산 글에는 AI 고지문 점검 줄이 없다
        self.assertIn("- 본문 분량: 한국어 ", body)                                                       # 다른 점검 줄은 그대로
        self.assertIn("- 글 끝 출처 목록: 한국어 ", body)
        self.assertEqual(lines.count(FACT_SIMILARITY_LINE), 1)                                         # N1: 하지 않은 제목 유사도 검사를 했다고 안내하지 않는다 — '해당 없음' 한 줄
        self.assertNotIn(FEED_SIMILARITY_LINE, body)
        self.assertNotIn("생성기가 검사함", body)
        self.assertEqual(len([line for line in lines if line.startswith("- 제목 유사도")]), 1)
        two_languages = drafts.build_pr_body(entry, text, text, owner="owner")                          # 두 언어 모양으로 불러도 계산 글이면 같은 줄이다(표식이 정하고 언어 수가 정하지 않는다)
        self.assertEqual(two_languages.splitlines().count(FACT_SIMILARITY_LINE), 1)
        old = "- 이 글은 AI 가 만든 초안이고 이 PR 은 `[Chance] 글 자동 작성·게시` 워크플로가 만들었습니다."
        without_text_mark = text.replace('provenance: "facts"\n', "")
        without_entry_mark = {key: item for key, item in entry.items() if key != "provenance"}
        wrong_entry_mark = dict(entry, provenance="other")
        for label, pair in (("글에 표식이 없다", (entry, without_text_mark)), ("이력에 표식이 없다", (without_entry_mark, text)), ("둘 다 없다(피드 글)", (without_entry_mark, without_text_mark)),
                            ("이력의 표식 값이 다르다", (wrong_entry_mark, text)), ("이력이 사전이 아니다", ("문자열", text)), ("글이 없다", (entry, None))):
            with self.subTest(case=label):
                self.assertFalse(drafts.is_fact_draft(*pair))
                plain = drafts.build_pr_body(pair[0], pair[1], None, owner="owner")
                self.assertEqual(plain.splitlines()[-1], old)
                self.assertIn("- 출처 고지문(AI 작성·검토 안 받음 안내): 한국어 ", plain)
                self.assertNotIn("AI 미사용", plain)
                self.assertEqual(plain.splitlines().count(FEED_SIMILARITY_LINE), 1)                    # N1: 표식이 하나만 있거나 값이 달라도(피드 글 포함) 옛 줄 그대로
                self.assertNotIn(FACT_SIMILARITY_LINE, plain)
                self.assertNotIn("해당 없음", plain)

    def test_a_calculated_body_differs_from_the_feed_body_of_the_same_text_in_exactly_three_places(self):
        """N1: 같은 글·같은 이력 항목에서 표식만 뺀 피드 모양 본문과 계산 글 본문을 줄 단위로 견준다 — 다른 곳은 정확히 셋(AI 고지문 점검 줄이 빠짐·제목 유사도 줄이 '해당 없음'·마지막 안내 줄)이고
        나머지 줄은 하나도 다르지 않다. 계산 글에서만 바뀐다는 것(피드 글 본문은 바이트까지 그대로)을 줄 단위로 못박는다."""
        value, _report, _out = self.run_ok()
        entry = self.history()[0]
        text = (self.work / value[0]).read_text(encoding="utf-8")
        fact_lines = drafts.build_pr_body(entry, text, None, owner="owner").splitlines()
        feed_entry = {key: item for key, item in entry.items() if key != "provenance"}
        feed_lines = drafts.build_pr_body(feed_entry, text.replace('provenance: "facts"\n', ""), None, owner="owner").splitlines()
        self.assertNotEqual(fact_lines, feed_lines)
        expected, notice, similarity, last = [], 0, 0, 0
        for line in feed_lines:
            if line.startswith("- 출처 고지문(AI 작성·검토 안 받음 안내)"):
                notice += 1
                continue                                                                                  # ① 이 줄은 계산 글에 없다
            if line == FEED_SIMILARITY_LINE:
                similarity, line = similarity + 1, FACT_SIMILARITY_LINE                                   # ② 이 줄만 바뀐다
            elif line.startswith("- 이 글은 AI 가 만든 초안이고"):
                last, line = last + 1, "- 이 글은 계산으로 만든 초안(AI 미사용)이고 이 PR 은 `[Chance] 글 자동 작성·게시` 워크플로가 만들었습니다."      # ③
            expected.append(line)
        self.assertEqual((notice, similarity, last), (1, 1, 1))
        self.assertEqual(fact_lines, expected)
        self.assertEqual(len(fact_lines), len(feed_lines) - 1)

    def test_a_manual_run_without_a_slot_uses_a_time_stamped_branch(self):
        _value, _report, _out = self.run_ok(slot=None)
        entry = self.history()[0]
        self.assertIsNone(entry["slot"])
        self.assertEqual(entry["branch"], "ai/draft/2026-11-10-m101200")

    def test_no_feed_page_model_prompt_photo_or_search_function_is_ever_called_and_the_model_call_count_is_zero(self):
        urlopen = mock.patch("urllib.request.urlopen", side_effect=AssertionError("네트워크 직접 접속"))
        guard = mock.patch.object(ai_guard, "assert_clean", side_effect=AssertionError("AI 입구 방벽에 걸렸다 — 이 분기는 AI 입력을 만들지 않는다"))      # 방벽을 켠 채로도(부르면 실패) 걸리지 않는다
        with urlopen, guard as barrier, mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0}):
            _value, _report, _out = self.run_ok()
            self.assertEqual(g.GEMINI_CALLS, {"attempts": 0, "failed": 0})
            barrier.assert_not_called()
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


class HistoryReadTest(FB.FactEnv):
    """D7(독립 검증 S2b): Fact 경로는 이력으로 차례를 정하고 끝에 이력 전체를 다시 쓴다 — 깨진 이력을 빈 기록으로 읽고 진행하면 같은 글감을 되풀이하고 이력을 새 항목 하나로 덮어쓴다.
    이제 진입에서 엄격히 읽어(잠금 가드가 쓰는 `publish_lock.read_history_strict`) 읽을 수 없으면 글을 만들지 않고 이유 한 줄로 정상 종료한다. 피드 경로는 이전 그대로다(빈 기록으로 진행)."""
    BROKEN = (b"{broken", b"", b"   \n", b"null", b"{}", b'{"a": 1}', b'"text"', b"5", b"NaN", b"[1, 2", b"[]]", b"\xef\xbb\xbf[]", b"\xff\xfe[]")

    def assert_stopped(self, out, error, value, report):
        self.assertIsNone(error, error)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], source_policy.FACT_NOT_READY_OUTCOME)
        self.assertEqual((self.noaa.factory_calls, self.noaa.calls), (0, []))                              # 요청 도구도 만들지 않았다
        lines = [line for line in out.splitlines() if line.startswith("[구조화 Fact] 글을 만들지 않습니다")]
        self.assertEqual(len(lines), 1, out)                                                               # 이유는 한 줄
        self.assertIn("history.json", lines[0])
        for spy in self.spies.values():
            spy.assert_not_called()

    def test_an_unreadable_history_stops_the_run_and_leaves_the_file_as_it_was(self):
        path = self.work / "history.json"
        for raw in self.BROKEN:
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                value, report, out, error = self.run_branch()
                self.assert_stopped(out, error, value, report)
                self.assertEqual(path.read_bytes(), raw)                                                    # 깨진 이력을 덮어쓰지 않는다
                self.assertEqual(self.files(), ["history.json"])                                             # 글 파일도 없다

    def test_the_generators_strict_reader_agrees_with_the_lock_guards_on_every_input(self):
        """D-292: 생성기의 `read_history_strict` 는 잠금 가드의 같은 이름 함수와 같은 규칙이다 — 두 함수가 같은 입력(깨진 모양 전부·좋은 모양·없는 파일·폴더)에서 같은 결과를 낸다(규칙이 따로 어긋나지 않게)."""
        path = self.work / "history.json"
        for raw in (*self.BROKEN, b"[]", b" [ ] \n", b'[{"a": 1}, "x", null]', b"[1, 2]", b'[{"date": "2026-11-01"}]'):
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                self.assertEqual(g.read_history_strict(), publish_lock.read_history_strict(path))
        path.unlink()
        self.assertEqual((g.read_history_strict(), publish_lock.read_history_strict(path)), ([], []))          # 없는 파일 = 아직 글이 없다
        path.mkdir()
        self.assertEqual((g.read_history_strict(), publish_lock.read_history_strict(path)), (None, None))      # 폴더는 읽을 수 없다

    def test_a_start_condition_problem_is_reported_before_the_history_problem_and_the_history_is_not_even_read_then(self):
        """D-292: 이력은 시작 점검을 통과한 뒤에 읽는다 — 제공처가 꺼져 있고 이력도 깨졌으면 이유 한 줄은 제공처 이야기이고(지금 저장소의 실제 상태에서 이유가 바뀌지 않는다) 이력 파일은 그대로다."""
        self.use(FB.facts_registry(), FB.sources_registry(enabled=False))
        path = self.work / "history.json"
        path.write_bytes(b"{broken")
        value, report, out, error = self.run_branch()
        self.assertIsNone(error, error)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], source_policy.FACT_NOT_READY_OUTCOME)
        lines = [line for line in out.splitlines() if line.startswith("[구조화 Fact] 글을 만들지 않습니다")]
        self.assertEqual(len(lines), 1, out)
        self.assertIn(FB.PROVIDER_ID, lines[0])
        self.assertNotIn("history.json", lines[0])
        self.assertEqual(path.read_bytes(), b"{broken")

    def test_a_history_path_that_is_a_folder_stops_the_run_too(self):
        (self.work / "history.json").mkdir()
        value, report, out, error = self.run_branch()
        self.assert_stopped(out, error, value, report)
        self.assertTrue((self.work / "history.json").is_dir())
        self.assertEqual(self.posts(), [])

    def test_a_missing_or_empty_list_history_is_a_first_run_and_goes_on(self):
        for raw in (None, b"[]", b" [ ] \n"):
            with self.subTest(raw=raw):
                for leftover in self.work.glob("history.json"):
                    leftover.unlink()
                for post in self.posts():
                    post.unlink()
                if raw is not None:
                    (self.work / "history.json").write_bytes(raw)
                value, report, out, error = self.run_branch()
                self.assertIsNone(error, error)
                self.assertIsNotNone(value, (report, out))
                self.assertEqual(report["outcome"], "DRAFT_CREATED")
                self.assertEqual(len(self.history()), 1)

    def test_a_readable_list_with_garbage_entries_goes_on_and_keeps_every_old_entry(self):
        old = [1, "문자열 항목", None, {"date": "깨진 날짜", "topic": "옛 글"}, {"date": "2026-10-01", "topic": "옛 글 둘"}]
        self.set_history(old)
        value, report, out, error = self.run_branch()
        self.assertIsNone(error, error)
        self.assertIsNotNone(value)
        after = self.history()
        self.assertEqual(after[:len(old)], old)                                                              # 읽을 수 있는 이력의 옛 항목은 하나도 잃지 않는다
        self.assertEqual(len(after), len(old) + 1)

    def test_the_feed_path_is_unchanged_it_still_reads_a_broken_history_as_empty_and_goes_on(self):
        self.use(FB.facts_registry(content_source=None), FB.sources_registry())
        self.patch_value(g, "fetch_news_items", lambda editorial_lane=None, stats=None, deadline=None, clock=None: [])
        path = self.work / "history.json"
        path.write_bytes(b"{broken")
        value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], "ALL_LANES_EMPTY")                                              # 피드 경로의 결과 코드 그대로
        self.assertIn("history.json 읽기 실패, 빈 기록으로 진행", out)                                       # 피드 경로의 옛 동작: 깨진 이력은 빈 기록으로 읽고 계속한다
        self.assertEqual(path.read_bytes(), b"{broken")


class HistoryLimitTest(FB.FactEnv):
    """D-256: `write_history` 는 마지막 200개만 남기고 읽을 수 없는 날짜는 그 제품을 막는 쪽으로 읽힌다(`made_from_history`). 이력이 가득 찬 상태에서도 후보 선택은 이력에 남은 Fact 글로 가장 오래 전에 낸 글감을
    고르고 새 글을 더하면 가장 오래된 항목 하나만 밀려난다. 한 글감의 마지막 글이 밀려나면 그 글감은 낸 적 없는 것으로 읽혀 먼저 차례가 온다(문서화한 한계 — 주 1–2편이면 마지막 글이 밀려나려면 새 항목이 200개 쌓여야 한다)."""

    def filler(self, count):
        start = datetime.date(2025, 1, 1)
        return [{"date": (start + datetime.timedelta(days=index)).isoformat(), "topic": f"옛 글 {index}", "kr_title": f"옛 글 {index}"} for index in range(count)]

    def fact_entry(self, spec_id, day, **extra):
        spec = K.SPEC_BY_ID[spec_id]
        item = {"date": day, "topic": f"지난 글 {spec_id}", "content_source": "facts", "candidate_key": K.candidate_key(spec, day), "dedupe_key": f"old|{spec_id}|{day}", "provenance": "facts"}
        item.update(extra)
        return item

    def test_a_full_history_still_picks_the_subject_made_longest_ago_and_pushes_out_only_the_oldest_entry(self):
        recent = [self.fact_entry("flares_weekly", "2026-10-05"), self.fact_entry("scales_weekly", "2026-10-12"), self.fact_entry("kp_weekly", "2026-10-19"),
                  self.fact_entry("sunspot_daily_monthly", "2026-10-26"), self.fact_entry("sunspot_monthly_monthly", "2026-10-27")]
        history = self.filler(195) + recent
        self.assertEqual(len(history), 200)
        self.set_history(history)
        value, report, out, error = self.run_branch()
        self.assertIsNone(error, error)
        self.assertIsNotNone(value, (report, out))
        after = self.history()
        self.assertEqual(len(after), 200)                                                                     # 한 편을 더해도 200개 — 가장 오래된 하나가 밀려났다
        self.assertEqual(after[:-1], history[1:])
        self.assertEqual(after[-1]["candidate_key"], "space_weather.kp_storm_weekly:2026-W46")              # 한 번도 안 낸 글감이 맨 앞(Kp 묶음에서 안 낸 쪽) — 월 글감 둘은 28일 간격에 막혀 있다
        self.assertEqual(self.noaa.products(), ["kp_estimated"])

    def test_the_same_product_is_still_held_back_by_the_window_when_the_history_is_full(self):
        recent = [self.fact_entry(name, "2026-10-05") for name in ("flares_weekly", "scales_weekly", "kp_weekly", "sunspot_daily_monthly", "sunspot_monthly_monthly")] + [self.fact_entry("kp_storm_weekly", "2026-11-06")]
        history = self.filler(194) + recent
        self.assertEqual(len(history), 200)
        self.set_history(history)
        value, report, out, error = self.run_branch()
        self.assertIsNone(error, error)
        self.assertIsNotNone(value, (report, out))
        self.assertEqual(self.history()[-1]["candidate_key"], "space_weather.flares_weekly:2026-W46")        # 나흘 전에 Kp 를 읽은 글이 있어 Kp 두 글감은 7일 간격에 막히고 다음 차례인 플레어 글이 나온다
        self.assertEqual(self.noaa.products(), ["xray_flares"])                                               # Kp 제품은 부르지도 않았다

    def test_a_subject_whose_only_entry_is_pushed_out_reads_as_never_made_which_is_the_documented_limit(self):
        old = self.fact_entry("scales_weekly", "2026-01-05")
        history = [old] + self.filler(199)
        self.assertEqual(len(history), 200)
        self.assertEqual(set(K.made_from_history(history).last), {"scales_weekly"})
        self.set_history(history)
        value, report, out, error = self.run_branch()
        self.assertIsNone(error, error)
        self.assertIsNotNone(value)
        after = self.history()
        self.assertEqual((len(after), old in after), (200, False))                                           # 가장 오래된 항목(그 글감의 마지막 글)이 밀려났다
        self.assertEqual(after[:-1], history[1:])                                                            # 그 밖의 항목은 그대로다
        made = K.made_from_history(after)
        self.assertNotIn("scales_weekly", made.last)                                                         # 낸 적 없는 것으로 읽힌다 — 막는 쪽이 아니라 먼저 차례가 오는 쪽으로 틀린다
        self.assertEqual(set(made.last), {after[-1]["candidate_key"].split(":")[0].replace("space_weather.", "")})

    def test_a_fact_entry_with_a_broken_date_blocks_its_product_and_is_kept_as_it_is(self):
        broken = self.fact_entry("kp_weekly", "2026-10-05", date="깨진 날짜")
        self.set_history(self.filler(10) + [broken])
        value, report, out, error = self.run_branch()
        self.assertIsNone(error, error)
        self.assertIsNotNone(value)
        after = self.history()
        self.assertIn(broken, after)                                                                          # 고치지도 지우지도 않는다 — 사람이 고칠 때까지 그 제품은 막힌다
        self.assertEqual(after[-1]["candidate_key"], "space_weather.flares_weekly:2026-W46")                # Kp 묶음이 막혀 안 낸 글감 중 차례가 가장 앞선 플레어 글이 나온다
        self.assertEqual(self.noaa.products(), ["xray_flares"])


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

    def test_a_response_that_drips_past_the_deadline_closes_the_product_and_never_makes_a_post(self):
        """D2: 실제 연결 코드(`_fact_fetch`)에 천천히 흘리는 응답 대역과 가짜 시계를 물린다 — 제품마다 마감을 넘겨 `OPENER_FAILED` 로 닫히고(세 번 실패한 뒤의 제품은 호출 예산이 막는다) 글·이력은 없다."""
        clock, responses = FakeClock(), []

        def slow(url, *, timeout, max_bytes):
            responses.append(DrippingResponse(clock, itertools.repeat(b"x"), 19))
            return g._fact_fetch(DrippingOpener(responses[-1], clock), url, timeout, max_bytes, clock=clock)
        self.patch_value(g, "make_fact_transport", lambda sources: slow)
        value, report, out, error = self.run_branch()
        self.assertIsNone(error)
        self.assertIsNone(value)
        self.assertEqual(report["outcome"], source_policy.FACT_ALL_SKIPPED_OUTCOME)
        self.assertEqual(self.files(), [])
        notes = report["fact_notes"]
        self.assertEqual(len(notes), 6)
        self.assertTrue(all(note.endswith(("ADAPTER:OPENER_FAILED", "ADAPTER:BUDGET_DENIED")) for note in notes), notes)
        self.assertEqual(sum(note.endswith("ADAPTER:OPENER_FAILED") for note in notes), 4)                # Kp 두 글감(같은 제품 — 실패를 기억한다)·플레어·등급
        self.assertEqual(len(responses), 3)                                                                # 세 제품만 불렀고 세 번째 실패 뒤의 월 글감 둘은 호출이 나가지 않았다
        self.assertTrue(all(len(response.asked) == 4 for response in responses))

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
                piece, self.body = self.body[:size], self.body[size:]          # 흐르는 응답처럼 읽은 만큼 줄어든다(S2BFIX: 응답을 조각으로 읽으므로 같은 앞부분을 되풀이해 돌려주는 대역으로는 시험할 수 없다)
                return piece

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
            wire = gzipped if response.headers["Content-Encoding"] == "gzip" else raw
            self.assertEqual(response.read_sizes, [1001, 1001 - len(wire)])                               # 첫 요청이 한 바이트 더(max_bytes + 1)이고 그 뒤는 남은 몫만 — 마지막 빈 조각이 끝을 알린다(S2BFIX: 전에는 한 번에 [1001])
        self.assertTrue(packed)
        bomb = zlib.compressobj(wbits=31)
        zipped = bomb.compress(b"0" * 5_000_000) + bomb.flush()
        fake = Opener(Response(zipped, "gzip"))
        with mock.patch.object(egress, "build_checked_opener", lambda *args, **kwargs: fake):
            body = g.make_fact_transport(self.sources)("https://services.swpc.noaa.gov/x", timeout=7, max_bytes=1000)
        self.assertEqual(len(body), 1001)                                                                 # 압축을 푼 크기가 한도 + 1 에서 잘려 어댑터가 거절한다(압축 폭탄 방어)
        with self.assertRaises(ValueError):
            g._fact_gunzip(b"not gzip at all", 100)


class ResponseDeadlineTest(unittest.TestCase):
    """D2(독립 검증 S2b): `timeout` 은 소켓 연산마다의 시간이라 천천히 흘리는 응답은 오래 이어질 수 있었다 — 소켓 읽기마다 19초씩 걸리면 상한(1 MiB)까지 사실상 끝나지 않고 워크플로 시간 제한이 끊을 때까지 간다.
    이제 응답을 조각으로 읽으며 요청 시작부터의 경과가 마감(60초)을 **넘으면** 닫는다. 가짜 응답·가짜 시계만 쓴다(소켓·진짜 시간에 기대지 않는다 — 검증자의 slow_drip 도구와 같은 원리)."""
    URL = "https://services.swpc.noaa.gov/products/noaa-scales.json"
    KINDS = (DrippingResponse, ReadOnlyResponse)

    def setup_fetch(self, pieces, step, kind=DrippingResponse, open_seconds=0, encoding=""):
        clock = FakeClock()
        response = kind(clock, pieces, step, encoding)
        return DrippingOpener(response, clock, open_seconds), response, clock

    def fetch(self, opener, clock, max_bytes=1000, deadline=60):
        return g._fact_fetch(opener, self.URL, 20, max_bytes, clock=clock, deadline=deadline)

    def test_a_body_that_arrives_in_time_comes_back_whole_from_either_kind_of_response(self):
        for kind in self.KINDS:
            with self.subTest(kind=kind.__name__):
                opener, response, clock = self.setup_fetch([b"ab", b"cd", b"ef"], 1, kind)
                self.assertEqual(self.fetch(opener, clock), b"abcdef")
                self.assertEqual(response.asked, [1001, 999, 997, 995])                                  # 조각마다 남은 만큼(max_bytes + 1 에서 받은 몫을 뺀 것)만 요청하고 마지막은 빈 조각(끝)이다
                self.assertEqual(len(opener.requests), 1)
                request, socket_timeout = opener.requests[0]
                self.assertEqual(socket_timeout, 20)                                                      # 소켓 timeout 은 그대로 넘어간다 — 마감은 그 위에 더한 것이다
                self.assertEqual(request.get_header("Accept-encoding"), "gzip")

    def test_the_deadline_is_looked_at_before_every_read_and_a_slow_drip_is_closed_at_it(self):
        """한 번 읽는 데 19초씩(소켓 timeout 20초 아래) 걸리는 끝없는 응답 — 마감이 없으면 상한까지 끝나지 않는다. 읽기 앞마다 경과를 보니 네 번째 읽기까지(경과 0·19·38·57초) 하고 다섯 번째 앞(76초)에서 닫힌다."""
        for kind in self.KINDS:
            with self.subTest(kind=kind.__name__):
                opener, response, clock = self.setup_fetch(itertools.repeat(b"x"), 19, kind)
                with self.assertRaises(TimeoutError) as caught:
                    self.fetch(opener, clock)
                self.assertEqual(len(response.asked), 4)
                self.assertEqual(str(caught.exception), "응답을 60초 안에 다 받지 못했습니다")             # 고정 문장과 숫자뿐 — 주소·받은 응답 글자를 싣지 않는다

    def test_exactly_the_deadline_passes_and_the_next_instant_fails(self):
        """마감 직전·정확히 마감·직후(연결·머리글에 걸린 시간 open_seconds 로 첫 읽기 앞의 경과를 정한다): 59.999 와 60 은 통과하고 60.001 부터는 첫 조각을 읽기 전에 닫힌다 — 시작은 요청을 열기 전이다."""
        for seconds, passes in ((0, True), (59.999, True), (60, True), (60.001, False), (61, False), (500, False)):
            with self.subTest(open_seconds=seconds):
                opener, response, clock = self.setup_fetch([b"abc"], 0, open_seconds=seconds)
                if passes:
                    self.assertEqual(self.fetch(opener, clock), b"abc")
                else:
                    with self.assertRaises(TimeoutError):
                        self.fetch(opener, clock)
                    self.assertEqual(response.asked, [])                                                  # 한 바이트도 읽지 않고 닫았다

    def test_the_deadline_also_counts_the_time_the_reads_themselves_take(self):
        """한 번 읽을 때마다 20초 — 읽기 앞의 경과는 0·20·40·60. 네 번째 읽기(경과 정확히 60초)까지는 하고 그 뒤 경과 80초 앞에서 닫힌다. 본문이 세 조각이면 네 번째 읽기가 끝을 알려 통과하고 네 조각이면 닫힌다."""
        opener, response, clock = self.setup_fetch([b"a", b"b", b"c"], 20)
        self.assertEqual(self.fetch(opener, clock), b"abc")
        self.assertEqual(len(response.asked), 4)
        opener, response, clock = self.setup_fetch([b"a", b"b", b"c", b"d"], 20)
        with self.assertRaises(TimeoutError):
            self.fetch(opener, clock)
        self.assertEqual(len(response.asked), 4)

    def test_the_socket_read_once_function_is_preferred_and_read_is_only_the_fallback(self):
        """진짜 HTTPResponse 의 `read(n)` 은 n 바이트가 찰 때까지 안에서 기다려 한 바이트씩 흘리는 응답에서는 마감을 볼 수 없다 — 소켓 읽기를 한 번만 하는 `read1` 이 있으면 그것으로만 읽는다(없으면 read 로 물러난다 — 위 시험)."""
        class Read1Only(DrippingResponse):
            read1 = DrippingResponse._next

            def read(self, size=-1):
                raise AssertionError("read1 이 있는데 read 로 읽었다")
        opener, response, clock = self.setup_fetch([b"ab", b"cd"], 1, Read1Only)
        self.assertEqual(self.fetch(opener, clock), b"abcd")
        self.assertEqual(len(response.asked), 3)

    def test_each_read_asks_for_at_most_one_chunk_and_never_past_the_limit(self):
        for kind in self.KINDS:
            with self.subTest(kind=kind.__name__):
                opener, response, clock = self.setup_fetch([b"x" * 300000], 1, kind)
                body = self.fetch(opener, clock, max_bytes=200000)
                self.assertEqual(len(body), 200001)                                                       # max_bytes + 1 에서 멈춘다(어댑터가 상한 초과로 거절한다)
                self.assertEqual(response.asked, [65536, 65536, 65536, 3393])
                self.assertTrue(all(size <= g.FACT_READ_CHUNK_BYTES for size in response.asked))

    def test_a_gzip_body_is_unpacked_after_the_pieces_are_joined_and_a_bomb_is_still_cut(self):
        raw = b'{"a": 1}' * 50
        packer = zlib.compressobj(wbits=31)
        packed = packer.compress(raw) + packer.flush()
        opener, response, clock = self.setup_fetch([packed[:10], packed[10:30], packed[30:]], 1, encoding="gzip")
        self.assertEqual(self.fetch(opener, clock), raw)
        bomb = zlib.compressobj(wbits=31)
        zipped = bomb.compress(b"0" * 5_000_000) + bomb.flush()
        opener, response, clock = self.setup_fetch([zipped[start:start + 100] for start in range(0, len(zipped), 100)], 0, encoding="gzip")
        self.assertEqual(len(self.fetch(opener, clock)), 1001)                                             # 압축을 푼 크기가 한도 + 1 에서 잘린다(이전과 같다)

    def test_the_default_clock_and_deadline_are_the_modules_own_and_are_read_when_called(self):
        clock = FakeClock()
        response = DrippingResponse(clock, itertools.repeat(b"x"), 3)
        with mock.patch.object(g, "fact_clock", clock), mock.patch.object(g, "FACT_READ_DEADLINE_SECONDS", 5):
            with self.assertRaises(TimeoutError):
                g._fact_fetch(DrippingOpener(response, clock), self.URL, 20, 1000)
        self.assertEqual(len(response.asked), 2)                                                          # 경과 0·3초에서 읽고 6초(5초 초과) 앞에서 닫혔다
        self.assertEqual((g.FACT_READ_DEADLINE_SECONDS, g.FACT_READ_CHUNK_BYTES), (60, 65536))             # 기본값은 60초·64KiB
        self.assertIsInstance(g.fact_clock(), float)
        self.assertLessEqual(g.fact_clock(), g.fact_clock())                                               # 단조 시계다

    def test_through_the_real_transport_and_the_adapter_a_timeout_is_an_opener_failure_that_counts_against_the_run(self):
        clock = FakeClock()
        response = DrippingResponse(clock, itertools.repeat(b"x"), 19)
        sources = source_registry.build_registry(FB.sources_registry(), "2026-11-10")
        provider = sources.get(FB.PROVIDER_ID)
        access = fact_supply.api_access(provider)
        with mock.patch.object(egress, "build_checked_opener", lambda *args, **kwargs: DrippingOpener(response, clock)), mock.patch.object(g, "fact_clock", clock):
            transport = g.make_fact_transport(sources)
            opener, budget = g.fact_opener(sources, provider, access, transport)
            with self.assertRaises(fact_supply.AdapterError) as caught:
                N.NoaaSwpcAdapter(provider, "scales").fetch(access, {}, opener)
        self.assertEqual(caught.exception.code, "OPENER_FAILED")
        self.assertEqual((budget.calls, budget.failures), (1, 1))                                          # 호출 예산은 실패로 센다(세 번이면 이 실행의 나머지 호출이 멈춘다)
        self.assertEqual(len(response.asked), 4)
        self.assertNotIn("http", str(caught.exception))


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


class FactZoneExternalReadTest(unittest.TestCase):
    """D5(독립 검증 S2b): 정적 규칙 AF4·AF8 은 **AI 이름**만 본다 — AI 가 아닌 외부 읽기(사진·기사 읽기)를 Fact 구역이 불러도 위반으로 읽지 않는다(검증자가 구역에 한 줄씩 넣은 `pick_images(1)`·`search_unsplash`·
    `trigger_download`·`url_ok`·`fetch_pool_photo`·`_fetch_source_excerpt`·`_resolve_article_url`·`fetch_news_items()` 는 모두 위반 0 이었다). 막는 것은 FactEnv 의 동적 감시자(12개 이름)뿐이라 드물게 도는 갈래(예외 경로)에
    숨은 호출은 못 본다. 이 시험이 Fact 구역(생성기의 `fact_*`·`_fact_*`·`make_fact_*`·`generate_fact_*`, 공급 모듈 `fact_supply` 전체, 그림자 분기의 `run_facts`·`facts_branch_on`)의 소스를 AST 로 읽어 그 이름이
    호출·참조·`getattr` 에 글자로 넘기는 이름 어디에도 없음을 단언한다. 구역 이름이 바뀌어 검사 대상이 조용히 비지 않게 함수 개수 하한도 단언한다."""
    ZONE = NoNamedInnerFunctionTest.ZONE
    PHOTO_READS = frozenset({"pick_images", "search_unsplash", "trigger_download", "url_ok", "fetch_pool_photo", "_api_request", "_note_unsplash_rate", "_record_photo", "_forget_photo", "credit_line_for",
                             "fix_images", "repair", "UNSPLASH_KEY", "STUB_UNSPLASH", "UNSPLASH_RATE", "IMAGE_POOL"})
    ARTICLE_READS = frozenset({"fetch_news_items", "_fetch_source_excerpt", "_resolve_article_url", "pick_topic_candidates", "iter_candidate_lanes", "collect_candidates", "NEWS_SOURCES", "urlopen"})
    EXTERNAL_READS = PHOTO_READS | ARTICLE_READS | frozenset(FB.AI_NAMES)
    CLOCK_ATTRIBUTES = frozenset({"monotonic", "monotonic_ns", "perf_counter", "process_time", "time", "time_ns", "utcnow", "now", "today", "sleep"})

    def read(self, rel):
        return (_bootstrap.ROOT / rel).read_text(encoding="utf-8")

    def zone_functions(self):
        generated = [node for node in ast.parse(self.read("generator.py")).body if isinstance(node, ast.FunctionDef) and node.name.startswith(self.ZONE)]
        supply = [node for node in ast.walk(ast.parse(self.read("pipeline/fact_supply.py"))) if isinstance(node, ast.FunctionDef)]
        shadow = [node for node in ast.parse(self.read("pipeline/shadow_run.py")).body if isinstance(node, ast.FunctionDef) and node.name in ("run_facts", "facts_branch_on")]
        return generated, supply, shadow

    def names_in(self, node):
        """함수 하나 안에서 읽은 이름 전부: 맨 이름·속성 이름·이름처럼 생긴 글자 상수(`getattr(g, "이름")`·`globals()["이름"]`)."""
        found = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                found.add(child.id)
            elif isinstance(child, ast.Attribute):
                found.add(child.attr)
            elif isinstance(child, ast.Constant) and isinstance(child.value, str) and child.value.isidentifier():
                found.add(child.value)
        return found

    def test_the_fact_zone_never_names_a_photo_or_article_read_or_an_ai_function(self):
        generated, supply, shadow = self.zone_functions()
        for node in generated + supply + shadow:
            with self.subTest(function=node.name):
                self.assertEqual(sorted(self.names_in(node) & self.EXTERNAL_READS), [], node.name)

    def test_the_zone_is_really_found_so_the_check_cannot_pass_by_looking_at_nothing(self):
        generated, supply, shadow = self.zone_functions()
        names = {node.name for node in generated}
        self.assertGreaterEqual(len(generated), 15, sorted(names))
        self.assertTrue({"generate_fact_post", "fact_prepare", "fact_check_post", "fact_opener", "fact_context", "fact_history_entry", "make_fact_transport", "_fact_fetch", "_fact_read", "fact_clock"} <= names, sorted(names))
        self.assertGreaterEqual(len(supply), 6, [node.name for node in supply])
        self.assertIn("supply", {node.name for node in supply})
        self.assertEqual(sorted(node.name for node in shadow), ["facts_branch_on", "run_facts"])

    def test_the_scan_really_sees_a_call_a_bare_reference_a_name_given_as_text_and_an_attribute(self):
        sample = ast.parse("def fact_a(g):\n    return g.pick_images([])\n\ndef fact_b():\n    return fetch_news_items\n\ndef fact_c(g):\n    return getattr(g, 'url_ok')\n\n"
                           "def fact_d(opener):\n    return opener.open('x')\n\ndef fact_e(urllib):\n    return urllib.request.urlopen('x')\n")
        found = {node.name: self.names_in(node) & self.EXTERNAL_READS for node in sample.body}
        self.assertEqual(found, {"fact_a": {"pick_images"}, "fact_b": {"fetch_news_items"}, "fact_c": {"url_ok"}, "fact_d": set(), "fact_e": {"urlopen"}})

    def test_every_generator_function_that_opens_an_address_outside_the_zone_is_in_the_list_and_every_listed_name_exists(self):
        """새 외부 읽기 함수가 생성기에 생기면 이 목록에 더해야 한다 — 안 그러면 여기서 빨개진다(목록이 낡아 구역의 검사가 약해지지 않게)."""
        body = ast.parse(self.read("generator.py")).body
        openers = {node.name for node in body if isinstance(node, ast.FunctionDef) and not node.name.startswith(self.ZONE)
                   and any(isinstance(child, ast.Attribute) and child.attr == "urlopen" for child in ast.walk(node))}
        self.assertGreaterEqual(len(openers), 7, sorted(openers))
        self.assertLessEqual(openers, self.EXTERNAL_READS, f"주소를 여는 생성기 함수가 목록에 없다: {sorted(openers - self.EXTERNAL_READS)} — 목록(EXTERNAL_READS)에 더한다")
        defined = {node.name for node in body if isinstance(node, ast.FunctionDef)}
        defined |= {target.id for node in body if isinstance(node, ast.Assign) for target in node.targets if isinstance(target, ast.Name)}
        self.assertEqual(sorted((self.EXTERNAL_READS - {"urlopen"}) - defined), [], "목록에 있는데 생성기에 없는 이름(오타·이름 변경)")

    def test_the_zone_reads_the_clock_in_exactly_one_place_which_a_test_can_replace(self):
        """시계는 생성기 안 한 군데(`fact_clock`)에서만 읽는다 — 마감 판정이 여러 시계를 섞지 않고 시험이 한 군데만 바꾸면 되게(D-290)."""
        generated, supply, shadow = self.zone_functions()
        hits = [(node.name, child.attr) for node in generated + supply + shadow for child in ast.walk(node) if isinstance(child, ast.Attribute) and child.attr in self.CLOCK_ATTRIBUTES]
        self.assertEqual(hits, [("fact_clock", "monotonic")])


if __name__ == "__main__":
    unittest.main()
