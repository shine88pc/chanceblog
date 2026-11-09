"""구조화 Fact 경로 1단계 — 문서 시험: `docs/FACT_PATH.md` 가 코드의 실제 이름·표와 어긋나지 않고, 문서 규칙(물결표·http 링크·Liquid·로컬 경로 없음)을 지키며,
`docs/ARCHITECTURE.md` 의 §4-10 과 `docs/DEFECT_REGISTER.md` 의 D-100 이 있다. 네트워크 없이 파일만 읽는다."""
import re
import unittest

import _bootstrap
import fact_helpers as H

from pipeline import calc as C
from pipeline import fact_topics as T
from pipeline import facts as F
from pipeline import recipes as R

ROOT = _bootstrap.ROOT
DOC = (ROOT / "docs" / "FACT_PATH.md").read_text(encoding="utf-8")
ARCH = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
REGISTER = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")


def table_rows(text):
    rows = []
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                rows.append(cells)
    return rows


class DocRulesTest(unittest.TestCase):
    def test_the_document_follows_the_doc_rules(self):
        self.assertGreater(len(DOC), 8000)
        self.assertNotRegex(DOC, "[~～〜]")                                     # 범위는 en 대시
        self.assertNotRegex(DOC, r"(?i)https?://|www\.|\bftp://")              # 문서에 링크 금지 — 주소는 호스트 이름만
        for liquid in ("{{", "{%", "%}", "}}"):
            self.assertNotIn(liquid, DOC)
        self.assertNotRegex(DOC, r"[A-Za-z]:[\\/]|/Users/|/home/|\\\\")          # 로컬 경로 금지
        self.assertNotRegex(DOC, r"(?i)ca-pub|adsense|pub-\d{8,}")
        for relative in re.findall(r"\]\((\./[^)]+)\)", DOC):
            self.assertTrue((ROOT / "docs" / relative).exists(), relative)

    def test_the_changed_docs_follow_the_same_rules(self):
        new_arch = ARCH[ARCH.index("## 4-10."):ARCH.index("## 5. 상태·멱등성·동시성")]
        row = next(line for line in REGISTER.splitlines() if line.startswith("| **D-100** |"))
        for text in (new_arch, row):
            self.assertNotRegex(text, "[~～〜]")
            self.assertNotRegex(text, r"(?i)https?://|www\.")
            for liquid in ("{{", "{%"):
                self.assertNotIn(liquid, text)

    def test_the_documents_never_claim_the_path_is_connected_or_finished(self):
        self.assertIn("연결하지 않았다", DOC)
        self.assertIn("연결은 2단계", DOC)
        self.assertNotRegex(DOC, r"생성기에 연결(?:했|됐|되었)")
        self.assertIn("켜는 설정은 아직 없다", DOC)


class DocMatchesCodeTest(unittest.TestCase):
    def test_every_formula_has_a_row_with_its_function_name(self):
        rows = {cells[0]: cells for cells in table_rows(DOC[DOC.index("## 5. 계산식"):DOC.index("**비교 가능성")]) if cells and cells[0].startswith("F")}
        formulas = set()
        for key in rows:
            formulas |= set(re.findall(r"F\d{2}_[a-z_]+", key))
        self.assertEqual(formulas, set(C.FORMULAS))
        for formula_id, function in C.FORMULAS.items():
            self.assertIn(f"`{function.__name__}", DOC, formula_id)

    def test_every_recipe_kind_marker_and_reason_is_in_the_document(self):
        for recipe_id, recipe in R.RECIPES.items():
            self.assertIn(f"`{recipe_id}`", DOC)
            self.assertIn(recipe.name_ko, DOC)
            for formula_id in recipe.formulas:
                self.assertIn(formula_id.split("_", 1)[0], DOC)
        for kind in F.FACT_KINDS:
            self.assertIn(f"`{kind}`", DOC)
        for marker in F.MARKER_KINDS:
            self.assertIn(f"⟦{marker}:", DOC)
        for category in R.FORBIDDEN_PHRASES:
            self.assertIn(category, DOC)
        codes = set()
        for rel in ("pipeline/fact_assembler.py", "pipeline/recipes.py"):
            codes |= set(re.findall(r'Insufficient\("([A-Z_]+)"', (ROOT / rel).read_text(encoding="utf-8")))
        self.assertGreater(len(codes), 20)
        for code in codes:
            self.assertIn(f"`{code}`", DOC)
        table = DOC[DOC.index("## 5. 계산식"):DOC.index("**비교 가능성")]
        documented = set(re.findall(r"\b[A-Z]{2,}(?:_[A-Z]+)+\b", table)) - set(C.FORMULAS)
        documented = {code for code in documented if not re.fullmatch(r"F\d{2}_[A-Z_]+", code)}
        self.assertGreaterEqual(len(documented), 12)
        self.assertTrue(documented <= set(C.REASON_TEXT), documented - set(C.REASON_TEXT))      # 문서가 적은 사유 코드는 모두 코드에 있다

    def test_the_minimum_inputs_and_limits_in_the_document_match_the_recipes(self):
        table = {cells[0]: cells for cells in table_rows(DOC[DOC.index("| Recipe |"):DOC.index("글의 뼈대(모든 Recipe 공통)")]) if cells[0].startswith("`R0")}
        self.assertEqual(set(table), {f"`{rid}` {recipe.name_ko}" for rid, recipe in R.RECIPES.items()} | set())
        for rid, recipe in R.RECIPES.items():
            cells = table[f"`{rid}` {recipe.name_ko}"]
            self.assertIn(str(recipe.min_points), cells[-1], rid)
            self.assertTrue(all(fid.split("_", 1)[0] in cells[2] for fid in recipe.formulas), rid)
        self.assertIn("국문 1,000자", DOC)
        self.assertEqual(R.MIN_STORY_CHARS, 1000)
        self.assertEqual({recipe.max_age_days for recipe in R.RECIPES.values()}, {450})
        self.assertIn("450일", DOC)
        self.assertIn(f"{R.DESCRIPTION_MIN}–{R.DESCRIPTION_MAX}자", DOC)
        self.assertEqual(R.MAX_TITLE_CHARS, 60)

    def test_the_interface_with_src_uses_the_agreed_names(self):
        section = DOC[DOC.index("## 9. SRC"):DOC.index("## 10. 시험")]
        for name in ("Registry.get", "active_providers", "is_url_allowed", "ProviderLike", "RegistryLike", "Opener", "provider_id", "strict_tier", "effective_status",
                     "attribution_template", "snapshot", "policy", "retention_days", "exceptions", "typing.Protocol", "import 하지 않는다"):
            self.assertIn(name, section)
        self.assertEqual(set(F.PROVIDER_FIELDS), {"provider_id", "strict_tier", "effective_status", "access", "attribution_template", "snapshot", "policy", "retention_days"})
        self.assertEqual(F.ACTIVE_STATUS, "자동화 가능")
        self.assertEqual(F.MAX_ACTIVE_TIER, 2)

    def test_the_required_sections_and_the_second_stage_plan_are_there(self):
        for heading in ("## 7. 어댑터 작성 체크리스트", "## 11. 이미지 문제와 2단계 연결 계획", "### 이미지 문제", "### 2단계 연결 계획", "## 13. 한계와 남은 일"):
            self.assertIn(heading, DOC)
        for needle in ("chance.content_source", "evidence_text", "source_ref", "SHADOW_RUN", "dedupe_key", "이력", "`topic`", "자체 제목", "권고", "T3",
                       "7칸", "robots", "호출 한도", "구조화 경로", "낱말 표", "시험 고정 데이터", "strict_tier", "attribution", "`Insufficient`", "솔직한 평가"):
            self.assertIn(needle, DOC)
        checklist = DOC[DOC.index("## 7. 어댑터 작성 체크리스트"):DOC.index("## 8. Recipe")]
        self.assertGreaterEqual(len(re.findall(r"(?m)^\d+\. \*\*", checklist)), 9)

    def test_the_image_investigation_names_the_real_places(self):
        section = DOC[DOC.index("### 이미지 문제"):DOC.index("### 2단계 연결 계획")]
        for needle in ("front_matter_problems", "test_posts_front_matter", "_layouts/post.html", "index.html", "getDefaultThumbnail", "posts.json", "pipeline/drafts.py",
                       "_POST_PATH_RE", "credit_line_for", "pick_images", "권고"):
            self.assertIn(needle, section)
        generator = (ROOT / "generator.py").read_text(encoding="utf-8")
        for symbol in ("def front_matter_problems", "def credit_line_for", "def pick_images", "len(images) <", '_FM_REQUIRED = ("layout", "title", "category", "lang", "image")'):
            self.assertIn(symbol, generator)
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("getDefaultThumbnail(title)", index)
        self.assertIn("images.unsplash.com", index)
        self.assertNotIn("post.image", (ROOT / "_layouts" / "post.html").read_text(encoding="utf-8"))
        self.assertIn("_POST_PATH_RE", (ROOT / "pipeline" / "drafts.py").read_text(encoding="utf-8"))
        self.assertIn('startswith("https://")', (ROOT / "tests" / "test_posts_front_matter.py").read_text(encoding="utf-8"))

    def test_decisions_are_numbered_without_gaps_and_do_not_reuse_the_register_number(self):
        decisions = re.findall(r"(?m)^\| (D-\d+) \|", DOC)
        self.assertEqual(decisions, [f"D-{n}" for n in range(101, 101 + len(decisions))])
        self.assertGreaterEqual(len(decisions), 20)
        self.assertNotIn("D-100", decisions)


class ReviewFixDocsTest(unittest.TestCase):
    """독립 검증 지적(V-01–V-14)을 반영한 문서: 결정 D-129–D-146 · 새 모듈 · 2단계 계획의 QG5 · 글 품질 측정표(코드가 잰 값과 같다)."""

    def test_the_review_decisions_are_recorded(self):
        decisions = set(re.findall(r"(?m)^\| (D-\d+) \|", DOC))
        self.assertTrue({f"D-{n}" for n in range(129, 147)} <= decisions)
        for needle in ("V-01", "V-02", "V-03", "V-04", "V-05", "V-06", "V-07", "V-08", "V-09", "V-10", "V-11", "V-12", "V-13", "V-14"):
            self.assertIn(needle, DOC)
        for needle in ("pipeline/fact_topics.py", "display_context", "verdict", "reader_notes", "enabled", "endpoint_suffix", "EGRESS_DENIED", "QG5-COMPANY", "NO_REGION_SERIES",
                       "UNKNOWN_TOPIC", "FORMULA_LABELS", "ratio_ok", "VALUE_OUT_OF_RANGE", "PRECISION_LIMIT", "INTERNAL_ERROR", "초안 보조", "보류가 맞다"):
            self.assertIn(needle, DOC)
        self.assertIn("pipeline/fact_topics.py", ARCH[ARCH.index("## 4-10."):ARCH.index("## 5. 상태·멱등성·동시성")].replace("`fact_topics.py`", "pipeline/fact_topics.py"))

    def test_every_domain_is_named_in_the_document(self):
        for domain_id, domain in T.DOMAINS.items():
            self.assertIn(f"`{domain_id}`", DOC)
            self.assertIn(domain.name_ko, DOC)
        for topic in sorted(F.BLOCKED_TOPICS):
            self.assertNotIn(f"`{topic}`(", DOC)                                      # 막힌 주제는 허용 범주로 소개되지 않는다

    def test_every_unit_in_the_table_that_blocks_ratios_is_named(self):
        for unit, spec in F.UNIT_TABLE.items():
            if not spec.ratio_ok:
                self.assertIn(unit, DOC.split("**단위 표와 변화율**")[1].split("## 6.")[0], unit)

    def test_the_quality_table_matches_what_the_code_measures(self):
        section = DOC[DOC.index("## 13. 한계와 남은 일"):]
        rows = {cells[0]: cells for cells in table_rows(section) if cells[0].startswith("`R0")}
        self.assertEqual(set(rows), {f"`{rid}`" for rid in H.GOLDEN})
        for rid, params in H.GOLDEN.items():
            metrics = H.quality_metrics(H.run(rid, params=params))
            expected = [f"`{rid}`", f"{metrics['story']:,}", f"{metrics['caution']:,}", f"{metrics['pure']:,}", f"{metrics['fixed']:,}", f"{metrics['fixed_percent']}%"]
            self.assertEqual(rows[f"`{rid}`"], expected, rid)
        for needle in ("주의 절을 빼면 분량 하한(1,000자)에 못 미치고", "초안 보조", "보류가 맞다"):
            self.assertIn(needle, section)


class ChangedDocsTest(unittest.TestCase):
    def test_architecture_has_one_section_and_one_module_row(self):
        self.assertEqual(len(re.findall(r"(?m)^## 4-10\. ", ARCH)), 1)
        titles = re.findall(r"(?m)^## (\d+-\d+)\. ", ARCH)
        self.assertEqual(len(titles), len(set(titles)))
        section = ARCH[ARCH.index("## 4-10."):ARCH.index("## 5. 상태·멱등성·동시성")]
        self.assertIn("(./FACT_PATH.md)", section)
        self.assertIn("`pipeline/facts.py`", section)
        self.assertIn("연결하지 않았다", section)
        self.assertEqual(len([cells for cells in table_rows(section) if cells[0].startswith("`pipeline/")]), 1)
        self.assertTrue(ARCH.index("## 4-8.") < ARCH.index("## 4-10.") < ARCH.index("## 5. 상태·멱등성·동시성"))

    def test_the_defect_register_has_exactly_one_new_row_d100(self):
        ids = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", REGISTER)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids.count("D-100"), 1)
        row = next(line for line in REGISTER.splitlines() if line.startswith("| **D-100** |"))
        self.assertEqual(row.count("|"), 7)                                              # 표의 여섯 칸
        for needle in ("FACT_PATH.md", "완화", "2단계", "T3", "content_source"):
            self.assertIn(needle, row)
        before = ids[ids.index("D-100") - 1]
        self.assertTrue(88 <= int(before.split("-")[1]) <= 99, before)                   # D-89–D-99 는 다른 가지가 쓰는 번호 — 어느 가지가 먼저 병합돼도 통과


if __name__ == "__main__":
    unittest.main()
