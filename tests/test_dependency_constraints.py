"""설치 버전 묶기(constraints) — 검증기 DEP-3 과 새 파일 `constraints-py310.txt`·`constraints-py312.txt`(결함 D-461–D-465·D-481–D-484, 문서 docs/DEPENDENCY_PINNING.md).

요구 파일 셋(`requirements-dev/edits/pipeline.txt`)은 범위 표기(`>=2,<3`)를 그대로 두고, 워크플로의 모든 `pip install` 이 파이썬 버전별 constraints 파일로 설치 버전을 묶는다.
이 시험은 (1) 진짜 파일 — constraints 두 파일의 모양과 요구 파일과의 짝, 워크플로 열 곳의 설치 줄, (2) 검증기 DEP-3 이 진짜 저장소에서 오류 0 이고
(3) 진짜 파일을 임시 폴더로 복사해 한 곳씩 틀리게 하면(변이) 모두 검증기 오류로 잡히는지, (4) 범위 비교·줄 읽기·셸 줄 읽기(pip 하위 명령·붙여 쓴 -mpip)의 작은 규칙,
(5) 숨은 설치 읽기가 옛 정규식과 같은 판정을 긴 반복 입력에도 글 길이에 비례하는 시간에 내는지(결함 D-481·D-482), (6) 문서가 코드와 같은 말을 하는지(한계 문단이 말한 모양이 정말 그렇게 읽히는지 포함)를 본다.
워크플로를 읽는 시험은 PyYAML 이 있어야 돈다(없는 환경에서는 건너뜀 — requirements-dev.txt 가 CI 에 설치한다)."""
import itertools
import random
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover - requirements-dev.txt 가 설치하는 의존성
    yaml = None

ROOT = Path(_bootstrap.ROOT)
NEEDS_YAML = unittest.skipUnless(yaml is not None, "PyYAML(requirements-dev.txt)이 필요합니다(CI 에서는 항상 실행됩니다)")
CONSTRAINT_FILES = ("constraints-py310.txt", "constraints-py312.txt")
REQUIREMENT_FILES = ("requirements-dev.txt", "requirements-edits.txt", "requirements-pipeline.txt")

# 이 시험이 독립적으로 쓰는 줄 모양(검증기의 정규식을 빌리지 않는다 — 같은 실수를 같이 하지 않게)
PIN_LINE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*==[0-9][0-9A-Za-z.]*")


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def text_of(rel):
    return (ROOT / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")


def pins_of(rel):
    """constraints 파일의 {정규화 이름: 버전} — 주석·빈 줄을 뺀 줄 전부(모양이 틀리면 이 함수가 아니라 모양 시험이 잡는다)."""
    found = {}
    for line in text_of(rel).split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            name, _, version = line.partition("==")
            found[normalize(name)] = version
    return found


def requirement_lines(rel):
    """요구 파일의 (이름, 범위 글) 목록 — `>=A,<B` 와 `==V` 두 모양만 이 시험이 읽는다."""
    found = []
    for line in text_of(rel).split("\n"):
        line = line.split("#")[0].strip()
        if line:
            match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)(.*)", line)
            found.append((match.group(1), match.group(2).strip()))
    return found


def dotted(version):
    """`2.34.0` → (2, 34, 0) — 뒤를 0 으로 채워 길이가 다른 버전(`2` 와 `2.0.0`)도 비교할 수 있게."""
    numbers = [int(part) for part in version.split(".")]
    return tuple(numbers + [0] * (8 - len(numbers)))


def one_plain_line(test, finding):
    for text in (finding.message, finding.line()):
        test.assertEqual(len(text.splitlines()), 1, text)
        test.assertNotIn("::", text)
        test.assertNotIn("##[", text)


# ----------------------------------------------------------------------------
# 1) 진짜 constraints 두 파일
# ----------------------------------------------------------------------------
class ConstraintsFilesTest(unittest.TestCase):
    def test_both_files_exist_at_the_repository_root_next_to_the_requirement_files(self):
        for rel in CONSTRAINT_FILES + REQUIREMENT_FILES:
            with self.subTest(rel=rel):
                self.assertTrue((ROOT / rel).is_file(), rel)

    def test_every_line_is_a_comment_or_name_equals_exact_version_and_no_name_repeats(self):
        for rel in CONSTRAINT_FILES:
            with self.subTest(rel=rel):
                names = []
                for number, line in enumerate(text_of(rel).split("\n"), 1):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    self.assertIsNotNone(PIN_LINE.fullmatch(stripped), f"{rel}:{number}")
                    self.assertNotIn(" ", stripped, f"{rel}:{number}")
                    names.append(normalize(stripped.split("==")[0]))
                self.assertGreaterEqual(len(names), 30, rel)               # 빈 파일로 통과하지 않게(직접 요구 + 하위 의존성 36–37개)
                self.assertEqual(sorted(name for name in names if names.count(name) > 1), [], rel)

    def test_the_header_is_comments_only_and_names_the_python_version_the_file_is_for(self):
        for rel, dotted in (("constraints-py310.txt", "3.10"), ("constraints-py312.txt", "3.12")):
            with self.subTest(rel=rel):
                lines = text_of(rel).split("\n")
                head = []
                for line in lines:
                    if not line.startswith("#"):
                        break
                    head.append(line)
                self.assertGreaterEqual(len(head), 3, rel)
                self.assertIn(f"파이썬 {dotted}", head[0], rel)             # 두 파일이 바뀌어 들어가는 것을 막는다
                joined = "\n".join(head)
                for word in ("만든 방법", f"pip install -c {rel} -r", "docs/DEPENDENCY_PINNING.md"):
                    self.assertIn(word, joined, (rel, word))
                self.assertRegex(joined, r"20[0-9]{2}-[0-9]{2}-[0-9]{2}")             # 만든 날짜(갱신할 때마다 바뀌므로 값은 못박지 않는다)
                self.assertRegex(joined, r"전체 시험 [0-9,]+개")                       # 통과한 전체 시험 개수

    def test_the_files_have_no_web_addresses_tildes_braces_or_secret_or_personal_looking_text(self):
        """(이름을 본 것에 맞췄다 — 독립 검증 Q 의 N11: 옛 이름은 비밀·개인 정보를 본다고 했지만 주소·물결표·이중 중괄호만 봤다. 지금은 메일·계정 이름 꼴(@)·윈도 경로(백슬래시)·키처럼 긴 글자 덩어리도 본다.)"""
        for rel in CONSTRAINT_FILES:
            text = text_of(rel)
            self.assertNotIn("://", text, rel)                              # 웹 주소 없음(패키지 이름 httpx·httpcore 의 'http' 는 주소가 아니다)
            self.assertNotIn("~", text, rel)
            self.assertNotIn("{{", text, rel)
            self.assertNotIn("@", text, rel)
            self.assertNotIn(chr(92), text, rel)
            self.assertIsNone(re.search(r"[A-Za-z0-9+/=_-]{32,}", text), rel)

    def test_every_requirement_package_is_pinned_in_both_files_inside_the_requirement_range(self):
        for requirement in REQUIREMENT_FILES:
            for name, spec in requirement_lines(requirement):
                for constraints in CONSTRAINT_FILES:
                    with self.subTest(requirement=requirement, name=name, constraints=constraints):
                        pinned = pins_of(constraints).get(normalize(name))
                        exact = re.fullmatch(r"==([0-9][0-9.]*)", spec)
                        if exact and pinned is None:
                            continue                                        # 요구 파일이 이미 `==` 로 고정한 줄(actionlint-py)은 목록에 없어도 된다
                        self.assertIsNotNone(pinned, f"{name} 이(가) {constraints} 에 없다")
                        if exact:
                            self.assertEqual(pinned, exact.group(1))
                            continue
                        window = re.fullmatch(r">=([0-9][0-9.]*),<([0-9][0-9.]*)", spec)
                        if window is None:              # 이 시험이 따로 읽는 모양(>=A,<B)이 아니면 검증기의 비교로 본다(새 요구가 다른 모양이어도 이 시험이 막지 않게)
                            self.assertIs(vr._dep3_allowed(pinned, spec), True, f"{name}=={pinned} 가 {spec} 밖")
                            continue
                        self.assertTrue(dotted(window.group(1)) <= dotted(pinned) < dotted(window.group(2)), f"{name}=={pinned} 가 {spec} 밖")

    def test_the_direct_requirement_names_are_the_same_in_both_files(self):
        direct = {normalize(name) for requirement in REQUIREMENT_FILES for name, spec in requirement_lines(requirement) if not spec.startswith("==")}
        self.assertGreaterEqual(len(direct), 4)
        for constraints in CONSTRAINT_FILES:
            self.assertEqual(sorted(direct - set(pins_of(constraints))), [], constraints)
        self.assertEqual(sorted(direct & set(pins_of("constraints-py310.txt"))), sorted(direct & set(pins_of("constraints-py312.txt"))))

    def test_the_two_python_versions_keep_their_own_file(self):
        """파이썬 3.10 은 3.11 이상 전용인 google-genai 2.34.0·websockets 17.4 를 받지 못해 파일이 둘이다 — 3.10 용에 그 둘이 들어가면 설치가 깨진다(AP7 조사)."""
        ten = pins_of("constraints-py310.txt")
        self.assertNotEqual(ten["google-genai"], "2.34.0")
        self.assertNotEqual(ten["websockets"], "17.4")

    def test_the_pipeline_requirement_header_says_versions_differ_by_python_and_points_to_the_pinning_doc(self):
        """확인 040 ① 묶음 ④: requirements-pipeline.txt 의 머리 주석은 '3.10/3.12 모두에서 같은 버전으로 풀린다' 는 옛 문장(AP7 실측에서 google-genai 가 파이썬마다 달랐다 — 결함 D-10 행)이 아니라
        '범위 안에서 파이썬별로 다른 버전이 풀릴 수 있어 파이썬별 constraints 파일로 묶는다' 를 말하고 docs/DEPENDENCY_PINNING.md 를 가리킨다. 패키지 줄·범위는 이 시험이 보지 않는다(위의 짝 시험들이 본다)."""
        header = "\n".join(line for line in text_of("requirements-pipeline.txt").split("\n") if line.startswith("#"))
        self.assertNotIn("같은 버전으로 풀리는 것을 확인함", header)
        for needle in ("파이썬별로 다른 버전이 풀릴 수 있어", "constraints", "docs/DEPENDENCY_PINNING.md"):
            self.assertIn(needle, header, needle)
        self.assertTrue((ROOT / "docs" / "DEPENDENCY_PINNING.md").is_file())

    def test_the_site_cleanup_test_lists_both_files_as_deliberately_exposed(self):
        """새 루트 파일은 사이트로 내보낼지·뺄지 정해야 한다(tests/test_site_cleanup.py). `_config.yml` 은 광고 표면이라 이 변경 밖이어서 일부러 열어 두는 목록(STATIC_EXPOSED)에 있다.
        (그 파일들이 AI 병합 대상이 아닌 의존성 파일로 분류되는 것은 병합 정책 문서 시험의 '사이트로 내보내는 모든 파일은 운영자 전용' 시험이 이미 모든 루트 파일에 대해 본다 —
        그 시험이 정책 모듈의 이름을 다른 파일이 부르지 못하게 지키므로 이 모듈은 그 이름을 쓰지 않는다.)"""
        cleanup = text_of("tests/test_site_cleanup.py")
        start = cleanup.index("STATIC_EXPOSED = {")
        block = cleanup[start:cleanup.index("}", start)]
        for rel in CONSTRAINT_FILES:
            self.assertIn(f'"{rel}"', block, rel)
        self.assertIn('"README.md"', block)


# ----------------------------------------------------------------------------
# 2) 진짜 워크플로 열 곳의 설치 줄 — 요구 파일 값은 그대로, `-c` 만 더해졌다
# ----------------------------------------------------------------------------
# (워크플로, job, setup-python 의 python-version, 설치 줄의 pip install 뒤 글자 전체)
INSTALL_LINES = (
    ("blogger.yml", "generate", "3.12", "-c constraints-py312.txt -r requirements-pipeline.txt"),
    ("naver.yml", "generate", "3.12", "-c constraints-py312.txt -r requirements-pipeline.txt"),
    ("tistory.yml", "generate", "3.12", "-c constraints-py312.txt -r requirements-pipeline.txt"),
    ("issue-edit.yml", "edit", "3.12", "-c constraints-py312.txt -r requirements-edits.txt"),
    ("pr-scope-check.yml", "scope", "3.12", "-c constraints-py312.txt -r requirements-edits.txt"),
    ("sync-issue-form.yml", "sync", "3.12", "-c constraints-py312.txt -r requirements-edits.txt"),
    ("chanceblog.yml", "build", "3.10", '-c constraints-py310.txt "google-genai>=2,<3"'),
    ("chance-fix-images.yml", "build", "3.10", '-c constraints-py310.txt "google-genai>=2,<3"'),
    ("chance-shadow.yml", "shadow", "3.10", '-c constraints-py310.txt "google-genai>=2,<3"'),
)


def load_workflow(name):
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_bytes().decode("utf-8"))


@NEEDS_YAML
class WorkflowInstallLinesTest(unittest.TestCase):
    def install_runs(self, workflow, job):
        """job 의 pip install 줄(`--upgrade pip` 줄은 뺀다)을 run 안의 글 그대로 모은다."""
        found = []
        for step in load_workflow(workflow)["jobs"][job]["steps"]:
            for line in str(step.get("run", "")).split("\n"):
                text = line.strip()
                if re.search(r"\bpip3? install\b", text) and "--upgrade pip" not in text:
                    found.append(text)
        return found

    def python_of(self, workflow, job):
        versions = [step["with"]["python-version"] for step in load_workflow(workflow)["jobs"][job]["steps"] if str(step.get("uses", "")).startswith("actions/setup-python@")]
        self.assertEqual(len(versions), 1, (workflow, job))
        return versions[0]

    def test_nine_install_lines_carry_the_constraints_file_of_their_python(self):
        for workflow, job, python, tail in INSTALL_LINES:
            with self.subTest(workflow=workflow):
                self.assertEqual(self.python_of(workflow, job), python)
                lines = self.install_runs(workflow, job)
                self.assertEqual(len(lines), 1, (workflow, lines))
                self.assertRegex(lines[0], r"^(?:python -m )?pip install " + re.escape(tail) + r"$")
                self.assertIn("constraints-py" + python.replace(".", ""), lines[0])      # 3.10 ↔ py310, 3.12 ↔ py312

    def test_the_upgrade_pip_lines_were_left_alone(self):
        """`pip install --upgrade pip` 은 이 변경 밖이다 — -c 도 붙지 않았다."""
        for workflow, job, _python, _tail in INSTALL_LINES:
            for step in load_workflow(workflow)["jobs"][job]["steps"]:
                for line in str(step.get("run", "")).split("\n"):
                    if "--upgrade pip" in line:
                        with self.subTest(workflow=workflow):
                            self.assertEqual(line.strip(), "python -m pip install --upgrade pip")

    def test_the_chance_workflows_install_the_same_way(self):
        lines = {workflow: self.install_runs(workflow, job) for workflow, job, _python, _tail in INSTALL_LINES if workflow.startswith("chance")}
        self.assertEqual(len(lines), 3)
        self.assertEqual(len({tuple(value) for value in lines.values()}), 1)

    def test_the_guardrails_matrix_picks_the_file_of_each_python_with_an_env_variable_and_no_expression_in_run(self):
        job = load_workflow("guardrails.yml")["jobs"]["validate"]
        self.assertEqual(job["strategy"]["matrix"]["python-version"], ["3.10", "3.12"])
        install = next(step for step in job["steps"] if step.get("name") == "검증 도구 설치")
        self.assertEqual(install["env"], {"CONSTRAINTS": "constraints-py${{ matrix.python-version == '3.10' && '310' || '312' }}.txt"})
        self.assertEqual(install["run"], 'python -m pip install -c "$CONSTRAINTS" -r requirements-dev.txt')
        self.assertNotIn("${{", install["run"])                        # 식은 env 안에만 둔다(검증기 WF-4)
        self.assertEqual(sorted(install), ["env", "name", "run"])      # 이 단계에 다른 키(if·permissions·uses)를 얹지 않았다
        python = {"versions": job["strategy"]["matrix"]["python-version"], "key": "python-version"}
        targets, why = vr._dep3_constraint_targets("$CONSTRAINTS", install["env"], python)
        self.assertIsNone(why)
        self.assertEqual(targets, {"3.10": "constraints-py310.txt", "3.12": "constraints-py312.txt"})

    def test_no_workflow_installs_anything_without_a_constraints_file(self):
        """모든 워크플로의 모든 run 의 pip install 이 (pip 자신만 올리는 줄을 빼고) -c 를 가진다 — 검증기와 따로 글자로 센다."""
        checked = 0
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            for job in (yaml.safe_load(path.read_bytes().decode("utf-8")).get("jobs") or {}).values():
                for step in job.get("steps") or []:
                    for line in str(step.get("run", "")).split("\n"):
                        if re.search(r"\bpip3? install\b", line) and "--upgrade pip" not in line:
                            checked += 1
                            self.assertRegex(line, r"\s(?:-c|--constraint)[ =]", f"{path.name}: {line.strip()}")
        self.assertGreaterEqual(checked, 10)


# ----------------------------------------------------------------------------
# 3) DEP-3 — 진짜 저장소는 오류 0, 진짜 파일을 한 곳씩 틀리게 하면 모두 오류
# ----------------------------------------------------------------------------
class Dep3RealRepositoryTest(unittest.TestCase):
    def test_the_real_repository_has_no_dep3_findings(self):
        self.assertEqual([finding.line() for finding in vr.check_dependency_constraints(ROOT, vr.list_files(ROOT))], [])

    def test_the_rule_is_one_of_the_checks_run_checks_calls(self):
        """등록 확인: 진짜 저장소 전체를 돌리면 느리므로(그 오류 0 은 test_validate_repo.RealRepoTest 가 본다) 소스에서 부르는 줄만 확인하고, 실제로 도는지는 아래 임시 폴더 시험이 본다."""
        source = text_of("scripts/validate_repo.py")
        body = source[source.index("def run_checks("):source.index("def main(")]
        self.assertIn("    findings += check_dependency_constraints(root, files)\n", body)
        self.assertLess(body.index("check_dependencies(root, files)"), body.index("check_dependency_constraints(root, files)"))     # DEP-1 바로 뒤

    def test_dep1_does_not_read_the_quoted_constraints_variable_as_an_unpinned_package(self):
        findings = vr.check_dependencies(ROOT, vr.list_files(ROOT))
        self.assertEqual([finding.line() for finding in findings], [])


def copy_sources():
    """임시 복사본에 넣을 진짜 파일의 ({요구 파일 셋·constraints 둘}, {워크플로 전부}) — 각각 {경로: 줄 끝을 LF 로 통일한 바이트}. 한 번만 읽는다(저장소 전체 목록을 매번 읽으면 느리다)."""
    names = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / ".github" / "workflows").glob("*") if path.suffix.lower() in (".yml", ".yaml"))
    read = lambda rel: (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")      # noqa: E731
    return {rel: read(rel) for rel in list(REQUIREMENT_FILES) + list(CONSTRAINT_FILES)}, {rel: read(rel) for rel in names}


FILE_SOURCES, WORKFLOW_SOURCES = copy_sources()


class TmpCase(unittest.TestCase):
    def setUp(self):
        """새 임시 폴더에 요구 파일 셋·constraints 둘만 복사한다(워크플로는 `fresh` 로 필요한 것만 — DEP-3 은 있는 워크플로를 모두 읽으므로 적게 둘수록 빠르다)."""
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for rel, data in FILE_SOURCES.items():
            self.write_bytes(rel, data)

    def fresh(self, *workflows):
        """처음부터 다시: 새 임시 폴더에 요구 파일 셋·constraints 둘과 지정한 워크플로(파일 이름)를 복사한다. 이름 대신 `*` 하나면 워크플로 전부."""
        self.setUp()
        wanted = sorted(WORKFLOW_SOURCES) if workflows == ("*",) else [f".github/workflows/{name}" for name in workflows]
        for rel in wanted:
            self.write_bytes(rel, WORKFLOW_SOURCES[rel])

    def write_bytes(self, rel, data):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def edit(self, rel, old, new, count=1):
        """파일에서 옛 글이 정확히 `count` 번 나올 때만 바꾼다(진짜 파일의 모양이 변하면 이 변이 시험이 소리 내어 실패한다)."""
        path = self.root / rel
        text = path.read_bytes().decode("utf-8")
        self.assertEqual(text.count(old), count, f"{rel}: 옛 글 {old!r} 가 {text.count(old)} 번 나온다")
        path.write_bytes(text.replace(old, new).encode("utf-8"))

    def write(self, rel, text):
        self.write_bytes(rel, text.encode("utf-8"))

    def listing(self):
        return sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*") if path.is_file())

    def found(self):
        return vr.check_dependency_constraints(self.root, self.listing())

    def assert_caught(self, path, needle, found=None):
        found = self.found() if found is None else found
        hits = [item for item in found if item.check == "DEP-3" and item.level == "ERROR" and item.path.split(":")[0] == path and needle in item.message]
        self.assertTrue(hits, f"{path}: {needle!r} 를 말하는 DEP-3 오류가 없다 — 있는 것: {[item.line() for item in found]}")
        for item in found:
            one_plain_line(self, item)
        return hits


@NEEDS_YAML
class Dep3WorkflowMutationTest(TmpCase):
    def test_the_untouched_copy_is_clean_so_every_red_below_comes_from_its_own_mutation(self):
        self.fresh("*")
        self.assertGreaterEqual(len(WORKFLOW_SOURCES), 20)                          # 워크플로 전부를 복사했다(빈 복사본으로 통과하지 않게)
        self.assertEqual([item.line() for item in self.found()], [])

    # ① -c 가 없다
    def test_removing_the_constraints_option_from_each_of_the_ten_install_lines_is_caught(self):
        for workflow, _job, _python, tail in INSTALL_LINES:
            with self.subTest(workflow=workflow):
                self.fresh(workflow)
                rel = f".github/workflows/{workflow}"
                option = re.match(r"-c (constraints-py[0-9]+\.txt) ", tail).group(1)
                self.edit(rel, f"-c {option} ", "")
                self.assert_caught(rel, "-c 가 없습니다")
        self.fresh("guardrails.yml")
        self.edit(".github/workflows/guardrails.yml", 'python -m pip install -c "$CONSTRAINTS" -r requirements-dev.txt', "python -m pip install -r requirements-dev.txt")
        self.assert_caught(".github/workflows/guardrails.yml", "-c 가 없습니다")

    # ② 잘못된 파이썬 번호
    def test_a_constraints_file_of_the_wrong_python_is_caught(self):
        for workflow, wrong in (("blogger.yml", "constraints-py310.txt"), ("issue-edit.yml", "constraints-py310.txt"), ("chanceblog.yml", "constraints-py312.txt"), ("chance-shadow.yml", "constraints-py312.txt")):
            with self.subTest(workflow=workflow):
                self.fresh(workflow)
                rel = f".github/workflows/{workflow}"
                right = "constraints-py312.txt" if wrong == "constraints-py310.txt" else "constraints-py310.txt"
                self.edit(rel, f"-c {right}", f"-c {wrong}")
                self.assert_caught(rel, f"{right} 여야 합니다")

    def test_the_guardrails_matrix_must_pick_the_right_file_for_each_python(self):
        rel = ".github/workflows/guardrails.yml"
        self.fresh("guardrails.yml")
        swapped = "constraints-py${{ matrix.python-version == '3.10' && '312' || '310' }}.txt"
        self.edit(rel, "constraints-py${{ matrix.python-version == '3.10' && '310' || '312' }}.txt", swapped)
        found = self.found()
        self.assert_caught(rel, "파이썬 3.10 칸의 -c 가 constraints-py312.txt", found)
        self.assert_caught(rel, "파이썬 3.12 칸의 -c 가 constraints-py310.txt", found)

    def test_a_literal_file_in_the_matrix_job_is_wrong_for_one_of_the_two_pythons(self):
        rel = ".github/workflows/guardrails.yml"
        self.fresh("guardrails.yml")
        self.edit(rel, '-c "$CONSTRAINTS"', "-c constraints-py312.txt")
        self.assert_caught(rel, "파이썬 3.10 칸의 -c 가 constraints-py312.txt")

    def test_a_matrix_expression_over_another_matrix_key_is_not_trusted(self):
        rel = ".github/workflows/guardrails.yml"
        self.fresh("guardrails.yml")
        self.edit(rel, "matrix.python-version == '3.10' && '310'", "matrix.os == 'x' && '310'")
        self.assert_caught(rel, "matrix 키와 다릅니다")

    def test_an_expression_shape_the_validator_does_not_read_is_an_error_not_a_pass(self):
        rel = ".github/workflows/guardrails.yml"
        self.fresh("guardrails.yml")
        self.edit(rel, "matrix.python-version == '3.10' && '310' || '312'", "matrix.python-version != '3.10' && '312' || '310'")
        self.assert_caught(rel, "지원하지 않는 모양")

    def test_the_variable_must_be_defined_in_an_env_the_step_can_see(self):
        rel = ".github/workflows/guardrails.yml"
        self.fresh("guardrails.yml")
        self.edit(rel, '-c "$CONSTRAINTS"', '-c "$NOPE"')
        self.assert_caught(rel, "env 에 없습니다")

    def test_an_env_defined_at_job_or_workflow_level_is_read_too_and_the_step_value_wins(self):
        rel = ".github/workflows/blogger.yml"
        self.fresh("blogger.yml")
        self.edit(rel, "-c constraints-py312.txt -r requirements-pipeline.txt", '-c "$FILE" -r requirements-pipeline.txt')
        self.assert_caught(rel, "env 에 없습니다")                                  # 어디에도 정의가 없다
        self.edit(rel, "\npermissions:\n  contents: read\n", "\nenv:\n  FILE: constraints-py312.txt\npermissions:\n  contents: read\n")
        self.assertEqual([item.line() for item in self.found()], [])               # 워크플로 env
        self.edit(rel, "      DRY_RUN: ${{ inputs.dry_run && 'true' || 'false' }}\n", "      DRY_RUN: ${{ inputs.dry_run && 'true' || 'false' }}\n      FILE: constraints-py310.txt\n")
        self.assert_caught(rel, "constraints-py312.txt 여야 합니다")              # job env 가 워크플로 env 를 덮어써 틀린 번호가 됐다
        self.edit(rel, "      - name: 의존성 설치\n        run: |\n", "      - name: 의존성 설치\n        env:\n          FILE: constraints-py312.txt\n        run: |\n")
        self.assertEqual([item.line() for item in self.found()], [])               # 단계 env 가 job env 를 덮어써 다시 맞다

    def test_the_file_named_by_c_must_exist(self):
        rel = ".github/workflows/blogger.yml"
        self.fresh("blogger.yml")
        (self.root / "constraints-py312.txt").unlink()
        self.assert_caught(rel, "constraints-py312.txt 가 저장소에 없습니다")

    def test_only_the_upgrade_pip_line_having_the_option_does_not_count(self):
        """-c 가 `--upgrade pip` 줄에만 있고 요구 파일을 설치하는 줄에는 없다."""
        rel = ".github/workflows/blogger.yml"
        self.fresh("blogger.yml")
        self.edit(rel, "          python -m pip install --upgrade pip\n          python -m pip install -c constraints-py312.txt -r requirements-pipeline.txt\n",
                  "          python -m pip install -c constraints-py312.txt --upgrade pip\n          python -m pip install -r requirements-pipeline.txt\n")
        self.assert_caught(rel, "-c 가 없습니다")

    def test_a_package_install_on_the_upgrade_line_needs_the_option_too(self):
        rel = ".github/workflows/blogger.yml"
        self.fresh("blogger.yml")
        self.edit(rel, "          python -m pip install --upgrade pip\n", "          python -m pip install --upgrade pip wheel\n")
        self.assert_caught(rel, "-c 가 없습니다")

    def test_the_pip_only_install_lines_need_no_option(self):
        rel = ".github/workflows/blogger.yml"
        self.fresh("blogger.yml")
        self.edit(rel, "          python -m pip install --upgrade pip\n", "          python -m pip install --upgrade pip\n          python -m pip install -U \"pip>=24\"\n")
        self.assertEqual([item.line() for item in self.found()], [])

    # 단계가 쓰는 파이썬을 알 수 없는 모양
    def test_a_job_without_setup_python_cannot_be_matched_to_a_constraints_file(self):
        rel = ".github/workflows/issue-edit.yml"
        self.fresh("issue-edit.yml")
        text = (self.root / rel).read_bytes().decode("utf-8")
        start = text.index("      - uses: actions/setup-python@v6")
        end = text.index("\n\n", start) + 2
        self.edit(rel, text[start:end], "")
        self.assert_caught(rel, "파이썬을 알 수 없어")

    def test_an_unquoted_python_version_is_not_read(self):
        rel = ".github/workflows/issue-edit.yml"
        self.fresh("issue-edit.yml")
        self.edit(rel, "python-version: '3.12'", "python-version: 3.12")
        self.assert_caught(rel, "따옴표")

    def test_a_python_version_from_somewhere_other_than_a_literal_or_a_matrix_list_is_not_read(self):
        rel = ".github/workflows/issue-edit.yml"
        self.fresh("issue-edit.yml")
        self.edit(rel, "python-version: '3.12'", "python-version: ${{ vars.PY }}")
        self.assert_caught(rel, "파이썬을 알 수 없어")

    def test_a_matrix_python_list_with_an_unquoted_number_is_not_read(self):
        rel = ".github/workflows/guardrails.yml"
        self.fresh("guardrails.yml")
        self.edit(rel, "python-version: ['3.10', '3.12']", "python-version: [3.10, '3.12']")
        self.assert_caught(rel, "따옴표")

    def test_a_python_without_a_constraints_file_is_caught_when_a_matrix_adds_it(self):
        rel = ".github/workflows/guardrails.yml"
        self.fresh("guardrails.yml")
        self.edit(rel, "python-version: ['3.10', '3.12']", "python-version: ['3.10', '3.11', '3.12']")
        found = self.found()
        self.assert_caught(rel, "파이썬 3.11 칸의 -c 가 constraints-py312.txt", found)       # 식은 3.10 이 아니면 312 로 읽힌다 — 3.11 은 틀린 파일이다

    def test_the_pip_install_input_of_setup_python_would_bypass_the_rule_so_it_is_refused(self):
        rel = ".github/workflows/issue-edit.yml"
        self.fresh("issue-edit.yml")
        self.edit(rel, "python-version: '3.12'", "python-version: '3.12'\n          pip-install: -r requirements-edits.txt")
        self.assert_caught(rel, "pip-install")

    # 읽지 못하는 설치 모양은 통과가 아니라 오류
    def test_installs_hidden_in_a_nested_shell_or_eval_are_errors(self):
        rel = ".github/workflows/issue-edit.yml"
        for hidden in ('bash -c "python -m pip install -r requirements-edits.txt"', 'eval "pip install pyyaml"', "xargs pip install < list.txt", "uv pip install pyyaml"):
            with self.subTest(hidden=hidden):
                self.fresh("issue-edit.yml")
                self.edit(rel, "python -m pip install -c constraints-py312.txt -r requirements-edits.txt", hidden)
                self.assert_caught(rel, "읽지 못하는 모양")

    # 값을 받는 전역 옵션이 install 앞에 오는 모양(결함 D-481)과 붙여 쓴 -mpip — 진짜 워크플로의 설치 줄을 바꿔서
    def test_global_pip_options_before_install_do_not_hide_the_install(self):
        """`pip --cache-dir cache install …` 처럼 값을 받는 전역 옵션이 install 앞에 오면 그 값(`cache`·`list` 같은 하위 명령 낱말)이 하위 명령으로 읽혀 설치를 놓쳤다(안전 검증 S 의 R1)."""
        rel = ".github/workflows/issue-edit.yml"
        old = "python -m pip install -c constraints-py312.txt -r requirements-edits.txt"
        for text in ("python -m pip --cache-dir cache install -r requirements-edits.txt", "python -m pip --log list install -r requirements-edits.txt", "pip --cache-dir cache install -r requirements-edits.txt",
                     "python -m pip --proxy check install -r requirements-edits.txt", "pip --python show install -r requirements-edits.txt", "python -m pip --cache-dir cache --log list install -r requirements-edits.txt",
                     "python -m pip --cache cache install -r requirements-edits.txt", "pip --log-f list --pro check install -r requirements-edits.txt",
                     "python -mpip install -r requirements-edits.txt", "python3 -X utf8 -mpip install -r requirements-edits.txt"):
            with self.subTest(text=text):
                self.fresh("issue-edit.yml")
                self.edit(rel, old, text)
                self.assert_caught(rel, "-c 가 없습니다")
                self.edit(rel, text, text.replace(" install ", " install -c constraints-py312.txt ", 1))
                self.assertEqual([item.line() for item in self.found()], [])        # -c 를 붙이면 같은 모양이 통과한다 — 모양 자체를 거절하는 것이 아니다

    HEAD = ("name: w\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: actions/setup-python@v6\n        with:\n          python-version: '3.12'\n")

    def test_hostile_step_and_job_names_cannot_forge_a_workflow_command_in_an_error(self):
        """오류 문구의 단계 이름·job 이름도 저장소 글이다 — 줄바꿈·`::` 를 넣어도 한 줄이고 명령으로 읽히지 않는다(독립 검증 Q 의 살아남은 변이 Q18)."""
        self.fresh()
        self.write(".github/workflows/w.yml",
                   'name: w\non: push\njobs:\n  "j\\n::error::job":\n    runs-on: ubuntu-latest\n    steps:\n'
                   "      - uses: actions/setup-python@v6\n        with:\n          python-version: '3.12'\n"
                   '      - name: "a\\n::error::step"\n        run: python -m pip install -r requirements-edits.txt\n')
        found = self.found()
        hits = self.assert_caught(".github/workflows/w.yml", "-c 가 없습니다", found)          # 모든 오류가 한 줄·`::` 없음은 assert_caught 가 본다
        self.assertIn("error", hits[0].message)                                                   # 이름의 글자는 남고(무력화만 됨)

    def test_the_nearest_setup_python_before_the_install_decides_the_python(self):
        """한 job 에 setup-python 이 둘이면 설치 줄 바로 앞의 것이 파이썬이다(독립 검증 Q 의 살아남은 변이 Q28)."""
        head = self.HEAD.replace("python-version: '3.12'", "python-version: '3.10'") + "      - uses: actions/setup-python@v6\n        with:\n          python-version: '3.12'\n"
        self.fresh()
        self.write(".github/workflows/w.yml", head + "      - run: python -m pip install -c constraints-py312.txt -r requirements-edits.txt\n")
        self.assertEqual([item.line() for item in self.found()], [])
        self.write(".github/workflows/w.yml", head + "      - run: python -m pip install -c constraints-py310.txt -r requirements-edits.txt\n")
        self.assert_caught(".github/workflows/w.yml", "constraints-py312.txt 여야 합니다")

    def test_a_requirement_file_with_any_name_that_an_install_line_points_to_is_checked_too(self):
        """설치 줄이 -r 로 가리킨 파일은 이름이 requirements*.txt 가 아니어도 ④ 의 대상이다(독립 검증 Q 의 살아남은 변이 Q29)."""
        self.fresh()
        self.write("deps.txt", "rich>=13,<14\n")
        self.write(".github/workflows/w.yml", self.HEAD + "      - run: python -m pip install -c constraints-py312.txt -r deps.txt\n")
        found = self.found()
        self.assert_caught("deps.txt", "constraints-py310.txt 에 없습니다", found)
        self.assert_caught("deps.txt", "constraints-py312.txt 에 없습니다", found)

    def test_the_two_workflow_level_limits_the_document_names_really_pass(self):
        """§3 '오류도 없이 지나가는 모양' 의 (d) 같은 단계의 스크립트 안에서 -c 변수를 다시 대입하기, (g) bash 가 아닌 shell 안의 pip — 문서가 거짓이 되지 않게 묶는다(막는 변경이 생기면 시험과 문단을 함께 고친다)."""
        self.fresh()
        self.write(".github/workflows/w.yml", self.HEAD + "      - env:\n          CONSTRAINTS: constraints-py312.txt\n        run: |\n          CONSTRAINTS=/dev/null\n"
                                                      '          python -m pip install -c "$CONSTRAINTS" -r requirements-edits.txt\n')
        self.assertEqual([item.line() for item in self.found()], [])
        self.write(".github/workflows/w.yml", self.HEAD + "      - shell: python\n        run: |\n          import subprocess\n          subprocess.run(['pip', 'install', '-r', 'requirements-edits.txt'])\n")
        self.assertEqual([item.line() for item in self.found()], [])

    def test_message_text_that_only_mentions_pip_install_is_not_an_install(self):
        rel = ".github/workflows/issue-edit.yml"
        self.fresh("issue-edit.yml")
        self.edit(rel, "python -m pip install -c constraints-py312.txt -r requirements-edits.txt",
                  'python -m pip install -c constraints-py312.txt -r requirements-edits.txt\n          echo "pip install failed? check the log"\n          git commit -m "docs: pip install note" --allow-empty')
        self.assertEqual([item.line() for item in self.found()], [])

    def test_editable_and_missing_requirement_installs_are_errors(self):
        rel = ".github/workflows/issue-edit.yml"
        self.fresh("issue-edit.yml")
        self.edit(rel, "-c constraints-py312.txt -r requirements-edits.txt", "-c constraints-py312.txt -e .")
        self.assert_caught(rel, "-e")
        self.fresh("issue-edit.yml")
        self.edit(rel, "-r requirements-edits.txt", "-r requirements-nope.txt")
        self.assert_caught(rel, "requirements-nope.txt 이 저장소에 없습니다")

    def test_an_inline_package_must_be_in_the_constraints_of_its_python_inside_its_range(self):
        rel = ".github/workflows/chanceblog.yml"
        self.fresh("chanceblog.yml")
        self.edit(rel, '"google-genai>=2,<3"', '"google-genai>=3,<4"')
        self.assert_caught(rel, "범위")
        self.fresh("chanceblog.yml")
        self.edit(rel, '"google-genai>=2,<3"', '"rich>=13,<14"')
        self.assert_caught(rel, "rich")

    def test_accepted_shapes_of_the_option(self):
        rel = ".github/workflows/issue-edit.yml"
        old = "python -m pip install -c constraints-py312.txt -r requirements-edits.txt"
        for text in ('python -m pip install -c "constraints-py312.txt" -r requirements-edits.txt', "python -m pip install --constraint=constraints-py312.txt -r requirements-edits.txt",
                     "python -m pip install -cconstraints-py312.txt -r requirements-edits.txt", "python -m pip install -r requirements-edits.txt -c constraints-py312.txt",
                     "python -m pip install -c ./constraints-py312.txt --requirement=requirements-edits.txt", "python3 -m pip install -c constraints-py312.txt -r requirements-edits.txt",
                     "pip3 install -c constraints-py312.txt -r requirements-edits.txt", "python -m pip install -c constraints-py312.txt -r requirements-edits.txt 2>&1 | tail -3",
                     "python -m pip install \\\n            -c constraints-py312.txt \\\n            -r requirements-edits.txt",
                     "if true; then python -m pip install -c constraints-py312.txt -r requirements-edits.txt; fi"):
            with self.subTest(text=text):
                self.fresh("issue-edit.yml")
                self.edit(rel, old, text)
                self.assertEqual([item.line() for item in self.found()], [])
        self.fresh("issue-edit.yml")
        self.edit(rel, old, "python -m pip install \\\n            -r requirements-edits.txt")
        self.assert_caught(rel, "-c 가 없습니다")

    def test_a_duplicate_key_workflow_is_left_to_wf0_without_crashing(self):
        rel = ".github/workflows/issue-edit.yml"
        self.fresh("issue-edit.yml")
        self.edit(rel, "permissions:\n  contents: read\n", "permissions:\n  contents: read\npermissions:\n  contents: read\n")
        self.assertEqual([item.line() for item in self.found() if item.path == rel], [])

    def test_the_rule_is_registered_in_run_checks(self):
        rel = ".github/workflows/blogger.yml"
        self.fresh("blogger.yml")
        self.edit(rel, "-c constraints-py312.txt ", "")
        self.assertIn(("DEP-3", "ERROR"), [(item.check, item.level) for item in vr.run_checks(self.root)])


class Dep3ConstraintsFileMutationTest(TmpCase):
    """constraints 파일과 요구 파일의 변이 — 워크플로를 읽지 않으니 PyYAML 이 없어도 돈다."""

    def test_the_untouched_copy_is_clean(self):
        self.assertEqual([item.line() for item in self.found()], [])

    def test_a_range_mixed_into_a_constraints_line_is_caught(self):
        for operator in (">=", "<=", "~=", "!=", ">", "<"):
            with self.subTest(operator=operator):
                self.setUp()
                self.edit("constraints-py312.txt", "protobuf==7.36.2", f"protobuf{operator}7.36.2")
                hits = self.assert_caught("constraints-py312.txt", "범위 표기는 쓸 수 없습니다")
                self.assertRegex(hits[0].path, r"^constraints-py312\.txt:[0-9]+$")          # 줄 번호까지 가리킨다

    def test_other_line_shapes_are_each_caught(self):
        for line, needle in (("-e git+host/x#egg=x", "옵션 줄"), ("--hash=sha256:abc", "옵션 줄"), ("-r requirements-dev.txt", "옵션 줄"), ("x @ file:///tmp/x.whl", "주소(URL)"),
                             ("==1.0", "이름이 비어"), ("pyyaml[extra]==6.0.4", "extras"), ("pyyaml==6.0.4; python_version<'3.11'", "환경 표식"), ("pyyaml==6.*", "꼴이 아닙니다"),
                             ("pyyaml==6.0.4+local1", "버전을 읽을 수 없습니다"), ("pyyaml", "꼴이 아닙니다"), ("pyyaml 6.0.4", "꼴이 아닙니다"), ("pyyaml===6.0.4", "범위 표기")):
            with self.subTest(line=line):
                self.setUp()
                self.write("constraints-py312.txt", text_of("constraints-py312.txt") + line + "\n")
                self.assert_caught("constraints-py312.txt", needle)

    def test_an_unreadable_exact_version_is_caught(self):
        self.edit("constraints-py312.txt", "protobuf==7.36.2", "protobuf==7.x")
        self.assert_caught("constraints-py312.txt", "버전을 읽을 수 없습니다")

    def test_a_requirement_package_missing_from_the_constraints_is_caught_for_that_file_only(self):
        self.edit("constraints-py312.txt", "google-genai==2.34.0\n", "")
        found = self.found()
        self.assert_caught("requirements-edits.txt", "constraints-py312.txt 에 없습니다", found)
        self.assert_caught("requirements-pipeline.txt", "constraints-py312.txt 에 없습니다", found)
        self.assertEqual([item.path for item in found if "constraints-py310.txt" in item.message], [])

    def test_every_direct_requirement_missing_is_caught(self):
        for pinned_as, required_as in (("PyYAML", "pyyaml"), ("google-genai", "google-genai"), ("google-auth", "google-auth"), ("google-api-python-client", "google-api-python-client")):
            with self.subTest(name=required_as):
                self.setUp()
                path = self.root / "constraints-py310.txt"
                before = path.read_bytes().decode("utf-8").split("\n")
                lines = [line for line in before if not line.startswith(pinned_as + "==")]
                self.assertEqual(len(lines), len(before) - 1)
                path.write_bytes("\n".join(lines).encode("utf-8"))
                self.assertTrue([item for item in self.found() if item.level == "ERROR" and f"`{required_as}`" in item.message and "constraints-py310.txt 에 없습니다" in item.message])

    def test_a_version_outside_the_requirement_range_is_caught(self):
        for old, new, needle in (("PyYAML==6.0.4", "PyYAML==7.0.0", "PyYAML"), ("google-genai==2.34.0", "google-genai==3.0.0", "google-genai"), ("google-genai==2.34.0", "google-genai==1.99.0", "google-genai"),
                                 ("google-auth==2.63.1", "google-auth==3.0.0rc1", "google-auth"), ("google-api-python-client==2.202.0", "google-api-python-client==3.1", "google-api-python-client")):
            with self.subTest(new=new):
                self.setUp()
                self.edit("constraints-py312.txt", old, new)
                hits = [item for item in self.found() if item.level == "ERROR" and needle in item.message and "밖입니다" in item.message]
                self.assertTrue(hits, new)

    def test_the_exact_pin_in_a_requirement_file_needs_no_constraints_line_but_a_wrong_one_is_caught(self):
        self.assertNotIn("actionlint-py", text_of("constraints-py312.txt"))                 # 요구 파일이 이미 `==` 로 고정 — 목록에 없어도 통과(위 깨끗한 복사본)
        self.write("constraints-py312.txt", text_of("constraints-py312.txt") + "actionlint-py==1.7.12.25\n")
        self.assertEqual([item.line() for item in self.found()], [])                       # 있고 같은 값이면 통과
        self.edit("constraints-py312.txt", "actionlint-py==1.7.12.25", "actionlint-py==1.7.13.0")
        self.assert_caught("requirements-dev.txt", "밖입니다")                              # 있는데 다른 값이면 pip 가 풀지 못하는 충돌 — 오류

    def test_a_duplicate_name_is_caught_whatever_its_spelling(self):
        for extra in ("pyyaml==6.0.4", "PyYAML==6.0.4", "py-yaml==1.0", "Google_Genai==2.34.0", "google.genai==2.34.0"):
            with self.subTest(extra=extra):
                self.setUp()
                self.write("constraints-py312.txt", text_of("constraints-py312.txt") + extra + "\n")
                found = self.found()
                if normalize(extra.split("==")[0]) in pins_of("constraints-py312.txt"):
                    self.assert_caught("constraints-py312.txt", "두 번 있습니다", found)
                else:
                    self.assertEqual([item for item in found if "두 번" in item.message], [])          # py-yaml 은 다른 패키지다

    def test_a_new_requirement_file_with_a_package_nobody_pinned_is_caught_for_both_pythons(self):
        self.write("requirements-extra.txt", "rich>=13,<14\n")
        found = self.found()
        self.assert_caught("requirements-extra.txt", "constraints-py310.txt 에 없습니다", found)
        self.assert_caught("requirements-extra.txt", "constraints-py312.txt 에 없습니다", found)

    def test_a_single_lower_bound_requirement_nobody_pinned_is_caught(self):
        """상한 없는 하한 하나(`rich>=13`)는 정확한 고정이 아니다 — 목록에 없으면 오류다(새 의존성을 더하고 목록을 잊는 가장 흔한 실수. 독립 검증 Q 의 살아남은 변이 Q25)."""
        for line in ("rich>=13", "   rich >= 13", "rich<=13", "rich~=13.0", "rich!=13"):
            with self.subTest(line=line):
                self.setUp()
                self.write("requirements-extra.txt", line + "\n")
                found = self.found()
                self.assert_caught("requirements-extra.txt", "constraints-py310.txt 에 없습니다", found)
                self.assert_caught("requirements-extra.txt", "constraints-py312.txt 에 없습니다", found)

    def test_a_requirement_range_the_validator_cannot_compare_is_an_error_not_a_pass(self):
        """요구 파일의 범위를 비교하지 못하면(임의 일치 연산자·와일드카드가 붙은 하한·한 칸짜리 호환 릴리스) 통과가 아니라 오류다(살아남은 변이 Q23)."""
        for line in ("pyyaml===6.0.4", "pyyaml>=6.*", "pyyaml~=6"):
            with self.subTest(line=line):
                self.setUp()
                self.write("requirements-extra.txt", line + "\n")
                self.assert_caught("requirements-extra.txt", "읽을 수 없습니다")

    def test_a_very_long_package_name_is_cut_in_the_message(self):
        """파일에서 온 긴 이름은 오류 문구에 40자까지만 실린다(살아남은 변이 Q17 — 이름 정규식은 `::` 를 못 넣어 이 줄임만 남는 자리)."""
        name = "a" * 300
        self.write("requirements-extra.txt", name + ">=1,<2\n")
        hits = self.assert_caught("requirements-extra.txt", "constraints-py310.txt 에 없습니다")
        for hit in hits:
            self.assertNotIn(name, hit.message)
            self.assertLess(len(hit.message), 300)

    def test_requirement_lines_the_validator_cannot_read_are_errors_not_passes(self):
        for line, needle in (("-r other.txt", "옵션 줄"), ("pyyaml>=6,<7; python_version>'3'", "환경 표식"), ("pyyaml @ file:///x", "주소"), ("pyyaml>>6", "범위")):
            with self.subTest(line=line):
                self.setUp()
                self.write("requirements-extra.txt", line + "\n")
                self.assert_caught("requirements-extra.txt", needle)

    def test_without_pyyaml_the_workflow_part_is_skipped_but_the_file_parts_still_run(self):
        self.fresh("blogger.yml")
        self.edit(".github/workflows/blogger.yml", "-c constraints-py312.txt ", "")
        self.edit("constraints-py312.txt", "protobuf==7.36.2", "protobuf>=7.36.2")
        with mock.patch.object(vr, "yaml", None):
            found = self.found()
        self.assertEqual([item.path.split(":")[0] for item in found], ["constraints-py312.txt"])      # blogger.yml 의 빠진 -c 는 PyYAML 이 있어야 읽힌다(WF-0 이 그 경고를 낸다)

    def test_a_workflow_free_repository_without_constraints_or_requirements_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.py").write_text("x = 1\n", encoding="utf-8")
            self.assertEqual(vr.check_dependency_constraints(Path(tmp), vr.list_files(Path(tmp))), [])

    def test_hostile_text_in_the_files_cannot_forge_a_workflow_command_or_a_second_line(self):
        self.write("constraints-py312.txt", text_of("constraints-py312.txt") + "::error::boom\n")
        self.write("requirements-extra.txt", "::warning::x" + chr(10) + "pyyaml>=6,<7\n")
        found = self.found()
        self.assertTrue(found)
        for item in found:
            one_plain_line(self, item)


# ----------------------------------------------------------------------------
# 4) 작은 규칙: 범위 비교·줄 읽기·셸 줄 읽기
# ----------------------------------------------------------------------------
class RangeComparisonTest(unittest.TestCase):
    def test_inside_and_outside_the_range(self):
        for version, spec, expected in (
                ("2.34.0", ">=2,<3", True), ("2.0.0", ">=2,<3", True), ("2", ">=2.0,<3", True), ("1.9.9", ">=2,<3", False), ("3.0", ">=2,<3", False), ("3.0.1", ">=2,<3", False),
                ("6.0.4", ">=6,<7", True), ("7.0.0", ">=6,<7", False), ("6.0.4", "", True), ("2.202.0", ">=2,<3", True),
                ("1.7.12.25", "==1.7.12.25", True), ("1.7.12.26", "==1.7.12.25", False), ("1.7.12", "==1.7.12.0", True),
                ("2.5", "==2.*", True), ("3.0", "==2.*", False), ("2.5", "!=2.*", False), ("3.0", "!=2.*", True), ("2.0.5", "==2.0.*", True), ("2.1", "==2.0.*", False),
                ("2.1", "~=2.1", True), ("2.9", "~=2.1", True), ("3.0", "~=2.1", False), ("2.1.5", "~=2.1.3", True), ("2.2", "~=2.1.3", False), ("2.0", "~=2.1", False),
                ("2.0", ">2", False), ("2.0.1", ">2", True), ("2.0.post1", ">2", False), ("2.0.post1", ">=2", True),
                ("3.0rc1", ">=2,<3", False), ("3.0a1", "<3", False), ("2.9rc1", "<3", True), ("2.0rc1", ">=2", False), ("2.0rc1", ">=2rc1", True), ("3.0rc1", "<3rc2", True),
                ("1.0.dev1", "<1.0", False), ("1.0.dev1", "<1.0a1", True), ("1.0", ">1.0.dev1", True),
                ("2.0", "<=2", True), ("2.0.1", "<=2", False), ("1!1.0", ">=1", True), ("1.0", ">=1!0.1", False),
                ("1.5", "!=1.5", False), ("1.6", "!=1.5", True), ("1.5.0", "!=1.5", False),                       # `!=` 는 같은 버전만 거절한다
                ("2", "==2.0.*", True), ("2", "!=2.0.*", False), ("2.0", "==2.0.0.*", True), ("2.0.5", "==2.0.0.*", False)):   # 와일드카드 접두 비교는 짧은 버전을 0 으로 채워 견준다
            with self.subTest(version=version, spec=spec):
                self.assertIs(vr._dep3_allowed(version, spec), expected)

    def test_what_it_cannot_read_is_none_not_a_pass(self):
        for version, spec in (("1.0", "===1.0"), ("1.0+local", ">=1"), ("1.x", ">=1"), ("1.0", ">=x"), ("1.0", ">=1;<2"), ("1.0", "(>=1)"), ("1.0", ">=1 <2"), ("1.0", "~=1"), ("1.0", "<*"), ("1.0", ">=1.*")):
            with self.subTest(version=version, spec=spec):
                self.assertIsNone(vr._dep3_allowed(version, spec))

    def test_exact_pin_detection(self):
        for spec, expected in (("==1.7.12.25", True), (" == 1.0 ", True), ("==2.*", False), (">=2,<3", False), ("", False), ("==1.0,!=1.1", False), ("===1.0", False), ("==x", False),
                               (">=2", False), ("   >=2", False), ("<=2", False), ("~=2.1", False), ("!=2", False)):          # 조각이 하나여도 `==` 가 아니면 고정이 아니다
            with self.subTest(spec=spec):
                self.assertIs(vr._dep3_exact_pin(spec), expected)

    def test_names_compare_the_way_pip_does(self):
        for one, other in (("PyYAML", "pyyaml"), ("pyasn1_modules", "pyasn1-modules"), ("Google.Auth", "google-auth"), ("typing__extensions", "typing-extensions")):
            self.assertEqual(vr._dep3_name(one), vr._dep3_name(other))
        self.assertNotEqual(vr._dep3_name("py-yaml"), vr._dep3_name("pyyaml"))


class LineReadingTest(unittest.TestCase):
    def test_requirement_lines(self):
        for line, expected in (("google-genai>=2,<3", ("google-genai", ">=2,<3")), ("pyyaml>=6,<7  ", ("pyyaml", ">=6,<7")), ("actionlint-py==1.7.12.25", ("actionlint-py", "==1.7.12.25")),
                               ("loose", ("loose", "")), ("pkg[extra]>=1", ("pkg", ">=1")), ("Pkg_X >= 1 , < 2", ("Pkg_X", ">= 1 , < 2")), ("pip", ("pip", ""))):
            with self.subTest(line=line):
                self.assertEqual(vr._dep3_requirement(line), expected)
        for line in ("-r x.txt", "a; python_version<'3'", "a @ file:///x", "./local", "a>>1", "=1", "a" * 500):
            with self.subTest(line=line[:30]):
                self.assertIsInstance(vr._dep3_requirement(line), str)

    def test_constraints_text_comments_blank_lines_and_inline_comments(self):
        pins, problems = vr._dep3_read_constraints("# head\n\nPyYAML==6.0.4   # why\n  anyio==4.16.0\nx==1.0 #y\n")
        self.assertEqual(problems, [])
        self.assertEqual({key: value[1] for key, value in pins.items()}, {"pyyaml": "6.0.4", "anyio": "4.16.0", "x": "1.0"})
        self.assertEqual(pins["pyyaml"][2], 3)                                              # 줄 번호
        pins, problems = vr._dep3_read_constraints("a==1\nA==2\nb_c==1\nb-c==1\n")
        self.assertEqual([number for number, _ in problems], [2, 4])

    def test_a_leading_byte_order_mark_is_skipped_like_pip_does(self):
        bom = chr(0xFEFF)
        pins, problems = vr._dep3_read_constraints(bom + "# head\nx==1.0\n")
        self.assertEqual((problems, sorted(pins)), ([], ["x"]))
        entries, problems = vr._dep3_read_requirements(bom + "# head\nx>=1,<2\n")
        self.assertEqual((problems, [entry[1] for entry in entries]), ([], ["x"]))

    def test_a_very_long_line_is_refused_before_any_regex_runs_on_it(self):
        pins, problems = vr._dep3_read_constraints("a==" + "1" * 100000 + "\n")
        self.assertEqual((pins, len(problems)), ({}, 1))
        self.assertLess(len(problems[0][1]), 200)


class ShellReadingTest(unittest.TestCase):
    def installs(self, run):
        found, unreadable = vr._dep3_pip_installs(run)
        return [(item["constraints"], item["requirements"], item["editable"], item["specs"]) for item in found], unreadable

    def test_shapes_that_are_installs(self):
        for run, expected in (
                ("python -m pip install --upgrade pip", ([], [], [], ["pip"])),
                ("python -m pip install -c a.txt -r b.txt", (["a.txt"], ["b.txt"], [], [])),
                ('pip install -c a.txt "google-genai>=2,<3"', (["a.txt"], [], [], ["google-genai>=2,<3"])),
                ("pip3 install --no-cache-dir -q -r b.txt", ([], ["b.txt"], [], [])),
                ("FOO=1 python3.12 -X utf8 -m pip install x", ([], [], [], ["x"])),
                ("py -m pip install x==1", ([], [], [], ["x==1"])),
                ("/usr/bin/pip install x", ([], [], [], ["x"])),
                ("pip install --index-url mirror.invalid --constraint c.txt -r b.txt", (["c.txt"], ["b.txt"], [], [])),
                ("pip install -e . -c c.txt", (["c.txt"], [], ["."], [])),
                ("pip --cache-dir /tmp/x install y", ([], [], [], ["y"])),
                ("pip install -r b.txt 2>&1 | tail -3", ([], ["b.txt"], [], [])),
                ("pip install -r b.txt > out.txt", ([], ["b.txt"], [], [])),
                ("x=$(pip install -r req.txt)", ([], ["req.txt"], [], [])),
                ("a && pip install -r r.txt || true", ([], ["r.txt"], [], [])),
                ("if true; then pip install x; fi", ([], [], [], ["x"])),
                ("pip install \\\n   -c c.txt \\\n   -r r.txt", (["c.txt"], ["r.txt"], [], [])),
                ("echo hi\npip install -r r.txt\necho done", ([], ["r.txt"], [], [])),
                # 값을 받는 전역 옵션이 install 앞에 온다(결함 D-481 — 옵션의 값이 하위 명령 낱말이어도 뒤의 install 을 놓치지 않는다)
                ("pip --cache-dir cache install -r b.txt", ([], ["b.txt"], [], [])),
                ("python -m pip --cache-dir cache install -r b.txt", ([], ["b.txt"], [], [])),
                ("pip --log list install -r b.txt", ([], ["b.txt"], [], [])),
                ("pip --cache-dir=cache install -r b.txt", ([], ["b.txt"], [], [])),
                ("pip --proxy install install -r b.txt", ([], ["b.txt"], [], [])),
                ("pip -q --no-input --isolated install x", ([], [], [], ["x"])),
                ("pip --some-new-option value install -r b.txt", ([], ["b.txt"], [], [])),           # 목록에 없는 값 옵션: 낯선 낱말 뒤의 install 도 설치로 읽는다
                ("pip install --resume-retries 3 -r b.txt", ([], ["b.txt"], [], [])),                  # install 뒤의 값 옵션 값(3)은 패키지가 아니다
                ("pip --log install foo install -r b.txt", ([], ["b.txt"], [], [])),                  # 보수적으로 읽을 때도 앞의 install(값 옵션의 값)이 아니라 낯선 낱말 뒤의 install 이다
                # 붙여 쓴 -mpip(안전 검증 S 의 R2 b)
                ("python -mpip install -c a.txt -r b.txt", (["a.txt"], ["b.txt"], [], [])),
                ("python3.12 -X utf8 -mpip install x", ([], [], [], ["x"])),
                ("FOO=1 python -mpip3 install x", ([], [], [], ["x"]))):
            with self.subTest(run=run):
                found, unreadable = self.installs(run)
                self.assertEqual((found, unreadable), ([expected], []))

    def test_shapes_that_are_not_installs(self):
        for run in ("# pip install x", 'echo "pip install failed"', "python -m pipeline.run --blog \"$BLOG_KEY\"", "python -m pipeline.plan --count", "pip --version", "python -m pip list", "pip uninstall x",
                    'git commit -m "docs: pip install note"', "gh issue comment 1 --body 'pip install x'", "pytest tests/test_pipeline.py", "python scripts/validate_repo.py", "echo pip install x",
                    # 진짜 하위 명령이 install 이 아니면 그 앞뒤 낱말에 install 이 있어도 설치가 아니다(값 옵션의 값·도움말·다른 명령의 인자)
                    "pip --cache-dir cache list", "pip --log install list", "pip help install", "pip show install", "pip --proxy cache check", "pip uninstall install",
                    "python -m pip --version", "python -mpip list", "python -mpip --version", "pip --cache-dir", "pip --log", "python -m venv pip"):
            with self.subTest(run=run):
                self.assertEqual(self.installs(run), ([], []))

    # pip 가 하위 명령 앞에 받는 일반 옵션 중 값을 받는 것(pip 설명서의 일반 옵션) — 검증기의 목록을 빌리지 않는다. 그리고 pip 의 하위 명령 낱말 전부.
    GLOBAL_VALUE_OPTIONS = ("--cache-dir", "--log", "--log-file", "--local-log", "--proxy", "--timeout", "--default-timeout", "--retries", "--exists-action", "--trusted-host", "--cert", "--client-cert",
                            "--python", "--keyring-provider", "--use-feature", "--use-deprecated", "--resume-retries")
    PIP_COMMAND_WORDS = ("install", "download", "uninstall", "freeze", "inspect", "list", "show", "check", "config", "search", "cache", "index", "wheel", "hash", "completion", "debug", "help", "lock")

    def test_the_value_of_a_global_option_is_never_the_subcommand(self):
        """값을 받는 전역 옵션의 값이 pip 하위 명령 낱말이어도 그 뒤의 진짜 하위 명령을 읽는다 — 모든 값 옵션 × 모든 하위 명령 낱말 × 세 호출 꼴(pip·python -m pip·python -mpip — 결함 D-481, 안전 검증 S 의 R1)."""
        wrong = []
        for option in self.GLOBAL_VALUE_OPTIONS:
            for word in self.PIP_COMMAND_WORDS:
                for prefix in ("pip", "python -m pip", "python -mpip"):
                    found, unreadable = self.installs(f"{prefix} {option} {word} install -r b.txt")
                    if found != [([], ["b.txt"], [], [])] or unreadable:
                        wrong.append(f"{prefix} {option} {word} install: 설치 {found}")
                    found, unreadable = self.installs(f"{prefix} {option} {word} list")
                    if found or unreadable:
                        wrong.append(f"{prefix} {option} {word} list: 설치가 아닌데 {found}")
        self.assertEqual(wrong, [])

    # pip(optparse)는 겹치지 않는 앞부분도 그 옵션으로 받아 준다 — 일반 옵션 중 값을 받는 것의 줄임말(pip 23 에서 `pip --cac cache --version` 이 통과함을 이 PC 에서 확인)
    ABBREVIATED_VALUE_OPTIONS = ("--cache", "--cache-d", "--log-f", "--loc", "--local-l", "--pro", "--time", "--defa", "--ret", "--exists", "--trusted", "--client", "--pyth", "--keyr", "--use-f", "--use-d", "--resume")

    def test_every_value_option_of_the_real_pip_parser_is_read_as_taking_a_value(self):
        """진짜 pip 의 옵션 파서(접속 없음)에서 읽은 전역 옵션 이름 전부(별칭 포함)를 검증기가 값 옵션·플래그로 맞게 읽는다 —손 목록에 별칭이 빠지면(--log-file·--local-log·--default-timeout) 여기서 걸린다. pip 를 못 읽는 환경에서는 건너뛰고 위의 고정 표가 대신 지킨다."""
        try:
            from pip._internal.cli.main_parser import create_main_parser
            parser = create_main_parser()
            options = list(parser.option_list) + [option for group in parser.option_groups for option in group.option_list]
            takes = {name: option.takes_value() for option in options for name in option._long_opts}
        except Exception as error:  # pip 가 없거나 내부 구조가 다르다
            self.skipTest("pip 의 옵션 파서를 못 읽음: %s" % type(error).__name__)
        self.assertIn("--cache-dir", takes)
        wrong = [(name, value) for name, value in takes.items() if vr._dep3_takes_value(name) != value]
        self.assertEqual(wrong, [], "진짜 pip 파서와 다르게 읽는 옵션(이름, 값을 받는가) — 줄임말은 pip 판마다 겹침이 달라 위 고정 표가 지킨다")

    def test_an_abbreviated_global_option_takes_its_value_too(self):
        wrong = []
        for option in self.ABBREVIATED_VALUE_OPTIONS:
            for word in ("cache", "list", "check", "install", "help"):
                found, unreadable = self.installs(f"pip {option} {word} install -r b.txt")
                if found != [([], ["b.txt"], [], [])] or unreadable:
                    wrong.append(f"pip {option} {word} install: 설치 {found}")
        self.assertEqual(wrong, [])
        for run in ("pip --vers", "pip --no-in install x", "pip --no cache list", "pip --cache=cache list", "pip --c cache list"):         # 줄임말이 플래그이거나 겹치면(pip 가 오류로 끝내는 모양) 값을 받는 것으로 읽지 않는다
            found, unreadable = self.installs(run)
            self.assertEqual(unreadable, [], run)
        self.assertEqual(self.installs("pip --no-in install x")[0], [([], [], [], ["x"])])
        self.assertEqual(self.installs("pip --cache=cache install -r b.txt")[0], [([], ["b.txt"], [], [])])

    def test_the_position_of_the_subcommand(self):
        for args, expected in ((["install", "x"], 0), (["--cache-dir", "cache", "install"], 2), (["-q", "-q", "list"], 2), (["--version"], None), ([], None), (["--log"], None),
                               (["--cache-dir=cache", "install"], 1), (["x", "install"], 1), (["list", "install"], 0), (["--log", "install", "list"], 2), (["--cache-dir", "cache"], None),
                               (["frobnicate", "list", "install"], 2), (["--log", "install", "foo", "install"], 3),
                               (["--cache", "cache", "install"], 2), (["--log-f", "list", "install"], 2), (["--local-log", "list", "install"], 2), (["--default-timeout", "list", "install"], 2), (["--lo", "list", "install"], 1), (["--vers", "install"], 1), (["--cache=cache", "list"], 1)):
            with self.subTest(args=args):
                self.assertEqual(vr._dep3_pip_subcommand(args), expected)

    def test_python_dash_m_pip_in_both_spellings(self):
        for words, expected in ((["python", "-m", "pip", "install", "x"], ["install", "x"]), (["python", "-mpip", "install", "x"], ["install", "x"]), (["python3.12", "-X", "utf8", "-mpip3", "list"], ["list"]),
                                (["py", "-3.12", "-m", "pip", "list"], ["list"]), (["python", "-m", "venv", "pip"], None), (["python", "script.py"], None), (["python", "-m"], None), (["python"], None),
                                (["python", "-mpipx", "install", "x"], None), (["python", "-mpip"], [])):
            with self.subTest(words=words):
                self.assertEqual(vr._dep3_python_pip_args(words), expected)

    def test_the_leading_words_of_a_command_are_skipped_by_position(self):
        for segment, expected in ((["a=1", "b=2", "pip", "install"], ["pip", "install"]), (["if", "pip", "install"], ["pip", "install"]), (["then", "A=1", "{", "pip"], ["pip"]),
                                  (["pip", "a=1"], ["pip", "a=1"]), (["a=1"], []), ([], []), (["!", "time", "x=", "python"], ["python"])):
            with self.subTest(segment=segment):
                self.assertEqual(vr._dep3_command_words(segment), expected)

    def test_shapes_that_hide_an_install_are_reported_unreadable(self):
        for run in ('bash -c "pip install x"', "sh -c 'python -m pip install -r r.txt'", 'eval "pip install x"', "xargs pip install", "sudo pip install x", "uv pip install x", "time sudo pip install x",
                    "nohup pip install x &", '"$PYTHON" -m pip install -r r.txt', 'export X="$(pip install -r r.txt)"', "`pip install -r r.txt`", "pipx run pip install x"):
            with self.subTest(run=run):
                found, unreadable = self.installs(run)
                self.assertEqual(found, [], run)
                self.assertEqual(len(unreadable), 1, run)

    def test_the_shapes_the_document_lists_as_passing_without_an_error_really_do(self):
        """docs/DEPENDENCY_PINNING.md §3 '오류도 없이 지나가는 모양' 이 말하는 모양(a·b·c·e·f)이 정말 아무 설치로도 오류로도 읽히지 않는다 — 문서가 거짓이 되지 않게 묶는다.
        이 모양을 막는 변경이 생기면 이 시험과 그 문단을 함께 고친다(색인 옵션을 거절하는 규칙은 승인 범위 밖이라 두지 않았다)."""
        for run in ("PIP=pip; $PIP install -r r.txt", 'PIP="python -m pip"; ${PIP} install -r r.txt', "sudo python -mpip install -r r.txt", 'echo "$(python -m pip install -r r.txt)"',
                    'x="$(python -m pip install -r r.txt)"', "pipx install ruff", "python -m pip config set global.extra-index-url mirror.invalid"):
            with self.subTest(run=run):
                self.assertEqual(self.installs(run), ([], []))
        found, unreadable = self.installs("PIP_INDEX_URL=mirror.invalid python -m pip install --extra-index-url mirror.invalid -f mirror.invalid -c c.txt -r r.txt")
        self.assertEqual((found, unreadable), ([(["c.txt"], ["r.txt"], [], [])], []))              # 색인을 바꾸는 줄도 -c 만 맞으면 그대로 읽힌다
        found, unreadable = self.installs('x=$(python -m pip install -r r.txt)')
        self.assertEqual((found, unreadable), ([([], ["r.txt"], [], [])], []))                    # 따옴표 없는 명령 치환 안의 설치는 보통 설치 줄처럼 읽힌다(문서가 그렇게 말한다)

    def test_a_line_with_an_unclosed_quote_is_reported_only_when_it_mentions_pip(self):
        self.assertEqual(self.installs("echo \"it's open\n"), ([], []))
        found, unreadable = self.installs("echo 'pip install x")
        self.assertEqual(found, [])
        self.assertEqual(len(unreadable), 1)

    def test_a_quoted_string_across_lines_is_read_until_it_closes(self):
        found, unreadable = self.installs('echo "first line\nsecond line"\npip install -r r.txt\n')
        self.assertEqual((found, unreadable), ([([], ["r.txt"], [], [])], []))


# ----------------------------------------------------------------------------
# 숨은 설치 읽기와 병적 입력 — 옛 정규식(글 길이의 제곱 시간)과 같은 판정을 선형 시간으로(결함 D-482, 안전 검증 S 의 R3)
# ----------------------------------------------------------------------------
# 옛 구현의 글자 그대로의 사본 — 판정의 기준이다(낱말 경계를 뜻하는 백슬래시 b 는 글자를 이어 붙여 만든다)
OLD_HIDDEN_PIP = re.compile(r"(?<![\w./-])pip3?(?:\.[0-9]+)?(?:\.exe)?\s+(?:\S+\s+)*?install" + chr(92) + "b")
FRAGMENTS = ("pip", "pip3", "pip3.12", "pip.exe", "pip3.12.exe", "pip.", "pip3x", "pip.12.34", "mypip", "-pip", "/pip", "./pip", "_pip", ":pip", "(pip", "'pip", "=pip", "PIP", "python", "-m", "-mpip",
             "install", "installs", "install-x", "install.", "install_x", "install:pip", "installed", "uninstall", "-install", chr(0xE9) + "install", "install" + chr(0xE9), "x", "-r", "a.txt", "$(", ")", ";")
SEPARATORS = (" ", " ", "  ", "\t", "\n", chr(0xA0), chr(0x2028), chr(0x1F), chr(0x85), chr(0x3000), "", "")          # 빈 글자 = 붙여 쓰기, 나머지는 정규식 \s 가 공백으로 읽는 글자들


def best_seconds(function, value, runs=3, limit=2.0):
    """함수를 value 에 돌려 가장 빠른 한 번의 CPU 초를 돌려준다. 벽시계가 아니라 이 프로세스의 CPU 시간으로 재서 다른 프로그램이 CPU 를 쓰는 부하(공용 PC·바쁜 러너)에 덜 흔들린다.
    한 번이 limit 초를 넘으면 더 돌리지 않는다(제곱 시간 코드를 오래 돌리지 않으려고)."""
    best = None
    for _ in range(runs):
        started = time.process_time()
        function(value)
        took = time.process_time() - started
        best = took if best is None else min(best, took)
        if took > limit:
            break
    return best


class HiddenInstallScanTest(unittest.TestCase):
    def test_known_shapes(self):
        for text, expected in (
                ("pip install", True), ("x pip install y", True), ("pip   install", True), ("pip a b c install", True), ("(pip install", True), ('"pip install', True), ("=pip install", True),
                ("pip3 install", True), ("pip3.12 install", True), ("pip.exe install", True), ("pip3.12.exe install", True), ("pip pip install", True), ("pip install-x", True), ("pip install.", True),
                ("pip" + chr(0xA0) + "install", True), ("pip\ninstall", True), ("install:pip install", True), ("sudo pip3 -q install x", True),
                ("PIP install", False), ("mypip install", False), ("./pip install", False), ("/usr/bin/pip install", False), ("-pip install", False), ("_pip install", False), ("pip.install", False),
                ("pip installs", False), ("pip install_x", False), ("pip uninstall", False), ("pip", False), ("install pip", False), ("pip;", False), ("", False), ("pip3x install", False),
                ("pip.12.34 install", False), ("pip " + chr(0xE9) + "install", False), ("pip install" + chr(0xE9), False)):
            with self.subTest(text=text):
                self.assertIs(vr._dep3_hides_pip_install(text), expected)

    def test_same_verdict_as_the_old_regex_on_every_short_combination(self):
        pieces = ("pip", "install", " ", "-", "x", ".exe")
        checked = trues = 0
        for length in range(7):
            for combo in itertools.product(pieces, repeat=length):
                text = "".join(combo)
                expected = OLD_HIDDEN_PIP.search(text) is not None
                if vr._dep3_hides_pip_install(text) is not expected:
                    self.fail(f"옛 정규식과 판정이 다르다: {text!r} (옛 {expected})")
                checked += 1
                trues += expected
        self.assertEqual(checked, sum(len(pieces) ** length for length in range(7)))
        self.assertGreater(trues, 200)                           # 참인 글도 많이 본다(모두 거짓이면 이 시험은 아무것도 못 본다)
        self.assertLess(trues, checked - 1000)

    def test_same_verdict_as_the_old_regex_on_random_texts(self):
        rng = random.Random(20261124)
        trues = 0
        for _ in range(30000):
            pieces = []
            for _ in range(rng.randint(0, 9)):
                pieces.append(rng.choice(FRAGMENTS))
                pieces.append(rng.choice(SEPARATORS))
            text = "".join(pieces)
            expected = OLD_HIDDEN_PIP.search(text) is not None
            if vr._dep3_hides_pip_install(text) is not expected:
                self.fail(f"옛 정규식과 판정이 다르다: {text!r} (옛 {expected})")
            trues += expected
        self.assertGreater(trues, 1000)
        self.assertLess(trues, 29000)

    def test_the_old_shape_still_reports_hidden_installs_through_the_reader(self):
        """읽는 쪽(_dep3_pip_installs)에서도 같다: 다른 명령 안의 pip install 은 읽지 못한 설치로 알리고, 안내문 명령은 면제한다."""
        for run, hidden in (('bash -c "pip install x"', 1), ("sudo pip3 install x", 1), ("xargs pip install", 1), ("uv pip install x", 1), ("env PIP=1 pip install x", 1),
                            ("echo pip install x", 0), ('git commit -m "pip install x"', 0), ("grep pip install-notes.txt", 1), ("grep pipe install", 0), ("mypip install x", 0)):
            with self.subTest(run=run):
                found, unreadable = vr._dep3_pip_installs(run)
                self.assertEqual((found, len(unreadable)), ([], hidden))


class PathologicalInputTest(unittest.TestCase):
    """긴 반복 입력도 글 길이에 비례해 읽는다(결함 D-482). 옛 구현: `pip` 낱말 1만 6천 개에 14초(길이가 두 배면 네 배), 앞머리 대입 16만 개에 3초."""
    SHAPES = (("pip 만 반복", lambda tokens: "foo " + "pip " * tokens),
              ("pip 와 낱말 교대", lambda tokens: "foo " + "pip x " * (tokens // 2)),
              ("pip 꼴 세 가지 섞기", lambda tokens: "foo " + "pip3.12 pip.exe pip " * (tokens // 3)),
              ("끝에 install 닮은 낱말", lambda tokens: "foo " + "pip " * tokens + "installx"),
              ("줄마다 반복", lambda tokens: "\n".join("foo pip pip" for _ in range(tokens // 4))),
              ("줄임말 값 옵션 반복", lambda tokens: "pip " + "--cache cache " * (tokens // 2) + "install -r b.txt"))

    def test_sixteen_thousand_words_are_read_in_seconds_not_in_tens_of_seconds(self):
        """옛 구현은 이 입력들에서 CPU 6–19초였다. 지금은 0.1–0.3초 — 한도 2초는 바쁜 PC 의 흔들림을 덮고도 옛 제곱 시간을 잡는다."""
        for label, make in self.SHAPES:
            with self.subTest(label=label):
                self.assertLess(best_seconds(vr._dep3_pip_installs, make(16000), runs=1), 2.0)

    def test_eight_times_the_input_takes_about_eight_times_as_long(self):
        for label, make in self.SHAPES[:2]:
            with self.subTest(label=label):
                small = best_seconds(vr._dep3_pip_installs, make(8000), runs=2)
                self.assertLess(small, 2.0)
                large = best_seconds(vr._dep3_pip_installs, make(64000), runs=1)
                self.assertLess(large, 24 * max(small, 0.05), (small, large))               # 선형이면 8배 안팎, 제곱이면 64배(CPU 시간은 0.016초 단위로 읽혀 바닥을 0.05초로 둔다)

    def test_the_scan_alone_handles_a_very_long_text(self):
        self.assertLess(best_seconds(vr._dep3_hides_pip_install, "foo " + "pip x " * 100000, runs=1), 2.0)
        self.assertFalse(vr._dep3_hides_pip_install("foo " + "pip x " * 100000))
        self.assertTrue(vr._dep3_hides_pip_install("foo " + "pip x " * 100000 + "install"))

    def test_hundreds_of_thousands_of_leading_assignments_are_skipped_by_position(self):
        self.assertLess(best_seconds(vr._dep3_command_words, ["a=1"] * 200000 + ["pip", "install", "x"], runs=1), 2.0)
        self.assertEqual(vr._dep3_command_words(["if"] * 200000 + ["pip", "install", "x"]), ["pip", "install", "x"])

    def test_leading_assignments_in_a_real_command_line_take_linear_time(self):
        small = best_seconds(vr._dep3_pip_installs, "a=1 " * 20000 + "pip install -r b.txt", runs=2)
        self.assertLess(small, 2.0)
        large = best_seconds(vr._dep3_pip_installs, "a=1 " * 160000 + "pip install -r b.txt", runs=1, limit=6.0)
        self.assertLess(large, 20 * max(small, 0.05), (small, large))                   # 선형이면 8배 안팎(낱말 쪼개기), 앞에서 하나씩 빼면 40배
        found, unreadable = vr._dep3_pip_installs("a=1 " * 20 + "pip install -r b.txt")
        self.assertEqual(([item["requirements"] for item in found], unreadable), ([["b.txt"]], []))


class PythonVersionTest(unittest.TestCase):
    def job(self, python, matrix=None):
        job = {"steps": [{"uses": "actions/setup-python@v6", "with": {"python-version": python}}]}
        if matrix is not None:
            job["strategy"] = {"matrix": matrix}
        return job, job["steps"][0]

    def test_literal_and_matrix_lists(self):
        job, step = self.job("3.12")
        self.assertEqual(vr._dep3_setup_python(job, step), ({"versions": ["3.12"], "key": None}, None))
        job, step = self.job("${{ matrix.python-version }}", {"python-version": ["3.10", "3.12"]})
        self.assertEqual(vr._dep3_setup_python(job, step), ({"versions": ["3.10", "3.12"], "key": "python-version"}, None))
        job, step = self.job("${{matrix.py}}", {"py": ["3.10"], "include": [{"py": "3.12", "os": "x"}, {"os": "y"}]})
        self.assertEqual(vr._dep3_setup_python(job, step)[0], {"versions": ["3.10", "3.12"], "key": "py"})

    def test_everything_else_is_refused_with_a_reason(self):
        for python, matrix in ((3.12, None), (3.1, None), ("3.x", None), ("3", None), ("${{ matrix.python-version }}", None), ("${{ matrix.python-version }}", {"python-version": "${{ fromJSON(x) }}"}),
                               ("${{ matrix.python-version }}", {"python-version": [3.10, "3.12"]}), ("${{ vars.PY }}", {"python-version": ["3.12"]}), ("", None), (None, None)):
            with self.subTest(python=python):
                job, step = self.job(python, matrix)
                found, why = vr._dep3_setup_python(job, step)
                self.assertIsNone(found)
                self.assertTrue(why)


class ConstraintTargetTest(unittest.TestCase):
    PYTHON = {"versions": ["3.10", "3.12"], "key": "python-version"}
    LITERAL = {"versions": ["3.12"], "key": None}
    TERNARY = "constraints-py${{ matrix.python-version == '3.10' && '310' || '312' }}.txt"

    def test_the_readable_shapes(self):
        self.assertEqual(vr._dep3_constraint_targets("constraints-py312.txt", {}, self.LITERAL), ({"3.12": "constraints-py312.txt"}, None))
        self.assertEqual(vr._dep3_constraint_targets("./constraints-py312.txt", {}, self.LITERAL)[0], {"3.12": "constraints-py312.txt"})
        self.assertEqual(vr._dep3_constraint_targets("$F", {"F": "constraints-py312.txt"}, self.LITERAL)[0], {"3.12": "constraints-py312.txt"})
        self.assertEqual(vr._dep3_constraint_targets("${F}", {"F": "constraints-py312.txt"}, self.LITERAL)[0], {"3.12": "constraints-py312.txt"})
        self.assertEqual(vr._dep3_constraint_targets("$F", {"F": self.TERNARY}, self.PYTHON)[0], {"3.10": "constraints-py310.txt", "3.12": "constraints-py312.txt"})

    def test_everything_else_is_refused_with_a_reason(self):
        for token, env, python in (("$NOPE", {}, self.LITERAL), ("$F", {"F": 5}, self.LITERAL), ("other.txt", {}, self.LITERAL), ("dir/constraints-py312.txt", {}, self.LITERAL), ("$(echo x)", {}, self.LITERAL),
                                   ("${F:-x}", {"F": "constraints-py312.txt"}, self.LITERAL), ("$F", {"F": self.TERNARY}, self.LITERAL), ("$F", {"F": self.TERNARY.replace("==", "!=")}, self.PYTHON),
                                   ("$F", {"F": "constraints-py${{ github.ref }}.txt"}, self.PYTHON), ("", {}, self.LITERAL), ("-", {}, self.LITERAL), ("constraints-py312.txt.bak", {}, self.LITERAL),
                                   ("$F", {"F": "constraints-py312.txt $X"}, self.LITERAL)):
            with self.subTest(token=token):
                found, why = vr._dep3_constraint_targets(token, env, python)
                self.assertIsNone(found)
                self.assertTrue(why)


class Dep1Test(TmpCase):
    def test_quotes_do_not_change_what_dep1_sees(self):
        self.write(".github/workflows/w.yml", 'jobs:\n  j:\n    steps:\n      - run: |\n          pip install -c "$CONSTRAINTS" -r "requirements-x.txt" \'good>=1,<2\' "bad" \'also_bad\'\n')
        self.write("requirements-x.txt", "pinned==1.0\n")
        messages = " ".join(item.message for item in vr.check_dependencies(self.root, vr.list_files(self.root)))
        self.assertNotIn("CONSTRAINTS", messages)
        self.assertNotIn("requirements-x", messages)
        self.assertNotIn("good", messages)
        self.assertIn("bad", messages)                          # 따옴표 친 범위 없는 패키지는 옛 규칙처럼 여전히 경고
        self.assertIn("also_bad", messages)
        self.assertEqual({item.check for item in vr.check_dependencies(self.root, vr.list_files(self.root))}, {"DEP-1"})


# ----------------------------------------------------------------------------
# 5) 문서가 코드와 같은 말을 한다
# ----------------------------------------------------------------------------
class DocsTest(unittest.TestCase):
    def test_the_safety_document_sentences_the_merge_branch_adds_stay(self):
        """총괄이 병합 가지에서 고친 문장(G-A5 행·6장 DEP-3 행·D-10 행·ARCHITECTURE STATIC_EXPOSED 문장)이 나중에 지워지지 않는다(독립 시험 검증 Q 의 R4)."""
        guardrails = text_of("docs/SECURITY_GUARDRAILS.md").split("\n")
        row = next(line for line in guardrails if line.startswith("| G-A5 |"))
        for word in ("constraints-py310.txt", "constraints-py312.txt", "DEPENDENCY_PINNING.md", "**DEP-1**", "**DEP-3**"):
            self.assertIn(word, row)
        self.assertTrue(any(line.startswith("| DEP-3 |") and "G-A5" in line for line in guardrails))
        register = text_of("docs/DEFECT_REGISTER.md").split("\n")
        self.assertIn("**해결**", next(line for line in register if line.startswith("| **D-10** |")))
        architecture = text_of("docs/ARCHITECTURE.md")
        at = architecture.index("STATIC_EXPOSED")
        for rel in CONSTRAINT_FILES:
            self.assertIn(rel, architecture[at:at + 200])

    def test_the_guide_line_r4_mentions_constraints_and_the_new_document(self):
        guide = text_of("docs/ENGINEERING_GUIDE.md")
        row = next(line for line in guide.split("\n") if line.startswith("| R4 |"))
        for word in ("버전 범위를 고정하고", "constraints-py310.txt", "constraints-py312.txt", "DEPENDENCY_PINNING.md", "DEP-3"):
            self.assertIn(word, row)
        self.assertIn("**DEP-1**·**DEP-3**", next(line for line in guide.split("\n") if line.startswith("| W5 |")))      # 패키지 버전 규칙의 강제 칸도 DEP-3 을 말한다(독립 검증 Q 의 N6)

    def test_the_new_document_covers_the_procedure_the_rule_and_the_limits(self):
        doc = text_of("docs/DEPENDENCY_PINNING.md")
        for word in ("constraints-py310.txt", "constraints-py312.txt", "DEP-3", "-c constraints-py312.txt -r requirements-pipeline.txt", "CONSTRAINTS", "pip check", "번호 있는 확인", "월 1회",
                     "requirements-dev.txt", "requirements-edits.txt", "requirements-pipeline.txt", "actionlint-py", "한계", "되돌리", "PYTHONUTF8"):
            self.assertIn(word, doc, word)
        for forbidden in ("{{", "{%", "~", "http://", "https://"):
            self.assertNotIn(forbidden, doc, forbidden)

    def test_the_new_defect_rows_are_there_once_each_and_in_number_order(self):
        register = text_of("docs/DEFECT_REGISTER.md")
        for number in range(461, 466):
            rows = [line for line in register.split("\n") if line.startswith(f"| **D-{number}** |")]
            self.assertEqual(len(rows), 1, number)
            for forbidden in ("{{", "~", "http://", "https://"):
                self.assertNotIn(forbidden, rows[0], (number, forbidden))
        defects = re.findall(r"^\| \*\*(D-\d+)\*\* \|", register, re.M)
        positions = [defects.index(f"D-{number}") for number in range(461, 466)]
        self.assertEqual(positions, list(range(positions[0], positions[0] + 5)))            # 다섯 행이 번호 순서로 이어져 있다(뒤에 다른 묶음의 행이 붙어도 된다)

    def test_the_rework_defect_rows_are_there_once_each_after_the_first_five_and_in_number_order(self):
        """재작업(독립 검증 S·Q 의 지적)의 결함 행 D-481–D-484 — 한 번씩, 처음 다섯 행 뒤에, 번호 순서로(사이에 다른 묶음의 행이 끼어도 된다)."""
        register = text_of("docs/DEFECT_REGISTER.md")
        for number in range(481, 485):
            rows = [line for line in register.split("\n") if line.startswith(f"| **D-{number}** |")]
            self.assertEqual(len(rows), 1, number)
            for forbidden in ("{{", "~", "http://", "https://"):
                self.assertNotIn(forbidden, rows[0], (number, forbidden))
        defects = re.findall(r"^\| \*\*(D-\d+)\*\* \|", register, re.M)
        positions = [defects.index(f"D-{number}") for number in list(range(461, 466)) + list(range(481, 485))]
        self.assertEqual(positions, sorted(positions))

    def test_the_first_defect_row_says_the_linux_check_is_done_and_names_what_stays_outside(self):
        """D-461 이 끝난 일(리눅스 러너 점검)을 남은 일로 적지 않고, 상태 단어를 D-10 의 '해결' 과 같게 풀어 쓴다(독립 검증 S 의 R4·Q 의 R3)."""
        register = text_of("docs/DEFECT_REGISTER.md")
        row = next(line for line in register.split("\n") if line.startswith("| **D-461** |"))
        self.assertIn("| **해결**(범위 안 고정; `pip` 자신·`actionlint-py`·해시 고정은 이 변경 밖) |", row)
        self.assertIn("임시 가지 검증은 끝났다", row)
        self.assertIn("완료(2026-11-24", row)
        self.assertIn("linux_check_result.md", row)
        for stale in ("**남은 것**: 병합 전", "| **완화** |"):
            self.assertNotIn(stale, row)

    def test_the_limits_paragraph_names_the_shapes_that_pass_without_an_error(self):
        """§3 의 한계에 '오류도 없이 지나가는 모양'(안전 검증 S 의 R2 a–f, 시험 검증 Q 의 N7)이 말로 적혀 있고 색인 옵션 거절은 승인 밖이라 두지 않았다고 밝힌다."""
        doc = text_of("docs/DEPENDENCY_PINNING.md")
        self.assertIn("오류도 없이 지나가는 모양", doc)
        paragraph = doc[doc.index("오류도 없이 지나가는 모양"):doc.index("## 4.")]
        for word in ("명령 이름을 변수로", "$PIP install", "sudo python -mpip", "명령 치환", "CONSTRAINTS=/dev/null", "--index-url", "--extra-index-url", "--find-links", "pip config set", "PIP_INDEX_URL",
                     "pipx install", "shell:", "승인 범위 밖"):
            self.assertIn(word, paragraph, word)
        self.assertIn("(a)", paragraph)
        self.assertIn("(g)", paragraph)
        self.assertIn("`-mpip` 처럼 붙여 쓴 것도", doc)                      # 코드가 읽는 모양은 규칙 설명에 적혀 있다
        self.assertIn("줄임말 `--cache cache` 도", doc)


if __name__ == "__main__":
    unittest.main()
