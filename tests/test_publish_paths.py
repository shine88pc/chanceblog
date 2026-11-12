"""공개 경로 시험: '사람 승인 없이 공개 사이트나 Blogger 공개 글을 바꿀 수 있는 길'의 목록(docs/PUBLISH_PATHS.md)이 실제 워크플로와 같은지, 새 쓰기 길이 생기면 빨강이 되는지,
제한 재개 잠금(레지스트리 resume_lock)의 규칙을 하나씩 어기면 검증기와 가드가 거절하고 꺼져 있으면 거절하지 않는지, 그림자 실행 워크플로가 어떤 쓰기도 못 하는지를 확인한다.

워크플로 YAML 을 직접 읽는다(네트워크 없음). 새 워크플로를 더하거나 기존 워크플로에 쓰기 권한·git push·gh 호출·새 파이썬 진입점을 더하면 이 시험이 빨강이 된다 —
그때는 docs/PUBLISH_PATHS.md 와 아래 ALLOWED 표를 같은 변경에서 고친다(검토한 쓰기 길만 표에 있다).
"""
import contextlib
import io
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
import test_publish_lock as lock_tests
from lock_helpers import (CHANCE, EXTRA, KCYOON, MACAT, VIOLATIONS, blog_of, guard_off, lock_ready, mutated, real_registry, rules_in, today_registry, with_lock_off)
from pipeline import publish_lock, registry

ROOT = _bootstrap.ROOT
WORKFLOWS = ROOT / ".github" / "workflows"
DOC = ROOT / "docs" / "PUBLISH_PATHS.md"
GUIDE = ROOT / "docs" / "ACTIONS_GUIDE.md"
GUARDRAILS = ROOT / "docs" / "SECURITY_GUARDRAILS.md"
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"
DEFECTS = ROOT / "docs" / "DEFECT_REGISTER.md"

# ----------------------------------------------------------------------------
# 워크플로 신호: 쓰기 권한·쓰기 명령·파이썬 진입점·쓰기 가능한 외부 액션
# ----------------------------------------------------------------------------
NOT_BEFORE = "(?<![A-Za-z0-9_-])"
NOT_AFTER = "(?![A-Za-z0-9_-])"
CMD_PATTERNS = (
    ("git push", NOT_BEFORE + "git push" + NOT_AFTER),
    ("git commit", NOT_BEFORE + "git commit" + NOT_AFTER),
    ("git tag", NOT_BEFORE + "git tag" + NOT_AFTER),
    ("gh pr merge", NOT_BEFORE + "gh pr merge" + NOT_AFTER),
    ("gh pr create", NOT_BEFORE + "gh pr create" + NOT_AFTER),
    ("gh pr comment", NOT_BEFORE + r"gh pr (?:comment|edit|review|close|reopen|ready)" + NOT_AFTER),
    ("gh issue", NOT_BEFORE + "gh issue" + NOT_AFTER),
    ("gh label", NOT_BEFORE + "gh label" + NOT_AFTER),
    ("gh workflow run", NOT_BEFORE + "gh workflow run" + NOT_AFTER),
    ("gh api write", NOT_BEFORE + r"gh api[^\n]*(?:-X|--method)\s*(?:POST|PUT|PATCH|DELETE)"),
    ("gh api -f/-F", NOT_BEFORE + r"gh api[^\n]*\s-[fF]\s"),
    ("curl write", NOT_BEFORE + r"curl[^\n]*(?:-X|--request)\s*(?:POST|PUT|PATCH|DELETE)"),
)
PY_RX = re.compile(r"python3?\s+(?:-u\s+)?(?:-m\s+([A-Za-z0-9_.]+)|([A-Za-z0-9_./-]+\.py))")
NEUTRAL_PY = {"pip", "unittest"}                                     # 쓰지 않는 도구
TRUSTED_USES = {"actions/checkout", "actions/setup-python"}          # 읽기 전용 준비 단계(체크아웃·파이썬 설치)


def strip_comments(text):
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def run_bodies_with_expressions(text):
    """워크플로의 run 본문 중 `${{ … }}` 식이 직접 들어 있는 것(주석 줄은 뺀다). 입력·외부 값은 env 로 받아야 한다 — 식이 셸 명령 줄에 그대로 박히면 입력 문자열이 명령이 된다(검증 지적 4①)."""
    found = []
    for step in all_steps(yaml.safe_load(text)):
        body = strip_comments(str(step.get("run", ""))).strip()
        if "${{" in body:
            found.append(body)
    return found


ESCAPES = ("|| true", "||true", "|| :", "set +e", "|| exit 0")


def escape_hatches(step):
    """단계 하나가 실패해도 지나가게 하는 모든 길: continue-on-error(거짓이 아닌 값), `|| true` 류, `set +e`(검증 지적 4②)."""
    found = []
    if step.get("continue-on-error") not in (None, False):
        found.append("continue-on-error")
    body = strip_comments(str(step.get("run", "")))
    found.extend(escape for escape in ESCAPES if escape in body)
    return found


def all_steps(data):
    for job in (data.get("jobs") or {}).values():
        if isinstance(job, dict):
            for step in job.get("steps") or []:
                if isinstance(step, dict):
                    yield step


def write_permissions(data):
    found = set()

    def add(block):
        if isinstance(block, dict):
            found.update(f"{name}:write" for name, level in block.items() if str(level).lower() == "write")
        elif isinstance(block, str) and block.lower() == "write-all":
            found.add("write-all")
    add(data.get("permissions"))
    for job in (data.get("jobs") or {}).values():
        if isinstance(job, dict):
            add(job.get("permissions"))
    return found


def signature(text):
    """워크플로 본문에서 검토 대상 신호를 뽑는다: 쓰기 권한, 쓰기 명령, 파이썬 진입점, 쓰기 가능성이 있는 `uses`(재사용 워크플로 호출 포함)."""
    data = yaml.safe_load(text)
    runs = "\n".join(strip_comments(str(step.get("run", ""))) for step in all_steps(data))
    uses = {str(step["uses"]).split("@")[0] for step in all_steps(data) if step.get("uses")}
    uses |= {str(job["uses"]) for job in (data.get("jobs") or {}).values() if isinstance(job, dict) and job.get("uses")}
    return {
        "perms": write_permissions(data),
        "cmds": {name for name, pattern in CMD_PATTERNS if re.search(pattern, runs)},
        "py": {(match.group(1) or match.group(2)) for match in PY_RX.finditer(runs)} - NEUTRAL_PY,
        "uses": uses - TRUSTED_USES,
    }


def write_counts(text):
    """워크플로의 쓰기 명령 종류별 개수(주석 뺀 run 본문에서 패턴이 맞은 횟수). 신호 집합이 같아도(이미 허용된 `git push` 단계를 하나 더 달아도) 개수가 달라지면 잡힌다."""
    data = yaml.safe_load(text)
    runs = "\n".join(strip_comments(str(step.get("run", ""))) for step in all_steps(data))
    return {name: len(re.findall(pattern, runs)) for name, pattern in CMD_PATTERNS if re.search(pattern, runs)}


def entry(perms=(), cmds=(), py=(), uses=()):
    return {"perms": set(perms), "cmds": set(cmds), "py": set(py), "uses": set(uses)}


RECORD_PUSH = entry({"contents:write"}, {"git commit", "git push"}, {"pipeline.plan", "pipeline.run"})
# 검토한 쓰기 길 전부. 워크플로 파일 이름 → 신호(정확히 같아야 한다). 이 표의 의미(공개 여부·잠금)는 docs/PUBLISH_PATHS.md §3.
ALLOWED = {
    "ai-request.yml": entry(py={"pipeline.operator_loop"}),
    "auto-pr.yml": entry({"pull-requests:write"}, {"gh api -f/-F", "gh api write"}),
    "blogger-en.yml": entry({"contents:write"}, uses={"./.github/workflows/blogger.yml"}),
    "blogger-ko.yml": entry({"contents:write"}, uses={"./.github/workflows/blogger.yml"}),
    "blogger.yml": RECORD_PUSH,
    "chance-fix-images.yml": entry({"actions:write", "contents:write"}, {"gh workflow run", "git commit", "git push"}, {"generator.py", "pipeline.publish_lock"}),
    "chance-shadow.yml": entry(py={"generator.py", "pipeline.quality_shadow", "pipeline.source_policy"}, uses={"actions/upload-artifact"}),      # source_policy: AF7 의 읽기 단계(레지스트리 값을 한 줄 출력 — 읽기만 한다)
    "chanceblog.yml": entry({"actions:write", "contents:write", "pull-requests:write"}, {"gh workflow run", "git commit", "git push"},
                            {"generator.py", "pipeline.draft_flow", "pipeline.notify", "pipeline.source_policy"}),      # source_policy: AF7 의 읽기 단계(읽기만 한다)
    "guardrails.yml": entry(py={"pipeline.notify", "scripts/validate_repo.py"}),
    "issue-edit.yml": entry({"actions:write", "contents:write", "issues:write", "pull-requests:write"},
                            {"gh issue", "gh label", "gh pr create", "gh workflow run", "git commit", "git push"}, {"pipeline.edits.runner"}),
    "naver.yml": entry({"contents:write", "issues:write"}, {"git commit", "git push"}, {"pipeline.plan", "pipeline.run"}),
    "operator-reply.yml": entry({"issues:write"}, py={"pipeline.operator_loop"}),
    "ops-inbox.yml": entry({"issues:write"}, py={"scripts/ops_inbox.py"}),
    "pages.yml": entry({"id-token:write", "pages:write"}, py={"scripts/verify_pages_deploy.py"},
                       uses={"actions/configure-pages", "actions/deploy-pages", "actions/jekyll-build-pages", "actions/upload-pages-artifact"}),
    "pr-scope-check.yml": entry({"pull-requests:write"}, {"gh pr comment"}, {"pipeline.edits.scope_check"}),
    "sync-issue-form.yml": entry({"contents:write"}, {"git commit", "git push"}, {"scripts/build_pages_registry.py", "scripts/sync_issue_form.py"}),
    "telegram-inbox.yml": entry({"issues:write"}, py={"pipeline.telegram_inbox"}),
    "telegram-test.yml": entry(py={"pipeline.notify"}),
    "tistory.yml": entry({"contents:write", "issues:write"}, {"git commit", "git push"}, {"pipeline.plan", "pipeline.run"}),
    "watchdog.yml": entry({"issues:write"}, py={"scripts/watchdog.py"}),
}
# 워크플로별 쓰기 명령 개수(검토한 값). 같은 종류의 명령을 하나 더 달면(예: 쓰기가 허용된 워크플로에 `git push` 단계 추가) 이 표와 docs/PUBLISH_PATHS.md 를 함께 고치지 않는 한 빨강이다.
COUNTS = {
    "ai-request.yml": {},
    "auto-pr.yml": {"gh api write": 1, "gh api -f/-F": 1},
    "blogger-en.yml": {},
    "blogger-ko.yml": {},
    "blogger.yml": {"git push": 1, "git commit": 1},
    "chance-fix-images.yml": {"git push": 1, "git commit": 1, "gh workflow run": 1},
    "chance-shadow.yml": {},
    "chanceblog.yml": {"git push": 1, "git commit": 1, "gh workflow run": 1},
    "guardrails.yml": {},
    "issue-edit.yml": {"git push": 1, "git commit": 1, "gh pr create": 1, "gh issue": 2, "gh label": 4, "gh workflow run": 1},
    "naver.yml": {"git push": 1, "git commit": 1},
    "operator-reply.yml": {},
    "ops-inbox.yml": {},
    "pages.yml": {},
    "pr-scope-check.yml": {"gh pr comment": 1},
    "sync-issue-form.yml": {"git push": 1, "git commit": 1},
    "telegram-inbox.yml": {},
    "telegram-test.yml": {},
    "tistory.yml": {"git push": 1, "git commit": 1},
    "watchdog.yml": {},
}
# 사람 승인 없이 공개 화면을 바꿀 수 있는 길(P1–P4)과 그 길을 막는 시험(tests/test_publish_lock.py 의 시험 묶음 이름)
PUBLIC_PATHS = {
    "P1": ("chanceblog.yml", ("DirectPushNeverRunsUnderTheLockTest", "ChanceFlowLockTest", "GeneratorMainTest")),
    "P2": ("chance-fix-images.yml", ("DirectPushNeverRunsUnderTheLockTest", "GuardFixImagesTest")),
    "P3": ("blogger.yml", ("BloggerLockTest", "GuardRegistryRuleTest")),
    "P4": ("blogger-en.yml", ("BloggerLockTest",)),
}
# main 에 글(공개 파일)을 올릴 수 있는 워크플로 = 'git add -A' 로 전체를 커밋하는 둘. 그 밖의 main 쓰기는 기록 파일(공개되지 않는 경로)만 커밋한다.
MAIN_PUBLISHERS = {"chanceblog.yml", "chance-fix-images.yml"}
EXPECTED_CONTENTS_WRITERS = {"blogger-en.yml", "blogger-ko.yml", "blogger.yml", "chance-fix-images.yml", "chanceblog.yml", "issue-edit.yml", "naver.yml",
                             "sync-issue-form.yml", "tistory.yml"}


def workflow_names():
    return sorted(path.name for path in WORKFLOWS.glob("*.yml"))


def read(name):
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def difference(found, wanted):
    """신호 하나씩 '새로 생긴 것'과 '사라진 것'."""
    return {key: (sorted(found[key] - wanted[key]), sorted(wanted[key] - found[key])) for key in wanted if found[key] != wanted[key]}


# ----------------------------------------------------------------------------
# Jekyll 이 공개하는 경로인가(_config.yml 의 exclude 와 밑줄·점 규칙)
# ----------------------------------------------------------------------------
def config_exclude():
    config = yaml.safe_load((ROOT / "_config.yml").read_text(encoding="utf-8"))
    return [str(item) for item in config.get("exclude", [])]


def jekyll_serves(rel, exclude):
    """저장소 상대 경로가 사이트에 공개 파일이 되는가. `_posts/` 는 글로 공개된다. 그 밖에 점(.)이나 밑줄(_)로 시작하는 구간이 있으면 Jekyll 이 처리하지 않고,
    `exclude` 항목과 같은 파일·그 폴더 아래는 뺀다(이름이 항목으로 시작하는 것도 뺀다는 Jekyll 3.10 동작은 일부러 빼고 '정확히 같은 이름·폴더'만 본다 — 공개로 잘못 판정하는 쪽이 안전하다)."""
    parts = rel.split("/")
    if parts[0] == "_posts":
        return True
    if any(part.startswith((".", "_")) for part in parts):
        return False
    return not any(rel == item.rstrip("/") or rel.startswith(item.rstrip("/") + "/") for item in exclude)


class SignatureTest(unittest.TestCase):
    """신호를 뽑는 도구 자체: 합성한 워크플로로 새 쓰기 길을 실제로 알아보는지."""

    BASE = ("name: x\non: workflow_dispatch\npermissions:\n  contents: read\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: actions/checkout@v6\n      - run: python generator.py\n")

    def test_a_read_only_workflow_has_no_signal(self):
        self.assertEqual(signature(self.BASE), entry(py={"generator.py"}))

    def test_each_kind_of_new_write_path_is_noticed(self):
        cases = {
            "git push": ("      - run: git push origin HEAD:main\n", "cmds", "git push"),
            "git commit": ("      - run: git commit -m x\n", "cmds", "git commit"),
            "gh pr merge": ("      - run: gh pr merge 3 --squash\n", "cmds", "gh pr merge"),
            "gh pr create": ("      - run: gh pr create --fill\n", "cmds", "gh pr create"),
            "gh api POST": ("      - run: gh api -X POST repos/o/r/issues\n", "cmds", "gh api write"),
            "gh api 필드": ("      - run: gh api repos/o/r/pulls -f title=x\n", "cmds", "gh api -f/-F"),
            "gh workflow run": ("      - run: gh workflow run pages.yml\n", "cmds", "gh workflow run"),
            "curl POST": ("      - run: curl -X POST https://example.invalid\n", "cmds", "curl write"),
            "새 파이썬 진입점": ("      - run: python -m pipeline.publish_now\n", "py", "pipeline.publish_now"),
            "새 파이썬 스크립트": ("      - run: python3 -u scripts/ship.py --go\n", "py", "scripts/ship.py"),
            "쓰기 액션": ("      - uses: peter-evans/create-pull-request@v7\n", "uses", "peter-evans/create-pull-request"),
        }
        for label, (step, kind, value) in cases.items():
            with self.subTest(label):
                self.assertIn(value, signature(self.BASE + step)[kind])
                self.assertNotEqual(signature(self.BASE + step), signature(self.BASE))

    def test_the_count_notices_a_second_command_of_a_kind_that_is_already_allowed(self):
        one = self.BASE + "      - run: git push\n"
        two = one + "      - run: git push origin HEAD:main\n"
        self.assertEqual(signature(one)["cmds"], signature(two)["cmds"])                 # 신호 집합은 같다(예전 시험이 놓치던 모양)
        self.assertEqual(write_counts(one), {"git push": 1})
        self.assertEqual(write_counts(two), {"git push": 2})
        self.assertEqual(write_counts(self.BASE), {})
        self.assertEqual(write_counts(self.BASE + "      - run: |\n          # git push origin main\n          echo 이름\n"), {})     # 주석은 세지 않는다

    def test_write_permissions_are_noticed_at_workflow_and_job_level(self):
        top = self.BASE.replace("contents: read", "contents: write")
        self.assertEqual(signature(top)["perms"], {"contents:write"})
        job = self.BASE.replace("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    permissions:\n      pull-requests: write\n      issues: write\n")
        self.assertEqual(signature(job)["perms"], {"pull-requests:write", "issues:write"})
        self.assertEqual(signature(self.BASE.replace("contents: read", "write-all"))["perms"], {"write-all"})
        self.assertEqual(signature(self.BASE)["perms"], set())

    def test_commented_out_commands_do_not_count_and_pip_is_ignored(self):
        text = self.BASE + "      - run: |\n          # git push origin main\n          python -m pip install x\n          python -m unittest\n"
        self.assertEqual(signature(text), entry(py={"generator.py"}))

    def test_a_reusable_workflow_call_is_noticed(self):
        text = "name: x\non: workflow_dispatch\npermissions:\n  contents: read\njobs:\n  call:\n    uses: ./.github/workflows/blogger.yml\n"
        self.assertEqual(signature(text)["uses"], {"./.github/workflows/blogger.yml"})

    def test_an_expression_inside_a_run_body_is_noticed_and_one_in_env_is_not(self):
        bad = self.BASE + '      - run: echo "${{ inputs.as_of }}"\n'
        good = self.BASE + "      - env:\n          AS_OF: ${{ inputs.as_of }}\n        run: echo \"$AS_OF\"\n"
        self.assertEqual(run_bodies_with_expressions(bad), ['echo "${{ inputs.as_of }}"'])
        self.assertEqual(run_bodies_with_expressions(good), [])
        self.assertEqual(run_bodies_with_expressions(self.BASE + "      - run: echo x # ${{ inputs.a }}\n"), [])             # 줄 끝 주석은 YAML 이 뗀다 — 식으로 세지 않는다

    def test_the_escape_hatch_finder_sees_every_way_to_let_a_failing_step_pass(self):
        base = {"run": "set -euo pipefail\nflow=$(python -m pipeline.draft_flow flow)\n"}
        self.assertEqual(escape_hatches(base), [])
        self.assertEqual(escape_hatches({**base, "continue-on-error": True}), ["continue-on-error"])
        self.assertEqual(escape_hatches({**base, "continue-on-error": "${{ always() }}"}), ["continue-on-error"])
        for text in ("flow=$(python -m pipeline.draft_flow flow) || true\n", "python x ||true\n", "python x || :\n", "set +e\npython x\n", "python x || exit 0\n"):
            self.assertEqual(len(escape_hatches({"run": text})), 1, text)
        self.assertEqual(escape_hatches({**base, "continue-on-error": False}), [])

    def test_the_difference_helper_reports_added_and_removed(self):
        found = entry({"contents:write"}, {"git push"})
        wanted = entry({"contents:write"}, {"git commit"})
        self.assertEqual(difference(found, wanted), {"cmds": (["git push"], ["git commit"])})


class EveryWriteSignalIsReviewedTest(unittest.TestCase):
    """새 워크플로가 생기거나, 기존 워크플로에 쓰기 권한·명령·진입점이 더해지면 빨강이다."""

    def test_the_reviewed_table_and_the_real_workflow_files_are_the_same_set(self):
        self.assertEqual(workflow_names(), sorted(ALLOWED), "새 워크플로가 있으면 docs/PUBLISH_PATHS.md 와 이 시험의 ALLOWED 표에 먼저 올리세요(쓰기 길 검토)")

    def test_no_workflow_has_a_write_signal_the_table_does_not_know(self):
        for name in workflow_names():
            with self.subTest(workflow=name):
                found = signature(read(name))
                self.assertEqual(found, ALLOWED[name], f"{name}: 검토하지 않은 쓰기 길이 생겼거나 사라졌습니다 {difference(found, ALLOWED[name])} — "
                                                      "docs/PUBLISH_PATHS.md §3 과 이 시험의 ALLOWED 를 같은 변경에서 고치세요")

    def test_the_number_of_write_commands_of_every_workflow_is_pinned_too(self):
        """검증 지적 4③: 이미 쓰기가 허용된 워크플로에 `git push` 단계를 하나 더 달아도 신호 집합은 같다 — 명령 개수까지 못박는다."""
        self.assertEqual(sorted(COUNTS), sorted(ALLOWED))
        for name in workflow_names():
            with self.subTest(workflow=name):
                self.assertEqual(write_counts(read(name)), COUNTS[name], f"{name}: 쓰기 명령 개수가 달라졌습니다 — 검토한 뒤 이 시험의 COUNTS 와 docs/PUBLISH_PATHS.md 를 같은 변경에서 고치세요")
                self.assertEqual(set(COUNTS[name]), ALLOWED[name]["cmds"], name)          # 개수 표와 신호 표가 같은 종류를 말한다

    def test_gh_pr_merge_exists_nowhere(self):
        """사람의 병합이 곧 승인이다 — 워크플로 어디도 PR 을 병합하지 않는다(자동 병합 길이 없다)."""
        for name in workflow_names():
            self.assertNotIn("gh pr merge", signature(read(name))["cmds"], name)
            self.assertNotIn("--auto", " ".join(re.findall(NOT_BEFORE + r"gh pr [^\n]*", strip_comments(read(name)))), name)

    def test_the_workflows_that_may_write_to_the_repository_are_exactly_the_known_nine(self):
        writers = {name for name in workflow_names() if "contents:write" in signature(read(name))["perms"]}
        self.assertEqual(writers, EXPECTED_CONTENTS_WRITERS)
        pushers = {name for name in workflow_names() if "git push" in signature(read(name))["cmds"]}
        self.assertEqual(pushers, EXPECTED_CONTENTS_WRITERS - {"blogger-en.yml", "blogger-ko.yml"})       # 래퍼 둘은 공용 blogger.yml 이 push 한다

    def test_no_workflow_has_write_all_or_pull_request_target(self):
        for name in workflow_names():
            data = yaml.safe_load(read(name))
            self.assertNotIn("write-all", signature(read(name))["perms"], name)
            triggers = data.get("on") if "on" in data else data.get(True)
            self.assertNotIn("pull_request_target", triggers if isinstance(triggers, dict) else {}, name)

    def test_only_two_workflows_commit_the_whole_working_tree_which_is_the_only_way_to_publish_a_post_from_a_workflow(self):
        everything = {name for name in workflow_names() if re.search(NOT_BEFORE + r"git add -A" + NOT_AFTER, strip_comments(read(name)))}
        self.assertEqual(everything, MAIN_PUBLISHERS)

    def test_the_other_main_writers_add_only_named_record_files(self):
        for name in sorted(EXPECTED_CONTENTS_WRITERS - MAIN_PUBLISHERS - {"issue-edit.yml", "blogger-en.yml", "blogger-ko.yml"}):
            adds = re.findall(NOT_BEFORE + r"git add[^\n]*", strip_comments(read(name)))
            self.assertTrue(adds, name)
            for line in adds:
                self.assertNotIn("-A", line.split(), name)
                self.assertNotIn(".", line.split()[2:], name)
        text = strip_comments(read("sync-issue-form.yml"))
        self.assertIn("git add -- pages.json .github/ISSUE_TEMPLATE/page-edit.yml", text)
        for name in ("blogger.yml", "naver.yml", "tistory.yml"):
            body = strip_comments(read(name))
            self.assertIn('for p in "$HISTORY_FILE" "$CONTENT_DIR"; do', body, name)
            self.assertIn('git add -- "$p"', body, name)
            data = yaml.safe_load(read(name))
            commit = next(step for step in all_steps(data) if "git add" in str(step.get("run", "")))
            self.assertEqual(commit["env"]["HISTORY_FILE"], "${{ matrix.history }}", name)
            self.assertEqual(commit["env"]["CONTENT_DIR"], "${{ matrix.content_dir }}", name)


class RunBodiesAreInjectionSafeTest(unittest.TestCase):
    """검증 지적 4①: 입력(`inputs.*`)·외부 값을 `run:` 본문에 `${{ … }}` 로 직접 넣으면 입력 문자열이 셸 명령이 된다 — 두 잠금 워크플로는 값을 env 로만 받는다."""

    def test_no_run_body_of_the_shadow_and_image_fix_workflows_holds_an_expression(self):
        for name in ("chance-shadow.yml", "chance-fix-images.yml"):
            with self.subTest(workflow=name):
                self.assertEqual(run_bodies_with_expressions(read(name)), [], f"{name}: run 본문에 ${{{{ }}}} 식이 있습니다 — 값은 env 로 받으세요")

    def test_the_shadow_inputs_reach_the_shell_only_through_env(self):
        data = yaml.safe_load(read("chance-shadow.yml"))
        carried = {}
        for step in all_steps(data):
            for key, value in (step.get("env") or {}).items():
                if "inputs." in str(value):
                    carried[key] = str(value)
        self.assertEqual(carried, {"SHADOW_COUNT": "${{ inputs.count }}", "AS_OF": "${{ inputs.as_of }}"})


class FlowStepCannotBeBypassedTest(unittest.TestCase):
    """검증 지적 4②: chanceblog.yml 의 '발행 흐름 확인' 단계(id flow)가 실패해도 뒤 단계가 돌게 만드는 길이 없다(`continue-on-error`·`|| true`·`set +e`) — 잠금 아래 직접 커밋 단계가 안 도는 근거다."""

    def setUp(self):
        self.data = yaml.safe_load(read("chanceblog.yml"))
        self.steps = list(all_steps(self.data))
        self.flow = next(step for step in self.steps if step.get("id") == "flow")

    def test_the_flow_step_has_no_escape_hatch_and_is_never_skipped(self):
        self.assertEqual(escape_hatches(self.flow), [])
        self.assertNotIn("if", self.flow)
        self.assertIn("pipeline.draft_flow flow", self.flow["run"])

    def test_no_step_except_the_last_notification_can_let_a_failure_pass(self):
        """chanceblog.yml 의 '텔레그램 알림(새 글)' 단계만 일부러 continue-on-error 다(알림이 실패해도 글 게시 실행을 실패시키지 않는다) — 맨 마지막 단계라 뒤에 돌 단계가 없다."""
        for name, allowed in (("chanceblog.yml", {"텔레그램 알림(새 글)"}), ("chance-fix-images.yml", set())):
            data = yaml.safe_load(read(name))
            for job in data["jobs"].values():
                self.assertNotIn("continue-on-error", job, name)
                steps = job["steps"]
                for index, step in enumerate(steps):
                    label = step.get("name") or step.get("uses")
                    if label in allowed:
                        self.assertEqual(index, len(steps) - 1, label)
                        continue
                    self.assertEqual(escape_hatches(step), [], (name, label))


class RecordFilesAreNotPublicTest(unittest.TestCase):
    """main 에 기록을 직접 커밋하는 길이 공개 화면을 바꾸지 않는다는 증거: 커밋하는 파일이 Jekyll 공개 경로가 아니다(공개 글은 _posts 뿐이다)."""

    def test_the_predicate_itself(self):
        exclude = config_exclude()
        for rel, expected in (("_posts/2026/a.md", True), ("about.md", True), ("index.html", True), ("assets/a.png", True), ("posts.json", True),
                              ("history.json", False), ("pages.json", False), ("blogger_history.json", False), (".github/ISSUE_TEMPLATE/x.yml", False),
                              ("_blogger_drafts/a.md", False), ("docs/x.md", False), ("pipeline/blogs.json", False), ("generator.py", False)):
            with self.subTest(rel):
                self.assertEqual(jekyll_serves(rel, exclude), expected)
        self.assertTrue(jekyll_serves("history.json", []))                  # exclude 가 없으면 공개된다 — 판정이 exclude 에 실제로 기대고 있다
        self.assertFalse(jekyll_serves("x/history.json", ["x"]))

    def test_every_record_and_draft_path_the_workflows_commit_stays_off_the_site(self):
        exclude = config_exclude()
        reg = real_registry()
        for raw in reg["blogs"]:
            state = raw["state"]
            if raw["key"] == CHANCE:
                self.assertFalse(jekyll_serves(state["history"], exclude), state["history"])           # 승인 흐름이 main 에 따로 커밋하는 이력
                self.assertTrue(jekyll_serves(state["content_dir"] + "/2026/a.md", exclude))             # 글 폴더는 공개다(이 경로가 곧 공개 경로)
                continue
            for field in ("history", "content_dir"):
                probe = state[field] + ("/x.md" if field == "content_dir" else "")
                self.assertFalse(jekyll_serves(probe, exclude), (raw["key"], probe))
        for rel in ("pages.json", ".github/ISSUE_TEMPLATE/page-edit.yml"):                              # sync-issue-form.yml 이 main 에 커밋하는 두 파일
            self.assertFalse(jekyll_serves(rel, exclude), rel)

    def test_the_draft_flow_commits_the_history_file_to_main_and_that_file_is_not_public(self):
        from pipeline import draft_flow
        self.assertEqual(draft_flow.HISTORY_PATH, "history.json")
        self.assertFalse(jekyll_serves(draft_flow.HISTORY_PATH, config_exclude()))


class PublishedDocumentTest(unittest.TestCase):
    TEXT = DOC.read_text(encoding="utf-8") if DOC.is_file() else ""

    def test_the_document_exists_and_has_no_tilde(self):
        self.assertTrue(DOC.is_file(), "docs/PUBLISH_PATHS.md 가 없습니다")
        self.assertNotIn("~", self.TEXT)                                    # 마크다운 취소선으로 읽힌다 — 범위는 – 로 쓴다
        self.assertNotIn("{{", self.TEXT)                                   # front matter 없는 문서의 이중 중괄호는 Liquid 출력 구문으로 읽힌다(validate_repo LIQUID-1 경고)

    def test_every_workflow_is_listed_with_its_file_name(self):
        for name in workflow_names():
            self.assertIn(f"`{name}`", self.TEXT, f"{name} 이 docs/PUBLISH_PATHS.md 에 없습니다")

    def test_every_public_path_and_rule_is_listed(self):
        for path_id in ("P1", "P2", "P3", "P4", "P5", "P6"):
            self.assertIn(path_id, self.TEXT)
        for rule, _text in publish_lock.RULES + publish_lock.KEY_RULES:
            self.assertIn(rule, self.TEXT)

    def test_each_public_path_names_the_tests_that_lock_it(self):
        for path_id, (workflow, proofs) in PUBLIC_PATHS.items():
            self.assertIn(path_id, self.TEXT)
            for proof in proofs:
                self.assertTrue(hasattr(lock_tests, proof), f"{path_id}: 시험 묶음 {proof} 가 tests/test_publish_lock.py 에 없습니다")
                self.assertIn(proof, self.TEXT, f"{path_id}: 문서에 시험 묶음 {proof} 이름이 없습니다")
        self.assertEqual({workflow for workflow, _proofs in PUBLIC_PATHS.values()} - set(ALLOWED), set())

    def test_the_document_names_the_registry_values_that_turn_the_lock_on(self):
        for needle in ("resume_lock", "publish_flow", "max_posts_per_day", "max_open_drafts", "PIPELINE_PAUSE"):
            self.assertIn(needle, self.TEXT)

    def test_the_document_says_what_l0_covers_and_what_the_key_rules_cover(self):
        self.assertIn("L0 은 값 오타만 막는다", self.TEXT)
        self.assertNotIn("철자 실수로 잠금이 꺼지는 것", self.TEXT)                      # 예전 문구(키 이름 오타까지 막는다고 읽히던 것) — 정정했다
        for needle in ("`KNOWN_TOP_LEVEL_KEYS`", "resume_lock 오타로 보입니다", "최상위에만"):
            self.assertIn(needle, self.TEXT, needle)

    def test_the_document_gives_the_merge_order_the_shadow_order_and_the_signpost_rule(self):
        for needle in ("실제 병합 순서는 계획과 달라졌다", "켜는 변경은 GATE 병합 뒤에만", "정지 검사 → 그림자 분기(GATE 묶음, `SHADOW_RUN`) → 잠금 가드", "표지판 시험은 고치되 지우지 않는다",
                       "`resume_lock is True`", "`reg == lock_ready()`", "pipeline/shadow_run.py", "GATE 가 먼저 병합된 뒤에만 참이다"):
            self.assertIn(needle, self.TEXT, needle)
        self.assertNotIn("GATE → LOCK → SHADOW → R2 → SRC → FACT", self.TEXT)      # 처음 계획의 순서다 — 실제로는 잠금(M034)이 GATE 보다 먼저 병합됐다(독립 재검증 D8). 옛 문장이 되살아나면 빨강

    def test_the_document_lists_the_shadow_run_values_once_and_they_are_the_code_constants(self):
        for value in publish_lock.SHADOW_ON_VALUES + tuple(item for item in publish_lock.SHADOW_OFF_VALUES if item):
            self.assertIn(f"`{value}`", self.TEXT, value)
        self.assertEqual(self.TEXT.count("켜짐 `1`·`true`·`yes`·`on`·`enabled`"), 1)                  # 값 집합 목록은 이 문서에 한 곳뿐이다

    def test_the_document_lists_what_the_limits_section_must_say(self):
        limits = self.TEXT[self.TEXT.index("## 7. 한계와 남은 위험"):self.TEXT.index("## 8. 설계 결정")]
        for needle in ("원격 초안 목록을 못 읽으면 조용히 건너뛴다", "36시간", "7일간 열린 것으로 센다", "한국어·영어 한 쌍", "L6 은 GATE 의 `languages` 검증과 판정이 다르다"):
            self.assertIn(needle, limits, needle)

    def test_the_manual_run_wording_that_turns_wrong_after_the_flip_is_listed_in_section_9(self):
        section = self.TEXT[self.TEXT.index("## 9. 켜는 변경이 일부러 깨뜨리는 시험 고정값"):]
        self.assertIn("(수동 게시는 게시 시각·하루 상한을 따지지 않습니다)", section)
        self.assertIn("chanceblog.yml", section)

    def test_the_document_lists_the_workflow_that_stays_read_only(self):
        self.assertIn("chance-shadow.yml", self.TEXT)
        self.assertIn("contents: read", self.TEXT)

    def test_the_precondition_to_turn_the_lock_on_is_one_line_in_section_6(self):
        """독립 재검증 D6: 잠금만 병합한 채 켜면 가드의 그림자 값 예외가 하루 상한을 건너뛴다 — '켜기 전 조건: Gate 병합 뒤에만 켠다' 가 켜는 방법(§6)에 한 줄로 있다."""
        section = self.TEXT[self.TEXT.index("## 6. 켜는 방법"):self.TEXT.index("## 7. 한계와 남은 위험")]
        self.assertEqual(section.count("**켜기 전 조건: Gate 병합 뒤에만 켠다**"), 1)
        line = next(item for item in section.splitlines() if "켜기 전 조건" in item)
        for needle in ("pipeline/shadow_run.py", "SHADOW_RUN", "독립 재검증 D6"):
            self.assertIn(needle, line, needle)

    def test_the_twelve_tests_of_the_other_branches_that_break_once_the_lock_is_on_are_listed_with_the_fix(self):
        """독립 재검증 D7: 아직 main 에 없는 SRC 와 GATE 의 새 시험 12개가 켠 합성에서 깨진다 — 켜는 변경이 같은 변경에서 `guard_off()` 로 고치도록 목록과 방법을 문서에 둔다."""
        section = self.TEXT[self.TEXT.index("## 9. 켜는 변경이 일부러 깨뜨리는 시험 고정값"):]
        for needle in ("| SRC | `tests/test_generator_source_policy.py` | `AllowlistNoCallTest`(6)·`AllowlistFetchTest`(1)·`LegacyByteTest` 의 하위 시험(4) | 11 |",
                       "| GATE | `tests/test_shadow_run.py` | `DefaultUnchangedTest.test_a_normal_scheduled_run_writes_the_post_as_before_and_never_touches_the_shadow_path` | 1 |",
                       "`setUpModule()`", "`tearDownModule()`", "`guard_off()`", "전체 시험을 먼저 돌려 본다"):
            self.assertIn(needle, section, needle)
        self.assertTrue(callable(guard_off))                              # 문서가 권하는 도구가 실제로 있다

    def test_the_key_rules_say_how_deep_how_close_and_how_many_and_the_numbers_are_the_code_constants(self):
        """독립 재검증 D1·D2·D4: K2 는 어느 깊이든(상한 16), K1 의 '오타로 보임' 은 편집 거리 2 이내, 출력은 앞 20개 — 문서의 숫자가 코드 상수와 같다."""
        rows = {line.split("|")[1].strip(): line for line in self.TEXT.splitlines() if line.startswith("| **K")}
        self.assertEqual(sorted(rows), ["**K1**", "**K2**"])
        self.assertIn("편집 거리 %d 이내" % publish_lock.LOCK_KEY_EDITS, rows["**K1**"])
        for needle in ("`resumelock`", "알 수 없는 최상위 키", "`block`", "`resume_after`", "독립 재검증 D2", "전각·호환 글자를 보통 글자로 풀고"):
            self.assertIn(needle, rows["**K1**"], needle)
        for needle in ("**어느 깊이든**", "반복문", "`MAX_KEY_SCAN_DEPTH`(%d" % publish_lock.MAX_KEY_SCAN_DEPTH, "너무 깊다", "`chance.limits`", "독립 재검증 D1"):
            self.assertIn(needle, rows["**K2**"], needle)
        self.assertIn("`MAX_KEY_MESSAGES`(%d)" % publish_lock.MAX_KEY_MESSAGES, self.TEXT)
        self.assertIn("독립 재검증 D4", self.TEXT)
        for stale in ("`resume`·`lock` 이 들어 있으면", "줄인 이름에 `resume` 이 든 키", "영문 철자에 `resume`·`lock` 이 든"):
            self.assertNotIn(stale, self.TEXT, stale)                      # 예전의 넓은 판정·한 단계 깊이 문구(D1·D2)

    def test_the_overview_and_the_limits_say_what_the_key_check_catches_and_what_only_the_ci_catches(self):
        """독립 재검증 D3: '켠 줄 알았는데 꺼져 있는 일이 없다' 는 약속에는 범위 단서가 붙는다 — 쉬운 설명·§1 끝·§7-16 이 같은 말을 한다."""
        easy = self.TEXT[self.TEXT.index("## 쉬운 설명"):self.TEXT.index("## 1. 한눈에 보기")]
        self.assertIn("더 깊은 곳", easy)
        self.assertIn("이름이 전혀 다른 모르는 줄은 병합 전 검사만 거절합니다", easy)
        overview = self.TEXT[self.TEXT.index("## 1. 한눈에 보기"):self.TEXT.index("## 2. 정의와 판정 기준")]
        for needle in ("잠금 키 검사가 잡는 범위", "`rsmlck`", "병합 전 검사(검증기 REG-1)만 거절하고 실행 시에는 막지 않는다", "표지판 시험(§9)"):
            self.assertIn(needle, overview, needle)
        limits = self.TEXT[self.TEXT.index("## 7. 한계와 남은 위험"):self.TEXT.index("## 8. 설계 결정")]
        item = limits[limits.index("16. **실행 시 멈춤은 오타로 '보이는' 키만 본다**"):]
        for needle in ("`resumelock` 을 품거나 `resumelock` 과 편집 거리 2 이내인 최상위 키(K1)", "최상위 밖 어느 깊이(상한 16)", "`check` 의 `꺼짐` 표시"):
            self.assertIn(needle, item, needle)

    def test_the_decision_rows_for_the_deep_scan_the_narrow_typo_shape_and_the_output_cap_exist(self):
        decisions = self.TEXT[self.TEXT.index("## 8. 설계 결정"):self.TEXT.index("## 9. 켜는 변경이 일부러 깨뜨리는 시험 고정값")]
        ids = re.findall(r"(?m)^\| (L-\d+) \|", decisions)
        self.assertEqual(ids, ["L-%d" % number for number in range(1, len(ids) + 1)])  # 번호가 이어지고 겹치지 않는다
        self.assertGreaterEqual(len(ids), 19)                                           # L-19(주간 상한)까지 있다 — 뒤에 결정이 더해져도 깨지지 않는다
        for needle in ("독립 재검증 D1", "(D2)", "(D4)"):
            self.assertIn(needle, decisions, needle)


class OperatorGuideTest(unittest.TestCase):
    """운영자 설명서(docs/ACTIONS_GUIDE.md)가 코드와 어긋난 말을 하지 않는다(검증 지적 5)."""

    TEXT = GUIDE.read_text(encoding="utf-8")
    SECTION = TEXT[TEXT.index("### 3-22. 제한 재개 잠금"):TEXT.index("## 4. 점검 루틴과 키 교체")]

    def test_the_cap_skip_note_is_described_as_the_notice_line_of_the_run_summary_not_a_yellow_one(self):
        self.assertNotIn("노란 안내", self.SECTION)
        self.assertIn("실행 요약의 안내 줄", self.SECTION)
        self.assertIn("::notice::", Path(_bootstrap.ROOT, "pipeline", "publish_lock.py").read_text(encoding="utf-8"))      # 코드가 실제로 내는 것은 notice 다

    def test_the_shadow_claims_are_tied_to_the_merge_order_in_the_easy_explanation_too(self):
        self.assertIn("그림자 실행 코드가 먼저 병합된 뒤의 이야기입니다", self.SECTION)
        part = self.TEXT[self.TEXT.index("### 6-19."):self.TEXT.index("## 7. 알려진 한계와 예정")]
        for needle in ("pipeline/shadow_run.py", "실제 병합 순서는 계획과 달랐습니다", "GATE 병합 뒤에만 합니다", "docs/QUALITY_GATE.md"):
            self.assertIn(needle, part, needle)
        self.assertNotIn("GATE → LOCK → SHADOW", self.TEXT)              # 처음 계획의 순서 표기(독립 재검증 D8)

    def test_the_key_typo_rules_and_the_dry_run_exception_are_explained(self):
        for needle in ("resume_lok", "K1·K2", "L0 은 값 오타만 막고", "연습 실행은 저장하지 않아 그대로"):
            self.assertIn(needle, self.SECTION, needle)

    def test_the_easy_explanation_says_how_deep_and_how_close_and_when_to_turn_it_on(self):
        for needle in ("그 안의 `limits` 같은 더 깊은 곳도 같습니다", "글자 한두 개만 다른 줄", "`block` 처럼 전혀 다른 모르는 줄은 글 만들기를 멈추지는 않고", "'알 수 없는 최상위 키'",
                       "그림자 실행 코드(GATE 묶음)가 먼저 병합된 뒤에만 켭니다", "병합 전 검사만 거절합니다"):
            self.assertIn(needle, self.SECTION, needle)
        self.assertNotIn("오타로 보이는 줄이 있으면", self.SECTION)             # 예전의 넓은 판정 문구


class SecurityListAndRegisterTest(unittest.TestCase):
    """독립 재검증 D3·D8: T3 목록이 키 규칙·허용 목록·값 집합 변경을 T3 로 적고, 아키텍처 표가 실제 병합 순서를 말하며, 결함 표에 이번 후속의 행이 있다."""

    GUARDRAILS_TEXT = GUARDRAILS.read_text(encoding="utf-8")
    ARCH_TEXT = ARCHITECTURE.read_text(encoding="utf-8")
    DEFECT_TEXT = DEFECTS.read_text(encoding="utf-8")

    def test_the_t3_list_names_the_key_rules_the_allow_list_and_the_shadow_value_sets(self):
        line = next(item for item in self.GUARDRAILS_TEXT.splitlines() if item.startswith("- 제한 재개 잠금(레지스트리 `resume_lock`)을 끄거나"))
        names = ("RULES", "KEY_RULES", "KNOWN_TOP_LEVEL_KEYS", "SHADOW_ON_VALUES", "SHADOW_OFF_VALUES", "LOCK_KEY_EDITS", "MAX_KEY_SCAN_DEPTH")
        for name in names:
            self.assertIn("`%s`" % name if name not in ("RULES", "KEY_RULES") else "`publish_lock.%s`" % name, line, name)
            self.assertTrue(hasattr(publish_lock, name), "T3 목록이 코드에 없는 이름 %s 를 가리킨다" % name)
        self.assertIn("(G-C14)", line)

    def test_the_guardrail_row_says_how_deep_and_that_turning_it_on_waits_for_the_shadow_code(self):
        row = next(item for item in self.GUARDRAILS_TEXT.splitlines() if item.startswith("| G-C14 |"))
        for needle in ("최상위 밖 어느 깊이든", "`resumelock` 과 편집 거리 2 이내", "켜는 것(그림자 실행 코드 GATE 가 병합된 뒤에만)"):
            self.assertIn(needle, row, needle)

    def test_the_architecture_doc_says_how_deep_and_does_not_claim_the_old_merge_order(self):
        for needle in ("최상위 밖(어느 깊이든)의 위치 오류는 K1·K2", "최상위 밖 어느 깊이든 — `defaults`·블로그 항목과 그 안의 `limits` 등, 깊이 상한 16", "K2 — 최상위 밖 어느 깊이든 검사",
                       "켜는 변경은 GATE 병합 뒤에만 한다"):
            self.assertIn(needle, self.ARCH_TEXT, needle)
        self.assertNotIn("병합 순서(GATE 먼저)", self.ARCH_TEXT)

    def test_the_follow_up_rows_d160_to_d165_exist_once_each_with_six_cells(self):
        ids = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", self.DEFECT_TEXT)
        self.assertEqual(len(ids), len(set(ids)))
        needles = {160: ("D1", "K2", "깊이 상한 16"), 161: ("D2", "편집 거리 2"), 162: ("D4", "MAX_KEY_MESSAGES"), 163: ("W05", "W08·W09"), 164: ("D3·D8", "KEY_RULES"), 165: ("D6·D7", "flip.patch")}
        for number, words in needles.items():
            row_id = "D-%d" % number
            self.assertEqual(ids.count(row_id), 1, row_id)
            row = next(line for line in self.DEFECT_TEXT.splitlines() if line.startswith("| **%s** |" % row_id))
            self.assertEqual(row.count("|"), 7, row_id)                                 # 표의 여섯 칸 — 칸 안에 세로선이 없다
            for word in words:
                self.assertIn(word, row, "%s: %s" % (row_id, word))


class WeeklyCapDocumentTest(unittest.TestCase):
    """주간 상한(규칙 L8)의 문서가 코드와 같은 말을 한다: 규칙 행·§4-4 설계 표·§6 켜는 값·§7 한계·§8 결정·T3 목록·운영자 설명서·아키텍처 표·결함 표.
    (코드와 동작은 tests/test_publish_lock_weekly.py. 문서에 적은 날짜·숫자·코드 이름이 실제 코드의 출력·상수와 같은지도 여기서 견준다.)"""

    TEXT = DOC.read_text(encoding="utf-8")
    GUIDE_TEXT = GUIDE.read_text(encoding="utf-8")
    GUIDE_SECTION = GUIDE_TEXT[GUIDE_TEXT.index("### 3-22. 제한 재개 잠금"):GUIDE_TEXT.index("## 4. 점검 루틴과 키 교체")]
    GUARDRAILS_TEXT = GUARDRAILS.read_text(encoding="utf-8")
    ARCH_TEXT = ARCHITECTURE.read_text(encoding="utf-8")
    DEFECT_TEXT = DEFECTS.read_text(encoding="utf-8")
    SECTION_4_4 = TEXT[TEXT.index("### 4-4. 주간 상한"):TEXT.index("## 5. 그림자 실행 워크플로")]
    SECTION_6 = TEXT[TEXT.index("## 6. 켜는 방법"):TEXT.index("## 7. 한계와 남은 위험")]
    SECTION_7 = TEXT[TEXT.index("## 7. 한계와 남은 위험"):TEXT.index("## 8. 설계 결정")]
    SECTION_8 = TEXT[TEXT.index("## 8. 설계 결정"):TEXT.index("## 9. 켜는 변경이 일부러 깨뜨리는 시험 고정값")]
    SECTION_9 = TEXT[TEXT.index("## 9. 켜는 변경이 일부러 깨뜨리는 시험 고정값"):]

    def row(self, text, start):
        return next(line for line in text.splitlines() if line.startswith(start))

    def test_the_rule_row_says_the_value_the_ceiling_the_shape_and_who_is_not_covered(self):
        row = self.row(self.TEXT, "| **L8** |")
        for needle in ("`chance.limits.max_posts_per_week`", "**있어야**", "`MAX_POSTS_PER_WEEK` = %d" % publish_lock.MAX_POSTS_PER_WEEK, "1 이상 2 이하", "불리언", "defaults.limits",
                       "Chance 밖의 블로그(Blogger·네이버 초안 패키지)에는 주간 상한을 강제하지 않는다", "하루 1편 상한(L7)이 그대로 있다", "§4-4", "확인 요청 007"):
            self.assertIn(needle, row, needle)
        self.assertEqual(row.count("|"), 4)                                                      # 세 칸 — 칸 안에 세로선이 없다
        self.assertEqual(publish_lock.MAX_POSTS_PER_WEEK, 2)

    def test_the_counting_table_has_a_row_for_every_design_choice(self):
        labels = ("세는 단위", "세는 것", "중복 제거 열쇠", "창 경계", "날짜(이력 항목)", "날짜를 믿을 수 없을 때", "사전이 아닌 항목", "이 흐름이 만들지 않는 브랜치 이름", "초안 목록을 모를 때", "닫은 초안",
                  "병합된 글", "수동 실행", "연습·그림자·이미지 교체 연습", "상한을 보는 순서", "상한값", "잠금이 꺼져 있을 때", "Chance 밖의 블로그")
        for label in labels:
            row = self.row(self.SECTION_4_4, "| %s |" % label)
            self.assertEqual(row.count("|"), 4, label)
        self.assertTrue(self.SECTION_4_4.startswith("### 4-4. 주간 상한 — 굴러가는 7일에 최대 2편 (규칙 L8"))

    def test_the_counting_table_names_the_key_the_window_and_the_stop_reasons_the_code_uses(self):
        for needle in ("초안 브랜치 이름", "`ai/draft/YYYY-MM-DD-sN`", "`ai/draft/YYYY-MM-DD-mHHMMSS`", "양끝 포함", "7일 전은 창 밖", "`flow=pr`", "읽을 수 있는 것만 세고 지나가지 않는다",
                       "`OPEN_DRAFTS_UNKNOWN`", "`LOCK_WEEKLY_CAP`", "하루 → (원격 목록을 못 읽으면 멈춤) → 열린 초안 → 주간"):
            self.assertIn(needle, self.SECTION_4_4, needle)
        source = Path(_bootstrap.ROOT, "pipeline", "publish_lock.py").read_text(encoding="utf-8")
        for reason in ("HISTORY_DATE_UNREADABLE", "HISTORY_DATE_FUTURE", "DRAFT_BRANCH_DATE_FUTURE"):
            self.assertIn("`%s`" % reason, self.SECTION_4_4, reason)
            self.assertIn('"%s"' % reason, source, "문서가 코드에 없는 이유 코드 %s 를 적었다" % reason)
        self.assertEqual(publish_lock.WEEK_WINDOW_DAYS, 7)
        self.assertIn("그 6일 전까지", self.SECTION_4_4)

    def test_the_example_lines_in_the_document_are_what_the_guard_prints(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        history = [lock_tests.entry(date="2026-11-03"), lock_tests.entry(date="2026-11-05")]
        result = lock_tests.GuardRun(folder, lock_ready(), history=history, remote=[], exists=lambda path: False)
        self.assertEqual(result.out[0], "[SKIP] code=LOCK_WEEKLY_CAP since=2026-11-03 until=2026-11-09 week=2 cap=2")
        self.assertIn("`LOCK_WEEKLY_CAP since=2026-11-03 until=2026-11-09 week=2 cap=2`", self.SECTION_4_4)
        both = lock_tests.GuardRun(folder, lock_ready(), history=[lock_tests.entry(date="2026-11-09"), lock_tests.entry(date="2026-11-07")], remote=[], exists=lambda path: False)
        self.assertEqual(both.out[0], "[SKIP] code=LOCK_DAILY_CAP date=2026-11-09 today=1 cap=1")
        self.assertIn("`LOCK_DAILY_CAP`(하루 상한이 먼저)", self.SECTION_4_4)
        edge = lock_tests.GuardRun(folder, lock_ready(), history=[lock_tests.entry(date="2026-11-02"), lock_tests.entry(date="2026-11-05")], remote=[], exists=lambda path: False)
        self.assertEqual((edge.code, edge.out), (None, []))                                      # 문서의 '11-02·11-05 글 2건 → 통과'
        bad = lock_tests.GuardRun(folder, lock_ready(), history=[lock_tests.entry(date="2026-11-9")], remote=[], exists=lambda path: False)
        self.assertEqual(bad.out[0], "[SKIP] code=LOCK_BLOCKED reason=HISTORY_DATE_UNREADABLE")

    def test_section_6_lists_every_limit_the_ready_registry_sets_with_the_same_value_and_counts_five_values(self):
        limits = blog_of(lock_ready(), CHANCE)["limits"]
        self.assertTrue({"max_open_drafts", "max_posts_per_day", "max_posts_per_week"} <= set(limits), sorted(limits))      # 이 묶음의 셋이 있다 — 아래 반복이 모든 한도의 행과 값을 문서와 견준다
        for key, value in limits.items():
            cells = [cell.strip() for cell in self.row(self.SECTION_6, "| `chance.limits.%s` |" % key).split("|")[1:-1]]
            self.assertEqual(cells[2], "`%d`" % value, key)                                       # '켤 때' 칸이 켠 레지스트리 값과 같다
        self.assertIn("**다섯 값**", self.SECTION_6)
        self.assertEqual(self.row(self.SECTION_6, "| `chance.limits.max_posts_per_week` |").split("|")[4].strip(), "L8")

    def test_section_7_keeps_its_numbering_and_has_the_new_limits(self):
        numbers = re.findall(r"(?m)^(\d+)\. ", self.SECTION_7)
        self.assertEqual(numbers, [str(number) for number in range(1, len(numbers) + 1)])          # 번호가 1부터 이어진다(뒤에 다른 묶음의 항목이 더해져도 깨지지 않는다)
        self.assertGreaterEqual(len(numbers), 22)                                                    # 이 묶음의 17–22 까지 있다
        for needle in ("17. **굴러가는 7일은 달력 주와 다르다**", "18. **창 안에서 닫은 초안도 센다**", "19. **세는 값은 이력과 원격 브랜치 목록의 정확도만큼만 정확하다**", "20. **Chance 밖의 블로그에는 주간 상한이 없다**",
                       "21. **꺼진 잠금의 레지스트리에 값을 적어도 세지 않는다**", "22. **켠 직후 일주일은 켜기 전의 글도 센다, 그리고 워치독은 주 단위 기준으로 바뀐다**", "`STALE`", "`NO_POSTS_DAY`",
                       "D-169", "주간 상한(§4-4)도 같은 목록을 쓰므로"):
            self.assertIn(needle, self.SECTION_7, needle)

    def test_section_9_says_the_twelve_other_branch_tests_were_rechecked_with_the_weekly_cap(self):
        paragraph = next(line for line in self.SECTION_9.splitlines() if line.startswith("고치는 법:"))
        for needle in ("주간 상한(L8)을 더한 뒤 같은 합성", "깨지는 시험은 그대로 12개", "36개·82개", "주간 상한 때문에 목록이 늘거나 바뀌지 않았다"):
            self.assertIn(needle, paragraph, needle)

    def test_the_easy_explanation_section_9_and_the_decision_row_mention_the_weekly_cap(self):
        easy = self.TEXT[self.TEXT.index("## 쉬운 설명"):self.TEXT.index("## 1. 한눈에 보기")]
        self.assertIn("일주일(오늘을 포함한 굴러가는 7일)에 만드는 글은 최대 2편", easy)
        self.assertIn("확인 요청 007 답", self.TEXT[:900])                                           # 맨 위 운영자 결정 인용
        row = self.row(self.SECTION_9, "| `pipeline/blogs.json` |")
        for needle in ("`max_posts_per_week` 없음", "§6 의 값 다섯"):
            self.assertIn(needle, row, needle)
        self.assertIn("`[SKIP] code=LOCK_WEEKLY_CAP`", self.SECTION_9)
        decision = self.row(self.SECTION_8, "| L-19 |")
        for needle in ("주간 상한(L8)", "초안 브랜치 이름으로 중복 제거", "fail closed", "하루 → 열린 초안 → 주간"):
            self.assertIn(needle, decision, needle)

    def test_the_t3_list_the_guardrail_row_and_the_register_row_name_the_weekly_cap(self):
        line = next(item for item in self.GUARDRAILS_TEXT.splitlines() if item.startswith("- 제한 재개 잠금(레지스트리 `resume_lock`)을 끄거나"))
        for name in ("MAX_POSTS_PER_WEEK", "WEEK_WINDOW_DAYS"):
            self.assertIn("`%s`" % name, line, name)
            self.assertTrue(hasattr(publish_lock, name), name)
        for needle in ("`chance.limits.max_posts_per_week`", "레지스트리 값 다섯", "'재개 시 주 1–2편'", "(G-C14)"):
            self.assertIn(needle, line, needle)
        guard_row = self.row(self.GUARDRAILS_TEXT, "| G-C14 |")
        for needle in ("규칙 L0–L8", "`chance.limits.max_posts_per_week`", "'재개 시 주 1–2편'", "달력 주와 다르고 닫은 초안도 창 안에서는 센다"):
            self.assertIn(needle, guard_row, needle)
        self.assertNotIn("규칙 L0–L7", guard_row)
        reg_row = self.row(self.GUARDRAILS_TEXT, "| REG-1(제한 재개 잠금)")
        for needle in ("규칙 L0–L8", "`max_posts_per_week` 없음·2 초과"):
            self.assertIn(needle, reg_row, needle)

    def test_the_operator_guide_lists_the_five_values_the_new_code_and_the_new_rule_range(self):
        for needle in ("`resume_lock: true`", "`chance.publish_flow: pr`", "`chance.limits.max_posts_per_day: 1`", "`max_open_drafts: 3`", "`max_posts_per_week: 2`", "값 **다섯**", "`LOCK_WEEKLY_CAP`",
                       "L1–L8", "일주일에 만드는 글", "(운영자 조건 '재개 시 주 1–2편')", "워치독은 켠 뒤 Chance 만 주 단위 기준으로 점검합니다", "D-169"):
            self.assertIn(needle, self.GUIDE_SECTION, needle)
        self.assertNotIn("L1–L7", self.GUIDE_SECTION)
        values = lock_ready()
        limits = blog_of(values, CHANCE)["limits"]
        self.assertEqual({key: limits[key] for key in ("max_posts_per_day", "max_open_drafts", "max_posts_per_week")}, {"max_posts_per_day": 1, "max_open_drafts": 3, "max_posts_per_week": 2})       # 위 값과 같다

    def test_the_architecture_doc_has_the_limit_row_the_code_row_and_the_new_rule_range(self):
        for needle in ("| `limits.max_posts_per_week` |", "| `LOCK_WEEKLY_CAP` |", "L0–L8", "**주간 상한**(`chance.limits.max_posts_per_week`", "`tests/test_publish_lock_weekly.py`", "하루 → 열린 초안 → 주간"):
            self.assertIn(needle, self.ARCH_TEXT, needle)
        self.assertNotIn("규칙 L0–L7 을 어기면", self.ARCH_TEXT)
        row = self.row(self.ARCH_TEXT, "| `limits.max_posts_per_week` |")
        for needle in ("1–14 정수", "불리언 아님", "읽는 곳은 제한 재개 잠금뿐이다", "1 이상 2 이하(L8)"):
            self.assertIn(needle, row, needle)

    def test_the_register_rows_d166_to_d169_exist_once_with_six_cells_and_leave_the_next_branches_numbers_alone(self):
        ids = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", self.DEFECT_TEXT)
        self.assertEqual(len(ids), len(set(ids)))
        needles = {166: ("L8", "LOCK_WEEKLY_CAP", "넷에서 다섯으로"), 167: ("다섯 곳", "WeeklyOddDateTest", "WORKLOG"), 168: ("굴러가는 7일은 달력 주와 다르다", "닫은 초안도 센다", "§7-17–21"),
                   169: ("워치독", "STALE", "NO_POSTS_DAY", "max_gap_hours", "§7-22")}
        for number, words in needles.items():
            row_id = "D-%d" % number
            self.assertEqual(ids.count(row_id), 1, row_id)
            row = self.row(self.DEFECT_TEXT, "| **%s** |" % row_id)
            self.assertEqual(row.count("|"), 7, row_id)                                           # 표의 여섯 칸
            for word in words:
                self.assertIn(word, row, "%s: %s" % (row_id, word))
        for item in ids:                                                                            # D-170 부터는 다른 묶음(허용 목록 D-170–D-178·Fact 후속 D-180·Gate D-185·Gate 후속 D-186–D-189·방어 D-190 이상)이 쓴다 — 이 묶음의 행이 아니다(번호가 겹치지 않는다)
            if int(item[2:]) >= 170:
                self.assertNotIn("LOCK_WEEKLY_CAP", self.row(self.DEFECT_TEXT, "| **%s** |" % item), item)

    def test_the_parts_this_work_added_have_no_tilde_and_no_web_link(self):
        chunks = [self.row(self.TEXT, "| **L8** |"), self.SECTION_4_4, self.SECTION_6, self.SECTION_7, self.row(self.SECTION_8, "| L-19 |"), self.GUIDE_SECTION,
                  self.row(self.ARCH_TEXT, "| `limits.max_posts_per_week` |"), self.row(self.ARCH_TEXT, "| `LOCK_WEEKLY_CAP` |")] + [self.row(self.DEFECT_TEXT, "| **D-%d** |" % number) for number in (166, 167, 168, 169)]
        for chunk in chunks:
            self.assertNotIn("~", chunk)
            self.assertIsNone(re.search(r"https?://", chunk), chunk[:60])
            self.assertNotIn("{{", chunk)


class RuleMatrixTest(unittest.TestCase):
    """규칙을 하나씩 어기는 값으로: 잠금 켬이면 검증기와 가드가 거절하고, 꺼져 있으면 거절하지 않는다(이전과 같음)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def guard(self, reg, **kwargs):
        return lock_tests.GuardRun(self.folder, reg, history=[], remote=[], **kwargs)

    def test_the_ready_registry_is_accepted_by_both(self):
        reg = lock_ready()
        self.assertEqual(registry.validate_registry(reg), [])
        self.assertIsNone(self.guard(reg).code)

    def test_every_violation_is_refused_by_both_when_the_lock_is_on(self):
        for rule, cases in VIOLATIONS.items():
            for label, mutate in cases:
                with self.subTest(rule=rule, case=label):
                    reg = mutated(mutate)
                    self.assertTrue(any(rule in message for message in registry.validate_registry(reg)))        # 검증기(REG-1, python -m pipeline.registry)
                    run = self.guard(reg)
                    self.assertEqual(run.code, 1)                                                                 # 실행 시 가드(generator.py main() 앞)
                    self.assertIn(rule, run.out[0])
                    self.assertEqual(rules_in(publish_lock.lock_errors(reg)), {rule, *EXTRA.get((rule, label), ())})

    def test_the_same_violations_are_not_refused_with_the_lock_off(self):
        for rule, cases in VIOLATIONS.items():
            if rule == "L0":
                continue
            for label, mutate in cases:
                with self.subTest(rule=rule, case=label):
                    reg = with_lock_off(mutated(mutate))
                    if rule != "L5":                                       # L5 의 '값이 있으면 1 이상 정수' 모양 검사만 잠금과 무관하다(별도 시험)
                        self.assertFalse(any("제한 재개 잠금" in message for message in registry.validate_registry(reg)))
                    run = self.guard(reg)
                    self.assertTrue(run.code in (None, 0), (run.code, run.out))    # 거절(종료 1)이 아니다 — 열린 초안 상한이 차 있는 경우의 건너뜀(0)만 있을 수 있다

    def test_the_default_registry_gives_the_same_answers_as_before(self):
        reg = today_registry()
        self.assertEqual(registry.validate_registry(reg), [])
        run = lock_tests.GuardRun(self.folder, reg)
        self.assertEqual((run.code, run.out, run.summary), (None, [], []))


class ShadowWorkflowCannotWriteTest(unittest.TestCase):
    """그림자 실행 워크플로(chance-shadow.yml)가 어떤 쓰기도 못 하는 이유를 파일에서 직접 확인한다."""

    NAME = "chance-shadow.yml"

    def setUp(self):
        self.text = read(self.NAME)
        self.data = yaml.safe_load(self.text)
        self.code = strip_comments(self.text)

    def test_manual_only_no_schedule_no_push_no_pr_no_issue_trigger(self):
        triggers = self.data[True] if True in self.data else self.data["on"]
        self.assertEqual(list(triggers), ["workflow_dispatch"])
        self.assertEqual(sorted(triggers["workflow_dispatch"]["inputs"]), ["as_of", "count"])
        self.assertEqual(triggers["workflow_dispatch"]["inputs"]["count"]["options"], ["1", "2", "3", "4", "5"])
        self.assertEqual(triggers["workflow_dispatch"]["inputs"]["count"]["default"], "3")

    def test_the_token_can_only_read(self):
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        self.assertEqual(write_permissions(self.data), set())
        for job in self.data["jobs"].values():
            self.assertNotIn("permissions", job)                           # job 이 권한을 올리지 못한다
        checkout = next(step for step in all_steps(self.data) if str(step.get("uses", "")).startswith("actions/checkout"))
        self.assertIs(checkout["with"]["persist-credentials"], False)      # 토큰이 git 설정에 남지 않는다

    def test_no_step_writes_or_calls_github(self):
        found = signature(self.text)
        self.assertEqual(found["cmds"], set())
        self.assertEqual(found["perms"], set())
        self.assertEqual(found["uses"], {"actions/upload-artifact"})
        self.assertEqual(found["py"], {"generator.py", "pipeline.quality_shadow", "pipeline.source_policy"})      # source_policy 는 AF7 의 읽기 단계 — 레지스트리 값을 한 줄 낸다(쓰기 없음)
        for forbidden in ("git ", "gh ", "curl", "GITHUB_TOKEN", "GH_TOKEN", "secrets.GITHUB", "pull-requests", "contents: write", "issues: write", "actions: write",
                          "workflow_run", "pull_request", "schedule"):
            self.assertNotIn(forbidden, self.code, forbidden)

    def test_only_the_generator_step_gets_secrets_and_only_through_its_env(self):
        names = set(re.findall(r"secrets\.([A-Za-z0-9_]+)", self.code))
        self.assertEqual(names, {"GEMINI_API_KEY", "UNSPLASH_ACCESS_KEY"})
        carriers = [step for step in all_steps(self.data) if "secrets." in str(step.get("env", ""))]
        self.assertEqual([step["name"] for step in carriers], ["그림자 실행 — 후보 글 만들기(저장소에 쓰지 않음)"])
        for step in all_steps(self.data):
            self.assertNotIn("secrets.", str(step.get("run", "")))
            self.assertNotIn("secrets.", str(step.get("with", "")))

    def test_the_generator_runs_in_shadow_mode_and_the_pause_variable_is_only_read(self):
        step = next(step for step in all_steps(self.data) if step.get("name") == "그림자 실행 — 후보 글 만들기(저장소에 쓰지 않음)")
        env = step["env"]
        self.assertEqual(env["SHADOW_RUN"], "1")
        self.assertEqual(env["PIPELINE_PAUSE"], "${{ vars.PIPELINE_PAUSE }}")          # 값을 그대로 넘길 뿐 만지지 않는다(정지가 켜져 있어도 그림자 모드가 건너뛰는 것은 생성기 쪽 코드)
        self.assertEqual(env["SHADOW_OUT"], "${{ runner.temp }}/chance_shadow_out")     # 러너 임시 폴더 — 저장소 작업 트리가 아니다
        self.assertEqual(env["SHADOW_COUNT"], "${{ inputs.count }}")
        self.assertNotIn("DRY_RUN", env)
        self.assertEqual(set(env), {"GEMINI_API_KEY", "UNSPLASH_ACCESS_KEY", "EVENT_NAME", "PIPELINE_PAUSE", "SHADOW_RUN", "SHADOW_OUT", "SHADOW_COUNT"})
        self.assertNotIn("PIPELINE_PAUSE", self.code.replace("PIPELINE_PAUSE: ${{ vars.PIPELINE_PAUSE }}", ""))

    def test_the_measure_step_is_a_separate_process_and_skips_when_the_tool_is_missing(self):
        step = next(step for step in all_steps(self.data) if str(step.get("name", "")).startswith("그림자 측정"))
        run = step["run"]
        self.assertIn("if [ ! -f pipeline/quality_shadow.py ]; then", run)
        self.assertIn("exit 0", run)
        self.assertEqual(run.count("python -m pipeline.quality_shadow"), 2)
        self.assertIn("--as-of", run)
        self.assertIn("--out", run)
        self.assertIn("[[ \"$as_of\" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]", run)
        generator_step = next(step for step in all_steps(self.data) if step.get("run", "").strip().endswith("python generator.py"))
        self.assertNotIn("quality_shadow", generator_step["run"])           # 생성기 단계는 측정 도구를 부르지 않는다
        self.assertNotIn("quality_shadow", Path(_bootstrap.ROOT, "generator.py").read_text(encoding="utf-8"))

    def test_a_run_without_the_shadow_code_stops_right_after_the_checkout_before_it_can_make_anything(self):
        """검증 지적 2③: 그림자 실행 코드(pipeline/shadow_run.py, GATE 묶음)가 없으면 생성기가 SHADOW_RUN 을 몰라 일반 실행이 된다 — 구조로 막는다."""
        steps = list(all_steps(self.data))
        self.assertEqual([step.get("name") or step.get("uses") for step in steps[:3]], ["actions/checkout@v6", "그림자 실행 코드 확인 (없으면 중단)", "actions/setup-python@v6"])
        check = steps[1]
        self.assertIn("if [ ! -f pipeline/shadow_run.py ]; then", check["run"])
        self.assertIn("::error::이 저장소에는 그림자 실행 코드(pipeline/shadow_run.py)가 없어 중단합니다", check["run"])
        self.assertIn("exit 1", check["run"])
        for key in ("if", "env", "uses", "with"):
            self.assertNotIn(key, check)
        self.assertEqual(escape_hatches(check), [])
        generator = next(index for index, step in enumerate(steps) if str(step.get("run", "")).strip().endswith("python generator.py"))
        self.assertLess(1, generator)                                              # 그 단계는 생성기보다 앞이다
        for step in steps[:generator]:
            self.assertNotIn("secrets.", str(step))                              # 생성기 전에는 어떤 단계도 비밀을 받지 않는다

    def test_the_check_step_really_fails_without_the_file_and_passes_with_it(self):
        run = next(step for step in all_steps(self.data) if step.get("name") == "그림자 실행 코드 확인 (없으면 중단)")["run"]
        bash = shutil.which("bash")
        if os.name == "nt" or bash is None:
            self.skipTest("실제 셸로 돌리는 확인은 리눅스(CI)에서만 한다 — 윈도 PC 에서는 위 구조 시험이 단계의 글자를 확인한다")
        with tempfile.TemporaryDirectory() as tmp:
            first = subprocess.run([bash, "-c", run], cwd=tmp, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(first.returncode, 1)
            self.assertIn("::error::이 저장소에는 그림자 실행 코드(pipeline/shadow_run.py)가 없어 중단합니다", first.stdout)
            Path(tmp, "pipeline").mkdir()
            Path(tmp, "pipeline", "shadow_run.py").write_text("# 시험용 빈 파일\n", encoding="utf-8")
            second = subprocess.run([bash, "-c", run], cwd=tmp, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual((second.returncode, second.stdout), (0, ""))

    def test_the_header_says_the_workflow_is_safe_only_after_the_shadow_code_is_merged(self):
        header = self.text[:self.text.index("on:")]
        for needle in ("병합 순서", "GATE 묶음", "pipeline/shadow_run.py", "docs/QUALITY_GATE.md"):
            self.assertIn(needle, header, needle)

    def test_no_other_workflow_runs_it(self):
        for name in workflow_names():
            if name != self.NAME:
                self.assertNotIn("chance-shadow", read(name), name)
                self.assertNotIn("SHADOW_RUN", read(name), name)

    def test_the_summary_holds_numbers_and_fixed_sentences_only(self):
        step = next(step for step in all_steps(self.data) if step.get("name") == "그림자 결과 요약")
        run = step["run"]
        self.assertNotIn("source_url", run)
        self.assertNotIn("hold_reasons", run)
        self.assertEqual(re.findall(r"jq -r '([^']*)'", run), [".passed == true"])         # 글·사유 문구가 아니라 참/거짓만 읽는다

    def test_results_leave_only_as_an_artifact_with_a_retention(self):
        step = next(step for step in all_steps(self.data) if str(step.get("uses", "")).startswith("actions/upload-artifact"))
        self.assertEqual(step["uses"], "actions/upload-artifact@v6")
        self.assertEqual(step["with"]["retention-days"], 14)
        self.assertEqual(step["with"]["if-no-files-found"], "warn")
        self.assertEqual(sorted(line.strip() for line in step["with"]["path"].strip().splitlines()),
                         ["${{ runner.temp }}/chance_shadow_out", "${{ runner.temp }}/chance_shadow_report"])

    def test_its_name_and_steps_are_korean_and_it_has_a_timeout_and_its_own_queue(self):
        self.assertEqual(self.data["name"], "[Chance] 그림자 실행(수동, 읽기 전용)")
        self.assertTrue(self.data["run-name"].startswith("[Chance] "))
        self.assertNotIn("${{", self.data["run-name"])                       # 외부 값을 넣지 않는다
        self.assertEqual(self.data["concurrency"], {"group": "chance-shadow", "cancel-in-progress": False})
        job = self.data["jobs"]["shadow"]
        self.assertEqual((job["name"], job["timeout-minutes"]), ("그림자 실행·측정", 25))


if __name__ == "__main__":
    unittest.main()
