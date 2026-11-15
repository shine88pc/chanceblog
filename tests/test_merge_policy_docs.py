"""조건부 승인형 AI 병합 정책의 문서·정적 시험 — `docs/AI_MERGE_POLICY.md` 와 `pipeline/merge_policy.py` 가 서로, 그리고 운영자 원문의 목록과 어긋나지 않는지.

문서의 글이 옳은지는 시험이 알 수 없어 사람이 본다. 여기서는 낱말·번호·표·예시 글·이름을 코드와 대조하고(문서의 목록 = 시험에 글자 그대로 적어 둔 운영자 원문 = 모듈 상수), 문서 규칙(물결표·웹 주소·Liquid·
로컬 경로 없음)과 모듈의 성질 — 표준 라이브러리 `re`·`dataclasses` 만, 네트워크·파일 쓰기·환경 변수·시간·난수 없음, 어디서도 import 되지 않음(지금은 꺼져 있음) — 을 정적으로 지킨다.
이 시험은 네트워크·파일 쓰기를 하지 않는다.
"""
import ast
import re
import unittest

import _bootstrap
from pipeline import merge_policy as mp
from pipeline.secret_patterns import find_secrets

ROOT = _bootstrap.ROOT
DOC_PATH = ROOT / "docs" / "AI_MERGE_POLICY.md"
MODULE_PATH = ROOT / "pipeline" / "merge_policy.py"
TEST_PATHS = (ROOT / "tests" / "test_merge_policy.py", ROOT / "tests" / "test_merge_policy_docs.py")
DOC = DOC_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")
REGISTER = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8").replace("\r\n", "\n")

# ---- 운영자 결정 원문의 목록(글자 그대로 — 모듈 상수와 별개로 적어 둔다) -----------------------------------------------------------------------------------
OPERATOR_ONLY_12 = ("GitHub Actions Workflow", "광고·AdSense·ads.txt", "공개 게시물과 고정 페이지", "PIPELINE_PAUSE", "발행 모드와 발행 재개", "Provider 활성화",
                    "API Key·Secret·Credential", "의존성 추가", "데이터 삭제·Migration", "자동 게시 활성화", "외부 비용 발생 기능", "Main Branch 보호 설정")
PRECONDITIONS_8 = ("승인된 병합 번호와 PR 일치", "승인 이후 Commit 추가 없음", "검사 전체 통과", "독립 검증 통과", "충돌 없음", "변경 범위가 승인 설명과 일치", "비밀정보 노출 없음", "원복 방법 확인")
REJECTED_5 = ("확인했습니다", "진행하세요", "좋아 보입니다", "기본값대로", "다음 단계 진행")
SCOPES_7 = ("일반 프로그램 코드", "일반 UI", "시험", "문서", "로컬 저장·조회", "오류 수정", "접근성·성능 개선")
EXPLANATION_6 = ("무엇을 바꾸나요?", "왜 필요한가요?", "사용할 때 무엇이 달라지나요?", "위험은 무엇인가요?", "검사 결과", "되돌리기")
COMPLETION_7 = ("병합 번호", "PR 번호", "병합된 Commit", "실제 반영된 변화", "main 검사 결과", "이상 유무", "원복 Commit 또는 원복 방법")
TRIAL_6 = ("승인받은 PR만 병합", "승인 후 변경 없음", "main 검사 전체 통과", "원복 발생 0건", "다른 PR 오병합 0건", "운영자 전용 경로 변경 0건")
SECTION_TITLES = ("상태와 한눈에", "운영자 결정 요지", "흐름 7단계", "쉬운 병합 설명 양식", "승인 방식", "병합 직전 재확인 8조건", "범위", "병합 방식 제한", "사후 처리", "첫 운영 3건 시험과 즉시 중지",
                  "켜는 방법", "이 문서를 바꾸는 법")
FLOW = "AI 가 PR 작성 → 검사와 독립 검증 → 쉬운 병합 설명 발송 → 운영자가 병합 번호를 명시해 승인 → AI 가 승인된 PR 병합 → main 사후 검사 → 병합 완료 알림"
ANSWERS = ("앱을 닫아도 작성 중인 초안을 다시 열 수 있도록 저장 기능을 추가합니다.", "현재는 앱을 닫으면 초안이 사라집니다.", "저장 버튼과 저장된 초안 목록이 추가됩니다.",
           "저장 실패나 손상 가능성을 막기 위해 원자적 저장과 복구 시험을 수행했습니다.", "전체 검사와 독립 검증을 통과했고 기존 복사 기능에는 변화가 없습니다.",
           "문제가 발생하면 M075 병합만 되돌리면 이전 상태로 복구됩니다.")
URL_RX = re.compile("https?" + ":" + "//")
INVISIBLE = [chr(code) for code in list(range(0x200B, 0x2010)) + list(range(0x202A, 0x202F)) + list(range(0x2060, 0x2065)) + list(range(0x2066, 0x206A)) + [0xFEFF]]


def sections():
    """번호 → 절의 글(`## n. 제목` 줄부터 다음 `## ` 앞까지)."""
    found = {}
    for part in re.split(r"(?m)^(?=## \d+\. )", DOC):
        head = re.match(r"## (\d+)\. (.+)", part)
        if head:
            found[int(head.group(1))] = part
    return found


SECTIONS = sections()


def subsection(label):
    """`### 5-2. …` 소절의 글(다음 `## `·`### ` 앞까지)."""
    start = DOC.index("### " + label + ". ")
    following = re.search(r"(?m)^#{2,3} ", DOC[start + 5:])
    return DOC[start:start + 5 + following.start()] if following else DOC[start:]


def table_rows(text):
    """글 안의 첫 표의 본문 행들(머리·구분 행은 뺀다)."""
    rows = []
    for line in text.split("\n"):
        if re.match(r"^\|[-| ]+\|$", line):                                   # 머리 아래 구분 행은 건너뛴다
            continue
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        elif rows:
            break
    return rows[1:]


def bullets(text, indent=r""):
    return re.findall(r"(?m)^" + indent + r"- (.+)$", text)


class DocShapeTest(unittest.TestCase):
    def test_the_title_and_the_twelve_sections_are_in_order(self):
        self.assertTrue(DOC.startswith("# 조건부 승인형 AI 병합 정책\n"))
        heads = re.findall(r"(?m)^## (\d+)\. (.+)$", DOC)
        self.assertEqual([int(number) for number, _title in heads], list(range(1, 13)))
        self.assertEqual(tuple(title for _number, title in heads), SECTION_TITLES)
        self.assertEqual(set(SECTIONS), set(range(1, 13)))

    def test_the_status_is_off_and_turning_it_on_is_a_separate_operator_merge(self):
        quote = DOC.split("\n## 1.")[0]
        self.assertIn("꺼져 있음", quote)
        self.assertIn("꺼져 있음", SECTIONS[1])
        self.assertIn("**상태: 꺼져 있음.**", SECTIONS[1])
        self.assertIn("AI 는 아무것도 병합하지 않습니다", SECTIONS[1])
        for number in (1, 2, 11):
            self.assertIn("별도 병합 요청", SECTIONS[number], number)
        for number in (1, 2, 11, 12):
            self.assertIn("운영자가 직접 병합", SECTIONS[number], number)
        for number in (1, 8):
            self.assertIn("main 직접 push 금지", SECTIONS[number], number)
        self.assertIn("지금(꺼져 있음)은 4·5단계 대신 운영자가 PR 화면에서 직접 병합합니다", SECTIONS[3])

    def test_the_flow_is_the_operators_seven_steps(self):
        self.assertIn(FLOW, SECTIONS[3])
        rows = table_rows(SECTIONS[3])
        self.assertEqual(len(rows), 7)
        self.assertEqual([row[0].split(".")[0] for row in rows], [str(number) for number in range(1, 8)])
        self.assertEqual(len(re.findall(r"(?m)^\d+\. ", SECTIONS[2])), 10)

    def test_the_text_follows_the_document_rules(self):
        self.assertNotIn(chr(126), DOC)
        self.assertIsNone(URL_RX.search(DOC))
        self.assertNotIn("{{", DOC)
        self.assertNotIn("{%", DOC)
        self.assertNotIn("](", DOC)                                                            # 링크 없이 백틱으로 이름만 적는다
        self.assertNotRegex(DOC, r"[A-Za-z]:[/\\]")                                            # 로컬 경로 없음
        self.assertNotIn("SDI" + "_USER", DOC)
        self.assertNotIn("\r", DOC)
        self.assertIsNone(re.search("[" + "".join(INVISIBLE) + "]", DOC))                                           # 보이지 않는 글자 없음
        self.assertEqual(find_secrets(DOC), [])

    def test_the_tables_have_equal_columns(self):
        for block in re.findall(r"((?:^\|.*\|\n)+)", DOC, re.M):
            counts = {line.count("|") for line in block.splitlines()}
            self.assertEqual(len(counts), 1, block[:80])


class ListsMatchTest(unittest.TestCase):
    """문서의 목록 = 운영자 원문(이 파일에 글자 그대로) = 모듈 상수 — 셋 모두 같다."""

    def test_the_explanation_table_has_the_six_items(self):
        labels = tuple(row[0] for row in table_rows(subsection("4-1")))
        self.assertEqual(labels, EXPLANATION_6)
        self.assertEqual(labels, mp.EXPLANATION_ITEMS)

    def test_the_rejected_phrases_are_the_five_in_section_five(self):
        listed = tuple(bullets(subsection("5-2")))
        self.assertEqual(listed, REJECTED_5)
        self.assertEqual(listed, mp.REJECTED_PHRASES)
        self.assertIn("M075 승인", subsection("5-1"))

    def test_the_precondition_table_has_the_eight_in_order(self):
        rows = table_rows(SECTIONS[6])
        self.assertEqual([row[0] for row in rows], [str(number) for number in range(1, 9)])
        self.assertEqual(tuple(row[1] for row in rows), PRECONDITIONS_8)
        self.assertEqual(tuple(row[1] for row in rows), tuple(label for _code, label in mp.PRECONDITIONS))

    def test_the_allowed_scope_list_is_the_seven(self):
        listed = tuple(bullets(subsection("7-1")))
        self.assertEqual(listed, SCOPES_7)
        self.assertEqual(listed, mp.AI_MERGE_SCOPES)

    def test_the_operator_only_table_has_the_twelve_in_order(self):
        rows = table_rows(subsection("7-2"))
        self.assertEqual([row[0] for row in rows], [str(number) for number in range(1, 13)])
        self.assertEqual(tuple(row[1] for row in rows), OPERATOR_ONLY_12)
        self.assertEqual(tuple(row[1] for row in rows), mp.OPERATOR_ONLY_LABELS)

    def test_the_completion_notice_items_are_the_seven_in_section_nine(self):
        listed = tuple(bullets(SECTIONS[9], r"[ \t]+"))
        self.assertEqual(listed, COMPLETION_7)
        self.assertEqual(listed, mp.COMPLETION_ITEMS)

    def test_the_trial_criteria_are_the_six_in_section_ten(self):
        listed = tuple(bullets(SECTIONS[10]))
        self.assertEqual(listed, TRIAL_6)
        self.assertEqual(listed, tuple(label for _key, label in mp.TRIAL_CRITERIA))
        self.assertIn("즉시 중지", SECTIONS[10])
        self.assertIn("기록이 3건 미만이어도", SECTIONS[10])
        for word in (mp.TRIAL_CONTINUE, mp.TRIAL_PENDING, mp.TRIAL_STOP):
            self.assertIn("`" + word + "`", SECTIONS[10])

    def test_the_rule_words_of_the_classification_are_all_in_the_scope_section(self):
        for word in mp.DOCUMENTED_RULE_WORDS:
            with self.subTest(word=word):
                self.assertIn("`" + word + "`", SECTIONS[7])

    def test_the_safety_and_external_connection_rules_are_documented_in_full(self):
        """총괄의 보수적 판단(결함 D-347)으로 더한 두 표시의 규칙 낱말·모듈·스킴·예시 주소·문서 확장자가 §7-6 에 빠짐없이 있다."""
        section = subsection("7-6")
        words = (mp.SAFETY_GUARD_WORDS + mp.SAFETY_GUARD_DOCS + mp.EXTERNAL_MODULES + mp.EXTERNAL_SCHEMES + mp.EXAMPLE_HOSTS + mp.DOC_SUFFIXES
                 + tuple("." + name for name in mp.EXAMPLE_TOP_LEVELS))
        for word in words:
            with self.subTest(word=word):
                self.assertIn("`" + word + "`", section)
        self.assertEqual(len(mp.EXTERNAL_MODULES), 51)

    def test_the_extra_flags_and_the_policy_files_are_named(self):
        for code in mp.EXTRA_CODES:
            self.assertIn("`" + code + "`", SECTIONS[7])
        for name in mp.POLICY_SELF_FILES[1:]:
            self.assertIn("`" + name + "`", DOC)
            self.assertTrue((ROOT / name).is_file(), name)
        self.assertTrue((ROOT / mp.POLICY_SELF_FILES[0]).is_file())
        self.assertIn("이 정책의 문서·모듈·시험 자체", SECTIONS[7])

    def test_the_fact_keys_and_the_verification_keys_are_listed(self):
        rows = table_rows(SECTIONS[6][SECTIONS[6].index("확인에 쓰는 값"):])
        self.assertEqual(tuple(row[0].strip("`") for row in rows), mp.FACT_KEYS)
        for key in mp.VERIFICATION_KEYS:
            self.assertIn("`" + key + "`", SECTIONS[6])

    def test_the_merge_methods_are_listed(self):
        for word in (mp.ALLOWED_MERGE_METHOD,) + mp.FORBIDDEN_MERGE_METHODS:
            self.assertIn("`" + word + "`", SECTIONS[8])

    def test_the_declared_items_are_named_in_the_operators_words(self):
        for code in mp.DECLARED_REQUIRED:
            self.assertIn(dict(mp.OPERATOR_ONLY_ITEMS)[code], subsection("7-3"))

    def test_the_approval_example_and_guidance_are_the_modules(self):
        self.assertEqual(mp.APPROVAL_EXAMPLE, "M075 승인")
        self.assertIn(mp.AI_MERGE_OFF_NOTICE, DOC)
        self.assertIn(mp.AI_MERGE_ON_NOTICE, DOC)
        sentence = "병합 승인은 병합 번호와 함께 한 줄로 M075 승인 처럼 보내 주세요."
        self.assertIn(sentence, mp.check_approval_text("확인했습니다").guidance.replace("`", ""))
        self.assertIn(sentence, DOC.replace("`", ""))


class OperatorStatementsPinnedTest(unittest.TestCase):
    """운영자 결정의 문장 단위 약속이 문서에서 빠지지 않았다 — 낱말만이 아니라 약속(누가·무엇을·언제)을 못박는다."""

    PINS = (
        (2, "독자 판단 자동 병합이 아닙니다"),
        (2, "전문용어가 아니라 사용자가 체감할 변화 중심으로"),
        (5, "같은 승인으로 다른 PR 을 병합하거나"),
        (5, "새 커밋이 더해지거나 변경 파일 목록이 달라지거나 번호가 맞지 않으면 기존 승인은 **무효**"),
        (5, "새 설명과 새 승인을 받아야 합니다"),
        (6, "빠진 값은 실패"),
        (6, "하나라도 실패하면 병합하지 않고"),
        (7, "12항목에 하나도 안 걸리고"),
        (7, "선언이 거짓이어도 운영자 전용"),
        (7, "12항목 목록을 넓힌 것이 아니라 **12항목 밖의 표시**"),
        (7, "운영자 결정 D-347 의 보수적 판단(총괄 11-15)"),
        (7, "**시험 폴더도 면제하지 않습니다.**"),
        (7, "**예시 주소는 걸리지 않습니다**"),
        (7, "바뀐 파일이 **모두** 시험·문서일 때만 건너뜁니다"),
        (7, "루프백(`localhost`)은 걸립니다"),
        (8, "운영자 PC 의 Git 자격 증명"),
        (8, "강제 push"),
        (9, "추가 변경을 자동 병합하지 않습니다"),
        (9, "되돌리기 위한 요청과 쉬운 원인 설명을 **먼저**"),
        (10, "**즉시 중지 규칙:** 문제가 한 건이라도 발생하면 AI 병합을 **즉시 중지**하고"),
        (10, "기존 운영자 직접 병합 방식으로 돌아갑니다"),
        (11, "워크플로 파일(`.github/`)"),
        (12, "운영자 결정으로만"),
    )

    def test_the_conservative_judgement_is_attributed_where_the_two_flags_are_introduced(self):
        phrase = "운영자 결정 D-347 의 보수적 판단(총괄 11-15)"
        self.assertGreaterEqual(SECTIONS[7].count(phrase), 3)
        self.assertIn(phrase, subsection("7-6").split("\n")[0])
        for code in ("safety_guard", "external_connection"):
            rows = [line for line in subsection("7-5").split("\n") if line.startswith("| `" + code + "`")]
            self.assertEqual(len(rows), 1, code)
            self.assertIn(phrase, rows[0])

    def test_each_promise_is_in_its_section(self):
        for number, phrase in self.PINS:
            with self.subTest(section=number, phrase=phrase):
                self.assertIn(phrase, SECTIONS[number])

    def test_the_design_memo_names_the_constraints_of_the_workflow_way(self):
        memo = subsection("11-2")
        for phrase in ("AI 세션은 병합 자격 증명을 갖지 않습니다", "승인 시점의 머리 SHA", "후속 워크플로", "`workflow_dispatch`", "소유자 계정의 글에서만", "기본 가지의 것만 실행하고 PR 쪽 파일은 읽기만",
                       "병합된 PR 이력", "트리 해시", "확인 필요"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, memo)


class ExamplesMatchCodeTest(unittest.TestCase):
    EXPLANATION = mp.render_explanation("M075", 198, "a1b2c3d" + "0" * 33, ["src/chanceblog_desktop/content/drafts_store.py", "tests/test_drafts_store.py"], *ANSWERS)
    NOTICE = mp.render_completion_notice("M075", 198, "e4f5a6b8c9d0e1f2a3b4c5d6e7f8091a2b3c4d5e", "저장 버튼과 저장된 초안 목록이 앱에 반영되었습니다.", "전체 통과", "이상 없음",
                                         "병합 커밋 한 개를 되돌리는 PR 을 만들어 운영자께 보냅니다.")

    def block(self, text):
        found = re.findall(r"```text\n(.*?)```", text, re.S)
        self.assertEqual(len(found), 1)
        return found[0]

    def test_the_explanation_example_is_exactly_what_the_module_renders_and_passes_its_own_check(self):
        example = self.block(subsection("4-2"))
        self.assertEqual(example, self.EXPLANATION)
        self.assertEqual(mp.explanation_problems(example, pr_title="[M075] 초안 저장 기능"), [])
        for answer in ANSWERS:
            self.assertIn(answer, example)
        for label in OPERATOR_ONLY_12:
            self.assertIn("- " + label + ": 아니오", example)

    def test_the_notice_example_is_exactly_what_the_module_renders_and_passes_its_own_check(self):
        example = self.block(SECTIONS[9])
        self.assertEqual(example, self.NOTICE)
        self.assertEqual(mp.completion_notice_problems(example), [])
        for item in COMPLETION_7:
            self.assertIn(item + ": ", example)

    def test_the_example_numbers_are_consistent(self):
        text = self.block(subsection("4-2"))
        self.assertEqual(text.split("\n")[0], "병합 요청 M075")
        self.assertIn("승인 예: M075 승인", text)
        self.assertEqual(mp.parse_approval("M075 승인"), "M075")


class CorrespondenceTableTest(unittest.TestCase):
    def rows(self):
        start = DOC.index("### 코드와 시험의 대응")
        return table_rows(DOC[start:])

    def test_every_name_in_the_table_exists(self):
        test_source = TEST_PATHS[0].read_text(encoding="utf-8")
        rows = self.rows()
        self.assertEqual(len(rows), 12)
        for policy, section, code, tests in rows:
            with self.subTest(policy=policy):
                number = re.fullmatch(r"§(\d+)", section)
                self.assertIsNotNone(number, section)
                self.assertIn(int(number.group(1)), SECTIONS)
                for name in re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", code):
                    self.assertTrue(hasattr(mp, name), name)
                names = re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", tests)
                self.assertTrue(names, tests)
                for name in names:
                    self.assertIn("class " + name + "(", test_source, name)

    def test_the_table_covers_every_test_class_of_the_policy_tests(self):
        tree = ast.parse(TEST_PATHS[0].read_text(encoding="utf-8"))
        classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
        listed = set()
        for _policy, _section, _code, tests in self.rows():
            listed |= set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", tests))
        self.assertEqual(listed, classes)

    def test_every_public_function_of_the_module_is_in_the_document(self):
        tree = ast.parse(MODULE_SOURCE)
        public = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and not node.name.startswith("_")}
        public -= {"ApprovalCheck", "Decision", "Classification", "Failure", "Verdict", "TrialReport"}               # 결과를 담는 값 객체 — 이름은 함수 설명에 따라 나온다
        for name in sorted(public):
            with self.subTest(name=name):
                self.assertIn("`" + name + "`", DOC)


class ModulePurityTest(unittest.TestCase):
    TREE = ast.parse(MODULE_SOURCE)
    BANNED_CALLS = frozenset({"open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals", "vars", "input", "print", "breakpoint", "exit", "quit"})
    BANNED_NAMES = frozenset({"os", "sys", "time", "datetime", "random", "secrets", "socket", "urllib", "subprocess", "pathlib", "shutil", "tempfile", "io", "json", "logging", "threading",
                              "multiprocessing", "importlib", "ctypes", "http", "requests", "ssl", "uuid", "platform", "signal", "asyncio", "builtins"})
    BANNED_ATTRS = frozenset({"write", "write_text", "write_bytes", "read_text", "read_bytes", "open", "environ", "getenv", "putenv", "now", "utcnow", "today", "time", "sleep", "monotonic",
                              "perf_counter", "random", "randint", "choice", "urandom", "uuid4", "urlopen", "urlretrieve", "connect", "system", "popen", "mkdir", "makedirs", "remove",
                              "unlink", "rename", "rmtree", "getcwd", "chdir", "listdir", "glob", "rglob", "iterdir", "walk", "exists", "is_file", "is_dir", "flush", "seek"})

    def test_only_re_and_dataclasses_are_imported(self):
        names = []
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.Import):
                names += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0)
                names.append(node.module)
        self.assertEqual(sorted(names), ["dataclasses", "re"])

    def test_no_io_environment_clock_randomness_or_dynamic_code(self):
        found = []
        for node in ast.walk(self.TREE):
            line = getattr(node, "lineno", 0)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in self.BANNED_CALLS:
                found.append((line, "call", node.func.id))
            if isinstance(node, ast.Name) and node.id in self.BANNED_NAMES:
                found.append((line, "name", node.id))
            if isinstance(node, ast.Attribute) and node.attr in self.BANNED_ATTRS:
                found.append((line, "attribute", node.attr))
            if isinstance(node, (ast.Global, ast.Nonlocal, ast.Await, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Yield, ast.YieldFrom)):
                found.append((line, "statement", type(node).__name__))
        self.assertEqual(found, [])

    def test_importing_the_module_runs_nothing_but_definitions(self):
        for node in self.TREE.body:
            with self.subTest(line=node.lineno):
                if isinstance(node, ast.Expr):
                    self.assertIsInstance(node.value, ast.Constant)                          # 모듈 설명(독스트링)뿐이다
                else:
                    self.assertIsInstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.FunctionDef, ast.ClassDef))

    def test_the_source_has_no_web_address_tilde_local_path_or_secret_shape(self):
        for path in (MODULE_PATH,) + TEST_PATHS:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn(chr(126), text)
                self.assertIsNone(URL_RX.search(text))
                self.assertNotIn("SDI" + "_USER", text)
                self.assertNotRegex(text, r"[A-Za-z]:(?:/|\\)[A-Za-z0-9_.-]{2,}")
                self.assertEqual(find_secrets(text), [])
                self.assertIsNone(re.search("[" + "".join(chr(code) for code in (0x08, 0x0B, 0x0C)) + "]", text))


class NotWiredTest(unittest.TestCase):
    """지금은 꺼져 있다 — 아무도 이 모듈을 부르지 않는다. 켜는 변경이 연결을 더할 때 이 시험도 같이 고쳐야 하고, 그 변경은 운영자가 직접 병합한다."""

    ALLOWED = {"pipeline/merge_policy.py", "tests/test_merge_policy.py", "tests/test_merge_policy_docs.py"}

    def scan_targets(self):
        files = [path for pattern in ("*.py", "*.json", "*.yml", "*.yaml", "*.toml", "*.cfg") for path in ROOT.glob(pattern)]
        for base in ("pipeline", "scripts", "tests", ".github"):
            files += [path for pattern in ("*.py", "*.yml", "*.yaml", "*.json", "*.sh", "*.toml", "*.txt", "*.cfg") for path in (ROOT / base).rglob(pattern)]
        return sorted(set(files))

    def test_nobody_outside_the_policy_files_names_the_module(self):
        targets = self.scan_targets()
        self.assertGreater(len(targets), 100)
        named = [path.relative_to(ROOT).as_posix() for path in targets if "merge_policy" in path.read_text(encoding="utf-8", errors="replace")]
        self.assertEqual(sorted(set(named) - self.ALLOWED), [])
        self.assertEqual(set(named), self.ALLOWED)

    def test_no_workflow_or_script_mentions_the_policy_modules_functions(self):
        names = ("parse_approval", "check_preconditions", "classify_change", "evaluate_trial", "merge_method_allowed", "ApprovalLedger")
        for path in self.scan_targets():
            rel = path.relative_to(ROOT).as_posix()
            if rel in self.ALLOWED:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            with self.subTest(path=rel):
                self.assertFalse(any(name in text for name in names), rel)

    def test_the_policy_is_not_wired_to_the_operator_loop_or_the_validator(self):
        for rel in ("pipeline/operator_loop.py", "scripts/validate_repo.py", "pipeline/notify.py"):
            self.assertNotIn("merge_policy", (ROOT / rel).read_text(encoding="utf-8"), rel)


class DefectRegisterTest(unittest.TestCase):
    def rows(self):
        return {match.group(1): match.group(0) for match in re.finditer(r"(?m)^\| \*\*(D-34[67])\*\* \|.*$", REGISTER)}

    def test_the_two_rows_exist_with_six_columns(self):
        rows = self.rows()
        self.assertEqual(sorted(rows), ["D-346", "D-347"])
        for name, row in rows.items():
            with self.subTest(row=name):
                self.assertEqual(row.count("|"), 7)

    def test_d346_records_the_policy_work_and_that_it_is_off(self):
        row = self.rows()["D-346"]
        for word in ("docs/AI_MERGE_POLICY.md", "pipeline/merge_policy.py", "tests/test_merge_policy.py", "tests/test_merge_policy_docs.py", "확인 016", "꺼져 있음", "별도 병합 요청", "운영자가 직접 병합",
                     "더 보수적으로", "**해결**"):
            self.assertIn(word, row)
        self.assertIn("main 직접 push 금지", row)

    def test_d347_lists_the_seven_conservative_readings_and_records_the_conservative_judgement(self):
        """처음에는 열림(운영자 판단 필요)이었고, 총괄의 보수적 판단(2026-11-15)으로 해결로 바뀌었다 — 승인 문구는 엄격하게 유지."""
        row = self.rows()["D-347"]
        for mark in ("①", "②", "③", "④", "⑤", "⑥", "⑦"):
            self.assertIn(mark, row)
        self.assertIn("**해결**(보수적 판단 — 총괄 2026-11-15", row)
        self.assertNotIn("**열림**", row)
        for word in ("policy_self", "packaging_release", "invalid_input", "safety_guard", "external_connection", "승인 문구는 엄격하게 유지한다", "ClassifySafetyGuardTest",
                     "ClassifyExternalConnectionTest", "§7-7"):
            self.assertIn(word, row)


class NewTestsAreOfflineTest(unittest.TestCase):
    def test_the_new_tests_do_not_touch_the_network_or_write_files(self):
        for path in TEST_PATHS:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            with self.subTest(path=path.name):
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                        for module in modules:
                            self.assertNotIn(module.split(".")[0], {"urllib", "socket", "requests", "http", "ssl", "subprocess", "shutil", "tempfile", "smtplib", "ftplib"}, module)
                    if isinstance(node, ast.Call):
                        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                        self.assertNotIn(name, {"urlopen", "create_connection", "getaddrinfo", "write_text", "write_bytes", "mkdir", "unlink", "rmtree", "open", "system", "Popen", "run"}, name)


if __name__ == "__main__":
    unittest.main()
