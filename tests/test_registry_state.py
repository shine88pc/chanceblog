"""레지스트리 상태 가드(S2BFIX, 결정 D-308): 진짜 `pipeline/blogs.json`·`pipeline/source_registry.json` 은 알려진 상태(켜기 전·p2·p3 — `tests/registry_states.py`) 중 정확히 하나이고
`EXPECTED_STATE` 가 그것이다. 켜기 전 경로를 시험하는 클래스는 고정 표본(`tests/fixtures/registry_states/pre_flip_blogs.json`)을 쓰므로, 이 가드가 '표본이 진짜 값과 어긋난 채 시험이 가짜로 초록이 되는 일'을 막는다:
 - 진짜 레지스트리가 슬쩍 바뀌면(알려진 상태가 아니면) 이 시험이 빨개진다 — 켜는 변경이면 `EXPECTED_STATE` 를 한 칸 옮기고, 그 밖의 변경이면 고정 표본을 진짜 값에 맞춘다.
 - 알려진 상태 셋은 모두 유효한 레지스트리여야 한다(켜는 값이 검증을 통과하는지를 켜기 전에 미리 본다).
네트워크·시계·진짜 키를 쓰지 않는다."""
import json
import unittest

import _bootstrap  # noqa: F401
import registry_states as RS
from pipeline import publish_lock, registry


def real_blogs():
    return json.loads(RS.REAL_BLOGS.read_text(encoding="utf-8"))


class KnownStatesTest(unittest.TestCase):
    def test_the_real_registry_is_exactly_the_expected_known_state(self):
        self.assertIn(RS.EXPECTED_STATE, RS.STATE_NAMES)
        self.assertEqual(real_blogs(), RS.state_registry(RS.EXPECTED_STATE),
                         f"진짜 pipeline/blogs.json 이 기대 상태({RS.EXPECTED_STATE})와 다르다 — 켜는 변경이면 tests/registry_states.py 의 EXPECTED_STATE 를 한 칸 옮기고, 그 밖의 변경이면 고정 표본을 진짜 값에 맞춘다")

    def test_only_the_expected_state_matches_the_real_registry(self):
        real = real_blogs()
        self.assertEqual([name for name in RS.STATE_NAMES if real == RS.state_registry(name)], [RS.EXPECTED_STATE])

    def test_the_real_allowlist_enables_exactly_the_providers_of_the_expected_state(self):
        data = json.loads(RS.REAL_SOURCES.read_text(encoding="utf-8"))
        enabled = [item["provider_id"] for item in data["providers"] if item["enabled"] is not False]
        self.assertEqual(enabled, RS.ENABLED_PROVIDERS[RS.EXPECTED_STATE])

    def test_every_known_state_is_a_valid_registry(self):
        for name in RS.STATE_NAMES:
            with self.subTest(state=name):
                self.assertEqual(registry.validate_registry(RS.state_registry(name)), [])

    def test_the_states_differ_only_where_the_flip_changes_values(self):
        before, after_values, after_lock = (RS.state_registry(name) for name in RS.STATE_NAMES)
        self.assertEqual([publish_lock.lock_state(reg) for reg in (before, after_values, after_lock)], ["off", "off", "on"])
        chance_before, chance_values, chance_lock = (RS.chance_of(reg) for reg in (before, after_values, after_lock))
        self.assertEqual({key for key in chance_values if chance_before.get(key) != chance_values[key]} | (set(chance_before) - set(chance_values)),
                         {"languages", "publish_flow", "source_policy", "content_source", "limits"})
        self.assertEqual({key for key in chance_lock if chance_values.get(key) != chance_lock[key]}, {"quality_gate", "limits"})
        others = [blog for blog in before["blogs"] if blog["key"] != "chance"]
        self.assertEqual(others, [blog for blog in after_lock["blogs"] if blog["key"] != "chance"])         # Chance 말고 다른 항목은 어느 상태에서도 그대로다

    def test_the_fixture_is_the_pre_flip_sample_and_the_helpers_return_it(self):
        from lock_helpers import today_registry
        self.assertEqual(today_registry(), RS.pre_flip_registry())
        self.assertEqual(RS.state_registry("pre_flip"), RS.pre_flip_registry())
        self.assertNotIn("content_source", json.dumps(RS.pre_flip_registry()))
        self.assertNotIn("resume_lock", RS.pre_flip_registry())


if __name__ == "__main__":
    unittest.main()
