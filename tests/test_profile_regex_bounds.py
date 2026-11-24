"""프로필 정규식 값 묶기(BP3, 감사 BP-S1-5 의 T3-3, 결함 D-431) 시험. 네트워크 없이 돈다.

배경(D-415): 한국어 프로필 셋의 금지 표현 정규식 가운데 앞이 제한 없는 숫자 반복(`\\d+…`·`\\d[\\d,.]*…`)이거나 이메일 모양(`[A-Za-z0-9._%+\\-]+@…`)인 것은 같은 종류 글자가 길게 이어지면
시작 위치마다 다시 먹어 글 길이의 제곱으로 느려진다. D-415 가 길이 한도의 두 배를 넘는 글을 정규식 없이 탈락시켰지만 두 배 미만의 같은 글자 가득한 글에는 정규식이 그대로 돌았다
(6,400자 숫자가 heavy 프로필 둘에서 5.3초 안팎 — 시도 3번에 16초). 승인(확인 032 보기 ①, 이슈 #254)을 받아 같은 패턴의 앞을 묶었다: 이메일은 앞 경계와 길이 한도(로컬 1–64자·도메인 한 칸 1–63자),
숫자 단위는 앞 경계와 자릿수 한도(퍼센트 정수부 1–9자, 가격의 앞선 숫자 열은 20자까지 — 용량 패턴은 앞 경계만 두고 정수부 상한을 두지 않는다: 앞 경계가 제곱 시간을 이미 닫아 상한이 필요 없고,
품질 그림자 도구의 옛 시험 셋('줄여도 안 줄여도 같은 규칙이 걸림'·'줄인 뒤에도 진짜 용량이 걸림')은 승인안의 9자와도 총괄이 처음 정한 20자와도 맞지 않는다). 숫자 단위의 앞 경계는 '바로 앞 글자가 숫자이거나, 그 앞 두 글자가 숫자와 점(가격은 숫자와 점·쉼표)이면 거기서 다시 시작하지 않는다'다 —
점·쉼표 앞이 숫자가 아니면(버전 표기 뒤·공백 없는 문장 끝 점 뒤) 시작을 허락해 옛 패턴처럼 잡는다(총괄 결정, 승인 요건 '정상 글의 판정은 같음'). 바뀐 곳은 blogger_ai_tools_ko·naver_life_tips_ko·blogger_practical_ko 의
같은 패턴뿐이다(영문 프로필은 영향 없음 — 아래 근거).

이 시험이 보는 것: ① 새 값이 프로필에 정확히 한 번씩 있고 옛 값은 없다 ② 정상 문장의 매치가 옛·새 패턴에서 한 글자까지 같다(표와 저장소 글·문서·시험 입력 전부) ③ 경계 입력 표와 모든 짧은 글자 조합(여섯 글자 이하)에서도
옛·새 패턴의 매치가 같다 — 점·쉼표·글자 바로 뒤에 붙은 숫자도 옛 패턴처럼 잡힌다 ④ 알려진 좁아짐(옛 패턴은 잡고 새 패턴은 안 잡는 것)이 문서에 적은 것과 같다 — 열 자리 넘는 퍼센트 숫자·가격의 스물한 자 넘는 숫자 열·64자 넘는 이메일 로컬 파트·
63자 넘는 도메인 칸(승인된 자릿수 상한)과, 소수부·천 단위 숫자의 한가운데에서 다시 시작하는 꼴. 용량은 숫자가 몇 자리든 옛 패턴처럼 걸리고 품질 그림자 도구가 숫자 연속을 줄여도 안 줄여도 같은 규칙이 걸린다
⑤ 병적 입력(한도 두 배 미만의 같은 글자 가득)의 시간이 상한 안이다. 시험 안의 반복은 모두 고정된 작은 표다(무한히 돌지 않는다).
"""
import itertools
import json
import re
import time
import unittest
from pathlib import Path

import _bootstrap
from pipeline import quality_shadow, registry
from test_gates_oversize import check, max_chars

ROOT = _bootstrap.ROOT
PROFILES = ROOT / "pipeline" / "profiles"
DOCS = ROOT / "docs"

# 옛 값(고치기 전 — main a39f2d6)과 새 값
OLD_EMAIL = r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+\.[A-Za-z]{2,}"
NEW_EMAIL = r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9\-]{1,63}\.[A-Za-z]{2,}"
OLD_PERCENT = r"\d+(?:\.\d+)?\s*(?:%|퍼센트|배)\s*(?:가\s*|나\s*|까지\s*)?(?:빨라|빠르|단축|줄어|줄었|절약|향상|개선|늘어|늘었|증가|높아|정확)"
NEW_PERCENT = r"(?<!\d)(?<!\d\.)\d{1,9}(?:\.\d+)?\s*(?:%|퍼센트|배)\s*(?:가\s*|나\s*|까지\s*)?(?:빨라|빠르|단축|줄어|줄었|절약|향상|개선|늘어|늘었|증가|높아|정확)"
OLD_PRICE = r"(?:월|연|한\s*달|매달|1\s*회)\s*\d[\d,.]*\s*(?:만\s*)?(?:원|달러|유로|엔)|\$\s*\d|\d[\d,.]*\s*(?:달러|USD)"
NEW_PRICE = r"(?:월|연|한\s*달|매달|1\s*회)\s*\d[\d,.]*\s*(?:만\s*)?(?:원|달러|유로|엔)|\$\s*\d|(?<!\d)(?<!\d[.,])\d[\d,.]{0,19}\s*(?:달러|USD)"
OLD_DOSE = r"\d+(?:\.\d+)?\s?(?:mg|mcg|μg|iu)(?![a-z])|밀리그램|마이크로그램"
NEW_DOSE = r"(?<!\d)(?<!\d\.)\d+(?:\.\d+)?\s?(?:mg|mcg|μg|iu)(?![a-z])|밀리그램|마이크로그램"        # 정수부 상한 없음 — 앞 경계만 옛 패턴에 더했다(아래 ShippedPatternsTest 의 줄임 불변 시험)

# 첫 시도의 단순 경계 — 앞이 숫자나 점(가격은 숫자·점·쉼표)이면 시작하지 않았다. 점 바로 뒤의 숫자가 옛 패턴과 달리 안 잡혔다(총괄이 정밀화를 지시한 이유). 아래 표가 이 경계를 걸러내는지 본다.
REFINED_BOUNDARY = {"percent": r"(?<!\d)(?<!\d\.)", "price": r"(?<!\d)(?<!\d[.,])", "dose": r"(?<!\d)(?<!\d\.)"}
PLAIN_BOUNDARY = {"percent": r"(?<![\d.])", "price": r"(?<![\d,.])", "dose": r"(?<![\d.])"}

PAIRS = {"email": (OLD_EMAIL, NEW_EMAIL), "percent": (OLD_PERCENT, NEW_PERCENT), "price": (OLD_PRICE, NEW_PRICE), "dose": (OLD_DOSE, NEW_DOSE)}
GUARDRAIL_KO = (("banned_patterns", "percent", "price", "email"), ("banned_topic_patterns", "dose"), ("body_banned_patterns", "dose"))
PLACES = {
    "blogger_ai_tools_ko": GUARDRAIL_KO,
    "naver_life_tips_ko": GUARDRAIL_KO,
    "blogger_practical_ko": (("banned_topic_patterns", "dose"), ("body_banned_patterns", "dose")),
}
UNTOUCHED = ("blogger_practical_en",)
FLAGS = re.IGNORECASE


def load(name):
    return json.loads((PROFILES / (name + ".json")).read_text(encoding="utf-8"))


def spans(pattern, text):
    return [(m.start(), m.end(), m.group()) for m in re.compile(pattern, FLAGS).finditer(text)]


class ValueTest(unittest.TestCase):
    def test_each_changed_pattern_is_the_new_value_exactly_once_and_the_old_value_is_gone(self):
        for name, places in PLACES.items():
            profile = load(name)
            for entry in places:
                key, kinds = entry[0], entry[1:]
                for kind in kinds:
                    old, new = PAIRS[kind]
                    with self.subTest(profile=name, list=key, kind=kind):
                        self.assertEqual(profile[key].count(new), 1)
                        self.assertNotIn(old, profile[key])

    def test_the_three_profiles_are_still_valid_and_compile(self):
        for name in PLACES:
            profile = load(name)
            self.assertEqual(registry.validate_profile(profile), [], name)

    def test_the_two_korean_ai_profiles_keep_the_same_guardrail_lists(self):
        """naver_life_tips_ko 의 가드레일 목록은 blogger_ai_tools_ko 와 한 글자도 다르지 않다(test_profiles_naver 가 지킨다) — 바꾼 것도 같다. 한국어 기본 프로필은 주제 목록과 본문 목록이 같다(test_guardrails)."""
        first, second, base = load("blogger_ai_tools_ko"), load("naver_life_tips_ko"), load("blogger_practical_ko")
        for key in ("banned_patterns", "banned_topic_patterns", "body_banned_patterns"):
            self.assertEqual(first[key], second[key], key)
        self.assertEqual(base["body_banned_patterns"], base["banned_topic_patterns"])

    def test_the_english_profile_keeps_its_own_dose_patterns_and_needs_no_change(self):
        """영문 프로필의 숫자 패턴은 앞이 낱말 경계(\\b)라 같은 숫자 연속에서 제곱 시간이 나지 않는다(BP2 의 측정 — 아래 SpeedTest 가 시간으로 확인한다). 그래서 이 묶음이 건드리지 않았다."""
        english = load("blogger_practical_en")
        flat = json.dumps(english, ensure_ascii=False)
        self.assertIn(r"\\b\\d+(?:\\.\\d+)?\\s?(?:mg|mcg|μg|iu)\\b", flat)                      # JSON 글자(백슬래시 둘씩)로 그대로 있다
        for new in (NEW_EMAIL, NEW_PERCENT, NEW_PRICE, NEW_DOSE):
            self.assertNotIn(new.replace("\\", "\\\\"), flat)


# ----------------------------------------------------------------------------
# 같은 매치: 정상 문장에서 옛·새 패턴이 같은 자리를 같은 글자로 잡는다
# ----------------------------------------------------------------------------
NORMAL_SENTENCES = (
    "문의는 hello@example.com 으로 보내 주세요.", "연락처: a.b+c@sub.example.co.kr, x-y_z@w-w.io 둘 다 됩니다.", "골뱅이(@) 기호를 눌러 보세요.", "메일 주소는 first.last@example.com 과 other@test.org 입니다.",
    "작업 속도가 30% 빨라집니다.", "정리 시간이 2배 줄었어요.", "3.5퍼센트 향상된다고 합니다.", "정확도가 99.9 % 정확해요.", "배터리가 30% 남았을 때 절전 모드를 켜세요.", "앱을 2배속으로 재생해 보세요.",
    "월 9,900원 요금제예요.", "한 달 3만 원이면 돼요.", "$5짜리 플랜이에요.", "1,234.56달러, 100 USD, 월9900원, 연 120만 원, 월 1회 점검하세요.", "한 달에 한 번 정리하세요.",
    "비타민 500mg 을 먹었다.", "0.5 mcg, 10 IU, 250μg 용량.", "5mgx 같은 낱말은 아닙니다.", "밀리그램 단위와 마이크로그램 단위를 헷갈리지 마세요.", "혈압약 5 mg/dl 수치.",
    "버전 1.2.3 설치 후 2024.11.24 에 재시작.", "전화 010-1234-5678 과 02-123-4567.", "총 12,345,678원과 1,000,000,000원.", "https://example.com/a-b_c?x=1 은 링크입니다.",
    "여러 줄\n30%\n빨라집니다\n그리고 월\n9,900원\n입니다.", "탭\t5\tmg 과 줄바꿈 5\nmg.", "", "숫자 없는 한글 문장입니다.", "a@b", "@", "1" * 9 + "mg " + "9" * 9 + "% 빨라",
)


def corpus_files():
    bases = [ROOT / "_posts", ROOT / "_blogger_drafts", ROOT / "_blogger_ko_drafts", ROOT / "_naver_drafts", DOCS]
    found = []
    for base in bases:
        if base.is_dir():
            found += sorted(path for path in base.rglob("*") if path.is_file() and path.suffix.lower() in (".md", ".html", ".txt", ".json", ".yml"))
    found += [ROOT / name for name in ("README.md", "HANDLER.md", "AGENTS.md", "AI_COLLAB.md", "WORKLOG.md") if (ROOT / name).is_file()]
    tests = ROOT / "tests"
    found += [tests / name for name in ("test_profile_ko_ai.py", "test_profiles_naver.py", "test_guardrails.py", "test_gates.py", "test_personal_expressions.py", "test_quality_gate.py") if (tests / name).is_file()]
    return found


class SameMatchesTest(unittest.TestCase):
    def test_old_and_new_patterns_match_the_same_spans_on_normal_sentences(self):
        for kind, (old, new) in PAIRS.items():
            for text in NORMAL_SENTENCES:
                with self.subTest(kind=kind, text=text[:40]):
                    self.assertEqual(spans(new, text), spans(old, text))

    def test_normal_sentences_are_really_caught_by_both(self):
        """표가 비어 있지 않다: 같은 매치라는 말이 '둘 다 아무것도 못 잡는다'로 비지 않도록 종류마다 잡히는 문장이 있다."""
        for kind, (old, new) in PAIRS.items():
            caught = [text for text in NORMAL_SENTENCES if spans(new, text)]
            self.assertGreaterEqual(len(caught), 3, kind)
            self.assertTrue(all(spans(old, text) for text in caught), kind)

    def test_old_and_new_patterns_match_the_same_spans_on_the_repository_corpus(self):
        """저장소 글(_posts·초안 폴더)·문서·시험 입력 전부에서 옛·새 패턴의 매치 집합이 같다. 다르면 '정상 문장의 매치는 같다'는 약속이 깨진 것이니 새 값을 다시 본다."""
        files = corpus_files()
        self.assertGreater(len(files), 100, "코퍼스가 비었다")
        compiled = {kind: (re.compile(old, FLAGS), re.compile(new, FLAGS)) for kind, (old, new) in PAIRS.items()}
        checked, differences = 0, []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")[:300000]
            for kind, (old_rx, new_rx) in compiled.items():
                old_spans = [(m.start(), m.end()) for m in old_rx.finditer(text)]
                new_spans = [(m.start(), m.end()) for m in new_rx.finditer(text)]
                checked += 1
                if old_spans != new_spans and len(differences) < 5:
                    only_old = [span for span in old_spans if span not in new_spans][:2]
                    differences.append("%s %s: 옛 패턴만 %s" % (path.relative_to(ROOT).as_posix(), kind, [text[a:b][:40] for a, b in only_old]))
        self.assertGreater(checked, 400)
        self.assertEqual(differences, [], "옛·새 패턴의 매치가 다른 곳이 있다")


# ----------------------------------------------------------------------------
# 경계 입력 표와 모든 짧은 글자 조합: 점·쉼표·글자 바로 뒤의 숫자, 문장 끝 점 뒤의 숫자, 열 자리 넘는 숫자열
# ----------------------------------------------------------------------------
CAP = "자릿수 상한"
RESTART = "숫자 한가운데에서 다시 시작"
BOUNDARY_SAME = (      # (종류, 글) — 옛·새 패턴의 매치가 한 글자까지 같아야 하는 입력. 총괄이 요구한 최소 입력(점·쉼표·글자 뒤 숫자, 소수·천 단위 표기, 단위 세 가지, 문장 끝 점+공백+숫자)을 모두 든다
    ("percent", "ver.5% 빨라"), ("percent", "3.5% 빨라"), ("percent", "v1.5배 줄었"), ("percent", "a.5% 빨라"), ("percent", ".5% 빨라"), ("percent", "x5% 빨라"),
    ("percent", "정리했다. 5% 빨라"), ("percent", "정리했다.5% 빨라"), ("percent", "1,5% 빨라"), ("percent", "x,5% 빨라"), ("percent", "3.5퍼센트 향상"), ("percent", "1" * 9 + "% 빨라"), ("percent", "1" * 9 + ".5% 빨라"),
    ("price", "1,000달러"), ("price", "3,500.5달러"), ("price", "ver.5달러"), ("price", "a,5달러"), ("price", "x5달러"), ("price", ".5달러"), ("price", ",5달러"), ("price", "1,2,3달러"), ("price", "5.5.5달러"),
    ("price", "정리했다. 5달러"), ("price", "정리했다.5달러"), ("price", "1" * 20 + "달러"), ("price", "월 9,900원"), ("price", "$5"), ("price", "1,000 USD"),
    ("dose", "5mg"), ("dose", "1.5mg"), ("dose", ".5mg"), ("dose", "ver.5mg"), ("dose", "end.5mg 을"), ("dose", "x1.5mg"), ("dose", "정리했다. 5mg"), ("dose", "정리했다.5mg"),
    ("dose", "1" * 9 + "mg"), ("dose", "1" * 9 + ".5mg"), ("dose", "1" * 10 + "mg"), ("dose", "1" * 10 + ".5mg"), ("dose", "9" * 20 + "mg"), ("dose", "1" * 21 + "mg"), ("dose", "1" * 21 + ".5mg"),
    ("dose", "9" * 100 + "mg"), ("dose", "9" * 300 + "mg 을 담았다"),      # 몇 자리든 + 용량 단위는 옛 패턴처럼 걸린다(정수부 상한 없음)
    ("dose", "0.5 mcg"), ("dose", "10 IU"),
)
BOUNDARY_DIFFERENT = (      # (종류, 글, 이유) — 옛 패턴은 잡고 새 패턴은 안 잡는 입력은 이것뿐이다(문서·보고서에 같은 목록이 있다)
    ("percent", "1" * 10 + "% 빨라", CAP), ("percent", "1" * 10 + ".5% 빨라", CAP), ("percent", "5.5.5% 빨라", RESTART), ("percent", "1.5.5% 빨라", RESTART), ("percent", "12.5.5배 줄었", RESTART),
    ("price", "1" * 21 + "달러", CAP), ("price", "1" * 25 + ",5달러", CAP), ("price", "1" * 25 + ".5달러", CAP),
    ("dose", "5.5.5mg", RESTART), ("dose", "1.5.5mg", RESTART),
)
GRID_ALPHABET = ("1", "5", ".", ",", "a", " ")          # 숫자 둘·점·쉼표·글자·공백
GRID_SUFFIX = {"percent": "% 빨라", "price": "달러", "dose": "mg"}
GRID_LENGTH = 6
INSIDE_A_NUMBER = {"percent": r"\d\.", "price": r"\d[.,]", "dose": r"\d\."}


def starts_inside_a_number(kind, text, start):
    """그 자리에서 시작하는 매치가 숫자의 한가운데에서 다시 시작한 것인가: 바로 앞 글자가 숫자이거나 그 앞 두 글자가 숫자와 점(가격은 점·쉼표)이다 — 새 패턴이 일부러 시작하지 않는 자리다."""
    return (start >= 1 and text[start - 1] in "0123456789") or re.fullmatch(INSIDE_A_NUMBER[kind], text[max(0, start - 2):start]) is not None


class BoundaryTableTest(unittest.TestCase):
    def test_boundary_inputs_match_exactly_like_the_old_patterns(self):
        for kind, text in BOUNDARY_SAME:
            old, new = PAIRS[kind]
            with self.subTest(kind=kind, text=text[:40]):
                self.assertTrue(spans(old, text), "표의 입력이 옛 패턴에도 안 잡히면 '같다'는 말이 비어 버린다")
                self.assertEqual(spans(new, text), spans(old, text))

    def test_inputs_that_still_differ_are_exactly_the_listed_ones_the_old_pattern_catches_and_the_new_one_does_not(self):
        for kind, text, why in BOUNDARY_DIFFERENT:
            old, new = PAIRS[kind]
            with self.subTest(kind=kind, text=text[:40], why=why):
                self.assertTrue(spans(old, text), "옛 패턴이 잡지 않는 입력은 '달라지는 입력' 목록에 두지 않는다")
                self.assertEqual(spans(new, text), [])

    def test_the_tables_hold_the_inputs_the_brief_names_and_enough_of_each_kind(self):
        for kind in ("percent", "price", "dose"):
            self.assertGreaterEqual(sum(1 for entry in BOUNDARY_SAME if entry[0] == kind), 10, kind)
        same = {text for _kind, text in BOUNDARY_SAME}
        for needle in ("ver.5% 빨라", "3.5% 빨라", "v1.5배 줄었", "1,000달러", "a.5% 빨라", ".5% 빨라", "x5% 빨라", "3,500.5달러", "5mg", "1.5mg", ".5mg", "ver.5mg", "정리했다. 5% 빨라", "정리했다. 5mg"):
            self.assertIn(needle, same, needle)
        different = {text for _kind, text, _why in BOUNDARY_DIFFERENT}
        self.assertIn("5.5.5% 빨라", different)
        self.assertTrue(any(text.startswith("1" * 10) for text in different), "열 자리 이상 숫자열이 목록에 없다")
        self.assertEqual({why for _kind, _text, why in BOUNDARY_DIFFERENT}, {CAP, RESTART})

    def test_the_table_is_not_empty_talk_the_plain_boundary_of_the_first_version_would_fail_it(self):
        """첫 시도의 단순 경계(앞이 숫자나 점이면 시작 금지)를 같은 패턴에 끼우면 표의 여러 입력에서 옛 패턴과 달라진다 — 표가 정밀화한 경계를 실제로 지키는 증거."""
        for kind in ("percent", "price", "dose"):
            old, new = PAIRS[kind]
            plain = new.replace(REFINED_BOUNDARY[kind], PLAIN_BOUNDARY[kind])
            self.assertEqual(new.count(REFINED_BOUNDARY[kind]), 1, kind)
            self.assertNotEqual(plain, new, kind)
            failing = [text for entry_kind, text in BOUNDARY_SAME if entry_kind == kind and spans(plain, text) != spans(old, text)]
            self.assertGreaterEqual(len(failing), 3, (kind, failing))


UNIT_MARK = {"percent": "(?:%|퍼센트|배)", "price": "(?:달러|USD)", "dose": "(?:mg|mcg|μg|iu)"}       # 앞 경계가 어떤 값이든 프로필에서 종류별 패턴을 찾는 표지


class ShippedPatternsTest(unittest.TestCase):
    """표를 프로필에 실제로 든 패턴(상수가 아니라 배포되는 값)에 그대로 건다 — 한 프로필만 옛 경계로 되돌아가도 여기서 빨개진다."""

    def shipped(self):
        for name, places in PLACES.items():
            profile = load(name)
            for entry in places:
                key, kinds = entry[0], entry[1:]
                for kind in kinds:
                    if kind in UNIT_MARK:
                        yield name, key, kind, [pattern for pattern in profile[key] if UNIT_MARK[kind] in pattern]

    def test_the_shipped_patterns_match_the_boundary_tables_like_the_old_patterns(self):
        seen = 0
        for name, key, kind, found in self.shipped():
            with self.subTest(profile=name, list=key, kind=kind):
                self.assertEqual(len(found), 1, "목록마다 같은 종류의 패턴이 하나여야 한다")
                pattern, old = found[0], PAIRS[kind][0]
                for entry_kind, text in BOUNDARY_SAME:
                    if entry_kind == kind:
                        self.assertEqual(spans(pattern, text), spans(old, text), text)
                for entry_kind, text, _why in BOUNDARY_DIFFERENT:
                    if entry_kind == kind:
                        self.assertEqual(spans(pattern, text), [], text)
                seen += 1
        self.assertEqual(seen, 10)       # blogger_ai_tools_ko·naver_life_tips_ko 는 퍼센트·가격(금지 패턴)과 용량(주제·본문 목록) 4곳씩, blogger_practical_ko 는 용량 2곳

    def test_the_shipped_patterns_are_the_same_value_in_all_the_places_they_appear(self):
        values = {}
        for name, key, kind, found in self.shipped():
            values.setdefault(kind, set()).update(found)
        for kind, patterns in values.items():
            self.assertEqual(len(patterns), 1, (kind, len(patterns)))

    def test_the_shipped_dosage_pattern_has_no_integer_part_cap_so_the_quality_shadow_clipping_changes_nothing(self):
        """용량 패턴은 정수부 길이 상한이 없다 — 앞 경계가 같은 숫자 연속의 한가운데에서 다시 시작하는 것을 막아 제곱 시간은 이미 닫혀 있어 상한이 필요 없고, 상한(승인안 9자·총괄이 처음 정한 20자)은 품질 그림자 도구
        (pipeline/quality_shadow.py — 읽기만 한다)의 옛 시험 셋과 맞지 않는다: 그 도구는 이 규칙에 넘기는 글에서 숫자 연속을 줄이면서 '줄여도 안 줄여도 같은 규칙이 걸린다' 와 '줄인 뒤에도 진짜 용량이 걸린다' 를 보장한다.
        그래서 20자리부터 6,399자리(한도 두 배 안의 가장 긴 숫자 연속)까지 숫자 + 용량 단위가 줄이기 전·후 모두 걸리고, 줄이기 전 글에서는 숫자 연속 전체를 먹는다."""
        clip = len(quality_shadow._clip_digit_runs("9" * 100))
        self.assertGreater(clip, 9)
        seen = 0
        for name, key, kind, found in self.shipped():
            if kind != "dose":
                continue
            with self.subTest(profile=name, list=key):
                self.assertEqual(len(found), 1)
                for digits in (clip, clip + 1, 25, 100, 300, 5000, 6399):
                    text = "이 제품은 " + "9" * digits + "mg 을 담았다."
                    clipped = quality_shadow._clip_digit_runs(text)
                    matches = spans(found[0], text)
                    self.assertEqual([m[2] for m in matches], ["9" * digits + "mg"], digits)               # 줄이기 전 글: 숫자 연속 전체 + 단위를 한 번에 먹는다
                    self.assertTrue(spans(found[0], clipped), digits)                                     # 줄인 뒤에도 걸린다
                    if digits <= 300:                                                                      # 옛 패턴은 숫자가 길면 제곱 시간이라(6,399자리에서 2초 넘게) 짧은 입력으로만 견준다
                        self.assertEqual(matches, spans(PAIRS["dose"][0], text), digits)
                seen += 1
        self.assertEqual(seen, 6)       # 용량 패턴이 있는 곳: ai·naver 의 주제·본문 목록 넷 + practical 의 둘

class GridTest(unittest.TestCase):
    def test_on_every_short_text_old_and_new_patterns_differ_only_where_a_match_would_restart_inside_a_number(self):
        """여섯 글자 이하의 모든 조합(숫자 1·5, 점, 쉼표, 글자 a, 공백 — 종류마다 55,986 개) 뒤에 단위를 붙인 글: 옛·새 매치가 다르면 옛 매치 가운데 하나가 숫자 한가운데에서 시작한 것이어야 한다(자릿수 상한은 이 길이에서 닿지 않는다).
        가격 패턴은 옛 패턴의 가장 왼쪽 시작이 숫자 열 전체를 먹기 때문에 어떤 입력에서도 다르지 않다."""
        for kind in ("percent", "price", "dose"):
            old, new = PAIRS[kind]
            old_rx, new_rx = re.compile(old, FLAGS), re.compile(new, FLAGS)
            suffix, differing, caught, unexplained = GRID_SUFFIX[kind], 0, 0, []
            for length in range(1, GRID_LENGTH + 1):
                for combo in itertools.product(GRID_ALPHABET, repeat=length):
                    text = "".join(combo) + suffix
                    old_spans = [(m.start(), m.end()) for m in old_rx.finditer(text)]
                    new_spans = [(m.start(), m.end()) for m in new_rx.finditer(text)]
                    caught += bool(old_spans)
                    if old_spans != new_spans:
                        differing += 1
                        if len(unexplained) < 5 and not any(starts_inside_a_number(kind, text, start) for start, _end in old_spans):
                            unexplained.append(text)
            with self.subTest(kind=kind):
                self.assertEqual(unexplained, [], "숫자 한가운데 다시 시작으로 설명되지 않는 차이")
                self.assertGreater(caught, 1000)
                if kind == "price":
                    self.assertEqual(differing, 0)
                else:
                    self.assertGreater(differing, 0)


# ----------------------------------------------------------------------------
# 알려진 좁아짐: 문서에 적은 것과 같은지(옛 패턴만 잡는 것)
# ----------------------------------------------------------------------------
class KnownNarrowingTest(unittest.TestCase):
    def verdict(self, kind, text):
        old, new = PAIRS[kind]
        return bool(spans(old, text)), bool(spans(new, text))

    def test_numbers_over_the_percent_or_price_cap_before_a_unit_are_no_longer_caught(self):
        """퍼센트는 정수부 열 자리부터, 가격은 앞선 숫자 열 스물한 자부터 걸리지 않는다(승인된 자릿수 상한). 용량은 상한이 없다 — 아래 시험."""
        self.assertEqual(self.verdict("percent", "1" * 9 + "% 빨라"), (True, True))
        self.assertEqual(self.verdict("percent", "1" * 10 + "% 빨라"), (True, False))
        self.assertEqual(self.verdict("price", "1" * 20 + "달러"), (True, True))
        self.assertEqual(self.verdict("price", "1" * 21 + "달러"), (True, False))

    def test_the_dosage_integer_part_has_no_cap_so_a_number_of_any_length_before_a_unit_is_caught_like_before(self):
        """용량 패턴은 정수부 길이 상한이 없다(앞 경계가 제곱 시간을 닫는다). 승인안의 9자·총괄이 처음 정한 20자는 품질 그림자 도구의 옛 시험 셋과 맞지 않았다. 몇 자리든 + 용량 단위는 옛 패턴처럼 걸린다."""
        for digits in (9, 10, 20, 21, 100, 300):
            self.assertEqual(self.verdict("dose", "1" * digits + "mg"), (True, True), digits)
            self.assertEqual(self.verdict("dose", "1" * digits + ".5mg"), (True, True), digits)

    def test_a_number_glued_right_after_a_dot_or_a_comma_is_caught_like_before(self):
        """숫자 바로 앞에 점(또는 가격의 앞선 숫자 열에서는 쉼표)이 붙은 꼴 — 버전 표기 뒤나 공백 없는 문장 끝 점 뒤에 곧바로 숫자가 오는 경우 — 도 옛 패턴처럼 잡힌다(BP3 총괄 결정: 정상 글의 판정은 같다).
        점·쉼표 앞이 숫자가 아니면 시작을 허락하고, 점·쉼표 앞이 숫자인 소수·천 단위 표기도 그대로 잡힌다."""
        for kind, text in (("percent", "ver.5% 빨라"), ("dose", "end.5mg 을"), ("price", "x,5달러"), ("price", "ver.5달러"), ("percent", "3.5퍼센트 향상"), ("dose", "0.5 mcg"), ("price", "1,234.56달러"),
                           ("percent", "정리했다. 30% 빨라"), ("dose", "정리했다. 5mg 을"), ("percent", "정리했다.30% 빨라"), ("dose", "정리했다.5mg 을")):
            self.assertEqual(self.verdict(kind, text), (True, True), text)

    def test_a_number_that_would_restart_in_the_middle_of_a_decimal_or_a_thousands_number_is_still_not_caught(self):
        """소수부·천 단위 숫자의 한가운데(바로 앞이 숫자, 또는 그 앞 두 글자가 숫자와 점 — 가격은 숫자와 점·쉼표)에서 숫자가 다시 시작하는 것만 막는다. 같은 숫자 덩어리의 시작 위치마다 다시 먹어 제곱 시간이 나는 바로 그 부분이다.
        이 길이의 입력에서 옛 패턴과 달라지는 것은 이것뿐이다(GridTest). 가격 패턴은 옛 패턴의 가장 왼쪽 시작이 숫자 열 전체를 먹어서 같다."""
        self.assertEqual(self.verdict("percent", "5.5.5% 빨라"), (True, False))
        self.assertEqual(self.verdict("dose", "5.5.5mg"), (True, False))
        self.assertEqual(self.verdict("price", "5.5.5달러"), (True, True))
        self.assertEqual(self.verdict("price", "1,2.3,4달러"), (True, True))

    def test_an_email_with_a_local_part_over_64_or_a_domain_label_over_63_is_no_longer_caught(self):
        self.assertEqual(self.verdict("email", "a" * 64 + "@example.com"), (True, True))
        self.assertEqual(self.verdict("email", "a" * 65 + "@example.com"), (True, False))
        self.assertEqual(self.verdict("email", "ab@" + "d" * 63 + ".com"), (True, True))
        self.assertEqual(self.verdict("email", "ab@" + "d" * 64 + ".com"), (True, False))

    def test_the_email_still_starts_at_the_beginning_of_its_run_not_in_the_middle(self):
        """앞 경계 덕에 같은 자리에서 시작한다: 로컬 파트 앞에 이 문자들이 이어져 있으면 그 덩어리 전체가 하나의 후보다(예전과 같은 매치 자리)."""
        for text in ("ver.hello@example.com", "-hello@example.com", "x+y%z@example.com", "hello@@example.com", "x@y@z.com"):
            self.assertEqual(spans(NEW_EMAIL, text), spans(OLD_EMAIL, text), text)


# ----------------------------------------------------------------------------
# 병적 입력의 시간(상한): 한도 두 배 미만의 같은 글자가 가득
# ----------------------------------------------------------------------------
def worst_texts(length):
    return {"digits": "1" * length, "digit-comma": "1," * (length // 2), "digit-dot": "1." * (length // 2), "hyphens": "-" * length, "letters": "a" * length, "alnum-hyphen": "a-" * (length // 2),
            "dots": "." * length, "letter-dot": "a." * (length // 2), "at-signs": "a@" * (length // 2), "percent": "1%" * (length // 2),
            "digit-comma-dot": "1,." * (length // 3), "digit-dot-comma": "1.," * (length // 3), "decimal-chain": "1.5" * (length // 3)}      # 뒤의 셋: 정밀화한 경계가 시작을 허락하는 꼴(쉼표·점 둘이 낀 숫자 열) — 가격 패턴의 20자 상한이 막는다(상한이 없으면 0.27초)


def best_of(rx, text, repeats=3):
    best = None
    for _ in range(repeats):
        started = time.perf_counter()
        rx.search(text)
        took = time.perf_counter() - started
        best = took if best is None else min(best, took)
    return best


PATTERN_LIMIT = 0.1        # 패턴 하나가 병적 입력 하나를 검색하는 데 걸리는 시간의 상한(초 — 세 번 중 가장 빠른 것). 바뀐 패턴은 0.002초 안팎, 같은 목록의 다른 패턴도 0.02초 안이다(측정 문턱 이하). 옛 패턴은 숫자 연속에서 1초를 넘었고, 상한 없는 가격 패턴은 점·쉼표 낀 열에서 0.27초다
GATE_LIMIT = 1.5           # check_post 한 번(한도 정확히 두 배 — 조기 반환을 막 피하는 가장 긴 입력)의 상한(초). 옛 코드는 heavy 프로필 숫자에서 5초 안팎


def slowest(patterns, texts):
    """목록의 모든 패턴을 모든 병적 입력에서 한 번씩 재어 가장 느린 칸 (초, 패턴 번호, 입력 이름) 을 돌려준다. 문턱을 넘은 칸만 세 번 중 가장 빠른 값으로 다시 재서 부하로 한 번 흔들린 것을 거른다
    (합계가 아니라 칸마다 본다 — 패턴 수가 많은 목록에서도 부하에 합이 흔들리지 않는다)."""
    worst = (0.0, -1, "")
    for index, pattern in enumerate(patterns):
        rx = re.compile(pattern, FLAGS)
        for label, text in texts.items():
            started = time.perf_counter()
            rx.search(text)
            took = time.perf_counter() - started
            if took >= PATTERN_LIMIT:
                took = best_of(rx, text)
            if took > worst[0]:
                worst = (took, index, label)
    return worst


class SpeedTest(unittest.TestCase):
    def test_each_changed_pattern_is_fast_on_every_pathological_text(self):
        for name, places in PLACES.items():
            n = 2 * max_chars(name) - 1
            texts = worst_texts(n)
            profile = load(name)
            for entry in places:
                key, kinds = entry[0], entry[1:]
                for kind in kinds:
                    old, new = PAIRS[kind]
                    rx = re.compile(new if new in profile[key] else old, FLAGS)        # 프로필에 실제로 든 값을 잰다(새 값이 아니면 옛 값 — 옛 값은 여기서 느려 빨개진다)
                    for label, text in texts.items():
                        with self.subTest(profile=name, list=key, kind=kind, text=label):
                            took = best_of(rx, text)
                            self.assertLess(took, PATTERN_LIMIT, "%s %s %s %s: %.2f초" % (name, key, kind, label, took))

    def test_every_pattern_of_each_changed_list_is_fast_on_all_pathological_texts(self):
        """바뀐 패턴만이 아니라 같은 목록의 나머지 패턴도 — 목록의 모든 패턴을 모든 병적 입력에서 재서 가장 느린 칸이 문턱 안이다."""
        for name, places in PLACES.items():
            n = 2 * max_chars(name) - 1
            texts = worst_texts(n)
            profile = load(name)
            for key in sorted({entry[0] for entry in places}):
                with self.subTest(profile=name, list=key):
                    took, index, label = slowest(profile[key], texts)
                    self.assertLess(took, PATTERN_LIMIT, "%s %s[%d] %s: %.2f초" % (name, key, index, label, took))

    def test_the_whole_gate_is_fast_on_the_longest_body_it_does_not_reject_early(self):
        """한도 두 배 정확히(조기 반환은 두 배를 넘어야 건다 — test_gates_oversize) 같은 글자 가득한 본문: 옛 코드는 heavy 프로필 숫자에서 5초 안팎이었다."""
        for name in PLACES:
            n = 2 * max_chars(name)
            for label in ("digits", "hyphens", "letters", "digit-comma", "alnum-hyphen"):
                body = worst_texts(n)[label][:n]
                with self.subTest(profile=name, text=label):
                    started = time.perf_counter()
                    result = check(name, body)
                    took = time.perf_counter() - started
                    self.assertLess(took, GATE_LIMIT, "%s %s: %.2f초" % (name, label, took))
                    self.assertTrue(set(result.codes()) - {"LEN_LONG"}, result.codes())      # 조기 반환이 아니다 — 길이 사유 말고 구조 사유 같은 전체 검사의 결과도 있다

    def test_the_english_profile_banned_lists_were_already_fast_so_they_were_left_alone(self):
        """영문 프로필의 금지 목록은 숫자 패턴 앞이 낱말 경계 표지라 같은 글자 연속에서 제곱 시간이 나지 않는다 — 그래서 이 묶음이 건드리지 않았다.
        (면제 취소·절 나누기 목록은 같은 절에 상담 구절이 있을 때만 돌고 이 묶음의 승인 범위 밖이라 여기서 보지 않는다 — 보고서의 남은 위험.)"""
        name = "blogger_practical_en"
        profile = load(name)
        n = 2 * max_chars(name) - 1
        for key in ("banned_topic_patterns", "body_banned_patterns"):
            took, index, label = slowest(profile[key], worst_texts(n))
            self.assertLess(took, PATTERN_LIMIT, "%s %s[%d] %s: %.2f초" % (name, key, index, label, took))


class DocumentTest(unittest.TestCase):
    DEFECTS = (DOCS / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
    ROOT_TEXT = (ROOT / "tests" / "test_gates_oversize.py").read_text(encoding="utf-8")

    def test_the_defect_row_d431_exists_once_with_six_cells_and_is_solved(self):
        rows = [line for line in self.DEFECTS.splitlines() if line.startswith("| **D-431** |")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].count("|"), 7)
        self.assertIn("**해결**", rows[0])
        for needle in ("BP-S1-5", "D-415", "blogger_ai_tools_ko", "naver_life_tips_ko", "blogger_practical_ko", "tests/test_profile_regex_bounds.py", "확인 032", "열 자리", "64자",
                       "점이나 쉼표 바로 뒤에 붙은 숫자", "시작을 허락해 옛 패턴처럼 잡는다", "승인된 자릿수 상한", "스물한 자", "소수부 한가운데에서 숫자가 다시 시작하는 꼴", "여섯 글자 이하의 모든 조합",
                       "용량 패턴은 앞 경계만(정수부 길이 상한을 두지 않는다)", "줄여도 안 줄여도 같은 규칙이 걸린다고 보장", "승인안의 9자에서 총괄 결정으로 달라졌다", "열 자리 넘는 퍼센트 숫자", "용량은 숫자가 몇 자리든 옛 패턴처럼 잡힌다",
                       "이 행이 닫은 제곱 시간은 금지 표현 정규식", "`body_safe_veto_patterns` 둘은 승인 범위 밖이라 묶지 않았고", "4,000자 1.18초·0.279초", "후속 T3 로 제안"):      # 마지막 넷: 면제 취소 패턴은 여전히 제곱이라는 한계(BP3 독립 검증 S 권고)
            self.assertIn(needle, rows[0], needle)
        for gone in ("퍼센트·용량 패턴은 앞 경계와 정수부 1–9자", "정수부 1–20자", "스물한 자리 넘는 용량 숫자", "열 자리 넘는 숫자 단위"):
            self.assertNotIn(gone, rows[0], gone)       # 용량 상한이 9 나 20 이었던 서술이 남지 않았다
        self.assertNotIn("숫자 바로 앞에 점(가격은 점이나 쉼표)이 붙은 꼴", rows[0])       # 첫 시도의 '점 바로 뒤 숫자는 안 잡힌다'는 설명이 남지 않았다
        self.assertNotIn(chr(126), rows[0])
        self.assertIsNone(re.search(r"https?://", rows[0]))

    def test_the_oversize_test_header_no_longer_says_the_profile_values_are_untouched(self):
        self.assertNotIn("프로필 JSON 의 정규식 값은 고치지 않았다", self.ROOT_TEXT)
        self.assertIn("D-431", self.ROOT_TEXT)


if __name__ == "__main__":
    unittest.main()
