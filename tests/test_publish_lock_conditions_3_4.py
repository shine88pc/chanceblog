"""제한 재개 잠금의 규칙 L9·L10 — 재개 조건 3·4(최소 품질 Gate hold · 콘텐츠 출처 facts 와 국문 단독) 시험(BP3, 감사 BP-S1-2 의 T3-1, 결함 D-429). 네트워크 없이 돈다.

L9: 켜진 잠금 아래에서 chance.quality_gate 는 hold(적지 않으면 기본값 off 로 읽혀 거절).
L10: chance.content_source 는 facts(적지 않으면 기본값 feed 로 읽혀 거절)이고, 그때 chance.languages 는 정확히 ["ko"](한 쌍·적지 않음도 거절).
규칙 하나하나가 레지스트리 검증기·생성기 가드·chance_flow·Blogger 러너·명령줄에서 같은 말을 하는지는 기존 시험이 tests/lock_helpers.py 의 VIOLATIONS 표로 돌린다 —
여기서는 ① 규칙의 값 표와 기본값 읽기 ② 런타임이 값을 읽는 방식(항목 값 → defaults → 코드 기본값)과 규칙이 같은지 ③ 오류 문장 ④ 진짜 레지스트리가 켜는 순간 오류 0 인지
⑤ 값을 못박는 시험(test_resume_conditions_3_4)과의 관계 ⑥ 문서를 본다. 시험이 무한히 돌지 않는다(모든 반복은 고정된 작은 표).
"""
import copy
import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import _bootstrap
from lock_helpers import CHANCE, blog_of, lock_ready, mutated, real_registry, rules_in, set_in, with_lock_off
from pipeline import publish_lock, quality_gate, registry, source_policy
from test_resume_conditions_3_4 import EXPECTED

ROOT = _bootstrap.ROOT
DOCS = ROOT / "docs"
NOW = datetime(2026, 11, 9, 10, 0, tzinfo=timezone(timedelta(hours=9)))
STATUS_PREFIX = "[잠금] 제한 재개 잠금: "

# 켜진 잠금이 거절해야 하는 값(적힌 값). 문자열의 대소문자·앞뒤 공백·참/거짓·숫자·목록·사전까지 '정확히 이 값' 이 아니면 모두 거절한다.
GATE_BAD = ["off", "HOLD", "Hold", " hold", "hold ", "", None, True, False, 1, ["hold"], {"mode": "hold"}]
SOURCE_BAD = ["feed", "Facts", "FACTS", " facts", "facts ", "", None, True, 1, ["facts"], {"x": "facts"}]
LANGUAGES_BAD = [["ko", "en"], ["en", "ko"], ["en"], [], "ko", None, ["ko", "ko"], ["ko", 1], ["KO"], ["ko", "en", "ja"]]


def l_rules(reg):
    return rules_in(publish_lock.lock_errors(reg))


def pop_key(key):
    return lambda reg: blog_of(reg, CHANCE).pop(key)


def put(**fields):
    return lambda reg: set_in(reg, CHANCE, **fields)


def row_starting(text, start):
    return next(line for line in text.splitlines() if line.startswith(start))


def run_guard(folder, reg):
    """생성기 시작 가드를 한 번 부른다(빈 이력·빈 원격 초안 목록): 조용히 돌아오면 code 가 None, 멈추면 SystemExit 의 값. 상태 줄([잠금] … 켜짐)은 out 에서 뺀다 —
    test_publish_lock.GuardRun 과 같은 호출이지만 그 모듈은 PyYAML 를 불러와 PyYAML 없는 환경에서 불러오기에 실패하므로 이 시험은 따로 둔다."""
    path = Path(folder) / "history.json"
    path.write_text(json.dumps([]), encoding="utf-8")
    raw, summary = [], []
    try:
        publish_lock.guard_start({"EVENT_NAME": "schedule"}, path, lambda: NOW, False, False, summary.append, out=raw.append, load=lambda: reg, remote_drafts=lambda: [], exists=None)
        code = None
    except SystemExit as exc:
        code = exc.code
    return SimpleNamespace(code=code, out=[line for line in raw if not line.startswith(STATUS_PREFIX)], summary=summary)


class RuleValuesTest(unittest.TestCase):
    def test_the_ready_registry_obeys_both_rules(self):
        self.assertEqual(publish_lock.lock_errors(lock_ready()), [])
        self.assertEqual(registry.validate_registry(lock_ready()), [])

    def test_only_hold_passes_l9_and_every_other_value_is_refused(self):
        self.assertEqual(l_rules(mutated(put(quality_gate="hold"))), set())
        for value in GATE_BAD:
            with self.subTest(value=value):
                reg = mutated(put(quality_gate=value))
                self.assertEqual(l_rules(reg), {"L9"}, publish_lock.lock_errors(reg))

    def test_a_missing_quality_gate_is_read_as_off_and_refused(self):
        errors = publish_lock.lock_errors(mutated(pop_key("quality_gate")))
        self.assertEqual(rules_in(errors), {"L9"})
        self.assertIn("(지금 'off', 적지 않으면 off 로 읽힙니다)", errors[0])

    def test_only_facts_passes_l10_and_every_other_value_is_refused(self):
        self.assertEqual(l_rules(mutated(put(content_source="facts"))), set())
        for value in SOURCE_BAD:
            with self.subTest(value=value):
                reg = mutated(put(content_source=value))
                errors = publish_lock.lock_errors(reg)
                self.assertEqual(rules_in(errors), {"L10"}, errors)
                self.assertIn("chance.content_source", " ".join(errors))

    def test_a_missing_content_source_is_read_as_feed_and_refused(self):
        errors = publish_lock.lock_errors(mutated(pop_key("content_source")))
        self.assertEqual(rules_in(errors), {"L10"})
        self.assertIn("(지금 'feed', 적지 않으면 feed 로 읽힙니다)", errors[0])

    def test_with_facts_the_languages_must_be_exactly_ko(self):
        self.assertEqual(l_rules(mutated(put(languages=["ko"]))), set())
        for value in LANGUAGES_BAD:
            with self.subTest(value=value):
                reg = mutated(put(languages=value))
                errors = publish_lock.lock_errors(reg)
                self.assertIn("L10", rules_in(errors), errors)
                self.assertTrue(any("chance.languages" in message for message in errors), errors)
        for pair in (["ko", "en"], ["en", "ko"]):                  # L6 이 허용하는 한 쌍은 L10 만 거절한다(L6 은 조용하다)
            self.assertEqual(l_rules(mutated(put(languages=pair))), {"L10"}, pair)

    def test_a_missing_languages_key_is_read_as_the_pair_and_refused(self):
        errors = publish_lock.lock_errors(mutated(pop_key("languages")))
        self.assertEqual(rules_in(errors), {"L10"})
        self.assertIn("적지 않으면 ko·en 한 쌍으로 읽힙니다", errors[0])

    def test_languages_that_break_l6_are_also_refused_by_l10(self):
        """L6 이 거절하는 모양(ko 없음·겹침·모르는 언어·문자열·빈 목록)은 ['ko'] 가 아니므로 L10 도 함께 거절한다(짝 — tests/lock_helpers.py 의 EXTRA)."""
        for value in (["en"], ["ko", "ko"], ["ko", "fr"], "ko", []):
            with self.subTest(value=value):
                self.assertEqual(l_rules(mutated(put(languages=value))), {"L6", "L10"})

    def test_with_a_feed_source_the_languages_are_not_reported_twice(self):
        reg = mutated(put(content_source="feed", languages=["ko", "en"]))
        errors = publish_lock.lock_errors(reg)
        self.assertEqual(rules_in(errors), {"L10"})
        self.assertEqual(len(errors), 1, errors)                    # 콘텐츠 출처 하나만 말한다(그때 languages 는 보지 않는다)
        self.assertIn("chance.content_source", errors[0])

    def test_two_broken_values_are_both_reported(self):
        reg = mutated(lambda r: set_in(r, CHANCE, quality_gate="off", content_source="feed"))
        self.assertEqual(l_rules(reg), {"L9", "L10"})

    def test_an_invalid_lock_value_is_read_as_locked_and_the_rules_still_apply(self):
        reg = mutated(put(quality_gate="off"))
        reg["resume_lock"] = "true"
        self.assertEqual(l_rules(reg), {"L0", "L9"})


class RuleReadsLikeTheRuntimeTest(unittest.TestCase):
    """규칙은 값을 런타임이 읽는 방식 그대로 읽는다 — 항목에 적힌 값이 먼저, 없으면 defaults, 그것도 없으면 코드 기본값(registry.merged_blog 의 deep_merge 와 같다).
    규칙이 읽는 값과 런타임이 읽는 값이 어긋나면 '규칙은 통과인데 런타임은 다른 값' 이 되므로, 위치(항목·defaults·없음) 와 값(켠 값·꺼진 값)의 모든 조합을 병합된 항목과 견준다."""

    GOOD = {"quality_gate": "hold", "content_source": "facts", "languages": ["ko"]}
    BAD = {"quality_gate": "off", "content_source": "feed", "languages": ["ko", "en"]}
    PLACEMENTS = ("own-good", "own-bad", "defaults-good", "defaults-bad", "none")

    @classmethod
    def build(cls, placements):
        reg = lock_ready()
        chance = blog_of(reg, CHANCE)
        for key, placement in zip(cls.GOOD, placements):
            chance.pop(key, None)
            if placement == "own-good":
                chance[key] = copy.deepcopy(cls.GOOD[key])
            elif placement == "own-bad":
                chance[key] = copy.deepcopy(cls.BAD[key])
            elif placement == "defaults-good":
                reg["defaults"][key] = copy.deepcopy(cls.GOOD[key])
            elif placement == "defaults-bad":
                reg["defaults"][key] = copy.deepcopy(cls.BAD[key])
        return reg, chance

    def test_every_placement_of_every_value_agrees_with_the_merged_entry(self):
        count = 0
        for gate in self.PLACEMENTS:
            for source in self.PLACEMENTS:
                for languages in self.PLACEMENTS:
                    reg, chance = self.build((gate, source, languages))
                    merged = registry.merged_blog(reg, chance)
                    rules = l_rules(reg)
                    with self.subTest(gate=gate, source=source, languages=languages):
                        self.assertEqual("L9" in rules, merged.get("quality_gate", registry.DEFAULT_QUALITY_GATE) != "hold", merged)
                        source_ok = merged.get("content_source", source_policy.DEFAULT_CONTENT_SOURCE) == "facts"
                        self.assertEqual("L10" in rules, not (source_ok and merged.get("languages") == ["ko"]), merged)
                    count += 1
        self.assertEqual(count, len(self.PLACEMENTS) ** 3)

    def test_the_entry_wins_over_defaults(self):
        reg, chance = self.build(("own-bad", "own-bad", "own-bad"))
        for key in self.GOOD:
            reg["defaults"][key] = copy.deepcopy(self.GOOD[key])             # defaults 가 켠 값이어도 항목의 꺼진 값이 이긴다
        self.assertEqual(l_rules(reg), {"L9", "L10"})
        reg, chance = self.build(("defaults-bad", "defaults-bad", "defaults-bad"))
        for key in self.GOOD:
            chance[key] = copy.deepcopy(self.GOOD[key])                      # defaults 가 꺼진 값이어도 항목의 켠 값이 이긴다
        self.assertEqual(l_rules(reg), set())


class RuleSwitchTest(unittest.TestCase):
    def test_with_the_lock_off_neither_rule_applies(self):
        for mutate in (pop_key("quality_gate"), put(quality_gate="off"), pop_key("content_source"), put(content_source="feed"), put(languages=["ko", "en"]), pop_key("languages")):
            reg = with_lock_off(mutated(mutate))
            self.assertEqual(publish_lock.lock_errors(reg), [])
            self.assertEqual(publish_lock.registry_errors(reg), [])

    def test_an_explicit_false_is_the_same_as_no_key(self):
        reg = mutated(lambda r: set_in(r, CHANCE, quality_gate="off", content_source="feed", source_policy="legacy", languages=["ko", "en"]))
        reg["resume_lock"] = False
        self.assertEqual(publish_lock.registry_errors(reg), [])

    def test_other_blogs_are_not_read_by_these_rules(self):
        reg = lock_ready()
        others = [blog for blog in reg["blogs"] if blog["key"] != CHANCE]
        self.assertTrue(others)
        for blog in others:
            blog.update(quality_gate="off", content_source="feed", languages=["ko", "en"])      # 꺼진 값이 Chance 밖의 항목에 있어도 규칙은 보지 않는다
        self.assertEqual(publish_lock.lock_errors(reg), [])           # L9·L10 은 Chance 의 재개 조건이다


class MessageTest(unittest.TestCase):
    def test_the_messages_name_the_rule_the_key_the_wanted_value_and_the_folded_current_value(self):
        text = publish_lock.lock_errors(mutated(put(quality_gate="off")))[0]
        for piece in ("제한 재개 잠금 L9", "chance.quality_gate", "hold 여야 합니다", "(지금 'off')", "재개 조건 3"):
            self.assertIn(piece, text)
        text = publish_lock.lock_errors(mutated(put(content_source="feed")))[0]
        for piece in ("제한 재개 잠금 L10", "chance.content_source", "facts 여야 합니다", "(지금 'feed')", "재개 조건 4"):
            self.assertIn(piece, text)
        text = publish_lock.lock_errors(mutated(put(languages=["ko", "en"])))[0]
        for piece in ("제한 재개 잠금 L10", "chance.content_source 가 facts 일 때", "chance.languages", "['ko']", "국문 단독", "(국문 단독 — 재개 조건 4; 지금 ['ko', 'en'])"):
            self.assertIn(piece, text)

    def test_a_hostile_value_is_folded_to_one_short_line(self):
        evil = "x\n::error::가짜 주석\n" + "y" * 5000
        for key in ("quality_gate", "content_source", "languages"):
            with self.subTest(key=key):
                errors = publish_lock.lock_errors(mutated(put(**{key: evil})))
                self.assertTrue(errors)
                joined = "".join(errors)
                self.assertNotIn("\n", joined)
                self.assertNotIn("::error::", joined)                  # '::' 는 풀어 놓는다(워크플로 명령 흉내 방지)
                self.assertLess(len(joined), 1500)                    # 5천 자 값이 문장을 부풀리지 않는다

    def test_the_rule_table_has_both_rules_after_l8(self):
        ids = [rule for rule, _text in publish_lock.RULES]
        self.assertEqual(ids, ["L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10"])
        table = dict(publish_lock.RULES)
        for rule, words in (("L9", ("chance.quality_gate", "hold", "재개 조건 3")), ("L10", ("chance.content_source", "facts", "chance.languages", "재개 조건 4"))):
            for word in words:
                self.assertIn(word, table[rule], rule)


class EveryEntranceTest(unittest.TestCase):
    """같은 규칙을 레지스트리 검증기·생성기 가드가 같은 말로 거절한다(나머지 입구 — chance_flow·Blogger 러너·명령줄 — 는 기존 시험이 VIOLATIONS 표로 돌린다)."""

    CASES = ((pop_key("quality_gate"), "L9"), (put(quality_gate="off"), "L9"), (put(content_source="feed"), "L10"), (pop_key("content_source"), "L10"), (put(languages=["ko", "en"]), "L10"),
             (pop_key("languages"), "L10"))

    def folder(self):
        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        return Path(box.name)

    def test_the_validator_reports_the_rule(self):
        for mutate, rule in self.CASES:
            with self.subTest(rule=rule):
                self.assertTrue(any("제한 재개 잠금 %s:" % rule in message for message in registry.validate_registry(mutated(mutate))))

    def test_the_guard_stops_the_run_and_names_the_rule(self):
        for mutate, rule in self.CASES:
            with self.subTest(rule=rule):
                run = run_guard(self.folder(), mutated(mutate))
                self.assertEqual(run.code, 1)
                self.assertIn("[SKIP] code=LOCK_BLOCKED", run.out[0])
                self.assertEqual(set(re.search(r"rules=(\S+)", run.out[0]).group(1).split(",")), {rule}, run.out[0])

    def test_a_registry_that_obeys_both_passes_the_guard(self):
        self.assertIsNone(run_guard(self.folder(), lock_ready()).code)


class RealRegistryTest(unittest.TestCase):
    """켜는 순간 지금 레지스트리(quality_gate hold · content_source facts · languages ko)는 오류 0 이어야 한다 — 그리고 값 하나라도 빠지면 규칙이 잡는다."""

    def test_the_real_registry_obeys_l9_and_l10_with_the_lock_on(self):
        reg = real_registry()
        self.assertEqual(publish_lock.lock_state(reg), "on")
        self.assertEqual(publish_lock.lock_errors(reg), [])
        self.assertEqual(publish_lock.registry_errors(reg), [])
        self.assertEqual(registry.validate_registry(reg), [])
        chance = blog_of(reg, CHANCE)
        self.assertEqual((chance["quality_gate"], chance["content_source"], chance["languages"]),
                         (publish_lock.REQUIRED_QUALITY_GATE, publish_lock.REQUIRED_CONTENT_SOURCE, list(publish_lock.REQUIRED_LANGUAGES)))

    def test_each_value_of_the_real_registry_is_needed(self):
        cases = (("quality_gate 를 지움", lambda c: c.pop("quality_gate"), {"L9"}), ("quality_gate off", lambda c: c.update(quality_gate="off"), {"L9"}),
                 ("content_source 를 지움", lambda c: c.pop("content_source"), {"L10"}), ("content_source feed", lambda c: c.update(content_source="feed"), {"L10"}),
                 ("languages 한 쌍", lambda c: c.update(languages=["ko", "en"]), {"L10"}), ("languages 를 지움", lambda c: c.pop("languages"), {"L10"}))
        for label, change, expected in cases:
            with self.subTest(case=label):
                reg = real_registry()
                change(blog_of(reg, CHANCE))
                self.assertEqual(l_rules(reg), expected)
                self.assertTrue(any("제한 재개 잠금 %s:" % next(iter(expected)) in message for message in registry.validate_registry(reg)))

    def test_the_guard_accepts_the_real_registry(self):
        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        self.assertIsNone(run_guard(Path(box.name), real_registry()).code)


class RelationToTheValuePinTest(unittest.TestCase):
    """test_resume_conditions_3_4 는 레지스트리의 현재 값을 따로 못박는다 — 규칙과 겹쳐 지킨다. 두 곳이 같은 값을 말해야 한다."""

    def test_the_value_pin_and_the_rules_name_the_same_values(self):
        self.assertEqual(EXPECTED["quality_gate"], publish_lock.REQUIRED_QUALITY_GATE)
        self.assertEqual(EXPECTED["content_source"], publish_lock.REQUIRED_CONTENT_SOURCE)
        self.assertEqual(EXPECTED["languages"], list(publish_lock.REQUIRED_LANGUAGES))
        self.assertEqual(EXPECTED["source_policy"], source_policy.ALLOWLIST)          # 이 값은 규칙이 직접 보지 않는다 — facts 이면 검증기가 요구한다

    def test_the_rule_values_are_values_the_code_accepts_and_not_the_defaults(self):
        self.assertIn(publish_lock.REQUIRED_QUALITY_GATE, registry.QUALITY_GATE_MODES)
        self.assertNotEqual(publish_lock.REQUIRED_QUALITY_GATE, registry.DEFAULT_QUALITY_GATE)          # 기본값(적지 않음)은 거절 쪽이다
        self.assertEqual(publish_lock.REQUIRED_CONTENT_SOURCE, source_policy.CONTENT_FACTS)
        self.assertNotEqual(publish_lock.REQUIRED_CONTENT_SOURCE, source_policy.DEFAULT_CONTENT_SOURCE)
        self.assertIn(list(publish_lock.REQUIRED_LANGUAGES), [list(item) for item in registry.CHANCE_LANGUAGE_SETS])
        self.assertNotEqual(list(publish_lock.REQUIRED_LANGUAGES), registry.DEFAULT_CHANCE_LANGUAGES)
        self.assertEqual(quality_gate.normalize_languages(list(publish_lock.REQUIRED_LANGUAGES)), ("ko",))

    def test_the_validator_asks_for_the_allowlist_when_the_source_is_facts(self):
        """L10 이 facts 를 요구하므로 source_policy 가 allowlist 여야 한다는 검증기 규칙이 켠 레지스트리의 세 번째 조건이다(규칙 밖 — 검증기가 지킨다)."""
        reg = mutated(put(source_policy="legacy"))
        self.assertEqual(publish_lock.lock_errors(reg), [])
        self.assertTrue(any("source_policy 는 allowlist" in message for message in registry.validate_registry(reg)))


class DocumentTest(unittest.TestCase):
    PUBLISH = (DOCS / "PUBLISH_PATHS.md").read_text(encoding="utf-8")
    GUARDRAILS = (DOCS / "SECURITY_GUARDRAILS.md").read_text(encoding="utf-8")
    ARCHITECTURE = (DOCS / "ARCHITECTURE.md").read_text(encoding="utf-8")
    GUIDE = (DOCS / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")
    OPS = (DOCS / "OPS_INBOX.md").read_text(encoding="utf-8")
    DEFECTS = (DOCS / "DEFECT_REGISTER.md").read_text(encoding="utf-8")

    def test_the_rule_table_has_l9_and_l10_rows_with_three_cells(self):
        for rule, words in (("L9", ("`chance.quality_gate`", "`hold`", "재개 조건 3", "`off`", "`publish_lock.REQUIRED_QUALITY_GATE`", "`tests/test_resume_conditions_3_4.py`")),
                            ("L10", ("`chance.content_source`", "`facts`", "재개 조건 4", "`feed`", '`["ko"]`', "`REQUIRED_CONTENT_SOURCE`", "`REQUIRED_LANGUAGES`", "L6", "`source_policy: allowlist`"))):
            row = row_starting(self.PUBLISH, "| **%s** |" % rule)
            self.assertEqual(row.count("|"), 4, rule)                         # 세 칸 — 칸 안에 세로선이 없다
            for word in words:
                self.assertIn(word, row, (rule, word))

    def test_the_rule_range_in_the_documents_is_l0_to_l10(self):
        self.assertIn("**L0–L10 은 잠금이 켜져 있을 때만**", self.PUBLISH)
        self.assertNotIn("**L0–L8 은 잠금이 켜져 있을 때만**", self.PUBLISH)
        self.assertIn("규칙 L0–L10", row_starting(self.GUARDRAILS, "| G-C14 |"))
        self.assertIn("규칙 L0–L10", row_starting(self.GUARDRAILS, "| REG-1(제한 재개 잠금)"))
        self.assertIn("규칙 L0–L10 을 어기면 오류", self.ARCHITECTURE)
        for text in (self.PUBLISH, self.GUARDRAILS, self.ARCHITECTURE):
            self.assertNotIn("규칙 L0–L8", text)

    def test_section_6_lists_the_three_values_and_the_source_policy_with_their_rules(self):
        section = self.PUBLISH[self.PUBLISH.index("## 6. 켜는 방법"):self.PUBLISH.index("## 7. 한계와 남은 위험")]

        def cells(start):
            return [cell.strip() for cell in row_starting(section, start).split("|")[1:-1]]

        chance = blog_of(lock_ready(), CHANCE)
        self.assertEqual(cells("| `chance.quality_gate` |")[2:], ["`%s`" % chance["quality_gate"], "L9"])
        self.assertEqual(cells("| `chance.content_source` |")[2:], ["`%s`" % chance["content_source"], "L10"])
        self.assertEqual(cells("| `chance.source_policy` |")[2], "`%s`" % chance["source_policy"])
        languages = cells("| `chance.languages` |")
        self.assertTrue(languages[2].startswith('`["ko"]`'), languages)
        self.assertEqual(languages[3], "L6·L10")
        self.assertIn("**다섯 값**", section)                                    # 켜는 값 다섯은 그대로 — 재개 조건 값 셋은 이미 적혀 있다고 따로 적는다
        self.assertIn("재개 조건 3·4 의 값 셋", section)

    def test_section_9_names_the_helper_the_rules_changed_and_the_tick_fix(self):
        section = self.PUBLISH[self.PUBLISH.index("## 9. 켜는 변경이 일부러 깨뜨리는 시험 고정값"):]
        row = row_starting(section, "| `tests/lock_helpers.py` `lock_ready()` |")
        self.assertEqual(row.count("|"), 5)
        for word in ("`quality_gate` `hold`", "`content_source` `facts`", "`source_policy` `allowlist`", '`languages` `["ko"]`', "L9·L10"):
            self.assertIn(word, row, word)
        self.assertIn("`run_tick(..., guarded=True)`", section)

    def test_the_guardrail_list_names_the_new_constants_and_they_exist(self):
        line = next(item for item in self.GUARDRAILS.splitlines() if item.startswith("- 제한 재개 잠금(레지스트리 `resume_lock`)을 끄거나"))
        self.assertIn("L9·L10", line)
        for name in ("REQUIRED_QUALITY_GATE", "REQUIRED_CONTENT_SOURCE", "REQUIRED_LANGUAGES"):
            self.assertIn("`%s`" % name, line, name)
            self.assertTrue(hasattr(publish_lock, name), name)

    def test_the_operator_guide_and_the_release_checklist_say_the_rules_guard_the_values(self):
        guide = self.GUIDE[self.GUIDE.index("### 3-22. 제한 재개 잠금"):self.GUIDE.index("## 4. 점검 루틴과 키 교체")]
        for needle in ("L1–L10", "`chance.quality_gate: hold`", "`chance.content_source: facts`", '`chance.languages: ["ko"]`'):
            self.assertIn(needle, guide, needle)
        rows = {line.split("|")[1].strip().split(" ")[0]: line for line in self.OPS.splitlines() if line.startswith("| H")}
        for key, rule in (("H2", "잠금 규칙 L9 가 지킨다"), ("H3", "잠금 규칙 L10 이 지킨다"), ("H4", "잠금 규칙 L10 이 지킨다")):
            self.assertIn(rule, rows[key], key)
            self.assertNotIn("잠금이 보증하지 않", rows[key], key)

    def test_the_defect_row_d429_exists_once_with_six_cells_and_is_solved(self):
        rows = [line for line in self.DEFECTS.splitlines() if line.startswith("| **D-429** |")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].count("|"), 7)
        self.assertIn("**해결**", rows[0])
        for needle in ("D-413", "L9", "L10", "REQUIRED_QUALITY_GATE", "tests/test_publish_lock_conditions_3_4.py", "확인 032"):
            self.assertIn(needle, rows[0], needle)

    def test_the_new_text_has_no_tilde_and_no_link(self):
        """문서 규칙: ASCII 물결표 금지(숫자 범위는 en dash)·링크 금지 — 이 변경이 더한 줄만 본다(규칙 행·값 행·점검표 행·줄이기 금지 목록)."""
        marks = ("| **L9** |", "| **L10** |", "L9·L10", "REQUIRED_QUALITY_GATE", "| `chance.quality_gate` |", "| `chance.content_source` |", "| H2 ", "| H3 ", "| H4 ")
        seen = 0
        for text in (self.PUBLISH, self.GUARDRAILS, self.OPS, self.GUIDE, self.ARCHITECTURE):
            for line in text.splitlines():
                if any(mark in line for mark in marks):
                    seen += 1
                    self.assertNotIn(chr(126), line)
                    self.assertIsNone(re.search(r"https?://", line))
        self.assertGreaterEqual(seen, 10)


if __name__ == "__main__":
    unittest.main()
