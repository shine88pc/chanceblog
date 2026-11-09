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
from lock_helpers import (CHANCE, EXTRA, KCYOON, MACAT, VIOLATIONS, blog_of, lock_ready, mutated, real_registry, rules_in, today_registry, with_lock_off)
from pipeline import publish_lock, registry

ROOT = _bootstrap.ROOT
WORKFLOWS = ROOT / ".github" / "workflows"
DOC = ROOT / "docs" / "PUBLISH_PATHS.md"
GUIDE = ROOT / "docs" / "ACTIONS_GUIDE.md"

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
    "chance-shadow.yml": entry(py={"generator.py", "pipeline.quality_shadow"}, uses={"actions/upload-artifact"}),
    "chanceblog.yml": entry({"actions:write", "contents:write", "pull-requests:write"}, {"gh workflow run", "git commit", "git push"},
                            {"generator.py", "pipeline.draft_flow", "pipeline.notify"}),
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
        for needle in ("GATE → LOCK → SHADOW → R2 → SRC → FACT", "정지 검사 → 그림자 분기(GATE 묶음, `SHADOW_RUN`) → 잠금 가드", "표지판 시험은 고치되 지우지 않는다",
                       "`resume_lock is True`", "`reg == lock_ready()`", "pipeline/shadow_run.py", "GATE 가 먼저 병합된 뒤에만 참이다"):
            self.assertIn(needle, self.TEXT, needle)

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
        for needle in ("pipeline/shadow_run.py", "병합 순서 GATE → LOCK → SHADOW", "docs/QUALITY_GATE.md"):
            self.assertIn(needle, part, needle)

    def test_the_key_typo_rules_and_the_dry_run_exception_are_explained(self):
        for needle in ("resume_lok", "K1·K2", "L0 은 값 오타만 막고", "연습 실행은 저장하지 않아 그대로"):
            self.assertIn(needle, self.SECTION, needle)


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
        self.assertEqual(found["py"], {"generator.py", "pipeline.quality_shadow"})
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
