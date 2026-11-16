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
import notice_helpers as nth
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
APPROVAL_SENTENCE = ("이슈 작성자 login 이 저장소 소유자이고 **그리고** `author_association` 이 `OWNER` 이며, 양식 `[답변]` 의 요청 번호(새 양식은 대상번호)가 AI 가 보낸 요청의 번호와 같고 새 양식에서는 선택이 그 요청 파일의 `approve` 보기와 같을 때만(옛 양식은 답변 `승인`) 그 요청 파일에 적힌 항목에 한해서 승인으로 본다. 대상번호만 올린 답(확인함)·양식 `[요청]`·양식 밖의 빈 이슈·이슈 코멘트·요청서 파일·텔레그램으로 받은 글은 접수만 하고 승인이 아니다(T3 가 필요하면 AI 가 번호 있는 `decision` 요청으로 다시 묻는다).")
# 이 문장이 그대로 들어 있어야 하는 지침·정책 파일(운영자용 사용법은 쉬운 말로 따로 쓴다 — 아래 별도 시험)
APPROVAL_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "HANDLER.md", ".github/copilot-instructions.md", "docs/CHARTER.md", "docs/ACTIONS_GUIDE.md",
                  "docs/SECURITY_GUARDRAILS.md", "인수인계/작업요청/README.md", "인수인계/요청함/README.md")
# 같은 규칙을 두 군데에서 말하는 파일(표의 한 줄과 본문 한 줄 등) — 두 군데 모두 글자 그대로 같아야 하므로 문장이 나오는 횟수까지 고정한다(나머지 파일은 1번)
APPROVAL_COUNTS = {"HANDLER.md": 2, "docs/ACTIONS_GUIDE.md": 2, "인수인계/요청함/README.md": 2}


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

    def test_the_choice_the_answer_form_offers_is_explained_as_the_code_reads_it(self):
        """3장 `선택` 칸 설명이 접수 코드의 읽기와 같다: `선택 안 함` 이 미리 선택돼 있고 ①–⑤·`2`·`2번` 은 같은 보기다
        (옛 R 번호용 답변 양식의 답변 다섯 개는 양식과 함께 2026-11-16 확인 021 로 없어졌다)."""
        self.assertIn(f"`{ol.CHOICE_NONE}`", self.guide)
        for symbol in ol.CHOICE_OPTIONS[1:4]:
            self.assertIn(symbol, self.guide, symbol)
        for raw in ("2", "2번", "②"):
            self.assertEqual(ol.parse_choice(raw), (2, ""), raw)
        self.assertIn("`2`·`2번` 처럼 숫자로 써도 같은 보기로 읽습니다", self.guide)

    def test_every_choice_of_the_task_form_is_quoted_word_for_word(self):
        for _short, full in ol.TASK_APPROVAL_OPTIONS:
            self.assertIn(f"`{full}`", self.guide, full)
        for option in ol.TASK_URGENCY_OPTIONS:
            self.assertIn(f"`{option}`", self.guide, option)

    def test_the_guide_names_both_forms_exactly_as_the_menu_shows_them_and_never_sends_the_operator_to_the_deleted_one(self):
        for file in ("ai-answer.yml", "ai-task.yml"):
            self.assertIn(f"`{form_name(file)}`", self.guide, file)
        self.assertFalse((TEMPLATES / "ai-reply.yml").exists())                    # 옛 R 번호용 답변 양식은 2026-11-16 확인 021 로 없앴다
        for stale in ("AI 요청에 답하기(결정·확인)", "이전 R 번호용"):                  # 없는 메뉴로 운영자를 보내지 않는다
            self.assertNotIn(stale, self.guide, stale)

    def test_the_field_names_the_guide_tells_the_operator_to_fill_are_the_forms_labels(self):
        for label in ("대상번호", "선택", "내용"):
            self.assertIn(f"**{label}**", self.guide, label)
            self.assertIn(label, dict(ol.ANSWER_FIELDS).values())
        for label in ("해 주었으면 하는 일", "끝났다고 볼 기준", "긴급도", "진행 범위"):
            self.assertIn(label, self.guide, label)
            self.assertIn(label, dict(ol.TASK_FIELDS).values())

    def test_the_kind_table_lists_every_label_the_telegram_message_can_show(self):
        rows = table_rows(self.guide, "종류")
        self.assertEqual([row[0] for row in rows], [notify.REQUEST_KIND_LABELS[kind] for kind in ("merge", "run", "confirm", "decision", "info", "merged")])
        self.assertEqual(set(row[0] for row in rows), set(notify.REQUEST_KIND_LABELS.values()))

    def test_the_guide_step_for_the_target_number_keeps_the_short_form_and_the_dropped_digit_warning(self):
        """B-5(검증 B)·A-4(검증 A): 사용법 3장 4번의 '대상번호' 줄 하나가 `19` 로 써도 된다는 말·숫자를 하나 빠뜨리면 다른 번호로 읽힐 수 있다는 정직한 경고·번호가 아닌 것의 목록을 **그 줄 안에서** 말한다 —
        5행(한 줄 요약)에 같은 문장이 있어도 이 줄이 옛 세 자리 안내로 되돌아가면 빨개진다."""
        lines = [line for line in self.guide.splitlines() if line.lstrip().startswith("- **대상번호**(필수):")]
        self.assertEqual(len(lines), 1, lines)
        line = lines[0]
        for needle in ("`019` 처럼 텔레그램의 숫자를 쓰고 **번호 하나만** 씁니다", "`19` 처럼 앞의 0 을 빼고 써도 `019` 로 읽습니다(`1` 은 `001`, `135` 는 `135`, `1000` 이상은 그대로)",
                       "숫자를 하나 빠뜨리면(예: `122` 를 `22` 로) 다른 요청의 번호 `022` 로 읽혀 접수될 수 있습니다", "승인이 되려면 선택도 그 요청의 승인 보기와 같아야 하고",
                       "접수 답글이 `읽었습니다` 로 읽은 번호를 알려 주지만", "접수 답글에 적힌 읽은 번호가 쓰신 번호와 같은지 한 번 봐 주세요", "`0`·`000`·앞에 0 이 더 붙은 `0019`·`P012`·`M007`"):
            self.assertIn(needle, line, needle)
        for old in ("숫자 3자리", "세 자리로만", "세 자리로 쓰세요", "세 자리 숫자", "그대로 쓰세요"):
            self.assertNotIn(old, line, old)

    def test_the_kinds_that_need_an_answer_are_the_ones_the_guide_says_get_the_how_to_answer_line(self):
        for kind in notify.REQUEST_ANSWER_KINDS:
            self.assertIn(notify.REQUEST_KIND_LABELS[kind], self.guide)
        self.assertIn("`결정 부탁`·`확인 부탁` 메시지에는", self.guide)
        self.assertEqual(sorted(notify.REQUEST_ANSWER_KINDS), ["confirm", "decision"])

    def test_the_telegram_messages_quoted_in_the_guide_are_what_the_code_sends(self):
        head = re.sub(r"</?b>", "", notify.format_ai_request("R-001", "merge", "제목", "요약")).splitlines()[0]
        self.assertEqual(head, f"{notify.BELL_MARK} AI 요청 r001 · 병합 부탁")
        self.assertIn(head, self.guide)
        urgent = re.sub(r"</?b>", "", notify.format_ai_request("R-001", "merge", "제목", "요약", urgency="급함")).splitlines()[0]
        self.assertTrue(urgent.endswith(f"{notify.SIREN_MARK} 급함"))
        self.assertIn(f"`{notify.SIREN_MARK} 급함`", self.guide)
        asking = notify.format_ai_request("R-001", "decision", "제목", "요약")
        self.assertIn("답하는 법: 아래 [답하기] → 양식의 대상번호에 r001 (옛 번호 요청은 접수만 됩니다 — 승인은 AI 가 새 번호로 다시 묻습니다)", asking)
        self.assertIn("`답하는 법: 아래 [답하기] → 양식의 대상번호에 r001 (옛 번호 요청은 접수만 됩니다 — 승인은 AI 가 새 번호로 다시 묻습니다)`", self.guide)
        received = notify.format_answer_received("003", 2, 12)
        self.assertEqual(received, f"{notify.OK_MARK} 답변 접수 003 → 선택 ②(이슈 #12)")
        self.assertIn(received.replace("#12", "#N"), self.guide)
        short = notify.format_answer_received("019", 0, 12)                           # 짧게 써서 정규화된 번호도 읽은 번호(019)로 적힌다 — 확인함 문구까지 사용법과 같다
        self.assertIn(f"{notify.OK_MARK} 답변 접수 019 → 확인함 — 승인 아님", short)
        self.assertIn("→ 확인함 — 승인 아님", self.guide)
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
        for phrase in ("접수했습니다 — 요청", "접수했습니다 — 확인 요청", "접수했습니다 — 새 일 요청", "양식 모양이 달라 처리하지 못했습니다", "은 AI 가 자기가 보낸 요청과 대조해 처리합니다",
                       "이 번호가 AI 가 보낸 요청의 번호와 맞는지는 이 접수가 알 수 없습니다", "AI 요청 알림: {request.id} 을 알렸습니다"):
            self.assertIn(phrase, source, phrase)
        for phrase in ("접수했습니다 — 확인 요청", "접수했습니다 — 새 일 요청", "양식 모양이 달라 처리하지 못했습니다", "이 번호가 AI 가 보낸 요청의 번호와 맞는지는 이 접수가 알 수 없습니다",
                       "AI 요청 알림: R-… 을 알렸습니다", "다른 브랜치에도 있어 알리지 않은 요청 파일"):
            self.assertIn(phrase, self.guide, phrase)
        self.assertIn("다른 브랜치에도 있어 알리지 않은 요청 파일", ol.REQUESTS_SKIPPED_LINE)

    def test_the_neutral_number_sentences_are_the_same_in_the_code_and_in_every_document_that_quotes_them(self):
        """'알 수 없는 요청 번호 … 다시 확인하세요' 대신 중립 사실 진술(독립 검증 N-2). 옛 형식 이슈의 한 줄(접수 코드가 아직 읽는다)은 운영·구조 문서에,
        새 양식의 한 줄(`NUMBER_CHECK_NOTE`)은 사용법에 같은 말로 있다(옛 R 번호용 양식을 없앤 2026-11-16 이후)."""
        sub = ol.Submission("reply", "R-007", "승인", "", False, 0, "", False)
        comment = ol.reply_comment(sub, False)
        sentence = "요청 번호 r007 은 AI 가 자기가 보낸 요청과 대조해 처리합니다"
        self.assertIn(sentence + "(요청 파일이 병합 전 브랜치에만 있으면 이 저장소 기본 브랜치에서는 보이지 않으며 정상일 수 있습니다).", comment)
        for text in (rel_text("docs/ACTIONS_GUIDE.md"), rel_text("docs/ARCHITECTURE.md")):
            self.assertIn(sentence, text)
        note = ol.NUMBER_CHECK_NOTE
        for phrase in ("맞는지는 이 접수가 알 수 없습니다", "AI 가 이슈를 읽을 때 대조하고", "번호가 틀렸으면 폰으로 알립니다"):
            self.assertIn(phrase, note, phrase)
            self.assertIn(phrase, self.guide, phrase)
        for alarming in ("알 수 없는", "다시 확인하세요"):
            self.assertNotIn(alarming, comment)
            self.assertNotIn(alarming, note)
            self.assertNotIn(alarming, self.guide)

    def test_the_guide_says_the_safe_choice_is_preselected_and_a_target_only_answer_is_not_an_approval(self):
        """`선택` 드롭다운은 안전한 `선택 안 함` 이 첫째이고 미리 선택돼 있다 — 사용법도 '그대로 올리면 확인함(승인 아님)' 이라고 말한다(독립 검증 N-3 의 새 양식 판)."""
        form = yaml.safe_load(text_of(TEMPLATES / "ai-answer.yml"))
        choice = {item["id"]: item for item in form["body"][1:]}["choice"]["attributes"]
        self.assertEqual((choice["default"], choice["options"][choice["default"]]), (ol.CHOICE_DEFAULT_INDEX, ol.CHOICE_NONE))
        self.assertEqual(ol.CHOICE_OPTIONS[ol.CHOICE_DEFAULT_INDEX], "선택 안 함")
        self.assertIn("미리 `선택 안 함` 이 골라져 있고, 그대로 올리면 **확인함**(읽었다는 표시)입니다", self.guide)
        self.assertIn("**대상번호만 올린 답은 '확인함'이고 승인이 아닙니다.**", self.guide)

    def test_the_guide_says_the_task_form_is_not_a_t3_approval_and_t3_goes_through_a_numbered_request(self):
        for needle in ("**T3 승인이 아닙니다**", "번호 있는 `결정 부탁`(`r001` 같은 번호)으로 따로 묻고", ol.TASK_FORM_NUMBERED_ASK, "**진행 범위**(필수)", "`[요청]`"):
            self.assertIn(needle, self.guide, needle)
        self.assertNotIn("T3 포함", self.guide)
        self.assertIn(ol.TASK_FORM_NOT_T3.replace("이 양식은 ", ""), self.guide)

    def test_the_guide_tells_the_operator_to_report_a_receipt_they_did_not_make(self):
        """AI 가 소유자 명의로 이슈를 만들어 승인하는 길은 규칙과 탐지에 기댄다(독립 검증 N-4)."""
        self.assertIn("내가 올리지 않았는데 텔레그램에 `✅ 답변 접수` 가 오거나", self.guide)
        self.assertIn("**바로 알리세요**", self.guide)

    def test_the_branch_name_rule_the_docs_state_is_the_codes(self):
        """알림이 가는 브랜치 이름: `ai/claude/` 뒤에 영문·숫자·`.`·`_`·`-` 조각(독립 검증 N-8)."""
        for name, ok in (("ai/claude/a.b_c-d", True), ("ai/claude/x/y", True), ("ai/claude/한글", False), ("ai/claude/a+b", False), ("ai/claude/a@b", False),
                         ("ai/claude/a#b", False), ("ai/claude/a b", False)):
            self.assertEqual(ol.valid_branch(name, "ai/claude/"), ok, name)
        for text in (self.guide, text_of(FOLDER_README), rel_text("docs/ACTIONS_GUIDE.md"), rel_text("docs/ARCHITECTURE.md"), rel_text(".github/workflows/ai-request.yml")):
            self.assertIn("영문·숫자·`.`·`_`·`-`", text)
        for text in (self.guide, text_of(FOLDER_README)):                                     # 운영자·AI 가 읽는 두 안내는 `/` 로 이어도 된다는 것과 안 되는 글자의 예도 말한다(위 시험의 거짓 예와 같은 글자)
            self.assertIn("`/` 로 이어도 ", text)
            self.assertIn("한글·`+`·`@`·`#`", text)

    def test_the_acknowledgement_example_matches_what_the_code_writes(self):
        title = ol.REPLY_TITLE_PREFIX + "x"
        sub = ol.parse_reply(title, nth.answer_body("003", "②", crlf=False), oh.OWNER, "OWNER", oh.OWNER)
        comment = ol.answer_comment(sub)
        self.assertIn("접수했습니다 — 확인 요청 **003** · 선택: **②**", comment)
        self.assertIn("`접수했습니다 — 확인 요청 003 · 선택: ②`", self.guide)
        self.assertNotIn("읽었습니다", comment)                                        # 표준 모양(세 자리)으로 쓴 번호에는 '읽었습니다' 줄이 붙지 않는다
        short = ol.parse_reply(title, nth.answer_body("19", "②", crlf=False), oh.OWNER, "OWNER", oh.OWNER)
        self.assertEqual((short.kind, short.target), ("answer", "019"))
        said = "입력한 대상번호를 019 로 읽었습니다(앞의 0 은 자리 채움입니다)"
        self.assertIn(said, ol.answer_comment(short).replace("**", ""))                # 짧게 쓴 번호는 코멘트가 읽은 번호를 알린다(확인 022)
        self.assertIn(f"`{said}`", self.guide)

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
        self.assertIn("AI 요청 r001 · 병합 부탁", message)

    def test_the_readme_itself_is_not_a_request_file_so_it_never_triggers_an_alert(self):
        self.assertIsNone(ol.REQUEST_NAME_RE.fullmatch("README.md"))
        self.assertEqual(vr.check_request_files(ROOT, vr.list_files(ROOT)), [])
        self.assertEqual(ol.new_request_names(ROOT, oh.SHA_A, oh.SHA_B, "main", "ai/claude/x", runner=oh.RequestGit(tree=[ol.REQUEST_DIR + "/README.md"])), [])

    def test_the_numbers_of_requests_in_the_repository_are_unique(self):
        names = sorted(path.name for path in (ROOT / ol.REQUEST_DIR).glob("R-*.md"))
        numbers = [name.split("_", 1)[0] for name in names]
        self.assertEqual(len(numbers), len(set(numbers)))

    def test_the_trust_rule_it_gives_the_ai_is_the_validated_one(self):
        for needle in ("`author_association`", "`OWNER`", "그 요청 파일에 적힌 항목에 한해서", APPROVAL_SENTENCE):
            self.assertIn(needle, self.readme, needle)
        self.assertIn(f"labels={ol.LABEL_REPLY}", self.readme)
        self.assertIn(f"labels={ol.LABEL_TASK}", self.readme)
        self.assertIn(ol.REPLY_TITLE_PREFIX.strip(), self.readme)
        self.assertIn(ol.TASK_TITLE_PREFIX.strip(), self.readme)

    def test_the_readme_tells_the_ai_to_filter_by_creator_and_not_to_trust_the_labels(self):
        """양식 라벨은 낯선 사람의 이슈에도 붙을 수 있다 — 신뢰 신호가 아니고, REST 로 읽을 때는 `creator=<소유자>` 필터를 건다(독립 검증 N-5)."""
        self.assertIn(f"issues?creator={oh.OWNER}&labels={ol.LABEL_REPLY}&state=open", self.readme)
        self.assertIn("`creator=<소유자>` 필터", self.readme)
        self.assertIn("양식 라벨은 낯선 사람이 연 이슈에도 붙을 수 있어 신뢰 신호가 아닙니다", self.readme)
        self.assertIn("자기 자격증명(push 용 토큰 포함)으로 이슈·코멘트를 쓰지도 않습니다", self.readme)

    def test_the_readme_tells_the_ai_not_to_push_branches_that_carry_the_same_new_request_together(self):
        """같은 요청 커밋을 든 두 브랜치를 한꺼번에 push 하면 둘 다 서로가 가졌다고 보고 아무도 알리지 않는다 — 문서에 한계로 적고 로그 줄을 알려 준다(독립 검증 N-1)."""
        self.assertIn("동시에 push 하지 말고", self.readme)
        self.assertIn("git push origin A B", self.readme)
        self.assertIn(ol.REQUESTS_SKIPPED_LINE.format(ids="R-001").split("AI 요청 알림: ", 1)[1], self.readme.replace("`", ""))
        self.assertIn("main 을 합치거나 이미 알린 브랜치에서 새 브랜치를 만든 평범한 push 에도 남습니다", self.readme)          # 평범한 push 에도 같은 줄이 남는다고 미리 알려 놀라지 않게
        self.assertIn("다른 브랜치에도 있어 알리지 않은 요청 파일", rel_text("docs/ARCHITECTURE.md"))


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
        self.assertIn("인수인계/요청함/", rel_text("AGENTS.md"))
        self.assertIn("운영자_요청함_사용법.md", rel_text("HANDLER.md"))

    def test_every_policy_file_states_the_approval_rule_with_the_same_sentence(self):
        """승인 규칙(G-S9)의 한 문장이 모든 지침·정책 파일에 글자 그대로 같다 — 작성자 login 과 `author_association` 둘 다·요청 번호 일치·그 요청 파일에 적힌 항목에 한함·
        `[요청]`·양식 밖 이슈·코멘트·요청서 파일은 접수만(독립 검증 B-1·N-5: 파일마다 다른 요약이 `[요청]` 을 승인처럼 읽히게 했다)."""
        for rel in APPROVAL_FILES:
            text = rel_text(rel)
            self.assertIn(APPROVAL_SENTENCE, text, rel)
            self.assertEqual(text.count(APPROVAL_SENTENCE), APPROVAL_COUNTS.get(rel, 1), rel)      # 한 곳만 고쳐 모순되는 요약이 남는 것을 막는다
        for needle in ("**그리고**", "`author_association`", "`OWNER`", "`[답변]`", "요청 번호", "그 요청 파일에 적힌 항목에 한해서", "`[요청]`", "접수만 하고 승인이 아니다", "`decision`",
                       "대상번호", "`approve`", "대상번호만 올린 답(확인함)", "텔레그램으로 받은 글"):          # TG-STD: 새 양식의 승인 조건과 '확인함·텔레그램 글은 승인 아님'
            self.assertIn(needle, APPROVAL_SENTENCE, needle)

    def test_the_approval_sentence_is_what_the_code_does_with_each_form(self):
        """문장의 조건이 접수 코드의 동작과 같다: `[답변]` 만 요청 번호와 답을 담고, `[요청]` 은 번호도 답도 담지 않아 승인으로 읽을 수가 없다."""
        answer = ol.parse_reply("[답변] ", oh.reply_body(request_id="R-007", answer="승인"), oh.OWNER, "OWNER", oh.OWNER)
        self.assertEqual((answer.kind, answer.request_id, answer.answer), ("reply", "R-007", "승인"))
        task = ol.parse_reply("[요청] ", oh.task_body(approval=oh.TASK_SCOPE["yes"]), oh.OWNER, "OWNER", oh.OWNER)
        self.assertEqual((task.kind, task.request_id, task.answer), ("task", "", ""))
        for login, association in ((oh.OWNER, "MEMBER"), ("stranger", "OWNER"), ("stranger", "NONE")):
            self.assertIsInstance(ol.parse_reply("[답변] ", oh.reply_body(), login, association, oh.OWNER), ol.Refusal, (login, association))

    def test_the_short_target_rule_the_documents_state_is_what_the_code_does(self):
        """확인 022(2026-11-16): 대상번호는 ASCII 숫자만 읽고 1–3자리는 앞을 0 으로 채워 세 자리로 맞춘다 — 문서가 든 예(`19`→`019`·`1`→`001`)와 거절한다고 한 것(`0`·`000`·`0019`·전각·부호·소수점)이 접수 코드의 읽기와 같고,
        문서마다 그 규칙(정규화한 뒤 견준다)이 있다. 승인 규칙은 그대로다 — 번호만 맞고 선택이 없으면 확인함이다."""
        for raw, expected in (("19", "019"), ("1", "001"), ("019", "019"), ("135", "135"), ("1000", "1000"), (" 19 ", "019")):
            self.assertEqual(ol.parse_target(raw), ("ask", expected, ""), raw)
        for raw in ("0", "00", "000", "0019", "00019", "10000", chr(0xFF11) + chr(0xFF19), "+19", "-19", "19.0", "0x13", "19 20", "P19", "M19"):
            kind, value, problem = ol.parse_target(raw)
            self.assertEqual((kind, value), ("", ""), raw)
            self.assertTrue(problem, raw)
        needles = {
            "AGENTS.md": ("`19` 만 써도 `019` 로 읽어 정규화한 번호로 견준다",),
            "HANDLER.md": ("`19` 만 써도 `019` 로 읽는다",),
            "docs/ACTIONS_GUIDE.md": ("`19` 만 써도 `019` 로 읽습니다", "그렇게 정규화한 번호를 AI 가 보낸 요청의 번호와 견줍니다"),
            "docs/ARCHITECTURE.md": ("`19` 처럼 짧게 써도 앞을 0 으로 채워 `019` 로 읽고(`parse_target`) **그 정규화한 번호**를 요청의 `no` 와 견준다",),
            "docs/SECURITY_GUARDRAILS.md": ("정규화한 번호", "`19` → `019`", "`0019`"),
            "docs/AGENT_RUNBOOK.md": ("`parse_target`", "`19` → `019`", "정규화"),
            "인수인계/요청함/README.md": ("`parse_target`", "`19` → `019`", "정규화한 대상번호"),
            ol.GUIDE_PATH: ("`19` 처럼 앞의 0 을 빼고 써도 `019` 로 읽습니다", "`19` 처럼 짧게 써도 `019` 로 읽은 뒤 견줍니다"),
        }
        for rel, phrases in needles.items():
            text = rel_text(rel)
            for phrase in phrases:
                self.assertIn(phrase, text, (rel, phrase))

    CURRENT_DOCS = ("AGENTS.md", "HANDLER.md", "docs/ACTIONS_GUIDE.md", "docs/REQUEST_BRIEFING.md", "docs/TELEGRAM_INBOX.md", "docs/ISSUE_EDITS.md", "docs/AGENT_RUNBOOK.md",
                    "docs/SECURITY_GUARDRAILS.md", "docs/GLOSSARY.md", "인수인계/요청함/README.md", ol.GUIDE_PATH, "인수인계/PR_병합_방법.md")

    def test_the_documents_no_longer_send_the_operator_to_the_deleted_answer_form(self):
        """확인 021(2026-11-16): 옛 R 번호용 답변 양식의 메뉴 이름·파일 이름은 현행 안내 어디에도 없다(과거 기록인 WORKLOG·작업내용 5장·결함 대장은 제외하고,
        설계 결정 표(ARCHITECTURE)의 TS-10 한 줄만 그 양식의 역사를 말한다)."""
        for rel in self.CURRENT_DOCS:
            text = rel_text(rel)
            for stale in ("AI 요청에 답하기(결정·확인)", "이전 R 번호용", "ai-reply"):
                self.assertNotIn(stale, text, (rel, stale))
        history = [line for line in rel_text("docs/ARCHITECTURE.md").splitlines() if "ai-reply" in line or "이전 R 번호용" in line]
        self.assertEqual([line.split(" | ")[0] for line in history], ["| TS-10"])
        self.assertIn("2026-11-16 확인 021", history[0])
        self.assertFalse((TEMPLATES / "ai-reply.yml").exists())

    # ---- 검증 A-1: AI 가 읽는 문서의 개별 승인 문장·거절 목록 — 승인을 판정하는 코드가 저장소에 없고 AI 가 이 문장을 보고 판단하므로, 같은 줄 안의 문장이 약해지면 빨개져야 한다 ----
    README_READING_PHRASES = (
        "**대상번호만 올린 답은 '확인함' 이고 승인이 아닙니다**",
        "(`pipeline/operator_loop.py` 의 `parse_target`",
        "`0`·`000`·앞에 0 이 더 붙은 `0019`·전각 등 다른 문자의 숫자·부호·소수점·글자 사이의 공백·`P`·`M` 번호·두 번호는 번호가 아닙니다",
        "승인은 **그렇게 정규화한 대상번호**가 **내가 보낸 확인 요청 번호**",
        "`선택` 이 그 요청 파일의 `approve` 보기와 같을 때만, 그 요청 파일에 적힌 항목에 한해서 유효합니다",
        "같은 번호(`19` 와 `019` 도 같은 번호입니다)에 여러 이슈가 오면 **번호가 가장 큰(가장 나중) 이슈의 답이 이깁니다**",
        "옛 R 번호를 새 양식에 쓴 답(`r149`)은 **접수만** 되고 승인이 아닙니다",
        "새 번호의 `decision` 요청으로 다시 묻습니다",
    )
    RUNBOOK_READING_PHRASES = (
        "(`pipeline/operator_loop.py` 의 `parse_target`)으로 읽어 정규화합니다",
        "`0`·`000`·앞에 0 이 더 붙은 `0019`·전각 등 다른 문자의 숫자·부호·소수점·글자 사이의 공백·`P`·`M` 번호·두 번호는 번호가 아닙니다",
        "그렇게 정규화한 번호가 **내가 보낸 확인 요청의 알림 번호**",
        "선택이 그 요청의 `approve` 보기와 같을 때만 승인으로 읽습니다",
        "**대상번호만 올린 답은 '확인함'이고 승인이 아닙니다.**",
        "같은 번호에 여러 이슈가 있으면 번호가 가장 큰 이슈의 답이 이깁니다",
        "새 양식에 쓴 옛 번호 `r149` 는 접수만입니다",
    )
    WEAKENED_READING = ("대상번호만 올린 답은 승인", "대상번호만 올린 답도 승인", "번호가 같으면 승인", "번호만 맞으면 승인", "번호만 같으면 승인", "선택이 없어도 승인", "선택 없이도 승인",
                        "같으면 승인으로 읽습니다", "`0019` 도 같은 번호", "`000` 도 같은 번호", "전각 숫자도 번호", "`r149` 는 승인", "`r149` 도 승인", "숫자 사이의 공백도 번호")

    def test_the_ai_reading_rules_for_the_target_number_are_pinned_sentence_by_sentence(self):
        """README 'AI 읽기' 3번 한 줄과 AGENT_RUNBOOK J2 2번 한 줄: 승인 조건(정규화한 번호 일치 + 선택이 `approve` 보기와 같을 때만 + 그 요청 파일에 적힌 항목에 한해서)·'대상번호만 올린 답은 확인함'·
        '번호가 아닌 것' 목록·옛 R 번호는 접수만·같은 번호는 가장 나중 이슈 — 같은 파일 안의 다른 줄을 바꿔도 이 두 줄의 문장이 약해지면(예: '확인함' → '승인') 여기서 빨개진다."""
        readme = [line for line in rel_text("인수인계/요청함/README.md").splitlines() if line.startswith("3. **새 양식 읽기")]
        runbook = [line for line in rel_text("docs/AGENT_RUNBOOK.md").splitlines() if line.startswith("2. **`[답변]`**:")]
        self.assertEqual((len(readme), len(runbook)), (1, 1))
        for where, line, phrases in (("README 3번", readme[0], self.README_READING_PHRASES), ("AGENT_RUNBOOK J2 2번", runbook[0], self.RUNBOOK_READING_PHRASES)):
            for phrase in phrases:
                self.assertIn(phrase, line, (where, phrase))
            for weakened in self.WEAKENED_READING:
                self.assertNotIn(weakened, line, (where, weakened))

    def test_the_glossary_row_for_the_request_number_teaches_the_target_number_and_not_the_deleted_field(self):
        """검증 B-1: docs/ACTIONS_GUIDE.md 용어집의 '요청함·요청 번호' 행이 '답할 때 양식에 요청 번호를 그대로 쓴다' 고 가르치지 않는다 — 지금은 확인 요청 맨 위의 숫자 대상번호(`19` 로 써도 됨)를 쓰고 선택은 승인 보기 번호를 직접 고른다."""
        rows = [line for line in rel_text("docs/ACTIONS_GUIDE.md").splitlines() if line.startswith("| 요청함·요청 번호 |")]
        self.assertEqual(len(rows), 1)
        for needle in ("옛 텔레그램 메시지에서는 `r001` 꼴", "확인 요청 맨 위의 숫자 **대상번호**(`019` — `19` 로 써도 됩니다)", "선택은 그 요청의 승인 보기 번호를 직접 고릅니다"):
            self.assertIn(needle, rows[0], needle)
        self.assertNotIn("답할 때 양식에 그대로 씁니다", rows[0])

    # ---- 검증 B-5: 현행 문서 목록 밖의 어떤 파일에도 옛 메뉴 이름이 새로 생기지 않는다(저장소 훑기 + 기록 문서 허용 목록) ----
    RECORD_FILES = {
        "WORKLOG.md": "작업 기록 — 지난 항목은 고치지 않는다",
        "인수인계/작업내용.md": "작업 현황·기록 — 5장 날짜 기록·4장 지난 사용자 몫",
        "docs/DEFECT_REGISTER.md": "결함 대장 D-78(옛 양식을 만든 기록)",
        "docs/ARCHITECTURE.md": "설계 결정 TS-10(옛 양식을 두었다가 없앤 기록 한 줄)",
        ".github/workflows/operator-reply.yml": "머리 주석 — 승인 목록(R-370·R-372)에 없어 일부러 안 고친 곳(다음 확인 요청으로 묻는다)",
    }

    def test_the_old_menu_names_appear_in_no_file_but_the_records_and_the_known_leftover(self):
        """확인 021: 옛 R 번호용 답변 양식의 메뉴 이름(`AI 요청에 답하기(결정·확인)`·`이전 R 번호용`)은 저장소 어느 파일에도 새로 생기지 않는다 — 허용 목록(RECORD_FILES)은 과거 기록과 알려 둔 남긴 곳뿐이고
        시험 파일(tests/)과 요청함의 옛 요청 파일(R-nnn)은 그때의 기록이라 훑지 않는다. 허용 목록 밖에서 발견되면 그 파일을 고치거나, 정말 기록이면 이유를 적어 목록에 더한다."""
        stale = ("AI 요청에 답하기(결정·확인)", "이전 R 번호용")
        found = {}
        for rel in vr.list_files(ROOT):
            if rel.startswith("tests/") or rel.startswith("인수인계/요청함/R-"):
                continue
            text = vr.read_text(ROOT, rel)
            if text is None:
                continue
            hits = [needle for needle in stale if needle in text]
            if hits:
                found[rel] = hits
        self.assertLessEqual(set(found), set(self.RECORD_FILES), {rel: hits for rel, hits in found.items() if rel not in self.RECORD_FILES})
        for rel in self.CURRENT_DOCS:
            self.assertNotIn(rel, found, rel)                                  # 현행 안내는 허용 목록과 겹치지 않는다

    def test_the_target_number_is_read_by_one_function_and_the_status_tool_only_prints_the_issue_text(self):
        """문서(README·AGENT_RUNBOOK)는 `scripts/github_status.py` 가 이슈 본문을 그대로 보여 줄 뿐 대상번호를 읽지 않는다고 말하고, 텔레그램 수신은 접수 코드와 같은 함수로 읽는다고 한다 —
        누가 상태 도구에 번호 읽기를 더하면(규칙이 둘이 되면) 이 시험이 알린다: 그때는 같은 함수(`operator_loop.parse_target`)를 쓰게 하고 시험·문서를 함께 고친다."""
        status = text_of(ROOT / "scripts" / "github_status.py")
        for word in ("대상번호", "parse_target", "parse_reply", "operator_loop"):
            self.assertNotIn(word, status, word)
        self.assertIn("loop.parse_target(", text_of(ROOT / "pipeline" / "telegram_inbox.py"))         # 두 번째로 대상번호를 읽는 곳은 접수 코드와 같은 함수를 부른다
        for rel in ("인수인계/요청함/README.md", "docs/AGENT_RUNBOOK.md"):
            self.assertIn("`scripts/github_status.py` 는 이슈 본문을 그대로 보여 줄 뿐 번호를 읽지 않으니", rel_text(rel), rel)

    def test_the_task_requests_readme_rule_for_the_request_form_names_the_scope_choices_and_says_it_is_not_an_approval(self):
        """작업요청 README 규칙 7(양식 `[요청]` 이슈를 어떻게 다루나)은 규칙 3 의 문장과 따로 한 번 더 `[요청]` 은 승인이 아니라고 적고, 진행 범위의 두 선택지(코드의 값)를 말한다."""
        rule = next(line for line in rel_text("인수인계/작업요청/README.md").splitlines() if line.startswith("7. 운영자가 양식"))
        labels = dict(ol.TASK_FIELDS)
        self.assertIn(f"`{labels['approval']}`", rule)
        self.assertIn(f"`{oh.TASK_SCOPE['no']}`", rule)
        self.assertIn(f"`{oh.TASK_SCOPE['yes'].split(' — ')[0]}`", rule)                 # 긴 선택지 글의 앞부분(구현·시험까지 진행(T1·T2))
        for needle in ("**`[요청]` 은 승인이 아니다**", "T3 는 포함하지 않는다", "`decision` 요청(R-번호)으로 다시 묻고", "`[답변]` 으로 승인한다"):
            self.assertIn(needle, rule, needle)
        self.assertNotIn("승인으로 본다", rule)

    def test_no_wording_that_made_the_request_form_look_like_a_t3_approval_remains(self):
        """독립 검증 B-1: `[요청]`·`승인 범위(T3 포함)` 를 승인으로 읽히게 하던 옛 문구가 이 작업이 소유한 파일 어디에도 없다(WORKLOG 의 역사는 제외)."""
        owned = (*APPROVAL_FILES, "docs/ARCHITECTURE.md", "docs/DEFECT_REGISTER.md", "docs/OPS_INBOX.md", "docs/ISSUE_EDITS.md", ".github/editorial/TELEGRAM_SETUP.md",
                 ol.GUIDE_PATH, ".github/ISSUE_TEMPLATE/ai-task.yml", ".github/ISSUE_TEMPLATE/ai-answer.yml", "pipeline/operator_loop.py", "pipeline/notify.py")
        old = ("T3 포함", "`승인 범위`", "### 승인 범위", "알 수 없는 요청 번호", "`[답변]`·`[요청]` 으로 올린 응답", "양식 `[답변]`·`[요청]` —", "(양식 `[답변]`·`[요청]`,", "'예'를 골라도")
        for rel in owned:
            text = rel_text(rel)
            for phrase in old:
                self.assertNotIn(phrase, text, (rel, phrase))

    def test_the_security_row_states_the_request_form_is_not_an_approval_the_credential_rule_and_the_label_rule(self):
        row = next(line for line in rel_text("docs/SECURITY_GUARDRAILS.md").splitlines() if line.startswith("| G-S9 |"))
        for needle in ("`[요청]` 양식은 승인이 아니다", "AI 는 자기 자격증명(push 용 토큰 포함)으로 이슈·코멘트를 쓰지 않는다", "양식 라벨(`운영자응답`·`운영자요청`)은 낯선 사람이 연 이슈에도 붙을 수 있어 신뢰 신호가 아니다",
                       "`creator=<소유자>` 필터", "ASCII 영문 대소문자만 무시"):
            self.assertIn(needle, row, needle)
        self.assertIn("자기 자격증명", rel_text("AGENTS.md"))

    def test_the_path_filter_reason_is_stated_as_the_documents_say_not_as_unverified(self):
        """독립 검증 N-9: 새 브랜치 첫 push 의 경로 필터 평가는 공식 문서로 확인되고, 그래도 필터를 안 쓰는 이유는 안전·단순이다."""
        architecture = rel_text("docs/ARCHITECTURE.md")
        paragraph = next(line for line in architecture.splitlines() if line.startswith("**워크플로를 경로 필터 없이 브랜치만으로 거는 이유**"))
        security = next(line for line in rel_text("docs/SECURITY_GUARDRAILS.md").splitlines() if line.startswith("| G-C13 |"))
        for text in (paragraph, security, rel_text("docs/ACTIONS_GUIDE.md"), rel_text(".github/workflows/ai-request.yml")):
            self.assertIn("두 점 비교", text)
        for text in (paragraph, security):
            self.assertNotIn("미확인", text)
        self.assertNotIn("그 필터가 어떻게 평가되는지 미확인", rel_text("docs/ACTIONS_GUIDE.md"))

    def test_the_post_merge_observations_include_the_checks_the_review_asked_for(self):
        """독립 검증 N-13: 문서로 확인하지 못한 가정을 첫 관측 목록에 넣는다."""
        section = rel_text("docs/ARCHITECTURE.md")
        section = section[section.index("**관측이 필요한 것**(실제 GitHub·텔레그램에서 한 번도 돌려 보지 않았다)"):]
        section = section[:section.index("\n\n")]
        for needle in ("`### 요청 번호`", "`github-actions[bot]` 인지", "`OWNER` 로 오는지", "`before` 가 0 인 경우", "브랜치를 지운 뒤 Actions 목록", "`보류` 를 미리 선택해 보여 주는지"):
            self.assertIn(needle, section, needle)
        register = next(line for line in rel_text("docs/DEFECT_REGISTER.md").splitlines() if line.startswith("| 운영자 요청함(D-78) 병합 직후 |"))
        for needle in ("`github-actions[bot]` 인지", "`before` 가 전부 0 인지", "`OWNER` 로 오는지", "브랜치 삭제 뒤 Actions 목록"):
            self.assertIn(needle, register, needle)

    def test_the_limits_table_names_the_simultaneous_push_the_credential_gap_and_the_preselected_dropdown(self):
        section = rel_text("docs/ARCHITECTURE.md")
        for needle in ("한꺼번에 push 하면 둘 다 '다른 브랜치에도 있다'고 보고 아무도 알리지 못한다", "AI 가 자기 자격증명으로 소유자 명의의 이슈를 만들어 스스로 승인", "기술적으로는 막지 못한다",
                       "`[요청]` 양식을 T3 승인으로 오해", "필수 드롭다운이 첫 선택지를 미리 보여 줘"):
            self.assertIn(needle, section, needle)

    def test_the_engineering_guide_rule_names_the_validator_rules_that_enforce_it(self):
        row = next(line for line in rel_text("docs/ENGINEERING_GUIDE.md").splitlines() if line.startswith("| W11 |"))
        for rule in ("WF-14", "REQ-1", "FORM-1"):
            self.assertIn(rule, row, rule)
        self.assertEqual(len([line for line in rel_text("docs/ENGINEERING_GUIDE.md").splitlines() if line.startswith("| W11 |")]), 1)

    def test_the_telegram_setup_doc_lists_the_two_new_messages(self):
        text = rel_text(".github/editorial/TELEGRAM_SETUP.md")
        self.assertIn(f"`{notify.BELL_MARK} AI 요청 r001 · 병합 부탁`", text)
        self.assertIn(f"`{notify.OK_MARK} 답변 접수 r001 → 승인(이슈 #12)`", text)
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
