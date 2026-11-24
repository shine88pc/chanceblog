"""닫힌 쪽(fail closed)으로 쓴 워크플로 줄 둘을 못박는 시험(독립 감사 BP-S2 R3, 결함 D-468). 네트워크 없이 돌고 PyYAML 이 없어도 돈다(워크플로 글을 들여쓰기로 직접 읽는다 — PyYAML 이 있으면 같은 값을 읽는지 대조도 한다).

① `watchdog.yml` 의 감시 단계 env 는 `PIPELINE_PAUSE: ${{ vars.PIPELINE_PAUSE }}` 로 정지 변수를 그대로 넘긴다. 이 줄이 사라지면 워치독은 '일부러 멈춘 동안의 침묵'과 정지 변수 값이 오타일 때의 알림(PAUSE_UNKNOWN, D-432)을
둘 다 못 한다 — 같은 줄을 다른 워크플로(chanceblog.yml·blogger.yml·naver.yml·tistory.yml·chance-fix-images.yml·issue-edit.yml·chance-shadow.yml·ops-inbox.yml)는 시험이 못박았는데 워치독만 없었다(감사의 변이 W6·W6b 생존).
② `chanceblog.yml`·`chance-shadow.yml` 의 '콘텐츠 출처 확인' 단계(id source)는 레지스트리를 읽지 못하면 단계가 실패해 글을 만들기 전에 멈춘다(`set -euo pipefail` 이 맨 앞이고 `||` 가 없다 — 단계 머리 주석의 약속).
`|| echo feed` 처럼 실패를 덮으면 읽기가 실패해도 단계는 초록으로 `feed` 를 내고 Gemini·Unsplash 키가 생성기 단계로 넘어간다(감사의 변이 V3·V3b 생존). 옆의 '발행 흐름 확인' 단계는
test_publish_paths.FlowStepCannotBeBypassedTest 가 같은 길을 막고 있다 — 이 시험은 그 모양을 따라 쓴다.

워크플로 변이는 이 시험 안에서도 한다: 같은 검사 함수를 줄을 일부러 틀리게 바꾼 글에 적용해 문제가 나오는지 본다(진짜 파일은 고치지 않는다).
"""
import re
import textwrap
import unittest

import _bootstrap

try:
    import yaml
except ImportError:                                     # PyYAML 이 없는 환경에서도 이 시험은 돈다(글을 직접 읽는다)
    yaml = None

ROOT = _bootstrap.ROOT
WORKFLOWS = ROOT / ".github" / "workflows"
PAUSE_EXPRESSION = "${{ vars.PIPELINE_PAUSE }}"
WATCH_COMMAND = "python scripts/watchdog.py"
SOURCE_WORKFLOWS = ("chanceblog.yml", "chance-shadow.yml")
SOURCE_COMMAND = "python -m pipeline.source_policy content-source"
KEY_RX = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s+(.*?))?\s*$")
ESCAPES = ("set +e", "|| true", "||true", "|| :", "|| exit 0")


def read(name):
    return (WORKFLOWS / name).read_text(encoding="utf-8").replace("\r\n", "\n")


# ----------------------------------------------------------------------------
# 워크플로 글 읽기(들여쓰기만 본다): 단계 묶음 → 단계의 키·id·run 줄·env
# ----------------------------------------------------------------------------
def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def step_blocks(text):
    """`steps:` 아래 `- ` 로 시작하는 단계마다 줄 묶음을 낸다(주석·빈 줄은 앞뒤에서 건너뛴다)."""
    lines = text.split("\n")
    blocks, index = [], 0
    while index < len(lines):
        head = re.match(r"^(\s*)steps:\s*$", lines[index])
        index += 1
        if not head:
            continue
        base, step_indent = len(head.group(1)), None
        while index < len(lines):
            line = lines[index]
            if not line.strip() or line.lstrip().startswith("#"):
                index += 1
                continue
            if indent_of(line) <= base:
                break
            if step_indent is None:
                step_indent = indent_of(line)
            if indent_of(line) == step_indent and line.lstrip().startswith("- "):
                block = [line]
                index += 1
                while index < len(lines):
                    nxt = lines[index]
                    if nxt.strip() and (indent_of(nxt) < step_indent or indent_of(nxt) <= base or (indent_of(nxt) == step_indent and nxt.lstrip().startswith("- "))):
                        break
                    block.append(nxt)
                    index += 1
                blocks.append(block)
            else:
                index += 1
    return blocks


def plain_value(raw):
    """키 한 줄의 값: 앞뒤 공백·줄 끝 주석(` #…`, 따옴표 밖)을 걷고 짝이 맞는 따옴표를 벗긴다."""
    value = (raw or "").strip()
    if value[:1] in ("'", '"'):
        end = value.find(value[0], 1)
        while value[0] == "'" and end != -1 and value[end + 1:end + 2] == "'":                 # 홑따옴표 안의 '' 는 따옴표 하나
            end = value.find("'", end + 2)
        if end != -1:
            inner = value[1:end]
            return inner.replace("''", "'") if value[0] == "'" else inner
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def parse_step(block):
    """단계 하나 → {"keys": [최상위 키 순서], "id": …, "name": …, "env": {이름: 값}, "run": [줄…]}. 블록 글(`|`·`>`)의 줄은 그대로(쉘 주석 포함) 남긴다."""
    lead = indent_of(block[0])
    lines = [block[0][:lead] + "  " + block[0][lead + 2:]] + block[1:]            # `- ` 를 빈칸 둘로 — 첫 키도 다음 키들과 같은 들여쓰기가 된다
    keys_indent = lead + 2
    step = {"keys": [], "id": None, "name": None, "env": {}, "run": []}
    index = 0
    while index < len(lines):
        line = lines[index]
        found = KEY_RX.match(line.strip()) if line.strip() and indent_of(line) == keys_indent and not line.lstrip().startswith("#") else None
        if not found:
            index += 1
            continue
        key, raw = found.group(1), found.group(2) or ""
        children, end = [], index + 1
        while end < len(lines) and (not lines[end].strip() or indent_of(lines[end]) > keys_indent):
            children.append(lines[end])
            end += 1
        step["keys"].append(key)
        if key in ("id", "name"):
            step[key] = plain_value(raw)
        elif key == "run":
            if raw.strip()[:1] in ("|", ">"):
                step["run"] = textwrap.dedent("\n".join(children)).split("\n")
            else:
                step["run"] = [plain_value(raw)]
        elif key == "env":
            for child in children:
                item = KEY_RX.match(child.strip()) if child.strip() and not child.lstrip().startswith("#") else None
                if item:
                    step["env"][item.group(1)] = plain_value(item.group(2))
        index = end
    return step


def steps_of(text):
    return [parse_step(block) for block in step_blocks(text)]


def code_lines(step):
    """단계 run 의 명령 줄(빈 줄·쉘 주석 줄은 뺀다)."""
    return [line.strip() for line in step["run"] if line.strip() and not line.strip().startswith("#")]


# ----------------------------------------------------------------------------
# 검사: 문제가 있으면 문장 목록, 없으면 빈 목록
# ----------------------------------------------------------------------------
def watchdog_problems(text):
    """감시 단계(`python scripts/watchdog.py` 를 도는 단계)가 정지 변수를 `${{ vars.PIPELINE_PAUSE }}` 그대로 env 로 넘기는가."""
    watch = [step for step in steps_of(text) if code_lines(step) == [WATCH_COMMAND]]
    if len(watch) != 1:
        return [f"감시 단계가 {len(watch)}개다(하나여야 한다)"]
    value = watch[0]["env"].get("PIPELINE_PAUSE")
    return [] if value == PAUSE_EXPRESSION else [f"감시 단계 env.PIPELINE_PAUSE 가 {value!r} 이다({PAUSE_EXPRESSION!r} 여야 한다)"]


def source_problems(text):
    """'콘텐츠 출처 확인' 단계(id source)가 실패를 덮지 않는가: 맨 앞 명령이 `set -euo pipefail`·`||` 없음·읽기 명령이 `value=$(…)` 그대로·건너뛰기·계속 진행·다른 셸 없음."""
    found = [step for step in steps_of(text) if step["id"] == "source"]
    if len(found) != 1:
        return [f"id 가 source 인 단계가 {len(found)}개다(하나여야 한다)"]
    step, problems = found[0], []
    code = code_lines(step)
    body = "\n".join(code)
    if not code or code[0] != "set -euo pipefail":
        problems.append("맨 앞 명령이 `set -euo pipefail` 이 아니다")
    if "||" in body:
        problems.append("`||` 로 실패를 덮는다")
    for escape in ESCAPES:
        if escape in body:
            problems.append(f"`{escape}` 로 실패가 지나간다")
    if f"value=$({SOURCE_COMMAND})" not in code:
        problems.append(f"읽기 명령이 `value=$({SOURCE_COMMAND})` 그대로가 아니다")
    for key in ("if", "continue-on-error", "shell", "working-directory"):
        if key in step["keys"]:
            problems.append(f"단계에 `{key}` 가 있다(실패를 숨기거나 단계를 건너뛰거나 다른 셸로 돌릴 수 있다)")
    return problems


def mutated(text, old, new):
    assert text.count(old) == 1, (text.count(old), old[:60])
    return text.replace(old, new)


# ----------------------------------------------------------------------------
# ① 워치독이 정지 변수를 그대로 받는다
# ----------------------------------------------------------------------------
class WatchdogPauseVariableTest(unittest.TestCase):
    LINE = "          PIPELINE_PAUSE: " + PAUSE_EXPRESSION + "\n"

    def test_the_real_watch_step_passes_the_pause_variable_unchanged(self):
        self.assertEqual(watchdog_problems(read("watchdog.yml")), [])
        steps = [step for step in steps_of(read("watchdog.yml")) if code_lines(step) == [WATCH_COMMAND]]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["name"], "감시")
        self.assertEqual(steps[0]["env"]["PIPELINE_PAUSE"], "${{ vars.PIPELINE_PAUSE }}")           # 글자 그대로 한 번 더(상수와 따로)

    def test_only_the_watchdog_workflow_runs_the_watchdog_script(self):
        """같은 스크립트를 부르는 새 워크플로·단계가 생기면 이 시험이 빨개져 같은 줄을 함께 못박게 한다."""
        users = []
        for path in sorted(WORKFLOWS.glob("*.yml")):
            text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
            if any(WATCH_COMMAND in code_lines(step) for step in steps_of(text)):
                users.append(path.name)
        self.assertEqual(users, ["watchdog.yml"])

    def test_each_way_of_losing_the_variable_is_found(self):
        text = read("watchdog.yml")
        self.assertIn(self.LINE, text)                                  # 전제: 줄이 이 모양으로 있다(아래 변이의 옛 글)
        variants = {
            "line deleted (the comment above it stays)": mutated(text, self.LINE, ""),
            "a secret instead of a variable": mutated(text, self.LINE, "          PIPELINE_PAUSE: ${{ secrets.PIPELINE_PAUSE }}\n"),
            "empty text": mutated(text, self.LINE, "          PIPELINE_PAUSE: ''\n"),
            "a fixed off value": mutated(text, self.LINE, "          PIPELINE_PAUSE: 'false'\n"),
            "another variable": mutated(text, self.LINE, "          PIPELINE_PAUSE: ${{ vars.PIPELINE_PAUSED }}\n"),
            "the name has a typo": mutated(text, self.LINE, "          PIPELINE_PAUSED: ${{ vars.PIPELINE_PAUSE }}\n"),
            "the expression has extra text": mutated(text, self.LINE, "          PIPELINE_PAUSE: ${{ vars.PIPELINE_PAUSE }}x\n"),
            "only a comment is left": mutated(text, self.LINE, "          # PIPELINE_PAUSE: ${{ vars.PIPELINE_PAUSE }}\n"),
        }
        for label, changed in variants.items():
            with self.subTest(label):
                self.assertNotEqual(watchdog_problems(changed), [], label)

    def test_a_second_watch_step_or_a_renamed_command_is_found(self):
        text = read("watchdog.yml")
        for label, changed in {"command changed": mutated(text, "run: python scripts/watchdog.py", "run: python scripts/watchdog.py --quiet"),
                               "step run twice": text + "      - name: 또\n        run: python scripts/watchdog.py\n"}.items():
            with self.subTest(label):
                self.assertNotEqual(watchdog_problems(changed), [], label)


# ----------------------------------------------------------------------------
# ② 콘텐츠 출처 확인 단계가 읽기 실패를 덮지 않는다
# ----------------------------------------------------------------------------
class ContentSourceStepFailsClosedTest(unittest.TestCase):
    COMMAND = "          value=$(" + SOURCE_COMMAND + ")\n"
    HEAD = "        id: source\n        run: |\n          set -euo pipefail\n"

    def test_the_real_step_in_both_workflows_fails_when_the_registry_cannot_be_read(self):
        for name in SOURCE_WORKFLOWS:
            with self.subTest(name):
                self.assertEqual(source_problems(read(name)), [])
                step = next(item for item in steps_of(read(name)) if item["id"] == "source")
                self.assertEqual(step["name"], "콘텐츠 출처 확인 (레지스트리 content_source)")
                self.assertEqual(code_lines(step)[:2], ["set -euo pipefail", "value=$(python -m pipeline.source_policy content-source)"])
                self.assertNotIn("||", "\n".join(code_lines(step)))

    def test_every_workflow_that_reads_the_content_source_is_checked(self):
        """같은 읽기 명령을 쓰는 새 워크플로가 생기면 이 시험이 빨개져 같은 단계를 함께 못박게 한다(복사본이 `||` 를 달고 오는 것을 막는다)."""
        users = []
        for path in sorted(WORKFLOWS.glob("*.yml")):
            text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
            if any(SOURCE_COMMAND in line for step in steps_of(text) for line in code_lines(step)):
                users.append(path.name)
        self.assertEqual(users, sorted(SOURCE_WORKFLOWS))

    def test_each_way_of_covering_a_read_failure_is_found_in_both_workflows(self):
        for name in SOURCE_WORKFLOWS:
            text = read(name)
            self.assertEqual(text.count(self.COMMAND), 1, name)
            self.assertEqual(text.count(self.HEAD), 1, name)
            variants = {
                "echo feed after ||": mutated(text, self.COMMAND, "          value=$(" + SOURCE_COMMAND + " || echo feed)\n"),
                "|| true": mutated(text, self.COMMAND, "          value=$(" + SOURCE_COMMAND + ") || true\n"),
                "|| fallback on its own line": mutated(text, self.COMMAND, self.COMMAND + '          [ -n "${value}" ] || value=feed\n'),
                "set -e removed": mutated(text, self.HEAD, "        id: source\n        run: |\n"),
                "set -e weakened": mutated(text, self.HEAD, "        id: source\n        run: |\n          set -uo pipefail\n"),
                "set +e after it": mutated(text, self.COMMAND, "          set +e\n" + self.COMMAND),
                "the command is not a plain assignment": mutated(text, self.COMMAND, "          python -m pipeline.source_policy content-source > /dev/null\n          value=feed\n"),
                "continue-on-error": mutated(text, "        id: source\n", "        id: source\n        continue-on-error: true\n"),
                "a skip condition": mutated(text, "        id: source\n", "        id: source\n        if: ${{ always() }}\n"),
                "another shell": mutated(text, "        id: source\n", "        id: source\n        shell: sh\n"),
                "no step with the id": mutated(text, "        id: source\n", "        id: sources\n"),
            }
            for label, changed in variants.items():
                with self.subTest(name=name, variant=label):
                    self.assertNotEqual(source_problems(changed), [], label)

    def test_a_comment_that_mentions_the_dangerous_words_does_not_hide_or_cause_a_problem(self):
        """쉘 주석 줄의 `||`·`set +e` 는 명령이 아니다 — 주석 때문에 빨개지지 않고, 주석이 진짜 줄의 빈자리를 메우지도 못한다."""
        text = read("chanceblog.yml")
        with_comment = mutated(text, self.COMMAND, "          # 실패를 덮는 || echo feed 나 set +e 는 쓰지 않는다\n" + self.COMMAND)
        self.assertEqual(source_problems(with_comment), [])
        only_comment = mutated(text, self.HEAD, "        id: source\n        run: |\n          # set -euo pipefail\n")
        self.assertNotEqual(source_problems(only_comment), [])


# ----------------------------------------------------------------------------
# 글을 직접 읽는 이 시험의 읽기가 PyYAML 과 같은 값을 읽는다(PyYAML 이 있을 때)
# ----------------------------------------------------------------------------
@unittest.skipIf(yaml is None, "PyYAML 이 없다 — 직접 읽기만 쓴다")
class TextReaderAgreesWithYamlTest(unittest.TestCase):
    def test_the_three_workflows_read_the_same_way(self):
        for name in ("watchdog.yml", *SOURCE_WORKFLOWS):
            data = yaml.safe_load(read(name))
            expected = [step for job in data["jobs"].values() for step in job["steps"]]
            mine = steps_of(read(name))
            self.assertEqual(len(mine), len(expected), name)
            for ours, theirs in zip(mine, expected):
                with self.subTest(name=name, step=theirs.get("name") or theirs.get("uses")):
                    self.assertEqual(ours["id"], theirs.get("id"))
                    self.assertEqual(ours["name"], theirs.get("name"))
                    self.assertEqual({key: str(value) for key, value in (theirs.get("env") or {}).items()}, ours["env"])
                    if "run" in theirs:
                        self.assertEqual("\n".join(ours["run"]).strip(), str(theirs["run"]).strip())
                    else:
                        self.assertEqual(ours["run"], [])
                    self.assertEqual(ours["keys"], list(theirs.keys()))


class RegisterRowTest(unittest.TestCase):
    """결함 행 D-468 이 한 번만 있고 여섯 칸이며 시험 파일·변이를 말한다(문서와 시험이 어긋나지 않게)."""

    def test_the_defect_row_exists_once_with_six_cells_and_names_this_test_file(self):
        text = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8").replace("\r\n", "\n")
        rows = [line for line in text.split("\n") if line.startswith("| **D-468** |")]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.count("|"), 7)
        for needle in ("tests/test_fail_closed_workflow_lines.py", "**해결**", "감사 BP-S2 R3", "`watchdog.yml`", "`chanceblog.yml`", "`chance-shadow.yml`", "`set -euo pipefail`", "PAUSE_UNKNOWN",
                       "검증기 쪽(T3)", "변이 13개"):
            self.assertIn(needle, row, needle)
        self.assertNotIn(chr(126), row)
        self.assertNotIn("{" + "{", row)


if __name__ == "__main__":
    unittest.main()
