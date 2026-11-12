"""병합완료 확인(`kind: merged`, 운영자 요청 2026-11-12)의 시험 — 병합 부탁을 운영자가 병합한 뒤 '제대로 됐는지'만 짧게 알리는 새 요청 종류.

핵심: ① 새 종류는 앞머리 칸 일곱 개(id·kind·title·summary·created·no·result)뿐이고 `no` 는 확인하는 병합 부탁의 M 번호, `result` 는 정상·이상, `title` 은 번호·결과로 정해진 글이다
② 폰 글은 정상이면 제목 한 줄, 이상이면 제목 + 사유 한 줄(단추: 정상 없음·이상 요청 열기) — 긴급도·번호 줄·예상 완료·본문이 없다 ③ 같은 M 번호의 병합 부탁이 요청함에 있어야 하고(짝) 병합완료 확인은 하나뿐이다(검증기 REQ-1)
④ 진행 현황 번호(P)·확인 요청 번호·다음 M 번호 계산에 영향이 없다 ⑤ **다른 종류(info·merge·decision·confirm·run)의 폰 글·단추·요청 파일 판정은 이 변경 전 코드(main 299fda3)와 바이트까지 같다**(골든 비교 —
tests/merged_golden_tools.py·merged_golden_data.py). 네트워크·실제 텔레그램·실제 GitHub 는 없다(가짜 git·가짜 HTTP).
"""
import re
import unittest

import notice_helpers as nth
import notify_helpers as nh
from merged_helpers import BLOB, SUMMARY_BAD
from pipeline import notify
from pipeline import operator_loop as ol


class RegistryTest(unittest.TestCase):
    def test_the_new_kind_is_registered_with_its_korean_name_after_the_old_five(self):
        self.assertEqual(list(notify.REQUEST_KIND_LABELS), ["merge", "run", "confirm", "decision", "info", "merged"])
        self.assertEqual(notify.REQUEST_KIND_LABELS["merged"], "병합완료 확인")
        self.assertEqual(notify.MERGED_KIND, "merged")
        self.assertEqual(ol.MERGED_KIND, "merged")
        self.assertNotIn("merged", notify.REQUEST_ANSWER_KINDS)              # 답이 필요 없는 종류다

    def test_its_number_is_the_m_number_of_the_merge_request_and_no_other_kind_uses_m_but_merge(self):
        self.assertEqual(notify.NOTICE_KIND_TYPES, {"info": "progress", "merge": "merge", "decision": "ask", "confirm": "ask", "run": "ask", "merged": "merge"})
        for kind in ("info", "decision", "confirm", "run"):
            self.assertNotEqual(notify.NOTICE_KIND_TYPES[kind], notify.NOTICE_KIND_TYPES["merged"], kind)

    def test_the_front_matter_keys_are_exactly_seven_and_result_is_the_only_new_key(self):
        self.assertEqual(ol.MERGED_KEYS, ("result",))
        self.assertEqual(ol.MERGED_ALLOWED, ("id", "kind", "title", "summary", "no", "result", "created"))
        self.assertEqual(ol.REQUEST_KEYS[-1], "result")
        self.assertEqual(len(ol.REQUEST_KEYS), len(set(ol.REQUEST_KEYS)))
        for key in ol.MERGED_ALLOWED:
            self.assertIn(key, ol.REQUEST_KEYS, key)

    def test_the_tables_of_the_three_number_types_are_not_touched(self):
        self.assertEqual(set(ol.NOTICE_ALLOWED), {"progress", "merge", "ask"})
        self.assertEqual(set(ol.NOTICE_REQUIRED), {"progress", "merge", "ask"})
        self.assertEqual(ol.NOTICE_ALLOWED["merge"], ("repo", "target", "pr_title", "verify", "state"))
        self.assertEqual(ol.NOTICE_REQUIRED["merge"], ("repo", "target", "pr_title", "verify"))
        self.assertEqual(notify.NOTICE_LABELS, {"progress": "진행 현황", "merge": "병합 요청", "ask": "확인 요청"})

    def test_the_results_and_the_summary_limits(self):
        self.assertEqual((notify.MERGED_OK, notify.MERGED_BAD, notify.MERGED_RESULTS), ("정상", "이상", ("정상", "이상")))
        self.assertEqual(notify.MERGED_SUMMARY_LIMITS, {"정상": 60, "이상": 100})

    def test_every_new_problem_code_has_a_fixed_one_line_sentence_without_outside_values(self):
        for code in ("bad_result", "missing_result", "merged_title_mismatch", "long_merged_summary", "merged_unpaired", "merged_duplicate", "merged_summary_label"):
            self.assertIn(code, ol.PROBLEMS, code)
            text = ol.problem_text(code)
            self.assertTrue(text and "\n" not in text and "알 수 없는 문제" not in text, code)
        self.assertIn("60자", ol.problem_text("long_merged_summary"))
        self.assertIn("100자", ol.problem_text("long_merged_summary"))
        duplicate = ol.problem_text("merged_duplicate")                                  # D3: 다시 보내는 길은 파일 고치기가 아니라 다른 알림(info) — 알림은 새로 더해진 파일만 고른다
        self.assertIn("`info`", duplicate)
        self.assertIn("새로 더해진 파일만", duplicate)
        self.assertNotIn("그 파일을 고칩니다", duplicate)
        self.assertIn("`병합완료 확인`", ol.problem_text("merged_summary_label"))

    def test_the_unchanged_problem_sentences_are_byte_for_byte_the_old_ones(self):
        """다른 종류의 로그·검증기 문구가 달라지지 않게: 이미 있던 문제 문구는 한 글자도 바꾸지 않았다(새 종류는 새 코드만 더했다)."""
        self.assertEqual(ol.problem_text("no_kind_mismatch"), "no 의 유형이 kind 와 맞지 않습니다(info 는 `P`, merge 는 `M`, decision·confirm·run 은 숫자만)")
        self.assertEqual(ol.problem_text("foreign_key"), "이 알림 유형에 쓰지 않는 칸이 있습니다(진행 현황: at·now·changed·next·eta·waiting·check / 병합 요청: repo·target·pr_title·verify·state / 확인 요청: options·default·approve)")
        self.assertEqual(ol.problem_text("unknown_key"), "모르는 키가 있습니다(쓸 수 있는 키: " + ", ".join(ol.REQUEST_KEYS) + ")")


class TitleAndMessageTest(unittest.TestCase):
    def test_the_title_is_the_number_the_label_and_the_result(self):
        self.assertEqual(notify.merged_title("M050", "정상"), "[M050] 병합완료 확인 - 정상")
        self.assertEqual(notify.merged_title("M050", "이상"), "[M050] 병합완료 확인 - 이상")
        self.assertEqual(notify.merged_title("M1000", "정상"), "[M1000] 병합완료 확인 - 정상")
        self.assertEqual(notify.merged_title("M001", "이상"), "[M001] 병합완료 확인 - 이상")

    def test_the_title_refuses_every_number_that_is_not_a_merge_request_number(self):
        for no in ("M50", "M0500", "M000", "M10000", "m050", "P012", "012", "003", "R-050", "M 050", "M050 ", " M050", "M050\n", "", None, 50, "M-050", "MM050"):
            with self.assertRaises(ValueError, msg=repr(no)) as raised:
                notify.merged_title(no, "정상")
            self.assertEqual(str(raised.exception), "no", repr(no))

    def test_the_title_refuses_every_result_but_the_two(self):
        for result in (None, "", "정상 ", " 이상", "OK", "ok", "정상.", "이상함", "정 상", "성공", "실패", 1, True):
            with self.assertRaises(ValueError, msg=repr(result)) as raised:
                notify.merged_title("M050", result)
            self.assertEqual(str(raised.exception), "result", repr(result))

    def test_a_normal_result_is_exactly_one_line_and_nothing_else(self):
        text = notify.format_merged("M050", {"result": "정상", "summary": "정상"})
        self.assertEqual(text, "[M050] 병합완료 확인 - 정상")
        self.assertEqual(text, notify.merged_title("M050", "정상"))
        for needle in ("\n", "<", ">", "급함", "예상", "ETA", "📊", "🔀", "🔔", "🚨", "관련 PR", "작업", "기준", "병합 요청", "진행 현황"):
            self.assertNotIn(needle, text, needle)
        self.assertNotRegex(text, r"\bP[0-9]{3}\b")

    def test_a_normal_result_ignores_whatever_else_the_fields_carry(self):
        base = notify.format_merged("M050", {"result": "정상"})
        for fields in ({"result": "정상", "summary": "긴 요약 " * 20}, {"result": "정상", "urgency": "급함", "now": "x", "at": "2026-11-12 08:00"}, {"result": "정상", "pr_title": "x", "repo": "a/b"}):
            self.assertEqual(notify.format_merged("M050", fields), base)

    def test_an_abnormal_result_is_the_title_and_one_reason_line(self):
        text = notify.format_merged("M050", {"result": "이상", "summary": SUMMARY_BAD})
        self.assertEqual(text, "[M050] 병합완료 확인 - 이상\n" + SUMMARY_BAD)
        self.assertEqual(text.splitlines()[0], notify.merged_title("M050", "이상"))
        self.assertEqual(len(text.splitlines()), 2)
        for needle in ("급함", "예상", "📊", "🔀", "🔔", "🚨", "관련 PR", "<b>", "<code>"):
            self.assertNotIn(needle, text, needle)

    def test_the_reason_is_cleaned_like_every_other_phone_line(self):
        def second(summary):
            return notify.format_merged("M050", {"result": "이상", "summary": summary}).split("\n", 1)[1]
        self.assertEqual(second("@owner 확인 R-264 와 <b>굵게</b> & 끝"), "＠owner 확인 r264 와 &lt;b&gt;굵게&lt;/b&gt; &amp; 끝")
        self.assertEqual(second("줄\n바꿈\r\n접기"), "줄 바꿈 접기")
        self.assertEqual(second("보이지" + chr(0x200B) + "않는" + chr(0x202E) + "글자"), "보이지않는글자")
        self.assertEqual(second("https://example.com/a 와 tg://resolve"), "https：//example.com/a 와 tg：//resolve")
        self.assertNotIn("AIza", second("키 " + "AIza" + "x" * 35))
        self.assertIn("***", second("키 " + "AIza" + "x" * 35))
        long = second("가" * 300)
        self.assertEqual(len(long), 100)
        self.assertTrue(long.endswith("…"))
        self.assertEqual(second("가" * 100), "가" * 100)

    def test_an_abnormal_result_needs_a_reason(self):
        for summary in (None, "", "   ", chr(0x200B), "\n"):
            with self.assertRaises(ValueError, msg=repr(summary)) as raised:
                notify.format_merged("M050", {"result": "이상", "summary": summary})
            self.assertEqual(str(raised.exception), "summary")
        with self.assertRaises(ValueError):
            notify.format_merged("M050", {"result": "이상"})

    def test_the_overflow_line_is_the_same_one_the_other_numbered_messages_use(self):
        tail = "\n\n… 외 2건 (저장소의 인수인계/요청함/ 폴더에서 확인하세요)"
        self.assertEqual(notify.format_merged("M050", {"result": "정상"}, more=2), "[M050] 병합완료 확인 - 정상" + tail)
        self.assertEqual(notify.format_merged("M050", {"result": "이상", "summary": "x"}, more=2), "[M050] 병합완료 확인 - 이상\nx" + tail)
        self.assertTrue(notify.format_notice("P012", nth.PROGRESS, more=2).endswith(tail))
        for more in (-1, True, "x", 1.5):
            if more:
                with self.assertRaises(ValueError, msg=repr(more)):
                    notify.format_merged("M050", {"result": "정상"}, more=more)

    def test_bad_inputs_raise_value_error_with_the_key_name(self):
        for args, key in ((("P012", {"result": "정상"}), "no"), (("M50", {"result": "정상"}), "no"), (("M050", {}), "result"), (("M050", None), "result"), (("M050", {"result": "OK"}), "result"),
                          (("M050", {"result": None}), "result")):
            with self.assertRaises(ValueError, msg=args) as raised:
                notify.format_merged(*args)
            self.assertEqual(str(raised.exception), key, args)

    def test_every_standard_m_number_makes_a_one_line_title(self):
        pattern = re.compile(r"\[M[0-9]{3,4}\] 병합완료 확인 - (?:정상|이상)")
        for number in list(range(1, 1000, 7)) + list(range(1000, 10000, 97)) + [999, 1000, 9999]:
            no = notify.notice_no_text("merge", number)
            for result in notify.MERGED_RESULTS:
                title = notify.merged_title(no, result)
                self.assertIsNotNone(pattern.fullmatch(title), title)
                self.assertEqual(notify.format_merged(no, {"result": "정상"}), notify.merged_title(no, "정상"))

    def test_the_old_formats_still_refuse_the_new_kind_in_their_own_paths(self):
        for no in ("M050", "P012", "003"):
            builder = {"M050": notify.format_progress, "P012": notify.format_merge_request, "003": notify.format_progress}[no]
            with self.assertRaises(ValueError):
                builder(no, {"result": "정상"})
        with self.assertRaises(ValueError):                                      # 일반 길(format_notice)은 병합완료 확인 글을 병합 요청 글로 잘못 만들지 않는다
            notify.format_notice("M050", {"result": "정상", "summary": "정상"})

    def test_the_unreadable_file_text_is_one_fixed_line_with_only_the_request_number(self):
        text = notify.format_merged_unreadable("R-266")
        self.assertEqual(text, f"{notify.WARN_MARK} 병합완료 확인 파일 모양이 틀려 내용을 싣지 않았습니다(요청 r266) — 요청 열기 단추로 확인하세요")
        self.assertEqual(len(text.splitlines()), 1)
        for word in ("정상", "이상", "[M", "📊", "🔀", "🔔", "🚨", "관련 PR"):
            self.assertNotIn(word, text, word)                                   # 정상·이상 글자와 번호 줄이 없다 — 이 글이 '결과' 로 읽힐 수 없다
        for number in ("R-001", "R-100", "R-999"):
            self.assertIn(f"(요청 r{number[2:]})", notify.format_merged_unreadable(number), number)

    def test_the_unreadable_file_text_refuses_anything_but_a_request_number(self):
        for bad in ("R-1", "R-0266", "r266", "r-266", "M050", "", None, 266, "R-266\n", "R-266 ", "[R-266]", "R-266_x.md", "정상"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                notify.format_merged_unreadable(bad)

    def test_the_unreadable_file_text_adds_the_same_overflow_line_the_other_messages_use(self):
        base = notify.format_merged_unreadable("R-266")
        self.assertEqual(notify.format_merged_unreadable("R-266", more=0), base)
        for count in (1, 2, 7):
            self.assertEqual(notify.format_merged_unreadable("R-266", more=count), base + "\n\n" + f"… 외 {count}건 (저장소의 인수인계/요청함/ 폴더에서 확인하세요)")
        for bad in (-1, True, "2", 1.5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                notify.format_merged_unreadable("R-266", more=bad)


class NotifierTest(unittest.TestCase):
    def test_a_normal_result_is_sent_as_one_html_message_with_no_buttons(self):
        notifier, net, _clock = nh.make_notifier()
        result = notifier.notify_merged("M050", {"result": "정상", "summary": "정상"})
        self.assertEqual((result.ok, result.sent, result.reason), (True, True, "sent"))
        self.assertEqual(net.calls, 1)
        body = net.bodies()[0]
        self.assertEqual(body["text"], "[M050] 병합완료 확인 - 정상")
        self.assertEqual(body["parse_mode"], "HTML")
        self.assertNotIn("reply_markup", body)
        self.assertNotIn("disable_notification", body)
        self.assertEqual(nh.leaks(body["text"], chat=False), [])

    def test_buttons_are_sent_only_when_given_and_only_allowed_addresses(self):
        notifier, net, _clock = nh.make_notifier()
        url = BLOB + "ai/claude/x/" + "%EC%9A%94%EC%B2%AD%ED%95%A8/R-267_merged-m050.md"
        notifier.notify_merged("M050", {"result": "이상", "summary": SUMMARY_BAD}, buttons=[("요청 열기", url), ("나쁜 주소", "https://example.com/x")])
        row = net.bodies()[0]["reply_markup"]["inline_keyboard"][0]
        self.assertEqual([(item["text"], item["url"]) for item in row], [("요청 열기", url)])

    def test_the_unused_module_level_twin_is_gone_and_the_methods_are_the_only_way_in(self):
        """D5(독립 검증): 운영 코드가 쓰지 않던 모듈 수준 함수 `notify.notify_merged` 는 지웠다(operator_loop 는 `Notifier.notify_merged` 를 부른다 — 단추 전달은 위 시험이 본다). 새 고정 문구 길도 메서드만 둔다."""
        self.assertFalse(hasattr(notify, "notify_merged"))
        self.assertFalse(hasattr(notify, "notify_merged_unreadable"))
        self.assertTrue(callable(notify.Notifier.notify_merged) and callable(notify.Notifier.notify_merged_unreadable))

    def test_the_unreadable_file_message_is_one_fixed_html_line_and_passes_only_allowed_buttons(self):
        notifier, net, _clock = nh.make_notifier()
        url = BLOB + "ai/claude/x/" + "%EC%9A%94%EC%B2%AD%ED%95%A8/R-267_merged-m050.md"
        result = notifier.notify_merged_unreadable("R-267", buttons=[("요청 열기", url), ("나쁜 주소", "https://example.com/x")])
        self.assertEqual((result.ok, result.sent, result.reason), (True, True, "sent"))
        body = net.bodies()[0]
        self.assertEqual(body["text"], notify.format_merged_unreadable("R-267"))
        self.assertEqual(body["parse_mode"], "HTML")
        self.assertEqual([(item["text"], item["url"]) for item in body["reply_markup"]["inline_keyboard"][0]], [("요청 열기", url)])
        self.assertNotIn("disable_notification", body)
        self.assertEqual(nh.leaks(body["text"], chat=False), [])
        notifier, net, _clock = nh.make_notifier()
        self.assertTrue(notifier.notify_merged_unreadable("R-267", more=2).sent)
        self.assertEqual(net.bodies()[0]["text"], notify.format_merged_unreadable("R-267", more=2))
        self.assertNotIn("reply_markup", net.bodies()[0])

    def test_the_unreadable_file_message_sends_nothing_for_a_bad_number_and_never_raises(self):
        for args in (("r267",), ("M050",), ("",), (None,), ("R-267", None, -3)):
            notifier, net, _clock = nh.make_notifier()
            result = notifier.notify_merged_unreadable(*args)
            self.assertEqual((result.ok, result.sent, result.reason, net.calls), (False, False, notify.INTERNAL_ERROR, 0), args)
            self.assertEqual(result.detail, "ValueError")
        notifier, net, _clock = nh.make_notifier(environ={})
        result = notifier.notify_merged_unreadable("R-267")
        self.assertEqual((result.ok, result.sent, result.reason, net.calls), (True, False, notify.DISABLED, 0))

    def test_bad_input_sends_nothing_and_never_raises(self):
        for args in (("P012", {"result": "정상"}), ("M050", {"result": "OK"}), ("M050", {"result": "이상"}), ("M50", {"result": "정상"})):
            notifier, net, _clock = nh.make_notifier()
            result = notifier.notify_merged(*args)
            self.assertEqual((result.ok, result.sent, result.reason, net.calls), (False, False, notify.INTERNAL_ERROR, 0), args)
            self.assertEqual(result.detail, "ValueError")

    def test_without_secrets_nothing_is_sent(self):
        notifier, net, _clock = nh.make_notifier(environ={})
        result = notifier.notify_merged("M050", {"result": "정상"})
        self.assertEqual((result.ok, result.sent, result.reason, net.calls), (True, False, notify.DISABLED, 0))

    def test_it_counts_as_one_message_of_the_budget(self):
        notifier, net, _clock = nh.make_notifier()
        for _ in range(notify.MAX_MESSAGES):
            self.assertTrue(notifier.notify_merged("M050", {"result": "정상"}).sent)
        self.assertEqual(notifier.notify_merged("M050", {"result": "정상"}).reason, notify.LIMIT)
        self.assertEqual(net.calls, notify.MAX_MESSAGES)
