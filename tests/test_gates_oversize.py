"""본문이 길이 한도의 두 배를 넘으면 금지 표현 정규식을 돌리지 않고 곧바로 탈락시킨다(BP-S1-5, 결함 D-415) — 정규식의 제곱 시간(가용성) 닫기. 네트워크 없이 돈다.

배경: Blogger·네이버 프로필의 금지 표현 정규식(`\\d+…`·이메일 모양 `[A-Za-z0-9._%+\\-]+@…`)은 같은 종류 글자가 길게 이어지면 시작 위치마다 다시 먹어 글 길이의 제곱으로 느려진다
(감사 측정: 숫자 20,000자 48초·대시 30,000자 6.9초). 길이 한도(length.max_chars)는 [LEN_LONG] 사유로 쌓이기만 하고 정규식은 한도를 넘는 글에 그대로 돌았다 — 모델이 같은 글자를 길게 되풀이하는
고장이 나면 정기 실행이 15분 제한까지 붙들리고 시도 3번을 모두 썼다(게시되지는 않는다 — 가용성 문제). 이제 `check_post` 가 본문이 한도의 두 배를 넘는 글을 맨 앞에서 탈락시킨다(어차피 탈락).
프로필 JSON 의 정규식 값은 고치지 않았다(운영자 판단 — 보고서 제안). 정상 길이 글의 판정은 이전과 같다(기존 test_gates* 가 지킨다).
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


if __name__ == "__main__":
    unittest.main()
