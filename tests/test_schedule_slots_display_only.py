"""레지스트리의 chance.schedule.slots_kst 는 코드가 읽지 않는 표시용 값이다 — 코드가 읽는 값(POST_HOURS_KST 의 기본 9,18)과 같은지 대조한다(BP-S1-9, 결함 D-419). 네트워크 없이 돈다.

배경: 게시 시각(슬롯)은 generator.py 의 SLOT_HOURS 가 환경 변수 POST_HOURS_KST(기본 "9,18")에서 만들고, 워크플로는 이 변수를 넘기지 않는다. 레지스트리의 `schedule.slots_kst` 는 Python 코드·시험 어디에서도 읽지 않아
값을 고쳐도 게시 시각이 바뀌지 않는다 — 일정을 조정하려는 사람이 효과 없는 설정 변경을 병합할 수 있다. 레지스트리 값은 이 일이 바꾸지 않으므로(T3), 두 값이 같은지 대조하는 시험을 두고(어긋나면 빨강)
문서(docs/ARCHITECTURE.md 레지스트리 필드 표 아래)에 '표시용' 임을 적었다.
"""
import ast
import json
import re
import unittest

import _bootstrap

ROOT = _bootstrap.ROOT


def generator_default_hours():
    """generator.py 의 `os.environ.get("POST_HOURS_KST", "<기본>")` 의 기본 문자열을 소스에서 읽어 시 목록으로 만든다(모듈을 불러오지 않는다 — 환경 변수에 영향받지 않는다)."""
    tree = ast.parse((ROOT / "generator.py").read_text(encoding="utf-8"))
    defaults = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and len(node.args) == 2
                and isinstance(node.args[0], ast.Constant) and node.args[0].value == "POST_HOURS_KST" and isinstance(node.args[1], ast.Constant)):
            defaults.append(node.args[1].value)
    assert len(defaults) == 1, defaults
    return sorted({int(piece) for piece in defaults[0].split(",") if piece.strip().isdigit()})


def registry_chance():
    data = json.loads((ROOT / "pipeline" / "blogs.json").read_text(encoding="utf-8"))
    return next(blog for blog in data["blogs"] if blog["key"] == "chance")


class SlotsKstIsDisplayOnlyTest(unittest.TestCase):
    def test_the_registry_slots_equal_the_hours_the_generator_really_uses(self):
        shown = sorted(registry_chance()["schedule"]["slots_kst"])
        used = generator_default_hours()
        self.assertEqual(shown, used, f"레지스트리 schedule.slots_kst {shown} 는 표시용이고 게시 시각은 generator.py 의 POST_HOURS_KST(기본 {used})가 정한다 — 일정을 바꾸려면 코드(또는 워크플로 환경 변수)를 바꾸고 두 값을 같게 맞춘다")

    def test_no_workflow_overrides_the_post_hours_so_the_code_default_is_the_real_schedule(self):
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            self.assertNotIn("POST_HOURS_KST", path.read_text(encoding="utf-8"), path.name)

    def test_nothing_in_the_python_code_reads_the_registry_slots(self):
        """'읽지 않는 표시용 값' 이라는 전제 확인: 코드에서 slots_kst 를 읽는 곳이 없다. 읽는 코드가 생기면 이 시험이 알려 이 전제와 문서를 고치게 한다."""
        readers = []
        for path in [ROOT / "generator.py", ROOT / "blogger_generator.py", *sorted((ROOT / "pipeline").rglob("*.py")), *sorted((ROOT / "scripts").glob("*.py"))]:
            if "slots_kst" in path.read_text(encoding="utf-8"):
                readers.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(readers, [])

    def test_the_architecture_doc_says_it_is_display_only(self):
        text = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        start = text.index("`schedule.slots_kst`")
        note = text[start:text.index("\n", start)]
        for needle in ("표시용", "POST_HOURS_KST", "BP-S1-9", "D-419", "tests/test_schedule_slots_display_only.py"):
            self.assertIn(needle, note, needle)
        self.assertNotIn(chr(126), note)
        self.assertIsNone(re.search(r"https?://", note))


if __name__ == "__main__":
    unittest.main()
