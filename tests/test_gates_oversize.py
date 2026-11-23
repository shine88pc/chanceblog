"""본문이 길이 한도의 두 배를 넘으면 금지 표현 정규식을 돌리지 않고 곧바로 탈락시킨다(BP-S1-5, 결함 D-415) — 정규식의 제곱 시간(가용성) 닫기. 네트워크 없이 돈다.

배경: Blogger·네이버 프로필의 금지 표현 정규식(`\\d+…`·이메일 모양 `[A-Za-z0-9._%+\\-]+@…`)은 같은 종류 글자가 길게 이어지면 시작 위치마다 다시 먹어 글 길이의 제곱으로 느려진다
(감사 측정: 숫자 20,000자 48초·대시 30,000자 6.9초). 길이 한도(length.max_chars)는 [LEN_LONG] 사유로 쌓이기만 하고 정규식은 한도를 넘는 글에 그대로 돌았다 — 모델이 같은 글자를 길게 되풀이하는
고장이 나면 정기 실행이 15분 제한까지 붙들리고 시도 3번을 모두 썼다(게시되지는 않는다 — 가용성 문제). 이제 `check_post` 가 본문이 한도의 두 배를 넘는 글을 맨 앞에서 탈락시킨다(어차피 탈락).
프로필 JSON 의 정규식 값은 고치지 않았다(운영자 판단 — 보고서 제안). 정상 길이 글의 판정은 이전과 같다(기존 test_gates* 가 지킨다).

2차 검증(BP2S-1·Q 권고-1, 결함 D-422): 같은 제곱 시간이 제목 쪽에도 열려 있었다 — 제목만 같은 글자 2만 자로 바꾸면 한 번에 53.8초(숫자)·3.6초(대시)가 걸렸다(제목 전용 정규식과 제목 + 본문에
거는 정규식이 제목 앞쪽에서 시작한다). 이제 제목이 title.max_chars 의 두 배를 넘어도 같은 식으로 곧바로 탈락한다(사유는 같은 도우미의 [TITLE_LEN] 한 줄, 본문도 두 배를 넘었으면 그 뒤에 [LEN_LONG]).
제목 길이 경계(최소·최대 ±1)는 정상 경로와 조기 반환 경로 둘 다에서 못박는다(변이 Q17: 최대 `<=` 를 `<` 로 바꿔도 시험이 초록이던 틈).
"""
import time
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
from pipeline import gates, registry

KO_PROFILES = ("blogger_ai_tools_ko", "naver_life_tips_ko", "blogger_practical_ko")
EN_PROFILES = ("blogger_practical_en",)
ALL_PROFILES = KO_PROFILES + EN_PROFILES
STATS = {"dropped_blocks": 0, "unwrapped_tags": 0, "links_removed": 0}


def post_for(name, body, title=None):
    ko = name.endswith("_ko")
    return {"title": title if title is not None else ("시험 제목입니다 오늘의 글" if ko else "A calm and simple test title"), "labels": ["a", "b"], "content": "<p>" + body + "</p>"}


def check(name, body, title=None, stats=None):
    return gates.check_post(post_for(name, body, title), registry.load_profile(name), recent_titles=("x",), other_titles=("y",), sanitize_stats=stats)


def max_chars(name):
    return registry.load_profile(name)["length"]["max_chars"]


def title_limits(name):
    t_cfg = registry.load_profile(name)["title"]
    return t_cfg["min_chars"], t_cfg["max_chars"]


def filler(name):
    return "가" if name.endswith("_ko") else "a"


def normal_body(name):
    return filler(name) * 800


def title_reason(name, title):
    """정상 경로와 조기 반환이 같이 쓰는 [TITLE_LEN] 사유 문장(허용 범위의 물결 기호는 소스에 두지 않으려 chr(126) 으로 조립한다)."""
    low, high = title_limits(name)
    return f"[TITLE_LEN] 제목 길이 {len(title)}자 (허용 {low}{chr(126)}{high}자)"


def boom_scanner(name):
    return mock.patch.object(gates, name, side_effect=AssertionError(f"{name} 을(를) 불렀다 — 길이 초과 글에 정규식·유사도 검사를 돌렸다"))


class TrapTexts:
    """감사 재현의 병적 입력(같은 종류 글자의 긴 연속)."""
    DIGITS_20K = "1234567890" * 2000
    DASHES_30K = "-" * 30000
    LETTERS_30K = "a" * 30000
    DOTS_30K = "." * 30000


class OversizeSpeedTest(unittest.TestCase):
    def test_pathological_long_bodies_return_in_under_a_second_for_every_profile(self):
        for name in ALL_PROFILES:
            for label, body in (("숫자 20,000자", TrapTexts.DIGITS_20K), ("대시 30,000자", TrapTexts.DASHES_30K), ("영문 30,000자", TrapTexts.LETTERS_30K), ("점 30,000자", TrapTexts.DOTS_30K)):
                with self.subTest(profile=name, text=label):
                    started = time.perf_counter()
                    result = check(name, body)
                    elapsed = time.perf_counter() - started
                    self.assertLess(elapsed, 1.0, f"{name} {label}: {elapsed:.2f}초")
                    self.assertFalse(result.ok)
                    self.assertIn("LEN_LONG", result.codes())

    def test_the_oversize_result_is_only_the_cheap_reason_for_a_good_title(self):
        for name in ALL_PROFILES:
            with self.subTest(profile=name):
                result = check(name, TrapTexts.DIGITS_20K)
                self.assertEqual(result.reasons, [f"[LEN_LONG] 본문 20000자 (최대 {max_chars(name)}자)"])
                self.assertEqual(result.warnings, [])


class NoRegexScanTest(unittest.TestCase):
    """속도를 재지 않고도 같은 것을 보인다: 정규식·유사도 검사를 아예 부르지 않는다(결정적)."""

    SCANNERS = ("matches_any", "first_match", "body_risk_hit", "most_similar", "topic_allowed")

    def boom(self, name):
        return mock.patch.object(gates, name, side_effect=AssertionError(f"{name} 을(를) 불렀다 — 길이 초과 글에 정규식·유사도 검사를 돌렸다"))

    def test_an_oversize_body_calls_none_of_the_scanners(self):
        for name in ALL_PROFILES:
            body = "가" * (2 * max_chars(name) + 1) if name.endswith("_ko") else "a" * (2 * max_chars(name) + 1)
            with self.subTest(profile=name):
                with self.boom("matches_any"), self.boom("first_match"), self.boom("body_risk_hit"), self.boom("most_similar"), self.boom("topic_allowed"):
                    result = check(name, body)
                self.assertFalse(result.ok)
                self.assertIn("LEN_LONG", result.codes())

    def test_a_body_within_twice_the_limit_still_runs_every_scanner(self):
        """대조: 같은 가짜 감시가 정상·한도 경계 글에서는 불린다(감시가 비어 있지 않다는 증명)."""
        for name in ALL_PROFILES:
            ko = name.endswith("_ko")
            for size in (max_chars(name) // 2, max_chars(name) + 10, 2 * max_chars(name)):
                body = ("가" if ko else "a") * size
                with self.subTest(profile=name, size=size):
                    spies = {scanner: mock.patch.object(gates, scanner, wraps=getattr(gates, scanner)) for scanner in ("matches_any", "first_match", "body_risk_hit", "most_similar")}
                    started = {scanner: patcher.start() for scanner, patcher in spies.items()}
                    try:
                        check(name, body)
                    finally:
                        for patcher in spies.values():
                            patcher.stop()
                    self.assertTrue(all(spy.call_count > 0 for spy in started.values()), {scanner: spy.call_count for scanner, spy in started.items()})


class BoundaryAndShapeTest(unittest.TestCase):
    def test_exactly_twice_the_limit_is_not_oversize_but_one_more_character_is(self):
        for name in ALL_PROFILES:
            ko = name.endswith("_ko")
            limit = 2 * max_chars(name)
            with self.subTest(profile=name):
                at_limit = check(name, ("가" if ko else "a") * limit)
                self.assertGreater(len(at_limit.reasons), 1, at_limit.reasons)             # 전체 검사가 돌았다(구조·목록 사유가 함께 쌓인다)
                self.assertIn("LEN_LONG", at_limit.codes())
                over = check(name, ("가" if ko else "a") * (limit + 1))
                self.assertEqual(over.reasons, [f"[LEN_LONG] 본문 {limit + 1}자 (최대 {max_chars(name)}자)"])

    def test_between_the_limit_and_twice_the_limit_the_full_check_still_reports_every_reason(self):
        for name in ALL_PROFILES:
            with self.subTest(profile=name):
                result = check(name, ("가" if name.endswith("_ko") else "a") * (max_chars(name) + 10))
                self.assertIn("LEN_LONG", result.codes())
                self.assertTrue({"STRUCT_H3"} <= set(result.codes()), result.reasons)     # 소제목 규칙 사유도 같이 나온다 — 전과 같은 모양

    def test_the_normal_path_keeps_the_original_reason_sentences(self):
        """도우미로 옮긴 두 사유 문장(정상 경로)이 이전과 글자까지 같다 — 조기 반환과 같은 도우미를 쓰지만 문장 모양을 못박는다."""
        for name in ALL_PROFILES:
            with self.subTest(profile=name):
                profile = registry.load_profile(name)
                limit, t_cfg = profile["length"]["max_chars"], profile["title"]
                result = check(name, ("가" if name.endswith("_ko") else "a") * (limit + 10), title="x")
                self.assertIn(f"[LEN_LONG] 본문 {limit + 10}자 (최대 {limit}자)", result.reasons)
                self.assertIn(f"[TITLE_LEN] 제목 길이 1자 (허용 {t_cfg['min_chars']}~{t_cfg['max_chars']}자)", result.reasons)
                self.assertLess(result.codes().index("TITLE_LEN"), result.codes().index("LEN_LONG"))      # 순서: 제목 길이가 본문 길이보다 앞

    def test_a_bad_title_reason_still_comes_first_then_the_length_reason(self):
        for name in ALL_PROFILES:
            with self.subTest(profile=name):
                result = check(name, TrapTexts.DIGITS_20K, title="x")
                self.assertEqual(result.codes(), ["TITLE_LEN", "LEN_LONG"])
                self.assertTrue(result.reasons[0].startswith("[TITLE_LEN]"))

    def test_the_sanitize_warning_is_still_reported_on_the_early_return(self):
        for name in ALL_PROFILES:
            with self.subTest(profile=name):
                result = check(name, TrapTexts.DIGITS_20K, stats={"dropped_blocks": 2, "unwrapped_tags": 0, "links_removed": 0})
                self.assertEqual(result.warnings, ["[SANITIZED] HTML 정화로 제거됨: {'dropped_blocks': 2}"])

    def test_a_profile_without_a_length_limit_never_takes_the_early_return(self):
        profile = dict(registry.load_profile("blogger_practical_ko"))
        profile.pop("length")
        result = gates.check_post(post_for("blogger_practical_ko", "가" * 20000), profile, recent_titles=("x",), other_titles=("y",), sanitize_stats=STATS)
        self.assertNotIn("LEN_LONG", result.codes())


class OversizeTitleSpeedTest(unittest.TestCase):
    """2차 검증 BP2S-1: 제목이 같은 글자의 긴 연속이어도 1초 안에 탈락한다(옛 코드 실측: 숫자 2만 자 53.8초·대시 3만 자 3.6초)."""

    def assert_fast_and_cheap(self, title, label):
        for name in ALL_PROFILES:
            with self.subTest(profile=name, title=label):
                started = time.perf_counter()
                result = check(name, normal_body(name), title=title)
                elapsed = time.perf_counter() - started
                self.assertLess(elapsed, 1.0, f"{name} {label}: {elapsed:.2f}초")
                self.assertFalse(result.ok)
                self.assertEqual(result.reasons, [title_reason(name, title)])
                self.assertEqual(result.warnings, [])

    def test_a_20000_digit_title_returns_fast(self):
        self.assert_fast_and_cheap(TrapTexts.DIGITS_20K, "숫자 20,000자")

    def test_a_30000_dash_title_returns_fast(self):
        self.assert_fast_and_cheap(TrapTexts.DASHES_30K, "대시 30,000자")

    def test_a_30000_letter_title_returns_fast(self):
        self.assert_fast_and_cheap(TrapTexts.LETTERS_30K, "영문 30,000자")

    def test_a_30000_dot_title_returns_fast(self):
        self.assert_fast_and_cheap(TrapTexts.DOTS_30K, "점 30,000자")


class OversizeTitleNoScanTest(unittest.TestCase):
    """속도를 재지 않고도 같은 것을 보인다(결정적): 제목이 한도의 두 배를 넘으면 정규식·유사도 검사를 아예 부르지 않는다."""

    def test_an_oversize_title_calls_none_of_the_scanners(self):
        for name in ALL_PROFILES:
            title = filler(name) * (2 * title_limits(name)[1] + 1)
            with self.subTest(profile=name):
                with boom_scanner("matches_any"), boom_scanner("first_match"), boom_scanner("body_risk_hit"), boom_scanner("most_similar"), boom_scanner("topic_allowed"):
                    result = check(name, normal_body(name), title=title)
                self.assertFalse(result.ok)
                self.assertEqual(result.reasons, [title_reason(name, title)])

    def test_a_title_up_to_twice_the_limit_still_runs_every_scanner(self):
        """대조: 같은 감시가 한도를 넘은 제목 — 두 배 미만과 정확히 두 배 — 에서는 불린다(감시가 비어 있지 않고 경계가 두 배 + 1 이다)."""
        for name in ALL_PROFILES:
            high = title_limits(name)[1]
            for size in (high + 1, 2 * high - 1, 2 * high):
                with self.subTest(profile=name, size=size):
                    patchers = {scanner: mock.patch.object(gates, scanner, wraps=getattr(gates, scanner)) for scanner in ("matches_any", "first_match", "body_risk_hit", "most_similar")}
                    spies = {scanner: patcher.start() for scanner, patcher in patchers.items()}
                    try:
                        check(name, normal_body(name), title=filler(name) * size)
                    finally:
                        for patcher in patchers.values():
                            patcher.stop()
                    self.assertTrue(all(spy.call_count > 0 for spy in spies.values()), {scanner: spy.call_count for scanner, spy in spies.items()})


class OversizeTitleShapeTest(unittest.TestCase):
    def test_exactly_twice_the_title_limit_runs_the_full_check_and_one_more_character_does_not(self):
        for name in ALL_PROFILES:
            high = title_limits(name)[1]
            with self.subTest(profile=name):
                at_limit = check(name, normal_body(name), title=filler(name) * (2 * high))
                self.assertIn("TITLE_LEN", at_limit.codes())
                self.assertIn("STRUCT_H3", at_limit.codes())                    # 전체 검사가 돌았다 — 본문 구조 사유가 함께 쌓인다
                self.assertGreater(len(at_limit.reasons), 1, at_limit.reasons)
                title = filler(name) * (2 * high + 1)
                self.assertEqual(check(name, normal_body(name), title=title).reasons, [title_reason(name, title)])

    def test_a_title_far_over_twice_the_limit_with_a_good_body_reports_only_the_title_reason(self):
        for name in ALL_PROFILES:
            title = filler(name) * (2 * title_limits(name)[1] + 50)
            with self.subTest(profile=name):
                result = check(name, normal_body(name), title=title)
                self.assertEqual(result.codes(), ["TITLE_LEN"])
                self.assertEqual(result.reasons, [title_reason(name, title)])

    def test_title_and_body_both_oversize_give_the_title_reason_first_then_the_length_reason(self):
        for name in ALL_PROFILES:
            title = filler(name) * (2 * title_limits(name)[1] + 1)
            size = 2 * max_chars(name) + 1
            with self.subTest(profile=name):
                result = check(name, filler(name) * size, title=title)
                self.assertEqual(result.reasons, [title_reason(name, title), f"[LEN_LONG] 본문 {size}자 (최대 {max_chars(name)}자)"])

    def test_the_sanitize_warning_is_still_reported_when_only_the_title_is_oversize(self):
        for name in ALL_PROFILES:
            with self.subTest(profile=name):
                result = check(name, normal_body(name), title=filler(name) * (2 * title_limits(name)[1] + 1), stats={"dropped_blocks": 2, "unwrapped_tags": 0, "links_removed": 0})
                self.assertFalse(result.ok)
                self.assertEqual(result.warnings, ["[SANITIZED] HTML 정화로 제거됨: {'dropped_blocks': 2}"])

    def test_a_profile_without_a_title_section_uses_the_default_limit_of_two_hundred(self):
        """title 섹션이 없으면 한도 기본값 200 이다(_title_len_reason 과 같은 값): 두 배 400자까지는 전체 검사, 401자부터 조기 반환."""
        profile = dict(registry.load_profile("blogger_practical_ko"))
        profile.pop("title")
        scanners = ("matches_any", "first_match", "body_risk_hit", "most_similar")
        with boom_scanner("matches_any"), boom_scanner("first_match"), boom_scanner("body_risk_hit"), boom_scanner("most_similar"):
            early = gates.check_post(post_for("blogger_practical_ko", normal_body("blogger_practical_ko"), title="가" * 401), profile, recent_titles=("x",), other_titles=("y",), sanitize_stats=STATS)
        self.assertEqual(early.codes(), ["TITLE_LEN"])
        patchers = {scanner: mock.patch.object(gates, scanner, wraps=getattr(gates, scanner)) for scanner in scanners}
        spies = {scanner: patcher.start() for scanner, patcher in patchers.items()}
        try:
            full = gates.check_post(post_for("blogger_practical_ko", normal_body("blogger_practical_ko"), title="가" * 400), profile, recent_titles=("x",), other_titles=("y",), sanitize_stats=STATS)
        finally:
            for patcher in patchers.values():
                patcher.stop()
        self.assertTrue(all(spy.call_count > 0 for spy in spies.values()), {scanner: spy.call_count for scanner, spy in spies.items()})
        self.assertIn("TITLE_LEN", full.codes())


class TitleLengthBoundaryTest(unittest.TestCase):
    """Q 권고-1(변이 Q17: 최대 `<=` 를 `<` 로 바꿔도 초록이던 틈): 제목 길이의 최소·최대 경계 ±1 을 정상 경로와 본문 길이 초과 조기 반환 경로 둘 다에서 못박는다.
    두 경로는 같은 도우미(_title_len_reason)를 쓴다 — 옮기다 틀려도 잡히도록 같은 표를 두 번 돌린다."""

    def boundary_table(self, name):
        low, high = title_limits(name)
        self.assertGreaterEqual(low, 2)                                             # 최소 − 1 이 빈 제목이 되지 않는다
        return [(low - 1, True), (low, False), (low + 1, False), (high - 1, False), (high, False), (high + 1, True)]

    def test_the_normal_path_accepts_the_minimum_and_the_maximum_and_rejects_one_outside_each(self):
        for name in ALL_PROFILES:
            for length, rejected in self.boundary_table(name):
                title = filler(name) * length
                with self.subTest(profile=name, length=length):
                    result = check(name, normal_body(name), title=title)
                    self.assertEqual("TITLE_LEN" in result.codes(), rejected, result.reasons)
                    if rejected:
                        self.assertIn(title_reason(name, title), result.reasons)

    def test_the_early_return_path_judges_the_same_boundaries_with_the_same_sentence(self):
        for name in ALL_PROFILES:
            size = 2 * max_chars(name) + 1
            long_reason = f"[LEN_LONG] 본문 {size}자 (최대 {max_chars(name)}자)"
            for length, rejected in self.boundary_table(name):
                title = filler(name) * length
                with self.subTest(profile=name, length=length):
                    result = check(name, filler(name) * size, title=title)
                    self.assertEqual(result.reasons, ([title_reason(name, title)] if rejected else []) + [long_reason])

    def test_a_title_in_range_is_not_reported_on_either_path(self):
        for name in ALL_PROFILES:
            low, high = title_limits(name)
            title = filler(name) * ((low + high) // 2)
            with self.subTest(profile=name):
                self.assertNotIn("TITLE_LEN", check(name, normal_body(name), title=title).codes())
                self.assertNotIn("TITLE_LEN", check(name, filler(name) * (2 * max_chars(name) + 1), title=title).codes())


if __name__ == "__main__":
    unittest.main()
