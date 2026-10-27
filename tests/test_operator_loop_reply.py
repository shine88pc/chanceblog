"""운영자 요청함 — 운영자의 응답 이슈를 접수 확인하는 쪽(python -m pipeline.operator_loop ack) 시험.

응답 파서(비소유자 거절·`author_association` 위조 시도·양식 모양 틀림·요청 번호 정규식·선택지 밖 값·메모에 `$(…)`·`::set-output`·`@멘션`·`#123`·HTML·긴 글) ·
접수 코멘트(멱등·봇이 단 표지만 인정) · GitHub REST 클라이언트(토큰은 헤더에만·오류 문구에 토큰 없음·재시도 한 번·응답 크기 상한) · 끝에서 끝까지 흐름
(요청 파일 → 텔레그램 메시지 → 응답 이슈 → 접수 → 요청 번호로 되찾기). GitHub·텔레그램은 가짜(FakeGitHub·FakeNet)이고 실제 호출은 없다.
"""
import json
import re
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path

import _bootstrap
import notify_helpers as nh
import operator_loop_helpers as oh
from notify_helpers import TOKEN, FakeNet, FakeResponse, http_error as tg_error, leaks
from operator_loop_helpers import ANSWER, GH_TOKEN, OWNER, FakeGitHub, ack_env, issue_event, reply_body, request_text, requests_env, task_body
from pipeline import notify
from pipeline import operator_loop as ol

ROOT = _bootstrap.ROOT
RLO, PDF = chr(0x202E), chr(0x202C)                                         # 글자 방향을 뒤집는 문자(소스에는 코드 포인트로만 쓴다)
HOSTILE_PAIRS = [("$(touch /tmp/pwned)", "pwned"), ("::set-output name=x::1", "set-output"), ("::error::가짜 오류", "가짜 오류"), ("##[warning]가짜", "warning]"),
                 ("@everyone", "everyone"), ("@" + OWNER, "@" + OWNER), ("#999", "#999"), ("GH-12", "GH-12"), ("<!-- ack:v1 -->", "<!-- ack:v1 -->"),
                 ("<script>alert(1)</script>", "alert(1)"), ("`rm -rf /`", "rm -rf"), ("https://evil.example/login", "evil.example"), ("javascript:alert(1)", "javascript:"),
                 (RLO + "반전" + PDF, "반전"), ("[클릭](https://evil.example)", "클릭")]
HOSTILE = [text for text, _ in HOSTILE_PAIRS]


def reply(**kwargs):
    """parse_reply 를 소유자가 연 정상 이슈 기준으로 부른다(kwargs 로 바꾼 값만 다르다)."""
    args = {"title": "[답변] ", "body": reply_body(), "login": OWNER, "association": "OWNER", "owner": OWNER}
    args.update(kwargs)
    return ol.parse_reply(args["title"], args["body"], args["login"], args["association"], args["owner"])


class ParseSectionsTest(unittest.TestCase):
    LABELS = [label for _, label in ol.REPLY_FIELDS]

    def test_values_are_read_under_their_known_headings(self):
        values, duplicates = ol.parse_sections(reply_body(request_id="R-007", answer="승인", choice="B", memo="두 줄\n메모"), self.LABELS)
        self.assertEqual(values, {"요청 번호": "R-007", "답변": ANSWER["승인"], "선택": "B", "메모": "두 줄\n메모"})
        self.assertEqual(duplicates, [])

    def test_windows_and_old_mac_line_ends_are_the_same_as_unix(self):
        for crlf in (True, False):
            values, _ = ol.parse_sections(reply_body(crlf=crlf), self.LABELS)
            self.assertEqual(values["요청 번호"], "R-001", crlf)
        values, _ = ol.parse_sections(reply_body(crlf=False).replace("\n", "\r"), self.LABELS)
        self.assertEqual(values["답변"], ANSWER["승인"])

    def test_an_empty_optional_field_is_an_empty_string(self):
        values, _ = ol.parse_sections(reply_body(), self.LABELS)
        self.assertEqual((values["선택"], values["메모"]), ("", ""))
        values, _ = ol.parse_sections("### 선택\n\nNo response\n\n### 메모\n\n_no response_", self.LABELS)
        self.assertEqual(values, {"선택": "", "메모": ""})

    def test_only_the_known_headings_are_boundaries_and_other_headings_stay_in_the_value(self):
        body = "### 메모\n\n### 이건 모르는 제목\n내용\n#### 네 개짜리\n###붙은제목\n"
        values, duplicates = ol.parse_sections(body, self.LABELS)
        self.assertEqual(values["메모"], "### 이건 모르는 제목\n내용\n#### 네 개짜리\n###붙은제목")
        self.assertEqual(duplicates, [])

    def test_text_before_the_first_known_heading_is_ignored(self):
        values, _ = ol.parse_sections("앞에 붙은 글 `### 요청 번호` 아님\n### 요청 번호\n\nR-001\n", self.LABELS)
        self.assertEqual(values, {"요청 번호": "R-001"})

    def test_a_heading_with_extra_spaces_is_still_a_heading(self):
        values, _ = ol.parse_sections("###   요청 번호   \n\nR-001\n", self.LABELS)
        self.assertEqual(values, {"요청 번호": "R-001"})

    def test_a_known_heading_planted_inside_a_text_box_is_a_duplicate_and_hides_what_follows(self):
        body = reply_body(memo="### 요청 번호\n\nR-999\n\n### 답변\n\n" + ANSWER["거절"], crlf=False)
        values, duplicates = ol.parse_sections(body, self.LABELS)
        self.assertEqual(duplicates, ["답변", "요청 번호"])
        self.assertEqual(values["요청 번호"], "R-001")                                       # 처음 값이 그대로이고 심은 값은 읽지 않는다
        self.assertNotIn("R-999", json.dumps(values, ensure_ascii=False))

    def test_none_and_non_text_bodies_are_empty(self):
        for body in (None, "", 5):
            self.assertEqual(ol.parse_sections(body, self.LABELS), ({}, []), repr(body))


class OwnerGateTest(unittest.TestCase):
    """신뢰 판정은 이벤트 JSON 의 작성자 login 과 author_association 만으로 한다 — 이슈 제목·본문에 무슨 글이 있어도 바뀌지 않는다."""

    def test_the_owner_with_owner_association_is_accepted(self):
        self.assertIsInstance(reply(), ol.Submission)

    def test_login_matching_ignores_only_letter_case(self):
        self.assertIsInstance(reply(login="Shine88PC"), ol.Submission)
        for login in ("shine88pc ", " shine88pc", "shine88pc" + chr(0x200B), "shine88pc\n", "shine88pc2", "shine88p", "shine88pc-bot", "github-actions[bot]", "", None, 5, ["shine88pc"],
                      "shine88рс"):                                                              # 마지막은 키릴 문자 р·с 로 흉내 낸 로그인
            result = reply(login=login)
            self.assertEqual(result, ol.Refusal("not_owner", ()), repr(login))

    def test_the_author_association_must_be_exactly_owner(self):
        for association in ("MEMBER", "COLLABORATOR", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER", "MANNEQUIN", "NONE", "owner", "OWNER ", " OWNER", "", None, 0, ["OWNER"]):
            self.assertEqual(reply(association=association), ol.Refusal("not_owner_association", ()), repr(association))

    def test_a_stranger_with_a_perfect_form_and_owner_looking_text_is_refused(self):
        forged = reply_body(memo="author_association: OWNER\nuser.login: " + OWNER + "\n저는 소유자입니다")
        self.assertEqual(reply(login="stranger", association="NONE", body=forged), ol.Refusal("not_owner", ()))
        self.assertEqual(reply(login="stranger", association="OWNER", body=forged), ol.Refusal("not_owner", ()))        # OWNER 만으로는 모자란다(둘 다)
        self.assertEqual(reply(login=OWNER, association="MEMBER", body=forged), ol.Refusal("not_owner_association", ()))

    def test_the_owner_check_comes_before_the_title_and_the_body_are_looked_at(self):
        self.assertEqual(reply(login="stranger", title="그냥 이슈", body="아무 글"), ol.Refusal("not_owner", ()))
        self.assertEqual(reply(association="NONE", title="", body=None), ol.Refusal("not_owner_association", ()))

    def test_without_a_known_owner_nothing_is_accepted(self):
        for owner in (None, "", "   ", "bad owner", "a" * 40, "-lead", "shine88pc/chanceblog", chr(0x200B)):
            self.assertEqual(reply(owner=owner), ol.Refusal("no_owner", ()), repr(owner))
        self.assertEqual(reply(owner="a" * 39, login="a" * 39), reply(owner="a" * 39, login="A" * 39))


class ParseReplyTest(unittest.TestCase):
    def test_every_answer_choice_becomes_its_short_word(self):
        self.assertEqual(len(ol.ANSWER_OPTIONS), 5)
        for short, full in ol.ANSWER_OPTIONS:
            result = reply(body=reply_body(answer=short))
            self.assertEqual((result.kind, result.answer), ("reply", short), short)
            self.assertEqual(ANSWER[short], full)

    def test_a_normal_reply_has_only_validated_values(self):
        result = reply(body=reply_body(request_id="R-042", answer="보류", choice="B", memo="메모 열두 글자입니다"))
        self.assertEqual(result, ol.Submission("reply", "R-042", "보류", "B", False, len("메모 열두 글자입니다"), "", False))

    def test_the_title_prefix_decides_the_form(self):
        self.assertEqual(reply(title="[답변] 아무 글").kind, "reply")
        self.assertEqual(reply(title="[답변]").kind, "reply")
        self.assertEqual(reply(title="[요청] 일", body=task_body()).kind, "task")
        for title in ("", None, "답변", " [답변]", "[ANSWER]", "[답 변]", "[페이지 수정] x", "[이미지 변경] x", "[운영] 확인 필요 모음", "x [답변]", "(답변)", "[답변 ]x"):
            self.assertEqual(reply(title=title), ol.Refusal("not_form", ()), repr(title))

    def test_the_request_number_must_be_r_and_three_digits(self):
        for good in ("R-001", "R-999", "R-000"):
            self.assertEqual(reply(body=reply_body(request_id=good)).request_id, good)
        for bad in ("R-1", "R-0001", "r-001", "R_001", "R-001 extra", "R-001\nR-002", "001", "R-00a", "#R-001", "R-001.", "R−001"):
            result = reply(body=reply_body(request_id=bad, crlf=False))
            self.assertEqual(result.code, "bad_shape", repr(bad))
            self.assertEqual(result.problems, ("`요청 번호` 값이 `R-001` 처럼 `R-` 와 숫자 세 자리가 아닙니다",), repr(bad))

    def test_an_answer_outside_the_forms_choices_is_a_shape_problem(self):
        for bad in ("승인", "승인 — 제안한 대로 진행해 주세요!", "승인 - 제안한 대로 진행해 주세요", "APPROVE", "승인 — 제안한 대로 진행해 주세요\n거절 — 하지 마세요", "<script>", "",
                    "승인 — 제안한 대로 진행해 주세요 ", "승인  — 제안한 대로 진행해 주세요"):
            if bad.endswith(" ") and bad.strip() == ANSWER["승인"]:
                continue                                                                          # 앞뒤 공백은 봐준다(아래에서 따로 확인)
            result = reply(body=reply_body(raw_answer=bad, crlf=False))
            self.assertEqual(result, ol.Refusal("bad_shape", ("`답변` 값이 양식의 선택지가 아닙니다",)), repr(bad))
        self.assertEqual(reply(body=reply_body(answer="승인", crlf=False).replace(ANSWER["승인"], ANSWER["승인"] + "  ")).answer, "승인")     # 앞뒤 공백은 봐준다

    def test_a_missing_required_heading_is_named(self):
        no_id = reply_body().replace("### 요청 번호", "### 번호")
        self.assertEqual(reply(body=no_id), ol.Refusal("bad_shape", ("`요청 번호` 항목이 없습니다",)))
        no_answer = reply_body().replace("### 답변", "### 대답")                                       # 모르는 제목 아래의 글은 앞 항목의 값으로 들어간다
        self.assertEqual(reply(body=no_answer), ol.Refusal("bad_shape", ("`답변` 항목이 없습니다", "`요청 번호` 값이 `R-001` 처럼 `R-` 와 숫자 세 자리가 아닙니다")))
        only_answer = "### 요청 번호\n\nR-001\n"
        self.assertEqual(reply(body=only_answer), ol.Refusal("bad_shape", ("`답변` 항목이 없습니다",)))
        both = reply(body="아무 글만 있는 본문")
        self.assertEqual(both, ol.Refusal("bad_shape", ("`요청 번호` 항목이 없습니다", "`답변` 항목이 없습니다")))
        self.assertEqual(reply(body=None), both)
        self.assertEqual(reply(body=""), both)

    def test_optional_headings_may_be_missing(self):
        short = "### 요청 번호\n\nR-001\n\n### 답변\n\n" + ANSWER["거절"]
        result = reply(body=short)
        self.assertEqual((result.answer, result.choice, result.memo_chars), ("거절", "", 0))

    def test_a_planted_heading_in_the_memo_makes_the_whole_form_wrong(self):
        body = reply_body(memo="### 요청 번호\n\nR-999", crlf=False)
        self.assertEqual(reply(body=body), ol.Refusal("bad_shape", ("`요청 번호` 항목이 두 번 나옵니다",)))
        body = reply_body(memo="### 메모\n\n다시", crlf=False)
        self.assertEqual(reply(body=body), ol.Refusal("bad_shape", ("`메모` 항목이 두 번 나옵니다",)))

    def test_the_choice_is_one_to_three_letters_digits_or_hangul_and_anything_else_is_marked_invalid(self):
        for good, shown in (("B", "B"), ("b", "b"), ("1", "1"), ("12", "12"), ("가", "가"), ("A1", "A1"), ("B.", "B"), ("B)", "B"), ("  C  ", "C"), ("ABC", "ABC"), ("나다라", "나다라")):
            result = reply(body=reply_body(choice=good))
            self.assertEqual((result.choice, result.choice_invalid), (shown, False), repr(good))
        for bad in ("ABCD", "A B", "$(id)", "B; rm", "<b>", "@B", "#1", "https://x.example", "B\nC", "A-B", "::x", chr(0x200B) + "B" + chr(0x200B), "ＢＣ", "1234"):
            result = reply(body=reply_body(choice=bad, crlf=False))
            self.assertEqual((result.choice, result.choice_invalid), ("", True), repr(bad))
        self.assertEqual(reply(body=reply_body(choice="")).choice_invalid, False)                               # 비워 둔 것은 잘못이 아니다

    def test_the_memo_is_only_counted_never_kept(self):
        for memo in HOSTILE + ["가" * 70000, "줄\n" * 5000]:
            result = reply(body=reply_body(memo=memo, crlf=False))
            self.assertEqual(result.memo_chars, len(memo.strip()), memo[:20])
            self.assertEqual(sum(1 for field in result if isinstance(field, str) and memo[:6] in field and memo[:6].strip()), 0, memo[:20])

    def test_hostile_text_in_the_title_never_reaches_the_result(self):
        for hostile in HOSTILE:
            result = reply(title="[답변] " + hostile)
            self.assertEqual(result.kind, "reply")
            self.assertNotIn(hostile, "".join(str(field) for field in result), hostile)

    def test_a_task_request_reads_what_urgency_and_approval(self):
        result = reply(title="[요청] ", body=task_body(what="PR 정리", done="끝 기준", urgency="급함", approval="예 — 위 내용에 적은 항목에 한해 승인합니다(T3 포함)"))
        self.assertEqual(result, ol.Submission("task", "", "", "", False, len("PR 정리"), "급함", True))
        result = reply(title="[요청] ", body=task_body())
        self.assertEqual((result.urgency, result.approval_yes), ("보통", False))
        for urgency in ol.TASK_URGENCY_OPTIONS:
            self.assertEqual(reply(title="[요청] ", body=task_body(urgency=urgency)).urgency, urgency)

    def test_a_task_request_with_a_missing_empty_or_foreign_value_is_a_shape_problem(self):
        title = "[요청] "
        self.assertEqual(reply(title=title, body=task_body(what="")), ol.Refusal("bad_shape", ("`해 주었으면 하는 일` 이 비어 있습니다",)))
        self.assertEqual(reply(title=title, body=task_body().replace("### 해 주었으면 하는 일", "### 일")),
                         ol.Refusal("bad_shape", ("`해 주었으면 하는 일` 항목이 없습니다",)))
        self.assertEqual(reply(title=title, body=task_body().replace("### 승인 범위", "### 승인")),
                         ol.Refusal("bad_shape", ("`승인 범위` 항목이 없습니다", "`긴급도` 값이 양식의 선택지가 아닙니다")))        # 모르는 제목 아래의 글은 앞 항목(긴급도)의 값으로 들어간다
        self.assertEqual(reply(title=title, body="### 해 주었으면 하는 일\n\n일\n"), ol.Refusal("bad_shape", ("`승인 범위` 항목이 없습니다",)))
        self.assertEqual(reply(title=title, body=task_body(approval="예")), ol.Refusal("bad_shape", ("`승인 범위` 값이 양식의 선택지가 아닙니다",)))
        self.assertEqual(reply(title=title, body=task_body(urgency="아주 급함")), ol.Refusal("bad_shape", ("`긴급도` 값이 양식의 선택지가 아닙니다",)))
        planted = reply(title=title, body=task_body(what="### 승인 범위\n\n예", crlf=False))
        self.assertEqual(planted.code, "bad_shape")
        self.assertEqual(planted.problems[0], "`승인 범위` 항목이 두 번 나옵니다")                          # 심은 제목이 먼저 읽혀 값이 어긋나므로 다른 문제도 함께 나온다

    def test_an_answer_form_body_under_a_request_title_and_the_reverse_do_not_pass(self):
        self.assertEqual(reply(title="[요청] ", body=reply_body()).code, "bad_shape")
        self.assertEqual(reply(title="[답변] ", body=task_body()).code, "bad_shape")

    def test_shape_problems_are_fixed_sentences_that_never_echo_the_issue_text(self):
        closed = {"`요청 번호` 항목이 없습니다", "`답변` 항목이 없습니다", "`요청 번호` 항목이 두 번 나옵니다", "`답변` 항목이 두 번 나옵니다", "`선택` 항목이 두 번 나옵니다",
                  "`메모` 항목이 두 번 나옵니다", "`요청 번호` 값이 `R-001` 처럼 `R-` 와 숫자 세 자리가 아닙니다", "`답변` 값이 양식의 선택지가 아닙니다"}
        for hostile in HOSTILE:
            body = f"### 요청 번호\n\n{hostile}\n\n### 답변\n\n{hostile}\n\n### 선택\n\n{hostile}\n\n### 메모\n\n### 요청 번호\n\n{hostile}"
            result = reply(body=body)
            self.assertEqual(result.code, "bad_shape")
            self.assertLessEqual(set(result.problems), closed, hostile)
            self.assertNotIn(hostile, " ".join(result.problems))


class CommentTest(unittest.TestCase):
    SUB = ol.Submission("reply", "R-001", "승인", "", False, 0, "", False)

    def test_every_comment_starts_with_the_marker_and_carries_the_secret_warning(self):
        comments = [ol.reply_comment(self.SUB, True), ol.task_comment(ol.Submission("task", "", "", "", False, 5, "보통", False)), ol.shape_comment(("문제",))]
        for text in comments:
            self.assertTrue(text.startswith(ol.ACK_MARK + "\n"), text[:30])
        for text in comments[:2]:
            self.assertIn("비밀번호·토큰·키 값은 이 이슈에 쓰지 마세요", text)
            self.assertIn("AI 세션이 이 이슈를 감시해 이어서 진행하며 결과는 텔레그램으로 알립니다. (AI 가 켜져 있지 않으면 다음 세션에서 처리됩니다)", text)

    def test_the_reply_comment_names_the_request_the_answer_and_the_choice(self):
        text = ol.reply_comment(self.SUB._replace(choice="B"), True)
        self.assertEqual(text.splitlines()[1], "접수했습니다 — 요청 **R-001** · 답: **승인** · 선택: **B**.")
        self.assertEqual(ol.reply_comment(self.SUB, True).splitlines()[1], "접수했습니다 — 요청 **R-001** · 답: **승인**.")

    def test_notes_appear_only_when_they_apply(self):
        plain = ol.reply_comment(self.SUB, True)
        for needle in ("메모:", "알 수 없는 요청 번호", "선택 칸의 값이"):
            self.assertNotIn(needle, plain, needle)
        self.assertIn("- 메모: 있음(120자) — AI 가 이슈 본문에서 읽습니다(여기에는 되풀이하지 않습니다).", ol.reply_comment(self.SUB._replace(memo_chars=120), True))
        self.assertIn("- 선택 칸의 값이 형식(영문·숫자·한글 1~3자)에 맞지 않아 표시하지 않았습니다.", ol.reply_comment(self.SUB._replace(choice_invalid=True), True))
        unknown = ol.reply_comment(self.SUB, False)
        self.assertIn("- 알 수 없는 요청 번호: 저장소의 `인수인계/요청함/` 에서 R-001 파일을 찾지 못했습니다", unknown)
        self.assertIn("접수는 했습니다.", unknown)

    def test_the_task_comment_shows_urgency_and_the_approval_scope(self):
        text = ol.task_comment(ol.Submission("task", "", "", "", False, 5, "급함", True))
        self.assertEqual(text.splitlines()[1], "접수했습니다 — 새 일 요청 · 긴급도: **급함** · 승인 범위: **있음(T3 포함)**.")
        self.assertIn("승인은 이슈 본문에 적은 항목에만 유효합니다", text)
        plain = ol.task_comment(ol.Submission("task", "", "", "", False, 5, "보통", False))
        self.assertEqual(plain.splitlines()[1], "접수했습니다 — 새 일 요청 · 긴급도: **보통** · 승인 범위: **논의·준비까지만**.")
        self.assertNotIn("승인은 이슈 본문에 적은 항목에만", plain)

    def test_the_shape_comment_lists_the_fixed_problems_and_points_to_the_forms(self):
        text = ol.shape_comment(("`요청 번호` 항목이 없습니다", "`답변` 항목이 없습니다"))
        self.assertIn("양식 모양이 달라 처리하지 못했습니다 — `요청 번호` 항목이 없습니다; `답변` 항목이 없습니다.", text)
        self.assertIn("빈 이슈나 양식 밖의 글은 승인으로 보지 않습니다", text)


class GitHubClientTest(unittest.TestCase):
    def client(self, *outcomes, token=GH_TOKEN, repo=oh.REPO):
        github = FakeGitHub(failures=[("GET", "/x", outcome) for outcome in outcomes])
        clock = nh.Clock()
        return ol.GitHub(repo, token, opener=lambda request, timeout=None: github(request, timeout), sleep=clock.sleep), github, clock

    def test_the_token_goes_only_in_the_authorization_header(self):
        api, github, _ = self.client(FakeResponse(200, {"ok": 1}))
        self.assertEqual(api.request("GET", "/x", params={"per_page": 100}), {"ok": 1})
        sent = github.requests[0]
        self.assertEqual(sent["headers"]["Authorization"], f"Bearer {GH_TOKEN}")
        self.assertEqual((sent["method"], sent["path"], sent["query"], sent["timeout"]), ("GET", "/x", "per_page=100", ol.API_TIMEOUT))
        self.assertEqual(sent["headers"]["Accept"], "application/vnd.github+json")
        self.assertEqual(sent["headers"]["User-agent"], "chanceblog-operator-loop")
        self.assertNotIn(GH_TOKEN, json.dumps({key: value for key, value in sent.items() if key != "headers"}))

    def test_a_body_is_json_with_a_content_type_and_an_empty_response_is_none(self):
        github = FakeGitHub()
        api = ol.GitHub(oh.REPO, GH_TOKEN, opener=github)
        api.request("POST", "/issues/5/comments", payload={"body": "글"})
        self.assertEqual(github.requests[0]["payload"], {"body": "글"})
        self.assertEqual(github.requests[0]["headers"]["Content-type"], "application/json")
        api, _, _ = self.client(FakeResponse(204, b""))
        self.assertIsNone(api.request("GET", "/x"))

    def test_http_errors_become_a_short_message_with_the_status_and_no_token(self):
        for status, text in ((404, "Not Found"), (403, "Resource not accessible by integration"), (422, "Validation Failed"), (401, "Bad credentials")):
            api, _, _ = self.client(oh.http_error(status, text))
            with self.assertRaises(ol.GitHubError) as caught:
                api.request("GET", "/x")
            self.assertEqual((caught.exception.status, str(caught.exception)), (status, f"HTTP {status}: {text}"))

    def test_the_token_inside_githubs_message_and_workflow_command_text_are_neutralised(self):
        api, _, _ = self.client(oh.http_error(400, f"bad {GH_TOKEN} ::error::x\nnext ##[warning]"))
        with self.assertRaises(ol.GitHubError) as caught:
            api.request("GET", "/x")
        shown = str(caught.exception)
        self.assertNotIn(GH_TOKEN, shown)
        self.assertNotIn("::", shown)
        self.assertNotIn("##[", shown)
        self.assertEqual(len(shown.splitlines()), 1)
        self.assertTrue(shown.startswith("HTTP 400: bad ***"))

    def test_a_long_error_message_is_cut(self):
        api, _, _ = self.client(oh.http_error(422, "가" * 1000))
        with self.assertRaises(ol.GitHubError) as caught:
            api.request("GET", "/x")
        self.assertLessEqual(len(str(caught.exception)), len("HTTP 422: ") + 120)

    def test_a_transient_failure_is_retried_once_after_a_short_wait(self):
        for status in (429, 500, 502, 503, 504):
            api, github, clock = self.client(oh.http_error(status, "boom"), FakeResponse(200, {"ok": 1}))
            self.assertEqual(api.request("GET", "/x"), {"ok": 1}, status)
            self.assertEqual((len(github.requests), clock.sleeps), (2, [ol.RETRY_WAIT]), status)

    def test_a_rate_limit_403_is_retried_but_a_permission_403_is_not(self):
        api, github, _ = self.client(oh.http_error(403, "API rate limit exceeded"), FakeResponse(200, {"ok": 1}))
        self.assertEqual(api.request("GET", "/x"), {"ok": 1})
        api, github, _ = self.client(oh.http_error(403, "Resource not accessible by integration"), FakeResponse(200, {"ok": 1}))
        with self.assertRaises(ol.GitHubError):
            api.request("GET", "/x")
        self.assertEqual(len(github.requests), 1)

    def test_other_client_errors_are_not_retried(self):
        for status in (400, 401, 404, 410, 422):
            api, github, clock = self.client(oh.http_error(status, "no"), FakeResponse(200, {"ok": 1}))
            with self.assertRaises(ol.GitHubError):
                api.request("GET", "/x")
            self.assertEqual((len(github.requests), clock.sleeps), (1, []), status)

    def test_a_second_failure_is_raised_and_there_is_no_third_try(self):
        api, github, _ = self.client(oh.http_error(502, "a"), oh.http_error(503, "b"), FakeResponse(200, {"ok": 1}))
        with self.assertRaises(ol.GitHubError) as caught:
            api.request("GET", "/x")
        self.assertEqual((len(github.requests), caught.exception.status), (2, 503))

    def test_retry_false_sends_the_request_exactly_once(self):
        api, github, clock = self.client(oh.http_error(502, "a"), FakeResponse(200, {"ok": 1}))
        with self.assertRaises(ol.GitHubError):
            api.request("GET", "/x", retry=False)
        self.assertEqual((len(github.requests), clock.sleeps), (1, []))

    def test_connection_errors_are_retried_once_and_named_by_class_only(self):
        for error in (urllib.error.URLError("https://api.github.com/x?token=" + GH_TOKEN), socket.timeout("timed out " + GH_TOKEN), ConnectionResetError(GH_TOKEN)):
            api, github, _ = self.client(error, error)
            with self.assertRaises(ol.GitHubError) as caught:
                api.request("GET", "/x")
            self.assertEqual(len(github.requests), 2)
            self.assertEqual(str(caught.exception), f"연결 오류({type(error).__name__})")
            self.assertIsNone(caught.exception.status)
            self.assertNotIn(GH_TOKEN, repr(caught.exception))
            self.assertIsNone(caught.exception.__cause__)

    def test_a_connection_error_followed_by_success_is_fine(self):
        api, github, _ = self.client(urllib.error.URLError("x"), FakeResponse(200, {"ok": 1}))
        self.assertEqual(api.request("GET", "/x"), {"ok": 1})

    def test_an_oversized_or_non_json_response_is_an_error(self):
        api, _, _ = self.client(FakeResponse(200, b"x" * (ol.MAX_API_BYTES + 1)))
        with self.assertRaises(ol.GitHubError) as caught:
            api.request("GET", "/x")
        self.assertEqual(str(caught.exception), "응답이 너무 큽니다")
        for raw in (b"<html>", b"{", "[" * 100000):
            api, _, _ = self.client(FakeResponse(200, raw))
            with self.assertRaises(ol.GitHubError) as caught:
                api.request("GET", "/x")
            self.assertEqual(str(caught.exception), "응답이 JSON 이 아닙니다")

    def test_a_repository_name_of_the_wrong_shape_is_refused_before_any_call(self):
        for repo in ("", "noslash", "a/b/c", "a b/c", "../x", "x/..", "x/.", "-x/y", None, "a" * 40 + "/y"):
            api, github, _ = self.client(repo=repo)
            with self.assertRaises(ol.GitHubError):
                api.request("GET", "/x")
            self.assertEqual(github.requests, [], repr(repo))


class PostAckTest(unittest.TestCase):
    def setup(self, comments=None, failures=()):
        github = FakeGitHub(comments=comments, failures=failures)
        clock = nh.Clock()
        return ol.GitHub(oh.REPO, GH_TOKEN, opener=github, sleep=clock.sleep), github, clock

    def bot(self, body):
        return {"user": {"login": ol.BOT_LOGIN}, "body": body}

    def test_the_first_ack_is_posted_after_reading_the_comments(self):
        api, github, _ = self.setup()
        self.assertTrue(ol.post_ack(api, 12, ol.ACK_MARK + "\n접수"))
        self.assertEqual([(item["method"], item["path"]) for item in github.requests], [("GET", "/issues/12/comments"), ("POST", "/issues/12/comments")])
        self.assertEqual(github.requests[0]["query"], "per_page=100")
        self.assertEqual(github.posted(12), [ol.ACK_MARK + "\n접수"])

    def test_an_ack_the_bot_already_posted_is_not_posted_again(self):
        api, github, _ = self.setup(comments={12: [self.bot(ol.ACK_MARK + "\n접수")]})
        self.assertFalse(ol.post_ack(api, 12, ol.ACK_MARK + "\n접수"))
        self.assertEqual(github.writes(), [])

    def test_only_the_bots_own_comment_that_starts_with_the_marker_counts(self):
        stranger = {"user": {"login": "stranger"}, "body": ol.ACK_MARK + "\n나도 접수"}
        owner = {"user": {"login": OWNER}, "body": ol.ACK_MARK + "\n소유자가 쓴 표지"}
        buried = self.bot("앞에 글이 있고 " + ol.ACK_MARK)
        lookalike = {"user": {"login": "github-actions"}, "body": ol.ACK_MARK}
        empty = {"user": None, "body": None}
        for comment in (stranger, owner, buried, lookalike, empty, "문자열", None):
            api, github, _ = self.setup(comments={12: [comment]})
            self.assertTrue(ol.post_ack(api, 12, ol.ACK_MARK + "\n접수"), comment)
            self.assertEqual(len(github.writes()), 1)

    def test_a_failed_comment_list_does_not_stop_the_ack(self):
        api, github, _ = self.setup(failures=[("GET", "/comments", oh.http_error(500, "x")), ("GET", "/comments", oh.http_error(500, "x"))])
        self.assertTrue(ol.post_ack(api, 12, ol.ACK_MARK + "\n접수"))                              # 중복이 접수 누락보다 낫다
        self.assertEqual(len(github.writes()), 1)

    def test_a_refused_post_is_raised_and_not_retried(self):
        for status in (401, 403, 404, 410, 422):
            api, github, clock = self.setup(failures=[("POST", "/comments", oh.http_error(status, "no"))])
            with self.assertRaises(ol.GitHubError) as caught:
                ol.post_ack(api, 12, ol.ACK_MARK + "\n접수", sleep=clock.sleep)
            self.assertEqual(caught.exception.status, status)
            self.assertEqual((len(github.calls("POST")), len(github.calls("GET")), clock.sleeps), (1, 1, []), status)       # 만들어지지 않았음이 확실하니 다시 읽지도 않는다

    def test_when_the_response_is_lost_but_the_comment_was_made_it_counts_as_posted_and_is_not_made_twice(self):
        for outcome in (oh.http_error(502, "bad gateway"), urllib.error.URLError("reset"), oh.http_error(429, "slow down"), oh.http_error(500, "x")):
            api, github, clock = self.setup(failures=[("POST", "/comments", outcome, True)])
            self.assertTrue(ol.post_ack(api, 12, ol.ACK_MARK + "\n접수", sleep=clock.sleep), outcome)
            self.assertEqual(len(github.posted(12)), 1, outcome)
            self.assertEqual(len(github.calls("POST")), 1, outcome)
            self.assertEqual(clock.sleeps, [ol.RETRY_WAIT], outcome)

    def test_when_the_response_is_lost_and_no_comment_exists_the_error_is_raised_without_a_second_post(self):
        api, github, clock = self.setup(failures=[("POST", "/comments", oh.http_error(502, "bad gateway"))])
        with self.assertRaises(ol.GitHubError):
            ol.post_ack(api, 12, ol.ACK_MARK + "\n접수", sleep=clock.sleep)
        self.assertEqual((len(github.calls("POST")), github.posted(12)), (1, []))

    def test_when_the_response_is_lost_and_the_recheck_also_fails_the_error_is_raised(self):
        api, github, clock = self.setup(failures=[("GET", "/comments", FakeResponse(200, [])), ("POST", "/comments", oh.http_error(502, "x"), True),
                                                  ("GET", "/comments", oh.http_error(500, "x")), ("GET", "/comments", oh.http_error(500, "x"))])
        # 처음 읽기는 비어 있어 만들기가 나가고(서버는 만들었지만 응답을 잃음), 그 뒤의 다시 읽기가 두 번 실패하면 확인하지 못한 채 원래 오류를 올린다(다시 만들지 않는다)
        with self.assertRaises(ol.GitHubError) as caught:
            ol.post_ack(api, 12, ol.ACK_MARK + "\n접수", sleep=clock.sleep)
        self.assertEqual((len(github.calls("POST")), caught.exception.status), (1, 502))

    def test_ensure_label_creates_once_and_treats_an_existing_label_as_done(self):
        api, github, _ = self.setup()
        ol.ensure_label(api, ol.LABEL_REPLY)
        ol.ensure_label(api, ol.LABEL_REPLY)
        self.assertEqual(github.labels, {ol.LABEL_REPLY})
        self.assertEqual(github.requests[0]["payload"], {"name": "운영자응답", "color": "1d76db", "description": "운영자가 AI 의 요청에 답한 이슈(양식 [답변])"})
        api, github, _ = self.setup(failures=[("POST", "/labels", oh.http_error(403, "no"))])
        with self.assertRaises(ol.GitHubError):
            ol.ensure_label(api, ol.LABEL_TASK)


class KnownRequestsTest(unittest.TestCase):
    def test_request_numbers_come_from_valid_file_names_in_the_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / ol.REQUEST_DIR
            folder.mkdir(parents=True)
            for name in ("R-001_a.md", "R-002_b.md", "README.md", "R-003_Bad.md", "r-004_x.md", "R-005_x.txt"):
                (folder / name).write_text("x", encoding="utf-8")
            (folder / "R-006_dir.md").mkdir()                                                  # 이름만 같은 폴더는 요청 파일이 아니다
            self.assertEqual(ol.known_request_ids(tmp), {"R-001", "R-002"})
            self.assertEqual(ol.known_request_ids(Path(tmp) / "none"), set())

    def test_the_owner_comes_from_the_runner_variable_or_the_repository_name(self):
        self.assertEqual(ol._owner_of({"GITHUB_REPOSITORY_OWNER": " octo ", "GITHUB_REPOSITORY": "other/x"}), "octo")
        self.assertEqual(ol._owner_of({"GITHUB_REPOSITORY": "octo/blog"}), "octo")
        self.assertEqual(ol._owner_of({}), "")


class EventTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def event_file(self, content, name="event.json"):
        path = self.tmp / name
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        return {"GITHUB_EVENT_PATH": str(path)}

    def test_a_json_object_is_read(self):
        self.assertEqual(ol.read_event(self.event_file('{"action": "opened"}')), {"action": "opened"})

    def test_a_missing_big_or_broken_event_file_is_none(self):
        self.assertIsNone(ol.read_event({}))
        self.assertIsNone(ol.read_event({"GITHUB_EVENT_PATH": ""}))
        self.assertIsNone(ol.read_event({"GITHUB_EVENT_PATH": str(self.tmp / "nope.json")}))
        self.assertIsNone(ol.read_event({"GITHUB_EVENT_PATH": str(self.tmp)}))
        for content in ("", "{", "[1, 2]", '"text"', "null", b"\xff\xfe", "[" * 200000, " " * (ol.MAX_EVENT_BYTES + 5)):
            self.assertIsNone(ol.read_event(self.event_file(content)), repr(content)[:30])


class AckCliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo_root = self.tmp / "repo"
        (self.repo_root / ol.REQUEST_DIR).mkdir(parents=True)
        (self.repo_root / ol.REQUEST_DIR / "R-001_merge-pr57.md").write_text(request_text(), encoding="utf-8")
        self.summary = self.tmp / "summary.md"

    def ack(self, event=None, github=None, net=None, **env):
        event = event if event is not None else issue_event()
        environ = ack_env(self.tmp, event, GITHUB_STEP_SUMMARY=str(self.summary), **env)
        return oh.run_cli("ack", environ=environ, net=net, root=self.repo_root, github=github)

    def sequence(self, github):
        return [(item["method"], item["path"]) for item in github.requests]

    # ---- 정상 흐름 ----
    def test_an_owners_answer_gets_a_label_one_comment_and_one_phone_message(self):
        code, lines, net, github = self.ack(issue_event(body=reply_body(request_id="R-001", answer="승인", choice="B", memo="메모")))
        self.assertEqual(code, 0)
        self.assertEqual(self.sequence(github), [("POST", "/labels"), ("POST", "/issues/12/labels"), ("GET", "/issues/12/comments"), ("POST", "/issues/12/comments")])
        self.assertEqual(github.issue_labels, {12: ["운영자응답"]})
        comment = github.posted(12)[0]
        self.assertTrue(comment.startswith(ol.ACK_MARK + "\n접수했습니다 — 요청 **R-001** · 답: **승인** · 선택: **B**."))
        self.assertNotIn("알 수 없는 요청 번호", comment)                                          # 저장소 요청함에 R-001 파일이 있다
        self.assertEqual(net.calls, 1)
        body = net.bodies()[0]
        self.assertEqual(body["text"], f"{notify.OK_MARK} 답변 접수 R-001 → 승인 · 선택 B(이슈 #12)")
        self.assertNotIn("parse_mode", body)
        self.assertEqual(body["reply_markup"]["inline_keyboard"], [[{"text": "이슈 열기", "url": "https://github.com/shine88pc/chanceblog/issues/12"}]])
        self.assertEqual(lines, ["운영자 응답 접수: 이슈 #12 에 라벨 운영자응답 을 붙였습니다", "운영자 응답 접수: 이슈 #12 에 접수 코멘트를 달았습니다",
                                 "운영자 응답 접수: 텔레그램으로 접수를 알렸습니다"])
        self.assertEqual(self.summary.read_text(encoding="utf-8").strip(), "### 운영자 응답 접수\n\n- 이슈 #12: 요청 R-001 · 답 승인 을 접수했습니다")

    def test_the_github_token_is_sent_only_to_github_and_never_printed_or_posted(self):
        code, lines, net, github = self.ack(issue_event(body=reply_body(memo="메모")))
        for item in github.requests:
            self.assertEqual(item["headers"]["Authorization"], f"Bearer {GH_TOKEN}")
        everything = "\n".join(lines) + json.dumps(github.comments, ensure_ascii=False) + json.dumps(net.bodies(), ensure_ascii=False) + self.summary.read_text(encoding="utf-8")
        self.assertNotIn(GH_TOKEN, everything)
        self.assertEqual(leaks(everything, chat=False), [])                                       # 요청 본문에는 채팅 ID(수신자)가 있어야 한다. 토큰은 어디에도 없다
        self.assertEqual(leaks("\n".join(lines), json.dumps(github.comments, ensure_ascii=False), self.summary.read_text(encoding="utf-8")), [])

    def test_a_request_answer_without_a_choice_has_a_short_phone_message(self):
        code, lines, net, github = self.ack(issue_event(body=reply_body(answer="거절")))
        self.assertEqual(net.bodies()[0]["text"], f"{notify.OK_MARK} 답변 접수 R-001 → 거절(이슈 #12)")

    def test_a_repeated_run_does_not_post_or_send_a_second_time(self):
        github = FakeGitHub()
        self.ack(github=github)
        code, lines, net, _ = self.ack(github=github)
        self.assertEqual((code, net.calls), (0, 0))
        self.assertEqual(len(github.posted(12)), 1)
        self.assertEqual(lines[-1], "운영자 응답 접수: 이슈 #12 에는 접수 코멘트가 이미 있어 다시 달지 않습니다")        # 같은 이벤트를 다시 받으면 라벨은 한 번 더 붙지만(멱등) 코멘트·알림은 없다
        self.assertNotIn("운영자 응답 접수: 이슈 #12 에 접수 코멘트를 달았습니다", lines)
        self.assertEqual(len(github.calls("POST", "/comments")), 1)

    def test_a_label_the_form_already_put_on_the_issue_is_not_created_or_added_again(self):
        code, lines, net, github = self.ack(issue_event(labels=["운영자응답"]))
        self.assertEqual(self.sequence(github), [("GET", "/issues/12/comments"), ("POST", "/issues/12/comments")])
        self.assertNotIn("라벨", "\n".join(lines))

    def test_a_label_that_exists_in_the_repository_is_only_added(self):
        github = FakeGitHub(labels={"운영자응답"})
        code, lines, net, github = self.ack(github=github)
        self.assertEqual(self.sequence(github)[:3], [("POST", "/labels"), ("POST", "/issues/12/labels"), ("GET", "/issues/12/comments")])       # 만들기는 422 로 끝나고 붙이기가 이어진다
        self.assertEqual(github.issue_labels, {12: ["운영자응답"]})
        self.assertEqual(len(github.posted(12)), 1)

    def test_an_unknown_request_number_is_a_warning_in_the_comment_but_still_accepted(self):
        code, lines, net, github = self.ack(issue_event(body=reply_body(request_id="R-777")))
        self.assertIn("알 수 없는 요청 번호", github.posted(12)[0])
        self.assertEqual(net.calls, 1)
        self.assertIn("R-777", net.bodies()[0]["text"])

    def test_a_missing_request_folder_also_just_warns(self):
        (self.repo_root / ol.REQUEST_DIR / "R-001_merge-pr57.md").unlink()
        (self.repo_root / ol.REQUEST_DIR).rmdir()
        code, lines, net, github = self.ack()
        self.assertIn("알 수 없는 요청 번호", github.posted(12)[0])
        self.assertEqual(net.calls, 1)

    def test_a_new_task_request_gets_its_own_label_comment_and_phone_message(self):
        event = issue_event(number=13, title="[요청] ", body=task_body(what="PR 을 정리해 주세요", urgency="급함", approval="예 — 위 내용에 적은 항목에 한해 승인합니다(T3 포함)"))
        code, lines, net, github = self.ack(event)
        self.assertEqual(github.issue_labels, {13: ["운영자요청"]})
        self.assertEqual(github.labels, {"운영자요청"})
        self.assertIn("새 일 요청 · 긴급도: **급함** · 승인 범위: **있음(T3 포함)**", github.posted(13)[0])
        self.assertEqual(net.bodies()[0]["text"], f"{notify.OK_MARK} 새 일 요청 접수(이슈 #13) · 긴급도 급함 · 승인 범위 있음(T3 포함)")
        self.assertEqual(self.summary.read_text(encoding="utf-8").strip(), "### 운영자 응답 접수\n\n- 이슈 #13: 새 일 요청을 접수했습니다(긴급도 급함)")

    def test_a_task_request_without_approval_says_discussion_only(self):
        event = issue_event(number=14, title="[요청] ", body=task_body())
        code, lines, net, github = self.ack(event)
        self.assertEqual(net.bodies()[0]["text"], f"{notify.OK_MARK} 새 일 요청 접수(이슈 #14) · 긴급도 보통 · 논의·준비까지만")

    # ---- 거절·건너뜀(아무것도 하지 않는다) ----
    def assert_nothing_done(self, code, lines, net, github, expected_line):
        self.assertEqual(code, 0)
        self.assertEqual(github.requests, [], "GitHub 에 아무것도 쓰거나 읽지 않는다")
        self.assertEqual(net.calls, 0)
        self.assertEqual(lines, [expected_line])
        self.assertFalse(self.summary.exists())

    def test_a_stranger_gets_nothing_at_all(self):
        for login, association in (("stranger", "NONE"), ("stranger", "OWNER"), ("stranger", "CONTRIBUTOR"), ("github-actions[bot]", "NONE")):
            self.assert_nothing_done(*self.ack(issue_event(login=login, association=association)), "운영자 응답 접수: " + ol.REFUSAL_LINES["not_owner"])

    def test_an_owner_login_without_owner_association_gets_nothing(self):
        for association in ("MEMBER", "COLLABORATOR", "NONE", "owner"):
            self.assert_nothing_done(*self.ack(issue_event(association=association)), "운영자 응답 접수: " + ol.REFUSAL_LINES["not_owner_association"])

    def test_an_owner_issue_that_is_not_one_of_the_forms_gets_nothing(self):
        for title in ("[페이지 수정] 소개", "[이미지 변경] x", "그냥 질문", "", "[운영] 확인 필요 모음"):
            self.assert_nothing_done(*self.ack(issue_event(title=title)), "운영자 응답 접수: " + ol.REFUSAL_LINES["not_form"])

    def test_without_a_known_owner_nothing_is_done(self):
        environ = ack_env(self.tmp, issue_event(), owner="")
        del environ["GITHUB_REPOSITORY_OWNER"]
        environ["GITHUB_REPOSITORY"] = ""
        code, lines, net, github = oh.run_cli("ack", environ=environ, root=self.repo_root)
        self.assert_nothing_done(code, lines, net, github, "운영자 응답 접수: " + ol.REFUSAL_LINES["no_owner"])

    def test_events_that_are_not_a_newly_opened_issue_do_nothing(self):
        line = "운영자 응답 접수: 이 실행은 새로 열린 이슈 이벤트가 아니어서 아무것도 하지 않습니다"
        for action in ("edited", "closed", "reopened", "labeled", "deleted", ""):
            self.assert_nothing_done(*self.ack(issue_event(action=action)), line)
        for event_name in ("push", "issue_comment", "pull_request_target", "workflow_dispatch", ""):
            self.assert_nothing_done(*self.ack(issue_event(), event_name=event_name), line)
        environ = ack_env(self.tmp, issue_event())
        for broken in (lambda e: e.pop("GITHUB_EVENT_PATH"), lambda e: e.update(GITHUB_EVENT_PATH=str(self.tmp / "none.json"))):
            broken(environ)
            self.assert_nothing_done(*oh.run_cli("ack", environ=environ, root=self.repo_root), line)

    def test_a_bad_issue_number_stops_after_the_owner_check(self):
        for number in (None, 0, -1, True, "12", 1.5):
            event = issue_event()
            event["issue"]["number"] = number
            self.assert_nothing_done(*self.ack(event), "운영자 응답 접수: 이슈 번호를 읽지 못해 아무것도 하지 않습니다")

    def test_a_malformed_event_never_crashes_the_run(self):
        for issue in (None, [], "text", {"title": "[답변] "}, {"number": 3, "title": "[답변] ", "user": "x", "author_association": "OWNER", "labels": "a"}):
            event = {"action": "opened", "issue": issue}
            code, lines, net, github = self.ack(event)
            self.assertEqual(code, 0, issue)
            self.assertEqual(net.calls, 0)
            self.assertFalse(any("예기치 않은 오류" in line for line in lines), (issue, lines))

    def test_without_the_github_token_nothing_is_written_and_nothing_is_sent(self):
        code, lines, net, github = oh.run_cli("ack", environ=ack_env(self.tmp, issue_event(), token=""), root=self.repo_root)
        self.assertEqual((code, github.requests, net.calls), (0, [], 0))
        self.assertEqual(lines, ["운영자 응답 접수: GITHUB_TOKEN 이 없어 라벨·코멘트·알림을 하지 않습니다(읽기 전용)"])

    # ---- 양식 모양 문제 ----
    def test_an_owner_form_with_the_wrong_shape_gets_one_explanation_and_no_phone_message(self):
        event = issue_event(body="양식을 쓰지 않고 직접 쓴 글")
        code, lines, net, github = self.ack(event)
        self.assertEqual(code, 0)
        self.assertEqual(net.calls, 0)
        comment = github.posted(12)[0]
        self.assertTrue(comment.startswith(ol.ACK_MARK + "\n양식 모양이 달라 처리하지 못했습니다 — `요청 번호` 항목이 없습니다; `답변` 항목이 없습니다."))
        self.assertEqual(github.issue_labels, {12: ["운영자응답"]})
        self.assertNotIn("직접 쓴 글", comment)
        code, lines, net, _ = self.ack(event, github=github)                                         # 다시 실행해도 설명은 한 번
        self.assertEqual(len(github.posted(12)), 1)

    # ---- 알림·GitHub 실패는 경고뿐 ----
    def test_without_telegram_secrets_the_comment_is_still_posted(self):
        code, lines, net, github = oh.run_cli("ack", environ=ack_env(self.tmp, issue_event(), telegram=False), root=self.repo_root)
        self.assertEqual((code, net.calls, len(github.posted(12))), (0, 0, 1))
        self.assertIn(notify.SKIP_LINE, lines)
        self.assertFalse(any(line.startswith("::warning::") for line in lines))

    def test_a_telegram_failure_is_a_warning_the_comment_stays_and_the_exit_code_is_zero(self):
        code, lines, net, github = self.ack(net=FakeNet(tg_error(401, "Unauthorized " + TOKEN)))
        self.assertEqual(code, 0)
        self.assertEqual(len(github.posted(12)), 1)
        self.assertTrue(any("텔레그램 알림을 보내지 못했습니다" in line for line in lines))
        self.assertEqual(lines[-1], ol.ACK_WARNING)
        self.assertEqual(leaks(*lines), [])

    def test_a_label_failure_is_a_warning_and_the_comment_and_phone_message_still_go(self):
        github = FakeGitHub(failures=[("POST", "/labels", oh.http_error(403, "Resource not accessible by integration"))])
        code, lines, net, github = self.ack(github=github)
        self.assertEqual((code, len(github.posted(12)), net.calls), (0, 1, 1))
        self.assertIn("운영자 응답 접수: 라벨을 붙이지 못했습니다 — HTTP 403: Resource not accessible by integration", lines)
        self.assertEqual(lines[-1], ol.ACK_WARNING)

    def test_a_comment_failure_is_a_warning_and_there_is_no_phone_message(self):
        github = FakeGitHub(failures=[("POST", "/comments", oh.http_error(403, "Resource not accessible by integration"))])
        code, lines, net, github = self.ack(github=github)
        self.assertEqual((code, github.posted(12), net.calls), (0, [], 0))
        self.assertEqual(lines[-2:], ["운영자 응답 접수: 접수 코멘트를 달지 못했습니다 — HTTP 403: Resource not accessible by integration", ol.ACK_WARNING])
        self.assertFalse(self.summary.exists())

    def test_a_lost_comment_response_does_not_double_post_and_still_notifies(self):
        github = FakeGitHub(failures=[("POST", "/comments", oh.http_error(502, "bad gateway"), True)])
        code, lines, net, github = self.ack(github=github)
        self.assertEqual((code, len(github.posted(12)), net.calls), (0, 1, 1))

    def test_an_unexpected_bug_is_a_class_name_and_a_warning_with_exit_code_zero(self):
        class Broken(FakeGitHub):
            def __call__(self, request, timeout=None):
                raise RuntimeError("비밀 " + GH_TOKEN)
        code, lines, net, github = oh.run_cli("ack", environ=ack_env(self.tmp, issue_event()), root=self.repo_root, github=Broken())
        self.assertEqual(code, 0)
        self.assertEqual(net.calls, 0)
        self.assertNotIn(GH_TOKEN, "\n".join(lines))
        self.assertTrue(any("예기치 않은 오류(RuntimeError)" in line for line in lines), lines)

    # ---- 적대적 입력 ----
    def test_hostile_text_in_the_title_and_every_field_reaches_no_comment_no_message_no_log_and_no_summary(self):
        for hostile, marker in HOSTILE_PAIRS:
            event = issue_event(title="[답변] " + hostile, body=reply_body(choice=hostile, memo=hostile + "\n" + hostile, crlf=False))
            code, lines, net, github = self.ack(event)
            everything = "\n".join(lines) + json.dumps(github.comments, ensure_ascii=False) + json.dumps(net.bodies(), ensure_ascii=False) + self.summary.read_text(encoding="utf-8")
            self.assertEqual(code, 0, hostile)
            self.assertEqual(len(github.posted(12)), 1, hostile)
            self.assertNotIn(hostile, everything.replace(ol.ACK_MARK, ""), hostile)
            self.assertNotIn(marker, everything.replace(ol.ACK_MARK, "").replace("#12", ""), hostile)
            for line in lines:
                self.assertFalse(line.lstrip().startswith("::"), line)
            self.summary.unlink(missing_ok=True)

    def test_a_hostile_request_number_is_not_echoed_either(self):
        for hostile, marker in HOSTILE_PAIRS:
            event = issue_event(body=reply_body(request_id=hostile, crlf=False))
            code, lines, net, github = self.ack(event)
            everything = "\n".join(lines) + json.dumps(github.comments, ensure_ascii=False) + json.dumps(net.bodies(), ensure_ascii=False)
            self.assertNotIn(hostile, everything.replace(ol.ACK_MARK, ""), hostile)
            self.assertNotIn(marker, everything.replace(ol.ACK_MARK, "").replace("#12", ""), hostile)
            self.assertEqual(net.calls, 0, hostile)                                             # 양식 모양 문제는 휴대폰으로 보내지 않는다
            self.assertIn("양식 모양이 달라 처리하지 못했습니다", github.posted(12)[0])

    def test_a_huge_memo_is_counted_not_copied(self):
        event = issue_event(body=reply_body(memo="가" * 60000))
        code, lines, net, github = self.ack(event)
        comment = github.posted(12)[0]
        self.assertIn("메모: 있음(60000자)", comment)
        self.assertLess(len(comment), 2000)


class OperatorLoopFlowTest(unittest.TestCase):
    """AI 의 요청 파일 → 텔레그램 메시지 → 운영자의 응답 이슈 → 접수(코멘트·휴대폰) → AI 가 요청 번호로 되찾기까지 한 흐름."""

    def test_request_message_then_reply_issue_then_acknowledgement_then_lookup_by_request_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            repo_root = tmp / "repo"
            (repo_root / ol.REQUEST_DIR).mkdir(parents=True)
            name = "R-007_choose-title.md"
            text = request_text(id="R-007", kind="decision", title="블로그 제목 둘 중 고르기", summary="A: 오늘의 정리 / B: 한 줄 요약 중에서 골라 주세요(선택 칸에 A 또는 B).", urgency="급함", pr="58")
            (repo_root / ol.REQUEST_DIR / name).write_text(text, encoding="utf-8")
            # 1) AI 가 push → 알림 워크플로가 요청 파일을 텔레그램으로 보낸다
            code, lines, net, _ = oh.run_cli("requests", environ=requests_env(), runner=oh.RequestGit.with_requests({name: text}), root=repo_root)
            self.assertEqual((code, net.calls), (0, 1))
            message = net.bodies()[0]
            self.assertIn("AI 요청 R-007 · 결정 부탁", message["text"])
            self.assertIn("답하는 법: 아래 [답하기] → 양식에서 R-007 선택", message["text"])
            self.assertEqual([button["text"] for button in message["reply_markup"]["inline_keyboard"][0]], ["요청 열기", "PR 열기", "답하기", "사용법"])
            # 2) 운영자는 메시지 맨 위의 번호를 보고 양식에 쓴다(여기서는 메시지에서 번호를 읽어 그대로 쓴다)
            request_id = re.search(r"AI 요청 (R-[0-9]{3})", message["text"]).group(1)
            event = issue_event(number=21, body=reply_body(request_id=request_id, answer="승인", choice="B", memo="B 로 가요"))
            # 3) 이슈가 열리면 접수 확인이 코멘트와 텔레그램으로 간다
            code, lines, net2, github = oh.run_cli("ack", environ=ack_env(tmp, event), root=repo_root)
            self.assertEqual((code, net2.calls), (0, 1))
            self.assertIn("접수했습니다 — 요청 **R-007** · 답: **승인** · 선택: **B**.", github.posted(21)[0])
            self.assertNotIn("알 수 없는 요청 번호", github.posted(21)[0])
            self.assertEqual(net2.bodies()[0]["text"], f"{notify.OK_MARK} 답변 접수 R-007 → 승인 · 선택 B(이슈 #21)")
            # 4) AI 세션은 그 이슈를 읽어 요청 번호로 어느 요청에 대한 답인지 되찾는다
            issue = event["issue"]
            found = ol.parse_reply(issue["title"], issue["body"], issue["user"]["login"], issue["author_association"], OWNER)
            self.assertEqual((found.request_id, found.answer, found.choice), ("R-007", "승인", "B"))
            self.assertIn(found.request_id, ol.known_request_ids(repo_root))
            self.assertEqual(ol.parse_request(name, (repo_root / ol.REQUEST_DIR / name).read_text(encoding="utf-8")).id, found.request_id)

    def test_a_reply_to_a_request_number_that_does_not_exist_is_accepted_with_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            event = issue_event(number=22, body=reply_body(request_id="R-404"))
            code, lines, net, github = oh.run_cli("ack", environ=ack_env(tmp, event), root=tmp)
            self.assertEqual((code, net.calls, len(github.posted(22))), (0, 1, 1))
            self.assertIn("알 수 없는 요청 번호", github.posted(22)[0])


if __name__ == "__main__":
    unittest.main()
