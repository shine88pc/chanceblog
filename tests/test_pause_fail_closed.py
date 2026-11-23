"""발행 정지 변수 PIPELINE_PAUSE 의 알 수 없는 값은 정지로 읽는다(BP-S1-3, 결함 D-412) — 읽는 모든 곳이 같은 값에 같은 판정을 한다. 네트워크 없이 돈다.

배경: 읽는 곳마다 {1,true,yes,on} 복사본이 있고 나머지(enabled·paused·y·ture·2 …)를 모두 '정지 아님' 으로 읽어 값 오타 하나로 킬 스위치가 조용히 꺼졌다. 이제 pipeline/pause.py 한 곳이 읽고
(켜짐 1·true·yes·on, 꺼짐 0·false·no·off·비움, 그 밖은 정지 + ::error:: 한 줄), 생성기·Blogger 러너·초안 올리기·이슈 수정 처리기·워치독·확인 필요 모음이 모두 그것을 부른다.
이 시험이 지키는 것: ① 값 표(감사 탐침의 20개 + 덧붙인 값)의 판정 ② 지금 정지가 걸리는 값은 하나도 풀리지 않는다(옛 읽기와 대조한 전수·조합 시험) ③ 읽는 곳 여섯이 실제 실행 경로에서 같은 판정
(그림자 실행의 안내 줄은 test_shadow_run) ④ 알 수 없는 값은 고정 문장 한 줄만 내고 받은 값을 로그에 싣지 않는다 ⑤ 코드 어디에도 이 변수를 따로 읽는 곳이 없다(구조 시험).
"""
import ast
import contextlib
import io
import itertools
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))      # 워치독·확인 필요 모음 스크립트(scripts/)를 불러온다

import generator as g  # noqa: E402
import ops_inbox as oi  # noqa: E402
import ops_inbox_helpers as oh  # noqa: E402
import watchdog  # noqa: E402
from edits_helpers import issue, make_edit_root, page_body  # noqa: E402
from pipeline import draft_flow, inbox, pause  # noqa: E402
from pipeline import run as run_mod  # noqa: E402
from pipeline.edits import runner  # noqa: E402
from test_run import make_root  # noqa: E402

ROOT = _bootstrap.ROOT

try:
    import yaml
except ImportError:      # PyYAML 이 없는 환경(CI 모양의 로컬)에서는 이슈 수정 처리기 읽는 곳 시험을 건너뛴다 — 처리기가 명세 파일(edit-spec.yml)을 PyYAML 로 읽는다
    yaml = None


def blogger_key():
    """임시 저장소(make_root)가 mode 를 꺼 두는 Blogger 블로그의 키 — 레지스트리의 첫 blogger 항목(실제 이름을 이 파일에 적지 않는다)."""
    data = json.loads((ROOT / "pipeline" / "blogs.json").read_text(encoding="utf-8"))
    return next(blog["key"] for blog in data["blogs"] if blog["platform"] == "blogger")


BLOGGER_KEY = blogger_key()

# 감사 탐침(BP-S1 probe_pause_budget)의 값 20개 — 켜짐 7·꺼짐 3·알 수 없음 10
PROBE_VALUES = ["true", "TRUE", " true ", "1", "yes", "on", "On", "enabled", "paused", "pause", "stop", "y", "Y", "t", "false", "0", "", "ture", "truee", "2"]
PROBE_ON = ("true", "TRUE", " true ", "1", "yes", "on", "On")
PROBE_OFF = ("false", "0", "")
PROBE_UNKNOWN = ("enabled", "paused", "pause", "stop", "y", "Y", "t", "ture", "truee", "2")

FULLWIDTH_TRUE = "".join(chr(code) for code in (0xFF34, 0xFF32, 0xFF35, 0xFF25))       # 전각 TRUE — 옛 읽기는 '정지 아님'
ZERO_WIDTH_TRUE = chr(0x200B) + "true"                                                  # 보이지 않는 글자가 붙은 true
BOM_TRUE = chr(0xFEFF) + "true"
NBSP_TRUE = chr(0xA0) + "true" + chr(0xA0)                                              # 앞뒤 공백 처리(str.strip)가 지우는 공백 — 옛 읽기도 정지
EXTRA_ON = ("TrUe", " YES ", "\ton\n", "ON", "1 ", NBSP_TRUE, "\r\ntrue\r\n")
EXTRA_OFF = ("False", " no ", "OFF", "\n", "  ", "\t", "0 ", " Off\r\n")
EXTRA_UNKNOWN = ("disabled", "none", "null", "maybe", "on1", "1 1", "-1", "0.0", "yes please", "enable", "n", "f", "2.0", "01", "tru", "truee ", "paused ", FULLWIDTH_TRUE, ZERO_WIDTH_TRUE, BOM_TRUE,
                 "true,false", "true;", "'true'", '"true"', "off off")      # NUL 글자가 든 값은 환경 변수에 넣을 수 없는 플랫폼(리눅스)이 있어 읽는 곳 시험이 아니라 classify 시험에서만 본다
ALL_ON = PROBE_ON + EXTRA_ON
ALL_OFF = PROBE_OFF + EXTRA_OFF
ALL_UNKNOWN = PROBE_UNKNOWN + EXTRA_UNKNOWN
INJECTION = "evil" + chr(10) + "::set-output name=x::y"       # 받은 값이 줄바꿈과 '::' 를 품어도 로그에 실리지 않아야 한다

OLD_ON = {"1", "true", "yes", "on"}


def old_reading(value):
    """고치기 전의 읽기(생성기·초안 올리기·이슈 수정 처리기·Blogger 러너·워치독이 모두 같은 식이었다)."""
    return str(value).strip().lower() in OLD_ON


def pause_error_lines(text):
    return [line for line in text.splitlines() if line.startswith("::error::") and "PIPELINE_PAUSE" in line]


class ValueTableTest(unittest.TestCase):
    def test_the_probe_table_has_twenty_values_and_the_expected_split(self):
        self.assertEqual(len(PROBE_VALUES), 20)
        self.assertEqual(sorted(PROBE_ON + PROBE_OFF + PROBE_UNKNOWN), sorted(PROBE_VALUES))

    def test_the_value_sets_are_exactly_the_documented_ones(self):
        self.assertEqual(pause.ON_VALUES, frozenset({"1", "true", "yes", "on"}))
        self.assertEqual(pause.OFF_VALUES, frozenset({"0", "false", "no", "off"}))
        self.assertEqual(pause.ON_VALUES & pause.OFF_VALUES, frozenset())
        self.assertEqual(pause.VAR, "PIPELINE_PAUSE")

    def test_every_value_gets_the_documented_state(self):
        for values, expected in ((ALL_ON, pause.ON), (ALL_OFF, pause.OFF), (ALL_UNKNOWN, pause.UNKNOWN)):
            for value in values:
                with self.subTest(value=value):
                    self.assertEqual(pause.classify(value), expected)
                    self.assertEqual(pause.state({pause.VAR: value}), expected)
                    self.assertEqual(pause.is_paused({pause.VAR: value}), expected != pause.OFF)
                    self.assertEqual(pause.is_unrecognized({pause.VAR: value}), expected == pause.UNKNOWN)

    def test_a_missing_or_none_value_is_off_like_before(self):
        self.assertEqual(pause.state({}), pause.OFF)
        self.assertEqual(pause.state({pause.VAR: None}), pause.OFF)
        self.assertFalse(pause.is_paused({}))
        self.assertFalse(pause.is_paused({pause.VAR: None}))

    def test_a_value_with_an_embedded_nul_is_unknown_and_pauses(self):
        """환경 변수에는 넣을 수 없는 값이지만(리눅스) 함수는 사전 값을 받으므로 정지로 읽는다."""
        for value in ("true" + chr(0) + "x", chr(0), "on" + chr(0), chr(0) + "off"):
            with self.subTest(value=value):
                self.assertEqual(pause.classify(value), pause.UNKNOWN)
                self.assertTrue(pause.is_paused({pause.VAR: value}))

    def test_non_string_values_follow_their_text(self):
        for value, expected in ((1, pause.ON), (True, pause.ON), (0, pause.OFF), (False, pause.OFF), (2, pause.UNKNOWN), (1.5, pause.UNKNOWN)):
            with self.subTest(value=value):
                self.assertEqual(pause.classify(value), expected)

    def test_the_one_line_error_is_fixed_text_without_the_received_value(self):
        line = pause.error_line()
        self.assertTrue(line.startswith("::error::"))
        self.assertIn("PIPELINE_PAUSE", line)
        self.assertNotIn("\n", line)
        for word in ("1·true·yes·on", "0·false·no·off"):
            self.assertIn(word, line)
        tagged = pause.error_line("[tag] ")
        self.assertTrue(tagged.startswith("::error::[tag] "))
        self.assertEqual(tagged.count("::"), line.count("::"))       # 머리를 붙여도 '::' 가 늘지 않는다
        self.assertEqual(pause.SENTENCE, line[len("::error::"):])


class NothingThatPausesTodayIsReleasedTest(unittest.TestCase):
    """지금 정지가 걸리는 값은 하나도 풀리면 안 된다 — 옛 읽기와 대조한다."""

    ALPHABET = ("t", "r", "u", "e", "y", "s", "o", "n", "1", "0", " ", "T", chr(10), "x")

    def test_exhaustive_short_strings_never_go_from_paused_to_running(self):
        checked = 0
        for length in range(0, 5):
            for chars in itertools.product(self.ALPHABET, repeat=length):
                value = "".join(chars)
                checked += 1
                if old_reading(value):
                    self.assertTrue(pause.is_paused({pause.VAR: value}), repr(value))
                    self.assertEqual(pause.classify(value), pause.ON, repr(value))
        self.assertGreater(checked, 38000)

    def test_every_case_and_padding_combination_of_the_on_words_still_pauses(self):
        paddings = ("", " ", "\t", "\n", "  \r\n ", chr(0xA0))
        count = 0
        for word in sorted(OLD_ON):
            for mask in range(2 ** len(word)):
                cased = "".join(ch.upper() if mask >> i & 1 else ch for i, ch in enumerate(word))
                for left, right in itertools.product(paddings, repeat=2):
                    value = left + cased + right
                    count += 1
                    self.assertTrue(old_reading(value), repr(value))
                    self.assertEqual(pause.classify(value), pause.ON, repr(value))
        self.assertGreater(count, 500)

    def test_every_documented_off_spelling_is_still_running(self):
        paddings = ("", " ", "\t", "\n")
        for word in sorted(pause.OFF_VALUES):
            for mask in range(2 ** len(word)):
                cased = "".join(ch.upper() if mask >> i & 1 else ch for i, ch in enumerate(word))
                for left, right in itertools.product(paddings, repeat=2):
                    value = left + cased + right
                    self.assertEqual(pause.classify(value), pause.OFF, repr(value))
        for value in ("", " ", "\n", "\t "):
            self.assertEqual(pause.classify(value), pause.OFF, repr(value))

    def test_the_shadow_run_on_set_still_contains_the_pause_on_set(self):
        self.assertLessEqual(pause.ON_VALUES, g.SHADOW_RUN_ON_VALUES)          # generator.py 의 SHADOW_RUN 설명 주석이 기대는 포함 관계


class ReaderBase(unittest.TestCase):
    """읽는 곳 여섯이 실제 실행 경로에서 판정을 내는 모양. 돌려주는 값: (정지로 읽었나, 그 실행의 출력 글)."""

    def tmpdir(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name)

    # 1) 생성기(Chance) main() — 정지가 아니면 잠금 가드 호출에 닿는다(가드를 가짜로 바꿔 거기서 멈춘다)
    def read_generator(self, value):
        reached = RuntimeError("잠금 가드까지 왔다")
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, {"PIPELINE_PAUSE": value, "SHADOW_RUN": ""}), mock.patch("pipeline.publish_lock.guard_start", side_effect=reached), contextlib.redirect_stdout(buffer):
            try:
                g.main()
                paused = True
            except RuntimeError as exc:
                if exc is not reached:
                    raise
                paused = False
        return paused, buffer.getvalue()

    # 2) Blogger 러너 — 정지가 아니면 mode off 건너뜀(다음 줄)에 닿는다
    def read_blogger(self, value):
        root = make_root(self.tmpdir() / "blogger", mode="off")
        temp_registry = json.loads((root / "pipeline" / "blogs.json").read_text(encoding="utf-8"))
        self.assertEqual(next(blog["mode"] for blog in temp_registry["blogs"] if blog["key"] == BLOGGER_KEY), "off")      # 임시 저장소가 이 블로그를 꺼 두었는지(정지가 아니면 mode off 건너뜀에 닿는다)
        lines = []
        code = run_mod.run(["--blog", BLOGGER_KEY, "--root", str(root)], environ={"PIPELINE_PAUSE": value}, out=lines.append)
        text = "\n".join(lines)
        self.assertEqual(code, 0, text)
        paused = "code=PAUSED" in text
        self.assertTrue(paused or "code=MODE_OFF" in text, text)
        return paused, text

    # 3) 초안 올리기(deliver) — 정지가 아니면 연습 실행 안내(DRY_RUN)에 닿는다
    def read_draft_flow(self, value):
        lines = []
        code = draft_flow.run(env={"PIPELINE_PAUSE": value, "DRY_RUN": "1"}, out=lines.append)
        text = "\n".join(lines)
        self.assertEqual(code, 0, text)
        paused = "[일시정지]" in text
        self.assertTrue(paused or "[DRY_RUN]" in text or "direct" in text, text)
        return paused, text

    # 4) 이슈 수정 처리기 — 정지면 status paused(AI·이미지 검색 호출 0), 아니면 ok
    def read_issue_edit(self, value):
        root = make_edit_root(self.tmpdir() / "edit")
        calls = []

        def llm(prompt):
            calls.append(prompt)
            return "{}", "m"

        iss = issue(page_body(before="문의는 old@example.com 으로 보내 주세요.", after="문의는 new@example.com 으로 보내 주세요."))
        res = runner.process_issue(iss, root, env={"GITHUB_RUN_NUMBER": "5", "PIPELINE_PAUSE": value}, llm=llm, image_picker=lambda queries, used: "x")
        paused = res.status == "paused"
        self.assertIn(res.status, ("paused", "ok"), res.message)
        if paused:
            self.assertEqual(calls, [])
        return paused, "\n".join([res.message, res.comment, *res.notes])

    # 5) 워치독 — 정지면 알림을 만들지 않고 '[일시정지]' 한 줄, 아니면 점검을 이어 간다
    def read_watchdog(self, value):
        env = {"PIPELINE_PAUSE": value, "WATCHDOG_DRY_RUN": "1"}
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, env), mock.patch.object(watchdog, "load_registry", return_value={"blogs": []}), mock.patch.object(watchdog, "validate_registry", return_value=[]), \
                mock.patch.object(watchdog, "collect", return_value=([], [])), contextlib.redirect_stdout(buffer):
            for name in ("GITHUB_TOKEN", "GITHUB_REPOSITORY", "GITHUB_STEP_SUMMARY"):
                os.environ.pop(name, None)
            code = watchdog.main()
        text = buffer.getvalue()
        self.assertEqual(code, 0, text)
        paused = "[일시정지]" in text
        self.assertTrue(paused or "이상 없음" in text, text)
        return paused, text

    # 6) 확인 필요 모음 — 정지 사실(Snapshot.paused)을 만들어 규칙에 넘긴다
    def read_ops_inbox(self, value):
        tmp = self.tmpdir()
        root = oh.make_root(tmp / "repo", workflows=("chanceblog.yml", "blogger.yml"))
        fake = oh.FakeGitHub()
        seen = {}
        real = inbox.Snapshot

        def spy(*args, **kwargs):
            seen["paused"] = kwargs["paused"]
            return real(*args, **kwargs)

        environ = {"GITHUB_REPOSITORY": oh.REPO, "GITHUB_TOKEN": "t" * 8, "GITHUB_REPOSITORY_OWNER": "octo", "GITHUB_STEP_SUMMARY": str(tmp / "summary.md"), "PIPELINE_PAUSE": value}
        lines = []
        with mock.patch.object(inbox, "Snapshot", spy):
            oi.run(environ, fake, oh.NOW, root, lines.append, sleep=lambda seconds: None)
        self.assertIn("paused", seen)
        return seen["paused"], "\n".join(lines)

    READERS = ("generator", "blogger", "draft_flow", "issue_edit", "watchdog", "ops_inbox") if yaml is not None else ("generator", "blogger", "draft_flow", "watchdog", "ops_inbox")

    def read(self, reader, value):
        return getattr(self, "read_" + reader)(value)


class ReadersAgreeTest(ReaderBase):
    def test_every_reader_gives_the_documented_verdict_for_the_whole_value_table(self):
        values = [(value, False, False) for value in PROBE_OFF] + [(value, True, False) for value in PROBE_ON] + [(value, True, True) for value in PROBE_UNKNOWN]
        self.assertEqual(len(values), 20)
        for value, paused, unknown in values:
            for reader in self.READERS:
                with self.subTest(value=value, reader=reader):
                    got, out = self.read(reader, value)
                    self.assertEqual(got, paused, f"{reader} {value!r}: {out[:300]}")

    def test_the_extra_values_give_the_same_verdict_in_every_reader(self):
        extras = [(value, False) for value in EXTRA_OFF] + [(value, True) for value in EXTRA_ON + EXTRA_UNKNOWN]
        for value, paused in extras:
            verdicts = {reader: self.read(reader, value)[0] for reader in self.READERS}
            with self.subTest(value=value):
                self.assertEqual(set(verdicts.values()), {paused}, verdicts)

    def test_an_unknown_value_leaves_exactly_one_error_line_where_the_reader_prints_workflow_lines(self):
        for reader in ("generator", "blogger", "draft_flow", "watchdog", "ops_inbox"):
            for value in PROBE_UNKNOWN:
                with self.subTest(reader=reader, value=value):
                    paused, out = self.read(reader, value)
                    self.assertTrue(paused)
                    lines = pause_error_lines(out)
                    self.assertEqual(len(lines), 1, out)
                    self.assertIn("1·true·yes·on", lines[0])

    def test_a_known_value_never_leaves_the_error_line(self):
        for reader in self.READERS:
            for value in PROBE_ON + PROBE_OFF:
                with self.subTest(reader=reader, value=value):
                    self.assertEqual(pause_error_lines(self.read(reader, value)[1]), [])

    @unittest.skipUnless(yaml is not None, "PyYAML(requirements-dev.txt)이 필요합니다 — 이슈 수정 처리기가 명세 파일(edit-spec.yml)을 읽는다(CI 에서는 항상 실행됩니다)")
    def test_the_issue_edit_runner_says_so_in_its_notes_and_comment_without_a_workflow_line(self):
        for value in PROBE_UNKNOWN:
            with self.subTest(value=value):
                paused, text = self.read_issue_edit(value)
                self.assertTrue(paused)
                self.assertIn("알 수 없어 정지로 읽", text)
                self.assertIn("일시정지 중", text)
                self.assertNotIn("::", text)
        paused, text = self.read_issue_edit("true")
        self.assertTrue(paused)
        self.assertIn("켜져 있어", text)              # 켜짐 값의 문장은 그대로다
        self.assertNotIn("알 수 없어", text)

    def test_the_received_value_is_never_printed_even_when_it_carries_a_workflow_command(self):
        for reader in self.READERS:
            with self.subTest(reader=reader):
                paused, out = self.read(reader, INJECTION)
                self.assertTrue(paused)
                self.assertNotIn("evil", out)
                self.assertNotIn("set-output", out)

    def test_the_known_on_wording_of_each_reader_is_unchanged(self):
        """켜짐 값의 로그 문장·알림은 이전과 바이트 단위로 같다(알 수 없는 값만 문장이 다르다)."""
        paused, out = self.read_generator("true")
        self.assertIn("[SKIP] code=PAUSED var=PIPELINE_PAUSE", out)
        self.assertIn("[일시정지] PIPELINE_PAUSE 가 켜져 있어 실행하지 않습니다.", out)
        self.assertIn("::notice::PIPELINE_PAUSE 가 켜져 있어 Chance_Blog 실행을 건너뛰었습니다.", out)
        paused, out = self.read_blogger("true")
        self.assertIn(f"::notice::[{BLOGGER_KEY}] 저장소 변수 PIPELINE_PAUSE 가 켜져 있어 이번 실행을 건너뜁니다.", out)
        paused, out = self.read_draft_flow("true")
        self.assertIn("[일시정지] PIPELINE_PAUSE 가 켜져 있어 초안 올리기·정리를 하지 않습니다.", out)
        paused, out = self.read_watchdog("true")
        self.assertIn("[일시정지] PIPELINE_PAUSE 가 켜져 있어 점검 알림을 만들지 않습니다.", out)


class StructureTest(unittest.TestCase):
    """코드 어디에도 PIPELINE_PAUSE 를 따로 읽는 곳이 없다 — 읽기는 pipeline/pause.py 한 곳이다."""

    @staticmethod
    def sources():
        files = [ROOT / "generator.py", ROOT / "blogger_generator.py", *sorted((ROOT / "pipeline").rglob("*.py")), *sorted((ROOT / "scripts").rglob("*.py"))]
        return [path for path in files if path.exists()]

    @staticmethod
    def reads(tree):
        """변수 이름 문자열을 환경에서 읽는 식: .get(…)·.getenv(…)·.pop(…)의 첫 인자, `_flag(…, 이름)` 의 인자, `환경[이름]`."""
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                if name in ("get", "getenv", "pop", "_flag", "setdefault", "is_truthy", "truthy"):
                    found += [arg for arg in node.args if isinstance(arg, ast.Constant) and arg.value == "PIPELINE_PAUSE"]
            elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and node.slice.value == "PIPELINE_PAUSE":
                found.append(node.slice)
        return found

    def test_nobody_outside_pause_py_reads_the_variable_by_name(self):
        owners = {}
        for path in self.sources():
            hits = self.reads(ast.parse(path.read_text(encoding="utf-8")))
            if hits:
                owners[path.relative_to(ROOT).as_posix()] = len(hits)
        self.assertEqual(owners, {})
        self.assertTrue(self.reads(ast.parse("x = os.environ.get('PIPELINE_PAUSE', '')")))        # 탐지기 자체가 살아 있다
        self.assertTrue(self.reads(ast.parse("x = environ['PIPELINE_PAUSE']")))
        self.assertTrue(self.reads(ast.parse("x = _flag(environ, 'PIPELINE_PAUSE')")))

    def test_the_edit_runner_keeps_its_old_public_names_pointing_at_the_shared_set(self):
        self.assertEqual(runner.PAUSE_VALUES, pause.ON_VALUES)
        for value in sorted(pause.ON_VALUES):
            self.assertTrue(runner.pause_on({"PIPELINE_PAUSE": value}))
        self.assertTrue(runner.pause_on({"PIPELINE_PAUSE": "ture"}))
        self.assertFalse(runner.pause_on({"PIPELINE_PAUSE": None}))
        self.assertFalse(runner.pause_on({}))

    def test_the_guardrail_row_and_the_publish_paths_item_describe_the_rule(self):
        guard = (ROOT / "docs" / "SECURITY_GUARDRAILS.md").read_text(encoding="utf-8")
        row = next(line for line in guard.splitlines() if line.startswith("| G-O9 |"))
        for needle in ("pipeline/pause.py", "`1`·`true`·`yes`·`on`", "`0`·`false`·`no`·`off`", "정지로 읽고", "::error::", "tests/test_pause_fail_closed.py", "운영자만"):
            self.assertIn(needle, row, needle)
        paths = (ROOT / "docs" / "PUBLISH_PATHS.md").read_text(encoding="utf-8")
        item = next(line for line in paths.splitlines() if line.startswith("23. **발행 정지 변수의 값은 알 수 없는 값을 정지로 읽는다**"))
        for needle in ("pipeline/pause.py", "D-412", "BP-S1-3", "`disabled`", "정지로 읽힌다"):
            self.assertIn(needle, item, needle)
        for text in (row, item):
            self.assertNotIn(chr(126), text)                                     # 문서 규칙: ASCII 물결표 금지
            self.assertIsNone(re.search(r"https?://", text))                     # 문서 규칙: 링크 금지

    def test_pause_py_imports_nothing(self):
        tree = ast.parse((ROOT / "pipeline" / "pause.py").read_text(encoding="utf-8"))
        self.assertEqual([node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))], [])


if __name__ == "__main__":
    unittest.main()
