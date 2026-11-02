"""글감·프롬프트가 지금 시기(계절·명절)에 맞는가(이슈 #92) — 가을에 '봄맞이 대청소' 초안이 나오지 않게. 네트워크 없이 확인한다.

- pipeline/topics.py: season_of·mentioned_seasons·season_fits·season_hint·season_note, pick_topic·expand_prompt 의 시기 반영
- pipeline/registry.py: 프로필 seed_months(시드별 달 목록) 검증
- pipeline/run.py: build_prompt(today=…) 의 [작성 시점] 안내
- 실제 프로필: 시기를 타는 시드에 달이 표시돼 있고, 어느 달에도 고를 시드가 충분하다
"""
import copy
import json
import random
import unittest
from datetime import date

import _bootstrap
from pipeline import registry, run as run_mod, topics

NOV = date(2026, 11, 2)          # 가을
APR = date(2026, 4, 10)          # 봄
JUL = date(2026, 7, 15)          # 여름
JAN = date(2027, 1, 20)          # 겨울
SPRING_CLEANING = "봄맞이 대청소를 방별로 나눠 며칠에 걸쳐 끝내는 계획표 만드는 방법"
WINTER_PREP = "겨울이 오기 전에 베란다와 창가 주변을 점검하는 계절 체크리스트"
EVERGREEN = "집 안 조명을 필요한 곳만 켜도록 바꾸는 습관과 간단한 설정 방법"
PROFILE_DIR = _bootstrap.ROOT / "pipeline" / "profiles"
REAL_PROFILES = sorted(p.stem for p in PROFILE_DIR.glob("*.json"))


def profile(**extra):
    base = {"language": "ko", "seed_topics": [SPRING_CLEANING, WINTER_PREP, EVERGREEN], "topic_cooldown_days": 60,
            "banned_topic_patterns": [], "similarity": {"other_blogs": 0.6}}
    base.update(extra)
    return base


class SeasonOfTest(unittest.TestCase):
    def test_every_month_belongs_to_exactly_one_season(self):
        seen = {}
        for name, months in topics.SEASON_MONTHS.items():
            for month in months:
                self.assertNotIn(month, seen)
                seen[month] = name
        self.assertEqual(sorted(seen), list(range(1, 13)))

    def test_seasons_follow_the_korean_calendar(self):
        expected = {1: "winter", 2: "winter", 3: "spring", 5: "spring", 6: "summer", 8: "summer", 9: "autumn", 11: "autumn", 12: "winter"}
        for month, season in expected.items():
            self.assertEqual(topics.season_of(date(2026, month, 15)), season, month)
        self.assertEqual(topics.SEASONS, ("spring", "summer", "autumn", "winter"))


class MentionedSeasonsTest(unittest.TestCase):
    def test_korean_season_words_are_found_at_the_start_of_a_word(self):
        cases = {"봄맞이 대청소": {"spring"}, "한여름 더위를 식히는 방법": {"summer"}, "장마철 습기": {"summer"}, "초가을 옷차림": {"autumn"},
                 "김장철 준비": {"autumn"}, "한겨울 난방비": {"winter"}, "설날 귀성길": {"winter"}, "가을 단풍 나들이": {"autumn"},
                 "봄 가을 환절기 옷 정리": {"spring", "autumn"}}
        for text, seasons in cases.items():
            self.assertEqual(topics.mentioned_seasons(text, "ko"), seasons, text)

    def test_words_that_only_contain_a_season_syllable_are_not_seasons(self):
        for text in ("아이 돌봄 시간을 정리하는 방법", "책상 위 물건을 살펴봄", "가을걷이가 아닌 집 정리", "집 안 조명 정리"):
            self.assertEqual(topics.mentioned_seasons(text, "ko") - {"autumn"}, set(), text)
        self.assertEqual(topics.mentioned_seasons("아이 돌봄 시간을 정리하는 방법", "ko"), set())

    def test_english_season_words_ignore_fall_asleep(self):
        self.assertEqual(topics.mentioned_seasons("How to fall asleep faster", "en"), set())
        self.assertEqual(topics.mentioned_seasons("Spring cleaning in ten minutes", "en"), {"spring"})
        self.assertEqual(topics.mentioned_seasons("A cozy WINTER evening routine and a calm Autumn walk", "en"), {"winter", "autumn"})
        self.assertEqual(topics.mentioned_seasons("Easy Christmas gift wrapping", "en"), {"winter"})

    def test_an_unknown_language_or_odd_input_means_no_seasons(self):
        self.assertEqual(topics.mentioned_seasons("봄맞이", "fr"), set())
        self.assertEqual(topics.mentioned_seasons("봄맞이", None), set())
        self.assertEqual(topics.mentioned_seasons(None, "ko"), set())


class SeasonFitsTest(unittest.TestCase):
    def test_spring_topics_do_not_fit_autumn_but_the_next_season_does(self):
        p = profile()
        self.assertFalse(topics.season_fits(SPRING_CLEANING, p, NOV))
        self.assertTrue(topics.season_fits(WINTER_PREP, p, NOV))
        self.assertTrue(topics.season_fits(EVERGREEN, p, NOV))

    def test_the_current_season_and_the_next_one_fit_everything_else_does_not(self):
        p = profile()
        by_date = {NOV: {"autumn": True, "winter": True, "spring": False, "summer": False},
                   APR: {"spring": True, "summer": True, "autumn": False, "winter": False},
                   JUL: {"summer": True, "autumn": True, "winter": False, "spring": False},
                   JAN: {"winter": True, "spring": True, "summer": False, "autumn": False}}
        words = {"spring": "봄맞이 정리", "summer": "한여름 더위 식히기", "autumn": "가을 단풍 나들이", "winter": "겨울 난방 점검"}
        for day, expected in by_date.items():
            for season, fits in expected.items():
                self.assertEqual(topics.season_fits(words[season], p, day), fits, (day, season))

    def test_a_topic_naming_two_seasons_fits_when_either_fits(self):
        p = profile()
        self.assertTrue(topics.season_fits("봄 가을 환절기에 옷 정리하는 순서", p, NOV))
        self.assertFalse(topics.season_fits("봄 여름 옷 정리하는 순서", p, NOV))

    def test_english_profiles_use_english_words(self):
        en = {"language": "en"}
        self.assertFalse(topics.season_fits("Spring cleaning in ten minutes", en, NOV))
        self.assertTrue(topics.season_fits("Cozy winter evening routines", en, NOV))
        self.assertTrue(topics.season_fits("How to fall asleep faster", en, NOV))
        self.assertTrue(topics.season_fits("봄맞이 대청소", en, NOV))             # 영어 프로필은 한국어 낱말을 보지 않는다

    def test_listed_months_override_the_words(self):
        p = profile(seed_months={SPRING_CLEANING: [2, 3, 4], EVERGREEN: [11]})
        self.assertTrue(topics.season_fits(SPRING_CLEANING, p, date(2026, 2, 20)))          # 단어로는 겨울에 봄이 '다음 계절'이지만 달 목록이 정한다
        self.assertFalse(topics.season_fits(SPRING_CLEANING, p, NOV))
        self.assertFalse(topics.season_fits(EVERGREEN, p, date(2026, 5, 1)))                # 달이 적혀 있으면 사철 주제라도 그 달에만
        self.assertTrue(topics.season_fits(EVERGREEN, p, NOV))

    def test_a_malformed_seed_months_is_ignored_here_and_caught_by_the_registry(self):
        self.assertTrue(topics.season_fits(EVERGREEN, profile(seed_months="x"), NOV))
        self.assertFalse(topics.season_fits(SPRING_CLEANING, profile(seed_months=["x"]), NOV))


class PickTopicSeasonTest(unittest.TestCase):
    def test_a_seed_that_does_not_fit_the_season_is_never_picked(self):
        p = profile()
        picked = {topics.pick_topic(p, [], NOV, [], random.Random(n))[0] for n in range(200)}
        self.assertEqual(picked, {WINTER_PREP, EVERGREEN})
        april = {topics.pick_topic(p, [], APR, [], random.Random(n))[0] for n in range(200)}
        self.assertEqual(april, {SPRING_CLEANING, EVERGREEN})

    def test_when_every_fitting_seed_was_used_the_llm_is_asked_with_the_season_hint(self):
        p = profile()
        history = [{"topic": WINTER_PREP, "date": "2026-10-30"}, {"topic": EVERGREEN, "date": "2026-10-30"}]
        prompts = []

        def llm(prompt):
            prompts.append(prompt)
            return json.dumps(["봄맞이 창문 청소 계획 세우는 방법과 순서", "가을 낙엽이 쌓인 현관 정리하는 순서와 요령"], ensure_ascii=False), "m"

        topic, source = topics.pick_topic(p, history, NOV, [], random.Random(1), llm=llm)
        self.assertEqual((topic, source), ("가을 낙엽이 쌓인 현관 정리하는 순서와 요령", "llm"))        # 봄 제안은 건너뛰고 가을 제안을 고른다
        self.assertTrue(prompts[0].startswith("오늘은 2026-11-02이고 한국은 가을이다."))

    def test_when_no_seed_fits_the_season_and_there_is_no_llm_nothing_is_picked(self):
        p = profile(seed_topics=[SPRING_CLEANING])
        self.assertEqual(topics.pick_topic(p, [], NOV, [], random.Random(1), llm=None), (None, "exhausted"))

    def test_without_a_date_the_expand_prompt_is_unchanged(self):
        p = profile()
        self.assertEqual(topics.expand_prompt(p, ["a topic"], 6), topics._expand_prompt_base(p, ["a topic"], 6))
        with_date = topics.expand_prompt(p, ["a topic"], 6, NOV)
        self.assertTrue(with_date.endswith(topics._expand_prompt_base(p, ["a topic"], 6)))
        self.assertIn("2026-11-02", with_date)

    def test_the_english_hint_is_english_only(self):
        en = {"language": "en", "topic_expand_prompt": "Give {n} ideas of {min}-{max} chars. Avoid:\n{avoid}\nJSON array of strings only."}
        text = topics.expand_prompt(en, [], 5, NOV)
        self.assertIn("Today is 2026-11-02 (autumn in the Northern Hemisphere)", text)
        self.assertFalse([ch for ch in text if "가" <= ch <= "힣"])


class PromptNoteTest(unittest.TestCase):
    TEMPLATE = "주제 {topic} 로 글을 쓴다."

    def test_the_note_is_added_after_the_extra_rules_and_before_the_feedback(self):
        p = {"language": "ko", "prompt_extra": ["규칙 하나"]}
        prompt = run_mod.build_prompt(self.TEMPLATE, "겨울 준비", p, feedback=["제목이 길다"], today=NOV)
        self.assertLess(prompt.index("[추가 규칙]"), prompt.index("[작성 시점]"))
        self.assertLess(prompt.index("[작성 시점]"), prompt.index("[이전 시도에서 고쳐야 할 점]"))
        self.assertIn("오늘은 2026-11-02이고 한국은 가을이다", prompt)

    def test_without_a_date_the_prompt_is_unchanged(self):
        p = {"language": "ko", "prompt_extra": ["규칙 하나"]}
        self.assertNotIn("[작성 시점]", run_mod.build_prompt(self.TEMPLATE, "겨울 준비", p))
        self.assertEqual(run_mod.build_prompt(self.TEMPLATE, "겨울 준비", p),
                         run_mod.build_prompt(self.TEMPLATE, "겨울 준비", p, None, None))

    def test_the_english_note_has_no_korean_and_no_topic_marker_line(self):
        note = topics.season_note({"language": "en"}, NOV)
        self.assertTrue(note.startswith("[Timing]"))
        self.assertFalse([ch for ch in note if "가" <= ch <= "힣"])
        self.assertNotIn("Topic:", note)                  # 스텁 LLM 은 'Topic:' 줄로 영어 프롬프트를 알아본다 — 안내가 그 표식을 만들면 안 된다

    def test_the_run_passes_today_into_the_prompt(self):
        source = (_bootstrap.ROOT / "pipeline" / "run.py").read_text(encoding="utf-8")
        self.assertIn("llm(build_prompt(template, topic, profile, feedback, today))", source)
        self.assertIn("pick_topic(profile, history, today,", source)


class SeedMonthsValidationTest(unittest.TestCase):
    def errors(self, **extra):
        base = copy.deepcopy(registry.load_profile("blogger_practical_ko"))
        base.update(extra)
        return [e for e in registry.validate_profile(base) if "seed_months" in e]

    def test_a_valid_table_passes(self):
        seed = registry.load_profile("blogger_practical_ko")["seed_topics"][0]
        self.assertEqual(self.errors(seed_months={seed: [3, 4, 5]}), [])
        self.assertEqual(self.errors(), [])

    def test_unknown_seeds_bad_months_and_wrong_shapes_are_errors(self):
        seed = registry.load_profile("blogger_practical_ko")["seed_topics"][0]
        self.assertTrue(self.errors(seed_months=["x"]))
        self.assertTrue(self.errors(seed_months={"없는 시드 글입니다 하나둘": [1]}))
        for bad in ([], [0], [13], [1, 1], ["1"], [True], [1.5], "3", None, {"a": 1}):
            self.assertTrue(self.errors(seed_months={seed: bad}), bad)


class RealProfilesTest(unittest.TestCase):
    def load(self, name):
        return registry.load_profile(name)

    def test_every_seed_that_names_a_season_has_its_months_listed(self):
        for name in REAL_PROFILES:
            profile_ = self.load(name)
            listed = profile_.get("seed_months") or {}
            for seed in profile_["seed_topics"]:
                if topics.mentioned_seasons(seed, profile_["language"]):
                    self.assertIn(seed, listed, f"{name}: 계절 낱말이 든 시드에 seed_months 가 없다 — {seed}")

    def test_listed_months_are_sane_for_the_season_the_seed_names(self):
        for name in REAL_PROFILES:
            profile_ = self.load(name)
            for seed, months in (profile_.get("seed_months") or {}).items():
                seasons = topics.mentioned_seasons(seed, profile_["language"])
                if not seasons:
                    continue                       # 계절 낱말이 없는 시드(환절기·명절 선물·창문 틈 등)는 달을 사람이 정한다
                allowed = set()
                for season in seasons:
                    before = topics.SEASONS[(topics.SEASONS.index(season) - 1) % 4]                          # 그 계절 '앞' 계절(미리 준비)
                    allowed |= set(topics.SEASON_MONTHS[season]) | set(topics.SEASON_MONTHS[before])
                self.assertTrue(set(months) <= allowed, f"{name}: {seed} {months}")

    def test_every_month_leaves_enough_seeds_to_choose_from(self):
        for name in REAL_PROFILES:
            profile_ = self.load(name)
            for month in range(1, 13):
                fitting = [s for s in profile_["seed_topics"] if topics.season_fits(s, profile_, date(2026, month, 15))]
                self.assertGreaterEqual(len(fitting), 20, (name, month, len(fitting)))

    def test_the_naver_profile_no_longer_offers_spring_cleaning_in_autumn(self):
        naver = self.load("naver_life_tips_ko")
        picked = {topics.pick_topic(naver, [], NOV, [], random.Random(n))[0] for n in range(300)}
        self.assertFalse([t for t in picked if any(word in t for word in ("봄맞이", "꽃구경", "장마", "한여름", "여름이 오기 전"))], picked)
        self.assertTrue([t for t in picked if "김장철" in t or "겨울" in t or "단풍" in t])         # 가을·겨울 준비 주제는 나온다
        april = {topics.pick_topic(naver, [], APR, [], random.Random(n))[0] for n in range(300)}
        self.assertTrue([t for t in april if "봄맞이" in t or "꽃구경" in t])
        self.assertFalse([t for t in april if "김장철" in t or "겨울철" in t or "단풍" in t])

    def test_the_seed_months_keys_are_real_seeds_in_every_profile(self):
        for name in REAL_PROFILES:
            profile_ = self.load(name)
            self.assertLessEqual(set(profile_.get("seed_months") or {}), set(profile_["seed_topics"]), name)


class DocumentationTest(unittest.TestCase):
    def test_the_architecture_doc_describes_seed_months_and_the_timing_note(self):
        doc = (_bootstrap.ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        for phrase in ("`seed_months`", "[작성 시점]", "season_fits"):
            self.assertIn(phrase, doc, phrase)


if __name__ == "__main__":
    unittest.main()
