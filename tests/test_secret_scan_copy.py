"""제로폭·전각·결합 글자로 쪼갠 키가 외부 AI 로 나가는 길(결함 D-352).

옛 점검(`safety.sensitive_kinds` → `secret_patterns.find_secrets`)은 키·토큰 모양을 **원문 그대로** 훑었다. NFKC 로 접고 보이지 않는 글자를 지우는 `_fold` 는 주민등록번호·카드번호에만 썼다.
그래서 `ghp_` 사이에 제로폭 공백을 끼우거나 전각 글자로 쓰거나 결합 글자를 붙인 키는 걸리지 않고 AI 로 나갔다. 이제 비밀 모양은 **검사용 사본**(`scan_copy`: NFKD → 서식·결합·제어 글자 지움)도
함께 본다 — 원문은 바꾸지 않고, 걸리면 기존 거절 길(`check_outbound` → `EditError`)로 가며, 저장소 검증기의 SEC-2 와 AI 가 만든 변경의 '새 비밀' 검사(`verify_changes`)도 같은 사본을 쓴다.
가짜 키는 소스에 완성된 모양으로 쓰지 않고(검사가 소스도 훑는다) 런타임에 조립하며 몸통에 CANARY 표지를 넣는다.
"""
import json
import random
import sys
import tempfile
import time
import unicodedata
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
import test_edits_runner
from edits_helpers import ABOUT, image_body, img, issue, page_body, post_text, write
from pipeline import secret_patterns
from pipeline.edits import checks, safety
from pipeline.secret_patterns import find_secrets, scan_copy, scan_copy_spaced
from test_edits_runner import RunnerBase

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

GOOGLE_KEY = "AIza" + "CANARY_" + "B" * 28           # 접두사 뒤 35자(영숫자·밑줄·하이픈)
GITHUB_TOKEN = "gh" + "p_" + "CANARY" + "X" * 30      # 접두사 뒤 영숫자 36자
SK_KEY = "sk-" + "CANARY" + "y" * 30                 # 접두사 뒤 영숫자 36자
KEYS = {"Google API 키": GOOGLE_KEY, "GitHub 토큰": GITHUB_TOKEN, "sk- 형식 API 키": SK_KEY}
LAYOUT = "layout | 섹션/레이아웃 변경 (해당 페이지 안에서만)"
PATCH = {"patches": [{"old": "두 번째 문단입니다.", "new": "두 번째 문단입니다.\n\n**강조 문장입니다.**"}]}

# 키를 쪼개는 보이지 않는 글자 — 종류별 대표. 소스에 보이지 않는 글자를 쓰지 않고 코드 값으로 만든다.
SPLITTERS = {
    "폭 없는 공백 U+200B": 0x200B, "폭 없는 비결합자 U+200C": 0x200C, "폭 없는 결합자 U+200D": 0x200D, "왼쪽→오른쪽 표시 U+200E": 0x200E, "단어 결합자 U+2060": 0x2060,
    "소프트 하이픈 U+00AD": 0x00AD, "BOM U+FEFF": 0xFEFF, "방향 격리 U+2066": 0x2066, "방향 덮어쓰기 U+202E": 0x202E, "아랍 글자 표시 U+061C": 0x061C,
    "몽골 모음 구분 U+180E": 0x180E, "태그 글자 U+E0041": 0xE0041, "이모지 변이 선택자 U+FE0F": 0xFE0F,
    "결합 글자 연결자 U+034F": 0x034F, "결합 악센트 U+0301": 0x0301, "결합 둘러싸기 U+20E3": 0x20E3,
    "한글 채움 글자 U+3164": 0x3164, "한글 초성 채움 U+115F": 0x115F, "점자 빈칸 U+2800": 0x2800,
    "제어 글자 U+0008": 0x0008, "제어 글자 U+001B": 0x001B, "널 U+0000": 0x0000,
    # 아직 배정되지 않은 글자(Cn — 기본으로 안 그려지는 것)와 사용자 정의 영역(Co). 검증자 S 의 SP-5: 이것으로 쪼갠 키가 통과했다
    "미배정 글자 U+2065": 0x2065, "미배정 글자 U+FFF0": 0xFFF0, "미배정 태그 영역 글자 U+E0080": 0xE0080, "미배정 글자 U+E01F0": 0xE01F0, "사용자 정의 영역 U+E000": 0xE000,
}
GLUE_CHARS = (0x0B, 0x0C, 0x1F, 0x0301, 0xFE0F, 0x3164, 0x00, 0x2066, 0xE0041, 0x20E3)      # 번호 바로 앞뒤에 숫자와 함께 붙이면 번호 모양을 깨던 글자(검증자 S 의 SP-6)


def fullwidth(text):
    """ASCII 글자·숫자·기호를 전각으로(웹·문서에서 복사한 값 흉내). 소스에 전각 글자를 직접 쓰지 않는다."""
    return "".join(chr(ord(ch) - 0x21 + 0xFF01) if "!" <= ch <= chr(0x7E) else ch for ch in text)


def split_once(key, code):
    return key[:4] + chr(code) + key[4:]


def split_often(key, code):
    return chr(code).join(key[i:i + 4] for i in range(0, len(key), 4))


class Spy:
    """호출 기록을 남기는 가짜 AI."""

    def __init__(self, payload=PATCH):
        self.calls, self.payload = [], payload

    def __call__(self, *args):
        self.calls.append(args)
        return json.dumps(self.payload, ensure_ascii=False), "m"


class ScanCopyTest(unittest.TestCase):
    def test_fullwidth_and_compatibility_letters_fold_to_ascii(self):
        self.assertEqual(scan_copy(fullwidth("ghp_AB-12")), "ghp_AB-12")
        self.assertEqual(scan_copy("\N{CIRCLED LATIN CAPITAL LETTER A}\N{SUPERSCRIPT TWO}\N{LATIN SMALL LIGATURE FI}"), "A2fi")

    def test_invisible_and_combining_characters_are_removed_and_ordinary_ones_stay(self):
        for name, code in SPLITTERS.items():
            self.assertEqual(scan_copy("ab" + chr(code) + "cd"), "abcd", name)
        self.assertEqual(scan_copy("a\tb\nc\r\nd e"), "a\tb\nc\r\nd e")                      # 탭·줄바꿈·보통 공백은 남긴다
        self.assertEqual(scan_copy("tel 010-1234 / a_b.c"), "tel 010-1234 / a_b.c")
        self.assertEqual(scan_copy("cafe" + "\N{COMBINING ACUTE ACCENT}"), "cafe")
        self.assertEqual(scan_copy("caf\N{LATIN SMALL LETTER E WITH ACUTE}"), "cafe")        # 합쳐 쓴 악센트 글자도 풀려 악센트가 지워진다(NFKC 로는 그대로 남는다)

    def test_none_and_non_text_values(self):
        self.assertEqual(scan_copy(None), "")
        self.assertEqual(scan_copy(123), "123")
        self.assertEqual(scan_copy(""), "")
        self.assertEqual(scan_copy(chr(0xD800) + "ab"), "ab")                                  # 짝 없는 서로게이트가 있어도 예외 없이 지운다

    def test_the_result_is_stable_when_applied_twice(self):
        rng = random.Random(20261122)
        pool = [chr(code) for code in SPLITTERS.values()] + list("abcXYZ019-_ \t\n한글가나") + [fullwidth("A"), "\N{COMBINING ACUTE ACCENT}", "\N{LATIN SMALL LETTER E WITH ACUTE}"]
        for _ in range(300):
            sample = "".join(rng.choice(pool) for _ in range(rng.randint(0, 40)))
            once = scan_copy(sample)
            self.assertEqual(scan_copy(once), once, repr(sample))
            self.assertFalse(any(unicodedata.category(ch) in ("Cf", "Mn", "Me", "Cs", "Cn", "Co") for ch in once), repr(sample))

    def test_the_ascii_shortcut_gives_exactly_the_result_of_the_full_path(self):
        rng = random.Random(7)
        for _ in range(300):
            sample = "".join(chr(rng.randint(0x20, 0x7E)) for _ in range(rng.randint(0, 60)))
            self.assertEqual(scan_copy(sample), unicodedata.normalize("NFKD", sample).translate(secret_patterns._SCAN_TABLE), repr(sample))
        self.assertEqual(scan_copy("a\x1bb"), "ab")                                            # 제어 글자가 든 ASCII 는 지름길을 타지 않는다
        self.assertEqual(scan_copy("a\nb\tc"), "a\nb\tc")

    def test_hangul_syllables_are_put_back_together_so_length_conditions_see_the_original_length(self):
        """NFKD 는 한글 음절을 자모 두세 개로 풀어 글자 수를 늘린다. 마지막에 NFC 로 합치지 않으면 `client_secret` 값 8자 이상 조건에 3자에서 7자 사이의 한글 값이 잘못 걸린다(검증자 Q 의 QP-1)."""
        for text in ("한글 비밀번호", "비밀번호", "여기에 입력", "<값 자리>", "가나다라마바사", "각 닭 읊 삶 값"):
            with self.subTest(text=text):
                self.assertEqual(scan_copy(text), text)
                self.assertEqual(len(scan_copy(text)), len(text))
        self.assertEqual(scan_copy("한글" + chr(0x200B) + "비밀" + chr(0x0301)), "한글비밀")           # 지울 글자만 지우고 한글은 그대로

    def test_a_key_that_straddles_a_chunk_boundary_is_still_found_and_long_hangul_is_unchanged(self):
        edge = min(secret_patterns._SCAN_CHUNK, 8192)          # 조각 크기를 무한으로 키운 변이에서도 시험이 기가바이트 글을 만들지 않게 상한을 둔다(그 변이는 아래 시간 시험이 잡는다)
        key = split_once(GITHUB_TOKEN, 0x200B)
        for offset in (0, 3, 9, len(key) // 2):
            with self.subTest(offset=offset):
                text = "가" * (edge - offset - 1) + " " + key + " " + "나" * 50        # 키는 edge - offset 번째 글자에서 시작해 조각 경계(edge)를 가로지른다(앞에 공백 — 한글 바로 뒤에는 낱말 경계가 없다)
                self.assertEqual([label for label, _ in find_secrets(text)], ["GitHub 토큰"])
        long_hangul = "가나다 " * (edge * 2)
        self.assertEqual(scan_copy(long_hangul), long_hangul)

    def test_long_runs_of_combining_marks_do_not_cost_quadratic_time(self):
        """결합 글자가 순서가 뒤집힌 채 길게 이어지면 한꺼번에 정규화하는 비용이 제곱으로 는다(8만 자에 6초 넘게). 조각으로 나눠 처리하므로 선형에 가깝다(검증자 S 의 SP-8)."""
        text = "a" + chr(0x0345) * 60000 + chr(0x0300) * 60000
        started = time.monotonic()
        self.assertEqual(scan_copy(text), "a")
        self.assertLess(time.monotonic() - started, 2.0)                                       # 조각으로 나누면 0.02초 안팎, 안 나누면 이 PC 에서 10초가 넘는다(12만 자) — 두 값 사이의 넉넉한 상한

    def test_the_spaced_copy_turns_removed_characters_into_blanks(self):
        for name, code in SPLITTERS.items():
            if chr(code) in "\t\n\r":
                continue
            self.assertEqual(scan_copy_spaced("ab" + chr(code) + "cd"), "ab cd", name)
        self.assertEqual(scan_copy_spaced("a\tb\nc"), "a\tb\nc")
        self.assertEqual(scan_copy_spaced("plain ascii 123"), "plain ascii 123")
        self.assertEqual(scan_copy_spaced(None), "")
        self.assertEqual(scan_copy_spaced(fullwidth("ghp_1")), "ghp_1")                        # 전각은 지우지 않고 ASCII 로 접는다
        self.assertEqual(scan_copy_spaced("가" + chr(0x200B) + "나").count(" "), 1)                # 한글은 자모로 풀린 채 둔다(번호 점검에는 숫자 사이의 공백만 중요하다)

    def test_a_large_text_is_folded_quickly(self):
        text = ("가나다 abc 123 " + chr(0x200B) + "ＡＢＣ " + chr(0x0301)) * 20000                  # 약 36만 자
        started = time.monotonic()
        scan_copy(text)
        find_secrets(text)
        self.assertLess(time.monotonic() - started, 10.0)                                      # 느린 PC·병렬 실행에서도 안 흔들리는 넉넉한 상한


class SplitKeysAreFoundTest(unittest.TestCase):
    def test_unsplit_keys_are_found_as_before(self):
        for label, key in KEYS.items():
            self.assertIn(label, [found for found, _ in find_secrets(f"앞 {key} 뒤")], label)

    def test_every_kind_of_invisible_or_combining_character_hides_nothing(self):
        for label, key in KEYS.items():
            for name, code in SPLITTERS.items():
                for how, split in (("한 번", split_once), ("네 글자마다", split_often)):
                    with self.subTest(label=label, splitter=name, how=how):
                        text = "복사한 값: " + split(key, code) + " 끝"
                        found = find_secrets(text)
                        self.assertEqual([found_label for found_label, _ in found], [label])

    def test_fullwidth_keys_are_found(self):
        for label, key in KEYS.items():
            for text in (fullwidth(key), fullwidth(key[:6]) + key[6:], key[:6] + fullwidth(key[6:])):
                with self.subTest(label=label):
                    self.assertEqual([found_label for found_label, _ in find_secrets("값 " + text)], [label])

    def test_mixed_tricks_in_one_key_are_found(self):
        text = fullwidth(GITHUB_TOKEN[:5]) + chr(0x200B) + GITHUB_TOKEN[5:12] + chr(0x0301) + GITHUB_TOKEN[12:30] + chr(0x2060) + fullwidth(GITHUB_TOKEN[30:])
        self.assertEqual([label for label, _ in find_secrets(text)], ["GitHub 토큰"])

    def test_the_preview_never_carries_the_value_or_the_hidden_characters(self):
        text = split_often(GOOGLE_KEY, 0x200B)
        found = find_secrets(text)
        self.assertEqual(found, [("Google API 키", "AIza***")])
        for _label, preview in found:
            self.assertNotIn(chr(0x200B), preview)
            self.assertNotIn("CANARY", preview)

    def test_the_original_text_is_not_changed(self):
        text = split_once(GITHUB_TOKEN, 0x200B)
        copy = str(text)
        find_secrets(text)
        safety.sensitive_kinds(text)
        self.assertEqual(text, copy)
        self.assertIn(chr(0x200B), text)

    def test_a_key_that_is_one_character_too_short_is_still_not_a_key_after_folding(self):
        short = "gh" + "p_" + "CANARY" + "X" * 29                                              # 영숫자 35자
        for text in (short, split_once(short, 0x200B), fullwidth(short)):
            self.assertEqual(find_secrets(text), [])
        google_short = "AIza" + "CANARY_" + "B" * 27
        self.assertEqual(find_secrets(split_often(google_short, 0x200D)), [])


class NoFalsePositiveTest(unittest.TestCase):
    ORDINARY = (
        "안녕하세요. 오늘의 소식을 전합니다." + chr(0x200B) + " 줄바꿈 없는 공백이 낀 문장입니다.",
        "ＡＢＣ 전각 영문과 １２３ 전각 숫자、문장 부호！ 그리고 ？",
        "cafe" + chr(0x0301) + " re" + chr(0x0301) + "sume" + chr(0x0301) + " nai" + chr(0x0308) + "ve",
        "ภาษาไทยมีวรรณยุกต์ हिन्दी में मात्राएँ العَرَبِيَّةُ بِالتَّشْكِيلِ",
        "해시: " + "0123456789abcdef" * 4 + " 와 UUID 123e4567-e89b-12d3-a456-426614174000",
        "사진 photo-1507146426996-ef05306b995a 와 ca-pub-1234567890123456",
        "이모지 " + chr(0x1F600) + chr(0xFE0F) + " 와 가족 " + chr(0x1F468) + chr(0x200D) + chr(0x1F469) + chr(0x200D) + chr(0x1F467),
        chr(0x200B) * 200 + chr(0xFEFF) * 50,
        "AIza", "ghp_", "AIza" + chr(0x200B) + "short", "",
        # 길이 조건(값 8자 이상)이 있는 패턴에 3자에서 7자 사이의 한글 값이 NFKD 로 길어져 걸리던 오탐(검증자 Q 의 QP-1)
        '"client_secret": "비밀번호"', '"client_secret": "여기에 입력"', '"client_secret": "<값 자리>"', "설정 예시: " + '"client_secret": "비밀"' + " 처럼 적는다",
    )
    KOREAN_CLIENT_SECRET_EXAMPLES = ('"client_secret": "비밀번호"', '"client_secret": "여기에 입력"', '"client_secret": "<값 자리>"')

    def test_ordinary_text_in_many_scripts_is_not_flagged(self):
        for text in self.ORDINARY:
            with self.subTest(text=text[:20]):
                self.assertEqual(find_secrets(text), [])
                self.assertEqual(safety.sensitive_kinds(text), [])

    def test_none_is_fine(self):
        self.assertEqual(find_secrets(None), [])
        self.assertEqual(safety.sensitive_kinds(None), [])

    def test_a_real_client_secret_value_is_still_found_in_ascii_and_in_long_hangul(self):
        """대조: 값이 원문에서 8자 이상이면 옛 코드에서도 걸렸다. 길이 조건 자체는 그대로다."""
        value = "CANARY_" + "z" * 8
        head = '"client_secret": ' + '"'                       # 소스 줄이 그 자체로 비밀 모양이 되지 않게(검증기 SEC-2 가 소스도 훑는다) 따옴표를 떼어 조립한다
        for text in (head + value + '"', head + fullwidth(value) + '"', head + "여기에 시크릿 값을 넣으세요" + '"'):
            with self.subTest(text=text[:40]):
                self.assertEqual([label for label, _ in find_secrets(text)], ["client_secret JSON 값"])
                self.assertEqual(safety.sensitive_kinds(text), ["client_secret JSON 값"])

    def test_the_editable_pages_in_this_repository_are_still_clean(self):
        for name in ("about.md", "contact.md", "privacy.md", "categories.md"):
            text = (_bootstrap.ROOT / name).read_bytes().decode("utf-8")
            self.assertEqual(safety.sensitive_kinds(text), [], name)


class OutboundCheckTest(unittest.TestCase):
    def test_a_split_key_is_reported_by_label_only_through_the_outbound_check(self):
        for label, key in KEYS.items():
            text = "고쳐 주세요 " + split_often(key, 0x200D) + " 끝"
            self.assertIn(label, safety.sensitive_kinds(text))
            problems = safety.outbound_problems({"요청 내용": text, "변경 전": "정상 문장", "페이지 원문": "정상 문장"})
            self.assertEqual(problems, [("요청 내용", [label])])
            message = safety.outbound_refusal(problems)
            for hidden in (key, key[4:], "CANARY", chr(0x200D)):
                self.assertNotIn(hidden, message)
            for phrase in ("보내지 않았습니다", "폐기", "새로 발급"):
                self.assertIn(phrase, message)

    def test_numbers_split_by_characters_the_old_fold_did_not_know_are_found_too(self):
        """옛 `_fold` 는 방향 격리(U+2066 등)·결합 글자를 몰라 주민등록번호·카드번호 모양을 놓쳤다. 같은 검사용 사본을 쓰므로 이제 걸린다."""
        rrn = "900101" + chr(0x2066) + "-" + chr(0x034F) + "1234567"
        card = "4111" + chr(0x034F) + " 1111" + chr(0x2067) + " 1111 1111"
        self.assertEqual(safety.sensitive_kinds(rrn), ["주민등록번호 모양"])
        self.assertEqual(safety.sensitive_kinds(card), ["카드번호 모양"])
        self.assertEqual(safety.sensitive_kinds(fullwidth("900101-1234567")), ["주민등록번호 모양"])

    def test_a_number_glued_to_a_digit_by_a_character_that_is_removed_is_still_found(self):
        """검증자 S 의 SP-6: 번호 바로 앞뒤에 지워지는 글자와 숫자 하나를 붙이면 지운 사본에서는 숫자가 이어 붙어(`…1111` + `5`) 번호 모양이 깨졌다. 옛 접기는 그 글자를 경계로 남겨 잡았다.
        번호 점검은 지운 사본과 공백으로 바꾼 사본을 둘 다 본다."""
        card, rrn = "4111 1111 1111 1111", "900101-1234567"
        for code in GLUE_CHARS:
            glue = chr(code)
            for number, kind in ((card, "카드번호 모양"), (rrn, "주민등록번호 모양")):
                for text in (number + glue + "5", "5" + glue + number):
                    with self.subTest(glue=hex(code), kind=kind, text=text):
                        self.assertEqual(safety.sensitive_kinds(text), [kind])

    def test_glued_digits_do_not_turn_ordinary_numbers_into_numbers(self):
        for text in ("연도 2026 에 5 건", "전화 010-1234-5678 에 5", "5" + chr(0x200B) + "010-1234-5678", "ISBN 978-3-16-148410-0" + chr(0x0301) + "5", "표 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6" + chr(0x2066) + "7"):
            with self.subTest(text=text[:24]):
                self.assertEqual(safety.sensitive_kinds(text), [])

    def test_the_old_behaviours_for_numbers_are_unchanged(self):
        for text in ("010-1234-5678", "02-123-4567", "1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16", "ca-pub-1234567890123456", "photo-1507146426996-ef05306b995a"):
            self.assertEqual(safety.sensitive_kinds(text), [], text)


class IssueEditFlowTest(RunnerBase):
    def run_layout(self, after="둘째 문단 아래에 강조 문장을 넣어 주세요", before="", spy=None):
        spy = spy or Spy()
        return self.go(issue(page_body(edit=LAYOUT, before=before, after=after), assoc="OWNER"), llm=spy), spy

    def assertRefused(self, res, spy, key):
        self.assertEqual(res.status, "rejected", res.reasons)
        self.assertEqual(spy.calls, [], "쪼갠 키가 있는데 외부 AI 로 보냈다")
        for phrase in ("보내지 않았습니다", "공개", "폐기"):
            self.assertIn(phrase, res.comment)
        dump = repr(res)
        for hidden in (key, key[4:], "CANARY"):
            self.assertNotIn(hidden, dump)
        self.assertEqual(self.read("about.md"), ABOUT)

    def test_a_split_key_in_the_request_is_never_sent(self):
        for label, key in KEYS.items():
            for code in (0x200B, 0x2060, 0x034F):
                with self.subTest(label=label, code=hex(code)):
                    res, spy = self.run_layout(after="문단을 고쳐 주세요 " + split_often(key, code) + " 끝")
                    self.assertRefused(res, spy, key)
                    self.assertIn(label, res.comment)

    def test_a_fullwidth_key_in_the_request_is_never_sent(self):
        res, spy = self.run_layout(after="문단을 고쳐 주세요 " + fullwidth(GITHUB_TOKEN))
        self.assertRefused(res, spy, GITHUB_TOKEN)

    def test_a_split_key_in_the_before_text_is_never_sent(self):
        res, spy = self.run_layout(before="이 값 " + split_once(GOOGLE_KEY, 0x200B) + " 을", after="지워 주세요")
        self.assertRefused(res, spy, GOOGLE_KEY)
        self.assertIn("변경 전", res.comment)

    def test_a_split_key_already_in_the_page_text_is_not_sent_either(self):
        write(self.root, "about.md", ABOUT + "\n실수로 들어간 값 " + split_often(GITHUB_TOKEN, 0x200B) + "\n")
        spy = Spy()
        res = self.go(issue(page_body(edit=LAYOUT, after="둘째 문단을 고쳐 주세요"), assoc="OWNER"), llm=spy)
        self.assertEqual(res.status, "rejected")
        self.assertEqual(spy.calls, [])
        self.assertIn("페이지 원문", res.comment)
        self.assertNotIn("CANARY", repr(res))

    def test_text_change_without_a_before_text_goes_through_the_same_check(self):
        spy = Spy()
        res = self.go(issue(page_body(edit="text_change | 문구 수정", after="문구를 고쳐 주세요 " + split_once(SK_KEY, 0x200C)), assoc="OWNER"), llm=spy)
        self.assertEqual(res.status, "rejected")
        self.assertEqual(spy.calls, [])

    def test_a_request_with_a_short_korean_client_secret_example_goes_through(self):
        """검증자 Q 의 QP-1: 3자에서 7자 사이의 한글 값을 쓴 `client_secret` 예시가 '키·토큰이 노출됐으니 폐기하라' 는 오경보로 거절되던 것."""
        for example in NoFalsePositiveTest.KOREAN_CLIENT_SECRET_EXAMPLES:
            with self.subTest(example=example):
                res, spy = self.run_layout(after="둘째 문단 아래에 설정 예시 " + example + " 를 넣어 주세요")
                self.assertEqual(res.status, "ok", res.reasons)
                self.assertEqual(len(spy.calls), 1)

    def test_ordinary_requests_with_invisible_characters_still_go_through(self):
        res, spy = self.run_layout(after="둘째 문단 아래에" + chr(0x200B) + " 강조 문장을 넣어 주세요 ＡＢＣ")
        self.assertEqual(res.status, "ok", res.reasons)
        self.assertEqual(len(spy.calls), 1)


class ImagePathTest(RunnerBase):
    URL = test_edits_runner.ImageEditTest.URL

    def run_image(self, target, prompt, picker, llm=None):
        return self.go(issue(image_body(target, prompt), labels=("blog-control", "edit:image"), title="[이미지 변경] x"), image_picker=picker, llm=llm)

    def test_a_split_key_in_the_image_description_reaches_neither_the_ai_nor_the_image_search(self):
        for label, key in KEYS.items():
            with self.subTest(label=label):
                picker, llm = Spy(), Spy({"image_queries": ["a", "b", "c"]})
                res = self.run_image(self.URL, "소방관 " + split_often(key, 0x200B), picker, llm)
                self.assertEqual(res.status, "rejected")
                self.assertEqual((picker.calls, llm.calls), ([], []))
                self.assertNotIn("CANARY", repr(res))
                self.assertIn("원하는 이미지 설명", res.comment)

    def test_a_split_key_in_the_tags_that_go_into_the_prompt_is_checked(self):
        write(self.root, "_posts/2026-10-21-KR-800001.md",
              post_text("키가 든 태그 글", img("801")).replace("tags: ['a', 'b']", "tags: ['" + fullwidth(GOOGLE_KEY) + "']"))
        picker = Spy()
        res = self.run_image("키가 든 태그 글", "소방관", picker)
        self.assertEqual(res.status, "rejected")
        self.assertEqual(picker.calls, [])
        self.assertIn("태그", res.comment)
        self.assertNotIn("CANARY", repr(res))


class NewSecretInAiChangeTest(unittest.TestCase):
    LIMITS = {"max_changed_files": 1, "max_changed_lines": 80, "max_file_chars": 80000}

    def verify(self, before, after, **kw):
        return checks.verify_changes({"about.md": (before, after)}, ["about.md"], self.LIMITS, **kw)

    def test_a_split_key_that_a_change_adds_is_rejected(self):
        before = "본문 문장입니다.\n"
        for key in KEYS.values():
            reasons = self.verify(before, before + split_often(key, 0x200B) + "\n", ai_patch=True)
            self.assertTrue(any("비밀 값으로 보이는 문자열" in reason for reason in reasons), reasons)
            self.assertFalse(any("CANARY" in reason for reason in reasons), reasons)

    def test_a_split_key_that_was_already_there_is_not_blamed_on_the_change(self):
        before = "본문 문장입니다.\n" + split_often(GITHUB_TOKEN, 0x200B) + "\n"
        after = before.replace("본문 문장입니다.", "본문 문장입니다. 고쳤습니다.")
        self.assertEqual(self.verify(before, after, ai_patch=True), [])


class RepositoryScanTest(unittest.TestCase):
    """저장소 검증기 SEC-2: 커밋한 파일의 쪼갠 키도 같은 라벨로 걸린다(값은 출력하지 않는다)."""

    def scan(self, text, name="note.md"):
        with tempfile.TemporaryDirectory() as tmp:
            write(Path(tmp), name, text)
            return vr.check_secret_patterns(tmp, [name])

    def test_split_and_fullwidth_keys_in_a_committed_file_are_errors_without_the_value(self):
        for text in (split_often(GITHUB_TOKEN, 0x200B), fullwidth(GOOGLE_KEY), split_once(SK_KEY, 0x034F)):
            found = self.scan("토큰: " + text + "\n")
            self.assertEqual([(f.check, f.level) for f in found], [("SEC-2", "ERROR")])
            self.assertEqual(found[0].path, "note.md:1")
            for hidden in (text, "CANARY", chr(0x200B)):
                self.assertNotIn(hidden, found[0].message)

    def test_the_allow_marker_still_skips_the_line(self):
        self.assertEqual(self.scan(split_once(GITHUB_TOKEN, 0x200B) + "  # validate-repo: allow\n"), [])

    def test_short_korean_client_secret_examples_in_a_committed_file_are_not_errors(self):
        """한글 문서에 OAuth 설정 모양 예시를 짧은 한글 자리표시자로 적어도 SEC-2 가 병합을 막지 않는다(검증자 Q 의 QP-1)."""
        for example in NoFalsePositiveTest.KOREAN_CLIENT_SECRET_EXAMPLES:
            with self.subTest(example=example):
                self.assertEqual(self.scan("설정 파일 예시:\n    " + example + "\n"), [])

    def test_unsplit_keys_are_reported_exactly_once_per_label_as_before(self):
        found = self.scan(GITHUB_TOKEN + "\n")
        self.assertEqual([(f.check, f.level) for f in found], [("SEC-2", "ERROR")])

    def test_ordinary_text_is_not_flagged(self):
        text = "\n".join(NoFalsePositiveTest.ORDINARY)
        self.assertEqual(self.scan(text), [])


if __name__ == "__main__":
    unittest.main()
