"""가드레일 검사의 AI 브랜치 push '사전 검사'(운영자 요청 2026-11-03) — 트리거 모양·검사 기준(base) 계산·알림이 새지 않는 길.

운영자(비개발자)는 휴대폰에서 PR 을 만들어 병합만 하면 되고, 검사가 빨갛게 나와 다시 확인을 요청하는 일이 없어야 한다. 그래서 `ai/claude/**` 브랜치 push 에서도
`[공통] 저장소 규칙·테스트 자동 검사`의 `validate` 잡이 돌아, AI 가 병합 부탁(운영자 호출)을 보내기 **전에** 같은 검사의 결과(초록·빨강)를 먼저 본다.
이 시험은 다음을 고정한다.
 1. 트리거는 정확히 push(`main`·`ai/claude/**`)·PR·수동이다. 다른 워크플로가 AI 브랜치 push 에 반응하지 않는다(요청 알림 `ai-request.yml` 과 이 검사만).
 2. 광고 표면 검사의 기준(`--base`)은 PR 검사와 같은 범위 — main 끝(tip)이 아니라 main 과 갈라진 지점(merge-base)이다(main 이 앞서 간 만큼 오탐하지 않게).
    main push 의 `github.event.before` 와 PR 의 `base.sha` 경로는 그대로다.
 3. 갈라진 지점을 못 구하면 광고 표면 검사를 건너뛴 초록이 아니라 단계 실패다(`set -euo pipefail` 아래의 실제 실행으로 확인).
 4. AI 브랜치 push 의 실행은 운영자에게 가는 목록(확인 필요 모음)의 '워크플로 실패'에 오르지 않는다(그 목록은 기본 브랜치 실행만 읽는다). PR 이 열린 뒤에는 같은 커밋의
    검사로 PR 칸에 합쳐 읽힌다 — 취소는 실패가 아니고 하나라도 빨가면 빨강이다(마지막 시험).
네트워크는 쓰지 않는다. 단계의 셸 스크립트는 진짜 git 으로 만든 임시 저장소에서 bash 로 그대로 돌리고(bash 가 없으면 그 시험만 건너뜀), 검증기 호출만 인자를 찍는 가짜 함수로 바꾼다.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
import ops_inbox_helpers as h
import ops_inbox as oi
from pipeline import inbox

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import github_status as gs  # noqa: E402
import validate_repo as vr  # noqa: E402

WORKFLOWS = _bootstrap.ROOT / ".github" / "workflows"
GUARDRAILS = WORKFLOWS / "guardrails.yml"
STEP_NAME = "저장소 가드레일 검증"
BRANCH = "ai/claude/blog-ci-precheck"
ZEROS = "0" * 40
STUB = 'python() { echo "STUB-PYTHON $*"; return "${STUB_RC:-0}"; }\n'       # 진짜 검증기 대신 받은 인자를 찍는다(셸 함수는 PATH 의 python 보다 먼저 불린다)
REGISTRY = json.dumps({"schema_version": 1, "defaults": {},
                       "blogs": [{"key": "chance", "ad_surface": True, "protected_paths": ["index.html", "_layouts/"]}]})


def load_workflow(path=GUARDRAILS):
    text = path.read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def validation_step(data):
    return next(step for step in data["jobs"]["validate"]["steps"] if step.get("name") == STEP_NAME)


def find_bash():
    """단계의 셸을 돌릴 bash. Windows 에서는 PATH 의 bash(WSL 스텁일 수 있다) 대신 Git for Windows 의 것을 찾는다."""
    if os.name != "nt":
        return shutil.which("bash")
    candidates = []
    git = shutil.which("git")
    if git:
        top = Path(git).resolve().parent.parent
        candidates += [top / "bin" / "bash.exe", top / "usr" / "bin" / "bash.exe"]
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(name):
            candidates.append(Path(os.environ[name]) / "Git" / "bin" / "bash.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


BASH = find_bash()
needs_bash = unittest.skipUnless(BASH, "bash 가 없어 단계의 셸 스크립트를 돌려 보지 못했다(Actions 의 ubuntu 에는 있다)")


def notice_line(base):
    """갈라진 지점을 구한 AI 브랜치 push 의 성공 경로가 찍는 줄 — 비로그인 REST 의 주석(`github_status.py jobs`)으로 기준 해시를 읽게 한다."""
    return f"::notice title=광고 표면 검사 기준::main 과 갈라진 지점 {base}"


def code_lines(script):
    """셸 스크립트에서 주석만 있는 줄과 빈 줄을 뺀 줄 목록(주석 속 낱말이 줄 수 세기에 끼지 않게)."""
    return [line.strip() for line in script.splitlines() if line.strip() and not line.strip().startswith("#")]


class GitRepo:
    """진짜 git 으로 만드는 임시 저장소(기본 브랜치 main). 작성자·줄바꿈·서명은 명령마다 고정해 PC 설정에 기대지 않는다."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")

    def git(self, *args, input=None):
        proc = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                              cwd=self.root, check=True, capture_output=True, input=input)
        return proc.stdout.decode("utf-8", "replace").strip()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, rel, text, message=None):
        self.write(rel, text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message or f"edit {rel}")
        return self.git("rev-parse", "HEAD")


class TmpCase(unittest.TestCase):
    """클래스마다 임시 폴더를 한 번 만들고(진짜 git 저장소를 시험마다 새로 만들면 이 PC 에서 시험이 너무 느리다) 시험마다 `reset()` 으로 처음 모양으로 되돌린다."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.tmp = Path(cls._tmp.name)
        cls.repo = GitRepo(cls.tmp / "repo")
        cls.build()

    @classmethod
    def build(cls):
        raise NotImplementedError

    def reset(self):
        raise NotImplementedError

    def setUp(self):
        self.reset()


# ----------------------------------------------------------------------------
# 1. 트리거 모양
# ----------------------------------------------------------------------------
class TriggerShapeTest(unittest.TestCase):
    def setUp(self):
        self.text, self.data = load_workflow()
        self.triggers = self.data[True]                                       # PyYAML 은 on 을 True 로 읽는다

    def test_push_runs_for_main_and_ai_claude_branches_only(self):
        self.assertEqual(self.triggers["push"], {"branches": ["main", "ai/claude/**"]})          # 경로·태그·제외 필터가 없다

    def test_the_triggers_are_exactly_push_pull_request_and_manual(self):
        self.assertEqual(set(self.triggers), {"push", "pull_request", "workflow_dispatch"})
        self.assertIsNone(self.triggers["pull_request"])                                         # PR 검사는 그대로(필터 없음): 병합 결과 트리를 본다
        self.assertIsNone(self.triggers["workflow_dispatch"])
        for forbidden in ("pull_request_target", "schedule", "workflow_run", "issue_comment", "issues"):
            self.assertNotIn(forbidden, self.triggers, forbidden)

    def test_permissions_concurrency_and_history_depth_are_unchanged(self):
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        self.assertEqual(self.data["concurrency"], {"group": "guardrails-${{ github.ref }}", "cancel-in-progress": True})
        for name, job in self.data["jobs"].items():
            self.assertNotIn("permissions", job, name)                                            # 잡이 더 넓은 권한을 달라고 하지 않는다
        checkout = self.data["jobs"]["validate"]["steps"][0]
        self.assertEqual((checkout["uses"], checkout["with"]), ("actions/checkout@v6", {"fetch-depth": 0}))       # merge-base 는 main 의 전체 기록(origin/main)이 있어야 구해진다
        self.assertEqual(self.data["jobs"]["validate"]["strategy"]["matrix"]["python-version"], ["3.10", "3.12"])
        self.assertEqual(self.data["jobs"]["validate"]["timeout-minutes"], 10)

    def test_only_the_request_notification_and_this_check_react_to_a_push_on_an_ai_branch(self):
        """AI 브랜치 push 에 반응하는 워크플로가 이 검사와 요청 알림뿐이고(감시·확인 필요 모음·PR 범위 검사 등과 겹치지 않는다), 서로 같은 동시 실행 그룹을 쓰지 않는다."""
        reacting = {}
        for path in sorted(WORKFLOWS.glob("*.yml")):
            _, data = load_workflow(path)
            triggers = vr._triggers(data)                                                           # on 이 문자열·목록·표 어느 모양이어도 같은 표로 읽는다
            if "push" not in triggers:
                continue
            config = triggers["push"] or {}
            self.assertNotIn("branches-ignore", config, path.name)                                  # 이 시험이 계산하지 못하는 필터 — 쓰게 되면 시험을 먼저 고친다
            patterns = config.get("branches")
            if patterns is None or any(branch_pattern_matches(pattern, BRANCH) for pattern in patterns):
                reacting[path.name] = data                                                          # 브랜치 필터가 없으면 모든 브랜치 push 에 돈다
        self.assertEqual(sorted(reacting), ["ai-request.yml", "guardrails.yml"])
        groups = {name: data["concurrency"]["group"] for name, data in reacting.items()}
        self.assertEqual(groups, {"ai-request.yml": "ai-request-${{ github.sha }}", "guardrails.yml": "guardrails-${{ github.ref }}"})
        self.assertIs(reacting["ai-request.yml"]["concurrency"]["cancel-in-progress"], False)   # 검사 쪽 취소가 요청 알림을 취소하는 길이 없다


def branch_pattern_matches(pattern, branch):
    """GitHub 브랜치 필터의 글로브(`*` 은 `/` 를 넘지 않고 `**` 는 넘는다)를 정규식으로 바꿔 견준다."""
    regex = re.escape(pattern).replace(r"\*\*", "\0").replace(r"\*", "[^/]*").replace("\0", ".*")
    return re.fullmatch(regex, branch) is not None


class BranchPatternHelperTest(unittest.TestCase):
    def test_the_glob_helper_matches_the_way_github_filters_do(self):
        self.assertTrue(branch_pattern_matches("ai/claude/**", "ai/claude/a"))
        self.assertTrue(branch_pattern_matches("ai/claude/**", "ai/claude/a/b"))
        self.assertTrue(branch_pattern_matches("main", "main"))
        for other in ("ai/claude", "ai/draft/2026-11-03-s1", "ai/codex/x", "main2", "xmain", "copilot/x", "issue-edit/1-about"):
            self.assertFalse(branch_pattern_matches("ai/claude/**", other) or branch_pattern_matches("main", other), other)
        self.assertFalse(branch_pattern_matches("ai/*", "ai/claude/x"))


# ----------------------------------------------------------------------------
# 2·3. 검사 기준(base) 계산 — 단계의 셸 스크립트
# ----------------------------------------------------------------------------
class BaseStepTextTest(unittest.TestCase):
    def setUp(self):
        _, self.data = load_workflow()
        self.step = validation_step(self.data)
        self.script = self.step["run"]

    def test_the_step_keeps_its_environment_and_a_strict_shell(self):
        self.assertEqual(self.step["env"], {"PUSH_BASE": "${{ github.event.before }}", "PR_BASE": "${{ github.event.pull_request.base.sha }}"})
        lines = code_lines(self.script)
        self.assertEqual(lines[0], "set -euo pipefail")
        self.assertNotIn("${{", self.script)                                    # 이벤트 값을 셸 명령에 직접 끼우지 않는다(G-A2) — 환경변수로만
        self.assertIsNone(re.search(r"\|\|\s*true\b", self.script))              # 오류를 숨기지 않는다
        self.assertIsNone(self.step.get("continue-on-error"))

    def test_the_merge_base_is_used_for_non_main_pushes_and_the_old_bases_stay_for_main_and_pull_requests(self):
        lines = code_lines(self.script)
        self.assertEqual(sum("git merge-base origin/main HEAD" in line for line in lines), 1)
        self.assertEqual([line for line in lines if "PR_BASE" in line or "PUSH_BASE" in line], ['base="${PR_BASE:-${PUSH_BASE:-}}"'])
        condition = next(line for line in lines if line.startswith("if ") and "GITHUB_EVENT_NAME" in line)
        self.assertEqual(condition, 'if [ "$GITHUB_EVENT_NAME" = "push" ] && [ "$GITHUB_REF" != "refs/heads/main" ]; then')
        self.assertEqual([line for line in lines if "::notice" in line], ['echo "::notice title=광고 표면 검사 기준::main 과 갈라진 지점 $base"'])      # 성공 경로에 한 줄뿐
        self.assertIn("exit 1", lines)                                           # 못 구하면 실패한다
        self.assertEqual(sum(line.startswith("python scripts/validate_repo.py") for line in lines), 2)       # --base 가 있을 때와 없을 때


@needs_bash
class BaseStepBehaviorTest(TmpCase):
    """단계의 셸 스크립트를 진짜 bash·진짜 git 으로 돌린다. 내용: 갈라진 지점 F — (가지) b1 b2 / (main) m1 m2, origin/main = m2(앞서 간 main 끝)."""

    @classmethod
    def build(cls):
        _, data = load_workflow()
        cls.script = validation_step(data)["run"]
        repo = cls.repo
        cls.fork = repo.commit("a.txt", "base")
        repo.git("checkout", "-q", "-b", BRANCH)
        cls.b1 = repo.commit("b1.txt", "b1")
        cls.b2 = repo.commit("b2.txt", "b2")
        repo.git("checkout", "-q", "main")
        cls.m1 = repo.commit("m1.txt", "m1")
        cls.m2 = repo.commit("m2.txt", "m2")
        repo.git("update-ref", "refs/remotes/origin/main", cls.m2)
        repo.git("checkout", "-q", BRANCH)
        repo.git("branch", "-q", "-D", "main")                                     # Actions 의 checkout 처럼 지역에는 가지뿐이고 main 은 origin/main 으로만 있다(`git merge-base main …` 같은 실수를 잡는다)

    def reset(self):
        self.repo.git("checkout", "-q", "-f", BRANCH)
        self.repo.git("reset", "-q", "--hard", self.b2)
        self.repo.git("update-ref", "refs/remotes/origin/main", self.m2)

    def run_step(self, event, ref, push_base="", pr_base="", stub_rc=0, drop=()):
        path = self.tmp / "step.sh"
        path.write_bytes((STUB + self.script).replace("\r\n", "\n").encode("utf-8"))
        env = dict(os.environ, GITHUB_EVENT_NAME=event, GITHUB_REF=ref, PUSH_BASE=push_base, PR_BASE=pr_base, STUB_RC=str(stub_rc))
        for name in drop:
            env.pop(name, None)
        proc = subprocess.run([BASH, path.as_posix()], cwd=self.repo.root, env=env, capture_output=True, timeout=120)
        out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
        calls = [line[len("STUB-PYTHON "):] for line in out.splitlines() if line.startswith("STUB-PYTHON ")]
        return proc.returncode, calls, out

    def test_a_first_push_of_an_ai_branch_checks_the_range_since_it_left_main(self):
        code, calls, out = self.run_step("push", f"refs/heads/{BRANCH}", push_base=ZEROS)
        self.assertEqual((code, calls), (0, [f"scripts/validate_repo.py --base {self.fork}"]), out)
        self.assertNotIn(self.m2, calls[0])                                      # main 끝이 아니다 — main 이 앞서 간 만큼 오탐한다
        self.assertNotEqual(self.fork, self.m2)
        self.assertEqual([line for line in out.splitlines() if "::notice" in line], [notice_line(self.fork)])      # 기준 해시가 주석으로 남는다(단계 로그 원문은 로그인이 있어야 읽힌다)

    def test_a_later_push_of_the_same_branch_uses_the_same_range_not_the_previous_tip(self):
        code, calls, out = self.run_step("push", f"refs/heads/{BRANCH}", push_base=self.b1)
        self.assertEqual((code, calls), (0, [f"scripts/validate_repo.py --base {self.fork}"]), out)
        self.assertIn(notice_line(self.fork), out.splitlines())

    def test_a_branch_that_merged_main_keeps_the_last_main_commit_it_has_as_the_base(self):
        self.repo.git("merge", "-q", "--no-ff", "-m", "merge main up to m1", self.m1)       # 가지가 m1 까지 합쳤다(m2 는 아직)
        code, calls, out = self.run_step("push", f"refs/heads/{BRANCH}", push_base=ZEROS)
        self.assertEqual((code, calls), (0, [f"scripts/validate_repo.py --base {self.m1}"]), out)
        self.assertIn(notice_line(self.m1), out.splitlines())

    def test_a_push_to_main_keeps_using_the_commit_before_the_push_and_never_asks_git(self):
        self.repo.git("update-ref", "-d", "refs/remotes/origin/main")                 # main push 는 merge-base 를 쓰지 않는다 — origin/main 이 없어도 같다
        code, calls, out = self.run_step("push", "refs/heads/main", push_base=self.b1)
        self.assertEqual((code, calls), (0, [f"scripts/validate_repo.py --base {self.b1}"]), out)
        self.assertNotIn("::notice", out)                                        # 기준 주석은 AI 브랜치 push 에서만 — main 실행에는 생기지 않는다
        code, calls, out = self.run_step("push", "refs/heads/main", push_base=ZEROS)           # main 의 첫 push(이전 커밋 0)는 검증기가 알아서 건너뛴다 — 지금까지와 같다
        self.assertEqual((code, calls), (0, [f"scripts/validate_repo.py --base {ZEROS}"]), out)
        self.assertNotIn("::notice", out)
        code, calls, out = self.run_step("push", "refs/heads/main")
        self.assertEqual((code, calls), (0, ["scripts/validate_repo.py"]), out)
        self.assertNotIn("::notice", out)

    def test_a_pull_request_keeps_using_the_base_sha_of_the_pull_request(self):
        code, calls, out = self.run_step("pull_request", "refs/pull/7/merge", pr_base=self.m1)
        self.assertEqual((code, calls), (0, [f"scripts/validate_repo.py --base {self.m1}"]), out)
        self.assertNotIn("::notice", out)
        code, calls, out = self.run_step("pull_request", "refs/pull/7/merge", push_base=self.b1, pr_base=self.m1)      # 둘 다 있으면 PR 쪽이 이긴다 — 옛 식 그대로
        self.assertEqual((code, calls), (0, [f"scripts/validate_repo.py --base {self.m1}"]), out)

    def test_a_manual_run_has_no_base_as_before_even_on_an_ai_branch(self):
        for ref in ("refs/heads/main", f"refs/heads/{BRANCH}"):
            code, calls, out = self.run_step("workflow_dispatch", ref)
            self.assertEqual((code, calls), (0, ["scripts/validate_repo.py"]), (ref, out))
            self.assertNotIn("::notice", out)

    def test_without_origin_main_the_step_fails_instead_of_skipping_the_ad_surface_check(self):
        self.repo.git("update-ref", "-d", "refs/remotes/origin/main")
        code, calls, out = self.run_step("push", f"refs/heads/{BRANCH}", push_base=ZEROS)
        self.assertNotEqual(code, 0, out)
        self.assertEqual(calls, [], out)                                         # 검증기는 base 없이 돌지 않는다(조용한 초록 금지)
        self.assertIn("::error::", out)
        self.assertNotIn("::notice", out)                                        # 기준을 못 구했는데 '기준' 주석이 남으면 안 된다

    def test_unrelated_histories_also_fail_the_step(self):
        tree = self.repo.git("hash-object", "-w", "-t", "tree", "--stdin", input=b"")
        orphan = self.repo.git("commit-tree", tree, "-m", "unrelated root")
        self.repo.git("update-ref", "refs/remotes/origin/main", orphan)
        code, calls, out = self.run_step("push", f"refs/heads/{BRANCH}", push_base=ZEROS)
        self.assertNotEqual(code, 0, out)
        self.assertEqual(calls, [], out)
        self.assertIn("::error::", out)
        self.assertNotIn("::notice", out)

    def test_a_missing_runner_variable_stops_the_step_and_the_validator_failure_fails_it(self):
        code, calls, out = self.run_step("push", f"refs/heads/{BRANCH}", drop=("GITHUB_REF",))      # set -u: 정해지지 않은 변수는 멈춤
        self.assertNotEqual(code, 0, out)
        self.assertEqual(calls, [], out)
        for ref in ("refs/heads/main", f"refs/heads/{BRANCH}"):
            code, calls, out = self.run_step("push", ref, push_base=self.b1, stub_rc=1)
            self.assertEqual((code, len(calls)), (1, 1), (ref, out))             # 검증기가 실패하면 단계도 실패한다


# ----------------------------------------------------------------------------
# 왜 main 끝이 아니라 merge-base 인가 — 진짜 검증기(check_ad_surface)와 진짜 git
# ----------------------------------------------------------------------------
class AdSurfaceRangeTest(TmpCase):
    """갈라진 지점 F 에서 가지는 안내 글(notes.md)만 고치는데, main 은 그 뒤에 광고 표면(index.html)을 고쳤다(다른 PR·봇)."""

    @classmethod
    def build(cls):
        repo = cls.repo
        repo.write("pipeline/blogs.json", REGISTRY)
        repo.write("index.html", "<html>v1</html>")
        repo.write("notes.md", "n1")
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "base")
        cls.base = repo.git("rev-parse", "HEAD")                                    # 갈라진 지점 F
        repo.git("checkout", "-q", "-b", BRANCH)
        repo.git("checkout", "-q", "main")
        cls.tip = repo.commit("index.html", "<html>v2 — main 이 앞서 가며 고침</html>", "landing page changed on main after the branch left")
        repo.git("update-ref", "refs/remotes/origin/main", cls.tip)
        repo.git("checkout", "-q", BRANCH)
        repo.git("branch", "-q", "-D", "main")

    def reset(self):
        self.repo.git("checkout", "-q", "-f", BRANCH)
        self.repo.git("reset", "-q", "--hard", self.base)
        self.repo.git("update-ref", "refs/remotes/origin/main", self.tip)
        self.assertEqual(self.repo.git("merge-base", "origin/main", "HEAD"), self.base)

    def summary(self, findings):
        return [(f.check, f.level, f.message) for f in findings]

    def test_the_range_since_the_fork_ignores_what_main_did_after_the_branch_left(self):
        self.repo.commit("notes.md", "n2", "notes only")
        self.assertEqual(vr.check_ad_surface(self.repo.root, self.base), [])

    def test_the_tip_of_main_as_the_base_would_report_the_main_side_change_as_this_branchs(self):
        self.repo.commit("notes.md", "n2", "notes only")
        found = vr.check_ad_surface(self.repo.root, self.tip)                       # 이것이 merge-base 를 쓰는 이유다 — 오탐
        self.assertEqual([f.check for f in found], ["AD-1"])
        self.assertIn("index.html", found[0].message)

    def test_a_protected_change_made_on_the_branch_itself_is_still_caught_and_a_human_approval_passes(self):
        self.repo.commit("_layouts/post.html", "<html>x</html>", "layout tweak")
        found = vr.check_ad_surface(self.repo.root, self.base)
        self.assertEqual([f.check for f in found], ["AD-1"])
        self.assertIn("_layouts/post.html", found[0].message)
        self.assertNotIn("index.html", found[0].message)
        self.repo.git("commit", "-q", "--allow-empty", "-m", "approved\n\nAd-Surface-Approved: 운영자가 채팅으로 승인")
        self.assertEqual(vr.check_ad_surface(self.repo.root, self.base), [])

    def test_the_first_push_range_equals_what_the_pull_request_check_sees(self):
        """PR 검사: 병합 결과 트리(main 끝 + 이 가지)를 main 끝(base.sha)과 견준다. 사전 검사: 가지 끝을 갈라진 지점과 견준다 — 같은 결과여야 한다."""
        for number, (rel, text) in enumerate((("notes.md", "n2"), ("_layouts/post.html", "<html>x</html>"))):
            with self.subTest(changed=rel):
                self.repo.commit(rel, text, f"branch edit {rel}")
                precheck = self.summary(vr.check_ad_surface(self.repo.root, self.base))
                self.repo.git("checkout", "-q", "-b", f"pr-merge-{number}", self.tip)
                self.repo.git("merge", "-q", "--no-ff", "-m", "Merge pull request", BRANCH)
                pull_request = self.summary(vr.check_ad_surface(self.repo.root, self.tip))
                self.repo.git("checkout", "-q", BRANCH)
                self.assertEqual(precheck, pull_request)
        self.assertEqual([item[0] for item in precheck], ["AD-1"])               # 마지막 반복은 광고 표면을 건드렸다 — 양쪽 다 같은 오류


# ----------------------------------------------------------------------------
# 4. 운영자에게 가는 목록에 새는 길이 없다
# ----------------------------------------------------------------------------
class BranchAwareGitHub(h.FakeGitHub):
    """진짜 GitHub 처럼 `branch` 값으로 실행 목록을 거르는 가짜(기본 FakeGitHub 는 거르지 않는다)."""

    def get(self, path, **params):
        found = super().get(path, **params)
        if params.get("branch") and isinstance(found, dict) and "workflow_runs" in found:
            found["workflow_runs"] = [run for run in found["workflow_runs"] if run.get("head_branch") == params["branch"]]
        return found


NAME = "[공통] 저장소 규칙·테스트 자동 검사"
PATH = ".github/workflows/guardrails.yml"


def guardrails_run(run_id, hours, conclusion, branch, sha):
    return h.make_run(run_id, h.ago(hours=hours), conclusion=conclusion, name=NAME, path=PATH, event="push", branch=branch, sha=sha)


class OperatorListTest(unittest.TestCase):
    """확인 필요 모음(운영자에게 가는 목록)은 워크플로 실행을 기본 브랜치로 걸러 읽는다 — AI 브랜치 push 의 사전 검사 실패는 그 목록에 오르지 않는다."""

    def setUp(self):
        self.fake = BranchAwareGitHub()
        self.failures = []

    def items(self, runs):
        self.fake.runs["guardrails.yml"] = runs
        read = oi.fetch_runs(self.fake, ["guardrails.yml"], h.NOW, "main", self.failures)
        self.assertEqual(self.failures, [])
        return read, inbox.run_items(read, {}, h.NOW, h.REPO_URL, names={"guardrails.yml": NAME})

    def test_a_failed_precheck_on_an_ai_branch_is_not_in_the_list(self):
        red_ai = guardrails_run(10, 0.3, "failure", BRANCH, "b" * 40)
        green_main = guardrails_run(9, 3, "success", "main", "a" * 40)
        read, items = self.items([red_ai, green_main])
        self.assertEqual([run["id"] for run in read["guardrails.yml"]], [9])
        self.assertEqual(items, [])
        self.assertEqual({params.get("branch") for method, path, params in self.fake.log if method == "GET"}, {"main"})

    def test_a_failed_check_on_main_still_reaches_the_list(self):
        """대조: 같은 모양의 실패가 main 에서 나면 항목이 생긴다(위 시험이 항상 비어 있어서 통과하는 것이 아님을 보인다)."""
        read, items = self.items([guardrails_run(10, 0.3, "failure", "main", "b" * 40), guardrails_run(9, 3, "success", "main", "a" * 40)])
        self.assertEqual([item.id for item in items], ["run:guardrails.yml:failed"])
        self.assertEqual(items[0].level, inbox.LEVEL_ACTION)

    def test_a_cancelled_precheck_is_visible_to_the_ai_as_cancelled_and_counted_as_not_green(self):
        """같은 브랜치에 연달아 push 하면 앞선 실행이 취소된다(동시 실행 그룹, cancel-in-progress). AI 의 대기 도구(공개 REST 목록)에서는 `cancelled` 로 보이고 초록이 아닌 쪽으로 센다."""
        cancelled = guardrails_run(11, 0.2, "cancelled", BRANCH, "c" * 40)
        newest = guardrails_run(12, 0.1, None, BRANCH, "d" * 40)
        newest["status"] = "in_progress"
        lines = gs.run_lines([newest, cancelled])
        self.assertIn(" cancelled ", lines[1])
        self.assertIn("push", lines[1])
        self.assertTrue(lines[1].endswith("c" * 7))                                   # 머리 커밋 7자리로 어느 push 의 실행인지 가린다
        self.assertIn("in_progress", lines[0])
        self.assertIn("실패·취소 1", gs.tally([cancelled]))
        self.assertIn("성공·건너뜀 0", gs.tally([cancelled]))

    def test_a_cancelled_or_green_precheck_next_to_the_pull_request_check_does_not_turn_the_pull_request_red(self):
        """PR 이 열린 가지의 머리 커밋에는 사전 검사(push)와 PR 검사의 check-run 이 함께 붙는다 — 확인 필요 모음은 둘을 합쳐 읽는다."""
        green = [h.make_check("검사 (Python 3.10)"), h.make_check("검사 (Python 3.12)")]
        self.assertEqual(inbox.summarize_checks(green + [h.make_check("검사 (Python 3.12)", "cancelled")] + green), "pass")
        self.assertEqual(inbox.summarize_checks(green + [h.make_check("검사 (Python 3.12)", None, "in_progress")]), "pending")
        self.assertEqual(inbox.summarize_checks(green + [h.make_check("검사 (Python 3.12)", "failure")]), "fail")                # 하나라도 빨갛면 빨강 — 같은 코드의 두 검사 중 하나가 간헐 실패해도 같다


if __name__ == "__main__":
    unittest.main()
