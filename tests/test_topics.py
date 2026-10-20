import json
import random
import unittest
from datetime import date

import _bootstrap  # noqa: F401
from pipeline import registry, topics

PROFILE = registry.load_profile("blogger_practical_ko")
TODAY = date(2026, 10, 21)
SEEDS = PROFILE["seed_topics"]


class PickTopicTest(unittest.TestCase):
    def test_picks_a_seed_when_history_is_empty(self):
        topic, source = topics.pick_topic(PROFILE, [], TODAY, [], random.Random(1))
        self.assertEqual(source, "seed")
        self.assertIn(topic, SEEDS)

    def test_same_seed_for_same_rng_is_deterministic(self):
        a = topics.pick_topic(PROFILE, [], TODAY, [], random.Random(7))
        b = topics.pick_topic(PROFILE, [], TODAY, [], random.Random(7))
        self.assertEqual(a, b)

    def test_cooldown_excludes_recently_used_seeds(self):
        history = [{"topic": t, "date": "2026-10-20"} for t in SEEDS[:-1]]
        topic, source = topics.pick_topic(PROFILE, history, TODAY, [], random.Random(3))
        self.assertEqual((topic, source), (SEEDS[-1], "seed"))

    def test_old_history_is_outside_cooldown(self):
        history = [{"topic": t, "date": "2026-01-01"} for t in SEEDS]
        topic, source = topics.pick_topic(PROFILE, history, TODAY, [], random.Random(3))
        self.assertEqual(source, "seed")

    def test_exhausted_without_llm(self):
        history = [{"topic": t, "date": "2026-10-20"} for t in SEEDS]
        self.assertEqual(topics.pick_topic(PROFILE, history, TODAY, [], random.Random(3)), (None, "exhausted"))

    def test_other_blog_titles_block_similar_seeds(self):
        avoid = SEEDS[:-1]
        topic, source = topics.pick_topic(PROFILE, [], TODAY, avoid, random.Random(5))
        self.assertEqual(topic, SEEDS[-1])

    def test_llm_expansion_is_filtered_by_the_same_rules(self):
        history = [{"topic": t, "date": "2026-10-20"} for t in SEEDS]
        reply = json.dumps(["임신 중 안전하게 하는 운동 방법", "짧아", SEEDS[0],
                            "퇴근길 15분 가볍게 걷고 저녁을 편하게 시작하는 습관"], ensure_ascii=False)
        topic, source = topics.pick_topic(PROFILE, history, TODAY, [], random.Random(1),
                                          llm=lambda prompt: (reply, "m"))
        self.assertEqual(source, "llm")
        self.assertEqual(topic, "퇴근길 15분 가볍게 걷고 저녁을 편하게 시작하는 습관")

    def test_llm_failure_is_reported(self):
        history = [{"topic": t, "date": "2026-10-20"} for t in SEEDS]

        def boom(prompt):
            raise RuntimeError("down")
        self.assertEqual(topics.pick_topic(PROFILE, history, TODAY, [], random.Random(1), llm=boom),
                         (None, "expand_failed"))

    def test_llm_garbage_gives_exhausted(self):
        history = [{"topic": t, "date": "2026-10-20"} for t in SEEDS]
        self.assertEqual(topics.pick_topic(PROFILE, history, TODAY, [], random.Random(1),
                                           llm=lambda prompt: ("죄송합니다", "m")), (None, "exhausted"))


class ParsingTest(unittest.TestCase):
    def test_parse_topic_list(self):
        self.assertEqual(topics.parse_topic_list('```json\n["가 나 다 라 마 바 사 아", "가 나 다 라 마 바 사 아", 3]\n```'),
                         ["가 나 다 라 마 바 사 아"])
        self.assertEqual(topics.parse_topic_list("설명만 있음"), [])
        self.assertEqual(topics.parse_topic_list('{"a": 1}'), [])
        self.assertEqual(topics.parse_topic_list("[깨진 json"), [])

    def test_clean_topic(self):
        self.assertEqual(topics.clean_topic('  "여러 줄\n주제"  '), "여러 줄 주제")
        self.assertEqual(len(topics.clean_topic("가" * 500)), 120)
        self.assertEqual(topics.clean_topic(None), "")

    def test_recently_used_ignores_bad_entries(self):
        history = ["문자열", {"topic": "x"}, {"topic": "같은 주제 글", "date": "not-a-date"}]
        self.assertFalse(topics.recently_used("같은 주제 글", history, TODAY, 60))


if __name__ == "__main__":
    unittest.main()
