import io
import json
import re
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


def assert_one_plain_line(test, finding, folded):
    """finding 의 메시지·출력 줄이 한 줄이고 워크플로 명령(`::`)·로그 서식(`##[`) 표기가 없으며, 저장소 파일에서 온 값이 접힌 모양(folded)으로 들어 있다."""
    test.assertIn(folded, finding.message)
    for text in (finding.message, finding.line()):
        test.assertEqual(len(text.splitlines()), 1, text)
        test.assertNotIn("::", text)
        test.assertNotIn("##[", text)


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

    def test_a_name_with_line_breaks_and_command_marks_is_folded_to_one_line_in_the_message(self):
        """워크플로 name 은 저장소 파일의 값이다 — 줄바꿈·`::`·`##[` 가 들어 있어도 오류 줄이 여러 줄이 되거나 워크플로 명령으로 읽히지 않는다(G-L2)."""
        found = self.names('name: "Build\\n::error::forged ##[group]g"\njobs:\n  j:\n    name: 배포\n')      # 한글이 없는 값만 WF-11 오류가 된다
        self.assertEqual([(f.check, f.level) for f in found], [("WF-11", "ERROR")])
        assert_one_plain_line(self, found[0], "Build : :error: :forged # [group]g")

    def test_a_long_name_is_still_cut_at_forty_characters_in_the_message(self):
        found = self.names(f'name: "{"B" * 45}"\njobs:\n  j:\n    name: 배포\n')
        self.assertIn("B" * 40, found[0].message)
        self.assertNotIn("B" * 41, found[0].message)


AD_SCRIPT = ('<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-1234567890123456"\n'
             '     crossorigin="anonymous"></script>\n')


def registry_root(tmp, chance_cron="17 * * * *", blogger_cron="0 2 * * *", chance_extra="", blogger_matrix=True, korean_cron="30 3 * * *"):
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
    write(root, ".github/workflows/blogger.yml", BLOGGER_REUSABLE_TEXT)
    names = {"macat": reg_mod.get_blog(reg_mod.load_registry(root / "pipeline" / "blogs.json"), "blogger_macat")["secrets"],
             "kcyoon": reg_mod.get_blog(reg_mod.load_registry(root / "pipeline" / "blogs.json"), "blogger_kcyoon")["secrets"]}
    write(root, ".github/workflows/blogger-en.yml", blogger_wrapper("Blogger 영문", blogger_cron, "blogger_macat", "blogger-en", names["macat"], wired=blogger_matrix))
    write(root, ".github/workflows/blogger-ko.yml", blogger_wrapper("Blogger 한글", korean_cron, "blogger_kcyoon", "blogger-ko", names["kcyoon"], wired=blogger_matrix))
    return root


BLOGGER_REUSABLE_TEXT = """
    name: "[내부] Blogger 글 작성 공용(직접 실행하지 마세요)"
    on:
      workflow_call:
        inputs:
          blog: {type: string, required: true}
          topic: {type: string, required: false, default: ''}
          dry_run: {type: boolean, required: false, default: true}
          publish: {type: string, required: false, default: ''}
          auth_check: {type: boolean, required: false, default: false}
        secrets:
          PIPELINE_SECRET_LLM_API_KEY: {required: false}
          PIPELINE_SECRET_BLOG_ID: {required: false}
          PIPELINE_SECRET_CLIENT_ID: {required: false}
          PIPELINE_SECRET_CLIENT_SECRET: {required: false}
          PIPELINE_SECRET_REFRESH_TOKEN: {required: false}
          PIPELINE_SECRET_UNSPLASH_KEY: {required: false}
          TELEGRAM_BOT_TOKEN: {required: false}
          TELEGRAM_CHAT_ID: {required: false}
    permissions:
      contents: read
    jobs:
      plan:
        name: 대상 블로그 계획
        runs-on: ubuntu-latest
        timeout-minutes: 5
        steps:
          - run: echo ok
    """


def blogger_wrapper(label, cron, key, group, names, wired=True):
    """Blogger 채널 래퍼(blogger-en.yml·blogger-ko.yml 모양) 텍스트. names: 레지스트리 secrets({역할: 환경변수 이름}). wired=False 면 secrets 매핑을 뺀다."""
    secrets = "\n".join(f"              PIPELINE_SECRET_{role.upper()}: ${{{{ secrets.{name} }}}}" for role, name in names.items())
    return f"""
        name: "[{label}] 글 자동 작성"
        on:
          schedule:
            - cron: '{cron}'
          workflow_dispatch:
        permissions:
          contents: read
        concurrency:
          group: {group}
        jobs:
          blogger:
            name: 글 작성
            permissions:
              contents: write
            uses: ./.github/workflows/blogger.yml
            with:
              blog: {key}
              topic: ${{{{ github.event.inputs.topic || '' }}}}
              dry_run: ${{{{ github.event.inputs.dry_run == 'true' }}}}
              publish: ${{{{ github.event_name == 'workflow_dispatch' && github.event.inputs.publish || '' }}}}
              auth_check: ${{{{ github.event_name == 'workflow_dispatch' && github.event.inputs.auth_check == 'true' }}}}
""" + (f"""            secrets:
{secrets}
""" if wired else "")


DEPLOY_STEP = "              - run: gh workflow run pages.yml\n"


class WorkflowPrefixTest(TmpCase):
    """WF-12: 워크플로 name 은 `[구분] `(채널 라벨·공통·내부)으로 시작하고, run-name 이 있으면 같은 접두사로 시작한다."""

    def prefixes(self, text, rel=".github/workflows/w.yml"):
        write(self.root, rel, text)
        return vr.check_workflow_prefixes(self.root, vr.list_files(self.root))

    def test_every_allowed_label_passes(self):
        for label in ("Chance", "Blogger 영문", "Blogger 한글", "티스토리", "네이버", "공통", "내부"):
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
        for label in ("chance", "CHANCE", "Blogger 영어", "블로거", "Blogger"):      # 대소문자·표기가 다르면 다른 라벨이다(영문·한글로 나누기 전의 임시 라벨 `Blogger` 도 더 이상 허용 목록에 없다)
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
        self.assertEqual(reg_mod.CHANNEL_LABELS, ("Chance", "Blogger 영문", "Blogger 한글", "티스토리", "네이버"))

    def test_the_name_in_the_missing_prefix_message_is_folded_to_one_line(self):
        """name·run-name·구분(라벨)은 저장소 파일의 값이다 — 줄바꿈·`::`·`##[` 가 든 값이 오류 줄을 여러 줄로 쪼개거나 워크플로 명령(`::error::`)으로 읽히게 하지 않는다(G-L2)."""
        found = self.prefixes('name: "사이트\\n::error::위조 ##[group]g"\n')
        self.assertEqual([(f.check, f.level) for f in found], [("WF-12", "ERROR")])
        assert_one_plain_line(self, found[0], "사이트 : :error: :위조 # [group]g")

    def test_the_label_in_the_unknown_label_message_is_folded_to_one_line(self):
        found = self.prefixes('name: "[기\\n::error::타] 이름"\n')
        self.assertEqual([(f.check, f.level) for f in found], [("WF-12", "ERROR")])
        self.assertIn("허용 목록에 없습니다", found[0].message)
        assert_one_plain_line(self, found[0], "[기 : :error: :타]")

    def test_the_run_name_in_the_other_prefix_message_is_folded_to_one_line(self):
        found = self.prefixes('name: "[Chance] 이름"\nrun-name: "[공통] 제목\\n::error::위조 ##[group]g"\n')
        self.assertEqual([(f.check, f.level) for f in found], [("WF-12", "ERROR")])
        self.assertIn("run-name", found[0].message)
        assert_one_plain_line(self, found[0], "[공통] 제목 : :error: :위조 # [group]g")

    def test_a_long_name_and_run_name_are_still_cut_at_forty_characters_in_the_messages(self):
        found = self.prefixes(f'name: "{"가" * 45}"\n')
        self.assertIn("가" * 40, found[0].message)
        self.assertNotIn("가" * 41, found[0].message)
        found = self.prefixes(f'name: "[Chance] 이름"\nrun-name: "{"나" * 45}"\n')
        self.assertIn("나" * 40, found[0].message)
        self.assertNotIn("나" * 41, found[0].message)

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
        wf = root / ".github" / "workflows" / "blogger-en.yml"
        wf.write_text(wf.read_text(encoding="utf-8").replace('"[Blogger 영문] ', '"[Chance] '), encoding="utf-8")
        found = vr.check_registry(root, vr.list_files(root))
        self.assertEqual(levels(found, "REG-1"), ["ERROR"])
        message = next(f.message for f in found if f.check == "REG-1")
        self.assertIn("blogger_macat", message)
        self.assertIn("[Blogger 영문] ", message)


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
    FULL = "`chance` `blogger_macat` `blogger_kcyoon` `alpha.yml` `beta.yaml` `text_change` `link_change`\n"

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


TG_TOKEN = "${{ secrets.TELEGRAM_BOT_TOKEN }}"
TG_CHAT = "${{ secrets.TELEGRAM_CHAT_ID }}"
TG_GOOD_ENV = f"TELEGRAM_BOT_TOKEN: {TG_TOKEN}\nTELEGRAM_CHAT_ID: {TG_CHAT}"


def tg_step(run="python -m pipeline.notify test", env="", extra=()):
    """steps 항목 하나(YAML 줄들, 들여쓰기 없음). run 은 블록 문자열이라 특수 문자를 따옴표로 감쌀 필요가 없다."""
    lines = ["- name: 단계", *[f"  {line}" for line in extra]]
    if env:
        lines += ["  env:", *[f"    {line}" for line in env.splitlines()]]
    lines += ["  run: |", f"    {run}"]
    return "\n".join(lines)


def tg_yaml(*steps, job_env="", top_env="", step_text=None, job_extra=()):
    """텔레그램 시크릿 규칙·알림 단계 예외 시험용 워크플로 YAML(들여쓰기 없이 만든다). step_text 가 있으면 steps 항목을 그대로 쓴다.
    job_extra: 잡(j)의 키 아래에 그대로 넣을 줄들(예: container·services — 들여쓰기는 잡 기준)."""
    body = step_text if step_text is not None else "\n".join(steps)
    lines = ['name: "[공통] 시험"', "on:", "  workflow_dispatch:", "permissions:", "  contents: read"]
    if top_env:
        lines += ["env:", f"  {top_env}"]
    lines += ["jobs:", "  j:", "    name: 시험", "    runs-on: ubuntu-latest", "    timeout-minutes: 5"]
    lines += [f"    {line}" for line in job_extra]
    if job_env:
        lines += ["    env:", f"      {job_env}"]
    lines += ["    steps:", *["      " + line for line in body.splitlines()]]
    return "\n".join(lines) + "\n"


class TelegramSecretRuleTest(TmpCase):
    """WF-13: 텔레그램 시크릿 이름(TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID)은 단계 env 의 같은 이름 환경변수에 `secrets.그 이름` 표현식 그대로일 때만 허용된다."""

    def check(self, *steps, rel=".github/workflows/w.yml", **kwargs):
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(tg_yaml(*steps, **kwargs), encoding="utf-8")
        return vr.check_telegram_secrets(self.root, vr.list_files(self.root))

    @staticmethod
    def marks(found):
        return [(f.check, f.level) for f in found]

    @staticmethod
    def place(finding):
        return re.search(r"자리\((.*?)\)에", finding.message).group(1)

    def test_the_allowed_shape_is_clean(self):
        self.assertEqual(self.check(tg_step(env=TG_GOOD_ENV)), [])

    def test_whitespace_inside_the_expression_is_fine(self):
        env = "TELEGRAM_BOT_TOKEN: ${{secrets.TELEGRAM_BOT_TOKEN}}\nTELEGRAM_CHAT_ID: ${{   secrets.TELEGRAM_CHAT_ID   }}"
        self.assertEqual(self.check(tg_step(env=env)), [])

    def test_only_one_of_the_two_is_fine_too(self):
        self.assertEqual(self.check(tg_step(env=f"TELEGRAM_CHAT_ID: {TG_CHAT}")), [])

    def test_the_yaml_extension_is_checked_too(self):
        found = self.check(tg_step(run="echo $TELEGRAM_BOT_TOKEN"), rel=".github/workflows/w.yaml")
        self.assertEqual(self.marks(found), [("WF-13", "ERROR")])

    def test_workflows_without_the_names_are_untouched(self):
        self.assertEqual(self.check(tg_step(run="python generator.py", env="A: ${{ secrets.GEMINI_API_KEY }}")), [])

    def test_the_names_in_a_run_body_are_errors_in_every_spelling(self):
        for run in ('echo "$TELEGRAM_BOT_TOKEN"', "echo ${TELEGRAM_BOT_TOKEN}", 'curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"',
                    f'echo "t={TG_TOKEN}" >> "$GITHUB_ENV"', f"python x.py {TG_CHAT}", "echo ::set-output name=t::$TELEGRAM_CHAT_ID", "env | grep TELEGRAM_CHAT_ID",
                    "python -m pipeline.notify test  # TELEGRAM_BOT_TOKEN"):
            with self.subTest(run=run[:40]):
                found = self.check(tg_step(run=run, env=TG_GOOD_ENV))
                self.assertEqual(self.marks(found), [("WF-13", "ERROR")])
                self.assertEqual(self.place(found[0]), "jobs.j.steps.0.run")

    def test_a_step_input_for_an_action_is_an_error(self):
        step = f"- uses: someone/ok-action@0123456789abcdef0123456789abcdef01234567\n  with:\n    token: {TG_TOKEN}"
        found = self.check(step_text=step)
        self.assertEqual(self.marks(found), [("WF-13", "ERROR")])
        self.assertEqual(self.place(found[0]), "jobs.j.steps.0.with.token")

    def test_job_level_and_workflow_level_env_are_errors(self):
        found = self.check(tg_step(env=TG_GOOD_ENV), job_env=f"TELEGRAM_BOT_TOKEN: {TG_TOKEN}")
        self.assertEqual((self.marks(found), self.place(found[0])), ([("WF-13", "ERROR")], "jobs.j.env.TELEGRAM_BOT_TOKEN"))
        found = self.check(tg_step(env=TG_GOOD_ENV), top_env=f"TELEGRAM_CHAT_ID: {TG_CHAT}")
        self.assertEqual((self.marks(found), self.place(found[0])), ([("WF-13", "ERROR")], "env.TELEGRAM_CHAT_ID"))

    def test_conditions_ids_and_names_are_errors(self):
        name_step = "- name: TELEGRAM_BOT_TOKEN 단계\n  run: |\n    python -m pipeline.notify test"
        cases =((tg_step(env=TG_GOOD_ENV, extra=["if: secrets.TELEGRAM_BOT_TOKEN != ''"]), "if"),
                 (tg_step(env=TG_GOOD_ENV, extra=["id: TELEGRAM_CHAT_ID"]), "id"), (name_step, "name"))
        for step, where in cases:
            with self.subTest(where=where):
                found = self.check(step_text=step)
                self.assertEqual(self.marks(found), [("WF-13", "ERROR")])
                self.assertEqual(self.place(found[0]), f"jobs.j.steps.0.{where}")

    def test_an_env_name_that_does_not_match_the_secret_is_an_error(self):
        for env in (f"FOO: {TG_TOKEN}", f"TELEGRAM_BOT_TOKEN: {TG_CHAT}", f"TELEGRAM_CHAT_ID: {TG_TOKEN}", f"TOKEN: {TG_CHAT}"):
            with self.subTest(env=env):
                self.assertEqual(self.marks(self.check(tg_step(env=env))), [("WF-13", "ERROR")])

    def test_decorated_values_are_errors(self):
        values = (f'"{TG_TOKEN}-x"', f'"x{TG_TOKEN}"', f'"{TG_TOKEN} {TG_CHAT}"', f"'{TG_TOKEN}{TG_TOKEN}'",
                  "\"${{ secrets.TELEGRAM_BOT_TOKEN || 'x' }}\"", "\"${{ format('{0}', secrets.TELEGRAM_BOT_TOKEN) }}\"", "plain TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN")
        for value in values:
            with self.subTest(value=value[:40]):
                self.assertEqual(self.marks(self.check(tg_step(env=f"TELEGRAM_BOT_TOKEN: {value}"))), [("WF-13", "ERROR")])

    def test_other_letter_cases_of_the_names_are_errors_too(self):
        """독립 검증 N-3: GitHub 시크릿 이름은 대소문자를 가리지 않는다 — `secrets.telegram_bot_token` 은 같은 시크릿이라 같은 규칙을 받는다."""
        for run in ('echo "${{ secrets.telegram_bot_token }}"', "echo ${{ secrets.Telegram_Bot_Token }}", "echo ${{ secrets.telegram_chat_id }}",
                    'curl "https://api.telegram.org/bot${{ secrets.Telegram_Bot_Token }}/getMe"', "echo $Telegram_Chat_Id"):
            with self.subTest(run=run[:40]):
                found = self.check(tg_step(run=run, env=TG_GOOD_ENV))
                self.assertEqual(self.marks(found), [("WF-13", "ERROR")])
                self.assertEqual(self.place(found[0]), "jobs.j.steps.0.run")
                self.assertRegex(found[0].message, r"\(TELEGRAM_(BOT_TOKEN|CHAT_ID)\)")          # 메시지는 등록된 이름(대문자)으로 알린다

    def test_other_letter_cases_in_the_allowed_place_are_errors_too(self):
        """허용 자리(단계 env)에서도 표현식은 정확히 `secrets.TELEGRAM_…` 여야 하고 환경변수 이름과 같아야 한다 — 대소문자만 다른 것도 오류."""
        for env in ("TELEGRAM_BOT_TOKEN: ${{ secrets.telegram_bot_token }}", "telegram_bot_token: ${{ secrets.TELEGRAM_BOT_TOKEN }}",
                    "Telegram_Chat_Id: ${{ secrets.Telegram_Chat_Id }}"):
            with self.subTest(env=env):
                found = self.check(tg_step(env=env))
                self.assertEqual(self.marks(found), [("WF-13", "ERROR")])
        step = "- uses: someone/ok-action@0123456789abcdef0123456789abcdef01234567\n  with:\n    token: ${{ secrets.Telegram_Bot_Token }}"
        found = self.check(step_text=step)
        self.assertEqual((self.marks(found), self.place(found[0])), ([("WF-13", "ERROR")], "jobs.j.steps.0.with.token"))

    def test_container_and_service_env_are_errors(self):
        """독립 검증 V02: 잡의 container.env·services.<이름>.env 에 시크릿을 넘기는 것은 단계 env 가 아니라서 오류다(경로 모양이 달라도 막는다)."""
        cases = (("container", ["container:", "  image: python:3.10", "  env:", f"    TELEGRAM_BOT_TOKEN: {TG_TOKEN}"], "jobs.j.container.env.TELEGRAM_BOT_TOKEN"),
                 ("services", ["services:", "  s:", "    image: redis", "    env:", f"      TELEGRAM_CHAT_ID: {TG_CHAT}"], "jobs.j.services.s.env.TELEGRAM_CHAT_ID"))
        for name, extra, where in cases:
            with self.subTest(case=name):
                found = self.check(tg_step(env=TG_GOOD_ENV), job_extra=extra)
                self.assertEqual((self.marks(found), self.place(found[0])), ([("WF-13", "ERROR")], where))

    def test_each_misplaced_use_is_reported_separately_with_its_place(self):
        found = self.check(tg_step(run="echo $TELEGRAM_BOT_TOKEN $TELEGRAM_CHAT_ID", env=TG_GOOD_ENV), job_env=f"TELEGRAM_CHAT_ID: {TG_CHAT}")
        self.assertEqual(sorted(self.place(f) for f in found), ["jobs.j.env.TELEGRAM_CHAT_ID", "jobs.j.steps.0.run"])
        by_place = {self.place(f): f for f in found}
        self.assertIn("TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID", by_place["jobs.j.steps.0.run"].message)       # 한 문자열에 둘이 함께 있으면 이름을 모두 알린다
        self.assertIn("(TELEGRAM_CHAT_ID)", by_place["jobs.j.env.TELEGRAM_CHAT_ID"].message)

    def test_the_message_names_the_rule_and_never_contains_a_value(self):
        found = self.check(tg_step(run="echo $TELEGRAM_BOT_TOKEN", env=TG_GOOD_ENV))
        self.assertIn("G-C12", found[0].message)
        self.assertEqual(found[0].path, ".github/workflows/w.yml")
        self.assertNotRegex(found[0].message, r"[0-9]{6,}:[A-Za-z0-9_-]{30}")

    def test_a_yaml_syntax_error_is_left_to_wf0(self):
        write(self.root, ".github/workflows/w.yml", "name: [unclosed\n")
        self.assertEqual(vr.check_telegram_secrets(self.root, vr.list_files(self.root)), [])

    def test_a_missing_yaml_library_is_skipped(self):
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "w.yml").write_text(tg_yaml(tg_step(run="echo $TELEGRAM_BOT_TOKEN")), encoding="utf-8")
        original, vr.yaml = vr.yaml, None
        try:
            self.assertEqual(vr.check_telegram_secrets(self.root, vr.list_files(self.root)), [])
        finally:
            vr.yaml = original

    def test_files_outside_the_workflows_folder_are_ignored(self):
        self.assertEqual(self.check(tg_step(run="echo $TELEGRAM_BOT_TOKEN"), rel=".github/other/w.yml"), [])

    def test_run_checks_includes_the_rule(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        self.assertNotIn("WF-13", checks(vr.run_checks(root)))
        (root / ".github" / "workflows" / "extra.yml").write_text(tg_yaml(tg_step(run="echo $TELEGRAM_BOT_TOKEN")), encoding="utf-8")
        self.assertIn(("WF-13", "ERROR"), [(f.check, f.level) for f in vr.run_checks(root)])

    def test_the_real_repository_passes(self):
        self.assertEqual(vr.check_telegram_secrets(REAL, vr.list_files(REAL)), [])


class AlertStepExemptionTest(TmpCase):
    """WF-6 의 예외: run 이 정확히 `python -m pipeline.notify <이벤트> [--commit …]` 한 줄이고 timeout-minutes 가 있는 단계만 continue-on-error 를 써도 경고가 없다."""

    def check(self, run="python -m pipeline.notify chance-published --commit HEAD", timeout="timeout-minutes: 2", coe="continue-on-error: true"):
        extra = [line for line in (coe, timeout) if line]
        (self.root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        (self.root / ".github" / "workflows" / "w.yml").write_text(tg_yaml(tg_step(run=run, extra=extra)), encoding="utf-8")
        return vr.check_workflows(self.root, vr.list_files(self.root))

    def test_the_alert_step_shape_is_not_warned(self):
        for run in ("python -m pipeline.notify chance-published --commit HEAD", "python -m pipeline.notify test", "python3 -m pipeline.notify status",
                    "python -m pipeline.notify chance-published --commit 0123abcd"):
            with self.subTest(run=run):
                self.assertEqual(levels(self.check(run=run), "WF-6"), [])

    def test_without_a_positive_step_timeout_it_is_warned(self):
        for timeout in ("", "timeout-minutes: 0", "timeout-minutes: -1", "timeout-minutes: '2'", "timeout-minutes: true"):
            with self.subTest(timeout=timeout):
                self.assertEqual(levels(self.check(timeout=timeout), "WF-6"), ["WARN"])

    def test_other_commands_with_continue_on_error_are_still_warned(self):
        for run in ("python -m pipeline.run --blog x", "python generator.py", "python -m pipeline.notify chance-published --commit HEAD; echo hi",
                    "python -m pipeline.notify test && curl x", "python -m pipeline.notify test | tee log", "python -m pipeline.notifyx test",
                    "python -m pipeline.notify", "python -m pipeline.notify Test", "python -m pipeline.notify test --token x", "bash -c 'python -m pipeline.notify test'",
                    "pip install x && python -m pipeline.notify test", "python -m pipeline.notify test $(id)", "python -m pipeline.notify chance-published --commit HEAD~1"):
            with self.subTest(run=run):
                self.assertEqual(levels(self.check(run=run), "WF-6"), ["WARN"])

    def test_the_other_warning_about_hidden_failures_is_unchanged(self):
        self.assertEqual(levels(self.check(run="python -m pipeline.notify test || true"), "WF-6"), ["WARN", "WARN"])      # 알림 모양이 아니라 continue-on-error 와 `|| true` 둘 다
        self.assertEqual(self.check(coe="continue-on-error: false", run="python generator.py", timeout=""), [])

    def test_the_real_repository_has_no_hidden_failure_warning(self):
        found = [f for f in vr.check_workflows(REAL, vr.list_files(REAL)) if f.check == "WF-6"]
        self.assertEqual([f.line() for f in found], [])


def call_yaml(secrets="", uses="./.github/workflows/callee.yml", with_text="", job_extra=(), name="[공통] 부르는 쪽 시험"):
    """재사용 워크플로를 부르는 워크플로 YAML. secrets 는 `jobs.call.secrets` 아래에 그대로 넣을 줄들(들여쓰기 없이), with_text 는 `with:` 아래 줄들."""
    lines = [f'name: "{name}"', "on:", "  workflow_dispatch:", "permissions:", "  contents: read", "jobs:", "  call:", "    name: 부르기"]
    lines += [f"    uses: {uses}"]
    lines += [f"    {line}" for line in job_extra]
    if with_text:
        lines += ["    with:", *[f"      {line}" for line in with_text.splitlines()]]
    if secrets:
        lines += ["    secrets:", *[f"      {line}" for line in secrets.splitlines()]]
    return "\n".join(lines) + "\n"


def callee_yaml(declared="", steps="", description=None):
    """`on: workflow_call` 로 시크릿을 받는 쪽 워크플로 YAML. declared 는 `on.workflow_call.secrets` 아래에 그대로 넣을 줄들(들여쓰기 없이)."""
    lines = ['name: "[내부] 불리는 쪽 시험"', "on:", "  workflow_call:"]
    if declared:
        lines += ["    secrets:", *[f"      {line}" for line in declared.splitlines()]]
    lines += ["permissions:", "  contents: read", "jobs:", "  j:", "    name: 시험", "    runs-on: ubuntu-latest", "    timeout-minutes: 5", "    steps:"]
    lines += [f"      {line}" for line in (steps or "- run: echo ok").splitlines()]
    return "\n".join(lines) + "\n"


class TelegramReusableWorkflowTest(TmpCase):
    """WF-13 확장(작업 D, 독립 검증 N-4): 재사용 워크플로로 텔레그램 시크릿이 지나갈 때 허용되는 자리는 정확히 둘이다 —
    ① 이 저장소의 재사용 워크플로를 부르는 잡의 `secrets:` 에서 같은 이름으로(`${{ secrets.이름 }}` 그대로) ② 불리는 쪽 `on.workflow_call.secrets` 의 정의(선택 항목)."""

    def check(self, text, rel=".github/workflows/w.yml"):
        write(self.root, rel, text)
        return vr.check_telegram_secrets(self.root, vr.list_files(self.root))

    @staticmethod
    def marks(found):
        return [(f.check, f.level) for f in found]

    @staticmethod
    def place(finding):
        return re.search(r"자리\((.*?)\)에", finding.message).group(1)

    def test_the_caller_may_hand_both_secrets_over_by_the_same_name(self):
        self.assertEqual(self.check(call_yaml(secrets=TG_GOOD_ENV)), [])
        self.assertEqual(self.check(call_yaml(secrets=f"TELEGRAM_CHAT_ID: {TG_CHAT}")), [])                    # 하나만도 된다
        self.assertEqual(self.check(call_yaml(secrets="TELEGRAM_BOT_TOKEN: ${{secrets.TELEGRAM_BOT_TOKEN}}")), [])   # 식 안의 공백

    def test_a_caller_with_other_secrets_around_is_fine(self):
        secrets = "PIPELINE_SECRET_BLOG_ID: ${{ secrets.BLOGGER_BLOG_ID }}\n" + TG_GOOD_ENV
        self.assertEqual(self.check(call_yaml(secrets=secrets)), [])

    def test_the_callee_may_declare_both_secrets_as_optional(self):
        declared = "TELEGRAM_BOT_TOKEN:\n  required: false\n  description: '휴대폰 알림용(선택)'\nTELEGRAM_CHAT_ID:\n  required: false"
        self.assertEqual(self.check(callee_yaml(declared)), [])
        self.assertEqual(self.check(callee_yaml("TELEGRAM_BOT_TOKEN:\nTELEGRAM_CHAT_ID: {}")), [])                 # 정의가 비어 있어도(선택) 된다

    def test_the_callee_still_uses_the_secret_only_in_a_step_env(self):
        declared = "TELEGRAM_BOT_TOKEN:\n  required: false"
        step_env = "- name: 알림\n  run: python -m pipeline.notify test\n  env:\n    TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}"
        self.assertEqual(self.check(callee_yaml(declared, steps=step_env)), [])
        found = self.check(callee_yaml(declared, steps="- run: echo ${{ secrets.TELEGRAM_BOT_TOKEN }}"))
        self.assertEqual((self.marks(found), self.place(found[0])), ([("WF-13", "ERROR")], "jobs.j.steps.0.run"))

    def test_a_different_value_under_a_telegram_name_is_an_error(self):
        for secrets in (f"TELEGRAM_BOT_TOKEN: {TG_CHAT}", f"TELEGRAM_CHAT_ID: {TG_TOKEN}"):
            with self.subTest(secrets=secrets):
                found = self.check(call_yaml(secrets=secrets))
                self.assertEqual(self.marks(found), [("WF-13", "ERROR")])

    def test_decorated_or_computed_values_are_errors(self):
        values = (f'"{TG_TOKEN}-x"', "\"${{ secrets.TELEGRAM_BOT_TOKEN || 'x' }}\"", "\"${{ format('{0}', secrets.TELEGRAM_BOT_TOKEN) }}\"", f'"{TG_TOKEN} {TG_CHAT}"')
        for value in values:
            with self.subTest(value=value[:40]):
                found = self.check(call_yaml(secrets=f"TELEGRAM_BOT_TOKEN: {value}"))
                self.assertEqual((self.marks(found), self.place(found[0])), ([("WF-13", "ERROR")], "jobs.call.secrets.TELEGRAM_BOT_TOKEN"))

    def test_a_key_that_only_differs_in_letter_case_is_an_error(self):
        for secrets in (f"telegram_bot_token: {TG_TOKEN}", "TELEGRAM_BOT_TOKEN: ${{ secrets.telegram_bot_token }}", f"Telegram_Chat_Id: {TG_CHAT}"):
            with self.subTest(secrets=secrets):
                self.assertEqual(self.marks(self.check(call_yaml(secrets=secrets))), [("WF-13", "ERROR")])

    def test_a_telegram_name_with_an_unrelated_value_is_an_error_even_though_the_value_has_no_name(self):
        found = self.check(call_yaml(secrets="TELEGRAM_BOT_TOKEN: ${{ secrets.GEMINI_API_KEY }}"))
        self.assertEqual(self.marks(found), [("WF-13", "ERROR")])
        self.assertIn("jobs.call.secrets.TELEGRAM_BOT_TOKEN", found[0].message)
        self.assertEqual(self.marks(self.check(call_yaml(secrets="TELEGRAM_CHAT_ID: plain"))), [("WF-13", "ERROR")])

    def test_handing_the_secrets_to_a_workflow_in_another_repository_is_an_error(self):
        for uses in ("octo/repo/.github/workflows/x.yml@0123456789abcdef0123456789abcdef01234567", "./not-a-workflow-folder/x.yml", "./.github/workflows/sub/x.yml",
                     "./.github/actions/x", "docker://image",
                     "./.github/workflows/x.yml@main", "./.github/workflows/x.yml/extra", "octo/./.github/workflows/x.yml"):    # 이 저장소 것처럼 보이지만 앞뒤에 더 붙은 것(변이 V04: 부분 일치로 바뀌면 통과해 버린다)
            with self.subTest(uses=uses):
                found = self.check(call_yaml(secrets=TG_GOOD_ENV, uses=uses))
                self.assertEqual([self.place(f) for f in found], ["jobs.call.secrets.TELEGRAM_BOT_TOKEN", "jobs.call.secrets.TELEGRAM_CHAT_ID"])

    def test_a_job_that_is_not_a_reusable_call_cannot_carry_a_secrets_mapping(self):
        text = tg_yaml(tg_step(env=TG_GOOD_ENV), job_extra=["secrets:", f"  TELEGRAM_BOT_TOKEN: {TG_TOKEN}"])
        found = self.check(text)
        self.assertEqual((self.marks(found), self.place(found[0])), ([("WF-13", "ERROR")], "jobs.j.secrets.TELEGRAM_BOT_TOKEN"))

    def test_secrets_inherit_is_an_error_because_it_hands_over_every_secret_without_a_name(self):
        for text in ("inherit", " Inherit ", "INHERIT"):
            with self.subTest(text=text):
                found = self.check(call_yaml(job_extra=[f"secrets: '{text}'"]))
                self.assertEqual(self.marks(found), [("WF-13", "ERROR")])
                self.assertIn("jobs.call.secrets", found[0].message)
                self.assertIn("inherit", found[0].message)
        self.assertEqual(self.check(call_yaml(job_extra=["secrets: inherit"]))[0].check, "WF-13")     # 따옴표 없는 inherit 도 같다

    def test_inheriting_is_reported_for_any_job_even_with_no_telegram_name_anywhere(self):
        self.assertEqual(self.marks(self.check(call_yaml(job_extra=["secrets: inherit"], uses="./.github/workflows/tistory.yml"))), [("WF-13", "ERROR")])

    def test_the_with_inputs_of_a_call_cannot_carry_the_secret(self):
        found = self.check(call_yaml(with_text=f"token: {TG_TOKEN}", secrets=TG_GOOD_ENV))
        self.assertEqual((self.marks(found), self.place(found[0])), ([("WF-13", "ERROR")], "jobs.call.with.token"))

    def test_the_callee_declaration_must_be_optional(self):
        found = self.check(callee_yaml("TELEGRAM_BOT_TOKEN:\n  required: true"))
        self.assertEqual(self.marks(found), [("WF-13", "ERROR")])
        self.assertIn("required: true", found[0].message)
        self.assertIn("on.workflow_call.secrets.TELEGRAM_BOT_TOKEN", found[0].message)

    def test_the_callee_declaration_name_must_be_exactly_upper_case(self):
        for declared in ("telegram_bot_token:\n  required: false", "Telegram_Chat_Id: {}"):
            with self.subTest(declared=declared):
                found = self.check(callee_yaml(declared))
                self.assertEqual(self.marks(found), [("WF-13", "ERROR")])
                self.assertIn("대문자", found[0].message)

    def test_the_callee_declaration_allows_only_required_and_description(self):
        found = self.check(callee_yaml("TELEGRAM_BOT_TOKEN:\n  required: false\n  default: abc"))
        self.assertEqual(self.marks(found), [("WF-13", "ERROR")])
        self.assertIn("default", found[0].message)
        found = self.check(callee_yaml("TELEGRAM_BOT_TOKEN: abc"))                                             # 문자열 정의 — 값처럼 보이는 것을 정의에 두지 않는다
        self.assertTrue(found and all(f.check == "WF-13" for f in found))

    def test_the_description_of_a_declared_secret_cannot_repeat_the_name(self):
        found = self.check(callee_yaml("TELEGRAM_BOT_TOKEN:\n  required: false\n  description: 'TELEGRAM_BOT_TOKEN 알림용'"))
        self.assertEqual(self.marks(found), [("WF-13", "ERROR")])
        self.assertTrue(self.place(found[0]).endswith("secrets.TELEGRAM_BOT_TOKEN.description"), self.place(found[0]))

    def test_declaring_other_secrets_is_not_judged(self):
        self.assertEqual(self.check(callee_yaml("PIPELINE_SECRET_BLOG_ID:\n  required: true\nOTHER: {}")), [])

    def test_the_rule_runs_inside_run_checks(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        self.assertNotIn("WF-13", checks(vr.run_checks(root)))
        write(root, ".github/workflows/bad.yml", call_yaml(job_extra=["secrets: inherit"], uses="./.github/workflows/blogger.yml"))
        self.assertIn(("WF-13", "ERROR"), [(f.check, f.level) for f in vr.run_checks(root)])

    def test_the_real_blogger_wrappers_and_the_reusable_workflow_pass(self):
        found = vr.check_telegram_secrets(REAL, vr.list_files(REAL))
        self.assertEqual([f.line() for f in found], [])
        for wrapper in ("blogger-en.yml", "blogger-ko.yml"):
            self.assertIn("TELEGRAM_BOT_TOKEN", (REAL / ".github" / "workflows" / wrapper).read_text(encoding="utf-8"))   # 시험이 비어 있지 않다


class BloggerWrapperRuleTest(TmpCase):
    """REG-6(작업 D): Blogger 블로그의 워크플로(채널별 래퍼)가 레지스트리와 맞는지 — 어느 블로그를 어느 시크릿 이름으로 돌리는지가 레지스트리가 아니라 래퍼의 글자로 정해지기 때문이다."""

    def setUp(self):
        super().setUp()
        self.reg_root = registry_root(self.root, chance_extra=DEPLOY_STEP)

    def check(self, root=None):
        root = root or self.reg_root
        return vr.check_blogger_wrappers(root, vr.list_files(root))

    def edit(self, wrapper, old, new, count=1):
        path = self.reg_root / ".github" / "workflows" / wrapper
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), count, (old, text))
        path.write_text(text.replace(old, new), encoding="utf-8")

    def messages(self):
        return [f.message for f in self.check()]

    def test_consistent_wrappers_pass(self):
        self.assertEqual(self.check(), [])

    def test_a_wrapper_that_runs_the_other_blog_is_an_error(self):
        self.edit("blogger-en.yml", "blog: blogger_macat", "blog: blogger_kcyoon")
        found = self.check()
        self.assertEqual([(f.check, f.level, f.path) for f in found], [("REG-6", "ERROR", ".github/workflows/blogger-en.yml")])
        self.assertIn("blogger_macat", found[0].message)
        self.assertIn("with.blog", found[0].message)

    def test_the_blog_key_must_be_a_literal_not_an_expression(self):
        self.edit("blogger-ko.yml", "blog: blogger_kcyoon", "blog: ${{ github.event.inputs.blog }}")
        self.assertTrue(any("with.blog" in m for m in self.messages()))

    def test_every_input_must_be_handed_over_explicitly(self):
        self.edit("blogger-en.yml", "      auth_check: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.auth_check == 'true' }}\n", "")
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("빠진 것: auth_check", messages[0])

    def test_an_unknown_input_is_an_error(self):
        self.edit("blogger-en.yml", "      blog: blogger_macat\n", "      blog: blogger_macat\n      dry_runn: 'true'\n")
        self.assertTrue(any("모르는 것: dry_runn" in m for m in self.messages()))

    def test_the_korean_wrapper_may_not_hand_over_the_english_secrets(self):
        """한글 Blogger 는 영문과 계정·OAuth 클라이언트가 달라야 한다 — 한글 래퍼가 영문 시크릿 이름(BLOGGER_*)을 넘기면 오류다(역할마다 따로 알린다)."""
        for name in ("BLOGGER_KO_BLOG_ID", "BLOGGER_KO_CLIENT_ID", "BLOGGER_KO_CLIENT_SECRET", "BLOGGER_KO_REFRESH_TOKEN"):
            self.edit("blogger-ko.yml", f"secrets.{name}", f"secrets.{name.replace('BLOGGER_KO_', 'BLOGGER_')}")
        messages = self.messages()
        self.assertEqual(len(messages), 4, messages)
        for role in ("BLOG_ID", "CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN"):
            self.assertTrue(any(f"PIPELINE_SECRET_{role}" in m and f"BLOGGER_KO_{role}" in m for m in messages), (role, messages))

    def test_one_swapped_secret_is_reported_once(self):
        self.edit("blogger-ko.yml", "secrets.BLOGGER_KO_REFRESH_TOKEN", "secrets.BLOGGER_REFRESH_TOKEN")
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("PIPELINE_SECRET_REFRESH_TOKEN", messages[0])

    def test_a_missing_role_is_an_error(self):
        self.edit("blogger-en.yml", "      PIPELINE_SECRET_CLIENT_ID: ${{ secrets.BLOGGER_CLIENT_ID }}\n", "")
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("PIPELINE_SECRET_CLIENT_ID", messages[0])

    def test_a_secret_that_is_not_this_blogs_is_an_error(self):
        self.edit("blogger-en.yml", "    secrets:\n", "    secrets:\n      PIPELINE_SECRET_EXTRA: ${{ secrets.BLOGGER_KO_BLOG_ID }}\n")
        self.assertTrue(any("이 블로그의 것이 아닌 시크릿이 있습니다(PIPELINE_SECRET_EXTRA)" in m for m in self.messages()))

    def test_a_wrapper_that_forgets_the_optional_unsplash_key_is_an_error_because_the_registry_declares_it(self):
        """레지스트리가 블로그의 `unsplash_key` 역할을 선언하면 래퍼도 넘겨야 한다 — 선택 시크릿이어도 '무엇을 넘기는지'는 레지스트리와 래퍼가 같아야 한다(REG-6)."""
        for wrapper in ("blogger-en.yml", "blogger-ko.yml"):
            self.edit(wrapper, "      PIPELINE_SECRET_UNSPLASH_KEY: ${{ secrets.UNSPLASH_ACCESS_KEY }}\n", "")
            found = self.check()
            self.assertEqual([(f.check, f.level, f.path) for f in found], [("REG-6", "ERROR", f".github/workflows/{wrapper}")], wrapper)
            self.assertIn("PIPELINE_SECRET_UNSPLASH_KEY", found[0].message)
            self.assertIn("UNSPLASH_ACCESS_KEY", found[0].message)
            self.edit(wrapper, "    secrets:\n", "    secrets:\n      PIPELINE_SECRET_UNSPLASH_KEY: ${{ secrets.UNSPLASH_ACCESS_KEY }}\n")
        self.assertEqual(self.check(), [])

    def test_a_wrapper_that_hands_over_another_secret_as_the_unsplash_key_is_an_error(self):
        """다른 블로그의 시크릿 이름(한글 블로그 ID)이나 다른 용도의 키(Gemini)를 Unsplash 키 자리에 넘기면 오류다."""
        for other in ("BLOGGER_KO_BLOG_ID", "BLOGGER_BLOG_ID", "GEMINI_API_KEY", "UNSPLASH_ACCESS_KEY_OLD"):
            self.edit("blogger-en.yml", "PIPELINE_SECRET_UNSPLASH_KEY: ${{ secrets.UNSPLASH_ACCESS_KEY }}", "PIPELINE_SECRET_UNSPLASH_KEY: ${{ secrets.%s }}" % other)
            messages = self.messages()
            self.assertEqual(len(messages), 1, (other, messages))
            self.assertIn("PIPELINE_SECRET_UNSPLASH_KEY", messages[0])
            self.edit("blogger-en.yml", "PIPELINE_SECRET_UNSPLASH_KEY: ${{ secrets.%s }}" % other, "PIPELINE_SECRET_UNSPLASH_KEY: ${{ secrets.UNSPLASH_ACCESS_KEY }}")
        self.assertEqual(self.check(), [])

    def test_both_wrappers_hand_over_the_same_shared_unsplash_secret_name(self):
        text = {name: (self.reg_root / ".github" / "workflows" / name).read_text(encoding="utf-8") for name in ("blogger-en.yml", "blogger-ko.yml")}
        for name, content in text.items():
            self.assertEqual(content.count("PIPELINE_SECRET_UNSPLASH_KEY: ${{ secrets.UNSPLASH_ACCESS_KEY }}"), 1, name)

    def test_a_blog_whose_registry_entry_has_no_unsplash_role_must_not_hand_it_over(self):
        """끄는 법(docs/ARCHITECTURE.md §4-7): 레지스트리에서 역할을 빼면 래퍼의 한 줄도 함께 빼야 한다 — 하나만 빼면 REG-6 이 막는다."""
        path = self.reg_root / "pipeline" / "blogs.json"
        reg = json.loads(path.read_text(encoding="utf-8"))
        next(blog for blog in reg["blogs"] if blog["key"] == "blogger_macat")["secrets"].pop("unsplash_key")
        path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)                                    # 레지스트리에는 없는데 래퍼가 넘긴다
        self.assertIn("이 블로그의 것이 아닌 시크릿이 있습니다(PIPELINE_SECRET_UNSPLASH_KEY)", messages[0])
        self.edit("blogger-en.yml", "      PIPELINE_SECRET_UNSPLASH_KEY: ${{ secrets.UNSPLASH_ACCESS_KEY }}\n", "")
        self.assertEqual(self.check(), [])                                              # 둘 다 빼면 통과한다(한글 블로그는 그대로 넘기고 있다)

    def test_the_telegram_names_are_the_only_other_secrets_a_wrapper_may_hand_over(self):
        self.edit("blogger-en.yml", "    secrets:\n", f"    secrets:\n      TELEGRAM_BOT_TOKEN: {TG_TOKEN}\n      TELEGRAM_CHAT_ID: {TG_CHAT}\n")
        self.assertEqual(self.check(), [])                                    # 모양 자체는 WF-13 이 따로 본다

    def test_secrets_inherit_leaves_every_role_missing(self):
        path = self.reg_root / ".github" / "workflows" / "blogger-en.yml"
        text = path.read_text(encoding="utf-8")
        head = text[:text.index("    secrets:\n")]
        path.write_text(head + "    secrets: inherit\n", encoding="utf-8")
        self.assertEqual(len(self.messages()), 5 + 1, self.messages())         # 역할 6개(llm_api_key·선택 unsplash_key 포함) 모두 빠짐
        self.assertIn(("WF-13", "ERROR"), [(f.check, f.level) for f in vr.run_checks(self.reg_root)])

    def test_the_call_job_needs_contents_write_because_a_called_workflow_cannot_raise_permissions(self):
        self.edit("blogger-en.yml", "    permissions:\n      contents: write\n", "")
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("contents: write", messages[0])
        self.edit("blogger-ko.yml", "contents: write", "contents: read")
        self.assertEqual(len(self.messages()), 2)

    def test_the_concurrency_group_is_required_and_cannot_collide_with_the_reusable_workflows_own_group(self):
        self.edit("blogger-en.yml", "  group: blogger-en\n", "  group: blogger-blogger_macat\n")
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("blogger-blogger_macat", messages[0])
        self.assertIn("서로를 기다려", messages[0])
        self.edit("blogger-en.yml", "  group: blogger-blogger_macat\n", "  group: blogger-en\n")
        path = self.reg_root / ".github" / "workflows" / "blogger-ko.yml"
        path.write_text(path.read_text(encoding="utf-8").replace("concurrency:\n  group: blogger-ko\n", ""), encoding="utf-8")
        self.assertTrue(any("concurrency.group 이 없습니다" in m for m in self.messages()))

    def test_two_wrappers_cannot_share_one_group(self):
        self.edit("blogger-ko.yml", "  group: blogger-ko\n", "  group: blogger-en\n")
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("영문·한글 실행이 서로를 막지 않습니다", messages[0])

    def test_the_group_names_are_compared_without_regard_to_case_like_github_does(self):
        """독립 검증 N10: GitHub 은 concurrency 그룹 이름의 대소문자를 구분하지 않는다 — 'Blogger-EN' 과 'blogger-en' 은 같은 줄이다. 철자만 대소문자로 바꿔 검사를 피할 수 없다."""
        for variant in ("Blogger-EN", "BLOGGER-EN", "blogger-En"):
            with self.subTest(variant=variant):
                self.edit("blogger-ko.yml", "  group: blogger-ko\n", f"  group: {variant}\n")
                messages = self.messages()
                self.assertEqual(len(messages), 1, messages)
                self.assertIn("대소문자는 구분하지 않습니다", messages[0])
                self.assertIn(variant, messages[0])
                self.assertIn("blogger-en", messages[0])
                self.edit("blogger-ko.yml", f"  group: {variant}\n", "  group: blogger-ko\n")
        self.assertEqual(self.check(), [])

    def test_a_group_that_differs_only_in_case_from_the_reusable_workflows_own_group_is_an_error(self):
        for variant in ("Blogger-Blogger_Macat", "BLOGGER-BLOGGER_KCYOON"):
            with self.subTest(variant=variant):
                self.edit("blogger-en.yml", "  group: blogger-en\n", f"  group: {variant}\n")
                messages = self.messages()
                self.assertEqual(len(messages), 1, messages)
                self.assertIn("서로를 기다려", messages[0])
                self.assertIn("대소문자를 구분하지 않습니다", messages[0])
                self.edit("blogger-en.yml", f"  group: {variant}\n", "  group: blogger-en\n")

    def test_distinct_names_are_not_confused_by_the_case_folding(self):
        self.edit("blogger-ko.yml", "  group: blogger-ko\n", "  group: Blogger-Korean-Channel\n")
        self.assertEqual(self.check(), [])

    def test_the_call_job_permissions_are_exactly_contents_write_so_extra_permissions_are_errors(self):
        """독립 검증 N10: 호출 잡의 권한은 공용 워크플로가 쓸 수 있는 상한이다. contents: write 에 id-token·issues 같은 권한을 더하면 오류다."""
        for extra in ("id-token: write", "issues: write", "actions: write", "pull-requests: write", "packages: none", "contents2: write"):
            with self.subTest(extra=extra):
                self.edit("blogger-en.yml", "    permissions:\n      contents: write\n", f"    permissions:\n      contents: write\n      {extra}\n")
                messages = self.messages()
                self.assertEqual(len(messages), 1, messages)
                self.assertIn("contents: write 외의 권한이 있습니다", messages[0])
                self.assertIn(extra.split(":")[0], messages[0])
                self.edit("blogger-en.yml", f"    permissions:\n      contents: write\n      {extra}\n", "    permissions:\n      contents: write\n")
        self.assertEqual(self.check(), [])

    def test_two_extra_permissions_are_listed_together_and_each_wrapper_is_judged_on_its_own(self):
        self.edit("blogger-ko.yml", "    permissions:\n      contents: write\n", "    permissions:\n      contents: write\n      issues: write\n      id-token: write\n")
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("(id-token, issues)", messages[0])
        self.edit("blogger-en.yml", "    permissions:\n      contents: write\n", "    permissions:\n      contents: write\n      actions: read\n")
        self.assertEqual(len(self.messages()), 2)

    def test_the_same_permissions_written_another_way_still_pass_and_a_string_form_is_not_contents_write(self):
        self.edit("blogger-en.yml", "    permissions:\n      contents: write\n", "    permissions: {contents: write}\n")
        self.assertEqual(self.check(), [])                                   # 같은 뜻의 다른 표기
        self.edit("blogger-en.yml", "    permissions: {contents: write}\n", '    permissions:\n      contents: "write"\n')
        self.assertEqual(self.check(), [])
        self.edit("blogger-en.yml", '    permissions:\n      contents: "write"\n', "    permissions: write-all\n")
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("permissions: contents: write 가 없습니다", messages[0])      # write-all 은 contents: write 가 아니다

    def test_a_workflow_that_does_not_call_the_reusable_one_is_an_error(self):
        write(self.reg_root, ".github/workflows/blogger-ko.yml", blogger_wrapper("Blogger 한글", "30 3 * * *", "blogger_kcyoon", "blogger-ko", {}, wired=False).replace(
            "uses: ./.github/workflows/blogger.yml", "runs-on: ubuntu-latest"))
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("정확히 하나여야 합니다(지금 0개)", messages[0])

    def test_two_call_jobs_are_an_error(self):
        path = self.reg_root / ".github" / "workflows" / "blogger-en.yml"
        text = path.read_text(encoding="utf-8")
        job = text[text.index("jobs:\n") + len("jobs:\n"):]
        path.write_text(text + job.replace("blogger:", "blogger_two:", 1), encoding="utf-8")
        self.assertTrue(any("정확히 하나여야 합니다(지금 2개)" in m for m in self.messages()))

    def test_chance_and_other_platforms_are_not_judged(self):
        write(self.reg_root, ".github/workflows/chanceblog.yml", "name: '[Chance] 챈스 글'\non: push\npermissions:\n  contents: read\njobs: {}\n")
        self.assertEqual(self.check(), [])

    def test_a_yaml_syntax_error_is_left_to_wf0(self):
        write(self.reg_root, ".github/workflows/blogger-en.yml", "name: [unclosed\n")
        self.assertEqual(self.check(), [])

    def test_an_invalid_registry_is_left_to_reg1(self):
        path = self.reg_root / "pipeline" / "blogs.json"
        reg = json.loads(path.read_text(encoding="utf-8"))
        reg["blogs"][1]["mode"] = "yolo"
        path.write_text(json.dumps(reg), encoding="utf-8")
        self.assertEqual(self.check(), [])
        self.assertIn("REG-1", checks(vr.run_checks(self.reg_root)))

    def test_a_missing_yaml_library_is_skipped(self):
        original, vr.yaml = vr.yaml, None
        try:
            self.assertEqual(vr.check_blogger_wrappers(self.reg_root, vr.list_files(self.reg_root)), [])
        finally:
            vr.yaml = original

    def test_run_checks_includes_the_rule_and_the_cli_fails_on_it(self):
        self.assertNotIn("REG-6", checks(vr.run_checks(self.reg_root)))
        self.edit("blogger-ko.yml", "secrets.BLOGGER_KO_BLOG_ID", "secrets.BLOGGER_BLOG_ID")
        self.assertIn(("REG-6", "ERROR"), [(f.check, f.level) for f in vr.run_checks(self.reg_root)])
        out = io.StringIO()
        with redirect_stdout(out):
            code = vr.main(["--root", str(self.reg_root)])
        self.assertEqual(code, 1)
        self.assertIn("[REG-6]", out.getvalue())

    def test_the_messages_name_the_file_and_never_contain_a_secret_value(self):
        self.edit("blogger-ko.yml", "secrets.BLOGGER_KO_BLOG_ID", "secrets.BLOGGER_BLOG_ID")
        found = self.check()
        self.assertEqual(found[0].path, ".github/workflows/blogger-ko.yml")
        self.assertIn("BLOGGER_KO_BLOG_ID", found[0].message)               # 이름은 알려 준다(값은 저장소에 없다)

    def test_the_real_repository_passes(self):
        found = vr.check_blogger_wrappers(REAL, vr.list_files(REAL))
        self.assertEqual([f.line() for f in found], [])

    def test_the_real_wrappers_match_the_registry_workflow_field(self):
        reg = reg_mod.load_registry(REAL / "pipeline" / "blogs.json")
        files = {blog["key"]: blog["workflow"] for blog in reg["blogs"] if blog["platform"] == "blogger"}
        self.assertEqual(files, {"blogger_macat": ".github/workflows/blogger-en.yml", "blogger_kcyoon": ".github/workflows/blogger-ko.yml"})
        self.assertEqual(vr.BLOGGER_REUSABLE, "./.github/workflows/blogger.yml")
        self.assertEqual(vr.BLOGGER_CALL_INPUTS, ("blog", "topic", "dry_run", "publish", "auth_check"))


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
