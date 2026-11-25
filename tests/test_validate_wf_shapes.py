"""검증기가 놓치던 워크플로 모양 막기(독립 감사 BA-S2 의 R3·N1, 운영자 확인 040 ① 승인 — 이슈 #271).

이 모듈은 세 가지를 시험한다(항목마다 고치기 전 빨강·변이로 확인):
  ① 재사용 워크플로를 다른 저장소에서 부르는 줄(`jobs.<id>.uses`)과 `docker://` 단계 — WF-5 는 단계의 `uses` 만 봤고 `docker://` 는 아예 면제였다(감사 변이 D13·L6·L7·L8, 탐침 §2)
  ② 복합 액션 파일(`action.yml`)도 WF-4·WF-5 의 대상이다(감사 변이 L1)
  ④ WF-4 의 신뢰 못 할 칸 목록 확장 — shell·working-directory·runs-on·container·services·체크아웃 ref(감사 탐침 §1b)
  ⑤ 안전 독립 검증 S 의 권고 — R1 복합 액션 탐색이 워크플로 폴더의 하위 폴더도 읽는다·R2 job 의 container·services 이미지는 항상 WF-5 오류·R5 `uses` 값의 앞뒤 공백은 읽지 못한 모양
새 규칙은 모두 더 엄격한 쪽이고, 지금 저장소의 진짜 워크플로는 하나도 새로 거절하지 않는다(진짜 파일 시험이 보인다). 네트워크·GitHub 없이 임시 폴더에 워크플로 글을 써서 돌린다.
워크플로를 읽는 시험은 PyYAML 이 있어야 돈다(없는 환경에서는 건너뜀 — requirements-dev.txt 가 CI 에 설치한다).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap
from real_repo_helpers import run_checks_once

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover - requirements-dev.txt 가 CI 에 설치한다
    yaml = None

REAL = _bootstrap.ROOT
NEEDS_YAML = unittest.skipUnless(yaml is not None, "PyYAML(requirements-dev.txt)이 필요합니다(CI 에서는 항상 실행됩니다)")
WORKFLOWS = REAL / ".github" / "workflows"
SHA = "0123456789abcdef0123456789abcdef01234567"
CHANCE = "chance" + "blog.yml"                     # 실제 워크플로 파일 이름(이어 붙여 적는다 — 금지어 점검에 걸리지 않게, 옛 시험과 같은 방식)

# 감사 탐침(probe_misc.py)의 머리 — job 하나짜리 워크플로. 단계는 뒤에 붙인다.
HEAD = ('name: "[공통] 시험"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  j:\n    name: 일\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n')


def real_text(name):
    return (WORKFLOWS / name).read_bytes().decode("utf-8").replace("\r\n", "\n")


def swapped(text, old, new, count=1):
    """옛 글이 정확히 `count` 번 나올 때만 바꾼다(진짜 파일의 모양이 변하면 이 변이 시험이 소리 내어 실패한다)."""
    if text.count(old) != count:
        raise AssertionError(f"옛 글 {old!r} 가 {text.count(old)} 번 나온다(기대 {count})")
    return text.replace(old, new)


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def put(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
        return rel

    def wf(self, text, name="w.yml"):
        return self.put(f".github/workflows/{name}", text)

    def findings(self, text, name="w.yml"):
        rel = self.wf(text, name)
        return vr.check_workflows(self.root, [rel])

    @staticmethod
    def of(found, check, level=None):
        return [f for f in found if f.check == check and (level is None or f.level == level)]


def one_plain_line(test, finding):
    for text in (finding.message, finding.line()):
        test.assertEqual(len(text.splitlines()), 1, text)
        test.assertNotIn("##[", text)


# ----------------------------------------------------------------------------
# ① 재사용 워크플로를 다른 저장소에서 부르는 줄·docker:// 단계 (WF-5 확장)
# ----------------------------------------------------------------------------
EXTERNAL_CALLS = {
    # 감사 변이 D13: 이름·runs-on·timeout 없이 job 이 uses 한 줄뿐
    "D13": ('name: "[공통] 외부 호출"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  j:\n    uses: evil-org/evil-repo/.github/workflows/x.yml@main\n'),
    # L6: 시크릿을 이름으로 넘긴다
    "L6": ('name: "[공통] 외부 재사용"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  j:\n    uses: evil-org/evil-repo/.github/workflows/x.yml@main\n    secrets:\n      K: ${{ secrets.GEMINI_API_KEY }}\n'),
    # L7: 한글 job 이름을 붙여 job 이름 경고도 안 난다
    "L7": ('name: "[공통] 외부 재사용"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  j:\n    name: 외부 호출\n    uses: evil-org/evil-repo/.github/workflows/x.yml@main\n'),
    # L8: 한글 job 이름 + 명시한 시크릿
    "L8": ('name: "[공통] 외부 재사용"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  j:\n    name: 외부 호출\n    uses: evil-org/evil-repo/.github/workflows/x.yml@main\n    secrets:\n      K: ${{ secrets.GEMINI_API_KEY }}\n'),
    # 시험 렌즈 Q 의 Q03: 검사를 needs·if 가 있는 job 에서 건너뛰어도 옛 시험이 모두 통과했다 — reusable 호출 job 이 가질 수 있는 다른 키(needs·if·with·strategy)를 단 외부 호출도 오류다
    "needs": ('name: "[공통] 외부 호출"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  a:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - run: echo a\n'
              '  j:\n    needs: [a]\n    uses: evil-org/evil-repo/.github/workflows/x.yml@main\n'),
    "if": ('name: "[공통] 외부 호출"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  j:\n    if: always()\n    uses: evil-org/evil-repo/.github/workflows/x.yml@main\n'),
    "with": ('name: "[공통] 외부 호출"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  j:\n    uses: evil-org/evil-repo/.github/workflows/x.yml@main\n    with:\n      x: 1\n'),
    "strategy": ('name: "[공통] 외부 호출"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  j:\n    strategy:\n      matrix:\n        k: [1, 2]\n    uses: evil-org/evil-repo/.github/workflows/x.yml@main\n'),
    "needs if with strategy together": ('name: "[공통] 외부 호출"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  a:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - run: echo a\n'
                                         '  j:\n    needs: [a]\n    if: always()\n    strategy:\n      matrix:\n        k: [1]\n    uses: evil-org/evil-repo/.github/workflows/x.yml@main\n    with:\n      x: 1\n    secrets:\n      K: ${{ secrets.GEMINI_API_KEY }}\n'),
}


@NEEDS_YAML
class ReusableWorkflowCallTest(Case):
    def test_each_audit_mutation_of_an_external_reusable_call_is_a_wf5_error_that_names_the_job(self):
        for label, text in EXTERNAL_CALLS.items():
            with self.subTest(label=label):
                found = self.findings(text)
                errors = self.of(found, "WF-5", "ERROR")
                self.assertEqual(len(errors), 1, [f.line() for f in found])
                self.assertIn("job j", errors[0].message)
                self.assertIn("재사용 워크플로", errors[0].message)
                self.assertEqual(errors[0].path, ".github/workflows/w.yml")
                one_plain_line(self, errors[0])

    def test_pinning_the_external_workflow_to_a_commit_does_not_make_it_acceptable(self):
        """더 엄격한 쪽을 골랐다: 지금 저장소에 다른 저장소의 재사용 워크플로가 하나도 없으므로 SHA 로 고정한 것도 오류다."""
        text = HEAD.replace("    name: 일\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n", f"    uses: evil-org/evil-repo/.github/workflows/x.yml@{SHA}\n")
        self.assertEqual(len(self.of(self.findings(text), "WF-5", "ERROR")), 1)

    def test_a_call_to_a_workflow_of_this_repository_is_still_fine(self):
        text = HEAD.replace("    name: 일\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n",
                            "    name: 부름\n    uses: ./.github/workflows/blogger.yml\n    with:\n      blog: x\n    secrets:\n      PIPELINE_SECRET_LLM_API_KEY: ${{ secrets.GEMINI_API_KEY }}\n")
        self.assertEqual(self.of(self.findings(text), "WF-5"), [])

    def test_shapes_that_only_look_like_a_local_call_are_errors(self):
        for uses in ("./.github/workflows/x.yml@main", "./.github/workflows/sub/x.yml", "./not-a-workflow-folder/x.yml", "./.github/actions/x", "octo/./.github/workflows/x.yml",
                     "docker://image", "../x.yml", "./.github/workflows/x.txt", "./.github/workflows/", "x.yml", "./.github/workflows/x.yml extra"):
            with self.subTest(uses=uses):
                text = HEAD.replace("    name: 일\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n", "    uses: " + json.dumps(uses, ensure_ascii=False) + "\n")      # JSON 글자는 YAML 큰따옴표 글자와 같다
                self.assertEqual(len(self.of(self.findings(text), "WF-5", "ERROR")), 1)

    def test_a_uses_that_is_not_a_string_is_an_error_too(self):
        for value in ("[a, b]", "{x: 1}", "5", "''", "null"):
            with self.subTest(value=value):
                text = HEAD.replace("    name: 일\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n", f"    uses: {value}\n")
                self.assertEqual(len(self.of(self.findings(text), "WF-5", "ERROR")), 1)

    def test_every_external_job_gets_its_own_error(self):
        text = (HEAD.split("jobs:\n")[0] + "jobs:\n  a:\n    uses: o/r/.github/workflows/a.yml@main\n  b:\n    uses: ./.github/workflows/blogger.yml\n  c:\n    uses: o/r/.github/workflows/c.yml@main\n")
        found = self.of(self.findings(text), "WF-5", "ERROR")
        self.assertEqual(len(found), 2)
        self.assertEqual([("job a" in f.message, "job c" in f.message) for f in found], [(True, False), (False, True)])

    def test_the_hostile_job_name_and_uses_text_cannot_forge_a_workflow_command(self):
        evil = "evil\\n::error::forged ##[group]x"
        text = HEAD.split("jobs:\n")[0] + f'jobs:\n  "j{evil}":\n    uses: "o/r/.github/workflows/a.yml{evil}"\n'
        found = self.of(self.findings(text), "WF-5", "ERROR")
        self.assertEqual(len(found), 1)
        for text_ in (found[0].message, found[0].line()):
            self.assertEqual(len(text_.splitlines()), 1, text_)
            self.assertNotIn("::", text_)
            self.assertNotIn("##[", text_)

    def test_the_check_runs_inside_run_checks_so_the_whole_validator_reports_it(self):
        self.wf(EXTERNAL_CALLS["L6"], "zz-ext-reuse.yml")
        self.assertIn(("WF-5", "ERROR"), [(f.check, f.level) for f in vr.run_checks(self.root)])

    def test_a_real_wrapper_with_its_call_turned_into_an_external_one_is_caught(self):
        for name in ("blogger-en.yml", "blogger-ko.yml"):
            with self.subTest(name=name):
                self.setUp()
                old = "uses: ./.github/workflows/blogger.yml"
                self.wf(swapped(real_text(name), old, "uses: evil-org/evil-repo/.github/workflows/blogger.yml@main"), name)
                found = self.of(vr.check_workflows(self.root, [f".github/workflows/{name}"]), "WF-5", "ERROR")
                self.assertEqual(len(found), 1, [f.line() for f in found])
                self.setUp()
                self.wf(real_text(name), name)
                self.assertEqual(self.of(vr.check_workflows(self.root, [f".github/workflows/{name}"]), "WF-5"), [])      # 안 바꾼 진짜 파일은 지적 0


@NEEDS_YAML
class DockerStepAndUsesShapeTest(Case):
    STEP = HEAD + "    steps:\n      - uses: {uses}\n"

    def wf5(self, uses):
        return self.of(self.findings(self.STEP.format(uses=uses)), "WF-5")

    def test_a_docker_step_is_an_error_whatever_the_image_or_the_pin(self):
        for uses in ("docker://evil/image:latest", "docker://alpine:3.19", "docker://evil/image@sha256:" + "a" * 64, "docker://ghcr.io/o/i:1", "'Docker://Evil/Image:1'", "'  docker://evil/image:1'"):
            with self.subTest(uses=uses):
                found = self.wf5(uses)
                self.assertEqual([f.level for f in found], ["ERROR"])
                self.assertIn("docker://", found[0].message)
                one_plain_line(self, found[0])

    def test_the_unpinned_third_party_action_is_still_an_error_and_the_pinned_one_is_not(self):
        self.assertEqual([f.level for f in self.wf5("evil-org/evil-action@v1")], ["ERROR"])
        self.assertEqual(self.wf5(f"evil-org/evil-action@{SHA}"), [])
        self.assertEqual(self.wf5("actions/checkout@v6"), [])
        self.assertEqual(self.wf5("github/codeql-action/init@v3"), [])
        self.assertEqual([f.level for f in self.wf5("Actions/checkout@v6")], ["ERROR"])         # 대소문자가 다른 소유자는 첫 당사자가 아니다(옛 그대로)
        # 시험 렌즈 Q 의 Q02: SHA 판정을 4–40자로 풀어도 옛 시험이 모두 통과했다 — 짧은 해시·39자리·41자리·대문자·16진수가 아닌 글자는 고정이 아니다(정확히 40자리 소문자 16진수만 고정)
        for not_pinned in ("abc1234", SHA[:7], SHA[:12], SHA[:39], SHA + "0", SHA.upper(), SHA[:39] + "g", "z" * 40, "0" * 41, "0" * 39):
            with self.subTest(ref=not_pinned):
                found = self.wf5(f"evil-org/evil-action@{not_pinned}")
                self.assertEqual([f.level for f in found], ["ERROR"], not_pinned)
                self.assertIn("커밋 SHA 로 고정", found[0].message)
        for pinned in (SHA, "0" * 40, "f" * 40, "abcdef0123456789abcdef0123456789abcdef01"):
            with self.subTest(pinned=pinned):
                self.assertEqual(self.wf5(f"evil-org/evil-action@{pinned}"), [], pinned)

    def test_a_local_action_path_is_left_alone_here(self):
        self.assertEqual(self.wf5("./.github/actions/x"), [])
        self.assertEqual(self.wf5("./"), [])

    def test_only_the_exact_dot_slash_prefix_makes_a_path_local(self):
        """`./` 로 시작해야 이 저장소의 지역 액션이다 — 저장소 밖을 가리키는 `../` 나 점으로 시작하는 소유자 이름은 지역이 아니다(앞의 점 하나로 느슨하게 읽으면 통과해 버린다)."""
        for uses in ("../outside/action", ".hidden/x@v1", "'.\\x'", ".", "'.x/y@v1'"):
            with self.subTest(uses=uses):
                self.assertEqual([f.level for f in self.wf5(uses)], ["ERROR"], uses)

    def test_a_uses_shape_the_validator_cannot_read_is_an_error_not_a_pass(self):
        for uses in ("evil", "evil/action", "evil/action@", "'actions/checkout'", "'@v1'", "'a b/c@v1'", "'${{ matrix.action }}'"):
            with self.subTest(uses=uses):
                found = self.wf5(uses)
                self.assertEqual([f.level for f in found], ["ERROR"], uses)
                self.assertIn("읽지 못했습니다", found[0].message)

    def test_whitespace_around_a_pinned_third_party_action_does_not_hide_it_from_the_pin_rule(self):
        self.assertEqual([f.level for f in self.wf5("'  evil-org/evil-action@v1  '")], ["ERROR"])
        # 옛 시험은 여기서 `[]` 를 못박았다 — 공백을 깎고 비교하면 SHA 로 고정한 외부 액션 뒤의 공백이 기준(e39f0e2)의 오류를 지웠다(독립 검증 S 의 R5). 이제 앞뒤 공백이 있으면 읽지 못한 모양이라 오류다.
        found = self.wf5(f"'  evil-org/evil-action@{SHA}  '")
        self.assertEqual([f.level for f in found], ["ERROR"])
        self.assertIn("앞뒤에 공백", found[0].message)

    # 앞뒤에 붙을 수 있는 '공백' 모양(독립 검증 S 의 cases_ws.json 과 같은 갈래: 공백·탭·NBSP·유니코드 공백·줄바꿈·제어 문자·줄 구분자) — `str.strip()` 이 깎는 것들
    WHITESPACE = [" ", "  ", "\t", " ", " ", "　", "\r", "\r\n", "\n", "\x0b", "\x0c", "\x1c", "\x85", " ", " ", " \t "]

    def test_every_whitespace_shape_around_a_sha_pinned_external_action_is_an_error(self):
        """독립 검증 S 의 R5: SHA 로 고정한 외부 액션 뒤(또는 앞)에 공백·개행·NBSP·U+2003 등이 붙은 39개 모양에서 기준의 WF-5 오류가 0 으로 줄었다 — 이제 모두 오류다."""
        for owner in ("evil/x", "evil/x/sub", "Evil/X"):
            for white in self.WHITESPACE:
                for label, uses in (("trailing", f"{owner}@{SHA}{white}"), ("leading", f"{white}{owner}@{SHA}"), ("both", f"{white}{owner}@{SHA}{white}")):
                    with self.subTest(owner=owner, white=white, where=label):
                        found = vr._step_uses_findings("w.yml", uses)
                        self.assertEqual([(f.check, f.level) for f in found], [("WF-5", "ERROR")], repr(uses))
                        self.assertIn("앞뒤에 공백", found[0].message)
                        one_plain_line(self, found[0])
        for white in (" ", "\n", "\t"):                                                           # 진짜 YAML 글 한 번 거쳐도 같다(큰따옴표 글자의 이스케이프로 적는다)
            with self.subTest(yaml_white=white):
                self.assertEqual([f.level for f in self.wf5(json.dumps(f"evil/x@{SHA}{white}"))], ["ERROR"])

    def test_the_new_uses_check_never_accepts_what_the_old_one_flagged_and_the_clean_values_stay_clean(self):
        """'더 엄격한 쪽' 을 시험이 직접 계산한다: e39f0e2 의 단계 uses 검사(아래 복사)가 오류를 낸 모든 입력에서 새 검사도 오류를 낸다. 앞뒤 공백이 없는 SHA 고정·첫 당사자·지역 액션은 그대로 통과한다."""
        def old_flags(uses):
            if isinstance(uses, str) and not uses.startswith("./") and not uses.startswith("docker://"):
                found = vr._USES_RX.match(uses)
                if found and found.group(1) not in vr.FIRST_PARTY_OWNERS and not vr._SHA_RX.match(found.group(3)):
                    return True
            return False

        refs = (SHA, SHA[:39], SHA + "0", SHA.upper(), "v1", "main", "", "refs/heads/x")
        pads = ["", *self.WHITESPACE, "​", "­", "x"]
        checked = flagged_before = 0
        for owner in ("evil/x", "evil/x/sub", "Evil/X", "actions/checkout", "github/codeql-action/init", "Actions/checkout", "./local", "docker://evil/i"):
            for ref in refs:
                for pre in pads:
                    for post in pads:
                        uses = f"{pre}{owner}@{ref}{post}"
                        checked += 1
                        if old_flags(uses):
                            flagged_before += 1
                            self.assertNotEqual(vr._step_uses_findings("w.yml", uses), [], repr(uses))
        self.assertGreater(flagged_before, 800)                                                         # 비어서 통과하지 않는다
        self.assertGreater(checked, flagged_before)
        for clean in (f"evil/x@{SHA}", f"evil/x/sub@{SHA}", f"Evil/X@{SHA}", "actions/checkout@v6", "github/codeql-action/init@v3", "./.github/actions/x", "./"):
            with self.subTest(clean=clean):
                self.assertEqual(vr._step_uses_findings("w.yml", clean), [], clean)

    def test_a_real_workflow_with_a_docker_step_added_is_caught(self):
        for name, anchor in ((CHANCE, "      - uses: actions/checkout@v6\n"), ("sync-issue-form.yml", "      - uses: actions/checkout@v6\n")):
            with self.subTest(name=name):
                self.setUp()
                self.wf(swapped(real_text(name), anchor, "      - uses: docker://evil/image:latest\n" + anchor), name)
                found = self.of(vr.check_workflows(self.root, [f".github/workflows/{name}"]), "WF-5", "ERROR")
                self.assertEqual(len(found), 1, [f.line() for f in found])


@NEEDS_YAML
class RealRepositoryShapesTest(unittest.TestCase):
    def test_none_of_the_real_workflows_is_flagged_by_the_wf5_extension(self):
        """새 규칙이 지금 있는 파일을 하나도 새로 거절하지 않는다 — 진짜 워크플로 전부에서 WF-5 지적이 0 이다."""
        files = [f for f in vr.list_files(REAL) if f.startswith(".github/workflows/")]
        self.assertGreaterEqual(len(files), 20)
        self.assertEqual([f.line() for f in vr.check_workflows(REAL, files) if f.check == "WF-5"], [])

    def test_the_facts_the_rule_was_written_against_still_hold(self):
        """다른 저장소의 재사용 워크플로·docker:// 단계가 0 개라는 사실(그래서 SHA 로 고정한 것도 오류인 더 엄격한 쪽을 골랐다)이 바뀌면 이 시험이 알려 규칙을 다시 보게 한다."""
        calls, dockers, steps_with_uses = [], [], 0
        for path in sorted(WORKFLOWS.glob("*.yml")):
            data = yaml.safe_load(path.read_bytes().decode("utf-8"))
            for job_id, job in (data.get("jobs") or {}).items():
                if "uses" in job:
                    calls.append((path.name, job_id, job["uses"]))
                for step in job.get("steps") or []:
                    if isinstance(step.get("uses"), str):
                        steps_with_uses += 1
                        if step["uses"].lower().startswith("docker://"):
                            dockers.append((path.name, step["uses"]))
        self.assertGreaterEqual(len(calls), 2)                                                      # 지역 호출(블로그 래퍼)이 있다 — 빈 목록으로 통과하지 않는다
        self.assertTrue(all(call[2].startswith("./.github/workflows/") for call in calls), calls)   # 다른 저장소의 호출은 없다
        self.assertEqual(dockers, [])
        self.assertGreater(steps_with_uses, 30)

    def test_the_whole_validator_has_no_error_for_the_real_repository(self):
        findings = run_checks_once(REAL)
        self.assertEqual([f.line() for f in findings if f.level == "ERROR"], [])
        self.assertEqual([f.line() for f in findings if f.check == "WF-5"], [])


# ----------------------------------------------------------------------------
# ①b job 의 `container`·`services` 이미지 — `docker://` 단계와 같은 이유·같은 강도의 WF-5 오류(독립 검증 S 의 R2)
# ----------------------------------------------------------------------------
@NEEDS_YAML
class JobImageTest(Case):
    BODY = "    steps:\n      - run: echo hi\n"

    def job_with(self, extra):
        """HEAD(job j — runs-on·timeout-minutes) 뒤에 job 키 줄(들여쓰기 네 칸으로 붙인다)과 단계를 붙인 워크플로 글."""
        return HEAD + "".join("    " + line + "\n" for line in extra.splitlines()) + self.BODY

    def wf5(self, extra):
        return self.of(self.findings(self.job_with(extra)), "WF-5")

    def test_a_container_in_any_shape_is_an_error_that_names_the_job_and_the_image(self):
        for label, extra, image in (("string", "container: evil/x:latest", "evil/x:latest"),
                                    ("image", "container:\n  image: evil/x:latest", "evil/x:latest"),
                                    ("digest pinned", "container:\n  image: ghcr.io/o/i@sha256:" + "a" * 64, "ghcr.io/o/i@sha256:"),
                                    ("docker prefix", "container:\n  image: docker://evil/x:1", "docker://evil/x:1"),
                                    ("expression", "container:\n  image: ${{ matrix.image }}", "matrix.image"),
                                    ("options and env", "container:\n  image: node:20\n  options: --user root\n  env:\n    A: '1'", "node:20"),
                                    ("string expression", "container: ${{ matrix.image }}", "matrix.image")):
            with self.subTest(label=label):
                found = self.wf5(extra)
                self.assertEqual([f.level for f in found], ["ERROR"], [f.line() for f in found])
                self.assertIn("job j", found[0].message)
                self.assertIn("container", found[0].message)
                self.assertIn(image, found[0].message)
                self.assertEqual(found[0].path, ".github/workflows/w.yml")
                one_plain_line(self, found[0])

    def test_a_container_table_without_an_image_is_an_error_too_and_an_empty_one_is_not_a_container(self):
        found = self.wf5("container:\n  options: --user root")
        self.assertEqual([f.level for f in found], ["ERROR"])
        self.assertIn("이미지 없음", found[0].message)
        for label, extra in (("empty table", "container: {}"), ("empty string", "container: ''"), ("false", "container: false"), ("zero", "container: 0")):      # 비어 보여도 null 이 아니면 쓴 것이다(GitHub 가 거절하는 모양을 통과로 두지 않는다)
            with self.subTest(label=label):
                self.assertEqual([f.level for f in self.wf5(extra)], ["ERROR"], extra)
        self.assertEqual(self.wf5("container:"), [])                                                  # `container: null` — 쓰지 않는 것
        self.assertEqual(self.wf5("container: null"), [])

    def test_every_service_image_is_its_own_error_and_an_empty_services_table_is_not(self):
        found = self.wf5("services:\n  db:\n    image: postgres:16\n  cache:\n    image: redis:7")
        self.assertEqual([f.level for f in found], ["ERROR", "ERROR"], [f.line() for f in found])
        self.assertEqual([("services.db" in f.message, "services.cache" in f.message) for f in found], [(True, False), (False, True)])
        self.assertIn("postgres:16", found[0].message)
        self.assertIn("redis:7", found[1].message)
        for f in found:
            one_plain_line(self, f)
        for label, extra in (("empty table", "services: {}"), ("null", "services:"), ("explicit null", "services: null")):
            with self.subTest(label=label):
                self.assertEqual(self.wf5(extra), [])

    def test_a_service_in_a_shape_without_an_image_and_a_services_that_is_not_a_table_are_errors(self):
        for label, extra in (("string", "services:\n  db: postgres:16"), ("no image", "services:\n  db:\n    options: --health-cmd x"), ("empty service", "services:\n  db: {}"),
                             ("digest", "services:\n  db:\n    image: postgres@sha256:" + "b" * 64), ("expression", "services:\n  db:\n    image: ${{ matrix.db }}")):
            with self.subTest(label=label):
                self.assertEqual([f.level for f in self.wf5(extra)], ["ERROR"])
        for label, extra in (("list", "services: [a, b]"), ("string", "services: postgres"), ("number", "services: 5")):
            with self.subTest(label=label):
                found = self.wf5(extra)
                self.assertEqual([f.level for f in found], ["ERROR"])
                self.assertIn("표", found[0].message)

    def test_container_and_services_together_give_one_error_each_and_other_jobs_are_judged_separately(self):
        both = self.wf5("container: evil/x:1\nservices:\n  db:\n    image: postgres:16")
        self.assertEqual(len(both), 2)
        text = HEAD.split("jobs:\n")[0] + "jobs:\n  a:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    container: evil/a:1\n    steps:\n      - run: echo a\n" \
            "  b:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - run: echo b\n  c:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    container: evil/c:1\n    steps:\n      - run: echo c\n"
        found = self.of(self.findings(text), "WF-5")
        self.assertEqual([("job a" in f.message, "job c" in f.message) for f in found], [(True, False), (False, True)])

    def test_hostile_text_in_the_image_cannot_forge_a_workflow_command(self):
        evil = "evil\\n::error::forged ##[group]x"
        found = self.wf5('container: "' + evil + '"') + self.wf5('services:\n  "s' + evil + '":\n    image: "' + evil + '"')
        self.assertEqual(len(found), 2)
        for f in found:
            for text in (f.message, f.line()):
                self.assertEqual(len(text.splitlines()), 1, text)
                self.assertNotIn("::", text)
                self.assertNotIn("##[", text)

    def test_the_check_is_part_of_run_checks_so_the_whole_validator_reports_it(self):
        self.wf(self.job_with("container: evil/x:1"), "zz-container.yml")
        self.assertIn(("WF-5", "ERROR"), [(f.check, f.level) for f in vr.run_checks(self.root)])

    def test_the_docs_name_the_container_and_services_rule_and_the_whitespace_rule(self):
        guard = (REAL / "docs" / "SECURITY_GUARDRAILS.md").read_bytes().decode("utf-8").replace("\r\n", "\n")
        row = next(line for line in guard.split("\n") if line.startswith("| G-A4 |"))
        for needle in ("`container`·`services` 이미지", "검증기를 고치는 변경을 운영자가 검토한다", "앞뒤에 공백·줄바꿈이 붙은 것도 읽지 못한 모양"):
            self.assertIn(needle, row, needle)
        section = next(line for line in guard.split("\n") if line.startswith("| WF-0 / WF-1 / WF-3 / WF-4 / WF-5 / WF-9 |"))
        self.assertIn("job 의 `container`·`services` 이미지", section)
        register = (REAL / "docs" / "DEFECT_REGISTER.md").read_bytes().decode("utf-8").replace("\r\n", "\n")
        d490 = next(line for line in register.split("\n") if line.startswith("| **D-490** |"))
        for needle in ("`JobImageTest`", "독립 검증 S 의 R2·R5", "앞뒤에 공백·줄바꿈이 붙은 값은 읽지 못한 모양", "`services.<이름>` 이미지", "운영자가 검토한다"):
            self.assertIn(needle, d490, needle)

    def test_the_facts_the_rule_was_written_against_still_hold_no_real_job_has_a_container_or_services(self):
        """지금 저장소의 진짜 워크플로에는 container·services 가 하나도 없다(그래서 새로 거절하는 곳 0). 이 사실이 바뀌면 이 시험이 알려 규칙을 다시 보게 한다."""
        jobs = used = 0
        for path in sorted(WORKFLOWS.glob("*.yml")):
            data = yaml.safe_load(path.read_bytes().decode("utf-8"))
            for job in (data.get("jobs") or {}).values():
                jobs += 1
                used += sum(1 for key in ("container", "services") if key in job)
        self.assertGreater(jobs, 25)                                                                  # 비어서 통과하지 않는다
        self.assertEqual(used, 0)

    def test_the_real_workflows_are_clean_and_a_real_workflow_with_a_container_added_to_each_job_is_caught(self):
        files = [f for f in vr.list_files(REAL) if f.startswith(".github/workflows/")]
        self.assertEqual([f.line() for f in vr.check_workflows(REAL, files) if f.check == "WF-5"], [])
        anchor = "    runs-on: ubuntu-latest\n"
        for name in (CHANCE, "sync-issue-form.yml"):
            with self.subTest(name=name):
                text = real_text(name)
                count = text.count(anchor)
                self.assertGreaterEqual(count, 1)
                self.wf(text.replace(anchor, anchor + "    container: evil/x:latest\n"), name)
                found = self.of(vr.check_workflows(self.root, [f".github/workflows/{name}"]), "WF-5", "ERROR")
                self.assertEqual(len(found), count, [f.line() for f in found])
                self.setUp()


# ----------------------------------------------------------------------------
# ② 복합 액션 파일(`action.yml`)도 WF-4·WF-5 의 대상이다 — 지금 저장소에는 없어 '예방 규칙' 이다(감사 변이 L1)
# ----------------------------------------------------------------------------
ACTION =".github/actions/x/action.yml"
L1_ACTION = ('name: x\nruns:\n  using: composite\n  steps:\n    - uses: evil-org/evil-action@v1\n    - shell: bash\n      run: echo "${{ github.event.issue.title }}"\n')
CLEAN_ACTION = ('name: x\ndescription: d\nruns:\n  using: composite\n  steps:\n    - uses: actions/checkout@v6\n    - uses: evil-org/ok-action@' + SHA + '\n    - shell: bash\n      env:\n        TITLE: ${{ github.event.issue.title }}\n'
                '      run: echo "$TITLE"\n')


def composite_steps(*steps):
    """복합 액션 글 — 단계는 `- …` 줄들(앞 여섯 칸 들여쓰기는 알아서)."""
    return "name: x\ndescription: d\nruns:\n  using: composite\n  steps:\n" + "".join("    " + line + "\n" for step in steps for line in step.splitlines())


@NEEDS_YAML
class CompositeActionTest(Case):
    def check(self, text, rel=ACTION):
        self.put(rel, text)
        return vr.check_composite_actions(self.root, [rel])

    def test_the_audit_mutation_L1_is_both_an_injection_and_an_unpinned_action_and_each_is_one_error(self):
        found = self.check(L1_ACTION)
        self.assertEqual(sorted((f.check, f.level) for f in found), [("WF-4", "ERROR"), ("WF-5", "ERROR")], [f.line() for f in found])
        self.assertTrue(all(f.path == ACTION for f in found))
        self.assertIn("evil-org/evil-action@v1", [f for f in found if f.check == "WF-5"][0].message)
        for finding in found:
            one_plain_line(self, finding)

    def test_a_workflow_that_calls_the_action_stays_clean_and_the_error_is_in_the_action_file(self):
        self.put(ACTION, L1_ACTION)
        self.wf(HEAD + "    steps:\n      - uses: actions/checkout@v6\n      - uses: ./.github/actions/x\n", "zz-call-composite.yml")
        files = [ACTION, ".github/workflows/zz-call-composite.yml"]
        self.assertEqual(vr.check_workflows(self.root, files), [])                                      # 부르는 쪽 워크플로 자체는 지적 0
        self.assertEqual({f.path for f in vr.check_composite_actions(self.root, files)}, {ACTION})     # 오류는 액션 파일에서 난다
        self.assertIn(("WF-4", "ERROR"), [(f.check, f.level) for f in vr.run_checks(self.root)])        # 검증기 전체가 그것을 보고한다

    def test_a_clean_composite_action_passes_including_a_pinned_third_party_action_and_the_env_road(self):
        self.assertEqual(self.check(CLEAN_ACTION), [])

    def test_inputs_are_a_warning_like_in_a_workflow_and_every_other_untrusted_name_is_an_error(self):
        found = self.check(composite_steps('- shell: bash\n  run: echo "${{ inputs.name }}"'))
        self.assertEqual([(f.check, f.level) for f in found], [("WF-4", "WARN")])
        for expression in ("github.head_ref", "github.event.pull_request.title", "github.event.comment.body", "github.ref_name", "toJSON(github.event)", "format('{0}', github.event.issue.title)"):
            with self.subTest(expression=expression):
                found = self.check(composite_steps('- shell: bash\n  run: echo "${{ ' + expression + ' }}"'))
                self.assertEqual([(f.check, f.level) for f in found], [("WF-4", "ERROR")])

    def test_the_env_and_step_output_roads_are_read_in_a_composite_action_too(self):
        env_road = composite_steps('- shell: bash\n  env:\n    T: ${{ github.event.issue.title }}\n  run: echo "${{ env.T }}"')
        self.assertEqual([(f.check, f.level) for f in self.check(env_road)], [("WF-4", "ERROR")])
        output_road = composite_steps('- id: a\n  shell: bash\n  env:\n    X: ${{ github.event.issue.title }}\n  run: echo "t=$X" >> "$GITHUB_OUTPUT"',
                                      '- shell: bash\n  run: echo "${{ steps.a.outputs.t }}"')
        self.assertEqual([(f.check, f.level) for f in self.check(output_road)], [("WF-4", "ERROR")])

    def test_the_script_input_of_github_script_is_read_too(self):
        text = composite_steps("- uses: actions/github-script@v7\n  with:\n    script: |\n      console.log(`${{ github.event.issue.title }}`)")
        self.assertEqual([(f.check, f.level) for f in self.check(text)], [("WF-4", "ERROR")])

    def test_a_docker_step_a_docker_action_image_and_every_unreadable_uses_are_errors(self):
        for label, text in (("docker step", composite_steps("- uses: docker://evil/image:latest")),
                            ("docker action", "name: x\nruns:\n  using: docker\n  image: docker://evil/image:latest\n"),
                            ("docker action upper case", "name: x\nruns:\n  using: Docker\n  image: 'Docker://Evil/Image:1'\n"),
                            # 시험 렌즈 Q 의 Q14: 이미지 글의 앞뒤 공백을 접지 않으면 공백 붙은 docker:// 가 통과했다
                            ("docker action leading space", "name: x\nruns:\n  using: docker\n  image: ' docker://evil/image:1'\n"),
                            ("docker action trailing space", "name: x\nruns:\n  using: docker\n  image: 'docker://evil/image:1 '\n"),
                            ("docker action tab and newline", 'name: x\nruns:\n  using: docker\n  image: "\\t\\ndocker://evil/image:1\\n"\n'),
                            ("unreadable", composite_steps("- uses: evil"))):
            with self.subTest(label=label):
                found = self.check(text)
                self.assertEqual([(f.check, f.level) for f in found], [("WF-5", "ERROR")], [f.line() for f in found])
        self.assertEqual(self.check("name: x\nruns:\n  using: docker\n  image: Dockerfile\n"), [])        # 저장소의 Dockerfile 로 짓는 액션은 이 규칙이 보지 않는다(코드가 저장소 안에 있다)

    def test_a_local_action_called_from_a_composite_action_is_left_alone_and_a_node_action_is_not_read(self):
        self.assertEqual(self.check(composite_steps("- uses: ./.github/actions/other")), [])
        self.assertEqual(self.check("name: x\nruns:\n  using: node20\n  main: index.js\n"), [])

    def test_the_file_is_found_in_any_directory_in_both_spellings_and_any_letter_case_but_workflows_are_not_actions(self):
        # 워크플로 폴더의 하위 폴더(`.github/workflows/sub/action.yml`)는 읽는 이름이다 — 지역 액션은 `uses: ./.github/workflows/sub` 로 부를 수 있다(독립 검증 S 의 R1; 옛 시험은 이것을 '읽지 않는 이름' 에 넣어 구멍을 못박았다)
        names = ["action.yml", "action.yaml", ".github/actions/x/action.yml", "tools/y/z/action.yaml", "tools/ACTION.YML", ".github/actions/Deep/er/Action.Yaml",
                 ".github/workflows/sub/action.yml", ".github/workflows/sub/deep/action.yaml", ".github/workflows/Sub/ACTION.YML"]
        self.assertEqual(vr._composite_action_files(names), names)
        for other in ("my-action.yml", "action.yml.bak", "actions/x.yml", "action.json", ".github/workflows/action.yml", "docs/action.md"):
            self.assertEqual(vr._composite_action_files([other]), [], other)
        for rel in ("action.yml", "tools/y/action.yaml", "tools/ACTION.YML", ".github/workflows/sub/action.yml"):                          # 어디에 있든 같은 규칙을 받는다
            with self.subTest(rel=rel):
                self.assertEqual(sorted((f.check, f.level) for f in self.check(L1_ACTION, rel)), [("WF-4", "ERROR"), ("WF-5", "ERROR")])

    def test_a_workflow_that_happens_to_be_named_action_yml_is_a_workflow_and_not_read_as_an_action(self):
        rel = self.wf(HEAD + "    steps:\n      - run: echo hi\n", "action.yml")
        self.assertEqual(vr.check_composite_actions(self.root, [rel]), [])
        for name in ("action.yaml", "ACTION.YML", "Action.Yaml"):                                  # 워크플로 폴더 바로 아래의 어떤 철자든 워크플로다(워크플로 쪽 규칙이 읽는다)
            with self.subTest(name=name):
                self.assertEqual(vr._composite_action_files([f".github/workflows/{name}"]), [])

    SUBFOLDER = ".github/workflows/subaction/action.yml"

    def test_a_composite_action_in_a_subfolder_of_the_workflows_folder_gets_every_rule(self):
        """독립 검증 S 의 R1: 워크플로 폴더의 하위 폴더는 워크플로가 아니라 지역 액션이다(`uses: ./.github/workflows/subaction`). 옛 코드는 폴더 접두사로 통째로 빼서 WF-4·WF-5·docker 이미지 규칙이 모두 침묵했다."""
        for rel in (self.SUBFOLDER, ".github/workflows/sub/deep/action.yaml", ".github/workflows/Sub/ACTION.YML"):
            with self.subTest(rel=rel, rule="injection and unpinned"):
                found = self.check(L1_ACTION, rel)
                self.assertEqual(sorted((f.check, f.level) for f in found), [("WF-4", "ERROR"), ("WF-5", "ERROR")], [f.line() for f in found])
                self.assertTrue(all(f.path == rel for f in found))
            with self.subTest(rel=rel, rule="docker step"):
                found = self.check(composite_steps("- uses: docker://evil/image:latest"), rel)
                self.assertEqual([(f.check, f.level) for f in found], [("WF-5", "ERROR")], [f.line() for f in found])
            with self.subTest(rel=rel, rule="docker action image"):
                found = self.check("name: x\nruns:\n  using: docker\n  image: docker://evil/image:latest\n", rel)
                self.assertEqual([(f.check, f.level) for f in found], [("WF-5", "ERROR")], [f.line() for f in found])
            with self.subTest(rel=rel, rule="clean action stays clean"):
                self.assertEqual(self.check(CLEAN_ACTION, rel), [])

    def test_the_audit_probe_a_workflow_calling_the_subfolder_action_reports_the_errors_at_the_action_file(self):
        """탐침 그대로: `.github/workflows/subaction/action.yml`(composite — 주입 run·SHA 없는 외부 액션·docker:// 단계)과 그것을 `uses: ./.github/workflows/subaction` 으로 부르는 워크플로."""
        probe = composite_steps('- shell: bash\n  run: echo "${{ github.event.issue.title }}"', "- uses: evil/x@v1", "- uses: docker://alpine:3")
        self.put(self.SUBFOLDER, probe)
        self.wf(HEAD + "    steps:\n      - uses: actions/checkout@v6\n      - uses: ./.github/workflows/subaction\n", "zz-call-subaction.yml")
        files = [self.SUBFOLDER, ".github/workflows/zz-call-subaction.yml"]
        self.assertEqual(vr.check_workflows(self.root, files), [])                                       # 부르는 쪽 워크플로 자체는 지적 0
        found = vr.check_composite_actions(self.root, files)
        self.assertEqual(sorted((f.check, f.level) for f in found), [("WF-4", "ERROR"), ("WF-5", "ERROR"), ("WF-5", "ERROR")], [f.line() for f in found])
        self.assertEqual({f.path for f in found}, {self.SUBFOLDER})
        whole = [(f.check, f.level, f.path) for f in vr.run_checks(self.root) if f.path == self.SUBFOLDER]                  # 검증기 전체도 같다(run_checks 가 목록을 직접 만든다)
        self.assertEqual(sorted(whole), [("WF-4", "ERROR", self.SUBFOLDER), ("WF-5", "ERROR", self.SUBFOLDER), ("WF-5", "ERROR", self.SUBFOLDER)])

    def test_the_docs_say_that_only_the_files_directly_under_the_workflows_folder_are_left_out(self):
        guard = (REAL / "docs" / "SECURITY_GUARDRAILS.md").read_bytes().decode("utf-8").replace("\r\n", "\n")
        row = next(line for line in guard.split("\n") if line.startswith("| G-A2 |"))
        self.assertIn("바로 아래의 같은 이름 파일(그것은 워크플로)만 빼고 그 하위 폴더도 읽는다", row)
        self.assertNotIn("워크플로 폴더는 제외", row)
        register = (REAL / "docs" / "DEFECT_REGISTER.md").read_bytes().decode("utf-8").replace("\r\n", "\n")
        d491 = next(line for line in register.split("\n") if line.startswith("| **D-491** |"))
        self.assertIn("**바로 아래** 의 같은 이름 파일만 제외", d491)
        self.assertIn("워크플로 폴더의 하위 폴더에도 둘 수 있다", d491)
        self.assertNotIn("(워크플로 폴더는 제외", d491)

    def test_a_broken_action_file_is_an_error_and_never_a_crash(self):
        for label, text in (("syntax", "name: [unclosed\n"), ("list at the top", "- a\n- b\n"), ("no runs", "name: x\n"), ("runs is a string", "name: x\nruns: composite\n"),
                            ("steps missing", "name: x\nruns:\n  using: composite\n"), ("steps is a map", "name: x\nruns:\n  using: composite\n  steps:\n    a: 1\n"), ("empty", ""),
                            ("unknown using", "name: x\nruns:\n  using: weird\n"), ("using missing", "name: x\nruns:\n  main: index.js\n"),
                            # 시험 렌즈 Q 의 Q11: node 계열 판정을 n 으로 시작하는 모든 값으로 풀어도 옛 시험이 통과했다 — node 로 시작하지 않는 모르는 값은 모두 읽지 못한 모양이다
                            ("using nope", "name: x\nruns:\n  using: nope\n"), ("using n", "name: x\nruns:\n  using: n\n"), ("using number", "name: x\nruns:\n  using: 5\n"),
                            ("using empty", "name: x\nruns:\n  using: ''\n"), ("using null", "name: x\nruns:\n  using:\n"), ("using nu", "name: x\nruns:\n  using: nushell\n")):
            with self.subTest(label=label):
                found = self.check(text)
                self.assertEqual([(f.check, f.level) for f in found], [("WF-0", "ERROR")], [f.line() for f in found])
                one_plain_line(self, found[0])
        self.assertEqual(self.check(composite_steps("- 5", "- run")), [])                                 # 단계가 표가 아닌 항목은 건너뛴다(GitHub 가 거절하는 모양이라 여기서 따로 알리지 않는다)

    def test_the_hostile_text_of_a_uses_cannot_forge_a_workflow_command(self):
        evil = "evil\\n::error::forged ##[group]x"
        found = self.check(composite_steps('- uses: "o/r@v1' + evil + '"'))
        self.assertEqual(len([f for f in found if f.check == "WF-5"]), 1)
        for finding in found:
            for text in (finding.message, finding.line()):
                self.assertEqual(len(text.splitlines()), 1, text)
                self.assertNotIn("::", text)
                self.assertNotIn("##[", text)

    def test_the_check_is_part_of_run_checks_and_quiet_without_pyyaml(self):
        self.put(ACTION, L1_ACTION)
        self.assertIn(("WF-5", "ERROR"), [(f.check, f.level) for f in vr.run_checks(self.root) if f.path == ACTION])
        with mock.patch.object(vr, "yaml", None):
            self.assertEqual(vr.check_composite_actions(self.root, [ACTION]), [])

    def test_the_real_repository_has_nothing_the_rule_flags(self):
        files = vr.list_files(REAL)
        self.assertEqual([f.line() for f in vr.check_composite_actions(REAL, files)], [])


# ----------------------------------------------------------------------------
# ④ WF-4 의 신뢰 못 할 칸 확장 — shell·working-directory·runs-on·container·services·체크아웃 ref(·repository)·defaults.run (감사 탐침 §1b)
# ----------------------------------------------------------------------------
UNTRUSTED = ("github.event.issue.title", "github.head_ref", "github.ref_name", "github.event.pull_request.title", "github.event.comment.body", "toJSON(github.event)",
             "github['event']['issue']['title']", "format('{0}', github.event.head_commit.message)", "github.event.workflow_run.head_branch", "github.event.pull_request.head.ref")
TITLE = "${{ github.event.issue.title }}"


def sink_workflow(where, value):
    """감사 탐침과 같은 모양의 워크플로 — `where` 칸에 value 를 넣는다."""
    head = HEAD.replace("runs-on: ubuntu-latest", f"runs-on: {value}" if where == "runs-on" else "runs-on: ubuntu-latest")
    if where == "runs-on":
        return head + "    steps:\n      - run: echo hi\n"
    if where == "shell":
        return head + f"    steps:\n      - name: x\n        shell: {value}\n        run: echo hi\n"
    if where == "working-directory":
        return head + f"    steps:\n      - name: x\n        working-directory: {value}\n        run: echo hi\n"
    if where == "container.image":
        return head + f"    container:\n      image: {value}\n    steps:\n      - run: echo hi\n"
    if where == "container.options":
        return head + f"    container:\n      image: python:3.12\n      options: {value}\n    steps:\n      - run: echo hi\n"
    if where == "container.env":
        return head + f"    container:\n      image: python:3.12\n      env:\n        X: {value}\n    steps:\n      - run: echo hi\n"
    if where == "container string":
        return head + f"    container: {value}\n    steps:\n      - run: echo hi\n"
    if where == "services.image":
        return head + f"    services:\n      db:\n        image: {value}\n    steps:\n      - run: echo hi\n"
    if where == "services.env":
        return head + f"    services:\n      db:\n        image: redis\n        env:\n          X: {value}\n    steps:\n      - run: echo hi\n"
    if where == "checkout.ref":
        return head + f"    steps:\n      - uses: actions/checkout@v6\n        with:\n          ref: {value}\n"
    if where == "checkout.repository":
        return head + f"    steps:\n      - uses: actions/checkout@v6\n        with:\n          repository: {value}\n"
    if where == "job defaults shell":
        return head + f"    defaults:\n      run:\n        shell: {value}\n    steps:\n      - run: echo hi\n"
    if where == "job defaults working-directory":
        return head + f"    defaults:\n      run:\n        working-directory: {value}\n    steps:\n      - run: echo hi\n"
    if where == "workflow defaults shell":
        return head.replace("jobs:\n", f"defaults:\n  run:\n    shell: {value}\njobs:\n", 1) + "    steps:\n      - run: echo hi\n"
    if where == "workflow defaults working-directory":
        return head.replace("jobs:\n", f"defaults:\n  run:\n    working-directory: {value}\njobs:\n", 1) + "    steps:\n      - run: echo hi\n"
    raise AssertionError(where)


SINKS = ("runs-on", "shell", "working-directory", "container.image", "container.options", "container.env", "container string", "services.image", "services.env",
         "checkout.ref", "checkout.repository", "job defaults shell", "job defaults working-directory", "workflow defaults shell", "workflow defaults working-directory")


@NEEDS_YAML
class ConfigSinkTest(Case):
    def wf4(self, text):
        return self.of(self.findings(text), "WF-4")

    def test_an_untrusted_expression_in_each_new_sink_is_one_error_that_names_the_sink(self):
        words = {"runs-on": "runs-on", "shell": "shell", "working-directory": "working-directory", "checkout.ref": "with.ref", "checkout.repository": "with.repository",
                 "job defaults shell": "defaults.run", "job defaults working-directory": "defaults.run", "workflow defaults shell": "defaults.run", "workflow defaults working-directory": "defaults.run"}
        for where in SINKS:
            with self.subTest(where=where):
                found = self.wf4(sink_workflow(where, TITLE))
                self.assertEqual([f.level for f in found], ["ERROR"], [f.line() for f in found])
                self.assertIn(words.get(where, where.split()[0].split(".")[0]), found[0].message)
                self.assertIn("신뢰할 수 없는 입력을 직접 보간", found[0].message)
                one_plain_line(self, found[0])

    def test_every_untrusted_context_the_run_sink_knows_is_an_error_in_the_new_sinks_too(self):
        for expression in UNTRUSTED:
            for where in ("runs-on", "shell", "working-directory", "container.image", "services.image", "checkout.ref", "workflow defaults shell"):
                with self.subTest(expression=expression, where=where):
                    quoted = '"${{ ' + expression + ' }}"'                                                       # 따옴표를 둘러 YAML 이 식 안의 따옴표·중괄호를 글자로 읽게 한다
                    self.assertEqual([f.level for f in self.wf4(sink_workflow(where, quoted))], ["ERROR"])

    def test_inputs_stay_a_warning_in_the_new_sinks_as_they_are_in_run(self):
        for where in SINKS:
            with self.subTest(where=where):
                found = self.wf4(sink_workflow(where, "${{ inputs.value }}"))
                self.assertEqual([f.level for f in found], ["WARN"], [f.line() for f in found])
                self.assertIn("inputs", found[0].message)

    def test_values_that_are_fixed_or_not_attacker_chosen_are_clean_in_every_new_sink(self):
        for value in ("ubuntu-latest", "'3.12'", "${{ github.sha }}", "${{ github.event.repository.default_branch }}", "${{ github.repository }}", "${{ runner.os }}", "${{ vars.RUNNER }}",
                      "${{ github.event_name == 'pull_request' && github.event.repository.default_branch || github.sha }}", "${{ secrets.SOME_SECRET }}"):
            for where in SINKS:
                with self.subTest(value=value, where=where):
                    self.assertEqual(self.wf4(sink_workflow(where, value)), [])

    def test_the_env_road_into_a_sink_follows_the_same_taint_rules_as_run(self):
        text = sink_workflow("working-directory", "${{ env.D }}").replace("    steps:\n", f"    env:\n      D: {TITLE}\n    steps:\n", 1)
        self.assertEqual([f.level for f in self.wf4(text)], ["ERROR"])
        fixed = sink_workflow("working-directory", "${{ env.D }}").replace("    steps:\n", "    env:\n      D: sub/dir\n    steps:\n", 1)
        self.assertEqual(self.wf4(fixed), [])
        unknown = sink_workflow("working-directory", "${{ env.NOWHERE }}")
        self.assertEqual([f.level for f in self.wf4(unknown)], ["WARN"])

    def test_the_step_output_road_into_a_checkout_ref_is_an_error(self):
        steps = ("    steps:\n      - id: a\n        env:\n          X: " + TITLE + '\n        run: echo "t=$X" >> "$GITHUB_OUTPUT"\n'
                 "      - uses: actions/checkout@v6\n        with:\n          ref: ${{ steps.a.outputs.t }}\n")
        self.assertEqual([f.level for f in self.wf4(HEAD + steps)], ["ERROR"])
        clean = HEAD + "    steps:\n      - id: a\n        run: echo hi\n      - uses: actions/checkout@v6\n        with:\n          ref: ${{ steps.nowhere.outputs.t }}\n"
        self.assertEqual([f.level for f in self.wf4(clean)], ["WARN"])                                  # 출처를 알 수 없는 길은 경고

    def test_a_matrix_in_runs_on_is_clean_when_fixed_a_warning_when_computed_and_an_error_when_tainted(self):
        base = HEAD.replace("runs-on: ubuntu-latest", "runs-on: ${{ matrix.os }}") + "    steps:\n      - run: echo hi\n"
        fixed = base.replace("    steps:\n", "    strategy:\n      matrix:\n        os: [ubuntu-latest, ubuntu-22.04]\n    steps:\n", 1)
        self.assertEqual(self.wf4(fixed), [])
        computed = base.replace("    steps:\n", "    strategy:\n      matrix:\n        os: ${{ fromJSON(needs.plan.outputs.os) }}\n    steps:\n", 1)
        self.assertEqual([f.level for f in self.wf4(computed)], ["WARN"])
        tainted = base.replace("    steps:\n", f"    strategy:\n      matrix:\n        os:\n          - {TITLE}\n    steps:\n", 1)
        self.assertEqual([f.level for f in self.wf4(tainted)], ["ERROR"])

    def test_with_of_other_actions_and_other_step_keys_are_still_not_sinks(self):
        """run·script 와 새 칸만 읽는다 — 다른 액션의 with·단계 이름·if·env 는 여전히 칸이 아니다(옛 시험 `only_run_and_script_are_sinks` 와 같은 뜻)."""
        text = (HEAD + "    steps:\n      - uses: actions/cache@v4\n        with:\n          key: " + TITLE + "\n          ref: " + TITLE + "\n"
                "      - name: " + TITLE + "\n        if: github.head_ref != ''\n        env:\n          X: " + TITLE + "\n        run: echo hi\n")
        self.assertEqual(self.wf4(text), [])

    def test_the_checkout_action_is_recognised_in_any_letter_case_and_with_a_ref_suffix(self):
        for uses in ("actions/checkout@v6", "ACTIONS/CHECKOUT@v6", "actions/checkout@" + SHA, "Actions/Checkout@main"):
            with self.subTest(uses=uses):
                text = HEAD + f"    steps:\n      - uses: {uses}\n        with:\n          ref: {TITLE}\n"
                self.assertEqual([f.level for f in self.wf4(text)], ["ERROR"])

    def test_a_ref_on_a_non_string_value_or_a_missing_with_is_not_read_and_never_crashes(self):
        for step in ("- uses: actions/checkout@v6\n", "- uses: actions/checkout@v6\n  with: x\n", "- uses: actions/checkout@v6\n  with:\n    ref: 5\n", "- uses: actions/checkout@v6\n  with:\n    ref: [a, b]\n",
                     "- uses: actions/checkout@v6\n  with:\n    ref:\n", "- run: echo hi\n  shell: [a]\n", "- run: echo hi\n  working-directory: 5\n"):
            with self.subTest(step=step):
                text = HEAD + "    steps:\n" + "".join("      " + line + "\n" for line in step.splitlines())
                self.assertEqual(self.wf4(text), [])

    def test_a_real_workflow_with_the_untrusted_expression_put_into_each_sink_is_caught(self):
        cases = (("watchdog.yml", "runs-on: ubuntu-latest", f"runs-on: {TITLE}"),
                 ("sync-issue-form.yml", "      - uses: actions/checkout@v6\n", f"      - uses: actions/checkout@v6\n        with:\n          ref: {TITLE}\n"),
                 ("issue-edit.yml", "ref: ${{ github.event.repository.default_branch }}", f"ref: {TITLE}"),
                 ("ops-inbox.yml", "      - uses: actions/setup-python@v6\n", f"      - uses: actions/setup-python@v6\n        working-directory: {TITLE}\n"),
                 ("pages.yml", "    runs-on: ubuntu-latest\n    timeout-minutes: 15\n", f"    runs-on: ubuntu-latest\n    timeout-minutes: 15\n    container: {TITLE}\n"))
        for name, old, new in cases:
            with self.subTest(name=name):
                self.setUp()
                text = real_text(name)
                count = text.count(old)
                self.assertGreaterEqual(count, 1, (name, old))
                self.wf(text.replace(old, new, 1), name)
                found = [f for f in vr.check_workflows(self.root, [f".github/workflows/{name}"]) if f.check == "WF-4" and f.level == "ERROR"]
                self.assertEqual(len(found), 1, [f.line() for f in found])
                self.setUp()
                self.wf(text, name)
                self.assertEqual([f for f in vr.check_workflows(self.root, [f".github/workflows/{name}"]) if f.check == "WF-4"], [])      # 안 바꾼 진짜 파일은 지적 0

    def test_the_same_sinks_are_read_in_a_composite_action_step(self):
        for key, value in (("shell", TITLE), ("working-directory", "${{ github.head_ref }}")):
            with self.subTest(key=key):
                self.put(ACTION, composite_steps(f"- {key}: {value}\n  run: echo hi"))
                found = [f for f in vr.check_composite_actions(self.root, [ACTION]) if f.check == "WF-4"]
                self.assertEqual([f.level for f in found], ["ERROR"])
        self.put(ACTION, composite_steps("- uses: actions/checkout@v6\n  with:\n    ref: " + TITLE))
        self.assertEqual([f.level for f in vr.check_composite_actions(self.root, [ACTION]) if f.check == "WF-4"], ["ERROR"])

    def test_the_run_and_script_sinks_keep_their_old_messages(self):
        found = self.wf4(HEAD + "    steps:\n      - run: echo \"" + TITLE + "\"\n")
        self.assertEqual([f.level for f in found], ["ERROR"])
        self.assertIn("run 안에서 신뢰할 수 없는 입력을 직접 보간합니다 — env 로 넘기세요 (G-A2)", found[0].message)


@NEEDS_YAML
class RealRepositoryConfigSinksTest(unittest.TestCase):
    def test_no_real_workflow_is_flagged_for_any_wf4_finding_after_the_sinks_were_widened(self):
        files = [f for f in vr.list_files(REAL) if f.startswith(".github/workflows/")]
        self.assertGreaterEqual(len(files), 20)
        self.assertEqual([f.line() for f in vr.check_workflows(REAL, files) if f.check == "WF-4"], [])

    def test_the_new_sinks_are_really_read_in_the_real_files_so_the_empty_result_above_is_not_vacuous(self):
        """진짜 워크플로에서 새 칸의 글(runs-on 전부·체크아웃 ref)을 실제로 읽어 모았다 — 비어 있어서 통과한 것이 아니다."""
        texts = []
        for path in sorted(WORKFLOWS.glob("*.yml")):
            data = yaml.safe_load(path.read_bytes().decode("utf-8"))
            texts += [value for _where, value in vr._scope_config_texts({"defaults": data.get("defaults")})]
            for job in (data.get("jobs") or {}).values():
                texts += [value for _where, value in vr._scope_config_texts(job)]
                for step in job.get("steps") or []:
                    texts += [value for _where, value in vr._config_sink_texts(step)]
        self.assertGreater(len(texts), 30)
        self.assertIn("ubuntu-latest", texts)
        self.assertIn("${{ github.event.repository.default_branch }}", texts)
        self.assertEqual([text for text in texts if vr._untrusted_expression(text)], [])


# ----------------------------------------------------------------------------
# 문서 줄 — 결함 D-490·D-491·D-493 행, 안전 규칙 G-A2 행, 엔지니어링 가이드 W2 행을 한 줄씩 읽는다(시험 렌즈 Q 의 Q55·Q56 — 이 줄들을 지워도 모든 시험이 통과했다)
# ----------------------------------------------------------------------------
class DocsRowsTest(unittest.TestCase):
    @staticmethod
    def text(rel):
        return (REAL / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")

    def row(self, rel, prefix, cells):
        rows = [line for line in self.text(rel).split("\n") if line.startswith(prefix)]
        self.assertEqual(len(rows), 1, prefix)
        self.assertEqual(rows[0].replace("\\|", "").count("|"), cells + 1, f"{prefix} — 글 안에 파이프 글자를 그대로 쓰면 표의 칸이 깨진다")
        for forbidden in ("{{", "{%", "http://", "https://"):
            self.assertNotIn(forbidden, rows[0], (prefix, forbidden))
        return rows[0]

    def test_d490_names_the_rule_the_second_round_changes_and_the_facts(self):
        row = self.row("docs/DEFECT_REGISTER.md", "| **D-490** |", 6)
        for needle in ("**해결**", "WF-5", "`docker://`", "`ReusableWorkflowCallTest`", "`DockerStepAndUsesShapeTest`", "`JobImageTest`", "`RealRepositoryShapesTest`", "D13·L6·L7·L8", "독립 감사 BA-S2 R3-①",
                       "운영자 확인 040 ① 승인", "블로그 래퍼 둘의 지역 호출뿐", "`_step_uses_findings`", "독립 검증 S 의 R2·R5", "앞뒤에 공백·줄바꿈이 붙은 값은 읽지 못한 모양", "`services.<이름>` 이미지", "운영자가 검토한다",
                       "복합 액션 파일 안의 단계는 D-491 이 같은 함수로 읽는다"):
            self.assertIn(needle, row, needle)

    def test_d491_names_the_composite_action_rule_its_folder_rule_and_what_stays_open(self):
        row = self.row("docs/DEFECT_REGISTER.md", "| **D-491** |", 6)
        for needle in ("**해결**(예방)", "`check_composite_actions`", "`action.yml`·`action.yaml`", "**바로 아래**", "워크플로 폴더의 하위 폴더에도 둘 수 있다", "독립 검증 S 의 R1", "`CompositeActionTest`",
                       "독립 감사 BA-S2 R3-②", "운영자 확인 040 ① 승인", "node 계열은 자바스크립트 코드라 읽지 않고", "WF-0", "**남은 것**"):
            self.assertIn(needle, row, needle)
        self.assertNotIn("(워크플로 폴더는 제외", row)

    def test_d493_names_the_widened_sinks_the_tests_and_what_is_still_not_read(self):
        row = self.row("docs/DEFECT_REGISTER.md", "| **D-493** |", 6)
        for needle in ("**해결**", "WF-4", "`shell`·`working-directory`", "`runs-on`·`container`", "`services`", "`with.ref`", "`ConfigSinkTest`", "`RealRepositoryConfigSinksTest`", "`defaults.run`", "`with.repository`",
                       "`inputs` 직접 보간은 경고(설계 그대로)", "독립 감사 BA-S2 R3-④", "운영자 확인 040 ① 승인", "**남은 것**", "`jobs.<id>.environment`"):
            self.assertIn(needle, row, needle)

    def test_the_g_a2_row_and_the_w2_row_name_the_config_sinks_and_the_composite_action_files(self):
        guard = self.row("docs/SECURITY_GUARDRAILS.md", "| G-A2 |", 3)
        for needle in ("**설정 칸도 같다**", "`shell`·`working-directory`", "`runs-on`·`container`", "`services`", "`with.ref`·`with.repository`", "결함 D-493", "**지역 복합 액션 파일**", "결함 D-491",
                       "바로 아래의 같은 이름 파일(그것은 워크플로)만 빼고 그 하위 폴더도 읽는다", "`docker://` 금지(G-A4)", "WF-4"):
            self.assertIn(needle, guard, needle)
        w2 = self.row("docs/ENGINEERING_GUIDE.md", "| W2 |", 3)
        for needle in ("`env:`로 받아", "설정 칸", "`shell`·`working-directory`", "`runs-on`·`container`·`services`", "`with.ref`·`with.repository`", "**WF-4**", "복합 액션 파일을 부르는 쪽이 `with` 로 넘기는 값"):
            self.assertIn(needle, w2, needle)

    def test_the_wf14_row_and_d494_name_the_setup_python_rule_with_the_exact_key(self):
        wf14 = self.row("docs/SECURITY_GUARDRAILS.md", "| WF-14 |", 3)
        for needle in ("setup-python", "`with` 는 `python-version` 뿐이고", "`pip-install`·`cache`·`token`", "결함 D-494"):
            self.assertIn(needle, wf14, needle)
        d494 = self.row("docs/DEFECT_REGISTER.md", "| **D-494** |", 6)
        for needle in ("**해결**", "`pip-install`", "`cache`", "`token`", "`tests/test_operator_loop_workflows.py`", "`WorkflowRuleTest`", "독립 감사 BA-S2 N1", "운영자 확인 040 ① 승인", "앞뒤 공백이 붙은 `python-version` 도 오류",
                       "시험 렌즈 Q 의 Q37", "**남은 것**", "WF-15·WF-16·DEP-3"):
            self.assertIn(needle, d494, needle)


if __name__ == "__main__":
    unittest.main()
