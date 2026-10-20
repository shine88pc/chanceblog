import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from edits_helpers import make_edit_root
from test_run import make_root

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

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


def registry_root(tmp, chance_cron="17 * * * *", blogger_cron="0 2 * * *", chance_extra="", blogger_matrix=True):
    root = make_root(tmp)
    write(root, ".github/workflows/chanceblog.yml", f"""
        name: chance
        on:
          schedule:
            - cron: '{chance_cron}'
        permissions:
          contents: write
        concurrency:
          group: c
        jobs:
          build:
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
        name: blogger
        on:
          schedule:
            - cron: '{blogger_cron}'
        permissions:
          contents: read
        concurrency:
          group: b
        jobs:
          j:
            runs-on: ubuntu-latest
            timeout-minutes: 5
            steps:
              - env:
                  {secrets_line}
                run: echo ok
        """)
    return root


DEPLOY_STEP = "              - run: gh workflow run pages.yml\n"


class RegistryContractTest(TmpCase):
    def test_consistent_registry_passes(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        self.assertEqual(vr.check_registry(root, vr.list_files(root)), [])

    def test_cron_drift_is_an_error(self):
        root = registry_root(self.root, chance_cron="0 * * * *", chance_extra=DEPLOY_STEP)
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

    def test_model_drift_is_warned(self):
        root = registry_root(self.root, chance_extra=DEPLOY_STEP)
        write(root, "generator.py", 'MODEL_CANDIDATES = [\n    "gemini-old-1",\n]\n')
        found = vr.check_registry(root, vr.list_files(root))
        self.assertEqual(levels(found, "REG-4"), ["WARN"])


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
