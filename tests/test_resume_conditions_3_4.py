"""재개 조건 3·4(품질 관문·AI 미사용·국문 단독)의 레지스트리 현재 값을 한 곳에서 못박는다(BP-S1-2, 결함 D-413). 네트워크 없이 돈다.

왜: 제한 재개 잠금(pipeline/publish_lock.py)은 L1–L8 로 승인 PR 흐름·하루 1편·열린 초안 상한·주간 상한·언어 형식·다른 블로그 모드를 코드로 지키지만, 재개 조건 3(최소 품질 Gate)과 4(계산이 값을 더하는 글만·AI 미사용·국문 단독)는 지키지 않는다
(감사 BP-S1-2 의 재현: quality_gate 키를 지우거나 content_source 를 feed 로 바꾸거나 languages 에 en 을 더해도 잠금 오류 0·레지스트리 검증 오류 0). 규칙으로 막는 일(L9·L10)은 운영자 승인(T3)이 필요하므로 규칙은 더하지 않고, 대신 이 시험이 현재 값을 못박는다 —
그 값이 병합된 설정 한 줄로 바뀌면 CI 가 빨개져 운영자가 병합 부탁 알림에서 알아본다.

이 시험이 빨개지면: 시험을 고치기 전에 운영자가 발행 정지 해제 점검표(docs/OPS_INBOX.md §10-11 끝의 '해제 점검표 본체')를 보고 의도한 변경인지부터 확인한다. 의도한 변경이면 이 파일의 EXPECTED 값과 점검표의 같은 줄을 한 변경으로 함께 고친다.
값은 파일을 직접 읽어서(원본 JSON) 그리고 코드가 실제로 읽는 값(registry·source_policy 의 읽기 함수)으로 둘 다 본다 — 키를 지워 기본값으로 떨어지는 변경도 잡는다.
"""
import json
import re
import unittest

import _bootstrap
from pipeline import registry, source_policy

ROOT = _bootstrap.ROOT
CONDITIONS = "재개 조건 3·4(품질 관문·AI 미사용·국문 단독)"
FIX_HINT = (f"{CONDITIONS} 의 레지스트리 값이 바뀌었습니다 — 발행 정지 해제 점검표(docs/OPS_INBOX.md §10-11 끝의 '해제 점검표 본체')를 보고 운영자가 의도한 변경인지 먼저 확인하세요. "
            "의도한 변경이면 이 시험의 EXPECTED 와 점검표를 한 변경으로 함께 고칩니다")

# 지금의 값(2026-11-23 기준): 품질 관문 hold · 글감 출처 facts(AI 미사용, 계산이 값을 더하는 글만) · 출처 정책 allowlist · 국문 단독
EXPECTED = {"quality_gate": "hold", "content_source": "facts", "source_policy": "allowlist", "languages": ["ko"]}


def raw_chance():
    """레지스트리 파일의 chance 항목을 직접 읽는다(기본값 병합 전의 적힌 값)."""
    data = json.loads((ROOT / "pipeline" / "blogs.json").read_text(encoding="utf-8"))
    entries = [blog for blog in data["blogs"] if blog.get("key") == "chance"]
    assert len(entries) == 1, "chance 항목이 정확히 하나여야 합니다"
    return entries[0]


def checklist_body(text):
    """docs/OPS_INBOX.md §10-11 끝의 '해제 점검표 본체' 문단부터 다음 큰 절(## 11.) 앞까지. 새 소절(### 10-12)은 만들지 않는다 — 문서 시험이 §10 의 소절을 10-1–10-11 로 못박는다."""
    start = text.index("**해제 점검표 본체**")
    return text[start:text.index("\n## 11. ", start)]


class ResumeConditions34ValuesTest(unittest.TestCase):
    def test_condition_3_the_quality_gate_is_hold(self):
        self.assertEqual(raw_chance().get("quality_gate"), EXPECTED["quality_gate"], FIX_HINT)
        self.assertEqual(registry.chance_settings().quality_gate, EXPECTED["quality_gate"], FIX_HINT)

    def test_condition_4_no_ai_content_source_is_facts(self):
        self.assertEqual(raw_chance().get("content_source"), EXPECTED["content_source"], FIX_HINT)
        self.assertEqual(source_policy.chance_content_source(), source_policy.CONTENT_FACTS, FIX_HINT)

    def test_condition_4_the_source_policy_is_allowlist(self):
        self.assertEqual(raw_chance().get("source_policy"), EXPECTED["source_policy"], FIX_HINT)
        self.assertEqual(source_policy.chance_source_policy(), EXPECTED["source_policy"], FIX_HINT)

    def test_condition_4_the_languages_are_korean_only(self):
        self.assertEqual(raw_chance().get("languages"), EXPECTED["languages"], FIX_HINT)
        self.assertEqual(list(registry.chance_settings().languages), EXPECTED["languages"], FIX_HINT)

    def test_the_four_values_together_read_as_one_table(self):
        """한 단언으로 네 값을 같이 보여 준다(어느 값이 바뀌었는지 한눈에)."""
        entry = raw_chance()
        shown = {name: entry.get(name) for name in EXPECTED}
        self.assertEqual(shown, EXPECTED, FIX_HINT)

    def test_the_keys_are_written_in_the_registry_not_left_to_defaults(self):
        """키를 지우면 기본값(quality_gate off · content_source feed · source_policy legacy · languages ko·en)으로 떨어진다 — 네 키 모두 파일에 적혀 있어야 한다."""
        entry = raw_chance()
        for name in EXPECTED:
            self.assertIn(name, entry, f"{name} 키가 레지스트리에서 사라졌습니다. {FIX_HINT}")

    def test_the_resume_lock_does_not_pin_these_values_and_the_checklist_says_so(self):
        """잠금(publish_lock)이 이 값을 지키지 않는다는 사실과 점검표의 위치가 점검표 문서에 적혀 있다(규칙 L9·L10 은 T3 제안으로만 둔다)."""
        text = (ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
        section = checklist_body(text)
        for needle in ("`chance.quality_gate`", "`hold`", "`chance.content_source`", "`facts`", "`chance.source_policy`", "`allowlist`", "`chance.languages`", '`["ko"]`',
                       "잠금이 보증하지 않", "tests/test_resume_conditions_3_4.py", "운영자만", "`PIPELINE_PAUSE`"):
            self.assertIn(needle, section, needle)
        self.assertNotIn(chr(126), section)                                  # 문서 규칙: ASCII 물결표 금지(숫자 범위는 en dash)
        self.assertIsNone(re.search(r"https?://", section))             # 문서 규칙: 링크 금지

    def test_each_row_of_the_four_values_says_the_lock_does_not_pin_it(self):
        """H2·H3·H4 행(품질 관문·AI 미사용·국문 단독)마다 '잠금이 보증하지 않는다' 와 값을 못박는 시험이 적혀 있다 — 한 행의 말이 바뀌어도 다른 행의 같은 말에 가려지지 않게 행마다 본다."""
        text = (ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
        rows = {line.split("|")[1].strip().split(" ")[0]: line for line in checklist_body(text).splitlines() if line.startswith("| H")}
        self.assertEqual(sorted(rows, key=lambda key: int(key[1:])), [f"H{n}" for n in range(1, 11)])
        for key, value_name in (("H2", "`chance.quality_gate`"), ("H3", "`chance.content_source`"), ("H4", "`chance.languages`")):
            with self.subTest(row=key):
                self.assertIn(value_name, rows[key])
                self.assertIn("잠금이 보증하지 않", rows[key])
                self.assertTrue("tests/test_resume_conditions_3_4.py" in rows[key] or "같은 시험이 못박습니다" in rows[key], rows[key])
        self.assertEqual(rows["H3"].count("`chance."), 2)               # content_source 와 source_policy 를 한 행에서 같이 본다
        self.assertIn("`chance.source_policy`", rows["H3"])
        self.assertNotIn("잠금이 보증하지 않", rows["H1"])               # 1·2 는 코드가 지킨다(L1–L8) — 보증한다고 적는다
        self.assertIn("코드로 지킨다", rows["H1"])

    def test_the_checklist_never_gives_the_ai_a_way_to_release(self):
        text = (ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
        section = checklist_body(text)
        self.assertIn("AI 는 변수 `PIPELINE_PAUSE` 를 지우거나 바꾸지 않", section)
        self.assertIn("해제하는 길을 만들지 않", section)
        for forbidden in ("AI 가 해제", "AI 가 변수를", "자동으로 해제", "자동 해제"):
            self.assertNotIn(forbidden, section, forbidden)


if __name__ == "__main__":
    unittest.main()
