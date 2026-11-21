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
from edits_helpers import ABOUT, issue, page_body, write
from pipeline.edits import checks, safety
from pipeline.secret_patterns import find_secrets, scan_copy
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
}


def fullwidth(text):
    """ASCII 글자·숫자·기호를 전각으로(웹·문서에서 복사한 값 흉내). 소스에 전각 글자를 직접 쓰지 않는다."""
    return "".join(chr(ord(ch) - 0x21 + 0xFF01) if "!" <= ch <= "~" else ch for ch in text)


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
            self.assertFalse(any(unicodedata.category(ch) in ("Cf", "Mn", "Me", "Cs") for ch in once), repr(sample))

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
    )

    def test_ordinary_text_in_many_scripts_is_not_flagged(self):
        for text in self.ORDINARY:
            with self.subTest(text=text[:20]):
                self.assertEqual(find_secrets(text), [])
                self.assertEqual(safety.sensitive_kinds(text), [])

    def test_none_is_fine(self):
        self.assertEqual(find_secrets(None), [])
        self.assertEqual(safety.sensitive_kinds(None), [])

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

    def test_ordinary_requests_with_invisible_characters_still_go_through(self):
        res, spy = self.run_layout(after="둘째 문단 아래에" + chr(0x200B) + " 강조 문장을 넣어 주세요 ＡＢＣ")
        self.assertEqual(res.status, "ok", res.reasons)
        self.assertEqual(len(spy.calls), 1)


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

    def test_unsplit_keys_are_reported_exactly_once_per_label_as_before(self):
        found = self.scan(GITHUB_TOKEN + "\n")
        self.assertEqual([(f.check, f.level) for f in found], [("SEC-2", "ERROR")])

    def test_ordinary_text_is_not_flagged(self):
        text = "\n".join(NoFalsePositiveTest.ORDINARY)
        self.assertEqual(self.scan(text), [])


if __name__ == "__main__":
    unittest.main()
