"""지역 없는 글 틀(R04–R06)과 제목 정책 시험(S2a): 골든 글 여섯 편(`tests/fixtures/fact_golden_space_*.md` — 모양만 NOAA 응답과 같은 **시험용 가상 값**)·분량·표·출처·모든 숫자가 Fact 에서 옴·직접 계산한 값과 일치·
제목에 값 없음(R01–R06 모두)·꼬리표 상태가 틀리면 글을 만들지 않음·예보 라벨·영향 단정 없음·동률·빠진 날·결정성. 골든 글을 다시 쓰려면 환경 변수 UPDATE_GOLDEN=1 로 실행한다.
네트워크·시계 없이 돈다(난수는 고정 시드로만)."""
import dataclasses
import os
import random
import re
import unittest
from decimal import Decimal
from unittest import mock

import _bootstrap
import fact_helpers as FH
import space_helpers as H

import generator as g       # 읽기 전용(머리말 검사 함수를 불러 같은 규칙을 통과하는지 본다)
from pipeline import calc as C
from pipeline import fact_assembler as A
from pipeline import fact_topics as T
from pipeline import facts as F
from pipeline import recipes as R
from pipeline import recipes_noregion as RN

ROOT = _bootstrap.ROOT
GOLDEN_DIR = ROOT / "tests" / "fixtures"
IMAGE = "https://example.invalid/fact-golden.svg"
LANES = {lane["kr_category"] for lane in g.EDITORIAL_LANES.values()}
TEST_SOURCE_NAME, TEST_SOURCE_URL = "시험용 우주날씨 가상 자료", "https://example.invalid/space-weather-test"
KP_KEY, FLUX_KEY = "space_weather.kp_estimated", "space_weather.xray_flare_flux"
EVENTS = [("2026-11-03T06:15:00Z", "B4.8"), ("2026-11-03T16:40:00Z", "B4.2"), ("2026-11-04T06:54:00Z", "C1.2"), ("2026-11-04T17:34:00Z", "C2.2"), ("2026-11-05T09:10:00Z", "C5.0"),
          ("2026-11-06T04:17:00Z", "M2.1"), ("2026-11-06T22:05:00Z", "C9.9"), ("2026-11-07T11:30:00Z", "M1.4"), ("2026-11-08T03:03:00Z", "B9.0"), ("2026-11-09T18:20:00Z", "C3.3")]
PROBS = {"1": ("60", "15", "10"), "2": ("45", "10", "5"), "3": ("30", "5", "1")}


def golden_cases():
    """골든 글 여섯 편의 입력: 이름 → (Recipe id, 제품, 가상 응답, params)."""
    kp = H.kp_rows("2026-11-02", 8, storm_days=(2,), partial_last=3)
    return {
        "r04_kp": ("R04_NOREGION_SERIES", "kp_estimated", kp, {"key": KP_KEY}),
        "r04_ssn_daily": ("R04_NOREGION_SERIES", "ssn_daily", H.ssn_daily_rows("2026-11-09", 70), {"key": "space_weather.sunspot_daily_swpc"}),
        "r04_ssn_monthly": ("R04_NOREGION_SERIES", "ssn_monthly", H.ssn_monthly_rows("2026-10", 70), {"key": "space_weather.sunspot_monthly_swpc"}),
        "r05_kp_storm": ("R05_THRESHOLD_COUNT", "kp_estimated", kp, {"key": KP_KEY}),
        "r05_flares": ("R05_THRESHOLD_COUNT", "xray_flares", H.flare_rows(EVENTS), {"key": FLUX_KEY}),
        "r06_scales": ("R06_SCALE_OUTLOOK", "scales", H.scales_object(g_now="1", g_forecast=("1", "2", "0"), probs=PROBS), {}),
    }


def test_source(provider_=None):
    return A.SourceInfo(provider_ or H.NoaaProvider(), TEST_SOURCE_NAME, TEST_SOURCE_URL)


def build(name, *, mutate=None, today=H.TODAY, provider_=None, params=None, source=None):
    recipe_id, product_id, rows, base_params = golden_cases()[name]
    record, facts = H.parse_value(product_id, rows)
    facts = list(facts)
    if mutate is not None:
        facts = mutate(facts)
    return A.assemble(RN.NOREGION_RECIPES[recipe_id], facts, today, records=[record], source=source or test_source(provider_), params=base_params if params is None else params)


def revalue(fact, **changes):
    fields = {name: getattr(fact, name) for name in ("provider_id", "source_record_id", "kind", "key", "value", "unit", "as_of", "region", "region_level", "region_label_ko", "region_label_en",
                                                     "label_ko", "label_en", "meta")}
    fields.update(changes)
    return F.Fact.create(*(fields[name] for name in ("provider_id", "source_record_id", "kind", "key", "value", "unit", "as_of", "region", "region_level", "region_label_ko", "region_label_en",
                                                      "label_ko", "label_en", "meta")))


def with_status(facts, key, status):
    return [revalue(f, meta=dict(f.meta, status=status)) if f.key == key else f for f in facts]


def generator_file(post):
    data = {"kr_title": post.title, "kr_category": post.category, "kr_tags": list(post.tags)}
    source = {"link": post.source_url, "source": post.source_name, "publisher_domain": post.source_domain, "title": post.source_name}
    return g.add_discovery_metadata(g._fresh_front_matter(data, "kr", "ko", IMAGE) + post.body_markdown, source), source


def table_rows(post, first_cell=r"20"):
    return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in post.body_markdown.split("\n") if re.match(rf"\| {first_cell}", line)]


def story(post):
    return A.story_of(post.body_markdown)


def kp_daily_maxima(rows):
    """독립 대조: 응답 행에서 하루(8구간이 모두 있는 날)의 최댓값을 일반 파이썬으로 센다."""
    days = {}
    for row in rows:
        days.setdefault(row["time_tag"][:10], []).append(Decimal(str(row["Kp"])))
    return {day: max(values) for day, values in sorted(days.items()) if len(values) == 8}


def kp_rows_with_daily_maxima(maxima, *, first_day="2026-11-02", base=1.0):
    """하루(8구간)마다 한 구간만 maxima 의 값이고 나머지는 base 인 Kp 응답 행 — 날마다의 최대값을 정확히 정한다(maxima[0] 이 first_day 의 값)."""
    rows = H.kp_rows(first_day, len(maxima), partial_last=0, storm_days=())
    for index, row in enumerate(rows):
        day, slot = divmod(index, 8)
        row["Kp"] = maxima[day] if slot == 3 else base
    return rows


INTRO_CALC_RE = re.compile(r"받아 옮긴 구조화 데이터입니다\. (.+?) 같은 값은 이 글이 그 숫자로 직접 계산했습니다\.")
CAUTION_CALC_RE = re.compile(r"(?m)^- 계산한 값: (.+?) 같은 값은 이 글이 직접 계산했습니다\.")


def notice_words(post):
    """공통 안내 두 문장(첫 문단 뒤 자료 안내·'계산한 값' 주의 줄)이 말하는 계산 낱말 목록 — 두 문장 모두 (첫 문단 쪽, 주의 줄 쪽). 없으면 None."""
    first, second = INTRO_CALC_RE.search(post.body_markdown), CAUTION_CALC_RE.search(post.body_markdown)
    return (first.group(1) if first else None, second.group(1) if second else None)


def kp_rows_on_days(day_values, *, base=1.0):
    """(날짜 글자, 그날 최대 Kp) 목록 → 하루 여덟 구간 응답 행. 날짜가 이어지지 않아도 된다(빠진 날을 만들 수 있다)."""
    rows = []
    for day, top in day_values:
        for slot in range(8):
            rows.append({"time_tag": f"{day}T{slot * 3:02d}:00:00", "Kp": top if slot == 3 else base, "a_running": 5, "station_count": 8})
    return rows


class GoldenSpacePostsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.posts = {name: build(name) for name in golden_cases()}

    def test_six_golden_posts_one_per_subject(self):
        self.assertEqual(set(self.posts), {"r04_kp", "r04_ssn_daily", "r04_ssn_monthly", "r05_kp_storm", "r05_flares", "r06_scales"})
        for name, post in self.posts.items():
            with self.subTest(post=name):
                self.assertIsInstance(post, A.AssembledPost, post)
                self.assertEqual((post.lang, post.recipe_version, post.source_name, post.source_url, post.source_domain), ("ko", 1, TEST_SOURCE_NAME, TEST_SOURCE_URL, "example.invalid"))
                self.assertEqual(post.recipe_id, golden_cases()[name][0])
                self.assertEqual(post.category, "과학·환경")
                self.assertIn(post.category, LANES)
                self.assertTrue(post.tags and len(post.tags) <= 6 and len(set(post.tags)) == len(post.tags))
                for tag in post.tags:
                    self.assertTrue(0 < len(tag) <= 20 and not re.search(r"\d", tag), tag)
                self.assertRegex(post.dedupe_key, rf"\A{post.recipe_id}\|space_weather\.[a-z_]+\|-\|\d{{4}}-\d{{2}}(?:-\d{{2}})?\Z")
                self.assertGreaterEqual(len(post.formulas), 2)

    def test_the_golden_files_match_byte_for_byte(self):
        for name, post in self.posts.items():
            content, _source = generator_file(post)
            path = GOLDEN_DIR / f"fact_golden_space_{name}.md"
            if os.environ.get("UPDATE_GOLDEN") == "1":
                path.write_text(content, encoding="utf-8", newline="\n")
            with self.subTest(post=name):
                self.assertTrue(path.exists(), f"{path.name} 이 없다 — UPDATE_GOLDEN=1 로 만든다")
                self.assertEqual(path.read_text(encoding="utf-8"), content)
                self.assertIn("시험용", content)
                self.assertIn("실제 기관의 자료가 아닙니다", content)
                self.assertIn("https://example.invalid/", content)
                self.assertNotIn("{{", content)
                self.assertNotIn("{%", content)

    def test_the_body_clears_the_length_floor_the_skeleton_and_the_generator_rules(self):
        for name, post in self.posts.items():
            content, source = generator_file(post)
            body = post.body_markdown
            with self.subTest(post=name):
                self.assertGreaterEqual(A.readable_chars(story(post)), R.MIN_STORY_CHARS)
                g._validate_editorial_body(content, "kr", post.source_url)
                self.assertEqual(g.front_matter_problems(content, source), [])
                self.assertEqual(tuple(re.findall(r"(?m)^## (.+)$", body)), R.SECTION_ORDER)
                self.assertTrue(body.startswith(post.description + "\n\n"))
                self.assertGreaterEqual(len(re.findall(r"(?m)^\|(?: :?-{3,}:? \|)+$", body)), 1)
                self.assertEqual(content.count("## 출처"), 1)
                sources = body.split("## 출처\n")[1]
                self.assertIn(f"- [{TEST_SOURCE_NAME}]({TEST_SOURCE_URL}) — 열람 2026년 11월 10일", sources)
                self.assertEqual(sources.count("- 이용 조건: "), 1)
                self.assertIn(f"- 이용 조건: {H.TEST_TEMPLATE}", sources)
                self.assertIn("- 제공처 안내: 이 글은 제공처가 만든 값만 쓰고", story(post))
                self.assertIn("**이 글의 해석**:", story(post))
                self.assertEqual(A.post_problems(post, allowed_latin={"NOAA", "SWPC", "GOES", "Kp", "UTC", "nW"}), [])

    def test_every_number_in_the_story_comes_from_a_fact_or_a_calculation(self):
        for name, post in self.posts.items():
            with self.subTest(post=name):
                found = set(A.number_tokens(story(post)))
                self.assertTrue(found)
                self.assertLessEqual(found, A.traceable_numbers(post))
                self.assertLessEqual(found, set(A.number_tokens(post.evidence_text)))
                self.assertEqual(F.untraced_numbers(post.template_markdown), [])
                self.assertLessEqual(set(A.number_tokens(post.title + "\n" + post.description)), A.traceable_numbers(post))

    def test_the_provenance_of_each_post_is_complete_and_contains_no_internal_number(self):
        for name, post in self.posts.items():
            with self.subTest(post=name):
                derived_ids = {d.fact_id for d in post.derived}
                fact_ids = {f.fact_id for f in post.facts_used}
                self.assertTrue(fact_ids and derived_ids)
                for derived in post.derived:
                    self.assertEqual(F.validate_derived(derived), [])
                    self.assertTrue(set(derived.input_fact_ids) <= fact_ids | derived_ids)
                for fact in post.facts_used:
                    self.assertEqual(F.validate_fact(fact), [])
                    self.assertIn(fact.source_record_id, {r.record_id for r in post.source_records})
                    self.assertEqual(fact.meta_value("producer"), "NOAA")
                self.assertIsNone(re.search(r"[0-9a-f]{16}", post.evidence_text))
                self.assertIsNone(re.search(r"F[0-9]{2}_", post.evidence_text))
                self.assertNotIn("noaa_swpc_json", post.evidence_text)
                self.assertTrue(post.evidence_text.startswith("근거 자료(규칙 기반 조립, Fact 표)\n"))

    def test_the_posts_never_claim_what_the_data_cannot_say(self):
        claims = ("오로라", "정전", "통신 장애", "통신 두절", "위성 고장", "항공", "위험합니다", "안전합니다", "때문", "영향으로", "탓", "원인은", "예측", "예상", "전망", "건강", "피해")
        for name, post in self.posts.items():
            text = post.title + "\n" + post.description + "\n" + post.body_markdown
            with self.subTest(post=name):
                for claim in claims:
                    self.assertNotIn(claim, text)
                self.assertEqual(A.forbidden_found(text), [])
                self.assertEqual(A.blocked_found(text), [])
                self.assertIn("원인", story(post))                                                   # 원인을 말하지 않는다는 문장은 있다
                self.assertRegex(story(post), r"영향")                                              # …그리고 그 영향도 말하지 않는다고 밝힌다
                self.assertNotRegex(text, r"[~～〜]")

    def test_the_latin_words_in_the_story_are_only_names_from_labels_and_the_utc_mark(self):
        for name, post in self.posts.items():
            with self.subTest(post=name):
                allowed = {"NOAA", "SWPC", "GOES", "Kp", "UTC", "nW"}
                self.assertLessEqual(set(A.latin_words(story(post) + post.title)), allowed)

    def test_the_generator_keeps_the_title_as_a_value_free_line(self):
        for name, post in self.posts.items():
            content, _source = generator_file(post)
            with self.subTest(post=name):
                self.assertIn(f"title: {g._json_line(post.title)}", content)
                self.assertEqual(g._description_from_markdown(content), post.description)


class TitlePolicyTest(unittest.TestCase):
    """제목에는 값(숫자)이 없고 이름·지역·기준일뿐이다(R18, D-200) — R01–R03 도 같다."""

    @classmethod
    def setUpClass(cls):
        cls.new = {name: build(name) for name in golden_cases()}
        cls.old = {rid: FH.run(rid, params=params) for rid, params in FH.GOLDEN.items()}

    def dates_of(self, post):
        return A.date_numbers(post)

    def test_no_title_has_a_number_that_is_not_a_date(self):
        for name, post in {**self.new, **self.old}.items():
            with self.subTest(post=name):
                self.assertLessEqual(set(A.number_tokens(post.title)), self.dates_of(post))
                self.assertNotRegex(post.title, r"[+−%]|[0-9]\.[0-9]")                               # 값·변화량·퍼센트의 모양이 없다
                self.assertNotRegex(post.title, r"높아|낮아|같아|달라지|가장 높|가장 낮|위\b|곳")

    def test_the_title_templates_use_only_names_and_allowed_dates(self):
        mock_provider, mock_record, mock_facts = FH.mock_bundle()
        for rid, params in FH.GOLDEN.items():
            ctx = R.PlanContext(R.RECIPES[rid], tuple(sorted(mock_facts, key=lambda f: f.fact_id)), F.as_date(FH.TODAY), params)
            draft = R.RECIPES[rid].plan(ctx)
            self.assertIsInstance(draft, R.Draft)
            for template in draft.titles:
                with self.subTest(recipe=rid, template=template):
                    self.assertIsNone(R.title_template_problem(template))
                    self.assertTrue({kind for kind, _ref in F.references(template)} <= set("LRDT"))
        for name in golden_cases():
            recipe_id, product_id, rows, params = golden_cases()[name]
            record, facts = H.parse_value(product_id, rows)
            ctx = R.PlanContext(RN.NOREGION_RECIPES[recipe_id], tuple(sorted(facts, key=lambda f: f.fact_id)), F.as_date(H.TODAY), params)
            draft = RN.NOREGION_RECIPES[recipe_id].plan(ctx)
            self.assertIsInstance(draft, R.Draft, name)
            for template in draft.titles:
                with self.subTest(recipe=recipe_id, template=template):
                    self.assertIsNone(R.title_template_problem(template))

    def test_the_policy_function_refuses_values_and_unlisted_date_slots(self):
        good = ("⟦L:main⟧, ⟦D:main⟧ 기준", "⟦R:main⟧ ⟦L:main⟧, ⟦D:first_row⟧부터 ⟦D:last_row⟧까지", "⟦L:lbl⟧별 건수, ⟦T:record⟧ 기준", "⟦D:cur⟧ ⟦L:lbl⟧", "⟦D:first⟧부터 ⟦D:main⟧까지")
        for template in good:
            with self.subTest(template=template):
                self.assertIsNone(R.title_template_problem(template))
        for kind in "FSAVU":
            self.assertIsNotNone(R.title_template_problem(f"⟦L:main⟧ ⟦{kind}:main⟧"), kind)
        for template in ("⟦D:hi⟧ 기준", "⟦D:lo⟧", "⟦D:prev⟧ 기준", "⟦D:yago⟧", "⟦T:main⟧", "⟦D:record⟧"):
            with self.subTest(template=template):
                self.assertIsNotNone(R.title_template_problem(template))
        self.assertEqual(R.TITLE_DATE_SLOTS, {("D", "main"), ("D", "cur"), ("D", "first_row"), ("D", "last_row"), ("D", "first"), ("T", "record")})

    def test_a_recipe_that_puts_a_value_in_its_title_makes_no_post(self):
        def put_value(draft):
            draft.titles.insert(0, "⟦L:lbl⟧ ⟦F:cur⟧, ⟦D:cur⟧ 기준")
        for name in ("r04_kp", "r05_kp_storm"):
            recipe_id, product_id, rows, params = golden_cases()[name]
            base = RN.NOREGION_RECIPES[recipe_id]

            def plan(ctx, base=base):
                draft = base.plan(ctx)
                if not isinstance(draft, R.Insufficient):
                    put_value(draft)
                return draft
            record, facts = H.parse_value(product_id, rows)
            result = A.assemble(dataclasses.replace(base, plan=plan), facts, H.TODAY, records=[record], source=test_source(), params=params)
            with self.subTest(post=name):
                self.assertIsInstance(result, R.Insufficient)
                self.assertEqual(result.code, "TITLE_HAS_VALUE")
        old = FH.mock_bundle()

        def old_plan(ctx):
            draft = R.R01_TIME_SERIES.plan(ctx)
            if isinstance(draft, R.Draft):
                draft.titles.insert(0, "⟦R:main⟧ ⟦L:main⟧ ⟦F:main⟧(⟦D:main⟧ 기준)")           # 예전 제목 틀의 모양 — 이제는 거절된다
            return draft
        result = A.assemble(dataclasses.replace(R.R01_TIME_SERIES, plan=old_plan), old[2], FH.TODAY, records=[old[1]], source=FH.source_info(), params=FH.R01_PARAMS)
        self.assertEqual(result.code, "TITLE_HAS_VALUE")

    def test_post_problems_also_catches_a_value_in_a_finished_title(self):
        post = self.new["r04_kp"]
        value = next(token for token in A.number_tokens(post.description) if token not in A.date_numbers(post))
        self.assertEqual([p for p in A.post_problems(post, allowed_latin={"NOAA", "Kp", "UTC"}) if p.startswith("TITLE")], [])
        changed = dataclasses.replace(post, title=post.title.replace(" — 숫자로 읽기", f" {value}Kp 높아"))
        self.assertTrue(any(p.startswith("TITLE 제목에 기준일") for p in A.post_problems(changed, allowed_latin={"NOAA", "Kp", "UTC"})), A.post_problems(changed, allowed_latin={"NOAA", "Kp", "UTC"}))
        dated = dataclasses.replace(post, title="NOAA 추정 Kp 일별 최대값, 2026년 11월 8일 기준")
        self.assertEqual([p for p in A.post_problems(dated, allowed_latin={"NOAA", "Kp", "UTC"}) if p.startswith("TITLE")], [])

    def test_descriptions_may_carry_values_and_are_not_ai_input(self):
        for name, post in self.new.items():
            with self.subTest(post=name):
                self.assertRegex(post.description, r"\d")                                           # 설명에는 값이 있어도 된다
        text = (ROOT / "docs" / "FACT_PATH.md").read_text(encoding="utf-8")
        self.assertIn("설명(`description`)과 본문에는 값이 있어도 된다", text)
        self.assertIn("AI 가능 함수가 읽는 칸은 제목·태그·분류뿐", text)


class StatusTest(unittest.TestCase):
    """꼬리표 `status` 가 틀이 기대한 상태가 아니면 글을 만들지 않는다 — 예보·추정이 관측 계열에 섞이지 않는다."""

    def code(self, result):
        self.assertIsInstance(result, R.Insufficient, result)
        return result.code

    def test_a_forecast_or_estimate_in_a_measured_series_makes_no_post(self):
        for name, key in (("r04_kp", KP_KEY), ("r05_kp_storm", KP_KEY), ("r04_ssn_daily", "space_weather.sunspot_daily_swpc"), ("r04_ssn_monthly", "space_weather.sunspot_monthly_swpc"),
                          ("r05_flares", FLUX_KEY)):
            for status in ("predicted", "estimated", "reference"):
                with self.subTest(post=name, status=status):
                    self.assertEqual(self.code(build(name, mutate=lambda facts, key=key, status=status: with_status(facts, key, status))), "STATUS_MISMATCH")

    def test_a_value_without_any_status_cannot_be_shown_to_be_measured(self):
        stripped = lambda facts: [revalue(f, meta={"producer": "NOAA"}) if f.key == KP_KEY else f for f in facts]      # noqa: E731
        self.assertEqual(self.code(build("r04_kp", mutate=stripped)), "STATUS_MISMATCH")
        none_meta = lambda facts: [revalue(f, meta=None) if f.key == KP_KEY else f for f in facts]                      # noqa: E731
        self.assertEqual(self.code(build("r05_kp_storm", mutate=none_meta)), "STATUS_MISMATCH")

    def test_the_threshold_must_be_a_reference_value_of_the_same_unit(self):
        wrong = lambda status: (lambda facts: with_status(facts, "space_weather.kp_storm_threshold", status))            # noqa: E731
        for status in ("observed", "predicted"):
            self.assertEqual(self.code(build("r05_kp_storm", mutate=wrong(status))), "NO_THRESHOLD")
        gone = lambda facts: [f for f in facts if f.key != "space_weather.kp_storm_threshold"]                          # noqa: E731
        self.assertEqual(self.code(build("r05_kp_storm", mutate=gone)), "NO_THRESHOLD")
        unit = lambda facts: [revalue(f, unit="개") if f.key == "space_weather.kp_storm_threshold" else f for f in facts]  # noqa: E731
        self.assertEqual(self.code(build("r05_kp_storm", mutate=unit)), "NO_THRESHOLD")
        two = lambda facts: facts + [revalue(f, value="6", as_of="2026-11-09") for f in facts if f.key == "space_weather.kp_storm_threshold"]   # noqa: E731
        self.assertEqual(self.code(build("r05_kp_storm", mutate=two)), "NO_THRESHOLD")                                  # 기준값이 하나로 정해지지 않는다
        same = lambda facts: facts + [revalue(f, as_of="2026-11-09") for f in facts if f.key == "space_weather.kp_storm_threshold"]       # noqa: E731
        self.assertIsInstance(build("r05_kp_storm", mutate=same), A.AssembledPost)                                      # 값이 같은 여럿은 가장 나중 것

    def test_flare_floors_are_all_needed(self):
        for letter in "abcmx":
            gone = lambda facts, letter=letter: [f for f in facts if not f.key.endswith("floor_" + letter)]               # noqa: E731
            with self.subTest(letter=letter):
                self.assertEqual(self.code(build("r05_flares", mutate=gone)), "NO_THRESHOLD")

    def test_the_outlook_needs_forecast_values_and_observed_levels(self):
        base = build("r06_scales")
        self.assertIsInstance(base, A.AssembledPost)
        for key in ("daily_scale_radio", "daily_scale_radiation", "daily_scale_geomagnetic"):
            wrong = lambda facts, key=key: with_status(facts, "space_weather." + key, "predicted")                       # noqa: E731
            with self.subTest(key=key):
                self.assertEqual(self.code(build("r06_scales", mutate=wrong)), "STATUS_MISMATCH")
        for key in ("outlook_scale_geomagnetic", "outlook_prob_radio_minor", "outlook_prob_radio_major", "outlook_prob_radiation"):
            wrong = lambda facts, key=key: with_status(facts, "space_weather." + key, "observed")                        # noqa: E731
            with self.subTest(key=key):
                self.assertEqual(self.code(build("r06_scales", mutate=wrong)), "STATUS_MISMATCH")
            gone = lambda facts, key=key: [f for f in facts if f.key != "space_weather." + key]                          # noqa: E731
            self.assertEqual(self.code(build("r06_scales", mutate=gone)), "NO_FACTS")

    def test_region_facts_and_unknown_subjects_are_refused(self):
        with_region = lambda facts: [revalue(f, region="R01", region_level="province", region_label_ko="가상 지역 가") if f.key == KP_KEY else f for f in facts]    # noqa: E731
        self.assertEqual(self.code(build("r04_kp", mutate=with_region)), "HAS_REGION")
        self.assertEqual(self.code(build("r04_kp", params={"key": "space_weather.kp_outlook"})), "UNKNOWN_SUBJECT")
        self.assertEqual(self.code(build("r05_kp_storm", params={"key": "space_weather.sunspot_daily_swpc"})), "UNKNOWN_SUBJECT")
        self.assertEqual(self.code(build("r04_kp", params={"key": "labour.unemployment_rate"})), "UNKNOWN_SUBJECT")
        self.assertEqual(self.code(build("r04_kp", mutate=lambda facts: [])), "NO_FACTS")

    def test_the_old_recipes_still_say_no_region_series_for_these_facts(self):
        record, facts = H.parse_value("kp_estimated", H.kp_rows("2026-11-02", 8))
        for rid in FH.GOLDEN:
            result = A.assemble(R.RECIPES[rid], facts, H.TODAY, records=[record], source=test_source(), params={"key": KP_KEY})
            with self.subTest(recipe=rid):
                self.assertIsInstance(result, R.Insufficient)
                self.assertEqual(result.code, "NO_REGION_SERIES")


class SeriesRecipeTest(unittest.TestCase):
    """R04: 값이 직접 센 값과 같고, 빠진 날·구간 부족·오래됨·모자람에서 글을 만들지 않는다."""

    def kp(self, **kw):
        rows = kw.pop("rows", None) or H.kp_rows("2026-11-02", 8, storm_days=(2,), partial_last=3)
        record, facts = H.parse_value("kp_estimated", rows)
        return rows, A.assemble(RN.R04_NOREGION_SERIES, facts, kw.pop("today", H.TODAY), records=[record], source=test_source(), params={"key": KP_KEY})

    def test_the_daily_maxima_in_the_table_are_the_hand_computed_maxima(self):
        rows, post = self.kp()
        expected = kp_daily_maxima(rows)
        self.assertEqual(len(expected), 7)                                                       # 8일 가운데 마지막(구간 3개뿐인 날)은 빠진다
        table = table_rows(post)
        self.assertEqual(len(table), 7)
        self.assertEqual([row[0] for row in table], [f"2026년 11월 {int(day[-2:])}일" for day in sorted(expected, reverse=True)])
        self.assertEqual([Decimal(row[1].replace("Kp", "")) for row in table], [expected[day] for day in sorted(expected, reverse=True)])
        self.assertTrue(all(len(row) == 2 for row in table))                                     # S2AFIX D9: Kp 표에는 증감 칸이 없다(날짜·값 둘뿐)
        self.assertIn("| 기준 기간 | 값 |", post.body_markdown)
        self.assertNotIn("바로 앞 기간 대비", post.body_markdown)
        self.assertNotIn("2026년 11월 9일", "\n".join(row[0] for row in table))                    # 구간이 모자란 날은 건너뛴다
        self.assertIn("구간이 모자란 날은 표에서 건너뛰었습니다", post.body_markdown)

    def test_the_summary_lines_match_a_hand_calculation(self):
        rows, post = self.kp()
        expected = kp_daily_maxima(rows)
        values = [expected[day] for day in sorted(expected)]
        last, prev = values[-1], values[-2]
        window = values[-3:]
        mean = sum(window) / 3
        body = post.body_markdown
        self.assertIn(f"- 최신 값: {last:.2f}Kp(2026년 11월 8일 기준)", body)
        self.assertIn(f"- 최근 3일 평균: {mean.quantize(Decimal('0.01'), rounding='ROUND_HALF_UP'):.2f}Kp", body)
        self.assertIn(f"- 바로 앞 날: {prev:.2f}Kp(2026년 11월 7일)", body)                       # S2AFIX D9: 증감 줄 대신 앞 날의 값만 적는다
        self.assertNotIn("바로 앞 날 대비", body)
        self.assertIn(f"최저 {min(values):.2f}Kp", body)
        self.assertIn(f"최고 {max(values):.2f}Kp", body)

    def test_kp_has_no_change_column_and_says_only_the_direction_to_the_previous_day(self):
        """S2AFIX D9: Kp 는 3분의 1 단위 값을 소수 둘째 자리로 줄여 적어(5.33 → 2.67 의 차이가 −2.66) 두 값의 차이가 한 끝자리 어긋난다 — 증감 칸·줄을 만들지 않고 바로 앞 날과의 높낮이만 말한다."""
        for prev, cur, lead, reading in ((2.67, 3.33, "보다 높은 3.33Kp입니다", "의 2.67Kp보다 높습니다"), (3.33, 2.67, "보다 낮은 2.67Kp입니다", "의 3.33Kp보다 낮습니다"),
                                         (2.67, 2.67, "에서 달라지지 않은 2.67Kp입니다", "의 2.67Kp에서 달라지지 않았습니다")):
            _rows, post = self.kp(rows=kp_rows_with_daily_maxima([2.0, 3.0, 2.33, 4.0, 2.0, 3.67, prev, cur]))
            body = post.body_markdown
            with self.subTest(prev=prev, cur=cur):
                self.assertIsInstance(post, A.AssembledPost, post)
                self.assertTrue(all(len(row) == 2 for row in table_rows(post)))
                self.assertIn("| 기준 기간 | 값 |", body)
                for banned in ("바로 앞 기간 대비", "바로 앞 날 대비", "해당 없음", "증감의 단위", "변화율 열"):
                    self.assertNotIn(banned, body)
                self.assertNotRegex(body, r"[+−]\d\.\d\dKp")                                         # 부호가 붙은 차이 값이 글 어디에도 없다
                self.assertIn(lead, post.description)
                self.assertIn(f"- 바로 앞 날: {prev:.2f}Kp(2026년 11월 8일)", body)
                self.assertIn(f"최신 값은 바로 앞 날(2026년 11월 8일){reading}", body)
                self.assertIn("날짜 사이의 증감은 계산하지 않았고 평균은 적힌 값으로 계산했습니다", body)         # 이유를 글이 밝힌다
                self.assertEqual(A.post_problems(post, allowed_latin={"NOAA", "Kp", "UTC"}), [])
        self.assertNotIn("F01_change", build("r04_kp").formulas)                                 # 증감 계산식을 쓰지 않는다

    def test_the_sunspot_posts_keep_their_change_columns_and_the_trend_word_of_their_titles(self):
        """D9 는 Kp 에만 해당한다 — 흑점수 두 글은 증감·변화율 열을 그대로 두고, 제목어 `추이` 가 본문에도 있다(Gate QG6 의 약속어, S2AFIX D2)."""
        for name in ("r04_ssn_daily", "r04_ssn_monthly"):
            post = build(name)
            with self.subTest(post=name):
                self.assertIn("바로 앞 기간 대비 증감", post.body_markdown)
                self.assertIn("바로 앞 기간 대비 변화율", post.body_markdown)
                self.assertIn("추이", post.title)
                self.assertIn("의 추이를 ", story(post))
                self.assertIn("F01_change", post.formulas)
        self.assertNotIn("추이", build("r04_kp").title)

    def test_a_flat_kp_series_with_a_missing_day_in_the_last_three_makes_no_post_and_never_a_false_one(self):
        """S2AFIX2 N2: Kp 표에서 증감 칸을 뺀 대가(D9) — 하루 최대값이 읽은 모든 날 같고(평평) 최신 3일 안에 빠진 날이 있으면 글의 계산식이 하루 최댓값(F15) 하나뿐이라 `NO_ANALYSIS`(글 없음, 안전한 실패)다.
        7일이 이어지면 글이 나고 값이 달라지면 빠진 날이 있어도 글이 난다. 같은 자료로 R05 는 글이 만들어져 그 주에 Kp 글 하나가 사라지는 것은 R04 가 대표인 주뿐이다."""
        def run(recipe, day_values):
            record, facts = H.parse_value("kp_estimated", kp_rows_on_days(day_values))
            return A.assemble(recipe, facts, H.TODAY, records=[record], source=test_source(), params={"key": KP_KEY})
        flat_gap = [(f"2026-11-{day:02d}", 3.0) for day in (3, 4, 5, 6, 8, 9)]                                   # 11월 7일이 빠짐, 모두 3.0
        short_gap = [(f"2026-11-{day:02d}", 3.0) for day in (4, 5, 6, 8, 9)]
        for label, values in (("여섯 날(앞 날 빠짐)", flat_gap), ("다섯 날(앞 날 빠짐)", short_gap)):
            result = run(RN.R04_NOREGION_SERIES, values)
            with self.subTest(case=label):
                self.assertIsInstance(result, R.Insufficient)
                self.assertEqual(result.code, "NO_ANALYSIS")
                self.assertNotIsInstance(result, A.AssembledPost)
        with mock.patch.object(A, "MIN_DISTINCT_FORMULAS", 0):                                                   # 이유: 데이터 문제가 아니라 계산식이 둘 이상이어야 한다는 규칙
            relaxed = run(RN.R04_NOREGION_SERIES, flat_gap)
        self.assertIsInstance(relaxed, A.AssembledPost)
        self.assertEqual(relaxed.formulas, ("F15_day_max",))
        self.assertEqual(A.MIN_DISTINCT_FORMULAS, 2)
        connected = run(RN.R04_NOREGION_SERIES, [(f"2026-11-{day:02d}", 3.0) for day in range(3, 10)])           # 7일 이어짐: 창 평균(F07)이 생긴다
        self.assertIsInstance(connected, A.AssembledPost)
        self.assertIn("F07_rolling_mean", connected.formulas)
        varied = run(RN.R04_NOREGION_SERIES, [("2026-11-03", 2.0), ("2026-11-04", 3.0), ("2026-11-05", 2.33), ("2026-11-06", 4.0), ("2026-11-08", 2.67), ("2026-11-09", 3.33)])
        self.assertIsInstance(varied, A.AssembledPost)                                                           # 값이 달라지면 최고·최저(F09·F10)가 생긴다
        self.assertTrue({"F09_max", "F10_min"} <= set(varied.formulas))
        storm = run(RN.R05_THRESHOLD_COUNT, flat_gap)
        self.assertIsInstance(storm, A.AssembledPost, storm)                                                     # 같은 자료로 R05 는 글이 난다

    def test_incomplete_days_are_not_turned_into_values_and_too_few_days_make_no_post(self):
        _rows, post = self.kp(rows=H.kp_rows("2026-11-02", 8, partial_last=0, storm_days=()))
        self.assertEqual(len(table_rows(post)), 8)                                              # 여덟 날이 모두 있으면 모두 쓴다
        rows = H.kp_rows("2026-11-02", 8)
        del rows[10]                                                                             # 둘째 날의 구간 하나가 빠짐 — 그날은 값이 없다
        _rows, post = self.kp(rows=rows)
        self.assertEqual(len(table_rows(post)), 7)
        _rows, short = self.kp(rows=H.kp_rows("2026-11-05", 5, partial_last=0)[:32])
        self.assertIsInstance(short, R.Insufficient)
        self.assertEqual(short.code, "TOO_FEW_POINTS")
        _rows, nothing = self.kp(rows=H.kp_rows("2026-11-09", 1, partial_last=5))
        self.assertEqual(nothing.code, "TOO_FEW_POINTS")

    def test_stale_and_future_data_make_no_post(self):
        _rows, stale = self.kp(today="2026-11-30")
        self.assertEqual((stale.code if isinstance(stale, R.Insufficient) else "post"), "STALE")
        _rows, ok = self.kp(today="2026-11-18")
        self.assertIsInstance(ok, A.AssembledPost)
        record, facts = H.parse_value("kp_estimated", H.kp_rows("2026-11-02", 8, partial_last=0))
        result = A.assemble(RN.R04_NOREGION_SERIES, facts, "2026-11-05", records=[record], source=test_source(), params={"key": KP_KEY})
        self.assertIsInstance(result, R.Insufficient)
        self.assertEqual(result.code, "FUTURE_DATA")

    def test_the_same_instant_twice_and_mixed_period_kinds_are_refused(self):
        record, facts = H.parse_value("kp_estimated", H.kp_rows("2026-11-02", 8, partial_last=0))
        twice = list(facts) + [revalue(facts[0], value="9")]
        result = A.assemble(RN.R04_NOREGION_SERIES, twice, H.TODAY, records=[record], source=test_source(), params={"key": KP_KEY})
        self.assertEqual(result.code, "DUPLICATE_PERIOD")
        mixed = list(facts) + [revalue(facts[0], as_of="2026-11-03")]
        result = A.assemble(RN.R04_NOREGION_SERIES, mixed, H.TODAY, records=[record], source=test_source(), params={"key": KP_KEY})
        self.assertEqual(result.code, "MIXED_PERIOD_KIND")

    def test_labels_and_units_of_one_series_must_agree(self):
        record, facts = H.parse_value("kp_estimated", H.kp_rows("2026-11-02", 8, partial_last=0))
        other = [revalue(f, label_ko="NOAA 예보 Kp") if f is facts[3] else f for f in facts]
        self.assertEqual(A.assemble(RN.R04_NOREGION_SERIES, other, H.TODAY, records=[record], source=test_source(), params={"key": KP_KEY}).code, "INCONSISTENT_LABELS")
        unit = [revalue(f, unit="개") if f is facts[3] else f for f in facts]
        self.assertEqual(A.assemble(RN.R04_NOREGION_SERIES, unit, H.TODAY, records=[record], source=test_source(), params={"key": KP_KEY}).code, "INCONSISTENT_LABELS")
        unlisted = [revalue(f, label_ko="NOAA 건강 Kp") if f.key == KP_KEY else f for f in facts]
        self.assertEqual(A.assemble(RN.R04_NOREGION_SERIES, unlisted, H.TODAY, records=[record], source=test_source(), params={"key": KP_KEY}).code, "UNKNOWN_TOPIC")
        blocked = [revalue(f, label_ko="NOAA 환자 Kp") if f.key == KP_KEY else f for f in facts]
        self.assertEqual(A.assemble(RN.R04_NOREGION_SERIES, blocked, H.TODAY, records=[record], source=test_source(), params={"key": KP_KEY}).code, "TOPIC_NOT_ALLOWED")

    def test_the_daily_sunspot_comparison_uses_exact_windows(self):
        rows = H.ssn_daily_rows("2026-11-09", 70)
        values = [Decimal(row["swpc_ssn"]) for row in rows]
        record, facts = H.parse_value("ssn_daily", rows)
        post = A.assemble(RN.R04_NOREGION_SERIES, facts, H.TODAY, records=[record], source=test_source(), params={"key": "space_weather.sunspot_daily_swpc"})
        self.assertIsInstance(post, A.AssembledPost, post)
        recent, before = sum(values[-30:]) / 30, sum(values[-60:-30]) / 30
        self.assertEqual(len(values), 70)
        context = dict(post.decimals)
        digits = context["개"]
        self.assertEqual(digits, 0)
        shown = lambda value: f"{value.quantize(Decimal(1), rounding='ROUND_HALF_UP'):,}개"        # noqa: E731
        self.assertIn(f"- 최근 30일 평균 {shown(recent)}, 그 앞 30일 평균 {shown(before)} 대비 ", post.body_markdown)
        self.assertIn(f"- 최근 7일 평균: {shown(sum(values[-7:]) / 7)}", post.body_markdown)
        gappy_rows = H.ssn_daily_rows("2026-11-09", 70, gaps=(20,))                              # 최근 30일 안에는 빠진 날이 없고 그 앞 30일 안에 하루가 빠졌다
        record, facts = H.parse_value("ssn_daily", gappy_rows)
        gappy = A.assemble(RN.R04_NOREGION_SERIES, facts, H.TODAY, records=[record], source=test_source(), params={"key": "space_weather.sunspot_daily_swpc"})
        self.assertNotIn("그 앞 30일 평균", gappy.body_markdown)                                   # 이어지지 않은 창으로는 비교하지 않는다
        self.assertIn("최근 7일 평균", gappy.body_markdown)
        self.assertNotIn("개월", gappy.body_markdown)
        self.assertNotIn("69일", gappy.body_markdown)                                             # 빠진 날이 있는 자료의 개수를 기간(일)으로 말하지 않는다

    def test_a_window_mean_on_a_half_step_is_shown_exactly(self):
        """R02 의 D-152·N3 와 같은 규칙: 정수 자료의 30일 평균이 100.5 처럼 반 칸에 걸리면 표시 자리를 한 칸 늘린다 — '101 대 101 인데 평균이 1 낮다'가 나오지 않는다."""
        params = {"key": "space_weather.sunspot_daily_swpc"}
        older, recent = [101] * 32, [101] * 15 + [100] * 15                 # 앞 30일 평균 101·최근 30일 평균 100.5(합 3015 — 반 칸)
        record, facts = H.parse_value("ssn_daily", H.ssn_daily_rows_from(older + recent))
        post = A.assemble(RN.R04_NOREGION_SERIES, facts, H.TODAY, records=[record], source=test_source(), params=params)
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertEqual(dict(post.decimals), {"개": 1})
        self.assertIn("- 최근 30일 평균 100.5개, 그 앞 30일 평균 101.0개 대비 −0.5개", post.body_markdown)
        self.assertIn("최근 30일 평균은 그 앞 30일 평균보다 0.5개 낮습니다", post.body_markdown)
        self.assertEqual(A.post_problems(post, allowed_latin={"SWPC", "UTC"}), [])
        control = [101] * 15 + [100] * 14 + [101]                           # 합 3016 — 반 칸이 아니다
        record, facts = H.parse_value("ssn_daily", H.ssn_daily_rows_from(older + control))
        plain = A.assemble(RN.R04_NOREGION_SERIES, facts, H.TODAY, records=[record], source=test_source(), params=params)
        self.assertEqual(dict(plain.decimals), {"개": 0})
        self.assertIn("- 최근 30일 평균 101개, 그 앞 30일 평균 101개 대비 ", plain.body_markdown)
        # 두 평균은 반 칸이 아닌데 둘의 차이가 정확히 0.5 인 경우(합 3010 과 2995 — 100.33 과 99.83): 예전 방식이면 '100 대 100 인데 +1 높다'
        shifted_recent, shifted_before = [110] + [100] * 29, [95] + [100] * 29
        record, facts = H.parse_value("ssn_daily", H.ssn_daily_rows_from([100, 100] + shifted_before + shifted_recent))
        gap = A.assemble(RN.R04_NOREGION_SERIES, facts, H.TODAY, records=[record], source=test_source(), params=params)
        self.assertEqual(dict(gap.decimals), {"개": 1})
        self.assertIn("- 최근 30일 평균 100.3개, 그 앞 30일 평균 99.8개 대비 +0.5개", gap.body_markdown)
        self.assertIn("최근 30일 평균은 그 앞 30일 평균보다 0.5개 높습니다", gap.body_markdown)
        # 두 평균 가운데 하나만 반 칸에 걸리고 차이는 반 칸이 아닌 경우(합 3009 → 100.3, 3015 → 100.5): 예전 방식이면 '101 대 100 인데 차이 0'
        for older_sum, recent_sum, mean_c, mean_p, change in ((3009, 3015, "100.5", "100.3", "+0.2"), (3015, 3009, "100.3", "100.5", "−0.2")):
            older, recent = [older_sum - 2900] + [100] * 29, [recent_sum - 2900] + [100] * 29
            record, facts = H.parse_value("ssn_daily", H.ssn_daily_rows_from([100, 100] + older + recent))
            one_sided = A.assemble(RN.R04_NOREGION_SERIES, facts, H.TODAY, records=[record], source=test_source(), params=params)
            self.assertEqual(dict(one_sided.decimals), {"개": 1}, (older_sum, recent_sum))
            self.assertIn(f"- 최근 30일 평균 {mean_c}개, 그 앞 30일 평균 {mean_p}개 대비 {change}개", one_sided.body_markdown)

    def test_a_smoothed_series_that_is_not_measured_is_left_out_of_the_table(self):
        rows = H.ssn_monthly_rows("2026-10", 70)
        record, facts = H.parse_value("ssn_monthly", rows)
        forecast = with_status(facts, "space_weather.sunspot_monthly_smoothed_swpc", "predicted")
        post = A.assemble(RN.R04_NOREGION_SERIES, forecast, H.TODAY, records=[record], source=test_source(), params={"key": "space_weather.sunspot_monthly_swpc"})
        self.assertIsInstance(post, A.AssembledPost, post)
        self.assertNotIn("평활값(제공처)", post.body_markdown)                                      # 예보 상태의 값을 관측 표에 섞지 않는다
        kept = A.assemble(RN.R04_NOREGION_SERIES, facts, H.TODAY, records=[record], source=test_source(), params={"key": "space_weather.sunspot_monthly_swpc"})
        self.assertIn("평활값(제공처)", kept.body_markdown)

    def test_two_values_for_the_same_day_or_month_make_no_post(self):
        for product, key, rows in (("ssn_daily", "space_weather.sunspot_daily_swpc", H.ssn_daily_rows("2026-11-09", 70)), ("ssn_monthly", "space_weather.sunspot_monthly_swpc", H.ssn_monthly_rows("2026-10", 70))):
            record, facts = H.parse_value(product, rows)
            last = [f for f in facts if f.key == key][-1]
            twin = revalue(last, value=last.value + 1)
            with self.subTest(product=product):
                result = A.assemble(RN.R04_NOREGION_SERIES, list(facts) + [twin], H.TODAY, records=[record], source=test_source(), params={"key": key})
                self.assertIsInstance(result, R.Insufficient)
                self.assertEqual(result.code, "DUPLICATE_PERIOD")

    def test_the_monthly_table_marks_provisional_months_and_carries_the_smoothed_column(self):
        rows = H.ssn_monthly_rows("2026-10", 70)
        record, facts = H.parse_value("ssn_monthly", rows)
        post = A.assemble(RN.R04_NOREGION_SERIES, facts, H.TODAY, records=[record], source=test_source(), params={"key": "space_weather.sunspot_monthly_swpc"})
        table = table_rows(post)
        self.assertEqual(len(table), 12)
        self.assertEqual([row[-1] for row in table], ["잠정"] * 6 + ["표시 없음"] * 6)           # 최근 6개월은 잠정치
        self.assertEqual([row[-2] for row in table[:6]], ["자료 없음"] * 6)                       # 평활값은 최근 6개월이 비어 있다
        self.assertTrue(all(row[-2].endswith("개") for row in table[6:]))
        self.assertIn("전년 같은 달 대비", post.body_markdown)
        self.assertIn("잠정치 표시", post.body_markdown)
        for recipe_text in ("평활값(제공처)", "잠정치 표시"):
            self.assertIn(recipe_text, post.body_markdown)
        self.assertNotIn("확정", post.body_markdown)                                               # 잠정이 아닌 달을 '확정'이라 부르지 않는다
        values = [Decimal(str(row["observed_swpc_ssn"])) for row in rows]
        self.assertEqual(table[0][1], f"{values[-1]:,.2f}개")


class ThresholdRecipeTest(unittest.TestCase):
    def kp(self, storm_days=(2,), *, days=8, partial=3):
        rows = H.kp_rows("2026-11-02", days, storm_days=storm_days, partial_last=partial)
        record, facts = H.parse_value("kp_estimated", rows)
        return rows, A.assemble(RN.R05_THRESHOLD_COUNT, facts, H.TODAY, records=[record], source=test_source(), params={"key": KP_KEY})

    def test_storm_days_and_intervals_match_a_hand_count(self):
        for storm_days in ((), (2,), (0, 3, 5), (0, 1, 2, 3, 4, 5, 6)):
            rows, post = self.kp(storm_days)
            with self.subTest(storm_days=storm_days):
                self.assertIsInstance(post, A.AssembledPost, post)
                complete = {}
                for row in rows:
                    complete.setdefault(row["time_tag"][:10], []).append(Decimal(str(row["Kp"])))
                complete = {day: values for day, values in complete.items() if len(values) == 8}
                days_over = sum(1 for values in complete.values() if max(values) >= 5)
                intervals_over = sum(1 for values in complete.values() for value in values if value >= 5)
                interval_total = sum(len(values) for values in complete.values())
                self.assertIn(f"- 이 글이 읽은 {len(complete)}일 가운데 기준 이상인 날: {days_over}일", post.body_markdown)
                self.assertIn(f"- 구간 단위로는 {interval_total}구간 가운데 기준 이상인 구간: {intervals_over}구간", post.body_markdown)
                self.assertIn(f"이 글이 읽은 {len(complete)}일 가운데 {days_over}일입니다.", post.description)
                table = table_rows(post)
                self.assertEqual(len(table), len(complete))
                self.assertEqual(sum(1 for row in table if row[3] == "기준 이상"), days_over)
                self.assertEqual(sum(int(row[2].replace("구간", "")) for row in table), intervals_over)

    def test_zero_storm_days_is_said_with_a_number_not_a_blank(self):
        _rows, post = self.kp(())
        self.assertIn("기준 이상인 날: 0일", post.body_markdown)
        self.assertIn("하루 최대값이 기준 5.00Kp 이상인 날은 없었습니다", post.body_markdown)
        self.assertIn("0구간", post.body_markdown)
        self.assertTrue(post.description.endswith("가운데 0일입니다."))

    def test_the_threshold_comparison_includes_the_bound_and_excludes_just_below(self):
        rows = H.kp_rows("2026-11-02", 7, partial_last=0)
        for index, row in enumerate(rows):
            row["Kp"] = 4.67
        rows[3]["Kp"] = 5.0                                                                      # 첫째 날: 정확히 기준
        rows[11]["Kp"] = 4.67                                                                    # 둘째 날: 기준 바로 아래만
        record, facts = H.parse_value("kp_estimated", rows)
        post = A.assemble(RN.R05_THRESHOLD_COUNT, facts, H.TODAY, records=[record], source=test_source(), params={"key": KP_KEY})
        self.assertIn("기준 이상인 날: 1일", post.body_markdown)
        self.assertEqual([row[3] for row in table_rows(post)].count("기준 이상"), 1)

    def test_ties_of_the_highest_daily_maximum_are_not_one_day(self):
        rows = H.kp_rows("2026-11-02", 7, partial_last=0, storm_days=())
        for day in (1, 4):
            rows[day * 8 + 2]["Kp"] = 6.67
        record, facts = H.parse_value("kp_estimated", rows)
        post = A.assemble(RN.R05_THRESHOLD_COUNT, facts, H.TODAY, records=[record], source=test_source(), params={"key": KP_KEY})
        self.assertIn("가장 높은 하루 최대값: 6.67Kp(같은 값 2번, 가장 나중 2026년 11월 6일)", post.body_markdown)
        self.assertIn("기준 이상인 날: 2일", post.body_markdown)

    def kp_with_maxima(self, maxima):
        record, facts = H.parse_value("kp_estimated", kp_rows_with_daily_maxima(maxima))
        return A.assemble(RN.R05_THRESHOLD_COUNT, facts, H.TODAY, records=[record], source=test_source(), params={"key": KP_KEY})

    def test_when_every_daily_maximum_is_the_same_no_highest_or_lowest_day_is_named(self):
        """S2AFIX D6: 읽은 날의 하루 최대값이 모두 같으면 한 날짜를 가장 높은 날·가장 낮은 날로 지목하지 않는다(R04 의 flat_table 과 같은 규칙)."""
        for value, storm_days in ((6.0, 7), (2.0, 0)):
            post = self.kp_with_maxima([value] * 7)
            body = post.body_markdown
            with self.subTest(value=value):
                self.assertIsInstance(post, A.AssembledPost, post)
                self.assertIn(f"- 하루 최대값의 범위: 읽은 7일 모두 같은 {value:.2f}Kp입니다(가장 높은 날과 가장 낮은 날을 가르지 않았습니다)", body)
                self.assertIn(f"읽은 날의 하루 최대값은 모두 같은 {value:.2f}Kp입니다.", body)
                self.assertNotIn("가장 높은 하루 최대값", body)
                self.assertNotIn("가장 낮은 하루 최대값", body)
                self.assertIn(f"- 이 글이 읽은 7일 가운데 기준 이상인 날: {storm_days}일", body)
                self.assertEqual(A.post_problems(post, allowed_latin={"NOAA", "Kp", "UTC"}), [])

    def test_ties_of_the_lowest_daily_maximum_are_not_one_day(self):
        """S2AFIX D6: 최저가 여러 날이면 '같은 값 N번, 가장 나중 날짜' 로 쓰고 한 날짜로 단정하지 않는다. 하나뿐이면 그 날짜를 그대로 적는다."""
        post = self.kp_with_maxima([2.0, 2.0, 3.0, 2.0, 4.0, 2.0, 5.33])
        self.assertIn("- 가장 낮은 하루 최대값: 2.00Kp(같은 값 4번, 가장 나중 2026년 11월 7일)", post.body_markdown)
        self.assertIn("- 가장 높은 하루 최대값: 5.33Kp(2026년 11월 8일)", post.body_markdown)
        both = self.kp_with_maxima([2.0, 5.33, 3.0, 2.0, 5.33, 2.0, 5.33])
        self.assertIn("- 가장 낮은 하루 최대값: 2.00Kp(같은 값 3번, 가장 나중 2026년 11월 7일)", both.body_markdown)
        self.assertIn("- 가장 높은 하루 최대값: 5.33Kp(같은 값 3번, 가장 나중 2026년 11월 8일)", both.body_markdown)
        unique = self.kp_with_maxima([2.33, 3.0, 2.67, 4.0, 3.0, 2.67, 5.33])
        self.assertIn("- 가장 낮은 하루 최대값: 2.33Kp(2026년 11월 2일)", unique.body_markdown)
        self.assertNotRegex(unique.body_markdown, r"같은 값 \d+번")

    def test_flare_counts_by_class_match_a_hand_count_and_zero_classes_are_shown(self):
        record, facts = H.parse_value("xray_flares", H.flare_rows(EVENTS))
        post = A.assemble(RN.R05_THRESHOLD_COUNT, facts, H.TODAY, records=[record], source=test_source(), params={"key": FLUX_KEY})
        self.assertIsInstance(post, A.AssembledPost, post)
        by_letter = {letter: sum(1 for _stamp, text in EVENTS if text[0] == letter) for letter in "ABCMX"}
        for letter, count in by_letter.items():
            self.assertIn(f"| {letter}급 | {count}건 |", post.body_markdown)
        self.assertIn(f"| M급 이상 합계 | {by_letter['M'] + by_letter['X']}건 |", post.body_markdown)
        self.assertIn(f"| 전체 | {len(EVENTS)}건 |", post.body_markdown)
        self.assertEqual(by_letter["A"], 0)
        self.assertIn("가장 큰 플레어: M2.1(2026년 11월 6일 4시 17분(UTC))", post.body_markdown)
        self.assertIn("그 가운데 X급 0건", post.body_markdown)
        self.assertIn("기록한 위성: 이 목록의 플레어는 같은 위성의 기록입니다", post.body_markdown)

    def test_class_boundaries_belong_to_the_higher_class(self):
        events = [("2026-11-04T06:15:00Z", "B9.9"), ("2026-11-04T07:15:00Z", "C1.0"), ("2026-11-04T08:15:00Z", "C9.9"), ("2026-11-04T09:15:00Z", "M1.0"), ("2026-11-04T10:15:00Z", "M9.9"),
                  ("2026-11-04T11:15:00Z", "X1.0"), ("2026-11-04T12:15:00Z", "X1.1")]
        record, facts = H.parse_value("xray_flares", H.flare_rows(events))
        post = A.assemble(RN.R05_THRESHOLD_COUNT, facts, H.TODAY, records=[record], source=test_source(), params={"key": FLUX_KEY})
        for letter, count in (("A", 0), ("B", 1), ("C", 2), ("M", 2), ("X", 2)):
            self.assertIn(f"| {letter}급 | {count}건 |", post.body_markdown)
        self.assertIn("가장 큰 플레어: X1.1", post.body_markdown)

    def test_a_flare_list_with_several_satellites_says_so_and_ties_are_not_one_flare(self):
        rows = H.flare_rows(EVENTS)
        rows[0]["satellite"] = 19
        rows[1] = dict(rows[1], max_class="M2.1", satellite=19)
        record, facts = H.parse_value("xray_flares", rows)
        post = A.assemble(RN.R05_THRESHOLD_COUNT, facts, H.TODAY, records=[record], source=test_source(), params={"key": FLUX_KEY})
        self.assertIn("이 목록에는 여러 위성의 기록이 섞여 있어", post.body_markdown)
        self.assertNotIn("같은 위성의 기록입니다", post.body_markdown)
        self.assertRegex(post.body_markdown, r"가장 큰 플레어: M2\.1\(같은 세기 \d+번")

    def test_class_and_flux_must_be_a_pair_and_events_must_not_be_too_few(self):
        record, facts = H.parse_value("xray_flares", H.flare_rows(EVENTS))
        lone = [f for f in facts if not (f.key == "space_weather.xray_flare_class" and f.as_of == EVENTS[0][0])]
        self.assertEqual(A.assemble(RN.R05_THRESHOLD_COUNT, lone, H.TODAY, records=[record], source=test_source(), params={"key": FLUX_KEY}).code, "INCONSISTENT_LABELS")
        record, few = H.parse_value("xray_flares", H.flare_rows(EVENTS[:3]))
        self.assertEqual(A.assemble(RN.R05_THRESHOLD_COUNT, few, H.TODAY, records=[record], source=test_source(), params={"key": FLUX_KEY}).code, "TOO_FEW_POINTS")
        record, facts = H.parse_value("xray_flares", H.flare_rows(EVENTS))
        self.assertEqual(A.assemble(RN.R05_THRESHOLD_COUNT, facts, "2026-12-30", records=[record], source=test_source(), params={"key": FLUX_KEY}).code, "STALE")

    def test_a_flare_record_without_a_value_makes_no_post(self):
        """플레어 등급이나 세기 하나에 값이 없으면(어댑터는 이런 응답을 거절하지만 틀도 따로 막는다) 개수를 세지 않는다."""
        record, facts = H.parse_value("xray_flares", H.flare_rows(EVENTS))
        for key in (FLUX_KEY, "space_weather.xray_flare_class"):
            first = next(f for f in facts if f.key == key)
            broken = [revalue(f, value=None) if f is first else f for f in facts]
            with self.subTest(key=key):
                result = A.assemble(RN.R05_THRESHOLD_COUNT, broken, H.TODAY, records=[record], source=test_source(), params={"key": FLUX_KEY})
                self.assertIsInstance(result, R.Insufficient)
                self.assertEqual(result.code, "MISSING_VALUE")


class OutlookRecipeTest(unittest.TestCase):
    def post(self, **kw):
        obj = H.scales_object(g_now=kw.pop("g_now", "1"), g_forecast=kw.pop("g_forecast", ("1", "2", "0")), probs=kw.pop("probs", PROBS))
        record, facts = H.parse_value("scales", obj)
        return A.assemble(RN.R06_SCALE_OUTLOOK, facts, kw.pop("today", H.TODAY), records=[record], source=test_source(), params={})

    def test_the_forecast_numbers_are_computed_from_the_three_days(self):
        post = self.post()
        self.assertIsInstance(post, A.AssembledPost, post)
        rows = table_rows(post)
        forecast = [row for row in rows if len(row) == 5]
        self.assertEqual([row[1:] for row in forecast], [["60.0%", "15.0%", "10.0%", "1단계"], ["45.0%", "10.0%", "5.0%", "2단계"], ["30.0%", "5.0%", "1.0%", "0단계"]])
        self.assertIn("- 예보 — 전파 교란 낮은 등급 확률의 최댓값 60.0%, 평균 45.0%", post.body_markdown)
        self.assertIn("- 예보 — 전파 교란 높은 등급 확률의 최댓값 15.0%, 평균 10.0%", post.body_markdown)
        self.assertIn("- 예보 — 방사선 폭풍 확률의 최댓값 10.0%, 평균 5.3%", post.body_markdown)
        self.assertIn("- 예보 — 지자기 폭풍 등급의 최댓값 2단계", post.body_markdown)
        self.assertIn("30.0%p 낮아지는 쪽입니다", post.body_markdown)
        self.assertEqual(post.formulas, ("F01_change", "F07_rolling_mean", "F09_max", "F12_count"))

    def test_every_line_with_a_forecast_value_says_forecast(self):
        post = self.post()
        for line in story(post).split("\n"):
            if re.search(r"전파 교란 (?:낮은|높은) 등급 확률|방사선 폭풍 확률|지자기 폭풍 등급의 최댓값", line):
                self.assertIn("예보", line, line)
        header = next(line for line in post.body_markdown.split("\n") if line.startswith("| 예보 날짜"))
        self.assertEqual(header.count("예보"), 5)
        observed = next(line for line in post.body_markdown.split("\n") if line.startswith("| 기준일 | 전파 교란 등급"))
        self.assertNotIn("예보", observed)
        self.assertIn("예보를 관측처럼 읽지 마세요", post.body_markdown)
        self.assertIn("관측이 아니라 NOAA가 낸 예보입니다", post.body_markdown)

    def test_the_observed_levels_and_yesterday_are_shown_as_observed(self):
        post = self.post(g_now="2")
        table = [row for row in table_rows(post) if len(row) == 4]
        self.assertEqual([row[0] for row in table], ["2026년 11월 10일(지금)", "2026년 11월 9일(어제)"])
        self.assertEqual([row[1:] for row in table], [["0단계", "0단계", "2단계"], ["0단계", "0단계", "0단계"]])
        self.assertIn("지자기 폭풍 등급은 2단계입니다", post.description)

    def test_a_missing_forecast_value_or_a_stale_file_makes_no_post(self):
        obj = H.scales_object()
        obj["2"]["R"]["MinorProb"] = None
        record, facts = H.parse_value("scales", obj)
        result = A.assemble(RN.R06_SCALE_OUTLOOK, facts, H.TODAY, records=[record], source=test_source(), params={})
        self.assertIsInstance(result, R.Insufficient)
        self.assertEqual(result.code, "TOO_FEW_POINTS")
        self.assertEqual(self.post(today="2026-11-20").code, "STALE")
        self.assertIsInstance(self.post(today="2026-11-12"), A.AssembledPost)

    def test_forecast_days_that_skip_a_day_make_no_post(self):
        obj = H.scales_object()
        obj["3"]["DateStamp"] = H._iso_day(H.day_ordinal(H.TODAY) + 3)               # 예보 날짜 사이에 하루가 빠졌다(오늘·내일·사흘 뒤)
        record, facts = H.parse_value("scales", obj)
        result = A.assemble(RN.R06_SCALE_OUTLOOK, facts, H.TODAY, records=[record], source=test_source(), params={})
        self.assertIsInstance(result, R.Insufficient)
        self.assertEqual(result.code, "NOT_COMPARABLE")

    def test_equal_probabilities_say_the_same_not_a_direction(self):
        post = self.post(probs={"1": ("40", "10", "5"), "2": ("40", "10", "5"), "3": ("40", "10", "5")})
        self.assertIn("예보 시작 날과 마지막 날의 전파 교란 낮은 등급 확률 예보는 같습니다", post.body_markdown)
        self.assertNotIn("낮아지는", post.body_markdown)
        self.assertNotIn("높아지는", post.body_markdown)
        rising = self.post(probs={"1": ("10", "10", "5"), "2": ("20", "10", "5"), "3": ("30", "10", "5")})
        self.assertIn("20.0%p 높아지는 쪽입니다", rising.body_markdown)


class SpaceWordingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.posts = {name: build(name) for name in golden_cases()}

    def test_estimated_kp_is_called_the_noaa_estimate_and_the_threshold_is_stated(self):
        for name in ("r04_kp", "r05_kp_storm"):
            text = story(self.posts[name])
            self.assertIn("NOAA 추정 Kp", text)
            self.assertIn("다른 기관이 확정해 발표하는 Kp 와 다를 수 있습니다", text)
        storm = self.posts["r05_kp_storm"].body_markdown
        self.assertIn("NOAA가 가장 낮은 지자기 폭풍 등급으로 삼는 값이며 센 것은 이 글입니다", storm)
        self.assertIn("5.00Kp", storm)
        self.assertIn("NOAA가 구간마다 붙인 등급이 아니라 이 글이 값을 기준과 견주어 센 것이라 경계에서 다를 수 있습니다", storm)

    def test_the_times_are_utc_and_the_posts_say_so(self):
        for name, post in self.posts.items():
            if name == "r04_ssn_monthly":
                continue                                                                          # 달 단위 글은 시각을 쓰지 않는다
            with self.subTest(post=name):
                self.assertRegex(story(post), r"협정 세계시")

    def test_provisional_and_satellite_notes_are_there_where_they_belong(self):
        self.assertIn("잠정치 표시", self.posts["r04_ssn_monthly"].body_markdown)
        self.assertIn("기록한 위성", self.posts["r05_flares"].body_markdown)
        self.assertIn("감지가 놓친 느린 상승은 빠질 수 있습니다", self.posts["r05_flares"].body_markdown)

    def test_no_post_names_a_third_party_source_or_a_logo(self):
        for name, post in self.posts.items():
            text = post.title + post.description + post.body_markdown
            with self.subTest(post=name):
                for needle in ("NWS", "National Weather", "SIDC", "S.I.D.C", "Penticton", "NRC", "![", "<img", "F10.7", "f10.7"):
                    self.assertNotIn(needle, text)

    def test_the_first_paragraph_is_a_single_sentence_and_is_the_description(self):
        for name, post in self.posts.items():
            with self.subTest(post=name):
                self.assertTrue(R.DESCRIPTION_MIN <= len(post.description) <= R.DESCRIPTION_MAX)
                plain = re.sub(r"(?<=\d)\.(?=\d)", "", post.description)
                self.assertEqual(plain.count("."), 1)
                self.assertTrue(plain.endswith("."))


class DeterminismTest(unittest.TestCase):
    def test_input_order_and_repeated_calls_do_not_change_a_byte(self):
        rng = random.Random(5)
        for name, (recipe_id, product_id, rows, params) in golden_cases().items():
            record, facts = H.parse_value(product_id, rows)
            base = A.assemble(RN.NOREGION_RECIPES[recipe_id], facts, H.TODAY, records=[record], source=test_source(), params=params)
            with self.subTest(post=name):
                self.assertIsInstance(base, A.AssembledPost)
                for _ in range(3):
                    shuffled = list(facts)
                    rng.shuffle(shuffled)
                    again = A.assemble(RN.NOREGION_RECIPES[recipe_id], shuffled, H.TODAY, records=[record], source=test_source(), params=params)
                    self.assertEqual(again, base)
                    self.assertEqual(again.body_markdown.encode("utf-8"), base.body_markdown.encode("utf-8"))

    def test_the_global_decimal_context_does_not_change_the_post(self):
        import decimal
        for name in ("r04_kp", "r05_kp_storm", "r06_scales"):
            base = build(name)
            for prec, rounding in ((5, decimal.ROUND_DOWN), (10, decimal.ROUND_UP), (28, decimal.ROUND_HALF_EVEN)):
                with decimal.localcontext() as ctx:
                    ctx.prec, ctx.rounding = prec, rounding
                    with self.subTest(post=name, prec=prec):
                        self.assertEqual(build(name), base)

    def test_the_posts_do_not_depend_on_the_date_argument_except_for_freshness(self):
        for name in golden_cases():
            self.assertEqual(build(name, today="2026-11-10").body_markdown, build(name, today="2026-11-11").body_markdown)


class CalcNoteTest(unittest.TestCase):
    """S2AFIX2 N5: 지역 없는 틀(R04–R06)의 공통 안내 두 문장(첫 문단 뒤 자료 안내·'계산한 값' 주의 줄)은 이 글이 실제로 쓴 계산식만 말한다 — 이전에는 모든 글이 '증감·변화율·평균·순위' 를 나열해 Kp 글이
    계산하지 않는 증감·변화율·순위를 말했고 같은 글의 주의 줄('날짜 사이의 증감은 계산하지 않았고')과 어긋났다. 기존 틀 R01–R03 은 고정 문장 그대로다(출력 불변)."""
    SENTENCE_OF_KP = "날짜 사이의 증감은 계산하지 않았고"

    @classmethod
    def setUpClass(cls):
        cls.posts = {name: build(name) for name in golden_cases()}

    def test_both_sentences_name_exactly_the_calculations_each_golden_post_uses(self):
        for name, post in self.posts.items():
            first, second = notice_words(post)
            used = {R.CALC_WORD_OF[formula_id] for formula_id in post.formulas}
            with self.subTest(post=name):
                self.assertIsNotNone(first)
                self.assertEqual(first, second)                                                   # 두 문장의 낱말 목록은 같다
                self.assertEqual(first, R.calc_words(post.formulas))
                self.assertEqual(set(first.split("·")), used)                                      # 쓴 계산식의 낱말뿐 — 안 쓴 계산식의 낱말은 없다
                for word in {word for _formula, word in R.CALC_WORDS}:
                    self.assertEqual(word in first.split("·"), word in used, word)                  # 낱말 표의 모든 낱말이 쓴 계산식에 있을 때만 들어 있다
                self.assertNotIn("증감·변화율·평균·순위", post.body_markdown)

    def test_kp_posts_do_not_claim_a_change_a_rate_or_a_rank_and_do_not_contradict_their_own_last_caution(self):
        for name in ("r04_kp", "r05_kp_storm"):
            body = self.posts[name].body_markdown
            words = notice_words(self.posts[name])[0].split("·")
            with self.subTest(post=name):
                for word in ("증감", "변화율", "전년 대비 변화율", "순위", "비중"):
                    self.assertNotIn(word, words)
                rest = body.replace(self.SENTENCE_OF_KP, "")
                for word in ("증감", "변화율", "순위"):
                    self.assertNotIn(word, rest)                                                  # 글 어디에도 계산했다는 말이 없다(계산하지 않았다는 한 문장만 남는다)
        self.assertIn(self.SENTENCE_OF_KP, self.posts["r04_kp"].body_markdown)
        self.assertEqual(notice_words(self.posts["r04_kp"])[0], "하루 최대값·평균·평균과의 차이·최고값·최저값·개수")

    def test_the_other_posts_keep_the_calculations_they_really_make(self):
        self.assertTrue({"증감", "변화율"} <= set(notice_words(self.posts["r04_ssn_daily"])[0].split("·")))
        self.assertIn("전년 대비 변화율", notice_words(self.posts["r04_ssn_monthly"])[0].split("·"))
        self.assertIn("기준별 개수", notice_words(self.posts["r05_kp_storm"])[0].split("·"))
        self.assertIn("기준별 개수", notice_words(self.posts["r05_flares"])[0].split("·"))
        scales = notice_words(self.posts["r06_scales"])[0].split("·")
        self.assertIn("증감", scales)
        for word in ("변화율", "순위", "하루 최대값"):
            self.assertNotIn(word, scales)                                                        # 등급 글은 변화율·순위를 계산하지 않는다

    def test_the_old_recipes_keep_the_fixed_sentences_and_only_the_new_ones_opt_in(self):
        self.assertEqual([r.calc_from_formulas for r in R.RECIPES.values()], [False, False, False])
        self.assertEqual([r.calc_from_formulas for r in RN.NOREGION_RECIPES.values()], [True, True, True])
        for recipe_id, params in FH.GOLDEN.items():
            old = FH.run(recipe_id, params=params)
            with self.subTest(recipe=recipe_id):
                self.assertIn("증감·변화율·평균·순위 같은 값은 이 글이 그 숫자로 직접 계산했습니다.", old.body_markdown)
                self.assertIn("- 계산한 값: 증감·변화율·평균·순위는 이 글이 직접 계산했습니다.", old.body_markdown)
                self.assertEqual(notice_words(old), ("증감·변화율·평균·순위", None))                 # 첫 문단 쪽은 같은 낱말 꼴, 주의 줄은 옛 꼴(`…는`)이라 새 꼴에 맞지 않는다

    def test_calc_words_orders_removes_repeats_and_refuses_what_it_does_not_know(self):
        self.assertEqual(R.calc_words({"F07_rolling_mean", "F08_mean"}), "평균")                  # 같은 낱말은 한 번만
        self.assertEqual(R.calc_words(["F10_min", "F09_max", "F15_day_max"]), "하루 최대값·최고값·최저값")
        self.assertEqual(R.calc_words(("F16_count_between", "F12_count", "F01_change")), "증감·개수·기준별 개수")
        self.assertEqual(R.calc_words(frozenset(R.CALC_WORD_OF)), "하루 최대값·증감·변화율·전년 대비 변화율·순위·비중·평균·중앙값·평균과의 차이·격차·최고값·최저값·범위 안의 위치·개수·기준별 개수")
        for nothing in (None, (), [], set(), frozenset()):
            self.assertIsNone(R.calc_words(nothing))
        self.assertIsNone(R.calc_words({"F07_rolling_mean", "F99_unknown"}))                      # 모르는 계산식이 섞이면 만들지 않는다(고정 문장으로 돌아감)
        self.assertEqual(R.intro_template(None), R.INTRO_TEMPLATE)
        self.assertEqual(R.caution_common(None), R.CAUTION_COMMON)
        self.assertEqual(len(R.caution_common("평균")), len(R.CAUTION_COMMON))

    def test_the_new_sentences_obey_the_same_text_rules_as_the_fixed_ones(self):
        words = "하루 최대값·증감·변화율·전년 대비 변화율·순위·비중·평균·중앙값·평균과의 차이·격차·최고값·최저값·범위 안의 위치·개수·기준별 개수"        # 낱말을 모두 쓴 가장 긴 모양
        for text in (R.intro_template(words), *R.caution_common(words)):
            plain = F.REF_RE.sub("", text).replace(R.SOURCE_LINK_TOKEN, "")
            with self.subTest(text=text[:30]):
                self.assertEqual(F.untraced_numbers(text), [])
                self.assertEqual(A.forbidden_found(plain), [])
                self.assertEqual(A.blocked_found(plain), [])
                self.assertEqual(A.particle_problems(text), [])
                self.assertNotRegex(plain, r"[~～〜]|https?://")
        self.assertEqual(len(R.CAUTION_COMMON), 4)
        self.assertEqual(sum(line.startswith("- 계산한 값:") for line in R.caution_common(words)), 1)


class BackgroundSentencesTest(unittest.TestCase):
    """S2AFIX D5: 글마다 '이 값은 무엇인가·어떻게 읽나·무엇을 말해 주지 않나' 배경 문장이 둘에서 넷이고, 숫자·수 낱말 없는 우리 말 고정 문장이며 금지 표현·원인 단정·영향 단정이 없다."""
    PAIRS = {"r04_kp": (RN.KP_ABOUT, RN.KP_LIMIT), "r04_ssn_daily": (RN.SSN_ABOUT_DAILY, RN.SSN_LIMIT), "r04_ssn_monthly": (RN.SSN_ABOUT_MONTHLY, RN.SSN_LIMIT),
             "r05_kp_storm": (RN.KP_STORM_ABOUT, RN.KP_LIMIT), "r05_flares": (RN.FLARE_ABOUT, RN.FLARE_LIMIT), "r06_scales": (RN.SCALE_ABOUT, "")}
    CLAIMS = ("오로라", "정전", "통신 장애", "통신 두절", "위성 고장", "항공", "위험합니다", "안전합니다", "때문", "영향으로", "탓", "원인은", "예측", "예상", "전망", "건강", "피해")

    @classmethod
    def setUpClass(cls):
        cls.posts = {name: build(name) for name in golden_cases()}

    def test_every_post_carries_two_to_four_background_sentences(self):
        for name, (about, limit) in self.PAIRS.items():
            count = (about + " " + limit).count(".")
            with self.subTest(post=name):
                self.assertTrue(2 <= count <= 4, count)
                self.assertTrue(about.endswith(".") and about.count("  ") == 0)
        for name in ("r04_kp", "r05_kp_storm"):                                                  # 어떤 값인지(Kp 가 무엇인지)가 먼저, 그다음 읽는 법
            self.assertTrue(self.PAIRS[name][0].startswith("Kp는 지구 자기장이"))
        self.assertTrue(RN.SSN_ABOUT_DAILY.startswith("흑점수는 태양 표면에 나타나는") and RN.SSN_ABOUT_MONTHLY.startswith("흑점수는 태양 표면에 나타나는"))
        self.assertTrue(RN.FLARE_ABOUT.startswith("X선 플레어는") and RN.SCALE_ABOUT.startswith("NOAA는 우주기상을"))

    def test_the_sentences_are_in_the_posts_and_the_limit_says_what_the_value_does_not_tell(self):
        for name, (about, limit) in self.PAIRS.items():
            text = story(self.posts[name])
            shown = about.replace("⟦F:thr⟧", "5.00Kp")                                            # 참조 표시는 글에서 값으로 바뀐다
            with self.subTest(post=name):
                self.assertIn(shown, text)
                if limit:
                    self.assertIn(limit, text)
                    self.assertIn("알려 주지 않습니다", limit)
                    self.assertIn("영향", limit)
                else:
                    self.assertIn("말하지 않습니다", text)                                        # R06 은 해석의 일반 문장이 그 몫이다
        self.assertNotIn("5.00Kp 이상이면 가장 낮은 단계의 지자기 폭풍", story(self.posts["r06_scales"]))
        self.assertIn("NOAA는 이 값이 5.00Kp 이상이면 가장 낮은 단계의 지자기 폭풍으로 분류하며", story(self.posts["r05_kp_storm"]))

    def test_the_sentences_have_no_number_no_number_word_and_no_forbidden_or_claiming_word(self):
        for name, (about, limit) in self.PAIRS.items():
            text = about + " " + limit
            with self.subTest(post=name):
                self.assertNotRegex(text, r"\d")
                self.assertEqual(F.untraced_numbers(text), [])
                self.assertEqual(A.forbidden_found(text), [])
                self.assertEqual(A.blocked_found(text), [])
                for claim in self.CLAIMS:
                    self.assertNotIn(claim, text)
                self.assertLessEqual(set(A.latin_words(F.REF_RE.sub("", text))), {"NOAA", "SWPC", "Kp"})
                self.assertNotRegex(text, r"[~～〜]")
                self.assertNotIn("http", text)

    def test_the_sentences_use_only_the_particles_that_do_not_depend_on_the_final_consonant_after_a_marker(self):
        for name, (about, limit) in self.PAIRS.items():
            with self.subTest(post=name):
                self.assertEqual(A.particle_problems(about + " " + limit), [])

    def test_the_background_is_for_the_post_it_is_in(self):
        """다른 글감의 설명이 섞이지 않는다 — 흑점수 글에 Kp 설명이, Kp 글에 흑점수 설명이 없다."""
        self.assertNotIn("흑점", story(self.posts["r04_kp"]) + story(self.posts["r05_kp_storm"]) + story(self.posts["r05_flares"]) + story(self.posts["r06_scales"]))
        for name in ("r04_ssn_daily", "r04_ssn_monthly", "r05_flares", "r06_scales"):
            self.assertNotIn("Kp는 지구 자기장이", story(self.posts[name]), name)
        self.assertNotIn("이 글의 값은 SWPC가 달마다", story(self.posts["r04_ssn_daily"]))
        self.assertNotIn("이 글의 값은 SWPC가 날마다", story(self.posts["r04_ssn_monthly"]))


class RecipeRegistryTest(unittest.TestCase):
    def test_the_new_recipes_are_declared_and_the_old_ones_are_untouched(self):
        self.assertEqual(sorted(RN.NOREGION_RECIPES), ["R04_NOREGION_SERIES", "R05_THRESHOLD_COUNT", "R06_SCALE_OUTLOOK"])
        self.assertEqual(sorted(R.RECIPES), ["R01_time_series", "R02_region_compare", "R03_record_position"])
        for recipe in RN.NOREGION_RECIPES.values():
            self.assertEqual(recipe.allowed_domains, ("space_weather",))
            self.assertEqual(recipe.version, 1)
            self.assertEqual(recipe.min_story_chars, R.MIN_STORY_CHARS)
            self.assertTrue(recipe.name_ko and recipe.summary)
            self.assertTrue(set(recipe.formulas) <= set(C.FORMULAS))
        self.assertEqual(set(R.TOPIC_CATEGORY), set(T.DOMAINS))
        self.assertEqual(R.TOPIC_CATEGORY["space_weather"], "과학·환경")

    def test_the_recipes_declare_the_formulas_they_really_use(self):
        used = {rid: set() for rid in RN.NOREGION_RECIPES}
        for name, (recipe_id, product_id, rows, params) in golden_cases().items():
            used[recipe_id] |= set(build(name).formulas)
        for recipe_id, formulas in used.items():
            with self.subTest(recipe=recipe_id):
                self.assertEqual(formulas, set(RN.NOREGION_RECIPES[recipe_id].formulas))

    def test_every_new_unit_and_label_word_is_in_the_unit_table_and_the_allow_list(self):
        domain = T.DOMAINS["space_weather"]
        for unit in domain.units:
            self.assertIn(unit, F.UNIT_TABLE)
        self.assertFalse(F.ratio_ok("단계"))
        self.assertTrue(F.ratio_ok("nW/㎡") and F.ratio_ok("개") and F.ratio_ok("%"))
        self.assertFalse(F.ratio_ok("Kp"))
        self.assertEqual(F.UNIT_TABLE["nW/㎡"].decimals, 0)

    def test_the_subject_table_is_complete(self):
        self.assertEqual([s.key for s in RN.SERIES_SUBJECTS], [KP_KEY, "space_weather.sunspot_daily_swpc", "space_weather.sunspot_monthly_swpc"])
        for subject in RN.SERIES_SUBJECTS:
            self.assertIn(subject.granularity, ("day", "month"))
            self.assertGreaterEqual(subject.min_points, 5)
            self.assertTrue(subject.cautions)
            for line in subject.cautions:
                self.assertTrue(line.startswith("- "))
                self.assertEqual(F.untraced_numbers(line), [], line)
            self.assertEqual(R.title_template_problem(f"⟦L:lbl⟧ {subject.title_word}, ⟦D:cur⟧ 기준"), None)


if __name__ == "__main__":
    unittest.main()
