"""새 답변 양식(`AI 확인 요청에 답하기(대상번호)` — 대상번호·선택·내용)의 읽기·접수·폰 회신 시험(pipeline/operator_loop.py·telegram_inbox.py·validate_repo.py FORM-1, TG-STD 운영자 승인 2026-11-06 R-165).

핵심: ① 대상번호만 올린 답은 '확인함'이고 **승인이 아니다** ② 번호·선택은 ASCII 숫자·원문자만 읽고 위조(전각·보이지 않는 글자·두 번호·P/M 번호)는 거절 ③ 오류는 폰으로도 회신(소유자 판정을 통과한 새 양식 이슈에만)
④ 이미 답한 번호는 '대체'(가장 나중 답이 이김) ⑤ 옛 양식·옛 R 번호·`[요청]` 은 옛 동작 그대로 ⑥ 유지하는 안전 장치 10가지(분석 §5-5)를 시험으로 그대로 증명.
GitHub·텔레그램은 가짜(NoticeGitHub·FakeNet)이고 실제 호출은 없다.
"""
import itertools
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path

import yaml

import _bootstrap
import notice_helpers as nth
import notify_helpers as nh
import operator_loop_helpers as oh
import telegram_inbox_helpers as th
from notice_helpers import NoticeGitHub, answer_body, issue_item
from notify_helpers import FakeNet, leaks
from operator_loop_helpers import ANSWER, OWNER, ack_env, issue_event, reply_body
from pipeline import notify
from pipeline import operator_loop as ol
from pipeline import telegram_inbox as ti

ROOT = _bootstrap.ROOT
RLO = chr(0x202E)
HOSTILE = ["$(touch /tmp/pwned)", "::set-output name=x::1", "##[warning]가짜", "@everyone", "#999", "<script>alert(1)</script>", "`rm -rf /`",
           "https://evil.example/login", "[클릭](https://evil.example)", RLO + "반전", "javascript:alert(1)"]     # 접수 코멘트 맨 앞 표지(`<!-- ack:v1 -->`)는 코드가 직접 쓰므로 따로 시험한다
SAFE_FORM = "AI 확인 요청에 답하기(대상번호)"


def answer(**kwargs):
    """parse_reply 를 소유자가 연 새 양식 이슈 기준으로 부른다."""
    args = {"title": "[답변] ", "body": answer_body(), "login": OWNER, "association": "OWNER", "owner": OWNER}
    args.update(kwargs)
    return ol.parse_reply(args["title"], args["body"], args["login"], args["association"], args["owner"])


# ---- 기준 구현(정규식 없이): 대상번호 읽기 -------------------------------------------------------------------------------
def digits(text):
    return bool(text) and all(char in "0123456789" for char in text)


def numberish(part):
    rest = part
    if part[:1] in tuple("PpMmRr"):                       # 하이픈은 접두 글자 바로 뒤에서만 봐준다
        rest = part[1:]
        rest = rest[1:] if rest[:1] == "-" else rest
    return digits(rest) and len(rest) <= 4


def standard_number(text):
    """표준 표기의 번호 숫자 — 세 자리 `001`~`999`(0 채움) 또는 네 자리 `1000`~`9999`(앞에 0 이 더 붙으면 번호가 아니다)."""
    return digits(text) and ((len(text) == 3 and int(text) >= 1) or (len(text) == 4 and int(text) >= 1000))


def oracle_target(raw):
    text = raw.strip()
    if not text:
        return "", "", "empty"
    if standard_number(text):
        return "ask", text, ""
    if text[0] in tuple("PpMm"):
        rest = text[1:]
        rest = rest[1:] if rest[:1] in (" ", "-") else rest
        if digits(rest) and 3 <= len(rest) <= 4:
            return "", "", "type"
    if text[0] in ("r", "R"):
        rest = text[1:]
        rest = rest[1:] if rest[:1] in (" ", "-") else rest
        if digits(rest) and len(rest) == 3:
            return "request", "R-" + rest, ""
    if digits(text) and len(text) <= 2:
        return "", "", "short"
    parts = []
    token = ""
    for char in text:
        if char.isspace() or char in (",", "/", "·"):
            if token:
                parts.append(token)
                token = ""
        else:
            token += char
    if token:
        parts.append(token)
    if len(parts) >= 2 and all(numberish(part) for part in parts):
        return "", "", "two"
    return "", "", "format"


class ParseTargetTest(unittest.TestCase):
    def test_a_confirmation_request_number_is_three_or_four_ascii_digits(self):
        for raw in ("001", " 001 ", "\t001\n", "003", "012", "999", "1000", "9999"):
            self.assertEqual(ol.parse_target(raw), ("ask", raw.strip(), ""), repr(raw))

    def test_a_number_with_extra_leading_zeros_is_a_shape_problem_not_a_second_spelling_of_another_number(self):
        """수정 1차(V2 M1): `0003`·`0012`·`0999` 같은 앞 0 네 자리는 `003`·`012`·`999` 와 같은 값이라 '같은 번호가 두 글자로' 적히므로 번호가 아니다 — 쉬운 '번호 모양' 안내로 거절한다."""
        for raw in ("0001", "0003", "0012", "0100", "0999", " 0003 ", "0000", "00012"):
            self.assertEqual(ol.parse_target(raw), ("", "", "format"), repr(raw))
        for number in range(1, 1000):
            self.assertEqual(ol.parse_target(f"{number:03d}"), ("ask", f"{number:03d}", ""), number)
            self.assertEqual(ol.parse_target(f"{number:04d}"), ("", "", "format"), number)
        for number in range(1000, 10000):
            self.assertEqual(ol.parse_target(str(number)), ("ask", str(number), ""), number)
        self.assertIn("앞에 0 을 더 붙이지", ol.TARGET_PROBLEMS["format"])                                  # 운영자에게 무엇을 고치면 되는지 말한다
        self.assertEqual(ol.parse_target("P0012"), ("", "", "type"))                                       # P·M 으로 시작하는 번호는 여전히 '답하는 번호가 아님' 안내

    def test_an_old_request_number_in_any_of_the_five_shapes_is_read_as_the_canonical_one(self):
        for raw in ("r149", "R149", "r-149", "R-149", "r 149", " R-149 ", "r-000", "R999"):
            kind, value, problem = ol.parse_target(raw)
            self.assertEqual((kind, problem), ("request", ""), repr(raw))
            self.assertEqual(value, "R-" + raw.strip()[-3:], repr(raw))
            self.assertEqual(value, ol.normalize_request_id(raw))

    def test_the_problem_classes(self):
        table = {"empty": ["", "   ", None, "\n", "\t"], "short": ["1", "12", "0", "00", " 7 "],
                 "type": ["P012", "M007", "p012", "m007", "P-012", "M 007", "P0012", "P000", "m1234"],
                 "two": ["001 002", "001,002", "001/002", "001 · 002", "001\n002", "001 r149", "r149 r150", "1 2", "P012 M007", "001,r149"],
                 "format": ["001 메모", "#001", "001.", "０１２", "P０１２", "①②③", "٠٠١", "12345", "00012", "000", "0000", "r1490", "r14", "r-14", "ｒ149", "R−149", "x001", "001a",
                            "001\u200b", "0\u200b01", "\u200b001", "P", "-001", "r", "R-", "r--149", "r_149", "001-002x", "(001)", "[001]", "001번", "no.001", "P 012 메모", "0001", "0003", "0012", "0999"]}
        for problem, values in table.items():
            for raw in values:
                self.assertEqual(ol.parse_target(raw), ("", "", problem), repr(raw))
        self.assertEqual(set(table), set(ol.TARGET_PROBLEMS))

    def test_every_short_text_over_a_hostile_alphabet_matches_the_hand_written_oracle(self):
        alphabet = ["P", "M", "r", "R", "0", "1", "9", " ", "-", "\n", "１", "\u200b", ","]
        checked = 0
        for length in range(0, 6):
            for chars in itertools.product(alphabet, repeat=length):
                raw = "".join(chars)
                self.assertEqual(ol.parse_target(raw), oracle_target(raw), repr(raw))
                checked += 1
        self.assertGreater(checked, 300000)

    def test_the_problem_sentences_are_fixed_one_liners_for_the_phone_and_the_comment(self):
        for code, text in ol.TARGET_PROBLEMS.items():
            self.assertTrue(text.strip() and "\n" not in text, code)
            self.assertIn("대상번호", text)
        self.assertIn("예: 001", ol.TARGET_PROBLEMS["empty"])
        self.assertIn("숫자 3자리", ol.TARGET_PROBLEMS["short"])
        self.assertIn("하나만", ol.TARGET_PROBLEMS["two"])
        self.assertIn("P·M", ol.TARGET_PROBLEMS["type"])


class ParseChoiceTest(unittest.TestCase):
    def test_none_and_the_safe_default(self):
        for raw in ("", None, "   ", "선택 안 함", " 선택 안 함 ", "\n"):
            self.assertEqual(ol.parse_choice(raw), (0, ""), repr(raw))
        self.assertEqual(ol.CHOICE_NONE, "선택 안 함")

    def test_circled_digits_digits_and_the_short_suffixes_are_the_same_choice(self):
        for number in range(1, 6):
            for raw in (chr(0x2460 + number - 1), chr(0x2776 + number - 1), str(number), f"{number}.", f"{number})", f"{number}번", f" {chr(0x2460 + number - 1)} "):
                self.assertEqual(ol.parse_choice(raw), (number, ""), repr(raw))

    def test_anything_else_is_invalid_and_is_dropped_not_guessed(self):
        for raw in ("⑥", "⑩", "⑳", "0", "6", "10", "A", "두번째", "２", "①②", "1 2", "선택", "선택안함", "2번째", "二", "②\u200b", "-1", "②번", "1,2", "①.", "❻", "０", "+2", "02", "2..", "2번."):
            self.assertEqual(ol.parse_choice(raw), (0, "invalid"), repr(raw))

    def test_the_choice_options_of_the_form_are_the_none_word_and_five_circled_digits(self):
        self.assertEqual(ol.CHOICE_OPTIONS, ("선택 안 함", "①", "②", "③", "④", "⑤"))
        self.assertEqual(ol.CHOICE_DEFAULT_INDEX, 0)
        for index, option in enumerate(ol.CHOICE_OPTIONS):
            self.assertEqual(ol.parse_choice(option), (index, ""), option)

    def test_a_choice_never_reads_as_an_approval_word(self):
        for word in ("승인", "approve", "yes", "예", "OK", "ok", "승인 — 제안한 대로 진행해 주세요"):
            self.assertEqual(ol.parse_choice(word), (0, "invalid"), word)


class ParseAnswerTest(unittest.TestCase):
    def test_a_target_only_answer_has_no_choice_and_no_approval_word(self):
        result = answer()
        self.assertEqual(result, ol.Submission("answer", "", "", "", False, 0, "", False, "001", 0))
        self.assertEqual((result.answer, result.choice, result.approval_yes), ("", "", False))

    def test_a_choice_and_a_memo_are_read_and_the_memo_is_only_counted(self):
        result = answer(body=answer_body("003", "②", "확인했습니다 감사"))
        self.assertEqual(result, ol.Submission("answer", "", "", "", False, len("확인했습니다 감사"), "", False, "003", 2))
        for number, symbol in enumerate(ol.CHOICE_OPTIONS):
            self.assertEqual(answer(body=answer_body("004", symbol)).choice_no, number, symbol)

    def test_line_ends_and_edge_spaces_do_not_matter(self):
        for crlf in (True, False):
            self.assertEqual(answer(body=answer_body("003", "③", crlf=crlf)).choice_no, 3)
        self.assertEqual(answer(body=answer_body("  003  ")).target, "003")

    def test_an_old_request_number_in_the_new_form_is_received_as_the_old_request(self):
        for raw in ("r149", "R-149", "r-149", "R149", "r 149"):
            result = answer(body=answer_body(raw, "②"))
            self.assertEqual((result.kind, result.target, result.request_id, result.choice_no), ("answer", "R-149", "R-149", 2), raw)

    def test_an_invalid_choice_is_dropped_and_marked_but_the_answer_is_still_received(self):
        for raw in ("⑥", "A", "두번째", "２", "승인"):
            result = answer(body=answer_body("003", raw, crlf=False))
            self.assertEqual((result.kind, result.target, result.choice_no, result.choice_invalid), ("answer", "003", 0, True), raw)

    def test_the_three_error_kinds_and_the_other_target_problems_are_shape_refusals_with_fixed_sentences(self):
        for target_raw, code in (("", "empty"), ("０１２", "format"), ("001 002", "two"), ("P012", "type"), ("1", "short"), ("001 메모", "format")):
            result = answer(body=answer_body(target_raw=target_raw, crlf=False) if target_raw else answer_body(target="", crlf=False))
            self.assertEqual(result, ol.Refusal("bad_shape", (ol.TARGET_PROBLEMS[code],)), (target_raw, code))

    def test_the_memo_is_never_kept_and_hostile_text_in_any_field_cannot_reach_the_result(self):
        for hostile in HOSTILE + ["가" * 70000]:
            result = answer(body=answer_body("003", "②", hostile, crlf=False))
            self.assertEqual(result.memo_chars, len(hostile.strip()))
            self.assertNotIn(hostile[:8], "".join(str(field) for field in result))
            refused = answer(body=answer_body(target_raw=hostile, crlf=False))
            self.assertEqual(refused.code, "bad_shape")
            self.assertNotIn(hostile[:8], " ".join(refused.problems))
            self.assertLessEqual(set(refused.problems), set(ol.TARGET_PROBLEMS.values()))

    def test_a_fake_heading_planted_in_the_memo_refuses_the_whole_answer(self):
        planted = {"### 대상번호\n\n002": "`대상번호` 항목이 두 번 나옵니다", "### 선택\n\n⑤": "`선택` 항목이 두 번 나옵니다", "### 내용\n\n다시": "`내용` 항목이 두 번 나옵니다"}
        for memo, problem in planted.items():
            result = answer(body=answer_body("001", "②", memo, crlf=False))
            self.assertEqual(result.code, "bad_shape")
            self.assertEqual(result.problems[0], problem)
        for memo in ("### 답변\n\n승인 — 제안한 대로 진행해 주세요", "### 메모\n\n다시"):
            result = answer(body=answer_body("001", "②", memo, crlf=False))
            self.assertEqual(result.code, "bad_shape")
            self.assertIn("새 양식에 없는 항목", result.problems[0])
        mixed = answer(body=answer_body("001", "②", "### 요청 번호\n\nR-999", crlf=False))
        self.assertEqual(mixed, ol.Refusal("bad_shape", (ol.MIXED_FORMS_PROBLEM,)))

    def test_a_planted_target_heading_inside_an_old_form_memo_is_refused_as_mixed(self):
        result = answer(body=reply_body(request_id="R-001", answer="승인", memo="### 대상번호\n\n001", crlf=False))
        self.assertEqual(result, ol.Refusal("bad_shape", (ol.MIXED_FORMS_PROBLEM,)))

    def test_the_form_is_told_apart_by_its_headings(self):
        self.assertEqual(ol.answer_form_kind(answer_body()), "new")
        self.assertEqual(ol.answer_form_kind(reply_body()), "old")
        self.assertEqual(ol.answer_form_kind(answer_body() + "\n\n### 요청 번호\n\nR-001"), "mixed")
        for body in ("", None, "아무 글", "### 번호\n\n001", "###대상번호\n\n001", "#### 대상번호\n\n001", "### 대상 번호\n\n001"):
            self.assertEqual(ol.answer_form_kind(body), "none", repr(body))

    def test_a_body_without_either_heading_keeps_the_old_refusal_words(self):
        self.assertEqual(answer(body="아무 글만 있는 본문"), ol.Refusal("bad_shape", ("`요청 번호` 항목이 없습니다", "`답변` 항목이 없습니다")))

    def test_the_old_form_is_read_exactly_as_before_and_old_answers_still_carry_their_word(self):
        result = answer(body=reply_body(request_id="R-042", answer="승인", choice="B", memo="메모"))
        self.assertEqual(result, ol.Submission("reply", "R-042", "승인", "B", False, 2, "", False))
        self.assertEqual((result.target, result.choice_no), ("", 0))
        for short, full in ol.ANSWER_OPTIONS:
            self.assertEqual(answer(body=reply_body(answer=short)).answer, short)
            self.assertEqual(ANSWER[short], full)

    def test_a_memo_with_a_heading_of_the_new_form_but_in_the_old_form_is_still_old_text(self):
        """옛 양식 메모에 `### 내용` 같은 줄이 있어도(새 양식 제목이지만 `대상번호` 는 아니다) 옛 방식 그대로 메모 글자 수로 센다."""
        body = reply_body(request_id="R-001", answer="보류", memo="### 내용\n\n메모 글", crlf=False)
        result = answer(body=body)
        self.assertEqual((result.kind, result.answer), ("reply", "보류"))
        self.assertEqual(result.memo_chars, len("### 내용\n\n메모 글"))

    def test_the_trust_gate_comes_first_for_the_new_form_too(self):
        self.assertEqual(answer(login="stranger"), ol.Refusal("not_owner", ()))
        self.assertEqual(answer(login="stranger", association="OWNER"), ol.Refusal("not_owner", ()))
        for association in ("MEMBER", "COLLABORATOR", "NONE", "CONTRIBUTOR", "owner", None, ""):
            self.assertEqual(answer(association=association), ol.Refusal("not_owner_association", ()), association)
        self.assertEqual(answer(owner=""), ol.Refusal("no_owner", ()))
        for title in ("", None, "답변", " [답변]", "[질문] ", "x [답변]", "(답변)", "[ANSWER]", "[페이지 수정] x"):
            self.assertEqual(answer(title=title), ol.Refusal("not_form", ()), repr(title))
        self.assertEqual(answer(title="[답변]").kind, "answer")
        self.assertEqual(answer(title="[답변] 아무 글").kind, "answer")

    def test_the_task_form_is_not_touched_by_the_new_detection(self):
        result = ol.parse_reply("[요청] ", oh.task_body(approval=oh.TASK_SCOPE["yes"]), OWNER, "OWNER", OWNER)
        self.assertEqual((result.kind, result.target, result.choice_no, result.request_id, result.answer), ("task", "", 0, "", ""))
        self.assertEqual(ol.parse_reply("[요청] ", answer_body(), OWNER, "OWNER", OWNER).code, "bad_shape")


class AckAnswerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo_root = self.tmp / "repo"
        (self.repo_root / ol.REQUEST_DIR).mkdir(parents=True)
        self.summary = self.tmp / "summary.md"

    def ack(self, event=None, github=None, net=None, **env):
        event = event if event is not None else nth.answer_event()
        github = github if github is not None else NoticeGitHub()
        environ = ack_env(self.tmp, event, GITHUB_STEP_SUMMARY=str(self.summary), **env)
        return oh.run_cli("ack", environ=environ, net=net, root=self.repo_root, github=github)

    def sequence(self, github):
        return [(item["method"], item["path"]) for item in github.requests]

    # ---- 정상 접수 ----
    def test_a_target_only_answer_is_received_as_acknowledged_not_approved(self):
        code, lines, net, github = self.ack()
        self.assertEqual(code, 0)
        self.assertEqual(self.sequence(github), [("POST", "/labels"), ("POST", "/issues/145/labels"), ("GET", "/issues"), ("GET", "/issues/145/comments"), ("POST", "/issues/145/comments")])
        self.assertEqual(github.issue_labels, {145: ["운영자응답"]})
        comment = github.posted(145)[0]
        self.assertTrue(comment.startswith(ol.ACK_MARK + "\n접수했습니다 — 확인 요청 **001** · 확인함(승인 아님).\n\n"), comment[:90])
        self.assertIn("- 대상번호만 올린 답은 '확인함' 일 뿐 승인이 아닙니다.", comment)
        self.assertEqual(net.calls, 1)
        body = net.bodies()[0]
        self.assertEqual(body["text"], f"{notify.OK_MARK} 답변 접수 001 → 확인함 — 승인 아님(이슈 #145) · 번호가 요청과 맞는지는 AI 가 대조합니다")
        self.assertNotIn("parse_mode", body)
        self.assertIn(ol.NUMBER_CHECK_NOTE, github.posted(145)[0])                                       # 수정 1차(V3 L1·L3): 코멘트에도 '번호 일치는 AI 가 대조한다' 한 줄
        # 수정 2차(V1 C23): 그 문장의 **글자**를 못박는다(상수를 되읽기만 하면 '맞는 것을 이 접수가 확인했습니다' 로 뒤집어도 통과한다) — 접수는 번호가 맞는지 모른다고 말해야 한다
        for phrase in ("맞는지는 이 접수가 알 수 없습니다", "접수 워크플로는 요청 파일이 없는 기본 브랜치만 봅니다", "AI 가 이슈를 읽을 때 대조하고", "번호가 틀렸으면 폰으로 알립니다"):
            self.assertIn(phrase, github.posted(145)[0], phrase)
        self.assertNotIn("확인했습니다", github.posted(145)[0])                                          # 접수가 번호를 확인했다고 거짓으로 말하지 않는다
        self.assertEqual(body["reply_markup"]["inline_keyboard"], [[{"text": "이슈 열기", "url": "https://github.com/shine88pc/chanceblog/issues/145"}]])
        self.assertEqual(lines, ["운영자 응답 접수: 이슈 #145 에 라벨 운영자응답 을 붙였습니다", "운영자 응답 접수: 이슈 #145 에 접수 코멘트를 달았습니다", "운영자 응답 접수: 텔레그램으로 접수를 알렸습니다"])
        self.assertEqual(self.summary.read_text(encoding="utf-8").strip(), "### 운영자 응답 접수\n\n- 이슈 #145: 대상번호 001 의 답을 접수했습니다(선택 없음)")
        self.assertEqual(body["text"].count("승인"), 1)                                                   # '승인' 은 오직 '승인 아님' 으로만 나온다(수정 1차: 폰 확인함 문구에 승인 아님을 쓴다)
        self.assertIn("승인 아님", body["text"])

    def test_an_answer_with_a_choice_and_a_memo_says_the_choice_and_how_many_characters_but_never_the_memo(self):
        memo = "확인했습니다 감사합니다"
        code, lines, net, github = self.ack(nth.answer_event(body=answer_body("003", "②", memo)))
        comment = github.posted(145)[0]
        self.assertTrue(comment.startswith(ol.ACK_MARK + f"\n접수했습니다 — 확인 요청 **003** · 선택: **②** · 내용: 있음({len(memo)}자).\n\n"), comment[:100])
        self.assertIn("- 내용 글은 AI 가 이슈 본문에서 읽습니다(여기에는 되풀이하지 않습니다).", comment)
        self.assertIn("- 승인은 그 확인 요청에 승인 보기로 적힌 번호를 직접 고른 경우에만 인정됩니다. AI 가 요청 파일과 대조해 확인합니다.", comment)
        self.assertNotIn(memo, comment + json.dumps(net.bodies(), ensure_ascii=False) + "\n".join(lines))
        self.assertEqual(net.bodies()[0]["text"], f"{notify.OK_MARK} 답변 접수 003 → 선택 ②(이슈 #145)")

    def test_every_choice_symbol_is_acknowledged_in_the_phone_message(self):
        for number, symbol in enumerate(ol.CHOICE_OPTIONS):
            code, lines, net, github = self.ack(nth.answer_event(body=answer_body("003", symbol)))
            want = f"{notify.OK_MARK} 답변 접수 003 → " + (f"선택 {symbol}" if number else "확인함 — 승인 아님") + "(이슈 #145)" + ("" if number else " · 번호가 요청과 맞는지는 AI 가 대조합니다")
            self.assertEqual(net.bodies()[0]["text"], want, symbol)

    def test_an_old_request_number_in_the_new_form_is_received_only_and_says_it_cannot_approve(self):
        code, lines, net, github = self.ack(nth.answer_event(body=answer_body("r149", "②")))
        comment = github.posted(145)[0]
        self.assertTrue(comment.startswith(ol.ACK_MARK + "\n접수했습니다 — 요청 **r149**(이전 R 번호) · 선택: **②**.\n\n"), comment[:100])
        self.assertIn(ol.OLD_TARGET_NOTE, comment)
        self.assertIn("옛 R 번호 요청에는 새 양식으로 승인할 수 없습니다", comment)
        self.assertEqual(net.bodies()[0]["text"],
                         f"{notify.OK_MARK} 답변 접수 r149 → 선택 ②(이슈 #145) · 옛 R 번호 요청은 새 양식으로 승인되지 않습니다(승인은 이전 R 번호용 양식으로)")
        self.assertNotIn("R-149", comment + net.bodies()[0]["text"])

    def test_an_invalid_choice_is_received_without_the_choice_and_the_comment_says_so(self):
        code, lines, net, github = self.ack(nth.answer_event(body=answer_body("003", "두번째")))
        comment = github.posted(145)[0]
        self.assertIn("- 선택 칸의 값이 양식의 선택지(`선택 안 함`·①~⑤)가 아니라 표시하지 않았습니다. AI 가 이슈 본문에서 읽습니다.", comment)
        self.assertEqual(net.bodies()[0]["text"], f"{notify.OK_MARK} 답변 접수 003 → 확인함 — 승인 아님(이슈 #145) · 번호가 요청과 맞는지는 AI 가 대조합니다")

    def test_without_telegram_secrets_the_comment_is_still_posted(self):
        code, lines, net, github = self.ack(telegram=False)
        self.assertEqual((code, net.calls, len(github.posted(145))), (0, 0, 1))
        self.assertIn(notify.SKIP_LINE, lines)

    # ---- 이미 답한 번호는 대체 ----
    def earlier(self, number, target="003", **kwargs):
        return issue_item(number, kwargs.pop("body", None) or answer_body(target), **kwargs)

    def test_an_earlier_answer_to_the_same_number_is_replaced_and_the_newest_earlier_one_is_named(self):
        github = NoticeGitHub(issues=[self.earlier(144), self.earlier(143), self.earlier(120)])
        code, lines, net, github = self.ack(nth.answer_event(number=146, body=answer_body("003", "①")), github=github)
        comment = github.posted(146)[0]
        self.assertIn("- 이 번호에 앞서 올린 답(이슈 #144)이 있어 이 답이 그것을 대체합니다 — 가장 나중 답이 이깁니다(앞 이슈는 지우지 않습니다).", comment)
        self.assertEqual(net.bodies()[0]["text"], f"{notify.OK_MARK} 답변 접수 003 → 선택 ①(이슈 #146) · 이전 답(이슈 #144)을 대체합니다")
        self.assertIn("이슈 #144 을 대체", self.summary.read_text(encoding="utf-8"))
        query = [item for item in github.requests if item["path"] == "/issues"][0]["query"]
        for needle in (f"creator={OWNER}", "labels=%EC%9A%B4%EC%98%81%EC%9E%90%EC%9D%91%EB%8B%B5", "state=all", "per_page=100"):
            self.assertIn(needle, query)
        # 수정 2차(V1 D09·B02): 요청 매개변수 **전부**를 못박는다 — `sort=created` 를 `updated` 로, `direction=desc` 를 `asc` 로 바꾸면(최근에 고친 옛 이슈가 '가장 나중 답'으로 읽힘) 빨개진다
        self.assertEqual(urllib.parse.parse_qs(query), {"creator": [OWNER], "labels": ["운영자응답"], "state": ["all"], "sort": ["created"], "direction": ["desc"], "per_page": ["100"]})

    def test_only_the_owners_new_form_answers_to_the_same_number_before_this_issue_count(self):
        items = [self.earlier(150),                                                                                      # 이 이슈보다 뒤 번호
                 self.earlier(145),                                                                                      # 이 이슈 자신
                 self.earlier(144, "004"),                                                                               # 다른 번호
                 self.earlier(143, login="stranger"),                                                                    # 낯선 사람
                 self.earlier(142, association="MEMBER"),                                                                # 소유자 login 이지만 권한이 OWNER 가 아님
                 self.earlier(141, pull_request=True),                                                                   # PR
                 self.earlier(140, body=reply_body(request_id="R-003")),                                                 # 옛 양식
                 self.earlier(139, title="[요청] ", body=oh.task_body()),                                                # 다른 양식
                 self.earlier(138, body=answer_body(target_raw="003 004")),                                              # 모양 오류
                 self.earlier(137, body="아무 글")]
        code, lines, net, github = self.ack(github=NoticeGitHub(issues=items), event=nth.answer_event(number=145, body=answer_body("003")))
        self.assertNotIn("대체", github.posted(145)[0])
        self.assertNotIn("대체", net.bodies()[0]["text"])
        items.append(self.earlier(100))                                                                                  # 이제 진짜 앞선 답이 하나 있다
        code, lines, net, github = self.ack(github=NoticeGitHub(issues=items), event=nth.answer_event(number=146, body=answer_body("003")))
        self.assertIn("이전 답(이슈 #145)을 대체합니다", net.bodies()[0]["text"])       # 145 는 이제 앞선 답(모양 오류 아님)이다

    def test_an_old_request_number_answer_is_also_replaced_by_a_later_one_for_the_same_old_request(self):
        github = NoticeGitHub(issues=[self.earlier(140, "r149")])
        code, lines, net, github = self.ack(nth.answer_event(number=146, body=answer_body("R-149", "②")), github=github)
        self.assertIn("이전 답(이슈 #140)을 대체합니다", net.bodies()[0]["text"])

    def test_an_unreadable_list_is_a_log_line_and_the_acknowledgement_still_goes(self):
        for failure in (oh.http_error(500, "boom"), oh.http_error(403, "rate limit exceeded"), urllib.error.URLError("net")):
            github = NoticeGitHub(list_failure=failure)
            code, lines, net, github = self.ack(github=github)
            self.assertEqual((code, len(github.posted(145)), net.calls), (0, 1, 1), failure)
            self.assertTrue(any(line.startswith("운영자 응답 접수: 앞서 올라온 답을 확인하지 못했습니다 — ") for line in lines), lines)
            self.assertNotIn("대체", net.bodies()[0]["text"])
            self.assertFalse(any(line == ol.ACK_WARNING for line in lines), lines)
        github = NoticeGitHub()
        github.issues = {"not": "a list"}
        code, lines, net, github = self.ack(github=github)
        self.assertEqual((code, net.calls), (0, 1))

    def test_the_old_form_does_not_look_up_earlier_answers_at_all(self):
        github = NoticeGitHub()
        code, lines, net, github = self.ack(issue_event(body=reply_body(request_id="R-001", answer="승인")), github=github)
        self.assertNotIn(("GET", "/issues"), self.sequence(github))
        self.assertEqual(self.sequence(github), [("POST", "/labels"), ("POST", "/issues/12/labels"), ("GET", "/issues/12/comments"), ("POST", "/issues/12/comments")])

    # ---- 오류도 폰으로 ----
    def test_the_three_error_kinds_get_a_comment_and_a_phone_reply_with_one_fixed_reason(self):
        cases = (("", "empty"), ("０１２", "format"), ("001 002", "two"), ("P012", "type"), ("1", "short"))
        for target_raw, code_name in cases:
            body = answer_body(target="", crlf=False) if not target_raw else answer_body(target_raw=target_raw)
            code, lines, net, github = self.ack(nth.answer_event(body=body))
            self.assertEqual(code, 0)
            comment = github.posted(145)[0]
            self.assertTrue(comment.startswith(ol.ACK_MARK + f"\n양식 모양이 달라 처리하지 못했습니다 — {ol.TARGET_PROBLEMS[code_name]}.\n\n"), (code_name, comment[:120]))
            self.assertIn(SAFE_FORM, comment)
            self.assertEqual(github.issue_labels, {145: ["운영자응답"]})
            self.assertEqual(net.calls, 1, code_name)
            want = f"{notify.WARN_MARK} 답변을 접수하지 못했습니다(이슈 #145) — {ol.TARGET_PROBLEMS[code_name].replace(chr(96), '')}. 새 이슈로 다시 올려 주세요."
            self.assertEqual(net.bodies()[0]["text"], want, code_name)
            self.assertIn("운영자 응답 접수: 텔레그램으로 접수하지 못했다는 회신을 보냈습니다", lines)
            self.assertNotIn(("GET", "/issues"), self.sequence(github))                                                 # 오류 이슈는 앞선 답을 찾지 않는다

    def test_with_several_problems_the_phone_gets_the_first_one_and_the_comment_lists_them_all(self):
        """수정 1차(V3 O32): 문제가 둘 이상이면 폰에는 첫 문제의 고정 문장 한 줄만, 이슈 코멘트에는 전부 — 폰 회신이 `problems[0]` 대신 `[-1]` 을 쓰면 빨개진다."""
        body = answer_body(target_raw="P012", memo="### 내용\n\n또 하나", crlf=False)
        first, second = "`내용` 항목이 두 번 나옵니다", ol.TARGET_PROBLEMS["type"]
        code, lines, net, github = self.ack(nth.answer_event(body=body))
        self.assertEqual(code, 0)
        self.assertIn(f"{first}; {second}", github.posted(145)[0])
        phone = net.bodies()[0]["text"]
        self.assertEqual(phone, f"{notify.WARN_MARK} 답변을 접수하지 못했습니다(이슈 #145) — {first.replace(chr(96), '')}. 새 이슈로 다시 올려 주세요.")
        self.assertNotIn(second.replace(chr(96), ""), phone)

    def test_a_planted_heading_and_mixed_forms_are_also_answered_on_the_phone(self):
        for memo, reason in (("### 대상번호\n\n002", "`대상번호` 항목이 두 번 나옵니다"), ("### 요청 번호\n\nR-001", ol.MIXED_FORMS_PROBLEM)):
            code, lines, net, github = self.ack(nth.answer_event(body=answer_body("001", "②", memo, crlf=False)))
            self.assertEqual(net.calls, 1)
            self.assertEqual(net.bodies()[0]["text"], f"{notify.WARN_MARK} 답변을 접수하지 못했습니다(이슈 #145) — {reason.replace(chr(96), '')}. 새 이슈로 다시 올려 주세요.")

    def test_the_error_reply_is_sent_once_even_if_the_run_repeats(self):
        github = NoticeGitHub()
        self.ack(nth.answer_event(body=answer_body(target_raw="P012")), github=github)
        code, lines, net, _ = self.ack(nth.answer_event(body=answer_body(target_raw="P012")), github=github)
        self.assertEqual((code, net.calls, len(github.posted(145))), (0, 0, 1))

    def test_a_stranger_gets_no_comment_no_label_and_no_phone_message_even_with_a_perfect_or_a_broken_form(self):
        for body in (answer_body("001", "②"), answer_body(target_raw="P012"), answer_body(target="")):
            for login, association in (("stranger", "NONE"), ("stranger", "OWNER"), (OWNER, "MEMBER"), (OWNER, "CONTRIBUTOR")):
                code, lines, net, github = self.ack(nth.answer_event(body=body, login=login, association=association))
                self.assertEqual((code, github.requests, net.calls), (0, [], 0), (login, association))
                self.assertEqual(len(lines), 1)
                self.assertFalse(self.summary.exists())

    def test_the_error_reply_needs_the_secrets_and_a_telegram_failure_is_a_warning_only(self):
        code, lines, net, github = self.ack(nth.answer_event(body=answer_body(target_raw="P012")), telegram=False)
        self.assertEqual((net.calls, len(github.posted(145))), (0, 1))
        self.assertIn(notify.SKIP_LINE, lines)
        code, lines, net, github = self.ack(nth.answer_event(body=answer_body(target_raw="P012")), net=FakeNet(nh.http_error(401, "Unauthorized " + nh.TOKEN)))
        self.assertEqual((code, len(github.posted(145))), (0, 1))
        self.assertEqual(lines[-1], ol.ACK_WARNING)
        self.assertEqual(leaks(*lines), [])

    def test_an_old_form_shape_error_and_a_body_without_headings_and_a_task_error_still_get_no_phone_message(self):
        for event in (issue_event(body=reply_body(request_id="R-1", answer="승인")), issue_event(body="양식을 쓰지 않고 직접 쓴 글"),
                      issue_event(number=13, title="[요청] ", body=oh.task_body(what=""))):
            code, lines, net, github = self.ack(event)
            self.assertEqual((code, net.calls), (0, 0))
            self.assertEqual(len(github.posted(event["issue"]["number"])), 1)
            self.assertTrue(github.posted(event["issue"]["number"])[0].startswith(ol.ACK_MARK + "\n양식 모양이 달라 처리하지 못했습니다 — "))
            self.assertIn(SAFE_FORM, github.posted(event["issue"]["number"])[0])

    def test_a_task_request_is_received_exactly_as_before(self):
        event = issue_event(number=13, title="[요청] ", body=oh.task_body(what="PR 을 정리해 주세요", urgency="급함", approval=oh.TASK_SCOPE["yes"]))
        code, lines, net, github = self.ack(event)
        self.assertEqual(net.bodies()[0]["text"], f"{notify.OK_MARK} 새 일 요청 접수(이슈 #13) · 긴급도 급함 · 진행 범위 구현까지(T3 제외)")
        self.assertNotIn(("GET", "/issues"), self.sequence(github))


class RoundTripTest(unittest.TestCase):
    """알림이 말한 번호가 답 이슈의 번호로 되돌아오고, AI 가 승인을 판정할 때 쓰는 값(번호 글자·선택 번호)이 요청 파일의 `no`·`approve` 와 맞물리는지 — 요청 → 폰 글 → 양식 → 접수 → 승인 판정 한 바퀴."""

    @staticmethod
    def approved(sub, request):
        """G-S9 의 새 양식 규칙을 문서대로 옮긴 판정(AI 쪽 일 — 코드에는 없다): 번호가 같고 선택이 `approve` 보기와 같을 때만."""
        fields = dict(request.fields)
        return (isinstance(sub, ol.Submission) and sub.kind == "answer" and sub.target == request.no and sub.choice_no != 0
                and str(sub.choice_no) == fields.get("approve", "none"))

    def test_the_number_on_the_phone_comes_back_as_the_target_for_every_number(self):
        for kind in ("ask",):
            for number in list(range(1, 1100)) + [9998, 9999]:
                no = notify.notice_no_text(kind, number)
                phone = notify.format_notice(no, {"summary": "x"})
                self.assertIn(f"대상번호 {no} ", phone)
                sub = answer(body=answer_body(no, "②", crlf=False))
                self.assertEqual((sub.kind, sub.target), ("answer", no), no)

    def test_only_the_approve_choice_on_the_matching_number_counts_as_an_approval(self):
        request = nth.parse(nth.notice_text(number=170, no="003", kind="decision", summary="무엇을 할까요", fields={**nth.ASK, "approve": "2", "default": "1"}), number=170, strict=True)
        for choice, expected in zip(ol.CHOICE_OPTIONS, (False, False, True, False, False, False), strict=True):
            self.assertEqual(self.approved(answer(body=answer_body("003", choice)), request), expected, choice)
        self.assertFalse(self.approved(answer(body=answer_body("004", "②")), request))                         # 다른 번호
        self.assertFalse(self.approved(answer(body=answer_body("r149", "②")), request))                       # 옛 R 번호
        self.assertFalse(self.approved(answer(body=answer_body("003", "두번째")), request))                    # 틀린 선택은 버려진다
        self.assertFalse(self.approved(answer(body=answer_body("003", "②"), login="stranger"), request))     # 낯선 사람
        self.assertFalse(self.approved(answer(body=answer_body("003", "②"), association="MEMBER"), request))
        self.assertFalse(self.approved(answer(body=answer_body("003", "②", "### 대상번호\n\n004", crlf=False)), request))     # 심은 제목은 모양 오류
        self.assertFalse(self.approved(answer(body=reply_body(request_id="R-003", answer="승인")), request))               # 옛 양식의 승인은 옛 요청의 것

    def test_a_request_without_an_approve_option_can_never_be_approved_by_a_choice(self):
        request = nth.parse(nth.notice_text(number=170, no="003", kind="decision", summary="고르세요", fields={"options": "가 / 나", "default": "1"}), number=170, strict=True)
        for choice in ol.CHOICE_OPTIONS:
            self.assertFalse(self.approved(answer(body=answer_body("003", choice)), request), choice)

    def test_the_whole_flow_from_the_request_file_to_the_receipt(self):
        text = nth.notice_text(number=170, no="003", kind="decision", summary="현황 알림을 4시간 간격으로 바꿀까요?", fields=nth.ASK)
        lines_out = []
        with tempfile.TemporaryDirectory() as tmp:
            git = oh.RequestGit.with_requests({nth.name_of(170): text})
            code, lines, net, _ = oh.run_cli("requests", environ=oh.requests_env(), runner=git, root=tmp)
            lines_out.extend(lines)
            self.assertEqual((code, net.calls), (0, 1))
            message = net.bodies()[0]
            self.assertIn("대상번호 003", message["text"])
            self.assertEqual(message["reply_markup"]["inline_keyboard"][0][0]["url"], notify.NEW_ANSWER_URL)
            repo = Path(tmp) / "repo"
            (repo / ol.REQUEST_DIR).mkdir(parents=True)
            environ = ack_env(tmp, nth.answer_event(number=145, body=answer_body("003", "②", "확인했습니다")))
            code, lines, net, github = oh.run_cli("ack", environ=environ, root=repo, github=NoticeGitHub())
            self.assertEqual((code, net.calls), (0, 1))
            self.assertEqual(net.bodies()[0]["text"], f"{notify.OK_MARK} 답변 접수 003 → 선택 ②(이슈 #145)")
            request = nth.parse(text, number=170, strict=True)
            sub = answer(body=answer_body("003", "②", "확인했습니다"))
            self.assertTrue(self.approved(sub, request))
        self.assertTrue(lines_out)


class SafetyInvariantsTest(unittest.TestCase):
    """분석 §5-5 의 '유지하는 안전 장치 10가지' — 새 양식에서도 그대로인지 하나씩 증명한다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        (self.tmp / "repo" / ol.REQUEST_DIR).mkdir(parents=True)

    def ack(self, event, github=None, **env):
        environ = ack_env(self.tmp, event, **env)
        return oh.run_cli("ack", environ=environ, root=self.tmp / "repo", github=github or NoticeGitHub())

    def test_1_both_the_owner_login_and_the_owner_association_are_needed(self):
        for login, association in (("stranger", "OWNER"), (OWNER, "MEMBER"), (OWNER, "NONE"), (OWNER.replace("s", chr(0x17F), 1), "OWNER"), (OWNER + "x", "OWNER")):
            self.assertIsInstance(answer(login=login, association=association), ol.Refusal, (login, association))
        self.assertIsInstance(answer(login=OWNER.upper(), association="OWNER"), ol.Submission)                          # 영문 대소문자만 봐준다(옛 규칙 그대로)
        workflow = (ROOT / ".github" / "workflows" / "operator-reply.yml").read_text(encoding="utf-8")
        self.assertIn("github.event.issue.user.login == github.repository_owner && github.event.issue.author_association == 'OWNER'", workflow)

    def test_2_the_issue_text_never_enters_a_run_line_an_environment_variable_or_a_workflow_command(self):
        workflow = (ROOT / ".github" / "workflows" / "operator-reply.yml").read_text(encoding="utf-8")
        for needle in ("github.event.issue.title", "github.event.issue.body", "github.event.comment", "github.head_ref"):
            self.assertNotIn(needle, workflow, needle)
        self.assertIn("run: python -m pipeline.operator_loop ack", workflow)
        source = (ROOT / "pipeline" / "operator_loop.py").read_text(encoding="utf-8")
        self.assertNotIn("GITHUB_OUTPUT", source.replace("`$GITHUB_OUTPUT`", ""))
        for hostile in HOSTILE:
            event = nth.answer_event(body=answer_body("001", "②", hostile, crlf=False))
            code, lines, net, github = self.ack(event)
            for shown in (lines, github.comments, net.bodies()):
                self.assertNotIn(hostile, json.dumps(shown, ensure_ascii=False))

    def test_3_the_title_must_start_with_the_answer_prefix(self):
        for title in ("[질문] ", "답변 ", "x [답변]", "[ANSWER] ", "[페이지 수정] 소개", ""):
            code, lines, net, github = self.ack(issue_event(title=title, body=answer_body()))
            self.assertEqual((github.requests, net.calls, lines), ([], 0, ["운영자 응답 접수: " + ol.REFUSAL_LINES["not_form"]]), repr(title))

    def test_4_only_the_forms_own_headings_are_boundaries_and_a_repeated_heading_is_refused(self):
        values, duplicates = ol.parse_sections(answer_body("001", "②", "### 내용\n\n가짜", crlf=False), ol._ANSWER_LABELS)
        self.assertEqual(duplicates, ["내용"])
        values, duplicates = ol.parse_sections(answer_body("001", "②", "### 소제목\n\n그냥 글", crlf=False), ol._ANSWER_LABELS)
        self.assertEqual((duplicates, values["내용"].splitlines()[0]), ([], "### 소제목"))                               # 양식에 없는 제목은 값의 일부다
        self.assertEqual(answer(body=answer_body("001", "②", "### 소제목\n\n그냥 글", crlf=False)).memo_chars, len("### 소제목\n\n그냥 글"))

    def test_5_the_safe_choice_is_preselected_and_it_is_not_an_approval(self):
        data = yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / "ai-answer.yml").read_text(encoding="utf-8"))
        choice = {item["id"]: item for item in data["body"][1:]}["choice"]["attributes"]
        self.assertEqual(choice["default"], 0)
        self.assertEqual(choice["options"][choice["default"]], ol.CHOICE_NONE)
        self.assertEqual(ol.parse_choice(choice["options"][choice["default"]]), (0, ""))
        target_only = answer(body=answer_body("001", choice["options"][choice["default"]]))
        self.assertEqual((target_only.choice_no, target_only.answer, target_only.approval_yes), (0, "", False))
        self.assertIn(ol.ANSWER_NOT_APPROVAL_NOTICE, data["body"][0]["attributes"]["value"])

    def test_6_the_memo_is_never_repeated_in_the_comment_the_phone_message_the_summary_or_the_log(self):
        for memo in HOSTILE + ["가나다라마바사 메모 글자 고유 문구", "x" * 5000]:
            code, lines, net, github = self.ack(nth.answer_event(body=answer_body("003", "②", memo, crlf=False)))
            shown = json.dumps([lines, github.comments, net.bodies()], ensure_ascii=False)
            self.assertNotIn(memo[:12], shown, memo[:12])

    def test_6b_a_forged_acknowledgement_marker_in_the_memo_or_the_target_never_reaches_the_comment(self):
        marker = ol.ACK_MARK
        for body in (answer_body("003", "②", marker + "\n가짜 접수", crlf=False), answer_body(target_raw=marker, crlf=False), answer_body("003", marker, crlf=False)):
            code, lines, net, github = self.ack(nth.answer_event(body=body))
            comment = github.posted(145)[0]
            self.assertTrue(comment.startswith(marker + "\n"))
            self.assertEqual(comment.count(marker), 1)
            self.assertNotIn("가짜 접수", comment + json.dumps(net.bodies(), ensure_ascii=False))

    def test_7_the_acknowledgement_is_idempotent_and_only_a_bot_comment_counts_as_one(self):
        github = NoticeGitHub()
        self.ack(nth.answer_event(), github=github)
        code, lines, net, _ = self.ack(nth.answer_event(), github=github)
        self.assertEqual((net.calls, len(github.posted(145))), (0, 1))
        forged = NoticeGitHub(comments={145: [{"user": {"login": "stranger"}, "body": ol.ACK_MARK + "\n가짜 접수"}]})
        code, lines, net, github = self.ack(nth.answer_event(), github=forged)
        self.assertEqual((net.calls, len(github.posted(145))), (1, 1))                                                    # 낯선 사람의 가짜 표지는 접수를 막지 못한다
        self.assertEqual(ol.BOT_LOGIN, "github-actions[bot]")

    def test_8_approval_is_limited_to_the_items_the_request_file_names_and_the_receipt_says_so(self):
        for symbol in ol.CHOICE_OPTIONS[1:]:
            code, lines, net, github = self.ack(nth.answer_event(body=answer_body("003", symbol)))
            comment = github.posted(145)[0]
            self.assertIn("승인은 그 확인 요청에 승인 보기로 적힌 번호를 직접 고른 경우에만 인정됩니다", comment)
            self.assertNotIn("승인되었습니다", comment + net.bodies()[0]["text"])
            self.assertNotIn("승인했", comment + net.bodies()[0]["text"])
        security = (ROOT / "docs" / "SECURITY_GUARDRAILS.md").read_text(encoding="utf-8")
        row = next(line for line in security.splitlines() if line.startswith("| G-S9 |"))
        self.assertIn("그 요청 파일에 적힌 항목에 한해", row)

    def test_9_the_task_form_and_telegram_received_posts_are_never_approvals(self):
        task = ol.parse_reply("[요청] ", oh.task_body(approval=oh.TASK_SCOPE["yes"]), OWNER, "OWNER", OWNER)
        self.assertEqual((task.kind, task.target, task.answer, task.choice_no), ("task", "", "", 0))
        source = (ROOT / "pipeline" / "telegram_inbox.py").read_text(encoding="utf-8")
        for name in ("parse_reply", "run_ack", "post_ack", "ack_comment", "answer_comment", "earlier_answer"):
            self.assertNotIn(name, source)

    def test_10_comments_and_phone_messages_carry_only_validated_values(self):
        for hostile in HOSTILE:
            for body in (answer_body(target_raw=hostile, crlf=False), answer_body("003", hostile, crlf=False), answer_body("003", "②", hostile, crlf=False)):
                code, lines, net, github = self.ack(nth.answer_event(body=body))
                everything = json.dumps([lines, github.comments, net.bodies()], ensure_ascii=False)
                self.assertNotIn(hostile[:10], everything, hostile[:10])
                self.assertEqual(leaks(*lines, json.dumps(github.comments, ensure_ascii=False)), [])
        code, lines, net, github = self.ack(nth.answer_event(body=answer_body("003", "②", "비밀 " + nh.TOKEN)))
        self.assertEqual(leaks(*lines, json.dumps(github.comments, ensure_ascii=False), json.dumps(net.bodies(), ensure_ascii=False), chat=False), [])


class ThreeLineCandidateTest(th.NoOutbound, unittest.TestCase):
    """텔레그램에 보낸 세 줄 글(`대상번호: 001` / `선택: ②` / `내용: …`)은 이슈로 옮겨지고 '답변 후보(참고용)' 한 줄만 달린다 — 승인으로 읽지 않는다(G-S10)."""

    def parse(self, text):
        return ti.answer_candidate(ti.neutralize(text))

    def run_with(self, *updates):
        return th.run_inbox(th.FakeTelegram(list(updates)))

    def test_the_three_lines_are_read_into_a_candidate(self):
        text = "대상번호: 001\n선택: ②\n내용: 확인했습니다"
        self.assertEqual(self.parse(text), ti.ThreeLineCandidate("ask", "001", 2, False, len("확인했습니다"), ""))

    def test_only_the_target_is_needed_and_the_other_lines_may_be_missing_or_in_a_looser_shape(self):
        cases = {"대상번호: 001": ("ask", "001", 0, False, 0, ""), "대상번호:001": ("ask", "001", 0, False, 0, ""), "대상번호 : 003\n선택 : ①": ("ask", "003", 1, False, 0, ""),
                 "대상번호：003\n선택：③\n내용：전각 콜론": ("ask", "003", 3, False, len("전각 콜론"), ""), "  \n 대상번호: 001": ("ask", "001", 0, False, 0, ""),
                 "대상번호: 001\n선택: 선택 안 함": ("ask", "001", 0, False, 0, ""), "대상번호: 001\n선택: ⑥": ("ask", "001", 0, True, 0, ""),
                 "대상번호: 001\n내용: 첫 줄\n둘째 줄\n선택: ④": ("ask", "001", 0, False, len("첫 줄\n둘째 줄\n선택: ④"), ""), "대상번호: r149\n선택: ②": ("request", "R-149", 2, False, 0, ""),
                 "대상번호: 001\n선택: ②\n선택: ③": ("ask", "001", 2, False, 0, ""), "대상번호: 001\n아무 줄\n선택: ⑤": ("ask", "001", 5, False, 0, "")}
        for text, expected in cases.items():
            self.assertEqual(tuple(self.parse(text)), expected, repr(text))

    def test_the_memo_length_ignores_the_blank_space_around_it(self):
        """수정 1차(V3 T03): 내용 글자 수는 앞뒤 공백·빈 줄을 세지 않는다 — `strip()` 을 빼면 `내용: 확인 ` 뒤의 빈 줄까지 5자가 된다."""
        self.assertEqual(ti.three_line_candidate("대상번호: 001\n내용: 확인 \n\n").memo_chars, 2)
        self.assertEqual(ti.three_line_candidate("대상번호: 001\n내용:   \n  \n").memo_chars, 0)
        self.assertEqual(ti.three_line_candidate("대상번호: 001\n내용:  가  \n  나\n\n").memo_chars, len("가  \n  나"))

    def test_a_target_that_cannot_be_read_keeps_only_a_fixed_problem_code(self):
        for text, code in (("대상번호:", "empty"), ("대상번호: P012", "type"), ("대상번호: 001 002", "two"), ("대상번호: １２３", "format"), ("대상번호: 1", "short"), ("대상번호: 001 선택: ② 내용: 한 줄에", "format")):
            found = self.parse(text)
            self.assertEqual((found.target_kind, found.target, found.problem), ("", "", code), text)

    def test_texts_that_do_not_start_with_the_target_line_are_not_the_three_line_shape(self):
        for text in ("선택: ②\n대상번호: 001", "내용: 대상번호: 001", "그런데 대상번호: 001", "대상 번호: 001", "대상번호 001", "대상번호", "대상번호는 001입니다", "대상번호 :: 001x"):
            found = self.parse(text)
            self.assertFalse(isinstance(found, ti.ThreeLineCandidate) and not found.problem, text)
        self.assertIsNone(self.parse("선택: ②\n대상번호: 001"))

    def test_the_old_request_number_shape_is_read_as_before(self):
        self.assertEqual(self.parse("r103 승인 1"), ti.Candidate("R-103", "승인", "1", 0))
        self.assertEqual(self.parse("R-103"), ti.Candidate("R-103", "", "", 0))

    def test_the_candidate_line_for_each_case(self):
        self.assertEqual(ti.candidate_line(self.parse("대상번호: 001\n선택: ②\n내용: 확인했습니다")), "답변 후보(참고용): 확인 요청 **001** · 선택 **②** · 메모 있음(6자)")
        self.assertEqual(ti.candidate_line(self.parse("대상번호: 001")), "답변 후보(참고용): 확인 요청 **001** · 확인함 · 메모 없음")
        self.assertEqual(ti.candidate_line(self.parse("대상번호: 001\n선택: A")), "답변 후보(참고용): 확인 요청 **001** · 선택은 읽지 못했습니다 · 메모 없음")
        self.assertEqual(ti.candidate_line(self.parse("대상번호: r149\n선택: ②")), "답변 후보(참고용): 요청 **r149**(이전 R 번호) · 선택 **②** · 메모 없음")
        self.assertEqual(ti.candidate_line(self.parse("대상번호: P012")), f"답변 후보(참고용): 대상번호를 읽지 못했습니다 — {ol.TARGET_PROBLEMS['type']}")

    def test_the_candidate_line_is_in_the_issue_body_with_the_no_approval_note_and_nothing_else_happens(self):
        run = self.run_with(th.message_update(10, "대상번호: 001\n선택: ②\n내용: 확인했습니다"))
        [issue] = run.issues()
        body = issue["body"]
        self.assertIn("답변 후보(참고용): 확인 요청 **001** · 선택 **②** · 메모 있음(6자)", body)
        self.assertIn(ti.CANDIDATE_NOTE, body)
        self.assertIn("참고용이고 승인이 아닙니다", body)
        self.assertEqual(issue["title"], "[텔레그램] 대상번호: 001")
        self.assertEqual([(item["method"], item["path"]) for item in run.gh.requests], [("GET", "/issues"), ("POST", "/labels"), ("POST", "/issues")])
        self.assertEqual(run.tg.methods(), ["getUpdates", "sendMessage", "getUpdates"])
        self.assertNotIn("승인", run.tg.texts()[0].replace("승인은 [답하기] 양식으로", ""))

    def test_a_forwarded_three_line_text_gets_no_candidate(self):
        run = self.run_with(th.message_update(10, "대상번호: 001\n선택: ②", forward_origin={"type": "user"}))
        self.assertNotIn("답변 후보", run.issues()[0]["body"])

    def test_the_note_and_the_usage_text_name_the_new_rule(self):
        for needle in ("대상번호", "선택이 그 요청에 적힌 승인 보기와 같을 때만", "G-S9", "`[답하기]`", "`[답변]`"):
            self.assertIn(needle, ti.CANDIDATE_NOTE, needle)
        for needle in ("`대상번호: 001`", "001 같은 숫자", "r001 같은 번호", "승인이 아닙니다", "[답하기]", "접수만 합니다"):
            self.assertIn(needle, ti.USAGE_TEXT, needle)


class AnswerFormFileTest(unittest.TestCase):
    def form(self, name="ai-answer.yml"):
        return yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / name).read_text(encoding="utf-8"))

    def test_the_new_form_is_what_the_code_reads(self):
        data = self.form()
        self.assertEqual((data["name"], data["title"], data["labels"]), (ol.ANSWER_FORM_NAME, ol.REPLY_TITLE_PREFIX, [ol.LABEL_REPLY]))
        fields = {item["id"]: item for item in data["body"][1:]}
        self.assertEqual(list(fields), ["target", "choice", "memo"])
        self.assertEqual({field_id: item["attributes"]["label"] for field_id, item in fields.items()}, dict(ol.ANSWER_FIELDS))
        self.assertEqual({field_id: item["type"] for field_id, item in fields.items()}, ol.ANSWER_FIELD_TYPES)
        self.assertEqual({field_id for field_id, item in fields.items() if (item.get("validations") or {}).get("required")}, set(ol.ANSWER_REQUIRED))
        self.assertEqual(fields["choice"]["attributes"]["options"], list(ol.CHOICE_OPTIONS))
        self.assertEqual(fields["choice"]["attributes"]["default"], ol.CHOICE_DEFAULT_INDEX)
        self.assertEqual(fields["target"]["attributes"]["placeholder"], ol.TARGET_EXAMPLE)
        self.assertIn(ol.TARGET_EXAMPLE, fields["target"]["attributes"]["description"])

    def test_the_new_form_opens_with_the_secret_warning_the_owner_note_and_the_not_an_approval_sentences(self):
        notice = self.form()["body"][0]
        self.assertEqual(notice["type"], "markdown")
        value = notice["attributes"]["value"]
        for needle in (ol.FORM_NOTICE, "공개", "저장소 소유자 계정", ol.TARGET_NOTICE, ol.ANSWER_NOT_APPROVAL_NOTICE, "그 요청에 적힌 항목에 한해서만 유효합니다", "가장 나중 답이 이깁니다", "(이전 R 번호용)"):
            self.assertIn(needle, value, needle)

    def test_the_old_form_is_kept_with_the_old_number_mark_in_its_menu_name(self):
        data = self.form("ai-reply.yml")
        self.assertEqual(data["name"], ol.REPLY_FORM_NAME)
        self.assertTrue(data["name"].endswith("(이전 R 번호용)"))
        self.assertEqual((data["title"], data["labels"]), (ol.REPLY_TITLE_PREFIX, [ol.LABEL_REPLY]))
        self.assertIn("이전 방식", data["description"])
        self.assertIn("이전 방식(R 번호", data["body"][0]["attributes"]["value"])
        self.assertNotEqual(data["name"], self.form()["name"])

    def test_the_rendered_body_of_every_option_is_read_back_by_the_parser(self):
        data = self.form()
        fields = {item["id"]: item for item in data["body"][1:]}
        for option in fields["choice"]["attributes"]["options"]:
            body = (f"### {fields['target']['attributes']['label']}\n\n007\n\n### {fields['choice']['attributes']['label']}\n\n{option}\n\n"
                    f"### {fields['memo']['attributes']['label']}\n\n_No response_")
            result = ol.parse_reply(data["title"] + "x", body, OWNER, "OWNER", OWNER)
            self.assertEqual((result.kind, result.target, ol.CHOICE_OPTIONS[result.choice_no]), ("answer", "007", option))

    def test_the_two_answer_forms_share_the_title_and_the_label_so_the_ai_reading_procedure_is_unchanged(self):
        self.assertEqual((self.form()["title"], self.form()["labels"]), (self.form("ai-reply.yml")["title"], self.form("ai-reply.yml")["labels"]))
        readme = (ROOT / ol.REQUEST_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"labels={ol.LABEL_REPLY}", readme)

    def test_the_form_rule_FORM_1_passes_for_the_real_files_and_catches_changes_to_the_new_form(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import validate_repo as vr
        files = [vr.REPLY_FORM, vr.ANSWER_FORM, vr.TASK_FORM, vr.ISSUE_CONFIG]
        self.assertEqual([finding.line() for finding in vr.check_operator_forms(ROOT, files)], [])
        self.assertEqual(vr.ANSWER_FORM, ".github/ISSUE_TEMPLATE/ai-answer.yml")


if __name__ == "__main__":
    unittest.main()
