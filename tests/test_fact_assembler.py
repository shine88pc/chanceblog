"""구조화 Fact 경로 1단계 — `pipeline/recipes.py`·`pipeline/fact_assembler.py` 시험: 가짜 데이터로 만든 골든 글(분량 하한·표·출처·모든 숫자가 Fact 에서 옴)·결정성(바이트까지 같음)·Insufficient·
비교 불가 시 문장 생략·금지 표현·Liquid 문자·물결표·글자 체계 혼용·글 머리말이 생성기의 `front_matter_problems` 규칙을 통과하는지(생성기 함수는 읽기 전용으로만 부른다 — `generator.py` 는 바꾸지 않는다).
네트워크·시계·난수 없이 돈다. 골든 글 파일을 다시 쓰려면 환경 변수 UPDATE_GOLDEN=1 로 실행한다."""
import dataclasses
import datetime
import os
import re
import subprocess
import sys
import types
import unittest
from unittest import mock

import _bootstrap
import fact_helpers as H

import generator as g       # 읽기 전용으로만 쓴다(머리말·분량 검사 함수를 불러 같은 규칙을 통과하는지 본다)
from pipeline import calc as C
from pipeline import fact_assembler as A
from pipeline import fact_topics as T
from pipeline import facts as F
from pipeline import recipes as R
from pipeline.adapters import mock_stats as M

ROOT = _bootstrap.ROOT
GOLDEN_DIR = ROOT / "tests" / "fixtures"
IMAGE = "https://example.invalid/fact-golden.svg"
LANES = {lane["kr_category"] for lane in g.EDITORIAL_LANES.values()}


def generator_file(post):
    """생성기가 쓸 글 파일 모양(머리말 + 본문)과 소스 항목. 생성기의 함수를 읽기 전용으로 불러 머리말을 만든다."""
    data = {"kr_title": post.title, "kr_category": post.category, "kr_tags": list(post.tags)}
    source = {"link": post.source_url, "source": post.source_name, "publisher_domain": post.source_domain, "title": post.source_name}
    return g.add_discovery_metadata(g._fresh_front_matter(data, "kr", "ko", IMAGE) + post.body_markdown, source), source


def number_set(text):
    return set(A.number_tokens(text))


def allowed_numbers(post):
    """글에 나와도 되는 숫자: 쓴 Fact·계산 결과의 값·기준일과 수집일의 숫자(시험이 따로 만든 목록 — 근거 텍스트를 쓰지 않는다)."""
    allowed = set()
    context = dict(post.decimals)
    for item in (*post.facts_used, *post.derived):
        if item.value is not None and (isinstance(item, F.DerivedFact) or item.kind in F.NUMERIC_KINDS):
            allowed |= number_set(F.format_with_unit(item.value, item.unit, signed=True, context=context))
        if item.as_of:
            allowed |= number_set(F.format_period_ko(item.as_of))
    for record in post.source_records:
        allowed |= number_set(F.format_period_ko(record.retrieved_at[:10]))
    return allowed


def wrapped(mutator, base=R.R01_TIME_SERIES, **replace):
    """base Recipe 의 plan 이 만든 Draft 를 mutator 로 일부러 망가뜨리는 Recipe(결함 시험용)."""
    def plan(ctx):
        draft = base.plan(ctx)
        if not isinstance(draft, R.Insufficient):
            mutator(draft)
        return draft
    return dataclasses.replace(base, plan=plan, **replace)


def add_caveat(text):
    return lambda draft: draft.caveats.append(text)


def revalue(fact, value):
    """같은 Fact 의 값만 바꿔 새로 만든다(id 가 내용에 맞게 다시 계산된다)."""
    return F.Fact.create(fact.provider_id, fact.source_record_id, fact.kind, fact.key, value, fact.unit, fact.as_of, fact.region, fact.region_level,
                         fact.region_label_ko, fact.region_label_en, fact.label_ko, fact.label_en)


def bundle_without_retention(retrieved_at=H.RETRIEVED_AT):
    """보관 기한이 없는 Provider 로 읽은 (Provider, 수집 기록, Fact) — 기한과 상관없이 신선도 경계만 보려고 쓴다."""
    provider = dataclasses.replace(M.MockProvider(), retention_days=None)
    adapter = M.MockStatsAdapter(provider)
    raw = adapter.fetch(provider.access[0], {}, M.make_mock_opener())
    record, facts = adapter.parse(raw, provider.access[0], retrieved_at, {})
    return provider, record, facts


def build_draft(recipe, facts, params, today=H.TODAY):
    ctx = R.PlanContext(recipe, tuple(sorted(facts, key=lambda f: f.fact_id)), F.as_date(today), dict(params))
    return recipe.plan(ctx)


class GoldenPostsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.posts = {rid: H.run(rid, params=params) for rid, params in H.GOLDEN.items()}

    def test_three_recipes_make_three_posts(self):
        self.assertEqual(set(R.RECIPES), set(H.GOLDEN))
        for rid, post in self.posts.items():
            with self.subTest(recipe=rid):
                self.assertIsInstance(post, A.AssembledPost)
                self.assertEqual((post.recipe_id, post.lang, post.as_of, post.source_name, post.source_url, post.source_domain),
                                 (rid, "ko", "2026-03", M.SOURCE_NAME, M.SOURCE_URL, "stats.mock.invalid"))
                self.assertEqual(post.recipe_version, 1)
                self.assertIn(post.category, LANES)
                self.assertEqual(post.category, "경제·일")
                self.assertTrue(post.tags and len(post.tags) <= 6 and len(set(post.tags)) == len(post.tags))
                for tag in post.tags:
                    self.assertTrue(0 < len(tag) <= 20 and not re.search(r"\d", tag), tag)
                self.assertRegex(post.dedupe_key, rf"\A{rid}\|labour\.[a-z_]+\|(?:R01|-)\|2026-03\Z")

    def test_the_golden_files_match_byte_for_byte(self):
        for rid, post in self.posts.items():
            content, _source = generator_file(post)
            path = GOLDEN_DIR / f"fact_golden_{rid.lower()}.md"
            if os.environ.get("UPDATE_GOLDEN") == "1":
                GOLDEN_DIR.mkdir(exist_ok=True)
                path.write_text(content, encoding="utf-8", newline="\n")
            with self.subTest(recipe=rid):
                self.assertTrue(path.exists(), f"{path.name} 이 없다 — UPDATE_GOLDEN=1 로 만든다")
                self.assertEqual(path.read_text(encoding="utf-8"), content)          # 줄바꿈은 \n 으로 읽힌다(윈도우 작업 트리의 CRLF 도 같다)

    def test_the_body_clears_the_length_floor_without_padding(self):
        for rid, post in self.posts.items():
            story = A.story_of(post.body_markdown)
            content, _source = generator_file(post)
            with self.subTest(recipe=rid):
                ours = A.readable_chars(story)
                self.assertGreaterEqual(ours, R.MIN_STORY_CHARS)
                body = re.match(r"\A---\s*\n.*?\n---\s*\n(.*)\Z", content, re.S).group(1)
                theirs = len(re.sub(r"\s+", "", re.sub(r"<[^>]+>|[`*_>#|~]", " ", re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", re.split(r"(?im)^##\s*(?:출처|참고 자료|sources)\s*$", body, maxsplit=1)[0]))))
                self.assertGreaterEqual(theirs, ours, "우리 분량은 생성기가 세는 분량보다 같거나 작다(보수적)")
                g._validate_editorial_body(content, "kr", post.source_url)                       # 생성기의 분량·원문 링크 검사를 그대로 통과한다

    def test_the_skeleton_is_the_agreed_one(self):
        for rid, post in self.posts.items():
            body = post.body_markdown
            with self.subTest(recipe=rid):
                self.assertEqual(tuple(re.findall(r"(?m)^## (.+)$", body)), R.SECTION_ORDER)
                self.assertTrue(body.startswith(post.description + "\n\n"))
                self.assertIn(f"[공식 자료]({M.SOURCE_URL})에서 2026년 4월 18일에 받아 옮긴 구조화 데이터입니다", body)
                self.assertRegex(body, r"(?m)^\|(?: :?-{3,}:? \|)+$")                        # 표의 구분 줄
                self.assertGreaterEqual(len(re.findall(r"(?m)^\|(?: :?-{3,}:? \|)+$", body)), 1)
                story, sources = re.split(r"(?m)^## 출처\n", body)
                self.assertIn(f"- [{M.SOURCE_NAME}]({M.SOURCE_URL}) — 열람 2026년 4월 18일", sources)
                self.assertIn("- 이용 조건: 이 자료는 시험을 위해 만든 가상의 통계입니다. 실제 기관의 통계가 아닙니다.", sources)
                self.assertTrue(sources.rstrip().endswith("확인해 주세요.*"))
                self.assertIn("\n---\n\n*이 글은 사람이 쓴 글이 아니라", sources)
                self.assertIn("- 제공처 안내: 제3자 자료와 이미지는 이 이용 허락에 포함되지 않습니다.", story)
                self.assertIn("**이 글의 해석**:", story)
                self.assertTrue(body.endswith("\n") and not body.endswith("\n\n"))

    def test_every_number_in_the_story_comes_from_a_fact(self):
        for rid, post in self.posts.items():
            story = A.story_of(post.body_markdown)
            with self.subTest(recipe=rid):
                found = number_set(story)
                self.assertTrue(found)
                self.assertLessEqual(found, allowed_numbers(post))
                self.assertLessEqual(found, number_set(post.evidence_text))
                self.assertLessEqual(number_set(post.title + "\n" + post.description), allowed_numbers(post))
                self.assertEqual(F.untraced_numbers(post.template_markdown), [])

    def test_values_match_a_hand_calculation_from_the_dataset(self):
        r01 = self.posts["R01_time_series"].body_markdown
        for fragment in ("값은 2026년 2월(3.2%)보다 0.3%p 높은 3.5%입니다(2026년 3월 기준).", "- 바로 앞 기간 대비: +0.3%p, 변화율 +9.4% (견준 기간 2026년 2월, 그때 값 3.2%)",
                         "- 전년 같은 달 대비: +0.2%p, 변화율 +6.1% (견준 기간 2025년 3월, 그때 값 3.3%)", "- 최근 3개월 평균: 3.3%",
                         "- 표시한 기간 안의 범위: 최저 2.9%(같은 값 2번, 가장 나중 2025년 9월)에서 최고 3.5%(2026년 3월)까지", "| 2026년 3월 | 3.5% | +0.3%p | +9.4% |",
                         "| 2025년 9월 | 2.9% | 0.0%p | 0.0% |", "| 2025년 4월 | 3.2% | −0.1%p | −3.0% |", "최근 3개월 평균 3.3%보다 0.2%p 높아서"):
            self.assertIn(fragment, r01)
        r02 = self.posts["R02_region_compare"].body_markdown
        for fragment in ("| 1위 | 가상 지역 마 | 4.2% | +0.8%p |", "| 6위 | 가상 지역 바 | 2.7% | −0.7%p |", "- 평균: 3.4%(6곳 단순 평균), 중앙값: 3.4%", "- 최고와 최저의 격차: 1.5%p",
                         "- 평균보다 높은 곳 3곳, 낮은 곳 3곳", "- 평균보다 낮은 곳: 가상 지역 나, 가상 지역 다, 가상 지역 바"):
            self.assertIn(fragment, r02)
        r03 = self.posts["R03_record_position"].body_markdown
        for fragment in ("안에서 가장 높은 3.5%입니다.", "- 자료 기간의 최저: 2.9%(같은 값 2번, 가장 나중 2025년 9월)", "- 범위 안의 위치: 100.0%", "- 최저와의 차이: +0.6%p",
                         "| 2026년 2월 | 3.2% | −0.3%p | +0.3%p |", "2025년 1월부터 2026년 3월까지 15개월입니다"):
            self.assertIn(fragment, r03)

    def test_text_hygiene(self):
        for rid, post in self.posts.items():
            body = post.body_markdown
            with self.subTest(recipe=rid):
                self.assertEqual(A.post_problems(post), [])
                self.assertEqual(A.forbidden_found(post.title + "\n" + post.description + "\n" + body), [])
                for mark in ("⟦", "⟧", "{{", "{%", "}}", "%}", "{", "}", "~", "～", "〜", "\r", "\t", "  ", "@SOURCE_LINK@"):
                    self.assertNotIn(mark, body)
                    self.assertNotIn(mark, post.title)
                self.assertFalse(re.search(r" +$", body, re.M), "줄 끝 공백")
                self.assertEqual(A.latin_words(A.story_of(body) + post.title), [], "영문 낱말이 섞임")
                self.assertIsNone(re.search(r"[぀-ヿ㐀-鿿]", body), "한자·가나가 섞임")
                self.assertIsNone(re.search(R.VARYING_PARTICLE_PATTERNS[2], body), "은(는) 같은 표현")
                self.assertEqual(len(re.findall(r"(?m)^#{1,6} ", body)), len(R.SECTION_ORDER))

    def test_generator_front_matter_rules_accept_the_post(self):
        for rid, post in self.posts.items():
            content, source = generator_file(post)
            with self.subTest(recipe=rid):
                self.assertEqual(g.front_matter_problems(content, source), [])
                front = re.match(r"\A---\n(.*?)\n---\n", content, re.S).group(1)
                self.assertIn(f"title: {g._json_line(post.title)}", front)
                self.assertIn(f"description: {g._json_line(post.description)}", front)           # 생성기가 본문 첫 문단에서 뽑는 설명과 우리 설명이 같다
                self.assertEqual(g._description_from_markdown(content), post.description)
                self.assertIn(f'source_url: "{post.source_url}"', front)
                self.assertIn("lang: ko", front)
                self.assertEqual(content.count("## 출처"), 1)                                    # 생성기가 출처 절을 하나 더 붙이지 않는다

    def test_titles_and_descriptions_fit(self):
        for rid, post in self.posts.items():
            with self.subTest(recipe=rid):
                self.assertTrue(0 < len(post.title) <= R.MAX_TITLE_CHARS, post.title)
                self.assertTrue(R.DESCRIPTION_MIN <= len(post.description) <= R.DESCRIPTION_MAX)
                self.assertEqual(post.description.count("."), 1 + len(re.findall(r"\d\.\d", post.description)))
                self.assertTrue(post.description.endswith("."))

    def test_provenance_is_complete(self):
        for rid, post in self.posts.items():
            with self.subTest(recipe=rid):
                derived_ids = {d.fact_id for d in post.derived}
                fact_ids = {f.fact_id for f in post.facts_used}
                self.assertTrue(fact_ids and derived_ids)
                for derived in post.derived:
                    self.assertEqual(F.validate_derived(derived), [])
                    self.assertTrue(set(derived.input_fact_ids) <= fact_ids | derived_ids)
                for fact in post.facts_used:
                    self.assertEqual(F.validate_fact(fact), [])
                    self.assertIn(fact.source_record_id, {r.record_id for r in post.source_records})
                for record in post.source_records:
                    self.assertEqual(F.validate_record(record), [])
                referenced = {ref for _kind, ref in F.references(post.template_markdown)}
                self.assertTrue(referenced <= fact_ids | derived_ids | {r.record_id for r in post.source_records})
                self.assertTrue(len(post.formulas) >= 2)
                self.assertEqual(post.formulas, tuple(sorted({d.formula_id for d in post.derived})))
                context = dict(post.decimals)
                for fact in post.facts_used:
                    self.assertIn(F.describe(fact, context), post.evidence_text)
                self.assertTrue(post.evidence_text.startswith("근거 자료(규칙 기반 조립, Fact 표)\n"))
                self.assertIn("수집: 2026년 4월 18일", post.evidence_text)
                for item in (*post.facts_used, *post.derived, *post.source_records):                      # 내부 번호(id)는 근거 텍스트에 없다 — 숫자를 품어 '근거 숫자'로 세어지면 안 된다(V-03)
                    self.assertNotIn(getattr(item, "fact_id", None) or item.record_id, post.evidence_text)
                self.assertIsNone(re.search(r"[0-9a-f]{16}", post.evidence_text))
                self.assertIsNone(re.search(r"F[0-9]{2}_", post.evidence_text))
                self.assertNotIn(M.PROVIDER_ID, post.evidence_text)

    def test_the_recipes_declare_the_formulas_they_really_use(self):
        used = {rid: set() for rid in R.RECIPES}
        for region in ("R01", "R02", "R03", "R04", "R05", "R06"):
            for rid in ("R01_time_series", "R03_record_position"):
                used[rid] |= set(H.run(rid, params={"key": H.UNEMP, "region": region}).formulas)
        used["R02_region_compare"] = set(self.posts["R02_region_compare"].formulas)
        for rid, formulas in used.items():
            with self.subTest(recipe=rid):
                self.assertEqual(formulas, set(R.RECIPES[rid].formulas))                  # 선언한 계산식과 실제로 쓴 계산식(여섯 지역에 걸쳐)이 같다
                self.assertTrue(set(self.posts[rid].formulas) <= set(R.RECIPES[rid].formulas))


class DeterminismTest(unittest.TestCase):
    def test_same_input_same_bytes_in_any_input_order(self):
        _provider, _record, facts = H.mock_bundle()
        for rid, params in H.GOLDEN.items():
            base = H.run(rid, params=params)
            with self.subTest(recipe=rid):
                self.assertEqual(H.run(rid, params=params), base)
                for order in (list(reversed(facts)), facts[37:] + facts[:37], sorted(facts, key=lambda f: (f.region or "", f.as_of or ""))):
                    again = H.run(rid, params=params, facts=order)
                    self.assertEqual(again.body_markdown.encode("utf-8"), base.body_markdown.encode("utf-8"))
                    self.assertEqual(again, base)

    def test_a_fresh_parse_of_the_same_bytes_gives_the_same_post(self):
        provider = M.MockProvider()
        adapter = M.MockStatsAdapter(provider)
        raw = adapter.fetch(provider.access[0], {}, M.make_mock_opener())
        record, facts = adapter.parse(raw, provider.access[0], H.RETRIEVED_AT, {})
        for rid, params in H.GOLDEN.items():
            again = H.run(rid, params=params, facts=facts, records=[record])
            self.assertEqual(again, H.run(rid, params=params))

    def test_the_post_does_not_depend_on_the_hash_seed(self):
        code = ("import sys\nsys.path.insert(0, sys.argv[1])\nsys.path.insert(0, sys.argv[1] + '/tests')\nimport fact_helpers as H\nfrom pipeline import facts as F\n"
                "for rid, params in H.GOLDEN.items():\n    post = H.run(rid, params=params)\n    print(rid, F.sha256_hex(post.body_markdown.encode('utf-8')), post.dedupe_key)\n")
        outputs = set()
        for seed in ("0", "7", "99999"):
            done = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", code, str(ROOT)], capture_output=True, text=True, timeout=240,
                                  env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONUTF8="1"))
            self.assertEqual(done.returncode, 0, done.stderr[-500:])
            outputs.add(done.stdout)
        self.assertEqual(len(outputs), 1)

    def test_inputs_are_not_changed_and_today_may_be_a_date_object(self):
        _provider, record, facts = H.mock_bundle()
        snapshot = list(facts)
        base = H.run("R01_time_series", params=H.R01_PARAMS)
        self.assertEqual(list(facts), snapshot)
        self.assertEqual(H.run("R01_time_series", params=H.R01_PARAMS, today=datetime.date(2026, 4, 20)), base)
        self.assertEqual(H.run("R01_time_series", params=H.R01_PARAMS, today=datetime.datetime(2026, 4, 20, 12, 0)), base)
        self.assertEqual(H.run("R01_time_series", params=H.R01_PARAMS, today="2026-04-21").body_markdown, base.body_markdown)     # 오늘이 하루 달라도 글은 같다(오늘은 신선도 검사에만 쓴다)


class BranchesTest(unittest.TestCase):
    """지역마다 부호·같음·기록 여부가 다르게 나오는 문장 변주(입력에서 계산되는 규칙뿐 — 난수 없음)."""

    def post(self, rid, region):
        return H.run(rid, params={"key": H.UNEMP, "region": region})

    def test_time_series_wording_follows_the_sign_of_the_change(self):
        expect = {"R01": ("높은", "높아"), "R02": ("낮은", "낮아"), "R03": ("달라지지 않은", "같아"), "R04": ("달라지지 않은", "같아"),
                  "R05": ("달라지지 않은", "같아"), "R06": ("높은", "높아")}
        for region, (lead_word, title_word) in expect.items():
            post = self.post("R01_time_series", region)
            with self.subTest(region=region):
                self.assertIsInstance(post, A.AssembledPost)
                self.assertIn(lead_word, post.description)
                self.assertTrue(post.title.endswith("숫자로 읽기"), post.title)                  # 제목에는 값도 방향도 없다(D-200) — 방향은 설명과 본문에
                self.assertNotIn(title_word, post.title)
                self.assertIn(H.obs(region, "2026-03").region_label_ko, post.title)

    def test_record_sentences(self):
        highest, lowest, between = "표에서 가장 높은 값이 바로 최신 값입니다.", "표에서 가장 낮은 값이 바로 최신 값입니다.", "표에서 가장 높은 값은 "
        for region, sentence in (("R01", highest), ("R02", lowest), ("R03", between), ("R06", between)):
            with self.subTest(region=region):
                self.assertIn(sentence, self.post("R01_time_series", region).body_markdown)
        self.assertIn("가장 낮은 값은 ", self.post("R01_time_series", "R03").body_markdown)
        # 같은 값이 앞 기간에도 있으면 '바로 최신 값' 이라고 단정하지 않는다(V-06): R04 는 최신 두 달이 모두 최고(3.8%), R05 는 최신 두 달이 모두 최저(4.2%)
        tied_high, tied_low = self.post("R01_time_series", "R04").body_markdown, self.post("R01_time_series", "R05").body_markdown
        self.assertIn("최신 값은 표에서 가장 높은 값과 같고, 그 값은 표에 2번 나옵니다.", tied_high)
        self.assertNotIn("표에서 가장 높은 값이 바로 최신 값입니다.", tied_high)
        self.assertIn("최신 값은 표에서 가장 낮은 값과 같고, 그 값은 표에 2번 나옵니다.", tied_low)
        self.assertNotIn("표에서 가장 낮은 값이 바로 최신 값입니다.", tied_low)

    def test_record_position_branches(self):
        high, low, mid = self.post("R03_record_position", "R01"), self.post("R03_record_position", "R02"), self.post("R03_record_position", "R04")
        self.assertIn("안에서 가장 높은 3.5%입니다", high.description)
        self.assertIn("범위의 맨 위에 있습니다", high.body_markdown)
        self.assertNotIn("- 최고와의 차이", high.body_markdown)
        self.assertIn("안에서 가장 낮은 3.3%입니다", low.description)
        self.assertIn("범위의 맨 아래에 있습니다", low.body_markdown)
        self.assertNotIn("- 최저와의 차이", low.body_markdown)
        self.assertIn("최저와 최고 사이 80.0% 지점에 놓인 3.8%입니다", mid.description)
        self.assertIn("- 최고와의 차이: −0.1%p, 최고 대비 변화율 −2.6%", mid.body_markdown)
        self.assertIn("- 최저와의 차이: +0.4%p", mid.body_markdown)
        self.assertIn("최신 값은 최고보다 0.1%p 낮고 최저보다 0.4%p 높아, 범위의 안쪽에 있습니다.", mid.body_markdown)

    def test_a_missing_month_is_shown_as_unknown_not_zero(self):
        post = self.post("R01_time_series", "R06")
        rows = [line for line in post.body_markdown.split("\n") if line.startswith("| 202")]
        by_period = {row.split(" | ")[0].lstrip("| "): row for row in rows}
        self.assertEqual(by_period["2025년 9월"], "| 2025년 9월 | 자료 없음 | 해당 없음 | 해당 없음 |")
        self.assertEqual(by_period["2025년 10월"], "| 2025년 10월 | 2.7% | 해당 없음 | 해당 없음 |")           # 앞 달이 모름이라 증감을 만들지 않는다
        self.assertEqual(by_period["2025년 8월"], "| 2025년 8월 | 2.8% | 0.0%p | 0.0% |")
        self.assertNotIn("| 2025년 9월 | 0", post.body_markdown)

    def test_every_region_makes_a_clean_post_with_each_recipe(self):
        for region in ("R01", "R02", "R03", "R04", "R05", "R06"):
            for rid in ("R01_time_series", "R03_record_position"):
                with self.subTest(region=region, recipe=rid):
                    post = self.post(rid, region)
                    self.assertIsInstance(post, A.AssembledPost)
                    self.assertEqual(A.post_problems(post), [])
                    self.assertGreaterEqual(A.readable_chars(A.story_of(post.body_markdown)), R.MIN_STORY_CHARS)
                    self.assertEqual(g.front_matter_problems(*generator_file(post)), [])


class OmissionTest(unittest.TestCase):
    """비교할 수 없으면 그 문장을 만들지 않는다."""

    def test_no_previous_period_means_no_comparison_sentence(self):
        series = [f for f in H.series_of("R01") if f.as_of != "2026-02"]
        post = H.run("R01_time_series", facts=series, params=H.R01_PARAMS)
        self.assertIsInstance(post, A.AssembledPost)
        for text in ("바로 앞 기간 대비:", "앞 기간보다", "달라지지 않은", "평균 3"):
            self.assertNotIn(text, post.body_markdown + post.title)
        self.assertIn("(이 글이 읽은 관측 14개 자료의 마지막 값)", post.description)      # 2026년 2월이 빠졌으니 '14개월'(기간)이 아니라 관측 14개 — 개수를 기간으로 말하지 않는다(V-04)
        self.assertNotIn("개월 자료", post.description)
        self.assertIn("| 2026년 3월 | 3.5% | 해당 없음 | 해당 없음 |", post.body_markdown)
        self.assertEqual(post.skipped, ())                                  # 만들 수 없는 값은 계산을 시도하지도 않았다
        self.assertIn("F03_yoy", post.formulas)

    def test_no_year_before_means_no_year_over_year_text(self):
        series = [f for f in H.series_of("R01") if f.as_of != "2025-03"]
        post = H.run("R01_time_series", facts=series, params=H.R01_PARAMS)
        self.assertNotIn("- 전년 같은 달 대비", post.body_markdown)
        self.assertNotIn("전년 같은 기간(", post.body_markdown)
        self.assertNotIn("F03_yoy", post.formulas)
        self.assertIn("전년 같은 기간과도 견주어", post.body_markdown)       # 주의 줄은 '자료가 있으면'이라는 조건으로 늘 같다

    def test_a_zero_base_makes_no_ratio_but_keeps_the_difference(self):
        series = [revalue(f, "0") if f.as_of == "2026-02" else f for f in H.series_of("R01")]
        post = H.run("R01_time_series", facts=series, params=H.R01_PARAMS)
        self.assertIsInstance(post, A.AssembledPost)
        line = next(line for line in post.body_markdown.split("\n") if line.startswith("- 바로 앞 기간 대비:"))
        self.assertEqual(line, "- 바로 앞 기간 대비: +3.5%p (견준 기간 2026년 2월, 그때 값 0.0%)")
        self.assertIn(("pct", "F02_pct_change", "DIVISION_BY_ZERO"), post.skipped)
        self.assertIn("| 2026년 3월 | 3.5% | +3.5%p | 해당 없음 |", post.body_markdown)

    def _extra(self, **kw):
        _provider, record, _facts = H.mock_bundle()
        return H.make_fact(kw.pop("value", "3.9"), region="R07", region_label="가상 지역 사", record_id=record.record_id, **kw)

    def test_region_compare_leaves_out_values_that_cannot_be_compared(self):
        _provider, _record, facts = H.mock_bundle()
        base = H.run("R02_region_compare", params=H.R02_PARAMS)
        for name, extra in (("단위가 다름", self._extra(unit="명", value="1200")), ("기준일이 다름", self._extra(period="2026-02")),
                            ("지표 정의가 다름", self._extra(key="labour.employment_rate")), ("지역 수준이 다름", self._extra(level="city")),
                            ("제공처가 다름", self._extra(provider="other_stats")), ("값이 없음(모름)", self._extra(value=None))):
            with self.subTest(case=name):
                post = H.run("R02_region_compare", params=H.R02_PARAMS, facts=list(facts) + [extra])
                if name == "제공처가 다름":                                   # 다른 제공처의 Fact 는 아예 읽지 않는다
                    self.assertEqual(post, base)
                    continue
                self.assertIsInstance(post, A.AssembledPost)
                self.assertEqual(post.body_markdown, base.body_markdown)
                self.assertNotIn("가상 지역 사", post.body_markdown)

    def test_an_unknown_value_drops_the_region_instead_of_counting_zero(self):
        _provider, _record, facts = H.mock_bundle()
        target = H.obs("R06", "2026-03")
        blank = revalue(target, None)
        post = H.run("R02_region_compare", params=H.R02_PARAMS, facts=[f for f in facts if f.fact_id != target.fact_id] + [blank])
        self.assertIn("5곳의 실업률", post.description)
        self.assertNotIn("가상 지역 바", post.body_markdown)
        self.assertIn("- 평균: 3.5%(5곳 단순 평균), 중앙값: 3.5%", post.body_markdown)

    def test_other_keys_and_units_in_the_pool_do_not_disturb_the_chosen_series(self):
        post_all = H.run("R01_time_series", params=H.R01_PARAMS)
        only = H.run("R01_time_series", params=H.R01_PARAMS, facts=H.series_of("R01"))
        self.assertEqual(post_all.body_markdown, only.body_markdown)


class OtherPeriodKindsTest(unittest.TestCase):
    """분기·연 시계열도 같은 규칙으로 글이 된다(가짜 어댑터는 월 자료만 주므로 시험이 직접 만든 Fact 로)."""

    def series(self, periods, values, **kw):
        _provider, record, _facts = H.mock_bundle()
        return [H.make_fact(value, period=period, region="R01", record_id=record.record_id, **kw) for period, value in zip(periods, values)]

    def test_quarterly_series(self):
        facts = self.series(["2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"], ["3.1", "3.0", "3.2", "3.3", "3.4", "3.1", "3.5", "3.6"])
        for rid in ("R01_time_series", "R03_record_position"):
            with self.subTest(recipe=rid):
                post = H.run(rid, facts=facts, params={}, today="2026-08-01")
                self.assertIsInstance(post, A.AssembledPost, post)
                self.assertEqual(A.post_problems(post), [])
                self.assertEqual(g.front_matter_problems(*generator_file(post)), [])
                self.assertIn("2026년 2분기", post.body_markdown)
                self.assertEqual(post.as_of, "2026-Q2")
        body = H.run("R01_time_series", facts=facts, params={}, today="2026-08-01").body_markdown
        for fragment in ("- 최근 3분기 평균: 3.4%", "- 전년 같은 기간 대비: +0.3%p, 변화율 +9.1% (견준 기간 2025년 2분기, 그때 값 3.3%)", "| 2026년 2분기 | 3.6% | +0.1%p | +2.9% |"):
            self.assertIn(fragment, body)
        self.assertNotIn("개월", body)

    def test_yearly_series(self):
        facts = self.series([str(year) for year in range(2018, 2026)], ["2.0", "2.1", "2.4", "2.2", "2.5", "2.6", "2.4", "2.8"])
        for rid in ("R01_time_series", "R03_record_position"):
            with self.subTest(recipe=rid):
                post = H.run(rid, facts=facts, params={}, today="2026-06-01")
                self.assertIsInstance(post, A.AssembledPost, post)
                self.assertEqual(A.post_problems(post), [])
                self.assertIn("2025년", post.title)
        body = H.run("R01_time_series", facts=facts, params={}, today="2026-06-01").body_markdown
        self.assertIn("- 최근 3년 평균: 2.6%", body)
        self.assertIn("| 2025년 | 2.8% | +0.4%p | +16.7% |", body)
        self.assertEqual(H.run("R01_time_series", facts=facts, params={}, today="2027-07-01").code, "STALE")

    def test_instant_series_and_mixed_kinds_are_refused(self):
        instants = self.series([f"2026-03-0{day}T09:00:00Z" for day in range(1, 9)], ["1", "2", "3", "4", "5", "6", "7", "8"], unit="명")
        self.assertEqual(H.run("R01_time_series", facts=instants, params={}, today="2026-04-01").code, "MIXED_PERIOD_KIND")


SHORT_VOCABULARY = dataclasses.replace(T.VOCABULARY, regions=T.VOCABULARY.regions | frozenset("가나다라마바"))      # 시험용: 한 글자 지역 이름도 허용(실제 허용 목록에는 없다)


def short(recipe):
    return dataclasses.replace(recipe, vocabulary=SHORT_VOCABULARY)


class ShortTextTest(unittest.TestCase):
    """라벨·지역 이름·날짜 표기가 아주 짧아도 첫 문단(= 설명)이 60자 이상 한 문장이다 — 짧으면 읽은 자료 길이·평균을 덧붙인 후보로 넘어간다."""

    def facts(self, values, *, periods=None, regions=None, unit="%", label="율", region_label="가"):
        _provider, record, _facts = H.mock_bundle()
        if regions:
            return [H.make_fact(v, period=periods[0], unit=unit, region=f"R0{i}", region_label=n, label=label, record_id=record.record_id)
                    for i, (v, n) in enumerate(zip(values, regions), start=1)]
        return [H.make_fact(v, period=p, unit=unit, region="R01", region_label=region_label, label=label, record_id=record.record_id) for p, v in zip(periods, values)]

    def test_the_second_candidate_is_used_when_the_first_is_too_short(self):
        yearly = self.facts(["2.0", "2.1", "2.4", "2.2", "2.5", "2.6", "2.4", "2.8"], periods=[str(y) for y in range(2018, 2026)])
        post = H.run(short(R.R01_TIME_SERIES), facts=yearly, params={}, today="2026-06-01")
        self.assertIsInstance(post, A.AssembledPost)
        self.assertEqual(post.description, "가의 율 값은 2024년(2.4%)보다 0.4%p 높은 2.8%입니다(2025년 기준, 이 글이 읽은 8년 자료의 마지막 값).")
        counts = self.facts(["7", "6", "5", "3", "2", "1"], periods=["2025"], regions=["가", "나", "다", "라", "마", "바"], unit="명", label="수")        # 평균 4·중앙값 4(N3: 중앙값이 4.5 처럼 반 칸에 걸리면 한 자리가 늘어 글이 길어진다)
        post = H.run(short(R.R02_REGION_COMPARE), facts=counts, params={}, today="2026-06-01")
        self.assertIsInstance(post, A.AssembledPost)
        self.assertEqual(post.description, "2025년 기준 6곳의 수 값을 견주면 가장 높은 곳은 가(7명), 가장 낮은 곳은 바(1명)입니다(평균 4명).")
        for result in (H.run(short(R.R01_TIME_SERIES), facts=yearly, params={}, today="2026-06-01"), post):
            self.assertEqual(A.post_problems(result), [])
            self.assertEqual(g.front_matter_problems(*generator_file(result)), [])

    def test_the_record_recipe_first_paragraph_clears_the_floor_even_with_the_shortest_words(self):
        yearly = self.facts(["2.0", "2.1", "2.4", "2.2", "2.5", "2.6", "2.4", "2.8"], periods=[str(y) for y in range(2018, 2026)])
        post = H.run(short(R.R03_RECORD_POSITION), facts=yearly, params={}, today="2026-06-01")
        self.assertIsInstance(post, A.AssembledPost)
        self.assertGreaterEqual(len(post.description), R.DESCRIPTION_MIN)
        self.assertEqual(post.description, "2025년 기준 가의 율 값은 이 글이 읽은 자료(2018년부터 2025년까지) 안에서 가장 높은 2.8%입니다.")
        regional = self.facts(["3.5", "3.3", "2.9", "3.8", "4.2", "2.7"], periods=["2025"], regions=["가", "나", "다", "라", "마", "바"])
        post = H.run(short(R.R02_REGION_COMPARE), facts=regional, params={}, today="2026-06-01")
        self.assertGreaterEqual(len(post.description), R.DESCRIPTION_MIN)

    def test_a_first_paragraph_that_never_fits_makes_no_post(self):
        def plan(ctx):
            draft = R.R01_TIME_SERIES.plan(ctx)
            draft.leads[:] = ["⟦L:main⟧ 값입니다."]
            return draft
        result = H.run(dataclasses.replace(R.R01_TIME_SERIES, plan=plan), params=H.R01_PARAMS)
        self.assertIsInstance(result, R.Insufficient)
        self.assertEqual(result.code, "DESCRIPTION_LENGTH")

    def test_a_title_that_never_fits_makes_no_post(self):
        def plan(ctx):
            draft = R.R01_TIME_SERIES.plan(ctx)
            draft.titles[:] = ["⟦R:main⟧ ⟦L:main⟧ " * 8]
            return draft
        result = H.run(dataclasses.replace(R.R01_TIME_SERIES, plan=plan), params=H.R01_PARAMS)
        self.assertIsInstance(result, R.Insufficient)
        self.assertEqual(result.code, "TITLE_LENGTH")


class InsufficientTest(unittest.TestCase):
    def code(self, result):
        self.assertIsInstance(result, R.Insufficient, result)
        self.assertFalse(result)
        self.assertTrue(result.detail)
        return result.code

    def test_data_that_is_too_thin(self):
        r01 = H.series_of("R01")
        self.assertEqual(self.code(H.run("R01_time_series", facts=[], params=H.R01_PARAMS)), "NO_FACTS")
        self.assertEqual(self.code(H.run("R01_time_series", facts=[f for f in H.mock_bundle()[2] if f.kind == F.KIND_API_VERSION])), "NO_FACTS")
        self.assertEqual(self.code(H.run("R01_time_series", facts=r01[-5:], params=H.R01_PARAMS)), "TOO_FEW_POINTS")
        self.assertEqual(self.code(H.run("R03_record_position", facts=r01[-7:], params=H.R01_PARAMS)), "TOO_FEW_POINTS")
        r06 = H.series_of("R06")
        self.assertEqual(self.code(H.run("R01_time_series", facts=r06[8:14], params={"key": H.UNEMP, "region": "R06"})), "TOO_FEW_POINTS")     # 여섯 달 가운데 하나가 모름이면 점은 다섯이다
        three = [f for f in H.mock_bundle()[2] if f.region in ("R01", "R02", "R03") and f.as_of == "2026-03" and f.key == H.UNEMP]
        self.assertEqual(self.code(H.run("R02_region_compare", facts=three, params=H.R02_PARAMS)), "TOO_FEW_REGIONS")
        self.assertEqual(self.code(H.run("R01_time_series", params={"key": "labour.nothing"})), "NO_FACTS")
        self.assertEqual(self.code(H.run("R01_time_series", params={"key": H.UNEMP, "region": "R99"})), "NO_FACTS")

    def test_thin_but_allowed_data_is_refused_when_the_story_would_be_too_short(self):
        """데이터가 얇을수록 글이 짧아진다: 하한 아래면 글 대신 TOO_SHORT 이고, 글이 나왔다면 늘 하한 이상이다(근거 없는 문장으로 채우지 않는다)."""
        r01 = H.series_of("R01")
        self.assertEqual(self.code(H.run(dataclasses.replace(R.R01_TIME_SERIES, min_points=2), facts=r01[-2:], params=H.R01_PARAMS)), "TOO_SHORT")
        for k in (2, 3, 4, 5):
            result = H.run(dataclasses.replace(R.R01_TIME_SERIES, min_points=k), facts=r01[-k:], params=H.R01_PARAMS)
            with self.subTest(points=k):
                if isinstance(result, R.Insufficient):
                    self.assertEqual(result.code, "TOO_SHORT")
                else:
                    self.assertGreaterEqual(A.readable_chars(A.story_of(result.body_markdown)), R.MIN_STORY_CHARS)
        two = [f for f in H.mock_bundle()[2] if f.region in ("R01", "R02") and f.as_of == "2026-03" and f.key == H.UNEMP]
        result = H.run(dataclasses.replace(R.R02_REGION_COMPARE, min_points=2), facts=two, params=H.R02_PARAMS)
        self.assertTrue(isinstance(result, R.Insufficient) and result.code == "TOO_SHORT" or A.readable_chars(A.story_of(result.body_markdown)) >= R.MIN_STORY_CHARS)

    def test_the_length_floor_is_a_recipe_setting_and_the_default_is_the_generators(self):
        self.assertEqual(R.MIN_STORY_CHARS, g.MIN_BODY_CHARS["kr"])
        for recipe in R.RECIPES.values():
            self.assertEqual(recipe.min_story_chars, g.MIN_BODY_CHARS["kr"])
        huge = dataclasses.replace(R.R01_TIME_SERIES, min_story_chars=100000)
        self.assertEqual(self.code(H.run(huge, params=H.R01_PARAMS)), "TOO_SHORT")
        size = A.readable_chars(A.story_of(H.run("R01_time_series", params=H.R01_PARAMS).body_markdown))
        self.assertIsInstance(H.run(dataclasses.replace(R.R01_TIME_SERIES, min_story_chars=size), params=H.R01_PARAMS), A.AssembledPost)      # 딱 하한이면 통과
        self.assertEqual(self.code(H.run(dataclasses.replace(R.R01_TIME_SERIES, min_story_chars=size + 1), params=H.R01_PARAMS)), "TOO_SHORT")  # 한 글자 모자라면 거부

    def test_stale_and_future_data(self):
        self.assertEqual(self.code(H.run("R01_time_series", params=H.R01_PARAMS, today="2027-08-01")), "STALE")
        self.assertEqual(self.code(H.run("R03_record_position", params=H.R01_PARAMS, today="2027-08-01")), "STALE")
        self.assertEqual(self.code(H.run("R02_region_compare", params=H.R02_PARAMS, today="2027-08-01")), "STALE")
        provider, record, facts = bundle_without_retention("2026-01-02T00:00:00Z")      # 보관 기한이 신선도 경계를 가리지 않게, 수집일은 모든 시험 날짜보다 앞서게
        kw = dict(facts=facts, records=[record], provider=provider, params=H.R01_PARAMS)
        self.assertIsInstance(H.run("R01_time_series", today="2027-06-24", **kw), A.AssembledPost)          # 마지막 날(2026-03-31)로부터 450일 — 경계는 통과
        self.assertEqual(self.code(H.run("R01_time_series", today="2027-06-25", **kw)), "STALE")             # 451일
        self.assertEqual(self.code(H.run("R01_time_series", today="2026-02-15", **kw)), "FUTURE_DATA")
        self.assertIsInstance(H.run("R01_time_series", today="2026-03-01", **kw), A.AssembledPost)             # 그 달이 막 시작된 날부터는 쓴다
        self.assertEqual(self.code(H.run("R01_time_series", params=H.R01_PARAMS, today="내일")), "BAD_TODAY")
        self.assertEqual(self.code(H.run("R01_time_series", params=H.R01_PARAMS, today="2026-04-17")), "FUTURE_RECORD")       # 수집일(2026-04-18)이 오늘보다 뒤인 기록은 쓰지 않는다
        self.assertIsInstance(H.run("R01_time_series", params=H.R01_PARAMS, today="2026-04-18"), A.AssembledPost)

    def test_topics_that_are_blocked_or_unknown(self):
        _provider, record, _facts = H.mock_bundle()
        periods = [f"2025-{m:02d}" for m in range(1, 13)] + ["2026-01", "2026-02", "2026-03"]
        for key, rid in (("health.mortality_rate", "R01_time_series"), ("medical.visits", "R03_record_position"), ("invest.stock_index", "R02_region_compare"),
                         ("legal.cases", "R01_time_series"), ("crypto.price", "R01_time_series"), ("sports.scores", "R01_time_series")):
            facts = [H.make_fact(str(10 + i), key=key, period=p, region="R01", record_id=record.record_id) for i, p in enumerate(periods)]
            facts += [H.make_fact(str(10 + i), key=key, period="2026-03", region=f"R0{i}", record_id=record.record_id) for i in range(2, 8)]
            with self.subTest(key=key):
                expected = "UNKNOWN_TOPIC" if key.startswith("sports.") else "TOPIC_NOT_ALLOWED"           # 막힌 주제와 '허용 목록에 없음'은 사유 코드가 다르다
                self.assertEqual(self.code(H.run(rid, facts=facts, params={})), expected)
        blocked = [H.make_fact("5", key="health.mortality_rate", period=f"2025-{m:02d}", record_id=record.record_id) for m in range(1, 10)]
        self.assertEqual(H.run("R01_time_series", facts=list(H.mock_bundle()[2]) + blocked, params={}), H.run("R01_time_series", params={}))     # 막힌 계열은 있어도 글에 영향이 없다
        self.assertFalse(set(R.ALLOWED_DOMAINS) & F.BLOCKED_TOPICS)
        self.assertEqual(set(R.ALLOWED_DOMAINS), set(R.TOPIC_CATEGORY))
        self.assertEqual(set(R.ALLOWED_DOMAINS), set(T.DOMAINS))
        self.assertTrue(set(R.TOPIC_CATEGORY.values()) <= LANES)

    def test_every_blocked_topic_has_its_own_check(self):
        """막힌 주제는 하나씩 사유 코드 TOPIC_NOT_ALLOWED 로 막힌다(허용 목록 밖이라는 UNKNOWN_TOPIC 이 가려 주지 못하게)."""
        _provider, record, _facts = H.mock_bundle()
        for topic in sorted(F.BLOCKED_TOPICS):
            fact = H.make_fact("5", key=f"{topic}.index", period="2026-03", record_id=record.record_id)
            with self.subTest(topic=topic):
                self.assertEqual(R.topic_problem(R.R01_TIME_SERIES, fact).code, "TOPIC_NOT_ALLOWED")
        self.assertEqual(sorted(F.BLOCKED_TOPICS), sorted({"health", "medical", "pharma", "drug", "invest", "securities", "stock", "crypto", "legal"}))

    def test_a_blocked_topic_stays_blocked_even_if_a_recipe_were_misconfigured_to_allow_it(self):
        _provider, record, _facts = H.mock_bundle()
        periods = [f"2025-{m:02d}" for m in range(1, 13)] + ["2026-01", "2026-02", "2026-03"]
        facts = [H.make_fact(str(10 + i), key="health.mortality_rate", period=p, region="R01", record_id=record.record_id) for i, p in enumerate(periods)]
        careless = dataclasses.replace(R.R01_TIME_SERIES, allowed_domains=R.ALLOWED_DOMAINS + ("health",))
        loose = dataclasses.replace(T.VOCABULARY, domains={**T.DOMAINS, "health": dataclasses.replace(T.DOMAINS["labour"], domain_id="health")})
        careless = dataclasses.replace(careless, vocabulary=loose)
        self.assertEqual(R.topic_problem(careless, facts).code, "TOPIC_NOT_ALLOWED")
        result = H.run(careless, facts=facts, params={})
        self.assertEqual(self.code(result), "TOPIC_NOT_ALLOWED")
        self.assertIn("건강", result.detail)                                  # 막힌 주제라서 막혔다(허용 목록 밖이라서가 아니다)
        self.assertIsNone(R.topic_problem(R.R01_TIME_SERIES, H.obs("R01", "2026-03")))

    def test_inconsistent_series(self):
        _provider, record, _facts = H.mock_bundle()
        r01 = H.series_of("R01")
        mixed = r01 + [H.make_fact("3.3", period="2026-Q1", record_id=record.record_id)]
        self.assertEqual(self.code(H.run("R01_time_series", facts=mixed, params=H.R01_PARAMS)), "MIXED_PERIOD_KIND")
        twice = r01 + [H.make_fact("9.9", period="2026-03", record_id=record.record_id)]
        self.assertEqual(self.code(H.run("R01_time_series", facts=twice, params=H.R01_PARAMS)), "DUPLICATE_PERIOD")
        cross = [f for f in H.mock_bundle()[2] if f.as_of == "2026-03" and f.key == H.UNEMP] + [H.make_fact("9.9", record_id=record.record_id)]
        self.assertEqual(self.code(H.run("R02_region_compare", facts=cross, params=H.R02_PARAMS)), "DUPLICATE_REGION")

    def test_the_provider_and_the_source_are_checked_again(self):
        provider = M.MockProvider()
        for over in ({"strict_tier": 3}, {"effective_status": "자동화 제외"}, {"effective_status": "완전 제외"}):
            with self.subTest(over=over):
                self.assertEqual(self.code(H.run("R01_time_series", params=H.R01_PARAMS, provider=dataclasses.replace(provider, **over))), "PROVIDER_NOT_ACTIVE")
        self.assertEqual(self.code(H.run("R01_time_series", params=H.R01_PARAMS, provider=object())), "PROVIDER_NOT_ACTIVE")
        for name, url in (("[이름]", M.SOURCE_URL), ("이름", "http://stats.mock.invalid/x"), ("이름", "https://stats.mock.invalid/x(y)"), ("이름", "https://stats.mock.invalid/x?api_key=abc"),
                          ("", M.SOURCE_URL), ("이름\n", M.SOURCE_URL), ("이름", "https://")):
            with self.subTest(name=name, url=url):
                self.assertEqual(self.code(H.run("R01_time_series", params=H.R01_PARAMS, source=A.SourceInfo(provider, name, url))), "SOURCE_INFO_INVALID")
        self.assertEqual(self.code(H.run("R01_time_series", params=H.R01_PARAMS, source="아무 글자")), "SOURCE_INFO_INVALID")

    def test_other_providers_facts_are_ignored(self):
        _provider, record, facts = H.mock_bundle()
        foreign = [F.Fact.create("other_stats", f.source_record_id, f.kind, f.key, f.value, f.unit, f.as_of, f.region, f.region_level, f.region_label_ko,
                                 f.region_label_en, f.label_ko, f.label_en) for f in facts]
        self.assertEqual(self.code(H.run("R01_time_series", facts=foreign, params=H.R01_PARAMS)), "NO_FACTS")
        self.assertEqual(H.run("R01_time_series", facts=list(facts) + foreign, params=H.R01_PARAMS), H.run("R01_time_series", params=H.R01_PARAMS))

    def test_invalid_facts_and_records_are_refused_not_skipped(self):
        _provider, record, facts = H.mock_bundle()
        broken = [dataclasses.replace(facts[1], fact_id="f" + "0" * 16)] + list(facts[2:])
        self.assertEqual(self.code(H.run("R01_time_series", facts=broken, params=H.R01_PARAMS)), "INVALID_FACTS")
        self.assertEqual(self.code(H.run("R01_time_series", records=[dataclasses.replace(record, response_hash="x")], params=H.R01_PARAMS)), "INVALID_FACTS")
        self.assertEqual(self.code(H.run("R01_time_series", records=[], params=H.R01_PARAMS)), "MISSING_RECORD")
        other = F.SourceRecord.create("other_stats", "api", "https://stats.mock.invalid/v1/series", H.RETRIEVED_AT, "b" * 64, "tier=2", 365)
        self.assertEqual(self.code(H.run("R01_time_series", records=[other], params=H.R01_PARAMS)), "MISSING_RECORD")

    def test_expired_records_are_not_used(self):
        self.assertEqual(self.code(H.run("R01_time_series", params=H.R01_PARAMS, today="2027-05-01")), "RETENTION_EXPIRED")
        self.assertIsInstance(H.run("R01_time_series", params=H.R01_PARAMS, today="2027-04-18"), A.AssembledPost)
        self.assertEqual(self.code(H.run("R01_time_series", params=H.R01_PARAMS, today="2027-04-19")), "RETENTION_EXPIRED")

    def test_unsafe_reader_notes_are_refused(self):
        provider = M.MockProvider()
        for notes in (("2024년 이전 자료는 제외합니다",), ("{{ x }}",), ("물결~표",), ("줄\n바꿈",), ("",), ("⟦F:x⟧",), ("한 곳을 뺍니다",), (7,), ("가" * 121,),
                      ("이 자료로 반드시 돈을 법니다",), ("무 조건 믿으세요",), ("환자에게 효 능이 있습니다",), ("주식 사세요",)):
            with self.subTest(notes=notes):
                result = H.run("R01_time_series", params=H.R01_PARAMS, provider=dataclasses.replace(provider, reader_notes=notes))
                self.assertEqual(self.code(result), "READER_NOTE_UNSAFE")
        for template in ("{unknown} 이용", "이용 조건 ~", "이용 {{x}}", "⟦T:x⟧"):
            with self.subTest(template=template):
                self.assertEqual(self.code(H.run("R01_time_series", params=H.R01_PARAMS, provider=dataclasses.replace(provider, attribution_template=template))), "ATTRIBUTION_TEMPLATE_INVALID")

    def test_provider_texts_that_are_fine_are_used(self):
        provider = dataclasses.replace(M.MockProvider(), reader_notes=("제3자 자료는 제외됩니다", "이미지와 로고는 제외됩니다."), attribution_template="{title} 자료를 {date}에 받았습니다. 주소 {url}")
        post = H.run("R01_time_series", params=H.R01_PARAMS, provider=provider)
        self.assertIsInstance(post, A.AssembledPost)
        self.assertIn("- 제공처 안내: 제3자 자료는 제외됩니다.\n- 제공처 안내: 이미지와 로고는 제외됩니다.\n", post.body_markdown)
        self.assertIn(f"- 이용 조건: {M.SOURCE_NAME} 자료를 2026년 4월 18일에 받았습니다. 주소 {M.SOURCE_URL}\n", post.body_markdown)
        none = dataclasses.replace(M.MockProvider(), reader_notes=(), attribution_template=None, policy={"attribution": {"state": "ALLOWED"}})        # 출처 표시 의무가 없다고 명시한 Provider 만 템플릿 없이 글이 된다(S2AFIX D8)
        unknown = dataclasses.replace(M.MockProvider(), reader_notes=(), attribution_template=None)                                                   # 정책을 모르면 막는다
        self.assertEqual(self.code(H.run("R01_time_series", params=H.R01_PARAMS, provider=unknown)), "ATTRIBUTION_REQUIRED")
        plain = H.run("R01_time_series", params=H.R01_PARAMS, provider=none)
        self.assertNotIn("제공처 안내", plain.body_markdown)
        self.assertNotIn("이용 조건", plain.body_markdown)
        self.assertEqual(A.post_problems(plain), [])
        bare = types.SimpleNamespace(**{name: getattr(M.MockProvider(), name) for name in F.PROVIDER_FIELDS})        # reader_notes·exceptions·name 이 없는 Provider 도 글이 된다
        self.assertIsInstance(H.run("R01_time_series", params=H.R01_PARAMS, provider=bare), A.AssembledPost)
        self.assertEqual(A.SourceInfo(dataclasses.replace(M.MockProvider(), reader_notes="한 문장"), "이름", M.SOURCE_URL).reader_notes, ("한 문장",))   # 문자열 하나는 한 문장으로 본다(글자로 쪼개지 않는다)

    def test_audit_memo_shaped_exceptions_never_reach_the_post(self):
        """SRC 의 `exceptions` 는 독자용 문구가 아니라 약관 감사 메모다(독립 검증 V-08) — 어떤 모양이든 글에 새지 않고 글이 막히지도 않는다."""
        memos = ("확인 못 함 — 2026-10-26 자료 기준, 오늘 재확인 못 함", "제3자 자료 제외", "{{ x }}", "물결~표", "줄\n바꿈", "", "한 곳을 뺍니다", 7, "무 조건 믿으세요")
        base = H.run("R01_time_series", params=H.R01_PARAMS)
        for memo in memos:
            with self.subTest(memo=memo):
                post = H.run("R01_time_series", params=H.R01_PARAMS, provider=dataclasses.replace(M.MockProvider(), exceptions=(memo,)))
                self.assertEqual(post, base)
                self.assertNotIn("재확인", post.body_markdown)
        self.assertEqual(self.code(H.run("R01_time_series", params=H.R01_PARAMS, provider=dataclasses.replace(M.MockProvider(), reader_notes=("무 조건 믿으세요",)))), "READER_NOTE_UNSAFE")

    def test_insufficient_is_falsy_and_comparable(self):
        a, b = R.Insufficient("X", "사유"), R.Insufficient("X", "사유")
        self.assertFalse(a)
        self.assertEqual(a, b)
        self.assertEqual(len({a, b}), 1)
        self.assertNotEqual(a, R.Insufficient("Y", "사유"))
        self.assertIn("Insufficient", repr(a))


class DefectiveTemplatesTest(unittest.TestCase):
    """Recipe 의 plan 이 일부러 망가뜨린 틀을 내놓아도 조립기가 글을 내보내지 않는다."""

    def code(self, recipe):
        result = H.run(recipe, params=H.R01_PARAMS)
        self.assertIsInstance(result, R.Insufficient, "결함이 있는 틀로 글이 나왔다")
        return result

    def test_raw_numbers_in_a_template_are_refused(self):
        for name, mutator in (("첫 문단", lambda d: d.leads.insert(0, "값은 3.5 입니다 그리고 충분히 길게 쓴 문장입니다 그리고 충분히 길게 쓴 문장입니다.")),
                              ("제목", lambda d: d.titles.insert(0, "제목 2026")), ("절", lambda d: d.sections[0][1].append("추가 3.5")),
                              ("주의 줄", lambda d: d.caveats.append("- 숫자 3")), ("우리말 수 표현", lambda d: d.caveats.append("- 두 배로 늘었습니다.")),
                              ("전각 숫자", lambda d: d.caveats.append("- 값 １２")), ("원 숫자", lambda d: d.caveats.append("- ①번"))):
            with self.subTest(where=name):
                self.assertEqual(self.code(wrapped(mutator)).code, "TEMPLATE_UNTRACED")

    def test_other_broken_references_are_render_errors(self):
        for name, mutator in (("출처 기록을 값으로", lambda d: d.caveats.append("- ⟦F:record⟧")), ("모르는 칸", lambda d: d.sections[0][1].append("⟦F:nothing⟧")),
                              ("닫히지 않은 표시", lambda d: d.sections[0][1].append("⟦F:main")), ("모르는 종류", lambda d: d.sections[0][1].append("⟦X:main⟧")),
                              ("Liquid", lambda d: d.sections[0][1].append("{{ page.title }}"))):
            with self.subTest(where=name):
                self.assertEqual(self.code(wrapped(mutator)).code, "RENDER_ERROR")

    def test_a_first_choice_that_needs_a_missing_slot_falls_back(self):
        post = H.run(wrapped(lambda d: (d.titles.insert(0, "⟦F:nothing⟧ 제목"), d.leads.insert(0, "⟦F:nothing⟧ 첫 문단입니다."))), params=H.R01_PARAMS)
        self.assertEqual(post, H.run("R01_time_series", params=H.R01_PARAMS))

    def test_bad_wording_is_caught_by_the_final_check(self):
        cases = (("금지 표현(단정)", add_caveat("- 효과: 이 방법은 반드시 효과가 있습니다."), "FORBIDDEN"),
                 ("금지 표현(원인 단정)", add_caveat("- 이유: 경기가 나빠졌기 때문에 올랐습니다."), "FORBIDDEN"),
                 ("금지 표현(과장)", add_caveat("- 표현: 역대급으로 올랐습니다."), "FORBIDDEN"),
                 ("금지 표현(투자)", add_caveat("- 조언: 지금 매수하세요."), "FORBIDDEN"),
                 ("금지 표현(건강)", add_caveat("- 건강: 완치를 약속합니다."), "FORBIDDEN"),
                 ("금지 표현(즉시 효과)", add_caveat("- 효과: 즉시 효과가 납니다."), "FORBIDDEN"),
                 ("금지 표현(번역투 — 차단 낱말 목록에는 없는 표현)", add_caveat("- 표현: 이 값은 자료에 의해 정해졌습니다."), "FORBIDDEN"),
                 ("금지 표현(예측 — 차단 낱말 목록에는 없는 표현)", add_caveat("- 앞날: 앞으로 오를 것입니다."), "FORBIDDEN"),
                 ("물결표", add_caveat("- 범위: 가나~다라"), "MARKUP"), ("영문", add_caveat("- Note: this is English text"), "LANGUAGE"),
                 ("한자", add_caveat("- 한자: 漢字"), "LANGUAGE"), ("조사(표시 뒤)", add_caveat("- 값: ⟦F:main⟧가 높습니다."), "PARTICLE"),
                 ("조사(괄호 뒤)", add_caveat("- 값: (⟦F:main⟧)을 봅니다."), "PARTICLE"), ("조사 둘 다", add_caveat("- 값: 이것은(는) 높습니다."), "PARTICLE"),
                 ("반복", lambda d: d.caveats.append(d.caveats[0]), "REPEAT"),
                 ("절 빠짐", lambda d: d.sections.pop(1), "STRUCTURE"),
                 ("표 없음", lambda d: d.sections.__setitem__(1, (R.H_NUMBERS, [b for b in d.sections[1][1] if not b.startswith("| ")])), "STRUCTURE"))
        for name, mutator, code in cases:
            with self.subTest(case=name):
                result = self.code(wrapped(mutator))
                self.assertEqual(result.code, "QUALITY_CHECK_FAILED")
                self.assertTrue(result.detail.startswith(code), result.detail)

    def test_a_post_without_enough_own_calculation_is_refused(self):
        def plan(ctx):
            draft = R.R01_TIME_SERIES.plan(ctx)
            main = draft.main
            count = C.f12_count([main], "개월")
            words = "가 나 다 라 마 바 사 아 자 차 카 타 파 하 거 너 더 러 머 버 서 어 저 처 커 터 퍼 허".split()
            long_text = " ".join(f"{word} 항목은 공개된 자료를 읽고 정리하는 방법을 설명하는 문장입니다." for word in words * 3)
            lead = "⟦D:main⟧ 기준 ⟦R:main⟧의 ⟦L:main⟧ 값은 ⟦F:main⟧입니다(이 글이 읽은 자료 ⟦V:n⟧⟦U:n⟧의 마지막 값이며 따로 계산한 값은 없습니다)."
            return R.Draft(main, {"main": main, "n": count}, ["⟦L:main⟧ 제목"], [lead],
                           [(R.H_GLANCE, [long_text]), (R.H_NUMBERS, [R.md_table(["가", "나"], [["다", "라"]])]), (R.H_READING, ["해석입니다."])],
                           [], ["태그"], main.topic, main.as_of, {count.fact_id: count}, [], ("x",))
        result = H.run(dataclasses.replace(R.R01_TIME_SERIES, plan=plan), params=H.R01_PARAMS)
        self.assertIsInstance(result, R.Insufficient)
        self.assertEqual((result.code, A.MIN_DISTINCT_FORMULAS), ("NO_ANALYSIS", 2))


class QualityCheckDirectTest(unittest.TestCase):
    """`post_problems` 가 다 파는 결함을 하나씩(좋은 글을 일부러 고쳐서)."""

    @classmethod
    def setUpClass(cls):
        cls.post = H.run("R01_time_series", params=H.R01_PARAMS)

    def problems(self, **over):
        post = dataclasses.replace(self.post, **over)
        return [p.split(" ", 1)[0] for p in A.post_problems(post)]

    def test_the_good_post_has_no_problems(self):
        size = A.readable_chars(A.story_of(self.post.body_markdown))
        self.assertEqual(A.post_problems(self.post), [])
        self.assertEqual(A.post_problems(self.post, min_story_chars=size), [])
        self.assertEqual([p.split(" ", 1)[0] for p in A.post_problems(self.post, min_story_chars=size + 1)], ["TOO_SHORT"])

    def test_each_defect_has_its_code(self):
        body, post = self.post.body_markdown, self.post
        skeleton = (f"{post.description}\n\n## 한눈에\n\n- 값\n\n## 숫자로 보기\n\n| 가 | 나 |\n| --- | --- |\n| 다 | 라 |\n\n## 비교·해석\n\n해석\n\n"
                    "## 이 숫자를 읽을 때 주의\n\n- 주의\n\n## 출처\n\n- 출처\n")
        cases = (
            ("TITLE", dict(title="가" * 61)), ("TITLE", dict(title="")), ("TITLE", dict(title="두 줄\n제목")),
            ("DESCRIPTION", dict(description="짧은 설명입니다.")), ("DESCRIPTION", dict(description=post.description + " 한 문장이 더 있습니다.")),
            ("DESCRIPTION", dict(body_markdown=body.replace(post.description, "다른 첫 문단입니다.", 1))),
            ("TOO_SHORT", dict(body_markdown=skeleton)),
            ("UNTRACED", dict(body_markdown=body.replace("## 한눈에\n", "## 한눈에\n\n- 몰래 넣은 값: 99.9%\n", 1))),
            ("UNTRACED", dict(template_markdown=post.template_markdown + " 몰래 3")),
            ("FORBIDDEN", dict(body_markdown=body.replace("직접 계산했습니다.", "반드시 맞습니다.", 1))), ("MARKUP", dict(body_markdown=body.replace("## 한눈에", "## 한눈에 ~", 1))),
            ("FORBIDDEN", dict(body_markdown=body.replace("## 한눈에", "## 한눈에 코스피", 1))), ("FORBIDDEN", dict(body_markdown=body.replace("## 한눈에", "## 한눈에 당 뇨", 1))),
            ("FORBIDDEN", dict(title=post.title.replace("실업률", "고혈압", 1))),
            ("MARKUP", dict(body_markdown=body.replace("## 한눈에", "## 한눈에 {{ x }}", 1))), ("MARKUP", dict(title="제목 ⟦F:x⟧")),
            ("LANGUAGE", dict(body_markdown=body.replace("## 한눈에", "## Overview", 1))), ("LANGUAGE", dict(body_markdown=body.replace("## 한눈에", "## 漢字", 1))),
            ("STRUCTURE", dict(body_markdown=body.replace("## 비교·해석", "## 해석", 1))),
            ("STRUCTURE", dict(body_markdown=body.replace("| --- ", "| === ", 1))),
            ("REPEAT", dict(body_markdown=body.replace("## 출처", "- 지표와 단위: 실업률(단위 %). 다른 기관의 같은 이름 지표와는 정의가 다를 수 있어 직접 견주지 않았습니다.\n\n## 출처", 1))),
            ("PARTICLE", dict(template_markdown=post.template_markdown + " ⟦F:" + post.facts_used[0].fact_id + "⟧가")),
            ("PARTICLE", dict(body_markdown=body.replace("## 한눈에", "## 한눈에 이것은(는)", 1))),
        )
        for code, over in cases:
            with self.subTest(code=code, over=list(over)):
                self.assertIn(code, self.problems(**over))

    def test_description_and_title_length_bounds_are_checked_on_their_own(self):
        """설명은 60자 이상 155자 이하 — 첫 문단도 같이 바꿔 '첫 문단과 같음' 검사에 가려지지 않게 하고 경계(59·60·155·156자)를 하나씩 본다."""
        body, post = self.post.body_markdown, self.post
        message = "DESCRIPTION 설명이 한 문장(60자 이상 155자 이하)이 아님"
        for size, ok in ((59, False), (60, True), (155, True), (156, False)):
            description = "가" * (size - 1) + "."
            changed = dataclasses.replace(post, description=description, body_markdown=body.replace(post.description, description, 1))
            with self.subTest(size=size):
                self.assertEqual(message in A.post_problems(changed), not ok)
        for size, ok in ((R.MAX_TITLE_CHARS, True), (R.MAX_TITLE_CHARS + 1, False)):
            with self.subTest(title=size):
                self.assertEqual("TITLE" in self.problems(title="가" * size), not ok)

    def test_the_forbidden_phrases_are_found_one_by_one(self):
        for category, phrases in R.FORBIDDEN_PHRASES.items():
            for phrase in phrases:
                with self.subTest(category=category, phrase=phrase):
                    self.assertIn(phrase, {found for _category, found in A.forbidden_found(f"앞 {phrase} 뒤")})

    def test_only_the_legal_attribution_line_is_exempt_from_the_phrase_scan(self):
        self.assertEqual(A.forbidden_found(f"{A.ATTRIBUTION_PREFIX}제공처는 정확성을 보장하지 않습니다."), [])
        self.assertTrue(A.forbidden_found(f"{R.READER_NOTE_PREFIX}보장하지 않는 자료입니다."))          # 독자용 안내 문장은 우리 글과 같이 검사한다
        self.assertTrue(A.forbidden_found("- 지표: 보장합니다"))
        self.assertTrue(A.forbidden_found("- 지표: 무 조 건 맞습니다"))                                  # 띄어 써도 같다
        self.assertTrue(A.forbidden_found("- 지표: 무·조·건 맞습니다"))
        self.assertTrue(A.forbidden_found("- 지표: 무-조-건 맞습니다"))
        self.assertTrue(A.blocked_found("- 라벨: 당뇨병 환자"))

    def test_number_and_length_helpers(self):
        self.assertEqual(A.number_tokens("값 1,234.5와 3.2% 2026년 [링크](https://a.invalid/x1?y=2) https://b.invalid/3"), ["1234.5", "3.2", "2026"])
        self.assertEqual(A.number_tokens("제3자 자료"), [])
        self.assertEqual(A.readable_chars("가나다\n\n| --- | ---: |\n| 라 | 마 |"), 5)
        self.assertEqual(A.readable_chars("[가나](http://x.invalid/12345) ![그림](a.png) `코드` **굵게**"), 2 + 2 + 2)
        self.assertEqual(A.story_of("앞\n\n## 출처\n\n뒤"), "앞\n\n")
        self.assertEqual(A.story_of("출처가 없는 글"), "출처가 없는 글")
        self.assertEqual(A.latin_words("가 abc 나 d [x](https://e.invalid) kWh"), ["abc", "kWh"])


class TemplateReviewTest(unittest.TestCase):
    """틀(데이터 파일 격인 Recipe 모듈의 글)에 외부 문장이 없고 규칙을 지키는지 — 틀·라벨 검토 + 금지어."""

    @classmethod
    def setUpClass(cls):
        _provider, _record, facts = H.mock_bundle()
        cls.drafts = []
        for region in ("R01", "R02", "R03", "R04", "R05", "R06"):
            for recipe in (R.R01_TIME_SERIES, R.R03_RECORD_POSITION):
                cls.drafts.append(build_draft(recipe, facts, {"key": H.UNEMP, "region": region}))
        cls.drafts.append(build_draft(R.R02_REGION_COMPARE, facts, {"key": H.UNEMP}))
        series = [f for f in H.series_of("R01") if f.as_of != "2026-02"]
        cls.drafts.append(build_draft(R.R01_TIME_SERIES, series, {"key": H.UNEMP, "region": "R01"}))
        cls.constants = (list(R.CAUTION_COMMON) + [R.NOTICE_TEMPLATE, R.INTRO_TEMPLATE, R.READER_NOTE_PREFIX.strip(), R.MISSING_CELL, R.NA_CELL, *R.SECTION_ORDER]
                         + [R.intro_template("하루 최대값·개수·평균"), *R.caution_common("하루 최대값·개수·평균")])          # 지역 없는 틀이 쓰는 계산 목록 안내(S2AFIX2 N5)도 같은 글 규칙을 지킨다

    def templates(self):
        out = [(None, text) for text in self.constants]
        for draft in self.drafts:
            self.assertIsInstance(draft, R.Draft)
            texts = [*draft.titles, *draft.leads, *draft.caveats, *(b for _h, blocks in draft.sections for b in blocks), *(h for h, _b in draft.sections)]
            out += [(draft, text) for text in texts]
        return out

    def test_there_is_a_lot_to_review(self):
        self.assertGreater(len(self.templates()), 150)

    def test_templates_obey_every_text_rule(self):
        for draft, text in self.templates():
            plain = F.REF_RE.sub("", text).replace(R.SOURCE_LINK_TOKEN, "")
            with self.subTest(text=text[:40]):
                self.assertEqual(F.untraced_numbers(text), [])
                self.assertEqual(A.forbidden_found(text), [])
                self.assertEqual(A.particle_problems(text), [])
                self.assertIsNone(re.search(R.VARYING_PARTICLE_PATTERNS[2], text))
                for char in R.BLOCKED_TEXT_CHARS:
                    self.assertNotIn(char, plain)
                self.assertNotIn("http", text)
                self.assertEqual(re.findall(r"[A-Za-z]{2,}", plain), [], "틀에 영문 낱말이 있다 — 영문자는 라벨·단위 같은 데이터에서만 온다")
                self.assertIsNone(re.search(r"[぀-ヿ㐀-鿿]", text))
                self.assertEqual(text, text.strip())
                self.assertNotIn("  ", text.replace("| ", "|"))
                for _kind, name in F.references(text):
                    self.assertRegex(name, r"\A[a-z][a-z0-9_]*\Z")
                    if draft is not None:
                        self.assertTrue(name in draft.slots or name == "record", f"{name} 칸이 없다")

    def test_templates_do_not_copy_provider_sentences(self):
        provider = M.MockProvider()
        for _draft, text in self.templates():
            for sentence in (provider.attribution_template, *provider.exceptions, M.SOURCE_NAME):
                self.assertNotIn(sentence, text)
        for key, label, _en, _unit in M.SERIES.values():
            self.assertLessEqual(len(label), 12)

    def test_every_marker_kind_used_is_a_known_one(self):
        used = {kind for _draft, text in self.templates() for kind, _name in F.references(text)}
        self.assertTrue(used <= set(F.MARKER_KINDS))
        self.assertTrue({"F", "S", "A", "V", "U", "D", "L", "R", "T"} <= used)

    def test_the_forbidden_list_covers_the_agreed_examples(self):
        flat = {phrase for phrases in R.FORBIDDEN_PHRASES.values() for phrase in phrases}
        for phrase in ("치료", "완치", "보장", "반드시", "확실히", "무조건", "즉시 효과", "역대급", "때문에", "원인은", "매수", "매도"):
            self.assertIn(phrase, flat)


if __name__ == "__main__":
    unittest.main()
