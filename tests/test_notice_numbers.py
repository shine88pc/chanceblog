"""알림 번호(P001·M001·001)와 표준 메시지 3종(진행 현황·병합 요청·확인 요청)·새 양식 접수 회신의 글 모양 시험(pipeline/notify.py, TG-STD 운영자 승인 2026-11-06 R-165).

번호 읽기는 손으로 쓴 판정(정규식을 쓰지 않는 기준 구현)과 짧은 글 전수로 맞춰 본다. 메시지는 유형별로 글자 그대로 표(정상·선택 칸 비움·긴 값·한글/영문/이모지·`& < > @ https://`·길이 한도)로 못박고,
병합 요청의 PR 제목은 **이스케이프만 다르고 글자 그대로**인지 무작위 문자열로 역변환 대조한다. 네트워크·실제 텔레그램은 없다(가짜 HTTP).
"""
import html
import itertools
import json
import random
import re
import unittest

import _bootstrap  # noqa: F401 - 저장소 루트를 import 경로에 올린다
import notice_helpers as nth
import notify_helpers as nh
from pipeline import notify

PROGRESS_HEAD = f"{notify.PROGRESS_MARK} <b>P012 · 진행 현황</b> · 11-06 12:07 기준"
UNICODE_DIGITS = ("０１２", "١٢٣", "①②③")        # 전각·아랍 인도·원문자 숫자


def oracle(text):
    """번호 유형의 기준 구현(정규식 없이 글자 단위로) — 진행 현황 P·병합 M·확인(숫자만)·번호 아님(빈 글자열). 숫자는 표준 ASCII 표기만이다: 세 자리 `001`~`999`(0 채움, `000` 없음),
    네 자리 `1000`~`9999`(앞에 0 이 더 붙은 `0012` 는 번호가 아니다 — 같은 번호가 두 글자로 적혀 '유형별 중복 금지'를 피하지 못하게)."""
    head, digits = (text[0], text[1:]) if text[:1] in ("P", "M") else ("", text)
    if not digits or any(char not in "0123456789" for char in digits):
        return ""
    value = int(digits)
    if not ((len(digits) == 3 and value >= 1) or (len(digits) == 4 and value >= 1000)):
        return ""
    return {"P": notify.NOTICE_PROGRESS, "M": notify.NOTICE_MERGE, "": notify.NOTICE_ASK}[head]


class NoticeNumberTest(unittest.TestCase):
    def test_the_three_shapes_and_their_types(self):
        for text, kind in (("P001", "progress"), ("P012", "progress"), ("P999", "progress"), ("P1000", "progress"), ("P9999", "progress"), ("M001", "merge"), ("M007", "merge"),
                           ("M1234", "merge"), ("001", "ask"), ("003", "ask"), ("999", "ask"), ("1000", "ask"), ("9999", "ask")):
            self.assertEqual(notify.notice_type(text), kind, text)
        self.assertEqual({notify.NOTICE_PROGRESS, notify.NOTICE_MERGE, notify.NOTICE_ASK}, {"progress", "merge", "ask"})

    def test_everything_else_is_not_a_notice_number(self):
        bad = ["", "P", "M", "P1", "P12", "M12", "12", "1", "0", "00", "P000", "M000", "000", "0000", "P00000", "10000", "P10000", "0012", "0003", "P0012", "M0007", "0999", "p001", "m001", "PM001", "P-001", "P 001",
               " 001", "001 ", "001\n", "\n001", "P001\n", "001.", "#001", "R-001", "r001", "P00a", "00a", "A001", "001-", "P001x", "０１２", "P０１２", "①②③", "P①②③", "٠٠١",
               "001\u200b", "\u200b001", "0\u200b01", "P\u200b001", "\ufeff001", "0 01", "001001", None, 1, 12.0, b"001", ("001",)]
        for text in bad:
            self.assertEqual(notify.notice_type(text), "", repr(text))
            self.assertEqual(notify.notice_number(text), 0, repr(text))
        for digits in UNICODE_DIGITS:
            for text in (digits, "P" + digits, "M" + digits):
                self.assertEqual(notify.notice_type(text), "", repr(text))

    def test_every_short_text_over_a_hostile_alphabet_matches_the_hand_written_oracle(self):
        """길이 5 이하 글 전수(글자 12종: 접두어 P·M·p, 숫자, 전각 숫자, 원문자, 공백, 줄 바꿈, 폭 없는 공백, 하이픈) — 약 25만 개를 기준 구현과 하나씩 맞춰 본다."""
        alphabet = ["P", "M", "p", "0", "1", "9", "１", "①", " ", "\n", "\u200b", "-"]
        checked = 0
        for length in range(0, 6):
            for chars in itertools.product(alphabet, repeat=length):
                text = "".join(chars)
                self.assertEqual(notify.notice_type(text), oracle(text), repr(text))
                checked += 1
        self.assertGreater(checked, 250000)

    def test_every_number_from_1_to_9999_has_exactly_one_spelling_in_each_of_the_three_types(self):
        """수정 1차(V2 M1): 1..9999 × 3유형 전부에서 표준 표기(`notice_no_text`)만 번호이고, 같은 값의 다른 표기(앞 0 을 더 붙인 네 자리·다섯 자리)는 번호가 아니다 —
        `P012` 와 `P0012` 가 서로 다른 번호가 되어 유형별 중복 금지를 우회하는 일이 없다."""
        for kind, prefix in (("progress", "P"), ("merge", "M"), ("ask", "")):
            for number in range(1, 10000):
                standard = notify.notice_no_text(kind, number)
                self.assertEqual((notify.notice_type(standard), notify.notice_number(standard)), (kind, number), standard)
                spellings = {prefix + str(number).zfill(width) for width in range(1, 8)} - {standard}
                for other in spellings:
                    self.assertEqual((notify.notice_type(other), notify.notice_number(other)), ("", 0), other)

    def test_a_leading_zero_four_digit_number_is_not_a_number(self):
        for prefix in ("", "P", "M"):
            for digits in ("0001", "0003", "0012", "0099", "0100", "0999", "0000", "00012", "000012", "00000"):
                text = prefix + digits
                self.assertEqual(notify.notice_type(text), "", text)
                self.assertEqual(notify.notice_number(text), 0, text)
            for digits in ("001", "012", "999", "1000", "1234", "9999"):
                self.assertNotEqual(notify.notice_type(prefix + digits), "", prefix + digits)
        self.assertEqual(notify.NOTICE_NO_RE.fullmatch("P0012"), None)
        self.assertEqual(notify.NOTICE_NO_RE.fullmatch("0003"), None)

    def test_the_number_value_and_the_text_made_from_it_round_trip(self):
        for kind, prefix in (("progress", "P"), ("merge", "M"), ("ask", "")):
            for number in (1, 2, 9, 10, 12, 99, 100, 998, 999, 1000, 1001, 9998, 9999):
                text = notify.notice_no_text(kind, number)
                self.assertEqual(text, prefix + (f"{number:03d}"), (kind, number))
                self.assertEqual((notify.notice_type(text), notify.notice_number(text)), (kind, number))
        self.assertEqual([notify.notice_no_text("progress", n) for n in (1, 999, 1000)], ["P001", "P999", "P1000"])
        self.assertEqual([notify.notice_no_text("ask", n) for n in (1, 999, 1000)], ["001", "999", "1000"])
        for kind, number in (("progress", 0), ("progress", 10000), ("merge", -1), ("ask", 0), ("ask", True), ("ask", 1.5), ("ask", "1"), ("note", 1), ("", 1), (None, 1)):
            with self.assertRaises(ValueError, msg=(kind, number)):
                notify.notice_no_text(kind, number)

    def test_each_kind_maps_to_exactly_one_number_type(self):
        self.assertEqual(set(notify.NOTICE_KIND_TYPES), set(notify.REQUEST_KIND_LABELS))
        self.assertEqual(notify.NOTICE_KIND_TYPES, {"info": "progress", "merge": "merge", "decision": "ask", "confirm": "ask", "run": "ask", "merged": "merge"})       # merged(병합완료 확인)는 확인하는 병합 요청의 M 번호를 그대로 쓴다

    def test_the_labels_are_korean_and_only_the_prefix_and_the_digits_are_english(self):
        self.assertEqual(notify.NOTICE_LABELS, {"progress": "진행 현황", "merge": "병합 요청", "ask": "확인 요청"})
        for text in (notify.format_notice("P012", nth.PROGRESS), notify.format_notice("M007", nth.MERGE), notify.format_notice("003", nth.ASK | {"summary": "무엇을 할까요"})):
            head = re.sub(r"</?b>", "", text.splitlines()[0])
            self.assertRegex(head, r"^\S+ (?:P[0-9]{3}|M[0-9]{3}|[0-9]{3}) · [가-힣 ]+")


class ProgressFormatTest(unittest.TestCase):
    FIELDS = dict(nth.PROGRESS, waiting="없음 (확인 요청 003 은 답이 없으면 기본 보기 ①로 진행)", check="이상 없음")

    def test_the_message_is_the_five_items_under_a_head_word_for_word(self):
        text = notify.format_notice("P012", self.FIELDS)
        self.assertEqual(text, "\n".join([
            f"{PROGRESS_HEAD} · 점검 이상 없음",
            "현재 진행: 5채널 주제 엔진 P3 독립 검증 중",
            "직전 보고 이후: P3 구현·시험 통과",
            "다음 계획: 검증 통과 시 병합 요청",
            "예상 완료: 11-06 15:00경(추정)",
            "확인·승인 대기: 없음 (확인 요청 003 은 답이 없으면 기본 보기 ①로 진행)"]))

    def test_without_the_check_line_the_head_has_no_check_part_and_an_empty_check_is_the_same(self):
        fields = dict(nth.PROGRESS)
        expected = PROGRESS_HEAD + "\n" + "\n".join(notify.format_notice("P012", fields).splitlines()[1:])
        self.assertEqual(notify.format_notice("P012", fields), expected)
        self.assertNotIn("점검", notify.format_notice("P012", fields))
        self.assertEqual(notify.format_notice("P012", dict(fields, check="")), expected)
        self.assertEqual(notify.format_notice("P012", dict(fields, check="  ")), expected)

    def test_urgency_work_pr_and_more_decorate_without_changing_the_five_items(self):
        base = notify.format_notice("P012", nth.PROGRESS).splitlines()
        text = notify.format_notice("P012", nth.PROGRESS, urgency="급함", work="R-160", pr=7, more=2).splitlines()
        self.assertEqual(text[0], f"{PROGRESS_HEAD} · 작업 r160 {notify.SIREN_MARK} 급함")
        self.assertEqual(text[1], "관련 PR: #7")
        self.assertEqual(text[2:7], base[1:])
        self.assertEqual(text[7:], ["", "… 외 2건 (저장소의 인수인계/요청함/ 폴더에서 확인하세요)"])
        self.assertEqual(notify.format_notice("P012", nth.PROGRESS, urgency="보통"), "\n".join(base))
        for bad_pr in (0, -1, True, "7", 1.5):
            with self.assertRaises(ValueError, msg=bad_pr):
                notify.format_notice("P012", nth.PROGRESS, pr=bad_pr)
        for bad_more in (-1, True, "2", 1.5):
            with self.assertRaises(ValueError, msg=bad_more):
                notify.format_notice("P012", nth.PROGRESS, more=bad_more)

    def test_every_item_is_required_and_a_bad_time_is_refused(self):
        for key, _label, _limit in notify.PROGRESS_ITEMS:
            for value in (None, "", "   ", chr(0x200B)):
                with self.assertRaises(ValueError, msg=(key, value)) as caught:
                    notify.format_notice("P012", {**nth.PROGRESS, key: value})
                self.assertEqual(str(caught.exception), key)
        for at in (None, "", "2026-11-06", "2026-11-06T12:07", "2026-11-06 12:07:00", "2026-13-06 12:07", "2026-11-31 12:07", "2026-11-06 24:00", "2026-11-06 12:60", "26-11-06 12:07",
                   "2026-11-06  12:07", " 2026-11-06 12:07", "2026-11-06 12:07 ", "２０２６-11-06 12:07", "2026-11-06 12:07\n", 20261106):
            with self.assertRaises(ValueError, msg=repr(at)) as caught:
                notify.format_notice("P012", {**nth.PROGRESS, "at": at})
            self.assertEqual(str(caught.exception), "at")
        self.assertIn("02-29", notify.format_notice("P012", {**nth.PROGRESS, "at": "2028-02-29 00:00"}))
        with self.assertRaises(ValueError):
            notify.format_notice("P012", {**nth.PROGRESS, "at": "2026-02-29 00:00"})

    def test_values_are_one_line_sanitised_and_cut_at_their_limits(self):
        hostile = {**nth.PROGRESS, "now": "첫 줄\n::set-output name=x::1 @owner https://evil.example/x R-090 <b>굵게</b> & 끝", "changed": "가" * 500, "eta": "나" * 500,
                   "waiting": "다 " * 300, "check": "라" * 300}
        text = notify.format_notice("P012", hostile)
        lines = text.splitlines()
        self.assertEqual(len(lines), 6)
        for needle in ("::", "https://", "@", "<b>굵게", "R-090"):
            self.assertNotIn(needle, "\n".join(lines[1:]), needle)
        self.assertIn("r090", lines[1])
        self.assertIn("＠owner", lines[1])
        self.assertIn("https：//evil.example/x", lines[1])
        self.assertIn("&lt;b&gt;굵게&lt;/b&gt; &amp; 끝", lines[1])
        self.assertTrue(lines[2].endswith("…") and len(lines[2]) <= len("직전 보고 이후: ") + 200)
        self.assertTrue(lines[4].endswith("…") and len(lines[4]) <= len("예상 완료: ") + 100)
        self.assertTrue(lines[0].count("…") == 1 and "점검 " in lines[0])

    def test_korean_english_and_emoji_values_are_kept(self):
        fields = {**nth.PROGRESS, "now": "Gemini 키 순환 점검 완료 ✅ 🚀 (v1.2.3)", "next": "Build → Test → Release", "waiting": "없음 / none / ない"}
        text = notify.format_notice("P012", fields)
        for needle in ("Gemini 키 순환 점검 완료 ✅ 🚀 (v1.2.3)", "Build → Test → Release", "없음 / none / ない"):
            self.assertIn(needle, text)

    def test_a_progress_number_is_required_for_the_progress_form_and_other_numbers_are_refused(self):
        for no in ("M012", "012", "", "P12", "P000", None):
            with self.assertRaises(ValueError, msg=no):
                notify.format_progress(no, nth.PROGRESS)


class MergeFormatTest(unittest.TestCase):
    def test_the_message_is_the_five_items_word_for_word(self):
        text = notify.format_notice("M007", nth.MERGE)
        self.assertEqual(text, "\n".join([
            f"{notify.MERGE_MARK} <b>M007 · 병합 요청</b>",
            "병합 대상: 5채널 전략 P2b 후보 조립 부품",
            "저장소: shine88pc/chanceblog-desktop",
            "PR 제목: <code>[R-160] 5채널 전략 'P2b' — 후보 조립 순수 부품 [대상: 데스크톱]</code>",
            "검증 결과: 독립 검증 통과 · 검사 4칸 초록 · 변경 45개 파일",
            "상태: 승인 대기"]))

    def test_the_state_defaults_to_waiting_for_approval_and_can_be_changed(self):
        self.assertTrue(notify.format_notice("M007", nth.MERGE).endswith("상태: 승인 대기"))
        self.assertTrue(notify.format_notice("M007", {**nth.MERGE, "state": ""}).endswith("상태: 승인 대기"))
        self.assertTrue(notify.format_notice("M007", {**nth.MERGE, "state": "검사 대기"}).endswith("상태: 검사 대기"))

    def test_decorations_urgency_work_pr_and_more(self):
        lines = notify.format_notice("M007", nth.MERGE, urgency="급함", work="R-160", pr=57, more=1).splitlines()
        self.assertEqual(lines[0], f"{notify.MERGE_MARK} <b>M007 · 병합 요청</b> · 작업 r160 {notify.SIREN_MARK} 급함")
        self.assertEqual(lines[1], "관련 PR: #57")
        self.assertEqual(lines[-1], "… 외 1건 (저장소의 인수인계/요청함/ 폴더에서 확인하세요)")

    def test_every_item_is_required(self):
        for key in ("repo", "target", "pr_title", "verify"):
            for value in (None, "", "   "):
                with self.assertRaises(ValueError, msg=(key, value)):
                    notify.format_notice("M007", {**nth.MERGE, key: value})

    def test_the_pr_title_is_shown_exactly_inside_code_with_only_html_escaping(self):
        title = "[R-160] 't & \"q\"' <b>굵게</b> @owner https://x.example/p?a=1&b=2 R-090 `백틱` #12 $(x) ::warning:: ＠ ＜"
        text = notify.format_notice("M007", {**nth.MERGE, "pr_title": title})
        line = next(item for item in text.splitlines() if item.startswith("PR 제목: "))
        inner = re.fullmatch(r"PR 제목: <code>(.*)</code>", line).group(1)
        self.assertEqual(inner, html.escape(title, quote=False))
        self.assertEqual(html.unescape(inner), title)
        for needle in ("@owner", "https://x.example/p?a=1&amp;b=2", "R-090", "::warning::", "[R-160]"):
            self.assertIn(needle, inner)
        other = "\n".join(item for item in text.splitlines() if not item.startswith("PR 제목: "))
        self.assertNotIn("<code>", other)

    def test_the_other_lines_are_sanitised_but_the_pr_title_is_not(self):
        fields = {**nth.MERGE, "target": "R-090 @owner https://x.example/a <i>x</i>", "verify": "::x:: R-090 & ok", "pr_title": "[R-160] @owner https://x.example/a R-090"}
        lines = notify.format_notice("M007", fields).splitlines()
        self.assertEqual(lines[1], "병합 대상: r090 ＠owner https：//x.example/a &lt;i&gt;x&lt;/i&gt;")
        self.assertEqual(lines[4], "검증 결과: : :x: : r090 &amp; ok")                      # `::` 는 `: :` 로 풀어 쓴다(워크플로 명령 표기 무력화)
        self.assertEqual(lines[3], "PR 제목: <code>[R-160] @owner https://x.example/a R-090</code>")

    def test_random_titles_survive_unchanged_through_the_escape_and_back(self):
        rng = random.Random(20261106)
        alphabet = list("abcXYZ019 []()'\"<>&@#:/._-—·+*=%$!?,;~^|\\") + list("한글제목병합대상검증") + ["😀", "✅", "→", "é", "ß", "R-160", "https://", "[R-1] ", "@", "://", " — ", "&amp;", "&lt;", "<code>"]
        checked = 0
        while checked < 600:
            title = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 60))).strip()
            if not title or notify.pr_title_problem(title):
                continue
            text = notify.format_notice("M007", {**nth.MERGE, "pr_title": title})
            line = next(item for item in text.splitlines() if item.startswith("PR 제목: "))
            inner = re.fullmatch(r"PR 제목: <code>(.*)</code>", line, re.S).group(1)
            self.assertEqual(html.unescape(inner), title, repr(title))
            self.assertEqual(inner, html.escape(title, quote=False), repr(title))
            checked += 1

    def test_a_title_up_to_the_limit_is_shown_whole_and_a_longer_one_is_not_cut_at_run_time(self):
        for length in (1, 50, notify.PR_TITLE_LIMIT, notify.PR_TITLE_LIMIT + 1, 700):
            title = ("[R-160] " + "가" * length)[:length] if length > 8 else "가" * length
            text = notify.format_notice("M007", {**nth.MERGE, "pr_title": title})
            self.assertIn("<code>" + title + "</code>", text, length)
            self.assertNotIn("…", text.split("PR 제목: ")[1].split("\n")[0], length)

    def test_a_title_that_cannot_be_shown_exactly_is_refused_not_changed(self):
        secret_like = "[R-1] key " + "AIza" + "x" * 35
        for title, code in ((secret_like, "secret"), ("[R-1] x\u200by", "control"), ("[R-1] x\u202ey", "control"), ("[R-1] a\tb", "control"), ("[R-1] a\nb", "control"),
                            ("[R-1] a\u2028b", "control"), ("[R-1] a\x00b", "control"), ("[R-1] a\x7fb", "control"), ("", "empty"), ("   ", "empty"), (None, "empty")):
            with self.assertRaises(notify.NoticeRefused, msg=repr(title)) as caught:
                notify.format_notice("M007", {**nth.MERGE, "pr_title": title})
            self.assertEqual(caught.exception.code, code, repr(title))
            self.assertIsInstance(caught.exception, ValueError)
        self.assertEqual(notify.pr_title_problem("가" * 201, limit=200), "too_long")
        self.assertEqual(notify.pr_title_problem("가" * 200, limit=200), "")
        self.assertEqual(notify.pr_title_problem("가" * 201), "")

    def test_the_notifier_refuses_to_send_such_a_title_and_never_sends_a_changed_one(self):
        notifier, net, _clock = nh.make_notifier()
        result = notifier.notify_notice("M007", {**nth.MERGE, "pr_title": "[R-1] a\u200bb"})
        self.assertEqual((result.sent, result.ok, result.reason), (False, False, notify.REFUSED))
        self.assertEqual(net.calls, 0)
        self.assertIn("PR 제목", notify.describe(result))
        self.assertIn("그대로", notify.describe(result))
        result = notifier.notify_notice("M007", nth.MERGE)
        self.assertTrue(result.sent)
        body = net.bodies()[0]
        self.assertEqual(body["parse_mode"], "HTML")
        self.assertIn("<code>[R-160] 5채널 전략 'P2b'", body["text"])

    def test_the_pr_title_is_whole_even_when_escaping_makes_the_html_longer_than_the_limit(self):
        """`&` 가 많으면 이스케이프(`&amp;`)로 HTML 글이 길어져 서식을 버리고 평문으로 보내지만 제목은 그대로 온다(런타임은 200자보다 긴 제목도 줄이지 않는다)."""
        title = "[R-160] " + "&" * 1000
        notifier, net, _clock = nh.make_notifier()
        text = notify.format_notice("M007", {**nth.MERGE, "pr_title": title})
        self.assertGreater(notify.utf16_len(text), notify.TEXT_LIMIT)
        self.assertTrue(notifier.notify_notice("M007", {**nth.MERGE, "pr_title": title}).sent)
        body = net.bodies()[0]
        self.assertNotIn("parse_mode", body)
        self.assertIn("PR 제목: " + title, body["text"])
        self.assertLessEqual(notify.utf16_len(body["text"]), notify.TEXT_LIMIT)

    def test_a_progress_or_ask_number_is_refused_for_the_merge_form(self):
        for no in ("P007", "007", "M12", ""):
            with self.assertRaises(ValueError, msg=no):
                notify.format_merge_request(no, nth.MERGE)


class AskFormatTest(unittest.TestCase):
    FIELDS = {"summary": "현황 알림을 지금부터 4시간 간격으로 바꿀까요?", **nth.ASK}

    def test_the_message_is_the_how_to_answer_under_the_content_options_and_default_word_for_word(self):
        text = notify.format_notice("003", self.FIELDS)
        self.assertEqual(text, "\n".join([
            f"{notify.BELL_MARK} <b>003 · 확인 요청</b>",
            "확인이 필요한 내용: 현황 알림을 지금부터 4시간 간격으로 바꿀까요?",
            "보기: ① 지금부터 적용  ② 새 번호 체계 병합 뒤부터 적용  ③ 바꾸지 않음",
            "기본값: ① — 답이 없으면 이대로 진행합니다",
            "승인 보기: ② (이 요청에 적힌 항목에 한해 승인으로 읽습니다)",
            "답하는 법: [답하기] → 대상번호 003 (선택은 비워도 됩니다)"]))

    def test_without_an_approve_option_there_is_no_approval_line_and_without_a_default_it_says_so(self):
        text = notify.format_notice("003", {**self.FIELDS, "approve": ""})
        self.assertNotIn("승인 보기", text)
        self.assertIn("기본값: ① — 답이 없으면 이대로 진행합니다", text)
        text = notify.format_notice("003", {"summary": "고르세요", "options": "가 / 나"})
        self.assertEqual(text.splitlines()[3], "기본값: 없음 — 답이 필요합니다")
        self.assertNotIn("승인 보기", text)

    def test_without_options_there_are_no_options_default_or_approval_lines(self):
        text = notify.format_notice("004", {"summary": "AI 가 못 하는 일을 해 주세요"})
        self.assertEqual(text, "\n".join([f"{notify.BELL_MARK} <b>004 · 확인 요청</b>", "확인이 필요한 내용: AI 가 못 하는 일을 해 주세요",
                                         "답하는 법: [답하기] → 대상번호 004 (내용 칸에 답을 적어 주세요)"]))
        self.assertNotIn("보기", text)
        self.assertEqual(notify.format_notice("004", {"summary": "x", "options": ""}).count("\n"), 2)

    def test_up_to_five_options_are_numbered_with_circled_digits(self):
        text = notify.format_notice("003", {"summary": "고르세요", "options": " / ".join(f"보기{i}" for i in range(1, 6)), "default": "5"})
        self.assertIn("보기: ① 보기1  ② 보기2  ③ 보기3  ④ 보기4  ⑤ 보기5", text)
        self.assertIn("기본값: ⑤ — 답이 없으면 이대로 진행합니다", text)
        self.assertEqual(notify.CIRCLED_DIGITS, tuple(chr(0x2460 + index) for index in range(5)))

    def test_bad_option_lists_are_refused(self):
        for options in ("하나만", "가 / ", " / 가", "가 /  / 나", " / ".join("x" * 3 for _ in range(6)), "가/나"):
            with self.assertRaises(ValueError, msg=options):
                notify.format_notice("003", {"summary": "x", "options": options})
        with self.assertRaises(ValueError):
            notify.format_notice("003", {"summary": "", "options": "가 / 나"})
        for key, value in (("default", "0"), ("default", "6"), ("default", "3"), ("default", "①"), ("default", "01"), ("default", "-1"), ("approve", "3"), ("approve", "０"), ("approve", "x")):
            with self.assertRaises(ValueError, msg=(key, value)):
                notify.format_notice("003", {"summary": "x", "options": "가 / 나", key: value})
        for key in ("default", "approve"):
            with self.assertRaises(ValueError, msg=key):
                notify.format_notice("003", {"summary": "x", key: "1"})                 # 보기가 없는데 번호가 있다

    def test_the_approval_option_can_never_be_the_default_option(self):
        """답이 없을 때 진행하는 보기가 곧 승인 보기면 침묵이 승인이 된다 — 거절한다."""
        for number in "12":
            with self.assertRaises(ValueError) as caught:
                notify.format_notice("003", {"summary": "x", "options": "가 / 나", "default": number, "approve": number})
            self.assertEqual(str(caught.exception), "approve")
        self.assertIn("승인 보기: ②", notify.format_notice("003", {"summary": "x", "options": "가 / 나", "default": "1", "approve": "2"}))

    def test_values_are_sanitised(self):
        text = notify.format_notice("003", {"summary": "@owner https://evil.example/x R-090 <b>x</b> & ::x::", "options": "R-090 / https://a.b / <i>y</i>"})
        body = "\n".join(text.splitlines()[1:3])
        for needle in ("@", "https://", "::", "R-090", "<b>x", "<i>y"):
            self.assertNotIn(needle, body, needle)
        self.assertIn("r090", body)
        self.assertIn("＠owner", body)

    def test_long_summary_and_options_are_cut(self):
        text = notify.format_notice("003", {"summary": "가" * 500, "options": " / ".join(["나" * 200, "다" * 200])})
        lines = text.splitlines()
        self.assertTrue(lines[1].endswith("…") and len(lines[1]) <= len("확인이 필요한 내용: ") + notify.REQUEST_SUMMARY_LIMIT)
        self.assertEqual(lines[2].count("…"), 2)

    def test_a_number_that_is_not_a_plain_number_is_refused(self):
        for no in ("P003", "M003", "03", "3", "", None):
            with self.assertRaises(ValueError, msg=no):
                notify.format_ask(no, {"summary": "x"})


class DispatchAndLimitTest(unittest.TestCase):
    def test_the_number_decides_the_form(self):
        self.assertIn("진행 현황", notify.format_notice("P012", nth.PROGRESS))
        self.assertIn("병합 요청", notify.format_notice("M007", nth.MERGE))
        self.assertIn("확인 요청", notify.format_notice("003", {"summary": "x"}))
        for no in ("", "P000", "X001", None, "R-001"):
            with self.assertRaises(ValueError, msg=no):
                notify.format_notice(no, nth.PROGRESS)

    def test_only_the_urgent_word_marks_the_head_and_any_other_value_does_not(self):
        for no, fields in (("P012", nth.PROGRESS), ("M007", nth.MERGE), ("003", {"summary": "x", **nth.ASK})):
            for urgency in ("보통", "", "높음", None, "긴급", "급함 ", "urgent"):
                self.assertNotIn(notify.SIREN_MARK, notify.format_notice(no, fields, urgency=urgency), (no, urgency))
            head = notify.format_notice(no, fields, urgency="급함").splitlines()[0]
            self.assertTrue(head.endswith(f" {notify.SIREN_MARK} 급함"), (no, head))

    def test_a_non_dict_fields_is_an_empty_one_and_so_a_missing_value(self):
        for fields in (None, "x", [("now", "x")], 7):
            with self.assertRaises(ValueError):
                notify.format_notice("P012", fields)

    def test_the_largest_allowed_messages_fit_the_text_limit_with_room(self):
        wide = {"progress": {"at": "2026-11-06 12:07", "now": "가" * 200, "changed": "나" * 200, "next": "다" * 200, "eta": "라" * 100, "waiting": "마" * 200, "check": "바" * 60},
                "merge": {"repo": "o" * 39 + "/" + "r" * 100, "target": "가" * 100, "pr_title": "나" * 200, "verify": "다" * 120, "state": "라" * 40},
                "ask": {"summary": "가" * 300, "options": " / ".join("나" * 60 for _ in range(5)), "default": "1", "approve": "2"}}
        for no, kind in (("P1234", "progress"), ("M1234", "merge"), ("1234", "ask")):
            text = notify.format_notice(no, wide[kind], urgency="급함", work="R-160", pr=9999999, more=99)
            self.assertLess(notify.utf16_len(text), notify.TEXT_LIMIT // 2, kind)

    def test_emoji_values_count_twice_in_utf16_and_the_message_still_fits(self):
        text = notify.format_notice("P012", {**nth.PROGRESS, "now": "😀" * 200, "changed": "🚀" * 200, "next": "✅" * 200, "waiting": "🔧" * 200})
        self.assertLess(notify.utf16_len(text), notify.TEXT_LIMIT)
        self.assertGreater(notify.utf16_len(text), len(text))

    def test_the_largest_messages_are_delivered_whole_by_the_notifier(self):
        for no, fields in (("P012", nth.PROGRESS), ("M007", nth.MERGE), ("003", {"summary": "x", **nth.ASK})):
            notifier, net, _clock = nh.make_notifier()
            self.assertTrue(notifier.notify_notice(no, fields, urgency="급함", buttons=[("요청 열기", notify.REPO_URL)]).sent, no)
            body = net.bodies()[0]
            self.assertEqual(body["parse_mode"], "HTML")
            self.assertLessEqual(notify.utf16_len(body["text"]), notify.TEXT_LIMIT)
            self.assertEqual(body["reply_markup"]["inline_keyboard"][0][0]["text"], "요청 열기")
            self.assertEqual(nh.leaks(json.dumps(body, ensure_ascii=False), chat=False), [])

    def test_a_failure_to_format_is_a_failed_result_not_an_exception(self):
        notifier, net, _clock = nh.make_notifier()
        result = notifier.notify_notice("P012", {"at": "bad"})
        self.assertEqual((result.sent, result.reason), (False, notify.INTERNAL_ERROR))
        self.assertEqual(net.calls, 0)

    def test_the_module_level_wrappers_use_the_given_notifier(self):
        notifier, net, _clock = nh.make_notifier()
        self.assertTrue(notify.notify_notice("P012", nth.PROGRESS, notifier=notifier).sent)
        self.assertTrue(notify.notify_answer_received("003", 2, 145, notifier=notifier).sent)
        self.assertTrue(notify.notify_answer_error(145, "대상번호가 필요합니다", notifier=notifier).sent)
        self.assertEqual(net.calls, 3)


class AnswerMessageTest(unittest.TestCase):
    def test_the_receipt_for_an_answer_with_a_choice_a_bare_number_and_a_replacement(self):
        self.assertEqual(notify.format_answer_received("003", 2, 145), f"{notify.OK_MARK} 답변 접수 003 → 선택 ②(이슈 #145)")
        self.assertEqual(notify.format_answer_received("003", 0, 145), f"{notify.OK_MARK} 답변 접수 003 → 확인함 — 승인 아님(이슈 #145) · 번호가 요청과 맞는지는 AI 가 대조합니다")
        self.assertNotIn("승인 아님", notify.format_answer_received("003", 2, 145))                          # 선택이 있는 접수에는 '확인함' 문구가 없다
        self.assertNotIn("대조", notify.format_answer_received("003", 2, 145))
        self.assertEqual(notify.format_answer_received("003", 1, 146, replaced=145), f"{notify.OK_MARK} 답변 접수 003 → 선택 ①(이슈 #146) · 이전 답(이슈 #145)을 대체합니다")
        self.assertEqual(notify.format_answer_received("1000", 5, 7), f"{notify.OK_MARK} 답변 접수 1000 → 선택 ⑤(이슈 #7)")

    def test_an_old_request_number_is_shown_in_the_phone_form_and_cannot_be_approved_here(self):
        text = notify.format_answer_received("R-149", 2, 146)
        self.assertEqual(text, f"{notify.OK_MARK} 답변 접수 r149 → 선택 ②(이슈 #146) · 옛 R 번호 요청은 새 양식으로 승인되지 않습니다(승인은 이전 R 번호용 양식으로)")
        self.assertNotIn("R-149", text)

    def test_bad_values_are_refused(self):
        for target in ("", "P012", "M007", "12", "r149", "R149", "R-1", None, 3, "003 "):
            with self.assertRaises(ValueError, msg=repr(target)):
                notify.format_answer_received(target, 0, 1)
        for choice in (-1, 6, True, "2", 1.5, None):
            with self.assertRaises(ValueError, msg=repr(choice)):
                notify.format_answer_received("003", choice, 1)
        for issue in (0, -1, True, "1", None):
            with self.assertRaises(ValueError, msg=repr(issue)):
                notify.format_answer_received("003", 0, issue)
        for replaced in (0, -1, True, "1"):
            with self.assertRaises(ValueError, msg=repr(replaced)):
                notify.format_answer_received("003", 0, 5, replaced=replaced)

    def test_the_old_request_number_in_a_receipt_must_be_exactly_a_request_number(self):
        """수정 1차(V3 N39): 접수 회신의 옛 요청 번호는 `R-` + 숫자 세 자리 **전체**여야 한다 — `fullmatch` 를 `match` 로 바꾸면 `R-1499`·`R-149x` 가 앞 다섯 글자만 보고 통과한다."""
        for bad in ("R-1499", "R-149x", "R-149 ", " R-149", "R-14", "R-1", "r-149", "R149", "R-１４９", "R-149\n", "R-149메모", "R-"):
            with self.assertRaises(ValueError, msg=repr(bad)) as caught:
                notify.format_answer_received(bad, 2, 5)
            self.assertEqual(str(caught.exception), "target", repr(bad))                         # `match` 로 바꿔도 display_id 가 ValueError('request_id') 를 내므로 인자 이름까지 못박는다
        self.assertIn("r149", notify.format_answer_received("R-149", 2, 5))

    def test_the_error_reply_names_the_issue_and_one_fixed_reason(self):
        text = notify.format_answer_error(145, "`대상번호`가 필요합니다(텔레그램 확인 요청 맨 위의 숫자 3자리, 예: 001)")
        self.assertEqual(text, f"{notify.WARN_MARK} 답변을 접수하지 못했습니다(이슈 #145) — 대상번호가 필요합니다(텔레그램 확인 요청 맨 위의 숫자 3자리, 예: 001). 새 이슈로 다시 올려 주세요.")
        self.assertNotIn("`", text)
        for bad in ("", "   ", None, chr(0x200B)):
            with self.assertRaises(ValueError, msg=repr(bad)):
                notify.format_answer_error(145, bad)
        with self.assertRaises(ValueError):
            notify.format_answer_error(0, "이유")

    def test_the_error_reply_sanitises_its_reason_even_if_a_caller_passes_unsafe_text(self):
        text = notify.format_answer_error(7, "첫 줄\n::error::x " + "AIza" + "x" * 35 + " " + "가" * 300)
        self.assertEqual(len(text.splitlines()), 1)
        self.assertNotIn("::", text)
        self.assertNotIn("AIza", text)
        self.assertIn("…", text)

    def test_the_warning_mark_is_the_emoji_form_and_the_ok_mark_is_unchanged(self):
        self.assertEqual(notify.WARN_MARK, "⚠️")
        self.assertEqual(notify.OK_MARK, "✅")


if __name__ == "__main__":
    unittest.main()
