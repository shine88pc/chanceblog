"""연습 실행(DRY_RUN)의 켜짐 값이 읽는 곳마다 같고, 이미지 교체(FIX_IMAGES)는 옛 집합을 그대로 둔다(독립 감사 BP-S2 N4·독립 검증 BFIX1-S R2, 결함 D-473). 네트워크 없이 돈다.

옛 모습: 생성기(generator.py)의 `_flag` 는 {1, true, yes} 만 켜짐으로 읽었고 Blogger 러너(pipeline/run.py)의 `_flag`·초안 올리기(pipeline/draft_flow.py)의 `truthy` 는 {1, true, yes, on} 을 읽었다 —
`DRY_RUN=on` 이면 러너·초안 올리기는 연습으로 읽는데 생성기는 연습이 아니라고 읽어 실제로 글을 만들었다(워크플로는 '1'·'0'·'true'·'false' 만 넘겨 지금은 닿지 않는 값이다). 이제 셋 다
정지 변수 읽기와 같은 한 곳의 집합(pipeline/pause.py 의 ON_VALUES)을 쓴다. 이 시험은 ① 집합의 내용 ② 값 표에서 셋이 같은 판정을 한다 ③ 셋이 자기만의 집합을 다시 만들지 않는다를 본다. 쓰는 쪽 스위치인 FIX_IMAGES 는 옛 집합(1·true·yes)을 그대로 둔다 — on 을 켜짐으로 읽지 않는다(④).
"""
import importlib.util
import inspect
import os
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import generator as g
from pipeline import draft_flow, pause
from pipeline import run as run_mod

ON = ("1", "true", "yes", "on")
VALUES = ON + ("True", "TRUE", "Yes", "YES", "On", "ON", " on ", "\ton\n", " 1 ") + (
    "0", "false", "no", "off", "", "  ", "maybe", "2", "truee", "enabled", "y", "t", "onn", "o n", "on1", "1on", "on" + chr(0x200B))


def expected(value):
    return value.strip().lower() in set(ON)


class OneSetOfOnValuesTest(unittest.TestCase):
    def test_the_canonical_set_is_these_four(self):
        self.assertEqual(pause.ON_VALUES, frozenset(ON))
        self.assertEqual(run_mod._TRUE, set(ON))                                           # 러너의 옛 이름(시험이 쓰는 것)은 같은 내용이다

    def test_the_three_readers_agree_on_every_value_and_with_the_canonical_set(self):
        for value in VALUES:
            with self.subTest(value=value):
                with mock.patch.dict(os.environ, {"DRY_RUN": value}):
                    generator_says = g._flag("DRY_RUN")
                runner_says = run_mod._flag({"DRY_RUN": value}, "DRY_RUN")
                uploader_says = draft_flow.truthy(value)
                self.assertEqual((generator_says, runner_says, uploader_says), (expected(value),) * 3)

    def test_the_value_that_used_to_differ_is_now_a_practice_run_everywhere(self):
        """DRY_RUN=on: 러너와 초안 올리기는 연습으로 읽었는데 생성기는 읽지 않았다 — 연습(= 글을 올리지 않는) 쪽으로 맞췄다. 이미지 교체(FIX_IMAGES)는 다르다 — 아래 FixImagesKeepsTheOldSetTest."""
        with mock.patch.dict(os.environ, {"DRY_RUN": "on"}):
            self.assertTrue(g._flag("DRY_RUN"))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DRY_RUN", None)
            self.assertFalse(g._flag("DRY_RUN"))                                           # 없으면 꺼짐(옛 기본 그대로)

    def test_a_missing_variable_is_off_in_all_three(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DRY_RUN", None)
            self.assertFalse(g._flag("DRY_RUN"))
        self.assertFalse(run_mod._flag({}, "DRY_RUN"))
        self.assertFalse(draft_flow.truthy(None))
        self.assertFalse(draft_flow.truthy(""))

    def test_none_of_the_three_keeps_a_private_copy_of_the_set(self):
        """생성기의 `_flag` 와 초안 올리기의 `truthy` 는 함수 안에서 pause.ON_VALUES 를 쓰고, 러너는 모듈 상수 `_TRUE`(시험이 쓰는 옛 이름)를 같은 집합으로 만든다 — 낱말을 따로 적은 집합이 없다."""
        for label, function in (("generator._flag", g._flag), ("draft_flow.truthy", draft_flow.truthy)):
            with self.subTest(label):
                source = inspect.getsource(function)
                self.assertIn("pause.ON_VALUES", source)
                for literal in ('"yes"', "'yes'", '"true"', "'true'"):
                    self.assertNotIn(literal, source, literal)
        self.assertIn("_TRUE", inspect.getsource(run_mod._flag))
        assignment = [line for line in inspect.getsource(run_mod).split(chr(10)) if line.startswith("_TRUE =")]
        self.assertEqual(len(assignment), 1)
        self.assertIn("set(pause.ON_VALUES)", assignment[0])
        for literal in ('"yes"', "'yes'", '"true"', "'true'"):
            self.assertNotIn(literal, assignment[0], literal)


def fresh_generator(env):
    """생성기 파일을 새 모듈로 한 번 더 실행해 환경 변수 `env` 에서 모듈 수준 값(DRY_RUN·FIX_IMAGES)을 다시 읽는다 — 이미 불러온 모듈과 다른 시험은 건드리지 않는다."""
    spec = importlib.util.spec_from_file_location("generator_fix_images_probe", g.__file__)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, env):
        spec.loader.exec_module(module)
    return module


class FixImagesKeepsTheOldSetTest(unittest.TestCase):
    """이미지 교체(FIX_IMAGES)는 기존 글의 이미지를 직접 커밋으로 바꾸는 쓰는 쪽 스위치라 켜짐 값 집합을 넓히지 않는다 — 옛 집합(1·true·yes)이고 `on` 은 켜짐이 아니다(독립 검증 BFIX1-S R2)."""

    def test_the_set_is_the_old_three_and_stays_inside_the_pause_set(self):
        self.assertEqual(g.FIX_IMAGES_ON_VALUES, frozenset({"1", "true", "yes"}))
        self.assertLess(g.FIX_IMAGES_ON_VALUES, pause.ON_VALUES)
        self.assertEqual(pause.ON_VALUES - g.FIX_IMAGES_ON_VALUES, frozenset({"on"}))        # 둘의 차이는 on 하나뿐이다

    def test_on_is_not_a_switch_on_for_fix_images_but_is_one_for_dry_run(self):
        """실제 모듈 수준 값으로 본다: FIX_IMAGES=on 은 꺼짐, DRY_RUN=on 은 켜짐(덜 올리는 쪽)."""
        for value, fix_images, dry_run in (("on", False, True), (" ON ", False, True), ("1", True, True), ("true", True, True), ("YES", True, True), (" yes ", True, True),
                                           ("enabled", False, False), ("off", False, False), ("0", False, False), ("", False, False), ("maybe", False, False)):
            with self.subTest(value=value):
                module = fresh_generator({"FIX_IMAGES": value, "DRY_RUN": value})
                self.assertEqual((module.FIX_IMAGES, module.DRY_RUN), (fix_images, dry_run), value)

    def test_the_module_lines_pass_the_old_set_only_to_fix_images(self):
        lines = [line.split("#")[0].strip() for line in inspect.getsource(g).split(chr(10)) if line.startswith(("DRY_RUN = ", "FIX_IMAGES = "))]
        self.assertEqual(lines, ['DRY_RUN = _flag("DRY_RUN")', 'FIX_IMAGES = _flag("FIX_IMAGES", FIX_IMAGES_ON_VALUES)'])


if __name__ == "__main__":
    unittest.main()
