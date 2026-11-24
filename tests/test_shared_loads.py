"""속도를 위해 나눠 쓰는 워크플로 읽기(`test_workflow_names.load_shared`)와 Blogger 워크플로 계산 도우미(`blogger_workflow_helpers`)의 시험 — 나눠 쓰는 값이 매번 새로 읽은 것과 같고,
옛 `load` 는 그대로 매번 새로 읽고, 파일 글이 바뀌면 `load_shared` 도 새로 읽고, 계산 도우미가 새로 읽는 길과 같은 값을 낸다."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML 이 없는 환경(CI 에는 항상 있다)
    yaml = None
if yaml is not None:        # PyYAML 이 있으면 도우미 모듈을 그냥 불러온다 — 거기서 나는 진짜 ImportError 는 건너뜀으로 바뀌지 않고 그대로 드러난다
    import blogger_workflow_helpers as wf
    import test_workflow_names as names
else:
    wf = names = None
NEEDS_YAML = unittest.skipUnless(yaml is not None, "PyYAML(requirements-dev.txt)이 필요합니다(CI 에서는 항상 실행됩니다)")


def fresh_load(name):
    """`load` 가 나눠 쓰기 전에 하던 일 그대로(읽고 파싱하고 `on` 을 되돌린다)."""
    data = yaml.safe_load((names.WORKFLOWS / name).read_text(encoding="utf-8"))
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


@NEEDS_YAML
class SharedLoadTest(unittest.TestCase):
    def test_load_shared_equals_a_fresh_parse_and_load_is_unchanged_for_every_real_workflow(self):
        paths = names.workflow_paths()
        self.assertGreaterEqual(len(paths), 15)
        for path in paths:
            with self.subTest(path.name):
                fresh = fresh_load(path.name)
                self.assertEqual(names.load(path.name), fresh)
                self.assertEqual(names.load_shared(path.name), fresh)
                self.assertEqual(names.load_shared(path.name), fresh)                 # 나눠 쓰는 값(둘째 호출)도 같다

    def test_load_shared_is_one_object_and_load_still_reads_a_new_one_each_time(self):
        first = names.load("blogger.yml")
        want = copy.deepcopy(first)
        self.assertIsNot(first, names.load("blogger.yml"))                              # 옛 `load` 는 매번 새로 읽는다
        self.assertIs(names.load_shared("blogger.yml"), names.load_shared("blogger.yml"))
        first["name"] = "받는 쪽이 고친 이름"
        first["jobs"].clear()
        first["on"]["workflow_call"] = None
        self.assertEqual(names.load("blogger.yml"), want)                               # `load` 가 준 것을 고쳐도 다음 `load` 로 새지 않는다
        self.assertEqual(names.load_shared("blogger.yml"), want)                        # 나눠 쓰는 원본도 그대로다

    def test_a_changed_file_is_read_again_by_load_shared(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(names, "WORKFLOWS", Path(tmp)):
            target = Path(tmp) / "x.yml"
            target.write_text("name: 하나\non:\n  push:\njobs: {}\n", encoding="utf-8")
            self.assertEqual(names.load_shared("x.yml")["name"], "하나")
            target.write_text("name: 둘\non:\n  push:\njobs: {}\n", encoding="utf-8")
            self.assertEqual(names.load_shared("x.yml")["name"], "둘")
            self.assertEqual(names.load("x.yml")["name"], "둘")

    def test_a_missing_file_still_raises(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(names, "WORKFLOWS", Path(tmp)):
            for loader in (names.load, names.load_shared):
                with self.assertRaises(FileNotFoundError):
                    loader("none.yml")


@NEEDS_YAML
class BloggerHelperTest(unittest.TestCase):
    """계산 도우미(`wrapper_with`·`callee_env`·`end_to_end_env`)가 읽기 전용 읽기를 써도, 매번 새로 읽는 길(`load`)을 쓸 때와 같은 값을 낸다."""

    COMBOS = (("schedule", {}), ("schedule", {"dry_run": "true", "publish": "publish", "auth_check": "true", "topic": "x"}), ("workflow_dispatch", {}),
              ("workflow_dispatch", {"dry_run": "true", "publish": "draft", "auth_check": "false", "topic": "직접 정한 주제"}), ("workflow_dispatch", {"publish": "off", "auth_check": "true"}))

    def test_the_calculation_equals_the_one_that_reads_the_files_fresh_each_time(self):
        shared = {(wrapper, event, repr(combo)): (wf.wrapper_with(wrapper, event, combo), wf.end_to_end_env(wrapper, event, combo))
                  for wrapper in wf.WRAPPERS.values() for event, combo in self.COMBOS}
        self.assertEqual(len(shared), 2 * len(self.COMBOS))
        with mock.patch.object(wf, "load_shared", wf.load):                          # 같은 계산을 매번 깊은 복사본으로 읽는 길로
            fresh = {(wrapper, event, repr(combo)): (wf.wrapper_with(wrapper, event, combo), wf.end_to_end_env(wrapper, event, combo))
                     for wrapper in wf.WRAPPERS.values() for event, combo in self.COMBOS}
        self.assertEqual(shared, fresh)

    def test_the_public_helpers_still_hand_out_data_that_can_be_changed(self):
        for wrapper in wf.WRAPPERS.values():
            job_id, job = wf.call_job(wrapper)
            job["with"]["topic"] = "받는 쪽이 고친 값"
            job["with"].clear()
            self.assertTrue(wf.call_job(wrapper)[1]["with"], wrapper)
            self.assertEqual(wf.wrapper_with(wrapper, "schedule")["topic"], "", wrapper)
        plan_step, generate, run_step = wf.callee_steps()
        plan_step["env"].clear()
        generate["env"].clear()
        self.assertTrue(wf.callee_steps()[0]["env"])
        self.assertTrue(wf.callee_steps()[1]["env"])
        self.assertEqual(wf.end_to_end_env("blogger-en.yml", "schedule")["ONLY_BLOG"], "blogger_macat")


if __name__ == "__main__":
    unittest.main()
