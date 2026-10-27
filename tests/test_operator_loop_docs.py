"""운영자 요청함의 문서와 코드가 어긋나지 않는지 — 문서가 인용한 문구·표·한도·이름이 코드와 양식의 실제 값과 같은지, 문서 속 예시가 실제로 동작하는지.

문서를 사람이 고치고 코드를 따로 고치면 운영자가 화면에서 보는 말과 문서가 달라진다(운영자는 비개발자이고 문서가 유일한 안내다). 그래서 문서가 코드의 값을 인용한 자리를 시험이 붙들어 둔다.
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
import operator_loop_helpers as oh
from pipeline import notify
from pipeline import operator_loop as ol
from test_workflow_names import load

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

GUIDE = ROOT / ol.GUIDE_PATH
FOLDER_README = ROOT / ol.REQUEST_DIR / "README.md"
TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"


def text_of(path):
    return Path(path).read_text(encoding="utf-8")


def rel_text(rel):
    return text_of(ROOT / rel)


def form_name(file):
    return yaml.safe_load(text_of(TEMPLATES / file))["name"]


def table_rows(markdown, header_first_cell):
    """마크다운 표 중 첫 칸 제목이 header_first_cell 인 표의 본문 행(칸 목록)들."""
    lines, rows, inside = markdown.splitlines(), [], False
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")] if line.strip().startswith("|") else None
        if cells is None:
            if inside:
                break
            continue
        if not inside:
            inside = cells[0] == header_first_cell
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        rows.append(cells)
    return rows


class GuideMatchesFormsTest(unittest.TestCase):
    """사용법 문서(`인수인계/운영자_요청함_사용법.md`)가 양식 파일과 접수 코드의 말을 그대로 인용하는지."""

    def setUp(self):
        self.guide = text_of(GUIDE)

    def test_every_answer_the_reply_form_offers_is_quoted_word_for_word(self):
        for _short, full in ol.ANSWER_OPTIONS:
            self.assertIn(f"`{full}`", self.guide, full)

    def test_every_choice_of_the_task_form_is_quoted_word_for_word(self):
        for _short, full in ol.TASK_APPROVAL_OPTIONS:
            self.assertIn(f"`{full}`", self.guide, full)
        for option in ol.TASK_URGENCY_OPTIONS:
            self.assertIn(f"`{option}`", self.guide, option)

    def test_the_guide_names_both_forms_exactly_as_the_menu_shows_them(self):
        for file in ("ai-reply.yml", "ai-task.yml"):
            self.assertIn(f"`{form_name(file)}`", self.guide, file)

    def test_the_field_names_the_guide_tells_the_operator_to_fill_are_the_forms_labels(self):
        for label in ("요청 번호", "답변", "선택", "메모"):
            self.assertIn(f"**{label}**", self.guide, label)
            self.assertIn(label, dict(ol.REPLY_FIELDS).values())
        for label in ("해 주었으면 하는 일", "끝났다고 볼 기준", "긴급도", "승인 범위"):
            self.assertIn(label, self.guide, label)
            self.assertIn(label, dict(ol.TASK_FIELDS).values())

    def test_the_kind_table_lists_every_label_the_telegram_message_can_show(self):
        rows = table_rows(self.guide, "종류")
        self.assertEqual([row[0] for row in rows], [notify.REQUEST_KIND_LABELS[kind] for kind in ("merge", "run", "confirm", "decision", "info")])
        self.assertEqual(set(row[0] for row in rows), set(notify.REQUEST_KIND_LABELS.values()))

    def test_the_kinds_that_need_an_answer_are_the_ones_the_guide_says_get_the_how_to_answer_line(self):
        for kind in notify.REQUEST_ANSWER_KINDS:
            self.assertIn(notify.REQUEST_KIND_LABELS[kind], self.guide)
        self.assertIn("`결정 부탁`·`확인 부탁` 메시지에는", self.guide)
        self.assertEqual(sorted(notify.REQUEST_ANSWER_KINDS), ["confirm", "decision"])

    def test_the_telegram_messages_quoted_in_the_guide_are_what_the_code_sends(self):
        head = re.sub(r"</?b>", "", notify.format_ai_request("R-001", "merge", "제목", "요약")).splitlines()[0]
        self.assertEqual(head, f"{notify.BELL_MARK} AI 요청 R-001 · 병합 부탁")
        self.assertIn(head, self.guide)
        urgent = re.sub(r"</?b>", "", notify.format_ai_request("R-001", "merge", "제목", "요약", urgency="급함")).splitlines()[0]
        self.assertTrue(urgent.endswith(f"{notify.SIREN_MARK} 급함"))
        self.assertIn(f"`{notify.SIREN_MARK} 급함`", self.guide)
        asking = notify.format_ai_request("R-001", "decision", "제목", "요약")
        self.assertIn("답하는 법: 아래 [답하기] → 양식에서 R-001 선택", asking)
        self.assertIn("`답하는 법: 아래 [답하기] → 양식에서 R-001 선택`", self.guide)
        received = notify.format_reply_received("R-001", "승인", 12)
        self.assertEqual(received, f"{notify.OK_MARK} 답변 접수 R-001 → 승인(이슈 #12)")
        self.assertIn(received.replace("#12", "#N"), self.guide)
        task = notify.format_task_received(13, "급함", True)
        self.assertTrue(task.startswith(f"{notify.OK_MARK} 새 일 요청 접수(이슈 #13)"))
        self.assertIn(f"`{notify.OK_MARK} 새 일 요청 접수(이슈 #N)`", self.guide)
        self.assertIn("관련 PR: #번호", self.guide)
        self.assertIn("관련 PR: #7", notify.format_ai_request("R-001", "merge", "제목", "요약", pr=7))

    def test_the_buttons_the_guide_lists_are_the_buttons_the_code_attaches(self):
        request = ol.Request("R-001", "merge", "t", "s", "보통", 5, None, "R-001_x.md")
        labels = [label for label, _url in ol.request_buttons(request, "ai/claude/x", "main")]
        self.assertEqual(labels, ["요청 열기", "PR 열기", "답하기", "사용법"])
        for label in labels:
            self.assertIn(f"**{label}**", self.guide, label)
        self.assertIn(f"버튼은 최대 {len(labels)}개", self.guide)

    def test_the_comments_and_log_lines_the_guide_quotes_exist_in_the_code(self):
        source = text_of(ROOT / "pipeline" / "operator_loop.py")
        for phrase in ("접수했습니다 — 요청", "접수했습니다 — 새 일 요청", "양식 모양이 달라 처리하지 못했습니다", "알 수 없는 요청 번호", "AI 요청 알림: {request.id} 을 알렸습니다"):
            self.assertIn(phrase, source, phrase)
        for phrase in ("접수했습니다 — 새 일 요청", "양식 모양이 달라 처리하지 못했습니다", "알 수 없는 요청 번호", "AI 요청 알림: R-… 을 알렸습니다"):
            self.assertIn(phrase, self.guide, phrase)

    def test_the_acknowledgement_example_matches_what_the_code_writes(self):
        sub = ol.parse_reply(ol.REPLY_TITLE_PREFIX + "x", oh.reply_body(request_id="R-001", answer=oh.ANSWER["승인"]), oh.OWNER, "OWNER", oh.OWNER)
        comment = ol.reply_comment(sub, True)
        self.assertIn("접수했습니다 — 요청 **R-001** · 답: **승인**", comment)
        self.assertIn("`접수했습니다 — 요청 R-001 · 답: 승인`", self.guide)

    def test_the_labels_and_title_prefixes_the_guide_mentions_are_the_codes(self):
        for token in (ol.LABEL_REPLY, ol.LABEL_TASK, ol.REPLY_TITLE_PREFIX.strip(), ol.TASK_TITLE_PREFIX.strip()):
            self.assertIn(token, self.guide, token)

    def test_the_secret_names_the_guide_lists_are_the_ones_the_repository_uses(self):
        registry = rel_text("pipeline/blogs.json")
        for name in ("BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            self.assertIn(f"`{name}`", self.guide, name)
        self.assertIn("BLOGGER_BLOG_ID", registry)
        self.assertIn("BLOGGER_KO_*", self.guide)

    def test_the_auth_check_texts_the_guide_tells_the_operator_to_look_for_exist_in_the_code(self):
        from pipeline import run
        for name in ("AUTH_CHECK_OK", "AUTH_CHECK_FAILED", "SECRETS_MISSING"):
            self.assertIn(f"`{name}`", self.guide, name)
            self.assertIn(name, text_of(ROOT / "pipeline" / "run.py"), name)
        for text in (run.CLEANED_SUMMARY, run.CLEANED_NOTICE):
            self.assertIn("보이지 않는 문자", text)
        self.assertIn("`시크릿 값에 보이지 않는 문자가 섞여 있어 지우고 썼습니다`", self.guide)
        self.assertIn("시크릿 값에 보이지 않는 문자가 섞여 있어 지우고 썼습니다", run.CLEANED_SUMMARY)

    def test_the_workflow_names_the_guide_tells_the_operator_to_open_are_the_real_ones(self):
        for file in ("telegram-test.yml", "ai-request.yml", "operator-reply.yml", "blogger-en.yml", "blogger-ko.yml"):
            self.assertIn(f"`{load(file)['name']}`", self.guide, file)

    def test_the_input_name_for_the_auth_check_is_a_real_workflow_input(self):
        for file in ("blogger-en.yml", "blogger-ko.yml"):                               # 공용 blogger.yml 은 workflow_call 이라 운영자가 직접 누르지 않는다
            inputs = load(file)["on"]["workflow_dispatch"]["inputs"]
            self.assertIn("auth_check", inputs, file)
        self.assertIn("`auth_check`", self.guide)

    def test_the_guide_links_resolve_and_say_where_the_details_live(self):
        self.assertEqual([f.line() for f in vr.check_doc_links(ROOT, [ol.GUIDE_PATH, ol.REQUEST_DIR + "/README.md"])], [])
        for needle in ("PR_병합_방법.md", "SECURITY_GUARDRAILS.md", "TELEGRAM_SETUP.md", "ACTIONS_GUIDE.md", "ARCHITECTURE.md"):
            self.assertIn(needle, self.guide, needle)

    def test_the_guide_never_asks_for_a_secret_value_and_holds_no_secret_shaped_text(self):
        self.assertIn("**비밀번호·토큰·키 값은 절대 쓰지 마세요**", self.guide)
        self.assertEqual([f.line() for f in vr.check_secret_patterns(ROOT, [ol.GUIDE_PATH, ol.REQUEST_DIR + "/README.md"])], [])

    def test_the_guide_has_no_template_braces_that_the_site_builder_would_eat(self):
        for text in (self.guide, text_of(FOLDER_README)):
            self.assertNotIn("{{", text)
            self.assertNotIn("{%", text)


class FolderReadmeMatchesCodeTest(unittest.TestCase):
    """요청함 폴더의 README(AI 용 작성 규칙)가 파서·검증기와 같은 규칙을 말하는지."""

    def setUp(self):
        self.readme = text_of(FOLDER_README)
        self.rows = table_rows(self.readme, "키")

    def test_the_front_matter_table_lists_exactly_the_keys_the_parser_reads(self):
        self.assertEqual([row[0].strip("`") for row in self.rows], list(ol.REQUEST_KEYS))

    def test_the_keys_it_calls_required_are_the_keys_the_parser_requires(self):
        marked = {row[0].strip("`") for row in self.rows if row[1] == "필수"}
        needed = set()
        for key in ol.REQUEST_KEYS:
            fields = {"id": "R-001", "kind": "merge", "title": "t", "summary": "s"}
            fields.pop(key, None)
            text = "---\n" + "\n".join(f"{name}: {value}" for name, value in fields.items()) + "\n---\n"
            try:
                ol.parse_request("R-001_x.md", text, strict=True)
            except ol.RequestError:
                needed.add(key)
        self.assertEqual(marked, needed)
        self.assertEqual(marked, {"id", "kind", "title", "summary"})

    def test_the_limits_it_states_are_the_codes(self):
        text = self.readme
        for number, unit in ((ol.TITLE_MAX, "자"), (ol.SUMMARY_MAX, "자"), (ol.SLUG_MAX, "자"), (ol.MAX_FRONT_LINES, "줄"), (ol.MAX_REQUEST_MESSAGES, "통")):
            self.assertIn(f"{number}{unit}", text, (number, unit))
        title_row = next(row for row in self.rows if row[0] == "`title`")
        summary_row = next(row for row in self.rows if row[0] == "`summary`")
        self.assertIn(f"{ol.TITLE_MAX}자 이하", title_row[2])
        self.assertIn(f"{ol.SUMMARY_MAX}자 이하", summary_row[2])

    def test_the_kinds_and_urgencies_it_lists_are_the_codes(self):
        kind_row = next(row for row in self.rows if row[0] == "`kind`")
        for kind, label in notify.REQUEST_KIND_LABELS.items():
            self.assertIn(f"`{kind}`({label})", kind_row[2])
        urgency_row = next(row for row in self.rows if row[0] == "`urgency`")
        for value in ol.URGENCIES:
            self.assertIn(f"`{value}`", urgency_row[2])
        self.assertIn(f"{notify.SIREN_MARK} 급함", urgency_row[2])

    def test_the_file_name_rule_it_states_is_the_codes(self):
        self.assertIn("`R-<세 자리 번호>_<영문 소문자·숫자·하이픈 슬러그>.md`", self.readme)
        for name, ok in (("R-001_merge-pr57.md", True), ("R-001_Merge.md", False), ("R-1_x.md", False), ("R-001_a_b.md", False)):
            self.assertEqual(bool(ol.REQUEST_NAME_RE.fullmatch(name)), ok, name)
        self.assertIn("R-001_merge-pr57.md", self.readme)

    def test_the_example_in_the_readme_is_a_valid_request_file(self):
        match = re.search(r"```markdown\n(---\n.*?\n---\n.*?)```", self.readme, re.S)
        self.assertIsNotNone(match, "README 에 요청 파일 예시 코드 상자가 없습니다")
        example = match.group(1)
        request = ol.parse_request("R-001_merge-pr57.md", example, strict=True)
        self.assertEqual((request.id, request.kind, request.urgency, request.pr, request.created), ("R-001", "merge", "보통", 59, "2026-10-28"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ol.REQUEST_DIR / "R-001_merge-pr57.md"
            path.parent.mkdir(parents=True)
            path.write_text(example, encoding="utf-8", newline="\n")
            self.assertEqual(vr.check_request_files(Path(tmp), [ol.REQUEST_DIR + "/R-001_merge-pr57.md"]), [])
        message = notify.format_ai_request(request.id, request.kind, request.title, request.summary, request.urgency, request.pr)
        self.assertIn("AI 요청 R-001 · 병합 부탁", message)

    def test_the_readme_itself_is_not_a_request_file_so_it_never_triggers_an_alert(self):
        self.assertIsNone(ol.REQUEST_NAME_RE.fullmatch("README.md"))
        self.assertEqual(vr.check_request_files(ROOT, vr.list_files(ROOT)), [])
        self.assertEqual(ol.new_request_names(ROOT, oh.SHA_A, oh.SHA_B, "main", "ai/claude/x", runner=oh.RequestGit(tree=[ol.REQUEST_DIR + "/README.md"])), [])

    def test_the_numbers_of_requests_in_the_repository_are_unique(self):
        names = sorted(path.name for path in (ROOT / ol.REQUEST_DIR).glob("R-*.md"))
        numbers = [name.split("_", 1)[0] for name in names]
        self.assertEqual(len(numbers), len(set(numbers)))

    def test_the_trust_rule_it_gives_the_ai_is_the_validated_one(self):
        for needle in ("`user.login`", "`author_association`", "`OWNER`", "### 요청 번호", "그 요청 파일에 적힌 항목에 한해서만"):
            self.assertIn(needle, self.readme, needle)
        self.assertIn(f"labels={ol.LABEL_REPLY}", self.readme)
        self.assertIn(f"labels={ol.LABEL_TASK}", self.readme)
        self.assertIn(ol.REPLY_TITLE_PREFIX.strip(), self.readme)
        self.assertIn(ol.TASK_TITLE_PREFIX.strip(), self.readme)


class OtherDocsAgreeTest(unittest.TestCase):
    """여러 문서에 흩어진 같은 사실(이름·규칙 번호·경로)이 서로·코드와 어긋나지 않는지."""

    WORKFLOW_DOCS = ("docs/ACTIONS_GUIDE.md", "docs/ARCHITECTURE.md", "HANDLER.md", ".github/editorial/TELEGRAM_SETUP.md")

    def test_the_workflow_names_in_the_docs_are_the_workflows_current_names(self):
        for file in ("ai-request.yml", "operator-reply.yml"):
            name = load(file)["name"]
            for rel in self.WORKFLOW_DOCS:
                text = rel_text(rel)
                if file in text:
                    self.assertIn(f"`{name}`", text, (rel, file))

    def test_the_actions_guide_documents_both_workflows_in_its_table_and_its_how_to_sections(self):
        guide = rel_text("docs/ACTIONS_GUIDE.md")
        for file in ("ai-request.yml", "operator-reply.yml"):
            self.assertIn(f"`{file}`", guide, file)
            self.assertIn(f"`{load(file)['name']}`", guide, file)
        for heading in ("### 3-20. AI 의 요청을 받고 답하는 법", "### 6-15. `[공통] AI 요청 텔레그램 알림` (`ai-request.yml`)", "### 6-16. `[공통] 운영자 응답 접수` (`operator-reply.yml`)"):
            self.assertIn(heading, guide, heading)

    def test_the_architecture_doc_states_the_triggers_the_workflows_really_have(self):
        architecture = rel_text("docs/ARCHITECTURE.md")
        section = architecture[architecture.index("## 4-6."):]
        section = section[:section.index("\n## ", 5)] if "\n## " in section[5:] else section
        self.assertIn("`push` + `branches: ['ai/claude/**']`", section)
        self.assertEqual(load("ai-request.yml")["on"], {"push": {"branches": ["ai/claude/**"]}})
        self.assertIn("`issues: [opened]`", section)
        self.assertEqual(load("operator-reply.yml")["on"], {"issues": {"types": ["opened"]}})
        self.assertIn("경로 필터 없음", section)
        for path in (".github/workflows/ai-request.yml", ".github/workflows/operator-reply.yml", "pipeline/operator_loop.py"):
            self.assertIn(path, section, path)

    def test_the_guardrail_rules_the_validator_cites_exist_in_the_security_doc(self):
        security = rel_text("docs/SECURITY_GUARDRAILS.md")
        for rule in ("G-S9", "G-C13", "WF-14", "REQ-1", "FORM-1"):
            self.assertIn(f"| {rule} |", security, rule)
        source = text_of(ROOT / "scripts" / "validate_repo.py")
        for rule in ("WF-14", "REQ-1", "FORM-1"):
            self.assertIn(f'"{rule}"', source, rule)
        for rule in ("G-S9", "G-C13"):
            self.assertEqual(len([line for line in security.splitlines() if line.startswith(f"| {rule} |")]), 1, rule)    # 규칙 표의 행은 하나(검증기 표의 '규칙 번호' 칸에는 또 나온다)

    def test_the_trust_rule_text_names_exactly_the_checks_the_code_and_workflow_make(self):
        security = rel_text("docs/SECURITY_GUARDRAILS.md")
        row = next(line for line in security.splitlines() if line.startswith("| G-S9 |"))
        for needle in ("issue.user.login", "author_association", "OWNER"):
            self.assertIn(needle, row, needle)
        self.assertIn("github.event.issue.user.login == github.repository_owner", load("operator-reply.yml")["jobs"]["ack"]["if"])
        row = next(line for line in security.splitlines() if line.startswith("| G-C13 |"))
        for needle in ("pull_request_target", "issue_comment", "workflow_run", "ai/claude/**", "github.sha"):
            self.assertIn(needle, row, needle)

    def test_the_defect_register_entries_point_at_what_was_built(self):
        register = rel_text("docs/DEFECT_REGISTER.md")
        for number, needles in (("D-78", ("operator_loop", "ai-request.yml", "operator-reply.yml")), ("D-79", ("clean_secret",))):
            row = next(line for line in register.splitlines() if line.startswith(f"| **{number}** |"))
            for needle in needles:
                self.assertIn(needle, row, (number, needle))

    def test_every_agent_instruction_file_points_to_the_request_channel(self):
        for rel in ("AGENTS.md", "HANDLER.md", ".github/copilot-instructions.md", "CLAUDE.md", "GEMINI.md"):
            text = rel_text(rel)
            self.assertTrue("요청함" in text or "[답변]" in text, rel)
        for rel in ("CLAUDE.md", "GEMINI.md"):
            text = rel_text(rel)
            self.assertIn("G-S9", text, rel)
            self.assertEqual(text.count("`[답변]`·`[요청]`"), 1, rel)
        self.assertIn("인수인계/요청함/", rel_text("AGENTS.md"))
        self.assertIn("운영자_요청함_사용법.md", rel_text("HANDLER.md"))

    def test_the_approval_rule_is_stated_with_the_same_two_limits_everywhere(self):
        """승인 예외의 두 제한(요청 번호 일치·그 요청에 적힌 항목에 한함)이 정책 문서마다 빠지지 않는다."""
        for rel in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "docs/CHARTER.md", "인수인계/작업요청/README.md"):
            text = rel_text(rel)
            self.assertIn("요청 번호", text, rel)
            self.assertRegex(text, r"그 요청에 적힌 항목에 한|요청에 적힌 항목에 한|적힌 항목에 한", rel)

    def test_the_engineering_guide_rule_names_the_validator_rules_that_enforce_it(self):
        row = next(line for line in rel_text("docs/ENGINEERING_GUIDE.md").splitlines() if line.startswith("| W11 |"))
        for rule in ("WF-14", "REQ-1", "FORM-1"):
            self.assertIn(rule, row, rule)
        self.assertEqual(len([line for line in rel_text("docs/ENGINEERING_GUIDE.md").splitlines() if line.startswith("| W11 |")]), 1)

    def test_the_telegram_setup_doc_lists_the_two_new_messages(self):
        text = rel_text(".github/editorial/TELEGRAM_SETUP.md")
        self.assertIn(f"`{notify.BELL_MARK} AI 요청 R-001 · 병합 부탁`", text)
        self.assertIn(f"`{notify.OK_MARK} 답변 접수 R-001 → 승인(이슈 #12)`", text)
        self.assertIn(notify.format_reply_received("R-001", "승인", 12), text)

    def test_the_merge_howto_points_to_the_guide_and_says_to_report_back(self):
        text = rel_text("인수인계/PR_병합_방법.md")
        self.assertIn("운영자_요청함_사용법.md", text)
        self.assertIn("했어요", text)
        self.assertTrue((ROOT / "인수인계" / "운영자_요청함_사용법.md").is_file())

    def test_the_new_documents_are_listed_in_the_handover_signposts(self):
        handler = rel_text("HANDLER.md")
        self.assertIn("인수인계/요청함/README.md", handler)
        self.assertIn("인수인계/운영자_요청함_사용법.md", handler)
        self.assertIn("docs/ARCHITECTURE.md` §4-6", handler)

    def test_the_documents_that_the_site_publishes_are_not_changed(self):
        """광고·사이트 표면을 건드리지 않는다: 이 기능이 고친 파일 중 사이트 설정·첫 화면은 없다."""
        for rel in ("index.html", "_config.yml"):
            self.assertNotIn("요청함", rel_text(rel), rel)


if __name__ == "__main__":
    unittest.main()
