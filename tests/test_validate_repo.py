import io
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import _bootstrap  # noqa: F401
from edits_helpers import make_edit_root
from test_run import make_root

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402
from pipeline import registry as reg_mod  # noqa: E402

REAL = _bootstrap.ROOT


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return path


def checks(findings):
    return sorted({f.check for f in findings})


def levels(findings, check):
    return sorted(f.level for f in findings if f.check == check)


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)


class RealRepoTest(unittest.TestCase):
    def test_repository_has_no_guardrail_errors(self):
        errors = [f.line() for f in vr.run_checks(REAL) if f.level == "ERROR"]
        self.assertEqual(errors, [])


class SecretTest(TmpCase):
    def test_forbidden_files(self):
        for name in ("client_secret.json", "client_secret_123.apps.googleusercontent.com.json", "token.json",
                     ".env", ".env.production", "server.pem", "id_rsa", "my-service-account.json"):
            write(self.root, name, "x")
        write(self.root, ".env.example", "SAFE=1")   # 예시 파일은 허용
        write(self.root, "tokens.md", "notes")       # 이름이 비슷해도 JSON 이 아니면 허용
        found = vr.check_forbidden_files(vr.list_files(self.root))
        self.assertEqual(len(found), 8)
        self.assertTrue(all(f.check == "SEC-1" and f.level == "ERROR" for f in found))

    def test_secret_patterns_detected_and_masked(self):
        fakes = {
            "google_key": "AIza" + "B" * 35,
            "oauth": "GOCSPX-" + "c" * 24,
            "refresh": "1//0" + "d" * 45,
            "access": "ya29." + "e" * 40,
            "ghp": "ghp_" + "f" * 36,
            "pem": "-----BEGIN " + "PRIVATE KEY-----",
        }
        for name, value in fakes.items():
            write(self.root, f"{name}.txt", f"x = {value}\n")
        write(self.root, "assign.py", 'api_key = "' + "g" * 30 + '"\n')
        write(self.root, "client.json", '{"client_secret": "' + "h" * 20 + '"}\n')
        found = vr.check_secret_patterns(self.root, vr.list_files(self.root))
        self.assertEqual(len(found), len(fakes) + 2)
        joined = " ".join(f.message for f in found)
        for value in fakes.values():
            self.assertNotIn(value, joined)  # 값 전체는 출력하지 않는다

    def test_allow_marker_and_env_name_mapping_are_not_flagged(self):
        write(self.root, "doc.md", "AIza" + "B" * 35 + "  # validate-repo: allow\n")
        write(self.root, "reg.json", '{"client_secret": "BLOGGER_CLIENT_SECRET"}\n')
        self.assertEqual(vr.check_secret_patterns(self.root, vr.list_files(self.root)), [])


BAD_WORKFLOW = """
name: bad
on:
  pull_request_target:
  schedule:
    - cron: '0 0 * * *'
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - uses: someone/evil-action@v1
      - uses: actions/checkout@v4
      - run: echo "${{ github.event.issue.title }}"
      - run: echo ${{ secrets.TOKEN }}
      - run: do_it || true
      - run: echo "${{ inputs.name }}"
"""

GOOD_WORKFLOW = """
name: good
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  j:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: someone/ok-action@0123456789abcdef0123456789abcdef01234567
      - env:
          TITLE: ${{ github.event.issue.title }}
        run: echo "$TITLE"
"""


class WorkflowTest(TmpCase):
    def run_wf(self, text):
        write(self.root, ".github/workflows/w.yml", text)
        return vr.check_workflows(self.root, vr.list_files(self.root))

    def test_bad_workflow_is_flagged(self):
        found = self.run_wf(BAD_WORKFLOW)
        self.assertEqual(levels(found, "WF-1"), ["ERROR"])
        self.assertEqual(levels(found, "WF-3"), ["ERROR"])
        self.assertIn("ERROR", levels(found, "WF-4"))
        self.assertIn("WARN", levels(found, "WF-4"))     # inputs 직접 보간은 경고
        self.assertEqual(levels(found, "WF-5"), ["ERROR"])
        self.assertEqual(levels(found, "WF-9"), ["ERROR"])
        self.assertIn("WARN", levels(found, "WF-6"))
        self.assertEqual(levels(found, "WF-7"), ["WARN"])
        self.assertEqual(levels(found, "WF-8"), ["WARN"])

    def test_good_workflow_is_clean(self):
        self.assertEqual(self.run_wf(GOOD_WORKFLOW), [])

    def test_write_all_and_syntax_error(self):
        found = self.run_wf("name: x\non: push\npermissions: write-all\njobs: {}\n")
        self.assertEqual(levels(found, "WF-1"), ["ERROR"])
        found = self.run_wf("name: [unclosed\n")
        self.assertEqual(levels(found, "WF-0"), ["ERROR"])


KOREAN_NAMES_WORKFLOW = """
name: "[공통] 사이트 자동 배포"
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  build:
    name: 사이트 빌드
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo ok
  test:
    name: 검사 (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    timeout-minutes: 5
    strategy:
      matrix:
        python-version: ['3.10', '3.12']
    steps:
      - run: echo ok
"""


class WorkflowNameTest(TmpCase):
    """WF-11: 워크플로·job 이름은 한글로(운영자가 Actions 탭에서 이름만 보고 하는 일을 짐작하게)."""

    def names(self, text, rel=".github/workflows/w.yml"):
        write(self.root, rel, text)
        return vr.check_workflow_names(self.root, vr.list_files(self.root))

    def test_korean_workflow_and_job_names_pass(self):
        self.assertEqual(self.names(KOREAN_NAMES_WORKFLOW), [])

    def test_english_workflow_name_is_an_error(self):
        found = self.names("name: Build And Publish\njobs:\n  j:\n    name: 배포\n")
        self.assertEqual([(f.check, f.level, f.path) for f in found], [("WF-11", "ERROR", ".github/workflows/w.yml")])
        self.assertIn("Build And Publish", found[0].message)

    def test_missing_or_non_text_workflow_name_is_an_error(self):
        found = self.names("on: push\njobs:\n  j:\n    name: 배포\n")
        self.assertEqual([(f.check, f.level) for f in found], [("WF-11", "ERROR")])
        self.assertIn("name 이 없습니다", found[0].message)
        found = self.names("name: 2026\njobs:\n  j:\n    name: 배포\n")  # YAML 숫자
        self.assertEqual([(f.check, f.level) for f in found], [("WF-11", "ERROR")])

    def test_job_without_a_korean_name_is_only_a_warning(self):
        found = self.names("name: 배포\njobs:\n  nameless:\n    runs-on: x\n  english:\n    name: Build\n  korean:\n    name: 빌드\n")
        self.assertEqual([(f.check, f.level) for f in found], [("WF-11", "WARN"), ("WF-11", "WARN")])
        self.assertIn("'nameless'", found[0].message)
        self.assertIn("'english'", found[1].message)

    def test_hangul_next_to_expressions_counts(self):
        found = self.names('name: "${{ github.event_name }} 검사"\njobs:\n  j:\n    name: "글 생성 (${{ matrix.key }})"\n')
        self.assertEqual(found, [])

    def test_yaml_syntax_error_is_left_to_wf0(self):
        self.assertEqual(self.names("name: [unclosed\n"), [])

    def test_yaml_extension_is_checked(self):
        found = self.names("name: Deploy\njobs: {}\n", rel=".github/workflows/w.yaml")
        self.assertEqual([(f.check, f.level) for f in found], [("WF-11", "ERROR")])

    def test_yaml_files_outside_the_workflows_folder_are_ignored(self):
        self.assertEqual(self.names("name: English\njobs:\n  j:\n    runs-on: x\n", rel=".github/other/w.yml"), [])

    def test_run_checks_and_cli_report_english_workflow_name_as_error(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        self.assertNotIn("WF-11", checks(vr.run_checks(root)))
        wf = root / ".github" / "workflows" / "chanceblog.yml"
        wf.write_text(wf.read_text(encoding="utf-8").replace('name: "[Chance] 챈스 글 자동 작성"', "name: chance"), encoding="utf-8")
        self.assertIn(("WF-11", "ERROR"), [(f.check, f.level) for f in vr.run_checks(root)])
        out = io.StringIO()
        with redirect_stdout(out):
            code = vr.main(["--root", str(root)])
        self.assertEqual(code, 1)  # 오류가 있으니 종료 코드 1
        self.assertIn("[WF-11]", out.getvalue())

    def test_real_repository_workflow_and_job_names_are_korean(self):
        found = vr.check_workflow_names(REAL, vr.list_files(REAL))
        self.assertEqual([f.line() for f in found], [])

    def test_a_korean_prefix_does_not_count_as_a_korean_name(self):
        """`[공통]`·`[네이버]` 같은 한글 접두사가 한글 이름 검사를 대신 통과시키면 안 된다 — 접두사 뒤의 이름에 한글이 있어야 한다."""
        job = "jobs:\n  j:\n    name: 배포\n"
        found = self.names(f'name: "[공통] Deploy Pages"\n{job}')
        self.assertEqual([(f.check, f.level) for f in found], [("WF-11", "ERROR")])
        self.assertIn("접두사", found[0].message)
        self.assertEqual(self.names(f'name: "[공통] 사이트 자동 배포"\n{job}'), [])
        self.assertEqual(self.names(f'name: "[Chance] 글 자동 작성"\n{job}'), [])
        self.assertEqual([(f.check, f.level) for f in self.names(f'name: "[Chance] Full-Auto Engine"\n{job}')], [("WF-11", "ERROR")])
        self.assertEqual(self.names(f'name: "사이트 [공통] 배포"\n{job}'), [])  # 맨 앞이 아닌 대괄호는 접두사가 아니라 이름의 일부다


AD_SCRIPT = ('<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-1234567890123456"\n'
             '     crossorigin="anonymous"></script>\n')


def registry_root(tmp, chance_cron="17 * * * *", blogger_cron="0 2 * * *", chance_extra="", blogger_matrix=True):
    root = make_root(tmp)
    write(root, "index.html", AD_SCRIPT)   # Chance 의 광고 표면(protected_paths)에 광고 코드가 있다 — 레지스트리의 ads=on 과 맞는다(REG-5)
    write(root, ".github/workflows/chanceblog.yml", f"""
        name: "[Chance] 챈스 글 자동 작성"
        on:
          schedule:
            - cron: '{chance_cron}'
        permissions:
          contents: write
        concurrency:
          group: c
        jobs:
          build:
            name: 글 작성
            runs-on: ubuntu-latest
            timeout-minutes: 5
            steps:
              - env:
                  A: ${{{{ secrets.GEMINI_API_KEY }}}}
                  B: ${{{{ secrets.UNSPLASH_ACCESS_KEY }}}}
                run: git push
{chance_extra}
        """)
    secrets_line = "S: ${{ secrets[matrix.secret_blog_id] }}" if blogger_matrix else "S: nothing"
    write(root, ".github/workflows/blogger.yml", f"""
        name: "[Blogger] 블로거 글 자동 작성"
        on:
          schedule:
            - cron: '{blogger_cron}'
        permissions:
          contents: read
        concurrency:
          group: b
        jobs:
          j:
            name: 글 생성
            runs-on: ubuntu-latest
            timeout-minutes: 5
            steps:
              - env:
                  {secrets_line}
                run: echo ok
        """)
    return root


DEPLOY_STEP = "              - run: gh workflow run pages.yml\n"


class WorkflowPrefixTest(TmpCase):
    """WF-12: 워크플로 name 은 `[구분] `(채널 라벨·공통·내부)으로 시작하고, run-name 이 있으면 같은 접두사로 시작한다."""

    def prefixes(self, text, rel=".github/workflows/w.yml"):
        write(self.root, rel, text)
        return vr.check_workflow_prefixes(self.root, vr.list_files(self.root))

    def test_every_allowed_label_passes(self):
        for label in ("Chance", "Blogger", "Blogger 영문", "Blogger 한글", "티스토리", "네이버", "공통", "내부"):
            self.assertEqual(self.prefixes(f'name: "[{label}] 이름"\n'), [], label)

    def test_a_name_without_the_prefix_is_an_error(self):
        found = self.prefixes("name: 사이트 자동 배포\n")
        self.assertEqual([(f.check, f.level, f.path) for f in found], [("WF-12", "ERROR", ".github/workflows/w.yml")])
        self.assertIn("사이트 자동 배포", found[0].message)
        self.assertIn("[공통]", found[0].message)       # 허용 구분을 알려 준다

    def test_an_unknown_label_is_an_error(self):
        found = self.prefixes('name: "[기타] 이름"\n')
        self.assertEqual([(f.check, f.level) for f in found], [("WF-12", "ERROR")])
        self.assertIn("[기타]", found[0].message)
        self.assertIn("CHANNEL_LABELS", found[0].message)
        for label in ("chance", "CHANCE", "Blogger 영어", "블로거"):      # 대소문자·표기가 다르면 다른 라벨이다
            self.assertEqual(levels(self.prefixes(f'name: "[{label}] 이름"\n'), "WF-12"), ["ERROR"], label)

    def test_malformed_prefixes_are_errors(self):
        for name in ('"[Chance]이름"', '"[Chance] "', '"[Chance]  이름"', '"Chance] 이름"', '"[] 이름"', '" [Chance] 이름"', '"[[Chance]] 이름"', '"[Chance 이름"'):
            self.assertEqual(levels(self.prefixes(f"name: {name}\n"), "WF-12"), ["ERROR"], name)

    def test_run_name_must_use_the_same_prefix(self):
        self.assertEqual(self.prefixes('name: "[Chance] 이름"\nrun-name: "[Chance] 제목 · ${{ github.event_name }}"\n'), [])
        for run_name in ('"제목 · ${{ github.event_name }}"', '"[공통] 제목"', '"[Chance]제목"', '"Chance 제목"', "42"):
            found = self.prefixes(f'name: "[Chance] 이름"\nrun-name: {run_name}\n')
            self.assertEqual([(f.check, f.level) for f in found], [("WF-12", "ERROR")], run_name)
            self.assertIn("run-name", found[0].message)
            self.assertIn("[Chance] ", found[0].message)

    def test_a_workflow_without_run_name_needs_none(self):
        self.assertEqual(self.prefixes('name: "[공통] 사이트 자동 배포"\non: push\n'), [])

    def test_a_bad_name_is_reported_once_and_the_run_name_is_not_judged_against_it(self):
        found = self.prefixes('name: 이름\nrun-name: "[Chance] 제목"\n')
        self.assertEqual(len(found), 1)
        self.assertIn("name", found[0].message)

    def test_missing_or_non_text_names_are_left_to_wf11(self):
        for text in ("on: push\n", "name: 2026\n", "name: ''\n", "name:\n", "jobs: {}\n"):
            self.assertEqual(self.prefixes(text), [], text)

    def test_yaml_syntax_errors_are_left_to_wf0(self):
        """대괄호로 시작하는 값에 따옴표가 없으면 YAML 이 배열로 읽어 문법 오류가 된다 — 그 오류는 WF-0 이 알리고 WF-12 는 조용하다."""
        text = "name: [Chance] 이름\non: push\npermissions:\n  contents: read\njobs: {}\n"
        self.assertEqual(self.prefixes(text), [])
        self.assertEqual(levels(vr.check_workflows(self.root, vr.list_files(self.root)), "WF-0"), ["ERROR"])

    def test_yaml_extension_is_checked_and_other_folders_are_ignored(self):
        self.assertEqual(levels(self.prefixes("name: 이름\n", rel=".github/workflows/w.yaml"), "WF-12"), ["ERROR"])
        (self.root / ".github" / "workflows" / "w.yaml").unlink()
        self.assertEqual(self.prefixes("name: 이름\n", rel=".github/other/w.yml"), [])

    def test_labels_are_the_registry_channel_labels_plus_common_and_internal(self):
        self.assertEqual(vr.WORKFLOW_LABELS, tuple(reg_mod.CHANNEL_LABELS) + ("공통", "내부"))
        self.assertEqual(reg_mod.CHANNEL_LABELS, ("Chance", "Blogger", "Blogger 영문", "Blogger 한글", "티스토리", "네이버"))

    def test_run_checks_and_cli_report_a_missing_prefix_as_error(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        self.assertNotIn("WF-12", checks(vr.run_checks(root)))
        wf = root / ".github" / "workflows" / "chanceblog.yml"
        wf.write_text(wf.read_text(encoding="utf-8").replace('name: "[Chance] 챈스 글 자동 작성"', "name: 챈스 글 자동 작성"), encoding="utf-8")
        self.assertIn(("WF-12", "ERROR"), [(f.check, f.level) for f in vr.run_checks(root)])
        out = io.StringIO()
        with redirect_stdout(out):
            code = vr.main(["--root", str(root)])
        self.assertEqual(code, 1)
        self.assertIn("[WF-12]", out.getvalue())

    def test_real_repository_workflow_names_and_run_names_have_valid_prefixes(self):
        found = vr.check_workflow_prefixes(REAL, vr.list_files(REAL))
        self.assertEqual([f.line() for f in found], [])


class RegistryContractTest(TmpCase):
    def test_consistent_registry_passes(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        self.assertEqual(vr.check_registry(root, vr.list_files(root)), [])

    def test_cron_drift_is_an_error(self):
        root = registry_root(self.root, chance_cron="0 * * * *", chance_extra=DEPLOY_STEP)
        found = vr.check_registry(root, vr.list_files(root))
        self.assertEqual(levels(found, "REG-2"), ["ERROR"])

    def test_a_second_cron_tick_is_fine_when_the_registry_cron_is_one_of_them(self):
        both = "47 * * * *'\n            - cron: '17 * * * *"
        root = registry_root(self.root, chance_cron=both, chance_extra=DEPLOY_STEP)
        self.assertEqual(vr.check_registry(root, vr.list_files(root)), [])

    def test_two_cron_ticks_none_of_which_is_the_registry_cron_is_an_error(self):
        neither = "47 * * * *'\n            - cron: '5 * * * *"
        root = registry_root(self.root, chance_cron=neither, chance_extra=DEPLOY_STEP)
        found = vr.check_registry(root, vr.list_files(root))
        self.assertEqual(levels(found, "REG-2"), ["ERROR"])

    def test_missing_secret_wiring_is_warned(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP, blogger_matrix=False)
        found = vr.check_registry(root, vr.list_files(root))
        self.assertIn("REG-3", checks(found))

    def test_missing_deploy_dispatch_is_warned(self):
        root = registry_root(self.root)
        found = vr.check_registry(root, vr.list_files(root))
        self.assertEqual(levels(found, "WF-10"), ["WARN"])

    def test_invalid_registry_is_reported_as_errors(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        reg_path = root / "pipeline" / "blogs.json"
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["blogs"][0]["mode"] = "yolo"
        reg_path.write_text(json.dumps(reg), encoding="utf-8")
        found = vr.check_registry(root, vr.list_files(root))
        self.assertEqual(levels(found, "REG-1"), ["ERROR"])

    def test_a_blog_without_its_own_mode_is_a_REG_1_error(self):
        """블로그 항목이 mode 를 직접 적지 않으면 defaults.mode(auto)를 물려받아 새 블로그가 바로 자동 게시된다."""
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        reg_path = root / "pipeline" / "blogs.json"
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["defaults"]["mode"] = "auto"
        del reg["blogs"][1]["mode"]
        reg_path.write_text(json.dumps(reg), encoding="utf-8")
        found = vr.check_registry(root, vr.list_files(root))
        self.assertEqual(levels(found, "REG-1"), ["ERROR"])
        self.assertTrue(any("mode" in f.line() and "직접" in f.line() for f in found if f.check == "REG-1"))

    def test_model_drift_is_warned(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        write(root, "generator.py", 'MODEL_CANDIDATES = [\n    "gemini-old-1",\n]\n')
        found = vr.check_registry(root, vr.list_files(root))
        self.assertEqual(levels(found, "REG-4"), ["WARN"])

    def test_a_workflow_name_that_does_not_match_the_channel_label_is_a_REG_1_error(self):
        """블로그의 channel.label 과 그 워크플로 name 의 `[라벨] ` 이 다르면 레지스트리 검증(REG-1)이 알린다."""
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        wf = root / ".github" / "workflows" / "blogger.yml"
        wf.write_text(wf.read_text(encoding="utf-8").replace('"[Blogger] ', '"[Chance] '), encoding="utf-8")
        found = vr.check_registry(root, vr.list_files(root))
        self.assertEqual(levels(found, "REG-1"), ["ERROR"])
        message = next(f.message for f in found if f.check == "REG-1")
        self.assertIn("blogger_macat", message)
        self.assertIn("[Blogger] ", message)


class AdsDriftTest(TmpCase):
    """REG-5: 레지스트리의 ads 선언이 광고 표면(protected_paths)의 실제 광고 코드와 맞는지(jekyll-git 블로그만)."""

    PLAIN = "<html><body>광고 없음</body></html>\n"

    runs = 0

    def run_reg5(self, ads="on", index=AD_SCRIPT, extra_files=None):
        self.runs += 1                              # 한 시험 안에서 여러 번 부르므로 호출마다 새 임시 저장소를 만든다(make_root 는 폴더가 있으면 실패한다)
        root = registry_root(self.root / f"run{self.runs}", chance_extra=DEPLOY_STEP)
        reg_path = root / "pipeline" / "blogs.json"
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["blogs"][0]["ads"] = ads
        reg_path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        write(root, "index.html", index)
        for rel, text in (extra_files or {}).items():
            write(root, rel, text)
        return [f for f in vr.check_registry(root, vr.list_files(root)) if f.check == "REG-5"]

    def test_on_with_ad_code_and_off_without_it_are_consistent(self):
        self.assertEqual(self.run_reg5("on", AD_SCRIPT), [])
        for ads in ("off", "pending_gate"):
            self.assertEqual(self.run_reg5(ads, self.PLAIN), [], ads)

    def test_on_without_any_ad_code_is_an_error(self):
        found = self.run_reg5("on", self.PLAIN)
        self.assertEqual([(f.check, f.level, f.path) for f in found], [("REG-5", "ERROR", "pipeline/blogs.json")])
        self.assertIn("chance", found[0].message)
        self.assertIn("ads=on", found[0].message)
        self.assertIn("Ad-Surface-Approved", found[0].message)

    def test_off_or_pending_gate_with_ad_code_is_an_error(self):
        for ads in ("off", "pending_gate"):
            found = self.run_reg5(ads, AD_SCRIPT)
            self.assertEqual([(f.check, f.level) for f in found], [("REG-5", "ERROR")], ads)
            self.assertIn(f"ads={ads}", found[0].message)
            self.assertIn("index.html", found[0].message)          # 어느 파일에 있는지 알려 준다
            self.assertIn("Ad-Surface-Approved", found[0].message)

    def test_ad_code_in_a_protected_directory_counts(self):
        """protected_paths 의 `_layouts/` 처럼 '/' 로 끝나는 항목은 폴더 전체다."""
        layout = {"_layouts/default.html": AD_SCRIPT}
        self.assertEqual(self.run_reg5("on", self.PLAIN, layout), [])
        found = self.run_reg5("off", self.PLAIN, layout)
        self.assertEqual([f.check for f in found], ["REG-5"])
        self.assertIn("_layouts/default.html", found[0].message)

    def test_ad_code_outside_the_ad_surface_does_not_count(self):
        elsewhere = {"_posts/p.md": AD_SCRIPT, "docs/x.md": "adsbygoogle 설명\n", "notes.html": AD_SCRIPT}
        self.assertEqual(self.run_reg5("off", self.PLAIN, elsewhere), [])
        self.assertEqual(len(self.run_reg5("on", self.PLAIN, elsewhere)), 1)

    def test_each_ad_code_signature_counts_case_insensitively(self):
        for token in ("adsbygoogle", "googlesyndication", "ca-pub-1234567890123456", "AdsByGoogle", "GOOGLESYNDICATION", "CA-PUB-99"):
            page = f"<script>{token}</script>\n"
            self.assertEqual(self.run_reg5("on", page), [], token)
            self.assertEqual(len(self.run_reg5("off", page)), 1, token)
        for text in ("ca-pub-", "ca-pub-x", "google ads", "ad sense"):   # ca-pub- 뒤에는 숫자가 와야 하고 낱말만으로는 광고 코드가 아니다
            self.assertEqual(len(self.run_reg5("on", f"<p>{text}</p>\n")), 1, text)

    def test_non_jekyll_blogs_are_not_checked_here_and_on_is_a_registry_error(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        reg_path = root / "pipeline" / "blogs.json"
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["blogs"][1]["ads"] = "on"                     # blogger 블로그는 on 을 둘 수 없다 — REG-1 이 알리고 REG-5 는 대상이 아니다
        reg_path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        found = vr.check_registry(root, vr.list_files(root))
        self.assertEqual(levels(found, "REG-1"), ["ERROR"])
        self.assertEqual(levels(found, "REG-5"), [])

    def test_the_drift_check_looks_only_at_jekyll_git_blogs(self):
        """다른 플랫폼 블로그는 광고를 플랫폼 화면에서 켜므로 저장소에서 확인할 수 없다 — 선언이 무엇이든 REG-5 는 아무것도 말하지 않는다."""
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        files = vr.list_files(root)
        for ads in ("off", "pending_gate", "on"):
            blog = {"key": "x", "platform": "blogger", "ads": ads, "protected_paths": ["index.html"]}      # index.html 에는 광고 코드가 있다
            self.assertEqual(vr._ads_drift(root, files, blog), [], ads)
        chance = {"key": "x", "platform": "jekyll-git", "ads": "off", "protected_paths": ["index.html"]}
        self.assertEqual(len(vr._ads_drift(root, files, chance)), 1)                                       # 같은 입력이 jekyll-git 이면 걸린다
        self.assertEqual(vr._ads_drift(root, files, {"key": "x", "platform": "jekyll-git", "ads": "off", "protected_paths": None}), [])

    def test_patterns_are_the_same_as_the_edit_systems_ad_snippet_check(self):
        from pipeline.edits import checks as edit_checks
        self.assertEqual([p.pattern for p in vr._AD_CODE_PATTERNS], [p.pattern for p in edit_checks.AD_PATTERNS])
        self.assertEqual([p.flags for p in vr._AD_CODE_PATTERNS], [p.flags for p in edit_checks.AD_PATTERNS])

    def test_run_checks_and_cli_report_drift_as_error(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        write(root, "index.html", self.PLAIN)
        self.assertIn(("REG-5", "ERROR"), [(f.check, f.level) for f in vr.run_checks(root)])
        out = io.StringIO()
        with redirect_stdout(out):
            code = vr.main(["--root", str(root)])
        self.assertEqual(code, 1)
        self.assertIn("[REG-5]", out.getvalue())

    def test_real_repository_ads_declaration_matches_the_site(self):
        found = [f.line() for f in vr.check_registry(REAL, vr.list_files(REAL)) if f.check == "REG-5"]
        self.assertEqual(found, [])
        reg = reg_mod.load_registry()
        self.assertEqual(reg_mod.get_blog(reg, "chance")["ads"], "on")                 # 지금 사실: 홈에 광고 스크립트가 있다


class IssueContractTest(TmpCase):
    CONTROL = 'name: t\ntitle: "[이미지 변경] "\nlabels: ["blog-control"]\nbody: []\n'

    def test_prefix_mismatch_is_flagged_and_match_is_not(self):
        write(self.root, ".github/ISSUE_TEMPLATE/t.yml", self.CONTROL)
        write(self.root, ".github/workflows/w.yml",
              "name: w\non: issues\njobs:\n  j:\n    if: startsWith(github.event.issue.title, '[Control]')\n")
        found = vr.check_issue_contract(self.root, vr.list_files(self.root))
        self.assertEqual(levels(found, "CONTRACT-1"), ["WARN"])
        write(self.root, ".github/workflows/w.yml",
              "name: w\non: issues\njobs:\n  j:\n    if: startsWith(github.event.issue.title, '[이미지 변경]')\n")
        self.assertEqual(vr.check_issue_contract(self.root, vr.list_files(self.root)), [])

    def test_any_of_several_prefixes_is_enough_and_non_control_templates_are_ignored(self):
        write(self.root, ".github/ISSUE_TEMPLATE/t.yml", self.CONTROL)
        write(self.root, ".github/ISSUE_TEMPLATE/bug.yml", 'name: bug\ntitle: "[버그] "\nlabels: ["bug"]\nbody: []\n')
        write(self.root, ".github/workflows/w.yml",
              "name: w\non: issues\njobs:\n  j:\n    if: >-\n      startsWith(github.event.issue.title, '[페이지 수정]') ||\n"
              "      startsWith(github.event.issue.title, '[이미지 변경]')\n")
        self.assertEqual(vr.check_issue_contract(self.root, vr.list_files(self.root)), [])

    def test_real_repository_contract_holds(self):
        self.assertEqual(vr.check_issue_contract(REAL, vr.list_files(REAL)), [])


class EditSystemTest(TmpCase):
    def setUp(self):
        super().setUp()
        self.repo = make_edit_root(self.root)

    def run_check(self):
        return vr.check_edit_system(self.repo, vr.list_files(self.repo))

    def test_consistent_system_is_clean(self):
        self.assertEqual(self.run_check(), [])

    def test_spec_granting_forbidden_paths_is_an_error(self):
        spec = self.repo / ".github" / "editorial" / "edit-spec.yml"
        text = spec.read_text(encoding="utf-8").replace('allowed_paths: ["{page.path}"]\n    forbidden: ["front matter", "광고 코드", "링크 주소"]',
                                                      'allowed_paths: ["{page.path}", "_layouts/**"]\n    forbidden: ["front matter"]', 1)
        self.assertNotEqual(text, spec.read_text(encoding="utf-8"))
        spec.write_text(text, encoding="utf-8")
        self.assertIn("SPEC-1", checks(self.run_check()))

    def test_new_editable_page_makes_registry_stale_warning_only(self):
        write(self.repo, "faq.md", "---\ntitle: 자주 묻는 질문\neditable: true\n---\n")
        found = self.run_check()
        self.assertEqual(levels(found, "SYNC-1"), ["WARN"])
        self.assertEqual([f for f in found if f.level == "ERROR"], [])

    def test_stale_form_dropdown_is_a_warning(self):
        tpl = self.repo / ".github" / "ISSUE_TEMPLATE" / "page-edit.yml"
        tpl.write_text(tpl.read_text(encoding="utf-8").replace("about | 소개와 편집 원칙", "about | 옛 제목"), encoding="utf-8")
        found = self.run_check()
        self.assertEqual(levels(found, "SYNC-1"), ["WARN"])
        self.assertIn("드롭다운", found[0].message)

    def test_missing_control_template_for_a_spec_label_is_an_error(self):
        tpl = self.repo / ".github" / "ISSUE_TEMPLATE" / "blog_control.yml"
        tpl.write_text(tpl.read_text(encoding="utf-8").replace('"edit:image"', '"other"'), encoding="utf-8")
        found = self.run_check()
        self.assertIn("SPEC-2", checks(found))
        self.assertTrue(any(f.level == "ERROR" for f in found if f.check == "SPEC-2"))

    def test_repository_without_spec_is_skipped(self):
        (self.repo / ".github" / "editorial" / "edit-spec.yml").unlink()
        self.assertEqual(self.run_check(), [])

    def test_real_repository_edit_system_is_consistent(self):
        found = vr.check_edit_system(REAL, vr.list_files(REAL))
        self.assertEqual([f.line() for f in found], [])


class DataAndDocsTest(TmpCase):
    def test_python_and_json_errors(self):
        write(self.root, "bad.py", "def x(:\n")
        write(self.root, "ok.py", "x = 1\n")
        write(self.root, "bad.json", "{oops")
        write(self.root, "template.json", "---\n---\n[{% for p in site.posts %}{}{% endfor %}]\n")  # Jekyll 템플릿은 건너뜀
        files = vr.list_files(self.root)
        self.assertEqual([f.path for f in vr.check_python(self.root, files)], ["bad.py"])
        self.assertEqual([f.path for f in vr.check_json(self.root, files)], ["bad.json"])

    def test_broken_doc_links_strict_in_docs_and_warn_elsewhere(self):
        write(self.root, "docs/a.md", "[ok](b.md) [bad](missing.md) [web](https://x.example) [anchor](#top)\n")
        write(self.root, "docs/b.md", "x\n")
        write(self.root, "NOTES.md", "[bad](missing.md)\n")
        found = vr.check_doc_links(self.root, vr.list_files(self.root))
        by_path = {f.path.split(":")[0]: f.level for f in found}
        self.assertEqual(by_path, {"docs/a.md": "ERROR", "NOTES.md": "WARN"})

    def test_agent_files(self):
        found = vr.check_agent_files(self.root, vr.list_files(self.root))
        self.assertEqual(len(found), 4)
        for rel in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md"):
            write(self.root, rel, "HANDLER.md docs/SECURITY_GUARDRAILS.md")
        self.assertEqual(vr.check_agent_files(self.root, vr.list_files(self.root)), [])

    def test_dependencies(self):
        write(self.root, ".github/workflows/w.yml",
              "name: w\njobs:\n  j:\n    steps:\n      - run: |\n          pip install --upgrade pip\n"
              "          pip install requests 'good>=1,<2' -r other.txt\n")
        write(self.root, "requirements-x.txt", "pinned==1.0\nloose\n# comment\n")
        found = vr.check_dependencies(self.root, vr.list_files(self.root))
        messages = " ".join(f.message for f in found)
        self.assertIn("requests", messages)
        self.assertIn("loose", messages)
        self.assertNotIn("good", messages)
        self.assertNotIn("pinned", messages)

    def test_exposure_warning(self):
        write(self.root, "_config.yml", "title: x\n")
        write(self.root, "HANDLER.md", "x")
        self.assertEqual(checks(vr.check_exposure(self.root, vr.list_files(self.root))), ["EXPOSE-1"])
        write(self.root, "_config.yml", "title: x\nexclude: [HANDLER.md]\n")
        self.assertEqual(vr.check_exposure(self.root, vr.list_files(self.root)), [])


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=root,
                   check=True, capture_output=True)


class AdSurfaceTest(TmpCase):
    def make_repo(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        write(root, "index.html", "<html>v1</html>")
        write(root, "notes.md", "n1")
        git(root, "init", "-q")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "base")
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
        return root, base

    def test_unapproved_change_to_protected_file_is_an_error(self):
        root, base = self.make_repo()
        write(root, "index.html", "<html>v2</html>")
        git(root, "commit", "-q", "-am", "tweak landing")
        self.assertEqual(levels(vr.check_ad_surface(root, base), "AD-1"), ["ERROR"])

    def test_approved_change_passes(self):
        root, base = self.make_repo()
        write(root, "index.html", "<html>v2</html>")
        git(root, "commit", "-q", "-am", "tweak landing\n\nAd-Surface-Approved: user approved in chat")
        self.assertEqual(vr.check_ad_surface(root, base), [])

    def test_unprotected_change_passes_and_missing_base_is_skipped(self):
        root, base = self.make_repo()
        write(root, "notes.md", "n2")
        git(root, "commit", "-q", "-am", "notes")
        self.assertEqual(vr.check_ad_surface(root, base), [])
        self.assertEqual(vr.check_ad_surface(root, ""), [])
        self.assertEqual(vr.check_ad_surface(root, "0" * 40), [])
        self.assertEqual(levels(vr.check_ad_surface(root, "deadbeef" * 5), "AD-0"), ["WARN"])

    def test_directory_prefix_protection(self):
        root, base = self.make_repo()
        write(root, "_layouts/post.html", "<html>x</html>")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "layout")
        self.assertEqual(levels(vr.check_ad_surface(root, base), "AD-1"), ["ERROR"])


class LiquidInDocsTest(TmpCase):
    def test_liquid_tags_in_plain_markdown_break_the_pages_build(self):
        write(self.root, "docs/a.md", "설명 {" + "% include_relative x.html %" + "} 끝\n")
        write(self.root, "docs/b.md", "표현식 ${" + "{ github.event.issue.body }" + "}\n")
        write(self.root, "docs/ok.md", "Liquid 는 중괄호-퍼센트 구문이다.\n")
        write(self.root, "page.md", "---\ntitle: t\n---\n{" + "% for x in y %" + "}z{" + "% endfor %" + "}\n")  # front matter 가 있는 페이지는 정상
        write(self.root, ".github/instructions/i.md", "{" + "% x %" + "}\n")                                   # 숨김 폴더는 게시되지 않는다
        found = vr.check_liquid_in_docs(self.root, vr.list_files(self.root))
        self.assertEqual(sorted((f.path, f.level) for f in found), [("docs/a.md", "ERROR"), ("docs/b.md", "WARN")])

    def test_real_repository_docs_have_no_liquid_tags(self):
        found = [f.line() for f in vr.check_liquid_in_docs(REAL, vr.list_files(REAL)) if f.level == "ERROR"]
        self.assertEqual(found, [])


class BriefingTest(TmpCase):
    FULL = "`chance` `blogger_macat` `alpha.yml` `beta.yaml` `text_change` `link_change`\n"

    def build(self, briefing):
        (self.root / "pipeline").mkdir()
        shutil.copy(REAL / "pipeline" / "blogs.json", self.root / "pipeline" / "blogs.json")
        write(self.root, ".github/workflows/alpha.yml", "name: a\n")
        write(self.root, ".github/workflows/beta.yaml", "name: b\n")
        write(self.root, ".github/editorial/edit-spec.yml", "version: 1\nedit_types:\n  text_change: {}\n  link_change: {}\n")
        if briefing is not None:
            write(self.root, "docs/REQUEST_BRIEFING.md", briefing)
        return vr.check_briefing(self.root, vr.list_files(self.root))

    def test_complete_briefing_is_clean(self):
        self.assertEqual(self.build(self.FULL), [])

    def test_missing_items_are_reported_by_name(self):
        found = self.build("`chance` `alpha.yml` `text_change`\n")
        self.assertEqual([(f.check, f.level) for f in found], [("BRIEF-1", "WARN")])
        for missing in ("블로그 blogger_macat", "워크플로 beta.yaml", "수정 항목 link_change"):
            self.assertIn(missing, found[0].message)
        for present in ("블로그 chance,", "alpha.yml", "text_change"):
            self.assertNotIn(present, found[0].message)

    def test_mention_without_backticks_does_not_count(self):
        found = self.build("chance blogger_macat alpha.yml beta.yaml text_change link_change\n")
        self.assertEqual([f.check for f in found], ["BRIEF-1"])

    def test_missing_briefing_file_warns(self):
        found = self.build(None)
        self.assertEqual([(f.check, f.level) for f in found], [("BRIEF-1", "WARN")])

    def test_real_briefing_covers_current_repository(self):
        self.assertEqual(vr.check_briefing(REAL, vr.list_files(REAL)), [])


class CliTest(TmpCase):
    def test_exit_codes(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        write(root, "bad.py", "def x(:\n")
        self.assertEqual(vr.main(["--root", str(root)]), 1)
        (root / "bad.py").unlink()
        write(root, "ok.py", "x = 1\n")
        self.assertEqual(vr.main(["--root", str(root)]), 0)           # 경고만 있으면 통과
        self.assertEqual(vr.main(["--root", str(root), "--strict"]), 1)  # strict 는 경고도 실패


if __name__ == "__main__":
    unittest.main()
