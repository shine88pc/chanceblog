"""가드레일 검사의 '브랜치 push 사전 검사'(운영자 요청 2026-11-03)와 'PR 로는 돌리지 않는다'(운영자 요청 2026-11-04) — 트리거 모양·시험 병합·검사 기준(base) 계산·알림이 새지 않는 길.

운영자(비개발자)는 휴대폰에서 PR 을 만들어 병합만 하면 되고, 검사가 빨갛게 나와 다시 확인을 요청하거나 PR 화면의 '도는 중·건너뜀' 줄을 보고 일부 검사가 안 돈다고 읽는 일이 없어야 한다.
그래서 `[공통] 저장소 규칙·테스트 자동 검사`는 PR(`pull_request`)로 돌지 않고 어느 브랜치든 push 하면 그 커밋에서 돈다 — PR 화면에는 이미 끝난 결과(초록·빨강)만 보인다.
이 시험은 다음을 고정한다.
 1. 트리거는 정확히 push(브랜치 필터 없음)·수동이다. `pull_request` 가 없다. 다른 워크플로가 AI 브랜치 push 에 반응하지 않는다(요청 알림 `ai-request.yml` 과 이 검사만).
 2. main 이 아닌 브랜치 push 는 검증 전에 이 실행 안에서 `origin/main` 을 시험 병합한다(러너 안에서만 — 올리지 않는다). 충돌이면 실패(`::error::`)하고, 합쳐진 트리에서 검증·시험을 돈다.
 3. 광고 표면 검사의 기준(`--base`)은 시험 병합 직전의 `origin/main` 끝(sha)이다 — 옛 PR 검사의 `PR_BASE` 와 같은 뜻(main 이 앞서 간 만큼 '이 브랜치가 바꾼 파일'로 오탐하지 않는다).
    갈라진 지점(merge-base)이 아니다. main push 의 `github.event.before` 와 수동 실행(기준 없음)은 그대로다.
 4. 기준을 못 구하거나 시험 병합이 안 되거나 병합 결과가 main 끝을 담지 않으면 광고 표면 검사를 건너뛴 초록이 아니라 단계 실패다(`set -euo pipefail` 아래의 실제 실행으로 확인).
 5. main 이 아닌 브랜치 push 의 실행은 운영자에게 가는 목록(확인 필요 모음)의 '워크플로 실패'에 오르지 않는다(그 목록은 기본 브랜치 실행만 읽는다). PR 이 열린 뒤에는 같은 커밋의
    검사로 PR 칸에 합쳐 읽힌다 — 취소는 실패가 아니고 하나라도 빨가면 빨강이다(마지막 시험).
네트워크는 쓰지 않는다. 단계의 셸 스크립트는 진짜 git 으로 만든 임시 '원격'(bare 저장소)과 그 작업 사본에서 bash 로 그대로 돌리고(bash 가 없으면 그 시험만 건너뜀),
검증기 호출만 받은 인자(와 요청하면 그 순간의 추적 파일 목록)를 찍는 가짜 함수로 바꾼다. 시험 병합이 만든 트리에는 진짜 검증기(`check_ad_surface`)를 따로 건다.
진짜 git·bash 는 이 PC 에서 한 번 부르는 데 수 초가 걸려 장면(시나리오)을 클래스에서 한 번만 돌려 두고 여러 시험이 그 결과를 읽는다(RemoteCase).
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
from types import SimpleNamespace

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
# 진짜 검증기 대신 받은 인자를 찍는다(셸 함수는 PATH 의 python 보다 먼저 불린다). STUB_FILES 가 있으면 그 순간의 추적 파일 목록도 찍는다(합쳐진 트리를 보려고)
STUB = r'''python() {
  echo "STUB-PYTHON $*"
  if [ -n "${STUB_FILES:-}" ]; then echo "STUB-FILES $(git ls-files | tr '\n' ' ')"; fi
  return "${STUB_RC:-0}"
}
'''
REGISTRY = json.dumps({"schema_version": 1, "defaults": {},
                       "blogs": [{"key": "chance", "ad_surface": True, "protected_paths": ["index.html", "_layouts/"]}]})
TEMP_NAME, TEMP_EMAIL = "guardrails-premerge", "guardrails-premerge@users.noreply.github.com"      # 러너 안 임시 신원(스크립트가 정하는 값)
BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")


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
    """시험 병합에 성공한 브랜치 push 가 찍는 줄 — 비로그인 REST 의 주석(`github_status.py jobs`)으로 기준 해시를 읽게 한다."""
    return f"::notice title=광고 표면 검사 기준::시험 병합 직전의 main 끝 {base}"


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

    def git(self, *args, input=None, check=True, identity=None):
        who = identity or ("t", "t@example.com")
        proc = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", f"user.name={who[0]}", "-c", f"user.email={who[1]}",
                               "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                              cwd=self.root, capture_output=True, input=input)
        if check and proc.returncode:
            raise AssertionError(f"git {' '.join(args)} 실패({proc.returncode}): {proc.stderr.decode('utf-8', 'replace').strip()}")      # 왜 실패했는지 시험 출력에 남긴다
        return proc.stdout.decode("utf-8", "replace").strip()

    def plain(self, *args, check=True):
        """명령줄 설정(-c)을 붙이지 않고 git 을 부른다 — 저장소의 설정 파일에 실제로 적힌 값을 읽을 때."""
        proc = subprocess.run(["git", *args], cwd=self.root, check=check, capture_output=True)
        return proc.stdout.decode("utf-8", "replace").strip()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, rel, text, message=None, identity=None):
        self.write(rel, text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message or f"edit {rel}", identity=identity)
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


class Run:
    """단계 한 번의 결과: 종료 코드·전체 출력·가짜 검증기가 받은 인자 목록·(요청했다면) 그 순간의 추적 파일·`::notice`·`::error::` 줄."""

    def __init__(self, code, out):
        self.code, self.out = code, out
        lines = out.splitlines()
        self.calls = [line[len("STUB-PYTHON "):] for line in lines if line.startswith("STUB-PYTHON ")]
        files = [line[len("STUB-FILES "):] for line in lines if line.startswith("STUB-FILES ")]
        self.files = set(files[-1].split()) if files else set()
        self.notices = [line for line in lines if "::notice" in line]
        self.errors = [line for line in lines if "::error::" in line]



class RemoteCase(TmpCase):
    """진짜 git 의 임시 '원격'(bare 저장소 `remote.git`, 기본 가지 main)과 그 작업 사본(`repo`, 원격은 `origin`). 작업 사본은 Actions 의 checkout 이 만드는 모양이다 —
    지역에는 push 한 가지(BRANCH)뿐이고 main 은 `origin/main` 으로만 있다. 시험은 이 작업 사본에서 단계의 셸을 그대로 돌린다(진짜 `git fetch`·`git merge`).

    진짜 git·bash 는 이 PC 에서 한 번 부르는 데 수 초가 걸려 시험마다 새로 돌리면 한 파일이 10분을 넘는다. 그래서 '시나리오'(저장소 모양 → 단계 한 번 → 그 순간의 사실)를 클래스에서
    한 번만 돌려 두고(`scenario(이름)`) 여러 시험이 그 결과를 읽는다. 시나리오 사이의 되돌리기(`settle`)는 모양이 달라진 부분에만 git 을 부른다."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.tmp = Path(cls._tmp.name)
        cls.remote = cls.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(cls.remote)], check=True, capture_output=True)
        subprocess.run(["git", "--git-dir", str(cls.remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True, capture_output=True)
        cls.repo = GitRepo(cls.tmp / "repo")
        cls.repo.git("remote", "add", "origin", str(cls.remote))
        cls.home = cls.tmp / "home"                                                 # 러너의 전역 git 설정 자리 — 단계가 여기에 아무것도 쓰지 않아야 한다
        cls.home.mkdir()
        cls.nowhere = str(cls.tmp / "no-such-remote.git")                           # 닿지 않는 원격 주소
        cls.results = {}                                                            # 시나리오 이름 → 결과
        cls.state = {}                                                              # 작업 사본·원격이 지금 어떤 모양인지(None 은 모름)
        cls.build()

    def reset(self):
        """시험마다 되돌리지 않는다 — 시나리오가 시작할 때 `settle` 로 스스로 맞춘다."""

    @classmethod
    def keep(cls, **names):
        """나중에 쓸 커밋을 가리키는 참조를 달아 둔다(`reset` 으로 가지가 옮겨 가도 객체가 남게)."""
        for name, sha in names.items():
            cls.repo.git("update-ref", f"refs/keep/{name}", sha)
            setattr(cls, name, sha)

    @classmethod
    def start_from(cls, branch, remote):
        cls.start = {"branch": branch, "remote": remote}
        cls.state.update(branch=branch, remote=remote, tracking=remote, url=str(cls.remote), identity=False)

    def settle(self, branch=None, remote=None, tracking=None, url=None):
        """작업 사본·원격을 시나리오가 바라는 모양으로 맞춘다: BRANCH 는 branch, 원격 main 은 remote, 작업 사본의 origin/main 은 tracking(기본은 remote), origin 주소는 url.
        이미 그 모양이면 git 을 부르지 않는다."""
        want = {"branch": branch or self.start["branch"], "remote": remote or self.start["remote"], "url": url or str(self.remote)}
        want["tracking"] = tracking or want["remote"]
        state, repo = self.state, self.repo
        if state["identity"]:
            repo.git("config", "--remove-section", "user", check=False)             # 앞선 실행이 남긴 로컬 신원 — 단계가 스스로 정하는지 보려고 지운다
            state["identity"] = False
        if state["branch"] != want["branch"]:
            repo.git("reset", "-q", "--hard", want["branch"])
            state["branch"] = want["branch"]
        if state["remote"] != want["remote"]:
            repo.git("push", "-q", "-f", str(self.remote), f"{want['remote']}:refs/heads/main")        # 이름이 아니라 경로로 올린다(앞 시나리오가 origin 주소를 닿지 않는 곳으로 바꿔 뒀을 수 있다)
            state["remote"], state["tracking"] = want["remote"], None
        if state["tracking"] != want["tracking"]:
            repo.git("update-ref", "refs/remotes/origin/main", want["tracking"])
            state["tracking"] = want["tracking"]
        if state["url"] != want["url"]:
            repo.git("remote", "set-url", "origin", want["url"])
            state["url"] = want["url"]

    def scenario(self, name):
        results = type(self).results
        if name not in results:
            results[name] = getattr(self, "scenario_" + name)()
        return results[name]

    def remote_refs(self):
        proc = subprocess.run(["git", "--git-dir", str(self.remote), "for-each-ref", "--format=%(refname) %(objectname)"], check=True, capture_output=True)
        return proc.stdout.decode("utf-8", "replace").strip()

    def step_env(self, event, ref, push_base="", stub_rc=0, drop=(), extra=None, files=False):
        env = dict(os.environ, GITHUB_EVENT_NAME=event, GITHUB_REF=ref, PUSH_BASE=push_base, STUB_RC=str(stub_rc),
                   HOME=str(self.home), USERPROFILE=str(self.home), XDG_CONFIG_HOME=str(self.home / "xdg"), GIT_CONFIG_NOSYSTEM="1",
                   GIT_CONFIG_GLOBAL=str(self.home / "gitconfig"), GIT_TERMINAL_PROMPT="0", **(extra or {}))
        if files:
            env["STUB_FILES"] = "1"
        for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL", "GIT_DIR", "GIT_WORK_TREE"):
            env.pop(name, None)                                                    # 단계가 스스로 정한 임시 신원만 쓰는지 보려고 PC 의 신원이 새지 않게 한다
        for name in drop:
            env.pop(name, None)
        return env

    def go(self, event, ref, push_base="", stub_rc=0, drop=(), prelude="", extra=None, files=False):
        """단계의 셸을 작업 사본에서 그대로 돌린다(bash). 돌린 뒤에는 가지·추적 참조·로컬 신원이 바뀌었을 수 있다고 적어 둔다."""
        path = self.tmp / "step.sh"
        path.write_bytes((STUB + prelude + self.script).replace("\r\n", "\n").encode("utf-8"))
        env = self.step_env(event, ref, push_base, stub_rc, drop, extra, files)
        proc = subprocess.run([BASH, path.as_posix()], cwd=self.repo.root, env=env, capture_output=True, timeout=180)
        self.state.update(branch=None, tracking=None, identity=True)
        return Run(proc.returncode, proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace"))

    def push(self, push_base=ZEROS, ref=f"refs/heads/{BRANCH}", **kwargs):
        return self.go("push", ref, push_base=push_base, **kwargs)

    def head(self):
        return self.repo.git("rev-parse", "HEAD")

    def parents(self, rev="HEAD"):
        return self.repo.git("rev-list", "--parents", "-n", "1", rev).split()[1:]

    def names_between(self, base):
        """검증기가 '바뀐 파일'로 읽는 것 — `git diff --name-only <base>..HEAD`."""
        return self.repo.git("diff", "--name-only", f"{base}..HEAD").split()


# ----------------------------------------------------------------------------
# 1. 트리거 모양
# ----------------------------------------------------------------------------
class TriggerShapeTest(unittest.TestCase):
    def setUp(self):
        self.text, self.data = load_workflow()
        self.triggers = self.data[True]                                       # PyYAML 은 on 을 True 로 읽는다

    def test_push_has_no_filter_so_every_branch_is_checked_when_it_is_pushed(self):
        self.assertIn("push", self.triggers)
        self.assertIsNone(self.triggers["push"])                              # 필터(branches·branches-ignore·tags·paths)가 하나도 없다 — 어느 브랜치든
        head = self.text.split("\npermissions:")[0]
        on_block = [line for line in head.split("\non:\n")[1].splitlines() if line.strip() and not line.strip().startswith("#")]
        self.assertEqual(on_block, ["  push:", "  workflow_dispatch:"])       # 글자 그대로도 두 줄뿐(필터 줄이 끼어들지 않았다)

    def test_the_triggers_are_exactly_push_and_manual_and_a_pull_request_does_not_start_it(self):
        self.assertEqual(set(self.triggers), {"push", "workflow_dispatch"})
        self.assertIsNone(self.triggers["workflow_dispatch"])
        for forbidden in ("pull_request", "pull_request_target", "schedule", "workflow_run", "issue_comment", "issues", "release", "create"):
            self.assertNotIn(forbidden, self.triggers, forbidden)             # PR 을 만들면 새로 도는 검사·건너뜀 줄이 화면에 생기지 않는다(운영자 요청 2026-11-04)
        self.assertNotIn("pull_request", self.text.replace("pull_request_target", "").split("jobs:")[1])     # 잡 안에서 PR 이벤트를 기다리는 조건도 없다

    def test_permissions_concurrency_and_history_depth_are_unchanged(self):
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        self.assertEqual(self.data["concurrency"], {"group": "guardrails-${{ github.ref }}", "cancel-in-progress": True})
        for name, job in self.data["jobs"].items():
            self.assertNotIn("permissions", job, name)                                            # 잡이 더 넓은 권한을 달라고 하지 않는다
        checkout = self.data["jobs"]["validate"]["steps"][0]
        self.assertEqual((checkout["uses"], checkout["with"]), ("actions/checkout@v6", {"fetch-depth": 0}))       # 시험 병합은 main 의 전체 기록이 있어야 이어진다
        self.assertEqual(self.data["jobs"]["validate"]["strategy"]["matrix"]["python-version"], ["3.10", "3.12"])
        self.assertEqual(self.data["jobs"]["validate"]["timeout-minutes"], 10)
        self.assertIs(self.data["jobs"]["validate"]["strategy"]["fail-fast"], False)

    def test_the_checks_themselves_are_not_weakened(self):
        """같은 검증·단위 테스트·actionlint 가 그대로 있고 숨기는 장치가 없다(건너뛴 초록·continue-on-error·|| true 금지)."""
        steps = self.data["jobs"]["validate"]["steps"]
        names = [step.get("name") or step["uses"] for step in steps]
        self.assertEqual(names[2:], ["검증 도구 설치", "저장소 가드레일 검증", "단위 테스트", "워크플로 정적 분석 (actionlint)"])
        self.assertEqual(steps[4]["run"], "python -m unittest discover -s tests -v")
        self.assertEqual((steps[5]["run"], steps[5]["if"]), ("actionlint", "matrix.python-version == '3.12'"))
        for step in steps:
            self.assertNotIn("continue-on-error", step, step.get("name"))
            if step.get("name") != "워크플로 정적 분석 (actionlint)":
                self.assertNotIn("if", step, step.get("name"))                       # 건너뛰는 조건은 actionlint 의 3.12 한 칸뿐(옛 그대로)
        self.assertNotIn("continue-on-error", self.data["jobs"]["validate"])
        self.assertIsNone(re.search(r"\|\|\s*true\b", self.text))

    def reacting(self, branch):
        reacting = {}
        for path in sorted(WORKFLOWS.glob("*.yml")):
            _, data = load_workflow(path)
            triggers = vr._triggers(data)                                                           # on 이 문자열·목록·표 어느 모양이어도 같은 표로 읽는다
            if "push" not in triggers:
                continue
            config = triggers["push"] or {}
            self.assertNotIn("branches-ignore", config, path.name)                                  # 이 시험이 계산하지 못하는 필터 — 쓰게 되면 시험을 먼저 고친다
            patterns = config.get("branches")
            if patterns is None or any(branch_pattern_matches(pattern, branch) for pattern in patterns):
                reacting[path.name] = data                                                          # 브랜치 필터가 없으면 모든 브랜치 push 에 돈다
        return reacting

    def test_only_the_request_notification_and_this_check_react_to_a_push_on_an_ai_branch(self):
        """AI 브랜치 push 에 반응하는 워크플로가 이 검사·요청 알림·텔레그램 수신(예약 읽기, 2026-11-04 — 요청을 올릴 때마다 한 번 더 읽는다)뿐이고(감시·확인 필요 모음·PR 범위 검사 등과 겹치지 않는다),
        서로 같은 동시 실행 그룹을 쓰지 않는다."""
        reacting = self.reacting(BRANCH)
        self.assertEqual(sorted(reacting), ["ai-request.yml", "guardrails.yml", "telegram-inbox.yml"])
        groups = {name: data["concurrency"]["group"] for name, data in reacting.items()}
        self.assertEqual(groups, {"ai-request.yml": "ai-request-${{ github.sha }}", "guardrails.yml": "guardrails-${{ github.ref }}", "telegram-inbox.yml": "telegram-inbox"})
        self.assertEqual(len(set(groups.values())), 3)                                          # 세 그룹이 모두 달라 서로를 취소하거나 기다리게 하지 않는다
        self.assertIs(reacting["ai-request.yml"]["concurrency"]["cancel-in-progress"], False)   # 검사 쪽 취소가 요청 알림을 취소하는 길이 없다
        self.assertIs(reacting["telegram-inbox.yml"]["concurrency"]["cancel-in-progress"], False)  # 검사·요청 알림이 텔레그램 수신을 취소하는 길도 없다

    def test_every_other_branch_is_checked_by_this_check_alone(self):
        """Copilot·사람의 PR 가지(`copilot/…`·`issue-edit/…`·그 밖의 이름)도 push 로 이 검사가 돈다 — 다른 워크플로는 반응하지 않는다."""
        for branch in ("copilot/fix-12", "issue-edit/12-about-r5", "feature/x", "ai/draft/2026-11-03-s1", "ai/codex/x", "hotfix"):
            self.assertEqual(sorted(self.reacting(branch)), ["guardrails.yml"], branch)
        self.assertIn("guardrails.yml", self.reacting("main"))                                       # main push 는 병합 직후 검사(실패하면 알림)


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
# 2·3·4. 시험 병합과 검사 기준(base) — 단계의 셸 스크립트
# ----------------------------------------------------------------------------
class StepTextTest(unittest.TestCase):
    def setUp(self):
        self.text, self.data = load_workflow()
        self.step = validation_step(self.data)
        self.script = self.step["run"]
        self.lines = code_lines(self.script)

    def test_the_step_keeps_a_strict_shell_and_takes_event_values_only_through_the_environment(self):
        self.assertEqual(self.step["env"], {"PUSH_BASE": "${{ github.event.before }}"})        # PR 이벤트가 없으니 PR_BASE 도 없다
        self.assertEqual(self.lines[0], "set -euo pipefail")
        self.assertNotIn("${{", self.script)                                    # 이벤트 값을 셸 명령에 직접 끼우지 않는다(G-A2) — 환경변수로만
        self.assertIsNone(re.search(r"\|\|\s*true\b", self.script))              # 오류를 숨기지 않는다
        self.assertIsNone(self.step.get("continue-on-error"))
        for external in ("GITHUB_HEAD_REF", "head_ref", "github.event", "GITHUB_ACTOR", "GITHUB_REF_NAME"):
            self.assertNotIn(external, self.script, external)                   # 브랜치 이름·사람 이름 같은 바깥 값은 어떤 명령에도 쓰지 않는다
        self.assertEqual(self.script.count("GITHUB_REF"), 1)                    # 가지가 main 인지 견주는 조건 한 곳뿐
        self.assertEqual(self.script.count("GITHUB_EVENT_NAME"), 1)
        self.assertEqual(self.script.count("PUSH_BASE"), 1)                      # main push 의 옛 기준 한 곳뿐

    def test_the_whole_flow_is_fixed_line_by_line(self):
        """검사 단계의 모든 명령을 순서까지 고정한다(`::error::` 문구만 자유 — 아래 시험이 따로 본다). 옛 PR 경로(PR_BASE)·merge-base 기준은 없다."""
        structure = ["echo ::error::" if line.startswith('echo "::error::') else line for line in self.lines]
        self.assertEqual(structure, [
            "set -euo pipefail",
            'if [ "$GITHUB_EVENT_NAME" = "push" ] && [ "$GITHUB_REF" != "refs/heads/main" ]; then',
            "git fetch --no-tags origin '+refs/heads/main:refs/remotes/origin/main'",
            "if ! base=\"$(git rev-parse --verify --quiet 'refs/remotes/origin/main^{commit}')\" || [ -z \"$base\" ]; then",
            "echo ::error::", "exit 1", "fi",
            'git config user.name "guardrails-premerge"',
            'git config user.email "guardrails-premerge@users.noreply.github.com"',
            'if ! git merge --no-edit -m "guardrails: test merge of origin/main (not pushed)" origin/main; then',
            "echo ::error::", "exit 1", "fi",
            'if ! git merge-base --is-ancestor "$base" HEAD; then',
            "echo ::error::", "exit 1", "fi",
            'echo "::notice title=광고 표면 검사 기준::시험 병합 직전의 main 끝 $base"',
            "else",
            'base="${PUSH_BASE:-}"',
            "fi",
            'if [ -n "$base" ]; then',
            'python scripts/validate_repo.py --base "$base"',
            "else",
            "python scripts/validate_repo.py",
            "fi",
        ])

    def test_every_failure_path_ends_the_step_and_the_notice_comes_only_after_a_good_merge(self):
        errors = [i for i, line in enumerate(self.lines) if line.startswith('echo "::error::')]
        self.assertEqual(len(errors), 3)                                         # 기준 못 구함 · 병합 못 함 · 병합 결과가 main 끝을 담지 않음
        for index in errors:
            self.assertEqual(self.lines[index + 1], "exit 1", self.lines[index])
        notice = next(i for i, line in enumerate(self.lines) if "::notice" in line)
        self.assertGreater(notice, max(errors))                                  # 기준 주석은 시험 병합이 끝난 뒤에만 — 실패한 실행에 '기준' 줄이 남지 않는다
        self.assertEqual([line for line in self.lines if "::notice" in line], ['echo "::notice title=광고 표면 검사 기준::시험 병합 직전의 main 끝 $base"'])
        messages = [self.lines[i] for i in errors]
        self.assertIn("origin/main", messages[0])
        self.assertIn("새 main", messages[1])                                    # 충돌 안내: 새 main 위에서 다시 만들어야 한다
        self.assertIn("다시 만들어야", messages[1])
        self.assertIn("충돌", messages[1])
        self.assertIn("main 끝", messages[2])
        for message in messages:
            self.assertIn("실패시킵니다", message)                                # 건너뛴 초록으로 두지 않는다

    def test_the_base_is_the_main_tip_before_the_merge_and_the_comment_gives_the_reason(self):
        self.assertEqual([line for line in self.lines if "git merge-base" in line], ['if ! git merge-base --is-ancestor "$base" HEAD; then'])   # 갈라진 지점을 구하는 명령은 없다
        self.assertEqual(sum("rev-parse" in line for line in self.lines), 1)
        order = [next(i for i, line in enumerate(self.lines) if needle in line)
                 for needle in ("git fetch", "git rev-parse", "git config user.name", "git config user.email", "git merge --no-edit", "--is-ancestor", "::notice", "python scripts/validate_repo.py --base")]
        self.assertEqual(order, sorted(order))                                   # 가져오기 → 기준 → 신원 → 시험 병합 → 포함 확인 → 기준 주석 → 검증
        for phrase in ("시험 병합 직전의 origin/main 끝", "main 이 앞서 간 만큼", "오탐", "merge-base", "건너뛴 초록"):
            self.assertIn(phrase, self.script, phrase)                           # 근거를 주석에 적었다

    def test_the_merge_only_happens_inside_the_runner(self):
        for forbidden in ("git push", "--global", "--system", "git remote", "git checkout", "git reset", "git rebase", "git commit", "git tag", "git branch",
                          "git stash", "git clean", "gh ", "curl", "wget", "GITHUB_TOKEN", "secrets."):
            self.assertNotIn(forbidden, self.script, forbidden)
        self.assertEqual(sum(line.startswith("git config ") for line in self.lines), 2)           # 신원 둘뿐 — 저장소 폴더의 로컬 설정
        self.assertEqual(sum("git merge " in line for line in self.lines), 1)
        self.assertEqual(sum(line.startswith("git fetch ") for line in self.lines), 1)
        identity = re.findall(r'git config user\.(?:name|email) "([^"]+)"', self.script)
        self.assertEqual(identity, [TEMP_NAME, TEMP_EMAIL])
        self.assertFalse(vr._is_agent_commit((identity[0], identity[1], identity[0], identity[1], "")))      # 임시 신원이 Copilot 으로 읽혀 승인 표시 검사를 건드리지 않는다

    def test_the_two_validator_calls_stay_as_they_were(self):
        self.assertEqual(sum(line.startswith("python scripts/validate_repo.py") for line in self.lines), 2)       # --base 가 있을 때와 없을 때
        self.assertIn('python scripts/validate_repo.py --base "$base"', self.lines)
        self.assertIn("python scripts/validate_repo.py", self.lines)
        self.assertEqual(self.lines.count('base="${PUSH_BASE:-}"'), 1)


@needs_bash
class PremergeStepBehaviorTest(RemoteCase):
    """단계의 셸 스크립트를 진짜 bash·진짜 git(진짜 `git fetch`·`git merge`)으로 돌린다.
    기본 모양: 갈라진 지점 F — (가지) b1 b2 / (main) m1 m2, 원격 main·origin/main = m2(앞서 간 main 끝). 시나리오마다 이 모양에서 필요한 만큼만 바꿔 단계를 한 번 돌린다."""

    @classmethod
    def build(cls):
        _, data = load_workflow()
        cls.script = validation_step(data)["run"]
        repo = cls.repo
        cls.fork = repo.commit("a.txt", "base")
        repo.git("push", "-q", "origin", "main")
        repo.git("checkout", "-q", "-b", BRANCH)
        cls.b1 = repo.commit("b1.txt", "b1")
        cls.b2 = repo.commit("b2.txt", "b2")
        conflict_branch = repo.commit("conflict.txt", "branch side")                 # 가지 쪽 충돌 후보(b2 위)
        repo.git("reset", "-q", "--hard", cls.b2)
        repo.git("checkout", "-q", "main")
        cls.m1 = repo.commit("m1.txt", "m1")
        cls.m2 = repo.commit("m2.txt", "m2")
        repo.git("push", "-q", "origin", "main")
        m3 = repo.commit("m3.txt", "m3")                                              # main 이 더 앞서 갈 후보(원격에는 시나리오가 올린다)
        repo.git("reset", "-q", "--hard", cls.m2)
        repo.commit("_posts/2026-11-04-a.md", "post a", "자동 포스팅 a", identity=BOT)    # 봇이 main 에 올린 글 커밋들
        repo.commit("history.json", "{}", "자동 포스팅 이력", identity=BOT)
        bot_tip = repo.commit("_posts/2026-11-04-b.md", "post b", "자동 포스팅 b", identity=BOT)
        repo.git("reset", "-q", "--hard", cls.m2)
        conflict_main = repo.commit("conflict.txt", "main side")                      # main 쪽 충돌 후보(m2 위)
        repo.git("reset", "-q", "--hard", cls.m2)
        orphan = repo.git("commit-tree", repo.git("hash-object", "-w", "-t", "tree", "--stdin", input=b""), "-m", "unrelated root")
        repo.git("checkout", "-q", BRANCH)
        repo.git("merge", "-q", "--no-ff", "-m", "merge main up to m1", cls.m1)       # 가지가 main 을 m1 까지만(또는 m2 까지) 합친 모양
        merged_m1 = repo.git("rev-parse", "HEAD")
        repo.git("reset", "-q", "--hard", cls.b2)
        repo.git("merge", "-q", "--no-ff", "-m", "merge main up to m2", cls.m2)
        merged_m2 = repo.git("rev-parse", "HEAD")
        repo.git("reset", "-q", "--hard", cls.b2)
        cls.keep(m3=m3, bot_tip=bot_tip, conflict_branch=conflict_branch, conflict_main=conflict_main, orphan=orphan, merged_m1=merged_m1, merged_m2=merged_m2)
        repo.git("branch", "-q", "-D", "main")                                         # Actions 의 checkout 처럼 지역에는 가지뿐이고 main 은 origin/main 으로만 있다(`git merge-base main …` 같은 실수를 잡는다)
        cls.start_from(cls.b2, cls.m2)

    # ---- 시나리오(저장소 모양 → 단계 한 번 → 그 순간의 사실) ----
    def scenario_first(self):
        """평범한 경우: 가지 b1 b2, main m1 m2. 이전 커밋 값(github.event.before)이 있어도 기준으로 쓰지 않는다."""
        self.settle()
        before = self.remote_refs()
        run = self.push(push_base=self.b1, files=True)
        return SimpleNamespace(run=run, head=self.head(), parents=self.parents(), remote_before=before, remote_after=self.remote_refs(),
                               home_files=sorted(path.name for path in self.home.rglob("*")), local_name=self.repo.plain("config", "--local", "user.name", check=False),
                               local_email=self.repo.plain("config", "--local", "user.email", check=False),
                               who=self.repo.git("log", "-1", "--format=%an|%ae|%cn|%ce|%s"))

    def scenario_stale_copy_and_older_main(self):
        """가지가 main 을 m1 까지 합쳐 둔 상태에서, 러너 사본의 origin/main 은 m2 인데 원격 main 은 그 사이 m3 까지 앞서 갔다."""
        self.settle(branch=self.merged_m1, remote=self.m3, tracking=self.m2)
        run = self.push(files=True)
        return SimpleNamespace(run=run, parents=self.parents(), tracking=self.repo.git("rev-parse", "refs/remotes/origin/main"))

    def scenario_already_latest(self):
        self.settle(branch=self.merged_m2)
        run = self.push()
        return SimpleNamespace(run=run, before=self.merged_m2, after=self.head())

    def scenario_no_commit_of_its_own(self):
        """가지에 자기 커밋이 없고 main 만 앞서 갔다(가지 끝 = 갈라진 지점)."""
        self.settle(branch=self.fork)
        run = self.push(push_base="")
        return SimpleNamespace(run=run, after=self.head(), names=self.names_between(self.m2))

    def scenario_bot_commits(self):
        """봇이 main 에 글 커밋 셋을 올렸다(러너 사본은 m2 에서 멈춰 있다)."""
        self.settle(remote=self.bot_tip, tracking=self.m2)
        run = self.push(files=True)
        base = run.calls[0].split()[-1] if run.calls else self.m2
        return SimpleNamespace(run=run, base=base, names=self.names_between(base), commits=self.repo.git("rev-list", "--count", f"{base}..HEAD"),
                               stale_names=self.names_between(self.fork))

    def scenario_conflict(self):
        self.settle(branch=self.conflict_branch, remote=self.conflict_main, tracking=self.m2)
        return SimpleNamespace(run=self.push())

    def scenario_unrelated_histories(self):
        self.settle(remote=self.orphan, tracking=self.m2)
        return SimpleNamespace(run=self.push())

    def scenario_unreachable_remote(self):
        self.settle(url=self.nowhere)
        return SimpleNamespace(run=self.push(), head=self.head())

    def scenario_remote_without_main(self):
        self.settle()
        subprocess.run(["git", "--git-dir", str(self.remote), "update-ref", "-d", "refs/heads/main"], check=True, capture_output=True)
        self.state["remote"] = None
        return SimpleNamespace(run=self.push(), tracking=self.repo.git("rev-parse", "refs/remotes/origin/main"))

    def scenario_base_cannot_be_read(self):
        self.settle()
        run = self.push(prelude='git() { if [ "$1" = "rev-parse" ]; then return 1; fi; command git "$@"; }\n')      # 가져오기는 됐는데 기준 해시를 못 읽는 상황
        return SimpleNamespace(run=run, head=self.head())

    def scenario_merge_does_nothing(self):
        self.settle()
        run = self.push(prelude='git() { if [ "$1" = "merge" ]; then return 0; fi; command git "$@"; }\n')           # 병합 명령이 성공이라고만 하고 아무것도 안 한 상황
        return SimpleNamespace(run=run)

    def scenario_hostile_ref(self):
        self.settle()
        run = self.push(ref="refs/heads/ai/claude/x$(touch PWNED-SUBST)`touch PWNED-TICK`;touch PWNED-SEMI")
        made = {name: (self.repo.root / name).exists() for name in ("PWNED-SUBST", "PWNED-TICK", "PWNED-SEMI")}
        for name in made:
            (self.repo.root / name).unlink(missing_ok=True)
        return SimpleNamespace(run=run, made=made)

    def scenario_hostile_previous_commit_on_main(self):
        self.settle(url=self.nowhere)
        run = self.go("push", "refs/heads/main", push_base="$(touch PWNED-BASE)")        # main push 의 이전 커밋 값도 따옴표 안의 글자일 뿐
        made = (self.repo.root / "PWNED-BASE").exists()
        (self.repo.root / "PWNED-BASE").unlink(missing_ok=True)
        return SimpleNamespace(run=run, made=made)

    def scenario_branch_named_like_main(self):
        self.settle()
        return SimpleNamespace(run=self.push(ref="refs/heads/main2"), parents=self.parents())

    def scenario_main_push(self):
        """main push: 가져오기·병합이 없다(원격이 닿지 않아도 같다)."""
        self.settle(url=self.nowhere)
        before = self.head()
        return SimpleNamespace(before=before, runs=[self.go("push", "refs/heads/main", push_base=base) for base in (self.b1, ZEROS, "")], after=self.head())

    def scenario_manual(self):
        self.settle(url=self.nowhere)
        before = self.head()
        return SimpleNamespace(before=before, runs={ref: self.go("workflow_dispatch", ref) for ref in ("refs/heads/main", f"refs/heads/{BRANCH}")}, after=self.head())

    def scenario_pull_request_event(self):
        self.settle(url=self.nowhere)
        return SimpleNamespace(run=self.go("pull_request", "refs/pull/7/merge", push_base="", extra={"PR_BASE": self.m1}))

    def scenario_missing_variable(self):
        self.settle()
        return SimpleNamespace(run=self.push(drop=("GITHUB_REF",)))

    def scenario_validator_fails(self):
        self.settle()
        on_main = self.go("push", "refs/heads/main", push_base=self.b1, stub_rc=1)
        self.settle()
        on_branch = self.push(push_base=self.b1, stub_rc=1)
        return SimpleNamespace(on_main=on_main, on_branch=on_branch, head=self.head())

    # ---- 시험 ----
    def test_a_first_push_merges_the_new_main_and_checks_the_merged_tree_against_the_main_tip(self):
        scenario = self.scenario("first")
        run = scenario.run
        self.assertEqual((run.code, run.calls), (0, [f"scripts/validate_repo.py --base {self.m2}"]), run.out)
        self.assertEqual(run.notices, [notice_line(self.m2)])                    # 기준 해시가 주석으로 남는다(단계 로그 원문은 로그인이 있어야 읽힌다)
        self.assertEqual(scenario.parents, [self.b2, self.m2])                   # 검증기가 보는 머리는 가지 끝과 main 끝의 병합 커밋이다
        self.assertEqual(run.files, {"a.txt", "b1.txt", "b2.txt", "m1.txt", "m2.txt"})        # 합쳐진 트리: 가지가 바꾼 것과 main 이 앞서 간 것이 함께 있다
        self.assertNotIn(self.fork, run.calls[0])                                # 갈라진 지점이 아니다
        self.assertNotIn(self.b1, run.calls[0])                                  # 브랜치 push 에서 이전 커밋(github.event.before)도 기준이 아니다 — 첫 push 든 이어 올린 push 든 같다

    def test_the_merge_stays_in_the_runner_nothing_is_pushed_and_no_global_setting_is_written(self):
        scenario = self.scenario("first")
        self.assertEqual(scenario.run.code, 0, scenario.run.out)
        self.assertEqual(scenario.remote_after, scenario.remote_before)           # 원격은 그대로 — 병합 결과를 올리지 않았다
        self.assertEqual(scenario.home_files, [])                                 # 전역·사용자 git 설정을 만들지 않았다
        self.assertEqual((scenario.local_name, scenario.local_email), (TEMP_NAME, TEMP_EMAIL))      # 임시 신원은 이 작업 폴더의 로컬 설정에만
        self.assertEqual(scenario.who, f"{TEMP_NAME}|{TEMP_EMAIL}|{TEMP_NAME}|{TEMP_EMAIL}|guardrails: test merge of origin/main (not pushed)")      # 병합 커밋의 신원·메시지는 스크립트가 정한 값(바깥 값이 끼지 않는다)

    def test_a_branch_that_merged_an_older_main_gets_the_newest_main_and_the_tip_is_still_the_base(self):
        """러너 사본이 옛 main 을 알고(checkout 뒤에 main 이 앞서 갔다) 가지도 옛 main 까지만 합쳤어도: 단계가 먼저 가져와 그 끝에서 시험 병합하고, 그 끝이 기준이다."""
        scenario = self.scenario("stale_copy_and_older_main")
        run = scenario.run
        self.assertEqual((run.code, run.calls), (0, [f"scripts/validate_repo.py --base {self.m3}"]), run.out)
        self.assertEqual(run.notices, [notice_line(self.m3)])
        self.assertEqual(scenario.parents, [self.merged_m1, self.m3])
        self.assertLessEqual({"m2.txt", "m3.txt"}, run.files)
        self.assertEqual(scenario.tracking, self.m3)                             # 가져오기가 러너 사본의 origin/main 도 새로 고쳤다

    def test_a_branch_that_already_has_the_main_tip_is_left_exactly_as_it_is(self):
        scenario = self.scenario("already_latest")
        run = scenario.run
        self.assertEqual((run.code, run.calls), (0, [f"scripts/validate_repo.py --base {self.m2}"]), run.out)
        self.assertEqual((scenario.before, scenario.after), (self.merged_m2, self.merged_m2))      # 이미 최신이면 새 병합 커밋을 만들지 않는다
        self.assertEqual(run.notices, [notice_line(self.m2)])

    def test_a_branch_without_commits_of_its_own_just_moves_to_the_main_tip(self):
        scenario = self.scenario("no_commit_of_its_own")
        run = scenario.run
        self.assertEqual((run.code, run.calls), (0, [f"scripts/validate_repo.py --base {self.m2}"]), run.out)
        self.assertEqual(scenario.after, self.m2)
        self.assertEqual(scenario.names, [])                                      # 이 가지가 바꾼 파일이 없다

    def test_bot_commits_piled_on_main_are_merged_and_do_not_show_up_as_this_branchs_changes(self):
        """봇이 main 에 글 커밋을 계속 올린 경우: 병합 결과 트리를 main 끝과 견주면 '이 브랜치가 바꾼 파일'은 가지의 것뿐이다."""
        scenario = self.scenario("bot_commits")
        run = scenario.run
        self.assertEqual((run.code, run.calls), (0, [f"scripts/validate_repo.py --base {self.bot_tip}"]), run.out)
        self.assertLessEqual({"_posts/2026-11-04-a.md", "_posts/2026-11-04-b.md", "history.json"}, run.files)
        self.assertEqual(scenario.names, ["b1.txt", "b2.txt"])                    # 검증기가 '바뀐 파일'로 읽는 것 — 가지의 두 파일뿐
        self.assertEqual(scenario.commits, "3")                                   # 가지의 두 커밋과 병합 커밋 하나
        self.assertIn("_posts/2026-11-04-a.md", scenario.stale_names)             # 갈라진 지점을 기준으로 삼았다면(옛 방식) 봇 글까지 이 가지의 것이 된다
        self.assertIn("history.json", scenario.stale_names)

    def test_a_conflict_with_the_new_main_fails_the_step_before_any_check_and_says_why(self):
        run = self.scenario("conflict").run
        self.assertNotEqual(run.code, 0, run.out)
        self.assertEqual(run.calls, [], run.out)                                  # 검증기는 돌지 않는다(조용한 초록 금지)
        self.assertEqual(len(run.errors), 1, run.out)
        self.assertIn("새 main", run.errors[0])
        self.assertIn("다시 만들어야", run.errors[0])
        self.assertIn("CONFLICT", run.out)                                        # git 이 어느 파일이 충돌했는지 로그에 남긴다
        self.assertEqual(run.notices, [])                                         # 기준을 못 정했는데 '기준' 주석이 남으면 안 된다

    def test_unrelated_histories_fail_the_step_too(self):
        run = self.scenario("unrelated_histories").run
        self.assertNotEqual(run.code, 0, run.out)
        self.assertEqual(run.calls, [], run.out)
        self.assertEqual(len(run.errors), 1, run.out)
        self.assertEqual(run.notices, [])

    def test_a_remote_that_cannot_be_read_fails_the_step_instead_of_using_a_stale_copy(self):
        scenario = self.scenario("unreachable_remote")
        self.assertNotEqual(scenario.run.code, 0, scenario.run.out)               # 가져오기 실패를 숨기지 않는다 — 옛 origin/main 으로 초록을 만들지 않는다
        self.assertEqual((scenario.run.calls, scenario.run.notices), ([], []), scenario.run.out)
        self.assertEqual(scenario.head, self.b2)

    def test_a_remote_without_main_fails_the_step_instead_of_using_a_stale_copy(self):
        scenario = self.scenario("remote_without_main")
        self.assertEqual(scenario.tracking, self.m2)                              # 러너 사본에는 옛 main 이 남아 있었다 — 그래도 쓰지 않는다
        self.assertNotEqual(scenario.run.code, 0, scenario.run.out)
        self.assertEqual((scenario.run.calls, scenario.run.notices), ([], []), scenario.run.out)

    def test_a_base_that_cannot_be_read_ends_with_an_error_annotation(self):
        scenario = self.scenario("base_cannot_be_read")
        run = scenario.run
        self.assertNotEqual(run.code, 0, run.out)
        self.assertEqual(run.calls, [], run.out)
        self.assertEqual(len(run.errors), 1, run.out)
        self.assertIn("origin/main 의 끝", run.errors[0])
        self.assertEqual(run.notices, [])
        self.assertEqual(scenario.head, self.b2)                                  # 기준을 못 구하면 병합도 하지 않는다

    def test_a_merge_that_silently_did_nothing_is_caught_because_the_result_must_contain_the_main_tip(self):
        run = self.scenario("merge_does_nothing").run
        self.assertNotEqual(run.code, 0, run.out)
        self.assertEqual(run.calls, [], run.out)
        self.assertEqual(len(run.errors), 1, run.out)
        self.assertIn("main 끝", run.errors[0])
        self.assertEqual(run.notices, [])

    def test_event_values_are_never_run_as_commands(self):
        scenario = self.scenario("hostile_ref")
        self.assertEqual((scenario.run.code, scenario.run.calls), (0, [f"scripts/validate_repo.py --base {self.m2}"]), scenario.run.out)    # 이름이 이상해도 병합 길로 정상 통과
        self.assertEqual(scenario.made, {"PWNED-SUBST": False, "PWNED-TICK": False, "PWNED-SEMI": False})
        scenario = self.scenario("hostile_previous_commit_on_main")
        self.assertEqual((scenario.run.code, scenario.run.calls), (0, ["scripts/validate_repo.py --base $(touch PWNED-BASE)"]), scenario.run.out)
        self.assertFalse(scenario.made)

    def test_a_ref_that_only_looks_like_main_still_gets_the_test_merge(self):
        scenario = self.scenario("branch_named_like_main")
        self.assertEqual((scenario.run.code, scenario.run.calls), (0, [f"scripts/validate_repo.py --base {self.m2}"]), scenario.run.out)      # 이름에 main 이 들어 있어도 main 이 아니다
        self.assertEqual(scenario.parents, [self.b2, self.m2])

    def test_a_push_to_main_keeps_using_the_commit_before_the_push_and_never_asks_git_or_the_remote(self):
        scenario = self.scenario("main_push")                                     # 원격 주소가 닿지 않는 곳이다 — 가져오기를 했다면 실패했을 것
        expected = [(0, [f"scripts/validate_repo.py --base {self.b1}"]), (0, [f"scripts/validate_repo.py --base {ZEROS}"]), (0, ["scripts/validate_repo.py"])]
        self.assertEqual([(run.code, run.calls) for run in scenario.runs], expected, [run.out for run in scenario.runs])
        # main 의 첫 push(이전 커밋 0)는 검증기가 알아서 건너뛴다 — 지금까지와 같다
        for run in scenario.runs:
            self.assertEqual(run.notices, [])                                     # 기준 주석은 브랜치 push 에서만 — main 실행에는 생기지 않는다
        self.assertEqual(scenario.after, scenario.before)                         # 병합하지 않는다(검사 대상은 push 한 커밋 그대로)

    def test_a_manual_run_has_no_base_as_before_even_on_an_ai_branch_and_does_not_merge(self):
        scenario = self.scenario("manual")
        for ref, run in scenario.runs.items():
            self.assertEqual((run.code, run.calls), (0, ["scripts/validate_repo.py"]), (ref, run.out))
            self.assertEqual(run.notices, [])
        self.assertEqual(scenario.after, scenario.before)

    def test_a_pull_request_event_is_not_a_case_of_this_step_any_more(self):
        """`pull_request` 는 이 워크플로를 시작하지 않지만, 어떤 이유로 그 이벤트 이름이 들어와도 시험 병합 길로 들어가지 않고 기준 없이 도는 수동 길과 같다(옛 PR_BASE 는 없다)."""
        run = self.scenario("pull_request_event").run
        self.assertEqual((run.code, run.calls), (0, ["scripts/validate_repo.py"]), run.out)
        self.assertEqual(run.notices, [])

    def test_a_missing_runner_variable_stops_the_step(self):
        run = self.scenario("missing_variable").run
        self.assertNotEqual(run.code, 0, run.out)                                 # set -u: 정해지지 않은 변수는 멈춤
        self.assertEqual(run.calls, [], run.out)

    def test_a_validator_failure_fails_the_step_on_both_paths_even_after_a_good_test_merge(self):
        scenario = self.scenario("validator_fails")
        for label, run in (("main", scenario.on_main), ("branch", scenario.on_branch)):
            self.assertEqual((run.code, len(run.calls)), (1, 1), (label, run.out))   # 검증기가 실패하면 단계도 실패한다
        self.assertEqual(self.parents(scenario.head), [self.b2, self.m2])         # 브랜치 쪽은 시험 병합까지 하고 나서 실패했다


# ----------------------------------------------------------------------------
# 왜 main 끝이 기준인가 — 시험 병합이 만든 트리에 진짜 검증기(check_ad_surface)를 건다
# ----------------------------------------------------------------------------
@needs_bash
class AdSurfaceOnTheMergedTreeTest(RemoteCase):
    """갈라진 지점 F 에서 가지는 안내 글(notes.md) 또는 레이아웃(_layouts/post.html)을 고치는데, main 은 그 뒤에 광고 표면(index.html)을 고쳤다(다른 PR·봇).
    단계를 실제로 돌려 만든 병합 결과 트리를 진짜 검증기가 본다."""

    @classmethod
    def build(cls):
        _, data = load_workflow()
        cls.script = validation_step(data)["run"]
        repo = cls.repo
        repo.write("pipeline/blogs.json", REGISTRY)
        repo.write("index.html", "<html>v1</html>")
        repo.write("notes.md", "n1")
        repo.git("add", "-A")
        repo.git("commit", "-q", "-m", "base")
        cls.base = repo.git("rev-parse", "HEAD")                                    # 갈라진 지점 F
        repo.git("push", "-q", "origin", "main")
        repo.git("checkout", "-q", "-b", BRANCH)
        notes_head = repo.commit("notes.md", "n2", "notes only")                    # 가지 후보 둘: 안내 글만 / 레이아웃(광고 표면)
        repo.git("reset", "-q", "--hard", cls.base)
        layout_head = repo.commit("_layouts/post.html", "<html>x</html>", "layout tweak")
        repo.git("reset", "-q", "--hard", cls.base)
        repo.git("checkout", "-q", "main")
        tip = repo.commit("index.html", "<html>v2 — main 이 앞서 가며 고침</html>", "landing page changed on main after the branch left")
        repo.git("push", "-q", "origin", "main")
        repo.git("checkout", "-q", BRANCH)
        cls.keep(notes_head=notes_head, layout_head=layout_head, tip=tip)
        repo.git("branch", "-q", "-D", "main")
        cls.start_from(cls.base, cls.tip)

    def run_variant(self, head):
        self.settle(branch=head)
        run = self.push()
        self.assertEqual(run.code, 0, run.out)
        self.assertEqual(len(run.calls), 1, run.out)
        self.assertEqual(run.calls[0].split()[:2], ["scripts/validate_repo.py", "--base"])
        return SimpleNamespace(run=run, merged=self.head(), base=run.calls[0].split()[2], head_before=head)

    def scenario_notes(self):
        return self.run_variant(self.notes_head)

    def scenario_layout(self):
        return self.run_variant(self.layout_head)

    def at(self, name):
        """저장소를 그 시나리오가 만든 병합 결과 트리로 되돌려 놓고 시나리오 결과를 돌려준다(가지 BRANCH 위)."""
        scenario = self.scenario(name)
        self.repo.git("checkout", "-q", "-f", BRANCH)
        self.repo.git("reset", "-q", "--hard", scenario.merged)
        self.state["branch"] = None
        return scenario

    def summary(self, findings):
        return [(f.check, f.level, f.message) for f in findings]

    def test_the_main_tip_as_the_base_ignores_what_main_did_after_the_branch_left(self):
        scenario = self.at("notes")
        self.assertEqual(scenario.base, self.tip)
        self.assertEqual(self.names_between(scenario.base), ["notes.md"])         # 병합 결과 트리에서 이 브랜치가 바꾼 파일은 notes.md 뿐
        self.assertEqual(vr.check_ad_surface(self.repo.root, scenario.base), [])

    def test_the_fork_point_as_the_base_would_report_the_main_side_change_as_this_branchs(self):
        """옛 기준(갈라진 지점)을 병합 결과 트리에 대면 main 쪽 변경이 이 브랜치의 것으로 보여 오탐한다 — 기준을 main 끝으로 바꾼 이유."""
        self.at("notes")
        found = vr.check_ad_surface(self.repo.root, self.base)
        self.assertEqual([f.check for f in found], ["AD-1"])
        self.assertIn("index.html", found[0].message)

    def test_a_protected_change_made_on_the_branch_itself_is_still_caught_and_a_human_approval_passes(self):
        scenario = self.at("layout")
        found = vr.check_ad_surface(self.repo.root, scenario.base)
        self.assertEqual([f.check for f in found], ["AD-1"])
        self.assertIn("_layouts/post.html", found[0].message)
        self.assertNotIn("index.html", found[0].message)                          # main 쪽의 index.html 변경은 이 브랜치의 것이 아니다
        self.repo.git("commit", "-q", "--allow-empty", "-m", "approved\n\nAd-Surface-Approved: 운영자가 채팅으로 승인")
        self.assertEqual(vr.check_ad_surface(self.repo.root, scenario.base), [])    # 사람이 쓴 승인 표시는 시험 병합 커밋이 범위에 끼어도 그대로 통한다

    def test_an_approval_written_by_an_agent_account_is_still_refused_after_the_test_merge(self):
        scenario = self.at("layout")
        agent = ("Copilot", "198982749+Copilot@users.noreply.github.com")
        self.repo.git("commit", "-q", "--allow-empty", "-m", "approved by myself\n\nAd-Surface-Approved: 스스로 승인", identity=agent)
        found = vr.check_ad_surface(self.repo.root, scenario.base)
        self.assertEqual(sorted(f.check for f in found), ["AD-1", "AD-2"])         # 에이전트의 승인 표시는 없는 것으로 본다 — 시험 병합 커밋이 그 규칙을 바꾸지 않는다

    def test_the_protected_list_dropped_on_the_branch_is_still_caught(self):
        scenario = self.at("notes")
        weakened = json.dumps({"schema_version": 1, "defaults": {}, "blogs": [{"key": "chance", "ad_surface": True, "protected_paths": ["_layouts/"]}]})
        self.repo.commit("pipeline/blogs.json", weakened, "drop index.html from the protected list")
        found = vr.check_ad_surface(self.repo.root, scenario.base)
        self.assertEqual([f.check for f in found], ["AD-1"])
        self.assertIn("보호 목록에서 뺀 경로", found[0].message)

    def test_the_range_the_test_merge_checks_equals_what_the_old_pull_request_check_saw(self):
        """옛 PR 검사: 병합 결과 트리(main 끝 + 이 가지)를 main 끝(base.sha)과 견줬다. 시험 병합은 같은 일을 push 시점에 한다 — 같은 결과여야 한다."""
        for number, name in enumerate(("notes", "layout")):
            with self.subTest(variant=name):
                scenario = self.at(name)
                ours = self.summary(vr.check_ad_surface(self.repo.root, scenario.base))
                self.repo.git("checkout", "-q", "-b", f"pr-merge-{number}", self.tip)           # GitHub 의 PR 병합 커밋을 흉내 낸다
                self.repo.git("merge", "-q", "--no-ff", "-m", "Merge pull request", scenario.head_before)
                pull_request = self.summary(vr.check_ad_surface(self.repo.root, self.tip))
                self.repo.git("checkout", "-q", "-f", BRANCH)
                self.assertEqual(ours, pull_request)
        self.assertEqual([item[0] for item in ours], ["AD-1"])                     # 마지막 반복은 광고 표면을 건드렸다 — 양쪽 다 같은 오류

# ----------------------------------------------------------------------------
# 5. 운영자에게 가는 목록에 새는 길이 없다
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
    """확인 필요 모음(운영자에게 가는 목록)은 워크플로 실행을 기본 브랜치로 걸러 읽는다 — 브랜치 push 의 사전 검사 실패는 그 목록에 오르지 않는다."""

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

    def test_a_failed_precheck_on_a_non_ai_branch_is_not_in_the_list_either(self):
        """PR 가지(`copilot/…`·`issue-edit/…`)의 push 검사 실패도 같다 — 목록은 기본 브랜치 실행만 읽는다."""
        for branch in ("copilot/fix-12", "issue-edit/12-about-r5", "feature/x"):
            read, items = self.items([guardrails_run(10, 0.3, "failure", branch, "b" * 40), guardrails_run(9, 3, "success", "main", "a" * 40)])
            self.assertEqual([run["id"] for run in read["guardrails.yml"]], [9], branch)
            self.assertEqual(items, [], branch)

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

    def test_a_cancelled_or_green_precheck_does_not_turn_the_pull_request_red_when_the_pull_request_is_read(self):
        """PR 이 열린 가지의 머리 커밋에는 push 검사의 check-run 이 붙는다(PR 검사는 따로 없다) — 확인 필요 모음은 그 머리 커밋의 검사들을 합쳐 읽는다."""
        green = [h.make_check("검사 (Python 3.10)"), h.make_check("검사 (Python 3.12)")]
        self.assertEqual(inbox.summarize_checks(green + [h.make_check("검사 (Python 3.12)", "cancelled")] + green), "pass")
        self.assertEqual(inbox.summarize_checks(green + [h.make_check("검사 (Python 3.12)", None, "in_progress")]), "pending")
        self.assertEqual(inbox.summarize_checks(green + [h.make_check("검사 (Python 3.12)", "failure")]), "fail")                # 하나라도 빨갛면 빨강 — 같은 코드의 두 검사 중 하나가 간헐 실패해도 같다


if __name__ == "__main__":
    unittest.main()
