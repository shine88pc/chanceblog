import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from unittest import mock

import _bootstrap  # noqa: F401
from pipeline import plan, registry
from pipeline.health import Finding
from test_run import make_root

try:
    import yaml
except ImportError:  # pragma: no cover - requirements-dev.txt 가 설치하는 의존성
    yaml = None

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402


def registry_all_auto():
    """실제 레지스트리의 모든 블로그를 켜 둔 사본. 운영 중 일시 정지(mode off)와 무관하게 로직을 시험한다."""
    reg = registry.load_registry()
    for blog in reg["blogs"]:
        blog["mode"] = "auto"
    return reg


class PlanTest(unittest.TestCase):
    def test_matrix_for_blogger(self):
        matrix = plan.build_matrix(registry_all_auto(), "blogger")
        self.assertEqual(len(matrix["include"]), 1)
        item = matrix["include"][0]
        self.assertEqual(item["key"], "blogger_macat")
        self.assertEqual(item["secret_refresh_token"], "BLOGGER_REFRESH_TOKEN")
        self.assertEqual(item["history"], "blogger_history.json")
        self.assertNotIn("value", json.dumps(item))  # 이름만 있고 값은 없다

    def test_only_filters_to_one_blog(self):
        reg = registry_all_auto()
        self.assertEqual([i["key"] for i in plan.build_matrix(reg, "blogger", only="blogger_macat")["include"]],
                         ["blogger_macat"])
        self.assertEqual(plan.build_matrix(reg, "blogger", only="nope")["include"], [])

    def test_matrix_excludes_off_and_filters_platform(self):
        reg = registry_all_auto()
        self.assertEqual([i["key"] for i in plan.build_matrix(reg)["include"]], ["chance", "blogger_macat"])
        reg["blogs"][1]["mode"] = "off"
        self.assertEqual(plan.build_matrix(reg, "blogger")["include"], [])

    def test_cli_outputs_compact_json_and_count(self):
        with mock.patch.object(plan, "load_registry", return_value=registry_all_auto()):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(plan.main(["--platform", "blogger"]), 0)
            self.assertEqual(json.loads(buf.getvalue())["include"][0]["key"], "blogger_macat")
            self.assertNotIn("\n", buf.getvalue().strip())
            buf = io.StringIO()
            with redirect_stdout(buf):
                plan.main(["--platform", "blogger", "--count"])
            self.assertEqual(buf.getvalue().strip(), "1")

    def test_unknown_only_key_is_an_error_not_an_empty_matrix(self):
        """--only 에 오타를 내면 대상이 0개가 되어 generate 잡이 조용히 건너뛰어지던(초록) 문제."""
        with mock.patch.object(plan, "load_registry", return_value=registry_all_auto()):
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = plan.main(["--platform", "blogger", "--only", "blogger_macta"])
        self.assertEqual(code, 1)
        self.assertIn("blogger_macta", err.getvalue())
        self.assertIn("blogger_macat", err.getvalue())   # 유효한 key 안내
        self.assertIn("chance", err.getvalue())

    def test_only_key_of_another_platform_is_an_error_not_an_empty_matrix(self):
        """레지스트리에는 있지만 이 플랫폼 블로그가 아닌 key(blogger 워크플로에 chance)도 대상 0개(초록)가 아니라 오류다."""
        for extra in ([], ["--count"]):
            with self.subTest(extra=extra), mock.patch.object(plan, "load_registry", return_value=registry_all_auto()):
                err, out = io.StringIO(), io.StringIO()
                with redirect_stderr(err), redirect_stdout(out):
                    code = plan.main(["--platform", "blogger", "--only", "chance", *extra])
                self.assertEqual(code, 1)
                self.assertEqual(out.getvalue(), "")                 # 빈 매트릭스·"0" 을 출력하지 않는다
                self.assertIn("chance", err.getvalue())
                self.assertIn("blogger 가 아니라 jekyll-git 플랫폼 블로그", err.getvalue())
                self.assertIn("blogger_macat", err.getvalue())       # 이 플랫폼의 유효한 key 안내

    def test_only_without_platform_may_pick_any_registered_blog(self):
        """플랫폼 검사는 --platform 을 함께 줄 때만 한다(--only 단독은 레지스트리의 어떤 key 든 된다)."""
        with mock.patch.object(plan, "load_registry", return_value=registry_all_auto()):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(plan.main(["--only", "chance", "--count"]), 0)
            self.assertEqual(buf.getvalue().strip(), "1")

    def test_paused_blog_is_zero_targets_without_error(self):
        """mode=off 로 정지한 블로그는 오류가 아니라 대상 0개다(워크플로가 notice 를 남긴다)."""
        reg = registry_all_auto()
        reg["blogs"][1]["mode"] = "off"
        with mock.patch.object(plan, "load_registry", return_value=reg):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(plan.main(["--platform", "blogger", "--count"]), 0)
            self.assertEqual(buf.getvalue().strip(), "0")
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(plan.main(["--platform", "blogger", "--only", "blogger_macat", "--count"]), 0)
            self.assertEqual(buf.getvalue().strip(), "0")


def plan_step_script():
    """blogger.yml 의 plan 잡에서 id=plan 인 단계의 run 스크립트를 그대로 꺼낸다."""
    workflow = yaml.safe_load((_bootstrap.ROOT / ".github" / "workflows" / "blogger.yml").read_text(encoding="utf-8"))
    return next(step["run"] for step in workflow["jobs"]["plan"]["steps"] if step.get("id") == "plan")


@unittest.skipUnless(yaml is not None, "PyYAML(requirements-dev.txt)이 필요합니다(CI 에서는 항상 실행됩니다)")
class WorkflowGenerateJobTest(unittest.TestCase):
    def test_generate_runs_unless_plan_found_zero_targets(self):
        """generate 잡은 plan 이 찾은 대상이 0개일 때만 건너뛴다. 이 조건이 사라지거나 '!= 1' 로 틀어지면(독립 검증의 변이)
        대상이 1개일 때 generate 가 건너뛰어져 [SKIP]·notice 없이 초록으로 끝난다."""
        workflow = yaml.safe_load((_bootstrap.ROOT / ".github" / "workflows" / "blogger.yml").read_text(encoding="utf-8"))
        job = workflow["jobs"]["generate"]
        self.assertEqual(job["needs"], "plan")
        self.assertEqual(job["if"], "needs.plan.outputs.count != '0'")


@unittest.skipUnless(yaml is not None and shutil.which("bash"),
                     "PyYAML(requirements-dev.txt)과 bash 가 필요합니다(CI 의 Linux 에서는 항상 실행됩니다)")
class WorkflowPlanStepTest(unittest.TestCase):
    """blogger.yml 의 plan 단계를 GitHub 처럼 `bash -e <스크립트>` 로 실제 실행한다.
    레지스트리·plan 코드는 임시 저장소에 복사해 쓴다(운영 중 mode 와 무관하게 시험한다)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.script = self.work / "plan_step.sh"
        self.script.write_bytes(plan_step_script().encode("utf-8"))  # 줄 끝은 LF 여야 한다(CRLF 면 bash 가 오류를 낸다)

    def repo(self, mode):
        root = self.work / f"repo_{mode}"
        make_root(root, mode=mode)  # 레지스트리·프로필·프롬프트(blogger_macat 의 mode 만 바꾼다)
        ignore = shutil.ignore_patterns("__pycache__", "blogs.json", "profiles")
        shutil.copytree(_bootstrap.ROOT / "pipeline", root / "pipeline", dirs_exist_ok=True, ignore=ignore)
        return root

    def run_step(self, root, only=""):
        output, summary = root / "github_output", root / "github_step_summary"
        output.write_bytes(b"")
        summary.write_bytes(b"")
        env = {**os.environ, "PYTHONUTF8": "1", "ONLY_BLOG": only,
               "GITHUB_OUTPUT": output.as_posix(), "GITHUB_STEP_SUMMARY": summary.as_posix(),
               "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")}
        proc = subprocess.run(["bash", "-e", self.script.as_posix()], cwd=str(root), env=env, capture_output=True,
                              text=True, encoding="utf-8", timeout=120)
        return proc, output.read_text(encoding="utf-8"), summary.read_text(encoding="utf-8")

    def test_plan_errors_turn_the_step_red_and_zero_targets_are_announced(self):
        auto, off = self.repo("auto"), self.repo("off")

        with self.subTest("정상: 대상 1개, 알림 없음"):
            proc, output, summary = self.run_step(auto)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("count=1", output.splitlines())
            self.assertIn('"key":"blogger_macat"', output)
            self.assertNotIn("::notice::", proc.stdout)
            self.assertEqual(summary, "")

        for label, only in (("blogger 블로그가 모두 정지", ""), ("지정한 블로그가 정지", "blogger_macat")):
            with self.subTest(label):
                proc, output, summary = self.run_step(off, only)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("count=0", output.splitlines())
                self.assertIn('matrix={"include":[]}', output.splitlines())
                self.assertIn("::notice::실행할 Blogger 블로그가 없습니다", proc.stdout)
                self.assertIn("대상 0개", summary)
                self.assertIn("지정한 블로그", summary)  # 수동 실행(--only)에서도 맞는 설명이다
                self.assertIn("mode=off", summary)

        # plan 이 실패하면 단계도 실패해야 한다. 명령 치환을 echo 안에 넣던 예전 스크립트는 matrix= 만 쓰고 초록으로 끝났다.
        for label, only, hint in (("레지스트리에 없는 key(오타)", "blogger_macta", "레지스트리에 없는 key"),
                                  ("다른 플랫폼 블로그의 key", "chance", "jekyll-git")):
            with self.subTest(label):
                proc, output, summary = self.run_step(auto, only)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(output, "")  # matrix=·count= 를 한 줄도 쓰지 않는다
                self.assertEqual(summary, "")
                self.assertIn(hint, proc.stderr)


class FakeClient:
    def __init__(self):
        self.created, self.comments, self.closed = [], [], []

    def create_issue(self, title, body, assignees=None):
        self.created.append((title, body))
        self.assignees = assignees

    def update_body(self, number, body):
        self.updated = getattr(self, "updated", []) + [number]

    def comment(self, number, body):
        self.comments.append(number)

    def close(self, number):
        self.closed.append(number)


F1 = Finding("blogger_macat", "STALE", "critical", "멈춤")
F2 = Finding("chance", "FAIL_STREAK", "critical", "연속 실패")


class SyncIssuesTest(unittest.TestCase):
    def test_creates_missing_and_does_not_duplicate(self):
        client = FakeClient()
        created, closed, *_ = watchdog.sync_issues([F1, F2], [{"title": F1.title, "number": 5}], client, out=lambda s: None)
        self.assertEqual(created, [F2.title])
        self.assertEqual(closed, [])
        self.assertEqual([t for t, _ in client.created], [F2.title])
        self.assertIn("HANDLER.md", client.created[0][1])

    def test_closes_resolved_watchdog_issues_only(self):
        client = FakeClient()
        issues = [{"title": F1.title, "number": 5}, {"title": "[Watchdog] x: GONE", "number": 6},
                  {"title": "사람이 연 일반 이슈", "number": 7}]
        created, closed, *_ = watchdog.sync_issues([F1], issues, client, out=lambda s: None)
        self.assertEqual(closed, ["[Watchdog] x: GONE"])
        self.assertEqual(client.closed, [6])
        self.assertEqual(client.comments, [6])

    def test_dry_run_calls_nothing(self):
        client = FakeClient()
        created, closed, *_ = watchdog.sync_issues([F1], [{"title": "[Watchdog] x: GONE", "number": 6}], client,
                                                   dry=True, out=lambda s: None)
        self.assertEqual((created, closed), ([F1.title], ["[Watchdog] x: GONE"]))
        self.assertEqual((client.created, client.closed, client.comments), ([], [], []))


class CollectFindingsTest(unittest.TestCase):
    def test_corrupt_history_is_reported(self):
        reg = registry.load_registry()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "history.json").write_text("{broken", encoding="utf-8")
            findings = watchdog.collect_findings(reg, tmp, datetime(2026, 10, 22, tzinfo=timezone.utc))
        self.assertIn(("chance", "STATE_CORRUPT"), [(f.blog, f.code) for f in findings])

    def test_empty_repo_reports_no_activity(self):
        reg = registry_all_auto()
        with tempfile.TemporaryDirectory() as tmp:
            findings = watchdog.collect_findings(reg, tmp, datetime(2026, 10, 22, tzinfo=timezone.utc))
        self.assertEqual(sorted((f.blog, f.code) for f in findings),
                         [("blogger_macat", "NO_ACTIVITY"), ("chance", "NO_ACTIVITY")])


if __name__ == "__main__":
    unittest.main()
