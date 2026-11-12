"""docs/SOURCE_POLICY.md·ARCHITECTURE·DEFECT_REGISTER 가 코드와 어긋나지 않게 잡는 시험(표류 방지).

문서의 규칙표·운영 호스트·호출 지점 수·Provider 수·결과 코드·인터페이스 이름이 코드와 같고, 문서 규칙(물결표·http 주소·Liquid 구문 없음, 상대 링크가 열림)을 지킨다.
네트워크 없이 파일만 읽는다."""
import json
import re
import unittest

import _bootstrap  # noqa: F401
from pipeline import egress, source_policy, source_registry as sr
from test_egress import scan_tree, ungated_unlisted

ROOT = _bootstrap.ROOT
DOC = (ROOT / "docs" / "SOURCE_POLICY.md").read_text(encoding="utf-8")
ARCH = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
DEFECTS = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
ACTIONS = (ROOT / "docs" / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")


class DocRulesTest(unittest.TestCase):
    def test_house_rules_for_documents(self):
        for name, text in (("SOURCE_POLICY.md", DOC),):
            self.assertNotIn("~", text, f"{name}: 물결표(~) 금지 — 범위는 –")
            self.assertIsNone(re.search(r"https?://", text), f"{name}: 주소(http 링크) 금지 — 호스트 이름만")
            self.assertNotIn("{%", text, name)
            self.assertNotIn("{{", text, name)

    def test_relative_links_resolve(self):
        for target in re.findall(r"\]\((\./[^)#\s]+)", DOC + ARCH):
            if "SOURCE_POLICY" in target or target.startswith("./SECURITY") or target.startswith("./CHARTER") or target.startswith("./ARCHITECTURE"):
                self.assertTrue((ROOT / "docs" / target[2:]).exists(), target)

    def test_the_files_named_in_the_component_table_exist(self):
        table = DOC.split("## 3. 구성 요소", 1)[1].split("## 4.", 1)[0]
        for path in re.findall(r"`((?:pipeline|tests)/[A-Za-z0-9_./]+)`", table):
            self.assertTrue((ROOT / path).exists(), path)


class RulesAndNumbersTest(unittest.TestCase):
    def test_every_rule_code_in_the_code_is_in_the_doc_table_and_vice_versa(self):
        code_codes = set(re.findall(r'_tag\("([SA]\d+)"', (ROOT / "pipeline" / "source_registry.py").read_text(encoding="utf-8")))
        doc_codes = set(re.findall(r"^\| ([SA]\d+) \|", DOC, re.M))
        self.assertEqual(code_codes, doc_codes)
        self.assertEqual(code_codes, {f"A{n}" for n in range(12)} | {f"S{n}" for n in range(1, 12)})

    def test_every_provider_field_used_in_the_file_is_a_row_of_the_shape_table(self):
        """허용 목록 파일에 실제로 쓰인 Provider 칸 이름과 선택 칸(`ai_use`·`own_data_only`)이 4절 표의 첫 칸에 있다 — 칸을 더하고 표에 안 적으면(또는 행을 지우면) 빨개진다."""
        table = DOC.split("## 4. 허용 목록의 모양", 1)[1].split("## 5.", 1)[0]
        first_cells = " ".join(re.findall(r"^\| ([^|]+) \|", table, re.M))
        data = json.loads((ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8"))
        names = {key for provider in data["providers"] for key in provider} | {"ai_use", "own_data_only"}
        for name in sorted(names):
            self.assertIsNotNone(re.search(rf"`{re.escape(name)}(?:\[\])?`", first_cells), f"4절 표에 `{name}` 행이 없습니다")

    def test_the_ai_policy_cells_and_fixed_defaults_are_in_the_doc(self):
        section = DOC.split("## 10. AI 처리기 정책", 1)[1].split("## 11.", 1)[0]
        for name in sr.AI_FIELDS:
            self.assertIn(f"`{name}`", section, name)
        for name, fixed in sr.AI_FIXED.items():
            self.assertIn(f"`{fixed}`" if isinstance(fixed, str) else f"`{str(fixed).lower()}`", section, name)

    def test_operations_rules_and_site_counts_match_the_code(self):
        section = DOC.split("## 7. 외부 호출 관문", 1)[1].split("## 8.", 1)[0]
        for rule in egress.OPS_RULES:
            self.assertIn(f"`{rule.host}`", section, rule.host)
            for purpose in rule.purposes:
                self.assertIn(f"`{purpose}`", section, purpose)
        self.assertIn("`www.googleapis.com`", section)                              # 뺀 이유(D-173)를 적었다
        self.assertNotIn("www.googleapis.com", egress.OPS_HOSTS)
        sites, calls = scan_tree(ROOT)
        unique = {(s.file, s.function) for s in sites}
        self.assertEqual(ungated_unlisted(sites, calls, egress.EGRESS_EXCEPTIONS), [])
        self.assertIn(f"지점 {len(unique)}곳(함수 단위, {len({s.file for s in sites})}개 파일)", section)
        self.assertIn(f"등록 항목 {len(egress.EGRESS_EXCEPTIONS)}개", section)
        self.assertEqual(len([s for s in sites if s.gated]), 0)
        self.assertIn("관문을 거쳤다고 인정되는 곳은 0", section)

    def test_the_doc_words_the_call_list_test_as_not_a_guarantee_and_lists_the_blind_spots(self):
        for text in (DOC.split("## 1. 한눈에", 1)[1].split("## 2.", 1)[0], DOC.split("## 7. 외부 호출 관문", 1)[1].split("## 8.", 1)[0]):
            self.assertIn("보증", text)
            self.assertIn("사람 검토가 마지막 방어선", text)
        section = DOC.split("## 7. 외부 호출 관문", 1)[1].split("## 8.", 1)[0]
        for needle in ("사각지대", "`source_policy.egress_gate` 처럼", "관문 인정 기준", "스캔 범위", "`tests/` 는 제외", "build_checked_opener", "check_final_url", "own_repo", "max_redirects", "허용 목적"):
            self.assertIn(needle, section, needle)
        self.assertNotIn("모든 외부 호출 지점을 시험이 확인", DOC)
        self.assertNotIn("모든 외부 호출 지점을 시험이 확인", egress.__doc__)
        self.assertIn("보증이 아니다", egress.__doc__)
        self.assertIn("사람 검토가 마지막 방어선", egress.__doc__)
        test_egress_doc = (ROOT / "tests" / "test_egress.py").read_text(encoding="utf-8").split('"""', 2)[1]
        self.assertIn("보증이 아니다", test_egress_doc)

    def test_the_state_after_enabling_the_ai_policy_file_and_the_enable_order_are_written_honestly(self):
        """P07·P08·P09: 켠 뒤의 상태(새 글 0·36시간 뒤 STALE·ALL_LANES_EMPTY·ALL_REJECTED·연습과 실제 어긋남), AI 정책 파일이 실행 중에 읽히지 않는다는 것, Pew 체크리스트."""
        limits = DOC.split("## 12.", 1)[1].split("## 13.", 1)[0]
        for needle in ("새 글이 0", "STALE", "max_gap_hours", "36시간", "ALL_LANES_EMPTY", "ALL_REJECTED", "스텁", "PUBLISHED", "FACT 2단계", "연결되기 전에는 켜지 않는다"):
            self.assertIn(needle, limits, needle)
        order = DOC.split("## 11.", 1)[1].split("## 12.", 1)[0]
        for needle in ("이 단계가 끝나기 전에는", "정지를 풀기 전에", "`terms.status`", "별도 T3"):
            self.assertIn(needle, order, needle)
        ai = DOC.split("## 10.", 1)[1].split("## 11.", 1)[0]
        for needle in ("코드는 이 파일을 실행 중에 읽지 않는다", "`legacy` 에서는 외부 기사 요약이 지금도 Gemini 입력으로 간다", "`allowlist` 에서만", "legacy_policy_notice"):
            self.assertIn(needle, ai, needle)
        notes = " ".join(json.loads((ROOT / "pipeline" / "ai_processor_policy.json").read_text(encoding="utf-8"))["notes"])
        self.assertNotIn("코드가 지킨다", notes)
        self.assertIn("코드는 이 파일을 실행 중에 읽지 않는다", notes)
        self.assertIn("legacy 에서는 외부 기사 요약이 지금도 Gemini 입력으로 간다", notes)

    def test_the_fact_contract_lists_the_new_duties(self):
        section = DOC.split("## 9. FACT 와의 인터페이스 약속", 1)[1].split("## 10.", 1)[0]
        for needle in ("build_checked_opener", "check_final_url", "`source`·`publisher_domain`·`citation`", "자체 문자열", "shadow_run.py", "own_title_batches", "의무"):
            self.assertIn(needle, section, needle)

    def test_the_url_ok_reason_and_the_photo_limits_name_the_real_hosts(self):
        for needle in ("FIX_IMAGES", "기존 글 머리말의 `image:` 주소 호스트 전부(Unsplash 외 NASA 이미지 호스트 포함)", "운영자 결정"):
            self.assertIn(needle, DOC, needle)

    def test_provider_counts_in_the_doc_match_the_file(self):
        registry = sr.load_registry(today="2026-11-09")
        providers = registry.providers()
        self.assertIn(f"**{len(providers)} Provider**", DOC)
        by_tier = {}
        for p in providers:
            by_tier[p.strict_tier] = by_tier.get(p.strict_tier, 0) + 1
        self.assertIn(f"strict Tier 1 이 {by_tier[1]}, 3 이 {by_tier[3]}, 4 가 {by_tier[4]}", DOC)
        by_status = {}
        for p in providers:
            by_status[p.effective_status] = by_status.get(p.effective_status, 0) + 1
        self.assertIn(f"`자동화 제외` {by_status['자동화 제외']}·`참고 전용` {by_status['참고 전용']}·`완전 제외` {by_status['완전 제외']}", DOC)
        self.assertIn(f"`data` {sum(1 for p in providers if p.provider_class == 'data')}·`image` {sum(1 for p in providers if p.provider_class == 'image')}", DOC)
        self.assertEqual([p.provider_id for p in registry.active_providers()], ["noaa_swpc_json"])      # 켜는 변경(T3, 패치 02) 뒤: 켜진 곳은 이 하나(전에는 0)
        self.assertIn("ACTIVE 는 1", DOC)
        paragraph = next(line for line in DOC.splitlines() if line.startswith("5. 허용 목록은 Tier 감사표"))      # N2(D-321): 켜는 변경 뒤 이 문단이 앞뒤가 맞는다 — 'ACTIVE 는 1' 이면서 '켜지는 않았다' 가 남지 않는다
        for stale in ("ACTIVE 는 0", "켜지는 않았다", "켜기 직전 모양"):
            self.assertNotIn(stale, paragraph)
        self.assertIn("`noaa_swpc_json` 하나를 켰다", paragraph)
        self.assertIn("나머지 61곳은 모두 꺼져 있다", paragraph)

    def test_the_interface_promised_to_the_fact_path_exists_under_the_documented_names(self):
        section = DOC.split("## 6. 질의 API", 1)[1].split("## 7.", 1)[0]
        for name in ("load_registry(path=None, today=None)", "Registry.get(provider_id)", "Registry.active_providers()", "Registry.is_url_allowed(url, purpose)"):
            self.assertIn(name, section)
        registry = sr.load_registry(today="2026-11-09")
        for method in ("get", "active_providers", "is_url_allowed"):
            self.assertTrue(callable(getattr(registry, method)))
        for field in ("provider_id", "strict_tier", "effective_status", "access", "attribution_template", "snapshot", "policy", "retention_days"):
            self.assertIn(f"`{field}`", section)
            self.assertTrue(hasattr(registry.get("pew_rss"), field), field)

    def test_the_outcome_code_the_scenario_count_and_the_baseline_are_documented(self):
        self.assertIn(source_policy.NO_ACTIVE_OUTCOME, DOC)
        self.assertIn("여덟 시나리오", DOC)
        self.assertIn("78c6b89", DOC)
        for needle in ("켜는 것", "T3", "legacy", "allowlist", "own_title", "자체 제목"):
            self.assertIn(needle, DOC, needle)


class OtherDocsTest(unittest.TestCase):
    def test_architecture_has_the_registry_field_stage_and_exit_code_rows(self):
        self.assertTrue(re.search(r"^\| `source_policy` \|", ARCH, re.M))
        self.assertTrue(re.search(r"^\| \*\*Source policy\*\* \|", ARCH, re.M))
        self.assertTrue(re.search(r"^\| 정상 건너뜀\(소스 정책\) \|.*SOURCE_POLICY_NO_ACTIVE_PROVIDER", ARCH, re.M))
        self.assertIn("(./SOURCE_POLICY.md)", ARCH)
        row = re.search(r"^\| `source_policy` \|.*$", ARCH, re.M).group(0)
        for needle in ("legacy", "allowlist", "T3", "SOURCE_POLICY_NO_ACTIVE_PROVIDER"):
            self.assertIn(needle, row, needle)

    def test_the_fix_round_defects_d170_to_d179_are_registered_with_status_and_tests(self):
        """이 묶음의 결함 행: 수정 라운드 D-170–D-178(옛 D-140–D-148)과 병합 준비 라운드 D-179. 번호 범위는 이 묶음의 것이고 다른 묶음의 번호 집합은 보지 않는다."""
        for number in range(170, 180):
            rows = re.findall(rf"^\| \*\*D-{number}\*\* \|.*$", DEFECTS, re.M)
            self.assertEqual(len(rows), 1, f"D-{number}")
            self.assertRegex(rows[0], r"\*\*(해결|완화|열림)\*\*", f"D-{number} 상태")
            self.assertRegex(rows[0], r"2026-11-(09|10)", number)
            self.assertNotIn("~", rows[0], number)
            self.assertEqual(rows[0].count("|"), 7, f"D-{number}: 표의 여섯 칸")
        text = " ".join(re.findall(r"^\| \*\*D-17[0-8]\*\* \|.*$", DEFECTS, re.M))
        for needle in ("tests/test_egress.py", "tests/test_source_registry.py", "tests/test_source_policy.py", "OPS_RULES", "build_checked_opener", "www.googleapis.com", "STALE", "own_title_batches",
                       "legacy_policy_notice", "ALLOWED_PURPOSES", "A10"):
            self.assertIn(needle, text, needle)
        latest = re.search(r"^\| \*\*D-179\*\* \|.*$", DEFECTS, re.M).group(0)
        for needle in ("관문 인정", "A10", "ai_use", "check_ai_input", "own_data_only", "CallBudget", "noaa_swpc_json", "SRCV2", "test_source_registry_007.py", "test_egress_budget.py", "아무것도 켜지 않았다"):
            self.assertIn(needle, latest, needle)
        self.assertEqual(len(re.findall(r"^\| \*\*D-96\*\* \|", DEFECTS, re.M)), 1)             # D-96 은 그대로(병합 때 다른 가지의 행과 함께 남긴다)
        ids = re.findall(r"^\| \*\*(D-\d+)\*\* \|", DEFECTS, re.M)
        self.assertEqual(len(ids), len(set(ids)), "결함 번호가 겹친다")
        self.assertFalse([d for d in ids if re.fullmatch(r"D-14[0-8]", d)], "옛 번호 D-140–D-148 이 남아 있다(이 묶음의 행은 D-170–D-178 로 옮겼다)")

    def test_the_007_decision_is_written_into_the_doc(self):
        """운영자 결정 007 반영: ai_use·own_data_only·AI 입력 거부·호출 예산·새 규칙 S9–S11·A11·쪼갠 항목과 켜기 전 남은 것."""
        for needle in ("`ai_use`", "`own_data_only`", "`BY_CELL`", "`NEVER`", "check_ai_input", "AiInputDenied", "CallBudget", "run_call_cap", "아무것도 켜지 않는다", "ai_input` 칸만 건너뛴다"):
            self.assertIn(needle, DOC, needle)
        section = DOC.split("## 14.", 1)[1]
        for provider_id in ("noaa_swpc_json", "statcan_wds", "uk_govuk_api", "swpc_f107_nrc", "swpc_kyoto_dst", "swpc_sidc_penticton_fields"):
            self.assertIn(f"`{provider_id}`", section, provider_id)
            self.assertIsNotNone(sr.load_registry(today="2026-11-10").get(provider_id), provider_id)
        for needle in ("켜기 전 남은 확인", "필드 화이트리스트", "observed_swpc_ssn", "공식 수치 한도 없음", "자체 상한", "제3자", "NOAA 가 만든 값", "17 U.S.C. 403", "영구 상태", "조사 전", "설계안"):
            self.assertIn(needle, DOC if needle in ("영구 상태", "설계안") else section, needle)
        self.assertIn("Fact 후보에는 이 정화를 적용하지 않는다", DOC)

    def test_the_fact_candidates_do_not_use_the_prompt_sanitizers_and_the_doc_says_so_in_one_voice(self):
        """AI 흐름 감사 F7·F14·R9: `prompt_inputs`·`own_title_batches` 는 Fact 후보에 쓰지 않는다 — 9절 2·3·7항과 12절 ③ 이 FACT_PATH 11절과 한 가지 말이다."""
        section = DOC.split("## 9. FACT 와의 인터페이스 약속", 1)[1].split("## 10.", 1)[0]
        for item in ("2. **", "3. **", "7. **"):
            body = next(line for line in section.splitlines() if line.startswith(item))
            self.assertRegex(body, r"Fact 후보(에는|는|에)", item)
        self.assertIn("`own_title_batches`·`prompt_inputs` 는 Fact 후보에 쓰지 않는다", section)
        self.assertIn("`facts` 경로는 Gemini 를 부르지 않", section)
        limits = DOC.split("## 12.", 1)[1].split("## 13.", 1)[0]
        self.assertIn("피드형(일반) 후보 흐름이 `allowlist` 로 돌 때", limits)
        self.assertIn("Fact 후보(`content_source: facts`)는 이 흐름을 지나지 않고 프롬프트도 없다", limits)
        fact_path = (ROOT / "docs" / "FACT_PATH.md").read_text(encoding="utf-8")
        self.assertIn("Gemini 호출·피드 후보 대신", fact_path)                                           # FACT_PATH 11절 2항의 같은 말

    def test_the_new_outcome_code_is_in_the_actions_guide(self):
        self.assertTrue(re.search(r"^\| `SOURCE_POLICY_NO_ACTIVE_PROVIDER` \|.*초록 \+ 파란 안내.*$", ACTIONS, re.M))
        self.assertIn("SOURCE_POLICY_NO_ACTIVE_PROVIDER", re.search(r"^\| 결과 코드 \|.*$", ACTIONS, re.M).group(0))
        row = re.search(r"^\| `SOURCE_POLICY_NO_ACTIVE_PROVIDER` \|.*$", ACTIONS, re.M).group(0)
        for needle in ("allowlist", "ACTIVE 콘텐츠 Provider", "36시간", "STALE", "SOURCE_POLICY.md"):
            self.assertIn(needle, row, needle)

    def test_the_defect_register_has_d96_with_status_and_tests(self):
        row = re.search(r"^\| \*\*D-96\*\* \|.*$", DEFECTS, re.M)
        self.assertIsNotNone(row)
        text = row.group(0)
        for needle in ("완화", "legacy", "T3", "source_registry.json", "egress.py", "source_policy", "SOURCE_POLICY.md", "test_source_registry.py"):
            self.assertIn(needle, text, needle)
        self.assertEqual(len(re.findall(r"^\| \*\*D-96\*\* \|", DEFECTS, re.M)), 1)


if __name__ == "__main__":
    unittest.main()
