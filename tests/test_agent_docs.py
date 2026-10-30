"""위임 설계 문서·Copilot 지침이 저장소의 실제 모습과 어긋나지 않게 잡는 시험(표류 방지).

문서 표(워크플로·스크립트·일 번호)와 지침 파일의 금지 목록이 사실과 달라지면 위임받은 주체가 틀린 절차를 따르게 된다.
네트워크 없이 파일만 읽는다.
"""
import json
import re
import unittest

import _bootstrap  # noqa: F401

ROOT = _bootstrap.ROOT
RUNBOOK = (ROOT / "docs" / "AGENT_RUNBOOK.md").read_text(encoding="utf-8")
DELEGATION = (ROOT / "docs" / "AGENT_DELEGATION.md").read_text(encoding="utf-8")
COPILOT = (ROOT / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
CODE_REVIEW_LIMIT = 4000     # Copilot 코드 리뷰는 지침 파일마다 앞 4,000자만 읽는다(GitHub 문서)
JOBS = {f"J{n}" for n in range(1, 13)}


def job_numbers(text, pattern):
    return set(re.findall(pattern, text, re.M))


class RunbookCoversTheRepoTest(unittest.TestCase):
    def test_every_workflow_file_is_listed_in_the_runbook_table(self):
        names = sorted(p.name for p in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertGreater(len(names), 10)
        missing = [name for name in names if f"`{name}`" not in RUNBOOK]
        self.assertEqual(missing, [], "docs/AGENT_RUNBOOK.md §5 표에 빠진 워크플로 — 같은 변경에서 한 줄을 더하세요")

    def test_no_workflow_listed_in_the_runbook_is_missing_from_the_repo(self):
        listed = set(re.findall(r"^\| `([a-z0-9-]+\.yml)` \|", RUNBOOK, re.M))
        existing = {p.name for p in (ROOT / ".github" / "workflows").glob("*.yml")}
        self.assertEqual(sorted(listed - existing), [], "표에 있지만 저장소에 없는 워크플로")

    def test_every_script_is_listed_in_the_runbook_tools_table(self):
        names = sorted(p.name for p in (ROOT / "scripts").glob("*.py"))
        missing = [name for name in names if f"scripts/{name}" not in RUNBOOK]
        self.assertEqual(missing, [], "docs/AGENT_RUNBOOK.md §7 도구 표에 빠진 스크립트")

    def test_every_workflow_name_in_the_table_matches_the_real_name(self):
        for name in sorted(p.name for p in (ROOT / ".github" / "workflows").glob("*.yml")):
            real = re.search(r'^name:\s*"?(.+?)"?\s*$', (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"), re.M).group(1)
            row = next(line for line in RUNBOOK.splitlines() if line.startswith(f"| `{name}` |"))
            self.assertIn(f"`{real}`", row, f"{name}: 표의 Actions 이름이 실제 name 과 다름")

    def test_scheduled_workflows_show_their_real_cron_times(self):
        """표의 시각(UTC)이 실제 cron 과 같은지: 매일 한 번 도는 예약만 비교한다."""
        for name, expect, kst in (("blogger-en.yml", "02:00", "11:00"), ("blogger-ko.yml", "03:30", "12:30"), ("tistory.yml", "05:20", "14:20"), ("naver.yml", "06:20", "15:20")):
            text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            cron = re.search(r"cron:\s*'(\d+) (\d+) \* \* \*'", text)
            self.assertIsNotNone(cron, name)
            self.assertEqual(f"{int(cron.group(2)):02d}:{int(cron.group(1)):02d}", expect, name)
            row = next(line for line in RUNBOOK.splitlines() if line.startswith(f"| `{name}` |"))
            self.assertIn(expect, row, name)
            self.assertIn(f"{expect}(한국 {kst})", row, f"{name}: UTC {expect} 는 한국 시각 {kst} 이다")


class JobNumbersAreConsistentTest(unittest.TestCase):
    def test_runbook_has_a_procedure_and_a_catalog_row_for_every_job(self):
        headings = job_numbers(RUNBOOK, r"^### (J\d+)\.")
        catalog = job_numbers(RUNBOOK, r"^\| \*\*(J\d+)\*\* \|")
        self.assertEqual(headings, JOBS)
        self.assertEqual(catalog, JOBS)

    def test_delegation_matrix_covers_the_same_jobs(self):
        matrix = job_numbers(DELEGATION, r"^\| (J\d+) ")
        self.assertEqual(matrix, JOBS)

    def test_delegation_points_to_the_runbook_and_back(self):
        self.assertIn("AGENT_RUNBOOK.md", DELEGATION)
        self.assertIn("AGENT_DELEGATION.md", RUNBOOK)
        self.assertTrue((ROOT / "docs" / "AGENT_RUNBOOK.md").exists() and (ROOT / "docs" / "AGENT_DELEGATION.md").exists())


class InstructionFilesTest(unittest.TestCase):
    FILES = [ROOT / ".github" / "copilot-instructions.md"] + sorted((ROOT / ".github" / "instructions").glob("*.instructions.md"))

    def test_every_instruction_file_fits_the_code_review_limit(self):
        self.assertGreaterEqual(len(self.FILES), 5)
        for path in self.FILES:
            length = len(path.read_text(encoding="utf-8"))
            self.assertLessEqual(length, CODE_REVIEW_LIMIT, f"{path.name}: {length}자 — Copilot 코드 리뷰는 앞 4,000자만 읽는다")

    def test_path_specific_instruction_files_declare_apply_to(self):
        for path in self.FILES[1:]:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(re.match(r'---\napplyTo: "[^"\n]+"\n---\n', text.replace("\r\n", "\n")), path.name)

    def test_copilot_instructions_name_the_delegation_mode_and_its_hard_stops(self):
        for needle in ("위임 작업", "T0~T2만", "T3", "Ad-Surface-Approved:", "AD-2", "독립 검증 필요", "운영자 확인 필요", "scripts/final_checks.py",
                       "docs/AGENT_RUNBOOK.md", "HANDLER.md", "SECURITY_GUARDRAILS"):
            self.assertIn(needle, COPILOT, needle)

    def test_ad_surface_paths_are_the_same_in_the_registry_agents_md_and_copilot_instructions(self):
        registry = json.loads((ROOT / "pipeline" / "blogs.json").read_text(encoding="utf-8"))
        protected = {path for blog in registry["blogs"] if blog.get("ad_surface") for path in blog.get("protected_paths", [])}
        self.assertGreaterEqual(len(protected), 9)
        verification = {path for path in protected if re.match(r"^(google|naver)[0-9a-f]+\.html$", path)}     # 사이트 소유 확인 파일: AGENTS.md 는 '사이트 인증 파일'로 뭉뚱그린다
        self.assertEqual(len(verification), 2)
        self.assertIn("사이트 인증 파일", AGENTS)
        for path in sorted(protected):
            self.assertIn(path, COPILOT, f"{path}: 레지스트리의 광고 표면이 Copilot 지침의 금지 목록에 없다")
            if path not in verification:
                self.assertIn(path.rstrip("/"), AGENTS, f"{path}: 레지스트리의 광고 표면이 AGENTS.md 에 없다")

    def test_the_delegation_doc_documents_the_agent_marker_rule_that_the_validator_enforces(self):
        validator = (ROOT / "scripts" / "validate_repo.py").read_text(encoding="utf-8")
        self.assertIn('"AD-2"', validator)
        self.assertIn("AD-2", DELEGATION)
        self.assertIn("AD-2", (ROOT / "docs" / "SECURITY_GUARDRAILS.md").read_text(encoding="utf-8"))


class DelegationDecisionsTest(unittest.TestCase):
    def test_the_operator_questions_have_defaults_and_none_needs_a_t3_approval(self):
        rows = {m.group(1): m.group(0) for m in re.finditer(r"^\| (D\d+) \|.*$", DELEGATION, re.M)}
        self.assertEqual(sorted(rows), ["D1", "D2"])
        for number, row in rows.items():
            self.assertGreaterEqual(row.count("|"), 5, number)
            self.assertNotIn("T3 승인", row, number)
        self.assertIn("안 보임", rows["D1"])
        self.assertIn("없음", rows["D2"])
        self.assertIn("T3 승인이 필요한 항목이 없습니다", DELEGATION)


class PinnedRulesTest(unittest.TestCase):
    """독립 검증: 문서 변이 26개 중 13개가 살아남았다 — 사실이 바뀌면 문서도 바뀌게 규칙을 시험으로 고정한다."""

    WORKFLOW_ROWS = {      # 워크플로 파일: 절차서 표의 그 행에 있어야 하는 글자(트리거·시각)
        "chanceblog.yml": ("17분", "47분"), "watchdog.yml": ("03:30", "15:30"), "ops-inbox.yml": ("2시간", "텔레그램"),
        "ai-request.yml": ("ai/claude/**",), "guardrails.yml": ("main push", "PR"), "pages.yml": ("main push",),
        "sync-issue-form.yml": ("main push", "*.md"), "issue-edit.yml": ("이슈",), "pr-scope-check.yml": ("PR",),
        "operator-reply.yml": ("이슈가 열릴 때",), "telegram-test.yml": ("수동",), "chance-fix-images.yml": ("수동",), "blogger.yml": ("호출",),
    }
    REAL_CRONS = {"chanceblog.yml": ["17 * * * *", "47 * * * *"], "watchdog.yml": ["30 3,15 * * *"], "ops-inbox.yml": ["40 */2 * * *"]}

    def test_each_workflow_row_states_its_real_trigger(self):
        for name, needles in self.WORKFLOW_ROWS.items():
            row = next(line for line in RUNBOOK.splitlines() if line.startswith(f"| `{name}` |"))
            for needle in needles:
                self.assertIn(needle, row, (name, needle))

    def test_the_hourly_and_twice_daily_schedules_in_the_table_are_the_real_cron_lines(self):
        for name, crons in self.REAL_CRONS.items():
            workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            for cron in crons:
                self.assertIn(f"cron: '{cron}'", workflow, name)

    def test_the_ai_request_workflow_really_triggers_only_on_ai_claude_branches(self):
        workflow = (ROOT / ".github" / "workflows" / "ai-request.yml").read_text(encoding="utf-8")
        self.assertIn("- 'ai/claude/**'", workflow)
        self.assertEqual(workflow.count("branches:"), 1)

    def test_the_ops_inbox_telegram_fact_in_the_docs_matches_the_code(self):
        self.assertIn("TELEGRAM_BOT_TOKEN", (ROOT / ".github" / "workflows" / "ops-inbox.yml").read_text(encoding="utf-8"))
        self.assertIn("def approval_items", (ROOT / "pipeline" / "inbox.py").read_text(encoding="utf-8"))
        for needle in ("확인 필요 모음", "텔레그램", "승인 대기"):
            self.assertIn(needle, DELEGATION, needle)

    def test_the_a_mode_rules_of_the_copilot_instructions_are_kept(self):
        for needle in ("처음부터 끝까지 읽은 뒤", "원문과 글자 하나까지 대조", "요청한 부분만", "바꾼 곳 / 바꾸지 않은 곳", "Fixes #이슈번호", "그대로** 교체",
                       "소유자가 이슈 양식으로 그 문구를 명시적으로 요청한 경우만", "광고 표면은 고치지 않는다", "자동 처리 양식이나 세션형 AI 가 필요"):
            self.assertIn(needle, COPILOT, needle)

    def test_the_b_mode_hard_stops_are_all_there(self):
        for needle in ("소유자가 직접 Copilot 을 지정", "'구현·시험까지'", "T3(광고 표면, 시크릿·계정, `mode` 변경, 새 블로그·플랫폼, 삭제, 정책·톤, 비용 증가)",
                       "`.github/` 전체", "`scripts/validate_repo.py`", "`pipeline/blogs.json`(어느 필드든)", "`AGENTS.md`·`CLAUDE.md`·`GEMINI.md`",
                       "`docs/CHARTER.md`·`docs/SECURITY_GUARDRAILS.md`", "자동 commit/push·예약 작업·강제 push·삭제", "네트워크 없이",
                       "pip install -r requirements-dev.txt", "승인이 아니며", "Python 3.10"):
            self.assertIn(needle, COPILOT, needle)

    def test_code_and_docs_instruction_files_cover_their_paths_and_forbid_the_same_things(self):
        code = (ROOT / ".github" / "instructions" / "code.instructions.md").read_text(encoding="utf-8")
        apply_to = re.search(r'applyTo: "([^"]+)"', code).group(1)
        for path in ("pipeline/**", "scripts/**", "tests/**"):
            self.assertIn(path, apply_to)
        for needle in ("네트워크 없이", "Python 3.10", "어느 필드든", "scripts/validate_repo.py", "자동 commit/push", "`.github/` 전체"):
            self.assertIn(needle, code, needle)
        docs = (ROOT / ".github" / "instructions" / "handover-docs.instructions.md").read_text(encoding="utf-8")
        self.assertIn("docs/**", re.search(r'applyTo: "([^"]+)"', docs).group(1))
        self.assertIn("`docs/CHARTER.md`·`docs/SECURITY_GUARDRAILS.md`를 고치지 않는다", docs)

    def test_agents_md_points_to_the_runbook_and_the_delegation_design(self):
        self.assertIn("docs/AGENT_RUNBOOK.md", AGENTS)
        self.assertIn("docs/AGENT_DELEGATION.md", AGENTS)
        self.assertIn("T3 는 위임하지 않고", AGENTS)

    def test_the_runbook_ref_pattern_finds_two_level_branch_names(self):
        """`ai/*` 패턴은 `ai/claude/<주제>` 를 못 찾아 빈 결과 → 번호가 R-001 로 겹칠 수 있었다(독립 검증이 실행으로 확인)."""
        self.assertIn("'refs/remotes/origin/ai'", RUNBOOK)
        self.assertNotIn("origin/ai/*'", RUNBOOK)
        self.assertIn("R-001", RUNBOOK)

    def test_the_delegation_doc_states_what_is_never_delegated_and_the_safe_order(self):
        for needle in ("T3 는 위임하지 않습니다", "구현자 ≠ 검증자", "승인 건너뛰기", "diff 를 먼저 읽", "끄고 둡니다", "한계(사고 방지용"):
            self.assertIn(needle, DELEGATION, needle)

    def test_the_safe_order_of_a_copilot_pr_is_pinned(self):
        """안전의 핵심 순서: 세션형 AI 가 diff 를 먼저 읽고(워크플로는 PR 쪽 파일로 돈다), 클릭 직전에 머리 커밋이 같은지 다시 본다."""
        for needle in ("**세션형 AI(S)가 먼저 diff 를 읽습니다**", "승인 클릭 직전", "`.github/` 전체", "이 시점에는 검사 워크플로가 돌지 않습니다"):
            self.assertIn(needle, DELEGATION, needle)
        for needle in ("S 가 먼저 diff 를 읽습니다", "클릭 직전", "`.github/` 전체"):
            self.assertIn(needle, RUNBOOK, needle)

    def test_the_known_facts_about_alerts_and_limits_are_pinned(self):
        for needle in ("**이미 있는 것**", "approval_items", "pull_items", "자동 commit/push·예약 작업 금지", "한계(사고 방지용"):
            self.assertIn(needle, DELEGATION, needle)

    def test_ad_surface_edits_are_consistently_not_for_copilot(self):
        """독립 검증 2차: 지침은 광고 표면 수정을 허용하면서 검증기는 막는 모순이 있었다 — 모든 안내가 'Copilot 은 고치지 않고 세션형 AI·자동 처리 양식으로'로 같다."""
        pages = (ROOT / ".github" / "instructions" / "pages.instructions.md").read_text(encoding="utf-8")
        guide = (ROOT / "docs" / "COPILOT_GUIDE.md").read_text(encoding="utf-8")
        for name, text in (("copilot-instructions", COPILOT), ("pages.instructions", pages), ("COPILOT_GUIDE", guide)):
            self.assertIn("Ad-Surface-Approved:", text, name)
            self.assertNotIn("승인은 병합하는 운영자 몫", text, name)
        self.assertIn("고치지 않는다", COPILOT)
        self.assertIn("세션형 AI", pages)
        self.assertIn("세션형 AI", guide)

    def test_the_automatic_edit_scope_is_off_limits_for_delegated_work(self):
        """CHARTER §6.2: `pipeline/edits/` 의 NEVER_ALLOW 를 줄이거나 자동 수정 범위를 넓히는 것은 T3 다."""
        code = (ROOT / ".github" / "instructions" / "code.instructions.md").read_text(encoding="utf-8")
        for name, text in (("copilot-instructions", COPILOT), ("code.instructions", code)):
            self.assertIn("`pipeline/edits/`", text, name)

    def test_the_guardrail_doc_describes_ad_2_as_the_code_does(self):
        guard = (ROOT / "docs" / "SECURITY_GUARDRAILS.md").read_text(encoding="utf-8")
        row = next(line for line in guard.splitlines() if line.startswith("| AD-2 |"))
        for needle in ("작성자나 커미터", "NUL", "개수"):
            self.assertIn(needle, row, needle)

    def test_the_runbook_explains_the_squash_trap_and_the_incomplete_exit_code(self):
        for needle in ("squash 병합하면 커밋 작성자가 Copilot", "종료 코드는 0 모두 통과 · 1 실패 · 3 **불완전**", "S 가 먼저 diff 를 읽습니다"):
            self.assertIn(needle, RUNBOOK, needle)


if __name__ == "__main__":
    unittest.main()
