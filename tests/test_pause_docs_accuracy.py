"""정지·킬 스위치 안내 문서의 정정(독립 감사 BP-S2 N1·N2·N3·N5, BA-S2 N9 — 결함 D-469–D-472)이 코드의 사실과 같은지 본다. 네트워크 없이 파일을 읽고 임시 폴더에 레지스트리 사본만 쓴다.

정정한 말이 틀린 말로 되돌아가거나(예: 'mode: off 가 Chance 도 멈춘다') 사실이 바뀌었는데 문서만 남는 것(예: 새 정지 대상 워크플로가 멈춤 표에 없음)을 막는다. 문장의 낱말은 글자 그대로 못박고,
코드의 사실(Chance 에서 mode off 는 매 실행 오류·검증이 모르는 최상위 키를 거절·초안 패키지 워크플로가 정지 변수를 읽음)은 코드를 불러 확인한다.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path

import _bootstrap
from pipeline import drafts, registry, source_policy

ROOT = _bootstrap.ROOT
TILDE = chr(0x7E)
PACKAGE_WORKFLOWS = ("naver.yml", "tistory.yml")


def doc(rel):
    return (ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def line_starting(text, start):
    found = [line for line in text.splitlines() if line.startswith(start)]
    assert len(found) == 1, (start, len(found))
    return found[0]


def guide_section(heading_prefix="### 3-9."):
    text = doc("docs/ACTIONS_GUIDE.md")
    start = text.index(heading_prefix)
    return text[start:text.index("\n### 3-10.", start)]


def workflow_name(file):
    head = doc(".github/workflows/" + file).split("\n", 1)[0]
    found = re.fullmatch(r'name: "(.+)"', head)
    assert found, head
    return found.group(1)


def with_registry(change):
    """진짜 레지스트리를 불러 change(reg)로 고친 사본을 임시 파일에 쓰고 그 경로를 돌려준다(진짜 파일은 건드리지 않는다)."""
    reg = json.loads((ROOT / "pipeline" / "blogs.json").read_text(encoding="utf-8"))
    change(reg)
    folder = tempfile.TemporaryDirectory()
    path = Path(folder.name) / "blogs.json"
    path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    return folder, path


class KillSwitchWordingTest(unittest.TestCase):
    """BP N1: 'mode: off 가 한 블로그 킬 스위치' 는 Chance 에는 맞지 않는다 — 안전 규칙 행·실행 안내서·사전·헌장이 같은 정정을 한다."""

    def test_the_security_row_says_chance_is_stopped_only_by_the_variable_and_off_means_resume(self):
        row = line_starting(doc("docs/SECURITY_GUARDRAILS.md"), "| G-O1 |")
        self.assertEqual(row.count("|"), 4)                                                    # 세 칸 — 칸 안에 세로선이 없다
        for needle in ("`PIPELINE_PAUSE=true`", "**멈추려면 `true`, `off` 는 재개로 읽힌다**", "레지스트리 `mode: \"off\"`", "**Chance 에는 맞지 않는다**", "`PIPELINE_PAUSE` 만이 멈춤 수단",
                       "생성기는 `mode` 를 읽지 않으며", "`publish_flow: pr`", "조용히 멈추지 않고 매 실행이 빨강으로 끝난다", "결함 D-469", "Blogger 영문·한글·네이버·티스토리"):
            self.assertIn(needle, row, needle)
        self.assertNotIn(TILDE, row)

    def test_the_guide_says_the_same_in_its_pause_section(self):
        section = guide_section()
        bullet = next(line for line in section.splitlines() if line.startswith("  - 한 블로그만 멈추려면"))
        for needle in ("Blogger(영문·한글)·네이버·티스토리는 레지스트리의 `mode: off`", "**Chance 는 이 방법이 맞지 않습니다**", "`PIPELINE_PAUSE` 만이 멈춤 수단", "Chance 생성기는 `mode` 를 읽지 않습니다",
                       "매 실행이 빨강으로 끝납니다", "BP-S2 N1"):
            self.assertIn(needle, bullet, needle)
        self.assertNotIn(TILDE, bullet)

    def test_the_glossary_and_the_charter_do_not_promise_that_mode_off_stops_chance(self):
        self.assertIn("한 블로그만 정지는 그 블로그의 `mode: off`(Chance 는 제외 — Chance 는 `PIPELINE_PAUSE` 만)", doc("docs/GLOSSARY.md"))
        self.assertIn("② 전체 정지", line_starting(doc("docs/GLOSSARY.md"), "| 정지·중단 |"))
        self.assertIn("(이유는 `note`, Chance 는 제외)", line_starting(doc("docs/GLOSSARY.md"), "| 정지·중단 |"))
        self.assertIn("또는 레지스트리 `mode: off`(Chance 는 제외 — `PIPELINE_PAUSE` 만)", line_starting(doc("docs/CHARTER.md"), "| 킬 스위치 |"))

    def test_the_code_really_behaves_as_the_words_say(self):
        """말이 맞는지 코드로: Chance 의 승인 흐름에서 mode 를 off 로 바꾸면 발행 흐름 읽기가 멈추고(매 실행 오류) 레지스트리 검증도 거절한다. 다른 블로그의 mode off 는 실행 대상에서 빠진다."""
        folder, path = with_registry(lambda reg: next(blog for blog in reg["blogs"] if blog["key"] == "chance").update({"mode": "off"}))
        with folder:
            with self.assertRaises(drafts.DraftFlowError):
                drafts.chance_flow(path)
            errors = registry.validate_registry(registry.load_registry(path), ROOT)
            self.assertTrue([text for text in errors if "mode 는 auto" in text], errors)                  # '(pr 이면 mode 는 auto)' 검증 오류
        real = registry.load_registry()
        self.assertEqual(drafts.chance_flow(), "pr")                                           # 지금 레지스트리는 승인 흐름이다 — 위 말이 지금 사실에 서 있다
        others = [blog["key"] for blog in real["blogs"] if blog["key"] != "chance"]
        self.assertTrue(others)
        folder, path = with_registry(lambda reg: [blog.update({"mode": "off"}) for blog in reg["blogs"] if blog["key"] != "chance"])
        with folder:
            self.assertEqual([blog["key"] for blog in registry.enabled_blogs(registry.load_registry(path))], ["chance"])      # mode off 면 Chance 밖은 모두 대상에서 빠진다


class OffMeansResumeTest(unittest.TestCase):
    """BP N5: '멈추려면 true, off 는 재개' 를 굵게 — 운영자가 읽는 안내(실행 안내서 3-9 의 변수 만들기 단계)와 규칙(PUBLISH_PATHS 7번 23항)."""

    def test_the_variable_step_of_the_guide_has_the_bold_warning(self):
        step = next(line for line in guide_section().splitlines() if line.startswith("  2. Name에 `PIPELINE_PAUSE`"))
        for needle in ("**멈추려면 `true`, `off` 는 재개입니다**", "`off`·`false`·`0`·`no` 는 꺼짐으로 읽혀 계속 돕니다", "'끔' 뜻으로 `off` 를 쓰면 반대로 돕니다", "`disabled`·`stop`·`paused`", "안전한 쪽인 정지로 읽힙니다"):
            self.assertIn(needle, step, needle)

    def test_the_publish_paths_item_has_the_bold_warning_and_the_code_agrees_on_the_values(self):
        item = line_starting(doc("docs/PUBLISH_PATHS.md"), "23. **발행 정지 변수의 값은")
        self.assertIn("**멈추려면 `true`, `off` 는 재개다**", item)
        self.assertIn("결함 D-471", item)
        from pipeline import pause
        for value in ("off", "false", "0", "no", " OFF "):
            self.assertEqual(pause.state({"PIPELINE_PAUSE": value}), pause.OFF, value)         # off 는 꺼짐 = 재개다
        for value in ("true", "1", "yes", "on"):
            self.assertEqual(pause.state({"PIPELINE_PAUSE": value}), pause.ON, value)
        for value in ("disabled", "stop", "paused"):
            self.assertEqual(pause.state({"PIPELINE_PAUSE": value}), pause.UNKNOWN, value)     # 모르는 값은 정지로 읽힌다


class PauseTableTest(unittest.TestCase):
    """BP N3: 실행 안내서 3-9 의 '멈춤' 표에 네이버·티스토리 초안 패키지가 있다 — 이름은 워크플로 파일의 진짜 이름이고, 그 워크플로가 정말 정지 변수를 받는다."""

    def test_the_stop_row_lists_both_package_workflows_by_their_real_names(self):
        section = guide_section()
        stop_row = line_starting(section, "| 멈춤 |")
        keep_row = line_starting(section, "| 안 멈춤 |")
        for file in PACKAGE_WORKFLOWS:
            name = workflow_name(file)
            self.assertIn(f"`{name}`", stop_row, file)
            self.assertNotIn(f"`{name}`", keep_row, file)
            self.assertIn("PIPELINE_PAUSE: ${{ vars.PIPELINE_PAUSE }}", doc(".github/workflows/" + file), file)           # 코드 쪽 사실: 정지 변수를 그대로 받는다
        self.assertIn("같은 러너가 같은 변수를 읽어 초안 이슈를 만들지 않음", stop_row)
        self.assertIn("Chance·Blogger(영문·한글)·네이버·티스토리 초안 패키지·이슈 수정을 함께 멈추고", section)
        self.assertEqual(stop_row.count("|"), 3)                                                 # 두 칸

    def test_the_package_runner_really_stops_on_the_variable_before_anything_else(self):
        """초안 패키지 러너(pipeline/run.py)의 처리 순서 첫 칸이 정지 변수다 — 표의 말('이슈를 만들지 않음')의 근거(ARCHITECTURE 의 처리 순서 문장과 같은 사실)."""
        text = doc("docs/ARCHITECTURE.md")
        sentence = next(line for line in text.splitlines() if line.startswith("**초안 패키지 실행(`mode: package`, 티스토리·네이버)의 처리 순서**"))
        self.assertTrue(sentence.split("처리 순서**: ", 1)[1].startswith("`PIPELINE_PAUSE` →"))
        source = doc("pipeline/run.py")
        self.assertLess(source.index("pause.is_paused(environ)"), source.index("blog[\"mode\"] == \"off\" and not auth_only"))


class UnknownTopLevelKeyTest(unittest.TestCase):
    """BP N2: 모양이 다른 모르는 최상위 키는 레지스트리 검증을 부르는 실행 길에서 실행도 멈춘다 — PUBLISH_PATHS 7번 16항."""

    def test_the_item_names_the_runtime_paths_that_stop_and_the_ones_that_do_not(self):
        item = line_starting(doc("docs/PUBLISH_PATHS.md"), "16. **실행 시 멈춤은 오타로 '보이는' 키만 본다**")
        for needle in ("검증기 REG-1)가 거절하고", "레지스트리 검증(`validate_registry`)을 부르는 실행 길에서는 실행도 멈춘다", "Blogger 러너(`pipeline/run.py` 가 설정 오류로 끝낸다)",
                       "Chance 의 facts 시작 점검(`source_policy.fact_start` — 글을 만들지 않는다)", "워치독", "`pipeline.plan`", "결함 D-470", "그 검증을 부르지 않는 길(Chance feed 의 생성기 가드와 `chance_flow`)"):
            self.assertIn(needle, item, needle)
        self.assertNotIn("실행 시에는 막지 않는다", item)                                           # 옛 말은 사라졌다
        self.assertNotIn(TILDE, item)

    def test_the_named_paths_really_call_the_registry_validation_and_stop_on_an_unknown_key(self):
        for rel, needle in (("pipeline/run.py", "errors = validate_registry(reg, root)"), ("pipeline/source_policy.py", "found = registry.validate_registry(reg)"),
                            ("scripts/watchdog.py", "errors = validate_registry(reg, ROOT)"), ("pipeline/plan.py", "errors = validate_registry(reg, ROOT)")):
            self.assertIn(needle, doc(rel), rel)
        folder, path = with_registry(lambda reg: reg.update({"zzz_unknown_top_key": 1}))
        with folder:
            errors = registry.validate_registry(registry.load_registry(path), ROOT)
            self.assertTrue([text for text in errors if "zzz_unknown_top_key" in text], errors)           # 검증이 모르는 최상위 키를 거절한다
            problems, _ = source_policy.fact_start("2026-11-24", "noaa_swpc", registry_path=path)
            self.assertTrue([text for text in problems if "레지스트리 검증 오류" in text], problems)          # facts 시작 점검이 그 오류를 문제로 삼아 글을 만들지 않는다
        # 대조: Chance feed 의 발행 흐름 읽기(chance_flow)는 검증을 부르지 않는다 — 문서가 '그 검증을 부르지 않는 길' 이라고 적은 곳
        self.assertNotIn("validate_registry", doc("pipeline/drafts.py"))


class PauseUnknownIssueProcedureTest(unittest.TestCase):
    """BA N9: 워치독의 PAUSE_UNKNOWN 이슈는 값을 true 로 고치면 자동으로 닫히지 않는다 — 닫는 일을 AI 가 챙기는 절차가 런북 J6 에 있고, 이슈에 쓸 수 없다는 J2 의 규칙과 어긋나지 않는다."""

    def test_j6_has_the_procedure_as_item_7_after_item_6(self):
        runbook = doc("docs/AGENT_RUNBOOK.md")
        section = runbook[runbook.index("### J6."):runbook.index("### J7.")]
        item = line_starting(section, "7. **`[Watchdog] 공통: PAUSE_UNKNOWN` 이슈**")
        for needle in ("결함 D-472", "값을 고치는 것은 운영자 몫", "AI 는 변수를 만지지 않습니다", "`true` 로 고치면 워치독이 조용해져 **이슈가 자동으로 닫히지 않습니다**", "**닫는 일은 AI 가 맡습니다**",
                       "J2 의 4", "이슈에 쓰지 않습니다", "번호 있는 `info` 요청(J3)", "'이슈 #번호는 닫아도 됩니다'", "다음 J6 점검에서 확인", "`decision` 요청"):
            self.assertIn(needle, item, needle)
        self.assertLess(section.index("\n6. 감시 도구가 있는 세션"), section.index("\n7. **`[Watchdog] 공통: PAUSE_UNKNOWN` 이슈**"))
        self.assertIn("이슈를 닫거나 코멘트를 달지 않습니다(쓸 수 없고, 자기 자격증명으로 쓰지도 않습니다)", runbook)         # J2 의 4 — 절차가 기대는 규칙이 그대로 있다
        self.assertNotIn(TILDE, item)

    def test_the_alert_row_and_the_alert_text_agree_with_the_procedure(self):
        row = line_starting(doc("docs/ACTIONS_GUIDE.md"), "| `PAUSE_UNKNOWN` |")
        self.assertEqual(row.count("|"), 5)                                                       # 네 칸
        self.assertIn("`true` 로 고치면 직접 닫습니다(운영자가 GitHub 화면을 보지 않으므로 AI 가 `docs/AGENT_RUNBOOK.md` J6 의 7번 절차로 닫는 일을 챙깁니다)", row)
        watchdog = doc("scripts/watchdog.py")
        self.assertIn("true 로 고치면 일부러 멈춘 상태로 읽혀 워치독이 조용해지므로 이 알림은 직접 닫으세요", watchdog)          # 알림 문장은 그대로(T2 코드는 이 일에서 안 바꾼다)


class RegisterRowsTest(unittest.TestCase):
    """결함 행 D-469–D-472 가 한 번씩만 있고 여섯 칸이며 심각도·시험 파일·상태를 말한다(문서와 시험이 어긋나지 않게)."""

    EXPECTED = {"D-469": "낮음", "D-470": "낮음", "D-471": "낮음", "D-472": "정보"}

    def test_each_row_exists_once_with_six_cells_and_names_this_test_file(self):
        text = doc("docs/DEFECT_REGISTER.md")
        order = []
        for number, severity in self.EXPECTED.items():
            rows = [line for line in text.split("\n") if line.startswith(f"| **{number}** |")]
            self.assertEqual(len(rows), 1, number)
            row = rows[0]
            self.assertEqual(row.count("|"), 7, number)                                     # 여섯 칸 — 칸 안에 세로선이 없다
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            self.assertEqual(cells[1], severity, number)
            self.assertIn("tests/test_pause_docs_accuracy.py", cells[3], number)
            self.assertTrue(cells[4].startswith("**해결**"), number)
            self.assertNotIn(TILDE, row, number)
            self.assertNotIn("{" + "{", row, number)
            order.append(text.index(f"| **{number}** |"))
        self.assertEqual(order, sorted(order))
        self.assertLess(text.index("| **D-468** |"), order[0])                              # D-468(워크플로 줄 시험) 다음에 이어 붙었다


class RollbackTableTest(unittest.TestCase):
    """공학 안내서 10절 롤백 표의 '블로그 한 곳을 멈춤' 줄도 같은 말을 한다 — Chance 는 제외(독립 검증 BFIX1-S R1)."""

    def row(self):
        return line_starting(doc("docs/ENGINEERING_GUIDE.md"), "| 블로그 한 곳을 멈춤 |")

    def test_the_row_names_the_blogs_it_fits_and_excludes_chance(self):
        row = self.row()
        for needle in ('`mode: "off"`', "Blogger·네이버·티스토리에만 맞고", "**Chance 는 제외**", "`PIPELINE_PAUSE` 만 멈춤 수단", "`mode: off` 는 검증이 거절해 매 실행 빨강", "(T3 아님, 안전 방향)"):
            self.assertIn(needle, row, needle)
        self.assertNotIn(TILDE, row)
        self.assertNotIn("{" + "{", row)

    def test_the_row_is_still_a_two_cell_table_row(self):
        cells = [cell.strip() for cell in self.row().strip().strip("|").split("|")]
        self.assertEqual(len(cells), 2, cells)
        self.assertEqual(cells[0], "블로그 한 곳을 멈춤")


if __name__ == "__main__":
    unittest.main()
