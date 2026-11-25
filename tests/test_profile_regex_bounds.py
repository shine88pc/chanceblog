"""프로필 정규식 값 묶기(BP3, 감사 BP-S1-5 의 T3-3, 결함 D-431)와 그 앞 경계 정리(감사 BP-S2 R1, 확인 040 보기 ①, 결함 D-497) 시험. 네트워크 없이 돈다.

배경(D-415·D-431): 한국어 프로필 셋의 금지 표현 정규식 가운데 앞이 제한 없는 숫자 반복(`\\d+…`·`\\d[\\d,.]*…`)이거나 이메일 모양(`[A-Za-z0-9._%+\\-]+@…`)인 것은 같은 종류 글자가 길게 이어지면
시작 위치마다 다시 먹어 글 길이의 제곱으로 느려진다. D-415 가 길이 한도의 두 배를 넘는 글을 정규식 없이 탈락시켰지만 두 배 미만의 같은 글자 가득한 글에는 정규식이 그대로 돌았다
(6,400자 숫자가 heavy 프로필 둘에서 5.3초 안팎 — 시도 3번에 16초). M116(확인 032 보기 ①, 이슈 #254)은 같은 패턴의 앞을 묶었다: 앞 경계에 더해 이메일은 길이 한도(로컬 1–64자·도메인 한 칸 1–63자),
숫자 단위는 자릿수 한도(퍼센트 정수부 1–9자, 가격의 앞선 숫자 열 20자까지)를 걸고 점·쉼표 뒤 경계를 두었다. 그 상한은 옛 금지 판정보다 안전 쪽을 약하게 하는 입력(열 자리 이상 퍼센트·21자 이상 금액·65자 이상 메일·
'1.2.5%' 같은 점으로 이은 숫자)을 만들었고 속도에는 필요 없었다(2차 독립 감사 BP-S2 의 R1) — D-497(확인 040 보기 ①, 이슈 #271)가 걷어냈다.

지금 값(D-497): 퍼센트·용량은 옛 패턴 앞에 경계 `(?<!\\d)` 하나, 이메일은 옛 패턴 앞에 경계 `(?<![A-Za-z0-9._%+\\-])` 하나만 더했다 — 옛 패턴이 어떤 숫자 열(또는 메일 로컬 파트 열)의 한가운데에서 맞으면 그 열의 맨 앞에서도
같은 끝까지 맞으므로(뒤쪽 꼴이 같다) 열의 맨 앞에서만 시작해도 판정과 첫 맞은 자리가 옛 패턴과 같고, 시작 자리는 열마다 하나라 시간이 선형이다. 가격은 두 갈래다 — 짧은 열(맨 앞 숫자 뒤 63자 이하)은 M116 의 경계로,
긴 열은 열의 맨 앞(맨 앞의 점·쉼표 포함)에서 한 번만 시작한다(`price_two_way`): 한 갈래뿐인 상한 패턴은 64자를 넘는 열에서 옛 패턴보다 약해진다. 게이트는 search 의 맞음 여부와 첫 맞은 낱말(`found.group(0)`)만 쓴다 — 둘째 이후
매치는 쓰지 않으므로 판정 동치의 기준은 그 둘이다(가격 긴 열 갈래만 맞은 낱말에 맨 앞 점·쉼표가 더 붙을 수 있다). 바뀐 곳은 blogger_ai_tools_ko·naver_life_tips_ko·blogger_practical_ko 의 같은 패턴뿐이다(영문 프로필은 영향 없음 — 아래 근거).

이 시험이 보는 것: ① 지금 값이 프로필에 정확히 한 번씩 있고 옛 값과 M116 값은 없다 ② 정상 문장의 매치가 옛·지금 패턴에서 한 글자까지 같다(표와 저장소 글·문서·시험 입력 전부) ③ 경계 입력 표와 모든 짧은 글자 조합(여섯 글자 이하)에서도
옛·지금 패턴의 매치가 같다 — 점·쉼표·글자 바로 뒤에 붙은 숫자도 옛 패턴처럼 잡힌다 ④ M116 이 '더는 안 잡힌다'고 못박았던 입력(KnownNarrowingTest 의 옛 단언 — 열 자리 넘는 퍼센트·스물한 자 넘는 가격 열·64자 넘는 이메일 로컬 파트·63자 넘는 도메인 칸·
'5.5.5' 꼴)이 지금은 모두 옛 패턴처럼 잡힌다(NoWeakeningTest: 시작 자리를 상한 가장자리에 둔 가족·무작위 표본·가격 두 갈래 구조의 소범위 전수, AuditReproTest: 감사 재현 입력을 진짜 게이트 함수로). 용량은 숫자가 몇 자리든 옛 패턴처럼 걸리고
품질 그림자 도구가 숫자 연속을 줄여도 안 줄여도 같은 규칙이 걸린다 ⑤ 병적 입력(한도 두 배 미만의 같은 글자 가득)의 시간이 상한 안이다. 시험 안의 반복은 모두 고정된 작은 표나 고정 씨앗이다(무한히 돌지 않는다).
"""

import itertools
import json
import random
import re
import time
import unittest
from pathlib import Path

import _bootstrap
from pipeline import gates, quality_shadow, registry
from test_gates_oversize import check, max_chars

ROOT = _bootstrap.ROOT
PROFILES = ROOT / "pipeline" / "profiles"
DOCS = ROOT / "docs"

# 옛 값(M116 이전 — main 96540cf^, 처음 고치기 전 a39f2d6 과 같다)과 지금 값(D-497). 옛 값이 '금지 판정의 기준'이다 — 지금 값은 어떤 입력에서도 옛 값보다 약하면 안 된다.
OLD_EMAIL = r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+\.[A-Za-z]{2,}"
OLD_PERCENT = r"\d+(?:\.\d+)?\s*(?:%|퍼센트|배)\s*(?:가\s*|나\s*|까지\s*)?(?:빨라|빠르|단축|줄어|줄었|절약|향상|개선|늘어|늘었|증가|높아|정확)"
OLD_PRICE = r"(?:월|연|한\s*달|매달|1\s*회)\s*\d[\d,.]*\s*(?:만\s*)?(?:원|달러|유로|엔)|\$\s*\d|\d[\d,.]*\s*(?:달러|USD)"
OLD_DOSE = r"\d+(?:\.\d+)?\s?(?:mg|mcg|μg|iu)(?![a-z])|밀리그램|마이크로그램"

# M116(96540cf, 확인 032 보기 ①)이 승인받아 넣었던 값 — 자릿수 상한({1,9}·{0,19}·{1,64}·{1,63})과 숫자 한가운데 경계((?<!\d\.))가 옛 판정보다 약해지는 입력을 만들었고
# 속도에는 필요 없었다(2차 독립 감사 BP-S2 의 R1, 확인 040 보기 ①로 걷어냈다 — D-497). 이 값들은 이제 프로필에 없어야 하고, 아래 표가 '이 값은 놓치던' 입력을 보관한다.
M116_EMAIL = r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9\-]{1,63}\.[A-Za-z]{2,}"
M116_PERCENT = r"(?<!\d)(?<!\d\.)\d{1,9}(?:\.\d+)?\s*(?:%|퍼센트|배)\s*(?:가\s*|나\s*|까지\s*)?(?:빨라|빠르|단축|줄어|줄었|절약|향상|개선|늘어|늘었|증가|높아|정확)"
M116_PRICE = r"(?:월|연|한\s*달|매달|1\s*회)\s*\d[\d,.]*\s*(?:만\s*)?(?:원|달러|유로|엔)|\$\s*\d|(?<!\d)(?<!\d[.,])\d[\d,.]{0,19}\s*(?:달러|USD)"
M116_DOSE = r"(?<!\d)(?<!\d\.)\d+(?:\.\d+)?\s?(?:mg|mcg|μg|iu)(?![a-z])|밀리그램|마이크로그램"

# 지금 값. 퍼센트·용량·이메일은 옛 패턴에 '앞 경계 하나'만 더했다 — 옛 패턴이 어떤 숫자 열(또는 메일 로컬 파트 열)의 한가운데에서 맞으면 그 열의 맨 앞에서도 같은 끝까지 맞으므로
# (같은 뒤쪽 꼴) 열의 맨 앞에서만 시작해도 판정이 같고, 시작 자리는 열마다 하나라 시간이 선형이다. 가격은 두 갈래다 — 짧은 열(맨 앞 숫자 뒤 63자 이하)은 M116 의 앞 경계로,
# 긴 열(64자 이상)은 열의 맨 앞(맨 앞의 점·쉼표 포함)에서 한 번만 시작한다. 한 갈래뿐인 상한 패턴({0,63})은 64자를 넘는 열이 옛 패턴보다 약해진다(아래 시험이 그 입력을 든다).
PRICE_HEAD = r"(?:월|연|한\s*달|매달|1\s*회)\s*\d[\d,.]*\s*(?:만\s*)?(?:원|달러|유로|엔)|\$\s*\d|"
PRICE_UNIT = r"\s*(?:달러|USD)"
PRICE_CAP = 63


def price_two_way(cap):
    """가격 패턴의 두 갈래 구조(cap 은 짧은 열의 맨 앞 숫자 뒤 글자 수 상한). 작은 cap 으로 만든 것을 전수 시험에 쓴다."""
    return PRICE_HEAD + r"(?<!\d)(?<!\d[.,])\d[\d,.]{0,%d}" % cap + PRICE_UNIT + "|" + r"(?<![\d,.])[,.]*\d[\d,.]{%d,}" % (cap + 1) + PRICE_UNIT


NEW_EMAIL = r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+\.[A-Za-z]{2,}"
NEW_PERCENT = r"(?<!\d)\d+(?:\.\d+)?\s*(?:%|퍼센트|배)\s*(?:가\s*|나\s*|까지\s*)?(?:빨라|빠르|단축|줄어|줄었|절약|향상|개선|늘어|늘었|증가|높아|정확)"
NEW_PRICE = price_two_way(PRICE_CAP)
NEW_DOSE = r"(?<!\d)\d+(?:\.\d+)?\s?(?:mg|mcg|μg|iu)(?![a-z])|밀리그램|마이크로그램"        # 정수부 상한 없음 — 앞 경계 하나만 옛 패턴에 더했다(아래 ShippedPatternsTest 의 줄임 불변 시험)

# 첫 시도의 단순 경계 — 앞이 숫자나 점(가격은 숫자·점·쉼표)이면 시작하지 않았다. 점 바로 뒤의 숫자가 옛 패턴과 달리 안 잡혔다(총괄이 정밀화를 지시한 이유). 아래 표가 이 경계를 걸러내는지 본다.
# 지금 값의 경계: 퍼센트·용량은 (?<!\d) 하나, 가격 짧은 열은 M116 의 두 줄((?<!\d)(?<!\d[.,])).
REFINED_BOUNDARY = {"percent": r"(?<!\d)", "price": r"(?<!\d)(?<!\d[.,])", "dose": r"(?<!\d)"}
PLAIN_BOUNDARY = {"percent": r"(?<![\d.])", "price": r"(?<![\d,.])", "dose": r"(?<![\d.])"}

PAIRS = {"email": (OLD_EMAIL, NEW_EMAIL), "percent": (OLD_PERCENT, NEW_PERCENT), "price": (OLD_PRICE, NEW_PRICE), "dose": (OLD_DOSE, NEW_DOSE)}
M116_VALUES = {"email": M116_EMAIL, "percent": M116_PERCENT, "price": M116_PRICE, "dose": M116_DOSE}
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
                        self.assertNotIn(M116_VALUES[kind], profile[key])       # 자릿수 상한이 든 M116 값으로 되돌아가지 않았다(D-497)

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
    ("email", "hello@example.com"), ("email", "a.b+c@sub.example.co.kr"), ("email", "ver.hello@example.com"), ("email", "-hello@example.com"), ("email", "x+y%z@example.com"), ("email", "x@@y@z.com"),
    ("email", "x@y@z.com"), ("email", "a" * 64 + "@example.com"), ("email", "ab@" + "d" * 63 + ".com"), ("email", "문의: hello@example.com 으로"), ("email", "(a_b@c-d.io)"),
    # 재작업(검증 Q 권고-2 — 변이 Q52·Q56·Q59·Q60·Q61·Q62 가 살아남던 곳): 단위 바로 뒤에 숫자·슬래시가 붙은 꼴((?![a-z]) 는 영문자만 막는다)·단위와 낱말·조사와 낱말 사이 공백 둘·가격 첫 갈래의 만 뒤 공백 둘과 유로·엔·500자 넘는 열
    ("dose", "5mg2"), ("dose", "10IU3"), ("dose", "5mg/dl"), ("dose", "5mcg2"), ("dose", "2μg3"),
    ("percent", "30%  빨라"), ("percent", "30%가  빨라"), ("percent", "30%까지  빨라"), ("percent", "30  퍼센트  나  단축"), ("percent", "2배  줄었"),
    ("price", "연 3만  원"), ("price", "월 5유로"), ("price", "한 달 3만  원"), ("price", "매달 2,000엔"), ("price", "9" * 600 + "달러"), ("price", "9" * 300 + "," + "9" * 300 + " USD"),
    # 재작업 2차(독립 확인 D 권고-2 — 변이 D20·D25·D27 이 살아남던 곳): 퍼센트 낱말 열세 개 모두(낱말마다 따로 빠져도 잡히도록 — 절약·개선·늘어·늘었·증가·높아가 패턴 상수 밖에 한 번도 안 나왔다),
    # 가격 첫 갈래 머리의 '1회'(공백 있는 꼴 포함)와 둘째 갈래의 '$ 5'(공백이 낀 꼴), 머리와 금액·금액과 '원' 사이의 공백 둘
    ("percent", "2배 빨라"), ("percent", "2배 빠르"), ("percent", "2배 단축"), ("percent", "2배 줄어"), ("percent", "2배 줄었"), ("percent", "2배 절약"), ("percent", "2배 향상"),
    ("percent", "2배 개선"), ("percent", "2배 늘어"), ("percent", "2배 늘었"), ("percent", "2배 증가"), ("percent", "2배 높아"), ("percent", "2배 정확"),
    ("price", "1회 5,000원"), ("price", "1 회 5,000원"), ("price", "$ 5"), ("price", "$  5"), ("price", "월  5,000원"), ("price", "월 5,000  원"),
    ("price", "월 1,234.56원"), ("price", "연 3.5만 원"), ("price", "한달 5,000원"),        # 첫 갈래의 금액에 소수점이 낀 꼴(변이 H04: 금액 글자 모임에서 점을 뺌 — 점은 셋째 갈래(달러·USD)에서만 지켜지고 있었다)
)
FORMER_NARROWING = (      # (종류, 글, 이유) — M116 이 승인받아 넣은 값은 놓치고 옛 패턴은 잡던 입력(M116 시험이 '더는 안 잡힌다'고 못박았던 목록 + 감사 BP-S2 R1 의 재현 입력). 지금 값은 모두 옛 패턴처럼 잡는다(D-497).
    ("percent", "1" * 10 + "% 빨라", CAP), ("percent", "1" * 10 + ".5% 빨라", CAP), ("percent", "5.5.5% 빨라", RESTART), ("percent", "1.5.5% 빨라", RESTART), ("percent", "12.5.5배 줄었", RESTART),
    ("percent", "새 설정 이후 속도가 1.2.5% 빨라졌습니다", RESTART), ("percent", "처리 시간이 1234567890% 단축되었습니다", CAP), ("percent", "9" * 100 + "% 빨라", CAP),
    ("price", "1" * 21 + "달러", CAP), ("price", "1" * 25 + ",5달러", CAP), ("price", "1" * 25 + ".5달러", CAP), ("price", "가격은 " + "9" * 21 + " 달러입니다", CAP),
    ("dose", "5.5.5mg", RESTART), ("dose", "1.5.5mg", RESTART), ("dose", "하루 1.2.5mg 을 드세요", RESTART),
    ("email", "a" * 65 + "@example.com", CAP), ("email", "ab@" + "d" * 64 + ".com", CAP), ("email", "문의: user@" + "a" * 64 + ".com", CAP), ("email", "문의: " + "a" * 65 + "@example.com", CAP), ("email", "a" * 200 + "@example.com", CAP),
)
GRID_ALPHABET = ("1", "5", ".", ",", "a", " ")          # 숫자 둘·점·쉼표·글자·공백
GRID_SUFFIX = {"percent": "% 빨라", "price": "달러", "dose": "mg"}
GRID_LENGTH = 6
EMAIL_GRID_ALPHABET = ("a", "1", ".", "@", "-", " ")    # 메일 로컬 파트·골뱅이·도메인 글자·점·하이픈·공백
EMAIL_GRID_SUFFIX = ".io"
EMAIL_GRID_LENGTH = 6


class BoundaryTableTest(unittest.TestCase):
    def test_boundary_inputs_match_exactly_like_the_old_patterns(self):
        for kind, text in BOUNDARY_SAME:
            old, new = PAIRS[kind]
            with self.subTest(kind=kind, text=text[:40]):
                self.assertTrue(spans(old, text), "표의 입력이 옛 패턴에도 안 잡히면 '같다'는 말이 비어 버린다")
                self.assertEqual(spans(new, text), spans(old, text))

    def test_the_inputs_the_m116_values_missed_are_caught_exactly_like_the_old_patterns(self):
        """M116 이 '더는 안 잡힌다'고 못박았던 입력(옛 시험은 새 패턴이 [] 라고 단언했다)이 이제는 모두 옛 패턴처럼 잡힌다 — 한 글자까지 같은 자리. 목록이 빈말이 아니도록 M116 값은 실제로 놓친다."""
        for kind, text, why in FORMER_NARROWING:
            old, new = PAIRS[kind]
            with self.subTest(kind=kind, text=text[:40], why=why):
                self.assertTrue(spans(old, text), "옛 패턴이 잡지 않는 입력은 이 목록에 두지 않는다")
                self.assertEqual(spans(M116_VALUES[kind], text), [], "M116 값이 이 입력을 잡으면 목록이 빈말이다")
                self.assertEqual(spans(new, text), spans(old, text))

    def test_the_tables_hold_the_inputs_the_brief_names_and_enough_of_each_kind(self):
        for kind in ("percent", "price", "dose"):
            self.assertGreaterEqual(sum(1 for entry in BOUNDARY_SAME if entry[0] == kind), 10, kind)
        self.assertGreaterEqual(sum(1 for entry in BOUNDARY_SAME if entry[0] == "email"), 8)
        same = {text for _kind, text in BOUNDARY_SAME}
        for needle in ("ver.5% 빨라", "3.5% 빨라", "v1.5배 줄었", "1,000달러", "a.5% 빨라", ".5% 빨라", "x5% 빨라", "3,500.5달러", "5mg", "1.5mg", ".5mg", "ver.5mg", "정리했다. 5% 빨라", "정리했다. 5mg", "5mg2", "10IU3", "5mg/dl", "30%  빨라", "30%가  빨라", "연 3만  원", "월 5유로", "2배 절약", "2배 개선", "2배 늘어", "2배 늘었", "2배 증가", "2배 높아", "1회 5,000원", "1 회 5,000원", "$ 5", "월 1,234.56원"):
            self.assertIn(needle, same, needle)
        self.assertIn("9" * 600 + "달러", same, "500자 넘는 가격 열(긴 열 갈래의 위쪽 상한 변이를 잡는다)")
        former = {text for _kind, text, _why in FORMER_NARROWING}
        self.assertIn("5.5.5% 빨라", former)
        self.assertTrue(any(text.startswith("1" * 10) for text in former), "열 자리 이상 숫자열이 목록에 없다")
        self.assertEqual({why for _kind, _text, why in FORMER_NARROWING}, {CAP, RESTART})
        for kind in ("percent", "price", "dose", "email"):
            self.assertGreaterEqual(sum(1 for entry in FORMER_NARROWING if entry[0] == kind), 3, kind)

    def test_the_table_is_not_empty_talk_the_plain_boundary_of_the_first_version_would_fail_it(self):
        """첫 시도의 단순 경계(앞이 숫자나 점이면 시작 금지)를 같은 패턴에 끼우면 표의 여러 입력에서 옛 패턴과 달라진다 — 표가 정밀화한 경계를 실제로 지키는 증거."""
        for kind in ("percent", "price", "dose"):
            old, new = PAIRS[kind]
            plain = new.replace(REFINED_BOUNDARY[kind], PLAIN_BOUNDARY[kind])
            self.assertEqual(new.count(REFINED_BOUNDARY[kind]), 1, kind)
            self.assertNotEqual(plain, new, kind)
            failing = [text for entry_kind, text in BOUNDARY_SAME if entry_kind == kind and spans(plain, text) != spans(old, text)]
            self.assertGreaterEqual(len(failing), 3, (kind, failing))


UNIT_MARK = {"percent": "(?:%|퍼센트|배)", "price": "(?:달러|USD)", "dose": "(?:mg|mcg|μg|iu)", "email": "@[A-Za-z0-9\\-]"}       # 앞 경계가 어떤 값이든 프로필에서 종류별 패턴을 찾는 표지


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
                for entry_kind, text, _why in FORMER_NARROWING:
                    if entry_kind == kind:
                        self.assertEqual(spans(pattern, text), spans(old, text), text)       # M116 값이 놓치던 입력도 프로필의 값은 옛 패턴처럼 잡는다(옛 시험은 [] 를 단언했다)
                seen += 1
        self.assertEqual(seen, 12)       # blogger_ai_tools_ko·naver_life_tips_ko 는 퍼센트·가격·이메일(금지 패턴)과 용량(주제·본문 목록) 5곳씩, blogger_practical_ko 는 용량 2곳

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
    def test_on_every_short_text_old_and_new_patterns_match_exactly_the_same_spans(self):
        """여섯 글자 이하의 모든 조합(숫자 1·5, 점, 쉼표, 글자 a, 공백 — 종류마다 55,986 개) 뒤에 단위를 붙인 글: 옛·새 매치가 한 글자까지 같다 — 옛 시험은 퍼센트·용량에서 '다른 입력이 있어야 한다'
        (숫자 한가운데에서 다시 시작하는 꼴만 달라진다)고 단언했지만, 앞 경계를 하나만 두면 다른 입력이 없다(D-497). 가격 패턴은 M116 때도 없었다."""
        for kind in ("percent", "price", "dose"):
            old, new = PAIRS[kind]
            old_rx, new_rx = re.compile(old, FLAGS), re.compile(new, FLAGS)
            suffix, differing, caught, examples = GRID_SUFFIX[kind], 0, 0, []
            for length in range(1, GRID_LENGTH + 1):
                for combo in itertools.product(GRID_ALPHABET, repeat=length):
                    text = "".join(combo) + suffix
                    old_spans = [(m.start(), m.end()) for m in old_rx.finditer(text)]
                    new_spans = [(m.start(), m.end()) for m in new_rx.finditer(text)]
                    caught += bool(old_spans)
                    if old_spans != new_spans:
                        differing += 1
                        if len(examples) < 5:
                            examples.append(text)
            with self.subTest(kind=kind):
                self.assertGreater(caught, 1000)
                self.assertEqual(differing, 0, "옛 패턴과 맞은 자리가 다른 입력: %s" % examples)

    def test_on_every_short_mail_like_text_old_and_new_patterns_agree_on_the_verdict_and_the_first_match(self):
        """메일 모양(로컬 글자·골뱅이·점·하이픈·공백의 모든 여섯 글자 이하 조합 + '.io')도 같다. 판정(search)과 첫 맞은 자리가 같고, 둘째 이후 매치는 보지 않는다 — 앞 경계가 앞선 매치 끝에서
        다시 시작하는 것을 막으므로 둘째 이후의 목록은 달라질 수 있다(게이트는 search 만 쓴다)."""
        old_rx, new_rx = re.compile(OLD_EMAIL, FLAGS), re.compile(NEW_EMAIL, FLAGS)
        caught, differing, examples = 0, 0, []
        for length in range(1, EMAIL_GRID_LENGTH + 1):
            for combo in itertools.product(EMAIL_GRID_ALPHABET, repeat=length):
                text = "".join(combo) + EMAIL_GRID_SUFFIX
                old_match, new_match = old_rx.search(text), new_rx.search(text)
                caught += bool(old_match)
                if (old_match and old_match.span()) != (new_match and new_match.span()):
                    differing += 1
                    if len(examples) < 5:
                        examples.append(text)
        self.assertGreater(caught, 1000)
        self.assertEqual(differing, 0, "옛 패턴과 판정이나 첫 맞은 자리가 다른 입력: %s" % examples)


# ----------------------------------------------------------------------------
# 알려진 좁아짐이었던 것: M116 이 승인받아 넣은 자릿수 상한과 숫자 한가운데 경계가 만들던 좁아짐은 D-497 로 모두 없어졌다 — 옛 시험은 (옛 패턴 맞음, 새 패턴 안 맞음)을 못박았고
# 지금은 (맞음, 맞음)을 못박는다(옛 단언이 막던 것 — 9자리·20자리·64자 이하·점 바로 뒤 숫자 등 — 은 그대로 막고, 상한을 넘던 입력이 더해졌다)
# ----------------------------------------------------------------------------
class KnownNarrowingTest(unittest.TestCase):
    def verdict(self, kind, text):
        old, new = PAIRS[kind]
        return bool(spans(old, text)), bool(spans(new, text))

    def test_numbers_over_the_old_percent_or_price_cap_before_a_unit_are_caught_like_before(self):
        """퍼센트는 정수부가 몇 자리든, 가격은 앞선 숫자 열이 몇 자리든 옛 패턴처럼 걸린다(M116 의 정수부 9자·앞선 열 20자 상한은 없어졌다). 상한 안(9자·20자)은 전과 같이 걸린다."""
        self.assertEqual(self.verdict("percent", "1" * 9 + "% 빨라"), (True, True))
        self.assertEqual(self.verdict("price", "1" * 20 + "달러"), (True, True))
        for digits in (10, 11, 20, 21, 63, 64, 65, 100, 300):
            self.assertEqual(self.verdict("percent", "1" * digits + "% 빨라"), (True, True), digits)
            self.assertEqual(self.verdict("percent", "1" * digits + ".5% 빨라"), (True, True), digits)
        for digits in (21, 25, 62, 63, 64, 65, 66, 100, 300):
            self.assertEqual(self.verdict("price", "1" * digits + "달러"), (True, True), digits)
            self.assertEqual(self.verdict("price", "1" * digits + " USD"), (True, True), digits)
            self.assertEqual(self.verdict("price", "1" * digits + ",5달러"), (True, True), digits)
            self.assertEqual(self.verdict("price", "1," * (digits // 2) + "달러"), (True, True), digits)

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

    def test_a_number_that_would_restart_in_the_middle_of_a_decimal_or_a_thousands_number_is_caught_like_before(self):
        """소수부·천 단위 숫자 뒤쪽 조각('5.5.5' 의 끝 '5.5' 처럼 앞이 숫자와 점인 자리에서 다시 시작하는 꼴)도 옛 패턴처럼 잡힌다 — M116 의 (?<!\\d\\.) 는 이것을 막았고(옛 시험은 (True, False)),
        지금은 바로 앞 글자가 숫자일 때만 시작하지 않는다. 같은 숫자 덩어리의 맨 앞에서 시작해도 같은 끝까지 맞으므로 판정이 같다. 가격 패턴은 M116 때도 같았다."""
        self.assertEqual(self.verdict("percent", "5.5.5% 빨라"), (True, True))
        self.assertEqual(self.verdict("percent", "1.5.5% 빨라"), (True, True))
        self.assertEqual(self.verdict("dose", "5.5.5mg"), (True, True))
        self.assertEqual(self.verdict("dose", "1.5.5mg"), (True, True))
        self.assertEqual(self.verdict("price", "5.5.5달러"), (True, True))
        self.assertEqual(self.verdict("price", "1,2.3,4달러"), (True, True))

    def test_an_email_with_a_local_part_over_64_or_a_domain_label_over_63_is_caught_like_before(self):
        """이메일 로컬 파트·도메인 칸의 길이 상한(64·63)은 없어졌다 — 옛 시험은 65자·64자가 (True, False) 라고 못박았다. 64·63 이하는 전과 같이 걸린다."""
        self.assertEqual(self.verdict("email", "a" * 64 + "@example.com"), (True, True))
        self.assertEqual(self.verdict("email", "ab@" + "d" * 63 + ".com"), (True, True))
        for length in (65, 66, 100, 200, 300):
            self.assertEqual(self.verdict("email", "a" * length + "@example.com"), (True, True), length)
            self.assertEqual(self.verdict("email", "ab@" + "d" * length + ".com"), (True, True), length)

    def test_the_email_still_starts_at_the_beginning_of_its_run_not_in_the_middle(self):
        """앞 경계 덕에 같은 자리에서 시작한다: 로컬 파트 앞에 이 문자들이 이어져 있으면 그 덩어리 전체가 하나의 후보다(예전과 같은 매치 자리)."""
        for text in ("ver.hello@example.com", "-hello@example.com", "x+y%z@example.com", "hello@@example.com", "x@y@z.com"):
            self.assertEqual(spans(NEW_EMAIL, text), spans(OLD_EMAIL, text), text)


# ----------------------------------------------------------------------------
# 약해지는 입력 0(D-497): 프로필에 든 지금 값은 어떤 입력에서도 옛 패턴보다 약하지 않다 — 시작 자리를 긴 열 가장자리에 둔 가족·무작위 표본·가격 두 갈래 구조의 소범위 전수
# (짧은 글자 조합 전수는 GridTest 가 맡는다). 판정은 search 의 맞음 여부와 첫 맞은 자리다 — 게이트는 이 둘만 쓴다(둘째 이후 매치는 쓰지 않는다).
# ----------------------------------------------------------------------------
SAMPLE_SEED = 20261125
SAMPLE_COUNT = 8000
PRICE_LONG_RUNS = (330, 600)        # 가격 열이 300자를 넘는 꼴 — 가끔(3%) 낸다: 긴 열 갈래의 위쪽 상한을 두는 변이({64,500} 등)는 500자 넘는 열이 있어야 잡힌다
RUN_LENGTHS = (1, 2, 3, 9, 10, 11, 19, 20, 21, 62, 63, 64, 65, 66, 100, 130)       # M116 의 상한(9·19·20·63·64)과 지금 가격 짧은 열 상한(63)의 양쪽 가장자리를 모두 든다
PRICE_SMALL_CAP_TOKENS = ("1", ".", ",", " ", "x", "달러")


def shipped_pattern(kind):
    """프로필에 실제로 든 종류별 패턴 하나(다른 프로필·목록에서도 같은 값이라는 것은 ShippedPatternsTest 가 지킨다)."""
    profile = load("blogger_ai_tools_ko")
    key = "banned_topic_patterns" if kind == "dose" else "banned_patterns"
    found = [pattern for pattern in profile[key] if UNIT_MARK[kind] in pattern]
    assert len(found) == 1, (kind, len(found))
    return found[0]


def first_span(rx, text):
    match = rx.search(text)
    return match.span() if match else None


def explained_price_difference(text, old_span, new_span):
    """가격 긴 열 갈래가 만드는 단 하나의 자리 차이: 새 맞은 자리가 열의 맨 앞(맨 앞의 점·쉼표 포함)에서 시작하고 끝은 같다 — 사유 문구에 보이는 낱말에 맨 앞 점·쉼표가 더 붙을 뿐 판정은 같다."""
    return new_span[1] == old_span[1] and new_span[0] < old_span[0] and set(text[new_span[0]:old_span[0]]) <= set(",.")


def random_texts(kind, seed, count):
    """종류별 무작위 글(결정적): 숫자 덩어리·점·쉼표·글자가 섞이고, 일부는 M116 상한의 양쪽 가장자리 길이의 긴 열을 낀다. 가격은 숫자·점·쉼표로만 된 열(맨 앞 점·쉼표 0–3개 또는 70개)도 낸다."""
    rng = random.Random(seed)

    def digits(n):
        return "".join(rng.choice("0123456789") for _ in range(n))

    def number():
        parts = []
        for _ in range(rng.randint(1, 4)):
            roll = rng.random()
            parts.append(digits(rng.randint(1, 4)) if roll < 0.5 else rng.choice(".,") if roll < 0.85 else rng.choice(("a", "v", "ver.", " ", "-", "x")))
        if rng.random() < 0.15:
            parts.append(digits(rng.choice(RUN_LENGTHS)))
        return "".join(parts)

    def class_run():
        lead = "".join(rng.choice(",.") for _ in range(rng.choice((0, 0, 0, 1, 2, 3, 70))))
        length = rng.choice(PRICE_LONG_RUNS) if rng.random() < 0.03 else rng.choice(RUN_LENGTHS)
        body = "".join(rng.choice("0123456789") if rng.random() < 0.7 else rng.choice(",.") for _ in range(length))
        tail = "".join(rng.choice(",.") for _ in range(rng.choice((0, 0, 1, 2, 70))))
        return lead + body + tail

    def mail():
        local = "".join(rng.choice("abcXYZ019._%+-") for _ in range(rng.choice((1, 3, 10, 63, 64, 65, 66, 100))))
        label = "".join(rng.choice("abcXYZ01-") for _ in range(rng.choice((1, 3, 62, 63, 64, 65, 100))))
        return rng.choice(("", " ", "메일 ", "(", "-", "a", ".", "x@")) + local + "@" + label + rng.choice((".com", ".c", ".io", ".co.kr")) + rng.choice(("", " ", ".", "한글"))

    for _ in range(count):
        prefix = rng.choice(("", "약 ", "(", "ver.", "v", "1.", "1.2.", "x-", "No.", "1,", ".", ",", ".."))
        if kind == "percent":
            yield prefix + number() + rng.choice(("%", "퍼센트", "배", " %", "％")) + rng.choice(("", " ", "  ")) + rng.choice(("빨라", "빠르", "단축", "줄어", "가 빨라", "까지 빨라", "가  빨라", "나  단축", "까지  빨라", "줄었", "절약", "향상", "개선", "늘어", "늘었", "증가", "높아", "정확", "x"))
        elif kind == "dose":
            yield prefix + number() + rng.choice(("mg", "mcg", "μg", "iu", " mg", " IU", "mgx", "밀리그램", "마이크로그램")) + rng.choice(("", " 복용", "2", "/dl", ".", "한"))
        elif kind == "price":
            yield prefix + (class_run() if rng.random() < 0.4 else number()) + rng.choice(("", " ", "  ", "\n", "\t")) + rng.choice(("달러", "USD", " 달러", "usd", "$")) + rng.choice(("", " 입니다"))
        else:
            yield mail()


class NoWeakeningTest(unittest.TestCase):
    def assert_same_verdict(self, kind, old_rx, new_rx, text, label=""):
        """옛 패턴이 맞는 글은 새 패턴도 맞고(약해짐 0), 옛 패턴이 안 맞는 글은 새 패턴도 안 맞으며(더 엄격 0), 첫 맞은 자리는 같다 — 가격의 긴 열 갈래가 만드는 알려진 자리 차이는 빼고."""
        old_span, new_span = first_span(old_rx, text), first_span(new_rx, text)
        if old_span == new_span:
            return old_span is not None
        self.assertIsNotNone(old_span, "옛 패턴이 안 맞는데 새 패턴이 맞았다(더 엄격) %s %r" % (label, text[:80]))
        self.assertIsNotNone(new_span, "옛 패턴이 맞는데 새 패턴이 안 맞았다(약해짐) %s %r" % (label, text[:80]))
        self.assertTrue(kind == "price" and explained_price_difference(text, old_span, new_span), "첫 맞은 자리가 다르다 %s %r 옛 %s 새 %s" % (label, text[:80], old_span, new_span))
        return True

    def test_on_seeded_samples_the_shipped_patterns_agree_with_the_old_ones_on_the_raw_and_the_normalized_text(self):
        """종류마다 8,000 개의 무작위 글(M116 상한 가장자리의 긴 열 포함)을 날것과 게이트가 정규화한 글(NFKC 등) 둘로 건다 — 약해진 글 0·더 엄격한 글 0·첫 맞은 자리 같음. 같은 방식의 20만 표본 확인은 보고서에 있다."""
        for kind in ("percent", "price", "dose", "email"):
            old_rx, new_rx = re.compile(PAIRS[kind][0], FLAGS), re.compile(shipped_pattern(kind), FLAGS)
            caught = 0
            for text in random_texts(kind, SAMPLE_SEED, SAMPLE_COUNT):
                for variant in (text, gates._normalized(text)):
                    caught += self.assert_same_verdict(kind, old_rx, new_rx, variant, kind)
            with self.subTest(kind=kind):
                self.assertGreater(caught, SAMPLE_COUNT // 4, "표본에서 옛 패턴이 잡는 글이 너무 적으면 '같다'는 말이 비어 버린다")

    def test_the_m116_values_do_weaken_the_same_samples_so_the_samples_are_not_empty_talk(self):
        """같은 표본에서 M116 값은 옛 패턴보다 약해지는 글이 실제로 있다(퍼센트·가격·이메일·용량 모두) — 이 표본이 상한 가장자리를 실제로 건드리는 증거."""
        for kind in ("percent", "price", "dose", "email"):
            old_rx, m116_rx = re.compile(PAIRS[kind][0], FLAGS), re.compile(M116_VALUES[kind], FLAGS)
            weaker = sum(1 for text in random_texts(kind, SAMPLE_SEED, SAMPLE_COUNT) if old_rx.search(text) and not m116_rx.search(text))
            with self.subTest(kind=kind):
                self.assertGreater(weaker, 20, kind)

    def test_runs_of_digits_and_separators_around_every_cap_are_caught_like_the_old_pattern(self):
        """가격 패턴: 열 길이 1–130(짧은 열 상한 63 의 양쪽 가장자리 포함) × 열 맨 앞 점·쉼표 0–3개 × 열 끝 점·쉼표 0–2개 × 숫자만·숫자와 쉼표 번갈아 × 틈(없음·공백·줄바꿈) × 단위 셋 — 모두 옛 패턴과 같다."""
        old_rx, new_rx = re.compile(OLD_PRICE, FLAGS), re.compile(shipped_pattern("price"), FLAGS)
        checked = 0
        for length in (1, 2, 19, 20, 21, 62, 63, 64, 65, 66, 100, 130, 330, 600):
            for lead in ("", ".", ",", ",.", "..", ",,,"):
                for tail in ("", ".", ",", "..", ",,"):
                    for body in ("1" * length, ("1," * length)[:length]):
                        for gap in ("", " ", "  ", "\n"):
                            for unit in ("달러", "USD", "usd"):
                                text = "값 " + lead + body + tail + gap + unit
                                self.assertTrue(self.assert_same_verdict("price", old_rx, new_rx, text, "len=%d" % length))
                                checked += 1
        self.assertGreater(checked, 8000)

    def test_a_long_run_after_leading_separators_is_caught_and_only_the_quoted_word_differs(self):
        """긴 열(맨 앞 숫자 뒤 64자 이상)은 열의 맨 앞에서 한 번만 시작하므로 맨 앞의 점·쉼표가 맞은 낱말에 붙는다 — 판정은 같고 사유 문구의 낱말만 다른 단 하나의 경우. 63자 이하(짧은 열)는 자리까지 옛 패턴과 같다."""
        old_rx, new_rx = re.compile(OLD_PRICE, FLAGS), re.compile(shipped_pattern("price"), FLAGS)
        long_text = "값 ,." + "1" * 65 + "달러"                                          # 맨 앞 숫자 뒤 64자 → 긴 열 갈래
        old_span, new_span = first_span(old_rx, long_text), first_span(new_rx, long_text)
        self.assertEqual(long_text[old_span[0]:old_span[1]], "1" * 65 + "달러")
        self.assertEqual(long_text[new_span[0]:new_span[1]], ",." + "1" * 65 + "달러")
        short_text = "값 ,." + "1" * 64 + "달러"                                         # 맨 앞 숫자 뒤 63자 → 짧은 열 갈래
        self.assertEqual(first_span(new_rx, short_text), first_span(old_rx, short_text))
        self.assertEqual(short_text[first_span(new_rx, short_text)[0]:first_span(new_rx, short_text)[1]], "1" * 64 + "달러")
        plain = "값 " + "1" * 200 + "달러"                                              # 맨 앞에 점·쉼표가 없으면 긴 열도 자리까지 같다
        self.assertEqual(first_span(new_rx, plain), first_span(old_rx, plain))

    def test_the_price_two_way_structure_equals_the_old_pattern_on_every_short_text_for_small_caps(self):
        """두 갈래 구조는 cap 이 몇이든 옛 패턴과 같다 — 작은 cap(1·2·3)으로 만든 같은 구조를 글자 여섯·일곱 개 이하의 모든 조합(숫자·점·쉼표·공백·글자·단위)에서 전수로 견준다.
        프로필의 값은 같은 만드는 법에 cap 63 을 넣은 것이다(ValueTest). 대조로 한 갈래뿐인 상한 패턴(짧은 열 갈래만)은 cap 을 넘는 열에서 옛 패턴보다 약해진다."""
        old_rx = re.compile(OLD_PRICE, FLAGS)
        total = 0
        for cap, longest in ((1, 6), (2, 7), (3, 6)):
            new_rx = re.compile(price_two_way(cap), FLAGS)
            for length in range(1, longest + 1):
                for combo in itertools.product(PRICE_SMALL_CAP_TOKENS, repeat=length):
                    text = "".join(combo)
                    old_span, new_span = first_span(old_rx, text), first_span(new_rx, text)
                    total += 1
                    if old_span != new_span:
                        self.assertTrue(old_span and new_span and explained_price_difference(text, old_span, new_span), (cap, text, old_span, new_span))
        self.assertGreater(total, 300000)
        for cap in (1, 2, 3):
            only_short = re.compile(PRICE_HEAD + r"(?<!\d)(?<!\d[.,])\d[\d,.]{0,%d}" % cap + PRICE_UNIT, FLAGS)
            text = "1" * (cap + 3) + "달러"
            with self.subTest(cap=cap):
                self.assertTrue(old_rx.search(text))
                self.assertIsNone(only_short.search(text), "한 갈래뿐인 상한 패턴이 이 입력을 잡으면 대조가 빈말이다")
                self.assertTrue(re.compile(price_two_way(cap), FLAGS).search(text))


# ----------------------------------------------------------------------------
# 감사(BP-S2 R1)의 재현 입력을 진짜 게이트 함수로: M116 값은 통과시키던 글이 이제 탈락한다
# ----------------------------------------------------------------------------
AUDIT_REPRO = (      # (프로필, 목록 — 'body' 는 body_risk_hit, 종류, 글) — M116 값은 통과시키고 옛 판정은 탈락시키던 글
    ("blogger_ai_tools_ko", "banned_patterns", "percent", "새 설정 이후 속도가 1.2.5% 빨라졌습니다"),
    ("blogger_ai_tools_ko", "banned_patterns", "percent", "처리 시간이 1234567890% 단축되었습니다"),
    ("blogger_ai_tools_ko", "banned_patterns", "price", "가격은 " + "9" * 21 + " 달러입니다"),
    ("blogger_ai_tools_ko", "banned_patterns", "price", "가격은 " + "9" * 65 + " 달러입니다"),
    ("blogger_ai_tools_ko", "banned_patterns", "price", "가격은 ,." + "9" * 70 + " USD 입니다"),
    ("blogger_ai_tools_ko", "banned_patterns", "email", "문의: " + "a" * 65 + "@example.com"),
    ("blogger_ai_tools_ko", "banned_patterns", "email", "문의: user@" + "a" * 64 + ".com"),
    ("blogger_ai_tools_ko", "banned_topic_patterns", "dose", "비타민 1.2.5mg 후기"),
    ("blogger_ai_tools_ko", "body_banned_patterns", "dose", "하루 1.2.5mg 을 드세요"),
    ("blogger_practical_ko", "body", "dose", "하루 1.2.5mg 을 드세요"),
    ("blogger_practical_ko", "banned_topic_patterns", "dose", "비타민 1.2.5mg 후기"),
)
AUDIT_CONTROL = (      # 같은 틀의 대조: 옛·M116·지금 값이 모두 탈락시키는 글(감사가 '요청서가 짚은 ver.5%·전각은 약해지지 않았다'고 확인한 것)
    ("blogger_ai_tools_ko", "banned_patterns", "percent", "버전 ver.5% 빨라졌습니다"),
    ("blogger_ai_tools_ko", "banned_patterns", "percent", "처리 시간이 ５０％ 단축되었습니다"),
    ("blogger_ai_tools_ko", "banned_patterns", "email", "문의: " + "a" * 64 + "@example.com"),
    ("blogger_practical_ko", "body", "dose", "하루 5mg 을 드세요"),
    ("blogger_practical_ko", "body", "dose", "ver.5mg 을 드세요"),
)
KOREAN_GUARDRAIL_PROFILES = ("blogger_ai_tools_ko", "naver_life_tips_ko")        # 두 프로필의 가드레일 목록은 한 글자도 다르지 않다(ValueTest)
LISTS_WITH_THE_CHANGED_PATTERNS = ("banned_patterns", "banned_topic_patterns", "body_banned_patterns")


def gate_verdict(profile, key, text):
    """진짜 게이트 함수의 (걸린 패턴, 맞은 낱말) — 걸리지 않으면 (None, None). 'body' 는 본문 위험 규칙 body_risk_hit, 그 밖은 목록 하나에 first_match."""
    if key == "body":
        return gates.body_risk_hit(text, profile)
    return gates.first_match(profile.get(key), text)


def with_m116_values(profile):
    """프로필 사본에서 지금 값을 M116 값으로 바꿔 끼운다(종류 표지로 찾는다) — 'M116 값이면 통과시켰을 글'을 시험하는 데 쓴다."""
    swapped = dict(profile)
    for field in LISTS_WITH_THE_CHANGED_PATTERNS:
        swapped[field] = [next((M116_VALUES[kind] for kind in M116_VALUES if UNIT_MARK[kind] in pattern), pattern) for pattern in profile.get(field, [])]
    return swapped


class AuditReproTest(unittest.TestCase):
    def profiles_for(self, name):
        return KOREAN_GUARDRAIL_PROFILES if name == "blogger_ai_tools_ko" else (name,)

    def test_every_audit_reproduction_and_control_is_rejected_by_the_real_gate_functions(self):
        """감사 BP-S2 의 regex_repro 입력을 진짜 gates.first_match·body_risk_hit 으로 건다. 한국어 가드레일 프로필 둘(ai_tools·naver)은 같은 값이라 둘 다 본다 — 걸린 패턴은 시험하려던 종류의 패턴이다."""
        checked = 0
        for name, key, kind, text in AUDIT_REPRO + AUDIT_CONTROL:
            for profile_name in self.profiles_for(name):
                raw, word = gate_verdict(load(profile_name), key, text)
                with self.subTest(profile=profile_name, list=key, kind=kind, text=text[:40]):
                    self.assertIsNotNone(raw, "탈락해야 하는 글이 통과했다")
                    self.assertIn(UNIT_MARK[kind], raw, "다른 패턴이 걸렸다 — 이 입력이 시험하려던 패턴이 아니다")
                    self.assertTrue(word)
                checked += 1
        self.assertGreaterEqual(checked, 24)

    def test_the_reproductions_slip_through_when_the_m116_values_are_put_back_and_the_controls_do_not(self):
        """표가 빈말이 아니다: 지금 값을 M116 값으로 바꿔 끼운 프로필은 재현 입력을 모두 통과시키고(옛 판정은 탈락시켰다), 대조 입력은 그대로 탈락시킨다."""
        for name, key, kind, text in AUDIT_REPRO + AUDIT_CONTROL:
            for profile_name in self.profiles_for(name):
                raw, _word = gate_verdict(with_m116_values(load(profile_name)), key, text)
                with self.subTest(profile=profile_name, list=key, kind=kind, text=text[:40]):
                    if (name, key, kind, text) in AUDIT_REPRO:
                        self.assertIsNone(raw, "M116 값이 이 입력을 잡으면 재현 표가 빈말이다")
                    else:
                        self.assertIsNotNone(raw)

    def test_the_reproductions_are_what_the_old_pre_m116_patterns_rejected(self):
        """재현 입력은 정말 '옛 금지 판정이 탈락시키던 글'이다 — 같은 게이트 함수에 옛 값(M116 이전)을 끼워 건다."""
        old_values = {kind: PAIRS[kind][0] for kind in PAIRS}
        for name, key, kind, text in AUDIT_REPRO:
            profile = load(name)
            for field in LISTS_WITH_THE_CHANGED_PATTERNS:
                profile[field] = [next((old_values[k] for k in old_values if UNIT_MARK[k] in pattern), pattern) for pattern in profile.get(field, [])]
            raw, _word = gate_verdict(profile, key, text)
            with self.subTest(profile=name, list=key, kind=kind, text=text[:40]):
                self.assertIsNotNone(raw)


# ----------------------------------------------------------------------------
# 면제 취소 패턴(body_safe_veto_patterns, N6·D-498): 앞이 제한 없는 숫자 반복이라 숫자 N자(+ x)에서 4,000자 1.8초·0.36초 — 글 길이의 제곱이었다(D-431 의 '남은 것').
# 앞 경계만 더했다 — 옛 패턴이 숫자 열 한가운데에서 맞으면 그 열(점·쉼표로 이은 숫자 덩어리)의 맨 앞에서도 같은 끝까지 맞으므로 판정과 첫 맞은 자리가 같고 시간은 선형이다.
# 이 목록은 '있으면 면제를 취소해 막는다'는 쪽이라 약해지면 상담 구절이 든 절의 용량 표현이 통과한다 — 그래서 옛 패턴과의 판정 동치가 핵심이다.
# 알 수 단위 패턴(veto[1])은 뒤쪽 `(?![가-힣]{2,})` 도 한글 수사·단위가 이어진 열에서 제곱이었다 — 의미가 같은 `(?![가-힣]{2})`(다음 두 글자가 한글인가)로 바꿔 읽는 글자 수를 상수로 했다(QUADRATIC_VETO1 이 그 꼴의 값).
# ----------------------------------------------------------------------------
OLD_VETO = (
    r"\d+(?:[.,]\d+)*\s?(?:mgs?|mcg|μg|iu|(?-i:g))(?![a-z])|밀리그램|마이크로그램|\d+\s?(?:킬로)?그램",
    r"(?:\d+|(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|반))\s?(?:정|캡슐|알)(?![가-힣]{2,})",
)
NEW_VETO = (
    r"(?<!\d)(?<!\d[.,])\d+(?:[.,]\d+)*\s?(?:mgs?|mcg|μg|iu|(?-i:g))(?![a-z])|밀리그램|마이크로그램|(?<!\d)\d+\s?(?:킬로)?그램",
    r"(?:(?<!\d)\d+|(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|반))\s?(?:정|캡슐|알)(?![가-힣]{2})",
)
# 숫자 앞 경계만 더하고 뒤쪽은 {2,} 로 둔 veto[1] 꼴: 숫자 열은 선형이지만 한글 수사·단위('한정한정…')가 끊김 없이 이어진 글에서는 맞을 때마다 뒤에 이어진 한글 열을 끝까지 읽어 제곱 시간이다
# (독립 검증 S 권고-1·Q 권고-1). `(?![가-힣]{2,})`(두 글자 이상 이어지면 거절)와 `(?![가-힣]{2})`(다음 두 글자가 한글이면 거절)는 같은 말이라 판정·첫 맞은 자리가 같고, 뒤쪽 읽는 글자 수가 상수다.
QUADRATIC_VETO1 = r"(?:(?<!\d)\d+|(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|반))\s?(?:정|캡슐|알)(?![가-힣]{2,})"
VETO_PROFILES = ("blogger_ai_tools_ko", "naver_life_tips_ko", "blogger_practical_ko")
VETOED_SENTENCES = (       # 상담 구절이 든 절에 용량이 있어 면제를 취소해야만 막히는 문장(test_guardrails 의 MIXED_BLOCKED_KO 에서 옮김) + 점으로 이은 숫자 용량
    "의사와 상담하면 400mg 정도가 적당해요.", "의사와 상담하면 400 mg 정도가 적당해요.", "의사와 상담해서 멜라토닌 2알을 정하세요.", "의사와 상담해서 멜라토닌 0.4 g을 정하세요.", "의사와 상담하면 하루 1.2.5mg 정도가 적당해요.",
)
VETO_GRID = (       # (패턴 번호, 글자표, 최대 글자 수) — 숫자·점·쉼표·공백·글자와 단위 낱말의 모든 조합
    (0, ("1", ".", ",", " ", "x", "mg", "그램"), 6),
    (1, ("1", " ", "한", "정", "알", "x", "가"), 6),
)
# 옛 패턴이 속도 시험의 한도(PATTERN_LIMIT)를 넘는다는 대조에 쓰는 (패턴 번호, 숫자 자릿수). 이 PC 에서 세 번 중 가장 빠른 값(벽시계)이 옛 veto[0] 은 3,800자에 1.2초 안팎(한도 0.1초의 12배, CPU 시간으로 8–9배),
# 옛 veto[1] 은 6,399자에 0.7초 안팎(한도의 7배, CPU 시간 4–6배)이다. veto[1] 은 속도 시험의 병적 입력 길이(6,399자) 안에서 키울 수 있는 끝이다 — 이 패턴의 숫자 열은 그 길이에서 0.5–0.7초뿐이라 8배에 못 미친다.
# 두 패턴을 같은 길이로 재면 veto[0] 이 너무 오래 걸려(6,399자에서 4초 넘게 세 번) 따로 정했다. 시간은 글이 길수록 늘기만 하므로 이 길이에서 한도를 넘으면 속도 시험의 병적 입력(6,399자)에서도 넘는다 —
# 그 말이 서려면 자릿수가 속도 시험의 길이를 넘지 않아야 하고, TimeLimitRelationTest 가 그 관계를 못박는다.
OLD_VETO_PROOF_DIGITS = ((0, 3800), (1, 6399))
# 선형 시험: 한글 수사+단위 낱말('한정'·'두알'·'한알'·'열정'·'반캡슐'·'한정가')을 끊김 없이 이은 열을 속도 시험의 병적 입력(6,399자)의 열 배인 64,000자로 건다. 정상은 8 ms 안팎이라 한도(PATTERN_LIMIT, 0.1초)의 열두 배 여유이고,
# 제곱 시간이면 한글 열에서 4초(한도의 40배)라 그대로 잡힌다. 숫자 열은 일부러 뺐다 — 숫자 열이 제곱이면 64,000자에서 수 분이 걸려 시험이 실패할 때의 비용이 끝없이 커진다(숫자 열은 속도 시험의 병적 입력 6,399자가 맡는다).
LINEAR_UNITS = ("한정", "두알", "한알", "열정", "반캡슐", "한정가")
LINEAR_LENGTH = 64000
# `{2,}` 꼴(QUADRATIC_VETO1)이 한도를 넘는다는 대조에 쓰는 '한정' 반복 횟수(글자 수는 두 배): 34,000자에서 이 PC 의 세 번 중 최솟값이 1.2초 안팎(한도의 12배, CPU 시간으로 9–10배)이다.
# 선형 시험의 64,000자 안이라 '34,000자에서 한도를 넘으면 64,000자에서도 넘는다' 가 선다(관계는 TimeLimitRelationTest 가 못박는다).
QUADRATIC_PROOF_REPEATS = 17000


def veto_texts(index, seed, count):
    """면제 취소 패턴용 무작위 글(결정적): 숫자 덩어리·점·쉼표·한글 수사·글자가 섞이고 일부는 아주 긴 숫자 열을 낀다."""
    rng = random.Random(seed)
    pieces = ("1", "5", "10", "0.5", "2.5", "1,000", "3.14", "9" * 12, "9" * 70, "1.", "1,", ".", ",", "..", ",,", " ", "  ", "\n", "-", "x", "a", "ver.", "No.", "한글")
    units = (("mg", "mgs", "MG", "mcg", "μg", "iu", "IU", "g", "G", "gm", "mgx", "밀리그램", "마이크로그램", "그램", "킬로그램", "킬로 그램", "그램x", " 그램", " mg", "  mg", "ml", "mgA") if index == 0
             else ("정", "캡슐", "알", "정제", "정말", "알약", "알을", " 정", "  정", "캡슐약", "알아", "정정"))
    numerals = ("한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열", "반", "열두")
    for _ in range(count):
        parts = []
        for _ in range(rng.randint(1, 6)):
            roll = rng.random()
            if roll < 0.55:
                parts.append(rng.choice(pieces))
            elif roll < 0.7:
                parts.append(rng.choice(numerals))
            else:
                parts.append("".join(rng.choice("0123456789") for _ in range(rng.randint(1, 5))))
        yield "".join(parts) + rng.choice(units) + rng.choice(("", "", " 을", "a", "가나", "."))


class VetoPatternTest(unittest.TestCase):
    def test_the_three_korean_profiles_carry_the_new_veto_patterns_and_the_english_one_is_untouched(self):
        for name in VETO_PROFILES:
            profile = load(name)
            with self.subTest(profile=name):
                self.assertEqual(profile["body_safe_veto_patterns"], list(NEW_VETO))
                self.assertEqual(registry.validate_profile(profile), [])
        english = load("blogger_practical_en")["body_safe_veto_patterns"]
        self.assertEqual(len(english), 2)
        for pattern in english:
            self.assertNotIn(pattern, NEW_VETO + OLD_VETO)          # 영문 패턴은 앞이 낱말 경계(\\b)라 제곱 시간이 아니어서 이 묶음 밖이다

    def test_on_every_short_text_the_new_veto_patterns_match_exactly_like_the_old_ones(self):
        """글자 여섯 개 이하의 모든 조합에서 search 의 첫 맞은 자리가 같다(없음도 같다) — 면제 취소가 약해지면 상담 구절이 든 절의 용량 표현이 통과하므로 판정 동치가 핵심이다."""
        for index, tokens, longest in VETO_GRID:
            old_rx, new_rx = re.compile(OLD_VETO[index], FLAGS), re.compile(NEW_VETO[index], FLAGS)
            caught = differing = 0
            examples = []
            for length in range(1, longest + 1):
                for combo in itertools.product(tokens, repeat=length):
                    text = "".join(combo)
                    old_span, new_span = first_span(old_rx, text), first_span(new_rx, text)
                    caught += old_span is not None
                    if old_span != new_span:
                        differing += 1
                        if len(examples) < 5:
                            examples.append(text)
            with self.subTest(index=index):
                self.assertGreater(caught, 5000)
                self.assertEqual(differing, 0, "옛 패턴과 판정·첫 맞은 자리가 다른 글: %s" % examples)

    def test_on_seeded_samples_with_long_digit_runs_the_shipped_veto_patterns_agree_with_the_old_ones(self):
        for index in (0, 1):
            old_rx, new_rx = re.compile(OLD_VETO[index], FLAGS), re.compile(load("blogger_ai_tools_ko")["body_safe_veto_patterns"][index], FLAGS)
            caught = 0
            for text in veto_texts(index, SAMPLE_SEED, SAMPLE_COUNT):
                for variant in (text, gates._normalized(text)):
                    old_span, new_span = first_span(old_rx, variant), first_span(new_rx, variant)
                    self.assertEqual(new_span, old_span, "veto[%d] %r" % (index, variant[:80]))
                    caught += old_span is not None
            with self.subTest(index=index):
                self.assertGreater(caught, SAMPLE_COUNT // 4)

    def test_the_old_veto_patterns_are_slow_on_long_digit_runs_so_the_speed_test_is_not_empty_talk(self):
        """옛 패턴은 숫자 열이 길면 제곱 시간이다 — 옛 veto[0] 은 숫자 3,800자에 1.2초, veto[1] 은 6,399자(속도 시험의 병적 입력 길이)에 0.7초 걸려 세 번 중 가장 빠른 것도 속도 시험의 한도(PATTERN_LIMIT, 0.1초)의 12배·7배다(CPU 시간으로는 8–9배·4–6배).
        시간은 글이 길수록 늘기만 하므로 이 길이에서 한도를 넘으면 속도 시험의 병적 입력(한도 두 배 미만, 6,399자)에서도 넘는다 — 그래서 아래 속도 시험이 빈말이 아니다.
        두 길이(4,000자·2,000자)를 한 번씩 재서 시간 비율(> 2.5)을 단언하는 방식은 부하로 짧은 쪽이 한 번 밀리면 빨개져 쓰지 않는다(독립 검증 Q 필수-1: 60번 중 5번). 부하는 시간을 늘리기만 하므로 '한도를 넘는다' 는 단언은 부하에 흔들리지 않는다 —
        느려질수록 더 잘 통과하고, 세 번 중 가장 빠른 값을 쓰니 한 번 밀린 측정이 옛 패턴이 빠르다는 거짓 통과를 만들지도 않는다."""
        for index, digits in OLD_VETO_PROOF_DIGITS:
            rx = re.compile(OLD_VETO[index], FLAGS)
            took = best_of(rx, "1" * digits, 3)
            with self.subTest(index=index):
                self.assertGreater(took, PATTERN_LIMIT, "옛 veto[%d] 가 숫자 %d자에서 %.3f초 — 한도 %.1f초를 못 넘으면 속도 시험이 빈말이 된다" % (index, digits, took, PATTERN_LIMIT))

    def test_the_shipped_veto_patterns_are_fast_on_every_pathological_text(self):
        for name in VETO_PROFILES:
            texts = worst_texts(2 * max_chars(name) - 1)
            took, index, label = slowest(load(name)["body_safe_veto_patterns"], texts)
            with self.subTest(profile=name):
                self.assertLess(took, PATTERN_LIMIT, "%s veto[%d] %s: %.2f초" % (name, index, label, took))

    def test_the_two_lookahead_forms_pick_the_same_first_match_around_the_hangul_boundary(self):
        """뒤쪽 `(?![가-힣]{2,})`(두 글자 이상 이어지면 거절)와 `(?![가-힣]{2})`(다음 두 글자가 한글이면 거절)는 같은 말이다 — 단위 낱말 바로 뒤에 한글이 0·1·2·3글자 이어지거나 한글 범위 가장자리 글자·호환 자모·
        한글이 아닌 글자가 오는 꼴에서 첫 맞은 자리가 같다(없음도 같다). 글자 여섯 개 이하의 모든 조합(VETO_GRID)과 무작위 표본(위 시험)이 옛 패턴과의 동치를 이미 지키고, 이 표는 그 경계만 따로 든다."""
        heads = ("한정", "두알", "열캡슐", "1정", "10알", "반 정", "한 알", "x한정", "한정한정", "다섯알", "아홉 캡슐", "2.5정")
        tails = ("", "가", "가나", "가나다", "가나다라마바", "a", "가a", "a가", " 가나", "가 나", "가.나", chr(0xABFF) * 2, chr(0xD7A4) * 2, "가" + chr(0xD7A4), chr(0xABFF) + "가", "ㅎㅎ", "ㅏ가", "힣힣", "가힣", "정정", "알알알")
        old_rx, new_rx = re.compile(QUADRATIC_VETO1, FLAGS), re.compile(NEW_VETO[1], FLAGS)
        checked = matched = 0
        for lead in ("", "의사와 상담하면 "):
            for head in heads:
                for tail in tails:
                    text = lead + head + tail
                    checked += 1
                    matched += first_span(old_rx, text) is not None
                    self.assertEqual(first_span(new_rx, text), first_span(old_rx, text), text)
        self.assertGreater(matched, 40)           # 맞는 글도
        self.assertLess(matched, checked - 40)    # 한글이 두 글자 이어져 거절되는 글도 표에 많다 — 같다는 말이 한쪽으로만 비지 않는다

    def test_the_open_ended_lookahead_form_of_veto_one_is_quadratic_on_korean_numeral_runs_so_the_linearity_test_is_not_empty_talk(self):
        """뒤쪽을 `(?![가-힣]{2,})` 로 둔 꼴은 한글 수사·단위가 끊김 없이 이어진 글에서 제곱이다 — 맞을 때마다 뒤에 이어진 한글 열을 끝까지 읽는다. '한정' 을 34,000자(1만 7천 번) 이으면 이 PC 에서 세 번 중 가장 빠른 것이 1.2초 안팎으로
        속도 시험의 한도(PATTERN_LIMIT, 0.1초)의 12배다(CPU 시간으로 9–10배, 64,000자는 4초). 시간은 글이 길수록 늘기만 하므로 아래 선형 시험(64,000자, 같은 한도)이 이 값을 빨갛게 만든다 — 그 시험이 빈말이 아니다.
        부하는 시간을 늘리기만 하므로 이 방향의 단언은 부하에 흔들리지 않는다."""
        took = best_of(re.compile(QUADRATIC_VETO1, FLAGS), "한정" * QUADRATIC_PROOF_REPEATS, 3)
        self.assertGreater(took, PATTERN_LIMIT, "`{2,}` 꼴이 '한정' %d자에서 %.3f초 — 한도 %.1f초를 못 넘으면 선형 시험이 빈말이 된다" % (2 * QUADRATIC_PROOF_REPEATS, took, PATTERN_LIMIT))

    def test_the_shipped_veto_patterns_stay_linear_when_a_run_of_korean_numerals_and_units_is_ten_times_longer(self):
        """한국어 프로필 셋의 면제 취소 패턴 둘이, 한글 수사와 단위('한정한정…'·'두알두알…'·'한알…'·'열정…')가 끊김 없이 이어진 글을 속도 시험의 병적 입력(6,399자)의 열 배인
        64,000자로 늘려도 속도 시험의 한도(PATTERN_LIMIT, 0.1초) 안이다 — 글자 수가 열 배일 때 시간도 열 배 안팎(6,400자 0.7 ms → 64,000자 8 ms)이라야 들어가는 한도이고, 제곱이면(열 배 → 백 배) 4초라 그대로 잡힌다.
        시간 배율을 직접 단언하지 않는 이유: 짧은 쪽이 1 ms 안팎이라 측정 잡음이 배율을 흔들고, 흔들림을 막으려 바닥을 두면 한도와 같은 말이 된다 — 한도 단언은 부하가 시간을 늘리기만 하는 쪽으로만 흔들리고 세 번 중 가장 빠른 값을 쓴다.
        처음 위반한 칸에서 바로 멈춘다(제곱이면 한 칸이 수 초라 모두 재면 오래 걸린다)."""
        patterns = {}
        for name in VETO_PROFILES:
            for index, pattern in enumerate(load(name)["body_safe_veto_patterns"]):
                patterns.setdefault((index, pattern), name)       # 세 프로필의 값이 같다는 것은 위 시험이 지킨다 — 같은 값은 한 번만 잰다
        for (index, pattern), name in patterns.items():
            rx = re.compile(pattern, FLAGS)
            for unit in LINEAR_UNITS:
                text = (unit * (LINEAR_LENGTH // len(unit) + 1))[:LINEAR_LENGTH]
                took = best_of(rx, text, 3)
                self.assertLess(took, PATTERN_LIMIT, "%s veto[%d] %r 반복 %d자: %.3f초" % (name, index, unit, LINEAR_LENGTH, took))

    def test_the_gate_stays_fast_and_still_vetoes_a_dose_in_a_clause_with_a_consultation_phrase(self):
        """진짜 본문 위험 규칙(body_risk_hit): 상담 구절이 든 절에 6,000자 숫자가 이어져도 빠르고, 같은 절의 용량 표현(점으로 이은 숫자 포함)은 여전히 면제를 취소해 막는다.
        시간은 세 번 중 가장 빠른 것으로 잰다 — 정상은 6 ms 안팎이라 한도(0.5초)의 80배 여유이고, 부하로 한 번 밀린 측정이 시험을 빨갛게 하지 않는다(한 번만 재면 변이 62번 중 한 번 변이와 무관하게 빨개졌다,
        독립 검증 Q 필수-1). 제곱 시간이면 세 번 모두 5초 안팎이라 그대로 잡힌다."""
        text = "의사와 상담하세요 " + "1" * 6000
        for name in VETO_PROFILES:
            profile = load(name)
            took = best_call(lambda: gates.body_risk_hit(text, profile), 3)
            with self.subTest(profile=name):
                self.assertLess(took, GATE_PATH_LIMIT, "%.2f초" % took)
                for sentence in VETOED_SENTENCES:
                    self.assertIsNotNone(gates.body_risk_hit(sentence, profile)[0], sentence)


# ----------------------------------------------------------------------------
# 병적 입력의 시간(상한): 한도 두 배 미만의 같은 글자가 가득
# ----------------------------------------------------------------------------
def worst_texts(length):
    return {"digits": "1" * length, "digit-comma": "1," * (length // 2), "digit-dot": "1." * (length // 2), "hyphens": "-" * length, "letters": "a" * length, "alnum-hyphen": "a-" * (length // 2),
            "dots": "." * length, "letter-dot": "a." * (length // 2), "at-signs": "a@" * (length // 2), "percent": "1%" * (length // 2),
            "digit-comma-dot": "1,." * (length // 3), "digit-dot-comma": "1.," * (length // 3), "decimal-chain": "1.5" * (length // 3),
            "separator-lead": ",." * (length // 2) + "1x", "double-separator": "1.." * (length // 3) + "x", "triple-separator": "1..." * (length // 4) + "x", "run-then-space": "1" * (length // 2) + " " * (length // 2) + "x",
            "numeral-unit-han-jeong": "한정" * (length // 2), "numeral-unit-han-al": "한알" * (length // 2), "numeral-unit-yeol-jeong": "열정" * (length // 2), "unit-then-numeral": "알한" * (length // 2)}
    # digit-comma-dot 부터의 앞 셋: 앞 경계가 시작을 허락하는 꼴(쉼표·점 둘이 낀 숫자 열) — 가격 패턴 짧은 열 갈래의 63자 상한이 막는다(상한이 없으면 0.27초). 뒤의 넷(D-497): 가격 패턴의 긴 열 갈래(열의 맨 앞에서 한 번만 시작)와 점·쉼표가 겹친 열. 마지막 넷: 한글 수사+단위가 끊김 없이 이어진 열 — 면제 취소 패턴 veto[1] 의 뒤쪽 읽기를 본다(뒤쪽 `{2,}` 꼴은 6,399자에서 40 ms 안팎이라 이 한도로는 못 잡고 VetoPatternTest 의 64,000자 시험이 잡는다)


def best_of(rx, text, repeats=3):
    best = None
    for _ in range(repeats):
        started = time.perf_counter()
        rx.search(text)
        took = time.perf_counter() - started
        best = took if best is None else min(best, took)
    return best


def best_call(func, repeats=3):
    """best_of 의 함수 판 — func() 를 repeats 번 불러 가장 빠른 시간(초)을 돌려준다(부하는 시간을 늘리기만 하므로 가장 빠른 값이 진짜 시간에 가장 가깝다)."""
    best = None
    for _ in range(repeats):
        started = time.perf_counter()
        func()
        took = time.perf_counter() - started
        best = took if best is None else min(best, took)
    return best


PATTERN_LIMIT = 0.1        # 패턴 하나가 병적 입력 하나를 검색하는 데 걸리는 시간의 상한(초 — 세 번 중 가장 빠른 것). 바뀐 패턴은 0.001초 안팎(가격만 0.007초 안팎), 같은 목록의 다른 패턴도 0.02초 안이다(측정 문턱 이하). 옛 패턴은 숫자 연속에서 1초를 넘었고, 앞 경계만 둔 가격 패턴(두 갈래가 아닌 한 갈래)은 점·쉼표 낀 열에서 0.27초다
GATE_PATH_LIMIT = 0.5      # body_risk_hit 한 번(상담 구절 뒤 숫자 6,000자)의 상한(초 — 세 번 중 가장 빠른 것). 정상은 6 ms 안팎, 제곱 시간이면 5초 안팎
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


class TimeLimitRelationTest(unittest.TestCase):
    """시간 시험의 증명 입력 크기와 한도 상수 사이의 관계를 못박는다(독립 확인 D 권고-3 — 변이 T04·T05 가 살아남던 곳). 상수끼리만 견주고 시간을 재지 않는다(한도 값은 그대로).
    하한 증명('옛 패턴이 한도를 넘는다')이 받쳐 주는 말은 '시간은 글이 길수록 늘기만 하므로 증명 입력에서 한도를 넘으면 그보다 짧지 않은 속도·선형 시험의 입력에서도 넘는다' 인데, 그 말은 증명 입력이
    그 시험의 입력보다 길지 않을 때만 선다. 상수를 따로 고치다가 관계가 깨져도 시간 시험은 그대로 초록이라(변이 T04: 선형 시험을 6,400자로 줄여도 초록) 여기서 지킨다."""

    def test_each_old_pattern_proof_input_is_no_longer_than_the_test_input_it_vouches_for(self):
        self.assertEqual({index for index, _digits in OLD_VETO_PROOF_DIGITS}, {0, 1})        # 두 면제 취소 패턴의 옛 꼴 모두 하한 증명이 있다
        for name in VETO_PROFILES:
            for index, digits in OLD_VETO_PROOF_DIGITS:
                with self.subTest(profile=name, index=index):
                    self.assertLessEqual(digits, 2 * max_chars(name) - 1, "옛 veto[%d] 증명 입력(숫자 %d자)이 속도 시험의 병적 입력(%d자)보다 길다 — '속도 시험에서도 한도를 넘는다'가 안 선다" % (index, digits, 2 * max_chars(name) - 1))
        self.assertLessEqual(2 * QUADRATIC_PROOF_REPEATS, LINEAR_LENGTH, "`{2,}` 꼴 증명 입력(%d자)이 선형 시험의 입력(%d자)보다 길다 — '선형 시험에서도 한도를 넘는다'가 안 선다" % (2 * QUADRATIC_PROOF_REPEATS, LINEAR_LENGTH))

    def test_the_linear_test_input_is_ten_times_the_speed_test_input(self):
        for name in VETO_PROFILES:
            with self.subTest(profile=name):
                self.assertGreaterEqual(LINEAR_LENGTH, 10 * (2 * max_chars(name) - 1), "선형 시험이 속도 시험 입력의 열 배(그래서 '열 배 길어져도 선형')보다 짧아졌다")

    def test_the_time_limits_keep_their_order(self):
        """패턴 하나(PATTERN_LIMIT) <= 게이트 경로 한 번(GATE_PATH_LIMIT, 패턴 한도의 다섯 배 이하) < check_post 한 번(GATE_LIMIT). 게이트 경로 한도만 풀면(변이 T05: 0.5 -> 50) 시험이 빈말이 된다."""
        self.assertLessEqual(PATTERN_LIMIT, GATE_PATH_LIMIT)
        self.assertLessEqual(GATE_PATH_LIMIT, 5 * PATTERN_LIMIT + 1e-9)
        self.assertLess(GATE_PATH_LIMIT, GATE_LIMIT)


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

    def test_the_defect_rows_d497_and_d498_exist_once_with_six_cells_and_are_solved(self):
        """D-497(M116 의 자릿수 상한·점 뒤 경계가 옛 판정보다 약해지는 입력을 만든 것을 걷어냄 — 확인 040 ①)와 D-498(면제 취소 패턴의 제곱 시간 — D-431 의 '남은 것')은 정확히 한 행씩, 여섯 칸, 해결이고,
        D-431 의 알려진 좁아짐 서술은 역사로 남는다(D-431 시험이 지킨다)."""
        words = {
            "D-497": ("BP-S2", "R1", "D-431", "확인 032", "tests/test_profile_regex_bounds.py", "blogger_ai_tools_ko", "naver_life_tips_ko", "blogger_practical_ko", "12곳", "(?<!\\d)", "두 갈래", "19,949건",
                      "약해진 입력 0·더 엄격한 입력 0", "사유 문구의 낱말만 다르다", "이메일 둘째 이후 매치 목록", "낱말 목록의 한계", "`FORMER_NARROWING`", "`NoWeakeningTest`", "`AuditReproTest`", "`GridTest`"),
            "D-498": ("body_safe_veto_patterns", "N6", "D-431", "BP-S2", "VetoPatternTest", "(?<!\\d)(?<!\\d[.,])", "96만 조합", "20만 표본", "약해진 입력 0·더 엄격한 입력 0", "4,000자", "6,000자", "영문 프로필", "게이트 경로", "(?![가-힣]{2})", "한글 수사", "64,000자", "선형 시험", "998만", "한글 열 제곱은 위에서 닫았으므로", "34,000자", "TimeLimitRelationTest"),
        }
        for number, needles in words.items():
            rows = [line for line in self.DEFECTS.splitlines() if line.startswith("| **%s** |" % number)]
            with self.subTest(defect=number):
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0].count("|"), 7)
                self.assertIn("**해결**", rows[0])
                for needle in needles:
                    self.assertIn(needle, rows[0], needle)
                self.assertNotIn(chr(126), rows[0])
                self.assertIsNone(re.search(r"https?://", rows[0]))
        self.assertEqual(self.DEFECTS.count("| **D-497** |"), 1)
        self.assertEqual(self.DEFECTS.count("| **D-498** |"), 1)

    def test_the_oversize_test_header_no_longer_says_the_profile_values_are_untouched(self):
        self.assertNotIn("프로필 JSON 의 정규식 값은 고치지 않았다", self.ROOT_TEXT)
        self.assertIn("D-431", self.ROOT_TEXT)


if __name__ == "__main__":
    unittest.main()
