"""진짜 저장소 검증기 결과를 나눠 쓰는 도우미(`tests/real_repo_helpers.py`)의 시험 — 속도를 위해 한 번만 계산해 나눠 쓰는 값이 새로 계산한 값과 같고, 받는 쪽이 고쳐도 새지 않고,
트리나 검증기가 바뀌면 다시 계산한다는 것을 작은 임시 트리로 확인한다(진짜 저장소에 검증기를 다시 돌리지 않는다 — 그 값은 이 도우미를 쓰는 네 시험이 확인한다)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import real_repo_helpers as helpers

vr = helpers.vr


def shown(findings):
    return [(f.level, f.check, f.message, f.path) for f in findings]


class SharedValueTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "token.json").write_text("{}", encoding="utf-8")                               # SEC-1: 금지 파일 이름
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.md").write_text("[깨진 링크](./none.md)\n", encoding="utf-8")      # DOC-1: 깨진 링크(경고)
        patcher = mock.patch.dict(helpers._SHARED, clear=True)                                       # 이 시험만의 빈 저장소(끝나면 원래 값으로 돌아간다)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_shared_value_equals_a_fresh_computation(self):
        fresh = shown(vr.run_checks(self.root))
        self.assertIn("SEC-1", [check for _level, check, _message, _path in fresh], fresh)           # 시험이 속이 비지 않았다(지적이 실제로 있다)
        self.assertIn("DOC-1", [check for _level, check, _message, _path in fresh], fresh)
        self.assertEqual(shown(helpers.run_checks_once(self.root)), fresh)
        self.assertEqual(shown(helpers.run_checks_once(self.root)), fresh)                           # 둘째 호출(나눠 쓰는 값)도 같다
        self.assertEqual(shown(helpers.run_checks_once(str(self.root))), fresh)                      # 문자열 경로도 같은 값

    def test_the_second_call_reads_the_shared_value_and_does_not_run_the_validator_again(self):
        with mock.patch.object(vr, "run_checks", wraps=vr.run_checks) as spy:
            first = helpers.run_checks_once(self.root)
            second = helpers.run_checks_once(self.root)
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(shown(first), shown(second))
        self.assertGreaterEqual(len(first), 2)

    def test_a_caller_cannot_change_the_shared_value(self):
        first = helpers.run_checks_once(self.root)
        want = shown(first)
        self.assertGreaterEqual(len(first), 2)
        first[0].message = "받는 쪽이 고친 글"
        first[0].level = "WARN"
        first.append(vr.err("X-9", "받는 쪽이 끼워 넣은 지적"))
        again = helpers.run_checks_once(self.root)
        self.assertEqual(shown(again), want)
        again.clear()
        self.assertEqual(shown(helpers.run_checks_once(self.root)), want)

    def test_a_changed_tree_is_computed_again(self):
        before = helpers.run_checks_once(self.root)
        (self.root / "id_rsa").write_text("x", encoding="utf-8")                                     # 새 금지 파일
        added = helpers.run_checks_once(self.root)
        self.assertEqual(len(added), len(before) + 1)
        self.assertEqual(shown(added), shown(vr.run_checks(self.root)))
        (self.root / "docs" / "a.md").write_text("[깨진 링크](./none-at-all.md)\n", encoding="utf-8")   # 크기가 다른 고침
        edited = helpers.run_checks_once(self.root)
        self.assertEqual(shown(edited), shown(vr.run_checks(self.root)))
        self.assertTrue(any("none-at-all.md" in message for _level, _check, message, _path in shown(edited)))
        self.assertFalse(any("none.md" in message and "none-at-all.md" not in message for _level, _check, message, _path in shown(edited)))

    def test_a_patched_validator_has_its_own_value_and_the_patch_does_not_leak(self):
        plain = shown(helpers.run_checks_once(self.root))
        marker = ("ERROR", "X-1", "패치된 검사", "")
        with mock.patch.object(vr, "check_agent_files", return_value=[vr.err("X-1", "패치된 검사")]):
            patched = shown(helpers.run_checks_once(self.root))
        self.assertIn(marker, patched)
        self.assertNotIn(marker, plain)
        self.assertEqual(shown(helpers.run_checks_once(self.root)), plain)                           # 패치가 끝난 뒤에는 패치 때의 값이 아니다
        with mock.patch.object(vr, "MAX_TEXT_BYTES", 12345):                                         # 상수 하나를 바꿔도 검증기 상태가 달라진다(이 시험은 PyYAML 유무와 상관없다)
            changed_state = helpers.validator_state()
        self.assertNotEqual(changed_state, helpers.validator_state())
        self.assertEqual(helpers.validator_state(), helpers.validator_state())                       # 바꾸지 않았으면 같은 값(열쇠가 흔들리지 않는다)

    def test_different_roots_and_bases_have_different_keys(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        other = Path(tmp.name)
        (other / "readme.md").write_text("안녕\n", encoding="utf-8")
        self.assertNotEqual(shown(helpers.run_checks_once(other)), shown(helpers.run_checks_once(self.root)))
        with_base = helpers.run_checks_once(self.root, "0" * 40)                                      # 0 으로만 된 기준은 광고 표면 검사를 건너뛴다 — 같은 값이지만 열쇠는 따로다
        self.assertEqual(shown(with_base), shown(helpers.run_checks_once(self.root)))
        self.assertEqual(len({key[:2] for key in helpers._SHARED}), 3)                                # (경로, 기준) 조합이 셋

    def test_a_same_size_edit_in_the_same_clock_tick_is_computed_again(self):
        """크기·수정 시각만 지문으로 삼으면 같은 크기의 제자리 수정이 같은 시각 눈금 안에 일어나거나 수정 시각이 되돌려졌을 때 낡은 값을 준다 — 지문이 내용을 본다.
        임시 사본에서 같은 크기로 내용만 바꾸고 수정 시각을 처음 값으로 되돌려 이 경우를 만든다."""
        page = self.root / "docs" / "a.md"
        before = shown(helpers.run_checks_once(self.root))
        info = page.stat()
        page.write_text("[깨진 링크](./nope.md)\n", encoding="utf-8")                                     # none → nope: 바이트 수가 같다
        os.utime(page, ns=(info.st_atime_ns, info.st_mtime_ns))                                           # 수정 시각도 처음 값으로 되돌린다
        again = page.stat()
        self.assertEqual((again.st_size, again.st_mtime_ns), (info.st_size, info.st_mtime_ns))            # 크기도 시각도 그대로 — 내용만 다르다
        after = shown(helpers.run_checks_once(self.root))
        self.assertNotEqual(after, before)
        self.assertTrue(any("nope.md" in message for _level, _check, message, _path in after), after)
        self.assertEqual(after, shown(vr.run_checks(self.root)))

    def test_the_stamp_follows_size_and_clock_only_for_files_over_the_validators_size_limit(self):
        """검증기가 읽지 않는 큰 파일(한도 `MAX_TEXT_BYTES` 초과)은 내용 대신 (크기, 수정 시각)을 지문에 넣는다 — 수정 시각이 바뀌면 지문이 달라진다. 한도 안의 파일은 수정 시각이 아니라 내용이 지문이다."""
        big = self.root / "docs" / "big.md"
        big.write_text("가" * 40, encoding="utf-8")
        with mock.patch.object(vr, "MAX_TEXT_BYTES", 20):                                                 # 이 시험에서만 한도를 20바이트로 낮춰 big.md(120바이트)를 '큰 파일'로 만든다
            first = helpers.tree_stamp(self.root)
            self.assertEqual(helpers.tree_stamp(self.root), first)
            info = big.stat()
            os.utime(big, ns=(info.st_atime_ns, info.st_mtime_ns + 5_000_000_000))
            self.assertNotEqual(helpers.tree_stamp(self.root), first)
        small = self.root / "docs" / "a.md"
        base_stamp = helpers.tree_stamp(self.root)
        info = small.stat()
        os.utime(small, ns=(info.st_atime_ns, info.st_mtime_ns + 5_000_000_000))
        self.assertEqual(helpers.tree_stamp(self.root), base_stamp)                                       # 내용이 같으면 시각만 달라도 지문은 같다(괜한 재계산이 없다)

    def test_a_real_base_is_never_shared_because_the_validator_then_reads_the_git_history(self):
        with mock.patch.object(vr, "run_checks", wraps=vr.run_checks) as spy:
            first = helpers.run_checks_once(self.root, "a" * 40)
            second = helpers.run_checks_once(self.root, "a" * 40)
            zeros = helpers.run_checks_once(self.root, "0" * 40)
            zeros_again = helpers.run_checks_once(self.root, "0" * 40)
        self.assertEqual(spy.call_count, 3)                                                               # 실제 기준은 두 번 다 계산하고, 0 으로만 된 기준은 한 번만 계산해 나눈다
        self.assertEqual(shown(first), shown(second))
        self.assertEqual(shown(zeros), shown(zeros_again))
        self.assertIsNot(first, second)


if __name__ == "__main__":
    unittest.main()
