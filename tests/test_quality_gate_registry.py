"""레지스트리의 새 설정 두 개 — chance.quality_gate(off·hold, 기본 off)와 chance.languages(["ko","en"] 기본·["ko"])의 값 검증과 읽기.

기본값(필드 없음)에서는 이전과 같다: 실제 레지스트리에는 quality_gate 가 없고 languages 는 이미 있던 ["ko","en"] 이다(이 변경이 레지스트리 값을 바꾸지 않는다).
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from pipeline import quality_gate as qg, registry
from registry_states import pre_flip_registry


def real():
    """변이의 바탕: 켜기 전 고정 표본(켜기 전 진짜 레지스트리와 같은 사본) — 켜는 변경(T3) 뒤의 진짜 값(국문 단독·콘텐츠 출처 facts)이 이 파일의 값 검증·읽기 시험을 흔들지 않게 한다. 진짜 값을 못박는 시험은 `registry.load_registry()` 를 직접 읽는다."""
    return pre_flip_registry()


def chance_entry(reg):
    return next(b for b in reg["blogs"] if b["key"] == "chance")


def errors_for(change):
    reg = copy.deepcopy(real())
    change(chance_entry(reg))
    return registry.validate_registry(reg)


class RealRegistryUnchangedTest(unittest.TestCase):
    def test_the_real_registry_has_no_quality_gate_and_is_korean_only(self):
        """켜는 변경(T3, 패치 02) 뒤: 진짜 레지스트리의 Chance 항목은 Gate 값이 없고(꺼짐) 국문 단독이다(전에는 두 언어). 진짜 파일을 직접 읽는다(real() 은 고정 표본이다)."""
        reg = registry.load_registry()
        entry = chance_entry(reg)
        self.assertNotIn("quality_gate", entry)
        self.assertEqual(entry["languages"], ["ko"])
        self.assertEqual(registry.validate_registry(reg), [])

    def test_the_default_settings_are_off_and_korean_only(self):
        self.assertEqual(registry.chance_settings(), ("off", ("ko",)))

    def test_the_allowed_values_match_the_gate_module(self):
        self.assertEqual([tuple(s) for s in registry.CHANCE_LANGUAGE_SETS], list(qg.LANGUAGE_SETS))
        self.assertEqual(tuple(registry.DEFAULT_CHANCE_LANGUAGES), qg.DEFAULT_LANGUAGES)
        self.assertEqual(registry.QUALITY_GATE_MODES, ("off", "hold"))
        self.assertEqual(registry.DEFAULT_QUALITY_GATE, "off")


class ValidationTest(unittest.TestCase):
    def test_off_and_hold_are_valid_for_chance(self):
        for value in ("off", "hold"):
            with self.subTest(value=value):
                self.assertEqual(errors_for(lambda blog: blog.update(quality_gate=value)), [])

    def test_other_quality_gate_values_are_errors(self):
        for value in ("on", "shadow", "HOLD", "", None, True, 1, ["hold"]):
            with self.subTest(value=value):
                errors = errors_for(lambda blog: blog.update(quality_gate=value))
                self.assertTrue(any("quality_gate는" in e for e in errors), errors)

    def test_quality_gate_is_only_for_jekyll_git(self):
        reg = copy.deepcopy(real())
        blogger = next(b for b in reg["blogs"] if b.get("platform") == "blogger")
        blogger["quality_gate"] = "hold"
        self.assertTrue(any("platform jekyll-git 에서만" in e and "quality_gate" in e for e in registry.validate_registry(reg)))

    def test_chance_languages_allowed_values_in_either_order(self):
        """합집합 규칙: ko 를 포함하고 ko·en 만 겹침 없이 든 목록이면 순서와 상관없이 올바르다(제한 재개 잠금 L6 이 허용하는 집합과 같다)."""
        for value in (["ko", "en"], ["en", "ko"], ["ko"]):
            with self.subTest(value=value):
                self.assertEqual(errors_for(lambda blog: blog.update(languages=value)), [])

    def test_chance_languages_other_values_are_errors(self):
        for value in (["en"], ["ko", "en", "ja"], ["ko", "ko"], ["en", "en"], ["ja"], "ko", [], None, [1], ["ko", 1], ("ko",), {"ko": 1}, "ko,en"):
            with self.subTest(value=value):
                self.assertTrue(errors_for(lambda blog: blog.update(languages=value)), value)

    def test_the_single_definition_of_the_allowed_languages(self):
        """허용 값의 단일 정의처는 quality_gate.normalize_languages 다 — 레지스트리 검증기·chance_settings 가 이 함수를 쓰고 순서가 달라도 같은 정규 튜플이 나온다."""
        self.assertEqual(qg.normalize_languages(["ko", "en"]), ("ko", "en"))
        self.assertEqual(qg.normalize_languages(["en", "ko"]), ("ko", "en"))
        self.assertEqual(qg.normalize_languages(("en", "ko")), ("ko", "en"))
        self.assertEqual(qg.normalize_languages(["ko"]), ("ko",))
        for bad in (["en"], [], ["ko", "ko"], ["ko", "en", "ja"], ["ja"], "ko", None, 5, ["ko", None], [["ko"]], {"ko"}, ["KO"], ["ko", "EN"]):
            with self.subTest(bad=bad):
                self.assertIsNone(qg.normalize_languages(bad))

    def test_other_platforms_keep_their_free_languages_field(self):
        reg = copy.deepcopy(real())
        others = [b for b in reg["blogs"] if b.get("platform") != "jekyll-git"]
        self.assertTrue(others)
        for blog in others:        # jekyll-git 의 허용 목록 밖의 값(여기서는 'ja' 를 더한 것)도 다른 플랫폼에서는 표시·프로필 대조용이라 오류가 아니다
            blog["languages"] = list(blog["languages"]) + ["ja"]
        self.assertEqual(registry.validate_registry(reg), [])


class ReadingTest(unittest.TestCase):
    def read_with(self, **fields):
        reg = copy.deepcopy(real())
        chance_entry(reg).update(fields)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blogs.json"
            path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
            return registry.chance_settings(path)

    def test_values_are_read(self):
        self.assertEqual(self.read_with(languages=["en", "ko"]), ("off", ("ko", "en")))              # 순서가 달라도 같은 정규 튜플
        self.assertEqual(self.read_with(quality_gate="hold"), ("hold", ("ko", "en")))
        self.assertEqual(self.read_with(quality_gate="hold", languages=["ko"]), ("hold", ("ko",)))
        self.assertEqual(self.read_with(languages=["ko"]), ("off", ("ko",)))
        self.assertEqual(self.read_with(quality_gate="off"), ("off", ("ko", "en")))

    def test_a_field_that_is_not_written_means_the_default(self):
        reg = copy.deepcopy(real())
        entry = chance_entry(reg)
        for field in ("quality_gate", "languages"):
            entry.pop(field, None)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blogs.json"
            path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(registry.chance_settings(path), ("off", ("ko", "en")))

    def test_a_wrong_value_stops_instead_of_falling_back_to_a_weaker_setting(self):
        for fields in ({"quality_gate": "HOLD"}, {"quality_gate": None}, {"quality_gate": 1}, {"languages": ["en"]}, {"languages": "ko"}, {"languages": ["ko", "ja"]}):
            with self.subTest(fields=fields):
                with self.assertRaises(registry.RegistryError):
                    self.read_with(**fields)

    def test_an_unreadable_registry_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "none.json"
            with self.assertRaises(registry.RegistryError):
                registry.chance_settings(missing)
            broken = Path(tmp) / "broken.json"
            broken.write_text("{ 깨진 JSON", encoding="utf-8")
            with self.assertRaises(registry.RegistryError):
                registry.chance_settings(broken)

    def test_an_unknown_blog_key_raises(self):
        with self.assertRaises(registry.RegistryError):
            registry.chance_settings(key="nope")


if __name__ == "__main__":
    unittest.main()
