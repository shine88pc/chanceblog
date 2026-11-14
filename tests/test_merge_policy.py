"""조건부 승인형 AI 병합 정책(운영자 확인 016 답, 2026-11-15)의 순수 함수 시험 — `pipeline/merge_policy.py`.

이 시험은 모듈 상수를 믿지 않는다: 운영자 원문의 목록(운영자 전용 12항목·재확인 8조건·불허 문구 5개·병합 가능 7종·설명 6항목·완료 알림 7항목·시험 기준 6가지)을 아래에 글자 그대로 따로 적어 두고 모듈과 대조한다 —
상수에서 항목 하나를 지우는 변경도 빨개지게 한다. 시험의 가짜 비밀은 런타임에 조립한 문자열이고 `CANARY` 로 시작하는 본문을 쓴다(소스에 비밀 모양이 이어 붙어 있지 않다).
이 시험은 네트워크·파일 쓰기를 하지 않는다(모듈이 순수 함수라서 가짜가 필요 없다).
"""
import copy
import unicodedata
import unittest

import _bootstrap
from pipeline import merge_policy as mp
from pipeline import notify

ROOT = _bootstrap.ROOT

# ---- 운영자 결정 원문의 목록(글자 그대로) -------------------------------------------------------------------------------------------------------------------
OPERATOR_ONLY_12 = ("GitHub Actions Workflow", "광고·AdSense·ads.txt", "공개 게시물과 고정 페이지", "PIPELINE_PAUSE", "발행 모드와 발행 재개", "Provider 활성화",
                    "API Key·Secret·Credential", "의존성 추가", "데이터 삭제·Migration", "자동 게시 활성화", "외부 비용 발생 기능", "Main Branch 보호 설정")
PRECONDITIONS_8 = ("승인된 병합 번호와 PR 일치", "승인 이후 Commit 추가 없음", "검사 전체 통과", "독립 검증 통과", "충돌 없음", "변경 범위가 승인 설명과 일치", "비밀정보 노출 없음", "원복 방법 확인")
REJECTED_5 = ("확인했습니다", "진행하세요", "좋아 보입니다", "기본값대로", "다음 단계 진행")
SCOPES_7 = ("일반 프로그램 코드", "일반 UI", "시험", "문서", "로컬 저장·조회", "오류 수정", "접근성·성능 개선")
EXPLANATION_6 = ("무엇을 바꾸나요?", "왜 필요한가요?", "사용할 때 무엇이 달라지나요?", "위험은 무엇인가요?", "검사 결과", "되돌리기")
COMPLETION_7 = ("병합 번호", "PR 번호", "병합된 Commit", "실제 반영된 변화", "main 검사 결과", "이상 유무", "원복 Commit 또는 원복 방법")
TRIAL_6 = ("승인받은 PR만 병합", "승인 후 변경 없음", "main 검사 전체 통과", "원복 발생 0건", "다른 PR 오병합 0건", "운영자 전용 경로 변경 0건")
FACT_KEYS_16 = ("approved_number", "approved_pr_number", "pr_number", "pr_title_label", "consumed_numbers", "approved_head_sha", "current_head_sha", "current_tree",
                "approved_paths", "current_paths", "checks", "independent_verification", "has_conflict", "classification", "secret_findings", "rollback_method")
VERIFICATION_KEYS_5 = ("verdict", "verifier", "implementer", "verified_tree", "open_required_findings")

# 가짜 비밀 — 소스에는 이어 붙은 비밀 모양이 없고 런타임에 조립한다
FAKE_SECRETS = {
    "google": "AI" + "za" + "CANARY_" + "A" * 28,
    "google_new": "A" + "Q." + "CANARY_" + "B" * 40,
    "oauth": "GOC" + "SPX-" + "CANARY_" + "C" * 20,
    "refresh": "1/" + "/0" + "CANARY_" + "D" * 40,
    "access": "ya" + "29." + "CANARY_" + "E" * 30,
    "github": "gh" + "p_" + "CANARY" + "F" * 30,
    "pat": "github" + "_pat_" + "CANARY_" + "G" * 40,
    "private_key": "-----BEGIN " + "PRIVATE KEY" + "-----",
    "private_key_rsa": "-----BEGIN " + "RSA PRIVATE KEY" + "-----",
    "slack": "xo" + "xb-" + "CANARY" + "-" + "H" * 12,
    "aws": "AK" + "IA" + "CANARY" + "I" * 10,
    "telegram": "123456789" + ":" + "CANARY_" + "J" * 30,
    "sk": "s" + "k-" + "CANARY" + "K" * 30,
}

SHA_A, SHA_B = "1" * 40, "2" * 40
TREE_A, TREE_B = "3" * 40, "4" * 40
GOOD_PATHS = ("pipeline/topics.py", "tests/test_topics.py")
DECLARED_OK = {code: False for code in mp.DECLARED_REQUIRED}
GOOD_TEXT = "def add(a, b):\n    return a + b\n"


def classify(kind, paths, text="", declared=None):
    return mp.classify_change(kind, list(paths), text, dict(DECLARED_OK) if declared is None else declared)


def good_facts():
    paths = list(GOOD_PATHS)
    return {
        "approved_number": "M075", "approved_pr_number": 198, "pr_number": 198, "pr_title_label": "M075", "consumed_numbers": [],
        "approved_head_sha": SHA_A, "current_head_sha": SHA_A, "current_tree": TREE_A,
        "approved_paths": list(paths), "current_paths": list(paths),
        "checks": [{"name": "저장소 규칙 검사", "conclusion": "success"}, {"name": "사이트 배포 미리 검사", "conclusion": "success"}],
        "independent_verification": {"verdict": "pass", "verifier": "검증자 갑", "implementer": "구현자 을", "verified_tree": TREE_A, "open_required_findings": 0},
        "has_conflict": False,
        "classification": classify("blog", paths, GOOD_TEXT).to_dict(),
        "secret_findings": 0,
        "rollback_method": "문제가 생기면 M075 병합 커밋 하나만 되돌리면 이전 상태로 돌아갑니다.",
    }


ANSWERS = ("앱을 닫아도 작성 중인 초안을 다시 열 수 있도록 저장 기능을 추가합니다.", "현재는 앱을 닫으면 초안이 사라집니다.", "저장 버튼과 저장된 초안 목록이 추가됩니다.",
           "저장 실패나 손상 가능성을 막기 위해 원자적 저장과 복구 시험을 수행했습니다.", "전체 검사와 독립 검증을 통과했고 기존 복사 기능에는 변화가 없습니다.",
           "문제가 발생하면 M075 병합만 되돌리면 이전 상태로 복구됩니다.")


def make_text(number="M075", enabled=False, checklist=None, paths=("pipeline/drafts.py", "tests/test_drafts.py")):
    return mp.render_explanation(number, 198, "c" * 40, list(paths), *ANSWERS, ai_merge_enabled=enabled, checklist=checklist)


def make_notice():
    return mp.render_completion_notice("M075", 198, "d" * 40, "초안 저장 기능이 사이트에 반영되었습니다.", "전체 통과", "이상 없음", "해당 병합 커밋 한 개를 되돌립니다.")


def drop_line(text, start):
    """start 로 시작하는 줄을 지운다(없으면 시험이 틀린 것이다)."""
    lines = text.split("\n")
    kept = [line for line in lines if not line.startswith(start)]
    assert len(kept) == len(lines) - 1, start
    return "\n".join(kept)


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


class ConstantsPinTest(unittest.TestCase):
    """운영자 원문의 목록이 줄거나 늘지 않았다 — 모듈 상수와 이 파일의 글자 그대로의 목록이 같다."""

    def test_the_operator_lists_are_exactly_the_original_words(self):
        self.assertEqual(mp.OPERATOR_ONLY_LABELS, OPERATOR_ONLY_12)
        self.assertEqual(tuple(label for _code, label in mp.PRECONDITIONS), PRECONDITIONS_8)
        self.assertEqual(mp.REJECTED_PHRASES, REJECTED_5)
        self.assertEqual(mp.AI_MERGE_SCOPES, SCOPES_7)
        self.assertEqual(mp.EXPLANATION_ITEMS, EXPLANATION_6)
        self.assertEqual(mp.COMPLETION_ITEMS, COMPLETION_7)
        self.assertEqual(tuple(label for _key, label in mp.TRIAL_CRITERIA), TRIAL_6)

    def test_the_counts_are_twelve_eight_five_seven_six_seven_six(self):
        self.assertEqual([len(mp.OPERATOR_ONLY_ITEMS), len(mp.PRECONDITIONS), len(mp.REJECTED_PHRASES), len(mp.AI_MERGE_SCOPES), len(mp.EXPLANATION_ITEMS),
                          len(mp.COMPLETION_ITEMS), len(mp.TRIAL_CRITERIA)], [12, 8, 5, 7, 6, 7, 6])
        self.assertEqual(mp.TRIAL_SIZE, 3)

    def test_codes_are_unique_and_the_declared_six_are_among_the_twelve(self):
        for codes in (mp.OPERATOR_ONLY_CODES, tuple(code for code, _ in mp.PRECONDITIONS), tuple(key for key, _ in mp.TRIAL_CRITERIA), mp.EXTRA_CODES):
            self.assertEqual(len(set(codes)), len(codes))
        self.assertEqual(len(mp.DECLARED_REQUIRED), 6)
        self.assertLessEqual(set(mp.DECLARED_REQUIRED), set(mp.OPERATOR_ONLY_CODES))
        self.assertEqual(set(mp.EXTRA_CODES) & set(mp.OPERATOR_ONLY_CODES), set())
        self.assertEqual(mp.EXTRA_CODES, ("policy_self", "packaging_release", "invalid_input"))

    def test_the_fact_keys_and_verification_keys_are_pinned(self):
        self.assertEqual(mp.FACT_KEYS, FACT_KEYS_16)
        self.assertEqual(mp.VERIFICATION_KEYS, VERIFICATION_KEYS_5)
        self.assertEqual(set(good_facts()), set(FACT_KEYS_16))

    def test_the_merge_method_constants(self):
        self.assertEqual(mp.ALLOWED_MERGE_METHOD, "pr_merge")
        self.assertEqual(mp.FORBIDDEN_MERGE_METHODS, ("push_main", "direct_push", "force_push"))

    def test_the_merge_number_rule_is_the_notify_standard_with_the_m_prefix(self):
        """새로 만들지 않고 같은 값 — 숫자 부분이 pipeline.notify.NOTICE_NO_RE 와 글자 그대로 같고, 행동도 모든 숫자·표기에서 같다."""
        self.assertEqual(notify.NOTICE_NO_RE.pattern, "[PM]?" + mp.MERGE_NUMBER_DIGITS)
        different, accepted = [], 0
        for number in range(0, 10006):
            for text in ("M%03d" % number, "M%04d" % number, "M%d" % number, "m%03d" % number, "P%03d" % number, "%03d" % number, "M%05d" % number):
                mine = mp.MERGE_NUMBER_RE.fullmatch(text) is not None
                accepted += mine
                if mine != (notify.notice_type(text) == "merge"):
                    different.append(text)
        self.assertEqual(different, [])
        self.assertEqual(accepted, 9999 + 9000 + 9900)           # 세 자리 0 채움(M001–M999)·네 자리(M1000–M9999)·0 을 채우지 않은 쓰기 — 앞에 0 을 더 붙인 네 자리와 다섯 자리는 번호가 아니다
        self.assertIsNotNone(mp.MERGE_NUMBER_RE.fullmatch("M001"))
        self.assertIsNotNone(mp.MERGE_NUMBER_RE.fullmatch("M999"))
        self.assertIsNotNone(mp.MERGE_NUMBER_RE.fullmatch("M1000"))
        self.assertIsNotNone(mp.MERGE_NUMBER_RE.fullmatch("M9999"))
        for text in ("M000", "M0075", "M10000", "m075", "M75", "M07", "P075", "075", "M075\n", " M075", "M０７５"):
            self.assertIsNone(mp.MERGE_NUMBER_RE.fullmatch(text), text)

    def test_the_public_functions_exist(self):
        for name in ("parse_approval", "check_approval_text", "approval_matches", "approval_still_valid", "pr_title_label", "classify_change", "check_preconditions",
                     "merge_method_allowed", "explanation_problems", "render_explanation", "completion_notice_problems", "render_completion_notice", "evaluate_trial", "trial_report"):
            self.assertTrue(callable(getattr(mp, name)), name)
        self.assertTrue(callable(mp.ApprovalLedger))


class ApprovalParseTest(unittest.TestCase):
    VALID = (("M075 승인", "M075"), ("M075 승인.", "M075"), ("  M075 승인  ", "M075"), ("\tM075 승인\r\n", "M075"), ("m075 승인", "M075"), ("M075   승인", "M075"),
             ("M075\t승인", "M075"), ("M1000 승인", "M1000"), ("M999 승인", "M999"), ("M001 승인", "M001"), ("M9999 승인.", "M9999"), (" m1234 승인. \n", "M1234"))

    def test_the_exact_form_is_an_approval_and_the_number_is_returned_in_capitals(self):
        for text, number in self.VALID:
            with self.subTest(text=text):
                self.assertEqual(mp.parse_approval(text), number)
                result = mp.check_approval_text(text)
                self.assertEqual((result.number, result.reason, result.guidance), (number, "ok", ""))

    def test_each_rejected_phrase_alone_is_not_an_approval(self):
        for phrase in REJECTED_5:
            for text in (phrase, phrase + ".", "  " + phrase + "  ", "네, " + phrase, phrase + " 감사합니다"):
                with self.subTest(text=text):
                    self.assertIsNone(mp.parse_approval(text))
                    self.assertEqual(mp.check_approval_text(text).reason, "rejected_phrase")

    def test_a_phrase_next_to_a_number_is_not_an_approval_either(self):
        for text in ("M075 확인했습니다", "확인했습니다 M075 승인", "M075 승인 확인했습니다", "진행하세요 M075", "M075 기본값대로", "좋아 보입니다 M075 승인"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))

    def test_an_approval_word_without_a_number_is_not_an_approval(self):
        for text in ("승인", "승인합니다", "승인.", "M 승인", "M승인", "네 승인", "승인 부탁드립니다"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))
                self.assertEqual(mp.check_approval_text(text).reason, "no_number")

    def test_two_or_more_numbers_are_ambiguous(self):
        for text in ("M075 M076 승인", "M075 승인 M076 승인", "M075 승인\nM076 승인", "M075, M076 승인", "M075 승인 (M074 다음)"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))
                self.assertEqual(mp.check_approval_text(text).reason, "several_numbers")

    def test_words_after_the_approval_make_it_not_an_approval(self):
        for text in ("M075 승인하되 이름은 바꿔 주세요", "M075 승인합니다", "M075 승인 합니다", "M075 승인 (보류)", "M075 승인 취소", "M075 승인 안 함", "M075 승인 감사합니다",
                     "M075 승인 아님", "M075 승인 부탁", "M075 승인 확인했습니다"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))
                self.assertEqual(mp.check_approval_text(text).reason, "not_exact_form")

    def test_a_number_inside_another_sentence_is_not_an_approval(self):
        for text in ("오늘 M075 승인", "안녕하세요 M075 승인", "M075 승인 이라고 쓰면 됩니다", "회의에서 M075 승인 얘기가 나왔습니다", "참고: M075 승인", "- M075 승인 -"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))

    def test_the_form_is_exact_number_first_then_one_word(self):
        for text in ("승인 M075", "M075승인", "M075, 승인", "M075: 승인", "M075 - 승인", "[M075] 승인", "(M075 승인)", "M075 승인!", "M075 승인..", "M075 승인 .", "M075 승인?"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))

    def test_quotes_and_formatting_characters_are_not_stripped(self):
        for text in ("'M075 승인'", '"M075 승인"', "`M075 승인`", "*M075 승인*", "> M075 승인", "M075 승인</p>"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))

    def test_the_number_must_be_the_standard_three_or_four_digits(self):
        for text in ("M75 승인", "M0075 승인", "M000 승인", "M00075 승인", "M12345 승인", "M7 승인", "M10000 승인", "M-75 승인", "M+75 승인", "M075.5 승인", "M 075 승인"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))
        for text in ("M75 승인", "M0075 승인", "M000 승인", "M12345 승인"):
            self.assertEqual(mp.check_approval_text(text).reason, "bad_number")

    def test_other_prefixes_and_forms_are_not_merge_numbers(self):
        for text in ("P075 승인", "075 승인", "R-075 승인", "#075 승인", "N075 승인", "MM075 승인", "M075a 승인", "xM075 승인"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))

    def test_look_alike_and_invisible_characters_are_not_accepted(self):
        zero_width, nbsp, ideographic = chr(0x200B), chr(0xA0), chr(0x3000)
        for text in (chr(0xFF2D) + "075 승인",                                                                                        # 전각 M
                     "M" + chr(0xFF10) + chr(0xFF17) + chr(0xFF15) + " 승인",                                                            # 전각 숫자
                     "M07" + zero_width + "5 승인", "M075" + zero_width + " 승인", "M075 승" + zero_width + "인",
                     "M075" + nbsp + "승인", nbsp + "M075 승인", "M075 승인" + nbsp, "M075" + ideographic + "승인", chr(0xFEFF) + "M075 승인",
                     "M075 " + unicodedata.normalize("NFD", "승인"), chr(0x202E) + "M075 승인"):
            with self.subTest(text=repr(text)):
                self.assertIsNone(mp.parse_approval(text))

    def test_a_newline_inside_is_not_an_approval(self):
        for text in ("M075\n승인", "M075 \n승인", "M075\r\n승인", "\n\nM075\n\n승인"):
            with self.subTest(text=repr(text)):
                self.assertIsNone(mp.parse_approval(text))

    def test_empty_and_non_text_input_is_not_an_approval(self):
        for value in ("", "   ", "\n", None, 75, 7.5, True, "M075 승인".encode(), ["M075 승인"], ("M075", "승인"), {"M075": "승인"}, object()):
            with self.subTest(value=repr(value)):
                self.assertIsNone(mp.parse_approval(value))
                self.assertEqual(mp.check_approval_text(value).reason, "empty")

    def test_a_very_long_text_is_not_an_approval(self):
        self.assertIsNone(mp.parse_approval("M075 승인" + " 가" * 3000))
        self.assertIsNone(mp.parse_approval(" " * 5000 + "승인"))
        self.assertEqual(mp.check_approval_text("M075 승인" + " 가" * 3000).reason, "not_exact_form")

    def test_every_refusal_carries_the_exact_form_again(self):
        for text in ("확인했습니다", "승인", "M075 M076 승인", "M75 승인", "M075 승인하되", "", "그냥 좋아요"):
            with self.subTest(text=text):
                result = mp.check_approval_text(text)
                self.assertIsNone(result.number)
                self.assertIn(result.reason, mp.APPROVAL_REASONS)
                self.assertNotEqual(result.reason, "ok")
                self.assertIn("M075 승인", result.guidance)
                self.assertIn("병합 번호", result.guidance)

    def test_the_reason_codes_are_the_documented_seven(self):
        self.assertEqual(mp.APPROVAL_REASONS, ("ok", "empty", "rejected_phrase", "no_number", "several_numbers", "bad_number", "not_exact_form"))

    def test_the_result_is_immutable(self):
        result = mp.check_approval_text("M075 승인")
        with self.assertRaises(Exception):
            result.number = "M076"


class ApprovalValidityTest(unittest.TestCase):
    def test_the_approved_number_must_equal_the_pr_number_exactly(self):
        self.assertTrue(mp.approval_matches("M075", "M075"))
        self.assertTrue(mp.approval_matches("M1000", "M1000"))
        for approved, label in (("M075", "M076"), ("M075", "M750"), ("M75", "M75"), ("M0075", "M0075"), ("m075", "M075"), ("M075", "m075"), ("M075", None), (None, "M075"), (None, None),
                                ("M075", "[M075]"), ("M075 ", "M075"), ("M075", "M075 "), ("M075", ""), ("", ""), (75, 75), ("M000", "M000"), ("P075", "P075")):
            with self.subTest(approved=approved, label=label):
                self.assertFalse(mp.approval_matches(approved, label))

    def test_the_pr_title_number_is_the_leading_single_tag(self):
        for title, label in (("[M075] 앱을 닫아도 초안 저장", "M075"), ("[M1000] x", "M1000"), ("[M075]", "M075"), ("[M075]x", "M075")):
            with self.subTest(title=title):
                self.assertEqual(mp.pr_title_label(title), label)
        for title in (" [M075] x", "제목 [M075]", "[M075] [M076] x", "[M075] 제목 (이전 [M074] 이후)", "[R-175] 제목", "[M75] x", "[m075] x", "[M0075] x", "[M000] x", "제목", "", None, 75, ["[M075]"]):
            with self.subTest(title=title):
                self.assertIsNone(mp.pr_title_label(title))

    def test_a_commit_added_after_the_approval_voids_it(self):
        paths = ["pipeline/a.py", "tests/test_a.py"]
        self.assertTrue(mp.approval_still_valid(SHA_A, SHA_A, paths, paths))
        self.assertFalse(mp.approval_still_valid(SHA_A, SHA_B, paths, paths))
        self.assertFalse(mp.approval_still_valid(SHA_B, SHA_A, paths, paths))
        self.assertTrue(mp.approval_still_valid(SHA_A.upper().replace("1", "A"), SHA_A.replace("1", "a"), paths, paths))     # 대소문자만 다른 같은 해시

    def test_a_changed_file_list_voids_the_approval(self):
        base = ["pipeline/a.py", "tests/test_a.py"]
        for current in (base + ["docs/x.md"], ["pipeline/a.py"], ["pipeline/a.py", "tests/test_b.py"], ["pipeline/b.py", "tests/test_a.py"], ["pipeline/a.py", "tests/test_a.py", "pipeline/a2.py"]):
            with self.subTest(current=current):
                self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, base, current))
                self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, current, base))

    def test_the_file_list_is_compared_as_a_set_of_normalized_paths(self):
        self.assertTrue(mp.approval_still_valid(SHA_A, SHA_A, ["a.py", "b.py"], ["b.py", "a.py"]))
        self.assertTrue(mp.approval_still_valid(SHA_A, SHA_A, ["a.py"], ["./a.py"]))
        self.assertTrue(mp.approval_still_valid(SHA_A, SHA_A, ["pipeline\\a.py"], ["pipeline/a.py"]))
        self.assertTrue(mp.approval_still_valid(SHA_A, SHA_A, ["a.py", "a.py"], ["a.py"]))
        self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, ["A.py"], ["a.py"]))                       # 이름은 대소문자를 구분해 비교한다

    def test_missing_or_malformed_values_void_the_approval(self):
        paths = ["a.py"]
        for sha in ("abc1234", "", None, 123, "g" * 40, "1" * 39, "1" * 41, [SHA_A], b"1" * 40):
            with self.subTest(sha=sha):
                self.assertFalse(mp.approval_still_valid(sha, sha, paths, paths))
                self.assertFalse(mp.approval_still_valid(SHA_A, sha, paths, paths))
                self.assertFalse(mp.approval_still_valid(sha, SHA_A, paths, paths))
        for bad in ([], None, "a.py", ["../x.py"], [None], [1], ["/abs.py"], 5, [""]):
            with self.subTest(paths=bad):
                self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, bad, bad))
                self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, paths, bad))
                self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, bad, paths))

    def test_normalize_path(self):
        self.assertEqual(mp.normalize_repo_path("a/b.py"), "a/b.py")
        self.assertEqual(mp.normalize_repo_path("./a//b.py"), "a/b.py")
        self.assertEqual(mp.normalize_repo_path(" a\\b.py \n"), "a/b.py")
        for bad in ("", " ", ".", "./", "..", "a/../b", "../a", "/a", "\\a", "C" + ":/a", "C" + ":\\a", "a\x00b", "a\x1bb", None, 5, b"a", ["a"]):
            with self.subTest(bad=repr(bad)):
                self.assertIsNone(mp.normalize_repo_path(bad))


class ApprovalLedgerTest(unittest.TestCase):
    def test_an_approval_is_used_once(self):
        ledger = mp.ApprovalLedger()
        first = ledger.consume("M075", 198)
        self.assertTrue(first.ok)
        self.assertEqual(first.reason, "")
        again = ledger.consume("M075", 198)
        self.assertFalse(again.ok)
        self.assertIn("한 번 쓴 승인", again.reason)
        self.assertEqual(ledger.consumed_numbers, ("M075",))

    def test_one_approval_cannot_be_reused_for_another_pr(self):
        ledger = mp.ApprovalLedger()
        self.assertTrue(ledger.consume("M075", 198).ok)
        other = ledger.consume("M075", 199)
        self.assertFalse(other.ok)
        self.assertIn("다른 PR", other.reason)

    def test_one_pr_cannot_be_merged_under_a_second_approval(self):
        ledger = mp.ApprovalLedger()
        self.assertTrue(ledger.consume("M075", 198).ok)
        second = ledger.consume("M076", 198)
        self.assertFalse(second.ok)
        self.assertIn("이미 다른 승인", second.reason)
        self.assertEqual(ledger.consumed_numbers, ("M075",))                                  # 거절은 기록을 바꾸지 않는다
        self.assertTrue(ledger.consume("M076", 200).ok)                                         # 새 번호·새 PR 은 된다

    def test_malformed_input_is_refused_without_a_record(self):
        ledger = mp.ApprovalLedger()
        for number, pr_number in (("M75", 1), ("m075", 1), (None, 1), ("M075", 0), ("M075", -3), ("M075", True), ("M075", "198"), ("M075", None), ("M075", 1.0), (75, 75)):
            with self.subTest(number=number, pr_number=pr_number):
                self.assertFalse(ledger.consume(number, pr_number).ok)
        self.assertEqual(ledger.consumed_numbers, ())

    def test_the_ledger_can_start_from_the_merged_history(self):
        ledger = mp.ApprovalLedger([("M070", 190), ("M071", 191)])
        self.assertEqual(ledger.consumed_numbers, ("M070", "M071"))
        self.assertFalse(ledger.consume("M070", 300).ok)
        self.assertFalse(ledger.consume("M072", 191).ok)
        self.assertTrue(ledger.consume("M072", 192).ok)

    def test_a_malformed_history_is_an_error_not_a_silent_start(self):
        for bad in ([("M75", 1)], [("M070", 0)], [("M070",)], [5], 5, [("M070", 190, 1)]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    mp.ApprovalLedger(bad)

    def test_two_ledgers_do_not_share_state(self):
        first, second = mp.ApprovalLedger(), mp.ApprovalLedger()
        self.assertTrue(first.consume("M075", 198).ok)
        self.assertTrue(second.consume("M075", 198).ok)


class ClassifyAllowedTest(unittest.TestCase):
    """AI 병합 가능 7종의 대표 입력은 운영자 전용 12항목에 걸리지 않아 ai_ok 다."""

    CASES = (
        ("일반 프로그램 코드", "blog", ["pipeline/topics.py", "generator.py"], "def pick(items):\n    return items[0]\n"),
        ("일반 UI", "desktop", ["src/chanceblog_desktop/ui/pages/home.py"], "self.title.setText('홈')\n"),
        ("시험", "blog", ["tests/test_topics.py"], "self.assertEqual(1, 1)\n"),
        ("문서", "blog", ["docs/GLOSSARY.md"], "용어 설명을 한 줄 더합니다.\n"),
        ("로컬 저장·조회", "desktop", ["src/chanceblog_desktop/content/store.py"], "path.write_text(data, encoding='utf-8')\n"),
        ("오류 수정", "blog", ["pipeline/run.py"], "if value is None:\n    return 0\n"),
        ("접근성·성능 개선", "desktop", ["src/chanceblog_desktop/ui/core/focus.py"], "widget.setAccessibleName('저장')\n@cache\n"),
    )

    def test_the_seven_scopes_are_ai_ok(self):
        self.assertEqual(tuple(case[0] for case in self.CASES), SCOPES_7)
        for scope, kind, paths, text in self.CASES:
            with self.subTest(scope=scope):
                result = classify(kind, paths, text)
                self.assertEqual((result.tier, result.categories, result.extra_flags, result.reasons), ("ai_ok", (), (), ()))
                self.assertFalse(result.operator_only)

    def test_ai_ok_needs_no_answer_for_the_six_machine_checked_items(self):
        result = mp.classify_change("blog", ["pipeline/topics.py"], GOOD_TEXT, dict(DECLARED_OK))
        self.assertEqual(result.tier, "ai_ok")
        result = mp.classify_change("blog", ["pipeline/topics.py"], GOOD_TEXT, dict(DECLARED_OK, **{code: False for code in mp.OPERATOR_ONLY_CODES}))
        self.assertEqual(result.tier, "ai_ok")

    def test_common_words_that_only_look_like_the_watched_ones_stay_ai_ok(self):
        for text in ("tokens = []\n", "max_tokens = 100\n", "tokenizer.encode(text)\n", "detokenize(x)\n", "sort_key = lambda r: r.key\n", "for key in table:\n", "keyboard.press()\n",
                     "docs/about.md 를 읽습니다\n", "Ads 대시보드는 읽기 전용입니다\n"):
            with self.subTest(text=text):
                self.assertEqual(classify("blog", ["pipeline/topics.py"], text).tier, "ai_ok")

    def test_paths_that_only_look_like_the_watched_ones_stay_ai_ok(self):
        for kind, path in (("blog", "docs/about.md"), ("blog", "tests/fixtures/page.html"), ("blog", "docs/assets/x.png"), ("blog", "pipeline/tokenizer.py"), ("blog", "docs/SECURITY_GUARDRAILS.md"),
                           ("blog", "인수인계/작업내용.md"), ("blog", "VERSION"), ("blog", "README.md"), ("desktop", "index.html"), ("desktop", "_posts/x.md"), ("desktop", "src/x/version.py"),
                           ("desktop", "docs/RELEASE.md"), ("blog", "pipeline/blogs.py"), ("blog", "tests/fixtures/_config.json")):
            with self.subTest(path=path):
                self.assertEqual(classify(kind, [path]).tier, "ai_ok", path)

    def test_the_result_is_deterministic_and_order_free(self):
        paths = ["pipeline/b.py", "pipeline/a.py", "tests/test_a.py"]
        first = classify("blog", paths, GOOD_TEXT)
        self.assertEqual(first, classify("blog", list(reversed(paths)), GOOD_TEXT))
        self.assertEqual(first.paths, ("pipeline/a.py", "pipeline/b.py", "tests/test_a.py"))
        self.assertEqual(first["tier"], "ai_ok")
        self.assertEqual(first.to_dict()["paths"], list(first.paths))
        with self.assertRaises(Exception):
            first.tier = "operator_only"


class ClassifyOperatorOnlyTest(unittest.TestCase):
    """운영자 전용 12항목 각각이 걸리는 대표 입력 — 경로·내용·선언 참·선언 미응답."""

    def assert_flags(self, result, code):
        self.assertEqual(result.tier, "operator_only")
        self.assertIn(code, result.categories)
        self.assertTrue(result.reasons)

    def test_workflow_any_line_under_dot_github(self):
        for path in (".github/workflows/ci.yml", ".github/CODEOWNERS", ".github/ISSUE_TEMPLATE/x.yml", "sub/.github/x.yml", ".GitHub/Workflows/X.yml", "./.github/workflows/ci.yml",
                     ".github\\workflows\\ci.yml", ".github/a.md"):
            with self.subTest(path=path):
                self.assert_flags(classify("blog", [path]), "workflow")
                self.assert_flags(classify("desktop", [path]), "workflow")

    def test_a_single_workflow_line_among_many_files_still_flags(self):
        paths = ["pipeline/a.py", "tests/test_a.py", "docs/a.md", ".github/workflows/ci.yml"]
        result = classify("blog", paths, GOOD_TEXT)
        self.assertEqual(result.categories, ("workflow",))
        self.assertTrue(any(".github/workflows/ci.yml" in reason for reason in result.reasons))

    def test_ads_by_path(self):
        for path in ("index.html", "ads.txt", "app-ads.txt", "_config.yml", "_layouts/default.html", "_includes/ad.html", "sub/index.html", "INDEX.HTML", "sub/ads.txt", "x/_layouts/a.html"):
            with self.subTest(path=path):
                self.assert_flags(classify("blog", [path]), "ads")

    def test_ads_by_added_text(self):
        for text in ('<ins class="adsbygoogle"></ins>\n', "AdsByGoogle", 'data-ad-client="ca-pub-"', "CA-PUB-", "x = 'adsbygoogle'"):
            with self.subTest(text=text):
                self.assert_flags(classify("blog", ["pipeline/x.py"], text), "ads")
                self.assert_flags(classify("desktop", ["src/x.py"], text), "ads")

    def test_public_content_by_path(self):
        for path in ("_posts/2026-11-15-a.md", "sub/_posts/b.md", "about.md", "contact.md", "privacy.md", "categories.md", "pages.json", "posts.json", "feed.xml", "robots.txt", "assets/x.png",
                     "assets/css/a.css", "404.html", "googleabc.html", "_blogger_drafts/a.md", "_blogger_ko_drafts/a.md", "_naver_drafts/a.md", "history.json", "blogger_history.json",
                     "naver_history.json", "ABOUT.MD"):
            with self.subTest(path=path):
                self.assert_flags(classify("blog", [path]), "public_content")

    def test_publish_settings_files_map_to_their_items(self):
        expected = {"pipeline/blogs.json": {"publish_mode", "auto_publish", "ads"}, "pipeline/source_registry.json": {"provider_activation"},
                    "pipeline/ops_inbox_policy.json": {"pipeline_pause", "publish_mode"}}
        for path, codes in expected.items():
            with self.subTest(path=path):
                result = classify("blog", [path])
                self.assertEqual(result.tier, "operator_only")
                self.assertEqual(set(result.categories), codes)

    def test_pipeline_pause_by_text_and_declaration(self):
        self.assert_flags(classify("blog", ["pipeline/x.py"], "if PIPELINE_PAUSE:\n    return\n"), "pipeline_pause")
        self.assert_flags(classify("blog", ["pipeline/x.py"], "pipeline_pause = 1"), "pipeline_pause")
        self.assert_flags(classify("desktop", ["src/x.py"], "PIPELINE_PAUSE"), "pipeline_pause")

    def test_dependencies_by_path(self):
        for path in ("requirements.txt", "requirements-dev.txt", "sub/requirements-edits.txt", "constraints.txt", "vendor/pipeline/x.py", "src/vendor/a.py", "package.json", "package-lock.json",
                     "pyproject.toml", "Pipfile", "Pipfile.lock", "poetry.lock", "yarn.lock", "uv.lock", "setup.py", "setup.cfg", "Gemfile", "Gemfile.lock", "node_modules/x.js", "REQUIREMENTS.TXT"):
            with self.subTest(path=path):
                self.assert_flags(classify("blog", [path]), "dependencies")
                self.assert_flags(classify("desktop", [path]), "dependencies")

    def test_credentials_by_path(self):
        for path in (".env", ".env.example", ".env.local", "sub/.env", "certs/server.pem", "a/id.key", "x.p12", "x.pfx", "x.jks", "x.keystore", "client_secret_1.json", "token.json", "token-gmail.json",
                     "service-account.json", "my_service_account_key.json", "my_credentials.txt", "pipeline/secret_patterns.py", "tests/test_secret_invisible.py", "src/security/keystore.py",
                     "src/x/security/mask.py", "keyring/a.py", "id_rsa", "id_ed25519.pub", ".npmrc", ".pypirc", ".netrc"):
            with self.subTest(path=path):
                self.assert_flags(classify("blog", [path]), "credentials")
                self.assert_flags(classify("desktop", [path]), "credentials")

    def test_credentials_by_secret_shaped_values_never_echo_the_value(self):
        for name, value in FAKE_SECRETS.items():
            with self.subTest(name=name):
                result = classify("blog", ["pipeline/x.py"], "note " + value + " end\n")
                self.assert_flags(result, "credentials")
                joined = " ".join(result.reasons)
                self.assertIn("비밀 모양의 값이 있습니다", joined)
                self.assertNotIn(value, joined)
                self.assertNotIn("CANARY", joined)
                self.assert_flags(classify("desktop", ["src/x.py"], "note " + value + " end\n"), "credentials")

    def test_credentials_by_a_long_quoted_assignment(self):
        value = "pass" + "word = '" + "CANARY_" + "L" * 20 + "'"
        result = classify("blog", ["pipeline/x.py"], value)
        self.assert_flags(result, "credentials")
        self.assertNotIn("CANARY", " ".join(result.reasons))

    def test_credentials_by_secrets_reference_and_names(self):
        for text in ("secrets.SOME_NAME", "uses secrets . FOO", "secrets['FOO']", "GEMINI_API_KEY = os", "api_key = 1", "API-KEY", "ApiKey", "apikey", "my secret", "Password", "passwd", "credentials", "private key",
                     "private_key", "access-key", "TELEGRAM_BOT_TOKEN", "token", "bot_token", "accessToken", "mytoken", "비밀번호", "시크릿", "API 키", "자격 증명", "봇 토큰", "인증 정보"):
            with self.subTest(text=text):
                self.assert_flags(classify("blog", ["pipeline/x.py"], text), "credentials")

    def test_data_deletion_or_migration_by_text(self):
        for text in ("DROP TABLE drafts;", "drop   database x", "delete from drafts where id = 1", "TRUNCATE TABLE x", "shutil.rmtree(path)", "rmtree(path)", "마이그레이션 계획", "def migrate():", "Migration", "migrated rows",
                     "migrating"):
            with self.subTest(text=text):
                self.assert_flags(classify("blog", ["pipeline/x.py"], text), "data_deletion_migration")

    def test_each_of_the_twelve_items_is_flagged_when_declared_true(self):
        for code, label in mp.OPERATOR_ONLY_ITEMS:
            with self.subTest(code=code):
                declared = dict(DECLARED_OK)
                declared[code] = True
                result = classify("blog", ["pipeline/topics.py"], GOOD_TEXT, declared)
                self.assert_flags(result, code)
                self.assertTrue(any(label in reason for reason in result.reasons))

    def test_each_of_the_six_declared_items_is_flagged_when_unanswered(self):
        for code in mp.DECLARED_REQUIRED:
            for how in ("missing", None, "아니오", "no", 0, 1, [], "", object()):
                with self.subTest(code=code, how=repr(how)):
                    declared = dict(DECLARED_OK)
                    if how == "missing":
                        del declared[code]
                    else:
                        declared[code] = how
                    self.assert_flags(classify("blog", ["pipeline/topics.py"], GOOD_TEXT, declared), code)

    def test_an_unanswered_declaration_is_operator_only_for_all_six(self):
        for declared in (None, {}):
            result = mp.classify_change("blog", ["pipeline/topics.py"], GOOD_TEXT, declared)
            self.assertEqual(result.tier, "operator_only")
            self.assertEqual(set(result.categories), set(mp.DECLARED_REQUIRED))
        self.assertEqual(mp.classify_change("blog", ["pipeline/topics.py"], GOOD_TEXT).tier, "operator_only")

    def test_the_other_six_items_are_flagged_when_declared_with_anything_but_false_or_none(self):
        others = [code for code in mp.OPERATOR_ONLY_CODES if code not in mp.DECLARED_REQUIRED]
        self.assertEqual(len(others), 6)
        for code in others:
            for value in (True, "예", 1, "no"):
                with self.subTest(code=code, value=value):
                    self.assert_flags(classify("blog", ["pipeline/topics.py"], GOOD_TEXT, dict(DECLARED_OK, **{code: value})), code)
            for value in (False, None):
                with self.subTest(code=code, value=value):
                    self.assertEqual(classify("blog", ["pipeline/topics.py"], GOOD_TEXT, dict(DECLARED_OK, **{code: value})).tier, "ai_ok")

    def test_a_false_declaration_never_overrides_a_path_or_content_rule(self):
        everything_false = {code: False for code in mp.OPERATOR_ONLY_CODES}
        for kind, path, text, code in (("blog", ".github/workflows/ci.yml", "", "workflow"), ("blog", "index.html", "", "ads"), ("blog", "_posts/a.md", "", "public_content"),
                                       ("blog", "pipeline/blogs.json", "", "publish_mode"), ("blog", "pipeline/source_registry.json", "", "provider_activation"),
                                       ("blog", "requirements.txt", "", "dependencies"), ("blog", ".env", "", "credentials"), ("blog", "pipeline/x.py", "PIPELINE_PAUSE", "pipeline_pause"),
                                       ("blog", "pipeline/x.py", "adsbygoogle", "ads"), ("blog", "pipeline/x.py", "DROP TABLE x", "data_deletion_migration")):
            with self.subTest(path=path, text=text):
                self.assert_flags(mp.classify_change(kind, [path], text, dict(everything_false)), code)

    def test_every_documented_rule_word_triggers_something(self):
        samples = {
            ".github/": ("blog", [".github/x.yml"], ""), "index.html": ("blog", ["index.html"], ""), "_layouts/": ("blog", ["_layouts/a.html"], ""), "_includes/": ("blog", ["_includes/a.html"], ""),
            "_config.yml": ("blog", ["_config.yml"], ""), "ads.txt": ("blog", ["ads.txt"], ""), "adsbygoogle": ("blog", ["a.py"], "adsbygoogle"), "ca-pub-": ("blog", ["a.py"], "ca-pub-"),
            "_posts/": ("blog", ["_posts/a.md"], ""), "about.md": ("blog", ["about.md"], ""), "contact.md": ("blog", ["contact.md"], ""), "privacy.md": ("blog", ["privacy.md"], ""),
            "categories.md": ("blog", ["categories.md"], ""), "pages.json": ("blog", ["pages.json"], ""), "assets/": ("blog", ["assets/a.png"], ""),
            "pipeline/blogs.json": ("blog", ["pipeline/blogs.json"], ""), "pipeline/source_registry.json": ("blog", ["pipeline/source_registry.json"], ""),
            "pipeline/ops_inbox_policy.json": ("blog", ["pipeline/ops_inbox_policy.json"], ""), "requirements*.txt": ("blog", ["requirements-x.txt"], ""), "vendor/": ("desktop", ["vendor/a.py"], ""),
            "package*.json": ("blog", ["package-lock.json"], ""), "pyproject.toml": ("blog", ["pyproject.toml"], ""), "Pipfile*": ("blog", ["Pipfile.lock"], ""), "*.lock": ("blog", ["a.lock"], ""),
            ".env*": ("blog", [".env.x"], ""), "secrets.": ("blog", ["a.py"], "secrets.X"), "PIPELINE_PAUSE": ("blog", ["a.py"], "PIPELINE_PAUSE"), "VERSION": ("desktop", ["VERSION"], ""),
        }
        self.assertEqual(set(samples), set(mp.DOCUMENTED_RULE_WORDS))
        for word, (kind, paths, text) in samples.items():
            with self.subTest(word=word):
                self.assertEqual(classify(kind, paths, text).tier, "operator_only")

    def test_the_policy_files_themselves_are_operator_only(self):
        self.assertEqual(mp.POLICY_SELF_FILES, ("docs/AI_MERGE_POLICY.md", "pipeline/merge_policy.py", "tests/test_merge_policy.py", "tests/test_merge_policy_docs.py"))
        for kind in ("blog", "desktop"):
            for path in mp.POLICY_SELF_FILES + ("DOCS/ai_merge_policy.md", "./pipeline/merge_policy.py"):
                with self.subTest(kind=kind, path=path):
                    result = classify(kind, [path])
                    self.assertEqual(result.tier, "operator_only")
                    self.assertEqual(result.extra_flags, ("policy_self",))
                    self.assertEqual(result.categories, ())

    def test_several_items_are_listed_in_policy_order(self):
        result = classify("blog", ["requirements.txt", ".github/workflows/ci.yml", "index.html", "_posts/a.md"], "secrets.X")
        order = [code for code in mp.OPERATOR_ONLY_CODES if code in result.categories]
        self.assertEqual(list(result.categories), order)
        self.assertEqual(set(result.categories), {"workflow", "ads", "public_content", "dependencies", "credentials"})

    def test_many_files_are_summarized_not_listed_one_by_one(self):
        paths = ["_posts/2026-11-15-%03d.md" % number for number in range(100)]
        result = classify("blog", paths)
        self.assertEqual(result.categories, ("public_content",))
        self.assertLessEqual(len(result.reasons), 40)
        self.assertTrue(any("외 97개" in reason for reason in result.reasons))
        self.assertEqual(len(result.paths), 100)

    def test_a_path_with_a_secret_shape_is_masked_in_the_reasons(self):
        value = FAKE_SECRETS["google"]
        result = classify("blog", [".github/workflows/" + value + ".yml"])
        self.assertEqual(result.categories, ("workflow",))
        joined = " ".join(result.reasons)
        self.assertNotIn(value, joined)
        self.assertIn("가렸습니다", joined)


class ClassifyDesktopTest(unittest.TestCase):
    def test_desktop_rules(self):
        for path, categories, extras in (
                (".github/workflows/ci.yml", ("workflow",), ()), ("requirements.txt", ("dependencies",), ()), ("vendor/pipeline/console.py", ("dependencies",), ()),
                ("VERSION", (), ("packaging_release",)), ("app.spec", (), ("packaging_release",)), ("installer/setup.iss", (), ("packaging_release",)), ("build/x.py", (), ("packaging_release",)),
                ("packaging/a.py", (), ("packaging_release",)), ("src/chanceblog_desktop/security/mask.py", ("credentials",), ()), (".env.example", ("credentials",), ()),
                ("pyproject.toml", ("dependencies",), ())):
            with self.subTest(path=path):
                result = classify("desktop", [path])
                self.assertEqual((result.tier, result.categories, result.extra_flags), ("operator_only", categories, extras))

    def test_blog_only_rules_do_not_apply_to_the_desktop_and_the_reverse(self):
        self.assertEqual(classify("desktop", ["index.html", "_posts/a.md", "about.md", "pipeline/blogs.json"]).tier, "ai_ok")
        self.assertEqual(classify("blog", ["VERSION", "app.spec", "installer/setup.iss", "build/x.py"]).tier, "ai_ok")


class ClassifyInvalidInputTest(unittest.TestCase):
    def assert_invalid(self, result):
        self.assertEqual(result.tier, "operator_only")
        self.assertIn("invalid_input", result.extra_flags)
        self.assertTrue(result.reasons)

    def test_an_unknown_repo_kind_is_not_ai_ok(self):
        for kind in ("web", "", "Blog", "BLOG", None, 3, ["blog"]):
            with self.subTest(kind=kind):
                self.assert_invalid(mp.classify_change(kind, ["pipeline/a.py"], "", dict(DECLARED_OK)))

    def test_a_bad_path_list_is_not_ai_ok(self):
        for paths in (None, [], "pipeline/a.py", ["a/../.github/x"], ["../a.py"], ["/etc/a.py"], ["C" + ":/a.py"], [None], [1], [""], ["a\x00b"], 5, ("a.py", None)):
            with self.subTest(paths=paths):
                self.assert_invalid(mp.classify_change("blog", paths, "", dict(DECLARED_OK)))

    def test_a_bad_added_text_is_not_ai_ok(self):
        for text in (None, 5, ["x"], b"x", object()):
            with self.subTest(text=repr(text)):
                self.assert_invalid(mp.classify_change("blog", ["pipeline/a.py"], text, dict(DECLARED_OK)))
        self.assertEqual(mp.classify_change("blog", ["pipeline/a.py"], "", dict(DECLARED_OK)).tier, "ai_ok")

    def test_added_text_may_be_a_mapping_from_path_to_text(self):
        self.assertEqual(mp.classify_change("blog", ["pipeline/a.py"], {"pipeline/a.py": GOOD_TEXT, "tests/t.py": "pass\n"}, dict(DECLARED_OK)).tier, "ai_ok")
        flagged = mp.classify_change("blog", ["pipeline/a.py"], {"pipeline/a.py": GOOD_TEXT, "docs/x.md": "adsbygoogle"}, dict(DECLARED_OK))
        self.assertEqual(flagged.categories, ("ads",))
        self.assert_invalid(mp.classify_change("blog", ["pipeline/a.py"], {"pipeline/a.py": 5}, dict(DECLARED_OK)))

    def test_a_bad_declaration_is_not_ai_ok(self):
        for declared in ("no", ["x"], 5, dict(DECLARED_OK, unknown_item=False), {1: False}):
            with self.subTest(declared=declared):
                self.assert_invalid(mp.classify_change("blog", ["pipeline/a.py"], "", declared))

    def test_the_function_never_raises(self):
        weird = (None, 5, "x", [], {}, object(), b"x", ["x"], {"a": 1}, float("nan"), True)
        for kind in ("blog", "desktop", None, 3):
            for paths in weird:
                for text in weird:
                    for declared in (None, 5, {}, dict(DECLARED_OK)):
                        result = mp.classify_change(kind, paths, text, declared)
                        self.assertIn(result.tier, ("ai_ok", "operator_only"))
                        if result.tier == "ai_ok":
                            self.assertEqual(result.categories + result.extra_flags, ())


class PreconditionsTest(unittest.TestCase):
    def failed(self, facts):
        return mp.check_preconditions(facts).failed_codes

    def test_complete_good_facts_pass_all_eight(self):
        verdict = mp.check_preconditions(good_facts())
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.failures, ())
        self.assertEqual(verdict.explain(), [])

    def test_the_condition_names_are_the_operators_words_in_order(self):
        verdict = mp.check_preconditions({})
        self.assertEqual(tuple(item.name for item in verdict.failures), PRECONDITIONS_8)
        self.assertEqual(verdict.failed_codes, tuple(code for code, _ in mp.PRECONDITIONS))
        self.assertEqual(len(verdict.failures), 8)

    def test_condition_1_the_approved_number_must_match_the_pr(self):
        for key, value in (("approved_number", "M076"), ("pr_title_label", "M076"), ("approved_pr_number", 199), ("pr_number", 199), ("approved_number", "M75"), ("approved_number", "m075"),
                           ("pr_title_label", "[M075]"), ("approved_pr_number", True), ("pr_number", "198"), ("consumed_numbers", ["M074", "M075"]), ("consumed_numbers", "M075"),
                           ("consumed_numbers", {"M075": 1})):
            with self.subTest(key=key, value=value):
                facts = good_facts()
                facts[key] = value
                self.assertEqual(self.failed(facts), ("number_match",))

    def test_condition_1_a_used_approval_cannot_be_reused(self):
        facts = good_facts()
        facts["consumed_numbers"] = ("M070", "M075")
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("number_match",))
        self.assertIn("한 번 쓴 승인", verdict.failures[0].reason)
        facts["consumed_numbers"] = ["M070", "M071"]
        self.assertTrue(mp.check_preconditions(facts).ok)

    def test_condition_2_a_commit_after_the_approval_fails(self):
        for current in (SHA_B, "f" * 40):
            facts = good_facts()
            facts["current_head_sha"] = current
            self.assertEqual(self.failed(facts), ("no_new_commit",))
        for bad in ("abc1234", "", "g" * 40, 5):
            facts = good_facts()
            facts["approved_head_sha"] = bad
            self.assertEqual(self.failed(facts), ("no_new_commit",))

    def test_condition_3_every_check_must_have_succeeded(self):
        broken = (
            [{"name": "a", "conclusion": "failure"}], [{"name": "a", "conclusion": "success"}, {"name": "b", "conclusion": "skipped"}], [{"name": "a", "conclusion": "neutral"}],
            [{"name": "a", "conclusion": "cancelled"}], [{"name": "a", "conclusion": "timed_out"}], [{"name": "a", "conclusion": "action_required"}], [{"name": "a", "conclusion": None}],
            [{"name": "a", "conclusion": "SUCCESS"}], [{"name": "a", "conclusion": "pending"}], [{"name": "a"}], [{"name": "", "conclusion": "success"}], [{"conclusion": "success"}],
            [], "success", None, [None], ["success"], 5, [{"name": "a", "conclusion": "success"}, "x"])
        for checks in broken:
            with self.subTest(checks=checks):
                facts = good_facts()
                facts["checks"] = checks
                self.assertEqual(self.failed(facts), ("checks_pass",))

    def test_condition_3_names_the_failed_checks(self):
        facts = good_facts()
        facts["checks"] = [{"name": "빨간 검사", "conclusion": "failure"}, {"name": "초록 검사", "conclusion": "success"}]
        reason = mp.check_preconditions(facts).failures[0].reason
        self.assertIn("빨간 검사", reason)
        self.assertNotIn("초록 검사", reason)

    def test_condition_4_the_independent_verification_must_have_passed(self):
        def with_record(**changes):
            facts = good_facts()
            facts["independent_verification"] = dict(facts["independent_verification"], **changes)
            return facts

        for changes in ({"verdict": "fail"}, {"verdict": "Pass"}, {"verdict": True}, {"verifier": "구현자 을"}, {"verifier": " 구현자 을 "}, {"verifier": ""}, {"implementer": ""}, {"verifier": 5},
                        {"open_required_findings": 2}, {"open_required_findings": True}, {"open_required_findings": -1}, {"open_required_findings": "0"}, {"verified_tree": TREE_B},
                        {"verified_tree": "abc"}, {"verified_tree": None}, {"verdict": None}):
            with self.subTest(changes=changes):
                self.assertEqual(self.failed(with_record(**changes)), ("independent_verified",))
        for key in VERIFICATION_KEYS_5:
            facts = good_facts()
            del facts["independent_verification"][key]
            self.assertEqual(self.failed(facts), ("independent_verified",), key)
        for bad in ("pass", ["pass"], None, 5, {}):
            facts = good_facts()
            facts["independent_verification"] = bad
            self.assertEqual(self.failed(facts), ("independent_verified",))

    def test_condition_4_the_verified_content_must_be_the_content_being_merged(self):
        facts = good_facts()
        facts["current_tree"] = TREE_B
        self.assertEqual(self.failed(facts), ("independent_verified",))

    def test_condition_5_no_conflict(self):
        for value in (True, None, "false", "False", 0, 1, "", "no", [], object()):
            with self.subTest(value=repr(value)):
                facts = good_facts()
                facts["has_conflict"] = value
                self.assertEqual(self.failed(facts), ("no_conflict",))

    def test_condition_6_the_changed_files_must_match_the_approved_explanation(self):
        for current in (list(GOOD_PATHS) + ["docs/new.md"], [GOOD_PATHS[0]], ["pipeline/other.py", GOOD_PATHS[1]], [], None, "pipeline/topics.py", ["../x"]):
            with self.subTest(current=current):
                facts = good_facts()
                facts["current_paths"] = current
                self.assertEqual(self.failed(facts), ("scope_matches",))
        facts = good_facts()
        facts["approved_paths"] = list(GOOD_PATHS) + ["docs/old.md"]
        self.assertEqual(self.failed(facts), ("scope_matches",))

    def test_condition_6_an_operator_only_change_cannot_be_merged_by_ai(self):
        paths = list(GOOD_PATHS) + [".github/workflows/ci.yml"]
        facts = good_facts()
        facts["approved_paths"] = list(paths)
        facts["current_paths"] = list(paths)
        facts["classification"] = classify("blog", paths, GOOD_TEXT).to_dict()
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("scope_matches",))
        self.assertIn("GitHub Actions Workflow", verdict.failures[0].reason)
        facts["classification"] = classify("blog", paths, GOOD_TEXT)                              # 결과 객체를 그대로 넣어도 같다
        self.assertEqual(self.failed(facts), ("scope_matches",))

    def test_condition_6_a_policy_file_change_cannot_be_merged_by_ai(self):
        paths = ["pipeline/merge_policy.py"]
        facts = good_facts()
        facts["approved_paths"] = facts["current_paths"] = list(paths)
        facts["classification"] = classify("blog", paths, GOOD_TEXT)
        self.assertEqual(self.failed(facts), ("scope_matches",))

    def test_condition_6_a_stale_or_malformed_classification_fails(self):
        stale = classify("blog", ["pipeline/other.py"], GOOD_TEXT).to_dict()
        for value in (stale, {"tier": "ai_ok"}, {"tier": "maybe", "categories": [], "extra_flags": [], "paths": list(GOOD_PATHS)}, "ai_ok", 5, None,
                      {"tier": "ai_ok", "categories": [], "extra_flags": [], "paths": [1]}, {"tier": "ai_ok", "categories": ["workflow"], "extra_flags": [], "paths": list(GOOD_PATHS)},
                      {"tier": "ai_ok", "categories": [], "extra_flags": ["invalid_input"], "paths": list(GOOD_PATHS)},
                      {"tier": "operator_only", "categories": [], "extra_flags": [], "paths": list(GOOD_PATHS)}):
            with self.subTest(value=value):
                facts = good_facts()
                facts["classification"] = value
                self.assertEqual(self.failed(facts), ("scope_matches",))

    def test_condition_7_no_secret_findings(self):
        for value in (1, 3, True, False, "0", 0.0, -1, [], object()):
            with self.subTest(value=repr(value)):
                facts = good_facts()
                facts["secret_findings"] = value
                self.assertEqual(self.failed(facts), ("no_secret_exposure",))

    def test_condition_8_the_rollback_method_must_be_concrete(self):
        for text in ("", "   ", "없음", "해당 없음", "미정", "TBD", "n/a", "-", "되돌림", "짧은 문장", None, 5, ["되돌리기"]):
            with self.subTest(text=text):
                facts = good_facts()
                facts["rollback_method"] = text
                self.assertEqual(self.failed(facts), ("rollback_confirmed",))
        facts = good_facts()
        facts["rollback_method"] = "이 병합 커밋 하나를 되돌리는 PR 을 만듭니다."
        self.assertTrue(mp.check_preconditions(facts).ok)

    def test_a_missing_value_is_a_failure_of_the_condition_that_needs_it(self):
        owner = {"approved_number": "number_match", "approved_pr_number": "number_match", "pr_number": "number_match", "pr_title_label": "number_match", "consumed_numbers": "number_match",
                 "approved_head_sha": "no_new_commit", "current_head_sha": "no_new_commit", "current_tree": "independent_verified", "approved_paths": "scope_matches",
                 "current_paths": "scope_matches", "checks": "checks_pass", "independent_verification": "independent_verified", "has_conflict": "no_conflict",
                 "classification": "scope_matches", "secret_findings": "no_secret_exposure", "rollback_method": "rollback_confirmed"}
        self.assertEqual(set(owner), set(FACT_KEYS_16))
        special = {"has_conflict": "알 수 없습니다", "secret_findings": "결과가 없습니다", "rollback_method": "문장이 없습니다"}      # 값이 없을 때 이 세 조건이 쓰는 쉬운 말
        for key in FACT_KEYS_16:
            for how in ("missing", "none"):
                with self.subTest(key=key, how=how):
                    facts = good_facts()
                    if how == "missing":
                        del facts[key]
                    else:
                        facts[key] = None
                    verdict = mp.check_preconditions(facts)
                    self.assertFalse(verdict.ok)
                    self.assertEqual(verdict.failed_codes, (owner[key],))
                    reason = verdict.failures[0].reason
                    if key in special:
                        self.assertIn(special[key], reason)
                    else:                                                                     # 값이 없다고 말하고, 어느 값인지 이름을 댄다
                        self.assertIn("필요한 값이 없습니다", reason)
                        self.assertIn(key, reason)

    def test_an_empty_or_non_dictionary_facts_fails_every_condition(self):
        for facts in ({}, None, [], "facts", 5, [("approved_number", "M075")]):
            with self.subTest(facts=repr(facts)):
                verdict = mp.check_preconditions(facts)
                self.assertFalse(verdict.ok)
                self.assertEqual(len(verdict.failures), 8)

    def test_several_failures_are_reported_together(self):
        facts = good_facts()
        facts["current_head_sha"] = SHA_B
        facts["has_conflict"] = True
        facts["secret_findings"] = 2
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("no_new_commit", "no_conflict", "no_secret_exposure"))
        self.assertEqual(len(verdict.explain()), 3)
        self.assertTrue(all(": " in line for line in verdict.explain()))

    def test_weird_values_never_raise_and_never_pass(self):
        weird = (object(), [], {}, 0, "", -1, float("nan"), True, False, "x", (), {"a": 1}, [object()], b"x")
        valid_values = (("has_conflict", False), ("secret_findings", 0), ("consumed_numbers", []), ("consumed_numbers", ()))       # 값 자체가 올바른 것(통과해도 되는 것)
        for key in FACT_KEYS_16:
            for value in weird:
                with self.subTest(key=key, value=repr(value)):
                    facts = good_facts()
                    facts[key] = value
                    verdict = mp.check_preconditions(facts)
                    if any(key == name and type(value) is type(ok) and value == ok for name, ok in valid_values):
                        continue
                    self.assertFalse(verdict.ok)

    def test_the_input_is_not_modified(self):
        facts = good_facts()
        before = copy.deepcopy(facts)
        mp.check_preconditions(facts)
        self.assertEqual(facts, before)

    def test_extra_keys_are_ignored_but_the_result_is_the_same(self):
        facts = good_facts()
        facts["note"] = "참고"
        self.assertTrue(mp.check_preconditions(facts).ok)

    def test_a_broken_check_function_closes_instead_of_passing(self):
        class Exploding(dict):
            def get(self, key, default=None):
                raise RuntimeError("boom")

        verdict = mp.check_preconditions(Exploding(good_facts()))
        self.assertFalse(verdict.ok)


class MergeMethodTest(unittest.TestCase):
    def test_only_a_pr_merge_is_allowed(self):
        self.assertTrue(mp.merge_method_allowed("pr_merge"))

    def test_direct_pushes_and_force_pushes_are_refused(self):
        for method in ("push_main", "direct_push", "force_push"):
            with self.subTest(method=method):
                self.assertFalse(mp.merge_method_allowed(method))
        self.assertEqual(set(mp.FORBIDDEN_MERGE_METHODS), {"push_main", "direct_push", "force_push"})

    def test_unknown_or_differently_written_values_are_refused(self):
        for method in ("squash", "merge", "rebase", "PR_MERGE", "Pr_Merge", " pr_merge", "pr_merge ", "pr-merge", "pr_merge\n", "", None, 1, True, ["pr_merge"], b"pr_merge", ("pr_merge",), object(),
                       "git push origin main", "push", "force", "main", "push_main_branch", "pr_merge;push_main"):
            with self.subTest(method=repr(method)):
                self.assertFalse(mp.merge_method_allowed(method))


class ExplanationTest(unittest.TestCase):
    def problems(self, text, **kw):
        return mp.explanation_problems(text, **kw)

    def assert_problem(self, problems, *words):
        self.assertTrue(problems, "문제가 하나도 없다")
        self.assertTrue(any(all(word in problem for word in words) for problem in problems), (words, problems))

    def test_the_rendered_explanation_is_complete(self):
        text = make_text()
        self.assertEqual(self.problems(text), [])
        self.assertEqual(self.problems(text, pr_title="[M075] 초안 저장"), [])
        lines = text.split("\n")
        self.assertEqual(lines[0], "병합 요청 M075")
        self.assertEqual(lines[1], "대상 PR: #198 · 머리 커밋: ccccccc")
        for item, answer in zip(EXPLANATION_6, ANSWERS):
            self.assertIn(item + " " + answer, lines)
        self.assertIn("변경 파일 (2개)", lines)
        self.assertIn("- pipeline/drafts.py", lines)
        for label in OPERATOR_ONLY_12:
            self.assertIn("- " + label + ": 아니오", lines)
        self.assertIn("병합 방식: " + mp.AI_MERGE_OFF_NOTICE, lines)
        self.assertIn("지금은 AI 병합 기능이 꺼져 있어 운영자께서 직접 병합해 주세요.", text)
        self.assertIn("승인 방식은 반드시 병합 번호와 함께 사용해 주세요.", lines)
        self.assertEqual(lines[-2], "승인 예: M075 승인")
        self.assertEqual(lines[-1], "")

    def test_the_enabled_form_says_what_the_approval_does(self):
        text = make_text(enabled=True)
        self.assertEqual(self.problems(text), [])
        self.assertIn(mp.AI_MERGE_ON_NOTICE, text)
        self.assertNotIn(mp.AI_MERGE_OFF_NOTICE, text)
        self.assertIn("main 에 직접 push 하지 않습니다", text)

    def test_the_example_number_follows_the_requested_number(self):
        for number in ("M001", "M075", "M1000"):
            text = make_text(number=number)
            self.assertEqual(self.problems(text), [])
            self.assertIn("병합 요청 " + number + "\n", text)
            self.assertIn("승인 예: " + number + " 승인\n", text)

    def test_each_of_the_six_items_missing_is_reported_by_name(self):
        text = make_text()
        for item in EXPLANATION_6:
            with self.subTest(item=item):
                self.assert_problem(self.problems(drop_line(text, item + " ")), "항목이 빠졌습니다", item)

    def test_an_item_with_a_blank_short_or_non_korean_answer_is_reported(self):
        text = make_text()
        first = EXPLANATION_6[0] + " " + ANSWERS[0]
        for answer in ("", "없음", "TBD", "짧음", "the code was changed in the base", "pipeline/drafts.py", "1234567890"):
            with self.subTest(answer=answer):
                self.assert_problem(self.problems(replace_once(text, first, EXPLANATION_6[0] + " " + answer)), EXPLANATION_6[0])

    def test_an_item_written_twice_is_reported(self):
        text = make_text() + "왜 필요한가요? 한 번 더 적은 이유입니다.\n"
        self.assert_problem(self.problems(text), "두 번 이상", "왜 필요한가요?")

    def test_the_first_line_must_be_the_request_line_with_a_standard_number(self):
        text = make_text()
        self.assert_problem(self.problems("\n".join(text.split("\n")[1:])), "첫 줄")
        self.assert_problem(self.problems(replace_once(text, "병합 요청 M075\n", "병합 요청 M75\n")), "첫 줄")
        self.assert_problem(self.problems(replace_once(text, "병합 요청 M075\n", "병합 요청 M0075\n")), "첫 줄")
        self.assert_problem(self.problems(replace_once(text, "병합 요청 M075\n", "승인 요청 M075\n")), "첫 줄")
        self.assert_problem(self.problems(replace_once(text, "병합 요청 M075\n", "병합 요청 M075 입니다\n")), "첫 줄")

    def test_the_pr_number_and_head_commit_are_required_once(self):
        text = make_text()
        self.assert_problem(self.problems(replace_once(text, "대상 PR: #198 · 머리 커밋: ccccccc", "머리 커밋: ccccccc")), "대상 PR")
        self.assert_problem(self.problems(replace_once(text, "대상 PR: #198 · 머리 커밋: ccccccc", "대상 PR: #198")), "머리 커밋")
        self.assert_problem(self.problems(replace_once(text, "대상 PR: #198 · 머리 커밋: ccccccc", "대상 PR: #0 · 머리 커밋: ccccccc")), "대상 PR")
        self.assert_problem(self.problems(replace_once(text, "머리 커밋: ccccccc", "머리 커밋: ccccc")), "머리 커밋")                  # 5자는 짧다
        self.assert_problem(self.problems(replace_once(text, "머리 커밋: ccccccc", "머리 커밋: 해시없음")), "머리 커밋")
        self.assert_problem(self.problems(text + "대상 PR: #199\n"), "대상 PR")
        self.assert_problem(self.problems(text + "머리 커밋: abcdef1\n"), "머리 커밋")

    def test_the_changed_file_list_must_be_present_and_consistent(self):
        text = make_text()
        self.assert_problem(self.problems(replace_once(text, "변경 파일 (2개)\n", "")), "변경 파일 목록")
        self.assert_problem(self.problems(replace_once(text, "변경 파일 (2개)", "변경 파일 (3개)")), "개수")
        self.assert_problem(self.problems(replace_once(text, "변경 파일 (2개)", "변경 파일 (1개)")), "개수")
        self.assert_problem(self.problems(drop_line(drop_line(text, "- pipeline/drafts.py"), "- tests/test_drafts.py")), "비어 있습니다")
        self.assert_problem(self.problems(replace_once(text, "- tests/test_drafts.py\n", "- tests/test_drafts.py\n- ../evil.py\n").replace("(2개)", "(3개)")), "올바르지 않은 경로")

    def test_each_of_the_twelve_checklist_rows_flipped_to_yes_is_reported(self):
        text = make_text()
        for label in OPERATOR_ONLY_12:
            with self.subTest(label=label):
                flipped = replace_once(text, "- " + label + ": 아니오", "- " + label + ": 예")
                self.assert_problem(self.problems(flipped), "'예'", label)

    def test_each_of_the_twelve_checklist_rows_missing_is_reported(self):
        text = make_text()
        for label in OPERATOR_ONLY_12:
            with self.subTest(label=label):
                self.assert_problem(self.problems(drop_line(text, "- " + label + ":")), "빠진 항목", label)

    def test_a_garbled_or_extra_checklist_row_is_reported(self):
        text = make_text()
        self.assert_problem(self.problems(replace_once(text, "- PIPELINE_PAUSE: 아니오", "- PIPELINE_PAUSE: 모름")), "PIPELINE_PAUSE")
        self.assert_problem(self.problems(replace_once(text, "- PIPELINE_PAUSE: 아니오", "- PIPELINE_PAUSE:")), "PIPELINE_PAUSE")
        self.assert_problem(self.problems(replace_once(text, "- PIPELINE_PAUSE: 아니오", "- PIPELINE_PAUSE: 아니오\n- 새 항목: 예")), "새 항목")
        self.assert_problem(self.problems(replace_once(text, "- PIPELINE_PAUSE: 아니오", "- PIPELINE_PAUSE: 아니오 (일부)")), "PIPELINE_PAUSE")

    def test_the_checklist_header_is_required(self):
        text = make_text()
        header = "운영자 전용 항목 점검 (모두 아니오여야 AI 병합 대상입니다)"
        self.assertTrue(self.problems(replace_once(text, header + "\n", "")))
        self.assertTrue(self.problems(text.replace(header, "점검표 (생략)")))

    def test_a_yes_in_the_rendered_checklist_makes_it_not_an_ai_merge_request(self):
        for code, label in mp.OPERATOR_ONLY_ITEMS:
            with self.subTest(code=code):
                text = make_text(checklist={code: True})
                self.assert_problem(self.problems(text), "'예'", label)
        self.assertEqual(self.problems(make_text(checklist={code: False for code in mp.OPERATOR_ONLY_CODES})), [])
        self.assert_problem(self.problems(make_text(checklist={"workflow": None})), "'예'")

    def test_the_merge_way_line_is_required_and_must_be_one_of_the_two_sentences(self):
        text = make_text()
        self.assert_problem(self.problems(drop_line(text, "병합 방식:")), "병합 방식")
        self.assert_problem(self.problems(replace_once(text, mp.AI_MERGE_OFF_NOTICE, "곧 AI 가 병합합니다.")), "병합 방식")
        self.assert_problem(self.problems(text + "병합 방식: " + mp.AI_MERGE_OFF_NOTICE + "\n"), "병합 방식")

    def test_the_approval_guide_and_example_lines_are_required(self):
        text = make_text()
        self.assert_problem(self.problems(drop_line(text, "승인 방식은")), "승인 안내")
        self.assert_problem(self.problems(drop_line(text, "승인 예:")), "승인 예")
        self.assert_problem(self.problems(text + "승인 예: M075 승인\n"), "승인 예")

    def test_every_number_in_the_text_must_agree(self):
        text = make_text()
        mismatched = replace_once(text, "승인 예: M075 승인", "승인 예: M076 승인")
        self.assert_problem(self.problems(mismatched), "승인 예의 번호", "M076")
        self.assert_problem(self.problems(mismatched), "다른 번호의 승인 문구", "M076")
        stray = replace_once(text, ANSWERS[1], ANSWERS[1] + " 참고로 M999 승인 이라고 쓰면 됩니다.")
        self.assert_problem(self.problems(stray), "다른 번호의 승인 문구", "M999")
        self.assert_problem(self.problems(text, pr_title="[M076] 제목"), "PR 제목")
        self.assert_problem(self.problems(text, pr_title="제목 [M075]"), "PR 제목")
        self.assert_problem(self.problems(text, pr_title="[M075] [M076] 제목"), "PR 제목")
        self.assert_problem(self.problems(text, pr_title=""), "PR 제목")
        self.assertEqual(self.problems(text + "참고: M074 병합은 이미 끝났습니다.\n"), [])                 # 승인 문구가 아닌 다른 번호 언급은 괜찮다

    def test_invisible_and_direction_characters_are_reported(self):
        text = make_text()
        for char in (chr(0x200B), chr(0x200E), chr(0x202E), chr(0x2066), chr(0xFEFF), chr(0x2060)):
            with self.subTest(code=hex(ord(char))):
                self.assert_problem(self.problems(text.replace("병합 요청", "병합" + char + " 요청", 1)), "보이지 않는 글자")

    def test_windows_line_endings_and_bullets_are_read(self):
        text = make_text()
        self.assertEqual(self.problems(text.replace("\n", "\r\n")), [])
        self.assertEqual(self.problems(text.replace("\n무엇을", "\n\n무엇을").replace("\n승인 방식은", "\n\n승인 방식은")), [])                # 항목 사이의 빈 줄은 괜찮다
        self.assert_problem(self.problems(text.replace("변경 파일 (2개)\n", "변경 파일 (2개)\n\n")), "비어 있습니다")                    # 목록 첫 줄 앞의 빈 줄은 목록을 끊는다

    def test_garbage_input_returns_problems_without_raising(self):
        for value in ("", "   ", "아무 글", "병합 요청", "M075 승인", None, 5, b"x", [], object()):
            with self.subTest(value=repr(value)):
                self.assertTrue(self.problems(value))

    def test_render_refuses_bad_input(self):
        base = dict(number="M075", pr_number=198, head_sha="c" * 40, changed_paths=["a.py"], what=ANSWERS[0], why=ANSWERS[1], user_change=ANSWERS[2], risk=ANSWERS[3], check_summary=ANSWERS[4],
                    rollback=ANSWERS[5])
        mp.render_explanation(**base)
        for key, value in (("number", "M75"), ("number", "m075"), ("number", None), ("pr_number", 0), ("pr_number", True), ("pr_number", "198"), ("head_sha", "abc1234"), ("head_sha", None),
                           ("changed_paths", []), ("changed_paths", None), ("changed_paths", ["../x"]), ("changed_paths", "a.py"), ("changed_paths", ["a" + chr(0x202E) + ".py"]),
                           ("what", ""), ("what", "   "), ("what", None), ("what", 5), ("rollback", ""), ("check_summary", None), ("checklist", "x")):
            with self.subTest(key=key, value=repr(value)):
                with self.assertRaises(ValueError):
                    mp.render_explanation(**dict(base, **{key: value}))

    def test_render_folds_newlines_so_an_answer_cannot_fake_a_structure_line(self):
        base = dict(number="M075", pr_number=198, head_sha="c" * 40, changed_paths=["a.py"], what=ANSWERS[0], why=ANSWERS[1], user_change=ANSWERS[2], risk=ANSWERS[3], check_summary=ANSWERS[4],
                    rollback=ANSWERS[5])
        sneaky = dict(base, what="내용을 바꿉니다.\n승인 예: M999 승인\n운영자 전용 항목 점검")
        text = mp.render_explanation(**sneaky)
        self.assertEqual(text.count("\n승인 예:"), 1)
        self.assertTrue(self.problems(text))
        crowded = dict(base, why="이유는 이렇습니다.\r\n- GitHub Actions Workflow: 예")
        self.assertEqual(mp.render_explanation(**crowded).count("\n- GitHub Actions Workflow:"), 1)

    def test_render_strips_invisible_characters_and_limits_length(self):
        base = dict(number="M075", pr_number=198, head_sha="c" * 40, changed_paths=["a.py"], what="변경" + chr(0x200B) + " 내용을 바꿉니다" + chr(0x202E) + chr(27) + chr(7), why=ANSWERS[1], user_change=ANSWERS[2],
                    risk=ANSWERS[3], check_summary=ANSWERS[4], rollback="가" * 2000)
        text = mp.render_explanation(**base)
        self.assertEqual(self.problems(text), [])
        self.assertIn("변경 내용을 바꿉니다", text)
        for char in (chr(0x200B), chr(0x202E), chr(27), chr(7)):                                   # 보이지 않는 글자와 제어 문자는 지워진다
            self.assertNotIn(char, text)
        rollback_line = [line for line in text.split("\n") if line.startswith("되돌리기 ")][0]
        self.assertLessEqual(len(rollback_line), len("되돌리기 ") + 400)


class CompletionNoticeTest(unittest.TestCase):
    def assert_problem(self, problems, *words):
        self.assertTrue(any(all(word in problem for word in words) for problem in problems), (words, problems))

    def test_the_rendered_notice_has_all_seven_items(self):
        text = make_notice()
        self.assertEqual(mp.completion_notice_problems(text), [])
        lines = text.split("\n")
        self.assertEqual(lines[0], "병합 완료 알림")
        for item in COMPLETION_7:
            self.assertEqual(len([line for line in lines if line.startswith(item + ": ")]), 1, item)
        self.assertIn("병합 번호: M075", lines)
        self.assertIn("PR 번호: #198", lines)
        self.assertIn("병합된 Commit: dddddddddddd", lines)

    def test_each_of_the_seven_items_missing_is_reported_by_name(self):
        text = make_notice()
        for item in COMPLETION_7:
            with self.subTest(item=item):
                self.assert_problem(mp.completion_notice_problems(drop_line(text, item + ":")), "빠졌습니다", item)

    def test_an_item_with_an_empty_value_is_reported(self):
        text = make_notice()
        for item in COMPLETION_7:
            with self.subTest(item=item):
                line = [line for line in text.split("\n") if line.startswith(item + ":")][0]
                self.assert_problem(mp.completion_notice_problems(text.replace(line, item + ":")), "비어 있습니다", item)
                self.assert_problem(mp.completion_notice_problems(text.replace(line, item + ":   ")), "비어 있습니다", item)

    def test_an_item_without_a_colon_is_not_found(self):
        text = make_notice()
        self.assert_problem(mp.completion_notice_problems(replace_once(text, "이상 유무: 이상 없음", "이상 유무 이상 없음")), "빠졌습니다", "이상 유무")

    def test_an_item_written_twice_is_reported(self):
        text = make_notice() + "이상 유무: 있음\n"
        self.assert_problem(mp.completion_notice_problems(text), "두 번 이상", "이상 유무")

    def test_the_value_formats_are_checked(self):
        text = make_notice()
        for old, new, item in (("병합 번호: M075", "병합 번호: M75", "병합 번호"), ("병합 번호: M075", "병합 번호: 075", "병합 번호"), ("병합 번호: M075", "병합 번호: m075", "병합 번호"),
                               ("PR 번호: #198", "PR 번호: 열아홉", "PR 번호"), ("PR 번호: #198", "PR 번호: #0", "PR 번호"), ("PR 번호: #198", "PR 번호: 12a", "PR 번호"),
                               ("병합된 Commit: dddddddddddd", "병합된 Commit: 해시없음", "병합된 Commit"), ("병합된 Commit: dddddddddddd", "병합된 Commit: abc12", "병합된 Commit")):
            with self.subTest(new=new):
                self.assert_problem(mp.completion_notice_problems(replace_once(text, old, new)), item)
        self.assertEqual(mp.completion_notice_problems(replace_once(text, "PR 번호: #198", "PR 번호: 198")), [])

    def test_bullets_and_full_width_colons_are_read(self):
        text = make_notice()
        self.assertEqual(mp.completion_notice_problems("\n".join("- " + line if ": " in line else line for line in text.split("\n"))), [])
        self.assertEqual(mp.completion_notice_problems(text.replace(": ", chr(0xFF1A) + " ")), [])
        self.assertEqual(mp.completion_notice_problems(text.replace("\n", "\r\n")), [])

    def test_invisible_characters_are_reported(self):
        self.assert_problem(mp.completion_notice_problems(make_notice().replace("이상 유무", "이상" + chr(0x200B) + " 유무", 1)), "보이지 않는 글자")

    def test_garbage_input_returns_problems_without_raising(self):
        for value in ("", "알림", None, 5, b"x", [], object()):
            with self.subTest(value=repr(value)):
                self.assertTrue(mp.completion_notice_problems(value))

    def test_render_refuses_bad_input(self):
        base = dict(number="M075", pr_number=198, merged_commit="d" * 40, change="초안 저장이 반영되었습니다.", main_checks="전체 통과", anomaly="이상 없음", rollback="병합 커밋 한 개를 되돌립니다.")
        mp.render_completion_notice(**base)
        for key, value in (("number", "M75"), ("pr_number", 0), ("pr_number", True), ("merged_commit", "abc"), ("merged_commit", None), ("change", ""), ("rollback", None), ("anomaly", 5)):
            with self.subTest(key=key, value=repr(value)):
                with self.assertRaises(ValueError):
                    mp.render_completion_notice(**dict(base, **{key: value}))


def record(number, **changes):
    base = {"number": number}
    base.update({key: True for key, _label in mp.TRIAL_CRITERIA})
    base.update(changes)
    return base


class TrialTest(unittest.TestCase):
    OK3 = ("M070", "M071", "M072")

    def test_three_satisfied_records_continue(self):
        self.assertEqual(mp.evaluate_trial([record(n) for n in self.OK3]), "continue")
        self.assertEqual(mp.evaluate_trial([record(n) for n in self.OK3 + ("M073",)]), "continue")
        self.assertEqual(mp.evaluate_trial(tuple(record(n) for n in self.OK3)), "continue")
        report = mp.trial_report([record(n) for n in self.OK3])
        self.assertEqual((report.result, report.violations, report.counted), ("continue", (), 3))

    def test_fewer_than_three_without_violations_is_pending(self):
        for count in (0, 1, 2):
            with self.subTest(count=count):
                self.assertEqual(mp.evaluate_trial([record(n) for n in self.OK3[:count]]), "pending")

    def test_one_violation_stops_immediately_even_with_fewer_than_three_records(self):
        for key, label in mp.TRIAL_CRITERIA:
            for count in (1, 2, 3):
                with self.subTest(criterion=label, count=count):
                    records = [record(n) for n in self.OK3[:count - 1]] + [record(self.OK3[count - 1], **{key: False})]
                    report = mp.trial_report(records)
                    self.assertEqual(report.result, "stop_immediately")
                    self.assertTrue(any(label in violation for violation in report.violations), report.violations)
                    self.assertEqual(mp.evaluate_trial(records), "stop_immediately")

    def test_a_violation_in_any_position_of_a_longer_history_stops(self):
        for position in range(4):
            records = [record("M07%d" % n) for n in range(4)]
            records[position] = dict(records[position], no_revert=False)
            self.assertEqual(mp.evaluate_trial(records), "stop_immediately")

    def test_a_missing_or_non_boolean_value_is_a_violation(self):
        for key, _label in mp.TRIAL_CRITERIA:
            missing = record("M070")
            del missing[key]
            with self.subTest(key=key, how="missing"):
                self.assertEqual(mp.evaluate_trial([missing, record("M071"), record("M072")]), "stop_immediately")
            for value in ("true", "True", 1, 0, "예", [], {}, False):
                if key == "main_checks_passed" and value is None:
                    continue
                with self.subTest(key=key, value=repr(value)):
                    self.assertEqual(mp.evaluate_trial([record("M070", **{key: value})]), "stop_immediately")
        self.assertEqual(mp.evaluate_trial([record("M070", no_revert=None)]), "stop_immediately")

    def test_an_unknown_main_check_result_is_pending_not_continue(self):
        records = [record("M070"), record("M071"), record("M072", main_checks_passed=None)]
        self.assertEqual(mp.evaluate_trial(records), "pending")
        self.assertEqual(mp.evaluate_trial(records[:1] + [record("M071", main_checks_passed=None)]), "pending")
        self.assertEqual(mp.evaluate_trial(records + [record("M073", no_wrong_merge=False)]), "stop_immediately")

    def test_the_same_number_twice_is_a_violation(self):
        report = mp.trial_report([record("M070"), record("M070"), record("M071")])
        self.assertEqual(report.result, "stop_immediately")
        self.assertTrue(any("두 번 기록" in violation for violation in report.violations))
        self.assertEqual(mp.evaluate_trial([record("M070"), record("M070"), record("M070")]), "stop_immediately")

    def test_a_non_standard_number_or_a_malformed_record_is_a_violation(self):
        for bad in (record("M75"), record("m070"), record(None), record("P070"), record(70), {"number": "M070"}, "M070", None, 5, ["M070"]):
            with self.subTest(bad=repr(bad)):
                self.assertEqual(mp.evaluate_trial([bad, record("M071"), record("M072")]), "stop_immediately")

    def test_records_that_are_not_a_list_are_stopped(self):
        for value in (None, "M070", 5, {"M070": record("M070")}, record("M070"), object()):
            with self.subTest(value=repr(value)):
                self.assertEqual(mp.evaluate_trial(value), "stop_immediately")

    def test_three_records_of_which_one_is_bad_never_continue(self):
        for key, _label in mp.TRIAL_CRITERIA:
            records = [record("M070"), record("M071", **{key: False}), record("M072")]
            self.assertNotEqual(mp.evaluate_trial(records), "continue")

    def test_the_inputs_are_not_modified(self):
        records = [record(n) for n in self.OK3]
        before = copy.deepcopy(records)
        mp.evaluate_trial(records)
        self.assertEqual(records, before)

    def test_the_three_results_are_the_documented_words(self):
        self.assertEqual((mp.TRIAL_CONTINUE, mp.TRIAL_PENDING, mp.TRIAL_STOP), ("continue", "pending", "stop_immediately"))


class PolicyStoryTest(unittest.TestCase):
    """운영자 확인 016 의 예(M075)가 처음부터 끝까지 이어지는지 — 설명 → 승인 → 재확인 → 완료 알림 → 시험."""

    def test_the_whole_flow_for_one_pr(self):
        paths = ["pipeline/drafts.py", "tests/test_drafts.py"]
        explanation = make_text(paths=paths)
        self.assertEqual(mp.explanation_problems(explanation, pr_title="[M075] 초안 저장 기능"), [])
        number = mp.parse_approval("M075 승인")
        self.assertEqual(number, "M075")
        label = mp.pr_title_label("[M075] 초안 저장 기능")
        self.assertTrue(mp.approval_matches(number, label))
        ledger = mp.ApprovalLedger()
        facts = good_facts()
        facts.update({"approved_number": number, "pr_title_label": label, "approved_paths": list(paths), "current_paths": list(paths),
                      "classification": classify("blog", paths, GOOD_TEXT), "consumed_numbers": list(ledger.consumed_numbers)})
        verdict = mp.check_preconditions(facts)
        self.assertTrue(verdict.ok, verdict.explain())
        self.assertTrue(mp.approval_still_valid(SHA_A, SHA_A, paths, paths))
        self.assertTrue(mp.merge_method_allowed("pr_merge"))
        self.assertTrue(ledger.consume(number, 198).ok)
        self.assertEqual(mp.completion_notice_problems(make_notice()), [])
        self.assertEqual(mp.evaluate_trial([record("M075")]), "pending")

    def test_a_late_commit_a_wrong_number_or_a_reused_approval_each_stop_the_merge(self):
        facts = good_facts()
        facts["current_head_sha"] = SHA_B
        self.assertFalse(mp.check_preconditions(facts).ok)
        self.assertIsNone(mp.parse_approval("확인했습니다"))
        facts = good_facts()
        facts["pr_title_label"] = "M076"
        self.assertFalse(mp.check_preconditions(facts).ok)
        ledger = mp.ApprovalLedger([("M075", 198)])
        facts = good_facts()
        facts["consumed_numbers"] = list(ledger.consumed_numbers)
        self.assertFalse(mp.check_preconditions(facts).ok)


if __name__ == "__main__":
    unittest.main()
