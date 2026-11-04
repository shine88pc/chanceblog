"""요청 번호 표기(2026-11-04 운영자 요청) 시험 — 운영자에게 보이는 글은 `r090`, 안쪽 기록은 `R-090`, 운영자가 쓰는 입력은 `r090`·`R090`·`r-090`·`R-090`·`r 090` 모두 같은 요청.

운영자가 요청(2026-11-04 이슈 #110, 메모 '요청번호 작성 방법 수정 / r090 형태로 변경 - 삭제')으로 요청 번호를 `r090` 꼴로 바꿔 달라고 했다. 이 통로(AI 의 텔레그램 요청 ↔ 운영자의 답하기 이슈)는 운영자와 AI 의 유일한 연락 수단이라
표기를 바꾸면서 기존 동작(요청 파일 이름·앞머리 id·접수 이슈·멱등·보안 경계)이 하나도 깨지면 안 된다 — 그래서 아래를 글자 그대로 고정한다.
  1. display_id 표(000~999 전부·정본이 아닌 입력은 ValueError)와 '보이는 꼴을 그대로 다시 쳐도 접수된다'는 되돌림 성질
  2. normalize_request_id 표(허용 꼴 16종·거절 꼴 80종)와 독립 기준(손으로 쓴 판정)과의 전수 대조(길이 5 이하 16만 개 글), 정규화가 신뢰 판정 뒤에만 일어나는 순서
  3. 텔레그램 글 전체를 글자 그대로(머리·답하는 법·답변 접수 확인·새 일 접수 확인)
  4. 접수 코멘트 문구·`ack:v1` 멱등·요청 파일과의 짝짓기(`r090` 로 쳐도 요청 R-090 과 짝지어진다)
  5. 진짜 흐름: 요청 파일 push → 가짜 텔레그램 글 → 운영자가 보이는 번호를 쳐 답함 → 접수 — 코드가 만든 글에 `R-숫자` 가 하나도 없음, 옛 꼴 `R-090` 입력도 접수
  6. AI 가 쓴 제목·요약 속 번호(display_text): 요청 자신의 `[R-nnn]` 꼬리표와 맨 번호만 바꾸고 PR·커밋 제목 인용(「…」·백틱·`[R-nnn]`)·파일 이름 꼴은 그대로(표 38종 + 손으로 쓴 한 글자씩 판정과의 무작위 대조)
  7. 안쪽 기록(파일 이름·id·로그·실행 요약)은 정본 그대로, 양식·문서가 새 표기를 말함
네트워크·실제 GitHub·실제 텔레그램은 쓰지 않는다(가짜 알림기·가짜 GitHub).
"""
import itertools
import json
import random
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import _bootstrap
import operator_loop_helpers as oh
from notify_helpers import FakeNet
from operator_loop_helpers import ANSWER, OWNER, FakeGitHub, RequestGit, ack_env, issue_event, reply_body, request_text, requests_env
from pipeline import notify
from pipeline import operator_loop as ol

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

OK, BELL, SIREN = notify.OK_MARK, notify.BELL_MARK, notify.SIREN_MARK
ZWSP, ZWJ, BOM, SHY, RLO = chr(0x200B), chr(0x200D), chr(0xFEFF), chr(0x00AD), chr(0x202E)


def accepted(raw):
    """정규화한 값이 정본 모양(REQUEST_ID_RE)을 통과하는가 — 접수 코드가 쓰는 판정 그대로."""
    return notify.REQUEST_ID_RE.fullmatch(ol.normalize_request_id(raw)) is not None


def hand_oracle(raw):
    """normalize_request_id 와 따로 손으로 쓴 판정: 앞뒤 공백을 떼고 [rR] + (공백 한 칸 또는 하이픈 한 개, 없어도 됨) + ASCII 숫자 세 자리 전체일 때만 정본 `R-ddd`, 아니면 None."""
    text = raw.strip()
    digits = "0123456789"
    if len(text) == 4 and text[0] in "rR" and all(char in digits for char in text[1:]):
        return "R-" + text[1:]
    if len(text) == 5 and text[0] in "rR" and text[1] in " -" and all(char in digits for char in text[2:]):
        return "R-" + text[2:]
    return None


def hand_display_text(text, lead_tag=False):
    """display_text 와 따로 손으로 쓴 판정(정규식 없이 한 글자씩): 「」·『』·백틱 안은 그대로, 맨 `R-ddd` 만 `rddd`. 맨 앞 `[R-ddd]`(뒤가 공백·끝)는 lead_tag 일 때만."""
    digits = set("0123456789")
    alnum = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz") | digits
    blocked_before, blocked_after = alnum | set("_-["), alnum | set("_-]")
    out, index, size = [], 0, len(text)
    if lead_tag and size >= 7 and text.startswith("[R-") and all(char in digits for char in text[3:6]) and text[6] == "]" and (size == 7 or text[7].isspace()):
        out.append("[r" + text[3:6] + "]")
        index = 7
    closers = {"「": "」", "『": "』", "`": "`"}
    while index < size:
        char = text[index]
        if char in closers:
            end = text.find(closers[char], index + 1)
            if end != -1:
                out.append(text[index:end + 1])
                index = end + 1
                continue
        if text.startswith("R-", index) and index + 5 <= size and all(item in digits for item in text[index + 2:index + 5]):
            before = text[index - 1] if index > 0 else ""
            after = text[index + 5] if index + 5 < size else ""
            after2 = text[index + 6] if index + 6 < size else ""
            if before not in blocked_before and after not in blocked_after and not (after == "." and after2 in alnum):
                out.append("r" + text[index + 2:index + 5])
                index += 5
                continue
        out.append(char)
        index += 1
    return "".join(out)


def legacy_normalize(raw):
    """표기 변경 전(6a5fed2)의 normalize_request_id 그대로 — 옛 방식으로 쓴 입력이 하나도 깨지지 않았음을 전수로 대조하는 기준."""
    text = str(raw).strip()
    if text[:2] == "r-":
        return "R-" + text[2:]
    return text


class DisplayIdTest(unittest.TestCase):
    def test_every_number_from_000_to_999_is_a_lowercase_r_and_the_same_three_digits(self):
        for number in range(1000):
            canonical = f"R-{number:03d}"
            shown = notify.display_id(canonical)
            self.assertEqual(shown, f"r{number:03d}", canonical)
            self.assertEqual((len(shown), shown[0], shown[1:].isdigit()), (4, "r", True), canonical)

    def test_the_edges_and_the_numbers_the_operator_actually_sees(self):
        for canonical, shown in (("R-000", "r000"), ("R-001", "r001"), ("R-009", "r009"), ("R-010", "r010"), ("R-090", "r090"), ("R-099", "r099"), ("R-100", "r100"), ("R-999", "r999")):
            self.assertEqual(notify.display_id(canonical), shown)

    def test_anything_but_the_canonical_form_is_a_value_error(self):
        bad = ["", " ", "R-", "R-0", "R-09", "R-90", "R-0900", "R--090", "R_090", "R090", "r-090", "r090", "R-090 ", " R-090", "R-090\n", "\nR-090", "R-090\r\n", "R-090x", "xR-090", "R-09a",
               "R−090", "R‑090", "R–090", "R－090", "Ｒ-090", "R-０９０", "R-٠٩٠", "R-090" + ZWSP, ZWSP + "R-090", "R-0" + ZWJ + "90", BOM + "R-090", "R-090\0", "R-090,R-091",
               None, 90, 90.0, True, False, b"R-090", ["R-090"], ("R-090",), {"R-090": 1}, object()]
        for value in bad:
            with self.assertRaises(ValueError, msg=repr(value)) as caught:
                notify.display_id(value)
            self.assertEqual(str(caught.exception), "request_id")

    def test_what_the_operator_sees_is_accepted_back_as_the_same_request(self):
        """보이는 꼴을 그대로 다시 쳐도(또는 옛 꼴로 쳐도) 같은 요청으로 접수된다 — 이 표기 변경의 핵심 성질."""
        for number in range(1000):
            canonical = f"R-{number:03d}"
            self.assertEqual(ol.normalize_request_id(notify.display_id(canonical)), canonical, canonical)
            self.assertEqual(ol.normalize_request_id(canonical), canonical)

    def test_the_function_lives_in_the_shared_module_only(self):
        self.assertFalse(hasattr(ol, "display_id"), "표시 변환은 공용 모듈(notify)에 하나만 둔다")
        self.assertIs(ol.notify, notify)
        self.assertEqual(ol.REQUEST_ID_EXAMPLE, notify.display_id("R-001"))
        self.assertEqual(ol.REQUEST_ID_EXAMPLE, "r001")


class NormalizeTableTest(unittest.TestCase):
    ACCEPT = (
        ("R-090", "R-090"), ("r-090", "R-090"), ("R090", "R-090"), ("r090", "R-090"), ("r 090", "R-090"), ("R 090", "R-090"),
        (" r090 ", "R-090"), ("  R-090  ", "R-090"), ("\tr090\n", "R-090"), ("r000", "R-000"), ("R999", "R-999"), ("r-001", "R-001"),
        (chr(0x00A0) + "r090" + chr(0x00A0), "R-090"), (chr(0x3000) + "R-090" + chr(0x3000), "R-090"), ("r090\r\n", "R-090"), ("r 007", "R-007"),
    )
    REJECT = (
        # 번호 칸의 글자·자리 수 틀림
        "", "   ", "r", "R", "r-", "r9", "R9", "R-90", "r90", "r09", "r0900", "R-0900", "r-0-90", "r--090", "R--090", "rr090", "rR090", "R-R090", "r090x", "r09a", "ro90", "x090", "090", "-090",
        "r-090.", "r090,", "r090)", "(r090)", "[r090]", "`r090`", "**r090**", "#r090", "@r090", "R_090", "r_090", "r.090", "r/090", "r:090", "r~090",
        # 전각·다른 하이픈·다른 숫자·닮은 글자
        chr(0xFF52) + "090", chr(0xFF32) + "090", chr(0xFF52) + "-090", "r" + "".join(chr(0xFF10 + int(d)) for d in "090"), "R-" + "".join(chr(0xFF10 + int(d)) for d in "090"),
        "r" + chr(0x2212) + "090", "r" + chr(0x2011) + "090", "r" + chr(0x2013) + "090", "r" + chr(0x2014) + "090", "r" + chr(0xFF0D) + "090", "r" + "".join(chr(0x0660 + int(d)) for d in "090"),
        chr(0x0131) + "090", chr(0x017F) + "090", chr(0x0440) + "090", chr(0x212A) + "090",
        # 안쪽 공백·탭·줄 바꿈·메모가 붙은 꼴
        "r0 90", "r09 0", "r  090", "r\t090", "r" + chr(0x00A0) + "090", "r- 090", "r -090", "r - 090", " r - 090 ", "r090 메모", "r090\t메모", "r090\nr091", "r-090\n메모", "r090\n### 답변\n\n승인", "r090\r\nR-091",
        "R-090\nR-091", "r090 r091",
        # 보이지 않는 문자
        ZWSP + "r090", "r" + ZWSP + "090", "r090" + ZWSP, BOM + "r090", "r" + SHY + "090", RLO + "r090", "r0" + ZWJ + "90", "\0r090", "r090\0",
    )

    def test_the_accepted_forms_all_become_the_canonical_number(self):
        self.assertGreaterEqual(len(self.ACCEPT), 12)
        for raw, want in self.ACCEPT:
            self.assertEqual(ol.normalize_request_id(raw), want, repr(raw))
            self.assertTrue(accepted(raw), repr(raw))

    def test_the_rejected_forms_stay_rejected_by_the_canonical_pattern(self):
        self.assertGreaterEqual(len(self.REJECT), 20)
        for raw in self.REJECT:
            self.assertFalse(accepted(raw), repr(raw))

    def test_a_form_that_is_not_accepted_comes_back_exactly_as_the_old_rule_returned_it(self):
        """받아들이지 않는 꼴은 값을 건드리지 않는다 — 옛 규칙(6a5fed2)이 돌려주던 글 그대로(전각 숫자·두 자리 같은 틀린 꼴을 `R-…` 로 곱게 바꿔 오해를 부르지 않게)."""
        for raw in self.REJECT:
            self.assertEqual(ol.normalize_request_id(raw), legacy_normalize(raw), repr(raw))
        self.assertEqual(ol.normalize_request_id("r90"), "r90")
        self.assertEqual(ol.normalize_request_id("R-90"), "R-90")
        self.assertEqual(ol.normalize_request_id("r" + "".join(chr(0xFF10 + int(digit)) for digit in "090")), "r" + "".join(chr(0xFF10 + int(digit)) for digit in "090"))

    def test_the_old_behaviours_that_other_tests_pin_still_hold(self):
        """기존 시험이 고정한 값: 앞뒤 공백만 떼고 `r-` 로 시작하는 나머지 꼴은 앞의 r 만 대문자로(어차피 거절), 다른 꼴은 그대로."""
        for raw, want in (("r-002", "R-002"), (" r-002 ", "R-002"), ("\tr-002\n", "R-002"), ("R-002", "R-002"), ("r-ab", "R-ab"), ("rr-002", "rr-002"), ("r_002", "r_002"),
                          ("ı-002", "ı-002"), ("ſ-002", "ſ-002"), ("ｒ-002", "ｒ-002"), ("", "")):
            self.assertEqual(ol.normalize_request_id(raw), want, repr(raw))

    def test_non_text_input_never_raises_and_is_never_accepted(self):
        for raw in (None, 90, 90.0, True, b"r090", ["r090"], object()):
            self.assertFalse(accepted(raw), repr(raw))

    def test_every_short_string_over_a_hostile_alphabet_agrees_with_a_hand_written_oracle(self):
        """독립 기준과의 전수 대조: 허용 글자·위험한 글자(전각 r·보이지 않는 문자·탭·줄 바꿈·공백)로 만든 길이 5 이하의 모든 글."""
        alphabet = ["r", "R", "-", " ", "\t", "\n", "0", "9", "x", chr(0xFF52), ZWSP]
        checked = 0
        for length in range(0, 6):
            for combo in itertools.product(alphabet, repeat=length):
                raw = "".join(combo)
                want = hand_oracle(raw)
                got = ol.normalize_request_id(raw)
                self.assertEqual(notify.REQUEST_ID_RE.fullmatch(got) is not None, want is not None, repr(raw))
                if want is not None:
                    self.assertEqual(got, want, repr(raw))
                checked += 1
        self.assertGreater(checked, 160000)

    def test_everything_the_old_rule_accepted_is_still_accepted_with_the_same_number_and_the_new_forms_are_only_the_hyphenless_ones(self):
        """옛 규칙과의 전수 대조(길이 6 이하): 옛 규칙이 접수하던 입력은 지금도 같은 정본 번호로 접수되고, 새로 접수되는 입력은 하이픈 없는 꼴(`r090`·`R090`·`r 090`·`R 090`)뿐이다."""
        alphabet = ["r", "R", "-", " ", chr(9), chr(10), "0", "9", "x"]
        old_accepted = new_only = 0
        for length in range(0, 7):
            for combo in itertools.product(alphabet, repeat=length):
                raw = "".join(combo)
                legacy = legacy_normalize(raw)
                if notify.REQUEST_ID_RE.fullmatch(legacy):
                    old_accepted += 1
                    self.assertEqual(ol.normalize_request_id(raw), legacy, repr(raw))
                elif accepted(raw):
                    new_only += 1
                    self.assertNotIn("-", raw.strip(), repr(raw))
                    self.assertIsNotNone(hand_oracle(raw), repr(raw))
                else:
                    self.assertEqual(ol.normalize_request_id(raw), legacy, repr(raw))
        self.assertEqual((old_accepted, new_only), (112, 656))                       # 이 글자 집합·길이 6 이하의 모든 글(약 60만 개) 중 옛 규칙 접수 112·새로 접수되는 것 656

    def test_normalization_is_a_plain_function_of_the_text_and_idempotent(self):
        for raw, _want in self.ACCEPT:
            once = ol.normalize_request_id(raw)
            self.assertEqual(ol.normalize_request_id(once), once)


class TrustBoundaryTest(unittest.TestCase):
    """정규화가 보안 경계(작성자·권한·이슈 본문 파싱)를 약하게 하지 않는다: 신뢰 판정이 먼저이고 값은 비교·표시에만 쓰인다."""

    def reply(self, **kwargs):
        args = {"title": "[답변] ", "body": reply_body(request_id="r090"), "login": OWNER, "association": "OWNER", "owner": OWNER}
        args.update(kwargs)
        return ol.parse_reply(args["title"], args["body"], args["login"], args["association"], args["owner"])

    def test_the_owner_with_a_displayed_number_is_accepted_as_the_canonical_request(self):
        result = self.reply()
        self.assertEqual((result.kind, result.request_id, result.answer), ("reply", "R-090", "승인"))
        self.assertRegex(result.request_id, notify.REQUEST_ID_RE.pattern)

    def test_the_normalizer_is_not_even_called_before_the_trust_decision(self):
        with mock.patch.object(ol, "normalize_request_id", side_effect=AssertionError("신뢰 판정 전에 정규화를 불렀다")):
            self.assertEqual(self.reply(login="stranger"), ol.Refusal("not_owner", ()))
            self.assertEqual(self.reply(association="CONTRIBUTOR"), ol.Refusal("not_owner_association", ()))
            self.assertEqual(self.reply(owner=""), ol.Refusal("no_owner", ()))
            self.assertEqual(self.reply(title="[페이지 수정] x"), ol.Refusal("not_form", ()))
            self.assertEqual(self.reply(title="[요청] ", body=oh.task_body()).kind, "task")        # 새 일 요청에는 번호가 없고 정규화도 하지 않는다

    def test_a_stranger_gets_nothing_even_with_a_perfect_displayed_number(self):
        for login, association in (("stranger", "NONE"), ("stranger", "OWNER"), (OWNER, "MEMBER"), (OWNER, "NONE")):
            self.assertIsInstance(self.reply(login=login, association=association), ol.Refusal, (login, association))
        with tempfile.TemporaryDirectory() as tmp:
            for login, association in (("stranger", "OWNER"), (OWNER, "CONTRIBUTOR")):
                event = issue_event(body=reply_body(request_id="r090"), login=login, association=association)
                code, lines, net, github = oh.run_cli("ack", environ=ack_env(tmp, event), root=Path(tmp))
                self.assertEqual((code, net.calls, github.requests), (0, 0, []), (login, association))

    def test_a_hidden_second_line_in_the_number_box_is_refused_not_trimmed(self):
        for hostile in ("r090\nR-091", "r090\n메모", "r-090\n메모", "r090\r\n### 답변\r\n\r\n" + ANSWER["거절"], "r090" + ZWSP, ZWSP + "r090", "r090 <!-- ack:v1 -->", "**r090**", "`r090`",
                        "[r090](https://evil.example)", "<b>r090</b>", "r090\n\n### 요청 번호\n\nR-999", "r090; rm -rf /", "r$(id)090", "r090\n::set-output name=x::1"):
            result = self.reply(body=reply_body(request_id=hostile, crlf=False))
            self.assertIsInstance(result, ol.Refusal, repr(hostile))
            self.assertEqual(result.code, "bad_shape", repr(hostile))
            self.assertLessEqual(len(result.problems), 3)
            for problem in result.problems:
                self.assertNotIn(hostile.strip()[:6], problem)

    def test_the_answer_comes_only_from_the_forms_choices_whatever_the_number_looks_like(self):
        self.assertEqual(self.reply(body=reply_body(request_id="r090", raw_answer="승인")).code, "bad_shape")      # 짧은 말은 선택지가 아니다
        self.assertEqual(self.reply(body=reply_body(request_id="r090", raw_answer="")).code, "bad_shape")
        self.assertEqual(self.reply(body=reply_body(request_id="R-090", answer="거절")).answer, "거절")

    def test_the_number_is_never_taken_from_the_title_or_from_other_boxes(self):
        result = self.reply(title="[답변] r091", body=reply_body(request_id="r090", memo="요청 번호는 r092 입니다", choice="B"))
        self.assertEqual(result.request_id, "R-090")
        self.assertEqual(self.reply(title="[답변] r091", body=reply_body(request_id="", memo="r092")).code, "bad_shape")

    def test_the_whole_parser_agrees_with_the_hand_written_oracle_on_random_number_boxes(self):
        """본문 파서까지 이어서: 올바른 꼴에서 글자를 넣고·지우고·바꾼 무작위 번호 칸(공백·탭·줄 바꿈 포함)은 손으로 쓴 판정이 허용한 것만 접수(Submission)되고, 접수된 번호는 언제나 정본이다."""
        rng = random.Random(1104)
        bases = ["r090", "R-090", "r-090", "R090", "r 090", " r090 ", "R-007", "r999"]
        alphabet = ["r", "R", "-", " ", chr(9), chr(10), "0", "9", "x", ZWSP, chr(0xFF52), "_", "."]
        accepted_count = rejected_count = 0
        for _ in range(4000):
            chars = list(rng.choice(bases))
            for _step in range(rng.randint(0, 2)):
                action = rng.choice(("insert", "delete", "replace"))
                spot = rng.randint(0, len(chars))
                if action == "insert":
                    chars.insert(spot, rng.choice(alphabet))
                elif chars and action == "delete":
                    del chars[min(spot, len(chars) - 1)]
                elif chars:
                    chars[min(spot, len(chars) - 1)] = rng.choice(alphabet)
            raw = "".join(chars)
            result = self.reply(body=reply_body(request_id=raw, crlf=False))
            want = hand_oracle(raw)
            self.assertEqual(isinstance(result, ol.Submission), want is not None, repr(raw))
            if want is not None:
                accepted_count += 1
                self.assertEqual(result.request_id, want, repr(raw))
                self.assertRegex(result.request_id, notify.REQUEST_ID_RE.pattern)
            else:
                rejected_count += 1
                self.assertEqual(result.code, "bad_shape", repr(raw))
        self.assertGreater(accepted_count, 400)
        self.assertGreater(rejected_count, 400)

    def test_a_missing_number_heading_or_box_is_still_named_and_nothing_is_guessed(self):
        no_box = "### 요청 번호\n\n_No response_\n\n### 답변\n\n" + ANSWER["승인"]
        self.assertEqual(self.reply(body=no_box), ol.Refusal("bad_shape", ("`요청 번호` 값이 `r001` 처럼 `r` 와 숫자 세 자리가 아닙니다",)))
        self.assertEqual(self.reply(body="### 답변\n\n" + ANSWER["승인"]), ol.Refusal("bad_shape", ("`요청 번호` 항목이 없습니다",)))


class TelegramTextTest(unittest.TestCase):
    """운영자가 받는 텔레그램 글 전체를 글자 그대로 고정한다."""

    def test_the_header_of_every_kind_shows_the_displayed_number(self):
        for kind, label in (("merge", "병합 부탁"), ("run", "실행 부탁"), ("confirm", "확인 부탁"), ("decision", "결정 부탁"), ("info", "알림")):
            text = notify.format_ai_request("R-090", kind, "제목", "요약")
            first = text.splitlines()[0]
            self.assertEqual(first, f"{BELL} <b>AI 요청 r090 · {label}</b>", kind)
            self.assertNotIn("R-090", text, kind)

    def test_a_merge_request_is_this_text_exactly(self):
        text = notify.format_ai_request("R-090", "merge", "[R-090] 병합 부탁 — 용어·관계 사전(블로그 저장소)",
                                        "병합할 PR 제목 → 「[R-090] 용어·관계 사전 — 문서 시험 [대상: 공통]」 이 제목 하나만 병합합니다(PC 버전 GitHub).", pr=111)
        self.assertEqual(text, "\n".join([f"{BELL} <b>AI 요청 r090 · 병합 부탁</b>", "[r090] 병합 부탁 — 용어·관계 사전(블로그 저장소)",
                                          "병합할 PR 제목 → 「[R-090] 용어·관계 사전 — 문서 시험 [대상: 공통]」 이 제목 하나만 병합합니다(PC 버전 GitHub).", "관련 PR: #111"]))

    def test_a_periodic_status_message_is_this_text_exactly(self):
        text = notify.format_ai_request("R-091", "info", "[R-091] 진행 현황 알림 — 11-04 08:00 기준", "점검 결과: 이상 없음. 핵심: R-090 병합 확인, 표기 변경 구현 중. 하실 일 없음.")
        self.assertEqual(text, "\n".join([f"{BELL} <b>AI 요청 r091 · 알림</b>", "[r091] 진행 현황 알림 — 11-04 08:00 기준",
                                          "점검 결과: 이상 없음. 핵심: r090 병합 확인, 표기 변경 구현 중. 하실 일 없음."]))

    def test_the_how_to_answer_line_names_the_displayed_number(self):
        text = notify.format_ai_request("R-092", "decision", "표기 고르기", "A 또는 B", urgency="급함", pr=5, more=2)
        self.assertEqual(text, "\n".join([f"{BELL} <b>AI 요청 r092 · 결정 부탁</b> {SIREN} 급함", "표기 고르기", "A 또는 B", "관련 PR: #5", "",
                                          "답하는 법: 아래 [답하기] → 양식에서 r092 선택", "", "… 외 2건 (저장소의 인수인계/요청함/ 폴더에서 확인하세요)"]))
        confirm = notify.format_ai_request("R-007", "confirm", "t", "s")
        self.assertEqual(confirm.splitlines()[-1], "답하는 법: 아래 [답하기] → 양식에서 r007 선택")
        for kind in ("merge", "run", "info"):
            self.assertNotIn("답하는 법", notify.format_ai_request("R-007", kind, "t", "s"))

    def test_the_reply_receipt_is_this_text_exactly(self):
        self.assertEqual(notify.format_reply_received("R-090", "승인", 120), f"{OK} 답변 접수 r090 → 승인(이슈 #120)")
        self.assertEqual(notify.format_reply_received("R-090", "승인", 120, choice="B"), f"{OK} 답변 접수 r090 → 승인 · 선택 B(이슈 #120)")
        self.assertEqual(notify.format_reply_received("R-000", "문제", 1), f"{OK} 답변 접수 r000 → 문제(이슈 #1)")

    def test_the_new_task_receipt_has_no_request_number_and_is_unchanged(self):
        self.assertEqual(notify.format_task_received(121, "보통", True), f"{OK} 새 일 요청 접수(이슈 #121) · 긴급도 보통 · 진행 범위 구현까지(T3 제외)")
        self.assertEqual(notify.format_task_received(122, "급함", False), f"{OK} 새 일 요청 접수(이슈 #122) · 긴급도 급함 · 논의·준비까지만")
        self.assertIsNone(re.search(r"[Rr]-?\d", notify.format_task_received(121, "보통", True)))

    def test_the_formatters_still_take_only_the_canonical_number(self):
        """안쪽 호출은 정본 `R-nnn` 만 받는다 — 보이는 꼴을 되넘기면 ValueError(표시와 기록이 섞이지 않게)."""
        for bad in ("r090", "R090", "r-090", "R-90", "R-0900", "R-090\n", "", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                notify.format_ai_request(bad, "merge", "t", "s")
            with self.assertRaises(ValueError, msg=repr(bad)):
                notify.format_reply_received(bad, "승인", 1)
        with self.assertRaises(ValueError):
            notify.format_ai_request("R-090", "zzz", "t", "s")                                        # 번호가 맞아도 종류가 틀리면 그대로 거절

    def test_the_invalid_number_is_reported_before_the_invalid_kind(self):
        with self.assertRaises(ValueError) as caught:
            notify.format_ai_request("r090", "zzz", "t", "s")
        self.assertEqual(str(caught.exception), "request_id")


class DisplayTextTest(unittest.TestCase):
    """AI 가 쓴 제목·요약 속 번호: 요청 자신의 꼬리표와 맨 번호만 바꾸고 PR 제목 인용·파일 이름 꼴은 글자 그대로(운영자가 GitHub 에서 글자까지 같은 PR 제목을 찾아 병합한다)."""

    CASES = (
        ("R-090 병합 확인", False, "r090 병합 확인"),
        ("핵심: R-090 병합 확인, R-091 구현 중", False, "핵심: r090 병합 확인, r091 구현 중"),
        ("(R-090)", False, "(r090)"),
        ("R-090.", False, "r090."),
        ("R-090을 확인", False, "r090을 확인"),
        ("요청R-090", False, "요청r090"),
        ("R-090~R-092", False, "r090~r092"),
        ("R-090/R-091", False, "r090/r091"),
        ("R-090" + chr(0x2013) + "R-092", False, "r090" + chr(0x2013) + "r092"),
        ("R-090\nR-091", False, "r090\nr091"),
        ("「R-090 R-091", False, "「r090 r091"),
        ("[R-090] 병합", True, "[r090] 병합"),
        ("[R-091] 진행 현황 알림 — 11-04 08:00 기준", True, "[r091] 진행 현황 알림 — 11-04 08:00 기준"),
        ("[R-090] 병합 부탁 — R-091 후속 「[R-090] 용어」", True, "[r090] 병합 부탁 — r091 후속 「[R-090] 용어」"),
        ("docs/R-090.md 와 R-091", False, "docs/R-090.md 와 r091"),
        ("`R-090` 와 R-091", False, "`R-090` 와 r091"),
        ("『R-090』 R-091", False, "『R-090』 r091"),
        # 글자 그대로 두는 것
        ("[R-090] 병합", False, "[R-090] 병합"),
        ("[R-090]병합", True, "[R-090]병합"),
        (" [R-090] 병합", True, " [R-090] 병합"),
        ("「[R-090] 용어 사전」 이 제목 하나만", False, "「[R-090] 용어 사전」 이 제목 하나만"),
        ("「[R-090] 용어 사전」 이 제목 하나만", True, "「[R-090] 용어 사전」 이 제목 하나만"),
        ("병합할 PR 제목 → 「[R-090] 용어 — 문서 [대상: 공통]」 이 제목 하나만, R-089 의 저장소와 다릅니다", False, "병합할 PR 제목 → 「[R-090] 용어 — 문서 [대상: 공통]」 이 제목 하나만, r089 의 저장소와 다릅니다"),
        ("PR-123", False, "PR-123"), ("TR-001", False, "TR-001"), ("AR-090", False, "AR-090"), ("R-0901", False, "R-0901"), ("R-09", False, "R-09"), ("R-090-b", False, "R-090-b"),
        ("R-090_x.md", False, "R-090_x.md"), ("인수인계/요청함/R-090_x.md", False, "인수인계/요청함/R-090_x.md"), ("R-090.md", False, "R-090.md"), ("R-090R-091", False, "R-090R-091"),
        ("r-090 r090 R090", False, "r-090 r090 R090"),
        ("Ｒ-090", False, "Ｒ-090"), ("R-０９０", False, "R-０９０"),
        ("", False, ""), ("번호 없음", True, "번호 없음"),
    )

    def test_the_table(self):
        self.assertGreaterEqual(len(self.CASES), 30)
        for text, lead, want in self.CASES:
            self.assertEqual(notify.display_text(text, lead_tag=lead), want, (text, lead))

    def test_it_is_idempotent_never_raises_and_never_touches_a_quoted_span(self):
        rng = random.Random(20261104)
        pieces = ["R-", "R-090", "R-091", "r090", "090", "[", "]", "「", "」", "『", "』", "`", " ", "\n", "_", ".", "-", "a", "PR-", "x", "를", "R-0901", ".md", "/", "&amp;", "[R-092] "]
        quoted = re.compile("「[^」]*」|『[^』]*』|`[^`]*`")
        for _ in range(4000):
            text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 14)))
            for lead in (False, True):
                out = notify.display_text(text, lead_tag=lead)
                self.assertEqual(notify.display_text(out, lead_tag=lead), out, (text, lead))
                self.assertLessEqual(len(out), len(text), (text, lead))
                for span in quoted.finditer(text):
                    if lead and span.start() == 0:
                        continue
                    self.assertIn(span.group(0), out, (text, lead))
            self.assertIsInstance(notify.display_text(text), str)

    def test_a_hand_written_character_by_character_oracle_agrees_on_random_text(self):
        rng = random.Random(7)
        pieces = ["R-", "R-090", "R-12", "R-0901", "r-090", "[", "]", "「", "」", "『", "』", "`", " ", "\n", "_", ".md", ".", "-", "a", "P", "7", "를", "/", "[R-091] ", "[R-092]x", "R-093.", "R-094"]
        for _ in range(6000):
            text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 16)))
            for lead in (False, True):
                self.assertEqual(notify.display_text(text, lead_tag=lead), hand_display_text(text, lead_tag=lead), (text, lead))

    def test_only_the_number_form_changes(self):
        """바뀌는 곳은 `R-ddd` → `rddd`(하이픈 하나 지움)와 맨 앞 `[R-ddd]` → `[rddd]` 뿐이다 — 다른 글자는 하나도 달라지지 않는다."""
        text = "[R-091] 진행 R-090 확인 「[R-090] 제목」 `R-092` R-093.md PR-094 R-095, 끝"
        out = notify.display_text(text, lead_tag=True)
        self.assertEqual(out, "[r091] 진행 r090 확인 「[R-090] 제목」 `R-092` R-093.md PR-094 r095, 끝")
        self.assertEqual(len(text) - len(out), 3)

    def test_the_request_message_applies_it_to_the_title_and_the_summary_after_cleaning(self):
        text = notify.format_ai_request("R-091", "info", "  [R-091]   진행 알림\n둘째 줄", "R-090 확인\n「[R-089] 제목」", urgency="보통")
        self.assertEqual(text.splitlines()[1:], ["[r091] 진행 알림 둘째 줄", "r090 확인 「[R-089] 제목」"])

    def test_a_hostile_title_stays_one_safe_line_and_the_number_rewrite_does_not_open_a_hole(self):
        text = notify.format_ai_request("R-091", "merge", "@owner [R-091] <b>x</b> https://evil.example/R-091", "R-090 @everyone <script>")
        title, summary = text.splitlines()[1:3]
        for part in (title, summary):
            self.assertNotIn("@", part)
            self.assertNotIn("<", part)
        self.assertIn("r090", summary)
        self.assertNotIn("https://", title)


class AckCommentTest(unittest.TestCase):
    def test_the_reply_comment_for_a_known_request_is_this_text_exactly(self):
        sub = ol.Submission("reply", "R-090", "승인", "B", False, 0, "", False)
        self.assertEqual(ol.reply_comment(sub, True), f"{ol.ACK_MARK}\n접수했습니다 — 요청 **r090** · 답: **승인** · 선택: **B**.\n\n{ol.ACK_TAIL}")
        self.assertEqual(ol.reply_comment(sub._replace(choice=""), True).splitlines()[1], "접수했습니다 — 요청 **r090** · 답: **승인**.")

    def test_the_note_for_a_request_that_is_not_in_the_default_branch_names_the_displayed_number(self):
        sub = ol.Submission("reply", "R-090", "보류", "", False, 12, "", False)
        text = ol.reply_comment(sub, False)
        self.assertEqual(text.splitlines()[-1], "- 요청 번호 r090 은 AI 가 자기가 보낸 요청과 대조해 처리합니다(요청 파일이 병합 전 브랜치에만 있으면 이 저장소 기본 브랜치에서는 보이지 않으며 정상일 수 있습니다).")
        self.assertIn("- 메모: 있음(12자)", text)
        self.assertNotIn("R-090", text)

    def test_the_task_comment_points_to_numbered_requests_with_the_displayed_example(self):
        text = ol.task_comment(ol.Submission("task", "", "", "", False, 5, "급함", True))
        self.assertIn("가 필요하면 AI 가 번호 있는 `결정 부탁`(`r001` 같은 번호)으로 따로 묻고, 그때 `[답변]` 양식으로 답해 주세요.", text)
        self.assertNotIn("R-번호", text)
        self.assertEqual(ol.TASK_FORM_NUMBERED_ASK, "번호 있는 `결정 부탁`(`r001` 같은 번호)으로 따로 묻고")

    def test_the_shape_comment_for_a_wrong_number_teaches_the_displayed_form(self):
        result = ol.parse_reply("[답변] ", reply_body(request_id="r9", crlf=False), OWNER, "OWNER", OWNER)
        self.assertEqual(result.problems, ("`요청 번호` 값이 `r001` 처럼 `r` 와 숫자 세 자리가 아닙니다",))
        text = ol.shape_comment(result.problems)
        self.assertTrue(text.startswith(f"{ol.ACK_MARK}\n양식 모양이 달라 처리하지 못했습니다 — `요청 번호` 값이 `r001` 처럼 `r` 와 숫자 세 자리가 아닙니다.\n\n"))
        self.assertNotIn("R-", text)

    def test_the_comment_formatters_do_not_accept_a_displayed_number_as_internal_input(self):
        with self.assertRaises(ValueError):
            ol.reply_comment(ol.Submission("reply", "r090", "승인", "", False, 0, "", False), True)


class RealFlowTest(unittest.TestCase):
    """요청 파일 하나 push → 가짜 텔레그램 글 → 운영자가 보이는 번호를 쳐 답함 → 접수(코멘트·텔레그램) → AI 가 번호로 되찾기. 실제 호출은 없다."""

    NAME = "R-090_notation-choice.md"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo_root = self.tmp / "repo"
        (self.repo_root / ol.REQUEST_DIR).mkdir(parents=True)
        self.text = request_text(id="R-090", kind="decision", title="표기 방식 고르기", summary="A 안과 B 안 중 하나를 골라 주세요(선택 칸에 A 또는 B).", urgency="급함", pr="111")
        (self.repo_root / ol.REQUEST_DIR / self.NAME).write_text(self.text, encoding="utf-8")

    def push(self):
        code, lines, net, _ = oh.run_cli("requests", environ=requests_env(), runner=RequestGit.with_requests({self.NAME: self.text}), root=self.repo_root)
        self.assertEqual((code, net.calls), (0, 1))
        return lines, net.bodies()[0]

    def answer(self, typed, number=31, github=None, answer="승인", memo="B 로 가요"):
        event = issue_event(number=number, body=reply_body(request_id=typed, answer=answer, choice="B", memo=memo))
        env = ack_env(self.tmp, event)
        return oh.run_cli("ack", environ=env, root=self.repo_root, github=github), event

    def test_the_message_the_code_made_has_no_old_style_number_and_the_internal_records_keep_it(self):
        lines, message = self.push()
        text = message["text"]
        self.assertEqual(text.splitlines()[0], f"{BELL} <b>AI 요청 r090 · 결정 부탁</b> {SIREN} 급함")
        self.assertEqual(text.splitlines()[-1], "답하는 법: 아래 [답하기] → 양식에서 r090 선택")
        self.assertIsNone(re.search(r"R-\d", text), text)
        self.assertEqual([button["text"] for button in message["reply_markup"]["inline_keyboard"][0]], ["요청 열기", "PR 열기", "답하기", "사용법"])
        for button in message["reply_markup"]["inline_keyboard"][0]:
            self.assertEqual(notify.allowed_url(button["url"]), button["url"])
        opened = message["reply_markup"]["inline_keyboard"][0][0]["url"]
        self.assertTrue(opened.endswith("/" + self.NAME), opened)                                      # 파일 이름은 정본 그대로
        self.assertEqual(lines, ["AI 요청 알림: R-090 을 알렸습니다"])                                    # 로그는 정본 그대로

    def test_every_form_the_operator_may_type_is_accepted_as_the_same_request_and_acknowledged_with_the_displayed_number(self):
        lines, message = self.push()
        shown = re.search(r"AI 요청 (r[0-9]{3})", message["text"]).group(1)
        self.assertEqual(shown, "r090")
        for index, typed in enumerate((shown, "R090", "r-090", "R-090", " r090 ", "r 090", "R 090", "\tR-090\n")):
            (code, lines, net, github), event = self.answer(typed, number=40 + index)
            self.assertEqual(code, 0, repr(typed))
            comment = github.posted(40 + index)[0]
            self.assertTrue(comment.startswith(f"{ol.ACK_MARK}\n접수했습니다 — 요청 **r090** · 답: **승인** · 선택: **B**."), (typed, comment[:90]))
            self.assertNotIn("대조해 처리합니다", comment, typed)                                         # r090 으로 쳐도 요청 R-090 과 짝지어졌다(요청함에 그 파일이 있다)
            self.assertIsNone(re.search(r"R-\d", comment), comment)
            self.assertEqual(net.bodies()[0]["text"], f"{OK} 답변 접수 r090 → 승인 · 선택 B(이슈 #{40 + index})", repr(typed))
            issue = event["issue"]
            found = ol.parse_reply(issue["title"], issue["body"], issue["user"]["login"], issue["author_association"], OWNER)
            self.assertEqual((found.request_id, found.answer, found.choice), ("R-090", "승인", "B"), repr(typed))
            self.assertIn(found.request_id, ol.known_request_ids(self.repo_root))
            self.assertEqual(ol.parse_request(self.NAME, (self.repo_root / ol.REQUEST_DIR / self.NAME).read_text(encoding="utf-8")).id, found.request_id)

    def test_the_old_style_number_is_still_accepted_exactly_as_before(self):
        (code, lines, net, github), _event = self.answer("R-090", number=51)
        self.assertEqual(code, 0)
        self.assertEqual(net.calls, 1)
        self.assertIn("접수했습니다 — 요청 **r090** · 답: **승인** · 선택: **B**.", github.posted(51)[0])
        self.assertEqual(github.issue_labels, {51: ["운영자응답"]})
        self.assertEqual(lines[-1], "운영자 응답 접수: 텔레그램으로 접수를 알렸습니다")

    def test_a_number_that_is_not_in_the_request_folder_is_accepted_with_the_displayed_number_in_the_note(self):
        (code, lines, net, github), _event = self.answer("r777", number=52)
        self.assertEqual((code, net.calls), (0, 1))
        self.assertIn("요청 번호 r777 은 AI 가 자기가 보낸 요청과 대조해 처리합니다", github.posted(52)[0])
        self.assertEqual(net.bodies()[0]["text"], f"{OK} 답변 접수 r777 → 승인 · 선택 B(이슈 #52)")

    def test_a_wrong_number_gets_one_explanation_in_the_displayed_form_and_no_phone_message(self):
        for typed in ("r9", "R_090", "r0900", "r-0-90", "ｒ090", "r090 메모"):
            (code, lines, net, github), _event = self.answer(typed, number=53)
            self.assertEqual((code, net.calls), (0, 0), typed)
            comment = github.posted(53)[0]
            self.assertIn("`요청 번호` 값이 `r001` 처럼 `r` 와 숫자 세 자리가 아닙니다", comment, typed)
            self.assertNotIn(typed, comment)

    def test_the_same_issue_twice_is_acknowledged_once_in_the_comment_and_once_on_the_phone(self):
        github = FakeGitHub()
        (code, lines, net, github), event = self.answer("r090", number=60, github=github)
        self.assertEqual((len(github.posted(60)), net.calls), (1, 1))
        env = ack_env(self.tmp, event)
        code, lines, net, _ = oh.run_cli("ack", environ=env, root=self.repo_root, github=github)
        self.assertEqual((code, net.calls, len(github.posted(60))), (0, 0, 1))
        self.assertEqual(lines[-1], "운영자 응답 접수: 이슈 #60 에는 접수 코멘트가 이미 있어 다시 달지 않습니다")
        self.assertEqual(len([item for item in github.requests if item["method"] == "POST" and item["path"].endswith("/comments")]), 1)
        self.assertTrue(github.posted(60)[0].startswith(ol.ACK_MARK + "\n"))

    def test_the_same_issue_in_another_form_is_still_one_comment(self):
        """같은 이슈 번호에 다른 꼴의 번호로 두 번 와도(코멘트는 `ack:v1` 표지로 판정) 코멘트는 하나."""
        github = FakeGitHub()
        self.answer("r090", number=61, github=github)
        (code, lines, net, github), _event = self.answer("R-090", number=61, github=github)
        self.assertEqual((len(github.posted(61)), net.calls), (1, 0))

    def test_the_run_summary_file_and_the_log_keep_the_canonical_number(self):
        summary = self.tmp / "summary.md"
        event = issue_event(number=62, body=reply_body(request_id="r090"))
        env = ack_env(self.tmp, event, GITHUB_STEP_SUMMARY=str(summary))
        oh.run_cli("ack", environ=env, root=self.repo_root)
        self.assertEqual(summary.read_text(encoding="utf-8").strip(), "### 운영자 응답 접수\n\n- 이슈 #62: 요청 R-090 · 답 승인 을 접수했습니다")
        summary_requests = self.tmp / "summary_requests.md"
        oh.run_cli("requests", environ=requests_env(GITHUB_STEP_SUMMARY=str(summary_requests)), runner=RequestGit.with_requests({self.NAME: self.text}), root=self.repo_root)
        self.assertEqual(summary_requests.read_text(encoding="utf-8").strip(), "### AI 요청 텔레그램 알림\n\n- R-090: 알렸습니다")

    def test_a_telegram_failure_does_not_change_what_the_comment_says(self):
        from notify_helpers import http_error
        event = issue_event(number=63, body=reply_body(request_id="r090"))
        code, lines, net, github = oh.run_cli("ack", environ=ack_env(self.tmp, event), root=self.repo_root, net=FakeNet(http_error(401, "Unauthorized")))
        self.assertEqual(code, 0)
        self.assertIn("**r090**", github.posted(63)[0])
        self.assertEqual(lines[-1], ol.ACK_WARNING)


class InternalRecordsStayCanonicalTest(unittest.TestCase):
    """안쪽 기록은 그대로다: 요청 파일 이름·앞머리 id·번호 정규식·J3 번호 규칙 — 표기 변경이 이 기록을 건드리지 않는다."""

    def test_the_request_file_name_and_the_front_matter_id_are_still_the_capital_hyphen_form(self):
        self.assertIsNotNone(ol.REQUEST_NAME_RE.fullmatch("R-090_notation-choice.md"))
        for name in ("r090_notation.md", "R090_notation.md", "r-090_notation.md", "R-90_x.md", "R-0900_x.md"):
            self.assertIsNone(ol.REQUEST_NAME_RE.fullmatch(name), name)
        self.assertEqual(notify.REQUEST_ID_RE.pattern, "R-[0-9]{3}")
        request = ol.parse_request("R-090_notation-choice.md", request_text(id="R-090"))
        self.assertEqual(request.id, "R-090")
        for bad_id in ("r090", "R090", "r-090", "R-90"):
            with self.assertRaises(ol.RequestError) as caught:
                ol.parse_request("R-090_notation-choice.md", request_text(id=bad_id))
            self.assertEqual(caught.exception.code, "bad_id", bad_id)
        with self.assertRaises(ol.RequestError) as caught:
            ol.parse_request("r090_notation.md", request_text(id="R-090"))
        self.assertEqual(caught.exception.code, "bad_name")

    def test_the_request_file_problem_texts_for_the_ai_still_show_the_canonical_form(self):
        self.assertIn("`R-001_짧은-영문-설명.md`", ol.problem_text("bad_name"))
        self.assertIn("`R-001`", ol.problem_text("bad_id"))

    def test_known_request_numbers_are_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / ol.REQUEST_DIR
            folder.mkdir(parents=True)
            for name in ("R-090_a.md", "r091_b.md", "R-092_c.md"):
                (folder / name).write_text("x", encoding="utf-8")
            self.assertEqual(ol.known_request_ids(tmp), {"R-090", "R-092"})

    def test_the_branch_numbering_rule_text_is_untouched(self):
        runbook = (ROOT / "docs" / "AGENT_RUNBOOK.md").read_text(encoding="utf-8")
        self.assertIn("R-001", runbook)                                                                # J3(번호 정하기)는 정본 R-nnn 그대로


class FormAndDocsTest(unittest.TestCase):
    def form(self, name):
        return yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / name).read_text(encoding="utf-8"))

    def test_the_reply_form_teaches_the_displayed_form(self):
        data = self.form("ai-reply.yml")
        field = {item["id"]: item for item in data["body"][1:]}["request_id"]["attributes"]
        self.assertEqual(field["placeholder"], "r001")
        self.assertEqual(field["label"], "요청 번호")
        self.assertIn("r001", field["description"])
        notice = data["body"][0]["attributes"]["value"]
        self.assertIn("텔레그램 메시지 맨 위의 `r001` 같은 번호입니다", notice)
        self.assertIn(ol.REQUEST_ID_NOTICE, notice)
        self.assertIn("r001 같은 번호", data["description"])
        self.assertNotRegex(field["placeholder"], r"R-\d")

    def test_the_task_form_notice_uses_the_same_phrase_as_the_comment_and_the_guide(self):
        notice = self.form("ai-task.yml")["body"][0]["attributes"]["value"]
        self.assertIn(ol.TASK_FORM_NUMBERED_ASK, notice)
        self.assertNotIn("R-번호", notice)

    def test_the_documents_state_the_two_notations_and_the_internal_records(self):
        guide = (ROOT / ol.GUIDE_PATH).read_text(encoding="utf-8")
        self.assertIn("**`r001` 이 요청 번호**(소문자 `r` + 숫자 세 자리", guide)
        self.assertIn("`R-001`·`R001`·`r-001`·`r 001` 로 써도 같은 번호로 읽습니다", guide)
        architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        section = architecture[architecture.index("## 4-6."):]
        self.assertIn("**요청 번호 표기**(2026-11-04", section)
        for needle in ("`notify.display_id`", "`normalize_request_id`", "AI 가 쓴 제목·요약 속 번호는 `display_text` 가", "`R-001_….md`", "앞머리 `id: R-001`", "신뢰 판정 뒤에만"):
            self.assertIn(needle, section, needle)
        for rel in ("AGENTS.md", "HANDLER.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("`r001`", text, rel)
            self.assertIn("R-001", text, rel)
        glossary = (ROOT / "docs" / "GLOSSARY.md").read_text(encoding="utf-8")
        self.assertIn("`r090` 꼴(소문자 r + 세 자리, 하이픈 없음)", glossary)
        self.assertIn("요청 번호(요청 파일의 정본은 `R-nnn`, 운영자가 읽는 글에서는 `rnnn`)", glossary)
        readme = (ROOT / ol.REQUEST_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn("**PR·커밋 제목을 인용할 때는 반드시 「…」 안에** 쓰세요", readme)
        telegram_setup = (ROOT / ".github" / "editorial" / "TELEGRAM_SETUP.md").read_text(encoding="utf-8")
        self.assertIn("`🔔 AI 요청 r001 · 병합 부탁`", telegram_setup)

    def test_the_form_rule_FORM_1_checks_the_displayed_example(self):
        files = [vr.REPLY_FORM, vr.TASK_FORM, vr.ISSUE_CONFIG]
        self.assertEqual([finding.line() for finding in vr.check_operator_forms(ROOT, files)], [])
        self.assertEqual(ol.REQUEST_ID_EXAMPLE, "r001")
        self.assertEqual(json.dumps(ol.REQUEST_ID_NOTICE, ensure_ascii=False), '"텔레그램 메시지 맨 위의 `r001` 같은 번호"')


if __name__ == "__main__":
    unittest.main()
