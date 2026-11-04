"""텔레그램 수신('예약 읽기', pipeline/telegram_inbox.py) 시험 — 허용 조건·순서와 offset 확인·멱등·5통 상한·길이와 인젝션·비밀 비노출·답변 후보·오류 분류·진짜 urllib 경로.

진짜 텔레그램·GitHub 는 부르지 않는다: 둘 다 프로세스 안 가짜 서버(telegram_inbox_helpers.FakeTelegram·FakeIssues)이고 소켓 연결은 막혀 있다(NoOutbound — 시도가 있으면 실패).
같은 가짜 서버로 run_inbox 를 여러 번 부르면 '다음 예약 실행' 이다. 가짜 토큰·채팅 ID 는 런타임에 조합한 값이다(notify_helpers). 운영자 요청 번호는 n1 의 표기 시험과 겹치지 않게 `r090` 꼴이다.
"""
import contextlib
import http.server
import io
import json
import os
import re
import tempfile
import threading
import unicodedata
import unittest
import urllib.error
from unittest import mock

import _bootstrap  # noqa: F401
import notify_helpers as nh
import telegram_inbox_helpers as th
from pipeline import notify
from pipeline import operator_loop as loop
from pipeline import telegram_inbox as ti

TOKEN, CHAT = nh.TOKEN, nh.CHAT


class Case(th.NoOutbound, unittest.TestCase):
    """바깥 연결이 막힌 시험 바탕."""

    def run_with(self, *updates, **kwargs):
        return th.run_inbox(th.FakeTelegram(list(updates)), **kwargs)


def quote_of(body):
    """본문의 인용 블록(줄 앞 `> ` 를 뗀 글)."""
    return "\n".join(line[2:] if line.startswith("> ") else "" for line in body.split("\n") if line.startswith(">"))


def assert_safe_body(test, body, update_id):
    """본문이 코드가 정한 모양인지: 표지는 맨 위 한 번뿐, `@`·`<`·`>`(인용 머리 말고)가 원문에서 새지 않는다."""
    test.assertTrue(body.startswith(ti.MARKER_FORMAT.format(update_id) + "\n"), body[:80])
    test.assertEqual(body.count("<!--"), 1)
    test.assertEqual(body.count("-->"), 1)
    test.assertEqual(ti.MARKER_RE.findall(body), [str(update_id)])
    test.assertNotIn("@", body)
    for breaker in ("\r", "\u2028", "\u2029", "\x85", "\x0b", "\x0c", "\t"):        # 어떤 줄바꿈 꼴도 남지 않아야 모든 줄이 `> ` 머리를 단다
        test.assertNotIn(breaker, body)
    for line in body.split("\n")[1:]:
        test.assertNotIn("<", line)
        test.assertNotIn(">", line[1:] if line.startswith(">") else line)


# ====================================================================================================================
# 1. 허용 조건
# ====================================================================================================================
class AllowedSenderTest(Case):
    def test_operator_private_text_becomes_one_issue_with_ack_and_confirm(self):
        run = self.run_with(th.message_update(10, "안녕 AI"))
        self.assertEqual(run.code, 0)
        [issue] = run.issues()
        self.assertEqual(issue["title"], "[텔레그램] 안녕 AI")
        self.assertEqual([item["name"] for item in issue["labels"]], ["텔레그램수신"])
        self.assertEqual(issue["user"]["login"], "github-actions[bot]")
        self.assertEqual(run.tg.methods(), ["getUpdates", "sendMessage", "getUpdates"])
        self.assertNotIn("offset", run.tg.polls()[0])
        self.assertEqual(run.tg.polls()[1]["offset"], 11)
        ack = run.tg.texts()[0]
        for needle in ("접수했습니다", "#101", "비밀·키는 보내지 마세요", "[답하기]"):
            self.assertIn(needle, ack)
        self.assertEqual(run.tg.sent[0]["reply_markup"]["inline_keyboard"], [[{"text": "이슈 열기", "url": "https://github.com/shine88pc/chanceblog/issues/101"}]])
        self.assertEqual(run.tg.queue, [])

    def test_the_poll_request_shape(self):
        run = self.run_with(th.message_update(10, "안녕"))
        for payload in run.tg.polls():
            self.assertEqual(payload["timeout"], 0)
            self.assertEqual(payload["allowed_updates"], ["message"])
            self.assertLessEqual(payload["limit"], ti.UPDATES_LIMIT)
        self.assertEqual(run.tg.polls()[0]["limit"], ti.UPDATES_LIMIT)
        self.assertEqual(run.tg.timeouts[0], ti.TIMEOUT_SECONDS)

    def test_only_get_updates_and_send_message_are_ever_called(self):
        """웹훅을 만들지도 지우지도 않는다(setWebhook·deleteWebhook 없음) — th.run_inbox 도 모든 실행에서 이 집합을 지킨다."""
        run = self.run_with(th.message_update(10, "안녕"), th.message_update(11, None, photo=[{"file_id": "x"}]))
        self.assertEqual(set(run.tg.methods()), {"getUpdates", "sendMessage"})
        source = open(_bootstrap.ROOT / "pipeline" / "telegram_inbox.py", encoding="utf-8").read()
        for name in ("setWebhook", "deleteWebhook", "getWebhookInfo"):
            self.assertNotIn(f"/{name}", source)
            self.assertNotIn(f'"{name}"', source)

    def strangers(self):
        other = th.OTHER_ID
        no_sender = th.message_update(5, "x")
        del no_sender["message"]["from"]
        chat_str = th.message_update(5, "x", chat_id=str(th.CHAT_INT))
        from_str = th.message_update(5, "x")
        from_str["message"]["from"]["id"] = str(th.CHAT_INT)
        return {
            "다른 사람의 비공개 대화": th.message_update(5, "x", chat_id=other),
            "대화는 운영자·보낸 사람이 다름": th.message_update(5, "x", from_id=other),
            "대화는 다른 사람·보낸 사람은 운영자": th.message_update(5, "x", chat_id=other, from_id=th.CHAT_INT),
            "그룹(보낸 사람이 운영자)": th.message_update(5, "x", chat_id=-100123456, from_id=th.CHAT_INT, chat_type="group"),
            "슈퍼그룹": th.message_update(5, "x", chat_id=-100123456, from_id=th.CHAT_INT, chat_type="supergroup"),
            "채널 대화": th.message_update(5, "x", chat_id=-100123456, from_id=th.CHAT_INT, chat_type="channel"),
            "그룹인데 chat.id 가 운영자 값(위조)": th.message_update(5, "x", chat_type="group"),
            "chat.type 이 없음": {"update_id": 5, "message": {"chat": {"id": th.CHAT_INT}, "from": {"id": th.CHAT_INT}, "text": "x"}},
            "운영자 글과 모양이 같은 edited_message": th.renamed(th.message_update(5, "x"), "edited_message"),
            "운영자 글과 모양이 같은 channel_post": th.renamed(th.message_update(5, "x"), "channel_post"),
            "운영자 글과 모양이 같은 edited_channel_post": th.renamed(th.message_update(5, "x"), "edited_channel_post"),
            "운영자 글과 모양이 같은 business_message": th.renamed(th.message_update(5, "x"), "business_message"),
            "운영자 글을 품은 callback_query": {"update_id": 5, "callback_query": {"id": "1", "from": {"id": th.CHAT_INT}, "message": th.message_update(5, "x")["message"], "data": "x"}},
            "channel_post": th.other_update(5, "channel_post", text="x"),
            "edited_message": th.other_update(5, "edited_message", text="x"),
            "edited_channel_post": th.other_update(5, "edited_channel_post", text="x"),
            "callback_query": th.other_update(5, "callback_query", data="x"),
            "inline_query": th.other_update(5, "inline_query", query="x"),
            "message 가 문자열": {"update_id": 5, "message": "x"},
            "message 가 없음": {"update_id": 5},
            "보낸 사람 없음": no_sender,
            "chat.id 가 문자열": chat_str,
            "from.id 가 문자열": from_str,
        }

    def test_everything_else_makes_no_issue_and_gets_no_reply(self):
        for name, update in self.strangers().items():
            with self.subTest(name):
                run = self.run_with(update)
                self.assertEqual(run.code, 0, name)
                self.assertEqual(run.issues(), [], name)
                self.assertEqual(run.tg.sent, [], f"{name}: 남에게는 아무 답도 하지 않는다")
                self.assertEqual(run.gh.requests, [], f"{name}: GitHub 를 부르지 않는다")
                self.assertEqual(run.tg.queue, [], f"{name}: 허용 밖 글은 확인해 치운다(다음 묶음을 막지 않게)")

    def test_boolean_ids_are_not_numbers(self):
        """True == 1 이라서 `TELEGRAM_CHAT_ID=1` 이면 불리언 id 가 통과하지 않게 정수만 받는다."""
        update = th.message_update(5, "x", chat_id=True, from_id=True)
        run = th.run_inbox(th.FakeTelegram([update]), env=th.make_env(TELEGRAM_CHAT_ID="1"))
        self.assertEqual(run.issues(), [])
        self.assertEqual(run.tg.sent, [])

    def test_a_stranger_between_two_operator_texts_is_skipped_without_blocking(self):
        run = self.run_with(th.message_update(1, "첫째"), th.message_update(2, "남", chat_id=th.OTHER_ID), th.message_update(3, "셋째"))
        self.assertEqual([item["title"] for item in run.issues()], ["[텔레그램] 첫째", "[텔레그램] 셋째"])
        self.assertEqual(run.tg.queue, [])
        self.assertEqual(len(run.tg.sent), 2)           # 접수 확인 둘뿐(남에게도 답하지 않는다)

    def test_non_text_forms_from_the_operator_get_one_line_and_no_issue(self):
        forms = {"사진": {"photo": [{"file_id": "x"}]}, "음성": {"voice": {"file_id": "x"}}, "스티커": {"sticker": {"file_id": "x"}}, "파일": {"document": {"file_id": "x"}},
                 "영상": {"video": {"file_id": "x"}}, "연락처": {"contact": {"phone_number": "1"}}, "위치": {"location": {"latitude": 1, "longitude": 1}},
                 "사진+설명": {"photo": [{"file_id": "x"}], "caption": "설명 글"}}
        for name, extra in forms.items():
            with self.subTest(name):
                run = self.run_with(th.message_update(5, None, **extra))
                self.assertEqual(run.issues(), [])
                self.assertEqual(run.tg.texts(), [ti.NON_TEXT_TEXT])
                self.assertEqual(run.tg.queue, [])

    def test_blank_and_invisible_only_texts_are_treated_as_non_text(self):
        for text in ("   ", "\n \n", "\u200b\u200c\u2060", "\u202e\ufeff", "\x00\x01"):
            with self.subTest(text=repr(text)):
                run = self.run_with(th.message_update(5, text))
                self.assertEqual(run.issues(), [])
                self.assertEqual(run.tg.texts(), [ti.NON_TEXT_TEXT])

    def test_start_and_help_get_the_usage_paragraph_and_no_issue(self):
        for text in ("/start", "/help", "/start@chanceblog_bot", "/START", "/help 도와줘", "  /start", "/start abc123"):
            with self.subTest(text=text):
                run = self.run_with(th.message_update(5, text))
                self.assertEqual(run.issues(), [])
                self.assertEqual(run.tg.texts(), [ti.USAGE_TEXT])
        for needle in ("공개 이슈", "비밀번호·키·개인정보는 보내지 마세요", "수십 분", "승인이 아닙니다", "[답하기]"):
            self.assertIn(needle, ti.USAGE_TEXT)

    def test_commands_that_only_look_similar_are_normal_texts(self):
        for text in ("/startx", "/starting", "/helper 줄", "start", "도움말 /help"):
            with self.subTest(text=text):
                run = self.run_with(th.message_update(5, text))
                self.assertEqual(len(run.issues()), 1)

    def test_side_replies_are_capped_per_run(self):
        photos = [th.message_update(number, None, photo=[{"file_id": "x"}]) for number in range(1, 7)]
        run = self.run_with(*photos)
        self.assertEqual(len(run.tg.sent), ti.MAX_SIDE_REPLIES)
        self.assertEqual(run.tg.queue, [])
        self.assertEqual(run.issues(), [])

    def test_a_stranger_flood_larger_than_one_batch_is_drained_and_a_later_operator_text_is_found(self):
        junk = [th.message_update(number, "스팸", chat_id=th.OTHER_ID) for number in range(1, 46)]
        run = self.run_with(*junk, th.message_update(46, "진짜 글"))
        self.assertEqual([item["title"] for item in run.issues()], ["[텔레그램] 진짜 글"])
        self.assertEqual(len(run.tg.sent), 1)
        self.assertEqual(run.tg.queue, [])
        self.assertTrue(all(payload["limit"] <= ti.UPDATES_LIMIT for payload in run.tg.polls()))
        self.assertGreaterEqual(len(run.tg.polls()), 10)          # 글 46통을 5통씩

    def test_the_run_summary_has_the_counts_and_the_cause_line_and_the_log_has_one_summary_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = os.path.join(tmp, "summary.md")
            run = th.run_inbox(th.FakeTelegram([th.message_update(1, "하나"), th.message_update(2, "남", chat_id=th.OTHER_ID), th.message_update(3, None, photo=[{"file_id": "x"}])]),
                               env=th.make_env(GITHUB_STEP_SUMMARY=summary))
            with open(summary, encoding="utf-8") as handle:
                written = handle.read()
            self.assertIn("### 텔레그램 수신 가져오기", written)
            for needle in ("만든 이슈: #101", "이미 이슈가 있어 건너뜀: 0건", "허용 밖이라 무시(다른 사람·그룹·수정·콜백): 1건", "안내 답(/start·/help·글 아닌 형식): 1통"):
                self.assertIn(needle, written, needle)
            self.assertNotIn("**문제**", written)
            self.assertIn("텔레그램 수신: 이슈 1건 만듦(#101) · 이미 있어 건너뜀 0 · 허용 밖이라 무시 1 · 안내 답 1통", run.lines)
        with tempfile.TemporaryDirectory() as tmp:
            summary = os.path.join(tmp, "summary.md")
            tg = th.FakeTelegram([th.message_update(1, "하나")], webhook=True)
            th.run_inbox(tg, env=th.make_env(GITHUB_STEP_SUMMARY=summary))
            with open(summary, encoding="utf-8") as handle:
                written = handle.read()
            self.assertIn("**문제**", written)
            self.assertIn("웹훅이 설정돼 있어 getUpdates 로 읽을 수 없습니다(409)", written)
            self.assertNotIn("만든 이슈: #", written.replace("만든 이슈: 없음", ""))

    def test_nothing_new_is_one_quiet_line_without_calling_github(self):
        run = self.run_with()
        self.assertEqual((run.code, run.lines), (0, [ti.NONE_LINE]))
        self.assertEqual(run.gh.requests, [])
        self.assertEqual(run.tg.methods(), ["getUpdates"])


# ====================================================================================================================
# 2. 순서·offset 확인·실패 지점
# ====================================================================================================================
class OrderAndConfirmTest(Case):
    def test_calls_happen_in_the_documented_order(self):
        run = self.run_with(th.message_update(10, "하나"))
        self.assertEqual([(item["method"], item["path"]) for item in run.gh.requests],
                         [("GET", "/issues"), ("POST", "/labels"), ("POST", "/issues")])
        listing = run.gh.requests[0]["query"]
        for needle in ("labels=%ED%85%94%EB%A0%88%EA%B7%B8%EB%9E%A8%EC%88%98%EC%8B%A0", "state=all", "per_page=100"):
            self.assertIn(needle, listing)
        self.assertEqual(run.gh.requests[2]["payload"]["labels"], ["텔레그램수신"])
        self.assertIs(run.gh.requests[2]["headers"].get("Authorization", "").startswith("Bearer "), True)

    def test_a_failed_issue_creation_is_not_confirmed_and_the_next_run_retries(self):
        tg = th.FakeTelegram([th.message_update(10, "하나")])
        gh = th.FakeIssues(failures=[("POST", "/issues", th.oh.http_error(500, "boom"))])
        first = th.run_inbox(tg, gh)
        self.assertEqual(first.code, 0)                        # 일시 문제 — 경고만
        self.assertEqual(first.issues(), [])
        self.assertEqual([item["update_id"] for item in tg.queue], [10], "만들지 못한 글은 확인하지 않는다")
        self.assertEqual(tg.sent, [])
        self.assertTrue(all("offset" not in payload for payload in tg.polls()))
        self.assertIn("::warning::", first.text)
        second = th.run_inbox(tg, gh)
        self.assertEqual(len(second.issues()), 1)
        self.assertEqual(tg.queue, [])

    def test_a_rejected_issue_creation_is_a_setup_problem_and_not_confirmed(self):
        for status in (401, 403, 404, 422):
            with self.subTest(status=status):
                tg = th.FakeTelegram([th.message_update(10, "하나")])
                gh = th.FakeIssues(failures=[("POST", "/issues", th.oh.http_error(status, "denied"))])
                run = th.run_inbox(tg, gh)
                self.assertEqual(run.code, 1)
                self.assertIn("::error::", run.text)
                self.assertEqual([item["update_id"] for item in tg.queue], [10])
                self.assertEqual(tg.sent, [])

    def test_a_failure_in_the_middle_confirms_only_what_was_finished(self):
        tg = th.FakeTelegram([th.message_update(1, "A"), th.message_update(2, "B"), th.message_update(3, "C"), th.message_update(4, "남", chat_id=th.OTHER_ID)])
        gh = th.FakeIssues()
        created = []

        def nth_post_fails(request, timeout=None):
            if request.get_method() == "POST" and request.full_url.endswith("/issues"):
                created.append(1)
                if len(created) == 2:
                    raise th.oh.http_error(403, "denied")
            return gh(request, timeout)

        api = ti.loop.GitHub(th.REPO, th.GH_TOKEN, opener=nth_post_fails, sleep=nh.Clock().sleep)
        lines, clock = [], nh.Clock()
        code = ti.main([], environ=th.make_env(), out=lines.append, opener=tg, sleep=clock.sleep, clock=clock.clock, api=api)
        self.assertEqual(code, 1)
        self.assertEqual([item["title"] for item in gh.new_issues()], ["[텔레그램] A"])
        self.assertEqual([item["update_id"] for item in tg.queue], [2, 3, 4])
        self.assertEqual(tg.polls()[-1]["offset"], 2)
        self.assertEqual(tg.polls()[-1]["limit"], 1)

    def test_a_failed_confirm_call_does_not_create_duplicates_next_time(self):
        tg = th.FakeTelegram([th.message_update(10, "하나")],
                             failures=[{"method": "getUpdates", "when": lambda payload: "offset" in payload, "outcome": nh.http_error(500, "x"), "times": 2}])
        gh = th.FakeIssues()
        with tempfile.TemporaryDirectory() as tmp:
            summary = os.path.join(tmp, "summary.md")
            first = th.run_inbox(tg, gh, env=th.make_env(GITHUB_STEP_SUMMARY=summary))
            with open(summary, encoding="utf-8") as handle:
                written = handle.read()
        self.assertEqual(len(first.issues()), 1)
        self.assertEqual([item["update_id"] for item in tg.queue], [10], "확인이 실패해 글이 남아 있다")
        self.assertEqual(first.code, 0)
        self.assertIn("::warning::", first.text)
        self.assertIn("확인(offset)을 올리지 못한 글은 다음 실행이 다시 읽고", written)       # 실행 요약이 확인 실패와 그 결과를 알린다
        second = th.run_inbox(tg, gh)
        self.assertEqual(len(gh.new_issues()), 1, "같은 글의 이슈를 다시 만들지 않는다")
        self.assertEqual(len(tg.sent), 1, "접수 확인도 다시 보내지 않는다")
        self.assertEqual(tg.queue, [])
        self.assertIn("이미 있어 건너뜀 1", second.text)

    def test_confirmation_happens_after_the_issue_and_the_ack(self):
        tg = th.FakeTelegram([th.message_update(10, "하나"), th.message_update(11, "둘")])
        events = []
        gh = th.FakeIssues()

        class Spy:
            def __call__(self, request, timeout=None):
                path = request.full_url.rsplit("/", 1)[-1]
                events.append(("tg", path, json.loads(request.data.decode())) if request.data else ("tg", path, {}))
                return tg(request, timeout)

        orig_gh = gh.__call__

        def gh_spy(request, timeout=None):
            if request.get_method() == "POST" and request.full_url.endswith("/issues"):
                events.append(("gh", "create"))
            return orig_gh(request, timeout)

        api = ti.loop.GitHub(th.REPO, th.GH_TOKEN, opener=gh_spy, sleep=lambda seconds: None)
        lines, clock = [], nh.Clock()
        ti.main([], environ=th.make_env(), out=lines.append, opener=Spy(), sleep=clock.sleep, clock=clock.clock, api=api)
        kinds = [(item[0], item[1]) for item in events]
        self.assertEqual(kinds, [("tg", "getUpdates"), ("gh", "create"), ("tg", "sendMessage"), ("gh", "create"), ("tg", "sendMessage"), ("tg", "getUpdates")])
        self.assertEqual(events[-1][2]["offset"], 12)

    def test_at_most_five_issues_per_run_and_the_rest_next_time(self):
        updates = [th.message_update(number, f"글 {number}") for number in range(1, 9)]
        tg, gh = th.FakeTelegram(updates), th.FakeIssues()
        first = th.run_inbox(tg, gh)
        self.assertEqual(len(first.issues()), 5)
        self.assertEqual([item["update_id"] for item in tg.queue], [6, 7, 8], "다섯째 글까지만 확인한다")
        self.assertEqual(first.clock.sleeps.count(ti.ISSUE_GAP_SECONDS), 4, "이슈 사이 1초 간격")
        self.assertEqual(first.code, 0)
        second = th.run_inbox(tg, gh)
        self.assertEqual(len(gh.new_issues()), 8)
        self.assertEqual(len(second.issues()), 8)               # gh 가 같아 누적
        self.assertEqual(tg.queue, [])
        self.assertEqual(len({item["title"] for item in gh.new_issues()}), 8)

    def test_junk_after_the_fifth_issue_waits_for_the_next_run(self):
        updates = [th.message_update(number, f"글 {number}") for number in range(1, 6)] + [th.message_update(6, "스팸", chat_id=th.OTHER_ID)]
        tg = th.FakeTelegram(updates)
        run = th.run_inbox(tg)
        self.assertEqual([item["update_id"] for item in tg.queue], [6])
        self.assertEqual(len(run.issues()), 5)

    def test_issue_numbers_follow_update_order_even_if_the_server_lists_them_unordered(self):
        tg = th.FakeTelegram()
        tg.queue = [th.message_update(3, "셋"), th.message_update(1, "하나"), th.message_update(2, "둘")]       # 일부러 순서를 섞는다(서버 흉내가 정렬하지 않게)
        run = th.run_inbox(tg)
        self.assertEqual([item["title"] for item in run.issues()], ["[텔레그램] 하나", "[텔레그램] 둘", "[텔레그램] 셋"])

    def test_duplicate_update_ids_in_one_batch_make_one_issue(self):
        tg = th.FakeTelegram()
        tg.queue = [th.message_update(4, "같은 글"), th.message_update(4, "같은 글")]
        self.assertEqual(len(th.run_inbox(tg).issues()), 1)

    def test_a_server_that_ignores_offset_does_not_make_the_run_loop(self):
        """고장난 서버가 offset 을 무시하고 같은 묶음을 돌려줘도 같은 글을 다시 처리하거나 끝없이 읽지 않는다."""
        tg = th.FakeTelegram([th.message_update(1, "하나"), th.message_update(2, "둘")], ignore_offset=True, max_polls=6)
        run = th.run_inbox(tg)
        self.assertEqual(len(run.issues()), 2)
        self.assertEqual(len(tg.polls()), 2)                    # 처음 읽기 + 확인·다음 묶음 읽기 한 번뿐
        self.assertEqual(run.code, 0)
        self.assertEqual(len(tg.sent), 2)

    def test_a_batch_without_readable_update_ids_does_not_loop(self):
        tg = th.FakeTelegram()
        tg.queue = [{"update_id": "x", "message": {}}, {"message": {}}, 5, None]
        run = th.run_inbox(tg)
        self.assertEqual(run.code, 0)
        self.assertEqual(len(run.tg.polls()), 1)

    def test_ack_failure_keeps_the_issue_and_still_confirms(self):
        tg = th.FakeTelegram([th.message_update(10, "하나")], failures=[{"method": "sendMessage", "outcome": nh.http_error(403, "Forbidden: bot was blocked"), "times": 3}])
        run = th.run_inbox(tg)
        self.assertEqual(len(run.issues()), 1)
        self.assertEqual(tg.queue, [])
        self.assertEqual(run.code, 0)
        self.assertIn("접수 확인을 보내지 못했습니다", run.text)

    def test_transport_budget_never_exceeds_the_message_cap(self):
        photos = [th.message_update(number, None, photo=[{"file_id": "x"}]) for number in range(1, 5)]
        texts = [th.message_update(number, f"글 {number}") for number in range(5, 12)]
        run = self.run_with(*photos, *texts)
        self.assertLessEqual(len(run.tg.sent), ti.MAX_MESSAGES)


# ====================================================================================================================
# 3. 멱등(표지 검색)
# ====================================================================================================================
class IdempotencyTest(Case):
    def test_an_existing_marker_issue_open_or_closed_is_skipped(self):
        for state in ("open", "closed"):
            with self.subTest(state=state):
                gh = th.FakeIssues([th.stored_issue(7, 10, state=state)])
                run = th.run_inbox(th.FakeTelegram([th.message_update(10, "하나")]), gh)
                self.assertEqual(run.issues(), [])
                self.assertEqual([item["method"] for item in gh.requests], ["GET"], "만들기·라벨 호출이 없다")
                self.assertEqual(run.tg.sent, [])
                self.assertEqual(run.tg.queue, [])
                self.assertEqual(run.code, 0)

    def test_a_marker_issue_by_a_stranger_is_not_trusted(self):
        gh = th.FakeIssues([th.stored_issue(7, 10, login="mallory")])
        run = th.run_inbox(th.FakeTelegram([th.message_update(10, "진짜 글")]), gh)
        self.assertEqual(len(run.issues()), 1)

    def test_a_marker_that_is_not_at_the_top_of_the_body_is_not_trusted(self):
        gh = th.FakeIssues([th.stored_issue(7, 10, body="앞에 글이 있다\n" + ti.MARKER_FORMAT.format(10))])
        self.assertEqual(len(th.run_inbox(th.FakeTelegram([th.message_update(10, "진짜 글")]), gh).issues()), 1)

    def test_a_pull_request_with_the_marker_is_ignored(self):
        gh = th.FakeIssues([th.stored_issue(7, 10, pull=True)])
        self.assertEqual(len(th.run_inbox(th.FakeTelegram([th.message_update(10, "진짜 글")]), gh).issues()), 1)

    def test_other_update_ids_do_not_block(self):
        gh = th.FakeIssues([th.stored_issue(7, 9), th.stored_issue(8, 11)])
        self.assertEqual(len(th.run_inbox(th.FakeTelegram([th.message_update(10, "진짜 글")]), gh).issues()), 1)

    def test_the_search_reads_more_than_one_page(self):
        old = [th.stored_issue(number, 1000 + number) for number in range(2, 152)]       # 번호가 큰 150건이 첫 쪽(100건)과 둘째 쪽 앞을 채우고
        old.append(th.stored_issue(1, 10))                                                # 번호가 가장 작은 이슈(표지 10)는 둘째 쪽 끝에 있다
        gh = th.FakeIssues(old)
        run = th.run_inbox(th.FakeTelegram([th.message_update(10, "진짜 글")]), gh)
        self.assertEqual(run.issues(), [])
        pages = [item["query"] for item in gh.requests if item["method"] == "GET"]
        self.assertEqual(len(pages), 2)

    def test_the_search_stops_after_the_page_limit(self):
        many = [th.stored_issue(number, 5000 + number) for number in range(1, 401)]
        gh = th.FakeIssues(many)
        th.run_inbox(th.FakeTelegram([th.message_update(10, "진짜 글")]), gh)
        gets = [item for item in gh.requests if item["method"] == "GET"]
        self.assertEqual(len(gets), ti.SEARCH_PAGES)

    def test_listing_failure_stops_without_creating_or_confirming(self):
        for status, code in ((500, 0), (403, 1)):
            with self.subTest(status=status):
                tg = th.FakeTelegram([th.message_update(10, "하나")])
                gh = th.FakeIssues(failures=[("GET", "/issues", th.oh.http_error(status, "x"))] * 2)
                run = th.run_inbox(tg, gh)
                self.assertEqual(run.code, code)
                self.assertEqual(gh.new_issues(), [])
                self.assertEqual([item["update_id"] for item in tg.queue], [10])

    def test_non_list_listing_response_stops(self):
        gh = th.FakeIssues(failures=[("GET", "/issues", nh.FakeResponse(200, {"message": "x"}))])
        run = th.run_inbox(th.FakeTelegram([th.message_update(10, "하나")]), gh)
        self.assertEqual(run.issues(), [])

    def test_response_lost_after_creation_finds_the_marker_and_does_not_duplicate(self):
        tg = th.FakeTelegram([th.message_update(10, "하나")])
        gh = th.FakeIssues(failures=[("POST", "/issues", urllib.error.URLError("연결이 끊겼다"), True)])
        run = th.run_inbox(tg, gh)
        self.assertEqual(len(gh.new_issues()), 1)
        self.assertEqual(run.code, 0)
        self.assertIn("#101", tg.texts()[0])
        self.assertEqual(tg.queue, [])

    def test_a_creation_response_without_an_issue_number_is_treated_as_unknown_not_as_success(self):
        for response in (nh.FakeResponse(201, {"id": 1}), nh.FakeResponse(201, {"number": "7"}), nh.FakeResponse(201, {"number": 0}), nh.FakeResponse(201, {"number": True}),
                         nh.FakeResponse(201, [1, 2])):
            with self.subTest(body=response.read(30)):
                tg = th.FakeTelegram([th.message_update(10, "하나")])
                gh = th.FakeIssues(failures=[("POST", "/issues", response)])
                run = th.run_inbox(tg, gh)
                self.assertEqual((run.code, tg.sent), (0, []))
                self.assertEqual([item["update_id"] for item in tg.queue], [10])
                self.assertIn("::warning::", run.text)

    def test_5xx_without_creation_fails_and_does_not_confirm(self):
        tg = th.FakeTelegram([th.message_update(10, "하나")])
        gh = th.FakeIssues(failures=[("POST", "/issues", th.oh.http_error(502, "bad gateway"))])
        run = th.run_inbox(tg, gh)
        self.assertEqual((run.code, gh.new_issues()), (0, []))
        self.assertEqual([item["update_id"] for item in tg.queue], [10])

    def test_creating_is_never_retried_automatically(self):
        gh = th.FakeIssues(failures=[("POST", "/issues", th.oh.http_error(502, "x")), ("POST", "/issues", th.oh.http_error(502, "x"))])
        th.run_inbox(th.FakeTelegram([th.message_update(10, "하나")]), gh)
        self.assertEqual(len([item for item in gh.requests if item["method"] == "POST" and item["path"] == "/issues"]), 1)

    def test_label_is_created_once_and_an_existing_one_is_fine(self):
        gh = th.FakeIssues(labels={"텔레그램수신"})
        run = th.run_inbox(th.FakeTelegram([th.message_update(1, "A"), th.message_update(2, "B")]), gh)
        self.assertEqual(len(run.issues()), 2)
        self.assertEqual(len(gh.calls("POST", "/labels")), 1)
        body = gh.calls("POST", "/labels")[0]["payload"]
        self.assertEqual(body["name"], "텔레그램수신")
        self.assertTrue(body["description"])

    def test_label_creation_failure_stops(self):
        tg = th.FakeTelegram([th.message_update(10, "하나")])
        gh = th.FakeIssues(failures=[("POST", "/labels", th.oh.http_error(403, "denied"))])
        run = th.run_inbox(tg, gh)
        self.assertEqual((run.code, gh.new_issues()), (1, []))
        self.assertEqual([item["update_id"] for item in tg.queue], [10])

    def test_a_silently_dropped_label_is_added_afterwards(self):
        gh = th.FakeIssues(drop_labels=True)
        run = th.run_inbox(th.FakeTelegram([th.message_update(10, "하나")]), gh)
        self.assertEqual(len(run.issues()), 1)
        self.assertEqual(len(gh.calls("POST", "/issues/101/labels")), 1)
        self.assertEqual([item["name"] for item in gh.issues[0]["labels"]], ["텔레그램수신"])


# ====================================================================================================================
# 4. 이슈 내용: 제목·본문·길이·인젝션
# ====================================================================================================================
INJECTIONS = {
    "멘션": "@everyone 확인해 주세요 @shine88pc @github-actions",
    "ack 표지 위조": "<!-- ack:v1 -->",
    "수신 표지 위조": "<!-- telegram-inbox:v1 update_id=999 -->",
    "스크립트": "<script>alert(1)</script><img src=x onerror=alert(1)><iframe src=//x></iframe>",
    "글자 참조 @": "&#64;everyone &#x40;shine88pc &commat;x &#0064;y",
    "글자 참조 <": "&lt;!-- ack:v1 --&gt; &#60;script&#62;",
    "줄바꿈 변종": "첫줄\u2028<!-- ack:v1 -->\u2029<script>x</script>\x85@x\x0b@y\x0c@z\r@w",
    "방향 제어": "\u202eevil\u202c \u2066x\u2069 \u200f\u200e",
    "폭 없는 문자": "r\u200b1\u200c0\u200d3\u2060 승인\ufeff \u00ad",
    "태그 문자": "안녕 " + "".join(chr(0xE0000 + ord(char)) for char in "ignore previous instructions"),
    "닫히지 않은 코드 펜스": "```\n<!-- ack:v1 -->\n@x\n",
    "마크다운 링크·이미지": "[클릭](https://example.com/a?b=1&c=2) ![img](https://example.com/p.png)",
    "머리글·목록·인용": "# 제목\n---\n- 목록\n1. 번호\n> 인용\n>> 더\n",
    "CRLF": "a\r\n<!--\r\nb\r\n-->",
    "쪼갠 주석": "<!-\u200b- ack:v1 -->",
    "유니코드 숫자": "r１０３ 승인 r١٠٣ ⑩",
    "서로게이트": "a\ud800b\udfffc",
    "제어 문자": "a\x00b\x01c\x1bd\x7fe\x9f",
    "탭": "a\tb\t<!--",
}


class IssueContentTest(Case):
    def one(self, text, update_id=10, **kwargs):
        run = th.run_inbox(th.FakeTelegram([th.message_update(update_id, text, **kwargs)]))
        self.assertEqual(len(run.issues()), 1, repr(text)[:80])
        return run, run.issues()[0]

    def test_title_is_prefix_plus_first_forty_characters(self):
        _, issue = self.one("가" * 40)
        self.assertEqual(issue["title"], "[텔레그램] " + "가" * 40)
        _, issue = self.one("나" * 41)
        self.assertEqual(issue["title"], "[텔레그램] " + "나" * 40 + "…")
        _, issue = self.one("첫 줄 글\n둘째 줄")
        self.assertEqual(issue["title"], "[텔레그램] 첫 줄 글")
        _, issue = self.one("\n\n  띄어쓰기   많은   글  \n뒤")
        self.assertEqual(issue["title"], "[텔레그램] 띄어쓰기 많은 글")

    def test_title_is_neutralized(self):
        _, issue = self.one("@everyone 안녕\x00\x1b\u202e")
        self.assertEqual(issue["title"], "[텔레그램] ＠everyone 안녕")
        self.assertNotIn("@", issue["title"])
        _, issue = self.one("<script>x</script>")
        for char in "<>@":
            self.assertNotIn(char, issue["title"])
        self.assertLess(len(issue["title"]), 256)

    def test_a_secret_shaped_first_line_is_masked_in_the_title_too(self):
        key = "AIza" + "S" * 35
        _, issue = self.one(f"키는 {key} 입니다")
        self.assertNotIn(key, issue["title"])
        self.assertIn("***", issue["title"])

    def test_body_layout(self):
        _, issue = self.one("원문 첫 줄\n원문 둘째 줄")
        body = issue["body"]
        lines = body.split("\n")
        self.assertEqual(lines[0], "<!-- telegram-inbox:v1 update_id=10 -->")
        for needle in ("텔레그램으로 받은 글입니다", "접수일 뿐 승인이 아닙니다", "이 이슈는 공개입니다", "비밀번호·키·개인정보는 보내지 마세요", "보낸 시각: 2025-11-04 12:20 KST"):
            self.assertIn(needle, body)
        self.assertEqual(quote_of(body), "원문 첫 줄\n원문 둘째 줄")
        self.assertNotIn("답변 후보", body)
        assert_safe_body(self, body, 10)

    def test_every_injection_leaves_a_safe_body_and_title(self):
        for name, text in INJECTIONS.items():
            with self.subTest(name):
                _, issue = self.one(text, update_id=77)
                assert_safe_body(self, issue["body"], 77)
                for char in "<>@":
                    self.assertNotIn(char, issue["title"])
                self.assertEqual(ti.MARKER_RE.findall(issue["body"]), ["77"])
                for char in (chr(0x200B), chr(0x202E), chr(0xFEFF), chr(0xE0041), "\x00", "\x1b", "\x7f"):
                    self.assertNotIn(char, issue["body"])
                for shown in (issue["title"], issue["body"]):
                    for char in shown:       # 보이지 않는 서식 문자(방향 제어·폭 없는 공백·태그 문자)·제어 문자·짝 없는 서로게이트는 어떤 모양으로도 남지 않는다
                        self.assertTrue(char == "\n" or unicodedata.category(char) not in ("Cc", "Cf", "Cs"), (name, hex(ord(char))))
                        self.assertFalse(0xE0000 <= ord(char) <= 0xE007F, (name, hex(ord(char))))

    def test_code_fences_and_markdown_links_stay_as_written(self):
        text = "```py\nprint(1)\n```\n[링크](https://example.com/x?a=1&b=2) 와 `코드`"
        _, issue = self.one(text)
        self.assertEqual(quote_of(issue["body"]), text)

    def test_entity_like_ampersands_are_defanged_but_plain_ones_are_kept(self):
        _, issue = self.one("A & B &#64;x &lt;y&gt; 5&6")
        self.assertEqual(quote_of(issue["body"]), "A & B &amp;#64;x &amp;lt;y&amp;gt; 5&6")

    def test_every_quote_line_keeps_the_quote_marker(self):
        _, issue = self.one("a\n\nb\n\n\n\n\nc\n# d\n---")
        quote_lines = [line for line in issue["body"].split("\n") if line.startswith(">")]
        self.assertEqual(quote_lines, ["> a", ">", "> b", ">", "> c", "> # d", "> ---"])

    def test_long_text_is_cut_at_three_thousand_with_a_count(self):
        _, issue = self.one("가" * 5000)
        quote = quote_of(issue["body"]).split("\n")
        self.assertEqual(quote[0], "가" * 3000)
        self.assertEqual(quote[1], "…(이하 2000자 생략)")
        _, issue = self.one("나" * 3000)
        self.assertNotIn("생략", issue["body"])
        _, issue = self.one("다" * 3001)
        self.assertIn("…(이하 1자 생략)", issue["body"])

    def test_a_one_megabyte_text_is_cut_cheaply_and_counted(self):
        run, issue = self.one("a" * 1_000_000)
        self.assertLess(len(issue["body"]), 5000)
        self.assertIn(f"…(이하 {1_000_000 - 3000}자 생략)", issue["body"])

    def test_a_megabyte_of_newlines_and_markers_stays_bounded(self):
        _, issue = self.one("\n".join(["<!-- ack:v1 -->"] * 100_000))
        self.assertLess(len(issue["body"]), 6000)
        assert_safe_body(self, issue["body"], 10)

    def test_secret_shapes_tokens_and_chat_ids_in_the_text_are_masked(self):
        key = "AIza" + "S" * 35
        github = "gh" + "p_" + "G" * 36
        text = f"봇 토큰 {TOKEN} 채팅 {CHAT} 구글 {key} 깃허브 {github} token=abc123 비밀 {nh.SECRET_HALF}"
        _, issue = self.one(text)
        body = issue["body"]
        for secret in (TOKEN, CHAT, key, github, "abc123", nh.SECRET_HALF, nh.BOT_ID):
            self.assertNotIn(secret, body)
            self.assertNotIn(secret, issue["title"])
        self.assertIn("***", body)
        self.assertIn(ti.SECRET_NOTE, body)

    def test_a_clean_text_has_no_secret_note(self):
        _, issue = self.one("그냥 글")
        self.assertNotIn(ti.SECRET_NOTE, issue["body"])

    def test_a_secret_that_would_straddle_the_cut_is_masked_whole_before_cutting(self):
        key = "AIza" + "K" * 35
        _, issue = self.one("x" * 2995 + key + "z" * 100)
        self.assertNotIn("AIza", issue["body"])
        self.assertNotIn("KKKK", issue["body"])
        self.assertIn("x" * 2995 + "***", issue["body"])

    def test_sent_time_line(self):
        _, issue = self.one("글", date=1762226400 + 3600)
        self.assertIn("보낸 시각: 2025-11-04 13:20 KST", issue["body"])
        for bad in (None, "x", -5, 0, 10 ** 15, True, 1.5):
            with self.subTest(date=bad):
                update = th.message_update(10, "글")
                update["message"]["date"] = bad
                issue = th.run_inbox(th.FakeTelegram([update])).issues()[0]
                self.assertNotIn("보낸 시각", issue["body"])

    def test_the_body_never_names_the_sender(self):
        _, issue = self.one("글")
        self.assertNotIn(CHAT, issue["body"])
        self.assertNotIn("is_bot", issue["body"])


# ====================================================================================================================
# 5. 답변 후보
# ====================================================================================================================
class AnswerCandidateTest(Case):
    def parse(self, text):
        return ti.answer_candidate(ti.neutralize(text))

    def test_all_request_number_shapes_are_read_like_the_operator_loop(self):
        for shape in ("r103", "R103", "r-103", "R-103", "r 103"):
            with self.subTest(shape=shape):
                candidate = self.parse(f"{shape} 승인 1")
                self.assertEqual(candidate, ti.Candidate("R-103", "승인", "1", 0))
                self.assertEqual(candidate.request_id, loop.normalize_request_id(shape))

    def test_answer_words_choice_and_memo(self):
        cases = {
            "r103 승인 1": ("R-103", "승인", "1", 0),
            "r-103 거절 A=2 메모를 길게 적습니다": ("R-103", "거절", "A=2", len("메모를 길게 적습니다")),
            "r103 보류": ("R-103", "보류", "", 0),
            "r103 보류.": ("R-103", "보류", "", 0),
            "r103 했어요 가": ("R-103", "했어요", "가", 0),
            "r103 문제 B 여기가 안 열려요": ("R-103", "문제", "B", len("여기가 안 열려요")),
            "r103 승인 A=2,B=1 괜찮아요": ("R-103", "승인", "A=2,B=1", len("괜찮아요")),
            "r103 승인 1234 길어서 메모": ("R-103", "승인", "", len("1234 길어서 메모")),
            "r103 승인 좋아요 그리고": ("R-103", "승인", "좋아요", len("그리고")),
            "r103: 승인 1": ("R-103", "승인", "1", 0),
            "  \n r103 승인": ("R-103", "승인", "", 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(tuple(self.parse(text)), expected)

    def test_number_only_and_unknown_words_give_a_number_candidate_without_an_answer(self):
        for text in ("r103", "R-103", "r 103", "r103 승인합니다", "r103 ok", "r103 좋아요"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text), ti.Candidate("R-103", "", "", 0))

    def test_no_candidate_when_the_text_does_not_start_with_a_request_number(self):
        for text in ("안녕하세요", "그런데 r103 승인", "r10", "r10 승인", "r1034 승인", "r103x 승인", "r103승인", "r-10 거절", "rr103", "r  103", "r１０３ 승인",
                     "r١٠٣ 승인", "R-1O3", "req103 승인", "PR103 승인", "103 승인", ""):
            with self.subTest(text=text):
                self.assertIsNone(self.parse(text))

    def test_invisible_characters_are_removed_before_reading(self):
        self.assertEqual(self.parse("r\u200b1\u200c03 승인").request_id, "R-103")

    def test_the_candidate_line_is_in_the_body_with_the_no_approval_note(self):
        run = self.run_with(th.message_update(10, "r103 승인 1 메모"))
        body = run.issues()[0]["body"]
        self.assertIn("답변 후보(참고용): 요청 **r103** · 답 **승인** · 선택 **1** · 메모 있음(2자)", body)
        self.assertIn(ti.CANDIDATE_NOTE, body)
        self.assertIn("참고용이고 승인이 아닙니다", body)               # 이슈 맨 위 안내와 별개로, 후보 줄 바로 아래에도 한 번 더
        self.assertIn("`[답변]` 양식", body)
        self.assertIn("G-S9", body)
        assert_safe_body(self, body, 10)

    def test_number_only_line_and_no_line_for_plain_text(self):
        body = self.run_with(th.message_update(10, "R-103")).issues()[0]["body"]
        self.assertIn("요청 번호 후보(참고용): **r103**", body)
        self.assertIn("G-S9", body)
        plain = self.run_with(th.message_update(10, "그냥 글")).issues()[0]["body"]
        self.assertNotIn("후보", plain)
        self.assertNotIn("G-S9", plain)

    def test_a_candidate_never_changes_what_the_code_does(self):
        """답변 후보는 본문 한 줄일 뿐이다 — 승인 낱말이 있어도 이슈 하나·접수 확인 하나 외에는 아무 호출도 없다."""
        run = self.run_with(th.message_update(10, "r103 승인 1"))
        self.assertEqual([(item["method"], item["path"]) for item in run.gh.requests], [("GET", "/issues"), ("POST", "/labels"), ("POST", "/issues")])
        self.assertEqual(run.tg.methods(), ["getUpdates", "sendMessage", "getUpdates"])
        self.assertNotIn("승인", run.tg.texts()[0].replace("승인은 [답하기] 양식으로", ""))

    def test_the_source_never_imports_the_approval_decision_code(self):
        source = open(_bootstrap.ROOT / "pipeline" / "telegram_inbox.py", encoding="utf-8").read()
        for name in ("parse_reply", "run_ack", "post_ack", "ack_comment"):
            self.assertNotIn(name, source)


# ====================================================================================================================
# 6. 오류 분류·비밀 없음·인자
# ====================================================================================================================
class ErrorHandlingTest(Case):
    def poll_fail(self, outcome, times=2, text="하나"):
        tg = th.FakeTelegram([th.message_update(10, text)], failures=[{"method": "getUpdates", "outcome": outcome, "times": times}])
        return th.run_inbox(tg)

    def assert_quiet_failure(self, run):
        """이슈도 텔레그램 알림(답)도 없다."""
        self.assertEqual(run.issues(), [])
        self.assertEqual(run.tg.sent, [])
        self.assertEqual(run.gh.requests, [])

    def test_401_and_404_mean_a_bad_token_and_fail_the_run(self):
        for status, needle in ((401, "토큰이 틀렸거나 폐기됐습니다"), (404, "봇을 찾을 수 없습니다")):
            with self.subTest(status=status):
                run = self.poll_fail(nh.http_error(status, "Unauthorized"))
                self.assertEqual(run.code, 1)
                self.assertIn(needle, run.text)
                self.assertIn("::error::", run.text)
                self.assert_quiet_failure(run)

    def test_409_webhook_is_named_and_the_webhook_is_left_alone(self):
        tg = th.FakeTelegram([th.message_update(10, "하나")], webhook=True)
        run = th.run_inbox(tg)
        self.assertEqual(run.code, 1)
        self.assertIn("웹훅", run.text)
        self.assertIn("409", run.text)
        self.assertEqual(tg.methods(), ["getUpdates"])
        self.assert_quiet_failure(run)

    def test_409_conflict_between_two_readers_is_a_different_line(self):
        run = self.poll_fail(nh.http_error(409, "Conflict: terminated by other getUpdates request; make sure that only one bot instance is running"))
        self.assertEqual(run.code, 1)
        self.assertIn("동시에 읽고 있습니다", run.text)
        self.assertNotIn("웹훅이 설정돼", run.text)

    def test_400_and_403_fail_the_run(self):
        for status in (400, 403):
            run = self.poll_fail(nh.http_error(status, "Bad Request"))
            self.assertEqual(run.code, 1, status)
            self.assert_quiet_failure(run)

    def test_429_waits_the_capped_retry_after_once_then_reads(self):
        run = self.poll_fail(nh.http_error(429, "Too Many Requests", retry_after=3), times=1)
        self.assertEqual(run.code, 0)
        self.assertEqual(len(run.issues()), 1)
        self.assertIn(3, run.clock.sleeps)
        run = self.poll_fail(nh.http_error(429, "x", retry_after=999), times=1)
        self.assertIn(ti.RETRY_AFTER_MAX, run.clock.sleeps)
        run = self.poll_fail(nh.http_error(429, "x", header_retry=4), times=1)
        self.assertIn(4, run.clock.sleeps)

    def test_429_twice_is_a_warning_not_a_failure(self):
        run = self.poll_fail(nh.http_error(429, "Too Many Requests", retry_after=2), times=2)
        self.assertEqual(run.code, 0)
        self.assertIn("429", run.text)
        self.assertIn("::warning::", run.text)
        self.assertNotIn("::error::", run.text)
        self.assert_quiet_failure(run)

    def test_network_timeout_and_5xx_retry_once_then_warn(self):
        for outcome in (urllib.error.URLError("x"), TimeoutError("t"), nh.http_error(502, "bad"), OSError("o"), ValueError("v")):
            with self.subTest(outcome=type(outcome).__name__):
                run = self.poll_fail(outcome, times=1)
                self.assertEqual(len(run.issues()), 1, "한 번 실패해도 다시 시도해 읽는다")
                self.assertIn(ti.NETWORK_RETRY_WAIT, run.clock.sleeps)
                run = self.poll_fail(outcome, times=2)
                self.assertEqual(run.code, 0)
                self.assertIn("::warning::", run.text)
                self.assert_quiet_failure(run)

    def test_bad_responses_are_a_warning(self):
        for response in (nh.FakeResponse(200, "not json"), nh.FakeResponse(200, {"ok": False, "result": []}), nh.FakeResponse(200, {"ok": True, "result": {"a": 1}}),
                         nh.FakeResponse(200, {"ok": True}), nh.FakeResponse(200, [1, 2]), nh.FakeResponse(204, {"ok": True, "result": []}),
                         nh.FakeResponse(200, b"\xff\xfe\x00")):
            with self.subTest(body=response.read(40)):
                run = self.poll_fail(response, times=1)
                self.assertEqual(run.code, 0)
                self.assertIn("텔레그램의 응답을 읽을 수 없습니다", run.text)
                self.assert_quiet_failure(run)

    def test_an_oversized_response_is_refused(self):
        big = nh.FakeResponse(200, b'{"ok": true, "result": [' + b"1," * (ti.MAX_RESPONSE_BYTES // 2 + 10) + b"1]}")
        run = self.poll_fail(big, times=1)
        self.assertIn("텔레그램의 응답을 읽을 수 없습니다", run.text)
        self.assertEqual(run.issues(), [])

    def test_a_failing_confirm_after_creating_issues_is_reported_but_the_issues_stay(self):
        tg = th.FakeTelegram([th.message_update(10, "하나")], failures=[{"method": "getUpdates", "when": lambda payload: "offset" in payload,
                                                                          "outcome": nh.http_error(401, "Unauthorized"), "times": 1}])
        run = th.run_inbox(tg)
        self.assertEqual(len(run.issues()), 1)
        self.assertEqual(run.code, 1)

    def test_missing_secrets_are_skipped_with_exit_zero_and_no_network_use(self):
        for env in ({"GITHUB_TOKEN": th.GH_TOKEN}, {"GITHUB_TOKEN": th.GH_TOKEN, "TELEGRAM_BOT_TOKEN": TOKEN}, {"GITHUB_TOKEN": th.GH_TOKEN, "TELEGRAM_CHAT_ID": CHAT},
                    {"GITHUB_TOKEN": th.GH_TOKEN, "TELEGRAM_BOT_TOKEN": "  ", "TELEGRAM_CHAT_ID": ""}):
            with self.subTest(env=sorted(env)):
                run = th.run_inbox(th.FakeTelegram([th.message_update(10, "하나")]), env=env)
                self.assertEqual((run.code, run.lines), (0, [ti.SKIP_LINE]))
                self.assertEqual((run.tg.calls, run.gh.requests), ([], []))

    def test_without_a_github_token_nothing_is_read(self):
        env = dict(th.make_env())
        del env["GITHUB_TOKEN"]
        lines = []
        tg = th.FakeTelegram([th.message_update(10, "하나")])
        code = ti.main([], environ=env, out=lines.append, opener=tg, sleep=lambda seconds: None)
        self.assertEqual((code, lines), (0, [ti.NO_GITHUB_LINE]))
        self.assertEqual(tg.calls, [])
        self.assertEqual(len(tg.queue), 1)

    def test_malformed_telegram_secrets_stop_before_any_call(self):
        for token in ("bad", "123:abc", TOKEN + " x", "bot" + TOKEN, '"' + TOKEN + '"'):
            with self.subTest(token=token[:6]):
                run = th.run_inbox(th.FakeTelegram([th.message_update(10, "하나")]), env=th.make_env(TELEGRAM_BOT_TOKEN=token))
                self.assertEqual(run.code, 1)
                self.assertIn("봇 토큰 모양이 올바르지 않습니다", run.text)
                self.assertEqual(run.tg.calls, [])
        for chat in ("@운영자", "@chanceblog", "-100123", "abc", "0", "1.5", "12 34", "123456789012345678"):
            with self.subTest(chat=chat):
                run = th.run_inbox(th.FakeTelegram([th.message_update(10, "하나")]), env=th.make_env(TELEGRAM_CHAT_ID=chat))
                self.assertEqual(run.code, 1)
                self.assertIn("채팅 ID 가 양의 정수가 아닙니다", run.text)
                self.assertEqual(run.tg.calls, [])

    def test_invisible_characters_in_the_secrets_are_cleaned_like_the_notifier(self):
        env = th.make_env(TELEGRAM_BOT_TOKEN="\u200b" + TOKEN + "\ufeff", TELEGRAM_CHAT_ID=" " + CHAT + "\u2060")
        run = th.run_inbox(th.FakeTelegram([th.message_update(10, "하나")]), env=env)
        self.assertEqual(len(run.issues()), 1)

    def test_the_command_takes_no_arguments_and_never_echoes_them(self):
        secret = "ARG-" + TOKEN
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as caught:
                ti.main([secret], environ={})
        self.assertEqual(caught.exception.code, 2)
        for text in (out.getvalue(), err.getvalue()):
            self.assertNotIn(secret, text)
            self.assertNotIn(TOKEN, text)
        self.assertIn(ti.USAGE_ERROR_LINE, err.getvalue())

    def test_unexpected_exceptions_print_only_the_class_name_and_fail(self):
        lines = []
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        with mock.patch.object(ti.Telegram, "get_updates", side_effect=RuntimeError(url + CHAT)):
            code = ti.main([], environ=th.make_env(), out=lines.append, opener=th.FakeTelegram(), api=ti.loop.GitHub(th.REPO, th.GH_TOKEN, opener=th.FakeIssues()))
        self.assertEqual(code, 1)
        self.assertIn("RuntimeError", "\n".join(lines))
        self.assertEqual(nh.leaks(*lines), [])


# ====================================================================================================================
# 7. 토큰·채팅 ID 비노출(가짜 값을 심어 모든 출구를 훑는다)
# ====================================================================================================================
class SecretLeakTest(Case):
    def scenarios(self):
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        hostile = {"description": f"Unauthorized: {TOKEN} chat {CHAT}", "ok": False, "error_code": 401}
        text_with_secrets = f"내 토큰은 {TOKEN} 이고 채팅은 {CHAT}"
        yield "정상", th.FakeTelegram([th.message_update(10, text_with_secrets), th.message_update(11, "r103 승인 1")])
        yield "비밀이 든 글", th.FakeTelegram([th.message_update(10, text_with_secrets)])
        yield "401 설명에 비밀", th.FakeTelegram([th.message_update(10, "x")], failures=[{"method": "getUpdates", "times": 9, "outcome": th.nh.http_error(401, "x", raw=json.dumps(hostile).encode())}])
        yield "409 웹훅", th.FakeTelegram([th.message_update(10, "x")], webhook=True)
        yield "429", th.FakeTelegram([th.message_update(10, "x")], failures=[{"method": "getUpdates", "times": 9, "outcome": nh.http_error(429, f"slow {TOKEN}", retry_after=2)}])
        for outcome in (urllib.error.URLError(url), urllib.error.URLError(OSError(url)), OSError(url + CHAT), ValueError(url), RuntimeError(url), TimeoutError(url),
                        ConnectionError(url), UnicodeError(url), urllib.error.HTTPError(url, 500, url + TOKEN, {}, None)):
            yield f"예외 {type(outcome).__name__}", th.FakeTelegram([th.message_update(10, "x")], failures=[{"method": "getUpdates", "times": 9, "outcome": outcome}])
        yield "접수 확인 실패", th.FakeTelegram([th.message_update(10, "x")], failures=[{"method": "sendMessage", "times": 9, "outcome": nh.http_error(403, f"Forbidden {TOKEN}")}])
        yield "접수 확인 예외", th.FakeTelegram([th.message_update(10, "x")], failures=[{"method": "sendMessage", "times": 9, "outcome": urllib.error.URLError(url + CHAT)}])
        yield "응답 본문이 비밀", th.FakeTelegram([th.message_update(10, "x")], failures=[{"method": "getUpdates", "times": 9, "outcome": nh.FakeResponse(200, f"{TOKEN} {CHAT}")}])

    def test_a_github_error_description_with_the_chat_id_is_scrubbed_in_the_output(self):
        """GitHub 가 준 설명에 채팅 ID 가 섞여 있어도(토큰 모양이 아니라 mask 가 못 가린다) 모든 출력은 한 번 더 지워서 나간다."""
        tg = th.FakeTelegram([th.message_update(10, "하나")])
        gh = th.FakeIssues(failures=[("POST", "/issues", th.oh.http_error(403, f"denied for chat {CHAT} and bot {nh.BOT_ID}"))])
        run = th.run_inbox(tg, gh)
        self.assertEqual(run.code, 1)
        self.assertIn("HTTP 403", run.text)
        self.assertEqual(nh.leaks(run.text), [])

    def test_no_output_exit_leaks_the_token_or_the_chat_id(self):
        for name, tg in self.scenarios():
            with self.subTest(name):
                gh = th.FakeIssues()
                clock = nh.Clock()
                api = ti.loop.GitHub(th.REPO, th.GH_TOKEN, opener=gh, sleep=clock.sleep)
                code, out, err = th.capture_streams(ti.main, [], environ=th.make_env(), out=print, opener=tg, sleep=clock.sleep, clock=clock.clock, api=api)
                self.assertIn(code, (0, 1))
                issues = " ".join(item["title"] + item["body"] for item in gh.new_issues())
                replies = " ".join(tg.texts())
                self.assertEqual(nh.leaks(out, err), [], f"{name}: stdout·stderr")
                self.assertEqual(nh.leaks(issues), [], f"{name}: 이슈 제목·본문")
                self.assertEqual(nh.leaks(replies), [], f"{name}: 텔레그램 답")

    def test_the_summary_file_never_leaks_either(self):
        for name, tg in self.scenarios():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "summary.md")
                run = th.run_inbox(tg, env=th.make_env(GITHUB_STEP_SUMMARY=path))
                text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
                self.assertEqual(nh.leaks(text, *run.lines), [], name)

    def test_message_text_is_never_logged_only_counts(self):
        marker = "고유한본문표시ZXQ"
        run = self.run_with(th.message_update(10, marker + " 비밀 아님"), th.message_update(11, marker, chat_id=th.OTHER_ID))
        self.assertNotIn(marker, run.text)
        self.assertNotIn(marker, " ".join(run.tg.texts()))

    def test_response_json_is_never_logged(self):
        marker = "응답본문표시QWX"
        update = th.message_update(10, "x")
        update["message"]["from"]["first_name"] = marker
        update["message"]["chat"]["username"] = marker
        run = self.run_with(update)
        self.assertNotIn(marker, run.text)
        self.assertNotIn(marker, run.issues()[0]["body"])

    def test_the_notifier_and_client_reprs_hide_the_secrets(self):
        client = ti.Telegram(TOKEN)
        for text in (repr(client), str(client)):
            self.assertEqual(nh.leaks(text), [])

    def test_source_never_formats_exceptions_or_response_bodies_into_text(self):
        source = open(_bootstrap.ROOT / "pipeline" / "telegram_inbox.py", encoding="utf-8").read()
        client = source[source.index("class Telegram:"):source.index("# ---- 받은 글 읽기·소독")]
        for forbidden in ("str(exc)", "repr(exc)", "{exc}", "exc.args", "exc.reason", "__cause__", "exc.url", "exc.filename", "traceback", "print(", "logging"):
            self.assertNotIn(forbidden, client, forbidden)
        code = source.split('"""', 2)[2]                       # 모듈 설명(독스트링)은 원칙을 글로 적은 곳이라 뺀다
        for forbidden in ("import requests", "from requests", "add-mask", "import http", "from http"):
            self.assertNotIn(forbidden, code, forbidden)
        self.assertNotIn("print(", code.replace("out=print", ""))
        self.assertIn("type(exc).__name__", source)

    def test_the_token_shape_matches_the_notifier(self):
        self.assertEqual(ti.TOKEN_RE.pattern, notify._TOKEN_RE.pattern)

    def test_error_lines_use_only_fixed_texts(self):
        for reason, (text, code) in ti.POLL_FAILURES.items():
            self.assertIn(code, (0, 1), reason)
            self.assertEqual(nh.leaks(text), [], reason)
            self.assertNotIn("{", text)


# ====================================================================================================================
# 8. 진짜 urllib 경로(지역 가짜 서버) — 예외 문구·요청 주소 처리를 실제 표준 라이브러리로 확인
# ====================================================================================================================
class LocalTelegramServer:
    """127.0.0.1 의 지역 서버(스레드). 요청 경로·본문을 기록하고 준비한 (상태, 본문)을 차례로 돌려준다(마지막은 반복)."""

    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                outer.seen.append((self.path, json.loads(self.rfile.read(length).decode("utf-8") or "{}")))
                status, body = outer.replies.pop(0) if len(outer.replies) > 1 else outer.replies[0]
                raw = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        return False


class RealUrllibTest(Case):
    allow_loopback = True

    def run_against(self, server, gh=None, **env):
        gh = gh or th.FakeIssues()
        clock = nh.Clock()
        lines = []
        api = ti.loop.GitHub(th.REPO, th.GH_TOKEN, opener=gh, sleep=clock.sleep)
        with mock.patch.object(notify, "API_BASE", server.base):
            code = ti.main([], environ=th.make_env(**env), out=lines.append, sleep=clock.sleep, clock=clock.clock, api=api, base=server.base)
        return code, lines, gh

    def test_a_real_round_trip_creates_the_issue_and_confirms(self):
        update = th.message_update(10, "진짜 소켓 글")
        with LocalTelegramServer((200, {"ok": True, "result": [update]}), (200, {"ok": True, "result": {"message_id": 1}}), (200, {"ok": True, "result": []})) as server:
            code, lines, gh = self.run_against(server)
        self.assertEqual(code, 0, lines)
        self.assertEqual([item["title"] for item in gh.new_issues()], ["[텔레그램] 진짜 소켓 글"])
        paths = [path for path, _body in server.seen]
        self.assertEqual(paths, [f"/bot{TOKEN}/getUpdates", f"/bot{TOKEN}/sendMessage", f"/bot{TOKEN}/getUpdates"])
        self.assertEqual(server.seen[2][1]["offset"], 11)

    def test_a_real_401_response_is_classified_without_leaking(self):
        body = {"ok": False, "error_code": 401, "description": f"Unauthorized {TOKEN}"}
        with LocalTelegramServer((401, body)) as server:
            code, lines, gh = self.run_against(server)
        self.assertEqual(code, 1)
        self.assertEqual(nh.leaks("\n".join(lines)), [])
        self.assertIn("토큰이 틀렸거나 폐기됐습니다", "\n".join(lines))
        self.assertEqual(gh.new_issues(), [])

    def test_a_real_409_webhook_response(self):
        body = {"ok": False, "error_code": 409, "description": "Conflict: can't use getUpdates method while webhook is active"}
        with LocalTelegramServer((409, body)) as server:
            code, lines, _gh = self.run_against(server)
        self.assertEqual(code, 1)
        self.assertIn("웹훅", "\n".join(lines))

    def test_a_real_429_response_waits_and_gives_up_with_a_warning(self):
        body = {"ok": False, "error_code": 429, "description": "Too Many Requests: retry after 1", "parameters": {"retry_after": 1}}
        with LocalTelegramServer((429, body)) as server:
            code, lines, _gh = self.run_against(server)
        self.assertEqual(code, 0)
        self.assertIn("::warning::", "\n".join(lines))
        self.assertEqual(len(server.seen), 2)

    def test_a_real_connection_refusal_is_a_network_warning_with_no_address_in_the_output(self):
        server = LocalTelegramServer((200, {"ok": True, "result": []}))
        base = server.base                     # 서버를 시작하지 않은 포트 — 연결이 거절된다
        server.server.server_close()
        code, lines, _gh = self.run_against(type("S", (), {"base": base})())
        self.assertEqual(code, 0)
        text = "\n".join(lines)
        self.assertIn("연결하지 못했습니다", text)
        for needle in (TOKEN, "127.0.0.1", "bot", "http://"):
            self.assertNotIn(needle, text)

    def test_a_real_html_error_page_is_a_bad_response_not_a_crash(self):
        with LocalTelegramServer((200, "<html>proxy</html>")) as server:
            code, lines, _gh = self.run_against(server)
        self.assertEqual(code, 0)
        self.assertIn("응답을 읽을 수 없습니다", "\n".join(lines))


# ====================================================================================================================
# 9. 작은 함수 단위
# ====================================================================================================================
class UnitTest(Case):
    def test_classify(self):
        self.assertEqual(ti.classify("ok", 200, {"ok": True, "result": []}), "ok")
        self.assertEqual(ti.classify("ok", 200, {"ok": True, "result": {}}), "bad_response")
        self.assertEqual(ti.classify("ok", 200, {"ok": False, "result": []}), "bad_response")
        self.assertEqual(ti.classify("ok", 200, None), "bad_response")
        self.assertEqual(ti.classify("ok", 201, {"ok": True, "result": []}), "bad_response")
        self.assertEqual(ti.classify("http", 401, None), "unauthorized")
        self.assertEqual(ti.classify("http", 404, None), "not_found")
        self.assertEqual(ti.classify("http", 409, {"description": "Conflict: webhook is active"}), "webhook")
        self.assertEqual(ti.classify("http", 409, {"description": "terminated by other getUpdates request"}), "conflict")
        self.assertEqual(ti.classify("http", 409, None), "conflict")
        self.assertEqual(ti.classify("http", 429, None), "rate_limited")
        self.assertEqual(ti.classify("http", 500, None), "server_error")
        self.assertEqual(ti.classify("http", 503, None), "server_error")
        self.assertEqual(ti.classify("http", 400, None), "bad_request")
        self.assertEqual(ti.classify("http", None, None), "bad_request")
        self.assertEqual(ti.classify("timeout", None, None), "timeout")
        self.assertEqual(ti.classify("network", None, None), "network")
        for reason in ("unauthorized", "not_found", "webhook", "conflict", "bad_request", "rate_limited", "server_error", "network", "timeout", "bad_response"):
            self.assertIn(reason, ti.POLL_FAILURES)

    def test_retry_after(self):
        self.assertEqual(ti._retry_after({"parameters": {"retry_after": 3}}, None), 3)
        self.assertEqual(ti._retry_after({"parameters": {"retry_after": 0}}, None), 1)
        self.assertEqual(ti._retry_after({"parameters": {"retry_after": 500}}, None), ti.RETRY_AFTER_MAX)
        self.assertEqual(ti._retry_after(None, {"Retry-After": "4"}), 4)
        self.assertEqual(ti._retry_after(None, None), 1)
        self.assertEqual(ti._retry_after({"parameters": {"retry_after": "x"}}, None), 1)
        self.assertEqual(ti._retry_after({"parameters": {"retry_after": float("inf")}}, None), 1)

    def test_neutralize(self):
        self.assertEqual(ti.neutralize("a\r\nb\rc\u2028d\u2029e\x85f"), "a\nb\nc\nd\ne\nf")
        self.assertEqual(ti.neutralize("a\tb"), "a b")
        self.assertEqual(ti.neutralize("@a<b>c"), "＠a＜b＞c")
        self.assertEqual(ti.neutralize("\n\n\n\n글\n\n\n\n"), "글")
        self.assertEqual(ti.neutralize("가\u200b나\u202e다"), "가나다")
        self.assertEqual(ti.neutralize("한글과 😀 이모지"), "한글과 😀 이모지")

    def test_prepare_text_masks_everything_it_reads_and_counts_the_rest(self):
        key = "AIza" + "K" * 35
        clean, rest, masked = ti.prepare_text("x" * 100 + key + " " + "z" * 100, lambda value: notify.mask(value))
        self.assertTrue(masked)
        self.assertEqual(clean, "x" * 100 + "*** " + "z" * 100)
        clean, rest, masked = ti.prepare_text("y" * (ti.CLEAN_CAP + 50), lambda value: value)
        self.assertEqual((len(clean), rest, masked), (ti.CLEAN_CAP, 50, False))

    def test_read_update_requires_ints_and_a_private_chat(self):
        update = th.message_update(3, "글")
        self.assertEqual(ti.read_update(update, th.CHAT_INT), ti.Incoming(3, "text", "글", th.T0))
        self.assertEqual(ti.read_update(update, th.CHAT_INT + 1).kind, "skip")
        for bad in (None, 5, "x", [], {}, {"update_id": True}, {"update_id": -1}, {"update_id": 1.5}, {"update_id": "3"}):
            self.assertIsNone(ti.read_update(bad, th.CHAT_INT), bad)

    def test_build_title_and_marker(self):
        self.assertEqual(ti.build_title(""), "[텔레그램] (내용 없음)")
        self.assertEqual(ti.build_title("\n  \n첫 줄"), "[텔레그램] 첫 줄")
        self.assertEqual(ti.MARKER_FORMAT.format(7), "<!-- telegram-inbox:v1 update_id=7 -->")
        self.assertEqual(ti.MARKER_RE.match("<!-- telegram-inbox:v1 update_id=7 -->\n본문").group(1), "7")
        self.assertIsNone(ti.MARKER_RE.match("<!-- telegram-inbox:v2 update_id=7 -->"))
        self.assertIsNone(ti.MARKER_RE.match("<!-- telegram-inbox:v1 update_id=x -->"))
        self.assertIsNone(ti.MARKER_RE.match("<!-- telegram-inbox:v1 update_id=1234567890123456 -->"))

    def test_constants_match_the_brief(self):
        self.assertEqual((ti.MAX_ISSUES, ti.QUOTE_LIMIT, ti.TITLE_LIMIT, ti.UPDATES_LIMIT, ti.ISSUE_GAP_SECONDS), (5, 3000, 40, 5, 1.0))
        self.assertEqual((ti.MAX_RESPONSE_BYTES, ti.TIMEOUT_SECONDS, ti.MAX_SIDE_REPLIES, ti.MAX_MESSAGES), (4_000_000, 15, 3, 8))
        self.assertEqual((ti.LABEL, ti.TITLE_PREFIX), ("텔레그램수신", "[텔레그램] "))
        self.assertLessEqual(ti.UPDATES_LIMIT, ti.MAX_ISSUES)              # 한 묶음이 한 실행의 이슈 상한을 넘지 않는다(응답이 부풀어도 상한 안쪽 — 독립 검증 R3)
        self.assertEqual(ti.BOT_LOGIN, "github-actions[bot]")

    def test_the_marker_and_label_are_what_the_reader_documents_say(self):
        text = open(_bootstrap.ROOT / "docs" / "TELEGRAM_INBOX.md", encoding="utf-8").read() if (_bootstrap.ROOT / "docs" / "TELEGRAM_INBOX.md").exists() else ""
        for needle in (ti.LABEL, "telegram-inbox:v1", ti.BOT_LOGIN):
            self.assertIn(needle, text)


# ====================================================================================================================
# 10. 독립 검증 지적의 고침(필수 M1 + 권장 R1~R5·R7) — 고친 곳마다 새로 어겨 보는 변이 점검이 이 시험으로 잡는다
# ====================================================================================================================
ZW, WJ, BOM = chr(0x200B), chr(0x2060), chr(0xFEFF)        # 폭 없는 공백·단어 결합자·BOM — 시험 소스에 보이지 않는 문자를 두지 않으려고 코드 포인트로 만든다


def outside_quote_and_code(body):
    """본문에서 인용 블록(`>` 줄)과 인라인 코드 표시를 뺀 나머지 — 코드가 쓴 고정 문장만 남는다."""
    return re.sub(r"`[^`\n]*`", "", "\n".join(line for line in body.split("\n") if not line.startswith(">")))


class ReviewFixesTest(Case):
    def one(self, text, update_id=10, **kwargs):
        run = th.run_inbox(th.FakeTelegram([th.message_update(update_id, text, **kwargs)]))
        self.assertEqual(len(run.issues()), 1, repr(text)[:80])
        return run, run.issues()[0]

    # -- M1: 보이지 않는 문자로 쪼갠 비밀 ---------------------------------------------------------------------------------------
    def test_prepare_text_scrubs_again_after_the_invisible_characters_are_gone(self):
        key = "AIza" + "S" * 35
        clean, rest, masked = ti.prepare_text(key[:10] + ZW + key[10:], notify.mask)
        self.assertEqual((clean, rest, masked), ("***", 0, True))
        clean, rest, masked = ti.prepare_text("그냥 글 " + ZW + "입니다", notify.mask)
        self.assertEqual((clean, rest, masked), ("그냥 글 입니다", 0, False))        # 가릴 것이 없으면 가렸다고 하지 않는다

    def test_secrets_split_by_invisible_characters_are_masked_in_the_body_and_the_title(self):
        key = "AIza" + "S" * 35
        github = "gh" + "p_" + "G" * 36
        cases = {
            "구글 키": (key, key[:10] + ZW + key[10:], "S" * 8),
            "깃허브 토큰": (github, github[:8] + BOM + github[8:], "G" * 8),
            "봇 토큰(비밀 절반 한가운데)": (TOKEN, TOKEN[:20] + WJ + TOKEN[20:], "ZZZZZZZZ"),
            "봇 토큰(봇 번호 한가운데)": (TOKEN, TOKEN[:5] + ZW + TOKEN[5:], "ZZZZZZZZ"),
            "채팅 ID": (CHAT, CHAT[:3] + ZW + CHAT[3:], CHAT[3:]),
            "token= 꼴의 이름": ("token=abc123", "tok" + ZW + "en=abc123", "abc123"),
        }
        for name, (secret, split, fragment) in cases.items():
            with self.subTest(name):
                self.assertNotIn(secret, split)                      # 쪼갠 모양은 가리기 한 번만으로는 알아볼 수 없다
                _, issue = self.one(f"{split} 라고 적은 첫 줄\n뒤의 줄 {split}")
                for shown in (issue["body"], issue["title"]):
                    self.assertNotIn(secret, shown)
                    self.assertNotIn(fragment, shown)
                    self.assertEqual(nh.leaks(shown), [])
                    self.assertIn("***", shown)
                self.assertIn(ti.SECRET_NOTE, issue["body"])
                assert_safe_body(self, issue["body"], 10)

    # -- R1: 고정 문장의 대괄호가 사용자 글의 링크 정의로 링크가 되지 않게 ----------------------------------------------------------
    def test_the_fixed_candidate_sentence_keeps_its_brackets_inside_code_marks(self):
        self.assertIn("`[답하기]`", ti.CANDIDATE_NOTE)
        self.assertIn("`[답변]`", ti.CANDIDATE_NOTE)
        bare = re.sub(r"`[^`\n]*`", "", ti.CANDIDATE_NOTE)
        self.assertNotIn("[", bare)
        self.assertNotIn("]", bare)

    def test_user_text_cannot_turn_a_fixed_sentence_into_a_link(self):
        """글에 `[답하기]: 주소` 같은 줄이 있으면(CommonMark 의 링크 정의는 문서 어디서나 쓰인다) 고정 문장의 맨 대괄호가 그 주소의 링크가 된다."""
        hostile = "r103 승인 1\n\n[답하기]: https://example.invalid/x\n[답변]: https://example.invalid/y\n[G-S9]: https://example.invalid/z"
        for text in (hostile, "R-103\n" + hostile, "r103\n" + hostile, "그냥 글\n" + hostile):
            with self.subTest(text=text[:12]):
                _, issue = self.one(text)
                body = issue["body"]
                self.assertIn("> [답하기]: https://example.invalid/x", body)          # 사용자의 정의는 인용 안에 그대로 있고
                fixed = outside_quote_and_code(body)
                self.assertNotIn("[", fixed)                                           # 인용 밖의 고정 문장에는 대괄호가 없다(코드 표시 안은 링크가 되지 않는다)
                self.assertNotIn("]", fixed)
        _, issue = self.one("r103 승인 1")
        self.assertIn("(알림의 `[답하기]`)", issue["body"])

    # -- R2: 보낸 사람이 봇이면 운영자가 아니다 ----------------------------------------------------------------------------------
    def test_a_sender_marked_as_a_bot_is_not_the_operator_and_a_missing_flag_is_fine(self):
        bot = th.message_update(5, "x")
        bot["message"]["from"]["is_bot"] = True
        self.assertEqual(ti.read_update(bot, th.CHAT_INT), ti.Incoming(5, "skip", "", None))
        run = self.run_with(bot)
        self.assertEqual((run.issues(), run.tg.sent, run.gh.requests, run.tg.queue), ([], [], [], []))
        for flag in ("absent", False):
            update = th.message_update(5, "x")
            if flag == "absent":
                del update["message"]["from"]["is_bot"]
            else:
                update["message"]["from"]["is_bot"] = False
            self.assertEqual(ti.read_update(update, th.CHAT_INT).kind, "text", flag)

    # -- R3: 한 번에 받는 글은 5통 — 부풀린 낯선 글이 몰려도 응답 상한에 걸리지 않는다 ----------------------------------------------
    def test_bloated_stranger_updates_do_not_block_the_operators_text(self):
        def bloated(update_id):
            update = th.message_update(update_id, "스팸", chat_id=th.OTHER_ID)
            update["message"]["entities"] = [{"type": "text_link", "offset": 0, "length": 1, "url": "https://example.invalid/" + "a" * 2000}] * 100
            return update

        junk = [bloated(number) for number in range(1, 21)]
        self.assertGreater(len(json.dumps({"ok": True, "result": junk})), ti.MAX_RESPONSE_BYTES)       # 20통을 한꺼번에 받으면 읽기 상한을 넘는 크기다
        self.assertLess(len(json.dumps({"ok": True, "result": junk[:ti.UPDATES_LIMIT]})), ti.MAX_RESPONSE_BYTES)
        run = self.run_with(*junk, th.message_update(21, "진짜 글"))
        self.assertEqual([item["title"] for item in run.issues()], ["[텔레그램] 진짜 글"])
        self.assertEqual(run.code, 0)
        self.assertNotIn("::warning::", run.text)
        self.assertNotIn("응답을 읽을 수 없습니다", run.text)
        self.assertEqual((len(run.tg.sent), run.tg.queue), (1, []))          # 접수 확인 한 통뿐(낯선 이에게는 답이 없다)
        self.assertTrue(all(payload.get("limit", 100) <= ti.UPDATES_LIMIT for payload in run.tg.polls()))
        self.assertGreaterEqual(len(run.tg.polls()), 5)

    # -- R4: 전달된 글 ------------------------------------------------------------------------------------------------------------
    def test_forwarded_text_is_marked_as_not_written_by_the_operator_and_gets_no_candidate(self):
        origins = {
            "forward_origin": {"type": "user", "date": th.T0, "sender_user": {"id": th.OTHER_ID, "is_bot": False, "first_name": "남"}},
            "forward_from": {"id": th.OTHER_ID, "is_bot": False, "first_name": "남"},
            "forward_from_chat": {"id": -100123, "type": "channel", "title": "채널"},
            "forward_from_message_id": 7,
            "forward_signature": "서명",
            "forward_sender_name": "숨긴 사람",
            "forward_date": th.T0,
            "is_automatic_forward": True,
            "via_bot": {"id": 777, "is_bot": True, "first_name": "봇"},
        }
        self.assertEqual(set(origins), set(ti.FORWARD_KEYS))
        for key, value in origins.items():
            with self.subTest(key):
                _, issue = self.one("r103 승인 1", **{key: value})
                body = issue["body"]
                self.assertIn(ti.FORWARDED_NOTE, body)
                self.assertIn("운영자가 쓴 글이 아닙니다", body)
                self.assertNotIn("답변 후보", body)
                self.assertNotIn(ti.CANDIDATE_NOTE, body)
                self.assertLess(body.index(ti.ISSUE_NOTICE), body.index(ti.FORWARDED_NOTE))
                self.assertLess(body.index(ti.FORWARDED_NOTE), body.index("> r103"))
                self.assertEqual(quote_of(body), "r103 승인 1")
                assert_safe_body(self, body, 10)

    def test_a_plain_text_and_a_reply_are_not_marked_as_forwarded(self):
        _, issue = self.one("r103 승인 1")
        self.assertNotIn("운영자가 쓴 글이 아닙니다", issue["body"])
        self.assertIn("답변 후보", issue["body"])
        for extra in ({"reply_to_message": {"message_id": 1, "text": "남의 글"}}, {"entities": [{"type": "bold", "offset": 0, "length": 4}]}):
            with self.subTest(extra=sorted(extra)):
                _, issue = self.one("r103 승인 1", **extra)
                self.assertNotIn("운영자가 쓴 글이 아닙니다", issue["body"])
                self.assertIn("답변 후보", issue["body"])
        self.assertEqual(ti.read_update(th.message_update(3, "글"), th.CHAT_INT).forwarded, False)
        self.assertEqual(ti.read_update(th.message_update(3, "글", forward_origin={"type": "user"}), th.CHAT_INT).forwarded, True)

    # -- R5: 구현자 시험이 못 잡은 세 곳 --------------------------------------------------------------------------------------------
    def test_a_5xx_answer_for_an_issue_that_was_really_created_is_recovered_in_the_same_run(self):
        for status in (500, 502, 503, 504):
            with self.subTest(status=status):
                tg = th.FakeTelegram([th.message_update(10, "하나")])
                gh = th.FakeIssues(failures=[("POST", "/issues", th.oh.http_error(status, "bad gateway"), True)])      # 서버는 만들었고 응답만 5xx
                run = th.run_inbox(tg, gh)
                self.assertEqual(len(gh.new_issues()), 1)
                self.assertEqual(len([item for item in gh.requests if item["method"] == "POST" and item["path"] == "/issues"]), 1)
                self.assertEqual(run.code, 0)
                self.assertNotIn("::warning::", run.text)
                self.assertIn("#101", tg.texts()[0])
                self.assertEqual(tg.queue, [])

    def test_entity_references_of_any_length_never_revive_a_mention_or_a_tag(self):
        names = ["commat", "num", "lbrack", "rbrack", "Hat", "excl", "quest", "a" * 31, "b" * 32]
        text = " ".join(f"&{name};" for name in names) + " &#x000000040;y &#00000000064; 5&6 A & B &toolong" + "c" * 40 + ";"
        _, issue = self.one(text)
        quote = quote_of(issue["body"])
        expected = " ".join(f"&amp;{name};" for name in names) + " &amp;#x000000040;y &amp;#00000000064; 5&6 A & B &toolong" + "c" * 40 + ";"
        self.assertEqual(quote, expected)
        self.assertEqual(re.findall(r"&(?!amp;)#?[A-Za-z0-9]{1,32};", quote), [])

    def test_github_429_is_a_transient_warning_not_a_setup_failure(self):
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                tg = th.FakeTelegram([th.message_update(10, "하나")])
                gh = th.FakeIssues(failures=[(method, "/issues", th.oh.http_error(429, "rate limited")) for _ in range(3)])
                run = th.run_inbox(tg, gh)
                self.assertEqual(run.code, 0)
                self.assertIn("::warning::", run.text)
                self.assertNotIn("::error::", run.text)
                self.assertIn("429", run.text)
                self.assertEqual((gh.new_issues(), tg.sent), ([], []))
                self.assertEqual([item["update_id"] for item in tg.queue], [10])

    # -- R7: 안내 문구 ------------------------------------------------------------------------------------------------------------
    def test_the_409_webhook_text_states_only_facts_and_does_not_send_the_operator_to_botfather(self):
        text, code = ti.POLL_FAILURES["webhook"]
        self.assertEqual(code, 1)
        self.assertNotIn("BotFather", text)
        for needle in ("웹훅이 설정돼 있어 getUpdates 로 읽을 수 없습니다(409)", "`deleteWebhook`", "만들지도 지우지도 않습니다", "AI 에게 알려"):
            self.assertIn(needle, text)
        run = th.run_inbox(th.FakeTelegram([th.message_update(10, "하나")], webhook=True))
        self.assertEqual(run.code, 1)
        self.assertIn("deleteWebhook", run.text)
        self.assertNotIn("BotFather", run.text)
        self.assertEqual(run.tg.methods(), ["getUpdates"])                 # 이 코드는 deleteWebhook 을 부르지 않는다(말로만 알린다)

    def test_the_chat_id_text_does_not_call_negative_ids_non_numeric(self):
        line = ti.BAD_CHAT_LINE
        self.assertIn("양의 정수가 아닙니다", line)
        self.assertNotIn("숫자가 아닙니다", line)
        for needle in ("그룹·채널의 음수 ID", "`@이름`", "개인 대화 읽기에 쓸 수 없습니다"):
            self.assertIn(needle, line)
        for chat in ("-100123", "@운영자", "0", "abc", "1.5"):
            with self.subTest(chat=chat):
                run = th.run_inbox(th.FakeTelegram([th.message_update(10, "하나")]), env=th.make_env(TELEGRAM_CHAT_ID=chat))
                self.assertEqual(run.code, 1)
                self.assertIn(line, run.lines)
                self.assertEqual(run.tg.calls, [])


if __name__ == "__main__":
    unittest.main()
