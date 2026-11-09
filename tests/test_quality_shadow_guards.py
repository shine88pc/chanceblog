"""그림자 모드(품질 측정) 가드 시험 — 측정 도구가 게시·초안 생성 흐름에 끼어들지 못하게 소스 규칙으로 못박는다.

운영자 결정(2026-11-09): 게시 결과에 영향을 주지 않는 그림자 모드부터 진행하되 실제 게시·초안 생성 흐름에는 연결하지 않는다.
여기서 지키는 것: ① 연결 금지(유일한 예외: 수동 그림자 워크플로 `chance-shadow.yml` 한 파일의 별도 프로세스 호출 — 조건은 `shadow_workflow_problems`) ② 네트워크 0 ③ 쓰기는 `--out` 하나
④ 금지 구성요소·파이썬 3.10 문법 ⑤ 분류표·건강 프로필·문서와 코드의 일치 ⑥ 실제 글 스모크.
측정 정의 자체의 시험은 test_quality_shadow.py. 설명: docs/QUALITY_SHADOW.md
"""
import ast
import contextlib
import datetime
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import generator as g
from pipeline import gates, quality_shadow as q

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "pipeline" / "quality_shadow.py"
MODULE_REL = "pipeline/quality_shadow.py"
AS_OF = datetime.date(2026, 11, 9)
TEXT_SUFFIXES = {".py", ".yml", ".yaml", ".json", ".sh", ".md", ".txt", ".toml", ".cfg"}
# 비밀·계정 모양(런타임에 조각을 이어 만든다 — 소스에 그런 리터럴을 두지 않는다, ENGINEERING_GUIDE §5-4)
SECRET_AND_IDENTIFIER_PATTERNS = ("AI" + "za[0-9A-Za-z_-]{20,}", "gh" + "p_[0-9A-Za-z]{20,}", "ca-" + r"pub-\d+", "blog" + r"spot\.com", "UNSPLASH" + "_ACCESS_KEY")


def scan_targets(root):
    """게시·초안 생성 흐름을 이루는 파일: 생성기 둘, pipeline/ 전체(실행기·레지스트리 포함, 이 모듈 자신은 제외), scripts/, `.github/` 전체(워크플로·액션·이슈 양식·지침 …)."""
    targets = [root / name for name in ("generator.py", "blogger_generator.py") if (root / name).is_file()]
    for folder in ("pipeline", "scripts", ".github"):
        base = root / folder
        if base.is_dir():
            targets += sorted(path for path in base.rglob("*") if path.is_file() and (path.suffix in TEXT_SUFFIXES or path.suffix == ""))
    return [path for path in targets if path.relative_to(root).as_posix() != MODULE_REL]


def find_connections(root):
    """`quality_shadow` 라는 낱말을 담은 대상 파일의 상대 경로 목록(import·`-m` 실행·워크플로 단계·이름 문자열 모두 걸린다).
    유일한 예외는 `SHADOW_WORKFLOW_REL` 한 파일이고, 그 파일이 `shadow_workflow_problems` 의 조건을 모두 지킬 때만 목록에서 빠진다."""
    found = []
    for path in scan_targets(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if "quality_shadow" not in text:
            continue
        if rel == SHADOW_WORKFLOW_REL and not shadow_workflow_problems(text):
            continue                                                      # 유일한 예외 — 조건을 모두 지킨 경우만
        found.append(rel)
    return found


# --- 유일한 예외: 수동 그림자 워크플로의 별도 프로세스 호출 ---------------------------------------------------------------------------
# 병합 계획: 그림자 실행 뒤에 측정 도구를 따로 띄우는 수동 전용 워크플로 한 파일만, 모듈을 불러오지 않고 별도 프로세스(`python -m pipeline.quality_shadow …` 또는
# `python pipeline/quality_shadow.py …`)로 부를 때에 한해 이 도구의 이름이 나와도 '연결'로 읽지 않는다. 다른 모든 파일(다른 워크플로·생성기·pipeline/·scripts/ …)은 그대로 금지다.
# 예외 파일이 저장소에 없으면 예외 검사는 건너뛴다(검사할 대상이 없다). 있는데 조건을 하나라도 어기면 예외가 아니라 연결로 보고된다.
# 이 규칙은 사고 방지용 경보선이다 — 줄 단위 글자 규칙이라 쉘을 해석하지는 않으므로, 모르는 모양은 허용하지 않고 위반으로 읽는다.
SHADOW_WORKFLOW_REL = ".github/workflows/chance-shadow.yml"
_PYTHON = r"python(?:3(?:\.\d+)?)?(?:[ \t]+(?:-[BuI]|-X[ \t]+\w+))*"
SEPARATE_PROCESS_CALL_RE = re.compile(r"\b" + _PYTHON + r"[ \t]+(?:-m[ \t]+pipeline\.quality_shadow(?![\w.])|(?:\./)?pipeline/quality_shadow\.py(?![\w./-]))")
FILE_EXISTS_CHECK_RE = re.compile(r"""(?:\[\[?|\btest)[ \t]+(?:![ \t]+)?-[fe][ \t]+["']?(?:\./)?pipeline/quality_shadow\.py["']?(?:[ \t]+\]\]?)?""")
ECHO_ONLY_LINE_RE = re.compile(r"""^[ \t]*echo[ \t]+(?:-[neE]+[ \t]+)?(?:"[^"$`\\]*"|'[^']*')[ \t]*(?:>>?[ \t]*[^\s;&|<>]+)?[ \t]*$""")


def logical_lines(text):
    """(시작 줄 번호, 줄) 목록 — 줄 끝 백슬래시로 이어진 쉘 줄은 한 줄로 합친다(주석 줄은 이어지지 않는다)."""
    lines, buffer, start = [], "", 0
    for number, raw in enumerate(text.splitlines(), 1):
        if not buffer:
            start = number
        if raw.endswith("\\") and (buffer or not raw.lstrip().startswith("#")):
            buffer += raw[:-1] + " "
            continue
        lines.append((start, buffer + raw))
        buffer = ""
    if buffer:
        lines.append((start, buffer))
    return lines


def workflow_triggers(text):
    """워크플로 YAML 최상위 `on:` 의 트리거 이름 집합 — `on: x`·`on: [x, y]`·`on:` 아래 들여쓴 키·`on:` 아래 `- x` 목록을 읽는다. 읽지 못하면 None."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        head = re.match(r"""^(?:on|"on"|'on')[ \t]*:[ \t]*(.*?)[ \t]*(?:#.*)?$""", line)
        if not head:
            continue
        inline = head.group(1)
        if inline.startswith("["):
            return {item.strip().strip("\"'") for item in inline.strip("[]").split(",") if item.strip()}
        if inline.startswith("{"):
            return None
        if inline:
            return {inline.strip("\"'")}
        names, indent = set(), None
        for follow in lines[index + 1:]:
            if not follow.strip() or follow.lstrip().startswith("#"):
                continue
            current = len(follow) - len(follow.lstrip(" "))
            if current == 0:
                break
            indent = current if indent is None else indent
            if current == indent:
                item = re.match(r"""[ ]*(?:-[ ]+)?["']?([A-Za-z_][\w-]*)["']?[ ]*:?""", follow)
                if item:
                    names.add(item.group(1))
        return names
    return None


def shadow_workflow_problems(text):
    """예외 워크플로 본문이 예외의 조건을 어기는 곳의 (줄 번호, 이유) 목록 — 비어 있어야 `find_connections` 가 그 파일의 언급을 연결로 읽지 않는다.
    이름이 나오는 줄은 ① 주석 줄 ② 측정 도구 파일 존재 확인(`[ -f pipeline/quality_shadow.py ]`) ③ `echo "…"` 한 줄 안내 문구(명령 치환 없음)
    ④ `python -m pipeline.quality_shadow …`·`python pipeline/quality_shadow.py …` 별도 프로세스 호출 가운데 하나여야 하고(한 줄에 이름이 둘이면 둘 다),
    그 밖의 모양(불러오기·`python -c`·heredoc·다른 스크립트에 경로 넘기기 …)은 위반이다. 이름을 언급해서 예외를 쓰는 파일은 트리거도 수동 실행 하나뿐이어야 한다."""
    if "quality_shadow" not in text:
        return []                                                         # 이름을 언급하지 않으면 예외를 쓰는 것이 아니다
    problems = []
    for number, line in logical_lines(text):
        if "quality_shadow" not in line or line.lstrip().startswith("#"):
            continue
        allowed = [match.span() for pattern in (SEPARATE_PROCESS_CALL_RE, FILE_EXISTS_CHECK_RE) for match in pattern.finditer(line)]
        if ECHO_ONLY_LINE_RE.match(line):
            allowed.append((0, len(line)))
        if any(not any(start <= hit.start() and hit.end() <= end for start, end in allowed) for hit in re.finditer("quality_shadow", line)):
            problems.append((number, "측정 도구 이름이 별도 프로세스 호출·주석·파일 존재 확인·안내 문구 밖에서 나온다(불러오기·python -c·heredoc·다른 스크립트에 경로 넘기기 등)"))
    if workflow_triggers(text) != {"workflow_dispatch"}:
        problems.append((0, "트리거가 수동 실행(workflow_dispatch) 하나뿐이 아니다"))
    return problems


def shadow_workflow_problems_in(root):
    """저장소 루트에 예외 파일이 있으면 그 조건을 검사하고, 없으면 건너뛴다(빈 목록)."""
    path = root / SHADOW_WORKFLOW_REL
    return shadow_workflow_problems(path.read_text(encoding="utf-8", errors="replace")) if path.is_file() else []


# --- 이름을 글자 그대로 쓰지 않고 조립해서 연결하는 모양(독립 검증 P9) ---------------------------------------------------------------
# 글자 검색(`quality_shadow`)은 `'pipeline.quality_' + 'shadow'`·동적 import 를 못 본다. 파이썬 대상은 AST 로 본다: ① 문자열 상수가 이어 붙고 접혀서
# `quality_shadow` 가 되는 모양 ② 동적 import·코드 실행 호출(`__import__`·`import_module`·`run_module`·`run_path`·`eval`·`exec`). 저장소의 게시·초안 흐름에는
# 이런 호출이 하나도 없다(notify.py 의 `importlib.util.spec_from_file_location` 은 파일 경로로 읽는 것이라 대상이 아니다). 같은 이름 접두어를 쓰는 다른 모듈
# (`quality_gate` 등)을 막지 않으려고 `quality_` 조각 전체를 금지하지 않는다. 한계: `chr()` 로 글자를 만드는 식의 의도적 은폐는 못 잡는다 — 사고 방지용 경보선이다.
DYNAMIC_CALL_NAMES = frozenset({"__import__", "import_module", "run_module", "run_path", "eval", "exec"})
DYNAMIC_TEXT_RE = re.compile(r"__import__|import_module|\brunpy\b|\brun_module\b|\brun_path\b")


def call_name(node):
    return node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")


def folded_string(node):
    """AST 식이 문자열 상수로 접히면 그 문자열, 아니면 None — `'a' + 'b'`·`'%s' % 'x'`·상수만 든 f-문자열·`'_'.join(['a', 'b'])`·`'{}x'.format('a')` 까지."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = folded_string(node.left), folded_string(node.right)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        template = folded_string(node.left)
        values = [folded_string(item) for item in (node.right.elts if isinstance(node.right, ast.Tuple) else [node.right])]
        if template is None or any(value is None for value in values):
            return None
        try:
            return template % tuple(values)
        except (TypeError, ValueError):
            return None
    if isinstance(node, ast.JoinedStr):
        pieces = [folded_string(item.value) if isinstance(item, ast.FormattedValue) else folded_string(item) for item in node.values]
        return None if any(piece is None for piece in pieces) else "".join(pieces)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and not node.keywords:
        base = folded_string(node.func.value)
        if base is None:
            return None
        if node.func.attr == "join" and len(node.args) == 1 and isinstance(node.args[0], (ast.List, ast.Tuple)):
            pieces = [folded_string(item) for item in node.args[0].elts]
            return None if any(piece is None for piece in pieces) else base.join(pieces)
        if node.func.attr == "format":
            pieces = [folded_string(item) for item in node.args]
            try:
                return None if any(piece is None for piece in pieces) else base.format(*pieces)
            except (IndexError, KeyError, ValueError):
                return None
    return None


def assembled_connection_problems(source):
    """파이썬 소스 하나에서 '이름을 조립해 연결하는' 모양의 (줄 번호, 이유) 목록. 파싱이 안 되면(다른 파이썬 버전의 문법) 글자 규칙으로 대신 본다."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [(0, "소스를 파싱하지 못했고 글자 규칙에 걸렸다")] if re.search(r"quality_shadow|" + DYNAMIC_TEXT_RE.pattern + r"|\beval\s*\(|\bexec\s*\(", source) else []
    problems = set()
    for node in ast.walk(tree):
        value = folded_string(node)
        if value is not None and "quality_shadow" in value:
            problems.add((node.lineno, "문자열 상수를 이어 붙여 quality_shadow 를 만든다"))
        if isinstance(node, ast.Call) and call_name(node) in DYNAMIC_CALL_NAMES:
            problems.add((node.lineno, f"동적 import·코드 실행 호출({call_name(node)})"))
    return sorted(problems)


def find_assembled_connections(root):
    """대상 파일 가운데 조립한 연결 의심이 있는 곳의 목록(`경로:줄 이유`). 파이썬은 AST, 그 밖의 텍스트(워크플로 등)는 동적 import 낱말만 본다."""
    found = []
    for path in scan_targets(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".py":
            found += [f"{rel}:{line} {reason}" for line, reason in assembled_connection_problems(text)]
        elif DYNAMIC_TEXT_RE.search(text):
            found.append(f"{rel}:0 동적 import 낱말")
    return found


class NotConnectedTest(unittest.TestCase):
    def test_nothing_in_the_publishing_or_draft_flow_mentions_the_module(self):
        found = find_connections(ROOT)
        detail = f" — 유일한 예외 파일({SHADOW_WORKFLOW_REL})이 조건을 어겼다: {shadow_workflow_problems_in(ROOT)}" if SHADOW_WORKFLOW_REL in found else ""
        self.assertEqual(found, [], "그림자 모드가 게시·초안 흐름에 연결됐다 — 운영자 결정(연결 금지)과 docs/QUALITY_SHADOW.md 를 먼저 고친다" + detail)

    def test_nothing_in_the_flow_builds_the_name_from_pieces_or_imports_dynamically(self):
        self.assertEqual(find_assembled_connections(ROOT), [], "게시·초안 흐름에 문자열 조립·동적 import 모양이 있다 — 그림자 모드를 몰래 연결하는 것이 아닌지 확인한다")

    def test_the_scan_really_covers_the_generator_the_runner_and_the_workflows(self):
        targets = scan_targets(ROOT)
        scanned = {path.relative_to(ROOT).as_posix() for path in targets}
        for must in ("generator.py", "pipeline/run.py", "pipeline/blogs.json", "pipeline/gates.py", ".github/workflows/guardrails.yml"):
            self.assertIn(must, scanned, must)
        workflows = [path for path in targets if path.relative_to(ROOT).as_posix().startswith(".github/workflows/")]
        self.assertGreater(len(workflows), 5)
        texts = [path.read_text(encoding="utf-8", errors="replace") for path in workflows]
        self.assertTrue(any("generator.py" in text for text in texts), "글 생성 워크플로(generator.py 를 도는 것)가 검사 대상에 없다")
        self.assertTrue(any("pipeline.run" in text for text in texts), "실행기(pipeline.run)를 도는 워크플로가 검사 대상에 없다")
        self.assertNotIn(MODULE_REL, scanned)

    def test_the_scan_covers_the_whole_github_folder_not_only_the_workflows(self):
        """독립 검증 P9: `.github/` 의 워크플로 말고 다른 곳(액션·이슈 양식·지침·위원회 파일)에 연결을 숨겨도 걸린다."""
        scanned = {path.relative_to(ROOT).as_posix() for path in scan_targets(ROOT)}
        github = {name for name in scanned if name.startswith(".github/")}
        on_disk = {path.relative_to(ROOT).as_posix() for path in (ROOT / ".github").rglob("*") if path.is_file() and (path.suffix in TEXT_SUFFIXES or path.suffix == "")}
        self.assertEqual(github, on_disk)
        self.assertTrue(github - {name for name in github if name.startswith(".github/workflows/")}, "워크플로 밖의 .github 파일이 대상에 없다")
        for must in (".github/CODEOWNERS", ".github/editorial/edit-spec.yml", ".github/ISSUE_TEMPLATE/config.yml"):
            self.assertIn(must, scanned, must)

    def test_the_scan_catches_every_way_of_connecting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pipeline").mkdir()
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "actions" / "measure").mkdir(parents=True)
            (root / ".github" / "ISSUE_TEMPLATE").mkdir()
            (root / "scripts").mkdir()
            (root / "generator.py").write_text("from pipeline import quality_shadow\n", encoding="utf-8")
            (root / "pipeline" / "run.py").write_text("import importlib\nimportlib.import_module('pipeline.quality_shadow')\n", encoding="utf-8")
            (root / "pipeline" / "quality_shadow.py").write_text("# 자기 자신은 대상이 아니다\n", encoding="utf-8")
            (root / "pipeline" / "blogs.json").write_text('{"x": "quality_shadow"}', encoding="utf-8")
            (root / ".github" / "workflows" / "a.yml").write_text("steps:\n  - run: python -m pipeline.quality_shadow --posts _posts\n", encoding="utf-8")
            (root / ".github" / "actions" / "measure" / "action.yml").write_text("runs:\n  using: composite\n  steps:\n    - run: python -m pipeline.quality_shadow\n", encoding="utf-8")
            (root / ".github" / "ISSUE_TEMPLATE" / "x.yml").write_text("body: quality_shadow\n", encoding="utf-8")
            (root / ".github" / "CODEOWNERS").write_text("pipeline/quality_shadow.py @someone\n", encoding="utf-8")
            (root / "scripts" / "ok.py").write_text("print('no mention')\n", encoding="utf-8")
            self.assertEqual(sorted(find_connections(root)), [".github/CODEOWNERS", ".github/ISSUE_TEMPLATE/x.yml", ".github/actions/measure/action.yml", ".github/workflows/a.yml",
                                                              "generator.py", "pipeline/blogs.json", "pipeline/run.py"])

    ASSEMBLED = {
        "plus": "import importlib\nmodule = importlib.import_module('pipeline.quality_' + 'shadow')\n",
        "dunder import": "__import__('pipeline.qual' + 'ity_shadow')\n",
        "adjacent literals": "import importlib\nimportlib.import_module('pipeline.' 'quality_' 'shadow')\n",
        "join": "name = '.'.join(['pipeline', 'quality_shadow'])\n",
        "empty join": "name = ''.join(('pipeline.quality_', 'shadow'))\n",
        "percent format": "name = 'pipeline.%s_%s' % ('quality', 'shadow')\n",
        "str format": "name = 'pipeline.{}_{}'.format('quality', 'shadow')\n",
        "f-string of constants": "name = f\"pipeline.{'quality'}_{'shadow'}\"\n",
        "getattr": "import pipeline\ngetattr(pipeline, 'quality_' + 'shadow')\n",
        "dynamic import with a variable": "import importlib\nimportlib.import_module(name)\n",
        "run_module": "import runpy\nrunpy.run_module(name)\n",
        "exec": "exec(code)\n",
        "eval": "eval(code)\n",
    }

    def test_every_string_built_or_dynamic_import_shape_is_caught_in_python_files(self):
        for label, source in self.ASSEMBLED.items():
            with self.subTest(shape=label):
                self.assertTrue(assembled_connection_problems(source), source)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pipeline").mkdir()
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / "generator.py").write_text(self.ASSEMBLED["plus"], encoding="utf-8")
            (root / "pipeline" / "run.py").write_text(self.ASSEMBLED["dunder import"], encoding="utf-8")
            (root / ".github" / "workflows" / "x.yml").write_text("run: python -c \"import importlib; importlib.import_module('pipeline.qual'+'ity_shadow')\"\n", encoding="utf-8")
            found = find_assembled_connections(root)
            self.assertEqual(sorted({item.split(":")[0] for item in found}), [".github/workflows/x.yml", "generator.py", "pipeline/run.py"])
            self.assertEqual(find_connections(root), [])                              # 글자 검색만으로는 셋 다 못 잡는다 — 조립 규칙이 필요한 이유

    def test_normal_code_and_the_neighbouring_gate_module_names_are_not_flagged(self):
        fine = ["import importlib.util\nspec = importlib.util.spec_from_file_location('x', ROOT / 'scripts' / 'verify.py')\nmodule = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\n",
                "from pipeline import quality_gate\nname = 'pipeline.quality_gate'\nprint(name + '_config')\n", "import re\npattern = re.compile('quality_gate|shadow')\n",
                "text = 'quality' + '_gate'\nprint(text, 'shadow')\n", "def evaluate(x):\n    return x\nprint(evaluate(1))\n"]
        for source in fine:
            with self.subTest(source=source[:40]):
                self.assertEqual(assembled_connection_problems(source), [], source)

    def test_a_flow_file_that_cannot_be_parsed_here_falls_back_to_a_text_rule(self):
        self.assertTrue(assembled_connection_problems("def broken(:\n    pass\n# quality_shadow\n"))
        self.assertEqual(assembled_connection_problems("def broken(:\n    pass\n"), [])


# ----------------------------------------------------------------------------
# 유일한 예외 — 수동 그림자 워크플로 한 파일이 측정 도구를 별도 프로세스로 부르는 것
# ----------------------------------------------------------------------------
SHADOW_ON_MANUAL = "on:\n  workflow_dispatch:\n    inputs:\n      count:\n        type: choice\n        default: '3'\n        options:\n          - '1'\n          - '3'\n"
SHADOW_RUN_LINES = (
    "set -euo pipefail",
    "if [ ! -f pipeline/quality_shadow.py ]; then",
    '  echo "::notice::측정 도구(pipeline/quality_shadow.py)가 이 저장소에 아직 없어 측정 단계를 건너뜁니다."',
    "  exit 0",
    "fi",
    'python -m pipeline.quality_shadow --posts "$SHADOW_OUT" --as-of "$as_of" --out "$REPORT_DIR/shadow_report.json"',
    'python -m pipeline.quality_shadow --posts "$SHADOW_OUT" --as-of "$as_of" --out "$REPORT_DIR/shadow_report.md"',
)


def shadow_workflow(on_block=SHADOW_ON_MANUAL, run_lines=SHADOW_RUN_LINES, extra_run_lines=()):
    """수동 그림자 워크플로 시험용 본문 — 잠금(LOCK) 묶음의 chance-shadow.yml 이 측정 도구를 언급하는 모양(맨 위 주석·존재 확인·안내 문구·`python -m` 호출 둘)과 수동 트리거를 그대로 옮겼다."""
    head = ('name: "[Chance] 그림자 실행(수동, 읽기 전용)"\n\n'
            "# 측정 단계는 별도 프로세스다: 측정 도구(pipeline/quality_shadow.py)가 저장소에 있을 때만 돌고 없으면 건너뛴다(생성기는 측정 도구를 불러오지 않는다).\n\n")
    steps = "\npermissions:\n  contents: read\n\njobs:\n  shadow:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v6\n      - name: 그림자 측정 (측정 도구가 있을 때만)\n        run: |\n"
    return head + on_block + steps + "".join(f"          {line}\n" for line in list(run_lines) + list(extra_run_lines))


class ShadowWorkflowExceptionTest(unittest.TestCase):
    """연결 금지의 유일한 예외(병합 계획): `SHADOW_WORKFLOW_REL` 한 파일이, 모듈을 불러오지 않고 별도 프로세스로만 부르며 수동 실행 전용일 때. 그 밖의 모든 언급은 그대로 금지다."""

    def scan(self, files):
        """임시 저장소에 {상대 경로: 내용} 을 쓰고 (연결 목록, 조립·동적 import 의심 목록, 예외 파일 위반 목록) 을 낸다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, content in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(content, encoding="utf-8")
            return find_connections(root), find_assembled_connections(root), shadow_workflow_problems_in(root)

    def test_the_exception_is_one_named_file_and_its_check_is_skipped_where_that_file_does_not_exist(self):
        self.assertEqual(SHADOW_WORKFLOW_REL, ".github/workflows/chance-shadow.yml")
        self.assertEqual(shadow_workflow_problems_in(ROOT), [], "예외 파일이 있다면 별도 프로세스 호출만·수동 트리거 조건을 지켜야 한다")        # 파일이 없는 가지에서는 건너뛰어 통과한다
        self.assertEqual(self.scan({"generator.py": "print('x')\n", "pipeline/run.py": "x = 1\n", ".github/workflows/a.yml": "on: workflow_dispatch\n"}), ([], [], []))
        self.assertEqual(self.scan({}), ([], [], []))

    def test_a_manual_workflow_that_only_calls_the_module_as_a_separate_process_is_not_a_connection(self):
        self.assertEqual(self.scan({SHADOW_WORKFLOW_REL: shadow_workflow()}), ([], [], []))
        calls = {
            "python -m": 'python -m pipeline.quality_shadow --posts "$OUT" --as-of 2026-11-09 --out report.json',
            "python3 -m": 'python3 -m pipeline.quality_shadow --posts "$OUT" --as-of 2026-11-09 --out report.json',
            "python3.10 -m": "python3.10 -m pipeline.quality_shadow --help",
            "interpreter flags": "python -B -X utf8 -m pipeline.quality_shadow --help",
            "script path": 'python pipeline/quality_shadow.py --posts "$OUT" --as-of 2026-11-09 --out report.md',
            "script path with ./": "python ./pipeline/quality_shadow.py --help",
            "after an environment assignment": "PYTHONUTF8=1 python -m pipeline.quality_shadow --help",
            "two calls on one line": "python -m pipeline.quality_shadow --help && python pipeline/quality_shadow.py --help",
            "continued with backslashes": 'python -m \\\n  pipeline.quality_shadow --posts "$OUT" \\\n  --as-of 2026-11-09 --out report.json',
        }
        for label, call in calls.items():
            with self.subTest(call=label):
                self.assertEqual(self.scan({SHADOW_WORKFLOW_REL: shadow_workflow(run_lines=call.split("\n"))}), ([], [], []), call)

    def test_the_four_tolerated_mention_shapes_are_exactly_comment_existence_check_echo_and_separate_process_call(self):
        tolerated = {
            "comment": "# 측정 도구(pipeline/quality_shadow.py)는 별도 프로세스로만 부른다",
            "comment that ends with a backslash": "# pipeline/quality_shadow.py \\",
            "existence check": "[ -f pipeline/quality_shadow.py ] || exit 0",
            "negated existence check": "if [ ! -f pipeline/quality_shadow.py ]; then",
            "double bracket and exists": "if [[ ! -e ./pipeline/quality_shadow.py ]]; then",
            "test command": 'if ! test -f "pipeline/quality_shadow.py"; then',
            "echo notice": 'echo "::notice::측정 도구(pipeline/quality_shadow.py)가 없어 건너뜁니다."',
            "echo with single quotes": "echo '측정 도구 pipeline/quality_shadow.py 없음'",
            "echo into the step summary": 'echo "- 측정 도구: pipeline/quality_shadow.py" >> "$GITHUB_STEP_SUMMARY"',
            "separate process call": "python -m pipeline.quality_shadow --help",
        }
        for label, line in tolerated.items():
            with self.subTest(shape=label):
                self.assertEqual(shadow_workflow_problems(shadow_workflow(extra_run_lines=[line])), [], line)

    def test_the_same_content_anywhere_else_is_still_a_connection(self):
        text = shadow_workflow()
        elsewhere = (".github/workflows/other.yml", ".github/workflows/chance-shadow.yaml", ".github/workflows/Chance-Shadow.yml", ".github/workflows/sub/chance-shadow.yml",
                     ".github/workflows/guardrails.yml", ".github/actions/chance-shadow.yml", ".github/CODEOWNERS", "pipeline/chance-shadow.yml", "pipeline/run.py",
                     "scripts/chance-shadow.yml", "scripts/measure.sh", "generator.py", "blogger_generator.py")
        for rel in elsewhere:
            with self.subTest(file=rel):
                self.assertEqual(self.scan({rel: text})[0], [rel])
        with self.subTest(file="valid exception file next to an unrelated workflow that calls the module"):
            both = self.scan({SHADOW_WORKFLOW_REL: text, ".github/workflows/other.yml": "steps:\n  - run: python -m pipeline.quality_shadow --help\n", "pipeline/run.py": "import pipeline.quality_shadow\n"})
            self.assertEqual(sorted(both[0]), [".github/workflows/other.yml", "pipeline/run.py"])

    def test_the_exception_is_void_when_the_file_loads_the_module_or_hides_a_load_in_any_way(self):
        loads = {
            "python -c import": 'python -c "import pipeline.quality_shadow"',
            "python -c from import": "python -c 'from pipeline import quality_shadow'",
            "heredoc import": "python - <<'PY'\nimport pipeline.quality_shadow\nPY",
            "heredoc from import": "python - <<'PY'\nfrom pipeline import quality_shadow\nPY",
            "valid call and an import on one line": 'python -m pipeline.quality_shadow --help && python -c "import pipeline.quality_shadow"',
            "a comment after the code does not excuse it": 'python -c "import pipeline.quality_shadow"  # python -m pipeline.quality_shadow',
            "echo with command substitution": 'echo "$(python -c \'import pipeline.quality_shadow\')"',
            "echo with backticks": 'echo "`python -c \'import pipeline.quality_shadow\'`"',
            "echo followed by a command": 'echo "x" && python -c "import pipeline.quality_shadow"',
            "existence check with a body": "if [ -f pipeline/quality_shadow.py ]; then python -c 'import pipeline.quality_shadow'; fi",
            "path handed to another script": "python generator.py pipeline/quality_shadow.py",
            "source the file": ". pipeline/quality_shadow.py",
            "print the file": "cat pipeline/quality_shadow.py",
            "a comment line ending with a backslash does not continue": "# note \\\nimport pipeline.quality_shadow",
            "another package with the same module name": "python -m other.quality_shadow --help",
            "a longer module name": "python -m pipeline.quality_shadow_extra --help",
            "a longer file name": "python pipeline/quality_shadow.pyc",
            "environment variable naming the module": "MODULE=pipeline.quality_shadow",
        }
        for label, snippet in loads.items():
            with self.subTest(shape=label):
                text = shadow_workflow(extra_run_lines=snippet.split("\n"))
                self.assertTrue(shadow_workflow_problems(text), snippet)
                self.assertEqual(self.scan({SHADOW_WORKFLOW_REL: text})[0], [SHADOW_WORKFLOW_REL], snippet)

    def test_dynamic_import_words_stay_forbidden_even_inside_the_exception_file(self):
        text = shadow_workflow(extra_run_lines=['python -c "import importlib; importlib.import_module(\'pipeline.quality_\' + \'shadow\')"'])
        found, assembled, problems = self.scan({SHADOW_WORKFLOW_REL: text})
        self.assertEqual((found, problems), ([], []))                              # 글자 규칙만으로는 조립한 이름을 못 본다
        self.assertEqual(assembled, [f"{SHADOW_WORKFLOW_REL}:0 동적 import 낱말"])    # 그래서 동적 import 낱말 규칙이 예외 파일에도 그대로 적용된다

    def test_the_exception_file_must_stay_manual_only(self):
        manual = {"block mapping": SHADOW_ON_MANUAL, "scalar": "on: workflow_dispatch\n", "flow list": "on: [workflow_dispatch]\n", "quoted key": '"on":\n  workflow_dispatch:\n',
                  "comment after the key": "on:  # manual only\n  workflow_dispatch:\n", "block list": "on:\n  - workflow_dispatch\n"}
        for label, block in manual.items():
            with self.subTest(trigger=label):
                self.assertEqual(shadow_workflow_problems(shadow_workflow(on_block=block)), [], block)
        automatic = {"schedule added": SHADOW_ON_MANUAL + "  schedule:\n    - cron: '0 0 * * *'\n", "push added": "on:\n  workflow_dispatch:\n  push:\n    branches: [main]\n",
                     "pull request added": "on:\n  pull_request:\n  workflow_dispatch:\n", "scalar push": "on: push\n", "flow list with push": "on: [workflow_dispatch, push]\n",
                     "flow mapping": "on: {workflow_dispatch: {}, push: {}}\n", "reusable": "on:\n  workflow_call:\n", "block list with schedule": "on:\n  - workflow_dispatch\n  - schedule\n",
                     "empty": "on: []\n", "missing": "name_only: x\n"}
        for label, block in automatic.items():
            with self.subTest(trigger=label):
                text = shadow_workflow(on_block=block)
                self.assertEqual(shadow_workflow_problems(text), [(0, "트리거가 수동 실행(workflow_dispatch) 하나뿐이 아니다")], block)
                self.assertEqual(self.scan({SHADOW_WORKFLOW_REL: text})[0], [SHADOW_WORKFLOW_REL], block)

    def test_a_workflow_that_never_names_the_module_does_not_use_the_exception(self):
        text = "on:\n  schedule:\n    - cron: '0 0 * * *'\njobs:\n  x:\n    steps:\n      - run: echo hi\n"
        self.assertEqual(self.scan({SHADOW_WORKFLOW_REL: text}), ([], [], []))        # 이름을 언급하지 않으니 연결이 아니다 — 트리거 검사는 예외를 쓰는 파일에만 건다

    def test_the_trigger_reader_understands_each_yaml_shape(self):
        shapes = {"on: workflow_dispatch": {"workflow_dispatch"}, "on: 'workflow_dispatch'": {"workflow_dispatch"}, "on: [push, workflow_dispatch]": {"push", "workflow_dispatch"},
                  "on:\n  push:\n    branches: [main]\n  workflow_dispatch:\n    inputs:\n      count:\n        type: choice\n": {"push", "workflow_dispatch"},
                  "on:\n\n  # comment\n  workflow_dispatch:\n": {"workflow_dispatch"}, "on:\n  - push\n  - workflow_dispatch\n": {"push", "workflow_dispatch"},
                  'name: x\n"on": push\n': {"push"}, "on: []\n": set(), "on: {push: {}}\n": None, "name: x\n": None, "online: x\n": None}
        for text, expected in shapes.items():
            with self.subTest(text=text):
                self.assertEqual(workflow_triggers(text), expected)

    def test_a_shell_line_continuation_joins_lines_but_a_comment_never_continues(self):
        self.assertEqual(logical_lines("a \\\n  b\nc\n"), [(1, "a    b"), (3, "c")])
        self.assertEqual(logical_lines("# a \\\nb\n"), [(1, "# a \\"), (2, "b")])
        self.assertEqual(logical_lines("a \\\n"), [(1, "a  ")])


# ----------------------------------------------------------------------------
# 모듈 소스 규칙: 네트워크·쓰기·금지 구성요소
# ----------------------------------------------------------------------------
def module_tree():
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def imported_modules(tree):
    """소스가 불러오는 모듈 이름 집합. `from pipeline import llm` 은 하위 모듈 `pipeline.llm` 으로 적는다(독립 검증 P9: 예전에는 `pipeline` 만 기록해
    `pipeline` 이 허용 목록에 있으면 `llm`·`run`·`notify` 같은 하위 모듈을 불러와도 통과했다). 점으로 시작하는 상대 import 는 `.이름` 으로 적는다(허용하지 않는다)."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = "." * (node.level or 0) + (node.module or "")
            if base == "pipeline" or base.strip(".") == "":
                names.update(base + alias.name if base.endswith(".") or not base else f"{base}.{alias.name}" for alias in node.names)
            else:
                names.add(base)
    return names


def bare_dynamic_calls(tree):
    """동적 import·코드 실행을 하는 호출의 이름 집합: `__import__`·`eval`·`exec`·이름만으로 부르는 `compile`(re.compile 은 아니다)·`import_module`·`run_module`·`run_path`."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = call_name(node)
            if name in DYNAMIC_CALL_NAMES or (isinstance(node.func, ast.Name) and name == "compile"):
                found.add(name)
    return found


# 불러온 뒤 실제로 로드된 모듈에서 찾는 것(표준 라이브러리 내부가 버전마다 끌어올 수 있는 shutil·tempfile 같은 것은 정적 금지 목록에만 둔다)
NETWORK_AND_PROCESS_MODULES = frozenset({"socket", "ssl", "http", "http.client", "urllib.request", "urllib3", "requests", "ftplib", "smtplib", "subprocess", "asyncio",
                                         "multiprocessing", "webbrowser", "xmlrpc", "xmlrpc.client", "telnetlib", "ctypes", "msvcrt", "selectors"})


class ImportDetectorTest(unittest.TestCase):
    """가드 시험의 탐지기가 실제로 잡는지 합성 소스로 확인한다(독립 검증 P9: 가드가 `from pipeline import llm`·문자열 조립 import 를 못 잡았다)."""

    def test_from_pipeline_import_records_the_submodules(self):
        found = imported_modules(ast.parse("from pipeline import console, gates, llm, run as runner, notify\n"))
        self.assertEqual(found, {"pipeline.console", "pipeline.gates", "pipeline.llm", "pipeline.run", "pipeline.notify"})

    def test_plain_dotted_and_relative_imports_are_recorded(self):
        self.assertEqual(imported_modules(ast.parse("import pipeline.llm\nimport socket as s\nfrom urllib.request import urlopen\nfrom urllib.parse import urlsplit\n")),
                         {"pipeline.llm", "socket", "urllib.request", "urllib.parse"})
        self.assertEqual(imported_modules(ast.parse("from . import llm\nfrom .run import main\nfrom .. import other\nfrom pipeline.llm import call\n")),
                         {".llm", ".run", "..other", "pipeline.llm"})

    def test_a_forbidden_submodule_is_outside_the_allowed_list_even_when_the_package_name_is_allowed(self):
        allowed = NoNetworkTest.ALLOWED_IMPORTS
        for source in ("from pipeline import console, gates, llm", "from pipeline import console, gates, notify, run", "import pipeline.run", "from . import console",
                       "from pipeline import registry"):
            with self.subTest(source=source):
                self.assertTrue(imported_modules(ast.parse(source)) - allowed, source)
        self.assertEqual(imported_modules(ast.parse("from pipeline import console, gates")) - allowed, set())

    def test_the_dynamic_call_detector_sees_every_dynamic_shape_and_ignores_re_compile(self):
        for source, expected in (("__import__('x')", {"__import__"}), ("import importlib\nimportlib.import_module('x')", {"import_module"}), ("eval('1')", {"eval"}),
                                 ("exec('x = 1')", {"exec"}), ("compile('x', 'f', 'exec')", {"compile"}), ("import runpy\nrunpy.run_module('x')", {"run_module"}),
                                 ("import re\nre.compile('x')", set()), ("class A:\n    def evaluate(self):\n        return 1\nA().evaluate()", set())):
            with self.subTest(source=source):
                self.assertEqual(bare_dynamic_calls(ast.parse(source)), expected)


class NoNetworkTest(unittest.TestCase):
    ALLOWED_IMPORTS = {"argparse", "datetime", "json", "math", "re", "sys", "collections", "dataclasses", "pathlib", "urllib.parse", "pipeline.console", "pipeline.gates"}

    def test_the_module_imports_only_pure_standard_library_modules_and_the_two_allowed_pipeline_helpers(self):
        self.assertEqual(imported_modules(module_tree()) - self.ALLOWED_IMPORTS, set())

    def test_no_networking_process_or_file_system_helper_modules(self):
        banned = {"socket", "ssl", "http", "http.client", "urllib.request", "urllib", "requests", "ftplib", "smtplib", "subprocess", "os", "shutil", "tempfile",
                  "ctypes", "msvcrt", "asyncio", "multiprocessing", "webbrowser", "xmlrpc", "telnetlib", "importlib", "pipeline.llm", "pipeline.run", "pipeline.notify"}
        self.assertEqual(imported_modules(module_tree()) & banned, set())

    def test_the_module_has_no_dynamic_import_eval_exec_or_compile_calls(self):
        self.assertEqual(bare_dynamic_calls(module_tree()), set())
        names = {node.id for node in ast.walk(module_tree()) if isinstance(node, ast.Name)}
        self.assertEqual(names & {"__import__", "eval", "exec", "importlib", "__builtins__"}, set())

    def test_importing_the_module_in_a_clean_process_loads_no_network_process_or_other_pipeline_modules(self):
        """소스에 import 줄이 없어도 불러온 모듈이 다른 모듈을 끌고 오지 않는지 실제로 확인한다(`pipeline.gates` 가 끌고 오는 것까지)."""
        code = ("import sys; sys.path.insert(0, %r); before = set(sys.modules); import pipeline.quality_shadow; "
                "print(chr(10).join(sorted(set(sys.modules) - before)))" % str(ROOT))
        done = subprocess.run([sys.executable, "-I", "-X", "utf8", "-B", "-c", code], capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))
        self.assertEqual(done.returncode, 0, done.stderr[-300:])
        loaded = set(done.stdout.split())
        self.assertEqual({name for name in loaded if name == "pipeline" or name.startswith("pipeline.")},
                         {"pipeline", "pipeline.console", "pipeline.gates", "pipeline.quality_shadow"})
        self.assertEqual(loaded & NETWORK_AND_PROCESS_MODULES, set())

    def test_analysis_and_the_command_line_make_no_network_calls(self):
        def boom(*args, **kwargs):
            raise AssertionError("네트워크 호출")
        posts = [q.parse_post("---\ntitle: 가\nlang: ko\nsource_url: https://www.nasa.gov/a\n---\n\nNASA는 2026년 10월 1일 [발표](https://www.nasa.gov/a)했다.\n", "2026-11-01-KR-123456.md"),
                 q.parse_post("---\ntitle: a\nlang: en\nsource_url: https://www.nasa.gov/a\n---\n\nNASA announced it on October 1, 2026, see [it](https://www.nasa.gov/a).\n",
                              "2026-11-01-EN-123456.md")]
        with mock.patch("socket.socket.connect", boom), mock.patch("socket.create_connection", boom), mock.patch("socket.getaddrinfo", boom), \
                mock.patch("urllib.request.urlopen", boom), mock.patch("http.client.HTTPConnection.connect", boom):
            report = q.analyze_corpus(posts, AS_OF)
            q.render_json(report)
            q.render_markdown(report)
            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp) / "posts"
                folder.mkdir()
                (folder / "2026-11-01-KR-123456.md").write_text("---\ntitle: 가\nlang: ko\n---\n\n본문 2026년 계획.\n", encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    code = q.main(["--posts", str(folder), "--as-of", "2026-11-09", "--out", str(Path(tmp) / "r.json")])
                self.assertEqual(code, 0)
        self.assertEqual(len(report["posts"]), 2)


class WriteScopeTest(unittest.TestCase):
    FILE_WRITING_NAMES = {"write_text", "write_bytes", "mkdir", "unlink", "rmdir", "touch", "rename", "symlink_to", "hardlink_to", "chmod", "makedirs",
                          "remove", "removedirs", "copy", "copyfile", "move"}

    def calls_by_function(self):
        found = []
        tree = module_tree()
        for function in [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for node in ast.walk(function):
                if not isinstance(node, ast.Call):
                    continue
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                if name in self.FILE_WRITING_NAMES or name == "open":
                    found.append((function.name, name))
        return found

    def test_the_only_file_writing_call_is_inside_write_report(self):
        calls = self.calls_by_function()
        self.assertEqual(sorted(set(calls)), [("write_report", "write_text")])
        self.assertEqual(len(calls), 1)

    def test_nothing_at_module_level_writes_or_opens_files(self):
        for node in ast.walk(module_tree()):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                self.fail("open() 호출이 있다")
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("open(", source)

    def test_write_report_refuses_a_missing_parent_and_writes_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(q.QualityShadowError):
                q.write_report(root / "nope" / "r.json", "x")
            q.write_report(root / "r.json", "내용\n")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["r.json"])
            self.assertEqual((root / "r.json").read_bytes(), "내용\n".encode("utf-8"))      # 줄 끝은 LF 그대로


def f_string_problems(source):
    """파이썬 3.12 에서만 되는 f-문자열 식의 줄 번호: 식 안에 (한 줄 따옴표와) 같은 따옴표를 쓰거나 역슬래시를 쓴 것.
    3.10·3.11 에서는 인터프리터가 이미 문법 오류로 막으므로 3.12 이상에서만 AST 위치로 확인한다."""
    if sys.version_info < (3, 12):
        return []
    bad = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.JoinedStr):
            continue
        whole = ast.get_source_segment(source, node) or ""
        opening = re.match(r"[rRbBfF]+('''|\"\"\"|'|\")", whole)
        if not opening:
            continue
        delimiter = opening.group(1)
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                inner = ast.get_source_segment(source, value.value) or ""
                if (len(delimiter) == 1 and delimiter in inner) or "\\" in inner:
                    bad.append(node.lineno)
    return sorted(set(bad))


class ForbiddenConstructsTest(unittest.TestCase):
    def test_no_windows_only_constructs_or_backslash_paths(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        for word in ("msvcrt", "ctypes"):
            self.assertNotIn(word, source)
        self.assertIsNone(re.search(r"\b[A-Za-z]:\\", source), "드라이브 글자가 든 윈도 경로가 있다")

    def test_main_starts_by_making_the_console_safe(self):
        main = next(node for node in module_tree().body if isinstance(node, ast.FunctionDef) and node.name == "main")
        first = main.body[0]
        self.assertIsInstance(first, ast.Expr)
        self.assertEqual(ast.unparse(first.value), "console.safe_output()")

    def test_the_module_has_no_secret_like_literals_or_real_blog_identifiers(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        for pattern in SECRET_AND_IDENTIFIER_PATTERNS:
            self.assertIsNone(re.search(pattern, source), pattern)

    def test_the_ci_python_matrix_includes_3_10_so_no_newer_only_syntax_is_used(self):
        workflow = (ROOT / ".github" / "workflows" / "guardrails.yml").read_text(encoding="utf-8")
        self.assertIn("'3.10'", workflow)
        source = MODULE_PATH.read_text(encoding="utf-8")
        for newer in ("tomllib", "datetime.UTC", "typing.Self", "ExceptionGroup", "except*"):
            self.assertNotIn(newer, source)
        for path in (MODULE_PATH, Path(__file__), ROOT / "tests" / "test_quality_shadow.py"):
            self.assertEqual(f_string_problems(path.read_text(encoding="utf-8")), [], f"{path.name}: 3.12 에서만 되는 f-문자열 식(같은 따옴표·역슬래시)이 있다")

    @unittest.skipIf(sys.version_info < (3, 12), "3.12 이상에서만 이런 식을 문법으로 받아들인다")
    def test_the_f_string_detector_itself_works(self):
        quote = chr(34)
        bad = "x = f" + quote + "{d[" + quote + "k" + quote + "]}" + quote + "\n"
        self.assertEqual(f_string_problems(bad), [1])
        backslash = "y = f" + quote + "{" + chr(39) + chr(92) + "n" + chr(39) + ".join(z)}" + quote + "\n"
        self.assertEqual(f_string_problems(backslash), [1])
        good = "x = f" + quote + "{d[" + chr(39) + "k" + chr(39) + "]}" + quote + "\n"
        self.assertEqual(f_string_problems(good), [])
        triple = "x = f" + quote * 3 + "{d[" + quote + "k" + quote + "]}" + quote * 3 + "\n"
        self.assertEqual(f_string_problems(triple), [])


# ----------------------------------------------------------------------------
# 분류표·건강 프로필·문서 대조
# ----------------------------------------------------------------------------
def url_hosts(sources):
    return {q.host_of(source["url"]) for source in sources}


class DriftTest(unittest.TestCase):
    def test_every_domain_the_generator_knows_is_classified(self):
        domains = set(g.TERMS_BLOCKED_DOMAINS)
        for lane in g.TRUSTED_SOURCE_DOMAINS.values():
            domains.update(lane)
        domains.update(url_hosts(g.NEWS_SOURCES))
        unclassified = sorted(domain for domain in domains if q.classify_host(domain)[0] == q.CATEGORY_UNKNOWN)
        self.assertEqual(unclassified, [], "generator.py 의 도메인이 분류표에 없다 — pipeline/quality_shadow.py 의 DOMAIN_RULES 에 더한다")

    def test_every_source_the_generator_reads_is_official(self):
        for source in g.NEWS_SOURCES:
            with self.subTest(source=source["name"]):
                category = q.classify_host(q.host_of(source["url"]))[0]
                self.assertIn(category, q.OFFICIAL_CATEGORIES, f"{source['name']} → {category}")

    def test_blocked_media_are_never_classified_as_official_public_agencies(self):
        for domain in g.TERMS_BLOCKED_DOMAINS:
            with self.subTest(domain=domain):
                self.assertNotEqual(q.classify_host(domain)[0], q.CATEGORY_PUBLIC)

    def test_the_health_profiles_the_module_borrows_exist_and_keep_the_keys_it_reads(self):
        for lang, name in q.HEALTH_PROFILE_FILES.items():
            with self.subTest(lang=lang):
                profile = json.loads((ROOT / "pipeline" / "profiles" / name).read_text(encoding="utf-8"))
                self.assertTrue(profile.get("body_banned_patterns"))
                self.assertTrue(profile.get("banned_patterns"))
                self.assertEqual(profile.get("language"), lang)
                result = gates.body_risk_hit("그냥 평범한 문장입니다. A plain sentence.", profile)
                self.assertEqual(len(result), 2)
                self.assertEqual(len(gates.first_match(profile["banned_patterns"], "plain text")), 2)

    def test_the_profile_loader_returns_the_profile_and_no_reason_for_both_languages(self):
        for lang in ("ko", "en"):
            name, profile, reason = q._load_health_profile(lang)
            self.assertEqual(name, q.HEALTH_PROFILE_FILES[lang])
            self.assertIsNotNone(profile)
            self.assertIsNone(reason)
        self.assertIsNone(q._load_health_profile("fr")[1])


class DocsTest(unittest.TestCase):
    DOC = (ROOT / "docs" / "QUALITY_SHADOW.md").read_text(encoding="utf-8")

    def test_the_doc_declares_that_it_is_unrelated_to_publishing(self):
        for phrase in ("게시와 무관", "연결하지 않는다", "T3"):
            self.assertTrue(phrase in self.DOC, f"문서에 '{phrase}' 선언이 없다")

    def test_the_doc_states_the_one_exception_to_the_connection_ban_in_the_exact_words(self):
        """병합 계획의 추가 요청: 연결 금지 서술(머리말·§1 표·§7)에 '유일한 예외: 수동 그림자 워크플로의 별도 프로세스 호출' 이 정확히 있고, 예외 파일과 조건이 시험 코드와 같다."""
        phrase = "유일한 예외: 수동 그림자 워크플로의 별도 프로세스 호출"
        header = self.DOC[:self.DOC.index("## 1. 한눈에")]
        row = next(line for line in self.DOC.splitlines() if line.startswith("| 게시·초안 흐름에 연결하지 않는다 |"))
        section7 = self.DOC[self.DOC.index("## 7. 연결하려면"):self.DOC.index("## 8. 시험")]
        for label, part in (("머리말", header), ("§1 표", row), ("§7", section7)):
            self.assertIn(phrase, part, label)
        self.assertEqual(self.DOC.count(phrase), 3)
        for part in (header, row):
            self.assertIn(SHADOW_WORKFLOW_REL, part)
            self.assertIn("python -m pipeline.quality_shadow", part)
        for word in ("python pipeline/quality_shadow.py", "수동 실행", "불러오지 않고", "workflow_dispatch", "파일이 없는 저장소에서는 예외 검사를 건너뛴다", "다른 파일이 같은 일을 하면 연결로 읽혀"):
            self.assertIn(word, row)
        register = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
        d89 = next(line for line in register.splitlines() if line.startswith("| **D-89** |"))
        self.assertIn("워크플로는 수동 그림자 워크플로 한 파일이 별도 프로세스로 부르는 것만 예외", d89)
        self.assertNotIn("생성기·실행기·워크플로·레지스트리 어디에도 연결하지 않는다", d89)

    def test_the_doc_defines_all_nine_items_in_order(self):
        headings = re.findall(r"^### 항목 (\d) — (.+)$", self.DOC, re.M)
        self.assertEqual([number for number, _ in headings], [str(n) for n in range(1, 10)])
        names = " ".join(title for _, title in headings)
        for word in ("주장 수", "출처 수", "추가 가치", "유사도", "단순 요약", "행사 안내", "건강 위험", "주제 적합성"):
            self.assertIn(word, names)

    def test_the_threshold_table_matches_the_code_constants(self):
        rows = {name: row for name, row in re.findall(r"^\| `([A-Z_]+)` \| (.+)$", self.DOC, re.M)}
        expected = {"CLONE_STRUCTURE_TOLERANCE": [q.CLONE_STRUCTURE_TOLERANCE], "CLONE_NUMBER_JACCARD_MIN": [q.CLONE_NUMBER_JACCARD_MIN],
                    "CLONE_LENGTH_RATIO_BAND": list(q.CLONE_LENGTH_RATIO_BAND), "EVENT_SENTENCE_RATIO_MIN": [q.EVENT_SENTENCE_RATIO_MIN],
                    "EVENT_DISTINCT_TERMS_MIN": [q.EVENT_DISTINCT_TERMS_MIN], "EVENT_TITLE_RATIO_MIN": [q.EVENT_TITLE_RATIO_MIN],
                    "HEALTH_CAUTION_DISTINCT_MIN": [q.HEALTH_CAUTION_DISTINCT_MIN], "SMALL_INTEGER_MAX": [q.SMALL_INTEGER_MAX]}
        self.assertEqual(sorted(rows), sorted(expected))
        for name, values in expected.items():
            cell = rows[name].split("|")[0]
            numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", cell)]
            self.assertEqual(numbers, [float(v) for v in values], name)

    def test_the_usage_section_lists_every_command_line_option(self):
        parser_options = {option for action in q.build_parser()._actions for option in action.option_strings if option.startswith("--") and option != "--help"}
        for option in parser_options:
            self.assertTrue(f"`{option}" in self.DOC, f"문서 사용법 표에 {option} 이 없다")
        for phrase in ("python -m pipeline.quality_shadow", "null_reasons"):
            self.assertTrue(phrase in self.DOC, f"문서에 '{phrase}' 가 없다")

    def test_the_other_docs_point_at_it(self):
        architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        self.assertIsNotNone(re.search(r"\|[^\n]*그림자 모드[^\n]*quality_shadow[^\n]*\|", architecture), "ARCHITECTURE.md §9 표에 그림자 모드 한 줄이 없다")
        register = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
        self.assertIsNotNone(re.search(r"\| \*\*D-\d+\*\* \|[^\n]*그림자 모드[^\n]*\|", register), "DEFECT_REGISTER.md 에 그림자 모드 결정 행이 없다")

    def test_the_doc_has_no_liquid_syntax(self):
        self.assertNotIn("{%", self.DOC)
        self.assertNotIn("{{", self.DOC)

    def test_the_doc_and_the_defect_row_have_no_tilde_and_the_doc_has_no_web_links(self):
        """독립 검증 P11: 물결표 두 개 사이의 글이 GitHub 화면에서 취소선이 되는 사고를 막는다(범위는 en dash). 문서에는 웹 주소 링크도 넣지 않는다."""
        tilde = chr(126)                                           # 물결표 글자를 소스에 적지 않으려고 코드 값으로 만든다
        self.assertNotIn(tilde, self.DOC)
        self.assertIsNone(re.search(r"https?://", self.DOC))
        register = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
        rows = [line for line in register.splitlines() if line.startswith("| **D-89** |")]
        self.assertEqual(len(rows), 1)
        self.assertNotIn(tilde, rows[0])
        architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        lines = [line for line in architecture.splitlines() if "quality_shadow" in line]
        self.assertTrue(lines)
        self.assertTrue(all(tilde not in line for line in lines))

    def test_the_doc_says_what_the_tool_can_and_cannot_decide(self):
        """독립 검증 §5·§6: 아홉 측정의 '실제로 재는 것·격차'와 12개 제한 재개 조건 각각을 이 도구가 판정하는지 문서가 말한다."""
        self.assertIn("## 9. 이 도구로 판정할 수 있는 것·없는 것", self.DOC)
        self.assertGreaterEqual(self.DOC.count("이 도구는 신호를 낼 뿐 제한 재개 조건을 단독으로 판정하지 못한다"), 2)       # 머리말과 §9
        section = self.DOC[self.DOC.index("## 9. 이 도구로 판정할 수 있는 것·없는 것"):]
        conditions = re.findall(r"^\| ([①-⑫]) ", section, re.M)
        self.assertEqual(conditions, [chr(0x2460 + index) for index in range(12)])
        for word in ("불가", "후보 목록만", "부분", "글 수만 센다", "이 도구가 연결돼 있지 않다는 사실만"):
            self.assertIn(word, section)
        measures = ("핵심 사실 주장 수", "공식 근거로 지원되는 주장 수", "출처 수", "원문 대비 추가 가치", "한·영 유사도", "보도자료·회사 발표 단순 요약", "행사 안내 중심", "건강 위험 판정", "주제 적합성")
        table = section[section.index("### 아홉 측정"):section.index("### 제한 재개 조건 12개")]
        for measure in measures:
            self.assertIn(f"| {measure} |", table)
        for phrase in ("그림자 실행 횟수 기록", "서로 다른 초안 증명", "건강 C 누락 0", "가짜 인용 0", "결함 등급", "이 도구 밖의 일"):
            self.assertIn(phrase, self.DOC)
        for out_of_scope in ("그림자 실행 기록부", "--sources-dir", "건강 사전 확장", "지어낸 인용 탐지"):
            self.assertIn(out_of_scope, section.split("### 하지 않는 것")[1])

    def test_the_doc_states_the_health_limit_the_own_domain_warning_and_the_honest_sample_sizes(self):
        self.assertIn("운영자의 건강 C 예시 9개에 이 도구를 돌려 보면 6개를 놓친다", self.DOC)
        self.assertIn("A/B/C 규칙이 아니라 낱말 기반 신호", self.DOC)
        self.assertIn("실제 건강 C 자동 중단은 Gate 쪽 규칙의 몫", self.DOC)
        self.assertIn("이 도구의 사전을 고쳐 C 를 잡게 만들려고 하지도 않는다", self.DOC)
        self.assertIn("주지 않으면 사이트 자체 링크(내부 링크)가 **외부 출처 수**에 섞인다", self.DOC)
        self.assertIn("권장 호출 인자", self.DOC)
        self.assertIn("'오탐 0'은 이 음성 표본 3쌍에서의 값이라 근거가 약하다", self.DOC)
        self.assertIn("합성 독립 각색 8쌍", self.DOC)
        self.assertIn("5쌍이 걸러지고", self.DOC)
        self.assertIn("2쌍이 걸린다", self.DOC)
        self.assertIn("source_url_differs", self.DOC)
        self.assertIn("20자리를 넘는 숫자 연속을 20자리로 줄여서", self.DOC)
        self.assertIn("규칙 파일(`pipeline/gates.py`·프로필)은 고치지 않는다", self.DOC)
        self.assertNotIn("code_digest", q.render_json(q.analyze_corpus([], AS_OF)))               # 보고서 JSON 에 코드 판별 값 필드를 넣지 않는다(결정성·소비자 호환)

    def test_every_link_in_the_doc_resolves(self):
        for target in re.findall(r"\]\(([^)\s#]+)(?:#[^)]*)?\)", self.DOC):
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue
            self.assertTrue((ROOT / "docs" / target).exists(), target)


# ----------------------------------------------------------------------------
# 실제 글 스모크 — 이 저장소의 _posts 를 읽어 분석해도 죽지 않고 규약을 지킨다(개수·내용은 가정하지 않는다)
# ----------------------------------------------------------------------------
def missing_reasons(node, path=""):
    missing = []
    if isinstance(node, dict):
        reasons = node.get("null_reasons") if isinstance(node.get("null_reasons"), dict) else {}
        for key, value in node.items():
            if value is None and key not in reasons:
                missing.append(f"{path}.{key}")
            elif isinstance(value, (dict, list)):
                missing += missing_reasons(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            missing += missing_reasons(item, f"{path}[{index}]")
    return missing


class RealPostsSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.posts, cls.problems = q.collect_posts(ROOT / "_posts")
        cls.report = q.analyze_corpus(cls.posts, AS_OF, problems=cls.problems)

    def test_the_real_posts_are_read_and_every_one_gets_all_measurement_sections(self):
        self.assertGreater(len(self.posts), 10)
        self.assertEqual(len(self.report["posts"]), len(self.posts))
        for result in self.report["posts"]:
            for section in ("claims", "grounding", "sources", "added_value", "press_release_summary", "event_focus", "health_risk", "topic_fit"):
                self.assertIn(section, result, result["path"])

    def test_every_null_in_the_real_report_has_a_reason(self):
        missing = []
        for result in self.report["posts"]:
            for section in ("claims", "grounding", "sources", "added_value", "press_release_summary", "event_focus", "health_risk", "topic_fit"):
                missing += missing_reasons(result[section], f"{result['path']}.{section}")
        for pair in self.report["pairs"]:
            missing += missing_reasons(pair, f"pair {pair['date']} {pair['pair_key']}")
        self.assertEqual(missing, [])

    def test_the_real_report_is_byte_identical_when_run_twice(self):
        posts, _ = q.collect_posts(ROOT / "_posts")
        again = q.analyze_corpus(posts, AS_OF, problems=self.problems)
        self.assertEqual(q.render_json(self.report), q.render_json(again))

    def test_the_real_report_contains_no_absolute_paths_or_secrets(self):
        text = q.render_json(self.report)
        self.assertNotIn(str(ROOT), text)
        self.assertNotIn(ROOT.name + "/", text)
        for pattern in SECRET_AND_IDENTIFIER_PATTERNS:
            self.assertIsNone(re.search(pattern, text), pattern)

    def test_pairs_use_date_and_key_so_two_pairs_with_the_same_key_stay_separate(self):
        keys = [(pair["date"], pair["pair_key"]) for pair in self.report["pairs"]]
        self.assertEqual(len(keys), len(set(keys)))

    def test_running_the_analysis_does_not_change_the_real_posts(self):
        before = {path: path.stat().st_size for path in (ROOT / "_posts").rglob("*.md")}
        posts, _ = q.collect_posts(ROOT / "_posts")
        q.analyze_corpus(posts, AS_OF)
        self.assertEqual(before, {path: path.stat().st_size for path in (ROOT / "_posts").rglob("*.md")})


if __name__ == "__main__":
    unittest.main()
