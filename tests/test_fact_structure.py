"""구조화 Fact 경로 1단계 — 구조 시험(소스를 읽어 확인): 새 모듈이 표준 라이브러리와 서로만 import 하고 `generator.py`·`pipeline/` 의 다른 모듈을 import 하지 않음 ·
`urllib`·`socket`·`subprocess`·`time`·`random`·`datetime.now` 호출 0(AST) · `msvcrt`·`ctypes`·역슬래시 경로 없음 · 3.10 문법 · 연결 금지(`generator.py`·워크플로가 새 모듈 이름을 부르지 않음 — 2단계가 한 군데에서 연결).
네트워크 없이 파일만 읽는다."""
import ast
import re
import unittest

import _bootstrap

from pipeline import secret_patterns

ROOT = _bootstrap.ROOT
NEW_FILES = ["pipeline/facts.py", "pipeline/calc.py", "pipeline/fact_topics.py", "pipeline/recipes.py", "pipeline/fact_assembler.py",
             "pipeline/adapters/__init__.py", "pipeline/adapters/base.py", "pipeline/adapters/mock_stats.py"]
NEW_MODULES = {"facts", "calc", "fact_topics", "recipes", "fact_assembler", "adapters", "adapters.base", "adapters.mock_stats"}
NEW_TESTS = ["tests/fact_helpers.py", "tests/test_fact_facts.py", "tests/test_fact_calc.py", "tests/test_fact_adapters.py", "tests/test_fact_assembler.py",
             "tests/test_fact_review.py", "tests/test_fact_structure.py", "tests/test_fact_docs.py"]
STDLIB_ALLOWED = {"csv", "dataclasses", "datetime", "decimal", "functools", "hashlib", "io", "json", "re", "typing", "unicodedata"}
BANNED_MODULES = {"urllib", "socket", "subprocess", "time", "random", "os", "sys", "pathlib", "http", "ssl", "shutil", "tempfile", "secrets", "uuid", "glob",
                  "ctypes", "msvcrt", "threading", "multiprocessing", "asyncio", "logging", "requests", "html", "xml", "generator", "blogger_generator"}
BANNED_NAMES = {"open", "print", "input", "exec", "eval", "compile", "__import__", "abs"}      # abs: 단항 abs 는 decimal 전역 정밀도로 반올림한다 — `copy_abs()` 를 쓴다(D-150)
BANNED_CALLS = {"now", "today", "utcnow", "getenv", "urlopen", "system", "Popen", "sleep", "monotonic", "perf_counter", "randint", "choice", "shuffle", "random", "urandom"}
BANNED_ATTRIBUTES = {"environ", "argv"}


def source(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def tree(rel, feature_version=(3, 10)):
    return ast.parse(source(rel), feature_version=feature_version)


class ImportsTest(unittest.TestCase):
    def test_the_new_files_exist(self):
        for rel in NEW_FILES + NEW_TESTS:
            self.assertTrue((ROOT / rel).exists(), rel)

    def test_new_modules_import_only_the_standard_library_and_each_other(self):
        for rel in NEW_FILES:
            for node in ast.walk(tree(rel)):
                with self.subTest(file=rel, line=getattr(node, "lineno", 0)):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            top, _, rest = alias.name.partition(".")
                            if top == "pipeline":
                                self.assertIn(rest, NEW_MODULES, alias.name)
                            else:
                                self.assertIn(top, STDLIB_ALLOWED, alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        self.assertEqual(node.level, 0, "상대 import 를 쓰지 않는다")
                        module = node.module or ""
                        top, _, rest = module.partition(".")
                        if top == "pipeline":
                            if rest:
                                self.assertIn(rest, NEW_MODULES, module)
                            else:
                                for alias in node.names:
                                    self.assertIn(alias.name, NEW_MODULES, alias.name)
                        else:
                            self.assertIn(top, STDLIB_ALLOWED, module)

    def test_nothing_from_the_banned_list_is_imported_even_by_name(self):
        for rel in NEW_FILES:
            names = set()
            for node in ast.walk(tree(rel)):
                if isinstance(node, ast.Import):
                    names |= {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names.add((node.module or "").split(".")[0])
            self.assertFalse(names & BANNED_MODULES, f"{rel}: {names & BANNED_MODULES}")

    def test_no_existing_pipeline_module_is_imported(self):
        existing = {p.stem for p in (ROOT / "pipeline").glob("*.py")} - {"facts", "calc", "fact_topics", "recipes", "fact_assembler", "__init__"}
        self.assertTrue(existing)
        for rel in NEW_FILES:
            text = source(rel)
            for name in existing:
                self.assertNotRegex(text, rf"(?m)^\s*(?:from pipeline import[^\n]*\b{name}\b|from pipeline\.{name}\b|import pipeline\.{name}\b)", f"{rel} -> {name}")
            self.assertNotRegex(text, r"(?m)^\s*(?:import|from) generator\b")
            self.assertNotIn("source_registry", re.sub(r'"""[\s\S]*?"""|#.*', "", text), f"{rel} 이 SRC 모듈을 import 한다")


class PurityTest(unittest.TestCase):
    def test_no_clock_randomness_network_environment_or_file_io(self):
        for rel in NEW_FILES:
            for node in ast.walk(tree(rel)):
                with self.subTest(file=rel, line=getattr(node, "lineno", 0)):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, BANNED_NAMES)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                        self.assertNotIn(node.func.attr, BANNED_CALLS)         # `datetime.now()` 같은 호출 — `ctx.today` 처럼 값을 읽는 것은 시계가 아니다
                    if isinstance(node, ast.Attribute):
                        self.assertNotIn(node.attr, BANNED_ATTRIBUTES)
                    if isinstance(node, ast.Name):
                        self.assertNotIn(node.id, BANNED_NAMES | {"os", "sys", "time", "random", "urllib", "socket", "subprocess"})

    def test_no_msvcrt_ctypes_or_backslash_paths(self):
        for rel in NEW_FILES:
            text = source(rel)
            self.assertNotRegex(re.sub(r'"[^"\n]*"|\'[^\'\n]*\'', "", text), r"msvcrt|ctypes", rel)
            for node in ast.walk(tree(rel)):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertIsNone(re.search(r"[A-Za-z]:\\|\\\\[A-Za-z]|[A-Za-z]:/(?:Users|work|Windows)", node.value), f"{rel}: 경로로 보이는 글자")
                    self.assertNotIn("msvcrt", node.value)

    def test_python_310_syntax_only(self):
        for rel in NEW_FILES + NEW_TESTS:
            parsed = tree(rel, (3, 10))
            for node in ast.walk(parsed):
                self.assertNotIsInstance(node, getattr(ast, "TryStar", ()), rel)
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, {"Self", "StrEnum", "ExceptionGroup", "LiteralString", "Never", "assert_never"}, rel)
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    self.assertNotIn("tomllib", ast.dump(node), rel)

    def test_modules_hold_only_constants_and_definitions_at_the_top_level(self):
        for rel in NEW_FILES:
            for node in tree(rel).body:
                with self.subTest(file=rel, line=node.lineno):
                    allowed = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign, ast.Expr)
                    self.assertIsInstance(node, allowed)
                    if isinstance(node, ast.Expr):
                        self.assertIsInstance(node.value, ast.Constant, "모듈 최상위에서 부르는 식이 없다(독스트링만)")

    def test_the_standard_library_set_really_is_what_the_modules_use(self):
        used = set()
        for rel in NEW_FILES:
            for node in ast.walk(tree(rel)):
                if isinstance(node, ast.Import):
                    used |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] != "pipeline":
                    used.add((node.module or "").split(".")[0])
        self.assertTrue(used <= STDLIB_ALLOWED)
        self.assertTrue({"dataclasses", "decimal", "hashlib", "json", "re"} <= used)


class NoConnectionTest(unittest.TestCase):
    """1단계는 새 모듈·새 시험·문서뿐이다 — 생성기·다른 pipeline 모듈·워크플로·스크립트가 새 모듈 이름을 부르지 않는다. 2단계가 한 군데에서 연결한다."""
    NAMES = r"(?:facts|calc|fact_topics|recipes|fact_assembler|adapters)"
    # 문장 단위 import·`-m` 실행·문자열로 모듈 이름을 넘기는 호출만 연결로 본다(주석·문서의 언급은 연결이 아니다 — SRC 의 문서가 인터페이스를 설명할 수 있다)
    PATTERN = re.compile(rf"^\s*(?:from|import)\s+pipeline(?:\.{NAMES}\b|\s+import\s+[^\n#]*\b{NAMES}\b)"
                         rf"|^\s*(?:from|import)\s+{NAMES}\b|-m\s+pipeline\.{NAMES}\b|[\"']pipeline\.{NAMES}[\"']", re.M)

    def scan_targets(self):
        targets = [ROOT / "generator.py", ROOT / "blogger_generator.py"]
        targets += [p for p in sorted((ROOT / "pipeline").rglob("*.py")) if p.relative_to(ROOT).as_posix() not in NEW_FILES]
        targets += sorted((ROOT / "scripts").glob("*.py"))
        targets += sorted((ROOT / ".github").rglob("*.yml")) + sorted((ROOT / ".github").rglob("*.yaml"))
        targets += [ROOT / "pipeline" / "blogs.json"]
        return [t for t in targets if t.exists()]

    def test_nobody_outside_the_new_files_names_the_new_modules(self):
        targets = self.scan_targets()
        self.assertGreater(len(targets), 30)
        for path in targets:
            with self.subTest(file=path.relative_to(ROOT).as_posix()):
                self.assertIsNone(self.PATTERN.search(path.read_text(encoding="utf-8")))

    def test_other_tests_do_not_import_the_new_modules_either_except_ours(self):
        mine = {rel.split("/", 1)[1] for rel in NEW_TESTS}
        for path in sorted((ROOT / "tests").glob("*.py")):
            if path.name in mine:
                continue
            with self.subTest(file=path.name):
                self.assertIsNone(self.PATTERN.search(path.read_text(encoding="utf-8")))

    def test_the_registry_has_no_switch_for_the_new_path_yet(self):
        text = source("pipeline/blogs.json")
        for needle in ("content_source", "fact", "facts"):
            self.assertNotIn(needle, text)
        self.assertNotIn("content_source", source("pipeline/registry.py"))
        self.assertNotIn("content_source", source("generator.py"))

    def test_the_new_tests_are_offline(self):
        for rel in NEW_TESTS:
            for node in ast.walk(tree(rel)):
                if isinstance(node, ast.Call):
                    name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                    self.assertNotIn(name, ("urlopen", "create_connection", "getaddrinfo"), rel)
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                    for mod in mods:
                        self.assertNotIn(mod.split(".")[0], {"urllib", "socket", "requests", "http", "ssl"}, rel)


class HygieneTest(unittest.TestCase):
    def test_no_secret_like_text_or_real_identifiers_in_the_new_files(self):
        files = NEW_FILES + NEW_TESTS + ["docs/FACT_PATH.md"] + [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "tests" / "fixtures").glob("fact_golden_*.md"))]
        self.assertGreaterEqual(len(files), 19)
        parts = ["chance" + "blog", "shine" + "88pc", "kc" + "yoon", "blog" + "spot", "ma" + "cat", "ca-" + "pub-", "adsby" + "google", "pew" + "research", "client" + "_secret",
                 "refresh" + "_token"]
        real = re.compile("(?i)" + "|".join(re.escape(part) for part in parts) + r"|pub-\d{8,}")
        for rel in files:
            text = source(rel)
            with self.subTest(file=rel):
                self.assertEqual(secret_patterns.find_secrets(text), [])
                self.assertIsNone(real.search(text), real.search(text))

    def test_the_golden_posts_exist_and_are_marked_as_test_data(self):
        for rid in ("r01_time_series", "r02_region_compare", "r03_record_position"):
            text = source(f"tests/fixtures/fact_golden_{rid}.md")
            self.assertTrue(text.startswith("---\nlayout: post\n"))
            self.assertIn("시험용 가상 통계", text)
            self.assertIn("실제 기관의 통계가 아닙니다", text)
            self.assertIn("https://example.invalid/", text)
            self.assertNotIn("{{", text)
            self.assertNotIn("{%", text)


if __name__ == "__main__":
    unittest.main()
